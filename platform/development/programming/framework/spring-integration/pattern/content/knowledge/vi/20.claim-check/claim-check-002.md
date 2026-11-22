# Message chỉ giữ claim token

Trong các hệ thống tích hợp, một message có thể chứa tài liệu, ảnh, hóa đơn, hồ sơ hoặc nội dung rất lớn và nhạy cảm. Nhiều chặng trung gian chỉ cần biết **công việc nào đang chạy**, không cần nhìn thấy dữ liệu gốc. Truyền nguyên payload qua mọi Router, Filter, hàng đợi và handler có thể làm tăng chi phí serialization, bộ nhớ, thời gian truyền và nguy cơ lộ dữ liệu.

**Claim Check** là Enterprise Integration Pattern giúp **cất message gốc vào một kho rồi truyền một token tham chiếu thay cho payload gốc**. Trong Spring Integration, **Incoming Claim Check Transformer** lưu message vào `MessageStore` và phát một message mới có **UUID claim token làm payload**. **Outgoing Claim Check Transformer** dùng token để đọc lại message gốc khi downstream thực sự cần nội dung.

Bài **Message chỉ giữ claim token** thuộc chương **Claim check**, module **SPRING_INTEGRATION_PATTERN**. Module hướng tới xây dựng Enterprise Integration Patterns với Spring Integration, kết hợp Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel và correlation; đồng thời kiểm thử và quan sát các nhánh xử lý theo cách ít phụ thuộc, dễ mở rộng.

**Điểm quan trọng:** "chỉ giữ token" nói về **payload mới được đưa đi trong flow**. Không thể từ đó kết luận toàn bộ headers đã bị xóa, bản gốc đã biến mất khỏi hệ thống, hoặc bất kỳ người cầm token nào cũng được quyền lấy nội dung.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vòng đời **store → token → restore** của Claim Check.
2. Phân biệt `Message<DocumentRequest>` ban đầu với `Message<UUID>` sau check-in.
3. Hiểu Spring Integration lưu **message gốc**, không chỉ một chuỗi ID nghiệp vụ.
4. Dùng `claimCheckIn(MessageStore)` và `claimCheckOut(MessageStore, boolean)` bằng Java DSL.
5. Hiểu `removeMessage=false` mặc định và trường hợp cần `true`.
6. Viết integration test chứng minh payload giữa flow chỉ là UUID, sau đó lấy lại dữ liệu gốc.
7. Phân biệt token, business ID, trace ID và correlation ID.
8. Chọn `SimpleMessageStore` hoặc persistent `MessageStore` cho đúng vòng đời.
9. Thiết kế timeout, expiry, cleanup, retry, idempotency và xử lý token thất lạc.
10. Kiểm soát headers, authorization và bảo vệ dữ liệu dù message chỉ mang token.

## 2. Vấn đề: không phải endpoint nào cũng cần payload gốc

Giả sử ứng dụng nhận một yêu cầu xử lý tài liệu:

~~~text
Message<DocumentRequest>
  payload:
    documentId = DOC-1001
    customerId = CUST-21
    content = <nội dung rất lớn>
    classification = CONFIDENTIAL
  headers:
    traceId = trace-1001
    businessCorrelationId = DOC-1001
~~~

Flow phải phân loại công việc, đưa vào hàng đợi, audit rồi mới mở tài liệu. Chỉ handler cuối cùng cần `content`.

~~~mermaid
flowchart LR
    IN["Message<DocumentRequest>"] --> CI["Claim Check In"]
    CI --> STORE[("MessageStore")]
    CI --> TOKEN["Message<UUID token>"]
    TOKEN --> ROUTER["Router / queue / audit metadata"]
    ROUTER --> CO["Claim Check Out"]
    CO --> STORE
    CO --> OUT["Message<DocumentRequest>"]
    OUT --> HANDLER["Document Processor"]
~~~

Diễn giải:

- **Check-in** giữ một message chứa dữ liệu đầy đủ tại kho.
- **Token message** lưu hành giữa các endpoint, không chứa nội dung tài liệu ở payload.
- **Check-out** dùng token để tra lại message đã lưu.
- Việc không truyền payload lớn qua mọi channel **không tự bảo đảm** rằng headers không chứa dữ liệu nhạy cảm.

### 2.1. Hình ảnh tương tự nhận hành lý

| Claim Check | Ví dụ sân bay | Spring Integration |
|---|---|---|
| Dữ liệu gốc | Vali | Message chứa tài liệu |
| Điểm giữ | Quầy hành lý | MessageStore |
| Claim token | Thẻ nhận hành lý | UUID |
| Check-in | Gửi vali | ClaimCheckInTransformer |
| Check-out | Nhận lại vali | ClaimCheckOutTransformer |
| Không thấy đồ | Thẻ không truy xuất được | Missing-token/store failure |

Không phải ta "nén vali thành thẻ"; dữ liệu vẫn nằm tại một nơi khác, còn thẻ chỉ là tham chiếu.

## 3. "Message chỉ giữ token" nghĩa chính xác là gì?

Spring Integration tạo một **message mới** sau check-in, payload của nó là token:

~~~text
TRƯỚC
Message<DocumentRequest>
  payload = DocumentRequest(DOC-1001, ...)
  headers = traceId, businessCorrelationId, ...

STORE
MessageStore[token] = Message<DocumentRequest>

SAU CHECK-IN
Message<UUID>
  payload = token
  headers = metadata phù hợp theo cơ chế transformation
~~~

**Đúng:** payload hiện tại là `UUID`, không phải `DocumentRequest`.

**Sai:** mọi thông tin gốc đã bị xóa, mọi header mặc nhiên bị xóa hoặc bảo mật đã được giải quyết hoàn toàn.

### 3.1. Token là UUID, không phải documentId

Theo API của `ClaimCheckOutTransformer`, message dùng cho check-out có payload dạng `UUID`. Một `String` như `"DOC-1001"` hoặc `"4eab..."` không tự trở thành token có kiểu đúng.

~~~java
import java.util.UUID;
import org.springframework.messaging.Message;

void inspect(Message<?> afterCheckIn) {
    Object payload = afterCheckIn.getPayload();

    if (!(payload instanceof UUID token)) {
        throw new IllegalArgumentException(
                "CLAIM_TOKEN_MUST_BE_UUID");
    }

    System.out.println("Claim token acquired");
}
~~~

Code trên dùng `afterCheckIn` là message đã nhận từ token channel, không phải biến do Spring tự tạo. Không nên log trực tiếp token trong ví dụ production vì nó là một tham chiếu có thể nhạy cảm.

