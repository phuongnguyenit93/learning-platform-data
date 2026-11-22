# Retry message với claim đã dùng

## 1. Tình huống: message được retry nhưng claim không còn dùng được

Trong một luồng đặt hàng, payload ban đầu chứa nhiều thông tin như mã đơn, danh sách dòng hàng, chi tiết khách hàng và thông tin vận chuyển. Ta không muốn chuyển toàn bộ payload lớn hoặc nhạy cảm qua mọi bước xử lý, nên áp dụng **Claim Check** — một Enterprise Integration Pattern (EIP):

1. Ghi payload/message gốc vào một **Message Store**.
2. Gửi tiếp một **claim check/token** nhỏ tham chiếu đến dữ liệu đã lưu.
3. Ở bước cần dùng dữ liệu, **claim-check out** để lấy lại payload/message.
4. Theo chính sách lưu trữ, dữ liệu có thể được giữ lại hoặc xóa khi đã lấy.

Vấn đề xuất hiện khi message bị gửi lại (**retry/redelivery**) sau khi claim đã được dùng hoặc đã bị xóa.

~~~text
T0  Claim Check In:
    lưu Message<Order> vào store, nhận claimId=C-100

T1  Gửi ClaimToken(C-100) tới downstream

T2  Claim Check Out:
    lấy Order từ C-100; cấu hình xóa khi lấy
    -> store không còn C-100

T3  Downstream gọi dịch vụ thanh toán, bị timeout

T4  Retry cùng ClaimToken(C-100)
    -> Claim Check Out tìm C-100
    -> NOT_FOUND / ALREADY_CONSUMED
~~~

Nếu chỉ bật retry quanh toàn flow, request có thể lặp lại bước **claim-check out** bằng cùng token nhưng dữ liệu đã bị tiêu thụ ở lần đầu. Lúc này **retry không còn tương đương chạy lại lần trước**: dữ liệu cần thiết đã biến mất.

~~~mermaid
flowchart TD
    I[Original Message] --> IN[Claim Check In]
    IN --> S[(Message Store)]
    IN --> T[ClaimToken C-100]
    T --> OUT[Claim Check Out]
    OUT --> S
    S -->|Payload tìm được| P[Process Order]
    OUT -->|Remove-on-read| RM[Claim bị xóa]
    P -->|Lỗi tạm thời| RET[Retry same token]
    RET --> OUT
    OUT -->|Lần sau không còn claim| ERR[Claim missing / already consumed]
~~~

**Câu hỏi trọng tâm:** Khi một message có thể được retry, **claim được lấy một lần hay nhiều lần**, và **lúc nào an toàn để đánh dấu hoàn tất/xóa dữ liệu gốc**?

Bài học thuộc chương **Claim check** trong module `SPRING_INTEGRATION_PATTERN`. Module tập trung học triển khai EIP với Spring Integration nhằm xây dựng luồng thông điệp ít phụ thuộc, dễ mở rộng; đồng thời thực hành Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel, correlation và kiểm thử/quan sát các nhánh xử lý.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích vòng đời **claim-in → token → claim-out → downstream → cleanup**.
2. Phân biệt **đọc claim**, **tiêu thụ claim**, **xác nhận thành công** và **xóa khỏi store**.
3. Dự đoán hậu quả khi retry với một claim đã bị remove, hết hạn, bị thu hồi hoặc đã hoàn tất.
4. Chọn chính sách **one-time claim**, **reusable until completion** hoặc **replay với claim mới** phù hợp nghiệp vụ.
5. Thiết kế idempotency, correlation, transaction/outbox, trạng thái hoàn tất và tombstone.
6. Viết Java/Spring Integration flow minh họa và kiểm thử trường hợp retry, duplicate, timeout, race, missing/expired claim.
7. Xử lý bảo mật, TTL, message store persistence, lỗi downstream và vận hành an toàn.

## 2. Các khái niệm phải tách biệt

### 2.1. Claim Check là một tham chiếu, không phải payload

Ví dụ một thông điệp vào:

~~~json
{
  "orderId": "ORD-1001",
  "customerId": "C-007",
  "amountVnd": 8500000,
  "items": [
    {"sku": "SKU-A", "quantity": 2},
    {"sku": "SKU-B", "quantity": 1}
  ]
}
~~~

Sau claim-check in, message tiếp theo có thể chỉ chứa:

~~~json
{
  "claimId": "C-100",
  "operationId": "PAY-ORD-1001"
}
~~~

Consumer nhận token phải **tra cứu nguồn lưu trữ có thẩm quyền** trước khi sử dụng dữ liệu gốc. Không có lý do để giả định token có thể tự tái tạo toàn payload. Claim ID cũng không tự là một **security capability** an toàn: nếu bất cứ ai biết ID đều có thể lấy dữ liệu, cần kiểm soát quyền truy cập, tenant và giới hạn tuổi thọ.

### 2.2. Những trạng thái thường bị nhầm với nhau

| Trạng thái | Nghĩa chính xác | Tác động đến retry |
|---|---|---|
| **STORED** | Payload đã được lưu và có claim ID. | Có thể đọc nếu chưa hết hạn/quyền hợp lệ. |
| **ISSUED** | Token đã được phát cho consumer. | Consumer chưa chắc nhận hoặc xử lý. |
| **READ** | Có consumer lấy được payload từ store. | Chưa đồng nghĩa thanh toán hay nghiệp vụ đã thành công. |
| **IN_PROGRESS** | Một worker đang xử lý payload. | Cần phân biệt retry và xử lý trùng. |
| **COMPLETED** | Business operation đã hoàn tất theo hợp đồng. | Redelivery nên trả trạng thái cũ/skip side effect. |
| **CONSUMED** | Chính sách one-time không còn cho dùng claim. | Reclaim cùng token có thể bị từ chối. |
| **EXPIRED** | Claim quá TTL/retention. | Phải xử lý lỗi hạn dùng, không xem như transient timeout. |
| **DELETED** | Dữ liệu vật lý đã bị xóa. | Không thể phục hồi từ store đó; cần durable replay source khác nếu muốn chạy lại. |
| **REVOKED** | Claim bị vô hiệu vì lý do bảo mật/nghiệp vụ. | Không tự tạo token mới để né thu hồi. |

**Đọc thành công không đồng nghĩa nghiệp vụ hoàn tất.** Nếu claim-check out xóa payload ngay khi đọc, một lỗi xảy ra *sau khi đọc* vẫn khiến retry thiếu dữ liệu.

### 2.3. Retry là hành động của tầng nào?

| Retry ở đâu? | Ví dụ | Có lặp claim-check out? |
|---|---|---|
| **Downstream handler** | Retry riêng HTTP payment sau khi đã khôi phục payload. | Không nhất thiết, nếu giữ payload trong context của lần xử lý. |
| **Integration endpoint** | RequestHandlerRetryAdvice quanh endpoint claim-out và handler. | Có thể có, tùy advice đặt trên endpoint nào. |
| **Broker redelivery** | Consumer crash trước ack và nhận lại claim token. | Thường có nếu flow khởi chạy lại từ token. |
| **Gateway caller retry** | HTTP client gửi lại cùng operation. | Có thể tạo claim/token mới hoặc dùng lại token, tùy thiết kế. |
| **Replay batch** | Operator chạy lại message từ event log. | Có thể phải tạo claim mới từ nguồn gốc đáng tin. |
| **Scheduled recovery** | Error flow chọn thử lại phần lỗi. | Phụ thuộc recovery payload có còn hay không. |

Không thể trả lời “retry có được không?” chỉ từ tên Claim Check; cần biết **đường retry bắt đầu tại đâu, token có sống tiếp không và payload gốc có được lưu bền vững ở đâu**.

## 3. Các chính sách sử dụng claim

### 3.1. One-time claim: đọc một lần, sau đó không đọc được

Một hệ thống muốn dữ liệu nhạy cảm chỉ được truy xuất một lần có thể thiết kế:

~~~text
AVAILABLE --(claim out thành công)--> CONSUMED
CONSUMED --(claim out lần nữa)-----> ALREADY_USED
~~~

Ưu điểm: giảm số lần đọc hợp lệ và có thể hạn chế tái sử dụng token. Nhược điểm: nếu downstream thất bại sau khi dữ liệu bị tiêu thụ, **không thể khôi phục bằng chính token đó** trừ khi có một cơ chế replay khác đã được thiết kế.

### 3.2. Reusable claim: giữ payload cho đến khi xử lý hoàn tất

~~~text
AVAILABLE --(read)--> AVAILABLE
AVAILABLE --(read lại sau retry)--> AVAILABLE
AVAILABLE --(business completion được xác nhận)--> COMPLETED
COMPLETED --(cleanup theo policy)--> DELETED/TOMBSTONE
~~~

Ưu điểm: retry có thể đọc lại payload khi worker fail hoặc broker redeliver. Nhược điểm: cần **retention/security/idempotency** vì nhiều consumer/lần thử có thể nhìn thấy cùng payload.

**Đọc lại cùng payload không được phép nhân đôi side effect.** Reusable claim chỉ giải quyết **khả năng truy xuất dữ liệu**, không giải quyết exactly-once execution.

### 3.3. Replay từ nguồn gốc bằng claim mới

Nếu claim cũ đã consumed/deleted và nghiệp vụ cho phép replay, có thể:

~~~text
Original durable event / authorized archive
    -> kiểm tra quyền & trạng thái operation cũ
    -> tạo claim mới C-200
    -> giữ business operationId phù hợp hoặc tạo phiên mới
    -> chạy lại theo policy
~~~

**Tuyệt đối không tạo lại payload bằng cách đoán** từ token hoặc từ những trường ít ỏi còn sót. Replay chỉ hợp lệ khi có **nguồn dữ liệu nguyên vẹn, đúng version, có quyền và chưa bị thu hồi**.

### 3.4. So sánh các lựa chọn

| Tiêu chí | One-time claim | Reusable until completion | Replay/new claim |
|---|---|---|---|
| Retry cùng token sau lần đọc đầu | Thường không. | Có thể nếu còn hạn/quyền. | Không; dùng claim mới. |
| Có thể mất payload trước downstream success | Có nếu consume sớm. | Ít rủi ro hơn nếu cleanup sau commit. | Cần nguồn replay bên ngoài store cũ. |
| Rủi ro dùng lại token ngoài ý muốn | Thấp hơn sau consume. | Cần kiểm soát quyền/TTL. | Cần kiểm soát phê duyệt replay. |
| Cần idempotency downstream | Vẫn cần. | Bắt buộc thực tế khi retry/redelivery. | Bắt buộc nếu operation có side effect. |
| Độ phức tạp | Semantics đơn giản, recovery khó. | State/cleanup/dedupe phức tạp hơn. | Workflow version/replay/authorization phức tạp hơn. |

**Khuyến nghị thiết kế cho bài tập:** dùng **reusable until completion**, tách bước “đọc payload” khỏi “đánh dấu hoàn tất”, rồi xử lý redelivery bằng business idempotency. Đồng thời kiểm tra rõ đường lỗi one-time/expired claim vì các hệ thống thực tế có thể chọn chính sách khác.

## 4. Spring Integration Claim Check và Message Store

### 4.1. Vai trò các thành phần

Trong Spring Integration, Claim Check pattern có thể được triển khai bằng thành phần **Claim Check In Transformer**, **Claim Check Out Transformer** và **Message Store**:

~~~mermaid
flowchart LR
    M["Message<Order>"] --> IN[Claim Check In]
    IN --> S[(Message Store)]
    IN --> ID["Message<ClaimId>"]
    ID --> RT[Router / Queue / Gateway]
    RT --> OUT[Claim Check Out]
    OUT --> S
    OUT --> REST["Restored Message<Order>"]
    REST --> H[Handler]
~~~

Một Transformer claim-in thường lưu message gốc trong Message Store rồi chuyển tiếp thông tin tham chiếu; transformer claim-out dùng tham chiếu để tìm lại message. **Khả năng giữ/xóa message tại bước claim-out phải được kiểm soát và xác minh bằng cấu hình của phiên bản đang dùng**, không được suy luận từ tên phương thức.

### 4.2. Cẩn thận với tùy chọn remove message

Một số biến thể Claim Check Out có cơ chế cấu hình **remove-on-get/removeMessage**. Hãy phân biệt:

- **Lookup không remove:** claim có thể còn để retry (nếu chưa expired/removed bởi process khác).
- **Lookup kèm remove:** claim trở thành one-time theo cơ chế store, retry cùng token dễ thiếu payload.
- **Delete thủ công sau xử lý:** cần biết handler thực sự hoàn tất hay chưa và side effect đã commit chưa.

**Đừng khẳng định mặc định của `removeMessage` là true hoặc false** nếu chưa đối chiếu tài liệu/API/version trong dự án; điều quan trọng là ghi rõ contract của flow đang triển khai và test hành vi bằng hai lần claim-out.

### 4.3. Message Store bền vững hay không?

Store có thể có tính chất khác nhau:

| Store | Lợi thế | Lưu ý với retry |
|---|---|---|
| In-memory Message Store | Cấu hình/kiểm thử đơn giản, latency thấp. | Process crash có thể làm mất payload. |
| JDBC-backed store | Có thể lưu bền vững, hỗ trợ transaction theo cấu hình. | Cần schema, serialization, cleanup, lock/transaction policy. |
| Store phân tán được hỗ trợ | Cho nhiều worker truy xuất. | Race, availability, consistency và TTL cần được xác minh. |
| Object store ngoài + metadata record | Hợp với payload lớn. | Cần bảo vệ object reference, checksum, lifecycle hai hệ thống. |

**Đã lưu vào một Message Store không đồng nghĩa đã đủ độ bền cho production**. Phải kiểm tra transaction, consistency, broker ack, TTL, serialization format, encryption và sự cố restart.

