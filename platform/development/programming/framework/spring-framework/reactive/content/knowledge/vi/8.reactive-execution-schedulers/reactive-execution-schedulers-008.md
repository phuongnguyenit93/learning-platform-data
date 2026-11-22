# Giới hạn số luồng, hàng đợi và áp lực lên tài nguyên đích trong Spring WebFlux

## 1. Bài toán: nhiều tác vụ đồng thời không có nghĩa tài nguyên vô hạn

Một API Spring WebFlux có thể nhận hàng trăm request, dùng `WebClient` gọi nhiều dịch vụ, hoặc phải tích hợp một thư viện JDBC/SDK cũ thực hiện I/O blocking. Khi tăng tốc bằng cách tạo thêm tác vụ, ta thường gặp các giới hạn hoàn toàn khác nhau:

- **Số thread có thể thực thi công việc**: event-loop thread, worker CPU, worker dành cho blocking I/O hoặc virtual thread.
- **Số tác vụ đang chạy**: số subscription/inner publisher được bắt đầu đồng thời, ví dụ từ `flatMap(..., concurrency)`.
- **Hàng đợi tác vụ**: công việc đã được tiếp nhận nhưng chưa có worker hoặc connection để bắt đầu.
- **Tài nguyên đích**: connection pool JDBC/R2DBC/HTTP, số request đồng thời upstream chịu được, quota API, CPU, bộ nhớ và tốc độ phản hồi của dịch vụ ngoài.

Nếu một API đích chỉ xử lý ổn định 20 request đồng thời, việc tạo thêm 1.000 worker thread hoặc 1.000 `Mono` không tự nâng giới hạn API đích lên 1.000. Thay vào đó, công việc có thể dồn vào scheduler queue, connection-pool pending queue, hàng chờ ở server đích hoặc bị từ chối. Kết quả thường là **latency tăng, timeout, lỗi 429/503, GC và tiêu thụ bộ nhớ tăng**.

Mục tiêu bài học là thiết kế **giới hạn có chủ đích** cho từng lớp, hiểu mối quan hệ giữa throughput, concurrency và queue, xử lý quá tải rõ ràng, đo lường được và giữ hệ thống ổn định. Đây là chủ đề của nhóm kiến thức **Luồng thực thi**: tập trung vào nơi công việc chạy và cách ngăn nguồn chậm kéo sập ứng dụng.

## 2. Sơ đồ đường đi từ request đến tài nguyên đích

Xét một WebFlux endpoint nhận nhiều ID và gọi API bên ngoài:

```text
                         Client requests
                                |
                                v
                       Reactor Netty event loop
                                |
                                v
                       WebFlux controller
                                |
                         Flux<ID> + flatMap
                       (maxConcurrency = 8)
                                |
                                v
                       WebClient / HTTP client
                                |
                  +-------------+-------------+
                  |                           |
           Connection active             Pending acquire
           (pool limit = 16)            (queue limit = 32)
                  |                           |
                  +---------------------------+
                                |
                                v
                   Remote API / database
                   (quota, threads, CPU, DB)
```

Nếu service còn gọi một SDK **blocking**, thường có thêm nhánh:

```text
Reactive pipeline
       |
       v
Mono.fromCallable(blockingCall)
       |
       v
subscribeOn(dedicated boundedElastic)
       |
       +-- running worker threads (threadCap)
       |
       +-- pending tasks (queuedTaskCap)
       |
       +-- rejected when saturated
       |
       v
Legacy SDK -> downstream resource
```

Mỗi ô trong sơ đồ có thể là một giới hạn độc lập. Thậm chí nhiều request HTTP cùng lúc có thể tạo nhiều **subscription** riêng, mỗi subscription lại tạo `flatMap` mới. Vì vậy, `concurrency=8` bên trong một request **không phải giới hạn toàn ứng dụng là 8**.

Điểm quan trọng nữa là **non-blocking I/O không tạo tài nguyên đích miễn phí**. Event loop có thể quản lý rất nhiều kết nối đang chờ mà không giữ một worker thread cho từng kết nối, nhưng upstream vẫn phải xử lý các yêu cầu thực sự; băng thông, số kết nối, quota và bộ nhớ vẫn hữu hạn.

## 3. Phân biệt thread, subscription, connection và task

| Khái niệm | Đơn vị được giới hạn | Ví dụ | Có đồng nghĩa với khái niệm khác không? |
|---|---|---|---|
| Thread | Luồng thực thi Java | `Schedulers.parallel()` hoặc `newBoundedElastic` | Không; một event-loop thread phục vụ được nhiều I/O |
| Active inner publisher | Inner subscription chưa hoàn tất/hủy | `flatMap(mapper, 8)` | Không; một inner có thể phát nhiều phần tử hoặc thực hiện nhiều thao tác |
| Scheduled task | Runnable được scheduler tiếp nhận | `publishOn`, `subscribeOn`, lịch hẹn | Không; nhiều task có thể xếp chờ một worker |
| HTTP connection | Kết nối TCP/TLS hoặc kết nối được pool quản lý | `ConnectionProvider.maxConnections(16)` | Không; HTTP/2 có thể multiplex nhiều request trên một connection |
| DB connection | Phiên làm việc với database trong pool | `maximumPoolSize` của HikariCP | Không; nhiều worker có thể chờ lấy connection |
| Pending acquire | Yêu cầu lấy connection đang đợi pool | `pendingAcquireMaxCount(32)` | Không; khác scheduler task queue |
| Backpressure demand | Số phần tử subscriber sẵn sàng nhận | `Subscription.request(n)` | Không; không đo bằng request/giây hoặc thread |
| Rate limit | Số thao tác cho phép trong khoảng thời gian | 100 HTTP requests/giây | Không; concurrency chỉ đo việc đang diễn ra cùng lúc |

**Không dùng một núm chỉnh thay cho tất cả các giới hạn.** Trong ứng dụng thực, có thể cùng lúc có 8 inner publisher, 4 thread blocking, 16 HTTP connection, 32 lượt chờ cấp connection và một upstream chỉ cho 10 request/giây. Điểm nghẽn nằm ở tầng có khả năng phục vụ thấp nhất trước tải hiện tại.

## 4. Reactor xử lý công việc trên thread nào?

### 4.1. Event loop của WebFlux

Spring WebFlux với Reactor Netty thường nhận và xử lý sự kiện mạng trên một nhóm nhỏ **event-loop threads**. Các thread này hữu ích vì có thể tiếp tục xử lý sự kiện từ kết nối khác khi một thao tác I/O non-blocking chưa có dữ liệu.