### 3.2. Spring lưu cả Message

`ClaimCheckInTransformer` nhận `Message<?>` và dùng `MessageStore` để lưu. Kho có thể giữ payload cùng metadata gốc. Một ứng dụng tự lưu `byte[]` vào object storage rồi truyền URL cũng đang áp dụng *ý tưởng* Claim Check, nhưng đó không phải hành vi mặc định giống hệt `ClaimCheckInTransformer`.

### 3.3. Headers cần kiểm soát riêng

Giả sử message ban đầu có:

~~~text
payload = DocumentRequest(...)
headers:
  traceId = trace-1001
  customerEmail = private@example.invalid
  Authorization = SECRET
~~~

Nếu token flow còn truyền các headers nhạy cảm qua broker khác, Claim Check vẫn có rủi ro lộ thông tin. Hãy thiết kế **header allowlist**, kiểm tra propagation qua endpoint thật, và tuyệt đối không coi Claim Check là giải pháp thay thế authorization hoặc encryption.

## 4. Vòng đời của token

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant IN as Check-in
    participant S as MessageStore
    participant T as Token flow
    participant OUT as Check-out
    participant D as Downstream

    P->>IN: Message<DocumentRequest>
    IN->>S: Lưu original message
    S-->>IN: UUID token
    IN->>T: Message<UUID>
    Note over T: Payload chỉ chứa token
    T->>OUT: Message<UUID>
    OUT->>S: Tra theo token
    S-->>OUT: Original Message
    OUT->>D: Message<DocumentRequest>
~~~

Những điều kiện cần cho happy path:

1. Store có sẵn và lưu thành công.
2. Token được chuyển đúng kiểu qua các channel/giao thức.
3. Check-out truy cập **cùng backend và namespace** với check-in.
4. Entry chưa bị xóa hoặc hết hạn.
5. Người hoặc service yêu cầu khôi phục đã qua kiểm soát quyền.
6. Downstream có thể đọc kiểu/schema payload gốc.

Một token hợp lệ về mặt cú pháp **không chứng minh** store hiện còn message.

## 5. Claim Check khác những EIP nào?

| Pattern | Trách nhiệm | Khác với Claim Check |
|---|---|---|
| **Claim Check** | Cất nội dung và gửi token tham chiếu | Khôi phục được message từ MessageStore |
| **Transformer** | Đổi biểu diễn payload/message | Không mặc nhiên giữ bản gốc tại store |
| **Content Enricher** | Bổ sung dữ liệu còn thiếu | Không chủ yếu thay payload bằng token |
| **Filter** | Cho qua hoặc loại message | Không tự làm cơ chế lưu/lấy dữ liệu |
| **Router** | Chọn channel đích | Không lưu/khôi phục bản gốc |
| **Splitter** | Tách message thành các phần | Không thay payload bằng tham chiếu |
| **Aggregator** | Gom nhiều message thành một kết quả | Cần nhóm và release strategy |
| **Gateway** | Request/reply | Có thể nằm trước/sau Claim Check |
| **Wire Tap** | Sao chép message sang nhánh khác | Có thể làm lộ payload nếu đặt trước check-in |

Claim Check phù hợp khi các bước giữa flow **không cần nội dung gốc**; nếu mọi handler đều phải đọc tài liệu, việc check-in rồi check-out liên tục có thể chỉ tăng chi phí.

## 6. Hai Transformer trong Spring Integration

Spring Integration cung cấp:

- `org.springframework.integration.transformer.ClaimCheckInTransformer`.
- `org.springframework.integration.transformer.ClaimCheckOutTransformer`.

### 6.1. Check-in: từ Message<T> sang Message<UUID>

~~~text
Message<T> --> ClaimCheckInTransformer --> Message<UUID>
                    |
                    +--> MessageStore[token] = Message<T>
~~~

Transformer tạo một claim token dựa trên thông điệp lưu trữ. Trong implementation hiện hành, token là UUID. Dữ liệu được cất riêng, không tự động được gửi tới mọi endpoint tiếp theo.

### 6.2. Check-out: từ Message<UUID> về dữ liệu gốc

~~~text
Message<UUID> --> ClaimCheckOutTransformer --> Message<T>
                    |
                    +--> MessageStore.lookup(token)
~~~

Khi token không có entry tương ứng, check-out ném lỗi; nó không nên tự dựng một tài liệu rỗng rồi coi đó là thành công.

### 6.3. removeMessage không mặc định bật

`removeMessage` ở check-out mặc định là **`false`**. Nếu không cấu hình xóa hoặc cleanup khác, message gốc có thể còn nằm trong store sau nhiều lần claim.

| Cấu hình | Nghĩa | Rủi ro cần xét |
|---|---|---|
| `removeMessage=false` | Có thể lấy lại nội dung nếu entry còn | Store tăng nếu không cleanup |
| `removeMessage=true` | Xóa entry khi claim | Retry/redelivery token có thể thất bại |
| TTL/cleanup riêng | Hết thời hạn thì xóa | Không được ngắn hơn thời gian queue chờ và replay cần thiết |

Cần xác định policy dựa vào nghiệp vụ; đừng bật xóa chỉ vì muốn làm sạch bộ nhớ mà chưa xem xét failure window.

## 7. Model Java 17: DocumentRequest

Để tập trung vào token, ta mô phỏng tài liệu bằng record chứa chuỗi nội dung. Trong hệ thống thật, payload có thể là file binary, blob hoặc object đã decode.

~~~java
public record DocumentRequest(
        String documentId,
        String customerId,
        String content,
        String classification
) {
    public DocumentRequest {
        if (documentId == null || documentId.isBlank()) {
            throw new IllegalArgumentException(
                    "DOCUMENT_ID_REQUIRED");
        }
        if (customerId == null || customerId.isBlank()) {
            throw new IllegalArgumentException(
                    "CUSTOMER_ID_REQUIRED");
        }
        if (content == null || content.isBlank()) {
            throw new IllegalArgumentException(
                    "CONTENT_REQUIRED");
        }
        if (classification == null
                || classification.isBlank()) {
            throw new IllegalArgumentException(
                    "CLASSIFICATION_REQUIRED");
        }
    }
}
~~~

Record không có setter, nên phù hợp với ví dụ message bất biến. Với `byte[]` hoặc collection mutable, chỉ khai báo record **không tự tạo deep immutability**. Cân nhắc defensive copy và snapshot tại ranh giới store.

### 7.1. Validation nằm ở đâu?

