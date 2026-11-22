# Bật virtual threads trong Spring Boot bằng `spring.threads.virtual.enabled` (Java 21+)

## 1. Mục tiêu và ý chính

Trong một ứng dụng web Spring Boot, nhiều request cần chờ database, HTTP service khác hoặc file/network I/O. Với cách xử lý **một thread cho một request**, platform thread truyền thống tương đối tốn tài nguyên nếu phải giữ nó trong thời gian chờ. **Virtual thread (luồng ảo)** của Java cho phép duy trì cách viết mã đồng bộ dễ đọc mà có thể phục vụ nhiều tác vụ đang chờ hơn bằng số lượng nhỏ hơn các OS thread thực sự chạy mã Java.

Để Spring Boot kích hoạt hỗ trợ luồng ảo trên runtime tương thích, dùng:

```properties
spring.threads.virtual.enabled=true
```

Điều kiện chính: **ứng dụng phải chạy trên Java 21 trở lên** và dùng phiên bản Spring Boot có hỗ trợ property này (**Spring Boot 3.2+**; ví dụ trong bài sử dụng Spring Boot 3.x với Spring MVC và embedded Tomcat). Chỉ chỉnh Java source/target về 21 không đủ nếu tiến trình thực tế vẫn chạy bằng JDK thấp hơn.

**Ghi nhớ trước tiên:** bật virtual threads thay đổi cách một số tác vụ/request được thực thi; nó **không đổi HTTP request thành một thứ khác**, không tự động tăng tốc mã CPU-bound và không tự mở rộng connection pool của database.

## 2. Virtual thread là gì và vì sao phù hợp với web runtime?

`Thread` trong Java 21 có hai dạng chính:

- **Platform thread:** thường ánh xạ tương đối trực tiếp đến một OS thread; hệ điều hành lên lịch cho OS thread. Nếu một platform thread chờ blocking I/O, nó vẫn chiếm tài nguyên OS thread trong thời gian chờ.
- **Virtual thread:** vẫn là một `java.lang.Thread`, nhưng JVM quản lý lịch chạy. Một virtual thread được chạy trên platform thread gọi là **carrier**. Khi gặp thao tác blocking hỗ trợ cơ chế tạm dừng, JVM có thể tháo (*unmount*) virtual thread khỏi carrier để carrier chạy virtual thread khác; khi sẵn sàng, nó được đưa vào lịch tiếp.

Minh họa một request cần chờ DB:

```text
Platform thread:
  nhận request -> xử lý -> chờ DB (giữ OS thread) -> tiếp tục -> response

Virtual thread:
  nhận request -> xử lý -> chờ DB (virtual thread tạm dừng;
                               carrier có thể chạy tác vụ khác)
              -> tiếp tục -> response
```

Virtual thread **không chạy mã nhanh hơn**. Giá trị chính là giúp hệ thống chịu được **nhiều công việc đồng thời đang chờ I/O** với ít OS thread bị giữ vô ích hơn. Với tác vụ chủ yếu tính toán CPU, số lõi CPU và mức sử dụng CPU vẫn là giới hạn thực tế. Bật nhiều virtual thread không làm tăng số lõi.

| Thuộc tính | Platform thread | Virtual thread |
| --- | --- | --- |
| Ai quản lý lịch chạy? | Chủ yếu hệ điều hành | JVM lên lịch trên carrier platform threads |
| Chi phí một thread | Tương đối lớn | Thấp hơn đáng kể, có thể tạo theo tác vụ |
| Chờ I/O được JVM hỗ trợ | Thường giữ OS thread | Thường có thể tạm dừng để trả carrier |
| Mô hình phổ biến | Thread pool giới hạn số worker | Tạo một virtual thread cho mỗi tác vụ, không pool virtual threads |
| Dùng tốt nhất | Tác vụ tổng quát, tác vụ CPU hoặc hệ thống đã tối ưu pool | Nhiều tác vụ blocking I/O độc lập, ngắn hạn |
| Có phải `Thread` của Java? | Có | Có; `Thread.currentThread().isVirtual()` trả về `true` khi đang ở virtual thread |

