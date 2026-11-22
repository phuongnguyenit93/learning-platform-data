# Đọc thread dump, thống kê GC và quan sát event loop để xác minh giả thuyết

## 1. Mục tiêu: chẩn đoán hiệu năng Spring Boot bằng chứng cứ

Một Spring Boot API có p99 từ 200 ms tăng lên 3 giây. CPU của container lúc cao lúc thấp; heap trông như răng cưa; nhiều threads xuất hiện trong dump. Không thể từ một biểu đồ rồi khẳng định “GC gây lỗi”, “Tomcat thiếu threads” hoặc “Netty event loop bị block”. Bài học này tập trung vào **cách đọc bằng chứng để kiểm chứng hoặc bác bỏ một giả thuyết**, không chỉ cách gõ lệnh JVM.

Phạm vi: Spring Boot **3.3.x**, Spring Framework 6.1.x, Java 17+; ví dụ ứng dụng dùng Java 21 và Spring Boot 3.3.13. Công cụ `jcmd`, `jstat`, `jfr` và `-Xlog` nhắm **OpenJDK/HotSpot**; cú pháp, tác động và kết quả có thể khác với JVM vendor/version khác. Spring MVC thường chạy trên Servlet/Tomcat; WebFlux trong ví dụ dùng Reactor Netty.

Một quy trình tốt có 6 bước:

1. Xác định **symptom, khoảng thời gian và request route**.
2. Viết giả thuyết cụ thể cùng dấu hiệu dự đoán trước khi thu dữ liệu.
3. Thu **nhiều thread dumps** và metrics cùng khoảng thời gian.
4. Kiểm tra **GC count, GC pause, heap và CPU** trước khi gán lỗi cho JVM memory.
5. Nếu dùng WebFlux, xem **event loop và scheduler**; nếu dùng MVC, xem **Tomcat worker/queue/pool**.
6. Thay một biến trong staging/canary, đo trước/sau và cập nhật kết luận.

Không tự tăng `-Xmx`, Tomcat threads hay Netty workers chỉ vì thấy timeout. Pool starvation, slow SQL, lock contention, CPU throttling và GC pause có thể có biểu hiện giống nhau nhưng phương án xử lý rất khác.

## 2. Sơ đồ các tầng nơi request có thể bị chậm

```text
Browser / upstream caller
        |
        v
CDN / ingress / gateway / load balancer
        |
        v
Spring Boot HTTP runtime
        |
        +-- Spring MVC + Tomcat worker threads
        |      |
        |      +-- Service -> JDBC pool -> database
        |      +-- Service -> HTTP client pool -> downstream
        |
        +-- WebFlux + Reactor Netty event loops
               |
               +-- Non-blocking I/O
               +-- Reactive scheduler / boundedElastic
               +-- Connection pools / remote services
        |
        v
JVM heap, GC, safepoints, CPU and OS scheduling
        |
        v
HTTP response
```

Một request có thể mất 3 giây **trước khi đi vào controller** do gateway queue hoặc connector backlog. Ngược lại, controller có thể bắt đầu ngay nhưng đứng chờ DB pool. Nếu đo `http.server.requests` thấy 500 ms còn browser thấy 3 giây, phải kiểm tra khoảng thời gian ngoài HTTP observation boundary thay vì chỉ xem thread dump trong controller.

Đồng bộ timestamps, timezone, deployment revision, CPU quota, lưu lượng request, p50/p95/p99 và error rate. Một thread dump từ thời điểm service đã hồi phục thường không giải thích incident trước đó.

## 3. Tạo giả thuyết có thể bị bác bỏ

| Giả thuyết | Dự đoán khi đúng | Bằng chứng cần thêm |
| --- | --- | --- |
| GC pause làm tăng p99 | Pause duration/frequency tăng trùng incident | GC log, JFR, `jvm.gc.pause`, thời điểm HTTP latency |
| Tomcat worker threads cạn | Busy gần max, requests/queue chờ | `tomcat.threads.busy`, thread dumps, connector metrics |
| Lock contention | Nhiều threads `BLOCKED`, cùng monitor/lock owner | `Thread.print -l`, JFR monitor events |
| DB connection pool cạn | Hikari active=max, pending tăng, workers đợi borrow | Hikari metrics, SQL/transaction latency |
| Reactor Netty event loop bị blocking | Nhiều stacks `reactor-http-nio` trong blocking call, pending tasks tăng | Dumps, event-loop metrics, JFR |
| CPU-bound algorithm | Thread CPU delta cao, JFR execution samples tập trung | `top -H`, `pidstat`, JFR |
| Container CPU throttling | Service p99 tăng khi cgroup throttled time tăng | cgroup/Kubernetes CPU metrics |
| Downstream chậm | HTTP client/DB span kéo dài; threads chờ I/O | Distributed trace và downstream telemetry |

**Đừng viết giả thuyết quá chung** như “Java performance không tốt”. Ví dụ có thể kiểm chứng: “Trong 14:00–14:10, ít nhất 80% Tomcat request workers bị giữ tại `HikariPool.getConnection`; Hikari pending tăng; vì vậy p99 tăng do chờ lease DB connection”. Giả thuyết ấy có các số liệu để so sánh và có thể bị bác bỏ.

## 4. Thu baseline và xác định đúng PID Java

Trước tiên biết chính xác service, JVM và workload:

```bash
java -version
jcmd -l
jps -l
```

Trong Linux/container, PID trong namespace container có thể khác PID host. Một image tối giản có thể không có JDK diagnostic tools. Chỉ chạy attach commands khi được phép; `jcmd` thường yêu cầu cùng máy, quyền user/group phù hợp, và attach mechanism chưa bị vô hiệu.

Các lệnh sau dùng **PID giả định đã xác minh**:

```bash
PID=12345
jcmd "$PID" VM.version
jcmd "$PID" VM.uptime
jcmd "$PID" VM.command_line
jcmd "$PID" help
```

`jcmd -l` không phải công cụ inventory hoàn chỉnh cho mọi JVM ở namespace khác. Trong Kubernetes có thể cần debug image/ephemeral container đúng PID namespace và quyền, hoặc dùng metrics/JFR được bật từ trước. Không tự chạy `jcmd 0` để gửi lệnh cho mọi JVM.

Ghi JDK version/collector, heap flags, CPU quota, instance/pod, uptime và release version trước khi phân tích; thay collector hoặc image có thể làm metrics và thread naming khác.

## 5. Thread dump là ảnh chụp, không phải profiler theo thời gian

Với HotSpot JDK 17/21:

```bash
jcmd "$PID" help Thread.print
jcmd "$PID" Thread.print -l > dump-01.txt
sleep 3
jcmd "$PID" Thread.print -l > dump-02.txt
sleep 3
jcmd "$PID" Thread.print -l > dump-03.txt
```

