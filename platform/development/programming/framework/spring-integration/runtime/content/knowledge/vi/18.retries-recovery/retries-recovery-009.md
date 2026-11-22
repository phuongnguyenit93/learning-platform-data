# Tránh retry lồng nhiều tầng trong Spring Integration Runtime

## Mục tiêu bài học

Trong **Spring Integration Runtime**, một message có thể đi qua gateway, channel, service activator, poller, executor, adapter và hệ thống bên ngoài. Nhiều thành phần trong chuỗi đó có thể tự retry: HTTP client, **RequestHandlerRetryAdvice**, transaction interceptor, polling consumer, broker redelivery hoặc ứng dụng gọi ở phía trước.

Vấn đề xuất hiện khi mỗi tầng được cấu hình độc lập và cùng cố gắng “cứu” một lỗi. Một yêu cầu có thể bị thực thi hàng chục lần, vượt quá thời gian chờ, làm nghẽn thread pool hoặc lặp lại side effect nghiệp vụ.

Sau bài này, bạn có thể:

- Nhận biết các **tầng retry** và vẽ lại ranh giới thực thi của một message.
- Tính mức khuếch đại số attempt, tổng độ trễ và lượng tải khi retry lồng.
- Chọn **retry owner** phù hợp cho từng ranh giới, đặt giới hạn số lần thử và thời gian.
- Phân biệt **retry nội bộ**, **broker redelivery**, **transaction rollback** và **recovery sau khi cạn retry**.
- Thiết kế idempotency, correlation, error channel, message store và DLQ để không nhân đôi tác dụng.
- Kiểm chứng hành vi khi gặp timeout, lỗi dữ liệu, quá tải executor, mất kết nối và restart flow.

> **Nguyên tắc:** Mỗi thao tác nghiệp vụ nên có một **chính sách retry đầu-cuối được nhìn thấy rõ**, bao gồm ai sở hữu retry, điều kiện nào được retry, giới hạn bao nhiêu lần, khi hết retry sẽ đi đâu và làm thế nào nhận diện cùng một yêu cầu qua các attempt.

## 1. Retry lồng nhiều tầng là gì?

Giả sử một flow thanh toán có cấu trúc:

~~~mermaid
flowchart LR
    G["HTTP gateway<br/>caller retry"] --> C["Spring Integration channel"]
    C --> P["Poller/broker consumer<br/>redelivery"]
    P --> A["Service activator<br/>RetryAdvice"]
    A --> H["HTTP client<br/>transport retry"]
    H --> S["Payment service"]
~~~

Mỗi thành phần có thể tự thử lại khi không nhận được kết quả mong đợi:

| Tầng | Cơ chế ví dụ | Đơn vị được thực thi lại |
| --- | --- | --- |
| Caller/gateway phía trước | HTTP request retry, scheduler phát lại job | Có thể gửi lại **toàn bộ lệnh nghiệp vụ** |
| Broker/adapter | Nack, rollback, redelivery, restart consumer | **Message giao vận** được giao lại |
| Poller/transaction | Poll thất bại, nguồn vẫn giữ message hoặc transaction rollback | Có thể lấy lại message ở lần poll sau |
| Spring Integration endpoint | **RequestHandlerRetryAdvice** gọi lại handler | Một lời gọi **handle message** |
| HTTP/DB client | Retry kết nối, timeout, lệnh SQL hoặc request HTTP | Một **lời gọi phụ thuộc** |
| Recovery scheduler | Replay từ DLQ/quarantine sau một khoảng thời gian | Một **lần xử lý mới**, có thể sau nhiều giờ |

Không phải mọi tầng luôn có retry mặc định. Những dòng trên là **vị trí cần kiểm tra cấu hình thực tế**, không phải khẳng định framework luôn bật tất cả.

### Cấp số nhân số attempt

Nếu một message được broker giao tối đa **4 lần**, mỗi lần handler thử tối đa **3 lần**, còn HTTP client thử tối đa **2 lần** cho mỗi lần gọi, thì trong tình huống tất cả các lần đều thất bại:

\[
N_{\mathrm{HTTP,max}} = 4 \times 3 \times 2 = 24
\]

**Một yêu cầu nghiệp vụ** có thể tạo tới **24 lần gọi payment service**. Nếu caller còn retry toàn bộ yêu cầu 2 lần thì mức tối đa lý thuyết thành 48. Đây là **giới hạn trên** trong mô hình mọi tầng thực sự chạy đủ lượt; lỗi được xử lý thành công sớm hơn hoặc những tầng không tham gia sẽ cho số attempt nhỏ hơn.