Cấm đoán thực tiễn: **không đưa thao tác blocking kéo dài vào event loop**, ví dụ:

```java
@GetMapping("/bad")
public Mono<String> badEndpoint() {
    return Mono.fromCallable(() -> {
        Thread.sleep(500); // Không an toàn nếu chạy trên event loop
        return "done";
    });
}
```

Đây là snippet nằm trong WebFlux `@RestController`; `Mono.fromCallable` **không tự chọn scheduler riêng**. Nếu WebFlux subscribe trên event loop, `Thread.sleep` có thể chặn thread đó. `Mono` không có phép màu làm cho blocking code thành non-blocking.

Với API reactive thực sự (`WebClient`, driver reactive tương thích), nên sử dụng publisher từ chính client và **trả publisher** cho WebFlux:

```java
@GetMapping("/good")
public Mono<String> goodEndpoint() {
    return webClient.get()
            .uri("/status")
            .retrieve()
            .bodyToMono(String.class);
}
```

Đây cũng là snippet: `webClient` phải được inject/cấu hình và endpoint đích phải tồn tại. `WebClient` non-blocking ở phía HTTP client, nhưng dịch vụ đích vẫn có giới hạn xử lý riêng.

### 4.2. Các Scheduler thường gặp

| Scheduler | Ý định sử dụng | Điều phải tránh |
|---|---|---|
| `Schedulers.immediate()` | Chạy trên thread đang gọi | Không có tác dụng tách blocking code khỏi event loop |
| `Schedulers.single()` | Một worker dùng chung cho công việc tuần tự | Blocking kéo dài làm nghẽn mọi công việc chung worker |
| `Schedulers.parallel()` | Nhóm thread cố định, thường gần số CPU khả dụng; phù hợp tính toán CPU ngắn | Không đưa blocking I/O lâu vào nhóm CPU |
| `Schedulers.boundedElastic()` | Scheduler dùng chung có giới hạn cho công việc blocking legacy | Không xem hàng đợi lớn mặc định là cơ chế chống quá tải hoàn chỉnh |
| `Schedulers.newBoundedElastic(threadCap, queuedTaskCap, name)` | Tạo scheduler có giới hạn riêng cho một lớp blocking | Phải quản lý vòng đời và xử lý khi queue đầy |
| Scheduler từ `ExecutorService` | Tích hợp executor có chính sách queue/reject riêng | Không suy đoán giới hạn nếu chưa đọc cấu hình executor |

`parallel()` không phải công cụ cho mọi tác vụ chỉ vì tên chứa “parallel”. Nó dùng nhóm worker hữu hạn phù hợp tính toán. Việc `.publishOn(Schedulers.parallel())` chuyển chuỗi xử lý **phía sau operator** sang scheduler này; nó **không tự động song song hóa từng phần tử** hay tăng năng lực của database.

### 4.3. `subscribeOn` và `publishOn`

Với thư viện blocking cũ, Reactor khuyến nghị bao nó bằng `Mono.fromCallable(...)` và đặt `subscribeOn(Schedulers.boundedElastic())`:

```java
Mono<Account> account = Mono.fromCallable(
        () -> legacyAccountDao.load(accountId)
).subscribeOn(Schedulers.boundedElastic());
```

Đây là snippet cần có DAO và kiểu `Account` của ứng dụng. `fromCallable` trì hoãn lời gọi tới lúc subscribe; `subscribeOn` bố trí quá trình subscription/execution liên quan trên scheduler chỉ định. Một thread boundedElastic vẫn bị **giữ trong lúc `load` chờ**, vì đây vẫn là blocking I/O.

Với `publishOn`:

```java
Flux<Integer> calculated = Flux.range(1, 5)
        .publishOn(Schedulers.parallel())
        .map(value -> value * value);
```

`publishOn` tạo ranh giới chuyển scheduler cho những bước downstream như `map`. Nó không biến lệnh blocking nằm ở upstream thành non-blocking. Khi kết hợp nhiều `publishOn`, cần hiểu hướng của dòng tín hiệu và điểm chuyển thread.

Trong Java 21+, Reactor hỗ trợ biến thể `boundedElastic` dùng virtual threads khi đáp ứng yêu cầu JDK và cấu hình phiên bản tương ứng. **Virtual threads giảm chi phí thread trong nhiều tình huống blocking nhưng không bỏ giới hạn tài nguyên đích, queue hay connection pool.** Bài này dùng Java 17 nên không phụ thuộc virtual threads.

## 5. Giới hạn số thread: boundedElastic và lớp I/O blocking

Trong Reactor Core 3.6.6, `Schedulers.boundedElastic()` có giới hạn thread mặc định dựa trên **10 × số processor khả dụng** (có thể thay bằng system property), và giới hạn task chờ mặc định **100.000 task trên mỗi backing thread**. Đây là cấu hình **scheduler chung**, không nên diễn giải là 100.000 task trên toàn ứng dụng. Con số lớn có thể làm độ trễ đợi hàng chờ rất cao trước khi phát lỗi.

Để cô lập một dependency blocking cụ thể, có thể tạo scheduler riêng:

```java
Scheduler legacyScheduler =
        Schedulers.newBoundedElastic(
                4,          // tối đa 4 backing threads
                20,         // tối đa 20 scheduled tasks chờ / backing thread
                "legacy-io"
        );
```

`newBoundedElastic` trả về `Scheduler` có vòng đời riêng. Cần import `reactor.core.scheduler.Scheduler` và `reactor.core.scheduler.Schedulers`. Với config này:

- Scheduler không tạo vô hạn platform thread cho các task của nó.
- Khi có đủ worker, tối đa 4 thread nền chạy tác vụ blocking cùng thời điểm theo giới hạn scheduler.
- Khi scheduler đã đạt giới hạn thread, task mới có thể được xếp hàng theo `queuedTaskCap` gắn với backing thread. Cách phân phối worker đến backing thread và hàng đợi phụ thuộc implementation.
- Khi không còn chỗ queue, thao tác schedule bị từ chối bằng `RejectedExecutionException`; đừng để người dùng phải đợi mãi vì queue vô hạn.

**Không suy ra tổng dung lượng tài nguyên là `4 × 20 = 80` request HTTP**. Đây là giới hạn của các scheduled task trên scheduler, trong khi một request có thể tạo nhiều task hoặc dùng thêm các connection pool khác. Khi nhiều `Scheduler.Worker` dùng chung backing thread, hiện tượng từ chối còn phụ thuộc cách các worker được phân vào thread.