`-l` bổ sung thông tin `java.util.concurrent` locks. Lấy 2–3 snapshots ở thời điểm incident để tìm **mẫu lặp**. Số lần và khoảng cách tùy tình hình, không chụp quá dày trên JVM nhiều threads. `Thread.print` có chi phí phụ thuộc số threads và quy mô dữ liệu. `jstack -l PID` cũng được dùng nếu công cụ có sẵn, nhưng không cần gọi cả hai mà không có lý do.

Chú ý file thread dump có thể chứa thread names, class names, hostnames, query/operation descriptors và metadata nội bộ. Bảo vệ file và quyền truy cập; tránh gửi raw file lên ticket công khai.

Spring Boot Actuator có `/actuator/threaddump`, hỗ trợ response JSON khi endpoint được bật và expose. Nó không mặc nhiên được expose qua web. Endpoint này không thay thế hoàn toàn dump HotSpot có lock/virtual-thread details; cần chọn công cụ theo mục tiêu.

## 6. Đọc thread name, trạng thái, stack và lock

Một excerpt minh họa:

```text
"http-nio-8080-exec-7" #77 daemon
   java.lang.Thread.State: BLOCKED (on object monitor)
        at com.example.service.InventoryService.reserve(...)
        - waiting to lock <0x000000000abc1234>
        at com.example.web.InventoryController.reserve(...)
```

Quy trình đọc:

1. Xác định thread **thuộc vai trò nào**: `http-nio-*` thường Tomcat; `reactor-http-nio-*` thường Netty; `boundedElastic-*` thuộc Reactor scheduler. Đây là quy ước tên thường gặp, không phải API contract.
2. Ghi **state** và stack top. Đọc các frames bên dưới để biết method nào gọi blocking operation.
3. Tìm `- waiting to lock`, `- locked` và lock owner; xác định resource đang được giữ.
4. Tìm cùng stack trong 3 dumps; nếu cùng chờ qua nhiều giây và requests đang timeout, nghi bottleneck.
5. Đối chiếu metric của chính resource (Hikari pool, HTTP connection manager, Tomcat pool, OS CPU).
6. Đừng diễn giải một `RUNNABLE` riêng lẻ thành hot CPU thread.

Thread dump **chỉ là một lát thời gian**. Một request có thể mất 2 giây ở DB, nhưng đúng lúc dump thread đã quay lại xử lý JSON, khiến snapshot cho thấy stack vô hại. JFR/trace spans và nhiều snapshots giảm rủi ro đọc nhầm.

## 7. Ý nghĩa các trạng thái thread thường gặp

| State | Ý nghĩa khái quát | Điều không nên suy |
| --- | --- | --- |
| `RUNNABLE` | Đang thực thi hoặc sẵn sàng/nằm trong native execution | Chắc chắn đang ăn CPU |
| `BLOCKED` | Chờ vào Java intrinsic monitor, thường `synchronized` | Mọi dạng đợi I/O/pool đều có state này |
| `WAITING` | Đợi không có deadline trên `wait`, `park`, `join`, v.v. | Chắc chắn deadlock |
| `TIMED_WAITING` | Sleep/timed wait/timed park | Bản thân state là lỗi hiệu năng |
| `NEW`, `TERMINATED` | Chưa start, đã kết thúc | Có bottleneck runtime |

Ví dụ nhiều idle executor threads có thể ở `WAITING` trong `LinkedBlockingQueue.take`. Đó là bình thường nếu queue rỗng và requests hoàn thành nhanh. Với `ReentrantLock`/`Semaphore`/pool queues, thread thường `WAITING` trong `LockSupport.park`, không phải `BLOCKED`.

Một thread `RUNNABLE` trong native socket read/epoll cũng không đồng nghĩa đang đốt CPU. Phải dùng **thread CPU delta**, JFR samples hoặc OS profiler.

## 8. Đọc lock contention, deadlock và lỗi chờ pool

Khi thấy nhiều threads BLOCKED trên cùng monitor, tìm thread **giữ monitor**:

```text
Worker A:
  java.lang.Thread.State: BLOCKED
  - waiting to lock <0xABC>

Worker B:
  java.lang.Thread.State: TIMED_WAITING
  at java.lang.Thread.sleep(...)
  - locked <0xABC>
```

Worker B có thể đang sleep nhưng **vẫn giữ synchronized monitor**. Đó là lock contention, chưa chắc deadlock. Deadlock thực sự cần vòng phụ thuộc, ví dụ A giữ lock 1 chờ lock 2 và B giữ lock 2 chờ lock 1. HotSpot có thể phát hiện một số Java-level deadlocks trong thread dump, nhưng không phát hiện đầy đủ **distributed locks, DB transactions hoặc native deadlocks**.

Một mẫu chờ database connection thường có các frames như:

```text
at jdk.internal.misc.Unsafe.park(...)
at java.util.concurrent.locks.LockSupport.park(...)
at com.zaxxer.hikari.pool.HikariPool.getConnection(...)
at com.example.repository.OrderRepository.load(...)
```

Đây là stack minh họa; frames thực thay đổi theo JDK/Hikari/driver. Nhiều workers ở `HikariPool.getConnection` + pool pending tăng, active=max là bằng chứng **pool acquire bottleneck**, không phải chứng minh database lock. Tiếp tục xem SQL duration, transaction length, connection leak và pool cap.

## 9. Chương trình Java 17 độc lập để tạo BLOCKED có kiểm soát

Ví dụ tạo hai threads: một thread giữ intrinsic monitor và đợi một latch, thread còn lại cố vào monitor. Chạy trong terminal rồi dùng `jcmd` chụp ngay khi chương trình in cửa sổ quan sát.

**`ThreadDumpLab.java`:**

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

public class ThreadDumpLab {
    private static final Object LOCK = new Object();
    private static final CountDownLatch HELD = new CountDownLatch(1);
    private static final CountDownLatch RELEASE = new CountDownLatch(1);
    private static final CountDownLatch ATTEMPTED = new CountDownLatch(1);

