# Ảnh hưởng của nhận đồng bộ đến luồng xử lý HTTP hoặc tác vụ

> **Chủ đề:** Nhận đồng bộ trong Spring Framework JMS. `JmsTemplate.receive(...)` và `receiveAndConvert(...)` cho phép lấy message ngay trong luồng Java đang chạy. Cách này đơn giản nhưng **luồng gọi phải chờ cho tới khi có message, hết timeout hoặc xảy ra lỗi**. Nếu gọi trực tiếp trong HTTP controller hoặc một task có số worker giới hạn, ứng dụng có thể tiêu tốn hết luồng xử lý dù CPU gần như nhàn rỗi.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:
1. Phân biệt **nhận JMS đồng bộ** với **xử lý message bất đồng bộ bằng `@JmsListener`**.
2. Giải thích vì sao `receive` trong controller làm tăng thời gian phản hồi HTTP, giữ servlet thread và giảm throughput khi queue trống.
3. Phân biệt `receiveTimeout = 0` (chờ vô hạn), giá trị dương (chờ có giới hạn) và giá trị âm như `-1` (không chờ).
4. Đánh giá cùng vấn đề khi chạy trong scheduler, `@Async`, thread pool hoặc virtual thread.
5. Chạy một ví dụ **Java 17 + Spring Boot 3.3.5 + ActiveMQ Artemis** để quan sát HTTP 204 sau thời gian chờ và HTTP 200 khi nhận được message.
6. Chọn giữa **HTTP 202 + background consumer**, **polling có giới hạn** và **request–reply JMS có deadline** theo yêu cầu nghiệp vụ.
7. Nhận diện lỗi về acknowledgement, message bị lấy mất, timeout HTTP/JMS lệch nhau, thiếu capacity và cancellation.

**Thông điệp cốt lõi:** `receiveTimeout` hạn chế thời gian chờ của một lần JMS receive, **không biến API đồng bộ thành bất đồng bộ** và cũng không phải deadline tổng thể cho HTTP request.

## 2. Nhận đồng bộ nghĩa là gì?

JMS hỗ trợ consumer nhận bằng API cổ điển:

~~~java
// Snippet: consumer được tạo từ Session thuộc Connection đã start.
Message message = consumer.receive();        // Có thể đợi vô hạn.
Message message2 = consumer.receive(2000L);  // Đợi tối đa ~2 giây.
Message message3 = consumer.receiveNoWait();  // Không đợi message.
~~~

Mỗi lời gọi trên chạy **trong thread hiện tại**. Trong trường hợp `receive()` chờ message, thread không thể tiếp tục các dòng Java bên dưới cho tới khi thao tác nhận kết thúc.

Spring JMS bọc logic đó bằng `JmsTemplate`:

~~~java
// Snippet: jmsTemplate đã cấu hình ConnectionFactory và queue phù hợp.
jmsTemplate.setReceiveTimeout(2_000L);
Object body = jmsTemplate.receiveAndConvert("demo.sync.receive");
~~~

`JmsTemplate` còn có `receive(queueName)` (trả raw `jakarta.jms.Message`), `receiveSelected(...)` và `receiveSelectedAndConvert(...)` khi cần JMS selector. `receiveAndConvert` có thêm bước `MessageConverter.fromMessage` sau nhận. Dù có converter, việc **chờ message vẫn là đồng bộ**.

Theo Spring Framework, synchronous receive **blocks the calling thread**; thuộc tính `receiveTimeout` quyết định giới hạn đợi ở thao tác consumer receive. Nếu không cấu hình, mặc định của riêng `JmsTemplate` là **chờ vô hạn**. Không nhầm với mặc định `receiveTimeout` của một số listener container polling: đó là thuộc tính của **loại component khác**.

## 3. Ba giá trị `receiveTimeout` cần ghi nhớ

| `JmsTemplate.setReceiveTimeout(...)` | Ý nghĩa trong Spring JMS | Kết quả khi queue rỗng | Rủi ro trong HTTP |
| --- | --- | --- | --- |
| `0L` | `RECEIVE_TIMEOUT_INDEFINITE_WAIT`: gọi receive chờ cho tới khi có message hoặc lỗi | Có thể chờ vô hạn | Một request thread có thể bị giữ không xác định thời gian |
| `2_000L` | Chờ message tối đa khoảng 2000 ms | `receive` trả `null` khi hết chờ; `receiveAndConvert` trả `null` | Mỗi HTTP request vẫn có thể chiếm thread khoảng 2 giây |
| `-1L` hoặc số âm khác | `RECEIVE_TIMEOUT_NO_WAIT`: gọi receiveNoWait | Trả `null` gần như ngay nếu không có message | Ít đợi message nhưng vẫn tốn chi phí kết nối/JMS; không đồng nghĩa API bất đồng bộ |

**Không nhầm:** `-1` là **không chờ**, `0` mới là **chờ vô hạn** trong `JmsTemplate`. Dễ hiểu sai vì nhiều API HTTP dùng “-1” hoặc “0” theo quy ước timeout khác.

Các lưu ý:
- Đơn vị là **mili giây**, không phải giây.
- Hết timeout mà không có message thường trả `null`, không tự động ném “timeout exception”.
- Timeout của `receive` không phải thời gian tối đa chắc chắn cho **tạo connection, acquire session từ pool, TLS handshake, DNS, broker reconnect, convert payload, xử lý business hoặc serialize HTTP response**. Các bước đó có deadline riêng và có thể làm tổng thời gian dài hơn.
- Khi broker lỗi, `JmsTemplate` thường ném `org.springframework.jms.JmsException` (runtime) thay vì trả `null`. Cần phân biệt “queue không có message” với “dịch vụ JMS không khả dụng”.
- Cấu hình timeout trên một bean `JmsTemplate` dùng chung nên đặt **một lần lúc khởi tạo**. Không tăng/giảm `setReceiveTimeout` trong từng HTTP request vì request concurrent có thể dùng nhầm cấu hình.

