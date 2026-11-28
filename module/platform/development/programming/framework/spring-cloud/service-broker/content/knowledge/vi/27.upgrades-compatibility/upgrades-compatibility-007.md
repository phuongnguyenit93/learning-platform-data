# Di chuyển kho trạng thái và dữ liệu credentials

## Vì sao migration của service broker cần được kiểm soát chặt?

Service broker lưu trạng thái của các service instance, binding, operation, idempotency key và ánh xạ đến tài nguyên provider. Đồng thời, broker phải quản lý nhiều loại thông tin xác thực: credential mà ứng dụng consumer nhận sau bind, credential broker dùng để gọi provider, và thông tin xác thực giữa platform với broker. Khi chuyển database, đổi secret manager, thay KMS hoặc chuyển môi trường triển khai, tất cả dữ liệu này phải tiếp tục khớp với tài nguyên thật.

Một lần migration chỉ sao chép được các hàng database nhưng bỏ sót secret reference có thể khiến binding vẫn ở trạng thái `BOUND` trong broker nhưng ứng dụng không còn lấy được password. Ngược lại, nếu secret đã được chuyển nhưng binding ledger bị mất, broker có thể không biết secret đó thuộc `binding_id` nào để unbind hoặc rotation. Nếu restore database về thời điểm cũ hơn provider side effect, broker có thể tạo tài nguyên trùng khi retry.

Với `SPRING_CLOUD_SERVICE_BROKER`, migration cần bảo toàn đồng thời:

- **Identity:** `instance_id`, `binding_id`, service/plan ID và consumer reference.
- **Lifecycle state:** trạng thái instance, binding, operation và checkpoint.
- **Provider mapping:** provider account, resource ID, job ID và ownership marker.
- **Idempotency:** operation ID, request fingerprint và provider idempotency key.
- **Credential access:** secret reference, version, encryption metadata và quyền đọc.
- **Auditability:** lịch sử migration, actor, thời điểm, watermark và kết quả xác minh.

Mục tiêu không phải chỉ chuyển dữ liệu sang nơi lưu mới. Sau cutover, broker phải tiếp tục xử lý request OSB API và các operation đang chạy mà không mất mapping, cấp nhầm credential, tạo side effect trùng hoặc làm lộ secret.

## Phân loại dữ liệu trước khi di chuyển

Trước khi chọn công cụ, hãy lập inventory và xác định dữ liệu nào nằm trong state store, dữ liệu nào nằm trong secret manager và dữ liệu nào thuộc provider.

| Nhóm dữ liệu | Ví dụ | Nơi lưu phù hợp | Yêu cầu khi migration |
|---|---|---|---|
| Service instance metadata | `instance_id`, service ID, plan ID, state, context, provider resource reference. | Database broker. | Giữ nguyên identity và quan hệ. |
| Binding metadata | `binding_id`, `instance_id`, consumer reference, binding state. | Database broker. | Giữ mapping chính xác tới instance và provider binding. |
| Operation ledger | Operation ID, loại thao tác, state, step, retry count, provider job ID. | Database broker. | Không làm mất operation chưa terminal hoặc checkpoint. |
| Idempotency metadata | Idempotency key, request fingerprint, kết quả đã xử lý. | Database broker hoặc kho idempotency chuyên dụng. | Giữ key ổn định qua retry và restart. |
| Consumer credentials | Username/password, URI, certificate, token được trả trong bind response. | Secret manager hoặc encrypted secret store. | Giữ secret reference/version và khả năng consumer đọc. |
| Provider credentials | API token, client certificate, service account credential. | Secret manager/KMS. | Giữ đúng scope, account và quyền của provider adapter. |
| Broker authentication | Credential broker dùng xác thực request từ platform. | Secret manager/configuration bảo mật. | Đảm bảo platform và broker chuyển đổi đồng bộ. |
| Encryption metadata | Key ID, algorithm, nonce, ciphertext version. | Database metadata và KMS. | Khôi phục được key hoặc re-encrypt có kiểm soát. |
| Audit/outbox | Migration event, event chưa publish, audit history. | Database hoặc storage bền vững riêng. | Giữ thứ tự, replay safety và khả năng truy vết. |

