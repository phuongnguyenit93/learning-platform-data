# Địa chỉ lắng nghe, địa chỉ công bố và khả năng định tuyến

Trong service discovery, đăng ký một instance với đúng tên dịch vụ chưa đủ để consumer gọi được instance đó. Registry còn phải lưu địa chỉ và cổng mà consumer có thể truy cập. Một ứng dụng có thể đang lắng nghe trên 0.0.0.0:8080, nhưng lại công bố localhost:8080 hoặc một IP riêng chỉ tồn tại bên trong container. Khi đó đăng ký vẫn thành công, nhưng request từ service khác sẽ thất bại.

Khi triển khai Spring Cloud với Eureka hoặc Consul, cần phân biệt ba khái niệm: địa chỉ lắng nghe của tiến trình, địa chỉ công bố trong registry và đường mạng thực tế từ consumer tới instance. Ba giá trị này có thể giống nhau trong máy phát triển, nhưng thường khác nhau khi dùng Docker, Kubernetes, NAT, reverse proxy hoặc nhiều mạng nội bộ.

## 1. Ba loại địa chỉ cần phân biệt

**Địa chỉ lắng nghe (bind/listen address)** là interface và port mà web server trong ứng dụng mở để nhận kết nối. Spring Boot thường dùng server.address và server.port để cấu hình phần này.

**Địa chỉ công bố (advertised address)** là hostname hoặc IP, port và scheme mà ứng dụng đăng ký vào Eureka hoặc Consul. Consumer lấy thông tin này từ registry để tạo request tới instance. Đây là thông tin định tuyến được công bố cho các service khác.

**Địa chỉ có thể định tuyến (routable address)** là địa chỉ mà một consumer cụ thể có thể phân giải DNS, mở kết nối TCP và gửi request tới được. Một địa chỉ có thể đúng từ góc nhìn host nhưng không đúng từ góc nhìn container khác hoặc một subnet khác.

Ví dụ:

    Ứng dụng inventory-service
      Listen:      0.0.0.0:8080
      Advertise:   inventory-service:8080
      Consumer:    order-service trong cùng Docker network
      Route:       inventory-service -> IP container hiện tại -> port 8080

Nếu registry công bố localhost:8080, order-service sẽ gọi localhost của chính container order-service. Nếu registry công bố IP container cũ, địa chỉ đó có thể không còn đúng sau khi container được tạo lại.

| Khái niệm | Câu hỏi cần trả lời | Ví dụ |
|---|---|---|
| Listen/bind | Tiến trình nhận kết nối trên interface và port nào? | 0.0.0.0:8080 |
| Advertise | Registry sẽ đưa host, port và scheme nào cho consumer? | inventory-service:8080 |
| Route | Consumer có DNS, route, firewall và quyền truy cập tới địa chỉ đó không? | order-service gọi được inventory-service:8080 |

Một instance chỉ có thể phục vụ request khi cả ba lớp khớp với topology mạng thực tế.

## 2. Cấu hình địa chỉ lắng nghe trong Spring Boot

Spring Boot embedded web server mặc định lắng nghe HTTP trên port 8080. Có thể đổi port bằng server.port và chỉ định interface bind bằng server.address.

Ví dụ:

    server:
      address: 0.0.0.0
      port: 8080

0.0.0.0 có nghĩa là lắng nghe trên mọi IPv4 interface khả dụng trong network namespace của tiến trình. Đây thường là lựa chọn phù hợp khi ứng dụng chạy trong container và cần nhận kết nối từ container khác.

Nếu đặt:

    server:
      address: 127.0.0.1
      port: 8080

ứng dụng chỉ nhận kết nối loopback bên trong network namespace của chính nó. Một container khác không thể gọi trực tiếp tới 127.0.0.1:8080 của container này.

Cần phân biệt bind address với địa chỉ công bố. Đặt server.address=0.0.0.0 không có nghĩa registry nên công bố 0.0.0.0. Đây là địa chỉ wildcard để bind, không phải địa chỉ đích mà consumer dùng để kết nối.

Port lắng nghe có thể khác port công bố. Ví dụ ứng dụng nghe ở 8080 nhưng reverse proxy nhận kết nối ngoài ở 443. Khi đó registry có thể cần công bố hostname của proxy và port 443, trong khi server.address và server.port vẫn là 0.0.0.0:8080.

## 3. Vì sao đăng ký thành công nhưng consumer không gọi được?

