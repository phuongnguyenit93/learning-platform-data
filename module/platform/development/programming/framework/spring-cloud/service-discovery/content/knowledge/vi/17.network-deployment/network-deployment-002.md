# Localhost trên máy chủ, trong container và trong mạng riêng

Một lỗi phổ biến khi triển khai microservice là cấu hình provider bằng địa chỉ localhost rồi mong một tiến trình ở máy hoặc container khác truy cập được. Nguyên nhân là localhost luôn trỏ về **network namespace của chính caller**. Host, mỗi container và mỗi máy trong mạng riêng có loopback riêng; chúng không dùng chung một địa chỉ localhost.

Trong Spring Cloud Service Discovery, điều này rất quan trọng. Provider có thể đăng ký thành công với Eureka hoặc Consul, consumer có thể tìm thấy serviceId, nhưng request vẫn thất bại nếu registry công bố địa chỉ chỉ truy cập được từ một network khác. Muốn định tuyến đúng, cần phân biệt địa chỉ bind của ứng dụng, địa chỉ registry công bố và địa chỉ consumer thực sự có thể gọi.

## 1. Localhost thực sự có nghĩa gì?

Localhost thường được phân giải về loopback interface của máy hoặc network namespace hiện tại. IPv4 thường dùng 127.0.0.1; IPv6 dùng ::1. Gói tin gửi đến loopback được xử lý ngay trong namespace đó, không đi qua mạng vật lý hay Docker bridge.

Vì vậy:

- Khi chạy ứng dụng trực tiếp trên host, localhost là host.
- Khi chạy ứng dụng trong container A, localhost là container A.
- Khi chạy consumer trong container B, localhost là container B.
- Khi chạy ứng dụng trên máy 10.10.0.20, localhost là máy 10.10.0.20; máy 10.10.0.21 có localhost riêng.

Ví dụ, inventory-service chạy trong container ở cổng 8080. Request từ chính container đó đến http://localhost:8080 có thể thành công. Nhưng order-service ở container khác gọi http://localhost:8080 sẽ kết nối đến cổng 8080 của chính order-service, không phải inventory-service.

~~~mermaid
flowchart TB
    subgraph Host["Máy chủ Docker"]
        HostLoop["Host loopback<br/>127.0.0.1"]
        subgraph A["Container A: inventory"]
            ALoop["Loopback A<br/>127.0.0.1"]
            AApp["Inventory API :8080"]
            ALoop --> AApp
        end
        subgraph B["Container B: order"]
            BLoop["Loopback B<br/>127.0.0.1"]
            BApp["Order API :8080"]
            BLoop --> BApp
        end
    end
    HostLoop -. "Không phải cùng loopback" .-> ALoop
    ALoop -. "Không phải cùng loopback" .-> BLoop
~~~

Ba địa chỉ 127.0.0.1 trong hình có cùng giá trị số nhưng nằm trong ba network namespace khác nhau. Chúng không trỏ đến cùng một máy logic.

## 2. Phân biệt bind address và destination address

Ứng dụng server cần lắng nghe trên một interface. Địa chỉ bind quyết định interface nào nhận kết nối; destination address là địa chỉ mà client dùng để mở kết nối.

| Địa chỉ | Ý nghĩa | Có nên dùng làm địa chỉ đích cho consumer? |
|---|---|---|
| 127.0.0.1 hoặc ::1 | Chỉ nhận kết nối từ loopback namespace hiện tại | Chỉ khi consumer ở cùng namespace |
| 0.0.0.0 | Bind trên mọi interface IPv4 của namespace | Không; đây là địa chỉ bind, không phải địa chỉ đích |
| IP private, ví dụ 10.10.0.20 | Interface trong mạng nội bộ | Có, nếu consumer có route và firewall cho phép |
| IP container, ví dụ 172.20.0.5 | Interface của container trên Docker network | Có, nếu consumer cùng network hoặc có route đến subnet đó |
| DNS service name, ví dụ inventory-api | Tên được DNS của network phân giải | Có, nếu consumer dùng DNS đó và tên trỏ đến endpoint phù hợp |
| IP host và published port | Địa chỉ host sau khi Docker publish port | Có, nếu consumer truy cập được host và port |

