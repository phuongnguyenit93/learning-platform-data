# Tùy chỉnh đường dẫn bằng spring.cloud.openservicebroker.base-path

Spring Cloud Open Service Broker cung cấp các endpoint HTTP để platform giao tiếp với service broker theo Open Service Broker API (OSB API). Theo cấu hình thông thường, các endpoint của API được đặt dưới đường dẫn phiên bản /v2, chẳng hạn GET /v2/catalog để lấy danh mục dịch vụ hoặc PUT /v2/service_instances/{instance_id} để yêu cầu cấp phát một service instance.

Trong môi trường thực tế, broker có thể được triển khai phía sau reverse proxy, API gateway hoặc dùng chung một domain với những ứng dụng khác. Khi đó, nhóm vận hành có thể cần đặt API broker dưới một tiền tố riêng, ví dụ /platform-broker/v2. Spring Cloud Open Service Broker hỗ trợ cấu hình đường dẫn cơ sở này bằng thuộc tính spring.cloud.openservicebroker.base-path.

Bài học trình bày ý nghĩa của thuộc tính, cách cấu hình trong Spring Boot, cách xác định URL thực tế mà platform cần gọi, mối quan hệ với context path và reverse proxy, cùng cách kiểm tra khi endpoint không hoạt động. Nội dung áp dụng cho dự án xây dựng broker bằng Spring Cloud, nơi catalog, plan, provision, update, binding và deprovision được cung cấp qua cùng một API.

## 1. Đường dẫn cơ sở của OSB API

OSB API định nghĩa các endpoint HTTP mà platform sử dụng để tương tác với broker. Một số endpoint tiêu biểu gồm:

| Chức năng | Đường dẫn theo mặc định |
|---|---|
| Lấy catalog | GET /v2/catalog |
| Tạo service instance | PUT /v2/service_instances/{instance_id} |
| Đọc trạng thái thao tác | GET /v2/service_instances/{instance_id}/last_operation |
| Cập nhật service instance | PATCH /v2/service_instances/{instance_id} |
| Tạo service binding | PUT /v2/service_instances/{instance_id}/service_bindings/{binding_id} |
| Thu hồi service binding | DELETE /v2/service_instances/{instance_id}/service_bindings/{binding_id} |
| Thu hồi service instance | DELETE /v2/service_instances/{instance_id} |

Các đường dẫn này là những route của API broker. Chúng không phải tên của service, plan hoặc instance. instance_id và binding_id là các định danh do platform gửi trong từng yêu cầu.

**Base path** là phần đường dẫn đứng trước các route nghiệp vụ. Trong cấu hình mặc định, phần này thường là /v2. Khi thay đổi base path thành /platform-broker/v2, các endpoint tương ứng sẽ trở thành:

| Chức năng | Đường dẫn sau khi tùy chỉnh |
|---|---|
| Lấy catalog | GET /platform-broker/v2/catalog |
| Tạo service instance | PUT /platform-broker/v2/service_instances/{instance_id} |
| Đọc trạng thái thao tác | GET /platform-broker/v2/service_instances/{instance_id}/last_operation |
| Cập nhật service instance | PATCH /platform-broker/v2/service_instances/{instance_id} |
| Tạo service binding | PUT /platform-broker/v2/service_instances/{instance_id}/service_bindings/{binding_id} |
| Thu hồi service binding | DELETE /platform-broker/v2/service_instances/{instance_id}/service_bindings/{binding_id} |
| Thu hồi service instance | DELETE /platform-broker/v2/service_instances/{instance_id} |

Có thể hình dung cách ghép đường dẫn như sau:

~~~text
URL endpoint
    = scheme + host + base path + route

Ví dụ:
    https://broker.example.com
    + /platform-broker/v2
    + /catalog

Kết quả:
    https://broker.example.com/platform-broker/v2/catalog
~~~