## 4. Điều gì xảy ra nếu gọi `receive` trong HTTP controller?

Một HTTP controller kiểu Spring MVC chạy trên thread do servlet container (ví dụ Tomcat) cấp phát. Nếu method gọi `receiveAndConvert`, thread đó phải đợi broker:

~~~text
HTTP Client
    |
    | POST /demo/receive
    v
Tomcat HTTP worker thread #17
    |
    | controller.receive()
    v
JmsTemplate.receiveAndConvert("demo.sync.receive")
    |
    |  Queue rỗng: đợi message trong 2 giây
    |  [thread #17 bị giữ; không xử lý request khác]
    |
    +--> Có message: trả dữ liệu
    +--> Hết timeout: trả null
    +--> JMS lỗi: ném exception
    |
    v
Controller tạo HTTP response
    |
    v
HTTP Client nhận 200 / 204 / 503 tùy trường hợp
~~~

Trong lúc chờ broker, CPU của thread có thể thấp vì JVM/provider đang block chờ I/O. **CPU thấp không có nghĩa hệ thống còn khả năng nhận thêm request**: worker thread và một số connection/session JMS vẫn là tài nguyên hữu hạn.

### 4.1. Độ trễ HTTP

Giả sử:
- Controller có phần kiểm tra đầu vào `10 ms`.
- Queue rỗng và `receiveTimeout=2000 ms`.
- Đóng gói response mất khoảng `5 ms`.

Một request HTTP có thể mất xấp xỉ `2015 ms`, chưa kể network, pool contention, broker setup. Đây chỉ là **ví dụ số học**, không phải cam kết độ trễ chính xác. Nếu broker giao message sau 50 ms, cùng request có thể kết thúc nhanh hơn.

Nếu HTTP gateway timeout `1 giây` nhưng JMS nhận với timeout `5 giây`, người gọi có thể đã nhận `504 Gateway Timeout` **trong khi Java vẫn đang chờ JMS thêm vài giây**. Client đóng socket không bảo đảm provider sẽ lập tức hủy một lệnh JMS receive đang chặn.

### 4.2. Khả năng phục vụ khi nhiều request đồng thời

Giả sử có **20 HTTP worker threads** và request nào cũng gọi receive trên queue rỗng, mỗi lần chờ `2 giây`:

~~~text
T=0s:
  Request #01..#20 chiếm toàn bộ 20 threads -> receive đợi 2s
  Request #21..#40 không có worker rảnh -> chờ trong hàng đợi HTTP

T≈2s:
  #01..#20 kết thúc với 204
  #21..#40 mới được thực thi, tiếp tục đợi 2s

T≈4s:
  #21..#40 kết thúc (nếu không có lỗi/timeout ở tầng trước)
~~~

Nếu **toàn bộ** năng lực worker bị chiếm bởi các receive rỗng có thời gian đợi trung bình `W`, throughput lý thuyết dành cho loại request này xấp xỉ:

~~~text
throughput ≈ số worker / thời gian giữ worker

20 workers / 2 giây ≈ 10 requests/giây
~~~

Đây là mô hình đơn giản để thấy **thread starvation**, không phải phép đo broker thật. Tạo JMS consumer/session, network overhead và thời gian trả response làm throughput thực có thể thấp hơn. Nếu HTTP server còn phải xử lý login, health endpoint và request nghiệp vụ khác, việc 20 threads bị kẹt có thể làm **toàn bộ API suy giảm**.

### 4.3. Khi HTTP request dùng receive, nó đang tiêu thụ message

Một JMS `receive` trên queue không phải truy vấn “xem thử” an toàn như HTTP GET:
- Message có thể được **lấy khỏi queue** và được acknowledge theo mode/session.
- Một request của người dùng có thể lấy message mà worker nghiệp vụ vốn phải xử lý.
- Người dùng đóng tab hoặc HTTP response lỗi sau khi JMS nhận **không tự phục hồi message** đã được acknowledge.
- Hai HTTP request cùng gọi receive có thể cạnh tranh nhận **hai message khác nhau** hoặc một request timeout; không được tự suy ra thứ tự message đi tới từng client.

Vì thế, endpoint minh họa ở phần thực hành sẽ dùng **HTTP POST**, không dùng GET cho hành động tiêu thụ message. Không chạy mẫu trên queue production đang có consumer nghiệp vụ.

## 5. Luồng tác vụ nền cũng chịu ảnh hưởng

Vấn đề không chỉ nằm ở HTTP request. Một background job dùng `receive` cũng chiếm thread cho tới khi message tới hoặc timeout:

~~~text
TaskExecutor (pool size = 4)
   |
   +-- task A -> receive() chờ
   +-- task B -> receive() chờ
   +-- task C -> receive() chờ
   +-- task D -> receive() chờ
   |
   +-- task E -> không có thread rảnh để chạy
~~~

### 5.1. `@Async` không biến JMS receive thành non-blocking

Khi một method có `@Async` gọi `jmsTemplate.receive(...)`:
- HTTP caller có thể sớm trả response vì đã **chuyển việc sang thread khác**.
- Nhưng **thread của `TaskExecutor` vẫn block** trong JMS receive.
- Nếu executor có 4 workers, 4 lần receive vô hạn có thể làm các tác vụ còn lại xếp hàng.
- Executor queue không giới hạn có thể khiến backlog/memory tăng và che giấu tình trạng thiếu capacity; cấu hình bounded queue và rejection policy rõ ràng.

`CompletableFuture.supplyAsync(() -> template.receive(...), executor)` cũng là **offload blocking I/O**, không phải JMS receiver bất đồng bộ thực sự. `CompletableFuture.cancel(...)` hoặc việc client ngắt HTTP không bảo đảm mọi JMS provider có thể bị interrupt và dừng tiêu thụ ngay tại thời điểm đó.

### 5.2. `@Scheduled` polling

Một scheduler gọi `receive` với timeout quá lớn có thể trì hoãn các lần chạy tiếp theo. Với scheduler ít worker, một job chờ JMS có thể làm những job khác bị trễ. Nếu chỉ cần **kiểm tra nhanh rồi làm việc khác**, có thể dùng template riêng với `receiveTimeout=-1` và lịch polling hợp lý. Song polling liên tục làm phát sinh chi phí kết nối/session, broker requests và độ trễ giữa hai lần poll.

**Không dùng `Thread.sleep` trong vòng lặp vô hạn ở một thread HTTP** để “chờ queue có message”. Nếu đã cần nhận message lâu dài, ưu tiên listener container.

### 5.3. Virtual threads và reactive web

Virtual threads có thể giảm chi phí giữ **OS platform thread** khi block, nhưng không xóa timeout, quota broker, session ownership, JMS connection pool, CPU business processing hay yêu cầu ACK/transaction. Hành vi pinning và mức độ hỗ trợ I/O phụ thuộc JVM/provider. Cần benchmark thực tế trước khi thay đổi giả định capacity.

Trong Spring WebFlux/event-loop, gọi trực tiếp blocking `JmsTemplate.receive` trên event-loop thread là đặc biệt nguy hiểm. Offload sang bounded worker scheduler có thể bảo vệ event loop, **nhưng thao tác JMS vẫn đang block ở worker đó**. Nếu kiến trúc cần consumer lâu dài, dùng `@JmsListener` hoặc adapter phù hợp thay vì polling JMS trực tiếp trong request path.

## 6. Ví dụ chạy được: nhận đồng bộ trong một HTTP endpoint

Ví dụ dùng **Java 17 + Spring Boot 3.3.5 + Spring MVC + ActiveMQ Artemis**. Hai endpoint:

- `POST /demo/send?text=hello` gửi một String vào queue thử.
- `POST /demo/receive` nhận **một** message từ queue; nếu queue rỗng, chờ tối đa 2 giây rồi trả **204 No Content**.

**Mục đích:** cho thấy rằng HTTP worker chờ trong `receiveAndConvert`. Đây là thí nghiệm chứng minh nhược điểm, **không phải mẫu kiến trúc API khuyến nghị cho production**.

### 6.1. Broker và queue

Cần broker Artemis ở `tcp://localhost:61616`, tài khoản `demo/demo` và queue anycast `demo.sync.receive`. Với broker học tập bật auto-create queue, tài nguyên có thể được tạo tự động. Để dễ chẩn đoán, nên provision queue riêng trước và không có consumer khác tranh chấp. Credentials chỉ dành cho môi trường test; dùng secret manager/TLS ở production.

Nếu broker không hoạt động, ứng dụng có thể vẫn khởi động nhưng send/receive sẽ thất bại khi truy cập broker. Không diễn giải lỗi kết nối là hành vi timeout do queue rỗng.

### 6.2. Cấu trúc project

~~~text
http-blocking-jms/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/demo/
    │   ├── BlockingReceiveApplication.java
    │   └── DemoController.java
    └── resources/application.yml
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'http-blocking-jms'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
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
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-artemis'
}
~~~

