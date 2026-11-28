# Phân biệt service broker với service discovery, API gateway và message broker

Trong kiến trúc microservice và nền tảng cloud, bốn thuật ngữ *service broker*, *service discovery*, *API gateway* và *message broker* thường xuất hiện cùng nhau. Chúng đều đứng giữa các thành phần hoặc cung cấp một điểm truy cập chung, nhưng giải quyết bốn bài toán khác nhau: **cấp phát dịch vụ**, **tìm địa chỉ dịch vụ**, **điều phối lưu lượng API** và **truyền thông điệp**.

Trong module **SPRING_CLOUD_SERVICE_BROKER**, service broker được hiểu theo Open Service Broker API (OSB API). Đây là giao diện để một nền tảng như Cloud Foundry yêu cầu tạo, cập nhật, thu hồi hoặc binding một dịch vụ được quản lý. Spring Cloud Open Service Broker cung cấp nền tảng để xây dựng broker theo giao diện này bằng Spring.

Sau bài học, bạn cần phân biệt được vai trò của từng thành phần, nhận biết dữ liệu đầu vào và đầu ra của chúng, đồng thời giải thích được vì sao một hệ thống có thể sử dụng cả bốn mà không bị trùng trách nhiệm.

## 1. Service broker: quản lý vòng đời dịch vụ

Service broker cung cấp một giao diện quản trị để nền tảng hoặc người vận hành yêu cầu cấp phát và quản lý dịch vụ. Dịch vụ được cấp phát có thể là cơ sở dữ liệu, cache, message broker, object storage hoặc một dịch vụ SaaS bên ngoài.

Ví dụ, một nhóm phát triển muốn có một PostgreSQL riêng cho ứng dụng. Thay vì tự tạo máy chủ, cấu hình database, tạo tài khoản và phân phối mật khẩu, nhóm phát triển chọn một dịch vụ PostgreSQL trong catalog của nền tảng. Nền tảng gửi yêu cầu đến service broker. Broker gọi API của nhà cung cấp hoặc hệ thống hạ tầng để tạo database, lưu trạng thái và trả kết quả cho nền tảng.

Service broker tập trung vào **control plane**: mô tả dịch vụ có thể cung cấp, nhận yêu cầu thay đổi trạng thái và điều phối các thao tác lên tài nguyên. Nó không nhất thiết tự vận hành database hay lưu trữ dữ liệu ứng dụng. Nhiều broker chỉ là lớp tích hợp giữa nền tảng và API quản trị của nhà cung cấp.

### Catalog và service plan

Catalog cho nền tảng biết broker cung cấp những dịch vụ nào. Mỗi service có thể có nhiều plan, chẳng hạn:

- **postgresql** với các plan **small**, **standard** và **high-availability**.
- **redis** với các plan khác nhau về dung lượng và số replica.
- **object-storage** với các plan khác nhau về quota và chính sách lưu trữ.

Một mục catalog tối giản theo OSB API có dạng:

~~~json
{
  "services": [
    {
      "id": "postgres-service-id",
      "name": "postgresql",
      "description": "Managed PostgreSQL database",
      "bindable": true,
      "plans": [
        {
          "id": "postgres-small-plan-id",
          "name": "small",
          "description": "Một database với tài nguyên cơ bản"
        }
      ]
    }
  ]
}
~~~

**service_id** định danh dịch vụ; **plan_id** định danh gói cung cấp của dịch vụ đó. Các định danh này phải ổn định để nền tảng có thể tham chiếu nhất quán qua nhiều lần gọi API.

### Các thao tác trong vòng đời

OSB API chuẩn hóa các thao tác chính mà nền tảng gửi đến broker:

| Thao tác | Mục đích | Kết quả mong đợi |
|---|---|---|
| Catalog | Đọc danh sách service và plan | Nền tảng biết broker cung cấp gì |
| Provision | Tạo một service instance theo service và plan | Tài nguyên được tạo hoặc yêu cầu tạo được tiếp nhận |
| Update | Thay đổi cấu hình hoặc plan nếu dịch vụ hỗ trợ | Instance chuyển sang cấu hình mới |
| Bind | Tạo thông tin kết nối cho một ứng dụng hoặc consumer | Trả credentials và thông tin kết nối |
| Unbind | Hủy binding của một consumer | Credentials hoặc quyền truy cập tương ứng bị thu hồi |
| Deprovision | Thu hồi service instance | Tài nguyên được xóa hoặc đưa vào quy trình thu hồi |
| Last operation | Tra cứu tiến độ thao tác bất đồng bộ | Nền tảng biết thao tác đang chạy, thành công hay thất bại |

Một yêu cầu provision điển hình được gửi đến:

~~~http
PUT /v2/service_instances/{instance_id}?accepts_incomplete=true
Content-Type: application/json
~~~

~~~json
{
  "service_id": "postgres-service-id",
  "plan_id": "postgres-small-plan-id",
  "organization_guid": "org-123",
  "space_guid": "space-456",
  "parameters": {
    "database_name": "orders"
  }
}
~~~

**instance_id** xác định một lần cấp phát cụ thể. Broker dùng định danh này để theo dõi trạng thái và xử lý các lần retry. Nếu thao tác hoàn thành ngay, broker có thể trả kết quả thành công đồng bộ. Nếu cần thời gian để gọi cloud API, tạo tài nguyên hoặc chờ hệ thống bên ngoài, broker có thể chấp nhận thao tác bất đồng bộ và cung cấp mã operation để nền tảng truy vấn tiến độ qua **last_operation**.

Khi ứng dụng cần sử dụng dịch vụ, nền tảng gửi yêu cầu bind đến endpoint có dạng:

~~~http
PUT /v2/service_instances/{instance_id}/service_bindings/{binding_id}
Content-Type: application/json
~~~

Broker trả thông tin kết nối theo hợp đồng OSB API, thường nằm trong trường **credentials**:

~~~json
{
  "credentials": {
    "uri": "postgres://db.example.internal:5432/orders",
    "username": "orders_app",
    "password": "secret-value"
  }
}
~~~

Ứng dụng sử dụng thông tin binding để kết nối trực tiếp đến database. Trong môi trường thực tế, credentials phải được truyền qua kênh bảo mật, lưu trong kho bí mật phù hợp và không ghi vào log.

### Spring Cloud Open Service Broker đảm nhiệm phần nào?

Spring Cloud Open Service Broker là framework phía server giúp xây dựng ứng dụng broker tương thích OSB API trên nền Spring. Ứng dụng broker vẫn cần phần triển khai nghiệp vụ của mình, thường gồm:

1. **Catalog**: khai báo service, plan, khả năng bind và metadata cần công bố.
2. **Xử lý service instance**: thực hiện provision, update và deprovision theo yêu cầu.
3. **Xử lý binding**: tạo và thu hồi credentials hoặc quyền truy cập.
4. **Quản lý trạng thái**: lưu instance, binding, operation và kết quả xử lý để có thể phục hồi sau khi ứng dụng khởi động lại.
5. **Tích hợp nhà cung cấp**: gọi API quản trị của cloud, database, cache hoặc message broker thực tế.
6. **Bảo mật và vận hành**: xác thực lời gọi từ nền tảng, bảo vệ secrets, ghi nhận lỗi và hỗ trợ retry an toàn.

Framework giúp triển khai giao thức và cấu trúc xử lý theo OSB API; nó không tự biết cách tạo database hoặc tài nguyên cloud cụ thể của doanh nghiệp. Phần tích hợp nhà cung cấp và chính sách vòng đời vẫn thuộc về ứng dụng broker.

## 2. Service discovery: tìm vị trí của dịch vụ đang chạy

Service discovery giải quyết câu hỏi: **“Một service đang chạy ở đâu và tôi gọi nó bằng địa chỉ nào?”**

Trong hệ thống phân tán, địa chỉ IP hoặc cổng của một instance có thể thay đổi khi container được khởi động lại, pod được lập lịch sang node khác hoặc hệ thống tự động mở rộng. Nếu mỗi ứng dụng tự cấu hình địa chỉ của tất cả service, cấu hình sẽ nhanh chóng lỗi thời.

