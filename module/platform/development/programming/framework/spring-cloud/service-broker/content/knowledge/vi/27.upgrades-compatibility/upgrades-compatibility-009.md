# Ngừng cung cấp broker và bàn giao tài nguyên đang được sử dụng

Một service broker có thể ngừng phát triển hoặc ngừng vận hành trong khi các service instance do broker tạo ra vẫn đang phục vụ ứng dụng production. Xóa deployment hoặc gỡ đăng ký broker quá sớm có thể làm mất khả năng update, bind, unbind, deprovision, đọc trạng thái operation hoặc thu hồi credential. Backend resource vẫn tồn tại nhưng không còn thành phần biết cách quản lý nó; đó là tình trạng orphaned resource và có thể dẫn đến chi phí, rủi ro bảo mật hoặc mất dữ liệu.

Trong module **SPRING_CLOUD_SERVICE_BROKER**, việc retirement cần được xem như một migration có kiểm soát. Đội vận hành phải kiểm kê instance và binding, dừng tiếp nhận workload mới theo kế hoạch, hoàn tất hoặc đối soát operation đang chạy, chuyển quyền sở hữu state và provider resource sang broker thay thế, duy trì tương thích platform trong giai đoạn chuyển tiếp, rồi mới gỡ broker cũ. Mục tiêu là giữ tài nguyên đang sử dụng có chủ quản rõ ràng trong toàn bộ quá trình.

## 1. Phân biệt ngừng broker, ngừng service và ngừng plan

Có nhiều phạm vi retirement khác nhau. Nếu không xác định đúng phạm vi, thao tác dọn dẹp có thể ảnh hưởng cả những service không nằm trong kế hoạch.

| Phạm vi | Ý nghĩa | Điều cần giữ |
|---|---|---|
| Ngừng một plan | Không cho tạo instance mới theo plan đó | Existing instance vẫn cần retrieve, update theo policy, bind/unbind và deprovision |
| Ngừng một service offering | Không nhận provision mới cho service | Các instance và binding hiện hữu cần được quản lý đến khi chuyển hoặc thu hồi |
| Ngừng một provider/backend | Không còn tạo tài nguyên mới trên provider cũ | Có thể phải migrate dữ liệu/resource hoặc duy trì adapter cũ để cleanup |
| Thay broker implementation | Chuyển API và logic từ broker cũ sang broker mới | Mapping ID, state, operation và ownership phải được bàn giao |
| Gỡ broker khỏi platform | Xóa registration hoặc endpoint broker khỏi platform | Phải xác minh platform còn cần gọi broker cho instance hiện hữu hay không |
| Ngừng toàn bộ sản phẩm | Kết thúc dịch vụ và hợp đồng | Cần thông báo, export dữ liệu, deprovision, thu hồi credential và retention |

Ngừng công bố plan trong catalog không giống deprovision instance. Gỡ đăng ký broker khỏi platform cũng không tự động chứng minh provider resource đã bị xóa. Đây là các hành động có vòng đời và tác động khác nhau.

### OSB API không định nghĩa một endpoint handover broker chung

Open Service Broker API định nghĩa contract cho catalog, provision, update, bind, unbind, deprovision và last operation. Contract này không cung cấp một thao tác portable để chuyển ownership của mọi instance từ broker A sang broker B hoặc để platform tự động nhập state từ broker mới.

Vì vậy, quy trình retirement phải phối hợp với khả năng của platform, broker implementation, provider API và công cụ vận hành. Cloud Foundry, Kubernetes integration hoặc một platform nội bộ có thể có quy tắc riêng về deregistration và service instance migration. Hãy xác minh hành vi theo phiên bản đang chạy trước khi thay đổi registration.

## 2. Những nguyên tắc không được phá vỡ

Trong suốt quá trình bàn giao, cần duy trì các invariant sau:

1. Mỗi service instance đang tồn tại phải có một broker hoặc đội vận hành chịu trách nhiệm rõ ràng.
2. Mỗi binding còn hiệu lực phải có đường thu hồi credential và cập nhật consumer.
3. Mỗi operation đã được chấp nhận phải có kết quả cuối cùng hoặc trạng thái reconciliation có người theo dõi.
4. Không có hai broker cùng ghi lifecycle state cho một instance nếu chưa có cơ chế fencing/ownership.
5. Không xóa provider resource chỉ vì broker registration đã bị gỡ.
6. Không xóa state store hoặc secret reference trước khi xác nhận bàn giao/retention.
7. Không làm mất khả năng deprovision và xử lý security incident trong thời gian chuyển tiếp.
8. Mọi quyết định giữ, chuyển, export hoặc xóa dữ liệu phải có audit và owner.

Có thể dùng một câu hỏi kiểm soát cho từng instance: **nếu platform gửi DELETE hoặc người dùng cần revoke một binding ngay bây giờ, hệ thống nào sẽ xử lý và tìm được provider resource nào?** Nếu chưa có câu trả lời cụ thể, chưa thể coi instance đó đã được bàn giao.

## 3. Chọn chiến lược bàn giao phù hợp

Không phải mọi broker đều cần di chuyển backend resource. Có thể giữ nguyên resource và chỉ chuyển quyền quản lý, hoặc chuyển cả dữ liệu lẫn resource sang provider khác.

