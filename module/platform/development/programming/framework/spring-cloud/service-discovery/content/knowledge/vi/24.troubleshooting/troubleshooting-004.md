# Dịch vụ xuất hiện trên Dashboard nhưng bên gọi không truy cập được

Một service xuất hiện trên Dashboard của Eureka, Consul hoặc công cụ quan sát registry chỉ chứng minh rằng registry đang lưu một bản ghi hoặc trạng thái của instance. Điều đó không bảo đảm consumer có thể mở kết nối đến địa chỉ được công bố, cũng không bảo đảm request sẽ đi qua đúng protocol, TLS, xác thực và đường mạng.

Sự cố thường nằm ở một trong các ranh giới: provider đăng ký sai địa chỉ; registry hiển thị trạng thái khỏe theo phép kiểm tra từ một network khác; consumer phân giải DNS hoặc chọn instance khác; firewall/NAT/port mapping chặn kết nối; hoặc kết nối đã đến server nhưng TLS, authentication, context path hay ứng dụng từ chối request.

Cách chẩn đoán hiệu quả là lần theo đúng đường đi của request từ consumer đang lỗi. Ghi lại địa chỉ và port mà consumer thực sự nhận từ DiscoveryClient, rồi kiểm tra DNS, route, TCP, TLS và HTTP từ chính môi trường của consumer. Không kết luận dựa trên việc Dashboard có màu xanh hoặc một lệnh curl chạy thành công trên máy quản trị.

## 1. Dashboard đang chứng minh điều gì?

Dashboard thường hiển thị dữ liệu registration, heartbeat, health check hoặc trạng thái node. Mỗi registry có ý nghĩa trạng thái khác nhau:

| Registry | Dashboard có thể cho thấy | Điều chưa được chứng minh |
|---|---|---|
| Eureka | Application/instance đã đăng ký, status, lease và heartbeat | Consumer có route đến hostname/IP và port hay không |
| Consul | Service registration, node, check status như passing/critical | Mọi consumer có truy cập được service address hay không |
| ZooKeeper | Session, znode registration và dữ liệu instance | Endpoint HTTP/TCP của ứng dụng có hoạt động hay không |
| Registry tùy chỉnh | Record và trạng thái do hệ thống tự quản lý | Ý nghĩa thực tế của status nếu không có probe từ network consumer |

Ví dụ, Eureka có thể hiển thị instance ở trạng thái UP vì client vẫn gửi heartbeat. Heartbeat chứng minh client còn gia hạn lease, không phải một consumer bất kỳ đã gọi thành công API nghiệp vụ.

Consul có thể hiển thị check passing vì Consul agent gọi được URL health nội bộ. Consumer bên ngoài Docker network vẫn có thể không truy cập được địa chỉ service mà Consul trả về.

ZooKeeper có thể còn ephemeral znode vì session client chưa hết hạn. Node tồn tại không có nghĩa process vẫn xử lý request hoặc địa chỉ trong payload còn đúng.

Vì vậy cần phân biệt ba câu hỏi:

1. **Registration:** registry có bản ghi instance hay không?
2. **Health:** phép kiểm tra mà registry thực hiện có passing hay không?
3. **Reachability:** consumer cụ thể có kết nối được đến endpoint được công bố hay không?

Ba câu hỏi này liên quan nhưng không thay thế cho nhau.

## 2. Lần theo đường đi từ provider đến consumer

Một request dùng service discovery thường đi qua các bước:

1. Provider khởi động và bind web server vào một interface/port.
2. Provider hoặc agent đăng ký serviceId, instanceId, host, port và metadata.
3. Registry lưu record và có thể cập nhật health status.
4. Consumer gọi DiscoveryClient hoặc load-balanced client để lấy instance.
5. LoadBalancer chọn một instance trong danh sách.
6. HTTP client phân giải hostname, mở TCP connection, thương lượng TLS nếu có và gửi request.
7. Provider nhận request, kiểm tra authentication/authorization, route đến controller và xử lý nghiệp vụ.

