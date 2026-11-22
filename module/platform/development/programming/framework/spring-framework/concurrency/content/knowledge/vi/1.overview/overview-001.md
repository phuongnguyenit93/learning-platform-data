# Đồng thời trong Spring: mục đích và các tình huống sử dụng

## 1. Bối cảnh và mục tiêu

Trong một ứng dụng Spring, nhiều yêu cầu HTTP, sự kiện, tác vụ nền và lần gọi dịch vụ bên ngoài có thể diễn ra trong cùng một khoảng thời gian. **Lập trình đồng thời (concurrency)** giúp tổ chức các công việc đang tiến triển cùng lúc và kiểm soát tài nguyên chúng dùng. Đây là một quyết định về cách điều phối công việc, không phải bảo đảm rằng mọi thao tác sẽ chạy nhanh hơn.

Sau bài này, người học cần phân biệt được đồng thời, song song, bất đồng bộ và không chặn; nhận ra tình huống nên dùng cơ chế đồng thời trong Spring; chọn đúng công cụ ở mức tổng quan; và đánh giá rủi ro của luồng, hàng đợi, lỗi, giao dịch, dữ liệu dùng chung.

### Bốn khái niệm thường bị nhầm

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Concurrency – đồng thời** | Nhiều công việc cùng tồn tại và được điều phối trong một khoảng thời gian; có thể xen kẽ trên một lõi CPU. | Server xử lý nhiều request đang chờ I/O. |
| **Parallelism – song song** | Hai hay nhiều phần việc thật sự thực thi cùng thời điểm, thường trên nhiều lõi CPU. | Tính toán độc lập trên nhiều worker. |
| **Asynchrony – bất đồng bộ** | Bên gọi có thể tiếp tục công việc thay vì đợi tác vụ kết thúc ngay tại lời gọi; kết quả thường tới qua `Future`, callback hoặc tín hiệu. | Gọi phương thức `@Async` và nhận `CompletableFuture`. |
| **Blocking – chặn** | Luồng hiện tại phải đợi để thao tác hoàn tất. | `Thread.sleep(...)`, JDBC đồng bộ, `future.get()`. |
| **Non-blocking – không chặn** | Thao tác không giữ luồng để ngồi chờ I/O; cơ chế thông báo khi dữ liệu sẵn sàng. | I/O theo mô hình Reactor/WebFlux với thư viện tương thích. |

Một lời gọi `@Async` thường **chuyển công việc chặn sang luồng khác**; bản thân I/O trong công việc ấy chưa trở thành non-blocking. Ngược lại, một pipeline WebFlux non-blocking không mặc nhiên chạy nhiều phép tính CPU song song.

## 2. Spring cần concurrency để làm gì?

### Giữ hệ thống phản hồi tốt khi có thao tác chờ

Giả sử một API tổng hợp thông tin sản phẩm phải hỏi dịch vụ giá (khoảng 400 ms) và tồn kho (khoảng 600 ms). Nếu hai yêu cầu **độc lập** và gọi nối tiếp, thời gian chờ phần I/O xấp xỉ 1.000 ms. Nếu khởi chạy đồng thời và chỉ ghép kết quả sau khi cả hai hoàn thành, phần chờ lý tưởng có thể gần 600 ms cộng chi phí điều phối. Đây là minh họa, không phải cam kết về latency: giới hạn connection, thread pool, downstream, hàng đợi và lỗi đều có thể thay đổi kết quả.

Để hưởng lợi, phải có công việc độc lập đủ lớn để chồng lấp thời gian chờ. Gọi `@Async` rồi lập tức `join()` ngay tại cùng một điểm thường chỉ thêm chi phí chuyển luồng mà không tạo ra mức chồng lấp hữu ích.

### Tách công việc không nằm trên đường phản hồi chính

Ví dụ: sau khi xử lý yêu cầu, ứng dụng có thể khởi động việc tạo thumbnail, gửi thông báo không trọng yếu hoặc chuẩn bị bản tổng hợp. Người dùng không nhất thiết cần đợi các công việc này trước khi nhận phản hồi.

