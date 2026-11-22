# Phạm vi khóa, fingerprint yêu cầu và phát hiện tái sử dụng sai

## 1. Một khóa giống nhau chưa chắc là cùng một ý định

Giả sử client gọi **POST /api/v1/orders**. Database đã tạo đơn hàng **ord-501**, nhưng kết nối đứt trước khi client nhận phản hồi **201 Created**. Client retry với cùng **Idempotency-Key**. API cần nhận diện đây là lần gửi lại của **cùng ý định tạo đơn**, không tạo **ord-502**.

Ngược lại, một client có thể vô tình tái sử dụng khóa của đơn đầu cho đơn khác. Nếu server cứ trả kết quả cũ, client sẽ tưởng đơn mới đã được tạo; nếu cứ tạo đơn mới, cơ chế chống trùng mất tác dụng. Bài toán nằm ở ba quyết định:

1. **Phạm vi khóa (key scope):** một khóa là duy nhất đối với tenant, người dùng và loại thao tác nào?
2. **Fingerprint của request:** hai request có cùng khóa có mang cùng hiệu ứng nghiệp vụ không?
3. **Phát hiện tái sử dụng sai:** khi khóa đã gắn với một request khác, API từ chối và giải thích ra sao?

Bài này thuộc chương **Lũy đẳng và thử lại** của module **INTEGRATION_API_REST**: thiết kế REST dựa trên resource, URI, phương thức/mã HTTP và hợp đồng dữ liệu; thực hành idempotency, bảo mật, OpenAPI và kiểm thử bằng Java/Spring.

Sau bài học, bạn cần có thể thiết kế scope, canonical fingerprint, lưu trạng thái xử lý có tính nguyên tử, phân biệt retry hợp lệ với reuse sai, xử lý timeout sau commit và chứng minh hiệu quả bằng integration test đồng thời.

> Các lựa chọn ví dụ như **409 Conflict** cho key mismatch và **48 giờ** lưu record là **quy ước của API minh họa**, không phải quy tắc mặc định được mọi server HTTP thực thi. Đội thiết kế phải công bố mã lỗi, TTL và hành vi replay nhất quán.

## 2. Hợp đồng HTTP làm điểm xuất phát

Client tạo một khóa mới cho mỗi **ý định nghiệp vụ**, giữ nguyên khóa trong mọi lần thử lại của ý định đó.

~~~http
POST /api/v1/orders HTTP/1.1
Host: api.example.com
Authorization: Bearer <access-token>
Content-Type: application/json
Accept: application/json
Idempotency-Key: b0264990-ace7-4721-b420-c53dbf761d81

{
  "sku": "BOOK-42",
  "quantity": 2,
  "shippingAddressId": "addr-17"
}
~~~

Phản hồi lần đầu sau khi tạo thành công:

~~~http
HTTP/1.1 201 Created
Location: /api/v1/orders/ord-501
Content-Type: application/json
Cache-Control: no-store

{
  "id": "ord-501",
  "sku": "BOOK-42",
  "quantity": 2,
  "status": "PENDING"
}
~~~

Retry với **cùng key**, **cùng scope** và **cùng fingerprint** sẽ nhận lại kết quả đã lưu, ví dụ **201 Created** với cùng **Location: /api/v1/orders/ord-501** và cùng body. Hệ thống không tạo thêm đơn hoặc phát thêm sự kiện nghiệp vụ tạo đơn.

**Idempotency-Key không làm POST trở thành phương thức idempotent mặc định của HTTP.** Đó là một hợp đồng bổ sung giữa client và server; cả hai phải thống nhất quy tắc key, phạm vi, thời hạn và xung đột.

## 3. Scope: khóa thuộc về ai và thao tác nào?

Nếu chỉ lưu **key → response** trong một bảng chung, hai tenant có cùng chuỗi key có thể vô tình nhận nhầm kết quả của nhau. Một key cũng có thể bị dùng lại cho thao tác khác như tạo thanh toán, hoàn tiền hoặc shipment.

Hợp đồng của bài này chọn:

~~~text
idempotencyIdentity = (
    authenticatedTenantId,
    operationId,
    idempotencyKey
)

operationId = "orders.create.v1"
~~~

Ví dụ:

| Scope | Kết luận |
| --- | --- |
| **(T1, orders.create.v1, K-001)** | Một ý định thuộc T1 tạo đơn |
| **(T2, orders.create.v1, K-001)** | Scope khác; không replay kết quả của T1 |
| **(T1, shipments.create.v1, K-001)** | Operation khác; không replay kết quả tạo đơn |
| **(T1, orders.create.v1, K-001)** lần hai | Cùng scope; cần so fingerprint |

