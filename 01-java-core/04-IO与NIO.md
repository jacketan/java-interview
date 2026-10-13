# 04 IO 与 NIO

> 一句话定位：IO 是"写业务"到"写中间件"的分水岭，一道 IO 题能同时问出操作系统、JVM、网络协议三层功底 ｜ 面试权重 ★★★★★ ｜ 建议复习 60 分钟

## 本章大纲

- [一、IO 模型全景](#一io-模型全景)
- [二、文件描述符与用户态内核态切换](#二文件描述符与用户态内核态切换)
- [三、多路复用：select poll epoll](#三多路复用select-poll-epoll)
- [四、Java NIO 三大组件](#四java-nio-三大组件)
- [五、零拷贝](#五零拷贝)
- [六、IO 装饰器模式与序列化](#六io-装饰器模式与序列化)
- [七、Netty](#七netty)
- [高级岗三问](#高级岗三问)
- [高频面试题](#高频面试题)
- [易错点与踩坑](#易错点与踩坑)
- [一句话速记](#一句话速记)

## 一、IO 模型全景

### 1.1 版本地图（先记住版本，再谈结论）

| 时间点 | 事件 | 影响 |
| --- | --- | --- |
| JDK 1.0 | `java.io` 包，`InputStream`/`OutputStream`/`Reader`/`Writer` | 阻塞式、流式、装饰器模式 |
| JDK 1.4 (2002) | JSR 51 引入 `java.nio`，`Channel`/`Buffer`/`Selector` | 非阻塞 IO、多路复用，Linux 底层 `poll` |
| JDK 6 及更早 | Linux 上 `Selector` 基于 `poll` | `sun.nio.ch.PollSelectorImpl`，fd 多时性能差 |
| JDK 7 (2011) | JSR 203 `java.nio.file`，`AsynchronousChannel`/`Files`/`Path`/`WatchService`；Linux 上 `SelectorProvider` 默认切到 epoll | AIO、文件属性、目录监听（Linux inotify）、多路复用性能台阶 |
| JDK 8 | `AsynchronousFileChannel` 常用于大文件；`sun.misc.Unsafe` 仍可释放直接内存 | `-XX:MaxDirectMemorySize` 语义成熟 |
| JDK 9 (2017) | `ByteBuffer`/`CharBuffer` 等**子类**为 `flip`/`clear`/`rewind`/`position`/`limit` 增加返回子类型的覆盖方法（`Buffer` 上的同名方法同时去掉 `final`） | `ByteBuffer b = buf.flip()` 可链式调用，不再需要强转；注意 `Buffer` 自带的这些方法返回的仍是 `Buffer` |
| JDK 9 | `InputStream#readAllBytes`/`readNBytes`/`transferTo` | 小文件一次读完、流对拷不再需要第三方 `IOUtils` |
| JDK 9 | `jdk.internal.ref.Cleaner` 取代 `sun.misc.Cleaner`；`Unsafe.invokeCleaner` 公开 | 直接内存释放方式变化，旧反射代码失效 |
| JDK 9 | JEP 290 序列化过滤（backport 到 8u121） | `ObjectInputFilter`、`jdk.serialFilter` |
| JDK 16 起 | JEP 396 默认强封装 JDK 内部 API | 反射替换 `selectedKeys` 一类的优化受限，老版本 Netty 升级要验证 |
| JDK 21 | JEP 444 虚拟线程正式 | `Executors.newVirtualThreadPerTaskExecutor()`，BIO 模型重新可用 |
| JDK 24 | JEP 491 移除 `synchronized` 对虚拟线程的 pinning | 需 JDK 24 才彻底解决载体线程被占用 |

### 1.2 五种 Unix IO 模型

两阶段是所有 IO 讨论的地基：**第一阶段等待数据到达内核缓冲区，第二阶段把数据从内核缓冲区拷贝到用户缓冲区**。

| 模型 | 第一阶段 | 第二阶段 | 系统调用 | Java 对应 |
| --- | --- | --- | --- | --- |
| 阻塞 IO | 阻塞 | 阻塞 | `recvfrom` | `InputStream#read`、`Socket#getInputStream` |
| 非阻塞 IO | 立即返回 `EAGAIN` | 阻塞 | `recvfrom` 轮询 | `SocketChannel#configureBlocking(false)` |
| IO 多路复用 | `select`/`epoll_wait` 阻塞 | 阻塞 | `select`/`epoll_wait` + `recvfrom` | `Selector` |
| 信号驱动 IO | 立即返回，`SIGIO` 通知 | 阻塞 | `sigaction` + `recvfrom` | Java 无原生支持 |
| 异步 IO | 不阻塞 | 不阻塞（内核完成拷贝后通知） | `io_submit`/`aio_read` | JDK 7 `AsynchronousSocketChannel` |

结论先行：

1. **Java NIO 不是"异步 IO"，它是"同步非阻塞 + 多路复用"**。`Selector` 只是告诉你"哪个 fd 可读"，真正的 `read` 仍由你调用并阻塞在数据拷贝上。
2. 只有第五种是真正的异步 IO。Linux 原生 AIO（`io_submit`）只对 `O_DIRECT` 的文件 IO 有效，对 socket 无效；JDK 的 `AsynchronousSocketChannel` 在 Linux 上是 **epoll + 线程池模拟**（`sun.nio.ch.EPollPort` + `ThreadPool`），并不是内核异步。
3. 所以面试里说"Java AIO 性能比 NIO 好"是错的。AIO 在 Linux 上没有性能优势，工程里几乎不用。

```mermaid
flowchart TD
  subgraph BIO["BIO 一连接一线程"]
    A1["accept 阻塞"] --> A2["read 阻塞等待数据"]
    A2 --> A3["线程数等于连接数"]
    A3 --> A4["线程栈按 1MB 计 万连接即 10GB 虚拟内存"]
  end
  subgraph NIO["NIO 事件驱动"]
    B1["Channel 注册到 Selector"] --> B2["epoll_wait 阻塞在事件上"]
    B2 --> B3["只返回就绪的连接"]
    B3 --> B4["少量线程处理全部连接"]
    B4 --> B5["read 仍是同步拷贝 但不会为空闲连接占线程"]
  end
```

### 1.3 BIO / NIO / AIO 对比

| 维度 | BIO | NIO | AIO |
| --- | --- | --- | --- |
| 编程模型 | 流，`read`/`write` 阻塞 | 缓冲区 + 事件，`Channel`/`Buffer`/`Selector` | 回调 / `Future` |
| 是否阻塞 | 读写均阻塞 | 读写不阻塞，事件等待阻塞 | 全异步 |
| 线程与连接 | 1:1 | M:N（1 个 `Selector` 管 N 个连接） | M:N，回调由线程池执行 |
| 触发方式 | 无 | `select`/`poll`/`epoll` | 完成端口 / epoll 模拟 |
| 核心 API | `InputStream`/`OutputStream` | `SocketChannel`/`ByteBuffer`/`Selector` | `AsynchronousSocketChannel` |
| Linux 实现 | `read`/`write` syscall | `epoll` + LT | `EPollPort` + 线程池 |
| 吞吐（连接多、报文小） | 差（线程切换成本高） | 好 | 与 NIO 持平甚至更差 |
| 吞吐（连接少、数据大） | 好（代码最简单） | 一般 | 一般 |
| 典型场景 | 内网低并发、管理接口、批处理 | 网关、RPC、MQ、IM | 少量长连接 + 大文件，生态少 |
| 主要风险 | 线程耗尽、栈内存耗尽 | 编程复杂、空轮询、直接内存泄漏 | 平台差异、调试困难 |

选择建议：

- 连接数 < 几百且交互简单：**BIO 更划算**，别为了炫技上 Netty。
- 连接数上千、长连接、消息型：**NIO / Netty**。
- 团队没有 Netty 经验、Java 21 可用：**虚拟线程 + BIO** 是 2024 年后非常现实的一条路。

### 1.4 BIO 伪异步与 C10K

"伪异步"指的是 `ServerSocket#accept` 后把 `Socket` 丢给线程池，避免一线程一连接：

```java
ServerSocket server = new ServerSocket(8080, 1024); // backlog=1024
ThreadPoolExecutor pool = new ThreadPoolExecutor(
        8, 64, 60L, TimeUnit.SECONDS,
        new LinkedBlockingQueue<>()); // 注意：无界队列
while (true) {
    Socket socket = server.accept();      // 仍然阻塞
    pool.execute(() -> handle(socket));   // 队列无界 -> 压力转成堆内存压力
}
```

它解决了"线程数无限增长"，但没解决三个根本问题：

1. `accept` 是阻塞的，只能一个线程收连接。
2. `LinkedBlockingQueue` 无界，连接堆积时任务对象与 socket 缓冲一起把堆吃满，最终 `OutOfMemoryError`，比直接拒绝连接更糟。正确做法是**有界队列 + `AbortPolicy`/`CallerRunsPolicy` + 快速失败**。
3. 真正的问题是线程模型本身：C10K（1999 年 Dan Kegel 提出，单机 1 万并发连接）要求 **每连接成本与线程无关**，只有事件驱动能做到。C10K 之后还有 C10M，思路是内核旁路（DPDK、XDP）。

生产现象：BIO 服务在连接数上升时表现为 `java.lang.OutOfMemoryError: unable to create new native thread`、`pthread_create failed`、负载不高但 RT 飙高（线程上下文切换），`pidstat -w 1` 的 `cswch/s` 会非常高。

## 二、文件描述符与用户态内核态切换

### 2.1 文件描述符：所有 IO 的账本

Linux 下 socket、文件、管道、epoll 实例都是文件描述符（fd），是**进程级的整数索引**。

| 概念 | 说明 | 查看方式 |
| --- | --- | --- |
| 单进程 fd 上限 | 默认软限制 1024，硬限制可达 1048576 | `ulimit -n`、`cat /proc/<pid>/limits` |
| 系统级 fd 上限 | `fs.file-max`，通常几十万 | `cat /proc/sys/fs/file-max`、`cat /proc/sys/fs/file-nr` |
| 当前已用 fd | 每个 socket、每个打开文件、每个 epoll 实例各占 1 个 | `ls /proc/<pid>/fd` 数条目、`lsof -p <pid>` |
| 线程数也占资源 | 每个线程 1 个栈映射 + 可能的 fd | `ls /proc/<pid>/task` |

几个容易踩的点：

- 一个 `Selector.open()` 就占一个 fd（`epoll_create1`），`Selector` 忘了 `close()` 也是 fd 泄漏。
- classpath 上的 JAR 在 JDK 8 及更早由 `sun.misc.URLClassPath` 缓存的 `JarFile` 持有 fd；微服务依赖上千个 JAR 时，这部分 fd 不可忽略。
- `Too many open files` 是 `IOException`，不是 OOM，但会导致新连接直接被拒。
- 排队连接数由两处决定：内核 `net.core.somaxconn`（Linux 4.x 之前默认 128，5.4 起默认 4096）与 `ServerSocket`/`bind` 的 backlog 参数，取二者较小值。`ss -lnt` 的 `Send-Q` 就是实际生效的 accept 队列长度。

排查命令组合：

```bash
ls /proc/<pid>/fd | wc -l                       # 当前 fd 数
ls -l /proc/<pid>/fd | awk '{print $NF}' | sort | uniq -c | sort -rn | head
ss -s                                            # socket 汇总
ss -tan state close-wait | wc -l                 # CLOSE_WAIT 数量
ss -tan state time-wait | wc -l                  # TIME_WAIT 数量
cat /proc/net/sockstat                           # sockets: used TCP inuse ...
```

### 2.2 用户态与内核态的切换代价

每次 syscall 都要经历：保存用户态上下文 → 切到内核态 → 执行 → 切回用户态。一次 `read` 是 1 次 syscall、2 次模式切换；`read + write` 是 2 次 syscall、4 次模式切换。

切换本身在 x86-64 上是百纳秒级（含 Spectre/Meltdown 缓解后更贵，`KPTI` 使成本上升），但在高 QPS 下会累积成可观的内核态 CPU：

- `vmstat 1`：`sy` 列是内核态 CPU 占比，`cs` 是上下文切换数。
- `pidstat -w -p <pid> 1`：看自愿/非自愿上下文切换。
- `strace -c -f -p <pid>`：统计各 syscall 次数与耗时占比（会显著拖慢进程，只用于诊断）。
- `perf top -p <pid>`：看内核态热函数（常见 `__x64_sys_read`、`tcp_sendmsg`、`copy_user_enhanced_fast_string`）。

**零拷贝的价值就在这里**：不只是省内存带宽，更是省掉整个"用户态缓冲区"往返，把小包高频 IO 的内核态开销压下去。

```mermaid
sequenceDiagram
  participant App as 应用线程
  participant JVM as JDK Selector
  participant K as Linux 内核
  App->>JVM: Selector.open 创建多路复用器
  JVM->>K: epoll_create1 系统调用
  K-->>JVM: 返回 epfd 文件描述符
  App->>JVM: channel.register 注册 OP_READ
  JVM->>K: epoll_ctl 添加 fd 到内核红黑树
  App->>JVM: selector.select 超时 1000 毫秒
  JVM->>K: epoll_wait 阻塞
  K-->>JVM: 返回就绪事件数组
  JVM-->>App: selectedKeys 集合
  App->>JVM: channel.read 读取数据
  JVM->>K: recvfrom 同步拷贝到用户缓冲区
  K-->>App: 返回读取字节数
  Note over App,K: 每次调用都是用户态与内核态的一次往返
```

## 三、多路复用：select poll epoll

### 3.1 三者差异

| 维度 | select | poll | epoll |
| --- | --- | --- | --- |
| 数据结构 | `fd_set` 位图 | `struct pollfd` 数组 | 红黑树 + 就绪链表（`eventpoll`） |
| 单进程 fd 上限 | `FD_SETSIZE`，Linux 上 1024 | 无硬上限，受 `ulimit -n` 限制 | 无硬上限，受 `ulimit -n` 限制 |
| 每次调用是否传 fd 集合 | 是，全量拷贝进内核 | 是，全量拷贝进内核 | 否，`epoll_ctl` 时维护一次 |
| 内核复杂度 | `O(n)` 轮询 | `O(n)` 轮询 | 回调 `O(1)`，`epoll_wait` `O(就绪数)` |
| 返回后定位就绪 fd | 遍历全部，`O(n)` | 遍历全部，`O(n)` | 直接遍历就绪链表 |
| 是否要重置参数 | 是（`fd_set` 是值-结果参数） | `revents` 由内核置位，需自行清零 | 否 |
| 触发模式 | 只有 LT | 只有 LT | LT + ET |
| 内核版本 | 很早 | 2.1.23 | 2.5.44 起 |
| 典型使用 | 老代码、跨平台 | 少量 fd 的跨平台场景 | Nginx、Redis、Netty、Tomcat NIO |

关键差异一句话：**select/poll 的瓶颈是"每次调用都要把 fd 集合拷进内核并线性扫描"，epoll 把这两件事都消掉了**。

### 3.2 epoll 的内核结构

```mermaid
flowchart TD
  subgraph User["用户态"]
    U1["epoll_create1 得到 epfd"]
    U2["epoll_ctl ADD MOD DEL"]
    U3["epoll_wait 取就绪事件"]
  end
  subgraph Kernel["内核 eventpoll 实例"]
    K1["rbr 红黑树 存放监听的 epitem"]
    K2["rdllist 就绪链表"]
    K3["wq 等待队列 阻塞的调用者"]
    K4["ep_poll_callback 回调函数"]
  end
  U2 -->|"插入 删除 修改 O log n"| K1
  K1 --> K4
  K4 -->|"数据到达 挂到就绪链表"| K2
  U3 -->|"有就绪项则直接返回 否则睡眠到 wq"| K2
  K1 -.->|"每个 epitem 绑定 socket 等待队列"| NIC["网卡中断与协议栈 softirq"]
  NIC --> K4
```

要点：

1. `epoll_create1` 创建 `eventpoll` 对象，内含红黑树 `rbr` 与就绪链表 `rdllist`。红黑树解决的是"海量 fd 的增删改查"，不是"查找就绪"。
2. 注册时在 socket 的等待队列上挂 `ep_poll_callback`。数据到达触发协议栈 `softirq`，回调把 `epitem` 挂到 `rdllist`，因此**就绪发现是事件驱动的，不需要轮询**。
3. `epoll_wait` 检查 `rdllist`：非空则直接返回并拷贝就绪事件到用户数组；为空则把当前线程挂到 `wq` 睡眠，被回调唤醒。
4. 所以 epoll 的复杂度是 `O(活跃 fd)`，而 select/poll 是 `O(监听 fd)`。10 万连接里只有 100 个活跃时，差距是千倍级。

### 3.3 LT 与 ET

| 维度 | 水平触发 LT（默认） | 边缘触发 ET（`EPOLLET`） |
| --- | --- | --- |
| 通知条件 | 只要缓冲区还有数据，每次 `epoll_wait` 都通知 | 只在状态变化时通知一次 |
| fd 是否必须非阻塞 | 不强制 | **必须非阻塞**，否则最后一次 `read` 会永久阻塞 |
| 读取要求 | 读一次也行，下次还会通知 | 必须循环 `read` 直到 `EAGAIN` |
| `accept` 要求 | 一次 accept 一个也行 | 必须循环 accept 直到 `EAGAIN`，否则丢连接 |
| 编程复杂度 | 低 | 高，任何一处偷懒都会导致连接假死 |
| 事件次数 | 多，`epoll_wait` 返回次数多 | 少，减少 syscall 次数 |
| 适用 | JDK NIO、Netty 默认（`EpollMode.LEVEL_TRIGGERED`） | Nginx、追求极致 syscall 数的场景 |

**LT 的内核实现（"水平触发"到底怎么做到反复通知）**：

1. `epoll_wait` 进入内核后调用 `ep_poll`，把 `rdllist` 上的就绪 `epitem` 通过 `ep_send_events` 拷贝到用户态事件数组。
2. 拷贝时按触发模式分支：**ET 模式的 `epitem` 处理完就被移出 `rdllist`，不再检查**；**LT 模式的 `epitem` 会被再次调用 `ep_item_poll` 检查底层 fd 当前是否仍然就绪**。
3. 如果仍然就绪（比如接收缓冲区里还有没读完的数据），就把它重新挂回 `rdllist` 尾部，于是下一次 `epoll_wait` 依然会返回它——这就是"水平"二字的来源：只要处在"可读水位"之上，就一直报。
4. 推论：LT 下**忘记读或只读一半不会丢事件**，代价是 `epoll_wait` 被反复唤醒；ET 下漏读就是永久丢事件，所以 ET 必须配合"读到 `EAGAIN`"的循环。

```mermaid
flowchart TD
  Start["epoll_wait 返回可读事件"] --> LT["LT 水平触发"]
  Start --> ET["ET 边缘触发"]
  LT --> L1["缓冲区仍有数据 每次等待都会再次返回"]
  L1 --> L2["读一次也不算错 只是多几次 syscall"]
  ET --> E1["仅在可读状态发生跃迁时通知一次"]
  E1 --> E2["必须循环 read 直到返回 EAGAIN"]
  E2 --> E3["否则剩余数据滞留内核缓冲区 连接假死"]
  E2 --> E4["写侧同理 需 EPOLLOUT 与线程安全配合"]
```

ET 的三个具体陷阱：

1. **`EAGAIN` 判断**：Java 里 `SocketChannel#read` 返回 0 表示暂无数据，`-1` 表示 EOF；native epoll 里返回 `-1` 且 `errno == EAGAIN/EWOULDBLOCK` 才是"读完了"。两者语义不同，写 native 代码时不能混。
2. **`EPOLLOUT` 在 ET 下几乎不可用**：可写状态长期为真，ET 只通知一次，所以必须先尝试写、写满（返回部分写）后才注册 `EPOLLOUT`。Netty 用 `ChannelOutboundBuffer#isWritable` 与 `OP_WRITE` 动态注册解决了这个问题。
3. **`EPOLLONESHOT`**：为了多线程读同一个 fd 不互相打断，可以一次性注册，事件处理完再 `epoll_ctl MOD` 重新武装。

### 3.4 惊群与多 Reactor

- **accept 惊群**：多进程/多线程同时阻塞在同一个 listen fd 的 `accept`，新连接到来全部被唤醒，只有一个成功。Linux 2.6 内核已让 `accept` 只唤醒一个（`WQ_FLAG_EXCLUSIVE`）。
- **epoll_wait 惊群**：多个线程各自 `epoll_wait` 同一个 `epfd`（或多进程 fork 继承）时仍可能全部唤醒。Linux 4.5 引入 `EPOLLEXCLUSIVE` 解决；Nginx 老版本用 `accept_mutex` 应用层互斥。
- **`SO_REUSEPORT`**：Linux 3.9 起，多个进程/线程各自 bind 同一端口，内核按四元组哈希分流，避免单 accept 队列争抢。Nginx、Envoy 的高性能配置常用。
- **Netty 的做法**：boss 组通常只放 1 个 `NioEventLoop`，accept 无竞争；worker 组每个 `EventLoop` 持有独立 `Selector`，连接按 round-robin 注册，天然无锁。

### 3.5 JDK Selector 的实现细节与历史坑

- Linux 上 `SelectorProvider#provider()` 返回 `EPollSelectorProvider`，`openSelector()` 得到 `sun.nio.ch.EPollSelectorImpl`（JDK 7 起；JDK 6 及更早是 `PollSelectorImpl`，Solaris 用 `DevPollSelectorImpl`）。
- JDK 的 epoll 使用 **LT 模式**，没有对外暴露 `EPOLLET`；要 ET 必须用 Netty 的 native transport（`io.netty:netty-transport-native-epoll` + `EpollEventLoopGroup`）。
- **空轮询 bug**：部分内核版本下 `epoll_wait` 返回 0 但 `selectedKeys` 非空（或 select 提前返回），会把阻塞式 `select` 变成忙循环，CPU 打到 100%。这个坑 JDK 6/7 时代就存在，Netty 4.1 至今仍保留兜底：`NioEventLoop#select` 用 `selectCnt` 计数，连续超过 `SELECTOR_AUTO_REBUILD_THRESHOLD`（默认 512）就重建 `Selector`，阈值可用 `io.netty.selectorAutoRebuildThreshold` 覆盖，设为 0 表示关闭该保护。
- 在 JDK 9+ 模块化下，Netty 反射替换 `sun.nio.ch.SelectorImpl#selectedKeys` 为 `SelectedSelectionKeySet`（数组实现）的优化可能受强封装限制；失败只影响性能，不影响功能，需要时用 `--add-opens java.base/sun.nio.ch=ALL-UNNAMED`。
- `Selector#select()` 返回的是**本次 selection 中就绪操作集被更新的 key 数量**（Javadoc 原文 "whose ready-operation sets were updated"），不等于 `selectedKeys.size()`；`selectNow()` 不阻塞，`select(timeout)` 返回 0 也可能是超时。
- `wakeup()` 让阻塞中的 `select` 立即返回，语义是"下一次 `select` 立即返回、不再阻塞"。并发场景下有经典竞态：调用方先 `wakeup()` 再提交任务，任务提交时目标线程可能刚刚判断完队列为空并即将进入 `select`，于是这次唤醒被"吃掉"，任务要等到下一次超时或事件才执行。Netty 用一个唤醒标记（早期 4.1.x 是 `AtomicBoolean wakenUp`，较新的 4.1.x 换成了 `AtomicLong nextWakeupNanos`）配合 `selectNow()` 兜底解决。

## 四、Java NIO 三大组件

### 4.1 Channel

| 实现类 | 是否可非阻塞 | 可否注册 Selector | 关键方法 |
| --- | --- | --- | --- |
| `FileChannel` | 否（`configureBlocking` 不存在） | 否（不是 `SelectableChannel`） | `read`/`write`/`transferTo`/`transferFrom`/`map`/`force`/`lock` |
| `SocketChannel` | 是 | 是（`OP_READ`/`OP_WRITE`/`OP_CONNECT`） | `read`/`write`/`connect`/`finishConnect`/`shutdownOutput` |
| `ServerSocketChannel` | 是 | 是（`OP_ACCEPT`） | `bind`/`accept` |
| `DatagramChannel` | 是 | 是（`OP_READ`） | `send`/`receive` |
| `AsynchronousSocketChannel` | 异步 | 否 | `read(ByteBuffer, A, CompletionHandler)` |

必须记住的一条：**文件 IO 在 Linux 上无法用 `select`/`epoll` 做"非阻塞"**。普通文件永远"就绪"（`epoll` 对普通文件返回 `EPERM`），所以 `FileChannel` 不在 `SelectableChannel` 体系里。想异步读文件只能用 `AsynchronousFileChannel`（底层是线程池），或者依赖 page cache 让 `read` 足够快。

标准读循环（判断退出条件的正确写法）：

```java
SocketChannel ch = SocketChannel.open();
ch.configureBlocking(false);
ch.connect(new InetSocketAddress("127.0.0.1", 8080));

ByteBuffer buf = ByteBuffer.allocateDirect(16 * 1024);
while (true) {
    int n = ch.read(buf);       // 可能返回 0 大于 0 或 -1
    if (n > 0) {
        buf.flip();             // 切到读模式
        while (buf.hasRemaining()) {
            handle(buf.get());
        }
        buf.clear();            // 切回写模式
    } else if (n == 0) {
        // 非阻塞下无数据，交给 Selector 唤醒，不要忙等
        break;
    } else {
        ch.close();             // -1 表示对端关闭
        break;
    }
}
```

### 4.2 Buffer 与 ByteBuffer 的四个索引

`Buffer` 的四个状态变量与不变式：`0 <= mark <= position <= limit <= capacity`。

| 方法 | position | limit | mark | 语义 |
| --- | --- | --- | --- | --- |
| `flip()` | 0 | 原 position | 丢弃 | 写模式切读模式 |
| `clear()` | 0 | capacity | 丢弃 | 读模式切写模式，**不擦数据** |
| `compact()` | `remaining()` | capacity | 丢弃 | 保留未读数据并前移，继续写 |
| `rewind()` | 0 | 不变 | 丢弃 | 重读一遍 |
| `mark()` | 不变 | 不变 | position | 打标记 |
| `reset()` | mark | 不变 | 不变 | 回到标记 |

`remaining() = limit - position`，`hasRemaining() = position < limit`。

```mermaid
stateDiagram-v2
  [*] --> WriteMode
  WriteMode : 写模式 position 向前 limit 等于 capacity
  ReadMode : 读模式 position 到 limit 之间是可读数据
  WriteMode --> ReadMode : flip 把 limit 设为 position 再把 position 归零
  ReadMode --> WriteMode : clear 丢弃全部未读数据
  ReadMode --> WriteMode : compact 把未读数据搬到头部再继续写
  ReadMode --> ReadMode : rewind 只把 position 归零用于重读
  ReadMode --> [*] : 数据消费完毕
```

四个高频踩坑：

1. **`flip` 写成了 `clear`**：写完立刻 `clear()`，`position` 归零、`limit=capacity`，读出来的是一堆 0 字节或上次残留的数据。
2. **`clear()` 不等于清空内容**：它只重置指针。旧数据仍在数组里，靠 `limit` 界定有效范围。用 `buffer.array()` 直接当"数据"用是典型的越界读取。
3. **`compact()` 用错方向**：`compact` 是把"未读部分"搬到头部，用于"数据没读完又来了新数据"的追加写场景。读完了就该用 `clear()`。
4. **`ByteBuffer#equals`/`hashCode` 只比较 `position..limit` 之间的剩余内容**，且 `heap` 与 `direct` 的 `ByteBuffer` 不相等。把 `ByteBuffer` 当 Map 的 key 一定出问题。

补充 API 语义：

- `slice()`：从当前 position 到 limit 切一段**共享底层内存**的视图（新 buffer 的 position 归零、limit 等于剩余量，改一处另一处可见），但 position/limit/mark 各自独立——`java.nio` 的 `ByteBuffer` 没有引用计数，别和 Netty `ByteBuf` 的 `retain()` 混在一起。
- `duplicate()`：复制索引状态，共享内容。
- `asReadOnlyBuffer()`：只读视图。
- `order(ByteOrder)`：字节序，网络协议固定用 `ByteOrder.BIG_ENDIAN`（大端）。
- `ByteBuffer.allocate(cap)` 默认初始 position=0、limit=capacity；`ByteBuffer.allocateDirect(cap)` 同理。

### 4.3 堆内内存 vs 直接内存

| 维度 | `HeapByteBuffer` | `DirectByteBuffer` |
| --- | --- | --- |
| 分配位置 | JVM 堆（受 `-Xmx` 约束） | 堆外（受 `-XX:MaxDirectMemorySize` 约束） |
| 分配成本 | 低，走 TLAB | 高，`Unsafe.allocateMemory` + `Cleaner` 注册 + `Bits` 记账 |
| 回收 | 由 GC 自动完成 | 堆内对象不可达后由 `Cleaner` 释放，存在延迟 |
| 做 IO 是否额外拷贝 | 是，`FileChannelImpl#read` 会先 `Util.getTemporaryDirectBuffer` 再回填 | 否，直接传给 syscall |
| 适用 | 少量、短生命周期、纯计算 | 长生命周期缓冲、Socket IO、Netty |
| 典型异常 | `OutOfMemoryError: Java heap space` | `OutOfMemoryError: Direct buffer memory` |

关键数字与机制：

- `-XX:MaxDirectMemorySize` 默认为 0，含义是"不单独限制，等同于 `Runtime.getRuntime().maxMemory()`"，即最多可占用与 `-Xmx` 相当的堆外内存。所以**大堆 + 大量 Netty 直接内存的进程，实际 RSS 可能是 `Xmx` 的两倍**，容器里极易被 OOMKilled。
- JDK 8 的 `DirectByteBuffer` 构造器里 `Bits.reserveMemory(size, cap)` 记账，超限时先 `System.gc()` 并短暂重试，仍不足才抛 `OutOfMemoryError: Direct buffer memory`。如果启动了 `-XX:+DisableExplicitGC`，这条自救路径被切断，压力会直接变成硬 OOM。
- JDK 9 起释放由 `jdk.internal.ref.Cleaner` 完成（`DirectByteBuffer` 构造器里是 `Cleaner.create(this, new Deallocator(...))`，`CleanerFactory.cleaner()` 是 `FileChannelImpl`、`ZipFile` 等内部类在用的形式）；手动释放走 `sun.misc.Unsafe#invokeCleaner(ByteBuffer)`（JDK 9+ 公开该 API）；JDK 8 只能反射 `sun.misc.Cleaner`，而该类在 JDK 9 已被移除，所以升级后是**运行时**才失败（类不存在，或深反射被模块系统拒绝时抛 `InaccessibleObjectException`），不会是编译期报错。
- 观测手段：`ManagementFactory.getPlatformMXBeans(BufferPoolMXBean.class)` 对应 JMX 的 `java.nio:type=BufferPool,name=direct`，可拿到 `getCount()`、`getMemoryUsed()`、`getTotalCapacity()`；NMT（`-XX:NativeMemoryTracking=detail` + `jcmd <pid> VM.native_memory summary`）用于核对堆外内存总量是否与直接内存账目吻合。

```mermaid
flowchart TD
  D1["ByteBuffer.allocateDirect 申请"] --> D2["Bits.reserveMemory 先记账"]
  D2 --> D3{"totalCapacity 是否超过 MaxDirectMemorySize"}
  D3 -->|"未超过"| D4["Unsafe.allocateMemory 拿到堆外地址"]
  D4 --> D5["构造 DirectByteBuffer 堆内对象持有 address"]
  D5 --> D6["注册 Cleaner 与 Deallocator"]
  D3 -->|"超过"| D7["System.gc 后重试"]
  D7 --> D8{"仍然不足"}
  D8 -->|"是"| D9["抛出 OutOfMemoryError Direct buffer memory"]
  D5 --> D10{"堆内对象是否可达"}
  D10 -->|"可达"| D11["堆外内存不会释放"]
  D10 -->|"不可达"| D12["GC 回收对象 触发 Cleaner.clean"]
  D12 --> D13["Unsafe.freeMemory 归还并解除记账"]
```

### 4.4 Selector

核心 API 与语义：

| 项 | 值 / 说明 |
| --- | --- |
| `SelectionKey.OP_READ` | 1 |
| `SelectionKey.OP_WRITE` | 4 |
| `SelectionKey.OP_CONNECT` | 8 |
| `SelectionKey.OP_ACCEPT` | 16 |
| `interestOps()` | 关心的操作集（自己维护） |
| `readyOps()` | 就绪的操作集（内核置位） |
| `attachment()` | 绑定业务对象（会话、连接上下文） |
| `selector.selectedKeys()` | 返回**内部集合的直接引用**，不是副本 |
| `select()` / `selectNow()` / `select(timeout)` | 阻塞 / 立即返回 / 超时 |
| `wakeup()` | 唤醒阻塞中的 select |
| `keys()` | 全部注册的 key，包含已取消的 |

必背规则：

1. **`selectedKeys()` 迭代时必须 `iterator.remove()`**，否则该 key 会**一直留在集合里**（Javadoc 明确：除了显式 `remove`，selection 操作不会清理 selected-key set），下一轮被当成就绪 key 重复处理；严重时集合只增不减，业务逻辑空转。
2. **`OP_WRITE` 不要长期注册**。socket 发送缓冲区有空间时 `OP_WRITE` 恒为就绪，`select` 会立刻返回，线程 100% 空转。正确做法：写不出去时注册 `OP_WRITE`，写完立刻取消。
3. **`key.cancel()` 只是标记**，真正的注销发生在下一次 `select()`，所以要保证 `select` 会被调用（用 `wakeup()`）。
4. 通道被关闭、key 失效后调用 `key.interestOps()` 会抛 `CancelledKeyException`，处理事件前先 `key.isValid()`。
5. 一个 `Selector` 注册的 `Channel` 必须来自同一个 `SelectorProvider`，否则 `register` 抛 `IllegalSelectorException`。
6. `Selector` 本身不是线程安全的。多个线程共享一个 `Selector` 时，`register` 与 `select` 并发需要自己加锁或通过队列交给 `EventLoop` 线程。

## 五、零拷贝

### 5.1 传统 read + write 的四次拷贝

一次"把磁盘文件发给网络"的经典实现：

```java
FileInputStream in = new FileInputStream("a.dat");
Socket socket = new Socket("host", 80);
byte[] buf = new byte[8192];
int n;
while ((n = in.read(buf)) > 0) {
    socket.getOutputStream().write(buf, 0, n);
}
```

代价：4 次上下文切换（`read` + `write` 各 2 次）与 4 次数据拷贝（2 次 DMA、2 次 CPU）。

```mermaid
flowchart LR
  subgraph Traditional["传统 read 加 write 共 4 次拷贝"]
    T1["磁盘"] -->|"DMA 拷贝"| T2["内核页缓存 page cache"]
    T2 -->|"CPU 拷贝"| T3["用户缓冲区 byte 数组"]
    T3 -->|"CPU 拷贝"| T4["Socket 发送缓冲区"]
    T4 -->|"DMA 拷贝"| T5["网卡"]
  end
  subgraph Sendfile["sendfile 共 2 次拷贝"]
    Z1["磁盘"] -->|"DMA 拷贝"| Z2["内核页缓存"]
    Z2 -->|"只拷贝文件描述符信息"| Z3["Socket 发送缓冲区"]
    Z3 -->|"DMA 拷贝"| Z4["网卡"]
  end
```

### 5.2 三大零拷贝技术

| 技术 | 系统调用 | 拷贝次数 | 上下文切换 | 限制 |
| --- | --- | --- | --- | --- |
| `mmap` + `write` | `mmap` + `write` | 3（页缓存→socket 缓冲区仍是 CPU 拷贝） | 4 | 大文件映射引发大量缺页中断与内存压力 |
| `sendfile` | `sendfile` | 2（支持 SG-DMA 时全 DMA） | 2 | 输入必须是文件，无法在途中修改数据 |
| `splice` | `splice` | 2（经管道，无需硬件 SG-DMA） | 2 | 需要一个管道 fd，Linux 2.6.17 起；**Java 层没有对应 API**，只能靠 JNI |
| `MSG_ZEROCOPY` | `send` + `MSG_ZEROCOPY` | 1 | 2 | 需要网卡与内核支持，通知机制复杂 |

补充两个硬限制：

- **`sendfile` 无法用于 TLS**。数据不经过用户态就没法加密，所以 HTTPS 场景下零拷贝失效，必须回落到"读进堆缓冲 → 加密 → 写"。
- **`sendfile` 不能改数据**。想给文件加个协议头，要么先把头部单独 `write` 再 `transferTo`（两次写可能引发 TCP 小包），要么放弃零拷贝。这是"静态资源服务器 + 中间件"里最常见的取舍点。

### 5.3 Java 侧的 API

```java
FileChannel src = FileChannel.open(Paths.get("big.dat"), StandardOpenOption.READ);
SocketChannel dst = SocketChannel.open(new InetSocketAddress("host", 80));
long position = 0;
long size = src.size();
while (position < size) {
    long n = src.transferTo(position, size - position, dst); // 内部走 sendfile
    if (n <= 0) {                                            // 可能返回 0，必须防止死循环
        break;
    }
    position += n;
}
```

- `FileChannel#transferTo(long position, long count, WritableByteChannel target)`：Linux 下走 `sendfile`，Windows 走 `TransmitFile`。
- `FileChannel#transferFrom(ReadableByteChannel src, long position, long count)`：源必须是 `FileChannel` 才可能零拷贝。
- 单次内核 `sendfile` 有上限（Linux 上约 2GB），`FileChannelImpl#transferTo` 也把单次 `count` 截断到 `Integer.MAX_VALUE` 且**不做内部循环重试**（JDK 8 源码里 sendfile 路径 `transferToDirectly` 只有 EINTR 重试、不做分片循环，分片循环出现在 mmap 兜底路径 `transferToTrustedChannel` 中），所以**返回值可能小于请求长度、甚至为 0**，调用方必须循环并处理 0 的情况。
- `FileChannel#map(MapMode, position, size)` 返回 `MappedByteBuffer`：单次映射大小不能超过 `Integer.MAX_VALUE`（约 2GB），本质是 `mmap`。
- `MappedByteBuffer#force()` 强制刷盘；**没有 `close()`**，解除映射只能等 GC 回收后由 `Cleaner` 调用 `munmap`，长生命周期场景累积映射会导致虚拟内存与 RSS 上涨。

### 5.4 中间件怎么用

| 组件 | 技术选择 | 关键点 |
| --- | --- | --- |
| Kafka | 日志文件读走 `FileChannel#transferTo` sendfile 路径（`FileRecords#writeTo` 对 `TransportLayer` 调用 `transferFrom`，`PlaintextTransportLayer#transferFrom` 内部就是 `FileChannel#transferTo`） | 顺序写 + page cache + sendfile；`SslTransportLayer#transferFrom` 必须读进堆缓冲加密，零拷贝失效 |
| Kafka | 索引文件 `.index`/`.timeindex` 用 `MappedByteBuffer` | 默认 `log.index.size.max.bytes=10485760`（10MB），`log.index.interval.bytes=4096` |
| Kafka | 生产者端 `RecordAccumulator` 批量 + `SocketChannel` | 批大小 `batch.size=16384`、`linger.ms=0`，靠批把 syscall 摊薄 |
| RocketMQ | CommitLog 用 `MappedByteBuffer`（`MappedFile`） | `mappedFileSizeCommitLog=1073741824`（1GB），写内存 + 定时刷盘（`flushIntervalCommitLog=500ms`，`FlushDiskType=ASYNC_FLUSH`） |
| RocketMQ | 读路径依赖 page cache | 消费是随机读 ConsumeQueue + CommitLog，命中页缓存时等价于内存读 |
| Netty | `FileRegion`（`transferTo`）+ `CompositeByteBuf` | 只在 SSL 关闭时走 `FileRegion`，否则必须走 `ChunkedWriteHandler` |
| MySQL | InnoDB 自己的 buffer pool，不依赖 OS 页缓存做零拷贝 | 客户端协议层无零拷贝 |
| Nginx | `sendfile on` 默认开启 | 静态文件 + `tcp_nopush on` 合并头部与小文件 |

**为什么 Kafka 用 sendfile，RocketMQ 用 mmap？**

- Kafka 的消费模型是"按 offset 顺序读日志段并发给消费者"，数据不需要修改，天然适合 `sendfile`：数据不进用户态，broker 进程不消耗 CPU 做拷贝，也不占用堆。
- RocketMQ 需要构建 ConsumeQueue 索引、需要随机读、需要对消息做过滤与重试处理，而且要求写入后立刻可读（依赖 page cache 而不是自己维护 buffer），因此选择 `mmap` 让文件"看着像内存"。
- 代价对比：`sendfile` 省 CPU 但不可改数据、对大文件更友好；`mmap` 灵活但缺页中断与刷盘不可控，文件很大时（几十 GB）映射管理复杂，这也是 RocketMQ 把单一 CommitLog 限制在 1GB 的原因之一。

## 六、IO 装饰器模式与序列化

### 6.1 装饰器模式

`java.io` 是装饰器模式教科书级实现：`FilterInputStream` 持有 `InputStream` 并转发，具体装饰器叠加能力。

```mermaid
classDiagram
  class InputStream {
    +int read()
    +void close()
  }
  class FilterInputStream {
    #InputStream in
    +int read()
  }
  class BufferedInputStream {
    -byte buf
    -int count
    -int pos
    +int read()
  }
  class DataInputStream {
    +int readInt()
    +String readUTF()
  }
  class ObjectInputStream {
    +Object readObject()
  }
  class FileInputStream {
    +int read()
  }
  InputStream <|-- FileInputStream
  InputStream <|-- FilterInputStream
  FilterInputStream <|-- BufferedInputStream
  FilterInputStream <|-- DataInputStream
  InputStream <|-- ObjectInputStream
```

源码级要点：

- `FilterInputStream` 的 `in` 字段是 `protected volatile InputStream in`，所有方法默认直接委托，这正是"装饰"的钩子。
- `BufferedInputStream` 默认缓冲区 `DEFAULT_BUFFER_SIZE = 8192` 字节；`BufferedOutputStream` 同理。`FileInputStream#read()` 单字节读是一次 syscall，套上缓冲后 8KB 一次 syscall，吞吐差数十倍。
- `BufferedOutputStream#flush()` 必须显式调用或 `close()` 触发，否则最后一批数据留在缓冲区里。生产事故：写文件后没 flush 就被别的进程读取，内容缺失。
- `InputStreamReader`/`OutputStreamWriter` 是"装饰器 + 适配器"叠加，负责字节到字符的解码；`FileReader` 用平台默认字符集，**多环境部署必须显式指定 `StandardCharsets.UTF_8`**，否则 JDK 18 之前用默认字符集、JDK 18 起 `file.encoding` 默认 UTF-8。
- `ObjectInputStream` 直接继承 `InputStream` 而不是 `FilterInputStream`，因为它需要按自己的协议读取原始字节。

**Socket 上的坑**：先纠正一个流传很广的说法——`BufferedInputStream` **不会**为了填满 8KB 而阻塞：`fill()` 只调用一次底层 `read`（`getInIfOpen().read(buffer, pos, buffer.length - pos)`），而 socket 的 `read` 有数据就返回。真正的两个坑是：① `read(byte[])` 是**短读**，返回字节数可能小于请求长度，代码若按"循环读到 N 字节"来写协议，对端只发 10 字节就等应答时会死等；② **混用带缓冲与不带缓冲的读**——`BufferedInputStream` 会预读并把数据吞进自己的缓冲区，绕过它直接读底层 `Socket` 流的那次读就会丢数据。长连接协议要么自己按帧长读，要么统一用 `DataInputStream#readFully`。

### 6.2 Serializable 与 serialVersionUID

| 项 | 规则 |
| --- | --- |
| 标记接口 | `java.io.Serializable`，无方法，仅编译期/运行期判断 |
| `serialVersionUID` | 显式声明 `private static final long serialVersionUID = 1L;`，否则由 `ObjectStreamClass#computeDefaultSUID` 按类名/修饰符/接口/字段/静态初始化器/构造器/**方法**算 SHA-1 |
| 不匹配的后果 | `InvalidClassException: local class incompatible: stream classdesc serialVersionUID = x, local class serialVersionUID = y` |
| `transient` | 该字段不参与序列化，反序列化后为默认值（对象为 null，int 为 0） |
| `static` 字段 | 属于类不属于对象，不参与序列化 |
| 父类不可序列化 | 父类字段被初始化为默认值，且**父类的无参构造器会被调用**（子类反序列化时）；父类可序列化时构造器不调用 |
| 自定义钩子 | `writeObject`/`readObject`（必须成对，内部用 `defaultWriteObject`/`defaultReadObject`）、`writeReplace`/`readResolve`、`readObjectNoData` |
| `Externalizable` | 继承 `Serializable`，需 public 无参构造器 + `writeExternal`/`readExternal`，完全自控，性能优于默认反射式序列化 |
| 单例防护 | 实现 `readResolve()` 返回单例，否则反序列化会造出第二个实例 |

序列化流的格式细节：魔数 `0xACED`（`STREAM_MAGIC`）+ 版本 `0x0005`，随后是 `TC_OBJECT`、类描述符、字段值序列。`ObjectStreamClass` 在类描述符里写 `serialVersionUID`，这是跨版本兼容的抓手。

### 6.3 序列化安全：为什么它被业界放弃

JDK 序列化的设计缺陷是把"如何构造对象"的决策权交给了**流里的数据**：`ObjectInputStream#readObject` 会按流中声明的类去加载类、调用其 `readObject`，而 `readObject` 里的任意代码都会执行。

经典利用链（Apache Commons Collections 3.2.1，CVE-2015-4852）：

1. Gadget 入口：`AnnotationInvocationHandler#readObject`（JDK 自带，`sun.reflect.annotation`）在反序列化时对成员值做类型检查，会调用 map 的 `entrySet#iterator` 等方法。
2. 链中转：`TransformedMap`/`LazyMap` 的 `transform` 方法调用 `Transformer` 链。
3. 执行点：`InvokerTransformer#transform` 通过反射调用任意方法；配合 `ConstantTransformer` + `ChainedTransformer` 执行 `Runtime.getRuntime().exec(...)`。
4. 另一条路径：`TemplatesImpl`（`com.sun.org.apache.xalan.internal.xsltc.trax`）的 `newTransformer()` 会加载并执行字节码，配合 `TransformingComparator` 或 `PriorityQueue#readObject` 触发。

`ysoserial` 把这类链工程化，常见 payload 还有 `URLDNS`（仅发起 DNS 请求，用于检测反序列化点）、`JRMPClient`（配合 RMI 打 JNDI）。

防御手段（按有效性排序）：

| 手段 | 具体做法 | 局限 |
| --- | --- | --- |
| 不用 JDK 序列化 | 换 JSON（Jackson）、Protobuf、Thrift、Hessian2/自定义 | 存量系统改造成本 |
| JEP 290 过滤器 | `ObjectInputFilter`、`-Djdk.serialFilter=...`、`ObjectInputFilter.Config.createFilter` | 需要枚举白名单，维护成本高 |
| 黑名单库 | `SerialKiller`、commons-collections 升级到 3.2.2（`InvokerTransformer` 默认不可用） | 只挡已知 gadget |
| 关闭远程 codebase | `com.sun.jndi.rmi.object.trustURLCodebase` 自 8u121 起默认 false，`com.sun.jndi.ldap.object.trustURLCodebase` 自 8u191 起默认 false | 只防 JNDI 注入 |
| 网络隔离与鉴权 | 反序列化端点只对内网开放、加认证 | 不解决漏洞本身 |

`jdk.serialFilter` 的语法示例（模式用分号分隔，`**` 表示通配）：

```bash
# 只允许反序列化白名单内的类，并限制数组长度与深度
-Djdk.serialFilter="com.example.dto.*;java.base/*;!*;maxarray=100000;maxdepth=20"
```

程序内动态设置：

```java
ObjectInputFilter filter = ObjectInputFilter.Config.createFilter(
        "com.example.dto.*;java.base/*;!*;maxdepth=20");
ObjectInputFilter.Config.setSerialFilter(filter);
```

注意：`ObjectInputFilter.Config.setSerialFilter` 只能设置一次，第二次抛 `IllegalStateException`，这在"框架 + 业务都要设置过滤器"的场景是常见冲突源。JDK 17 起新增了 `ObjectInputFilter.Config.setSerialFilterFactory(BinaryOperator<ObjectInputFilter>)`：过滤器工厂会在每个 `ObjectInputStream` 创建（以及设置流级过滤器）时被调用，由它把"JVM 级静态过滤器 + 流级过滤器"合成，从根上解掉"只能设一次"的限制。

## 七、Netty

### 7.1 Reactor 三种模型

| 模型 | 结构 | 优点 | 缺点 | 代表 |
| --- | --- | --- | --- | --- |
| 单 Reactor 单线程 | 1 线程：accept + read + 业务 | 无锁、模型简单 | 业务耗时会阻塞所有连接，无法用多核 | Redis 6.0 之前的网络模型 |
| 单 Reactor 多线程 | 1 个 Reactor 线程 + 业务线程池 | 多核可用于业务 | 单 Reactor 仍是瓶颈，accept/read 串行 | 早期 Tomcat NIO |
| 主从多 Reactor | boss 组 accept，worker 组 read/write/业务 | 高并发、可扩展 | 结构复杂、跨 EventLoop 通信需异步 | Netty、Nginx、Envoy |

```mermaid
flowchart TD
  subgraph Boss["bossGroup 主 Reactor"]
    B1["NioEventLoop 通常只配 1 个线程"]
    B2["Selector 只监听 OP_ACCEPT"]
    B1 --> B2
  end
  B2 -->|"accept 得到 SocketChannel"| C1["按轮询选一个 worker EventLoop"]
  subgraph Worker["workerGroup 从 Reactor"]
    C1 --> W1["Selector 监听 OP_READ"]
    W1 --> W2["ChannelPipeline 依次执行解码器与业务 Handler"]
    W2 --> W3["写回时按需注册 OP_WRITE"]
  end
  subgraph Pool["耗时业务线程池"]
    W2 -->|"阻塞调用或重计算"| P1["DefaultEventExecutorGroup 或自建业务线程池"]
  end
  W3 --> N1["写回客户端"]
```

### 7.2 核心组件

| 组件 | 职责 | 关键实现类 |
| --- | --- | --- |
| `EventLoopGroup` | 线程组管理 | `NioEventLoopGroup`、`EpollEventLoopGroup`、`DefaultEventExecutorGroup` |
| `EventLoop` | 一个线程 + 一个 `Selector` + 任务队列 | `NioEventLoop`、`EpollEventLoop` |
| `Channel` | 连接抽象 | `NioSocketChannel`、`NioServerSocketChannel`、`EpollSocketChannel` |
| `ChannelPipeline` | Handler 双向链表 | `DefaultChannelPipeline` |
| `ChannelHandlerContext` | 链表节点，控制传播方向 | `AbstractChannelHandlerContext` |
| `ByteBuf` | 字节容器 | `PooledByteBufAllocator`、`Unpooled` |
| `ChannelFuture`/`Promise` | 异步结果 | `DefaultChannelPromise` |
| `AttributeKey` | Channel 级上下文数据 | `AttributeKey.valueOf("uid")` |

入站（inbound）事件沿 `head → tail` 传播（`ctx.fireChannelRead`），出站（outbound）沿 `tail → head` 传播（`ctx.write`）。`ChannelHandlerAdapter#isSharable` 决定一个 Handler 实例能否被多个 Channel 共享；带状态（如 `LengthFieldBasedFrameDecoder` 里的累积缓冲区）的 Handler **不能标注 `@Sharable`**，否则会串数据。

### 7.3 线程模型细节（面试高频数字）

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| worker 线程数 | `2 * CPU`（`MultithreadEventLoopGroup.DEFAULT_EVENT_LOOP_THREADS`，可用 `io.netty.eventLoopThreads` 覆盖） | 经验上 IO 密集可 2 倍核数，CPU 密集应回归核数 |
| boss 线程数 | 构造时显式给 1 | 只有一个 listen fd，多线程无益还有惊群风险 |
| `ioRatio` | 50 | `NioEventLoop#run` 中 IO 时间与任务时间的比例 |
| 单次 `select` 阻塞多久 | 由最近一个定时任务的到期时间决定；队列里有任务时先 `selectNow` 立即返回 | `NioEventLoop#select` 与 `DefaultSelectStrategy`，保证定时任务与提交任务不被饿死 |
| `SO_BACKLOG` | `NetUtil.SOMAXCONN`（优先读 `/proc/sys/net/core/somaxconn`，读不到时按平台回退：Linux 4096、macOS 128、Windows 200；实际生效值再与设置值取较小者） | 高并发时应显式设为 1024 以上并同步调内核参数 |
| `TCP_NODELAY` | `true`（Netty 对 `SocketChannel` 默认开启） | 关闭 Nagle 算法，降低小包延迟 |
| `SO_KEEPALIVE` | `false` | 靠 `IdleStateHandler` 做应用层心跳更可控 |
| `WRITE_BUFFER_WATER_MARK` | 低 32KB / 高 64KB（`WriteBufferWaterMark.DEFAULT`） | `isWritable()` 的判定依据，用于反压 |
| `RCVBUF_ALLOCATOR` | `AdaptiveRecvByteBufAllocator.DEFAULT`（最小 64、最大 65536，初始值较新的 4.1.x 是 2048、早期版本是 1024） | 自适应接收缓冲区，小包省内存大包少 syscall |
| `ResourceLeakDetector` 级别 | `SIMPLE` | 可调 `io.netty.leakDetection.level=paranoid` |

为什么 EventLoop 内部可以不用锁：一个 `Channel` 从注册那一刻起就绑定到唯一 `EventLoop`，其生命周期内所有事件都在同一个线程上串行执行，业务 Handler 因此天然是"单线程模型"，不需要加 `synchronized`。跨 `EventLoop` 提交任务时用 `channel.eventLoop().execute(task)`，返回 Promise 而不是直接阻塞等待。

### 7.4 ByteBuf

与 `ByteBuffer` 的最大差别是**读写索引分离**，不需要 `flip()`：

| 属性 | 含义 |
| --- | --- |
| `readerIndex` | 下一个读位置 |
| `writerIndex` | 下一个写位置 |
| `capacity` | 当前容量 |
| `maxCapacity` | 扩容上限，默认 `Integer.MAX_VALUE`（`AbstractByteBufAllocator.DEFAULT_MAX_CAPACITY`），初始容量默认 256 |
| `readableBytes()` | `writerIndex - readerIndex` |
| `writableBytes()` | `capacity - writerIndex` |

四种形态：

1. `UnpooledHeapByteBuf`：堆内数组，分配快，做 IO 多一次拷贝。
2. `UnpooledDirectByteBuf`：堆外内存，适合 IO。
3. `PooledByteBuf`（`PooledDirectByteBuf`/`PooledHeapByteBuf`）：`PooledByteBufAllocator` 默认分配器，jemalloc 风格，`PoolArena` → `PoolChunk`（`pageSize` 默认 8KB，`chunkSize = pageSize << maxOrder`）→ 完全二叉树位图分配，再配 `tinyCacheSize`/`smallCacheSize`/`normalCacheSize` 线程缓存减少锁竞争。**这几个默认值改过版本**：较新的 4.1.x（如 4.1.12x）是 `maxOrder=9`（chunk 4MB）+ `tinyCacheSize=0`（tiny 缓存默认关闭），早期 4.1.x（如 4.1.25）是 `maxOrder=11`（chunk 16MB）+ `tinyCacheSize=512`；`smallCacheSize=256`、`normalCacheSize=64` 两版一致，都可用 `io.netty.allocator.*` 覆盖。
4. `CompositeByteBuf`：把多个 `ByteBuf` 组合成一个逻辑视图，**不拷贝数据**，用于"头部 + body"场景。

其他要点：

- `slice()`/`duplicate()` 共享底层内存且**共享引用计数**，必须配合 `retain()`；`retainedSlice()` 是二者合一。
- `readRetainedSlice()` 与 `slice()` 的区别只在引用计数是否加 1，是内存泄漏的高发区。
- `ByteBufAllocator.DEFAULT` 在 4.1 中是池化分配器；可用 `-Dio.netty.allocator.type=unpooled` 切回非池化（排查问题时常用）。
- `Arena` 数量默认为 `min(2 × CPU 核数, 内存上限 / chunkSize / 2 / 3)`（即除以 6），其中堆 Arena 用 `Runtime.maxMemory()`、直接内存 Arena 用 `PlatformDependent.maxDirectMemory()`；可用 `io.netty.allocator.numDirectArenas` 与 `numHeapArenas` 覆盖。

### 7.5 粘包与拆包

TCP 是面向字节流的协议，没有消息边界。出现"粘包"的三种原因：应用写入大于 MSS 的消息被拆开；应用连续多次 write 被合并成一个 TCP 段（Nagle 算法）；接收方一次 `read` 读到多个消息（读循环里恰好凑齐）。

```mermaid
sequenceDiagram
  participant S as Socket 内核缓冲区
  participant D as ByteToMessageDecoder
  participant L as LengthFieldBasedFrameDecoder
  participant H as 业务 Handler
  S->>D: 触发 channelRead 携带一段 ByteBuf
  D->>D: 累加到 cumulation 累积缓冲区
  D->>L: 交给解码器处理 cumulation
  L->>L: 读长度字段 判断可读字节是否足够一帧
  alt 不足一帧
    L-->>D: 不消费任何字节 等下一次 TCP 报文
  else 凑齐完整帧
    L-->>D: 切出 frame 并按 initialBytesToStrip 去掉长度字段
    D->>H: fireChannelRead 完整业务消息
  end
```

四种解法与对应解码器：

| 方案 | 解码器 | 适用 |
| --- | --- | --- |
| 固定长度 | `FixedLengthFrameDecoder` | 定长协议，简单但不灵活 |
| 分隔符 | `LineBasedFrameDecoder`、`DelimiterBasedFrameDecoder` | 文本协议、Redis 协议 |
| 长度字段 | `LengthFieldBasedFrameDecoder` | 二进制 RPC、自定义协议（主流） |
| 自定义状态机 | 继承 `ByteToMessageDecoder` | 复杂协议（HTTP/2、MQTT） |

`LengthFieldBasedFrameDecoder` 的五个参数必须背下来：

```java
// maxFrameLength, lengthFieldOffset, lengthFieldLength,
// lengthAdjustment, initialBytesToStrip
new LengthFieldBasedFrameDecoder(1024 * 1024, 0, 4, 0, 4);
// 含义：最大 1MB，长度字段在偏移 0，占 4 字节，长度值等于剩余报文长度，解析后去掉这 4 字节
```

- `lengthAdjustment`：当长度字段的值包含自身长度或包含头部其他字段时用于校正（可正可负）。
- `initialBytesToStrip`：剥离的头部长度，通常等于"长度字段偏移 + 长度字段长度"。
- 编码侧对应 `LengthFieldPrepender(4)`，或在自定义编码器里把长度写进头部。
- `ByteToMessageDecoder` 会循环调用 `decode` 直到 `cumulation` 读不出完整消息，并把剩余数据留到下次；这也是它不能加 `@Sharable` 的原因。

### 7.6 为什么 Netty 快

1. **主从多 Reactor + 单线程串行化**：一个连接只在一个 `EventLoop` 上处理，无锁化，避免伪共享与锁竞争。
2. **池化内存 + 自适应缓冲**：`PooledByteBufAllocator` 用 jemalloc 思路管理 `PoolChunk`，`AdaptiveRecvByteBufAllocator` 按历史请求量动态调整 `ByteBuf` 大小，减少分配次数与内存占用。
3. **减少拷贝**：`CompositeByteBuf` 组合、`slice` 视图、`FileRegion`（`transferTo`）、`ByteBuf` 直接内存，全链路尽量不拷贝。
4. **无锁队列与 `FastThreadLocal`**：任务队列用 JCTools 的 `MpscQueue`（`PlatformDependent.newMpscQueue`），`FastThreadLocal` 用数组下标代替 `ThreadLocalMap` 的哈希查找。
5. **Selector 优化**：用数组实现 `SelectedSelectionKeySet` 替代 `HashSet` 遍历，减少装箱与迭代开销。
6. **可插拔的 native transport**：`EpollEventLoopGroup` + `SO_REUSEPORT`、`edge-triggered`（`EpollMode.EDGE_TRIGGERED`）、`TCP_FASTOPEN` 等 Linux 特性，仅在 `Epoll.isAvailable()` 为 true 时启用。
7. **避免线程上下文切换**：业务耗时操作请交给 `DefaultEventExecutorGroup`，但**不要把 IO 也搬过去**，否则 Netty 的优势全丢。

### 7.7 Netty 语境下的"零拷贝"（四种含义）

很多候选人只答 `FileRegion`，其实 Netty 文档里的 zero-copy 有四层：

1. **堆外直接内存**：`ByteBuf` 分配在堆外，socket 读写不额外拷贝。
2. **组合缓冲区**：`CompositeByteBuf` 把协议头与消息体组合，不复制字节。
3. **视图切片**：`slice()`/`duplicate()`/`unwrap()` 返回共享内存的视图。
4. **文件传输**：`FileRegion` 内部 `FileChannel#transferTo`，走 `sendfile`；一旦 pipeline 里有 `SslHandler`，`FileRegion` 无法工作，必须用 `ChunkedWriteHandler` 或回落到普通写。

### 7.8 生产参数与故障模式速查

| 现象 | 可能原因 | 定位手段 |
| --- | --- | --- |
| `OutOfMemoryError: Direct buffer memory` | 直接内存泄漏或 `MaxDirectMemorySize` 太小 | 打开 paranoid 泄漏检测、看 `BufferPoolMXBean` 的 `memoryUsed` 曲线、NMT |
| 连接建立后立即被关闭 | `SO_BACKLOG` 太小、accept 队列溢出 | `ss -lnt` 看 `Send-Q`/`Recv-Q`、`netstat -s` 里的 listen 队列溢出计数 |
| RT 抖动、吞吐上不去 | 业务在 `EventLoop` 线程里做了阻塞调用 | `jstack` 看 `NioEventLoop` 线程栈、`WRITE_BUFFER_WATER_MARK` 触发 `isWritable=false` |
| 内存持续上涨且 GC 后不降 | `ByteBuf` 未 `release()` | `-Dio.netty.leakDetection.level=paranoid`，看 `LEAK: ByteBuf.release() was not called` 日志 |
| 客户端超时但服务端无日志 | 粘包导致解码器一直等数据 | 抓包看 `tcpdump -i any port 8080 -A`、打印 `cumulation.readableBytes()` |
| CPU 100% 且无业务量 | `Selector` 空轮询或 `OP_WRITE` 长期注册 | 火焰图定位到 `EPollSelectorImpl#doSelect`/`NioEventLoop#select` |

## 高级岗三问

**问 1：为什么这么设计？**
三次取舍值得记住：`epoll` 用红黑树 + 回调换掉了 select 的"全量拷贝 + 线性扫描"；Netty 用"一个连接绑定一个线程"换掉了锁，代价是业务不能阻塞；Kafka 用 `sendfile` 换掉了用户态拷贝，代价是不能改数据、不能用 TLS 加速。**任何"高性能"背后都有一份被放弃的灵活性**，答出代价比答出优点更像架构师。

**问 2：线上出问题怎么定位？**
固定五步：`ss -s` / `ss -tan state xxx` 看连接状态分布 → `ls /proc/<pid>/fd | wc -l` 看 fd 泄漏 → `pidstat -w 1 -p <pid>` 与 `vmstat 1` 看上下文切换与内核态 CPU → `strace -c -p <pid>` / `perf top -p <pid>` 定位 syscall 热点 → JVM 侧 `jstack`、NMT、`BufferPoolMXBean` 定位直接内存。这套顺序能覆盖 90% 的 IO 类故障。

**问 3：规模变大后会怎样？**
连接数从 1 万到 100 万：fd、`somaxconn`、`tcp_max_syn_backlog`、epoll 就绪事件数组大小、直接内存总量、心跳定时器数量都会成为瓶颈；再往上会遇到单机网卡软中断（`softirq`）单核打满，需要用 `SO_REUSEPORT`、多队列网卡 `RSS`、`XDP`/`DPDK`。数据量变大：Kafka 的 page cache 命中率下降、`sendfile` 收益不变但磁盘成为瓶颈；RocketMQ 的 1GB CommitLog 文件数变多，刷盘与索引重建成本上升。

## 高频面试题

### Q1. BIO、NIO、AIO 的本质区别是什么？为什么说 Java NIO 不是异步 IO？

**答题框架（30 秒版）**：区别在"两个阶段是否阻塞"——数据准备与数据拷贝。BIO 两阶段都阻塞；NIO 用 `Selector` 把数据准备阶段变成事件通知，但 `read` 拷贝阶段仍同步阻塞，所以是**同步非阻塞**；AIO 两阶段都不阻塞，由内核完成后回调。

**展开（2 分钟版）**：
1. 五种 Unix IO 模型里只有异步 IO 是第二阶段也不阻塞的。
2. Linux 上 JDK 的 `AsynchronousSocketChannel` 由 `sun.nio.ch.EPollPort` + 线程池实现，内核层面仍是同步 IO，所以性能不比 NIO 好。
3. 工程选型：连接少用 BIO；连接多用 NIO/Netty；Java 21 之后虚拟线程让 BIO 重新可用（`Executors.newVirtualThreadPerTaskExecutor()`），JEP 491 在 JDK 24 移除了 `synchronized` 的 pinning 限制。

**追问**：「虚拟线程能替代 Netty 吗？」答：批量长连接、需要精确控制内存与背压的场景 Netty 仍占优；虚拟线程的优势是让既有阻塞代码直接获得高并发能力，代价是每个连接仍有栈与调度开销，且需要 JDK 21+。

### Q2. select、poll、epoll 有什么区别？epoll 为什么高效？

**答题框架（30 秒版）**：三点差异——fd 上限（1024 对无上限）、是否每次全量拷贝 fd 集合（是/否）、内核查找就绪的复杂度（`O(n)` 对 `O(就绪数)`）。epoll 用红黑树管理监听集合、用 `ep_poll_callback` 回调把就绪 fd 挂到就绪链表，`epoll_wait` 只遍历就绪链表。

**展开（2 分钟版）**：
1. `epoll_create1` 返回 `epfd`，内核建 `eventpoll`，含 `rbr` 红黑树与 `rdllist` 就绪链表。
2. `epoll_ctl ADD` 把 fd 对应的 `epitem` 插入红黑树，并在 socket 等待队列注册回调。
3. 数据到达 → 协议栈 `softirq` → 回调把 `epitem` 挂到 `rdllist` → 唤醒 `epoll_wait`。
4. 复杂度：epoll 是 `O(活跃 fd)`，select/poll 是 `O(监听 fd)`；但有大量活跃连接时 epoll 优势会下降。

**追问**：「epoll 一定比 select 快吗？」答：不一定。fd 少且几乎全活跃时，epoll 的 `epoll_ctl` 维护成本与 `epoll_wait` 拷贝成本摊不薄，select 反而更轻；epoll 的杀手场景是"连接多、活跃少"。

### Q3. epoll 的 LT 与 ET 有什么区别？为什么 JDK 和 Netty 默认用 LT？

**答题框架（30 秒版）**：LT 只要缓冲区有数据就反复通知，编程简单；ET 只在状态跃迁时通知一次，必须循环读到 `EAGAIN`，且 fd 必须非阻塞。JDK 的 `EPollSelectorImpl` 没有暴露 `EPOLLET`，Netty 默认也是 `EpollMode.LEVEL_TRIGGERED`——因为 LT 的容错性好，漏读最多多几次 `epoll_wait`，不会连接假死。

**展开（2 分钟版）**：
1. ET 的三个硬要求：非阻塞 fd、`read` 循环到 `EAGAIN`、`accept` 循环到 `EAGAIN`。
2. ET 下 `EPOLLOUT` 的注册时机需要"先写满再注册"，否则永远收不到通知。
3. 想用 ET：Netty native transport + `EpollChannelConfig#setEpollMode(EpollMode.EDGE_TRIGGERED)`，或用 `EPOLLONESHOT` 做多线程分工。

**追问**：「Nginx 为什么用 ET？」答：Nginx 用少量 worker 进程处理海量连接，ET 能显著减少 `epoll_wait` 的返回次数与 syscall 开销，而 Nginx 自己保证每个可读 fd 被读到 `EAGAIN`，所以敢用。

### Q4. ByteBuffer 的 flip、clear、compact 有什么区别？你踩过什么坑？

**答题框架（30 秒版）**：`flip` 写转读（`limit=position; position=0`）；`clear` 读转写并**丢弃全部未读**；`compact` 读转写但**保留未读数据并搬到头部**。核心不变式 `mark <= position <= limit <= capacity`。

**展开（2 分钟版）**：
1. 写完忘了 `flip` 直接读，读到 0 字节；写完用了 `clear` 再读，读到脏数据。
2. `compact` 的典型场景是"半包"：数据没读完又来了新数据，先 `compact` 把未读部分前移，再继续 `write`。
3. `ByteBuffer#equals` 只比较剩余内容且不允许 heap 与 direct 互等，不能做 Map key。
4. 直接内存用 `allocateDirect`，长期持有要注意 `-XX:MaxDirectMemorySize` 与 `Cleaner` 的释放延迟。

**追问**：「`ByteBuffer` 线程安全吗？」答：不安全，`position`/`limit` 是普通字段，多线程共享必须自己同步或用 Netty 的 `ByteBuf`（也不安全，但提供了 `retainedSlice` 等引用计数工具）。

### Q5. 零拷贝有哪几种实现？Kafka 和 RocketMQ 各用哪种？为什么？

**答题框架（30 秒版）**：`mmap`+`write`、`sendfile`、`splice`、`MSG_ZEROCOPY`。Kafka 用 `sendfile`（`FileChannel#transferTo`）顺序读日志段；RocketMQ 用 `mmap`（`MappedByteBuffer`）承载 CommitLog 与索引，因为它需要随机读、构建 ConsumeQueue 索引并依赖 page cache 立即可读。

**展开（2 分钟版）**：
1. 传统 read+write：4 次拷贝 4 次切换；`mmap` 3 次拷贝；`sendfile` 2 次拷贝（SG-DMA 下全 DMA）。
2. `sendfile` 不能改数据、不能做 TLS；`mmap` 有缺页中断与卸载困难。
3. Netty 的"零拷贝"还有 `CompositeByteBuf`、`slice`、堆外内存三层含义。

**追问**：「HTTPS 场景零拷贝还有用吗？」答：`sendfile` 失效因为数据必须进用户态加密；可以退化到 `mmap` 减少一次拷贝，或者用支持内核 TLS（`kTLS`）的方案。

### Q6. 【场景设计】设计一个支撑 50 万长连接的推送网关，你怎么选型与拆分？

**答题框架（30 秒版）**：接入层用 Netty 主从多 Reactor，单机连接数按 5 万~10 万规划，水平扩 N 台；会话路由用 Redis 记录 `uid → 网关实例`；消息投递用 MQ 广播到各网关；心跳用 `IdleStateHandler` + 应用层 ping/pong。

**展开（2 分钟版）**：
1. 接入层：`bossGroup=1`、`workerGroup=2*CPU`；`SO_BACKLOG=2048`；`TCP_NODELAY=true`；`WRITE_BUFFER_WATER_MARK` 做反压；`SO_KEEPALIVE=false` 改用心跳。
2. 内存预算：每连接按 10KB 直接内存估算，5 万连接约 500MB 直接内存，`-XX:MaxDirectMemorySize` 必须显式设置，容器内存 = 堆 + 直接内存 + 栈 + 元空间 + 预留。
3. 系统参数：`ulimit -n 1000000`、`net.core.somaxconn=32768`、`net.ipv4.tcp_max_syn_backlog=32768`、`net.ipv4.ip_local_port_range`、`net.ipv4.tcp_rmem/tcp_wmem`、关闭 `tcp_tw_recycle`（4.12 内核已移除）。
4. 连接保活与摘除：心跳超时 3 个周期踢连接；实例下线先摘除路由再 `graceful shutdown`（`EventLoopGroup#shutdownGracefully`）。
5. 水平扩展的失效模式：连接数受单机 fd 与内存限制；广播类消息随网关数线性放大流量；跨实例投递需要处理"用户刚好重连到另一台"的竞态，用会话版本号或本地投递 + 一次重试兜底。

### Q7. 【线上排查】服务大量 `CLOSE_WAIT`、报 `Too many open files`，怎么定位？

**答题框架（30 秒版）**：`CLOSE_WAIT` 是**本端收到 FIN 但没有调用 `close()`**，属于应用 bug，不是内核参数问题。先量化、再定位、最后修复。

**展开（2 分钟版）**：
1. 量化：`ss -tan state close-wait | wc -l`、`ss -tan state close-wait | awk '{print $5}' | sort | uniq -c | sort -rn` 找出对端分布；`ls /proc/<pid>/fd | wc -l` 与 `cat /proc/<pid>/limits` 确认是否触及 `ulimit -n`。
2. 定位：`jstack <pid> | grep -A 20 "http-nio"` 看线程是否卡在 `SocketInputStream#read`；`lsof -p <pid> | grep -c socket` 看 socket 增长；结合 `fat jar` 里连接池配置检查是否有未关闭的 `Connection`/`InputStream`。
3. 三类根因：A) 忘记 `finally { close() }`；B) 读到 `read() == -1` 后没有关闭；C) 连接池归还逻辑异常（`abandoned` 未开）。
4. 修复与加固：`try-with-resources`、连接池开启泄漏检测（如 HikariCP `leakDetectionThreshold=20000`，Druid `removeAbandoned=true` + `removeAbandonedTimeout`）、临时把 `ulimit -n` 调大续命但不算修复。
5. 反向指标：大量 `TIME_WAIT` 通常是**本端主动关闭**，属于正常现象（2MSL 60 秒），可用连接池长连接 + `tcp_tw_reuse` 缓解，但不要用已废弃的 `tcp_tw_recycle`。

### Q8. 【线上排查】Netty 服务运行几天后直接内存被吃满，怎么定位与修复？

**答题框架（30 秒版）**：先确认是"真泄漏"还是"配额太小"，用泄漏检测 + `BufferPoolMXBean` 曲线 + NMT 三件套区分，再顺着 `ByteBuf` 的生命周期找漏掉 `release()` 的位置。

**展开（2 分钟版）**：
1. 量化：`jcmd <pid> VM.native_memory summary`（需 `-XX:NativeMemoryTracking=detail`）看 `Internal`/`Other`；JMX 取 `BufferPoolMXBean#getMemoryUsed` 打点到监控，观察是否只涨不落。
2. 打开检测：`-Dio.netty.leakDetection.level=paranoid`，日志里会出现 `LEAK: ByteBuf.release() was not called before it's garbage-collected` 并给出分配处的堆栈（`targetRecords=4` 决定记录数）。
3. 常见根因：`SimpleChannelInboundHandler` 会自动 release，而继承 `ChannelInboundHandlerAdapter` 时必须手动 `ReferenceCountUtil.release(msg)`；`readRetainedSlice` 后忘记 `release`；异常分支提前 return 导致漏 release；把 `ByteBuf` 交给业务线程池后没有 `retain()`/`release()` 配对。
4. 治本：所有 inbound 处理统一走 `SimpleChannelInboundHandler` 或 `finally` 中 release；跨线程传递必须 `retain()`；压测阶段就开 paranoid。
5. 不要只调大 `-XX:MaxDirectMemorySize`：那只是延后爆炸时间，且容器的内存上限不会因此变大。

### Q9. 【场景设计】让你设计一个 RPC 协议，怎么解决粘包拆包并兼顾扩展性？

**答题框架（30 秒版）**：用"定长头 + 变长体"，头部含魔数、版本、序列化类型、消息类型、请求 ID、body 长度；解码用 `LengthFieldBasedFrameDecoder`，编码用自定义 `MessageToByteEncoder`。

**展开（2 分钟版）**：
1. 头部定长：`magic(2) + version(1) + serializeType(1) + msgType(1) + status(1) + requestId(8) + bodyLength(4)` 一共 **18 字节**；想压到 16 字节，就把 `version`/`serializeType`/`msgType` 塞进同一个 flag 字节。定长才能用 `getInt`/`getLong` 直接定位字段，也便于 `initialBytesToStrip` 一次性剥离。
2. 解码链：`LengthFieldBasedFrameDecoder(maxFrameLength=1MB, 0, 4, 0, 0)` 拿到完整帧 → 自定义解码器读头部、校验魔数 → 按 `serializeType` 选反序列化器 → 交给业务 Handler。
3. `maxFrameLength` 必须设置，否则恶意长度字段会让对端申请巨大缓冲区（内存放大攻击）。
4. 扩展性：头部预留 `status`、`version` 支持灰度；序列化类型做成可插拔（Protobuf/Hessian2/JSON），新老版本靠 `version` 协商。
5. 配套：`IdleStateHandler` 做心跳，`LengthFieldPrepender` 或自定义编码器写长度，异常时回一条带 `status` 的错误响应而不是直接断连。

### Q10. 为什么生产环境不推荐 JDK 原生序列化？如果必须用怎么加固？

**答题框架（30 秒版）**：三个原因——安全问题（`readObject` 可被 gadget chain 利用执行任意代码）、性能问题（反射 + 类描述符元数据冗余，序列化后体积通常大于 Protobuf/JSON，且不支持跨语言）、兼容性问题（`serialVersionUID` 变更即报 `InvalidClassException`）。加固首选 JEP 290 白名单过滤器。

**展开（2 分钟版）**：
1. 经典链：`AnnotationInvocationHandler` + `TransformedMap` + `InvokerTransformer`（commons-collections 3.2.1，CVE-2015-4852）；`TemplatesImpl` 直接加载字节码；`ysoserial` 一键生成。
2. 加固：`-Djdk.serialFilter="com.example.dto.*;!*;maxdepth=20"` 或代码里 `ObjectInputFilter.Config.setSerialFilter`（只能设置一次）；升级 commons-collections 到 3.2.2；JNDI 侧 `com.sun.jndi.rmi.object.trustURLCodebase`（8u121 起默认 false）与 `com.sun.jndi.ldap.object.trustURLCodebase`（8u191 起默认 false）。
3. 长期方案：RPC 换 Protobuf/Thrift/JSON。
4. `serialVersionUID` 实践：**永远显式声明**，否则加一个字段就导致不兼容；`transient` 用于密码、连接、大缓存等不该上线的字段。

### Q11. 【线上排查】一个 HTTP 服务 QPS 不高但 `sy`（内核态 CPU）很高，方向在哪？

**答题框架（30 秒版）**：`sy` 高说明 syscall 或中断开销大，通常是**小包高频读写**、**大量短连接**、**日志同步刷盘**或**频繁 `System.gc`/线程创建**导致。用 `strace -c` 看 syscall 分布，用 `perf top` 看内核热函数。

**展开（2 分钟版）**：
1. 先分流：`vmstat 1` 看 `sy`、`cs`、`in`（中断）；`pidstat -w -p <pid> 1` 看上下文切换；`/proc/<pid>/status` 的 `voluntary_ctxt_switches`。
2. `strace -c -f -p <pid>`：若 `read`/`write`/`recvfrom` 次数远高于请求数，说明没有批量；若 `futex`/`epoll_wait` 极高，说明线程争用或空轮询。
3. 常见治理：开启 `TCP_NODELAY` 之外的批量（Kafka 的 `batch.size`/`linger.ms`）；把短连接改成 keep-alive；日志异步（`AsyncAppender`）或降级；把 `net.core.somaxconn` 与 accept 队列调大减少重传。
4. 别忘了应用层：`strace` 里 `openat` 次数过多往往是**每次请求都新建文件/连接**，改成池化即可。

### Q12. Netty 解决了什么问题？什么场景不该用 Netty？

**答题框架（30 秒版）**：Netty 用主从多 Reactor 把"高并发网络编程"变成"写 Handler"，同时提供成熟的编解码、心跳、背压、内存池。不该用的场景是：内部低并发短连接（HTTP 客户端足够）、团队没有 NIO 调试能力、连接数很少且延迟不敏感。

**展开（2 分钟版）**：
1. 相比裸 NIO，Netty 解决了：粘包拆包、`ByteBuffer` 指针管理、`Selector` 空轮询、半包读写、连接生命周期与优雅关闭、内存泄漏。
2. 常见的误用：在 `EventLoop` 里做阻塞 IO/DB 查询（应该丢到业务线程池）；Handler 标了 `@Sharable` 却持有状态；`ByteBuf` 忘记 release；`ChannelFuture` 用 `sync()` 在 IO 线程里阻塞。
3. 适合：RPC 框架、网关、MQ、IM、游戏长连接、自定义二进制协议。

## 易错点与踩坑

| 易错点 | 正确理解 |
| --- | --- |
| "Java NIO 是异步 IO" | NIO 是同步非阻塞，`read` 的数据拷贝阶段仍阻塞；只有 AIO/`AsynchronousSocketChannel` 是异步，且 Linux 上由线程池模拟 |
| "epoll 一定比 select 快" | 只在"连接多、活跃少"时优势明显；低延迟高频活跃场景两者差距小，epoll 还有 `epoll_ctl` 维护成本 |
| "ET 比 LT 高级所以必须用 ET" | ET 要求循环读到 `EAGAIN`、非阻塞 fd、`accept` 也要循环，一处偷懒就连接假死；JDK 与 Netty 默认都是 LT |
| "`clear()` 会清空数据" | 只重置 `position=0`、`limit=capacity`，旧数据仍在数组里 |
| "直接内存由 GC 回收所以不用管" | 堆外内存由 `Cleaner` 在堆内对象不可达后释放，存在延迟；`-XX:+DisableExplicitGC` 会切断 `Bits.reserveMemory` 的自救路径 |
| "`-XX:MaxDirectMemorySize` 默认是 64MB" | 默认 0，含义是等同于 `Runtime.maxMemory()`，即与 `-Xmx` 同量级 |
| "`transferTo` 一定把所有字节发完" | 返回值可能小于请求长度甚至为 0，必须循环并处理 0 |
| "`mmap` 对任何文件都更快" | 大文件映射引发缺页中断，且没有 `close()`，卸载依赖 `Cleaner`，长生命周期会累积映射 |
| "`SO_KEEPALIVE` 能替代心跳" | TCP keepalive 默认 2 小时才探测，必须用应用层心跳（`IdleStateHandler`） |
| "`OP_WRITE` 注册上更保险" | 可写恒为真会导致 `select` 立即返回、CPU 空转，应在写不出去时才注册 |
| "`selectedKeys` 遍历后不用 remove" | 不移除会重复处理同一个 key，且集合只增不减 |
| "`serialVersionUID` 不写也没关系" | 不写则由类结构算 SHA-1，加字段/改方法签名即不兼容，反序列化报 `InvalidClassException` |
| "Netty 的 `FileRegion` 可以配合 SSL 用" | 有 `SslHandler` 时数据必须进用户态加密，`FileRegion` 失效 |
| "`LinkedBlockingQueue` 无界更安全" | 无界队列把过载转成 OOM，应使用有界队列 + 拒绝策略 |
| "非阻塞 `read` 返回 0 表示连接关闭" | 0 表示暂无数据；`-1` 才是 EOF；native 层的 `EAGAIN` 与 Java 的 0 语义不同 |

## 一句话速记

- IO 两阶段：**等数据（内核缓冲区）** 与 **拷数据（内核到用户）**；谁阻塞这两阶段，决定了模型的名字。
- Java NIO = 多路复用 + 非阻塞，**同步非阻塞**；AIO 在 Linux 上是 epoll + 线程池模拟。
- select 病在"全量拷贝 + 线性扫描"；epoll 的药是**红黑树管注册 + 回调挂就绪链表**。
- LT 反复通知、容错好，是 JDK/Netty 默认；ET 只通知一次，必须**循环读到 EAGAIN**。
- `ByteBuffer`：`flip` 写转读、`clear` 全丢、`compact` 留未读；不变式 `mark <= position <= limit <= capacity`。
- 直接内存默认上限 = `Xmx`（`MaxDirectMemorySize=0`），由 `Cleaner` 释放，`-XX:+DisableExplicitGC` 会让它变成硬 OOM。
- 零拷贝三招：`sendfile` 省到极致但不可改数据、不可走 TLS；`mmap` 灵活但有缺页与卸载问题；`splice` 靠管道。
- Kafka 靠 `sendfile` + 顺序写 + page cache；RocketMQ 靠 `mmap` + 1GB CommitLog + 异步刷盘。
- 粘包拆包四解：定长、分隔符、长度字段（主流）、自定义状态机；五参数 `LengthFieldBasedFrameDecoder` 必须背。
- Netty 快的根因是**一个连接绑定一个 EventLoop、全程无锁**，加上池化内存与减少拷贝。
- 排查顺序：`ss -s` 看状态 → `/proc/<pid>/fd` 看 fd → `pidstat -w`/`vmstat` 看切换与 `sy` → `strace -c`/`perf` 看 syscall → JVM 侧 NMT 与泄漏检测。
- `CLOSE_WAIT` 多 = 应用没关连接（代码 bug）；`TIME_WAIT` 多 = 本端主动关闭（正常，2MSL 60 秒）。
- 扩容三件套：`ulimit -n`、`net.core.somaxconn`、`net.ipv4.tcp_max_syn_backlog`，再往上是 `SO_REUSEPORT` 与网卡多队列。
