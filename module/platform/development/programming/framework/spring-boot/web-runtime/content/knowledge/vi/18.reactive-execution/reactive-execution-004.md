# Chuyển tác vụ chặn luồng sang Scheduler có giới hạn trong Spring WebFlux

## 1. Mục tiêu: giữ event loop thông thoáng khi phải dùng API blocking

Trong Spring WebFlux, server thường nhận request trên một số lượng nhỏ **event-loop threads** (ví dụ các luồng `reactor-http-nio-*` của Reactor Netty). Những luồng này được thiết kế để thực hiện tác vụ ngắn, phối hợp I/O bất đồng bộ và xử lý tín hiệu reactive. Nếu một request gọi `Thread.sleep(...)`, JDBC/JPA đồng bộ, HTTP client blocking, thao tác file blocking hoặc `Future.get()` trực tiếp trên event loop, luồng đó phải **đứng chờ**. Nhiều request khác dùng chung event loop có thể cùng bị chậm.

Giải pháp khi **chưa thể thay API blocking** là cô lập đoạn đồng bộ thành một publisher lạnh (cold publisher), rồi chuyển **việc thực thi đoạn blocking** sang `Scheduler` có giới hạn. Mẫu chuẩn của Project Reactor là:

```java
Mono<Result> result = Mono.fromCallable(() -> legacyService.load())
        .subscribeOn(Schedulers.boundedElastic());
```

Đây là **mẫu minh họa**, chưa phải chương trình độc lập: `Result` và `legacyService` do ứng dụng cung cấp. Bản chất:

1. `Mono.fromCallable(...)` **trì hoãn** lời gọi `legacyService.load()` cho đến khi có subscriber.
2. `subscribeOn(...)` chuyển việc subscribe và thực thi nguồn `Callable` sang worker của `boundedElastic()`.
3. Trong lúc lời gọi blocking chạy, thread của scheduler vẫn **bị chiếm**, nhưng event loop không phải chờ nó.
4. Khi có kết quả/lỗi, Reactor phát tín hiệu `onNext`/`onComplete` hoặc `onError` tới pipeline.

**Giới hạn của kỹ thuật:** nó không biến JDBC, JPA hoặc thư viện blocking thành I/O non-blocking, không làm lệnh gọi ngoại vi nhanh hơn, không tạo vô hạn khả năng chịu tải. Nó chỉ **cô lập nơi bị chặn** và đặt giới hạn lên tài nguyên thực thi để bảo vệ các luồng reactive khác.

## 2. Thế nào là blocking, non-blocking và scheduler?

### 2.1. Blocking call

Một blocking call giữ thread đợi cho đến khi có kết quả/timeout/lỗi, chẳng hạn:

```java
String readLegacy() throws InterruptedException {
    Thread.sleep(200); // Mô phỏng I/O đồng bộ; không dùng sleep làm I/O production.
    return "done";
}
```

Nếu gọi `readLegacy()` trong `map(...)` đang chạy trên `reactor-http-nio-*`, thread HTTP ấy bị chặn 200 ms. Với hoạt động thật như `jdbcTemplate.query(...)`, thời gian chặn có thể phụ thuộc kết nối DB, khóa, timeout và tải downstream.

### 2.2. Non-blocking reactive publisher

`Mono<T>` mô tả một chuỗi phát **0 hoặc 1** giá trị; `Flux<T>` mô tả **0 đến nhiều** giá trị. Publisher không tự bảo đảm non-blocking: nếu code bên trong gọi thư viện đồng bộ thì vẫn có blocking.

`Mono.just(value)` chỉ giữ giá trị đã được tính. Vì biểu thức đối số được Java đánh giá trước, `Mono.just(readLegacy())` sẽ chạy blocking **ngay lúc tạo Mono**, có thể trước `subscribeOn`.

`Mono.fromCallable(...)` tạo publisher lạnh: mỗi subscription kích hoạt lại một lần gọi `Callable`, trừ khi có cơ chế cache/share khác. Sự trì hoãn này là yếu tố bắt buộc để chuyển blocking call đúng thread.

### 2.3. Scheduler là gì?

`Scheduler` của Reactor cung cấp khả năng lên lịch thực thi cho các operator như `subscribeOn` và `publishOn`. Nó quản lý `Worker`, task queue và thread/executor tương ứng; nó **không phải HTTP server** và không phải database connection pool.