Trong Spring Boot, thuộc tính server.address điều khiển địa chỉ bind của web server. Nếu container cần nhận request từ các container khác trong cùng network, ứng dụng thường phải bind trên interface container:

~~~yaml
server:
  address: 0.0.0.0
  port: 8080
~~~

Nếu chỉ bind vào 127.0.0.1 bên trong container, Docker có thể publish port ra host nhưng kết nối chuyển tiếp vẫn không đến được socket chỉ lắng nghe loopback. Hãy kiểm tra bind address khi port mapping có vẻ đúng nhưng kết nối vẫn bị refused.

Không đăng ký 0.0.0.0 làm địa chỉ service. Địa chỉ này có nghĩa “mọi interface” khi bind; nó không xác định một đích mà consumer có thể định tuyến đến.

Trên host vật lý, không nhất thiết phải bind tất cả interface. Có thể bind vào một IP private cụ thể nếu chỉ muốn nhận traffic từ một mạng. Khi bind 0.0.0.0, cần giới hạn cổng bằng firewall hoặc security group.

## 3. Chọn địa chỉ theo vị trí của caller

| Caller | Provider | Địa chỉ thường dùng |
|---|---|---|
| Process trên cùng host | Process trên host | localhost và port ứng dụng |
| Host | Container có publish port | localhost hoặc IP host cùng published port |
| Container A | Container B cùng Docker network | Compose service name và container port |
| Container | Ứng dụng trên host | host.docker.internal và port host, nếu môi trường hỗ trợ |
| Máy khác trong private network | Host hoặc VM | Private DNS/IP và port được mở |
| Máy qua VPN | Dịch vụ trong mạng private | Private DNS/IP có route qua VPN |
| Consumer ngoài mạng | Dịch vụ nội bộ | Public endpoint, ingress hoặc reverse proxy được kiểm soát |

Đừng chọn địa chỉ chỉ vì nó hoạt động từ terminal hiện tại. Hãy chọn dựa trên vị trí thực tế của consumer. Lệnh curl chạy trên host không chứng minh container khác cũng truy cập được; curl chạy trong một container không chứng minh laptop hoặc máy qua VPN có route đến cùng địa chỉ.

## 4. Container gọi container qua Docker Compose network

Docker Compose tạo DNS nội bộ cho các service trên cùng network. Container có thể dùng tên service làm hostname thay vì phụ thuộc vào IP container thay đổi theo lần tạo.

Ví dụ:

~~~yaml
services:
  inventory-api:
    image: inventory-service:1.0
    networks:
      - backend
    expose:
      - "8080"

  order-api:
    image: order-service:1.0
    environment:
      INVENTORY_BASE_URL: http://inventory-api:8080
    networks:
      - backend

networks:
  backend:
    driver: bridge
~~~

Order service gọi inventory bằng hostname inventory-api và port nội bộ 8080. Không dùng localhost:8080 vì localhost lúc này là container order-api.

Thuộc tính expose chỉ mô tả cổng nội bộ cho người đọc cấu hình và công cụ; nó không publish cổng ra host. Các container cùng network có thể kết nối đến port mà ứng dụng đang lắng nghe ngay cả khi không khai báo expose.

Nếu hai service không nằm trong cùng network, DNS service name có thể không phân giải và traffic có thể không có route. Hãy gắn chúng vào một network chung hoặc cấu hình gateway phù hợp. Tránh đưa tất cả container vào một mạng rộng nếu không cần thiết.

IP của container có thể thay đổi khi container được tạo lại. Dùng service DNS của Docker cho giao tiếp trực tiếp trong cùng network. Khi dùng service discovery, registry phải trả về địa chỉ instance mà consumer thực sự truy cập được; DNS name hoặc IP đăng ký cần phù hợp với kiến trúc đó.

## 5. Host truy cập container qua port mapping

Port mapping chuyển tiếp một cổng trên host đến cổng trong container:

~~~yaml
services:
  inventory-api:
    image: inventory-service:1.0
    ports:
      - "18080:8080"
~~~

