# Đánh dấu message trước hay sau business action

**Idempotent Receiver** là Enterprise Integration Pattern (EIP) giúp hệ thống nhận lại cùng một message nhưng **không thực hiện side effect nghiệp vụ nhiều lần ngoài ý muốn**. Trong Spring Integration, có thể dùng `IdempotentReceiverInterceptor` kết hợp `MessageSelector` và `MetadataStoreSelector` để phát hiện một key đã xuất hiện. Tuy nhiên, một câu hỏi quan trọng hơn việc phát hiện duplicate là: **thời điểm nào mới được ghi rằng một message đã được xử lý?**

Nếu **đánh dấu trước business action**, hệ thống dễ chặn hai worker thực thi cùng một việc, nhưng có nguy cơ **mất tác vụ** nếu ứng dụng chết sau khi lưu dấu mà trước khi side effect xảy ra. Nếu **đánh dấu sau business action**, retry dễ khôi phục tác vụ chưa chạy, nhưng có nguy cơ **làm trùng side effect** nếu ứng dụng chết sau khi side effect thành công mà trước lúc lưu dấu. Cả hai cách đều có một **crash window** nếu marker và tác vụ nghiệp vụ không nằm trong cùng ranh giới giao dịch hoặc không có một giao thức phối hợp.

Bài **Đánh dấu message trước hay sau business action** thuộc chương **Idempotent receiver** của module **SPRING_INTEGRATION_PATTERN**. Module tập trung thực hành Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel và correlation với Spring Integration để xây dựng luồng thông điệp ít phụ thuộc, dễ mở rộng và có thể kiểm thử/quan sát.

**Kết luận nền tảng:** Không có một quy tắc "luôn đánh dấu trước" hoặc "luôn đánh dấu sau" đúng cho mọi topology. Cần phân biệt **đã nhìn thấy message**, **đang xử lý message** và **business action đã commit**. Với side effect trong **cùng một database**, nên dùng unique constraint và một transaction chung để **ghi marker và thay đổi nghiệp vụ commit nguyên tử**. Với side effect qua hệ thống khác, cần idempotency phía đích, outbox/inbox hoặc một state machine có cơ chế recovery rõ ràng.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt duplicate delivery, duplicate business command và một message instance mới.
2. Nắm thời điểm `MetadataStoreSelector` đánh dấu key trong store.
3. Hiểu chính xác hành vi mặc định của `IdempotentReceiverInterceptor` khi selector từ chối message.
4. So sánh rủi ro đánh dấu **BEFORE** và **AFTER** business action qua các điểm crash.
5. Phân biệt `RECEIVED`, `PROCESSING`, `SUCCEEDED` và `FAILED` thay vì một boolean duy nhất.
6. Chọn idempotency key ổn định, có namespace và kiểm soát xung đột cùng key khác payload.
7. Sử dụng `ConcurrentMetadataStore.putIfAbsent` để claim key nguyên tử, đồng thời hiểu giới hạn của nó.
8. Cấu hình Spring Integration Java DSL với advice và duplicate discard route.
9. Thiết kế transaction chung cho marker và cập nhật nghiệp vụ trong một database.
10. Xây inbox/outbox hoặc remote API idempotency strategy cho side effect xuyên hệ thống.
11. Kiểm thử crash window, retry, hai worker đồng thời, broker redelivery và timeout.
12. Đặt metric, log và chính sách TTL/reconciliation giúp không chặn sai message chưa hoàn tất.

## 2. Bài toán: thanh toán bị gửi lại

Một service nhận sự kiện `InvoicePaymentConfirmed` và cộng tiền đã thanh toán vào số dư hóa đơn:

~~~text
Message:
  tenantId = tenant-a
  eventId = evt-pay-1001
  invoiceId = INV-1001
  paidMinorUnits = 25000
~~~

Một message có thể tới hai lần vì:

- Broker không nhận được ACK dù handler đã commit.
- Consumer bị restart, partition được rebalance.
- Producer retry vì network timeout.
- DLQ được replay.
- Sự kiện được chuyển lại từ event replay hoặc data recovery.

Nếu mỗi lần nhận đều chạy:

~~~sql
UPDATE invoice_balance
SET paid_minor_units = paid_minor_units + 25000
WHERE tenant_id = 'tenant-a'
  AND invoice_id = 'INV-1001';
~~~

thì **cùng sự kiện** xuất hiện hai lần sẽ làm số tiền đã thanh toán tăng gấp đôi.

~~~mermaid
flowchart LR
    B["Broker: evt-pay-1001"] --> C1["Consumer nhận lần 1"]
    B --> C2["Broker redelivery lần 2"]
    C1 --> D["Idempotent receiver"]
    C2 --> D
    D --> DB[("Business DB")]
    DB --> O["Chỉ một business effect hợp lệ"]
~~~

Nhiệm vụ của Idempotent Receiver không chỉ là nhận diện hai lần delivery, mà là **đảm bảo side effect phù hợp contract** ngay cả khi một attempt thất bại ở thời điểm khó nhất.

## 3. "Đã nhận" khác "đã thực hiện"

Ba câu nói sau khác nhau:

1. **Đã nhìn thấy message**: một attempt nhận đã đến ingress.
2. **Đã giành quyền xử lý**: một worker claim được key, worker khác chưa được chạy cùng tác vụ.
3. **Đã hoàn thành business action**: thay đổi nghiệp vụ đã commit hoặc được hệ thống đích xác nhận chắc chắn theo hợp đồng.

~~~mermaid
flowchart TD
    M["Message tới"] --> R["RECEIVED"]
    R --> P["PROCESSING (claim/lock)"]
    P --> A["Business action"]
    A --> S["SUCCEEDED (committed)"]
    P --> F["FAILED / RETRYABLE"]
    F --> P
~~~

Một entry trong MetadataStore có thể chứng minh **key từng được ghi vào store**, nhưng **không tự chứng minh** rằng business action đã chạy xong. Đó là sự khác biệt quyết định thời điểm đánh dấu.

### 3.1. Hai lớp định danh

| Định danh | Nhận diện | Có phù hợp làm idempotency key? |
|---|---|---|
| `MessageHeaders.ID` | Một instance của Spring Message | Thường không: retry có thể tạo instance mới |
| `eventId` | Một sự kiện nghiệp vụ ổn định qua redelivery | Thường phù hợp với event consumer |
| `commandId` | Một lệnh có ý nghĩa nghiệp vụ duy nhất | Thường phù hợp với command receiver |
| `invoiceId` | Một hóa đơn | Quá rộng nếu hóa đơn có nhiều payment events |
| `traceId` | Một trace/span flow | Không thay thế event/command identity |
| `deliveryTag` | Một lần delivery của broker | Không ổn định qua redelivery |
| `correlationId` | Nhóm message liên quan | Có thể quá rộng nếu một group có nhiều tác vụ |
| `retryAttempt` | Số lần xử lý | Không, vì mỗi retry sẽ tạo key mới |

Nếu consumer đang ghi nhận mỗi **payment event** riêng, key gợi ý là `(tenantId, sourceId, eventId)`; nếu đang nhận một **lệnh thanh toán** có thể được gửi lại, key có thể là `(tenantId, commandId)`. Key phải được cấp **một lần** ở nguồn có thẩm quyền và được **giữ nguyên qua retry**.

### 3.2. Cùng key nhưng payload khác là lỗi

~~~text
Lần 1:
  key=(tenant-a, evt-pay-1001)
  paidMinorUnits=25000

Lần 2:
  key=(tenant-a, evt-pay-1001)
  paidMinorUnits=75000
~~~

Không được âm thầm loại message thứ hai như một duplicate an toàn. Cùng key nhưng payload khác có thể là **idempotency-key reuse bug, xung đột dữ liệu hoặc tấn công**. Lưu một `requestFingerprint` được tính từ canonical business fields để kiểm tra sự nhất quán, không gồm những trường thay đổi mỗi lần delivery như timestamp/traceId/retry count.

## 4. Phương án A: đánh dấu trước business action

Giả sử hệ thống thực hiện:

~~~text
1. Dedup Store: putIfAbsent(eventId, "seen")
2. Nếu tồn tại key -> skip
3. Nếu key mới -> cập nhật invoice
4. ACK broker
~~~

### 4.1. Timeline thành công

~~~mermaid
sequenceDiagram
    participant C as Consumer
    participant M as MetadataStore
    participant DB as Business DB
    participant B as Broker

    C->>M: putIfAbsent(evt-pay-1001, "seen")
    M-->>C: Key mới, accepted
    C->>DB: UPDATE invoice balance
    DB-->>C: Commit OK
    C->>B: ACK
