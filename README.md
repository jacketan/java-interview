# Java 高级 / 架构师 面试复习知识库

> 32 章 · 48,036 行 · 365 张 Mermaid 原理图 · 433 道高频面试题 · 970 张对照表 · 覆盖 Java 核心、并发、JVM、框架、数据库、分布式与计算机基础

## 一、怎么用这份资料

| 入口 | 适用场景 |
| --- | --- |
| [`index.html`](index.html) | **推荐**。离线单页总览，双击用浏览器打开即可，无需联网、无需插件。 |
| 各章 `.md` 文件 | 用 VSCode / Typora / Obsidian 打开，可编辑、可做个人笔记（Mermaid 图在 VSCode 需装 Markdown Preview Mermaid Support 插件）。 |
| [`_STYLE.md`](_STYLE.md) | 本知识库的写作规范，便于你按同一风格继续补充章节。 |

`index.html` 已实现的功能：

- **左侧大纲导航**：按 7 大模块分组，标注每章面试权重（★）与原理图数量；移动端自动收起为抽屉。
- **全文检索**：顶部搜索框输入关键字，边输边过滤章节名；按回车则对全部 32 章正文做全文检索，命中处高亮并显示上下文片段。
- **Mermaid 图渲染**：365 张图按需渲染（切到哪章渲染哪章，避免卡顿）；**点击任意图可全屏放大**细看。
- **深色模式**：右上角切换，图形会按深色主题重新渲染。
- **打印 / 导出 PDF**：右上角按钮会先渲染完当前章的全部图再调起打印（每章单独打印，导出效果最好）。
- **代码高亮**：417 个 Java 代码块按 GitHub 主题着色（浅色/深色各一套）。
- **记住进度**：自动记录上次阅读的章节与主题，支持用 URL 锚点（`index.html#ch-03-jvm-02-...`）直接分享某一章。

> 快捷键：`/` 聚焦搜索框，`Esc` 清除搜索或关闭放大图。

## 二、目录与面试权重

权重为 ★ 的五档标注，★★★★★ 表示高级岗几乎必问。

### 01 Java 核心（[`01-java-core/`](01-java-core/)）

| 章节 | 核心内容 | 权重 |
| --- | --- | --- |
| [01 语言基础与对象模型](01-java-core/01-语言基础与对象模型.md) | 包装类缓存、String 与常量池、equals/hashCode 契约、深浅拷贝、分派与桥接方法、异常体系、类初始化顺序 | ★★★★☆ |
| [02 集合框架](01-java-core/02-集合框架.md) | HashMap 扩容与树化、ConcurrentHashMap 并发设计、fail-fast、LinkedHashMap 与 LRU、COW | ★★★★★ |
| [03 泛型与反射](01-java-core/03-泛型与反射.md) | 类型擦除、PECS、桥接方法、反射与 MethodHandle、JDK/CGLIB 动态代理 | ★★★★☆ |
| [04 IO 与 NIO](01-java-core/04-IO与NIO.md) | BIO/NIO/AIO、epoll 的 LT/ET、零拷贝、Netty Reactor 模型与粘包拆包 | ★★★★☆ |
| [05 Java 8+ 新特性](01-java-core/05-Java8新特性与函数式编程.md) | Stream 惰性求值、parallelStream 陷阱、CompletableFuture 编排、JDK 9~21 演进 | ★★★★☆ |

### 02 并发编程（[`02-concurrency/`](02-concurrency/)）

| 章节 | 核心内容 | 权重 |
| --- | --- | --- |
| [01 线程基础与 JMM](02-concurrency/01-线程基础与JMM.md) | 六状态机、happens-before 八条、volatile 内存屏障、DCL 为什么要 volatile | ★★★★★ |
| [02 synchronized 与锁升级](02-concurrency/02-synchronized与锁升级.md) | 对象头 Mark Word、偏向锁/轻量级/重量级升级、锁消除与粗化、ObjectMonitor | ★★★★★ |
| [03 AQS 与 ReentrantLock](02-concurrency/03-AQS与ReentrantLock.md) | AQS 源码流程、Condition 条件队列、读写锁 state 拆分、StampedLock | ★★★★★ |
| [04 线程池与并发工具类](02-concurrency/04-线程池与并发工具类.md) | 七大参数与执行流程、拒绝策略、ctl 位设计、参数估算与动态调参、ForkJoin | ★★★★★ |
| [05 并发容器与并发实战](02-concurrency/05-并发容器与并发实战.md) | ThreadLocal 内存泄漏、CountDownLatch/CyclicBarrier、CAS 与 ABA、死锁排查 | ★★★★★ |