| Scheduler | Mục đích phổ biến | Có hợp để chạy blocking I/O? |
| --- | --- | --- |
| `Schedulers.immediate()` | Chạy ngay trên thread hiện tại | Không giải quyết blocking |
| `Schedulers.single()` | Một luồng dùng chung cho việc nhanh, tuần tự | Không; một lần chặn ảnh hưởng các việc khác |
| `Schedulers.parallel()` | Công việc ngắn, CPU-bound, không blocking | **Không**; có thể báo lỗi khi dùng API `block()` trên non-blocking thread, và blocking code vẫn gây nghẽn |
| `Schedulers.boundedElastic()` | Tác vụ blocking dài hơn; thread/queue được giới hạn | **Có**; phương án chuyển tiếp khuyến nghị |
| `Schedulers.newBoundedElastic(...)` | Pool riêng có giới hạn do ứng dụng đặt | **Có**; phù hợp cách ly một integration blocking |

Không dùng `Schedulers.parallel()` để chạy JDBC hoặc `Thread.sleep` chỉ vì tên “parallel”. Nó phục vụ công việc tính toán không chặn luồng, không phải nguồn thread I/O vô hạn.

## 3. Cơ chế và giới hạn của `boundedElastic()`

`Schedulers.boundedElastic()` trả về **scheduler dùng chung** của Reactor, thích hợp để offload các lệnh blocking. Trong cấu hình mặc định của nhiều phiên bản Reactor 3.6–3.8 chạy trên platform threads:

- Có giới hạn số luồng nền, mặc định **10 × số processor khả dụng** (tại thời điểm khởi tạo scheduler).
- Khi thiếu luồng trống, task có thể **được đưa vào queue**. Giới hạn mặc định là khoảng **100.000 task đang chờ trên mỗi backing thread**, không phải 100.000 cho toàn bộ ứng dụng.
- Khi vượt giới hạn queue, scheduler **từ chối lập lịch** bằng lỗi, thường liên quan `RejectedExecutionException`.
- Thread có thể được tái sử dụng và các thread idle được thu hồi sau thời gian rảnh; scheduler dùng chung thường sống cùng ứng dụng.

Các giá trị trên là **mặc định của phiên bản Reactor**, có thể cấu hình và thay đổi giữa các phiên bản; không lấy chúng làm SLA. Các system properties liên quan gồm:

```properties
reactor.schedulers.defaultBoundedElasticSize=40
reactor.schedulers.defaultBoundedElasticQueueSize=1000
```

Đây là **system properties của JVM**, không mặc nhiên tương đương đặt hai dòng trong `application.properties` của Spring Boot. Nếu cần chúng, truyền dạng `-D...` trước khi Reactor khởi tạo shared scheduler, hoặc cấu hình JVM/container tương ứng:

```bash
java -Dreactor.schedulers.defaultBoundedElasticSize=40 \
     -Dreactor.schedulers.defaultBoundedElasticQueueSize=1000 \
     -jar app.jar
```

Ví dụ lệnh trên dành cho shell hỗ trợ nối dòng bằng `\` (Linux/macOS). Đổi các giới hạn chỉ sau khi đo tải và xem giới hạn connection pool/CPU/memory của downstream. Tăng queue rất lớn không giúp database xử lý nhanh hơn; nó có thể giữ request lâu, tăng bộ nhớ và độ trễ.

### Vì sao có queue nhưng vẫn phải giới hạn request?

Giả sử pool thực thi cùng lúc 4 tác vụ blocking, mỗi tác vụ mất 2 giây. Nếu 500 request đến cùng lúc, chỉ một số ít chạy ngay; phần còn lại phải đợi. Hàng đợi càng dài, thời gian phản hồi cuối đợt càng tệ. Vì thế:

- Giới hạn **số task đồng thời** tại tác vụ/kênh xử lý;
- Đặt **timeout thực** trong thư viện HTTP/DB/SDK blocking;
- Có chính sách **từ chối hoặc giảm tải** khi queue đầy;
- Giám sát cả scheduler, nguồn blocking và số request đang chờ.

Đặt `threadCap=4` cho một scheduler riêng **không có nghĩa toàn bộ endpoint chỉ nhận tối đa 4 request**; request dư có thể vào queue nếu còn chỗ. Phải phân biệt số tác vụ đang chạy với số tác vụ được chấp nhận vào hàng chờ.

### Java 21+ và virtual threads

Từ Reactor 3.6, `boundedElastic()` có thể dùng kiểu thread-per-task với **virtual threads** khi chạy JVM Java 21+ và bật system property:

```text
-Dreactor.schedulers.defaultBoundedElasticOnVirtualThreads=true
```

Chế độ này khác bản platform-thread pool: từng task có thể dùng một virtual thread, nhưng scheduler vẫn có giới hạn mức đồng thời/queue. Virtual threads **không bỏ giới hạn kết nối DB, connection pool, rate limit hay bộ nhớ**; blocking do native code hoặc pinning còn cần được đánh giá. Ví dụ Java 17 phía dưới dùng platform threads để dễ tái hiện.

## 4. Mẫu chuẩn: bọc call blocking rồi dùng `subscribeOn`

```java
public Mono<User> findUser(long userId) {
    return Mono.fromCallable(() -> legacyUserDao.findById(userId))
            .subscribeOn(Schedulers.boundedElastic());
}
```

Đây là **minh họa service**, với `User`/`legacyUserDao` được khai báo ở dự án thực. Giải thích:

1. Lambda truyền vào `fromCallable` là nơi đặt **toàn bộ đoạn đồng bộ** cần cô lập.
2. `subscribeOn` ở ngay sau source làm rõ ranh giới thread.
3. Khi WebFlux subscribe để phục vụ HTTP, callable được thực hiện bởi `boundedElastic`.
4. Exception do `Callable` ném được chuyển thành tín hiệu `onError`; không cần tự `try/catch` rồi giấu lỗi.
5. Nếu callable trả về `null`, `Mono.fromCallable` **hoàn thành rỗng** (không phát `onNext`), có thể gây kết quả HTTP không mong muốn; kiểm tra semantics “không tìm thấy” và xử lý rõ.

Đối với thao tác blocking chỉ có side effect và không trả dữ liệu:

```java
Mono<Void> update = Mono.fromRunnable(() -> legacyAudit.write("saved"))
        .subscribeOn(Schedulers.boundedElastic())
        .then();