Trong thực tế, retry lồng còn nguy hiểm hơn phép nhân đơn thuần:

- Timeout tầng ngoài có thể xảy ra khi tầng trong **vẫn đang chạy**, khiến các lần xử lý chồng lấn.
- Một API trả timeout **không chứng minh** side effect đã thất bại; bên nhận có thể đã commit.
- Mỗi lần retry có thể tạo thêm thread chờ, kết nối, log, tracing span và lock.
- Khi downstream đang quá tải, các lần retry đồng loạt tạo **retry storm**, làm tình trạng tệ hơn.

### Ba khái niệm cần tách riêng

- **Attempt**: một lần thực thi cụ thể, ví dụ một lần gọi charge.
- **Delivery**: một lần broker/poller đưa message cho consumer; một delivery có thể chứa nhiều attempt.
- **Business operation**: hành động nghiệp vụ duy nhất, ví dụ thanh toán yêu cầu **paymentId=PAY-42**; mọi attempt/delivery của nó phải được liên kết với cùng khóa nghiệp vụ.

Không dùng số lần gọi handler làm số giao dịch thành công. **at-least-once delivery** và retry không tự tạo ra **exactly-once side effect**.

## 2. Nhận diện các tầng retry trong message flow

Khi chẩn đoán một flow, cần lần theo chính xác đường đi:

~~~text
External producer
  └─ inbound adapter / gateway
       └─ input channel
            └─ poller hoặc dispatcher
                 └─ handler advice chain
                      └─ service / repository
                           └─ external HTTP/DB client
  └─ error flow / recovery / broker redelivery
~~~

Với mỗi điểm, hãy ghi lại **attempt limit**, **backoff**, **timeout**, **transaction boundary** và **ai quyết định message đã thành công**. Một ứng dụng có thể có retry ở thư viện bên dưới mà bạn không khai báo trực tiếp trong IntegrationFlow.

### DirectChannel và ExecutorChannel

**DirectChannel** gọi consumer trên thread của sender. Nếu handler ném exception, lỗi có thể truyền ngược về sender; một caller retry toàn bộ send sẽ thực thi lại cả chuỗi đồng bộ. Khi đặt **RequestHandlerRetryAdvice** quanh handler, một lần send còn có thể gọi handler nhiều lần.

**ExecutorChannel** đưa việc xử lý sang thread của executor. Send phía producer có thể kết thúc trước khi handler lỗi. Transaction hoặc retry ở thread gửi **không mặc định bao trùm** xử lý bên consumer. Một retry ở producer có thể gửi **message mới** trong khi lần gửi trước còn đang thực thi ở worker.

### Poller và broker

Poller quyết định thời điểm lấy message từ nguồn. Bản thân việc poll theo chu kỳ **không đồng nghĩa** mỗi message lỗi sẽ tự được phát lại: kết quả phụ thuộc loại nguồn, transaction, ack và cấu hình error flow. Với broker, redelivery có thể phát sinh từ rollback/nack, visibility timeout, reset offset hoặc restart.

Nếu handler đã retry ba lần rồi ném exception, broker **có thể** giao lại message từ đầu theo chính sách của nguồn. Nếu handler recovery bằng cách bắt lỗi và kết thúc bình thường, broker **có thể** coi delivery đã xử lý thành công. Phải kiểm tra đúng hợp đồng adapter/ack; không suy luận từ tên errorChannel.

## 3. Các hậu quả khó thấy của retry lồng

### 3.1. Vượt tổng thời gian chờ

Giả sử mỗi HTTP call timeout sau **2 giây**. Với ba attempt ở handler và hai attempt trong HTTP client, chỉ riêng thời gian chờ network đã có thể gần **12 giây** cho một delivery, chưa tính backoff, serialization, DB và chi phí thread. Nếu gateway chỉ cho phép **5 giây**, caller có thể bỏ cuộc và retry, còn handler cũ vẫn chạy.

Đặt **deadline đầu-cuối** cho yêu cầu. Mỗi tầng con phải dùng ngân sách còn lại thay vì khởi tạo timeout mới không giới hạn. Nếu hết ngân sách, không nên tiếp tục khởi chạy side effect mới trừ khi có cơ chế xử lý bất đồng bộ được thiết kế riêng.

### 3.2. Duplicate side effect