Base path giúp nhóm triển khai kiểm soát vị trí công khai của toàn bộ API OSB. Thay đổi nó ảnh hưởng đến tất cả endpoint thuộc broker, vì vậy platform, gateway và cấu hình kiểm thử phải sử dụng cùng một đường dẫn.

## 2. Thuộc tính spring.cloud.openservicebroker.base-path

Spring Cloud Open Service Broker cung cấp thuộc tính cấu hình:

~~~properties
spring.cloud.openservicebroker.base-path=/platform-broker/v2
~~~

Thuộc tính này xác định tiền tố đường dẫn được framework dùng để ánh xạ các endpoint OSB. Nếu ứng dụng không khai báo giá trị riêng, framework sử dụng đường dẫn mặc định theo phiên bản thư viện đang dùng, thông thường là /v2.

Khi cấu hình:

~~~yaml
spring:
  cloud:
    openservicebroker:
      base-path: /platform-broker/v2
~~~

thì route catalog được công bố dưới:

~~~http
GET /platform-broker/v2/catalog
~~~

Các route quản lý instance và binding cũng được đặt dưới cùng base path. Nhờ đó, broker có thể được triển khai tại một URL có tiền tố riêng mà không cần đổi từng controller hoặc viết lại từng endpoint.

Cần hiểu rõ ba thành phần:

- spring.cloud.openservicebroker: nhóm cấu hình của Spring Cloud Open Service Broker.
- base-path: thuộc tính xác định đường dẫn cơ sở của các route OSB.
- /platform-broker/v2: giá trị do ứng dụng lựa chọn để tạo tiền tố API.

Giá trị ví dụ /platform-broker/v2 chỉ minh họa một tiền tố triển khai. Hãy chọn đường dẫn phù hợp với kiến trúc mạng và cấu hình platform của môi trường thực tế.

### 2.1. Giữ phần phiên bản API trong đường dẫn

OSB API sử dụng namespace đường dẫn /v2 cho các endpoint phiên bản 2. Khi cần thêm một tiền tố triển khai, thông thường nên giữ phần /v2 ở cuối base path, ví dụ:

~~~text
/v2
/broker/v2
/platform/services/broker/v2
/internal/osb/v2
~~~

Cách đặt tên này giúp người vận hành nhận biết rõ API OSB phiên bản 2 khi xem URL trong gateway, log hoặc cấu hình platform.

Base path là cấu hình định tuyến HTTP. Nó không thay thế header phiên bản API mà platform gửi theo hợp đồng OSB. Ví dụ, header X-Broker-API-Version vẫn được xử lý theo phiên bản đặc tả mà broker hỗ trợ. Việc thay đổi URL không tự động nâng cấp hoặc hạ cấp khả năng của broker.

### 2.2. Chọn base path có chủ đích

Một base path nên ngắn, ổn định và không gây nhầm lẫn với các route quản trị khác. Tránh thay đổi nó tùy tiện giữa các lần phát hành, vì platform đã đăng ký broker bằng URL cũ có thể không gọi được endpoint sau khi đường dẫn thay đổi.

Một số nguyên tắc lựa chọn:

- Dùng cùng một quy ước cho tất cả môi trường, chỉ thay đổi hostname hoặc tiền tố khi kiến trúc triển khai yêu cầu.
- Không dùng tên môi trường tạm thời như /test-new-2 làm đường dẫn chính thức lâu dài.
- Tránh trùng với đường dẫn của trang quản trị, actuator hoặc API nghiệp vụ của ứng dụng.
- Ghi nhận base path trong tài liệu triển khai và cấu hình đăng ký broker trên platform.
- Kiểm tra quy tắc chuẩn hóa dấu / theo phiên bản framework đang dùng; sử dụng một giá trị nhất quán, dễ đọc, thường bắt đầu bằng dấu /.

## 3. Cấu hình trong Spring Boot

