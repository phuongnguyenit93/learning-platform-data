# Host, IP, port, URI và thuộc tính secure của một instance

## 1. Định danh dịch vụ và địa chỉ của một instance

Trong hệ thống phân tán, một dịch vụ thường có nhiều instance cùng xử lý request. Service discovery giúp consumer tìm các instance đang được đăng ký mà không cần cố định địa chỉ của từng máy trong mã nguồn. Tuy nhiên, để giao tiếp đúng, consumer phải hiểu các thông tin định danh và mạng mà mỗi instance công bố.

Một instance thường có các thông tin:

- **Service ID:** tên logic của dịch vụ, ví dụ `inventory-service`.
- **Instance ID:** mã nhận diện một lần đăng ký cụ thể, ví dụ `inventory-service:pod-7f9c`.
- **Host:** tên DNS hoặc hostname mà consumer có thể phân giải.
- **IP address:** địa chỉ IP mà consumer có thể định tuyến tới.
- **Port:** cổng mà instance nhận kết nối.
- **URI:** địa chỉ gốc được tạo từ scheme, host và port; thường là `http://host:port` hoặc `https://host:port`.
- **Secure flag:** cho biết instance được công bố để truy cập bằng giao thức bảo mật như HTTPS hay HTTP.
- **Metadata:** thông tin bổ sung như zone, version, rack hoặc nhóm triển khai.

Các trường này liên quan nhưng không thể thay thế lẫn nhau. Service ID định danh dịch vụ logic; host và port chỉ vị trí mạng hiện tại của một instance. Secure flag mô tả giao thức truy cập mà instance công bố; nó không tự cấu hình TLS, chứng thực người dùng hoặc mã hóa kết nối.

Bài thuộc chương **Định danh và mạng** của mô-đun **SPRING_CLOUD_CORE**. Mô-đun tập trung vào các nền tảng Spring Cloud Commons, Context, cấu hình bên ngoài, discovery, service registry, giao tiếp dịch vụ và khả năng kiểm thử, vận hành các abstraction chung.

Sau bài học, người học có thể:

- Phân biệt service ID, instance ID, hostname và IP address.
- Phân biệt địa chỉ bind với địa chỉ quảng bá cho consumer.
- Xác định port thực tế mà instance đăng ký vào service registry.
- Đọc và xây dựng URI từ `ServiceInstance`.
- Giải thích ý nghĩa của `isSecure()` và mối quan hệ với HTTPS.
- Nhận diện lỗi địa chỉ khi chạy trong container, Kubernetes hoặc sau reverse proxy.
- Chọn DiscoveryClient hoặc Spring Cloud LoadBalancer theo nhu cầu truy cập.

## 2. ServiceInstance trong Spring Cloud Commons

Spring Cloud Commons định nghĩa abstraction `ServiceInstance` để mô tả một instance có thể được truy cập. Các discovery provider như Eureka, Consul hoặc Kubernetes có thể có mô hình đăng ký riêng, nhưng consumer có thể làm việc với abstraction chung.

Các phương thức thường dùng:

| Phương thức | Ý nghĩa |
| --- | --- |
| `getServiceId()` | Service ID mà instance thuộc về. |
| `getInstanceId()` | ID riêng của instance; tùy provider có thể không có giá trị. |
| `getHost()` | Hostname hoặc IP mà instance công bố. |
| `getPort()` | Port mà consumer dùng để kết nối tới instance. |
| `isSecure()` | Cho biết instance được công bố là secure. |
| `getUri()` | URI gốc của instance, thường bao gồm scheme, host và port. |
| `getMetadata()` | Map metadata dạng key/value do provider hoặc ứng dụng công bố. |

Ví dụ:

```java
ServiceInstance instance = ...;

String serviceId = instance.getServiceId();
String instanceId = instance.getInstanceId();
String host = instance.getHost();
int port = instance.getPort();
boolean secure = instance.isSecure();
URI baseUri = instance.getUri();
Map<String, String> metadata = instance.getMetadata();
```

Không nên dùng địa chỉ IP làm định danh lâu dài của instance. IP có thể đổi khi container được tạo lại, pod được reschedule hoặc máy chủ thay đổi mạng. Service ID thường ổn định hơn cho consumer; instance ID dùng để phân biệt từng registration.

### 2.1. Service ID và instance ID khác nhau