### 03 JVM（[`03-jvm/`](03-jvm/)）

| 章节 | 核心内容 | 权重 |
| --- | --- | --- |
| [01 内存区域与对象创建](03-jvm/01-内存区域与对象创建.md) | 运行时数据区、栈帧、对象分配流程、TLAB、对象头与指针压缩、OOM 分区复现 | ★★★★★ |
| [02 垃圾回收与 GC 调优](03-jvm/02-垃圾回收与GC调优.md) | 三色标记、CMS/G1/ZGC 原理、GC 日志解读、参数速查与调优案例 | ★★★★★ |
| [03 类加载机制](03-jvm/03-类加载机制.md) | 类加载生命周期、双亲委派与打破、Class 文件结构、javap 与 invokedynamic | ★★★★☆ |
| [04 性能诊断与调优实战](03-jvm/04-性能诊断与调优实战.md) | CPU 100%/内存泄漏/频繁 Full GC 的完整排查链路、Arthas、火焰图、参数模板 | ★★★★★ |

### 04 框架（[`04-spring/`](04-spring/)）

| 章节 | 核心内容 | 权重 |
| --- | --- | --- |
| [01 Spring IoC 与 AOP 原理](04-spring/01-Spring-IoC与AOP原理.md) | refresh 十二步、Bean 生命周期扩展点、三级缓存、AOP 失效场景清单 | ★★★★★ |
| [02 Spring 事务与进阶](04-spring/02-Spring事务与循环依赖.md) | 传播行为 7 种、事务失效 8 因、TransactionSynchronization、事件机制 | ★★★★★ |
| [03 Spring Boot 原理](04-spring/03-SpringBoot原理.md) | 自动配置与条件装配、手写 starter、启动流程、优雅停机、2.x 与 3.x 差异 | ★★★★☆ |
| [04 MyBatis 原理](04-spring/04-MyBatis原理.md) | 四大对象、Mapper 动态代理、一/二级缓存、插件链与分页、#{} 与 ${} | ★★★★☆ |

### 05 数据库与缓存（[`05-database/`](05-database/)）

| 章节 | 核心内容 | 权重 |
| --- | --- | --- |
| [01 MySQL 索引与执行计划](05-database/01-MySQL索引与执行计划.md) | B+ 树与页结构、覆盖索引、索引失效十场景、explain 精读、在线 DDL | ★★★★★ |
| [02 MySQL 事务与锁](05-database/02-MySQL事务与锁.md) | MVCC 与 Read View、临键锁加锁规则、死锁排查、redo/binlog 两阶段提交 | ★★★★★ |
| [03 高可用与分库分表](05-database/03-MySQL高可用与分库分表.md) | 主从复制与延迟治理、分片键与全局 ID、跨库 join/分页、在线扩容 | ★★★★☆ |
| [04 Redis 数据结构与持久化](05-database/04-Redis数据结构与持久化.md) | 底层编码转换、单线程与多线程 IO、内存淘汰、RDB/AOF 与混合持久化 | ★★★★★ |
| [05 Redis 高可用与缓存问题](05-database/05-Redis高可用与缓存问题.md) | 哨兵与 Cluster、穿透/击穿/雪崩、缓存一致性方案、分布式锁 | ★★★★★ |
| [06 Redis 实战与分布式锁](05-database/06-Redis实战与分布式锁.md) | 限流、排行榜、秒杀扣库存完整方案、Redisson 看门狗与 RedLock 争议 | ★★★★☆ |

### 06 分布式与中间件（[`06-distributed/`](06-distributed/)）