Sơ đồ:

~~~mermaid
sequenceDiagram
    participant P as Provider
    participant R as Registry
    participant C as Consumer
    participant N as DNS/Network
    participant A as Provider API

    P->>R: Register serviceId, host, port, metadata
    C->>R: Discover serviceId
    R-->>C: Return instance address
    C->>C: LoadBalancer selects instance
    C->>N: Resolve host and route to port
    N-->>C: IP / TCP connection
    C->>A: HTTP or HTTPS request
    A-->>C: HTTP response or connection error
~~~

Nếu service xuất hiện trên Dashboard nhưng request thất bại, hãy tìm bước đầu tiên không hoạt động. Ví dụ:

- DiscoveryClient không trả instance: kiểm tra serviceId, health filter và cache.
- DiscoveryClient trả instance nhưng DNS không phân giải: kiểm tra hostname được quảng bá.
- DNS đúng nhưng TCP timeout: kiểm tra route, firewall, security group và port.
- TCP thành công nhưng TLS lỗi: kiểm tra scheme, certificate, SNI và truststore.
- HTTP trả 401/403: kiểm tra credential, token, ACL hoặc mTLS identity.
- HTTP trả 404/503: kiểm tra context path, reverse proxy, gateway và upstream.

## 3. Ghi lại chính xác instance mà consumer đang chọn

Đừng chỉ nhìn tên service trên Dashboard. Cần biết consumer đang nhận và chọn instance nào.

Với DiscoveryClient, có thể log danh sách instance theo serviceId trong môi trường chẩn đoán:

~~~java
import java.util.List;

import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.stereotype.Component;

@Component
public class DiscoveryDiagnostics {

    private final DiscoveryClient discoveryClient;