Không nhầm **virtual thread** với request HTTP, session, socket, reactive stream hay một core CPU. Một socket keep-alive có thể đưa nhiều request khác nhau tới server; server có thể xử lý từng request trên virtual thread riêng.

## 3. Điều kiện và cách bật bằng cấu hình

### 3.1. Điều kiện tối thiểu

1. Cài **JDK 21+** và bảo đảm chính tiến trình chạy Spring Boot sử dụng JDK ấy. Kiểm tra bằng `java -version` và `mvn -version` (hoặc `./mvnw -version` nếu dự án dùng Maven Wrapper).
2. Dùng Spring Boot **3.2 trở lên** có tích hợp hỗ trợ virtual threads. Java 21 tự nó không khiến mọi phiên bản Boot cũ hiểu property.
3. Với ví dụ web servlet, dùng `spring-boot-starter-web` (Spring Boot 3.x, Spring MVC với embedded Tomcat mặc định). Hành vi thread của request còn phụ thuộc loại server và executor tùy biến.
4. Bật property và **khởi động lại** ứng dụng để cấu hình runtime có hiệu lực; kiểm tra rằng profile hoặc biến môi trường khác không ghi đè giá trị.

Không cần `--enable-preview`: virtual threads là tính năng chính thức của Java 21.

### 3.2. `application.properties`

Tại `src/main/resources/application.properties`:

```properties
spring.threads.virtual.enabled=true
spring.main.keep-alive=true
```

Dòng thứ nhất bật virtual threads. Dòng thứ hai giúp giữ JVM sống nếu ứng dụng chỉ còn các daemon thread; điều này đặc biệt đáng cân nhắc với ứng dụng chạy `@Scheduled` hoặc tác vụ nền. Với một web server bình thường, JVM có thể đã có thread nền giữ tiến trình sống, nhưng đặt `spring.main.keep-alive=true` là lựa chọn Spring Boot khuyến nghị khi dùng virtual threads.

### 3.3. Cấu hình tương đương bằng YAML

Tại `src/main/resources/application.yml`:

```yaml
spring:
  threads:
    virtual:
      enabled: true
  main:
    keep-alive: true
```

Chỉ chọn một trong hai dạng nếu chúng mô tả cùng bộ cấu hình, tránh để các nguồn cấu hình mâu thuẫn. Theo cơ chế externalized configuration của Spring Boot, có thể ghi đè từ command-line:

```bash
java -jar app.jar --spring.threads.virtual.enabled=true --spring.main.keep-alive=true
```

Ở đây `app.jar` là tên file jar đã build của ứng dụng; thay bằng tên jar thật của dự án. Với môi trường dùng biến môi trường, tên tương đương là `SPRING_THREADS_VIRTUAL_ENABLED=true`. Hãy kiểm tra precedence của profile/biến môi trường/command-line nếu giá trị vận hành khác mong đợi.

## 4. Khi bật property, Spring Boot thay đổi những gì?

Với các thành phần Spring Boot tự cấu hình, virtual threads được áp dụng ở các điểm tích hợp thích hợp; **không có nghĩa toàn bộ thread trong JVM trở thành virtual**.

### 4.1. Spring MVC trên embedded servlet server

Theo hỗ trợ được giới thiệu từ Spring Boot 3.2, **embedded Tomcat và Jetty** có thể dùng virtual threads để xử lý HTTP request khi bật property và chạy Java 21+. Controller kiểu Spring MVC vẫn viết theo mô hình quen thuộc:

```java
@GetMapping("/orders/{id}")
public Order find(@PathVariable long id) {
    return orderService.find(id);
}
```

Đây là **đoạn minh họa**: `Order` và `orderService` thuộc ứng dụng, không phải mã độc lập có thể biên dịch ngay. Nếu request chạy trên virtual thread, lệnh gọi blocking JDBC/HTTP client tương thích vẫn có thể giữ cú pháp tuần tự dễ hiểu. Không cần đổi controller thành reactive hoặc thêm `@Async` chỉ để kiểm tra `Thread.currentThread().isVirtual()`.

