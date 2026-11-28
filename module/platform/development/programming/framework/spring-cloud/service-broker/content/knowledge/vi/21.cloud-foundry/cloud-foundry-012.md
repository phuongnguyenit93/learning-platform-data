# Dashboard SSO và kiểm soát truy cập trang quản lý dịch vụ

Cloud Foundry cho phép người dùng mở trang quản lý của một service instance từ Apps Manager hoặc client tương thích thông qua trường **dashboard_url**. Để người dùng không phải tạo tài khoản riêng cho từng nhà cung cấp, service dashboard có thể tích hợp **Dashboard Single Sign-On (SSO)** với User Account and Authentication (UAA). Người dùng đăng nhập bằng danh tính Cloud Foundry, còn dashboard nhận OAuth token có scope giới hạn và kiểm tra quyền trên đúng service instance trước khi hiển thị chức năng quản lý.

Trong module **SPRING_CLOUD_SERVICE_BROKER**, dashboard là một giao diện bổ sung bên cạnh các endpoint OSB API. Broker chịu trách nhiệm công bố dashboard client trong catalog, trả dashboard URL khi provision, lưu ánh xạ platform/instance cần thiết và cung cấp giao diện quản lý an toàn. Dashboard phải hoàn thành OAuth Authorization Code flow, kiểm tra quyền đọc hoặc quản lý instance qua Cloud Controller, rồi áp dụng quyền đó cho cả giao diện lẫn API phía server.

## 1. Dashboard của service broker là gì?

Service instance được tạo qua OSB API có thể cần một giao diện web để người vận hành xem trạng thái, cấu hình, chẩn đoán hoặc quản lý tài nguyên. Ví dụ:

- PostgreSQL dashboard hiển thị database, dung lượng, backup, kết nối và thông tin failover.
- Redis dashboard hiển thị memory, key statistics, replication và maintenance.
- Message broker dashboard hiển thị queue, consumer, throughput và policy.
- Search service dashboard hiển thị index, shard, query metrics và trạng thái cluster.

Cloud Foundry không tự xây dựng giao diện riêng cho từng nhà cung cấp. Broker có thể trả URL đến dashboard do nhà cung cấp vận hành. Platform lưu URL này cùng service instance và hiển thị liên kết cho người dùng có quyền.

Dashboard SSO giúp tái sử dụng danh tính Cloud Foundry. Người dùng mở dashboard, được chuyển đến UAA để đăng nhập hoặc sử dụng session hiện có, sau đó quay lại dashboard với authorization code. Dashboard đổi code lấy access token và dùng token đó để hỏi Cloud Controller xem người dùng có quyền trên instance được mở hay không.

Dashboard SSO là **phần mở rộng dành riêng cho Cloud Foundry**, không phải một trường bắt buộc của OSB API áp dụng giống nhau cho mọi platform. Broker có thể triển khai dashboard URL mà không triển khai SSO, nhưng nếu công bố Dashboard SSO thì phải tuân thủ contract và cơ chế UAA của Cloud Foundry.

## 2. Phân biệt dashboard_url và dashboard_client

Hai trường có vai trò khác nhau:

| Trường | Nơi công bố | Ý nghĩa |
|---|---|---|
| dashboard_url | Response provision của service instance | URL dashboard dành cho một instance cụ thể |
| dashboard_client | Catalog extension ở cấp service | OAuth client ID, secret và redirect URI để dashboard xác thực với UAA |

**dashboard_url** cho platform biết người dùng cần mở trang nào. URL phải chứa đủ thông tin để dashboard xác định instance cần quản lý. Nó thường được tạo khi provision và được lưu cùng instance.

**dashboard_client** cung cấp thông tin OAuth client cho dashboard. Cloud Controller đọc thông tin này khi broker được đăng ký hoặc cập nhật catalog và tạo/cập nhật UAA client tương ứng. Dashboard sử dụng client ID và secret đó khi đổi authorization code lấy token.

Ví dụ catalog extension:

~~~json
{
  "services": [
    {
      "id": "svc-postgresql",
      "name": "postgresql",
      "description": "Managed PostgreSQL",
      "bindable": true,
      "dashboard_client": {
        "id": "postgresql-dashboard",
        "secret": "<dashboard-client-secret>",
        "redirect_uri": "https://dashboard.example.com"
      },
      "plans": [
        {
          "id": "plan-production",
          "name": "production",
          "description": "PostgreSQL production"
        }
      ]
    }
  ]
}
~~~

Các giá trị trong ví dụ chỉ minh họa. Không dùng secret giả hoặc secret dùng chung cho môi trường production.

### Dashboard client là thuộc tính cấp service

Cloud Foundry yêu cầu có một dashboard_client entry cho mỗi service sử dụng SSO. Client ID phải duy nhất trong một Cloud Foundry deployment. Nếu ID đã được sử dụng, Cloud Controller có thể từ chối khi đăng ký hoặc cập nhật broker.

Không tạo một dashboard client khác nhau theo từng instance trong catalog. Một service definition công bố client mà dashboard của service sử dụng; mỗi dashboard URL lại xác định instance cụ thể mà người dùng đang mở.

## 3. Hai loại OAuth client trong cấu hình Cloud Foundry

Khi cấu hình Dashboard SSO, cần phân biệt client quản trị của Cloud Controller và client dashboard do broker công bố.

| Client | Ai sử dụng? | Mục đích |
|---|---|---|
| cc-service-dashboards | Cloud Controller | Tạo, cập nhật và xóa UAA client cho service dashboard |
| dashboard_client của service | Ứng dụng dashboard | Bắt đầu OAuth flow và đổi authorization code lấy token |

Cloud Controller cần một UAA client có authority quản lý các client khác. Cấu hình triển khai Cloud Foundry có thể khai báo:

~~~yaml
properties:
  uaa:
    clients:
      cc-service-dashboards:
        secret: <cloud-controller-dashboard-management-secret>
        scope: openid,cloud_controller_service_permissions.read
        authorities: clients.read,clients.write,clients.admin
        authorized-grant-types: authorization_code,client_credentials
~~~

Đây là ví dụ cấu hình trong manifest của triển khai Cloud Foundry; tên property và cách quản lý secret cần theo phiên bản cf-deployment/cf-release đang vận hành.

Client này cho phép Cloud Controller quản lý các UAA client mà broker yêu cầu. Khi thiếu client hoặc thiếu authority, Cloud Controller không thể tạo/cập nhật dashboard client và có thể phát cảnh báo khi broker đăng ký hoặc cập nhật catalog.

Không dùng secret của cc-service-dashboards trong ứng dụng dashboard. Dashboard chỉ dùng client ID và secret tương ứng với service đã công bố trong catalog.

## 4. Luồng tổng thể của Dashboard SSO

Một luồng phổ biến:

~~~mermaid
sequenceDiagram
    participant U as User
    participant CF as Cloud Foundry Apps Manager
    participant D as Service Dashboard
    participant UAA as UAA
    participant CC as Cloud Controller
    participant B as Service Broker

    U->>CF: Mở service instance
    CF-->>U: Hiển thị dashboard_url
    U->>D: GET dashboard_url
    D->>D: Resolve instance và platform
    D-->>U: Redirect tới UAA Authorization Endpoint
    U->>UAA: Đăng nhập / consent
    UAA-->>U: Redirect callback với authorization code
    U->>D: GET callback?code=...
    D->>UAA: Đổi code lấy token (client authentication)
    UAA-->>D: Access token + refresh token
    D->>CC: GET /v3/service_instances/{guid}/permissions
    CC-->>D: manage / read
    D-->>U: Render dashboard theo quyền
    D->>B: Đọc dữ liệu service instance (nếu cần)
~~~

Các bước:

1. Người dùng mở liên kết dashboard từ platform.
2. Dashboard xác định service instance và Cloud Foundry foundation tương ứng.
3. Dashboard chuyển trình duyệt đến UAA Authorization Endpoint.
4. UAA xác thực người dùng và xử lý consent theo cấu hình.
5. UAA chuyển trình duyệt về callback URL kèm authorization code.
6. Dashboard server đổi code lấy token tại UAA Token Endpoint.
7. Dashboard dùng access token gọi Cloud Controller permissions endpoint.
8. Dashboard kiểm tra quyền manage/read và tạo session phù hợp.
9. Mỗi thao tác nhạy cảm tiếp tục được authorization ở backend.

UAA xác thực danh tính; Cloud Controller trả lời người dùng có quyền gì trên service instance cụ thể. Không được coi việc OAuth login thành công là đủ để cho phép quản lý mọi instance.

## 5. Khám phá UAA endpoint của đúng Cloud Foundry foundation

Một broker có thể được đăng ký với nhiều Cloud Foundry foundation. Mỗi foundation có thể sử dụng UAA riêng. Dashboard cần gọi đúng Authorization Endpoint và Token Endpoint của foundation đã tạo instance.

Cloud Controller cung cấp thông tin này qua endpoint info. Trường authorization_endpoint và token_endpoint trong response cho biết các URL của UAA.

Ví dụ response info rút gọn:

~~~json
{
  "name": "vcap",
  "authorization_endpoint": "https://login.cf.example.com",
  "token_endpoint": "https://uaa.cf.example.com"
}
~~~

Cloud Foundry gửi header **X-Api-Info-Location** trong các request đến service broker. Header chứa URL endpoint info của foundation gửi request. Service broker có thể lưu thông tin này cùng platform registration hoặc service instance để dashboard tìm đúng UAA sau này.

Ví dụ:

~~~http
PUT /v2/service_instances/instance-guid-123?service_id=svc-postgresql&plan_id=plan-production
X-Api-Info-Location: https://api.cf-east.example.com/v2/info
X-Broker-API-Version: 2.17
Authorization: Basic <broker-credentials>
~~~

Broker cần:

- Nhận header ở mọi request platform gửi.
- Xác minh URL thuộc một platform registration được phép.
- Lưu platform identity và API info location với instance.
- Khi dashboard mở instance, lấy đúng info URL đã lưu.
- Đọc authorization_endpoint và token_endpoint từ response info.
- Không giả định tất cả instance đều dùng một UAA cố định.

Tài liệu Cloud Foundry hiện tại ghi nhận CAPI V2 đã deprecated, nhưng Cloud Controller vẫn truyền URL /v2/info qua header X-Api-Info-Location; /v2/info tiếp tục được phục vụ cho mục đích này trong các cấu hình được mô tả. Cần kiểm tra hành vi ở phiên bản Cloud Foundry thực tế đang tích hợp.

### Không tin URL tùy ý từ browser

Nếu dashboard nhận info URL từ query parameter hoặc header do người dùng tự gửi, kẻ tấn công có thể khiến server gọi một địa chỉ nội bộ. Đây là nguy cơ SSRF.

Dashboard chỉ nên dùng URL đã được broker lưu từ request platform đã xác thực hoặc platform registry đã được quản trị. Cần kiểm tra scheme HTTPS, host allowlist, DNS/IP policy và redirect behavior. Không cho phép URL do caller tùy ý chọn để server thực hiện HTTP request.

## 6. Cấu hình dashboard_client trong Spring Cloud Service Broker

Spring Cloud Open Service Broker có model **DashboardClient** trong package catalog. Model này chứa ID, secret và redirect URI. ServiceDefinition có thể gắn dashboard client để framework serialize extension vào catalog.

Ví dụ cấu hình Java:

~~~java
import org.springframework.cloud.servicebroker.model.catalog.DashboardClient;
import org.springframework.cloud.servicebroker.model.catalog.ServiceDefinition;