- **Trước check-in:** validate schema, size limit, quyền upload và những thông tin tối thiểu.
- **Giữa check-in/out:** có thể Filter/Router theo metadata **đã xác thực**, không cần đọc `content`.
- **Sau check-out:** validate nội dung chi tiết mà chỉ handler có quyền mới đọc.
- **Khi token thất lạc:** error flow riêng; không mặc nhiên coi như Filter rejection.

## 8. Java DSL: check-in và check-out dùng chung MessageStore

Spring Integration Java DSL có `claimCheckIn(MessageStore)` và `claimCheckOut(MessageStore, boolean)`. Cấu hình demo sau dùng `SimpleMessageStore` trong bộ nhớ để JUnit dễ kiểm tra.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.store.MessageStore;
import org.springframework.integration.store.SimpleMessageStore;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;

@Configuration
@EnableIntegration
public class ClaimCheckConfiguration {

    @Bean
    public MessageStore claimMessageStore() {
        return new SimpleMessageStore();
    }

    @Bean(name = "claims.in")
    public MessageChannel checkInInput() {
        return new DirectChannel();
    }

    @Bean(name = "claims.token")
    public PollableChannel tokenOutput() {
        return new QueueChannel();
    }

    @Bean(name = "claims.checkout")
    public MessageChannel checkOutInput() {
        return new DirectChannel();
    }

    @Bean(name = "claims.restored")
    public PollableChannel restoredOutput() {
        return new QueueChannel();
    }

    @Bean
    public IntegrationFlow checkInFlow(
            MessageStore claimMessageStore) {
        return IntegrationFlow.from("claims.in")
                .claimCheckIn(claimMessageStore)
                .channel("claims.token")
                .get();
    }

    @Bean
    public IntegrationFlow checkOutFlow(
            MessageStore claimMessageStore) {
        return IntegrationFlow.from("claims.checkout")
                .claimCheckOut(claimMessageStore, true)
                .channel("claims.restored")
                .get();
    }
}
~~~

Ở đây:

1. `claims.in` nhận message gốc.
2. `claimCheckIn(store)` lưu message và phát UUID token.
3. `claims.token` là QueueChannel test fixture chứa message token.
4. `claims.checkout` nhận UUID để lấy lại dữ liệu.
5. `claimCheckOut(store, true)` khôi phục và **xóa entry** theo lựa chọn claim once.
6. `claims.restored` nhận message được phục hồi.

**Lưu ý:** Đây là demo với `removeMessage=true`, không phải cấu hình duy nhất. Nếu cần replay, hãy cân nhắc `claimCheckOut(store, false)` cùng chính sách cleanup khác.

### 8.1. Vì sao hai endpoint phải dùng cùng store?

~~~text
ĐÚNG
  Claim Check In  --> Store A
  Claim Check Out <-- Store A

SAI
  Claim Check In  --> Store A
  Claim Check Out <-- Store B
~~~

Hai store có cùng class hoặc bean name trên **hai JVM khác nhau** không tự chia sẻ dữ liệu. Với cross-instance, cần một backend chung hoặc cơ chế định tuyến cùng instance có quản lý lifecycle thích hợp.

### 8.2. XML namespace tương ứng

~~~xml
<int:claim-check-in
    id="checkin"
    input-channel="claimsIn"
    output-channel="claimsToken"
    message-store="claimMessageStore"/>

<int:claim-check-out
    id="checkout"
    input-channel="claimsCheckout"
    output-channel="claimsRestored"
    message-store="claimMessageStore"
    remove-message="true"/>
~~~

Ví dụ XML giả định namespace `int` đã được khai báo trong Spring XML context hợp lệ; không phải một XML file độc lập. Dùng XML hoặc Java DSL theo dự án, không đăng ký hai endpoint trùng nhau.

## 9. Message gốc và message token

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

void submit(MessageChannel input) {
    DocumentRequest document = new DocumentRequest(
            "DOC-1001",
            "CUST-21",
            "Confidential document body",
            "CONFIDENTIAL");

    Message<DocumentRequest> original =
            MessageBuilder.withPayload(document)
                    .setHeader("traceId", "trace-1001")
                    .setHeader(
                            "businessCorrelationId", "DOC-1001")
                    .build();

    input.send(original);
}
~~~

Sau check-in:

- `MessageStore` giữ một message có payload `DocumentRequest`.
- `claims.token` nhận message mới có payload `UUID`.
- `DocumentRequest.content` **không** là payload của token message.
- Một check-out hợp lệ khôi phục payload gốc.

Đừng nhầm **`documentId`** (business ID) với **`UUID token`** (tham chiếu tới entry). Một document có thể được check-in lại và mang token mới; business ID nên ổn định cho idempotency và audit.

## 10. Integration test chứng minh token-only payload

Test cần chạy qua Spring channels thực. Không chỉ gọi transformer trực tiếp rồi giả định wiring là đúng.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.integration.store.MessageStore;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(classes = ClaimCheckConfiguration.class)
class ClaimCheckFlowTest {

    @Autowired @Qualifier("claims.in")
    MessageChannel in;

    @Autowired @Qualifier("claims.token")
    PollableChannel tokens;

    @Autowired @Qualifier("claims.checkout")
    MessageChannel checkout;

    @Autowired @Qualifier("claims.restored")
    PollableChannel restored;

    @Autowired
    MessageStore claimMessageStore;

    @Test
    void checkInUsesUuidPayloadAndCheckOutRestoresDocument() {
        DocumentRequest document = new DocumentRequest(
                "DOC-1001", "CUST-21",
                "Confidential document body",
                "CONFIDENTIAL");

        Message<DocumentRequest> original =
                MessageBuilder.withPayload(document)
                        .setHeader("traceId", "trace-1001")
                        .build();

        assertTrue(in.send(original));

        Message<?> tokenMessage = tokens.receive(1000);
        assertNotNull(tokenMessage);
        assertInstanceOf(UUID.class, tokenMessage.getPayload());
        assertNotEquals(document, tokenMessage.getPayload());

        UUID token = (UUID) tokenMessage.getPayload();
        Message<?> stored = claimMessageStore.getMessage(token);

        assertNotNull(stored);
        assertEquals(document, stored.getPayload());

        assertTrue(checkout.send(
                MessageBuilder.withPayload(token).build()));

        Message<?> claimed = restored.receive(1000);
        assertNotNull(claimed);
        assertEquals(document, claimed.getPayload());

        // Config dùng removeMessage=true.
        assertNull(claimMessageStore.getMessage(token));
        assertNull(tokens.receive(0));
        assertNull(restored.receive(0));
    }
}
~~~

Test chứng minh ba trạng thái:

| Thời điểm | Payload đọc được | Nơi chứa nội dung gốc |
|---|---|---|
| Trước check-in | `DocumentRequest` | Message input |
| Sau check-in | `UUID` | `MessageStore` |
| Sau check-out | `DocumentRequest` | Message output; entry store đã bị xóa trong demo |

**Không suy rằng headers đều biến mất** vì test chỉ assert payload. Nếu chính sách yêu cầu xóa PII khỏi token message, phải thêm kiểm thử riêng cho headers.

### 10.1. Test header propagation độc lập

~~~java
// Snippet minh họa trong test sau khi nhận tokenMessage:
Object traceId = tokenMessage.getHeaders().get("traceId");
Object correlation =
        tokenMessage.getHeaders().get("businessCorrelationId");
~~~

Đây là đoạn quan sát, không phải phương thức Java độc lập. Khi dữ liệu đi qua boundary ngoài, nên test cả **những header được phép** và **những header buộc không được tồn tại**.

## 11. Unit test validation của token

Bản thân Claim Check Transformer do Spring cung cấp; ứng dụng nên test policy kiểm soát token ở ingress.

~~~java
import java.util.UUID;

public final class ClaimTokenPolicy {

    public UUID requireToken(Object payload) {
        if (!(payload instanceof UUID token)) {
            throw new IllegalArgumentException(
                    "CLAIM_TOKEN_MUST_BE_UUID");
        }
        return token;
    }
}
~~~

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.UUID;

import org.junit.jupiter.api.Test;

class ClaimTokenPolicyTest {

    private final ClaimTokenPolicy policy =
            new ClaimTokenPolicy();

    @Test
    void acceptsUuid() {
        UUID token = UUID.randomUUID();
        assertEquals(token, policy.requireToken(token));
    }

    @Test
    void rejectsDocumentIdString() {
        assertThrows(IllegalArgumentException.class,
                () -> policy.requireToken("DOC-1001"));
    }

    @Test
    void rejectsOriginalDocument() {
        DocumentRequest document = new DocumentRequest(
                "DOC-2001", "CUST-22",
                "Example body", "INTERNAL");
        assertThrows(IllegalArgumentException.class,
                () -> policy.requireToken(document));
    }
}
~~~

Validator chỉ xác nhận **kiểu payload**, không chứng minh token tồn tại hay người gửi có quyền lấy nội dung. Authorization phải dựa trên principal/tenant đã xác thực và metadata do server kiểm soát.

## 12. Luồng Router, Filter và queue chỉ nhận token

~~~mermaid
flowchart LR
    IN["DocumentRequest"] --> CI["Claim Check In"]
    CI --> ST[("MessageStore")]
    CI --> TK["Message<UUID>"]
    TK --> ROUTE{"Router theo trusted headers"}
    ROUTE --> Q["Token queue"]
    Q --> FILT{"Filter: quyền/trạng thái"}
    FILT --> CO["Claim Check Out"]
    CO --> ST
    CO --> PROC["Document handler"]
~~~

### 12.1. Router không thể đọc document.content từ UUID

Ví dụ một Router sau check-in lại đòi `DocumentRequest`:

~~~java
import org.springframework.integration.annotation.Router;

@Router(inputChannel = "claims.token")
public String route(DocumentRequest document) {
    return document.classification().equals("CONFIDENTIAL")
            ? "restricted"
            : "standard";
}
~~~

Đoạn này là **anti-pattern**: input channel đang mang `UUID`, không phải `DocumentRequest`.

Hai cách đúng:

1. Route **trước check-in** khi thật sự cần thuộc tính từ payload gốc.
2. Tính và đưa metadata **đáng tin cậy, tối thiểu** vào token message trước khi route.

Nếu classification cũng nhạy cảm, không mặc định rằng chuyển nó thành header là an toàn; cần kiểm soát nơi headers được gửi.

### 12.2. Filter sau check-in

Một Filter sau check-in có thể kiểm tra token format, trạng thái request hoặc quyền xử lý theo trusted metadata. Nó không thể đọc nội dung tài liệu nếu chưa check-out.

Khi Filter reject một token **trước check-out**, entry gốc vẫn có thể còn trong `MessageStore`. Cần một cleanup policy, nếu không sẽ gây rò rỉ dung lượng.

### 12.3. Queue bền vững và store không bền vững

Nếu token được gửi tới broker bền vững nhưng store gốc là `SimpleMessageStore` trong một JVM, sau restart queue có thể vẫn còn token mà message gốc đã mất. Tuổi thọ và durability của **token flow và store** cần được thiết kế nhất quán.
## 13. Chọn MessageStore: in-memory hay persistent?

`MessageStore` là abstraction lưu và truy xuất message trong Spring Integration. Việc dùng Claim Check **không tự động biến dữ liệu thành bền vững**: khả năng phục hồi phụ thuộc store được chọn.

| Giải pháp | Cách lưu | Khi nào phù hợp | Rủi ro |
|---|---|---|---|
| `SimpleMessageStore` | Trong bộ nhớ JVM, Map-based | Demo, unit/integration test, dữ liệu ngắn hạn có thể mất | Restart mất nội dung; tăng RAM |
| `JdbcMessageStore` | Cơ sở dữ liệu quan hệ qua JDBC | Cần lưu lâu hơn và chia sẻ backend | Schema, transaction, serializer, migration |
| `MessageStore` tùy biến | Do ứng dụng triển khai | Backend riêng và lifecycle chuyên biệt | Phải đáp ứng contract của Spring |
| Object storage + metadata store | Claim Check thiết kế riêng | File cực lớn, cross-service | Không đồng nhất với transformer mặc định |

### 13.1. Khi nhiều instance tham gia

~~~text
Instance A:
  Incoming Claim Check
       -> SHARED MESSAGE STORE
       -> UUID token -> broker

Instance B:
  broker -> UUID token
       -> SHARED MESSAGE STORE
       -> Outgoing Claim Check
~~~

Nếu A và B tạo hai `SimpleMessageStore` riêng, một token do A tạo sẽ không tự xuất hiện trong kho của B. Để hoạt động phân tán, cần backend chia sẻ hoặc một cơ chế key-based routing đưa token về nơi lưu dữ liệu.

### 13.2. Persistent store không xóa hết mọi vấn đề

Ngay cả với database:

- Dữ liệu cần được serialize/deserialize đúng kiểu.
- Schema Java và format lưu có thể thay đổi qua phiên bản deploy.
- Message headers có thể chứa object nội bộ không serializable.
- Transaction thêm entry và phát token có thể không đồng bộ với broker.
- Nếu giữ dữ liệu quá lâu, database tăng dung lượng liên tục.
- Nếu xóa entry khi consumer chưa commit, retry có thể mất khả năng khôi phục.