Lưu ý: proxy, acceptor, event-loop, carrier, GC và các thread nội bộ khác có thể vẫn là platform thread; một filter hoặc thành phần tự định nghĩa dùng executor riêng có thể chuyển công việc sang thread khác. Nếu dùng servlet container hoặc executor tùy biến, hãy kiểm tra hỗ trợ thực tế thay vì suy ra rằng mọi controller đều luôn chạy trên virtual thread.

### 4.2. Task execution và `@Async`

Khi không có executor tùy biến làm thay đổi auto-configuration, Spring Boot cấu hình `AsyncTaskExecutor` dựa trên `SimpleAsyncTaskExecutor` sử dụng virtual threads khi property bật. Các tích hợp có thể sử dụng nó gồm `@EnableAsync`/`@Async`, xử lý bất đồng bộ của Spring MVC và một số thành phần khác.

- Chỉ gắn `@Async` vào method là chưa đủ nếu thiếu `@EnableAsync` hoặc gọi tự thân trong cùng object khiến lời gọi bỏ qua Spring proxy.
- Nếu ứng dụng tự tạo `Executor`, `AsyncConfigurer` hoặc bean `applicationTaskExecutor`, executor đó có thể được ưu tiên và **không nhất thiết dùng virtual threads**.
- `SimpleAsyncTaskExecutor` tạo thread theo tác vụ; nó **không phải thread pool**. Các cấu hình như `spring.task.execution.pool.core-size`, `max-size`, `queue-capacity` không có ý nghĩa đối với executor dạng này như khi dùng `ThreadPoolTaskExecutor`.
- Tùy phiên bản Boot, cấu hình nâng cao về executor có thêm lựa chọn ưu tiên auto-configuration; luôn đối chiếu phiên bản đang chạy trước khi thay đổi.

### 4.3. Scheduled tasks

Khi Spring Boot tự cấu hình scheduler trong môi trường bật virtual threads, nó sử dụng `SimpleAsyncTaskScheduler`, không phải `ThreadPoolTaskScheduler`. Vì thế các thuộc tính quản lý kích thước scheduler pool (ví dụ `spring.task.scheduling.pool.size`) không còn tác dụng như với pool truyền thống.

**Điểm dễ bỏ sót:** đối với `SimpleAsyncTaskScheduler`, các tác vụ `fixedDelay` được xử lý theo cơ chế một scheduler thread, còn `fixedRate`/cron có thể tạo luồng thực thi riêng. Cần đo và kiểm thử nếu có tác vụ định kỳ chạy lâu hoặc yêu cầu không chồng lấn.

Virtual threads đều là **daemon threads**. Nếu một ứng dụng không có non-daemon thread nào giữ JVM chạy (đặc biệt ứng dụng chỉ chạy scheduled tasks), JVM có thể thoát. Dùng `spring.main.keep-alive=true` để tránh trường hợp đó khi phù hợp.

### 4.4. WebFlux và Netty

Property không biến Netty event loop của Spring WebFlux thành một tập virtual threads. WebFlux tiếp tục dùng kiến trúc phản ứng/event-loop; một số tác vụ blocking được tích hợp qua `applicationTaskExecutor` có thể sử dụng virtual threads nếu auto-configuration phù hợp.

Do đó, lợi ích trực tiếp, dễ quan sát nhất trong bài này nằm ở **Spring MVC + Tomcat/Jetty**. Đừng coi việc bật virtual threads là lý do để tùy tiện thực hiện blocking I/O trên event-loop của WebFlux.

## 5. Ví dụ chạy được: xác nhận HTTP request đang dùng virtual thread

Tạo dự án **Spring Boot 3.x từ 3.2 trở lên**, **Java 21+**, dependency **Spring Web** (`spring-boot-starter-web`). Ví dụ đặt package là `com.example.demo` và dùng embedded Tomcat mặc định.

**File 1 — `src/main/java/com/example/demo/DemoApplication.java`**

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

**File 2 — `src/main/java/com/example/demo/ThreadProbeController.java`**

