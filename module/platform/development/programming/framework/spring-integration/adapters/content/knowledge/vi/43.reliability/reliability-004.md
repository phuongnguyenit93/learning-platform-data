# Recoverer sau khi retry hết lượt

**Chương:** Reliability  
**Bài học:** Recoverer sau khi retry hết lượt  
**Module:** Spring Integration Adapters  
**Phạm vi:** Thiết kế và triển khai chiến lược xử lý message khi một adapter hoặc message handler đã thử lại đủ số lần nhưng vẫn thất bại; bao gồm `RequestHandlerRetryAdvice`, Spring Retry, `RecoveryCallback`, `ErrorMessageSendingRecoverer`, `MessageChannel`, dead-letter flow, idempotency, acknowledgment và kiểm toán vận hành.

## 1. Vấn đề cần giải quyết

Một luồng Spring Integration thường phải giao tiếp với hệ thống ngoài: HTTP API, SFTP, JMS, AMQP, Kafka, file system hoặc cơ sở dữ liệu. Những kết nối này có thể lỗi tạm thời, chẳng hạn timeout, quá tải, mất mạng ngắn hạn hay dịch vụ trả mã lỗi máy chủ. **Retry** cho hệ thống cơ hội hồi phục mà không phải can thiệp thủ công.

Tuy nhiên, nếu đã thử lại hết số lượt mà vẫn thất bại thì sao?

- Nếu chỉ ném exception, một upstream adapter có thể rollback, redeliver hoặc dừng xử lý tùy cách cấu hình.
- Nếu ghi log rồi bỏ qua, message có nguy cơ bị mất về mặt nghiệp vụ.
- Nếu gửi message về đúng một error channel rồi không có consumer bền vững, failure vẫn có thể không được xử lý.
- Nếu tiếp tục retry vô hạn, một bản tin lỗi có thể chiếm thread, gây quá tải downstream hoặc tạo vòng lặp.

**Recoverer** là bước quyết định **làm gì sau khi retry đã cạn**. Nó không có nghĩa bản thân yêu cầu đã thành công. Một chiến lược recovery đúng cần bảo toàn thông tin thất bại, chọn nơi lưu/trả lỗi/đẩy DLQ, bảo đảm trạng thái acknowledgment phù hợp và cung cấp đường xử lý hoặc replay có kiểm soát.

### 1.1. Tình huống minh họa

Luồng nhận file qua SFTP, chuyển từng bản ghi thành message rồi gửi sang HTTP API của đối tác:

~~~text
SFTP inbound adapter
    -> transform/validate
    -> MessageChannel
    -> HTTP outbound gateway / handler
    -> API đối tác
~~~

API đối tác bị timeout. Hệ thống thử tổng cộng ba lần. Sau lần thứ ba, nếu vẫn timeout, luồng phải tạo **failure record** có message ID, file nguồn, correlation ID, lỗi cuối cùng và trạng thái **RETRY_EXHAUSTED**, sau đó xử lý theo chính sách: lưu vào failure store, gửi tới dead-letter flow hoặc chuyển cho đội vận hành.

Điểm quan trọng là retry và recovery là **hai giai đoạn khác nhau**:

1. **Retry:** Thử lại cùng thao tác theo một chính sách hữu hạn.
2. **Recovery:** Đưa ra kết quả cuối sau khi số lần thử đã hết hoặc lỗi được xác định là không thể retry.

## 2. Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích mối quan hệ giữa `RetryTemplate`, `RequestHandlerRetryAdvice`, `RecoveryCallback` và `ErrorMessageSendingRecoverer`.
2. Phân biệt **lỗi tạm thời** với **lỗi vĩnh viễn** để tránh retry những tác vụ không có khả năng thành công.
3. Cấu hình số lần thử, backoff và recoverer ở một message handler của Spring Integration.
4. Chọn recovery action phù hợp: **propagate exception**, **error channel**, **durable failure store**, **dead-letter destination** hoặc **fallback** có hợp đồng rõ.
5. Phân tích ảnh hưởng của recovery tới ack/nack, transaction, gateway response và broker redelivery.
6. Thiết kế idempotency, correlation và replay cho các adapter File/SFTP, HTTP, JMS, AMQP, Kafka và JDBC.
7. Lập test matrix và chỉ số theo dõi retry exhaustion mà không làm lộ payload, credentials hoặc thông tin nhạy cảm.

## 3. Phân biệt các lớp xử lý lỗi

| Thành phần | Chức năng | Không tự bảo đảm |
| --- | --- | --- |
| **Message handler** | Thực hiện logic nghiệp vụ hoặc gọi hệ thống ngoài | Không tự quản lý retry bền vững |
| **RetryTemplate (Spring Retry)** | Quyết định số lượt, exception nào có thể retry và thời gian chờ | Không tự lưu DLQ hay ack đúng cho broker |
| **RequestHandlerRetryAdvice** | Bao retry quanh một Spring Integration request handler phù hợp | Không tự áp cho mọi đoạn của toàn flow |
| **RecoveryCallback** | Quyết định kết quả khi retry bị cạn | Không mặc định có persistence hay audit |
| **ErrorMessageSendingRecoverer** | Gửi một `ErrorMessage` tới channel được chỉ định | Không mặc định ghi bền hoặc tạo broker DLQ |
| **Error channel / error flow** | Tiếp nhận, định tuyến và xử lý thông điệp lỗi | Không mặc định làm lỗi nghiệp vụ đã được khắc phục |
| **Broker retry / DLQ** | Cơ chế retry, redelivery hoặc dead-letter theo broker/container | Không đồng nghĩa retry trong handler advice |
| **Transaction / acknowledgment** | Quyết định commit, rollback hoặc xác nhận message nguồn | Phụ thuộc adapter, nguồn và cấu hình cụ thể |

### 3.1. Retry exhaustion là trạng thái nào?

Giả sử đặt **maxAttempts = 3**. Giá trị này thông thường tính **cả lần gọi đầu tiên**:

~~~text
Attempt 1: gửi HTTP -> timeout
Backoff 1: chờ theo cấu hình
Attempt 2: gửi HTTP -> timeout
Backoff 2: chờ theo cấu hình
Attempt 3: gửi HTTP -> timeout
RetryTemplate: không thử lần 4
RecoveryCallback: được gọi với thông tin thất bại cuối
~~~

Như vậy **ba attempts là một lần đầu + hai lần retry**, không phải một lần đầu + ba lần retry. Nếu một exception được xác định là **non-retryable**, recovery có thể được thực hiện mà không chạy đủ ba attempts.

### 3.2. Retry exhaustion không chứng minh downstream chưa xử lý

Đặc biệt với HTTP, JMS hoặc thao tác ghi dữ liệu: **client timeout không đồng nghĩa server chưa nhận hoặc chưa commit tác vụ**. Có thể server đã xử lý, còn response bị mất. Nếu gửi lại thiếu idempotency, cùng đơn hàng có thể được tạo nhiều lần.

Vì vậy thiết kế recoverer phải trả lời hai câu hỏi:

- **Trạng thái kỹ thuật:** Có nhận được response/ack hợp lệ hay không?
- **Trạng thái nghiệp vụ:** Tác vụ có thể đã được downstream thực hiện không?

Khi chưa thể phân biệt, trạng thái trung gian như **OUTCOME_UNKNOWN / RECONCILIATION_REQUIRED** thường trung thực hơn việc tự kết luận FAILED.

## 4. Mô hình retry rồi recover

