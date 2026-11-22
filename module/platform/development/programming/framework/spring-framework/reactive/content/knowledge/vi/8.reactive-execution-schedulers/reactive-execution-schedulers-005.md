# Vị trí đổi Scheduler và chi phí chuyển luồng trong Project Reactor

> **Module:** Spring Framework – reactive. **Chủ đề cha:** Luồng thực thi. Bài học giải thích vì sao và đặt ở đâu các ranh giới thực thi `publishOn`/`subscribeOn`, cách chọn Scheduler, chi phí lập lịch và queue, cũng như ứng dụng trong Spring WebFlux. Các ví dụ sử dụng Java 17+, Reactor Core 3.8.8 và Maven.

## 1. Học xong cần nắm được

1. Phân biệt **subscription/request** đi về phía nguồn (upstream) với **onNext/onError/onComplete** đi về subscriber (downstream).
2. Xác định operator nào chạy trên thread nguồn, thread của `subscribeOn` và thread của `publishOn`, kể cả khi hai ranh giới cùng xuất hiện.
3. Đặt `publishOn` đúng trước công đoạn cần đổi ngữ cảnh và `subscribeOn` ở gần nguồn đồng bộ/blocking cần offload.
4. Giải thích một lần “đổi Scheduler” không đồng nghĩa một lần chuyển thread vật lý cho mọi phần tử; hiểu chi phí queue, worker, prefetch, backpressure, RAM và tail latency.
5. Tránh khóa Reactor Netty event-loop trong WebFlux; chọn đúng `boundedElastic`, `parallel`, `single`, `immediate` và hiểu virtual threads.
6. Viết và chạy ví dụ Java kiểm chứng các vùng thread và JUnit/StepVerifier test, đo hiệu năng bằng quy trình có baseline.
7. Phân biệt chuyển thread tuần tự với **chạy nhiều phần tử đồng thời** qua `flatMap` hoặc `parallel().runOn(...)`.

**Quy tắc:** Scheduler giúp **đặt công việc vào đúng tài nguyên thực thi**, nhưng không tự tăng tốc pipeline. Mỗi ranh giới bất đồng bộ có chi phí, cần có mục đích và dữ liệu đo thực tế.

## 2. Hai chiều của Reactor: subscription và tín hiệu

Một `Mono<T>` hoặc `Flux<T>` thông thường **lazy**. Tạo pipeline bằng `map`, `filter`, `publishOn` chưa làm nguồn chạy. Khi một Subscriber đăng ký, Reactor lắp chuỗi subscriber ngược từ downstream về upstream, rồi nguồn bắt đầu phát khi có demand. Những phần tử và terminal signal đi xuôi về downstream.

~~~text
subscribe / request(n):
Subscriber <── operator cuối <── publishOn <── map <── Source

onNext / onError / onComplete:
Source ──> map ──> publishOn ──> operator cuối ──> Subscriber
~~~

Ở đây có ba khái niệm khác nhau:

- **Thread:** nơi JVM đang thực thi callback; có thể là caller thread, event-loop, worker pool hay virtual thread.
- **Scheduler:** trừu tượng của Reactor cấp `Worker` để lập lịch chạy callback; một Scheduler có thể dùng một hoặc nhiều thread.
- **Backpressure/demand:** Subscriber gọi `request(n)` để điều tiết lượng dữ liệu; nó không đồng nghĩa số thread.

**Mặc định Reactor không tạo một thread mới cho mỗi `map`.** Với `Flux.range(1, 3)` đồng bộ, một chuỗi `map/filter` thường chạy ngay trên thread thực hiện subscription. Với `WebClient`, `Flux.interval`, một nguồn I/O hoặc `Mono.fromFuture` bất đồng bộ, callback phát giá trị có thể chạy trên thread riêng của nguồn. Do đó khi đọc luồng thực thi, phải hỏi **ai là người phát tín hiệu thực sự**, thay vì chỉ nhìn vị trí một `subscribeOn`.

## 3. publishOn: đổi chỗ thực thi tín hiệu downstream

**Cú pháp và cách đọc:**

~~~java
Flux<Integer> result = Flux.range(1, 3)
    .map(i -> i + 10)                    // A: trước boundary
    .publishOn(Schedulers.parallel())    // chuyển cách phát downstream
    .map(i -> i * 2);                    // B: sau boundary
~~~

Với `Flux.range` đồng bộ và caller subscribe:
1. Nguồn `Flux.range` và `map(+10)` thường chạy trên caller thread.
2. `publishOn` tiếp nhận tín hiệu nguồn, lập lịch chuyển tiếp tới một Worker của `Schedulers.parallel()`.
3. `map(*2)` chạy trên worker đó, cùng các toán tử phía sau cho tới boundary kế tiếp hoặc một nguồn/operator bất đồng bộ thay đổi cách phát.

**Vị trí `publishOn` có ý nghĩa trực tiếp.** Nếu tác vụ CPU nặng đứng **trước** publishOn, publishOn không quay lại chuyển tác vụ đó sang Scheduler mới. Muốn đổi chỗ xử lý một bước cụ thể, đặt boundary **trước** bước ấy.