`src/main/resources/application.yml`:

~~~yaml
server:
  port: 8080
spring:
  artemis:
    mode: native
    broker-url: "tcp://localhost:61616"
    user: "demo"
    password: "demo"
~~~

Spring Boot cấu hình `ConnectionFactory` từ `spring.artemis.*`. Đoạn cấu hình là demo cục bộ; không commit mật khẩu thật trong ứng dụng doanh nghiệp.

### 6.3. Cấu hình JmsTemplate timeout hữu hạn

`src/main/java/demo/BlockingReceiveApplication.java`:

~~~java
package demo;

import jakarta.jms.ConnectionFactory;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.core.JmsTemplate;

@SpringBootApplication
public class BlockingReceiveApplication {

    public static void main(String[] args) {
        SpringApplication.run(BlockingReceiveApplication.class, args);
    }

    @Bean
    JmsTemplate demoJmsTemplate(ConnectionFactory connectionFactory) {
        JmsTemplate template = new JmsTemplate(connectionFactory);
        template.setReceiveTimeout(2_000L);
        return template;
    }
}
~~~

Khai báo bean riêng để timeout được cấu hình **trước khi nhận HTTP requests**. `JmsTemplate` thường có thể dùng lại giữa nhiều thread ở tầng ứng dụng, nhưng mỗi lần `receiveAndConvert` vẫn phải chờ message và sử dụng tài nguyên JMS theo cấu hình `ConnectionFactory`.

### 6.4. Controller gửi một message và nhận đồng bộ

`src/main/java/demo/DemoController.java`:

~~~java
package demo;