Điều kiện là nghiệp vụ **cho phép hoàn thành sau** và có cách quan sát/lấy lại lỗi. Đẩy việc sang thread nền trong cùng tiến trình không bảo đảm tác vụ còn tồn tại khi ứng dụng khởi động lại. Với việc bắt buộc giao thành công, nên dùng outbox/queue/job bền vững thay vì coi `@Async void` là cơ chế giao hàng tin cậy.

### Tăng khả năng phục vụ nhiều request chờ I/O

Khi request thường phải đợi database hoặc mạng, một luồng có thể rảnh CPU nhưng vẫn bị giữ vì blocking. Thread pool giúp giới hạn và phân phối công việc; các API async của Spring MVC hoặc I/O non-blocking có thể giúp dùng luồng hiệu quả hơn trong các mô hình phù hợp. **Throughput**, **latency** và **mức sử dụng tài nguyên** là các mục tiêu khác nhau: tăng số luồng quá nhiều có thể làm hệ thống chậm, tốn bộ nhớ và gây quá tải downstream.

### Điều phối công việc theo thời điểm

Nhu cầu quét dữ liệu định kỳ, gia hạn token, dọn cache hoặc tổng hợp báo cáo hàng đêm cần cơ chế lập lịch. Trong Spring, đây là nhóm `@Scheduled`/`TaskScheduler`. Lập lịch quyết định *khi nào* công việc được kích hoạt; điều khiển đồng thời quyết định *có bao nhiêu* công việc chạy và *chạy ở đâu*.

## 3. Tình huống sử dụng điển hình

| Tình huống | Cách tiếp cận phù hợp | Điều cần kiểm soát |
| --- | --- | --- |
| Ghép kết quả từ hai API độc lập trong một request | `CompletableFuture`/executor có giới hạn; trả future cho Spring MVC nếu cần | Timeout của từng API, lỗi từng nhánh, số kết nối ra ngoài |
| Gửi email thông báo không trọng yếu sau khi phản hồi | `@Async` với executor riêng nếu chấp nhận best-effort | Retry, theo dõi thất bại; chuyển sang queue nếu phải giao chắc chắn |
| Tạo báo cáo/export có thể mất vài phút | Job nền có trạng thái, idempotency; queue/job store nếu cần sống qua restart | Tiến độ, hủy, retry, dung lượng bộ nhớ |
| Xử lý file, tạo thumbnail hoặc gọi API chậm | Executor riêng cho I/O, giới hạn số công việc | I/O, băng thông, giới hạn từ dịch vụ phụ thuộc |
| Đồng bộ dữ liệu, dọn dẹp theo lịch | `@Scheduled` và cơ chế chống trùng phù hợp | Nhiều instance có thể cùng chạy; tránh chạy chồng |
| Tác vụ CPU nặng, có thể chia độc lập | Worker pool giới hạn theo năng lực CPU, hoặc hệ xử lý batch | Tranh CPU, memory pressure, không nhân thread vô hạn |
| Lưu lượng lớn với chuỗi I/O non-blocking tương thích | Spring WebFlux/Reactor (hoặc mô hình async phù hợp) | Không chặn event loop; backpressure, observability |

Không nên tạo tác vụ nền cho thao tác rất ngắn, có tính thứ tự bắt buộc hoặc cần giao dịch nguyên tử với request hiện tại chỉ vì muốn “dùng đa luồng”. Cũng không nên tự tạo `new Thread(...)` cho mỗi request để né cấu hình năng lực hệ thống.

## 4. Các công cụ liên quan trong Spring

