# CreateServiceInstanceResponse, dashboard_url và metadata được hỗ trợ

## Bối cảnh

Trong Open Service Broker API (OSB API), Platform gửi yêu cầu provision để broker tạo một service instance theo `service_id`, `plan_id` và các tham số đã chọn. Sau khi xử lý, broker phải trả response đúng hợp đồng để Platform biết instance đã được tạo, thao tác còn chạy nền hay request đang tham chiếu tới một instance đã tồn tại.

Trong Spring Cloud Open Service Broker, `CreateServiceInstanceResponse` là kiểu kết quả mà ứng dụng broker trả về từ xử lý tạo service instance. Framework dùng kết quả này để tạo HTTP response theo OSB API. Các thông tin thường cần quan tâm gồm:

- `dashboard_url`: URL để người dùng truy cập giao diện quản trị của service instance, nếu broker cung cấp dashboard.
- `async` và `operation`: cho biết thao tác được chấp nhận xử lý bất đồng bộ và mã để Platform theo dõi operation.
- `instanceExisted`: biểu thị trường hợp provision lặp hợp lệ mà instance đã tồn tại, khi được hỗ trợ bởi phiên bản thư viện đang dùng.

Một điểm quan trọng là `metadata` trong catalog không đồng nghĩa với metadata tùy ý trong response provision. OSB API định nghĩa metadata cho service và plan nhằm mô tả sản phẩm. `CreateServiceInstanceResponse` chủ yếu mô tả kết quả của thao tác provision; không nên tự thêm trường JSON không thuộc schema response và kỳ vọng mọi Platform đều hiểu hoặc lưu lại.

## 1. Vai trò của CreateServiceInstanceResponse

`CreateServiceInstanceResponse` là kết quả ở ranh giới giữa service nghiệp vụ và HTTP controller/framework. Service xử lý việc cấp phát, lưu trạng thái và gọi provider. Khi hoàn tất hoặc quyết định chuyển sang xử lý nền, service trả một response object. Framework dựa trên object đó để chọn HTTP status và serialize body theo OSB API.

Luồng tổng quát:

~~~mermaid
sequenceDiagram
    participant P as Platform
    participant C as OSB Controller
    participant S as ServiceInstanceService
    participant R as Repository
    participant I as Infrastructure Adapter

    P->>C: PUT /v2/service_instances/{instance_id}
    C->>S: CreateServiceInstanceRequest
    S->>R: Kiểm tra instance và idempotency
    S->>I: Provision tài nguyên
    I-->>S: Resource result
    S->>R: Lưu trạng thái instance
    S-->>C: CreateServiceInstanceResponse
    C-->>P: 201 Created + response body
~~~

Controller không nên tự tạo dashboard URL, tự quyết định operation ID hoặc tự gọi provider. Những giá trị này phải đến từ service nghiệp vụ hoặc một thành phần chuyên trách được service điều phối. Controller/framework chịu trách nhiệm chuyển kết quả sang HTTP.

## 2. Response đồng bộ và dashboard_url

Khi broker hoàn tất provision trong thời gian xử lý request, Platform nhận response `201 Created`. Nếu broker cung cấp giao diện quản trị cho instance, body có thể chứa `dashboard_url`.

Ví dụ response:

~~~http
HTTP/1.1 201 Created
Content-Type: application/json

{
  "dashboard_url": "https://console.example.com/services/db-instance-42"
}
~~~

`dashboard_url` là URL mà người dùng có thể mở để xem hoặc quản lý service instance thông qua dashboard của nhà cung cấp. URL này có thể dẫn tới trang chi tiết instance, trang quản trị database hoặc giao diện điều khiển dịch vụ tương ứng.

Broker không bắt buộc phải có dashboard. Nếu sản phẩm không cung cấp giao diện như vậy, có thể bỏ trường này khỏi response. Không trả chuỗi rỗng, URL giả hoặc một địa chỉ không thể truy cập chỉ để lấp đầy response.

