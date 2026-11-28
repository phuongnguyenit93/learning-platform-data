# Phương án chuyển đổi hệ thống OSB cũ mà vẫn giữ tài nguyên và thông tin kết nối

Trong module **SPRING_CLOUD_SERVICE_BROKER**, broker có thể được thay thế hoặc chuyển từ một nền tảng cũ sang một triển khai mới chạy trên Kubernetes. Lý do có thể là nâng cấp Spring Cloud Open Service Broker, thay đổi cơ sở dữ liệu quản lý, chuyển provider adapter, hợp nhất nhiều broker hoặc hiện đại hóa hạ tầng. Dù thay đổi phần mềm và nơi vận hành, các service instance đã được provision vẫn đang tồn tại ở provider và các ứng dụng vẫn cần kết nối bằng thông tin binding hiện tại.

Vì vậy, migration OSB cần bảo toàn cả **quyền sở hữu vòng đời** lẫn **đường kết nối dữ liệu**. Broker mới phải tiếp tục nhận diện đúng service instance và binding mà platform đã tạo; phải tìm được provider resource tương ứng; phải giữ hoặc chuyển giao credentials an toàn; và phải tránh việc một thao tác retry tạo thêm tài nguyên mới. Việc chỉ cài broker mới với cùng catalog không tự động chuyển trạng thái của platform hoặc nhận quyền quản lý tài nguyên cũ.

Nguyên tắc quan trọng là **adopt tài nguyên hiện hữu thay vì provision lại**. Broker mới tiếp nhận metadata và mapping của tài nguyên cũ, xác minh provider state, sau đó trở thành đầu mối duy nhất xử lý các thao tác vòng đời. Bài học này trình bày cách lập kế hoạch, kiểm kê, chuyển metadata và credentials, cutover sang Kubernetes, kiểm thử, rollback và đóng hệ thống cũ an toàn.

## 1. Xác định chính xác phạm vi migration

Trước khi di chuyển, cần xác định điều gì đang được thay đổi. Một hệ thống OSB có nhiều lớp độc lập:

| Thành phần | Ví dụ | Có cần chuyển? |
|---|---|---|
| Broker application | Spring Boot broker cũ | Thay bằng broker mới |
| OSB endpoint/registration | URL broker mà platform gọi | Có thể đổi endpoint hoặc giữ qua gateway |
| Catalog | Service ID, plan ID, schemas, capabilities | Phải giữ tương thích hoặc có kế hoạch chuyển đổi |
| Instance registry | Instance ID, service ID, plan ID, lifecycle state | Cần chuyển hoặc tái dựng có xác minh |
| Binding registry | Binding ID, consumer, principal và credential reference | Cần chuyển để quản lý đúng binding |
| Provider resources | Database, Redis, queue, bucket, cluster resource | Thường giữ nguyên, không tạo lại |
| Secrets | Username, password, certificates, tokens | Phải giữ hoặc rotate theo kế hoạch |
| Operations | Provision/update/deprovision đang chạy | Phải hoàn tất hoặc chuyển giao có kiểm soát |
| Quota/usage/billing | Reservation, usage, cost attribution | Cần giữ continuity và audit |
| Audit history | Actor, tenant, thao tác và thời gian | Chuyển hoặc lưu archive có thể tra cứu |

Không phải dữ liệu nào cũng cần nằm trong cùng database mới. Một số thành phần như provider resource có thể tiếp tục tồn tại tại cloud provider; secret có thể nằm trong vault; audit cũ có thể được archive. Nhưng broker mới phải có mapping và quyền truy cập tới các nguồn dữ liệu đó.

Cần phân biệt migration **control plane** với migration **data plane**. Control plane gồm broker API, catalog, registry, operation store và policy. Data plane gồm database, queue, bucket, endpoint và credential mà ứng dụng đang dùng. Thay control plane không nhất thiết phải di chuyển data plane.

## 2. Vì sao không được provision lại các instance cũ?

Mỗi service instance do platform tạo có một định danh ổn định trong phạm vi OSB platform. Broker lưu mapping từ instance ID sang provider resource ID. Nếu broker mới nhận một instance ID cũ như một request provision mới, nó có thể tạo thêm database hoặc queue thứ hai.

Những rủi ro khi provision lại:

- Dữ liệu ứng dụng đang dùng nằm trong resource cũ, còn broker mới tạo resource rỗng.
- Endpoint hoặc hostname mới khiến ứng dụng kết nối tới sai database.
- Credentials mới không khớp với credentials đang được workload sử dụng.
- Hóa đơn và quota bị tính trùng.
- Platform giữ một instance ID nhưng broker quản lý hai provider resources.
- Deprovision từ platform có thể xóa nhầm resource cũ hoặc resource mới.
- Binding cũ không còn được broker mới nhận diện, dẫn đến không thể unbind hoặc rotate an toàn.

Migration cần dùng quy trình **adoption/import** nội bộ: tìm resource đã tồn tại, xác minh owner, gắn nó với instance ID cũ và lưu mapping mới. Không gọi luồng create provider resource thông thường cho một instance đã có resource.

## 3. Bảo toàn các định danh OSB

Platform tiếp tục dùng các định danh đã được tạo trước migration. Broker mới cần giữ nguyên hoặc ánh xạ chính xác các định danh sau:

| Định danh | Vai trò | Yêu cầu migration |
|---|---|---|
| Service ID | Offering được chọn | Giữ ổn định hoặc có mapping tương thích |
| Plan ID | Cấp dịch vụ được chọn | Giữ semantics và khả năng hỗ trợ resource hiện hữu |
| Service instance ID | Định danh instance từ platform | Bảo toàn chính xác |
| Binding ID | Định danh binding từ platform | Bảo toàn chính xác |
| Operation ID/token | Định danh operation bất đồng bộ | Chuyển các operation còn hoạt động hoặc hoàn tất trước cutover |
| Tenant/platform context | Phạm vi sở hữu | Giữ mapping đã xác minh |
| Provider resource ID | Tài nguyên thực tại provider | Không đổi nếu resource được giữ nguyên |

Nếu platform gửi một instance ID cũ tới broker mới, broker phải tìm đúng instance record. Không tạo ID mới và không yêu cầu người dùng tạo lại service chỉ vì backend broker đã thay đổi.

Một khóa nội bộ nên bao gồm platform namespace nếu broker phục vụ nhiều foundation:

~~~text
platform_instance_id + service_instance_id
platform_instance_id + service_instance_id + binding_id
~~~

Cách này tránh collision khi nhiều platform có thể tạo cùng một chuỗi instance ID hoặc binding ID.

## 4. Lập inventory trước khi chuyển

Migration chỉ an toàn khi broker biết chính xác những gì đang tồn tại. Inventory nên được tạo từ registry cũ, platform inventory và provider inventory rồi đối chiếu.

Một bản ghi instance cần tối thiểu:

| Trường | Mục đích |
|---|---|
| platform_instance_id | Platform/foundation sở hữu instance |
| instance_id | ID OSB từ platform |
| tenant_id | Tenant đã xác minh |
| service_id, plan_id | Offering và plan |
| provider_type | Loại provider |
| provider_account/project | Phạm vi tài khoản provider |
| provider_resource_id | ID resource thực tế |
| external_resource_key | Tên/label dùng tra cứu |
| endpoint_reference | Tham chiếu endpoint hoặc DNS |
| lifecycle_state | Trạng thái đã xác minh |
| created_at, updated_at | Mốc vòng đời |
| last_operation_id | Operation gần nhất nếu có |

Binding inventory cần thêm binding ID, consumer identity, provider principal ID, permission profile, credential reference, trạng thái revoke và thời điểm tạo. Không xuất password hoặc private key dạng rõ vào file inventory.

### 4.1. Đối chiếu ba nguồn

Nên so sánh:

1. **Broker registry cũ:** broker nghĩ instance/binding nào tồn tại.
2. **Platform inventory:** platform nghĩ service instance/binding nào đã được tạo.
3. **Provider inventory:** hạ tầng thực tế đang có resource nào.

Ví dụ:

| Nguồn | Instance | Provider resource |
|---|---|---|
| Broker cũ | instance-7f3a | pg-orders-991 |
| Platform | instance-7f3a | Không lưu provider ID |
| Provider | pg-orders-991 | Database orders |

Ba nguồn cần được nối bằng mapping đáng tin cậy. Nếu provider có resource không xuất hiện trong broker registry, cần xác minh ownership trước khi import. Không tự nhận mọi resource có tên gần giống instance ID.

### 4.2. Phân loại trước khi migrate

Chia inventory thành các nhóm:

- ACTIVE và mapping đầy đủ.
- ACTIVE nhưng thiếu provider resource ID.
- PROVISIONING/UPDATING/DEPROVISIONING.
- FAILED nhưng provider resource vẫn tồn tại.
- DEPROVISIONED hoặc tombstone.
- Binding ACTIVE có credentials truy xuất được.
- Binding ACTIVE nhưng provider không thể đọc lại secret.
- Resource orphan hoặc ownership chưa rõ.

Nhóm có operation đang chạy hoặc ownership không rõ cần được giải quyết riêng. Không nên cutover một instance đang ở trạng thái không xác định.

## 5. Chọn chiến lược cutover

Có ba chiến lược phổ biến. Lựa chọn phụ thuộc quy mô, khả năng đồng bộ dữ liệu và mức downtime chấp nhận được.

| Chiến lược | Cách làm | Ưu điểm | Rủi ro/chi phí |
|---|---|---|---|
| Big-bang | Dừng mutation, chuyển toàn bộ registry, đổi endpoint một lần | Quy trình đơn giản, tránh hai broker cùng ghi | Cần cửa sổ bảo trì, phạm vi lỗi lớn |
| Phased migration | Chuyển theo tenant, platform hoặc nhóm service | Blast radius nhỏ, có thể canary | Cần routing và ownership theo nhóm |
| Proxy cutover | Giữ URL cũ, gateway định tuyến request sang broker mới | Platform ít phải đổi registration | Gateway trở thành thành phần quan trọng, cần giữ semantics và authentication |

Không có chiến lược nào tự động bảo đảm zero downtime. Nếu cần tiếp tục nhận request trong lúc migration, phải thiết kế cách giữ một writer duy nhất, đồng bộ mutation và chuyển giao operation đang chạy.

### 5.1. Chọn theo khả năng kiểm soát

- Với vài instance và có thể có cửa sổ bảo trì, big-bang thường dễ kiểm soát.
- Với nhiều tenant hoặc nhiều foundation, phased migration giúp kiểm chứng từng nhóm.
- Nếu platform khó thay broker URL, proxy cutover có thể giữ endpoint ổn định trong khi backend đổi.
- Nếu database registry cũ và mới không thể đồng bộ nhất quán, hãy ưu tiên freeze mutation thay vì dual-write tùy tiện.

## 6. Quy tắc single-writer trong thời gian chuyển đổi

Hai broker cùng có quyền xử lý provision, update, bind, unbind và deprovision trên cùng một instance có thể tạo race condition. Ví dụ broker cũ nhận DELETE trong khi broker mới nhận PATCH. Cả hai có thể gọi provider trên cùng resource.

Cần có một thời điểm chuyển quyền sở hữu rõ ràng:

1. Đặt broker cũ vào maintenance/read-only hoặc chặn mutation theo nhóm đang migrate.
2. Chờ request đang xử lý kết thúc hoặc ghi lại trạng thái operation có thể chuyển giao.
3. Đồng bộ snapshot cuối cùng và các thay đổi phát sinh trước freeze.
4. Chuyển registry và secret references.
5. Xác minh broker mới đọc được toàn bộ mapping.
6. Cấp quyền mutation cho broker mới.
7. Chuyển platform traffic sang broker mới.
8. Theo dõi và chỉ cho phép một writer sở hữu từng resource namespace.

Nếu dùng gateway, routing rule phải bảo đảm một instance chỉ được xử lý bởi một backend tại một thời điểm. Không dựa vào load balancing round-robin giữa broker cũ và mới.

## 7. Di chuyển metadata và chuẩn hóa schema

Broker mới có thể dùng schema database khác với broker cũ. Cần có migration mapping từ schema cũ sang canonical model mới.

Một canonical instance record có thể gồm:

~~~json
{
  "platform_instance_id": "cf-prod",
  "instance_id": "instance-7f3a",
  "tenant_id": "tenant-payments",
  "service_id": "service-postgresql",
  "plan_id": "plan-standard",
  "provider": {
    "type": "postgresql",
    "account_id": "cloud-account-01",
    "resource_id": "pg-orders-991",
    "external_key": "broker-pg-orders-991"
  },
  "lifecycle_state": "ACTIVE",
  "migration_state": "ADOPTED"
}
~~~

Đây là record nội bộ minh họa, không phải OSB response. Schema mới cần giữ các field phục vụ lifecycle, ownership, provider mapping và audit. Nếu field cũ không còn được sử dụng, không xóa ngay trước khi xác minh không còn workflow nào cần nó.

### 7.1. Giữ raw value hay chỉ lưu normalized value?