    public static void main(String[] args) throws Exception {
        Thread holder = new Thread(() -> {
            synchronized (LOCK) {
                HELD.countDown();
                try {
                    RELEASE.await();
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            }
        }, "lab-monitor-holder");

        Thread waiter = new Thread(() -> {
            ATTEMPTED.countDown();
            synchronized (LOCK) {
                // Chỉ vào được sau khi holder thả monitor.
            }
        }, "lab-monitor-waiter");

        holder.start();
        HELD.await();
        waiter.start();
        ATTEMPTED.await();

        long deadline = System.nanoTime()
                + TimeUnit.SECONDS.toNanos(3);

        while (waiter.getState() != Thread.State.BLOCKED) {
            if (System.nanoTime() > deadline) {
                RELEASE.countDown();
                throw new IllegalStateException("No BLOCKED thread");
            }
            Thread.sleep(10);
        }

        try {
            System.out.println("holder=" + holder.getState());
            System.out.println("waiter=" + waiter.getState());
            System.out.println("capture-window=5s");
            Thread.sleep(5000);
        } finally {
            RELEASE.countDown();
            holder.join();
            waiter.join();
        }
        System.out.println("done");
    }
}
```

Lệnh:

```bash
javac ThreadDumpLab.java
java ThreadDumpLab
```

**Stdout khi chạy đúng như thiết kế:**

```text
holder=WAITING
waiter=BLOCKED
capture-window=5s
done
```

Dùng terminal thứ hai trong cửa sổ 5 giây:

```bash
jcmd -l
jcmd <PID> Thread.print -l
```

Thay `<PID>` bằng PID thực. Khi đọc dump, thread `lab-monitor-holder` ở `CountDownLatch.await` có thể là `WAITING` nhưng vẫn giữ monitor `LOCK`; thread `lab-monitor-waiter` ở `BLOCKED` chờ chính monitor đó. Với máy chậm, tăng thời gian cửa sổ trong source rồi chạy lại. Không dùng ví dụ này để gây contention trên production.

## 10. Chẩn đoán thread chạy CPU cao

`RUNNABLE` không có nghĩa đang thật sự tiêu thụ CPU. Trên Linux có thể quan sát OS TIDs:

```bash
top -H -p "$PID"
pidstat -t -p "$PID" 1 5
```

`pidstat` chỉ chạy nếu có sysstat package. HotSpot traditional dump có thể hiển thị `nid=0x...` theo hex; OS tool thường có TID dạng decimal. Có thể đổi decimal sang hex để đối chiếu:

```bash
printf '0x%x\n' 1234
```

**Không nhầm Java `threadId`/`Thread.getId()` với OS TID**. Với virtual threads còn không có ánh xạ 1:1 sang kernel threads. JFR execution samples hay profiler là nguồn bằng chứng tốt hơn cho hot Java methods.

Trường hợp mạnh:

```text
top -H: OS thread TID 1234 dùng CPU cao qua nhiều giây
Thread.print: nid=0x4d2, stack tại ReportService.sortHugeList
JFR: jdk.ExecutionSample nổi bật cùng call path
```

Đó là bộ bằng chứng hỗ trợ giả thuyết CPU-bound. Nếu thread ở `EPoll.wait` và CPU delta gần 0, không kết luận nó “đang chạy liên tục” dù dump ghi RUNNABLE.

## 11. Spring MVC/Tomcat: saturation cần so với worker cap

Với Servlet Spring MVC, Tomcat thường dùng worker threads `http-nio-8080-exec-*`. Blocking operations như JDBC, synchronous `RestClient`, `Thread.sleep`, lock contention hoặc file I/O có thể giữ worker trong suốt thời gian chờ. Nếu nhiều concurrent requests bị giữ, busy threads tiến gần cap và requests mới phải đợi ở tầng connector/gateway.

Spring Boot 3.3 có các properties:

```properties
server.tomcat.threads.max=200
server.tomcat.accept-count=100
```

`threads.max` và accept count **không phải cùng tài nguyên**: accept count không tạo thêm request workers. Đừng dùng 200/100 làm giá trị mặc định cho mọi workload; chúng là giá trị minh họa. Khi dùng async Servlet, SSE hoặc virtual threads, mapping giữa request lifetime và thread occupancy khác request đồng bộ.

Để kiểm chứng Tomcat saturation: xem `tomcat.threads.busy`, `tomcat.threads.current`, request p99/5xx, queue/connection statistics và 2–3 thread dumps; xác định threads đang bận **do CPU**, **chờ pool**, **chờ I/O** hay **giữ lock** trước khi thay cap.

## 12. Demo Spring Boot MVC có thể chạy để quan sát worker

Project dùng Java 21, Spring Boot 3.3.13, Gradle Wrapper. Chỉ chạy ở localhost/staging vì endpoint cố tình ngủ để tạo request chậm.

**`build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories { mavenCentral() }

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') { useJUnitPlatform() }
```

**`src/main/java/com/example/mvcdiag/MvcDiagApplication.java`:**

```java
package com.example.mvcdiag;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MvcDiagApplication {
    public static void main(String[] args) {
        SpringApplication.run(MvcDiagApplication.class, args);
    }
}
```

**`src/main/java/com/example/mvcdiag/SlowController.java`:**

```java
package com.example.mvcdiag;

import java.util.concurrent.TimeUnit;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
public class SlowController {

    @GetMapping("/demo/sleep")
    public String slow(
            @RequestParam(defaultValue = "2000") long delayMs)
            throws InterruptedException {

        if (delayMs < 0 || delayMs > 5000) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "Invalid delayMs");
        }
        TimeUnit.MILLISECONDS.sleep(delayMs);
        return "slept";
    }

    @GetMapping("/demo/quick")
    public String quick() {
        return "quick";
    }
}
```

Đây là **một ví dụ có chủ đích tạo blocking**, không phải kiến trúc xử lý request production. Trong môi trường thật, thread bị giữ có thể do slow SQL hoặc downstream, chứ không phải `Thread.sleep`.

## 13. Bật JVM/Tomcat metrics ở localhost

**`src/main/resources/application.properties`:**

```properties
server.address=127.0.0.1
server.port=8080

server.tomcat.mbeanregistry.enabled=true
server.tomcat.threads.max=20

