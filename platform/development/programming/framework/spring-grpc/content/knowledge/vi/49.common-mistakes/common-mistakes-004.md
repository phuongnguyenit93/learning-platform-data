# Retry command không idempotent

## 1. Lỗi thường gặp: retry một command như thể nó chưa từng chạy

Trong **SPRING_GRPC**, nhiều RPC thực hiện command có side effect: tạo order, trừ tiền, capture payment, tăng số dư, cấp coupon hoặc gửi lệnh tới thiết bị. Một lỗi nguy hiểm là client nhận timeout/UNAVAILABLE rồi gửi lại command như một request mới, không có cơ chế nhận diện lần gửi trước.

Ví dụ client gọi DebitAccount với amount = 100:

1. Server nhận request và trừ 100.
2. Database commit thành công.
3. Response bị mất vì kết nối bị ngắt.
4. Client nhận DEADLINE_EXCEEDED.
5. Client retry cùng nội dung nhưng server xử lý như command mới.
6. Tài khoản bị trừ thêm 100.

Client chỉ biết không nhận được response; nó không biết server đã commit hay chưa. Đây là **ambiguous outcome**. Retry một command không idempotent mà không có deduplication có thể nhân đôi side effect.

Nguyên tắc quan trọng: **một lần gửi lại là một attempt mới của cùng ý định nghiệp vụ, không phải một ý định mới**. Nếu server không thể nhận diện điều đó, client không thể suy ra kết quả chỉ từ timeout.

## 2. Idempotent và non-idempotent khác nhau thế nào?

Một operation idempotent có thể được thực hiện nhiều lần với cùng ý định mà kết quả hiệu lực cuối không thay đổi sau lần đầu. Ví dụ đặt trạng thái thiết bị thành OFF thường có thể idempotent.

Một operation non-idempotent tạo thêm hiệu lực mỗi lần thực hiện:

- Tăng balance thêm 100.
- Tạo một order mới.
- Charge thẻ thêm một khoản.
- Gửi một email hoặc SMS.
- Cấp một voucher mới.
- Tăng bộ đếm hoặc phát một lệnh vật lý.

Không đánh giá idempotency chỉ bằng HTTP/gRPC method name hoặc request giống nhau. Hãy xét side effect và semantics nghiệp vụ. Một RPC tên Update có thể non-idempotent nếu nó cộng dồn giá trị; một RPC tên Create có thể an toàn khi server deduplicate theo operation key.

## 3. Timeout không chứng minh server chưa thực thi

Một command có thể thất bại ở nhiều thời điểm:

| Failure window | Trạng thái có thể có | Hành động an toàn |
| --- | --- | --- |
| Request chưa tới server | Chưa có side effect | Có thể gửi lại cùng command identity |
| Server nhận nhưng chưa bắt đầu xử lý | Chưa có side effect | Retry theo contract |
| Transaction đang chạy và rollback | Không có thay đổi đã commit | Retry có thể thực thi |
| Database commit xong, response chưa tới client | Side effect đã tồn tại | Replay kết quả, không thực thi lại |
| Downstream đã thực hiện, response downstream bị mất | Side effect ngoài có thể đã tồn tại | Query/retry bằng downstream idempotency key |
| Response tới client | Caller biết kết quả | Chỉ gửi command mới khi có ý định mới |

DEADLINE_EXCEEDED chỉ nói caller hết thời gian chờ. UNAVAILABLE chỉ nói call không hoàn tất do service/transport không sẵn sàng. Cả hai không phải bằng chứng transaction chưa commit.

Đặc biệt, database commit và gửi gRPC response không nằm trong cùng một transaction. Server có thể commit thành công rồi process hoặc network lỗi trước khi client nhận response.

## 4. Vì sao retry mù nguy hiểm hơn trong hệ thống nhiều tầng?

Một command có thể bị retry ở nhiều nơi:

- Client application tự retry.
- gRPC retry policy tạo attempt mới khi call còn đủ điều kiện retry.
- API gateway hoặc proxy có retry policy.
- Worker/queue redelivery command.
- Downstream service retry lời gọi tới provider.

Nếu mỗi tầng đều retry mà không có một command identity dùng xuyên suốt, số lần side effect có thể tăng theo cấp số nhân. Ví dụ client retry 3 lần, gateway retry 2 lần và worker retry 3 lần có thể tạo nhiều attempt hơn dự kiến.

Retry cần có một owner rõ ràng cho mỗi workflow. Mọi tầng có retry phải giữ cùng operation ID/idempotency key và tuân theo giới hạn attempt/deadline chung.

gRPC retry policy điều khiển transport attempt; nó không cung cấp exactly-once cho business operation. Runtime có thể retry trong những điều kiện call còn retryable, nhưng ứng dụng không được dựa vào chi tiết retry nội bộ để bảo vệ side effect.

## 5. Khi nào không nên retry?

Không tự động retry một command non-idempotent nếu server/downstream không có cơ chế deduplicate và outcome có thể đã xảy ra.

Các trường hợp thường không retry mù:

- Không có idempotency key hoặc operation ID ổn định.
- Provider thanh toán không hỗ trợ idempotency và không có API tra cứu giao dịch.
- Lệnh thiết bị đã có thể được thực thi nhưng không có command sequence/status.
- Không thể xác định transaction đã commit hay chưa.
- Request mới có thể tạo một nghiệp vụ mới thay vì hỏi lại kết quả cũ.

Khi outcome chưa rõ, ưu tiên query operation status, đối soát bằng reference nghiệp vụ hoặc chuyển sang quy trình reconciliation. Nếu contract không có cách xác minh, dừng retry tự động và báo trạng thái chưa xác định cho caller/operation owner.

Không yêu cầu người dùng bấm lại nút để tạo request mới với key mới khi command cũ có thể đã thành công. UI nên giữ command identity và cho phép kiểm tra kết quả.

## 6. Tạo operation ID hoặc idempotency key trước attempt đầu

Client tạo key một lần cho một ý định nghiệp vụ, trước khi gửi RPC đầu tiên:

```proto
message DebitAccountRequest {
  string account_id = 1;
  int64 amount = 2;
  string idempotency_key = 3;
}

message DebitAccountReply {
  string operation_id = 1;
  int64 new_balance = 2;
}
```

Quy tắc:

- Cùng một ý định debit dùng cùng key qua mọi retry.
- Người dùng tạo một lệnh debit mới phải dùng key mới.
- Key phải được giữ qua process restart nếu client có thể retry sau khi khởi động lại.
- Scope key theo tenant, client/application và RPC method.
- Không sinh key trong interceptor cho mỗi attempt.
- Không dùng key làm credential hoặc thay thế authorization.

Nếu client tạo UUID mới mỗi lần retry, server sẽ nhìn thấy các command khác nhau và không thể deduplicate. Key cần được tạo tại boundary nơi ý định nghiệp vụ được hình thành và lưu đủ lâu cho retry/recovery window.

## 7. Request fingerprint ngăn dùng lại key cho payload khác

Server cần phát hiện trường hợp cùng key nhưng nội dung command thay đổi. Tạo fingerprint từ canonical business input:

- Resource/aggregate đích.
- Amount, currency và loại operation.
- Các field quyết định side effect.
- Phiên bản semantics nếu command contract thay đổi.

Không đưa trace ID, retry count, deadline hoặc metadata transport vào fingerprint. Chuẩn hóa representation trước khi hash để cùng một ý định có fingerprint ổn định.

Khi key đã tồn tại:

- Cùng fingerprint: đây là attempt khác của cùng command; trả kết quả cũ hoặc trạng thái đang xử lý.
- Khác fingerprint: từ chối vì key đã được sử dụng cho command khác.

Không trả kết quả của command cũ khi payload mới khác. Đây là lỗi client quan trọng cần được log và đo riêng.

