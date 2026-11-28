# Phối hợp bộ xử lý nền để tránh chạy trùng tác vụ

Service broker thường chạy nhiều bản sao ứng dụng để chịu tải và duy trì khả năng phục vụ khi một pod hoặc máy chủ gặp sự cố. Các bản sao này có thể cùng đọc operation queue, cùng quét database để tìm công việc đến hạn hoặc cùng nhận một message được gửi lại. Nếu mỗi worker tự quyết định xử lý mà không có cơ chế claim dùng chung, hai bộ xử lý có thể đồng thời provision một database, update cùng service instance hoặc deprovision cùng một tài nguyên.

Trong module SPRING_CLOUD_SERVICE_BROKER, việc tránh chạy trùng tác vụ cần được thiết kế ở cấp triển khai và state store. Một scheduler đơn lẻ trong bộ nhớ chỉ điều phối được một process; nó không bảo vệ được nhiều replica. Một distributed lock đơn giản cũng chưa đủ nếu worker cũ tiếp tục chạy sau khi lease hết hạn. Cần kết hợp durable operation state, atomic claim, lease/fencing, idempotent backend action, ordering theo instance và quy trình retry có kiểm soát.

## 1. Vì sao nhiều worker có thể xử lý cùng một tác vụ

Các tình huống thường gặp:

- Hai pod cùng chạy một scheduled poller và cùng thấy operation PENDING.
- Message broker giao lại message vì consumer chưa acknowledge trước visibility timeout.
- Worker đã gọi cloud provider nhưng chết trước khi ghi checkpoint; message được giao cho worker khác.
- Worker A bị pause lâu, lease hết hạn, worker B tiếp quản; sau đó A hoạt động lại.
- Một deployment rolling update khiến pod cũ và pod mới cùng tồn tại trong một khoảng thời gian.
- Hai loại trigger khác nhau cùng đưa một operation vào hàng đợi, ví dụ outbox publisher và recovery scanner.
- Một request retry tạo event lặp trong khi event trước vẫn đang được xử lý.

Vì delivery thường là at-least-once và process có thể dừng ở bất kỳ thời điểm nào, không thể dựa vào giả định một message chỉ đến một lần. Mục tiêu thực tế là bảo đảm chỉ một worker có quyền sở hữu operation tại một thời điểm, đồng thời mọi tác dụng phụ có thể được lặp lại hoặc reconcile an toàn.

## 2. Phân biệt operation, message và worker attempt

Ba khái niệm cần được lưu riêng:

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Operation | Ý định nghiệp vụ bền vững mà platform đã gửi | Provision instance X |
| Message/event | Thông báo cần đánh thức worker xử lý operation | OperationCreated(op-123) |
| Worker attempt | Một lần worker nhận quyền xử lý operation | Worker pod-7 claim op-123 lần thứ hai |

Một operation có thể tạo nhiều message do retry hoặc outbox redelivery. Một operation cũng có thể có nhiều worker attempt theo thời gian nếu worker trước chết hoặc lease hết hạn. Những lần attempt này vẫn phải phục vụ cùng một operation ID và cùng một logical resource.

Không tạo operation ID mới mỗi khi message được gửi lại. Operation ID đại diện cho công việc nghiệp vụ; message ID đại diện cho một lần phát sự kiện; attempt number đại diện cho số lần worker đã nhận xử lý.

## 3. Bất biến khi chạy nhiều worker

Trước khi chọn queue hoặc lock, hãy xác định các điều kiện cần luôn đúng:

- Một operation chỉ có một owner hợp lệ tại một thời điểm.
- Worker không có lease hiện hành không được ghi checkpoint hoặc terminal result.
- Một instance không chạy đồng thời hai operation lifecycle không tương thích.
- Event lặp không tạo thêm logical operation hoặc resource.
- Worker restart có thể tiếp tục từ state/checkpoint đã lưu.
- Operation không bị mất khi pod bị xóa hoặc broker restart.
- Operation hết retry được chuyển sang trạng thái cần can thiệp, không bị bỏ quên.
- Một operation cũ không ghi đè trạng thái mới hơn của instance.

