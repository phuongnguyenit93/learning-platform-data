# Cập nhật tại chỗ hoặc thay thế tài nguyên và di chuyển dữ liệu

## Bối cảnh

Khi Platform gửi yêu cầu cập nhật một service instance theo Open Service Broker API (OSB API), broker phải chuyển yêu cầu đó thành thay đổi thực tế trên tài nguyên do provider quản lý. Thay đổi có thể đơn giản như tăng dung lượng, đổi cấu hình hoặc áp dụng bản vá. Cũng có trường hợp broker phải tạo một tài nguyên mới, di chuyển dữ liệu từ tài nguyên cũ, chuyển ứng dụng sang tài nguyên mới rồi mới thu hồi tài nguyên cũ.

Hai chiến lược phổ biến là:

- **Cập nhật tại chỗ (in-place update):** thay đổi cấu hình hoặc phiên bản trên chính tài nguyên đang phục vụ instance.
- **Thay thế và di chuyển (replace-and-migrate):** tạo tài nguyên mới, sao chép hoặc đồng bộ dữ liệu, chuyển lưu lượng sang tài nguyên mới rồi dọn tài nguyên cũ.

OSB API giữ một định danh service instance ở phía Platform trong suốt vòng đời của instance. Provider resource ID bên dưới có thể giữ nguyên hoặc thay đổi tùy chiến lược. Broker phải quản lý sự khác biệt đó một cách an toàn để Platform vẫn thao tác trên cùng instance, còn dữ liệu và kết nối của ứng dụng không bị mất hoặc chuyển sang trạng thái không nhất quán.

Trong module SPRING_CLOUD_SERVICE_BROKER, chủ đề này gắn với service instance update, quản lý trạng thái, xử lý bất đồng bộ, idempotency, bảo mật và adapter tích hợp Cloud Foundry hoặc Kubernetes.

## 1. Vị trí của update trong hợp đồng OSB API

Platform yêu cầu cập nhật service instance bằng HTTP PATCH tới endpoint:

~~~http
PATCH /v2/service_instances/{instance_id}
X-Broker-API-Version: 2.17
Content-Type: application/json
~~~

Request có thể chứa service ID, plan ID mới, parameters và previous_values. previous_values mô tả các giá trị trước cập nhật mà Platform đang biết; broker nên đối chiếu chúng với trạng thái lưu trữ của chính mình thay vì xem chúng là nguồn dữ liệu duy nhất.

Ví dụ request rút gọn:

~~~json
{
  "service_id": "postgres-service",
  "plan_id": "postgres-ha",
  "parameters": {
    "storage_gb": 200,
    "maintenance_window": "sun-02:00-04:00"
  },
  "previous_values": {
    "service_id": "postgres-service",
    "plan_id": "postgres-standard",
    "organization_id": "org-123",
    "space_id": "space-456"
  }
}
~~~

Request này có thể biểu diễn thay đổi plan từ postgres-standard sang postgres-ha và thay đổi tham số. Nó không nói rằng provider phải cập nhật tại chỗ hay thay thế tài nguyên. Quyết định đó thuộc broker, dựa trên khả năng của provider, chính sách plan, dữ liệu hiện tại và yêu cầu vận hành.

Ở lớp catalog, thuộc tính plan_updateable của service cho Platform biết khả năng đổi plan theo hợp đồng OSB API. Broker vẫn phải kiểm tra từng thay đổi cụ thể: plan đích có hợp lệ không, tham số có được phép thay đổi không, tài nguyên hiện tại có thể chuyển đổi an toàn không và caller có quyền trên instance không.

Kết quả update đồng bộ thường được trả bằng HTTP 200 OK. Nếu Platform cho phép incomplete operation và broker cần thời gian xử lý, broker có thể trả HTTP 202 Accepted cùng operation reference. Response cụ thể phải tuân theo phiên bản OSB API và response model mà ứng dụng Spring Cloud Open Service Broker đang dùng.

## 2. Cập nhật tại chỗ (in-place update)