~~~

Lợi thế:

- `putIfAbsent` nguyên tử có thể chặn hai worker cùng claim key.
- Duplicate đến sau được nhận diện sớm.
- Giảm thực thi business handler trùng khi hệ thống khỏe mạnh.

Nhưng việc **lưu dấu thấy message trước** không được nhầm với **business action đã commit**.

### 4.2. Crash window nguy hiểm

~~~mermaid
sequenceDiagram
    participant C as Consumer
    participant M as MetadataStore
    participant DB as Business DB
    participant B as Broker

    C->>M: putIfAbsent(evt-pay-1001)
    M-->>C: Accepted, marker đã tồn tại
    Note over C: Crash trước UPDATE invoice
    B->>C: Redelivery evt-pay-1001
    C->>M: putIfAbsent(evt-pay-1001)
    M-->>C: Duplicate
    Note over C: Skip, invoice chưa hề cập nhật
~~~

Đây là **lost work**: marker nói "đã xử lý", nhưng nghiệp vụ chưa chạy.

Nếu marker được commit và tồn tại qua restart, hệ thống có thể bỏ qua tác vụ vĩnh viễn. Vì vậy một `ConcurrentMetadataStore` chỉ có key-value "seen" là chưa đủ cho mọi nghiệp vụ có side effect quan trọng.

### 4.3. Ghi dấu trước phù hợp khi nào?

- Side effect **không quan trọng** và chấp nhận mất một số attempt.
- Việc xử lý có thể được **tự khôi phục** bằng reconciliation độc lập.
- Marker trước là **PROCESSING/lease**, không phải **DONE**, có takeover an toàn khi worker chết.
- Marker và business write nằm trong **cùng transaction**, nên chưa có commit marker độc lập trước business action.

Đối với trừ tiền, thanh toán, ghi sổ hoặc cấp quyền quan trọng, **không** được mặc định xem mark-before độc lập là một bảo đảm exactly-once.

## 5. Phương án B: thực hiện rồi mới đánh dấu

Giả sử hệ thống làm:

~~~text
1. Kiểm tra key đã DONE chưa
2. Nếu chưa -> cập nhật invoice
3. Lưu marker DONE
4. ACK broker
~~~

### 5.1. Timeline thành công

~~~mermaid
sequenceDiagram
    participant C as Consumer
    participant DB as Business DB
    participant M as MetadataStore
    participant B as Broker

    C->>M: get(evt-pay-1001)
    M-->>C: Not found
    C->>DB: UPDATE invoice balance
    DB-->>C: Commit OK
    C->>M: put(evt-pay-1001, DONE)
    M-->>C: Saved
    C->>B: ACK
~~~

Ưu điểm: nếu business action chưa bắt đầu mà hệ thống chết, message được redeliver và vẫn chưa có marker DONE; có cơ hội xử lý lại.

### 5.2. Crash window sau side effect

~~~mermaid
sequenceDiagram
    participant C as Consumer
    participant DB as Business DB
    participant M as MetadataStore
    participant B as Broker

    C->>DB: UPDATE invoice balance
    DB-->>C: Commit OK
    Note over C: Crash trước khi ghi DONE
    B->>C: Redelivery evt-pay-1001
    C->>M: get(evt-pay-1001)
    M-->>C: Chưa có marker
    C->>DB: UPDATE invoice balance lần nữa
    Note over DB: Double credit / duplicate side effect
~~~

Đây là **duplicate effect**: nghiệp vụ đã thành công nhưng dấu hoàn tất chưa được ghi.

### 5.3. Race khi hai worker kiểm tra trước

Ngay cả khi không crash, lối làm `get()` rồi `put()` đơn giản không an toàn trước concurrency:

~~~text
Worker A: get(key) -> absent
Worker B: get(key) -> absent
Worker A: business action
Worker B: business action
Worker A: put(key, DONE)
Worker B: put(key, DONE)
~~~

Cả hai worker có thể chạy tác vụ. Thêm `synchronized` trong một JVM chỉ có tác dụng trong chính JVM đó, không đủ cho multi-instance.

## 6. Bảng so sánh mark-before và mark-after

| Tiêu chí | Mark-before (marker commit độc lập) | Mark-after (marker commit độc lập) |
|---|---|---|
| Marker tồn tại trước side effect? | Có | Không |
| Rủi ro khi crash trước business action | **Bỏ sót việc** vì key đã seen | Có thể retry |
| Rủi ro khi crash sau action, trước marker | Nếu action đã chạy, marker tồn tại | **Lặp side effect** |
| Race giữa hai worker | `putIfAbsent` có thể bảo vệ claim | `get` rồi `put` đơn giản không an toàn |
| Đồng nghĩa DONE với đã commit? | **Không** | Có ý định, nhưng vẫn có crash window |
| Phù hợp với việc cực kỳ quan trọng? | Chỉ với recovery/atomicity phù hợp | Chỉ với idempotent action/atomicity phù hợp |
| Nếu backend đích không transactional | Cần recovery protocol | Cần idempotency từ phía đích |
| Nếu marker và action cùng DB transaction | Có thể commit nguyên tử | Có thể commit nguyên tử |

Một phân loại hữu ích:

- Mark-before độc lập thiên về **at-most-once attempt** ở phía consumer, nhưng có thể mất tác vụ.
- Mark-after độc lập thiên về **at-least-once business attempt**, nhưng có thể tạo tác dụng lặp.
- Muốn **effectively-once** theo ngữ nghĩa nghiệp vụ, cần atomicity, idempotency hoặc cơ chế reconciliation ở hệ thống đích.

Đây là các **xu hướng failure mode**, không phải bảo đảm tuyệt đối của một phương thức gọi `put()`.

## 7. Bảng crash points để quyết định

| Thời điểm crash | Mark-before độc lập | Mark-after độc lập | Một DB transaction chung |
|---|---|---|---|
| Trước ghi marker và action | Retry như mới | Retry như mới | Retry như mới |
| Sau marker đã commit, trước action | Có thể skip sai | Không xảy ra theo thứ tự after | Marker chưa commit nếu transaction chưa hoàn tất |
| Sau action đã commit, trước marker | Marker đã có, khó biết kết quả | Có thể chạy lại action | Không có trạng thái nửa commit nếu cùng transaction |
| Sau cả hai commit, trước ACK | Duplicate được nhận diện | Duplicate được nhận diện | Duplicate được nhận diện bằng unique key |
| Trong khi hai worker xử lý cùng key | Cần atomic claim | `get+put` không đủ | Unique constraint/transaction isolation |
| Remote side effect đã thành công, response mất | Marker không chứng minh kết quả | Marker chưa có → có thể retry | Transaction local không bao trùm remote |

**Không nên chỉ test happy path.** Những mốc crash ở giữa mới quyết định tính đúng đắn của Idempotent Receiver.

## 8. Spring Integration IdempotentReceiverInterceptor hoạt động thế nào?

Spring Integration cung cấp `IdempotentReceiverInterceptor` dưới dạng một **advice** bao quanh `MessageHandler.handleMessage()`. Nó sử dụng một `MessageSelector` để quyết định message được chấp nhận hay bị xem là duplicate.

Điểm cần hiểu chính xác:

- Nó **không phải một endpoint EIP độc lập** thay cho business handler.
- Nó được gắn vào advice chain của handler endpoint, ví dụ qua Java DSL.
- Nếu selector từ chối message và **không cấu hình discard channel hoặc throw exception**, interceptor **mặc định chuyển message có header `duplicateMessage=true` cho handler**.
- Nếu muốn duplicate **không đi vào handler**, phải cấu hình `discardChannel` hoặc `throwExceptionOnRejection=true` phù hợp.
- Dùng `nullChannel` làm discard destination nếu mục tiêu là drop im lặng, nhưng phải cân nhắc ACK/observability.

### 8.1. Hành vi mặc định không phải auto-skip

~~~text
New message:
  selector.accept() = true
  -> handler.handleMessage(message)

Duplicate:
  selector.accept() = false
  -> interceptor gắn duplicateMessage=true
  -> handler vẫn có thể được gọi (mặc định)
~~~

Nếu handler bỏ qua header duplicate và luôn ghi DB, bạn có thể vẫn gặp double effect mặc dù đã dùng advice. Đây là một **ngộ nhận nguy hiểm**.

### 8.2. Điều kiện loại duplicate khỏi handler

~~~text
Duplicate
  -> discardChannel được cấu hình
     -> message chuyển tới discard flow
     -> target handler không chạy

