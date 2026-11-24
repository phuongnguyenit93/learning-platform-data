# Công bố trang trạng thái, địa chỉ sức khỏe và cổng HTTPS

Eureka lưu thông tin định vị của từng service instance và có thể công bố thêm các URL để người vận hành hoặc ứng dụng khác truy cập trang chủ, trang trạng thái và endpoint sức khỏe của instance. Với Spring Cloud Netflix Eureka Client, các URL này được cấu hình thông qua thuộc tính của **eureka.instance**.

Khi ứng dụng chạy HTTPS, cần công bố đúng cổng bảo mật và giao thức để consumer tạo URL đến instance. Đồng thời, phải phân biệt cổng phục vụ API nghiệp vụ với cổng quản trị Actuator nếu ứng dụng dùng một management port riêng. Một cấu hình sai có thể khiến Eureka hiển thị địa chỉ không truy cập được, hoặc consumer cố gọi HTTP đến một service chỉ chấp nhận HTTPS.

Bài viết tập trung vào ba việc: công bố URL trang trạng thái, công bố health-check URL và khai báo cổng HTTPS trong Eureka Client. Nội dung cũng làm rõ mối quan hệ giữa Actuator, trạng thái sức khỏe được Eureka Client báo cáo và TLS giữa ứng dụng với Eureka Server.

## 1. Những URL Eureka có thể công bố

Một instance có thể công bố các địa chỉ sau:

| Thuộc tính | Mục đích | Ví dụ |
|---|---|---|
| Home page URL | Trang gốc hoặc trang giới thiệu service | https://inventory.internal/ |
| Status page URL | Trang thông tin/trạng thái để người vận hành xem | https://inventory.internal/actuator/info |
| Health check URL | Endpoint cung cấp thông tin sức khỏe | https://inventory.internal/actuator/health |
| Service URL | Địa chỉ và cổng mà consumer dùng để gọi API | https://inventory.internal:8443 |

Các URL trang chủ, trạng thái và sức khỏe được công bố cùng thông tin instance trong Eureka. Chúng giúp dashboard hoặc thành phần khác biết endpoint tương ứng. Chỉ khai báo một URL không có nghĩa Eureka Server sẽ liên tục gọi endpoint đó để kiểm tra sức khỏe. Cơ chế cập nhật trạng thái instance cần được cấu hình và hiểu riêng.

Spring Cloud Netflix cung cấp hai cách cấu hình URL:

- Dùng các thuộc tính dạng **url-path** khi URL có thể được tạo từ host, port và đường dẫn của instance.
- Dùng các thuộc tính dạng **url** khi cần công bố URL tuyệt đối, ví dụ khi endpoint chạy trên management port riêng hoặc nằm sau reverse proxy.

## 2. Công bố status page và health-check URL

Với một ứng dụng Spring Boot dùng Actuator, các endpoint thường gặp là:

- **/actuator/info:** cung cấp thông tin ứng dụng; có thể dùng làm status page.
- **/actuator/health:** cung cấp trạng thái sức khỏe tổng quát.

Đường dẫn mặc định có thể thay đổi nếu ứng dụng cấu hình **management.endpoints.web.base-path**, **management.server.base-path** hoặc context path. Vì vậy, URL công bố phải khớp với endpoint thực tế.

### Cấu hình đường dẫn tương đối

Nếu Actuator dùng cùng host và port với service, có thể khai báo đường dẫn:

~~~yaml
spring:
  application:
    name: inventory-service

management:
  endpoints:
    web:
      base-path: /actuator
      exposure:
        include: health,info

eureka:
  instance:
    status-page-url-path: /actuator/info
    health-check-url-path: /actuator/health
    home-page-url-path: /
~~~

Trong ví dụ, Eureka Client tạo URL từ thông tin instance và các path đã khai báo. Endpoint info và health cần thực sự được bật và có thể truy cập theo cấu hình mạng của ứng dụng. Actuator chỉ tạo endpoint khi có dependency phù hợp, thông thường là **spring-boot-starter-actuator**.

Nếu thay base path, ví dụ đặt thành **/manage**, cần cập nhật các path tương ứng:

~~~yaml
management:
  endpoints:
    web:
      base-path: /manage

eureka:
  instance:
    status-page-url-path: /manage/info
    health-check-url-path: /manage/health