Giả sử có ba instance của `inventory-service`:

| Service ID | Instance ID | Host | Port |
| --- | --- | --- | ---: |
| `inventory-service` | `inventory-01` | `inventory-01.internal` | 8080 |
| `inventory-service` | `inventory-02` | `inventory-02.internal` | 8080 |
| `inventory-service` | `inventory-03` | `10.20.4.18` | 8080 |

Consumer tìm theo service ID `inventory-service`; discovery trả về một tập instance phù hợp. Load balancer chọn instance theo thuật toán và trạng thái. Instance ID giúp nhận diện registration cụ thể trong log, metric hoặc registry.

Một service ID có thể ánh xạ tới nhiều host/port. Không gắn cứng một host vào service ID trong mã consumer, trừ khi hệ thống thực sự chỉ có một endpoint cố định và không dùng discovery.

## 3. Hostname và IP address

### 3.1. Host có thể là DNS name hoặc IP

Host là phần tên máy trong địa chỉ mạng. Ví dụ:

```text
inventory-01.internal
inventory.default.svc.cluster.local
10.20.4.18
2001:db8::18
```

DNS name thường phù hợp hơn IP tĩnh khi địa chỉ máy có thể thay đổi. DNS cho phép hạ tầng cập nhật ánh xạ tên tới địa chỉ mới mà consumer vẫn sử dụng cùng tên dịch vụ. Trong môi trường container hoặc Kubernetes, DNS service thường là điểm truy cập ổn định.

IP address hữu ích khi registry cần công bố địa chỉ trực tiếp của instance hoặc môi trường không có DNS nội bộ phù hợp. Tuy nhiên, IP phải định tuyến được từ phía consumer. Một địa chỉ chỉ có ý nghĩa bên trong network namespace của container không nhất thiết truy cập được từ container khác hoặc từ cluster khác.

### 3.2. Địa chỉ bind và địa chỉ quảng bá là hai khái niệm khác nhau

Ứng dụng có thể lắng nghe trên một địa chỉ, nhưng công bố một địa chỉ khác cho consumer.

- **Bind address:** địa chỉ interface mà server mở socket để nhận kết nối.
- **Advertised host/IP:** địa chỉ được đăng ký hoặc công bố cho consumer sử dụng.

Ví dụ, một ứng dụng trong container bind trên `0.0.0.0:8080`, nghĩa là lắng nghe trên mọi interface IPv4 của container. Consumer không thể gọi `0.0.0.0`; địa chỉ đó không phải địa chỉ đích để quảng bá. Registry cần nhận hostname hoặc IP thực sự có thể định tuyến tới container.

Trong Spring Boot, `server.address` điều khiển địa chỉ bind của web server. Thuộc tính này không tự quyết định hostname mà một discovery provider đăng ký. Địa chỉ đăng ký còn phụ thuộc provider, môi trường chạy và cấu hình instance của integration tương ứng.

### 3.3. Chọn interface mạng khi máy có nhiều card

Máy chạy ứng dụng có thể có nhiều interface: loopback, Ethernet, Wi-Fi, VPN, bridge Docker, interface Kubernetes hoặc interface quản trị. Nếu tự động chọn sai interface, registry có thể công bố IP không thể truy cập từ consumer.

Spring Cloud Commons có `InetUtils` và các thuộc tính `spring.cloud.inetutils` để điều chỉnh cách tìm hostname/IP của máy. Một số thuộc tính thường gặp:

| Thuộc tính | Mục đích |
| --- | --- |
| `spring.cloud.inetutils.ignored-interfaces` | Bỏ qua interface khớp các biểu thức cấu hình. |
| `spring.cloud.inetutils.preferred-networks` | Ưu tiên các dải mạng phù hợp. |
| `spring.cloud.inetutils.use-only-site-local-interfaces` | Chỉ xem xét interface có địa chỉ site-local theo quy tắc của Java. |
| `spring.cloud.inetutils.default-hostname` | Giá trị hostname dự phòng khi không tìm được hostname phù hợp. |
| `spring.cloud.inetutils.default-ip-address` | Giá trị IP dự phòng khi không tìm được IP phù hợp. |

Ví dụ cấu hình ưu tiên mạng nội bộ và bỏ qua interface bridge:

```yaml
spring:
  cloud:
    inetutils:
      ignored-interfaces:
        - docker0
        - veth.*
      preferred-networks:
        - 10\.20\..*
      use-only-site-local-interfaces: true
```