**authenticatedTenantId** phải đến từ principal/token đã xác thực hoặc membership đã kiểm tra. Không được tin giá trị tenant do client tự gửi trong body rồi dùng nó để đọc idempotency record.

### Chọn tenant hay principal làm phạm vi?

Nếu một người tạo đơn và một service account thuộc cùng tenant được phép retry thay, scope **theo tenant** có thể phù hợp hơn scope theo access token hoặc ID người dùng. Ngược lại, nếu hai người trong một tenant không được phép xem dữ liệu của nhau, cần đưa boundary sở hữu vào scope hoặc kiểm soát quyền chặt chẽ khi tra/replay.

**Scope không thay authorization.** Một key đúng không phải vé truy cập: server phải kiểm tra người gọi **hiện tại** có quyền tạo/xem kết quả trong phạm vi đó, nhất là sau khi tài khoản bị thu hồi quyền.

### Không phụ thuộc mù quáng vào raw URL

**POST /v1/orders** và **POST /api/v1/orders** có thể là cùng thao tác sau reverse proxy. Nếu key scope được tạo từ raw URL mà không chuẩn hóa, client có thể gửi lại qua đường dẫn khác rồi bị coi là lệnh mới. Dùng **operationId do server định nghĩa** giúp ổn định hợp đồng qua thay đổi gateway.

Ngược lại, **staging** và **production** phải có phạm vi/lưu trữ idempotency tách biệt; không chia sẻ record chỉ vì URL hoặc key trùng nhau. Nếu thay đổi ngữ nghĩa operation khi nâng phiên bản, cần xem xét operationId/version, không để key cũ vô tình ràng buộc một thao tác mới không tương thích.

## 4. Fingerprint: định danh nội dung nghiệp vụ, không phải byte JSON

**Fingerprint** là giá trị do server tính từ thông tin quyết định hiệu ứng của request. Với tạo đơn, những trường ảnh hưởng kết quả gồm:

- **sku** sau khi chuẩn hóa theo hợp đồng.
- **quantity**.
- **shippingAddressId**.
- Những trường khác nếu có: **couponCode**, **currency**, delivery option, thông số query hoặc header mang ý nghĩa nghiệp vụ.

Hai body này có thể tương đương vì thứ tự thuộc tính JSON không làm thay đổi giá trị:

~~~json
{"sku":"BOOK-42","quantity":2,"shippingAddressId":"addr-17"}
~~~

~~~json
{"shippingAddressId":"addr-17","quantity":2,"sku":"BOOK-42"}
~~~

Nếu băm trực tiếp **raw HTTP body bytes**, chúng sẽ có hash khác nhau không cần thiết. Cách tốt hơn: **parse JSON → validate thành DTO có kiểu → chuẩn hóa theo quy tắc thực thi → serialize canonical → hash**.

| Thay đổi request | Fingerprint nên thế nào? | Lý do |
| --- | --- | --- |
| Chỉ đảo thứ tự thuộc tính hoặc thêm whitespace JSON | **Giống** | Không đổi ý nghĩa JSON object |
| Thay quantity từ 2 thành 3 | **Khác** | Đổi số lượng đơn |
| Đổi shippingAddressId | **Khác** | Đổi địa chỉ giao hàng |
| SKU từ book-42 sang BOOK-42 | **Có thể giống** | Chỉ khi business thực sự normalize SKU không phân biệt hoa/thường |
| Đổi couponCode có hiệu lực | **Khác** | Đổi giá/ưu đãi |
| Thay trace ID, thời điểm retry hoặc access token | **Thường giống** | Không ảnh hưởng cùng ý định nghiệp vụ |
| Gửi thêm trường JSON không được hỗ trợ | **Từ chối theo schema** | Không âm thầm bỏ qua input client tưởng có tác động |

**Bất biến quan trọng:** thuật toán canonicalization phải **khớp logic lưu dữ liệu**. Nếu fingerprint coi hai SKU tương đương nhưng service lại lưu theo hai cách khác nhau, hash sẽ không phản ánh hiệu ứng. Không chuẩn hóa quá mức: thứ tự mảng, chữ hoa/thường hay khoảng trắng có thể có ý nghĩa đối với một số tài nguyên.

### Fingerprint của API cần có phiên bản