~~~text
T1: handler gọi payment provider bằng paymentId=PAY-42.
T2: provider xử lý thành công nhưng response bị mất.
T3: HTTP client timeout và retry.
T4: RetryAdvice tiếp tục thử lại cả handler.
T5: Broker redeliver message khi transaction thất bại.
~~~

Nếu provider không hỗ trợ idempotency key và ứng dụng không có đối soát, một lệnh có thể bị thu tiền nhiều lần. **Rollback transaction DB nội bộ không rollback được** một lời gọi HTTP đã hoàn tất ở hệ thống ngoài.

### 3.3. Khuếch đại tải và nghẽn runtime

Retry có backoff đồng bộ có thể giữ thread xử lý đang chờ; poller hoặc executor ít thread dễ bị chiếm hết. Khi nhiều message cùng lỗi, queue tăng, latency tăng và timeout mới kích hoạt thêm retry. Tăng số thread lúc này có thể chỉ làm nguồn lỗi chịu nhiều request hơn.

### 3.4. Làm mờ trách nhiệm vận hành

Các log như “retry attempt 3/3”, “delivery count 2”, “HTTP retry 2” có thể nói về **ba bộ đếm khác nhau**. Nếu không gắn **businessId/requestId/correlationId** với toàn bộ attempt, người vận hành rất khó trả lời một lệnh thực sự đã được gửi bao nhiêu lần.

## 4. Chọn một retry owner cho từng ranh giới

**Retry owner** là tầng quyết định có nên thực hiện lại **toàn bộ thao tác được bảo vệ** hay không. Nên xác định theo phạm vi nhất quán của state, vị trí transaction, loại lỗi và chi phí side effect.

| Tình huống | Retry owner thường phù hợp | Vì sao |
| --- | --- | --- |
| Lỗi tạm thời khi gọi dịch vụ ngoài, handler stateless | Retry advice quanh handler **hoặc** client retry có giới hạn | Tránh cả hai cùng retry theo mặc định |
| Đọc message từ broker với transaction/ack riêng | Cơ chế consumer/broker redelivery có giới hạn, có DLQ | Nguồn kiểm soát delivery; cần tránh retry vô hạn |
| Transaction DB bị deadlock/serialization conflict | Retry bao trùm **transaction mới** | Một lần retry cần trạng thái transaction sạch |
| JSON hỏng, thiếu trường bắt buộc | Không retry nóng; quarantine/DLQ | Lặp lại cùng payload thường không thay đổi kết quả |
| Chờ dịch vụ được phục hồi sau sự cố dài | Durable delayed retry / scheduler / DLQ replay | Không chiếm thread hoặc giữ transaction hàng giờ |
| Side effect đã có kết quả không chắc chắn | Đối soát theo idempotency key trước khi retry | Timeout không chứng minh thao tác thất bại |

Chọn một owner **không bắt buộc cấm mọi retry ở tầng dưới**. Ví dụ client có thể retry kết nối an toàn một lần trong ngân sách đã thống nhất. Nhưng số lượt **tổng**, thời gian và điều kiện retry phải được tính chung; không cấu hình các tầng độc lập rồi cộng dồn một cách vô thức.

### Mô hình quyết định cho từng lỗi

~~~mermaid
flowchart TD
    F["Bắt được exception"] --> C{"Lỗi có thể phục hồi<br/>nếu thử lại?"}
    C -- "Không" --> Q["Ghi nhận và quarantine / business failure"]
    C -- "Có" --> U{"Side effect đã có<br/>kết quả chắc chắn?"}
    U -- "Không rõ" --> I["Tra cứu / đối soát theo idempotency key"]
    I --> U2{"Có bằng chứng chưa hoàn tất?"}
    U2 -- "Không" --> M["Giữ trạng thái chờ điều tra<br/>hoặc phục hồi có kiểm soát"]
    U2 -- "Có" --> B{"Còn ngân sách attempt<br/>và deadline?"}
    U -- "Chưa thực hiện hoặc an toàn để gọi lại" --> B
    B -- "Có" --> R["Retry tại owner đã chọn"]
    B -- "Không" --> E["Recovery: DLQ / journal / cảnh báo"]
~~~

Trạng thái **unknown outcome** cần được mô hình hóa thật. Trả về “failed” ngay sau HTTP timeout mà không kiểm tra phía cung cấp có thể dẫn tới việc người dùng thử lại một giao dịch đã thành công.