~~~

Không nên giữ đường dẫn mặc định **/actuator/...** khi endpoint thực tế đã chuyển sang đường dẫn khác.

### Cấu hình URL tuyệt đối

Khi status page hoặc health endpoint nằm ở host, port hay đường dẫn khác, hãy khai báo URL tuyệt đối:

~~~yaml
eureka:
  instance:
    status-page-url: https://inventory-01.internal:9443/actuator/info
    health-check-url: https://inventory-01.internal:9443/actuator/health
    home-page-url: https://inventory-01.internal:8443/
~~~

URL tuyệt đối đặc biệt hữu ích khi:

- Management server chạy trên một port riêng.
- Ứng dụng nằm sau reverse proxy hoặc ingress.
- Host mà consumer truy cập khác hostname nội bộ của tiến trình.
- Đường dẫn công bố có prefix do gateway hoặc proxy thêm vào.

Địa chỉ phải có thể truy cập từ nơi sẽ sử dụng nó. Không công bố **localhost** nếu Eureka Dashboard hoặc consumer ở máy khác cần truy cập, vì localhost sẽ trỏ về chính máy của bên gọi.

## 3. Phân biệt status page với health status

Status page và health check có liên quan nhưng phục vụ hai mục đích khác nhau.

**Status page URL** là đường dẫn để xem thông tin ứng dụng hoặc trạng thái vận hành. Ví dụ **/actuator/info** có thể hiển thị phiên bản build, commit hoặc thông tin release đã được cấu hình. Nó không nhất thiết phản ánh ứng dụng có đủ điều kiện nhận request hay không.

**Health-check URL** là đường dẫn cung cấp kết quả kiểm tra sức khỏe. Với Actuator, **/actuator/health** trả về trạng thái tổng hợp từ các HealthIndicator đang được cấu hình.

**Eureka instance status** là trạng thái mà Eureka Client công bố với registry, chẳng hạn UP, DOWN, OUT_OF_SERVICE hoặc trạng thái khác tùy cơ chế. URL health được công bố không tự động đồng nghĩa Eureka Server đang chủ động gọi URL đó. Nếu muốn trạng thái Actuator được phản ánh vào Eureka, cần bật health-check integration của Eureka Client.

~~~mermaid
flowchart TD
    APP["Spring Boot application"]
    APP --> INFO["Actuator /info"]
    APP --> HEALTH["Actuator /health"]
    HEALTH --> HC["HealthIndicator result"]
    HC -->|"eureka.client.healthcheck.enabled"| STATUS["Eureka Client instance status"]
    INFO --> META["Status page URL in Eureka metadata"]
    HEALTH --> URL["Health check URL in Eureka metadata"]
    STATUS --> REG[("Eureka Server")]
    META --> REG
    URL --> REG
~~~

Để tích hợp trạng thái Actuator với Eureka Client, cấu hình:

~~~yaml
eureka:
  client:
    healthcheck:
      enabled: true
~~~

Thuộc tính này nên đặt trong **application.yml** hoặc cấu hình ứng dụng tương đương, không đặt trong **bootstrap.yml**. Đặt sai giai đoạn nạp cấu hình có thể khiến client đăng ký trước khi health status được khởi tạo đúng và công bố trạng thái không mong muốn.

Khi bật tích hợp, Eureka Client sử dụng trạng thái sức khỏe của ứng dụng để cập nhật trạng thái instance theo cơ chế Spring Cloud Netflix. Điều này khác với việc chỉ công bố health-check URL cho dashboard hoặc consumer biết địa chỉ endpoint.

### Chọn HealthIndicator phù hợp

Actuator có thể tổng hợp trạng thái từ nhiều thành phần như database, disk space hoặc dependency khác. Nếu health endpoint phụ thuộc vào một hệ thống bên ngoài, sự cố của dependency có thể khiến service bị đánh dấu không khỏe dù nó vẫn có thể xử lý một số request.

Hãy xác định mục tiêu health check:

- **Liveness:** tiến trình có còn hoạt động và có cần khởi động lại không?
- **Readiness:** instance đã sẵn sàng nhận request nghiệp vụ chưa?
- **Dependency health:** các hệ thống phụ thuộc có đáp ứng không?
- **Registry status:** instance có nên được consumer chọn trong thời điểm hiện tại không?

