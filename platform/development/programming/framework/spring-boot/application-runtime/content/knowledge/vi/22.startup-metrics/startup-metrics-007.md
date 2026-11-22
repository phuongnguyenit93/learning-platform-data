# Quan sát cấp phát bộ nhớ, nạp lớp và GC trong quá trình khởi động Spring Boot

## 1. Mục tiêu học tập và câu hỏi cần trả lời

Một ứng dụng Spring Boot có thể mất nhiều giây để khởi động vì hàng loạt công việc: JVM chuẩn bị runtime, nạp class, quét classpath, phân tích metadata annotation, tạo bean definitions, khởi tạo singleton, cấu hình auto-configuration, dựng proxy, mở kết nối, lập cache, chạy runner. Trong thời gian đó JVM có thể cấp phát nhiều object, nạp hàng nghìn lớp và thực hiện một số lần Garbage Collection (GC).

Cần phân biệt **ba nhóm số đo**:

- **Cấp phát bộ nhớ (allocation):** bao nhiêu object/byte mới được tạo theo thời gian, từ class và stack trace nào? Object có sống lâu hay nhanh chóng trở thành rác?
- **Nạp lớp (class loading):** bao nhiêu class đã được nạp vào JVM, tại thời điểm nào, qua class loader/nguồn nào? Nạp lớp khác khởi tạo class, khác tạo bean.
- **Garbage Collection:** có collection/stop-the-world pause nào trong khoảng startup không? Mất bao nhiêu thời gian và thu hồi bộ nhớ thế nào?

Chúng có thể tác động lẫn nhau nhưng không đồng nghĩa. Một snapshot heap nhỏ sau Ready có thể đi kèm lượng object tạm được cấp phát rất lớn. Hàng nghìn class được nạp không chứng minh có hàng nghìn bean. Có GC events không chứng minh GC là nguyên nhân chính làm startup chậm.

```text
JVM khởi động
     |
     +-- Load/verify/link classes -----+
     |                                 |
     +-- Spring scan/bind/create beans +--> Allocation --> Heap occupancy
     |                                 |                       |
     +-- Reflection/proxies ----------+                    GC khi cần
     |
     +-- Disk I/O / network / CPU / locks / JIT
                    |
               Startup wall time
```

Hãy xây dựng **giả thuyết có thể kiểm chứng**: “Bean X tạo nhiều mảng tạm khi khởi tạo”, “classpath kéo thư viện không cần thiết vào JVM”, hoặc “một GC pause lớn nằm trên critical path tới Ready”. Mỗi giả thuyết sẽ cần dữ liệu khác nhau.

Bài này sử dụng **Java 17+ và Spring Boot 3.3.x** với một project Gradle runnable và các công cụ JDK: MemoryMXBean, ClassLoadingMXBean, GarbageCollectorMXBean, Unified JVM Logging, Java Flight Recorder (JFR), jcmd và jstat.

## 2. Trước hết xác định ranh giới của chữ “khởi động”

Có nhiều khoảng thời gian khác nhau:

| Mốc đo | Bắt đầu | Kết thúc | Lưu ý |
|---|---|---|---|
| Process startup từ phía OS | Hệ điều hành bắt đầu tiến trình Java | Ứng dụng đạt mốc phục vụ | Bao gồm thời gian trước `main` |
| Java main → Spring Boot Ready | Đầu `main` | `SpringApplication.run(args)` trả về | Đã qua refresh, runners và Ready event nếu thành công |
| Spring Started | Quá trình bootstrap | `ApplicationStartedEvent` | Trước runners, khác Ready |
| Ready | Sau runners | `ApplicationReadyEvent`/readiness update | Background work có thể vẫn chạy |
| First-use latency | Lần gọi tính năng đầu | Kết quả chức năng | Có thể gồm lazy bean, cache và JIT warmup |

`System.nanoTime()` trong `main` chỉ đo từ thời điểm code Java đó chạy, không đo hết thời gian JVM dựng process trước main. `time java -jar app.jar` đo tới **process exit**, không đo riêng Ready nếu ứng dụng Web không tự thoát. Log Boot “Started ... in ... seconds” là một mốc khác với thời gian process sống hoặc request đầu tiên.

Trong phân tích sau, mốc chính của demo là **đầu phép đo trong main tới khi `SpringApplication.run(args)` trả về**. Hãy ghi rõ mốc này mỗi khi so sánh kết quả.

## 3. Đọc đúng các chỉ số bộ nhớ

### 3.1. Heap used, committed, max và allocated khác nhau

`MemoryMXBean.getHeapMemoryUsage()` trả `MemoryUsage` gồm:

- `used`: byte heap được dùng ở thời điểm lấy snapshot.
- `committed`: byte heap JVM đã cam kết sẵn cho sử dụng.
- `max`: giới hạn tối đa JVM công bố; có thể `-1` nếu không xác định.
- `init`: giá trị khởi tạo JVM công bố.

Các biến này **không phải** tổng byte Java object được cấp phát từ lúc process khởi động. Ví dụ lý thuyết:

```text
t0: heap used 24 MiB
t1: startup cấp phát tổng 250 MiB object, nhiều object ngắn hạn
t2: GC thu hồi phần lớn object tạm
t3: heap used 38 MiB
```

`38 - 24 = 14 MiB` là chênh lệch heap occupancy giữa hai snapshot, **không phải** tổng `250 MiB` đã cấp phát. Để tìm allocation hotspots cần JFR/profiler hoặc API đo allocated bytes phù hợp, không chỉ trừ hai số `getUsed()`.

### 3.2. Live set, churn và allocation rate

