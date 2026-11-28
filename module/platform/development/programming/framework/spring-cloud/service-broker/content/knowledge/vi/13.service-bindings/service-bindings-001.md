# Vai trò của service binding và điều kiện bindable

Trong Open Service Broker API (OSB API), **service binding** là quan hệ cấp quyền sử dụng giữa một service instance đã được provision và một consumer như ứng dụng hoặc workload. Broker tạo binding để consumer nhận được thông tin kết nối, credential hoặc cấu hình cần thiết để sử dụng dịch vụ. Trường **bindable** trong catalog cho platform biết một service có hỗ trợ quy trình binding hay không.

Với module **SPRING_CLOUD_SERVICE_BROKER**, cần tách rõ vòng đời của service instance và vòng đời của binding. Provision tạo tài nguyên như database hoặc queue; bind tạo quyền truy cập cho một consumer; unbind thu hồi quyền của consumer đó; deprovision thu hồi tài nguyên. Một instance có thể có nhiều binding độc lập. Điều này cho phép broker cấp và thu hồi credential theo từng ứng dụng mà không phải tạo lại hoặc xóa tài nguyên dùng chung.

## 1. Service binding giải quyết vấn đề gì?

Sau khi platform provision một service instance, tài nguyên có thể đã tồn tại nhưng ứng dụng vẫn chưa biết cách truy cập. Ứng dụng cần một tập thông tin như hostname, port, database name, username, password, token hoặc cấu hình đặc thù của dịch vụ.

Service binding tạo ra mối quan hệ giữa instance và consumer, đồng thời cung cấp dữ liệu cần thiết để consumer sử dụng tài nguyên. Ví dụ:

- Một PostgreSQL instance có thể cấp một database user riêng cho mỗi ứng dụng.
- Một Redis instance có thể tạo username/password hoặc ACL riêng cho từng consumer.
- Một message broker có thể cấp quyền publish/consume trên một tập queue hoặc topic.
- Một object storage service có thể cấp access key giới hạn vào bucket hoặc prefix.
- Một dịch vụ route hoặc logging có thể trả URL hoặc cấu hình tích hợp thay vì credential database thông thường.

Nếu không có binding, platform có thể provision được tài nguyên nhưng không có quy trình tiêu chuẩn để nhận thông tin kết nối và quản lý quyền sử dụng cho ứng dụng.

Binding cũng giúp tách quyền của các consumer. Giả sử database được dùng bởi cả `orders-api` và `billing-worker`. Broker có thể tạo hai binding với hai bộ credential khác nhau. Khi `orders-api` ngừng sử dụng database, broker chỉ thu hồi credential của binding đó; `billing-worker` vẫn hoạt động.

## 2. Phân biệt service, plan, instance và binding

Bốn khái niệm liên kết với nhau nhưng có trách nhiệm riêng:

| Đối tượng | Vai trò | Ví dụ |
|---|---|---|
| Service | Loại dịch vụ broker công bố trong catalog | PostgreSQL |
| Service plan | Cấp cấu hình hoặc tính năng của service | Standard, Production |
| Service instance | Tài nguyên cụ thể được tạo từ service và plan | Database `orders-db-prod` |
| Service binding | Quyền truy cập của một consumer đối với instance | Credential riêng cho `orders-api` |

Quan hệ thường gặp:

~~~mermaid
flowchart TD
    S["Service: PostgreSQL"] --> P["Plan: Production"]
    P --> I["Instance: orders-db-prod"]
    I --> B1["Binding: orders-api"]
    I --> B2["Binding: billing-worker"]
    B1 --> C1["Credential A / quyền A"]
    B2 --> C2["Credential B / quyền B"]
~~~

Một service có thể có nhiều plan. Mỗi lần provision tạo một instance cụ thể từ một service và một plan. Instance đó có thể chưa có binding, có một binding hoặc có nhiều binding tùy khả năng của service và policy của broker.

Binding không tạo ra một service instance mới. Nó tạo một quan hệ tiêu thụ và thông tin truy cập cho instance đã tồn tại. Vì vậy, số lượng binding không nhất thiết bằng số lượng instance hoặc số lượng ứng dụng đã provision dịch vụ.

## 3. Trường bindable trong catalog OSB API

Trong catalog, service definition công bố thuộc tính **bindable** để mô tả khả năng binding. Đây là thuộc tính ở cấp service definition.

