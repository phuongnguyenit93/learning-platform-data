# So sánh nhắn tin bất đồng bộ với lời gọi HTTP đồng bộ

> **Ngữ cảnh:** Bức tranh JMS trong Spring Framework. Bài này so sánh hai cách phối hợp giữa các thành phần của hệ thống: gọi HTTP và chờ kết quả, hoặc gửi thông điệp qua broker để xử lý sau. Trọng tâm là thời điểm nhận kết quả, phụ thuộc giữa các dịch vụ, xử lý lỗi và cách triển khai bằng Spring JMS.

## 1. Mô hình hoạt động và ý nghĩa của “đồng bộ”, “bất đồng bộ”

**HTTP đồng bộ (synchronous request–response):** bên gọi gửi HTTP request đến bên nhận và chờ HTTP response cho thao tác đó. Nếu API A cần kết quả từ API B để hoàn tất công việc, A phải chờ B xử lý hoặc trả lỗi/timeout. Ví dụ: API đặt hàng gọi dịch vụ kiểm tra tồn kho, đợi kết quả rồi mới quyết định xác nhận đơn.

**Nhắn tin JMS bất đồng bộ (asynchronous messaging):** bên gửi (producer) tạo message, gửi đến broker (ví dụ ActiveMQ Artemis), rồi tiếp tục công việc mà không phải chờ consumer hoàn thành nghiệp vụ. Broker giữ/chuyển message đến consumer theo cấu hình. Ví dụ: sau khi tiếp nhận đơn, API phát lệnh tạo hóa đơn vào queue; worker tạo hóa đơn khi có khả năng xử lý.

Hai mốc cần phân biệt:
- **Đã gửi/được broker tiếp nhận:** producer nhận kết quả của thao tác gửi. Điều này chưa có nghĩa consumer đã xử lý thành công.
- **Đã hoàn tất nghiệp vụ:** consumer đã xử lý và cập nhật kết quả; có thể xảy ra sau vài mili giây, vài phút hoặc lâu hơn nếu queue tồn đọng.

Trong Spring, `JmsTemplate.convertAndSend(...)` là lời gọi gửi message **trên luồng hiện tại**, có thể đợi kết nối/broker và ném lỗi. Tính bất đồng bộ nằm ở việc producer **không đợi kết quả xử lý nghiệp vụ của consumer**, không có nghĩa thao tác gửi luôn không chặn.

~~~text
HTTP đồng bộ:
Client -> Order API -> HTTP POST -> Inventory API
Client <- Order API <- HTTP response (OK / lỗi)
         [Order API chờ kết quả Inventory API]

JMS bất đồng bộ:
Client -> Order API -> JMS Producer -> Broker/Queue -> JMS Consumer -> Xử lý
Client <- 202 Accepted              [consumer có thể xử lý về sau]
         [202 không đồng nghĩa đã xử lý xong]
~~~

**Lưu ý về thuật ngữ:** HTTP cũng có thể được thiết kế bất đồng bộ về mặt nghiệp vụ (trả `202 Accepted` rồi polling/webhook), và JMS có thể dùng request–reply hoặc nhận đồng bộ bằng `JmsTemplate.receive(...)`. Vì vậy, hãy so sánh **kiểu tương tác cụ thể** chứ đừng kết luận “HTTP luôn đồng bộ, JMS luôn bất đồng bộ”.

## 2. So sánh theo những tiêu chí quyết định

