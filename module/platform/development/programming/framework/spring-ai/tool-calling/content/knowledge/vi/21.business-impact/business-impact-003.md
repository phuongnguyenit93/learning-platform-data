# Thiết kế khóa lũy đẳng để ngăn xử lý trùng

Một tool có thể tạo thanh toán, hoàn tiền, đặt chỗ, gửi thông báo hoặc thay đổi trạng thái nghiệp vụ. Nếu model gọi lại tool sau timeout, nếu người dùng gửi lại request hoặc nếu hai request đến đồng thời, cùng một ý định có thể bị thực thi nhiều lần. Với thao tác ghi, hậu quả có thể là tạo hai đơn hàng, trừ tiền hai lần hoặc gửi cùng một thông báo nhiều lần.

Idempotency key (khóa lũy đẳng) giúp ứng dụng nhận diện những lần gửi lại thuộc cùng một thao tác nghiệp vụ. Backend lưu key cùng dấu vân tay của request và kết quả xử lý. Khi nhận lại cùng key và cùng nội dung, hệ thống trả kết quả đã có hoặc báo thao tác vẫn đang chạy thay vì thực hiện lại. Khi key bị dùng với nội dung khác, hệ thống từ chối.

Trong Spring AI, việc model yêu cầu gọi tool không tự bảo đảm thao tác chỉ chạy một lần. Callback và service nghiệp vụ phải áp dụng idempotency tại nơi phát sinh side effect. Đây là lớp bảo vệ cần thiết khi tool có thể bị gọi lại do retry, timeout, nhiều vòng hội thoại hoặc nhiều request đồng thời.

## Sau bài học, bạn có thể

- Phân biệt tính lũy đẳng của thao tác với việc chống xử lý trùng bằng idempotency key.
- Chọn phạm vi và nguồn tạo key cho từng ý định nghiệp vụ.
- Tính request fingerprint để phát hiện key bị dùng với payload khác.
- Dùng unique constraint và thao tác insert nguyên tử để giành quyền xử lý.
- Thiết kế trạng thái `IN_PROGRESS`, `SUCCEEDED`, `FAILED` và kết quả replay.
- Xử lý request trùng đồng thời, request retry sau khi hoàn tất và key bị tái sử dụng sai.
- Kết hợp idempotency với transaction, outbox và idempotency của dịch vụ bên ngoài.
- Truyền operation ID đáng tin cậy đến tool qua `ToolContext`.
- Xác định thời hạn lưu key, bảo mật và các trường hợp cần đối soát.
- Kiểm thử race condition và bảo đảm side effect không bị lặp.

## Tình huống gây xử lý trùng

