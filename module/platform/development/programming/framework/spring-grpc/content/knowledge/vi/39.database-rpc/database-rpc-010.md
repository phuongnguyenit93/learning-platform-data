# Side effect và retry

## 1. Vì sao retry có thể tạo side effect trùng?

Trong **SPRING_GRPC**, nhiều RPC không chỉ đọc dữ liệu mà còn tạo thay đổi có tác động bên ngoài: tạo đơn hàng, trừ tiền, ghi nhận thanh toán, gửi lệnh thiết bị, phát event hoặc gửi thông báo. Khi client không nhận được response, nó có thể retry dù server đã thực hiện side effect.

Một tình huống điển hình:

1. Client gửi command tạo đơn.
2. Server ghi đơn và commit database.
3. Kết nối bị ngắt trước khi response tới client.
4. Client thấy timeout hoặc UNAVAILABLE.
5. Client gửi lại command.
6. Nếu server xử lý lần hai như một ý định mới, hệ thống có thể tạo hai đơn.

Timeout chỉ cho biết caller không nhận được kết quả trong thời hạn; nó không chứng minh transaction đã rollback. Đây là **ambiguous outcome**. Vì vậy, retry và side effect phải được thiết kế cùng nhau.

Mục tiêu không phải hứa hẹn mạng truyền đúng một lần. Mục tiêu là bảo đảm nhiều attempt của cùng một ý định nghiệp vụ chỉ tạo một hiệu lực nghiệp vụ, thông qua idempotency, transaction, deduplication và recovery.

## 2. Phân biệt attempt, command và side effect

Ba khái niệm này cần được tách rõ:

- **Attempt:** một lần truyền RPC. Một command có thể có nhiều attempt do retry.
- **Command:** ý định nghiệp vụ ổn định của caller, ví dụ “tạo đơn hàng cho giỏ hàng này”.
- **Side effect:** thay đổi thực sự được tạo ra, như một order row, payment capture hoặc event phát ra.

Retry tạo attempt mới nhưng không được tự động tạo command mới. Client phải giữ một định danh ổn định cho command qua các lần gửi lại.

Một operation tự nhiên idempotent có thể lặp lại mà kết quả hiệu lực không đổi, ví dụ đặt trạng thái cấu hình thành một giá trị cụ thể. Operation như “tăng số dư”, “tạo đơn mới” hoặc “charge thẻ” thường không tự idempotent.

Với operation không idempotent, cần một idempotency key hoặc operation ID. Key phải đại diện cho một ý định nghiệp vụ, không phải cho một lần gọi mạng.

## 3. Các failure window quyết định retry an toàn

| Điểm lỗi | Trạng thái có thể có ở server | Điều client biết | Hướng xử lý |
| --- | --- | --- | --- |
| Trước khi server nhận request | Chưa có side effect | Không có response | Retry thường an toàn |
| Sau khi nhận nhưng trước business execution | Chưa có side effect nếu chưa bắt đầu | Có thể chỉ thấy timeout | Retry cùng command identity |
| Trong transaction, trước commit | Transaction có thể rollback | Client không biết chắc | Retry cùng key; server xác định kết quả |
| Sau commit, trước response | Side effect đã tồn tại | Client chỉ thấy timeout/UNAVAILABLE | Replay kết quả, không thực thi lại |
| Sau khi response tới client | Side effect đã hoàn tất | Client biết kết quả | Không retry trừ khi caller có ý định mới |

Điểm khó nhất là khoảng giữa commit và response. Database commit và gửi response qua HTTP/2 không phải một thao tác nguyên tử. Server không thể rollback một commit chỉ vì socket đã đóng.

Thiết kế idempotency phải bảo vệ cả trường hợp request đầu chưa commit lẫn trường hợp đã commit nhưng response bị mất.

## 4. Retry policy không thay thế idempotency

gRPC có cơ chế retry ở client khi method được cấu hình retry policy và status nằm trong retryable codes. Một số retry có thể được thực hiện minh bạch bởi runtime khi lời gọi chưa được xử lý hoặc chưa nhận response headers; retry policy cấu hình có thể tạo attempt mới theo số lần và backoff giới hạn.