Với cập nhật tại chỗ, broker yêu cầu provider sửa tài nguyên hiện có. Resource ID, địa chỉ kết nối và phần lớn topology có thể được giữ nguyên, dù điều đó phụ thuộc vào provider và loại thay đổi.

Ví dụ:

- Tăng dung lượng volume hoặc database storage.
- Thay đổi giới hạn connection hoặc tham số cấu hình.
- Tăng CPU/RAM của một workload khi nền tảng cho phép resize.
- Áp dụng minor patch có hỗ trợ nâng cấp trực tiếp.
- Thay đổi policy backup hoặc lịch bảo trì.

### Luồng xử lý

1. Tải instance theo Platform scope và instance ID.
2. Xác minh trạng thái hiện tại cho phép update.
3. So sánh plan/parameters hiện tại với yêu cầu mới.
4. Kiểm tra giới hạn tài nguyên, khả năng nâng cấp và các điều kiện phụ thuộc.
5. Ghi operation hoặc trạng thái cập nhật trước khi gọi provider nếu cần xử lý dài.
6. Gọi adapter để thay đổi tài nguyên hiện có.
7. Đọc lại trạng thái từ provider và xác nhận cấu hình mong muốn đã có hiệu lực.
8. Cập nhật bản ghi instance, kết thúc operation và trả response OSB API.

Sơ đồ đơn giản:

~~~mermaid
sequenceDiagram
    participant P as Platform
    participant B as Broker
    participant DB as Instance Repository
    participant A as Provider Adapter
    participant R as Existing Resource

    P->>B: PATCH service instance
    B->>DB: Read instance and current state
    B->>B: Validate plan, parameters and policy
    B->>DB: Mark UPDATING
    B->>A: Update existing resource
    A->>R: Resize or change configuration
    R-->>A: Provider result
    A-->>B: Normalized update result
    B->>A: Verify actual resource state
    A-->>B: Desired state confirmed
    B->>DB: Persist new plan/parameters
    B-->>P: 200 OK
~~~

### Ưu điểm và giới hạn

| Khía cạnh | Đặc điểm |
|---|---|
| Thời gian | Thường ngắn hơn vì không phải sao chép toàn bộ dữ liệu |
| Chi phí | Có thể thấp hơn do không cần duy trì hai tài nguyên song song |
| Định danh provider | Thường giữ nguyên |
| Endpoint và credentials | Có khả năng giữ nguyên, nhưng phải xác minh theo provider |
| Downtime | Có thể không downtime, downtime ngắn hoặc cần restart |
| Khả năng rollback | Phụ thuộc provider; nhiều thay đổi không thể giảm ngược an toàn |
| Rủi ro | Provider có thể thay đổi trạng thái một phần hoặc thao tác bị gián đoạn |

Không nên mặc định rằng in-place luôn đơn giản hoặc an toàn. Nâng cấp major version database, thay đổi định dạng dữ liệu hoặc chuyển đổi storage có thể không hỗ trợ downgrade. Trước khi chọn chiến lược này, broker phải biết provider hỗ trợ thao tác nào, có backup hay snapshot không và trạng thái sau lỗi có thể được phục hồi như thế nào.

### Khi nào nên dùng?

In-place phù hợp khi provider hỗ trợ thay đổi trực tiếp, định dạng dữ liệu tương thích, thời gian thao tác đáp ứng yêu cầu và có cách xác minh kết quả. Với thay đổi không thể đảo ngược, cần backup có thể khôi phục và kế hoạch forward recovery trước khi bắt đầu.

## 3. Thay thế tài nguyên và di chuyển dữ liệu

Replace-and-migrate tạo một tài nguyên mới thay cho tài nguyên hiện tại. Broker giữ tài nguyên cũ trong khi chuẩn bị tài nguyên mới, di chuyển dữ liệu và kiểm tra kết quả. Khi đã sẵn sàng, broker chuyển endpoint hoặc tham chiếu nội bộ sang tài nguyên mới. Sau một khoảng thời gian xác nhận, broker mới thu hồi tài nguyên cũ.

