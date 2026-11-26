# Retry operation không tạo side effect kép trong Spring Batch

> **Chương:** Idempotency
>
> **Module:** SPRING_BATCH_SCALING_OPERATIONS — Mở rộng Spring Batch cho workload dữ liệu lớn bằng multi-threaded step, parallel steps, partitioning và các mô hình phân tán; đồng thời đo nút thắt, bảo đảm thread safety, retry/restart và chọn kiến trúc phù hợp tài nguyên. Bài học tập trung vào **cách retry cùng một operation mà không thực hiện tác dụng nghiệp vụ hai lần**.

Khi xử lý dữ liệu lớn, **một attempt thất bại không đồng nghĩa một operation chưa gây tác dụng phụ**. Worker có thể đã ghi sổ, gửi lệnh thanh toán hoặc phát message thành công, nhưng mất phản hồi trước khi lưu checkpoint. Nếu cứ retry bằng một request mới, hệ thống có nguy cơ tính tiền hai lần, tạo hai hóa đơn hoặc gửi trùng thông báo. Mục tiêu là biến việc thử lại thành hành vi **có thể kiểm chứng và phục hồi**, không phải loại bỏ hoàn toàn retry.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **operation**, **attempt**, **side effect**, **acknowledgement** và **kết quả cuối cùng**; chỉ ra vì sao timeout tạo trạng thái **chưa xác định**.
2. Chọn khóa **idempotency key** dựa trên ý nghĩa nghiệp vụ, ổn định qua retry, rollback, restart và message redelivery.
3. Thiết kế thao tác database an toàn với **unique constraint, transaction và kiểm tra payload**, không dựa vào check-then-act trong RAM.
4. Xây dựng luồng **durable operation intent → dispatcher → hệ thống đích → reconciliation** cho API ngoài transaction của Spring Batch.
5. Cấu hình retry có chọn lọc, backoff, concurrency bounds và tránh retry lồng nhau khiến side effect bị nhân bội.
6. Kiểm thử các **crash windows**, hai worker cùng operation, thay đổi payload, kết quả không rõ và replay sau restart.

## 1. Chỉ một operation, nhưng có thể nhiều attempt

Giả sử một khách hàng yêu cầu chuyển 250.000 VND từ ví A sang ví B. Nghiệp vụ định nghĩa một operation:

~~~text
operationId  = "TRANSFER-2026-000123"
tenantId     = "tenant-A"
fromWallet   = "wallet-01"
toWallet     = "wallet-02"
amountMinor  = 250000
currency     = "VND"
~~~

Worker gọi một dịch vụ chuyển tiền. Dịch vụ nhận request, hoàn thành chuyển khoản nhưng response bị mất:

~~~mermaid
sequenceDiagram
    participant W as Batch worker
    participant G as Transfer API
    participant D as Gateway ledger
    W->>G: Transfer(operationId=TRANSFER-000123)
    G->>D: Ghi chuyển khoản
    D-->>G: COMMIT thành công
    G--xW: Response thất lạc
    Note over W: Worker chỉ thấy timeout
    W->>G: Retry với CÙNG operationId / idempotency key
    G->>D: Tra trạng thái operation đã lưu
    D-->>G: Đã hoàn tất, không chuyển lần hai
    G-->>W: Trả kết quả đã có
~~~

Nếu retry tạo `operationId` mới, gateway có thể xem đây là **yêu cầu chuyển khoản thứ hai**. Ngược lại, nếu gateway lưu trạng thái theo key và kiểm tra payload, nhiều delivery có thể trả về cùng kết quả mà không phát sinh chuyển khoản mới.

### Từ vựng cần phân biệt

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Business operation** | Một hành động nghiệp vụ với identity được xác định | Chuyển khoản `TRANSFER-000123` |
| **Attempt** | Một lần thử thực thi/gọi hệ thống đích | Gọi HTTP lần #1, #2, #3 |
| **Side effect** | Thay đổi trạng thái ngoài hàm hiện tại | Trừ tiền, ghi ledger, tạo invoice, gửi email |
| **Commit** | Ranh giới dữ liệu có hiệu lực bền vững trong một transaction | Gateway ghi sổ thành công |
| **ACK/response** | Tín hiệu được caller/broker quan sát | HTTP 200 hoặc broker ACK |
| **Retry** | Lặp attempt sau lỗi | Gọi lại với cùng key |
| **Restart** | Spring Batch tạo lượt thực thi mới của `JobInstance` đang thất bại/dừng | `JobOperator.restart(...)` |
| **Reconciliation** | Tra cứu/đối chiếu kết quả thực tại đích | Query transaction theo operation ID |

**Không đồng nhất “caller nhận exception” với “side effect thất bại”.** Ngoại lệ mạng có thể xảy ra sau khi đích commit. Đây là lý do idempotency phải nằm ở **hệ thống có thẩm quyền thực hiện tác dụng**, hoặc được chứng minh bằng transaction atomic với nơi đó.

## 2. Định nghĩa “không tạo side effect kép” như một bất biến

Với nghiệp vụ chuyển khoản, một bất biến có thể là:

~~~text
Với mỗi (tenantId, operationId):
  số lần ghi hiệu ứng chuyển tiền được chấp nhận <= 1

Nếu cùng operationId xuất hiện lại với cùng payload:
  trả kết quả đã có hoặc tiếp tục trạng thái đang xử lý;
  KHÔNG tạo transfer mới.

Nếu cùng operationId xuất hiện với payload khác:
  báo conflict; KHÔNG tự chọn bản mới nhất.
~~~

Trong mô hình có thể hủy/hoàn tiền, việc *hoàn tiền* là **một operation khác với identity riêng**, có thể tham chiếu operation gốc. Không dùng việc ghi hai bút toán đối ứng như cái cớ để coi hai lần capture trùng là an toàn.

### Idempotency không phải chỉ “có một hàng trong DB”

- Có thể chỉ có **một order row** nhưng hai email xác nhận được gửi đi.
- Có thể chỉ có **một invoice row** nhưng hai yêu cầu thanh toán được gửi sang PSP.
- Có thể broker deliver hai lần nhưng ledger chỉ ghi một bút toán: **delivery lặp, effect không lặp**.
- Có thể writer dùng `ON CONFLICT DO NOTHING` nhưng cùng key lại mang amount khác: không có row thứ hai, song **lỗi dữ liệu bị che**.

Thiết kế cần xác định **tất cả side effects** của operation, không chỉ bảng mà Spring Batch ghi trực tiếp.

## 3. Các “khoảng hở” khiến retry trở nên nguy hiểm

Giả sử worker vừa ghi database vừa gọi API:

| Điểm lỗi | Database của Batch | Hệ thống đích | Caller biết gì? | Nguy cơ khi retry |
| --- | --- | --- | --- | --- |
| Trước khi gửi yêu cầu | Chưa advance checkpoint | Chưa có effect | Lỗi kết nối trước khi gửi | Có thể thử lại |
| Đã gửi request nhưng chưa nhận response | Có thể chưa commit | **Không rõ** đã xử lý hay chưa | Timeout | **Double effect** nếu gửi request mới không có key |
| Hệ thống đích commit nhưng response mất | Checkpoint có thể cũ | Đã có effect | Chỉ thấy timeout | Replay làm phát sinh effect thứ hai nếu đích không idempotent |
| DB writer ghi trong transaction rồi rollback | Metadata thường rollback theo transaction phù hợp | DB row chưa commit | Writer thất bại | Có thể thử lại an toàn nếu mọi effect cùng transaction |
| Checkpoint được ghi nhưng effect ngoài DB chưa bền vững | Đã tiến tới vị trí mới | Thiếu effect | Job có thể tưởng đã xử lý | **Mất operation** nếu không có durable pending state |
| Business DB commit trước broker ACK | Đã ghi kết quả | Đã có effect | Broker chưa biết | Broker giao lại request; cần dedupe |

### Bài học về transaction

`@Transactional` không tạo một transaction tự động bao trùm **HTTP API, SMTP, message broker và nhiều datasource độc lập**. Trong chunk-oriented step, transaction manager bảo vệ các resource được liên kết với transaction ấy; các tác dụng ngoài phạm vi vẫn cần idempotency/reconciliation.

~~~mermaid
flowchart TD
    A["Batch đọc item và quyết định operation"] --> B["Ghi durable intent trong DB transaction"]
    B --> C["Commit intent"]
    C --> D["Dispatcher gửi cùng idempotency key"]
    D --> E{"Gateway trả kết quả?"}
    E -- "Thành công" --> F["Lưu CONFIRMED"]
    E -- "Timeout / không rõ" --> G["Lưu UNKNOWN / pending reconciliation"]
    E -- "Lỗi vĩnh viễn rõ" --> H["Lưu FAILED_FINAL theo quy tắc"]
    G --> I["Tra trạng thái gateway theo operation key"]
    I --> F
    I --> G
~~~

**Không đánh dấu operation `CONFIRMED` khi chỉ mới gửi request thành công ở phía client.** Trạng thái xác nhận phải dựa trên bằng chứng từ đích hoặc một hợp đồng idempotency có thể tin cậy.

## 4. Chọn idempotency key đúng nghiệp vụ

Khóa phải **được tạo trước attempt đầu tiên** và giữ nguyên ở mọi đường replay của cùng operation. Chọn key theo business identity, không theo thời gian worker hiện tại.

| Ứng viên | Phù hợp? | Lý do |
| --- | --- | --- |
| `(tenantId, transferId)` | Thường **có** | Nhận diện operation chuyển khoản |
| `(tenantId, invoiceId, captureType)` | Có, nếu mỗi invoice chỉ cho đúng một capture loại đó | Cần hiểu quy tắc partial capture |
| `UUID.randomUUID()` mỗi attempt | **Không** | Retry tạo identity khác |
| `StepExecutionId` | **Không** làm business key | Worker có ID mới khi restart |
| `JobExecutionId` | **Không** làm business key | JobExecution thay đổi theo restart |
| `chunkIndex` | **Không đủ** | Chunk chứa nhiều operations, index có thể đổi khi input thay đổi |
| Message delivery tag | **Không** | Broker có thể cấp tag mới khi redelivery |
| Hash toàn payload | Chỉ phụ trợ | Hai operation hợp lệ có thể có payload giống nhau |

### Phạm vi dedupe phải rõ

Một key `ORDER-42` có thể trùng ở hai tenant. Ví dụ:

~~~text
namespace       = "billing"
tenantId        = "tenant-A"
operationType   = "capture"
businessId      = "PAY-42"
idempotencyKey  = "billing:tenant-A:capture:PAY-42"
~~~

Nếu order có thể capture nhiều lần hợp lệ (partial capture), key cần thêm **capture operation ID riêng**, không chỉ order ID. Ngược lại, đừng gắn `JobExecutionId` hoặc timestamp vào key khi cùng operation chạy lại, vì key mới sẽ mở cửa cho side effect mới.

### Payload phải ổn định hoặc phát hiện xung đột

Một idempotency key cần đi cùng payload có semantics không đổi, ví dụ:

~~~text
Key: tenant-A:CAPTURE:PAY-42
Payload v1: amount=250000 VND, beneficiary=wallet-01
Payload v2: amount=750000 VND, beneficiary=wallet-01
~~~

Không tự coi v2 là “retry” của v1. Phía nhận phải kiểm tra những trường bất biến (hoặc canonical payload fingerprint) và trả conflict. Nếu nghiệp vụ cho phép chỉnh số tiền, hãy định nghĩa **operation thay đổi** riêng, với version và identity phù hợp.

## 5. Cách đơn giản nhất: một transaction database và unique operation key

Khi tất cả tác dụng phụ quan trọng nằm trong **cùng một database transaction**, có thể thực thi bằng unique constraint:

~~~sql
-- PostgreSQL, schema minh họa.
CREATE TABLE transfer_ledger (
    tenant_id      VARCHAR(80) NOT NULL,
    operation_id   VARCHAR(160) NOT NULL,
    source_id      VARCHAR(160) NOT NULL,
    amount_minor   BIGINT NOT NULL,
    currency       VARCHAR(3) NOT NULL,
    payload_hash   VARCHAR(128) NOT NULL,
    applied_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (tenant_id, operation_id)
);
~~~

Kịch bản:

1. Worker A chèn operation `PAY-42`.
2. Worker B cũng chèn `PAY-42` do retry, broker redelivery hoặc partition overlap.
3. **Unique constraint** tại database chỉ cho phép một row cùng key được commit.
4. Worker nhận duplicate phải kiểm tra payload bất biến; nếu giống thì no-op thành công, nếu khác thì báo conflict.

Không làm:

~~~java
if (!repository.existsByOperationId(operationId)) {
    repository.insert(operation);
}
~~~

Đây là lỗi **check-then-act**: hai worker có thể cùng thấy `false` trước khi một worker insert. `synchronized` trong một JVM cũng không bảo vệ được các worker ở JVM khác.

### Java ví dụ: atomic insert rồi xác nhận duplicate

~~~java
import java.util.Objects;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

public record TransferOperation(
        String tenantId,
        String operationId,
        String sourceId,
        long amountMinor,
        String currency,
        String payloadHash) {}

@Service
public class TransferLedgerService {

    private final JdbcTemplate jdbc;