| Chiến lược | Cách làm | Khi phù hợp | Rủi ro chính |
|---|---|---|---|
| In-place ownership transfer | Broker mới tiếp quản cùng provider resource và state | Provider resource giữ nguyên, API tương thích | Mapping/state thiếu hoặc hai broker cùng thao tác |
| Shared state cutover | Broker mới dùng cùng state store sau khi có fencing | Cùng schema hoặc đã có migration an toàn | Schema compatibility và dual writer |
| Export/import state | Snapshot metadata và import vào store mới | Hệ thống tách database hoặc thay nền tảng | Snapshot không nhất quán, thiếu binding/operation |
| Blue-green broker | Broker mới chạy song song, chuyển traffic theo từng scope | Cần giảm downtime và rollback | Hai broker cùng nhận request hoặc dùng secret khác nhau |
| Backend resource migration | Tạo resource mới, migrate data, chuyển consumer | Thay provider/region/engine | Downtime, data consistency, credential rotation |
| Customer-managed handover | Export dữ liệu và hướng dẫn khách hàng tự chuyển | Không thể giữ tương thích hoặc dịch vụ kết thúc | Khách hàng phải phối hợp nhiều bước |

### In-place handover

Broker mới tiếp quản resource ID hiện tại, giữ instance ID/plan mapping cần thiết và tiếp tục phục vụ API. Đây thường là lựa chọn ít ảnh hưởng nhất nếu provider API và mô hình dữ liệu tương thích.

### Backend migration

Broker mới provision resource mới, chuyển dữ liệu và binding rồi mới ngừng resource cũ. Cần có chiến lược consistency như replication, change data capture, freeze writes hoặc maintenance window. Không coi việc import metadata broker là đã chuyển dữ liệu backend.

### Customer handover

Nếu khách hàng phải tự chuyển sang dịch vụ khác, cần cung cấp export, lịch kết thúc, hướng dẫn connection string mới, thời gian song song, cách kiểm tra dữ liệu và ngày thu hồi resource cũ. Không giữ credential cũ vô thời hạn chỉ để khách hàng có thể quay lại.

## 4. Kiểm kê đầy đủ trước khi thông báo retirement

Bắt đầu bằng inventory có thể truy vết, lấy từ state store, provider inventory và platform records. Không chỉ đếm service instance.

### Dữ liệu cần kiểm kê

| Nhóm | Dữ liệu |
|---|---|
| Catalog | Service ID, plan ID, bindable, schemas, capabilities, dashboard URL/client và phiên bản contract |
| Instance | External instance ID, internal ID, service/plan ID, tenant, platform registration, region, lifecycle state |
| Binding | Binding ID, parent instance, consumer identity, credential reference, binding state |
| Operation | Operation ID, type, state, retry count, provider operation ID, thời điểm tạo/cập nhật |
| Provider resource | Resource ID, account/project, region, network, encryption key, tags và dependencies |
| Credential | Secret reference/version, expiry, rotation state, scope và consumer cần cập nhật |
| Quota | Used, reserved, limit, reservation owner và quota cần giữ cho cleanup |
| Data | Backup, retention, encryption, replication, export format và data owner |
| Platform | Broker registration, endpoint, authentication, platform ID, service access và visibility |
| Contract | SLA, support contact, migration notice, legal hold và thời hạn kết thúc |

Cần đối chiếu ba nguồn:

- State store của broker: instance, binding, operation và ownership.
- Provider inventory: tài nguyên thực sự tồn tại, kể cả tài nguyên broker không còn record.
- Platform inventory: service instance/binding mà platform cho rằng đang được cung cấp.

Chênh lệch giữa các nguồn là việc cần xử lý trước cutover. Ví dụ provider có database nhưng broker không có instance record có thể là orphan; broker có instance ACTIVE nhưng provider resource không tồn tại có thể là state drift. Không tự động xóa hoặc bỏ qua các record lệch nhau.

### Phân nhóm tài nguyên

Mỗi instance nên được xếp vào một nhóm:

- ACTIVE_AND_IN_USE: đang phục vụ consumer.
- IDLE_OR_UNUSED: không có consumer hoạt động nhưng vẫn được khách hàng giữ.
- PROVISIONING_OR_UPDATING: có operation chưa terminal.
- DEPROVISIONING: đang thu hồi.
- FAILED_OR_UNKNOWN: kết quả provider chưa xác định.
- MIGRATION_REQUIRED: cần chuyển resource/data.
- HANDOVER_READY: đã đủ điều kiện để broker mới nhận ownership.
- RETIREMENT_BLOCKED: có legal hold, lỗi provider, thiếu mapping hoặc owner chưa xác nhận.

Nhóm này giúp lập kế hoạch theo rủi ro thay vì xử lý tất cả instance theo một lệnh bulk.

## 5. Thiết kế trạng thái retirement

Nên quản lý trạng thái ngừng broker bằng một workflow có persistence và audit. Ví dụ:

~~~mermaid
stateDiagram-v2
    [*] --> ACTIVE
    ACTIVE --> ANNOUNCED
    ANNOUNCED --> PROVISION_FROZEN
    PROVISION_FROZEN --> DRAINING
    DRAINING --> HANDOVER_READY
    HANDOVER_READY --> CUTOVER
    CUTOVER --> READ_ONLY
    READ_ONLY --> DEREGISTERED
    DEREGISTERED --> CLEANED
    DRAINING --> RETIREMENT_BLOCKED
    HANDOVER_READY --> RETIREMENT_BLOCKED
    RETIREMENT_BLOCKED --> DRAINING
    RETIREMENT_BLOCKED --> HANDOVER_READY
    ANNOUNCED --> ACTIVE: cancel retirement
    PROVISION_FROZEN --> ACTIVE: rollback before cutover
~~~

| Trạng thái | Ý nghĩa | Hành vi chính |
|---|---|---|
| ACTIVE | Broker hoạt động bình thường | Catalog và lifecycle operations theo policy |
| ANNOUNCED | Đã công bố lịch kết thúc | Thông báo, inventory và migration support |
| PROVISION_FROZEN | Không nhận provision mới cho scope được retire | Existing instance vẫn được phục vụ |
| DRAINING | Chờ operation hoàn tất và xử lý retry | Không nhận workload mới; tiếp tục cleanup |
| HANDOVER_READY | Snapshot, mapping và owner đã được xác minh | Có thể chuyển quyền |
| CUTOVER | Broker mới nhận quyền ghi | Broker cũ bị fence |
| READ_ONLY | Broker cũ chỉ phục vụ tra cứu/đối soát theo kế hoạch | Không tạo thay đổi mới |
| DEREGISTERED | Đã gỡ registration khỏi platform | Giữ dữ liệu phục vụ retention và incident |
| CLEANED | Đã kết thúc retention và xóa phần được phép | Chỉ sau khi xác nhận resource/credential |