| Tiêu chí | Gọi HTTP đồng bộ | Nhắn tin JMS bất đồng bộ |
| --- | --- | --- |
| Kết quả bên gọi nhận | Kết quả/HTTP status của thao tác được gọi, trong cùng vòng request–response | Kết quả gửi vào broker; kết quả xử lý cuối cùng cần kênh khác để tra cứu/thông báo |
| Phụ thuộc thời gian | Bên nhận phải phản hồi kịp khi bên gọi đang chờ | Producer và consumer không cần hoạt động cùng thời điểm nếu broker lưu message bền vững |
| Khi dịch vụ xử lý tạm dừng | Bên gọi có thể gặp timeout, lỗi hoặc cần retry | Message có thể nằm trong queue để xử lý sau; còn phụ thuộc cấu hình lưu trữ, TTL và tình trạng broker |
| Khi broker/dịch vụ đích hỏng | Lỗi HTTP được nhận trực tiếp nếu phát hiện được | Nếu broker không tiếp nhận được, producer vẫn lỗi; nếu consumer hỏng sau khi broker nhận thì có thể xử lý lại sau |
| Độ trễ cảm nhận | Thời gian phản hồi thường bao gồm thời gian xử lý bên nhận | Producer có thể phản hồi sớm; thời gian **hoàn tất** bao gồm cả thời gian đợi trong queue |
| Tải đột biến | Có thể gây dồn request, cạn connection/thread hoặc tăng timeout | Queue hấp thụ đỉnh tải trong giới hạn dung lượng; độ trễ hàng đợi tăng nếu tiêu thụ chậm |
| Mở rộng | Scale dịch vụ HTTP và điều tiết bằng timeout, rate limit, circuit breaker | Scale số consumer cho queue (theo năng lực broker và yêu cầu thứ tự) |
| Thứ tự xử lý | Thứ tự giữa nhiều request độc lập không mặc nhiên được bảo đảm | Queue không bảo đảm thứ tự xử lý hoàn tất toàn cục khi có nhiều consumer, retry hoặc redelivery |
| Độ tin cậy | Cần thiết kế retry, idempotency và xử lý kết quả timeout không rõ | Cần thiết kế persistence, ack/transaction, redelivery, DLQ, idempotency và giám sát backlog |
| Tính nhất quán | Dễ biểu diễn kết quả tức thời nhưng không tự động có transaction xuyên nhiều dịch vụ | Thường chấp nhận eventual consistency và thiết kế trạng thái đang xử lý |
| Vận hành | Theo dõi HTTP latency, error rate, timeout, saturation | Theo dõi thêm queue depth/age, consumer lag, retry, DLQ và sức khỏe broker |
| Mức độ phức tạp | Thường trực quan hơn cho tương tác cần kết quả ngay | Phức tạp hơn về broker, schema message, trạng thái công việc và xử lý trùng |

Không có mô hình nào tự động “nhanh hơn” hoặc “tin cậy hơn” trong mọi tình huống. Với HTTP, thời gian user phải chờ có thể gần bằng thời gian xử lý phía sau. Với JMS, thời gian trả lời **đã tiếp nhận** thường ngắn, nhưng **thời gian hoàn tất** có thể dài hơn do chờ queue. Broker không tự biến một xử lý chậm thành nhanh.

## 3. Ví dụ nghiệp vụ: tạo hóa đơn sau khi đặt hàng

**Cách 1 – HTTP đồng bộ:**
1. Client gửi `POST /orders`.
2. Order Service gọi HTTP đến Invoice Service và chờ tạo hóa đơn.
3. Chỉ khi Invoice Service trả lời, Order Service mới hoàn tất response cho client.
4. Nếu Invoice Service chậm hoặc không khả dụng, client có thể chờ lâu/timeout dù đơn hàng đã được tạo ở một bước trước.

Ưu điểm: kết quả tạo hóa đơn có thể được trả ngay nếu mọi bước thành công. Nhược điểm: luồng request bị phụ thuộc vào thời gian sống và hiệu năng của dịch vụ khác; timeout còn tạo tình huống “không biết bên kia đã xử lý hay chưa”.

**Cách 2 – JMS bất đồng bộ:**
1. Order Service xác thực yêu cầu và ghi nhận đơn hàng/trạng thái cần xử lý.
2. Producer gửi message `CreateInvoice` (gồm `orderId`, `requestId`, phiên bản schema) vào queue.
3. Sau khi việc tiếp nhận request và gửi/lập lịch công việc đủ an toàn theo hợp đồng API, client có thể nhận `202 Accepted` kèm `jobId` hoặc đường dẫn tra cứu.
4. Consumer dùng `@JmsListener` nhận message và tạo hóa đơn. Trạng thái chuyển `PENDING → PROCESSING → SUCCEEDED` hoặc `FAILED`.
5. Client gọi `GET /jobs/{id}`, nhận webhook hoặc nhận thông báo qua kênh riêng để biết **kết quả cuối cùng**.

**Điểm thiết kế quan trọng:** nếu vừa ghi database vừa gửi message là hai thao tác riêng, có thể xảy ra trường hợp “đã commit đơn hàng nhưng chưa gửi được message”. Với yêu cầu không mất công việc, cân nhắc **transactional outbox**: lưu bản ghi công việc/outbox trong cùng transaction với đơn hàng, sau đó publisher riêng gửi đến broker và đánh dấu đã phát; consumer vẫn phải chống trùng.