Giả sử API bổ sung **deliveryMethod** sau triển khai mới. Request cũ trong TTL chưa có field đó có thể bị coi mismatch nếu triển khai mới dùng canonical form khác.

Nên lưu **fingerprintVersion** (ví dụ 1), giữ thuật toán tương ứng để so request retry của key cũ, dùng version mới cho key mới. Việc thay đổi canonicalization qua rolling deployment phải được kiểm thử như một thay đổi hợp đồng, không chỉ là refactor.

## 5. Reuse sai: chặn trước khi chạy nghiệp vụ

Client giữ nguyên key nhưng đổi quantity:

~~~http
POST /api/v1/orders HTTP/1.1
Content-Type: application/json
Idempotency-Key: b0264990-ace7-4721-b420-c53dbf761d81

{
  "sku": "BOOK-42",
  "quantity": 3,
  "shippingAddressId": "addr-17"
}
~~~

API minh họa chọn **409 Conflict**, với Problem Details có mã ổn định:

~~~http
HTTP/1.1 409 Conflict
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type": "https://api.example.com/problems/idempotency-key-reused",
  "title": "Idempotency key reused",
  "status": 409,
  "detail": "Khóa đã gắn với một yêu cầu có nội dung nghiệp vụ khác.",
  "code": "IDEMPOTENCY_KEY_REUSED"
}
~~~

Một số API dùng **422** cho trường hợp này; mã phải được chọn và tài liệu hóa thống nhất. Trong bài này dùng **409** để phân biệt xung đột scope/key và kiểm thử được.

**Không thực thi lệnh mới và không replay 201 cũ khi fingerprint khác.** Nếu replay kết quả cũ, client có thể hiểu nhầm rằng đơn quantity=3 đã được tạo; nếu tạo mới, cơ chế idempotency đã bị phá.

### Mismatch khác trạng thái đang xử lý

| Scope/key | Fingerprint | Record | Response/hành vi |
| --- | --- | --- | --- |
| Chưa có | Hợp lệ | Chưa có | Claim, tạo và lưu kết quả |
| Đã có | Giống | **COMPLETED** | Replay 201, Location và body |
| Đã có | Khác | **COMPLETED** | **409 IDEMPOTENCY_KEY_REUSED** |
| Đã có | Giống | **IN_PROGRESS** | Chờ hữu hạn hoặc **409 IDEMPOTENCY_IN_PROGRESS** theo contract |
| Đã có | Khác | **IN_PROGRESS** | **409 IDEMPOTENCY_KEY_REUSED** |
| Key mới | Bất kỳ hợp lệ | Chưa có trong scope đó | Ý định mới; vẫn phải kiểm tra business uniqueness |
| Key trùng chuỗi, scope khác | Bất kỳ | Record độc lập | Không replay xuyên tenant/operation |

Nếu API trả **409 IN_PROGRESS**, có thể kèm **Retry-After** và cho client retry cùng key/payload sau backoff. **409 KEY_REUSED không phải tín hiệu để retry mù quáng**; client phải kiểm tra key, payload và ý định người dùng.

## 6. Điểm claim phải nguyên tử

Các request cùng key có thể vào hai API pod cùng lúc. Code kiểu sau có race condition:

~~~text
if key does not exist:
    createOrder()
    saveKey()
~~~

Hai pod cùng thấy key chưa tồn tại, cùng tạo hai đơn. Cơ chế đúng cần **unique constraint hoặc thao tác claim nguyên tử** tại nguồn dữ liệu có thẩm quyền, không chỉ một cache hoặc khóa trong từng JVM.

Một bảng minh họa PostgreSQL:

~~~sql
CREATE TABLE idempotency_records (
    tenant_id         VARCHAR(80) NOT NULL,
    operation_id      VARCHAR(100) NOT NULL,
    idem_key          VARCHAR(120) NOT NULL,
    fingerprint_ver   INTEGER NOT NULL,
    request_hash      CHAR(64) NOT NULL,
    state             VARCHAR(20) NOT NULL,
    http_status       INTEGER,
    response_location TEXT,
    response_json     TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at        TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (tenant_id, operation_id, idem_key)
);
~~~

Key **(tenant_id, operation_id, idem_key)** biểu diễn chính xác scope được định nghĩa ở phần 3. Với account/user boundary phức tạp, schema phải mở rộng theo chính sách đã quyết định.

Claim bằng SQL PostgreSQL:

~~~sql
INSERT INTO idempotency_records (
    tenant_id, operation_id, idem_key,
    fingerprint_ver, request_hash, state, expires_at
) VALUES (
    :tenant, 'orders.create.v1', :key,
    1, :hash, 'IN_PROGRESS', NOW() + INTERVAL '48 hours'
)
ON CONFLICT (tenant_id, operation_id, idem_key)
DO NOTHING;
~~~

- Nếu thêm được **1 row**, request giành quyền thực thi.
- Nếu thêm **0 row**, scope/key đã có: đọc fingerprint/state đã commit và xử lý theo bảng phần 5.
- Nếu database lỗi/timeout, **không tự coi claim đã thành công**.

### Cùng transaction cho order, outbox và kết quả

Nếu tạo đơn là giao dịch đồng bộ ngắn trong cùng database, giữ ba hiệu ứng trong **một transaction**:

~~~text
BEGIN TRANSACTION
  Claim key bằng unique insert.
  Nếu key đã tồn tại: so fingerprint/state; không tạo order.

  Nếu claim thành công:
    INSERT order.
    INSERT outbox event OrderCreated.
    UPDATE idempotency_records
      SET state = COMPLETED,
          http_status = 201,
          response_location = ...,
          response_json = ...
COMMIT TRANSACTION
~~~

Như vậy **order, outbox và response mapping cùng commit hoặc cùng rollback**. Nếu HTTP response bị mất sau commit, retry đọc được kết quả gốc. Không ghi order xong rồi mới lưu idempotency record trong một transaction khác.

Trong **PostgreSQL READ COMMITTED**, request tranh một unique key có thể chờ transaction đối thủ hoàn tất; nếu claim không thêm row, câu **SELECT tiếp theo** có thể thấy record đã commit. Với isolation level hoặc database khác, cần kiểm chứng snapshot/locking và cơ chế retry transaction.

**IN_PROGRESS:** trong mô hình một transaction ngắn, state này thường chưa thể thấy như bản ghi đã commit giữa chừng. Nếu cần job chạy lâu và **commit claim trước**, phải thêm lease/owner token, timeout, reconciler và fencing để tránh hai worker xử lý cùng lúc. Không áp dụng mô hình transaction ngắn cho workflow nhiều giờ mà thiếu cơ chế phục hồi.

### Hệ thống bên ngoài transaction

Nếu tạo đơn còn gọi payment gateway hoặc gửi webhook, DB transaction không thể rollback side effect bên ngoài. Dùng **transactional outbox**, event ID, idempotency của đối tác và reconciliation. Kết quả cần bảo vệ là **một hiệu ứng nghiệp vụ**, không chỉ một row trong bảng orders.

## 7. Java: tính fingerprint theo dữ liệu đã chuẩn hóa

Ví dụ request DTO trong Java 17+:

~~~java
public record CreateOrderRequest(
    @NotBlank String sku,
    @Min(1) int quantity,
    @NotBlank String shippingAddressId
) {}
~~~

Hàm hash sau không phụ thuộc thứ tự property trong raw JSON vì nhận **DTO đã parse và validate**. Dạng canonical dùng mã hóa Base64url từng chuỗi để không nhập nhằng khi dữ liệu có ký tự phân cách.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.Base64;
import java.util.HexFormat;
import java.util.Locale;

public final class OrderFingerprint {
    private OrderFingerprint() {}

    private static String encode(String value) {
        return Base64.getUrlEncoder().withoutPadding()
            .encodeToString(value.getBytes(StandardCharsets.UTF_8));
    }

    public static String calculate(CreateOrderRequest request) {
        String normalizedSku =
            request.sku().trim().toUpperCase(Locale.ROOT);

        String canonical = String.join("\n",
            "orders.create.fp.v1",
            encode(normalizedSku),
            Integer.toString(request.quantity()),
            encode(request.shippingAddressId()));

        try {
            byte[] digest = MessageDigest.getInstance("SHA-256")
                .digest(canonical.getBytes(StandardCharsets.UTF_8));
            return HexFormat.of().formatHex(digest);
        } catch (NoSuchAlgorithmException ex) {
            throw new IllegalStateException("SHA-256 unavailable", ex);
        }
    }
}
~~~

Code mẫu chỉ đúng khi **OrderService cũng lưu SKU bằng cùng quy tắc chuẩn hóa**, và **mọi input ảnh hưởng đơn hàng** đều có mặt trong canonical string. Nếu bổ sung coupon, currency hoặc delivery option, cập nhật fingerprint và version. Với payload lồng nhau, dùng một canonical serialization được định nghĩa và kiểm thử; không tự nối raw JSON.