Các biểu thức và danh sách cần phù hợp với sơ đồ mạng thực tế. Không sao chép nguyên ví dụ này vào mọi môi trường: dải IP, tên interface và loại địa chỉ site-local của mỗi tổ chức có thể khác nhau.

Spring Cloud cũng cung cấp các thông tin client phổ biến như `spring.cloud.client.hostname` và `spring.cloud.client.ip-address`. Chúng hỗ trợ các thành phần dùng thông tin máy cục bộ; không nên mặc định rằng mọi discovery provider sẽ đăng ký đúng các giá trị này mà không có quy tắc riêng.

### 3.4. Tránh quảng bá localhost hoặc địa chỉ không thể định tuyến

Các địa chỉ sau thường gây lỗi khi dùng làm advertised host trong hệ thống nhiều máy:

- `localhost` hoặc `127.0.0.1`: chỉ trỏ về loopback của chính consumer.
- `0.0.0.0`: địa chỉ bind wildcard, không phải địa chỉ đích để client gọi.
- IP private chỉ có thể truy cập trong một network namespace khác.
- IP của interface quản trị mà consumer không có route tới.
- Hostname chỉ phân giải được trong container của chính instance.

Hãy kiểm tra từ **network của consumer**: phân giải DNS có thành công không, có route tới IP không, firewall có cho phép port không và TLS có xác thực đúng hostname không.

## 4. Port: cổng lắng nghe và cổng công bố

Port xác định ứng dụng hoặc endpoint nhận kết nối trên một host. Với Spring Boot, web server thường mặc định lắng nghe trên port `8080`, trừ khi cấu hình khác.

Các thuộc tính thường gặp:

| Thuộc tính | Vai trò |
| --- | --- |
| `server.port` | Port của web server ứng dụng. |
| `server.address` | Địa chỉ bind của web server. |
| `management.server.port` | Port riêng cho management/Actuator nếu được cấu hình tách biệt. |
| `management.server.address` | Địa chỉ bind cho management server riêng. |

`ServiceInstance.getPort()` cần phản ánh port mà consumer thực sự sử dụng để truy cập instance theo topology đã chọn. Không đăng ký management port thay cho application port trừ khi dịch vụ chủ đích cung cấp API nghiệp vụ ở port đó.

### 4.1. Port cố định và port ngẫu nhiên

Port có thể cấu hình tường minh:

```yaml
server:
  port: 8085
```

Hoặc yêu cầu hệ điều hành chọn port còn trống:

```yaml
server:
  port: 0
```

`server.port=0` hữu ích trong test hoặc khi chạy nhiều instance trên cùng máy. Sau khi server khởi động, port thực tế được gán mới có thể dùng để tạo URI hoặc đăng ký instance. Không quảng bá giá trị `0` như port kết nối.

Trong test Spring Boot, có thể lấy port thực tế được gán qua `@LocalServerPort`:

```java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class InventoryApplicationTest {

    @LocalServerPort
    int port;

    @Test
    void serverUsesAnAvailablePort() {
        assertThat(port).isPositive();
    }
}
```

### 4.2. Port trong container và Kubernetes

Port bên trong container, port publish trên host, Service port và targetPort của Kubernetes có thể khác nhau.

| Lớp mạng | Port ví dụ | Ý nghĩa |
| --- | ---: | --- |
| Ứng dụng trong container | 8080 | Spring Boot lắng nghe bên trong container. |
| Kubernetes Service port | 80 | Port consumer dùng khi gọi Kubernetes Service. |
| Kubernetes targetPort | 8080 | Port đích của container/pod. |
| NodePort hoặc load balancer port | 30080 hoặc 443 | Port công bố qua một lớp truy cập khác. |

Nếu registry trả về địa chỉ pod trực tiếp, port cần là port pod lắng nghe. Nếu consumer gọi qua Kubernetes Service, consumer thường dùng Service DNS và Service port. Không lấy port của một lớp mạng rồi ghép với host thuộc lớp khác.

Chọn một mô hình truy cập nhất quán:

- Discovery đăng ký từng pod và load balancer phía client chọn pod.
- Consumer gọi Kubernetes Service DNS và để Kubernetes Service phân phối traffic.
- Consumer gọi gateway/ingress, còn gateway định tuyến tới service.