~~~text
HTTP đồng bộ:
Order API ──POST /invoices──> Invoice Service
          <── kết quả ────────
          -> trả kết quả cho client

JMS bất đồng bộ:
Order API ── CreateInvoice(orderId, requestId) ──> Queue
          <── gửi được/đã tiếp nhận ─────────────
          -> 202 + jobId
Queue ──> Invoice Worker ──> Invoice DB / job status
Client ── GET /jobs/{id} hoặc webhook ──> kết quả cuối
~~~

## 4. Minh họa với Spring Boot 3.3, Java 17 và ActiveMQ Artemis

Ví dụ sau cho thấy **hai điểm vào khác nhau**: một endpoint gọi HTTP và chờ kết quả, một endpoint gửi JMS queue rồi trả `202`. Để chạy demo trên một ứng dụng nhỏ, endpoint `/internal/process` đóng vai trò **giả lập dịch vụ HTTP phía sau**; trong hệ thống thật nó thường nằm ở một service khác. Listener chỉ ghi log để thấy message được xử lý độc lập, chưa phải triển khai quản lý trạng thái production.

**Cấu trúc dự án:**

~~~text
spring-jms-comparison/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/demo/
    │   ├── ComparisonApplication.java
    │   ├── TaskController.java
    │   └── TaskListener.java
    └── resources/application.yml
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'spring-jms-comparison'
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
spring:
  artemis:
    mode: native
    broker-url: tcp://localhost:61616
    user: demo
    password: demo
~~~

Trước khi chạy, cần một **ActiveMQ Artemis broker** có cổng JMS/Netty `61616`, tài khoản `demo/demo` và queue `demo.jobs` (hoặc cấu hình broker cho phép tự tạo queue). Đây là thông tin demo cục bộ; môi trường thật phải dùng cơ chế quản lý secret, xác thực và phân quyền broker.

`src/main/java/demo/ComparisonApplication.java`:

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.web.client.RestClient;

@SpringBootApplication
@EnableJms
public class ComparisonApplication {
    public static void main(String[] args) {
        SpringApplication.run(ComparisonApplication.class, args);
    }

    @Bean
    RestClient downstreamClient(RestClient.Builder builder) {
        return builder.baseUrl("http://localhost:8080").build();
    }
}
~~~

`src/main/java/demo/TaskController.java`:

~~~java
package demo;

import java.util.Map;
import java.util.Objects;
import java.util.UUID;

import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestClient;

@RestController
public class TaskController {
    private final RestClient downstreamClient;
    private final JmsTemplate jmsTemplate;

    public TaskController(RestClient downstreamClient, JmsTemplate jmsTemplate) {
        this.downstreamClient = downstreamClient;
        this.jmsTemplate = jmsTemplate;
    }

    public record JobRequest(String name) {}

    @PostMapping("/demo/sync")
    public Map<String, String> sync(@RequestBody JobRequest request) {
        String result = downstreamClient.post()
                .uri("/internal/process")
                .body(request)
                .retrieve()
                .body(String.class); // Chờ HTTP response của endpoint phía sau.

        return Map.of("state", "DONE", "result", Objects.requireNonNull(result));
    }

    @PostMapping("/demo/async")
    public ResponseEntity<Map<String, String>> async(@RequestBody JobRequest request) {
        String jobId = UUID.randomUUID().toString();
        jmsTemplate.convertAndSend("demo.jobs", jobId + "|" + request.name());
        // Đã gửi tới broker theo thao tác JMS, chưa chờ TaskListener xử lý.
        return ResponseEntity.accepted()
                .body(Map.of("jobId", jobId, "state", "ACCEPTED"));
    }

    @PostMapping(value = "/internal/process",
                 produces = MediaType.TEXT_PLAIN_VALUE)
    public String process(@RequestBody JobRequest request) {
        return "processed:" + request.name();
    }
}
~~~

`src/main/java/demo/TaskListener.java`:

~~~java
package demo;

import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class TaskListener {
    @JmsListener(destination = "demo.jobs")
    public void consume(String payload) {
        System.out.println("JMS processed: " + payload);
    }
}
~~~