Hash giúp so sánh gọn, **không tự mã hóa nội dung**. Một hash của input có entropy thấp vẫn có thể bị thử đoán nếu bị lộ; hạn chế quyền đọc bảng, không log raw payload/hash tùy tiện và tuân chính sách dữ liệu.

## 8. Spring: tách HTTP, claim và transaction

### 8.1. Service (minh họa abstraction)

~~~java
public record StoredAttempt(
    String fingerprint,
    String state,
    int status,
    String location,
    String responseJson
) {}

public record CreateOrderResult(
    int status,
    String location,
    String responseJson
) {}

@Service
public class CreateOrderService {
    private final IdempotencyStore attempts;
    private final OrderRepository orders;
    private final OutboxRepository outbox;

    // Constructor injection được lược bỏ.

    @Transactional
    public CreateOrderResult create(
            String authorizedTenant, String key,
            CreateOrderRequest request) {

        String operation = "orders.create.v1";
        String hash = OrderFingerprint.calculate(request);

        boolean claimed = attempts.claimIfAbsent(
            authorizedTenant, operation, key, hash, 1);

        if (!claimed) {
            StoredAttempt old = attempts.loadCommitted(
                authorizedTenant, operation, key);

            if (!old.fingerprint().equals(hash)) {
                throw new IdempotencyKeyReusedException();
            }
            if (!"COMPLETED".equals(old.state())) {
                throw new IdempotencyInProgressException();
            }
            return new CreateOrderResult(
                old.status(), old.location(), old.responseJson());
        }

        Order order = orders.insertAuthorized(
            authorizedTenant, request);
        outbox.insertOrderCreated(order.id());

        String location = "/api/v1/orders/" + order.id();
        String responseJson = serializeCreateResponse(order);

        attempts.markCompleted(
            authorizedTenant, operation, key,
            201, location, responseJson);

        return new CreateOrderResult(
            201, location, responseJson);
    }
}
~~~

**IdempotencyStore**, **OrderRepository**, **OutboxRepository**, **Order** và **serializeCreateResponse** là thành phần ứng dụng tự định nghĩa; ví dụ tập trung vào thuật toán. IdempotencyStore phải triển khai claim nguyên tử theo phần 6; **cùng transaction thật** với dữ liệu order và outbox, không phải ba lời gọi sang ba database không có transaction chung.

Khi key đã có, cần kiểm tra **fingerprint_ver** trong bản ghi để dùng đúng thuật toán của version đó. Các tác động tới service bên ngoài cần outbox/workflow và chống lặp ở downstream, không gọi tùy tiện bên trong transaction rồi coi như có rollback.

### 8.2. Controller

~~~java
@RestController
@RequestMapping("/api/v1/orders")
public class OrderController {
    private final CreateOrderService service;
    private final TenantAccess tenantAccess;

    // Constructor injection được lược bỏ.

    @PostMapping
    public ResponseEntity<String> create(
            @RequestHeader(
                value = "Idempotency-Key", required = false) String key,
            @Valid @RequestBody CreateOrderRequest request,
            Authentication authentication) {

        if (key == null || !key.matches("[A-Za-z0-9_-]{8,120}")) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST,
                "Idempotency-Key thiếu hoặc sai định dạng");
        }

        String tenant =
            tenantAccess.authorizedTenantId(authentication);
        CreateOrderResult result = service.create(tenant, key, request);

        return ResponseEntity.status(result.status())
            .location(URI.create(result.location()))
            .contentType(MediaType.APPLICATION_JSON)
            .cacheControl(CacheControl.noStore())
            .body(result.responseJson());
    }
}
~~~

Ví dụ chọn một định dạng key có độ dài giới hạn; có thể dùng UUID. Trong dự án thực, cần import Spring MVC/Security/Validation, cấu hình JSON DTO, transaction, Problem Details và quy tắc phát hiện **header trùng**. Đừng tự động lấy tenant từ request chưa xác thực hoặc dùng key như token thay cho kiểm tra quyền.

### 8.3. Hai lỗi 409 khác nhau

~~~java
@RestControllerAdvice
public class IdempotencyErrorHandler {

    @ExceptionHandler(IdempotencyKeyReusedException.class)
    ResponseEntity<ProblemDetail> reused() {
        ProblemDetail p = ProblemDetail.forStatusAndDetail(
            HttpStatus.CONFLICT,
            "Khóa đã dùng cho yêu cầu có nội dung khác.");
        p.setType(URI.create(
            "https://api.example.com/problems/idempotency-key-reused"));
        p.setProperty("code", "IDEMPOTENCY_KEY_REUSED");
        return ResponseEntity.status(HttpStatus.CONFLICT).body(p);
    }