~~~mermaid
flowchart TD
    IN["Incoming Message"] --> H["Handler / Outbound Adapter"]
    H --> OK{"Thành công?"}
    OK -->|Có| DONE["Tiếp tục flow / reply"]
    OK -->|Không| CL{"Exception retryable?"}
    CL -->|Không| REC["RecoveryCallback"]
    CL -->|Có| N{"Còn lượt thử?"}
    N -->|Có| WAIT["Backoff theo chính sách"]
    WAIT --> H
    N -->|Không| REC
    REC --> CH{"Recovery policy"}
    CH -->|Ném lỗi| PROP["Upstream exception / rollback theo cấu hình"]
    CH -->|Bền vững| STORE["Failure store / DLQ / incident"]
    CH -->|Fallback hợp lệ| FALL["Kết quả thay thế có hợp đồng"]
    STORE --> VERIFY["Xác minh persist + trạng thái nguồn"]
    PROP --> VERIFY
    FALL --> VERIFY
~~~

Sơ đồ thể hiện các quyết định logic. **Một triển khai cụ thể thường chọn một recovery path rõ ràng cho một failure**, không đồng thời coi ném exception và nuốt exception là kết quả giống nhau.

### 4.1. Gọi đúng tên từng thời điểm

| Mốc | Ví dụ trạng thái | Diễn giải |
| --- | --- | --- |
| Trước gửi | RECEIVED | Message được adapter nhận theo cơ chế nguồn |
| Handler thất bại lần đầu | RETRYABLE_FAILURE | Có thể thử lại nếu thuộc nhóm transient |
| Đang chờ retry | RETRY_SCHEDULED | Chưa thể xem là hoàn tất |
| Hết lượt | RETRY_EXHAUSTED | Handler chưa có kết quả thành công |
| Recoverer ghi record | RECOVERY_PERSISTED | Bản ghi failure đã lưu thành công, chưa giải quyết nghiệp vụ |
| Xử lý sau sự cố | REPLAY_REQUESTED | Được phép gửi lại theo runbook |
| Downstream xác nhận | DELIVERED / RECONCILED | Đã có bằng chứng kết quả phù hợp |
| Chưa rõ kết quả | OUTCOME_UNKNOWN | Cần đối soát, tránh gửi lại mù quáng |

**RECOVERY_PERSISTED không đồng nghĩa DELIVERED.** Đây là phân biệt cốt lõi khi xây reliable adapter.

## 5. Ba lựa chọn chính sau retry

### 5.1. Propagate exception

Nếu không cấu hình recovery callback, hoặc callback chủ động ném lại lỗi, thất bại có thể truyền ngược lên caller/adapter theo cách handler được gọi.

Phù hợp khi:

- Inbound adapter có transaction hoặc cơ chế rollback/redelivery đáng tin cậy.
- Muốn broker quyết định retry/DLQ bằng chính sách container.
- Cần gateway trả failure thay vì ngầm coi giao dịch đã được xử lý.
- Chưa thể ghi bản tin thất bại vào nơi bền vững.

**Rủi ro:** Nếu upstream không quản lý lỗi, thread có thể bị lỗi, message có thể bị mất hoặc redelivery vô hạn. Không chọn propagate chỉ vì “để Spring tự lo”.

### 5.2. Publish ErrorMessage rồi xử lý ở error flow

`ErrorMessageSendingRecoverer` chuyển lỗi sau retry sang **MessageChannel** dành cho recovery. Error flow cần xử lý:

1. Nhận exception cuối và message gốc/metadata nếu truy xuất được.
2. Xác định nguyên nhân, destination, correlation và trạng thái kết quả.
3. Ghi failure vào DB, queue hoặc DLQ **có cơ chế bền vững phù hợp**.
4. Chỉ sau khi ghi thành công mới quyết định có thể xác nhận message nguồn hay không.
5. Cung cấp runbook replay, alert và audit.

**Lưu ý:** `ErrorMessageSendingRecoverer` tự nó chỉ **gửi** ErrorMessage. Một `DirectChannel` trong bộ nhớ không phải durable queue. Nếu error flow chỉ ghi log và trả về, message nguồn có thể được xem là đã xử lý ở một số cấu hình, trong khi nghiệp vụ vẫn chưa hoàn thành.

### 5.3. Fallback có chủ đích

`RecoveryCallback` có thể trả một kết quả thay thế **nếu** hợp đồng của handler/gateway cho phép, ví dụ:

- Trả snapshot đã cache cho yêu cầu đọc không nhạy cảm và có chính sách stale data rõ.
- Chuyển trạng thái tác vụ sang **PENDING_RECONCILIATION**.
- Trả kết quả mô tả lỗi tạm thời, không giả mạo thành công.

Không nên trả mặc định `null` hoặc một object “success” để che giấu thất bại. Với **request-reply gateway**, phải đảm bảo caller nhận được reply/error đúng thời hạn và kiểu dữ liệu, vì recoverer dùng để **gửi ErrorMessage** thường không tạo business reply cho gateway.

## 6. Những lỗi nên và không nên retry

| Nhóm lỗi | Ví dụ | Hướng xử lý |
| --- | --- | --- |
| **Transient infrastructure** | Connection reset, timeout tạm thời, DNS/network gián đoạn | Retry hữu hạn với backoff |
| **Remote overload** | HTTP 429, một số HTTP 503 | Retry nếu hợp đồng API cho phép; tôn trọng Retry-After/rate limit |
| **Temporary database contention** | Deadlock hoặc connection pool tạm hết, khi thao tác có thể thử lại an toàn | Retry theo loại lỗi và transaction |
| **Permanent input error** | JSON không hợp lệ, thiếu field bắt buộc, sai schema | Không retry vô ích; chuyển quarantine/failure |
| **Authentication/authorization** | Sai credential, 401/403 do cấu hình quyền | Thường không retry trong vòng ngắn; cảnh báo cấu hình/bảo mật |
| **Not found mang tính nghiệp vụ** | Resource không tồn tại và không có eventual consistency được cam kết | Thường không retry; trả lỗi nghiệp vụ |
| **Idempotency conflict** | Request đã tồn tại với cùng khóa nhưng nội dung khác | Không retry như transient; cần đối soát |
| **Downstream outcome unknown** | Timeout sau khi gửi lệnh thanh toán | Tra cứu trạng thái bằng idempotency/correlation trước khi replay |

Không mặc định tất cả **5xx** đều an toàn để retry: cần biết endpoint có side effect và contract của đối tác. Ngay cả lỗi **4xx** cũng có ngoại lệ được retry theo giao thức/ứng dụng; quyết định cuối phụ thuộc tài liệu API và rủi ro.

### 6.1. Traverse causes đúng cách

Trong Spring Integration, một lỗi gốc có thể được bọc trong `MessagingException` hoặc exception của adapter. Retry policy cần biết có xem **cause chain** hay không.

Ví dụ: một service báo `TemporaryPartnerException`, nhưng handler ném `MessageHandlingException` chứa nó. Nếu policy chỉ kiểm tra lớp exception bên ngoài, lỗi tạm thời có thể bị phân loại sai.

Không được bật “retry toàn bộ Throwable” để giải quyết thiếu hiểu biết về wrapper. Hãy xác định nhóm exception rõ ràng, test cả dạng trực tiếp và dạng bị bọc.

## 7. Java DSL: cấu hình RequestHandlerRetryAdvice

Đây là ví dụ dùng **Spring Integration Java DSL** cùng **Spring Retry** để minh họa cách gắn advice vào một handler. Tên package/overload cần đối chiếu với phiên bản Spring Integration/Spring Retry mà dự án đang sử dụng; các component nghiệp vụ `PartnerSender` và `FailureArchive` do ứng dụng tự triển khai.

### 7.1. Cấu hình retry và recovery channel

~~~java
import java.util.Map;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.handler.advice.ErrorMessageSendingRecoverer;
import org.springframework.integration.handler.advice.RequestHandlerRetryAdvice;
import org.springframework.messaging.MessageChannel;
import org.springframework.retry.backoff.ExponentialBackOffPolicy;
import org.springframework.retry.policy.SimpleRetryPolicy;
import org.springframework.retry.support.RetryTemplate;