Không nên đưa mọi kiểm tra phụ thuộc vào readiness nếu việc đó khiến toàn bộ service bị loại khỏi discovery trong khi một số chức năng vẫn hoạt động. Chọn nhóm health indicator và trạng thái công bố theo chính sách của hệ thống.

## 4. Khi management server dùng port riêng

Spring Boot cho phép chạy Actuator trên một port riêng thông qua **management.server.port**. Ví dụ, API nghiệp vụ chạy HTTPS ở port **8443**, còn Actuator chạy ở port **9443**.

~~~yaml
server:
  port: 8443
  ssl:
    enabled: true
    key-store: ${APP_KEYSTORE}
    key-store-password: ${APP_KEYSTORE_PASSWORD}
    key-store-type: PKCS12
    key-alias: inventory

management:
  server:
    port: 9443
    ssl:
      enabled: true
      key-store: ${APP_MANAGEMENT_KEYSTORE}
      key-store-password: ${APP_MANAGEMENT_KEYSTORE_PASSWORD}
      key-store-type: PKCS12
  endpoints:
    web:
      base-path: /actuator
      exposure:
        include: health,info

eureka:
  instance:
    non-secure-port-enabled: false
    secure-port-enabled: true
    secure-port: 8443
    home-page-url: https://inventory-01.internal:8443/
    status-page-url: https://inventory-01.internal:9443/actuator/info
    health-check-url: https://inventory-01.internal:9443/actuator/health
~~~

Trong cấu hình này:

- Port **8443** là cổng HTTPS của API nghiệp vụ mà consumer sử dụng.
- Port **9443** là cổng quản trị riêng, nơi Actuator cung cấp info và health.
- Eureka công bố service instance qua cổng bảo mật **8443**.
- Status page và health-check URL được đặt rõ ràng để trỏ đến management port **9443**.

Trong ví dụ, management server cũng bật HTTPS bằng cấu hình management.server.ssl. Hãy cấp keystore và password riêng qua secret manager hoặc biến môi trường, đồng thời bảo đảm chứng thư hợp lệ cho hostname và cổng 9443. Nếu management port được để HTTP, đổi scheme trong status-page-url và health-check-url thành http và giới hạn truy cập bằng mạng nội bộ hoặc cơ chế bảo vệ phù hợp.

Nếu management server dùng cùng port với API, có thể dùng các thuộc tính status-page-url-path và health-check-url-path thay cho URL tuyệt đối. Nếu dùng port riêng, URL tuyệt đối thường dễ kiểm soát hơn vì thể hiện rõ host, scheme và port.

## 5. Công bố cổng HTTPS cho Eureka

Khi instance chỉ phục vụ HTTPS, Eureka cần được thông báo rằng địa chỉ service phải sử dụng cổng bảo mật. Cấu hình thường dùng:

~~~yaml
eureka:
  instance:
    non-secure-port-enabled: false
    secure-port-enabled: true
    secure-port: 8443
~~~

Ý nghĩa:

- **secure-port-enabled: true:** đánh dấu cổng bảo mật của instance có hiệu lực.
- **secure-port: 8443:** khai báo cổng HTTPS mà instance sử dụng.
- **non-secure-port-enabled: false:** không công bố cổng HTTP như một cổng truy cập service hợp lệ.

Nếu ứng dụng phục vụ cả HTTP và HTTPS, có thể cấu hình cả hai cổng và cờ tương ứng theo chính sách triển khai. Khi chỉ muốn consumer dùng HTTPS, không để metadata công bố một cổng HTTP còn có thể truy cập.

### Cấu hình TLS cho ứng dụng Spring Boot

Một ví dụ cấu hình TLS:

~~~yaml
server:
  port: 8443
  ssl:
    enabled: true
    key-store: ${APP_KEYSTORE}
    key-store-password: ${APP_KEYSTORE_PASSWORD}
    key-store-type: PKCS12
    key-alias: inventory
~~~

Các giá trị keystore và password nên được cấp từ secret manager hoặc biến môi trường an toàn. Không commit mật khẩu, private key hay keystore production vào repository.

