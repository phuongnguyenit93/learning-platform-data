# Tránh thử lại thao tác xuất bản hoặc triển khai gây tác động lặp

Retry giúp pipeline phục hồi khi gặp lỗi tạm thời. Nhưng nhiều thao tác CI/CD tạo hoặc thay đổi trạng thái bên ngoài: publish package, push image, tạo release, gửi notification, chạy database migration, tạo deployment, chuyển traffic hoặc kích hoạt job nền. Nếu pipeline không biết lần gọi trước đã thực hiện đến đâu, retry có thể tạo bản phát hành trùng, ghi đè artifact, chạy migration hai lần, gửi thông báo lặp hoặc thực hiện side effect nhiều lần.

Điểm nguy hiểm là một request timeout hoặc mất kết nối không chứng minh thao tác chưa xảy ra. Server có thể đã commit thay đổi nhưng response bị mất trên đường về. Pipeline nhìn thấy lỗi trong khi hệ thống đích đã hoàn tất công việc. Retry mù quáng biến một lỗi truyền thông thành tác động lặp.

Cách thiết kế an toàn là xác định semantics của thao tác, dùng idempotency key hoặc deduplication khi có thể, lưu trạng thái operation bền vững, giới hạn retry và kiểm tra trạng thái hệ thống đích trước khi gửi lại. Nếu không thể chứng minh lần gọi trước chưa tạo side effect, hãy reconcile trước khi retry.

## 1. Vì sao retry thao tác publish hoặc deploy có thể nguy hiểm?

Một lệnh publish/deploy thường đi qua nhiều bước: xác thực, gửi request, hệ thống đích nhận yêu cầu, ghi trạng thái, thực thi side effect rồi trả response. Lỗi có thể xảy ra ở bất kỳ điểm nào.

Ví dụ pipeline gửi yêu cầu publish version 3.2.0. Registry đã lưu package thành công, nhưng kết nối bị reset trước khi pipeline nhận được HTTP response. Job kết thúc với trạng thái failed. Nếu retry bằng thao tác tạo mới, hệ thống có thể:

- Tạo thêm release record hoặc notification trùng.
- Ghi đè tag mutable đang trỏ sang artifact khác.
- Tạo hai deployment hoặc hai rollout cùng mục tiêu.
- Chạy lại migration hoặc hook có side effect.
- Tạo hai tài nguyên cloud nếu API không hỗ trợ idempotency.
- Gửi lại email, webhook hoặc sự kiện phát hành.
- Tăng version hoặc tạo thêm package ngoài dự kiến.
- Khiến trạng thái pipeline và trạng thái hệ thống đích không còn khớp.

### 1.1. Timeout không có nghĩa là thao tác thất bại

Giả sử pipeline gửi request đến deployment API:

1. Pipeline gửi yêu cầu triển khai release R42.
2. Server nhận request và bắt đầu xử lý.
3. Server tạo deployment và cập nhật trạng thái.
4. Response bị mất do network timeout.
5. Pipeline chỉ nhìn thấy timeout và đánh dấu job failed.

Deployment lúc này có thể đã chạy, đang chạy hoặc đã hoàn tất. Nếu gửi một request tạo deployment mới, pipeline có thể tạo operation thứ hai.

Đây là ambiguous outcome (kết quả chưa xác định): caller không biết thao tác trước đã được commit hay chưa. Cần truy vấn trạng thái theo operation ID hoặc đối chiếu trạng thái thực tế trước khi gửi lại.

~~~mermaid
sequenceDiagram
    participant P as CI Pipeline
    participant D as Deployment API
    participant C as Cluster
    P->>D: Create deployment R42
    D->>C: Apply desired state
    C-->>D: Accepted / progressing
    D--xP: Response bị mất / timeout
    Note over P: Pipeline không biết operation đã được tạo
    P->>D: Query status bằng operation ID
    D-->>P: R42 đang progressing hoặc succeeded
    Note over P,D: Theo dõi operation cũ, không tạo operation mới
~~~

### 1.2. Phân biệt lỗi trước khi nhận request và lỗi sau khi commit

| Tình huống | Caller biết gì? | Hành động an toàn |
|---|---|---|
| Validation trả lỗi trước khi xử lý | Request bị từ chối rõ ràng | Sửa input; không retry cùng payload sai |
| DNS/connect thất bại trước khi gửi request | Có cơ sở cho rằng server chưa nhận request | Có thể retry theo policy |
| Timeout khi đang gửi hoặc chờ response | Không chắc server đã nhận/commit chưa | Query operation hoặc reconcile trước |
| Server trả 5xx | Có thể lỗi trước hoặc sau commit tùy API | Dựa vào contract và idempotency; không mặc định retry |
| Server trả 429 kèm Retry-After | Bị giới hạn tốc độ theo phản hồi | Chờ theo chỉ dẫn; vẫn cần idempotency nếu thao tác tạo side effect |
| Response thành công nhưng pipeline bị hủy trước khi ghi state | Hệ thống đích có thể đã hoàn tất | Query trạng thái đích và cập nhật release record |
| Client retry do process restart | Lần trước có thể đã thành công | Dùng cùng operation/idempotency key |