### Cô lập dependency để tránh tranh chấp toàn ứng dụng

Nếu tích hợp hai SDK blocking độc lập với đặc tính tải khác nhau, có thể sử dụng hai scheduler giới hạn riêng:

```java
Scheduler reportScheduler =
        Schedulers.newBoundedElastic(3, 12, "report-legacy");

Scheduler paymentScheduler =
        Schedulers.newBoundedElastic(2, 8, "payment-legacy");
```

Cấu hình chỉ mang tính minh họa, không phải giá trị mặc định nên dùng trong production. Khi service báo cáo bị treo, nhóm worker và queue dành cho thanh toán không tự động bị chiếm bởi những task chạy trên report scheduler.

Mỗi scheduler tạo riêng phải được **dispose khi ứng dụng dừng**, ví dụ cung cấp qua bean Spring có destroy method thích hợp. Tránh tạo một scheduler mới **cho từng request** vì sẽ làm bùng số pool/thread và khó thu hồi tài nguyên.

## 6. Hàng đợi xuất hiện ở đâu, và vì sao phải có giới hạn?

Một tác vụ có thể đi qua nhiều queue:

```text
Client -> HTTP server ingress
       -> operator/prefetch buffer
       -> scheduler task queue (nếu chuyển sang worker)
       -> HTTP connection pending-acquire queue
       -> upstream HTTP server queue
       -> upstream database connection queue
       -> database execution/lock wait
```

**Queue hấp thụ burst ngắn, nhưng không tạo thêm throughput bền vững.** Khi tốc độ đến liên tục lớn hơn tốc độ xử lý, lượng việc chờ sẽ tăng. Queue càng lớn càng có thể làm trì hoãn lỗi đến lúc request đã vượt deadline, tăng heap và thời gian chờ của khách hàng.

Bốn chiến lược cần phân biệt:

1. **Giới hạn công việc đang chạy**: concurrency cap để upstream không nhận quá nhiều yêu cầu mới cùng lúc.
2. **Giới hạn số việc đang chờ**: queue bounded; khi đầy, từ chối nhanh hoặc phản hồi overload phù hợp.
3. **Giới hạn thời gian chờ**: timeout/deadline cho acquire, request và nghiệp vụ, tránh request mất nhiều giây trong queue rồi vẫn chạy.
4. **Điều tiết đầu vào**: backpressure nơi giao thức hỗ trợ, rate limiting tại ingress hoặc cơ chế admission control.

Nếu dùng queue không giới hạn và chỉ định thời gian chờ ở client, một tác vụ có thể vẫn chiếm tài nguyên sau khi caller bỏ cuộc nếu downstream không hủy đúng cách. Cần quan sát cancellation và cấu hình timeout ở đúng các tầng.

### Các kiểu thất bại dưới tải cao

| Tầng bão hòa | Dấu hiệu | Hành động hợp lý |
|---|---|---|
| Event loop bị block | Latency nhiều endpoint cùng tăng, event-loop thread đứng chờ | Loại bỏ blocking trên event loop, chuyển legacy I/O sang scheduler phù hợp |
| boundedElastic hết thread + queue | Pending task tăng, sau đó `RejectedExecutionException` | Giảm lượng việc nhận, thu nhỏ thời gian blocking, đặt queue bounded và báo quá tải |
| HTTP connection pool đầy | Pending acquire tăng, timeout/cancel khi chờ connection | Giảm `flatMap` concurrency, kiểm tra `maxConnections`, timeout và upstream |
| DB pool đầy | Thread/task chờ lấy connection, thời gian checkout tăng | Giảm concurrency DB, tối ưu query/transaction và điều chỉnh pool dựa trên DB |
| Remote API quá tải | 429, 503, tăng p99, reset kết nối | Tuân thủ quota, dùng giới hạn toàn cục, retry thận trọng với backoff/jitter |
| Downstream consumer chậm | Buffer operator/phản hồi tăng, RAM/GC tăng | Hạ prefetch/concurrency, propagate backpressure, giới hạn buffer |

Không xử lý mọi lỗi bằng cách tăng thread. Nếu bottleneck là DB với 10 connections và SQL chậm, tăng worker từ 20 lên 200 chỉ có thể tạo thêm rất nhiều người chờ DB.

## 7. Áp lực lên tài nguyên đích và phép tính năng lực đơn giản

### 7.1. Little's law cho concurrency trung bình

Trong hệ thống ổn định, định luật Little:

\[
L = \lambda \times W
\]

Với:

- `L`: số tác vụ trung bình đang ở trong phạm vi đo (có thể gồm chạy và chờ).
- `λ`: throughput trung bình, ví dụ request/giây.
- `W`: thời gian trung bình một tác vụ ở trong phạm vi đó, tính bằng giây.

Ví dụ một hệ thống xử lý ổn định **80 request/giây** và mỗi request mất trung bình **0,25 giây** trong đoạn gọi downstream: `L ≈ 80 × 0,25 = 20` request đang in-flight trong đoạn đó. Đây là **ước lượng trung bình**, không phải p95 hay cấu hình thread/pool chính xác. Để có headroom với burst, cần theo dõi phân phối và giới hạn thực tế.

Nếu downstream chỉ có 8 kết nối để xử lý thao tác **mỗi kết nối một yêu cầu trong 0,25 giây**, năng lực lý tưởng gần `8 / 0,25 = 32 yêu cầu/giây` trước khi tính overhead. Nếu đầu vào liên tục đến 40/giây, hàng đợi sẽ có xu hướng tăng vì nhu cầu vượt khả năng xử lý. Tăng queue chỉ trì hoãn biểu hiện quá tải.

Ví dụ này không áp dụng nguyên xi cho HTTP/2 multiplex hoặc các giao thức cho phép nhiều request trên một connection. Phải xác định **đơn vị công việc thực sự giới hạn tại tài nguyên đích**.

### 7.2. Sizing không phải chỉ nhìn CPU

CPU 20% không chứng minh còn đủ năng lực: request có thể đang chờ remote API, lock database, connection hoặc quota. Đánh giá tối thiểu:

- Thời gian service ở downstream (trung bình và p95/p99).
- Tổng số request in-flight, số pending acquire và thời gian chờ lấy connection.
- CPU, heap, GC, số thread và thời gian chạy/chờ của task scheduler.
- Số request thực tế đến API đích (bao gồm retry), lỗi 429/503/timeout.
- Thời gian nằm trong từng queue và tỷ lệ cancel khi client không còn chờ.