Hoặc:
  -> throwExceptionOnRejection=true
     -> MessageRejectedException theo error flow
     -> target handler không chạy
~~~

Cần chọn đường xử lý phù hợp:

- Duplicate thực sự đã DONE: có thể acknowledge/no-op.
- Duplicate đang PROCESSING: có thể cần retry/requeue, **không mặc nhiên ACK như DONE**.
- Cùng key nhưng fingerprint khác: báo conflict/quarantine.
- Duplicate request HTTP: nhiều trường hợp nên trả **kết quả đã lưu**, không chỉ bỏ message.

## 9. MetadataStoreSelector: ghi dấu xảy ra khi nào?

`MetadataStoreSelector` dùng một `MessageProcessor<String>` để tính key và một `ConcurrentMetadataStore` để duy trì metadata. Với key chưa tồn tại, selector sử dụng thao tác **`putIfAbsent(key,value)`** để nhận message. Điều này có nghĩa marker có thể được **ghi khi đánh giá selector, trước khi handler thực hiện business action**.

~~~mermaid
flowchart TD
    IN["Message tới"] --> K["Key strategy tạo idempotency key"]
    K --> M{"metadataStore.putIfAbsent()"}
    M -->|"Mới"| H["Handler business action"]
    M -->|"Đã có"| D["duplicateMessage / discard / reject"]
~~~

### 9.1. Value mặc định của metadata store

Trong `MetadataStoreSelector`, value mặc định được suy từ **timestamp header** (biểu diễn chuỗi/hex theo implementation). Điều đó **không** có nghĩa value đang lưu là kết quả business action. Nếu cần lưu `SUCCEEDED`, error reason, request fingerprint hoặc receipt, phải **thiết kế state storage riêng** hoặc custom value/processor có hợp đồng rõ.

### 9.2. Atomic putIfAbsent không đồng nghĩa atomic business action

`ConcurrentMetadataStore.putIfAbsent` giúp một worker giành key một cách nguyên tử **trong phạm vi backend hỗ trợ**. Nhưng nó không làm:

~~~text
putIfAbsent + call external API
~~~

thành một transaction chung. Nếu hai bước được thực hiện ở hai tài nguyên khác nhau, crash window vẫn tồn tại.

### 9.3. compareValues không phải xác nhận DONE

`MetadataStoreSelector` hỗ trợ `compareValues` để so giá trị cũ/mới và có thể chấp nhận/ghi đè theo rule, hữu ích cho thứ tự line/file offset hoặc version. Không dùng nó để tự suy "business đã thành công" nếu value chỉ là timestamp. Một value tăng lên có thể mô tả progression, **không bảo đảm side effect đã commit**.

## 10. Chọn key và fingerprint có hợp đồng

Ví dụ event Java 17:

~~~java
public record InvoicePaymentConfirmed(
        String tenantId,
        String sourceId,
        String eventId,
        String invoiceId,
        long paidMinorUnits,
        String payloadFingerprint
) {
    public InvoicePaymentConfirmed {
        if (tenantId == null || tenantId.isBlank()) {
            throw new IllegalArgumentException("TENANT_REQUIRED");
        }
        if (sourceId == null || sourceId.isBlank()) {
            throw new IllegalArgumentException("SOURCE_REQUIRED");
        }
        if (eventId == null || eventId.isBlank()) {
            throw new IllegalArgumentException("EVENT_ID_REQUIRED");
        }
        if (invoiceId == null || invoiceId.isBlank()) {
            throw new IllegalArgumentException("INVOICE_ID_REQUIRED");
        }
        if (paidMinorUnits <= 0) {
            throw new IllegalArgumentException("AMOUNT_INVALID");
        }
        if (payloadFingerprint == null
                || payloadFingerprint.isBlank()) {
            throw new IllegalArgumentException("FINGERPRINT_REQUIRED");
        }
    }
}
~~~

`payloadFingerprint` là dấu vân tay được tạo/kiểm chứng ở ingress theo **canonical business fields**, chẳng hạn loại event, invoiceId, amount, currency, nguồn và version. Không đơn thuần tin fingerprint từ client rồi coi là an toàn: server phải tính/đối chiếu để phát hiện cùng key khác nội dung.

### 10.1. Composite key tránh collision

~~~java
import java.io.Serializable;

public record EventDedupKey(
        String tenantId,
        String sourceId,
        String eventId
) implements Serializable {}
~~~

Một key gồm `(tenantId,sourceId,eventId)` phù hợp khi eventId ổn định trong namespace của từng nguồn. Nếu API dùng `commandId` do client cấp, cần scope theo tenant và operation type để tránh hai lệnh khác nhau trùng idempotency key.

### 10.2. Đừng dùng giá trị dễ thay đổi làm key

Các lựa chọn rủi ro:

- `Instant.now()` hoặc UUID được sinh **mỗi lần delivery**.
- `retryAttempt` hoặc broker delivery tag.
- `MessageHeaders.ID` khi retry tạo message mới.
- `invoice.status`, balance, email, updatedAt.
- `invoiceId` một mình khi nhiều payment events hợp lệ cùng invoice.

Những key này có thể khiến replay không bị chặn hoặc **chặn nhầm** các giao dịch khác nhau.

## 11. Java DSL: chặn duplicate trước handler để minh họa

Đoạn cấu hình sau minh họa hành vi của `MetadataStoreSelector` và `IdempotentReceiverInterceptor`: key được claim **trước** khi handler chạy. Chúng ta chủ động gửi duplicate tới `nullChannel` để không gọi handler lần nữa.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.handler.advice.IdempotentReceiverInterceptor;
import org.springframework.integration.metadata.ConcurrentMetadataStore;
import org.springframework.integration.metadata.SimpleMetadataStore;
import org.springframework.integration.selector.MetadataStoreSelector;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
public class PreMarkIdempotencyConfiguration {

    @Bean(name = "payments.in")
    public MessageChannel input() {
        return new DirectChannel();
    }

    @Bean
    public ConcurrentMetadataStore dedupMetadataStore() {
        return new SimpleMetadataStore();
    }

    @Bean
    public InvoiceEventHandler invoiceEventHandler() {
        return new InvoiceEventHandler();
    }

    @Bean
    public IdempotentReceiverInterceptor invoiceDedupAdvice(
            ConcurrentMetadataStore dedupMetadataStore) {

        MetadataStoreSelector selector =
                new MetadataStoreSelector(message -> {
                    InvoicePaymentConfirmed event =
                            (InvoicePaymentConfirmed)
                                    message.getPayload();

                    return event.tenantId() + ":"
                            + event.sourceId() + ":"
                            + event.eventId();
                }, dedupMetadataStore);

        IdempotentReceiverInterceptor advice =
                new IdempotentReceiverInterceptor(selector);

        advice.setDiscardChannelName("nullChannel");
        return advice;
    }

    @Bean
    public IntegrationFlow preMarkFlow(
            IdempotentReceiverInterceptor invoiceDedupAdvice) {
        return IntegrationFlow.from("payments.in")
                .handle("invoiceEventHandler", "apply",
                        endpoint -> endpoint
                                .advice(invoiceDedupAdvice))
                .get();
    }
}
~~~

Business handler demo:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

public final class InvoiceEventHandler {

    private final AtomicInteger calls =
            new AtomicInteger();

    public void apply(InvoicePaymentConfirmed event) {
        calls.incrementAndGet();
    }

    public int invocationCount() {
        return calls.get();
    }
}
~~~

Hai đoạn code là ví dụ **quan sát advice và dedup trong một JVM**. Business handler chỉ đếm số lần được gọi, không thực hiện thanh toán. Không dùng cách marker-only này làm bảo đảm mất mát bằng 0 cho hành động tài chính quan trọng.

### 11.1. Khác biệt với mặc định

Nếu bỏ dòng:

~~~java
advice.setDiscardChannelName("nullChannel");
~~~

thì duplicate có thể **vẫn đi vào handler** với header `IntegrationMessageHeaderAccessor.DUPLICATE_MESSAGE` bằng `true`. Handler demo `apply(InvoicePaymentConfirmed)` không nhìn headers, nên nó có thể tăng count hai lần. Bài học: **phải quy định rõ duplicate outcome**, không chỉ tạo interceptor bean.

### 11.2. Tính chính xác của key encoding

Nối ba trường bằng dấu `:` chỉ an toàn nếu contract đảm bảo chúng không chứa dấu phân cách hoặc có escaping/length-prefix. Với sản phẩm thực tế, nên dùng canonical key codec, value object với encoding không collision hoặc unique columns ở database. Không dùng `tenantId + ":" + eventId` mà không có namespace và encoding policy.