~~~text
Flux.range --- map(A) --- publishOn(cpu) --- map(B) --- publishOn(out) --- map(C)
    caller       caller              |        cpu             |          out
                                   boundary 1            boundary 2
~~~

Mỗi `publishOn` chọn một Worker và chuyển tiếp `onNext`, `onError`, `onComplete` của luồng xuống downstream. **Đối với một subscription tuần tự, `onNext` sau publishOn vẫn được serialize**, không phải mọi phần tử đồng thời được đẩy vào nhiều CPU. `publishOn(Schedulers.parallel())` không tương đương `parallel().runOn(...)`.

### 3.1. Hai publishOn

~~~java
Flux<String> transformed = Flux.range(1, 3)
    .map(i -> "item-" + i)
    .publishOn(cpuScheduler)
    .map(this::compute)
    .publishOn(outputScheduler)
    .doOnNext(this::send);
~~~

Đây là **fragment**, vì `cpuScheduler`, `outputScheduler`, `compute` và `send` cần được ứng dụng định nghĩa. Theo nguồn đồng bộ ở ví dụ, `compute` chạy trên vùng cpuScheduler; `send` trên vùng outputScheduler. Nếu `send` lại là I/O blocking, cần chiến lược riêng; một `publishOn` tự nó không làm lời gọi blocking trở thành non-blocking.

### 3.2. Queue, prefetch và backpressure

`publishOn` là một **ranh giới bất đồng bộ**: phần tử từ upstream có thể được đưa vào queue, Worker phía downstream đọc và chuyển theo demand. Overload có `prefetch`:

~~~java
Flux<Integer> result = Flux.range(1, 1_000)
    .publishOn(Schedulers.parallel(), 32)
    .map(this::compute);
~~~

Đây là fragment với hàm `compute` của ứng dụng. `32` là prefetch cấu hình: operator có thể xin trước một số phần tử và bổ sung yêu cầu theo tiến độ. Nó **không** bảo đảm queue luôn giữ đúng 32 phần tử, cũng không giới hạn mọi queue nằm ngoài boundary ở 32 phần tử.

Ưu/nhược của prefetch:
- Cao hơn có thể giảm tần suất phối hợp `request(n)` và cải thiện throughput.
- Cao hơn cũng có thể tăng phần tử **in-flight**, heap, áp lực GC và thời gian nằm chờ.
- Thấp hơn có thể giảm áp lực bộ nhớ nhưng tăng số lần trao đổi nhu cầu, làm nguồn ít bận hơn mức cần thiết.
- Giá trị phù hợp phụ thuộc tải, payload, tốc độ downstream và lượng subscription đồng thời; không có “prefetch tối ưu” cho mọi ứng dụng.

`publishOn` vẫn tôn trọng backpressure trong chuỗi chuẩn. **Nguồn nóng phát dữ liệu bất chấp demand** cần chiến lược tràn riêng (`onBackpressureBuffer` có giới hạn, drop/latest/error hoặc broker), vì đổi scheduler không tự giải quyết việc producer nhanh hơn consumer kéo dài.

## 4. subscribeOn: đổi cách đăng ký tới nguồn

**Cú pháp điển hình:**

~~~java
Mono<String> loaded = Mono.fromCallable(() -> legacyRead())
    .subscribeOn(Schedulers.boundedElastic())
    .map(String::trim);
~~~

Đoạn trên là **fragment**, `legacyRead()` là hàm blocking có thật do ứng dụng cung cấp. `subscribeOn` sắp xếp quá trình subscribe và các tương tác request với upstream trên Worker của Scheduler đã chọn. Vì `fromCallable` thực thi Callable khi subscribe, blocking call thường chạy trên `boundedElastic()` thay vì giữ thread caller hoặc Netty event-loop.

Với nguồn đồng bộ, vị trí subscribeOn tương đối linh hoạt hơn publishOn:

~~~java
Flux<Integer> a = Flux.range(1, 3)
    .subscribeOn(Schedulers.parallel())
    .map(i -> i + 1);

Flux<Integer> b = Flux.range(1, 3)
    .map(i -> i + 1)
    .subscribeOn(Schedulers.parallel());
~~~

Trong hai pipeline này, nguồn synchronous và `map` nằm trên cùng vùng thực thi do subscribeOn chọn, nếu không có boundary khác. **Nên đặt subscribeOn gần nguồn** để code dễ kiểm tra, nhất là khi `doFirst`, `doOnRequest` và các operator khác quan sát đường subscription/request.

### 4.1. Có nên thêm nhiều subscribeOn?

~~~java
Flux<Integer> unnecessary = Flux.range(1, 3)
    .subscribeOn(schedulerA)
    .map(i -> i * 2)
    .subscribeOn(schedulerB);
~~~

Các Scheduler ở fragment phải được định nghĩa trong ứng dụng. Nhiều `subscribeOn` **không làm mỗi phần tử chạy song song**. Tài liệu Reactor cảnh báo chỉ một subscribeOn gần đường upstream nhất định mới chi phối việc scheduling subscription/request tới nguồn; thêm subscribeOn có thể tạo **hop thừa**. Dùng **một subscribeOn ở từng nguồn cần offload**; dùng publishOn tại ranh giới downstream thật sự cần đổi Worker.

