# Service Catalog đã ngừng duy trì và giới hạn khi vận hành hệ thống cũ

## Mục tiêu và bối cảnh

Kubernetes Service Catalog từng cung cấp một lớp API để ứng dụng và người vận hành trong Kubernetes sử dụng các dịch vụ bên ngoài thông qua Open Service Broker API (OSB API). Người dùng có thể đăng ký broker, xem service offering và plan, tạo service instance, bind workload để nhận credentials, rồi thu hồi binding hoặc instance bằng các đối tượng Kubernetes.

Dự án Kubernetes Service Catalog cũ hiện là công nghệ legacy và không còn được phát triển tích cực như một thành phần nền tảng hiện đại. Điều này tạo ra rủi ro khi vận hành trên các Kubernetes version mới: khả năng tương thích, bản vá bảo mật, dependency, API aggregation và hỗ trợ cộng đồng có thể không còn đáp ứng yêu cầu production.

Cần phân biệt rõ hai khái niệm:

- **Kubernetes Service Catalog:** dự án tích hợp Kubernetes với broker theo OSB API, hiện đã ngừng duy trì tích cực.
- **Open Service Broker API:** giao thức HTTP chuẩn hóa cách platform trao đổi với service broker. Việc dự án Kubernetes Service Catalog ngừng duy trì không có nghĩa OSB API tự động bị khai tử hoặc mọi broker dùng OSB đều phải ngừng hoạt động.

Bài học này giúp đánh giá hệ thống cũ, hiểu kiến trúc và giới hạn của Service Catalog, vận hành tạm thời có kiểm soát và lựa chọn hướng thay thế phù hợp như Crossplane, Service Binding Specification hoặc Kubernetes Operator chuyên biệt.

Sau bài học, bạn có thể:

- Nhận diện các thành phần và đối tượng của Kubernetes Service Catalog legacy.
- Mô tả luồng đăng ký broker, đồng bộ catalog, provision và binding.
- Đánh giá rủi ro tương thích, bảo mật và vận hành khi tiếp tục dùng hệ thống cũ.
- Kiểm kê và bảo vệ instance, binding, secret cùng backend resource trước migration.
- Phân biệt chức năng provisioning với chức năng binding workload.
- Chọn hướng thay thế mà không giả định các công nghệ mới tương thích trực tiếp với OSB API.
- Lập kế hoạch chuyển đổi có kiểm soát và tránh xóa nhầm tài nguyên đang được sử dụng.

## 1. Phạm vi của Kubernetes Service Catalog

Kubernetes Service Catalog là một dự án mở rộng Kubernetes để sử dụng dịch vụ do một service broker cung cấp. Nó ánh xạ mô hình của OSB API thành các đối tượng và quy trình điều khiển trong Kubernetes.

Một hệ thống Service Catalog legacy thường gồm:

- API server mở rộng để cung cấp các API Service Catalog cho Kubernetes.
- Controller manager theo dõi đối tượng và điều phối lifecycle.
- Service broker được đăng ký bằng URL và credentials.
- Các đối tượng mô tả broker, service class và plan.
- Service instance và service binding đại diện cho tài nguyên đã provision và credentials được cấp.
- Công cụ CLI như svcat từng được dùng để thao tác với các đối tượng này.

Service Catalog không phải là một phần mặc định của Kubernetes core. Việc cài đặt nó bổ sung các thành phần API và controller riêng vào cluster. Do đó, vòng đời của nó còn phụ thuộc vào cách cài đặt, phiên bản Kubernetes, phiên bản API extension và các thành phần đi kèm.

### 1.1. Phân biệt Service Catalog với catalog trong OSB API

OSB API định nghĩa endpoint catalog của broker. Broker trả danh sách service offering và plan mà nó hỗ trợ.

Kubernetes Service Catalog tiêu thụ catalog đó rồi biểu diễn các mục phù hợp thành tài nguyên Kubernetes để người dùng có thể chọn và tạo instance.

Luồng khái quát:

~~~mermaid
flowchart TD
    U[Developer / Operator] --> K[Kubernetes API]
    K --> SC[Service Catalog API]
    SC --> C[Service Catalog Controller]
    C --> B[Open Service Broker API]
    B --> CAT[Service offerings và plans]
    C --> I[ServiceInstance]
    C --> BD[ServiceBinding]
    B --> R[External resources]
    BD --> S[Kubernetes Secret]
    W[Workload] --> S
~~~

