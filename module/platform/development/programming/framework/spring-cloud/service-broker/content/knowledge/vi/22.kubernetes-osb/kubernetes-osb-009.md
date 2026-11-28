# Đối chiếu OSB với Operator và cơ chế Service Binding của hệ sinh thái Kubernetes

## Bối cảnh

Open Service Broker API (OSB API), Kubernetes Operator và Service Binding đều có thể xuất hiện trong một nền tảng cung cấp dịch vụ cho ứng dụng, nhưng chúng giải quyết các bài toán khác nhau.

- OSB API định nghĩa hợp đồng HTTP để một platform khám phá catalog, provision service instance, update, deprovision và tạo hoặc xóa binding.
- Kubernetes Operator là một controller mở rộng Kubernetes API. Operator thường khai báo CustomResourceDefinition (CRD), theo dõi custom resource và liên tục reconcile trạng thái thực tế về trạng thái mong muốn.
- Service Binding trong hệ sinh thái Kubernetes chuẩn hóa cách mô tả mối liên kết giữa một workload và một backing service, sau đó đưa dữ liệu kết nối vào workload theo quy ước mà ứng dụng có thể đọc.

Một Service Broker theo Spring Cloud có thể triển khai OSB API cho Cloud Foundry hoặc platform khác, đồng thời dùng Kubernetes Operator để thực thi tài nguyên phía sau. Nếu workload chạy trên Kubernetes, broker còn có thể phối hợp với cơ chế Service Binding để đưa credentials vào Pod. Ba thành phần bổ sung cho nhau khi được đặt đúng ranh giới.

Điều quan trọng là không đồng nhất chúng. OSB service instance không phải Kubernetes Service object; OSB service binding không phải ServiceBinding custom resource; Operator không tự động cung cấp marketplace; Service Binding controller không tự provision database chỉ vì có một workload cần kết nối.

## 1. Ba mô hình và trách nhiệm

| Tiêu chí | OSB API / Service Broker | Kubernetes Operator | Service Binding |
|---|---|---|---|
| Mục tiêu | Cung cấp dịch vụ qua một contract thống nhất cho platform | Quản lý vòng đời tài nguyên bằng reconciliation | Kết nối workload với backing service |
| Giao diện | HTTP API và catalog | CRD, Kubernetes API, controller | ServiceBinding API/CRD và binding data |
| Đối tượng chính | Service offering, plan, instance, binding, operation | Custom resource và trạng thái tài nguyên | Workload, service reference và credentials |
| Cách điều khiển | Platform gửi request provision/update/delete | Người dùng hoặc automation khai báo desired state; controller reconcile | Người dùng khai báo workload cần service; controller chuẩn bị binding projection |
| Trạng thái | OSB response và last_operation | spec/status, conditions, observedGeneration | ServiceBinding condition và trạng thái workload projection tùy triển khai |
| Nơi chạy | Broker có thể ở ngoài hoặc trong Kubernetes | Thường chạy trong cluster cần quản lý tài nguyên | Controller chạy trong cluster |
| Phạm vi | Có thể quản lý nhiều platform/provider | Thường tập trung vào một API/domain tài nguyên | Tập trung vào phân phối thông tin binding cho workload |

### OSB API: contract giữa platform và broker

OSB API chuẩn hóa cách platform yêu cầu một dịch vụ. Platform không cần biết database được tạo bằng cloud API, Helm chart, Kubernetes CRD hay một hệ thống bên ngoài. Platform chỉ cần biết service ID, plan ID, instance ID và các endpoint OSB.

Ví dụ các endpoint:

~~~text
GET    /v2/catalog
PUT    /v2/service_instances/{instance_id}
PATCH  /v2/service_instances/{instance_id}
DELETE /v2/service_instances/{instance_id}
PUT    /v2/service_instances/{instance_id}/service_bindings/{binding_id}
DELETE /v2/service_instances/{instance_id}/service_bindings/{binding_id}
GET    /v2/service_instances/{instance_id}/last_operation
~~~

Broker chịu trách nhiệm kiểm tra request, áp dụng idempotency, lưu trạng thái và ánh xạ kết quả provider về contract OSB. Catalog và plan là khái niệm của broker/platform; Kubernetes không tự tạo marketplace OSB chỉ vì cluster có CRD.

### Operator: controller của một API miền

Operator đóng gói kiến thức vận hành một hệ thống cụ thể thành controller. Ví dụ Database Operator có thể cung cấp CRD Database với spec mô tả version, storage, backup và replication. Controller theo dõi Database resource, tạo StatefulSet hoặc gọi cloud database API, sau đó cập nhật status.

Operator không nhất thiết có catalog, plan, binding endpoint hoặc authentication contract theo OSB API. Một operator có thể chỉ quản lý PostgreSQL; broker có thể công bố nhiều offering và plan rồi chuyển từng yêu cầu sang một hoặc nhiều operator.

### Service Binding: hợp đồng đưa dữ liệu kết nối tới workload