    @ExceptionHandler(IdempotencyInProgressException.class)
    ResponseEntity<ProblemDetail> inProgress() {
        ProblemDetail p = ProblemDetail.forStatusAndDetail(
            HttpStatus.CONFLICT,
            "Yêu cầu cùng khóa vẫn đang được xử lý.");
        p.setType(URI.create(
            "https://api.example.com/problems/idempotency-in-progress"));
        p.setProperty("code", "IDEMPOTENCY_IN_PROGRESS");
        return ResponseEntity.status(HttpStatus.CONFLICT)
            .header("Retry-After", "2")
            .body(p);
    }
}
~~~

Trong một ứng dụng Spring Boot, cần xác minh serializer/exception configuration trả **application/problem+json**, đồng thời bảo đảm error body không tiết lộ fingerprint, nội dung request đã lưu hoặc thông tin tenant khác. Hai mã **code** khác nhau giúp client biết **IN_PROGRESS có thể retry theo hợp đồng**, còn **KEY_REUSED phải sửa ý định/key**, không retry mù.

## 9. TTL, timeout và deployment mới

Nếu server giữ record **48 giờ**, retry cùng key trong thời gian đó có thể tra được kết quả. Sau khi record hết hạn và bị xóa, server **có thể không nhận ra lệnh cũ**; gửi lại POST có nguy cơ tạo đơn mới.

Vì vậy TTL phải dựa trên thời gian client offline, timeout của job, khả năng retry và mức độ nghiêm trọng của việc tạo trùng. Với thanh toán/hoàn tiền, có thể cần một **business reference duy nhất** tồn tại lâu hơn TTL của idempotency cache.

Các failure mode phải có giải pháp:

| Sự cố | Cách xử lý |
| --- | --- |
| Commit order thành công, response HTTP mất | Retry cùng scope/key tra kết quả đã commit |
| Transaction rollback trước commit | Không ghi order hoặc kết quả completed giả; retry an toàn |
| Client gửi key cũ sau TTL | Theo contract; cần business reference/reconciliation nếu không thể chấp nhận tạo trùng |
| Record IN_PROGRESS tồn tại quá lâu | Reconciler/lease/fencing; không xóa tùy tiện khi việc thực thi chưa rõ |
| Rolling deploy đổi thuật toán fingerprint | Dùng **fingerprint_ver** đã lưu cho key cũ |
| Kết quả đã lưu chứa dữ liệu người dùng nay mất quyền | Kiểm tra authz hiện tại trước replay |
| Client đổi key sau timeout | Có thể là ý định mới; phải hỏi trạng thái trước khi tạo |

**Một lỗi 5xx sau POST không chứng minh DB chưa commit.** Có thể lỗi xảy ra khi đóng kết nối hoặc serialize response. Client nên dùng cùng key khi retry trong chính sách cho phép, hoặc truy vấn business reference/operation status nếu kết quả chưa rõ.

## 10. Kiểm thử sát scope và fingerprint

### 10.1. MockMvc: một key nhưng đổi lượng hàng

~~~java
@Test
void sameKeyDifferentQuantityReturnsConflict() throws Exception {
    String key = "test-intent-0001";
    String first = """
        {"sku":"BOOK-42","quantity":2,"shippingAddressId":"addr-17"}
        """;
    String changed = """
        {"sku":"BOOK-42","quantity":3,"shippingAddressId":"addr-17"}
        """;

    MvcResult result = mockMvc.perform(post("/api/v1/orders")
            .header("Idempotency-Key", key)
            .contentType(MediaType.APPLICATION_JSON)
            .content(first))
        .andExpect(status().isCreated())
        .andExpect(header().exists("Location"))
        .andReturn();

    mockMvc.perform(post("/api/v1/orders")
            .header("Idempotency-Key", key)
            .contentType(MediaType.APPLICATION_JSON)
            .content(changed))
        .andExpect(status().isConflict())
        .andExpect(jsonPath("$.code")
            .value("IDEMPOTENCY_KEY_REUSED"));

    String uri = result.getResponse().getHeader("Location");

    mockMvc.perform(get(uri))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.quantity").value(2));
}
~~~

Test giả định có endpoint GET, dữ liệu test riêng và principal có quyền ở tenant tương ứng. Phải kiểm tra thêm **số row trong database** và **outbox event**; chỉ đọc lại đơn đầu chưa đủ chứng minh không có đơn phụ.