Catalog trong OSB API là hợp đồng do broker công bố. Kubernetes Service Catalog là lớp tích hợp cũ dùng catalog đó để điều khiển tài nguyên trong cluster. Không nên dùng hai tên gọi này như thể chúng là cùng một sản phẩm.

## 2. Kiến trúc và các đối tượng của Service Catalog legacy

Service Catalog chuyển các khái niệm của broker thành các tài nguyên mà Kubernetes API có thể lưu trữ và controller có thể reconcile.

Các đối tượng thường gặp:

| Đối tượng | Vai trò |
|---|---|
| ServiceBroker | Đăng ký broker trong phạm vi namespace theo mô hình của phiên bản Service Catalog |
| ClusterServiceBroker | Đăng ký broker ở phạm vi cluster |
| ServiceClass / ClusterServiceClass | Biểu diễn service offering được đồng bộ từ catalog |
| ServicePlan / ClusterServicePlan | Biểu diễn plan thuộc một service class |
| ServiceInstance | Yêu cầu tạo và quản lý một instance của service |
| ServiceBinding | Yêu cầu cấp credentials hoặc quyền truy cập cho workload |

Tên và scope cụ thể có thể khác theo phiên bản cài đặt. Cần kiểm tra API resource thực tế của cluster legacy trước khi viết automation hoặc migration script.

### 2.1. ServiceBroker và ClusterServiceBroker

ServiceBroker đăng ký một broker trong phạm vi namespace theo mô hình của hệ thống. ClusterServiceBroker cho phép công bố broker ở phạm vi cluster và có thể làm các offering của broker hiển thị cho nhiều namespace theo policy.

Broker registration thường lưu:

- URL của OSB API.
- Credentials để controller xác thực khi gọi broker.
- Trạng thái đồng bộ catalog.
- Thông tin scope và cấu hình truy cập.

Cluster-scoped broker mở rộng phạm vi tin cậy. Nếu broker có quyền provision tài nguyên trong cloud account dùng chung, việc đăng ký ở cấp cluster có thể ảnh hưởng nhiều tenant. Cần giới hạn RBAC, network access và quyền backend theo phạm vi tối thiểu.

### 2.2. ServiceClass và ServicePlan

Controller đọc catalog của broker rồi tạo các đối tượng đại diện cho service và plan. Người dùng chọn class và plan để tạo ServiceInstance.

Các định danh service và plan có ý nghĩa lâu dài. Không nên tạo ID mới cho cùng một offering sau mỗi lần deploy broker. Nếu ID thay đổi, các instance hiện hữu có thể không còn liên kết rõ ràng với catalog mới.

### 2.3. ServiceInstance và ServiceBinding

ServiceInstance đại diện cho một tài nguyên dịch vụ được yêu cầu thông qua broker, chẳng hạn database hoặc message queue. Controller điều phối provision và theo dõi trạng thái.

ServiceBinding đại diện cho quan hệ giữa instance và một consumer. Khi broker hoàn tất bind, thông tin credentials hoặc binding data có thể được lưu trong Kubernetes Secret để workload sử dụng.

Không đồng nhất ServiceBinding với Secret. Secret là nơi lưu dữ liệu nhạy cảm cho workload; binding còn là đối tượng lifecycle để controller và broker biết quyền nào cần tạo hoặc thu hồi.

## 3. Luồng hoạt động của hệ thống cũ

Một luồng điển hình gồm đăng ký broker, đồng bộ catalog, tạo instance và tạo binding.

~~~mermaid
sequenceDiagram
    participant U as Operator
    participant K as Kubernetes API
    participant C as Service Catalog Controller
    participant B as OSB Broker
    participant P as Provider Backend
    participant S as Kubernetes Secret
    U->>K: Tạo ServiceBroker
    K->>C: Thông báo object mới
    C->>B: GET /v2/catalog
    B-->>C: Services và plans
    C->>K: Cập nhật ServiceClass / ServicePlan
    U->>K: Tạo ServiceInstance
    K->>C: Reconcile instance
    C->>B: PUT provision
    B->>P: Tạo tài nguyên
    P-->>B: Resource result
    B-->>C: Provision response
    U->>K: Tạo ServiceBinding
    K->>C: Reconcile binding
    C->>B: PUT bind
    B-->>C: Credentials
    C->>S: Lưu binding data
~~~

### 3.1. Đăng ký broker và đồng bộ catalog

Operator tạo đối tượng broker chứa endpoint và thông tin xác thực. Controller đọc cấu hình, gọi endpoint catalog của broker rồi đồng bộ service và plan.

