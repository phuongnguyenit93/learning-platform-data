# Xây dựng idempotency key theo ý nghĩa nghiệp vụ

Trong serverless, cùng một yêu cầu có thể đến nhiều lần: HTTP client retry sau timeout, queue giao lại message, Lambda bị retry, workflow chạy lại một state hoặc người dùng bấm nút hai lần. Nếu mỗi lần nhận được đều tạo một side effect mới, hệ thống có thể tạo hai đơn hàng, thu tiền hai lần hoặc trừ tồn kho nhiều lần.

Idempotency giúp một ý định nghiệp vụ chỉ tạo ra một kết quả có hiệu lực, dù yêu cầu được gửi hoặc xử lý nhiều lần. Thành phần quan trọng là idempotency key: định danh ổn định cho một lần thực hiện nghiệp vụ cụ thể.

Một key tốt phải trả lời được câu hỏi: **Đây có phải cùng một ý định nghiệp vụ đã được gửi lại, hay là một ý định mới tình cờ có payload giống hệt?**

Không nên tạo key tùy tiện từ toàn bộ payload rồi xem hai payload giống nhau là cùng một giao dịch. Khách hàng có thể chủ động mua cùng một sản phẩm hai lần với cùng số lượng và giá. Đó là hai ý định hợp lệ khác nhau. Key cần gắn với danh tính của thao tác nghiệp vụ, còn fingerprint của payload dùng để phát hiện việc một key bị tái sử dụng với dữ liệu khác.

Bài học này trình bày cách xác định business intent, thiết kế scope và vòng đời key, lưu trạng thái idempotency an toàn khi có concurrency, xử lý side effect bên ngoài và áp dụng trong Java serverless.

## 1. Idempotency giải quyết vấn đề gì?

Một thao tác idempotent có thể được thực hiện lặp lại mà kết quả nghiệp vụ cuối cùng không thay đổi sau lần đầu tiên.

Ví dụ:

- Tạo order với cùng key chỉ tạo một order.
- Capture payment với cùng key chỉ tạo một payment capture.
- Ghi nhận event đã xử lý với cùng event identity không chạy side effect lần nữa.
- Release một reservation đã release không làm tồn kho tăng hai lần.

Ngược lại, nếu cùng một yêu cầu được xử lý hai lần và tạo hai order hoặc hai lần charge, thao tác đó chưa idempotent.

### 1.1. Vì sao serverless dễ gặp duplicate?

Các hệ thống serverless thường ưu tiên delivery có retry để tăng khả năng hoàn tất công việc. Vì vậy, một handler có thể được gọi lại trong các tình huống:

- HTTP client không nhận response do network timeout dù server đã commit.
- Lambda xử lý message nhưng bị lỗi trước khi event source nhận được kết quả thành công.
- SQS hoặc Pub/Sub giao lại message.
- Worker hoàn tất side effect nhưng mất kết nối trước khi ack.
- Step Functions retry Task sau lỗi tạm thời.
- Người dùng gửi lại request do không biết lần trước đã thành công hay chưa.
- Một DLQ message được replay sau nhiều giờ hoặc nhiều ngày.

Không thể dựa vào giả định một message chỉ được giao một lần. Hãy thiết kế consumer để duplicate delivery không làm lặp tác động nghiệp vụ.

### 1.2. Idempotency không phải exactly-once delivery

Cần phân biệt:

| Khái niệm | Ý nghĩa |
|---|---|
| At-most-once | Có thể mất thao tác nhưng không xử lý lặp |
| At-least-once | Có thể giao/xử lý lặp để giảm nguy cơ mất việc |
| Deduplication | Nhận diện và bỏ qua bản sao theo một identity |
| Idempotent effect | Lặp thao tác không tạo thêm tác động nghiệp vụ |
| Exactly-once effect | Một tác động nghiệp vụ được commit đúng một lần trong phạm vi đã định nghĩa |

Một queue hoặc function không thể tự bảo đảm exactly-once cho toàn bộ chuỗi gồm broker, Java process, database và payment provider. Thực tế thường đạt được **effectively-once business outcome** bằng cách kết hợp delivery có retry, idempotency key, unique constraint, transaction, outbox/inbox và reconciliation.

Không gọi một hệ thống là exactly-once nếu chỉ có một bước dedup trong memory hoặc chỉ dựa vào tính năng FIFO của queue.

## 2. Xác định business intent trước khi tạo key

Idempotency key đại diện cho một lần thực hiện nghiệp vụ, không nhất thiết là một payload hay một message.

Ví dụ, cùng một khách hàng có thể đặt hai order khác nhau với nội dung giống hệt. Mỗi lần bấm xác nhận mua hàng là một intent riêng. Hệ thống cần một order request ID hoặc operation ID riêng cho từng lần xác nhận.

Một số business intent và key phù hợp:

| Nghiệp vụ | Định danh intent có thể dùng |
|---|---|
| Tạo order | order request ID được tạo khi người dùng xác nhận |
| Capture payment | payment attempt ID |
| Refund | refund request ID |
| Giữ tồn kho | reservation request ID |
| Gửi hóa đơn | invoice delivery operation ID |
| Xử lý một event | event source + event ID, kết hợp business operation ID nếu cần |
| Chạy một batch item | batch run ID + item operation ID |

Ví dụ với payment:

- Order 1042 có payment attempt A.
- Provider timeout và worker retry attempt A.
- Tất cả lần retry của attempt A phải dùng cùng key.
- Nếu payment bị từ chối và người dùng chủ động thử lại bằng một payment attempt mới, attempt B phải có key khác.

Không dùng order ID làm key cho mọi payment attempt nếu nghiệp vụ cho phép nhiều lần thử thanh toán hợp lệ.

### 2.1. Không tạo key chỉ từ payload hash

Giả sử hai request đều có nội dung:

~~~json
{
  "sku": "BOOK-01",
  "quantity": 1,
  "unitPrice": 250000
}
~~~

Nếu dùng SHA-256 của payload làm key, hai lần mua độc lập sẽ bị xem là cùng một thao tác. Request thứ hai có thể bị trả lại kết quả của lần mua đầu tiên và khách hàng không tạo được order mới.

Payload hash có vai trò khác: nó là **request fingerprint** để kiểm tra cùng một key có đang được dùng với cùng nội dung hay không.

Quy tắc:

- Business intent ID tạo ra hoặc nhận diện key.
- Fingerprint kiểm tra nội dung request.
- Key được giữ nguyên qua retry của cùng intent.
- Intent mới phải có key mới, kể cả payload giống hệt.

## 3. Thiết kế scope của idempotency key

Key cần được đặt trong một phạm vi rõ ràng. Cùng chuỗi key có thể hợp lệ cho hai tenant hoặc hai operation khác nhau.

Một scope thường gồm:

- Tenant hoặc account đã xác thực.
- Tên operation/API.
- Idempotency key.
- Có thể thêm phiên bản contract nếu semantics thay đổi.

Ví dụ khóa duy nhất:

~~~text
tenant_id + operation_name + idempotency_key
~~~

Ví dụ:

~~~text
tenant=tenant-17
operation=capture-payment
key=pay-attempt-8d71...
~~~

Không chỉ đặt unique constraint trên key toàn cục nếu hệ thống cho phép nhiều tenant tự sinh key. Ngược lại, không bỏ tenant khỏi scope rồi tin rằng client sẽ luôn tạo key duy nhất.

Scope cũng cần ngăn một key được dùng nhầm giữa các endpoint. Key của create-order không nên xung đột với key của refund-payment chỉ vì client gửi cùng chuỗi.

### 3.1. Key cần có entropy và không chứa dữ liệu nhạy cảm

Nếu client tạo key, dùng UUID ngẫu nhiên hoặc một giá trị đủ entropy. Nếu server tạo operation ID, tạo và lưu ID đó trước lần thử đầu tiên để các lần retry có thể lấy lại.

Không đưa email, số điện thoại, số thẻ, tên khách hàng hoặc dữ liệu nhạy cảm vào key. Key có thể xuất hiện trong database, log, trace hoặc hệ thống hỗ trợ.

Không xem idempotency key là credential để cấp quyền. Người có key không mặc nhiên được xem hoặc sửa kết quả; mọi request vẫn phải xác thực và phân quyền theo tenant/resource.

Có thể log một fingerprint rút gọn hoặc reference đã che bớt để điều tra, nhưng tránh ghi toàn bộ key nếu không cần.

## 4. Tạo và truyền key qua các lần retry

Key phải được tạo tại ranh giới nơi hệ thống biết một ý định nghiệp vụ mới bắt đầu.

Ví dụ HTTP API:

1. Client tạo một Idempotency-Key cho thao tác submit order.
2. Client gửi key cùng request.
3. Nếu timeout, client gửi lại đúng key và cùng payload.
4. Server trả lại kết quả đã lưu nếu thao tác trước hoàn tất.
5. Khi người dùng bắt đầu một lần đặt hàng mới, client tạo key mới.

Ví dụ message consumer:

1. Producer tạo operation ID khi nghiệp vụ bắt đầu.
2. Event mang operation ID trong payload hoặc metadata tin cậy.
3. Broker giao lại event, consumer đọc lại cùng operation ID.
4. Mọi retry và redelivery dùng lại key đó.
5. Replay DLQ cũng giữ nguyên operation ID nếu vẫn là cùng ý định nghiệp vụ.

Không tạo UUID mới ở đầu mỗi lần Lambda invocation. Nếu mỗi retry tạo key mới, hệ thống sẽ coi mỗi lần thử là một thao tác mới và idempotency mất tác dụng.

### 4.1. Không dùng execution ID hoặc attempt number làm business key

Step Functions execution ARN và retry attempt hữu ích cho tracing và vận hành, nhưng không nhất thiết đại diện cho ý định nghiệp vụ.

Nếu người vận hành khởi chạy một execution mới để phục hồi order đã lỗi, execution ARN sẽ khác. Business operation ID cần được giữ lại trong input hoặc lấy từ bản ghi nghiệp vụ.

Tương tự, không thêm attempt number vào key của một thao tác capture nếu các lần retry phải là cùng một capture. Attempt number chỉ phù hợp khi nghiệp vụ thực sự tạo một intent mới, chẳng hạn khách hàng xác nhận một payment attempt mới.

## 5. API HTTP với Idempotency-Key

Một API có thể nhận key qua header:

~~~http
POST /v1/orders
Idempotency-Key: 3d9b3c5e-2e7f-4a4d-9f9e-7c...
Content-Type: application/json
~~~

Server cần:

1. Xác thực caller và xác định tenant.
2. Kiểm tra key có mặt, đúng định dạng và nằm trong giới hạn độ dài.
3. Xác định operation scope.
4. Chuẩn hóa request và tính fingerprint.
5. Claim key atomically trong database.
6. Nếu đã hoàn tất với cùng fingerprint, trả lại kết quả đã lưu.
7. Nếu key đang xử lý, trả response theo contract đã công bố.
8. Nếu cùng key nhưng fingerprint khác, từ chối.

### 5.1. Response khi request được gửi lại

API cần quy định rõ response cho từng trạng thái:

| Trạng thái key | Hành vi có thể chọn |
|---|---|
| Chưa tồn tại | Claim và thực hiện operation |
| Đang xử lý | Trả 202 với operation status URL, hoặc 409/Retry-After theo contract |
| Đã hoàn tất | Trả lại status/body/resource reference đã lưu |
| Cùng key nhưng payload khác | Trả 409 Conflict |
| Thất bại tạm thời | Cho retry theo policy với cùng key |
| Bị từ chối vĩnh viễn | Trả lại lỗi đã lưu hoặc yêu cầu intent mới theo contract |
| Cần reconciliation | Trả trạng thái pending/unknown và tiếp tục đối soát |

Không có một status code duy nhất phù hợp cho mọi API. Điều quan trọng là contract phải nhất quán và client biết có nên retry, poll operation status hay tạo intent mới.

### 5.2. Trả lại kết quả gốc

Nếu request đầu đã tạo order 1042 và response bị mất, request retry cùng key nên nhận kết quả đại diện cho order 1042 đó.

Có thể lưu:

- HTTP status.
- Response body hoặc resource ID.
- Content type và một số header nghiệp vụ cần thiết.
- Thời điểm hoàn tất.
- API/contract version.

Không cần lưu mọi header. Không lưu Authorization, cookie, access token hoặc dữ liệu bí mật vào idempotency response.

Nếu response chứa dữ liệu có thể thay đổi theo quyền truy cập, hãy kiểm tra authorization lại trước khi trả dữ liệu đã lưu. Idempotency không được vượt qua ranh giới bảo mật.

## 6. Request fingerprint: phát hiện key bị dùng sai

Fingerprint đại diện cho nội dung có ý nghĩa nghiệp vụ của request. Khi cùng key được gửi lại, fingerprint phải khớp với lần đầu.

Không nên hash raw JSON tùy ý vì hai JSON có thể mang cùng ý nghĩa nhưng khác thứ tự field hoặc cách biểu diễn. Hãy canonicalize dữ liệu trước:

- Chuẩn hóa thứ tự field.
- Chuẩn hóa số và decimal scale theo quy tắc nghiệp vụ.
- Chuẩn hóa giá trị mặc định.
- Chuẩn hóa enum và mã đơn vị.
- Loại bỏ trace ID, request timestamp và metadata vận chuyển không ảnh hưởng nghiệp vụ.
- Giữ các field có ảnh hưởng đến kết quả như amount, currency, account và target resource.

Ví dụ, nếu amount là tiền, dùng BigDecimal với scale/currency được xác định; không chuyển qua double trước khi hash.

### 6.1. Java fingerprint example

Ví dụ dưới đây minh họa fingerprint từ các field đã chuẩn hóa:

~~~java
import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.Locale;
import java.util.UUID;

public final class PaymentFingerprint {

    public String calculate(
            String tenantId,
            UUID paymentAttemptId,
            BigDecimal amount,
            String currency) {

        String canonical = String.join("|",
                tenantId,
                paymentAttemptId.toString(),
                amount.stripTrailingZeros().toPlainString(),
                currency.toUpperCase(Locale.ROOT));

        try {
            byte[] digest = MessageDigest.getInstance("SHA-256")
                    .digest(canonical.getBytes(StandardCharsets.UTF_8));
            return HexFormat.of().formatHex(digest);
        } catch (NoSuchAlgorithmException error) {
            throw new IllegalStateException(error);
        }
    }
}
~~~

Đây là ví dụ tối giản. Trong production, canonical format phải có version, delimiter/encoding không nhập nhằng và quy tắc normalization rõ. Dùng serializer canonical hoặc cấu trúc length-prefixed nếu các field có thể chứa delimiter.

Không đưa field thay đổi theo lần gửi như trace ID hoặc timestamp nhận request vào fingerprint. Nếu không, retry hợp lệ có thể bị hiểu nhầm là payload khác.

## 7. Lưu idempotency record bền vững

Không dùng static map hoặc in-memory cache làm nguồn sự thật. Serverless instance có thể bị scale-to-zero, restart hoặc chạy song song ở nhiều instance. Một key phải được nhận diện nhất quán trên toàn bộ worker.

Một bảng có thể lưu:

~~~sql
CREATE TABLE idempotency_record (
    tenant_id            VARCHAR(100) NOT NULL,
    operation_name       VARCHAR(100) NOT NULL,
    idempotency_key      VARCHAR(200) NOT NULL,
    request_fingerprint  VARCHAR(128) NOT NULL,
    status               VARCHAR(32) NOT NULL,
    resource_id          VARCHAR(200),
    response_status      INTEGER,
    response_body        JSONB,
    provider_key         VARCHAR(200),
    owner_token          UUID,
    generation           BIGINT NOT NULL DEFAULT 1,
    lease_until          TIMESTAMPTZ,
    created_at           TIMESTAMPTZ NOT NULL,
    updated_at           TIMESTAMPTZ NOT NULL,
    expires_at           TIMESTAMPTZ,
    PRIMARY KEY (tenant_id, operation_name, idempotency_key)
);
~~~