Registry chỉ lưu thông tin instance mà client cung cấp. Nó không tự tạo route mạng giữa các container, máy ảo hoặc subnet.

Một số lỗi thường gặp:

- **Công bố localhost:** consumer gọi loopback của chính nó thay vì instance đích.
- **Công bố IP container:** IP có thể thay đổi khi container được tạo lại hoặc scale.
- **Công bố IP private sai mạng:** IP hợp lệ nhưng consumer ở subnet khác không có route tới địa chỉ đó.
- **Sai port:** ứng dụng lắng nghe container port 8080 nhưng registry công bố host port hoặc port của proxy không đúng.
- **Sai hostname:** DNS chỉ phân giải được trong một network hoặc một datacenter, nhưng consumer nằm ngoài phạm vi đó.
- **Sai scheme:** registry công bố http trong khi proxy chỉ chấp nhận https, hoặc ngược lại.
- **Firewall/network policy:** DNS và TCP có thể hoạt động ở một chiều nhưng bị chặn ở chiều consumer tới service.
- **Sai địa chỉ health check:** Consul Agent không truy cập được endpoint kiểm tra dù consumer có thể gọi endpoint nghiệp vụ.

Vì vậy, thấy service xuất hiện trên Eureka Dashboard hoặc Consul Catalog mới chỉ chứng minh thông tin đăng ký đã được ghi nhận. Cần thử kết nối từ chính môi trường của consumer để xác nhận đường định tuyến.

## 4. Cấu hình địa chỉ công bố với Consul

Spring Cloud Consul tự xác định hostname và IP của instance theo môi trường. Có thể ghi đè thông tin này bằng các thuộc tính:

- spring.cloud.consul.discovery.hostname: hostname công bố.
- spring.cloud.consul.discovery.ip-address: IP công bố.
- spring.cloud.consul.discovery.prefer-ip-address: ưu tiên dùng IP thay cho hostname.
- spring.cloud.consul.discovery.port: port công bố; mặc định lấy từ port lắng nghe.
- spring.cloud.consul.discovery.scheme: scheme http hoặc https.

Ví dụ khi các service chạy cùng một Docker Compose network:

    server:
      address: 0.0.0.0
      port: 8080

    spring:
      application:
        name: inventory-service
      cloud:
        consul:
          host: consul
          port: 8500
          discovery:
            register: true
            hostname: inventory-service
            prefer-ip-address: false
            port: 8080
            scheme: http

Trong ví dụ:

- server.address và server.port điều khiển web server của inventory-service.
- spring.cloud.consul.host và port là địa chỉ Consul Agent mà ứng dụng gọi để đăng ký.
- discovery.hostname và discovery.port là địa chỉ service được công bố cho consumer.
- hostname inventory-service chỉ phân giải được từ các container nằm trong network có DNS record tương ứng.

Không nhầm spring.cloud.consul.host với spring.cloud.consul.discovery.hostname. Thuộc tính đầu tiên chỉ nơi ứng dụng gọi Consul Agent API; thuộc tính thứ hai là địa chỉ instance mà Consul đăng ký để consumer sử dụng.

Nếu muốn công bố IP thay cho hostname:

    spring:
      cloud:
        consul:
          discovery:
            ip-address: 10.20.0.15
            prefer-ip-address: true

IP phải là địa chỉ mà tất cả consumer cần gọi có thể định tuyến tới. Không chọn IP loopback, IP của interface quản trị không truy cập được hoặc IP nội bộ của một container chỉ có ý nghĩa trên một node.

## 5. Cấu hình địa chỉ công bố với Eureka

Eureka Client gửi thông tin instance như hostname, IP, port và instance ID lên Eureka Server. Các thuộc tính thường dùng gồm:

- eureka.instance.hostname: hostname công bố.
- eureka.instance.ip-address: IP của instance.
- eureka.instance.prefer-ip-address: ưu tiên công bố IP thay vì hostname.
- eureka.instance.instance-id: định danh duy nhất của instance trong service.
- eureka.instance.non-secure-port và secure-port: port công bố cho HTTP và HTTPS.
- eureka.instance.non-secure-port-enabled và secure-port-enabled: bật/tắt loại endpoint tương ứng.