Với context, parameters hoặc metadata cũ, có thể cần giữ cả:

- Giá trị normalized mà broker mới dùng cho policy.
- Bản snapshot tương thích để audit hoặc khôi phục.
- Phiên bản schema nguồn và thời điểm chuyển đổi.

Không nên giữ raw payload vô thời hạn nếu nó chứa PII hoặc secret. Chỉ giữ phần cần thiết, mã hóa và áp dụng retention.

### 7.2. Migration script phải có thể chạy lại

Mỗi record migration nên có source key, target key, migration batch ID và trạng thái. Nếu job chạy lại, nó phải nhận diện record đã được chuyển và không tạo duplicate.

Ví dụ trạng thái:

~~~text
PENDING -> VALIDATED -> IMPORTED -> ADOPTED
                    \-> NEEDS_REVIEW
                    \-> FAILED
~~~

Chỉ đánh dấu ADOPTED khi provider resource đã được xác minh và broker mới có thể quản lý đúng instance.

## 8. Giữ nguyên provider resource và endpoint kết nối

Mục tiêu là giữ resource data plane hiện hữu. Với database, Redis hoặc message broker, broker mới cần tiếp tục tham chiếu đúng resource ID và endpoint mà ứng dụng đang sử dụng.

Có thể bảo toàn kết nối theo một trong các cách:

- Giữ nguyên hostname và port của provider resource.
- Giữ DNS alias hoặc stable endpoint trỏ tới resource cũ.
- Giữ proxy/gateway endpoint và chỉ đổi backend sau khi xác minh.
- Giữ certificate chain và trust roots mà workload đang sử dụng.
- Giữ firewall rules, private network routes và allowlists.
- Giữ database name, virtual host, bucket hoặc namespace.

Không đổi hostname hoặc rotate certificate trong cùng một bước cutover nếu không cần thiết. Nếu bắt buộc thay endpoint, cần có giai đoạn tương thích để workload cập nhật cấu hình và xác nhận kết nối trước khi ngừng endpoint cũ.

Ví dụ một binding đang trả:

~~~json
{
  "hostname": "orders-db.internal.example",
  "port": 5432,
  "database": "orders",
  "sslmode": "verify-full"
}
~~~

Broker mới nên giữ nguyên giá trị kết nối nếu provider resource không đổi. Nếu hostname là DNS alias do broker quản lý, cần chuyển quyền quản lý DNS mà không làm mất record hoặc thay đổi TLS identity bất ngờ.

## 9. Bảo toàn credentials và binding information

Binding là nơi rủi ro migration thường cao nhất vì credentials đã được phân phối cho ứng dụng và có thể đang được sử dụng liên tục.

Cần kiểm kê:

- Binding ID và instance ID.
- Consumer/app/workload reference.
- Provider principal hoặc key ID.
- Username, password, token hoặc certificate reference.
- Permission profile và ACL.
- Endpoint, database, virtual host hoặc schema.
- Credential rotation status và thời hạn.
- Nơi secret đang được lưu: vault, encrypted database, platform secret hoặc external secret store.

### 9.1. Ưu tiên chuyển secret reference

Nếu broker cũ và mới cùng dùng một secret manager, có thể chuyển quyền truy cập tới cùng secret path/reference. Khi đó không cần xuất secret value khỏi vault. Cần cập nhật policy để broker mới đọc được đúng secret, đồng thời thu hồi quyền của broker cũ sau cutover.

Nếu dùng hai vault khác nhau, có thể replicate secret bằng kênh mã hóa và identity được cấp quyền tối thiểu. Mỗi secret cần checksum/version metadata hoặc xác minh bằng một phép thử kết nối không ghi log secret.

### 9.2. Khi buộc phải chuyển secret value

Nếu provider không cho đọc lại password và secret chỉ tồn tại trong store cũ, phải chuyển giá trị bằng quy trình secret migration được kiểm soát:

1. Dùng service identity chuyên dụng có quyền đọc đúng tập secret.
2. Truyền qua kênh mã hóa và không ghi ra log hoặc file tạm không bảo vệ.
3. Mã hóa bằng key của secret store đích.
4. Xác minh broker mới có thể truy xuất và giải mã.
5. Kiểm tra metadata/version và liên kết đúng binding.
6. Thu hồi bản sao hoặc quyền truy cập không còn cần thiết theo chính sách.
7. Audit việc chuyển giao mà không ghi secret value.