import java.util.concurrent.TimeUnit;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.jms.JmsException;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    private static final String QUEUE = "demo.sync.receive";
    private final JmsTemplate template;

    public DemoController(JmsTemplate template) {
        this.template = template;
    }

    @PostMapping("/demo/send")
    public ResponseEntity<String> send(
            @RequestParam(defaultValue = "hello") String text) {

        if (text.length() > 100) {
            return ResponseEntity.badRequest().body("TEXT_TOO_LONG");
        }

        try {
            template.convertAndSend(QUEUE, text);
            return ResponseEntity.ok("SENT");
        } catch (JmsException ex) {
            System.err.println(
                    "SEND_FAILED type=" + ex.getClass().getSimpleName());
            return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                    .body("JMS_UNAVAILABLE");
        }
    }

    @PostMapping("/demo/receive")
    public ResponseEntity<String> receive() {

        String threadName = Thread.currentThread().getName();
        long started = System.nanoTime();

        try {
            // Chính HTTP request thread sẽ chờ tại đây.
            Object result = template.receiveAndConvert(QUEUE);

            long elapsedMs = TimeUnit.NANOSECONDS.toMillis(
                    System.nanoTime() - started);

            System.out.println("RECEIVE_THREAD=" + threadName
                    + " ELAPSED_MS=" + elapsedMs
                    + " EMPTY=" + (result == null));

            if (result == null) {
                return ResponseEntity.noContent().build(); // HTTP 204
            }
            if (!(result instanceof String text)) {
                throw new IllegalStateException(
                        "Expected String payload");
            }
            return ResponseEntity.ok("RECEIVED " + text); // HTTP 200

        } catch (JmsException ex) {
            System.err.println("RECEIVE_FAILED type="
                    + ex.getClass().getSimpleName());
            return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                    .body("JMS_UNAVAILABLE"); // HTTP 503
        }
    }
}
~~~

**Vì sao đây là chương trình chạy được?**

- Có một `public class` khớp với tên mỗi file Java, package `demo` nhất quán, dependency Spring MVC và Artemis JMS đủ cho hai endpoint.
- `JmsTemplate` đã có `receiveTimeout=2000`, nên khi **broker đang chạy và queue rỗng**, nhận không đợi vô hạn.
- `SimpleMessageConverter` mặc định chuyển String thành `TextMessage` khi gửi và trả String khi `receiveAndConvert`.
- `TimeUnit.NANOSECONDS.toMillis` chỉ đo thời gian ở bên trong Java (gồm JMS receive và setup), không hứa đúng 2000 ms tuyệt đối.
- `Thread.currentThread().getName()` giúp thấy request đang chạy trên HTTP worker thread của servlet container.
- `POST` được dùng cho thao tác receive vì việc lấy message khỏi queue **có tác dụng thay đổi trạng thái**, không nên trình bày như GET chỉ đọc.
- Mẫu bắt `JmsException` để trả 503 khi hạ tầng JMS lỗi, phân biệt với 204 khi queue trống. Lỗi validation/non-JMS khác không cố tình bị biến thành “queue rỗng”.

**Không dùng endpoint này như API production.** Nó bỏ qua authentication/authorization của HTTP, rate limiting, retry, audit và thiết kế acknowledgement phù hợp với nghiệp vụ.

### 6.5. Chạy và thử bằng HTTP

Ở thư mục project, với JDK 17+, Gradle và broker có sẵn:

~~~bash
gradle bootRun
~~~

**Thử A: queue trống.** Nếu chưa có message, gọi:

~~~bash
curl -i -X POST http://localhost:8080/demo/receive
~~~

Phản hồi dự kiến có status:

~~~text
HTTP/1.1 204
~~~

Status thực có thể hiển thị thành `HTTP/1.1 204 No Content`, phụ thuộc server/client. Độ trễ thường gần `2 giây` khi queue trống; dùng `curl -w` hoặc xem `ELAPSED_MS` trong log. Nếu chạy PowerShell, dùng `curl.exe` để tránh alias cũ của `curl`.

**Thử B: đã có message.** Gửi và nhận tuần tự:

~~~bash
curl -i -X POST "http://localhost:8080/demo/send?text=hello"
curl -i -X POST http://localhost:8080/demo/receive
~~~

Phần body HTTP dự kiến:

~~~text
SENT
RECEIVED hello
~~~

Lần receive này thường nhanh hơn vì có message đang chờ. Nếu queue chứa message cũ hoặc consumer khác cùng tranh chấp, body có thể khác hoặc timeout. Để giữ kết quả rõ ràng, dùng queue riêng đã dọn trước, hoặc thiết kế selector theo ID cho thử nghiệm phức tạp hơn.

**Thử C: quan sát luồng đang chờ.** Mở 2 terminal, gọi `/demo/receive` trên queue trống ở cả hai cửa sổ gần như cùng lúc. Log sẽ cho thấy hai dòng `RECEIVE_THREAD` với thread names khác nhau sau khi đợi xong. Nhiều request đồng thời sẽ giữ nhiều HTTP worker threads trong khoảng thời gian chờ.

### 6.6. Nếu muốn tăng tải để thấy thread starvation

Chỉ thử trên môi trường riêng với mức tải giới hạn:
1. Đặt thread pool HTTP nhỏ có chủ đích, ví dụ `server.tomcat.threads.max: 4` trong bản copy test.
2. Giữ queue rỗng và gửi 8 HTTP `POST /demo/receive` đồng thời bằng công cụ load test có giới hạn.
3. Quan sát 4 request đầu gần như cùng thời điểm chờ JMS; các request còn lại phải chờ server có worker rảnh.
4. Đo tổng request latency, `http.server.requests`, thread utilization, kết nối JMS và queue depth.