Không thể phân loại mọi mã HTTP thành an toàn hay không an toàn nếu không biết semantics của API. Một HTTP 500 có thể được trả sau khi server đã commit; một timeout có thể xảy ra trước khi request rời máy. Hãy dùng contract của dịch vụ đích và bằng chứng quan sát được.

## 2. Phân loại thao tác theo khả năng retry

Trước khi thêm retry, hãy xác định thao tác thuộc loại nào.

| Loại thao tác | Ví dụ | Retry mặc định |
|---|---|---|
| Read-only | GET release status, đọc digest, truy vấn deployment | Thường an toàn nếu request không có side effect |
| Idempotent write | Đặt desired replica count về 4, cập nhật config về một giá trị xác định | Có thể retry cùng payload nếu API thực sự bảo đảm idempotency |
| Create có deduplication | Tạo deployment với idempotency key/operation ID duy nhất | Có thể retry cùng key và cùng payload |
| Create không có deduplication | Tạo release, package hoặc resource mới mỗi lần gọi | Không retry mù quáng |
| Append/event publish | Gửi message, webhook hoặc event mới | Cần event ID, deduplication hoặc transactional outbox |
| Non-idempotent business action | Thu tiền, hoàn tiền, gửi email, tạo hóa đơn | Chỉ retry khi có idempotency contract hoặc đã xác minh chưa thực hiện |
| Irreversible action | Xóa dữ liệu, rotate key, phát hành giao dịch bên ngoài | Cần quy trình phục hồi riêng và xác nhận trạng thái |

### 2.1. Idempotent và non-idempotent

Một thao tác là idempotent nếu thực hiện nhiều lần với cùng ý định và đầu vào không làm thay đổi kết quả cuối cùng sau lần đầu.

Ví dụ đặt cấu hình mong muốn:

~~~http
PUT /environments/staging/services/orders/config
Content-Type: application/json

{"replicas": 4, "featureFlag": "disabled"}
~~~

Nếu API có semantics thay thế trạng thái cấu hình bằng đúng payload đó, gửi lại cùng request có thể vẫn cho kết quả mong muốn là bốn replica và flag disabled.

Ngược lại, một lệnh tạo tài nguyên:

~~~http
POST /deployments
Content-Type: application/json

{"service": "orders", "version": "3.2.0"}
~~~

có thể tạo deployment mới ở mỗi lần gọi. Gửi hai lần có thể tạo hai deployment record hoặc kích hoạt hai rollout.

Không thể kết luận chỉ từ HTTP method. PUT thường được thiết kế idempotent, nhưng implementation vẫn có thể tạo side effect phụ; POST có thể idempotent nếu API hỗ trợ idempotency key. Cần kiểm tra contract thực tế.

### 2.2. Idempotency của trạng thái và idempotency của side effect

Một API có thể đưa tài nguyên về cùng trạng thái cuối cùng nhưng vẫn phát sinh side effect nhiều lần. Ví dụ apply manifest lần hai không đổi Pod template, nhưng script deploy lại gửi notification, chạy migration hook hoặc gọi webhook.

Cần xác định cả hai:

- **State idempotency:** trạng thái cuối cùng của tài nguyên có giống nhau khi gọi lặp không?
- **Effect idempotency:** các hành động bên ngoài như publish event, gửi email, charge payment hoặc migration có bị lặp không?

Một deployment an toàn cần kiểm soát cả trạng thái lẫn side effect.

## 3. Idempotency key: nhận diện cùng một ý định

Idempotency key là một định danh duy nhất cho một ý định nghiệp vụ hoặc operation. Caller tạo key một lần, lưu bền vững và dùng lại key đó cho mọi lần retry của cùng operation.

Ví dụ:

~~~http
POST /releases
Idempotency-Key: release-orders-3.2.0-commit-a1b2c3d
Content-Type: application/json

{
  "service": "orders",
  "version": "3.2.0",
  "artifactDigest": "sha256:abc123..."
}
~~~

Nếu request đầu đã được xử lý nhưng response bị mất, request lặp với cùng key có thể nhận lại kết quả đã lưu thay vì tạo release thứ hai.

### 3.1. Quy tắc thiết kế key

Key nên:

- Đại diện cho một operation cụ thể, không chỉ cho một lần chạy job.
- Ổn định qua các lần retry của cùng operation.
- Khác nhau khi người dùng thực sự yêu cầu operation mới.
- Có phạm vi rõ ràng như tenant, service, environment hoặc resource.
- Không chứa secret, password, token hay dữ liệu cá nhân.
- Được lưu cùng release/deployment record để điều tra.

