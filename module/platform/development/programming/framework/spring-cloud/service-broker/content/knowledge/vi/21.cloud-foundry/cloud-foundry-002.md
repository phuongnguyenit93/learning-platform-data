# Triển khai broker và đăng ký bằng cf create-service-broker

## Mục tiêu và bối cảnh

Cloud Foundry sử dụng Service Broker API để kết nối platform với các hệ thống cung cấp dịch vụ bên ngoài. Broker công bố catalog gồm service offering và plan; Cloud Controller đọc catalog, hiển thị dịch vụ trong marketplace và gọi broker khi người dùng tạo service instance, bind ứng dụng hoặc thu hồi dịch vụ.

Trong module Spring Cloud Service Broker, ứng dụng Spring triển khai các endpoint theo Open Service Broker API (OSB API). Để Cloud Foundry sử dụng được broker, người quản trị cần triển khai ứng dụng với một route có thể truy cập từ Cloud Controller, cấu hình xác thực, đăng ký broker bằng lệnh CLI và cấp quyền truy cập offering/plan cho các organization.

Bài học này tập trung vào quy trình triển khai và đăng ký broker bằng lệnh cf create-service-broker. Sau bài học, bạn có thể:

- Chuẩn bị ứng dụng broker, route HTTPS và credentials.
- Kiểm tra catalog mà broker công bố.
- Đăng ký broker với Cloud Controller.
- Phân biệt đăng ký broker với cấp quyền truy cập service offering.
- Kiểm tra marketplace và tạo service instance.
- Kiểm thử bind/unbind và theo dõi operation bất đồng bộ.
- Cập nhật credentials, route và catalog an toàn.
- Chẩn đoán lỗi kết nối, xác thực, catalog và lifecycle.

## 1. Kiến trúc tích hợp Cloud Foundry và service broker

Cloud Foundry không tự tạo database, queue hoặc bucket do broker quản lý. Cloud Controller điều phối request từ người dùng hoặc ứng dụng tới broker đã đăng ký.

~~~mermaid
flowchart TD
    U[Developer / Operator] --> CLI[Cloud Foundry CLI]
    CLI --> CC[Cloud Controller]
    CC -->|GET /v2/catalog| B[Spring Cloud Service Broker]
    B --> CAT[Catalog và Plans]
    CC -->|Provision / Bind / Update / Deprovision| B
    B --> DB[(Broker Database)]
    B --> AD[Backend Adapter]
    AD --> R[Database / Queue / Cloud Resources]
    CLI -->|Marketplace / Service commands| CC
~~~

Các thành phần chính:

| Thành phần | Trách nhiệm |
|---|---|
| Cloud Foundry CLI | Gửi lệnh quản trị và yêu cầu service tới Cloud Controller |
| Cloud Controller | Lưu đăng ký broker, đọc catalog, quản lý service offering/plan access và điều phối lifecycle |
| Service broker | Triển khai OSB API, xác thực platform, quản lý instance/binding và gọi backend |
| Broker database | Lưu catalog identity, instance, binding, operation và resource reference |
| Backend adapter | Tích hợp hệ thống thực tế như PostgreSQL, Redis, RabbitMQ hoặc cloud provider |

Luồng đăng ký không có nghĩa Cloud Foundry triển khai ứng dụng broker thay bạn. Trước tiên broker phải được deploy và có URL mà Cloud Controller truy cập được. Sau đó người quản trị mới đăng ký URL và credentials với Cloud Controller.

## 2. Chuẩn bị broker trước khi đăng ký

Trước khi chạy cf create-service-broker, cần hoàn tất các điều kiện sau:

- Ứng dụng Spring Boot đã được build và deploy.
- Broker có route ổn định, truy cập được từ mạng của Cloud Controller.
- Endpoint catalog của OSB API trả về dữ liệu hợp lệ.
- Broker yêu cầu xác thực theo cấu hình đã thống nhất với platform.
- TLS certificate hợp lệ nếu sử dụng HTTPS.
- Backend adapter và database đã được cấu hình.
- Các ID service và plan ổn định qua những lần deploy.
- Có log, health check và giám sát để vận hành.

Ví dụ URL broker:

~~~text
https://service-broker.example.com
~~~

Cloud Controller sẽ gọi các endpoint OSB API theo URL đã đăng ký, chẳng hạn /v2/catalog. Vì vậy, cần xác nhận base URL, route và path mapping khớp với ứng dụng. Không đăng ký URL của trang quản trị hoặc health endpoint thay cho API broker.