- **`TaskExecutor` / `AsyncTaskExecutor`:** abstraction của Spring để gửi `Runnable`/`Callable` vào cơ chế thực thi; implementation có thể là pool, luồng riêng hoặc thậm chí chạy đồng bộ. Không phải executor nào cũng có pool.
- **`ThreadPoolTaskExecutor`:** executor có `corePoolSize`, `maxPoolSize` và `queueCapacity`; phù hợp để giới hạn số tác vụ chạy/đợi trong ứng dụng. Hàng đợi lớn có thể che giấu tình trạng nghẽn và làm tăng latency.
- **`@EnableAsync` + `@Async`:** bật interception của Spring và chuyển lời gọi phương thức qua executor khi phương thức được gọi **qua Spring proxy**. Thường dùng ở service được inject vào bean khác; có thể chỉ định executor bằng `@Async("ioExecutor")`.
- **`CompletableFuture<T>`:** đại diện kết quả sẽ có sau, cho phép ghép, xử lý lỗi và đợi kết quả. `thenApply`, `thenCombine` và `allOf` giúp mô tả quan hệ giữa các tác vụ; luôn cân nhắc thread thực thi và ngoại lệ.
- **`@Scheduled` + `TaskScheduler`:** dùng cho công việc định kỳ/đến hạn. `@Scheduled` không có nghĩa là tự động có persistence hay khóa phân tán.
- **Spring MVC async:** controller có thể trả `Callable`, `DeferredResult`, `CompletableFuture` hoặc kiểu async hỗ trợ để trả lại servlet request thread trong lúc chờ kết quả, tùy adapter và cấu hình. HTTP response vẫn chỉ hoàn tất khi có dữ liệu.
- **Spring WebFlux/Reactor:** mô hình reactive/non-blocking, phù hợp khi cả chuỗi thao tác hỗ trợ non-blocking. Không mang JDBC chặn trực tiếp lên event-loop thread.
- **Message broker/job system:** phù hợp cho hàng đợi bền vững, retry và xử lý kéo dài qua vòng đời process. Đây là mô hình kiến trúc khác với việc gửi việc vào pool trong JVM.

**Phân biệt ba đường đi:**

```text
Đồng bộ:    request thread -> gọi tác vụ -> chờ -> nhận kết quả -> phản hồi
@Async:     caller -> Spring proxy -> executor -> worker chạy tác vụ
                                      -> Future hoàn thành hoặc lỗi
MVC async:  request thread -> trả Future/async handle -> giải phóng request thread
                                                    -> kết quả -> hoàn tất HTTP
```

Không có cơ chế nào trong ba cơ chế này tự làm một truy vấn SQL blocking trở thành truy vấn non-blocking. Sự khác biệt nằm ở thread nào chờ và thread nào được giải phóng.

## 5. Ví dụ có thể chạy: API Spring MVC thực hiện công việc I/O mô phỏng qua `@Async`

Ví dụ dùng Java 17 và Spring Boot 3.5.7 (Spring Framework 6.x). Đây là project Maven độc lập với hai tệp, đủ để chạy một endpoint. Nó mô phỏng một lần gọi I/O chậm bằng `Thread.sleep(300)` để quan sát ranh giới bất đồng bộ; mã sản xuất nên thay bằng client thật có timeout.

**Tệp `pom.xml`:**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>spring-concurrency-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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

**Tệp `src/main/java/example/demo/ConcurrencyDemoApplication.java`:**

```java
package example.demo;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ThreadPoolExecutor;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.ResponseEntity;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@EnableAsync
public class ConcurrencyDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ConcurrencyDemoApplication.class, args);
    }

    @Bean("ioExecutor")
    public ThreadPoolTaskExecutor ioExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(20);
        executor.setThreadNamePrefix("io-worker-");
        executor.setRejectedExecutionHandler(new ThreadPoolExecutor.AbortPolicy());
        executor.initialize();
        return executor;
    }
}

@Service
class QuoteService {
    @Async("ioExecutor")
    public CompletableFuture<String> getQuote(String productId) {
        try {
            Thread.sleep(300); // Chỉ mô phỏng I/O blocking.
            return CompletableFuture.completedFuture("Báo giá cho " + productId);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            return CompletableFuture.failedFuture(ex);
        }
    }
}

@RestController
class QuoteController {
    private final QuoteService quoteService;

    QuoteController(QuoteService quoteService) {
        this.quoteService = quoteService;
    }

    @GetMapping(value = "/quotes/{id}", produces = "text/plain")
    public CompletableFuture<ResponseEntity<String>> quote(@PathVariable String id) {
        return quoteService.getQuote(id).thenApply(ResponseEntity::ok);
    }
}
```