DashboardClient dashboardClient = DashboardClient.builder()
    .id("postgresql-dashboard")
    .secret(dashboardClientSecret)
    .redirectUri("https://dashboard.example.com")
    .build();

ServiceDefinition service = ServiceDefinition.builder()
    .id("svc-postgresql")
    .name("postgresql")
    .description("Managed PostgreSQL")
    .bindable(true)
    .dashboardClient(dashboardClient)
    .plans(plans)
    .build();
~~~

Tên builder và model cần khớp với phiên bản dependency đang dùng. Trong Spring Cloud Open Service Broker 4.4.x, catalog model có DashboardClient và ServiceDefinition builder hỗ trợ dashboardClient(...).

Một số điểm cần chú ý:

- Chỉ gắn dashboard client cho service có dashboard SSO.
- Client ID phải duy nhất trong Cloud Foundry deployment.
- Secret phải lấy từ secret manager hoặc cấu hình bảo mật.
- Redirect URI phải trỏ đến callback domain mà dashboard kiểm soát.
- Không ghi secret vào log catalog hoặc log request.
- Khi secret thay đổi, cập nhật catalog/broker registration theo quy trình rotation.

Vì catalog endpoint có thể được Cloud Controller đọc định kỳ hoặc khi operator cập nhật broker, dashboard client phải được giữ ổn định và nhất quán với cấu hình UAA đang hoạt động.

## 7. Trả dashboard_url khi provision

Cloud Foundry cần biết URL quản lý cho mỗi service instance. Broker trả trường dashboard_url trong response provision.

Ví dụ:

~~~json
{
  "dashboard_url": "https://dashboard.example.com/instances/opaque-instance-reference"
}
~~~

URL phải chứa đủ thông tin để dashboard xác định tài nguyên đang được truy cập. Có thể dùng opaque reference được tạo ngẫu nhiên và ánh xạ trong state store đến internal instance ID. Không nên đặt password, access token, provider credential hoặc thông tin nhạy cảm trong URL.

Trong Spring Cloud Open Service Broker:

~~~java
@Override
public Mono<CreateServiceInstanceResponse> createServiceInstance(
        CreateServiceInstanceRequest request) {

    return provisionService.start(request)
        .map(result -> CreateServiceInstanceResponse.builder()
            .dashboardUrl(result.dashboardUrl())
            .async(result.async())
            .operation(result.operationId())
            .build());
}
~~~

Ví dụ minh họa cấu trúc response; ProvisionService là domain service do ứng dụng xây dựng. Dashboard URL được xác định từ instance identity và platform registration đã lưu.

### Phải trả dashboard_url ngay trong response ban đầu

Nếu broker muốn Cloud Foundry hiển thị dashboard, dashboard_url cần được trả trong response provision ban đầu, kể cả khi provisioning được xử lý bất đồng bộ. Không đợi worker hoàn tất mới thêm URL nếu platform cần lưu liên kết ngay từ request đầu.

Điều đó không có nghĩa dashboard phải cho phép quản lý tài nguyên chưa sẵn sàng. Khi người dùng mở URL trong lúc instance còn PROVISIONING, dashboard có thể hiển thị trạng thái đang tạo và vô hiệu hóa thao tác quản lý cho đến khi backend sẵn sàng.

Nếu broker hỗ trợ retrieve service instance, response retrieve cũng nên trả dashboard URL đã lưu để platform có thể hiển thị lại liên kết theo contract. Khi update thay đổi URL, phải áp dụng semantics response update của OSB API; nếu không cung cấp URL mới, platform có thể giữ giá trị trước đó theo contract.

## 8. Thiết kế dashboard URL an toàn

Một URL có thể có dạng:

~~~text
https://dashboard.example.com/instances/7f4a9b0c2e...
~~~

Phần cuối nên là opaque identifier hoặc signed reference có entropy đủ lớn. Dashboard dùng nó để tra cứu instance trong database.

Không nên tạo URL như:

~~~text
https://dashboard.example.com/manage?tenant=tenant-a&instance=orders-db&admin=true
~~~

Các tham số có thể bị sửa, ghi vào browser history, proxy log hoặc analytics. Dashboard không được tin tenant, role hoặc permission trong URL.

Một thiết kế an toàn:

1. Tạo random reference khi provision.
2. Lưu hash/reference cùng internal instance ID, platform ID và tenant ID.
3. Trả URL chứa reference.
4. Khi truy cập, tìm instance theo reference.
5. Xác định platform registration và UAA endpoint đã lưu.
6. Chưa hiển thị dữ liệu nhạy cảm trước khi OAuth và permission check thành công.
7. Giới hạn tốc độ thử reference và audit truy cập thất bại.

Nếu dùng signed token trong URL, cần có expiry, audience, signature verification và không chứa quyền lâu dài. Tuy vậy, một opaque reference tra cứu server-side thường dễ thu hồi và không biến URL thành bearer credential.

## 9. OAuth Authorization Code Grant

Cloud Foundry Dashboard SSO yêu cầu dashboard triển khai OAuth Authorization Code Grant. UAA cung cấp Authorization Endpoint và Token Endpoint.

Dashboard chuyển browser đến Authorization Endpoint với các tham số chính:

| Tham số | Ý nghĩa |
|---|---|
| response_type | Giá trị code để yêu cầu authorization code |
| client_id | ID của dashboard client đã đăng ký |
| redirect_uri | Callback URL của dashboard |
| scope | Các quyền tối thiểu dashboard cần |
| state | Giá trị ngẫu nhiên liên kết request và callback |
| client-specific context | Thông tin cần thiết để dashboard xác định instance/platform |

Ví dụ URL khái niệm:

~~~text
https://login.cf.example.com/oauth/authorize
  ?response_type=code
  &client_id=postgresql-dashboard
  &redirect_uri=https%3A%2F%2Fdashboard.example.com%2Fauth%2Fcallback
  &scope=openid%20cloud_controller_service_permissions.read
  &state=RANDOM_CSRF_VALUE