Tránh vô tình xếp chồng nhiều tầng load balancing hoặc công bố địa chỉ pod khi consumer không thể truy cập pod network.

## 5. URI và cách dựng endpoint từ ServiceInstance

URI là địa chỉ tài nguyên có cấu trúc. Với instance HTTP, URI gốc thường gồm:

```text
scheme://host:port
```

Ví dụ:

```text
http://inventory-01.internal:8080
https://inventory.default.svc.cluster.local:443
```

Trong Spring Cloud, `ServiceInstance.getUri()` cung cấp URI gốc của instance. Consumer nên dùng URI này thay vì tự nối chuỗi host, port và scheme. Cách làm đó giúp tránh lỗi khi xử lý IPv6, scheme secure hoặc định dạng URI.

### 5.1. Ví dụ lấy URI và thêm path

```java
ServiceInstance instance = ...;

URI baseUri = instance.getUri();

URI itemsUri = UriComponentsBuilder.fromUri(baseUri)
        .pathSegment("api", "items")
        .build()
        .toUri();
```

Kết quả có dạng:

```text
https://inventory-01.internal:8443/api/items
```

`getUri()` là URI gốc của instance; context path hoặc API path của ứng dụng cần được ghép theo hợp đồng endpoint. Nếu service chạy dưới `server.servlet.context-path`, consumer phải biết base path đó hoặc lấy từ cấu hình/metadata được quản lý rõ ràng.

Không nên ghép URI bằng phép nối chuỗi:

```java
// Dễ lỗi khi host là IPv6 hoặc scheme/port thay đổi.
String url = (instance.isSecure() ? "https://" : "http://")
        + instance.getHost() + ":" + instance.getPort() + "/api/items";
```

Dùng URI builder để xử lý dấu ngoặc IPv6, encode path segment và các thành phần URI đúng quy tắc.

### 5.2. URI không phải lúc nào cũng là địa chỉ công khai

URI trong `ServiceInstance` là địa chỉ consumer dự kiến dùng theo network topology của discovery provider. Nó có thể là địa chỉ pod trong mạng cluster, DNS nội bộ của service, hostname/IP của máy ảo hoặc địa chỉ sau reverse proxy/load balancer.

URI này không tự trở thành public URL. Nếu một consumer ở ngoài cluster cần gọi dịch vụ, phải công bố endpoint có thể truy cập từ network của consumer hoặc đặt gateway phù hợp.

### 5.3. Context path và query parameter

`ServiceInstance.getUri()` thường mô tả origin của instance. Đường dẫn API, query parameter và fragment thuộc request cụ thể, không phải định danh host/port của instance.

Ví dụ:

```java
URI requestUri = UriComponentsBuilder.fromUri(instance.getUri())
        .pathSegment("api", "v1", "items")
        .queryParam("page", 0)
        .queryParam("size", 20)
        .build()
        .toUri();
```

Không lưu query chứa token hoặc dữ liệu cá nhân trong metadata của instance. Credential cần đi qua cơ chế xác thực phù hợp và được quản lý như secret.

## 6. Thuộc tính secure và HTTPS

`ServiceInstance.isSecure()` cho biết instance được công bố là secure. Trong mô hình HTTP/HTTPS thông dụng:

- `false`: URI thường dùng scheme `http`.
- `true`: URI thường dùng scheme `https`.

Đây là thông tin về giao thức mà consumer nên sử dụng khi truy cập instance. Nó không tự bật TLS trên web server, không tạo certificate và không cấu hình trust store.

### 6.1. Ba lớp cần phân biệt

| Thành phần | Trách nhiệm |
| --- | --- |
| Server TLS configuration | Cấu hình ứng dụng hoặc proxy thực sự chấp nhận kết nối HTTPS, certificate và private key. |
| ServiceInstance secure flag | Công bố cho discovery consumer biết instance được truy cập bằng giao thức secure. |
| Client TLS configuration | Xác minh certificate/hostname, trust chain và các chính sách TLS của consumer. |

Ví dụ, nếu instance lắng nghe HTTPS ở port `8443`, registration cần công bố host, port `8443` và secure flag phù hợp. Consumer sẽ tạo URI HTTPS để kết nối.

Nếu instance chỉ lắng nghe HTTP ở port `8080`, nhưng registry đánh dấu `isSecure=true`, consumer có thể thử HTTPS tới port HTTP và handshake thất bại.