Service discovery cung cấp cơ chế đăng ký và tra cứu vị trí service. Tùy nền tảng, nó có thể dựa trên service registry, DNS, health check hoặc cơ chế khám phá tích hợp của hạ tầng.

Ví dụ:

- Service **order-service** cần gọi **inventory-service**.
- **inventory-service** có nhiều instance và địa chỉ có thể thay đổi.
- Cơ chế discovery cung cấp địa chỉ hoặc danh sách instance đang khả dụng.
- Client hoặc lớp cân bằng tải chọn một instance để gửi request.

Các công nghệ thường gặp gồm Kubernetes Service và DNS, Consul, Eureka và các cơ chế discovery tích hợp trong nền tảng cloud.

Điểm khác biệt quan trọng: service discovery tìm **địa chỉ của service đã tồn tại**. Nó không có trách nhiệm tạo một database mới, chọn service plan, cấp credentials hay thu hồi tài nguyên. Những công việc đó thuộc vòng đời của service broker.

Hai thành phần có thể phối hợp. Service broker có thể dùng service discovery để tìm endpoint của API quản trị nhà cung cấp. Ngược lại, broker cũng có thể cấp phát một dịch vụ discovery như một sản phẩm được quản lý. Việc phối hợp không làm hai vai trò trở thành một.

## 3. API gateway: tiếp nhận và điều phối lưu lượng API

API gateway là điểm vào tập trung cho các request API, thường nằm giữa client bên ngoài và các service phía sau. Nó giải quyết câu hỏi: **“Request đi vào hệ thống qua đâu, được định tuyến thế nào và phải áp dụng chính sách gì?”**

Một gateway có thể đảm nhiệm:

- Định tuyến request đến service phù hợp dựa trên path, host hoặc header.
- Xác thực, kiểm tra token và áp dụng chính sách phân quyền ở biên.
- Giới hạn tốc độ, quota và kích thước request.
- Kết thúc TLS, ghi nhận access log và thu thập metric.
- Biến đổi header hoặc request/response khi có yêu cầu tích hợp.

Ví dụ, client gọi **https://api.example.com/orders**. API gateway nhận request, kiểm tra token, áp dụng rate limit rồi chuyển tiếp đến **order-service**. Client không cần biết địa chỉ nội bộ hoặc số lượng instance của service.

Spring Cloud Gateway là một lựa chọn để xây dựng gateway trong hệ sinh thái Spring. Gateway có thể sử dụng service discovery để tìm instance đích, nhưng hai thành phần vẫn có trách nhiệm riêng: discovery tìm vị trí; gateway xử lý request và chính sách lưu lượng.

Service broker cũng có thể được đặt sau gateway để giới hạn truy cập đến API quản trị. Tuy nhiên, gateway chỉ chuyển tiếp và áp dụng chính sách cho request. Broker mới hiểu ý nghĩa của các thao tác OSB như provision, bind hay deprovision và chịu trách nhiệm điều phối vòng đời tài nguyên.

## 4. Message broker: truyền thông điệp giữa các thành phần

Message broker giải quyết câu hỏi: **“Làm thế nào để các thành phần trao đổi dữ liệu bất đồng bộ mà không cần gọi trực tiếp nhau tại cùng một thời điểm?”**

Producer gửi message đến queue, topic hoặc một cơ chế định tuyến. Consumer nhận và xử lý message theo mô hình mà hệ thống hỗ trợ. Message broker thường cung cấp một số khả năng như:

- Lưu message tạm thời hoặc bền vững.
- Định tuyến message đến queue hoặc subscriber phù hợp.
- Xác nhận xử lý (acknowledgement), retry và dead-letter.
- Tách thời điểm gửi khỏi thời điểm xử lý.
- Hỗ trợ các mô hình queue, publish/subscribe hoặc streaming.