Cặp giá trị có thứ tự host-port:container-port. Trong ví dụ, host nhận kết nối ở cổng 18080 rồi Docker chuyển đến cổng 8080 trong container.

Từ host, gọi:

~~~bash
curl http://localhost:18080/actuator/health
~~~

Từ một container khác cùng network, gọi:

~~~bash
curl http://inventory-api:8080/actuator/health
~~~

Hai request đi đến cùng ứng dụng nhưng dùng hai địa chỉ khác nhau. Consumer trong container không nên đi vòng qua host published port nếu có thể dùng network nội bộ; đường nội bộ thường ít bước hơn và không cần expose cổng ra host.

Có thể giới hạn publish vào loopback host nếu chỉ ứng dụng trên host cần truy cập:

~~~yaml
ports:
  - "127.0.0.1:18080:8080"
~~~

Khi bind published port vào 127.0.0.1, máy khác trong LAN không truy cập được qua IP LAN của host. Nếu cần caller ở mạng khác, hãy publish vào interface phù hợp và cấu hình firewall theo đúng phạm vi truy cập.

## 6. Container gọi ứng dụng đang chạy trên host

Một container có thể cần gọi database, mock server hoặc công cụ phát triển đang chạy trực tiếp trên host. Trong Docker Desktop, tên host.docker.internal thường được cung cấp để container truy cập host.

Ví dụ:

~~~yaml
services:
  integration-test:
    image: test-runner:1.0
    extra_hosts:
      - "host.docker.internal:host-gateway"
~~~

Trên Docker Engine Linux, host.docker.internal có thể cần khai báo host-gateway như trên tùy phiên bản và cấu hình. Docker Desktop thường cung cấp tên này sẵn.

Từ container:

~~~bash
curl http://host.docker.internal:9090/health
~~~

Ứng dụng trên host phải lắng nghe trên interface có thể truy cập qua gateway đó. Nếu ứng dụng chỉ bind vào 127.0.0.1 của host, một số cấu hình bridge sẽ không thể truy cập qua địa chỉ gateway. Có thể bind vào IP host/gateway phù hợp và giới hạn firewall để không mở rộng truy cập ngoài ý muốn.

Không thay host.docker.internal bằng một IP gateway hard-code nếu không có lý do vận hành rõ ràng. Gateway có thể khác giữa Docker Desktop, Linux bridge, WSL và các môi trường CI.

## 7. Giao tiếp trong mạng riêng, LAN và VPN

Private network thường sử dụng dải địa chỉ RFC 1918 như:

- 10.0.0.0/8
- 172.16.0.0/12
- 192.168.0.0/16

Ví dụ provider chạy trên máy 10.20.1.15, cổng 8080. Consumer ở máy 10.20.1.30 có thể gọi địa chỉ này nếu:

1. Hai máy có route đến nhau.
2. Ứng dụng bind trên interface private phù hợp.
3. Firewall/security group cho phép TCP 8080 từ subnet consumer.
4. Không có NAT hoặc policy route chuyển traffic đến đích khác.
5. DNS nội bộ, nếu sử dụng, phân giải về địa chỉ đúng từ network consumer.

Một hostname như inventory.internal có thể phân giải thành 10.20.1.15. Nếu môi trường có split-horizon DNS, cùng hostname có thể trả về IP khác nhau tùy mạng của caller. Điều đó có thể hữu ích, nhưng cần xác minh mọi consumer nhận được địa chỉ phù hợp.

Khi consumer kết nối qua VPN, cần kiểm tra route của subnet, DNS được cấp qua VPN và chính sách firewall. Việc VPN hiển thị trạng thái connected không bảo đảm route đến mọi subnet private đã được cài đặt.

Không công bố IP private cho consumer ở Internet nếu không có VPN hoặc đường kết nối riêng. Consumer bên ngoài cần một endpoint được công bố có chủ đích như API gateway, ingress, reverse proxy hoặc public load balancer.

## 8. Vì sao service discovery tìm thấy service nhưng vẫn gọi thất bại?