Service Binding tập trung vào câu hỏi: workload nào cần kết nối tới service nào, và dữ liệu kết nối nên được đưa vào workload ra sao? Cơ chế này có thể đọc binding data từ Secret hoặc nguồn mà implementation hỗ trợ, sau đó chiếu dữ liệu thành file hoặc environment theo convention của Service Binding Specification.

Service Binding không thay thế quá trình provision. Một Database resource phải tồn tại và có thông tin binding trước khi workload nhận được hostname, port, username hoặc password.

## 2. Kubernetes primitives liên quan

Để hiểu Operator và Service Binding, cần phân biệt một số tài nguyên Kubernetes:

| Kubernetes resource | Vai trò |
|---|---|
| CRD | Đăng ký một loại API mới cho cluster |
| Custom Resource (CR) | Một object cụ thể thuộc loại API do CRD định nghĩa |
| Controller | Theo dõi object và reconcile trạng thái |
| Deployment/StatefulSet | Quản lý Pod cho workload hoặc thành phần dịch vụ |
| Service | Cung cấp endpoint mạng ổn định cho một nhóm Pod |
| Secret | Lưu dữ liệu nhạy cảm như credential và token |
| ConfigMap | Lưu cấu hình không nhạy cảm |
| ServiceAccount/Role/RoleBinding | Xác định danh tính và quyền của workload/controller |

Kubernetes Service là tài nguyên mạng trong cluster, ví dụ DNS name trỏ tới Pod. OSB service là offering do broker công bố, có thể đại diện cho database managed bên ngoài cluster. OSB service binding là quan hệ cấp credential cho consumer. Không có quan hệ một-một bắt buộc giữa các khái niệm này.

Ví dụ, broker provision một database managed bên ngoài Kubernetes. Database không có Pod trong cluster, nhưng broker vẫn có thể tạo Kubernetes Secret chứa endpoint và credentials để workload sử dụng. Trường hợp khác, Operator tạo PostgreSQL StatefulSet và Kubernetes Service để cung cấp DNS nội bộ; broker vẫn quản lý nó như một OSB service instance.

## 3. Operator hoạt động theo reconciliation

Operator thường hoạt động theo vòng lặp:

1. Watch custom resource hoặc nhận event cần xử lý.
2. Đọc spec, status và các dependency liên quan.
3. Quan sát trạng thái thực tế của tài nguyên.
4. Tính toán thay đổi cần thực hiện.
5. Tạo, cập nhật hoặc xóa resource phụ thuộc.
6. Cập nhật status và conditions.
7. Requeue khi cần tiếp tục hoặc khi có thay đổi mới.

~~~mermaid
flowchart TD
    A[Watch custom resource] --> B[Read spec and current state]
    B --> C[Compare desired and observed state]
    C --> D{Converged?}
    D -->|Yes| E[Set Ready condition]
    D -->|No| F[Apply safe changes]
    F --> G[Update status and checkpoint]
    G --> H[Requeue or wait for event]
    H --> B
~~~

Điểm khác biệt quan trọng là request OSB có thể kết thúc ngay khi broker nhận yêu cầu và trả 202, trong khi Operator tiếp tục reconcile cho đến khi desired state đạt được hoặc phát hiện lỗi terminal. Broker có thể coi trạng thái của CR và các resource phụ thuộc là nguồn quan sát để cập nhật OSB operation.

### Desired state và observed state

Ví dụ custom resource Database:

~~~yaml
apiVersion: database.example.io/v1alpha1
kind: Database
metadata:
  name: orders-db
  namespace: retail
spec:
  engine: postgresql
  version: "16"
  storage:
    size: 50Gi
  backup:
    schedule: "0 2 * * *"
status:
  phase: Ready
  observedGeneration: 3
  conditions:
    - type: Ready
      status: "True"
      reason: DatabaseAvailable
      message: Database is accepting connections
~~~

Đây là CRD minh họa, không phải API có sẵn của Kubernetes. CRD thực tế do Operator cài đặt sẽ định nghĩa schema, validation, defaulting và status subresource.

Trường spec biểu diễn trạng thái mong muốn; status phản ánh trạng thái controller đã quan sát. Broker không nên chỉ kiểm tra object đã được tạo thành công rồi kết luận provision hoàn tất. Cần đợi condition phù hợp, kiểm tra observedGeneration tương ứng và xác minh các thông tin kết nối đã sẵn sàng.

### Conditions và observedGeneration

Controller có thể cập nhật các condition như Ready, Progressing, Degraded hoặc Failed tùy convention của API. Broker cần biết contract cụ thể của Operator để ánh xạ condition thành OSB operation state.

Nếu spec vừa thay đổi generation từ 3 lên 4 nhưng status vẫn ghi observedGeneration=3, trạng thái Ready cũ có thể chưa phản ánh cấu hình mới. Broker nên chờ controller quan sát generation mới trước khi báo update succeeded.

## 4. Đối chiếu OSB service instance với custom resource

Một cách tích hợp phổ biến là ánh xạ một OSB service instance sang một custom resource do Operator quản lý:

| OSB | Kubernetes |
|---|---|
| service_id | Loại offering mà broker chọn controller/API tương ứng |
| plan_id | Cấu hình desired state được chuyển thành spec |
| instance_id | Khóa mapping nghiệp vụ và có thể dùng trong label/annotation |
| parameters | Giá trị spec sau validation và normalization |
| operation ID | Bản ghi operation trong broker; không nhất thiết là Kubernetes resourceVersion |
| provider resource ID | UID/name của custom resource hoặc ID tài nguyên ngoài cluster |

Broker cần lưu mapping ổn định giữa platform scope, instance ID, CR namespace/name/UID và provider resource reference. Không chỉ dựa vào tên CR có thể đoán được từ instance ID, vì tên Kubernetes có giới hạn ký tự, scope theo namespace và có thể có collision.

Ví dụ mapping:

~~~text
Platform: cf-prod
OSB instance_id: 2e3a...f91
Service: managed-postgresql
Plan: standard
Kubernetes namespace: broker-retail
Custom resource: databases/db-2e3af91
Custom resource UID: 8c7b...d21
Provider resource: cloud-db-88421
~~~

Giá trị trên là ví dụ minh họa. Trong production, broker nên lưu đầy đủ mapping trong database của mình, đồng thời gắn owner labels/annotations lên CR để reconciliation và cleanup có thể xác minh quyền sở hữu.

### Không dùng Kubernetes UID thay OSB instance_id

Kubernetes UID do API server cấp cho một object cụ thể. Khi CR bị xóa rồi tạo lại, UID thay đổi. OSB instance ID do Platform sử dụng để tham chiếu service instance trong suốt vòng đời nghiệp vụ. Broker phải giữ OSB ID ổn định và cập nhật mapping tới UID mới nếu có một quy trình tái tạo được cho phép.

ResourceVersion cũng không phải operation ID. ResourceVersion phục vụ concurrency và watch semantics của Kubernetes API; operation ID phục vụ Platform polling OSB last_operation.

## 5. Luồng provision: broker tạo custom resource, Operator thực thi

Một luồng provision có thể diễn ra như sau:

1. Platform gửi PUT provision với instance ID, service ID, plan ID, parameters và context.
2. Spring Cloud broker xác thực request, kiểm tra plan và idempotency.
3. Broker tạo operation record và mapping instance trong database.
4. Broker tạo Database custom resource với desired state tương ứng plan/parameters.
5. Operator watch CR, tạo database hoặc gọi provider.
6. Operator cập nhật status/conditions và observedGeneration.
7. Broker worker quan sát CR status hoặc nhận event.
8. Khi target state đã sẵn sàng, broker đánh dấu operation succeeded.
9. Cloud Controller/platform polling last_operation nhận kết quả cuối.

~~~mermaid
sequenceDiagram
    participant P as Platform
    participant B as Spring Cloud Broker
    participant DB as Broker DB
    participant K as Kubernetes API
    participant O as Database Operator
    participant D as Database Provider

    P->>B: PUT provision instance
    B->>DB: Save instance and operation
    B-->>P: 202 Accepted + operation ID
    B->>K: Create Database custom resource
    K-->>O: Watch event
    O->>K: Read desired spec
    O->>D: Create database
    D-->>O: Database ready
    O->>K: Update status Ready
    B->>K: Read CR status
    B->>DB: Mark operation succeeded
    P->>B: GET last_operation
    B->>DB: Read operation
    B-->>P: succeeded
~~~

Broker không cần giữ HTTP request mở trong suốt quá trình Operator reconcile. OSB operation và Kubernetes resource có vòng đời độc lập nhưng phải được liên kết bằng mapping bền vững.

### Vì sao cần database operation riêng?

CR status phản ánh trạng thái tài nguyên do Operator quản lý. OSB operation phản ánh một yêu cầu cụ thể từ Platform. Một instance có thể trải qua nhiều operation: provision, update rồi deprovision. Chỉ lưu một phase trong CR status sẽ không đủ để truy vết từng yêu cầu, xử lý retry của Platform hoặc trả đúng operation ID.

## 6. Update và deprovision qua Operator

### Update

Khi Platform gửi PATCH update, broker kiểm tra khả năng update của offering/plan và tính hợp lệ của thay đổi. Broker sau đó cập nhật spec của CR. Operator reconcile generation mới và cập nhật status khi thay đổi hoàn tất.

Quy trình cần:

- Lưu target plan và target parameters trong operation.
- So sánh spec hiện tại với target state.
- Không ghi đè các trường do Operator quản lý.
- Chờ observedGeneration tương ứng với spec mới.
- Kiểm tra condition Ready/Progressing/Degraded theo contract.
- Xử lý update lỗi một phần bằng retry, rollback hoặc forward recovery.

Không được xem PATCH thành công ở Kubernetes API là update service đã hoàn tất. PATCH chỉ cho biết API server nhận thay đổi; Operator có thể vẫn đang nâng cấp StatefulSet, migrate schema hoặc chờ provider.

### Deprovision