Ví dụ:

~~~json
{
  "services": [
    {
      "id": "svc-postgresql",
      "name": "postgresql",
      "description": "PostgreSQL database service",
      "bindable": true,
      "plans": [
        {
          "id": "plan-postgresql-standard",
          "name": "standard",
          "description": "Database cho ứng dụng thông thường"
        }
      ]
    },
    {
      "id": "svc-static-export",
      "name": "static-export",
      "description": "Dịch vụ tạo bản xuất tĩnh",
      "bindable": false,
      "plans": [
        {
          "id": "plan-static-export-basic",
          "name": "basic",
          "description": "Tạo bản xuất theo yêu cầu"
        }
      ]
    }
  ]
}
~~~

Ý nghĩa:

- **bindable = true:** service hỗ trợ service binding. Platform có thể cung cấp thao tác bind cho instance của service; broker phải triển khai luồng tạo và xóa binding theo OSB API.
- **bindable = false:** service không hỗ trợ binding. Platform không nên hiển thị hoặc gửi yêu cầu bind cho instance của service đó. Nếu nhận yêu cầu binding không hợp lệ cho service không bindable, broker phải từ chối theo contract OSB API, thường là HTTP 422 Unprocessable Entity.

`bindable` là metadata công bố khả năng, không phải cơ chế bảo mật. Broker vẫn phải kiểm tra ở server khi nhận request. Không được chỉ dựa vào việc giao diện platform đã ẩn nút bind để cho phép mọi request đi vào backend.

### bindable là thuộc tính cấp service

Trong catalog OSB API, `bindable` được khai báo trên service definition, không phải thuộc tính chuẩn để mỗi plan tự công bố một giá trị bindable độc lập. Do đó, nếu một số plan hỗ trợ binding còn plan khác hoàn toàn không hỗ trợ, thiết kế catalog cần được xem xét cẩn thận.

Có thể lựa chọn:

- Thiết kế các plan trong cùng service với khả năng binding nhất quán.
- Nếu hai nhóm có khả năng và contract binding khác hẳn nhau, cân nhắc tách thành service definition riêng.
- Nếu broker có policy giới hạn binding theo plan hoặc tenant, công bố rõ giới hạn đó trong tài liệu/schema phù hợp và kiểm tra ở server; không giả định platform hiểu được một cờ bindable riêng không có trong contract chuẩn.

Một service có `bindable=true` vẫn có thể từ chối một request cụ thể vì instance chưa sẵn sàng, consumer không có quyền, quota đã hết hoặc parameters không hợp lệ. Các điều kiện này khác với việc service không hỗ trợ binding về mặt capability.

## 4. Điều kiện để một request bind hợp lệ

Khi platform gọi bind, broker nên kiểm tra theo nhiều lớp. Một request thường chỉ được chấp nhận khi đáp ứng các điều kiện sau:

1. **Platform đã được xác thực.** Broker nhận diện được platform caller qua cơ chế bảo mật đã cấu hình.
2. **Service hỗ trợ binding.** Service definition được tham chiếu có `bindable=true`.
3. **Instance tồn tại và thuộc đúng phạm vi.** Instance ID phải được tra cứu trong platform/tenant scope đã xác thực.
4. **Instance đã provision thành công.** Instance ở trạng thái sẵn sàng, không đang provision, deprovision hoặc ở trạng thái lỗi không cho phép bind.
5. **Service ID và plan ID khớp.** Các ID trong request phải tương ứng với service và plan đã lưu cùng instance.
6. **Consumer hợp lệ.** App GUID, bind resource hoặc consumer context phải đáp ứng quy tắc của platform tích hợp.
7. **Policy cho phép.** Tenant, plan, quota và loại consumer được phép sử dụng dịch vụ.
8. **Parameters hợp lệ.** Các tham số binding phải tuân theo schema và allowlist của broker.
9. **Binding ID chưa bị dùng cho một quan hệ mâu thuẫn.** Request lặp cùng nội dung có thể được xử lý idempotent; request khác nội dung cần bị từ chối.

Điều kiện có thể khác theo loại dịch vụ. Ví dụ một PostgreSQL service cần tạo database user, trong khi route service có thể cần route hoặc URL đích. Tuy vậy, xác thực platform, ownership, trạng thái instance và kiểm tra capability vẫn là các bước nền tảng.