Spring Boot hỗ trợ khai báo thuộc tính trong application.yml hoặc application.properties. Với cấu hình phân cấp, YAML giúp dễ nhìn thấy nhóm thuộc tính của Spring Cloud Open Service Broker.

### 3.1. Cấu hình bằng application.yml

Ví dụ đặt broker tại /platform-broker/v2:

~~~yaml
spring:
  application:
    name: postgres-service-broker

  cloud:
    openservicebroker:
      base-path: /platform-broker/v2
~~~

Trong cấu hình trên, spring.application.name đặt tên ứng dụng Spring Boot. spring.cloud.openservicebroker.base-path đặt base path của API broker. Hai thuộc tính phục vụ hai mục đích khác nhau.

Khi ứng dụng chạy ở domain broker.example.com, URL catalog dự kiến là:

~~~text
https://broker.example.com/platform-broker/v2/catalog
~~~

Các endpoint khác được tạo từ cùng base path. Không cần khai báo riêng catalog-path, provision-path hay binding-path nếu framework đã cung cấp route tương ứng.

### 3.2. Cấu hình bằng application.properties

Nếu dự án dùng file properties, có thể khai báo cùng thuộc tính trên một dòng:

~~~properties
spring.application.name=postgres-service-broker
spring.cloud.openservicebroker.base-path=/platform-broker/v2
~~~

Hai cách cấu hình YAML và properties có ý nghĩa tương đương. Nên chọn một kiểu nhất quán với cấu trúc hiện tại của dự án để tránh các giá trị trùng lặp gây khó xác định cấu hình cuối cùng.

### 3.3. Cấu hình riêng theo profile

Một ứng dụng có thể chạy ở nhiều môi trường. Nếu mỗi môi trường có yêu cầu định tuyến khác nhau, có thể đặt base path trong file profile tương ứng.

Ví dụ:

~~~yaml
# application.yml
spring:
  cloud:
    openservicebroker:
      base-path: /v2
~~~

~~~yaml
# application-prod.yml
spring:
  cloud:
    openservicebroker:
      base-path: /platform-broker/v2
~~~

Khi chạy với profile prod, cấu hình profile được áp dụng theo cơ chế ưu tiên cấu hình của Spring Boot. Cần bảo đảm platform production đã đăng ký đúng URL mới.

Không nên để nhiều nguồn cấu hình cùng đặt giá trị khác nhau mà không xác định nguồn nào có độ ưu tiên cao hơn. Các nguồn thường gặp gồm file cấu hình, biến môi trường, tham số dòng lệnh và cấu hình được cung cấp khi triển khai container.

### 3.4. Ghi đè bằng biến môi trường

Quy tắc ánh xạ biến môi trường của Spring Boot cho phép biểu diễn thuộc tính dạng phân cấp bằng chữ in hoa và dấu gạch dưới. Tên biến tương ứng là:

~~~text
SPRING_CLOUD_OPENSERVICEBROKER_BASE_PATH
~~~

Ví dụ trong môi trường container:

~~~yaml
services:
  service-broker:
    image: example/postgres-service-broker:1.0
    environment:
      SPRING_CLOUD_OPENSERVICEBROKER_BASE_PATH: /platform-broker/v2
~~~

Đây là ví dụ cấu hình môi trường cho container; cần điều chỉnh image, network và các thiết lập bảo mật theo hệ thống triển khai thật.

Dùng biến môi trường hữu ích khi một image được dùng cho nhiều môi trường. Nhóm triển khai có thể thay đổi đường dẫn mà không cần đóng gói lại ứng dụng. Cần kiểm tra biến môi trường đã được truyền vào đúng container và không bị một nguồn cấu hình có độ ưu tiên cao hơn ghi đè.

### 3.5. Ghi đè bằng tham số dòng lệnh

Có thể truyền giá trị trực tiếp khi chạy ứng dụng:

~~~bash
java -jar service-broker.jar \
  --spring.cloud.openservicebroker.base-path=/platform-broker/v2
~~~

Tham số dòng lệnh phù hợp cho thử nghiệm hoặc một số kịch bản triển khai. Trong môi trường production, nên quản lý giá trị bằng hệ thống cấu hình hoặc biến môi trường của nền tảng để dễ kiểm soát và kiểm toán.

## 4. Base path khác gì context path của Spring Boot?

Đây là điểm dễ gây nhầm lẫn khi triển khai broker. spring.cloud.openservicebroker.base-path thuộc cấu hình định tuyến của các endpoint OSB. Trong khi đó, server.servlet.context-path là context path của ứng dụng web chạy trên Servlet container.

Ví dụ:

~~~yaml
spring:
  cloud:
    openservicebroker:
      base-path: /platform-broker/v2

server:
  servlet:
    context-path: /broker-app
~~~

Trong ứng dụng Spring MVC chạy với cấu hình Servlet này, đường dẫn công khai có thể bao gồm cả context path và base path:

~~~text
/broker-app/platform-broker/v2/catalog
~~~

Cần xác minh cách kết hợp này theo stack web và phiên bản Spring Cloud Open Service Broker của dự án. Nếu ứng dụng dùng WebFlux, không áp dụng máy móc thuộc tính dành riêng cho Servlet; hãy kiểm tra cấu hình server tương ứng.

Hai thuộc tính giải quyết hai lớp khác nhau:

| Thuộc tính | Phạm vi | Ví dụ |
|---|---|---|
| spring.cloud.openservicebroker.base-path | Tiền tố route OSB do framework ánh xạ | /platform-broker/v2 |
| server.servlet.context-path | Context path của ứng dụng Servlet | /broker-app |
| server.port | Cổng HTTP ứng dụng lắng nghe | 8080 |

Nếu chỉ cần thay đổi vị trí API OSB trong ứng dụng, hãy bắt đầu từ base-path. Nếu cần đặt toàn bộ ứng dụng dưới một tiền tố URL, context path có thể là lựa chọn phù hợp. Không nên thay đổi cả hai thuộc tính cùng lúc nếu chưa xác định rõ URL kết quả, vì dễ tạo ra đường dẫn lặp hoặc cấu hình không khớp với platform.

## 5. Tích hợp với reverse proxy hoặc API gateway

Trong môi trường production, broker thường không công khai trực tiếp cổng ứng dụng Spring Boot. Một reverse proxy hoặc API gateway có thể đảm nhiệm TLS termination, định tuyến theo hostname/path, giới hạn truy cập và chuyển tiếp request tới broker.

Ví dụ kiến trúc:

~~~mermaid
flowchart LR
    P[Cloud Foundry hoặc OSB client] -->|HTTPS| G[Reverse proxy / API gateway]
    G -->|HTTP nội bộ| B[Spring Boot service broker]
    B --> C[Spring Cloud Open Service Broker]
    C --> D[Catalog và lifecycle handlers]
~~~

Giả sử platform truy cập:

~~~text
https://services.example.com/platform-broker/v2/catalog
~~~

Có hai cách định tuyến thường gặp.

### 5.1. Gateway giữ nguyên tiền tố

Gateway chuyển tiếp nguyên path /platform-broker/v2/catalog tới broker. Khi đó ứng dụng backend cần ánh xạ route tương ứng với /platform-broker/v2/catalog.

Cấu hình spring.cloud.openservicebroker.base-path có thể được đặt là /platform-broker/v2, tùy cách gateway chuyển tiếp request và cách framework ánh xạ route.

### 5.2. Gateway loại bỏ tiền tố trước khi chuyển tiếp

Gateway có thể nhận request công khai ở /platform-broker/v2/catalog, sau đó loại bỏ /platform-broker trước khi gửi tới backend. Khi đó backend nhận:

~~~text
/v2/catalog
~~~