Trong ví dụ, `JmsTemplate` dùng converter mặc định để gửi một `String` thành JMS `TextMessage`, còn tham số `String payload` của listener được Spring chuyển từ nội dung message. Chuỗi ghép bằng dấu `|` **chỉ để demo**, chưa phải message contract phù hợp production; ứng dụng thật nên dùng JSON/schema có version, validate trường bắt buộc và định nghĩa quy tắc tương thích.

Sau khi broker sẵn sàng, tại thư mục dự án chạy bằng Gradle đã cài:

~~~bash
gradle bootRun
~~~

Gửi hai request (cú pháp shell Bash; trên Windows PowerShell có thể dùng `curl.exe` với cách escape JSON phù hợp):

~~~bash
curl -i -X POST http://localhost:8080/demo/sync \
  -H 'Content-Type: application/json' \
  -d '{"name":"invoice-42"}'

curl -i -X POST http://localhost:8080/demo/async \
  -H 'Content-Type: application/json' \
  -d '{"name":"invoice-42"}'
~~~

**Kết quả quan sát được:**
- `/demo/sync`: HTTP `200 OK` với các trường `state: "DONE"` và `result: "processed:invoice-42"`; endpoint đợi lời gọi HTTP phía sau trả về. Thứ tự các trường JSON không được cam kết.
- `/demo/async`: HTTP `202 Accepted` với `state: "ACCEPTED"` và một UUID ở `jobId`; listener ghi log dạng `JMS processed: <UUID>|invoice-42`, thời điểm xuất hiện log không nhất thiết sau response HTTP.
- Nếu broker không kết nối được, thao tác `convertAndSend` có thể lỗi; ví dụ này **không** tự động lưu dự phòng trong database và **không** có endpoint tra trạng thái thực tế.

Vì chương trình Spring cần dependency và broker, không biên dịch độc lập bằng `javac TaskController.java`. Cách chạy phù hợp là `gradle bootRun` với Java 17+ và các dependency được Gradle tải về.

## 5. Tính tin cậy: điều gì xảy ra khi có lỗi?

### 5.1. Lỗi ở HTTP đồng bộ

Nếu HTTP client bị timeout, có ít nhất hai khả năng: server chưa xử lý hoặc server đã xử lý xong nhưng response bị mất/chậm. Vì vậy **timeout không đồng nghĩa tác vụ chưa chạy**. Retry vô điều kiện một lệnh tạo đơn/thu tiền có thể tạo dữ liệu trùng.

Cách giảm rủi ro: đặt timeout rõ ràng, retry có giới hạn với backoff và jitter, circuit breaker khi phù hợp, đồng thời sử dụng **idempotency key** để server nhận diện nhiều lần gọi cho một thao tác logic. Đối với thao tác cần nguyên tử, yêu cầu trạng thái server-side thay vì suy diễn hoàn toàn từ lỗi mạng.

### 5.2. Lỗi ở JMS bất đồng bộ

| Điểm lỗi | Điều có thể xảy ra | Thiết kế cần có |
| --- | --- | --- |
| Producer không gửi được vì broker ngừng | Không có công việc trong queue; API có thể trả lỗi | Không trả “đã nhận xử lý” vô điều kiện; cân nhắc outbox nếu yêu cầu không mất lệnh |
| Broker đã nhận, consumer đang ngừng | Message chờ trong queue nếu cấu hình lưu giữ còn hiệu lực | Persistent delivery, giới hạn tồn đọng, TTL hợp lý, alert khi queue tăng |
| Consumer ném exception trước khi xác nhận xử lý | Có thể rollback/redelivery tùy transaction, ack và broker | Cấu hình listener transaction, chính sách retry/backoff, DLQ |
| Consumer ghi DB thành công rồi crash trước JMS ack/commit | Message có thể được phát lại dù side effect đã xảy ra | Idempotent consumer, khóa duy nhất theo eventId/jobId |
| Message không hợp lệ hoặc luôn gây lỗi | Lặp xử lý gây tắc/hại tài nguyên | Phân loại lỗi, số lần thử tối đa, dead-letter queue, công cụ replay có kiểm soát |
| Queue tồn đọng lâu | Client đã nhận `202` nhưng kết quả đến muộn | Theo dõi oldest-message age, queue depth, throughput, deadline/timeout nghiệp vụ |