Một bottleneck CPU cần hướng xử lý khác với bottleneck network hay database. Khi latency tăng, dùng trace/metrics để định vị **đang chờ ở tầng nào** rồi mới chỉnh concurrency.

## 8. Giới hạn concurrency trong pipeline: hiệu quả và giới hạn của `flatMap`

```java
Flux<Order> orders = orderIds.flatMap(
        id -> orderClient.fetch(id),
        8 // tối đa 8 inner publishers đang hoạt động trong subscription này
);
```

Đây là snippet: `orderIds`, `orderClient` và `Order` phải được định nghĩa trong ứng dụng. Nếu `fetch(id)` trả `Mono<Order>` bắt đầu gọi HTTP khi subscribe:

- `flatMap` có thể subscribe tới **8** inner cùng lúc; khi một inner hoàn tất, nó có thể subscribe thêm một ID mới.
- Kết quả giữa các inner có thể xen kẽ và **không bảo đảm** thứ tự ID đầu vào.
- `8` là giới hạn **cho một subscription**. Nếu có 50 request HTTP đồng thời và mỗi request tạo một pipeline tương tự, ứng dụng có thể tạo nhiều lời gọi concurrent tới upstream.
- Nếu mỗi inner kích hoạt hai request con, concurrency của các request HTTP thật có thể lớn hơn số inner.
- `flatMap` không trực tiếp giới hạn số thread ở runtime hay số connections của `WebClient`.

Nếu cần giữ thứ tự ID, `flatMapSequential` cho phép subscribe sớm nhưng giữ output theo nhóm nguồn, với cái giá là **buffer** khi inner trước chậm. Nếu quy trình đòi hỏi bước sau chỉ chạy khi bước trước xong, `concatMap` subscribe inner lần lượt. Mỗi toán tử cho phép giới hạn áp lực theo một hợp đồng khác nhau.

Ví dụ `flatMap(mapper, 8, 16)` có thêm `prefetch=16`, chủ yếu điều chỉnh demand ban đầu trên **mỗi inner Flux**; nó không có nghĩa 16 request HTTP/giây. Với inner `Mono`, prefetch lớn thường ít tác dụng vì mỗi Mono tối đa một giá trị.

## 9. Chương trình Java 17+ chạy được: giới hạn inner và từ chối queue đầy

Ví dụ dưới đây dùng **Project Reactor Core 3.6.6** độc lập, không cần Spring Boot. Có hai phần:

1. Tạo 9 inner `Mono.delay` nhưng `flatMap(..., 3)` chỉ cho tối đa 3 inner active cùng lúc.
2. Tạo một scheduler **chỉ có 1 backing thread và 1 task chờ**. Chủ động giữ task đầu tiên bằng `CountDownLatch`, xếp task thứ hai, rồi thử xếp task thứ ba để quan sát `RejectedExecutionException`.

`CountDownLatch` giúp tạo tình huống queue đầy **có kiểm soát**, không cần hi vọng máy đang bận hay phụ thuộc vào timing ngẫu nhiên. Tất cả lệnh chờ trong ví dụ chạy trong ứng dụng console, **không đặt trên WebFlux event loop**.

### 9.1. Cấu trúc dự án

```text
reactor-resource-limits/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── edu/
                └── demo/
                    └── ResourceLimitsDemo.java
```

Tạo `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>edu.demo</groupId>
    <artifactId>reactor-resource-limits</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-core</artifactId>
            <version>3.6.6</version>
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
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Tạo `src/main/java/edu/demo/ResourceLimitsDemo.java`:

```java
package edu.demo;

import java.time.Duration;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Scheduler;
import reactor.core.scheduler.Schedulers;

public final class ResourceLimitsDemo {

    public static void main(String[] args) throws Exception {
        demonstrateInnerConcurrency();
        demonstrateBoundedTaskQueue();
    }

    private static void demonstrateInnerConcurrency() {
        AtomicInteger active = new AtomicInteger();
        AtomicInteger peak = new AtomicInteger();

        List<Integer> results = Flux.range(1, 9)
                .flatMap(id -> Mono.defer(() -> {
                    int running = active.incrementAndGet();
                    peak.accumulateAndGet(running, Math::max);

                    return Mono.delay(Duration.ofMillis(40))
                            .map(tick -> id)
                            .doOnTerminate(
                                    () -> active.decrementAndGet());
                }), 3)
                .collectList()
                .block(Duration.ofSeconds(5));

        if (results == null || results.size() != 9
                || peak.get() != 3 || active.get() != 0) {
            throw new IllegalStateException(
                    "Unexpected concurrency behavior");
        }

        System.out.println("received=" + results.size());
        System.out.println("peakInner=" + peak.get());
    }