## 8. Deduplicate nguyên tử cùng business transaction

Với command ngắn và side effect nằm trong cùng database, lưu idempotency record và business update trong cùng transaction.

Bảng record có thể lưu:

| Field | Vai trò |
| --- | --- |
| tenant_id/client_id/method | Scope key |
| idempotency_key | Định danh ý định |
| request_hash | Fingerprint |
| operation_id | ID nghiệp vụ ổn định |
| result/status | Kết quả có thể replay |
| created_at/expires_at | Thời gian lưu |
| state | Trạng thái nếu workflow cần |

Tạo unique constraint trên scope key. Một câu SELECT kiểm tra rồi INSERT riêng rẽ không đủ an toàn vì hai request đồng thời có thể cùng thấy key chưa tồn tại.

Pseudo-flow:

```java
@Transactional
public DebitResult execute(DebitCommand command) {
    String hash = fingerprint(command);

    boolean claimed = idempotencyRepository.insertIfAbsent(
        command.tenantId(),
        command.clientId(),
        "accounts.v1.AccountService/Debit",
        command.idempotencyKey(),
        hash
    );

    if (!claimed) {
        IdempotencyRecord record =
            idempotencyRepository.findRequired(command.scope());

        if (!record.requestHash().equals(hash)) {
            throw new IdempotencyKeyReuseException();
        }

        return record.completedResult();
    }

    Account account = accounts.findRequired(command.accountId());
    account.debit(command.amount());

    DebitResult result = DebitResult.from(account);
    idempotencyRepository.complete(command.idempotencyKey(), result);
    return result;
}
```

insertIfAbsent phải là thao tác atomic được bảo vệ bởi unique constraint, ví dụ insert-on-conflict theo database. Không triển khai bằng SELECT rồi INSERT không khóa.

Khi transaction commit, business update và kết quả idempotency cùng tồn tại. Nếu transaction rollback, cả hai cùng rollback. Nếu commit thành công nhưng response mất, retry cùng key tìm record đã hoàn tất và replay kết quả.

Với duplicate-key exception, transaction có thể đã bị đánh dấu rollback-only. Không bắt exception rồi mặc định query tiếp trong transaction đó; dùng insert-if-absent phù hợp hoặc rollback rồi lookup bằng transaction mới.

## 9. Xử lý hai request cùng key đến đồng thời

Client có thể retry trong khi attempt đầu vẫn đang chạy; hoặc hai request cùng key tới hai replica khác nhau. In-memory map hoặc synchronized trong một JVM không đủ bảo vệ.

Với transaction ngắn, unique index trong database là điểm điều phối chung:

1. Attempt đầu insert idempotency key.
2. Attempt thứ hai đụng unique key và chờ kết quả transaction đầu hoặc nhận kết quả conflict theo database.
3. Nếu attempt đầu commit, attempt hai đọc record và replay.
4. Nếu attempt đầu rollback, attempt hai có thể claim và thực thi.
5. Nếu thời gian chờ vượt deadline, caller retry lại cùng key.

Với tác vụ dài, có thể commit reservation PROCESSING riêng. Khi đó phải có lease expiry, owner token, heartbeat và recovery sau worker crash. Worker tiếp quản có thể chạy lại, nên side effect vẫn phải deduplicate. Không để PROCESSING record bị treo vĩnh viễn.

## 10. Downstream cũng phải nhận cùng command identity

Server deduplicate trong database nhưng sau đó gọi payment provider. Nếu provider không nhận idempotency key, vẫn có thể charge hai lần khi provider đã xử lý nhưng response bị mất.

Propagate operation identity tới downstream:

- Dùng cùng operation ID hoặc key riêng được ánh xạ ổn định theo provider.
- Lưu provider transaction/reference ID.
- Retry cùng provider key, không tạo key mới mỗi attempt.
- Nếu provider có API query status, dùng nó để giải quyết outcome chưa rõ.
- Nếu provider không hỗ trợ deduplication, xây reconciliation/manual review thay vì retry mù.