**Không mặc định xem JMS là exactly-once cho nghiệp vụ.** JMS cung cấp cơ chế acknowledge, transaction, redelivery và delivery mode; mức bảo đảm thực tế phụ thuộc broker, client, cấu hình và ranh giới giao dịch. Cơ sở dữ liệu và JMS broker thường là **hai tài nguyên giao dịch độc lập**. Một local JMS transaction không tự biến việc cập nhật database và ack message thành một transaction nguyên tử. Cách phổ biến để đạt **hiệu ứng nghiệp vụ một lần** là:
1. Mỗi message mang `eventId`/`jobId` ổn định qua các lần redelivery.
2. Consumer ghi dấu đã xử lý bằng thao tác database có ràng buộc duy nhất hoặc cập nhật nguyên tử cùng giao dịch với side effect.
3. Nếu gặp ID đã xử lý, consumer bỏ qua side effect nhưng vẫn hoàn tất cơ chế ack/commit thích hợp.
4. Theo dõi message lỗi và replay có chủ đích; không giả định mọi exception sẽ tự đến DLQ.

Ví dụ, đặt unique constraint trên cột `processed_event_id` (hoặc bảng dedup) trong cùng database transaction với cập nhật trạng thái. Chỉ kiểm tra “ID đã tồn tại chưa?” bằng một câu SELECT riêng trước khi ghi là chưa đủ an toàn khi nhiều consumer chạy song song.

## 6. Những khác biệt thường bị bỏ sót

**Queue và Topic:** trong JMS, **queue** phù hợp mô hình work distribution (mỗi message được một consumer xử lý trong nhóm cạnh tranh); **topic** phù hợp publish–subscribe (nhiều subscription có thể nhận cùng một thông điệp). Topic chỉ nhận được message khi không online nếu có cơ chế durable subscription và broker lưu phù hợp; không suy diễn rằng mọi topic đều giữ message vô hạn.

**Thứ tự:** tăng concurrency của listener giúp tăng throughput, nhưng với nhiều message liên quan cùng một đơn, thứ tự hoàn tất có thể thay đổi. Nếu thứ tự là ràng buộc nghiệp vụ, cần thiết kế theo entity key, sequence/version và cơ chế serialize/partition phù hợp; không dựa vào cảm giác “queue luôn FIFO”.

**Hợp đồng dữ liệu:** HTTP thường có request/response schema, mã lỗi, timeout. JMS cần message schema và version, tên destination, content type, message ID/correlation ID, TTL và quy tắc xử lý khi gặp message cũ. Đổi tên trường hoặc thay đổi ý nghĩa message mà không quản lý tương thích có thể làm consumer cũ hỏng.

**Quan sát:** với HTTP, đo latency theo endpoint, status 4xx/5xx, số request đang xử lý và trace xuyên service. Với JMS, cần thêm thời gian message chờ trong queue, thời gian consumer xử lý, số lần redelivery, queue depth, DLQ, tình trạng broker và correlation ID nối request tạo job với các bước xử lý. Log “đã gửi” riêng lẻ không chứng minh nghiệp vụ thành công.

**Điều tiết tải:** queue giúp tách tốc độ nhận và tốc độ xử lý **trong giới hạn** dung lượng broker và chính sách lưu trữ. Nếu producer liên tục nhanh hơn consumer, backlog và độ trễ sẽ tăng. Phải có rate limit, hạn mức message, số consumer phù hợp, kế hoạch scale, cảnh báo queue age và chính sách xử lý quá tải.

**Bảo mật:** cả HTTP và JMS cần xác thực, phân quyền, bảo vệ kết nối và dữ liệu. Với JMS, kiểm soát quyền publish/consume theo destination, TLS, quản lý secret, không đưa dữ liệu nhạy cảm không cần thiết vào payload/log/DLQ. Message có thể được lưu trên đĩa của broker nên chính sách retention cũng quan trọng.

## 7. Chọn mô hình nào?

**Ưu tiên HTTP đồng bộ khi** bên gọi cần kết quả ngay để đưa ra quyết định trong cùng tương tác, thao tác ngắn, SLA đáp ứng rõ và có cách xử lý timeout/idempotency. Ví dụ: hỏi tồn kho hiện tại, xác thực quyền truy cập, tính phí để người dùng xác nhận trước khi thanh toán.