### 2.1. Kiểm tra endpoint catalog

Trước khi đăng ký, dùng một HTTP client để gọi catalog với credentials đã cấu hình:

~~~http
GET /v2/catalog HTTP/1.1
Host: service-broker.example.com
Authorization: Basic <broker-username-and-password>
X-Broker-API-Version: <supported-version>
Accept: application/json
~~~

Một catalog minh họa:

~~~json
{
  "services": [
    {
      "id": "4d2c1d7a-0c52-4c42-9e33-18f6b38a2a11",
      "name": "managed-postgresql",
      "description": "PostgreSQL database service managed by the broker",
      "bindable": true,
      "plans": [
        {
          "id": "8c0e9f3d-7a8a-4b24-9d62-2d65e3c6f010",
          "name": "standard",
          "description": "Standard PostgreSQL plan"
        }
      ]
    }
  ]
}
~~~

Các ID trong ví dụ là định danh minh họa. Khi triển khai thật, service ID và plan ID phải duy nhất, ổn định và không được tạo UUID mới mỗi lần ứng dụng khởi động. Cloud Controller lưu và tham chiếu các định danh này khi quản lý service offering và instance.

Kiểm tra thêm:

- name dễ hiểu và ổn định.
- description mô tả đúng dịch vụ.
- bindable phản ánh broker có hỗ trợ binding hay không.
- Mỗi plan có ID và tên ổn định.
- Plan metadata và capability phản ánh đúng chức năng thực tế.
- Catalog không chứa credentials hoặc thông tin backend bí mật.
- Endpoint trả đúng JSON và status code theo OSB API.

### 2.2. Kiểm tra xác thực và TLS

Nếu broker dùng HTTP Basic, Cloud Controller sẽ gửi credentials được cấu hình khi đăng ký trong các request tới broker. Broker cần kiểm tra chúng ở mọi endpoint được bảo vệ, không chỉ catalog.

Ưu tiên HTTPS với certificate hợp lệ. Tránh dùng HTTP không mã hóa trên mạng không tin cậy vì credentials broker có thể bị lộ. Nếu môi trường dùng CA nội bộ, cần bảo đảm Cloud Controller tin cậy certificate chain theo cấu hình platform.

## 3. Chuẩn bị credentials cho broker

Cloud Foundry cần một cặp credentials để xác thực khi gọi broker. Đây là credentials giữa platform và broker, không phải credentials mà ứng dụng cuối dùng để kết nối PostgreSQL hoặc Redis.

Nên tạo một tài khoản service riêng cho Cloud Controller:

- Username dành riêng cho broker registration.
- Password ngẫu nhiên đủ mạnh.
- Quyền chỉ đủ để truy cập OSB API của broker.
- Không dùng chung với tài khoản quản trị database hoặc tài khoản người dùng.
- Có quy trình rotate và cập nhật credentials.

Ví dụ biến môi trường minh họa cho ứng dụng Spring:

~~~yaml
broker:
  security:
    username: BROKER_API_USERNAME
    password: BROKER_API_PASSWORD
~~~

Đây là cấu hình ứng dụng do nhóm phát triển định nghĩa, không phải property mặc định bắt buộc của Spring Cloud Open Service Broker. Hãy nối nó với security configuration thực tế của project và cấp giá trị qua secret store hoặc cơ chế bảo mật của môi trường triển khai.

Không commit password vào Git, Docker image hoặc file manifest dùng chung. Nếu cần cập nhật credentials, phải phối hợp thay đổi ở broker và Cloud Controller để không tạo khoảng thời gian hai bên dùng giá trị khác nhau.

## 4. Đăng nhập và chọn API endpoint của Cloud Foundry

Trước khi đăng ký broker, người vận hành cần đăng nhập vào đúng Cloud Foundry foundation và chọn organization/space phù hợp cho các bước kiểm thử.

~~~bash
cf api https://api.example-cf.com
cf login
cf target -o platform-ops -s broker-validation
~~~

Ý nghĩa:

- cf api chọn API endpoint của foundation.
- cf login xác thực người vận hành.
- cf target chọn organization và space cho các thao tác CLI phụ thuộc target.