```

Đây là đoạn minh họa, `legacyAudit` được ứng dụng cung cấp. `Mono.fromRunnable` phát completion/error; `then()` biểu đạt rõ chỉ quan tâm hoàn tất.

## 5. `subscribeOn` và `publishOn`: khác biệt quyết định việc offload

Cả hai đều đổi execution context nhưng ở vị trí và hướng khác nhau:

- **`subscribeOn(scheduler)`**: lên lịch quá trình subscribe đến **nguồn** (upstream); với `Mono.fromCallable`, điều này đưa chính blocking callable sang scheduler. Vị trí ở ngay sau source thường dễ hiểu nhất.
- **`publishOn(scheduler)`**: chuyển **các tín hiệu từ đoạn trước** sang scheduler, để các operator **phía sau** chạy ở đó. Nó không quay ngược thời gian để di chuyển một lời gọi blocking đã xảy ra.

Sơ đồ:

```text
ĐÚNG:        fromCallable(() -> BLOCKING)
                  |
             subscribeOn(boundedElastic)
                  |
                map(...)

SAI:          just(BLOCKING())  --> publishOn(boundedElastic)
                    ^
                 đã chạy trước khi lập Mono

SAI:          fromCallable(() -> BLOCKING)
                  |
             publishOn(boundedElastic)
                  ^
              source đã chạy ở thread upstream khi bị subscribe
```

Nếu **bắt buộc** chạy một phép biến đổi blocking nằm trong `map`, có thể đặt `publishOn` **trước** phép biến đổi ấy:

```java
Mono<String> migrated = input
        .publishOn(Schedulers.boundedElastic())
        .map(value -> legacyFormatter.format(value));
```

Đoạn này chỉ là minh họa, `input` là một `Mono` đã tồn tại, `legacyFormatter` là API blocking. `publishOn` trước `map` khiến callback `format` chạy trong scheduler. Tuy vậy, **bọc chính call blocking thành `Mono.fromCallable(...).subscribeOn(...)` thường rõ hơn**, nhất là khi pipeline có nhiều bước bất đồng bộ hoặc phải quản lý từng API blocking riêng biệt.

### Những đoạn trông giống đúng nhưng thực ra sai

**Sai 1 — đánh giá sớm trước khi offload:**

```java
// blockingCall() đã chạy ngay trên thread đang xây pipeline.
return Mono.just(blockingCall())
        .subscribeOn(Schedulers.boundedElastic());
```

**Đúng:**

```java
return Mono.fromCallable(() -> blockingCall())
        .subscribeOn(Schedulers.boundedElastic());
```

**Sai 2 — gọi API blocking ngay trong `map` trên event loop:**

```java
return requestMono.map(value -> blockingClient.lookup(value));
```

**Đúng — cô lập từng giá trị:**

```java
return requestMono.flatMap(value ->
        Mono.fromCallable(() -> blockingClient.lookup(value))
                .subscribeOn(Schedulers.boundedElastic()));