    private static void demonstrateBoundedTaskQueue()
            throws InterruptedException {
        Scheduler scheduler =
                Schedulers.newBoundedElastic(1, 1, "legacy-lab");
        Scheduler.Worker worker = scheduler.createWorker();

        CountDownLatch firstStarted = new CountDownLatch(1);
        CountDownLatch releaseFirst = new CountDownLatch(1);
        CountDownLatch queuedCompleted = new CountDownLatch(1);
        AtomicBoolean queuedRan = new AtomicBoolean();

        try {
            worker.schedule(() -> {
                firstStarted.countDown();
                try {
                    releaseFirst.await();
                } catch (InterruptedException error) {
                    Thread.currentThread().interrupt();
                }
            });

            if (!firstStarted.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("First task not started");
            }

            // Thread is occupied: this task enters its bounded queue.
            worker.schedule(() -> {
                queuedRan.set(true);
                queuedCompleted.countDown();
            });

            boolean thirdRejected = false;
            try {
                worker.schedule(() -> {});
            } catch (RejectedExecutionException expected) {
                thirdRejected = true;
            }

            releaseFirst.countDown();

            if (!queuedCompleted.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Queued task not run");
            }
            System.out.println("thirdRejected=" + thirdRejected);
            System.out.println("queuedTaskRan=" + queuedRan.get());
        } finally {
            releaseFirst.countDown();
            worker.dispose();
            scheduler.dispose();
        }
    }
}
```

### 9.2. Chạy và đọc kết quả

Trong thư mục chứa `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=edu.demo.ResourceLimitsDemo
```

Kết quả tiêu chuẩn của ví dụ với Reactor Core 3.6.6:

```text
received=9
peakInner=3
thirdRejected=true
queuedTaskRan=true
```

Giải thích:

- `received=9`: cả chín inner đều có cơ hội chạy và hoàn tất.
- `peakInner=3`: giới hạn `flatMap(..., 3)` không cho hơn ba inner đang active trong ví dụ. `Mono.delay` dùng scheduler của Reactor, **không tạo riêng một thread cho từng Mono**.
- `thirdRejected=true`: có một thread đã bị task đầu tiên chiếm; một task khác chờ trong queue giới hạn một phần tử; task thứ ba bị từ chối. Đây là **giới hạn scheduled task**, không liên quan đến HTTP connection pool.
- `queuedTaskRan=true`: sau khi giải phóng task đầu tiên, task thứ hai có chỗ chạy.
- `scheduler.dispose()`: thu hồi scheduler riêng. Các bước cleanup không được bỏ qua khi áp dụng trong ứng dụng chạy dài hạn.

Các assert trong chương trình phù hợp với mô hình thử nghiệm chủ động khống chế queue. Trên máy thiếu tài nguyên, chương trình có thể phát lỗi do vượt timeout 5 giây dùng cho kiểm tra, không nên hiểu đó là thông lượng chuẩn của Reactor. Không xem ví dụ này là benchmark hiệu năng.

### 9.3. Biến thể cần tránh khi dùng WebFlux

Không đặt một task kiểu sau trực tiếp trên event loop:

```java
@GetMapping("/blocking")
Mono<String> blocking() {
    return Mono.fromCallable(() -> {
        Thread.sleep(500);
        return "blocked";
    });
}
```

`Mono.fromCallable` là một nguồn lazy, **nhưng chưa được chuyển scheduler**. Nếu bắt buộc dùng thư viện blocking, hãy đặt toàn bộ việc gọi trong `fromCallable` và dùng một scheduler phù hợp:

```java
@GetMapping("/legacy")
Mono<String> legacy() {
    return Mono.fromCallable(() -> {
        Thread.sleep(500); // Chỉ mô phỏng SDK blocking
        return "finished";
    }).subscribeOn(legacyScheduler);
}
```

Hai đoạn trên là **snippets** bên trong WebFlux controller đã có import `Mono` và `GetMapping`, cùng bean `legacyScheduler`. Không dùng `Thread.sleep` trong production; thay bằng API blocking thật nếu bắt buộc tích hợp và đo khả năng chịu tải. `.subscribeOn()` không biến lời gọi đó thành non-blocking: worker vẫn bị giữ trong 500 ms. Scheduler có giới hạn và khả năng từ chối khi đầy.

## 10. Giới hạn riêng cho HTTP client: connection pool và pending acquire

Một `WebClient` reactive vẫn cần kết nối mạng. Khi số lời gọi đồng thời cao hơn số connection sẵn có, nhiều request phải **đợi lấy connection**. Reactor Netty cho phép cấu hình pool:

```java
ConnectionProvider provider =
        ConnectionProvider.builder("reports-api")
                .maxConnections(16)
                .pendingAcquireMaxCount(32)
                .pendingAcquireTimeout(Duration.ofSeconds(2))
                .build();

HttpClient httpClient = HttpClient.create(provider)
        .responseTimeout(Duration.ofSeconds(3));

WebClient client = WebClient.builder()
        .baseUrl("https://reports.example")
        .clientConnector(
                new ReactorClientHttpConnector(httpClient))
        .build();
```

Đây là **snippet cấu hình Spring WebFlux**, cần các dependency Spring WebFlux/Reactor Netty và các import:

```java
import java.time.Duration;
import reactor.netty.http.client.HttpClient;
import reactor.netty.resources.ConnectionProvider;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;
```

URI `https://reports.example` chỉ là ví dụ, không phải server thật để chạy thử. Hãy tạo provider một lần theo vòng đời ứng dụng và đóng khi shutdown.

Ý nghĩa các tham số:

- `maxConnections(16)`: giới hạn số kết nối trong pool theo phạm vi pool của client/provider; không phải 16 thread Java. Với HTTP/2, một kết nối có thể phục vụ nhiều stream nên phải hiểu tính chất giao thức khi sizing.
- `pendingAcquireMaxCount(32)`: số lượt xin connection được giữ trong pending queue khi chưa cấp được; vượt ngưỡng có thể bị từ chối.
- `pendingAcquireTimeout(Duration.ofSeconds(2))`: thời gian tối đa một lần cấp connection có thể chờ.
- `responseTimeout(Duration.ofSeconds(3))`: giới hạn về **thời gian đọc response theo hành vi của HTTP client**, không đồng nghĩa deadline end-to-end bao gồm tất cả thời gian queue, DNS, connect, xử lý nghiệp vụ. Khi cần deadline toàn request, đặt ở tầng thích hợp nữa.

Với Reactor Netty, các giới hạn pool thường được áp dụng **theo pool key/đích** của connection provider; không nên coi số 16 là giới hạn tuyệt đối của mọi upstream host trong cả ứng dụng. Một `WebClient` cũng có thể chia sẻ provider/HTTP resources với nhiều client khác, nên cấu hình và phạm vi chia sẻ phải được xác định rõ.

### Ghép cùng giới hạn ở operator

Ví dụ service gọi một API cho mỗi ID:

```java
public Flux<Report> getReports(Flux<String> ids) {
    return ids.flatMap(id ->
                    reportClient.get()
                            .uri("/reports/{id}", id)
                            .retrieve()
                            .bodyToMono(Report.class)
                            .timeout(Duration.ofSeconds(4)),
            8);
}
```

Đây là **snippet tích hợp**, chưa tự chạy: cần có `reportClient` được cấu hình, class `Report`, import `Flux`, `Duration`. Mỗi subscription có tối đa tám inner đang xử lý, trong khi provider HTTP có thể cho nhiều requests từ **các subscription khác** cùng giành pool. Nếu client hỗ trợ retry, một inner có thể tạo thêm các lượt HTTP request theo thời gian; cần đo số attempt thực.

Không tự kết luận `flatMap(...,8)` cộng `maxConnections(16)` thành “tối đa 24 request”; các giới hạn nằm trên những lớp **khác nhau** và không cộng như vậy.

## 11. Giới hạn trên database, transaction và upstream service

### 11.1. Database pool

Một ứng dụng truy cập JDBC/JPA thường có connection pool (chẳng hạn HikariCP). Nếu pool có 10 connection, tạo 100 tác vụ JDBC đồng thời không làm database tự có 100 connection. Các task dư có thể **chờ lấy connection**, gây thêm latency và có nguy cơ timeout.

Ví dụ cấu hình HikariCP trong ứng dụng Spring Boot dùng JDBC/JPA:

```yaml
spring:
  datasource:
    hikari:
      maximum-pool-size: 10
      connection-timeout: 2000
```