Đăng ký service broker là thao tác quản trị. Tài khoản CLI cần role phù hợp, thường là quyền administrator của foundation. Developer thông thường không thể tự đăng ký broker toàn cục.

Kiểm tra target trước khi chạy lệnh quản trị để tránh thao tác nhầm foundation hoặc nhầm organization. Lệnh cf create-service-broker đăng ký broker ở phạm vi platform; việc cấp quyền sử dụng offering cho organization được thực hiện ở bước riêng.

## 5. Đăng ký broker bằng cf create-service-broker

Cú pháp CLI:

~~~bash
cf create-service-broker BROKER USERNAME PASSWORD URL
~~~

Ví dụ:

~~~bash
cf create-service-broker spring-cloud-broker broker-cf-user "<broker-password>" https://service-broker.example.com
~~~

Các tham số:

| Tham số | Ý nghĩa |
|---|---|
| BROKER | Tên đăng ký broker trong Cloud Foundry |
| USERNAME | Username Cloud Controller dùng khi gọi broker |
| PASSWORD | Password tương ứng |
| URL | Base URL của OSB API broker |

Tên đăng ký spring-cloud-broker là tên quản trị trong Cloud Foundry. Nó khác với tên service offering trong catalog, ví dụ managed-postgresql.

Sau khi chạy lệnh thành công, Cloud Controller lưu đăng ký và có thể truy cập catalog của broker. CLI có thể hiển thị thông báo tạo broker thành công. Tuy nhiên, vẫn cần kiểm tra catalog và quyền truy cập service ở các bước tiếp theo.

Không đưa password thật vào tài liệu, shell history dùng chung hoặc log CI. Khi chạy trong môi trường thật, dùng secret management hoặc cơ chế nhập credentials an toàn được CLI và môi trường hỗ trợ.

### 5.1. Kiểm tra broker đã đăng ký

Dùng lệnh:

~~~bash
cf service-brokers
~~~

Lệnh này liệt kê các broker đã đăng ký và giúp xác nhận tên broker xuất hiện trong danh sách. Đây là bước kiểm tra đăng ký ở cấp platform; nó chưa chứng minh người dùng trong organization đã nhìn thấy service offering.

Nếu broker không xuất hiện:

- Kiểm tra người dùng CLI có quyền administrator.
- Kiểm tra lệnh đã chạy trên đúng foundation.
- Đọc thông báo lỗi từ Cloud Controller.
- Xác minh URL broker và credentials.
- Kiểm tra route và TLS từ góc nhìn mạng của Cloud Controller.

## 6. Cấp quyền truy cập service offering và plan

Đăng ký broker và công bố service cho organization là hai việc khác nhau. Sau khi broker đăng ký thành công, Cloud Controller đọc catalog để biết offering và plan. Administrator vẫn cần enable service access cho organization hoặc phạm vi mong muốn.

Kiểm tra quyền hiện tại:

~~~bash
cf service-access
~~~

Cấp quyền truy cập một service offering:

~~~bash
cf enable-service-access managed-postgresql
~~~

Nếu muốn chỉ cấp một plan:

~~~bash
cf enable-service-access managed-postgresql --plan standard
~~~

Nếu chỉ cấp cho một organization:

~~~bash
cf enable-service-access managed-postgresql --org product-team
~~~

Có thể kết hợp các tùy chọn theo cú pháp của phiên bản CF CLI đang dùng. Hãy kiểm tra cf help enable-service-access trên CLI mục tiêu nếu phiên bản có khác biệt.

Sau khi enable, developer trong phạm vi được cấp quyền có thể tìm service trong marketplace. Nếu offering hoặc plan chưa được enable, lệnh marketplace có thể không hiển thị dịch vụ đó cho organization hiện tại.

### 6.1. Kiểm tra marketplace

~~~bash
cf marketplace
~~~

Lệnh hiển thị các service offering mà user hiện tại được phép truy cập. Kiểm tra:

- Tên service đúng với catalog.
- Description hiển thị đúng.
- Các plan được enable xuất hiện.
- Plan không được cấp quyền không xuất hiện trong phạm vi organization đó.

Nếu broker đã đăng ký nhưng marketplace không có service, kiểm tra service access trước khi kết luận catalog bị lỗi.

## 7. Tạo service instance từ marketplace

Sau khi offering và plan được enable, developer có thể tạo instance:

~~~bash
cf create-service managed-postgresql standard orders-db
~~~