Không bật một phép thử vô hạn gây cạn thread. Không chạy đồng thời trên production. Số liệu thật còn chịu ảnh hưởng thread pool, connection factory, OS scheduling, broker và cấu hình client.

## 7. Vì sao HTTP timeout và JMS timeout phải được phối hợp?

Một request thường đi qua nhiều tầng:

~~~text
Client timeout
      |
      v
CDN / Load Balancer / Gateway timeout
      |
      v
Servlet container / HTTP worker
      |
      v
JmsTemplate.receiveTimeout
      |
      v
JMS provider: connection / session / broker
      |
      v
Message delivery, converter, business logic
~~~

Nếu mỗi tầng tự cấu hình timeout độc lập, hệ thống có thể tạo kết quả khó đoán. Ví dụ:

| Tầng | Timeout ví dụ |
| --- | --- |
| Client HTTP | 1.5 giây |
| Gateway HTTP | 1.0 giây |
| JMS receive | 5.0 giây |
| JMS connection recovery | Có thể chờ lâu hơn |

HTTP client/gateway có thể timeout **trước** khi JMS receive kết thúc. Nếu trong lúc đó một message được giao, consumer có thể lấy/ack message dù người gọi HTTP đã rời đi.

### 7.1. Deadline tổng thể không bằng `receiveTimeout`

Giả sử API phải đáp ứng trong `1500 ms`. Không thể đơn giản đặt `receiveTimeout=1500` rồi coi đã đủ: thời gian setup JMS, convert, xử lý business và truyền HTTP vẫn cộng thêm. Nguyên tắc thiết kế:

~~~text
remainingBudget =
    HTTP_deadline
    - thời gian xử lý trước JMS
    - ngân sách convert/response
    - safety margin
~~~

Nếu phải chờ kết quả, chỉ chờ trong **ngân sách còn lại** và phải có chính sách xử lý khi hết hạn. Với shared `JmsTemplate`, không thay đổi `receiveTimeout` theo từng request vì race condition. Hãy dùng template có timeout cố định cho lớp nghiệp vụ đó hoặc API/abstraction thiết kế riêng cho per-request timeout.

### 7.2. Cancel HTTP không đồng nghĩa rollback JMS

Trong `AUTO_ACKNOWLEDGE`, một synchronous receive thành công thường đã được JMS runtime acknowledge theo quy tắc của session, **không đợi việc gửi HTTP response thành công**. Nếu HTTP response 200 không tới client, message vẫn có thể đã biến mất khỏi queue. Ngược lại, khi cần ack/commit sau một tác vụ nghiệp vụ, phải cấu hình session transaction/container riêng, đồng thời chuẩn bị cho redelivery và duplicate side effect.

Đừng hứa “client retry request sẽ thấy lại cùng message” sau khi lần đầu nhận đã thành công. Queue không phải một kho kết quả truy vấn lại theo request ID.

## 8. So sánh ba kiến trúc thay thế

### 8.1. Cách A: HTTP request trực tiếp gọi `receive`

~~~text
HTTP request ──> Controller ──> JMS receive (chờ) ──> HTTP response
                                   |
                             Queue trống / timeout
~~~

**Phù hợp:** công cụ quản trị cục bộ, bài test, tác vụ thử nghiệm hoặc thao tác rất ít concurrency, có timeout và queue chuyên dụng. **Không phù hợp:** API public nhiều request, yêu cầu latency thấp, health-check bị gọi thường xuyên, hoặc nghiệp vụ có nhiều worker cạnh tranh queue.

### 8.2. Cách B: HTTP nhận lệnh; listener xử lý nền

~~~text
HTTP POST /jobs
      |
      +-- Validate request + tạo jobId
      +-- Publish persistent message vào jobs.queue
      +-- HTTP 202 Accepted + jobId
                     |
                     v
              JMS Broker / Queue
                     |
                     v
        @JmsListener (dedicated worker threads)
                     |
                     +-- Xử lý nghiệp vụ
                     +-- Ghi trạng thái DONE / FAILED
                     +-- ACK / Commit theo cấu hình
                     |
                     v
         HTTP GET /jobs/{jobId} để xem trạng thái
~~~

**Đây thường là lựa chọn tốt hơn** cho tác vụ tốn thời gian hoặc không cần kết quả ngay. HTTP request không phải giữ worker để chờ message đến. Listener container quản lý consumer/concurrency và vận hành retry/ack theo chính sách.

Ví dụ listener (snippet, **không** thêm vào queue `demo.sync.receive` đang dùng trong ví dụ thực hành vì sẽ tranh giành message):

~~~java
// Snippet Spring bean riêng, với JMS listener infrastructure đã bật.
@Component
public class JobConsumer {

    @JmsListener(destination = "demo.jobs", concurrency = "2-4")
    public void handle(String body) {
        // Validate, xử lý nghiệp vụ và ghi job status.
        System.out.println("JOB_RECEIVED=" + body);
    }
}
~~~

Cần imports `org.springframework.stereotype.Component` và `org.springframework.jms.annotation.JmsListener`; cấu hình Spring Boot JMS listener factory hoặc `@EnableJms` phù hợp. `@JmsListener` **cũng sử dụng worker threads**, nhưng thuộc **nhóm listener riêng**, không giữ request threads để đợi queue rỗng. Cấu hình concurrency và transaction phải phù hợp khả năng broker/database; không tăng concurrency vô hạn.

