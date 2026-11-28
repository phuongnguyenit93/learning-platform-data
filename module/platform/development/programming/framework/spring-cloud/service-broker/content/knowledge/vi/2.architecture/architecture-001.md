# Kiến trúc nền tảng – broker – hệ thống cung cấp tài nguyên

## Bối cảnh và mục tiêu

Trong hệ sinh thái Spring Cloud, một service broker là lớp trung gian công bố các dịch vụ có thể được nền tảng cấp phát theo yêu cầu. Nền tảng như Cloud Foundry hoặc một bộ điều khiển tích hợp Open Service Broker API (OSB API) gọi broker để khám phá dịch vụ, chọn gói dịch vụ, tạo một service instance, tạo binding cho ứng dụng, thay đổi cấu hình hoặc thu hồi tài nguyên khi người dùng không còn cần chúng.

Broker không nhất thiết tự lưu trữ cơ sở dữ liệu, hàng đợi hay cụm Kubernetes. Nó cung cấp một hợp đồng thống nhất để nền tảng yêu cầu những tài nguyên đó, sau đó điều phối các hệ thống phía sau như PostgreSQL, Redis, Kafka, object storage, API cloud hoặc Kubernetes. Nhờ vậy, người dùng làm việc với một thao tác cấp phát nhất quán thay vì phải biết cách tạo, cấu hình, cấp quyền và dọn dẹp từng loại tài nguyên ở từng nhà cung cấp.

Bài học này tập trung vào kiến trúc nền tảng – broker – hệ thống cung cấp tài nguyên trong module Spring Cloud Service Broker. Các mục tiêu chính là:

- Hiểu ranh giới trách nhiệm giữa nền tảng, broker và hệ thống cung cấp tài nguyên.
- Hiểu catalog, service definition và service plan được công bố qua OSB API.
- Theo dõi vòng đời provision, update, bind, unbind và deprovision.
- Thiết kế trạng thái bền vững, xử lý bất đồng bộ, retry và idempotency.
- Tổ chức ứng dụng Spring Cloud Service Broker thành các lớp dễ kiểm thử và thay thế backend.
- Tích hợp broker với Cloud Foundry và các mô hình tích hợp trên Kubernetes.
- Bảo vệ thông tin tenant, credentials và quyền truy cập vào tài nguyên.

## 1. Kiến trúc tổng thể

Một hệ thống service broker thường có ba vùng chính:

1. **Nền tảng (platform):** nơi người dùng hoặc ứng dụng yêu cầu dịch vụ. Nền tảng quản lý danh tính, tổ chức, không gian triển khai, ứng dụng và vòng đời yêu cầu ở cấp nền tảng.
2. **Service broker:** công bố catalog và thực thi hợp đồng OSB API. Broker xác thực yêu cầu, kiểm tra plan, lưu trạng thái, điều phối công việc và trả kết quả cho nền tảng.
3. **Hệ thống cung cấp tài nguyên (provisioning backend):** nơi tài nguyên thực sự được tạo và vận hành, chẳng hạn một cụm cơ sở dữ liệu, namespace, queue, bucket hoặc tài khoản dịch vụ.

~~~mermaid
flowchart LR
    U[Người dùng / Ứng dụng] --> P[Nền tảng]
    P -->|HTTPS + OSB API| A[Spring Cloud Service Broker]
    subgraph Broker["Vùng trách nhiệm của broker"]
        A --> S[Xác thực và kiểm tra yêu cầu]
        S --> C[Catalog và Plan]
        S --> L[Application Service / Lifecycle]
        L --> R[(Instance, Binding, Operation)]
        L --> O[Outbox / Hàng đợi công việc]
        O --> W[Worker / Reconciler]
    end
    W --> D[Backend Adapter]
    D --> B[(Database / Cache / Queue / Storage / Kubernetes)]
    P -->|GET last_operation| A
    A --> M[Logs, Metrics, Tracing, Audit]
    W --> M
~~~

Luồng dữ liệu chính bắt đầu từ nền tảng. Nền tảng gửi một yêu cầu HTTP đến endpoint OSB API. Lớp giao tiếp của broker kiểm tra phiên bản API, thông tin xác thực và dữ liệu đầu vào. Sau đó, lớp ứng dụng áp dụng quy tắc nghiệp vụ, ghi nhận trạng thái và gọi adapter tương ứng. Nếu thao tác mất thời gian, broker tạo một operation bền vững và giao việc cho worker. Nền tảng có thể truy vấn trạng thái operation cho đến khi thao tác hoàn tất.

Cần phân biệt hai loại trạng thái:

- **Trạng thái nghiệp vụ:** trạng thái hiện tại của service instance hoặc binding, ví dụ đang cấp phát, sẵn sàng, đang cập nhật hoặc đang thu hồi.
- **Trạng thái operation:** kết quả của một lần thực hiện cụ thể, ví dụ đang chạy, thành công hoặc thất bại.

Một instance có thể trải qua nhiều operation trong suốt vòng đời. Vì vậy, không nên chỉ dùng một cột trạng thái duy nhất để đại diện đồng thời cho instance và mọi yêu cầu đã tác động lên nó.

## 2. Ranh giới trách nhiệm và các khái niệm cốt lõi

### 2.1. Nền tảng

Nền tảng cung cấp giao diện cho người dùng, quản lý vòng đời ứng dụng và gọi broker theo hợp đồng OSB API. Nền tảng thường chịu trách nhiệm:

- Hiển thị các dịch vụ và plan mà broker công bố.
- Gắn yêu cầu với tổ chức, không gian hoặc tenant của người dùng.
- Sinh và quản lý định danh instance, binding.
- Gọi provision, update, bind, unbind và deprovision.
- Theo dõi thao tác bất đồng bộ qua endpoint last operation.
- Chuyển credentials trả về từ thao tác bind đến ứng dụng theo cơ chế của nền tảng.

Nền tảng không nên phải biết backend đang dùng lệnh SQL nào, API cloud nào hay cấu trúc tài nguyên Kubernetes ra sao.

### 2.2. Service broker

Broker chịu trách nhiệm thực hiện hợp đồng mà nền tảng gọi. Các trách nhiệm điển hình gồm:

- Công bố catalog và các plan hợp lệ.
- Xác thực request và kiểm tra quyền trên tenant hoặc context.
- Kiểm tra service ID, plan ID, parameters và khả năng chuyển đổi plan.
- Lưu định danh và trạng thái service instance, binding, operation.
- Điều phối thao tác đến backend và xử lý kết quả.
- Cung cấp endpoint truy vấn trạng thái khi thao tác bất đồng bộ.
- Thu hồi quyền truy cập và dọn dẹp tài nguyên khi được yêu cầu.
- Ghi audit và phát metric để vận hành hệ thống.

Broker là nơi áp dụng chính sách của sản phẩm dịch vụ. Ví dụ, một plan có thể giới hạn dung lượng, số kết nối, vùng triển khai, chính sách sao lưu hoặc thời gian lưu dữ liệu. Các chính sách đó phải được kiểm tra trước khi broker gọi backend.

### 2.3. Hệ thống cung cấp tài nguyên

