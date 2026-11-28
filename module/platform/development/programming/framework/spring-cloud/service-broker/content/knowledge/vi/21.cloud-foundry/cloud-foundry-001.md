# Vai trò marketplace, service broker và service instance trong Cloud Foundry

## Bối cảnh

Cloud Foundry cung cấp marketplace để người dùng ứng dụng tìm và sử dụng các dịch vụ như PostgreSQL, Redis, message queue hoặc object storage. Marketplace không trực tiếp tạo database hay cấp credential. Nó hiển thị các service offering và service plan mà nền tảng đã đăng ký từ những service broker.

Service broker là ứng dụng hoặc dịch vụ độc lập thực hiện hợp đồng Open Service Broker API (OSB API). Khi người dùng chọn một dịch vụ trong marketplace, Cloud Foundry gọi broker để lấy catalog, provision service instance, tạo binding và thu hồi tài nguyên khi cần. Broker tiếp tục làm việc với provider phía sau, chẳng hạn một dịch vụ database managed, API của cloud hoặc Kubernetes operator.

Trong mô hình này có ba khái niệm cần tách biệt:

- **Marketplace:** nơi công bố và khám phá service offering cùng các plan mà tổ chức/space được phép sử dụng.
- **Service broker:** thành phần cung cấp catalog và thực thi các thao tác vòng đời theo OSB API.
- **Service instance:** một lần triển khai dịch vụ cụ thể được tạo theo offering và plan, ví dụ một database cho ứng dụng orders.

Hiểu đúng vai trò của ba thành phần giúp thiết kế broker tương thích Cloud Foundry, phân quyền service access, quản lý instance và binding, cũng như xử lý các thao tác bất đồng bộ.

## 1. Các thành phần trong kiến trúc

Một triển khai Cloud Foundry điển hình có các thành phần sau:

| Thành phần | Vai trò |
|---|---|
| Developer hoặc operator | Khám phá marketplace, tạo service instance, bind service vào ứng dụng |
| Cloud Foundry CLI | Gửi lệnh quản trị và sử dụng dịch vụ tới Cloud Controller API |
| Marketplace UI | Hiển thị offering và plan mà người dùng được phép truy cập |
| Cloud Controller (CC) | Quản lý service broker registration, catalog, service access, service instance và binding; điều phối request OSB |
| Service broker | Triển khai OSB API, xác thực request từ platform, quản lý nghiệp vụ và gọi provider |
| Provider | Hệ thống thực sự tạo hoặc quản lý database, cache, queue, bucket hay tài nguyên khác |
| Application | Sử dụng thông tin kết nối được cấp qua service binding |

Cloud Controller là điểm điều phối giữa người dùng và broker. Broker không thay thế Cloud Controller, cũng không cần biết cách hiển thị marketplace. Broker cung cấp catalog và thực hiện hợp đồng API; Cloud Controller quản lý trải nghiệm platform, quyền truy cập và trạng thái service instance mà người dùng nhìn thấy.

~~~mermaid
flowchart LR
    DEV[Developer / Operator] --> CLI[Cloud Foundry CLI]
    DEV --> UI[Marketplace UI]
    CLI --> CC[Cloud Controller]
    UI --> CC
    CC -->|GET catalog| BROKER[Service Broker]
    CC -->|Provision / Update / Deprovision| BROKER
    CC -->|Bind / Unbind| BROKER
    BROKER --> APP[Broker application services]
    APP --> PROVIDER[Cloud provider / Kubernetes / Database]
    PROVIDER --> RESOURCE[Database, cache, queue, storage]
    CC -->|Binding credentials| APPENV[Application environment]
    APPENV --> APPCLIENT[Application]
~~~

Sơ đồ thể hiện luồng khái niệm. Cách triển khai cụ thể có thể bổ sung gateway, queue, worker, secret manager hoặc service manager riêng.

## 2. Marketplace, service offering và service plan

Marketplace là danh mục dịch vụ mà Cloud Foundry công bố cho người dùng. Một mục trong marketplace thường tương ứng với một service offering do broker cung cấp. Offering mô tả loại dịch vụ; plan mô tả một cấu hình hoặc cấp dịch vụ cụ thể.

Ví dụ:

| Offering | Plan | Ý nghĩa |
|---|---|---|
| orders-db | small | Database dung lượng nhỏ cho môi trường phát triển |
| orders-db | standard | Database production với tài nguyên tiêu chuẩn |
| orders-db | high-availability | Database có dự phòng và khả năng chịu lỗi cao |
| cache | shared | Cache dùng chung, giới hạn tài nguyên |
| cache | dedicated | Cache dành riêng cho một instance |

Người dùng thường xem marketplace bằng:

~~~bash
cf marketplace
cf marketplace -s orders-db
~~~

Lệnh đầu hiển thị các service offering khả dụng với người dùng hiện tại. Lệnh thứ hai hiển thị các plan của offering orders-db mà người dùng được phép truy cập.

### Catalog đến từ broker

Broker cung cấp catalog qua endpoint OSB API:

~~~http
GET /v2/catalog HTTP/1.1
X-Broker-API-Version: 2.17
~~~

Response catalog chứa danh sách services và plans. Ví dụ rút gọn:

~~~json
{
  "services": [
    {
      "name": "orders-db",
      "id": "7a1c2d3e-4f50-4a60-8b70-123456789001",
      "description": "Managed PostgreSQL for application workloads",
      "bindable": true,
      "plans": [
        {
          "name": "small",
          "id": "8b2c3d4e-5f60-4a70-9c80-123456789002",
          "description": "Small PostgreSQL instance",
          "free": false
        },
        {
          "name": "standard",
          "id": "9c3d4e5f-6070-4a80-ad90-123456789003",
          "description": "Production PostgreSQL instance",
          "free": false
        }
      ]
    }
  ]
}
~~~

Các ID service và plan phải ổn định qua các lần cập nhật broker. Cloud Controller và các service instance đã tạo tham chiếu đến những ID này; đổi ID có thể làm hỏng mapping giữa instance hiện có với catalog mới. Tên và mô tả có thể được cải thiện, nhưng ID phải được quản lý như định danh contract.

Một số thuộc tính catalog quan trọng:

- **bindable:** offering có cho phép tạo service binding hay không.
- **plans:** những cấu hình người dùng có thể chọn.
- **plan_updateable:** broker có hỗ trợ thay đổi plan của instance hay không.
- **instances_retrievable** và **bindings_retrievable:** broker có hỗ trợ fetch trạng thái tương ứng hay không.
- **metadata:** thông tin hiển thị bổ sung nếu platform và broker sử dụng.

Không khai báo một capability là true nếu broker chưa triển khai đầy đủ endpoint và semantics cần thiết.

## 3. Service broker là adapter giữa Cloud Foundry và provider

Service broker triển khai hợp đồng OSB API để Cloud Controller có thể yêu cầu:

| Nghiệp vụ | OSB API endpoint điển hình | Kết quả |
|---|---|---|
| Đọc catalog | GET /v2/catalog | Danh sách offering và plan |
| Provision instance | PUT /v2/service_instances/{instance_id} | Tạo tài nguyên theo service/plan |
| Fetch instance (nếu hỗ trợ) | GET /v2/service_instances/{instance_id} | Đọc trạng thái instance |
| Update instance | PATCH /v2/service_instances/{instance_id} | Thay đổi plan/parameters được hỗ trợ |
| Deprovision instance | DELETE /v2/service_instances/{instance_id} | Thu hồi tài nguyên |
| Create binding | PUT /v2/service_instances/{instance_id}/service_bindings/{binding_id} | Cấp thông tin kết nối/quyền truy cập |
| Delete binding | DELETE /v2/service_instances/{instance_id}/service_bindings/{binding_id} | Thu hồi credential hoặc quyền |

Cloud Controller gọi broker qua mạng bằng địa chỉ và credential đã đăng ký. Broker không nên phụ thuộc vào một UI hoặc CLI cụ thể; cùng một API có thể được sử dụng bởi Cloud Foundry CLI, dashboard và automation của platform.

### Broker không phải provider

Một broker có thể quản lý nhiều provider. Ví dụ offering orders-db có thể tạo database trên cloud managed database; offering cache có thể tạo Redis trên Kubernetes. Broker chuẩn hóa khác biệt provider thành một contract OSB nhất quán.