### 11.3. Tính bền vững của store

`SimpleMetadataStore` chỉ tồn tại trong bộ nhớ. Sau restart, key "seen" không còn, nên redelivery có thể được xử lý lại. Với production cần persistent/concurrent store phù hợp, nhưng **durable marker không xóa được crash window giữa marker và side effect**.

## 12. Thử nghiệm đơn giản với selector

Trước khi chạy full integration test, có thể kiểm tra hành vi nguyên tử của selector trong một JVM:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;
import org.springframework.integration.metadata.SimpleMetadataStore;
import org.springframework.integration.selector.MetadataStoreSelector;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

class MetadataStoreSelectorTest {

    @Test
    void firstAcceptWritesMarkerBeforeAnyBusinessAction() {
        SimpleMetadataStore store =
                new SimpleMetadataStore();

        MetadataStoreSelector selector =
                new MetadataStoreSelector(
                        message -> "invoice-payment:" +
                                message.getPayload(),
                        store);

        Message<String> event =
                MessageBuilder.withPayload("evt-1001").build();

        assertTrue(selector.accept(event));

        // Selector đã ghi metadata dù chưa gọi handler nào.
        assertNotNull(store.get("invoice-payment:evt-1001"));

        // Lần accept thứ hai bị coi là duplicate.
        assertFalse(selector.accept(event));
    }
}
~~~

Đây là một bằng chứng trực tiếp: `MetadataStoreSelector` lưu key khi `accept` thành công, **không đợi business action**. Bài toán nghiệp vụ phải xử lý hậu quả nếu worker chết ở khoảng giữa.

## 13. Integration test: duplicate không vào handler

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(classes = PreMarkIdempotencyConfiguration.class)
class PreMarkIdempotencyFlowTest {

    @Autowired
    @Qualifier("payments.in")
    MessageChannel input;

    @Autowired
    InvoiceEventHandler handler;

    @Test
    void discardsRedeliveryBeforeCallingTargetHandler() {
        InvoicePaymentConfirmed event =
                new InvoicePaymentConfirmed(
                        "tenant-a",
                        "payment-provider",
                        "evt-pay-1001",
                        "INV-1001",
                        25000,
                        "verified-fingerprint");

        assertTrue(input.send(
                MessageBuilder.withPayload(event).build()));

        assertTrue(input.send(
                MessageBuilder.withPayload(event).build()));

        assertEquals(1, handler.invocationCount());
    }
}
~~~

Test kiểm tra **wiring của Spring Integration advice** và đường discard duplicate. Test này **không** chứng minh nghiệp vụ đã commit, vì handler chỉ tăng counter; nó cũng không kiểm tra restart hoặc multi-instance. Nên dùng event ID riêng cho mỗi test hoặc cô lập Spring context nếu các bài test dùng chung MetadataStore.

### 13.1. Test khi handler ném lỗi

Bổ sung một handler giả:

~~~java
public void apply(InvoicePaymentConfirmed event) {
    throw new IllegalStateException("DB_TEMPORARILY_UNAVAILABLE");
}
~~~

Với mark-before selector và một persistent marker không tham gia rollback business transaction, message **đã có marker trước khi handler ném lỗi**. Một retry sử dụng cùng key có nguy cơ bị discard, **làm mất business action**. Đây là failure test quan trọng hơn test duplicate count.

### 13.2. Không dùng header duplicate làm "đã DONE"

Nếu không cấu hình discard, một handler có thể nhận `duplicateMessage=true`. Nhưng marker có thể được tạo **trước** một attempt đã thất bại. Header duplicate chỉ nói selector từng gặp key, **không tự nói attempt trước thành công**. Đối với nghiệp vụ quan trọng, hãy tra **business outcome state** đáng tin thay vì discard vô điều kiện.

## 14. Khi nào dùng mark-before độc lập và khi nào không?

| Trường hợp | Có thể chấp nhận? | Vì sao |
|---|---|---|
| Cache warm-up có thể rebuild | Có thể | Lost work được khôi phục bằng job khác |
| Gửi metric best-effort | Có thể | Duplicate/loss có trade-off riêng |
| Đồng bộ dữ liệu sẽ có reconciliation định kỳ | Có điều kiện | Cần recovery process |
| Cộng tiền đã thanh toán | Không, nếu chỉ có seen marker | Có thể làm mất khoản thanh toán |
| Trừ tiền tài khoản | Không | Hậu quả tài chính nghiêm trọng |
| Phát email xác nhận | Cân nhắc | Có thể tránh trùng nhưng mất email |
| Tạo shipment | Không nên marker-only | Cần idempotent API hoặc state machine |
| Ghi event vào local database | Nên transaction hóa | Marker và write có thể commit cùng nhau |

**Phải phát biểu rõ ngữ nghĩa nghiệp vụ:** có chấp nhận thất lạc? Có thể phát lại? Hệ thống đích có hỗ trợ idempotency key? Cần biết outcome đã thành công hay chưa? Một boolean seen không trả lời đủ các câu hỏi này.
## 15. Một database: marker và business action cùng transaction

Nếu marker và thay đổi nghiệp vụ nằm trong **cùng một relational database**, cách tiếp cận mạnh nhất thường là:

1. Mở **một database transaction**.
2. Dùng unique constraint để claim `(tenantId, sourceId, eventId)`.
3. Nếu key đã tồn tại, so fingerprint, đọc outcome và **không cập nhật nghiệp vụ lần nữa**.
4. Nếu key mới, thực hiện business mutation **trong cùng transaction**.
5. Commit marker và business mutation **cùng nhau**.
6. ACK broker theo chính sách delivery **sau khi transaction thành công**.

~~~mermaid
flowchart TD
    IN["Event redelivery"] --> TX["BEGIN DB TRANSACTION"]
    TX --> INSERT{"INSERT dedup key với UNIQUE"}
    INSERT -->|"Key đã có"| CHECK["Compare fingerprint / load result"]
    CHECK --> EXIST["Return existing outcome"]
    INSERT -->|"Key mới"| WRITE["UPDATE business state"]
    WRITE --> COMMIT["COMMIT marker + business state"]
    EXIST --> ACK["ACK theo delivery policy"]
    COMMIT --> ACK
~~~

**Điểm quan trọng:** ở mức SQL, `INSERT marker` có thể được thực hiện **trước** `UPDATE business`, nhưng **không được commit marker riêng**. Nếu UPDATE thất bại và transaction rollback, marker **cũng rollback**. Không tồn tại trạng thái một phần đã commit marker mà chưa commit business action trong cùng transaction.

### 15.1. DDL minh họa PostgreSQL

~~~sql
CREATE TABLE invoice_balance (
    tenant_id         VARCHAR(80) NOT NULL,
    invoice_id        VARCHAR(160) NOT NULL,
    paid_minor_units  BIGINT NOT NULL DEFAULT 0,
    PRIMARY KEY (tenant_id, invoice_id),
    CHECK (paid_minor_units >= 0)
);

CREATE TABLE processed_payment_event (
    tenant_id         VARCHAR(80) NOT NULL,
    source_id         VARCHAR(80) NOT NULL,
    event_id          VARCHAR(160) NOT NULL,
    request_hash      VARCHAR(128) NOT NULL,
    applied_at        TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (tenant_id, source_id, event_id)
);
~~~

`processed_payment_event` vừa là dedup ledger vừa là bằng chứng có transaction đã commit. Để trả lại đúng receipt của request đầu, có thể lưu thêm kết quả hoặc reference tới business record.

### 15.2. Service Java với @Transactional

~~~java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class TransactionalInvoicePaymentService {

    private final JdbcTemplate jdbc;

    public TransactionalInvoicePaymentService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public ApplyOutcome apply(
            InvoicePaymentConfirmed event) {

        // Fingerprint được tính và xác thực tại ingress.
        String hash = event.payloadFingerprint();

        int claimed = jdbc.update(
                """
                INSERT INTO processed_payment_event
                    (tenant_id, source_id, event_id, request_hash)
                VALUES (?, ?, ?, ?)
                ON CONFLICT (tenant_id, source_id, event_id)
                DO NOTHING
                """,
                event.tenantId(),
                event.sourceId(),
                event.eventId(),
                hash);

        if (claimed == 0) {
            String previousHash = jdbc.queryForObject(
                    """
                    SELECT request_hash
                    FROM processed_payment_event
                    WHERE tenant_id = ?
                      AND source_id = ?
                      AND event_id = ?
                    """,
                    String.class,
                    event.tenantId(),
                    event.sourceId(),
                    event.eventId());

            if (!hash.equals(previousHash)) {
                throw new IllegalStateException(
                        "SAME_KEY_DIFFERENT_PAYLOAD");
            }

            return ApplyOutcome.ALREADY_APPLIED;
        }

        int updated = jdbc.update(
                """
                UPDATE invoice_balance
                SET paid_minor_units = paid_minor_units + ?
                WHERE tenant_id = ?
                  AND invoice_id = ?
                """,
                event.paidMinorUnits(),
                event.tenantId(),
                event.invoiceId());

        if (updated != 1) {
            throw new IllegalStateException(
                    "INVOICE_NOT_FOUND");
        }

        return ApplyOutcome.APPLIED;
    }
}
~~~