management.endpoints.web.exposure.include=health,metrics,threaddump
server.error.include-stacktrace=never
```

Theo Spring Boot 3.3, Tomcat metrics do auto-configuration cung cấp khi MBean registry của Tomcat được bật (`server.tomcat.mbeanregistry.enabled=true`). `jvm.*` metrics của Micrometer nói chung được auto-configured cùng Actuator. Cần kiểm tra tên metric có trong runtime thay vì tự suy đoán mọi meter luôn tồn tại.

Chạy:

```bash
./gradlew bootRun
curl -i http://127.0.0.1:8080/demo/quick
curl -i "http://127.0.0.1:8080/demo/sleep?delayMs=3000"
```

Body thành công là `quick` hoặc `slept`; thời gian HTTP response thực tế phụ thuộc scheduling/GC.

Trong lúc `/demo/sleep` chạy, terminal khác:

```bash
curl -s http://127.0.0.1:8080/actuator/metrics
curl -s http://127.0.0.1:8080/actuator/metrics/jvm.threads.live
curl -s http://127.0.0.1:8080/actuator/metrics/tomcat.threads.busy
curl -s http://127.0.0.1:8080/actuator/threaddump > dump.json
```

`dump.json` là snapshot của JVM qua Spring Actuator. Nếu tăng đồng thời một số requests chậm trên **localhost có kiểm soát**, busy threads có thể tăng; các stack thường xuất hiện trong `TimeUnit.sleep`. Nhưng **một thread sleeping trong demo không chứng minh sản xuất thiếu worker**, cần thêm pool/throughput/queue context.

Không expose Actuator threaddump công khai. `server.address=127.0.0.1` chỉ bảo vệ demo trên máy đơn, không thay role-based access, network policy và TLS production.

## 14. GC statistics: phân biệt allocation, pause và retention

Garbage collection thu hồi objects không còn reachable; heap tăng rồi giảm sau GC thường là **điều bình thường**. Một performance incident có thể liên quan:

- **Allocation rate cao:** tạo objects nhanh, gây young collections thường xuyên.
- **Pause dài hoặc thường xuyên:** làm dừng các application threads trong một khoảng thời gian.
- **Concurrent GC overhead:** tiêu tốn CPU trong khi application vẫn chạy.
- **Heap gần giới hạn:** làm tăng pressure, old collections và nguy cơ OutOfMemoryError.
- **Object retention/leak:** live set sau GC tăng bền vững ở workload tương đương.
- **Native/direct memory:** RSS tăng trong khi Java heap ít thay đổi.

Đừng đánh đồng G1, Parallel GC và ZGC. Collector có semantics/pause phases khác nhau. Một concurrent phase kéo dài hàng giây không nhất thiết tạo **stop-the-world pause** tương ứng hàng giây. Ngược lại, pause vài chục ms trùng request có thể đóng góp một phần latency nhưng không đủ giải thích 4 giây.

## 15. Dùng `jstat -gcutil` để xem xu hướng, không chỉ một dòng

Ví dụ 10 samples cách nhau 1.000 ms:

```bash
jstat -gcutil "$PID" 1000 10
```

Các cột thường gặp (phụ thuộc collector/JDK):

| Cột | Diễn giải thực dụng |
| --- | --- |
| `E` | Eden utilization |
| `O` | Old generation usage |
| `YGC`/`YGCT` | Young GC count và cumulative time |
| `FGC`/`FGCT` | Full GC count và cumulative time |
| `CGC`/`CGCT` | Concurrent GC count/time khi có |
| `GCT` | Tổng thời gian GC mà tool ghi nhận |

`jstat` được Oracle đánh dấu experimental/unsupported và output có thể thay đổi giữa JVM releases. Không hardcode parser với thứ tự cột từ một ví dụ cũ.

Đọc **delta**, không đọc tổng thời gian tích lũy như thời gian một request. Nếu `GCT` từ 6,40 lên 6,55 trong 10 giây, chênh lệch là 0,15 giây thống kê GC trong cửa sổ ấy; cần so với HTTP latency và GC pause logs, không tự kết luận ngay.

Cùng lúc xem `jvm.memory.used`, `jvm.gc.pause`, `jvm.threads.live`, `process.cpu.usage` và container memory RSS. `jvm.gc.pause` có thể là Timer; tìm COUNT/TOTAL_TIME/MAX hoặc phân bố trên monitoring backend theo version. Không chỉ nhìn một average.

## 16. GC unified logging trên Java 17/21

JVM HotSpot hỗ trợ unified logging từ JDK 9, ví dụ khi khởi động trong test/staging:

```bash
java \
  '-Xlog:gc*,safepoint:file=gc-%p.log:time,uptime,level,tags:filecount=5,filesize=20M' \
  -jar app.jar
```

`app.jar` là tên minh họa, thay bằng đường dẫn `bootJar` thật. `-Xlog:gc*` ghi GC events với nhiều chi tiết hơn `-Xlog:gc`; `safepoint` hữu ích khi JVM pause vì các nguyên nhân ngoài GC. Logging có chi phí và file rotation cần đủ disk.

Một dòng GC mang tính minh họa:

```text
[2026-11-08T09:00:00+0700][info][gc] GC(21) Pause Young (...) 140M->88M(256M) 18.7ms
```

Tên collector, heap sizes, thời gian và format **không có stdout cố định**. Đối chiếu **timestamp của pause** với trace/HTTP latency. Không nói request 4 giây bị GC gây ra khi chỉ có một pause 18,7 ms không đủ giải thích phần lớn độ trễ.

Nếu app đã chạy và quyền cho phép:

```bash
jcmd "$PID" help VM.log
jcmd "$PID" VM.log list
jcmd "$PID" GC.heap_info
```

`VM.log` hỗ trợ cấu hình logging runtime trên HotSpot nhưng phải kiểm tra syntax/overhead trước khi bật mức chi tiết mới. `GC.heap_info` giúp quan sát heap cấu trúc, không phát hiện leak bằng một snapshot. Đừng dùng `GC.heap_dump` hoặc `GC.class_histogram` trên production mà không xét tác động và dữ liệu nhạy cảm.

## 17. Ba hình dạng dữ liệu GC hay bị hiểu sai

**Mẫu A: heap răng cưa bình thường**

```text
Used heap: 120M -> 190M -> GC -> 125M -> 195M -> GC -> 126M
Pause: thấp, HTTP p99 ổn định
```

Không có cơ sở gọi là memory leak chỉ vì heap tăng trước mỗi GC.

**Mẫu B: allocation pressure**

```text
Young GC count tăng nhanh, allocation rate cao
GC total pause và CPU GC tăng
HTTP p99 tăng cùng cửa sổ
```

Nghi code tạo quá nhiều objects, parsing/serialization, cache churn hoặc heap sizing không phù hợp. Dùng JFR allocation sample/profiler, giảm allocations thử trong staging và so GC before/after.

**Mẫu C: retention nghi leak**

```text
Post-GC live set: 180M -> 240M -> 300M -> 370M
Traffic mix tương đương, nhiều chu kỳ GC
```

Nghi một số objects bị giữ lại: caches không giới hạn, listeners/SSE/WebSocket sessions chưa dọn, thread locals hoặc queues. Chưa đủ kết luận leak: cache warmup, batch processing, workload khác cũng làm live set tăng. Heap dump/retention graph có thể cần sau khi có phê duyệt.

**Bổ sung:** heap không tăng mà RSS tăng có thể do Netty direct buffers, native allocations, thread stacks, JIT code cache hay memory mapped files. `-Xmx` không giới hạn toàn bộ process memory.

## 18. Java Flight Recorder bổ sung khía cạnh thời gian

Thread dump là snapshot; **JFR** thu events trong một khoảng thời gian: CPU execution samples, monitor contention, thread park, allocations, GC, network I/O và các JVM events khác theo cấu hình.

Ví dụ trên JDK 21:

```bash
jcmd "$PID" JFR.check
jcmd "$PID" JFR.start \
  name=incident \
  settings=profile \
  duration=60s \
  filename=/tmp/incident.jfr
```

`settings=profile` thu nhiều dữ liệu hơn `default` và có thể tăng overhead; chỉ dùng khoảng ngắn và theo chính sách vận hành. Nếu command syntax khác trong JVM cụ thể, dùng `jcmd "$PID" help JFR.start`.

Sau khi recording hoàn tất:

```bash
jfr summary /tmp/incident.jfr
jfr print --events jdk.ExecutionSample,jdk.JavaMonitorEnter,jdk.GarbageCollection \
  /tmp/incident.jfr