Các điều kiện này phải được thực thi bởi database, queue có semantics phù hợp hoặc coordinator dùng chung. Một biến AtomicBoolean, synchronized block hay ConcurrentHashMap trong JVM không thể bảo vệ nhiều pod.

## 4. Mô hình operation bền vững

Một bảng operation có thể chứa:

| Field | Mục đích |
|---|---|
| operation_id | Định danh ổn định của logical operation |
| aggregate_id | Service instance bị tác động |
| operation_type | PROVISION, UPDATE hoặc DEPROVISION |
| status | PENDING, RUNNING, RETRY_WAIT, SUCCEEDED, FAILED |
| attempt | Số lần đã claim hoặc bắt đầu xử lý |
| owner_id | Worker hiện đang sở hữu operation |
| lease_until | Thời điểm quyền xử lý hiện tại hết hạn |
| fencing_token | Số tăng đơn điệu cho mỗi lần claim |
| next_attempt_at | Thời điểm operation được phép retry |
| checkpoint | Tiến độ đã lưu để worker tiếp tục |
| created_at, updated_at | Thời điểm tạo và cập nhật |
| completed_at | Thời điểm đạt trạng thái terminal |

Tên cột chỉ là mô hình minh họa. Có thể tách lease, attempt history, checkpoint hoặc event vào bảng riêng khi cần lưu audit và kiểm soát dung lượng.

Operation record phải được ghi bền vững trước khi trả 202 Accepted cho platform. Nếu message queue unavailable, outbox event vẫn nằm trong database để publisher gửi lại. Nếu dùng database polling trực tiếp, operation PENDING chính là hàng đợi bền vững.

## 5. Atomic claim thay cho đọc rồi mới khóa

Một lỗi phổ biến là worker đọc danh sách PENDING rồi mới cập nhật từng record:

    Worker A: SELECT operation WHERE status = PENDING
    Worker B: SELECT operation WHERE status = PENDING
    Worker A: xử lý op-123
    Worker B: xử lý op-123

Cả hai worker đều đã nhìn thấy cùng một record trước khi một bên thay đổi trạng thái. Claim phải là một thao tác atomic ở state store.

Với database hỗ trợ row locking và SKIP LOCKED, có thể claim theo batch:

~~~sql
BEGIN;

SELECT operation_id
FROM broker_operation
WHERE status IN ('PENDING', 'RETRY_WAIT')
  AND next_attempt_at <= CURRENT_TIMESTAMP
ORDER BY created_at
FOR UPDATE SKIP LOCKED
LIMIT 10;

-- Cập nhật các hàng đã khóa thành RUNNING,
-- gán owner_id, lease_until và tăng fencing_token.

COMMIT;
~~~

Đây là pseudocode SQL theo nhóm database hỗ trợ cú pháp tương tự PostgreSQL. Cần kiểm tra cú pháp và semantics của hệ quản trị thực tế. Claim và cập nhật owner/lease/token phải nằm trong cùng transaction; không commit chỉ sau SELECT rồi mới cập nhật ở transaction khác.

Một lựa chọn khác là compare-and-set:

~~~sql
UPDATE broker_operation
SET status = 'RUNNING',
    owner_id = :worker_id,
    lease_until = :lease_until,
    attempt = attempt + 1,
    fencing_token = fencing_token + 1,
    updated_at = CURRENT_TIMESTAMP
WHERE operation_id = :operation_id
  AND status IN ('PENDING', 'RETRY_WAIT')
  AND next_attempt_at <= CURRENT_TIMESTAMP;
~~~

Chỉ worker nhận được số hàng cập nhật bằng 1 mới được xử lý operation. Nếu số hàng bằng 0, worker khác đã claim, operation chưa đến hạn hoặc state đã thay đổi. Worker phải bỏ qua record đó và không gọi backend.