```

**Sai 3 — dùng `.block()` trong handler rồi nghĩ đã chuyển thành reactive:**

```java
@GetMapping("/item")
public String item() {
    return reactiveClient.getItem().block();
}
```

Nếu chạy trên event loop/non-blocking thread, `block()` có thể ném `IllegalStateException` vì Reactor cấm blocking trên những thread được đánh dấu `NonBlocking`. Trường hợp khác, nó vẫn chiếm thread chờ và phá lợi ích reactive. Handler WebFlux nên **trả về `Mono`/`Flux`**, để runtime subscribe.

**Sai 4 — tự `.subscribe()` bên trong controller:**

```java
@GetMapping("/item")
public Mono<String> item() {
    fetch().subscribe(System.out::println);
    return Mono.just("ok");
}
```

`subscribe()` thủ công tạo tác vụ tách rời lifecycle HTTP, làm mất lan truyền lỗi/cancellation và có thể trả “ok” trước khi việc chính hoàn tất. Hãy **trả pipeline** cho framework, không subscribe để “khởi động chạy nền”.

## 6. Ví dụ Spring Boot WebFlux chạy được với Java 17+

Ví dụ này mô phỏng integration cũ dùng lệnh blocking `Thread.sleep`, rồi offload trên scheduler riêng có **giới hạn 4 thread và queue cap 20 task trên mỗi backing thread**. Ví dụ dùng **Spring Boot 3.5.16** đã phát hành, với API Reactor tương thích. Project thực tế nên chọn phiên bản Boot đang được hỗ trợ phù hợp môi trường.

Tạo cấu trúc:

```text
offload-demo/
├── pom.xml
└── src/main/java/com/example/offload/OffloadDemoApplication.java
```

### 6.1. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>offload-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

Đây là POM hoàn chỉnh cho Maven; không cần khai báo phiên bản Reactor riêng vì Spring Boot BOM quản lý dependency phù hợp. **Không thêm `spring-boot-starter-web` vào ví dụ**, vì khi đồng thời có MVC và WebFlux trên classpath Boot thường chọn web application type Servlet.

### 6.2. `OffloadDemoApplication.java`

```java
package com.example.offload;

import java.util.List;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Scheduler;
import reactor.core.scheduler.Schedulers;

@SpringBootApplication
public class OffloadDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(OffloadDemoApplication.class, args);
    }

    // Scheduler riêng cho API legacy; khi đóng context, Spring gọi dispose().
    @Bean(name = "legacyIoScheduler", destroyMethod = "dispose")
    Scheduler legacyIoScheduler() {
        return Schedulers.newBoundedElastic(4, 20, "legacy-io");
    }
}

@RestController
class LegacyController {

    private final Scheduler legacyIoScheduler;

    LegacyController(@Qualifier("legacyIoScheduler") Scheduler legacyIoScheduler) {
        this.legacyIoScheduler = legacyIoScheduler;
    }

    @GetMapping("/legacy/{id}")
    Mono<String> one(@PathVariable long id) {
        return lookup(id);
    }

    @GetMapping("/batch")
    Mono<List<String>> batch() {
        // Mỗi request /batch cho phép tối đa 2 lookup đang subscribe đồng thời.
        return Flux.range(1, 6)
                .flatMap(i -> lookup(i), 2)
                .collectList();
    }

    private Mono<String> lookup(long id) {
        return Mono.fromCallable(() -> blockingLookup(id))
                .subscribeOn(legacyIoScheduler);
    }