Ví dụ:

- Chuyển database từ storage class cũ sang storage class mới.
- Nâng cấp giữa các major version database không hỗ trợ in-place.
- Di chuyển workload sang cluster hoặc region khác.
- Thay thế một managed database bằng dịch vụ provider khác.
- Thay đổi topology từ một node sang high availability.

### Luồng tổng quát

~~~mermaid
flowchart TD
    A[Nhận PATCH update] --> B[Kiểm tra instance, plan và policy]
    B --> C[Ghi operation và khóa cập nhật]
    C --> D[Tạo tài nguyên mới]
    D --> E[Kiểm tra tài nguyên mới]
    E --> F[Sao chép snapshot hoặc dữ liệu ban đầu]
    F --> G[Đồng bộ thay đổi phát sinh]
    G --> H[Chặn hoặc tạm dừng ghi trong cửa sổ cutover]
    H --> I[Đồng bộ phần dữ liệu cuối]
    I --> J[Kiểm tra tính toàn vẹn]
    J --> K[Chuyển endpoint hoặc active resource pointer]
    K --> L[Kiểm tra ứng dụng và binding]
    L --> M[Giữ tài nguyên cũ trong thời gian rollback]
    M --> N[Thu hồi tài nguyên cũ]
    N --> O[Đánh dấu update thành công]
~~~

Trình tự thực tế có thể khác tùy loại database và provider. Điểm cốt lõi là broker không chuyển traffic sang tài nguyên mới trước khi dữ liệu đạt mức nhất quán yêu cầu và không xóa tài nguyên cũ trước khi đã xác minh việc chuyển đổi.

### Các giai đoạn chính

**1. Prepare**

- Xác định resource hiện tại, version, kích thước dữ liệu và dependencies.
- Kiểm tra quota để tạm thời cấp đủ tài nguyên cho cả bản cũ và bản mới.
- Xác nhận quyền, maintenance window, backup và khả năng rollback.
- Tạo operation có source resource ID và target configuration.

**2. Provision target**

- Tạo database/cluster/volume mới theo plan hoặc cấu hình đích.
- Thiết lập network, firewall, encryption, identity và monitoring.
- Tạo schema hoặc database rỗng theo quy trình chuẩn.
- Kiểm tra target có thể truy cập từ broker và các thành phần cần thiết.

**3. Initial data copy**

- Tạo snapshot nhất quán hoặc dump dữ liệu.
- Restore vào target hoặc dùng native replication.
- Giữ nguyên encoding, collation, extension, index, sequence và quyền cần thiết.
- Ghi nhận checkpoint để có thể tiếp tục nếu worker bị dừng.

**4. Continuous synchronization**

Nếu ứng dụng vẫn ghi dữ liệu vào nguồn trong khi sao chép, broker cần đồng bộ các thay đổi phát sinh. Có thể dùng native replication, change data capture (CDC), transaction log hoặc cơ chế đồng bộ do provider hỗ trợ. Broker phải theo dõi replication lag và không được coi bản sao ban đầu là dữ liệu mới nhất khi hệ thống vẫn có ghi.

**5. Cutover**

- Thông báo hoặc phối hợp với Platform/operator về cửa sổ chuyển đổi.
- Tạm dừng ghi hoặc chuyển ứng dụng sang chế độ read-only nếu cần.
- Chờ replication lag về mức cho phép và đồng bộ phần thay đổi cuối.
- Kiểm tra số lượng bản ghi, checksum hoặc các invariant nghiệp vụ.
- Chuyển endpoint, proxy route, DNS hoặc active resource pointer theo cơ chế có thể kiểm soát.
- Xác minh ứng dụng kết nối và thực hiện thao tác đọc/ghi kiểm tra.

**6. Stabilize and cleanup**

- Theo dõi lỗi kết nối, độ trễ, error rate và tính toàn vẹn dữ liệu.
- Giữ tài nguyên cũ trong khoảng rollback đã thống nhất.
- Sau khi hết cửa sổ rollback, thu hồi tài nguyên cũ và credentials không còn dùng.
- Cập nhật instance thành trạng thái READY và operation thành succeeded.