Với mô hình HTTP 202, cần thêm:
- ID job/sự kiện ổn định và **durable status store** để client tra cứu.
- Chống gửi/nhận lặp bằng idempotency key.
- Trạng thái `PENDING/RUNNING/DONE/FAILED` và timeouts nghiệp vụ.
- DLQ/retry và cơ chế replay an toàn.
- Transactional outbox nếu việc ghi database và phát JMS message phải nhất quán.

### 8.3. Cách C: JMS request–reply có timeout

Một số API thực sự phải trả kết quả đồng bộ cho người gọi. Khi đó có thể dùng JMS request–reply:

~~~text
HTTP request
   |
   v
Producer gửi request message (correlationId, replyTo)
   |
   v
Worker consume và xử lý
   |
   v
Worker gửi reply đến reply queue
   |
   v
HTTP caller đợi reply có cùng correlationId
   |
   +-- reply tới kịp -> HTTP 200
   +-- quá deadline -> HTTP 504/202 hoặc status phù hợp
~~~

Cách này có thể cần blocking wait hoặc một cơ chế callback/state để phối hợp reply bất đồng bộ. **Vẫn có timeout và tài nguyên giữ chỗ** nếu chờ trực tiếp trong HTTP worker. Phải thiết kế:
- `JMSCorrelationID`/`JMSReplyTo` và selector chính xác; không dùng reply queue chung mà consumer nào cũng nhận bừa.
- Deadline/TTL của request và reply; xử lý late reply sau khi HTTP đã timeout.
- Số lượng outstanding requests có giới hạn, không tạo vô hạn temporary queues/consumers.
- Idempotency khi client retry và worker có thể nhận lại.
- Mô hình tương thích với gateway timeout và khả năng phục hồi.

Nếu công việc thường mất lâu hoặc kết quả chưa cần ngay, HTTP 202 + status endpoint đơn giản và vững hơn request–reply blocking.

## 9. Polling trong background job: cách dùng có giới hạn

Có tình huống không muốn chạy listener container liên tục (ví dụ một batch job có cửa sổ thời gian cố định). Khi đó **polling ở worker riêng** có thể hợp lý, nhưng nên dùng timeout hữu hạn hoặc no-wait, có lịch chạy và dừng rõ ràng.

Snippet minh họa:

~~~java
// Snippet: đặt trong @Configuration, cần imports Spring/JMS.
@Bean
JmsTemplate pollTemplate(ConnectionFactory factory) {
    JmsTemplate template = new JmsTemplate(factory);
    template.setReceiveTimeout(-1L);  // receiveNoWait
    return template;
}
~~~

Và task polling:

~~~java
// Snippet: @EnableScheduling phải được bật trong cấu hình.
@Component
public class QueuePoller {

    private final JmsTemplate pollTemplate;

    public QueuePoller(@Qualifier("pollTemplate") JmsTemplate pollTemplate) {
        this.pollTemplate = pollTemplate;
    }

    @Scheduled(fixedDelay = 5_000L)
    public void poll() {
        Object msg = pollTemplate.receiveAndConvert("demo.scheduled");
        if (msg != null) {
            process(msg); // Hàm nghiệp vụ do ứng dụng định nghĩa.
        }
    }

    private void process(Object message) {
        System.out.println("TASK_RECEIVED=" + message);
    }
}
~~~

Cần import `jakarta.jms.ConnectionFactory`, `org.springframework.context.annotation.Bean`, `org.springframework.stereotype.Component`, `org.springframework.beans.factory.annotation.Qualifier`, `org.springframework.scheduling.annotation.Scheduled` và `org.springframework.jms.core.JmsTemplate`. Hai khối trên là **snippets**, không phải project runnable độc lập.

Cẩn thận: `receiveAndConvert` trong một scheduled method thường nhận/ack message theo cấu hình session, trước khi `process(msg)` hoàn tất. Nếu cần đảm bảo redelivery khi business xử lý lỗi, dùng listener container có transaction phù hợp hoặc bọc nguyên poll+process trong một JMS transaction rõ ràng. Không coi polling với `receiveTimeout=-1` là tự động reliable.

### 9.1. Tính tải polling

Nếu poll mỗi 5 giây nhưng các lần nhận/convert tốn 1 giây và mỗi lần chỉ lấy một message, throughput tối đa chỉ khoảng **1 message / 6 giây** với `fixedDelay` một worker, bỏ qua các yếu tố khác. Backlog có thể tăng nhanh nếu queue nhận hàng chục message mỗi giây.

Polling quá nhanh (ví dụ liên tục không ngủ) tăng overhead; polling quá chậm tăng latency. Khi cần xử lý event-driven liên tục, listener container thường hợp lý hơn.

## 10. Transaction và acknowledgement trong nhận đồng bộ

Điểm dễ bỏ sót khi nhúng `receive` vào HTTP hoặc task: việc nhận một message **không nhất thiết** thuộc cùng transaction với nghiệp vụ tiếp theo.

### 10.1. Auto-acknowledge

Với `Session.AUTO_ACKNOWLEDGE`, quá trình nhận đồng bộ thành công có cơ chế acknowledge của JMS runtime sau việc trả message theo hợp đồng. Nếu code tiếp tục gọi một database rồi database lỗi, **không được mặc định message sẽ redeliver** chỉ vì HTTP trả 500. Đó là lý do không nên thiết kế “HTTP consume message rồi thực hiện database side effect” mà chưa có transaction rõ ràng.