Backend thực hiện thao tác kỹ thuật thực tế. Ví dụ:

- Tạo database, schema hoặc user trên PostgreSQL.
- Tạo Redis instance hoặc cấp một database index.
- Tạo topic, queue và quyền truy cập trên hệ thống messaging.
- Tạo bucket, policy và access key trên object storage.
- Tạo namespace, Secret, Deployment hoặc custom resource trong Kubernetes.
- Gọi API của nhà cung cấp cloud để tạo tài nguyên được quản lý.

Broker nên giao tiếp với backend qua adapter. Adapter chuyển lệnh nghiệp vụ của broker thành thao tác đặc thù của nhà cung cấp, đồng thời chuẩn hóa lỗi và kết quả. Cách tổ chức này giúp thay backend mà không làm thay đổi hợp đồng OSB API.

### 2.4. Service, plan, instance và binding

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Service definition | Một loại dịch vụ mà broker cung cấp | PostgreSQL Database |
| Service plan | Một cấu hình hoặc cấp dịch vụ của service | Dev, Standard, High Availability |
| Service instance | Một tài nguyên cụ thể được cấp phát từ service và plan | Database của ứng dụng billing |
| Service binding | Quan hệ cấp quyền sử dụng instance cho một consumer | Credentials cho ứng dụng billing-api |
| Operation | Một lần thực hiện hành động trên instance hoặc binding | Provision database đang chạy |
| Backend resource | Tài nguyên thực tế ở hệ thống phía sau | Database và role trong PostgreSQL |

Một service có thể có nhiều plan. Một plan mô tả cách cấp phát và giới hạn của một loại tài nguyên. Service instance là kết quả của một lần provision theo service và plan cụ thể. Một instance có thể có nhiều binding nếu dịch vụ cho phép nhiều consumer cùng sử dụng.

Không nên đồng nhất service instance với binding. Instance đại diện cho tài nguyên được quản lý; binding đại diện cho quyền hoặc thông tin kết nối của một consumer đến tài nguyên đó. Khi một ứng dụng bị xóa, broker có thể cần thu hồi binding của ứng dụng mà vẫn giữ nguyên instance để ứng dụng khác tiếp tục sử dụng.

## 3. Hợp đồng Open Service Broker API

OSB API chuẩn hóa giao tiếp giữa platform và broker qua HTTP. Các endpoint thường dùng gồm:

| Hành động | HTTP endpoint | Mục đích |
|---|---|---|
| Lấy catalog | GET /v2/catalog | Đọc danh sách service và plan |
| Provision | PUT /v2/service_instances/{instance_id} | Tạo service instance |
| Update | PATCH /v2/service_instances/{instance_id} | Thay đổi cấu hình hoặc plan |
| Deprovision | DELETE /v2/service_instances/{instance_id} | Thu hồi service instance |
| Bind | PUT /v2/service_instances/{instance_id}/service_bindings/{binding_id} | Cấp quyền cho consumer |
| Unbind | DELETE /v2/service_instances/{instance_id}/service_bindings/{binding_id} | Thu hồi binding |
| Kiểm tra operation | GET /v2/service_instances/{instance_id}/last_operation | Lấy trạng thái operation của instance |

Các endpoint truy vấn instance hoặc binding chỉ nên được công bố khi broker thực sự hỗ trợ capability tương ứng. Chi tiết request và response phải tuân theo phiên bản OSB API mà broker triển khai.

Request OSB API thường mang header phiên bản API do broker hỗ trợ, ví dụ header X-Broker-API-Version. Broker cần kiểm tra phiên bản này và xử lý các trường hợp không tương thích theo hợp đồng. Broker cũng cần cơ chế xác thực request, thường thông qua thông tin xác thực mà nền tảng được cấp khi đăng ký broker.

### 3.1. Provision: cấp phát service instance

Nền tảng gửi PUT đến endpoint service instance. ID instance thường do nền tảng tạo và được dùng ổn định cho các lần retry của cùng yêu cầu.

Ví dụ request:

~~~http
PUT /v2/service_instances/inst-7f82?accepts_incomplete=true
Authorization: Basic <broker-credentials>
X-Broker-API-Version: <supported-version>
Content-Type: application/json
~~~

~~~json
{
  "service_id": "8b5d3d7a-1f10-4b2c-9e70-7f4e8d0a1001",
  "plan_id": "2b10d3a0-40a0-4b19-a0f4-12a9b8000002",
  "organization_guid": "org-123",
  "space_guid": "space-456",
  "parameters": {
    "storage_gb": 50,
    "backup_enabled": true
  },
  "context": {
    "platform": "cloud-foundry"
  }
}
~~~

Broker xử lý request theo các bước:

1. Xác thực nền tảng và kiểm tra quyền gọi broker.
2. Kiểm tra service ID và plan ID có tồn tại trong catalog.
3. Kiểm tra plan thuộc đúng service, parameters hợp lệ và quota của tenant còn đủ.
4. Kiểm tra instance ID đã tồn tại hay chưa.
5. Ghi nhận instance và operation vào kho dữ liệu.
6. Thực hiện hoặc xếp hàng công việc tạo tài nguyên backend.
7. Trả response đồng bộ nếu tài nguyên đã sẵn sàng, hoặc trả response bất đồng bộ nếu công việc tiếp tục ở nền.

Nếu provision hoàn tất ngay, broker trả response thành công theo OSB API. Nếu cần chạy bất đồng bộ và request cho phép bằng accepts_incomplete=true, broker có thể trả HTTP 202 Accepted cùng operation token:

~~~json
{
  "operation": "provision-op-001",
  "dashboard_url": "https://broker.example.com/instances/inst-7f82"
}
~~~

Operation token là định danh để nền tảng theo dõi công việc. Token này nên là giá trị opaque; nền tảng không cần biết cách broker lưu hoặc xử lý operation bên trong.

Nếu broker cần xử lý bất đồng bộ nhưng request không cho phép accepts_incomplete, broker phải trả lỗi theo hợp đồng OSB API thay vì giả vờ rằng tài nguyên đã sẵn sàng. Điều này giúp nền tảng biết cần thay đổi cách gửi yêu cầu hoặc thông báo cho người dùng.

### 3.2. Theo dõi thao tác bất đồng bộ

Khi provision, update hoặc deprovision chưa hoàn tất, nền tảng truy vấn endpoint last operation. Request thường mang service_id, plan_id và operation token tương ứng.

Ví dụ:

~~~http
GET /v2/service_instances/inst-7f82/last_operation?service_id=<service-id>&plan_id=<plan-id>&operation=provision-op-001
Authorization: Basic <broker-credentials>
X-Broker-API-Version: <supported-version>
~~~

Response có thể cho biết:

~~~json
{
  "state": "in progress",
  "description": "Dang tao database va cau hinh backup"
}
~~~

Khi hoàn tất:

~~~json
{
  "state": "succeeded",
  "description": "Database da san sang"
}
~~~

Các trạng thái operation thường được biểu diễn bằng in progress, succeeded hoặc failed. Description nên ngắn gọn, hữu ích cho vận hành và không chứa credentials, token bí mật hoặc chi tiết nội bộ nhạy cảm.

