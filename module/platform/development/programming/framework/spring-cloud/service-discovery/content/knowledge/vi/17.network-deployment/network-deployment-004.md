# Cổng trong container, cổng công bố và ánh xạ NAT

Khi triển khai microservice bằng Docker hoặc Kubernetes, một ứng dụng có thể lắng nghe trên một cổng bên trong container hoặc Pod, trong khi client ở bên ngoài truy cập qua một cổng khác. Hạ tầng mạng thực hiện ánh xạ giữa hai cổng đó bằng port publishing, Service, load balancer hoặc NAT.

Với Spring Cloud Service Discovery, điều quan trọng là registry phải công bố đúng địa chỉ và cổng mà consumer có thể truy cập. Một instance có thể chạy ở cổng 8081 bên trong container nhưng được publish thành cổng 18081 trên host. Consumer ở cùng Docker network thường gọi cổng 8081; consumer đi qua host NAT có thể phải gọi cổng 18081. Nếu provider đăng ký nhầm cặp host/port, service vẫn có thể xuất hiện trong Eureka hoặc Consul nhưng request sẽ thất bại.

Bài viết phân biệt các loại cổng, giải thích port mapping và NAT, trình bày ví dụ Docker/Kubernetes, và chỉ ra cách chọn địa chỉ đăng ký phù hợp với vị trí mạng của consumer.

## 1. Ba khái niệm cổng cần phân biệt

Khi đọc cấu hình container, cần phân biệt:

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Container port | Cổng mà tiến trình ứng dụng lắng nghe trong network namespace của container | Spring Boot lắng nghe 8081 |
| Published/host port | Cổng được công bố trên host để client bên ngoài container truy cập | Host nhận tại 18081 |
| Target port | Cổng đích mà lớp chuyển tiếp gửi request vào container hoặc Pod | 8081 |

Ví dụ:

~~~text
Spring Boot trong container
  server.port = 8081
        |
        v
Container IP:8081
        |
        | Port mapping / DNAT
        v
Host IP:18081
~~~

Ứng dụng vẫn lắng nghe trên 8081. Việc publish port 18081 không thay đổi giá trị server.port bên trong Spring Boot; nó tạo một đường truy cập từ host hoặc mạng bên ngoài đến cổng 8081 của container.

### EXPOSE không giống publish port

Trong Dockerfile:

~~~dockerfile
EXPOSE 8081
~~~

EXPOSE ghi nhận cổng mà container dự kiến sử dụng như metadata của image. Chỉ thị này không tự mở cổng trên host, không tạo NAT mapping và không bảo đảm firewall cho phép truy cập.

Muốn publish cổng, cần cấu hình lúc chạy container, ví dụ:

~~~bash
docker run -p 18081:8081 inventory-service:latest
~~~

Quy tắc đọc là host-port:container-port. Docker chuyển lưu lượng đến host port 18081 vào port 8081 của container.

## 2. Port publishing và ánh xạ NAT trong Docker

Khi publish port, Docker tạo cơ chế chuyển tiếp lưu lượng từ địa chỉ host đến địa chỉ và cổng của container. Tùy nền tảng và chế độ mạng, việc này có thể được triển khai bằng iptables/nftables, proxy hoặc cơ chế mạng tương đương.

~~~mermaid
flowchart LR
    CLIENT["Client bên ngoài"]
    HOST["Docker host<br/>192.0.2.10:18081"]
    NAT["Port mapping / DNAT<br/>18081 -> 8081"]
    CONTAINER["Container<br/>172.20.0.5:8081"]
    APP["Spring Boot<br/>server.port=8081"]
    CLIENT --> HOST
    HOST --> NAT
    NAT --> CONTAINER
    CONTAINER --> APP
~~~

Ví dụ Docker:

~~~bash
docker run --name inventory \
  -p 18081:8081 \
  inventory-service:latest
~~~

Trong ví dụ:

- Spring Boot lắng nghe cổng 8081 trong container.
- Docker công bố cổng 18081 trên host.
- Client bên ngoài gọi host-address:18081.
- Docker chuyển request đến container-address:8081.

Nếu chỉ khai báo -p 8081:8081, host port và container port có cùng số nhưng vẫn là hai đầu của một mapping riêng.

### Bind địa chỉ host cụ thể

Có thể giới hạn interface mà host port được publish:

~~~bash
docker run -p 127.0.0.1:18081:8081 inventory-service:latest
~~~

Cấu hình này chỉ publish cổng trên loopback của host. Client từ máy khác không thể truy cập qua địa chỉ mạng của host bằng mapping này.

Nếu bỏ địa chỉ bind:

~~~bash
docker run -p 18081:8081 inventory-service:latest
~~~

Docker thường publish trên các interface host theo mặc định. Cần kết hợp firewall và network policy để giới hạn nguồn truy cập. Không publish một cổng ra mọi interface chỉ vì muốn các container khác gọi được nhau; các container cùng user-defined network thường có thể giao tiếp trực tiếp bằng service/container DNS và container port.

### Publish cổng ngẫu nhiên

Docker có thể chọn host port động:

~~~bash
docker run -P inventory-service:latest
~~~

Với -P, các cổng EXPOSE được publish ra host port được chọn tự động. Host port có thể thay đổi giữa các lần chạy. Nếu một registry đăng ký địa chỉ host, cần biết host port thực tế sau khi container được tạo. Không nên giả định host port luôn trùng container port.

Kiểm tra mapping đang có:

~~~bash
docker port inventory
docker inspect inventory
~~~

## 3. Địa chỉ và cổng nào cần đăng ký vào service registry?

Registry cần lưu địa chỉ mà consumer sẽ dùng để gọi instance. Địa chỉ đó phụ thuộc vào vị trí của consumer và đường mạng được thiết kế.

Giả sử:

~~~text
Docker host:       192.0.2.10
Container IP:      172.20.0.5
Container port:    8081
Published port:    18081
Service ID:        inventory-service
~~~

Có thể có hai đường gọi khác nhau:

| Vị trí consumer | Địa chỉ có thể dùng |
|---|---|
| Container khác cùng Docker network | inventory:8081 hoặc container DNS/IP:8081 |
| Client đi qua Docker host | 192.0.2.10:18081 |

Nếu order-service và inventory-service ở cùng Docker network, order-service thường nên gọi inventory-service:8081. Đường gọi này không cần vòng qua host published port.

Nếu consumer ở ngoài Docker host, nó có thể không định tuyến được tới IP riêng 172.20.0.5. Khi đó cần công bố địa chỉ host có thể truy cập cùng published port 18081, hoặc đặt một load balancer/reverse proxy có địa chỉ ổn định phía trước.

Không có một host/port duy nhất luôn đúng cho mọi consumer. Provider phải đăng ký endpoint phù hợp với network scope mà consumer thực sự sử dụng. Nếu consumer ở nhiều network scope khác nhau, nên thiết kế ranh giới discovery hoặc một địa chỉ trung gian ổn định thay vì quảng bá một địa chỉ chỉ truy cập được từ một nhóm.

## 4. Đăng ký sai cổng khiến discovery tìm thấy nhưng không gọi được

Một lỗi thường gặp là provider đăng ký container port trong khi consumer lại gọi qua host port, hoặc ngược lại.

Ví dụ provider lắng nghe trong container ở 8081, Docker publish 18081. Nếu provider đăng ký host 192.0.2.10 nhưng port 8081, consumer bên ngoài sẽ gọi:

~~~text
http://192.0.2.10:8081
~~~

Trong khi mapping thực tế chỉ nhận ở:

~~~text
http://192.0.2.10:18081
~~~

