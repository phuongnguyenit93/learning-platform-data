# Kết nối Spring Cloud Consul Discovery tới Consul agent

Spring Cloud Consul Discovery giúp ứng dụng Spring Boot đăng ký service instance và tìm instance của dịch vụ khác thông qua Consul. Trong mô hình triển khai phổ biến, ứng dụng giao tiếp với **Consul agent** bằng HTTP API. Agent tiếp nhận yêu cầu đăng ký, truy vấn và health check, sau đó đồng bộ thông tin với cụm Consul server.

Điểm cần nắm rõ là ứng dụng Spring Cloud thường kết nối tới API của agent, không trực tiếp tham gia giao thức nội bộ giữa các Consul server. Agent có thể chạy cùng máy với ứng dụng, trong container sidecar hoặc ở một node gần ứng dụng. Địa chỉ host, port, scheme và quyền truy cập của agent phải phù hợp với network topology thực tế.

Bài viết hướng dẫn cách cấu hình Spring Cloud Consul Discovery để kết nối agent, phân biệt agent client với server, đăng ký instance, xử lý địa chỉ trong môi trường container, bảo vệ kết nối và kiểm tra lỗi thường gặp.

## 1. Vai trò của Consul agent trong service discovery

Consul thường được triển khai với hai loại tiến trình:

- **Consul server:** duy trì trạng thái cụm, tham gia consensus, lưu catalog và điều phối dữ liệu giữa các server.
- **Consul agent:** chạy trên node hoặc môi trường ứng dụng, cung cấp HTTP/DNS interface, theo dõi service và health check cục bộ, đồng thời trao đổi thông tin với cụm server.

Agent có thể chạy ở chế độ client hoặc server. Agent ở chế độ client không lưu vai trò server trong cụm consensus; nó nhận yêu cầu từ ứng dụng và chuyển tiếp thông tin phù hợp tới server. Agent server cũng cung cấp API agent trên node của nó, ngoài vai trò thành viên server.

~~~mermaid
flowchart TB
    APP["Spring Boot application"]
    API["Spring Cloud Consul Discovery"]
    AGENT["Consul agent<br/>HTTP API :8500"]
    SERVER1[("Consul server A")]
    SERVER2[("Consul server B")]
    SERVER3[("Consul server C")]

    APP --> API
    API -->|"HTTP API: register / query"| AGENT
    AGENT <-->|"Gossip / RPC / đồng bộ catalog"| SERVER1
    SERVER1 <--> SERVER2
    SERVER2 <--> SERVER3
    SERVER3 <--> SERVER1
~~~

Ứng dụng Spring Cloud sử dụng API của agent để đăng ký service, hủy đăng ký hoặc truy vấn dữ liệu discovery. Agent chịu trách nhiệm tham gia hệ thống Consul theo cấu hình hạ tầng.

### Agent API và các cổng Consul

Các cổng mặc định thường gặp:

| Cổng | Giao thức | Vai trò |
|---|---|---|
| 8500 | HTTP hoặc HTTPS khi bật TLS | HTTP API và giao diện web của Consul agent |
| 8600 | DNS hoặc DNS-over-TLS tùy cấu hình | Truy vấn DNS của Consul |
| 8300 | TCP | RPC giữa các Consul server |
| 8301 | TCP/UDP | LAN gossip |
| 8302 | TCP/UDP | WAN gossip giữa các server/datacenter |

Spring Cloud Consul Discovery kết nối tới HTTP API của agent, thường là port 8500. Không cấu hình ứng dụng Spring Cloud trỏ vào cổng RPC 8300 hoặc các cổng gossip để thực hiện service discovery. Các cổng nội bộ của cụm được quản lý bởi Consul agent và hạ tầng mạng.

Các cổng có thể thay đổi theo cấu hình Consul. Hãy xác nhận port thực tế trên agent đang chạy, firewall và container mapping trước khi cấu hình ứng dụng.

## 2. Vì sao ứng dụng nên kết nối tới agent gần nó?

Trong môi trường production, mô hình phổ biến là chạy một Consul agent trên mỗi node hoặc cùng vùng mạng với workload. Ứng dụng kết nối tới agent cục bộ; agent giao tiếp với cụm Consul server.

Cách này có các lợi ích:

- Ứng dụng không cần biết danh sách server, topology consensus hoặc cơ chế gossip.
- Agent có thể thực hiện health check từ góc nhìn mạng gần với workload.
- Nhiều ứng dụng trên cùng node có thể sử dụng API agent chung.
- Hạ tầng có thể thay đổi số lượng server hoặc cách phân cụm mà ít ảnh hưởng cấu hình ứng dụng.
- Có thể cấp quyền và giới hạn truy cập API ở cấp agent hoặc theo chính sách ACL.

Kết nối trực tiếp tới agent từ xa vẫn có thể dùng trong môi trường phát triển hoặc kiến trúc được thiết kế rõ ràng, nhưng cần tính đến khả năng truy cập, ACL, TLS và phạm vi ảnh hưởng khi agent đó gặp sự cố.

Một agent cục bộ không đồng nghĩa với địa chỉ localhost trong mọi môi trường. Nếu ứng dụng và agent nằm trong hai container riêng, localhost của ứng dụng là chính container ứng dụng. Khi đó cần dùng DNS/service name của agent trên cùng Docker network, địa chỉ host được công bố hoặc một địa chỉ có thể định tuyến từ container ứng dụng.

## 3. Thêm dependency Spring Cloud Consul Discovery

Ứng dụng cần starter tương ứng để Spring Cloud tạo các thành phần discovery và auto-configuration cho Consul.

Ví dụ Maven dependency:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-consul-discovery</artifactId>
</dependency>
~~~

Quản lý phiên bản Spring Cloud bằng Spring Cloud BOM tương thích với phiên bản Spring Boot của dự án. Không nên tự chọn phiên bản starter riêng lẻ nếu dự án đã dùng dependency management của Spring Cloud.

Nếu muốn Consul kiểm tra endpoint Actuator của provider, bổ sung Spring Boot Actuator:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
~~~

Actuator không bắt buộc chỉ để kết nối agent hoặc tra cứu service, nhưng thường hữu ích để cung cấp health endpoint cho Consul. Cần bảo đảm endpoint được mở và có thể truy cập từ agent theo chính sách bảo mật.

## 4. Cấu hình địa chỉ Consul agent

Spring Cloud Consul dùng các thuộc tính chung để xác định endpoint agent:

| Thuộc tính | Ý nghĩa | Mặc định thường dùng |
|---|---|---|
| spring.cloud.consul.host | Hostname hoặc IP của agent | localhost |
| spring.cloud.consul.port | HTTP API port của agent | 8500 |
| spring.cloud.consul.scheme | Giao thức kết nối tới agent | http |

Ví dụ cấu hình tối thiểu trong application.yml:

~~~yaml
spring:
  application:
    name: inventory-service
  cloud:
    consul:
      host: localhost
      port: 8500
      scheme: http
      discovery:
        enabled: true
        register: true
        service-name: inventory-service
~~~

Với cấu hình này, Spring Cloud Consul Discovery kết nối tới HTTP API tại địa chỉ http://localhost:8500. Ứng dụng đăng ký dưới service name inventory-service.

Trong môi trường phát triển, agent thường chạy trên cùng máy nên localhost có thể phù hợp. Trong Docker Compose, Kubernetes hoặc môi trường nhiều node, hãy thay host bằng địa chỉ agent mà ứng dụng thực sự truy cập được.

### Tách cấu hình theo môi trường

Không nên hard-code cùng một địa chỉ agent cho mọi môi trường nếu topology khác nhau. Có thể dùng Spring profile:

~~~yaml
# application-dev.yml
spring:
  cloud:
    consul:
      host: localhost
      port: 8500
      scheme: http
~~~

~~~yaml
# application-prod.yml
spring:
  cloud:
    consul:
      host: consul-agent.service.internal
      port: 8500
      scheme: https
~~~

Ví dụ production sử dụng HTTPS tới một địa chỉ agent nội bộ. Tên DNS và cổng cần được thay bằng endpoint thực tế của môi trường. Secret, ACL token và trust material nên được cấp từ secret manager hoặc cơ chế cấu hình an toàn, không commit vào repository.

## 5. Kết nối agent trong Docker và Kubernetes

### Docker Compose

Giả sử ứng dụng và agent chạy ở hai container cùng Docker network. Có thể dùng tên service của agent làm hostname:

~~~yaml
services:
  consul-agent:
    image: hashicorp/consul:latest
    command: agent -dev -client=0.0.0.0
    ports:
      - "8500:8500"

  inventory-service:
    build: .
    environment:
      SPRING_APPLICATION_NAME: inventory-service
      SPRING_CLOUD_CONSUL_HOST: consul-agent
      SPRING_CLOUD_CONSUL_PORT: 8500
      SPRING_CLOUD_CONSUL_SCHEME: http
    depends_on:
      - consul-agent
~~~

Đây là ví dụ minh họa cho môi trường local. Agent ở chế độ dev không phù hợp để vận hành production. Trong cùng Docker network, ứng dụng truy cập consul-agent:8500; port mapping 8500 ra host phục vụ truy cập từ máy phát triển, không phải địa chỉ mà container ứng dụng bắt buộc phải dùng.

depends_on chỉ điều khiển thứ tự khởi tạo container theo cơ chế Compose; nó không đảm bảo Consul agent đã sẵn sàng nhận API request. Ứng dụng cần retry kết nối phù hợp hoặc orchestration cần có health/readiness check cho agent.

### Kubernetes

Trong Kubernetes, agent có thể chạy dưới dạng DaemonSet trên mỗi node, sidecar hoặc một dịch vụ nội bộ. Cách đặt địa chỉ phụ thuộc mô hình triển khai:

- Nếu agent là sidecar trong cùng Pod, ứng dụng có thể dùng localhost và port được chia sẻ trong network namespace của Pod.
- Nếu agent là DaemonSet, ứng dụng cần địa chỉ node/agent có thể truy cập và cơ chế chọn đúng node tương ứng.
- Nếu agent được công bố qua Kubernetes Service, ứng dụng dùng DNS của Service; cần cân nhắc việc request có thể đến agent trên node khác hay không.

Không nên mặc định localhost luôn trỏ tới agent trong Kubernetes. Chỉ dùng localhost khi agent và ứng dụng chia sẻ network namespace, chẳng hạn sidecar trong cùng Pod.

~~~yaml
spring:
  cloud:
    consul:
      host: consul-agent.default.svc.cluster.local
      port: 8500
      scheme: http
~~~

Hostname trong ví dụ là DNS minh họa. Hãy thay namespace và tên Service theo cluster. Nếu agent chỉ lắng nghe trên loopback, Service hoặc Pod khác sẽ không thể truy cập cho đến khi bind address và network policy được cấu hình phù hợp.

## 6. Địa chỉ agent khác với địa chỉ service instance được đăng ký

Hai loại địa chỉ này thường bị nhầm lẫn:

| Địa chỉ | Được dùng để làm gì? | Ví dụ |
|---|---|---|
| Consul agent endpoint | Spring Cloud gửi API request để đăng ký hoặc truy vấn | localhost:8500 |
| Service instance address | Consumer kết nối tới API của provider | 10.0.2.15:8081 |

Thuộc tính spring.cloud.consul.host và spring.cloud.consul.port xác định nơi Spring Cloud nói chuyện với agent. Chúng không nhất thiết là host và port mà consumer sẽ dùng để gọi inventory-service.

Thông tin địa chỉ service instance được cấu hình qua discovery properties hoặc được suy ra từ môi trường runtime. Ví dụ:

~~~yaml
spring:
  application:
    name: inventory-service
  cloud:
    consul:
      host: localhost
      port: 8500
      discovery:
        service-name: inventory-service
        prefer-ip-address: true
        health-check-path: /actuator/health
        health-check-interval: 15s
~~~

Trong ví dụ, localhost:8500 là địa chỉ agent; địa chỉ instance được đăng ký được Spring Cloud Consul Discovery xác định theo cấu hình instance và môi trường. Nếu cần quảng bá hostname hoặc IP cụ thể, cấu hình các thuộc tính hostname/ip-address/port tương ứng với phiên bản Spring Cloud Consul đang dùng và xác minh kết quả trong Consul catalog.

Địa chỉ quảng bá phải truy cập được từ nơi thực hiện health check và từ consumer. Ví dụ, nếu provider chạy trong container nhưng đăng ký địa chỉ 127.0.0.1, một agent ở container khác sẽ kiểm tra loopback của chính nó thay vì provider. Đây là nguyên nhân thường gặp khiến service được đăng ký nhưng health check thất bại.