Đặt cấu trúc file đúng như trên. Tại thư mục có `pom.xml`, dùng JDK 17+ và Maven:

```bash
mvn spring-boot:run
```

Ở terminal khác:

```bash
curl -s http://localhost:8080/quotes/A12
```

**Nội dung HTTP response body:**

```text
Báo giá cho A12
```

Thứ tự log và tên các luồng khác nhau giữa các lần chạy, nên ví dụ không khẳng định một trình tự stdout cố định. `Thread.sleep(300)` mô phỏng khoảng chờ chứ không chứng minh hiệu năng khi có tải.

**Cơ chế thực thi:**

1. `QuoteController` nhận request; `quoteService` là một bean riêng nên lời gọi `getQuote` đi qua proxy do `@EnableAsync` thiết lập.
2. Spring gửi phương thức `@Async("ioExecutor")` tới `ThreadPoolTaskExecutor`; worker có thể chạy thao tác chờ 300 ms mà không giữ request thread ở lời gọi đó.
3. Controller trả `CompletableFuture<ResponseEntity<String>>`; Spring MVC hỗ trợ async response và hoàn tất HTTP khi future có kết quả. Client vẫn đợi response; lợi ích trước hết là điều phối thread trong server.
4. Vì executor có số worker và hàng đợi hữu hạn, khi quá tải có thể xảy ra từ chối tác vụ. Chính sách `AbortPolicy` chỉ làm lỗi được bộc lộ, chưa phải cơ chế phản hồi 503/retry hoàn chỉnh cho production.

Ví dụ chỉ minh họa **một** cuộc gọi. Không thể kết luận endpoint này giảm tổng thời gian của một lần I/O; muốn giảm latency do chờ nối tiếp, cần có ít nhất hai nhánh công việc *độc lập* và khởi chạy chúng trước lúc ghép kết quả.

## 6. Quyết định thực tế: khi nào nên và không nên chạy đồng thời?

### Nên cân nhắc

1. Có nhiều tác vụ I/O độc lập và đo được phần thời gian đang chờ; concurrency có thể chồng lấp phần chờ đó.
2. Có tác vụ phụ mà kết quả HTTP không bắt buộc đợi; nghiệp vụ cho phép xử lý sau và có phương án lỗi rõ ràng.
3. Có nhóm công việc batch đủ lớn, độc lập, có giới hạn tài nguyên và chiến lược gộp kết quả.
4. Cần xử lý nhiều event/request nhưng phải tránh để một tác vụ chậm chiếm toàn bộ năng lực phục vụ.

### Không nên áp dụng máy móc

- Tác vụ rất nhỏ, kết quả phụ thuộc tuần tự vào nhau, hoặc caller lập tức đợi `join()`; overhead có thể vượt lợi ích.
- Công việc phải cam kết cùng giao dịch với thao tác chính: chuyển sang luồng khác có thể phá giả định về thứ tự, context và atomicity.
- Công việc có trạng thái bắt buộc phải tồn tại sau khi JVM tắt: chỉ `@Async` trong bộ nhớ là không đủ.
- Tác vụ CPU-bound đang bão hòa CPU: tăng thread không tạo thêm lõi và có thể tăng context switching.
- Code blocking chạy trên event loop WebFlux: các request khác có thể bị ảnh hưởng. Dùng thư viện non-blocking hoặc chuyển công việc blocking sang scheduler chuyên dụng có giới hạn, tùy kiến trúc.
- Tác vụ “fire-and-forget” không có log, metric, timeout, retry hoặc người chịu trách nhiệm xử lý khi thất bại.

