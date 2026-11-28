# Tính lặp lại an toàn và khôi phục sau lỗi cập nhật một phần

Một command có thể cập nhật nhiều bản ghi hoặc gọi nhiều dịch vụ trong cùng một nghiệp vụ. Nếu tiến trình dừng giữa chừng, người vận hành cần biết bước nào đã hoàn tất, bước nào chưa chạy và bước nào có kết quả chưa xác định. Chạy lại toàn bộ command mà không có cơ chế chống trùng có thể tạo bản ghi trùng, gửi thông báo nhiều lần hoặc áp dụng thay đổi hai lần.

Thiết kế an toàn cần kết hợp ba khả năng: nhận diện cùng một yêu cầu qua idempotency key, lưu trạng thái thực thi đủ bền để tiếp tục sau lỗi, và khôi phục phần đã hoàn tất bằng hành động bù khi nghiệp vụ yêu cầu. Các cơ chế này phải được bảo vệ bằng kiểm soát truy cập, giới hạn phạm vi tenant và audit trail để một lần retry hoặc resume không trở thành cách thực hiện lại thao tác ngoài quyền hạn.

## Phân biệt retry, idempotency, rollback và compensation

Các khái niệm thường xuất hiện cùng nhau nhưng có trách nhiệm khác nhau:

| Khái niệm | Câu hỏi được giải quyết | Cơ chế |
|---|---|---|
| Retry | Khi nào nên thử lại sau lỗi? | Phân loại lỗi, timeout, backoff, giới hạn lần thử |
| Idempotency | Nếu cùng yêu cầu được gửi nhiều lần thì có tạo thêm tác động không? | Request ID ổn định, deduplication, lưu kết quả và ràng buộc duy nhất |
| Rollback | Làm sao hủy mọi thay đổi trong một transaction cục bộ? | Transaction manager và rollback rule |
| Compensation | Làm sao xử lý tác động đã commit ở nhiều bước/hệ thống? | Hành động nghiệp vụ bù, saga hoặc workflow phục hồi |
| Reconciliation | Khi không biết request trước đã thành công hay chưa thì xác định trạng thái thế nào? | Tra cứu trạng thái thực tế và đối chiếu với operation ledger |

Retry không tự làm một thao tác an toàn. Một request có thể đã được server xử lý nhưng phản hồi bị mất. Idempotency cho phép gửi lại cùng ý định mà không tạo side effect mới. Rollback chỉ bao phủ các thay đổi tham gia cùng transaction. Compensation là thao tác nghiệp vụ mới nhằm xử lý tác động đã commit; nó cũng có thể thất bại và cần được retry.

## Cửa sổ lỗi khi cập nhật nhiều bước

Giả sử command `release-apply` thực hiện ba bước:

1. Tạo cấu hình release trong database.
2. Gọi deployment service để cập nhật môi trường.
3. Gửi sự kiện thông báo release đã triển khai.

Nếu bước 2 thành công nhưng phản hồi timeout, command không thể kết luận deployment thất bại. Nếu người vận hành chạy lại với một request ID mới, dịch vụ có thể tạo một deployment thứ hai. Nếu bước 2 đã thành công nhưng tiến trình chết trước khi lưu checkpoint, operation ledger cũng có thể cho thấy bước này chưa hoàn tất.

```text
CLI gửi yêu cầu
      |
      v
Ghi operation ID và request key
      |
      v
Step 1: cập nhật database --------> SUCCEEDED
      |
      v
Step 2: gọi deployment service ---> timeout / chưa rõ kết quả
      |
      v
Process dừng
      |
      v
Resume cùng operation ID
      |
      +--> tra cứu trạng thái/key ở deployment service
      |       |
      |       +--> đã triển khai: ghi nhận SUCCEEDED
      |       +--> chưa xử lý: gửi lại cùng idempotency key
      |       +--> trạng thái không rõ: dừng và yêu cầu đối soát
      |
      v
Step 3: chỉ gửi event sau khi Step 2 được xác nhận
```