```java
package com.example.demo;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
public class ThreadProbeController {

    @GetMapping("/thread-info")
    public ThreadInfo threadInfo() {
        Thread current = Thread.currentThread();
        return new ThreadInfo(current.isVirtual(), current.threadId());
    }

    @GetMapping("/wait")
    public ThreadInfo waitFor(
            @RequestParam(defaultValue = "200") long ms
    ) throws InterruptedException {
        if (ms < 0 || ms > 2000) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "ms must be between 0 and 2000"
            );
        }

        Thread.sleep(ms);
        return threadInfo();
    }

    public record ThreadInfo(boolean virtual, long threadId) {}
}
```

**File 3 — `src/main/resources/application.properties`**

```properties
spring.threads.virtual.enabled=true
spring.main.keep-alive=true
server.port=8080
```

Chạy dự án:

```bash
java -version
mvn spring-boot:run
```

Mở terminal khác:

```bash
curl -s http://localhost:8080/thread-info
curl -s "http://localhost:8080/wait?ms=200"
```

Với Tomcat mặc định, cấu hình được áp dụng và không có executor tùy biến cản trở, JSON có dạng:

```json
{"virtual":true,"threadId":73}
```

`threadId` ở đây **chỉ là giá trị minh họa**: con số thực tế thay đổi theo JVM và request. Trên môi trường hỗ trợ, `"virtual":true` mới là dấu hiệu quyết định. `/wait` trả về cấu trúc tương tự sau khi chờ khoảng 200 ms; `Thread.sleep` là thao tác chờ minh họa, **không phải ví dụ xử lý dữ liệu hay benchmark throughput thực tế**. Response HTTP được serialize sau khi handler trả về; ví dụ đo thread trong chính handler.

Để so sánh, đổi duy nhất:

```properties
spring.threads.virtual.enabled=false
```

Sau đó **khởi động lại** và gọi `/thread-info`. Với embedded Tomcat mặc định, kết quả dự kiến là `"virtual":false` vì request xử lý trên platform thread. Nếu kết quả không đổi, kiểm tra JDK chạy thật, phiên bản Boot, profile đang kích hoạt và server/executor tùy biến.

**Quan trọng:** controller không tạo thread thủ công. Nó hỏi trực tiếp thread đang thực thi handler. Cách kiểm tra này chính xác hơn việc đoán từ tên thread: virtual threads có thể có tên trống hoặc tên phụ thuộc executor và phiên bản.

## 6. Lợi ích thực tế và các giới hạn không thay đổi

### 6.1. Khi nào đáng thử?

Ví dụ một endpoint thực hiện:

```text
HTTP request
  -> đọc DB (phần lớn thời gian chờ I/O)
  -> gọi API từ xa (tiếp tục chờ)
  -> tính toán ngắn
  -> HTTP response
```

Khi có nhiều request như vậy cùng lúc, mô hình platform-thread-per-request thường cần nhiều worker thread bị chặn; virtual threads có thể cho phép tăng concurrency với ít carrier bị chiếm giữ hơn. Hệ quả có thể là **throughput cao hơn hoặc dùng tài nguyên hiệu quả hơn dưới tải blocking I/O lớn**.

Tuy nhiên, virtual threads **không bảo đảm từng request trả nhanh hơn** và không giúp đáng kể cho thuật toán CPU-bound. Nếu DB đã đạt giới hạn CPU/connections, hệ thống upstream áp dụng rate limit hoặc máy chủ thiếu RAM, bật virtual threads không loại bỏ các giới hạn đó.

### 6.2. Các giới hạn cần giữ

- **JDBC connection pool** (chẳng hạn HikariCP) vẫn có số connection tối đa; nhiều virtual thread có thể cùng chờ để lấy connection. `spring.datasource.hikari.maximum-pool-size` là vấn đề riêng, không tự tăng theo số virtual thread.
- **HTTP outbound connection pool**, rate limit, số socket, giới hạn request, hàng đợi và timeout của service khác vẫn tồn tại.
- **Servlet container limits** về kết nối, request và các tài nguyên không phải worker-thread pool vẫn có thể áp dụng.
- **Backpressure và bảo vệ downstream:** nếu bỏ giới hạn platform worker threads, ứng dụng có thể gửi quá nhiều công việc vào DB/service phụ thuộc. Khi cần giới hạn số thao tác đồng thời, dùng cơ chế thích hợp như `Semaphore`, giới hạn connection pool hoặc rate limiter; **không tạo pool virtual threads chỉ để giới hạn concurrency**.
- **ThreadLocal, transaction, security context:** virtual threads vẫn hỗ trợ `ThreadLocal`, nhưng mỗi tác vụ có thể dùng thread riêng. Không dựa vào việc thread được tái sử dụng để cache đối tượng nặng; giữ đúng request/transaction scope, đóng tài nguyên và tránh lưu mutable state chung trong singleton controller.
- **Cấu hình pool truyền thống:** khi Tomcat sử dụng virtual thread executor, các thiết lập như `server.tomcat.threads.max` và `server.tomcat.threads.min-spare` không còn mang ý nghĩa giới hạn worker platform thread như trước. Không nhầm với giới hạn connection, DB pool hoặc bộ nhớ.

