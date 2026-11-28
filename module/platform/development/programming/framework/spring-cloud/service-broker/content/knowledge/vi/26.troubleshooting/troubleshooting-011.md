# Quy trình thu thập bằng chứng từ nền tảng, broker, kho dữ liệu và nhà cung cấp

Khi một service broker gặp sự cố, một dòng log lỗi hiếm khi đủ để giải thích điều gì đã xảy ra. Platform có thể đã gửi request nhiều lần; broker có thể đã trả 202 rồi giao operation cho worker; database có thể đã commit state trong khi provider chưa hoàn tất; provider có thể đã tạo tài nguyên nhưng response bị timeout trên đường về. Nếu chỉ xem một thành phần, đội vận hành dễ kết luận sai, retry không an toàn hoặc xóa nhầm tài nguyên.

Với module SPRING_CLOUD_SERVICE_BROKER, chẩn đoán cần ghép bằng chứng theo cùng một timeline từ bốn lớp: **nền tảng gọi broker**, **broker và worker**, **kho dữ liệu của broker**, và **cloud provider hoặc Kubernetes control plane**. Quy trình phải bảo toàn bằng chứng, ghi rõ nguồn và thời điểm, bảo vệ dữ liệu nhạy cảm, rồi mới hình thành giả thuyết. Thu thập bằng chứng là hoạt động quan sát; không thay đổi trạng thái instance, operation, quota hoặc resource trong lúc đang xác minh.

## 1. Mục tiêu của quy trình điều tra

Một cuộc điều tra tốt cần trả lời được:

- Người dùng hoặc platform thực hiện thao tác gì, với service, plan, instance và binding nào?
- Platform đã gửi request lúc nào, gửi bao nhiêu lần và nhận HTTP status/error nào?
- Broker đã nhận request, xác thực, validate, ghi operation và trả response ra sao?
- Operation có được worker claim không? Worker nào xử lý, attempt nào và checkpoint cuối là gì?
- Transaction database đã commit hay rollback? Có reservation, outbox event hoặc state transition nào còn dở?
- Provider đã nhận lệnh chưa? Có provider request ID, async job ID hoặc resource ID không?
- Actual resource state có khớp với desired state mà broker lưu hay không?
- Bằng chứng nào đã xác nhận, bằng chứng nào chỉ là giả thuyết và còn thiếu dữ liệu gì?

Kết quả không chỉ là một nguyên nhân có vẻ hợp lý. Cần có timeline, danh sách evidence, mối liên hệ giữa các ID, phạm vi ảnh hưởng và mức độ chắc chắn của kết luận.

## 2. Bắt đầu bằng phạm vi và thời gian sự cố

Trước khi truy vấn log, lập incident record ngắn:

| Trường | Nội dung cần ghi |
|---|---|
| Incident ID | Mã sự cố nội bộ dùng xuyên suốt |
| Service | Service ID và plan ID liên quan |
| Resource | Instance ID, binding ID hoặc operation ID nếu đã biết |
| Tenant/scope | Tenant reference, provider account/project và region; chỉ lưu định danh cần thiết |
| Operation | PROVISION, UPDATE, DEPROVISION, BIND, UNBIND hoặc thao tác khác |
| Thời gian | Khoảng bắt đầu/kết thúc theo UTC và múi giờ gốc nếu cần |
| Platform | Cloud Foundry, Kubernetes hoặc nền tảng gọi broker |
| Mức độ ảnh hưởng | Một resource, một tenant, một provider region hay toàn broker |
| Người điều tra | Người thu thập và người xác minh |

Chọn khoảng thời gian đủ rộng để bao gồm request đầu tiên, retry, async polling, worker attempt và provider operation. Ví dụ, nếu người dùng báo lỗi lúc 10:20, hãy tìm request trước đó và các lần retry sau đó thay vì chỉ lấy log trong đúng một phút.

Ghi rõ múi giờ. Chuẩn hóa timeline về UTC, nhưng giữ timestamp gốc và timezone trong evidence record. Không tự giả định tất cả log, database và provider đều dùng cùng đồng hồ.

