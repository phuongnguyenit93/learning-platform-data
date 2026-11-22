# Kiểm thử reply timeout và late reply trong Spring Integration

## 1. Mục tiêu và bối cảnh

Trong một flow **request–reply**, bên gửi phát request rồi chờ kết quả từ một nhánh xử lý khác. Các thành phần thường tham gia là **Gateway**, **Message Channel**, **Service Activator**, **Router**, **Transformer** và các bước xử lý bất đồng bộ. Nếu phản hồi không tới đúng hạn, Gateway phải có cách kết thúc việc chờ. Nhưng request đã gửi có thể **vẫn đang được xử lý** và reply có thể xuất hiện **sau khi caller đã timeout**.

Đó là hai vấn đề cần kiểm thử riêng:

1. **Reply timeout:** Caller kết thúc chờ đúng chính sách khi không nhận được reply trước hạn.
2. **Late reply:** Kết quả đến muộn không được nhầm thành phản hồi của request mới, không tự khiến request đã timeout được xác nhận thành công và phải được xử lý/quan sát theo chính sách nghiệp vụ.

Bài **“Kiểm thử reply timeout và late reply”** thuộc chương **Kiểm thử pattern** của module **SPRING_INTEGRATION_PATTERN**. Module hướng đến triển khai Enterprise Integration Patterns bằng Spring Integration để xây dựng luồng message ít phụ thuộc, dễ mở rộng; kết hợp Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel và correlation, đồng thời kiểm thử và theo dõi từng nhánh xử lý.

Sau bài học, bạn có thể:

- Phân biệt \`requestTimeout\` với \`replyTimeout\` và timeout của tầng nghiệp vụ/HTTP.
- Hiểu vì sao cần **ranh giới bất đồng bộ** để giới hạn thời gian đợi của Gateway khi handler chạy lâu.
- Viết test xác định cho reply đến kịp, không có reply và reply đến sau hạn.
- Dùng \`requestId\` hoặc correlation key để tránh ghép reply sai request.
- Xác định chính sách cho kết quả đến muộn, retry, side effect, lỗi downstream và timeout.
- Kiểm tra bằng timeout hữu hạn, tín hiệu đồng bộ và isolation, không phụ thuộc \`Thread.sleep\` tùy ý.

## 2. Sơ đồ vòng đời request–reply

~~~mermaid
sequenceDiagram
    participant C as Caller
    participant G as Gateway
    participant Q as Request Channel
    participant W as Worker
    C->>G: request(id=A)
    G->>Q: send request(A)
    Q-->>W: giao request(A)
    Note over G: Chờ reply trong thời hạn
    alt Reply đến đúng hạn
        W-->>G: reply(A)
        G-->>C: kết quả A
    else Hết replyTimeout trước khi reply đến
        G-->>C: null / timeout error theo cấu hình
        Note over W: Worker có thể vẫn đang chạy
        W-->>G: late reply(A)
        Note over G,W: Không tự biến kết quả đã timeout thành thành công
    end
~~~

Đặt các mốc thời gian:

~~~text
t0: Caller gọi Gateway với request A
t1: Request được chấp nhận vào channel
t2: Gateway bắt đầu đợi reply (sau khi send/handoff trở về)
t3: Hết thời hạn replyTimeout => caller không còn đợi
t4: Downstream tạo reply A, nhưng A đã timeout

Nếu t4 < t3: phản hồi đúng hạn.
Nếu t4 > t3: late reply.
Nếu t4 gần t3: kết quả có thể phụ thuộc thứ tự race thực tế.
~~~

**Không nên định nghĩa “late” chỉ bằng thời gian xử lý của worker.** Thời điểm bắt đầu chờ, độ trễ trong queue, scheduling thread, network, broker và thời gian gửi reply đều có thể ảnh hưởng việc kết quả có kịp đến caller hay không.

## 3. Phân biệt request timeout và reply timeout

Spring Integration Gateway có hai cấu hình quan trọng:

| Thuộc tính | Bảo vệ giai đoạn nào? | Trường hợp thường gặp |
| --- | --- | --- |
| \`requestTimeout\` | Thời gian chờ khi **gửi request** đến channel có thể block | \`QueueChannel\` có capacity hữu hạn và đang đầy |
| \`replyTimeout\` | Thời gian Gateway **đợi reply** sau khi send/handoff trả quyền điều khiển | Downstream chưa tạo reply hoặc không có nhánh trả kết quả |

Ví dụ giao diện Gateway, Java 17 với Spring Integration 6.2+:

~~~java
import org.springframework.integration.annotation.MessagingGateway;
import org.springframework.integration.annotation.Gateway;

@MessagingGateway(
        defaultRequestChannel = "orders.requests",
        defaultRequestTimeout = "200",
        defaultReplyTimeout = "500")
public interface OrderGateway {

    String submit(String orderId);

    // Có thể override cho một phương thức.
    @Gateway(requestTimeout = 100, replyTimeout = 1000)
    String submitSlowAllowed(String orderId);
}
~~~

Các số trên tính bằng **mili giây** và chỉ là ví dụ. Với cấu hình dựa trên annotation, cần bật \`@IntegrationComponentScan\` tại cấu hình Spring để phát hiện interface \`@MessagingGateway\`; \`@ComponentScan\` thông thường không thay thế hoàn toàn chức năng quét này.

**Điểm cần nhớ:** \`requestTimeout=200\` không có nghĩa downstream phải xử lý trong 200 ms. Nếu việc gửi vào channel thành công ngay, request timeout gần như không ảnh hưởng đến thời gian đợi kết quả. Ngược lại, \`replyTimeout=500\` không bảo đảm request đã được hủy khi caller ngừng chờ.

### Timeout mặc định không nên được dùng như hợp đồng ngầm

Giá trị mặc định phụ thuộc phiên bản Spring Integration, loại Gateway và cấu hình endpoint. Ví dụ, các bản API 6.x có khác biệt lịch sử về mặc định \`defaultReplyTimeout\`; inbound Gateway của HTTP/JMS còn có đặc thù riêng. Vì vậy hãy **đặt timeout tường minh** tại flow hoặc gateway cần SLA, rồi kiểm thử chính giá trị đó.

## 4. Vì sao replyTimeout có thể không cắt được handler chậm?

Một nhầm lẫn phổ biến là đặt \`replyTimeout=100\` rồi mong Gateway trả về sau 100 ms ngay cả khi Service Activator chạy đồng bộ mất 2 giây.

### Flow đồng bộ trên DirectChannel

~~~mermaid
flowchart LR
    G["Gateway / caller thread"] --> D["DirectChannel"]
    D --> H["Service Activator\nxử lý lâu"]
    H --> R["Reply"]
~~~

Với \`DirectChannel\`, handler thường chạy **trên chính thread đang gọi send**. Gateway phải chờ \`send()\` hoàn thành trước khi bắt đầu phần đợi reply. Nếu downstream block trong handler, \`replyTimeout\` **không tự ngắt hoặc hủy** xử lý đó.

### Có ranh giới bất đồng bộ

~~~mermaid
flowchart LR
    G["Gateway"] --> Q["QueueChannel"]
    Q --> W["Worker / Poller"]
    W --> R["Reply Channel"]
    R --> G
~~~

Khi request được enqueue nhanh rồi worker xử lý **trên thread khác**, caller có thể đợi tối đa \`replyTimeout\` ở phía Gateway. Có thể tạo ranh giới tương đương bằng \`ExecutorChannel\` hoặc một adapter/broker, tùy flow.

Lưu ý một timeout của Gateway **không phải lệnh cancel worker**. Kể cả caller đã nhận timeout, worker vẫn có thể:

- Ghi dữ liệu vào database.
- Gọi dịch vụ bên ngoài.
- Retry lỗi tạm thời.
- Gửi reply muộn.
- Gửi exception đến error channel khi đã quá hạn.

Test phải kiểm tra các tác dụng phụ này khi chúng thuộc hợp đồng nghiệp vụ.

## 5. Định nghĩa hợp đồng kiểm thử trước khi viết code

Giả sử ứng dụng xử lý yêu cầu có \`requestId\` và muốn reply trước hạn 200 ms:

| Case | Điều kiện | Kết quả mong đợi ở caller | Điều cần quan sát ở downstream |
| --- | --- | --- | --- |
| Reply đúng hạn | Worker gửi reply trước deadline | Caller nhận reply đúng request | Một reply, payload/header hợp lệ |
| Không có reply | Worker không phát gì | Gateway kết thúc chờ theo timeout policy | Request vẫn có thể tồn tại |
| Reply đến muộn | Worker trả sau caller timeout | Caller không bị cập nhật thành success | Late reply được phân loại/ghi nhận |
| Hai request độc lập | A timeout, B trả kịp | B chỉ nhận reply B | Không trộn correlation A/B |
| Handler đồng bộ chậm | Handler chiếm caller thread | Reply timeout không bảo đảm ngắt handler | Thấy rõ ranh giới thread |
| Bounded request queue đầy | \`send\` không vào được queue | Xử lý gửi thất bại theo requestTimeout | Không coi request đã được xử lý |
| Downstream lỗi | Handler ném exception | Error policy thay vì im lặng chờ | Exception/error channel có ngữ cảnh |
| Retry sau timeout | Caller gửi lại cùng yêu cầu | Không gây side effect lặp ngoài ý muốn | Idempotency hoặc dedup đúng |

Một phép thử tốt thường cần **hai loại assertion**:

1. **Caller-facing:** Caller nhận payload, \`null\` hoặc exception theo chính sách đã cấu hình.
2. **System-facing:** Request vẫn có thể đang chạy; kết quả muộn không được gán nhầm và tác dụng phụ không bị nhân đôi.

Không nên chỉ kiểm tra \`null\` rồi kết luận toàn bộ nghiệp vụ đã thất bại hoặc đã được rollback.

## 6. Dựng môi trường test không cần broker

Ta có thể kiểm tra logic timeout ở mức messaging với:

- \`QueueChannel requests\`: nơi lưu request, giúp tách thread caller và worker.
- \`MessagingTemplate\`: thực hiện \`sendAndReceive\` với **receive timeout tường minh**, tương đương ý tưởng request–reply của Gateway.
- \`ExecutorService\`: chạy caller ở thread khác để test chủ động quan sát request.
- Header \`replyChannel\`: kênh tạm mà \`MessagingTemplate\` gắn vào message request để nhận reply.
- Header \`requestId\`: định danh nghiệp vụ để biết request nào đang được xử lý.

Khác với một test đo thời gian bằng sleep, test điều khiển chính xác **lúc nào reply được gửi**. Khi cần xác nhận caller đã timeout, test đợi \`Future\` kết thúc rồi mới gửi reply muộn.

Với Spring Boot, các dependency tương thích thường là:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-integration</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Ví dụ tiếp theo tập trung vào Spring Integration 6.x, Java 17, JUnit 5 và AssertJ. Chúng minh họa semantics của **MessagingTemplate request–reply**; với Gateway proxy \`@MessagingGateway\`, cần bổ sung integration test của proxy và \`errorOnTimeout\` theo phiên bản cụ thể.

## 7. Ví dụ Java hoàn chỉnh: đúng hạn, timeout, late reply và tương quan

Tạo lớp \`src/test/java/example/ReplyTimeoutAndLateReplyTest.java\`:

~~~java
package example;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.core.MessagingTemplate;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessagingException;
import org.springframework.messaging.support.MessageBuilder;

class ReplyTimeoutAndLateReplyTest {

    private final ExecutorService callers =
            Executors.newFixedThreadPool(2);
    private final QueueChannel requests = new QueueChannel();

    @AfterEach
    void shutdown() {
        callers.shutdownNow();
    }

    private Future<Message<?>> startCall(
            String requestId, long replyTimeoutMs) {
        return callers.submit(() -> {
            MessagingTemplate template = new MessagingTemplate();
            template.setSendTimeout(500);
            template.setReceiveTimeout(replyTimeoutMs);
            Message<String> message = MessageBuilder
                    .withPayload("payload-" + requestId)
                    .setHeader("requestId", requestId)
                    .build();
            return template.sendAndReceive(requests, message);
        });
    }

    private Message<?> nextRequest() {
        Message<?> request = requests.receive(1_000);
        assertThat(request).isNotNull();
        return request;
    }

    private static MessageChannel replyTo(Message<?> request) {
        Object destination = request.getHeaders().getReplyChannel();
        assertThat(destination)
                .as("Gateway-style request needs a replyChannel")
                .isInstanceOf(MessageChannel.class);
        return (MessageChannel) destination;
    }

    private static void sendReply(
            Message<?> request, String payload) {
        Message<String> reply = MessageBuilder.withPayload(payload)
                .setHeader(
                        "requestId",
                        request.getHeaders().get("requestId"))
                .build();
        assertThat(replyTo(request).send(reply)).isTrue();
    }

    @Test
    void reply_before_timeout_is_returned_to_caller()
            throws Exception {
        Future<Message<?>> call = startCall("A", 1_000);
        Message<?> incoming = nextRequest();

        assertThat(incoming.getHeaders().get("requestId"))
                .isEqualTo("A");
        sendReply(incoming, "accepted-A");

        Message<?> reply = call.get(2, TimeUnit.SECONDS);
        assertThat(reply).isNotNull();
        assertThat(reply.getPayload()).isEqualTo("accepted-A");
        assertThat(reply.getHeaders().get("requestId")).isEqualTo("A");
        assertThat(requests.receive(0)).isNull();
    }

    @Test
    void missing_reply_causes_receive_timeout()
            throws Exception {
        Future<Message<?>> call = startCall("NO-REPLY", 150);
        Message<?> incoming = nextRequest();
        assertThat(incoming.getHeaders().get("requestId"))
                .isEqualTo("NO-REPLY");

        // Không gửi reply. Caller kết thúc chờ.
        assertThat(call.get(2, TimeUnit.SECONDS)).isNull();
        assertThat(requests.receive(0)).isNull();

        // Đã timeout không đồng nghĩa worker bị hủy:
        // biến incoming vẫn đại diện cho request đã được lấy ra.
        assertThat(incoming.getPayload()).isEqualTo("payload-NO-REPLY");
    }

    @Test
    void late_reply_does_not_turn_timed_out_call_into_success()
            throws Exception {
        Future<Message<?>> callA = startCall("A", 150);
        Message<?> requestA = nextRequest();

        // Chứng minh A đã timeout TRƯỚC khi gửi late reply.
        assertThat(callA.get(2, TimeUnit.SECONDS)).isNull();

        Message<String> lateA = MessageBuilder
                .withPayload("late-result-A")
                .setHeader("requestId", "A")
                .build();

        // Đích reply tạm có thể nhận, từ chối hoặc báo lỗi
        // sau khi caller đã thôi đợi, tùy endpoint/phiên bản.
        try {
            replyTo(requestA).send(lateA);
        } catch (MessagingException expiredReplyDestination) {
            // Đây là kết quả có thể xảy ra với reply quá hạn.
        }

        // B là request khác, có replyChannel của B.
        Future<Message<?>> callB = startCall("B", 1_000);
        Message<?> requestB = nextRequest();
        assertThat(requestB.getHeaders().get("requestId"))
                .isEqualTo("B");
        sendReply(requestB, "accepted-B");

        Message<?> resultB = callB.get(2, TimeUnit.SECONDS);
        assertThat(resultB).isNotNull();
        assertThat(resultB.getPayload()).isEqualTo("accepted-B");
        assertThat(resultB.getHeaders().get("requestId"))
                .isEqualTo("B");
        assertThat(requests.receive(0)).isNull();
    }
}
~~~

### Diễn giải chính xác các assertion

**Test 1 — Reply đúng hạn:** Caller nhận được \`accepted-A\` vì test đã gửi reply đến đúng kênh tạm của request A trước khi hết thời hạn.

**Test 2 — Không có reply:** \`MessagingTemplate\` trả \`null\` khi hết \`receiveTimeout\`. Request đã được lấy ra vẫn tồn tại như một công việc mà downstream có thể tiếp tục thực hiện.

**Test 3 — Late reply:** Test chỉ gửi \`late-result-A\` **sau khi Future của A đã trả về \`null\`**, nên không có race về việc reply A đến trước hay sau deadline. Sau đó B có một request/reply riêng và nhận đúng \`accepted-B\`, không phải \`late-result-A\`.

Không nên assert rằng **mọi** đích reply tạm sẽ luôn ném exception hoặc luôn chấp nhận reply quá hạn. Chi tiết này phụ thuộc channel, phiên bản và cách cấu hình đường trả lời. Điều cần kiểm tra ở ranh giới nghiệp vụ là: **kết quả muộn không biến call A đã timeout thành success và không xuất hiện như reply của B**.

**Giới hạn phạm vi:** Đây là test thực sự cho \`MessagingTemplate\`, không phải test proxy \`@MessagingGateway\`. Nó kiểm tra thao tác request–reply nền tảng mà Gateway sử dụng. Khi triển khai \`@MessagingGateway\`, hãy có thêm test riêng cho method return type, timeout annotation và chính sách exception.

## 8. Viết test trực tiếp cho @MessagingGateway

Gateway proxy có thể được khai báo:

~~~java
import org.springframework.integration.annotation.MessagingGateway;
import org.springframework.integration.annotation.Gateway;

@MessagingGateway(
        defaultRequestChannel = "checkout.requests",
        defaultReplyTimeout = "200")
public interface CheckoutGateway {

    String checkout(String orderId);

    @Gateway(replyTimeout = 500)
    String checkoutWithLongerWait(String orderId);
}
~~~

Để dùng interface này trong Spring context, có thể cấu hình:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.IntegrationComponentScan;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;

@Configuration
@EnableIntegration
@IntegrationComponentScan(basePackageClasses = CheckoutGateway.class)
class CheckoutTestConfiguration {

    @Bean("checkout.requests")
    QueueChannel requests() {
        return new QueueChannel();
    }
}
~~~

Với \`QueueChannel\` đầu vào và không có consumer được cấu hình trong test, một thread gọi \`gateway.checkout("order-1")\` sẽ gửi request vào queue rồi đợi reply. Test có thể chạy gateway call bằng \`ExecutorService\`, lấy request từ bean \`checkout.requests\`, lấy header \`replyChannel\`, gửi reply đúng hạn hoặc cố ý không gửi để quan sát timeout.

**Khi kiểm tra riêng Gateway proxy**, cần xác minh:

1. Giá trị trả về của method là đúng payload của reply khi có kết quả.
2. Với chính sách mặc định, method có thể trả \`null\` khi timeout.
3. Nếu cấu hình \`errorOnTimeout=true\` (Spring Integration 6.2+), một \`MessageTimeoutException\` được ném khi không có error channel phù hợp, hoặc lỗi được xử lý theo error channel nếu đã cấu hình.
4. Hai method có \`replyTimeout\` khác nhau tuân theo timeout đã khai báo.
5. Không có reply nào bị ghép nhầm giữa các lời gọi đồng thời.

Đừng dùng assertion kiểu “nhất định kết thúc trong đúng 200 ms”. Scheduler, CI load và thread startup làm thời gian thực dao động; hãy dùng timeout hữu hạn để tránh treo test, còn việc kiểm tra giá trị cấu hình nên thực hiện độc lập.

## 9. errorOnTimeout, null và lỗi downstream là ba trường hợp khác nhau

Trong Spring Integration 6.2+, \`@MessagingGateway\` có \`errorOnTimeout\`:

~~~java
@MessagingGateway(
        defaultRequestChannel = "checkout.requests",
        defaultReplyTimeout = "200",
        errorOnTimeout = true)
public interface StrictCheckoutGateway {
    String checkout(String orderId);
}
~~~

Nếu gateway hết thời hạn nhận reply, tùy cấu hình error channel, lỗi timeout có thể được gửi đi hoặc được ném dưới dạng \`MessageTimeoutException\`. Không phải mọi exception từ downstream đều là timeout.

| Trường hợp | Cách nhận diện | Điều cần kiểm thử |
| --- | --- | --- |
| Gateway đợi reply quá hạn | Không có reply trước hạn | \`null\` hoặc \`MessageTimeoutException\` theo policy |
| Service Activator ném exception | Có lỗi thực thi | Exception gốc/error message/correlation phù hợp |
| Filter loại message | Không có reply | Có discard/exception/requires-reply rõ ràng |
| Router không tìm được route | Không có đích hoặc route lỗi | \`resolutionRequired\` hoặc fallback theo contract |
| Handler trả \`null\` | Không có reply message | \`requiresReply\` nếu flow bắt buộc trả lời |
| Request channel đầy | Gửi request không thành công | \`requestTimeout\`/send failure, không đánh đồng reply timeout |

Nếu sử dụng \`requiresReply\` ở endpoint hoặc \`throwExceptionOnRejection\` cho Filter, các lỗi thiếu reply có thể được biểu diễn bằng exception rõ hơn thay vì chờ đến timeout. Điều này cải thiện khả năng chẩn đoán nhưng không thay thế hợp đồng timeout của Gateway.

## 10. Late reply phải được xử lý như một trạng thái nghiệp vụ

Một reply muộn không nhất thiết vô dụng. Ví dụ, hệ thống vận chuyển có thể đã tạo nhãn giao hàng thành công dù Gateway HTTP đã timeout. Nếu caller retry ngay và hệ thống tạo nhãn lần hai, lỗi sẽ đến từ **side effect bị lặp**, không phải chỉ từ chuyện return value.

Vì vậy cần xác định chính sách:

| Chính sách | Ví dụ | Cách kiểm tra |
| --- | --- | --- |
| **Bỏ reply quá hạn** | Dữ liệu realtime đã hết giá trị | Có counter/trace cho late reply, không update request mới |
| **Lưu kết quả bất đồng bộ** | Người dùng có thể tra cứu trạng thái sau | Tra cứu theo \`requestId\` thấy kết quả cuối |
| **Phát sự kiện hoàn tất** | Đơn hàng chuyển trạng thái sau timeout | Event có correlation key và chống lặp |
| **Gửi đến late-reply channel** | Vận hành cần đối soát | Message được route đúng channel theo policy |
| **Compensate** | Side effect cần đảo sau timeout | Bước bù trừ có điều kiện và kiểm tra idempotent |

Đây là **chính sách ứng dụng**: Spring Integration không mặc định biến mọi reply muộn thành dead-letter hoặc tự rollback tác vụ downstream. Đừng tạo \`lateReplyChannel\` trên sơ đồ rồi coi như Gateway tự động định tuyến tới đó; cần triển khai logic nhận diện và chuyển hướng thật sự.

### Một bộ phân loại late reply theo requestId

Để biết reply có còn hợp lệ, ứng dụng thường lưu thông tin request đang chờ và deadline:

~~~text
Pending requests:
  A -> waiting until t=200
  B -> waiting until t=400

Khi reply(A) đến ở t=250:
  A đã quá hạn -> classify as LATE

Khi reply(B) đến ở t=300:
  B còn thời hạn -> classify as ON_TIME
~~~

Không chỉ dùng \`replyChannel\` để nhận diện request. Trong nhiều luồng, \`replyChannel\` là kênh tạm phục vụ một invocation. Nếu cần đối soát sau khi caller kết thúc, hệ thống nên dùng khóa nghiệp vụ bền vững như \`tenantId + requestId + attemptId\` và một store theo dõi trạng thái.

## 11. Kiểm thử logic phân loại late reply không phụ thuộc đồng hồ thật

Tách logic nghiệp vụ khỏi hệ thống messaging giúp test không phụ thuộc scheduler. Ví dụ hàm phân loại:

~~~java
import java.time.Instant;

enum ReplyStatus {
    ON_TIME, LATE, UNKNOWN
}

static ReplyStatus classify(
        Instant deadline, Instant receivedAt) {
    if (deadline == null) {
        return ReplyStatus.UNKNOWN;
    }
    return receivedAt.isAfter(deadline)
            ? ReplyStatus.LATE
            : ReplyStatus.ON_TIME;
}
~~~

Và các assertion theo mốc thời gian **được cung cấp**, không phải \`System.currentTimeMillis()\`:

~~~java
@Test
void classifies_reply_using_explicit_deadline() {
    Instant deadline = Instant.parse("2026-11-21T08:00:00Z");

    assertThat(classify(
            deadline, deadline.minusMillis(1)))
            .isEqualTo(ReplyStatus.ON_TIME);

    assertThat(classify(deadline, deadline))
            .isEqualTo(ReplyStatus.ON_TIME);

    assertThat(classify(
            deadline, deadline.plusMillis(1)))
            .isEqualTo(ReplyStatus.LATE);

    assertThat(classify(
            null, deadline.plusMillis(1)))
            .isEqualTo(ReplyStatus.UNKNOWN);
}
~~~

Đây là **minh họa quy tắc nghiệp vụ**. Trong hệ thống thực tế, cần thống nhất deadline được đo tại đâu, có tính thời gian chuyển tiếp/buffer hay không, và đồng hồ giữa các thành phần có đồng bộ không.

Đặc biệt, quy tắc \`receivedAt == deadline\` phải được ghi rõ. Ví dụ trên coi đúng bằng deadline là còn hợp lệ; một hệ thống khác có thể dùng dấu \`>=\` để coi đó là timeout. Điều quan trọng là test xác minh **chính sách đã chọn**, không tự mặc định một quy tắc cho mọi dịch vụ.

## 12. Correlation và chống ghép nhầm reply

Một Gateway request–reply thường dùng reply channel/correlation nội bộ để ghép reply với invocation. Tuy nhiên, khi flow đi qua broker, adapter hoặc dùng reply channel chung, ứng dụng phải bảo đảm correlation end-to-end.

~~~mermaid
flowchart TD
    A["Request A / requestId=A"] --> Q["Async requests"]
    B["Request B / requestId=B"] --> Q
    Q --> W["Worker"]
    W --> RA["Reply A / requestId=A"]
    W --> RB["Reply B / requestId=B"]
    RA --> CA{"Kiểm tra correlation + deadline"}
    RB --> CA
    CA -->|"Còn pending đúng khóa"| OK["Giao đúng caller"]
    CA -->|"Hết hạn / không có khóa"| LATE["Late / Orphan handling"]
~~~

Các tình huống phải test:

1. A và B cùng gửi, B trả trước A: mỗi caller vẫn nhận đúng reply.
2. A đã timeout; reply A đến sau, trong lúc B còn đợi: B **không** nhận reply A.
3. Reply mang \`requestId\` không tồn tại: không được tự gửi cho request gần nhất.
4. Reply có cùng \`requestId\` nhưng khác tenant: không trộn dữ liệu.
5. Retry tạo attempt mới: phân biệt \`requestId\` nghiệp vụ với \`attemptId\` của từng lần gửi.
6. Duplicate reply: không tạo hai lần chuyển trạng thái nghiệp vụ nếu hợp đồng chỉ cho phép một kết quả.

**Không dùng một QueueChannel reply chung mà thiếu correlation strategy rõ ràng.** Nếu nhiều request cùng đọc từ một queue không phân biệt ID, thứ tự đến bất đồng bộ có thể làm reply A bị người đợi B lấy mất.

## 13. Retry sau timeout: tình huống có thể tạo tác dụng phụ lặp

Giả sử A gọi tạo đơn hàng; Gateway timeout ở mốc 200 ms nhưng worker lưu database xong ở 300 ms. Caller retry bằng request A và một worker khác cũng lưu đơn hàng.

~~~text
t=0    Request A attempt=1
t=200  Caller timeout; worker 1 vẫn chạy
t=210  Caller retry attempt=2
t=300  Worker 1 commit thành công
t=350  Worker 2 cố commit lại
~~~

Khi kiểm thử tình huống này, hãy assert:

- Cả hai attempt được ghi nhận bằng ID rõ ràng.
- Side effect nghiệp vụ chỉ xảy ra đúng số lần theo chính sách (thường một lần nếu thao tác idempotent).
- Late reply attempt 1 không được dùng để hoàn thành sai attempt 2.
- Retry có giới hạn, backoff và cơ chế kiểm tra trạng thái nếu cần.
- Error channel và audit log cho phép phân biệt timeout với xử lý nghiệp vụ thất bại.

Một mô hình phổ biến là dùng **idempotency key** và lưu trạng thái kết quả theo khóa nghiệp vụ, ví dụ \`tenantId + orderId\`. Nếu caller timeout, việc tra cứu kết quả cũ có thể an toàn hơn gửi một tác vụ tạo mới không được bảo vệ.

Không xem \`requestTimeout\`, \`replyTimeout\` hoặc \`errorOnTimeout\` là cơ chế exactly-once. Chúng điều chỉnh cách caller gửi/đợi và báo lỗi, **không** tự biến side effect downstream thành giao dịch bất khả lặp.

## 14. Những lưu ý khi kiểm thử bất đồng bộ

### Tránh test dựa vào Thread.sleep

Test kiểu sau dễ flaky:

~~~java
// Không nên dùng đây làm assertion chính cho late reply:
Thread.sleep(250);
assertThat(gateway.checkout("A")).isNull();
~~~

Nó không điều khiển được chính xác thời điểm request được lấy hay reply được phát. Trong CI, thread startup và tải máy có thể thay đổi.

Thay vào đó:

- Dùng \`QueueChannel\` để chặn việc xử lý tự động và chủ động lấy request.
- Gửi reply **trước khi** Future kết thúc để kiểm tra happy path.
- Đợi Future xác nhận timeout, **sau đó** mới gửi reply để kiểm tra late path.
- Dùng \`CountDownLatch\`, barrier hoặc executor được kiểm soát để phối hợp thread khi cần.
- Đặt timeout hữu hạn cho \`Future.get\` và \`QueueChannel.receive\` để test không treo.
- Tách test về nghiệp vụ deadline khỏi test thật với đồng hồ hoặc thread.

### Timeout ở ranh giới là race hợp lệ

Khi reply đến gần sát deadline, kết quả có thể thay đổi theo lịch thực thi. Không nên viết một test không ổn định rồi coi mỗi lần nhận kết quả khác là lỗi. Chọn hai tình huống rõ ràng **trước hạn** và **sau khi đã xác nhận hết hạn**, sau đó kiểm tra race ở ranh giới bằng test chuyên biệt nếu sản phẩm thực sự cần semantics chi tiết.

### Cô lập test case

Nếu nhiều test dùng chung reply channel, worker pool, message store hoặc pending-request registry, message trễ của test trước có thể ảnh hưởng test sau. Mỗi test nên:

1. Có \`requestId\` duy nhất hoặc namespace riêng.
2. Tiêu thụ/dọn các request và reply liên quan.
3. Đóng executor đúng cách.
4. Không tiếp tục gửi vào channel của Spring context đã bị đóng.
5. Kiểm tra không còn pending request sau khi timeout/hoàn tất nếu registry do ứng dụng quản lý.

## 15. Tương tác với Router, Filter, Aggregator và error channel

Các pattern phía sau Gateway có thể làm việc chờ reply kéo dài hoặc khiến reply không đến:

| Pattern / endpoint | Tình huống dễ gây timeout | Cách kiểm thử |
| --- | --- | --- |
| **Router** | Không có route hợp lệ hoặc reply đi nhầm nhánh | Test từng route và default/error policy |
| **Filter** | Message bị loại nhưng Gateway vẫn đợi | Test discard channel hoặc ném exception theo policy |
| **Transformer** | Transform lỗi hoặc đổi/mất header | Kiểm tra payload và correlation cần giữ |
| **Splitter/Aggregator** | Thiếu fragment nên Aggregator không release | Gửi đủ/thiếu fragment, kiểm tra group timeout |
| **Gateway lồng nhau** | Timeout tổng nhỏ hơn thời gian chờ các bước con | Test budget và propagation |
| **Retry** | Backoff làm reply đến sau deadline | Test attempts, recovery và idempotency |
| **Error channel** | Exception xuất hiện nhưng không được caller quan sát | Kiểm tra error route, cause và requestId |
| **ExecutorChannel/Broker** | Queue hoặc scheduling khiến downstream chậm | Test async handoff, timeout và late-result policy |

Nếu một Aggregator có \`groupTimeout\` lớn hơn \`replyTimeout\` của Gateway, caller có thể timeout trước khi nhóm đủ phần tử. Đó không nhất thiết là lỗi Aggregator, nhưng là **mâu thuẫn về ngân sách thời gian** nếu ứng dụng hứa reply đồng bộ.

## 16. Quan sát timeout và late reply trong vận hành

Khi chạy production, việc đếm tổng timeout không đủ. Nên phân biệt:

| Metric / log | Ý nghĩa | Gợi ý nhãn |
| --- | --- | --- |
| \`gateway_request_timeout_total\` | Không gửi được request trong hạn | Gateway, route, loại lỗi |
| \`gateway_reply_timeout_total\` | Caller hết hạn đợi reply | Gateway, service, class |
| \`reply_latency_seconds\` | Thời gian từ lúc bắt đầu đợi đến khi nhận reply | Handler/service; p50/p95/p99 |
| \`late_reply_total\` | Reply đến sau deadline ứng dụng | Nhánh xử lý, nhóm yêu cầu |
| \`orphan_reply_total\` | Không còn pending request phù hợp | Adapter/service |
| \`pending_requests\` | Số request còn đang chờ | Gateway/class |
| \`handler_duration_seconds\` | Thời gian downstream chạy | Handler/class |
| \`retry_attempts_total\` | Số lần thử lại | Route/error class |

\`requestId\` và \`correlationId\` nên có trong tracing/log có cấu trúc, nhưng **không** nên dùng các ID có cardinality cao làm label metric cho mỗi request. Không ghi token, dữ liệu nhạy cảm hoặc toàn bộ payload vào log chỉ để chẩn đoán timeout.

Đặt cảnh báo theo **tỉ lệ reply timeout**, **tuổi pending request** và **late reply bất thường**. Nếu late reply tăng mà handler vẫn hoàn tất thành công, hãy kiểm tra queue wait, timeout budget hoặc xử lý quá chậm, thay vì kết luận tất cả request đều thất bại.

## 17. Ma trận kiểm thử đề xuất

| Kịch bản | Input / cách điều khiển | Assertion chính |
| --- | --- | --- |
| Reply đúng hạn | Nhận request rồi gửi reply ngay | Caller nhận đúng payload |
| Không reply | Không gửi vào \`replyChannel\` | Caller kết thúc theo timeout policy |
| Reply quá hạn | Đợi caller timeout rồi mới reply | Không hồi sinh call đã kết thúc |
| Reply A, B đảo thứ tự | Hai request có ID riêng | Không cross-deliver |
| Late A trong lúc B pending | Timeout A rồi khởi tạo B | B chỉ nhận reply B |
| DirectChannel handler chậm | Handler chạy đồng bộ | Không giả định reply timeout ngắt handler |
| Queue đầu vào đầy | Bounded channel không nhận thêm | Request timeout/send error đúng policy |
| Filter loại message | Không có reply bình thường | Discard/error policy đúng |
| Aggregator thiếu phần tử | Một nhóm chưa complete | Gateway timeout nhưng group không bị coi là complete |
| Retry sau timeout | Attempt 2 khi attempt 1 còn chạy | Side effect không lặp trái contract |
| Duplicate late reply | Hai lần reply cho request đã hết hạn | Không tạo hai trạng thái success |
| Không có correlation | Reply không xác định request | Không gán cho caller bất kỳ |
| Downstream exception | Worker phát exception | Lỗi/error channel phản ánh nguyên nhân thực |
| Race sát deadline | Điều khiển scheduling rõ ràng | Không kỳ vọng ordering không được bảo đảm |

## 18. Bài thực hành

### Bài A — Kiểm tra reply timeout tại Gateway proxy

Tạo \`@MessagingGateway(defaultRequestChannel="requests", defaultReplyTimeout="200")\` và một \`QueueChannel\` tên \`requests\`. Gọi method Gateway từ thread riêng. Đọc request nhưng **không** gửi reply. Kiểm tra method trả \`null\` theo chính sách và không treo vô hạn. Sau đó bật \`errorOnTimeout=true\` trên Spring Integration 6.2+, kiểm tra hành vi exception/error channel theo cấu hình.

### Bài B — Chứng minh replyTimeout không ngắt DirectChannel đồng bộ

Tạo flow đồng bộ với một Service Activator chạy lâu hơn \`replyTimeout\` của Gateway. Quan sát caller không được cắt ngang chỉ bởi reply timeout khi handler chiếm thread gửi. Sau đó thay bằng \`QueueChannel\` và poller/worker riêng, kiểm tra caller có thể kết thúc chờ khi quá hạn.

### Bài C — Late reply và request mới

Sử dụng ví dụ \`ReplyTimeoutAndLateReplyTest\` để cho A timeout, rồi gửi reply A muộn. Bắt đầu B và trả reply B đúng hạn. Xác minh B không nhận nhầm kết quả A. Thảo luận vì sao không được phụ thuộc vào một reply queue chung thiếu correlation.

### Bài D — Retry và idempotency

Giả lập worker tạo đơn hàng xong **sau** khi Gateway trả timeout. Caller retry cùng \`orderId\`. Thiết kế khóa idempotency và assert chỉ tạo một đơn hàng, dù có hai attempt. Ghi nhận late reply attempt đầu mà không chuyển trạng thái nhầm cho attempt sau.

### Bài E — Timeout budget cho Aggregator

Tạo luồng Splitter → Aggregator, nhóm gồm ba message. Đưa phần tử cuối đến sau \`replyTimeout\` của Gateway. Kiểm tra caller timeout đúng policy, Aggregator vẫn có trạng thái nhóm phù hợp và kết quả đến muộn được phân loại theo \`correlationId\`. Đặt rõ nhóm sẽ tiếp tục hoàn tất hay bị expire.

## 19. Checklist trước khi kết luận test đạt

1. Đã phân biệt rõ **send/request timeout** và **reply/receive timeout** chưa?
2. Có ranh giới bất đồng bộ khi mong đợi timeout cắt việc đợi caller đối với handler chạy lâu không?
3. Có test reply đúng hạn, không reply và late reply bằng **tín hiệu xác định** không?
4. Có tránh khẳng định thời gian kết thúc chính xác từng mili giây trong CI không?
5. Nếu timeout trả \`null\`, tầng nghiệp vụ có phân biệt được với kết quả rỗng hợp lệ không?
6. Nếu dùng \`errorOnTimeout\`, đã test exception/error channel theo phiên bản Spring Integration chưa?
7. Late reply có được phân loại theo request/attempt và không ghép nhầm với caller mới không?
8. Retry sau timeout có cơ chế idempotency hoặc reconciliation để ngăn side effect lặp không?
9. Đã tách lỗi downstream, Filter/Router discard và timeout thật thành các tình huống riêng chưa?
10. Có đo pending requests, reply latency, timeout rate và late reply theo các nhánh quan trọng không?
11. Test có giới hạn thời gian \`Future.get\`, \`receive\` và dọn worker/thread sau mỗi case không?
12. Có chính sách rõ khi reply quá hạn được bỏ qua, lưu lại, chuyển error/late channel hoặc phát sự kiện không?

**Kết luận:** Reply timeout chỉ kết thúc **việc chờ của caller** theo cấu hình, không bảo đảm hủy tác vụ đã gửi. Kiểm thử tốt cần chứng minh request–reply đúng hạn, caller kết thúc chờ khi hết hạn, phản hồi muộn được xử lý an toàn và correlation không bị trộn giữa các lần gọi. Khi kết hợp các kiểm tra đó với idempotency, error channel, retry và quan sát bất đồng bộ, hệ thống Spring Integration có thể phản hồi có kiểm soát mà không mất dấu những công việc vẫn đang tiến hành sau timeout.

### Tài liệu tham khảo

- [Spring Integration Reference — Messaging Gateways](https://docs.spring.io/spring-integration/reference/gateway.html): phân biệt request/reply timeout, DirectChannel đồng bộ và luồng đa thread, \`errorOnTimeout\`.
- [Spring Integration Reference — Annotation Support](https://docs.spring.io/spring-integration/reference/configuration/annotations.html): đăng ký interface \`@MessagingGateway\` thông qua \`@IntegrationComponentScan\`.
- [Spring Integration API — MessagingGateway 6.4.2](https://docs.spring.io/spring-integration/docs/6.4.2/api/org/springframework/integration/annotation/MessagingGateway.html): \`defaultRequestTimeout\`, \`defaultReplyTimeout\`, \`errorOnTimeout\`.