## 7. Đăng ký service và kiểm tra health qua agent

Khi auto registration được bật, Spring Cloud Consul Discovery gửi yêu cầu đăng ký đến agent. Agent lưu registration cục bộ và đồng bộ catalog tới server theo cơ chế Consul.

~~~mermaid
sequenceDiagram
    participant A as Spring Boot inventory-service
    participant C as Spring Cloud Consul
    participant G as Consul agent
    participant S as Consul server
    participant O as order-service

    A->>C: Khởi động ứng dụng
    C->>G: Register inventory-service
    G->>S: Đồng bộ catalog
    S-->>G: Registration được ghi nhận
    G-->>C: Kết quả đăng ký
    loop Health check
        G->>A: GET /actuator/health
        A-->>G: UP hoặc trạng thái lỗi
        G->>S: Cập nhật health/catalog
    end
    O->>G: Query inventory-service
    G-->>O: Danh sách instance
~~~

Ví dụ cấu hình discovery:

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
        instance-id: inventory-service-node-01
        health-check-path: /actuator/health
        health-check-interval: 15s
        prefer-ip-address: true

management:
  endpoints:
    web:
      exposure:
        include: health,info
~~~

Các thuộc tính health check cần được điều chỉnh theo phiên bản starter và môi trường. Consul agent thực hiện health check tới địa chỉ service đã đăng ký; do đó path, port, scheme và địa chỉ quảng bá phải nhất quán. Instance ID phải duy nhất trong phạm vi Consul catalog để tránh bản ghi trùng hoặc ghi đè ngoài ý muốn.

Việc đăng ký qua agent không có nghĩa consumer bắt buộc truy vấn cùng agent đó. Consumer có thể kết nối tới agent cục bộ của nó để truy vấn catalog; agent chuyển tiếp hoặc phục vụ dữ liệu theo cơ chế Consul.

## 8. Bảo vệ kết nối tới Consul agent

API agent có thể cho phép đăng ký, hủy đăng ký, đọc catalog hoặc truy cập dữ liệu nhạy cảm tùy ACL. Không nên mở HTTP API không xác thực ra mạng không tin cậy.

Các lớp bảo vệ thường cần xem xét:

- **Network binding:** chỉ bind HTTP API trên interface mà ứng dụng hợp lệ có thể truy cập.
- **Firewall/network policy:** giới hạn nguồn có thể kết nối tới agent API.
- **ACL:** cấp token với quyền tối thiểu cần cho thao tác discovery hoặc registration.
- **TLS:** dùng HTTPS khi lưu lượng đi qua mạng không tin cậy hoặc chính sách yêu cầu mã hóa.
- **Secret management:** cấp ACL token và thông tin truststore từ nơi quản lý bí mật; không ghi vào Git hoặc log.

Spring Cloud Consul có các thuộc tính cấu hình ACL token theo từng chức năng như discovery hoặc config. Tên và phạm vi thuộc tính phụ thuộc phiên bản starter. Hãy dùng property reference của đúng phiên bản đang triển khai; tránh dùng một token quản trị toàn quyền cho mọi service.

Khi agent API dùng HTTPS, đặt scheme phù hợp và cấu hình JVM tin cậy CA/chứng thư của agent. Nếu hệ thống yêu cầu mutual TLS, cần cung cấp client certificate theo chính sách của hạ tầng. HTTPS chỉ mã hóa kết nối; ACL vẫn cần thiết để kiểm soát thao tác được phép.

Không nên dùng Consul dev agent với ACL/TLS mặc định cho production. Môi trường thật cần cấu hình agent, server, ACL bootstrap, gossip encryption, TLS và network segmentation theo hướng dẫn vận hành Consul.

## 9. Kiểm tra agent trước khi chạy ứng dụng

Trước khi khởi động Spring Boot, xác nhận HTTP API của agent có thể truy cập từ đúng network namespace của ứng dụng.

Kiểm tra agent self:

~~~bash
curl http://127.0.0.1:8500/v1/agent/self
~~~

Liệt kê service mà agent đang quản lý:

~~~bash
curl http://127.0.0.1:8500/v1/agent/services
~~~

Kiểm tra health của service theo catalog:

~~~bash
curl "http://127.0.0.1:8500/v1/health/service/inventory-service?passing=true"
~~~

Các lệnh trên minh họa API mặc định không TLS và không kèm ACL token. Trong môi trường bảo mật, dùng HTTPS, xác thực và header/token phù hợp. Không đưa token thật vào command history hoặc tài liệu.

Sau khi ứng dụng khởi động:

1. Kiểm tra log để xác nhận Spring Cloud kết nối được tới agent.
2. Kiểm tra endpoint agent services để xem registration đã xuất hiện.
3. Kiểm tra catalog/health để xác nhận instance đang passing.
4. Xác minh địa chỉ và port của instance có thể truy cập từ consumer.
5. Dừng ứng dụng có kiểm soát và kiểm tra registration được hủy nếu deregistration được bật.

## 10. Lỗi thường gặp khi kết nối agent

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Connection refused tới port 8500 | Agent chưa chạy, sai port hoặc API chưa bind interface phù hợp | Kiểm tra agent status, listener và port mapping |
| Timeout khi gọi agent | Firewall, route hoặc network policy chặn kết nối | Kiểm tra từ container/pod của ứng dụng |
| 403 hoặc permission denied | ACL token thiếu quyền hoặc không được gửi | Kiểm tra token, policy và thuộc tính ACL theo starter |
| TLS handshake thất bại | Sai scheme, CA chưa tin cậy hoặc certificate không hợp lệ | Kiểm tra HTTPS, truststore, hostname và thời hạn cert |
| Agent truy cập được nhưng service không xuất hiện | Discovery bị tắt, register=false hoặc đăng ký lỗi | Kiểm tra dependency, cấu hình và log startup |
| Service xuất hiện nhưng health critical | Agent không truy cập được địa chỉ provider hoặc path sai | Kiểm tra advertised host/port, network và health-check path |
| Instance có địa chỉ localhost | Địa chỉ quảng bá được suy ra sai trong container | Cấu hình IP/hostname có thể truy cập từ consumer và agent |
| Consumer không thấy service | Consumer truy vấn agent khác, sai service name hoặc catalog chưa đồng bộ | Kiểm tra agent endpoint, service ID và trạng thái catalog |

### Phân biệt lỗi agent và lỗi server

Nếu ứng dụng không kết nối được port 8500, trước hết kiểm tra agent API tại node hoặc container liên quan. Nếu agent API hoạt động nhưng catalog không đồng bộ hoặc agent báo lỗi giao tiếp với server, kiểm tra membership, RPC, gossip, datacenter và log của Consul server/agent.

Không nên khắc phục lỗi HTTP API bằng cách đổi ứng dụng sang cổng RPC hoặc gossip. Đó là các giao thức nội bộ khác nhau và không thay thế API mà Spring Cloud Consul sử dụng.

## 11. Nguyên tắc triển khai

- Dùng Spring Cloud Consul Discovery starter và phiên bản BOM tương thích với Spring Boot.
- Cấu hình spring.cloud.consul.host, port và scheme trỏ tới HTTP API của agent.
- Trong production, ưu tiên agent cục bộ hoặc sidecar phù hợp với topology thay vì để mọi ứng dụng phụ thuộc trực tiếp vào một agent từ xa duy nhất.
- Chỉ dùng localhost khi agent thật sự nằm trong cùng network namespace với ứng dụng.
- Phân biệt agent endpoint với địa chỉ host/port mà provider quảng bá cho consumer.
- Bảo đảm agent có thể truy cập địa chỉ và health-check path của provider.
- Đặt instance ID duy nhất và thống nhất service name giữa provider với consumer.
- Dùng ACL token quyền tối thiểu, TLS và network policy phù hợp.
- Theo dõi trạng thái agent, lỗi đăng ký, health check và độ trễ đồng bộ catalog.
- Kiểm tra service trong catalog từ đúng agent mà consumer sử dụng.

Spring Cloud Consul Discovery kết nối Consul agent qua HTTP API để đăng ký và tra cứu service. Agent là điểm giao tiếp gần ứng dụng, còn Consul server quản lý catalog và trạng thái cụm. Cấu hình đúng endpoint agent, network namespace, địa chỉ instance được quảng bá, ACL và TLS giúp quá trình discovery hoạt động ổn định từ môi trường phát triển đến production.