## 4. Di chuyển dữ liệu và tính nhất quán

Di chuyển dữ liệu là phần khó nhất khi thay thế tài nguyên. Broker cần lựa chọn phương thức theo kích thước dữ liệu, khả năng của provider, mức downtime chấp nhận được và yêu cầu nhất quán của ứng dụng.

| Phương thức | Cách hoạt động | Phù hợp khi | Rủi ro/chú ý |
|---|---|---|---|
| Snapshot/backup và restore | Chụp trạng thái nguồn rồi phục hồi sang target | Có thể chấp nhận khoảng dừng ghi hoặc có snapshot nhất quán | Dữ liệu mới phát sinh sau snapshot phải được đồng bộ |
| Logical dump/import | Xuất schema và records rồi nhập vào target | Cần đổi engine/version hoặc lọc/chuyển đổi schema | Có thể chậm với dữ liệu lớn; cần xử lý sequence, extension và quyền |
| Native replication | Provider/database đồng bộ transaction log | Hệ quản trị hỗ trợ replication tương thích | Phải theo dõi lag, version compatibility và quyền replication |
| CDC | Đọc change log và áp dụng thay đổi lên target | Cần giảm downtime cho hệ thống vẫn hoạt động | Cần xử lý thứ tự, duplicate event, schema evolution và delete |
| Dual-write | Ứng dụng ghi đồng thời vào nguồn và đích | Có thể thay đổi ứng dụng và có cơ chế reconciliation mạnh | Khó bảo đảm atomicity giữa hai hệ thống; dễ lệch dữ liệu |

### Snapshot và restore

Snapshot cần có tính nhất quán phù hợp với ứng dụng. Với database đang chạy, snapshot ở mức storage không phải lúc nào cũng tương đương backup logic nhất quán. Hãy dùng cơ chế backup được database/provider hỗ trợ và lưu metadata về timestamp, checkpoint, encryption key và version engine.

Sau restore, chạy kiểm tra schema, index, sequence, constraint, user/role, extension và quyền truy cập. Một restore hoàn tất không đồng nghĩa dữ liệu đã sẵn sàng phục vụ ứng dụng.

### Replication và CDC

Khi dùng replication hoặc CDC, broker cần theo dõi vị trí đồng bộ cuối cùng. Ví dụ, database có thể dùng log sequence number (LSN), binlog position hoặc checkpoint riêng của provider. Chỉ chuyển traffic khi target đã nhận mọi thay đổi trước điểm cutover và nguồn không còn nhận ghi mới.

Consumer CDC phải xử lý duplicate message theo cách idempotent. Thứ tự transaction cần được giữ đúng ở phạm vi mà dữ liệu phụ thuộc. Nếu có thay đổi schema trong lúc migration, cần quy định schema version tương thích giữa source, pipeline và target.

### Dual-write

Dual-write không tự động tạo tính nhất quán. Nếu ghi vào source thành công nhưng ghi target thất bại, hai hệ thống sẽ lệch nhau. Chỉ dùng khi có cơ chế transactional outbox, retry, idempotency key, reconciliation và quy tắc xử lý xung đột rõ ràng. Với nhiều ứng dụng, replication hoặc CDC thường dễ kiểm soát hơn việc yêu cầu tất cả caller ghi vào hai database.

## 5. Cutover, endpoint và binding

Tài nguyên mới có thể có hostname, port, certificate hoặc credentials khác tài nguyên cũ. Broker phải quyết định cách ứng dụng chuyển sang endpoint mới.

Một số mô hình:

- **Stable proxy endpoint:** ứng dụng luôn dùng một endpoint ổn định; broker đổi backend đích ở proxy/gateway.
- **Stable DNS alias:** hostname không đổi nhưng record phía sau chuyển sang target mới; cần tính tới DNS cache và connection pool.
- **Binding rotation:** broker tạo credentials mới, cập nhật binding state và hỗ trợ ứng dụng nhận cấu hình mới theo quy trình nền tảng.
- **Explicit rebinding:** yêu cầu Platform/operator tạo lại binding hoặc triển khai lại ứng dụng theo khả năng của nền tảng.