Không gộp các loại credentials vào một bảng hoặc một secret path chỉ vì chúng đều là chuỗi nhạy cảm. Consumer credential có vòng đời theo binding; provider credential có vòng đời theo account/adapter; broker authentication có vòng đời theo platform registration. Quyền truy cập và chính sách rotation của chúng khác nhau.

## Mô hình lưu trữ: metadata trong database, secret trong secret manager

Database broker nên lưu metadata và reference tới secret. Secret value được lưu trong secret manager hoặc kho mã hóa chuyên dụng. Ví dụ binding ledger:

```text
service_binding
---------------
binding_id
instance_id
consumer_reference
provider_binding_id
credential_secret_ref
credential_version
binding_state
created_at
updated_at
```

`credential_secret_ref` có thể là đường dẫn hoặc ID bất biến trong secret manager; `credential_version` xác định phiên bản secret mà binding đang sử dụng. Không lưu password/token dạng rõ trong bảng này.

Provider credentials cũng nên dùng reference:

```text
provider_account
----------------
provider_id
account_ref
credential_secret_ref
credential_version
credential_status
updated_at
```

Nếu hệ thống cũ đang lưu secret trực tiếp trong database, cần phân loại mức độ nhạy cảm và thiết kế chuyển sang secret manager hoặc encrypted column. Không được mặc định rằng chỉ cần chuyển file backup là đủ an toàn.

### Những quan hệ phải bảo toàn

| Quan hệ | Bất biến |
|---|---|
| Instance → service/plan | Instance tiếp tục tham chiếu đúng service ID và plan ID đã provision. |
| Binding → instance | Mỗi binding trỏ đến đúng instance; không đổi `binding_id` khi migration. |
| Binding → consumer | App/consumer context không bị gán sang consumer khác. |
| Instance/binding → provider resource | Provider ID và account scope giữ nguyên. |
| Operation → resource | Operation đang chạy vẫn tham chiếu đúng instance/binding. |
| Operation → idempotency key | Retry sau migration dùng đúng key đã lưu. |
| Binding → secret reference/version | Consumer nhận đúng credential version đã được xác minh. |
| Outbox event → operation | Event replay không tạo operation hoặc side effect mới. |

Không tạo lại ID chỉ vì database mới có sequence khác. Các ID được platform và provider sử dụng phải được bảo toàn; sequence nội bộ chỉ được điều chỉnh sau khi copy dữ liệu để tránh collision với bản ghi mới.

## Lựa chọn chiến lược migration

Không có một cách chuyển duy nhất phù hợp cho mọi quy mô. Chọn chiến lược theo kích thước dữ liệu, downtime cho phép, khả năng replication và độ phức tạp của secret store.

| Chiến lược | Cách làm | Phù hợp khi | Rủi ro chính |
|---|---|---|---|
| Offline backup/restore | Dừng ghi, backup, restore sang hệ thống mới rồi cutover. | Database nhỏ hoặc có maintenance window. | Downtime; backup có thể không đồng bộ với provider side effect nếu worker vẫn chạy. |
| Snapshot + change data capture (CDC) | Copy snapshot ban đầu, sau đó phát lại thay đổi từ transaction log đến watermark. | Database lớn, cần giảm downtime. | Cần quản lý thứ tự, schema compatibility và lag. |
| Logical replication | Đồng bộ bảng/transaction sang database mới trước cutover. | Hai hệ quản trị tương thích hoặc cùng engine. | DDL, sequence, extension và quyền có thể không được replicate đầy đủ. |
| Application-level batch migration | Đọc/ghi theo batch qua repository hoặc migration job. | Cần transform schema hoặc chuyển secret reference. | Chậm hơn, dễ bỏ sót quan hệ và cần checkpoint. |
| Re-encryption migration | Đọc ciphertext cũ, giải mã trong memory và mã hóa bằng key mới. | Đổi KMS/key hierarchy hoặc encryption format. | Key cũ phải còn khả dụng; plaintext không được ghi ra disk/log. |

Có thể kết hợp snapshot + CDC cho database với một quy trình riêng cho secret manager. Không coi CDC database là bằng chứng secret value đã được sao chép; secret manager có hệ thống version và quyền riêng.

## Chuẩn bị schema bằng expand-contract

Nếu migration đồng thời đổi cấu trúc dữ liệu, áp dụng expand-contract để phiên bản ứng dụng cũ và mới có giai đoạn tương thích.

