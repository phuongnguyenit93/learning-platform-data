# Tự động đăng ký trong vòng đời ứng dụng Spring Boot

Trong kiến trúc microservice, một service instance cần xuất hiện trong service registry để các consumer có thể tìm thấy và gọi nó. Nếu phải tự đăng ký thủ công mỗi lần ứng dụng khởi động, đội phát triển sẽ phải quản lý thêm mã khởi tạo, thời điểm đăng ký, địa chỉ mạng, port và thao tác hủy đăng ký khi dừng ứng dụng.

Spring Cloud hỗ trợ tự động hóa phần lớn quy trình này thông qua tích hợp discovery của registry như Eureka hoặc Consul. Khi cấu hình đúng starter và thông tin dịch vụ, ứng dụng Spring Boot có thể tự đăng ký instance trong quá trình khởi động và thực hiện hủy đăng ký khi shutdown có kiểm soát.

Để hiểu cơ chế này, cần phân biệt ba vai trò: **ServiceRegistry** cung cấp thao tác đăng ký; **AutoServiceRegistration** điều phối đăng ký theo vòng đời ứng dụng; còn registry cụ thể như Eureka hoặc Consul lưu thông tin instance và cung cấp dữ liệu discovery cho consumer.

## 1. Tự động đăng ký giải quyết vấn đề gì?

Giả sử có một ứng dụng Spring Boot tên **inventory-service**, chạy ở port **8081**. Một ứng dụng khác là **order-service** cần tìm các instance của inventory-service để kiểm tra tồn kho.

Nếu không có cơ chế đăng ký tự động, đội phát triển có thể phải viết logic để:

1. Đọc service ID và thông tin địa chỉ của ứng dụng.
2. Kết nối đến registry.
3. Tạo bản ghi instance và gửi yêu cầu đăng ký.
4. Duy trì heartbeat hoặc đáp ứng health check theo cơ chế registry.
5. Hủy đăng ký khi ứng dụng dừng.

Logic này lặp lại ở nhiều service và dễ sai lệch. Chẳng hạn, ứng dụng có thể đăng ký trước khi biết port thực tế, quên hủy đăng ký khi shutdown hoặc dùng service ID khác với tên mà consumer tra cứu.

Khi sử dụng starter Spring Cloud phù hợp, ứng dụng khai báo các thông tin cần thiết trong cấu hình. Phần tích hợp tự động đọc thông tin ứng dụng, tạo registration phù hợp với registry và điều phối việc đăng ký theo vòng đời.

## 2. Các thành phần Spring Cloud tham gia

| Thành phần | Vai trò |
|---|---|
| Service provider | Ứng dụng Spring Boot cung cấp API và cần được phát hiện. |
| Registration | Đối tượng mang thông tin cần thiết để đăng ký một instance, tùy implementation. |
| ServiceRegistry | Abstraction cung cấp thao tác register và deregister. |
| AutoServiceRegistration | Điều phối việc đăng ký tự động theo vòng đời ứng dụng. |
| Registry implementation | Starter cụ thể thực hiện tích hợp với Eureka, Consul hoặc registry khác. |
| Service consumer | Ứng dụng tra cứu service ID và gọi instance đã phát hiện. |

ServiceRegistry mô tả thao tác đăng ký ở mức abstraction. Mỗi registry có kiểu registration và cách thực hiện riêng. Ví dụ, Eureka và Consul không nhất thiết lưu cùng cấu trúc bản ghi, dùng cùng cơ chế heartbeat hoặc có cùng cách kiểm tra sức khỏe.

AutoServiceRegistration là phần điều phối tự động. Trong nhiều tích hợp Spring Cloud, logic nền tảng được xây dựng trên một thành phần quản lý vòng đời, nhận biết thời điểm web server đã khởi động và sau đó đăng ký instance. Tên lớp và chi tiết nội bộ có thể khác theo starter và phiên bản Spring Cloud.

## 3. Vòng đời tự động đăng ký trong ứng dụng Spring Boot

Với một ứng dụng web dùng embedded server, đăng ký cần diễn ra sau khi ứng dụng đã xác định được thông tin kết nối thực tế. Điều này đặc biệt quan trọng khi cấu hình **server.port: 0**, vì hệ điều hành sẽ cấp một port khả dụng thay vì dùng một port cố định.