Không thể giả định rằng Platform tự động cập nhật mọi biến môi trường hoặc secret khi broker thay endpoint. Binding là một phần riêng của OSB API. Broker phải biết Platform hỗ trợ retrieve/recreate binding hay không và cần tài liệu hóa hành vi khi update làm thay đổi credentials.

Nếu broker có thể giữ endpoint ổn định, đó thường là cách giảm tác động tới ứng dụng. Nếu endpoint hoặc credentials bắt buộc thay đổi, cần xác định trước thời điểm cutover, cách phân phối secret mới, thời gian hỗ trợ credential cũ và cách thu hồi an toàn.

Với Kubernetes, endpoint có thể được trừu tượng hóa qua Service, Ingress hoặc proxy; với database managed bên ngoài cluster, có thể dùng DNS alias hoặc gateway. Với Cloud Foundry, binding credentials thường được cung cấp cho ứng dụng qua cơ chế service binding của nền tảng. Trong cả hai trường hợp, broker vẫn phải quản lý trạng thái binding và phối hợp để ứng dụng sử dụng thông tin kết nối mới.

## 6. Giữ ổn định định danh OSB trong khi provider resource thay đổi

Platform thao tác trên service instance ID do Platform cấp. Khi broker thay thế provider resource, không nên tạo một service instance OSB mới chỉ vì resource ID nội bộ thay đổi. Thay vào đó, bản ghi instance có thể giữ:

~~~text
ServiceInstance
  platformId
  instanceId
  serviceId
  planId
  activeProviderResourceId
  lifecycleState
  currentOperationId

ServiceUpdateOperation
  operationId
  instanceId
  strategy                 # IN_PLACE hoặc REPLACE_MIGRATE
  sourceResourceId
  targetResourceId
  sourcePlanId
  targetPlanId
  sourceVersion
  targetVersion
  phase
  checkpoint
  state
  startedAt
  completedAt
~~~

activeProviderResourceId là con trỏ tới tài nguyên đang phục vụ instance. Trong chiến lược replace-and-migrate, broker chỉ đổi con trỏ này tại thời điểm cutover sau khi target đã sẵn sàng và dữ liệu được xác minh. Source resource ID vẫn được lưu trong operation để rollback hoặc cleanup.

Thay đổi con trỏ phải được bảo vệ bằng transaction hoặc compare-and-set để hai worker không đồng thời chuyển instance sang hai target khác nhau. Có thể dùng version number/optimistic locking hoặc fencing token để ngăn worker cũ ghi đè trạng thái mới.

## 7. Máy trạng thái cho update

Update phức tạp cần được mô hình hóa thành state machine. Ví dụ:

| Trạng thái | Ý nghĩa | Điều kiện chuyển tiếp |
|---|---|---|
| READY | Instance đang phục vụ bình thường | Nhận request update hợp lệ |
| UPDATE_REQUESTED | Broker đã ghi nhận ý định | Policy và quota được xác nhận |
| PREPARING | Đang tạo target hoặc chuẩn bị in-place | Provider chấp nhận thao tác |
| COPYING | Đang snapshot/restore/replicate dữ liệu | Target đạt checkpoint |
| CUTOVER_PENDING | Đã sẵn sàng chuyển traffic | Final sync và validation đạt |
| CUTTING_OVER | Đang chuyển endpoint hoặc active pointer | Health check thành công |
| VERIFYING | Đang kiểm tra sau cutover | Invariant và kết nối đạt |
| CLEANUP_PENDING | Đang giữ tài nguyên cũ trong cửa sổ rollback | Hết thời gian giữ hoặc operator xác nhận |
| SUCCEEDED | Update hoàn tất | Trả kết quả cuối |
| ROLLBACK_PENDING | Cần chuyển về nguồn hoặc phục hồi | Điều kiện rollback được xác minh |
| FAILED | Update thất bại và không tự phục hồi | Cần retry, reconcile hoặc can thiệp |