Ví dụ, khi **order-service** tạo đơn hàng, nó phát sự kiện **OrderCreated**. Các consumer như **notification-service** và **analytics-service** có thể nhận sự kiện để gửi email hoặc cập nhật báo cáo. **order-service** không cần gọi trực tiếp từng consumer và không phải chờ tất cả consumer hoàn tất mới trả kết quả cho người dùng.

RabbitMQ và Apache Kafka là những công nghệ thường gặp trong nhóm này, dù mô hình lưu trữ, định tuyến và tiêu thụ message của chúng khác nhau.

Message broker xử lý **data plane của thông điệp**. Nó không mặc nhiên cung cấp catalog và plan theo OSB API, cũng không chịu trách nhiệm quản lý toàn bộ vòng đời dịch vụ cho nền tảng. Tuy nhiên, message broker hoàn toàn có thể là tài nguyên mà một service broker cấp phát. Chẳng hạn, service broker tạo một RabbitMQ instance, tạo user/vhost hoặc thông tin truy cập rồi trả credentials qua thao tác bind. Ứng dụng sau đó dùng credentials để gửi và nhận message.

## 5. So sánh trực tiếp bốn thành phần

| Tiêu chí | Service broker | Service discovery | API gateway | Message broker |
|---|---|---|---|---|
| Bài toán chính | Cấp phát và quản lý vòng đời dịch vụ | Tìm vị trí service đang chạy | Tiếp nhận và định tuyến request API | Truyền message giữa producer và consumer |
| Câu hỏi cần trả lời | Có thể tạo dịch vụ nào, theo plan nào và trạng thái ra sao? | Service cần gọi hiện ở địa chỉ nào? | Request đi vào đâu và áp dụng chính sách nào? | Message được gửi, lưu và chuyển đến consumer nào? |
| Đối tượng quản lý | Service instance, plan, binding, operation | Service registry, endpoint, instance khả dụng | Route, request, policy và lưu lượng | Queue, topic, message, consumer |
| Đầu vào thường gặp | Lệnh catalog, provision, update, bind, deprovision | Tên service hoặc truy vấn registry/DNS | HTTP request từ client | Message từ producer |
| Đầu ra thường gặp | Trạng thái thao tác, credentials, thông tin binding | Địa chỉ hoặc danh sách instance | HTTP response hoặc request đã được chuyển tiếp | Message được giao hoặc trạng thái xác nhận |
| Ví dụ công nghệ | Spring Cloud Open Service Broker, broker tương thích OSB API | Kubernetes DNS, Consul, Eureka | Spring Cloud Gateway | RabbitMQ, Apache Kafka |

Có thể ghi nhớ bằng bốn động từ:

- **Service broker: cấp phát** tài nguyên và quản lý vòng đời của nó.
- **Service discovery: tìm** địa chỉ của service đang hoạt động.
- **API gateway: định tuyến** request API và áp dụng chính sách lưu lượng.
- **Message broker: chuyển** message giữa các thành phần.

## 6. Một kịch bản sử dụng cả bốn thành phần

Giả sử một nền tảng cung cấp dịch vụ cho ứng dụng đặt hàng. Đội phát triển muốn có một RabbitMQ riêng để xử lý sự kiện, đồng thời ứng dụng cần gọi các microservice khác và tiếp nhận request từ client.

Quy trình có thể diễn ra như sau:

1. Nền tảng đọc catalog của service broker và hiển thị dịch vụ RabbitMQ cùng các plan.
2. Người dùng chọn một plan. Nền tảng gửi yêu cầu provision đến service broker.
3. Service broker gọi API quản trị hạ tầng để tạo RabbitMQ instance. Nếu tạo mất thời gian, broker xử lý bất đồng bộ và cập nhật tiến độ để nền tảng truy vấn.
4. Nền tảng yêu cầu bind. Service broker tạo thông tin truy cập và trả credentials cho ứng dụng.
5. Ứng dụng dùng credentials để kết nối RabbitMQ và gửi hoặc nhận message.
6. Khi **order-service** cần gọi **inventory-service**, service discovery giúp tìm instance phù hợp.
7. Khi client bên ngoài gọi API đặt hàng, API gateway tiếp nhận request, áp dụng chính sách rồi định tuyến đến **order-service**.