Nếu claim một batch, phải giới hạn số record theo năng lực worker và thời gian lease. Không claim hàng trăm operation rồi để chúng chờ trong bộ nhớ; lease có thể hết hạn trước khi worker bắt đầu xử lý.

## 6. Lease và gia hạn quyền sở hữu

Lease là quyền xử lý có thời hạn. Khi claim, worker được gán lease_until. Nếu xử lý lâu hơn dự kiến, worker gia hạn lease định kỳ:

~~~sql
UPDATE broker_operation
SET lease_until = :new_lease_until,
    updated_at = CURRENT_TIMESTAMP
WHERE operation_id = :operation_id
  AND status = 'RUNNING'
  AND owner_id = :worker_id
  AND fencing_token = :fencing_token
  AND lease_until > CURRENT_TIMESTAMP;
~~~

Nếu update không tác động hàng nào, worker đã mất quyền sở hữu hoặc lease hết hạn. Worker cần dừng việc nhận thêm bước xử lý và không ghi state như owner hiện tại. Không gia hạn lease chỉ dựa trên operation ID; phải xác minh owner và fencing token.

Lease duration cần dài hơn một khoảng xử lý bình thường nhưng vẫn đủ ngắn để operation được tiếp quản khi worker chết. Chọn thời hạn dựa trên thời gian backend call, checkpoint cadence, pause của JVM, network latency và thời gian shutdown. Không dùng một lease rất dài để tránh phải heartbeat; điều đó làm recovery chậm khi pod chết.

## 7. Fencing token ngăn worker cũ ghi đè

Lease không thể buộc một process bị pause phải dừng ngay. Worker A có thể ngừng hoạt động lâu hơn lease, worker B tiếp quản, rồi A tiếp tục sau khi JVM được resume. Nếu chỉ kiểm tra owner ở lúc claim, A vẫn có thể ghi dữ liệu trễ.

Fencing token là số tăng đơn điệu mỗi lần operation được claim:

    Worker A claim op-123 -> token 41
    Lease của A hết hạn
    Worker B claim op-123 -> token 42
    Worker B ghi checkpoint token 42 -> chấp nhận
    Worker A hoạt động lại, ghi token 41 -> từ chối

Mọi cập nhật checkpoint, trạng thái operation và instance snapshot phải kèm fencing token/version hiện hành. Ví dụ:

~~~sql
UPDATE broker_operation
SET checkpoint = :checkpoint,
    updated_at = CURRENT_TIMESTAMP
WHERE operation_id = :operation_id
  AND status = 'RUNNING'
  AND owner_id = :worker_id
  AND fencing_token = :fencing_token;
~~~

Fencing token trong database chỉ ngăn worker cũ ghi state vào database đó. Nếu worker A đã gửi lệnh tới cloud provider trước khi mất lease, lệnh vẫn có thể tiếp tục ở provider. Khi có thể, truyền operation ID hoặc token tới backend nếu API hỗ trợ idempotency/version. Nếu backend không hỗ trợ, worker mới phải reconcile resource state trước khi lặp tác dụng phụ.

## 8. Idempotent worker và adapter

Không có distributed coordination nào loại bỏ hoàn toàn cửa sổ lỗi giữa side effect bên ngoài và việc ghi kết quả nội bộ. Ví dụ provider đã tạo database nhưng worker chết trước khi lưu resource ID. Worker khác tiếp quản và có thể tạo database thứ hai nếu adapter không idempotent.

Mỗi tác dụng phụ cần một logical idempotency identity:

- Provision: broker instance ID hoặc operation ID làm external idempotency key nếu provider hỗ trợ.
- Tạo binding principal: instance ID + binding ID.
- Revoke credential: binding ID + action type.
- Update: instance ID + desired configuration/version.
- Deprovision: instance ID + resource ownership tag.

Adapter nên tra cứu resource theo ownership metadata trước khi tạo lại. Khi retry, nếu resource đã tồn tại và thuộc đúng instance, adapter tiếp tục hoặc trả kết quả hiện tại. Nếu resource cùng tên nhưng thuộc owner khác, không nhận nhầm; báo conflict và cần xử lý theo policy.