### 4.4. Hai ID rất dễ bị nhầm

- **Claim ID:** khóa tìm lại thông điệp đã lưu. Với một implementation dựa trên message ID, token có thể liên quan đến `MessageHeaders.ID` của message được store giữ.
- **Operation ID:** danh tính nghiệp vụ dùng để chống side effect trùng, ví dụ `CHARGE:ORD-1001`.

Nếu cùng operation được replay bằng claim mới, **claimId thay đổi nhưng operationId có thể vẫn giữ nguyên** khi mục đích là retry đúng cùng tác vụ. Nếu nghiệp vụ thật sự muốn tạo một operation mới, phải có chính sách/new operation ID minh bạch. Không dùng claim ID làm khóa idempotency duy nhất khi claim có thể được tạo lại.

## 5. Mô hình Java cho claim có thể retry

Để thấy rõ sự khác nhau giữa **đọc claim** và **tiêu thụ claim**, ta xây dựng một repository minh họa bằng Java 17. Ví dụ này **mô phỏng Claim Check pattern**, không thay thế lớp `MessageStore` của Spring Integration; code framework sẽ xuất hiện sau.

### 5.1. Payload gốc và ticket nhỏ

~~~java
import java.math.BigDecimal;
import java.time.Instant;

record OrderPayload(
        String orderId,
        String customerId,
        BigDecimal amountVnd) {
    OrderPayload {
        if (orderId == null || orderId.isBlank()
                || customerId == null || customerId.isBlank()
                || amountVnd == null
                || amountVnd.signum() <= 0) {
            throw new IllegalArgumentException("INVALID_ORDER_PAYLOAD");
        }
    }
}

record ClaimTicket(
        String claimId,
        String operationId,
        String tenantId) {
    ClaimTicket {
        if (claimId == null || claimId.isBlank()
                || operationId == null || operationId.isBlank()
                || tenantId == null || tenantId.isBlank()) {
            throw new IllegalArgumentException("INVALID_CLAIM_TICKET");
        }
    }
}

record StoredClaim(
        ClaimTicket ticket,
        OrderPayload original,
        Instant expiresAt) {
    StoredClaim {
        if (ticket == null || original == null
                || expiresAt == null) {
            throw new IllegalArgumentException("INVALID_STORED_CLAIM");
        }
    }
}
~~~

`ClaimTicket` có đủ thông tin để đối chiếu **claim ID, business operation và tenant**, nhưng bản thân các trường này **không thay thế xác thực/ủy quyền**. Khi dùng token trên wire, phải bảo vệ nó như một reference có thể dẫn đến dữ liệu nhạy cảm.

### 5.2. Repository có contract rõ về đọc và xóa

~~~java
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

interface ClaimRepository {
    void put(StoredClaim claim);
    Optional<StoredClaim> find(String claimId);
    Optional<StoredClaim> take(String claimId);
    boolean delete(String claimId);
}

final class InMemoryClaimRepository implements ClaimRepository {
    private final ConcurrentMap<String, StoredClaim> items =
            new ConcurrentHashMap<>();

    @Override
    public void put(StoredClaim claim) {
        if (items.putIfAbsent(
                claim.ticket().claimId(), claim) != null) {
            throw new IllegalStateException("DUPLICATE_CLAIM_ID");
        }
    }

    @Override
    public Optional<StoredClaim> find(String claimId) {
        return Optional.ofNullable(items.get(claimId));
    }

    @Override
    public Optional<StoredClaim> take(String claimId) {
        // Mô phỏng single-use: lấy và xóa bằng một map operation.
        return Optional.ofNullable(items.remove(claimId));
    }

    @Override
    public boolean delete(String claimId) {
        return items.remove(claimId) != null;
    }
}
~~~

Các thao tác `find`, `take` và `delete` cố tình **khác nhau**:

| Phương thức | Dữ liệu sau khi gọi thành công | Có thể retry cùng claim? |
|---|---|---|
| `find` | Vẫn nằm trong repository. | Có thể, nếu chưa expired/revoked. |
| `take` | Bị xóa ngay khi lấy. | Không từ repository này. |
| `delete` | Bị xóa không kèm trả payload. | Không từ repository này. |

`ConcurrentHashMap.remove` giúp phép lấy/xóa của **demo trong một JVM** có tính nguyên tử ở mức map operation. Nó **không đại diện** cho khả năng atomic consume của mọi persistent `MessageStore`, cũng không tạo một transaction bao trùm remote payment.

### 5.3. Mã lỗi phân biệt nguyên nhân

~~~java
enum ClaimFailureCode {
    NOT_FOUND,
    EXPIRED,
    ACCESS_DENIED,
    ALREADY_CONSUMED,
    INVALID_TICKET,
    STORE_UNAVAILABLE
}

final class ClaimAccessException extends RuntimeException {
    private final ClaimFailureCode code;

    ClaimAccessException(ClaimFailureCode code) {
        super(code.name());
        this.code = code;
    }

    ClaimFailureCode code() {
        return code;
    }
}
~~~

Một store trả về `null`/empty **không tự cho biết** claim đã bị consume, expired, deleted hay chưa từng tồn tại. Muốn phân biệt chính xác phải duy trì **state/tombstone hoặc audit metadata**. Vì vậy `NOT_FOUND` là lỗi quan sát được khi không có record; `ALREADY_CONSUMED` chỉ dùng khi hệ thống có bằng chứng trạng thái consumed.

### 5.4. Service đọc claim nhiều lần nhưng không xóa

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.Objects;
import java.util.UUID;

final class RetryableClaimService {
    private final ClaimRepository repository;
    private final Clock clock;

    RetryableClaimService(
            ClaimRepository repository, Clock clock) {
        this.repository = repository;
        this.clock = clock;
    }

    ClaimTicket issue(
            String operationId,
            String tenantId,
            OrderPayload original,
            Duration ttl) {
        Objects.requireNonNull(original, "original");
        if (ttl == null || ttl.isZero() || ttl.isNegative()) {
            throw new IllegalArgumentException("INVALID_CLAIM_TTL");
        }
        ClaimTicket ticket = new ClaimTicket(
                UUID.randomUUID().toString(),
                operationId,
                tenantId);
        repository.put(new StoredClaim(
                ticket,
                original,
                Instant.now(clock).plus(ttl)));
        return ticket;
    }

    OrderPayload restore(
            ClaimTicket ticket,
            String authenticatedTenantId) {
        if (ticket == null) {
            throw new ClaimAccessException(
                    ClaimFailureCode.INVALID_TICKET);
        }
        if (!ticket.tenantId().equals(authenticatedTenantId)) {
            throw new ClaimAccessException(
                    ClaimFailureCode.ACCESS_DENIED);
        }

        StoredClaim stored = repository.find(ticket.claimId())
                .orElseThrow(() -> new ClaimAccessException(
                        ClaimFailureCode.NOT_FOUND));

        if (!stored.ticket().equals(ticket)) {
            throw new ClaimAccessException(
                    ClaimFailureCode.ACCESS_DENIED);
        }
        if (!Instant.now(clock).isBefore(stored.expiresAt())) {
            throw new ClaimAccessException(
                    ClaimFailureCode.EXPIRED);
        }
        return stored.original();
    }

    boolean cleanupAfterConfirmed(ClaimTicket ticket) {
        // Chỉ gọi sau xác nhận nghiệp vụ có thẩm quyền.
        return repository.delete(ticket.claimId());
    }
}
~~~

**Chú ý đến thứ tự:**

1. Xác minh tenant theo **ngữ cảnh đã xác thực**, không tin một claim token tùy ý do caller sửa.
2. Tìm claim theo `claimId`.
3. Kiểm tra record lưu khớp **toàn bộ ticket**, tránh dùng một ID với metadata bị tráo.
4. Kiểm tra TTL tại thời điểm đọc.
5. Trả payload **mà không xóa** — một lỗi downstream có thể retry lại claim.
6. Cleanup chỉ được xem xét khi có bằng chứng business completion và chính sách giữ dữ liệu phù hợp.

Ví dụ này **chưa** hỗ trợ revoke, multi-tenant authorization thực, auditing, encryption, retention manager, rate limit hoặc consistency giữa nhiều node. Việc tách `authenticatedTenantId` khỏi `ticket.tenantId` là cần thiết, nhưng production phải lấy ngữ cảnh tenant từ principal/trust boundary thay vì từ request body.

### 5.5. Ví dụ hai lần restore cùng claim

~~~java
import java.math.BigDecimal;
import java.time.Clock;
import java.time.Duration;

ClaimRepository store = new InMemoryClaimRepository();
RetryableClaimService claims =
        new RetryableClaimService(store, Clock.systemUTC());

OrderPayload order = new OrderPayload(
        "ORD-1", "C-7", new BigDecimal("8500000"));
ClaimTicket ticket = claims.issue(
        "PAY-ORD-1", "TENANT-A", order,
        Duration.ofMinutes(15));

OrderPayload firstRead = claims.restore(ticket, "TENANT-A");
OrderPayload secondRead = claims.restore(ticket, "TENANT-A");

// firstRead.equals(secondRead) == true
// store.find(ticket.claimId()).isPresent() == true
~~~

Hai lần restore vẫn trả cùng dữ liệu vì **không có remove-on-read**. Điều đó không đồng nghĩa được phép **thực hiện charge hai lần**. Ta còn cần quản lý operation và kết quả nghiệp vụ.

## 6. Idempotency khi retry claim thành công hoặc lỗi

### 6.1. Một business operation phải có ID ổn định

Giả sử thao tác thanh toán có operation ID `PAY-ORD-1`. Khi producer gửi lại claim token, downstream phải biết đây **không phải một yêu cầu charge mới**.

~~~text
Attempt 1:
  claimId=C-100
  operationId=PAY-ORD-1
  charge succeeded, reply lost

Attempt 2 (redelivery):
  claimId=C-100
  operationId=PAY-ORD-1
  phải tra được kết quả đã hoàn tất
  không charge lần hai
~~~

Nếu claim cũ đã được dọn, idempotency status **vẫn cần đủ tuổi thọ** để xử lý các message retry đến muộn trong replay horizon. Không xóa claim và đồng thời xóa luôn mọi dấu vết đã xử lý khi broker vẫn có thể redeliver.

### 6.2. Receipt và gateway có idempotency

~~~java
record OperationReceipt(
        String operationId,
        String externalReference,
        String status) {}

interface IdempotentPaymentGateway {
    OperationReceipt charge(
            String operationId,
            OrderPayload order);
}
~~~

Một implementation production phải đảm bảo rằng **same operationId** được nhận diện ở đúng ranh giới tạo side effect. Nếu remote payment API hỗ trợ idempotency key, truyền `operationId` qua request đó và kiểm tra response/reconciliation. Nếu không có, cần inbox/operation state machine và cơ chế query trạng thái trước retry; một `HashMap` ở process gọi không thể bảo đảm hiệu lực khi hệ thống restart.

### 6.3. Implementation fake chỉ để unit test

~~~java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicInteger;

final class FakeIdempotentPaymentGateway
        implements IdempotentPaymentGateway {

    final AtomicInteger committedOperations =
            new AtomicInteger();
    private final ConcurrentMap<String, OperationReceipt> ledger =
            new ConcurrentHashMap<>();

    @Override
    public OperationReceipt charge(
            String operationId,
            OrderPayload order) {
        return ledger.computeIfAbsent(operationId, id -> {
            committedOperations.incrementAndGet();
            return new OperationReceipt(
                    id,
                    "PAYMENT-" + id,
                    "SUCCESS");
        });
    }
}
~~~

`computeIfAbsent` mô phỏng **dedupe trong một JVM**. Đây **không phải** hướng dẫn gọi HTTP hoặc DB transaction thực bên trong một map computation. Một gateway thật phải quản lý tính duy nhất, concurrency, remote timeout và commit trong phạm vi transaction/systems thực tế.

### 6.4. Workflow retry giữ claim cho đến khi an toàn cleanup

~~~java
final class ClaimPaymentWorkflow {
    private final RetryableClaimService claims;
    private final IdempotentPaymentGateway payments;

    ClaimPaymentWorkflow(
            RetryableClaimService claims,
            IdempotentPaymentGateway payments) {
        this.claims = claims;
        this.payments = payments;
    }

    OperationReceipt handle(
            ClaimTicket ticket, String authenticatedTenant) {
        OrderPayload original = claims.restore(
                ticket, authenticatedTenant);

        // Ở ranh giới có side effect, truyền stable operation ID.
        return payments.charge(ticket.operationId(), original);
    }
}
~~~

Workflow demo **không xóa claim** trong `handle`: retry có thể đọc lại payload. Trong production, sau khi ghi nhận completion một cách bền vững, một lifecycle manager riêng mới được cleanup theo retention. Không đặt `repository.delete` vào khối `finally` của `handle` — vì `finally` chạy **cả khi payment lỗi**.

### 6.5. Cleanup sau khi đã commit có thật sự nguyên tử?

Xem một trình tự bất lợi:

~~~text
T1 Payment service commit SUCCESS
T2 Process crash trước khi caller ghi OperationReceipt
T3 Broker redeliver claim
T4 Caller không biết payment đã commit, có nguy cơ charge lại
~~~

Nếu payment service hỗ trợ idempotency key, lần thứ hai có thể nhận receipt cũ thay vì tạo charge mới. Nếu không, phải **reconcile** với hệ thống đích trước khi tạo side effect mới.

Một trình tự khác:

~~~text
T1 Caller ghi receipt SUCCESS
T2 Caller delete claim
T3 Ack broker bị mất
T4 Broker redeliver token
~~~

Khi đó claim không còn. Nếu consumer **kiểm tra completion receipt trước claim-out**, nó có thể trả `ALREADY_COMPLETED` hoặc một receipt đã lưu và không cần restore payload. Nếu logic luôn claim-out trước, nó sẽ báo `NOT_FOUND` dù operation đã hoàn tất — một false alarm không cần thiết.