Đây là **snippet cấu hình**, không phải ứng dụng đầy đủ. Tên thuộc tính áp dụng khi dùng HikariCP; `connection-timeout` là thời gian tối đa chờ lấy connection từ pool, không phải thời gian SQL được phép chạy. Giá trị `2000` là mili giây; pool size chỉ là một thông số trong tổng khả năng chịu tải của database.

Với WebFlux, JDBC là blocking API. Nếu buộc dùng, cần cách ly khỏi event loop như mục 5 nhưng vẫn **khống chế mức công việc đi xuống JDBC**; tăng thread boundedElastic vô tội vạ chỉ tạo thêm thời gian đợi pool. Nếu pipeline cần non-blocking end-to-end, cân nhắc R2DBC cùng các driver và transaction reactive, đồng thời cấu hình connection pool tương ứng.

### 11.2. Remote service có quota

Giả sử đối tác giới hạn 100 request/giây. Dù service của ta chỉ tạo 8 request đồng thời, nếu mỗi request hoàn tất trong 20 ms thì tốc độ phát request có thể rất cao. **Concurrency cap không phải rate limit theo thời gian.**

Cần phân biệt:

- Concurrency: có bao nhiêu request đang hoạt động cùng lúc?
- Rate: trong một giây có bao nhiêu attempt được gửi?
- Retry: một yêu cầu nghiệp vụ có tạo thêm attempt không?
- Queue depth: có bao nhiêu việc đang đợi?
- Deadline: bao lâu caller còn quan tâm đến kết quả?

Tại ranh giới upstream, có thể cần **cả concurrency limit, rate limiter và timeout**. Với HTTP 429, tôn trọng chính sách `Retry-After` nếu có và nghiệp vụ cho phép; chỉ retry lệnh idempotent hoặc có khóa idempotency đúng nghĩa. Retry dồn dập khi upstream quá tải có thể tạo **retry storm**.

### 11.3. Bulkhead theo dependency

Một service dùng cả hệ thống tra cứu và hệ thống thanh toán nên tách giới hạn để upstream tra cứu bị chậm không chiếm hết tài nguyên xử lý thanh toán. Có thể phân chia client pool, scheduler cho blocking SDK và admission limit theo dependency.

Tên gọi kiến trúc thường dùng là **bulkhead**: các nhóm công việc có giới hạn riêng để một nơi bão hòa không kéo toàn bộ hệ thống bão hòa theo. Không nhất thiết xây dựng từ thread pool mới cho mọi thứ; với WebClient non-blocking, bulkhead dựa trên **số request in-flight**, client pool hoặc limiter có thể phù hợp hơn.

## 12. Hàng đợi, deadline và chính sách từ chối

### 12.1. Vì sao bounded queue tốt hơn chờ vô hạn?

Nếu nguồn đích xử lý tối đa 40 tác vụ/giây và lượng công việc đến ổn định 60/giây, backlog tăng khoảng **20 tác vụ/giây** (bỏ qua overhead). Sau 10 giây, backlog có thể tăng khoảng 200 tác vụ. Giữ queue vô hạn khiến ngày càng nhiều request đã hết giá trị nhưng vẫn được nhận. Khi queue đầy, phản hồi quá tải **có kiểm soát** có thể tốt hơn nhận thêm việc không thể hoàn tất đúng hạn.

Có các cách xử lý quá tải tùy ngữ cảnh:

- **Fail fast**: từ chối ngay khi đã hết số slot/queue; ánh xạ lỗi sang phản hồi HTTP hợp lý (thường 503, có thể kèm `Retry-After` phù hợp).
- **Đợi tối đa một khoảng thời gian ngắn**: pending acquire timeout hoặc bounded wait.
- **Giảm tải**: hạn chế nhận công việc ở ingress, chuyển xử lý thành hàng đợi durable nếu nghiệp vụ chấp nhận kết quả bất đồng bộ.
- **Giảm tốc nguồn**: tận dụng backpressure nếu upstream thực sự có thể phản ứng với demand.
- **Loại bỏ việc đã hết hạn**: kiểm tra cancellation/deadline để không chạy một tác vụ không còn cần thiết.

Các giới hạn này phải phản ánh **SLO và mục tiêu nghiệp vụ**, không chỉ kích thước heap của máy.

### 12.2. `onBackpressureBuffer` không phải hàng đợi vạn năng

```java
Flux<Event> buffered = events.onBackpressureBuffer(256);
```

Đây là snippet, cần có `Flux<Event>` nguồn. Biểu thức này thêm buffer có giới hạn 256 phần tử ở ranh giới backpressure; khi không còn chỗ, hành vi lỗi/overflow tùy overload. Nó **không** tự giảm số lời gọi HTTP đã bắt đầu, không giới hạn SQL đang chạy và không thay connection pool. Với nguồn nóng phát không ngừng, cần chính sách overflow và giám sát rõ ràng. Không dùng `onBackpressureBuffer()` không tham số một cách vô thức trong đường tải cao vì có nguy cơ bộ nhớ tăng mạnh.

### 12.3. Timeout không thay thế cancellation tài nguyên thật

Trong Reactor:

```java
Mono<String> answer = remoteCall
        .timeout(Duration.ofSeconds(2));
```

Đây là snippet với `remoteCall` đã có. Nếu không nhận được tín hiệu phù hợp trước timeout, `timeout` phát lỗi và hủy upstream subscription theo khả năng của operator. Tuy nhiên, **một SDK blocking không hỗ trợ interrupt/cancellation có thể tiếp tục làm việc** ngay cả khi caller đã bỏ cuộc. Vì vậy phải cấu hình timeout ở chính HTTP/DB/SDK client và giữ giới hạn thread/queue.

Với `Flux` nhiều phần tử, `.timeout(Duration)` mặc định đo **khoảng chờ giữa các tín hiệu `onNext`** (và từ subscribe đến tín hiệu đầu tiên); nó không tự là deadline toàn bộ stream. Cần phân biệt idle timeout, connect timeout, acquire timeout và overall deadline.

## 13. Quan sát sức khỏe dưới tải thay vì chỉ nhìn số thread

Khi hệ thống chậm, câu hỏi đầu tiên là: **thời gian đang bị mất ở bước nào?** Các nhóm số liệu nên thu thập:

| Vị trí | Số liệu đáng quan sát | Ý nghĩa |
|---|---|---|
| HTTP ingress | Requests/s, in-flight, p50/p95/p99, 4xx/5xx | Tải đầu vào và chất lượng đáp ứng |
| Reactor Netty event loop | Event-loop blocked time, CPU/thread diagnostics | Xác định blocking trên luồng mạng |
| Scheduler riêng | Active/running tasks, pending queue, rejected tasks | Biết thread cap hay queue cap đang chạm |
| WebClient connection pool | Connections active/idle, pending connections, acquire timeout | Định vị áp lực chờ connection |
| Database pool | Active/idle/pending connections, checkout wait | Xác định DB pool bottleneck |
| Upstream API | 429, 503, latency, retry attempt, timeout | Xác định khả năng chịu tải của đích |
| Memory | Heap, GC pause, queue size, retained objects | Phát hiện buffer/queue tăng không kiểm soát |

Micrometer và Spring Boot Actuator có thể hỗ trợ đo nhiều loại metric tùy thư viện/phiên bản và cấu hình bật metrics. **Tên metric thực tế cần kiểm tra trong ứng dụng**, không giả định mọi scheduler và pool luôn tự xuất metric.

Gắn trace giữa các lớp để tách các khoảng:

```text
Request total latency
    = ingress queue/wait (nếu có)
    + chờ worker/scheduler (nếu có)
    + chờ connection
    + I/O/service time ở upstream
    + xử lý response
    + thời gian khác
```

Đây là sơ đồ phân rã mang tính chẩn đoán; không phải công thức cộng chính xác cho các giai đoạn chạy song song. Với fan-out nhiều inner, các nhánh có thể overlap.

### Dùng log scheduler đúng cách

`doOnSubscribe`, `doOnRequest`, `doOnCancel`, `doFinally` giúp quan sát vòng đời reactive:

```java
Mono<String> traced = remoteCall
        .doOnSubscribe(s -> logger.debug("remote subscribed"))
        .doFinally(signal -> logger.debug("remote finished: {}", signal));
```

Đây là snippet: `remoteCall` và `logger` cần có sẵn. `doFinally` có thể nhận `ON_COMPLETE`, `ON_ERROR`, `CANCEL`; cancellation không có nghĩa upstream đã ngừng công việc vật lý ngay lập tức. Với chương trình thực, ưu tiên metrics/tracing có kiểm soát thay vì ghi log mỗi phần tử gây quá tải.

## 14. Quy trình xác định giới hạn an toàn

Một quy trình có thể áp dụng khi điều chỉnh production:

1. **Xác định nguồn bottleneck**: CPU, thread blocking, DB connection, HTTP pool, quota hay upstream latency.
2. **Định nghĩa phạm vi**: giới hạn theo một inner, một subscription, một HTTP client, một service instance hay toàn hệ thống?
3. **Đặt giới hạn trước khi phát sinh công việc**: dùng `flatMap` concurrency, pool limit hoặc admission control ở tầng thích hợp. Đừng đợi queue downstream đầy rồi mới phát hiện quá tải.
4. **Đặt queue bound và timeout**: mỗi đoạn đợi quan trọng có giới hạn về số phần tử và thời gian, đi cùng chính sách từ chối.
5. **Cách ly dependency xấu**: scheduler riêng cho SDK blocking hoặc pool/limiter riêng cho upstream có quota; không cấp thêm thread vô hạn.
6. **Bảo đảm hủy và cleanup**: request bị ngắt phải giải phóng subscription, connection/tài nguyên theo hỗ trợ của thư viện.
7. **Kiểm thử tải có burst và lỗi**: thêm trường hợp upstream chậm, timeout, connection pool đầy, response lớn, client cancel và retry storm.
8. **Đo trước/sau**: throughput, latency tail, pending queue, rejected/timeout, heap và tải thật trên upstream.
9. **Điều chỉnh từng lớp một**: ví dụ concurrency 4→8 với pool/queue giữ nguyên; không tăng mọi giới hạn cùng lúc vì không thể biết nguyên nhân cải thiện hoặc suy giảm.
10. **Giữ headroom và bảo vệ upstream**: cấu hình tốt là cấu hình ổn định dưới tải kỳ vọng và có cách xử lý quá tải minh bạch, chứ không chỉ có p50 thấp khi chạy một request.

### Một bảng lựa chọn thực tế

| Tình huống | Cách ưu tiên |
|---|---|
| CPU-bound transform trên dữ liệu đã có | Giới hạn theo số core, cân nhắc scheduler CPU và cách chia công việc |
| WebClient non-blocking gọi nhiều API độc lập | `flatMap` concurrency vừa phải + HTTP pool + timeout/quota |
| JDBC/SDK blocking bắt buộc tích hợp | `fromCallable` + boundedElastic riêng + giới hạn tác vụ/DB pool |
| Nguồn nóng tạo dữ liệu nhanh hơn tiêu thụ | Backpressure hoặc overflow policy, buffer có giới hạn |
| Cần giữ thứ tự nhóm nguồn | `concatMap` hoặc `flatMapSequential`, giám sát buffering |
| Upstream trả 429 khi tải tăng | Điều tiết request rate, giảm concurrency, retry có backoff có điều kiện |
| Nhiều request đã timeout vẫn nằm trong queue | Giảm queue, đặt deadline/cancellation và admission control |
| Heap tăng khi load test | Kiểm tra queue nhiều tầng, prefetch, kích thước payload, retained objects |

## 15. Các hiểu lầm phổ biến

| Hiểu lầm | Cách hiểu đúng |
|---|---|
| “WebFlux không cần thread” | Vẫn có event-loop và các worker; tối ưu là không giữ thread để chờ I/O non-blocking. |
| “`Mono.fromCallable` tự chuyển blocking code sang thread khác” | Phải chọn scheduler với `subscribeOn`/cơ chế thực thi thích hợp. |
| “`boundedElastic` là vô hạn” | Reactor Core có giới hạn thread và hàng đợi; khi đầy có thể reject. |
| “Tăng số thread là tăng tốc mọi API” | Nếu đích bị giới hạn connection/quota/CPU, thêm thread chỉ làm tăng chờ và áp lực. |
| “`flatMap(..., 8)` bảo đảm toàn server chỉ 8 HTTP calls” | Giới hạn inner active **trên một subscription**, còn nhiều subscriber/inner khác. |
| “`maxConnections(16)` bằng 16 requests hoặc 16 threads” | Là giới hạn connection trong pool; HTTP/2 có thể multiplex; không phải số thread. |
| “Prefetch 32 là 32 request/giây” | Prefetch là demand phần tử tại ranh giới operator, không phải rate limit. |
| “Queue càng lớn càng ít lỗi” | Có thể làm queueing latency, bộ nhớ và timeout tăng; nhiều việc không còn giá trị. |
| “Response timeout bao gồm mọi bước chờ của request” | Acquire/connect/response/overall deadline là các giới hạn khác nhau. |
| “Timeout bảo đảm mọi tác vụ đã dừng” | Cancellation phụ thuộc client/SDK, blocking code có thể tiếp tục. |
| “CPU thấp nghĩa là server chưa quá tải” | Có thể đang chờ DB, connection, remote API hoặc lock. |
| “Virtual threads làm pool DB lớn hơn” | Virtual thread giảm chi phí thread trong nhiều trường hợp; DB pool vẫn hữu hạn. |
| “Retry sẽ tự xử lý quá tải” | Retry sai cách có thể khuếch đại số attempt và làm downstream sụp nhanh hơn. |
| “`publishOn(parallel())` tự chạy mỗi phần tử trên một core” | Nó đổi ranh giới scheduler; không tự thêm concurrency cho từng inner. |
| “Backpressure trong Flux đủ bảo vệ mọi dịch vụ ngoài” | Giao thức/driver/call site có thể không phản ứng với demand; cần cap và queue riêng. |