Cần kiểm thử cả **restart/recovery**, không chỉ happy path trong cùng một JVM.

### 13.3. Token không phải URL bên ngoài

Một hệ thống có thể tự thiết kế claim token là opaque ID trỏ tới blob trong object storage. Cách ấy có thể phù hợp cho file rất lớn, nhưng cần một adapter riêng và quyền truy cập. Không tự đưa URL vào `ClaimCheckOutTransformer` đang mong UUID token của Spring Integration rồi coi hai cơ chế là tương đương.

## 14. Chính sách xóa: false hay true?

### 14.1. Mặc định không xóa

~~~java
@Bean
IntegrationFlow reusableClaimFlow(MessageStore store) {
    return IntegrationFlow
            .from("claims.checkout.reusable")
            .claimCheckOut(store)
            .channel("claims.restored.reusable")
            .get();
}
~~~

Overload `claimCheckOut(store)` có `removeMessage=false`. Nếu cùng tài liệu cần được khôi phục nhiều lần bởi nhiều consumer, lựa chọn này có ích. Nhưng phải có retention/cleanup rõ ràng; nếu không, store trở thành một kho tích lũy mãi mãi.

### 14.2. Claim một lần và xóa entry

~~~java
@Bean
IntegrationFlow oneTimeClaimFlow(MessageStore store) {
    return IntegrationFlow
            .from("claims.checkout.once")
            .claimCheckOut(store, true)
            .channel("claims.restored.once")
            .get();
}
~~~

Đây là lựa chọn được dùng trong `ClaimCheckConfiguration` ở phần trước. Một lần check-out thành công lấy lại message đồng thời xóa entry theo chính sách.

### 14.3. Failure window khi xóa sớm

~~~mermaid
flowchart TD
    T["Nhận UUID token"] --> CO["Check-out remove=true"]
    CO --> ST["Entry bị xóa khỏi store"]
    ST --> DB["Business handler ghi DB"]
    DB --> F{"Commit thành công?"}
    F -->|Có| OK["Hoàn tất"]
    F -->|Không| R["Broker redelivery token"]
    R --> MISS["Không còn entry để claim"]
~~~

**Xóa khỏi MessageStore không có nghĩa handler đã hoàn tất business transaction.** Nếu retry dựa trên cùng token, remove=true có thể khiến lần thử sau thất bại. Tùy yêu cầu, giải pháp có thể là:

1. Giữ `removeMessage=false` trong giai đoạn cần replay, cleanup sau khi confirm processing.
2. Sử dụng transaction/ack phù hợp giữa store và consumer.
3. Dùng idempotency key bền vững để ngăn side effect trùng.
4. Thiết kế outbox/saga nếu nhiều hệ thống không chia sẻ một transaction.
5. Có một recovery path khi token không còn entry nhưng business state chưa rõ.

Không một lựa chọn nào mặc định bảo đảm exactly-once xuyên broker, store và database.

### 14.4. Bảng quyết định

| Nhu cầu nghiệp vụ | Hướng thiết kế |
|---|---|
| Một worker đọc đúng một lần; không replay | Có thể cân nhắc remove=true |
| Nhiều worker cần cùng payload | remove=false kèm cleanup |
| Token có thể được broker redeliver | Replay policy hoặc transaction/idempotency |
| Dữ liệu chỉ được giữ trong giới hạn thời gian | Retention/TTL có kiểm soát |
| Có luật lưu trữ chứng từ | Chọn policy phù hợp yêu cầu |
| Dữ liệu đặc biệt nhạy cảm | Least privilege, encryption và xóa đúng hạn |

## 15. Token bị thất lạc, sai kiểu hoặc hết hạn

Một token có hình dạng UUID không đảm bảo nó trỏ tới một message hiện có trong store.

| Tình huống | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Payload token là String | Serializer/adapter chuyển sai kiểu | Chuyển về UUID có validation hoặc reject |
| UUID chưa từng check-in | Token giả/sai namespace | Lookup failure/audit |
| UUID đã check-out với remove=true | One-time claim | Không replay thành công bằng cùng token |
| Entry bị TTL xóa | Lưu quá ngắn so với queue | Expired/recovery flow |
| Store tạm lỗi | Database/network outage | Retry giới hạn, backoff |
| Store không chia sẻ giữa instances | Wiring sai | Sửa backend/namespace |
| Entry không deserialize được | Schema/version mismatch | Compatibility/migration |
| Token thuộc tenant khác | Không có quyền | Deny/audit |
| Hai consumer claim cùng token | Race | Transaction/locking & policy |
| Payload lưu đã bị mutate | Object mutable/in-memory reference | Snapshot/immutability |

### 15.1. Thiếu token không phải Filter rejection

Một Filter trả `false` vì message hợp lệ không thuộc nhánh xử lý là **quyết định nghiệp vụ bình thường**. Không truy xuất được message do token sai, đã xóa hoặc store lỗi là **lỗi lookup/lifecycle**. Phân loại đúng giúp không che sự cố dữ liệu dưới metric "skipped".

### 15.2. Retry đúng loại lỗi

- Store timeout/network failure: có thể retry có giới hạn.
- Token sai kiểu hoặc sai format: không retry vô hạn.
- Token đã hết hạn hoặc bị xóa: retry cùng token không làm entry quay lại.
- Handler business lỗi sau check-out: cần policy có thể replay hoặc có bù trừ.
- Token không có quyền: không dùng retry để vượt authorization.

Trong `DirectChannel`, exception có thể nổi về sender. Trong flow bất đồng bộ, lỗi có thể đi qua error channel/adapter theo topology. **Không giả định mọi lỗi tự động được chuyển tới errorChannel chỉ vì có header này.**

## 16. Claim token có phải bí mật không?

Token là một **tham chiếu để tra dữ liệu**. UUID khó đoán hơn số tuần tự, nhưng **không phải cơ chế authentication hay authorization**. Nếu endpoint check-out nhận token từ người ngoài rồi trả nội dung mà không kiểm tra quyền, token có thể bị lạm dụng như bearer capability.

### 16.1. Những lớp bảo vệ cần có

1. **Authentication**: xác định người/service yêu cầu check-out.
2. **Authorization**: kiểm tra quyền xem nội dung tương ứng.
3. **Tenant isolation**: chỉ lookup dữ liệu thuộc tenant hợp lệ.
4. **Least privilege**: chỉ endpoint cần payload mới được đọc store.
5. **Encryption at rest/in transit**: bảo vệ bản gốc tại store và trên mạng.
6. **Audit**: theo dõi hành vi claim thành công/thất bại.
7. **Retention**: xác định khi nào phải xóa hoặc archive.
8. **No token leakage**: tránh token trong URL/log/metric công khai.