    public TransferLedgerService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(transactionManager = "businessTransactionManager")
    public void applyOnce(TransferOperation op) {
        int inserted = jdbc.update(
                """
                INSERT INTO transfer_ledger
                  (tenant_id, operation_id, source_id,
                   amount_minor, currency, payload_hash)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT (tenant_id, operation_id) DO NOTHING
                """,
                op.tenantId(), op.operationId(), op.sourceId(),
                op.amountMinor(), op.currency(), op.payloadHash());

        if (inserted == 1) {
            return; // Lần thực thi đầu tiên trong transaction này.
        }

        Boolean same = jdbc.queryForObject(
                """
                SELECT (source_id = ? AND amount_minor = ?
                        AND currency = ? AND payload_hash = ?)
                FROM transfer_ledger
                WHERE tenant_id = ? AND operation_id = ?
                """,
                Boolean.class,
                op.sourceId(), op.amountMinor(),
                op.currency(), op.payloadHash(),
                op.tenantId(), op.operationId());

        if (!Boolean.TRUE.equals(same)) {
            throw new IllegalStateException(
                    "Operation ID đã có nhưng payload khác nhau");
        }
        // Duplicate hợp lệ, không áp dụng side effect lần nữa.
    }
}
~~~

**Giới hạn của ví dụ:** `TransferOperation` và `TransferLedgerService` nên nằm trong **các file Java riêng**. PostgreSQL `ON CONFLICT`, text block Java 17 và `JdbcTemplate` được dùng để minh họa. Database `businessTransactionManager` phải quản lý **cùng datasource** với bảng ledger; lời gọi `applyOnce` phải đi qua Spring transaction proxy. Nếu service tự gọi method của chính nó qua `this`, hãy xem xét cơ chế proxy/self-invocation.

Ở isolation thông dụng `READ COMMITTED`, truy vấn kiểm tra duplicate sau khi `INSERT ... ON CONFLICT DO NOTHING` kết thúc có thể nhìn thấy row đã commit. Khi đổi isolation hoặc giao dịch phân tán, cần test concurrency/visibility đúng DBMS; không mặc định câu lệnh này hoạt động y hệt trên mọi database.

**Ví dụ chỉ bảo vệ việc ghi ledger**. Nếu sau đó chương trình gọi API trừ tiền hoặc gửi email, unique row tự thân không làm API/email idempotent. Không dùng mã trên như một giải pháp thanh toán hoàn chỉnh.

## 6. Nhiều side effects trong một operation

Một nghiệp vụ “xác nhận đơn hàng” có thể gồm:

- Ghi trạng thái order;
- Ghi một bản ghi ledger;
- Phát event `OrderConfirmed`;
- Gửi email xác nhận;
- Gọi dịch vụ đối tác.

Nếu chỉ dedupe lệnh cập nhật order, các bước khác vẫn có thể thực hiện lại khi retry.

~~~mermaid
flowchart TB
    O["Operation ORD-CONFIRM-42"] --> T["Một DB transaction"]
    T --> D1["Update order"]
    T --> D2["Insert ledger / audit"]
    T --> D3["Insert outbox event"]
    D3 --> P["Outbox dispatcher"]
    P --> B["Message broker"]
    B --> C["Consumer có inbox / dedupe"]
    C --> E["Email/API với key riêng nếu hỗ trợ"]
~~~

### Transactional outbox bảo vệ điều gì?

Outbox ghi **ý định phát event** trong cùng database transaction với thay đổi nghiệp vụ. Khi chunk commit, cả order, ledger và outbox row cùng bền vững. Dispatcher phát event sau commit.

Nhưng dispatcher cũng có thể crash **sau khi publish thành công, trước khi đánh dấu row đã gửi**. Vì vậy event có thể được phát hai lần; downstream vẫn cần inbox/idempotency hoặc cơ chế nhận trùng phù hợp.

### Khi external service không hỗ trợ idempotency

Với một hệ thống ngoài transaction và **không có API tra cứu kết quả**, không thể cam kết exactly-once effect chỉ bằng cách thêm một cờ ở database local. Nếu crash sau khi gửi nhưng trước khi nhận response, trạng thái tác dụng thật có thể không xác định.

Các hướng xử lý gồm:

1. Thỏa thuận bổ sung idempotency key/API tra cứu trạng thái từ đối tác.
2. Lưu durable intent và đưa trạng thái nghi vấn vào **manual review/reconciliation**.
3. Chấp nhận mô hình at-least-once/at-most-once có giới hạn và **công bố rõ rủi ro**, nếu yêu cầu nghiệp vụ cho phép.
4. Thiết kế thao tác bù (compensation) có identity riêng, không giả định bù sẽ luôn thành công tức thì.

Không tuyên bố “exactly-once” cho toàn chuỗi chỉ vì Spring Batch commit chunk thành công hoặc broker có một chế độ delivery được quảng bá là exactly-once.

## 7. Durable operation intent: không gọi API trực tiếp từ processor

Trong chunk-oriented processing, `ItemProcessor` có thể bị gọi lại sau rollback. Vì vậy đặt lệnh **gửi tiền thật, phát email thật hoặc publish event thật** ngay trong processor là một nguồn side effect kép.

Một thiết kế phù hợp hơn là:

1. Processor tạo **command dữ liệu thuần**, chứa stable operation ID.
2. Writer ghi command vào **bảng operation intent** trong transaction của chunk.
3. Worker dispatcher độc lập đọc intent, gọi external API bằng **cùng idempotency key**.
4. Kết quả được ghi lại theo trạng thái xác nhận; các trường hợp timeout cần reconciliation.

### Sơ đồ kiến trúc

~~~mermaid
flowchart LR
    S["Spring Batch Reader"] --> P["Pure Processor<br/>tạo command"]
    P --> W["Batch Writer"]
    W --> I[("Operation intent DB<br/>unique operation key")]
    I --> X["Dispatcher / claim"]
    X --> A["External API<br/>idempotency key"]
    A --> X
    X --> R[("Result / status ledger")]
    R --> Q["Reconciler / replay"]
    Q --> A
~~~

**Bản chất:** Batch commit đảm bảo **“ý định thực hiện operation này không bị mất”**. Dispatcher đảm bảo nỗ lực gửi, còn hệ thống đích và quy trình đối soát quyết định **“operation đã thật sự hoàn tất một lần hay chưa”**.

## 8. Thiết kế trạng thái cho operation bên ngoài

Một bảng `operation_intent` có thể mang các trạng thái:

| Trạng thái | Ý nghĩa | Có nên tự động gửi lại? |
| --- | --- | --- |
| `PENDING` | Ý định đã commit, chưa được claim | Có |
| `IN_FLIGHT` | Đã có worker claim và đang gọi | Không gửi lại mù; xét lease/fencing và provider idempotency |
| `CONFIRMED` | Có kết quả thành công đáng tin từ đích | Không |
| `UNKNOWN` | Request có thể đã được thực hiện nhưng không có phản hồi chắc chắn | **Tra trạng thái trước**, sau đó retry với cùng key nếu hợp đồng cho phép |
| `RETRYABLE_FAILURE` | Lỗi tạm thời đã được xác định | Có, sau backoff/`next_retry_at` |
| `FAILED_FINAL` | Lỗi cuối cùng rõ ràng, không cần/thể retry | Không tự động; chuyển review hoặc xử lý khác |