@Configuration
public class PartnerReliabilityConfiguration {

    @Bean
    public MessageChannel partnerRecoveryChannel() {
        return new DirectChannel();
    }

    @Bean
    public RequestHandlerRetryAdvice partnerRetryAdvice(
            @Qualifier("partnerRecoveryChannel") MessageChannel recoveryChannel) {

        // 3 attempts = lần gọi đầu tiên + tối đa 2 lần retry.
        Map<Class<? extends Throwable>, Boolean> retryable = Map.of(
                TemporaryPartnerException.class, true);

        SimpleRetryPolicy policy = new SimpleRetryPolicy(
                3, retryable, true /* traverse causes */);

        ExponentialBackOffPolicy backoff = new ExponentialBackOffPolicy();
        backoff.setInitialInterval(500L);
        backoff.setMultiplier(2.0);
        backoff.setMaxInterval(5_000L);

        RetryTemplate template = new RetryTemplate();
        template.setRetryPolicy(policy);
        template.setBackOffPolicy(backoff);

        RequestHandlerRetryAdvice advice = new RequestHandlerRetryAdvice();
        advice.setRetryTemplate(template);
        advice.setRecoveryCallback(
                new ErrorMessageSendingRecoverer(recoveryChannel));

        return advice;
    }

    @Bean
    public IntegrationFlow outboundPartnerFlow(
            PartnerSender partnerSender,
            RequestHandlerRetryAdvice partnerRetryAdvice) {

        return IntegrationFlow.from("partnerOutboundRequests")
                .handle(partnerSender, "send",
                        endpoint -> endpoint.advice(partnerRetryAdvice))
                .get();
    }
}
~~~

**Giải thích:**

- `RetryTemplate` điều phối retry; `SimpleRetryPolicy` giới hạn số attempts và lớp exception hợp lệ.
- `ExponentialBackOffPolicy` đặt khoảng chờ tăng dần, giúp tránh đập dồn dập vào hệ thống đang lỗi.
- `RequestHandlerRetryAdvice` bọc việc gọi **message handler** được gắn advice.
- `ErrorMessageSendingRecoverer` được gọi khi policy xác định cần recovery; nó gửi ErrorMessage tới `partnerRecoveryChannel`.
- `PartnerSender.send(...)` là **method của service do ứng dụng sở hữu**; mã mẫu không định nghĩa giao thức HTTP/SFTP cụ thể.
- Việc recoverer trả về sau khi gửi lỗi có thể khiến lời gọi handler được xem là đã hoàn thành ở một số flow; **nghiệp vụ vẫn chưa thành công**. Phải quyết định semantics của nguồn và caller trước khi bật.

### 7.2. Ví dụ handler nghiệp vụ

~~~java
public class TemporaryPartnerException extends RuntimeException {
    public TemporaryPartnerException(String message, Throwable cause) {
        super(message, cause);
    }
}

public class PartnerSender {
    private final PartnerApiClient apiClient;

    public PartnerSender(PartnerApiClient apiClient) {
        this.apiClient = apiClient;
    }

    // Method dùng bởi Service Activator trong IntegrationFlow.
    public void send(String payload) {
        try {
            apiClient.submit(payload);
        }
        catch (PartnerTimeoutException ex) {
            throw new TemporaryPartnerException(
                    "Partner temporarily unavailable", ex);
        }
        // Lỗi validation, auth, business conflict phải được phân loại riêng;
        // không gom mọi exception thành TemporaryPartnerException.
    }
}
~~~

`PartnerApiClient` và `PartnerTimeoutException` là các kiểu miền nghiệp vụ minh họa, **không phải API có sẵn của Spring Integration**. Trong dự án thật, client HTTP/JMS/SFTP có exception cụ thể; bộ phân loại lỗi phải căn cứ loại exception và contract của hệ thống ngoài.

### 7.3. Recovery handler cần lưu thất bại bền vững

~~~java
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessagingException;
import org.springframework.messaging.support.ErrorMessage;
import org.springframework.stereotype.Component;

@Component
public class PartnerRecoveryHandler {
    private final FailureArchive archive;

    public PartnerRecoveryHandler(FailureArchive archive) {
        this.archive = archive;
    }

    @ServiceActivator(inputChannel = "partnerRecoveryChannel")
    public void onRecovery(ErrorMessage errorMessage) {
        Throwable failure = errorMessage.getPayload();

        Message<?> original = failure instanceof MessagingException me
                ? me.getFailedMessage()
                : errorMessage.getOriginalMessage();

        // Phải thực sự ghi bền + kiểm soát transaction/ack nguồn.
        // Archive tự triển khai và có kiểm tra dữ liệu nhạy cảm.
        archive.persist(original, failure);
    }
}
~~~

`FailureArchive` là **giao diện nghiệp vụ do đội dự án triển khai**, không phải Spring Integration cung cấp sẵn. Handler phải định nghĩa rõ cách bảo toàn payload/reference, độ bền dữ liệu, khóa chống trùng, chính sách lỗi của chính archive và khả năng replay.

**Điểm cần test:** Các phiên bản và đường lỗi khác nhau có thể bọc exception trong các lớp `MessagingException` khác nhau. Không được giả định message gốc luôn có mặt trong cùng một field; nếu không tìm được, hệ thống cần báo lỗi có thể điều tra thay vì persist một failure record không đầy đủ mà xem là thành công.

### 7.4. Không nên dùng recoverer chỉ để ghi log

~~~java
// Đây là anti-pattern trong một luồng cần bảo đảm không mất message.
@ServiceActivator(inputChannel = "partnerRecoveryChannel")
public void logAndForget(ErrorMessage error) {
    log.warn("Delivery failed", error.getPayload());
    // Không có lưu trữ bền, không DLQ, không trạng thái xử lý.
}
~~~

Nếu upstream ack message vì recovery callback đã hoàn thành, còn failure chỉ nằm trong một dòng log khó replay, hệ thống có thể **mất khả năng xử lý nghiệp vụ**, dù vẫn thấy log lỗi.

## 8. RecoveryCallback tùy biến và chiến lược ném lại lỗi

`RequestHandlerRetryAdvice` có thể dùng một `RecoveryCallback` khác, thay vì `ErrorMessageSendingRecoverer`. Cần phân biệt ba hợp đồng:

1. **Trả dữ liệu thay thế:** Chỉ phù hợp khi caller hiểu đây là fallback và kiểu trả về hợp lệ.
2. **Ghi failure rồi return:** Chỉ phù hợp khi failure store bền vững và semantics ack/commit cho phép coi message nguồn đã được tiếp nhận để xử lý sau.
3. **Ném lỗi ra ngoài:** Phù hợp khi cần transaction rollback hoặc giao cho nguồn quyết định redelivery.

~~~java
advice.setRecoveryCallback(context -> {
    Throwable lastFailure = context.getLastThrowable();
    if (lastFailure == null) {
        throw new IllegalStateException("Retry ended without a failure");
    }

    // Trong flow cần để upstream rollback hoặc nack,
    // ném một exception giữ nguyên cause thay vì âm thầm return null.
    throw new IllegalStateException(
            "Outbound handler exhausted retry attempts", lastFailure);
});
~~~

Đoạn này minh họa **một callback cố ý truyền lỗi ngược**. Nơi nào upstream bắt exception, có rollback hay không, và nguồn có redeliver không, phụ thuộc adapter. Đừng dùng callback này nếu yêu cầu thực tế là lưu failure và ack sau khi lưu bền.

### 8.1. RecoveryCallback không phải handler retry thứ tư

Callback nhận `RetryContext` chứa thông tin retry (trong đó có lỗi cuối). Nó không phải một attempt gửi lại tự động. Nếu callback lại gọi external API mà không có idempotency/giới hạn, bạn vừa tạo một **đường retry ẩn**, rất khó đo số lần tác động hệ thống ngoài.