Enum output:

~~~java
public enum ApplyOutcome {
    APPLIED,
    ALREADY_APPLIED
}
~~~

Ví dụ dùng **PostgreSQL** (cú pháp `ON CONFLICT DO NOTHING`), Spring JDBC và `PlatformTransactionManager` đúng với cùng `DataSource`. Với dialect khác, cú pháp insert-if-absent thay đổi. Các kiểu top-level `public` phải nằm trong source file riêng.

Điểm cốt lõi:

- `processed_payment_event` có unique key nhận diện event.
- Marker và `invoice_balance` được cập nhật trong **cùng một DB transaction**.
- UPDATE thất bại thì cả marker và business write rollback.
- Retry sau commit gặp duplicate và không cộng tiền lần nữa.
- Hai worker cùng key được phân xử bằng **unique constraint của DB**, không phải `SELECT exists` thiếu locking.

**Phải cấu hình transaction thật:** method `@Transactional` được gọi qua Spring proxy/transaction interceptor, không self-invoke rồi kỳ vọng annotation tự có hiệu lực. Kiểm tra rollback rules và transaction manager cùng database; chạy concurrency test trên DB thực tế.

### 15.3. Crash giữa transaction

~~~text
BEGIN
  INSERT marker (chưa commit)
  UPDATE invoice (chưa commit)
  CRASH
ROLLBACK
~~~

Sau restart, redelivery có thể claim key vì marker **chưa từng commit**. Khi transaction commit thành công, cả marker và business effect xuất hiện cùng nhau. Điều này **không** bao trùm side effect HTTP hoặc broker ngoài transaction.

### 15.4. Tránh marker-only advice chặn retry trước transaction

Nếu flow có `MetadataStoreSelector` ở ngoài transaction với marker độc lập, advice có thể lưu `seen` rồi service rollback. Retry bị discard **trước khi tới business transaction**. Với nghiệp vụ tài chính, ưu tiên **DB unique ledger + transaction**, không dùng pre-mark độc lập làm chốt duy nhất. Advice có thể giảm tải khi đã biết outcome `SUCCEEDED`, nhưng không chặn attempt cần recovery.

## 16. Kiểm thử rollback và duplicate với transaction

Chỉ mock repository hoặc dùng `AtomicInteger` không chứng minh được tính nguyên tử của transaction. Test quan trọng nên dùng database có unique constraint thực và một transaction manager giống production.

| Kịch bản | Thao tác | Kỳ vọng |
|---|---|---|
| Event mới | Gửi `evt-pay-1001` | Marker 1, balance tăng một lần |
| Redelivery | Gửi lại cùng key/fingerprint | Balance không tăng nữa |
| Same key, changed payload | Thay amount và fingerprint | Conflict, không cộng tiền |
| Invoice không tồn tại | INSERT marker rồi UPDATE 0 rows | Transaction rollback marker |
| Retry sau rollback | Tạo invoice và gửi lại | Apply được đúng một lần |
| Hai worker cùng key | Hai transaction đồng thời | Chỉ một mutation hợp lệ |
| Crash trước commit | Mất connection | Không có nửa marker/nửa business write |
| Commit xong mất ACK | Redelivery | Duplicate được nhận diện |

### 16.1. Kịch bản JUnit kiểm tra rollback

~~~java
@Test
void failedBusinessWriteDoesNotLeaveMarker() {
    InvoicePaymentConfirmed event =
            testPayment("evt-rollback-1", "INV-MISSING");

    assertThrows(IllegalStateException.class,
            () -> invoiceService.apply(event));

    assertEquals(0, processedEventCount(
            event.tenantId(),
            event.sourceId(),
            event.eventId()));

    createInvoice("INV-MISSING");

    assertEquals(ApplyOutcome.APPLIED,
            invoiceService.apply(event));

    assertEquals(1, processedEventCount(
            event.tenantId(),
            event.sourceId(),
            event.eventId()));
}
~~~

Đây là **test recipe**: các helper `testPayment`, `processedEventCount`, `createInvoice` và fixture `invoiceService` cần hiện thực theo project. Để kiểm tra rollback thật, tránh bọc toàn bộ test trong transaction riêng khiến thời điểm commit khác production.

### 16.2. Concurrency test

Khởi chạy hai worker với hai connections/transactions, cùng `(tenantId, sourceId, eventId)` và cùng fingerprint. Dùng barrier cho hai attempt bắt đầu gần nhau, nhưng assert ở **database sau commit** rằng chỉ một marker và một business mutation tồn tại. `synchronized` trong một instance không chứng minh hành vi nhiều JVM.

## 17. Side effect ngoài database: PROCESSING và SUCCEEDED

Khi business action là HTTP call tới payment API, shipping API hoặc email provider, local metadata store và remote action **không tự commit chung một transaction**.

Một marker boolean `seen=true` không đủ thông tin. Thiết kế một **state machine**:

~~~mermaid
stateDiagram-v2
    [*] --> PROCESSING: Claim key
    PROCESSING --> SUCCEEDED: Remote confirmed
    PROCESSING --> RETRYABLE: Known transient error
    PROCESSING --> UNKNOWN: Lost response / timeout
    RETRYABLE --> PROCESSING: Safe retry
    UNKNOWN --> RECONCILING: Query remote
    RECONCILING --> SUCCEEDED: Remote confirmed
    RECONCILING --> PROCESSING: Confirmed not executed
    PROCESSING --> FAILED_FINAL: Non-retryable failure
~~~

Kiểu domain minh họa:

~~~java
import java.time.Instant;

public enum OperationState {
    PROCESSING,
    SUCCEEDED,
    RETRYABLE,
    UNKNOWN,
    FAILED_FINAL
}

public record ProcessingRecord(
        EventDedupKey key,
        String fingerprint,
        OperationState state,
        String ownerToken,
        Instant leaseUntil,
        int attempt,
        String remoteOperationId,
        String businessReceipt
) {}
~~~

Các `public` types ở code block cần source file riêng; đây là domain model ví dụ, không phải API có sẵn của Spring Integration.

### 17.1. Quy trình thực tế

1. **Claim key** với insert-if-absent/CAS nguyên tử.
2. Lưu `PROCESSING` kèm `ownerToken` và `leaseUntil`.
3. Gọi remote API với **idempotency key ổn định** nếu có hỗ trợ.
4. Khi xác nhận chắc chắn thành công, CAS state sang `SUCCEEDED` và lưu receipt.
5. Nếu timeout không rõ remote đã làm chưa, chuyển `UNKNOWN` và **reconcile**.
6. Không retry mù một side effect không idempotent.
7. ACK/requeue message theo trạng thái bền vững và delivery contract.

### 17.2. Duplicate đến trong các trạng thái

| State hiện tại | Hành vi gợi ý |
|---|---|
| `SUCCEEDED` | Trả receipt/no-op và ACK |
| `PROCESSING` lease còn | IN_PROGRESS, wait hoặc retry sau |
| `PROCESSING` lease hết | Takeover bằng CAS, kiểm tra outcome |
| `UNKNOWN` | Reconcile bằng remote idempotency key |
| `RETRYABLE` | Retry có backoff và ownership |
| `FAILED_FINAL` | Trả lỗi được lưu hoặc reject theo contract |
| Cùng key nhưng fingerprint khác | Reject conflict, không chạy như mới |

**Đừng mặc định một duplicate `PROCESSING` tương đương `SUCCEEDED`** và ACK như đã hoàn thành. Nó có thể là một tác vụ đang mắc kẹt.

## 18. Lease, CAS và fencing

Một worker có thể chết sau khi claim `PROCESSING`. Đặt `leaseUntil` giúp worker khác takeover khi hết hạn, nhưng cần ngăn hai worker cùng gây side effect.