Trong Spring Cloud, có thể phân chia:

- OSB controller/handler nhận request.
- Application service điều phối provision, update, bind và deprovision.
- Repository lưu service instance, binding và operation.
- Provider adapter gọi cloud API hoặc Kubernetes.
- Worker xử lý operation dài hạn.
- Secret manager lưu credential và trả secret reference cho binding service.

Việc phân lớp giúp thay provider mà không thay đổi cách Cloud Controller sử dụng marketplace.

## 4. Đăng ký broker với Cloud Foundry

Operator đăng ký service broker để Cloud Controller biết endpoint và credential dùng khi gọi API. Với Cloud Foundry CLI, lệnh phổ biến có dạng:

~~~bash
cf create-service-broker orders-broker BROKER_USERNAME BROKER_PASSWORD https://broker.example.com
~~~

Tên broker là tên quản trị trong Cloud Foundry. Username/password là credential Cloud Controller dùng để xác thực với broker; chúng không phải credential của người dùng ứng dụng và cũng không phải credential của provider.

Sau khi broker được đăng ký, operator có thể kiểm soát offering/plan được phép dùng trong tổ chức:

~~~bash
cf enable-service-access orders-db --plan standard --org retail
~~~

Ví dụ trên bật quyền truy cập plan standard của offering orders-db cho org retail. Tùy phiên bản CLI và platform, cú pháp tùy chọn có thể khác; cần kiểm tra help của CLI đang dùng.

Người dùng trong phạm vi được cấp quyền có thể xem offering:

~~~bash
cf marketplace -s orders-db
~~~

### Cập nhật broker và catalog

Khi broker thay đổi catalog, operator cập nhật thông tin broker đã đăng ký:

~~~bash
cf update-service-broker orders-broker BROKER_USERNAME BROKER_PASSWORD https://broker.example.com
~~~

Lệnh cập nhật broker registration và cho Cloud Controller làm mới thông tin broker theo hành vi của bản phân phối Cloud Foundry đang dùng. Sau khi cập nhật, operator nên kiểm tra marketplace, plan access và các service instance hiện có.

Không xóa rồi đăng ký lại broker chỉ để đổi mô tả hoặc endpoint nếu lệnh update đáp ứng được nhu cầu. Việc thay registration có thể ảnh hưởng tới catalog access và quá trình vận hành.

## 5. Service instance là gì?

Service instance là một lần sử dụng cụ thể của service offering theo một plan. Ví dụ, offering orders-db có plan standard; người dùng tạo instance orders-production cho ứng dụng đơn hàng.

Lệnh:

~~~bash
cf create-service orders-db standard orders-production
~~~

Cloud Controller ghi nhận yêu cầu và gọi broker provision instance. Broker nhận instance_id do platform dùng để nhận diện tài nguyên, cùng service ID, plan ID, parameters và context. Broker tạo tài nguyên provider hoặc bắt đầu operation bất đồng bộ.

Một service instance có thể được dùng bởi một hoặc nhiều ứng dụng tùy chính sách binding và thiết kế dịch vụ. Instance không đồng nghĩa với một binding:

- Instance biểu diễn tài nguyên dịch vụ đã được provision.
- Binding biểu diễn quyền truy cập hoặc cấu hình kết nối được cấp cho một consumer.
- Một instance có thể có nhiều binding nếu offering cho phép.

~~~mermaid
flowchart TD
    O[Service offering: orders-db] --> P1[Plan: small]
    O --> P2[Plan: standard]
    O --> P3[Plan: high-availability]
    P2 --> I[Service instance: orders-production]
    I --> B1[Binding: orders-api]
    I --> B2[Binding: reporting-worker]
    B1 --> C1[Credentials for orders-api]
    B2 --> C2[Credentials for reporting-worker]
~~~

### Managed service instance và user-provided service

Cloud Foundry phân biệt managed service instance do broker quản lý với user-provided service do người dùng tự khai báo thông tin kết nối.

| Loại | Cách tạo | Có gọi broker OSB để provision? |
|---|---|---|
| Managed service instance | Chọn offering và plan từ marketplace | Có |
| User-provided service instance | Người dùng cung cấp URL/credential hoặc thông tin kết nối | Không provision qua service broker |