Điểm quan trọng là trạng thái của một bước không thể chỉ dựa trên việc client nhận được phản hồi. Khi mất phản hồi, phải giữ trạng thái `UNKNOWN` hoặc `RECONCILIATION_REQUIRED` cho đến khi kiểm tra được hệ thống đích.

## Thiết kế idempotency key ổn định

Một idempotency key nhận diện một ý định nghiệp vụ cụ thể. Cùng một ý định phải dùng cùng key trong mọi lần retry; một ý định mới phải có key mới, kể cả khi payload trông giống hệt.

Ví dụ command triển khai:

```text
release-apply \
  --environment staging \
  --version 2.7.1 \
  --request-id 9e25f97a-3b28-4ef2-9f4c-2c31d94e9c11
```

Nếu lệnh timeout, chạy lại với đúng `--request-id` đó. Khi người dùng chủ động tạo một release khác, hãy tạo key mới.

Không suy ra rằng hai request giống payload luôn là cùng ý định. Ví dụ, hai lần tạo hai bản sao cùng cấu hình có thể là hai yêu cầu hợp lệ. AWS Builders' Library khuyến nghị caller cung cấp request ID để thể hiện rõ ý định; cách này tránh việc server tự coi hai request giống nhau là một. <Link url="https://aws.amazon.com/builders-library/making-retries-safe-with-idempotent-APIs/" title="Making retries safe with idempotent APIs"/>.

### Phạm vi key và quyền sở hữu

Không dùng key đơn lẻ làm khóa toàn cục. Phạm vi nên bao gồm caller/tenant và loại operation, ví dụ:

```text
(tenant_id, operation_name, idempotency_key)
```

Điều này ngăn hai tenant vô tình hoặc cố ý dùng cùng chuỗi key để đọc lại kết quả của nhau. Khi nhận request, service phải xác thực danh tính caller và kiểm tra caller có quyền thực hiện operation trong tenant đó. Idempotency key không phải password, bearer token hoặc bằng chứng authorization.

Key nên có entropy đủ lớn, không chứa email, username, account number, access token hoặc dữ liệu cá nhân. Tránh timestamp làm key vì đồng hồ lệch và nhiều client có thể tạo cùng giá trị. UUID ngẫu nhiên hoặc ID do caller tạo theo một chuẩn thống nhất thường phù hợp hơn.

### Cùng key nhưng payload khác

Lưu fingerprint của request đã chuẩn hóa cùng key. Nếu key đã tồn tại:

- Cùng fingerprint: trả trạng thái/kết quả đã lưu hoặc hướng dẫn kiểm tra operation đang chạy.
- Khác fingerprint: trả lỗi conflict/validation; không thực hiện request mới bằng key cũ.
- Đang xử lý: trả operation ID và trạng thái `IN_PROGRESS`; không khởi chạy bản thực thi thứ hai.

Fingerprint nên được tính từ các trường nghiệp vụ có ảnh hưởng đến kết quả, theo dạng canonical để thứ tự field hoặc cách serialize không làm thay đổi hash. Không lưu toàn bộ payload nếu chỉ cần hash và metadata. Không đưa secret vào fingerprint log hoặc lưu raw request có chứa credential.

AWS mô tả việc từ chối cùng request ID nhưng khác tham số như một validation error; giữ nguyên key nhưng đổi ý định sẽ làm kết quả retry khó dự đoán. <Link url="https://aws.amazon.com/builders-library/making-retries-safe-with-idempotent-APIs/" title="AWS Builders' Library"/>.

## Lưu idempotency record cùng thay đổi dữ liệu

Với thay đổi nằm trong một database, ghi nhận idempotency key, mutation và kết quả trong cùng transaction. Nếu key được ghi trước nhưng mutation thất bại, request sau có thể bị coi nhầm là đã hoàn tất. Nếu mutation thành công nhưng key không được ghi, retry có thể áp dụng thay đổi lần nữa.