Ví dụ ngắn về bảo vệ một tài nguyên giới hạn:

```java
// Minh họa bên trong một service; externalCall() là logic do ứng dụng tự định nghĩa.
private final java.util.concurrent.Semaphore permits =
        new java.util.concurrent.Semaphore(10);

public String callLimitedService() throws InterruptedException {
    permits.acquire();
    try {
        return externalCall();
    } finally {
        permits.release();
    }
}
```

Đoạn này **không độc lập biên dịch** vì `externalCall()` do ứng dụng cung cấp. Ý nghĩa: cho tối đa 10 lời gọi đồng thời đến tài nguyên nhạy cảm, dù hệ thống có hàng nghìn virtual threads đang chờ.

## 7. Pinning, phiên bản Java và lựa chọn vận hành

**Pinning** xảy ra khi virtual thread không thể tháo khỏi carrier trong một đoạn blocking nhất định, khiến carrier bị giữ lại. Khi tình huống này lặp lại nhiều lần và kéo dài, khả năng mở rộng có thể giảm.

- Trên **Java 21–23**, blocking trong một số đoạn `synchronized` và native code có thể gây pinning. Không phải mọi `synchronized` đều gây vấn đề: rủi ro đáng kể khi có blocking lâu/dày đặc bên trong.
- **Java 24+** có cải tiến **JEP 491** nhằm tránh phần lớn pinning do monitor/`synchronized`. Một số tình huống liên quan native/foreign code vẫn cần theo dõi. Đó là lý do tài liệu Spring Boot khuyến nghị Java 24+ để có trải nghiệm virtual threads tốt hơn khi môi trường cho phép.
- Trên môi trường Java 21, có thể dùng JDK Flight Recorder để theo dõi sự kiện `jdk.VirtualThreadPinned` và công cụ thread dump. Hướng dẫn và khả năng chẩn đoán cụ thể phụ thuộc phiên bản JDK; không nên áp dụng cờ gỡ lỗi của JDK 21 cho JDK mới mà không kiểm tra tài liệu phiên bản tương ứng.

Tạo thread dump có hiển thị virtual threads (lệnh chạy trên máy có JDK hỗ trợ):

```bash
jcmd <pid> Thread.dump_to_file -format=json threads.json
```

Thay `<pid>` bằng PID thật của tiến trình Java. Lệnh tạo file `threads.json` để phân tích; số lượng, trạng thái và tên thread phụ thuộc tải đang chạy. Đây là công cụ quan sát, **không có stdout cố định** và không dùng chỉ số đếm thread đơn lẻ để kết luận hệ thống đã nhanh hơn.

Khi thử nghiệm production/staging, so sánh **trước và sau** trên cùng loại workload: requests/second, p95/p99 latency, lỗi/timeouts, CPU, RAM/GC, DB pool wait, outbound pool, số kết nối đang mở, thread dump và JFR khi cần. Một request ngủ 200 ms trong demo chỉ xác nhận cách thực thi; nó không chứng minh cải thiện hiệu năng.