## 5. Ví dụ cấu hình RequestHandlerRetryAdvice có phạm vi rõ

Ví dụ sau minh họa **một retry owner tại service activator** khi downstream có lỗi tạm thời. Giả sử HTTP client bên dưới đã được cấu hình để không tự lặp lại cùng lệnh nghiệp vụ, và ingress không thêm vòng retry nóng độc lập.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.handler.advice.RequestHandlerRetryAdvice;
import org.springframework.retry.backoff.ExponentialBackOffPolicy;
import org.springframework.retry.policy.SimpleRetryPolicy;
import org.springframework.retry.support.RetryTemplate;

@Configuration
class PaymentRetryConfiguration {

    @Bean("paymentRetryAdvice")
    RequestHandlerRetryAdvice paymentRetryAdvice() {
        // maxAttempts = 3: gồm lần thử đầu tiên và tối đa 2 lần retry.
        SimpleRetryPolicy policy = new SimpleRetryPolicy(3);

        ExponentialBackOffPolicy backoff = new ExponentialBackOffPolicy();
        backoff.setInitialInterval(200L);
        backoff.setMultiplier(2.0);
        backoff.setMaxInterval(800L);

        RetryTemplate template = new RetryTemplate();
        template.setRetryPolicy(policy);
        template.setBackOffPolicy(backoff);

        RequestHandlerRetryAdvice advice = new RequestHandlerRetryAdvice();
        advice.setRetryTemplate(template);
        return advice;
    }
}
~~~

Áp dụng advice cho endpoint bằng tên bean:

~~~java
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.messaging.Message;
import org.springframework.stereotype.Component;

record PaymentCommand(String paymentId, long amount) {}

interface PaymentGateway {
    // Provider phải áp dụng idempotencyKey cho thao tác thanh toán.
    void charge(PaymentCommand command, String idempotencyKey);
}

@Component
class PaymentHandler {
    private final PaymentGateway gateway;

    PaymentHandler(PaymentGateway gateway) {
        this.gateway = gateway;
    }

    @ServiceActivator(
            inputChannel = "paymentCommands",
            adviceChain = "paymentRetryAdvice")
    public void handle(Message<PaymentCommand> message) {
        String idempotencyKey =
                (String) message.getHeaders().get("idempotencyKey");
        if (idempotencyKey == null || idempotencyKey.isBlank()) {
            throw new IllegalArgumentException("Missing idempotencyKey");
        }

        gateway.charge(message.getPayload(), idempotencyKey);
    }
}
~~~

**Giải thích và giới hạn của ví dụ:**

1. Retry ở đây bao quanh **lời gọi handler**, không tự động bao quanh producer, broker redelivery hay tất cả endpoint khác.
2. **SimpleRetryPolicy(3)** minh họa số lần thử nhưng chính sách mặc định quá rộng cho production: cần giới hạn theo **exception retryable**, xem xét cause chain và tránh retry lỗi validation/authorization vĩnh viễn.
3. Với hai lần backoff **200 ms rồi 400 ms**, phần chờ lý thuyết khoảng **600 ms** nếu cả ba attempt đều được thực hiện; thời gian thực tế còn cộng thời gian xử lý, timeout và scheduler.
4. Không có recovery callback ở cấu hình minh họa: khi cạn retry, exception thường được ném ra cho luồng xử lý lỗi tương ứng. Muốn xử lý cuối cùng phải cấu hình error flow/transaction và hành vi ack phù hợp.
5. **idempotencyKey** phải được giữ nguyên giữa mọi attempt, broker redelivery và replay. Chỉ truyền key tới provider chưa đủ nếu provider không có bảo đảm idempotency hoặc yêu cầu hết hiệu lực theo thời gian.
6. Trong triển khai thực, **đừng retry ngay khi timeout chưa rõ kết quả** mà chưa áp dụng kiểm soát duplicate/đối soát. Có thể phải tách bước tra cứu trạng thái khỏi lệnh charge.

### Khi transaction và retry cùng bao quanh handler

Thứ tự các advice làm thay đổi semantics. Nếu retry chạy **bên trong cùng một transaction** đã bị đánh dấu rollback-only sau lỗi đầu tiên, attempt tiếp theo có thể tiếp tục trong transaction không còn hợp lệ. Thường cần để **mỗi attempt có transaction mới** ở phạm vi công việc cần atomic; đối với nguồn broker, việc rollback/ack lại phụ thuộc consumer container và quản lý transaction.

Ví dụ ý tưởng:

~~~text
Retry (3 attempts)
  ├─ Transaction 1 → handler → rollback
  ├─ Transaction 2 → handler → rollback
  └─ Transaction 3 → handler → commit hoặc lỗi cuối
~~~

Thứ tự thực tế của advice/proxy và transaction manager phải được xác minh bằng integration test, không kết luận chỉ từ thứ tự viết annotation. Và dù DB rollback, HTTP call tới hệ thống ngoài có thể đã thành công.

## 6. Recovery sau khi cạn retry: đừng tạo một vòng retry vô hạn khác

Một chính sách đầy đủ phải trả lời: **Sau attempt cuối cùng, message sẽ ở đâu?**

Trong Spring Integration, **RequestHandlerRetryAdvice** có thể kết hợp recovery callback, chẳng hạn cơ chế dựa trên **ErrorMessageSendingRecoverer** để phát thông báo lỗi. Error flow có thể ghi **FailureJournal**, chuyển quarantine/DLQ hoặc kích hoạt cảnh báo. **Điểm cần kiểm tra:** Recovery tiêu thụ exception có thể khiến tầng bên ngoài coi xử lý là hoàn tất; broker có redeliver hay không phụ thuộc adapter, ack và transaction.

~~~mermaid
flowchart LR
    IN["Message nhận"] --> RP["Retry owner<br/>tối đa 3 attempts"]
    RP -- "Thành công" --> OK["Ghi nhận COMPLETED"]
    RP -- "Hết retry" --> REC["Recovery"]
    REC --> FJ[("FailureJournal / DLQ")]
    FJ --> OBS["Cảnh báo + tra cứu trạng thái"]
    FJ -. "Replay có điều kiện<br/>sau khi xử lý nguyên nhân" .-> IN
~~~

Các lựa chọn recovery thường dùng:

- **Ném lại exception** để transaction rollback hoặc nguồn quyết định redelivery, nếu đó là chủ đích và có giới hạn delivery.
- **Chuyển DLQ/quarantine** khi payload không thể xử lý hoặc đã hết ngân sách; lưu payload/tham chiếu an toàn, reason, time và correlation.
- **Ghi FailureJournal** và đánh dấu nghiệp vụ FAILED/UNKNOWN, có đối soát và quy trình phục hồi.
- **Delayed retry bền vững** cho lỗi tạm thời kéo dài, bằng job/broker delay với số lần phát lại và thời gian sống tối đa; không giữ thread chờ hàng giờ.

Nếu recovery handler chỉ log rồi trả về, message có thể bị xem là thành công về mặt delivery dù tác vụ nghiệp vụ chưa xong. Nếu recovery tự phát lại liên tục mà không ghi số lần retry tổng, nó có thể tạo **vòng lặp vô hạn qua DLQ**.

### Không phải mọi ErrorMessage đều là một phép retry

**ErrorMessage** mang lỗi được publish bởi thành phần hỗ trợ error flow; gửi ErrorMessage không tự động đưa original message trở lại input channel. **errorChannel** chỉ là đường định tuyến thông báo lỗi; retry, replay và ack phải được thiết kế riêng.

Khi lỗi xuất hiện sau **ExecutorChannel**, producer có thể đã trả về thành công. Cần quan sát exception ở thread xử lý và error flow của nó. Retry ở HTTP caller bên ngoài có thể gửi lại toàn bộ yêu cầu khi attempt cũ vẫn còn in-flight.

## 7. Idempotency, correlation và deduplication qua mọi attempt

Điều kiện quan trọng nhất khi có retry là **lặp lại xử lý không tạo lặp lại tác dụng nghiệp vụ**. Có thể đạt được ở nhiều mức tùy hệ thống:

| Dữ liệu/khóa | Dùng để làm gì? | Không nên dùng để làm gì? |
| --- | --- | --- |
| **paymentId / operationId** | Định danh một thao tác nghiệp vụ duy nhất | Thay đổi mỗi attempt |
| **idempotencyKey** | Cho phép phía nhận nhận biết nhiều attempt của cùng thao tác | Dùng chung cho hai nghiệp vụ khác nhau |
| **correlationId** | Gắn các message, lỗi và event của cùng hành trình | Giả định luôn duy nhất cho từng side effect |
| **Spring MessageHeaders.ID** | Định danh một Spring Message kỹ thuật | Khóa chống lặp qua restart/broker/rebuild message |
| **deliveryAttempt / retryCount** | Phân tích số lần một tầng đã thử | Đại diện cho tổng số attempt ở mọi tầng |
| **traceId/spanId** | Quan sát đường thực thi; span có thể thay đổi | Thay thế business key hoặc idempotency key |