Không giả định mọi cloud API đều hỗ trợ idempotency key. Với provider không có cơ chế đó, gắn tag/label chứa broker instance ID và operation reference, sau đó reconcile trước khi tạo hoặc xóa.

## 9. Tránh chạy hai operation lifecycle trên cùng instance

Atomic claim đảm bảo một operation record không bị hai worker sở hữu đồng thời. Nhưng một instance có thể có hai operation record khác nhau: ví dụ update và deprovision cùng được tạo. Vì vậy cần thêm serialization theo aggregate.

Một số lựa chọn:

- Unique constraint cho một active lifecycle operation trên mỗi instance.
- Parent-row lock khi tạo operation và chuyển instance state.
- Compare-and-set trên instance version/status.
- Partition message theo instance ID để giữ thứ tự xử lý.
- Aggregate command coordinator nếu workflow có nhiều loại event và thứ tự phức tạp.

Ví dụ quy tắc:

| Instance state | Operation mới | Kết quả |
|---|---|---|
| ACTIVE | UPDATE | Chấp nhận nếu plan policy cho phép |
| ACTIVE | DEPROVISION | Chấp nhận nếu không còn binding blocking |
| UPDATING | UPDATE thứ hai | Từ chối hoặc xếp hàng theo policy đã định nghĩa |
| UPDATING | DEPROVISION | Từ chối hoặc ghi nhận intent chờ sau khi update kết thúc |
| DEPROVISIONING | PROVISION/UPDATE/BIND | Từ chối |
| DEPROVISIONED | Request lặp | Xử lý theo tombstone và semantics OSB |

Không để worker tự quyết định thứ tự chỉ dựa vào message arrival time. Operation được tạo từ nhiều nguồn có thể đến queue theo thứ tự khác nhau; state transition trong database mới là nguồn quyết định có thẩm quyền.

## 10. Ordering theo instance và song song giữa các instance

Broker thường muốn xử lý nhiều instance song song để tăng throughput, nhưng các operation trên cùng instance cần được tuần tự hóa khi có phụ thuộc.

Một chiến lược là partition theo aggregate ID:

    Partition 0: instance-A -> provision -> update
    Partition 1: instance-B -> provision -> deprovision
    Partition 2: instance-C -> provision -> bind

Mỗi partition có thể xử lý tuần tự, trong khi các partition chạy song song. Nếu dùng Kafka, key message theo instance ID giúp record của cùng key đi vào cùng partition. Tuy nhiên, rebalance và retry vẫn cần idempotency và state check; ordering trong partition không bảo vệ được tác dụng phụ ngoài queue.

Nếu dùng database queue, có thể dùng aggregate lock hoặc active-operation constraint để bảo vệ cùng instance. Những operation thuộc instance khác vẫn có thể chạy song song. Tránh global lock vì nó làm giảm throughput và tạo điểm nghẽn.

## 11. Transactional outbox và nhiều publisher

Khi request được accepted, broker thường cần ghi operation và gửi message để worker xử lý. Nếu ghi database thành công nhưng publish thất bại, operation bị kẹt. Nếu publish trước commit rồi transaction rollback, worker nhận event không có operation tương ứng.

Transactional outbox ghi state và event trong cùng transaction:

1. Ghi operation PENDING.
2. Chuyển instance sang trạng thái phù hợp.
3. Ghi outbox event chứa event ID, operation ID, aggregate ID và version.
4. Commit.
5. Một hoặc nhiều outbox publisher claim event chưa gửi.
6. Publisher gửi message rồi đánh dấu event đã publish.

Nhiều publisher có thể cùng chạy nếu claim event atomic bằng row lock/lease hoặc compare-and-set. Nếu publisher gửi message thành công nhưng chết trước khi đánh dấu SENT, event sẽ được gửi lại. Consumer phải deduplicate theo event ID hoặc operation ID.