```

Dùng JDK Mission Control để nhìn timeline/hot methods/locks/GC. Không có một event trong file **không chứng minh** hiện tượng không tồn tại: event có thể chưa bật, threshold/sampling bỏ qua hoặc incident nằm ngoài cửa sổ recording. JFR có thể chứa thông tin nhạy cảm trong thread names, custom events và data paths; bảo vệ file.

## 19. JFR và OS CPU giúp hiểu RUNNABLE đúng nghĩa

**CPU-bound** được ủng hộ khi:

```text
Thread dump nhiều lần: cùng thread RUNNABLE trong ReportService.sort
top -H: cùng OS TID có CPU delta cao
JFR execution samples: hot method là ReportService.sort
GC: không có pause đủ lớn giải thích p99
```

**I/O wait** được ủng hộ khi:

```text
Thread dump: nhiều workers chờ socket read/JDBC pool
CPU per-thread thấp
JFR: thread park/socket events hoặc downstream spans chậm
GC: bình thường trong incident window
```

Ví dụ này là **ma trận bằng chứng**, không phải output thật của tool. Một thread RUNNABLE ở native selector vẫn có thể chờ network; khi không có CPU samples đừng gọi là CPU-bound.

Nếu OS threads nóng nhưng JFR chỉ cho thấy GC work hoặc VM internal threads, cần tính cả GC/compiler/system overhead thay vì vội tối ưu controller business code.

## 20. WebFlux/Reactor Netty: vì sao event loop nhạy với blocking code?

WebFlux trên Reactor Netty dùng **event-loop threads** để xử lý non-blocking I/O cho nhiều connections, không một Java worker cố định cho mỗi request như Servlet model thông thường.

```text
Connections A, B, C
       |
       v
Reactor Netty EventLoop #1
       |
       +-- read/write callbacks
       +-- reactive operators
       +-- schedule work
       |
       +-- Nếu chạy blocking JDBC/Thread.sleep ở đây:
             event loop bị giữ, callbacks khác phải đợi
```

Các thread names thường thấy: `reactor-http-nio-1`, `reactor-http-epoll-2`, nhưng tên phụ thuộc transport/resources config. Event loop thường ở `NioEventLoop.select`/`EPoll.wait` khi rảnh; một state RUNNABLE ở đây không phải mặc định “lỗi”.

Một dấu hiệu đáng nghi là lặp lại stack:

```text
"reactor-http-nio-2"
    at java.lang.Thread.sleep(...)
    at com.example.LegacyClient.fetch(...)
    at reactor.core.publisher.MonoCallable.call(...)
```

Nếu đồng thời `reactor.netty.eventloop.pending.tasks` tăng và quick requests cũng chậm, **event-loop starvation** là giả thuyết cần kiểm chứng. Ngược lại, event loop thấy `select/epoll` trong ba dumps và task backlog thấp làm giả thuyết blocking yếu hơn.

## 21. Ví dụ WebFlux riêng: unsafe blocking và offloaded work

Đây là **project độc lập** với Spring MVC demo. Dùng chỉ `spring-boot-starter-webflux` (không thêm starter-web vào runtime) để dùng Reactor Netty HTTP server.

**`build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain { languageVersion = JavaLanguageVersion.of(21) }
}

repositories { mavenCentral() }

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') { useJUnitPlatform() }
```

**`src/main/java/com/example/reactivediag/ReactiveDiagApplication.java`:**

```java
package com.example.reactivediag;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveDiagApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveDiagApplication.class, args);
    }
}
```

**`src/main/java/com/example/reactivediag/BlockingProbeController.java`:**

```java
package com.example.reactivediag;

import java.util.concurrent.TimeUnit;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@RestController
public class BlockingProbeController {
    private String legacyBlockingCall() {
        try {
            TimeUnit.MILLISECONDS.sleep(800);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Interrupted", e);
        }
        return "done";
    }

    // Cố ý sai: work blocking có thể chạy trên Netty event loop.
    @GetMapping("/demo/unsafe")
    public Mono<String> unsafe() {
        return Mono.fromSupplier(this::legacyBlockingCall);
    }

    // Đúng hướng khi buộc phải gọi một blocking SDK.
    @GetMapping("/demo/offloaded")
    public Mono<String> offloaded() {
        return Mono.fromCallable(this::legacyBlockingCall)
                .subscribeOn(Schedulers.boundedElastic());
    }

    @GetMapping("/demo/quick")
    public Mono<String> quick() {
        return Mono.just("quick");
    }
}
```

`Mono.fromSupplier` trì hoãn thực thi nhưng **không tự đổi thread**; trong server reactive, một blocking supplier có thể chiếm Netty event loop. `subscribeOn(Schedulers.boundedElastic())` chuyển nguồn blocking sang scheduler phù hợp hơn và có capacity hữu hạn. Nó **không biến SDK/JDBC thành non-blocking**; vẫn cần giới hạn concurrent requests và kiểm tra pool downstream.

## 22. Đo event loop interference trong local test

**`src/main/resources/application.properties`:**

```properties
server.address=127.0.0.1
server.port=8080
management.endpoints.web.exposure.include=health,metrics
```

Chạy:

```bash
./gradlew bootRun
curl -i http://127.0.0.1:8080/demo/unsafe
curl -i http://127.0.0.1:8080/demo/offloaded
curl -i http://127.0.0.1:8080/demo/quick
```

Body của `/demo/unsafe` và `/demo/offloaded` dự kiến là `done`; body `/demo/quick` là `quick`. Không có thời gian HTTP response byte-exact.

Để kiểm chứng starvation phải có **requests chồng nhau** với concurrency nhỏ trên localhost: gửi một vài `/demo/unsafe` trong lúc đo latency của `/demo/quick`, sau đó làm tương tự với `/demo/offloaded`. Hai request chạy tuần tự không chứng minh được interference. Thu thread dump cùng window và nếu metric có mặt thì `reactor.netty.eventloop.pending.tasks`.

Kết quả dự đoán: khi unsafe blocking callbacks chiếm cùng event loop, quick requests có thể chậm theo. Khi offload đúng, event loop có cơ hội xử lý I/O trong lúc blocking tasks ở boundedElastic. Số liệu tùy CPU/scheduler/transport, không mong một ngưỡng latency cố định.

Không dùng các endpoints này để benchmark production hoặc gửi traffic lớn vào môi trường dùng chung.

## 23. Metrics Reactor Netty: phải xác nhận đã bật instrumentation

Các metrics từ tài liệu Reactor Netty gồm nhóm tham khảo:

```text
reactor.netty.http.server.connections.active
reactor.netty.http.server.connections.total
reactor.netty.http.server.response.time
reactor.netty.http.server.errors
reactor.netty.eventloop.pending.tasks
```

Tùy Reactor Netty 1.1.x version và metrics integration, **không phải mọi metric tự hiện khi thêm Actuator**. Có thể cần bật Reactor Netty metrics/LoopResources integration, Micrometer registry và recorder tương ứng. Hãy kiểm tra runtime metric names thay vì coi endpoint 404 là bằng chứng không có event loops.

Với Spring Boot Actuator:

```bash
curl -s http://127.0.0.1:8080/actuator/metrics
```

Chỉ sau khi thấy tên có mặt, gọi `/actuator/metrics/<metric-name>`. Các metrics bổ sung nên đối chiếu: HTTP p99, process CPU, cgroup throttling, GC pauses, Netty direct buffer usage và outbound client pending acquire.

**Pending tasks tăng không tự chứng minh blocking code.** Một burst I/O lớn, event storm, scheduler overhead hoặc CPU throttling cũng có thể tạo queue. Cần thread dump/JFR cùng thời điểm để biết callbacks có bị giữ bởi operation blocking không.

## 24. `boundedElastic`, `subscribeOn` và scheduler saturation

`boundedElastic` là một lựa chọn cho blocking work legacy:

```java
Mono<Book> result = Mono.fromCallable(
        () -> blockingBookRepository.findById(id))
        .subscribeOn(Schedulers.boundedElastic());