1. **Expand:** thêm bảng/cột/index mới ở trạng thái tương thích; không xóa field cũ.
2. **Dual-read hoặc backfill:** ứng dụng mới đọc dữ liệu cũ và mới theo quy tắc rõ ràng; chạy backfill có checkpoint.
3. **Switch writes:** chuyển writer duy nhất sang schema/secret reference mới sau khi dữ liệu đã được xác minh.
4. **Verify:** so sánh record count, foreign key, state distribution, secret reference và operation watermark.
5. **Contract:** chỉ xóa field/bảng cũ sau khi mọi replica và job không còn dùng chúng, rollback window đã qua.

Ví dụ thêm reference trước khi bỏ cột legacy:

```sql
ALTER TABLE service_binding
    ADD COLUMN credential_secret_ref VARCHAR(512),
    ADD COLUMN credential_version VARCHAR(128);
```

Sau khi backfill và chuyển code sang reference, có thể đánh dấu legacy credential column là deprecated. Chỉ xóa nó trong một release sau, khi đã xác minh không còn reader/writer nào phụ thuộc.

Flyway hoặc Liquibase có thể quản lý schema version trong ứng dụng Spring. Migration script phải được kiểm thử trên bản sao dữ liệu gần production và có thời gian chạy/lock được đo trước. Tránh chạy DDL phá hủy cùng lúc với cutover ứng dụng nếu không có kế hoạch phục hồi.

## Di chuyển dữ liệu credentials an toàn

### Không xuất secret thành CSV hoặc plaintext dump

Credential data không nên được chuyển bằng cách export bảng thành CSV, ghi vào file tạm hoặc đưa vào biến môi trường của shell. Những nơi này có thể bị lưu trong disk, terminal history, CI artifact, process listing hoặc log.

Một pipeline an toàn nên:

1. Xác thực quyền đọc secret ở nguồn và quyền ghi ở đích bằng service identity riêng cho migration.
2. Truyền dữ liệu qua TLS và dùng API/SDK chính thức của secret manager.
3. Giải mã trong memory khi cần đổi encryption format; không ghi plaintext xuống disk.
4. Mã hóa ngay tại đích bằng KMS/key của môi trường mới.
5. Ghi metadata reference/version và migration status vào ledger, không ghi secret value.
6. Kiểm tra bằng version, metadata hoặc HMAC được quản lý an toàn; không log plaintext để so sánh.
7. Giới hạn quyền migration identity và thu hồi quyền tạm sau khi hoàn tất.

Nếu secret manager hỗ trợ replication hoặc native migration, ưu tiên cơ chế đó sau khi xác minh semantics, version history và ACL. Việc copy một secret value nhưng bỏ qua version, lease, expiry hoặc policy có thể làm credential không còn hoạt động như trước.

### Re-encryption khi thay KMS hoặc encryption key

Nếu database cũ lưu ciphertext, mỗi bản ghi có thể cần metadata như:

```text
encrypted_secret
----------------
secret_id
ciphertext
key_id
algorithm
nonce_or_iv
format_version
created_at
```

Khi chuyển sang key mới, quy trình envelope encryption thường là:

1. Đọc ciphertext cùng `key_id` và metadata cần thiết.
2. Gọi KMS để giải mã data encryption key (DEK) hoặc decrypt payload theo thiết kế hiện tại.
3. Giải mã trong memory.
4. Tạo DEK/nonce mới theo chính sách đích.
5. Mã hóa plaintext bằng key/DEK mới và lưu ciphertext cùng metadata mới.
6. Xác minh decrypt được bằng key đích và secret reference vẫn đúng.
7. Chỉ retire key cũ khi không còn ciphertext hoặc backup cần key đó.

Không xóa key cũ ngay sau khi re-encrypt bảng hiện tại. Backup cũ, replica lag hoặc snapshot chưa hết retention có thể vẫn cần key cũ để restore. Quy trình retire key phải tính cả backup retention và disaster recovery.

### Credential rotation khác với credential migration

Migration chuyển vị trí hoặc định dạng lưu trữ, còn rotation thay đổi credential được provider chấp nhận. Hai việc này có thể phối hợp nhưng không nên gộp làm một thao tác không thể phân biệt.