- **Live objects:** object còn reachable tại thời điểm đang xét.
- **Allocation rate:** lượng dữ liệu/object mới cấp phát trên một đơn vị thời gian.
- **Allocation churn:** nhiều object nhanh chóng hết vòng đời, có thể tạo áp lực GC.
- **Retained heap:** bộ nhớ còn được giữ bởi reference graph, không bằng tổng cấp phát.

Ví dụ, classpath scanning tạo nhiều cấu trúc metadata tạm, sau đó chỉ giữ một lượng nhỏ để vận hành. Heap cuối nhỏ nhưng các allocation ban đầu vẫn tốn CPU và có thể kích hoạt GC.

### 3.3. Heap không phải tổng bộ nhớ tiến trình

Một process HotSpot còn tiêu thụ:

```text
Java heap
Metaspace / class metadata
JIT code cache
Thread stacks
GC/compiler native structures
Direct/native buffers
Mapped libraries / other native allocations
```

**Metaspace** lưu metadata lớp chủ yếu ngoài Java heap. Khi có rất nhiều class loaded, chỉ xem `heap used` không đủ để biết tổng bộ nhớ tiến trình. **RSS** từ OS khác `heap committed`; RSS liên quan số trang resident. NMT có thể báo bộ nhớ JVM reserved/committed nhưng không phải phép đo RSS hoàn chỉnh và không bao trùm toàn bộ allocations native từ mọi thư viện ngoài JVM.

### 3.4. Các đơn vị thường dùng

`1 KiB = 1024 bytes`; `1 MiB = 1,048,576 bytes`. Đừng cộng các đại lượng “MB”, “MiB” hoặc số byte mà không thống nhất đơn vị. Ghi dữ liệu raw bằng bytes rồi chuyển đổi lúc báo cáo.

## 4. Hiểu nạp lớp trước khi nhìn class log

Một class thường liên quan các giai đoạn:

1. **Loading:** class loader tìm và định nghĩa class từ bytecode.
2. **Linking:** verification, preparation và resolution theo quy tắc JVM.
3. **Initialization:** chạy static initializer khi điều kiện active-use kích hoạt.
4. **JIT compilation:** JVM có thể tối ưu mã đã chạy; không phải cùng sự kiện class loading.
5. **Bean instantiation:** Spring gọi constructor/factory method để tạo object bean, một cơ chế cấp ứng dụng khác.

Một class được load có thể **không bao giờ trở thành Spring bean**. Bean definition có thể được đăng ký nhưng lazy bean chưa được tạo. Có thể có generated proxy classes khi dùng AOP; số class loaded còn gồm JDK, logging, serializers và auto-configurations.

`ClassLoadingMXBean` có ba phép đo quan trọng:

| API | Ý nghĩa |
|---|---|
| `getLoadedClassCount()` | Class đang loaded trong JVM tại mốc đo |
| `getTotalLoadedClassCount()` | Tổng số class từng được loaded kể từ JVM start, kể cả lớp sau đó unload |
| `getUnloadedClassCount()` | Tổng số class đã unload kể từ JVM start |

Các số này **ở cấp JVM**, không phải cấp `ApplicationContext`. Không dùng `getTotalLoadedClassCount()` như số bean được tạo. Một class có thể được load vì bytecode verification hoặc code path chỉ chạy lần đầu; không nên quy mọi class vào component scan.

## 5. Đọc GC theo đúng semantics

GC thu hồi object không còn cần thiết. Trong Java 17 HotSpot, G1 thường là collector mặc định trên cấu hình server-class thích hợp, nhưng thực tế collector phụ thuộc runtime, flags và môi trường. Hãy **kiểm tra JVM đang chạy collector nào**, không giả định.

### 5.1. Ba nhóm câu hỏi

1. **Sự kiện:** startup có GC nào không? Có young/full/concurrent activities nào?
2. **Thời gian:** tổng pause stop-the-world trên critical path là bao nhiêu? Pause lớn nhất xảy ra lúc nào?
3. **Bộ nhớ:** trước/sau collection, heap occupancy/capacity thay đổi ra sao?

Một số collector có pha đồng thời. Tổng `GarbageCollectorMXBean.getCollectionTime()` từ nhiều collector **không nhất thiết chính là tổng thời gian ứng dụng dừng vì GC**. Nếu cần pause đúng mốc, dùng GC unified logs hoặc JFR.

### 5.2. Không có GC vẫn có thể có rất nhiều allocation

Nếu startup hoàn tất trước khi JVM cần GC, `GC count delta` có thể bằng 0. Điều này không nói rằng 0 object được cấp phát. Khi đó, tìm chậm startup ở classpath scanning, bean initialization, I/O, parsing, JIT/CPU hoặc lock contention.

### 5.3. Số đo từ GarbageCollectorMXBean

`ManagementFactory.getGarbageCollectorMXBeans()` trả nhiều collector beans. `getCollectionCount()` và `getCollectionTime()` có thể trả `-1` khi số đo không được hỗ trợ. Nếu cộng các giá trị, phải bỏ qua `-1` và báo rõ rằng đó là số liệu **do JVM MXBeans hỗ trợ**, không phải định nghĩa chung về pause time.

## 6. Chọn công cụ theo câu hỏi