Đây là state machine nội bộ, không phải các trạng thái OSB API bắt buộc. Cần lưu thời điểm chuyển, actor, lý do, phạm vi service/plan/platform và kết quả kiểm tra. Nếu retirement bị hủy trước cutover, có thể quay về ACTIVE sau khi xác minh catalog và request routing. Sau cutover, rollback phải có ownership transfer ngược rõ ràng.

## 6. Lập lịch và thông báo cho người sử dụng

Retirement ảnh hưởng đến platform operator, tenant administrator, application team, support và provider team. Thông báo nên có:

- Service/plan/platform bị ảnh hưởng.
- Thời điểm ngừng provision mới.
- Thời điểm ngừng update hoặc thay đổi cấu hình nếu có.
- Thời điểm cutover và thời gian có thể gián đoạn.
- Ngày cuối cùng có thể bind/unbind hoặc deprovision qua broker cũ.
- Phương án thay thế và điều kiện tương thích.
- Cách export dữ liệu, backup và kiểm tra restore.
- Cách chuyển connection credentials và consumer configuration.
- Support contact, escalation và incident channel.
- Ngày xóa tài nguyên/credential nếu khách hàng không thực hiện hành động.

Thông báo phải phân biệt ngày ngừng bán plan với ngày kết thúc hỗ trợ instance đang hoạt động. Nếu khách hàng không cần migration vì broker mới tiếp quản nguyên trạng, hãy nói rõ điều đó và nêu những thay đổi mà consumer vẫn phải thực hiện, nếu có.

Không cam kết thời gian migration trước khi thử nghiệm với dữ liệu và provider resource đại diện. Với service stateful, cần xác định downtime, RPO, RTO và cách xử lý write traffic trong cutover.

## 7. Ngừng nhận provision mới nhưng vẫn phục vụ instance cũ

Đây là giai đoạn dễ bị triển khai sai. Khi đã freeze provision, broker vẫn có thể cần xử lý:

- GET catalog hoặc catalog filtering theo chính sách platform.
- Retrieve instance nếu broker hỗ trợ.
- Last operation cho operation đang chạy.
- Bind/unbind theo thời gian chuyển tiếp đã công bố.
- Update nếu policy cho phép và operation không xung đột.
- Deprovision để khách hàng có thể kết thúc resource.
- Retry/reconciliation của operation đã được chấp nhận.

Không nhất thiết giữ mọi capability mở đến ngày cuối; quyết định phải theo kế hoạch và platform contract. Tuy nhiên, nếu tắt toàn bộ endpoint ngay sau khi ngừng provision, platform có thể không thể unbind/deprovision hoặc nhận kết quả operation.

### Broker lifecycle gate

Có thể thêm policy state ở application service:

~~~java
public Mono<Void> assertProvisionAllowed(
        String serviceId,
        String planId) {

    return retirementPolicy.currentState(serviceId, planId)
        .flatMap(state -> {
            if (state == RetirementState.ACTIVE
                    || state == RetirementState.ANNOUNCED) {
                return Mono.empty();
            }

            return Mono.error(
                new ServiceOfferingRetiredException(serviceId, planId)
            );
        });
}
~~~

Ví dụ chỉ minh họa policy nội bộ. Cần quyết định rõ ANNOUNCED còn cho phép provision hay không. Khi PROVISION_FROZEN, chặn request provision mới trước khi reserve quota hoặc gọi provider. Không để catalog vẫn công bố plan có thể provision trong khi backend từ chối không có thông báo hoặc error mapping nhất quán.

Đối với deprovision, không áp dụng cùng gate với provision. Quyền thu hồi resource thường phải tiếp tục được duy trì trong giai đoạn retirement, trừ khi có quy trình cleanup thay thế đã được xác minh.

## 8. Drain operation đang chạy

Trước khi chuyển ownership, phải biết operation nào đang chạy và có thể kết thúc an toàn.

1. Chặn tạo operation mới trong scope đã freeze.
2. Liệt kê operation ACCEPTED, QUEUED, IN_PROGRESS và RETRY_WAIT.
3. Xác định worker owner, lease, retry schedule và provider operation ID.
4. Đợi operation bình thường hoàn tất trong time budget.
5. Với operation quá hạn, kiểm tra provider state trước khi retry.
6. Đưa unknown outcome vào reconciliation queue.
7. Xác nhận không còn worker nào giữ lease hoặc đang ghi state cho instance sẽ chuyển.
8. Lưu trạng thái cuối cùng và operation history vào handover snapshot.

Không xóa job queue hoặc reset operation thành FAILED chỉ để làm inventory trống. Một create timeout có thể đã tạo resource thành công ở provider; nếu broker mới không biết provider operation ID hoặc idempotency key, retry có thể tạo resource trùng.

### Điều kiện hoàn tất drain

Một scope chỉ nên chuyển HANDOVER_READY khi:

- Không còn operation đang chạy hoặc mọi operation còn lại đã có owner tiếp nhận.
- Không có message bị bỏ sót trong retry/DLQ.
- Worker lease được release hoặc fencing token đã vô hiệu hóa.
- Unknown provider outcomes được reconcile hoặc có kế hoạch xử lý.
- State store và provider inventory đã được đối chiếu.
- Binding và credential có trạng thái rõ ràng.
- Snapshot có version, checksum và thời điểm tạo.

Nếu không thể drain một operation, phải chuyển thành blocker có owner và deadline, không âm thầm bỏ qua.