Một bảng tối thiểu có thể gồm:

```sql
CREATE TABLE idempotency_record (
    tenant_id          VARCHAR(80)  NOT NULL,
    operation_name     VARCHAR(100) NOT NULL,
    idempotency_key    VARCHAR(100) NOT NULL,
    request_fingerprint VARCHAR(128) NOT NULL,
    operation_id       VARCHAR(80)  NOT NULL,
    status             VARCHAR(32)  NOT NULL,
    result_reference   VARCHAR(160),
    created_at         TIMESTAMP    NOT NULL,
    updated_at         TIMESTAMP    NOT NULL,
    expires_at         TIMESTAMP,
    PRIMARY KEY (tenant_id, operation_name, idempotency_key),
    UNIQUE (operation_id)
);
```

Đây là schema minh họa; kiểu dữ liệu và cú pháp timestamp cần điều chỉnh theo database. Không lưu password, access token, private key hoặc toàn bộ request nhạy cảm trong record. Lưu result reference hoặc kết quả đã được lọc để caller nhận lại cùng ý nghĩa khi retry.

Một luồng xử lý đơn giản:

1. Xác thực caller và quyền trên tenant/resource.
2. Chuẩn hóa request và tính fingerprint.
3. Tạo operation ID và thử insert idempotency record với unique key.
4. Nếu insert xung đột, đọc record hiện có và so sánh fingerprint.
5. Nếu key mới, thực hiện mutation và cập nhật status/result trong cùng transaction.
6. Commit trước khi trả kết quả thành công.

Unique constraint là hàng rào cuối cùng chống hai process đồng thời cùng nhận một key. Chỉ làm `SELECT` trước rồi `INSERT` mà không có unique constraint/transaction phù hợp vẫn có race condition.

Transaction trên phù hợp với thao tác ngắn nằm trong cùng database. Không giữ một transaction database mở trong lúc chờ nhiều API từ xa. Với workflow dài, transaction đầu tiên nên ghi operation/idempotency record và outbox event rồi commit; mỗi bước tiếp theo cập nhật ledger trong transaction cục bộ của nó và dùng idempotency key riêng khi gọi downstream. Cách này cho phép worker khác tiếp tục sau khi process ban đầu dừng.

AWS Well-Architected khuyến nghị lưu trạng thái key, dùng transaction/lock/optimistic concurrency để kết hợp key với mutation, đặt TTL và chỉ lưu lượng state cần thiết thay vì toàn bộ payload. <Link url="https://docs.aws.amazon.com/wellarchitected/latest/framework/rel04-bp04.html" title="Make mutating operations idempotent"/>.

## Khi operation đi qua nhiều dịch vụ

Một transaction database không thể tự rollback một API call đã thành công ở dịch vụ khác, email đã gửi hoặc event đã được consumer xử lý. Với workflow nhiều hệ thống, lưu operation ledger và trạng thái từng bước.

Ví dụ các trạng thái của operation:

| Trạng thái | Ý nghĩa |
|---|---|
| `ACCEPTED` | Request hợp lệ và đã được ghi nhận |
| `RUNNING` | Đang thực hiện các bước |
| `PARTIAL` | Một số bước đã hoàn tất, một số bước thất bại/chưa rõ |
| `RETRY_WAIT` | Có bước gặp lỗi tạm thời và chờ retry |
| `COMPENSATING` | Đang thực hiện hành động bù |
| `COMPENSATED` | Các hành động bù đã hoàn tất theo chính sách |
| `SUCCEEDED` | Tất cả bước bắt buộc đã được xác nhận thành công |
| `FAILED` | Thất bại cuối cùng, không còn retry tự động |
| `RECONCILIATION_REQUIRED` | Trạng thái hệ thống đích chưa xác định |
| `MANUAL_REVIEW` | Cần người có thẩm quyền quyết định bước tiếp theo |