User-provided service thường được tạo bằng lệnh như cf create-user-provided-service. Nó giúp ứng dụng nhận cấu hình kết nối qua cơ chế binding của Cloud Foundry, nhưng không có nghĩa broker đã tạo hoặc quản lý tài nguyên đằng sau.

Khi xây dựng service broker, cần tập trung vào managed service lifecycle. Không nhầm user-provided service với một service offering được broker công bố.

## 6. Luồng từ marketplace đến provision

Một luồng tạo service instance điển hình:

1. Operator đăng ký broker với Cloud Controller.
2. Cloud Controller lấy catalog từ endpoint của broker.
3. Operator bật quyền truy cập offering/plan cho org hoặc phạm vi phù hợp.
4. Developer xem marketplace và chọn offering cùng plan.
5. Developer chạy cf create-service.
6. Cloud Controller xác thực quyền và tạo bản ghi service instance ở trạng thái đang xử lý.
7. Cloud Controller gửi PUT provision đến broker.
8. Broker xác thực request, kiểm tra plan/parameters/context và lưu trạng thái.
9. Broker gọi provider trực tiếp hoặc enqueue operation.
10. Cloud Controller nhận kết quả đồng bộ hoặc polling last_operation nếu broker trả 202.
11. Khi hoàn tất, service instance chuyển sang trạng thái sẵn sàng theo platform.

~~~mermaid
sequenceDiagram
    participant D as Developer
    participant CC as Cloud Controller
    participant B as Service Broker
    participant DB as Broker Database
    participant P as Provider

    D->>CC: cf create-service orders-db standard orders-production
    CC->>CC: Check service access and plan
    CC->>B: PUT /v2/service_instances/{instance_id}
    B->>DB: Save instance and operation state
    B->>P: Create database
    alt Synchronous completion
        P-->>B: Database ready
        B->>DB: Save provider resource ID
        B-->>CC: 201 Created
    else Asynchronous completion
        B-->>CC: 202 Accepted + operation
        loop Poll until terminal
            CC->>B: GET last_operation
            B->>DB: Read operation state
            B-->>CC: in progress / succeeded / failed
        end
        P-->>B: Database ready
        B->>DB: Mark operation succeeded
    end
    CC-->>D: Service instance status
~~~

Nếu request cần xử lý dài, broker chỉ trả 202 sau khi đã lưu operation bền vững. Worker phải có thể tiếp tục sau restart và bảo đảm retry không tạo database trùng.

## 7. Parameters và context từ Cloud Foundry

Khi tạo instance, developer có thể truyền parameters:

~~~bash
cf create-service orders-db standard orders-production -c '{"storage_gb":50,"backup":"daily"}'
~~~

Parameters mô tả cấu hình instance do offering/plan cho phép, ví dụ storage size hoặc backup policy. Broker cần validate theo schema và policy của plan; không tin mọi giá trị do caller gửi.

Cloud Foundry cũng có thể gửi context theo OSB API, chứa thông tin platform và phạm vi tổ chức/space. Với Cloud Foundry, context thường giúp broker hiểu instance được tạo từ foundation, org hoặc space nào.

Context hữu ích cho:

- Phân vùng tài nguyên theo tenant.
- Gắn owner metadata vào provider resource.
- Áp dụng quota hoặc policy theo organization.
- Audit nguồn yêu cầu.
- Tạo tên resource tránh xung đột giữa các tenant.

Context không phải credential xác thực. Broker phải xác thực Cloud Controller bằng broker credentials và chỉ sử dụng context sau khi kiểm tra cấu trúc, nguồn và chính sách. Không dùng một trường context do caller gửi làm bằng chứng duy nhất để cấp quyền truy cập vào tenant.

## 8. Binding service instance với application

Sau khi instance sẵn sàng, developer có thể bind vào ứng dụng:

~~~bash
cf bind-service orders-api orders-production
~~~

Cloud Controller gọi endpoint create binding của broker. Broker thường tạo hoặc cấp:

- Username/password hoặc database role riêng.
- Token hoặc API key.
- Endpoint/hostname và port.
- Quyền truy cập theo phạm vi của ứng dụng.
- Secret reference để platform có thể cung cấp credentials cho application.