| Muốn biết | Công cụ | Điểm mạnh | Giới hạn |
|---|---|---|---|
| Heap used/committed/max | `MemoryMXBean` | Nhẹ, dễ tích hợp Java | Snapshot không phải tổng allocations |
| Loaded/unloaded classes | `ClassLoadingMXBean`/`jstat -class` | Thấy xu hướng theo JVM | Không chỉ ra stack của từng class |
| GC count/time | `GarbageCollectorMXBean` | Nhanh, không cần profiler | Collector-dependent semantics |
| GC pause ở uptime cụ thể | `-Xlog:gc*` | Có timestamp/heap/GC ID | Không đo mọi allocation |
| Class load theo thời gian | `-Xlog:class+load=info` | Thấy class name và nguồn | Log lớn, có overhead |
| Allocation stacks và timeline | JFR/JMC | Phân tích sampling, class/GC/CPU | Cần bật event và hiểu sampling |
| Heap/class snapshot của process | `jcmd` | Trực tiếp tại PID | Process phải còn sống/attach được |
| Sampling thống kê JVM | `jstat` | Poll định kỳ | Có thể bỏ qua spike ngắn |
| Native memory categories | NMT + `jcmd VM.native_memory` | Reserved/committed theo JVM | Bật từ đầu, không phải RSS |
| Bước khởi động Spring | `ApplicationStartup` | Biết Spring đang làm bước gì | Không thay JFR allocations/GC |

**Cách tiếp cận:** baseline trước; chỉ bật log/class/JFR/NMT khi có giả thuyết. Bật tất cả công cụ ở lần chạy đầu có thể làm thay đổi latency.

## 7. Project hoàn chỉnh Spring Boot 3.3.5 + Java 17

Ví dụ non-web không cần HTTP server hay database. Một bean tạo mảng để có lượng allocation có thể quan sát; main chụp JVM snapshots trước và sau `SpringApplication.run`. Có option `--probe.pause-seconds=30` để giữ JVM sống ngắn hạn cho `jcmd`/`jstat`.

### 7.1. Cấu trúc

```text
startup-memory-observer/
├── settings.gradle
├── build.gradle
└── src/main/java/com/example/startupmemory/
    ├── StartupMemoryObserverApplication.java
    └── StartupSampleCache.java
```

**`settings.gradle`:**

```groovy
rootProject.name = 'startup-memory-observer'
```

**`build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
}
```

Nếu muốn dùng `./gradlew` cần Gradle Wrapper đã tạo từ Spring Initializr hoặc từ Gradle tương thích. `build.gradle` không tự sinh ra Wrapper.

### 7.2. Bean cấp phát có kiểm soát

**`src/main/java/com/example/startupmemory/StartupSampleCache.java`:**

```java
package com.example.startupmemory;

import org.springframework.stereotype.Component;

@Component
public final class StartupSampleCache {

    private final byte[][] blocks = new byte[128][];

    public StartupSampleCache() {
        for (int i = 0; i < blocks.length; i++) {
            blocks[i] = new byte[16 * 1024];
        }
    }

    public long payloadBytes() {
        return (long) blocks.length * 16 * 1024;
    }
}
```

Bean giữ `128` byte arrays, mỗi array có payload `16 * 1024` byte. Tổng payload xác định:

```text
128 * 16 * 1024 = 2,097,152 bytes = 2 MiB
```

Đây là **payload byte[]**, không phải retained heap chính xác: còn object headers, array tham chiếu, alignment và mọi object khác của Spring/JVM. Các mảng được giữ trong field nên có thể quan sát trong lifetime của bean.

### 7.3. Snapshot trước/sau SpringApplication.run

**`src/main/java/com/example/startupmemory/StartupMemoryObserverApplication.java`:**

```java
package com.example.startupmemory;

import java.lang.management.ClassLoadingMXBean;
import java.lang.management.GarbageCollectorMXBean;
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryUsage;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class StartupMemoryObserverApplication {

    public static void main(String[] args)
            throws InterruptedException {

        Snapshot before = Snapshot.capture();
        long startedAt = System.nanoTime();

        SpringApplication app =
                new SpringApplication(StartupMemoryObserverApplication.class);

        app.setWebApplicationType(WebApplicationType.NONE);

        try (ConfigurableApplicationContext context = app.run(args)) {
            long elapsedNanos = System.nanoTime() - startedAt;
            Snapshot after = Snapshot.capture();

            before.print("BEFORE");
            after.print("AFTER");

            System.out.printf(
                    "RUN duration = %.1f ms%n",
                    elapsedNanos / 1_000_000.0);

            System.out.println(
                    "Class load delta = "
                    + (after.totalLoaded() - before.totalLoaded()));

            System.out.println(
                    "GC count delta = "
                    + (after.gcCount() - before.gcCount()));

            System.out.println(
                    "GC reported time delta = "
                    + (after.gcTimeMs() - before.gcTimeMs())
                    + " ms");

            int pauseSeconds = context.getEnvironment()
                    .getProperty(
                            "probe.pause-seconds", Integer.class, 0);

            if (pauseSeconds > 0) {
                pauseSeconds = Math.min(pauseSeconds, 60);
                System.out.println(
                        "PROBE: pause " + pauseSeconds + " seconds");
                Thread.sleep(pauseSeconds * 1000L);
            }
        }

        System.out.println("MAIN: context closed");
    }

    @Bean
    ApplicationRunner showCache(StartupSampleCache cache) {
        return args -> System.out.println(
                "CACHE payload bytes = " + cache.payloadBytes());
    }

    record Snapshot(
            long heapUsed,
            long heapCommitted,
            long heapMax,
            int currentlyLoaded,
            long totalLoaded,
            long unloaded,
            long gcCount,
            long gcTimeMs) {

        static Snapshot capture() {
            MemoryUsage heap = ManagementFactory
                    .getMemoryMXBean().getHeapMemoryUsage();

            ClassLoadingMXBean classes =
                    ManagementFactory.getClassLoadingMXBean();

            long count = 0;
            long time = 0;

            for (GarbageCollectorMXBean gc :
                    ManagementFactory.getGarbageCollectorMXBeans()) {
                long c = gc.getCollectionCount();
                if (c >= 0) {
                    count += c;
                }
                long t = gc.getCollectionTime();
                if (t >= 0) {
                    time += t;
                }
            }

            return new Snapshot(
                    heap.getUsed(),
                    heap.getCommitted(),
                    heap.getMax(),
                    classes.getLoadedClassCount(),
                    classes.getTotalLoadedClassCount(),
                    classes.getUnloadedClassCount(),
                    count,
                    time);
        }

        void print(String label) {
            System.out.printf(
                    "%s used=%d KiB committed=%d KiB max=%d KiB "
                    + "loadedNow=%d totalLoaded=%d unloaded=%d "
                    + "gcCount=%d gcTime=%d ms%n",
                    label,
                    heapUsed / 1024,
                    heapCommitted / 1024,
                    heapMax < 0 ? -1 : heapMax / 1024,
                    currentlyLoaded,
                    totalLoaded,
                    unloaded,
                    gcCount,
                    gcTimeMs);
        }
    }
}
```