Tuy nhiên, retry policy chỉ điều khiển việc gửi lại RPC. Nó không biết database đã commit hay payment provider đã charge hay chưa. Vì thế:

- Chỉ bật retry cho method có semantics retry được.
- Command có side effect cần idempotency ở server hoặc downstream.
- Không coi UNAVAILABLE là bằng chứng server chưa thực thi.
- Không retry vô hạn hoặc ở nhiều tầng mà không tính tổng attempt.
- Không dùng hedging cho side effect nếu chưa có deduplication an toàn.

Transport retry, application retry, proxy retry và queue redelivery có thể cộng dồn. Nếu mỗi tầng retry 3 lần, một command có thể tạo ra nhiều attempt hơn dự kiến. Xác định một nơi điều phối retry chính và ghi nhận attempt count/correlation.

## 5. Phân loại status trước khi retry

Không phải status nào cũng nên retry:

| gRPC status | Ý nghĩa đối với retry | Hành động thường phù hợp |
| --- | --- | --- |
| UNAVAILABLE | Có thể là lỗi tạm thời; outcome có thể chưa rõ | Retry cùng idempotency key với backoff |
| DEADLINE_EXCEEDED | Caller hết thời gian; server có thể đã commit | Query/retry cùng key, không tạo key mới |
| ABORTED | Conflict trong workflow, ví dụ optimistic locking | Đọc lại trạng thái và chạy lại toàn bộ use case |
| RESOURCE_EXHAUSTED | Quota hoặc quá tải tài nguyên | Chỉ retry khi contract cho biết có thể phục hồi; tôn trọng RetryInfo/backoff |
| FAILED_PRECONDITION | Trạng thái hiện tại không cho phép thao tác | Chờ/sửa precondition; không retry mù |
| INVALID_ARGUMENT | Request sai | Sửa input trước khi gửi lại |
| NOT_FOUND | Resource không tồn tại | Không retry như lỗi mạng |
| PERMISSION_DENIED | Không có quyền | Không retry cho tới khi quyền thay đổi |
| CANCELLED | Caller đã hủy | Dừng công việc chưa cần thiết; không mặc định rollback phần đã commit |
| INTERNAL/UNKNOWN | Lỗi không đủ thông tin để kết luận retry an toàn | Dựa vào contract và telemetry; tránh retry chung chung |

Status là tín hiệu cho caller, không phải bằng chứng đầy đủ về commit state. Với command có side effect, idempotency key hoặc operation-status endpoint mới giúp giải quyết outcome chưa rõ.

## 6. Thiết kế idempotency key cho command

Client tạo key trước attempt đầu và giữ nguyên qua retry:

```proto
message CreateOrderRequest {
  string customer_id = 1;
  repeated OrderLine items = 2;
  string idempotency_key = 3;
}
```

Quy tắc:

- Một ý định tạo đơn dùng một key.
- Retry cùng ý định giữ nguyên key và payload semantics.
- Người dùng chủ động tạo đơn mới phải có key mới.
- Key nên có entropy đủ lớn hoặc được tạo từ operation ID duy nhất.
- Scope key theo tenant, client và RPC method để tránh đụng namespace.
- Không dùng key làm authentication token hoặc bằng chứng quyền truy cập.

Server cần kiểm tra authorization trên mỗi attempt, kể cả khi trả lại kết quả đã lưu. Key không được cho phép caller khác đọc kết quả command.

Nếu request có field thay đổi theo từng attempt như trace ID hoặc timestamp transport, không đưa chúng vào fingerprint nghiệp vụ. Fingerprint chỉ bao gồm dữ liệu ảnh hưởng đến side effect.

## 7. Atomic idempotency: business data và command result cùng commit

Với command ngắn, cách đáng tin cậy là lưu idempotency record, business update và kết quả trong cùng transaction:

1. Atomically claim key bằng unique constraint.
2. Nếu key mới, thực hiện business operation.
3. Lưu operation/result reference.
4. Commit business data và idempotency record cùng nhau.
5. Chỉ sau commit mới gửi gRPC response.

Schema tối thiểu:

| Field | Vai trò |
| --- | --- |
| tenant_id, client_id, method | Scope của key |
| idempotency_key | Định danh command |
| request_hash | Phát hiện key bị dùng với payload khác |
| state | PROCESSING/COMPLETED/FAILED nếu workflow cần |
| operation_id | ID nghiệp vụ ổn định |
| result | Dữ liệu cần replay |
| created_at, expires_at | Retention |