    private String blockingLookup(long id) throws InterruptedException {
        Thread.sleep(200);  // Chỉ mô phỏng một API blocking.
        return "legacy-" + id;
    }
}
```

Toàn bộ source trên ở **một tệp Java**. Chỉ `OffloadDemoApplication` là class `public`; `LegacyController` là class package-private và vẫn được Spring component scan phát hiện. `@Bean(destroyMethod = "dispose")` quản lý shutdown pool riêng, tránh để thread sống ngoài vòng đời ứng dụng.

**Vì sao code này offload đúng?** Spring WebFlux subscribe vào `Mono` do controller trả về. `lookup(id)` chưa gọi `blockingLookup` cho đến lúc subscribe. Vì source có `subscribeOn(legacyIoScheduler)`, đoạn `Thread.sleep` chạy trên worker thuộc pool `legacy-io`, không trực tiếp trên event loop.

### 6.3. Chạy và kiểm tra

Cần **JDK 17+**, Maven 3.6.3+ và cổng 8080 trống. Đứng trong thư mục `offload-demo`:

```bash
mvn spring-boot:run
```

Mở terminal khác:

```bash
curl -s http://localhost:8080/legacy/7
```

HTTP response body **chính xác**:

```text
legacy-7
```

Thử endpoint batch:

```bash
curl -s http://localhost:8080/batch
```

Body là một mảng JSON gồm 6 chuỗi `legacy-1` đến `legacy-6`. **Thứ tự không được bảo đảm** vì `flatMap` có thể hoàn tất các nguồn con khác thứ tự; đừng dùng chính xác thứ tự xuất hiện làm phép kiểm tra đúng/sai.

Trong PowerShell, `curl` có thể là alias của lệnh khác ở một số phiên bản hệ điều hành; dùng `curl.exe` khi cần. Có thể đổi cổng với `--server.port=8081` thông qua đối số Spring Boot thích hợp nếu 8080 bận. Khi dừng app, Spring gọi `dispose()` cho scheduler riêng.

### 6.4. Kiểm tra thực sự đang dùng thread nào

Để quan sát, tạm thêm vào `blockingLookup` trước `Thread.sleep`:

```java
System.out.println("blockingLookup thread=" + Thread.currentThread().getName());
```

Sau khi gửi request, tên thread thường có tiền tố `legacy-io-`; số thứ tự thread và thứ tự dòng log **không cố định**. Có thể thay bằng logger phù hợp ở production. Không lấy tên thread làm API cứng, nhưng dùng thread dump/profiler để xác minh không có `reactor-http-nio-*` bị kẹt trong lời gọi legacy.

## 7. Giới hạn Scheduler, `flatMap` và tài nguyên downstream là ba chuyện khác nhau

Một thiết kế ổn cần **nhiều tầng kiểm soát**, vì scheduler chỉ quyết định nơi chạy code.

### 7.1. Giới hạn scheduler riêng

`Schedulers.newBoundedElastic(4, 20, "legacy-io")` có ý nghĩa:

- **`threadCap=4`**: tối đa 4 backing threads do scheduler này quản lý.
- **`queuedTaskCap=20`**: giới hạn task chờ theo cơ chế queue của mỗi backing thread; không phải “tối đa 20 request cho cả ứng dụng”.
- **`name="legacy-io"`**: tiền tố tên thread, hữu ích khi debug.

Số task có thể bị từ chối khi queue đạt giới hạn. Queue có thể phân bố không đều giữa các worker; đừng tính một SLA “chính xác 4 + 4×20 request” chỉ từ hai con số mà không đo đạc.

Dùng scheduler riêng khi cần bảo vệ phần lớn ứng dụng khỏi một integration blocking kém ổn định. `Schedulers.boundedElastic()` dùng chung đơn giản hơn, phù hợp tác vụ blocking nhỏ/lẻ. **Không gọi `dispose()` lên shared `Schedulers.boundedElastic()` trong code xử lý request**; chỉ dispose scheduler do mình tạo và sở hữu.

### 7.2. `flatMap(..., concurrency)`

`flatMap(id -> lookup(id), 2)` trong ví dụ giữ tối đa **2 inner subscriptions đồng thời** tại operator đó, giúp tránh dồn cùng lúc 6 việc vào pool. Nhưng một server có thể xử lý **nhiều request `/batch` song song**: mỗi request có giới hạn riêng nên tổng có thể vượt 2.

Muốn có **giới hạn toàn cục** cho một legacy backend, phải có admission control/bulkhead/semaphore hoặc rate limiter ở phạm vi toàn ứng dụng, được tích hợp với publisher và cơ chế giải phóng permit khi thành công, lỗi hoặc hủy. Không nên giữ semaphore blocking `acquire()` trên event loop. Dùng timeout và điều kiện overload rõ ràng để không tạo queue vô hạn.

### 7.3. Giới hạn thật của DB/HTTP/SDK

Giả sử scheduler có 40 threads nhưng DB pool chỉ 10 connections. Ít nhất một phần task có thể **chặn để chờ lấy connection**, tăng latency và memory. Điều chỉnh đồng bộ giữa:

- số request đầu vào được phép nhận;
- số blocking tasks đồng thời;
- kích thước connection pool/HTTP client pool;
- timeout kết nối, query, read và tổng deadline;
- mức throughput tối đa của dịch vụ phụ thuộc.

Số worker càng nhiều không bảo đảm hiệu năng càng tốt. Một giới hạn nhỏ được benchmark và quan sát kỹ thường hữu ích hơn việc tăng `threadCap` mặc định.

## 8. Timeout, cancellation, lỗi và retry

### 8.1. Timeout reactive không phải lúc nào cũng ngắt được I/O blocking

```java
return Mono.fromCallable(() -> legacyClient.fetch())
        .subscribeOn(legacyIoScheduler)
        .timeout(Duration.ofSeconds(2));