### 4.2. Không cưỡng ép nguồn bất đồng bộ quay về subscribeOn

~~~java
Flux<Long> ticks = Flux.interval(Duration.ofSeconds(1))
    .subscribeOn(Schedulers.boundedElastic())
    .map(i -> i + 1);
~~~

`Flux.interval` dùng Scheduler để lên lịch **phát tick**, theo mặc định thường là `Schedulers.parallel()`. `subscribeOn` có thể chuyển lúc đăng ký nhưng **không buộc mỗi tick từ timer chạy trên boundedElastic**. Nếu muốn thay Scheduler **phát timer**, dùng overload `Flux.interval(period, scheduler)`; nếu muốn đổi chỗ xử lý **sau** timer, dùng publishOn.

Điều tương tự áp dụng cho `WebClient`, callback từ network, `Mono.fromFuture` hoặc Publisher bên trong `flatMap`: nguồn bất đồng bộ có thể phát callback trên thread khác với thread đã subscribe. Không suy ra mọi `onNext` phải cùng thread chỉ vì có subscribeOn.

## 5. Kết hợp subscribeOn và nhiều publishOn

~~~java
Mono<Integer> pipeline = Mono.fromSupplier(() -> 10)
    .map(n -> n + 1)
    .subscribeOn(sourceScheduler)
    .publishOn(cpuScheduler)
    .map(n -> n * 2)
    .publishOn(resultScheduler)
    .map(n -> n + 3);
~~~

Đây là fragment với ba Scheduler do ứng dụng cung cấp. Từ nguồn `fromSupplier` đồng bộ:
- `subscribeOn(sourceScheduler)` điều phối việc subscribe của upstream; supplier và `map(+1)` chạy ở vùng source.
- `publishOn(cpuScheduler)` chuyển phần downstream, vì vậy `map(*2)` chạy trên cpuScheduler.
- `publishOn(resultScheduler)` chuyển phần cuối, nên `map(+3)` chạy trên resultScheduler.

**Giá trị đầu ra luôn là 25**: `(10 + 1) * 2 + 3 = 25`. Scheduler ảnh hưởng thread, scheduling và latency, chứ không thay đổi phép tính thuần.

~~~text
                           subscribe từ caller
                                    |
                       subscribeOn(sourceScheduler)
                                    |
                   Supplier -> map(+1) [sourceScheduler]
                                    |
                        publishOn(cpuScheduler)
                                    |
                         map(*2) [cpuScheduler]
                                    |
                       publishOn(resultScheduler)
                                    |
                        map(+3) [resultScheduler]
                                    |
                                Subscriber
~~~

Đừng nhầm toàn bộ callback đều chắc chắn nằm trong vùng của `publishOn`: `doFirst`, `doOnSubscribe`, `doOnRequest`, `doFinally` có thể quan sát subscription/request/cancel vào những lúc khác. Khi cần biết thread ở một điểm, ghi nhận trực tiếp callback cụ thể và tín hiệu đi qua ranh giới nào.

## 6. Lựa chọn Scheduler đúng việc

| Scheduler | Đặc điểm | Phù hợp | Rủi ro |
| --- | --- | --- | --- |
| `Schedulers.immediate()` | Thực thi trên thread đang gọi, không tạo thread riêng | Giữ ngữ cảnh hiện tại khi không cần offload | Không xử lý được blocking/CPU nặng bằng cách chuyển worker. |
| `Schedulers.single()` | Một worker/thread dùng chung | Công việc ngắn, tuần tự, affinity đơn giản | Tác vụ chậm chặn các tác vụ khác của pool chung. |
| `Schedulers.newSingle("name")` | Một scheduler riêng, cần `dispose()` | Ví dụ, thành phần yêu cầu một thread có lifecycle riêng | Tránh tạo theo mỗi request hoặc dispose quá sớm. |
| `Schedulers.parallel()` | Pool phục vụ CPU/timer, số worker liên quan số CPU | Tính toán không blocking, scheduling ngắn | Không đặt JDBC/Thread.sleep hay network sync trực tiếp vào pool này. |
| `Schedulers.boundedElastic()` | Thread/task queue có giới hạn, tối ưu bridge blocking | Thư viện legacy/JDBC/file blocking chưa có API async | Có thể bão hòa, chờ hàng đợi, tăng latency khi tải cao. |
| Scheduler từ ExecutorService | Cấu hình hạ tầng thực thi riêng | Tích hợp pool đã được quản lý | Phải có lifecycle, bounded queue và shutdown rõ. |

`boundedElastic()` có tài nguyên **hữu hạn**. Ở JDK 17, thường dùng thread nền tảng. Reactor từ 3.6 hỗ trợ tùy chọn chạy trên **virtual threads** ở JDK 21+ với thuộc tính khởi động `reactor.schedulers.defaultBoundedElasticOnVirtualThreads=true`; đừng hiểu tính năng này có sẵn trên JDK 17. Virtual threads vẫn không làm backend DB/connection pool có vô hạn capacity; một API blocking vẫn là API blocking.