Unique constraint trên scope key là bắt buộc. SELECT kiểm tra rồi INSERT không có unique constraint vẫn có race condition khi hai attempt tới cùng lúc.

Pseudo-flow của application service:

```java
@Transactional
public CreateOrderResult create(CreateOrderCommand command) {
    ClaimResult claim = idempotency.claim(command.key(),
                                           fingerprint(command));

    if (claim.isExisting()) {
        return claim.replayResultOrRejectFingerprintMismatch();
    }

    Order order = orderRepository.save(Order.create(command));
    CreateOrderResult result = CreateOrderResult.from(order);

    idempotency.complete(command.key(), result);
    return result;
}
```

Adapter chỉ phát response sau khi lời gọi transactional qua Spring proxy trả về. Nếu transaction rollback, cả business data và idempotency record mới đều rollback. Nếu commit thành công nhưng response mất, lần retry tìm thấy record COMPLETED và replay kết quả.

Cách triển khai claim phải dùng primitive atomic phù hợp database. Nếu duplicate-key làm transaction hiện tại rollback-only, không bắt exception rồi query trong cùng transaction; rollback và lookup trong transaction mới hoặc dùng insert-if-absent/upsert đúng semantics.

## 8. Request fingerprint và key mismatch

Cùng một key nhưng payload khác phải bị từ chối. Nếu không, client có thể vô tình dùng key của đơn A cho đơn B và nhận kết quả A như thể B đã được tạo.

Tạo fingerprint từ canonical business input:

- Bao gồm customer, items, quantity, amount và field ảnh hưởng side effect.
- Chuẩn hóa representation theo contract trước khi hash.
- Không bao gồm trace ID, deadline, retry count hoặc transport metadata.
- Lưu fingerprint version nếu canonicalization có thể thay đổi.
- Dùng hash mạnh như SHA-256 trên encoding ổn định.

Nếu fingerprint trùng, request là retry của cùng command. Nếu fingerprint khác, trả lỗi conflict/invalid usage theo contract; tuyệt đối không chạy side effect mới dưới key cũ.

Không nên chỉ hash raw Protobuf bytes nếu thứ tự field, unknown fields hoặc cách biểu diễn default có thể khác nhau nhưng semantics nghiệp vụ giống nhau. Canonicalization cần phản ánh semantics, không chỉ bytes.

## 9. Request trùng đồng thời và command đang xử lý

Hai attempt cùng key có thể tới hai replica khác nhau. Cơ chế phải hoạt động ở database/shared store, không dựa vào synchronized hoặc in-memory map của một instance.

Với transaction ngắn:

- Attempt đầu claim key và thực hiện operation.
- Attempt thứ hai bị unique constraint điều phối; nó chờ transaction đầu hoặc nhận conflict.
- Nếu attempt đầu commit, attempt hai đọc record COMPLETED và replay.
- Nếu attempt đầu rollback, attempt hai có thể claim và thực thi.
- Nếu chờ vượt deadline, caller retry cùng key sau đó.

Với workflow dài, có thể commit reservation PROCESSING riêng rồi chạy worker. Khi đó cần lease expiry, owner token, heartbeat, takeover và recovery. Worker có thể bị chạy lại sau lease timeout nên side effect vẫn phải idempotent. Cần API query trạng thái operation thay vì để client mở RPC trong thời gian dài.

Không để record PROCESSING tồn tại vĩnh viễn sau crash. Recovery job phải tìm lease hết hạn và quyết định retry, mark failed hoặc đưa vào hàng chờ xử lý thủ công.

## 10. Side effect trong cùng database và ngoài database

### Side effect nằm trong cùng database

Nếu tạo order, cập nhật inventory và lưu idempotency result đều ở cùng database, thực hiện chúng trong một transaction. Hoặc tất cả commit, hoặc tất cả rollback.

Nếu có nhiều bảng, giữ invariant bằng constraint, locking hoặc optimistic version. Không phát response thành công trước khi commit hoàn tất.

### Side effect ở hệ thống bên ngoài