Trong mô hình này, base path phía ứng dụng có thể vẫn là /v2. Platform vẫn dùng URL công khai có tiền tố /platform-broker/v2.

Điều quan trọng là phân biệt **public path** mà platform gọi với **upstream path** mà backend nhận. Hai đường dẫn có thể giống nhau hoặc khác nhau tùy quy tắc rewrite của proxy.

Ví dụ minh họa với Nginx khi proxy loại bỏ tiền tố công khai:

~~~nginx
location /platform-broker/ {
    proxy_pass http://service-broker:8080/;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
}
~~~

Cách xử lý dấu / ở cuối location và proxy_pass có ảnh hưởng đến việc Nginx thay thế phần URI. Vì vậy, cần kiểm tra URL upstream thực tế trong môi trường thử nghiệm trước khi đưa vào production. Đoạn cấu hình trên chỉ minh họa ý tưởng rewrite path; hãy điều chỉnh theo topology và quy tắc proxy đang dùng.

### 5.3. Đăng ký URL đúng trên platform

Platform cần được cấu hình với URL công khai có thể truy cập tới catalog, ví dụ:

~~~text
https://services.example.com/platform-broker/v2
~~~

Tùy platform và công cụ đăng ký broker, trường endpoint có thể yêu cầu URL gốc hoặc URL API cụ thể. Hãy làm theo hợp đồng đăng ký của platform và kiểm tra request thực tế được gửi tới broker.

Nếu broker trả lời catalog tại URL nội bộ nhưng platform gọi URL công khai khác, cần kiểm tra lại các quy tắc rewrite và định tuyến. Không nên dùng URL backend nội bộ làm endpoint đăng ký cho platform nếu platform không thể truy cập mạng đó.

## 6. Base path và phiên bản OSB API

Base path là một phần của URL route. Phiên bản OSB API còn liên quan đến header phiên bản mà client gửi. Hai khái niệm này cần được quản lý độc lập.

Ví dụ request:

~~~http
GET /platform-broker/v2/catalog HTTP/1.1
Host: services.example.com
X-Broker-API-Version: 2.14
Authorization: Basic <credentials>
~~~

Trong ví dụ này:

- /platform-broker/v2 là base path đã tùy chỉnh.
- /catalog là route lấy danh mục.
- X-Broker-API-Version thể hiện phiên bản OSB API mà client muốn sử dụng.
- Authorization chứa thông tin xác thực theo cách platform và broker đã cấu hình.

Không nên coi việc thay đổi /v2 trong URL là cách nâng cấp API. Nếu broker hỗ trợ một phiên bản OSB API mới, cần xác minh framework và phần triển khai handler tương thích với phiên bản đó, đồng thời kiểm tra các yêu cầu về header và hành vi giao thức.

Khi thiết kế đường dẫn, nên giữ /v2 trong base path nếu framework và platform sử dụng quy ước endpoint OSB phiên bản 2. Nếu có lý do cần một cấu trúc URL khác, phải xác minh khả năng cấu hình của phiên bản thư viện, đặc tả mà platform hỗ trợ và cách đăng ký endpoint trước khi triển khai.

## 7. Kiểm tra endpoint sau khi cấu hình

Sau khi thay đổi base path, cần kiểm tra ứng dụng đã khởi động với cấu hình mong muốn và endpoint thực sự được ánh xạ đúng.

### 7.1. Kiểm tra catalog

Catalog là endpoint thuận tiện để xác nhận broker có thể được truy cập qua base path. Ví dụ:

~~~bash
curl -i \
  -H "X-Broker-API-Version: 2.14" \
  -u broker-user:broker-password \
  https://localhost:8443/platform-broker/v2/catalog
~~~

Đây là request minh họa. Thay hostname, cổng, thông tin xác thực và phiên bản API theo môi trường của bạn. Không đưa mật khẩu thật vào lịch sử shell hoặc tài liệu dùng chung; trong production nên dùng cơ chế quản lý secret phù hợp.