~~~

Đây là URL minh họa; endpoint và tham số cần theo UAA deployment. Dashboard cần bảo vệ callback bằng state để chống login CSRF và liên kết callback với browser session đã bắt đầu flow.

### Bước 1 — Bắt đầu login

Người dùng mở dashboard URL. Dashboard tạo state ngẫu nhiên, lưu state vào session tạm hoặc cookie bảo mật và redirect browser tới Authorization Endpoint tương ứng với foundation của instance.

### Bước 2 — Người dùng xác thực

UAA xác thực người dùng bằng Cloud Foundry identity store hoặc identity provider mà deployment cấu hình. Nếu session UAA đã tồn tại, người dùng có thể không phải nhập lại thông tin đăng nhập.

### Bước 3 — Nhận authorization code

Nếu người dùng chấp thuận quyền được yêu cầu, UAA redirect về callback URL cùng authorization code. Dashboard kiểm tra state, thời hạn và session correlation trước khi sử dụng code.

### Bước 4 — Đổi code lấy token

Dashboard server gọi Token Endpoint, gửi authorization code, redirect URI và xác thực client theo cấu hình UAA. Cloud Foundry documentation mô tả dashboard client xác thực bằng client ID/secret qua HTTP Basic Authentication trong token request.

~~~http
POST /oauth/token
Authorization: Basic <base64(client_id:client_secret)>
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code&
code=<authorization-code>&
redirect_uri=https%3A%2F%2Fdashboard.example.com%2Fauth%2Fcallback
~~~

UAA kiểm tra code, client và redirect URI. Nếu hợp lệ, UAA trả access token và refresh token theo cấu hình.

### Bước 5 — Tạo dashboard session

Dashboard lưu token ở server-side session hoặc token store bảo vệ. Browser chỉ nhận session cookie ngẫu nhiên, không nhận client secret hoặc refresh token.

Không đặt access token trong query string, fragment URL, localStorage hoặc log. Token có thể xuất hiện trong browser history, Referer header hoặc hệ thống giám sát nếu được truyền qua URL.

## 10. Kiểm tra quyền trên đúng service instance

Sau khi login, dashboard phải kiểm tra quyền người dùng trên instance cụ thể qua Cloud Controller endpoint:

~~~http
GET /v3/service_instances/{service_instance_guid}/permissions
Authorization: Bearer <user-access-token>
Content-Type: application/json
~~~

Ví dụ response:

~~~json
{
  "manage": true,
  "read": true
}
~~~

Hai giá trị có ý nghĩa:

| Permission | Ý nghĩa |
|---|---|
| manage | Người dùng có quyền thay đổi hoặc quản lý service instance |
| read | Người dùng có quyền xem thông tin chẩn đoán/giám sát ở chế độ chỉ đọc |

UAA xác thực người dùng và cấp token có scope yêu cầu. Cloud Controller permissions endpoint xác định quyền đối với service instance. Dashboard phải sử dụng kết quả này để quyết định giao diện và hành động được phép.

Không tự suy ra quyền manage chỉ từ role hiển thị trong JWT hoặc từ việc người dùng đăng nhập thành công. Quyền trên service instance có thể thay đổi khi administrator cập nhật membership hoặc role.

### Kiểm tra mỗi lần vào SSO

Cloud Foundry yêu cầu dashboard kiểm tra permissions endpoint trong mỗi lần người dùng sử dụng SSO để vào giao diện service. Administrator có thể thay đổi quyền bất kỳ lúc nào; do đó không nên dựa vào một kết quả allow được lưu vô thời hạn.

Đối với thao tác quan trọng, dashboard cũng nên kiểm tra quyền ở server trước khi thực hiện action. Việc ẩn nút trên giao diện chỉ là trải nghiệm người dùng, không phải authorization boundary.

## 11. Hiển thị dashboard theo quyền manage và read

Sau khi nhận permission response:

| manage | read | Cách xử lý dashboard |
|---|---|---|
| true | true | Cho phép xem và thực hiện chức năng quản lý được hỗ trợ |
| false | true | Chỉ hiển thị dashboard read-only |
| true | false | Chỉ cung cấp thao tác mà policy/API xác nhận; không mặc định có quyền xem diagnostics |
| false | false | Từ chối truy cập nội dung instance |

Trường hợp manage=true/read=false cần được xử lý theo semantics permissions của platform và thiết kế sản phẩm. Không tự nâng read thành true chỉ vì manage được cấp. Nếu một thao tác quản lý cần đọc dữ liệu để thực hiện, backend phải kiểm tra permission phù hợp hoặc dùng endpoint có authorization rõ ràng.

### Read-only dashboard

Người có quyền read có thể được xem:

- Trạng thái instance.
- Metrics và thông tin health.
- Lịch sử sự kiện được phép đọc.
- Cấu hình không nhạy cảm.
- Trạng thái backup/replication.
- Thông tin chẩn đoán đã được lọc.

Không hiển thị password, private key hoặc binding secret chỉ vì người dùng có quyền đọc dashboard. Quyền read của Cloud Controller không tự động cấp quyền đọc mọi secret trong backend.

### Manage dashboard

Người có quyền manage có thể được cung cấp:

- Thay đổi cấu hình được hỗ trợ.
- Thực hiện thao tác maintenance.
- Tạo hoặc xóa resource phụ trợ.
- Khởi chạy backup hoặc restore nếu policy cho phép.
- Xem thông tin quản trị cần thiết.
- Thực hiện các hành động service-specific.

Mỗi API endpoint của dashboard vẫn phải xác thực session, xác minh instance ownership và kiểm tra manage permission. Không chỉ kiểm tra quyền ở route render trang HTML.

## 12. Scopes tối thiểu và nguyên tắc least privilege

Cloud Foundry Dashboard SSO mô tả hai scope tối thiểu:

| Scope | Mục đích |
|---|---|
| openid | Cho phép truy cập thông tin nhận dạng cơ bản |
| cloud_controller_service_permissions.read | Cho phép gọi endpoint permissions để kiểm tra quyền trên service instance |

Dashboard có thể cần thêm scope cho chức năng mở rộng:

| Scope | Khả năng |
|---|---|
| cloud_controller.read | Đọc các resource mà người dùng vốn được phép đọc |
| cloud_controller.write | Tạo, cập nhật hoặc xóa resource mà người dùng được phép thao tác |

Scopes giới hạn những API mà token có thể gọi; chúng không cấp thêm quyền vượt qua quyền người dùng đang có. Dashboard nên chỉ yêu cầu scope thực sự cần.

Ví dụ, nếu dashboard chỉ cần hiển thị trạng thái và nút quản lý thông qua backend API của nhà cung cấp, không nhất thiết yêu cầu cloud_controller.write. Việc có token scope rộng hơn làm tăng tác động nếu token bị lộ.

Không nhầm scope của dashboard client với authority của Cloud Controller management client. Client cc-service-dashboards có quyền quản lý UAA clients; dashboard client chỉ nên nhận scope phục vụ trải nghiệm dashboard.

## 13. Redirect URI và bảo vệ OAuth callback

Redirect URI là một ranh giới bảo mật quan trọng. UAA dùng redirect URI để kiểm tra authorization code có được trả về đúng dashboard client đã đăng ký hay không.

Các nguyên tắc:

- Dùng HTTPS cho dashboard và callback trong production.
- Đăng ký một callback domain ổn định, do broker kiểm soát.
- Không lấy redirect URI từ query parameter do user tự gửi.
- Không cho phép open redirect sau callback.
- Kiểm tra state trước khi đổi code.
- Không tái sử dụng authorization code.
- Không chấp nhận callback thiếu code hoặc có state không khớp.
- Giới hạn thời gian sống của state và session tạm.
- Không ghi code, token hoặc client secret vào log.

Cloud Foundry documentation mô tả UAA kiểm tra domain của callback URI theo redirect_uri được khai báo trong dashboard_client; cách matching path phụ thuộc hành vi UAA. Dù deployment cho phép nhiều path trong cùng domain, nên cấu hình callback cụ thể và ổn định để giảm bề mặt tấn công.

Nếu dashboard chạy sau reverse proxy, phải cấu hình trusted forwarded headers đúng cách. Không dùng Host hoặc X-Forwarded-Host do caller không tin cậy gửi để tự tạo redirect URI.

## 14. Quản lý client secret và token

Dashboard client là confidential OAuth client trong flow được mô tả bởi Cloud Foundry. Client secret phải nằm ở server-side.

Không được:

- Đưa client secret vào JavaScript bundle.
- Render secret trong HTML.
- Trả secret qua API cho browser.
- Ghi secret vào log catalog, trace hoặc exception.
- Lưu secret trong source control.
- Dùng một secret cố định cho mọi môi trường.
- Dùng secret của Cloud Controller management client thay cho dashboard client.

Nên:

1. Lưu secret trong secret manager hoặc hệ thống cấu hình bảo mật.
2. Chỉ cho dashboard server và quy trình quản lý catalog đọc secret cần thiết.
3. Mã hóa khi lưu trữ và giới hạn quyền truy cập.
4. Rotation có kế hoạch để catalog và UAA client đồng bộ.
5. Hạn chế access token và refresh token theo session.
6. Thu hồi session/token khi logout hoặc khi phát hiện compromise.
7. Không lưu token trong browser localStorage.
8. Redact Authorization header và token body khỏi log.

Nếu dashboard client secret bị lộ, attacker có thể giả mạo client trong token exchange nếu còn đáp ứng điều kiện OAuth. Cần rotation và điều tra các token/session phát sinh trong khoảng thời gian bị lộ.

## 15. Session, cookie và CSRF trong dashboard

Sau khi OAuth hoàn tất, dashboard thường tạo session web riêng. Session này không thay thế Cloud Foundry permission check; nó chỉ duy trì trạng thái đăng nhập đã được xác thực.

Cookie session nên có:

- HttpOnly để JavaScript không đọc được.
- Secure để chỉ gửi qua HTTPS.
- SameSite phù hợp với redirect flow và cách triển khai.
- Path/domain giới hạn.
- Thời hạn hợp lý và rotation sau login.
- Session ID mới sau khi xác thực để chống session fixation.

Các request thay đổi dữ liệu phải có CSRF protection nếu dùng cookie-based authentication. OAuth state bảo vệ mối liên hệ của authorization request/callback; nó không tự động thay thế CSRF token cho mọi form hoặc API mutation của dashboard.

Khi logout:

- Hủy session server-side.
- Xóa cookie với cùng Path/Domain attributes.
- Xóa token khỏi server-side store theo policy.
- Nếu cần, gọi revocation endpoint của UAA theo khả năng deployment.
- Không giả định logout khỏi dashboard tự động logout toàn bộ Cloud Foundry/UAA session của browser.

## 16. Dashboard backend API phải kiểm tra quyền ở mọi thao tác

Một lỗi phổ biến là kiểm tra manage/read khi tải trang đầu tiên rồi coi toàn bộ request sau đó đều được phép. Người dùng có thể giữ tab mở trong khi administrator thu hồi quyền, hoặc gọi API trực tiếp mà không qua giao diện.

Mỗi endpoint quản lý cần:

1. Xác thực dashboard session.
2. Lấy instance identity từ server-side session hoặc opaque reference.
3. Tải instance và xác minh platform/tenant ownership.
4. Kiểm tra permission còn hiệu lực theo policy.
5. Kiểm tra action cụ thể được phép.
6. Ghi audit.
7. Thực hiện nghiệp vụ qua service/domain layer.
8. Trả dữ liệu đã lọc theo quyền.

Ví dụ pseudo-controller:

~~~java
@PostMapping("/instances/{reference}/backup")
public Mono<ResponseEntity<Void>> createBackup(
        @PathVariable String reference,
        Principal principal) {

    return dashboardAccessService
        .requireManage(principal, reference)
        .then(backupService.start(reference))
        .thenReturn(ResponseEntity.accepted().build());
}
~~~

Đây là ví dụ cấu trúc; DashboardAccessService phải xác minh session, instance ownership và permission. Không chỉ kiểm tra một role tĩnh trên principal.

Nếu permission endpoint hoặc Cloud Controller tạm thời không truy cập được, thao tác nhạy cảm nên fail closed hoặc chuyển sang trạng thái không thể quản lý tạm thời. Không tự động coi lỗi kết nối là manage=true.

## 17. Hỗ trợ nhiều Cloud Foundry foundation

Một broker có thể được đăng ký trên nhiều Cloud Foundry instance. Khi đó, dashboard phải biết instance được provision từ foundation nào vì mỗi foundation có thể dùng UAA khác nhau và Cloud Controller GUID khác nhau.

Cloud Foundry cung cấp hai cách thường dùng để phân biệt platform:

- Đăng ký broker với URL riêng hoặc credential riêng cho từng foundation.
- Dùng header X-Api-Info-Location để xác định info endpoint của foundation gửi request.

Spring Cloud Open Service Broker hỗ trợ platform instance ID trong broker path để broker phân biệt platform registration. Ví dụ một broker có thể được đăng ký ở các path khác nhau:

~~~text
https://broker.example.com/east/v2/catalog
https://broker.example.com/west/v2/catalog
~~~

Trong request model, framework có thể cung cấp platform instance ID và API info location theo phiên bản. Broker nên lưu các giá trị này cùng instance thay vì suy đoán từ dashboard hostname.

Mỗi instance cần giữ:

| Field | Mục đích |
|---|---|
| platform_instance_id | Registration/path scope của broker |
| api_info_location | URL info endpoint của foundation |
| authorization_endpoint | UAA endpoint đã resolve và xác minh |
| token_endpoint | UAA endpoint đã resolve và xác minh |
| cloud_controller_instance_guid | Định danh service instance trong foundation |
| internal_instance_id | Khóa nội bộ của broker |
| dashboard_reference | Opaque reference trong dashboard URL |

Không dùng một UAA endpoint global cho tất cả foundation nếu broker hỗ trợ multi-CF. Cũng không gọi endpoint được lấy từ request browser mà không xác minh registration và allowlist.

## 18. Tổ chức triển khai trong Spring Cloud Service Broker

Có thể tách phần OSB API và dashboard web thành hai khu vực:

~~~text
broker/
  catalog/
    ServiceCatalogConfiguration
    DashboardClientConfiguration
  instance/
    ServiceInstanceServiceImpl
    DashboardUrlFactory
    PlatformInfoLocationRepository
  dashboard/
    DashboardController
    DashboardSessionService
    DashboardOAuthClient
    DashboardAccessService
    DashboardInstanceRepository
  security/
    BrokerApiSecurityConfiguration
    DashboardWebSecurityConfiguration
    OAuthStateStore
    SecretProvider
  cloudfoundry/
    CloudFoundryInfoClient
    CloudControllerPermissionClient
  audit/
    DashboardAuditService
~~~

Các trách nhiệm:

- Catalog configuration công bố dashboard_client.
- Provision service tạo và lưu dashboard reference.
- DashboardUrlFactory sinh URL ổn định cho instance.
- Platform info repository lưu thông tin foundation đã xác minh.
- OAuth client thực hiện authorization code flow.
- DashboardAccessService gọi permissions endpoint.
- Controller chỉ render dữ liệu hoặc chuyển lệnh sau khi access check.
- Audit service ghi nhận truy cập và thao tác mà không chứa token/secret.

Không đặt toàn bộ OAuth flow và permission check trong một controller method dài. Tách các thành phần để kiểm thử redirect, token exchange, permission lookup và policy độc lập.

## 19. Ví dụ tích hợp dashboard URL trong provision service

Một service xử lý provision có thể tạo URL sau khi xác định instance và lưu metadata:

~~~java
@Service
public class BrokerServiceInstanceService
        implements ServiceInstanceService {

    private final ProvisionService provisionService;
    private final DashboardUrlFactory dashboardUrlFactory;

    public BrokerServiceInstanceService(
            ProvisionService provisionService,
            DashboardUrlFactory dashboardUrlFactory) {
        this.provisionService = provisionService;
        this.dashboardUrlFactory = dashboardUrlFactory;
    }

    @Override
    public Mono<CreateServiceInstanceResponse> createServiceInstance(
            CreateServiceInstanceRequest request) {

        return provisionService.accept(request)
            .map(result -> {
                String dashboardUrl =
                    dashboardUrlFactory.forInstance(result.dashboardReference());

                return CreateServiceInstanceResponse.builder()
                    .dashboardUrl(dashboardUrl)
                    .async(result.async())
                    .operation(result.operationId())
                    .build();
            });
    }
}
~~~

Ví dụ minh họa reactive API. ProvisionService phải lưu instance, platform identity, API info location và dashboard reference bền vững trước khi response được trả về. Nếu provision bất đồng bộ, dashboard URL vẫn có thể trỏ đến trang hiển thị trạng thái đang tạo.

Khi instance đã được retrieve, broker lấy dashboard URL từ record đã lưu:

~~~java
GetServiceInstanceResponse.builder()
    .dashboardUrl(dashboardUrl)
    .build();
~~~

Không tạo một URL mới ngẫu nhiên mỗi lần retrieve nếu platform mong đợi một liên kết ổn định. Nếu cần rotate dashboard reference, phải có quy trình chuyển tiếp và thu hồi reference cũ.

## 20. Kiểm tra permissions endpoint

Một client service có thể gọi Cloud Controller:

~~~http
GET https://api.cf.example.com/v3/service_instances/instance-guid-123/permissions
Authorization: Bearer <user-access-token>
~~~

Ví dụ response:

~~~json
{
  "manage": false,
  "read": true
}
~~~

Dashboard có thể ánh xạ kết quả vào một object nội bộ:

~~~java
public record InstancePermissions(
    boolean manage,
    boolean read
) {}
~~~

Policy:

~~~java
public Mono<DashboardAccess> resolveAccess(
        InstancePermissions permissions) {

    if (permissions.manage()) {
        return Mono.just(DashboardAccess.MANAGE);
    }

    if (permissions.read()) {
        return Mono.just(DashboardAccess.READ_ONLY);
    }

    return Mono.error(new AccessDeniedException(
        "User cannot access this service instance"
    ));
}
~~~

Ví dụ trên giả định manage=true bao gồm quyền hiển thị giao diện quản lý cần thiết. Nếu sản phẩm có thao tác đọc riêng hoặc trường hợp manage/read độc lập, hãy giữ cả hai cờ và quyết định theo từng capability thay vì gộp thành một enum đơn giản.

Không lưu permissions response vô thời hạn. Cloud Foundry administrators có thể thay đổi role/membership; dashboard cần kiểm tra lại khi người dùng bắt đầu SSO session và trước hành động nhạy cảm theo policy.

## 21. Phân biệt quyền Cloud Foundry và quyền nội bộ của service

Permissions endpoint cho biết người dùng có quyền manage/read đối với service instance theo Cloud Controller. Nó không tự động xác định mọi quyền nghiệp vụ bên trong service.

Ví dụ:

- Cloud Foundry cho phép user manage instance PostgreSQL.
- Dashboard có thể cho phép thay đổi maintenance window.
- Nhưng thao tác xóa backup có thể cần policy nội bộ khác hoặc approval.
- User có quyền read service instance vẫn không nhất thiết được xem password hoặc private key.
- Một instance có thể có nhiều database/schema với quyền nội bộ khác nhau.

Do đó, dashboard nên kết hợp quyền Cloud Foundry với policy nội bộ của service. Quyền Cloud Foundry là điều kiện cần để vào vùng quản lý instance; authorization domain của provider vẫn kiểm soát từng hành động cụ thể.

## 22. Xử lý lỗi SSO và quyền

| Tình huống | Xử lý |
|---|---|
| Thiếu dashboard_client trong catalog | Cloud Foundry không thể thiết lập Dashboard SSO cho service |
| cc-service-dashboards client thiếu authority | Cloud Controller không tạo/cập nhật dashboard UAA client |
| dashboard_client ID trùng | Broker registration/update có thể bị từ chối |
| redirect_uri không khớp | UAA từ chối token exchange hoặc callback |
| Authorization code hết hạn/đã dùng | Bắt đầu flow mới |
| state không khớp | Từ chối callback, không tạo session |
| Token exchange thất bại | Không hiển thị dashboard protected |
| Token hết hạn | Refresh theo policy hoặc yêu cầu login lại |
| Permissions endpoint trả manage=false/read=false | Từ chối truy cập instance |
| Permissions endpoint không khả dụng | Không cấp quyền quản lý dựa trên cache vô thời hạn |
| UAA endpoint không resolve được | Kiểm tra platform mapping và info endpoint |
| Dashboard URL reference không tồn tại | Trả not found, không dò instance khác |
| User mất quyền khi session còn mở | Từ chối thao tác tiếp theo và làm mới access state |
| Broker hỗ trợ nhiều CF nhưng dùng nhầm UAA | Không chấp nhận token/permission từ foundation khác |

Không hiển thị token, authorization code, client secret hoặc lỗi provider chi tiết trong trang lỗi. Ghi correlation ID để đội vận hành tìm log đã redaction.

## 23. Audit truy cập dashboard

Dashboard quản lý tài nguyên có thể thực hiện các thao tác ảnh hưởng đến dữ liệu production. Audit nên ghi:

| Field | Ý nghĩa |
|---|---|
| event_id | ID audit event |
| timestamp | Thời điểm |
| user_subject | Danh tính người dùng từ UAA |
| platform_instance_id | Cloud Foundry foundation/registration |
| service_instance_id | GUID service instance |
| internal_instance_id | Khóa nội bộ broker |
| action | VIEW, UPDATE_CONFIG, BACKUP, RESTORE, DELETE_RESOURCE |
| permission | manage/read đã kiểm tra |
| decision | ALLOW hoặc DENY |
| correlation_id | Liên kết request và operation |
| source_ip | IP theo proxy trust policy nếu cần |

Không ghi access token, refresh token, authorization code, client secret, database password hoặc URI có credential.

Audit cần được bảo vệ khỏi sửa/xóa trái phép và có retention policy. Có thể phát metric về login success/failure, permission denied, token exchange error và các hành động quản trị. Không dùng token hoặc user email làm metric label có cardinality cao.

## 24. Kiểm thử Dashboard SSO

Bộ kiểm thử nên bao phủ catalog, OAuth flow, permission lookup và từng API quản lý.