Một giải pháp cross-service có thể đặt **Claim Access Service** giữa token consumer và store để enforce quyền trước khi tra dữ liệu; không để client gửi arbitrary UUID trực tiếp tới một endpoint không được bảo vệ.

### 16.2. Payload token không đồng nghĩa dữ liệu an toàn

~~~text
Message:
  payload = UUID token
  headers:
    customerEmail = private@example.invalid
    rawContentPreview = ...
    accessToken = SECRET
~~~

Không cần payload gốc, những headers này vẫn có thể làm lộ dữ liệu. Hãy xác định **header allowlist** tại ranh giới channel/broker thay vì tin check-in tự loại mọi metadata.

### 16.3. Không log token tùy tiện

Claim token có cardinality cao và có thể là tham chiếu nhạy cảm. Trong metrics, dùng `flow`, `result`, `reasonCode`; trong logs/traces có kiểm soát, chỉ ghi token khi thực sự cần debug và có chính sách redaction/retention thích hợp.

## 17. Headers, traceId và correlation

Spring message có cả payload và headers. Claim Check chủ đích thay payload; metadata cần được quản lý riêng.

| Metadata | Vai trò | Nguyên tắc |
|---|---|---|
| `traceId` | Theo dõi các chặng | Giữ theo observability contract |
| `businessCorrelationId` | Gắn xử lý với tài liệu/đơn | Không đồng nhất với claim token |
| `replyChannel` | Đường phản hồi Gateway | Cẩn trọng qua broker/cross-JVM |
| `errorChannel` | Đường xử lý exception | Không copy mù đối tượng nội bộ |
| `tenantId` | Scope dữ liệu | Chỉ dùng sau xác thực |
| `contentType` | Loại payload | Có thể phải thay khi payload thành UUID |
| `MessageHeaders.ID` | ID instance | Không dùng làm business ID |
| `schemaVersion` | Format payload | Có thể cần hai version: stored message và token protocol |

### 17.1. contentType có thể không phù hợp sau check-in

Nếu message gốc khai `contentType=application/pdf`, nhưng payload sau check-in là UUID, adapter downstream có thể hiểu nhầm token là bytes PDF. Khi kết nối broker/HTTP, hãy xác định codec cho token message và mapping headers tương ứng. Không dùng header từ payload gốc mà không kiểm tra nghĩa mới.

### 17.2. Gateway reply và token

Một Gateway có thể gửi request và chờ reply. Nhưng nếu Claim Check In gửi token vào một broker, worker xử lý hàng phút, rồi Claim Check Out, `replyChannel` tạm từ request cũ có thể đã mất hiệu lực.

Mô hình phù hợp hơn cho xử lý dài hạn:

~~~text
POST /documents
  -> 202 Accepted + trackingId

DocumentRequest -> Check-in -> Token queue
  -> Worker -> Check-out -> Process
  -> DocumentProcessed event
  -> Status store

GET /documents/DOC-1001/status
  -> Trạng thái xử lý
~~~

`trackingId` của API là định danh workflow, không nhất thiết là UUID token nội bộ. Không đưa token cho client ngoài nếu không có chính sách quyền truy cập phù hợp.

### 17.3. businessCorrelationId khác claim token

Một nghiệp vụ có thể check-in nhiều lần và nhận nhiều token qua các vòng xử lý. Nếu dùng token làm idempotency key của toàn nghiệp vụ, cùng tài liệu có thể bị coi thành nhiều yêu cầu khác nhau. Giữ một `documentId`/`eventId` ổn định trong business state, tách khỏi khóa tra store.

## 18. Tính bất biến của payload lưu trữ

Một object Java có thể bị sửa ngoài ý muốn nếu payload hoặc trường lồng bên trong là mutable.

~~~java
public final class MutableDocument {
    private byte[] content;

    public MutableDocument(byte[] content) {
        this.content = content;
    }

    public byte[] getContent() {
        return content;
    }

    public void setContent(byte[] content) {
        this.content = content;
    }
}
~~~

Nếu object được chia sẻ giữa nhiều handler và một store trong bộ nhớ giữ tham chiếu, việc sửa `content` sau check-in có thể làm dữ liệu đọc ra khác bản mong đợi.

Khuyến nghị:

- Dùng DTO bất biến nếu có thể.
- Defensive copy cho mảng/collection mutable.
- Dùng serializer lưu snapshot phù hợp khi cần persistence.
- Với blob lớn, cân nhắc content checksum và immutability ở object storage.
- Kiểm tra schema/serialization compatibility sau upgrade.

Claim Check **không tự biến mọi payload thành immutable**.

## 19. Claim Check với Splitter và Aggregator

Nếu một message chứa `List<InvoiceLine>` được check-in trước rồi đi thẳng đến Splitter, Splitter chỉ thấy **UUID token**, không thấy collection gốc.

~~~text
List<InvoiceLine> -> Check-in -> UUID token -> Splitter
                                         (không còn List để split)
~~~

Hai vị trí dùng Claim Check thường gặp:

### 19.1. Split rồi check-in từng part

~~~mermaid
flowchart LR
    IN["Batch<List<Line>>"] --> SP["Splitter"]
    SP --> CI["Check-in từng part"]
    CI --> Q["Token queue"]
    Q --> CO["Check-out"]
    CO --> AG["Aggregator"]
~~~

Ưu điểm: mỗi part không cần mang payload lớn trên queue. Nhược điểm: tạo nhiều entries trong store; correlation/sequence headers cần được giữ để Aggregator gom đúng. **Mỗi part có thể có một token riêng nhưng cùng business correlation key.**

### 19.2. Aggregate rồi check-in output lớn

~~~mermaid
flowchart LR
    M["N parts"] --> AG["Aggregator"]
    AG --> D["Aggregate payload lớn"]
    D --> CI["Check-in"]
    CI --> STORE[("MessageStore")]
    CI --> Q["Token queue"]
    Q --> CO["Check-out"]
~~~

Hợp lý khi đầu ra của một group lớn nhưng nhiều bước tiếp theo chỉ cần tracking metadata. Không dùng token riêng của từng part làm `correlationId` để thay business group key.

### 19.3. Filter loại token có thể để lại entry

~~~text
Original -> Check-in -> Token -> Filter rejects
                             -> Không có check-out
                             -> Original vẫn ở MessageStore
~~~