## 3. Xác định các định danh liên kết

Một request OSB có thể đi qua nhiều process và tạo ra nhiều ID. Trước khi truy vấn sâu, lập bảng liên kết:

| Định danh | Nguồn tạo | Dùng để tìm |
|---|---|---|
| Correlation/trace ID | Gateway hoặc broker ingress | Log và distributed trace xuyên service |
| HTTP request ID | Platform, ingress hoặc broker | Một lần gọi HTTP cụ thể |
| Service instance ID | Platform request | Provision, update, deprovision và last operation |
| Binding ID | Platform request | Create/unbind binding |
| Operation key/ID | Broker response/state store | Async worker và last operation polling |
| Worker ID/attempt | Worker runtime | Claim, lease, checkpoint và retry |
| Provider request ID | Provider API response/header | Audit log và support của provider |
| Provider resource ID | Provider | Describe/list resource và audit event |
| Database transaction/reference | Data access layer hoặc database | Commit, rollback, lock và row history |

Không phải mọi nền tảng đều gửi một correlation ID chuẩn trong request OSB. Broker nên tạo request ID nội bộ nếu thiếu, ghi lại ID nhận từ gateway nếu có và truyền trace context qua các service nội bộ. Không tự tạo lại ID ở mỗi lớp rồi làm mất mối liên hệ.

Với async operation, operation key là mối nối quan trọng giữa HTTP response 202, worker, operation store và endpoint last operation. Với provider call, lưu provider request ID cùng operation ID trong log/state để có thể hỏi nhà cung cấp bằng một tham chiếu chính xác.

## 4. Bảo toàn bằng chứng trước khi phân tích

Log có thể bị rotate, pod có thể bị reschedule, message có thể hết retention và provider audit event có thể chỉ lưu trong một khoảng thời gian. Khi incident được mở:

1. Ghi lại thời gian và phạm vi cần thu thập.
2. Export log/trace/metric cần thiết theo khoảng thời gian.
3. Ghi nguồn, query/filter, thời điểm export và người thực hiện.
4. Giữ bản gốc ở nơi lưu trữ có quyền truy cập hạn chế.
5. Tạo bản đã redact để chia sẻ cho người cần phân tích.
6. Ghi checksum nếu quy trình tổ chức yêu cầu chứng minh file không bị thay đổi.
7. Không chỉnh sửa bản gốc để thêm ghi chú; ghi chú trong incident record riêng.

Evidence ledger có thể có cấu trúc:

| Field | Ví dụ |
|---|---|
| evidence_id | EV-0042 |
| source | broker-worker log |
| query/window | operation ID, UTC start/end |
| collected_at | Thời điểm export |
| collector | Người hoặc hệ thống thu thập |
| original_location | Kho lưu trữ có kiểm soát |
| checksum | SHA-256 nếu quy trình yêu cầu |
| redaction | Các trường đã che |
| limitation | Log thiếu 3 phút do retention hoặc pod đã bị xóa |

Không gửi raw log, database dump hoặc provider response có secret qua kênh chat công khai. Dùng kho evidence được phê duyệt và chia sẻ bản đã redact theo nguyên tắc tối thiểu cần biết.

## 5. Thu thập bằng chứng từ platform

Platform là nguồn tốt nhất để xác định ý định của caller và những gì platform quan sát được. Cần lấy:

- Request method, endpoint, path và query parameters.
- Thời điểm gửi, timeout phía client và số lần retry.
- OSB API version header mà platform gửi.
- HTTP status và response body nhận được.
- Service ID, plan ID, instance ID hoặc binding ID.
- Giá trị accepts_incomplete nếu thao tác hỗ trợ async.
- Operation key nhận từ response 202.
- Các lần polling last operation và kết quả succeeded/failed/in progress.
- Event/audit record của platform về create, update, delete hoặc bind.
- Platform request ID, task ID hoặc job ID nếu có.

