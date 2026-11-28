# Luồng xử lý từ HTTP request đến dịch vụ nghiệp vụ và HTTP response

## Bối cảnh và mục tiêu

Trong một service broker tuân theo Open Service Broker API (OSB API), nền tảng như Cloud Foundry hoặc một hệ thống tích hợp Kubernetes gọi broker qua HTTP để khám phá catalog, cấp phát service instance, thay đổi plan, thu hồi instance hoặc tạo binding cho ứng dụng. Broker tiếp nhận hợp đồng HTTP chuẩn hóa đó, chuyển yêu cầu thành hành động nghiệp vụ, điều phối hệ thống cung cấp tài nguyên và trả kết quả theo đúng hợp đồng OSB API.

Luồng xử lý cần có ranh giới rõ ràng giữa bốn trách nhiệm:

1. **Lớp HTTP và bảo vệ đầu vào** tiếp nhận kết nối, xác thực, định tuyến, kiểm tra header và giải mã request.
2. **Lớp điều khiển OSB API** hiểu endpoint, cấu trúc request/response và mã trạng thái HTTP; nó chuyển request thành lời gọi dịch vụ phù hợp.
3. **Lớp nghiệp vụ** quyết định broker phải làm gì, kiểm tra trạng thái instance, chính sách, plan, quyền sở hữu và tính idempotent của thao tác.
4. **Lớp tích hợp hạ tầng** chuyển ý định nghiệp vụ thành lời gọi tới Kubernetes, Cloud Foundry hoặc hệ thống cung cấp tài nguyên khác.

Trong Spring Cloud Open Service Broker, framework cung cấp các thành phần HTTP và hợp đồng dịch vụ để ứng dụng broker triển khai. Ứng dụng tập trung hiện thực các service như `CatalogService`, `ServiceInstanceService` và `ServiceInstanceBindingService`, đồng thời bổ sung repository, hàng đợi và adapter hạ tầng theo nhu cầu. Cách phân lớp này giúp chi tiết của HTTP không tràn vào nghiệp vụ và chi tiết của nhà cung cấp không làm thay đổi hợp đồng OSB API.

## Bức tranh tổng thể

Một request đi từ nền tảng qua lớp mạng và HTTP, được ánh xạ thành request object, đi qua service nghiệp vụ, có thể gọi adapter hạ tầng, rồi quay lại thành HTTP response. Ví dụ dưới đây mô tả thao tác cấp phát service instance; nhánh đồng bộ và bất đồng bộ có điểm kết thúc HTTP khác nhau.

~~~mermaid
sequenceDiagram
    autonumber
    participant P as Nền tảng CF/Kubernetes
    participant G as Ingress hoặc API Gateway
    participant H as Spring Boot HTTP stack
    participant C as OSB Controller
    participant S as Service nghiệp vụ
    participant DB as Repository
    participant Q as Outbox hoặc hàng đợi
    participant W as Worker
    participant A as Adapter hạ tầng
    participant I as API nhà cung cấp

    P->>G: PUT /v2/service_instances/{instance_id}
    G->>H: Chuyển tiếp request qua TLS
    H->>C: Xác thực, định tuyến, giải mã JSON
    C->>S: CreateServiceInstanceRequest
    S->>DB: Đọc trạng thái và kiểm tra idempotency
    alt Hoàn tất đồng bộ
        S->>A: Tạo tài nguyên
        A->>I: Gọi API nhà cung cấp
        I-->>A: Kết quả tạo tài nguyên
        A-->>S: Thông tin tài nguyên
        S->>DB: Lưu trạng thái sẵn sàng
        S-->>C: Kết quả cấp phát
        C-->>H: Ánh xạ body và HTTP status
        H-->>G: HTTP response
        G-->>P: Kết quả hoàn tất
    else Chấp nhận xử lý bất đồng bộ
        S->>DB: Lưu instance và operation đang chờ
        S->>Q: Ghi sự kiện cần xử lý
        S-->>C: Kết quả kèm operation ID
        C-->>H: 202 Accepted
        H-->>G: HTTP response
        G-->>P: Broker đã nhận yêu cầu
        W->>Q: Nhận công việc
        W->>A: Tạo tài nguyên
        A->>I: Gọi API nhà cung cấp
        I-->>A: Kết quả
        A-->>W: Kết quả xử lý
        W->>DB: Cập nhật operation và instance
        P->>C: GET .../last_operation
        C->>S: Tra cứu trạng thái operation
        S->>DB: Đọc trạng thái mới nhất
        DB-->>S: succeeded hoặc failed
        S-->>C: Last operation response
        C-->>P: HTTP response
    end