Nếu broker không truy cập được, credentials sai hoặc catalog không hợp lệ, trạng thái broker có thể không sẵn sàng. Khi đó người dùng không nên tiếp tục tạo instance dựa trên catalog cũ mà chưa xác định được catalog đó còn phù hợp hay không.

### 3.2. Provision service instance

Người dùng tạo ServiceInstance tham chiếu service class và plan. Controller gọi endpoint provision của broker với instance ID và parameters.

Nếu broker hỗ trợ asynchronous provisioning và yêu cầu được chấp nhận ở chế độ async, controller theo dõi operation bằng endpoint last_operation. Trạng thái Kubernetes cần phản ánh kết quả mà broker trả về, không chỉ việc API object đã được tạo.

### 3.3. Bind workload

Người dùng tạo ServiceBinding tham chiếu ServiceInstance và consumer. Controller gọi bind endpoint của broker. Khi thành công, credentials hoặc binding data được lưu thành Secret để workload có thể mount hoặc đọc qua cơ chế được cấu hình.

Khi binding bị xóa, controller yêu cầu broker unbind. Broker phải thu hồi quyền backend của đúng binding. Việc xóa Secret trong Kubernetes không tự làm credentials đã được workload đọc trước đó mất hiệu lực.

### 3.4. Deprovision instance

Khi ServiceInstance không còn cần thiết, controller yêu cầu broker deprovision. Việc xóa object Kubernetes và việc thu hồi tài nguyên backend là hai bước liên quan nhưng không đồng nhất. Cần xác nhận deprovision đã hoàn tất hoặc có quy trình retry trước khi xóa dữ liệu điều phối cần thiết.

## 4. Vì sao Service Catalog cũ đã trở thành công nghệ legacy?

Dự án Kubernetes Service Catalog đã ngừng được phát triển tích cực và không còn là lựa chọn mặc định cho kiến trúc Kubernetes mới. Khi một dự án tích hợp sâu với Kubernetes API không còn được duy trì, chi phí vận hành tăng theo thời gian.

Các giới hạn thường gặp:

1. **Tương thích Kubernetes:** API aggregation, dependency và controller cũ có thể không tương thích với Kubernetes version mới hoặc chính sách bảo mật hiện tại.
2. **Bản vá bảo mật:** việc nhận bản vá cho thành phần API server, controller và dependency không còn được bảo đảm như một dự án đang phát triển.
3. **Chi phí vận hành:** cluster phải duy trì thêm API service, controller manager, RBAC, certificates, monitoring và quy trình nâng cấp riêng.
4. **Phụ thuộc vào controller legacy:** lỗi reconcile hoặc controller dừng có thể làm instance và binding mắc kẹt ở trạng thái trung gian.
5. **Khả năng mở rộng và quan sát:** cách theo dõi trạng thái, event, retry và troubleshooting có thể không phù hợp với tiêu chuẩn vận hành hiện tại.
6. **Ranh giới bảo mật:** broker ở phạm vi cluster có thể nắm credentials và quyền tạo tài nguyên ngoài cluster; sai cấu hình có thể ảnh hưởng nhiều tenant.
7. **Khó tích hợp mô hình Kubernetes hiện đại:** các workload và operator mới thường dùng CRD, controller và cơ chế binding riêng thay vì Service Catalog API cũ.

Không nên hiểu việc dự án ngừng duy trì là mọi cluster đang chạy nó sẽ ngừng hoạt động ngay. Một hệ thống legacy có thể tiếp tục chạy trong môi trường tương thích. Rủi ro nằm ở khả năng xử lý lỗi mới, vá lỗ hổng, nâng cấp Kubernetes và duy trì tích hợp lâu dài.

## 5. Giới hạn khi vận hành hệ thống cũ

### 5.1. API aggregation và dependency

Service Catalog được cài như một phần mở rộng API, không phải chỉ là một thư viện trong ứng dụng. Khi API server extension không sẵn sàng, Kubernetes API discovery hoặc thao tác với các resource Service Catalog có thể bị ảnh hưởng.

Trước khi nâng cấp cluster, cần xác định:

- APIService hoặc API registration nào được cài bởi Service Catalog.
- Phiên bản API group và resource đang được sử dụng.
- Controller manager và API server extension chạy ở namespace nào.
- Các certificate, service account và RBAC liên quan.
- Dependency như storage, webhook hoặc thành phần phụ trợ mà bản cài đặt yêu cầu.