Scheduler tự tạo như `newSingle`/`newParallel` phải được `dispose()` đúng vòng đời, không ở lúc vừa trả về `Mono` chưa subscribe. Các scheduler dùng chung từ `Schedulers.parallel()` và `Schedulers.boundedElastic()` thường do Reactor quản lý; không tùy tiện dispose toàn cục trong request.

## 7. Chi phí chuyển ngữ cảnh: tại sao không thêm publishOn khắp nơi?

### 7.1. Lập lịch và phối hợp queue

Một `publishOn` thường cần đặt task vào Worker, enqueue/dequeue tín hiệu, phối hợp demand và drain queue. Các hoạt động này tiêu CPU/atomic/heap; nếu toán tử tiếp theo chỉ là `i + 1`, chi phí scheduling có thể lớn hơn phần xử lý hữu ích. Nếu worker đang bận, tín hiệu chờ trong queue và tăng **queueing latency**.

**Không khẳng định một onNext luôn gây một OS thread context switch**: nhiều tín hiệu có thể được drain trên một Worker liên tục, scheduler có thể reuse thread. Nhưng async boundary vẫn thêm overhead logic, queueing và áp lực tài nguyên có thể đo được.

### 7.2. Prefetch, RAM và backpressure

Nhiều boundary có thể tạo nhiều nơi giữ phần tử đang chờ. Áp lực RAM gần đúng tăng theo số subscription, số queue, prefetch và kích thước payload, nhưng không có công thức cố định vì còn operator upstream, codec, network buffer và nguồn ngoài. Nếu downstream chậm, queue có thể khiến p95/p99 tăng ngay cả khi throughput ban đầu cao.

Kiểm tra kích thước và hình dạng backpressure thực tế. `publishOn(..., 32)` là cấu hình prefetch, không phải cam kết “cả ứng dụng chỉ tốn 32 phần tử”.

### 7.3. Chi phí pool/thread và CPU cache

Thêm boundary thừa có thể làm nhiều Worker tranh nhau CPU, tăng số tác vụ scheduling, đổi locality/cache và làm log khó nối dòng. `publishOn(parallel)` chọn Worker để chuyển tín hiệu của một subscription, không tự tạo `N` tác vụ xử lý phần tử song song.

### 7.4. Context và observability

`ThreadLocal` hay MDC kiểu truyền thống gắn với **thread**, không tự chuyển sang Worker khác. `Thread.currentThread().getName()` hữu ích khi debug nhưng **không** là định danh request. Trong Reactor nên dùng **Reactor Context** (`contextWrite`, `deferContextual`) gắn với subscription, kết hợp context-propagation/security/tracing chính thức nếu cần khôi phục MDC khi log.

Đừng tự giả định việc thêm `publishOn` giữ nguyên `ThreadLocal` hoặc là giải pháp để truyền JWT, correlation ID và dữ liệu request. Kiểm thử trace và security context qua mỗi async boundary.

### 7.5. Vì sao có hop vẫn đáng trả?

Khi event-loop đang phục vụ nhiều socket, chuyển một phần công việc CPU vừa phải ra pool thích hợp có thể giúp event-loop duy trì responsiveness. Khi một nguồn legacy chặn I/O, `fromCallable(...).subscribeOn(boundedElastic())` giúp tránh giữ event-loop trong thời gian chờ. Lợi ích phải so với chi phí queue, pool bão hòa và số hop — đừng chỉ so một request đơn lẻ.

## 8. Ví dụ Java 17+ chạy được, in vùng thực thi xác định

Ví dụ dùng ba `Schedulers.newSingle` có prefix rõ ràng. Thay vì in tên thread đầy đủ (có thể thêm chỉ số thay đổi), helper kiểm tra prefix và in **tên vùng**. Các `block()` ở đây chỉ làm ứng dụng CLI đợi kết quả trước khi in; **không đặt block() trong WebFlux request path**.

### 8.1. Cấu trúc

~~~text
reactor-scheduler-demo/
├── pom.xml
├── src/main/java/com/example/scheduler/SchedulerDemo.java
└── src/test/java/com/example/scheduler/SchedulerDemoTest.java
~~~

### 8.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>reactor-scheduler-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-core</artifactId>
            <version>3.8.8</version>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
            <version>3.8.8</version>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.4</version>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 8.3. src/main/java/com/example/scheduler/SchedulerDemo.java

~~~java
package com.example.scheduler;

import java.util.List;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Scheduler;
import reactor.core.scheduler.Schedulers;

public final class SchedulerDemo {
    private SchedulerDemo() {}

    static String region(String expected) {
        String threadName = Thread.currentThread().getName();
        if (!threadName.startsWith(expected + "-")) {
            throw new IllegalStateException(
                "Expected " + expected + ", got " + threadName);
        }
        return expected;
    }