**Kết luận thiết kế:** thứ tự và thời điểm kiểm tra **idempotency record → claim retrieval → side effect → completion record → cleanup** là một phần của hợp đồng retry, không phải chỉ là chi tiết tối ưu.

## 7. Workflow có completion record để xử lý redelivery sau cleanup

### 7.1. Tại sao cần kiểm tra trạng thái trước khi đọc claim?

Ngay sau khi operation đã hoàn tất và dữ liệu claim bị xóa đúng chính sách, broker vẫn có thể gửi lại token do ack bị mất. Lúc này, **không nên lập tức báo lỗi “không có claim”** nếu đã có bằng chứng bền vững rằng operation tương ứng hoàn tất.

~~~mermaid
flowchart TD
    T[ClaimTicket trên retry queue] --> AUTH{Xác thực tenant + token?}
    AUTH -->|Không| DENY[ACCESS_DENIED]
    AUTH -->|Có| L{Operation completion ledger}
    L -->|Có receipt hợp lệ| OLD[Trả receipt cũ / skip side effect]
    L -->|Chưa có| R[Restore claim]
    R -->|Available| PAY[Idempotent business action]
    R -->|Missing/expired/consumed| Q[Quarantine / reconcile / replay policy]
    PAY --> COMMIT[Record completion]
    COMMIT --> CLEAN[Cleanup theo retention]
~~~

**Receipt có thể được trả trước khi đọc claim** chỉ khi việc tra cứu receipt được **ủy quyền**, gắn đúng tenant, operation và request tương ứng. Đừng cho một token giả tự nêu `operationId` bất kỳ rồi lấy được kết quả của người khác.

### 7.2. Một ledger minh họa

~~~java
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

record OperationKey(String tenantId, String operationId) {}

interface CompletionLedger {
    Optional<OperationReceipt> find(OperationKey key);
    void record(OperationKey key, OperationReceipt receipt);
}

final class InMemoryCompletionLedger implements CompletionLedger {
    private final ConcurrentMap<OperationKey, OperationReceipt> done =
            new ConcurrentHashMap<>();

    @Override
    public Optional<OperationReceipt> find(OperationKey key) {
        return Optional.ofNullable(done.get(key));
    }

    @Override
    public void record(OperationKey key, OperationReceipt receipt) {
        done.putIfAbsent(key, receipt);
    }
}
~~~

`InMemoryCompletionLedger` chỉ làm rõ logic kiểm tra trạng thái; nó **không bền qua restart** và không tự ngăn hai process cùng lúc bắt đầu side effect. Trong production, ledger nên có constraints/locking/transaction policy được kiểm chứng và gắn với operation thực ở hệ thống đích.

### 7.3. Workflow xử lý duplicate trước restore

~~~java
final class CompletionAwareClaimWorkflow {
    private final RetryableClaimService claims;
    private final IdempotentPaymentGateway payments;
    private final CompletionLedger ledger;

    CompletionAwareClaimWorkflow(
            RetryableClaimService claims,
            IdempotentPaymentGateway payments,
            CompletionLedger ledger) {
        this.claims = claims;
        this.payments = payments;
        this.ledger = ledger;
    }

    OperationReceipt handle(
            ClaimTicket ticket, String authenticatedTenant) {

        if (ticket == null
                || !ticket.tenantId().equals(authenticatedTenant)) {
            throw new ClaimAccessException(
                    ClaimFailureCode.ACCESS_DENIED);
        }

        OperationKey key = new OperationKey(
                authenticatedTenant, ticket.operationId());

        OperationReceipt previous = ledger.find(key)
                .orElse(null);
        if (previous != null) {
            // Production còn phải validate claim-to-operation binding
            // hoặc quyền xem receipt theo principal.
            return previous;
        }

        OrderPayload payload = claims.restore(
                ticket, authenticatedTenant);

        OperationReceipt result = payments.charge(
                ticket.operationId(), payload);

        ledger.record(key, result);
        return result;
    }
}
~~~

**Giới hạn có chủ đích:** ví dụ không đưa ra một thuật toán exactly-once phân tán. Giữa `ledger.find` và `payments.charge`, **hai worker** có thể cùng quan sát chưa có completion và đồng thời gọi payment. Bởi vậy `IdempotentPaymentGateway` phải thực sự idempotent ở nơi có side effect, hoặc workflow cần cơ chế **claim operation → IN_PROGRESS → COMMITTED** cùng lock/lease có fencing và recovery hợp lệ.

Một completion ledger theo `operationId` cũng phải ràng buộc **request fingerprint, tenant, owner và claim provenance**; nếu hai payload khác nhau bị gán cùng operation ID, không được âm thầm coi operation thứ hai là duplicate hợp lệ.

### 7.4. State machine nghiệp vụ nên thiết kế rõ

~~~mermaid
stateDiagram-v2
    [*] --> CREATED
    CREATED --> IN_PROGRESS: attempt claim
    IN_PROGRESS --> COMPLETED: side effect confirmed
    IN_PROGRESS --> RETRYABLE: transient failure
    RETRYABLE --> IN_PROGRESS: retry with same operation
    IN_PROGRESS --> UNKNOWN: reply lost after possible commit
    UNKNOWN --> COMPLETED: reconcile confirmed
    UNKNOWN --> RETRYABLE: reconcile confirmed not committed
    CREATED --> CANCELLED: authorized cancel
    RETRYABLE --> CANCELLED: stop retry
    COMPLETED --> [*]
    CANCELLED --> [*]
~~~

Điểm đặc biệt là trạng thái **UNKNOWN**: timeout không đủ chứng minh operation đã thất bại. Trước khi retry một thao tác tạo side effect, cần query/reconcile theo idempotency key hoặc receipt của hệ thống đích.

## 8. Unit test cho claim reusable và one-time

### 8.1. Hai lần đọc claim reusable không làm mất dữ liệu

~~~java
import java.math.BigDecimal;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class RetryableClaimServiceTest {

    private static final Clock FIXED = Clock.fixed(
            Instant.parse("2026-01-01T00:00:00Z"),
            ZoneOffset.UTC);

    private final ClaimRepository repository =
            new InMemoryClaimRepository();
    private final RetryableClaimService service =
            new RetryableClaimService(repository, FIXED);

    @Test
    void sameClaimCanBeReadAgainBeforeCompletion() {
        OrderPayload original = new OrderPayload(
                "ORD-1", "C-1", new BigDecimal("8500000"));
        ClaimTicket token = service.issue(
                "PAY-1", "TENANT-A", original,
                Duration.ofMinutes(10));

        assertEquals(original,
                service.restore(token, "TENANT-A"));
        assertEquals(original,
                service.restore(token, "TENANT-A"));
        assertTrue(repository.find(token.claimId()).isPresent());
    }
}
~~~

Test này chứng minh **dữ liệu vẫn còn sau đọc** trong implementation reusable. Nó chưa chứng minh không có hai payment charges khi handler gọi hai lần.

### 8.2. One-time consume làm retry cùng token thất bại

~~~java
import java.math.BigDecimal;
import java.time.Clock;
import java.time.Duration;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ClaimConsumedRetryTest {

    @Test
    void oldTokenCannotRestoreAfterOneTimeTake() {
        ClaimRepository store = new InMemoryClaimRepository();
        RetryableClaimService service =
                new RetryableClaimService(store, Clock.systemUTC());

        ClaimTicket ticket = service.issue(
                "PAY-2",
                "TENANT-A",
                new OrderPayload(
                        "ORD-2", "C-2",
                        new BigDecimal("1000000")),
                Duration.ofMinutes(5));

        assertTrue(store.take(ticket.claimId()).isPresent());

        ClaimAccessException error = assertThrows(
                ClaimAccessException.class,
                () -> service.restore(ticket, "TENANT-A"));

        assertEquals(ClaimFailureCode.NOT_FOUND, error.code());
    }
}
~~~

Tại sao test mong `NOT_FOUND` mà không phải `ALREADY_CONSUMED`? Vì `take` đã **xóa hẳn record**, repository demo không có tombstone để phân biệt “đã dùng” với “chưa từng tồn tại”. Nếu business contract cần trả `ALREADY_CONSUMED`, phải lưu dấu vết trạng thái ở một nơi khác.

### 8.3. Không đọc sau TTL

~~~java
import java.math.BigDecimal;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class ClaimExpirationTest {

    @Test
    void expiredTokenCannotBeUsedEvenIfRecordStillExists() {
        Instant start = Instant.parse("2026-01-01T00:00:00Z");
        Clock issueClock = Clock.fixed(start, ZoneOffset.UTC);
        Clock laterClock = Clock.fixed(
                start.plus(Duration.ofMinutes(11)),
                ZoneOffset.UTC);

        ClaimRepository store = new InMemoryClaimRepository();
        RetryableClaimService issuer =
                new RetryableClaimService(store, issueClock);
        RetryableClaimService reader =
                new RetryableClaimService(store, laterClock);

        ClaimTicket token = issuer.issue(
                "PAY-3", "TENANT-A",
                new OrderPayload(
                        "ORD-3", "C-3",
                        new BigDecimal("1000000")),
                Duration.ofMinutes(10));

        ClaimAccessException error = assertThrows(
                ClaimAccessException.class,
                () -> reader.restore(token, "TENANT-A"));

        assertEquals(ClaimFailureCode.EXPIRED, error.code());
    }
}
~~~

**Không dùng `Thread.sleep(11 * 60 * 1000)`** để test TTL. Inject `Clock` khiến test ổn định và nhanh. Khi store có TTL tự động **xóa vật lý record** trước lúc đọc, có thể chỉ quan sát `NOT_FOUND` trừ khi có tombstone/metadata riêng; cần kiểm thử behavior đúng store production.

### 8.4. Không cho tenant khác lấy payload

~~~java
import java.math.BigDecimal;
import java.time.Clock;
import java.time.Duration;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class ClaimAuthorizationTest {
    @Test
    void differentTenantCannotRestoreClaim() {
        RetryableClaimService service =
                new RetryableClaimService(
                        new InMemoryClaimRepository(),
                        Clock.systemUTC());

        ClaimTicket token = service.issue(
                "PAY-4", "TENANT-A",
                new OrderPayload(
                        "ORD-4", "C-4",
                        new BigDecimal("1000000")),
                Duration.ofMinutes(5));

        ClaimAccessException error = assertThrows(
                ClaimAccessException.class,
                () -> service.restore(token, "TENANT-B"));

        assertEquals(
                ClaimFailureCode.ACCESS_DENIED, error.code());
    }
}
~~~

**Lưu ý bảo mật:** mã trên chỉ mô tả kiểm tra tenant trong một service method. Production phải kiểm tra **principal thực, tenant ownership, permission, message integrity và audit**, không lấy `authenticatedTenant` trực tiếp từ body của request ngoài.

### 8.5. Retry sau transient failure: lần đầu lỗi, lần sau thành công

~~~java
import java.math.BigDecimal;
import java.time.Clock;
import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class ClaimRetryAfterFailureTest {

    @Test
    void retryCanReadSameClaimAfterTransientFailure() {
        ClaimRepository store = new InMemoryClaimRepository();
        RetryableClaimService claims =
                new RetryableClaimService(store, Clock.systemUTC());
        ClaimTicket ticket = claims.issue(
                "PAY-5", "TENANT-A",
                new OrderPayload(
                        "ORD-5", "C-5",
                        new BigDecimal("1500000")),
                Duration.ofMinutes(10));

        AtomicInteger attempts = new AtomicInteger();
        IdempotentPaymentGateway flaky = (operationId, order) -> {
            if (attempts.incrementAndGet() == 1) {
                throw new IllegalStateException(
                        "TRANSIENT_PAYMENT_UNAVAILABLE");
            }
            return new OperationReceipt(
                    operationId, "PAYMENT-5", "SUCCESS");
        };

        ClaimPaymentWorkflow workflow =
                new ClaimPaymentWorkflow(claims, flaky);

        assertThrows(IllegalStateException.class, () ->
                workflow.handle(ticket, "TENANT-A"));

        OperationReceipt recovered =
                workflow.handle(ticket, "TENANT-A");

        assertEquals("SUCCESS", recovered.status());
        assertEquals(2, attempts.get());
    }
}
~~~

Trong test, failure xảy ra **trước khi fake payment commit**, nên việc gọi lại là an toàn theo kịch bản minh họa. Nếu lần đầu đã commit nhưng mất reply, cần idempotency/reconciliation như mục 6–7; không suy từ exception rằng side effect chưa xảy ra.

### 8.6. Redelivery hai lần không tạo side effect trùng trong fake

~~~java
import java.math.BigDecimal;
import java.time.Clock;
import java.time.Duration;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class ClaimRedeliveryIdempotencyTest {
    @Test
    void sameOperationReturnsSameReceipt() {
        RetryableClaimService claims =
                new RetryableClaimService(
                        new InMemoryClaimRepository(),
                        Clock.systemUTC());
        FakeIdempotentPaymentGateway payments =
                new FakeIdempotentPaymentGateway();
        ClaimPaymentWorkflow workflow =
                new ClaimPaymentWorkflow(claims, payments);

        ClaimTicket token = claims.issue(
                "PAY-6", "TENANT-A",
                new OrderPayload(
                        "ORD-6", "C-6",
                        new BigDecimal("750000")),
                Duration.ofMinutes(10));

        OperationReceipt first =
                workflow.handle(token, "TENANT-A");
        OperationReceipt repeated =
                workflow.handle(token, "TENANT-A");

        assertEquals(first, repeated);
        assertEquals(1, payments.committedOperations.get());
    }
}
~~~

Đây là một **unit test fake gateway** chứng minh contract giả lập. Nó **không** chứng minh merchant/payment processor bên ngoài hỗ trợ exactly-once hoặc idempotency như fake; cần adapter/system test ở đúng hệ thống đích.