Không xóa APIService hoặc deployment legacy chỉ vì thấy chúng không thuộc Kubernetes core. Có thể workload vẫn phụ thuộc vào API đó.

### 5.2. Vòng đời controller và trạng thái bị kẹt

Controller hoạt động theo mô hình reconcile: đọc trạng thái mong muốn từ Kubernetes API, so sánh với trạng thái đã biết rồi gọi broker để đưa hệ thống về trạng thái phù hợp.

Nếu controller dừng hoặc request broker thất bại, object có thể ở trạng thái đang provision, binding hoặc deprovision. Khi controller được khởi động lại, khả năng tiếp tục phụ thuộc vào trạng thái đã lưu, retry logic và khả năng idempotent của broker.

Với hệ thống legacy, cần có quy trình kiểm tra thủ công:

- Object nào đang chờ quá lâu?
- Broker có operation tương ứng không?
- Backend resource đã được tạo hay chưa?
- Secret binding có tồn tại và còn hợp lệ không?
- Có resource orphan hoặc credentials chưa bị revoke không?

Không sửa status object bằng tay để làm cho giao diện trông như đã hoàn tất nếu chưa xác minh backend.

### 5.3. Quản lý Secret và vòng đời credentials

Binding credentials thường nhạy cảm. Secret có thể bị sao chép vào pod hoặc hệ thống triển khai. Xóa Secret không thu hồi được credential đã được consumer đọc và giữ trong bộ nhớ.

Khi unbind:

1. Xác định backend principal gắn với binding.
2. Yêu cầu broker revoke credentials hoặc grant.
3. Xác nhận quyền cũ không còn hiệu lực.
4. Dọn Secret và metadata liên quan.
5. Ghi audit và xử lý cleanup còn lại.

Nếu chỉ xóa Secret, workload cũ có thể tiếp tục kết nối bằng credentials còn hiệu lực. Đây là rủi ro bảo mật nghiêm trọng khi vận hành Service Catalog legacy.

### 5.4. Phạm vi cluster và namespace

ServiceBroker theo namespace và ClusterServiceBroker theo cluster có ranh giới quyền khác nhau. Đăng ký broker ở phạm vi cluster thuận tiện cho chia sẻ offering nhưng làm tăng blast radius nếu broker credentials hoặc backend quyền bị lộ.

Cần kiểm tra:

- Ai được tạo hoặc sửa broker registration?
- Namespace nào được phép tạo instance?
- Secret binding được tạo trong namespace nào?
- Controller có quyền đọc Secret ở những namespace nào?
- Backend credentials được giới hạn theo tenant hay dùng chung?
- Có policy ngăn namespace không được phép truy cập offering hay không?

Không dựa vào việc object nằm trong namespace để kết luận backend resource đã được cô lập theo namespace.

## 6. Rủi ro khi nâng cấp Kubernetes

Trước khi nâng cấp Kubernetes, cần đánh giá riêng Service Catalog thay vì coi nó là một thành phần mặc định sẽ tự tương thích.

Các bước đánh giá:

1. Xác định chính xác phiên bản Service Catalog và các image đang chạy.
2. Đối chiếu API group, APIService, admission webhook và dependency.
3. Kiểm tra tương thích với phiên bản Kubernetes đích.
4. Kiểm tra các API đã bị loại bỏ hoặc thay đổi.
5. Thử nâng cấp trên cluster staging có dữ liệu và resource mẫu.
6. Xác minh controller có thể reconcile ServiceBroker, ServiceInstance và ServiceBinding.
7. Kiểm tra provision, bind, unbind và deprovision end-to-end.
8. Xác nhận rollback có thể phục hồi API extension và trạng thái đã lưu.

Nếu không còn bản phát hành hỗ trợ Kubernetes version đích, không nên giả định có thể khắc phục chỉ bằng cách sửa image tag. Cần lập kế hoạch di chuyển khỏi Service Catalog trước hoặc đồng thời với việc nâng cấp cluster.

## 7. Vận hành tạm thời có kiểm soát

Một hệ thống legacy đôi khi chưa thể thay thế ngay vì có nhiều service instance đang chạy hoặc ứng dụng phụ thuộc vào binding hiện tại. Có thể tiếp tục vận hành trong một khoảng chuyển tiếp nếu kiểm soát rõ rủi ro.

### 7.1. Đóng băng thay đổi không cần thiết