    public static void main(String[] args) {
        Scheduler source = Schedulers.newSingle("source-zone");
        Scheduler compute = Schedulers.newSingle("compute-zone");
        Scheduler output = Schedulers.newSingle("output-zone");

        try {
            Mono<String> positions = Mono
                .fromSupplier(() -> region("source-zone"))
                .subscribeOn(source)
                .map(s -> s + " > " + region("source-zone"))
                .publishOn(compute)
                .map(s -> s + " > " + region("compute-zone"))
                .publishOn(output)
                .map(s -> s + " > " + region("output-zone"));

            System.out.println("positions=" + positions.block());

            List<Integer> values = Flux.range(1, 10)
                .publishOn(compute, 4)
                .map(i -> {
                    region("compute-zone");
                    return i * 2;
                })
                .take(4)
                .collectList()
                .block();
            System.out.println("values=" + values);

            // Đây là mô phỏng một thư viện blocking cũ.
            Mono<String> legacy = Mono.fromCallable(() -> {
                Thread.sleep(20);
                return "OK";
            }).subscribeOn(Schedulers.boundedElastic());
            System.out.println("legacy=" + legacy.block());
        } finally {
            source.dispose();
            compute.dispose();
            output.dispose();
        }
    }
}
~~~

`Mono.fromSupplier` chạy trong vùng `source-zone` nhờ subscribeOn. `map` đầu vẫn trong vùng source; sau publishOn(compute), `map` tiếp theo chạy trên `compute-zone`; sau publishOn(output), bước cuối chạy trên `output-zone`. `Flux.range` chỉ chuyển bước nhân đôi sang compute Worker; prefetch 4 không tự tạo 4 thread. Lời gọi sleep mô phỏng SDK blocking và được offload sang boundedElastic.

**Vì sao dispose ở cuối là đúng?** CLI đã gọi block tại các điểm cuối nên các subscription đã hoàn thành. Trong WebFlux, trả Mono chưa đồng nghĩa Mono đã chạy; nếu dispose Scheduler ngay khi phương thức service return, có thể khiến pipeline sau đó lỗi do Scheduler đã bị đóng. Dùng Scheduler bean có lifecycle dài đủ.

### 8.4. Lệnh chạy và stdout

Ở thư mục chứa pom.xml, cần JDK 17+ và Maven:

~~~bash
java -version
mvn -version
mvn test
mvn -q exec:java -Dexec.mainClass=com.example.scheduler.SchedulerDemo
~~~

**Những dòng stdout do main in ra** (không tính log Maven):

~~~text
positions=source-zone > source-zone > compute-zone > output-zone
values=[2, 4, 6, 8]
legacy=OK
~~~

Giá trị/thứ tự không phụ thuộc thời điểm OS lập lịch. Prefix tên thread chỉ được dùng để chứng minh vùng trong demo; không thiết kế nghiệp vụ dựa trên tên thread.

## 9. Kiểm thử thread boundary với StepVerifier

`StepVerifier` kiểm tra onNext/terminal signal mà không cần thêm Thread.sleep vào test. Test bên dưới dùng Scheduler tự tạo, gọi `dispose()` sau khi verify, và kiểm tra prefix thread đúng từng vùng.

**src/test/java/com/example/scheduler/SchedulerDemoTest.java**

~~~java
package com.example.scheduler;

import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Scheduler;
import reactor.core.scheduler.Schedulers;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SchedulerDemoTest {

    @Test
    void publishOnChangesDownstreamThread() {
        Scheduler stage = Schedulers.newSingle("test-stage");
        String caller = Thread.currentThread().getName();
        AtomicReference<String> before = new AtomicReference<>();
        AtomicReference<String> after = new AtomicReference<>();
        try {
            Flux<Integer> values = Flux.range(1, 3)
                .doOnNext(v -> before.set(
                    Thread.currentThread().getName()))
                .publishOn(stage)
                .doOnNext(v -> after.set(
                    Thread.currentThread().getName()));

            StepVerifier.create(values)
                .expectNext(1, 2, 3)
                .verifyComplete();

            assertEquals(caller, before.get());
            assertTrue(after.get().startsWith("test-stage-"));
        } finally {
            stage.dispose();
        }
    }

    @Test
    void subscribeOnSchedulesCallableSource() {
        Scheduler source = Schedulers.newSingle("test-source");
        AtomicReference<String> executedOn = new AtomicReference<>();
        try {
            Mono<Integer> sourceValue = Mono.fromCallable(() -> {
                executedOn.set(Thread.currentThread().getName());
                return 7;
            }).subscribeOn(source).map(i -> i + 1);

            StepVerifier.create(sourceValue)
                .expectNext(8)
                .verifyComplete();

            assertTrue(executedOn.get().startsWith("test-source-"));
        } finally {
            source.dispose();
        }
    }

    @Test
    void twoPublishOnBoundariesChooseTwoZones() {
        Scheduler one = Schedulers.newSingle("test-one");
        Scheduler two = Schedulers.newSingle("test-two");
        AtomicReference<String> first = new AtomicReference<>();
        AtomicReference<String> second = new AtomicReference<>();
        try {
            Flux<Integer> values = Flux.range(1, 3)
                .publishOn(one)
                .doOnNext(v ->
                    first.set(Thread.currentThread().getName()))
                .publishOn(two)
                .doOnNext(v ->
                    second.set(Thread.currentThread().getName()));

            StepVerifier.create(values)
                .expectNext(1, 2, 3)
                .verifyComplete();

            assertTrue(first.get().startsWith("test-one-"));
            assertTrue(second.get().startsWith("test-two-"));
        } finally {
            one.dispose();
            two.dispose();
        }
    }
}
~~~