## 9. Retry sau khi claim đã cleanup nhưng operation đã hoàn tất

### 9.1. Kết quả cũ có thể giải quyết duplicate mà không cần payload

Đây là một tình huống khác với “retry do payment thất bại”:

~~~text
Attempt #1:
  claim C-100 -> restore Order
  charge PAY-100 -> SUCCESS
  completion ledger ghi SUCCESS
  cleanup claim C-100
  broker ack bị thất lạc

Attempt #2:
  broker gửi lại C-100
  check completion ledger: PAY-100 đã SUCCESS
  -> trả receipt cũ / acknowledge duplicate
  -> KHÔNG cần restore C-100
  -> KHÔNG charge thêm
~~~

Một flow có thể giải quyết được duplicate **dù claim đã bị xóa**, vì operation đã hoàn tất và có bằng chứng độc lập. Nhưng nếu ledger không đáng tin hoặc token không được ràng buộc đúng với operation/tenant, **không được tự đoán** rằng missing claim đồng nghĩa thành công.

### 9.2. Unit test completion-aware workflow

~~~java
import java.math.BigDecimal;
import java.time.Clock;
import java.time.Duration;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;

class ClaimAlreadyCompletedTest {
    @Test
    void redeliveryAfterCleanupUsesVerifiedReceipt() {
        ClaimRepository store = new InMemoryClaimRepository();
        RetryableClaimService claims =
                new RetryableClaimService(store, Clock.systemUTC());
        FakeIdempotentPaymentGateway payment =
                new FakeIdempotentPaymentGateway();
        CompletionLedger ledger =
                new InMemoryCompletionLedger();
        CompletionAwareClaimWorkflow workflow =
                new CompletionAwareClaimWorkflow(
                        claims, payment, ledger);

        ClaimTicket token = claims.issue(
                "PAY-100", "TENANT-A",
                new OrderPayload(
                        "ORD-100", "C-100",
                        new BigDecimal("5000000")),
                Duration.ofMinutes(15));

        OperationReceipt first =
                workflow.handle(token, "TENANT-A");
        claims.cleanupAfterConfirmed(token);

        assertFalse(store.find(token.claimId()).isPresent());

        // Retry không cần đọc claim nếu ledger ghi completion.
        OperationReceipt duplicate =
                workflow.handle(token, "TENANT-A");

        assertEquals(first, duplicate);
        assertEquals(1, payment.committedOperations.get());
    }
}
~~~

Kết quả test phù hợp với **implementation demo**. Với completion ledger bền vững và remote payment, vẫn cần kiểm tra transaction/commit semantics: **ledger và store không nhất thiết được cập nhật nguyên tử với payment**. Khi hai worker cùng chạy, cần khóa hoặc idempotency ở hệ thống có side effect.

### 9.3. Nếu claim mất mà không có completion receipt?

~~~text
ClaimToken C-404
  -> ledger không có COMPLETED
  -> store không có C-404
  -> CLAIM_NOT_FOUND
~~~

Đây là một **trạng thái không chắc chắn cần điều tra** chứ không tự suy ra payment đã thành công hay chắc chắn chưa chạy. Một số khả năng:

- Claim đã bị consume ở lần trước, downstream lỗi sau đó.
- TTL cleanup đã xóa dữ liệu.
- Message Store in-memory mất state sau restart.
- Token thuộc sai store/shard/tenant.
- Token không hợp lệ hoặc bị giả mạo.
- Claim chưa bao giờ được lưu bền vững trước khi token được phát.
- Completion ledger đã bị mất nhưng remote payment đã commit.

Hướng xử lý đúng là **phân loại, reconcile theo operationId và chỉ replay nếu có nguồn gốc đáng tin**, thay vì retry mù hoặc tự tạo payload giả.

## 10. Java DSL: Claim Check retry qua hai IntegrationFlow

### 10.1. Vì sao tách issue và process thành hai flow?

Để kiểm thử rõ ràng, ta chia:

~~~mermaid
flowchart LR
    A["ClaimSubmission"] --> I["Claim In / store"]
    I --> T["ClaimTicket"]
    T --> Q[(Token queue / transport)]
    Q --> W["Completion-aware workflow"]
    W -->|Chưa hoàn tất| OUT["Claim Out / restore payload"]
    OUT --> PAY["Idempotent Payment"]
    PAY --> REC["Completion ledger"]
    W -->|Đã hoàn tất| OLD["Existing receipt"]
    REC --> R["OperationReceipt"]
    OLD --> R
~~~

Ví dụ dùng **Transformer/service endpoint** để triển khai cùng Claim Check pattern và kiểm soát chính xác **read-without-remove**. Spring Integration cũng có **Claim Check In/Out Transformer chuyên dụng**; khi dùng native components, phải xác minh `MessageStore` và remove behavior của phiên bản đang chạy.

### 10.2. Input DTOs cho Gateway

~~~java
record ClaimSubmission(
        OrderPayload original,
        String operationId,
        String tenantId) {}

record ClaimAttempt(
        ClaimTicket ticket,
        String authenticatedTenantId) {}
~~~

Trường `authenticatedTenantId` ở đây chỉ đại diện cho **ngữ cảnh được adapter giả lập truyền vào**. Trong HTTP/broker production, nó phải được lấy từ principal/trusted security context, không phải một chuỗi mà caller bên ngoài tùy ý chọn.

### 10.3. Cấu hình Spring Integration

~~~java
import java.time.Clock;
import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.Gateway;
import org.springframework.integration.annotation.IntegrationComponentScan;
import org.springframework.integration.annotation.MessagingGateway;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;

@MessagingGateway
interface ClaimPaymentGateway {
    @Gateway(requestChannel = "claims.issue.input",
            replyTimeout = 5000)
    ClaimTicket issue(ClaimSubmission submission);

    @Gateway(requestChannel = "claims.process.input",
            replyTimeout = 5000)
    OperationReceipt process(ClaimAttempt attempt);
}

@Configuration
@EnableIntegration
@IntegrationComponentScan
class ClaimRetryFlowConfiguration {

    @Bean(name = "claims.issue.input")
    MessageChannel issueChannel() {
        return new DirectChannel();
    }

    @Bean(name = "claims.process.input")
    MessageChannel processChannel() {
        return new DirectChannel();
    }

    @Bean
    Clock claimClock() {
        return Clock.systemUTC();
    }

    @Bean
    ClaimRepository claimRepository() {
        return new InMemoryClaimRepository();
    }

    @Bean
    RetryableClaimService retryableClaims(
            ClaimRepository repository, Clock claimClock) {
        return new RetryableClaimService(
                repository, claimClock);
    }

    @Bean
    FakeIdempotentPaymentGateway paymentGatewayFake() {
        return new FakeIdempotentPaymentGateway();
    }

    @Bean
    CompletionLedger completionLedger() {
        return new InMemoryCompletionLedger();
    }

    @Bean
    CompletionAwareClaimWorkflow completionAwareWorkflow(
            RetryableClaimService claims,
            FakeIdempotentPaymentGateway payments,
            CompletionLedger ledger) {
        return new CompletionAwareClaimWorkflow(
                claims, payments, ledger);
    }

    @Bean
    IntegrationFlow issueClaimFlow(RetryableClaimService claims) {
        return IntegrationFlow.from("claims.issue.input")
                .transform(ClaimSubmission.class, submission ->
                        claims.issue(
                                submission.operationId(),
                                submission.tenantId(),
                                submission.original(),
                                Duration.ofMinutes(15)))
                .get();
    }

    @Bean
    IntegrationFlow retryClaimFlow(
            CompletionAwareClaimWorkflow workflow) {
        return IntegrationFlow.from("claims.process.input")
                .handle(ClaimAttempt.class, (attempt, headers) ->
                        workflow.handle(
                                attempt.ticket(),
                                attempt.authenticatedTenantId()))
                .get();
    }
}
~~~

**Cách đọc:**

1. `ClaimPaymentGateway.issue` nhận original payload và trả ticket.
2. `issueClaimFlow` ghi payload vào repository rồi trả `ClaimTicket` qua reply path của Gateway.
3. `ClaimPaymentGateway.process` nhận một attempt chứa ticket.
4. `retryClaimFlow` kiểm tra completion ledger, nếu chưa hoàn tất thì restore payload mà **không xóa**.
5. Payment fake sử dụng stable operation ID để chống duplicate trong test.
6. Khi đã hoàn tất và claim được cleanup, receipt còn lại có thể giải quyết redelivery.

**Quan trọng:** ví dụ này là flow đồng bộ/in-memory để học cơ chế. Không dùng nó như implementation production khi chưa bổ sung **persistent store, trusted tenant context, transactional claim publishing, secure token format, durable completion ledger, error channel, bounded retry, monitoring và remote idempotency**.

### 10.4. Dùng native Claim Check In/Out như thế nào?

Nếu chọn các transformer Claim Check chuyên dụng thay vì service tự viết, kiến trúc là:

~~~text
input
  -> Claim Check In Transformer (store original Message)
  -> claim token channel
  -> Claim Check Out Transformer
       lookup message bằng claim token
       preserve-or-remove theo cấu hình
  -> business handler
~~~

Khi đối chiếu Java DSL cho dependency Spring Integration đang dùng, hãy xác nhận:

- **Kiểu token:** là Message ID/UUID hay một kiểu ID khác?
- **Store:** Claim Check In/Out dùng chính xác cùng `MessageStore` instance/logical backing store chưa?
- **Remove behavior:** Claim Check Out giữ message để retry hay xóa khi đọc?
- **Header merge:** original headers và token-envelope headers được kết hợp ra sao?
- **Error behavior:** missing claim ném exception nào hoặc trả trạng thái gì?
- **Transaction:** claim-out và downstream có cùng transaction khi cần không?
- **TTL/persistence:** claim còn sau restart và retry horizon không?

Không trộn native `ClaimCheckOutTransformer` với một service đọc lại `ClaimTicket` có schema khác mà chưa có adapter mapping. Token của demo và token framework **không đương nhiên tương thích**.

## 11. Integration test cho luồng Spring Integration

### 11.1. Issue → Process → Redeliver cùng token