Luồng tổng quát:

~~~mermaid
sequenceDiagram
    participant B as Spring Boot
    participant W as Embedded Web Server
    participant A as AutoServiceRegistration
    participant S as ServiceRegistry
    participant R as Eureka / Consul

    B->>B: Đọc cấu hình và tạo ApplicationContext
    B->>W: Khởi tạo web server
    W-->>B: WebServerInitializedEvent (port thực tế)
    B->>A: Kích hoạt vòng đời auto registration
    A->>A: Tạo Registration từ service ID, host, port, metadata
    A->>S: register(Registration)
    S->>R: Gửi thông tin instance
    R-->>S: Kết quả đăng ký
    S-->>A: Hoàn tất thao tác
    Note over B,R: Instance có thể được consumer phát hiện
    B->>A: Shutdown có kiểm soát
    A->>S: deregister(Registration)
    S->>R: Xóa hoặc đánh dấu instance rời registry
~~~

Các giai đoạn chính:

1. **Khởi tạo cấu hình:** Spring Boot tạo ApplicationContext, nạp cấu hình và khởi tạo các bean. Starter discovery cung cấp các bean cần thiết cho registry tương ứng.
2. **Khởi động web server:** embedded server được tạo và bắt đầu lắng nghe. Nếu dùng port ngẫu nhiên, port thực tế chỉ có sau giai đoạn này.
3. **Nhận biết server đã sẵn sàng:** tích hợp auto registration nhận sự kiện vòng đời phù hợp, chẳng hạn sự kiện web server đã khởi tạo, để lấy port thực tế.
4. **Tạo registration:** thông tin service ID, instance ID, host, port, scheme và metadata được tập hợp theo cấu hình và implementation.
5. **Đăng ký với registry:** ServiceRegistry gửi registration đến Eureka, Consul hoặc registry đang dùng.
6. **Duy trì trạng thái:** registry client thực hiện heartbeat, renewal hoặc health check theo cơ chế riêng.
7. **Shutdown:** khi ứng dụng dừng có kiểm soát, tích hợp tự động thực hiện thao tác deregister nếu được bật và vòng đời cho phép.

Đăng ký thành công có nghĩa registry đã nhận thông tin instance. Điều đó không đảm bảo mọi consumer lập tức nhìn thấy bản ghi: registry client, cache và chu kỳ refresh có thể tạo ra độ trễ đồng bộ.

## 4. Cấu hình nền tảng trong Spring Boot

Một ứng dụng provider cần có tên logic ổn định và dependency discovery phù hợp. Ví dụ cấu hình cơ bản:

~~~yaml
spring:
  application:
    name: inventory-service

server:
  port: 8081
~~~

spring.application.name thường được dùng làm service ID mặc định trong các tích hợp Spring Cloud phổ biến. Có thể cấu hình instance ID, host, metadata hoặc port theo registry và môi trường triển khai. Không nên giả định tên dịch vụ trong mọi registry luôn được suy ra theo cùng một quy tắc nếu đã tùy chỉnh cấu hình.

Ứng dụng cũng cần dependency starter tương ứng với registry. Quản lý phiên bản thông qua Spring Cloud BOM tương thích với phiên bản Spring Boot đang dùng để tránh xung đột giữa các thư viện. Chỉ thêm starter cần thiết cho registry thực tế; dependency có mặt mới cung cấp được auto-configuration tương ứng.

### Ví dụ cấu hình với Eureka

Với provider sử dụng Spring Cloud Netflix Eureka Client, cấu hình minh họa có thể như sau:

~~~yaml
spring:
  application:
    name: inventory-service

server:
  port: 8081

eureka:
  client:
    service-url:
      defaultZone: http://localhost:8761/eureka/
    register-with-eureka: true
  instance:
    prefer-ip-address: true
    instance-id: ${spring.application.name}:${server.port}
~~~

Trong ví dụ:

- spring.application.name đặt tên logic của ứng dụng.
- service-url.defaultZone chỉ đến Eureka Server.
- register-with-eureka bật đăng ký client với Eureka.
- prefer-ip-address yêu cầu quảng bá địa chỉ IP theo cấu hình của Eureka instance.
- instance-id tạo định danh instance minh họa dựa trên tên và port.