Không cần thu Authorization header nguyên vẹn. Nếu cần xác minh xác thực, ghi loại cơ chế, principal/client identity đã được chuẩn hóa và kết quả authentication; không lưu Basic credential, bearer token hoặc secret.

### Cách đọc chuỗi request

Một chuỗi provision async có thể có dạng:

    10:00:00 Platform gửi PUT service_instances/inst-42
    10:00:01 Broker trả 202 và operation key op-91
    10:00:02 Platform polling last_operation op-91
    10:00:04 Broker trả in progress
    10:00:20 Platform polling lại
    10:00:21 Broker trả failed

Nếu platform chỉ lưu response cuối, có thể bỏ sót việc broker đã trả 202 đúng và operation thất bại sau đó. Cần thu toàn bộ chuỗi request/response, không chỉ request đầu hoặc lần polling cuối.

### Phân biệt retry với thao tác mới

So sánh instance ID, binding ID, request payload đã chuẩn hóa, idempotency key nếu broker có hỗ trợ và timestamp. Hai request có cùng instance ID nhưng payload khác nhau có thể là update mới hoặc conflict, không mặc định là retry. Giữ payload đã redact hoặc fingerprint; không sao chép parameters có password/token vào incident report.

## 6. Thu thập bằng chứng từ broker HTTP layer

Ở ingress và HTTP handler, cần tìm:

- Request ID/correlation ID, method, route và timestamp.
- Kết quả authentication/authorization, không kèm credential.
- API version negotiation.
- Parse/validation outcome.
- Service ID, plan ID, instance ID và binding ID đã được chuẩn hóa.
- HTTP status, OSB error code và thời gian xử lý.
- Exception type đã chuẩn hóa và stack trace nội bộ có quyền truy cập.
- Response write/connection reset nếu client đã ngắt kết nối.

Với Spring Cloud Open Service Broker, kiểm tra log tại các lớp nhận request, service interface implementation, application service và exception/error mapper. Nếu framework trả 422 AsyncRequired, 409 Conflict hoặc 5xx, cần xác định exception/domain condition nào đã dẫn đến mapping đó.

Không bật debug logging toàn bộ request body ở production một cách tùy tiện. Parameters của service broker có thể chứa mật khẩu database, username, certificate, webhook secret hoặc dữ liệu khách hàng. Nếu cần bật log tạm thời, dùng allowlist field, thời gian giới hạn, quyền truy cập hạn chế và xác nhận redaction trước.

## 7. Thu thập bằng chứng từ worker và operation pipeline

Với operation bất đồng bộ, lấy log và state theo operation ID:

- Thời điểm operation được tạo và commit.
- Worker nào claim operation và attempt number.
- Lease expiry/renewal, owner ID và fencing token nếu có.
- Checkpoint trước và sau mỗi bước quan trọng.
- Provider adapter được gọi với action/resource reference nào.
- Provider request ID và response classification.
- Retry count, next attempt time và last normalized error.
- Terminal state và completed timestamp.
- Message ID, redelivery count hoặc consumer lag nếu dùng message broker.

Một timeline worker minh họa:

| Thời điểm | Event | Ý nghĩa |
|---|---|---|
| 10:00:01 | Operation op-91 được commit PENDING | Broker đã nhận async work |
| 10:00:02 | Worker w-3 claim attempt 1 | Có owner xử lý |
| 10:00:05 | Provider create request req-p7 | Provider đã nhận lệnh |
| 10:00:35 | Worker timeout trước checkpoint | Chưa biết side effect đã hoàn tất hay chưa |
| 10:01:10 | Worker w-5 claim attempt 2 | Operation được tiếp quản |
| 10:01:12 | Adapter describe resource | Reconcile trước khi retry create |

Timeout sau provider call không chứng minh provider chưa tạo resource. Tìm provider request ID hoặc inventory trước khi kết luận thao tác thất bại. Cũng cần kiểm tra worker cũ có tiếp tục chạy sau khi lease hết hạn hay không; fencing token có thể giải thích vì sao một checkpoint bị từ chối.