### 8.2. Chọn hành động sau cùng theo nguồn

| Nguồn | Thường cần cân nhắc |
| --- | --- |
| HTTP request-reply gateway | Trả failure có hợp đồng, không nuốt lỗi rồi để caller timeout vô cớ |
| JMS/AMQP inbound | Ack/rollback/redelivery/DLQ phải được xác nhận theo listener container |
| Kafka inbound | Offset commit/seek/error handling của consumer không đồng nghĩa retry handler advice |
| File/SFTP polling | Không có broker ack tương đương; cần persistent filter, move/quarantine và trạng thái file |
| Database polling | Khóa hàng, transaction, trạng thái xử lý và duplicate trên lần poll tiếp theo |
| In-memory DirectChannel | Lỗi có thể lan đồng bộ; không có lưu trữ bền mặc định |

## 9. Recovery channel khác gì global errorChannel?

Spring Integration hỗ trợ các **error channel** và cơ chế `ErrorMessage` trong những kịch bản phù hợp. Tuy nhiên **message đã phát ra recovery channel** và **exception được error flow bắt từ một poller/asynchronous endpoint** không phải lúc nào cũng có cùng điểm xuất phát.

### 9.1. Dedicated recovery channel

Một channel riêng như `partnerRecoveryChannel` có ưu điểm:

- Biết chính xác những failure nào đã **vượt quá retry policy** của một handler.
- Áp retention, alert, quarantine và replay rule riêng cho integration với đối tác.
- Không trộn lỗi parse của file với lỗi HTTP outbound và lỗi container.
- Dễ gắn service owner và correlation metadata.

Nhược điểm: Cần đảm bảo subscriber/error flow luôn hoạt động, không biến nó thành “hố đen” message. `DirectChannel` không tự có durability và có thể truyền exception của recovery handler về caller.

### 9.2. Global errorChannel và header errorChannel

Một số endpoint gửi lỗi tới channel từ header `errorChannel` hoặc global `errorChannel`, tùy cơ chế dispatch và source. Không nên mặc định **mọi exception bất đồng bộ** sẽ về dedicated recovery channel nếu advice chưa được gắn đúng handler, hay mọi exception synchronous sẽ tự được chuyển thành ErrorMessage.

Kiểm tra:

1. Handler nào thực sự được bọc bởi advice?
2. Thread nào đang thực thi handler?
3. Error message được phát tại điểm nào?
4. Recoverer gửi tới channel nào?
5. Channel có consumer không, consumer làm gì khi persist thất bại?
6. Upstream nhận kết quả thành công hay exception sau khi recoverer hoàn thành?

## 10. Retry advice không đồng nghĩa retry toàn flow

`RequestHandlerRetryAdvice` bao phần **handler được cấu hình**. Nếu flow gồm parse → transform → outbound call, advice gắn tại outbound handler thông thường chỉ thử lại phần xử lý outbound đó.

~~~text
SFTP source
  -> parser                 (ngoài handler retry)
  -> transformer            (ngoài handler retry)
  -> outbound HTTP handler  (gắn RequestHandlerRetryAdvice)
  -> downstream
~~~

Lợi ích: Không đọc lại file và không parse lại toàn bộ dữ liệu vì một lỗi transient tại API đối tác. Nhưng hạn chế cũng rõ: Lỗi parse ở upstream **không tự đi qua recoverer của HTTP handler**.

### 10.1. Synchronous và asynchronous boundary

**DirectChannel** thường truyền message đồng bộ trên thread gọi. **ExecutorChannel** hoặc một consumer/poller bất đồng bộ có thể tách thread và ranh giới lan truyền exception.

Khi đặt advice:

- Xác nhận exception được ném ở **phần handler mà advice bọc**, không chỉ ở một callback bất đồng bộ chạy sau đó.
- Nếu một outbound gateway gọi remote API trong thread của handler, retry có thể bao request đó.
- Nếu handler chỉ enqueue công việc rồi trả về, lỗi xảy ra sau đó không tự quay lại lần gọi đã hoàn thành để được retry.
- Xác định rõ retry nào nằm ở application, broker, scheduler, consumer container hoặc remote client.

### 10.2. Request-reply gateway có hợp đồng riêng

Với outbound gateway cần reply, khi recoverer gửi ErrorMessage rồi return mà không tạo reply, caller có thể nhận null, timeout hoặc hành vi khác theo cấu hình/endpoint. **Không sử dụng recovery channel thay thế reply mà không thiết kế rõ hợp đồng lỗi.**

Một cách phù hợp có thể là **ném exception có cấu trúc để inbound gateway trả HTTP 503**, hoặc trả response nghiệp vụ mô tả trạng thái xử lý đang chờ nếu ứng dụng đã lưu yêu cầu bền vững. Lựa chọn phải theo contract và thời hạn chờ của caller.

## 11. Retry policy phải đi cùng timeout và backoff

Nếu một HTTP call có timeout 30 giây và retry ba lần, một thread có thể bị giữ hơn 90 giây cộng thời gian backoff. Đặt retry mà không tính latency budget có thể làm nghẽn thread pool khi downstream gặp sự cố.

### 11.1. Tính latency budget

~~~text
maxAttempts = 3
timeoutPerAttempt = 2 giây
backoff = 0,5 giây rồi 1 giây

Worst-case gần đúng:
    3 * 2 giây + 0,5 giây + 1 giây
  = 7,5 giây

Chưa bao gồm: serialization, scheduling, kết nối, DNS,
độ lệch timeout giữa client/server và overhead khác.
~~~

Khi một upstream gateway chỉ chờ 5 giây, cấu hình này có thể làm request của caller đã hết hạn **trước khi recoverer được gọi**. Cần căn chỉnh tổng thời gian retry, timeout, throughput và SLAs.

### 11.2. Exponential backoff và jitter

Backoff tăng dần giúp giảm tải khi downstream đang lỗi. Jitter làm các client không đồng loạt retry theo cùng nhịp.

Không nên mặc định một cấu hình exponential backoff có **jitter tự động**; lựa chọn policy cụ thể của Spring Retry phải được kiểm tra. Nếu hệ thống có nhiều instance, hãy xem nhu cầu sử dụng backoff với jitter theo khả năng phiên bản thư viện và chính sách vận hành.

### 11.3. Retry storm và backpressure

Nếu 100 consumer cùng retry ba lần, tải gửi tới downstream có thể tăng nhiều lần đúng lúc dịch vụ đang sự cố. Cần kết hợp:

- Concurrency limit / worker pool hợp lý.
- Circuit breaker và bulkhead khi kiến trúc hỗ trợ.
- Rate limiter hoặc tuân thủ `Retry-After`.
- Queue depth monitoring, dead-letter policy và backpressure.
- Giới hạn retry cho mỗi lớp: handler, SDK, broker và workflow.

Tổng số request thực tế có thể lớn hơn `maxAttempts` của một tầng nếu client HTTP hoặc broker cũng tự retry.

## 12. Stateful retry và broker redelivery

**Stateless retry** thường thử nhiều lần trong **một lần handler invocation**; `RetryTemplate` giữ trạng thái trong phạm vi lần gọi đó. Nếu sau exhaustion exception bị ném về broker/container, broker có thể **redeliver message**, khởi tạo một vòng retry mới.

Ví dụ:

~~~text
JMS/AMQP broker redeliver tối đa 4 delivery attempts
RequestHandlerRetryAdvice maxAttempts = 3

Trong trường hợp mỗi delivery đều chạy đủ retry:
    4 broker deliveries x 3 handler attempts
  = tối đa 12 lần gọi downstream
~~~

Đây là **mô hình minh họa**, không khẳng định broker nào cũng dùng mặc định như vậy. Cần xác định lại với cấu hình listener, transaction, nack/requeue và những cơ chế retry ở SDK.

### 12.1. Stateful retry có cần không?