Nếu message bị loại trước check-out, phải có retention/cleanup phù hợp. Không xóa vội nếu một nhánh Publish–Subscribe khác vẫn đang dùng cùng token.

## 20. Đo dung lượng, độ trễ và cleanup

MessageStore không phải kho vô hạn không cần vận hành. Một hệ thống nhiều tài liệu lớn cần theo dõi:

| Metric | Mục đích |
|---|---|
| `claim_check_in_total` | Số message cất vào store |
| `claim_check_out_total` | Số message được claim |
| `claim_check_lookup_failure_total` | Token không tìm thấy hoặc lỗi lookup |
| `claim_check_store_entries` | Số entry còn lưu |
| `claim_check_store_bytes` | Dung lượng đang dùng |
| `claim_check_entry_age_seconds` | Tuổi entry |
| `claim_check_expired_total` | Số entry bị expiry |
| `claim_check_cleanup_failure_total` | Lỗi cleanup |
| `claim_check_restore_latency_seconds` | Độ trễ khôi phục |
| `claim_check_access_denied_total` | Truy cập không được phép |

### 20.1. TTL phải tương thích queue backlog

Nếu store giữ 5 phút nhưng token được xử lý ở broker sau 30 phút, consumer nhận UUID hợp lệ về format mà không còn entry. Retention cần được chọn theo **thời gian queue chờ tối đa, retry, dead-letter và recovery window**, hoặc có expired-token flow được công bố rõ.

### 20.2. Không đồng nhất remove=true với policy retention đầy đủ

Dữ liệu có thể tồn tại ở backup, replica và log dù entry chính bị xóa. Với dữ liệu cá nhân hoặc chứng từ, cần chính sách retention/xóa phù hợp hệ thống, không chỉ một cấu hình của transformer.

### 20.3. Log structured nhưng hạn chế dữ liệu

~~~text
flow=document-claim
operation=CHECK_OUT
documentId=DOC-1001
claimResult=SUCCESS
storeBackend=jdbc
durationMs=24
traceId=trace-1001
~~~

Ví dụ này không chứa payload tài liệu hoặc token. Nếu `documentId` cũng nhạy cảm, log phải tuân theo chính sách bảo vệ identifiers.

## 21. Các lỗi thường gặp

### Lỗi 1 — Nghĩ check-in chỉ thêm header token

**Triệu chứng:** Router phía sau vẫn cố nhận `DocumentRequest`, trong khi payload đã là UUID.

**Khắc phục:** kiểm tra kiểu payload sau check-in và cập nhật contract endpoint.

### Lỗi 2 — Nghĩ mọi header biến mất

**Triệu chứng:** token message vẫn mang PII/authorization trong headers.

**Khắc phục:** thiết kế header allowlist và test propagation.

### Lỗi 3 — Token là String nhưng check-out mong UUID

**Triệu chứng:** adapter đã serialize UUID thành String nhưng không decode trước check-out.

**Khắc phục:** có converter String → UUID tại boundary, validation và test.

### Lỗi 4 — Hai endpoints dùng hai stores khác nhau

**Triệu chứng:** UUID trông hợp lệ nhưng lookup luôn fail.

**Khắc phục:** kiểm tra backend/namespace và bean wiring thực.

### Lỗi 5 — Dùng SimpleMessageStore cho cross-instance

**Triệu chứng:** instance B không có message do instance A check-in.

**Khắc phục:** shared/persistent store hoặc key routing phù hợp.

### Lỗi 6 — Xóa sớm khiến retry thất bại

**Triệu chứng:** check-out remove=true, handler lỗi, broker redelivery nhưng entry đã mất.

**Khắc phục:** transaction/replay policy, hoặc remove=false kèm cleanup sau business success.

### Lỗi 7 — Không cleanup nên memory tăng

**Triệu chứng:** `SimpleMessageStore` giữ entry từ mọi check-in.

**Khắc phục:** remove=true khi thích hợp hoặc TTL/retention/cleanup rõ ràng.

### Lỗi 8 — Dùng token làm quyền truy cập

**Triệu chứng:** ai có UUID cũng xem được tài liệu từ public API.

**Khắc phục:** authentication, authorization, tenant isolation, audit.

### Lỗi 9 — Broker durable nhưng store không durable

**Triệu chứng:** restart mất dữ liệu gốc dù token còn trên queue.

**Khắc phục:** kiểm soát durability/lifecycle của cả hai bên.

### Lỗi 10 — Giữ contentType cũ

**Triệu chứng:** adapter cố deserialize token như tài liệu PDF/JSON gốc.

**Khắc phục:** thiết kế codec/token message schema rõ ràng.

### Lỗi 11 — Filter reject token không cleanup

**Triệu chứng:** không check-out nên stored message bị bỏ quên.

**Khắc phục:** cleanup theo outcome, lưu ý còn consumer khác cần token.

### Lỗi 12 — Token thay thế business ID

**Triệu chứng:** check-in lại một tài liệu tạo token mới khiến downstream hiểu là nghiệp vụ khác.

**Khắc phục:** giữ documentId/eventId ổn định để idempotency.

### Lỗi 13 — Check-out thành công bị hiểu là business hoàn tất

**Triệu chứng:** ghi DONE ngay khi lấy lại message, dù handler sau đó chưa commit.

**Khắc phục:** đo business result ở downstream.

### Lỗi 14 — Store entry chứa object mutable

**Triệu chứng:** dữ liệu khôi phục khác nội dung thời điểm check-in.

**Khắc phục:** immutable DTO, defensive copy hoặc serialized snapshot.

## 22. Bài tập thực hành

**Bài 1 — Kiểm tra token:** gửi `DocumentRequest` vào `ClaimCheckConfiguration`, assert token channel nhận payload `UUID`, không phải `DocumentRequest`.

**Bài 2 — Kiểm tra store:** lấy UUID từ output rồi gọi `MessageStore.getMessage(token)`, xác nhận message gốc có nội dung đúng.

**Bài 3 — Check-out:** gửi token vào channel checkout, xác nhận payload được phục hồi; với remove=true, entry sau đó không còn.

**Bài 4 — Claim nhiều lần:** tạo flow `claimCheckOut(store, false)`, thử claim lại; đề xuất cleanup policy cho trường hợp này.

**Bài 5 — Token sai:** gửi String document ID, rồi UUID chưa được check-in; phân biệt lỗi kiểu payload và lỗi lookup.

**Bài 6 — Headers:** gửi input có traceId và custom sensitive header, kiểm tra token message rồi thiết kế allowlist trước khi phát qua broker.

**Bài 7 — Router:** route theo classification đã xác minh, chỉ dùng metadata tối thiểu sau check-in; không giả định Router có quyền đọc content từ UUID.