Ngược lại, nếu server yêu cầu HTTPS nhưng instance được công bố là không secure, consumer có thể gọi HTTP và nhận lỗi redirect, lỗi kết nối hoặc lỗi chính sách bảo mật.

### 6.2. TLS termination tại ingress hoặc reverse proxy

Một mô hình phổ biến:

```text
Consumer -- HTTPS --> Ingress / Gateway -- HTTP --> Application Pod
```

Consumer dùng HTTPS tới ingress, nhưng ingress kết nối HTTP tới pod. Trong mô hình này, scheme và port mà consumer dùng để truy cập phụ thuộc endpoint được công bố cho consumer:

- Nếu discovery trả địa chỉ ingress, instance đó cần thể hiện HTTPS và port của ingress.
- Nếu discovery trả địa chỉ pod trực tiếp, scheme/port phải mô tả listener của pod, có thể là HTTP.

Không đánh dấu secure chỉ vì request ban đầu của người dùng tới ingress là HTTPS. Hãy xác định **hop mạng mà consumer đang kết nối**. Nếu cần mã hóa end-to-end, cấu hình TLS cả đoạn từ ingress tới pod và công bố đúng giao thức.

### 6.3. Secure flag không thay thế bảo mật ứng dụng

`isSecure=true` không chứng minh:

- Certificate còn hạn hoặc được ký bởi CA tin cậy.
- Hostname trong certificate khớp hostname URI.
- Client đã xác thực server.
- Server đã xác thực client.
- Request được phân quyền.
- Metadata hoặc payload đã được bảo vệ ở các hop khác.

TLS, authentication, authorization và network policy là các lớp riêng. Không dùng cờ secure làm điều kiện duy nhất để coi một instance là đáng tin cậy.

## 7. Metadata và thông tin instance bổ sung

`ServiceInstance.getMetadata()` trả về map key/value cho thông tin không nằm trong các trường chuẩn. Ví dụ:

```text
zone=zone-a
version=v2
weight=80
protocol=grpc
management-port=9091
```

Metadata có thể giúp load balancer hoặc consumer lựa chọn instance theo zone, phiên bản, nhóm canary hoặc năng lực. Tuy nhiên:

- Metadata là chuỗi key/value, không có schema chung cho mọi provider.
- Tên key và ý nghĩa cần được thống nhất giữa bên đăng ký và consumer.
- Không giả định metadata luôn tồn tại hoặc luôn có giá trị hợp lệ.
- Không đưa password, token, private key hoặc secret vào metadata; registry thường có nhiều thành phần được phép đọc metadata.
- Không dùng metadata thay cho host, port hoặc secure flag nếu thông tin đó đã có trường chuẩn.

Ví dụ đọc zone có fallback:

```java
String zone = instance.getMetadata().getOrDefault("zone", "unknown");
```

Nếu thuật toán phụ thuộc metadata, cần định nghĩa hành vi khi key thiếu, sai định dạng hoặc giá trị không được hỗ trợ.

## 8. Lấy instance trực tiếp hay dùng Spring Cloud LoadBalancer?

### 8.1. DiscoveryClient

`DiscoveryClient` cho phép consumer tra cứu các instance theo service ID:

```java
List<ServiceInstance> instances =
        discoveryClient.getInstances("inventory-service");

if (instances.isEmpty()) {
    throw new IllegalStateException(
            "No instance available for inventory-service");
}
```

API này phù hợp khi cần quan sát danh sách instance, xây dựng công cụ quản trị hoặc triển khai logic discovery chuyên biệt. Cần xử lý danh sách rỗng và trạng thái registry có thể thay đổi.

Không nên chọn phần tử đầu tiên trong danh sách làm chiến lược cân bằng tải production. Thứ tự trả về không phải cam kết load balancing, và consumer cần xử lý instance lỗi, retry, zone, health và thay đổi registry.

### 8.2. Spring Cloud LoadBalancer

Với request nghiệp vụ tới một service ID, Spring Cloud LoadBalancer thường là abstraction phù hợp hơn. Consumer dùng tên dịch vụ logic trong URI; LoadBalancer chọn instance rồi chuyển request tới host/port tương ứng.

Ví dụ dùng `WebClient` có load-balancer filter:

```java
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
```