- **Migration:** giữ nguyên credential value/version nếu an toàn, chỉ đổi secret reference hoặc encryption key.
- **Rotation:** tạo credential mới ở provider, cập nhật secret, chuyển consumer, rồi thu hồi credential cũ.
- **Revocation:** vô hiệu hóa credential bị lộ hoặc không còn được sử dụng.

Nếu rotation xảy ra cùng migration, phải lưu state riêng cho từng binding để biết consumer nào đã chuyển sang version mới. Không thu hồi credential cũ trước khi app đã nhận và xác minh credential mới, trừ khi có sự cố bảo mật yêu cầu thu hồi khẩn cấp.

## Chuẩn bị migration state store

Trước khi copy, tạo inventory của schema và dữ liệu:

- Danh sách bảng, view, sequence, index, constraint và trigger.
- Số lượng instance theo state (`PROVISIONING`, `READY`, `DEPROVISIONING`, `FAILED` hoặc state nội bộ tương ứng).
- Số lượng binding theo state.
- Số operation chưa terminal và tuổi operation lâu nhất.
- Outbox/inbox chưa xử lý và dead-letter count.
- Idempotency key và request fingerprint còn trong retention.
- Provider resource mapping và account reference.
- Secret reference/version cùng trạng thái tồn tại/expiry.
- Audit record và schema migration version.

Chụp baseline trước khi di chuyển để so sánh sau copy. Không chỉ so tổng row count; cần so count theo state, quan hệ FK, unique key và các tập operation đang chạy.

Ví dụ truy vấn kiểm kê (tên bảng/cột minh họa):

```sql
SELECT state, COUNT(*)
FROM service_instance
GROUP BY state;

SELECT binding_state, COUNT(*)
FROM service_binding
GROUP BY binding_state;

SELECT state, COUNT(*)
FROM broker_operation
GROUP BY state;

SELECT COUNT(*) AS pending_outbox
FROM broker_outbox
WHERE published_at IS NULL;
```

Điều chỉnh truy vấn theo schema thực tế của ứng dụng. Không đọc hoặc in các cột chứa secret để kiểm kê.

## Cutover có kiểm soát

Cutover là thời điểm chuyển quyền ghi từ state store cũ sang state store mới. Với broker có side effect provider, cần kiểm soát cả API request, worker và scheduler.

### Giai đoạn trước cutover

1. Rehearse migration trên bản sao dữ liệu và đo thời gian.
2. Kiểm tra backup/restore của cả database và secret manager.
3. Deploy phiên bản ứng dụng tương thích schema mới nếu dùng expand-contract.
4. Xác nhận provider adapter, KMS, network policy và secret access của môi trường mới.
5. Đồng bộ snapshot ban đầu và CDC/replication đến gần zero lag.
6. Xác định operation có thể tiếp tục, operation cần drain và operation cần giữ lại.
7. Thông báo maintenance window và xác định người phê duyệt cutover/rollback.

### Giai đoạn cutover

1. Bật maintenance/admission mode để ngăn request mutation mới hoặc giới hạn chúng theo kế hoạch.
2. Dừng scheduler tạo job mới và ngừng nhận message mới ở worker cũ.
3. Cho operation đang chạy hoàn tất trong thời hạn; operation chưa hoàn tất phải được checkpoint và giữ nguyên idempotency key.
4. Chờ transaction database và CDC đạt watermark đã chọn.
5. Fence writer cũ; xác nhận không còn process nào ghi vào store cũ.
6. Đồng bộ phần thay đổi cuối và sequence/constraint cần thiết.
7. Chuyển cấu hình DataSource và secret manager endpoint sang đích.
8. Khởi động một writer/worker canary, kiểm tra health và truy vấn read-only.
9. Mở worker theo batch nhỏ; xác nhận operation redelivery không tạo side effect trùng.
10. Mở admission API theo từng nhóm operation sau khi smoke test đạt.

Không để old và new deployment cùng ghi vào hai database độc lập. Dual-write không có transaction phân tán dễ tạo hai bản state khác nhau. Nếu cần dual-write trong giai đoạn chuyển tiếp, phải dùng một nguồn ghi chính, outbox/CDC hoặc cơ chế đồng bộ có thứ tự và reconciliation rõ ràng.

### Sau cutover