### Yêu cầu thiết kế dashboard URL

- **Đúng instance:** URL phải trỏ tới đúng service instance mà Platform vừa provision.
- **Có thể truy cập:** hostname, route và TLS phải hoạt động từ môi trường mà người dùng sử dụng.
- **Không chứa bí mật:** không nhúng password, access token, connection string hoặc credential dài hạn vào query string hay path.
- **Có xác thực riêng:** dashboard tự thực hiện đăng nhập hoặc kiểm tra quyền. Biết URL không đồng nghĩa với được quyền quản trị instance.
- **Ổn định:** nếu dashboard URL được lưu lại bởi Platform, URL nên tiếp tục trỏ tới instance trong vòng đời mà broker hỗ trợ; khi đổi domain hoặc route cần có kế hoạch chuyển tiếp.
- **Không thay thế binding:** URL dashboard dành cho giao diện người dùng, còn thông tin kết nối ứng dụng được trả qua service binding theo hợp đồng riêng.

Ví dụ trong Spring Cloud Open Service Broker:

~~~java
return CreateServiceInstanceResponse.builder()
        .dashboardUrl("https://console.example.com/services/" + instanceId)
        .build();
~~~

Đây là ví dụ minh họa API builder; cần đối chiếu chữ ký chính xác với phiên bản dependency đang sử dụng. `instanceId` phải được mã hóa an toàn khi đưa vào URL path, và dashboard phải kiểm tra quyền người dùng ở phía server.

### Dashboard URL và thông tin kết nối

Không dùng `dashboard_url` để chuyển endpoint database, username hoặc password cho ứng dụng. Các thông tin kết nối thuộc response của thao tác tạo binding. Dashboard URL phục vụ người dùng hoặc operator; binding credentials phục vụ ứng dụng tiêu thụ dịch vụ.

| Thông tin | Nơi trả về | Người/Thành phần sử dụng |
|---|---|---|
| URL dashboard | Provision response (`dashboard_url`) | Người dùng hoặc operator |
| Database host, port, database name | Binding response (`credentials` hoặc cấu trúc binding phù hợp) | Ứng dụng |
| Username/password hoặc token kết nối | Binding response, được bảo vệ như secret | Ứng dụng |
| Service/plan display name, icon, mô tả | Catalog metadata | Platform UI và người dùng khi chọn dịch vụ |

## 3. Response bất đồng bộ và operation

Một số thao tác provision cần tạo hạ tầng lâu hơn timeout HTTP, chẳng hạn tạo database cluster, cấp namespace, cấu hình network hoặc chờ provider hoàn tất. Khi Platform cho phép incomplete operation qua query `accepts_incomplete=true`, broker có thể nhận request, lưu operation và tiếp tục xử lý ở worker.

Trong trường hợp này, broker trả `202 Accepted`. Trường `operation` là mã tham chiếu để Platform gửi các request `last_operation` tiếp theo. Mã operation thường là một chuỗi opaque do broker quản lý; Platform không nên suy diễn cấu trúc nội bộ của nó.

Ví dụ:

~~~http
HTTP/1.1 202 Accepted
Content-Type: application/json

{
  "operation": "provision-7f31a9"
}
~~~

Luồng xử lý:

1. Broker xác thực request, kiểm tra service/plan, tenant và tính idempotent.
2. Broker ghi instance ở trạng thái `PROVISIONING` và tạo operation bền vững.
3. Broker ghi sự kiện outbox hoặc đưa công việc vào cơ chế điều phối đã được bảo đảm.
4. Broker trả `202 Accepted` cùng operation ID theo response contract.
5. Worker gọi provider, cập nhật trạng thái và lưu kết quả.
6. Platform gọi `GET /v2/service_instances/{instance_id}/last_operation` để đọc tiến trình.
7. Khi operation kết thúc, Platform nhận `succeeded` hoặc `failed` theo hợp đồng OSB API.

Ví dụ Spring:

~~~java
return CreateServiceInstanceResponse.builder()
        .async(true)
        .operation(operationId)
        .build();
~~~

Không đặt `async(true)` chỉ vì service sử dụng `Mono`, `CompletableFuture` hoặc một thread pool. Reactive/non-blocking mô tả cách thực thi I/O; OSB asynchronous operation mô tả hợp đồng HTTP trong đó công việc tiếp tục sau response ban đầu. Nếu thao tác đã hoàn tất trước khi trả response, hãy trả kết quả đồng bộ phù hợp.

### Khi nào cần operation ID?

Operation ID hữu ích khi Platform cần theo dõi một công việc có thể kéo dài sau request ban đầu. Mã này phải:

- Duy nhất trong phạm vi mà broker dùng để tra cứu operation.
- Được lưu bền vững cùng `instance_id` và loại operation.
- Không tiết lộ credential, tenant secret hoặc thông tin nội bộ nhạy cảm.
- Có thể được dùng an toàn trong request `last_operation`.
- Gắn với trạng thái cuối cùng và thông tin lỗi đã chuẩn hóa.

Nếu broker xử lý đồng bộ, không cần tạo operation giả chỉ để trả một chuỗi trong response. Nếu xử lý bất đồng bộ, không trả `202` mà không có khả năng tra cứu trạng thái và phục hồi công việc.

## 4. Provision lặp và instanceExisted

Platform có thể gửi lại request provision sau timeout hoặc mất kết nối. Broker phải phân biệt hai trường hợp:

1. Instance đã tồn tại với cùng ý định provision, request mới là retry hợp lệ.
2. Instance đã tồn tại nhưng service, plan hoặc tham số khác với request mới.

Với trường hợp đầu, broker cần trả kết quả phù hợp theo quy tắc idempotency của OSB API. Với trường hợp thứ hai, broker trả `409 Conflict` vì cùng `instance_id` đang đại diện cho một cấu hình khác.

Một số phiên bản Spring Cloud Open Service Broker hỗ trợ cờ `instanceExisted` trên `CreateServiceInstanceResponse` để framework biểu diễn trường hợp instance đã tồn tại. Ví dụ minh họa:

~~~java
return CreateServiceInstanceResponse.builder()
        .dashboardUrl(existing.dashboardUrl())
        .instanceExisted(true)
        .build();
~~~

Kiểm tra API của dependency thực tế trước khi dùng builder method này. Cờ `instanceExisted` không thay thế việc kiểm tra dữ liệu. Broker vẫn phải so sánh fingerprint của service ID, plan ID, tenant và parameters đã chuẩn hóa để xác nhận request lặp có cùng ý định.

Một cách xử lý khái quát:

~~~java
var existing = repository.findByPlatformAndInstanceId(platformId, instanceId);

if (existing != null) {
    if (!existing.requestFingerprint().equals(requestFingerprint)) {
        throw new ServiceInstanceAlreadyExistsException(instanceId);
    }

    return CreateServiceInstanceResponse.builder()
            .dashboardUrl(existing.dashboardUrl())
            .instanceExisted(true)
            .build();
}
~~~

Đoạn mã trên là pseudocode để giải thích quy tắc; tên exception, repository và builder method phụ thuộc phiên bản framework và cách tổ chức ứng dụng. Việc tạo instance mới cần được bảo vệ bằng unique constraint hoặc thao tác insert có kiểm soát để hai request đồng thời không cùng tạo tài nguyên.

## 5. Metadata được hỗ trợ trong OSB API

OSB API có trường `metadata` trong mô hình catalog để broker cung cấp thông tin mô tả service và plan. Metadata này giúp Platform hiển thị danh mục dễ hiểu hơn, ví dụ tên hiển thị, hình ảnh, mô tả dài, nhà cung cấp, tài liệu và chi phí.

Các key phổ biến trong metadata catalog gồm:

| Key | Ý nghĩa |
|---|---|
| `displayName` | Tên thân thiện để hiển thị |
| `imageUrl` | URL hình ảnh đại diện cho service hoặc plan |
| `longDescription` | Mô tả chi tiết hơn so với trường `description` ngắn |
| `providerDisplayName` | Tên nhà cung cấp hiển thị |
| `documentationUrl` | URL tài liệu hướng dẫn |
| `supportUrl` | URL trang hỗ trợ |
| `bullets` | Danh sách điểm nổi bật |
| `costs` | Thông tin chi phí theo cấu trúc schema được OSB API định nghĩa |
| `shareable` | Thông tin về khả năng chia sẻ service instance theo mô hình được hỗ trợ |

Ví dụ metadata trên một service plan trong catalog:

~~~json
{
  "id": "postgres-standard",
  "name": "standard",
  "description": "Managed PostgreSQL for general workloads",
  "free": false,
  "metadata": {
    "displayName": "PostgreSQL Standard",
    "imageUrl": "https://assets.example.com/catalog/postgres.png",
    "longDescription": "A managed PostgreSQL plan for production applications.",
    "providerDisplayName": "Example Cloud",
    "documentationUrl": "https://docs.example.com/postgres",
    "supportUrl": "https://support.example.com",
    "bullets": [
      "Automated backups",
      "Managed patching",
      "Private network connectivity"
    ]
  }
}
~~~

Metadata có thể được đặt ở service hoặc plan theo schema catalog. Các key chuẩn giúp Platform UI có thể hiểu và hiển thị nhất quán. Một số Platform có thể bỏ qua key không biết; do đó metadata mở rộng không được dùng làm kênh truyền dữ liệu bắt buộc cho logic provision.

### Metadata không phải response provision tùy ý

Không nhầm `metadata` trong catalog với body của `CreateServiceInstanceResponse`:

| Dữ liệu | Vị trí hợp đồng | Mục đích |
|---|---|---|
| `metadata.displayName`, `metadata.imageUrl`, `metadata.bullets` | Service/plan trong `GET /v2/catalog` | Mô tả sản phẩm khi người dùng chọn plan |
| `dashboard_url` | Response của provision | Mở dashboard quản trị instance |
| `operation` | Response bất đồng bộ | Theo dõi công việc provision |
| `credentials` | Response tạo binding | Cấp thông tin kết nối cho ứng dụng |
| `parameters` | Request provision/update | Cấu hình riêng cho instance |
| `context` | Request từ Platform | Ngữ cảnh nền tảng hoặc tenant |

OSB API không định nghĩa một trường `metadata` tùy ý trong response provision chuẩn để broker gửi mọi thuộc tính nội bộ của instance. Nếu cần lưu metadata riêng như region thực tế, provider resource ID hoặc phiên bản engine, hãy lưu trong database của broker hoặc metadata của tài nguyên provider. Chỉ đưa dữ liệu ra ngoài qua trường OSB API được định nghĩa rõ và có mục đích phù hợp.

Không đưa credential, token, password hoặc connection string vào catalog metadata. Catalog thường được nhiều thành phần đọc và có thể được cache; bí mật chỉ được trả cho caller có quyền trong luồng binding thích hợp.

## 6. Mapping sang Spring Cloud Open Service Broker

Spring Cloud Open Service Broker cung cấp abstraction để ứng dụng triển khai service instance lifecycle. Trong luồng create, service implementation nhận request model và trả `CreateServiceInstanceResponse` hoặc kiểu reactive tương ứng tùy stack ứng dụng.

Ví dụ service đồng bộ rút gọn:

~~~java
@Service
class DatabaseServiceInstanceService implements ServiceInstanceService {

    private final ProvisioningService provisioningService;

    DatabaseServiceInstanceService(ProvisioningService provisioningService) {
        this.provisioningService = provisioningService;
    }