~~~

Sơ đồ thể hiện hai khái niệm cần phân biệt. HTTP controller là nơi thực thi hợp đồng giao tiếp; service nghiệp vụ là nơi quyết định hành động. Ngoài ra, một request có thể kết thúc ở `202 Accepted` trong khi công việc cấp phát vẫn tiếp tục ở worker. Khi đó nền tảng dùng endpoint `last_operation` để hỏi trạng thái sau.

## 1. Tiếp nhận HTTP request

Nền tảng gửi request tới URL của broker. HTTP method, path, query string, header và JSON body cùng nhau xác định thao tác. Một số endpoint OSB API thường gặp:

| Thao tác | Endpoint | Ý nghĩa |
|---|---|---|
| Đọc catalog | `GET /v2/catalog` | Lấy danh sách service và plan broker công bố |
| Cấp phát instance | `PUT /v2/service_instances/{instance_id}` | Yêu cầu tạo một service instance |
| Đọc instance | `GET /v2/service_instances/{instance_id}` | Lấy thông tin instance nếu broker hỗ trợ thao tác này |
| Cập nhật instance | `PATCH /v2/service_instances/{instance_id}` | Thay đổi plan hoặc tham số được phép |
| Thu hồi instance | `DELETE /v2/service_instances/{instance_id}` | Yêu cầu xóa tài nguyên đã cấp phát |
| Theo dõi thao tác | `GET /v2/service_instances/{instance_id}/last_operation` | Lấy trạng thái xử lý bất đồng bộ |
| Tạo binding | `PUT /v2/service_instances/{instance_id}/service_bindings/{binding_id}` | Tạo thông tin kết nối cho ứng dụng |
| Xóa binding | `DELETE /v2/service_instances/{instance_id}/service_bindings/{binding_id}` | Thu hồi thông tin binding |

### Lớp mạng và HTTP server

Trong môi trường triển khai thực tế, request thường đi qua load balancer, ingress hoặc reverse proxy trước khi đến Spring Boot. Các thành phần này có thể kết thúc TLS, giới hạn kích thước body, áp dụng timeout, chuyển tiếp header và chọn instance broker. Cấu hình proxy phải giữ đúng scheme, host và prefix đường dẫn mà broker công bố; nếu proxy thêm hoặc loại bỏ prefix sai, nền tảng có thể gọi nhầm endpoint hoặc nhận URL không hợp lệ.

HTTP server nhận request, tạo ngữ cảnh xử lý và chuyển nó tới bộ định tuyến của ứng dụng. Ở giai đoạn này có thể gắn request ID hoặc trace context để nối log giữa gateway, broker và worker. Request ID phục vụ quan sát một lần gọi; nó không thay thế cơ chế idempotency cho thao tác cấp phát.

### Xác thực, phiên bản và header

Broker thường bảo vệ endpoint bằng thông tin xác thực do nền tảng và broker cấu hình, phổ biến là HTTP Basic Authentication qua TLS. Việc xác thực phải diễn ra trước khi thực hiện nghiệp vụ. Không ghi header `Authorization`, mật khẩu broker, token hoặc thông tin nhạy cảm vào log.

Các header OSB API có vai trò riêng:

- `X-Broker-API-Version` cho biết phiên bản hợp đồng API mà nền tảng sử dụng. Broker cần kiểm tra phiên bản đó nằm trong phạm vi hỗ trợ.
- `X-Broker-API-Originating-Identity`, nếu được gửi, mang thông tin nhận diện người dùng hoặc thành phần khởi tạo từ nền tảng. Broker có thể dùng nó cho audit hoặc chính sách, nhưng cần giải mã và kiểm tra dữ liệu cẩn thận.
- `Content-Type: application/json` mô tả định dạng body của request có nội dung. Broker cần từ chối hoặc xử lý rõ ràng định dạng không được hỗ trợ.
- Query parameter `accepts_incomplete=true` cho biết nền tảng chấp nhận một thao tác hoàn tất bất đồng bộ trong các endpoint có hỗ trợ.