Không nên dùng một cột boolean `processed` cho mọi tình huống. `processed=false` không phân biệt chưa từng gửi với đã gửi nhưng mất reply.

### Schema PostgreSQL minh họa

~~~sql
CREATE TABLE operation_intent (
    tenant_id       VARCHAR(80)  NOT NULL,
    operation_id    VARCHAR(160) NOT NULL,
    operation_type  VARCHAR(80)  NOT NULL,
    source_version  VARCHAR(120) NOT NULL,
    source_id       VARCHAR(160) NOT NULL,
    payload_hash    VARCHAR(128) NOT NULL,
    amount_minor    BIGINT NOT NULL,
    currency        VARCHAR(3) NOT NULL,
    status          VARCHAR(30) NOT NULL,
    attempt_count   INTEGER NOT NULL DEFAULT 0,
    next_retry_at   TIMESTAMPTZ,
    lease_until     TIMESTAMPTZ,
    owner_token     VARCHAR(160),
    provider_ref    VARCHAR(200),
    last_error_code VARCHAR(100),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (tenant_id, operation_id),
    CONSTRAINT ck_intent_status CHECK (
        status IN ('PENDING','IN_FLIGHT','CONFIRMED',
                   'UNKNOWN','RETRYABLE_FAILURE','FAILED_FINAL')
    )
);

CREATE INDEX idx_intent_pending
    ON operation_intent (status, next_retry_at);
~~~

Đây là schema học tập, chưa bao gồm encryption, tenant access policy, payload storage, historical attempts, housekeeping và mọi index cho production. Có thể tách bảng attempts để audit từng lần gửi mà không cập nhật đè thông tin cũ.

### Bất biến dữ liệu quan trọng

Với một `(tenant_id, operation_id)`, `operation_type`, `amount_minor`, `currency` và `payload_hash` phải được kiểm tra khi nhận lại command. Nếu một operation đã `CONFIRMED` mà xuất hiện cùng key nhưng amount khác, phải báo **identity conflict**, không ghi đè thành request mới.

Một thao tác nghiệp vụ mới hợp lệ phải có operation ID mới theo quy tắc nghiệp vụ. Đừng tạo key mới chỉ vì retry bị timeout.

## 9. Writer của Spring Batch chỉ ghi intent bền vững

Ví dụ Spring Batch 5.x: `ItemProcessor` chuyển input thành command, còn writer lưu intent trong cùng business transaction.

### 9.1. Input và command

~~~java
public record PaymentInput(
        String sourceId,
        String paymentId,
        String tenantId,
        long amountMinor,
        String currency,
        String sourceVersion) {}

public record PaymentCommand(
        String sourceId,
        String sourceVersion,
        String tenantId,
        String operationId,
        long amountMinor,
        String currency,
        String payloadHash) {}
~~~

Các record trên là những kiểu Java do ứng dụng định nghĩa và nên đặt thành file phù hợp. Với payment, `operationId` nên lấy từ **payment/capture operation được xác định ở nghiệp vụ**, không tạo `UUID` mới khi gọi `process`.

~~~java
import org.springframework.batch.item.ItemProcessor;

public final class PaymentCommandProcessor
        implements ItemProcessor<PaymentInput, PaymentCommand> {

    @Override
    public PaymentCommand process(PaymentInput input) {
        if (input.amountMinor() <= 0) {
            throw new IllegalArgumentException(
                    "Amount phải dương");
        }

        String operationId = "CAPTURE:" + input.paymentId();
        String canonicalPayload = input.tenantId() + "|"
                + operationId + "|"
                + input.amountMinor() + "|"
                + input.currency();

        // Minh họa: hàm fingerprint phải được triển khai thống nhất,
        // có version và tránh kiểu ghép chuỗi mơ hồ trong production.
        String payloadHash = PayloadFingerprint.sha256(
                canonicalPayload);

        return new PaymentCommand(
                input.sourceId(), input.sourceVersion(),
                input.tenantId(), operationId,
                input.amountMinor(), input.currency(), payloadHash);
    }
}
~~~

`PayloadFingerprint` là **helper minh họa chưa được triển khai trong đoạn này**. Ở production, cần canonical representation có version, xử lý escaping và tính cả những trường bất biến quan trọng; không dùng nối chuỗi đơn giản làm chuẩn bảo mật. Đừng lấy hash làm **khóa nghiệp vụ duy nhất** vì hai operation hợp lệ vẫn có thể mang cùng payload.

### 9.2. Atomic insert command; duplicate phải kiểm tra

~~~java
import java.util.Objects;

import org.springframework.batch.item.Chunk;
import org.springframework.batch.item.ItemWriter;
import org.springframework.jdbc.core.JdbcTemplate;