**Ưu tiên JMS bất đồng bộ khi** công việc có thể hoàn tất sau, tải biến động, cần tách vòng đời producer–consumer hoặc cần xử lý lại sau khi dịch vụ tiêu thụ tạm ngừng. Ví dụ: tạo hóa đơn, gửi email, đồng bộ dữ liệu sang hệ thống ngoài, tạo báo cáo, xử lý sự kiện hậu giao dịch.

**Kết hợp cả hai** thường hợp lý: HTTP nhận yêu cầu, xác thực và trả `202` với `jobId`; JMS phân phối việc làm; HTTP `GET /jobs/{id}` hoặc webhook trả kết quả sau. Trong kiến trúc này, cần định nghĩa rõ:
- `ACCEPTED`: yêu cầu đã được tiếp nhận theo hợp đồng bền vững nào (đã ghi DB/outbox hay đã broker xác nhận)?
- `PROCESSING`: worker bắt đầu thực hiện; có heartbeat/lease nếu job lâu.
- `SUCCEEDED / FAILED`: trạng thái cuối cùng, thời điểm, nguyên nhân lỗi và có thể thử lại hay không.
- Deadline nghiệp vụ, message retention/TTL, cơ chế retry, idempotency và kênh thông báo kết quả.

### Một vài ngộ nhận cần tránh

1. **“Trả HTTP 202 nghĩa là xử lý thành công.”** Sai: `202` chỉ nói request đã được chấp nhận để xử lý; cần cơ chế xác nhận kết quả sau.
2. **“Có JMS là không mất message.”** Sai: còn tùy persistent delivery, broker storage/HA, TTL, transaction, chính sách lỗi và cách producer bảo đảm gửi.
3. **“Retry bảo đảm chính xác một lần.”** Sai: retry có thể tạo duplicate; phải thiết kế idempotency và ranh giới transaction.
4. **“JMS luôn nhanh hơn HTTP.”** Sai: JMS có thêm broker và chờ queue; tối ưu cho tách thời gian và điều tiết tải, không tự giảm tổng thời gian xử lý.
5. **“Dùng `@Async` thay được JMS.”** Sai: `@Async` chạy tác vụ trên executor trong tiến trình hiện tại, không mặc nhiên có hàng đợi bền vững, redelivery hoặc khả năng phục hồi qua lần khởi động lại.
6. **“Thêm nhiều consumer thì luôn tốt hơn.”** Sai: có thể ảnh hưởng thứ tự, tranh chấp database, downstream rate limit và số lượng message đang xử lý cùng lúc.

## 8. Checklist thiết kế và câu hỏi tự kiểm tra

Khi chuyển một thao tác từ HTTP đồng bộ sang JMS, hãy trả lời: người gọi cần thông tin nào **ngay lập tức**; điều kiện nào được phép trả `202`; kết quả được tra cứu/thông báo thế nào; message và trạng thái công việc được lưu bao lâu; khi broker/consumer/database hỏng thì phục hồi ra sao; một message phát lại có gây side effect trùng không; queue và DLQ được giám sát bởi ai?

**Tự kiểm tra:**
1. Client nhận `202` nhưng consumer chưa chạy. Điều gì bảo đảm công việc không bị mất, và client biết trạng thái bằng cách nào?
2. Consumer đã ghi hóa đơn vào DB rồi crash trước ack JMS. Một message được gửi lại sẽ được xử lý an toàn như thế nào?
3. Nếu người dùng cần biết “còn hàng hay không” trước khi bấm xác nhận, tại sao HTTP đồng bộ thường phù hợp hơn việc phát command vào queue rồi chờ kết quả?

**Ghi nhớ:** câu hỏi quan trọng nhất không phải “HTTP hay JMS hiện đại hơn”, mà là **nghiệp vụ có cần kết quả trong cùng request hay có thể chấp nhận hoàn tất sau**, và hệ thống sẽ công bố, lưu giữ, phục hồi, quan sát kết quả đó như thế nào.

## Tài liệu tham khảo

- Spring Framework – JMS Receiving a Message: https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html
- Spring Framework – Annotation-driven JMS Listener Endpoints: https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html
- Spring Boot 3.4 – JMS and ActiveMQ Artemis: https://docs.spring.io/spring-boot/3.4/reference/messaging/jms.html