```

Đây là **minh họa trong một method**, cần import `java.time.Duration`; `legacyClient` và `legacyIoScheduler` do ứng dụng cung cấp. `timeout` phát lỗi khi pipeline không nhận tín hiệu đúng hạn, đồng thời có thể hủy subscription/upstream. Nhưng lời gọi đang chặn có thể **không dừng ngay** nếu thư viện blocking không phản hồi interruption hoặc đang kẹt tại syscall/SDK không có timeout.

Vì thế phải cấu hình **connect timeout/read timeout/query timeout** ở *thư viện blocking thật*, và chọn deadline phù hợp với deadline HTTP ở phía ngoài. Nếu nguồn blocking không dừng được, việc hủy request không trả thread về ngay; thread vẫn có thể bị giữ đến khi API tự kết thúc.

### 8.2. Đừng retry vô điều kiện

`Mono.fromCallable` thường chạy **lại callable mỗi subscription**. `retryWhen` tạo subscription mới khi lỗi, nên có thể lặp lại thao tác blocking:

- Với GET/read idempotent có thể cân nhắc retry hữu hạn, backoff và jitter khi lỗi nhất thời.
- Với ghi dữ liệu, thanh toán, gửi email hoặc side effect, phải có idempotency key/transaction semantics trước khi retry.
- Retry tăng tải trên scheduler và downstream; không retry hàng loạt khi pool đang bão hòa.

### 8.3. Xử lý queue đầy và lỗi nghiệp vụ

Khi scheduler không còn nhận task, có thể gặp `RejectedExecutionException`. Cần xác định phản ứng mong muốn:

- trả lỗi phù hợp (ví dụ HTTP 503 khi dịch vụ phụ thuộc đang quá tải), kèm logging/metric;
- hạn chế request mới để phục hồi;
- không giấu lỗi bằng `onErrorResume(e -> Mono.empty())` nếu điều đó khiến client hiểu nhầm request thành công;
- không tự tăng vô hạn queue hoặc khởi tạo scheduler mới trong mỗi request để “vượt” giới hạn.

Lỗi business (không tìm thấy, validation, HTTP status từ downstream) và lỗi hạ tầng (timeout, reject, connect failure) nên được ánh xạ riêng ở lớp API.

## 9. Thiết kế đúng khi có nhiều phần việc trong một request

Giả sử endpoint cần dữ liệu từ `legacyDao` (blocking) rồi kết hợp với `WebClient` (non-blocking). Chỉ offload **đoạn blocking**:

```java
Mono<LegacyUser> user = Mono.fromCallable(() -> legacyDao.find(userId))
        .subscribeOn(legacyIoScheduler);

return user.flatMap(u ->
        webClient.get()
                .uri("/profiles/{id}", u.id())
                .retrieve()
                .bodyToMono(Profile.class)
                .map(profile -> combine(u, profile)));