Một ví dụ kết hợp:

~~~text
paymentId=PAY-42
idempotencyKey=charge:PAY-42
correlationId=checkout-42
brokerDelivery=3
handlerAttempt=2
httpAttempt=1
~~~

Nếu một message được redeliver, nên **giữ paymentId/idempotencyKey/correlationId**. Có thể tạo executionId hoặc trace span mới cho lần chạy để phân biệt retry. Không sử dụng delivery count làm khóa nghiệp vụ vì mỗi lần phát lại có thể thay đổi.

### Kiểm soát duplicate ở nơi lưu trạng thái

Các thao tác chỉ trong một JVM (AtomicInteger, synchronized, ConcurrentHashMap) không bảo vệ được nhiều instance hoặc restart. Với DB, thường dùng **unique constraint** trên operationId, trạng thái xử lý và transaction để ngăn hai consumer đồng thời cùng commit một trạng thái.

Một mô hình trạng thái có thể là:

~~~text
RECEIVED → PROCESSING → COMPLETED
                      → FAILED_RETRYABLE → SCHEDULED
                      → QUARANTINED
                      → UNKNOWN_OUTCOME → RECONCILING
~~~

Với side effect nằm ở hệ thống ngoài, unique constraint ở DB **không tạo transaction phân tán** cùng HTTP provider. Muốn tránh gửi lặp, có thể dùng **idempotency key do provider thực thi**, transactional outbox/inbox, truy vấn trạng thái theo operationId, hoặc quy trình đối soát/bù trừ. Phải xử lý cả trường hợp tiến trình chết giữa lúc gọi provider và lúc ghi COMPLETED.

## 8. Giới hạn tổng số attempt, backoff và deadline

Một policy thực tế cần có **budget được chia sẻ** hoặc ít nhất quy tắc phối hợp giữa các tầng:

- **maxAttempts**: tính cả lần đầu, ví dụ 3 attempts nghĩa là tối đa 2 retries.
- **maxElapsedTime/deadline**: tổng thời gian nghiệp vụ được phép chờ; mỗi lời gọi con phải tôn trọng thời gian còn lại.
- **Retryable exceptions**: timeout kết nối, quá tải tạm thời, HTTP 429/503 nếu giao thức và idempotency cho phép; tránh retry dữ liệu sai, auth fail hoặc lỗi không thể tự hồi phục.
- **Backoff + jitter**: giảm đồng bộ hóa retry của nhiều message cùng lỗi; đặt trần và chú ý giới hạn throughput.
- **Rate limit, bulkhead, circuit breaker**: giới hạn tải lên downstream khi lỗi lan rộng; không biến circuit-breaker rejection thành một vòng retry mới.
- **Per-operation attempt counter**: nếu có delayed retry và broker redelivery, lưu số lần phát lại tổng bằng state bền vững; đừng chỉ phụ thuộc bộ đếm trong một bean mới tạo sau restart.

Để định lượng, nếu retry bên trong có tối đa 3 attempts, request timeout mỗi lần 2 giây và backoff 0,2 + 0,4 giây, **một delivery** có thể mất gần **6,6 giây** trước overhead. Nếu broker giao lại 4 lần, tổng thời gian xử lý tuần tự có thể gần **26,4 giây** cộng thêm backoff ở broker. Caller có deadline 5 giây sẽ không thể chờ được toàn bộ vòng này.

**Công thức đơn giản** khi các attempt chạy tuần tự:

\[
T_{\mathrm{upper}} \approx
N_{\mathrm{outer}}\left(
N_{\mathrm{inner}}\,T_{\mathrm{attempt}} +
\sum T_{\mathrm{inner\ backoff}}
\right) + \sum T_{\mathrm{outer\ backoff}}
\]

Trong thực tế còn có queue latency, transaction, serializer, GC và các attempt **chồng lấn** do timeout của tầng ngoài. Vì vậy đây là phép ước tính ngân sách, không phải bảo đảm về thời gian tối đa.

## 9. Tình huống thực hành: sửa flow có ba vòng retry

Hệ thống nhận message thanh toán từ broker:

~~~text
Broker consumer: redelivery tối đa 4 deliveries
  └─ DirectChannel
       └─ service activator + RequestHandlerRetryAdvice(3 attempts)
            └─ HTTP client retry(2 attempts)
                 └─ payment provider