```

Đây là **mẫu tích hợp**, các kiểu/biến `Book`, `blockingBookRepository`, `id` do ứng dụng thật định nghĩa. Nếu bạn gọi repository **trước khi tạo Mono**, rồi mới `.subscribeOn(...)`, blocking đã xảy ra trên thread cũ — offload quá muộn.

`boundedElastic` có giới hạn threads và task queue. Nếu toàn bộ WebFlux traffic dồn vào một blocking database, scheduler có thể đầy, request p99 tiếp tục tăng và DB pool cạn. Đúng hướng là giới hạn concurrency, timeouts/retry budget, bulkhead, tối ưu query hoặc chuyển sang I/O non-blocking khi phù hợp.

Đừng nhầm `publishOn` với `subscribeOn`; `publishOn` chỉ đổi execution context cho downstream operators theo vị trí đặt, không hồi tố di chuyển các blocking steps phía trước. Xác minh bằng actual thread names/stacks, không giả định từ một dòng code.

## 25. Vì sao tăng Netty event-loop threads có thể không giải quyết vấn đề

Một số cấu hình dùng system property `reactor.netty.ioWorkerCount`. Reactor Netty thường chọn worker count theo CPUs runtime với ngưỡng tối thiểu phụ thuộc version. Tăng workers từ 4 lên 32 có thể **che tạm** một blocking call, nhưng vẫn có blocking operations trên từng event loop và thêm overhead/context switches.

Trước khi thay đổi workers:

1. Kiểm tra threads thực sự bị giữ tại blocking method không.
2. Chuyển sang non-blocking client hoặc offload source blocking.
3. Xem CPU quota/throttling; thêm workers trên CPU quá ít không giúp gì.
4. Xem event-loop pending tasks, response time, active connections và GC.
5. Load test cùng request mix trước/sau, xác nhận throughput, p99, CPU, error rate.

Không tự tạo `LoopResources` mới cho mỗi request; resource này có vòng đời phải được quản lý. Server và client có thể chia sẻ Reactor Netty event-loop resources trong JVM theo cấu hình mặc định.

## 26. Java 21 virtual threads và cách chụp dump phù hợp

Spring Boot 3.3 hỗ trợ Java 21 virtual threads khi bật:

```properties
spring.threads.virtual.enabled=true
```

Một số auto-configured `AsyncTaskExecutor`/scheduler của Boot chuyển sang virtual threads. Tuy nhiên nếu có custom executors hoặc stack khác, không suy rằng mọi request nhất thiết chạy trên virtual thread.

Truyền thống:

```bash
jcmd "$PID" Thread.print -l
```

không cung cấp bức tranh đầy đủ của mọi virtual threads. Trên Java 21 HotSpot, dùng thêm:

```bash
jcmd "$PID" Thread.dump_to_file -format=text /tmp/threads.txt
jcmd "$PID" Thread.dump_to_file -format=json /tmp/threads.json
```

Virtual-thread dump có thể rất lớn và **không chứa tất cả lock/heap details của traditional dump** trong JDK 21. Bảo vệ file, chỉ thu có mục đích và xem syntax trong JDK runtime nếu command không có. Với JDK 17, không giả định virtual-thread commands tồn tại.

JFR event `jdk.VirtualThreadPinned` giúp điều tra virtual thread pinning; Java 21 có các tình huống blocking khi giữ monitor (`synchronized`) có thể pin carrier thread. Cần xem JFR evidence, không quy mọi virtual thread slow call cho pinning. Dùng virtual threads không tự chữa slow SQL hoặc connection pool starvation.

## 27. CPU throttling trong Kubernetes có thể giả giống event-loop starvation

CPU quota nhỏ có thể làm:

- Event loop task backlog tăng mặc dù không có `Thread.sleep`.
- Tomcat workers tiến triển chậm, p99 tăng.
- Concurrent GC tranh CPU với ứng dụng.
- CPU host dường như còn rảnh, nhưng cgroup bị throttled.

Điểm cần xem: container CPU usage **theo quota**, CFS throttled periods/time, `Runtime.availableProcessors()`, request throughput và concurrency. Một biểu đồ process CPU 40% có thể dùng **denominator khác** container limit, nên không đủ để kết luận còn 60% capacity.

Nếu event-loop pending tasks cao nhưng dumps chủ yếu có selector/epoll, hãy xem throttling và event volume. Nếu GC pauses thấp, threads không bị block, nhưng request queue tăng đúng các đợt CPU throttling, giả thuyết quota mạnh hơn “JVM heap thiếu RAM”.

## 28. Pool và downstream bottleneck: điểm chờ không nằm ở HTTP worker

Một request MVC có thể đi qua:

```text
Tomcat worker
  -> Service
  -> Hikari connection lease
  -> SQL execution / DB transaction
  -> Outbound HTTP connection acquire
  -> Downstream response