Thông tin xác thực broker và thông tin người dùng khởi tạo request không đồng nghĩa với nhau. Xác thực broker chứng minh caller được phép gọi API; originating identity cung cấp ngữ cảnh về người dùng hoặc thành phần đứng sau caller. Nếu cần phân quyền theo tenant, broker vẫn phải kiểm tra tenant và quyền sở hữu instance trong nghiệp vụ.

### Định tuyến và giải mã request

Sau khi qua lớp bảo vệ đầu vào, bộ định tuyến chọn handler dựa trên HTTP method và path. Ví dụ, `PUT /v2/service_instances/{instance_id}` được phân biệt với `DELETE` trên cùng path vì hai method đại diện cho hai ý định khác nhau.

Framework giải mã JSON thành cấu trúc request tương ứng, đọc path variable và query parameter, rồi kiểm tra các điều kiện định dạng cơ bản. Với yêu cầu cấp phát, body thường chứa `service_id`, `plan_id`, `organization_guid`, `space_guid`, `parameters` và `context` tùy nền tảng. `instance_id` lấy từ path là định danh mà nền tảng dùng để tham chiếu instance trong các lần gọi sau.

Giải mã JSON thành công chưa có nghĩa request hợp lệ về nghiệp vụ. Một body có thể đúng cú pháp nhưng chỉ định service hoặc plan không tồn tại, thiếu tham số bắt buộc, vượt quota hoặc không tương thích với trạng thái instance. Những kiểm tra đó thuộc service nghiệp vụ.

## 2. Controller OSB API chuyển request thành lời gọi dịch vụ

Controller là lớp chuyển đổi giữa giao thức HTTP và hợp đồng dịch vụ của ứng dụng. Với Spring Cloud Open Service Broker, framework đảm nhiệm phần lớn việc cung cấp endpoint OSB, ánh xạ dữ liệu HTTP vào các request object và chuyển kết quả service thành response theo giao thức.

Controller thường thực hiện các việc sau:

1. Nhận method, path variable, query parameter và header đã qua bước tiếp nhận.
2. Dùng bộ giải mã để tạo request object có cấu trúc rõ ràng.
3. Kiểm tra điều kiện thuộc giao thức như phiên bản API, định dạng dữ liệu và tham số bắt buộc.
4. Gọi đúng service tương ứng với use case.
5. Chuyển kết quả hoặc lỗi từ service thành HTTP status, response header và JSON body theo OSB API.

Controller không nên tự tạo namespace Kubernetes, gọi API cloud provider, tính quota hay quyết định trạng thái nghiệp vụ. Nếu những quyết định đó nằm trong controller, cùng một quy tắc sẽ dễ bị lặp ở nhiều endpoint và khó kiểm thử độc lập.

### Ánh xạ endpoint tới service

Trong ứng dụng Spring Cloud Open Service Broker, các service interface thể hiện nhóm năng lực mà broker cung cấp:

| Nhóm service | Trách nhiệm chính | Ví dụ thao tác |
|---|---|---|
| `CatalogService` | Công bố danh mục service và plan | Đọc catalog |
| `ServiceInstanceService` | Quản lý vòng đời service instance | Create, retrieve, update, delete và kiểm tra last operation |
| `ServiceInstanceBindingService` | Quản lý binding gắn với instance | Create, retrieve hoặc delete binding |

Tên method cụ thể phụ thuộc phiên bản thư viện, nhưng nguyên tắc ánh xạ không đổi: endpoint catalog đi tới service catalog; endpoint vòng đời instance đi tới service instance; endpoint binding đi tới service binding. Các request object giữ dữ liệu giao thức, còn service quyết định cách xử lý dữ liệu đó.