Ví dụ này cần WebFlux để có `WebClient` và dependency `spring-cloud-starter-loadbalancer` để có load-balancer integration. Hãy dùng BOM Spring Cloud tương thích với phiên bản Spring Boot của ứng dụng để quản lý version.

Consumer có thể gọi service bằng service ID:

```java
webClientBuilder.build()
        .get()
        .uri("http://inventory-service/api/items")
        .retrieve()
        .bodyToMono(ItemList.class);
```

LoadBalancer chọn một `ServiceInstance` từ discovery client và dùng thông tin host, port, URI, secure cùng metadata theo cấu hình và integration đang dùng. Scheme ban đầu trong URI là một phần của request đầu vào; hành vi scheme cuối cùng còn phụ thuộc service instance và cấu hình load balancer. Kiểm thử rõ trường hợp HTTPS nếu service có secure instance.

Khi có nhiều instance, nên dùng LoadBalancer hoặc cơ chế cân bằng tải của nền tảng. Chỉ tự chọn instance trực tiếp khi ứng dụng thật sự cần kiểm soát lựa chọn và đã triển khai đầy đủ timeout, retry, health, circuit breaker và xử lý instance biến mất.

## 9. Ví dụ mô hình instance hoàn chỉnh

Giả sử một dịch vụ `payment-service` có hai instance:

| Thuộc tính | Instance A | Instance B |
| --- | --- | --- |
| Service ID | `payment-service` | `payment-service` |
| Instance ID | `payment-a` | `payment-b` |
| Host | `payment-a.internal` | `payment-b.internal` |
| Port | 8443 | 8443 |
| Secure | `true` | `true` |
| URI gốc | `https://payment-a.internal:8443` | `https://payment-b.internal:8443` |
| Metadata | `zone=zone-a`, `version=v2` | `zone=zone-b`, `version=v2` |

Consumer tra cứu `payment-service`. LoadBalancer chọn instance A hoặc B theo chính sách. Với instance A, URI request có thể được tạo thành:

```text
https://payment-a.internal:8443/api/payments
```

Nếu instance A được triển khai lại và có IP mới, registry cập nhật host hoặc IP trong registration mới. Consumer vẫn tìm theo service ID và không cần thay đổi URL cố định trong mã nguồn.

## 10. Kiểm tra địa chỉ từ góc nhìn consumer

Khi một instance đăng ký thành công nhưng consumer không gọi được, kiểm tra theo thứ tự:

1. **Service ID:** consumer có tra đúng tên dịch vụ không?
2. **Instance ID:** registry có registration đang hoạt động và không bị trùng ngoài ý muốn không?
3. **Host:** hostname có phân giải từ network của consumer không?
4. **IP và route:** IP có thuộc mạng consumer truy cập được không?
5. **Port:** port có đúng listener mà consumer cần gọi không? Firewall/network policy có cho phép không?
6. **URI/scheme:** URI có dùng đúng HTTP hoặc HTTPS không?
7. **TLS:** certificate có hợp lệ và hostname có khớp không?
8. **Path:** context path và API path có đúng không?
9. **Metadata:** nếu load balancer dùng zone/version/weight, các giá trị có đúng schema không?

Có thể kiểm tra DNS và port từ môi trường chạy consumer:

```bash
nslookup payment-a.internal
```

```bash
curl -vk https://payment-a.internal:8443/actuator/health
```

Lệnh `curl -k` bỏ qua xác minh certificate, chỉ phù hợp để khoanh vùng lỗi trong môi trường kiểm thử có kiểm soát. Khi xác minh TLS thực sự, bỏ `-k` và cung cấp CA/trust store đúng. Không dùng lệnh bỏ xác minh certificate như cấu hình production.

Trong container, chạy kiểm tra từ đúng container hoặc pod consumer. DNS và route trên máy phát triển không chứng minh rằng network namespace của ứng dụng production có thể truy cập cùng địa chỉ.