Test đầu chỉ suy ra trước publishOn chạy trên caller vì **nguồn `Flux.range` đồng bộ**. Không áp dụng giả định đó cho `WebClient`, `Mono.delay` hay inner async Publisher. Test thứ hai xác định vị trí thực thi của Callable. Test thứ ba xác nhận hai ranh giới trên hai Scheduler riêng.

**Không phải benchmark:** kiểm tra tên thread/signal cho biết chức năng đúng, không đo độ trễ hop. Test timing thực tế cần môi trường tải và phương pháp đo riêng.

## 10. publishOn(parallel) không phải xử lý nhiều phần tử song song

~~~java
Flux<Integer> serialOnWorker = Flux.range(1, 1_000)
    .publishOn(Schedulers.parallel())
    .map(this::heavyComputation);
~~~

Đây là fragment dùng hàm `heavyComputation` của ứng dụng. Nó chuyển **đường xử lý downstream** của một subscription sang một Worker, nhưng `map` vẫn nhận phần tử theo chuỗi. Nếu công việc thực sự CPU-bound và mỗi phần tử độc lập:

~~~java
Flux<Integer> multiRail = Flux.range(1, 1_000)
    .parallel(4)
    .runOn(Schedulers.parallel())
    .map(this::heavyComputation)
    .sequential();
~~~

`parallel(4)` chia nguồn thành bốn rail; `runOn` đặt các rail trên Scheduler; `sequential` đưa về Flux thường. Nó có overhead phân chia/ghép và không luôn nhanh hơn; cần kiểm tra tính chất thứ tự, CPU cores và lượng việc mỗi phần tử. Phép toán quá nhỏ như `i + 1` có thể chậm hơn vì overhead.

Đối với nhiều tác vụ **I/O non-blocking** (ví dụ WebClient) theo danh sách id, dùng `flatMap` với concurrency hữu hạn:

~~~java
Flux<Result> results = Flux.fromIterable(ids)
    .flatMap(id -> remoteClient.fetch(id), 8);
~~~

Fragment giả định `ids` là danh sách, `remoteClient.fetch(id)` trả `Mono<Result>`. `8` giới hạn số inner subscription đồng thời trong flatMap; thứ tự kết quả có thể thay đổi. Khi cần giữ thứ tự xuất ra, cân nhắc `flatMapSequential` hoặc `concatMap`; không rải subscribeOn vào mọi phần tử của một nguồn vốn đã non-blocking.

## 11. Cô lập blocking I/O khỏi Spring WebFlux event-loop

Reactor Netty event-loop phục vụ I/O cho nhiều socket. Một lời gọi **JDBC đồng bộ, SDK HTTP blocking, Thread.sleep, đọc file blocking hoặc Mono.block()** trên event-loop có thể chặn nhiều request cùng lúc. `publishOn(Schedulers.parallel())` không phải cách offload blocking I/O hợp lý: các worker parallel được thiết kế cho non-blocking/CPU.

**Mẫu bridge blocking cũ:**

~~~java
Mono<Customer> found = Mono.fromCallable(() ->
        legacyGateway.load(customerId))
    .subscribeOn(Schedulers.boundedElastic())
    .map(this::mapToCustomer);
~~~

Đây là fragment trong service có `legacyGateway`, `customerId`, `Customer`, `mapToCustomer`; không tự biên dịch khi thiếu các định nghĩa đó. `fromCallable` trì hoãn blocking call tới subscription, còn subscribeOn đặt nó vào pool boundedElastic. `boundedElastic` vẫn có giới hạn thread/queue; cần timeout, connection pool, concurrency limit và giám sát saturation. Driver reactive phù hợp có thể tốt hơn khi phải xử lý tải I/O cao.

### 11.1. Controller WebFlux minh họa

~~~java
package com.example.web;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@RestController
@RequestMapping("/customers")
public class CustomerController {
    private final BlockingCustomerGateway gateway;

    public CustomerController(BlockingCustomerGateway gateway) {
        this.gateway = gateway;
    }

    @GetMapping("/{id}")
    public Mono<CustomerDto> find(@PathVariable String id) {
        return Mono.fromCallable(() -> gateway.load(id))
            .subscribeOn(Schedulers.boundedElastic())
            .map(row -> new CustomerDto(row.id(), row.name()));
    }
}
~~~

**Fragment tích hợp**, không phải chương trình độc lập: cần Spring Boot WebFlux application, bean `BlockingCustomerGateway`, các kiểu `CustomerDto`/row và cấu hình thực tế. Phải bổ sung HTTP 404, validation, xử lý lỗi, bảo mật theo hệ thống. Controller **trả Mono** cho WebFlux subscribe; không gọi block/subscribe trong request handler.

### 11.2. Blocking I/O trong từng inner Publisher

~~~java
Flux<Customer> customers = Flux.fromIterable(ids)
    .flatMap(id ->
        Mono.fromCallable(() -> gateway.load(id))
            .subscribeOn(Schedulers.boundedElastic()),
        8);
~~~