Broker phải lưu trạng thái operation bền vững. Nếu tiến trình ứng dụng khởi động lại giữa lúc backend đang tạo tài nguyên, nền tảng vẫn phải truy vấn được trạng thái gần nhất. Một operation không thể chỉ tồn tại trong biến bộ nhớ của một instance Spring Boot.

### 3.3. Update: cập nhật instance

Nền tảng sử dụng PATCH để thay đổi plan hoặc parameters của instance. Request có thể chứa plan ID mới, parameters mới, previous_values và context.

Broker cần xác định rõ những thay đổi nào được hỗ trợ. Ví dụ:

- Tăng dung lượng lưu trữ có thể được hỗ trợ tại chỗ.
- Giảm dung lượng có thể không được hỗ trợ nếu backend không thể thu nhỏ an toàn.
- Chuyển từ plan development sang production có thể yêu cầu bật backup hoặc tạo replica.
- Thay đổi region có thể đòi hỏi di chuyển dữ liệu, không thể xử lý như một phép cập nhật thuộc tính đơn giản.

Quy trình update nên kiểm tra trạng thái instance hiện tại, quyền của tenant, khả năng cập nhật plan và tính tương thích giữa cấu hình cũ với cấu hình mới. Nếu thay đổi cần nhiều bước, broker tạo operation riêng và thực hiện theo workflow có khả năng retry hoặc bù trừ.

Một thao tác update thất bại không nên khiến database record của broker ghi nhận cấu hình mới trong khi backend vẫn giữ cấu hình cũ. Broker cần lưu cấu hình mong muốn, cấu hình đã áp dụng và trạng thái chuyển đổi đủ rõ để có thể tiếp tục hoặc phục hồi.

### 3.4. Deprovision: thu hồi instance

Nền tảng gửi DELETE để yêu cầu broker thu hồi tài nguyên. Broker cần xác minh service ID, plan ID và instance tương ứng trước khi gọi backend.

Các bước thường gồm:

1. Kiểm tra instance có tồn tại và có thuộc tenant tương ứng hay không.
2. Kiểm tra binding còn hoạt động và áp dụng chính sách xử lý phụ thuộc.
3. Chuyển instance sang trạng thái đang thu hồi.
4. Thu hồi hoặc vô hiệu hóa tài khoản, quyền truy cập và tài nguyên backend.
5. Xác nhận tài nguyên đã được xóa hoặc đã được đưa vào trạng thái không còn khả năng sử dụng.
6. Lưu kết quả và kết thúc operation.

Nền tảng thường thực hiện unbind trước khi deprovision. Tuy nhiên, broker vẫn phải bảo vệ dữ liệu và tài nguyên trước trường hợp nhận yêu cầu không theo thứ tự mong đợi. Tùy chính sách dịch vụ, broker có thể từ chối deprovision khi còn binding hoặc thực hiện quy trình thu hồi phụ thuộc đã được định nghĩa.

Deprovision phải có tính idempotent. Nếu tài nguyên đã được xóa và nền tảng gửi lại yêu cầu do timeout, broker cần trả kết quả phù hợp với trạng thái đã hoàn tất thay vì cố tạo lại hoặc báo lỗi không nhất quán.

### 3.5. Bind và unbind

Bind tạo quan hệ giữa service instance và một consumer, thường là ứng dụng. Broker có thể tạo username/password, cấp role, tạo access key, thiết lập network policy hoặc cấp một bộ thông tin kết nối.

Ví dụ request bind:

~~~http
PUT /v2/service_instances/inst-7f82/service_bindings/bind-2a91
Authorization: Basic <broker-credentials>
X-Broker-API-Version: <supported-version>
Content-Type: application/json
~~~

~~~json
{
  "service_id": "<service-id>",
  "plan_id": "<plan-id>",
  "app_guid": "app-789",
  "bind_resource": {
    "app_guid": "app-789"
  },
  "parameters": {
    "role": "read-write"
  },
  "context": {
    "platform": "cloud-foundry"
  }
}
~~~

Response bind có thể trả credentials:

~~~json
{
  "credentials": {
    "hostname": "db.internal.example",
    "port": 5432,
    "database": "billing",
    "username": "billing_app",
    "password": "<generated-secret>",
    "sslmode": "require"
  }
}
~~~

Nền tảng sử dụng thông tin này để cung cấp cấu hình kết nối cho ứng dụng. Trong Cloud Foundry, thông tin binding thường xuất hiện trong VCAP_SERVICES. Trong Kubernetes, adapter hoặc controller có thể lưu credentials vào Secret.

Unbind phải thu hồi quyền truy cập đã cấp. Với database, thao tác có thể xóa hoặc khóa role; với object storage, có thể thu hồi access key hoặc policy; với queue, có thể xóa principal hoặc ACL. Unbind phải an toàn khi được gửi lặp lại.

Binding thường được thiết kế để hoàn tất đồng bộ và nhanh. Nếu một tích hợp cụ thể cần workflow bất đồng bộ, cần kiểm tra phiên bản OSB API và khả năng hỗ trợ của platform trước khi thiết kế hợp đồng mở rộng. Không nên tự giả định mọi platform đều xử lý async bind giống async provision.

## 4. Catalog và service plan

Catalog là danh mục mà broker công bố cho nền tảng qua endpoint GET /v2/catalog. Đây là hợp đồng mô tả dịch vụ nào có thể được yêu cầu và các khả năng của dịch vụ đó.

Một catalog đơn giản có thể có dạng:

~~~json
{
  "services": [
    {
      "id": "8b5d3d7a-1f10-4b2c-9e70-7f4e8d0a1001",
      "name": "managed-postgresql",
      "description": "Co so du lieu PostgreSQL duoc quan ly",
      "bindable": true,
      "plan_updateable": true,
      "instances_retrievable": true,
      "bindings_retrievable": false,
      "tags": ["database", "sql", "postgresql"],
      "plans": [
        {
          "id": "2b10d3a0-40a0-4b19-a0f4-12a9b8000001",
          "name": "development",
          "description": "Moi truong phat trien",
          "free": false
        },
        {
          "id": "2b10d3a0-40a0-4b19-a0f4-12a9b8000002",
          "name": "production",
          "description": "Moi truong san xuat co sao luu",
          "free": false
        }
      ]
    }
  ]
}
~~~

Các ID trong ví dụ chỉ có mục đích minh họa. Trong hệ thống thật, service ID và plan ID phải ổn định qua các lần khởi động và triển khai. Không nên sinh ID mới mỗi lần broker trả catalog, vì nền tảng lưu các ID đó để tham chiếu đến instance đã tồn tại.

### 4.1. Service definition

Service definition mô tả sản phẩm dịch vụ ở mức tổng thể. Một số trường quan trọng:

- **id:** định danh ổn định của service.
- **name:** tên kỹ thuật mà nền tảng và người vận hành có thể nhận biết.
- **description:** mô tả mục đích của dịch vụ.
- **bindable:** cho biết service có hỗ trợ tạo binding hay không.
- **plan_updateable:** cho biết broker hỗ trợ cập nhật plan cho instance hay không.
- **instances_retrievable:** cho biết broker hỗ trợ truy vấn thông tin service instance theo khả năng của OSB API.
- **bindings_retrievable:** cho biết broker hỗ trợ truy vấn thông tin binding theo khả năng của OSB API.
- **tags:** nhãn giúp nền tảng phân loại hoặc tìm kiếm dịch vụ.
- **requires:** khai báo các khả năng đặc biệt mà service cần, nếu có.
- **metadata:** thông tin bổ sung phục vụ giao diện hoặc tích hợp.

Các capability trong catalog phải phản ánh đúng hành vi thực tế. Ví dụ, không công bố bindable nếu broker chưa thể tạo và thu hồi credentials an toàn. Không công bố plan_updateable nếu backend không có cơ chế thay đổi plan hoặc broker chưa định nghĩa được cách chuyển đổi an toàn.

### 4.2. Service plan

Plan mô tả một biến thể của service. Với dịch vụ database, các plan có thể khác nhau về:

- CPU, RAM, dung lượng lưu trữ.
- Số kết nối đồng thời.
- Số replica và khả năng chịu lỗi.
- Chính sách backup, retention và phục hồi.
- Region hoặc vùng sẵn sàng.
- Hạn mức, quota và mức dịch vụ.
- Tính năng mở rộng hoặc giám sát.

Plan cần có ID ổn định và ý nghĩa rõ ràng. Tên plan có thể hiển thị cho người dùng, còn ID là định danh kỹ thuật dùng trong API. Nếu thay đổi ý nghĩa của một plan đang được sử dụng, broker có thể làm cho instance cũ trở nên khó quản lý. Với thay đổi lớn về giới hạn hoặc hành vi, nên cân nhắc tạo plan mới thay vì âm thầm thay đổi định nghĩa cũ.

### 4.3. Parameters và schema

Parameters là dữ liệu tùy chọn mà nền tảng gửi khi provision hoặc update. Ví dụ:

~~~json
{
  "storage_gb": 50,
  "region": "ap-southeast-1",
  "backup_enabled": true,
  "maintenance_window": "SUN:02:00"
}
~~~

Broker phải kiểm tra parameters theo schema và chính sách của plan. Cần kiểm tra kiểu dữ liệu, giá trị tối thiểu/tối đa, trường bắt buộc, trường không được phép và tính tương thích với backend. Không nên chuyển nguyên một JSON tùy ý từ người dùng xuống API quản trị của cloud hoặc Kubernetes.

Schema trong catalog có thể giúp nền tảng hiển thị biểu mẫu và kiểm tra dữ liệu sớm. Tuy nhiên, broker vẫn phải xác thực lại ở phía server vì request có thể được gửi bởi client khác hoặc bị thay đổi sau khi hiển thị.

## 5. Tổ chức ứng dụng bằng Spring Cloud Service Broker

Spring Cloud Open Service Broker cung cấp lớp tích hợp để ứng dụng Spring triển khai hợp đồng OSB API. Thư viện xử lý phần giao tiếp HTTP, chuyển request thành các đối tượng nghiệp vụ và chuyển kết quả của service implementation thành response phù hợp.

Ứng dụng broker nên tách thành các lớp có trách nhiệm rõ ràng:

~~~mermaid
flowchart TB
    HTTP[OSB HTTP Endpoints]
    HTTP --> LIB[Spring Cloud Service Broker]
    LIB --> CAT[Catalog Service]
    LIB --> SIS[Service Instance Service]
    LIB --> SBS[Service Instance Binding Service]
    CAT --> CFG[Catalog Configuration]
    SIS --> APP[Application Services]
    SBS --> APP
    APP --> DOMAIN[Domain Model and Policies]
    APP --> REPO[(Repositories)]
    APP --> WF[Workflow / Operation Coordinator]
    WF --> ADAPTERS[Provisioning Adapters]
    ADAPTERS --> TARGETS[Database, Cache, Queue, Cloud, Kubernetes]
~~~

### 5.1. Catalog service

Catalog service trả về danh sách service definition và plan mà broker hỗ trợ. Catalog nên được xây dựng từ cấu hình có kiểm soát hoặc dữ liệu sản phẩm ổn định. Nếu catalog thay đổi theo môi trường, cần quản lý thay đổi đó như một thay đổi cấu hình sản phẩm.

Catalog không nên gọi API tạo tài nguyên. Nhiệm vụ của nó là mô tả những gì broker có thể cung cấp.

### 5.2. Service instance service

Service instance service xử lý các yêu cầu liên quan đến vòng đời instance, thường gồm:

- Tạo instance.
- Truy vấn instance nếu capability được công bố.
- Cập nhật instance.
- Thu hồi instance.
- Trả trạng thái operation gần nhất.

Trong Spring Cloud Service Broker, các vai trò này được thể hiện qua các abstraction như CatalogService và ServiceInstanceService. Ứng dụng triển khai logic tương ứng, còn thư viện đảm nhiệm việc kết nối logic đó với giao thức OSB API.

### 5.3. Binding service

Service instance binding service xử lý tạo và thu hồi binding. Phần này nên gọi một dịch vụ nghiệp vụ riêng để tạo credentials và áp dụng quyền truy cập. Logic tạo user, role, key hoặc ACL nên nằm trong backend adapter hoặc domain service, không nên đặt trực tiếp trong HTTP endpoint.

### 5.4. Application service và backend adapter

Application service điều phối use case. Ví dụ, ProvisionService nhận một lệnh provision đã được chuẩn hóa, kiểm tra chính sách, tạo bản ghi instance, tạo operation và phát sự kiện yêu cầu worker thực hiện công việc.

Backend adapter đóng gói cách giao tiếp với nhà cung cấp. Một interface nội bộ có thể được thiết kế như sau:

~~~java
public interface ResourceProvisioner {
    ProvisionOutcome provision(ProvisionCommand command);

    UpdateOutcome update(UpdateCommand command);

    DeprovisionOutcome deprovision(DeprovisionCommand command);

    BindingCredentials bind(BindCommand command);

    void unbind(UnbindCommand command);
}
~~~

Đây là interface minh họa cho tầng ứng dụng của dự án. Các kiểu dữ liệu và chữ ký thực tế cần được điều chỉnh theo backend, phiên bản thư viện và mô hình bất đồng bộ đang sử dụng.

Có thể có nhiều adapter cùng triển khai interface này:

- PostgreSQLProvisioner tạo database và database role.
- RedisProvisioner tạo namespace hoặc ACL user.
- KubernetesProvisioner tạo custom resource hoặc tài nguyên trong namespace.
- CloudStorageProvisioner tạo bucket và access policy.

Application service không cần biết chi tiết của từng API backend. Nó chỉ làm việc với command và outcome ở mức nghiệp vụ.

### 5.5. Minh họa điều phối provision

Đoạn mã sau mô tả ý tưởng ghi nhận request và tạo công việc bền vững. Đây là mã minh họa cho luồng nghiệp vụ, không phải một implementation hoàn chỉnh của interface thư viện:

~~~java
public ProvisionResult provision(ProvisionCommand command) {
    return transactionTemplate.execute(transaction -> {
        ServiceInstance existing =
                instanceRepository.findById(command.instanceId());

        if (existing != null) {
            if (existing.matches(command)) {
                return ProvisionResult.replay(existing.operationId());
            }
            throw new InstanceConflictException(command.instanceId());
        }

        ServiceInstance instance =
                ServiceInstance.provisioning(command);

        BrokerOperation operation =
                BrokerOperation.pendingProvision(command.instanceId());

        instanceRepository.save(instance.withOperation(operation.id()));
        operationRepository.save(operation);
        outboxRepository.save(
                OutboxEvent.provisionRequested(operation.id(), command));

        return ProvisionResult.accepted(operation.id());
    });
}
~~~

Giao dịch cơ sở dữ liệu chỉ ghi nhận trạng thái, operation và sự kiện outbox. Worker đọc sự kiện rồi gọi backend. Cách làm này giúp request HTTP không phải giữ kết nối trong suốt thời gian tạo tài nguyên và tránh mất công việc khi tiến trình ứng dụng khởi động lại.

Nếu ứng dụng sử dụng API reactive của Spring Cloud Service Broker, cần giữ đúng nguyên tắc không thực hiện lời gọi blocking kéo dài trực tiếp trên event loop. Có thể chuyển công việc sang scheduler phù hợp hoặc một worker riêng. Một thao tác tạo database mất vài phút không nên chiếm luồng xử lý HTTP trong suốt thời gian đó.

## 6. Mô hình dữ liệu và quản lý trạng thái

Broker cần một kho lưu trữ bền vững để theo dõi các đối tượng nghiệp vụ. Một mô hình quan hệ tham khảo gồm:

| Bảng | Dữ liệu chính | Mục đích |
|---|---|---|
| service_instance | instance_id, service_id, plan_id, tenant, state, backend_ref, version | Quản lý vòng đời instance |
| service_binding | binding_id, instance_id, consumer_id, state, secret_ref, version | Quản lý quyền của consumer |
| broker_operation | operation_id, target_id, operation_type, state, attempt, description | Theo dõi từng thao tác |
| idempotency_record | key, request_fingerprint, result_ref | Nhận diện request lặp |
| outbox_event | event_id, aggregate_id, event_type, payload, published_at | Phát công việc bền vững |

Không nhất thiết phải tạo đúng năm bảng trên trong mọi dự án. Điều quan trọng là lưu được trạng thái instance, binding, operation và cơ chế phát công việc có thể phục hồi.

### 6.1. Trạng thái service instance

Một state machine nội bộ đơn giản có thể là:

~~~mermaid
stateDiagram-v2
    [*] --> PROVISIONING
    PROVISIONING --> READY
    PROVISIONING --> FAILED
    READY --> UPDATING
    UPDATING --> READY
    UPDATING --> FAILED
    READY --> DEPROVISIONING
    FAILED --> DEPROVISIONING
    DEPROVISIONING --> DELETED
    DEPROVISIONING --> FAILED
~~~

Ý nghĩa các trạng thái:

- PROVISIONING: broker đã nhận yêu cầu và đang tạo tài nguyên.
- READY: tài nguyên đã được xác nhận sẵn sàng.
- UPDATING: broker đang thay đổi cấu hình hoặc plan.
- DEPROVISIONING: broker đang thu hồi tài nguyên.
- DELETED: tài nguyên đã được thu hồi.
- FAILED: thao tác gần nhất thất bại và cần xác định khả năng retry hoặc xử lý thủ công.

Trong thực tế có thể cần phân biệt FAILED_RETRYABLE và FAILED_TERMINAL, hoặc lưu trạng thái mong muốn riêng với trạng thái quan sát được từ backend. Không nên chuyển instance sang READY chỉ vì lệnh tạo tài nguyên đã được gửi đi; cần có bằng chứng backend đã hoàn tất theo tiêu chí sẵn sàng của dịch vụ.

### 6.2. Trạng thái binding

Binding có vòng đời riêng:

~~~mermaid
stateDiagram-v2
    [*] --> BINDING
    BINDING --> BOUND
    BINDING --> FAILED
    BOUND --> UNBINDING
    UNBINDING --> UNBOUND
    UNBINDING --> FAILED
~~~

Một binding chỉ được coi là BOUND sau khi broker đã tạo quyền truy cập và lưu được tham chiếu đến credentials cần trả về. Nếu tạo user thành công nhưng ghi dữ liệu binding thất bại, broker phải có cách khôi phục hoặc thu hồi user vừa tạo.

### 6.3. Operation record

Mỗi operation nên lưu tối thiểu:

- Operation ID và loại thao tác.
- Instance ID hoặc binding ID mục tiêu.
- Trạng thái hiện tại.
- Thời điểm tạo, cập nhật và hoàn tất.
- Số lần thử và thông tin lỗi đã được chuẩn hóa.
- Tham chiếu đến tài nguyên backend nếu cần.
- Request fingerprint hoặc idempotency key.
- Phiên bản dữ liệu để phát hiện cập nhật đồng thời.

Không lưu password, access token hoặc secret thô trong description và log. Nếu operation cần credentials để tiếp tục, hãy dùng secret manager hoặc cơ chế mã hóa phù hợp.

## 7. Xử lý bất đồng bộ và độ tin cậy

Provisioning thường mất nhiều thời gian hơn thời gian xử lý một HTTP request. Ví dụ, tạo một database được quản lý có thể cần tạo network, storage, database engine, user, backup policy và kiểm tra kết nối. Nếu giữ request mở đến khi mọi bước hoàn tất, broker dễ gặp timeout ở load balancer, platform hoặc client.

Với thao tác dài, mô hình bất đồng bộ thường phù hợp hơn:

~~~mermaid
sequenceDiagram
    participant P as Platform
    participant B as Broker API
    participant DB as Broker Database
    participant Q as Outbox / Queue
    participant W as Worker
    participant R as Resource Backend

    P->>B: PUT service_instances
    B->>DB: Lưu instance và operation
    B->>Q: Ghi outbox event
    B-->>P: 202 Accepted + operation
    Q->>W: Phân phối công việc
    W->>R: Tạo tài nguyên
    R-->>W: Kết quả
    W->>DB: Cập nhật instance và operation
    P->>B: GET last_operation
    B->>DB: Đọc trạng thái
    B-->>P: in progress / succeeded / failed
~~~

### 7.1. Vì sao cần operation bền vững

Một workflow có thể bị gián đoạn bởi:

- Tiến trình broker bị restart.
- Worker bị mất kết nối với queue.
- API backend timeout sau khi đã nhận lệnh.
- Mạng bị gián đoạn khi broker đang chờ kết quả.
- Nền tảng gửi lại request do không nhận được response.
- Một thao tác cần nhiều bước và chỉ một số bước đã hoàn tất.

Nếu chỉ giữ trạng thái trong bộ nhớ, broker không thể phục hồi đáng tin cậy sau các tình huống trên. Operation record, outbox và worker cho phép công việc tiếp tục sau khi tiến trình được khởi động lại.

### 7.2. Retry và backoff