Response binding theo OSB API có thể chứa credentials và thông tin cần thiết để kết nối. Cloud Foundry sử dụng binding để cung cấp dữ liệu dịch vụ cho ứng dụng, thường qua biến môi trường VCAP_SERVICES.

Ví dụ minh họa:

~~~json
{
  "VCAP_SERVICES": {
    "orders-db": [
      {
        "name": "orders-production",
        "label": "orders-db",
        "plan": "standard",
        "credentials": {
          "hostname": "db.internal.example",
          "port": 5432,
          "database": "orders",
          "username": "orders_api",
          "password": "<injected-secret>"
        }
      }
    ]
  }
}
~~~

Đây là cấu trúc minh họa. Ứng dụng thực tế nên đọc VCAP_SERVICES qua thư viện/configuration phù hợp thay vì hardcode tên biến hoặc giả định chỉ có một service.

### Vì sao mỗi binding nên có identity riêng?

Nếu một instance có nhiều ứng dụng consumer, broker có thể cấp principal hoặc token riêng cho từng binding. Khi orders-api bị unbind, broker thu hồi đúng credential của binding đó mà không làm gián đoạn reporting-worker.

Broker không nên trả lại cùng credential quản trị của database cho mọi ứng dụng. Cần áp dụng least privilege, lưu binding record và hỗ trợ thu hồi.

### Khi credentials thay đổi

Sau khi bind một service vào ứng dụng đang chạy, Cloud Foundry cần cập nhật environment của application process để ứng dụng đọc được binding mới. Trong workflow phổ biến, developer chạy:

~~~bash
cf restage orders-api
~~~

Tùy runtime và cơ chế binding của platform, có thể cần restage hoặc restart để process nhận cấu hình mới. Không nên giả định một process đang chạy tự động thấy mọi thay đổi của VCAP_SERVICES.

## 9. Unbind và deprovision

Unbind thu hồi quyền truy cập được tạo cho một binding:

~~~bash
cf unbind-service orders-api orders-production
~~~

Cloud Controller gọi DELETE binding của broker. Broker thu hồi token, database role, secret hoặc resource mapping gắn với binding. Unbind không nhất thiết xóa service instance.

Deprovision xóa service instance:

~~~bash
cf delete-service orders-production
~~~

Cloud Controller gọi DELETE service instance. Broker thu hồi tài nguyên provider do instance sở hữu, xử lý dependencies và cập nhật trạng thái cuối.

Phân biệt hai thao tác:

| Thao tác | Tác động | Tài nguyên còn lại |
|---|---|---|
| Unbind | Thu hồi quyền của một consumer | Service instance và các binding khác vẫn tồn tại |
| Deprovision | Xóa service instance | Provider resource thuộc instance được thu hồi theo policy |

Nếu broker xóa database khi chỉ có một ứng dụng unbind, ứng dụng khác đang dùng instance có thể bị mất dữ liệu. Ngược lại, nếu deprovision không thu hồi provider resource, broker tạo tài nguyên mồ côi và tiếp tục phát sinh chi phí.

## 10. Update service instance

Một số offering cho phép thay đổi plan hoặc parameters sau khi provision. Cloud Foundry có thể gửi update request đến broker khi developer chạy:

~~~bash
cf update-service orders-production -p high-availability -c '{"backup":"hourly"}'
~~~

Broker phải công bố khả năng update trong catalog, kiểm tra plan và parameters đích, xác minh chuyển đổi có hợp lệ hay không và xử lý migration. Không phải mọi plan đều có thể chuyển đổi hai chiều; ví dụ chuyển từ standard sang high-availability có thể hỗ trợ nhưng downgrade ngược lại có thể không an toàn.

Các điểm cần kiểm tra:

- Plan mới có thuộc cùng service offering và được phép update không.
- Tham số nào có thể thay đổi sau khi tạo.
- Update có làm mất dữ liệu hoặc thay endpoint không.
- Có cần backup/snapshot trước khi thay đổi không.
- Provider có hỗ trợ asynchronous update không.
- Broker có cần serialize update với binding/deprovision không.
- Nếu update thất bại giữa chừng, broker rollback hay forward-recovery?