    public DiscoveryDiagnostics(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    public void inspect(String serviceId) {
        List<ServiceInstance> instances =
                discoveryClient.getInstances(serviceId);

        for (ServiceInstance instance : instances) {
            System.out.printf(
                    "serviceId=%s instanceId=%s host=%s port=%d secure=%s uri=%s zone=%s%n",
                    instance.getServiceId(),
                    instance.getInstanceId(),
                    instance.getHost(),
                    instance.getPort(),
                    instance.isSecure(),
                    instance.getUri(),
                    instance.getMetadata().get("routing.zone"));
        }
    }
}
~~~

Đoạn code là công cụ chẩn đoán; chỉ log các khóa metadata nằm trong allowlist như routing.zone. Không ghi toàn bộ metadata nếu metadata có thể chứa thông tin nhạy cảm, và che endpoint nội bộ khi log được gửi ra hệ thống bên ngoài.

Đối chiếu từng trường với Dashboard hoặc API registry:

| Trường | Cần xác minh |
|---|---|
| serviceId | Có trùng chính xác với tên consumer yêu cầu không? |
| instanceId | Có phải đúng replica đang lỗi không? |
| host | Là hostname/IP nào; caller có phân giải và định tuyến được không? |
| port | Là container port, host published port hay port của proxy? |
| isSecure / scheme | Consumer dùng HTTP hay HTTPS? |
| metadata | Zone, version, canary hoặc thuộc tính lọc có làm instance bị chọn sai không? |
| health/status | Consumer có lọc instance passing/healthy không? |

Nếu có nhiều replica, log cả danh sách và instance được LoadBalancer chọn. Một request có thể thất bại chỉ ở một replica do registration cũ hoặc một node có firewall khác biệt.

Không giả định thứ tự phần tử trong danh sách DiscoveryClient là cố định. Hãy tìm theo instanceId/host/port và đối chiếu với request thực tế.

## 4. Kiểm tra địa chỉ bind và địa chỉ được quảng bá

Provider có hai loại địa chỉ cần phân biệt:

- **Bind address:** interface mà web server lắng nghe.
- **Advertised/service address:** hostname/IP và port được ghi vào registry để consumer gọi.

Bind vào 0.0.0.0 có nghĩa server lắng nghe trên mọi interface IPv4 trong network namespace hiện tại. Đây không phải địa chỉ đích hợp lệ để đăng ký cho consumer.

Bind vào 127.0.0.1 chỉ nhận kết nối trên loopback namespace của provider. Consumer ở container hoặc máy khác không thể dùng loopback của chính nó để đến provider.

| Cấu hình/địa chỉ | Ý nghĩa | Rủi ro |
|---|---|---|
| server.address=127.0.0.1 | Chỉ nghe loopback của process/container | Container khác không gọi được |
| server.address=0.0.0.0 | Nghe trên các interface IPv4 của namespace | Cần firewall giới hạn nguồn truy cập |
| Service address=127.0.0.1 | Công bố loopback cho consumer | Consumer gọi localhost của chính nó |
| Service address=0.0.0.0 | Công bố wildcard address | Không xác định được đích định tuyến |
| Container IP | Địa chỉ trong bridge network | Caller ngoài network có thể không có route |
| Host IP + published port | Địa chỉ host chuyển tiếp vào container | Cần port mapping và firewall đúng |
| Private DNS/IP | Endpoint trong mạng nội bộ | Caller phải có route và DNS phù hợp |

Ví dụ cấu hình web server trong container:

~~~yaml
server:
  address: 0.0.0.0
  port: 8080
~~~

Sau đó cần đăng ký địa chỉ mà consumer thực sự truy cập được. Nếu consumer ở cùng Docker network, có thể là DNS service name và container port. Nếu consumer ở ngoài Docker network, có thể phải công bố host IP/DNS và published port hoặc endpoint của reverse proxy.

Không thay địa chỉ registration bằng 0.0.0.0 chỉ vì ứng dụng bind ở 0.0.0.0. Hai giá trị phục vụ hai mục đích khác nhau.

## 5. Kiểm tra Docker, port mapping và network namespace

Một lỗi phổ biến là đăng ký container IP hoặc localhost nhưng consumer nằm ở network khác.

Giả sử:

- inventory-service chạy trong container và lắng nghe cổng 8080.
- Docker host publish cổng 18080 đến cổng 8080.
- order-service chạy trong một container khác cùng Docker network.
- Một consumer ngoài Docker truy cập qua private IP của host.

Các đường truy cập:

| Caller | Địa chỉ phù hợp |
|---|---|
| Container order-service cùng network | inventory-api:8080 |
| Host | localhost:18080 |
| Máy khác trong private network | 10.20.1.15:18080, nếu firewall cho phép |

Compose minh họa:

~~~yaml
services:
  inventory-api:
    image: inventory-service:1.0
    ports:
      - "18080:8080"
    networks:
      - backend