- Hạn chế thêm broker hoặc service plan mới.
- Tránh thay đổi service ID và plan ID.
- Hạn chế nâng cấp controller không có bản tương thích đã kiểm chứng.
- Duy trì catalog và endpoint broker ổn định.
- Chỉ cho phép operator có quyền phù hợp thay đổi cấu hình.

### 7.2. Bảo vệ đường kết nối broker

- Dùng TLS với certificate còn hiệu lực.
- Giới hạn network path từ controller tới broker.
- Rotate broker credentials theo quy trình có kiểm thử.
- Giới hạn quyền backend service account.
- Không để credentials trong manifest hoặc log.
- Theo dõi các request catalog, provision, bind và delete bất thường.

### 7.3. Theo dõi trạng thái và đối chiếu backend

Cần có inventory định kỳ so sánh:

- ServiceInstance trong Kubernetes.
- ServiceBinding và Secret.
- Operation record tại broker.
- External resource reference ở backend.
- Principal và quyền truy cập thực tế.

Đối chiếu giúp phát hiện instance đã bị xóa ở Kubernetes nhưng tài nguyên cloud còn tồn tại, binding không còn object nhưng backend user vẫn hoạt động, hoặc Secret không còn nhưng credentials chưa bị revoke.

### 7.4. Sao lưu trước mọi thay đổi

Sao lưu cần bao gồm:

- Kubernetes API objects thuộc Service Catalog.
- Secret và dữ liệu nhạy cảm bằng cơ chế mã hóa phù hợp.
- Broker database và operation records.
- Cấu hình broker registration và controller.
- External resource identifiers và metadata cần để phục hồi.

Một bản backup chỉ chứa YAML không đủ nếu thiếu secret, database state hoặc mapping tới backend resource. Kiểm tra khả năng restore trên môi trường thử nghiệm.

## 8. Các hướng thay thế

Không có một sản phẩm thay thế duy nhất phù hợp cho mọi hệ thống. Chọn công nghệ dựa trên việc hệ thống cần provision tài nguyên, bind workload, quản lý lifecycle hay chỉ phân phối credentials.

| Hướng | Vai trò chính | Phù hợp khi |
|---|---|---|
| Crossplane | Điều khiển tài nguyên hạ tầng ngoài cluster bằng Kubernetes API, provider và composition | Muốn quản lý hạ tầng theo mô hình declarative và reconciliation |
| Service Binding Specification for Kubernetes | Chuẩn hóa cách mô tả binding giữa workload và service | Đã có service do controller/operator khác quản lý và cần cung cấp thông tin kết nối cho workload |
| Kubernetes Operator chuyên biệt | Quản lý lifecycle của một loại service bằng CRD và controller | Service có domain model riêng, cần trạng thái và reconciliation sâu |
| Controller gọi OSB broker trực tiếp | Tạo lớp tích hợp Kubernetes riêng với broker hiện có | Cần giữ OSB API nhưng không muốn phụ thuộc Service Catalog legacy |
| External Secrets Operator hoặc secret manager integration | Đồng bộ secret vào Kubernetes | Chỉ cần phân phối và xoay vòng secret; không cần provisioning service |

### 8.1. Crossplane

Crossplane mở rộng Kubernetes để quản lý tài nguyên bên ngoài thông qua provider và các đối tượng managed resource. Người dùng khai báo trạng thái mong muốn; controller reconcile tài nguyên cloud hoặc dịch vụ tương ứng.

Ưu điểm:

- Mô hình declarative gần với cách Kubernetes quản lý workload.
- Có provider và composition để chuẩn hóa nhiều loại tài nguyên.
- Có thể thể hiện trạng thái, điều kiện và quan hệ phụ thuộc trong API.
- Hỗ trợ tổ chức platform API riêng qua composition.

Giới hạn cần hiểu:

- Crossplane không phải implementation thay thế trực tiếp cho Kubernetes Service Catalog.
- Crossplane không tự động biến một OSB broker thành provider.
- Phải xác định provider có hỗ trợ backend cần dùng hay phải phát triển provider riêng.
- Mô hình ownership, import resource hiện có, secret và deletion policy cần được thiết kế.

Nếu muốn giữ broker OSB hiện có, có thể xây provider hoặc adapter phù hợp để gọi broker, nhưng đây là công việc tích hợp cần thiết kế và kiểm thử; không phải khả năng tự động có sẵn cho mọi broker.

### 8.2. Service Binding Specification for Kubernetes

Service Binding Specification tập trung vào cách liên kết thông tin kết nối từ một service với workload. Nó giúp workload nhận dữ liệu binding theo một quy ước mà controller hoặc runtime hỗ trợ.