Kết quả có thể là connection refused hoặc timeout. Eureka/Consul vẫn có thể hiển thị instance vì thao tác đăng ký chỉ lưu thông tin được cung cấp; registry không nhất thiết kiểm tra mọi đường mạng từ từng consumer.

Ngược lại, nếu consumer cùng Docker network gọi host port 18081 trong khi host mapping chỉ bind loopback hoặc không thể định tuyến từ container, request cũng có thể thất bại. Hãy xác định đường đi mạng trước khi chọn địa chỉ đăng ký.

~~~mermaid
flowchart TD
    R["Registry trả về host:8081"]
    C["Consumer bên ngoài Docker host"]
    BAD["Sai đích: host:8081"]
    GOOD["Đích đúng: host:18081"]
    APP["Container app:8081"]
    R --> C
    C --> BAD
    BAD -->|"Không có mapping tương ứng"| FAIL["Connection refused / timeout"]
    C --> GOOD
    GOOD -->|"DNAT 18081 -> 8081"| APP
~~~

## 5. Cấu hình Spring Boot và Docker Compose

Giả sử inventory-service chạy trong container tại port 8081 và publish host port 18081.

Docker Compose:

~~~yaml
services:
  inventory-service:
    image: inventory-service:latest
    environment:
      SERVER_PORT: 8081
    ports:
      - "18081:8081"
    networks:
      - backend

  order-service:
    image: order-service:latest
    networks:
      - backend

networks:
  backend:
    driver: bridge
~~~

Spring Boot trong inventory-service lắng nghe port 8081. Từ order-service cùng network, địa chỉ gọi phù hợp là:

~~~text
http://inventory-service:8081
~~~

Từ máy host, địa chỉ truy cập là:

~~~text
http://localhost:18081
~~~

Đây là hai đường truy cập khác nhau tới cùng ứng dụng. Nếu order-service dùng service discovery, thông tin provider đăng ký phải tương thích với mạng mà order-service sử dụng. Trong ví dụ này, provider nên quảng bá tên DNS inventory-service và port 8081 cho consumer cùng network.

### Cấu hình Eureka cho consumer cùng Docker network

Ví dụ provider có thể công bố hostname có thể phân giải trên Docker network:

~~~yaml
spring:
  application:
    name: inventory-service

server:
  port: 8081

eureka:
  instance:
    hostname: inventory-service
    prefer-ip-address: false
    non-secure-port: 8081
~~~

Tên hostname chỉ phù hợp nếu consumer có thể phân giải inventory-service và kết nối tới port 8081 trên cùng network. Cần kiểm tra bản ghi instance trong Eureka để xác nhận hostname và port thực tế được đăng ký đúng như mong muốn.

Nếu consumer nằm ngoài Docker network và chỉ truy cập qua host published port, provider cần quảng bá địa chỉ host và port 18081 hoặc sử dụng một gateway/load balancer ổn định. Một Eureka instance thông thường không tự biết rằng một consumer cụ thể cần dùng host port còn consumer khác cần dùng container port.

### Không để một cấu hình registration dùng sai cho mọi network

Một provider có thể có nhiều đường truy cập nhưng Eureka registration thường cung cấp một endpoint chính cho instance. Nếu có consumer ở cả trong và ngoài Docker network, cân nhắc:

- Đưa các consumer qua một API Gateway hoặc load balancer có địa chỉ ổn định.
- Tách registry hoặc discovery scope theo network nếu hai nhóm consumer cần endpoint khác nhau.
- Dùng DNS định tuyến phù hợp với mạng của từng consumer khi hạ tầng hỗ trợ split-horizon DNS.
- Đặt provider và consumer vào cùng một network overlay có thể định tuyến thống nhất.

Không nên đăng ký hai instance giả cùng service ID chỉ để biểu diễn hai cổng của một tiến trình nếu không có chính sách định tuyến và quản lý vòng đời rõ ràng. Cách đó có thể khiến LoadBalancer gửi request lặp hoặc phân phối không đúng.