## 7. Các giới hạn và lỗi phổ biến cần biết ngay từ đầu

### Giới hạn pool, queue, tài nguyên downstream

Executor không có năng lực vô tận. Kích thước pool, hàng đợi và số kết nối HTTP/DB quyết định hệ thống có thể hấp thụ bao nhiêu công việc. Với `ThreadPoolTaskExecutor`, một hàng đợi còn chỗ thường được dùng trước khi pool tăng lên `maxPoolSize`; cấu hình queue quá lớn có thể khiến request chờ lâu mà số worker không tăng như mong đợi.

Chọn giới hạn theo phép đo: tốc độ đến của task, thời gian xử lý, CPU, bộ nhớ, khả năng dịch vụ phụ thuộc, timeout và SLO. Có metric về số active threads, số task đang đợi, số từ chối, latency và tỉ lệ lỗi. Khi quá tải, phải có chính sách rõ: từ chối sớm, trả trạng thái phù hợp, giảm tải, điều tiết hoặc chuyển sang queue bền vững.

### Dữ liệu dùng chung và tính đúng đắn

Spring bean `@Service`/`@Component` thường là singleton; nhiều request/worker có thể đồng thời gọi cùng bean. Không đặt trạng thái thay đổi theo request vào field chia sẻ nếu chưa có thiết kế đồng bộ đúng. Ưu tiên biến cục bộ, dữ liệu immutable, lớp thread-safe; khi dùng lock/concurrent collection/transaction phải xác định ranh giới bảo vệ thực sự.

Một `HashMap` thường không an toàn khi nhiều thread cùng ghi. Ngay cả `ConcurrentHashMap` cũng không tự làm an toàn chuỗi thao tác “đọc rồi ghi” nhiều bước nếu các bước cần tính nguyên tử.

### Proxy, lời gọi nội bộ và kiểu trả về

- `@Async` mặc định hoạt động qua Spring AOP proxy. Gọi `this.doAsync()` từ chính bean đó không đi qua proxy, nên thường chạy đồng bộ. Nên tách phương thức sang service khác hoặc sử dụng cơ chế interception phù hợp.
- Method `@Async` nên được gọi qua Spring-managed bean và có chữ ký hợp lệ; các kiểu trả về thường dùng là `void`, `Future<T>` hoặc `CompletableFuture<T>`. Ví dụ dùng `CompletableFuture<T>` để xử lý kết quả/lỗi.
- Nếu dùng `@Async void`, caller không có future để nhận exception. Cần quan sát lỗi và có thể cấu hình `AsyncUncaughtExceptionHandler`; với future, xử lý exception ở phía nhận kết quả.
- Khi gọi `get()` hoặc `join()`, luồng gọi sẽ chặn đến khi kết quả sẵn sàng. Không gọi chặn ngay nếu mục tiêu là chồng lấp tác vụ.

### Giao dịch, SecurityContext và trace

`@Transactional` truyền thống dựa trên ngữ cảnh gắn với thread. Một tác vụ `@Async` chạy trên thread khác **không tự động kế thừa** transaction của thread gọi; cần thiết kế giao dịch riêng ở nơi xử lý, và không truyền entity lazy chưa tải ra ngoài ranh giới persistence context. `ThreadLocal`, MDC/log trace và `SecurityContext` cũng không nên được giả định là tự lan truyền; nếu cần, phải dùng cơ chế propagation được thiết kế và kiểm thử phù hợp, tránh rò rỉ context giữa task.

### Timeout, hủy, shutdown và consistency

Một future chưa hoàn tất có thể treo luồng đợi nếu không có timeout thực tế ở HTTP/DB/client. Hủy future không bảo đảm thư viện downstream dừng công việc; phải kiểm soát khả năng interruption. Khi ứng dụng shutdown, tác vụ còn trong bộ nhớ có thể mất; kiểm thử chính sách drain/shutdown, retry và idempotency. Nếu phát sự kiện sau khi ghi dữ liệu, cân nhắc phát sau commit hoặc outbox để tránh người nhận nhìn thấy dữ liệu chưa commit.