- Theo dõi error rate, operation latency, queue age, provider 429/5xx và DB pool.
- Kiểm tra catalog, provision test, bind test, unbind và deprovision theo môi trường kiểm thử.
- Xác minh Secret mới có thể đọc bởi workload được phép.
- So sánh instance/binding/operation counts và state distribution.
- Đối soát provider resource mapping cho operation quanh thời điểm cutover.
- Giữ state store cũ ở chế độ read-only trong rollback window theo policy.
- Chỉ xóa dữ liệu cũ khi đã hết retention và được phê duyệt.

## Xử lý operation đang chạy trong lúc migration

Operation `IN_PROGRESS` là phần rủi ro cao nhất. Nếu copy database khi worker vẫn ghi checkpoint, snapshot đích có thể thiếu bước cuối hoặc nhận event theo thứ tự sai.

Phân loại trước cutover:

| Loại operation | Cách xử lý |
|---|---|
| Chưa bắt đầu, state `PENDING` | Giữ operation và outbox; replay sau cutover bằng cùng operation ID. |
| Provider job đang chạy | Giữ provider job ID; worker mới tiếp tục polling job hiện tại. |
| Provider side effect đã xong, broker chưa persist | Lookup theo idempotency key/resource marker rồi persist kết quả; không tạo mới. |
| Operation đang compensation | Giữ checkpoint của từng bước bù; tiếp tục từ bước chưa hoàn tất. |
| Operation terminal | Không chạy side effect lại khi queue redelivery; chỉ acknowledge duplicate. |
| Kết quả không xác định | Giữ `RECONCILIATION_REQUIRED`; không tự động retry với key mới. |

Nếu không thể drain tất cả operation trong maintenance window, lưu snapshot nhất quán và đảm bảo worker mới có thể tiếp tục từ checkpoint. Không đánh dấu operation failed chỉ để làm queue trống trước cutover.

## Cấu hình Spring sau khi chuyển DataSource

Ứng dụng Spring Boot thường cấu hình DataSource qua environment/configuration management. Ví dụ:

```yaml
spring:
  datasource:
    url: ${BROKER_DB_URL}
    username: ${BROKER_DB_USERNAME}
    password: ${BROKER_DB_PASSWORD}
    hikari:
      maximum-pool-size: 12
      connection-timeout: 3000
```

Các giá trị nhạy cảm nên được inject từ secret manager hoặc workload identity; không commit vào `application.yml`. Khi cutover, thay endpoint/credential qua config source được kiểm soát và xác minh mỗi replica đã nhận cùng cấu hình. Nếu dùng nhiều DataSource (state store, audit hoặc outbox), phải lập danh sách và chuyển từng nguồn theo dependency.

Flyway/Liquibase schema migration cần chạy trước khi phiên bản ứng dụng mới phụ thuộc vào cột/bảng mới. Với nhiều replica, tránh để mọi Pod tự chạy DDL đồng thời nếu cơ chế migration tool/deployment chưa được thiết kế cho điều đó; thường nên có một migration job hoặc một leader được kiểm soát.

Sau khi DataSource đổi, kiểm tra:

- Connection pool đang trỏ đúng database/cluster.
- TLS và certificate database hợp lệ.
- User mới có quyền cần thiết nhưng không có quyền thừa.
- Transaction isolation, timezone, collation và extension không bị thay đổi ngoài dự kiến.
- Database sequence/identity không tạo ID trùng.
- Query/index plan vẫn đáp ứng latency yêu cầu.

## Chuyển secret reference và quyền truy cập

Nếu secret manager đích dùng path/namespace khác, có thể migration theo hai pha:

1. **Copy:** sao chép secret/version sang đích, giữ metadata về binding/provider và xác minh khả năng đọc bằng identity migration.
2. **Switch reference:** cập nhật `credential_secret_ref` và version trong database theo batch, sau đó kiểm tra ứng dụng/worker đọc được.

Không đổi reference trước khi secret đích tồn tại và policy cho workload đọc đã được cấp. Nếu cần tránh downtime, có thể cho phép reader tạm thời hiểu cả reference cũ và mới trong một release tương thích; writer chỉ ghi reference mới sau cutover. Sau khi mọi consumer/worker đã chuyển, thu hồi ACL và xóa secret cũ theo retention.

Kiểm tra quyền theo từng identity:

| Identity | Quyền cần thiết |
|---|---|
| Broker runtime | Đọc đúng provider credential và binding secret cần xử lý. |
| Operation worker | Đọc secret cho operation được claim; không cần quyền đọc toàn bộ secret của mọi tenant nếu có thể giới hạn. |
| Migration job | Đọc nguồn và ghi đích trong thời gian migration; quyền tạm thời. |
| Application consumer | Chỉ đọc secret binding của chính workload/namespace. |
| Operator/auditor | Xem metadata và audit; không mặc định có quyền xem secret value. |

Sau migration, thu hồi identity và policy tạm. Kiểm tra access log của secret manager để phát hiện việc đọc ngoài phạm vi.

## Rollback và roll-forward

Rollback không phải lúc nào cũng là khôi phục backup cũ. Sau cutover, broker có thể đã nhận request mới và tạo provider resource mới. Nếu quay database về snapshot cũ mà không chuyển các operation mới, mapping sẽ mất.

| Tình huống | Chiến lược |
|---|---|
| Chưa mở ghi ở database mới | Có thể quay cấu hình về store cũ nếu store cũ còn nguyên và watermark đồng bộ. |
| Đã có ghi mới nhưng chưa có provider side effect | Đồng bộ ngược hoặc replay journal về store cũ trước khi rollback. |
| Đã có provider side effect mới | Ưu tiên roll-forward hoặc reverse-replicate toàn bộ state/operation; không restore snapshot cũ đơn thuần. |
| Secret đã được re-encrypt | Giữ key cũ và mới trong rollback window; bảo đảm reader cũ vẫn truy cập được dữ liệu cần thiết. |
| Credential đã rotation/revocation | Không thể chỉ rollback reference nếu credential cũ đã bị revoke; cần quy trình rotation ngược hoặc roll-forward. |
| Schema đã contract/xóa cột | Có thể không rollback trực tiếp; cần migration ngược có kiểm chứng hoặc roll-forward. |

Trước migration, xác định rõ điểm không thể quay lại (point of no return). Sau điểm đó, ưu tiên roll-forward bằng migration sửa lỗi, CDC tiếp tục hoặc reconciliation thay vì restore database cũ gây mất operation.

## Kiểm chứng dữ liệu sau migration

Không chỉ dựa vào thông báo migration tool thành công. Cần kiểm chứng theo nhiều lớp:

### Kiểm chứng database

- Record count theo từng bảng và state.
- Primary key/unique key, foreign key và constraint.
- Sequence/identity value lớn hơn ID hiện tại cần cấp.
- Operation chưa terminal, outbox chưa publish và dead-letter.
- Timestamp, timezone, precision và JSON payload.
- Schema migration version và index tồn tại.

### Kiểm chứng secret

- Tất cả reference được trỏ đến secret tồn tại.
- Version/expiry/lease còn hợp lệ.
- Broker runtime và worker identity đọc được secret cần thiết.
- KMS decrypt/encrypt hoạt động bằng key đúng.
- Không có secret value trong log, artifact, backup không mã hóa hoặc terminal history.
- ACL đích không rộng hơn policy đã phê duyệt.

### Kiểm chứng provider mapping

- Provider resource ID tồn tại trong đúng account/project.
- Instance và binding map đúng resource/credential.
- Operation đang chạy tham chiếu đúng provider job ID.
- Không có resource mới trùng do retry trong cutover.
- Resource orphan hoặc mapping không xác định được đưa vào reconciliation queue.

Ví dụ kiểm tra tính đầy đủ của reference (SQL minh họa):

```sql
SELECT COUNT(*) AS bindings_without_secret_reference
FROM service_binding
WHERE binding_state = 'BOUND'
  AND credential_secret_ref IS NULL;

SELECT COUNT(*) AS operations_without_resource
FROM broker_operation
WHERE state IN ('IN_PROGRESS', 'RECONCILIATION_REQUIRED')
  AND resource_id IS NULL;
```

Các truy vấn phải điều chỉnh theo schema thực tế. Kết quả khác 0 không tự động có nghĩa dữ liệu sai; cần phân biệt loại binding/operation không cần reference và kiểm tra invariant đúng của domain.

## Kế hoạch kiểm thử migration

Một lần diễn tập nên dùng snapshot dữ liệu đại diện, có instance `READY`, binding hoạt động, operation đang chạy, operation thất bại và secret đã rotation.