Không đưa password vào migration report, shell history, console output hoặc CSV thông thường.

### 9.3. Không rotate đồng loạt nếu không cần

Nếu chỉ thay broker control plane, giữ nguyên credentials thường giảm rủi ro downtime. Rotation có thể là một dự án riêng sau khi cutover ổn định.

Nếu có lý do bảo mật buộc phải rotate, nên thực hiện theo từng binding hoặc từng nhóm consumer, có overlap nếu provider hỗ trợ, kiểm tra kết nối mới rồi mới revoke credential cũ. Không rotate toàn bộ shared credential khi chưa có inventory mọi consumer đang sử dụng.

## 10. Giữ catalog và semantics OSB tương thích

Platform đã lưu service ID và plan ID từ catalog cũ. Broker mới cần công bố catalog tương thích với các instance hiện hữu.

Các điểm cần kiểm tra:

- Service ID và plan ID vẫn được nhận diện.
- Description, schemas và parameters không thay đổi semantics ngoài kế hoạch.
- Bindable, plan_updateable và các capability retrieval phản ánh đúng implementation.
- Plan cũ vẫn được hỗ trợ cho các instance đang tồn tại, kể cả khi plan đó không còn cho phép provision mới.
- Broker mới hiểu context và parameters cũ đã được lưu.
- Update và deprovision của instance cũ vẫn được xử lý theo contract.
- Binding cũ vẫn có thể unbind hoặc retrieve theo capability được công bố.

Không xóa một plan khỏi catalog chỉ vì không muốn nhận provision mới nếu platform hoặc broker cần plan ID đó để update/deprovision instance cũ. Có thể cần policy ngừng provision mới nhưng vẫn hỗ trợ lifecycle cho resource hiện hữu.

Catalog metadata không chứa instance state hoặc secret. Việc chuyển catalog không thay thế việc chuyển instance/binding registry.

## 11. Xử lý các operation đang chạy

Trước cutover, cần liệt kê các operation PROVISIONING, UPDATING, DEPROVISIONING, BINDING hoặc UNBINDING đang hoạt động.

Có hai lựa chọn:

- **Drain trước cutover:** chờ operation hoàn tất hoặc chuyển về trạng thái terminal, sau đó migration snapshot.
- **Chuyển giao operation:** chỉ thực hiện nếu broker mới hiểu được state machine, operation token, request payload, provider request ID, retry count và outbox/queue semantics.

Drain thường ít rủi ro hơn. Nếu cần chuyển giao, operation record phải giữ nguyên định danh mà platform sẽ dùng để poll, hoặc có mapping tương thích. Không tạo operation mới làm platform mất token cũ nếu token đó còn được tham chiếu.

Một operation record cần mang theo:

| Field | Mục đích |
|---|---|
| operation_id/token | Giữ liên kết với last_operation request |
| instance_id và platform scope | Resource sở hữu |
| operation_type | Provision, update, deprovision hoặc binding action |
| request fingerprint | Nhận diện retry |
| state | Trạng thái đã xác nhận |
| provider_request_id | Tra cứu tiến trình phía provider |
| next_retry_at, attempt_count | Tiếp tục retry đúng lịch |
| outbox/event state | Tránh mất hoặc phát trùng job |
| created_at, updated_at | Giữ timeline và timeout policy |

Worker mới phải kiểm tra provider state trước khi tiếp tục side effect. Không chạy lại toàn bộ job chỉ vì queue được tạo lại trong hệ thống mới.

## 12. Cutover sang Kubernetes

Khi broker mới chạy trên Kubernetes, cần chuyển cả application và các dependency control plane:

- Deployment/StatefulSet hoặc workload phù hợp.
- Service và Ingress/Gateway.
- TLS certificate và trust configuration.
- Database registry và migration schema.
- Secret manager integration.
- Queue/event broker nếu dùng async operations.
- Provider credentials và Kubernetes/cloud RBAC.
- NetworkPolicy, egress rules và DNS.
- Monitoring, logging, tracing và alerting.

Không nên nhúng provider credentials vào image hoặc manifest plaintext. Dùng Kubernetes Secret được bảo vệ hoặc external secret manager, RBAC giới hạn namespace và workload identity khi provider hỗ trợ.

### 12.1. Tổ chức namespace và service account

Broker mới nên có service account riêng với quyền tối thiểu. Nếu broker quản lý resource trong nhiều namespace, cân nhắc quyền theo namespace hoặc một controller có phạm vi được giới hạn rõ ràng.