    @Override
    public CreateServiceInstanceResponse createServiceInstance(
            CreateServiceInstanceRequest request) {

        var result = provisioningService.provision(
                request.getServiceInstanceId(),
                request.getServiceDefinitionId(),
                request.getPlanId(),
                request.getParameters(),
                request.getContext());

        return CreateServiceInstanceResponse.builder()
                .dashboardUrl(result.dashboardUrl())
                .build();
    }
}
~~~

Đây là ví dụ định hướng; method signature và request accessor có thể khác theo phiên bản thư viện. Mục tiêu là giữ việc gọi provider, lưu trạng thái và tạo dashboard URL trong application service, còn implementation OSB chuyển kết quả sang response type của framework.

### Ranh giới trách nhiệm

| Thành phần | Trách nhiệm |
|---|---|
| `ServiceInstanceService` implementation | Nhận request model và trả response model |
| Provisioning application service | Kiểm tra plan, parameters, tenant, idempotency và trạng thái |
| Repository | Lưu instance, fingerprint, dashboard URL và operation |
| Infrastructure adapter | Tạo tài nguyên trên database provider hoặc Kubernetes |
| Catalog service/configuration | Công bố metadata của service và plan |
| Spring Cloud Open Service Broker | Ánh xạ response model thành HTTP status/body OSB API |

Không tạo controller thủ công trùng với endpoint do framework quản lý. Nếu framework có sẵn cơ chế serialize response, hãy trả đúng response type thay vì tự tạo JSON hoặc set status ở service.

## 7. Lỗi và response không thành công

Nếu provision thất bại, broker không trả một `CreateServiceInstanceResponse` giả vờ thành công. Hãy chuyển lỗi nghiệp vụ thành lỗi OSB API phù hợp để Platform hiểu và có thể retry hoặc báo người dùng.

Các trường hợp thường gặp:

| Tình huống | Response thường dùng | Ý nghĩa |
|---|---|---|
| Request không hợp lệ hoặc thiếu dữ liệu | `400 Bad Request` | Platform cần sửa request |
| Caller không được xác thực | `401 Unauthorized` | Kiểm tra credential |
| Caller không có quyền | `403 Forbidden` | Kiểm tra authorization |
| Service hoặc plan không tồn tại | `404 Not Found` theo điều kiện endpoint | Catalog hoặc ID không hợp lệ |
| Instance ID đã tồn tại với cấu hình khác | `409 Conflict` | Không thể tạo instance trùng ID |
| Provider tạm thời không sẵn sàng | `5xx` hoặc lỗi phù hợp theo hợp đồng và retry policy | Có thể cần thử lại |

Không trả `201 Created` nếu provider mới chỉ nhận lệnh mà chưa hoàn tất provision đồng bộ. Nếu broker đã chấp nhận xử lý nền hợp lệ, dùng `202 Accepted` và operation để theo dõi. Nếu worker thất bại sau đó, trạng thái `last_operation` phải phản ánh `failed` cùng mô tả đã chuẩn hóa.

Error description không được tiết lộ stack trace, SQL, credential, nội dung secret hoặc địa chỉ nội bộ. Log nội bộ có thể giữ provider error code và trace ID để điều tra với quyền truy cập phù hợp.

## 8. Bảo mật dashboard và metadata

Dashboard URL và catalog metadata thường được lưu hoặc hiển thị bởi Platform. Vì vậy, cần xem chúng là dữ liệu có thể đi qua nhiều thành phần:

- Chỉ trả dashboard URL khi broker thực sự cung cấp dashboard và URL được tạo từ nguồn tin cậy.
- Không ghép host từ header `Host` chưa được xác thực hoặc từ input tùy ý của người dùng.
- Dùng allowlist hostname hoặc cấu hình base URL đáng tin cậy để tạo link.
- Không tạo URL chứa bearer token dài hạn hoặc mật khẩu trong query string.
- Dashboard tự xác thực và phân quyền; có thể yêu cầu đăng nhập SSO hoặc luồng token ngắn hạn an toàn.
- Metadata catalog chỉ chứa thông tin công khai, không chứa secret hoặc dữ liệu tenant-specific.
- Kiểm tra URL hình ảnh và tài liệu để tránh công bố link không tin cậy hoặc nội dung không phù hợp.
- Không ghi response body chứa dữ liệu nhạy cảm vào log một cách mặc định.