Cần phân biệt:

- Provisioning tạo hoặc quản lý service instance.
- Binding tạo quan hệ và thông tin kết nối giữa service với workload.
- Service Binding Specification mô tả cách đưa binding data tới workload; bản thân specification không phải hệ thống provisioning database, queue hoặc cloud resource.

Do đó, có thể kết hợp Service Binding với Crossplane, operator hoặc một controller khác chịu trách nhiệm tạo service. Việc dùng Service Binding không tự thay thế endpoint provision/deprovision của OSB API.

### 8.3. Kubernetes Operator chuyên biệt

Một operator có thể cung cấp CRD riêng như ManagedDatabase, ManagedQueue hoặc ManagedCache. Controller quan sát spec, gọi provider API, cập nhật status và reconcile khi có drift.

Ví dụ CRD minh họa do một tổ chức tự định nghĩa:

~~~yaml
apiVersion: platform.example.io/v1alpha1
kind: ManagedDatabase
metadata:
  name: orders-db
  namespace: orders
spec:
  engine: postgresql
  plan: standard
  storageGB: 100
  backup:
    enabled: true
status:
  conditions:
    - type: Ready
      status: "False"
      reason: Provisioning
~~~

Đây là API ví dụ, không phải resource Kubernetes có sẵn. Một operator tốt cần định nghĩa rõ:

- Schema và validation của spec.
- Conditions và observed generation trong status.
- Quyền controller được phép sử dụng.
- Reconciliation, retry và idempotency.
- Finalizer và deletion policy.
- Cách cấp, rotate và revoke credentials.
- Import hoặc adopt resource đã tồn tại.

### 8.4. Controller gọi OSB broker trực tiếp

Nếu tổ chức có nhiều broker OSB đang vận hành ổn định, có thể xây một controller Kubernetes nhỏ để ánh xạ custom resource sang OSB API. Cách này giữ lại broker và backend adapter hiện có mà không phụ thuộc API của Service Catalog legacy.

Controller cần tự chịu trách nhiệm cho:

- Authentication và TLS khi gọi broker.
- Mapping resource identity và tenant.
- Provision, update, bind, unbind và deprovision.
- Polling last_operation cho thao tác async được OSB hỗ trợ.
- Retry, backoff, idempotency và reconciliation.
- Lưu operation token, external resource reference và trạng thái.
- Quản lý Secret và thu hồi credentials.

Không được tạo controller chỉ gửi HTTP request mà không lưu trạng thái. Controller phải chịu được restart, duplicate event và backend timeout giống bất kỳ hệ thống điều phối phân tán nào.

## 9. Chọn hướng thay thế theo nhu cầu

Hãy bắt đầu bằng việc xác định điều hệ thống thực sự cần:

| Nhu cầu | Hướng phù hợp để đánh giá |
|---|---|
| Quản lý cloud database, network, storage theo declarative API | Crossplane hoặc operator/provider chuyên biệt |
| Cấp credentials cho workload từ service đã tồn tại | Service Binding Specification kết hợp secret manager/controller |
| Quản lý một sản phẩm database cụ thể trong Kubernetes | Operator của sản phẩm hoặc operator do tổ chức phát triển |
| Giữ broker OSB hiện có và tích hợp Kubernetes | Controller/adapter OSB riêng |
| Broker chủ yếu phục vụ Cloud Foundry | Tiếp tục dùng OSB API với Cloud Foundry; không cần đưa Service Catalog legacy vào đường đi |
| Chỉ đồng bộ secret từ hệ thống ngoài | External Secrets Operator hoặc tích hợp secret manager |

Các hướng này có thể kết hợp. Ví dụ Crossplane quản lý database, Service Binding đưa thông tin kết nối vào workload, còn secret manager quản lý vòng đời credentials. Không cần ép một công nghệ thực hiện mọi chức năng.

## 10. Lập kế hoạch migration khỏi Service Catalog legacy

Migration cần bảo toàn trạng thái backend và quyền truy cập. Không bắt đầu bằng việc gỡ controller hoặc xóa API extension.

### Bước 1: Kiểm kê

Lập danh sách:

- ServiceBroker và ClusterServiceBroker.
- ServiceClass, ServicePlan và catalog ID.
- ServiceInstance, namespace và tenant owner.
- ServiceBinding và consumer workload.
- Secret liên quan và quyền backend.
- Broker URL, credentials, API version.
- Operation đang chạy và tài nguyên backend thực tế.