Nếu đường dẫn đúng, xác thực hợp lệ và broker có catalog, response sẽ chứa danh sách service. Nếu nhận 404 Not Found, cần xác định request có tới đúng ứng dụng hay không và base path backend có khớp với đường dẫn mà proxy chuyển tiếp hay không.

### 7.2. Kiểm tra các route khác

Không nên chỉ kiểm tra catalog rồi kết luận toàn bộ API hoạt động. Có thể xác minh route provision, last operation, binding và deprovision trong môi trường tích hợp bằng dữ liệu thử nghiệm.

Ví dụ đường dẫn cần kiểm tra:

~~~text
GET    /platform-broker/v2/catalog
PUT    /platform-broker/v2/service_instances/{instance_id}
GET    /platform-broker/v2/service_instances/{instance_id}/last_operation
PATCH  /platform-broker/v2/service_instances/{instance_id}
PUT    /platform-broker/v2/service_instances/{instance_id}/service_bindings/{binding_id}
DELETE /platform-broker/v2/service_instances/{instance_id}/service_bindings/{binding_id}
DELETE /platform-broker/v2/service_instances/{instance_id}
~~~

Các request thay đổi trạng thái phải được chạy với instance và binding thử nghiệm, đúng tham số và đúng quyền. Không dùng các lệnh provision hoặc deprovision thử nghiệm lên tài nguyên production.

### 7.3. Kiểm tra sau khi restart

Nếu cấu hình đến từ biến môi trường, profile hoặc tham số dòng lệnh, cần xác minh đúng cấu hình được nạp sau khi ứng dụng khởi động lại. Một thay đổi trong file cấu hình trên máy phát triển không bảo đảm container production đã nhận cùng giá trị.

Trong triển khai nhiều replica, tất cả replica của cùng broker cần có cấu hình route nhất quán. Nếu các replica ánh xạ base path khác nhau, request có thể thành công ngẫu nhiên tùy load balancer chuyển tới instance nào.

## 8. Các lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra và xử lý |
|---|---|---|
| 404 Not Found tại URL mới | Base path chưa được áp dụng hoặc URL client gọi sai | Kiểm tra cấu hình hiệu lực và route backend |
| Catalog hoạt động nhưng provision bị 404 | Gateway chỉ rewrite một số route hoặc route instance không được chuyển tiếp | Kiểm tra quy tắc proxy cho toàn bộ prefix |
| URL có tiền tố lặp, ví dụ /broker/broker/v2 | Context path và base path cùng chứa một tiền tố, hoặc proxy thêm prefix hai lần | Vẽ lại public path và upstream path, bỏ phần prefix bị lặp |
| Request tới được backend nhưng sai route | Proxy strip hoặc giữ prefix khác với cấu hình ứng dụng | Kiểm tra path mà backend thực sự nhận |
| Một số replica trả 404, replica khác thành công | Cấu hình base path giữa các replica không đồng nhất | Đồng bộ cấu hình deployment và rollout lại |
| Platform không lấy được catalog sau khi đổi path | URL đăng ký broker trên platform vẫn dùng đường dẫn cũ | Cập nhật endpoint broker trên platform theo quy trình quản trị |
| Request bị từ chối trước khi tới handler | TLS, xác thực, gateway policy hoặc network rule không phù hợp | Kiểm tra log gateway, trạng thái TLS và cấu hình xác thực |
| URL đúng nhưng client báo lỗi phiên bản API | Header X-Broker-API-Version không nằm trong phạm vi broker hỗ trợ | Kiểm tra phiên bản client, framework và đặc tả tương thích |

### 8.1. Phân biệt lỗi định tuyến và lỗi xác thực