Không xóa outbox event ngay sau khi publish nếu cần audit/replay. Có thể lưu trạng thái published và dọn theo retention policy riêng.

## 12. Chọn database polling hay message broker

Hai mô hình đều có thể dùng; lựa chọn dựa trên quy mô, throughput và yêu cầu vận hành:

| Tiêu chí | Database polling | Message broker |
|---|---|---|
| Hạ tầng | Ít thành phần hơn nếu đã có relational DB | Cần vận hành queue/cluster |
| Claim | Row lock, lease hoặc compare-and-set | Consumer group, ack và visibility/offset |
| Delivery | Worker quét lại record đến hạn | Thường at-least-once tùy cấu hình |
| Ordering | Khóa/partition do ứng dụng thiết kế | Có thể partition theo aggregate key |
| Retry | next_attempt_at trong operation table | Retry topic/queue hoặc delayed delivery |
| Backpressure | Batch size và polling interval | Consumer concurrency và prefetch |
| Quan sát | DB query, queue age, lease | Consumer lag, redelivery, DLQ |

Database polling phù hợp khi workload vừa phải và muốn ít hạ tầng. Message broker phù hợp khi cần tách producer/consumer, throughput lớn hoặc nhiều nhóm worker. Dù chọn cách nào, operation state vẫn nên được lưu bền vững và worker vẫn phải idempotent.

## 13. Retry, backoff và dead-letter

Không retry vô hạn ngay lập tức. Operation record nên có attempt, next_attempt_at và last_error_code đã chuẩn hóa.

Một policy ví dụ:

| Lỗi | Hành vi |
|---|---|
| Network timeout tạm thời | Reconcile backend, rồi retry có backoff |
| Provider rate limit | Tôn trọng Retry-After nếu có và giới hạn concurrency |
| Provider unavailable | Retry có giới hạn với exponential backoff và jitter |
| Validation/configuration error | Đánh dấu FAILED; không retry tự động |
| Quota exhausted | Chờ quota thay đổi hoặc kết thúc theo policy |
| Resource ownership conflict | Đưa vào trạng thái cần điều tra; không tự xóa resource |
| Max attempts reached | Chuyển DEAD/NEEDS_ATTENTION và phát cảnh báo |

Dead-letter không có nghĩa bỏ operation. Cần lưu lý do, attempt history và cách operator replay hoặc xử lý thủ công. Replay phải dùng cùng operation ID và idempotency identity, đồng thời xác minh state hiện tại trước khi chạy tiếp.

## 14. Scheduled scanner và leader election

Một ứng dụng Spring có thể dùng scheduler để quét operation PENDING hoặc lease hết hạn. Khi chạy nhiều replica, mọi replica có thể cùng kích hoạt scheduled method. Điều này không sai nếu mỗi batch được claim atomic:

~~~java
@Scheduled(fixedDelayString = "1000")
public void scanOperations() {
    operationClaimer.claimBatch(workerIdentity, batchSize)
            .forEach(workerDispatcher::dispatch);
}
~~~

Đây là pseudocode imperative. Nếu repository reactive, không gọi subscribe tùy tiện trong scheduler; hãy dùng scheduler/worker lifecycle được quản lý và giữ publisher trong pipeline phù hợp.

Leader election có thể hữu ích cho một số tác vụ cần một coordinator toàn cục, như refresh catalog snapshot hoặc cleanup một partition metadata duy nhất. Tuy nhiên, không cần buộc chỉ một pod được chạy toàn bộ worker pool nếu database/queue đã hỗ trợ competing consumers. Một leader đơn nhất có thể trở thành bottleneck và điểm lỗi.

Nếu dùng leader election, lease leader phải được gia hạn và có fencing/epoch. Leader cũ sau network partition không được tiếp tục ghi state khi leader mới đã được bầu.

## 15. Triển khai nhiều replica trên Kubernetes

Kubernetes Deployment có thể chạy nhiều replica của broker và worker. Cần xác định rõ:

- HTTP broker replicas phục vụ request OSB.
- Worker replicas claim operation và gọi provider.
- Outbox publisher replicas phát event.
- Scheduled maintenance jobs chạy theo cơ chế riêng nếu cần.

Không đặt một scheduled task destructive trên mọi pod mà không có claim/lock dùng chung. Nếu dùng Kubernetes CronJob, cấu hình concurrency policy có thể giảm lần chạy chồng nhau của một CronJob, nhưng không thay thế idempotency và database state guard. Pod có thể bị terminate, job có thể retry và một thao tác trước đó có thể đã hoàn tất ở provider.

Tách worker deployment khỏi HTTP deployment có thể giúp scale độc lập. Khi worker cần thêm CPU/memory hoặc provider concurrency thấp, scale worker theo queue depth/operation age thay vì tăng HTTP replicas.

Readiness và liveness probe cần phản ánh trạng thái ứng dụng phù hợp. Worker không nên nhận thêm operation khi đang shutdown hoặc chưa kết nối được state store/queue. Liveness probe không nên restart pod chỉ vì một operation backend đang chạy lâu hợp lệ.

## 16. Graceful shutdown và rolling deployment

Khi Kubernetes gửi SIGTERM, worker nên:

1. Chuyển sang trạng thái draining và ngừng claim operation mới.
2. Cho các attempt đang chạy thời gian hoàn tất trong shutdown grace period.
3. Lưu checkpoint trước khi dừng nếu workflow hỗ trợ checkpoint.
4. Ack message chỉ khi operation đã được ghi nhận bền vững theo contract.
5. Nếu chưa hoàn tất, để lease hết hạn hoặc chủ động release lease có điều kiện để worker khác tiếp quản.
6. Đóng client, scheduler và connection pool sau khi xử lý xong.

Không đánh dấu FAILED chỉ vì pod bị terminate khi operation vẫn có thể tiếp tục. Không ack message trước khi operation/checkpoint được lưu bền vững. Không release lease bằng câu UPDATE chỉ theo operation ID; phải kiểm tra owner và fencing token để tránh pod cũ giải phóng lease của worker mới.

Trong rolling deployment, worker phiên bản mới và cũ có thể cùng xử lý operation. Event schema và operation state cần tương thích ngược trong khoảng rollout. Nếu thay đổi schema, dùng migration theo kiểu expand-and-contract: thêm field tương thích, deploy consumer hiểu cả cũ/mới, chuyển producer, rồi mới loại field cũ.

## 17. Backpressure và giới hạn concurrency

Không claim nhiều operation hơn số worker có thể xử lý. Nếu mỗi pod chỉ có 8 slot xử lý nhưng claim 100 operation, 92 operation có thể nằm chờ trong memory trong khi lease vẫn chạy.

Thiết kế nên có:

- Batch size gần với số slot rảnh.
- Giới hạn concurrency toàn cục theo provider nếu provider có rate limit.
- Giới hạn concurrency theo tenant để một tenant không chiếm hết worker.
- Giới hạn riêng cho operation nặng như snapshot/migration.
- Queue age và operation deadline để phát hiện backlog.
- Circuit breaker hoặc admission control khi provider đang lỗi.

Nếu một provider chỉ cho tối đa 20 thao tác đồng thời, cần quota concurrency dùng chung giữa các replica hoặc chia partition có giới hạn. Semaphore trong mỗi pod với giá trị 20 sẽ cho phép tổng cộng 20 nhân số pod, vượt giới hạn provider.

## 18. Quan sát và cảnh báo

Các metric vận hành nên gồm:

- Số operation PENDING, RUNNING, RETRY_WAIT và NEEDS_ATTENTION.
- Tuổi operation PENDING lâu nhất.
- Số lease hết hạn và số lần operation được claim lại.
- Số lần fencing token cũ bị từ chối.
- Thời gian xử lý mỗi operation type và provider.
- Số event redelivery, outbox pending và consumer lag.
- Số operation đạt max attempts hoặc vào dead-letter.
- Số lỗi duplicate resource/idempotency conflict.
- Số worker slot đang dùng và concurrency theo provider/tenant.
- Thời gian shutdown/drain và số operation được release để tiếp quản.