**Bài 8 — Filter reject:** cho Filter loại một token trước check-out, xác định nơi cleanup stored message mà không ảnh hưởng consumer khác.

**Bài 9 — Retry:** làm handler lỗi sau check-out(remove=true), xác định failure window và đề xuất policy phục hồi.

**Bài 10 — Multi-instance:** check-in trên JVM A, check-out trên JVM B, giải thích vì sao hai SimpleMessageStore riêng không hoạt động.

**Bài 11 — TTL:** token có thể nằm trong queue 30 phút và retry 2 giờ; thiết kế retention, expired-token outcome và metric.

**Bài 12 — Security:** mô phỏng user của tenant B cầm UUID token của tenant A, thiết kế authorization trước khi đọc store.

**Bài 13 — Splitter/Aggregator:** split batch thành ba part, check-in từng part, kiểm tra correlation metadata và không nhóm theo UUID token.

**Bài 14 — Object storage:** thiết kế một Claim Check tùy biến cho blob cực lớn, so sánh với MessageStore có sẵn.

### Câu hỏi tự kiểm tra

1. Claim Check khác nén payload như thế nào?
2. Spring Claim Check In lưu message hay chỉ payload?
3. Payload sau check-in là kiểu gì?
4. Token có được mặc nhiên đưa vào header thay vì payload không?
5. Vì sao "chỉ token" không có nghĩa mọi header đã bị loại?
6. Claim token khác documentId, traceId, correlationId thế nào?
7. Check-out cần điều kiện gì để truy xuất thành công?
8. `removeMessage` mặc định là true hay false?
9. Khi nào remove=true làm retry thất bại?
10. SimpleMessageStore có bền vững qua restart không?
11. UUID token có tự cấp quyền xem tài liệu không?
12. Nếu token qua JSON thành String, cần làm gì trước check-out?
13. Vì sao broker durable và store volatile là tổ hợp rủi ro?
14. Filter reject token trước check-out sẽ gây vấn đề storage nào?
15. Tại sao không để contentType=application/pdf cho mọi UUID token?
16. Check-out có chứng minh downstream DB đã commit không?
17. Cần metric nào để phát hiện store growth và lookup failure?
18. Trong Splitter/Aggregator, token có thể thay correlation key không?

## 23. Checklist triển khai

- [ ] Đã xác định rõ payload message gốc, entry trong store và UUID token payload.
- [ ] Check-in và check-out dùng cùng backend/namespace.
- [ ] Độ bền MessageStore phù hợp queue/retry/restart.
- [ ] Cấu hình removeMessage=true/false có chủ đích.
- [ ] Có TTL, retention, cleanup và quota store.
- [ ] UUID token được serialize/deserialize đúng kiểu qua giao thức.
- [ ] Không dùng token thay documentId/eventId.
- [ ] Có validation, authentication và authorization tại điểm check-out.
- [ ] Có tenant isolation, encryption và audit phù hợp.
- [ ] Có header allowlist, không để lộ PII/token qua log/metrics.
- [ ] Có quy tắc contentType/token message schema.
- [ ] Retry/ack/transaction không xóa dữ liệu trước khi có recovery path.
- [ ] Có idempotency ở handler có side effect.
- [ ] Có kiểm thử Spring Integration channels và MessageStore.
- [ ] Có test token sai, missing/expired, claim lần hai, restart.
- [ ] Có metric entry count, store bytes, token age, restore latency.
- [ ] Khi dùng Splitter/Aggregator, correlation/sequence headers vẫn hợp lệ.
- [ ] Có chính sách cleanup khi token bị Filter reject.
- [ ] Có retention/xóa dữ liệu đúng yêu cầu tuân thủ.

## 24. Tổng kết

**Message chỉ giữ claim token** là cách nói ngắn của Claim Check: **message mới lưu hành trong luồng chỉ có UUID token làm payload**, còn **message gốc được lưu tại MessageStore** để khôi phục sau. `ClaimCheckInTransformer` thực hiện check-in, `ClaimCheckOutTransformer` thực hiện check-out. Chúng có thể được cấu hình bằng Java DSL `claimCheckIn(store)` và `claimCheckOut(store, removeMessage)`.

Không được hiểu token-only payload là mọi headers đã sạch hoặc hệ thống đã tự giải quyết bảo mật. `removeMessage=false` là giá trị mặc định; bật true hữu ích cho claim-once nhưng có thể phá replay nếu downstream lỗi. Store lifecycle, cleanup, transaction, TTL, quyền đọc, business correlation và idempotency đều phải có thiết kế cụ thể.

Trong module **SPRING_INTEGRATION_PATTERN**, Claim Check giúp Router, Filter và các bước xử lý metadata vận chuyển **tham chiếu nhỏ thay vì payload lớn**, trong khi Transformer, Splitter/Aggregator, Gateway, retry và error channel vẫn có thể phối hợp theo những hợp đồng riêng. Hãy chỉ khôi phục dữ liệu tại điểm thực sự cần, kiểm thử token và store cùng nhau, và phân biệt rõ **đã claim** với **đã hoàn thành nghiệp vụ**.

### Tài liệu tham khảo

- Spring Integration Reference — Claim Check: https://docs.spring.io/spring-integration/reference/claim-check.html
- Spring Integration Reference — Message Store: https://docs.spring.io/spring-integration/reference/message-store.html
- Spring Integration Reference — Java DSL: https://docs.spring.io/spring-integration/reference/dsl.html
- Spring Integration API — ClaimCheckInTransformer: https://docs.spring.io/spring-integration/api/org/springframework/integration/transformer/ClaimCheckInTransformer.html
- Spring Integration API — ClaimCheckOutTransformer: https://docs.spring.io/spring-integration/api/org/springframework/integration/transformer/ClaimCheckOutTransformer.html
- Spring Integration API — BaseIntegrationFlowDefinition: https://docs.spring.io/spring-integration/api/org/springframework/integration/dsl/BaseIntegrationFlowDefinition.html
- Spring Integration API — MessageStore: https://docs.spring.io/spring-integration/api/org/springframework/integration/store/MessageStore.html
- Spring Integration API — SimpleMessageStore: https://docs.spring.io/spring-integration/api/org/springframework/integration/store/SimpleMessageStore.html
- Spring Integration Reference — Router: https://docs.spring.io/spring-integration/reference/router.html
- Spring Integration Reference — Aggregator: https://docs.spring.io/spring-integration/reference/aggregator.html
- JUnit 5 User Guide — JUnit Jupiter: https://junit.org/junit5/docs/current/user-guide/