~~~text
t0: Worker A claims, lease 60s
t1: Worker A bị treo
t2: Lease A hết hạn
t3: Worker B takeover
t4: Worker A tỉnh lại và tiếp tục gửi remote request
~~~

Lease **không đủ** bảo đảm mutual exclusion nếu worker A vẫn chạy sau khi mất lease.

### 18.1. CAS theo ownership

~~~sql
UPDATE processing_command
SET owner_token = :newOwner,
    lease_until = :newLeaseUntil,
    attempt = attempt + 1
WHERE tenant_id = :tenantId
  AND command_id = :commandId
  AND state = 'PROCESSING'
  AND lease_until < CURRENT_TIMESTAMP
  AND owner_token = :oldOwner;
~~~

Chỉ worker update **đúng một row** theo CAS mới được coi là owner mới. Khi hoàn tất, CAS `PROCESSING → SUCCEEDED` phải xác nhận owner/version chưa đổi.

### 18.2. Fencing token

Khi downstream resource hỗ trợ, gửi một **fencing number tăng đơn điệu**. Resource từ chối lệnh từ worker có fencing number cũ. Nếu remote không hỗ trợ fencing, dùng **remote idempotency key** hoặc reconciliation. `ownerToken` dạng UUID chỉ giúp phân biệt worker nội bộ, không tự chặn remote side effect đến muộn.

## 19. Remote API idempotency

Với thanh toán hoặc tạo shipment, nên dùng idempotency contract của hệ thống đích nếu có:

~~~text
POST /charges
Idempotency-Key: tenant-a/charge-cmd-1001

{
  "accountId": "ACC-1001",
  "amountMinorUnits": 25000,
  "currency": "VND"
}
~~~

Đây là giao thức **minh họa**, không phải khẳng định mọi API hỗ trợ header này. Cần kiểm tra key scope, retention, xử lý same key/different body, pending response và replay behavior của nhà cung cấp.

### 19.1. Lost response không chứng minh thất bại

~~~mermaid
sequenceDiagram
    participant C as Consumer
    participant R as Remote API
    participant S as State Store

    C->>S: PROCESSING
    C->>R: POST với Idempotency-Key K
    R-->>C: Remote commit thành công
    Note over C: Response mất do network
    C->>S: UNKNOWN
    C->>R: Query status hoặc retry K theo contract
    R-->>C: Receipt của thao tác đã hoàn tất
    C->>S: SUCCEEDED + receipt
~~~

Đừng làm:

~~~java
try {
    remoteCharge();
} catch (Exception ex) {
    metadataStore.remove(key); // SAI nếu remote đã commit.
    throw ex;
}
~~~

Exception có thể là timeout **sau** khi remote đã thực hiện. Xóa marker ngay sẽ cho phép retry tạo tác dụng lặp. Nếu API không hỗ trợ idempotency hoặc status query, cần reconciliation/manual intervention khi outcome không rõ.

## 20. Transactional outbox và inbox

Nếu business action gồm **ghi DB local và phát event tới broker**, quy trình sau có crash window:

~~~text
UPDATE database -> COMMIT -> broker.publish()
~~~

Crash sau DB commit nhưng trước publish làm mất event. **Transactional outbox** giải quyết bằng cách ghi event cần phát trong cùng local transaction.

~~~mermaid
flowchart LR
    IN["Incoming event"] --> TX["DB Transaction"]
    TX --> M["Insert dedup/inbox row"]
    TX --> B["Update business state"]
    TX --> O["Insert outbox event"]
    O --> COMMIT["COMMIT"]
    COMMIT --> PUB["Outbox publisher"]
    PUB --> BROKER["Broker"]
~~~

SQL đơn giản:

~~~sql
CREATE TABLE outbox_event (
    id            UUID PRIMARY KEY,
    aggregate_id  VARCHAR(160) NOT NULL,
    event_type    VARCHAR(120) NOT NULL,
    payload_json  TEXT NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    published_at  TIMESTAMPTZ NULL
);
~~~

Khi inbox marker, business update và outbox entry cùng transaction, chúng có thể commit nguyên tử. Outbox publisher vẫn có thể **gửi trùng** nếu đã publish nhưng crash trước khi mark sent, nên consumer phía sau cũng phải idempotent.

~~~text
Broker input (at least once)
  -> Inbox unique key + local DB transaction
  -> Business mutation + outbox record
  -> Outbox publisher
  -> Broker (có thể redelivery)
  -> Idempotent receiver ở downstream
~~~

Không có "exactly-once xuyên toàn hệ thống" chỉ nhờ dùng một interceptor hoặc outbox ở một service.

## 21. Broker ACK: nên sau business commit

### 21.1. ACK trước commit

~~~text
ACK broker -> business action -> DB commit
~~~

Crash sau ACK nhưng trước DB commit có thể khiến broker không redeliver: **lost work**.

### 21.2. ACK sau commit

~~~text
DB commit -> ACK broker
~~~

Crash sau commit nhưng trước ACK có thể gây redelivery: **cần dedup/idempotency**, nhưng business state đã được bảo vệ bởi unique inbox row và local transaction.

### 21.3. Những điều cần kiểm tra

- Broker/adapter đang auto-ack hay manual-ack?
- ACK gắn với listener attempt nào?
- Transaction thực sự commit trước ACK không?
- Consumer có nhận lại message sau rebalance/partition không?
- Duplicate `SUCCEEDED` có được ACK không?
- Duplicate `PROCESSING` cần retry delay hay pending queue?
- DLQ replay còn giữ nguyên idempotency key không?

`MessageChannel.send()==true` không chứng minh DB đã commit hay broker ACK thành công.
## 22. Kiểm thử bằng fault injection

Không chỉ gửi cùng message hai lần khi hệ thống khỏe mạnh. Một bộ test đáng tin phải chủ động chèn lỗi đúng những điểm ranh giới.

| Điểm lỗi | Cách mô phỏng | Mark-before độc lập | Atomic DB transaction |
|---|---|---|---|
| Trước claim | Store unavailable | Không được chạy action khi claim chưa rõ | Rollback/no effect |
| Sau claim, trước action | Crash handler | Marker có thể làm skip sai | Marker rollback nếu transaction chưa commit |
| Trong action | UPDATE ném exception | Marker có thể vẫn tồn tại | Không còn mutation hoặc marker |
| Sau action, trước marker | Crash | Mark-after có thể gây duplicate | Không thể nửa commit nếu cùng transaction |
| Sau commit, trước ACK | Broker redelivery | Phụ thuộc marker/outcome | Unique ledger chặn effect trùng |
| Hai worker cùng key | Đồng bộ bằng barrier | Cần CAS | Unique constraint phân xử |
| Remote commit, lost response | Timeout | Outcome không xác định | Local DB không bao trùm remote |
| Lease expired, old worker trở lại | Pause/resume worker | Có thể side-effect trùng | Cần fencing/remote idempotency |
| Replay sau TTL | Xóa marker rồi gửi lại | Có thể chạy lại | Retention/business uniqueness policy |

### 22.1. Test minh họa rủi ro mark-before

~~~text
Arrange:
  MetadataStore trống
  Handler giả sẽ crash trước DB write

Act:
  send event -> selector lưu marker -> handler lỗi
  redeliver event với cùng key

Assert:
  marker tồn tại
  retry bị discard nếu advice dùng nullChannel
  business effect vẫn chưa xảy ra
~~~

Test này chứng minh **lỗ hổng thiết kế**, không phải hành vi được khuyến nghị. Trong production, một bài test an toàn phải **fail** khi một event quan trọng chưa được thực hiện nhưng đã bị ACK/drop như thể hoàn tất.

### 22.2. Test minh họa rủi ro mark-after

~~~text
Arrange:
  Business action và marker dùng hai commit độc lập

Act:
  business action thành công
  crash trước marker DONE
  redeliver same event

Assert:
  nếu action không idempotent, business action bị gọi lần hai
~~~

Không thể sửa lỗi này chỉ bằng cách gọi `MetadataStore.put` nhanh hơn sau handler. Một crash luôn có thể chen giữa hai commit độc lập.

### 22.3. Test transaction commit

~~~text
1. Tạo invoice_balance(initial=0).
2. apply(event) -> paid=25000, processed_event=1.
3. apply(event) lần hai -> paid=25000, processed_event=1.
4. apply(same key, different fingerprint) -> conflict.
5. Cho UPDATE fail sau INSERT -> marker rollback.
6. Retry sau khi sửa dữ liệu -> cập nhật đúng một lần.
7. Cho hai workers đồng thời -> một mutation duy nhất.
8. Sau commit, giả lập ACK mất -> replay không tăng balance.
~~~