**Giải thích:**

- `Snapshot.capture()` lấy dữ liệu từ các MXBeans của **JVM hiện tại**; không phải dữ liệu giả.
- `before` được chụp trước khi tạo `SpringApplication` nhưng **sau khi JVM đã bắt đầu chạy main**.
- `after` chụp ngay sau `app.run(args)` thành công, tức sau runners và Ready event.
- `Class load delta` lấy chênh lệch `getTotalLoadedClassCount`, không dùng chênh lệch currently loaded để suy ra mọi class từng được tải.
- `GC count/time` cộng thống kê từ collector MXBeans khi giá trị không âm. Nếu JVM không hỗ trợ một thống kê thì demo bỏ qua; trong thực tế nên in trạng thái “unavailable” hoặc kiểm chứng bằng GC log.
- `showCache` trong `ApplicationRunner` làm bean `StartupSampleCache` được yêu cầu trước khi `run` trả về. Nó in payload bytes đã được code định nghĩa.
- `WebApplicationType.NONE` giúp project không giữ HTTP server chạy; `try-with-resources` đóng context để chương trình tự kết thúc.
- `Thread.sleep` chỉ dành cho tùy chọn chụp snapshot ngoài, **không** nằm trong mốc đo `RUN duration`; thời gian pause tối đa 60 giây.
- `System.out.printf` có phần thời gian in log sau snapshot, không nên lấy log output làm profiler chính xác từng method.

### 7.4. Chạy

```bash
./gradlew bootJar
java -jar build/libs/startup-memory-observer-0.0.1-SNAPSHOT.jar
```

PowerShell:

```powershell
.\gradlew.bat bootJar
java -jar build/libs/startup-memory-observer-0.0.1-SNAPSHOT.jar
```

Những dòng do code in có dạng:

```text
CACHE payload bytes = 2097152
BEFORE used=... KiB committed=... KiB max=... KiB loadedNow=... totalLoaded=... unloaded=... gcCount=... gcTime=... ms
AFTER used=... KiB committed=... KiB max=... KiB loadedNow=... totalLoaded=... unloaded=... gcCount=... gcTime=... ms
RUN duration = ... ms
Class load delta = ...
GC count delta = ...
GC reported time delta = ... ms
MAIN: context closed
```

Các dấu ba chấm **chỉ là ký hiệu thay cho số phụ thuộc runtime**, không phải stdout xác định. Dòng duy nhất về số byte có thể dự đoán chính xác từ code là `CACHE payload bytes = 2097152`.

**Không dùng kết quả của một lần duy nhất** để suy rằng Java 17/Boot 3.3 luôn mất một số mili-giây cố định. JDK distribution, CPU, OS cache, disk, dependency JAR, JVM flags và trạng thái hệ thống đều có thể đổi.

## 8. GC unified logging: -Xlog:gc*

Cách ghi GC events từ trước `main`:

```bash
java '-Xlog:gc*:file=gc-startup.log:time,uptime,level,tags' -jar build/libs/startup-memory-observer-0.0.1-SNAPSHOT.jar
```

PowerShell dùng cùng một dòng:

```powershell
java '-Xlog:gc*:file=gc-startup.log:time,uptime,level,tags' -jar build/libs/startup-memory-observer-0.0.1-SNAPSHOT.jar
```

Một log GC minh họa theo định dạng HotSpot:

```text
[2026-11-09T08:01:12.111+0000][1.123s][info][gc] GC(0) Pause Young (Normal) (G1 Evacuation Pause) 40M->18M(128M) 9.123ms
```

Đây **không phải đo thực tế** của project. Trong ví dụ cấu trúc này:

- `1.123s` là JVM uptime, không phải tổng startup duration.
- `GC(0)` là ID sự kiện GC.
- `40M->18M(128M)` thể hiện heap usage trước/sau và capacity theo định dạng collector.
- `9.123ms` là pause được dòng log báo.

Hãy xác định event nằm **trong khoảng khởi động đang đo** rồi mới tính tỷ trọng pause so với thời gian. GC log có các dòng về collector, heap sizing và region phụ thuộc JVM. Không áp dụng cùng parser cho mọi JDK/GC mà không kiểm tra format.

### Nếu log không có collection nào

Đó có thể là kết quả bình thường của ứng dụng nhỏ với heap đủ lớn. **Không có collection không phải không có allocation.** Có thể dùng JFR để tìm allocation hotspots ngay cả khi GC chưa từng chạy trong đoạn khởi động.

### Tránh làm sai phép đo

Đừng thêm `System.gc()` vào startup để “kiểm tra GC”; lệnh này có thể tạo collection không đại diện cho ứng dụng thực. Không gọi `jcmd PID GC.run` trong baseline. Nếu cần so sánh GC tuning, phải giữ workload và JVM version giống nhau.

## 9. Class loading log: -Xlog:class+load