Spring Boot auto-configuration có thể đăng ký các thành phần framework khi ứng dụng cung cấp những bean cần thiết. Vì vậy, khi triển khai broker, cần hiểu rõ phần nào framework đã cung cấp và phần nào ứng dụng phải tự triển khai. Không nên tạo một controller thứ hai cho cùng endpoint nếu framework đã sở hữu route đó.

## 3. Service nghiệp vụ điều phối use case

Service nghiệp vụ nhận request object từ controller và chuyển nó thành một use case có ý nghĩa với domain. Ví dụ, yêu cầu cấp phát instance có thể được chuyển thành lệnh `ProvisionServiceInstance` gồm định danh instance, service, plan, tenant, tham số và ngữ cảnh nền tảng.

Service nghiệp vụ chịu trách nhiệm cho các quyết định như:

- Service và plan có tồn tại, đang được công bố và cho phép cấp phát hay không.
- Plan có phù hợp với tenant, vùng triển khai, giới hạn tài nguyên và chính sách hiện tại hay không.
- Tham số đầu vào có hợp lệ theo schema hoặc quy tắc riêng của service hay không.
- Instance đã tồn tại chưa; request hiện tại là lần gọi mới hay lần retry của một thao tác trước đó.
- Người gọi có quyền đọc, thay đổi, binding hoặc thu hồi instance thuộc tenant đó hay không.
- Thao tác có thể hoàn tất ngay hay cần chuyển sang quy trình bất đồng bộ.

Service nghiệp vụ không cần biết request đến từ `PUT` hay `PATCH` ở mức chi tiết HTTP. Nó cần biết ý định cần thực hiện, dữ liệu đã được chuẩn hóa và ngữ cảnh bảo mật cần thiết. Tách biệt này cho phép kiểm thử quy tắc domain mà không cần mở HTTP server.

### Kiểm tra trạng thái trước khi gọi hạ tầng

Trước khi tạo tài nguyên, broker thường đọc bản ghi instance theo định danh và phạm vi tenant hoặc nền tảng. Nếu chưa có bản ghi, service kiểm tra service, plan và tham số rồi tạo bản ghi ở trạng thái phù hợp như `REQUESTED` hoặc `PROVISIONING`. Nếu đã có bản ghi, service cần so sánh ý định hiện tại với thao tác trước đó để xử lý retry idempotent hoặc báo xung đột.

Không nên dựa vào một lần kiểm tra trong bộ nhớ để bảo đảm duy nhất. Hai request đồng thời có thể cùng đọc thấy instance chưa tồn tại. Ràng buộc unique trong database và thao tác insert có kiểm soát giúp tránh tạo hai bản ghi hoặc hai tài nguyên cho cùng một định danh. Với broker phục vụ nhiều nền tảng, khóa nghiệp vụ có thể cần kết hợp định danh nền tảng với `instance_id` để tránh va chạm giữa các phạm vi.

### Lưu trạng thái và điều phối

Một thao tác vòng đời thường kéo dài qua nhiều bước: kiểm tra dữ liệu, ghi nhận ý định, gọi provider, lưu ID tài nguyên và cập nhật trạng thái. Không nên giữ transaction database mở trong suốt một lời gọi mạng dài. Thay vào đó, service ghi nhận trạng thái và dữ liệu cần thiết trong transaction ngắn, thực hiện lời gọi hạ tầng ở bước phù hợp, rồi ghi kết quả bằng transaction khác.

Với xử lý bất đồng bộ, mẫu transactional outbox giúp tránh tình huống database đã ghi operation nhưng sự kiện đưa vào hàng đợi bị mất, hoặc hàng đợi nhận sự kiện trong khi transaction database rollback. Service ghi bản ghi operation và sự kiện outbox trong cùng transaction; một publisher riêng chuyển sự kiện sang hàng đợi. Worker xử lý sự kiện và cập nhật trạng thái operation.

## 4. Adapter hạ tầng thực hiện thao tác với nhà cung cấp

Adapter hạ tầng là ranh giới giữa mô hình nghiệp vụ của broker và API riêng của nhà cung cấp. Service nghiệp vụ có thể yêu cầu “tạo database theo plan tiêu chuẩn cho tenant A”; adapter chuyển yêu cầu đó thành lời gọi cụ thể tới Kubernetes operator, API cloud database hoặc hệ thống nội bộ.