```

Các pool quan trọng:

| Thành phần | Bằng chứng |
| --- | --- |
| HikariCP | `hikaricp.connections.active`, `idle`, `pending`, `max` |
| Apache HttpClient 5 | Leased/available/pending per route |
| Reactor Netty HTTP client | Pending-acquire, active/idle connections |
| Tomcat | Busy/max worker count, accept backlog |
| App executors | Active/queue/rejections |
| Database | Slow queries, lock waits, transaction times |

Một thread stack trong `HikariPool.getConnection` không nói được **vì sao connections hết**. Có thể do pool nhỏ, slow SQL, long transactions, giữ connection khi gọi HTTP bên ngoài, hoặc connection leak. Đặt hypothesis riêng và so tracing/DB metrics.

Với reactive code, synchronous JDBC chạy trong boundedElastic vẫn có thể gây Hikari pending tăng; offload chỉ chuyển blocking từ event loop sang pool khác. Đừng coi việc “Netty thread không còn bị block” là ứng dụng đã xử lý xong performance bottleneck.

## 29. Xây timeline latency trước khi kết luận

Một request p99 3,0 giây có thể phân bổ giả định:

```text
Ingress / gateway waiting      0.5s
App dispatch                   0.1s
DB connection acquisition      0.7s
SQL execution                  1.2s
Serialization                  0.2s
Network response               0.3s
------------------------------------
Total                          3.0s
```

Đây là dữ liệu minh họa, không được coi là phép đo thật. **Một thread dump chụp khi DB connection acquisition đang xảy ra không chứng minh toàn bộ 3 giây do Hikari**. Cần trace spans/metrics thể hiện time budgets cho từng operation.

Correlation yêu cầu đồng bộ thời gian giữa JVM/containers/proxy/DB, so HTTP request ID/trace ID đã được xử lý bảo mật và version deployment. GC stop-the-world có thể làm nhiều traces kéo dài cùng lúc; JFR/GC timestamp giúp phân biệt khỏi một downstream spike.

Với server-side observations, khoảng thời gian đo có thể khác browser end-to-end time, đặc biệt với async Servlet, WebFlux và streaming. Đừng so các metrics có boundary khác nhau mà không ghi rõ.

## 30. Cách xác nhận giả thuyết bằng thay đổi một biến

| Giả thuyết | Thử nghiệm staging/canary | Chỉ số cần cải thiện |
| --- | --- | --- |
| Event loop bị blocking | Thay blocking call bằng non-blocking/offload | Pending tasks và quick route p99 giảm |
| Tomcat worker saturation | Giảm blocking duration, giới hạn concurrency | Busy/queue giảm, throughput cải thiện |
| GC allocation pressure | Giảm allocations theo JFR hotspot | GC pauses/allocation rate giảm |
| Hikari pool starvation | Sửa leak/SQL duration hoặc điều chỉnh pool sau load test | Pending giảm, DB không quá tải |
| Monitor contention | Thu hẹp critical section | BLOCKED samples/lock wait giảm |
| CPU throttling | Tăng quota hợp lý hoặc giảm CPU work | Throttled time/p99 giảm |
| Downstream chậm | Tối ưu query/HTTP dependency | Downstream span p99 và overall p99 giảm |

Giữ nguyên request mix, concurrency, deployment, JVM warmup và load-generator capacity; đo đủ nhiều lần để tránh nhiễu. Nếu thay đổi không tác động **chỉ số dự đoán**, hãy bác bỏ hoặc sửa giả thuyết. Một biểu đồ đẹp lên không chứng minh quan hệ nhân quả khi load đã giảm cùng thời điểm.

## 31. Ma trận chẩn đoán nhanh

| Thread dump | GC/JFR | OS/pool/event-loop | Khả năng ưu tiên |
| --- | --- | --- | --- |
| Workers chờ `HikariPool.getConnection` liên tục | GC bình thường | Hikari pending tăng, active=max | Pool acquisition contention |
| Nhiều threads `BLOCKED` cùng lock | JFR monitor wait tăng | CPU có thể thấp | Lock contention |
| Cùng thread RUNNABLE trong algorithm | JFR execution samples nóng | Thread CPU cao | CPU-bound |
| Netty event loop nằm trong `Thread.sleep`/JDBC | GC bình thường | Pending tasks tăng | Event-loop blocking |
| Nhiều requests chậm cùng lúc | GC pause lớn đúng timestamp | JVM-wide latency | GC/safepoint contribution |
| Threads chờ socket | GC bình thường | Downstream p99 tăng | External I/O bottleneck |
| Không có hot Java stack | GC bình thường | cgroup throttling cao | CPU quota |
| Post-GC live set tăng nhiều cửa sổ | Allocation/retention evidence | RSS/GC pressure tăng | Có thể leak; điều tra sâu |

**Không gọi ma trận này là chứng minh cuối cùng.** Nhiều vấn đề có thể xảy ra đồng thời, ví dụ slow SQL gây Hikari pending và Tomcat saturation; cần tìm thứ tự causal chain.

## 32. Những kết luận sai phổ biến

**“RUNNABLE nghĩa CPU 100%.”** Sai; selector/network I/O cũng có thể xuất hiện RUNNABLE.

**“Có nhiều WAITING tức deadlock.”** Sai; idle executor threads chờ queue là bình thường.

**“Heap tăng tức memory leak.”** Sai; quan sát post-GC live set trong workload tương đương.

**“GC có chạy nghĩa p99 cao do GC.”** Sai; GC bình thường có thể chỉ pause rất ngắn.

**“Một thread dump đủ tìm root cause.”** Sai; cần nhiều thời điểm và metrics.

**“WebFlux Mono không thể chạy blocking.”** Sai; blocking supplier có thể chiếm Netty loop.

**“Tăng event loops chữa JDBC blocking.”** Sai; blocking vẫn còn.

**“Offload bằng boundedElastic làm database nhanh.”** Sai; nó chỉ chuyển nơi chạy blocking work.

**“Tăng Tomcat threads luôn tăng throughput.”** Sai nếu DB, CPU, pool, queue hoặc downstream mới là giới hạn.

**“JFR không ghi event tức hiện tượng không tồn tại.”** Sai; sampling, threshold và capture window có thể bỏ qua.

**“Actuator threaddump có thể public vì không chứa password.”** Sai; stack/threads/heap diagnostics vẫn có thể lộ metadata nhạy cảm.

**“CPU thấp nghĩa service không nghẽn.”** Sai nếu đang chờ lock/pool/I/O hoặc container bị throttle.

## 33. Bảo mật và tác động của diagnostics

Trước khi thu `Thread.print`, JFR hoặc heap artifacts trên môi trường có người dùng:

1. Xác minh đúng JVM, quyền truy cập, mục đích, cửa sổ thời gian.
2. Thống nhất mức tác động tối đa và quyết định có cần bật JFR profile hay không.
3. Giới hạn dung lượng/retention, dùng directory với quyền file phù hợp.
4. Không expose `/actuator/threaddump` hay `/actuator/heapdump` public.
5. Không chia sẻ raw heap dumps hoặc JFR files qua chat/ticket công khai: chúng có thể chứa data paths, SQL/URL, tokens, PII.
6. Không bật verbose wire logging toàn hệ thống chỉ để xem một request chậm.
7. Khi cần điều tra leak sâu, xét mức độ xâm lấn của `GC.class_histogram`/heap dump; không chạy tự động mọi 5 giây.
8. Hoàn nguyên debug settings sau incident, bảo vệ và xóa artifacts theo policy.

Actuator cung cấp nhiều endpoints, nhưng **chỉ `health` thường được expose qua HTTP mặc định**; các endpoint khác phải được cho phép theo cấu hình và phải có security tương ứng. Nếu định nghĩa custom `SecurityFilterChain`, cần tự kiểm tra quyền Actuator thay vì ỷ lại auto-configured defaults.

## 34. Runbook ngắn cho 15 phút đầu một incident

**Phút 0–3:** Ghi cửa sổ incident, affected route, throughput, p99/error rate, deploy changes, JVM version, CPU limit và MVC/WebFlux stack.

**Phút 3–6:** Thu `jvm.gc.pause`, heap/memory, process/container CPU, `jvm.threads.live`, Tomcat/Hikari/Netty metrics, downstream spans. Xác nhận những metrics thực sự có mặt.

**Phút 6–10:** Lấy 2–3 thread dumps cùng window, ghi timestamp và PID. Tìm lặp stack/lock/pool waits. Nếu CPU hay lock contention chưa rõ, JFR ngắn có kiểm soát.

**Phút 10–15:** Xác định hai nguồn bằng chứng độc lập ủng hộ một hypothesis, hai nguồn có thể phản bác; quyết định thử nghiệm thay một biến và guardrails/rollback.

Mẫu báo cáo:

```text
Incident window: 14:00-14:10 +07
Affected route: /api/orders/{id}
Hypothesis: Tomcat requests are waiting for Hikari connection leases
Evidence 1: 3 dumps show workers at HikariPool.getConnection
Evidence 2: Hikari active=max and pending rises in same window
Counter-evidence: GC pauses stay low
Test: reduce long transactions / query time in staging
Before/after: compare p99, throughput, errors, pool pending
Conclusion: supported / rejected / inconclusive
```

Đây là **mẫu ghi điều tra**, không phải output thật. `Counter-evidence` cần được ghi để tránh confirmation bias. Nếu các nguồn mâu thuẫn hoặc không đủ dữ liệu, kết luận là **INCONCLUSIVE** thay vì một root cause bịa ra.

## 35. Lệnh nhanh và câu hỏi ôn tập

Bash/Linux với `PID` là process đã xác minh:

```bash
jcmd -l
jcmd "$PID" VM.version
jcmd "$PID" help
jcmd "$PID" Thread.print -l > thread-1.txt
sleep 3
jcmd "$PID" Thread.print -l > thread-2.txt
sleep 3
jcmd "$PID" Thread.print -l > thread-3.txt