404 Not Found thường gợi ý route không được ánh xạ hoặc request đến sai ứng dụng. 401 Unauthorized hoặc 403 Forbidden thường cho thấy request đã đến một lớp có kiểm tra xác thực/phân quyền nhưng thông tin truy cập không hợp lệ hoặc không đủ quyền.

Tuy nhiên, gateway có thể chủ động trả mã lỗi để che giấu tài nguyên. Vì vậy cần đối chiếu response với log ở gateway và broker, đồng thời tránh ghi thông tin xác thực hoặc nội dung nhạy cảm vào log.

### 8.2. Thay đổi base path là thay đổi endpoint tích hợp

Nếu platform đã đăng ký broker tại /v2, việc đổi base path sang /platform-broker/v2 có thể làm platform tiếp tục gọi đường dẫn cũ và nhận lỗi. Cần phối hợp cập nhật cấu hình đăng ký broker, kiểm tra khả năng chuyển đổi và chọn thời điểm triển khai phù hợp.

Với hệ thống production, có thể cần một giai đoạn chuyển tiếp trong đó gateway duy trì route cũ và route mới trong phạm vi được phép. Nếu duy trì song song, cả hai route phải đi tới cùng broker và áp dụng cùng chính sách bảo mật. Sau khi platform đã chuyển sang URL mới và xác nhận hoạt động, có thể loại bỏ route cũ theo kế hoạch vận hành.

## 9. Bảo mật khi công bố API dưới một base path tùy chỉnh

Base path chỉ là cấu hình URL, không phải cơ chế bảo mật. Đặt API dưới một đường dẫn khó đoán không thay thế xác thực, phân quyền hoặc mã hóa kết nối.

Khi triển khai broker, cần chú ý:

- Dùng HTTPS cho kết nối từ platform tới endpoint công khai.
- Bảo vệ thông tin xác thực broker và không ghi password, token hoặc secret vào log.
- Chỉ cho phép nguồn truy cập phù hợp tới các endpoint quản lý dịch vụ.
- Không công khai các endpoint quản trị hoặc actuator cùng chính sách truy cập với OSB API nếu không có chủ đích.
- Cấu hình proxy để chuyển tiếp đúng header cần thiết và không tin cậy header do client bên ngoài tự giả mạo.
- Kiểm tra cả URL công khai lẫn URL nội bộ để tránh vô tình mở broker trên mạng không được kiểm soát.

Đặc biệt, không nên nghĩ rằng một base path riêng như /hidden-broker/v2 sẽ làm endpoint an toàn. Người có quyền truy cập mạng vẫn có thể dò tìm URL. Bảo mật phải dựa trên TLS, xác thực, phân quyền, network policy và quản lý secret.

## 10. Quy trình cấu hình đề xuất

Khi cần thay đổi base path trong một dự án Spring Cloud Service Broker, có thể thực hiện theo trình tự:

1. Xác định URL hiện tại mà platform đang gọi và đường dẫn backend nhận được.
2. Chọn base path mới, giữ quy ước /v2 nếu cần duy trì endpoint OSB API phiên bản 2.
3. Khai báo spring.cloud.openservicebroker.base-path trong cấu hình phù hợp với môi trường.
4. Xác định gateway giữ nguyên hay loại bỏ tiền tố trước khi forward request.
5. Cập nhật URL đăng ký broker trên platform theo đúng endpoint công khai.
6. Khởi động lại hoặc rollout ứng dụng để nạp cấu hình mới.
7. Kiểm tra catalog và các route vòng đời trong môi trường thử nghiệm.
8. Kiểm tra log, xác thực, TLS và hành vi giữa các replica.
9. Cập nhật tài liệu vận hành để nhóm phát triển và platform administrator sử dụng cùng một URL.

Quy trình này giúp tránh trường hợp ứng dụng Spring đã đổi route nhưng platform hoặc gateway vẫn dùng cấu hình cũ.

## 11. Ví dụ hoàn chỉnh: broker dưới tiền tố /platform-broker/v2