Không dùng một key chung cho các operation khác nhau như authorize, capture và refund. Mỗi loại side effect có identity riêng hoặc key được tạo theo operation type.

## 11. Outbox và saga cho side effect ngoài database

Một transaction database không thể rollback payment provider, email, broker hoặc service khác.

Nếu command cần phát event, ghi business state, idempotency result và outbox event trong cùng transaction. Dispatcher publish sau commit với event ID ổn định; consumer deduplicate vì broker delivery có thể lặp.

Với workflow nhiều service, dùng saga:

- Mỗi bước có operation ID và state transition bền vững.
- Command/consumer ở từng bước idempotent.
- Retry có giới hạn và backoff.
- Bước đã hoàn tất có compensation tương ứng khi workflow thất bại.
- Có timeout, stuck-state detection và manual recovery.

Compensation là một hành động nghiệp vụ mới, không phải rollback xuyên nhiều database. Ví dụ void authorization hoặc release inventory phải có identity riêng và idempotency riêng.

## 12. Retry policy và gRPC status

Không retry mọi status:

| Status | Cách xử lý với command non-idempotent |
| --- | --- |
| UNAVAILABLE | Outcome có thể chưa rõ; chỉ retry cùng key nếu server deduplicate |
| DEADLINE_EXCEEDED | Không kết luận rollback; query status hoặc retry cùng key |
| ABORTED | Đọc lại state và chạy lại workflow theo contract; không lặp write cũ |
| RESOURCE_EXHAUSTED | Backoff/tôn trọng RetryInfo; không retry dồn dập |
| FAILED_PRECONDITION | Chờ/sửa trạng thái nghiệp vụ; không retry mù |
| INVALID_ARGUMENT | Sửa request; không retry nguyên payload |
| PERMISSION_DENIED | Không retry cho tới khi quyền thay đổi |
| NOT_FOUND | Xử lý resource theo contract, không retry như lỗi transport |
| CANCELLED | Dừng công việc còn có thể hủy; side effect đã commit vẫn tồn tại |

DEADLINE_EXCEEDED và UNAVAILABLE không cho biết chắc server đã commit hay chưa. Với operation có idempotency, giữ key qua retry. Với operation không có deduplication, dùng status query/reconciliation.

## 13. Backoff, deadline và giới hạn attempt

Retry cần có exponential backoff và jitter để tránh nhiều client cùng retry đúng một thời điểm:

```text
delay = min(max_delay, base_delay × 2^(attempt - 1))
wait  = delay + random_jitter
```

Đặt:

- Maximum attempts.
- Maximum elapsed time.
- Deadline tổng cho command.
- Giới hạn concurrency của retry.
- Phân loại lỗi transient/permanent.
- Circuit breaker hoặc load shedding khi dependency quá tải.

Trước mỗi attempt, kiểm tra remaining deadline. Không cấp lại toàn bộ timeout ở mỗi lần thử. Không retry đồng thời ở client, server, proxy và worker mà không tính tổng số lần thực thi.

Nếu retry budget cạn mà outcome vẫn chưa rõ, trả kết quả chưa xác định theo API contract và cung cấp operation ID để tra cứu. Đừng đổi sang key mới chỉ để “thử lại lần nữa”.

## 14. Streaming command không thể retry như unary

Với client-streaming hoặc bidirectional streaming, client có thể đã gửi một số message trước khi kết nối bị ngắt. Server có thể đã commit một phần command stream.

Cần protocol resume rõ ràng:

- Stream/session ID ổn định.
- Sequence number cho từng command/chunk.
- Idempotency key hoặc message ID cho mỗi side effect.
- Receipt/checkpoint được lưu cùng transaction với side effect.
- Client reconnect và gửi tiếp sequence chưa được xác nhận.
- Duplicate sequence cùng payload replay receipt; payload khác bị từ chối.