### 10.2. Ma trận kiểm thử

| Kịch bản | Bằng chứng |
| --- | --- |
| Key mới, request hợp lệ | 201 + Location + đúng một order/outbox |
| Cùng scope/key, JSON đảo thứ tự field | Replay cùng order, không tạo mới |
| Cùng scope/key, đổi quantity | 409 KEY_REUSED, không tạo mới |
| Cùng scope/key, đổi shippingAddressId | 409 KEY_REUSED |
| Cùng payload, **key mới** | Ý định mới; có thể tạo order thứ hai nếu nghiệp vụ cho phép |
| Cùng chuỗi key nhưng **tenant khác** | Không replay chéo tenant; authz và business uniqueness vẫn áp dụng |
| Cùng chuỗi key nhưng **operation khác** | Scope độc lập theo contract |
| Hai request đồng thời cùng key/payload | Một commit; response replay hoặc nhánh in-progress hợp lệ |
| Hai request đồng thời cùng key nhưng khác payload | Một request thắng; request kia bị từ chối mismatch |
| Commit thành công, response 201 bị mất | Retry nhận lại Location cũ, không tạo mới |
| Lỗi trước commit | Rollback nhất quán |
| TTL hết hoặc client offline lâu | Hành vi đúng chính sách, cơ chế đối soát hoạt động |
| Thay fingerprint version sau deploy | Key cũ vẫn được so theo version lưu |
| Thiếu hoặc có nhiều header Idempotency-Key | 400/validation theo contract |
| Quyền bị thu hồi trước lần retry | Không replay dữ liệu trái quyền |

### 10.3. Concurrency test cần database thật

Dùng PostgreSQL test container hoặc database tương đương, đưa **hai request cùng scope/key** vào hai thread gần như đồng thời bằng barrier; nếu có thể, gọi qua **hai instance API**. Kiểm tra:

~~~text
SELECT COUNT(*)
FROM idempotency_records
WHERE tenant_id = :tenant AND operation_id = :op
  AND idem_key = :key;

Kỳ vọng: 1

SELECT COUNT(*) FROM orders WHERE create_intent_ref = :intent;
Kỳ vọng: 1 (nếu bảng có business intent reference)

SELECT COUNT(*) FROM outbox WHERE event_key = :intent;
Kỳ vọng: 1
~~~

Nếu chưa có **create_intent_ref**, test phải đối chiếu những order ID được ánh xạ tới record idempotency và xác minh không có order thứ hai sinh từ cặp request. Đừng chỉ test **201 rồi replay 201** tuần tự: một implementation kiểu kiểm tra trước rồi insert có thể pass mọi test tuần tự nhưng tạo trùng dưới tải đồng thời.

## 11. OpenAPI và hướng dẫn client

Ví dụ OpenAPI 3.1 rút gọn:

~~~yaml
openapi: 3.1.0
info:
  title: Orders API
  version: 1.0.0
paths:
  /api/v1/orders:
    post:
      operationId: createOrder
      summary: Tạo đơn với Idempotency-Key
      description: >
        Key mới cho mỗi ý định, giữ nguyên khi retry.
        Scope: tenant đã xác thực + orders.create.v1 + key.
        Cùng key và cùng fingerprint đã hoàn tất: replay 201.
        Cùng key nhưng request nghiệp vụ khác: 409 KEY_REUSED.
        Retention minh họa: 48 giờ.
      parameters:
        - in: header
          name: Idempotency-Key
          required: true
          schema:
            type: string
            minLength: 8
            maxLength: 120
            pattern: '^[A-Za-z0-9_-]+$'
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              additionalProperties: false
              required: [sku, quantity, shippingAddressId]
              properties:
                sku: { type: string, minLength: 1 }
                quantity: { type: integer, minimum: 1 }
                shippingAddressId: { type: string, minLength: 1 }
      responses:
        '201':
          description: Tạo thành công hoặc replay kết quả tạo đã lưu
          headers:
            Location:
              schema: { type: string, format: uri-reference }
          content:
            application/json:
              schema:
                type: object
                required: [id, sku, quantity, status]
                properties:
                  id: { type: string }
                  sku: { type: string }
                  quantity: { type: integer }
                  status: { type: string }
        '400':
          description: Request hoặc key không hợp lệ
        '401':
          description: Chưa xác thực
        '403':
          description: Không có quyền
        '409':
          description: KEY_REUSED hoặc IN_PROGRESS; phân biệt bằng code
          content:
            application/problem+json:
              schema:
                type: object
                properties:
                  type: { type: string, format: uri-reference }
                  status: { type: integer, const: 409 }
                  detail: { type: string }
                  code:
                    type: string
                    enum: [IDEMPOTENCY_KEY_REUSED, IDEMPOTENCY_IN_PROGRESS]