Eureka chỉ công bố thông tin cổng và trạng thái secure; nó không tự bật TLS trên ứng dụng provider. Provider phải thực sự cấu hình HTTPS và có chứng thư hợp lệ. Nếu Eureka công bố 8443 nhưng ứng dụng chỉ lắng nghe HTTP, consumer sẽ không thể kết nối đúng giao thức.

## 6. Phân biệt HTTPS đến service và HTTPS đến Eureka Server

Có hai kết nối TLS độc lập:

1. **Consumer đến service instance:** do cấu hình HTTPS của provider và các thuộc tính secure port trong Eureka quyết định.
2. **Eureka Client đến Eureka Server:** do URL của registry và cấu hình TLS/truststore của client quyết định.

Ví dụ cấu hình endpoint Eureka Server dùng HTTPS:

~~~yaml
eureka:
  client:
    service-url:
      defaultZone: https://eureka.internal:8761/eureka/
~~~

Thuộc tính defaultZone chỉ định địa chỉ mà Eureka Client dùng để giao tiếp với Eureka Server. Nó không tự làm cho service instance được công bố là HTTPS. Ngược lại, secure-port-enabled của instance không tự bật HTTPS cho kết nối client đến registry.

Với môi trường dùng chứng thư nội bộ hoặc CA riêng, JVM của ứng dụng phải tin cậy chứng thư server. Cấu hình truststore và client certificate nếu hạ tầng yêu cầu mutual TLS. Cần kiểm tra hostname verification, chuỗi chứng thư, thời hạn và quyền đọc secret khi khởi động.

~~~mermaid
flowchart LR
    C["Order Service"] -->|"HTTPS đến 8443"| I["Inventory Service"]
    I -->|"HTTPS đăng ký/heartbeat"| E[("Eureka Server")]
    C -->|"HTTPS discovery query"| E
    M["Actuator management port 9443"] -.->|"Health/status URL được công bố"| E
~~~

Trong sơ đồ, đường kết nối từ consumer đến provider dùng cổng HTTPS mà instance công bố. Kết nối registry là một luồng TLS riêng. Management endpoint có thể nằm trên port khác và được công bố bằng URL tuyệt đối.

## 7. Đường dẫn, context path và reverse proxy

URL công bố phải khớp với đường dẫn mà bên truy cập thực sự nhìn thấy. Một số cấu hình có thể làm thay đổi đường dẫn:

- **server.servlet.context-path** thêm prefix cho ứng dụng servlet.
- **management.endpoints.web.base-path** thay prefix của Actuator.
- Reverse proxy hoặc ingress có thể thêm, bỏ hoặc viết lại prefix.
- Management server có thể dùng port hoặc hostname riêng.

Ví dụ, nếu ứng dụng có context path **/inventory** và Actuator base path **/manage**, endpoint health có thể nằm tại **/inventory/manage/health** tùy cách cấu hình server và management context. Cần xác minh URL thực tế bằng request từ đúng mạng của consumer hoặc registry.

Nếu reverse proxy công bố địa chỉ bên ngoài khác địa chỉ nội bộ của ứng dụng, có thể dùng status-page-url và health-check-url tuyệt đối để công bố URL mà bên sử dụng có thể truy cập. Không quảng bá hostname nội bộ của container nếu consumer hoặc dashboard không phân giải được hostname đó.

## 8. Bảo vệ status page và health endpoint

Actuator có thể chứa thông tin về phiên bản, trạng thái dependency và chi tiết môi trường. Không nên mở toàn bộ endpoint quản trị ra Internet.

Một cấu hình exposure giới hạn:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info
  endpoint:
    health:
      show-details: when_authorized
~~~

Việc exposure endpoint và việc cho phép truy cập là hai vấn đề riêng. Spring Security, firewall, security group hoặc network policy cần giới hạn đối tượng có thể gọi endpoint. Nếu endpoint health được bảo vệ bằng xác thực, cần bảo đảm thành phần thực hiện kiểm tra có cơ chế xác thực phù hợp. Đừng giả định Eureka Server tự có credential để gọi URL health chỉ vì URL đã được đăng ký.

Một số nguyên tắc:

- Chỉ công bố các endpoint thật sự cần thiết.
- Không để env, configprops, heapdump, threaddump hoặc endpoint nhạy cảm mở công khai.
- Ẩn chi tiết health khi người gọi chưa được xác thực.
- Giới hạn health endpoint trong mạng nội bộ hoặc qua proxy được bảo vệ.
- Dùng TLS cho đường truyền có dữ liệu vận hành nhạy cảm.
- Không đưa password, token hoặc thông tin bí mật vào URL hay metadata Eureka.

## 9. Kiểm tra URL và cổng được công bố

Sau khi provider khởi động, cần xác minh cả thông tin trong registry lẫn khả năng truy cập thực tế.

1. Xác nhận ứng dụng đang lắng nghe đúng cổng HTTP/HTTPS.
2. Kiểm tra Actuator info và health từ mạng mà bên sử dụng URL có thể truy cập.
3. Mở Eureka Dashboard hoặc truy vấn registry để kiểm tra service ID và instance.
4. Xác nhận statusPageUrl và healthCheckUrl trỏ đúng scheme, host, port và path.
5. Xác nhận instance được đánh dấu secure và cổng HTTPS đúng với API nghiệp vụ.
6. Nếu management port riêng, xác minh URL Actuator trỏ đến đúng port quản trị.
7. Từ consumer, thử gọi API bằng HTTPS và xác nhận chứng thư được tin cậy.
8. Nếu dùng HTTPS đến Eureka Server, kiểm tra riêng kết nối registry và truststore.

### Bảng chẩn đoán nhanh

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Status URL trả về 404 | Sai base path, context path hoặc URL path | Kiểm tra endpoint Actuator thực tế và thuộc tính status-page-url-path |
| Health URL không truy cập được | Sai host, management port hoặc firewall | Dùng URL tuyệt đối và kiểm tra từ đúng mạng |
| Eureka công bố HTTP dù service chỉ hỗ trợ HTTPS | Cờ secure port chưa bật hoặc non-secure port vẫn được công bố | Bật secure port, tắt non-secure port nếu cần |
| Consumer kết nối HTTPS thất bại | Provider chưa bật SSL hoặc chứng thư không hợp lệ | Kiểm tra server SSL, trust chain và hostname |
| Eureka Client không kết nối được Eureka Server | URL registry, TLS hoặc truststore sai | Kiểm tra defaultZone, CA và chứng thư của registry |
| Instance vẫn UP dù health endpoint lỗi | Chưa bật health-check integration hoặc health indicator không phản ánh lỗi | Kiểm tra eureka.client.healthcheck.enabled và cấu hình Actuator |
| Instance DOWN dù API vẫn hoạt động | Health indicator kiểm tra dependency không cần thiết hoặc lỗi tạm thời | Rà soát readiness và các HealthIndicator |

## 10. Nguyên tắc cấu hình

- Dùng status-page-url-path và health-check-url-path khi endpoint nằm cùng host/port và có đường dẫn ổn định.
- Dùng status-page-url và health-check-url khi management port, hostname hoặc reverse proxy khác với địa chỉ service.
- Đảm bảo Actuator endpoint được tạo, expose và truy cập đúng phạm vi mạng.
- Phân biệt URL health được công bố với cơ chế đồng bộ health status của Eureka Client.
- Bật eureka.client.healthcheck.enabled trong cấu hình ứng dụng nếu muốn dùng trạng thái Actuator để cập nhật Eureka status.
- Bật secure-port-enabled và cấu hình secure-port khi service được phục vụ qua HTTPS; tắt cổng không bảo mật nếu không muốn consumer sử dụng HTTP.
- Cấu hình SSL thực tế cho provider; Eureka chỉ lưu thông tin cổng và URL.
- Cấu hình TLS/truststore cho kết nối đến Eureka Server riêng biệt với TLS của service instance.
- Kiểm tra URL từ mạng của bên sử dụng, không chỉ từ localhost của provider.
- Bảo vệ endpoint quản trị và không công bố bí mật trong metadata.

Khi URL trạng thái, health endpoint và secure port được công bố đúng, Eureka cung cấp thông tin nhất quán để người vận hành kiểm tra instance và consumer kết nối đúng giao thức. Cần nhớ rằng URL metadata, trạng thái sức khỏe do client báo cáo và cấu hình TLS là ba phần liên quan nhưng độc lập; cấu hình từng phần đúng mục đích giúp tránh endpoint không truy cập được và tránh định tuyến nhầm sang HTTP.