### Bước 2: Xác định nguồn sự thật

Đối chiếu object Kubernetes với broker database và backend provider. Một object có trạng thái READY không đủ chứng minh tài nguyên vẫn tồn tại và credentials còn hợp lệ.

Ghi lại external resource ID, backend owner tag, plan, parameters và binding principal. Xử lý các trường hợp object mồ côi hoặc trạng thái không nhất quán trước khi migration.

### Bước 3: Thiết kế mô hình đích

Chọn Crossplane, Service Binding, operator riêng hoặc OSB adapter theo nhu cầu. Xác định resource identity, tenant boundary, lifecycle, status conditions, secret delivery và deletion policy.

Giữ mapping rõ ràng từ ID cũ sang resource mới. Tránh tạo một resource backend mới chỉ vì tên object Kubernetes đã thay đổi.

### Bước 4: Thử nghiệm import/adoption

Trên môi trường staging:

- Tạo resource target tham chiếu tới backend resource hiện có.
- Xác minh controller nhận diện resource mà không provision trùng.
- Kiểm tra owner, plan, parameters và trạng thái.
- Kiểm thử binding và workload access.
- Kiểm thử delete policy để chắc chắn resource không bị xóa ngoài ý muốn.

Không phải provider hoặc operator nào cũng hỗ trợ import/adoption. Nếu không hỗ trợ, cần thiết kế quy trình chuyển giao ownership hoặc migration riêng.

### Bước 5: Chuyển đổi theo nhóm

Chuyển từng nhóm service hoặc namespace. Với mỗi nhóm:

1. Tạm dừng thay đổi lifecycle mới trong thời gian cutover đã thống nhất.
2. Đối chiếu trạng thái instance và binding.
3. Chuyển quyền điều khiển sang controller mới.
4. Xác minh workload tiếp tục truy cập bằng credentials hợp lệ.
5. Thử update, unbind và deprovision trên resource thử nghiệm.
6. Theo dõi drift, retry và lỗi trong giai đoạn ổn định.

Không để hai controller cùng sở hữu và reconcile một resource backend nếu chưa có cơ chế ownership rõ ràng.

### Bước 6: Thu hồi và gỡ thành phần legacy

Chỉ sau khi xác nhận không còn resource do Service Catalog quản lý:

- Xử lý broker registration cũ.
- Thu hồi credentials không còn dùng.
- Sao lưu lần cuối.
- Gỡ controller và API extension theo hướng dẫn của phiên bản cài đặt.
- Kiểm tra API discovery và workload không còn phụ thuộc.
- Theo dõi backend resources và secret sau khi gỡ.

Xóa Service Catalog API trước khi migration xong có thể khiến người vận hành mất khả năng quan sát hoặc điều phối các instance còn tồn tại.

## 11. Bảo mật khi duy trì hoặc di chuyển hệ thống

Service Catalog legacy có thể lưu broker credentials, binding metadata và Secret trong cluster. Cần đánh giá toàn bộ đường đi của dữ liệu nhạy cảm.

Nguyên tắc:

- Giới hạn RBAC cho broker registration và service instance.
- Hạn chế quyền đọc Secret ở namespace không liên quan.
- Dùng TLS giữa controller và broker.
- Rotate broker credentials nếu có nghi ngờ lộ hoặc không còn quản lý được.
- Revoke backend principal khi binding bị thu hồi.
- Không copy secret bản rõ qua log, manifest hoặc file migration.
- Gắn backend resource với tenant và owner đã xác minh.
- Kiểm tra finalizer và deletion policy trước khi xóa object.
- Ghi audit cho việc thay đổi broker, plan, instance và binding.

Khi di chuyển binding, tránh chỉ sao chép Secret cũ sang namespace hoặc controller mới rồi coi migration đã hoàn tất. Cần xác minh principal backend, quyền thực tế, thời hạn credentials và khả năng rotate/revoke.

## 12. Kiểm thử hệ thống legacy và giải pháp thay thế

Bộ kiểm thử cần bao phủ cả Kubernetes API và backend service.