Retry chỉ nên áp dụng cho lỗi có khả năng phục hồi, chẳng hạn timeout mạng, giới hạn tốc độ tạm thời hoặc backend tạm ngừng phục vụ. Lỗi dữ liệu không hợp lệ, plan không tồn tại hoặc tenant vượt quota thường không thể giải quyết bằng cách retry liên tục.

Một chiến lược retry nên có:

- Số lần thử tối đa.
- Exponential backoff kết hợp jitter.
- Phân loại lỗi retryable và terminal.
- Timeout cho từng lời gọi backend.
- Dead-letter queue hoặc trạng thái cần can thiệp khi vượt giới hạn.
- Audit về số lần thử và nguyên nhân.

Trước khi retry một lời gọi backend bị timeout, broker cần xác định liệu backend đã thực hiện thao tác hay chưa. Timeout không chứng minh thao tác thất bại. Nếu gọi tạo tài nguyên lần nữa mà không kiểm tra, broker có thể tạo ra tài nguyên trùng lặp.

### 7.3. Reconciliation

Reconciliation là quá trình so sánh trạng thái mong muốn trong broker với trạng thái thực tế của backend. Worker hoặc controller có thể định kỳ kiểm tra:

- Instance đang PROVISIONING nhưng backend đã có tài nguyên.
- Instance READY nhưng backend resource không còn tồn tại.
- Operation bị treo quá thời gian cho phép.
- Binding đã bị thu hồi ở backend nhưng broker chưa cập nhật.
- Một tài nguyên được tạo thành công nhưng broker chưa lưu được backend reference.

Reconciliation giúp hệ thống tự phục hồi khỏi những lỗi xảy ra giữa hai hệ thống mà không có giao dịch phân tán chung.

## 8. Idempotency và xử lý request lặp

Nền tảng có thể gửi lại cùng một request khi response bị mất hoặc timeout. Broker phải đảm bảo việc gửi lặp không tạo ra nhiều tài nguyên hoặc nhiều credentials ngoài ý muốn.

Idempotency có nghĩa là cùng một yêu cầu nghiệp vụ được xử lý nhiều lần vẫn dẫn đến một kết quả nhất quán. Trong OSB API, các định danh instance và binding do platform cung cấp là cơ sở quan trọng để broker nhận diện yêu cầu lặp.

Ví dụ, nền tảng gửi hai lần PUT provision với cùng instance ID:

- Nếu instance chưa tồn tại, broker tạo một instance và một operation.
- Nếu instance đã tồn tại với cùng service, plan và request có ý nghĩa tương đương, broker trả kết quả phù hợp với operation hiện tại hoặc đã hoàn tất.
- Nếu instance ID đã thuộc về một yêu cầu có service, plan hoặc parameters xung đột, broker trả lỗi conflict theo hợp đồng.

Một số kỹ thuật thường dùng:

1. **Unique constraint:** đặt khóa duy nhất trên instance ID và binding ID để database ngăn bản ghi trùng.
2. **Request fingerprint:** chuẩn hóa các trường quan trọng rồi tạo hash để nhận diện request giống hoặc khác nhau.
3. **Idempotency key:** lưu khóa và kết quả của một lần xử lý để request lặp có thể nhận lại kết quả cũ.
4. **Backend resource naming:** đặt tên tài nguyên backend theo định danh ổn định hoặc gắn tag chứa instance ID.
5. **Optimistic locking:** dùng version để tránh hai worker cập nhật cùng một instance mà không biết thay đổi của nhau.
6. **Distributed lock hoặc lease:** dùng khi cần bảo đảm chỉ một worker điều phối một instance tại một thời điểm.

Không thể dựa vào một khóa trong database để bảo đảm exactly-once trên nhiều hệ thống độc lập. Một tình huống điển hình là backend đã tạo database thành công nhưng broker mất kết nối trước khi lưu kết quả. Lần retry tiếp theo phải tìm được database đã tạo dựa trên instance ID hoặc metadata ổn định, sau đó tiếp tục cập nhật trạng thái thay vì tạo database thứ hai.

Một nguyên tắc hữu ích là thiết kế hệ thống theo hướng at-least-once delivery kết hợp với handler idempotent. Queue có thể phân phối một sự kiện nhiều lần; worker vẫn phải bảo đảm cùng một sự kiện không tạo ra tác động phụ lặp lại.

## 9. Bảo mật và cô lập tenant

Broker nằm giữa nền tảng và hệ thống quản trị tài nguyên nên có quyền truy cập đáng kể. Một lỗi xác thực hoặc kiểm tra tenant có thể khiến ứng dụng này truy cập dữ liệu của ứng dụng khác.

### 9.1. Xác thực giao tiếp

- Chỉ cho phép giao tiếp qua TLS.
- Cấp credentials riêng cho từng platform hoặc môi trường.
- Lưu credentials trong secret manager, không đưa vào source code.
- Có quy trình xoay vòng và thu hồi credentials.
- Giới hạn quyền truy cập của tài khoản broker ở mức cần thiết.
- Bảo vệ endpoint quản trị và endpoint nội bộ khỏi truy cập công khai không cần thiết.

Header X-Broker-API-Originating-Identity có thể cung cấp thông tin về người dùng hoặc nguồn gốc request để phục vụ audit. Broker cần hiểu định dạng và nguồn phát của header này, đồng thời không dùng một giá trị header đơn lẻ làm cơ chế xác thực thay thế cho credentials và kiểm tra quyền của platform.

### 9.2. Cô lập tenant

Context thường mang thông tin về platform, organization, space hoặc namespace. Broker nên chuẩn hóa context thành một mô hình tenant nội bộ và áp dụng kiểm tra quyền ở mọi thao tác.

Ví dụ, khi nhận yêu cầu DELETE instance, broker phải xác minh instance thuộc tenant được phép thao tác. Không được chỉ kiểm tra instance ID có tồn tại rồi gọi backend xóa tài nguyên.

Các nguyên tắc quan trọng:

- Gắn tenant ID vào bản ghi instance và binding.
- Kiểm tra quyền trước khi đọc, cập nhật hoặc thu hồi tài nguyên.
- Không cho parameters ghi đè tenant identity do platform cung cấp.
- Phân tách credentials backend giữa tenant nếu mô hình bảo mật yêu cầu.
- Giới hạn quota và rate limit theo tenant.
- Ghi audit cho thao tác tạo, cấp quyền, thay đổi và thu hồi.

### 9.3. Quản lý credentials

Credentials trả về khi bind là dữ liệu nhạy cảm. Broker cần:

- Sinh secret bằng nguồn ngẫu nhiên mật mã phù hợp.
- Lưu secret trong secret manager hoặc lưu dữ liệu đã mã hóa khi cần truy xuất lại.
- Hạn chế quyền đọc secret và ghi nhận audit khi truy xuất.
- Không ghi secret vào log, trace, exception hoặc metric label.
- Có chính sách rotation và thu hồi.
- Không trả credentials của binding khác khi nhận request lặp hoặc request có ID xung đột.

Nếu platform yêu cầu truy xuất lại binding, broker phải thiết kế khả năng lấy credentials phù hợp với capability đã công bố. Nếu không cần truy xuất lại, có thể lưu tham chiếu secret thay vì lưu bản rõ trong bảng binding.