## 9. Bàn giao state store và mapping

State store là bản đồ cho biết broker quản lý resource nào và cần gọi provider bằng thông tin gì. Bàn giao thiếu một bảng phụ cũng có thể làm mất khả năng deprovision hoặc revoke credential.

### Những dữ liệu phải chuyển

- Instance identity và external ID.
- Internal ID và tenant/platform ownership.
- Service ID, plan ID và catalog version.
- Provider resource ID và provider account/region.
- Provision parameters đã được chuẩn hóa, loại bỏ secret.
- Binding records và secret references.
- Operation history, last operation state và provider operation ID.
- Idempotency keys/fingerprints và kết quả request trước đó.
- Quota reservation và cleanup responsibility.
- Dashboard references, metadata và audit correlation.
- Retirement/handover status và ownership version.

Không export secret value vào file CSV hoặc artifact thông thường. Chuyển secret qua secret manager replication, vault export được mã hóa hoặc quy trình credential rotation có kiểm soát. Snapshot chứa thông tin nhạy cảm cần mã hóa, giới hạn quyền đọc và ghi nhận người nhận.

### Version hóa snapshot

Ví dụ manifest snapshot:

~~~json
{
  "snapshot_version": 3,
  "source_broker": "broker-v1",
  "target_broker": "broker-v2",
  "created_at": "2026-11-27T10:00:00Z",
  "scope": {
    "platform_id": "cf-prod-a",
    "service_ids": ["svc-postgresql"]
  },
  "instance_count": 128,
  "binding_count": 294,
  "operation_count": 0,
  "checksum": "sha256:..."
}
~~~

Manifest chỉ là ví dụ. Snapshot cần có schema version, source/target identity, scope, record counts, checksum, encryption metadata và trạng thái validation. Không đưa credential value vào manifest.

Broker mới phải kiểm tra snapshot trước import: version được hỗ trợ, checksum hợp lệ, duplicate key, foreign key, reference tới provider account và dữ liệu bắt buộc. Import nên idempotent để có thể chạy lại sau lỗi mà không nhân đôi record.

## 10. Ngăn hai broker cùng quản lý một resource

Blue-green deployment có thể khiến broker cũ và broker mới cùng chạy. Nếu cả hai cùng nhận request hoặc cùng chạy worker, có thể tạo hai operation cạnh tranh, xóa resource đang được cập nhật hoặc ghi đè state.

Cần cơ chế ownership/fencing:

- Mỗi instance có owner broker ID.
- Mỗi lần chuyển ownership tăng ownership epoch/version.
- Worker chỉ thực hiện operation nếu epoch của job còn khớp epoch hiện tại.
- Database update dùng compare-and-set hoặc optimistic locking.
- Lease có expiry và fencing token; chỉ lease holder mới có quyền ghi.
- Broker cũ bị chặn ghi sau khi cutover.
- Provider call có idempotency key nếu provider hỗ trợ.

Ví dụ record:

~~~java
public record ResourceOwnership(
    UUID instanceId,
    String ownerBrokerId,
    long ownershipEpoch,
    Instant transferredAt
) {}
~~~

Khi broker mới tiếp quản, transaction cập nhật ownerBrokerId và tăng ownershipEpoch. Worker cũ có epoch thấp hơn phải dừng trước khi thay đổi state. Chỉ kiểm tra process đang chạy hay không là chưa đủ; worker cũ có thể tiếp tục sau network partition hoặc pause dài.

Nếu broker cũ và mới dùng hai state store khác nhau, cần có thời điểm cutover có fencing rõ ràng. Không cho cả hai ghi độc lập rồi hy vọng eventual consistency tự giải quyết conflict.

## 11. Giữ tương thích ID và contract OSB

Platform và consumer có thể lưu service instance ID, binding ID, service ID và plan ID. Đổi các giá trị này tùy tiện có thể làm platform không tìm được resource hoặc gửi request đến sai broker.

### Giữ ID khi có thể

Nếu service semantics không đổi, ưu tiên giữ ổn định:

- Service ID.
- Plan ID.
- External instance ID.
- Binding ID.
- Operation identity hoặc mapping sang operation mới.
- Dashboard URL/reference nếu người dùng đã lưu.

ID ổn định giúp giảm thay đổi platform-side. Tuy nhiên, giữ ID không có nghĩa service/plan implementation hoàn toàn tương thích. Broker mới phải hiểu metadata và parameters đã được broker cũ tạo ra.

### Khi cần đổi ID

Nếu service hoặc plan thay đổi semantics, hãy tạo mapping tường minh:

| ID cũ | ID mới | Quy tắc |
|---|---|---|
| svc-postgresql-v1 | svc-postgresql-v2 | Chỉ map nếu resource và API contract tương thích |
| plan-standard-v1 | plan-standard-v2 | Kiểm tra capacity, pricing, backup và SLA |
| old-instance-id | internal-instance-id | Giữ external ID hoặc mapping không mất tính duy nhất |
| old-binding-id | new-binding-id | Duy trì consumer reference và revoke path |

OSB API không cung cấp thao tác chung để platform tự thay service ID/plan ID của instance. Nếu cần thay đổi ID mà platform lưu, phải dùng migration workflow của platform hoặc yêu cầu tạo service instance mới và chuyển consumer theo quy trình được hỗ trợ.

Không trả một service ID mới cho instance cũ trong response chỉ để che việc mapping chưa hoàn tất.

## 12. Bàn giao provider resource mà không tạo resource trùng

Nếu provider resource vẫn tồn tại, broker mới nên tiếp quản bằng provider resource ID hiện có thay vì provision thêm một resource mới.

Bàn giao cần xác minh:

- Resource ID thực tế tồn tại.
- Resource nằm trong đúng account/project/region.
- Resource thuộc tenant/platform scope dự kiến.
- Tags/labels owner được cập nhật theo policy.
- Network, encryption key và IAM permission còn hiệu lực.
- Provider API version được broker mới hỗ trợ.
- Broker mới có credential đủ quyền quản lý và cleanup.
- Resource state phù hợp với state store.
- Quota reservation và billing ownership đã được chuyển.

Một adapter import/attach có thể dùng provider API để đọc resource và tạo record mapping. Không dùng thao tác create thay cho attach nếu provider resource đã có; điều này tránh tạo database, cluster hoặc bucket thứ hai.

Nếu provider không hỗ trợ transfer ownership, có thể cần chia sẻ account, tạo role mới hoặc thực hiện migration resource. Đó là quyết định provider-specific và phải được thử nghiệm trước.

## 13. Bàn giao binding và credential đang được consumer sử dụng

Binding thường chứa credential hoặc thông tin kết nối mà ứng dụng đang dùng. Đây là phần dễ gây outage nhất nếu rotate hoặc revoke không đúng thời điểm.

### Các phương án

1. **Giữ nguyên credential:** broker mới tiếp quản secret reference và quyền quản lý credential hiện tại.
2. **Credential overlap:** tạo credential mới, cho phép cũ và mới cùng hoạt động trong thời gian ngắn, cập nhật consumer rồi revoke cũ.
3. **Rebind/recreate binding:** tạo binding mới qua platform workflow, cập nhật application, sau đó unbind binding cũ.
4. **Customer-managed migration:** cung cấp thông tin và lịch để ứng dụng tự cập nhật secret/connection.

Không ghi credential vào snapshot dạng plaintext. Cần chuyển secret reference hoặc sử dụng secret manager replication. Broker mới phải chứng minh có thể đọc/rotate/revoke credential trước khi nhận ownership binding.

### Trình tự rotation an toàn

~~~mermaid
sequenceDiagram
    participant Old as Broker cũ
    participant New as Broker mới
    participant SM as Secret Manager
    participant App as Consumer
    participant DB as Provider

    Old->>New: Bàn giao binding metadata và secret reference
    New->>SM: Kiểm tra quyền đọc version hiện tại
    New->>DB: Xác minh credential hiện tại
    New->>DB: Tạo credential mới nếu cần
    New->>SM: Lưu version mới
    New-->>App: Phát hành thông tin cập nhật theo platform workflow
    App->>DB: Kết nối bằng credential mới
    New->>DB: Xác minh hoạt động mới
    New->>DB: Revoke credential cũ
~~~

Không revoke credential cũ ngay sau khi tạo credential mới. Phải xác nhận consumer đã chuyển và có thể kết nối. Nếu platform quản lý việc phân phối binding credentials, thực hiện rotation qua workflow của platform để app nhận cập nhật đúng cách.

Khi service ngừng hoàn toàn, phải thu hồi credential và certificate còn hiệu lực, xóa token tạm, cập nhật firewall/IAM và xác nhận không còn consumer dùng endpoint cũ.

## 14. Bảo vệ dữ liệu và backup trong quá trình chuyển

Với database, object storage hoặc message broker stateful, migration metadata và migration data là hai công việc riêng.

### Kế hoạch dữ liệu

- Xác định data owner, data classification và retention.
- Chọn full backup, snapshot, replication hoặc change data capture.
- Xác định RPO/RTO và downtime cho từng plan.
- Mã hóa dữ liệu khi truyền và lưu.
- Kiểm tra encryption key có thể được broker mới/provider mới sử dụng.
- Chạy checksum hoặc validation record count.
- Thử restore vào môi trường cô lập.
- Có cutover window và freeze write nếu cần.
- Có rollback hoặc forward-fix plan.
- Xác định khi nào được xóa bản cũ.

Nếu dùng replication, phải đo replication lag trước khi chuyển write traffic. Khi freeze writes, xác nhận consumer không còn ghi vào source hoặc có cơ chế dual-write/CDC đã kiểm chứng. Không chỉ so sánh số lượng file; cần xác minh schema, index, transaction log và dữ liệu nghiệp vụ quan trọng.

### Không xóa bản nguồn quá sớm

Giữ backup/snapshot nguồn trong retention đã thống nhất. Chỉ xóa sau khi owner xác nhận dữ liệu đích đủ, ứng dụng hoạt động, thời hạn rollback hết và legal hold cho phép. Broker retirement không phải căn cứ để bỏ qua chính sách lưu trữ dữ liệu.

## 15. Tích hợp Cloud Foundry khi retire broker

Cloud Foundry quản lý service broker registration và các service/plan mà broker công bố. Cách xử lý broker deregistration, visibility, instance dependencies và service lifecycle có thể phụ thuộc phiên bản Cloud Controller/CAPI và cách operator quản lý foundation.

Một quy trình an toàn:

1. Liệt kê broker registration và service offerings trên foundation.
2. Xác định service instances, bindings và async operations còn tồn tại.
3. Kiểm tra behavior của phiên bản Cloud Controller khi service broker bị xóa hoặc service/plan bị thay đổi.
4. Freeze provision mới theo kế hoạch và xác minh Apps Manager/CLI không còn quảng bá offering đã ngừng.
5. Duy trì broker endpoint và authentication trong khi platform còn cần gọi lifecycle API.
6. Nếu thay broker, cập nhật registration hoặc routing theo kế hoạch có kiểm soát; xác minh instance cũ được route đến implementation có state tương ứng.
7. Kiểm tra binding credentials và app environment sau cutover.
8. Chỉ deregister broker cũ khi không còn instance cần broker đó hoặc đã có cơ chế platform-supported để chuyển quyền.
9. Giữ audit và export record theo retention.

Không giả định rằng xóa broker registration sẽ tự động xóa provider resource, chuyển instance sang broker mới hoặc giữ nguyên khả năng deprovision. Trước khi chạy lệnh deregister/delete trên production, thử nghiệm hành vi trên foundation cùng phiên bản và đọc kết quả inventory.