Nếu nhiều instance cùng chạy trên một máy và dùng chung port trong các container riêng, cần bảo đảm instance ID vẫn duy nhất trong phạm vi Eureka Server. Trong môi trường container, hostname hoặc địa chỉ quảng bá phải có thể truy cập từ consumer.

### Ví dụ cấu hình với Consul

Với provider dùng Spring Cloud Consul Discovery, cấu hình minh họa:

~~~yaml
spring:
  application:
    name: inventory-service
  cloud:
    consul:
      host: localhost
      port: 8500
      discovery:
        enabled: true
        register: true
        service-name: inventory-service
        health-check-path: /actuator/health
        health-check-interval: 10s

server:
  port: 8081
~~~

Trong ví dụ này, ứng dụng khai báo Consul agent hoặc endpoint có thể truy cập. register bật đăng ký service; tên service được chỉ định rõ để consumer tra cứu thống nhất. Health check path cần tồn tại và có thể được Consul truy cập. Nếu sử dụng /actuator/health, ứng dụng cần cấu hình Spring Boot Actuator và bảo đảm endpoint được mở trong phạm vi mạng phù hợp.

Các thuộc tính chi tiết và mặc định có thể thay đổi theo phiên bản starter. Khi áp dụng, đối chiếu cấu hình với phiên bản Spring Cloud Consul đang dùng, nhất là địa chỉ agent, health check, ACL và địa chỉ service được quảng bá.

Hai ví dụ trên là hai lựa chọn registry riêng. Một ứng dụng thường tích hợp registry phù hợp với môi trường triển khai; không cần khai báo cấu hình Eureka và Consul đồng thời chỉ để có auto registration.

## 5. Kiểm soát auto registration

Trong một số môi trường, ứng dụng cần khởi động nhưng không đăng ký vào registry. Ví dụ:

- Chạy unit test hoặc integration test mà không cần registry thật.
- Chạy một tiến trình hỗ trợ hoặc batch job không nhận request từ service khác.
- Chạy ứng dụng cục bộ khi registry dùng chung không khả dụng.
- Tạo một instance tạm thời chỉ phục vụ tác vụ nội bộ.

Spring Cloud Commons cung cấp thuộc tính điều khiển auto registration ở mức chung trong nhiều phiên bản:

~~~yaml
spring:
  cloud:
    service-registry:
      auto-registration:
        enabled: false
~~~

Khi tắt auto registration, ứng dụng có thể vẫn khởi tạo các thành phần discovery khác tùy cấu hình, nhưng không thực hiện luồng đăng ký tự động chung. Registry starter cụ thể cũng có các thuộc tính riêng để bật/tắt client, đăng ký hoặc discovery. Cần phân biệt:

- Tắt **auto registration**: ngăn phần điều phối tự động đăng ký instance.
- Tắt **registry client hoặc discovery integration**: có thể ảnh hưởng cả khả năng truy vấn hoặc giao tiếp với registry.
- Tắt **register** ở cấu hình riêng của registry: điều khiển hành vi đăng ký theo implementation đó.

Không nên dùng lẫn các thuộc tính này. Hãy xác định mục tiêu là ngăn provider đăng ký, ngăn consumer truy vấn hay loại bỏ hoàn toàn kết nối registry.

## 6. Đăng ký tự động và đăng ký thủ công

Spring Cloud cũng cung cấp ServiceRegistry để thao tác registration theo cách chủ động. Đăng ký thủ công có thể phù hợp khi một ứng dụng quản lý vòng đời nhiều endpoint động hoặc cần đăng ký một tài nguyên không gắn trực tiếp với vòng đời web server.

| Tiêu chí | Auto registration | Đăng ký thủ công |
|---|---|---|
| Thời điểm đăng ký | Do tích hợp vòng đời ứng dụng điều phối | Do mã ứng dụng quyết định |
| Thông tin instance | Lấy từ cấu hình và môi trường runtime theo implementation | Mã ứng dụng phải cung cấp registration phù hợp |
| Hủy đăng ký | Được tích hợp với shutdown có kiểm soát | Mã ứng dụng phải gọi deregister đúng lúc |
| Độ phức tạp | Ít mã vòng đời hơn | Linh hoạt nhưng cần quản lý lỗi và đồng bộ |
| Trường hợp phù hợp | Một ứng dụng Spring Boot đại diện cho một service instance | Đăng ký tài nguyên động hoặc tình huống đặc thù |