Đây là schema minh họa theo PostgreSQL. Có thể dùng database hoặc durable key-value store khác nếu hỗ trợ conditional write/transaction tương đương.

Các trường quan trọng:

- Scope và key tạo unique identity.
- Fingerprint phát hiện reuse sai payload.
- Status cho biết operation đang ở bước nào.
- Resource/response lưu kết quả cần replay.
- Owner token và generation hỗ trợ lease/fencing.
- Provider key (nếu operation gọi dịch vụ ngoài) giữ ổn định qua retry.
- Expires at hỗ trợ retention và cleanup.

Không lưu raw request có chứa dữ liệu nhạy cảm nếu không cần. Nếu phải lưu response để replay, áp dụng quyền truy cập, encryption, retention và data minimization.

## 8. Các trạng thái của idempotency record

Một state model đơn giản:

~~~text
NEW
  -> IN_PROGRESS
       -> COMPLETED
       -> RETRYABLE_FAILURE
       -> RECONCILIATION_REQUIRED
       -> REJECTED
~~~

| Trạng thái | Ý nghĩa | Hành vi khi nhận lại cùng key |
|---|---|---|
| IN_PROGRESS | Một worker đang sở hữu operation | Không chạy song song side effect; chờ hoặc trả trạng thái đang xử lý |
| COMPLETED | Operation đã có kết quả cuối | Trả lại kết quả đã lưu |
| RETRYABLE_FAILURE | Lỗi tạm thời, có thể thử lại an toàn | Claim lại theo policy với cùng key |
| RECONCILIATION_REQUIRED | Không rõ side effect đã xảy ra chưa | Đối soát trước khi retry |
| REJECTED | Request bị từ chối vĩnh viễn theo contract | Trả lại lỗi đã lưu hoặc yêu cầu intent mới |

Không đánh dấu COMPLETED chỉ vì handler đã bắt đầu chạy hoặc đã gọi provider. Chỉ đánh dấu khi kết quả nghiệp vụ đã được xác nhận và lưu bền vững.

Một lỗi validation xác định trước side effect có thể được ghi REJECTED. Một timeout sau khi gọi provider không nên tự động ghi RETRYABLE_FAILURE vì provider có thể đã thực hiện thao tác.

## 9. Claim key atomically để chống race condition

Hai Lambda có thể nhận cùng một message hoặc hai HTTP request cùng key đến gần như đồng thời. Nếu cả hai cùng kiểm tra “chưa có record” rồi cùng tạo order, idempotency bị phá vỡ.

Cần một thao tác atomic:

- Unique constraint trên scope + key.
- Conditional insert/update.
- Transaction hoặc compare-and-set.
- Một worker duy nhất sở hữu lease hợp lệ tại một thời điểm.

Luồng claim:

~~~mermaid
flowchart TD
    A["Nhận request + key"] --> B["Canonicalize và fingerprint"]
    B --> C["Atomic insert / claim"]
    C --> D{"Đã claim được?"}
    D -->|Có| E["Thực hiện operation"]
    D -->|Không| F["Đọc record hiện có"]
    F --> G{"Fingerprint khớp?"}
    G -->|Không| H["409 Conflict"]
    G -->|Có| I{"Status"}
    I -->|COMPLETED| J["Replay kết quả"]
    I -->|IN_PROGRESS| K["Wait / 202 / Retry-After"]
    I -->|RETRYABLE| L["Claim lại theo lease"]
    I -->|RECONCILIATION| M["Đối soát trước"]
~~~

Không dùng mô hình “SELECT rồi INSERT” mà không có unique constraint hoặc transaction. Hai request có thể cùng SELECT không thấy record trước khi cả hai INSERT.

### 9.1. Pseudocode claim

Một cách triển khai với database:

1. Bắt đầu transaction.
2. Thử INSERT record với status IN_PROGRESS và owner token mới.
3. Nếu insert thành công, commit claim.
4. Nếu unique conflict, đọc record hiện có.
5. So fingerprint; nếu khác, trả conflict.
6. Nếu COMPLETED, trả kết quả lưu.
7. Nếu lease còn hiệu lực, báo operation đang xử lý.
8. Nếu lease hết hạn và state cho phép reclaim, update owner/generation có điều kiện.
9. Commit trước khi thực hiện network call dài.

Unique constraint là lớp bảo vệ cuối cùng trước hai request đồng thời. Không dựa vào một check ở Java process.

## 10. Lease và fencing khi worker bị dừng

Một worker có thể bị terminate sau khi claim key. Nếu record giữ IN_PROGRESS mãi mãi, operation bị kẹt. Lease cho phép worker khác reclaim sau một khoảng thời gian.

Nhưng lease có một rủi ro: worker cũ có thể vẫn chạy sau khi lease hết hạn, trong khi worker mới đã reclaim key.

Dùng owner token và generation:

- Mỗi lần claim tạo owner token mới.
- Mỗi lần reclaim tăng generation.
- Khi ghi kết quả, worker phải cập nhật với owner token/generation hiện tại.
- Worker cũ không được ghi đè kết quả của worker mới.

Ví dụ điều kiện cập nhật:

~~~sql
UPDATE idempotency_record
SET status = 'COMPLETED',
    response_status = :response_status,
    response_body = CAST(:response_body AS JSONB),
    updated_at = NOW()
WHERE tenant_id = :tenant_id
  AND operation_name = :operation_name
  AND idempotency_key = :key
  AND status = 'IN_PROGRESS'
  AND owner_token = :owner_token
  AND generation = :generation;
~~~

Nếu số row được cập nhật bằng zero, worker không còn sở hữu operation. Nó cần đọc trạng thái hiện tại và không được ghi đè.

Fencing chỉ bảo vệ cập nhật vào store kiểm tra generation. Với external provider, vẫn cần provider idempotency key hoặc reconciliation để worker cũ và mới không tạo hai side effect.

## 11. Không giữ database transaction trong lúc gọi API ngoài

Một anti-pattern là mở transaction, giữ row lock rồi gọi payment provider qua network. Nếu provider chậm, transaction giữ lock lâu, connection bị chiếm và database có thể nghẽn.

Thay vào đó:

1. Transaction ngắn để claim key và tạo operation state.
2. Commit.
3. Gọi provider ngoài transaction với stable provider key.
4. Transaction khác lưu kết quả provider và cập nhật business/idempotency state.
5. Nếu process chết giữa các bước, retry hoặc reconciler tiếp tục từ state bền vững.

Nếu business row và idempotency record nằm cùng database, có thể commit chúng trong cùng transaction để tránh một bên hoàn tất còn bên kia chưa ghi.

Với provider ngoài, không thể atomic commit giữa database của bạn và hệ thống provider nếu không có distributed transaction protocol mà cả hai hỗ trợ. Hãy thiết kế state machine và reconcile cho khoảng trống đó.

## 12. External side effect cần provider idempotency

Giả sử Java Lambda gọi payment provider:

1. Provider đã capture payment.
2. Response bị mất do network timeout.
3. Lambda ném exception.
4. Queue giao lại message.
5. Worker gọi capture lần nữa.

Nếu provider hỗ trợ idempotency key, gửi cùng một provider key trong mọi lần thử của cùng payment intent. Provider có thể trả lại kết quả giao dịch đã tạo thay vì capture thêm.

Provider key nên được lưu trong idempotency record trước lần gọi đầu tiên. Không tạo key mới khi retry.

### 12.1. Khi provider không hỗ trợ idempotency

Nếu provider không có idempotency key, cần dùng business reference và API tra cứu trạng thái nếu có:

- Gửi một merchant reference duy nhất cho operation.
- Khi timeout, truy vấn giao dịch theo reference.
- Nếu đã thành công, ghi nhận kết quả và không gọi lại thao tác tạo mới.
- Nếu chưa có giao dịch, retry theo policy.
- Nếu không xác định được, giữ trạng thái RECONCILIATION_REQUIRED và chuyển xử lý thủ công hoặc job đối soát.

Không thể đảm bảo không có duplicate nếu provider không hỗ trợ idempotency, không có unique merchant reference và cũng không có cách tra cứu kết quả.

### 12.2. Thời hạn idempotency của provider

Provider có thể chỉ giữ idempotency key trong một khoảng thời gian. Nếu hệ thống replay DLQ sau khi provider đã quên key, gửi lại cùng key có thể tạo side effect mới tùy contract của provider.

Vì vậy:

- Đọc retention window trong tài liệu provider.
- Lưu provider transaction/reference ID sau khi biết kết quả.
- Không replay thao tác cũ mù quáng sau khi provider key hết hạn.
- Chạy reconciliation trước khi replay ngoài retention window.
- Lưu local idempotency record đủ lâu cho retry và recovery.

## 13. Transactional outbox và inbox

Một thao tác có thể vừa cập nhật database vừa publish event. Nếu commit database thành công nhưng publish thất bại, hệ thống mất event. Nếu publish thành công nhưng transaction rollback, consumer nhận event cho dữ liệu chưa tồn tại.

Transactional outbox giải quyết bằng cách ghi business state và outbox row trong cùng transaction:

~~~mermaid
flowchart TD
    A["Java command handler"] --> T["Database transaction"]
    T --> B["Update business row"]
    T --> O["Insert outbox event"]
    B --> C["Commit"]
    O --> C
    C --> P["Outbox publisher"]
    P --> Q["Broker"]
    Q --> I["Consumer inbox / idempotency"]
    I --> D["Business effect"]
~~~

Publisher có thể gửi lại cùng outbox event nếu không biết lần gửi trước đã thành công chưa. Vì vậy event ID phải ổn định và consumer cần inbox/dedup.

Inbox lưu identity của event đã xử lý, ví dụ source + event ID, cùng trạng thái hoặc transaction nghiệp vụ. Unique constraint ngăn hai consumer xử lý cùng event identity đồng thời.

Outbox giải quyết tính nguyên tử giữa business database update và việc ghi ý định publish. Nó không tự bảo đảm broker chỉ giao một lần; publisher và consumer vẫn cần retry/idempotency.

## 14. Event ID khác business idempotency key

Event ID định danh một event cụ thể. Business key định danh một ý định nghiệp vụ cụ thể.

Ví dụ:

- Producer tạo CloudEvent với source /orders và id evt-91.
- Broker giao lại đúng event đó nhiều lần; source + id vẫn giữ nguyên.
- Consumer dùng source + id để dedup delivery của event.
- Event yêu cầu capture payment cho payment attempt P-17; consumer dùng operation capture-payment:P-17 làm business key.
- Nếu cùng một payment intent được phát lại dưới event ID mới, business key vẫn ngăn capture lần hai.