Nếu URL dashboard có token dùng một lần, cần thiết kế thời hạn ngắn, giới hạn phạm vi và cơ chế thu hồi; tuy nhiên, cách an toàn hơn thường là URL ổn định tới dashboard có xác thực độc lập.

## 9. Kiểm thử CreateServiceInstanceResponse

Kiểm thử nên xác nhận cả response object của framework lẫn HTTP response cuối cùng mà Platform nhìn thấy.

| Ca kiểm thử | Điều cần xác minh |
|---|---|
| Provision đồng bộ có dashboard | HTTP `201`; `dashboard_url` đúng instance |
| Broker không có dashboard | Response không chứa URL giả hoặc rỗng |
| Provision bất đồng bộ | HTTP `202`; operation ID được trả và lưu bền vững |
| Platform polling operation | Trạng thái `in progress`, `succeeded`, `failed` đúng với worker |
| Retry cùng request | Không tạo tài nguyên lần hai; trả kết quả idempotent phù hợp |
| Cùng ID nhưng parameters khác | Trả conflict theo hợp đồng |
| Metadata catalog | Metadata nằm ở service/plan và serialize đúng schema |
| Provision response | Không có trường metadata tùy ý ngoài hợp đồng |
| Dashboard URL | HTTPS, đúng host, không chứa credential |
| Provider thất bại | Không trả response thành công và không ghi instance thành READY |

Nên dùng integration test qua HTTP endpoint thực của Spring Cloud Open Service Broker để kiểm tra mapping status/body. Unit test có thể kiểm tra application service, fingerprint và cách tạo dashboard URL. Adapter test xác nhận provider resource ID và trạng thái được chuẩn hóa trước khi lưu.

## 10. Checklist triển khai

- [ ] `CreateServiceInstanceResponse` chỉ biểu diễn kết quả provision theo hợp đồng OSB API.
- [ ] Provision hoàn tất đồng bộ trả status/body phù hợp.
- [ ] Provision bất đồng bộ chỉ trả `202` khi Platform chấp nhận incomplete operation.
- [ ] Operation ID được lưu bền vững và có thể truy vấn qua `last_operation`.
- [ ] `dashboard_url` chỉ xuất hiện khi broker thực sự có dashboard.
- [ ] Dashboard URL đúng instance, ổn định, dùng HTTPS và không chứa secret.
- [ ] Dashboard tự xác thực và kiểm tra quyền truy cập.
- [ ] Provision retry được xử lý idempotent; cấu hình khác nhau trả conflict.
- [ ] `instanceExisted` chỉ được dùng nếu phiên bản framework hỗ trợ và điều kiện idempotency đã được xác minh.
- [ ] Metadata công khai được đặt ở service/plan catalog theo schema OSB API.
- [ ] Không thêm metadata tùy ý vào response provision và không dùng metadata để truyền credential.
- [ ] Có integration test xác nhận response HTTP thực tế và các nhánh lỗi.

## Kết luận

`CreateServiceInstanceResponse` là hợp đồng kết quả provision giữa service implementation và Spring Cloud Open Service Broker. `dashboard_url` cung cấp đường dẫn tới giao diện quản trị instance nếu broker có dashboard; `operation` hỗ trợ theo dõi provision bất đồng bộ; `instanceExisted` có thể biểu diễn trường hợp provision lặp theo khả năng của phiên bản thư viện. Metadata mô tả service và plan thuộc catalog, không phải một túi dữ liệu tùy ý trong response provision. Khi tách đúng các loại dữ liệu, kiểm tra idempotency và bảo vệ dashboard, broker có thể trả kết quả nhất quán cho Cloud Foundry, Kubernetes và các Platform OSB API khác.