| 章节 | 核心内容 | 权重 |
| --- | --- | --- |
| [01 分布式理论与一致性](06-distributed/01-分布式理论与一致性.md) | CAP/BASE 正解、Raft 选举与日志复制、一致性哈希、时钟与顺序 | ★★★★☆ |
| [02 注册中心与 RPC](06-distributed/02-注册中心与RPC.md) | 注册中心 CAP 取舍、一次 RPC 调用全链路、Dubbo SPI 与容错、服务治理 | ★★★★☆ |
| [03 消息队列](06-distributed/03-消息队列.md) | Kafka 与 RocketMQ 存储与副本机制、不丢不重有序、积压治理 | ★★★★★ |
| [04 限流熔断与网关](06-distributed/04-限流熔断与网关.md) | 五种限流算法、熔断状态机、Sentinel Slot 链、网关选型、雪崩复盘 | ★★★★☆ |
| [05 分布式事务与幂等](06-distributed/05-分布式事务与幂等.md) | Seata AT/TCC/Saga、可靠消息最终一致、幂等实现手段与决策树 | ★★★★★ |

### 07 计算机基础（[`07-cs-fundamentals/`](07-cs-fundamentals/)）

| 章节 | 核心内容 | 权重 |
| --- | --- | --- |
| [01 计算机网络](07-cs-fundamentals/01-计算机网络.md) | 三次握手四次挥手、TIME_WAIT 治理、拥塞控制、HTTP/2/3、HTTPS 握手 | ★★★★☆ |
| [02 操作系统](07-cs-fundamentals/02-操作系统.md) | 用户态内核态、调度与上下文切换、虚拟内存与页面置换、IO 模型、容器本质 | ★★★★☆ |
| [03 数据结构与算法](07-cs-fundamentals/03-数据结构与算法.md) | 复杂度与排序对比、树与图、DP 状态设计、高频题型模板与刷题路线 | ★★★★☆ |

## 三、四周冲刺计划

| 周次 | 目标 | 章节安排 | 每日投入 |
| --- | --- | --- | --- |
| 第 1 周 | 打牢 Java 底座 | 01 Java 核心（5 章）+ 02 并发（前 3 章） | 2.5h：1h 精读 + 1h 手写源码流程 + 0.5h 复述面试题 |
| 第 2 周 | 并发与 JVM | 02 并发（后 2 章）+ 03 JVM（4 章） | 2.5h：结合 `jstack`/`jmap`/Arthas 在本机跑一遍 |
| 第 3 周 | 框架与数据库 | 04 框架（4 章）+ 05 数据库（前 3 章） | 3h：SQL 在本地 MySQL 上复现 explain 与锁等待 |
| 第 4 周 | 缓存、分布式与基础 | 05 数据库（后 3 章）+ 06 分布式（5 章）+ 07 基础（3 章） | 3h：重点做场景设计题，按"背景→方案→权衡→兜底"口述 |

**复习技巧**：每章末尾的「高频面试题」用来做**闭卷复述**；「一句话速记」用来做**考前 30 分钟扫读**；每张 Mermaid 图都值得自己**默画一遍**——能画出来就说明机制真的懂了。

## 四、面试答题方法论

技术题按四步答，避免"背诵感"：

1. **结论先行**：一句话给出答案（"HashMap 线程不安全，根因是并发扩容与哈希冲突写入没有同步"）。
2. **机制展开**：讲清原理与源码位置（JDK 7 `HashMap#resize` 调用的 `transfer`、头插成环）。
3. **版本 / 边界**：说明版本差异与例外（JDK 8 改为尾插 + 红黑树，但仍有数据覆盖问题）。
4. **生产落地**：给出你实际怎么用、怎么排查、怎么规避（用 `ConcurrentHashMap`、或用 `Collections.synchronizedMap` 的代价）。

场景设计题按"背景 → 目标与约束 → 方案选型 → 一致性/幂等 → 容量与降级 → 监控与兜底"的顺序展开，主动说出**你放弃了什么**，这是高级岗与初级的最大区别。

## 五、说明

- 内容基线：JDK 8 / 11 / 17 / 21、Spring Framework 5.3.x 与 Spring Boot 2.x/3.x、MySQL 5.7 与 8.0、Redis 6/7、Kafka 3.x、RocketMQ 4.9+。
- 每章均标注了版本与关键默认值，遇到不确定的版本号时宁可不写——**面试中说错版本比不知道更减分**。
- 本知识库为个人复习资料，建议配合官方文档与真实源码阅读使用。