## 8. Thu thập bằng chứng từ database

Database là nguồn có thẩm quyền cho broker desired state, operation state, quota ledger và outbox. Chỉ dùng truy vấn read-only trong giai đoạn thu thập.

Các record thường cần đối chiếu:

- Service instance: ID, tenant reference, service/plan ID, lifecycle status, provider resource ID, version.
- Binding: binding ID, instance ID, status, credential reference đã redact.
- Operation: operation ID, type, status, attempt, owner, lease, checkpoint và timestamps.
- Quota account/reservation: limit, committed, reserved, operation reference và reservation status.
- Outbox/inbox: event ID, operation ID, publish/consume status và timestamps.
- Idempotency record: key fingerprint, request fingerprint, stored result reference và expiry.
- Audit/state transition history nếu broker lưu riêng.

Ví dụ truy vấn minh họa trong read-only transaction:

~~~sql
BEGIN TRANSACTION READ ONLY;

SELECT instance_id, tenant_ref, service_id, plan_id,
       status, provider_resource_id, version, updated_at
FROM broker_service_instance
WHERE instance_id = :instance_id;

SELECT operation_id, operation_type, status, attempt,
       owner_id, lease_until, fencing_token,
       next_attempt_at, created_at, updated_at
FROM broker_operation
WHERE operation_id = :operation_id;

ROLLBACK;
~~~

Tên bảng/cột là ví dụ, không phải schema bắt buộc của Spring Cloud Open Service Broker. Dùng schema thực tế của dự án và tài khoản read-only. Nếu database không hỗ trợ cú pháp transaction trên, dùng cơ chế read-only tương đương do DBA quy định. Không chạy UPDATE, DELETE, manual unlock hoặc sửa quota trong lúc thu thập.

### Những điểm cần xác minh

- Instance có được tạo trước operation không?
- Operation và outbox có cùng transaction boundary không?
- Có reservation ACTIVE không? Nó gắn với operation nào?
- Có nhiều operation lifecycle active trên cùng instance không?
- Row version hoặc fencing token có tăng đúng không?
- Có transaction rollback/deadlock/lock timeout không?
- Outbox event đã publish nhưng consumer chưa xử lý, hay chưa publish?
- Idempotency record có cùng request fingerprint với lần retry không?

Một snapshot database là ảnh chụp tại một thời điểm. Ghi timestamp và isolation semantics nếu cần so sánh với provider inventory. Tránh chạy truy vấn quét toàn bảng hoặc join nặng trên primary trong giờ cao điểm; phối hợp DBA và dùng replica/read endpoint nếu có.

## 9. Thu thập bằng chứng từ provider

Provider là nguồn xác nhận actual resource state và kết quả API call. Thu thập theo provider account/project, region, resource ID và operation/request ID:

- Audit event hoặc activity log của provider.
- API request ID, job/operation ID và status.
- Resource describe/get response và timestamps.
- Inventory/list result có pagination và filter được ghi lại.
- Resource tags/labels/ownership metadata.
- IAM/authorization deny, quota exceeded, throttling và rate limit.
- Network/connectivity error, TLS failure hoặc DNS resolution evidence.
- Provider maintenance, incident hoặc regional degradation trong khoảng thời gian liên quan.

Phân biệt các kết quả:

| Provider result | Ý nghĩa điều tra |
|---|---|
| Accepted/in progress | Provider đã nhận công việc nhưng chưa có kết quả cuối |
| Succeeded | Provider xác nhận thao tác thành công; cần đối chiếu resource ID/state |
| Failed | Có lỗi cuối; lấy mã lỗi và request reference |
| Timeout/connection reset | Chưa biết provider có thực hiện side effect hay không |
| Not found | Có thể resource đã mất; kiểm tra account, region, ID và consistency |
| Access denied | Broker credential/role/policy có thể thiếu quyền |
| Rate limited | Cần xem Retry-After, concurrency và retry policy |