Database transaction không thể rollback một email đã gửi, một payment provider đã charge hoặc một message đã publish. Không gọi hệ thống ngoài trong transaction rồi giả định rollback database sẽ undo side effect đó.

Các lựa chọn:

- Propagate idempotency key tới payment/provider nếu API downstream hỗ trợ.
- Ghi outbox event trong cùng transaction với business update.
- Dùng worker retry publish với event ID ổn định.
- Consumer deduplicate theo event ID/operation ID.
- Với workflow nhiều service, dùng saga và compensation.

## 11. Transactional outbox cho event và notification

Nếu command cập nhật order và cần phát OrderCreated:

1. Trong transaction, tạo order.
2. Trong cùng transaction, tạo idempotency result.
3. Trong cùng transaction, ghi outbox event với event ID ổn định.
4. Commit.
5. Worker đọc outbox và publish.
6. Worker đánh dấu đã gửi hoặc retry theo policy.
7. Consumer deduplicate event nếu broker redelivery.

Outbox bảo đảm business update và ý định phát event được lưu cùng nhau. Nó không bảo đảm broker chỉ nhận đúng một lần: worker có thể publish xong rồi crash trước khi đánh dấu sent. Vì vậy consumer phải idempotent.

Không gửi email trực tiếp trong transaction. Thay vào đó, ghi notification intent vào outbox; worker gửi với provider idempotency key nếu được hỗ trợ, hoặc lưu delivery receipt để giảm duplicate.

## 12. Saga và compensation cho workflow nhiều service

Khi command tạo side effect qua nhiều service/database, không có một transaction ACID đơn giản bao trùm tất cả.

Ví dụ đặt hàng:

1. Reserve inventory.
2. Authorize payment.
3. Tạo shipment.
4. Confirm order.

Nếu bước 3 thất bại sau khi payment đã authorize, hệ thống cần compensation như release inventory và void authorization. Đây là saga.

Mỗi bước saga cần:

- Operation ID ổn định.
- State transition bền vững.
- Idempotent command/consumer.
- Retry có giới hạn và backoff.
- Compensation rõ ràng cho bước đã hoàn tất.
- Dead-letter/manual recovery khi không thể tự phục hồi.

Compensation là nghiệp vụ mới để đưa hệ thống về trạng thái chấp nhận được; nó không phải rollback database xuyên service. Có thể có thời gian hệ thống ở trạng thái trung gian như PAYMENT_AUTHORIZED hoặc COMPENSATING; API phải biểu diễn trạng thái này rõ ràng.

## 13. Retry policy, backoff và deadline tổng

Retry cần giới hạn số lần và thời gian. Exponential backoff có jitter giảm khả năng nhiều client đồng loạt retry theo nhịp giống nhau:

```text
delay = min(max_delay, base_delay × 2^attempt) + random_jitter
```

Ngân sách tổng phải nằm trong deadline RPC/caller. Mỗi attempt dùng remaining deadline, không cấp lại timeout đầy đủ vô hạn.

Quy tắc vận hành:

- Chỉ retry status được contract xác định là transient/retryable.
- Giữ nguyên idempotency key và request semantics.
- Tôn trọng retry-after/RetryInfo nếu server trả.
- Có giới hạn attempt, tổng elapsed time và concurrency.
- Dùng circuit breaker/load shedding khi dependency quá tải.
- Tránh retry ở client, gRPC service, proxy và worker cùng lúc mà không tính tổng.
- Không retry side effect không có idempotency/deduplication.

Retry storm có thể làm database hoặc downstream càng quá tải. Khi tải cao, trả RESOURCE_EXHAUSTED/UNAVAILABLE phù hợp và yêu cầu client backoff thay vì nhận thêm attempt ngay lập tức.

## 14. Streaming RPC và giới hạn replay

Unary command có request hữu hạn nên client có thể gửi lại cùng request/key. Với client-streaming hoặc bidirectional streaming, client có thể đã gửi nhiều message trước khi kết nối bị ngắt. Không thể mặc định runtime sẽ replay toàn bộ stream ở tầng application hoặc server đã xử lý đến đâu.

Thiết kế streaming có side effect cần protocol resume:

- Mỗi stream có session/upload ID.
- Mỗi message có sequence number và idempotency key hoặc stable message ID.
- Server lưu receipt/checkpoint cùng transaction với side effect.
- Client reconnect và tiếp tục từ sequence chưa được xác nhận.
- Duplicate sequence cùng payload được replay receipt; cùng sequence nhưng payload khác bị conflict.
- Có expiry/cleanup cho session bỏ dở.

Với stream gồm nhiều command độc lập, commit từng command và ack sau commit. Nếu stream kết thúc lỗi, các command đã commit vẫn tồn tại; API phải công bố partial commit. Nếu toàn bộ batch phải atomic, dùng staging/finalize thay vì transaction mở suốt stream.

## 15. Observability và audit

Để điều tra duplicate side effect, ghi nhận:

- Operation ID/idempotency key ở dạng an toàn hoặc hash.
- RPC method và attempt number.
- Kết quả claim: NEW, REPLAY, IN_PROGRESS, KEY_MISMATCH.
- Business transaction outcome: committed/rolled back.
- Outbox event ID và delivery attempts.
- Saga state và compensation outcome.
- gRPC status, deadline remaining và retry delay.

Không đưa raw key, payload nhạy cảm hoặc customer/payment data vào metric labels. Metrics nên dùng label có cardinality giới hạn như method, outcome và dependency. Log/audit cần quyền truy cập, retention và masking phù hợp.

Các chỉ số hữu ích gồm duplicate request rate, replay count, key mismatch count, idempotency conflict, outbox backlog, publish retry, saga stuck duration và compensation failure.

## 16. Kiểm thử side effect và retry

Test thành công một lần chưa đủ. Cần kiểm thử failure window và concurrency:

| Test | Điều cần xác nhận |
| --- | --- |
| Retry trước khi server thực thi | Một command được thực hiện |
| Transaction rollback trước commit | Attempt sau có thể thực thi theo policy |
| Commit thành công, response bị ngắt | Retry cùng key replay kết quả |
| Hai request cùng key đồng thời | Chỉ một business side effect |
| Cùng key, payload khác | Bị từ chối; không có side effect mới |
| Outbox publish rồi worker crash | Event có thể gửi lại nhưng consumer deduplicate |
| Payment/provider timeout | Retry dùng cùng downstream idempotency key |
| Saga thất bại giữa các bước | Compensation đưa workflow về trạng thái hợp lệ |
| Deadline hết trong retry | Tổng attempt dừng trong ngân sách |
| Streaming disconnect | Resume từ checkpoint không lặp command đã commit |

Dùng hai transaction/thread độc lập để tạo duplicate race. Dùng fault injection để ngắt kết nối sau commit nhưng trước response. Test qua gRPC server thật và database cùng loại production khi cần xác minh unique constraint, transaction rollback và status mapping.

## 17. Checklist review

- Command có side effect được định danh ổn định qua nhiều attempt.
- Client giữ nguyên idempotency key qua retry của cùng ý định.
- Server kiểm tra fingerprint và từ chối key reuse với payload khác.
- Unique constraint bảo vệ key trên shared database/store.
- Claim, business update và stored result commit nguyên tử khi có thể.
- Response chỉ gửi sau commit.
- Timeout/UNAVAILABLE được coi là outcome có thể chưa rõ.
- Retry có status policy, backoff/jitter, attempt limit và deadline tổng.
- Không retry side effect không có idempotency/deduplication.
- External effects dùng downstream key, outbox hoặc saga/compensation.
- Consumer deduplicate event; không giả định broker exactly-once.
- Streaming có session, sequence, receipt và resume protocol.
- Partial commit và trạng thái workflow được công bố.
- Metrics/logs hỗ trợ truy vết mà không làm lộ dữ liệu nhạy cảm.
- Có fault-injection và concurrency tests cho mọi failure window quan trọng.

Trong **SPRING_GRPC**, retry chỉ tạo thêm attempt; nó không chứng minh attempt trước chưa commit. Hãy định danh command bằng idempotency key, lưu side effect và kết quả trong cùng transaction, rồi phát response sau commit. Với event và hệ thống ngoài database, dùng outbox, downstream deduplication hoặc saga. Khi stream bị ngắt, dùng sequence/checkpoint để resume thay vì giả định toàn bộ stream có thể replay an toàn.