### 10.2. Transacted JMS session

JMS `Session.SESSION_TRANSACTED` gom receive và acknowledgement vào transaction cục bộ. Khi `commit`, broker coi việc consume hoàn tất; khi `rollback`, message có thể được giao lại. Tuy nhiên, local JMS transaction **không tự động** commit cùng JDBC database transaction.

Một snippet API thấp (không độc lập):

~~~java
// Snippet: connection và queue đã hợp lệ, connection đã start.
try (Session session =
             connection.createSession(Session.SESSION_TRANSACTED);
     MessageConsumer consumer = session.createConsumer(queue)) {

    Message message = consumer.receive(2_000L);

    if (message != null) {
        try {
            handleBusiness(message);
            session.commit();
        } catch (Exception failure) {
            session.rollback();
            throw failure;
        }
    }
}
~~~

Hàm `handleBusiness`, biến `connection`/`queue` và imports `jakarta.jms.*` phải có trong ứng dụng. Vẫn cần idempotency cho tình huống **database commit xong nhưng JMS commit chưa rõ kết quả**.

### 10.3. Listener container và lỗi xử lý

`@JmsListener` thông qua `DefaultMessageListenerContainer` có thể cấu hình `sessionTransacted=true` hoặc transaction manager thích hợp, để lỗi trong callback ảnh hưởng quá trình commit/rollback JMS. Đây là lợi thế so với receive thủ công rồi xử lý không có transaction, nhưng **không tự bảo đảm exactly-once đối với database hoặc API ngoài**.

## 11. Những hiểu nhầm và lỗi phổ biến

| Nhận định/hành động | Vì sao dễ sai | Cách làm phù hợp |
| --- | --- | --- |
| `receiveAndConvert` là non-blocking vì JMS “bất đồng bộ” | API nhận đồng bộ vẫn chặn caller | Dùng `@JmsListener` hoặc offload có pool giới hạn |
| `setReceiveTimeout(0)` là không đợi | Spring quy ước 0 là đợi vô hạn | `-1` cho no-wait; số dương cho giới hạn |
| Có timeout 2 giây nên API chắc trả trong 2 giây | Setup connection, broker recovery, convert và HTTP còn tốn thời gian | Đặt deadline toàn chuỗi và đo latency thực |
| CPU thấp nghĩa HTTP còn khỏe | Các worker bị block không làm CPU cao | Theo dõi active threads, queue length, latency |
| Dùng `@Async` giải quyết hết blocking | Chuyển blocking sang pool khác, pool đó vẫn có thể cạn | Bounded executor, bulkhead, prefer listener |
| Dùng WebFlux rồi gọi JMS receive trên event loop | Block event loop, kéo theo nhiều request khác | Offload tách biệt hoặc thiết kế listener |
| Dùng HTTP GET để lấy message từ JMS queue | Nhận có thể ack/tiêu thụ message | Dùng POST ở demo; production dùng job/state API rõ |
| HTTP client hủy request nghĩa JMS receive cũng hủy | Cancellation không luôn được propagate tới provider | Deadline và cơ chế cleanup/late-result |
| HTTP trả 500 thì JMS message tự quay lại | Message có thể đã ACK trước khi xử lý HTTP xong | Transaction/ACK và idempotency đúng |
| Tăng Tomcat threads là giải pháp lâu dài | Chỉ dời bottleneck sang memory, JMS pool, broker | Tách worker, đo capacity, hạn chế concurrency |
| Có `@JmsListener` thì không dùng thread | Container vẫn có consumer workers | Cấu hình concurrency/transactions theo tải |
| `receiveTimeout=-1` đủ để polling hàng triệu message | Mỗi poll vẫn có JMS overhead và lịch scheduler | Listener/event-driven hoặc throughput design |
| Dùng template singleton đổi timeout trong từng request | Race condition giữa các HTTP callers | Bean chuyên dụng có cấu hình bất biến |

## 12. Quan sát, giám sát và kiểm thử

### 12.1. Chỉ số cần có

- **HTTP:** thời gian đáp ứng p50/p95/p99, RPS, HTTP 204/503/5xx, gateway timeout, active servlet threads, số request chờ.
- **JMS receiver:** số lần receive, số lần timeout/null, receive duration, connection/session acquire latency, broker error và reconnect.
- **Broker:** queue depth, oldest message age, consumer count, pending vs delivering, expired/redelivered messages, quota và DLQ.
- **Background workers:** active threads, executor queue size, rejected tasks, scheduler lag, processing throughput.
- **Nghiệp vụ:** số job PENDING/RUNNING/FAILED, duplicate event ID, thời gian từ publish tới DONE, số lần retry.

Không đánh giá chỉ bằng CPU hoặc việc có log “RECEIVE_OK”. Những hệ thống này có thể CPU thấp nhưng RPS sụt mạnh vì hết HTTP threads.

### 12.2. Ma trận kiểm thử đề xuất