### Đa instance và lịch định kỳ

Một ứng dụng có ba instance có thể chạy tác vụ `@Scheduled` trên cả ba. Nếu nghiệp vụ yêu cầu “chỉ một lần trên toàn cụm”, cần lock/job coordinator hay hệ thống lập lịch phân tán. Không thể suy ra tính duy nhất từ annotation.

### Virtual threads không bỏ qua giới hạn công suất

Trên Java 21+, virtual threads có thể giảm chi phí sử dụng thread cho nhiều công việc blocking phù hợp; Spring có khả năng tích hợp tùy phiên bản/cấu hình. Nhưng chúng không làm API downstream nhanh hơn, không tăng kết nối DB vô hạn và không thay thế timeout, rate limit, backpressure. Với CPU-bound, virtual thread cũng không tạo thêm CPU.

## 8. Chọn phương án bằng các câu hỏi

Trước khi đưa concurrency vào thiết kế, hãy trả lời:

1. **Độc lập ở đâu?** Có thể chạy các nhánh trước khi cần kết quả của nhau không? Có ràng buộc thứ tự/transaction không?
2. **Đang chờ cái gì?** CPU, mạng, database, file hay khóa? Số liệu latency/throughput trước khi thay đổi là bao nhiêu?
3. **Ai đợi kết quả?** Client phải nhận ngay, nhận sau qua job ID, hay không cần kết quả? Công việc được phép mất khi process chết không?
4. **Giới hạn ở đâu?** Pool, queue, DB connections, downstream quota, memory, số instance?
5. **Lỗi xử lý ra sao?** Timeout, trả lỗi, retry có idempotency, bỏ qua có giám sát hay đẩy vào queue?
6. **Đo điều gì sau thay đổi?** P95/P99 latency, throughput, error rate, queue delay, saturation và mức sử dụng CPU/heap.

**Ba tình huống tự kiểm tra:**

- *Một API gọi hai service độc lập, mỗi service mất vài trăm ms:* có thể thử gọi đồng thời và ghép kết quả sau; giới hạn số request ra ngoài và xác định timeout/partial failure.
- *Đơn hàng đã ghi DB, cần bảo đảm phát sự kiện cho hệ thống kho dù ứng dụng restart:* chỉ `@Async` không đủ; cân nhắc transactional outbox và broker/job worker, có retry/idempotency.
- *Một phép tính mã hóa tốn CPU trên máy 4 lõi, thêm 100 worker có giúp nhanh gấp 25 lần?* Không. Cần đo và giới hạn concurrency theo CPU, chi phí chia việc, bộ nhớ.

## 9. Tài liệu đối chiếu

- [Spring Framework – Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): `TaskExecutor`, `@Async`, `@Scheduled`, proxy và exception.
- [Spring Boot – Task Execution and Scheduling](https://docs.spring.io/spring-boot/reference/features/task-execution-and-scheduling.html): executor mặc định và cấu hình tích hợp theo phiên bản Boot.
- [Spring Framework – WebFlux Overview](https://docs.spring.io/spring-framework/reference/web/webflux.html): cách tiếp cận reactive/non-blocking.
- [Spring Framework – WebFlux Concurrency Model](https://docs.spring.io/spring-framework/reference/web/webflux/new-framework.html): khác biệt blocking/thread model giữa MVC và WebFlux.

Concurrency trong Spring có ý nghĩa khi nó giải quyết một điểm chờ hoặc nhu cầu điều phối thật sự. Chọn mô hình theo **độ độc lập của công việc, yêu cầu độ tin cậy và giới hạn tài nguyên**, rồi kiểm chứng bằng số liệu và xử lý lỗi, thay vì mặc định chuyển mọi phương thức sang `@Async`.