| Kịch bản | Kết quả cần xác nhận |
|---|---|
| Copy state store sang database mới | ID, quan hệ, state và timestamp được bảo toàn. |
| Migration secret reference | Mọi binding active trỏ tới secret tồn tại và đúng version. |
| Re-encryption bằng KMS mới | Ciphertext mới decrypt được; key cũ vẫn dùng được cho backup trong retention. |
| Worker restart trong cutover | Job được nhận lại từ checkpoint; không tạo side effect trùng. |
| CDC lag hoặc mất event | Watermark phát hiện gap; không cutover khi chưa hội tụ. |
| Platform gửi retry cùng request | Broker trả kết quả nhất quán bằng idempotency record cũ. |
| Credential rotation đồng thời | Consumer chuyển sang secret version mới trước khi credential cũ bị thu hồi. |
| Rollback sau provider side effect | Operation/mapping mới không bị mất; roll-forward/replication giữ nhất quán. |
| Secret manager outage | Broker không trả credential giả hoặc đánh dấu binding hoạt động sai. |
| Reconciliation sau migration | Resource/provider mapping hội tụ, orphan candidate được phân loại. |

Kiểm thử functional sau cutover cần bao gồm catalog, provision, bind, retrieve nếu được công bố, unbind, update và deprovision trong môi trường thử nghiệm. Không chỉ kiểm tra API health hoặc database connection.

## Observability trong thời gian migration

Theo dõi metric riêng cho migration:

- Tổng record đã copy, record lỗi và batch checkpoint.
- CDC/replication lag và watermark cuối cùng.
- Số instance/binding/operation theo state trước và sau.
- Số secret reference đã chuyển, reference lỗi và secret version không khớp.
- KMS decrypt/encrypt failure và key access denial.
- Operation queue depth, oldest message age và worker retry.
- Provider 429/5xx, operation duration và reconciliation backlog.
- DB connection pool, transaction latency và lock wait.
- Số request OSB bị từ chối trong maintenance/admission mode.

Log migration nên ghi batch ID, record ID không nhạy cảm, source/target reference, watermark và error code. Không log secret value, ciphertext đầy đủ nếu không cần, token hoặc connection string chứa password.

## Checklist trước, trong và sau cutover

**Trước migration**

1. Inventory tất cả state store, secret store, KMS key và provider account.
2. Xác định RTO/RPO, downtime, rollback window và point of no return.
3. Backup và diễn tập restore database lẫn secret manager.
4. Kiểm tra expand-contract và compatibility giữa phiên bản app.
5. Xác định operation drain/freeze và cơ chế fencing worker.
6. Xác minh migration identity, TLS, ACL và quyền KMS.

**Trong migration**

7. Dừng admission mutation theo kế hoạch và drain/checkpoint operation.
8. Copy snapshot/CDC đến watermark nhất quán.
9. Chuyển secret theo pipeline mã hóa, không tạo plaintext artifact.
10. Bảo toàn ID, idempotency key, provider mapping và secret version.
11. Fence writer cũ trước khi mở writer mới.
12. Chạy canary và smoke test trước khi mở toàn bộ traffic.

**Sau migration**

13. Kiểm tra row count, relationship, state distribution, outbox và sequence.
14. Xác minh secret tồn tại, ACL đúng và runtime đọc được.
15. Đối soát provider resource và operation quanh cutover.
16. Theo dõi error rate, queue, provider quota và reconciliation.
17. Giữ nguồn cũ read-only trong rollback window; không xóa vội.
18. Thu hồi migration credential và retire key cũ theo backup retention.
19. Ghi audit, kết quả diễn tập và post-migration review.

## Kết luận

Di chuyển kho trạng thái và credentials của service broker là thay đổi có ảnh hưởng trực tiếp đến khả năng quản lý tài nguyên đã provision. Hãy phân biệt metadata với secret value, giữ nguyên instance/binding/operation identity, bảo toàn provider mapping và idempotency key, đồng thời chuyển secret qua pipeline mã hóa có kiểm soát. Dùng expand-contract, snapshot/CDC hoặc batch migration phù hợp; fence worker và chuyển writer tại một watermark nhất quán; sau cutover kiểm tra database, secret manager và provider reality trước khi mở toàn bộ traffic. Với Spring Cloud Service Broker, backup có thể khôi phục database nhưng chỉ reconciliation mới xác nhận broker còn quản lý đúng tài nguyên thật.