~~~

Triệu chứng:

- Một lệnh thanh toán đôi lúc tạo 24 HTTP calls khi provider chậm hoặc lỗi.
- Thread pool tại consumer bị giữ lâu, backlog broker tăng.
- Có trường hợp provider đã xử lý nhưng caller thấy timeout.
- Sau restart, message bị giao lại nhưng log không có chung operationId.

### Các bước xử lý

**Bước 1 — Đo trước khi sửa.** Thu thập logs, traces và cấu hình thực tế để xác định tầng nào retry. Ghi operationId, broker delivery ID/count, handler attempt, HTTP attempt, exception và thời gian mỗi lần gọi. Đối chiếu provider theo idempotency key để biết side effect nào đã xảy ra.

**Bước 2 — Chọn retry owner.** Ví dụ chọn **handler retry** cho lỗi HTTP ngắn hạn: giới hạn tối đa ba attempts, deadline rõ, client không tự retry charge, broker chỉ redeliver khi transaction thất bại ngoài phạm vi đã xử lý hoặc theo chính sách recovery được phối hợp. Không để broker chạy vòng redelivery nóng độc lập sau khi app đã quyết định chuyển DLQ.

**Bước 3 — Phân loại lỗi.** JSON sai và lỗi validation chuyển quarantine ngay. Timeout có kết quả chưa rõ chuyển đối soát hoặc gọi lại bằng **cùng idempotency key** nếu provider hỗ trợ. HTTP 429/503 có thể retry với backoff/jitter trong budget.

**Bước 4 — Quyết định sau cạn retry.** Ghi một kết cục có thể kiểm tra: COMPLETED, QUARANTINED, FAILED hoặc UNKNOWN_OUTCOME. Nếu phải phát lại theo lịch, duy trì attempt budget bền vững qua các lần delivery và restart.

**Bước 5 — Kiểm thử cả hệ thống.** Chạy nhiều message đồng thời với cùng và khác operationId; đo tổng số HTTP calls, tác dụng thực tế ở provider, thời gian hoàn tất, số lượng DLQ và lỗi correlation.

Một bảng before/after:

| Tiêu chí | Khi retry lồng không phối hợp | Sau khi có chính sách tổng |
| --- | --- | --- |
| Số call tối đa | 4 × 3 × 2 = **24** mỗi operation | Đặt trần theo policy đã thống nhất, ví dụ **3** trong một chu kỳ xử lý |
| Timeout | Các tầng tự đặt timeout riêng | Một deadline và budget cho phần còn lại |
| Duplicate | Không có idempotency key ổn định | Cùng operationId/idempotencyKey qua mọi attempt |
| Sau cạn retry | Redelivery và error handler có thể lặp vô hạn | FAILED/UNKNOWN/DLQ rõ ràng; replay có điều kiện |
| Chẩn đoán | Log attempt rời rạc | Correlation, delivery count, retry count theo từng tầng |

**Giới hạn của con số “3”:** Nếu chính sách còn cho broker giao lại hoặc scheduler replay về sau, tổng số lần gọi toàn đời operation **có thể lớn hơn 3**. Muốn khống chế tổng số lần gọi, phải quản lý ngân sách **xuyên delivery và replay**; không chỉ cấu hình RetryAdvice(3).

## 10. Kiểm thử và quan sát runtime

### Các ca kiểm thử có giá trị

1. **Lỗi tạm thời rồi thành công:** downstream thất bại hai lần và thành công lần ba; xác minh đúng ba call, cùng idempotencyKey, chỉ một tác dụng nghiệp vụ.
2. **Payload không hợp lệ:** handler/recovery từ chối ngay; xác minh không tạo vòng retry nóng.
3. **Mọi attempt đều thất bại:** cạn budget sẽ đi đúng error flow/DLQ; message không biến mất sau log.
4. **Timeout sau khi provider đã xử lý:** kiểm tra idempotency hoặc đối soát; không thu tiền lần hai.
5. **ExecutorChannel:** producer hoàn tất send trước lỗi downstream; exception đi đúng error channel, tránh caller tự retry gây hai task song song.
6. **Transaction rollback:** xác minh transaction mới cho mỗi attempt nếu đó là hợp đồng; kiểm tra broker ack/redelivery sau khi hết retry.
7. **Restart giữa các attempt:** budget, idempotencyKey và correlationId không bị reset vô ý; message store vẫn đọc được.
8. **Nhiều consumer/instance:** cùng một operationId chỉ có một trạng thái kết quả được commit, hoặc được đối soát an toàn.
9. **Downstream quá tải hàng loạt:** retry có backoff/jitter và rate limit; không khiến executor queue tăng vô hạn.