Đây là fragment có `ids`, gateway và kiểu Customer. `subscribeOn` trong từng `Mono.fromCallable` offload riêng từng lời gọi; `8` giới hạn concurrency. Một subscribeOn đặt ngoài toàn bộ Flux không bảo đảm mọi inner blocking work được chạy song song an toàn; vị trí ở nguồn công việc cụ thể mới rõ nghĩa.

### 11.3. Nếu đã dùng client reactive

~~~java
Mono<CustomerDto> customer = webClient.get()
    .uri("/customers/{id}", id)
    .retrieve()
    .bodyToMono(CustomerDto.class);
~~~

Đây là fragment với `webClient`, `id` và `CustomerDto` có sẵn. `WebClient` với connector non-blocking đã thực hiện network I/O bất đồng bộ; **không cần thêm subscribeOn(boundedElastic) chỉ vì có HTTP request**. Chỉ thêm publishOn nếu một bước downstream cụ thể cần Scheduler khác, và phải hiểu chi phí.

## 12. Các sai lầm điển hình

| Sai lầm | Hậu quả | Sửa đúng |
| --- | --- | --- |
| Đặt publishOn **sau** bước CPU/blocking cần đổi | Bước ấy vẫn chạy upstream | Đặt publishOn trước bước cần đổi; dùng boundedElastic nếu blocking. |
| Rải subscribeOn ở mọi đoạn | Hop subscribe thừa, không tăng per-item parallelism | Một subscribeOn cho mỗi nguồn cần offload. |
| Coi publishOn(parallel) là parallel per item | Không đạt concurrency kỳ vọng | Dùng `parallel().runOn` cho CPU độc lập hoặc flatMap cho I/O async. |
| Chuyển mọi callback sang boundedElastic | Hàng chờ/tài nguyên tăng, mất lợi ích async | Chỉ dùng boundedElastic cho legacy blocking. |
| Dùng Thread.sleep hoặc block trong Netty event-loop | Dừng phục vụ nhiều kết nối | Reactive driver hoặc offload nguồn blocking đúng cách. |
| Tạo Scheduler mới cho mỗi request | Nổ số thread và khó cleanup | Dùng shared Scheduler hoặc bean quản lý lifecycle. |
| Dispose Scheduler ngay khi trả Mono | Mono chưa subscribe nên có thể lỗi scheduler | Giữ Scheduler đến khi subscription hoàn thành/shutdown app. |
| Tăng prefetch vô hạn để tăng tốc | Heap/GC và p99 xấu khi consumer chậm | Tuning theo workload và giới hạn bộ đệm. |
| Đọc MDC/ThreadLocal sau publishOn mà không truyền context | Mất trace/requestId | Reactor Context và context-propagation đúng. |
| Tưởng subscribeOn buộc mọi callback network ở cùng thread | Debug sai hành vi async source | Kiểm tra thread của emitter/inner Publisher, dùng publishOn nơi cần. |
| Thấy nhiều scheduler nên nghĩ chắc chắn nhanh hơn | Scheduling/queue có thể tốn hơn công việc hữu ích | Đo baseline, 1 hop, 2 hop dưới cùng tải. |

## 13. Đo chi phí chuyển luồng có phương pháp

Không có số cố định “một publishOn tốn X microsecond” áp dụng mọi máy. Chi phí phụ thuộc Reactor/JDK, thread pool, CPU quota, số request đồng thời, payload size, GC, prefetch và mức bão hòa downstream.

**Quy trình đo:**
1. **Baseline:** source và `map` đồng bộ trên cùng Worker; tính throughput, p50/p95/p99, CPU/heap/GC.
2. **Một publishOn:** đổi đúng trước bước cần offload, giữ dữ liệu và hàm xử lý không đổi.
3. **Hai publishOn:** thêm ranh giới nếu topology sản phẩm yêu cầu, so p99, queue và resource consumption.
4. **Tuning prefetch:** chạy các mức hữu hạn (ví dụ 16, 32, 128), đo in-flight, lượng memory và tốc độ downstream.
5. **Tải đồng thời thực tế:** kiểm tra request latency, event-loop responsiveness, boundedElastic queue, connection pool và cancellation dưới tải cao.
6. **Công cụ:** dùng JMH cho microbenchmark cần warmup/JIT đúng, load test của endpoint cho hành vi server, Micrometer/Actuator/trace cho chẩn đoán trong ứng dụng.

**Kết luận từ số liệu:** một boundary có thể làm một pipeline đơn lẻ chậm thêm chút ít nhưng bảo vệ event-loop và cải thiện khả năng phục vụ tải; ngược lại, thêm hai boundary cho phép toán rất nhỏ có thể tăng queueing/p99. Đo SLO thực, không chỉ số thread.

## 14. Bảng quyết định nhanh