### 9.4. Kiểm tra parameters và chống lạm dụng

Parameters không được xem là dữ liệu đáng tin cậy. Broker cần kiểm tra schema, giới hạn kích thước request, whitelist trường được phép và validate mọi giá trị trước khi gọi backend.

Nếu broker gọi một URL do người dùng cung cấp, cần phòng chống SSRF bằng cách kiểm tra scheme, host, địa chỉ IP, DNS resolution và giới hạn mạng đích. Nếu broker tạo tài nguyên Kubernetes, cần tránh ghép trực tiếp dữ liệu đầu vào vào tên resource, label, annotation hoặc manifest mà không chuẩn hóa.

## 10. Tích hợp với Cloud Foundry và Kubernetes

OSB API là hợp đồng giao tiếp chung, nhưng mỗi nền tảng có cách quản lý người dùng, context và vòng đời riêng. Broker nên giữ phần nghiệp vụ độc lập với platform, sau đó dùng adapter để chuyển context và các đặc tính nền tảng thành mô hình nội bộ.

### 10.1. Cloud Foundry

Cloud Foundry có mô hình tích hợp service broker trực tiếp. Quản trị viên đăng ký broker với endpoint và thông tin xác thực, sau đó cấp quyền truy cập các service plan cho người dùng hoặc tổ chức.

Luồng điển hình:

1. Cloud Controller lấy catalog từ broker.
2. Người dùng chọn service và plan để tạo service instance.
3. Cloud Controller gọi provision với thông tin organization và space.
4. Broker tạo tài nguyên hoặc trả operation bất đồng bộ.
5. Cloud Controller theo dõi last operation nếu cần.
6. Khi ứng dụng yêu cầu bind, Cloud Controller gọi endpoint binding.
7. Broker trả credentials và Cloud Foundry cung cấp thông tin đó cho ứng dụng, thường qua VCAP_SERVICES.
8. Khi ứng dụng bỏ binding hoặc người dùng xóa instance, Cloud Controller gọi unbind và deprovision theo vòng đời.

Broker có thể dùng context của Cloud Foundry để phân vùng tài nguyên, áp dụng quota hoặc gắn metadata. Tuy nhiên, logic nghiệp vụ không nên phụ thuộc cứng vào một cấu trúc context duy nhất. Cần chuyển context thành một mô hình nội bộ rõ ràng để sau này có thể tích hợp platform khác.

### 10.2. Kubernetes

Kubernetes không mặc định cung cấp một API service broker OSB giống Cloud Foundry. Có một mô hình Service Catalog từng tích hợp OSB API với Kubernetes thông qua các resource như ServiceInstance và ServiceBinding. Đây là mô hình tích hợp có tính lịch sử; khi triển khai trên cluster hiện đại, cần xác minh controller và phiên bản Service Catalog đang được hỗ trợ.

Một cách tích hợp khác là xây dựng controller hoặc adapter riêng. Controller theo dõi Custom Resource Definition (CRD) mô tả yêu cầu dịch vụ, sau đó gọi OSB API của broker. Ví dụ:

- Một custom resource đại diện cho service instance.
- Một custom resource khác đại diện cho binding.
- Controller chuyển spec thành request provision hoặc bind.
- Trạng thái operation được phản ánh vào status và conditions của resource.
- Khi resource bị xóa, finalizer bảo đảm controller gọi deprovision hoặc unbind trước khi Kubernetes xóa hẳn object.
- Credentials được lưu trong Kubernetes Secret và chỉ cấp cho workload cần sử dụng.

Luồng minh họa:

~~~mermaid
flowchart LR
    U[Developer áp dụng YAML] --> API[Kubernetes API Server]
    API --> CRD[Service Request CRD]
    CRD --> C[Broker Integration Controller]
    C -->|OSB API| B[Service Broker]
    B --> P[Provisioning Backend]
    P --> R[Tài nguyên thực tế]
    B --> C
    C --> ST[CR Status / Conditions]
    C --> SEC[Kubernetes Secret]
    SEC --> APP[Workload]
~~~

Khi thiết kế tích hợp Kubernetes, cần xác định rõ:

- Scope của resource là namespaced hay cluster-scoped.
- Namespace UID và tenant identity được truyền sang broker như thế nào.
- Controller xử lý retry và backoff ra sao.
- Finalizer xử lý thế nào khi broker không truy cập được.
- Secret được tạo, cập nhật, rotation và xóa như thế nào.
- Controller có thể khôi phục trạng thái sau khi restart hay không.
- Quyền RBAC nào cần thiết để đọc CRD, tạo Secret và gọi broker.

Không nên cho rằng mọi tài nguyên Kubernetes đều tự động trở thành service instance. Broker vẫn cần định nghĩa catalog, plan, chính sách cấp phát và mapping giữa thao tác OSB API với tài nguyên cluster.

### 10.3. Giữ phần nghiệp vụ độc lập với platform

Nếu cần hỗ trợ nhiều nền tảng, nên chuẩn hóa context thành một đối tượng nội bộ:

~~~java
public record TenantContext(
        String platform,
        String organizationId,
        String spaceId,
        String namespaceId,
        String consumerId
) {}
~~~

Đây là mô hình minh họa. Các trường thực tế phụ thuộc vào nền tảng và chính sách cô lập tenant. Adapter của Cloud Foundry có thể điền organizationId và spaceId; adapter Kubernetes có thể điền namespaceId và định danh cluster. Application service chỉ làm việc với TenantContext đã được xác thực và chuẩn hóa.

## 11. Lỗi, khả năng quan sát và vận hành

Broker cần phân biệt lỗi đầu vào, lỗi quyền, lỗi trạng thái và lỗi backend. Việc ánh xạ lỗi nên tuân theo mã HTTP và error response của OSB API.

| Tình huống | Cách xử lý thường gặp |
|---|---|
| Request sai cấu trúc hoặc thiếu dữ liệu | 400 Bad Request |
| Thiếu hoặc sai thông tin xác thực | 401 Unauthorized |
| Không có quyền trên tenant hoặc tài nguyên | 403 Forbidden |
| Instance hoặc binding không tồn tại | 404 Not Found |
| ID đã được dùng cho request xung đột | 409 Conflict |
| Thao tác không hợp lệ theo trạng thái hoặc capability | 422 Unprocessable Entity |
| Backend tạm thời không sẵn sàng | 503 Service Unavailable hoặc lỗi gateway phù hợp |
| Lỗi không dự kiến trong broker | 500 Internal Server Error |

Không nên trả stack trace hoặc thông tin kết nối nội bộ trong response. Response nên có error code và description đủ để nền tảng hoặc người vận hành hiểu cách xử lý mà không làm lộ dữ liệu nhạy cảm.

### 11.1. Logging và tracing

Mỗi request nên có correlation ID hoặc trace ID xuyên suốt từ platform đến broker, worker và backend adapter. Log cần giúp trả lời:

- Ai hoặc platform nào gửi request?
- Request tác động lên instance hoặc binding nào?
- Operation nào được tạo?
- Worker nào đang xử lý?
- Backend nào được gọi?
- Thao tác thất bại ở bước nào?
- Có bao nhiêu lần retry?