Giả sử một tổ chức triển khai Spring Boot service broker trên cổng nội bộ 8080. API gateway công bố broker qua hostname services.example.com, với tiền tố /platform-broker/v2.

Cấu hình ứng dụng:

~~~yaml
spring:
  application:
    name: postgres-service-broker
  cloud:
    openservicebroker:
      base-path: /platform-broker/v2

server:
  port: 8080
~~~

Nếu gateway giữ nguyên URI khi chuyển tiếp, ứng dụng backend phải nhận request tại /platform-broker/v2/.... Nếu gateway loại bỏ /platform-broker trước khi chuyển tiếp, ứng dụng backend cần được cấu hình và ánh xạ phù hợp với path còn lại, chẳng hạn /v2/....

Platform sử dụng endpoint công khai:

~~~text
https://services.example.com/platform-broker/v2
~~~

Khi platform yêu cầu catalog, luồng xử lý là:

1. Platform gửi GET /platform-broker/v2/catalog qua HTTPS.
2. Gateway kiểm tra chính sách truy cập và chuyển tiếp request theo quy tắc rewrite.
3. Ứng dụng Spring nhận request tại route tương ứng với base path hiệu lực.
4. Spring Cloud Open Service Broker xử lý endpoint catalog.
5. Broker trả danh sách service và plan theo cấu hình catalog.
6. Gateway chuyển response về platform.

Các request provision, update, binding và deprovision đi qua cùng tiền tố. Phần logic vòng đời tài nguyên vẫn do các thành phần xử lý nghiệp vụ của broker đảm nhiệm.

~~~mermaid
sequenceDiagram
    participant P as Platform
    participant G as API Gateway
    participant A as Spring Boot Broker
    participant F as Open Service Broker Framework
    P->>G: GET /platform-broker/v2/catalog
    G->>A: Forward request theo path mapping
    A->>F: Route tới OSB catalog endpoint
    F-->>A: Catalog response
    A-->>G: HTTP response
    G-->>P: Danh sách service và plan
~~~

Ví dụ này cho thấy base path là một phần của hợp đồng kết nối giữa platform, gateway và broker. Mỗi thành phần cần thống nhất đường dẫn mà nó gửi, nhận hoặc chuyển tiếp.

## 12. Checklist trước khi đưa cấu hình vào production

- [ ] Đã xác định rõ base path hiện tại và base path mục tiêu.
- [ ] spring.cloud.openservicebroker.base-path được khai báo đúng trong nguồn cấu hình đang có hiệu lực.
- [ ] Giá trị base path thống nhất giữa các replica của broker.
- [ ] Đã phân biệt base path của OSB API với server.servlet.context-path.
- [ ] Đã xác định gateway giữ nguyên hay rewrite tiền tố URL.
- [ ] URL backend nhận được khớp với route do ứng dụng ánh xạ.
- [ ] Platform đã được cấu hình endpoint công khai chính xác.
- [ ] Catalog và các endpoint vòng đời đã được kiểm tra.
- [ ] Header phiên bản OSB API vẫn được gửi và xử lý đúng.
- [ ] TLS, xác thực, phân quyền và chính sách mạng đã được xác minh.
- [ ] Log không chứa thông tin xác thực hoặc secret.
- [ ] Có kế hoạch chuyển đổi nếu endpoint cũ đã được platform sử dụng.

spring.cloud.openservicebroker.base-path là điểm cấu hình tập trung để tùy chỉnh tiền tố của các endpoint OSB trong ứng dụng Spring. Khi dùng thuộc tính này, hãy xác định rõ URL công khai, đường dẫn backend và quy tắc rewrite của gateway. Một cấu hình đúng cần bảo đảm platform gọi được catalog và toàn bộ route vòng đời qua cùng một endpoint ổn định, trong khi xác thực và bảo mật vẫn được thực thi đầy đủ.