Trong đó:

- managed-postgresql là service offering name.
- standard là plan name.
- orders-db là tên instance trong Cloud Foundry.

Nếu service hỗ trợ parameters, có thể truyền file JSON:

~~~bash
cf create-service managed-postgresql standard orders-db -c service-config.json
~~~

Ví dụ file cấu hình:

~~~json
{
  "storage_gb": 100,
  "backup_enabled": true,
  "region": "ap-southeast-1"
}
~~~

Broker cần validate parameters theo schema và policy của service/plan. Không tin dữ liệu từ file cấu hình là hợp lệ chỉ vì Cloud Foundry đã gửi request.

Cloud Controller gửi request provision tới broker. Nếu thao tác hoàn tất đồng bộ, broker trả response hoàn tất theo OSB API. Nếu broker yêu cầu async và client chấp nhận incomplete operation, broker có thể trả 202 cùng operation token; Cloud Controller sẽ theo dõi trạng thái qua last operation.

### 7.1. Theo dõi quá trình tạo instance

~~~bash
cf service orders-db
~~~

Lệnh hiển thị trạng thái service instance và thông tin operation theo khả năng của CLI/platform. Nếu provision bất đồng bộ, chờ cho đến khi Cloud Foundry báo instance đã được tạo thành công.

Nếu thất bại:

- Đọc thông báo từ CLI.
- Kiểm tra operation record và broker logs.
- Xác minh Cloud Controller có gọi được last_operation.
- Kiểm tra backend resource đã được tạo một phần hay chưa.
- Dùng reconciliation hoặc compensation để xử lý tài nguyên mồ côi.

Không gửi lặp create-service chỉ vì operation vẫn đang chạy. Hãy theo dõi operation hiện tại trước.

## 8. Bind service với ứng dụng

Nếu catalog khai báo service bindable, developer có thể bind instance cho application:

~~~bash
cf bind-service orders-api orders-db
~~~

Cloud Controller gửi request bind tới broker. Broker tạo hoặc cấp credentials riêng cho binding, ví dụ database username/password, URI hoặc token.

Với Cloud Foundry, thông tin binding thường được cung cấp cho ứng dụng qua environment variable VCAP_SERVICES sau khi ứng dụng được restage hoặc restart theo cách platform yêu cầu.

Kiểm tra biến môi trường:

~~~bash
cf env orders-api
~~~

Ví dụ cấu trúc minh họa của một entry trong VCAP_SERVICES:

~~~json
{
  "managed-postgresql": [
    {
      "name": "orders-db",
      "label": "managed-postgresql",
      "plan": "standard",
      "credentials": {
        "uri": "jdbc:postgresql://db.example.internal:5432/orders",
        "username": "<binding-user>",
        "password": "<binding-password>"
      }
    }
  ]
}
~~~

Không đưa credentials thật vào log hoặc tài liệu. Ứng dụng nên đọc binding credentials từ VCAP_SERVICES hoặc cơ chế binding được platform hỗ trợ thay vì hardcode endpoint và password.

### 8.1. Kiểm thử unbind và deprovision

Khi ứng dụng không còn cần binding:

~~~bash
cf unbind-service orders-api orders-db
~~~

Broker phải thu hồi principal hoặc credentials của đúng binding. Unbind không được xóa service instance nếu còn consumer khác.

Khi không còn cần instance:

~~~bash
cf delete-service orders-db
~~~

Cloud Controller gửi deprovision request tới broker. Broker thu hồi tài nguyên instance theo chính sách, xử lý bất đồng bộ nếu được hỗ trợ và giữ trạng thái đủ để retry/reconciliation.

## 9. Cập nhật thông tin broker

Khi thay đổi route hoặc credentials, có thể cập nhật đăng ký bằng:

~~~bash
cf update-service-broker BROKER USERNAME PASSWORD URL
~~~

Ví dụ:

~~~bash
cf update-service-broker spring-cloud-broker broker-cf-user "<new-broker-password>" https://service-broker.example.com
~~~

Quy trình rotate credentials an toàn:

1. Tạo hoặc cấu hình credentials mới ở broker.
2. Cho phép broker xác thực giá trị mới.
3. Cập nhật đăng ký Cloud Foundry bằng cf update-service-broker.
4. Kiểm tra catalog và một request an toàn.
5. Thu hồi credentials cũ sau khi xác nhận Cloud Controller đã dùng cấu hình mới.