Ghi lớp được load:

```bash
java '-Xlog:class+load=info:file=class-load.log:time,uptime,level,tags' -jar build/libs/startup-memory-observer-0.0.1-SNAPSHOT.jar
```

Một dòng minh họa:

```text
[0.923s][info][class,load] com.example.startupmemory.StartupSampleCache source: file:/.../app.jar
```

Đường source có thể khác khi dùng Spring Boot executable JAR có nested JAR classpath. Không xem ví dụ trên là định dạng source tuyệt đối.

**Phương pháp đọc:** xem package nào load nhiều class, thời điểm xảy ra, và so với Spring startup steps/JFR CPU. Đừng chỉ đếm dòng mà bỏ qua thông tin thời gian. Log class ở mức info có thể **rất lớn**, gây I/O overhead và làm startup chậm hơn. Chạy ở diagnostic pass riêng.

**Loading khác initialization:** thấy class trong `-Xlog:class+load` không chứng minh static initializer đã chạy. Nếu cần nghiên cứu class init, dùng những log tags được hỗ trợ trên JVM đang chạy (`java -Xlog:help`) hoặc công cụ chuyên sâu phù hợp.

**Một lỗi tư duy:** nhiều lớp được load không nhất thiết kéo dài thời gian startup nhiều hơn. Class loading có thể trùng với I/O, CPU, JIT và khởi tạo bean. Chỉ có profiling/đối chứng mới cho phép đánh giá ảnh hưởng thực.

## 10. JFR: quan sát allocation hotspots, class load và GC trên cùng timeline

Java Flight Recorder có thể được bật **từ lúc JVM bắt đầu**, phù hợp startup quá nhanh để attach profiler sau đó:

```bash
java '-XX:StartFlightRecording=filename=boot-start.jfr,settings=profile,dumponexit=true' -jar build/libs/startup-memory-observer-0.0.1-SNAPSHOT.jar
```

- `settings=profile` dùng cấu hình chi tiết hơn `default` để điều tra ngắn; overhead có thể cao hơn.
- `filename` là nơi lưu recording.
- `dumponexit=true` ghi recording lúc JVM shutdown, hữu ích cho chương trình non-web.
- Events nào được bật phụ thuộc JDK và JFR settings, **không phải mọi sự kiện đều mặc định có mặt**.

### 10.1. Kiểm tra recording trước khi diễn giải

```bash
jfr summary boot-start.jfr
jfr print --events jdk.GarbageCollection boot-start.jfr
jfr print --events jdk.ClassLoad boot-start.jfr
jfr print --events jdk.ObjectAllocationSample boot-start.jfr
```

Nếu không thấy một loại event, xem `jfr summary` và settings. Đừng khẳng định không có GC/class load/allocations chỉ vì event type bị tắt hoặc sampling không thu được mẫu.

`jdk.ObjectAllocationSample` **không ghi mỗi object được cấp phát**. Nó là sampling; dùng JDK Mission Control (JMC) hoặc profiler để xem hotspots theo trọng số và allocation stacks. Không cộng `size` của các sample và gọi đó là tổng allocated bytes nếu chưa hiểu kỹ cơ chế sampling.

### 10.2. Điều gì đáng xem trong JMC?

- Top allocation classes: `byte[]`, `String`, collections, reflection metadata, proxy, cấu trúc binder, dữ liệu ứng dụng.
- Allocation stack traces: class/method nào tạo object và trong giai đoạn nào.
- Class loading events: thời điểm class cụ thể xuất hiện, có proxy/generated types không.
- GC pauses/heap summary: các pause lớn có nằm gần giai đoạn bean creation/Ready không.
- CPU/method sampling và threads: nếu GC nhẹ nhưng startup chậm, tìm classpath I/O, parsing, lock hoặc công việc CPU-heavy.

**Chỉ có tương quan thời gian chưa chứng minh quan hệ nhân quả.** Một đợt allocations trùng với startup step có thể do một thư viện khác chạy cùng lúc. Dùng stack traces và thí nghiệm thay đổi một yếu tố để xác nhận.

### 10.3. JFR bật sau Ready sẽ bỏ lỡ cold start

```bash
jcmd 12345 JFR.start name=late settings=profile
```

là cách tạo recording cho JVM đã chạy, nhưng không thể ghi lại các class loads/allocations **trước lúc bắt đầu recording**. Với startup bottleneck, chọn `-XX:StartFlightRecording` ở câu lệnh Java hoặc tích hợp recording trước phần muốn quan sát.

## 11. Live snapshots: jcmd, jstat, Native Memory Tracking

Ví dụ là ứng dụng non-web, nên cần giữ context sống để attach từ một terminal khác:

```bash
java -jar build/libs/startup-memory-observer-0.0.1-SNAPSHOT.jar --probe.pause-seconds=30
```

Sau khi thấy `PROBE: pause 30 seconds`, mở terminal khác:

```bash
jcmd -l
```

Xác định PID thật, ví dụ `12345`, rồi chạy:

```bash
jcmd 12345 GC.heap_info
jcmd 12345 VM.classloader_stats
jcmd 12345 VM.flags
jstat -gc 12345 1000 5
jstat -class 12345 1000 5
```

`jcmd GC.heap_info` mô tả heap lúc attach; `VM.classloader_stats` đưa số liệu các class loaders; `jstat` poll thống kê theo khoảng một giây. Đây **chủ yếu là snapshot/trend sau Ready** của demo; không thể khôi phục allocation sites từng giây đầu nếu chưa bật JFR/logs từ launch.

### 11.1. NMT: theo dõi native memory của HotSpot

Để `jcmd VM.native_memory` hoạt động, bật NMT **khi launch JVM**:

```bash
java -XX:NativeMemoryTracking=summary -jar build/libs/startup-memory-observer-0.0.1-SNAPSHOT.jar --probe.pause-seconds=30
```

Sau đó:

```bash
jcmd 12345 VM.native_memory summary
```

NMT có thể phân loại Java Heap, Class, Thread, Code, GC, Compiler và những vùng native khác. Phân biệt **reserved** (không gian địa chỉ dự trữ) và **committed** (đã commit). Không gọi tổng reserved là bộ nhớ vật lý thực sự dùng (RSS). NMT không theo dõi đầy đủ mọi cấp phát native của thư viện ngoài JVM và có overhead.

Nếu `VM.native_memory` báo tính năng chưa bật, **phải khởi động lại** với flag ở trên; không thêm flag vào một JVM đang chạy bằng cách đổi command line trong script rồi mong process tự cập nhật.

### 11.2. Quyền và môi trường

`jcmd` cần process còn sống, công cụ JDK có sẵn, PID đúng và quyền attach phù hợp. Trong container, PID namespace có thể khác host; trong image runtime nhỏ chỉ có JRE có thể không có `jcmd`/`jstat`. Không tự ý cài tooling vào production hoặc yêu cầu heap dump của người dùng khi chưa có quy trình bảo mật.

### 11.3. Heap histogram và heap dump là công cụ khác

`jcmd PID GC.class_histogram` hoặc `GC.heap_dump` có thể rất hữu ích cho phân tích giữ bộ nhớ, nhưng có overhead, có thể ảnh hưởng GC/pause và mang thông tin nhạy cảm. Không dùng làm bước mặc định cho benchmark startup khi chỉ cần GC log, JFR hoặc MXBean.

## 12. Ghép các mốc JVM với Spring ApplicationStartup

JVM biết class, object, GC; Spring biết các bước tạo context, nạp bean definitions, bind configuration và tạo beans. Spring Framework có abstraction `ApplicationStartup`; Spring Boot 3.3 hỗ trợ `BufferingApplicationStartup`:

```java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.context.metrics.buffering.BufferingApplicationStartup;

SpringApplication app = new SpringApplication(MyApplication.class);
app.setApplicationStartup(new BufferingApplicationStartup(2048));
app.run(args);
```

Đây là **snippet tích hợp**, cần class `MyApplication` trong project thật. `2048` là capacity startup steps buffer, **không phải kích thước heap bytes hay số object**.

Với Actuator startup endpoint được bật/expose và môi trường Web phù hợp, có thể xem startup steps ở `/actuator/startup`. Demo non-web không tự có HTTP endpoint; đừng mặc định cứ import Actuator là endpoint được công khai. Giới hạn quyền truy cập vì thông tin startup có thể tiết lộ cấu trúc nội bộ.

Spring Framework còn có `FlightRecorderApplicationStartup`:

```java
import org.springframework.core.metrics.jfr.FlightRecorderApplicationStartup;

app.setApplicationStartup(new FlightRecorderApplicationStartup());
```

Đây là snippet thay thế, không được thêm đè vô tình cùng lúc với BufferingApplicationStartup trên cùng object. Khi kết hợp với JFR recording, các startup steps có thể hiển thị trên timeline để đối chiếu GC/class/allocations.

**ApplicationStartup không thay thế JFR.** Nó không đo đầy đủ mọi Java allocation, không báo mọi GC pause và không đưa ra số class loaded. Nó cung cấp ngữ cảnh Spring-specific để hiểu khoảng JVM đang bận là pha nào.

## 13. Thiết kế một thí nghiệm đáng tin

1. **Chọn đúng mục tiêu:** thời gian process tới Ready, thời gian `run`, hay first request? Không trộn.
2. **Giữ JVM và classpath cố định:** cùng Java version, cùng Boot, starters, profiles, flags và dữ liệu.
3. **Tránh chi phí build:** build JAR trước, rồi đo `java -jar`; đừng tính lần Gradle download/dependency resolution.
4. **Lặp nhiều lần:** cold/warm system cache, CPU frequency, disk và tải máy có thể làm kết quả dao động.
5. **Ghi baseline không profiler:** vài lần chạy, lưu median và spread; không lựa chọn run nhanh nhất làm đại diện.
6. **Chỉ bật một công cụ ở mỗi pass:** GC log, class load log, JFR hoặc NMT có thể làm thay đổi startup.
7. **Đối chiếu JVM uptime với mốc Spring:** không trộn wall-clock timestamp và uptime mà thiếu phép chuyển.
8. **Thay đổi một yếu tố:** ví dụ loại một starter không dùng, giảm classpath scan, hoãn init cache, đổi heap budget.
9. **Đo lại đúng kịch bản:** cùng môi trường, đo cả startup và first-use nếu có lazy init.
10. **Đánh giá correctness:** một ứng dụng khởi động nhanh nhưng đẩy lỗi thiếu cấu hình tới request đầu có thể là regression vận hành.

Bảng mẫu báo cáo (số phải đo thật):

| Run | Java/flags | run() ms | Loaded classes delta | GC count | GC pause ms (log) | Heap used after MiB |
|---|---|---|---|---|---|---|
| 1 | Java17 baseline | ... | ... | ... | ... | ... |
| 2 | Java17 baseline | ... | ... | ... | ... | ... |
| 3 | Java17 + JFR | ... | ... | ... | ... | ... |

Không tính p95 từ 3 lần chạy rồi coi đó là latency phân phối đáng tin cậy. Với mẫu nhỏ, trình bày từng lần, median và khoảng biến thiên; muốn tail percentile cần mẫu đủ lớn.

## 14. Ba tình huống chẩn đoán

### Tình huống A: class load nhiều, GC ít

Giả sử đo được:

```text
run duration        = 3.5s
class load delta    = 4,200
gc count delta      = 0
heap used after     = 80 MiB
```

Đây là **số giả định minh họa**, không phải output project. Chưa thể kết luận class loading chiếm 3,5 giây; cần JFR CPU/method sampling, class log và thời gian Spring steps. Nhưng đã có cơ sở không coi GC là giả thuyết chính chỉ vì startup chậm.

### Tình huống B: GC pause rõ ràng gần Ready

Giả định `run` mất 2 giây, GC logs cho thấy hai pause 12 ms và 45 ms trong cùng khoảng. Nếu hai pause không bị đếm trùng, khoảng 57 ms là tỷ lệ nhỏ so với 2.000 ms wall time. Tối ưu GC lúc này có thể kém giá trị hơn xem bean initialization, I/O và classpath.

Ngược lại, nếu logs cho thấy nhiều pause lớn cùng heap quá nhỏ, hãy profile allocations rồi so sánh heap/GC settings trong một thí nghiệm có kiểm soát.

### Tình huống C: heap cuối nhỏ, allocation churn cao

Giả sử `heapUsed` tăng 20 MiB giữa hai snapshots, nhưng JFR cho thấy nhiều mẫu cấp phát `String`, `byte[]` và temporary collections trong khởi động. Điều này có thể phản ánh object churn; không được suy `allocated=20 MiB` từ snapshot. Xem stack trong JFR để xác nhận nguồn tạo rác, tránh tối ưu nhầm vào object live lâu dài.

## 15. Lỗi thường gặp và cách sửa

| Cách hiểu hoặc thao tác sai | Vì sao sai | Hướng sửa |
|---|---|---|
| `heapAfter - heapBefore` là total allocation | Object tạm đã bị GC | JFR allocations/allocated bytes |
| `Runtime.totalMemory()` là used heap | Nó gần heap committed | `MemoryUsage.getUsed()` |
| GC delta = 0 nghĩa là không có object mới | GC có thể chưa cần chạy | Dùng JFR khi cần allocation |
| Có GC nên GC chắc chắn gây chậm | Pause có thể nhỏ | So pause time với wall time |
| Loaded class = số Spring beans | Class loading là ở JVM | Kết hợp Spring StartupStep/bean diagnostics |
| Class loaded = static initializer đã chạy | Loading khác initialization | Quan sát init riêng khi cần |
| `-Xmx` là trần toàn bộ memory process | Metaspace/thread/native còn lại | OS RSS + NMT + heap |
| NMT reserved là RSS | Reserved khác committed/resident | Đọc NMT đúng semantics |
| `jcmd` sau Ready tái tạo cold-start timeline | Snapshot chỉ là thời điểm attach | Bật JFR/-Xlog từ launch |
| JFR allocation sample là toàn bộ object | Sampling không log mọi allocation | Dùng JMC/weighted analysis |
| Bật profiler nặng rồi so với baseline nhẹ | Overhead khác nhau | Tách diagnostic passes |
| Gọi `System.gc()` trước phép đo | Tạo hành vi không đại diện | Đo collector tự nhiên |
| `GC.class_histogram` vô hại | Có thể gây pause/overhead | Chạy diagnostic riêng |
| Chạy `./gradlew bootRun` lần đầu để đo JVM startup | Gradle có build/download | Build trước, đo JAR |
| Một lần chạy nhanh chứng minh tối ưu | OS cache/JIT/tải máy dao động | Nhiều lần, cùng cấu hình |
| NMT không có output nên jcmd hỏng | Có thể NMT chưa bật khi launch | Launch với NMT flag |
| Class log lớn nên bật production vĩnh viễn | Disk/CPU overhead và lộ metadata | Bật ngắn hạn, kiểm soát log |
| Giảm startup bằng lazy mà bỏ qua first request | Chi phí chỉ bị dời muộn | Đo Ready và first-use |

## 16. Bảo mật và chi phí chẩn đoán

JFR files, class loading logs, heap dumps và diagnostic snapshots có thể chứa package names, classpaths, code stacks, JVM arguments, user/application data hoặc thông tin nhạy cảm. Không xuất heap dump công khai. Dùng thư mục quyền truy cập hạn chế, giữ dữ liệu đúng thời gian cần thiết và xóa theo chính sách.

Các option `-Xlog:class+load` và JFR profile có runtime overhead; `GC.heap_dump` có thể gây pause lớn. Đừng bật log class load toàn hệ thống ở mức cực chi tiết trên production chỉ để đo số lớp. Với Actuator startup/threaddump, dùng authentication và mạng quản trị; không mở endpoint ra Internet.

Nếu muốn đo RSS/GC trong container, quan sát cả **cgroup memory/CPU limits** và số liệu process thật. Chỉ số host RAM rảnh không phản ánh ngân sách của pod/container.

## 17. Bài thực hành có thể tự kiểm chứng

**Bài 1 — snapshot cơ bản.** Chạy JAR ba lần, ghi `RUN duration`, `heap used/committed`, `class load delta`, `gc count delta`. Vì sao số liệu khác nhau?

**Bài 2 — tăng payload.** Đổi `blocks` từ 128 lên 256, build lại. `CACHE payload bytes` tăng bao nhiêu? Heap used có tăng đúng số byte đó không? Giải thích overhead và GC.

**Bài 3 — GC logs.** Bật `-Xlog:gc*`. Có GC pause nào giữa mốc JVM startup và Ready không? Nếu không, vì sao vẫn có thể có allocations?

**Bài 4 — class logs.** Bật `-Xlog:class+load=info`, tìm `StartupSampleCache` và class của Spring. So thời điểm load với uptime. Vì sao class logs không chứng minh constructor đã chạy?