| Ca kiểm thử | Đầu vào | Kết quả mong đợi |
|---|---|---|
| Catalog có dashboard_client | Service bật SSO | JSON có id, secret và redirect_uri |
| Catalog không bật SSO | Service không dùng dashboard | Không công bố dashboard_client |
| Client ID trùng | Đăng ký broker | Phát hiện lỗi UAA client registration |
| Provision sync | Instance mới | Response có dashboard_url |
| Provision async | Operation đang chạy | Response ban đầu vẫn có dashboard_url |
| Dashboard URL | Reference hợp lệ | Resolve đúng instance |
| URL giả mạo | Reference không tồn tại | Không truy cập resource |
| Foundation A/B | Hai UAA khác nhau | Dashboard chọn đúng UAA của instance |
| X-Api-Info-Location giả | URL không thuộc allowlist | Từ chối hoặc không lưu |
| OAuth state | Callback có state đúng | Tiếp tục token exchange |
| OAuth CSRF | State sai/thiếu | Từ chối callback |
| Redirect URI sai | Callback khác cấu hình | UAA/token exchange thất bại |
| Token exchange | Code hợp lệ | Nhận token server-side |
| Secret handling | Kiểm tra browser/log | Client secret không lộ |
| Permission manage/read | manage=true, read=true | Dashboard cho phép chức năng tương ứng |
| Read-only | manage=false, read=true | Ẩn/khóa mutation và API từ chối mutation |
| No access | Cả hai false | Từ chối instance |
| Permission revoked | Admin thu hồi role | Lần SSO hoặc mutation kế tiếp bị từ chối |
| Token expired | Access token hết hạn | Refresh hợp lệ hoặc login lại |
| CSRF dashboard API | POST thiếu CSRF token | Từ chối |
| Logout | Session kết thúc | Cookie/session bị hủy |
| SSRF | Info URL trỏ IP nội bộ | Bị allowlist/policy chặn |

Nên dùng mock UAA và Cloud Controller cho unit/integration test, đồng thời có contract test với Cloud Foundry foundation test phù hợp. Kiểm tra cả server-side API, không chỉ screenshot hoặc trạng thái nút trên UI.

## 25. Những lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Nhầm dashboard_url với dashboard_client | Platform không biết URL instance hoặc OAuth client không được tạo | Tách URL instance và client service |
| Chỉ trả dashboard_url sau async completion | Platform không có link trong response ban đầu | Trả URL ngay từ provision response |
| Dùng một UAA endpoint cho mọi foundation | Token/permission kiểm tra sai platform | Lưu X-Api-Info-Location theo instance |
| Tin URL info từ browser | SSRF vào mạng nội bộ | Dùng URL platform đã xác minh và allowlist |
| Đưa client secret vào JavaScript | Lộ OAuth client credential | Token exchange server-side |
| Chỉ kiểm tra OAuth login | User có thể vào instance không thuộc quyền | Gọi permissions endpoint |
| Chỉ ẩn nút trên UI | API mutation vẫn bị gọi trực tiếp | Authorization ở mọi endpoint server-side |
| Cache manage=true vô thời hạn | User đã bị thu hồi quyền vẫn quản lý được | Kiểm tra lại SSO và action nhạy cảm |
| Yêu cầu scope quá rộng | Token có quyền lớn hơn nhu cầu | Chỉ yêu cầu scope tối thiểu |
| Không dùng state | Login CSRF hoặc callback injection | Sinh và xác minh state |
| Ghi token vào log | Lộ session người dùng | Redaction và secret-safe logging |
| Dùng dashboard reference như bearer token | Ai biết URL có thể truy cập dữ liệu | Reference chỉ định danh; luôn yêu cầu OAuth và permission check |
| Không xử lý user read-only | User có quyền đọc vẫn có thể gọi mutation | Kiểm tra manage/read riêng |
| Không audit thao tác | Khó điều tra thay đổi production | Audit action và decision |

## 26. Nguyên tắc cần ghi nhớ

Dashboard SSO của Cloud Foundry kết hợp ba thành phần: **dashboard_client** để đăng ký OAuth client cho service, **dashboard_url** để mở trang quản lý của một instance và UAA/Cloud Controller để xác thực người dùng cùng kiểm tra quyền trên instance đó.

Khi triển khai trong **SPRING_CLOUD_SERVICE_BROKER**, hãy giữ các nguyên tắc:

- Dashboard SSO là extension riêng của Cloud Foundry.
- Công bố dashboard_client trong catalog cho từng service hỗ trợ SSO.
- Phân biệt client cc-service-dashboards của Cloud Controller với dashboard client của service.
- Trả dashboard_url trong response provision ban đầu, kể cả provision async.
- Lưu platform identity và X-Api-Info-Location để tìm đúng UAA khi hỗ trợ nhiều foundation.
- Dùng OAuth Authorization Code Grant và bảo vệ callback bằng state.
- Giữ client secret và token ở server-side.
- Yêu cầu scope tối thiểu: openid và cloud_controller_service_permissions.read.
- Gọi permissions endpoint để xác định manage/read trên đúng service instance.
- Kiểm tra quyền ở server cho mọi API mutation; UI chỉ phản ánh quyền.
- Dùng HTTPS, secure session cookie, CSRF protection, SSRF allowlist và audit redacted.
- Không coi dashboard URL hoặc OAuth login thành bằng chứng quyền truy cập tài nguyên.

Khi các thành phần này được kết hợp đúng, người dùng Cloud Foundry có thể mở giao diện quản lý dịch vụ bằng danh tính nền tảng, còn broker và dashboard vẫn kiểm soát được quyền trên từng instance, từng thao tác và từng foundation.

## Tài liệu tham khảo

- [Cloud Foundry — Dashboard Single Sign-on](https://docs.cloudfoundry.org/services/dashboard-sso.html)
- [Cloud Foundry — Supporting multiple instances](https://docs.cloudfoundry.org/services/supporting-multiple-cf-instances.html)
- [Cloud Foundry — Managing Service Brokers](https://docs.cloudfoundry.org/services/managing-service-brokers.html)
- [Spring Cloud Open Service Broker 4.4.1 Reference](https://docs.spring.io/spring-cloud-open-service-broker/docs/4.4.1/reference/)
- [Spring Cloud Open Service Broker — DashboardClient API](https://docs.spring.io/spring-cloud-open-service-broker/docs/4.4.1/apidocs/org/springframework/cloud/servicebroker/model/catalog/DashboardClient.html)
- [Spring Cloud Open Service Broker — CreateServiceInstanceResponse API](https://docs.spring.io/spring-cloud-open-service-broker/docs/4.4.1/apidocs/org/springframework/cloud/servicebroker/model/instance/CreateServiceInstanceResponse.html)