Với CloudEvents, source + id là cặp định danh event phù hợp để nhận diện bản sao cùng event. Nhưng event ID mới không tự chứng minh nghiệp vụ mới; producer có thể phát lại cùng command dưới ID khác. Ngược lại, cùng một business object có thể tạo nhiều event hợp lệ khác nhau.

Thường nên có cả hai lớp:

1. Transport/event dedup theo source + event ID.
2. Business idempotency theo operation + business intent ID.

Không dùng timestamp hoặc message receive count làm event identity.

## 15. Xây dựng key cho từng loại trigger

| Trigger | Identity nên giữ ổn định | Lưu ý |
|---|---|---|
| HTTP API | Idempotency-Key của một client intent | Scope theo tenant và operation |
| SQS | Message/business operation ID trong payload; event ID nếu có | Standard queue có thể giao lại |
| SQS FIFO | Message dedup ID cho publish và business key ở consumer | Deduplication window của broker không thay thế store bền vững |
| Pub/Sub | Message/event identity và business operation ID | Redelivery có thể xảy ra trước ack |
| Kafka | Event identity hoặc topic/partition/offset cho delivery tracking; business key cho effect | Offset không đại diện cho một intent nghiệp vụ xuyên lần publish |
| Step Functions | Business operation ID trong execution input | Retry/redrive phải giữ nguyên ID |
| Scheduled job | Job run ID + item ID | Một lịch chạy mới là intent mới nếu nghiệp vụ quy định |

Không lấy queue receipt handle, delivery attempt hoặc visibility token làm business key. Những giá trị này có thể thay đổi qua lần giao lại.

## 16. Java service xử lý idempotency

Một service có thể tách các trách nhiệm:

- IdempotencyStore: claim, đọc state và cập nhật kết quả.
- RequestFingerprinter: canonicalize và fingerprint.
- BusinessService: thực hiện nghiệp vụ.
- ExternalClient: gọi provider bằng stable provider key.
- Reconciler: xử lý kết quả không rõ.
- Transaction boundary: commit business state và idempotency result cùng nhau khi có thể.

Ví dụ interface:

~~~java
public interface IdempotencyStore {
    ClaimResult claim(
            String tenantId,
            String operation,
            String key,
            String fingerprint);

    void complete(
            Claim claim,
            String resourceId,
            PaymentResult result);

    void markRetryable(Claim claim, String reason);

    void markReconciliationRequired(Claim claim, String reason);

    void markRejected(Claim claim, String reason);
}

public interface PaymentGateway {
    PaymentResult capture(
            PaymentCommand command,
            String providerIdempotencyKey);
}
~~~

ClaimResult có thể là một trong các kết quả:

~~~text
ACQUIRED
ALREADY_COMPLETED
IN_PROGRESS
FINGERPRINT_MISMATCH
RECONCILIATION_REQUIRED
REJECTED
~~~

Ví dụ orchestration:

~~~java
public final class IdempotentCaptureService {

    private final IdempotencyStore store;
    private final PaymentGateway gateway;

    public IdempotentCaptureService(
            IdempotencyStore store,
            PaymentGateway gateway) {
        this.store = store;
        this.gateway = gateway;
    }

    public PaymentResult capture(PaymentCommand command) {
        String fingerprint = command.fingerprint();

        ClaimResult result = store.claim(
                command.tenantId(),
                "capture-payment",
                command.idempotencyKey(),
                fingerprint);

        if (result.isFingerprintMismatch()) {
            throw new IdempotencyConflictException(
                    "Key was already used with different request data");
        }

        if (result.isCompleted()) {
            return result.savedPaymentResult();
        }

        if (result.isInProgress()) {
            throw new OperationInProgressException(
                    result.operationReference());
        }

        if (result.requiresReconciliation()) {
            throw new ReconciliationRequiredException(
                    result.operationReference());
        }

        if (result.isRejected()) {
            throw new PreviouslyRejectedOperationException(
                    result.savedError());
        }

        Claim claim = result.claim();

        try {
            PaymentResult payment = gateway.capture(
                    command,
                    claim.providerIdempotencyKey());

            store.complete(
                    claim,
                    payment.paymentId(),
                    payment);

            return payment;
        } catch (OutcomeUnknownException error) {
            store.markReconciliationRequired(
                    claim,
                    error.getClass().getSimpleName());
            throw error;
        } catch (RetryablePaymentException error) {
            store.markRetryable(
                    claim,
                    error.getClass().getSimpleName());
            throw error;
        } catch (PermanentPaymentException error) {
            store.markRejected(
                    claim,
                    error.getClass().getSimpleName());
            throw error;
        }
    }
}
~~~

Đây là skeleton minh họa; các method cần được triển khai bằng transaction/conditional update và fencing như phần trước. Phân loại exception phải dựa trên contract của provider. Nếu provider có thể đã thực hiện side effect trước timeout, dùng OutcomeUnknownException và reconcile thay vì đánh dấu thất bại có thể retry mù quáng.

Khi store trả ALREADY_COMPLETED, trả kết quả đã lưu. Khi trả IN_PROGRESS, API có thể poll hoặc trả 202/409 theo contract. Không gọi gateway trong những nhánh đó.