Spring Retry có mô hình **stateful retry** để gắn trạng thái theo một key của message hoặc transaction, dùng cho những tình huống cần nhả exception để transaction rollback rồi thử lại khi message được redeliver. Trong Spring Integration, cấu hình có thể liên quan tới **retry state generator** và `RetryContextCache` theo API được hỗ trợ của phiên bản.

Lưu ý:

- Phải chọn **key ổn định** và duy nhất theo message nghiệp vụ; không dùng giá trị thay đổi ở mỗi delivery.
- In-memory retry context **không mặc nhiên bền vững qua restart**.
- Cache, concurrency và redelivery cần được kiểm thử; một broker khác không dùng cùng semantics.
- Không bật stateful retry chỉ vì muốn “thử lại tốt hơn”: nó làm tăng độ phức tạp transaction và vận hành.

### 12.2. Chọn một nguồn chịu trách nhiệm retry chính

Để dễ tính attempts và bảo đảm recovery, nên xác định rõ:

- Tầng nào retry lỗi kết nối rất ngắn?
- Tầng nào quyết định retry exhaustion?
- Tầng nào quản lý redelivery bền vững?
- Tầng nào đưa message vào DLQ?
- Khi một message quay lại, làm sao giữ cùng idempotency key và attempt lineage?

Không để SDK, handler advice, Spring Kafka container và broker đều retry mà không có ngân sách tổng.

## 13. Tương tác với transaction và acknowledgment

**Đây là phần có ảnh hưởng trực tiếp đến nguy cơ mất hoặc xử lý trùng message.** Sau khi recoverer gửi ErrorMessage rồi trả về thành công, consumer nguồn có thể xem handler hoàn tất. Nhưng chính xác **ack/commit/rollback xảy ra hay không** phụ thuộc adapter, listener container, transaction manager, thread boundary và cấu hình ứng dụng.

### 13.1. Ma trận hành vi cần kiểm chứng

| Nguồn/adapter | Khi recoverer xử lý xong không ném exception | Cần kiểm tra |
| --- | --- | --- |
| JMS inbound | Container có thể commit/ack nếu toàn bộ processing được xem là thành công | Transaction/session acknowledgment, redelivery policy, DLQ |
| AMQP inbound | Container có thể ack theo cấu hình khi handler trả thành công | Ack mode, requeue/nack, DLX và retry advice |
| Kafka inbound | Consumer/container có thể commit offset theo xử lý/ack mode | Offset commit, container error handler, transaction, DLT |
| File inbound | Không có broker ack chung; file vẫn có thể bị filter bỏ qua hoặc poll lại | File state, accept-once filter, move/quarantine, recovery |
| SFTP inbound | Poll/download và remote file lifecycle có thể tách delivery HTTP | Metadata store, filter, local file staging, remote move |
| HTTP inbound | Caller cần status/reply/error phù hợp | Timeout, HTTP response, retry hoàn tất trước hạn |
| JDBC polling | Trạng thái record/transaction quyết định có được đọc lại không | Row claim, lock, processed flag, rollback |

**Không dựa vào bảng để suy ra behavior mặc định.** Mục tiêu là buộc người thiết kế **kiểm tra cấu hình thật** và viết test xác nhận ack/commit sau recovery.

### 13.2. Một hướng an toàn khi muốn ack sau exhaustion

~~~text
Inbound message
  -> handler retry
  -> exhaustion
  -> recovery handler
  -> ghi failure vào kho bền vững
  -> nhận bằng chứng đã persist
  -> chỉ khi đó mới cho nhánh xử lý kết thúc theo ack policy
~~~

Nếu failure store ghi thất bại, recovery handler cần **ném exception hoặc kích hoạt chính sách xử lý nguồn phù hợp**, không nuốt lỗi rồi làm source commit. Việc ghi failure và ack nguồn có thể không nằm trong cùng distributed transaction; khi đó phải thiết kế idempotency và đối soát cho cửa sổ lỗi giữa hai thao tác.

### 13.3. Khi nên để broker quản lý DLQ

Nếu JMS, RabbitMQ hoặc Kafka consumer đã có chiến lược retry/commit/error handler phù hợp ở **container/broker layer**, có thể không cần `RequestHandlerRetryAdvice` cùng loại ở handler, hoặc chỉ dùng advice cho số retry rất ngắn.

Ưu tiên có **một nơi chịu trách nhiệm quyết định failure terminal** và một cách chứng minh message không bị mất/trùng ngoài dự kiến.

## 14. Dead-letter và quarantine: thiết kế failure record

**Dead-letter queue (DLQ)** hoặc **quarantine store** giữ message không xử lý được sau retry để có thể phân tích, sửa dữ liệu và replay. Tên gọi khác nhau tùy broker và kiến trúc; `ErrorMessageSendingRecoverer` không tự tạo DLQ trên JMS/AMQP/Kafka.

### 14.1. Failure envelope tối thiểu

~~~json
{
  "failureId": "fail-2026-11-23-0042",
  "messageId": "msg-84021",
  "correlationId": "order-7321",
  "sourceAdapter": "sftp-orders",
  "destination": "partner-http-api",
  "operation": "submit-order",
  "status": "RETRY_EXHAUSTED",
  "attempts": 3,
  "lastErrorType": "TemporaryPartnerException",
  "firstSeenAt": "2026-11-23T08:00:00Z",
  "lastAttemptAt": "2026-11-23T08:00:02Z",
  "payloadReference": "encrypted-object-ref:orders/msg-84021",
  "replayPolicy": "manual-after-reconciliation"
}
~~~

Đây là **schema nghiệp vụ minh họa**, không phải dữ liệu do `ErrorMessageSendingRecoverer` tự sinh ra. Trường **attempts** phải được lấy từ nguồn có tin cậy nếu cần độ chính xác; không tự ghi 3 nếu exception là non-retryable và chỉ được gọi một lần.

### 14.2. Vì sao dùng payloadReference?

Payload gốc có thể chứa dữ liệu cá nhân, secret, file lớn, nhị phân hoặc reference tới đối tượng đã bị xóa. Thay vì log toàn bộ payload, có thể lưu:

- Bản nội dung mã hóa trong kho bền vững với quyền truy cập phù hợp.
- Reference và checksum để xác minh integrity.
- Message ID / file ID / business key để tái tạo tác vụ.
- Header cần thiết và phiên bản schema/contract.

Không log raw Authorization header, cookie, access key, mật khẩu SFTP hoặc toàn bộ nội dung nghiệp vụ nhạy cảm.

### 14.3. Quarantine khác DLQ ở điểm nào?

Quarantine thường nhấn mạnh **cần sửa hoặc xem xét dữ liệu** trước khi gửi lại. DLQ thường là cơ chế **giữ message lỗi** của broker hoặc application. Cả hai cần:

1. Owner, retention và quyền đọc.
2. Trạng thái xử lý.
3. Đường replay có phê duyệt và audit.
4. Dead-letter message ID liên kết source message ID.
5. Chống vòng lặp khi replay liên tục thất bại.
6. Cleanup hoặc archive theo yêu cầu dữ liệu.

## 15. Idempotency: bảo vệ trước retry và replay

Với thao tác có side effect, **idempotency** quan trọng không kém retry. Một request gửi thành công nhưng response mất có thể bị gửi lại. Nếu downstream không chống trùng, bạn có thể tạo đơn hàng, giao dịch hoặc file trùng.

### 15.1. Ví dụ khóa idempotency

~~~text
Business operation: create-payment
Idempotency key: payment-tenant42-order7321-v1

Attempt 1 -> timeout sau khi gửi
Attempt 2 -> cùng idempotency key
Attempt 3 -> cùng idempotency key
Recovery -> OUTCOME_UNKNOWN
Reconciliation -> tra cứu kết quả theo cùng business key
Replay nếu cần -> vẫn cùng operation key theo contract
~~~