```

Đây là **minh họa rút gọn**, chưa là chương trình độc lập: `LegacyUser`, `Profile`, `webClient` và `combine` do ứng dụng cung cấp. `WebClient` không cần bị “bọc” trong `boundedElastic` chỉ vì nối sau nguồn blocking: WebClient vốn sử dụng I/O reactive. Đừng dùng `.block()` để lấy kết quả WebClient bên trong handler WebFlux.

Với hàng trăm phần tử, tránh lấy toàn bộ dữ liệu đồng bộ bằng một lệnh blocking lớn rồi nghĩ `Flux.fromIterable(...)` là streaming non-blocking. Nếu upstream vẫn chặn để tính toàn bộ tập, scheduler chỉ giúp cô lập **lời gọi blocking đó**. Nên có paging, streaming API thực sự hoặc driver reactive nếu cần backpressure xuyên tầng.

### JDBC/JPA và transaction

`JdbcTemplate`, `EntityManager`/JPA thường là **blocking**. Chạy chúng trên bounded scheduler giúp tránh chặn event loop, nhưng **không chuyển persistence thành reactive**. Transaction của Spring Data JPA thường dựa trên `ThreadLocal`; nếu viết `@Transactional` trên method chỉ **trả về một `Mono` lạnh** rồi truy vấn thực thi ở thread khác sau khi method kết thúc, đừng mặc định rằng transaction imperative bao trọn callable.

Cách tổ chức an toàn là giữ một **service blocking có ranh giới transaction imperative rõ** (ví dụ `@Transactional` trên public method của service được proxy Spring quản lý), rồi gọi method đó **bên trong `fromCallable`** trên bounded scheduler. Đối với hệ thống reactive xuyên tầng, xem xét R2DBC và reactive transaction management phù hợp.

### ThreadLocal, MDC và security context

Đổi thread có thể làm mất giá trị lưu trong `ThreadLocal` tự quản lý (correlation ID/MDC). Reactor có `Context` và hệ sinh thái context propagation; dùng cơ chế tương thích phiên bản Spring/Reactor thay vì dựa vào giả định “mọi callback chạy cùng request thread”. Không chép thủ công hoặc giữ tràn lan context nhạy cảm trong static field.

## 10. Quan sát và kiểm thử thực tế

Một phép thử tốt cần chứng minh **thread isolation**, **giới hạn tải** và **độ trễ của hệ thống**:

1. **Xác nhận runtime:** ứng dụng dùng WebFlux; log/request thread không bị chiếm bởi operation legacy; kiểm tra stack trace hoặc profiler.
2. **Tạo tải có kiểm soát:** thử 1, 10, 100 request đồng thời; quan sát p50/p95/p99 latency, throughput, số request lỗi/rejected và thời gian chờ.
3. **Quan sát scheduler:** số thread, task pending, thời gian task chờ trong queue, rejected tasks. Tùy phiên bản có thể bật metrics/instrument scheduler bằng Micrometer/Reactor Micrometer hoặc công cụ profiler.
4. **Quan sát downstream:** connection pool active/pending, query duration, timeout và retry.
5. **Đo khi downstream chậm:** ví dụ tăng thời gian chờ của stub từ 50 ms lên 2 giây. Scheduler không nên tăng thread không giới hạn; nếu quá tải cần có timeout và policy từ chối.
6. **Kiểm thử hủy request:** đóng kết nối client giữa chừng, xem blocking thư viện có phản hồi interruption hay tiếp tục chạy.
7. **Kiểm thử correctness:** đảm bảo exception truyền ra HTTP đúng nghĩa; kiểm tra transaction và idempotency.

Khi dùng BlockHound trong môi trường phát triển/test tương thích phiên bản, có thể phát hiện một số lời gọi blocking trái phép trên non-blocking threads. Nhưng BlockHound **không phải bảo đảm tuyệt đối** nhận diện mọi API blocking và không thay thế benchmark hoặc thread dump.

Đừng so sánh chỉ bằng “mỗi request nhanh hơn”: offload thường thêm chi phí chuyển thread; mục tiêu chính là **không khóa event loop, giữ hệ thống phản hồi được dưới nhiều I/O blocking và giới hạn resource**. Với ứng dụng thuần JDBC/JPA blocking, Spring MVC có thể đơn giản và phù hợp hơn WebFlux + offload ở khắp nơi.

## 11. Lỗi phổ biến và cách sửa

| Hiện tượng / sai lầm | Nguyên nhân | Hướng sửa |
| --- | --- | --- |
| Đặt `Mono.just(dao.query())` rồi `subscribeOn` | `query()` đã chạy trước khi Mono được tạo | Đổi thành `Mono.fromCallable(() -> dao.query())` |
| Đặt `publishOn` **sau** `map` blocking | Chuyển thread quá muộn | Dùng `fromCallable + subscribeOn` hoặc đặt `publishOn` trước callback blocking |
| Dùng `Schedulers.parallel()` cho JDBC | Pool dành cho công việc non-blocking/CPU | Dùng `boundedElastic` hoặc scheduler blocking riêng |
| Gọi `.block()` trong handler WebFlux | Chặn luồng reactive, có thể bị Reactor cấm | Trả `Mono`/`Flux` về framework |
| Dùng `.subscribe()` trong controller | Tách việc khỏi lifecycle HTTP | Trả publisher đầy đủ, kết hợp bằng `flatMap`/`then` |
| Tạo `newBoundedElastic` cho **mỗi request** | Rò rỉ thread/queue, phá giới hạn chung | Tạo một bean singleton, dispose khi shutdown |
| Mặc định coi `boundedElastic` là vô hạn | Pool/queue có cap và sẽ reject | Bổ sung overload policy, metrics, timeout |
| Timeout HTTP rồi nghĩ DB query chắc chắn đã dừng | Cancellation không bảo đảm ngắt mọi blocking API | Cấu hình timeout tại JDBC/SDK/socket; kiểm tra interrupt |
| `flatMap(..., 2)` nhưng toàn app vẫn quá nhiều call | Giới hạn chỉ trên mỗi subscription cụ thể | Thêm admission/bulkhead toàn cục |
| `ThreadLocal`/transaction bị thiếu sau đổi thread | Context imperative không tự chuyển qua thread khác | Giữ service transaction ở callable, dùng context propagation |
| Mọi bước trong pipeline đều offload sang elastic | Chuyển thread thừa; non-blocking steps cũng bị dồn vào pool | Offload đúng phần blocking, giữ WebClient/R2DBC reactive |
| Test thông qua 1 request thấy chạy nhanh | Không kiểm tra contention/queue | Benchmark concurrency và đo p95/p99, resource, reject |

## 12. Bài tập tự đánh giá

1. **Đoạn nào chạy blocking call đúng nơi?**

   `Mono.just(legacyCall()).subscribeOn(Schedulers.boundedElastic())` hay `Mono.fromCallable(() -> legacyCall()).subscribeOn(Schedulers.boundedElastic())`?

   **Đáp án:** đoạn thứ hai, vì call bị trì hoãn đến lúc subscribe và subscription được lên lịch trên scheduler.

2. **`Schedulers.boundedElastic()` có biến `JdbcTemplate` thành non-blocking không?**

   **Không.** JDBC vẫn chặn một thread của bounded scheduler; chỉ event loop được bảo vệ.

3. **Đã đặt `threadCap=4`, có chắc chỉ tối đa 4 request được nhận không?**

   **Không.** Có thể có task đang chờ; cần phân biệt running, queued và rejected, thêm admission control nếu muốn giới hạn tổng request.

4. **`flatMap(..., 3)` trong một request có giới hạn tối đa 3 blocking task trên toàn hệ thống không?**

   **Không.** Nó giới hạn concurrency tại operator/subscription đó; nhiều request có thể đồng thời tạo các nhóm khác.

5. **Vì sao `timeout(Duration.ofSeconds(2))` chưa chắc giải phóng được worker sau 2 giây?**

   **Vì** thư viện blocking có thể không phản hồi cancellation/interruption ngay; cần timeout ở thư viện thực.

6. **Khi nào nên thay JDBC bằng R2DBC thay vì offload?**

   Khi thiết kế cần non-blocking end-to-end, driver/DB phù hợp và lợi ích được xác nhận qua tải thật. Nếu phần lớn hệ thống vẫn imperative blocking, cân nhắc MVC để giảm độ phức tạp.

## 13. Checklist áp dụng trong ứng dụng

- [ ] Xác định chính xác API nào chặn luồng và ở thread nào nó đang chạy.
- [ ] Bọc call bằng `Mono.fromCallable` hoặc `Mono.fromRunnable` để trì hoãn thực thi.
- [ ] Đặt `subscribeOn(Schedulers.boundedElastic())` ngay gần source, hoặc dùng scheduler riêng do Spring quản lý.
- [ ] Giữ HTTP handler trả về `Mono`/`Flux`, không `.block()` và không `.subscribe()` thủ công.
- [ ] Giới hạn concurrency của từng luồng dữ liệu và của toàn hệ thống khi cần.
- [ ] Cấu hình timeout ở API blocking bên dưới; đánh giá cancellation, error/retry/idempotency.
- [ ] Bảo đảm vòng đời `dispose()` của scheduler riêng, không tạo scheduler trên mỗi request.
- [ ] Xác minh transactions, ThreadLocal/context, metrics, thread dump và phản ứng khi overload.
- [ ] Cân nhắc chọn Spring MVC khi phần lớn code là blocking I/O.

## 14. Tài liệu chính thức

- Project Reactor — [Threading and Schedulers](https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html)
- Project Reactor — [FAQ: How Do I Wrap a Synchronous, Blocking Call?](https://projectreactor.io/docs/core/release/reference/faq.html)
- Reactor API — [Schedulers: boundedElastic, newBoundedElastic và giới hạn](https://projectreactor.io/docs/core/release/api/reactor/core/scheduler/Schedulers.html)
- Spring Framework — [Spring WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux.html)
- Spring Framework — [Reactive Core, concurrency model](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html)
- Spring Boot — [Reactive Web Applications](https://docs.spring.io/spring-boot/reference/web/reactive.html)

**Ghi nhớ:** công thức cần nắm là **`Mono.fromCallable(blockingCall) + subscribeOn(boundedElastic)`**; trong ứng dụng thực cần thêm **giới hạn scheduler, giới hạn request/concurrency, timeout downstream và quan sát khi quá tải**. Offload chỉ là một ranh giới bảo vệ event loop, không phải phép biến blocking I/O thành reactive I/O.