Nếu thay URL, cần triển khai route mới và kiểm tra TLS/network trước khi cập nhật đăng ký. Tránh xóa route cũ trước khi Cloud Controller chuyển sang URL mới.

### 9.1. Thay đổi catalog

Khi cập nhật catalog:

- Giữ nguyên service ID và plan ID của offering/plan đã tồn tại.
- Không đổi ID chỉ vì đổi description hoặc bổ sung metadata.
- Chỉ công bố plan mới khi backend có thể provision và quản lý plan đó.
- Không loại bỏ plan đang có instance hoạt động nếu chưa có kế hoạch migration.
- Kiểm tra service access sau khi catalog thay đổi.

Catalog là hợp đồng giữa broker và platform. Đổi ID có thể khiến Cloud Controller nhìn một offering/plan cũ thành một định danh khác và gây khó khăn cho lifecycle của instance hiện hữu.

## 10. Xóa hoặc ngừng cung cấp broker

Khi cần ngừng broker, hãy xác định trước các service instance và binding còn được quản lý. Việc xóa đăng ký broker không đồng nghĩa đã thu hồi tài nguyên backend.

Một quy trình ngừng cung cấp an toàn:

1. Ngừng cấp quyền truy cập mới cho offering/plan theo policy.
2. Thông báo và xử lý các instance đang hoạt động.
3. Unbind consumer theo quy trình.
4. Deprovision instance theo OSB API hoặc quy trình migration.
5. Xác nhận backend resources đã được xử lý.
6. Sau khi không còn phụ thuộc, administrator mới xóa đăng ký broker bằng lệnh CLI phù hợp.

Lệnh quản trị:

~~~bash
cf delete-service-broker spring-cloud-broker
~~~

Hành vi cụ thể khi còn service instance hoặc offering phụ thuộc phiên bản Cloud Controller và CLI. Kiểm tra điều kiện platform trước khi thực hiện. Không dùng thao tác purge service offering như một cách dọn dẹp nhanh nếu chưa xác định rõ ảnh hưởng tới instance và dữ liệu đang tồn tại.

## 11. Bảo mật và kết nối mạng

Broker cần được Cloud Controller truy cập, nhưng không nên mở quyền quản trị backend cho toàn bộ mạng platform.

Các nguyên tắc:

- Dùng HTTPS với certificate hợp lệ.
- Dùng credentials riêng cho mỗi broker registration.
- Lưu password trong secret store hoặc cơ chế bảo mật tương đương.
- Chỉ cho phép Cloud Controller và thành phần được ủy quyền gọi OSB API.
- Không expose endpoint quản trị nội bộ ra route công khai.
- Xác thực mọi request OSB được bảo vệ.
- Kiểm tra tenant/ownership trước khi thay đổi instance hoặc binding.
- Giới hạn quyền backend service account.
- Ghi audit nhưng che credentials và parameters nhạy cảm.

Nếu broker chạy trong Cloud Foundry, cần kiểm tra network policy, security group và routing để Cloud Controller có thể kết nối tới route broker. Không chỉ kiểm tra bằng cách gọi URL từ máy laptop của developer; đường mạng từ Cloud Controller có thể khác.

## 12. Chẩn đoán lỗi đăng ký và sử dụng broker

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| cf create-service-broker trả 401 | Broker credentials sai hoặc security config không khớp | Kiểm tra username/password và Basic Auth |
| CLI báo không kết nối được broker | Route sai, DNS, TLS hoặc network | Kiểm tra URL từ môi trường Cloud Controller có thể truy cập |
| Broker đăng ký nhưng catalog lỗi | JSON sai hoặc endpoint catalog lỗi | Gọi GET /v2/catalog và xem broker log |
| cf service-brokers có broker nhưng marketplace không thấy service | Chưa enable service access hoặc catalog không có offering | Kiểm tra cf service-access và catalog |
| Service hiển thị nhưng plan không tạo được | Plan metadata hoặc backend provisioning lỗi | Kiểm tra plan ID, parameters và provision logs |
| cf create-service bị pending lâu | Worker/operation không hoàn tất hoặc last_operation lỗi | Kiểm tra operation, queue, worker và endpoint polling |
| Bind thất bại | Service không bindable hoặc backend credential creation lỗi | Kiểm tra bindable, binding handler và backend adapter |
| App không thấy credentials | Binding chưa hoàn tất hoặc app chưa restage/restart | Kiểm tra cf service, cf env và trạng thái app |
| Unbind thành công nhưng credential vẫn dùng được | Backend principal chưa bị revoke | Kiểm tra revoke logic và resource ownership |
| Update broker không thành công | URL/credentials mới không hợp lệ | Kiểm tra route và cấu hình broker trước khi rotate |