## 11. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Registry trả `localhost` | Host được suy ra từ môi trường local hoặc cấu hình advertised host sai | Công bố DNS/IP có thể truy cập từ consumer. |
| Instance có host đúng nhưng port sai | Nhầm port container, Service, NodePort hoặc management port | Xác định consumer gọi qua lớp mạng nào và đăng ký đúng port của lớp đó. |
| URI tạo thành HTTP dù server yêu cầu HTTPS | Secure flag hoặc registration scheme không đúng | Đồng bộ `isSecure`, port và TLS listener. |
| HTTPS handshake thất bại | Port đang chạy HTTP, certificate không tin cậy hoặc hostname không khớp | Kiểm tra listener, CA chain, SAN và client trust configuration. |
| IP thay đổi sau khi deploy | Dùng IP động làm cấu hình cố định | Dùng service ID/DNS và cập nhật registration qua discovery. |
| IPv6 URI sai định dạng | Tự nối chuỗi host và port | Dùng `ServiceInstance.getUri()` và URI builder. |
| Consumer không truy cập được host registry trả về | Registry công bố interface hoặc network namespace không thể định tuyến | Kiểm tra từ network consumer và cấu hình advertised address. |
| Management health hoạt động nhưng API nghiệp vụ không gọi được | Đăng ký management port thay application port hoặc path không đúng | Phân biệt management endpoint với service endpoint. |
| Nhiều instance nhưng traffic luôn tới một địa chỉ | Chọn instance đầu tiên hoặc không dùng load balancing | Dùng Spring Cloud LoadBalancer hoặc cơ chế cân bằng tải của nền tảng. |
| HTTPS ngoài ingress nhưng HTTP tới pod | Nhầm TLS termination với TLS end-to-end | Công bố đúng endpoint theo hop consumer gọi và cấu hình TLS cho từng hop cần mã hóa. |

## 12. Hướng dẫn thiết kế và vận hành

- Dùng service ID làm tên tra cứu logic; không gắn cứng IP của một instance vào consumer.
- Chọn advertised host mà consumer thực sự phân giải và định tuyến được.
- Phân biệt `server.address` (bind address) với địa chỉ được discovery provider đăng ký.
- Đăng ký port của listener mà consumer cần gọi; không dùng port `0` hoặc management port làm application port.
- Dùng `ServiceInstance.getUri()` để có scheme/host/port nhất quán; dùng URI builder để thêm path và query.
- Đặt secure flag đúng với giao thức ở hop mà consumer kết nối. Cấu hình TLS và xác minh certificate riêng.
- Chỉ đưa metadata cần thiết vào registry; không lưu secret.
- Dùng Spring Cloud LoadBalancer cho truy cập theo service ID trong các trường hợp thông thường.
- Kiểm tra địa chỉ từ network consumer, không chỉ từ máy phát triển.
- Theo dõi registration, health, DNS, port và TLS như các phần của cùng một đường kết nối.

## 13. Câu hỏi tự kiểm tra

1. Service ID khác instance ID ở điểm nào?
2. Vì sao `0.0.0.0` có thể là bind address nhưng không phải advertised host hợp lệ cho consumer?
3. `server.address` và host trong `ServiceInstance` có quan hệ gì?
4. Khi `server.port=0`, làm sao xác định port thực tế sau khi server khởi động?
5. Vì sao port của container có thể khác Service port hoặc NodePort?
6. `ServiceInstance.getUri()` giúp tránh những lỗi nào khi tạo URL?
7. `isSecure()` mô tả điều gì và không bảo đảm điều gì?
8. Nếu TLS kết thúc tại ingress nhưng pod nhận HTTP, secure flag cần phản ánh endpoint nào?
9. Khi nào nên dùng `DiscoveryClient` trực tiếp và khi nào nên dùng Spring Cloud LoadBalancer?
10. Làm sao xác minh host, port và TLS từ đúng network của consumer?

## 14. Tài liệu tham khảo chính thức

- [Spring Cloud Commons — Common Abstractions và Service Discovery](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html)
- [Spring Cloud Commons — ServiceInstance API](https://docs.spring.io/spring-cloud-commons/docs/current/api/org/springframework/cloud/client/ServiceInstance.html)
- [Spring Boot — Embedded Web Servers và Server Properties](https://docs.spring.io/spring-boot/reference/web/servlet.html)
- [Kubernetes — Services, Networking và Service DNS](https://kubernetes.io/docs/concepts/services-networking/service/)

Tên thuộc tính đăng ký host, port và secure có thể khác giữa Eureka, Consul, Kubernetes hoặc discovery provider khác. Luôn đối chiếu cấu hình của provider và phiên bản Spring Cloud đang sử dụng; `ServiceInstance` là abstraction chung, không phải một bộ property đăng ký dùng chung cho mọi registry.