Ví dụ RBAC minh họa cho một namespace được quản lý:

~~~yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: service-broker
  namespace: broker-system
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: broker-resource-manager
  namespace: tenant-payments
rules:
  - apiGroups: [""]
    resources: ["services", "persistentvolumeclaims", "secrets"]
    verbs: ["get", "list", "watch", "create", "update", "patch", "delete"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: broker-resource-manager
  namespace: tenant-payments
subjects:
  - kind: ServiceAccount
    name: service-broker
    namespace: broker-system
roleRef:
  kind: Role
  name: broker-resource-manager
  apiGroup: rbac.authorization.k8s.io
~~~

Đây chỉ là ví dụ để minh họa RBAC. Không áp dụng nguyên trạng cho mọi broker. Cần giới hạn resource types, verbs, namespaces và secret access đúng nhu cầu thực tế. Nếu broker không cần đọc Secret trực tiếp, không cấp quyền đó.

### 12.2. Kiểm tra readiness trước khi chuyển traffic

Broker mới chỉ nên nhận mutation khi:

- Database schema đã migrate và repository đọc được.
- Secret references đã resolve.
- Provider adapters kết nối được.
- Catalog và API version policy đã được kiểm tra.
- Worker/queue có thể tiếp tục operation hoặc đang ở chế độ drain.
- Authentication và authorization được cấu hình.
- Readiness probe phản ánh khả năng phục vụ thực tế, không chỉ process đang sống.

Liveness probe không nên gọi provider hoặc thực hiện side effect. Readiness có thể kiểm tra dependency tối thiểu và trạng thái migration của broker.

## 13. Quy trình migration theo từng giai đoạn

Một quy trình có thể triển khai:

### Giai đoạn A — Discovery và freeze plan

1. Kiểm kê broker, platform registrations, tenants, instances, bindings và operations.
2. Đối chiếu broker registry với platform và provider inventory.
3. Xác định catalog compatibility.
4. Xác định nguồn secrets và khả năng truy xuất.
5. Chọn big-bang, phased hoặc proxy cutover.
6. Đặt tiêu chí go/no-go, thời gian freeze và owner cho từng bước.

### Giai đoạn B — Chuẩn bị broker mới

1. Triển khai broker mới trên Kubernetes ở chế độ chưa nhận mutation.
2. Cấu hình database, vault, queue và provider adapters.
3. Migrate schema và catalog model.
4. Chạy import thử trên snapshot.
5. Kiểm tra mapping instance/binding/provider.
6. Kiểm tra credentials bằng test connection có kiểm soát.
7. Chạy contract tests và security tests.

### Giai đoạn C — Final sync và ownership transfer

1. Bật maintenance/read-only trên broker cũ theo phạm vi.
2. Drain hoặc ghi lại operations đang chạy.
3. Đồng bộ thay đổi cuối cùng.
4. Xác minh không còn writer hoặc worker cũ tác động resource.
5. Đánh dấu batch/record được adopt.
6. Cấp quyền truy cập vault và provider cho broker mới.
7. Chuyển routing hoặc broker registration.

### Giai đoạn D — Canary và mở rộng

1. Chọn một tenant hoặc nhóm instance ít rủi ro.
2. Kiểm tra catalog, retrieve, bind, unbind và lifecycle trên broker mới.
3. Theo dõi error rate, provider calls, latency và connection success.
4. Mở rộng từng batch.
5. Giữ broker cũ ở trạng thái không nhận mutation nhưng còn khả năng tra cứu audit trong thời gian rollback.

### Giai đoạn E — Hoàn tất và đóng hệ thống cũ

1. Xác minh toàn bộ inventory đã adopt.
2. Đối soát quota, billing và provider resource mapping.
3. Kiểm tra không còn request hoặc worker tới broker cũ.
4. Thu hồi provider credentials của broker cũ.
5. Archive audit và migration manifest.
6. Gỡ registration/deployment cũ theo quy trình đã xác nhận.
7. Chỉ xóa dữ liệu cũ sau retention và sign-off vận hành.

## 14. Rollback mà không mất quyền quản lý tài nguyên

Rollback cần được thiết kế trước khi cutover. Việc chỉ đổi traffic về broker cũ có thể không an toàn nếu broker mới đã tạo binding, update plan hoặc thay đổi provider resource.

Một số nguyên tắc:

- Trước khi broker mới nhận mutation, rollback thường đơn giản: quay lại broker cũ vì state chưa phân kỳ.
- Sau khi broker mới nhận mutation, phải đồng bộ ngược các thay đổi hoặc có một registry chung làm nguồn chuẩn.
- Không cho broker cũ hoạt động lại với snapshot stale rồi thực hiện DELETE/UPDATE trên resource đã thay đổi.
- Giữ operation history và provider request IDs để điều tra.
- Nếu secret đã rotate, broker cũ không được tiếp tục trả secret cũ.
- Nếu DNS hoặc certificate đã thay đổi, rollback phải giữ endpoint tương thích hoặc có quy trình chuyển ngược.
- Nếu không thể đồng bộ ngược an toàn, tiếp tục phục vụ bằng broker mới và sửa lỗi forward là lựa chọn ít rủi ro hơn.

Một state marker có thể phân biệt ownership:

~~~text
OLD_BROKER_ACTIVE
MIGRATION_FROZEN
NEW_BROKER_ADOPTED
NEW_BROKER_ACTIVE
ROLLBACK_PENDING
ROLLBACK_COMPLETED
~~~

Mỗi instance nên có owner epoch hoặc version để broker cũ không thể ghi sau khi quyền sở hữu đã chuyển. Một fencing token tăng đơn điệu giúp database/provider coordinator từ chối mutation từ broker có epoch cũ.

## 15. Idempotency và adoption an toàn

Migration script có thể chạy lại sau lỗi. Broker mới cũng có thể nhận lại cùng request từ platform sau khi cutover. Vì vậy adoption phải idempotent.

Khóa adoption có thể gồm:

~~~text
platform_instance_id + instance_id + provider_resource_id
~~~

Quy trình:

1. Tìm instance theo composite platform/resource key.
2. Nếu đã ADOPTED và mapping giống nhau, trả kết quả hiện có.
3. Nếu instance chưa tồn tại, tạo import reservation.
4. Xác minh provider resource ID, tenant owner và external key.
5. Lưu mapping trong transaction.
6. Đánh dấu ADOPTED sau khi kiểm tra provider state.
7. Nếu mapping đã tồn tại nhưng provider resource khác, chuyển NEEDS_REVIEW thay vì ghi đè.

Không dùng tên gần giống làm bằng chứng đủ để adopt. Cần nhiều thuộc tính đối chiếu: account/project, resource ID, tags, region, service type, tenant mapping và metadata đã lưu.

## 16. Kiểm thử trước và sau cutover

Kiểm thử phải chứng minh ứng dụng vẫn kết nối được và broker mới quản lý đúng resource cũ.

| Nhóm | Test | Kết quả mong đợi |
|---|---|---|
| Catalog | GET catalog từ broker mới | Service/plan IDs và capability tương thích |
| Instance adoption | Lookup instance ID cũ | Tìm đúng provider resource cũ |
| Binding adoption | Lookup binding ID cũ | Tìm đúng principal và secret reference |
| Connection | Ứng dụng dùng credentials hiện tại | Kết nối thành công tới cùng endpoint |
| Provision retry | Retry instance đã adopt | Không tạo provider resource thứ hai |
| Bind retry | Retry binding cũ | Không tạo principal/credential trùng |
| Unbind | Xóa binding cũ | Revoke đúng principal theo policy |
| Deprovision | Xóa instance cũ | Chỉ xóa đúng provider resource |
| Async operation | Poll token đang hoạt động | Trả state đúng hoặc operation đã được drain |
| Tenant isolation | Tenant khác truy cập ID cũ | Bị từ chối |
| Secret security | Log/trace trong migration | Không chứa secret plaintext |
| Provider inventory | So sánh trước/sau | Resource count và IDs không bị nhân đôi |
| Rollback | Chuyển quyền trước khi mutation | Broker cũ có thể phục vụ theo snapshot nhất quán |
| Reconciliation | Đối chiếu broker/platform/provider | Không có mismatch chưa phân loại |

Một bài kiểm thử quan trọng là lấy một workload đang chạy, không thay đổi cấu hình kết nối, thực hiện cutover broker control plane rồi xác nhận workload vẫn đọc/ghi được dữ liệu. Việc này chứng minh data plane và credentials được giữ nguyên, không chỉ chứng minh API broker trả HTTP 200.

## 17. Quan sát sau migration

Sau cutover, theo dõi các chỉ số:

- Tỷ lệ request OSB thành công theo endpoint.
- Provision/update/deprovision errors.
- Số instance và binding đã adopt.
- Số resource orphan hoặc mapping mismatch.
- Connection success rate của ứng dụng.
- Số lần provider adapter tạo resource mới.
- Số request bị xử lý bởi broker cũ.
- Operation bị kẹt hoặc retry bất thường.
- Secret retrieval failures.
- Quota, usage và billing reconciliation differences.

Đặc biệt, số lượng provider resource mới trong thời gian migration phải được giải thích. Nếu chỉ đang adopt resource cũ mà số database hoặc principal tăng đột biến, cần dừng rollout để điều tra duplicate provisioning.

Giữ correlation ID từ platform request qua broker application, worker, provider adapter và audit event. Không đưa secret hoặc raw credentials vào trace attribute.

## 18. Các lỗi migration thường gặp

| Lỗi | Hậu quả | Cách phòng tránh |
|---|---|---|
| Cài broker mới rồi để platform provision lại | Tạo resource trùng và mất liên kết dữ liệu cũ | Import/adopt resource hiện hữu |
| Đổi instance ID hoặc binding ID | Platform không tìm được resource đã tạo | Bảo toàn định danh OSB |
| Chỉ chuyển instance table, bỏ binding/secret mapping | Ứng dụng mất kết nối hoặc không unbind được | Migrate binding và credentials cùng registry |
| Chuyển secret qua file plaintext | Lộ credential | Vault-to-vault transfer và encryption |
| Hai broker cùng nhận mutation | Race condition, xóa/update nhầm | Single-writer và fencing |
| Bỏ qua operation đang chạy | Mất polling state hoặc lặp provider side effect | Drain hoặc chuyển giao operation |
| Thay hostname/certificate cùng lúc | Workload mất kết nối | Giữ endpoint hoặc migration riêng có overlap |
| Xóa plan cũ khỏi catalog | Không update/deprovision được instance hiện hữu | Giữ lifecycle compatibility |
| Rollback về registry stale | Broker cũ tác động sai resource | Reverse sync hoặc giữ broker mới làm owner |
| Xóa broker cũ quá sớm | Mất audit và đường phục hồi | Retention, archive và sign-off |
| Adopt theo tên resource gần giống | Nhận nhầm resource của tenant khác | Verify provider ID, account, tags và ownership |

## 19. Checklist chuyển đổi OSB cũ sang Kubernetes

Trước khi cutover, hãy xác nhận:

- [ ] Có inventory đầy đủ instance, binding, operation và provider resource.
- [ ] Mỗi instance có platform scope, tenant owner và provider mapping đã xác minh.
- [ ] Service ID và plan ID vẫn tương thích với platform.
- [ ] Broker mới hiểu schema metadata và parameters cũ.
- [ ] Instance ID và binding ID được bảo toàn.
- [ ] Credentials được chuyển qua secret manager an toàn hoặc có rotation plan.
- [ ] Endpoint, DNS, port, TLS và firewall rules vẫn hoạt động.
- [ ] Các operation đang chạy đã drain hoặc có kế hoạch handoff.
- [ ] Chỉ có một broker được phép mutate mỗi resource namespace.
- [ ] Migration script có thể chạy lại và có manifest trạng thái.
- [ ] Provider resources được adopt, không provision lại.
- [ ] Kubernetes service account và RBAC tuân theo least privilege.
- [ ] Broker mới có readiness checks và dependency configuration.
- [ ] Có canary, go/no-go criteria và rollback plan.
- [ ] Có test connection từ workload hiện tại sau cutover.
- [ ] Có reconciliation cho broker registry, platform inventory và provider inventory.
- [ ] Broker cũ chỉ bị gỡ sau khi xác nhận không còn request/worker và dữ liệu đã archive.

Chuyển đổi OSB cũ sang một broker mới trên Kubernetes là quá trình chuyển giao quyền quản lý control plane trong khi bảo toàn data plane. Việc giữ nguyên instance ID, binding ID, provider resource, endpoint và credentials giúp ứng dụng tiếp tục hoạt động; inventory, adoption, single-writer, idempotency và reconciliation giúp broker mới tiếp nhận tài nguyên một cách có kiểm soát. Khi cutover và rollback được thiết kế theo từng giai đoạn, Spring Cloud Service Broker có thể thay đổi hạ tầng vận hành mà không buộc khách hàng tạo lại dịch vụ hoặc thay đổi kết nối đang chạy.