## 5. Endpoint bind trong OSB API

Một yêu cầu tạo binding thường được gửi bằng:

~~~http
PUT /v2/service_instances/{instance_id}/service_bindings/{binding_id}?service_id={service_id}&plan_id={plan_id}
~~~

Ví dụ:

~~~http
PUT /v2/service_instances/orders-db-prod/service_bindings/orders-api-binding?service_id=svc-postgresql&plan_id=plan-postgresql-production
X-Broker-API-Version: 2.17
Authorization: Bearer <broker-platform-token>
Content-Type: application/json
~~~

Request body có thể chứa context, bind resource và parameters:

~~~json
{
  "context": {
    "platform": "cloudfoundry",
    "organization_guid": "org-commerce",
    "space_guid": "space-production"
  },
  "bind_resource": {
    "app_guid": "app-orders-api"
  },
  "parameters": {
    "access_mode": "read_write",
    "database_schema": "orders"
  }
}
~~~

Các thành phần:

| Thành phần | Vai trò |
|---|---|
| `instance_id` | Xác định service instance được bind |
| `binding_id` | Định danh lần binding do platform gửi |
| `service_id` | Xác nhận service definition của instance |
| `plan_id` | Xác nhận plan đã provision |
| `context` | Metadata nền tảng hoặc tenant theo hợp đồng tích hợp |
| `bind_resource` | Thông tin consumer/resource cần liên kết, nếu có |
| `parameters` | Tùy chọn của binding trong giới hạn schema |

Trong một số phiên bản hoặc tích hợp cũ, request có thể sử dụng `app_guid` ở vị trí tương thích. Cần theo đúng phiên bản OSB API và platform client; nếu hỗ trợ field cũ, chuẩn hóa về mô hình consumer nội bộ tại adapter.

## 6. Response binding cung cấp gì?

Khi bind thành công, broker trả thông tin cần thiết để platform chuyển cho consumer. Tùy loại dịch vụ và kiểu binding, response có thể chứa:

- **credentials:** thông tin xác thực hoặc cấu hình kết nối như URI, hostname, port, username, password, token.
- **syslog_drain_url:** địa chỉ nhận log trong trường hợp service cung cấp syslog drain.
- **route_service_url:** URL của route service.
- **volume_mounts:** mô tả mount volume nếu service hỗ trợ kiểu binding này.
- **endpoints:** metadata endpoint theo capability và phiên bản API có hỗ trợ.

Ví dụ response credentials cho PostgreSQL:

~~~json
{
  "credentials": {
    "uri": "postgresql://orders_api:secret@db.example.internal:5432/orders",
    "hostname": "db.example.internal",
    "port": 5432,
    "database": "orders",
    "username": "orders_api",
    "password": "<secret>"
  }
}
~~~

Đây là ví dụ minh họa. Broker chỉ trả các field phù hợp với loại binding và contract đã công bố. Không phải mọi binding đều cần trả đủ mọi field; một số kiểu dịch vụ trả route URL hoặc cấu hình khác thay vì credential database.

Thông tin trong response thường được platform lưu hoặc chuyển vào môi trường của ứng dụng, chẳng hạn biến môi trường hoặc Kubernetes Secret do adapter/controller quản lý. Vì vậy, response binding cần được xem là dữ liệu nhạy cảm. Không log nguyên response, không đưa password vào exception và không trả credential của binding khác.

## 7. Một instance có thể có nhiều binding

Khả năng có nhiều binding là một trong những lý do quan trọng để quản lý binding riêng với instance.

Ví dụ instance PostgreSQL `orders-db-prod` được dùng bởi hai consumer:

| Binding | Consumer | Quyền | Credential |
|---|---|---|---|
| `orders-api-binding` | `orders-api` | Read/write trên schema orders | User `orders_api` |
| `billing-worker-binding` | `billing-worker` | Read-only trên dữ liệu cần đối soát | User `billing_worker` |

Mỗi binding có ID, trạng thái, consumer và credential riêng. Nếu `orders-api` bị xóa, broker unbind binding của ứng dụng này, thu hồi user `orders_api`, trong khi `billing-worker` vẫn có thể tiếp tục sử dụng instance.