Một key có thể kết hợp loại operation, service, environment, artifact digest và release request ID. Tránh chỉ dùng pipeline run ID nếu rerun tạo run ID mới nhưng vẫn đại diện cùng một release request; điều đó sẽ làm mất khả năng deduplicate qua rerun.

### 3.2. Cùng key phải đi cùng cùng payload

Server nên lưu fingerprint/hash của payload đầu tiên gắn với key. Nếu caller gửi cùng key nhưng payload khác, server nên từ chối với conflict thay vì âm thầm dùng kết quả cũ hoặc tạo side effect mới.

| Request | Key | Payload | Kết quả mong đợi |
|---|---|---|---|
| Lần đầu | K-42 | Deploy digest A lên staging | Tạo operation K-42 |
| Retry sau timeout | K-42 | Cùng digest A, cùng staging | Trả trạng thái/kết quả của K-42 |
| Gửi nhầm payload khác | K-42 | Digest B hoặc production | Conflict; không tạo side effect |
| Release mới có chủ đích | K-43 | Digest B lên staging | Operation mới |

### 3.3. Server cần lưu idempotency record bền vững

Một implementation phía server thường cần lưu:

- Key và scope của key.
- Payload fingerprint.
- Trạng thái operation.
- Operation/resource ID được tạo.
- Response hoặc kết quả có thể trả lại.
- Thời điểm tạo, cập nhật và hết hạn.
- Chủ thể tạo operation.

Việc ghi idempotency record và side effect cần có ranh giới transaction hoặc cơ chế phục hồi nhất quán. Nếu server tạo tài nguyên trước rồi mới lưu key, crash ở giữa có thể khiến retry tạo trùng. Nếu lưu key là completed trước khi side effect thành công, caller có thể nhận kết quả thành công giả.

## 4. State machine cho operation có side effect

Đừng chỉ lưu job status là success/failed. Một operation publish hoặc deploy nên có trạng thái riêng ở hệ thống đích.

~~~mermaid
stateDiagram-v2
    [*] --> Requested
    Requested --> InProgress: Nhận request hợp lệ
    InProgress --> Succeeded: Side effect hoàn tất
    InProgress --> Failed: Thất bại chắc chắn và không commit
    InProgress --> Unknown: Mất kết nối / timeout, chưa xác định
    Unknown --> InProgress: Reconcile xác nhận vẫn đang chạy
    Unknown --> Succeeded: Query xác nhận đã hoàn tất
    Unknown --> Failed: Query xác nhận chưa commit hoặc đã dừng an toàn
    Failed --> Requested: Tạo operation mới sau khi sửa điều kiện
    Succeeded --> [*]
~~~

Trạng thái Unknown rất quan trọng. Không nên chuyển Unknown thành Failed chỉ vì client timeout. Nếu hệ thống đích không có API query operation, cần đối chiếu tài nguyên đã tạo, artifact digest, release record hoặc audit log trước khi quyết định gửi lại.

### 4.1. Tránh trạng thái “đã gửi” nhưng không có dấu vết

Pipeline nên lưu operation ID ngay khi server trả hoặc cung cấp ID có thể xác định trước. Nếu client mất response trước khi biết ID, idempotency key có thể dùng để query lại operation. Hãy lưu key và payload fingerprint trước khi gửi request, không chỉ sau khi job thành công.

### 4.2. Xử lý request đồng thời

Hai job có thể retry cùng operation đồng thời do rerun, webhook trùng hoặc worker phục hồi. Server cần atomic claim/unique constraint trên idempotency key để chỉ một request tạo operation; request còn lại nhận trạng thái đang xử lý hoặc kết quả đã lưu.

Chỉ kiểm tra key trong memory của một process là chưa đủ nếu server có nhiều replica hoặc restart. Deduplication cần dùng storage chia sẻ và thao tác nguyên tử.

## 5. Exactly-once là mục tiêu khó; thiết kế hiệu ứng đúng một lần

Trong hệ thống phân tán, caller có thể không biết server đã commit hay chưa khi response bị mất. Mạng có thể gửi lại request; consumer có thể nhận lại message; process có thể crash giữa side effect và ghi nhận kết quả. Vì vậy, “exactly once” ở toàn bộ chuỗi thường không thể được bảo đảm chỉ bằng một retry setting.

Cách triển khai thực tế thường là:

- Delivery có thể at-least-once (một thông điệp có thể được giao nhiều lần).
- Mỗi event/operation có ID ổn định.
- Consumer deduplicate theo ID bằng storage bền vững.
- Ghi nhận business effect và trạng thái đã xử lý trong cùng transaction khi có thể.
- Nếu gọi hệ thống ngoài, dùng idempotency contract của provider hoặc quy trình reconciliation.
- Retry có giới hạn và không tạo một operation ID mới cho cùng ý định.

Mục tiêu là đạt một business effect duy nhất dù request/message có thể được giao nhiều lần.

## 6. Publish artifact: tránh tạo bản phát hành hoặc ghi đè tag trùng