**Bài 5 — JFR.** Bật recording từ JVM launch. Dùng `jfr summary`, kiểm tra loại event đã thu, xem `ObjectAllocationSample`/`ClassLoad`/`GarbageCollection` khi có. Giải thích sampling.

**Bài 6 — attach jcmd.** Chạy `--probe.pause-seconds=30` rồi `jcmd -l`, `GC.heap_info`, `VM.classloader_stats`. Vì sao các snapshot này không thay JFR startup timeline?

**Bài 7 — NMT.** Chạy với `-XX:NativeMemoryTracking=summary`, attach `VM.native_memory summary`. Phân biệt reserved/committed với RSS.

**Bài 8 — jstat.** Chạy `jstat -gc` và `jstat -class` trong thời gian pause. Quan sát những số nào ổn định sau Ready; làm thế nào bắt được spike khi startup quá nhanh?

**Bài 9 — Spring StartupStep.** Bật `BufferingApplicationStartup` hoặc `FlightRecorderApplicationStartup`, đối chiếu với JFR. Nêu vì sao tương quan không tự là quan hệ nhân quả.

**Bài 10 — heap budget.** Trong máy thử nghiệm có RAM đủ, so `-Xms64m -Xmx256m` với `-Xms128m -Xmx512m`. Cấu hình lớn hơn có luôn nhanh hơn không? Không thay cùng lúc GC collector và classpath.

**Bài 11 — lazy initialization.** Thử `--spring.main.lazy-initialization=true` trên bản project riêng; so before/after. Có chi phí nào chuyển sang lần truy cập bean đầu tiên?

**Bài 12 — ca thực tế.** Chọn một ứng dụng Spring Boot có startup chậm. Viết giả thuyết, mốc đo, GC/class/JFR evidence, một thay đổi tối thiểu và kết quả đo đối chứng.

### Câu hỏi tự đánh giá

1. Vì sao heap used không thể đại diện tổng allocated bytes?
2. `getTotalLoadedClassCount` khác `getLoadedClassCount` thế nào?
3. Nạp class khác class initialization và bean instantiation thế nào?
4. Metaspace nằm ở đâu trong mô hình bộ nhớ HotSpot?
5. Vì sao GC count có thể bằng 0 dù startup tạo hàng nghìn objects?
6. Khi nào dùng `-Xlog:gc*` thay vì chỉ `GarbageCollectorMXBean`?
7. JFR `ObjectAllocationSample` có ghi mọi allocation không?
8. Vì sao cần bật JFR trước main cho cold-start profiling?
9. NMT reserved và OS RSS có bằng nhau không?
10. Vì sao `jcmd` sau Ready không cho allocation stacks của giây startup trước đó?
11. Vì sao `BufferingApplicationStartup` không thay thế JFR?
12. Cần ghi lại những cấu hình nào để so sánh hai lần startup một cách tin cậy?

## 18. Checklist và kết luận

- [ ] Xác định mốc main/Started/Ready/first-use.
- [ ] Ghi Java/Boot version, JDK vendor, profiles, JVM flags, CPU/RAM/container limits.
- [ ] Build trước, đo JAR thay vì tính chi phí Gradle.
- [ ] Chạy baseline nhiều lần, ghi rõ run conditions.
- [ ] Thu heap snapshots và class/GC counters như thông tin tổng quan.
- [ ] Dùng GC logs cho pause/heap timeline.
- [ ] Dùng class load logs để thấy lớp và nguồn nạp.
- [ ] Dùng JFR cho sampled allocations, GC/class timeline và CPU hotspots.
- [ ] Dùng jcmd/jstat khi JVM còn sống, không suy ngược quá khứ từ snapshot.
- [ ] Bật NMT từ launch trước khi yêu cầu native memory summary.
- [ ] Liên hệ JVM timeline với ApplicationStartup steps.
- [ ] Phân biệt heap occupancy, total allocations, Metaspace và OS RSS.
- [ ] Không dùng GC.run/heap dump trong baseline.
- [ ] Đo lại startup và first-use sau một thay đổi, kiểm tra correctness.
- [ ] Bảo vệ logs/JFR/dump và không để profiler chạy quá phạm vi cần thiết.

**Kết luận:** Để hiểu khởi động Spring Boot, hãy đo **allocation** bằng JFR/profiler, **class loading** bằng ClassLoadingMXBean và class load logs, **GC** bằng GC logs/JFR, rồi đối chiếu với **Spring ApplicationStartup** để xác định giai đoạn. Heap used thấp không chứng minh cấp phát ít; nhiều class loaded không đồng nghĩa nhiều bean; một vài GC events không chứng minh GC làm startup chậm. Chỉ những phép đo cùng ranh giới, cùng môi trường và có đối chứng mới hỗ trợ quyết định tối ưu đáng tin cậy.

### Tài liệu chính thức

- Spring Boot 3.3 — Startup Tracking: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Boot 3.3 — Actuator startup endpoint: https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html
- Spring Framework 6.1 — ApplicationStartup: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/core/metrics/ApplicationStartup.html
- Spring Framework 6.1 — FlightRecorderApplicationStartup: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/core/metrics/jfr/FlightRecorderApplicationStartup.html
- Oracle Java 17 — java command / Unified Logging / JFR flags: https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html
- Oracle Java 17 — jcmd: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html
- Oracle Java 17 — jstat: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jstat.html
- Oracle Java 17 — jfr command: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jfr.html
- Oracle Java 17 — MemoryMXBean: https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/MemoryMXBean.html
- Oracle Java 17 — ClassLoadingMXBean: https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ClassLoadingMXBean.html
- Oracle Java 17 — GarbageCollectorMXBean: https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/GarbageCollectorMXBean.html