Không nên vừa bật auto registration vừa tự đăng ký cùng một instance nếu chưa hiểu rõ hành vi của registry. Điều này có thể tạo bản ghi trùng, instance ID xung đột hoặc khiến một thao tác deregister xóa bản ghi mà luồng khác vẫn cần.

## 7. Hủy đăng ký khi ứng dụng dừng

Đăng ký chỉ là một nửa vòng đời. Khi ứng dụng shutdown có kiểm soát, instance cần rời registry để consumer ngừng chọn nó cho request mới.

Quy trình dừng thường cần phối hợp:

1. Nhận tín hiệu shutdown.
2. Ngừng nhận request mới hoặc chuyển readiness sang trạng thái không sẵn sàng theo cách triển khai.
3. Hoàn tất request đang xử lý trong thời gian grace period.
4. Thực hiện deregister với registry nếu tích hợp hỗ trợ và còn thời gian.
5. Đóng kết nối và kết thúc tiến trình.

Thứ tự thực tế giữa readiness, ngừng nhận traffic và deregistration phụ thuộc nền tảng triển khai. Cần bảo đảm consumer hoặc load balancer có đủ thời gian nhận biết instance đã rời hệ thống trước khi tiến trình kết thúc hoàn toàn.

### Shutdown đột ngột

Không phải mọi lần dừng đều chạy được hook shutdown. Khi máy mất điện, container bị kill cưỡng bức hoặc tiến trình crash, ứng dụng có thể không kịp gửi deregister. Registry cần cơ chế heartbeat expiration hoặc health check để phát hiện bản ghi không còn hợp lệ.

Do đó, không nên dựa hoàn toàn vào deregister khi shutdown. Heartbeat, lease, health check và timeout của registry vẫn cần được cấu hình phù hợp. Thời gian phát hiện instance chết càng ngắn thì khả năng loại bỏ nhanh càng cao, nhưng kiểm tra quá thường xuyên cũng làm tăng tải và có thể nhạy với sự cố mạng ngắn hạn.

## 8. Health check và trạng thái sẵn sàng

Đăng ký thành công không đồng nghĩa ứng dụng đã sẵn sàng phục vụ mọi request. Một service có thể mở port nhưng vẫn đang tải dữ liệu, khởi tạo kết nối cơ sở dữ liệu hoặc chưa hoàn thành bước chuẩn bị nghiệp vụ.

Cần phân biệt:

- **Process alive:** tiến trình còn chạy.
- **Liveness:** ứng dụng có cần được khởi động lại vì không còn khả năng hoạt động hay không.
- **Readiness:** ứng dụng đã sẵn sàng nhận traffic hay chưa.
- **Registry health check:** cơ chế registry dùng để xác định instance có đủ điều kiện được công bố hay không.

Nếu registry chỉ kiểm tra TCP port, nó có thể đánh dấu instance khỏe dù API chưa sẵn sàng. Nếu health check phụ thuộc một hệ thống bên ngoài bị chậm, instance có thể bị đánh dấu không khỏe dù bản thân ứng dụng vẫn xử lý được một số request. Chọn endpoint và tiêu chí kiểm tra theo mục đích thực tế.

Với Consul, health check có thể gọi HTTP endpoint của provider theo cấu hình. Với Eureka, client thường duy trì đăng ký bằng heartbeat và có thể tích hợp trạng thái sức khỏe ứng dụng tùy cấu hình. Không nên giả định hai registry dùng cùng ngữ nghĩa health check.

Spring Boot Actuator cung cấp endpoint health, nhưng cần cấu hình exposure, bảo mật và quyền truy cập phù hợp. Không mở endpoint quản trị ra mạng công cộng chỉ để registry kiểm tra sức khỏe.