### 12.1. Kiểm tra log và operation

Nếu broker là ứng dụng Cloud Foundry, dùng CLI để xem log theo tên app broker:

~~~bash
cf logs spring-cloud-broker --recent
~~~

Nếu broker chạy ở nền tảng khác, dùng hệ thống log/trace của môi trường đó. Tìm theo correlation ID, instance ID hoặc operation ID; không đưa password hoặc token vào truy vấn log.

Với thao tác bất đồng bộ, kiểm tra:

- Operation đã được ghi bền vững chưa?
- Outbox event đã được publish chưa?
- Worker có claim operation không?
- Backend đã tạo hoặc xóa tài nguyên chưa?
- Last operation trả state đúng chưa?
- Có retry hoặc compensation đang chờ không?

## 13. Kiểm thử đăng ký trên môi trường không production

Trước khi công bố broker cho organization thật, nên kiểm thử trong một foundation hoặc org thử nghiệm.

Một checklist:

- [ ] Broker app đã deploy và route HTTPS hoạt động.
- [ ] GET /v2/catalog trả catalog hợp lệ.
- [ ] Cloud Controller xác thực được broker credentials.
- [ ] cf create-service-broker thành công.
- [ ] cf service-brokers liệt kê broker.
- [ ] cf service-access hiển thị quyền phù hợp.
- [ ] cf enable-service-access cho offering/plan dự kiến.
- [ ] cf marketplace hiển thị đúng service và plan.
- [ ] cf create-service tạo được instance.
- [ ] cf service hiển thị trạng thái provision.
- [ ] cf bind-service cấp credentials đúng consumer.
- [ ] Ứng dụng đọc được binding credentials.
- [ ] cf unbind-service thu hồi đúng principal.
- [ ] cf delete-service deprovision đúng instance.
- [ ] Request retry không tạo resource hoặc binding trùng.
- [ ] Log và audit không chứa secrets.

Dùng dữ liệu thử nghiệm và backend resource riêng. Không kiểm thử deprovision bằng cách trỏ vào database đang phục vụ production.

## 14. Quy trình triển khai hoàn chỉnh

Một quy trình có thể lặp lại cho mỗi lần triển khai broker:

1. Build và deploy Spring Cloud Service Broker.
2. Cấu hình route, TLS, credentials và backend connectivity.
3. Kiểm tra health và GET /v2/catalog.
4. Đăng nhập đúng Cloud Foundry foundation bằng tài khoản quản trị.
5. Chạy cf create-service-broker với tên, credentials và base URL.
6. Xác nhận bằng cf service-brokers.
7. Kiểm tra catalog và service access.
8. Chạy cf enable-service-access cho offering/plan và organization cần thiết.
9. Xác nhận bằng cf marketplace.
10. Tạo service instance thử nghiệm bằng cf create-service.
11. Theo dõi bằng cf service.
12. Bind ứng dụng, kiểm tra VCAP_SERVICES.
13. Thử unbind, deprovision và request retry.
14. Kiểm tra log, operation, audit và backend resource.
15. Chỉ sau khi xác minh mới mở quyền cho các organization khác.

## Kết luận

Đăng ký service broker với Cloud Foundry là quá trình kết nối một endpoint OSB API đã triển khai với Cloud Controller. cf create-service-broker lưu tên đăng ký, credentials và base URL để platform gọi broker; cf enable-service-access quyết định organization nào được sử dụng offering và plan; cf marketplace giúp xác nhận dịch vụ đã hiển thị.

Trong Spring Cloud Service Broker, hãy bảo đảm catalog có ID ổn định, endpoint HTTPS truy cập được từ Cloud Controller, credentials được quản lý an toàn và các handler provision/bind/unbind/deprovision hoạt động đúng. Sau khi đăng ký, kiểm thử toàn bộ lifecycle từ marketplace đến backend và chuẩn bị quy trình rotate credentials, cập nhật catalog, giám sát operation và ngừng cung cấp broker an toàn.