### Dashboard và service access

Nếu broker cung cấp dashboard URL hoặc Dashboard SSO, cần bàn giao:

- Dashboard hostname và TLS certificate.
- UAA/dashboard client registration.
- Redirect URI và secret rotation.
- Instance reference mapping.
- Permission check và ownership scope.
- Audit, session và access policy.

Không để dashboard cũ hiển thị quyền manage sau khi ownership đã chuyển sang broker mới. Dashboard phải tra cứu owner hiện tại hoặc redirect sang giao diện mới theo mapping được xác minh.

## 16. Tích hợp Kubernetes và operator-based platform

Nếu broker được gọi qua controller/operator trong Kubernetes, việc gỡ deployment quá sớm có thể làm các resource finalizer bị kẹt hoặc không thể cleanup.

Kiểm tra:

- Custom Resource instances còn tồn tại.
- ServiceBinding hoặc Secret liên quan.
- Finalizers cần controller xử lý.
- CRD versions và conversion webhook.
- Admission webhook và service endpoint.
- RBAC/service account của controller cũ và mới.
- Namespace, cluster scope và owner references.
- Queue/job đang reconcile.
- Secret references và provider credentials.
- Helm release/operator subscription và uninstall order.

### Finalizer

Một finalizer thường giữ resource ở trạng thái deletion pending cho đến khi controller hoàn tất cleanup. Nếu xóa controller trước, resource có thể ở Terminating vô hạn. Trước khi uninstall:

1. Dừng tạo Custom Resource mới theo policy.
2. Để controller xử lý hoặc chuyển finalizer responsibility sang controller mới.
3. Xác minh provider resource đã được chuyển hoặc thu hồi.
4. Kiểm tra không còn finalizer do controller cũ sở hữu.
5. Chỉ xóa CRD/webhook sau khi không còn custom resource cần chúng.

Không xóa finalizer hàng loạt chỉ để namespace hoặc Helm release kết thúc. Nếu bỏ finalizer mà không cleanup provider, backend resource có thể bị orphan.

### CRD version handover

Nếu broker/operator mới dùng CRD schema khác, cần version conversion hoặc migration dữ liệu. Xác minh mọi stored object được đọc/ghi bởi version mới; kiểm tra webhook còn sẵn sàng trong toàn bộ migration. Không xóa CRD version cũ trước khi mọi object đã được chuyển và clients không còn sử dụng version đó.

## 17. Thiết kế cutover blue-green

Một cutover có thể chia thành các bước:

~~~mermaid
flowchart TD
    A["Inventory and baseline"] --> B["Deploy broker mới ở chế độ shadow"]
    B --> C["Import snapshot và validate"]
    C --> D["Kiểm tra provider access và permissions"]
    D --> E["Freeze writes từ broker cũ"]
    E --> F["Drain operations và release leases"]
    F --> G["Chuyển ownership epoch"]
    G --> H["Route requests sang broker mới"]
    H --> I["Smoke test lifecycle và polling"]
    I --> J["Giữ broker cũ read-only trong retention window"]
    J --> K["Deregister và cleanup theo phê duyệt"]
~~~

### Shadow phase

Broker mới đọc snapshot hoặc provider inventory nhưng chưa ghi resource. So sánh kết quả retrieve, plan mapping, binding metadata và operation state với broker cũ. Không để shadow broker gọi create/delete thật.

### Freeze and fencing

Tại thời điểm cutover:

- Tắt nhận request mutation mới ở broker cũ theo scope.
- Drain operation.
- Dừng/release worker lease.
- Tăng ownership epoch trong transaction.
- Chuyển routing.
- Broker mới xác minh epoch trước mỗi write.
- Broker cũ từ chối mutation nếu epoch không còn thuộc nó.

### Smoke test

Thực hiện trên instance canary hoặc tenant thử nghiệm:

- Retrieve instance.
- Read last operation.
- Bind/unbind nếu workflow cho phép.
- Update một thuộc tính không phá hủy nếu có.
- Kiểm tra provider identity và quota.
- Deprovision một resource thử nghiệm riêng.
- Xác nhận audit và metrics ghi nhận broker mới.

Không dùng production resource đang phục vụ ứng dụng để thử deprovision.

## 18. Rollback và forward recovery

Rollback phải được thiết kế trước cutover. Sau khi broker mới nhận write, broker cũ không thể đơn giản bật lại vì state và provider resource có thể đã thay đổi.

### Điều kiện rollback

- Broker mới chưa tạo thay đổi không thể đảo ngược hoặc đã có cách reconcile.
- Snapshot/CDC đủ để broker cũ đọc trạng thái mới.
- Ownership epoch có thể chuyển ngược an toàn.
- Provider credential cũ còn hiệu lực hoặc có thể cấp lại.
- Routing có thể quay về.
- Không có operation đang chạy bị mất owner.

### Quy trình rollback

1. Freeze mutation ở broker mới.
2. Drain/reconcile operation mới phát sinh.
3. Export delta state và provider mapping từ broker mới.
4. Import delta vào broker cũ hoặc chuẩn bị một broker phục hồi.
5. Chuyển ownership epoch về owner mới được chỉ định.
6. Cập nhật routing và xác minh read/operation.
7. Mở lại mutation theo từng scope.
8. Thông báo incident và theo dõi reconciliation.

Nếu resource đã được thay đổi bởi broker mới, có thể an toàn hơn khi forward-fix trên broker mới thay vì rollback. Không chuyển quyền về broker cũ nếu nó không hiểu schema hoặc provider state mới.

## 19. Gỡ broker và cleanup cuối cùng

Chỉ thực hiện deregistration và cleanup sau khi có bằng chứng:

- Không còn instance cần broker cũ xử lý, hoặc platform đã chuyển routing/ownership theo cơ chế được hỗ trợ.
- Không còn binding cần credential cleanup.
- Không còn operation đang chạy hoặc operation còn lại có owner mới.
- Provider inventory đã đối chiếu với state store.
- Quota reservation và billing responsibility đã chuyển.
- Backup/export đã được xác minh.
- Platform operator và service owner chấp thuận.
- Monitoring không còn alert về instance/worker thuộc broker cũ.
- Retention/legal hold cho phép xóa dữ liệu.

Sau deregistration, giữ lại package/config cần thiết để khôi phục hoặc điều tra theo retention. Thu hồi broker API credentials, provider service accounts, certificates, dashboard clients, webhook secrets và network allowlist theo từng giai đoạn. Trước khi revoke, xác minh không còn workload khác dùng chung credential.

Không xóa secret store namespace hoặc database schema chỉ vì deployment đã scale về zero. Cleanup phải dựa trên inventory và owner sign-off.

## 20. Bảng phân công trách nhiệm

Retirement thường liên quan nhiều nhóm. RACI đơn giản giúp tránh khoảng trống ownership:

| Công việc | Broker team | Platform team | Provider team | Service owner |
|---|---|---|---|---|
| Inventory instance/binding | R | C | C | A |
| Freeze provision | R | A/C | C | I |
| Drain operation | R/A | I | C | I |
| Export/import broker state | R/A | C | C | I |
| Provider resource transfer | C | I | R/A | C |
| Consumer credential migration | R | C | C | A |
| Platform routing/deregistration | C | R/A | I | I |
| Data validation/acceptance | C | I | R | A |
| Final cleanup | R | C | R | A |
| Audit/retention sign-off | R | C | C | A |

R = Responsible, A = Accountable, C = Consulted, I = Informed. Điều chỉnh theo tổ chức. Mỗi resource/tenant cần một owner cụ thể; không để việc bàn giao chỉ được xác nhận ở cấp dự án mà thiếu người chịu trách nhiệm từng instance.

## 21. Ví dụ retirement registry trong broker

Có thể quản lý trạng thái retirement ở database:

~~~java
public enum RetirementState {
    ACTIVE,
    ANNOUNCED,
    PROVISION_FROZEN,
    DRAINING,
    HANDOVER_READY,
    CUTOVER,
    READ_ONLY,
    DEREGISTERED,
    CLEANED,
    BLOCKED
}

public record BrokerRetirementScope(
    String platformId,
    String serviceId,
    Set<String> planIds,
    RetirementState state,
    Instant effectiveAt,
    String targetBrokerId,
    long ownershipEpoch
) {}
~~~

Service dùng registry để kiểm tra action:

~~~java
public Mono<Void> assertActionAllowed(
        BrokerAction action,
        RetirementState state) {

    if (state == RetirementState.ACTIVE) {
        return Mono.empty();
    }

    if (action == BrokerAction.DEPROVISION
            || action == BrokerAction.UNBIND
            || action == BrokerAction.GET_LAST_OPERATION) {
        return Mono.empty();
    }

    if (state == RetirementState.PROVISION_FROZEN
            || state == RetirementState.DRAINING) {
        return Mono.error(new ServiceOfferingRetiredException());
    }

    return Mono.error(new BrokerRetiredException());
}
~~~

Đây là pseudocode chính sách. Thực tế cần phân biệt update/retrieve/bind theo thời gian chuyển tiếp và platform behavior. Deprovision/unbind thường phải tiếp tục được hỗ trợ để cleanup, nhưng chỉ mở nếu broker còn đủ state/provider access và có authorization hợp lệ.

Retirement registry cần lưu actor, timestamp, reason, target broker, scope và policy version. Mọi thay đổi trạng thái nên là transition có điều kiện, tránh hai operator cùng chuyển trạng thái theo thứ tự không mong muốn.

## 22. Kiểm thử kế hoạch handover

Không nên chỉ test rằng broker mới khởi động thành công. Cần test toàn bộ đường chuyển quyền và tình huống lỗi.

| Ca kiểm thử | Cách thực hiện | Kết quả mong đợi |
|---|---|---|
| Inventory completeness | So sánh broker DB, platform và provider inventory | Chênh lệch được liệt kê, có owner |
| Provision freeze | Gửi provision sau cutoff | Bị từ chối đúng contract, không gọi provider |
| Existing deprovision | Gửi DELETE instance cũ | Broker có owner hợp lệ xử lý cleanup |
| In-flight operation | Cutover khi operation đang chạy | Drain hoặc chuyển owner không mất job |
| Unknown provider outcome | Giả lập timeout sau create | Reconcile trước retry, không tạo resource trùng |
| Snapshot checksum | Sửa một byte snapshot | Import bị từ chối |
| Snapshot schema version | Import version không hỗ trợ | Dừng trước khi ghi state |
| Duplicate import | Import cùng snapshot hai lần | Idempotent, không nhân bản record |
| Ownership fencing | Worker cũ chạy sau cutover | Epoch cũ bị từ chối |
| Dual writer | Cả hai broker gửi mutation | Chỉ owner hiện tại được ghi |
| Binding credential | Chuyển secret reference | Broker mới đọc và xác minh được |
| Credential rotation | Candidate lỗi hoặc consumer chưa đổi | Không revoke credential cũ quá sớm |
| Provider attach | Import resource đã tồn tại | Không tạo resource mới |
| Cloud Foundry deregistration | Thử trên foundation cùng version | Behavior và dependency được xác minh |
| Kubernetes finalizer | Controller cũ dừng trong khi delete | Finalizer được controller có owner xử lý |
| CRD conversion | Upgrade stored object version | Không mất field hoặc reference |
| Rollback | Lỗi sau cutover canary | Ownership/routing trở về trạng thái có kiểm soát |
| Final cleanup | Inventory không còn owner cũ | Chỉ xóa thành phần đủ điều kiện |
| Security audit | Thực hiện transfer/revoke | Có actor, target, reason và correlation |
| Recovery drill | Restore snapshot và provider mapping | Có thể khôi phục trong RTO đã định |