Không nên mặc định mọi service đều cho phép số lượng binding không giới hạn. Broker có thể áp dụng quota hoặc policy về số consumer, số credential, loại consumer hoặc quyền được cấp. Các giới hạn đó phải được kiểm tra khi tạo binding và phải được lưu để xử lý unbind, audit và retry.

## 8. Vòng đời binding: bind và unbind

Vòng đời thông thường:

~~~mermaid
sequenceDiagram
    participant P as Platform
    participant B as Service Broker
    participant R as Backend
    participant A as Application

    P->>B: PUT service_bindings/{binding_id}
    B->>B: Validate bindable, instance, consumer, policy
    B->>R: Create user / token / permission
    R-->>B: Credential and access reference
    B->>B: Persist binding record
    B-->>P: Binding response
    P-->>A: Deliver connection data
    A->>R: Use service
    P->>B: DELETE service_bindings/{binding_id}
    B->>R: Revoke credential / permission
    R-->>B: Revocation result
    B->>B: Mark binding removed
    B-->>P: Unbind response
~~~

### Bind

Broker tạo quyền hoặc cấu hình cho consumer. Quy trình thường gồm:

1. Xác minh service bindable và instance active.
2. Xác minh ownership và consumer context.
3. Kiểm tra binding ID, quota và parameters.
4. Tạo credential hoặc policy giới hạn ở backend.
5. Lưu binding record và secret reference.
6. Trả response binding cho platform.

Broker nên lưu binding record trước hoặc phối hợp transaction/outbox phù hợp để tránh backend đã tạo user nhưng broker mất dấu. Nếu backend và database không thể cùng transaction, cần có idempotency key hoặc quy trình đối soát/compensation.

### Unbind

Platform gửi:

~~~http
DELETE /v2/service_instances/{instance_id}/service_bindings/{binding_id}?service_id={service_id}&plan_id={plan_id}
~~~

Broker tìm đúng binding, thu hồi credential hoặc quyền ở backend, cập nhật trạng thái và trả response theo contract OSB API. Unbind không deprovision instance và không được thu hồi credential của binding khác.

Nếu backend trả timeout, broker cần đối soát trước khi tạo lại hoặc đánh dấu thất bại. Request unbind lặp phải được xử lý an toàn: nếu credential đã bị thu hồi, lần tiếp theo không được tạo lại quyền hoặc xóa nhầm tài nguyên.

## 9. bindable không thay thế authorization

Một service có `bindable=true` chỉ có nghĩa broker công bố hỗ trợ binding. Nó không có nghĩa mọi caller đều có quyền bind mọi instance.

Ví dụ:

- Tenant A có instance PostgreSQL trong namespace production.
- Một ứng dụng thuộc tenant B gửi request bind với instance ID đoán được.
- Service definition có `bindable=true`.

Broker vẫn phải từ chối vì consumer không thuộc phạm vi được phép. Trường bindable không phải ACL, không phải credential và không phải bằng chứng ownership.

Các kiểm tra bảo mật cần gồm:

- Xác thực platform và kiểm tra principal.
- Ánh xạ instance đến tenant/platform scope đã lưu.
- Xác minh consumer thuộc phạm vi được phép hoặc có quyền chia sẻ.
- Cấp quyền tối thiểu trên backend.
- Dùng credential riêng cho từng binding khi có thể.
- Lưu secret trong secret manager hoặc kho mã hóa.
- Thu hồi quyền đúng binding khi unbind.
- Audit binding/unbinding mà không log secret.

Không dùng `app_guid`, namespace hoặc consumer ID do caller gửi làm bằng chứng xác thực độc lập. Những giá trị này phải được đối chiếu với platform identity và mapping đáng tin cậy.

## 10. Bindability theo loại dịch vụ

Không phải mọi dịch vụ đều cung cấp cùng kiểu binding.

| Loại dịch vụ | Binding có thể tạo | Dữ liệu response thường gặp |
|---|---|---|
| Relational database | Database user, role, schema grant | URI, host, port, database, username, password |
| Cache | ACL user hoặc token | Host, port, username, password, TLS settings |
| Message broker | User và quyền trên queue/topic | Broker URL, credentials, topic/queue metadata |
| Object storage | Access key hoặc policy giới hạn bucket | Endpoint, bucket, access key, secret |
| Syslog service | Đăng ký điểm nhận log | Syslog drain URL |
| Route service | Đăng ký route và target | Route service URL |
| Volume service | Cấp quyền mount hoặc volume attachment metadata | Volume mount metadata |