~~~java
import java.math.BigDecimal;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringJUnitConfig(ClaimRetryFlowConfiguration.class)
@DirtiesContext(classMode =
        DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class ClaimRetryIntegrationTest {

    @Autowired
    ClaimPaymentGateway gateway;

    @Autowired
    FakeIdempotentPaymentGateway payments;

    @Test
    void retrySameClaimReturnsSameBusinessReceipt() {
        ClaimTicket ticket = gateway.issue(
                new ClaimSubmission(
                        new OrderPayload(
                                "ORD-7", "C-7",
                                new BigDecimal("8500000")),
                        "PAY-ORD-7",
                        "TENANT-A"));

        ClaimAttempt attempt = new ClaimAttempt(
                ticket, "TENANT-A");

        OperationReceipt first = gateway.process(attempt);
        OperationReceipt retry = gateway.process(attempt);

        assertEquals(first, retry);
        assertEquals("SUCCESS", retry.status());
        assertEquals(1, payments.committedOperations.get());
    }
}
~~~

Test đi qua **Gateway → Spring Integration Transformer/Handler → claim repository → fake payment**. Nó mạnh hơn unit test service nhưng **chưa đi qua broker hoặc native Claim Check Transformer**. Cần một adapter integration test riêng cho các thành phần đó.

### 11.2. Claim được dọn sau completion, duplicate vẫn có thể trả receipt

~~~java
import java.math.BigDecimal;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;

@SpringJUnitConfig(ClaimRetryFlowConfiguration.class)
@DirtiesContext(classMode =
        DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class ClaimCleanupRedeliveryIntegrationTest {

    @Autowired
    ClaimPaymentGateway gateway;

    @Autowired
    RetryableClaimService claims;

    @Autowired
    ClaimRepository store;

    @Autowired
    FakeIdempotentPaymentGateway payments;

    @Test
    void completedOperationCanAnswerAfterClaimDeleted() {
        ClaimTicket ticket = gateway.issue(
                new ClaimSubmission(
                        new OrderPayload(
                                "ORD-8", "C-8",
                                new BigDecimal("2000000")),
                        "PAY-ORD-8",
                        "TENANT-A"));

        ClaimAttempt attempt = new ClaimAttempt(
                ticket, "TENANT-A");
        OperationReceipt first = gateway.process(attempt);

        claims.cleanupAfterConfirmed(ticket);
        assertFalse(store.find(ticket.claimId()).isPresent());

        OperationReceipt repeated = gateway.process(attempt);
        assertEquals(first, repeated);
        assertEquals(1, payments.committedOperations.get());
    }
}
~~~

**Tại sao dùng `@DirtiesContext`?** Repository, ledger và fake payment giữ state trong Spring beans. Mỗi test phải có bối cảnh độc lập hoặc reset rõ ràng, nếu không test sẽ phụ thuộc thứ tự chạy hoặc ảnh hưởng từ test khác.

### 11.3. Negative integration test: claim bị lấy mất, chưa có completion

~~~java
import java.math.BigDecimal;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringJUnitConfig(ClaimRetryFlowConfiguration.class)
class ClaimLostBeforeCompletionIntegrationTest {

    @Autowired
    ClaimPaymentGateway gateway;

    @Autowired
    ClaimRepository store;

    @Test
    void consumedClaimWithoutReceiptMustNotCharge() {
        ClaimTicket ticket = gateway.issue(
                new ClaimSubmission(
                        new OrderPayload(
                                "ORD-9", "C-9",
                                new BigDecimal("1000000")),
                        "PAY-ORD-9",
                        "TENANT-A"));

        store.take(ticket.claimId());

        assertThrows(RuntimeException.class, () ->
                gateway.process(
                        new ClaimAttempt(ticket, "TENANT-A")));
    }
}
~~~

Một integration endpoint có thể bọc exception trong `MessageHandlingException` hoặc kiểu messaging exception khác; do đó ví dụ bắt `RuntimeException` để không phụ thuộc một wrapper cụ thể. Một test hoàn thiện nên kiểm tra **cause chain chứa mã NOT_FOUND** và xác nhận payment fake **không được gọi**.

## 12. Đặt retry sai vị trí có thể làm claim hết hiệu lực

### 12.1. Retry *chỉ* downstream khác retry toàn flow

So sánh hai cách thiết kế:

~~~text
Phương án A:
  claim out (remove=true)
    -> giữ payload trong memory của lần xử lý
    -> retry HTTP request 3 lần

Phương án B:
  retry( claim out(remove=true) -> HTTP request )
    -> attempt 1: claim out xóa payload, HTTP timeout
    -> attempt 2: claim out báo NOT_FOUND
~~~

Ở **phương án A**, retry HTTP trong **cùng execution context** có thể tiếp tục dùng payload đã khôi phục, dù store không còn claim. Nhưng khi process crash hoặc broker redeliver, payload trong memory cũng mất; recovery vẫn có thể thất bại.

Ở **phương án B**, retry chạy lại cả claim-out, nên đụng ngay lỗi “claim đã dùng”. Hai phương án **không tương đương**, dù cùng có chữ “retry 3 lần”.

### 12.2. Ranh giới retry phải được thiết kế

| Phạm vi retry | Có lặp claim-out không? | Rủi ro |
|---|---|---|
| Chỉ HTTP/payment client sau restore | Không trong một attempt. | Crash mất payload nếu claim đã consume. |
| Advice quanh payment handler | Không nếu claim-out nằm ở endpoint trước đó. | Cần đúng transaction/ack của handler. |
| Advice quanh claim-out transformer | Có. | One-time claim có thể bị tiêu thụ ngay từ lần đầu. |
| Broker redelivery từ token topic | Có thể chạy lại toàn chain. | Missing claim sau remove; phải có completion/restore policy. |
| Gateway request retry từ original input | Có thể tạo claim mới. | Trùng business operation/side effect nếu không giữ idempotency. |

**RequestHandlerRetryAdvice** là một lựa chọn trong Spring Integration để retry một endpoint tương ứng, nhưng cấu hình chính xác phải theo phiên bản framework và semantics của endpoint. Trước khi thêm advice, hãy xác định **nó bao bọc method nào**, **exception nào retryable**, và **side effect nào có thể đã commit**.

### 12.3. Phân biệt lỗi có thể thử lại

| Mã lỗi hoặc tình huống | Nên retry nguyên token ngay? | Hành động |
|---|---|---|
| Payment service tạm unavailable; claim reusable còn tồn tại | Có thể, có giới hạn. | Backoff + idempotency + deadline. |
| Claim store tạm unavailable | Có thể sau khi store hồi phục. | Không diễn giải thành claim missing. |
| `NOT_FOUND` sau one-time consume | Thường không có ích. | Kiểm tra completion, tombstone, replay source. |
| `EXPIRED` | Không với token cũ. | Reauthorize/reissue nếu policy cho phép. |
| `ALREADY_CONSUMED` có tombstone | Không với cùng claim. | Tra trạng thái operation; replay mới nếu được phép. |
| `ACCESS_DENIED` | Không. | Dừng; audit/security response. |
| `INVALID_TICKET` hoặc payload malformed | Không nên retry vô hạn. | Quarantine/validation lỗi producer. |
| Charge đã commit nhưng reply mất | Không được charge mù lần hai. | Reconcile/idempotency key. |
| Gateway reply timeout | Không chứng minh downstream chưa xử lý. | Query status/reconcile trước khi thử lại. |
| Store full / DB deadlock | Có thể là transient. | Retry có giới hạn, backpressure và alert. |

**Không retry bằng cách bắt mọi `RuntimeException` rồi gửi lại vô hạn.** Phân loại lỗi trước, đặt max attempts/deadline, kiểm tra operation state và có đường recovery.

### 12.4. Recovery không được tự tạo success

Một recovery flow có thể trả về một trong các trạng thái:

~~~text
CLAIM_RETRY_SCHEDULED
CLAIM_ALREADY_COMPLETED
CLAIM_REPLAY_AUTHORIZATION_REQUIRED
CLAIM_EXPIRED
CLAIM_NOT_FOUND
CLAIM_REVOKED
CLAIM_QUARANTINED
OPERATION_OUTCOME_UNKNOWN
~~~

**Không có trạng thái nào mặc định bằng PAYMENT_SUCCESS**. Chỉ nguồn payment/completion ledger có thẩm quyền mới có thể xác nhận operation đã hoàn tất.

## 13. Giao dịch: lưu claim, publish token và acknowledge

### 13.1. Dual-write tại claim-in

Việc tạo claim có hai bước logic:

~~~text
1. Persist original Message in Claim Store
2. Publish ClaimToken to message broker
~~~

Có những cửa sổ lỗi:

| Thời điểm crash | Hệ quả |
|---|---|
| Trước khi lưu payload | Không có claim/token. |
| Sau khi lưu payload, trước publish token | Có **orphan claim** không ai nhận. |
| Publish token thành công nhưng ghi store không bền vững | Consumer nhận token nhưng không tìm thấy payload. |
| Sau publish, trước khi producer nhận ack | Producer có thể publish lại token gây duplicate. |

Nếu database và broker không nằm trong một transaction phù hợp, **không thể giả định hai bước luôn nguyên tử**. Một lựa chọn phổ biến là **transactional outbox**:

~~~mermaid
flowchart LR
    A[Receive original] --> TX[DB Transaction]
    TX --> S[(Stored Claim)]
    TX --> O[(Outbox token record)]
    O --> RELAY[Outbox Publisher]
    RELAY --> B[(Broker)]
    B --> C[Claim Consumer]
~~~

Khi cả claim record và outbox record được ghi trong một **DB transaction**, một crash có thể khiến publisher gửi lại, nhưng **không tạo token chỉ vào claim chưa commit** theo contract outbox. Cần dedupe ở consumer vì outbox relay có thể publish lặp.

### 13.2. Transaction ở claim-out

Nếu dùng one-time consume, lý tưởng có thể muốn:

~~~text
begin transaction
  read and mark claim used
  process downstream
  record completion
commit
~~~

Nhưng không phải mọi HTTP payment hoặc Kafka broker tham gia cùng transaction. **Claim store commit không thể rollback một payment đã commit ngoài hệ thống**. Khi có nhiều resource managers, cần idempotency, saga/compensation hoặc cơ chế reconciliation; không dùng transaction annotation như lời hứa atomic xuyên mọi dịch vụ.

### 13.3. Xóa claim sau completion cũng có thể lỗi

Giả sử payment thành công nhưng cleanup `delete(claimId)` trả lỗi do DB unavailable. Không nên **đánh dấu payment thất bại rồi charge lại** chỉ vì cleanup lỗi.

Thiết kế tốt hơn:

~~~text
Payment outcome: SUCCESS, durable receipt
Cleanup job:     PENDING_DELETE

Nếu cleanup lỗi:
  retry cleanup theo job ID
  giữ business receipt SUCCESS
  không charge lại
~~~

Cleanup là một lifecycle action riêng, có retry và monitoring riêng. Nếu dữ liệu nhạy cảm cần xóa đúng hạn, phải có cảnh báo và recovery khi cleanup bị kẹt; nhưng trạng thái xóa không nên làm đảo ngược một kết quả nghiệp vụ đã xác nhận.

### 13.4. Atomic consume không bằng atomic business processing

Một repository có thể hỗ trợ **atomic read-and-delete**, đảm bảo chỉ một worker lấy được payload. Tuy nhiên:

~~~text
Worker A: atomic take thành công
Worker A: crash trước payment
Worker B: retry thấy claim đã mất
~~~

Atomic consume chỉ ngăn **hai worker lấy cùng claim**, không giải quyết **mất payload sau worker crash**. Muốn at-least-once processing an toàn hơn, có thể dùng **lease**:

~~~text
AVAILABLE -> LEASED(to worker A, until T)
LEASED -> COMPLETED (payment committed)
LEASED -> AVAILABLE (lease expired, recovery approved)
~~~

Nhưng lease cũng cần **fencing token/attempt generation** để một worker cũ không tiếp tục commit sau khi lease đã được cấp lại cho worker mới. Không coi lease timeout đồng nghĩa worker A chắc chắn đã dừng.

## 14. Concurrency: hai worker retry cùng claim

### 14.1. Race giữa hai consumer

~~~mermaid
sequenceDiagram
    participant A as Worker A
    participant B as Worker B
    participant S as Claim Store
    participant P as Payment API
    A->>S: restore C-100
    B->>S: restore C-100
    S-->>A: Order payload
    S-->>B: Order payload
    A->>P: charge PAY-100
    B->>P: charge PAY-100
    Note over P: Phải nhận diện stable idempotency key
~~~

Reusable claim cho cả hai worker đọc được payload — đó là mục tiêu hỗ trợ retry — nhưng **không tự ngăn gọi payment đồng thời**.

### 14.2. Chọn điểm khóa theo operation

Các thành phần có thể phối hợp:

1. **Durable operation ledger** có unique key `(tenantId, operationId)`.
2. **Operation fingerprint** để không dùng cùng ID cho payload khác nhau.
3. **In-progress lease** để điều phối worker trong thời gian hữu hạn.
4. **Fencing/version** để ngăn worker có lease cũ cập nhật trạng thái sau worker mới.
5. **Payment idempotency key** ở đúng external side-effect boundary.
6. **Reconciliation** với external service khi trạng thái commit không chắc chắn.
7. **Cleanup** chỉ sau khi biết kết quả cuối, với tombstone đủ tuổi thọ.

Một distributed lock đơn lẻ cũng có thể mất hiệu lực khi tiến trình paused hoặc mạng partition; không bỏ qua fencing/idempotency.

### 14.3. Hai kết quả khác nhau cho cùng operation ID

Nếu Worker A có payload `amount=5_000_000` còn Worker B nhận claim mới cùng `operationId` nhưng amount `8_000_000`, không được “dedupe thành công” một cách mù quáng. Một completion ledger nên ghi **payload fingerprint** và từ chối request có cùng operation ID nhưng nội dung nghiệp vụ khác.

~~~text
key = (TENANT-A, PAY-ORD-1)
storedFingerprint = sha256(canonical business payload v1)

retry request:
  same operation key
  same fingerprint -> có thể return previous receipt
  different fingerprint -> OPERATION_CONFLICT
~~~

Nếu hash payload, phải định nghĩa **canonicalization** trước (schema version, số, timezone, field order, Unicode), không lấy `toString()` của Java object làm chuẩn đáng tin. Không dùng fingerprint thay authorization.

## 15. TTL, retention và tombstone sau claim-out

### 15.1. TTL của claim không được ngắn hơn retry horizon một cách vô ý

~~~text
Claim TTL:        5 phút
Broker max retry: 30 phút
Error recovery:   2 giờ
~~~

Nếu claim bị xóa sau 5 phút, retry ở phút 15 có thể không còn dữ liệu. Có thể giải quyết bằng:

- Tăng TTL phù hợp với **retry horizon** và yêu cầu bảo mật.
- Tách **active claim retention** khỏi **replay archive retention**.
- Cho phép reissue từ nguồn bền vững có ủy quyền thay vì kéo dài TTL vô hạn.
- Khi claim sắp hết hạn, quyết định **gia hạn có kiểm soát** hoặc dừng retry/quarantine.

### 15.2. Không giữ mọi claim vô hạn

Reusable claim giúp retry, nhưng lưu vô hạn gây chi phí và rủi ro dữ liệu:

| Vấn đề | Biện pháp |
|---|---|
| Payload chứa PII | Encryption, minimization, access control, retention. |
| Orphan claim chưa từng publish token | Quét record quá hạn và kiểm tra outbox/recovery. |
| Claim đã completed | Cleanup sau retention/audit window. |
| Claim đã revoked | Chặn đọc ngay, cleanup theo policy. |
| Claim active nhưng không có consumer | Backlog/claim age alert, admission control. |
| Claim đang được dùng khi TTL kết thúc | Trạng thái in-progress/lease/deadline rõ. |
| Store hết dung lượng | Capacity alert và backpressure, không silent drop. |

### 15.3. Tombstone không phải dữ liệu gốc

Để phân biệt `ALREADY_USED` với `NOT_FOUND`, có thể giữ metadata tối thiểu sau khi xóa payload:

~~~json
{
  "claimId": "C-100",
  "operationId": "PAY-ORD-1",
  "tenantId": "TENANT-A",
  "state": "COMPLETED",
  "completedAt": "2026-01-01T00:00:00Z"
}
~~~

Đây là **schema minh họa do ứng dụng tự thiết kế**, không phải record mà Spring Integration Message Store tự sinh trong mọi cấu hình.

Tombstone giúp:

- Nhận diện claim đã dùng/đã đóng.
- Ngăn một late token làm sống lại một group đã hoàn tất.
- Truy tìm operation receipt mà không giữ toàn payload.
- Áp dụng retention tách biệt cho dữ liệu lớn và metadata.

Nhưng tombstone **không đủ để tái chạy nghiệp vụ** nếu original payload đã bị xóa. Nếu dữ liệu không còn, phải có nguồn replay hợp lệ khác hoặc trả trạng thái không phục hồi được.

### 15.4. Revoke token là một trạng thái riêng

Nếu Claim Check được dùng để hạn chế truy cập vào dữ liệu nhạy cảm, một claim bị **REVOKED** vì gian lận/bảo mật không được cấp lại chỉ vì consumer báo retry. Chính sách reissue phải kiểm tra lý do revoke và quyền hiện tại; hoàn toàn khác một claim **EXPIRED** vì thời gian.

## 16. Claim Check kết hợp các Enterprise Integration Patterns

### 16.1. Filter sau claim-in có thể tạo orphan claim

~~~mermaid
flowchart LR
    P[Original payload] --> C[Claim In]
    C --> F{Filter token}
    F -->|Accepted| Q[(Queue)]
    F -->|Rejected| D[Discard]
    C --> S[(Claim Store)]
    D -.-> O[Orphan claim nếu không cleanup]
~~~

Nếu Filter từ chối token **sau khi** payload đã được lưu, có thể không còn consumer nào lấy claim. Đây không phải lỗi Claim Check Out, nhưng tạo dữ liệu không được dùng và tồn tại tới TTL.

Các lựa chọn:

- Đặt **validation/eligibility Filter trước claim-in** khi dữ liệu cần kiểm tra đã có sẵn ở original.
- Nếu phải Filter theo metadata ở token, thiết kế cleanup cho nhánh rejected với audit hợp lệ.
- Theo dõi số claim được issue nhưng không có token được accepted/processed.
- Dùng outbox/state machine để nhận diện orphan claim sau crash.

Không xóa claim ngay khi một Filter loại token nếu **các nhánh khác cũng đang cần cùng claim**; policy ownership của token phải rõ.

### 16.2. Router chọn nhánh không làm token tự dùng được nhiều lần

Một Content-Based Router có thể đưa cùng một claim qua các xử lý khác nhau theo `orderType` hoặc `region`:

~~~text
ClaimToken C-100
  -> Router
      -> domestic handler
      -> international handler
~~~

Nếu Router chọn **một** branch, one-time claim có thể phù hợp với hợp đồng một consumer. Nhưng nếu một nhánh fail và message được route lại hoặc cùng token được gửi tới nhiều recipient, cần xem claim có thể được đọc lần nữa không.

**Router không tự đảm bảo dữ liệu original có sẵn**, còn Claim Check không tự chọn route; hai mẫu có trách nhiệm khác nhau.

### 16.3. Scatter–Gather và Recipient List: một claim, nhiều readers

Đây là một bẫy thiết kế quan trọng:

~~~mermaid
flowchart TD
    C["ClaimToken C-100"] --> S{Scatter}
    S --> I[Inventory check]
    S --> F[Fraud check]
    I --> OI[Claim Out]
    F --> OF[Claim Out]
    OI --> STORE[(Message Store)]
    OF --> STORE
    OI -->|Read-and-remove đầu tiên| OK[Inventory lấy được payload]
    OF -->|Đọc sau khi đã remove| FAIL[Fraud missing claim]
~~~

Nếu hai recipient dùng **cùng token one-time**, chỉ một nhánh có thể lấy được original trong thiết kế read-and-remove. Những cách xử lý hợp lệ:

1. **Reusable claim** trong thời gian các recipient và retry còn cần đọc, rồi cleanup sau Gather/operation completion.
2. **Một claim riêng cho từng recipient** khi không muốn hai nhánh chia sẻ quyền truy xuất; mỗi claim có scope/TTL riêng.
3. **Restore trước Scatter**, sau đó phân phối payload theo contract và quyền của từng recipient (cần cân nhắc bảo mật và payload size).
4. **Tách projection cho mỗi recipient** tại nguồn đáng tin, thay vì cho tất cả đọc dữ liệu nhạy cảm đầy đủ.

Không coi cấu hình một `claimCheckOut` ở mỗi nhánh là an toàn khi chưa test duplicate readers và chính sách remove.

### 16.4. Splitter/Aggregator và claim nhỏ cho từng child

Một batch lớn có thể được split thành các item, mỗi item được claim-in riêng:

~~~text
Batch ORD-1
  -> Splitter
      -> Item #1 -> claim C-1
      -> Item #2 -> claim C-2
      -> Item #3 -> claim C-3
  -> per-item retry
  -> Aggregator
~~~

Nếu `C-2` đã bị dùng rồi nhưng handler #2 lỗi, một retry per-item phải có khả năng restore #2 hoặc nguồn replay. Đồng thời Aggregator cần:

- `correlationId` của batch.
- `sequenceNumber`/`sequenceSize` hoặc business item identity.
- Outcome cho mỗi item kể cả rejected/failed theo contract.
- Quy tắc timeout nếu một claim không khôi phục được.
- Phân biệt duplicate item reply với một item khác bị thiếu.

**Không để một claim bị xóa gây ra một Aggregator chờ mãi mà không có error/timeout outcome.**

### 16.5. Resequencer giữ token quá lâu có thể làm claim hết hạn

~~~text
T0 Claim In: C-1, C-2, C-3 (TTL 5 phút)
T1 Token C-3 đến Resequencer trước, bị buffer
T2 Thiếu token C-2, group chờ hơn 5 phút
T3 C-2 tới, Resequencer release C-2 và C-3
T4 Claim Out với C-3 -> EXPIRED
~~~

Resequencer đã **hoàn thành đúng trách nhiệm ordering**, nhưng Claim Check Out vẫn không khôi phục được payload vì TTL. Khi ghép hai pattern:

- Ước lượng thời gian buffer/gap/retry so với claim TTL.
- Đặt retention theo worst-case được chấp thuận hoặc giữ durable replay source.
- Có trạng thái **expired while buffered** và đường quarantine.
- Không giữ claim vô hạn chỉ để né timeout.
- Không tự xem thứ tự release đúng là dữ liệu original chắc chắn còn.

### 16.6. Content Enricher và dữ liệu claim đã thay đổi

Nếu một Content Enricher lấy original rồi bổ sung thông tin khách hàng, đừng ghi đè dữ liệu lưu dưới claim cũ bằng một payload hoàn toàn mới mà không có version/provenance:

~~~text
Stored original at Claim C-100
  original order payload

Enrichment result
  {original: ..., profile: ..., enrichedAt: ...}
~~~

Giữ **original** và **enrichment** riêng hoặc tạo claim/version mới theo hợp đồng. Với retry, cần biết sẽ dùng **dữ liệu enrich snapshot của attempt trước** hay sẽ lookup lại theo trạng thái hiện tại.

### 16.7. Gateway timeout không đồng nghĩa claim đã được dọn

Một HTTP/Gateway caller có thể hết `replyTimeout` trong khi broker worker vẫn xử lý claim:

~~~text
Caller -> Gateway -> Token C-100 -> queue
Gateway timeout at 3s
Worker completes payment at 7s
~~~

Khi caller gửi lại:

- Không tạo charge mới nếu operation cũ đã commit.
- Xem completion ledger trước khi phục hồi payload/issue claim mới.
- Cần trả trạng thái `PENDING`/`COMPLETED`/`UNKNOWN` hoặc receipt theo API contract.
- Nếu claim đã consumed, phải phân biệt consumed với operation failed.

## 17. Headers, correlation và serialization khi khôi phục message

### 17.1. Payload gốc và message gốc khác nhau

Claim Check có thể lưu một **Spring `Message<?>`** với payload lẫn headers; một implementation tự viết có thể chỉ lưu **payload** và metadata được chọn. Hai lựa chọn này không tương đương.

Ví dụ original:

~~~text
payload: OrderPayload
headers:
  traceId: T-100
  correlationId: ORD-1
  replyChannel: (internal MessageChannel)
  errorChannel: (internal MessageChannel)
~~~

Sau claim-in, token message có thể có **MessageHeaders.ID** mới, và sau claim-out framework có thể dựng lại/khôi phục message cùng headers theo semantics cụ thể. Cần xác minh **header nào được bảo tồn, merge, override hoặc loại bỏ**, nhất là khi message đi qua nhiều adapter.

### 17.2. Không tái sử dụng replyChannel của một JVM đã chết

`replyChannel`/`errorChannel` trong Spring Integration có thể chứa tham chiếu internal channel. Chúng không phải địa chỉ wire-portable cho Kafka/JMS/HTTP. Nếu message được lưu lâu, rồi đọc lại ở một JVM khác:

- Không serialize và trông đợi một object `MessageChannel` cũ vẫn hoạt động.
- Thiết kế **reply destination** và error route phù hợp transport.
- Giữ `requestId`/`correlationId` như metadata có thể chuyển, không phải object pointer.
- Test header mapping sau serialize/deserialize và version upgrade.
- Nếu token đã đổi identity, đừng nhầm original message ID với claim ID hoặc current retry delivery ID.

### 17.3. Correlation khi tạo claim mới

Nếu operator reissue claim `C-200` từ source của `C-100`:

~~~text
business orderId = ORD-1
operationId      = PAY-ORD-1
old claimId      = C-100
new claimId      = C-200
replayAttemptId  = A-2
~~~

Các ID có vai trò riêng:

| ID | Nghĩa | Nên giữ hay thay khi replay? |
|---|---|---|
| `orderId` | Order gốc. | Giữ nếu cùng business order. |
| `operationId` | Operation có side effect cần chống trùng. | Giữ khi retry cùng operation, thay khi thực sự tạo operation mới. |
| `claimId` | Khóa tra payload từ store. | Thay nếu reissue claim mới. |
| `replayAttemptId` | Lần thử/replay. | Thay cho mỗi lần có chủ đích. |
| `traceId` | Quan sát một call chain. | Có thể mới, nhưng liên kết tới operation cũ. |
| `correlationId` | Gom message trong flow. | Theo group contract; không tự thay ngẫu nhiên. |

### 17.4. Dữ liệu raw cần lưu thế nào?

Nếu business yêu cầu **replay byte-for-byte**, lưu một DTO `OrderPayload` đã parse chưa chắc đủ: converter có thể thay whitespace, unknown fields, timezone hoặc scale của số. Cần định nghĩa:

- **Exact raw-event replay:** lưu bản wire payload có integrity hash và schema version.
- **Semantic replay:** giữ DTO/canonical business fields và policy/lookup version.
- **Event-sourced replay:** tái xây trạng thái từ event log đã xác minh.

Mỗi hướng có retention, chi phí và quyền dữ liệu khác nhau; không suy rằng một claim token nhỏ tự giữ được “original request chính xác từng byte”.

## 18. Bảo mật của claim trong retry

### 18.1. Claim token phải được bảo vệ như tham chiếu tới dữ liệu

Một claim ID dễ đoán như `C-1, C-2, C-3` có thể gây **enumeration** nếu endpoint claim-out không kiểm soát truy cập. Trong ví dụ code, `UUID.randomUUID` giúp tạo ID khó đoán hơn, nhưng **không đủ thay authentication/authorization**.

Biện pháp:

1. Dùng token/ID entropy đủ cao và scope tối thiểu.
2. Kiểm tra tenant/owner/permission từ **principal đã xác thực**.
3. Áp dụng TTL, revoke và rate limit.
4. Mã hóa data at rest và in transit theo chính sách.
5. Không đặt token nhạy cảm trong URL query, log hoặc analytics không kiểm soát.
6. Không cho recipient không cần thiết đọc toàn original.
7. Khi retry, **kiểm tra quyền tại thời điểm đọc lại**, không chỉ khi claim-in.
8. Ghi audit truy cập với ID tham chiếu/masked value, không nhất thiết ghi token thô.

### 18.2. Retry không được vượt qua quyền truy cập

Ví dụ một nhân viên đã mất quyền xem dữ liệu đơn hàng sau lần claim-out đầu. Một retry chạy bằng cùng token cũ **không được dùng token để bỏ qua chính sách quyền mới** nếu hệ thống yêu cầu reauthorization.

Ngược lại, với retry máy–máy đã được xác thực, cần biết worker/tenant nào được quyền xử lý claim. Một token bị revoke không thể được “sửa” bằng cách copy dữ liệu từ cache cá nhân và phát hành token khác.

### 18.3. Token và metadata trong error channel

`ErrorMessage` có thể chứa `Throwable` và thông tin về failed message tùy execution context. Nếu failed message chứa claim token, log toàn bộ exception chain có thể làm lộ ID dùng để truy cập payload.

Nên log:

~~~text
event=CLAIM_RESTORE_FAILED
  operationRef=PAY-ORD-1
  claimRefHash=...
  tenantScope=TENANT-A
  code=EXPIRED
  retryable=false
~~~

Đây là schema log đề xuất, không phải log mặc định Spring Integration. Nếu retention/forensic policy yêu cầu lưu thêm, phải giới hạn quyền và không ghi nguyên payload nhạy cảm bừa bãi.

## 19. Observability: phân biệt claim đã dùng và operation đã hoàn tất

### 19.1. Các mốc cần quan sát

~~~text
event=CLAIM_ISSUED
  operationId=PAY-ORD-1 claimRefHash=...
  ttlSeconds=900

event=CLAIM_RESTORED
  operationId=PAY-ORD-1 attempt=1
  removeOnRead=false

event=BUSINESS_ACTION_STARTED
  operationId=PAY-ORD-1 attempt=1

event=BUSINESS_ACTION_OUTCOME_UNKNOWN
  operationId=PAY-ORD-1 reason=REMOTE_REPLY_TIMEOUT

event=CLAIM_RESTORED
  operationId=PAY-ORD-1 attempt=2
  removeOnRead=false

event=BUSINESS_ACTION_RECONCILED
  operationId=PAY-ORD-1 status=COMPLETED

event=CLAIM_CLEANUP_COMPLETED
  operationId=PAY-ORD-1 claimRefHash=...

event=CLAIM_REDELIVERED
  operationId=PAY-ORD-1 attempt=3
  handling=RETURN_EXISTING_RECEIPT
~~~

**Đây là sự kiện ứng dụng đề xuất**, không phải các dòng log framework tự cung cấp. Chúng cho biết **claim lifecycle** và **business operation lifecycle** riêng biệt.

### 19.2. Metrics nên tách lớp

| Metric minh họa | Đo điều gì? |
|---|---|
| `claim_issued_total` | Số claim tạo mới. |
| `claim_restore_total{result}` | Restore thành công/thất bại theo mã lỗi. |
| `claim_consumed_total` | Claim bị dùng theo chế độ one-time. |
| `claim_expired_total` | Claim hết hạn được phát hiện. |
| `claim_missing_total` | Không tìm thấy claim tại store. |
| `claim_reissued_total` | Replay tạo claim mới được phê duyệt. |
| `claim_cleanup_pending` | Số claim chờ cleanup. |
| `claim_cleanup_failed_total` | Cleanup lỗi, có thể vi phạm retention. |
| `claim_payload_bytes` | Kích thước payload đang lưu/được đọc. |
| `claim_store_latency_seconds` | Độ trễ đọc/ghi store. |
| `claim_store_errors_total{reason}` | DB timeout, unavailable, capacity, serialization... |
| `operation_completed_total` | Business operation xác nhận hoàn tất. |
| `operation_duplicate_prevented_total` | Retry/redelivery được xử lý không tạo side effect lặp. |
| `operation_outcome_unknown_total` | Lần xử lý cần reconciliation. |
| `claim_retry_exhausted_total` | Hết số retry mà chưa thể phục hồi. |
| `claim_orphan_age_seconds` | Tuổi của claim chưa có consumer/outcome. |

Các tên metric là **gợi ý**. Kiểm tra meter mặc định của Spring Integration/Micrometer theo version, tránh đếm trùng semantics. Không dùng `claimId`, `operationId` hay `customerId` làm metric labels có cardinality cao; dùng log/tracing có quyền truy cập phù hợp.

### 19.3. Cách hiểu một số liệu

| Tín hiệu | Có thể kết luận | Chưa thể kết luận |
|---|---|---|
| Claim được issue | Đã có attempt tạo reference. | Token đã được broker giao thành công. |
| Claim restore thành công | Payload được tìm thấy, validate/authorize theo contract. | Payment đã commit. |
| Claim bị consumed | Token không còn được phép đọc lại theo policy. | Business operation đã thành công. |
| Completion ledger ghi SUCCESS | Có receipt theo contract ledger. | Remote side effect tuyệt đối không lặp nếu ledger không đáng tin. |
| Cleanup thành công | Payload đã được xóa ở store tương ứng. | Mọi replica/cache/backup đã hết retention. |
| Broker ack thành công | Transport ghi nhận ack theo semantics cấu hình. | Không có duplicate trong toàn hệ thống. |

### 19.4. Message History và provenance

Spring Integration Message History có thể giúp thấy một message đã đi qua Claim Check In/Out, Transformer, Router, Gateway hoặc handler nào khi tracking được bật. Nhưng nó **không tự cho biết**:

- Claim đã thực sự được xóa khỏi Message Store hay chưa.
- Hệ thống đích đã commit payment hay chưa.
- Completion ledger có cùng kết quả với remote side effect hay không.
- Claim có bị đọc bởi tenant khác hay không.
- Retry nào dùng claim cũ, retry nào reissue claim mới theo policy.

Vì vậy cần kết hợp **claim metadata, operation ledger, transport status, structured logs, trace/correlation và audit store** thay vì chỉ dựa vào Message History.

## 20. Ma trận kiểm thử cho claim đã dùng và retry

| ID | Kịch bản | Kết quả mong đợi | Điều không được xảy ra |
|---|---|---|---|
| CC-01 | Claim-in original hợp lệ | Store chứa original, trả token hợp lệ. | Token trỏ đến record không có. |
| CC-02 | Claim-out reusable lần đầu | Trả payload đúng, record còn. | Xóa sớm. |
| CC-03 | Claim-out reusable lần thứ hai | Trả cùng dữ liệu theo contract. | Bất ngờ NOT_FOUND. |
| CC-04 | One-time `take` lần đầu | Trả payload và consume. | Hai caller cùng lấy được từ atomic store. |
| CC-05 | Retry token đã one-time consume | NOT_FOUND/ALREADY_USED theo metadata. | Tự bịa payload mới. |
| CC-06 | Downstream lỗi trước commit, reusable claim còn | Retry có thể restore lại. | Claim bị xóa trong `finally`. |
| CC-07 | Downstream đã commit, reply mất | Reconcile/idempotency trả receipt cũ. | Charge lại mù. |
| CC-08 | Claim cleanup sau completion, broker redeliver | Completion ledger trả existing result. | Cố restore rồi charge lại. |
| CC-09 | Claim missing, không có receipt | Fail closed/reconcile/quarantine. | Khẳng định SUCCESS vô căn cứ. |
| CC-10 | Token đã expired nhưng record còn | EXPIRED, không trả payload. | Bỏ qua TTL khi retry. |
| CC-11 | Store TTL đã xóa record | NOT_FOUND hoặc tombstone-specific status. | Coi lỗi là payment success. |
| CC-12 | Token bị revoke | Access denied theo policy. | Reissue để né revoke. |
| CC-13 | Tenant khác dùng token | ACCESS_DENIED. | Rò rỉ original. |
| CC-14 | Claim ID hợp lệ nhưng operationId bị tráo | Detect mismatch. | Dùng claim để chạy operation khác. |
| CC-15 | Claim data malformed | Validation failure. | Đưa payload hỏng vào payment. |
| CC-16 | Claim Store tạm unavailable | Retryable infrastructure error. | Biến thành permanent NOT_FOUND. |
| CC-17 | Claim Store full | Backpressure/alert/recovery. | Silent drop token hoặc payload. |
| CC-18 | Claim-in persisted nhưng token chưa publish | Orphan detection/outbox recovery. | Giữ vô hạn không biết chủ. |
| CC-19 | Token publish nhưng claim chưa commit | Outbox/transaction ngăn sai contract. | Consumer nhận dangling token. |
| CC-20 | Outbox relay publish cùng token hai lần | Consumer idempotency hoạt động. | Hai side effect. |
| CC-21 | Hai worker đồng thời dùng reusable claim | Operation idempotency/fencing. | Hai charge độc lập. |
| CC-22 | Hai worker atomic take one-time | Tối đa một worker lấy được payload. | Cả hai cùng consume. |
| CC-23 | Worker atomic take rồi crash trước commit | Recovery nhận diện claim consumed/outcome unknown. | Tuyên bố thành công. |
| CC-24 | Hai claim khác nhau cùng operationId | Dedupe/reconcile theo operation. | Hai business charges. |
| CC-25 | Hai claim cùng operationId nhưng payload khác | OPERATION_CONFLICT. | Dùng receipt của payload khác. |
| CC-26 | Retry qua Gateway bị timeout | Kiểm tra trạng thái operation. | Giả định worker đã cancel. |
| CC-27 | Filter drop token sau claim-in | Cleanup/orphan handling. | Giữ claim vô hạn. |
| CC-28 | Scatter hai recipients dùng same one-time claim | Thiết kế bị phát hiện sai; đổi policy. | Chỉ nhánh nhanh nhất có payload nhưng báo all success. |
| CC-29 | Splitter ba items, một claim bị consumed | Outcome/error đủ để Aggregator release đúng. | Chờ thiếu phần mãi. |
| CC-30 | Resequencer buffer token qua TTL | Expiration/quarantine/reissue theo policy. | Release token cũ rồi coi success. |
| CC-31 | Header mapping qua broker | Claim identity, correlation, tenant policy preserved. | Serialize replyChannel JVM hoặc mất ID. |
| CC-32 | Group/operation restart sau crash | Durable store + ledger recovery đúng. | Mất dữ liệu âm thầm. |
| CC-33 | Cleanup job fail sau business SUCCESS | Retry cleanup riêng. | Charge lại vì cleanup failure. |
| CC-34 | Claim quá lớn/số claims quá nhiều | Size/capacity controls. | OOM hoặc store exhaustion. |
| CC-35 | Redelivery sau tombstone retention | Chính sách replay horizon được xác định. | Coi late token là operation mới. |
| CC-36 | Retry message sau khi quyền tenant bị thu hồi | Reauthorization từ trusted principal. | Lấy payload nhờ token cũ. |
| CC-37 | Test cùng claim qua hai JVM | Consistent store & idempotency thật. | Chỉ tin fake map in-memory. |
| CC-38 | Parallel retry có một attempt trả lỗi muộn | State machine/version bảo vệ completed result. | Lỗi cũ ghi đè SUCCESS. |
| CC-39 | Completion ledger stale hoặc unavailable | Không tự tạo duplicate charge. | Đoán success/not-found. |
| CC-40 | Backup/replica còn payload sau cleanup | Retention/data deletion policy đúng. | Tưởng dữ liệu đã được xóa ở mọi nơi. |

### 20.1. Kiểm thử ở tầng nào?

| Cấp test | Giá trị | Không đủ để chứng minh |
|---|---|---|
| **Unit test claim repository/service** | Restore, take, TTL, tenant, lỗi missing. | DB/transport thật, durability qua restart. |
| **Unit test workflow/ledger** | Retry behavior và idempotency fake. | Remote API xử lý duplicate thực tế. |
| **Spring Integration test** | Gateway, Transformer, reply/error path, channel. | Broker ack/re-delivery nếu không dùng broker. |
| **Adapter integration test** | Store/broker headers, serialization, retry advice scope. | Remote payment thật nếu chỉ mock. |
| **System/recovery test** | Crash windows, replay, outbox, cleanup, reconciliation. | Mọi failure mode production ngoài test. |
| **Security test** | Tenant authorization, token guessing, expiry, revoke. | Mọi rủi ro truy cập nếu chưa review trust boundary. |

Nên có ít nhất một test ở mỗi tầng **mà yêu cầu production thật sự phụ thuộc**. Không kết luận chắc chắn an toàn chỉ vì fake `ConcurrentHashMap` bảo đảm một operation trong cùng JVM.

## 21. Quy trình chẩn đoán: retry báo “claim not found”

Một consumer log:

~~~text
CLAIM_RESTORE_FAILED
  operationId=PAY-ORD-1
  code=NOT_FOUND
  deliveryAttempt=2
~~~

Hãy điều tra có hệ thống:

1. **Xác nhận token:** `claimId`, operation ID, tenant/group ID có đúng không? Message có bị biến đổi khi qua adapter không?
2. **Tìm trạng thái operation:** completion ledger hoặc remote service có receipt thành công không? Nếu có, xử lý duplicate thay vì charge lại.
3. **Đọc claim lifecycle:** token được issue lúc nào, có bị consumed, revoked hoặc expired không?
4. **Kiểm tra remove-on-get:** Claim Check Out có xóa ở lần đọc đầu không? Retry đang lặp đoạn nào?
5. **Kiểm tra Message Store:** đang trỏ đúng datasource/schema/shard/node không? Store có in-memory và process vừa restart không?
6. **Kiểm tra outbox/commit:** token có được publish trước khi original record commit không?
7. **Kiểm tra TTL:** retry delay + queue backlog + group buffer có dài hơn retention không?
8. **Kiểm tra race:** worker khác có lấy/xóa claim hoặc dọn cleanup sớm không?
9. **Kiểm tra error handling:** lỗi store unavailable có bị map nhầm thành NOT_FOUND không?
10. **Kiểm tra nguyên bản dữ liệu:** có nguồn replay được ủy quyền, đúng schema version và checksum không?
11. **Chọn recovery:** return existing receipt, retry restore khi store hồi phục, reissue theo policy, quarantine hoặc manual investigation.
12. **Bổ sung hồi quy:** tạo test tái hiện đúng cửa sổ lỗi và theo dõi metric claim missing/consumed/replay.

### 21.1. Phân biệt ba trường hợp dễ bị gộp nhầm

~~~text
Case A:
  claim missing + operation completed
  -> duplicate success acknowledgement / existing receipt

Case B:
  claim missing + operation unknown + replay source trusted
  -> reconcile, authorize, possibly reissue

Case C:
  claim missing + operation unknown + no replay source
  -> blocked/quarantine/manual action
  -> KHÔNG tạo fake success
~~~

Không nên sửa một lỗi `NOT_FOUND` bằng cách tăng số lần retry ngay lập tức: claim đã bị xóa vĩnh viễn thì retry 100 lần cũng không làm record xuất hiện lại. Phải tìm nguyên nhân và nguồn phục hồi hợp lệ.

## 22. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách thiết kế phù hợp |
|---|---|---|
| “Claim Check Out đọc được tức là payment thành công.” | Xóa payload trước khi downstream commit. | Tách read, completion và cleanup. |
| “One-time claim vẫn retry nguyên token bao nhiêu lần cũng được.” | Lần sau không còn payload. | Chọn reusable hoặc replay source rõ. |
| “Cứ bật retry advice quanh toàn flow.” | Lặp claim-out đã remove và báo NOT_FOUND. | Đặt retry đúng endpoint/scope. |
| “Claim ID và operation ID là một.” | Tạo claim mới sẽ né dedupe. | Dùng stable business idempotency key. |
| “Claim ID không đoán được thì không cần authorization.” | Lộ dữ liệu nếu token bị lộ/đoán/truyền nhầm. | AuthN/AuthZ, tenant, scope, TTL. |
| “Message Store in-memory là durable.” | Restart mất payload dù token đã phát. | Persistent store/ack/recovery nếu cần. |
| “Read-and-remove là transaction thanh toán.” | Crash sau consume gây mất khả năng retry. | Dùng idempotency/lease/reconciliation. |
| “Lỗi timeout nghĩa là payment chưa commit.” | Retry có thể charge hai lần. | Query remote status/idempotency. |
| “Ghi completion ledger sau charge luôn an toàn.” | Crash giữa hai thao tác làm trạng thái UNKNOWN. | Remote idempotency + reconcile/outbox/inbox. |
| “Có ledger là không cần kiểm tra payload.” | Hai payload khác nhau dùng chung operation key. | Operation fingerprint/conflict detection. |
| “Hai worker có thể cùng đọc claim nhưng không thể cùng xử lý.” | Hai side effects đồng thời. | Operation state + remote idempotency/lease. |
| “Xóa claim sau success thì mọi retry phải lỗi.” | Duplicate hợp lệ bị báo sai. | Kiểm tra completion trước claim-out. |
| “NOT_FOUND luôn có nghĩa đã CONSUMED.” | Che lỗi store/shard/issue hoặc token giả. | Tombstone và phân loại trạng thái. |
| “Expired claim chỉ cần gia hạn tự động.” | Vượt retention/authorization hiện tại. | Reauthorize/reissue theo policy. |
| “Revoke có thể bỏ qua khi retry.” | Vi phạm quyền truy cập. | Chặn và audit, không reissue mù. |
| “Cùng one-time token có thể cho nhiều Scatter recipients.” | Chỉ reader đầu tiên nhận được original. | Reusable hoặc per-recipient claims. |
| “Resequencer release token tức claim còn hạn.” | Token có thể expired trong buffer. | Đồng bộ TTL và gap/retry horizon. |
| “Filter drop token không cần cleanup.” | Orphan claim giữ dữ liệu vô ích. | Cleanup/TTL/orphan monitoring. |
| “Cleanup job lỗi phải chạy lại payment.” | Tạo side effect trùng. | Retry cleanup độc lập. |
| “Đã delete ở primary là xóa sạch mọi bản sao.” | Backup/cache vẫn còn dữ liệu. | Retention/replica/data deletion policy. |
| “Có `errorChannel` là mọi missing claim sẽ được repair.” | Poison token retry vô hạn. | Recovery policy theo code và durable replay source. |
| “Có Message History là biết claim đã xóa.” | History không thay DB lifecycle. | Claim/ledger audit riêng. |
| “Toàn bộ original MessageHeaders an toàn để gửi sang JVM khác.” | replyChannel/errorChannel stale hoặc không serialize được. | Header mapping và wire metadata có chủ đích. |
| “Chỉ cần happy-path integration test.” | Không phát hiện consume-before-failure/restart race. | Tests cho failure windows và duplicate. |

## 23. Bài tập thực hành

1. **One-time consume:** tạo claim, gọi `take`, giả lập downstream lỗi, thử restore cùng ticket. Ghi rõ tại sao báo `NOT_FOUND`.
2. **Reusable read:** đổi code sang `find`, gọi restore hai lần trong TTL và xác nhận payload gốc giữ nguyên.
3. **Completion-aware:** xử lý thành công, cleanup claim, gửi lại token và trả receipt cũ từ ledger mà không charge lại.
4. **Transient payment error:** fake payment throw lần đầu trước commit, lần hai thành công. Xác minh claim vẫn được restore ở lần hai.
5. **Commit-but-reply-lost:** fake payment đã ghi success nhưng caller nhận timeout. Thiết kế reconciliation và test không gọi side effect lần hai.
6. **TTL:** dùng `Clock.fixed` để tạo token có TTL 10 phút, đọc ở phút 11 và assert `EXPIRED` mà không sleep.
7. **Tombstone:** thêm bảng trạng thái claim `AVAILABLE/CONSUMED/COMPLETED/EXPIRED` để phân biệt lỗi khi record payload đã bị xóa.
8. **Cross-tenant:** thử restore token của `TENANT-A` bằng principal `TENANT-B`; xác nhận ACCESS_DENIED và không trả dữ liệu.
9. **Forged ticket:** giữ claimId nhưng thay operationId; kiểm tra service từ chối ticket không khớp record.
10. **Revocation:** thêm trạng thái revoke, xác minh retry và replay không được vượt quyền.
11. **Idempotency conflict:** cùng operationId nhưng amount khác, bổ sung fingerprint và trả `OPERATION_CONFLICT`.
12. **Concurrent readers:** cho hai thread đồng thời restore reusable claim; chứng minh cả hai đọc được, nhưng payment fake chỉ tạo một operation.
13. **Lease/fencing:** mô phỏng Worker A bị pause quá hạn, Worker B nhận lease mới. Chặn A commit với fencing token cũ.
14. **Native Spring Claim Check:** tạo flow dùng Claim Check In/Out Transformer và Message Store phù hợp phiên bản. Kiểm thử hành vi giữ/xóa trên hai lần đọc.
15. **Retry scope:** đặt advice chỉ quanh payment rồi so với advice quanh claim-out + payment. Giải thích kết quả khi remove-on-read.
16. **Broker redelivery:** gửi cùng token qua transport hai lần; xác minh một business receipt, không chỉ hai message được nhận.
17. **Transactional outbox:** mô phỏng crash sau lưu claim nhưng trước publish; xác minh outbox relay có thể phát token sau recovery.
18. **Orphan claim:** Filter reject sau claim-in, viết cleanup/TTL job với audit và metric.
19. **Scatter–Gather:** cho Inventory và Fraud dùng cùng one-time claim; tái hiện lỗi, sau đó sửa bằng reusable claim hoặc hai claims khác nhau.
20. **Resequencer:** giữ token tới sau TTL; xác minh late claim-out trả expired và có recovery policy.
21. **Splitter/Aggregator:** tách batch thành ba claims, làm một claim bị xóa sớm, tạo outcome lỗi thay vì khiến group chờ vô hạn.
22. **Gateway timeout:** cho remote worker tiếp tục xử lý sau khi caller timeout; test retry operation không tạo side effect mới.
23. **Restart:** chuyển in-memory store sang persistent store, mô phỏng restart giữa issue và claim-out; kiểm tra token vẫn đọc được.
24. **Serialization:** đưa token qua JSON/Kafka/HTTP adapter, kiểm tra claimId/operationId/correlation và loại bỏ internal replyChannel không wire-portable.
25. **Observability:** tạo log `CLAIM_ISSUED`, `CLAIM_RESTORED`, `OPERATION_OUTCOME_UNKNOWN`, `CLAIM_CLEANUP_COMPLETED`; dựng dashboard claim missing, completed và orphan.
26. **Security:** giới hạn payload size, rate-limit restore endpoint và bảo vệ token trong logs, tracing, dead-letter queue.
27. **Data deletion:** kiểm tra dữ liệu claim được dọn khỏi primary, cache và backup theo retention policy đã phê duyệt.
28. **Recovery runbook:** viết flow xử lý rõ `NOT_FOUND+COMPLETED`, `NOT_FOUND+UNKNOWN`, `EXPIRED`, `ACCESS_DENIED` và `STORE_UNAVAILABLE`.

### Tiêu chí hoàn thành bài thực hành

Một implementation đúng nên trả lời được:

- Claim có được **đọc lại sau claim-out** không? Hành vi có được test theo cấu hình remove thực không?
- Message retry bắt đầu từ bước nào và có lặp claim-out không?
- Sau khi operation đã commit và claim bị xóa, **duplicate token** được xử lý thế nào?
- Một lỗi store unavailable có bị nhầm với claim missing không?
- Nếu payload đã mất, có nguồn replay được ủy quyền và đúng version không?
- Claim ID, operation ID, tenant và attempt ID có được phân biệt không?
- Retry có tạo side effect trùng dưới concurrency/crash không?
- Có TTL, capacity, cleanup, tombstone và revoke policy không?
- Có thể truy nguyên một message từ claim-in đến business outcome và cleanup không?
- Đã test đúng broker/store/payment boundary mà production sử dụng chưa?

## 24. Câu hỏi tự kiểm tra

**Câu 1:** Claim Check Out đã lấy payload lần đầu, dùng `remove-on-get`; payment timeout. Retry cùng claim ID có chắc lấy lại payload không?

**Không.** Nếu claim đã được remove, retry có thể nhận NOT_FOUND/ALREADY_CONSUMED. Phải kiểm tra completion và replay policy hoặc thiết kế read-without-remove.

**Câu 2:** Claim-out không remove thì hai lần retry có thể gây charge hai lần không?

**Có thể.** Reusable claim chỉ giữ dữ liệu; cần operation-level idempotency tại nơi tạo side effect.

**Câu 3:** Vì sao “restore thành công” không bằng “payment thành công”?

Vì restore chỉ trả payload từ store. Downstream còn có thể timeout, throw hoặc commit thất bại.

**Câu 4:** Claim đã delete, broker redeliver token, completion ledger có SUCCESS. Nên làm gì?

Nếu receipt được xác thực/ủy quyền và khớp operation, có thể trả receipt cũ hoặc acknowledge duplicate mà không gọi payment lần nữa.

**Câu 5:** Claim không tồn tại, completion ledger cũng không có. Có thể coi là claim đã dùng thành công không?

**Không.** Có nhiều nguyên nhân NOT_FOUND. Cần điều tra/reconcile, hoặc replay từ nguồn hợp lệ khi được phép.

**Câu 6:** `claimId` có thể thay đổi khi operator reissue, nhưng `operationId` nên thế nào?

Nếu retry cùng business operation, operationId nên ổn định để dedupe. Nếu tạo operation mới thật sự, phải có hợp đồng và ID mới rõ ràng.

**Câu 7:** Vì sao thử lại toàn flow khác retry chỉ payment endpoint?

Retry toàn flow có thể lặp cả claim-out và xóa claim ở lần đầu; retry payment riêng trong cùng attempt có thể dùng payload đã restore mà không đọc lại store.

**Câu 8:** Claim được lưu thành công nhưng publish token thất bại. Điều gì xảy ra?

Có thể tạo orphan claim. Outbox/recovery/cleanup giúp tránh mất token hoặc lưu dữ liệu vô hạn.

**Câu 9:** Payment đã commit nhưng response thất lạc. Lần retry có thể mặc định charge lại không?

**Không.** Phải dùng idempotency key hoặc truy vấn/reconcile trạng thái trước khi tạo thêm side effect.

**Câu 10:** One-time claim có đủ cho hai recipient Inventory và Fraud cùng cần dữ liệu không?

**Không mặc định.** Một recipient có thể consume trước khiến recipient kia không lấy được. Cân nhắc reusable hoặc scoped claims riêng.

**Câu 11:** Claim TTL 5 phút, Resequencer buffer token 10 phút. Resequencer release có chứng minh claim còn tồn tại không?

**Không.** Message token có thể được release đúng thứ tự nhưng payload đã hết hạn; phải đồng bộ retention và gap/retry policy.

**Câu 12:** `ConcurrentHashMap.computeIfAbsent` trong fake payment có bảo đảm exactly-once khi chạy nhiều JVM và HTTP payment thật không?

**Không.** Nó chỉ minh họa dedupe trong một process; distributed side effect cần ranh giới idempotency/transaction và recovery phù hợp.

**Câu 13:** Tại sao không xóa claim trong khối `finally` của payment handler?

Vì `finally` chạy cả khi handler lỗi; payload có thể biến mất trước khi retry có cơ hội khôi phục.

**Câu 14:** Một claim bị revoke có thể reissue ngay vì có retry request không?

**Không.** Reissue phải kiểm tra lý do thu hồi và quyền hiện tại, không né bảo mật.

**Câu 15:** Message Store có dữ liệu bền vững rồi thì còn cần idempotency không?

**Cần.** Store bảo vệ payload, còn idempotency bảo vệ side effect khi message/redelivery được xử lý lặp.

**Câu 16:** ErrorMessage có chứa claim token có thể log toàn bộ không?

Không nên mặc định. Claim ID có thể dẫn đến dữ liệu nhạy cảm; nên dùng reference đã che/hashed và policy log phù hợp.

**Câu 17:** Completion record và cleanup record là một trạng thái không?

**Không.** Payment đã hoàn tất nhưng claim còn chờ xóa là tình huống hợp lệ; cleanup failure không đồng nghĩa business failure.

**Câu 18:** Nếu cùng operation ID có hai payload khác nhau, có được trả receipt cũ cho payload mới không?

**Không mặc định.** Phải kiểm tra operation fingerprint/provenance và trả conflict khi dữ liệu không khớp.

## 25. Kết luận

**Retry message với claim đã dùng** là bài toán về **vòng đời dữ liệu và kết quả nghiệp vụ**, không chỉ là tăng số lần retry. Với Claim Check, payload được lưu tách khỏi message lưu chuyển và được truy xuất bằng token. Nếu bước claim-out **tiêu thụ/xóa claim trước khi downstream hoàn tất**, retry cùng token có thể không còn dữ liệu; nếu giữ claim cho phép đọc lại, vẫn phải chống **side effect trùng** khi broker redeliver hoặc nhiều worker chạy đồng thời.

Trong Spring Integration, hãy kiểm tra rõ **Claim Check In/Out Transformer, Message Store, hành vi remove-on-read, retry advice scope, Gateway timeout, error channel, header mapping và transaction boundary**. Với nghiệp vụ quan trọng, ưu tiên thiết kế dễ phục hồi: **lưu payload bền vững, issue token có kiểm soát, restore không xóa quá sớm, dùng stable operationId/idempotency, ghi completion có thẩm quyền và cleanup sau đó**. Nếu claim đã consumed, expired hoặc revoked, recovery phải dựa trên completion/tombstone và nguồn replay được phép — không suy luận thành công hay tự dựng lại dữ liệu.

Khi kết hợp Claim Check với Router, Filter, Splitter, Aggregator, Scatter–Gather, Resequencer, Transformer và Gateway trong `SPRING_INTEGRATION_PATTERN`, cần kiểm tra **mỗi nhánh có thể truy xuất original bao nhiêu lần, token còn hạn trong suốt retry/buffer horizon hay không, và kết quả nghiệp vụ đã được xác nhận ở đâu**. Một thiết kế đúng giúp message flow ít phụ thuộc, dễ mở rộng, có thể truy nguyên, phục hồi sau lỗi và không báo “thành công” chỉ vì một claim đã được đọc.