Khóa phải gắn với **thao tác nghiệp vụ**, không phải UUID mới ở mỗi retry. Trường hợp body thay đổi với cùng khóa cần được quy định rõ (thường phải phát hiện conflict).

### 15.2. Các tầng chống trùng

| Tầng | Cách kiểm soát |
| --- | --- |
| Inbound adapter | Persistent filters, source checkpoint, dedup key |
| Spring Integration flow | MetadataStore, Idempotent Receiver khi phù hợp, correlation |
| Database | Unique constraint, upsert, transactional state machine |
| External HTTP API | Idempotency-Key hoặc API contract chống trùng |
| Broker | Message key, deduplication theo broker nếu có hỗ trợ |
| Replay tool | Giữ nguyên operation ID, lưu lịch sử replay |

Không tuyên bố **exactly-once end-to-end** chỉ vì dùng một transaction hoặc một connector. Across SFTP → HTTP → DB → broker, thường cần thiết kế **at-least-once + idempotency + reconciliation** thay vì giả định một giao dịch phân tán hoàn hảo.

## 16. Recovery theo từng adapter

### 16.1. File và SFTP inbound

Rủi ro đặc thù là trạng thái của file nguồn và tiến độ xử lý:

- File đã được download nhưng chưa hoàn tất xử lý.
- Poller có filter ghi nhận file đã nhìn thấy.
- File bị parse thành nhiều messages; một message thất bại sau retry.
- File đã bị move/archive ở bước không phù hợp và không thể replay.
- Nhiều instance có thể đọc cùng file nếu thiếu coordination.

Thiết kế nên có **file ID/checksum, persistent accept-once state khi phù hợp, staging directory, trạng thái từng record và quarantine**, không trông chờ retry HTTP tự quyết định remote SFTP file lifecycle.

### 16.2. HTTP outbound gateway hoặc adapter

Rủi ro đặc thù:

- Timeout không chứng minh server chưa xử lý.
- 429/503 có thể cần retry có backoff và tôn trọng rate limit.
- 400/401/403 thường không phù hợp để retry nhiều lần.
- Gateway cần reply/error rõ với caller.
- Client SDK có thể có retry riêng, làm tăng tổng attempts.

Recovery nên phân biệt **REJECTED**, **TEMPORARY_UNAVAILABLE** và **OUTCOME_UNKNOWN**; khi cần, query trạng thái downstream trước replay.

### 16.3. JMS và AMQP

Rủi ro đặc thù là **redelivery** và **acknowledgment**. Handler advice retry trong lần delivery hiện tại; broker/container có thể retry lần nữa nếu transaction rollback. Nếu recoverer nuốt lỗi và error flow không lưu bền, nguồn có thể ack message lỗi.

Điều phải test:

- Ack/commit khi recoverer return bình thường.
- Rollback/nack khi recoverer hoặc archive ném exception.
- Broker DLQ khi vượt số delivery theo cấu hình thật.
- Chính sách requeue, max redelivery, duplicate và poison message.

### 16.4. Kafka

Kafka có offset và consumer group; retry ở Spring Integration handler không đồng nghĩa với retry của **Spring Kafka listener container error handler**. Phải kiểm tra endpoint thực dùng lớp nào và commit offset theo cấu hình nào.

Kiểm chứng:

- Khi recoverer hoàn tất, offset có commit không?
- Khi lỗi bị propagate, consumer có seek/redelivery hoặc DLT theo thiết kế không?
- Transaction và producer DLT có bảo đảm cần thiết không?
- Replay dùng cùng business key và tránh duplicate side effect thế nào?

### 16.5. JDBC / database polling

Rủi ro đặc thù là row lock và trạng thái record:

- Bản ghi được claim nhưng external API thất bại.
- Transaction rollback khiến record xuất hiện lại.
- Lưu failure và đánh dấu processed nằm ở hai transaction khác nhau.
- Các poller cạnh tranh xử lý một hàng.

Nên thiết kế **state transition rõ ràng**: NEW → CLAIMED → SENT hoặc RECOVERY_PENDING → REPLAYED/RECONCILED. Dùng khóa, unique constraint và transaction của database theo khả năng thực tế.

## 17. Recovery handler cũng có thể lỗi

Đừng giả định error flow luôn thành công. Failure store có thể mất kết nối, DLQ broker có thể quá tải hoặc schema lưu failure bị lỗi.

### 17.1. Quy tắc fail-safe

Nếu recovery chưa ghi bền nhưng recoverer vẫn trả về bình thường, có nguy cơ **ack nguồn trước khi message có bản sao an toàn**. Khi archive lỗi, hệ thống cần một quyết định:

- Propagate exception để upstream rollback/redeliver khi có transaction phù hợp.
- Chuyển sang một kênh lưu bền khác đã thiết kế và kiểm chứng.
- Tạm dừng intake có kiểm soát, cảnh báo và giữ message ở nguồn.

Không nên “catch Exception rồi log” trong recovery handler để bảo vệ throughput bằng mọi giá.

### 17.2. Tránh recursion và error loop

~~~text
Outbound failure -> recoverer -> recoveryChannel
Recovery handler -> failure store timeout
Không được vô hạn:
    retry recovery -> same recoverer -> same channel -> ...
~~~

Recovery path cần có retry policy riêng, giới hạn rõ và **điểm dừng cuối** như alert + giữ nguyên trạng thái nguồn nếu không persist được. Đường retry error flow không nên tự quay lại outbound handler mà không có điều kiện và idempotency.

## 18. Đo lường và quan sát được

Retry exhaustion phải là **sự kiện quan trọng trong reliability observability**, chứ không chỉ là exception stack trace.

### 18.1. Các metric cần có

| Metric | Ý nghĩa |
| --- | --- |
| `adapter_attempts_total` | Tổng số handler attempts |
| `adapter_retry_total` | Số lần thử lại sau lần đầu |
| `adapter_retry_exhausted_total` | Số message hết lượt retry |
| `adapter_recovery_persisted_total` | Số failure record ghi thành công |
| `adapter_recovery_failed_total` | Số lần recovery path lỗi |
| `adapter_dead_letter_depth` | Số record/message đang chờ xử lý |
| `adapter_replay_total` | Số lượt replay |
| `adapter_reconciliation_pending` | Số tác vụ chưa rõ outcome |
| `adapter_end_to_end_latency` | Thời gian từ source tới kết quả cuối |
| `adapter_source_lag` | Độ trễ queue/file/polling source |

Nên nhóm metric theo **adapter, dependency, error category, environment và result**. Không dùng message ID hoặc user ID làm label metric có cardinality cao; đặt correlation ID trong trace/log có phân quyền.

### 18.2. Structured log gợi ý

~~~json
{
  "event": "adapter.retry.exhausted",
  "flow": "sftp-to-partner-http",
  "sourceMessageId": "msg-84021",
  "correlationId": "order-7321",
  "adapter": "partner-http",
  "errorCategory": "TRANSIENT_TIMEOUT",
  "attemptsObserved": 3,
  "recoveryDecision": "PERSIST_FOR_RECONCILIATION",
  "recoveryStatus": "PERSISTED",
  "occurredAt": "2026-11-23T08:00:03Z"
}
~~~

Đây là ví dụ **schema log do ứng dụng định nghĩa**; Spring Integration không tự tạo toàn bộ các field này. Không đưa raw payload chứa PII hoặc Authorization header vào log.

### 18.3. Cảnh báo quan trọng

- Retry exhaustion tăng nhanh so với baseline.
- Failure store/DLQ không nhận message hoặc không có consumer.
- Depth và tuổi lớn nhất của dead-letter tăng liên tục.
- Recovery handler thất bại.
- Downstream không phản hồi nhưng upstream vẫn ack.
- Replay thất bại lặp lại cùng business key.
- Lỗi auth/permission tăng (có thể là cấu hình, không nên retry vô ích).
- Tỷ lệ OUTCOME_UNKNOWN quá cao.