  order-api:
    image: order-service:1.0
    environment:
      INVENTORY_URL: http://inventory-api:8080
    networks:
      - backend

networks:
  backend:
    driver: bridge
~~~

Trong cùng Docker network, container gọi nhau bằng service DNS và container port. Host hoặc máy khác dùng host port đã publish. Nếu registry công bố 172.x container IP cho consumer ngoài network, record có thể hợp lệ nhưng caller không có route.

Cũng cần nhớ localhost luôn thuộc network namespace của caller. Nếu Consul agent chạy trong container riêng, check URL dùng localhost sẽ trỏ về container agent, không phải container provider.

Kiểm tra từ container consumer:

~~~bash
docker exec order-api getent hosts inventory-api
docker exec order-api curl -v --connect-timeout 3 http://inventory-api:8080/actuator/health
~~~

Kiểm tra port publish từ host:

~~~bash
curl -v --connect-timeout 3 http://127.0.0.1:18080/actuator/health
~~~

Nếu host gọi được nhưng container consumer không gọi được, hãy kiểm tra network attachment và DNS của container. Nếu container gọi được nhưng máy khác không gọi được, kiểm tra publish binding, route và firewall của host.

## 6. Kiểm tra Kubernetes Service và Pod address

Trong Kubernetes, mỗi Pod có network namespace riêng; các container trong cùng Pod chia sẻ network namespace. Pod IP thường chỉ định tuyến được trong cluster network.

Consumer trong cluster thường nên gọi Kubernetes Service DNS, ví dụ:

~~~text
http://inventory-service.default.svc.cluster.local:8080
~~~

Nếu Eureka hoặc Consul đăng ký Pod IP nhưng consumer ở ngoài cluster, caller có thể không có route đến Pod CIDR. Nếu consumer ở trong cluster, Pod IP có thể truy cập được, nhưng cần kiểm tra NetworkPolicy và CNI.

Khi dùng Kubernetes Service cùng Spring Cloud Discovery, cần quyết định lớp nào chịu trách nhiệm chọn instance:

- Kubernetes Service chọn Pod endpoint thông qua Service/EndpointSlice.
- Spring Cloud LoadBalancer chọn instance từ registry như Eureka/Consul.
- Service mesh hoặc ingress có thể thêm một tầng routing khác.

Nếu cả hai tầng cùng chọn endpoint nhưng registry trả Pod IP cũ, có thể xảy ra lệch dữ liệu. Kiểm tra EndpointSlice, Pod readiness, registry record và cache consumer.

Các lệnh chẩn đoán từ Pod consumer:

~~~bash
kubectl exec -n default deploy/order-service -- nslookup inventory-service.default.svc.cluster.local
kubectl exec -n default deploy/order-service -- curl -v --connect-timeout 3 http://inventory-service.default.svc.cluster.local:8080/actuator/health
~~~

Nếu image không có nslookup hoặc curl, dùng ephemeral debug container hoặc một pod debug trên cùng namespace/network policy. Kết quả cần lấy từ đúng network context của consumer đang lỗi.

## 7. Kiểm tra DNS, route và firewall từ phía caller

Một hostname có thể phân giải khác nhau giữa host, container, pod, VPN và máy trong private network. DNS split-horizon cũng có thể trả về địa chỉ khác theo vùng mạng.

Kiểm tra DNS trên Linux:

~~~bash
getent hosts inventory.internal
nslookup inventory.internal
~~~

Kiểm tra TCP:

~~~bash
nc -vz -w 3 inventory.internal 8081
~~~

Kiểm tra HTTP:

~~~bash
curl -v --connect-timeout 3 --max-time 8 http://inventory.internal:8081/actuator/health
~~~

Trên Windows PowerShell:

~~~powershell
Resolve-DnsName inventory.internal
Test-NetConnection -ComputerName inventory.internal -Port 8081
~~~

Khi TCP không kết nối được, xác minh:

1. Caller có route đến subnet đích không?
2. Provider có bind vào interface nhận kết nối từ subnet đó không?
3. Firewall trên host có cho phép cổng ứng dụng không?
4. Security group hoặc network ACL có cho phép nguồn caller không?
5. NAT/port mapping có chuyển đến đúng container và port không?
6. NetworkPolicy hoặc service mesh policy có chặn traffic không?
7. DNS có trỏ đến endpoint cũ hoặc interface không thể truy cập không?

Không chỉ kiểm tra firewall inbound của provider. Một số môi trường có egress policy ở consumer, network ACL hai chiều hoặc firewall trung gian. Cần biết gói SYN có đến provider hay không và phản hồi có quay lại caller hay không.

## 8. Kiểm tra HTTP, HTTPS, TLS và authentication

TCP connect thành công chỉ chứng minh socket có thể mở. Nó không chứng minh request nghiệp vụ được chấp nhận.

| Kết quả | Nguyên nhân có thể | Kiểm tra |
|---|---|---|
| TLS handshake failure | Protocol/cipher không tương thích, TLS termination sai | TLS version, cipher và cấu hình proxy |
| Certificate path/PKIX error | Consumer không tin CA hoặc thiếu intermediate certificate | Truststore và certificate chain |
| Hostname verification failed | Certificate SAN không khớp hostname registry công bố | DNS/SAN/SNI và advertised hostname |
| 401 Unauthorized | Thiếu hoặc sai credential/token | Authentication filter và token |
| 403 Forbidden | Đã xác thực nhưng không đủ quyền | Role, scope, ACL và policy |
| 404 Not Found | Sai context path hoặc route | server.servlet.context-path, gateway path và controller mapping |
| 405 Method Not Allowed | Gọi sai HTTP method | Method của endpoint |
| 503 Service Unavailable | Proxy/load balancer không có upstream khỏe | Upstream pool và health filter |
| 502 Bad Gateway | Gateway không nhận được phản hồi hợp lệ từ upstream | Proxy log, kết nối upstream và protocol |
| 200 health nhưng API lỗi | Health endpoint kiểm tra phạm vi hẹp hơn nghiệp vụ | Dependency, auth và endpoint thực tế |

Kiểm tra HTTPS bằng hostname thật để TLS SNI và hostname verification hoạt động đúng:

~~~bash
curl -v --connect-timeout 3 https://inventory.internal:8443/actuator/health
~~~

Không tắt xác minh certificate trong production để che lỗi. Nếu cần cô lập lỗi trong lab, chỉ thực hiện kiểm tra có kiểm soát và khôi phục xác minh TLS ngay sau đó.

Nếu gateway kết thúc TLS và chuyển tiếp HTTP đến provider, registry có thể cần công bố gateway HTTPS cho consumer thay vì địa chỉ HTTP nội bộ. Khi đó health check nội bộ và service address có thể khác nhau, nhưng cả hai phải được cấu hình theo đúng network và trust boundary.

## 9. Phân biệt health check URL với service address trong Consul

Consul có hai địa chỉ thường bị nhầm:

- Service address và port là endpoint consumer nhận từ catalog.
- Check URL là endpoint mà Consul agent chủ động gọi để kiểm tra service.

Ví dụ:

~~~json
{
  "service": {
    "name": "inventory-service",
    "id": "inventory-node-a",
    "address": "10.20.1.15",
    "port": 18080,
    "checks": [
      {
        "http": "http://inventory-api:8080/actuator/health",
        "interval": "10s",
        "timeout": "2s"
      }
    ]
  }
}
~~~

Agent có thể gọi inventory-api:8080 trong Docker network và check passing. Consumer bên ngoài lại nhận 10.20.1.15:18080. Nếu port 18080 không được publish hoặc firewall chặn, Dashboard vẫn có thể hiển thị passing trong khi consumer không kết nối được.

Kiểm tra cả hai đường từ đúng nơi:

- Từ network của Consul agent, gọi check URL.
- Từ network của consumer, gọi service address và port trong catalog.

Nếu consumer chỉ lấy instance passing, hãy kiểm tra query có filter passing đúng không. Nếu consumer lấy catalog không lọc health, instance critical vẫn có thể được trả về tùy API và client.

## 10. Những điểm riêng cần kiểm tra trong Eureka

Eureka Dashboard cho biết instance đã đăng ký và heartbeat/lease. Khi Dashboard hiển thị UP nhưng consumer không gọi được, kiểm tra:

1. Instance hostname/IP mà Eureka lưu có truy cập được từ consumer không.
2. Port được đăng ký có đúng là port ứng dụng hoặc proxy công bố không.
3. Nếu dùng prefer-ip-address, IP đó có route từ consumer không.
4. Nếu dùng hostname, DNS từ consumer có phân giải đúng không.
5. Nếu có nhiều network, Eureka có đang công bố địa chỉ của network khác không.
6. Consumer có dùng đúng application name/serviceId không.
7. Registry fetch và cache LoadBalancer có đang giữ instance cũ không.
8. Instance có bị filter bởi zone, metadata hoặc health policy không.

Ví dụ cấu hình minh họa cho provider trong một network chung:

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
    instance-id: inventory-node-a
~~~

prefer-ip-address chỉ chọn IP thay cho hostname trong thông tin instance; nó không bảo đảm IP được chọn có thể truy cập từ mọi consumer. Nếu consumer ở network khác, hãy công bố hostname/IP có route hoặc dùng gateway/load balancer chung.

instance-id trong ví dụ là ID cố định cho một instance minh họa. Khi chạy nhiều replica, mỗi replica cần instance ID riêng; không sao chép nguyên giá trị này cho mọi provider.

Eureka status UP cũng không phải HTTP health check từ từng consumer. Có thể cấu hình health check integration theo phiên bản Spring Cloud Netflix, nhưng vẫn cần kiểm tra endpoint quảng bá và đường mạng consumer.

## 11. Những điểm riêng cần kiểm tra trong ZooKeeper

ZooKeeper thường lưu service registration dưới znode, có thể là ephemeral node gắn với session. Nếu znode xuất hiện trên dashboard hoặc công cụ quản trị, điều đó chỉ chứng minh record tồn tại trong cây dữ liệu.

Kiểm tra:

- Path đăng ký có đúng service name và instance ID không.
- Payload znode chứa host/port nào.
- Địa chỉ đó có thể truy cập từ consumer không.
- Session của provider còn hiệu lực hay record đã cũ.
- Consumer đã nhận watcher event hoặc resync sau reconnect chưa.
- Consumer cache có giữ instance cũ không.
- ACL có cho phép consumer đọc path cần thiết không.
- Payload có bị lỗi schema hoặc dữ liệu metadata cũ không.

ZooKeeper không tự kiểm tra HTTP endpoint chỉ vì znode tồn tại. Nếu muốn trạng thái sức khỏe nghiệp vụ, cần health check riêng hoặc cơ chế loại instance khỏi danh sách mà consumer sử dụng.

Sau session LOST, ephemeral node cũ sẽ bị xóa. Khi client reconnect và tạo node mới, consumer cần cập nhật danh sách instance. Nếu consumer giữ cache hoặc watcher chưa được đăng ký lại, dashboard và dữ liệu consumer có thể khác nhau trong một khoảng thời gian.

## 12. Kiểm tra consumer có thật sự dùng Spring Cloud LoadBalancer

Một ứng dụng có thể truy vấn được DiscoveryClient nhưng HTTP client không được cấu hình để dùng serviceId như hostname logic.

Ví dụ, khi dùng load-balanced WebClient.Builder:

~~~java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class HttpClientConfiguration {

    @Bean
    @LoadBalanced
    WebClient.Builder loadBalancedWebClientBuilder() {
        return WebClient.builder();
    }
}
~~~

Consumer có thể inject builder đã được đánh dấu LoadBalanced vào client riêng:

~~~java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

@Component
public class InventoryClient {