Một service có thể bindable dù response không phải bộ username/password truyền thống. Khái niệm binding là quan hệ và quy trình cấp quyền/configuration cho consumer; dữ liệu trả về tùy loại dịch vụ.

Một service không bindable có thể vẫn tạo instance hữu ích. Ví dụ broker tạo một bản xuất dữ liệu hoặc chạy một tác vụ xử lý theo yêu cầu, kết quả được lấy qua một quy trình khác đã định nghĩa. Nếu consumer cần thông tin truy cập sau provision, broker phải cung cấp cơ chế phù hợp và công bố rõ liệu nó có được biểu diễn bằng OSB binding hay không.

## 11. Triển khai điều kiện bindable trong Spring Cloud Service Broker

Trong Spring Cloud Service Broker, catalog provider cần công bố đúng giá trị bindable cho service definition. Cách cấu hình cụ thể phụ thuộc phiên bản thư viện và cách ứng dụng xây dựng catalog.

Ở tầng nghiệp vụ, nên có một policy service tập trung:

~~~java
public void assertBindingAllowed(
        ServiceInstance instance,
        ServiceDefinition service,
        AuthenticatedPlatform platform,
        ConsumerReference consumer) {

    if (!service.isBindable()) {
        throw new ServiceNotBindableException();
    }

    if (!instance.isActive()) {
        throw new ServiceInstanceNotReadyException();
    }

    ownershipPolicy.assertConsumerCanAccess(
        platform,
        instance,
        consumer
    );

    bindingQuota.assertAvailable(instance.tenantId());
}
~~~

Đây là pseudocode minh họa; tên getter và kiểu model cần điều chỉnh theo phiên bản Spring Cloud Service Broker. Ý nghĩa là không chỉ dựa vào catalog, mà kiểm tra lại capability và policy ngay trước khi tạo binding.

Một service xử lý binding có thể triển khai abstraction tương ứng của framework, thường là `ServiceInstanceBindingService`, với các phương thức tạo và xóa binding. Request adapter được chuyển thành command nội bộ, domain service thực hiện kiểm tra và gọi backend adapter, sau đó framework response được tạo từ kết quả.

Cấu trúc package tham khảo:

~~~text
broker/
  catalog/
    ServiceCatalogConfiguration
  binding/
    ServiceInstanceBindingServiceImpl
    BindingCommand
    BindingPolicyService
    BindingCredentialService
    BindingRepository
  instance/
    ServiceInstanceRepository
  backend/
    DatabaseBindingAdapter
    CacheBindingAdapter
    MessagingBindingAdapter
  security/
    OwnershipPolicy
    SecretStore
~~~

Không nên đặt logic cấp user/role, kiểm tra tenant và lưu credential trực tiếp trong controller. Dùng domain service giúp các luồng đồng bộ, bất đồng bộ và retry áp dụng cùng một policy.

## 12. Mô hình lưu trữ binding

Một binding record có thể lưu:

| Field | Mục đích |
|---|---|
| internal_binding_id | Khóa nội bộ của broker |
| platform_id | Nền tảng tạo binding |
| binding_id | Định danh binding từ OSB request |
| instance_id | Instance được liên kết |
| tenant_id | Ownership đã xác minh |
| consumer_id | Ứng dụng/workload sử dụng dịch vụ |
| binding_state | Trạng thái tạo, active, unbinding hoặc revoked |
| backend_principal_id | User/role/token reference ở backend |
| secret_reference | Tham chiếu đến secret store |
| request_fingerprint | Nhận diện request bind lặp |
| created_at / updated_at | Audit và quản lý vòng đời |

Không lưu password/token dạng plaintext trong binding table nếu có thể lưu secret trong secret manager. Binding record chỉ cần giữ secret reference và metadata không nhạy cảm cần cho việc thu hồi.

Unique key cần phản ánh phạm vi ID của platform, ví dụ `(platform_id, instance_id, binding_id)` nếu hợp đồng cho phép binding ID trùng giữa các platform. Dùng foreign key hoặc invariant nghiệp vụ để bảo đảm binding luôn tham chiếu đến đúng instance.