~~~

Phải bổ sung security scheme, lỗi 429/5xx và schema thực tế khi triển khai. Nếu client retry khi gặp **IN_PROGRESS**, sử dụng **cùng key và payload**, backoff và hạn tổng; không tạo key mới chỉ để “thoát” xung đột. Nếu KEY_REUSED, dừng và xem có đang gửi **ý định mới** với key cũ hay không.

## 12. Bảo mật và theo dõi reuse sai

Key nên có entropy tốt, chẳng hạn UUID ngẫu nhiên; **không chứa password, email, số thẻ, token hoặc thông tin cá nhân**. Key không thay thế authz; server kiểm tra quyền trước khi tìm/replay kết quả.

Về vận hành, theo dõi số lượt replay, tỷ lệ **KEY_REUSED** và **IN_PROGRESS**, thời gian xử lý, record sắp hết TTL, lỗi concurrent claim. Đột biến **KEY_REUSED** có thể do SDK tạo key sai, frontend reuse key cho lần mua mới, rolling deploy đổi canonicalization hoặc hành vi lạm dụng.

Không đưa raw key/payload vào **metric label** gây high cardinality hoặc lộ dữ liệu; nếu cần log để tra cứu sự cố, áp giới hạn quyền, masking/HMAC và retention phù hợp. Trường **response_json** lưu trong database có thể chứa dữ liệu khách hàng, nên cần bảo vệ và xóa theo chính sách.

## 13. Bài thực hành: hoàn tiền có idempotency

Một API **POST /api/v1/refund-requests** nhận:

~~~json
{
  "paymentId": "pay-892",
  "amountMinor": 250000,
  "currency": "VND",
  "reasonCode": "DUPLICATE_PAYMENT"
}
~~~

Yêu cầu: hai service account cùng tenant có thể retry cùng ý định nếu được phân quyền; đổi amountMinor hoặc reasonCode dưới cùng key phải bị từ chối; thao tác hoàn tiền với đối tác không được nhân đôi.

Hãy thực hiện:

1. Định nghĩa scope: tenant/account, operation **refunds.create.v1**, key; giải thích vì sao paymentId phải có trong fingerprint hoặc scope.
2. Viết canonical DTO và fingerprint có version; xét currency, amountMinor và mọi trường ảnh hưởng hoàn tiền.
3. Lập ma trận xử lý key mới, cùng key/cùng fingerprint, cùng key/khác fingerprint, in-progress, khác tenant.
4. Viết HTTP transcript cho lần đầu thành công, retry hợp lệ và mismatch. Nếu hoàn tiền chưa hoàn tất, giải thích khi nào dùng **202 Accepted** cùng operation resource thay vì 201.
5. Thiết kế unique constraint, transaction, outbox, idempotency của payment gateway và reconciliation.
6. Viết controller/service Spring, Problem Details và ít nhất **8 test**: concurrent claim, đổi amount, đổi reason, khác tenant, response mất, key hết TTL, deploy fingerprint version mới, bị thu hồi quyền.
7. Lựa chọn thời hạn lưu dựa trên rủi ro tài chính; nêu cơ chế business reference ngăn trùng sau TTL.

**Sản phẩm:** hợp đồng HTTP, scope/fingerprint, sơ đồ trạng thái, mã Spring, schema SQL, ma trận test và ADR ngắn về độ bền, chi phí, bảo mật.

## 14. Tổng kết

Một endpoint có Idempotency-Key chỉ an toàn khi có đủ ba yếu tố:

- **Scope đúng:** ràng buộc key với chủ thể nghiệp vụ và operation đã được xác thực.
- **Fingerprint đúng:** cùng key chỉ được replay khi request mang cùng ý nghĩa; khác request phải được phát hiện và chặn.
- **Commit nguyên tử:** đúng một business effect và một kết quả có thể tra cứu sau retry, kể cả khi phản hồi đầu đã mất.

**Đừng đồng nhất “cùng chuỗi key” với “cùng ý định”.** Định nghĩa scope, so fingerprint và kiểm thử concurrency giúp API phân biệt retry hợp lệ với tái sử dụng sai, từ đó tránh tạo trùng, bỏ sót thao tác và rò dữ liệu.