## 9. Các lỗi thường gặp khi tự động đăng ký

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Ứng dụng chạy nhưng không có bản ghi | Thiếu starter, tắt auto registration hoặc sai cấu hình registry | Kiểm tra dependency, log auto-configuration và thuộc tính đăng ký |
| Bản ghi có host hoặc port sai | Địa chỉ quảng bá, port mapping hoặc cấu hình instance không đúng | So sánh địa chỉ trong registry với địa chỉ consumer truy cập được |
| Consumer không tìm thấy service | Service ID provider và consumer không thống nhất | Kiểm tra application name và service name đã tùy chỉnh |
| Có nhiều bản ghi trùng | Instance ID không duy nhất hoặc đăng ký thủ công trùng auto registration | Kiểm tra quy tắc tạo ID và số luồng đăng ký |
| Instance dừng nhưng bản ghi vẫn còn | Shutdown không graceful hoặc registry chưa hết lease/health check | Kiểm tra deregister, heartbeat, TTL và health check |
| Instance được đăng ký quá sớm | Thời điểm readiness chưa phù hợp với luồng triển khai | Kiểm tra sự kiện vòng đời và chính sách readiness |
| Registry từ chối đăng ký | Sai endpoint, thông tin xác thực, ACL hoặc lỗi mạng | Kiểm tra log client, quyền và kết nối đến registry |

Khi chẩn đoán, cần phân biệt lỗi tạo registration, lỗi gửi đăng ký, lỗi registry lưu bản ghi và độ trễ consumer nhìn thấy bản ghi. Một bản ghi chưa xuất hiện ở consumer chưa chắc có nghĩa thao tác register ở provider đã thất bại.

## 10. Thực hành kiểm tra vòng đời

Có thể xác minh auto registration theo trình tự:

1. Khởi động registry tương ứng và xác nhận endpoint của registry có thể truy cập.
2. Khởi động provider với service ID đã biết.
3. Kiểm tra log startup để xác nhận client kết nối và đăng ký thành công.
4. Kiểm tra registry catalog hoặc dashboard để tìm service ID và instance ID.
5. Gọi API health từ vị trí mà registry sử dụng để kiểm tra, nếu đã cấu hình health check.
6. Khởi động thêm một instance với định danh riêng và xác nhận registry hiển thị cả hai.
7. Dừng một instance bằng shutdown có kiểm soát và quan sát bản ghi được hủy.
8. Thử dừng cưỡng bức trong môi trường kiểm thử để quan sát cơ chế heartbeat/health check loại bản ghi cũ.
9. Từ consumer, tra cứu service ID bằng DiscoveryClient hoặc gọi qua client có tích hợp load balancing.

Ví dụ cấu hình log có thể tăng mức chi tiết cho package registry client trong lúc kiểm tra, sau đó giảm về mức phù hợp khi vận hành. Tránh bật log quá chi tiết lâu dài nếu nó làm lộ thông tin kết nối hoặc tạo lượng log lớn.

## 11. Nguyên tắc triển khai

- Dùng starter và phiên bản Spring Cloud tương thích với Spring Boot.
- Đặt spring.application.name ổn định và thống nhất với service ID mà consumer sử dụng.
- Bảo đảm host và port được đăng ký là địa chỉ có thể truy cập từ consumer hoặc gateway.
- Tạo instance ID duy nhất khi chạy nhiều instance.
- Để auto registration quản lý vòng đời thông thường; chỉ dùng đăng ký thủ công khi có nhu cầu cụ thể.
- Cấu hình health check và readiness theo trạng thái thực sự cần thiết để nhận traffic.
- Thiết kế shutdown có thời gian drain request và deregister phù hợp.
- Dùng heartbeat hoặc health check để xử lý crash và shutdown không graceful.
- Bảo vệ endpoint registry, thông tin xác thực và endpoint Actuator.
- Theo dõi số instance, lỗi đăng ký, tuổi bản ghi và độ trễ từ lúc provider đăng ký đến lúc consumer phát hiện.

Tự động đăng ký kết nối vòng đời Spring Boot với service registry. Provider khai báo danh tính và thông tin instance; tích hợp Spring Cloud chờ thời điểm phù hợp, thực hiện register và phối hợp deregister khi shutdown. Hiểu rõ thời điểm đăng ký, địa chỉ quảng bá, health check và cơ chế phục hồi giúp service instance xuất hiện đúng trong registry và rời khỏi danh sách một cách an toàn.