public final class PaymentIntentWriter
        implements ItemWriter<PaymentCommand> {

    private final JdbcTemplate jdbc;

    public PaymentIntentWriter(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Override
    public void write(Chunk<? extends PaymentCommand> chunk) {
        for (PaymentCommand cmd : chunk) {
            int inserted = jdbc.update(
                    """
                    INSERT INTO operation_intent
                        (tenant_id, operation_id, operation_type,
                         source_version, source_id, payload_hash,
                         amount_minor, currency, status)
                    VALUES (?, ?, 'CAPTURE', ?, ?, ?, ?, ?, 'PENDING')
                    ON CONFLICT (tenant_id, operation_id) DO NOTHING
                    """,
                    cmd.tenantId(), cmd.operationId(),
                    cmd.sourceVersion(), cmd.sourceId(),
                    cmd.payloadHash(), cmd.amountMinor(),
                    cmd.currency());

            if (inserted == 1) {
                continue; // Intent mới đã được chuẩn bị để commit.
            }

            Boolean same = jdbc.queryForObject(
                    """
                    SELECT operation_type = 'CAPTURE'
                       AND source_version = ?
                       AND source_id = ?
                       AND payload_hash = ?
                       AND amount_minor = ?
                       AND currency = ?
                    FROM operation_intent
                    WHERE tenant_id = ? AND operation_id = ?
                    """,
                    Boolean.class,
                    cmd.sourceVersion(), cmd.sourceId(),
                    cmd.payloadHash(), cmd.amountMinor(),
                    cmd.currency(), cmd.tenantId(), cmd.operationId());

            if (!Boolean.TRUE.equals(same)) {
                throw new IllegalStateException(
                        "Operation ID trùng nhưng input khác");
            }
            // Không reset status CONFIRMED/IN_FLIGHT/UNKNOWN thành PENDING.
        }
    }
}
~~~

Code dùng `Chunk` của Spring Batch 5.x và `ON CONFLICT` của PostgreSQL. Đảm bảo `JdbcTemplate` gắn với datasource của **transaction manager dùng cho chunk step**. Nếu một record đã tồn tại với `status=CONFIRMED`, việc replay chunk chỉ xác nhận input đồng nhất, **không mở lại việc gửi API**.

Đây chưa phải writer bulk load tối ưu: kiểm tra từng item có thể tạo thêm database round-trip. Tối ưu bằng batch insert/staging/merge chỉ sau khi giữ được các bất biến **unique key, payload conflict và status không bị reset**.

### 9.3. Kết nối vào worker step

~~~java
@Bean
Step paymentIntentStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<PaymentInput> reader,
        ItemProcessor<PaymentInput, PaymentCommand> processor,
        ItemWriter<PaymentCommand> intentWriter) {

    return new StepBuilder("paymentIntentStep", jobRepository)
            .<PaymentInput, PaymentCommand>chunk(200, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(intentWriter)
            .build();
}
~~~

Đây là snippet cấu hình, cần `@Bean`, các import và bean reader/processor/writer thật trong ứng dụng. **Batch step chỉ bảo đảm command được ghi bền vững**, chưa bảo đảm payment ở provider đã được capture. `BatchStatus.COMPLETED` của bước này **không** được hiển thị như “toàn bộ thanh toán đã thành công” nếu còn intents đang chờ.

## 10. Dispatcher gửi API với cùng key và tự reconcile

Khi chuyển intent sang external API, cần một **dispatcher** với cơ chế claim bền vững và idempotency ở đích.

~~~text
DB operation_intent (PENDING)
    |
    +-- Claim atomically (IN_FLIGHT + owner_token + lease_until)
    |
    +-- Gateway.capture(
            idempotencyKey = tenantId + ":" + operationId,
            exact payload = amount/currency/recipient)
    |
    +-- Response CONFIRMED:
    |       ghi provider_ref + status CONFIRMED
    |
    +-- Timeout/connection lost:
    |       ghi UNKNOWN hoặc để lease expire để reconciler tra cứu
    |
    +-- Retryable explicit failure:
    |       ghi RETRYABLE_FAILURE + next_retry_at
    |
    +-- Permanent explicit rejection:
            ghi FAILED_FINAL + reason
~~~

### Chọn một trạng thái sau timeout

| Tín hiệu | Không nên làm | Nên làm |
| --- | --- | --- |
| Không kết nối được trước khi có khả năng gửi request | Tạo key mới cho lần sau | Retry cùng key, timeout/backoff theo policy |
| Read timeout sau khi request đã gửi | Đánh dấu “thất bại chắc chắn” | `UNKNOWN` hoặc trạng thái cần reconciliation |
| Provider xác nhận `CONFIRMED` | Gửi lại payment bằng key khác | Lưu reference, không gửi thêm |
| Provider xác nhận lỗi business vĩnh viễn | Retry vô hạn | `FAILED_FINAL`, có reason/audit |
| Provider trả rate limit/temporary unavailable | Retry ngay liên tục trên mọi worker | Backoff, jitter, global throughput cap |
| Cùng key nhưng payload khác | Ghi đè dữ liệu tại provider | Conflict, điều tra nguồn |

### Worker claim và fencing

Một bảng có `lease_until` không tự loại trừ việc worker cũ tiếp tục chạy sau khi lease hết hạn. Nếu dispatcher A gửi request rồi bị tạm dừng, dispatcher B có thể claim lại và cũng gửi.

Vì vậy:

- Claim/renew lease phải được cập nhật **atomically** ở DB, không chỉ `SELECT` rồi `UPDATE` rời rạc.
- Gắn `owner_token`/generation vào thao tác cập nhật trạng thái để worker cũ không ghi đè kết quả của owner mới.
- **Quan trọng nhất:** provider phải xử lý cùng idempotency key một cách an toàn nếu A và B gửi đồng thời. Lease không thể rollback request đã rời khỏi process.
- Nếu provider không thể dedupe, phải chọn quy trình reconciliation/manual review; không hứa exactly-once từ lease.

Một worker lấy nhiều công việc cùng lúc có thể dùng `SELECT ... FOR UPDATE SKIP LOCKED` trong một transaction **claim ngắn** rồi commit, nhưng không giữ database lock qua toàn bộ HTTP request kéo dài. Cần thiết kế thời hạn lease, heartbeat và recovery riêng; `SKIP LOCKED` không phải idempotency của API.

## 11. Retry policy: khi nào thử lại và bao nhiêu lần?

Không retry tất cả exception. Một policy cần phân loại:

| Exception/tình huống | Retry? | Lý do |
| --- | --- | --- |
| Kết nối tạm mất, provider 503 | Có, trong budget | Lỗi có thể hồi phục |
| Provider 429 / yêu cầu giảm tốc | Có nhưng tôn trọng backoff/quota | Retry dồn có thể làm outage nặng hơn |
| Gateway timeout sau khi gửi | Có điều kiện, **cùng key**; ưu tiên tra trạng thái | Kết quả trước có thể đã commit |
| Payload sai, thiếu trường bắt buộc | Không tự retry | Input không đổi thì lỗi không tự hết |
| Không có quyền, credentials sai | Thường fail/escalate | Retry không sửa quyền |
| Cùng key nhưng amount khác | Không | Xung đột identity nghiêm trọng |
| Unique conflict đã chứng minh same payload | Không cần ghi lại | Đây là replay hợp lệ |
| Unique conflict khác payload | Fail/quarantine | Không tự chọn bản nào được giữ |

### Tránh retry lồng nhau

Giả sử:

~~~text
Spring Batch retryLimit = 3
  × Spring Retry maxAttempts = 3
    × HTTP client retry = 2

Một item có thể kích hoạt tới 18 lần gọi HTTP
trong đường lỗi được minh họa, chưa kể restart.
~~~

Đây là **nguy cơ nhân budget** trong một kịch bản nơi mỗi tầng cho phép thử tối đa như cấu hình; số calls thực tế phụ thuộc loại exception, transaction rollback và thứ tự xử lý. Một endpoint đang quá tải có thể càng chậm hơn nếu 20 partition đồng loạt retry.

Nên đặt **một tầng chịu trách nhiệm chính** cho retry của thao tác external, các tầng còn lại biết cách propagate, fail hoặc defer. Khi có retry lồng, phải kiểm thử **số requests thực tế** chứ không chỉ kiểm tra `retryLimit` trên code.

### Backoff, jitter và timeout

- Mỗi network call phải có **connect/read/overall deadline** phù hợp.
- Backoff giúp giảm áp lực; jitter giúp các worker không gọi lại cùng lúc.
- Giới hạn tổng thời gian và số attempts của mỗi operation; lưu `attempt_count` bền vững nếu policy cần áp dụng xuyên worker/restart.
- Có circuit breaker/rate limiter hoặc quota ở **phạm vi toàn cụm** nếu downstream yêu cầu, không chỉ biến `AtomicInteger` trong một JVM.
- Khi hết budget, chuyển `UNKNOWN` / `FAILED_FINAL` / manual review theo hợp đồng, không tạo operation key mới để “thử thêm”.

## 12. Retry, rollback và restart trong Spring Batch

Một `StepExecution` có thể rollback chunk do lỗi DB và framework có thể gọi lại reader, processor hoặc writer. Trường hợp worker fail, operator có thể restart **cùng `JobInstance`** để đọc từ checkpoint hợp lệ.

~~~mermaid
sequenceDiagram
    participant S as StepExecution #1
    participant B as Business intent DB
    participant O as JobOperator
    participant N as StepExecution #2
    S->>B: Insert intent OP-42
    B-->>S: COMMIT
    Note over S: Lỗi trước khi checkpoint/reply chắc chắn
    O->>N: Restart cùng JobInstance
    N->>B: Replay intent OP-42, cùng key
    B-->>N: Duplicate same payload -> no-op
    Note over N: Không reset trạng thái operation
~~~

**Phân biệt hai lớp bảo vệ:**

- `ExecutionContext` / checkpoint trả lời câu hỏi **“reader bắt đầu tiếp ở đâu?”**.
- Business key và durable intent/ledger trả lời câu hỏi **“nếu cùng operation được đọc lại, side effect có bị nhân đôi không?”**.

Checkpoint không đảm bảo input bất biến. Nếu sort key, phân vùng hoặc snapshot thay đổi khi restart, replay có thể gồm item khác; thiết kế phải lưu `sourceVersion` và key → input range ổn định.

### @StepScope không thay thế idempotency

`@StepScope` giúp reader/processor có state riêng theo `StepExecution`. Nhưng:

- Hai partition vẫn có thể overlap nếu `Partitioner` chia phạm vi sai.
- Hai worker từ hai JVM vẫn có thể gửi cùng operation.
- Một worker có thể gửi cùng request nhiều lần sau retry/restart.
- Multi-threaded chunk trong cùng `StepExecution` vẫn có thể chia sẻ reader stateful.

Các business effects vẫn cần unique key/transaction hoặc provider-side idempotency.

## 13. Local và remote: side effect phải chịu được duplicate ở đâu?

### Local partitioning

`TaskExecutorPartitionHandler` chạy nhiều worker trên cùng JVM. Nếu manager tăng `gridSize` và thread pool, cùng một shared singleton processor có mutable `currentOperationId` có thể gây **cross-talk**. Bean scope đúng giúp tránh trộn biến, nhưng không giải quyết duplicate do broker, restart hoặc SQL overlap.

### Remote partitioning

Một manager có thể giao worker step qua message. Sau timeout, worker cũ vẫn chạy nhưng manager kích hoạt worker mới. Hai tiến trình có thể cùng gửi một operation:

~~~text
Worker A: POST capture(OP-42) → timeout
Worker B: POST capture(OP-42) → được giao lại

Cả hai gửi CÙNG idempotency key
→ provider phải phân xử atomic để chỉ có một business effect.
~~~

`StepExecutionId` khác nhau **không** khiến hai capture hợp lệ trở thành hai operation riêng. Dùng business operation ID xuyên attempt, kết hợp claim/lease/fencing để hạn chế làm việc thừa.

### Remote chunking

Trong remote chunking, manager gửi chunk requests qua broker; worker xử lý/ghi rồi trả reply. Nếu worker commit rồi mất reply/ACK, request có thể được giao lại. Dedupe ở mức chunk request ID hữu ích nhưng **không đủ** nếu 120/200 external calls đã thành công trước crash. Cần idempotency **ở từng operation** hoặc mô hình xử lý ngoài transaction có thể hòa giải.

| Mô hình | Nguy cơ replay | Điểm bảo vệ |
| --- | --- | --- |
| Single-threaded chunk step | Rollback/restart | Business unique key / transactional writer |
| Multi-threaded chunk step | Retry và gọi đồng thời cùng StepExecution | Thread-safe reader/writer, DB uniqueness |
| Local partitioning | Worker overlap hoặc restart | Stable partition plan, business key |
| Remote partitioning | Worker cũ và mới cùng thực thi | Coordination/claim + idempotency tại đích |
| Remote chunking | Request redelivery, reply mất | Request correlation + per-item operation ID |
| Message-driven external worker | At-least-once broker delivery | Transactional inbox/outbox, ACK sau commit |

## 14. Sai lầm thường gặp

### 14.1. Tạo UUID trong mỗi lần gọi processor

~~~java
// Sai nếu đây là cùng một operation bị retry:
String operationId = UUID.randomUUID().toString();
gateway.capture(operationId, amount);
~~~

Sau rollback, `process(...)` có thể chạy lại và tạo ID mới. Hãy tạo operation ID **ở nguồn hoặc một durable intent trước attempt đầu**, rồi dùng lại trong mọi lần phát lại.

### 14.2. Lưu boolean `processed=true` trước khi thực hiện effect

~~~text
Đánh dấu processed=true -> COMMIT
                     |
                     +-- crash trước HTTP call
                     |
                     +-- retry thấy processed=true và bỏ qua
                     |
                     +-- business effect chưa bao giờ xảy ra
~~~

Đó là **false positive dedupe**. Cần trạng thái `PENDING/IN_FLIGHT/CONFIRMED/UNKNOWN` và transaction/reconciliation phù hợp.

### 14.3. Chỉ ghi ledger sau external API

~~~text
Gọi API thành công
   ↓
Worker crash trước khi ghi ledger
   ↓
Retry không thấy ledger → gọi API lại
~~~

Nếu provider không hỗ trợ idempotency, khó phân biệt effect đã xảy ra hay chưa. Durable intent **trước** khi gọi và idempotency key **ở phía nhận** là lớp bảo vệ quan trọng.

### 14.4. Dùng `ConcurrentHashMap` để chống trùng

Cache trong JVM bị mất khi pod restart và không chia sẻ giữa các worker remote. Nó có thể hỗ trợ tối ưu ngắn hạn nhưng **không** phải nguồn chân lý cho operation ledger.

### 14.5. ACK broker trước commit

Broker tin message đã xong, nhưng database rollback sau đó; công việc có thể **mất**, không phải bị lặp. Nếu ACK muộn sau commit, broker có thể giao lại; khi đó **idempotent consumer** phải chấp nhận redelivery.

### 14.6. Dùng `ON CONFLICT DO NOTHING` cho mọi tình huống

Một row có cùng key nhưng payload khác là conflict có thể nghiêm trọng. Không được im lặng bỏ qua và gọi job thành công. Cần so sánh các trường bất biến và cảnh báo.

## 15. Kiểm thử không side effect kép

### 15.1. Unit test: key được giữ nguyên qua retry

Một test thuần Java có thể xác nhận mapping từ `PaymentInput` sang `PaymentCommand` không phụ thuộc thời gian, thread hoặc `JobExecutionId`:

~~~java
@Test
void sameInputProducesSameOperationIdentity() throws Exception {
    PaymentInput input = new PaymentInput(
            "row-001", "PAY-42", "tenant-A",
            250000L, "VND", "snapshot-v1");

    PaymentCommandProcessor processor =
            new PaymentCommandProcessor();

    PaymentCommand first = processor.process(input);
    PaymentCommand replay = processor.process(input);

    assertEquals(first.operationId(), replay.operationId());
    assertEquals(first.payloadHash(), replay.payloadHash());
    assertEquals("CAPTURE:PAY-42", first.operationId());
}
~~~

Test giả định `PayloadFingerprint.sha256(...)` được triển khai đúng trong dự án. Đây chỉ là test **tính ổn định của command**, chưa chứng minh provider xử lý idempotent.

### 15.2. Integration test: intent writer chạy lại sau commit

~~~java
@Test
void replayIntentKhongMoLaiConfirmedOperation() {
    PaymentCommand command = new PaymentCommand(
            "row-001", "snapshot-v1",
            "tenant-A", "CAPTURE:PAY-42",
            250000L, "VND", "hash-v1");

    Chunk<PaymentCommand> chunk = new Chunk<>(List.of(command));

    transactionTemplate.executeWithoutResult(
            status -> intentWriter.write(chunk));

    // Giả lập dispatcher đã được provider xác nhận.
    jdbc.update(
            "UPDATE operation_intent SET status='CONFIRMED' "
            + "WHERE tenant_id=? AND operation_id=?",
            "tenant-A", "CAPTURE:PAY-42");

    transactionTemplate.executeWithoutResult(
            status -> intentWriter.write(chunk)); // Replay cùng input.

    String state = jdbc.queryForObject(
            "SELECT status FROM operation_intent "
            + "WHERE tenant_id=? AND operation_id=?",
            String.class, "tenant-A", "CAPTURE:PAY-42");

    assertEquals("CONFIRMED", state); // Không reset về PENDING.
}
~~~

Đây là snippet cần Spring Test context, PostgreSQL schema, `JdbcTemplate`, `TransactionTemplate`, JUnit 5 và writer đã inject; không phải class độc lập. Test dùng **hai transaction commit riêng**. Nếu bọc cả test bằng một transaction rollback cuối cùng, có thể vô tình che lỗi crash window.

### 15.3. Test cùng key khác payload

~~~text
Ghi intent:
  operationId=CAPTURE:PAY-42
  amountMinor=250000
  currency=VND

Replay:
  operationId=CAPTURE:PAY-42
  amountMinor=350000

Kỳ vọng:
  - phát hiện conflict
  - không reset trạng thái cũ
  - không gửi request mới tới provider
  - có log/audit và hướng xử lý sự cố
~~~

### 15.4. Ma trận fault injection

| Kịch bản | Kết quả phải chứng minh |
| --- | --- |
| Lần gửi đầu thành công | Operation `CONFIRMED`, một effect tại provider |
| Timeout **trước khi gửi** | Retry cùng key, không tạo operation mới |
| Timeout **sau khi provider commit** | Reconciliation hoặc same-key retry trả cùng effect |
| Crash sau khi tạo intent, trước khi gửi | Dispatcher tìm lại `PENDING`, không bỏ quên |
| Crash sau khi gửi, trước cập nhật status | `UNKNOWN`/lease recovery, không nhân effect |
| Crash sau cập nhật `CONFIRMED`, trước ACK | Replay no-op; không gửi lại với key mới |
| Hai worker claim cùng intent | DB claim/fencing đúng, provider vẫn chỉ một effect |
| Worker cũ tiếp tục sau lease expiry | Stale owner không overwrite status mới; provider dedupe |
| Retry ba tầng cùng lúc | Tổng attempts có giới hạn đo được; không gây request storm |
| Lỗi nonretryable/permanent | Không retry vô hạn, trạng thái có reason |
| Cùng key khác amount/currency | Conflict; không “first or last wins” âm thầm |
| `JobExecutionId` thay đổi khi restart | Business key không đổi, replay an toàn |
| Partition ranges overlap | Có thể cùng operation được xử lý hai lần nhưng effect duy nhất |
| Broker giao lại remote chunk | Request correlation đúng, per-item side effects không trùng |
| Provider không có idempotency | Test chỉ ra trạng thái unknown; runbook yêu cầu reconcile |
| Outbox publish lại | Downstream dedupe event ID ổn định |
| Retention idempotency hết trước replay | Hàng rào business ledger dài hạn vẫn bảo vệ effect |

### 15.5. Kiểm thử concurrency bằng database thật

Hai thread/JVM cùng gọi `applyOnce` hoặc ghi `PaymentIntentWriter` với **cùng operation ID**:

1. Sử dụng hai connection/transaction độc lập.
2. Kích hoạt gần đồng thời bằng latch/barrier có timeout.
3. Kiểm tra unique constraint phân xử atomic.
4. Nếu một transaction rollback, transaction còn lại phải có khả năng thực thi đúng.
5. Sau khi hai attempts hoàn tất, chỉ có **một business operation** được ghi; các duplicate hợp lệ không làm tăng effect.
6. Kiểm tra khác payload tạo conflict thay vì bỏ qua.

Test bằng `HashMap` giả lập hoặc một `synchronized` singleton **không chứng minh** an toàn nhiều JVM. Ưu tiên Testcontainers với cùng loại database như production cho bài test transaction/unique key.

## 16. Đo lường và giám sát vận hành

Nếu chỉ nhìn `BatchStatus.COMPLETED` hoặc `StepExecution.writeCount`, bạn có thể bỏ sót các operation `UNKNOWN`/`PENDING` chưa thực hiện.

| Metric / chỉ số | Ý nghĩa |
| --- | --- |
| `operation_intents_created_total` | Số intent mới được commit |
| `operation_duplicate_noop_total` | Số replay hợp lệ, không tạo effect mới |
| `operation_payload_conflict_total` | Số key cũ xuất hiện với payload khác |
| `gateway_attempts_total` | Số lần client thực sự gọi provider |
| `gateway_timeout_total` | Kết quả chưa chắc chắn do timeout |
| `operation_unknown_count` | Backlog cần reconcile |
| `operation_pending_age_seconds` | Tuổi công việc chưa hoàn tất |
| `operation_confirmed_total` | Số operation đã xác nhận bền vững |
| `operation_recovery_attempt_total` | Lần dispatcher/reconciler thử xử lý |
| `batch_rollback_count` / `commit_count` | Số rollback/commit của Batch step |
| `reconciliation_mismatch_total` | Mâu thuẫn giữa intent, provider và business output |

**Phân biệt attempts với unique operations.** Một operation có thể được gọi năm lần, nhưng chỉ tạo một effect. `writeCount` của Spring Batch không nhất thiết bằng số row insert mới khi writer no-op trên duplicate.

### Phát hiện bottleneck khi tăng concurrency

- Nhiều partition gọi cùng provider làm tăng 429/503 và timeout.
- Unique index trên operation table có thể tăng lock contention khi nhiều workers xử lý cùng key.
- Pool kết nối, HTTP client pool, dispatcher leases và `JobRepository` đều cần đo.
- Thay vì tăng `gridSize` vô hạn, đặt backpressure/rate limit theo tài nguyên **thực tế**.
- Đừng gắn mỗi `operationId` thành một nhãn Prometheus lâu dài: cardinality lớn; dùng audit/log/tracing cho việc tra cứu từng operation.

## 17. Runbook khi nghi ngờ side effect kép

1. **Ghi nhận identity:** `tenantId`, operation ID, source version, input record, JobInstance, partition key và attempt.
2. **Kiểm tra phía đích:** API/provider/ledger có bao nhiêu effects thật theo operation ID, provider reference nào?
3. **Đọc durable intent:** `PENDING`, `IN_FLIGHT`, `UNKNOWN`, `CONFIRMED` hay `FAILED_FINAL`? Có owner/lease còn sống không?
4. **Xác minh retry path:** Có request mới dùng idempotency key khác sau timeout không? Có retry lồng từ HTTP client, Spring Retry và Batch không?
5. **Kiểm tra transaction:** Intent có commit trước khi gửi? Có side effect ngoài transaction bị bỏ qua không?
6. **Kiểm tra identity conflict:** Cùng operation ID có payload khác giữa các attempt/snapshot không?
7. **Khoanh vùng worker:** Có hai worker remote cùng xử lý partition, hoặc chunk request bị broker redelivery không?
8. **Tạm ngừng gửi nếu không rõ:** Với thanh toán/ledger quan trọng, không tạo capture mới khi chưa biết outcome trước.
9. **Reconcile rồi khôi phục:** Tra provider theo same key; cập nhật trạng thái bền vững hoặc xử lý bù có operation ID riêng.
10. **Bổ sung kiểm thử:** Đưa crash window thực tế, timeout sau commit và concurrency vào suite để ngăn lặp sự cố.

### Quyết định khi nào restart job

Spring Batch restart **không** đồng nghĩa tất cả tác dụng nghiệp vụ chưa hoàn tất sẽ tự được khôi phục đúng. Có thể job đã `COMPLETED` sau khi ghi intent nhưng dispatcher còn hàng nghìn `PENDING`. Cần **runbook riêng cho dispatcher/reconciliation**; nếu thiết kế yêu cầu job chỉ thành công khi các effect được xác nhận, cần thêm bước kiểm tra/publish gate có ngữ nghĩa rõ.

Ngược lại, nếu worker Batch `FAILED` nhưng nhiều intents đã commit, restart có thể replay input; writer phải nhận ra same-key intent và **không reset trạng thái**.

## 18. Bài tập tình huống

Một job Spring Batch xử lý 4 triệu giao dịch bằng 10 partition. Mỗi worker dùng `chunk(200)`, đọc database A và gọi API thanh toán B trong `ItemProcessor`. Mỗi lần processor chạy, mã tạo `UUID.randomUUID()` làm idempotency key. Khi provider timeout, Spring Retry thử ba lần; HTTP client còn tự retry hai lần. Sau đó worker `FAILED` và job được restart. Một số giao dịch bị capture nhiều lần dù bảng `BATCH_STEP_EXECUTION` chỉ báo một lần restart.

**Câu hỏi:**

1. Vì sao UUID mới theo mỗi attempt không chống được double charge?
2. Retry lồng hai tầng gây rủi ro gì với một provider đang quá tải?
3. Tại sao checkpoint `ExecutionContext` không thể rollback một giao dịch đã commit ở provider B?
4. Thay processor side effect bằng thiết kế nào để batch restart an toàn?
5. Sau HTTP timeout, nên ghi `FAILED_FINAL` hay `UNKNOWN`? Cần bằng chứng gì để kết luận?
6. Nếu worker A và B cùng claim payment `PAY-42`, cần những rào chắn nào?
7. Những test nào chứng minh khách hàng không bị trừ tiền hai lần?

**Định hướng trả lời:** Operation key phải được tạo ổn định theo payment/capture identity trước attempt đầu và giữ nguyên qua retry/restart; key mới khiến provider coi mỗi request là một thao tác khác. Retry lồng có thể khuếch đại request. Transaction của Batch không bao trùm side effect HTTP bên ngoài. Nên ghi **durable intent** trong writer cùng chunk transaction, dispatcher gửi same-key request, provider lưu kết quả theo key, reconciler xử lý trạng thái `UNKNOWN`. DB claim/lease giúp giảm cạnh tranh, nhưng **provider-side idempotency** mới bảo vệ external effect khi hai requests đồng thời. Test timeout sau provider commit, crash trước/sau cập nhật trạng thái, concurrent workers, key conflict và reconciliation.

## Tài liệu tham khảo

- [Spring Batch Reference — Chunk-Oriented Processing](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing.html): ranh giới read/process/write/commit.
- [Spring Batch Reference — Configuring Retry Logic](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/retry-logic.html): retry policy của fault-tolerant step.
- [Spring Batch Reference — Configuring a Step for Restart](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/restart.html): checkpoint, `ItemStream` và restart.
- [Spring Batch Reference — Scaling and Parallel Processing](https://docs.spring.io/spring-batch/reference/scalability.html): multi-threaded step, parallel steps và partitioning.
- [Spring Batch Reference — Remote Chunking](https://docs.spring.io/spring-batch/reference/spring-batch-integration/remote-chunking.html): chunk request/reply qua message.
- [Spring Batch Reference — Remote Partitioning](https://docs.spring.io/spring-batch/reference/spring-batch-integration/remote-partitioning.html): worker step phân tán.
- [Spring Framework Reference — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html): transaction boundaries và `@Transactional`.
- [PostgreSQL Documentation — INSERT and ON CONFLICT](https://www.postgresql.org/docs/current/sql-insert.html): atomic insert, unique constraint và conflict handling.

> **Ghi nhớ:** **Retry operation an toàn không có nghĩa request chỉ được gửi một lần.** Nghĩa là các lần gửi lại **không tạo thêm tác dụng nghiệp vụ ngoài operation đã định nghĩa**. Hãy dùng **business operation ID bền vững, payload validation, transaction/unique constraint ở nơi phù hợp, durable intent, idempotency tại provider và reconciliation cho timeout**. Với Spring Batch chạy song song hoặc phân tán, luôn kiểm thử crash windows, restart và hai worker cùng operation.