Không xem timeout là bằng chứng provider không nhận request. Không xem inventory list thiếu resource ngay sau create là bằng chứng create thất bại; provider có thể có eventual consistency. Hãy kiểm tra resource trực tiếp bằng ID hoặc provider operation reference nếu API hỗ trợ.

## 10. Thu thập bằng chứng từ Kubernetes hoặc Cloud Foundry

Nếu broker hoặc provider adapter chạy trên Kubernetes, cần lấy:

- Namespace, Deployment, ReplicaSet, Pod name và pod UID.
- Pod restart count, termination reason, exit code và previous container logs.
- Events quanh thời điểm incident.
- Readiness/liveness probe failures.
- Resource pressure, OOMKilled, CPU throttling và node conditions.
- Service/Ingress/NetworkPolicy liên quan đến broker hoặc worker.
- HPA/rollout history và thời điểm scale/replace pod.

Các lệnh dưới đây chỉ đọc thông tin; thay placeholder bằng namespace, pod và khoảng thời gian phù hợp:

~~~bash
kubectl get pods -n <namespace> -o wide
kubectl describe pod <pod-name> -n <namespace>
kubectl logs <pod-name> -n <namespace> --since=2h
kubectl logs <pod-name> -n <namespace> --previous
kubectl get events -n <namespace> --sort-by=.lastTimestamp
kubectl rollout history deployment/<deployment-name> -n <namespace>
~~~

Không đưa output có environment variable hoặc secret mount vào incident report. Pod description và event có thể chứa image, node, volume hoặc annotation nội bộ; chỉ chia sẻ phần cần thiết.

Với Cloud Foundry, thu thập app/process instance, route mapping, recent app logs, staging/crash events, health status và platform request/audit reference theo quyền operator. Không restart app hoặc restage chỉ để thử xem có hết lỗi không trước khi đã lưu evidence cần thiết.

## 11. Ghép timeline từ bốn lớp

Sau khi thu thập, tạo một timeline thống nhất. Mỗi dòng phải có timestamp UTC, nguồn, correlation/operation ID, event và evidence reference:

| UTC | Nguồn | ID liên kết | Sự kiện | Evidence |
|---|---|---|---|---|
| 10:00:00.120 | Platform | request p-17, instance i-42 | Gửi provision | EV-01 |
| 10:00:00.260 | Broker API | request b-91, instance i-42 | Xác thực và validate thành công | EV-02 |
| 10:00:00.410 | Broker DB | operation o-55 | Commit operation và reservation | EV-03 |
| 10:00:00.700 | Broker worker | worker w-2, attempt 1 | Claim operation | EV-04 |
| 10:00:01.050 | Provider | request pr-8 | Nhận lệnh tạo resource | EV-05 |
| 10:00:30.000 | Broker worker | worker w-2 | Timeout khi chờ provider | EV-06 |
| 10:01:00.000 | Provider | request pr-8 | Resource đã ACTIVE | EV-07 |

Ví dụ trên minh họa vì sao kết luận provision thất bại từ timeout worker có thể sai: provider đã hoàn tất sau đó. Broker cần reconcile resource và hoàn tất operation theo state machine.

Nếu timestamp lệch giữa các hệ thống, ghi cả timestamp gốc, offset đã ước lượng và độ tin cậy. Dùng request ID/operation ID để nối sự kiện khi clock skew khiến thứ tự timestamp không chắc chắn.

## 12. Phân tích distributed trace và metrics

Trace giúp thấy request đi qua ingress, application service, repository, provider adapter và worker. Tuy nhiên, async worker thường chạy trong một trace mới sau khi HTTP request đã kết thúc. Cần truyền operation ID và link trace context từ event/outbox sang worker trace.

Khi đọc trace:

- Tìm span có error status và dependency name.
- So sánh thời gian chờ queue với thời gian xử lý thực tế.
- Phân biệt lỗi ở broker code với lỗi ở provider call.
- Kiểm tra retry span và số lần gọi provider.
- Xác nhận trace ID có được liên kết qua async boundary không.
- Đối chiếu span với log và provider request ID.