## 16. Câu hỏi và bài tập tự đánh giá

**Bài 1.** Một endpoint có `flatMap(..., 5)` và cùng lúc có 30 request HTTP, mỗi request tạo một subscription riêng. Có bảo đảm cả service chỉ gọi tối đa 5 API đích cùng lúc không?

**Đáp án:** Không. `5` giới hạn inner active trong **mỗi subscription**. Nhiều subscription có thể tạo tải cộng dồn; cần thêm giới hạn theo client/pool hoặc cơ chế chia sẻ toàn service.

**Bài 2.** Một SDK blocking mất 500 ms, chạy trên boundedElastic cap 4 thread. Giới hạn lý tưởng về số SDK call hoàn tất/giây trong môi trường không có overhead và không tăng pool là bao nhiêu?

**Đáp án:** Nếu mỗi call chiếm một thread đủ 0,5 giây, giới hạn xấp xỉ `4 / 0,5 = 8 call/giây`. Queue lớn không nâng giới hạn bền vững này. Nếu SDK có điểm tranh chấp hoặc DB đích chậm, throughput có thể thấp hơn.

**Bài 3.** `Schedulers.newBoundedElastic(2, 10, "x")` có chắc tạo 20 HTTP connection không?

**Đáp án:** Không. Nó có cap 2 backing threads và queue cap task chờ trên mỗi backing thread; connection pool HTTP là một cơ chế riêng.

**Bài 4.** Một API đã có pool 10 connection, latency DB tăng cao và nhiều thread đang chờ connection. Nên tăng boundedElastic thread lên 100 ngay không?

**Đáp án:** Không nên làm mù quáng. Đo wait time, SQL latency, giới hạn DB, xử lý transaction và mức concurrency gửi tới DB; giảm đầu vào hoặc tối ưu query có thể hiệu quả hơn thêm người chờ pool.

**Bài 5.** Vì sao `.timeout(Duration.ofSeconds(3))` trên một `Flux` streaming không bảo đảm stream đóng sau tổng cộng ba giây?

**Đáp án:** Vì overload này kiểm soát khoảng **im lặng giữa các tín hiệu**, có thể tiếp tục nếu upstream cứ phát phần tử đúng hạn. Overall deadline là bài toán khác.

**Bài 6.** Một service bị HTTP 429, khi tăng concurrency từ 10 lên 50 tỷ lệ lỗi tăng. Có nên tăng tiếp concurrency không?

**Đáp án:** Không. 429 thường cho biết giới hạn từ upstream. Cần kiểm tra quota/rate limit, giảm tải, dùng retry thận trọng với backoff/jitter và theo dõi số attempt thực tế.

**Bài 7.** Queue scheduler và pending-acquire queue HTTP có cùng ý nghĩa không?

**Đáp án:** Không. Queue scheduler giữ tác vụ chưa được worker thực thi; pending acquire giữ yêu cầu lấy kết nối chưa được cấp. Một request có thể đi qua cả hai và phải có deadline ở đúng tầng.

**Bài 8.** Khi nào nên có `newBoundedElastic` riêng thay vì mọi lời gọi blocking dùng `boundedElastic()` toàn cục?

**Đáp án:** Khi một dependency blocking có đặc tính chậm, quota hoặc rủi ro quá tải riêng và cần **cô lập số worker/queue**, để nó không cạnh tranh vô hạn với các tác vụ blocking khác. Cần tái sử dụng instance và dispose lúc shutdown.

## 17. Kết luận

Đối với luồng thực thi trong Spring WebFlux, điều khiển tài nguyên là một chuỗi giới hạn nối tiếp nhau:

1. **Thread/scheduler cap** xác định số tác vụ blocking/CPU có thể chạy trên nhóm worker.
2. **Concurrency cap** xác định số inner công việc được phép khởi động đồng thời trong một pipeline.
3. **Queue cap và timeout** xác định lượng việc được phép chờ và thời gian caller còn chấp nhận.
4. **Connection pool, quota và năng lực downstream** xác định có thể thực hiện bao nhiêu công việc thật tại tài nguyên đích.

Hãy đo **nút thắt thực tế** và áp các giới hạn ở đúng phạm vi. WebFlux có thể tiết kiệm thread khi chờ I/O non-blocking, nhưng không làm mất các giới hạn vật lý của dịch vụ đích. Một hệ thống ổn định cần biết **khi nào phải giảm tốc, đợi ngắn, từ chối sớm hoặc hủy**, chứ không chỉ biết tăng concurrency.

## Tài liệu chính thức

- Project Reactor, **Schedulers API (3.6.6)**, bao gồm `boundedElastic`, `newBoundedElastic` và giới hạn queue/thread: https://docs.spring.io/projectreactor/reactor-core/docs/3.6.6/api/reactor/core/scheduler/Schedulers.html
- Project Reactor, **Threading and Schedulers**: https://projectreactor.io/docs/core/3.6.6/reference/coreFeatures/schedulers.html
- Project Reactor, **Backpressure and Ways to Reshape Requests**: https://projectreactor.io/docs/core/3.6.6/reference/
- Reactor Netty, **HTTP Client – Connection Pool**: https://projectreactor.io/docs/netty/release/reference/http-client.html
- Spring Framework, **WebFlux**: https://docs.spring.io/spring-framework/reference/web/webflux.html
- Spring Framework, **WebClient**: https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html
- Reactive Streams, **JVM Specification**: https://www.reactive-streams.org/