## 6. Cấu hình Consul: agent port và service port là hai cổng khác nhau

Với Consul, ứng dụng kết nối tới HTTP API của agent, thường là port 8500. Đây là địa chỉ để đăng ký và truy vấn catalog. Service port là cổng của ứng dụng provider mà consumer sẽ gọi.

Ví dụ:

~~~yaml
spring:
  application:
    name: inventory-service
  cloud:
    consul:
      host: consul-agent
      port: 8500
      discovery:
        service-name: inventory-service
        hostname: inventory-service
        port: 8081
        prefer-ip-address: false
~~~

Trong ví dụ:

- consul-agent:8500 là Consul agent API endpoint.
- inventory-service:8081 là địa chỉ service được đăng ký.
- Consumer cùng network gọi provider qua service instance address.

Tên thuộc tính chi tiết có thể thay đổi theo phiên bản Spring Cloud Consul. Hãy kiểm tra cấu hình được hỗ trợ trong release train đang dùng và xác minh địa chỉ thực tế trong Consul catalog. Không lấy port 8500 của agent làm service port của inventory-service.

## 7. NAT, firewall và nhiều lớp ánh xạ

Trong một hệ thống thực tế, request có thể đi qua nhiều lớp:

~~~text
Internet client
  -> Public IP:443
  -> Cloud Load Balancer:443
  -> Node IP:NodePort
  -> Pod IP:8081
  -> Spring Boot
~~~

Mỗi lớp có thể thay đổi địa chỉ hoặc cổng đích. Registry cần công bố endpoint mà consumer có thể truy cập trong kiến trúc đó. Nếu consumer gọi qua gateway, thường nên dùng địa chỉ gateway ổn định thay vì đăng ký IP private của Pod.

NAT chỉ chuyển tiếp gói tin theo mapping. Nó không tự cập nhật service registry và không tự thay đổi metadata đã đăng ký. Khi host port, public IP hoặc mapping thay đổi, registration hoặc DNS/gateway tương ứng cũng phải được cập nhật.

Firewall và security group là lớp kiểm soát riêng. Một port đã publish vẫn có thể bị chặn bởi firewall. Ngược lại, việc mở firewall không tạo ra mapping nếu host port chưa được publish hoặc service không lắng nghe ở target port.

### Phân biệt bind address và advertised address

Ứng dụng có thể bind trên:

- 127.0.0.1: chỉ nhận kết nối loopback trong network namespace của ứng dụng.
- 0.0.0.0: nhận kết nối trên các IPv4 interface của network namespace đó.
- Một IP cụ thể: chỉ nhận kết nối qua interface tương ứng.

Trong container, bind 127.0.0.1 thường khiến tiến trình chỉ nhận kết nối từ chính container. Docker port publishing không thể làm ứng dụng trong container nhận kết nối qua interface mà nó không lắng nghe.

Advertised address là địa chỉ mà provider công bố cho registry. Nó có thể khác địa chỉ bind, nhưng phải dẫn đến một đường mạng thực sự tới tiến trình. Ví dụ, ứng dụng bind 0.0.0.0:8081 trong container, còn registry công bố hostname inventory-service:8081 cho các consumer cùng Docker network.

## 8. Kubernetes: containerPort, Service port và NodePort

Kubernetes có nhiều lớp cổng cần phân biệt:

| Trường hoặc loại cổng | Ý nghĩa |
|---|---|
| containerPort | Khai báo cổng container dự kiến lắng nghe; không tự publish ra bên ngoài cluster |
| targetPort | Cổng đích trên Pod mà Service chuyển request tới |
| port | Cổng mà Kubernetes Service cung cấp trong cluster |
| nodePort | Cổng được mở trên các node cho Service kiểu NodePort hoặc LoadBalancer theo cấu hình |
| LoadBalancer port | Cổng frontend do hạ tầng load balancer cung cấp |