Mỗi bước nên có record riêng với `step_id`, `attempt`, `status`, `started_at`, `completed_at`, `downstream_request_id`, `result_reference` và thông tin compensation. Lưu dữ liệu tối thiểu để tiếp tục hoặc đối soát; không đưa credential hay payload nhạy cảm vào operation ledger.

### State machine của từng bước

```text
PENDING
   |
   v
RUNNING ----> SUCCEEDED
   |
   +--------> RETRY_WAIT ----> RUNNING
   |
   +--------> UNKNOWN -------> RECONCILIATION_REQUIRED
   |
   +--------> FAILED
                   |
                   v
              COMPENSATING
                   |
          +--------+--------+
          v                 v
     COMPENSATED       MANUAL_REVIEW
```

Chỉ đánh dấu `SUCCEEDED` sau khi có bằng chứng phù hợp từ hệ thống đích. Nếu timeout, đừng tự đổi thành `FAILED` rồi tạo key mới. Tra cứu bằng downstream request ID/idempotency key hoặc query resource state trước khi quyết định retry.

## Bảo đảm lưu trạng thái và phát lệnh tiếp theo

Một lỗi thường gặp là commit thay đổi database rồi gửi event; process có thể chết giữa hai hành động, làm dữ liệu đã đổi nhưng event không được gửi. Chiều ngược lại, event được gửi trước khi transaction commit có thể khiến consumer nhìn thấy trạng thái chưa tồn tại.

Với hệ thống dùng message broker, cân nhắc Transactional Outbox:

1. Trong cùng transaction, cập nhật dữ liệu nghiệp vụ và ghi một outbox event.
2. Một publisher đọc outbox và gửi event tới broker.
3. Sau khi gửi thành công, đánh dấu event đã publish.
4. Consumer xử lý event theo idempotency key/message ID vì broker có thể giao lại.

Outbox giảm cửa sổ mất event giữa commit và publish. Nó không tự bảo đảm consumer xử lý đúng một lần; consumer vẫn phải chống duplicate delivery. Mỗi bước downstream cần truyền operation ID hoặc request ID tương ứng để có thể truy vết xuyên suốt.

## Retry có giới hạn và giữ nguyên ý định

Chỉ retry lỗi có khả năng tạm thời, ví dụ timeout kết nối, rate limit hoặc dịch vụ tạm thời unavailable theo hợp đồng của API. Không retry liên tục các lỗi validation, authorization, conflict hoặc lỗi nghiệp vụ không thể tự hết.

| Loại lỗi | Cách xử lý |
|---|---|
| Timeout/mất phản hồi | Query trạng thái theo cùng key; nếu chưa xử lý thì retry cùng key |
| HTTP 429/503 hoặc lỗi mạng tạm thời | Retry có giới hạn, backoff và jitter theo retry policy của dịch vụ |
| Validation/parameter mismatch | Dừng; sửa request hoặc tạo operation mới với key mới nếu đó là ý định mới |
| Authorization denied | Dừng; xử lý quyền. Không tự retry bằng principal khác |
| Conflict/version mismatch | Đọc lại trạng thái, reconcile và tạo quyết định nghiệp vụ mới |
| Không rõ side effect đã xảy ra | Đánh dấu `UNKNOWN`, truy vấn hệ thống đích hoặc chuyển đối soát |

Retry policy cần có số lần tối đa, deadline tổng, timeout cho từng lần và backoff tăng dần kèm jitter. Không để nhiều tầng retry nhân số lần gọi lên nhau. Khi retry, giữ nguyên key, operation ID và fingerprint. Chỉ tạo key mới khi caller chủ động tạo một ý định nghiệp vụ mới.

## Khôi phục sau cập nhật một phần

Khi operation ở trạng thái `PARTIAL`, không chạy lại mọi bước một cách mù quáng. Đọc ledger, kiểm tra trạng thái thực tế và chọn một trong các cách:

- **Resume:** tiếp tục các bước `PENDING`/`RETRY_WAIT` sau khi xác nhận các bước trước đã hoàn tất.
- **Retry một bước:** gửi lại đúng downstream request với cùng idempotency key.
- **Reconcile:** query resource/service đích để xác định trạng thái của bước `UNKNOWN`.
- **Compensate:** thực hiện hành động bù cho các bước đã commit nếu nghiệp vụ yêu cầu hủy toàn bộ.
- **Manual review:** tạm dừng khi hành động bù có rủi ro cao hoặc trạng thái không thể xác định tự động.

Một CLI có thể cung cấp các command vận hành:

```text
operation-status --operation-id op-7d1a...
operation-resume --operation-id op-7d1a...
operation-reconcile --operation-id op-7d1a...
operation-compensate --operation-id op-7d1a... --reason "release cancelled"
```

Đây là cú pháp minh họa. Command resume/compensate phải kiểm tra authorization riêng, ghi audit actor/reason và xác nhận operation thuộc tenant mà caller được phép truy cập. Không coi việc biết operation ID là quyền được xem hoặc thay đổi operation.

## Compensation không phải rollback

Rollback database trả transaction cục bộ về trạng thái trước commit. Compensation là hành động nghiệp vụ mới sau khi một hoặc nhiều bước đã commit. Nó không nhất thiết khôi phục byte-for-byte trạng thái cũ vì các actor khác có thể đã thay đổi dữ liệu trong lúc workflow chạy.

Ví dụ workflow cấp tài nguyên:

| Bước đã thực hiện | Hành động bù có thể có |
|---|---|
| Tạo reservation | Hủy reservation nếu vẫn thuộc operation này |
| Cấp quyền tạm | Thu hồi đúng grant do operation tạo |
| Tạo deployment | Roll back deployment về phiên bản trước nếu policy cho phép |
| Gửi thông báo | Không thể thu hồi email đã gửi; gửi thông báo đính chính nếu nghiệp vụ yêu cầu |
| Thu tiền | Tạo giao dịch refund theo policy, không xóa lịch sử payment |

Lưu trước thông tin cần thiết cho compensation: resource ID được tạo, version trước/sau, owner, downstream request ID và hành động bù hợp lệ. Hành động bù phải có idempotency key riêng nhưng liên kết với operation gốc. Nếu compensation chạy lại, không được thu hồi quyền của người khác hoặc refund hai lần.

Microsoft mô tả compensating transaction là workflow riêng có thể thất bại; cần lưu tiến độ để resume, làm cho từng bước bù idempotent, giữ correlation/audit và xác định điểm không thể đảo ngược. <Link url="https://learn.microsoft.com/en-us/azure/architecture/patterns/compensating-transaction" title="Compensating Transaction pattern"/>.

### Xác định điểm không thể đảo ngược

Một số hành động không thể bù hoàn toàn, chẳng hạn email đã gửi, dữ liệu đã được tải xuống, thông tin đã công bố hoặc giao dịch pháp lý đã hoàn tất. Đặt các hành động không thể đảo ngược sau các bước validation và precondition quan trọng nhất. Nếu nghiệp vụ cần human approval, hãy dừng ở trạng thái chờ duyệt trước khi qua điểm không thể quay lại.

Không tự động compensate một workflow có hậu quả tài chính/pháp lý lớn khi trạng thái chưa rõ. Chuyển `MANUAL_REVIEW`, hiển thị bằng chứng và yêu cầu người có thẩm quyền quyết định.

## Kiểm soát cạnh tranh và replay trái phép

Hai process có thể cùng nhận một request ID gần như đồng thời. Bảo vệ ở server bằng unique constraint, transaction hoặc optimistic locking; không dựa vào việc CLI chỉ chạy một instance.

Với operation đang chạy:

- Chỉ một worker được claim bước tại một thời điểm; dùng lease có thời hạn hoặc optimistic version.
- Worker cũ không được ghi đè kết quả worker mới sau khi lease hết hạn; kiểm tra fencing/version token.
- Mỗi downstream request có key ổn định riêng hoặc được suy ra bền vững từ operation ID + step ID.
- Khi cùng key và payload khác, từ chối thay vì dùng request mới để ghi đè operation cũ.
- Kiểm tra tenant, caller và quyền trên resource ở mọi lệnh status/resume/compensate.

Idempotency không thay thế authorization. Một caller đã mất quyền không được phép resume operation chỉ vì key đã tồn tại. Khi workflow chạy lâu, xác định rõ quyền được đánh giá tại thời điểm nhận request, tại từng bước hay cả hai; với hành động nhạy cảm, thường cần kiểm tra lại quyền trước khi thực hiện bước tiếp theo hoặc compensation.

## Audit và bảo vệ dữ liệu vận hành

Ghi log có cấu trúc theo operation ID, step ID, attempt number, state transition, duration, downstream status và actor ID. Dữ liệu này giúp điều tra và resume mà không cần ghi toàn bộ request.

Không log:

- Password, API token, private key hoặc Authorization header.
- Payload chứa dữ liệu cá nhân không cần thiết cho điều tra.
- Toàn bộ request/response của dịch vụ bên ngoài nếu có secret hoặc dữ liệu nhạy cảm.
- Nội dung file import/export có thể chứa thông tin khách hàng.

Idempotency key thường không phải credential, nhưng vẫn nên giới hạn quyền đọc log và tránh dùng key chứa PII. Nếu cần tra cứu, dùng operation ID hoặc key đã chuẩn hóa/ẩn một phần theo chính sách audit.

Record idempotency và operation ledger cũng cần retention policy. Giữ chúng ít nhất đủ lâu cho cửa sổ retry, thời gian xử lý workflow, compensation và late-arriving request. Xóa key quá sớm có thể làm request cũ được xử lý lại; giữ vô thời hạn có thể tăng chi phí và gây va chạm nếu key được tái sử dụng. Không tái sử dụng key trong cùng phạm vi ngay cả sau khi operation hoàn tất.

## Ví dụ tích hợp với Spring Shell 3.x

Command nhận request ID không bí mật và file cấu hình. Service sở hữu idempotency, transaction và operation ledger; command không tự quyết định một bước đã thành công chỉ dựa trên output.

```java
import java.nio.file.Path;

import org.springframework.shell.standard.ShellComponent;
import org.springframework.shell.standard.ShellMethod;
import org.springframework.shell.standard.ShellOption;

@ShellComponent
class ReleaseCommands {

    private final ReleaseOperationService operationService;

    ReleaseCommands(ReleaseOperationService operationService) {
        this.operationService = operationService;
    }

    @ShellMethod(key = "release-apply")
    public String apply(
            @ShellOption("request-id") String requestId,
            @ShellOption("environment") String environment,
            @ShellOption("version") String version,
            @ShellOption("config") Path config) {

        ReleaseRequest request = new ReleaseRequest(
                environment, version, config);
        OperationReport report = operationService.execute(requestId, request);

        return switch (report.status()) {
            case SUCCEEDED -> "Release hoàn tất: " + report.operationId();
            case RUNNING, RETRY_WAIT -> "Operation đang xử lý: " + report.operationId();
            case PARTIAL, RECONCILIATION_REQUIRED ->
                    "Operation cần đối soát: " + report.operationId();
            case MANUAL_REVIEW -> "Operation cần người có thẩm quyền xử lý: "
                    + report.operationId();
            case FAILED -> "Operation thất bại: " + report.operationId();
        };
    }
}
```