Test nên dùng provider fake hoặc sandbox và resource riêng. Không dùng production resource đang phục vụ ứng dụng làm fixture cho test deprovision.

## 23. Checklist trước, trong và sau cutover

### Trước cutover

- [ ] Phạm vi retirement và ngày cutoff được phê duyệt.
- [ ] Platform/provider behavior đã được xác minh theo version.
- [ ] Inventory instance, binding, operation và resource hoàn chỉnh.
- [ ] Owner từng resource/tenant được xác định.
- [ ] Broker mới có catalog/plan compatibility và provider access.
- [ ] Snapshot/export đã kiểm checksum và thử import.
- [ ] Credential và secret references đã được bàn giao an toàn.
- [ ] Backup, RPO/RTO, rollback và support window đã được xác định.
- [ ] Alert và dashboard có thể phân biệt broker cũ/mới.

### Trong cutover

- [ ] Provision mới đã freeze đúng scope.
- [ ] Operation được drain hoặc có owner chuyển tiếp.
- [ ] Worker lease và fencing token được kiểm tra.
- [ ] State import và provider resource mapping được xác minh.
- [ ] Ownership epoch được chuyển nguyên tử.
- [ ] Routing sang broker mới hoạt động.
- [ ] Smoke test retrieve, bind/unbind, polling và cleanup đã đạt.
- [ ] Consumer credential hoạt động sau chuyển đổi.

### Sau cutover

- [ ] Broker mới là owner duy nhất cho mỗi resource.
- [ ] Không có operation hoặc queue message bị bỏ lại.
- [ ] Quota, billing, audit và monitoring đã chuyển.
- [ ] Broker cũ ở trạng thái read-only/fenced.
- [ ] Platform registration cũ chỉ được gỡ sau khi dependency đã hết.
- [ ] Provider credential, certificate và dashboard client cũ được thu hồi đúng thời điểm.
- [ ] Backup/retention được giữ theo policy.
- [ ] Owner xác nhận dịch vụ hoạt động và incident window kết thúc.

## 24. Những lỗi thường gặp khi ngừng broker

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Xóa deployment trước khi inventory | Không còn nơi biết resource ID và credential reference | Inventory và export trước |
| Nghĩ deregister broker sẽ cleanup resource | Provider resource có thể bị orphan | Xác minh platform/provider và cleanup riêng |
| Gỡ catalog rồi tắt mọi endpoint | Instance cũ không thể unbind/deprovision | Duy trì lifecycle path đến cutoff |
| Chuyển state nhưng quên operation | Last operation và retry mất tính nhất quán | Bàn giao operation history/queue |
| Hai broker cùng ghi resource | State race và thao tác phá hủy | Ownership epoch và fencing |
| Import thiếu binding | Consumer vẫn dùng credential nhưng broker không thể revoke | Đối chiếu binding inventory |
| Revoke secret cũ quá sớm | Ứng dụng mất kết nối | Credential overlap và consumer verification |
| Chỉ chuyển metadata, không chuyển data | Ứng dụng mới nhìn thấy resource nhưng dữ liệu thiếu | Data migration/validation riêng |
| Xóa controller trước finalizer | Kubernetes resource bị Terminating vô hạn | Chuyển finalizer responsibility trước |
| Xóa CRD quá sớm | Mất khả năng đọc/migrate object | Convert và xác minh object trước |
| Giữ broker cũ chạy song song không fencing | Dual writer và duplicate provider calls | Shadow read, freeze, epoch cutover |
| Không có rollback | Một lỗi cutover kéo dài outage | Diễn tập rollback hoặc forward recovery |
| Xóa backup/secret store ngay | Mất khả năng khôi phục hoặc xử lý incident | Retention và sign-off |
| Không chỉ định owner sau bàn giao | Resource không ai chịu trách nhiệm | Gắn owner và SLA cho từng scope |

## 25. Nguyên tắc cần ghi nhớ

Ngừng service broker là quá trình chuyển trách nhiệm vận hành, không chỉ là tắt một ứng dụng. Các service instance và binding có thể tiếp tục được sử dụng lâu sau khi broker ngừng nhận provision mới. Vì vậy, cần bảo đảm mỗi resource vẫn có owner, state, provider mapping, credential path và khả năng cleanup.

Khi triển khai **SPRING_CLOUD_SERVICE_BROKER**, hãy giữ các nguyên tắc:

- Phân biệt retire plan, service offering, backend provider và broker registration.
- Không giả định OSB API có endpoint handover broker portable.
- Inventory và đối chiếu broker state, platform records và provider resources.
- Freeze provision mới theo scope, nhưng duy trì lifecycle operations cần cho instance cũ.
- Drain/reconcile operation trước khi cutover.
- Chuyển state, binding, operation, idempotency mapping và provider resource identity.
- Dùng ownership epoch/fencing để ngăn dual writer.
- Giữ service/plan/instance/binding IDs khi semantics cho phép.
- Bàn giao credential qua secret manager và chỉ revoke sau khi consumer/provider được xác minh.
- Tách metadata migration khỏi data migration.
- Xác minh Cloud Foundry registration behavior và Kubernetes finalizer/CRD lifecycle theo phiên bản thực tế.
- Có rollback hoặc forward-recovery, runbook, audit và owner sign-off.
- Chỉ deregister, thu hồi credential và xóa state khi mọi dependency đã được giải quyết.

Một kế hoạch retirement có kiểm soát giúp broker cũ kết thúc an toàn trong khi dịch vụ của khách hàng tiếp tục hoạt động, quyền truy cập vẫn được quản lý và không để lại tài nguyên hoặc credential không có người chịu trách nhiệm.