Đo số lần gọi ở **đích thật hoặc stub có bộ đếm**, không chỉ số lần framework gọi vào handler; HTTP client có thể tự retry mà unit test của handler không phát hiện.

### Các metric và log nên có

~~~text
operationId=PAY-42 correlationId=checkout-42
flow=payment endpoint=paymentHandler
deliveryAttempt=2 handlerAttempt=3 clientAttempt=1
errorType=PAYMENT_TIMEOUT
decision=QUARANTINED elapsedMs=6480
~~~

- Tổng số external calls theo **operationId** và tỷ lệ số lần gọi trên mỗi yêu cầu nghiệp vụ.
- Số retry theo **từng tầng**, tỷ lệ thành công sau retry, exception class.
- Độ trễ P95/P99, deadline exceeded, in-flight operations và executor queue.
- Message chờ trong queue/poller, DLQ depth, tuổi message lớn nhất, số delayed retries.
- Unknown outcomes, reconciliation pending, duplicate side effects và idempotency key conflicts.
- Số message thiếu correlationId hoặc idempotencyKey ở error flow.

Khi đánh giá hiệu năng, tăng throughput không phải lý do đủ để tăng retry. Retry cần giải quyết **lỗi tạm thời** trong ngân sách; khi downstream quá tải, giảm concurrency hoặc tạm ngừng gửi thường hiệu quả hơn.

## 11. Checklist triển khai

- Xác định mọi nguồn retry: caller, gateway, broker, poller, handler advice, DB/HTTP client, scheduler và replay.
- Viết rõ **retry owner** cho từng loại lỗi và ranh giới; tránh tự thiết lập số lần thử ở nhiều tầng độc lập.
- Tính số attempt tối đa và thời gian xử lý theo **phép nhân** khi có retry lồng.
- Giới hạn **maxAttempts, deadline, timeout, backoff + jitter**, có thể kiểm tra được khi vận hành.
- Chỉ retry lỗi phù hợp; không retry nóng dữ liệu sai hoặc kết quả side effect chưa rõ mà chưa đối soát.
- Giữ operationId, correlationId và **idempotencyKey** qua biến đổi message, broker redelivery, errorChannel, DLQ và restart.
- Định nghĩa transaction/ack, đặc biệt khi qua ExecutorChannel hoặc khi kết hợp RequestHandlerRetryAdvice với transaction advice.
- Thiết kế recovery sau cạn retry với trạng thái bền vững, cảnh báo và replay có điều kiện.
- Xác minh bằng integration test số call **thật**, tác dụng nghiệp vụ và hành vi khi downstream timeout.
- Theo dõi retry storm, executor saturation, queue backlog và số yêu cầu UNKNOWN_OUTCOME.

## Kết luận

Retry là công cụ phục hồi lỗi tạm thời; **retry lồng nhiều tầng** lại có thể biến một lỗi nhỏ thành số lượng lớn request, timeout chồng lấn và side effect lặp. Trong Spring Integration Runtime, phải xem cả channel, endpoint, poller, executor, transaction, adapter, message store và error flow để xác định ai đang retry. Khi có **một chính sách tổng**, ngân sách hữu hạn, idempotency ổn định và recovery có kết cục rõ ràng, hệ thống có thể phục hồi mà vẫn kiểm soát được tải và tính đúng đắn nghiệp vụ.

## Tài liệu tham khảo

- [Spring Integration Reference — Retry Advice](https://docs.spring.io/spring-integration/reference/handler-advice/classes.html)
- [Spring Integration Reference — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html)
- [Spring Integration Reference — Polling Consumer](https://docs.spring.io/spring-integration/reference/endpoint/polling-consumer.html)
- [Spring Integration Reference — Transaction Support](https://docs.spring.io/spring-integration/reference/transactions.html)
- [Spring Retry API — RetryTemplate](https://docs.spring.io/spring-retry/docs/current/apidocs/org/springframework/retry/support/RetryTemplate.html)
- [Spring Retry API — SimpleRetryPolicy](https://docs.spring.io/spring-retry/docs/current/apidocs/org/springframework/retry/policy/SimpleRetryPolicy.html)