Adapter thường đảm nhiệm:

- Chuyển plan và tham số nghiệp vụ thành cấu hình mà provider hiểu.
- Chọn cluster, project, namespace, region hoặc tài khoản phù hợp với tenant.
- Quản lý credential kỹ thuật và gọi API provider qua client được cấu hình.
- Áp dụng timeout, retry có giới hạn, circuit breaker và giới hạn tốc độ khi phù hợp.
- Chuẩn hóa phản hồi provider thành kết quả mà domain hiểu.
- Phân loại lỗi tạm thời, lỗi cấu hình, lỗi quyền truy cập và lỗi không thể khôi phục.

Adapter không nên quyết định một plan có được phép bán hay tenant có vượt quota hay không; đó là chính sách nghiệp vụ. Tương tự, service nghiệp vụ không nên phụ thuộc trực tiếp vào cấu trúc JSON riêng của một provider. Nhờ adapter, broker có thể thay đổi backend hoặc hỗ trợ nhiều backend mà không làm thay đổi hợp đồng HTTP.

Khi provider trả về thành công, adapter chuyển các thông tin cần lưu như resource ID, endpoint, trạng thái hoặc metadata. Khi provider trả lỗi, adapter chuyển nó thành lỗi domain có phân loại. Service quyết định cập nhật trạng thái và controller chịu trách nhiệm chuyển lỗi cuối cùng thành response OSB API. Không trả nguyên văn thông báo nội bộ của provider nếu nội dung có thể tiết lộ địa chỉ, credential hoặc cấu trúc hạ tầng.

## 5. Tạo HTTP response từ kết quả nghiệp vụ

Sau khi service hoàn tất hoặc chấp nhận công việc, kết quả đi ngược qua controller và HTTP stack. Service nên trả về một kết quả có kiểu rõ ràng, chẳng hạn cấp phát thành công, đã nhận operation bất đồng bộ hoặc thất bại do một điều kiện domain. Controller ánh xạ kết quả đó sang response contract của OSB API.

Một response HTTP hoàn chỉnh gồm:

- **Status code** thể hiện request đã thành công, được chấp nhận xử lý tiếp hay thất bại.
- **Header** mô tả nội dung và metadata cần thiết cho client.
- **Body** theo schema OSB API, thường là JSON; một số response thành công có thể không cần body theo hợp đồng endpoint.

Với cấp phát hoàn tất đồng bộ, broker thường trả `201 Created` cùng response body theo hợp đồng, có thể chứa thông tin như dashboard URL nếu broker cung cấp. Với thao tác được chấp nhận xử lý bất đồng bộ, broker trả `202 Accepted` và mã operation để nền tảng theo dõi. `202` chỉ xác nhận broker đã nhận trách nhiệm xử lý; nó không khẳng định tài nguyên đã sẵn sàng.

Đối với request đọc catalog, controller chuyển catalog service response thành JSON chứa các service và plan được công bố. Đối với binding, response có thể chứa thông tin kết nối và credential dành cho ứng dụng. Những dữ liệu này cần được bảo vệ như bí mật: chỉ trả cho caller được phép và không ghi chúng vào log.

### Chu trình theo dõi operation bất đồng bộ

Khi broker trả `202 Accepted`, nền tảng có thể gọi `GET /v2/service_instances/{instance_id}/last_operation`, kèm query `operation` nếu hợp đồng hoặc broker yêu cầu. Broker đọc trạng thái mới nhất và trả một trong các trạng thái như `in progress`, `succeeded` hoặc `failed`, cùng mô tả phù hợp. Nền tảng có thể tiếp tục polling theo chính sách của nó cho tới khi thao tác kết thúc.

Operation cần có định danh ổn định, liên kết với instance và lưu được lịch sử tối thiểu để xử lý retry, audit và điều tra lỗi. Nếu worker chạy lại cùng một sự kiện, nó phải nhận ra công việc đã hoàn thành hoặc đang được xử lý để tránh tạo tài nguyên lần thứ hai.