| Ca | Thiết lập | Điều cần xác minh |
| --- | --- | --- |
| Queue rỗng + `receiveTimeout=2000` | Một HTTP request | 204 sau khoảng 2 giây, log thread chờ |
| Queue có một String message | Gửi `hello` trước receive | 200, body `RECEIVED hello`, thường phản hồi nhanh |
| Nhiều request, queue rỗng | Tạo concurrency có giới hạn trong môi trường test | Active servlet threads tăng, request latency có thể xếp hàng |
| Broker tắt | Tắt broker test trước send/receive | JMS exception / HTTP 503 theo logic demo, không nhầm 204 |
| Gateway timeout ngắn hơn JMS timeout | Cấu hình test gateway riêng | Có thể HTTP timeout trước khi receive kết thúc; xử lý late result |
| Hai consumer cạnh tranh | Một queue test, hai endpoint/worker | Mỗi message chỉ được một consumer queue nhận tại một thời điểm; kiểm tra kết quả thực tế |
| `@Async` pool nhỏ | Tạo nhiều async tasks có receive hữu hạn | Pool chật, jobs đợi/reject; HTTP có thể trả sớm nhưng task vẫn block |
| `@JmsListener` với transaction | Listener độc lập trên queue test | Kiểm tra rollback/redelivery khi callback lỗi |
| Receive thành công, response HTTP mất | Mô phỏng disconnect sau JMS receive | Không mặc nhiên nhận lại cùng message; đánh giá ACK/commit |
| Scheduled polling no-wait | Poll queue test theo lịch | Nhận được message khi polling, chấp nhận latency giữa hai lượt |

Khi test failover, không dùng lệnh phá hủy dữ liệu hoặc purge trên broker production. Khi chạy thử nhận message, luôn dùng **queue riêng** và không cho consumer test lấy nhầm message thật.

## 13. Checklist ra quyết định thiết kế

Trước khi đặt `receive` trong HTTP endpoint hoặc một task, hãy trả lời:

- [ ] Caller thật sự cần message **ngay trong cùng request** hay chỉ cần xác nhận đã nhận job?
- [ ] Khi queue rỗng, timeout là bao nhiêu? Nó có nhỏ hơn **ngân sách HTTP tổng thể**?
- [ ] Có giới hạn số request/task được phép đồng thời block? Nếu pool đầy thì chính sách gì?
- [ ] Nếu client hủy HTTP nhưng JMS vẫn đang chờ, hệ thống xử lý ra sao?
- [ ] Message bị nhận có được ACK trước khi side effect hoàn thành không?
- [ ] Có nguy cơ một HTTP caller tiêu thụ message của worker khác không?
- [ ] Nếu dùng `@Async`, executor có bounded queue, metrics và rejection policy?
- [ ] Nếu dùng `@Scheduled`, polling interval/receiveTimeout có gây queue backlog?
- [ ] Nếu dùng listener, đã tách queue, concurrency, transaction, retry, DLQ và idempotency?
- [ ] Với request–reply, đã có correlation ID, reply destination, deadline và xử lý late reply?
- [ ] Có đo p95/p99 HTTP, active threads và queue age trong thử nghiệm tải thực?
- [ ] Nếu việc kéo dài vài giây hoặc phút, đã cân nhắc HTTP 202 + job status thay vì blocking?

### Câu hỏi tự kiểm tra

1. Vì sao một request HTTP đang gọi `receiveAndConvert` có thể giữ servlet thread trong khi CPU không cao?
2. Trong Spring `JmsTemplate`, `receiveTimeout = 0` và `receiveTimeout = -1` khác nhau thế nào?
3. Nếu 20 threads đều chờ queue rỗng 2 giây, vì sao 40 HTTP requests đồng thời có thể khiến một phần request mất khoảng 4 giây?
4. Vì sao timeout JMS 5 giây không bảo đảm gateway timeout 1 giây sẽ “hủy” việc nhận?
5. `@Async` có biến JMS receive thành I/O không chặn worker không? Vì sao?
6. Tại sao một HTTP GET chỉ để “xem message” trên queue lại không vô hại như truy vấn thông thường?
7. Vì sao `receiveAndConvert` trả về message rồi HTTP response bị lỗi không đồng nghĩa message sẽ được giao lại?
8. Khi nào nên chọn `@JmsListener`, khi nào polling scheduler có giới hạn vẫn phù hợp?
9. Trong mô hình HTTP 202, phía client kiểm tra kết quả job bằng cách nào mà không phải giữ một request đang đợi JMS?
10. Nếu producer và consumer cần request–reply trong deadline ngắn, metadata và tài nguyên nào cần quản lý để không nhầm reply?

**Ghi nhớ:** JMS nhận đồng bộ đơn giản cho **tác vụ thăm dò hoặc request–reply có giới hạn rõ**, nhưng đưa `receive` vào HTTP thread hoặc worker pool nhỏ khiến số luồng chờ tăng theo lượng request. **`receiveTimeout` chỉ giới hạn thời gian chờ một lần nhận, không tạo event-driven processing.** Với xử lý hàng đợi liên tục, chọn `@JmsListener` trên dedicated consumer threads; với công việc dài, cân nhắc **HTTP 202 + jobId + status store**. Luôn thiết kế ACK/transaction, timeouts và idempotency độc lập với cách phân bổ threads.

## Tài liệu tham khảo

1. Spring Framework — Receiving a Message (synchronous receive blocks, asynchronous listeners): https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html
2. Spring Framework — JmsTemplate API (receiveTimeout, receiveAndConvert): https://docs.spring.io/spring-framework/docs/6.1.16/javadoc-api/org/springframework/jms/core/JmsTemplate.html
3. Spring Framework — Using Spring JMS (template, containers, transaction): https://docs.spring.io/spring-framework/reference/integration/jms/using.html
4. Spring Framework — Annotation-driven Listener Endpoints: https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html
5. Spring Boot 3.3 — JMS and Artemis: https://docs.spring.io/spring-boot/3.3/reference/messaging/jms.html
6. Jakarta Messaging 3.1 Specification (MessageConsumer, acknowledge and transaction): https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html