Giả sử người dùng yêu cầu hoàn tiền cho thanh toán `PAY-2048). Model gọi tool `createRefund`, ứng dụng gửi lệnh đến dịch vụ thanh toán. Dịch vụ đã tạo refund thành công nhưng response bị timeout trên đường về. Model hoặc ứng dụng không nhận được kết quả nên thử lại.

Nếu callback gọi lại dịch vụ với một request mới, hệ thống có thể tạo refund thứ hai. Một tình huống khác là người dùng nhấn nút hai lần, gateway retry POST hoặc hai worker cùng nhận một message.

| Tình huống | Vì sao có thể xử lý trùng |
|---|---|
| HTTP client retry sau timeout | Không biết server đã commit hay chưa |
| Model yêu cầu gọi tool lại | Tool call mới có thể có call ID khác dù cùng ý định |
| Người dùng gửi hai request | Hai request cùng mô tả một hành động |
| Hai worker nhận message trùng | Broker thường có thể giao lại message |
| Callback timeout nhưng service vẫn chạy | Caller thử lại trong khi lần đầu chưa kết thúc |
| Worker khởi động lại | Công việc đã commit side effect nhưng chưa ghi nhận trạng thái hoàn tất |

Không thể dựa vào việc “model thường chỉ gọi tool một lần”. Backend cần bảo vệ thao tác ở nơi thực thi nghiệp vụ, vì retry có thể xuất hiện ở nhiều tầng.

## Idempotent operation và idempotency key

Một thao tác là lũy đẳng khi thực hiện nhiều lần với cùng ý định không làm thay đổi kết quả nghiệp vụ vượt quá lần đầu.

Ví dụ:

- `PUT /profile/42` đặt hồ sơ về cùng một trạng thái có thể có tính lũy đẳng theo HTTP semantics.
- `POST /payments` tạo giao dịch mới thường không lũy đẳng nếu mỗi lần gọi đều sinh giao dịch mới.
- `POST /refunds` có thể được làm lũy đẳng bằng key gắn với một yêu cầu hoàn tiền cụ thể.
- `sendEmail` không tự lũy đẳng vì mỗi lần gọi có thể gửi thêm một email.

Idempotency key là định danh opaque của một ý định thao tác. Client hoặc application layer tạo key và gửi cùng key trong mọi lần retry của cùng thao tác. Server dùng key đó để tra cứu trạng thái và kết quả đã lưu.

Một key không phải là authorization token. Biết key không đồng nghĩa có quyền xem kết quả hoặc thực hiện hành động. Mỗi request, kể cả request trùng, vẫn phải xác thực người gọi và kiểm tra quyền truy cập tài nguyên trước khi trả lại dữ liệu.

## Chọn phạm vi và tạo key

Khóa cần duy nhất trong phạm vi mà hệ thống định nghĩa. Chỉ lưu một chuỗi key toàn cục mà không có tenant hoặc loại thao tác có thể gây va chạm hoặc làm lộ kết quả giữa các người dùng.

Một khóa tra cứu thường gồm:

- `tenantId` hoặc chủ thể sở hữu thao tác.
- `operationName` hoặc loại nghiệp vụ, ví dụ `refund.create.v1`.
- `idempotencyKey` do client hoặc backend tạo.

Ví dụ unique scope:

~~~text
(tenant_id, operation_name, idempotency_key)
~~~

Nếu key được tạo ngẫu nhiên, dùng UUID có entropy đủ cao hoặc một giá trị ngẫu nhiên an toàn tương đương. Nếu API nhận header `Idempotency-Key`, hãy xác định định dạng, giới hạn độ dài và chính sách hết hạn trong hợp đồng API.

### Key phải đại diện cho một ý định nghiệp vụ

Key cần được tạo một lần cho một hành động cụ thể và được giữ nguyên qua mọi lần gửi lại của hành động đó.

Ví dụ:

~~~http
POST /api/refunds
Idempotency-Key: "b2a8a8d7-4a8c-4a2d-9f2c-6d77b0e8f9d1"
Content-Type: application/json

{
  "paymentId": "PAY-2048",
  "amount": 250000,
  "reason": "duplicate-charge"
}
~~~

Nếu response bị timeout, client gửi lại đúng key và cùng payload. Nếu người dùng chủ động tạo một yêu cầu hoàn tiền mới, ứng dụng tạo key mới sau khi xác nhận đó là ý định mới.

Không dùng một key cố định cho mọi thao tác của người dùng. Không dùng riêng `conversationId` làm key vì một cuộc hội thoại có thể có nhiều thao tác hợp lệ cùng loại. Không dùng `toolCallId` của model làm key vì lần model gọi lại có thể có ID mới. Không tạo UUID mới bên trong mỗi lần callback chạy, vì như vậy retry sẽ luôn trông như một thao tác mới.

### Tạo operation ID trong luồng Spring AI

Với tool có side effect, backend nên tạo hoặc tiếp nhận operation ID ở application layer trước khi gọi model, sau khi đã xác định ý định và quyền của người dùng. Truyền ID qua `ToolContext` để callback dùng lại:

~~~java
UUID operationId = operationRegistry.createFor(
        authenticatedUser.tenantId(),
        "refund.create.v1"
);

String answer = chatClient.prompt()
        .user(question)
        .tools(refundTools)
        .toolContext(Map.of(
                "tenantId", authenticatedUser.tenantId(),
                "userId", authenticatedUser.userId(),
                "operationId", operationId.toString()
        ))
        .call()
        .content();
~~~

Tool lấy operation ID từ context do ứng dụng tạo:

~~~java
@Tool(description = "Tạo hoàn tiền cho một thanh toán")
public RefundResult createRefund(
        RefundRequest request,
        ToolContext toolContext) {

    Map<String, Object> context = toolContext.getContext();

    UUID tenantId = UUID.fromString((String) context.get("tenantId"));
    UUID operationId = UUID.fromString((String) context.get("operationId"));

    return refundService.createRefund(
            tenantId,
            operationId.toString(),
            request
    );
}
~~~

Ví dụ này giả định một request đang xử lý một ý định hoàn tiền. Nếu một response có nhiều thao tác ghi độc lập, mỗi thao tác cần operation ID riêng. Đừng dùng chung một ID cho hai refund khác nhau. Nếu model có thể tự quyết định nhiều hành động, orchestration layer cần ánh xạ từng hành động đã được phê duyệt sang một operation ID ổn định trước khi callback tạo side effect.

Không để model tự chọn tenant ID, user ID hoặc idempotency key tùy ý. Các giá trị đó phải được xác thực, kiểm tra phạm vi và tạo bởi backend hoặc client đáng tin cậy theo hợp đồng API.

## Request fingerprint để phát hiện key dùng sai

Chỉ kiểm tra key đã tồn tại chưa là chưa đủ. Nếu cùng key được gửi lại với payload khác, server không thể biết caller đang retry hay vô tình tái sử dụng key cho một ý định khác.

Request fingerprint là hash của phần dữ liệu có ý nghĩa nghiệp vụ. Khi key đã tồn tại:

- Fingerprint giống nhau: đây là retry của cùng thao tác; trả kết quả cũ hoặc trạng thái đang xử lý.
- Fingerprint khác nhau: key bị dùng cho payload khác; từ chối request.

Fingerprint nên bao gồm các trường ảnh hưởng đến side effect, ví dụ:

- Operation name và version.
- Payment ID hoặc resource ID.
- Số tiền và loại tiền.
- Lý do hoặc loại hành động.
- Các lựa chọn nghiệp vụ làm thay đổi kết quả.

Không đưa các giá trị thay đổi giữa các lần retry vào fingerprint, ví dụ trace ID, request timestamp, thứ tự thuộc tính JSON không có ý nghĩa, hoặc header theo dõi. Nếu không, hai lần gửi lại cùng ý định có thể tạo hash khác nhau.

### Chuẩn hóa trước khi hash

Không hash trực tiếp JSON thô nếu thứ tự field, format số hoặc cách biểu diễn ngày có thể thay đổi. Hãy chuẩn hóa dữ liệu nghiệp vụ rồi serialize theo một cấu trúc ổn định.

~~~java
public record RefundFingerprintV1(
        String paymentId,
        BigDecimal amount,
        String currency,
        String reason
) {
}

@Component
public class RequestFingerprint {

    private final ObjectMapper objectMapper;

    public RequestFingerprint(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    public String forRefund(RefundRequest request) {
        RefundFingerprintV1 canonical = new RefundFingerprintV1(
                request.paymentId().trim(),
                request.amount().stripTrailingZeros(),
                request.currency().toUpperCase(Locale.ROOT),
                request.reason().trim()
        );

        try {
            byte[] payload = objectMapper.writeValueAsBytes(canonical);
            byte[] digest = MessageDigest.getInstance("SHA-256")
                    .digest(payload);

            return HexFormat.of().formatHex(digest);
        }
        catch (JsonProcessingException | NoSuchAlgorithmException ex) {
            throw new FingerprintCreationException(ex);
        }
    }
}
~~~

Trong dự án thực tế, cấu trúc `RefundFingerprintV1` là một phần của hợp đồng idempotency. Khi thay đổi quy tắc chuẩn hóa hoặc trường ảnh hưởng đến nghiệp vụ, hãy version fingerprint để các key cũ vẫn được so sánh theo đúng quy tắc lúc tạo.

Với payload chứa dữ liệu nhạy cảm hoặc có entropy thấp, cân nhắc dùng HMAC-SHA-256 với secret được quản lý an toàn thay cho hash không khóa. Không lưu payload thô chỉ để so sánh nếu hash đã đáp ứng yêu cầu kiểm chứng.

## Lưu trạng thái idempotency

Backend cần lưu key đủ lâu để nhận diện retry, cùng fingerprint, trạng thái và kết quả có thể trả lại.

Ví dụ schema PostgreSQL:

~~~sql
CREATE TABLE idempotency_record (
    tenant_id          UUID         NOT NULL,
    operation_name     VARCHAR(120) NOT NULL,
    idempotency_key    VARCHAR(200) NOT NULL,
    request_hash       CHAR(64)     NOT NULL,
    status             VARCHAR(24)  NOT NULL,
    response_status    INTEGER,
    response_body      JSONB,
    resource_id        VARCHAR(120),
    created_at         TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ  NOT NULL DEFAULT now(),
    completed_at       TIMESTAMPTZ,
    expires_at         TIMESTAMPTZ  NOT NULL,
    PRIMARY KEY (tenant_id, operation_name, idempotency_key),
    CHECK (status IN (
        'IN_PROGRESS',
        'SUCCEEDED',
        'FAILED_FINAL',
        'UNKNOWN'
    ))
);

CREATE INDEX idempotency_record_expiry_idx
    ON idempotency_record (expires_at);
~~~

Các cột quan trọng:

| Cột | Mục đích |
|---|---|
| `tenant_id` | Phân vùng dữ liệu theo tenant |
| `operation_name` | Tách phạm vi giữa các loại thao tác |
| `idempotency_key` | Định danh một ý định |
| `request_hash` | Phát hiện cùng key nhưng payload khác |
| `status` | Trạng thái thực thi |
| `response_body` | Kết quả đã hoàn tất để replay |
| `resource_id` | ID nghiệp vụ được tạo hoặc thay đổi |
| `created_at`, `completed_at` | Thời điểm bắt đầu và hoàn tất |
| `expires_at` | Mốc có thể dọn record theo retention policy |

Không nhất thiết lưu toàn bộ response nếu response chứa dữ liệu nhạy cảm hoặc lớn. Có thể lưu resource ID và tái tạo response từ dữ liệu nghiệp vụ, miễn kết quả trả cho retry vẫn nhất quán với hợp đồng API.

## Dùng unique constraint để giành quyền xử lý nguyên tử

Kiểm tra kiểu `SELECT rồi INSERT` không an toàn khi có hai request đồng thời:

~~~text
Request A: SELECT -> không thấy key
Request B: SELECT -> không thấy key
Request A: INSERT
Request B: INSERT
Request A: thực thi nghiệp vụ
Request B: thực thi nghiệp vụ
~~~

Cả hai request đều có thể vượt qua bước kiểm tra và cùng thực hiện side effect. Một khóa lũy đẳng cần thao tác giành quyền xử lý nguyên tử.

Unique constraint ở database là điểm phân xử giữa các request. Với PostgreSQL, có thể dùng:

~~~sql
INSERT INTO idempotency_record (
    tenant_id,
    operation_name,
    idempotency_key,
    request_hash,
    status,
    expires_at
)
VALUES (
    :tenantId,
    :operationName,
    :key,
    :requestHash,
    'IN_PROGRESS',
    :expiresAt
)
ON CONFLICT (tenant_id, operation_name, idempotency_key)
DO NOTHING;
~~~

Nếu số row được insert là 1, request hiện tại giành được quyền xử lý. Nếu số row là 0, key đã tồn tại; ứng dụng đọc record hiện có, so sánh fingerprint và quyết định replay hoặc trả trạng thái đang xử lý.

Unique index của PostgreSQL phối hợp với transaction đang ghi key để xử lý xung đột đồng thời. Request thứ hai phải chờ transaction đang giữ key kết thúc rồi mới xác định insert có được phép hay không. Điều này tránh race condition mà một bước SELECT riêng lẻ không giải quyết được.

## Luồng xử lý chuẩn

~~~mermaid
flowchart TD
    A[Nhận yêu cầu ghi] --> B[Xác thực user và tenant]
    B --> C[Đọc operation ID / Idempotency-Key]
    C --> D[Chuẩn hóa payload và tính fingerprint]
    D --> E[INSERT key với unique constraint]
    E --> F{Insert thành công?}
    F -->|Có| G[Thực thi nghiệp vụ]
    G --> H[Lưu kết quả và SUCCEEDED]
    H --> I[Commit transaction]
    I --> J[Trả kết quả]
    F -->|Không| K[Đọc record hiện có]
    K --> L{Fingerprint giống?}
    L -->|Không| M[Trả lỗi key bị tái sử dụng]
    L -->|Có| N{Trạng thái}
    N -->|SUCCEEDED| O[Replay kết quả cũ]
    N -->|IN_PROGRESS| P[Trả trạng thái đang xử lý]
    N -->|FAILED_FINAL| Q[Replay lỗi cuối]
    N -->|UNKNOWN| R[Đối soát trước khi chạy lại]
~~~

Thứ tự quan trọng:

1. Xác thực người dùng và quyền truy cập.
2. Xác định operation scope và key.
3. Tính fingerprint từ payload đã chuẩn hóa.
4. Thử insert key bằng unique constraint.
5. Nếu request sở hữu key, thực thi side effect trong ranh giới an toàn.
6. Lưu kết quả và trạng thái cuối.
7. Nếu key đã tồn tại, kiểm tra fingerprint rồi replay hoặc trả trạng thái tương ứng.

Không trả kết quả cũ trước khi xác thực caller hiện tại. Nếu quyền truy cập đã bị thu hồi sau lần đầu, ứng dụng vẫn phải từ chối việc xem lại response nhạy cảm.

## Ví dụ transaction cho thao tác chỉ ghi trong cùng database

Nếu thay đổi nghiệp vụ và idempotency record nằm trong cùng một database, có thể ghi chúng trong một transaction ngắn. Khi transaction commit, cả side effect và kết quả idempotency cùng tồn tại. Nếu transaction rollback, cả hai cùng rollback.

Repository có thể dùng `JdbcTemplate`:

~~~java
@Repository
public class IdempotencyRepository {

    private final JdbcTemplate jdbcTemplate;

    public IdempotencyRepository(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public boolean tryStart(
            UUID tenantId,
            String operationName,
            String key,
            String requestHash,
            Instant expiresAt) {

        int inserted = jdbcTemplate.update("""
                INSERT INTO idempotency_record (
                    tenant_id, operation_name, idempotency_key,
                    request_hash, status, expires_at
                )
                VALUES (?, ?, ?, ?, 'IN_PROGRESS', ?)
                ON CONFLICT (
                    tenant_id, operation_name, idempotency_key
                ) DO NOTHING
                """,
                tenantId,
                operationName,
                key,
                requestHash,
                Timestamp.from(expiresAt)
        );

        return inserted == 1;
    }
}
~~~

Service điều phối:

~~~java
@Service
public class RefundApplicationService {

    private static final String OPERATION = "refund.create.v1";

    private final IdempotencyRepository idempotencyRepository;
    private final RefundRepository refundRepository;
    private final RequestFingerprint fingerprint;
    private final ObjectMapper objectMapper;
    private final Clock clock;

    public RefundApplicationService(
            IdempotencyRepository idempotencyRepository,
            RefundRepository refundRepository,
            RequestFingerprint fingerprint,
            ObjectMapper objectMapper,
            Clock clock) {
        this.idempotencyRepository = idempotencyRepository;
        this.refundRepository = refundRepository;
        this.fingerprint = fingerprint;
        this.objectMapper = objectMapper;
        this.clock = clock;
    }

    @Transactional
    public RefundResult createRefund(
            UUID tenantId,
            String idempotencyKey,
            RefundRequest request) {

        String requestHash = fingerprint.forRefund(request);

        boolean owner = idempotencyRepository.tryStart(
                tenantId,
                OPERATION,
                idempotencyKey,
                requestHash,
                clock.instant().plus(Duration.ofDays(2))
        );

        if (!owner) {
            return replayExisting(
                    tenantId,
                    OPERATION,
                    idempotencyKey,
                    requestHash
            );
        }

        // Chỉ thực hiện thay đổi trong cùng database transaction.
        RefundResult result = refundRepository.createRefund(request, tenantId);

        idempotencyRepository.markSucceeded(
                tenantId,
                OPERATION,
                idempotencyKey,
                result.refundId(),
                serialize(result)
        );

        return result;
    }

    private RefundResult replayExisting(
            UUID tenantId,
            String operation,
            String key,
            String requestHash) {

        IdempotencyRecord existing = idempotencyRepository
                .findRequired(tenantId, operation, key);

        if (!existing.requestHash().equals(requestHash)) {
            throw new IdempotencyKeyReuseException();
        }

        return switch (existing.status()) {
            case "SUCCEEDED" -> deserialize(existing.responseBody());
            case "IN_PROGRESS" -> throw new OperationInProgressException();
            case "FAILED_FINAL" -> throw replayStoredFailure(existing);
            case "UNKNOWN" -> throw new ReconciliationRequiredException();
            default -> throw new IllegalStateException(
                    "Unknown idempotency status: " + existing.status()
            );
        };
    }

    private String serialize(RefundResult result) {
        try {
            return objectMapper.writeValueAsString(result);
        }
        catch (JsonProcessingException ex) {
            throw new IllegalStateException("Cannot serialize refund result", ex);
        }
    }

    private RefundResult deserialize(String body) {
        try {
            return objectMapper.readValue(body, RefundResult.class);
        }
        catch (JsonProcessingException ex) {
            throw new IllegalStateException("Cannot read stored refund result", ex);
        }
    }
}
~~~

Đây là khung minh họa. Repository cần triển khai `findRequired`, `markSucceeded` và mapping trạng thái theo schema. Cần bảo đảm `RefundRepository.createRefund` chỉ thay đổi dữ liệu trong cùng database transaction. Nếu gọi nhà cung cấp thanh toán qua HTTP, transaction database không thể rollback side effect đã commit ở hệ thống bên ngoài.

Trong mô hình transaction ngắn này, request thứ hai có thể phải chờ unique insert của request đầu kết thúc. Nếu request đầu commit, request thứ hai đọc trạng thái `SUCCEEDED` và replay kết quả. Nếu request đầu rollback, request thứ hai có thể giành quyền insert và thực thi. Không giữ transaction mở trong lúc chờ một dịch vụ bên ngoài phản hồi lâu.

Vì row `IN_PROGRESS` trong ví dụ chưa commit cho đến khi toàn bộ transaction hoàn tất, request thứ hai thường chờ ở unique insert rồi mới đọc được trạng thái cuối. Nếu nghiệp vụ kéo dài và cần công bố trạng thái đang chạy, hãy tách bước reserve thành transaction ngắn: insert `IN_PROGRESS` kèm `owner_id` và `lease_until`, commit, rồi worker xử lý ở transaction khác. Request trùng đọc được `IN_PROGRESS` và trả 409 hoặc 202 kèm URL theo dõi. Khi lease hết hạn, không tự động chạy lại nếu chưa xác định side effect cũ đã xảy ra hay chưa; trước tiên phải kiểm tra trạng thái downstream hoặc chuyển sang `UNKNOWN` để đối soát.

## Xử lý trạng thái và request trùng

Các trạng thái nên có ý nghĩa rõ ràng:

| Trạng thái | Ý nghĩa | Hành vi khi nhận lại cùng key và hash |
|---|---|---|
| `IN_PROGRESS` | Đã giành quyền xử lý, chưa có kết quả cuối | Trả 409/202 hoặc thông tin theo dõi |
| `SUCCEEDED` | Side effect và kết quả đã được ghi nhận | Replay kết quả đã lưu |
| `FAILED_FINAL` | Lỗi cuối, không được tự chạy lại | Replay lỗi cuối theo hợp đồng |
| `UNKNOWN` | Không xác định side effect đã xảy ra chưa | Đối soát trước khi quyết định |

Không dùng một trạng thái `FAILED` chung cho mọi lỗi. Một lỗi validation trước khi có side effect khác với timeout sau khi gửi lệnh đến nhà cung cấp. Với lỗi tạm thời chắc chắn chưa tạo side effect, hệ thống có thể cho phép chuyển về trạng thái retryable theo chính sách. Với kết quả không xác định, phải giữ trạng thái để đối soát thay vì chạy lại mù.

### Ba tình huống duplicate phổ biến

| Tình huống | Điều kiện | Hành vi khuyến nghị |
|---|---|---|
| Retry sau khi đã hoàn tất | Cùng key, cùng hash, trạng thái SUCCEEDED | Trả lại response đã lưu |
| Request trùng khi thao tác đang chạy | Cùng key, cùng hash, trạng thái IN_PROGRESS | Trả 409 Conflict hoặc 202 kèm URL trạng thái theo hợp đồng API |
| Dùng lại key với payload khác | Cùng key, hash khác | Trả 422 và không thực thi |

Một Internet-Draft của IETF về `Idempotency-Key` hiện mô tả cách xử lý tương tự: request trùng đã hoàn tất nhận kết quả nhất quán, request đồng thời nhận conflict, còn key bị dùng với payload khác nhận 422. Đây là Internet-Draft đang phát triển, không phải RFC đã được công bố; hãy xem hợp đồng API của chính ứng dụng là nguồn quy định cuối cùng.

## Tách transaction ngắn và công việc bên ngoài

Một transaction database không thể bảo đảm atomicity với HTTP API, hệ thống thanh toán hoặc broker nếu không có giao thức phân tán tương ứng. Ví dụ:

1. Database ghi idempotency record.
2. Ứng dụng gọi payment provider.
3. Provider tạo refund thành công.
4. Ứng dụng bị crash trước khi cập nhật record thành SUCCEEDED.

Khi request retry, record có thể vẫn ở `IN_PROGRESS` hoặc `UNKNOWN`. Nếu ứng dụng gọi provider lần nữa với một key mới, refund có thể bị tạo trùng.

Có hai cơ chế cần phối hợp:

- Gửi cùng operation key làm idempotency key cho provider nếu provider hỗ trợ.
- Lưu ý định phát lệnh và dữ liệu nghiệp vụ trong một transaction, sau đó dùng outbox worker gửi lệnh ra ngoài.

### Transactional outbox

Trong transaction database:

- Tạo bản ghi nghiệp vụ hoặc operation.
- Lưu idempotency record.
- Thêm outbox event có event ID ổn định.
- Commit tất cả cùng nhau.

Worker đọc outbox và gửi lệnh đến provider. Nếu worker gửi thành công nhưng crash trước khi đánh dấu event đã xử lý, worker có thể gửi lại. Khi đó provider cần nhận cùng idempotency key hoặc consumer phải có bảng dedupe riêng.

~~~mermaid
flowchart TD
    A[Nhận command + key] --> B[Transaction DB]
    B --> C[Insert idempotency record]
    B --> D[Update nghiệp vụ]
    B --> E[Insert outbox event]
    C --> F[Commit]
    D --> F
    E --> F
    F --> G[Outbox worker]
    G --> H[Gọi provider với cùng operation key]
    H --> I[Provider dedupe]
    I --> J[Worker lưu kết quả]
~~~

Outbox bảo đảm ý định gửi message được lưu cùng transaction nghiệp vụ. Nó không tự bảo đảm provider chỉ thực hiện một lần. Consumer và provider vẫn cần idempotency hoặc cơ chế đối soát để xử lý giao nhận lặp.

## Dùng cùng key khi gọi hệ thống bên ngoài

Nếu downstream hỗ trợ idempotency key, truyền operation ID ổn định của ứng dụng:

~~~java
PaymentProviderResult result = paymentClient.createRefund(
        command,
        operationId.toString()
);
~~~

Mỗi lần worker retry cùng một refund phải gửi cùng key. Không tạo UUID mới mỗi attempt. Nếu provider có thời gian lưu key riêng, retention của ứng dụng phải được thiết kế phù hợp với cửa sổ retry và đối soát của provider.

Nếu downstream không hỗ trợ idempotency, timeout sau khi gửi request tạo ra trạng thái không xác định. Ứng dụng cần:

- Tra cứu giao dịch bằng merchant reference hoặc operation ID.
- Đối soát trước khi gửi lại.
- Lưu `UNKNOWN` hoặc `RECONCILIATION_REQUIRED`.
- Chuyển trường hợp không thể xác minh sang xử lý thủ công.
- Không khẳng định timeout đồng nghĩa provider chưa thực hiện thao tác.

Không có một transaction local nào có thể tự rollback side effect đã được hệ thống bên ngoài commit.

## Kết hợp idempotency với Spring AI tool execution

Tool callback là điểm vào của nghiệp vụ, nhưng idempotency nên nằm ở application service hoặc domain service để mọi đường gọi đều được bảo vệ. Không chỉ kiểm tra key trong method `@Tool` rồi để REST endpoint hoặc message consumer gọi service mà không có cùng cơ chế.

Ví dụ:

~~~java
@Component
public class RefundTools {

    private final RefundApplicationService refundService;

    public RefundTools(RefundApplicationService refundService) {
        this.refundService = refundService;
    }

    @Tool(description = "Tạo yêu cầu hoàn tiền cho thanh toán")
    public RefundResult createRefund(
            @ToolParam(description = "Mã thanh toán") String paymentId,
            @ToolParam(description = "Số tiền hoàn") BigDecimal amount,
            ToolContext toolContext) {

        Map<String, Object> context = toolContext.getContext();

        UUID tenantId = (UUID) context.get("tenantId");
        String operationId = (String) context.get("operationId");
        String userId = (String) context.get("userId");

        return refundService.createRefund(
                tenantId,
                userId,
                operationId,
                new RefundRequest(paymentId, amount)
        );
    }
}
~~~

Service kiểm tra quyền trước khi replay hoặc tạo mới:

~~~java
@Transactional
public RefundResult createRefund(
        UUID tenantId,
        String userId,
        String operationId,
        RefundRequest request) {

    authorizationService.requireCanRefund(
            userId,
            tenantId,
            request.paymentId()
    );

    return idempotentRefundProcessor.execute(
            tenantId,
            "refund.create.v1",
            operationId,
            request
    );
}
~~~

Ví dụ này cho thấy callback chỉ chuyển dữ liệu và context đến service. `idempotentRefundProcessor` chịu trách nhiệm fingerprint, unique claim, transaction và replay. Việc kiểm tra quyền được thực hiện cả khi key đã tồn tại, để người dùng không thể dùng key cũ để đọc lại response của người khác.

Nếu model gọi lại tool với cùng operation ID, service nhận ra cùng ý định. Nếu người dùng bắt đầu một yêu cầu hoàn tiền mới, application layer phải cấp operation ID mới. Không dùng conversation ID hoặc tool call ID thay cho operation ID nghiệp vụ.

## TTL và vòng đời của key

Idempotency record không nhất thiết phải lưu vĩnh viễn, nhưng xóa quá sớm có thể cho phép request retry cũ tạo side effect lần nữa.

Retention nên bao phủ:

- Thời gian client có thể retry.
- Thời gian gateway, queue và worker có thể giao lại.
- Retry window của provider bên ngoài.
- Thời gian cần để đối soát và xử lý khiếu nại.
- Yêu cầu lưu trữ của nghiệp vụ hoặc kiểm toán.

Ví dụ một API hoàn tiền có thể giữ key ít nhất trong toàn bộ cửa sổ retry và đối soát đã công bố. Một thao tác thanh toán có rủi ro cao có thể cần giữ operation ledger lâu hơn thời gian cache response.

Quy tắc dọn dẹp:

- Không xóa record `IN_PROGRESS` khi worker còn có thể đang chạy.
- Không xóa record `UNKNOWN` trước khi đối soát.
- Chỉ dọn record terminal đã qua thời hạn retention.
- Có thể giữ tombstone gồm scope, key hash, fingerprint và resource ID sau khi xóa response chi tiết.
- Công bố rõ key hết hạn có thể được xem là thao tác mới hay bị từ chối.

Nếu key hết hạn và record bị xóa, server có thể không còn nhận ra retry cũ. TTL là một phần của hợp đồng idempotency, không chỉ là công việc dọn cache.

## Bảo mật và quyền truy cập

Idempotency store có thể chứa kết quả thanh toán, refund hoặc thông tin cá nhân. Cần kiểm soát:

- Key có định dạng và giới hạn độ dài cố định.
- Dùng UUID hoặc giá trị ngẫu nhiên đủ entropy; không dùng số tăng tuần tự dễ đoán.
- Scope unique bao gồm tenant hoặc principal phù hợp.
- Không cho phép đoán key để lấy response của người khác.
- Xác thực và authorization trước khi replay.
- Không ghi raw key, access token hoặc payload nhạy cảm vào log nếu không cần.
- Lưu fingerprint hoặc HMAC thay vì bản sao payload đầy đủ khi phù hợp.
- Phân quyền truy cập bảng idempotency và đặt retention theo chính sách dữ liệu.

Key chỉ là khóa nhận diện thao tác, không thay thế xác thực. Nếu dùng header `Idempotency-Key`, hãy kiểm tra format trước khi đưa vào SQL và luôn bind parameter, không nối chuỗi vào câu lệnh.

## Kiểm thử idempotency

Unit test cho một lần retry thành công chưa đủ. Cần kiểm tra nhiều request đồng thời và các tình huống không chắc chắn.

| Trường hợp | Kết quả mong đợi |
|---|---|
| Lần đầu với key mới | Thực hiện nghiệp vụ một lần và lưu kết quả |
| Gửi lại cùng key, cùng payload sau khi hoàn tất | Replay kết quả, không gọi service nghiệp vụ lần hai |
| Cùng key nhưng payload khác | Từ chối, không thực hiện side effect |
| Hai request đồng thời cùng key | Chỉ một request giành quyền thực thi |
| Request thứ hai đến khi thao tác còn chạy | Nhận trạng thái in-progress/conflict theo hợp đồng |
| Transaction đầu rollback | Request sau có thể giành key và xử lý |
| Timeout sau side effect bên ngoài | Chuyển sang đối soát hoặc dùng cùng downstream key |
| Key đã hết hạn | Hành vi đúng theo retention policy |
| User khác hoặc tenant khác dùng key cũ | Không thể đọc response trái quyền |
| Worker nhận outbox event lặp | Side effect downstream vẫn được dedupe |

Ví dụ kiểm thử cùng key không tạo refund lần hai:

~~~java
@Test
void retryWithSameKeyShouldReplayStoredResult() {
    String key = "op-8f13";
    RefundRequest request = new RefundRequest(
            "PAY-2048",
            new BigDecimal("250000")
    );

    RefundResult first = service.createRefund(
            tenantId,
            key,
            request
    );

    RefundResult second = service.createRefund(
            tenantId,
            key,
            request
    );

    assertThat(second).isEqualTo(first);
    verify(refundRepository, times(1))
            .createRefund(request, tenantId);
}
~~~

Test này giả định repository idempotency và refund repository dùng cùng transaction manager/database. Test tích hợp nên dùng database thật hoặc Testcontainers để xác minh unique constraint và transaction behavior, không chỉ mock repository.

### Kiểm thử hai request đồng thời

Dùng hai thread/barrier để gửi cùng key gần như cùng lúc. Xác minh:

- Chỉ một lần insert key thành công.
- Side effect nghiệp vụ chỉ xảy ra một lần.
- Request còn lại replay kết quả hoặc nhận trạng thái in-progress.
- Không có hai resource ID được tạo cho cùng operation.
- Không có deadlock hoặc lock chờ vô hạn.

Nên kiểm thử trên database production tương đương vì hành vi unique constraint và isolation có thể khác giữa H2 và PostgreSQL.

### Kiểm thử key bị tái sử dụng với payload khác

~~~java
@Test
void sameKeyWithDifferentPayloadShouldBeRejected() {
    service.createRefund(
            tenantId,
            "op-8f13",
            new RefundRequest("PAY-2048", new BigDecimal("250000"))
    );

    assertThatThrownBy(() -> service.createRefund(
            tenantId,
            "op-8f13",
            new RefundRequest("PAY-2048", new BigDecimal("300000"))
    )).isInstanceOf(IdempotencyKeyReuseException.class);

    verify(refundRepository, times(1))
            .createRefund(any(), eq(tenantId));
}
~~~

Test này bảo đảm key không thể bị tái sử dụng cho một số tiền hoàn khác. Fingerprint phải tính trên những trường ảnh hưởng đến nghiệp vụ.

## Những lỗi thường gặp

- **Tạo UUID mới trong mỗi lần retry:** mỗi lần gửi lại bị xem là thao tác mới. Giữ cùng key cho cùng một ý định.
- **Dùng toolCallId làm idempotency key:** model có thể tạo call ID khác khi thử lại. Dùng operation ID do backend quản lý.
- **Dùng conversationId làm key duy nhất:** một hội thoại có thể có nhiều hành động hợp lệ. Tạo key theo từng ý định nghiệp vụ.
- **Chỉ SELECT rồi INSERT:** hai request đồng thời đều có thể thấy key chưa tồn tại. Dùng unique constraint và insert nguyên tử.
- **Không lưu request fingerprint:** cùng key với payload khác có thể bị replay nhầm kết quả.
- **Hash JSON thô:** thứ tự field hoặc format số có thể làm cùng payload sinh hash khác. Chuẩn hóa trước khi hash.
- **Chỉ bảo vệ trong ToolCallback:** các đường gọi REST, job hoặc message khác có thể bỏ qua. Đặt idempotency ở application service.
- **Replay response trước khi kiểm tra quyền:** có thể làm lộ dữ liệu giữa tenant hoặc user.
- **Giữ transaction DB trong khi gọi provider lâu:** giữ lock và connection quá lâu, nhưng vẫn không tạo transaction phân tán. Dùng outbox hoặc workflow.
- **Xóa key đang xử lý:** request retry có thể tạo side effect lần nữa. Không dọn trạng thái chưa terminal.
- **Cho rằng timeout đồng nghĩa chưa commit:** server hoặc provider có thể đã thực hiện. Đối soát trước khi retry.
- **Cho rằng idempotency tạo exactly-once tuyệt đối:** hiệu quả phụ thuộc vào store bền vững, phạm vi key, retention và sự hỗ trợ của downstream.

## Checklist trước khi phát hành

- [ ] Mỗi thao tác có side effect xác định được operation name và key scope.
- [ ] Key được tạo một lần cho một ý định và giữ nguyên qua retry.
- [ ] Key không dựa riêng vào conversation ID hoặc tool call ID.
- [ ] Scope unique có tenant/principal và operation phù hợp.
- [ ] Payload được chuẩn hóa trước khi tạo fingerprint.
- [ ] Cùng key nhưng payload khác bị từ chối.
- [ ] Database có unique constraint trên composite scope.
- [ ] Việc giành quyền xử lý dùng insert nguyên tử.
- [ ] Trạng thái IN_PROGRESS/SUCCEEDED/FAILED_FINAL/UNKNOWN có hành vi rõ.
- [ ] Kết quả thành công được lưu để replay.
- [ ] Request trùng vẫn phải qua xác thực và authorization.
- [ ] Transaction bao trùm idempotency record và side effect local.
- [ ] External side effect dùng downstream idempotency key hoặc outbox/đối soát.
- [ ] TTL bao phủ retry window và không xóa record chưa terminal.
- [ ] Có test duplicate, concurrent request, key mismatch, rollback và timeout.

## Ghi nhớ khi thiết kế

Idempotency key nhận diện một ý định nghiệp vụ qua nhiều lần gửi. Request fingerprint xác nhận key đó vẫn đi cùng nội dung đã dùng lần đầu. Unique constraint giúp database chỉ cho một request giành quyền xử lý; record trạng thái và kết quả cho phép replay an toàn khi request được gửi lại.

Trong Spring AI, operation ID phải do backend quản lý và được truyền đến tool qua context đáng tin cậy. Đặt idempotency ở application service, kiểm tra quyền cả khi replay, và dùng transaction cho side effect trong cùng database. Với dịch vụ bên ngoài, kết hợp downstream idempotency key, outbox và đối soát. Cơ chế này giảm xử lý trùng trong phạm vi key và retention đã định nghĩa; nó không thay thế transaction phân tán hoặc bảo đảm exactly-once tuyệt đối.

## Tài liệu tham khảo

- [IETF Internet-Draft — The Idempotency-Key HTTP Header Field (draft-ietf-httpapi-idempotency-key-header-09, November 2026)](https://datatracker.ietf.org/doc/draft-ietf-httpapi-idempotency-key-header/)
- [PostgreSQL 19 — INSERT and ON CONFLICT](https://www.postgresql.org/docs/19/sql-insert.html)
- [PostgreSQL 19 — Index Uniqueness Checks](https://www.postgresql.org/docs/19/index-unique-checks.html)
- [Spring Framework — Programmatic Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html)
- [Spring Framework — Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html)
- [Spring AI — Tool Calling and ToolContext](https://docs.spring.io/spring-ai/reference/api/tools.html)
- [Stripe — Designing robust and predictable APIs with idempotency](https://stripe.com/blog/idempotency)