Không phải mọi update đều đi qua tất cả trạng thái. In-place update có thể bỏ qua COPYING và CUTOVER. State machine phải thể hiện các phase thực sự của provider và lưu checkpoint để worker có thể tiếp tục sau restart.

### Lock và concurrency

Broker nên tuần tự hóa update trên cùng một instance. Nếu hai PATCH cùng lúc thay plan hoặc parameters, thao tác thứ hai cần chờ, bị từ chối do conflict hoặc được hợp nhất theo policy. Không cho phép hai operation cùng sửa active resource pointer.

Khóa trong bộ nhớ của một process không đủ khi broker có nhiều replica. Dùng database lock, optimistic version, distributed lock có lease hoặc cơ chế fencing. Lease hết hạn không đồng nghĩa worker cũ đã dừng; fencing token giúp từ chối các cập nhật trạng thái đến từ worker đã mất quyền sở hữu.

## 8. Xử lý bất đồng bộ và phục hồi sau lỗi

Di chuyển dữ liệu và thay thế tài nguyên thường kéo dài, nên thường phù hợp với OSB asynchronous operation nếu Platform gửi accepts_incomplete=true. Broker trả 202 Accepted cùng operation ID, sau đó Platform truy vấn last_operation theo hợp đồng.

Một luồng bền vững nên:

1. Ghi operation và trạng thái UPDATE_REQUESTED trong cùng transaction.
2. Ghi outbox event trong cùng transaction để bảo đảm công việc không bị mất.
3. Publisher đưa event vào queue.
4. Worker nhận job, xác minh operation vẫn là operation hiện hành của instance.
5. Worker chạy từng phase và lưu checkpoint sau mỗi bước có ý nghĩa.
6. Worker cập nhật operation state và instance state theo transaction.
7. Platform polling last_operation nhận trạng thái tiến trình hoặc lỗi cuối.

### Bảng xử lý lỗi

| Điểm lỗi | Rủi ro | Hành động phục hồi |
|---|---|---|
| Tạo target thất bại | Chưa có tài nguyên mới | Giải phóng tài nguyên dở dang, giữ source hoạt động |
| Restore thất bại | Target chưa hoàn chỉnh | Xóa/recreate target hoặc tiếp tục từ checkpoint |
| Replication bị gián đoạn | Target không theo kịp source | Reconnect replication, kiểm tra lag và checkpoint |
| Final sync thất bại | Không thể cutover an toàn | Giữ source nhận traffic, retry hoặc hủy migration |
| Cutover thất bại | Route có thể trỏ sai hoặc một phần | Kiểm tra active pointer, route và health; khôi phục source nếu an toàn |
| Target lỗi sau cutover | Ứng dụng có thể bị gián đoạn | Thực hiện rollback có kiểm soát hoặc forward recovery |
| Cleanup source thất bại | Tốn chi phí và còn tài nguyên cũ | Giữ cleanup pending, retry idempotent |
| Broker restart | Worker có thể bị chạy lại | Đọc checkpoint/provider state trước khi lặp side effect |

### Rollback và forward recovery

Rollback dễ nhất trước cutover: source vẫn là tài nguyên chính, target có thể bị hủy. Sau cutover, nếu ứng dụng đã ghi dữ liệu mới vào target, quay lại source có thể làm mất dữ liệu phát sinh. Vì vậy, rollback sau cutover cần có chiến lược đồng bộ ngược hoặc phải chặn ghi trong thời gian khôi phục.

Với thay đổi không thể đảo ngược, forward recovery có thể an toàn hơn: giữ target, sửa lỗi cấu hình hoặc tiếp tục migration cho tới khi target đạt trạng thái mong muốn. Broker cần phân loại phase nào có thể retry, phase nào có side effect không thể lặp và phase nào cần operator can thiệp.

## 9. Idempotency và xử lý request lặp