Metrics giúp xác định phạm vi và thời điểm bắt đầu:

- Tỷ lệ 4xx/5xx theo endpoint và OSB error code.
- Provision/update/deprovision latency.
- Operation age, queue depth, retry count và stuck operation.
- Provider request latency, timeout, throttling và error rate.
- Database pool saturation, transaction duration, lock wait/deadlock.
- Worker concurrency, restart count và lease expiry.
- Quota rejection, reservation age và reconciliation findings.

Metric thường là dữ liệu tổng hợp, không đủ để xác định một instance cụ thể. Dùng metric để khoanh vùng khoảng thời gian/ảnh hưởng, sau đó dùng log, trace và state record để điều tra một operation.

## 13. Phân biệt lỗi ở từng lớp

Một số dấu hiệu giúp định hướng:

| Dấu hiệu | Lớp cần kiểm tra trước | Bằng chứng cần xác nhận |
|---|---|---|
| Platform không kết nối được broker | DNS, route, ingress, TLS, network policy | Platform/gateway log, ingress access log, certificate event |
| 401/403 | Authentication/authorization | Principal, credential rotation, security decision log |
| 400 hoặc lỗi parse | Request schema/serialization | Request đã redact, API version, validation result |
| 422 AsyncRequired | Sync/async capability | accepts_incomplete, execution policy, response body |
| 409 Conflict | Instance/operation state | Active operation, state version, idempotency fingerprint |
| 202 nhưng không tiến triển | Outbox, queue, worker, lease | Operation record, message status, worker logs |
| Worker timeout | Provider/network | Provider request ID, describe resource, timeout trace |
| 5xx từ broker | Application/database/provider adapter | Exception mapping, transaction, dependency health |
| Quota exceeded bất thường | Quota ledger/reservation | Committed, reserved, adjustment history |
| Resource còn sau deprovision | Provider cleanup/reconciliation | Provider inventory, delete job, ownership tags |

Đây là thứ tự khoanh vùng ban đầu, không phải kết luận tự động. Ví dụ 409 có thể do idempotency fingerprint conflict hoặc một active operation; cần đọc domain error và state record để phân biệt.

## 14. Bảo vệ dữ liệu nhạy cảm khi thu thập

Service broker có thể xử lý credentials và parameters nhạy cảm. Trước khi export hoặc chia sẻ evidence:

- Loại bỏ Authorization header, password, token, private key và secret value.
- Redact credential trong request/response body và provider payload.
- Thay tenant/customer identifier bằng pseudonymous reference nếu không cần tên thật.
- Không export toàn bộ database; chỉ lấy record và cột liên quan.
- Không đưa secret vào command line, shell history hoặc ticket.
- Giới hạn quyền truy cập evidence theo incident role.
- Ghi lại ai đã xem/export và thời hạn lưu theo policy.
- Giữ bản gốc trong kho bảo mật; chỉ chia sẻ bản đã redact.

Không xóa hoặc sửa log gốc để che dữ liệu. Nếu phát hiện secret đã bị ghi vào log, bảo toàn bản gốc theo quy trình incident, hạn chế quyền truy cập và chuyển sang quy trình xử lý lộ secret/rotation của tổ chức.

## 15. Phân biệt sự kiện, giả thuyết và kết luận

Trong incident report, đánh dấu rõ:

- **Fact:** có evidence trực tiếp hỗ trợ, ví dụ database operation status là RUNNING tại thời điểm snapshot.
- **Inference:** suy luận từ nhiều fact, ví dụ worker có thể đã mất lease trước khi ghi checkpoint.
- **Hypothesis:** khả năng cần kiểm tra, ví dụ provider đã tạo resource nhưng response bị mất.
- **Unknown:** dữ liệu chưa có, ví dụ provider audit log hết retention.

Ví dụ bảng giả thuyết:

| Giả thuyết | Bằng chứng ủng hộ | Bằng chứng phản bác/còn thiếu | Trạng thái |
|---|---|---|---|
| Provider tạo resource nhưng broker timeout | Provider request ID và resource ACTIVE | Chưa có log adapter sau response | Đang xác minh |
| Worker cũ ghi đè state | Lease expiry và fencing token tăng | Chưa có rejected update log | Chưa đủ bằng chứng |
| Quota bị giữ do reservation mồ côi | Reservation ACTIVE lâu, operation terminal | Chưa đối chiếu provider actual state | Có khả năng |

Không viết nguyên nhân là provider lỗi nếu mới chỉ thấy timeout. Ghi rõ điều gì đã được chứng minh và điều gì cần provider support hoặc DBA xác minh thêm.

## 16. Quy trình điều tra theo từng bước

Một runbook có thể thực hiện theo thứ tự:

1. **Mở incident:** ghi phạm vi, mức độ ảnh hưởng, thời gian và người điều tra.
2. **Chọn resource:** xác định service/plan/instance/binding và operation liên quan.
3. **Tạo correlation map:** nối platform request ID, broker request ID, operation ID, worker attempt và provider request/resource ID.
4. **Export platform evidence:** request/response, retries, polling và platform events.
5. **Export broker evidence:** ingress, application, worker, exception mapping, traces và metrics.
6. **Đọc state store:** instance, binding, operation, reservation, outbox và idempotency record bằng truy vấn read-only.
7. **Đọc provider evidence:** audit events, operation status, resource describe/inventory và quota/rate limit.
8. **Ghép timeline:** chuẩn hóa UTC, ghi clock skew và evidence reference.
9. **Kiểm tra giả thuyết:** xác nhận hoặc loại trừ từng giả thuyết bằng nguồn độc lập.
10. **Đánh giá ảnh hưởng:** resource/tenant nào bị tác động, có dữ liệu hoặc credential nào bị lộ không.
11. **Đề xuất hành động:** ghi rõ owner, rủi ro, điều kiện và cách xác minh sau hành động.
12. **Đóng incident:** lưu evidence, root cause, contributing factors, remediation reference và bài học.

Nếu sự cố vẫn đang diễn ra, tách việc thu thập khỏi quyết định giảm thiểu tác động. Người có quyền vận hành có thể cần thực hiện mitigation riêng, nhưng phải ghi thời điểm và hành động đó để phân biệt evidence trước và sau mitigation.

## 17. Khi nào cần chuyển cấp

Chuyển cho nhóm chuyên trách khi:

- Có dấu hiệu truy cập trái phép, credential exposure hoặc cross-tenant data access.
- Provider báo resource đã tạo/xóa nhưng broker state không thể reconcile.
- Database có deadlock, corruption, replication lag hoặc transaction bất thường.
- Nhiều tenant/region cùng gặp lỗi, có khả năng là platform-wide incident.
- Provider audit/request ID cho thấy lỗi phía control plane hoặc quota account.
- Có orphan resource chứa dữ liệu khách hàng hoặc không xác minh được owner.
- Bằng chứng thiếu do retention hoặc log pipeline bị gián đoạn.

Gói escalation cần gồm incident ID, thời gian UTC, phạm vi ảnh hưởng, service/plan/resource references đã pseudonymize, timeline, evidence IDs, request/operation/provider IDs cần thiết, giả thuyết đã kiểm tra và câu hỏi cụ thể gửi nhóm tiếp nhận. Không gửi credential hoặc raw customer payload.

## 18. Mẫu evidence checklist

Trước khi kết luận, kiểm tra các mục cần thiết:

- [ ] Đã ghi incident ID, scope và khoảng thời gian UTC.
- [ ] Đã xác định service ID, plan ID, instance/binding ID.
- [ ] Đã nối platform request với broker request/correlation ID.
- [ ] Đã thu request/response status và retry history.
- [ ] Nếu async, đã thu operation key, polling và worker attempts.
- [ ] Đã thu broker application/worker logs và distributed traces.
- [ ] Đã đọc instance, binding, operation, reservation và outbox state bằng read-only query.
- [ ] Đã thu provider request ID, audit event và actual resource state.
- [ ] Đã kiểm tra platform runtime/pod events nếu có liên quan.
- [ ] Đã ghi clock skew, missing logs và retention limitations.
- [ ] Đã redact secret và customer data trong bản chia sẻ.
- [ ] Đã lưu evidence source, collector, collected_at và checksum theo policy.
- [ ] Đã phân biệt fact, inference, hypothesis và unknown.
- [ ] Đã đánh giá phạm vi ảnh hưởng và yêu cầu escalation.

Checklist này là công cụ điều tra; không phải yêu cầu phải thu mọi nguồn cho mọi incident. Chỉ lấy dữ liệu phù hợp với triệu chứng, quyền truy cập và nguyên tắc tối thiểu cần thiết.

## 19. Ví dụ: provision báo timeout nhưng resource đã tồn tại

Giả sử platform báo provision instance inst-42 bị timeout. Điều tra theo operation:

1. Platform log cho thấy PUT provision được gửi một lần và client timeout sau 30 giây.
2. Broker ingress log cho thấy request đã qua authentication và validation.
3. Database có operation op-91 ở RUNNING, instance ở PROVISIONING và reservation storage còn ACTIVE.
4. Worker log cho thấy đã gọi provider create với request ID pr-8, sau đó HTTP client timeout.
5. Provider audit log cho thấy request pr-8 đã thành công; resource db-77 được tạo.
6. Provider describe xác nhận db-77 ACTIVE và ownership tag trỏ về inst-42.
7. Worker attempt mới đã claim operation nhưng chưa có provider resource ID trong checkpoint.

Từ các fact này có thể kết luận provider đã tạo resource, còn broker chưa ghi nhận kết quả do timeout giữa side effect và checkpoint. Hành động tiếp theo là để workflow reconcile resource theo ownership metadata và hoàn tất operation bằng cơ chế idempotent đã thiết kế. Không gửi một lệnh create mới chỉ vì worker cũ không ghi được checkpoint. Nếu remediation cần thay đổi state, thực hiện theo quy trình vận hành có audit riêng sau khi evidence đã được bảo toàn.

## 20. Những sai lầm thường gặp

- Chỉ xem log broker mà không lấy request/response từ platform.
- Chỉ xem operation status mà không kiểm tra provider actual state.
- Tìm theo instance ID nhưng bỏ qua operation key và provider request ID.
- So sánh timestamp khác timezone mà không chuẩn hóa.
- Cho rằng timeout đồng nghĩa provider không thực hiện side effect.
- Đọc database bằng query có thể khóa hoặc gây tải lớn trên primary.
- Bật log request body đầy đủ và làm lộ credentials.
- Chia sẻ raw logs hoặc database dump qua kênh không được bảo vệ.
- Sửa operation, release quota hoặc xóa provider resource trước khi lưu evidence.
- Xem inventory list nhất thời là nguồn xác nhận duy nhất.
- Gộp fact và giả thuyết thành một kết luận chắc chắn.
- Không ghi rõ nguồn, query, người thu thập và thời điểm export.
- Không lưu limitation khi pod/log đã hết retention.

## Kết luận

Chẩn đoán service broker đáng tin cậy cần ghép bằng chứng từ platform, broker/worker, database và provider trên cùng một timeline. Bắt đầu bằng incident scope và correlation map; thu request/response, operation attempts, state records, provider audit/resource state và runtime events theo quyền read-only. Bảo toàn bản gốc, ghi nguồn và thời điểm, chuẩn hóa UTC, redact credentials và phân biệt fact với giả thuyết. Đặc biệt với thao tác async, timeout hoặc worker restart, phải đối chiếu provider actual state trước khi kết luận thất bại hoặc lặp side effect. Một evidence package có cấu trúc giúp đội vận hành khoanh vùng nhanh, escalation đúng nhóm và phục hồi broker mà không làm mất dấu vết hoặc gây thêm tài nguyên trùng.