## 19. Kiểm thử: không chỉ kiểm tra số lần gọi

Một bộ test tốt cần chứng minh **đường thành công, lỗi tạm thời, lỗi vĩnh viễn, exhaustion, recovery, ack và replay**.

| Test case | Thiết lập | Kỳ vọng |
| --- | --- | --- |
| Thành công ngay | Call đầu trả thành công | Handler gọi 1 lần, recoverer không chạy |
| Lỗi tạm thời rồi thành công | Hai lần fail, lần 3 success | 3 attempts, không có failure record |
| Hết lượt retry | 3 lần timeout retryable | 3 attempts, recoverer chạy đúng 1 lần |
| Lỗi non-retryable | Validation/auth failure | Không thử lại vô ích, chuyển đường lỗi đúng policy |
| Exception bị wrap | MessagingException chứa cause transient | Policy nhận diện đúng theo cấu hình traverse causes |
| Recovery lưu bền | Store thành công | Có failure envelope đúng correlation, không log secret |
| Recovery store lỗi | Store ném exception | Không âm thầm ack; hành vi nguồn theo contract |
| Handler có side effect | Response lost sau khi server commit | Không tạo duplicate; có idempotency/reconciliation |
| Gateway cần reply | Handler exhausts | Caller nhận lỗi/fallback đúng contract, không treo ngoài dự kiến |
| Broker redelivery | Source rollback/requeue | Đếm tổng attempts đúng qua mọi tầng |
| Replay được duyệt | Sửa lỗi downstream rồi replay | Giữ business key; outcome được đối soát |
| Concurrent duplicates | Hai message cùng business ID | Chỉ một business effect hợp lệ theo thiết kế |

### 19.1. Kiểm tra maxAttempts

Một lỗi phổ biến là test kỳ vọng **4 lần gọi** khi cấu hình **maxAttempts = 3**. Hãy assert số lần handler invocation thực tế và số lần recoverer invocation. Khi exception non-retryable, expected attempts có thể nhỏ hơn 3.

### 19.2. Kiểm tra ack/offset thật

Đừng chỉ mock `RecoveryCallback` rồi kết luận hệ thống không mất message. Cần integration test với source phù hợp (ví dụ test broker hoặc file directory cách ly) để quan sát:

1. Source message được nhận.
2. Handler retry đúng số lần.
3. Recovery record được ghi.
4. Container ack/offset/file state đúng sau recovery.
5. Nếu recovery store lỗi, source message không biến mất mà không có bản ghi bền.

### 19.3. Test theo thời gian

Backoff tạo delay thật. Với unit test, có thể dùng chính sách backoff rất ngắn hoặc cơ chế test clock/backoff của phiên bản thư viện. Với integration test, đo tổng duration và timeout đầu cuối; tránh test quá mong manh dựa trên thời gian chính xác từng mili giây.

## 20. Ví dụ tình huống xuyên suốt: SFTP sang HTTP

Một hệ thống lấy file đơn hàng mỗi phút từ SFTP và gọi HTTP API của nhà vận chuyển.

### 20.1. Thiết kế flow

~~~mermaid
flowchart LR
    S["SFTP inbound + file metadata"] --> P["Parser + schema validation"]
    P --> ID["Business ID / idempotency key"]
    ID --> C["MessageChannel"]
    C --> H["HTTP outbound handler + retry advice"]
    H -->|Thành công| DONE["Record delivered"]
    H -->|Exhaustion| REC["ErrorMessageSendingRecoverer"]
    REC --> ER["Dedicated recovery channel"]
    ER --> STORE["Durable failure store"]
    STORE --> OPS["Reconciliation / replay có kiểm soát"]
~~~

### 20.2. Các trạng thái cho bản ghi

~~~text
NEW
  -> VALIDATED
  -> SENDING
  -> DELIVERED
  -> RETRY_EXHAUSTED
       -> RECOVERY_PERSISTED
       -> OUTCOME_UNKNOWN / REJECTED
       -> RECONCILIATION_REQUIRED
       -> REPLAY_APPROVED
       -> DELIVERED / CLOSED_WITH_REASON
~~~

Không phải mọi record đều đi qua tất cả các trạng thái. Một message validation invalid có thể bị quarantine **trước handler retry**. Một HTTP timeout cần điều tra outcome trước khi replay, trong khi lỗi reject rõ ràng có thể được đóng theo quy tắc nghiệp vụ.

### 20.3. Ba kịch bản

**Kịch bản A — Đối tác hồi phục:** HTTP timeout lần 1 và 2, thành công lần 3. Không tạo failure envelope, ghi thành công, bảo đảm API idempotency theo contract.

**Kịch bản B — Retry exhausted:** Cả 3 attempts timeout; recoverer xuất ErrorMessage; error flow ghi failure bền vững; owner được cảnh báo khi backlog vượt ngưỡng. Nghiệp vụ ở trạng thái cần đối soát, không tự coi đã gửi thất bại vĩnh viễn.

**Kịch bản C — Failure store cũng lỗi:** Nếu recoverer không persist được, flow phải thực hiện chính sách ném lỗi/rollback hoặc giữ trạng thái source theo thiết kế. Không chuyển file sang thư mục DONE và không ack nguồn nếu làm vậy sẽ mất khả năng xử lý lại.

### 20.4. Correlation từ file tới request

Một bản ghi có thể mang:

~~~yaml
# Metadata minh họa cho integration contract
source:
  protocol: sftp
  fileId: file-20261123-17
  recordNumber: 42
message:
  messageId: msg-84021
  correlationId: order-7321
  businessOperation: create-shipment
  idempotencyKey: ship-tenant-a-order-7321
destination:
  protocol: https
  partner: logistics-service
failurePolicy:
  maxAttempts: 3
  onExhausted: persist-and-reconcile
~~~

Schema này là yêu cầu nghiệp vụ, không phải các headers được Spring Integration tự tạo. Phải xác định cách map trường vào `MessageHeaders` và failure store. Không sử dụng tên file duy nhất làm khóa chống trùng khi một file có nhiều record.

## 21. Runbook khi retry exhaustion tăng đột biến

### 21.1. Triage ban đầu

1. Xác định luồng nào bị ảnh hưởng: nguồn, destination, endpoint, môi trường.
2. Phân loại lỗi: timeout, 429/503, auth, validation, network hay database.
3. Kiểm tra số handler attempts, lỗi cuối, log/traces và thời điểm bắt đầu.
4. Kiểm tra downstream health, rate limit, dependency incident và credential expiry.
5. Xác nhận recovery store/DLQ còn hoạt động, không mất message.
6. Kiểm tra ack/commit, depth/lag ở nguồn và các chiến lược redelivery.

### 21.2. Khắc phục

- Với transient outage: giảm concurrency/điều chỉnh backoff, cân nhắc circuit breaker, không tăng retry vô hạn.
- Với auth/config: sửa credential hoặc quyền theo change control; không retry 401/403 liên tục.
- Với validation: sửa contract/parser hoặc quarantine message; không tự chỉnh dữ liệu nhạy cảm mà không có approval.
- Với outcome unknown: đối soát downstream trước replay.
- Với backlog: xử lý theo thứ tự ưu tiên và giới hạn rate để không gây sự cố lặp.

### 21.3. Đóng sự cố

Chỉ đóng khi có bằng chứng:

- Downstream đã hồi phục hoặc lỗi được khắc phục.
- Failure records đã được đối soát, replay/đóng hợp lệ theo chính sách.
- Không còn message không rõ trạng thái bị bỏ sót.
- Ack, offset hoặc file state nhất quán với recovery store.
- Số lượng retry exhaustion trở về mức chấp nhận.
- Nguyên nhân, thay đổi cấu hình và bài kiểm thử phòng tránh tái diễn đã được ghi.