Platform có thể retry PATCH khi không nhận được response. Worker có thể nhận lại event vì queue thường giao thông điệp theo cơ chế at-least-once. Broker cần bảo đảm cùng một ý định update không tạo nhiều target hoặc chạy migration nhiều lần.

Fingerprint update có thể dựa trên:

- Platform ID và instance ID.
- Source plan/resource version.
- Target plan và parameters đã chuẩn hóa.
- Loại chiến lược update.
- Operation ID hoặc request identity nếu có.

Quy tắc xử lý:

- Nếu cùng target configuration đã hoàn tất, trả kết quả hiện có theo hợp đồng.
- Nếu cùng operation đang chạy, trả lại operation hiện tại thay vì tạo operation mới.
- Nếu request mới xung đột với operation đang chạy, trả lỗi conflict phù hợp.
- Nếu worker chạy lại sau khi provider đã thực hiện một bước, đọc trạng thái provider và checkpoint trước khi gọi lại.
- Nếu target resource đã tồn tại với operation tag tương ứng, tái sử dụng hoặc tiếp tục theo policy thay vì tạo thêm.

Provider resource nên được gắn metadata/tag nội bộ như broker instance ID, operation ID và generation để hỗ trợ tìm kiếm, reconcile và cleanup. Các tag này không thay thế bản ghi bền vững của broker nhưng giúp phục hồi khi broker mất kết nối giữa provider call và database commit.

## 10. Tích hợp với Spring Cloud Open Service Broker

Spring Cloud Open Service Broker cung cấp abstraction cho service instance update. Ứng dụng triển khai update handler/service phù hợp với phiên bản thư viện, nhận request model chứa service ID, plan ID, parameters và previous values, sau đó trả response model đồng bộ hoặc bất đồng bộ theo API được hỗ trợ.

Nên tách trách nhiệm:

| Thành phần | Trách nhiệm |
|---|---|
| OSB update handler | Nhận request và chuyển dữ liệu sang application service |
| Update application service | Chọn in-place hay replace-and-migrate, áp dụng policy và điều phối operation |
| Plan/parameter policy | Kiểm tra khả năng update và giới hạn đích |
| Instance repository | Lưu trạng thái, active resource ID và version |
| Operation repository/outbox | Lưu tiến trình và phát công việc bền vững |
| Provider adapter | Thực hiện resize, snapshot, restore, replication, cutover hoặc cleanup |
| Binding service/state | Quản lý endpoint và credentials liên quan tới binding |

Ví dụ pseudocode cho quyết định chiến lược:

~~~java
UpdateResult update(UpdateCommand command) {
    var instance = instances.lockAndLoad(
            command.platformId(), command.instanceId());

    updatePolicy.validate(instance, command);

    var strategy = strategySelector.select(
            instance.currentProviderType(),
            instance.currentPlan(),
            command.targetPlan(),
            command.parameters());

    return switch (strategy) {
        case IN_PLACE -> inPlaceUpdater.start(instance, command);
        case REPLACE_MIGRATE -> migrationCoordinator.start(instance, command);
    };
}
~~~

Đây là pseudocode mô tả ranh giới nghiệp vụ, không phải chữ ký method cụ thể của Spring Cloud Open Service Broker. Trong ứng dụng thực tế, hãy dùng đúng interface và response type của phiên bản dependency đang cài đặt. Không tạo controller trùng endpoint mà framework đã đăng ký.

### Ánh xạ kết quả update sang OSB API

- Nếu provider đã hoàn tất update đồng bộ và broker đã xác minh trạng thái, trả response đồng bộ theo hợp đồng.
- Nếu công việc còn tiếp tục và Platform chấp nhận incomplete operation, lưu operation và trả response bất đồng bộ với operation reference.
- Nếu request không hợp lệ, caller không có quyền, plan không hỗ trợ hoặc trạng thái xung đột, chuyển lỗi thành response OSB API phù hợp.
- Không báo thành công chỉ vì provider đã nhận lệnh; cần xác minh trạng thái tài nguyên và lưu kết quả bền vững.

## 11. Kiểm thử chiến lược update