Ví dụ dùng hostname nội bộ có thể phân giải từ consumer:

    server:
      address: 0.0.0.0
      port: 8080

    spring:
      application:
        name: inventory-service

    eureka:
      instance:
        hostname: inventory-service.internal
        prefer-ip-address: false
        non-secure-port: 8080
        non-secure-port-enabled: true
        instance-id: ${spring.application.name}:${HOSTNAME:node-01}:${server.port}

Nếu consumer không phân giải được hostname nhưng có route tới IP của instance, có thể dùng:

    eureka:
      instance:
        ip-address: 10.20.0.15
        prefer-ip-address: true

Đặt prefer-ip-address=true yêu cầu Eureka công bố IP thay vì hostname. Hãy xác minh IP mà ứng dụng chọn thực sự thuộc interface dùng cho giao tiếp giữa các service. Máy có nhiều card mạng, VPN hoặc interface container có thể khiến địa chỉ tự phát hiện không phải địa chỉ consumer truy cập được.

Nếu chạy nhiều instance cùng service trên một máy, hãy bảo đảm instance ID không bị trùng. Một định danh thường kết hợp service name với hostname hoặc ID container và port. Nếu hai instance đăng ký cùng một ID, thông tin có thể ghi đè hoặc gây nhầm lẫn trong registry.

## 6. Phân biệt địa chỉ công bố và port khi dùng reverse proxy

Một mô hình phổ biến là ứng dụng chạy trong mạng riêng, còn consumer truy cập qua reverse proxy hoặc load balancer:

    Consumer
       |
       | https://inventory.api.internal:443
       v
    Reverse proxy / Load balancer
       |
       | http://inventory-service:8080
       v
    Spring Boot inventory-service

Trong mô hình này:

- Spring Boot lắng nghe 0.0.0.0:8080.
- Reverse proxy nhận HTTPS ở inventory.api.internal:443.
- Proxy chuyển request vào ứng dụng qua HTTP port 8080.
- Nếu consumer sẽ gọi qua proxy, registry phải công bố inventory.api.internal và port 443 với scheme HTTPS.
- Nếu consumer cùng mạng riêng và gọi trực tiếp container, registry có thể công bố inventory-service:8080.

Không thể dùng một địa chỉ công bố cho mọi nhóm consumer nếu các nhóm có đường mạng khác nhau. Có thể cần DNS nội bộ, registry riêng theo môi trường, service gateway hoặc một địa chỉ VIP có thể truy cập từ tất cả consumer liên quan.

Với Eureka, cấu hình endpoint HTTPS có thể dùng:

    eureka:
      instance:
        hostname: inventory.api.internal
        non-secure-port-enabled: false
        secure-port-enabled: true
        secure-port: 443
        secure-health-check-url: https://inventory.api.internal/actuator/health
        status-page-url: https://inventory.api.internal/actuator/info
        home-page-url: https://inventory.api.internal/

Với Consul, cấu hình service công bố qua proxy có thể dùng:

    spring:
      cloud:
        consul:
          discovery:
            hostname: inventory.api.internal
            prefer-ip-address: false
            port: 443
            scheme: https
            health-check-url: http://inventory-service:8080/actuator/health

Ví dụ Consul trên công bố HTTPS port 443 cho consumer nhưng health check đi trực tiếp tới HTTP endpoint nội bộ port 8080. Consul Agent phải nằm trong network có thể truy cập inventory-service:8080. Chỉ dùng health-check-url riêng khi địa chỉ kiểm tra thực sự khác địa chỉ công bố; hãy bảo đảm endpoint nội bộ cũng được bảo vệ bằng network policy phù hợp.

Nếu TLS được kết thúc tại proxy, ứng dụng có thể cần cấu hình xử lý forwarded headers để tạo URL tuyệt đối đúng scheme và host bên ngoài. Việc này không tự thay đổi địa chỉ đăng ký; cấu hình hostname, port và scheme trong registry vẫn cần được đặt phù hợp.

## 7. Docker Compose: host port và container port

Docker Compose tạo một network mặc định cho các service trong cùng project. Container có thể tìm nhau bằng service name qua DNS nội bộ. IP container có thể thay đổi sau khi tạo lại, còn service name giữ ổn định.