### Chuẩn hóa lỗi

Lỗi có thể xuất hiện ở nhiều tầng: xác thực thất bại, request JSON sai, endpoint không tồn tại, service hoặc plan không hợp lệ, instance không thuộc tenant, provider timeout hoặc broker gặp lỗi nội bộ. Controller và framework cần chuyển chúng thành status code cùng error response đúng hợp đồng OSB API.

Thông thường, lỗi xác thực được phản ánh bằng `401` hoặc `403`; tài nguyên không tồn tại bằng `404`; xung đột trạng thái bằng `409`; dữ liệu hoặc tham số không hợp lệ bằng nhóm `4xx`; lỗi không dự kiến ở broker hoặc provider bằng nhóm `5xx`. Mã cụ thể phải theo điều kiện và quy định của endpoint OSB API, không nên dùng một status chung cho mọi lỗi.

Error body OSB API thường cung cấp trường `error` và `description`. `error` nên ổn định để nền tảng hoặc người vận hành có thể phân loại; `description` giải thích đủ để xử lý nhưng không tiết lộ stack trace, SQL, token, credential hay thông tin hạ tầng nhạy cảm. Log nội bộ có thể chứa mã lỗi provider và trace ID để điều tra, nhưng cần lọc dữ liệu bí mật.

## 6. Ví dụ luồng cấp phát service instance

Giả sử nền tảng yêu cầu tạo một database từ service broker. Request có thể có dạng minh họa sau:

~~~http
PUT /v2/service_instances/db-instance-42?accepts_incomplete=true HTTP/1.1
Host: broker.example.internal
Authorization: Basic <broker-credentials>
X-Broker-API-Version: 2.16
Content-Type: application/json

{
  "service_id": "database-service",
  "plan_id": "standard-plan",
  "organization_guid": "org-123",
  "space_guid": "space-456",
  "parameters": {
    "storage_gb": 20,
    "engine": "postgres"
  },
  "context": {
    "platform": "example-platform"
  }
}
~~~

Các bước xử lý có thể diễn ra như sau:

1. Ingress nhận kết nối HTTPS, áp dụng giới hạn request và chuyển tiếp tới broker.
2. Spring Security hoặc lớp bảo vệ tương đương xác thực credential. Bộ định tuyến chọn endpoint cấp phát instance.
3. Framework kiểm tra header phiên bản, giải mã JSON và tạo request object. `instance_id` lấy từ path; `accepts_incomplete` lấy từ query.
4. Service instance kiểm tra service và plan, xác thực tham số, kiểm tra phạm vi tenant và tìm instance có cùng định danh.
5. Nếu đây là request mới, broker ghi nhận instance cùng operation ở trạng thái chờ. Sự kiện cấp phát được chuyển cho worker.
6. Worker gọi adapter database. Adapter tạo database trên provider, nhận resource ID và thông tin kết nối cần thiết.
7. Worker lưu kết quả, chuyển instance sang trạng thái sẵn sàng và operation sang trạng thái thành công. Nếu có lỗi, worker lưu trạng thái thất bại cùng mã lỗi đã chuẩn hóa.
8. Nền tảng gọi `last_operation` để đọc trạng thái. Controller ánh xạ trạng thái đã lưu thành JSON response theo OSB API.

Nếu broker có thể hoàn tất nhanh và chọn xử lý đồng bộ, bước 5 đến 7 diễn ra trước khi request ban đầu kết thúc; controller trả response thành công tương ứng. Nếu broker cần xử lý nền, request ban đầu kết thúc bằng `202 Accepted`, sau đó nền tảng theo dõi operation.

Mã giả sau minh họa trách nhiệm của use case. Đây là mã mô hình hóa nghiệp vụ, không phải chữ ký method của thư viện Spring Cloud Open Service Broker:

~~~java
ProvisionResult provision(ProvisionCommand command) {
    var existing = instanceRepository.find(
        command.platformId(), command.instanceId());

    if (existing != null) {
        return idempotencyPolicy.resolve(
            existing, command.requestFingerprint());
    }

    var instance = instanceRepository.insertIfAbsent(
        ServiceInstance.requested(command));

    if (!command.acceptsIncomplete()) {
        var resource = infrastructure.provision(command);
        instanceRepository.markReady(instance.id(), resource.id());
        return ProvisionResult.created(instance.id());
    }

    var operation = operationRepository.create(instance.id());
    outboxRepository.append(
        ProvisionRequested.of(instance.id(), operation.id()));

    return ProvisionResult.accepted(instance.id(), operation.id());
}
~~~

Trong triển khai thực tế, nhánh đồng bộ phải xử lý trường hợp provider không thể hoàn tất trong thời gian request cho phép. Nếu broker chỉ hỗ trợ xử lý bất đồng bộ nhưng nền tảng không chấp nhận incomplete operation, broker cần trả lỗi theo hợp đồng OSB API thay vì âm thầm giữ kết nối quá lâu.

## 7. Idempotency và xử lý request lặp

Nền tảng có thể gửi lại request khi timeout, mất kết nối hoặc không nhận được response dù broker đã thực hiện một phần công việc. Vì vậy, broker phải thiết kế thao tác vòng đời để retry không tạo ra tài nguyên trùng lặp.

Với cấp phát, `instance_id` là một phần quan trọng của định danh thao tác. Broker lưu ý định cấp phát và trạng thái theo định danh đó. Khi nhận lại request:

- Nếu request có cùng ý định với thao tác hiện tại, broker trả kết quả hoặc operation hiện có theo hợp đồng.
- Nếu request mâu thuẫn với dữ liệu đã gắn với instance, broker trả lỗi xung đột phù hợp.
- Nếu thao tác trước đang chạy, broker không khởi tạo thêm một lần cấp phát độc lập.
- Nếu provider đã tạo tài nguyên nhưng broker chưa kịp lưu kết quả, adapter hoặc worker cần cơ chế tra cứu/reconcile để tìm lại tài nguyên trước khi thử tạo mới.

Một fingerprint có thể được tạo từ service ID, plan ID, tenant, tham số đã chuẩn hóa và các thuộc tính có ý nghĩa. Không nên đưa dữ liệu bí mật thô vào fingerprint có thể quan sát được; có thể dùng hash phù hợp và bảo vệ dữ liệu đầu vào. Idempotency cần được bảo đảm bằng lưu trữ bền vững, khóa duy nhất và xử lý đồng thời, không chỉ bằng cache trong một instance ứng dụng.

Idempotency cũng áp dụng cho delete và binding. Xóa một binding đã được xóa trước đó hoặc xử lý lại một sự kiện hoàn thành cần có kết quả xác định. Mục tiêu là mỗi ý định nghiệp vụ chỉ tạo ra một hiệu ứng tài nguyên, ngay cả khi hệ thống truyền thông điệp theo cơ chế ít nhất một lần và có retry.

## 8. Phân biệt xử lý reactive với operation bất đồng bộ của OSB

Một số API của hệ sinh thái Spring sử dụng kiểu reactive như `Mono` để biểu diễn kết quả sẽ phát ra sau khi pipeline hoàn tất. Reactive giúp xử lý I/O không chặn thread trong khi chờ database hoặc provider. Tuy nhiên, việc method trả về `Mono` không tự động có nghĩa broker đã bắt đầu một OSB asynchronous operation.

Hai khái niệm khác nhau ở mục đích:

| Khái niệm | Ý nghĩa | Dấu hiệu ở HTTP/OSB |
|---|---|---|
| Reactive hoặc non-blocking | Cách ứng dụng thực thi I/O và phối hợp kết quả | Có thể vẫn trả một response hoàn tất trong request hiện tại |
| OSB asynchronous operation | Hợp đồng cho biết công việc vòng đời tiếp tục sau response ban đầu | Trả `202 Accepted`, có operation và hỗ trợ `last_operation` |

Một pipeline reactive có thể hoàn thành nhanh và trả response đồng bộ theo OSB. Ngược lại, một OSB operation bất đồng bộ cần lưu trạng thái bền vững, có worker hoặc cơ chế điều phối nền, và cho phép nền tảng truy vấn tiến độ sau khi request ban đầu kết thúc. Thiết kế broker phải đáp ứng cả mô hình thực thi của framework lẫn hợp đồng vòng đời OSB.