## 13. Idempotency khi bind

Platform có thể retry bind khi response bị mất. Broker cần phân biệt request lặp cùng nội dung với request mâu thuẫn.

| Trạng thái binding | Request mới | Hành vi |
|---|---|---|
| Chưa tồn tại | Binding hợp lệ | Tạo binding và credential |
| Đang tạo | Cùng ID và fingerprint | Trả operation/kết quả đang có |
| Đã active | Cùng ID và fingerprint | Trả kết quả đã lưu theo contract |
| ID tồn tại | Consumer hoặc parameters khác | Báo conflict, không ghi đè |
| Đang unbind/revoked | Request bind lặp cũ | Áp dụng policy generation/lifecycle; không tự hồi sinh credential |

Nếu backend tạo credential thành công nhưng response bị mất, broker cần dùng idempotency key hoặc tìm principal theo binding ID/tag trước khi tạo credential mới. Nếu backend không hỗ trợ idempotency, cần lưu correlation ID và có quy trình đối soát để tránh tạo nhiều user cho một binding.

Fingerprint cần được tính từ request đã chuẩn hóa, bao gồm platform scope, instance, binding ID, consumer identity và parameters có ảnh hưởng đến quyền. Không đưa secret thô vào log hoặc fingerprint có thể bị quan sát.

## 14. Xử lý lỗi bindability và lỗi binding

Các trường hợp thường gặp:

| Tình huống | Cách xử lý |
|---|---|
| Service có `bindable=false` | Từ chối bind theo OSB API, thường là 422 |
| Instance chưa provision xong | Từ chối hoặc yêu cầu platform thử lại theo contract |
| Service/plan ID không khớp | Từ chối, không cấp credential |
| Caller không có ownership | Từ chối mà không tiết lộ instance của tenant khác |
| Consumer context không hợp lệ | Từ chối request |
| Binding parameters sai schema | Trả lỗi validation |
| Quota binding đã hết | Từ chối theo policy/quota |
| Backend tạo credential lỗi | Không trả binding thành công; lưu trạng thái và cleanup nếu tạo một phần |
| Request bind bị gửi lặp | Replay kết quả hoặc operation hiện tại |
| Backend timeout sau khi tạo credential | Reconcile trước khi tạo lại |

Lỗi `bindable=false` là lỗi capability của service. Lỗi tenant không có quyền, instance chưa sẵn sàng hoặc parameters sai là các lỗi khác. Không gộp tất cả thành một thông báo chung khiến platform và người vận hành khó xác định nguyên nhân.

## 15. Khi nào không nên công bố bindable?

Một service nên có `bindable=false` khi quy trình sản phẩm không có thao tác liên kết consumer theo mô hình OSB binding. Ví dụ, service chỉ tạo một artifact hoặc chạy một tác vụ theo yêu cầu, kết quả được lấy qua một API hoặc workflow khác đã định nghĩa.

Không nên đặt `bindable=false` chỉ vì:

- Broker chưa hoàn thiện code binding nhưng sản phẩm thực sự cần binding.
- Việc tạo credential khó triển khai.
- Chỉ có một consumer hiện tại.
- Muốn bỏ qua quản lý quyền truy cập.
- Muốn tránh viết thao tác unbind.

Nếu service cần ứng dụng truy cập tài nguyên qua credential hoặc cần đăng ký consumer, hãy triển khai binding và unbinding đúng contract. Nếu service thực sự không có khái niệm consumer binding, công bố false và cung cấp cơ chế sử dụng khác rõ ràng.

Với service có `bindable=true`, broker phải duy trì khả năng bind nhất quán trong suốt vòng đời các instance được tạo. Thay đổi metadata catalog cần được cân nhắc với instance hiện hữu và platform đã lưu lựa chọn trước đó.

## 16. Kiểm thử bindable và service binding

Kiểm thử cần xác nhận cả metadata catalog lẫn hành vi server:

| Trường hợp | Đầu vào | Kết quả mong đợi |
|---|---|---|
| Catalog bindable | Service hỗ trợ binding | Catalog trả `bindable=true` |
| Catalog không bindable | Service không hỗ trợ binding | Catalog trả `bindable=false` |
| Bind service không bindable | Request PUT binding | Trả 422 theo contract, không gọi backend |
| Bind instance active | Service bindable, consumer hợp lệ | Tạo binding và trả response |
| Bind instance provisioning | Instance chưa sẵn sàng | Từ chối theo state policy |
| Bind sai service/plan | ID không khớp instance | Từ chối, không tạo credential |
| Bind sai tenant | Caller không có quyền | Từ chối, không lộ dữ liệu |
| Bind parameters sai | Field lạ hoặc sai kiểu | Validation error, không gọi backend |
| Nhiều consumer | Hai binding ID khác nhau | Hai binding độc lập, credential riêng |
| Bind retry | Cùng ID và nội dung | Không tạo credential trùng |
| Binding ID conflict | Cùng ID nhưng consumer khác | Conflict |
| Unbind một consumer | Hai binding đang active | Chỉ thu hồi binding được chỉ định |
| Unbind retry | Credential đã thu hồi | Hoàn tất idempotent, không ảnh hưởng binding khác |
| Backend timeout | Credential có thể đã tạo | Reconcile trước khi tạo lại |
| Secret handling | Response có password/token | Không log secret, lưu đúng secret reference |

Nên có unit test cho `BindingPolicyService`, integration test cho endpoint OSB và repository, cùng test adapter backend để xác nhận credential được tạo/thu hồi đúng binding. Test catalog riêng để tránh tình trạng server hỗ trợ binding nhưng catalog công bố false hoặc catalog công bố true trong khi handler không hoạt động.

## 17. Những lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Coi bindable là authorization | Caller không hợp lệ có thể truy cập instance | Xác thực và kiểm tra ownership ở server |
| Gộp binding với instance | Unbind một app có thể làm hỏng app khác | Lưu binding riêng theo consumer |
| Service khai báo bindable nhưng không có handler | Platform gửi request nhưng broker không xử lý được | Triển khai cả bind và unbind |
| Chỉ ẩn nút bind ở UI | Request trực tiếp vẫn có thể đến broker | Kiểm tra bindable server-side |
| Dùng chung credential cho mọi app | Không thể thu hồi quyền riêng lẻ | Credential riêng theo binding |
| Chỉ xóa binding record | Backend user/token vẫn còn hiệu lực | Thu hồi quyền trước khi đánh dấu revoked |
| Tin app_guid do caller gửi | Có thể liên kết nhầm consumer | Xác minh context với platform identity |
| Không xử lý request lặp | Tạo nhiều user/credential | Fingerprint và idempotency |
| Công bố bindable khác nhau tùy plan nhưng không có contract rõ | Platform hiểu sai khả năng của service | Giữ capability cấp service nhất quán hoặc tách service |
| Log response binding | Lộ credential | Redaction và secret store |

## 18. Nguyên tắc cần ghi nhớ

Service binding là quan hệ giữa một service instance và consumer cần sử dụng instance đó. Trường `bindable` trong catalog cho platform biết service có hỗ trợ quy trình binding theo OSB API hay không. Khi giá trị là true, broker cần có khả năng tạo và thu hồi binding; khi false, broker phải từ chối yêu cầu bind theo contract.

Khi triển khai trong Spring Cloud Service Broker, hãy giữ các nguyên tắc:

- Service và plan mô tả lựa chọn dịch vụ; instance là tài nguyên đã provision; binding là quyền truy cập của consumer.
- `bindable` được công bố ở cấp service definition.
- `bindable=true` không thay thế xác thực, authorization, ownership hoặc kiểm tra trạng thái instance.
- Bind chỉ thực hiện khi instance sẵn sàng, service/plan khớp và consumer được phép.
- Mỗi binding có ID, consumer, state và credential/secret reference riêng.
- Response binding chỉ trả thông tin kết nối phù hợp với loại dịch vụ.
- Unbind thu hồi đúng quyền của binding; deprovision mới thu hồi instance.
- Request lặp cần được xử lý idempotent; ID trùng nội dung khác phải bị từ chối.
- Secret không được ghi vào log hoặc lưu plaintext không cần thiết.
- Catalog, binding handler và unbind handler phải công bố và thực thi cùng một capability.

Khi tách rõ bindability, quyền truy cập và vòng đời tài nguyên, broker có thể phục vụ nhiều consumer trên cùng một instance, thu hồi từng quyền độc lập và tích hợp nhất quán với Cloud Foundry hoặc adapter Kubernetes.