## 17. Transaction cho local database effect

Nếu side effect chỉ là cập nhật cùng một database, có thể commit business update và idempotency completion trong một transaction.

Ví dụ logic:

~~~text
BEGIN

Lock/verify idempotency claim by owner_token + generation
Insert or update order row
Insert outbox event if needed
Update idempotency record to COMPLETED
Save response/resource reference

COMMIT
~~~

Nếu transaction rollback, cả business state và idempotency completion đều rollback. Retry có thể claim lại theo policy.

Nếu business update đã commit nhưng idempotency record được cập nhật ở transaction khác, process có thể chết ở giữa và request retry không biết side effect đã xảy ra. Đưa hai thay đổi vào cùng transaction khi chúng nằm trong cùng database.

Không thực hiện network call đến payment provider bên trong transaction này. External side effect cần state/reconciliation riêng.

## 18. Idempotency trong workflow và Saga

Một Step Functions workflow có thể retry từng Task. Business operation ID nên được truyền xuyên suốt:

~~~json
{
  "orderId": "order-1042",
  "paymentAttemptId": "payment-attempt-17",
  "operations": {
    "capturePaymentKey": "capture-payment-attempt-17",
    "reserveInventoryKey": "reserve-order-1042"
  }
}
~~~

Khi Task retry, Lambda nhận cùng key. Nếu execution được khởi chạy lại để phục hồi, workflow cần lấy lại operation ID từ order record hoặc input đã lưu.

Compensation là một business operation khác và cần key riêng. Ví dụ:

~~~text
capture-payment:payment-attempt-17
refund-payment:payment-attempt-17
release-inventory:reservation-771
~~~

Không dùng cùng key cho forward action và compensation vì chúng có semantics khác nhau. Refund cần idempotent riêng để retry không hoàn tiền hai lần.

Nếu Saga chạy compensation sau timeout nhưng forward action có thể đã thành công, hãy reconcile forward action trước khi quyết định có cần bù hay không.

## 19. Retention và vòng đời key

Nếu xóa idempotency record quá sớm, một message cũ được replay có thể được xem như intent mới. Nếu giữ vô thời hạn, storage tăng và dữ liệu cũ có thể gây khó quản trị.

Retention nên dài hơn khoảng thời gian lớn nhất mà cùng intent có thể được gửi lại:

- Client retry horizon.
- Broker retention và redelivery horizon.
- DLQ retention và thời gian replay dự kiến.
- Workflow duration, retry và redrive window.
- Thời gian reconciliation/manual recovery.
- Provider idempotency retention.
- Quy định lưu trữ/audit của nghiệp vụ.

Không đặt TTL chỉ dựa trên thời gian xử lý thông thường. Một event có thể được replay sau vài ngày khi sự cố được khắc phục.

Có thể xóa response body trước nhưng giữ tombstone/key fingerprint/resource reference lâu hơn nếu cần ngăn side effect lặp. Quy tắc cleanup phải tránh xóa record IN_PROGRESS hoặc RECONCILIATION_REQUIRED.

Nếu key hết hạn theo contract API, tài liệu phải nói rõ client không được retry intent cũ sau thời hạn đó mà không kiểm tra trạng thái.

## 20. Bảo mật và quyền riêng tư

Idempotency key không phải secret xác thực, nhưng vẫn là metadata có thể liên kết với một operation. Bảo vệ nó như một identifier có kiểm soát:

- Scope theo tenant đã xác thực, không theo tenant ID do client tùy ý khai báo.
- Không log full key nếu không cần.
- Không chứa PII hoặc payment data trong key.
- Không trả response đã lưu trước khi kiểm tra authorization hiện tại.
- Mã hóa dữ liệu lưu trữ theo policy.
- Giới hạn quyền đọc bảng idempotency.
- Chống việc client tạo vô hạn key để làm phình storage.
- Áp dụng rate limit và quota theo principal/tenant.
- Không để key trở thành cách đoán resource ID hoặc bypass access control.

Fingerprint cũng có thể tiết lộ thông tin nếu được tính từ dữ liệu có entropy thấp và bị lộ. Dùng hash/HMAC phù hợp với threat model, không lưu raw secret trong fingerprint input logs.

## 21. Các lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Tạo UUID mới mỗi lần retry | Mỗi lần thử trở thành operation mới | Tạo key một lần tại ranh giới business intent |
| Dùng payload hash làm key | Hai intent hợp lệ có payload giống nhau bị gộp | Dùng operation ID; fingerprint chỉ để so payload |
| Không có unique constraint | Hai worker cùng tạo side effect | Atomic claim và database uniqueness |
| Dùng static map | Mất state khi scale/restart | Durable store dùng chung |
| Chỉ dedup bằng event ID | Event mới có thể lặp cùng business command | Thêm business idempotency key |
| Dùng execution ARN | Execution mới không nhận ra intent cũ | Giữ business operation ID |
| Đánh dấu complete trước provider result | Retry bị bỏ qua dù side effect chưa xảy ra | Chỉ complete sau xác nhận bền vững |
| Retry ngay sau timeout mơ hồ | Có thể tạo side effect trùng | Reconcile hoặc dùng provider key |
| Lease không có fencing | Worker cũ ghi đè worker mới | Owner token và generation |
| TTL quá ngắn | Replay cũ tạo giao dịch mới | Retention theo retry/replay horizon |
| Dùng chung key cho capture và refund | Hai operation khác nhau bị xung đột | Key namespace theo operation |
| Trả kết quả cũ mà không auth lại | Có thể lộ dữ liệu của tenant/resource | Authorization trước khi replay response |