## 9. Bảo mật và khả năng quan sát xuyên suốt

Request đi qua nhiều thành phần nên bảo mật cần được áp dụng ở từng ranh giới:

- Bắt buộc dùng TLS trên đường truyền và bảo vệ credential broker trong secret store.
- Xác thực caller ở lớp HTTP; kiểm tra quyền sở hữu instance và tenant ở lớp nghiệp vụ.
- Xác thực `service_id`, `plan_id`, `instance_id`, binding ID và mọi tham số do client gửi; không tin `context` chỉ vì nó đến từ nền tảng.
- Chỉ trả credential binding cho caller được phép; mã hóa dữ liệu nhạy cảm khi lưu trữ và không ghi chúng vào log.
- Giới hạn kích thước request, timeout, số lần retry và tốc độ gọi provider để giảm nguy cơ cạn tài nguyên.
- Chuẩn hóa lỗi trước khi trả ra ngoài, giữ chi tiết kỹ thuật cần thiết trong log nội bộ có kiểm soát truy cập.

Để theo dõi một request từ HTTP đến worker, broker nên truyền trace context hoặc correlation ID qua các lời gọi nội bộ và sự kiện hàng đợi. Log có cấu trúc nên ghi các trường như request ID, operation ID, service ID, plan ID, instance ID đã che/mã hóa phù hợp, trạng thái trước và sau, thời gian xử lý và mã lỗi. Không đưa token, password hoặc credential binding vào log.

Các metric hữu ích gồm số request theo endpoint và status code, độ trễ HTTP, số operation đang chờ, thời gian hoàn tất operation, tỷ lệ thất bại theo provider, số lần retry và độ sâu hàng đợi. Metric cần có nhãn được kiểm soát để tránh tạo cardinality quá lớn từ instance ID hoặc tenant ID.

## 10. Kiểm thử từng ranh giới

Thiết kế phân lớp cho phép kiểm thử từng phần và kiểm tra toàn bộ hợp đồng:

| Phạm vi | Nội dung cần kiểm tra |
|---|---|
| HTTP contract | Method, path, header phiên bản, JSON schema, status code và error body |
| Controller/service mapping | Mỗi endpoint gọi đúng service; request object giữ đúng path, query và body |
| Service nghiệp vụ | Plan không hợp lệ, quota, tenant, trạng thái instance, retry và xung đột đồng thời |
| Repository | Ràng buộc unique, transaction, cập nhật trạng thái và truy vấn operation |
| Adapter hạ tầng | Provider thành công, timeout, lỗi quyền, retry và phản hồi không đầy đủ |
| Async workflow | Outbox không mất sự kiện, worker chạy lại an toàn, polling trả trạng thái đúng |
| Security | Thiếu hoặc sai credential, truy cập chéo tenant, rò rỉ secret trong response/log |

Kiểm thử tích hợp nên chạy request qua HTTP endpoint thực của framework để xác nhận status code và JSON response đúng OSB API. Kiểm thử service có thể dùng repository và adapter giả lập để tập trung vào quy tắc domain. Kiểm thử adapter nên xác nhận mapping request/response với provider. Với thao tác bất đồng bộ, cần mô phỏng việc worker nhận lại cùng sự kiện và kiểm tra rằng tài nguyên không bị tạo trùng.

## Kết luận

Luồng từ HTTP request đến HTTP response là chuỗi chuyển đổi có kiểm soát: giao thức OSB API được tiếp nhận và xác thực, controller chuyển dữ liệu thành lời gọi service, service áp dụng quy tắc nghiệp vụ và điều phối adapter, sau đó kết quả được ánh xạ trở lại response theo hợp đồng. Khi mỗi lớp giữ đúng trách nhiệm, broker dễ mở rộng thêm service và plan, thay đổi provider, hỗ trợ Cloud Foundry hoặc Kubernetes, đồng thời duy trì idempotency, bảo mật và khả năng quan sát trong cả xử lý đồng bộ lẫn bất đồng bộ.