Kiểm thử cần xác minh không chỉ response HTTP mà cả tài nguyên, dữ liệu, endpoint và trạng thái broker.

| Nhóm kiểm thử | Nội dung |
|---|---|
| Policy | Chọn đúng in-place hoặc replace-and-migrate cho từng thay đổi |
| In-place success | Resource ID giữ đúng, provider state và instance state được cập nhật |
| In-place failure | Lỗi một phần được phát hiện, trạng thái không bị đánh dấu READY sai |
| Target provisioning | Tài nguyên mới có cấu hình, network và security đúng |
| Data migration | Snapshot/restore hoặc replication giữ đủ dữ liệu và invariant |
| Cutover | Active pointer/route chỉ chuyển sau final sync và validation |
| Binding | Endpoint/credentials được giữ ổn định hoặc xoay vòng theo policy |
| Rollback | Có thể giữ source hoặc phục hồi theo phase đã định nghĩa |
| Async operation | 202, operation polling và trạng thái cuối chính xác |
| Idempotency | Retry PATCH và duplicate queue event không tạo target trùng |
| Concurrency | Hai update đồng thời không ghi đè active resource pointer |
| Cleanup | Source chỉ bị xóa sau thời gian giữ và điều kiện xác nhận |

Với migration dữ liệu, cần có dữ liệu thử gồm update, delete, transaction đồng thời, dữ liệu lớn, index, sequence và trường hợp schema thay đổi. So sánh số lượng bản ghi đơn thuần chưa đủ; cần kiểm tra checksum hoặc invariant nghiệp vụ quan trọng. Kiểm thử cutover nên mô phỏng ứng dụng đang ghi để xác nhận không mất transaction.

## 12. Checklist triển khai production

- [ ] Broker phân loại rõ thay đổi nào hỗ trợ in-place và thay đổi nào cần thay thế tài nguyên.
- [ ] Policy kiểm tra plan_updateable, parameters, quota và khả năng provider.
- [ ] Source resource được giữ nguyên cho tới khi target sẵn sàng và cutover được xác minh.
- [ ] Có backup/snapshot và checkpoint phù hợp với phương thức di chuyển.
- [ ] Có phương thức đồng bộ dữ liệu phát sinh khi source vẫn nhận ghi.
- [ ] Có cửa sổ cutover và điều kiện replication lag/tính toàn vẹn rõ ràng.
- [ ] Endpoint và binding credentials được giữ ổn định hoặc có kế hoạch xoay vòng.
- [ ] OSB instance ID không đổi chỉ vì provider resource ID thay đổi.
- [ ] Active resource pointer được cập nhật nguyên tử hoặc có optimistic locking/fencing.
- [ ] Operation và outbox được lưu bền vững trước khi trả 202.
- [ ] Worker có checkpoint, idempotency và khả năng reconcile sau restart.
- [ ] Rollback trước/sau cutover được định nghĩa; biết khi nào cần forward recovery.
- [ ] Tài nguyên cũ chỉ được cleanup sau khi hết cửa sổ rollback.
- [ ] Có audit, metric, cảnh báo và quy trình operator can thiệp.

## Kết luận

Cập nhật tại chỗ phù hợp khi provider hỗ trợ thay đổi trực tiếp và trạng thái dữ liệu có thể được bảo vệ trong cùng tài nguyên. Thay thế tài nguyên và di chuyển dữ liệu phù hợp khi cần đổi engine, storage, topology hoặc nền tảng mà không thể nâng cấp an toàn tại chỗ. Dù chọn chiến lược nào, broker phải giữ ổn định định danh OSB instance, lưu trạng thái update bền vững, xác minh dữ liệu và endpoint trước khi báo thành công. Với replace-and-migrate, source chỉ được thu hồi sau cutover và cửa sổ rollback; với in-place, broker cần biết rõ khả năng phục hồi khi provider chỉ hoàn thành một phần. Đây là nền tảng để service broker thực hiện update đáng tin cậy trên các provider được tích hợp qua Spring Cloud.