Với update dài hạn, broker trả 202 và Cloud Controller polling last_operation. Broker cần lưu target plan/parameters, operation ID và checkpoint để có thể tiếp tục sau restart.

## 11. Service access và phạm vi organization/space

Việc một offering xuất hiện trong catalog không có nghĩa mọi developer đều được phép sử dụng. Cloud Foundry operator có thể kiểm soát service access theo org và plan.

Ví dụ:

~~~bash
cf enable-service-access orders-db --plan standard --org retail
cf disable-service-access orders-db --plan standard --org retail
~~~

Service access kiểm soát ai có thể tạo instance từ offering/plan. Đây là lớp quyền của Cloud Foundry. Broker vẫn cần tự bảo vệ dữ liệu tenant và tài nguyên provider.

Broker nên lưu liên kết giữa:

- Platform/foundation identity.
- Organization ID.
- Space ID nếu có.
- Service instance ID.
- Service offering ID và plan ID.
- Provider resource ID.
- Binding IDs và principal/token được cấp.

Khi nhận update/deprovision, broker phải kiểm tra instance thuộc đúng phạm vi và không để request từ một platform hoặc tenant tác động tài nguyên của tenant khác. Không chỉ dựa vào tên instance mà developer nhìn thấy; dùng định danh ổn định do OSB request cung cấp cùng platform scope đã xác thực.

## 12. Xử lý bất đồng bộ trong Cloud Foundry

Provision, update hoặc deprovision có thể kéo dài. Broker có thể trả 202 Accepted nếu request hỗ trợ asynchronous operation và broker đã lưu công việc bền vững.

Luồng:

1. Cloud Controller gửi request với accepts_incomplete=true khi hỗ trợ thao tác bất đồng bộ.
2. Broker validate request và kiểm tra xung đột.
3. Broker lưu operation cùng trạng thái instance trong database.
4. Broker trả 202 và operation reference.
5. Worker gọi provider hoặc polling provider operation.
6. Cloud Controller gọi last_operation để kiểm tra tiến trình.
7. Broker trả in progress, succeeded hoặc failed theo trạng thái đã lưu.

Broker không được trả 202 trước khi operation được commit. Nếu worker crash hoặc broker restart, operation phải được recovery. Nếu provider timeout sau khi có thể đã tạo tài nguyên, broker phải reconcile trước khi gọi create lại.

### Trạng thái cần đồng bộ

Cloud Controller giữ trạng thái service instance ở phía platform. Broker giữ trạng thái nghiệp vụ và mapping provider ở phía broker. Hai bên cần hội tụ về kết quả nhất quán:

| Broker state | Ý nghĩa với Cloud Foundry |
|---|---|
| ACCEPTED / RUNNING | Instance đang được tạo/cập nhật/xóa |
| RETRY_WAIT / RECONCILING | Operation còn đang xử lý; platform tiếp tục theo dõi |
| SUCCEEDED | Thao tác đạt target state |
| FAILED | Broker xác nhận thao tác thất bại |

Không đánh dấu succeeded chỉ vì provider đã nhận request. Cần xác minh resource đạt trạng thái mong muốn.

## 13. Tích hợp Spring Cloud Open Service Broker

Spring Cloud Open Service Broker cung cấp abstraction để xây dựng broker theo OSB API. Ứng dụng có thể triển khai service instance service và binding service, sau đó kết nối với application service riêng.

Một cách phân lớp:

~~~text
cloudfoundry-broker/
  osb/
    CatalogService
    ServiceInstanceService
    ServiceInstanceBindingService
  application/
    ProvisioningService
    UpdatingService
    DeprovisioningService
    BindingService
  domain/
    ServiceInstance
    ServiceBinding
    ServiceOperation
  persistence/
    ServiceInstanceRepository
    BindingRepository
    OperationRepository
  provider/
    DatabaseProviderAdapter
    KubernetesProviderAdapter
~~~

Tên package/class là gợi ý tổ chức mã nguồn, không phải tên bắt buộc của framework.

### Catalog service

Catalog service công bố offering và plan ổn định. Có thể cấu hình service definition trong code hoặc xây dựng từ registry/configuration được quản trị. Không tạo ID mới mỗi lần ứng dụng khởi động.

### Service instance service