Đây là những ca test nên chạy với database thật hoặc Testcontainers dùng DB tương thích production; mock `JdbcTemplate` không đủ chứng minh transaction/unique constraint.

## 23. Trả lại kết quả nhất quán cho Gateway/API

Một HTTP API có `Idempotency-Key` thường cần **trả cùng business response** cho request duplicate, chứ không chỉ ngăn side effect lặp.

Ví dụ hợp đồng:

~~~text
POST /orders/ORDER-101/submit
Idempotency-Key: cmd-1001

Lần đầu:
  201 Created
  orderStatus=SUBMITTED

Retry cùng key + cùng body:
  201 Created
  cùng orderId/result (theo contract)

Retry cùng key + body khác:
  409 Conflict hoặc lỗi contract

Key đang PROCESSING:
  202 Accepted + status URL
  hoặc retryable response theo contract
~~~

Các HTTP status trong ví dụ là **lựa chọn thiết kế**, không phải quy tắc bắt buộc của mọi API. Nếu cần response replay, hãy lưu receipt/result hoặc reference tới resource **cùng transaction với business state**.

Chỉ cấu hình `IdempotentReceiverInterceptor` gửi duplicate vào `nullChannel` có thể dẫn đến **Gateway timeout** nếu caller đang chờ một reply. Cần phân biệt message không được xử lý lại và request vẫn cần một response.

### 23.1. Fingerprint canonical

Không nhất thiết hash raw JSON bytes nếu thứ tự field/whitespace có thể thay đổi mà nghiệp vụ tương đương. Nên canonicalize các trường có ý nghĩa: operation, tenant, target resource, amount minor units, currency, version. Không include traceId, timestamp retry hoặc những giá trị đổi mỗi lần delivery.

### 23.2. Duplicate PROCESSING không được giả là thành công

Nếu attempt đầu còn chạy:

- Có thể trả `IN_PROGRESS` hoặc tracking URL.
- Có thể short-wait đến lúc attempt đầu hoàn tất.
- Có thể retry sau backoff.
- Không được trả `SUCCEEDED` nếu chưa có business receipt chắc chắn.
- Không được để hai attempts cùng gọi remote payment chỉ vì request đến gần nhau.

## 24. Retention và TTL của idempotency marker

Marker giữ mãi có chi phí lưu trữ. Marker hết hạn quá sớm lại làm replay của event cũ bị xử lý như event mới.

~~~text
t0: message được publish
t0+30 phút: normal retry
t0+7 ngày: replay từ DLQ
t0+30 ngày: manual recovery/reconciliation
~~~

Nếu TTL chỉ một giờ, event replay sau bảy ngày có thể vượt qua dedup store.

### 24.1. Những khoảng thời gian cần xét

- Broker retention và DLQ retention.
- Khả năng manual replay.
- Thời gian remote API giữ idempotency key.
- Business audit/compliance.
- Sự kiện có thể được tái phát từ lịch sử.
- Độ nguy hiểm nếu một side effect bị thực hiện thêm lần nữa.
- Chi phí metadata store và khả năng archive/tombstone.

### 24.2. Xóa marker DONE cần có lớp bảo vệ khác

Nếu cleanup xóa marker DONE, cần một business uniqueness constraint lâu dài hoặc một tombstone vẫn ngăn replay cũ. Xóa để tối ưu store không được thay đổi ý nghĩa của "event này đã tác động vào hóa đơn".

### 24.3. Tenant isolation

Key cần scope theo tenant/source/operation. Không để client tự khai `tenantId` khác principal đã xác thực để **chặn nhầm** event của tenant khác hoặc truy vấn outcome không thuộc quyền. Authorization phải nằm tại trust boundary, không chỉ trong logic chọn key.

## 25. Observability: tách claim và commit

| Metric | Điều cần quan sát |
|---|---|
| `idempotency_received_total` | Số messages nhận |
| `idempotency_first_claim_total` | Số lần claim key mới |
| `idempotency_duplicate_total` | Số key đã xuất hiện |
| `idempotency_processing_total` | Số task ở PROCESSING |
| `idempotency_succeeded_total` | Số business actions confirmed |
| `idempotency_retryable_failure_total` | Số lỗi có thể retry |
| `idempotency_unknown_total` | Số outcome chưa rõ |
| `idempotency_fingerprint_conflict_total` | Cùng key khác nội dung |
| `idempotency_lease_expired_total` | Lease hết hạn |
| `idempotency_takeover_total` | Worker khác takeover |
| `idempotency_reconciliation_total` | Đối soát external action |
| `idempotency_business_commit_latency_seconds` | Độ trễ business commit |

Ví dụ log:

~~~text
flow=invoice-payment
eventType=InvoicePaymentConfirmed
eventId=evt-pay-1001
tenant=tenant-a
idempotencyState=PROCESSING
claimResult=ACQUIRED
businessCommit=PENDING
traceId=trace-1001
~~~

**`claimResult=ACQUIRED` không nói business đã hoàn tất.** Cần ghi confirmed outcome tại đúng business boundary, ví dụ sau DB commit hoặc remote receipt đáng tin.

Đừng đưa `eventId`, account ID, customer ID hay idempotency key vào metric labels có cardinality cao. Nếu log cụ thể phải có identifier, dùng access control, redaction và retention phù hợp.

### 25.1. Dấu hiệu cần alert

- `PROCESSING` vượt lease và không có takeover/reconciliation.
- `UNKNOWN` tăng đột biến sau timeout remote API.
- Marker `SUCCEEDED` nhưng không có business record tương ứng.
- Business record đã commit nhưng marker không có.
- Cùng key mang nhiều fingerprint.
- Duplicate tăng sau broker rebalance.
- Khoảng từ claim tới action quá dài.
- Nhiều workers cùng key có stale owner/version.

## 26. Những anti-pattern thường gặp

| Sai lầm | Hậu quả | Khắc phục |
|---|---|---|
| Đánh dấu DONE rồi mới gọi business action | Crash → lost work | PROCESSING + recovery hoặc atomic transaction |
| Business xong rồi mới commit marker riêng | Crash → duplicate effect | Atomic transaction/remote idempotency |
| Nghĩ interceptor tự drop duplicate | Handler có thể vẫn chạy với header duplicate | Cấu hình discard/throw hoặc xử lý header |
| Coi duplicateMessage là SUCCEEDED | Attempt trước có thể thất bại | Kiểm tra outcome bền vững |
| Dùng get rồi put không CAS | Hai worker đều chạy | Unique constraint/CAS |
| Key = MessageHeaders.ID | Redelivery có ID mới | Stable event/command ID |
| Key = invoiceId | Chặn nhiều payment hợp lệ của cùng invoice | Scope theo event/command |
| Same key khác payload vẫn skip | Che conflict hoặc tấn công | Fingerprint validation |
| SimpleMetadataStore làm dedup production qua restart | Marker mất sau restart | Persistent metadata/DB inbox |
| Marker persistent nhưng side effect remote | Crash window vẫn có | Remote idempotency/reconciliation |
| Xóa marker trong catch timeout | Remote có thể đã commit | UNKNOWN/reconcile |
| ACK trước business commit | Lost work | ACK sau commit theo adapter |
| TTL ngắn hơn thời gian replay | Event cũ chạy lại | Retention/tombstone |
| Lease hết hạn là tự do gửi lại remote | Worker cũ vẫn có thể chạy | Fencing/remote idempotency |
| Chỉ test gửi duplicate hai lần | Không bắt lỗi crash | Fault injection/concurrency |
| HashSet trong một JVM | Không bảo vệ nhiều instances | Shared/DB unique |
| Drop duplicate API nhưng không trả result | Gateway timeout/inconsistent response | Stored receipt/reply path |
| Nghĩ transaction local bảo vệ remote side effect | Không atomic xuyên dịch vụ | Outbox/inbox/idempotent API |

## 27. Bài tập thực hành

**Bài 1 — Crash matrix.** Vẽ các điểm crash trước marker, sau marker, sau business action và trước broker ACK; so sánh before/after.

**Bài 2 — Selector.** Dựng `MetadataStoreSelector` với `SimpleMetadataStore`; chứng minh `accept()` ghi key trước khi handler chạy.

**Bài 3 — Advice mặc định.** Bỏ discard channel, cho handler nhận `Message<?>` và kiểm tra `duplicateMessage`; giải thích vì sao duplicate vẫn tới handler.

**Bài 4 — Discard.** Thêm `nullChannel`; gửi event hai lần, test handler chỉ gọi một lần. Cho lần đầu lỗi rồi redeliver để phơi bày lost-work.