`ReleaseOperationService.execute()` phải xác thực caller, kiểm tra tenant, so sánh fingerprint, claim operation atomically và thực hiện các bước theo ledger. Ví dụ command trên chỉ minh họa adapter; cần bổ sung exit-code mapping để `PARTIAL`, `RECONCILIATION_REQUIRED` và `FAILED` trả status khác 0 theo hợp đồng CLI.

Vì `--config` nhận đường dẫn file, fingerprint phải bao gồm nội dung cấu hình đã chuẩn hóa hoặc checksum của nội dung tại thời điểm nhận request; chỉ băm chuỗi đường dẫn có thể khiến cùng key nhưng file đã đổi nội dung bị xem nhầm là cùng request. Lưu checksum và metadata cần thiết, không lưu secret trong file hoặc fingerprint log.

Không đặt password/token trong `ReleaseRequest` rồi log record. Nếu service cần secret để gọi downstream, lấy secret từ secret manager hoặc credential provider và chỉ sử dụng tại bước cần thiết.

## Kiểm thử tính lặp lại và phục hồi

Test cần mô phỏng cả lỗi trước, trong và sau side effect. Đặc biệt, kiểm tra trường hợp server đã xử lý nhưng client không nhận được response.

| Kịch bản | Điều cần xác nhận |
|---|---|
| Gửi lần đầu với key mới | Tạo một operation và mutation dự kiến |
| Gửi lại cùng key, cùng payload sau thành công | Trả cùng operation/result về mặt ngữ nghĩa; không tạo side effect mới |
| Gửi cùng key nhưng payload khác | Conflict/validation error; không chạy mutation |
| Hai request cùng key đồng thời | Chỉ một execution được claim; không tạo duplicate resource |
| Timeout sau khi downstream commit | Reconcile hoặc retry cùng downstream key; không tạo bản sao |
| Process chết sau mỗi bước | Resume từ ledger và không lặp bước đã xác nhận |
| Checkpoint mất sau side effect | Downstream idempotency/reconciliation xác định kết quả |
| Retry gặp validation/authorization error | Dừng, không retry vô hạn |
| Compensation bị timeout | Dùng cùng compensation key và kiểm tra trạng thái trước khi gửi lại |
| Compensation thất bại nhiều lần | Ghi `MANUAL_REVIEW`, cảnh báo và giữ đầy đủ audit |
| Caller khác tenant dùng operation ID | Bị từ chối, không lộ status/result |
| Caller mất quyền trước khi resume | Quyền được kiểm tra lại theo policy; không tiếp tục trái phép |
| Idempotency record hết TTL | Hành vi với late request tuân theo retention contract; không vô tình xử lý lại operation cũ |
| Payload/log chứa secret | Secret không xuất hiện trong log, report hoặc operation ledger |

Nên có integration test dùng database thật hoặc containerized database để xác minh unique constraint và transaction race. Unit test mock repository không thể chứng minh hai request đồng thời được chống trùng ở tầng lưu trữ.

## Lỗi thường gặp

| Biểu hiện | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Chạy lại command tạo thêm tài nguyên | Mỗi lần retry tạo request ID mới | Giữ cùng key cho cùng ý định |
| Cùng key nhưng request mới ghi đè dữ liệu cũ | Không lưu/so sánh request fingerprint | Trả conflict khi payload khác |
| Có idempotency record nhưng mutation không xảy ra | Ghi key và mutation ở hai transaction độc lập | Kết hợp trong transaction hoặc workflow state machine có phục hồi |
| Mutation đã xảy ra nhưng không có record | Side effect xảy ra trước khi lưu kết quả | Dùng transaction/outbox hoặc downstream idempotency và reconciliation |
| Hai process cùng xử lý một key | Chỉ SELECT trước khi insert, thiếu unique constraint/lock | Dùng unique constraint và atomic claim |
| Retry lặp lỗi vĩnh viễn | Không phân loại lỗi hoặc không có retry limit | Chỉ retry lỗi transient, đặt deadline/backoff/jitter |
| Resume bỏ qua bước đã lỗi | Dựa vào log text thay vì operation ledger | Lưu state machine và status theo từng step |
| Compensation hoàn tác nhầm thay đổi mới | Ghi đè trạng thái cũ mà không kiểm tra version/owner | Dùng version check, resource ownership và business-specific compensation |
| Compensation chạy hai lần | Hành động bù không idempotent | Cấp compensation key ổn định và lưu kết quả |
| Caller khác tenant đọc được operation | Không scope key/operation theo tenant và authorization | Kiểm tra tenant/caller ở mọi command |
| Log lộ payload hoặc token | Log toàn bộ request/exception | Chỉ log metadata allowlist và result reference |
| Xóa idempotency key quá sớm | TTL ngắn hơn retry/recovery window | Đặt retention theo vòng đời operation và late request |