Khi nhận DELETE, broker cần xác minh instance thuộc đúng platform/tenant rồi yêu cầu xóa CR hoặc chuyển spec sang trạng thái xóa theo thiết kế Operator. Operator có thể dùng finalizer để dọn tài nguyên bên ngoài trước khi object bị xóa hoàn toàn.

Finalizer giúp bảo đảm cleanup có thể chạy khi database nằm ngoài cluster hoặc cần thu hồi credential. Broker nên theo dõi kết quả cleanup và chỉ báo OSB deprovision succeeded khi tài nguyên thuộc instance đã được xử lý theo policy.

Nếu CR biến mất nhưng provider database vẫn còn, broker không nên kết luận deprovision thành công chỉ dựa vào HTTP 404 từ Kubernetes API. Cần đối chiếu provider resource ID/owner metadata và cleanup orphan resource.

## 7. OSB service binding và Kubernetes ServiceBinding

Đây là nơi dễ nhầm nhất vì cả hai cùng dùng từ binding.

### OSB service binding

OSB API định nghĩa endpoint create/delete binding gắn với service instance và binding ID. Broker thực hiện cấp quyền truy cập, sinh credential hoặc tạo mapping cho một consumer. Platform nhận response credentials theo contract và quản lý quan hệ binding.

Một OSB binding có thể đại diện cho một database user, token, role, endpoint hoặc tập quyền truy cập riêng.

### Kubernetes ServiceBinding

Service Binding trong hệ sinh thái Kubernetes là một API/controller hướng tới việc liên kết backing service với workload. ServiceBinding resource tham chiếu service và workload. Controller tìm binding data, thường được lưu trong Secret hoặc được cung cấp theo convention của implementation, rồi đưa dữ liệu đó vào workload theo Service Binding Specification.

Một implementation có thể expose dữ liệu dưới dạng file trong thư mục binding và thiết lập biến môi trường SERVICE_BINDING_ROOT để ứng dụng tìm các binding. Chi tiết schema, API group, điều kiện và cách projection phụ thuộc phiên bản Service Binding Specification và controller được cài đặt.

Kubernetes ServiceBinding không tự động đồng nghĩa với việc gọi OSB PUT binding. Nó thường tiêu thụ thông tin kết nối đã tồn tại và đưa thông tin đó vào workload. Một integration layer có thể gọi OSB broker để tạo credential trước, sau đó tạo Secret/ServiceBinding resource để phân phối dữ liệu tới Pod.

### So sánh trực tiếp

| Nội dung | OSB binding | Kubernetes ServiceBinding |
|---|---|---|
| Đối tượng | Consumer binding với service instance | Quan hệ giữa workload và backing service |
| Đầu vào | instance ID, binding ID, service/plan và context | Service reference và workload reference |
| Tác vụ chính | Cấp hoặc thu hồi credential/quyền truy cập | Tìm binding data và đưa vào workload |
| Kết quả | OSB binding record và credentials | Files/environment/volume projection tùy implementation |
| Lifecycle owner | Broker và platform OSB | Service Binding controller và Kubernetes API |
| Có provision service không? | Không phải endpoint binding; provision là thao tác riêng | Không; thường tiêu thụ service đã provision |

## 8. Luồng kết hợp OSB binding với Service Binding

Một kiến trúc tích hợp có thể gồm broker tạo credential, Secret lưu dữ liệu kết nối và Service Binding controller đưa dữ liệu vào workload:

1. Database instance đã được provision và sẵn sàng.
2. Workload khai báo cần database service.
3. Integration controller hoặc automation gọi OSB create binding, sử dụng binding ID ổn định.
4. Broker tạo database principal/token riêng và lưu binding record.
5. Broker hoặc integration layer lưu credentials vào Kubernetes Secret đúng namespace.
6. Tạo ServiceBinding resource tham chiếu service và workload.
7. Service Binding controller kiểm tra reference, đọc binding data và cập nhật workload projection.
8. Pod mới nhận dữ liệu kết nối theo convention mà ứng dụng hỗ trợ.
9. Khi xóa ServiceBinding, integration layer phải thực hiện OSB unbind nếu mục tiêu là thu hồi credential; chỉ xóa projection chưa chắc đã thu hồi quyền tại provider.

~~~mermaid
sequenceDiagram
    participant W as Workload owner
    participant I as Integration controller
    participant B as OSB Broker
    participant DB as Database
    participant K as Kubernetes API
    participant S as Service Binding controller
    participant Pod as Application Pod

    W->>I: Request binding for workload
    I->>B: PUT OSB service binding
    B->>DB: Create principal and grants
    DB-->>B: Credentials created
    B-->>I: Binding credentials
    I->>K: Store Secret and ServiceBinding resource
    K-->>S: Watch ServiceBinding
    S->>K: Read service Secret and workload
    S->>K: Project binding data into workload
    K-->>Pod: Updated environment/files
    Pod->>DB: Connect with binding credentials
~~~

Đây là một integration pattern, không phải mọi Service Binding controller đều tự gọi OSB API. Nếu implementation không có adapter OSB, cần một thành phần tích hợp riêng chịu trách nhiệm tạo/xóa OSB binding và quản lý Secret.

### Thu hồi binding đúng cách