**Bài 5 — Key scope.** Dùng invoiceId làm key và gửi hai payments hợp lệ; giải thích vì sao nó chặn sai.

**Bài 6 — Fingerprint conflict.** Cùng key với hai amount khác nhau: phải reject thay vì silent dedup.

**Bài 7 — Transaction.** Dùng PostgreSQL unique ledger và `@Transactional`; test một event redelivery không tăng balance hai lần.

**Bài 8 — Rollback.** Làm UPDATE invoice fail sau INSERT marker; xác nhận marker rollback và retry vẫn chạy.

**Bài 9 — Concurrency.** Hai connections cùng insert key; test chỉ có một mutation.

**Bài 10 — ACK lost.** DB commit rồi giả lập mất ACK; redelivery không tạo side effect mới.

**Bài 11 — Remote timeout.** API đã thực hiện charge nhưng response bị mất; dùng remote idempotency key/lookup để reconcile.

**Bài 12 — Lease takeover.** Worker A hết lease, B takeover, A tỉnh lại; xác định nơi cần fencing.

**Bài 13 — Outbox.** Cùng DB transaction ghi inbox, business state và outbox. Cho publisher gửi thành công nhưng không mark sent, xem downstream dedup.

**Bài 14 — Gateway.** Trả reply nhất quán cho duplicate SUCCEEDED, IN_PROGRESS và same-key-different-body.

**Bài 15 — TTL.** Replay từ DLQ sau một tuần trong khi marker TTL một ngày; thiết kế retention an toàn.

**Bài 16 — Monitoring.** Tạo metrics/log cho claim, commit, duplicate, UNKNOWN, reconciliation, stale PROCESSING và fingerprint conflicts.

### Câu hỏi tự kiểm tra

1. Đã thấy message có nghĩa business đã commit chưa?
2. Crash window nào làm mất việc với mark-before?
3. Crash window nào làm lặp tác dụng với mark-after?
4. `MetadataStoreSelector` dùng thao tác nào để nhận key mới?
5. `putIfAbsent` bảo đảm điều gì, không bảo đảm điều gì?
6. `IdempotentReceiverInterceptor` mặc định có drop duplicate không?
7. Khi nào cần discard channel hoặc throw exception?
8. `duplicateMessage=true` có chứng minh attempt trước SUCCEEDED không?
9. Vì sao MessageHeaders.ID không phù hợp cho nhiều loại retry?
10. Vì sao invoiceId có thể là idempotency key quá rộng?
11. Same key nhưng fingerprint khác cần làm gì?
12. Một transaction chung bảo vệ được những crash windows nào?
13. INSERT marker trước UPDATE trong cùng transaction có nghĩa commit marker trước không?
14. Vì sao phải phân biệt PROCESSING và SUCCEEDED?
15. Duplicate đến lúc PROCESSING có nên ACK như đã DONE không?
16. Lease hết hạn có ngăn worker cũ gọi API không?
17. Remote timeout có chứng minh action chưa xảy ra không?
18. Vì sao không nên remove marker ngay trong catch timeout?
19. Outbox bảo vệ vấn đề gì khi ghi DB và publish?
20. Vì sao outbox publisher vẫn có thể gửi trùng?
21. ACK trước commit có thể gây mất tác vụ ra sao?
22. TTL marker cần cân nhắc những nguồn replay nào?
23. HTTP duplicate cần trả gì ngoài việc không chạy lại?
24. Test nào chứng minh unique constraint và rollback hoạt động?
25. Vì sao chỉ test happy path duplicate không đủ?

## 28. Checklist triển khai

- [ ] Đã định nghĩa duplicate theo một business operation ổn định.
- [ ] Key scope theo tenant/source/operation và giữ nguyên qua replay.
- [ ] Có fingerprint validation khi cùng key nhưng payload khác.
- [ ] Đã phân biệt RECEIVED, PROCESSING, SUCCEEDED và UNKNOWN.
- [ ] Marker seen không được dùng làm bằng chứng business committed.
- [ ] Nếu cùng database, marker và side effect dùng **một transaction**.
- [ ] Database có unique constraint và test concurrency.
- [ ] Nếu remote side effect, có idempotency key hoặc reconciliation.
- [ ] Không dùng `get+put` không CAS cho nhiều workers.
- [ ] `IdempotentReceiverInterceptor` gắn vào đúng handler endpoint.
- [ ] Duplicate path rõ: header, discard hoặc exception.
- [ ] Không drop duplicate PROCESSING như đã SUCCEEDED nếu chưa có recovery.
- [ ] MetadataStore có atomicity/durability phù hợp.
- [ ] Retry bounded, backoff, DLQ và error flow được xác định.
- [ ] Không xóa key mù khi remote outcome UNKNOWN.
- [ ] ACK broker gắn với transaction/outcome đúng.
- [ ] Có lease, CAS, fencing hoặc remote idempotency khi takeover.
- [ ] Marker retention đủ qua replay window hoặc có business uniqueness.
- [ ] Downstream xử lý idempotent khi outbox/broker phát lại.
- [ ] Test crash trước action, sau action, trước ACK, concurrency.
- [ ] Test rollback, fingerprint conflict, remote timeout, lease expiry.
- [ ] Metrics tách claim, duplicate, committed, UNKNOWN, failure.
- [ ] Không để PII/key cardinality cao trong metric labels.
- [ ] Side effect quan trọng có reconciliation và audit trail.

## 29. Tổng kết

**Đánh dấu message trước hay sau business action** không chỉ là một lựa chọn cú pháp Spring Integration; đó là quyết định về **crash recovery, delivery guarantees và tính đúng đắn nghiệp vụ**.

Nếu đánh dấu trước và **commit marker riêng**, crash có thể khiến hệ thống **bỏ mất tác vụ**. Nếu thực hiện business action rồi **commit marker riêng sau đó**, crash có thể khiến **side effect bị làm hai lần**. `MetadataStoreSelector` ghi dấu bằng `putIfAbsent` khi selector chấp nhận key mới, **trước khi handler chạy**, nên phải hiểu crash window của nó. Ngoài ra, `IdempotentReceiverInterceptor` mặc định **không tự loại message duplicate**: nó có thể gắn `duplicateMessage=true` rồi vẫn chuyển tới handler nếu không cấu hình discard/exception.

Với side effect **trong cùng một database**, hãy dùng unique idempotency key, marker và business mutation **chung một transaction**. Với side effect **ở hệ thống bên ngoài**, thiết kế `PROCESSING/SUCCEEDED/UNKNOWN`, CAS/lease có recovery, remote idempotency hoặc reconciliation. Khi vừa ghi DB vừa gửi broker event, dùng transactional outbox và idempotent consumer. Luôn đặt ACK theo outcome phù hợp, giữ marker đủ lâu và test các crash points thực tế.

Những nguyên tắc này giúp Idempotent Receiver phối hợp với Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel và correlation trong **SPRING_INTEGRATION_PATTERN** để tạo luồng ít phụ thuộc, dễ mở rộng và có khả năng quan sát, kiểm chứng.

### Tài liệu tham khảo

- Spring Integration Reference — Idempotent Receiver: https://docs.spring.io/spring-integration/reference/handler-advice/idempotent-receiver.html
- Spring Integration Reference — Metadata Store: https://docs.spring.io/spring-integration/reference/meta-data-store.html
- Spring Integration Reference — Handling Message Advice: https://docs.spring.io/spring-integration/reference/handler-advice.html
- Spring Integration Reference — Java DSL: https://docs.spring.io/spring-integration/reference/dsl.html
- Spring Integration API — IdempotentReceiverInterceptor: https://docs.spring.io/spring-integration/api/org/springframework/integration/handler/advice/IdempotentReceiverInterceptor.html
- Spring Integration API — MetadataStoreSelector: https://docs.spring.io/spring-integration/api/org/springframework/integration/selector/MetadataStoreSelector.html
- Spring Integration API — ConcurrentMetadataStore: https://docs.spring.io/spring-integration/api/org/springframework/integration/metadata/ConcurrentMetadataStore.html
- Spring Integration API — SimpleMetadataStore: https://docs.spring.io/spring-integration/api/org/springframework/integration/metadata/SimpleMetadataStore.html
- Spring Framework Reference — Declarative Transaction Management: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html
- PostgreSQL — INSERT ON CONFLICT: https://www.postgresql.org/docs/current/sql-insert.html
- JUnit 5 User Guide: https://junit.org/junit5/docs/current/user-guide/