    private final WebClient webClient;

    public InventoryClient(@LoadBalanced WebClient.Builder builder) {
        this.webClient = builder.build();
    }

    public Mono<String> getItems() {
        return webClient.get()
                .uri("http://inventory-service/api/items")
                .retrieve()
                .bodyToMono(String.class);
    }
}
~~~

Đây là ví dụ cho WebFlux và Spring Cloud LoadBalancer tương thích với phiên bản ứng dụng; dự án cần dependency LoadBalancer và discovery integration tương ứng. Nếu dùng WebClient.Builder không có @LoadBalanced, hostname inventory-service có thể bị gửi thẳng đến DNS thông thường thay vì được chuyển qua service discovery.

Với RestTemplate, RestClient hoặc HTTP client khác, cần dùng integration/load-balancing adapter đúng với phiên bản Spring Cloud. Không giả định chỉ cần viết serviceId trong URL là mọi HTTP client tự động hiểu.

Kiểm tra log LoadBalancer để biết:
- serviceId được yêu cầu;
- số instance nhận được;
- instance được chọn;
- host/port cuối cùng;
- lỗi xảy ra trước hay sau khi mở kết nối.

Nếu DiscoveryClient trả danh sách rỗng, kiểm tra registry, serviceId và filter. Nếu trả instance đúng nhưng LoadBalancer không chọn được, kiểm tra supplier, health filter, zone preference, retry và cấu hình bean.

## 13. Kiểm tra cache và dữ liệu registry cũ

Dashboard và consumer có thể nhìn thấy dữ liệu ở thời điểm khác nhau. Consumer có thể giữ cache instance list trong khi provider đã đổi IP hoặc port.

Các nguyên nhân:

- Registry fetch interval dài.
- LoadBalancer cache chưa hết TTL.
- DNS cache giữ IP cũ.
- Consumer chưa xử lý watcher event.
- Provider restart nhưng instance ID/hostname cũ vẫn còn.
- Health status thay đổi nhưng consumer không lọc trạng thái.
- Có nhiều registry hoặc nhiều cluster và consumer đang truy vấn nhầm nguồn.

Cần đối chiếu timestamp:
- thời điểm provider đăng ký;
- thời điểm instance address thay đổi;
- thời điểm registry nhận update;
- thời điểm consumer refresh;
- thời điểm request cuối cùng đến endpoint cũ.

Không xóa cache một cách mù quáng khi chưa biết nguồn dữ liệu sai. Nếu registry đang trả địa chỉ sai, refresh liên tục chỉ làm consumer nhận lại cùng dữ liệu. Sửa registration hoặc advertised address trước, sau đó xác nhận consumer nhận bản ghi mới.

## 14. Bảng chẩn đoán theo triệu chứng

| Triệu chứng | Lớp nghi ngờ đầu tiên | Kiểm tra tiếp theo |
|---|---|---|
| Dashboard có instance, DiscoveryClient trả danh sách rỗng | ServiceId/filter/cache | Tên service, health filter, registry endpoint và client cache |
| DiscoveryClient trả host 127.0.0.1 | Registration address | Advertised host và network namespace của provider |
| Host gọi được, container consumer không gọi được | Docker network/DNS | Network attachment, service DNS và port nội bộ |
| Container gọi được, máy qua VPN không gọi được | Private routing/firewall | VPN route, split DNS, security group |
| DNS không phân giải | DNS | Search domain, DNS zone và hostname đã đăng ký |
| TCP connection refused | Listener/port | Bind address, port, NAT và firewall reject |
| TCP timeout | Route/filter/drop | Firewall, NetworkPolicy, security group, NAT |
| TLS handshake lỗi | TLS/protocol | Scheme, truststore, certificate chain, SAN, SNI |
| HTTP 401/403 | Authentication/authorization | Token, role, ACL, mTLS identity |
| HTTP 404 | Path/routing | Context path, gateway rewrite, controller mapping |
| HTTP 502/503 | Proxy/upstream | Target pool, health filter, proxy logs |
| Chỉ một replica lỗi | Instance-specific config | InstanceId, host, port, zone, metadata và firewall |
| Dashboard passing nhưng API nghiệp vụ lỗi | Health scope | Health endpoint, dependency và readiness |
| Sau reconnect vẫn gọi IP cũ | Cache/propagation | Registry update, fetch interval, DNS TTL và watcher |

## 15. Quy trình runbook từ consumer đang lỗi

Thực hiện theo thứ tự sau và lưu kết quả ở từng bước:

1. **Ghi request thực tế:** serviceId, path, scheme, method, thời điểm, lỗi và correlation ID.
2. **Đọc instance list:** gọi DiscoveryClient.getInstances(serviceId), ghi host/port/instanceId đã che thông tin nhạy cảm.
3. **Xác định instance được chọn:** bật log LoadBalancer hoặc trace để biết request dùng endpoint nào.
4. **Kiểm tra DNS từ caller:** hostname có phân giải đúng IP mong đợi không?
5. **Kiểm tra TCP từ caller:** cổng có mở và route có hoạt động không?
6. **Kiểm tra HTTP/TLS:** endpoint health và endpoint nghiệp vụ có phản hồi đúng không?
7. **Đối chiếu provider:** server có bind đúng interface/port và log có nhận request không?
8. **Đối chiếu registry:** service address, check URL, health status và timestamp có nhất quán không?
9. **Kiểm tra security:** firewall, ACL, token, certificate và network policy.
10. **Kiểm tra cache:** sau khi sửa registration, consumer đã nhận address mới chưa?
11. **Kiểm tra tất cả replica:** không chỉ một instance đang được Dashboard chọn làm ví dụ.
12. **Xác nhận phục hồi:** gửi request từ consumer thật và quan sát log provider nhận đúng request.

Ghi nhận kết quả bằng bảng:

| Bước | Kết quả | Bằng chứng |
|---|---|---|
| DiscoveryClient trả instance | PASS/FAIL | serviceId, instanceId, host, port |
| DNS resolve | PASS/FAIL | hostname và IP trả về |
| TCP connect | PASS/FAIL | port và thời gian kết nối |
| TLS handshake | PASS/FAIL/N/A | certificate/SAN/protocol |
| HTTP health | PASS/FAIL | status code và latency |
| API nghiệp vụ | PASS/FAIL | status code, correlation ID |
| Provider log nhận request | YES/NO | timestamp và trace |
| Cache cập nhật | PASS/FAIL | thời điểm refresh và endpoint mới |

## 16. Những việc không nên làm khi xử lý sự cố

- Không kết luận service khỏe chỉ vì Dashboard hiển thị UP hoặc passing.
- Không đăng ký localhost hoặc 0.0.0.0 làm địa chỉ cho consumer ở network khác.
- Không thay đổi port hoặc IP nhiều nơi cùng lúc mà không ghi lại giá trị registry đang trả.
- Không mở firewall toàn bộ subnet hoặc expose registry API ra Internet chỉ để thử nhanh.
- Không tắt TLS verification hoặc authentication trong production để làm request thành công.
- Không xóa hàng loạt registration khi chưa xác định instance nào stale.
- Không retry vô hạn khi lỗi là DNS/configuration/authorization.
- Không thêm một lớp cache mới trước khi kiểm tra cache sẵn có của discovery client và LoadBalancer.
- Không chỉ kiểm tra từ host quản trị; phải kiểm tra từ đúng container/pod/máy consumer.
- Không coi health check URL nội bộ là bằng chứng service address công bố cho consumer truy cập được.

## 17. Checklist phòng ngừa

Trước khi triển khai service mới, xác nhận:

1. Provider bind trên interface nhận traffic từ network dự kiến.
2. Registry công bố hostname/IP và port mà consumer có route đến.
3. Không dùng localhost hoặc 0.0.0.0 làm destination address.
4. Docker port mapping, Kubernetes Service hoặc gateway được cấu hình đúng.
5. DNS từ mọi nhóm consumer phân giải đúng endpoint.
6. Firewall, security group và NetworkPolicy cho phép luồng cần thiết.
7. HTTP/HTTPS, TLS certificate, SNI và authentication thống nhất.
8. Health check được thử từ network của agent thực hiện check.
9. Consumer request được thử từ network namespace thực tế.
10. DiscoveryClient và LoadBalancer dùng đúng serviceId và filter.
11. Cache/refresh có giới hạn stale và được cập nhật sau registration change.
12. Log/metric có instanceId, endpoint, lỗi kết nối và latency để truy vết.
13. Mỗi replica được kiểm tra, tránh chỉ xác nhận một instance.
14. Có runbook cho DNS, TCP, TLS, HTTP và registry state.

Điểm cần nhớ là: **Dashboard chứng minh registry có dữ liệu; consumer chỉ truy cập được khi địa chỉ instance mà nó nhận có thể phân giải, định tuyến và chấp nhận kết nối từ network của chính consumer.** Hãy lấy endpoint từ DiscoveryClient, kiểm tra từng lớp từ caller đến provider và đối chiếu với registration/health check để tìm đúng ranh giới đang lỗi.