## 8. Các lỗi cấu hình và cách chẩn đoán

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Đã bật property nhưng `isVirtual()` vẫn là `false` | Runtime Java chưa đủ 21; Boot chưa hỗ trợ; profile ghi đè; server/executor tùy biến | Xem `java -version` thực tế, phiên bản Boot, nguồn cấu hình có hiệu lực, loại servlet container |
| `@Async` vẫn chạy trên platform thread | `@Async` thiếu `@EnableAsync`, gọi self-invocation, hoặc có custom `Executor`/`AsyncConfigurer` | Xem bean executor thực dùng và cách gọi qua Spring proxy |
| Chỉnh `spring.task.execution.pool.max-size` nhưng không có hiệu quả | Executor đã chuyển sang `SimpleAsyncTaskExecutor` dùng virtual threads, không có pool để resize | Quan sát loại executor; giới hạn downstream bằng cơ chế phù hợp |
| Chỉnh `server.tomcat.threads.max` nhưng không thấy giới hạn như cũ | Tomcat xử lý request bằng virtual threads | Phân biệt worker thread pool và giới hạn connections/DB |
| Ứng dụng chỉ có scheduled tasks rồi thoát | Virtual threads là daemon; không còn non-daemon thread giữ JVM | Dùng `spring.main.keep-alive=true` và kiểm tra lifecycle |
| Throughput không cải thiện hoặc thấp hơn | Công việc CPU-bound, pinning, DB/HTTP pool nhỏ, rate limit, lock hoặc contention | Kiểm tra profiler/JFR, p95/p99 và bottleneck thực trước khi điều chỉnh |
| WebFlux trên Netty vẫn có event-loop threads | Property không tự chuyển toàn bộ Netty event loop sang virtual threads | Xác định tác vụ blocking có dùng `applicationTaskExecutor` hay không |

Không suy từ việc property đã xuất hiện trong file rằng luồng ảo chắc chắn đang được dùng. **Kiểm tra thread thật trong đúng code path cần đánh giá**, như endpoint `/thread-info`, và kiểm tra cấu hình các executor riêng.

## 9. Câu hỏi tự kiểm tra

1. **Cần Java mấy để bật virtual threads bằng property này?** Java **21 trở lên**, trên Spring Boot có hỗ trợ (3.2+).
2. **Bật `spring.threads.virtual.enabled=true` có làm controller tính toán CPU chạy nhanh hơn?** Không; virtual thread hỗ trợ concurrency khi phần lớn thời gian là chờ I/O, không tăng tốc CPU.
3. **Vì sao `@Async` vẫn có thể chạy trên platform thread?** Vì có thể dùng executor/`AsyncConfigurer` tùy biến, hoặc lời gọi không đi qua Spring proxy.
4. **Cấu hình Tomcat `server.tomcat.threads.max` còn giới hạn virtual threads theo cách cũ không?** Không. Nó là cấu hình worker pool truyền thống; các giới hạn tài nguyên khác vẫn có hiệu lực.
5. **Một ứng dụng chỉ chạy `@Scheduled` có thể tự thoát vì sao?** Virtual threads là daemon; cần xem xét `spring.main.keep-alive=true`.
6. **Khi bật property, làm sao xác nhận một request MVC chạy trên luồng ảo?** In/tra `Thread.currentThread().isVirtual()` ngay trong handler dưới cấu hình server phù hợp.
7. **Cần tạo pool virtual threads để tránh quá tải DB không?** Không; giữ giới hạn DB pool và dùng semaphore/rate limit khi cần.

## 10. Tài liệu chính thức để tra cứu theo phiên bản

- Spring Boot — Virtual threads: https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html#features.spring-application.virtual-threads
- Spring Boot — Task Execution and Scheduling: https://docs.spring.io/spring-boot/3.5/reference/features/task-execution-and-scheduling.html
- Spring Boot 3.2 Release Notes — hỗ trợ virtual threads cho Tomcat/Jetty và executor: https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.2-Release-Notes
- Oracle — Virtual Threads (Java 21): https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html
- OpenJDK — JEP 491, cải tiến pinning trong Java 24: https://openjdk.org/jeps/491

**Kết luận:** với **Spring Boot 3.2+ và Java 21+**, bật `spring.threads.virtual.enabled=true` để những thành phần Spring Boot có hỗ trợ sử dụng virtual threads. Bắt đầu bằng thử nghiệm Spring MVC + Tomcat, xác nhận bằng `Thread.currentThread().isVirtual()`, giữ các giới hạn DB/downstream và đo tải thực trước khi triển khai rộng.