Khi workload không còn cần service:

- Ngừng hoặc cập nhật workload để không còn sử dụng credentials.
- Xóa ServiceBinding resource hoặc binding projection theo controller.
- Gọi OSB DELETE binding để thu hồi principal/token/quyền tại provider.
- Xác minh credential đã mất hiệu lực.
- Xóa Secret cũ theo retention policy.

Thứ tự có thể thay đổi theo yêu cầu zero-downtime và khả năng rotation. Điều quan trọng là xóa ServiceBinding object không tự động bảo đảm database user hoặc token đã bị revoke.

## 9. Secret, workload và Service Binding Specification

Binding data có thể chứa:

- host, port và database name.
- username/password.
- URI hoặc token.
- CA certificate hoặc thông tin TLS.
- Tên schema, role hoặc thông tin cấu hình khác.

Không nên hardcode credential vào Deployment YAML hoặc Git repository. Dữ liệu nhạy cảm cần được lưu trong Kubernetes Secret hoặc secret manager tích hợp, có RBAC và encryption at rest phù hợp. Secret mặc định không phải kho mã hóa hoàn chỉnh chỉ vì giá trị được biểu diễn bằng Base64.

Service Binding controller cần quyền đọc nguồn binding data và cập nhật workload projection trong phạm vi được phép. Không cấp quyền cluster-admin chỉ để đọc Secret. Tách namespace, service account và Role/RoleBinding theo tenant hoặc workload boundary.

### Files và environment

Service Binding Specification định hướng một convention để ứng dụng đọc binding data mà không phụ thuộc tên Secret cụ thể. Một implementation có thể mount dữ liệu thành cây thư mục và cung cấp SERVICE_BINDING_ROOT trỏ tới thư mục gốc.

Ví dụ cấu trúc khái niệm:

~~~text
/bindings/
  orders-db/
    type
    provider
    host
    port
    username
    password
    uri
~~~

Đây là ví dụ minh họa; file nào xuất hiện phụ thuộc dữ liệu service và implementation. Ứng dụng cần xử lý trường có thể thiếu, secret rotation và lỗi khi binding chưa sẵn sàng. Không giả định mọi service đều cung cấp đủ host, port, username, password.

Ví dụ workload đọc binding root:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-api
  namespace: retail
spec:
  replicas: 2
  selector:
    matchLabels:
      app: orders-api
  template:
    metadata:
      labels:
        app: orders-api
    spec:
      containers:
        - name: app
          image: example/orders-api:1.0
          env:
            - name: SERVICE_BINDING_ROOT
              value: /bindings
~~~

Đoạn YAML minh họa biến môi trường theo convention; việc mount binding files và cập nhật Pod do Service Binding controller thực hiện theo API/implementation đang dùng.

## 10. Thiết kế CRD cho broker và Operator

Nếu broker dùng Operator để quản lý provider, cần thiết kế custom resource thể hiện đúng desired state và ownership.

Ví dụ CR provision:

~~~yaml
apiVersion: broker.example.io/v1alpha1
kind: ManagedDatabase
metadata:
  name: db-2e3af91
  namespace: broker-retail
  labels:
    broker.example.io/instance-hash: 2e3af91
  annotations:
    broker.example.io/platform-id: cf-prod
    broker.example.io/osb-instance-id: 2e3a-example-f91
spec:
  plan: standard
  engine: postgresql
  storage: 50Gi
  backup:
    enabled: true
status:
  conditions:
    - type: Ready
      status: "False"
      reason: Provisioning
      message: Waiting for database provider
~~~

Không nên lưu password trong annotation hoặc label. Label phù hợp với selector có giá trị ngắn, không nhạy cảm; annotation lưu metadata không nhạy cảm cần thiết. Mapping đầy đủ và secret reference nên nằm trong database/secret store.

### Thiết kế schema

CRD nên:

- Dùng OpenAPI schema validation cho spec.
- Giới hạn enum, min/max và quantity.
- Có default rõ ràng.
- Tách spec do broker quản lý khỏi status do Operator quản lý.
- Dùng status subresource.
- Có versioning và conversion strategy khi API thay đổi.
- Không cho người dùng sửa trường ownership hoặc provider identity tùy ý.

Broker chỉ cập nhật trường spec thuộc quyền của nó. Operator chỉ cập nhật status và các trường được quy định trong contract. Nếu cả hai cùng ghi một object mà không có quy ước ownership, update có thể ghi đè lẫn nhau.

### Owner reference và finalizer

OwnerReference phù hợp cho resource phụ thuộc trong cùng scope khi Kubernetes garbage collection có thể quản lý. Tài nguyên bên ngoài cluster hoặc cần cleanup nghiệp vụ thường cần finalizer và state lưu bền vững. Không dùng owner reference như bằng chứng duy nhất rằng provider resource đã được thu hồi.

Khi xóa custom resource, finalizer có thể giữ object ở trạng thái Terminating cho đến khi Operator hoàn tất cleanup. Broker phải có timeout, reconciliation và cảnh báo nếu finalizer bị kẹt.