Ví dụ:

    services:
      inventory-service:
        image: example/inventory-service
        environment:
          SERVER_ADDRESS: 0.0.0.0
          SERVER_PORT: 8080
        ports:
          - "18080:8080"
        networks:
          - backend

      order-service:
        image: example/order-service
        environment:
          SPRING_CLOUD_CONSUL_HOST: consul
          SPRING_CLOUD_CONSUL_PORT: 8500
        networks:
          - backend

      consul:
        image: hashicorp/consul:latest
        command: agent -dev -client=0.0.0.0
        ports:
          - "8500:8500"
        networks:
          - backend

    networks:
      backend:

Trong ví dụ, Consul chạy với chế độ dev để phục vụ thí nghiệm local; không dùng chế độ này cho production. Trong môi trường thật, triển khai Consul Agent theo cấu hình cluster và bảo mật phù hợp.

Có hai cách truy cập inventory-service:

| Nơi gọi | Địa chỉ | Port |
|---|---|---:|
| Container order-service trong backend network | inventory-service | 8080 |
| Máy host | localhost | 18080 |

Nếu Consul Agent chạy trong container consul cùng network, nó cũng có thể truy cập inventory-service:8080 để thực hiện HTTP health check. Vì vậy, trong mô hình này Consul nên lưu địa chỉ công bố inventory-service:8080, không phải localhost:18080.

Host port 18080 chỉ cần thiết khi một tiến trình bên ngoài Docker network truy cập từ máy host. Container-to-container communication sử dụng container port 8080. Không đăng ký host port 18080 nếu consumer trong network cần gọi port nội bộ 8080.

Nếu Consul Agent chạy trực tiếp trên host thay vì trong container, địa chỉ health check và địa chỉ đăng ký cần được đánh giá lại theo đường mạng từ host tới container. Có thể dùng host address và port đã publish, hoặc đặt agent cùng network với service để dùng DNS service name và container port.

## 8. Kubernetes và địa chỉ Pod/Service

Trong Kubernetes, Pod IP thường chỉ có ý nghĩa trong cluster network và có thể thay đổi khi Pod được tạo lại. Kubernetes Service cung cấp địa chỉ DNS ổn định cho một nhóm Pod.

Ví dụ:

    Spring Boot container:
      listen: 0.0.0.0:8080

    Kubernetes Service:
      service port: 80
      targetPort: 8080

    Consumer trong cùng cluster:
      http://inventory-service:80

Nếu ứng dụng đăng ký Pod IP trực tiếp vào Eureka hoặc Consul, mọi consumer phải có route tới Pod CIDR và network policy phải cho phép kết nối. Nếu muốn consumer gọi qua Kubernetes Service, địa chỉ công bố nên là DNS Service và port service. Cần bảo đảm health check của registry cũng có thể truy cập địa chỉ đã cấu hình.

Không mặc định rằng Pod IP, Node IP, Service ClusterIP và LoadBalancer IP có thể thay thế cho nhau. Chúng thuộc các phạm vi mạng khác nhau:

| Địa chỉ | Phạm vi sử dụng điển hình |
|---|---|
| Pod IP | Giao tiếp trực tiếp tới Pod trong cluster network |
| ClusterIP / Service DNS | Giao tiếp tới Kubernetes Service từ bên trong cluster |
| Node IP + NodePort | Truy cập qua node và port được công bố |
| LoadBalancer IP/hostname | Truy cập qua load balancer bên ngoài cluster |

Chọn loại địa chỉ dựa trên vị trí của consumer, không dựa trên địa chỉ nào dễ lấy nhất từ ứng dụng.

## 9. Management port và health check

Ứng dụng có thể chạy management endpoint trên port riêng:

    server:
      address: 0.0.0.0
      port: 8080

    management:
      server:
        port: 8081

Khi management server dùng port khác application server, Spring Cloud Consul đăng ký management service riêng. Consul discovery có các thuộc tính management-port, management-suffix và management-tags để điều chỉnh registration đó.

Cần phân biệt:

- Port nghiệp vụ là địa chỉ consumer dùng để gọi API.
- Management port thường chỉ dành cho health, metrics và vận hành.
- Health check port là nơi Consul Agent gọi endpoint kiểm tra.

Không công bố management port như port nghiệp vụ nếu consumer không nên truy cập nó. Cũng không mở management port ra mạng công khai chỉ để Consul Agent có thể kiểm tra. Hãy dùng network nội bộ, ACL hoặc health-check-url riêng để giới hạn đường truy cập.

Với Eureka, health-check-url, secure-health-check-url, status-page-url và home-page-url có thể được cấu hình riêng khi các endpoint nằm sau proxy hoặc khác địa chỉ của instance. Các URL này cần phản ánh đường truy cập thực tế của thành phần sẽ sử dụng chúng.