jstat -gcutil "$PID" 1000 10
jcmd "$PID" GC.heap_info

jcmd "$PID" JFR.start name=incident settings=profile \
  duration=60s filename=/tmp/incident.jfr
```

Java 21 virtual threads:

```bash
jcmd "$PID" Thread.dump_to_file -format=json /tmp/threads.json
```

Spring Boot Actuator localhost trong demo:

```bash
curl -s http://127.0.0.1:8080/actuator/metrics
curl -s http://127.0.0.1:8080/actuator/metrics/jvm.gc.pause
curl -s http://127.0.0.1:8080/actuator/metrics/jvm.threads.live
```

**Câu hỏi ôn tập:**

1. Một thread `RUNNABLE` ở `EPoll.wait` có chắc dùng CPU không? Cần thêm metric gì?
2. Vì sao phải lấy nhiều dumps, không chỉ một lần?
3. Thread ở `CountDownLatch.await` có thể vẫn giữ monitor khác không?
4. `BLOCKED` trong intrinsic monitor khác `WAITING` khi Hikari pool lease thế nào?
5. `jstat -gcutil` trả cumulative times; cần tính delta để làm gì?
6. GC heap sawtooth khác retained live set tăng bền vững ra sao?
7. Một GC pause 20 ms đủ giải thích p99 tăng 3 giây chưa?
8. Vì sao `Mono.fromSupplier(() -> jdbc())` có thể block event loop?
9. `subscribeOn(boundedElastic())` giúp gì và không giúp gì?
10. Vì sao event-loop pending tasks có thể tăng bởi CPU throttling chứ không chỉ code blocking?
11. Java 21 virtual threads cần công cụ dump nào ngoài traditional `Thread.print`?
12. Khi nhiều MVC workers chờ Hikari, tại sao không tăng pool ngay?
13. Khi JFR không ghi một event, có thể loại trừ hypothesis không?
14. Cần chứng minh điều gì trước khi tăng `reactor.netty.ioWorkerCount`?
15. Một canary change phải giữ những biến workload nào ổn định?
16. Vì sao heap dump hoặc JFR files cần bảo mật?
17. Khi sửa xong một lỗi, vì sao phải kiểm tra cả p99, throughput, errors, CPU và GC?
18. Khi nào nên báo “chưa đủ bằng chứng” thay vì khẳng định root cause?

## 36. Kết luận: đối chiếu ba mặt phẳng thay vì điều chỉnh cảm tính

Để kiểm chứng một giả thuyết hiệu năng web runtime, hãy phối hợp:

- **Thread dump** cho biết threads đang làm gì và chờ tài nguyên nào, nhất là khi so 2–3 snapshots.
- **GC metrics và unified logs** cho biết phần thời gian JVM bị GC/safepoint ảnh hưởng; không mọi allocation hoặc heap growth đều là leak.
- **Reactor Netty event-loop metrics và thread stacks** giúp phát hiện callback blocking trong WebFlux; trong MVC cần nhìn Tomcat busy workers và pool waits.
- **OS/cgroup CPU, JFR và downstream traces** giúp phân biệt CPU-bound, I/O wait, lock contention, throttling và GC.
- **Một thay đổi có kiểm soát, đo trước/sau** là cách chuyển từ tương quan sang kiểm chứng nguyên nhân.

Kết luận kỹ thuật tốt phải trả lời được: **điểm nghẽn ở đâu, bằng chứng theo thời gian nào, phương án khắc phục nào được thử, kết quả thay đổi bao nhiêu và giả thuyết nào đã bị loại?**

### Tài liệu tham khảo chính thức

- Spring Boot 3.3 — Actuator Metrics, JVM/Tomcat/HTTP: https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html
- Spring Boot 3.3 — Actuator Security/Endpoints: https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html
- Spring Boot 3.3 — Thread dump endpoint: https://docs.spring.io/spring-boot/3.3/api/rest/actuator/threaddump.html
- Spring Boot 3.3 — Virtual Threads/Task Execution: https://docs.spring.io/spring-boot/3.3/reference/features/task-execution-and-scheduling.html
- Oracle Java 21 — jcmd: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html
- Oracle Java 21 — jstat: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jstat.html
- Oracle Java 21 — GC Unified Logging: https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html
- Oracle Java 21 — jfr command: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html
- Oracle Java 21 — Virtual Threads and Dumps: https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html
- Oracle Java 21 — Garbage Collection Tuning: https://docs.oracle.com/en/java/javase/21/gctuning/
- Reactor Netty 1.1 — HTTP Server and Event-Loop Metrics: https://projectreactor.io/docs/netty/1.1.17/reference/index.html
- Project Reactor — Schedulers: https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html