## Quy trình triển khai an toàn

1. Phân loại thao tác: read-only, mutation cục bộ, mutation nhiều dịch vụ hay side effect không thể đảo ngược.
2. Xác định một request ID cho mỗi ý định; giữ key qua mọi lần retry.
3. Scope key theo tenant/caller và operation; không dùng key làm authorization token.
4. Chuẩn hóa request, lưu fingerprint và từ chối cùng key nhưng khác intent.
5. Dùng unique constraint/transaction/optimistic lock để chống cạnh tranh.
6. Kết hợp idempotency record với mutation trong cùng transaction khi có thể; dùng outbox cho bước publish.
7. Lưu operation ledger và trạng thái từng bước trước khi thực hiện workflow dài.
8. Phân loại transient/permanent/unknown; retry có giới hạn và giữ nguyên key.
9. Khi partial failure, query trạng thái đích rồi chọn resume, retry, reconcile, compensate hoặc manual review.
10. Thiết kế compensation idempotent, có audit và kiểm tra version/ownership.
11. Xác định điểm không thể đảo ngược và đặt chúng sau validation/approval.
12. Kiểm tra authorization ở mọi lệnh status/resume/compensate; không log secret hoặc payload nhạy cảm.
13. Đặt retention/TTL đủ cho retry, recovery và late-arriving request.
14. Kiểm thử duplicate, race, timeout-after-commit, process crash, compensation failure và cross-tenant access.

Khi một lần cập nhật bị gián đoạn, hệ thống phải có khả năng chứng minh bước nào đã xảy ra, bước nào chưa và bước nào cần quyết định thêm. Idempotency ngăn cùng ý định tạo tác động lặp; operation ledger giúp tiếp tục đúng chỗ; compensation xử lý các tác động đã commit theo quy tắc nghiệp vụ. Kết hợp cả ba với authorization và audit giúp khôi phục trạng thái an toàn mà không biến retry thành một đường vòng để vượt quyền.

## Tài liệu tham khảo

- [AWS Builders' Library — Making retries safe with idempotent APIs](https://aws.amazon.com/builders-library/making-retries-safe-with-idempotent-APIs/): caller-provided request ID, atomicity giữa key và side effect, xử lý cùng key nhưng khác intent, late-arriving request và retention.
- [AWS Well-Architected — REL04-BP04 Make mutating operations idempotent](https://docs.aws.amazon.com/wellarchitected/latest/framework/rel04-bp04.html): lưu idempotency state, transaction/concurrency control, TTL, propagation qua downstream và test duplicate requests.
- [Microsoft Azure Architecture Center — Compensating Transaction pattern](https://learn.microsoft.com/en-us/azure/architecture/patterns/compensating-transaction): operation ledger, compensation có thể thất bại, resume, idempotent compensation, audit và điểm không thể đảo ngược.
- [Microsoft Azure Architecture Center — Saga distributed transactions pattern](https://learn.microsoft.com/azure/architecture/reference-architectures/saga/saga): local transactions, compensable/pivot/retryable transactions và xử lý anomaly trong workflow nhiều dịch vụ.