Không đưa credentials, access token, mật khẩu hoặc dữ liệu parameters nhạy cảm vào log. Các định danh instance, operation và tenant nên được ghi theo chính sách bảo vệ dữ liệu của hệ thống.

### 11.2. Metrics

Một số metric hữu ích:

- Số request theo endpoint và kết quả HTTP.
- Thời gian xử lý provision, update, bind và deprovision.
- Số operation đang chạy và số operation bị treo.
- Tỷ lệ operation thành công/thất bại.
- Số lần retry theo loại backend.
- Độ trễ queue và tuổi của message lâu nhất.
- Số instance theo trạng thái và plan.
- Số lỗi xác thực, authorization và quota.

Không nên dùng instance ID, user ID hoặc secret làm metric label vì cardinality cao và có thể làm lộ thông tin.

### 11.3. Audit

Audit ghi lại các thay đổi có ảnh hưởng đến tài nguyên: tạo instance, đổi plan, cấp binding, thu hồi binding và deprovision. Bản ghi nên có actor hoặc platform, tenant, resource ID, operation ID, thời điểm và kết quả. Audit cần được bảo vệ khỏi sửa đổi trái phép và có thời hạn lưu phù hợp.

## 12. Ví dụ luồng vòng đời hoàn chỉnh

Giả sử một nhóm phát triển cần database PostgreSQL cho ứng dụng billing.

1. Nền tảng đọc catalog và hiển thị service managed-postgresql cùng các plan.
2. Người dùng chọn plan production và gửi yêu cầu tạo instance.
3. Broker kiểm tra tenant, quota, service ID, plan ID và parameters.
4. Broker lưu instance ở trạng thái PROVISIONING, tạo operation và phát sự kiện outbox.
5. Worker gọi PostgreSQL backend để tạo database, cấu hình backup và tạo thông tin quản trị cần thiết.
6. Worker xác nhận backend đã sẵn sàng, lưu backend reference và chuyển instance sang READY.
7. Nền tảng truy vấn last operation và nhận state succeeded.
8. Ứng dụng yêu cầu bind. Broker tạo database role riêng, lưu secret reference và trả credentials.
9. Nền tảng cung cấp credentials cho ứng dụng.
10. Khi cần tăng dung lượng, nền tảng gọi update. Broker tạo operation mới và điều phối backend.
11. Khi ứng dụng không còn dùng database, nền tảng gọi unbind để thu hồi role.
12. Khi người dùng xóa service instance, broker thực hiện deprovision và xác nhận tài nguyên đã được thu hồi.

Luồng này cho thấy broker quản lý cả tài nguyên lẫn quyền sử dụng tài nguyên. Chỉ tạo database là chưa đủ; broker còn phải bảo đảm credentials được cấp đúng consumer, có thể thu hồi và không bị dùng lại sau khi binding đã kết thúc.

## 13. Các quyết định kiến trúc cần làm rõ

Khi xây dựng một broker thực tế, nhóm phát triển cần thống nhất một số quyết định trước khi triển khai:

**Nguồn sự thật của trạng thái:** broker lưu trạng thái mong muốn, trạng thái operation và backend reference ở đâu? Khi broker và backend không đồng bộ, quy trình reconciliation sẽ xác định trạng thái đúng như thế nào?

**Chiến lược provision:** thao tác nào có thể hoàn tất đồng bộ, thao tác nào cần async? Thời gian chờ tối đa là bao lâu? Nền tảng sẽ nhận operation token và truy vấn trạng thái như thế nào?

**Idempotency:** instance ID và binding ID được dùng làm khóa ra sao? Request fingerprint bao gồm những trường nào? Backend có thể tìm lại tài nguyên đã tạo sau một timeout hay không?

**Update và rollback:** plan nào có thể chuyển sang plan nào? Có thay đổi nào không thể đảo ngược? Khi bước thứ ba thất bại sau khi hai bước đầu đã hoàn tất, broker sẽ tiếp tục, bù trừ hay yêu cầu can thiệp?

**Quyền và credentials:** broker tạo danh tính backend riêng cho từng binding hay dùng chung? Secret được lưu ở đâu? Ai có thể truy xuất và rotation diễn ra khi nào?

**Deprovision:** tài nguyên có được xóa ngay hay có thời gian giữ lại? Backup có cần được giữ? Cách xử lý khi còn binding hoặc backend không phản hồi là gì?

**Tích hợp platform:** context nào là bắt buộc? Capability nào được công bố trong catalog? Platform có hỗ trợ đúng phiên bản OSB API và các luồng async cần thiết hay không?

Các quyết định này phải được thể hiện trong domain model, catalog và workflow. Nếu chỉ xử lý trong controller, hệ thống sẽ khó duy trì tính nhất quán khi thêm backend hoặc platform mới.

## 14. Những lỗi thiết kế thường gặp

- **Lưu operation trong bộ nhớ:** broker restart sẽ mất khả năng theo dõi công việc đang chạy.
- **Gọi backend trực tiếp trong request dài:** dễ vượt timeout và giữ tài nguyên HTTP không cần thiết.
- **Không có idempotency:** platform retry có thể tạo nhiều database, bucket hoặc credentials.
- **Cập nhật trạng thái trước khi backend xác nhận:** broker có thể báo READY trong khi tài nguyên chưa sử dụng được.
- **Gộp instance và binding:** khó thu hồi quyền của một consumer mà vẫn giữ tài nguyên cho consumer khác.
- **Catalog không ổn định:** thay đổi service ID hoặc plan ID có thể làm các instance hiện có không còn được tham chiếu đúng.
- **Tin parameters từ client:** có thể dẫn đến vượt quota, cấp quyền quá mức hoặc tạo tài nguyên ngoài chính sách.
- **Log credentials:** làm lộ dữ liệu truy cập qua log aggregation hoặc tracing.
- **Không có reconciliation:** trạng thái broker có thể lệch backend trong thời gian dài sau timeout hoặc crash.
- **Phụ thuộc cứng vào Cloud Foundry hoặc Kubernetes:** khiến logic nghiệp vụ khó tái sử dụng khi tích hợp nền tảng khác.

## Kết luận

Kiến trúc service broker tạo ra một lớp hợp đồng giữa nền tảng và các hệ thống cung cấp tài nguyên. OSB API chuẩn hóa cách công bố catalog, lựa chọn plan và quản lý vòng đời service instance, binding. Spring Cloud Service Broker giúp triển khai hợp đồng này trong ứng dụng Spring, còn application service, domain model và backend adapter chịu trách nhiệm cho chính sách và thao tác nghiệp vụ.

Một broker đáng tin cậy cần lưu trạng thái bền vững, hỗ trợ operation bất đồng bộ, xử lý request lặp an toàn, cô lập tenant và có khả năng phục hồi khi backend hoặc mạng gặp lỗi. Khi các trách nhiệm đó được tổ chức thành những lớp rõ ràng, broker có thể tích hợp với Cloud Foundry, Kubernetes hoặc platform khác mà vẫn giữ được một mô hình cấp phát tài nguyên nhất quán.