## 10. DNS, NAT, firewall và route

Hostname công bố chỉ hữu ích khi consumer có thể phân giải nó thành địa chỉ IP phù hợp. Trong môi trường nhiều mạng, cùng một hostname có thể được phân giải khác nhau tùy DNS view hoặc search domain.

Khi kiểm tra, hãy xác minh từ đúng môi trường consumer:

1. DNS có trả về IP dự kiến không?
2. IP đó có thuộc network mà consumer có route tới không?
3. Firewall, security group và network policy có cho phép TCP tới port công bố không?
4. Service có thật sự listen trên interface đó và port đó không?
5. Nếu có NAT hoặc port mapping, port consumer dùng có được chuyển tới đúng container/server port không?
6. Nếu dùng HTTPS, hostname có khớp certificate và trust chain có hợp lệ không?
7. Nếu đi qua proxy, proxy có route tới upstream và chuyển tiếp đúng path, method, header không?

NAT có thể làm địa chỉ bên trong khác địa chỉ bên ngoài. Nếu consumer nằm ngoài NAT, đăng ký địa chỉ private bên trong thường không đủ. Cần công bố hostname/IP và port bên ngoài mà consumer có thể truy cập, hoặc dùng một mạng overlay/VPN để các bên có route trực tiếp.

Không dùng ping làm bằng chứng duy nhất. ICMP có thể bị chặn trong khi TCP hoạt động, hoặc ping thành công nhưng port ứng dụng vẫn đóng. Hãy thử TCP và HTTP/HTTPS tới đúng port.

## 11. Kiểm chứng địa chỉ từ phía consumer

Một quy trình chẩn đoán thực tế nên bắt đầu từ registry và kết thúc ở request thật.

**Bước 1: Xem địa chỉ registry đang công bố**

Với Consul, truy vấn service catalog:

    curl http://consul:8500/v1/catalog/service/inventory-service

Kiểm tra ServiceAddress, ServicePort, ServiceName, Node và datacenter. Nếu ServiceAddress rỗng, Consul có thể dùng địa chỉ node theo quy tắc của catalog; hãy xác minh địa chỉ kết quả consumer nhận được.

Với Eureka, mở Dashboard hoặc truy vấn registry để xem hostname, IP, port, status và instance ID mà client đã đăng ký.

**Bước 2: Kiểm tra DNS từ consumer**

    nslookup inventory-service

Lệnh phải chạy trong container hoặc máy của consumer. Chạy trên host có thể cho kết quả khác với container.

**Bước 3: Kiểm tra HTTP từ consumer**

    curl -v http://inventory-service:8080/actuator/health

Nếu service công bố qua HTTPS proxy:

    curl -v https://inventory.api.internal/actuator/health

Nếu DNS phân giải đúng nhưng kết nối timeout, kiểm tra route, firewall và security group. Nếu TCP kết nối được nhưng trả 404, kiểm tra context path hoặc reverse proxy routing. Nếu trả 401/403, kiểm tra xác thực và quyền truy cập. Nếu TLS lỗi, kiểm tra hostname certificate, CA và SNI.

**Bước 4: So sánh với địa chỉ listen**

Trên máy hoặc container chạy service, xác nhận tiến trình thực sự listen trên port và interface đã cấu hình. Trên Linux có thể dùng ss -lntp; trong container có thể dùng công cụ tương đương có sẵn trong image hoặc kiểm tra log khởi động Spring Boot.

**Bước 5: Gọi qua service discovery**

Sau khi địa chỉ trực tiếp hoạt động, kiểm tra DiscoveryClient hoặc Spring Cloud LoadBalancer để xác nhận consumer nhận đúng URI và request được chuyển tới instance mong muốn.