## 22. Test plan cho idempotency

Cần kiểm thử cả trường hợp tuần tự, đồng thời và crash ở ranh giới side effect.

| Test | Tình huống | Kết quả mong đợi |
|---|---|---|
| ID-01 | Cùng key, cùng payload gửi hai lần | Một business effect; lần hai replay kết quả |
| ID-02 | Cùng key, payload khác | Conflict; không chạy side effect thứ hai |
| ID-03 | Hai request cùng key đồng thời | Chỉ một worker claim được |
| ID-04 | Hai tenant dùng cùng chuỗi key | Không xung đột nếu scope khác nhau |
| ID-05 | Hai intent mới có payload giống nhau | Hai key khác nhau, hai operation hợp lệ |
| ID-06 | Worker chết sau claim trước side effect | Lease/recovery cho phép tiếp tục |
| ID-07 | Provider thành công nhưng response timeout | Retry/reconcile không capture lần hai |
| ID-08 | Worker chết sau provider success trước DB update | Stable provider key hoặc reconciliation phục hồi |
| ID-09 | Lease hết hạn khi worker cũ còn chạy | Fencing ngăn worker cũ ghi đè |
| ID-10 | Event redelivery cùng source + id | Inbox bỏ qua duplicate |
| ID-11 | Event ID mới nhưng business intent cũ | Business key ngăn side effect lặp |
| ID-12 | Replay DLQ sau thời gian dài | Kiểm tra retention và reconcile trước replay |
| ID-13 | Key hết hạn | Hành vi theo contract; không âm thầm tạo duplicate |
| ID-14 | Callback/compensation được gọi hai lần | Một business effect bù |
| ID-15 | Unauthorized caller dùng key đã biết | Không được xem hoặc thay đổi kết quả |

### 22.1. Kiểm thử concurrency thực

Không chỉ mock store rồi kiểm tra method được gọi một lần. Cần integration test với database thật hoặc test database có unique constraint/transaction tương đương:

1. Khởi chạy nhiều request đồng thời cùng scope/key.
2. Dùng barrier để các request bắt đầu gần như cùng lúc.
3. Xác minh chỉ một request nhận claim.
4. Xác minh chỉ một provider call hoặc business insert được commit.
5. Xác minh request còn lại nhận IN_PROGRESS hoặc kết quả đã hoàn tất.
6. Chạy lại sau khi process bị dừng giữa các bước.

Kiểm thử bằng nhiều instance/process để chứng minh cơ chế không phụ thuộc synchronized hoặc static lock trong JVM.

## 23. Quy trình thiết kế idempotency key

1. **Xác định business intent.** Một lần đặt hàng, một payment attempt hay một refund request là một intent?
2. **Chọn operation ID ổn định.** Tạo và lưu trước lần thử đầu tiên.
3. **Xác định scope.** Tenant + operation + key.
4. **Tách key và fingerprint.** Key nhận diện intent; fingerprint xác minh request data.
5. **Đặt unique constraint.** Bảo vệ claim trước concurrency giữa nhiều instance.
6. **Thiết kế state machine.** IN_PROGRESS, COMPLETED, RETRYABLE_FAILURE, RECONCILIATION_REQUIRED và REJECTED.
7. **Dùng lease/fencing.** Cho phép recovery mà không để worker cũ ghi đè.
8. **Bảo vệ external side effect.** Truyền stable provider key hoặc reconciliation reference.
9. **Dùng transaction/outbox.** Commit business state và idempotency record nguyên tử khi có thể.
10. **Đặt retention.** Bao phủ client retry, broker redelivery, DLQ replay và workflow recovery.
11. **Kiểm tra authorization.** Idempotency không thay thế access control.
12. **Test crash và race.** Mô phỏng timeout trước/sau side effect và nhiều request đồng thời.

Idempotency key tốt bắt đầu từ mô hình nghiệp vụ rõ ràng. Khi key đại diện cho một intent ổn định, fingerprint phát hiện reuse sai dữ liệu, database claim atomically và external side effect có provider key hoặc reconciliation, Java serverless worker có thể retry an toàn hơn mà không tạo thêm order, payment hoặc reservation ngoài ý muốn.

## 24. Câu hỏi tự kiểm tra

- Idempotency khác exactly-once delivery như thế nào?
- Vì sao key phải đại diện cho business intent?
- Vì sao không nên dùng payload hash làm key duy nhất?
- Một payment attempt mới cần key khác trong trường hợp nào?
- Scope tenant + operation + key ngăn xung đột ra sao?
- Fingerprint cần canonicalize những field nào?
- Vì sao SELECT rồi INSERT không có unique constraint là không an toàn?
- Lease và fencing giải quyết hai vấn đề nào?
- Vì sao không giữ database transaction trong lúc gọi provider?
- Làm gì khi provider đã thực hiện side effect nhưng response bị timeout?
- Transactional outbox và inbox bổ sung idempotency như thế nào?
- Event ID khác business idempotency key ở đâu?
- Vì sao Step Functions retry cần giữ nguyên operation ID?
- Retention của idempotency record cần dựa trên những khoảng thời gian nào?
- Làm sao kiểm thử hai Lambda instance cùng nhận một key?