Service discovery giải quyết việc tìm instance theo tên logic. Registry lưu hoặc trả về địa chỉ host/port của từng instance. Spring Cloud LoadBalancer chọn một instance và HTTP client kết nối đến địa chỉ đó.

Registry không tự tạo network route. Nếu provider đăng ký localhost, IP container chỉ tồn tại trong bridge riêng, hostname chỉ phân giải trong một network hoặc port nội bộ không được mở cho consumer, request sẽ thất bại dù tra cứu thành công.

~~~mermaid
sequenceDiagram
    participant P as Provider
    participant R as Service Registry
    participant C as Consumer
    P->>R: Đăng ký serviceId và instance address
    C->>R: Tra cứu serviceId
    R-->>C: Trả về host và port đã đăng ký
    C->>C: LoadBalancer chọn instance
    C->>P: HTTP request đến địa chỉ thực tế
    Note over C,P: Nếu địa chỉ không có route hoặc sai port, request thất bại
~~~

Ví dụ sai: provider trong container đăng ký 127.0.0.1:8080. Consumer nhận đúng địa chỉ đó nhưng gọi localhost của chính consumer.

Ví dụ khác: provider đăng ký 172.20.0.5:8080, địa chỉ chỉ tồn tại trong Docker network A. Consumer ở private network B không có route đến subnet 172.20.0.0/16. Registry vẫn trả kết quả hợp lệ theo dữ liệu đã lưu, nhưng địa chỉ không thể sử dụng từ consumer.

Vì vậy, trước khi kết luận discovery bị lỗi, hãy kiểm tra địa chỉ instance mà registry trả về và thử kết nối từ chính môi trường consumer.

## 9. Cấu hình địa chỉ instance trong Eureka

Eureka Client đăng ký application name, instance ID, hostname/IP và port. Consumer dùng serviceId để lấy instance list; Spring Cloud LoadBalancer chọn instance và gửi request đến URI của nó.

Một cấu hình provider minh họa khi provider và consumer cùng Docker network:

~~~yaml
spring:
  application:
    name: inventory-service

server:
  address: 0.0.0.0
  port: 8080

eureka:
  client:
    service-url:
      defaultZone: http://eureka-server:8761/eureka/
  instance:
    prefer-ip-address: true
    instance-id: ${spring.application.name}:${HOSTNAME:local}:${server.port}
~~~

Trong ví dụ, Eureka Server được gọi qua tên service eureka-server trên Docker network. Provider lắng nghe trên mọi interface của container. prefer-ip-address yêu cầu client công bố IP thay vì hostname; điều này chỉ phù hợp nếu IP đó có thể truy cập từ các consumer.

Nếu consumer nằm ngoài Docker network, địa chỉ container mà Eureka công bố có thể không dùng được. Khi đó cần chọn một kiến trúc địa chỉ phù hợp: đưa consumer vào cùng private network, công bố hostname có route từ consumer, hoặc dùng gateway/proxy có thể truy cập từ cả hai phía. Đừng chỉ bật prefer-ip-address rồi cho rằng mọi client đều truy cập được.

Có thể cấu hình hostname cụ thể nếu DNS nội bộ có tên duy nhất cho từng instance và consumer phân giải được tên đó. Với nhiều replica, tránh để tất cả instance công bố cùng một hostname đơn lẻ nếu hostname không ánh xạ đúng đến từng instance; nếu cần một địa chỉ chung thì nên dùng load balancer hoặc endpoint gateway có thiết kế rõ ràng.

Nếu nhiều consumer ở các network không có route chung, một service registration duy nhất có thể không đủ. Có thể tạo registration/endpoint riêng theo network hoặc để consumer đi qua gateway. Cần bảo đảm serviceId, metadata và chính sách chọn instance nhất quán; metadata chỉ có ích khi consumer hoặc LoadBalancer thực sự lọc theo nó.

## 10. Cấu hình Consul và health check

Consul service registration cũng có địa chỉ service riêng. Agent có thể kiểm tra ứng dụng bằng URL nội bộ, trong khi consumer dùng service address có thể truy cập từ mạng của mình.

Ví dụ registration:

~~~json
{
  "service": {
    "name": "inventory-service",
    "id": "inventory-node-a",
    "address": "10.20.1.15",
    "port": 8080,
    "checks": [
      {
        "http": "http://127.0.0.1:8080/actuator/health",
        "interval": "10s",
        "timeout": "2s"
      }
    ]
  }
}
~~~

Ví dụ này chỉ phù hợp khi Consul agent chạy cùng network namespace với ứng dụng hoặc loopback 127.0.0.1 từ agent thực sự trỏ đến ứng dụng. Nếu agent chạy trong container khác, localhost trong check URL là chính container agent. Khi đó dùng DNS/IP mà agent truy cập được, chẳng hạn inventory-api:8080 trong cùng Docker network.

Address và Port trong registration là dữ liệu consumer nhận được. HTTP check URL là địa chỉ agent gọi để kiểm tra. Hai địa chỉ có thể khác nhau, nhưng phải dẫn đến đúng service và được truy cập từ hai network tương ứng.

Khi service được consumer ở nhiều mạng dùng chung, cần chọn địa chỉ công bố theo nhóm consumer. Một agent check passing không chứng minh mọi consumer có thể truy cập service address.

## 11. Những cấu hình thường gây lỗi

| Cấu hình | Vì sao lỗi | Cách sửa |
|---|---|---|
| Consumer container gọi localhost:8080 để đến provider container | localhost là loopback của consumer | Dùng service DNS và container port |
| Provider bind 127.0.0.1 trong container | Chỉ nhận kết nối trong container đó | Bind interface container, thường là 0.0.0.0 |
| Eureka đăng ký 127.0.0.1 | Consumer nhận loopback của chính nó | Công bố IP/DNS có thể truy cập từ consumer |
| Registry trả IP bridge nhưng consumer ở mạng khác | Consumer không có route đến subnet container | Dùng network chung, private route hoặc gateway |
| Consumer dùng container port từ host | Container port chưa chắc được publish | Dùng host published port |
| Consumer dùng host published port từ container cùng network | Đi vòng qua host NAT và có thể gặp hairpin/NAT policy | Dùng service DNS và container port |
| Container gọi localhost của host | Loopback trỏ về container | Dùng host.docker.internal hoặc host gateway phù hợp |
| Dùng 0.0.0.0 làm destination | Đây là wildcard bind address | Dùng IP hoặc hostname cụ thể |
| Health check chạy được nhưng consumer timeout | Agent và consumer có network view khác nhau | Test địa chỉ từ đúng namespace của từng bên |

## 12. Quy trình chẩn đoán từ đúng vị trí gọi

Khi request thất bại, hãy kiểm tra theo thứ tự:

1. Xác định caller chạy ở đâu: host, container, VM, Kubernetes pod hay máy qua VPN.
2. Ghi lại địa chỉ đích chính xác: hostname/IP, port và scheme.
3. Xác định địa chỉ bind của provider và interface mà ứng dụng đang lắng nghe.
4. Nếu dùng registry, đọc instance address mà consumer thực sự nhận được.
5. Kiểm tra DNS từ chính caller, không chỉ từ host vận hành.
6. Kiểm tra route và firewall từ caller đến destination.
7. Kiểm tra port mapping nếu destination đi qua Docker host.
8. Dùng curl hoặc công cụ TCP từ đúng môi trường caller.
9. Đối chiếu log server để xác định request có đến ứng dụng hay chưa.
10. Sau khi đổi địa chỉ registration, chờ discovery cache cập nhật và kiểm tra lại từ consumer.

Ví dụ kiểm tra DNS và HTTP từ container:

~~~bash
getent hosts inventory-api
curl -v --connect-timeout 3 http://inventory-api:8080/actuator/health
~~~

Trên image tối giản có thể không cài getent hoặc curl. Có thể dùng công cụ tương đương sẵn có trong image, hoặc chạy một container debug tạm thời trên cùng network. Kết quả phải được lấy từ network namespace tương ứng với caller.

Trên host, kiểm tra published port:

~~~bash
curl -v --connect-timeout 3 http://127.0.0.1:18080/actuator/health
~~~

Từ một máy khác trong private network, dùng IP hoặc DNS mà máy đó phân giải được:

~~~bash
curl -v --connect-timeout 3 http://10.20.1.15:8080/actuator/health
~~~

Nếu lệnh host thành công nhưng lệnh từ container thất bại, vấn đề có thể nằm ở DNS, network attachment hoặc route của container. Nếu lệnh từ container thành công nhưng từ VPN thất bại, kiểm tra VPN route, DNS và firewall của private network.

## 13. Lưu ý khi chạy trên Kubernetes

Kubernetes cũng dùng network namespace riêng cho mỗi Pod. localhost trong một container trỏ về Pod network namespace; các container trong cùng Pod chia sẻ network namespace nên có thể gọi nhau qua localhost nếu dùng port khác nhau.

Các Pod khác nhau nên giao tiếp qua Service DNS, ví dụ inventory-service.default.svc.cluster.local, và port của Kubernetes Service. Không đăng ký localhost làm địa chỉ instance cho consumer ở Pod khác.

Kubernetes Service có thể cung cấp một virtual IP ổn định và phân phối traffic đến các Pod đủ điều kiện theo readiness. Nếu kết hợp Spring Cloud Discovery với Kubernetes, cần quyết định rõ lớp nào chịu trách nhiệm discovery/load balancing để tránh hai tầng định tuyến chồng chéo ngoài ý muốn.

Pod IP thường chỉ có ý nghĩa trong cluster network. Consumer bên ngoài cluster cần ingress, gateway, load balancer hoặc VPN route được cấu hình. Không công bố Pod IP cho client Internet.

## 14. Bảo mật khi mở cổng và công bố địa chỉ

Để một địa chỉ có thể truy cập được không có nghĩa là nên mở nó cho mọi mạng. Khi bind vào 0.0.0.0 hoặc publish port, hãy giới hạn nguồn truy cập bằng firewall, security group hoặc network policy.

Một số nguyên tắc:

- Chỉ publish cổng cần thiết ra host.
- Giới hạn published port vào loopback nếu chỉ host cần truy cập.
- Không expose trực tiếp registry dashboard/API ra Internet.
- Dùng private DNS và private network cho giao tiếp nội bộ khi phù hợp.
- Dùng TLS cho kết nối qua mạng không tin cậy và xác minh certificate.
- Không công bố địa chỉ quản trị hoặc cổng debug trong service registration dùng cho consumer.
- Kiểm tra ACL và quyền đăng ký service để tránh workload giả mạo địa chỉ instance.
- Sau khi thay đổi IP, port mapping hoặc gateway, cập nhật registration và dọn record cũ.

Địa chỉ được công bố trong registry là một phần của cấu hình định tuyến. Cần coi nó như dữ liệu quan trọng, có kiểm soát và có thể kiểm toán.

## 15. Checklist trước khi đưa service vào registry

Trước khi bật auto-registration cho provider, xác nhận:

1. Provider bind trên interface phù hợp với network của consumer.
2. Consumer không dùng localhost để gọi một host/container khác namespace.
3. Port trong registry là port mà consumer thực sự có thể kết nối.
4. Hostname/IP được công bố phân giải và định tuyến được từ consumer.
5. Nếu dùng Docker, provider và consumer có network chung hoặc có gateway/port mapping hợp lệ.
6. Nếu dùng host.docker.internal, môi trường Docker hỗ trợ tên đó và host service lắng nghe trên interface phù hợp.
7. Nếu dùng private network/VPN, route, DNS và firewall cho phép kết nối hai chiều cần thiết.
8. Health check được thử từ network namespace của agent thực hiện check.
9. HTTP request được thử từ network namespace của consumer thực hiện request.
10. Sau khi container restart hoặc IP thay đổi, registry cập nhật địa chỉ và consumer loại bỏ dữ liệu cũ.

Điểm cần nhớ là: **localhost luôn thuộc về network namespace của caller; địa chỉ bind quyết định server lắng nghe ở đâu; địa chỉ service trong registry phải là đích mà consumer có thể truy cập.** Khi xác định đúng vị trí của caller và provider, việc chọn localhost, service DNS, host gateway hay private IP sẽ trở nên rõ ràng.