## 12. Bảng lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Service có trong registry nhưng request timeout | Advertised IP/hostname không có route từ consumer | Công bố địa chỉ consumer truy cập được; kiểm tra firewall và subnet |
| Consumer gọi localhost và nhận nhầm chính nó | Registry chứa localhost | Đặt hostname/IP của instance thay vì loopback |
| Container khác không gọi được ứng dụng | server.address bind 127.0.0.1 | Bind vào 0.0.0.0 hoặc interface phù hợp |
| Docker host gọi được nhưng container không gọi được | Dùng host port hoặc localhost sai phạm vi | Dùng service DNS name và container port |
| Consul health check critical nhưng API gọi được từ host | Consul Agent ở network khác hoặc health check dùng sai port/path | Kiểm tra từ network của agent và cấu hình health-check-url/path |
| Request đi sai port sau reverse proxy | Registry công bố port nội bộ thay vì port proxy, hoặc ngược lại | Chọn một đường gọi nhất quán và cấu hình port công bố |
| HTTPS trả lỗi certificate | Hostname công bố không khớp SAN hoặc CA không được tin cậy | Dùng DNS khớp certificate và cấu hình trust |
| Eureka hiển thị hostname không phân giải được | Java tự chọn hostname không phù hợp network | Đặt eureka.instance.hostname hoặc prefer-ip-address |
| Consul công bố sai interface | Auto-detect chọn nhầm NIC/VPN/container interface | Đặt hostname hoặc ip-address và prefer-ip-address rõ ràng |
| Health endpoint hoạt động nhưng consumer vẫn không gọi được | Health check chỉ chứng minh agent tới được endpoint kiểm tra | Kiểm tra riêng route từ consumer tới application endpoint |

## 13. Nguyên tắc chọn địa chỉ công bố

Khi quyết định địa chỉ đăng ký cho một service, hãy trả lời theo thứ tự:

1. Những consumer nào cần gọi instance này?
2. Các consumer đó nằm trong cùng Docker network, cùng Kubernetes cluster, cùng VPC hay qua mạng ngoài?
3. Có hostname ổn định được phân giải từ tất cả consumer không?
4. Consumer nên gọi trực tiếp instance hay đi qua proxy/load balancer?
5. Port và scheme nào thực sự mở trên đường đi đó?
6. Health checker chạy ở đâu và có cần một URL riêng không?
7. Địa chỉ có còn đúng sau restart, reschedule hoặc scale không?

Nếu tất cả consumer ở cùng một overlay network, service DNS name thường ổn định và dễ quản lý hơn IP container. Nếu consumer nằm ở nhiều network, dùng DNS/VIP hoặc gateway có thể truy cập xuyên các network đó. Nếu một service có cả consumer nội bộ và bên ngoài, có thể cần hai endpoint hoặc hai registration khác nhau thay vì một advertised address duy nhất.

Không nên công bố IP chỉ vì registry cho phép lưu IP. Địa chỉ phải được kiểm thử từ nơi consumer chạy và phải có vòng đời phù hợp với cách triển khai instance.

## 14. Kết luận

Địa chỉ lắng nghe mô tả nơi tiến trình Spring Boot mở socket; địa chỉ công bố mô tả host, port và scheme mà Eureka hoặc Consul trả cho consumer; khả năng định tuyến xác định consumer có thực sự kết nối được tới địa chỉ đó hay không. server.address và server.port điều khiển bind/listen, còn spring.cloud.consul.discovery.hostname/ip-address/port hoặc eureka.instance.hostname/ip-address/port điều khiển thông tin đăng ký.

Trong Docker và Kubernetes, ưu tiên hostname hoặc service DNS ổn định trong đúng phạm vi mạng, đồng thời dùng container port hoặc Service port phù hợp. Khi có NAT hoặc reverse proxy, công bố địa chỉ mà consumer thực sự truy cập và cấu hình health check theo đường đi mà agent có thể sử dụng. Cuối cùng, xác minh DNS, TCP, HTTP/TLS từ chính consumer; một registration thành công không chứng minh route đã hoạt động.

## Tài liệu tham khảo

- [Spring Boot — Embedded Web Servers](https://docs.spring.io/spring-boot/how-to/webserver.html)
- [Spring Cloud Consul — Configuring the Service Hostname and IP Address](https://docs.spring.io/spring-cloud-consul/reference/discovery.html)
- [Spring Cloud Consul — Common Application Properties](https://docs.spring.io/spring-cloud-consul/reference/appendix.html)
- [Spring Cloud Netflix — Eureka Instance Configuration](https://docs.spring.io/spring-cloud-netflix/reference/configprops.html)
- [Spring Cloud Netflix — Registering a Secure Application and Eureka Instance URLs](https://docs.spring.io/spring-cloud-netflix/reference/spring-cloud-netflix.html)
- [Docker Compose — Networking](https://docs.docker.com/compose/how-tos/networking/)