| Kịch bản | Kết quả mong đợi |
|---|---|
| Controller không truy cập được broker | Object không bị đánh dấu Ready giả; có trạng thái lỗi và retry |
| Catalog thay đổi ID ngoài dự kiến | Phát hiện mismatch; không tự tạo duplicate offering |
| Provision timeout sau khi backend tạo resource | Reconcile/lookup trước khi retry |
| ServiceInstance bị xóa khi backend còn tồn tại | Phát hiện orphan và áp dụng deletion policy |
| Binding bị xóa | Backend credentials được revoke trước khi hoàn tất |
| Secret bị xóa nhưng credential cũ còn hiệu lực | Phát hiện và revoke principal backend |
| Controller restart khi operation đang chạy | Khôi phục từ trạng thái bền vững |
| Hai controller cùng xử lý một resource | Ownership/lease ngăn side effect trùng |
| Migration adopt resource hiện hữu | Không provision resource mới |
| Gỡ API extension | Workload và controller đích không còn phụ thuộc API legacy |

Đối với giải pháp mới, cần kiểm thử thêm:

- Schema validation và status conditions.
- Reconciliation sau drift.
- RBAC và namespace isolation.
- Secret rotation.
- Import/adoption và deletion policy.
- Upgrade/rollback controller.
- Khả năng phục hồi khi provider API hoặc broker tạm thời không sẵn sàng.

## 13. Những lỗi thường gặp khi tiếp tục dùng Service Catalog cũ

- **Coi Service Catalog là thành phần Kubernetes core:** dẫn đến nâng cấp cluster mà không kiểm tra API extension.
- **Nhầm dự án legacy với OSB API:** ngừng dùng Service Catalog không bắt buộc phải bỏ mọi broker OSB.
- **Gỡ controller trước khi kiểm kê:** mất cơ chế quản lý instance và binding đang hoạt động.
- **Chỉ backup YAML:** bỏ sót Secret, broker database và backend reference.
- **Tin status Ready tuyệt đối:** không đối chiếu trạng thái thực tế của provider.
- **Xóa Secret thay cho revoke:** credentials cũ vẫn có thể truy cập backend.
- **Dùng ClusterServiceBroker thiếu RBAC:** mở rộng phạm vi tin cậy quá mức.
- **Để hai controller cùng sở hữu resource:** gây provision, update hoặc delete cạnh tranh.
- **Chọn Crossplane như một drop-in replacement:** bỏ qua khác biệt về API, provider, ownership và migration.
- **Dùng Service Binding để thay provisioning:** nhầm cơ chế phân phối binding data với cơ chế tạo service.
- **Không kiểm thử import/adoption:** có thể tạo tài nguyên trùng hoặc xóa nhầm tài nguyên hiện hữu.

## 14. Quy trình đánh giá và chuyển đổi

Khi tiếp nhận một cluster đang dùng Kubernetes Service Catalog, hãy thực hiện theo trình tự:

1. Xác định phiên bản Service Catalog, API group, APIService và controller đang chạy.
2. Kiểm kê broker registration, class, plan, instance, binding và Secret.
3. Đối chiếu object với operation database và backend resources.
4. Xác định workload nào còn phụ thuộc vào binding hiện tại.
5. Đánh giá compatibility, security patch và khả năng nâng cấp Kubernetes.
6. Chọn giải pháp đích theo nhu cầu provisioning, binding và secret delivery.
7. Thử import/adoption trên staging với resource hiện hữu.
8. Xây migration mapping và kế hoạch rollback.
9. Chuyển từng nhóm workload, kiểm tra access và lifecycle.
10. Thu hồi credentials và gỡ Service Catalog chỉ khi không còn dependency.
11. Tiếp tục theo dõi orphan resource, drift và secret sau migration.

## Kết luận

Kubernetes Service Catalog là một lớp tích hợp OSB API dành cho Kubernetes đã trở thành công nghệ legacy và không còn được phát triển tích cực. Hệ thống cũ có thể tiếp tục chạy trong môi trường tương thích, nhưng việc duy trì lâu dài tạo rủi ro về bản vá bảo mật, API aggregation, dependency, controller reconciliation và khả năng nâng cấp Kubernetes.

Khi vận hành hoặc migration, cần kiểm kê ServiceBroker, ServiceClass, ServicePlan, ServiceInstance, ServiceBinding, Secret và backend resource trước khi thay đổi. Crossplane phù hợp với provisioning hạ tầng theo mô hình declarative; Service Binding Specification tập trung vào việc đưa binding data tới workload; operator chuyên biệt hoặc controller gọi OSB trực tiếp có thể đáp ứng các lifecycle riêng. Các lựa chọn này không phải drop-in replacement của Service Catalog. Hãy chọn theo chức năng cần giữ, bảo toàn resource identity và quyền truy cập, thử adoption trên staging rồi mới chuyển đổi và gỡ thành phần legacy.