Nếu stream xử lý mỗi message độc lập, commit và ack theo từng message; lỗi cuối stream không rollback các message đã commit. Nếu cần atomic cho toàn bộ batch, dùng staging/finalize thay vì transaction kéo dài qua network.

Không tự động mở stream mới rồi phát lại toàn bộ message nếu server không có deduplication theo sequence.

## 15. Khi không thể làm command idempotent

Có những side effect vật lý hoặc hệ thống legacy không hỗ trợ idempotency, operation lookup hay transaction chung. Khi đó phải công nhận giới hạn:

- Không tự động retry sau lỗi có outcome không rõ.
- Ghi operation attempt và correlation reference trước khi gửi.
- Tra cứu trạng thái qua kênh độc lập nếu có.
- Đối soát với hệ thống sở hữu side effect.
- Đưa trường hợp không thể xác định vào hàng chờ xử lý thủ công.
- Thiết kế compensation nếu nghiệp vụ cho phép.

Không tuyên bố exactly-once nếu không có cơ chế deduplication bền vững tại nơi side effect xảy ra. “Gửi đúng một lần” ở client không thể bảo đảm server hoặc provider chỉ thực hiện một lần khi response bị mất.

## 16. Kiểm thử để chứng minh retry không nhân đôi side effect

| Kịch bản | Assertion |
| --- | --- |
| Retry trước khi server nhận request | Chỉ một command hiệu lực |
| Commit rồi cắt response | Retry cùng key replay kết quả |
| Transaction rollback | Attempt sau có thể claim key và thực thi |
| Hai request cùng key đồng thời | Chỉ một business side effect |
| Cùng key, payload khác | Bị từ chối |
| Provider xử lý nhưng response mất | Retry cùng downstream key không charge lần hai |
| Outbox publish rồi crash | Consumer deduplicate event |
| Saga lỗi giữa các bước | Compensation chạy an toàn và có thể retry |
| Deadline hết trong retry | Không vượt deadline/attempt budget |
| Stream disconnect | Resume không lặp sequence đã commit |
| Không có deduplication | Client không tự retry outcome mơ hồ |

Dùng hai transaction/thread độc lập để tạo duplicate race. Fault injection cần mô phỏng đúng failure window sau commit nhưng trước response; ném exception bên trong transaction không thay thế được kịch bản này.

Kiểm tra cả database state, provider reference, outbox/inbox và gRPC status. Testcontainers hoặc môi trường test của provider giúp xác minh unique constraint và semantics thực tế.

## 17. Checklist review

- Phân biệt attempt mạng với ý định command nghiệp vụ.
- Không tự retry command non-idempotent khi outcome có thể chưa rõ.
- Key được tạo một lần trước attempt đầu và giữ qua mọi retry.
- Fingerprint phát hiện key bị tái sử dụng với payload khác.
- Unique constraint/deduplication nằm ở shared durable store.
- Idempotency record và business update commit cùng transaction.
- Response chỉ gửi sau commit; retry sau lost response replay kết quả.
- Duplicate concurrent requests được xử lý trên database, không chỉ trong memory.
- Downstream provider nhận key ổn định hoặc có status lookup/reconciliation.
- External event dùng outbox; consumer deduplicate.
- Multi-service workflow có saga/compensation khi cần.
- Retry status, backoff, deadline và attempt budget được định nghĩa.
- Streaming có sequence, receipt và resume protocol.
- Nếu không thể deduplicate, dừng retry mù và đối soát outcome.
- Có fault-injection tests cho commit-before-response và duplicate concurrency.

Trong **SPRING_GRPC**, retry một command không idempotent có thể nhân đôi side effect vì timeout không chứng minh server chưa commit. Hãy giữ một command identity qua mọi attempt, deduplicate nguyên tử cùng business transaction và truyền identity xuống các hệ thống ngoài. Nếu không thể xác định hoặc deduplicate outcome, query/reconcile thay vì tạo một request mới. Với streaming, cần sequence và checkpoint để resume an toàn.