~~~mermaid
flowchart LR
    Platform["Nền tảng cloud"] -->|"Catalog / Provision / Bind"| SB["Service broker"]
    SB -->|"API quản trị"| Provider["Nhà cung cấp hạ tầng"]
    Provider --> Resource["RabbitMQ instance"]
    SB -->|"Credentials của binding"| App["Ứng dụng"]
    App -->|"Publish / Consume"| Resource
    App -->|"Tra cứu instance"| SD["Service discovery"]
    SD -->|"Địa chỉ service"| App
    Client["Client bên ngoài"] -->|"HTTP request"| GW["API gateway"]
    GW -->|"Route"| App
~~~

Trong sơ đồ, service broker chỉ tham gia vào giai đoạn cung cấp và quản lý tài nguyên. Sau khi được binding, ứng dụng giao tiếp trực tiếp với RabbitMQ theo giao thức của dịch vụ đó. Discovery hỗ trợ tìm các service nội bộ; gateway xử lý lưu lượng API đi từ bên ngoài vào hệ thống.

Một service broker có thể cấp phát RabbitMQ, nhưng không vì vậy mà nó trở thành nơi vận chuyển message. Tương tự, gateway có thể chuyển tiếp request đến broker, nhưng không thay broker xử lý quy tắc provision của OSB API.

## 7. Cách chọn đúng thành phần theo nhu cầu

Hãy bắt đầu từ vấn đề cần giải quyết:

| Nhu cầu | Thành phần phù hợp | Ví dụ |
|---|---|---|
| Cho phép nhóm phát triển tự chọn database, cache hoặc queue theo plan | Service broker | Người dùng yêu cầu database PostgreSQL riêng |
| Tìm một instance đang chạy khi địa chỉ thay đổi | Service discovery | **order-service** tìm **inventory-service** |
| Cung cấp một địa chỉ API chung và kiểm soát request từ bên ngoài | API gateway | Client gọi **api.example.com** |
| Gửi công việc hoặc sự kiện để consumer xử lý độc lập | Message broker | Phát sự kiện **OrderCreated** đến nhiều consumer |

Nếu hệ thống chỉ cần tra cứu địa chỉ một service đã được triển khai, service discovery là đủ. Nếu cần kiểm soát request HTTP đi vào hệ thống, hãy xem xét API gateway. Nếu cần giao tiếp bất đồng bộ và giảm phụ thuộc trực tiếp giữa producer với consumer, hãy dùng message broker. Nếu cần cung cấp dịch vụ theo catalog và plan, đồng thời tự động hóa provision, binding và deprovision trên nền tảng, service broker mới là thành phần phù hợp.

Một sản phẩm thực tế thường kết hợp các thành phần này. Ví dụ, nền tảng có thể dùng service broker để cấp phát một cụm Kafka; ứng dụng dùng cụm Kafka để truyền sự kiện; service discovery tìm các endpoint nội bộ; API gateway tiếp nhận request từ client. Mỗi thành phần có một hợp đồng và vòng đời riêng.

## 8. Những nhầm lẫn thường gặp

**Nhầm catalog với service registry.** Catalog của service broker mô tả những sản phẩm và plan có thể yêu cầu cấp phát. Service registry của discovery ghi nhận những instance đang chạy và vị trí của chúng. Một bên mô tả khả năng cung cấp; bên kia mô tả trạng thái khám phá tại thời điểm chạy.

**Cho rằng service broker phải trực tiếp chạy tài nguyên.** Broker có thể gọi API của nhà cung cấp để tạo tài nguyên ở một hệ thống khác. Trách nhiệm cốt lõi của broker là thực hiện hợp đồng vòng đời và phản ánh trạng thái nhất quán cho nền tảng.

**Cho rằng API gateway và service broker đều chỉ là REST proxy.** Cả hai có thể nhận HTTP request, nhưng gateway xử lý định tuyến và chính sách lưu lượng; service broker hiểu ngữ nghĩa của các thao tác OSB và thay đổi trạng thái tài nguyên.