Ví dụ Deployment và Service:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: inventory-service
spec:
  replicas: 2
  selector:
    matchLabels:
      app: inventory-service
  template:
    metadata:
      labels:
        app: inventory-service
    spec:
      containers:
        - name: inventory
          image: inventory-service:latest
          ports:
            - name: http
              containerPort: 8081
~~~

~~~yaml
apiVersion: v1
kind: Service
metadata:
  name: inventory-service
spec:
  selector:
    app: inventory-service
  ports:
    - name: http
      port: 80
      targetPort: 8081
  type: ClusterIP
~~~

Trong cluster, consumer gọi:

~~~text
http://inventory-service:80
~~~

Kubernetes Service chuyển request đến một Pod phù hợp tại targetPort 8081. Pod IP có thể thay đổi khi Pod được tạo lại; Service DNS và virtual IP cung cấp điểm truy cập ổn định.

Trường containerPort trong Pod spec mang tính khai báo và hỗ trợ tài liệu hóa, named port hoặc các tích hợp khác. Nó không tự mở cổng trên node. Chính Service, NodePort, LoadBalancer hoặc Ingress/Gateway mới quyết định đường truy cập ở các phạm vi khác nhau.

### Service discovery trong Kubernetes

Nếu consumer chạy trong cluster, DNS của Kubernetes Service thường là endpoint ổn định để gọi. Nếu dùng Eureka hoặc Consul trong cluster, cần quyết định provider đăng ký Pod IP:8081, Service DNS:80 hay một địa chỉ gateway.

- Pod IP:8081 phù hợp khi consumer có thể định tuyến trực tiếp tới Pod và muốn registry theo dõi từng replica.
- Service DNS:80 phù hợp khi muốn Kubernetes Service tự phân phối tải; registry lúc đó chỉ cần một endpoint logic ổn định.
- Gateway/Ingress address phù hợp với consumer bên ngoài cluster hoặc cần chính sách truy cập tập trung.

Không nên để Eureka LoadBalancer phân phối tới Pod IP trong khi Kubernetes Service cũng đã cân bằng tải nếu không có chủ đích rõ ràng. Hai lớp load balancing có thể chồng lấn và gây khó khăn khi chẩn đoán.

## 9. HTTPS và cổng công bố

Nếu ứng dụng lắng nghe HTTPS trong container ở port 8443 và host publish 18443:8443, hai địa chỉ tương ứng là:

~~~text
Trong Docker network: https://inventory-service:8443
Từ host:              https://localhost:18443
~~~

Registry phải công bố scheme và port phù hợp với consumer. Với Eureka, có thể cấu hình secure port khi instance thực sự phục vụ HTTPS:

~~~yaml
eureka:
  instance:
    secure-port-enabled: true
    secure-port: 8443
    non-secure-port-enabled: false
~~~

Ví dụ trên phù hợp với consumer cùng network có thể gọi container port 8443. Nếu consumer ngoài network phải gọi host port 18443, cần công bố endpoint tương ứng hoặc đưa consumer qua một proxy/gateway. Chỉ bật secure-port không tự cấu hình TLS cho ứng dụng; Spring Boot phải thực sự bật SSL và có chứng thư hợp lệ.

Nếu TLS kết thúc tại ingress/load balancer, cổng backend có thể là HTTP trong khi frontend là HTTPS. Khi đó cần quyết định consumer gọi trực tiếp provider hay gọi qua frontend. Không suy ra scheme từ một port đơn lẻ; phải xét điểm TLS termination và endpoint mà registry quảng bá.

## 10. Kiểm tra đường mạng từ đúng vị trí consumer

Một endpoint truy cập được từ Docker host chưa chắc truy cập được từ container khác hoặc từ Pod. Kiểm tra phải chạy từ network namespace tương ứng với consumer.

Với Docker:

~~~bash
docker ps
docker port inventory
docker exec order-service sh
~~~

Từ shell của order-service, thử:

~~~bash
curl --connect-timeout 2 http://inventory-service:8081/actuator/health
~~~

Từ host, thử published port:

~~~bash
curl --connect-timeout 2 http://127.0.0.1:18081/actuator/health
~~~

Với Kubernetes:

~~~bash
kubectl get svc inventory-service
kubectl get endpointslices -l kubernetes.io/service-name=inventory-service
kubectl exec deploy/order-service -- \
  curl --connect-timeout 2 http://inventory-service:80/actuator/health
~~~

Sau đó kiểm tra registry:

1. Xác nhận service ID và instance ID đúng.
2. Đọc host, port và scheme đã đăng ký.
3. So sánh với địa chỉ có thể truy cập từ consumer.
4. Gọi health endpoint từ đúng network path.
5. Kiểm tra DNS, NAT mapping, firewall và TLS nếu request vẫn thất bại.

## 11. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Registry hiển thị instance nhưng request bị refused | Đăng ký host port hoặc container port sai | Đối chiếu published port, target port và địa chỉ consumer dùng |
| Truy cập được từ host nhưng container khác không truy cập được | Consumer dùng localhost hoặc host mapping không phù hợp | Gọi bằng service DNS và container port từ cùng network |
| Container khác gọi IP container thất bại | Container khác network hoặc IP đã thay đổi | Kiểm tra network attachment và dùng service DNS |
| Docker port đã publish nhưng request timeout | App bind loopback, firewall chặn hoặc app chưa listen | Kiểm tra server.address, listener và firewall |
| Eureka đăng ký IP private không thể định tuyến | Consumer ở ngoài network container | Quảng bá host/gateway address hoặc tách discovery scope |
| Port thay đổi sau mỗi lần chạy container | Dùng random published port | Cố định host port hoặc cập nhật registration từ mapping thực tế |
| Kubernetes consumer gọi sai cổng | Nhầm port với targetPort hoặc containerPort | Đọc Service spec và EndpointSlice |
| HTTPS handshake thất bại | Scheme, port, TLS termination hoặc certificate sai | Kiểm tra endpoint thực tế và trust chain |
| Health check báo lỗi nhưng API gọi từ host thành công | Agent/consumer có network path khác | Thử probe từ đúng node/namespace thực hiện health check |

## 12. Nguyên tắc thiết kế

- Phân biệt cổng ứng dụng lắng nghe, cổng container, cổng host publish, Service port và targetPort.
- Hiểu EXPOSE chỉ là metadata; cần port publishing hoặc Service để tạo đường truy cập phù hợp.
- Xác định vị trí của consumer trước khi chọn địa chỉ và port để đăng ký.
- Với consumer cùng Docker network, ưu tiên service DNS và container port.
- Với consumer ngoài host, dùng host address cùng published port hoặc gateway ổn định.
- Không quảng bá container IP riêng cho consumer không thể định tuyến tới mạng container.
- Bảo đảm ứng dụng bind trên interface phù hợp; port mapping không sửa được lỗi bind loopback.
- Tách Consul agent port khỏi service instance port.
- Trong Kubernetes, phân biệt containerPort, Service port, targetPort, NodePort và LoadBalancer port.
- Kiểm tra host/port/scheme trong registry và thử kết nối từ đúng network namespace của consumer.
- Khi NAT mapping hoặc host port thay đổi, cập nhật registration hoặc endpoint trung gian tương ứng.

Service discovery chỉ có ích khi địa chỉ được đăng ký thực sự có thể truy cập từ consumer. Cổng trong container mô tả nơi ứng dụng lắng nghe; cổng công bố tạo điểm vào từ một phạm vi mạng khác; NAT hoặc Service chuyển tiếp lưu lượng giữa chúng. Khi cấu hình Spring Cloud, hãy chọn host, port và scheme theo đường mạng thực tế của consumer, rồi xác minh bằng một request từ chính môi trường đó.