Các handler provision, update, deprovision chuyển request model của framework thành command nghiệp vụ. Application service kiểm tra plan, context, parameters, idempotency và trạng thái operation.

### Binding service

Binding service cấp credential hoặc quyền truy cập theo binding ID. Secret nên được sinh an toàn, lưu trong secret manager hoặc kho mã hóa, và chỉ trả cho consumer được phép.

### Provider adapter

Provider adapter che giấu khác biệt của cloud API, database API hoặc Kubernetes. Không để controller OSB gọi provider SDK trực tiếp; điều này giúp test, retry, reconciliation và thay provider dễ hơn.

## 14. Bảo mật khi vận hành broker trên Cloud Foundry

Cloud Foundry và broker có hai mặt bảo mật:

**Platform gọi broker**

- Dùng TLS cho endpoint broker.
- Cấu hình broker username/password đủ mạnh và quản lý qua secret store.
- Chỉ Cloud Controller hoặc thành phần được phép mới được gọi endpoint OSB.
- Rotate broker credentials theo quy trình có kiểm soát.
- Không ghi Authorization header vào log.

**Broker gọi provider**

- Dùng service account hoặc workload identity có least privilege.
- Không dùng credential quản trị provider cho mọi binding.
- Giới hạn quyền theo tenant/instance nếu provider hỗ trợ.
- Gắn owner metadata vào resource để reconciliation và cleanup an toàn.
- Thu hồi credential khi unbind hoặc deprovision.

**Application nhận binding**

- Chỉ cung cấp credential cần thiết cho ứng dụng.
- Tách credential theo binding khi có thể.
- Không log VCAP_SERVICES nguyên vẹn vì có thể chứa password/token.
- Không commit binding credentials vào source control.
- Khi rotate secret, phối hợp cập nhật binding và restage/restart ứng dụng theo khả năng platform.

## 15. Quan sát và xử lý sự cố

Khi developer không thấy offering trong marketplace, cần kiểm tra theo thứ tự:

1. Broker đã được đăng ký với Cloud Controller chưa.
2. Endpoint catalog có truy cập được và xác thực thành công không.
3. Catalog có service offering và plan hợp lệ không.
4. Operator đã enable service access cho org/plan chưa.
5. Catalog đã được làm mới sau khi broker thay đổi chưa.
6. Người dùng đang ở đúng org/space chưa.

Khi create-service thất bại:

- Kiểm tra trạng thái service instance bằng cf service orders-production.
- Kiểm tra log Cloud Controller và broker theo thời điểm/request.
- Xác định request provision trả đồng bộ hay 202.
- Nếu 202, kiểm tra operation và provider state.
- Kiểm tra plan ID, parameters, context và provider quota/permission.
- Xác minh provider resource có thể đã được tạo dù broker timeout.

Khi bind thất bại:

- Kiểm tra offering có bindable hay không.
- Kiểm tra binding ID và instance ID.
- Kiểm tra provider đã tạo principal/token chưa.
- Kiểm tra secret manager và quyền ghi binding record.
- Không tạo lại credential nếu request retry đang tham chiếu binding đã tồn tại.

Các metric nên có:

- Catalog request success/error.
- Provision/update/deprovision duration.
- Binding/unbinding success/error.
- Async operation age và retry count.
- Provider latency, 429/5xx và reconciliation backlog.
- Số resource mồ côi hoặc binding credential chưa được thu hồi.

## 16. Ví dụ một vòng đời đầy đủ

Giả sử team retail cần database cho ứng dụng orders:

~~~bash
# Operator đăng ký broker và bật plan
cf create-service-broker orders-broker BROKER_USERNAME BROKER_PASSWORD https://broker.example.com
cf enable-service-access orders-db --plan standard --org retail

# Developer khám phá và tạo service instance
cf marketplace -s orders-db
cf create-service orders-db standard orders-production -c '{"storage_gb":50}'

# Gắn instance vào ứng dụng
cf bind-service orders-api orders-production
cf restage orders-api

# Kiểm tra cấu hình ứng dụng
cf env orders-api

# Thu hồi binding khi ứng dụng không còn dùng
cf unbind-service orders-api orders-production

# Xóa service instance khi không còn consumer
cf delete-service orders-production
~~~