| Mục tiêu | Vị trí/cách dùng | Nhận xét |
| --- | --- | --- |
| Offload nguồn Callable blocking | `Mono.fromCallable(...).subscribeOn(boundedElastic())` | Đặt gần nguồn và giới hạn tải. |
| Đổi nơi thực thi một bước CPU phía sau | `source.map(light).publishOn(cpu).map(heavy)` | publishOn đứng trước bước cần đổi. |
| Cần hai vùng worker tiếp nối nhau | `publishOn(s1).map(A).publishOn(s2).map(B)` | Hai boundary có thêm overhead. |
| Xử lý nhẹ sau WebClient non-blocking | `webClient...bodyToMono(...).map(...)` | Không cần scheduler hop mặc định. |
| Nhiều phần tử CPU-bound độc lập | `parallel(rails).runOn(parallel).map(...).sequential()` | Đo overhead và yêu cầu thứ tự. |
| Nhiều I/O non-blocking | `flatMap(id -> client.fetch(id), concurrency)` | Giới hạn in-flight; lưu ý thứ tự. |
| Nhiều SDK blocking | `flatMap(id -> fromCallable(...).subscribeOn(boundedElastic()), concurrency)` | Offload từng inner work. |
| Timer tự phát trên Scheduler chỉ định | `Flux.interval(period, scheduler)` | Scheduler của timer khác subscribeOn. |
| Giữ trace/security khi đổi thread | Reactor Context và framework context propagation | Không tin ThreadLocal tự được sao chép. |
| Hạn chế RAM ở async boundary | Chọn `publishOn(scheduler, prefetch)` + giám sát | Prefetch không phải giới hạn bộ nhớ toàn hệ thống. |

## 15. Bài tập áp dụng

**Bài 1.** Chạy `Flux.range(1,3).map(A).publishOn(cpu).map(B)`, in thread ở A/B, rồi chuyển publishOn lên trước A. **Đáp án mong đợi:** lần đầu A thuộc vùng source, B thuộc vùng cpu; lần sau cả A/B thuộc vùng cpu, với nguồn đồng bộ và không có async boundary khác.

**Bài 2.** Thêm `publishOn(s1).map(A).publishOn(s2).map(B)` và xác nhận A/B chạy ở hai worker bằng test. Sau đó đo liệu hop thứ hai có ích hay không với công việc nhỏ. **Đáp án:** đúng về placement không đồng nghĩa tốt về hiệu năng.

**Bài 3.** Gọi một SDK blocking trong WebFlux qua `Mono.fromCallable`, `subscribeOn(boundedElastic)`. Kiểm tra concurrent requests và khi pool bị bão hòa. **Đáp án:** giảm blocking trên event-loop, nhưng vẫn phải quản lý connection, timeout và saturation.

**Bài 4.** So `publishOn(parallel).map(cpu)` với `parallel(4).runOn(parallel).map(cpu).sequential()` cho 10.000 phần tử. **Đáp án:** trường hợp đầu là đổi ngữ cảnh cho một luồng tuần tự; trường hợp sau mới phân rail, có overhead và có thể đổi đặc điểm thứ tự.

**Bài 5.** Với request phải truyền requestId qua nhiều Scheduler, kiểm tra `ThreadLocal`/MDC có bị mất, rồi dùng Reactor Context/context propagation. **Đáp án:** dữ liệu gắn thread không tự trở thành dữ liệu gắn subscription.

## 16. Checklist trước khi triển khai

- [ ] Tôi biết nguồn synchronous hay asynchronous và callback do ai phát.
- [ ] Tôi giải thích được chiều subscription/request và chiều onNext/error/complete.
- [ ] Tôi đặt subscribeOn cho nguồn cần offload và publishOn trước downstream cần đổi context.
- [ ] Tôi không hiểu publishOn(parallel) là xử lý song song từng phần tử.
- [ ] Tôi không chạy Blocking I/O hay Thread.sleep trên Netty/parallel Scheduler.
- [ ] Tôi quản lý Scheduler riêng theo lifecycle và không dispose sớm.
- [ ] Tôi hiểu prefetch/queue, backpressure, memory, p99 và giới hạn boundedElastic.
- [ ] Tôi có test vị trí thread tại từng boundary, không hardcode tên thread bất biến.
- [ ] Tôi đã kiểm tra Reactor Context, MDC, security và trace khi đổi worker.
- [ ] Tôi có baseline và số đo hiệu năng đủ tin cậy trước khi thêm hop.

## 17. Tài liệu tham khảo chính thức

1. Project Reactor Reference – Threading and Schedulers: https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html
2. Reactor Flux Javadoc – `publishOn`, `subscribeOn`, prefetch: https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html
3. Reactor Mono Javadoc – `publishOn`, `subscribeOn`: https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html
4. Reactor Schedulers API – `parallel`, `boundedElastic`, virtual-thread option: https://projectreactor.io/docs/core/release/api/reactor/core/scheduler/Schedulers.html
5. Reactor Test StepVerifier: https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html
6. Spring Framework WebFlux: https://docs.spring.io/spring-framework/reference/web/webflux.html

**Tự kiểm tra:** Cho `Mono.fromSupplier(...).subscribeOn(A).map(X).publishOn(B).map(Y).publishOn(C).map(Z)`, bạn cần chỉ ra vị trí thực thi của nguồn, X, Y, Z khi nguồn đồng bộ; giải thích vì sao WebClient/timer có thể khác; và nêu lý do mỗi boundary có lợi hoặc có hại theo tải. Đó là nền tảng để dùng Scheduler đúng.