**Cho rằng message broker và service broker là một.** Từ “broker” trong hai tên gọi không nói lên cùng một vai trò. Message broker vận chuyển message; service broker cấp phát và quản lý dịch vụ. Một message broker có thể là sản phẩm do service broker cung cấp.

**Cho rằng bind chỉ là trả về một URL.** Binding có thể bao gồm credentials, quyền truy cập và metadata kết nối. Khi unbind, broker cần thu hồi hoặc vô hiệu hóa quyền tương ứng theo chính sách của dịch vụ.

**Cho rằng mọi thao tác provision đều hoàn tất ngay.** Việc tạo tài nguyên cloud có thể kéo dài hoặc phụ thuộc hệ thống ngoài. Broker cần hỗ trợ trạng thái bất đồng bộ, cho phép nền tảng truy vấn tiến độ và xử lý retry mà không tạo trùng tài nguyên.

## 9. Những điểm cần chú ý khi triển khai bằng Spring Cloud Open Service Broker

Khi xây dựng broker, việc phân biệt bốn thành phần giúp xác định đúng ranh giới trách nhiệm. Một số nguyên tắc triển khai quan trọng gồm:

- **Duy trì trạng thái bền vững:** lưu quan hệ giữa **instance_id**, **binding_id**, service, plan và operation. Sau khi broker khởi động lại, nó vẫn phải biết tài nguyên nào đã được tạo và thao tác nào còn dang dở.
- **Thiết kế idempotency:** nền tảng có thể retry khi timeout hoặc mất kết nối. Cùng một định danh và cùng một yêu cầu phải được xử lý an toàn, tránh tạo nhiều tài nguyên ngoài ý muốn.
- **Xử lý bất đồng bộ có thể quan sát:** lưu operation ID, trạng thái, lỗi và thời điểm cập nhật. Endpoint tra cứu tiến độ phải phản ánh trạng thái thực tế của thao tác ở nhà cung cấp.
- **Quản lý lỗi từ hệ thống bên ngoài:** phân biệt lỗi tạm thời có thể retry với lỗi cấu hình hoặc yêu cầu không hợp lệ. Không đánh dấu thành công chỉ vì đã gửi request đến nhà cung cấp.
- **Bảo vệ credentials:** xác thực nền tảng gọi broker, phân quyền theo thao tác, hạn chế quyền của tài khoản được tạo, tránh ghi secrets vào log và hỗ trợ thu hồi khi unbind hoặc deprovision.
- **Kiểm soát vòng đời tài nguyên:** xử lý trường hợp tạo tài nguyên thành công ở nhà cung cấp nhưng broker bị lỗi trước khi lưu kết quả. Cần có chiến lược đối soát để phát hiện và xử lý tài nguyên mồ côi.
- **Tách adapter nhà cung cấp:** giữ logic OSB API độc lập với API cụ thể của AWS, Azure, database hoặc hệ thống nội bộ. Cách tổ chức này giúp thay đổi nhà cung cấp mà không làm thay đổi hợp đồng với nền tảng.

Với Cloud Foundry, service broker tương thích OSB API có thể tích hợp vào quy trình cung cấp dịch vụ của nền tảng. Trong Kubernetes, cách tích hợp phụ thuộc hệ sinh thái và phiên bản nền tảng: các hệ thống cũ từng dùng Service Catalog để kết nối broker OSB, trong khi các triển khai hiện đại có thể dùng operator hoặc cơ chế service binding riêng. Vì vậy, cần kiểm tra cơ chế tích hợp thực tế của nền tảng thay vì giả định mọi cụm Kubernetes đều hỗ trợ OSB API trực tiếp.

Khi thiết kế hệ thống, hãy xác định rõ ai yêu cầu cấp phát, ai quản lý trạng thái tài nguyên, ai tìm endpoint, ai xử lý request và ai vận chuyển message. Ranh giới rõ ràng giúp service broker trong Spring tập trung vào hợp đồng OSB, đồng thời phối hợp tốt với discovery, gateway và message broker trong toàn bộ nền tảng cloud.