Ở phía broker, các bước tương ứng là catalog, provision, create binding, delete binding và deprovision. Provider adapter thực hiện các thao tác tài nguyên thực tế; Cloud Controller quản lý trạng thái và quyền sử dụng trên platform.

Không chạy các lệnh xóa trong ví dụ trên trên môi trường production nếu chưa xác nhận đúng service instance và chính sách lưu giữ dữ liệu. Đây là ví dụ học tập mô tả vòng đời.

## 17. Các lỗi thiết kế thường gặp

### Coi marketplace là provider

Marketplace chỉ hiển thị dịch vụ. Broker mới là thành phần nhận lệnh OSB và điều phối provider. Không đặt logic tạo database vào UI hoặc CLI.

### Coi service instance là application binding

Instance là tài nguyên dịch vụ; binding là quyền truy cập của consumer. Một instance có thể có nhiều binding và mỗi binding có thể cần credential riêng.

### Thay service/plan ID sau khi đã phát hành

Cloud Controller và instance hiện có tham chiếu ID ổn định. Đổi ID tùy tiện làm hỏng mapping và gây khó khăn khi update/deprovision.

### Bỏ qua service access

Catalog có thể hợp lệ nhưng người dùng không nhìn thấy plan vì operator chưa bật quyền cho org. Kiểm tra service access trước khi điều tra provider.

### Trả 202 nhưng không lưu operation

Cloud Controller có thể polling operation không tồn tại sau broker restart. Persist operation trước khi trả 202 và có worker recovery.

### Xóa instance khi chỉ unbind một ứng dụng

Unbind phải thu hồi quyền của binding. Deprovision mới là thao tác thu hồi service instance theo lifecycle.

### Cấp chung credential quản trị

Một ứng dụng bị lộ credential có thể ảnh hưởng toàn bộ instance. Cấp principal/token riêng, giới hạn quyền và hỗ trợ revoke.

## 18. Checklist triển khai

- [ ] Broker được đăng ký với Cloud Controller bằng endpoint TLS và credential riêng.
- [ ] Catalog trả service offering và plan có ID ổn định.
- [ ] Offering chỉ bật bindable khi binding flow đã được triển khai.
- [ ] Operator kiểm soát service access theo org/plan.
- [ ] Service instance được lưu với platform scope, instance ID, service ID và plan ID.
- [ ] Parameters và Cloud Foundry context được validate.
- [ ] Provision/update/deprovision tuân theo OSB API.
- [ ] Operation được persist trước khi trả 202 và có thể recovery sau restart.
- [ ] Binding có identity riêng và credential theo least privilege.
- [ ] Unbind chỉ thu hồi binding; deprovision thu hồi instance.
- [ ] Credentials được cung cấp cho app qua cơ chế binding/VCAP_SERVICES an toàn.
- [ ] Ứng dụng được restage/restart khi cần nhận binding environment mới.
- [ ] Retry và reconciliation không tạo provider resource trùng.
- [ ] Log/metric không làm lộ secret.
- [ ] Có kiểm thử catalog, service access, provision, bind, unbind và deprovision.

## Kết luận

Trong Cloud Foundry, marketplace là nơi khám phá service offering và plan; service broker cung cấp catalog và thực thi OSB API; service instance là tài nguyên cụ thể được provision theo một plan. Cloud Controller kết nối ba thành phần này, quản lý quyền truy cập theo org/space, lưu trạng thái instance và điều phối binding. Broker chuyển yêu cầu của platform thành thao tác provider, cấp credential theo binding và thu hồi tài nguyên theo đúng vòng đời. Khi kết hợp catalog ID ổn định, service access rõ ràng, operation bền vững, binding riêng và bảo mật credential, service broker Spring Cloud có thể tích hợp với Cloud Foundry một cách nhất quán và vận hành được trong môi trường nhiều tenant.

## Tài liệu tham khảo

- [Cloud Foundry Documentation — Services](https://docs.cloudfoundry.org/devguide/services/)
- [Cloud Foundry CLI Reference — create-service-broker](https://cli.cloudfoundry.org/en-US/v8/create-service-broker.html)
- [Open Service Broker API Specification](https://github.com/cloudfoundry/servicebroker/blob/master/spec.md)