Publish artifact có nhiều semantics khác nhau. Push một OCI image layer có thể được registry xử lý theo digest nội dung; gắn hoặc di chuyển tag lại là thao tác trạng thái riêng. Publish một package version có thể bị từ chối nếu version đã tồn tại, hoặc registry cho phép overwrite tùy policy.

### 6.1. Version phát hành nên bất biến

Với package version đã phát hành, nên áp dụng quy tắc không ghi đè. Nếu version 3.2.0 đã tồn tại, retry cần xác minh artifact hiện có có cùng digest hay không:

- Nếu digest khớp, xem operation là đã hoàn tất và tiếp tục.
- Nếu digest khác, dừng và điều tra; không overwrite để “sửa” trạng thái.
- Nếu package chưa tồn tại và registry xác nhận chưa publish, có thể tiếp tục operation theo cơ chế an toàn.

Không dùng version cố định có thể ghi đè cho mọi lần build. Dùng version/release identity rõ ràng và lưu digest.

### 6.2. Container image: tag và digest

Tag như orders:3.2.0 hoặc orders:latest có thể được di chuyển tùy registry policy. Digest xác định nội dung image. Khi retry push:

1. Kiểm tra image manifest theo tag/digest hiện có.
2. So sánh digest với artifact đã build.
3. Nếu cùng digest, không cần tạo một release khác chỉ để lặp push.
4. Nếu tag trỏ đến digest khác, dừng và xử lý conflict.
5. Deploy bằng digest thay vì tag mutable.

Ví dụ kiểm tra image theo digest bằng công cụ registry phù hợp:

~~~bash
docker build -t registry.example.com/orders:3.2.0 .
docker push registry.example.com/orders:3.2.0

# Lấy digest từ kết quả push hoặc registry metadata.
# Khi retry, truy vấn tag/digest trước khi push lại.
docker buildx imagetools inspect registry.example.com/orders:3.2.0
~~~

Lệnh inspect chỉ là ví dụ truy vấn; cách lấy digest phụ thuộc công cụ và registry. Không giả định việc push lại tag sẽ an toàn nếu tag có thể ghi đè.

### 6.3. Package registry

Với npm, Maven, NuGet hoặc registry nội bộ, cần hiểu policy về version đã publish. Một số registry không cho overwrite version; một số hệ thống nội bộ có thể cho phép. Pipeline nên:

- Dùng version duy nhất cho release.
- Kiểm tra package/version đã tồn tại.
- So sánh checksum hoặc metadata trước khi coi là thành công.
- Không xóa rồi publish lại cùng version như cách retry.
- Lưu registry URL, package coordinates, version và digest/checksum vào release record.

## 7. Deploy: declarative apply và imperative side effect

Triển khai theo desired state thường có thể lặp an toàn hơn thao tác imperative tạo mới mỗi lần.

Ví dụ khai báo mong muốn:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders
spec:
  replicas: 4
  template:
    spec:
      containers:
        - name: orders
          image: registry.example.com/orders@sha256:abc123...
~~~

Áp dụng cùng manifest bằng cơ chế declarative có thể đưa cluster về cùng desired state. Tuy nhiên, các hook, migration, notification, Job tạo một lần hoặc script phụ vẫn có thể tạo side effect lặp. Declarative apply không tự làm cho mọi phần của release idempotent.

### 7.1. Desired-state reconciliation

Với GitOps hoặc controller, pipeline cập nhật desired state có version và controller liên tục reconcile actual state về desired state. Retry cập nhật cùng desired state thường ít rủi ro hơn tạo một deployment operation mới mỗi lần.

Dù vậy cần lưu ý:

- Hook trước/sau deploy có thể chạy lại.
- Kubernetes Job có thể tạo execution mới tùy tên, TTL và cơ chế controller.
- Helm hook có thể thực thi lệnh migration hoặc thao tác ngoài.
- Script imperative có thể tạo resource mới mỗi lần.
- Một số controller chỉ bảo đảm trạng thái tài nguyên, không bảo đảm side effect của ứng dụng chỉ xảy ra một lần.

### 7.2. Tách deploy state khỏi release side effects

Nên tách các bước:

1. Xác định artifact digest và release ID.
2. Cập nhật desired state của deployment.
3. Chờ rollout theo deployment ID/revision.
4. Chạy post-deployment validation có operation ID riêng.
5. Chỉ gửi notification hoặc ghi release announcement sau khi xác nhận trạng thái cuối.
6. Nếu notification thất bại, retry notification theo event ID; không chạy lại toàn bộ deploy.

## 8. Database migration và hook triển khai

Database migration là thao tác có side effect rõ ràng. Một script có thể thêm cột, backfill dữ liệu, tạo index hoặc thay đổi constraint. Nếu client timeout sau khi database commit, chạy lại migration có thể lỗi hoặc thay đổi dữ liệu thêm lần nữa.

Các biện pháp:

- Dùng migration version/ID duy nhất và migration ledger.
- Đánh dấu migration trong cùng transaction với DDL/DML khi database hỗ trợ.
- Thiết kế migration idempotent nếu phù hợp, ví dụ kiểm tra trạng thái schema trước khi thêm đối tượng.
- Không chỉ dựa vào điều kiện “object đã tồn tại”; cần xác minh object đúng định nghĩa mong muốn.
- Backfill theo batch với checkpoint và điều kiện tiếp tục.
- Dùng unique constraint hoặc idempotency key để ngăn ghi trùng.
- Tách expand migration khỏi contract migration.
- Không chạy migration từ mọi replica khi ứng dụng khởi động; dùng job/migration runner có khóa điều phối.

Ví dụ bảng migration ledger:

~~~sql
CREATE TABLE schema_migrations (
    migration_id VARCHAR(200) PRIMARY KEY,
    checksum VARCHAR(128) NOT NULL,
    applied_at TIMESTAMP NOT NULL
);
~~~

Trước khi chạy migration, runner kiểm tra migration ID và checksum. Nếu đã áp dụng với cùng checksum, coi là hoàn tất. Nếu cùng ID nhưng checksum khác, dừng và yêu cầu điều tra; không chạy lại một nội dung đã bị thay đổi dưới cùng định danh.

## 9. Message, webhook và notification: dùng event ID và outbox

Gửi message hoặc webhook thường là at-least-once. Nếu producer gửi thành công nhưng không nhận ack, nó có thể gửi lại. Consumer cần deduplicate theo event ID hoặc business key.

Một consumer có thể lưu bảng đã xử lý:

~~~sql
CREATE TABLE processed_events (
    consumer_name VARCHAR(100) NOT NULL,
    event_id VARCHAR(200) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Trong transaction xử lý event, consumer ghi event ID và cập nhật business state. Nếu event ID đã tồn tại, không thực hiện business effect lần nữa.

### 9.1. Transactional outbox

Khi ứng dụng vừa cập nhật database vừa cần publish event, ghi business change và outbox record trong cùng transaction. Một publisher đọc outbox và gửi event; nếu gửi lại, consumer deduplicate theo event ID.

Outbox không làm message broker thành exactly-once. Nó giúp tránh mất liên kết giữa database commit và publish request; consumer vẫn cần idempotency/deduplication.

### 9.2. Webhook và notification

Khi gửi webhook hoặc email phát hành:

- Tạo event ID ổn định.
- Lưu trạng thái queued/sent/failed/unknown.
- Dùng idempotency contract của provider nếu có.
- Nếu provider không hỗ trợ deduplication, query trạng thái hoặc chấp nhận rằng không thể chứng minh không gửi trùng sau timeout.
- Tách notification khỏi deploy job để lỗi email không khiến pipeline deploy chạy lại.

## 10. Chính sách retry: chỉ retry khi biết thao tác an toàn

Một policy nên phân loại lỗi thành ít nhất bốn nhóm:

| Nhóm lỗi | Ví dụ | Hành động |
|---|---|---|
| Permanent failure | Payload sai, version conflict, permission denied, policy reject | Dừng; sửa nguyên nhân, không retry tự động |
| Transient failure | Rate limit, service unavailable, connection reset đã xác định trước khi gửi | Retry có giới hạn và backoff nếu operation an toàn |
| Ambiguous outcome | Timeout sau khi gửi request, mất response sau commit có thể xảy ra | Query operation/reconcile; chỉ retry cùng idempotency key nếu API hỗ trợ |
| Partial completion | Một số resource đã tạo, bước tiếp theo thất bại | Đọc trạng thái từng resource và tiếp tục từ checkpoint; không chạy lại toàn bộ chuỗi |

### 10.1. Exponential backoff và jitter

Khi lỗi tạm thời và thao tác có thể retry, exponential backoff giúp giảm áp lực lên dịch vụ:

~~~text
delay = min(max_delay, base_delay * 2^attempt)
actual_delay = random(0, delay)
~~~

Jitter ngẫu nhiên giúp nhiều pipeline không cùng retry tại một thời điểm. Nếu server trả Retry-After, tôn trọng hướng dẫn đó theo policy. Đặt giới hạn số lần retry và tổng thời gian chờ.

Backoff không làm một thao tác non-idempotent trở nên an toàn. Nó chỉ điều chỉnh thời điểm gửi lại.

### 10.2. Retry budget và giới hạn thời gian

Cần giới hạn:

- Số lần retry tối đa.
- Tổng thời gian operation.
- Thời gian chờ giữa các lần thử.
- Số operation đồng thời.
- Retry budget theo dịch vụ hoặc pipeline.
- Số lần retry lồng nhau giữa client, SDK, job và workflow.

Nếu mỗi lớp tự retry ba lần, ba lớp lồng nhau có thể tạo đến 27 request cho một operation. Chọn một lớp chịu trách nhiệm retry hoặc phối hợp budget rõ ràng.

### 10.3. Không retry lỗi validation và authorization

Một request sai schema, thiếu quyền, artifact conflict hoặc vi phạm policy thường không tự hết khi gửi lại. Retry liên tục chỉ tạo log nhiễu và tải không cần thiết. Dừng, hiển thị lỗi và yêu cầu sửa đầu vào hoặc quyền.

## 11. Reconcile trước khi retry

Khi outcome không rõ, thứ tự an toàn thường là:

1. Giữ nguyên idempotency key/operation ID và payload ban đầu.
2. Query API trạng thái theo key/operation ID.
3. Nếu operation đang chạy, tiếp tục poll với backoff; không tạo operation mới.
4. Nếu đã thành công, xác minh resource/digest và đánh dấu pipeline step hoàn tất.
5. Nếu thất bại chắc chắn trước commit, sửa điều kiện hoặc retry theo policy.
6. Nếu trạng thái không xác định, đối chiếu registry, deployment controller, audit log hoặc resource state.
7. Chỉ tạo operation mới khi đã chứng minh operation cũ không còn tạo side effect và có quyết định rõ ràng.

### 11.1. Poll status khác retry create

Request tạo operation:

~~~http
POST /deployments
Idempotency-Key: deploy-orders-prod-release-42
~~~

Request truy vấn trạng thái:

~~~http
GET /operations/deploy-orders-prod-release-42
~~~

Khi POST timeout, hãy GET trạng thái operation trước. Không gửi POST với key mới chỉ để xem hệ thống có phản hồi hay không.

### 11.2. Khi API đích không có idempotency key hoặc operation status

Có thể phải reconcile qua tài nguyên đích:

- Registry: package version/tag/digest đã tồn tại chưa?
- Kubernetes: Deployment revision, image digest và rollout status là gì?
- Cloud API: resource ID, client token hoặc operation record nào được tạo?
- Release platform: release ID/version có tồn tại chưa?
- Database: migration ledger, schema và checkpoint hiện tại là gì?
- Message broker: event ID/offset hoặc consumer ledger đã ghi nhận chưa?

Nếu không có cách xác minh đáng tin cậy, dừng retry tự động và chuyển sang xử lý có người điều tra. Không đoán rằng timeout nghĩa là chưa thực hiện.

## 12. Ví dụ: publish package có kiểm tra trước khi retry

Giả sử pipeline publish package coordinates và version đã xác định. Script có thể tuân theo logic:

~~~text
operation_key = release_request_id
expected_digest = digest_of_built_artifact

status = registry.lookup(package, version)

if status == NOT_FOUND:
    publish_once(package, version, artifact, operation_key)
    verify_registry_digest(package, version, expected_digest)

else if status.digest == expected_digest:
    mark_publish_complete()

else:
    stop_with_conflict()
~~~

Đây là pseudocode, không phải API cụ thể. Nếu registry hỗ trợ idempotency key, truyền cùng key cho lần retry. Nếu registry không hỗ trợ, kiểm tra version/digest trước khi publish và coi conflict digest là lỗi cần điều tra.

Không nên xóa package version đã tồn tại rồi publish lại cùng version như một cách khôi phục. Việc đó phá vỡ tính bất biến và có thể làm consumer nhận nội dung khác nhau dưới cùng coordinates.

## 13. Ví dụ: deploy bằng operation ID và reconcile

Một deployment client nên tách request tạo operation khỏi truy vấn trạng thái:

~~~python
def ensure_deployment(api, operation_key, desired):
    operation = api.get_operation(operation_key)

    if operation is None:
        try:
            operation = api.create_deployment(
                desired_state=desired,
                idempotency_key=operation_key,
            )
        except TimeoutError:
            # Request có thể đã được server commit.
            operation = api.get_operation(operation_key)
            if operation is None:
                raise RuntimeError(
                    "Deployment outcome unknown; reconcile before retry"
                )

    while operation.status in {"queued", "running"}:
        wait_with_backoff()
        operation = api.get_operation(operation_key)

    if operation.status == "succeeded":
        verify_runtime_digest(desired["artifact_digest"])
        return operation

    if operation.status == "failed":
        raise RuntimeError(operation.error)

    raise RuntimeError("Deployment requires manual reconciliation")
~~~

Ví dụ giả định API hỗ trợ query bằng operation key và create có idempotency key. Với API thật, cần dùng đúng contract, authentication, timeout, polling interval và error model của nhà cung cấp. Nếu operation status là unknown, không tạo key mới tự động.

## 14. Ví dụ pipeline: không rerun toàn bộ deploy chỉ vì notification lỗi

Nên tách publish, deploy, verify và notification thành các bước có trạng thái riêng. Ví dụ cấu trúc:

~~~yaml
jobs:
  publish:
    steps:
      - name: Publish immutable artifact
        run: ./scripts/publish-with-idempotency.sh

  deploy:
    needs: publish
    steps:
      - name: Reconcile deployment operation
        run: ./scripts/ensure-deployment.sh

  verify:
    needs: deploy
    steps:
      - name: Verify runtime digest and smoke checks
        run: ./scripts/verify-release.sh

  notify:
    needs: verify
    steps:
      - name: Send release notification using event ID
        run: ./scripts/send-notification-once.sh
~~~

Đây là cấu trúc minh họa. Mỗi script cần lưu operation/event ID và có cơ chế reconcile tương ứng. Nếu notification thất bại, chỉ xử lý notification theo event ID; không rerun job deploy. Nếu deploy timeout, job deploy truy vấn operation cũ; không tạo deployment mới.

Với GitHub Actions hoặc nền tảng tương tự, việc rerun failed job có thể tạo lại side effect nếu script không idempotent. Rerun một job không tự động bảo đảm nền tảng đích nhận diện đó là cùng operation.

## 15. Chống retry lặp ở nhiều lớp

Một thao tác có thể được retry ở nhiều nơi:

- Workflow rerun hoặc job retry.
- Script shell tự retry.
- SDK/HTTP client retry.
- Reverse proxy/service mesh retry request.
- Server queue retry message.
- Deployment controller reconcile desired state.
- Operator bấm chạy lại thủ công.

Nếu không thống nhất, một thao tác có thể bị nhân số lần gọi. Hãy ghi rõ lớp nào sở hữu retry và lớp nào chỉ quan sát trạng thái.

| Lớp | Vai trò phù hợp |
|---|---|
| CI workflow | Điều phối operation, lưu ID, quyết định tiếp tục hay dừng |
| Client/SDK | Retry lỗi transient chỉ khi API semantics cho phép |
| API server | Deduplicate theo key, lưu operation state và trả kết quả ổn định |
| Queue/consumer | Delivery có thể lặp; consumer deduplicate theo event ID |
| Controller | Reconcile desired state thay vì tạo operation mới liên tục |
| Operator | Điều tra Unknown/Conflict và phê duyệt hành động thủ công |

Không để workflow retry cả chuỗi nếu chỉ một bước phụ thất bại. Thiết kế checkpoint và job boundary giúp tiếp tục đúng bước chưa hoàn tất.

## 16. Concurrency control và khóa operation

Hai pipeline có thể cùng publish version hoặc deploy cùng service/environment. Idempotency key ngăn lặp cùng operation, nhưng chưa chắc ngăn hai operation khác nhau xung đột.

Cần bổ sung concurrency control:

- Unique constraint cho package coordinates/version hoặc release ID.
- Lock theo service/environment khi thao tác deploy không thể chạy song song.
- Compare-and-swap hoặc resource version để tránh ghi đè trạng thái mới hơn.
- Deployment queue/lease có TTL và cơ chế phục hồi khi worker chết.
- Kiểm tra desired state trước khi apply.
- Conflict response rõ ràng nếu operation khác đang sở hữu resource.

Lock không thay thế idempotency. Lock ngăn thao tác cạnh tranh; idempotency xử lý request lặp của cùng ý định. Hệ thống cần cả hai khi có nhiều pipeline và retry.

## 17. Timeout, cancellation và trạng thái Unknown

Timeout thường chỉ dừng việc caller chờ response. Nó không nhất thiết hủy operation ở server. Tương tự, cancel pipeline không bảo đảm deployment hoặc publish đã dừng.

Khi cancel hoặc timeout:

1. Ghi operation ID và thời điểm.
2. Query trạng thái server.
3. Nếu operation đang chạy, dùng API cancel chính thức nếu được phép và semantics rõ.
4. Query lại để xác nhận cancellation đã hoàn tất.
5. Kiểm tra resource thực tế và side effect đã xảy ra.
6. Chỉ giải phóng lock hoặc bắt đầu operation mới khi trạng thái đã rõ.

Không xóa lock/lease chỉ vì client process đã kết thúc; operation phía server có thể vẫn chạy. Lease cần TTL, fencing token hoặc cơ chế ownership để worker cũ không tiếp tục ghi sau khi quyền sở hữu đã chuyển.

## 18. Observability cho retry và side effect

Mỗi lần gọi cần có thông tin đủ để nối các lần thử vào cùng operation:

- Operation ID và idempotency key (có thể mask/hash khi hiển thị).
- Pipeline run ID, job ID, workflow revision và commit SHA.
- Artifact version/digest hoặc deployment target.
- Attempt number, retry reason và backoff delay.
- Request ID, response code, server operation ID.
- Trạng thái trước/sau và thời điểm.
- Side effect được xác nhận: resource created, package published, event emitted, deployment completed.
- Kết quả reconciliation và nguồn bằng chứng.

Các metric hữu ích:

- Retry rate theo operation type.
- Tỷ lệ retry thành công và retry dẫn đến duplicate/conflict.
- Số operation ở trạng thái Unknown quá lâu.
- Thời gian từ request đến terminal state.
- Số lần publish/deploy trùng bị deduplicate.
- Số pipeline rerun nhưng operation đã thành công.
- Tỷ lệ operation cần manual reconciliation.
- Retry budget consumption và số request do retry tạo thêm.

Không log raw idempotency secret, token, password hoặc payload nhạy cảm. Key thường không phải credential, nhưng vẫn có thể là định danh nội bộ cần giới hạn truy cập.

## 19. Những anti-pattern thường gặp

| Anti-pattern | Rủi ro | Cách làm tốt hơn |
|---|---|---|
| Retry mọi lỗi 5xx/timeout | Request trước có thể đã commit side effect | Query operation và reconcile |
| Tạo idempotency key mới mỗi lần retry | Server coi mỗi lần là operation mới | Lưu và dùng lại key của cùng ý định |
| Dùng cùng key cho payload khác | Kết quả cũ có thể bị áp dụng sai | So sánh payload fingerprint và trả conflict |
| Rerun toàn workflow khi notification lỗi | Publish/deploy bị thực hiện lại | Tách job và retry notification riêng |
| Dùng version/tag mutable cho release | Artifact bị ghi đè dưới cùng tên | Version bất biến, digest và registry policy |
| Retry migration không có ledger/checkpoint | DDL/DML hoặc backfill bị lặp | Migration ID, checksum, transaction và checkpoint |
| Coi timeout là cancel | Server vẫn tiếp tục side effect | Query/cancel operation rồi xác nhận trạng thái |
| Chỉ lưu job success/failed | Không phân biệt Unknown và Partial completion | State machine cho operation |
| Retry lồng nhau ở nhiều lớp | Request nhân lên, gây quá tải và duplicate | Một retry owner và retry budget |
| Dùng lock nhưng không có fencing | Worker cũ có thể tiếp tục ghi sau khi lease hết | Lease/fencing token và compare-and-swap |
| Giả định declarative apply không có side effect | Hook và script vẫn có thể chạy lặp | Tách state reconciliation khỏi side-effect steps |
| Không đối chiếu trạng thái đích | Pipeline và hệ thống đích lệch nhau | Reconciliation và release record |

## 20. Checklist thiết kế publish/deploy retry an toàn

### Trước khi bật retry

- [ ] Đã xác định thao tác read-only, idempotent write hay non-idempotent side effect.
- [ ] Đã đọc contract của API về timeout, retry, idempotency và error response.
- [ ] Đã phân biệt lỗi chắc chắn chưa commit với ambiguous outcome.
- [ ] Có idempotency key/operation ID ổn định cho cùng một ý định.
- [ ] Cùng key luôn gắn với cùng payload fingerprint.
- [ ] Server deduplicate nguyên tử và lưu operation state bền vững.
- [ ] Có API query trạng thái hoặc cách reconcile đáng tin cậy.
- [ ] Side effect bên ngoài có event ID, idempotency contract hoặc compensating plan.

### Khi publish artifact

- [ ] Version/coordinates không bị ghi đè sau khi phát hành.
- [ ] Retry kiểm tra package/version và digest hiện có.
- [ ] Digest khác với artifact mong đợi tạo conflict và dừng pipeline.
- [ ] Không xóa package/tag đã publish để retry cùng version.
- [ ] Release record lưu artifact digest và operation ID.

### Khi deploy

- [ ] Desired state có thể reconcile và được version hóa.
- [ ] Deploy operation có ID ổn định; timeout sẽ query trạng thái cũ.
- [ ] Migration, hook, notification và side effect được tách khỏi apply trạng thái.
- [ ] Có concurrency control theo service/environment khi cần.
- [ ] Cancel/timeout được xác minh ở hệ thống đích.
- [ ] Post-deploy verification xác nhận runtime digest và hành vi thực tế.

### Chính sách retry và vận hành

- [ ] Retry chỉ áp dụng cho lỗi transient và operation an toàn.
- [ ] Permanent failure không bị retry tự động.
- [ ] Ambiguous outcome chuyển sang reconcile, không tạo operation mới.
- [ ] Có exponential backoff, jitter, max attempts, deadline và retry budget.
- [ ] Không có retry lồng nhau gây nhân request.
- [ ] Logs/metrics nối attempt với operation ID và resource.
- [ ] Có quy trình manual reconciliation cho trạng thái Unknown hoặc Conflict.
- [ ] Runbook mô tả cách xác minh side effect trước khi bấm rerun.

Retry giúp pipeline chịu được lỗi tạm thời, nhưng không làm một thao tác có side effect trở nên an toàn. Publish và deploy cần định danh operation ổn định, idempotency/deduplication ở hệ thống đích, trạng thái bền vững và khả năng reconcile sau timeout. Khi chưa biết request trước đã commit hay chưa, truy vấn trạng thái và xác minh tài nguyên trước khi gửi lại. Nhờ đó pipeline có thể phục hồi từ lỗi mạng hoặc runner mà không tạo thêm release, deployment, migration hay giao dịch ngoài ý muốn.