## 22. Những anti-pattern cần tránh

| Anti-pattern | Hậu quả | Hướng sửa |
| --- | --- | --- |
| Retry tất cả exceptions | Lặp lỗi schema/auth vô ích | Phân loại retryable và non-retryable |
| Nhầm maxAttempts=3 là 3 retry sau lần đầu | Dự báo sai tải và latency | Tính cả attempt đầu |
| Recoverer chỉ ghi log rồi return | Message có thể ack mà không có bản sao xử lý tiếp | Persist bền hoặc propagate phù hợp |
| Dùng DirectChannel như DLQ bền vững | Mất trạng thái khi process dừng | Durable broker/store và xác minh publish |
| Retry non-idempotent POST không có khóa | Tạo trùng đơn hàng/giao dịch | Idempotency key + reconciliation |
| Callback gửi lại API lần thứ tư không kiểm soát | Tăng side effects ngoài retry policy | Recovery terminal rõ ràng |
| Quá nhiều tầng retry | Retry storm và nhân số attempts | Budget tổng xuyên SDK/handler/container/broker |
| Retry lâu hơn gateway timeout | Caller timeout trước khi recoverer xử lý | Căn chỉnh latency budget |
| Không kiểm thử recovery handler fail | Có thể ack nguồn sau khi persist lỗi | Test rollback/nack/retention |
| Mọi lỗi đổ về global errorChannel | Khó phân biệt owner và retry exhaustion | Dedicated recovery route theo flow |
| Quên async boundary | Lỗi xảy ra ngoài advice | Gắn retry đúng handler/thread boundary |
| Nhầm ErrorMessage với business success | Caller/monitoring ghi nhận sai | Trạng thái terminal và error contract riêng |
| Mặc định Kafka offset/JMS ack theo suy đoán | Mất hoặc nhân đôi message | Integration test theo source |
| Replay dùng message ID mới làm idempotency key | Mất chống trùng xuyên các lần retry | Giữ ổn định business operation key |
| Lưu raw payload/Authorization vào DLQ/log | Rò rỉ thông tin nhạy cảm | Redaction, encryption, access control |
| Retry exhaustion không có owner | DLQ tăng mãi không ai xử lý | Alert, SLA, retention, runbook |

## 23. Câu hỏi tự kiểm tra

### Câu 1. maxAttempts bằng 3 nghĩa là gì?

**Đáp án:** Thông thường là tối đa **ba lần thực thi handler**, gồm lần đầu và hai lượt retry, nếu policy xem exception có thể retry. Non-retryable failure có thể đi sang recovery sớm hơn.

### Câu 2. ErrorMessageSendingRecoverer có tự tạo dead-letter queue không?

**Đáp án:** Không. Nó gửi `ErrorMessage` vào channel được chỉ định. Error flow phía sau phải chịu trách nhiệm lưu bền, phát DLQ hoặc xử lý theo chính sách; cần kiểm tra behavior khi chính error flow lỗi.

### Câu 3. Sau retry exhaustion, có nên luôn return null không?

**Đáp án:** Không. Return bình thường có thể khiến upstream xem handler đã hoàn tất; với gateway có thể làm thiếu reply; với broker có thể ảnh hưởng ack/commit. Cần chọn rõ propagate, persist-and-ack hoặc fallback có hợp đồng.

### Câu 4. HTTP timeout có chứng minh downstream chưa tạo đơn hàng?

**Đáp án:** Không. Server có thể đã commit mà response bị mất. Dùng idempotency key và cơ chế đối soát trạng thái trước khi replay.

### Câu 5. RequestHandlerRetryAdvice có retry lỗi parser ở bước trước không?

**Đáp án:** Không mặc định. Advice được gắn vào **handler cụ thể**; lỗi ở thành phần ngoài phạm vi handler cần error/retry strategy riêng.

### Câu 6. Tại sao retry của broker và handler có thể nguy hiểm?

**Đáp án:** Mỗi broker delivery có thể tạo một vòng handler retry mới, làm tổng số attempts tăng theo cấp số nhân của các tầng và tăng side effects. Cần quy định retry budget tổng và điểm DLQ terminal.

### Câu 7. Recovery persisted có nghĩa message được deliver chưa?

**Đáp án:** Chưa. Nó chỉ nói failure đã được lưu để xử lý sau. Nghiệp vụ cần được replay/đối soát và có bằng chứng thực hiện thành công.

### Câu 8. Khi nào non-retryable exception vẫn đi qua recoverer?

**Đáp án:** Khi retry policy xác định không nên retry và đã có recovery callback tương ứng; có thể recovery sau một attempt mà không tiêu hết maxAttempts. Cần kiểm tra chính sách cụ thể và test.

## 24. Checklist triển khai recoverer an toàn

1. **Đúng điểm gắn advice:** Chỉ retry handler/outbound endpoint thực sự cần; xác định synchronous/asynchronous boundary.
2. **Đúng phân loại lỗi:** Retry transient, không lặp vô nghĩa validation, auth hoặc conflict.
3. **Đúng số lượt:** maxAttempts tính cả lần đầu; tính cả retry ở SDK/container/broker.
4. **Đúng timeout:** Tổng attempts + backoff phù hợp request SLA và thread budget.
5. **Backoff hợp lý:** Tránh retry storm, dùng jitter/rate limit nếu cần.
6. **Recovery rõ:** Chọn propagate, durable store/DLQ hoặc fallback có contract.
7. **Error channel có consumer:** Recovery channel không được thành sink không kiểm soát.
8. **Durability được xác minh:** ErrorMessage gửi thành công chưa đủ; failure record phải lưu bền.
9. **Ack/commit được test:** Không suy đoán behavior của JMS, AMQP, Kafka hoặc poller.
10. **Idempotency:** Giữ business key qua retry, broker redelivery và replay.
11. **Outcome unknown:** Có reconciliation khi downstream có thể đã xử lý trước timeout.
12. **Lỗi của recovery path:** Có fail-safe, escalation và không tạo vòng lặp retry vô hạn.
13. **Observability:** Đếm exhaustion, recovery success/failure, backlog, lag, replay và latency.
14. **Audit:** Ghi correlation ID, attempts thực tế, error category, owner và quyết định.
15. **Security:** Redact secrets/PII, mã hóa payload lưu bền và giới hạn quyền DLQ.
16. **Replay có kiểm soát:** Có owner, approval khi cần, backpressure và tránh duplicate.
17. **Test thực tế:** Success, transient recovery, exhausted, non-retryable, archive failure, broker ack và gateway reply.
18. **Runbook:** Có hướng dẫn triage, quyết định retry/replay và điều kiện đóng incident.

## 25. Tổng kết

**Recoverer sau khi retry hết lượt** là cơ chế đưa message từ vòng thử lại hữu hạn sang một **quyết định xử lý cuối**. Với Spring Integration, `RequestHandlerRetryAdvice` kết hợp `RetryTemplate` để thử lại handler; `RecoveryCallback` quyết định bước tiếp theo, còn `ErrorMessageSendingRecoverer` là một lựa chọn chuyển lỗi sang `MessageChannel` dành cho xử lý tiếp.

Reliability không đến từ số lần retry lớn, mà từ **phân loại lỗi chính xác, timeout/backoff hợp lý, không tạo side effect trùng, recovery bền vững, ack/transaction nhất quán và replay có kiểm soát**. Khi triển khai adapter File/SFTP, HTTP, JMS, AMQP, Kafka hoặc JDBC, phải xác minh chính xác điểm phát lỗi và semantics của nguồn. Một message được xem là xử lý an toàn sau exhaustion khi **đã có failure record bền vững hoặc upstream vẫn giữ trách nhiệm delivery**, mọi outcome chưa rõ được đối soát, và kết quả cuối có thể được theo dõi, kiểm thử và kiểm toán.