Log cần mang operation ID, instance ID, worker ID, attempt, fencing token và correlation ID. Không log credentials hoặc toàn bộ parameters. Metric label phải có cardinality giới hạn; dùng operation type, provider name và outcome thay vì instance ID.

Cảnh báo khi operation pending quá lâu, lease liên tục hết hạn, outbox age tăng, DLQ tăng hoặc worker claim được operation nhưng không ghi checkpoint trong khoảng thời gian bất thường.

## 19. Kiểm thử nhiều worker và lỗi giữa chừng

Unit test cho state transition chưa đủ. Cần integration test với database/queue thực tế hoặc container test để kiểm chứng claim và redelivery:

| Ca kiểm thử | Kết quả mong đợi |
|---|---|
| Hai worker claim cùng một operation đồng thời | Chỉ một worker nhận quyền |
| Hai worker claim hai operation khác instance | Có thể chạy song song |
| Hai operation lifecycle trên cùng instance | Chỉ operation hợp lệ được active |
| Worker chết sau khi claim | Lease hết hạn và worker khác tiếp quản |
| Worker chết sau backend side effect, trước checkpoint | Worker mới reconcile, không tạo resource thứ hai |
| Worker A trở lại sau khi B đã claim | Fencing token cũ không ghi được state |
| Message được giao hai lần | Consumer deduplicate hoặc xử lý idempotently |
| Publisher chết sau publish, trước mark SENT | Event có thể redeliver nhưng operation không chạy trùng |
| Provider rate limit | Backoff và concurrency limit được tuân thủ |
| Max attempts đạt ngưỡng | Operation chuyển trạng thái cần can thiệp |
| Pod nhận SIGTERM khi đang xử lý | Ngừng claim mới, checkpoint/release an toàn |
| Rolling deploy có message schema mới | Worker cũ và mới không làm hỏng operation |

Test concurrency nên dùng barrier để buộc hai worker cùng tranh claim và xác minh trạng thái database cuối cùng. Không chỉ assert một trong hai future thành công; cần kiểm tra owner, lease, attempt, token và số lần provider adapter được gọi.

## 20. Những sai lầm thường gặp

- Dùng một scheduled method trong mọi pod mà không có atomic claim.
- Đọc PENDING rồi xử lý trước khi cập nhật quyền sở hữu.
- Cho rằng message broker chỉ giao một lần.
- Dùng distributed lock có TTL nhưng không fencing worker cũ.
- Claim batch lớn hơn khả năng xử lý thực tế.
- Giữ database transaction mở trong lúc gọi cloud provider.
- Tạo operation ID mới cho mỗi lần redelivery.
- Retry side effect mà không tra cứu resource đã tạo.
- Chỉ khóa operation record mà không serialize theo service instance.
- Dùng leader election để thay thế idempotency và state guard.
- Ack message trước khi lưu checkpoint bền vững.
- Đánh dấu FAILED mọi operation khi pod shutdown.
- Scale semaphore theo pod mà không xét giới hạn concurrency toàn cục.
- Deploy worker mới với schema event không tương thích worker cũ.

## Kết luận

Để nhiều bộ xử lý nền không chạy trùng tác vụ, service broker cần operation state bền vững, atomic claim, lease có gia hạn, fencing token và idempotent provider adapter. Claim bảo vệ một operation khỏi hai worker cùng sở hữu; serialization theo instance bảo vệ các operation khác nhau nhưng không tương thích; outbox và consumer dedup xử lý redelivery; retry/DLQ giữ công việc có thể phục hồi. Khi triển khai trên Kubernetes, graceful shutdown, rolling compatibility, backpressure và metrics phải đi cùng các cơ chế đó. Thiết kế như vậy cho phép tăng worker replicas và tiếp quản sau sự cố mà không tạo tài nguyên trùng, ghi đè state mới hoặc làm mất operation mà platform đang chờ.