## 11. Idempotency và concurrency giữa broker với Operator

OSB request có thể retry vì Platform timeout. Kubernetes watch event cũng có thể được phát lại; controller reconcile cùng một resource nhiều lần là hành vi bình thường. Vì vậy, cả broker và Operator đều phải idempotent.

### Broker chịu trách nhiệm

- Map cùng platform scope + instance ID tới cùng một logical service instance.
- Dùng unique constraint hoặc lock để tránh tạo hai CR cho cùng instance.
- Ghi operation và mapping trước khi trả 202.
- Nếu CR đã tồn tại, xác minh owner metadata và desired spec trước khi coi request là retry.
- Không tạo operation mới cho cùng request intent khi retry.
- Reconcile provider outcome nếu timeout xảy ra sau side effect.

### Operator chịu trách nhiệm

- Reconcile theo desired state, không dựa vào số lần event được phát.
- Dùng resourceVersion/optimistic concurrency khi update object.
- Không tạo resource phụ thuộc trùng nếu reconcile chạy lại.
- Gắn owner identity và labels để tìm resource.
- Cập nhật conditions và observedGeneration nhất quán.
- Xử lý finalizer/cleanup có thể retry.

### Không dùng event delivery làm đảm bảo exactly-once

Kubernetes watch, queue hoặc event bus có thể phát lại thông báo. Mục tiêu thực tế là xử lý at-least-once an toàn bằng idempotency, compare-and-set và reconciliation. Không giả định mỗi OSB request hoặc mỗi event chỉ được xử lý đúng một lần.

## 12. Bảo mật multi-tenant

Một broker có thể phục vụ nhiều Cloud Foundry foundation, Kubernetes namespace hoặc tenant. Ranh giới bảo mật cần được duy trì xuyên suốt OSB, CRD, Secret và workload.

- Xác thực Platform gọi broker bằng cơ chế broker registration đã cấu hình.
- Xác định platform scope từ caller đã xác thực, không tin namespace do request tùy ý cung cấp.
- Map tenant tới namespace theo policy server-side.
- Broker service account chỉ có quyền CRUD các CRD cần thiết trong namespace được phép.
- Operator có quyền đúng phạm vi để quản lý provider resource.
- Service Binding controller chỉ đọc binding data và sửa workload được policy cho phép.
- Secret phải có owner/namespace rõ ràng, RBAC hạn chế và encryption at rest.
- Không log Secret object hoặc credentials response.
- Dùng NetworkPolicy, egress control và workload identity khi phù hợp.
- Kiểm tra owner metadata trước khi update hoặc xóa CR.

Không cho phép một OSB binding trong namespace A tham chiếu Secret của namespace B chỉ bằng cách thay tên trong custom resource. Cross-namespace reference phải được kiểm soát rõ ràng bởi controller và policy.

## 13. Khi nào dùng OSB, Operator hay Service Binding?

| Nhu cầu | Cơ chế phù hợp | Lý do |
|---|---|---|
| Cloud Foundry cần marketplace và plan | OSB API broker | Cloud Controller tích hợp trực tiếp contract OSB |
| Quản lý database/queue trên Kubernetes bằng desired state | Operator | CRD và reconciliation phù hợp với lifecycle tài nguyên |
| Đưa credentials của backing service vào Pod | Service Binding | Chuẩn hóa cách workload nhận binding data |
| Một broker cần phục vụ cả Cloud Foundry và Kubernetes | OSB API + adapter Kubernetes/Operator | OSB làm platform contract; Operator thực thi resource |
| Workload trên Kubernetes cần dùng service đã provision bên ngoài cluster | Service Binding + Secret/integration | Không cần service phải có Pod trong cluster |
| Chỉ cần một Service nội bộ trỏ tới Pod | Kubernetes Service | Đây là discovery/networking, không phải service broker |

### Kiến trúc kết hợp được khuyến nghị

Với Spring Cloud Service Broker, một thiết kế có thể chia:

1. OSB API layer: cung cấp catalog, provision, update, deprovision, bind và unbind.
2. Application/domain layer: quản lý instance, plan, binding, operation, idempotency và tenant scope.
3. Kubernetes adapter: tạo/đọc/update/delete custom resource qua Kubernetes API.
4. Operator: thực hiện reconcile và điều khiển provider resource.
5. Binding integration: tạo Secret và ServiceBinding resource hoặc gọi controller tương ứng để phân phối credentials.
6. Secret manager: quản lý secret material, rotation và audit.

Cloud Foundry có thể tiếp tục gọi OSB broker mà không cần biết broker dùng Kubernetes Operator phía sau. Kubernetes workload có thể sử dụng Service Binding để nhận credentials mà không cần hiểu endpoint OSB. Broker và integration controller là cầu nối giữa hai contract.

## 14. Tích hợp với Spring Cloud Open Service Broker

Spring Cloud Open Service Broker cung cấp abstraction để triển khai OSB API. Phần tích hợp Kubernetes nên nằm sau application service, không đặt Kubernetes client trực tiếp trong controller HTTP.

Một cấu trúc package tham khảo:

~~~text
service-broker/
  osb/
    CatalogService
    ServiceInstanceService
    ServiceInstanceBindingService
  application/
    ProvisioningService
    UpdatingService
    DeprovisioningService
    BindingService
    OperationCoordinator
  domain/
    ServiceInstance
    ServiceBinding
    ServiceOperation
    PlanDefinition
  persistence/
    InstanceRepository
    BindingRepository
    OperationRepository
  kubernetes/
    CustomResourceGateway
    OperatorStatusReader
    SecretBindingGateway
  provider/
    DatabaseProviderAdapter
~~~

### Provision service

Pseudocode:

~~~java
ProvisionResult provision(ProvisionCommand command) {
    var instance = instanceRepository.find(
            command.platformId(), command.instanceId());

    if (instance != null) {
        return idempotencyService.resolveProvisionRetry(
                instance, command);
    }

    var operation = operationService.accept(command);
    var resourceName = resourceNameFactory.forInstance(
            command.platformId(), command.instanceId());

    customResourceGateway.createManagedDatabase(
            command.namespace(),
            resourceName,
            command.plan(),
            command.parameters(),
            operation.id());

    return ProvisionResult.accepted(operation.id());
}
~~~

Đây là pseudocode thể hiện trách nhiệm, không phải chữ ký API chính xác của Spring Cloud Open Service Broker hoặc Kubernetes Java client. Transaction thực tế cần bảo đảm operation, instance mapping và ý định tạo CR được lưu nhất quán; có thể dùng transactional outbox để tránh mất việc giữa database và Kubernetes API.

### Theo dõi Operator status

~~~java
void reconcileOperation(ServiceOperation operation) {
    var resource = customResourceGateway.get(
            operation.namespace(), operation.resourceName());

    if (resource == null) {
        operationService.markForReconciliation(operation.id());
        return;
    }

    if (!resource.belongsTo(operation.platformId(),
            operation.instanceId())) {
        operationService.markFailed(
                operation.id(), "Resource ownership mismatch");
        return;
    }

    var status = operatorStatusReader.read(resource);
    if (status.observedGeneration() < resource.generation()) {
        operationService.keepInProgress(operation.id());
        return;
    }

    if (status.ready()) {
        operationService.markSucceeded(operation.id());
    } else if (status.terminalFailure()) {
        operationService.markFailed(
                operation.id(), status.safeDescription());
    } else {
        operationService.keepInProgress(operation.id());
    }
}
~~~

Worker phải kiểm tra operation version/fencing token và owner metadata trước khi ghi kết quả. Không chuyển operation sang succeeded chỉ vì custom resource đã được tạo hoặc PATCH thành công.

### Binding service

Binding flow có thể:

- Tạo OSB binding record với binding ID.
- Yêu cầu provider/operator cấp principal hoặc token.
- Lưu secret material vào secret manager.
- Tạo Kubernetes Secret trong namespace của workload hoặc namespace binding được kiểm soát.
- Tạo ServiceBinding resource nếu controller được cài đặt và schema phù hợp.
- Trả credentials theo OSB response cho Cloud Foundry caller nếu đây là OSB binding.

Không phải mọi binding đều cần ServiceBinding resource. Nếu consumer là Cloud Foundry application, Cloud Controller quản lý binding theo OSB contract. Nếu consumer là Kubernetes workload, Service Binding controller có thể giúp projection dữ liệu vào Pod.

## 15. Kiểm thử tích hợp

Kiểm thử cần bao phủ cả ba lớp và các ranh giới ownership.

| Ca kiểm thử | Kết quả mong đợi |
|---|---|
| Catalog broker | Trả offering/plan ổn định, không phụ thuộc CRD name |
| Provision request lặp | Chỉ một logical instance và một CR do broker sở hữu |
| Operator chưa reconcile | OSB operation tiếp tục in progress |
| observedGeneration cũ | Broker chưa báo update succeeded |
| Operator condition Ready | Operation được hoàn tất sau khi xác minh target |
| Operator terminal failure | OSB last_operation trả failed với safe description |
| Broker restart sau khi tạo CR | Worker tìm lại CR bằng mapping/owner metadata |
| CR bị xóa ngoài ý muốn | Broker reconcile hoặc báo lỗi theo policy, không tạo tài nguyên trùng mù quáng |
| CR ownership mismatch | Không update/delete resource thuộc tenant khác |
| Deprovision có finalizer | Broker chờ cleanup và xử lý timeout/finalizer stuck |
| Secret được tạo | Secret nằm đúng namespace và chỉ principal cần thiết đọc được |
| ServiceBinding projection | Workload nhận binding data theo convention của controller |
| Xóa ServiceBinding | Projection bị gỡ; OSB unbind được gọi nếu cần thu hồi credential |
| Secret rotation | Workload nhận dữ liệu mới theo policy và credential cũ bị revoke |
| Namespace isolation | Workload tenant khác không đọc được Secret |
| Operator event bị phát lại | Reconciliation không tạo resource trùng |

### Kiểm thử failure injection

Giả lập các tình huống:

- Broker timeout sau khi Kubernetes API đã nhận CR create.
- Operator crash sau khi provider đã tạo database nhưng trước khi update status.
- Kubernetes API trả 409 resourceVersion conflict.
- Finalizer cleanup bị provider timeout.
- Secret đã được tạo nhưng ServiceBinding resource chưa được commit.
- Workload rollout thất bại sau khi binding data thay đổi.

Sau mỗi tình huống, xác minh broker và Operator có thể reconcile tới trạng thái cuối mà không nhân đôi tài nguyên, không lộ credentials và không báo succeeded khi workload/provider chưa sẵn sàng.

## 16. Lỗi thiết kế thường gặp

### Coi Operator là OSB broker

Operator thường quản lý custom resource của domain. Nó không tự cung cấp catalog, plan, service access hay endpoint OSB. Nếu platform yêu cầu OSB, cần broker hoặc adapter triển khai contract đó.

### Coi ServiceBinding là provision

ServiceBinding kết nối workload với binding data. Nó không mặc định tạo database hoặc cấp quyền tại provider. Provision và bind phải được thực hiện bởi broker/provider workflow tương ứng.

### Coi Kubernetes Service là OSB service

Kubernetes Service cung cấp network endpoint cho Pod. OSB service là offering trong catalog; một service instance có thể là database managed ngoài cluster và không có Kubernetes Service object.

### Đánh dấu succeeded ngay khi tạo CR

Kubernetes API nhận object chỉ xác nhận desired state đã được ghi. Operator có thể chưa tạo tài nguyên thật. Hãy chờ status/conditions và observedGeneration.

### Dùng CR status thay operation repository

Một CR có thể trải qua nhiều OSB operation. Không có lịch sử request, operation ID và retry identity đầy đủ nếu chỉ dựa vào một trường phase.

### Xóa Secret nhưng quên revoke provider credential

Workload không còn nhìn thấy Secret nhưng credential cũ có thể vẫn kết nối được. Unbind phải thu hồi quyền tại provider và xác minh kết quả.

### Cấp quyền cluster-wide quá rộng

Broker hoặc binding controller có thể đọc Secret của tenant khác. Phải thiết kế namespace boundary, RBAC và reference policy ngay từ đầu.

## 17. Checklist triển khai

- [ ] Xác định OSB API là contract platform-facing và Operator là implementation-facing.
- [ ] Catalog service/plan ID ổn định, độc lập với CRD name/version.
- [ ] Mapping platform scope + instance ID tới CR namespace/name/UID được lưu bền vững.
- [ ] CRD schema có validation, status subresource và versioning.
- [ ] Broker không sửa status do Operator quản lý.
- [ ] Operation được lưu trước khi trả 202 và có thể recovery.
- [ ] Broker chỉ báo succeeded khi observedGeneration/condition xác nhận target state.
- [ ] Operator reconcile idempotent và xử lý duplicate event an toàn.
- [ ] Update/deprovision có concurrency, finalizer và cleanup policy.
- [ ] OSB binding và Kubernetes ServiceBinding được mô hình hóa riêng.
- [ ] Binding data được lưu trong Secret/secret manager với RBAC tối thiểu.
- [ ] ServiceBinding projection không bị hiểu nhầm là thu hồi credential.
- [ ] Unbind thu hồi principal/token tại provider và xác minh hiệu lực.
- [ ] Tenant namespace, owner metadata và cross-namespace reference được kiểm soát.
- [ ] Có test restart, timeout, duplicate event, stale generation và secret rotation.
- [ ] Log, status message và metric không làm lộ secret.

## Kết luận

OSB API, Kubernetes Operator và Service Binding giải quyết ba lớp khác nhau. OSB cung cấp contract marketplace và vòng đời service instance/binding cho platform; Operator quản lý desired state của tài nguyên bằng CRD và reconciliation; Service Binding chuẩn hóa cách workload nhận dữ liệu kết nối tới backing service. Một Spring Cloud Service Broker có thể dùng OSB làm giao diện bên ngoài, tạo custom resource để Operator thực thi provision/update/deprovision, rồi phối hợp Secret và ServiceBinding resource để cấp dữ liệu kết nối cho workload Kubernetes. Khi giữ riêng operation ID, instance ID, CR identity và binding identity, đồng thời quản lý ownership, status, finalizer và Secret đúng cách, kiến trúc có thể phục vụ cả Cloud Foundry lẫn Kubernetes mà không trộn lẫn trách nhiệm của từng hệ sinh thái.

## Tài liệu tham khảo

- [Open Service Broker API Specification](https://github.com/cloudfoundry/servicebroker/blob/master/spec.md)
- [Kubernetes Documentation — Operator pattern](https://kubernetes.io/docs/concepts/extend-kubernetes/operator/)
- [Kubernetes Documentation — Custom Resources](https://kubernetes.io/docs/concepts/extend-kubernetes/api-extension/custom-resources/)
- [Kubernetes Documentation — Secrets](https://kubernetes.io/docs/concepts/configuration/secret/)
- [Service Binding Specification](https://servicebinding.io/)
