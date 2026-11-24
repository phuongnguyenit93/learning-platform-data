# Reverse proxy, TLS termination và địa chỉ được công bố

Trong triển khai microservice, địa chỉ mà ứng dụng đang lắng nghe không nhất thiết là địa chỉ mà client nhìn thấy. Một service có thể chạy tại `10.0.2.15:8080`, nhận request từ reverse proxy, còn người dùng truy cập qua `https://api.example.com`. Nếu service đăng ký sai địa chỉ vào Eureka hoặc Consul, consumer có thể nhận endpoint không thể truy cập, tạo URL sai giao thức hoặc bỏ qua lớp proxy cần thiết.

Để cấu hình đúng, cần phân biệt ba loại địa chỉ:

- **Bind address:** địa chỉ và port mà tiến trình web server lắng nghe.
- **Advertised address:** địa chỉ và port được công bố trong service registry để consumer tìm và gọi instance.
- **Public address:** hostname, port và scheme mà client bên ngoài sử dụng qua reverse proxy, load balancer hoặc ingress.

TLS termination và forwarded headers tạo thêm một ranh giới: kết nối từ client đến proxy có thể là HTTPS, trong khi proxy gọi ứng dụng bằng HTTP nội bộ. Ứng dụng phải biết request ban đầu là HTTPS nếu cần tạo redirect, absolute URL, cookie hoặc callback chính xác.

## 1. Kiến trúc reverse proxy

Reverse proxy nhận request thay mặt cho một hoặc nhiều backend. Client chỉ biết hostname của proxy; proxy chọn backend dựa trên host, path, header, thuật toán cân bằng tải hoặc cấu hình route.

Ví dụ:

- Client truy cập `https://api.example.com/orders`.
- Reverse proxy nhận kết nối TLS tại cổng 443.
- Proxy chuyển request vào mạng nội bộ tới `order-service` tại `10.0.2.15:8080`.
- Ứng dụng xử lý request rồi trả response qua proxy.

~~~mermaid
flowchart LR
    CLIENT["Browser / API client"] -->|"HTTPS :443"| PROXY["Reverse proxy / Ingress"]
    PROXY -->|"HTTP :8080"| APP["Spring Boot application"]
    APP --> DB[("Database")]
    APP --> REG[("Eureka / Consul")]
~~~

Reverse proxy thường đảm nhiệm một số trách nhiệm:

- Công bố hostname và cổng truy cập bên ngoài.
- Kết thúc TLS và quản lý certificate phía client.
- Định tuyến theo hostname, path hoặc header.
- Cân bằng tải giữa backend.
- Giới hạn request, áp dụng access policy và ghi access log.
- Chuyển thông tin request ban đầu cho backend qua forwarded headers.

Reverse proxy không nhất thiết thay thế service discovery. Nó có thể dùng service registry để tìm backend, hoặc dùng cấu hình endpoint tĩnh, DNS, Kubernetes Service hay một cơ chế khác.

## 2. Phân biệt bind, advertised và public address

Ba địa chỉ này có thể giống nhau trong triển khai đơn giản, nhưng thường khác nhau khi chạy container, VM, Kubernetes hoặc qua proxy.

| Loại địa chỉ | Ví dụ | Ai sử dụng? | Ý nghĩa |
|---|---|---|---|
| Bind address | `0.0.0.0:8080` | Web server trong container | Lắng nghe trên các interface của container |
| Advertised address | `inventory-1.internal:8080` | Consumer trong mạng nội bộ | Endpoint instance được đăng ký trong registry |
| Public address | `https://api.example.com:443` | Browser hoặc client bên ngoài | Địa chỉ được reverse proxy công bố |

`0.0.0.0` là địa chỉ bind để lắng nghe trên mọi interface IPv4 phù hợp. Nó không phải địa chỉ để consumer kết nối và không nên được đăng ký làm advertised address.

Một hostname nội bộ có thể phân giải khác nhau theo mạng. Ví dụ `inventory-1.internal` chỉ phân giải được trong VPC hoặc cluster. Nếu consumer ở ngoài mạng đó, endpoint này không phù hợp với họ. Ngược lại, nếu mọi service nội bộ đều gọi qua `api.example.com`, hệ thống có thể tạo một điểm vào chung nhưng sẽ phụ thuộc route và chính sách proxy.

### 2.1. Registry cần công bố địa chỉ mà consumer có thể truy cập

Registry không tự biến địa chỉ private thành public và cũng không biết proxy đang route request như thế nào. Provider hoặc discovery integration phải công bố host, port và scheme phù hợp với topology.

Có hai mẫu phổ biến:

**Mẫu A — Internal direct discovery**

- Mỗi instance đăng ký hostname/IP và port nội bộ.
- Consumer trong cùng mạng truy vấn registry.
- LoadBalancer chọn instance và gọi trực tiếp.
- Reverse proxy chỉ phục vụ traffic từ bên ngoài.

**Mẫu B — Discovery qua gateway**

- Provider đăng ký endpoint nội bộ để gateway tìm backend.
- Client bên ngoài chỉ biết hostname của gateway.
- Gateway dùng discovery hoặc route configuration để chuyển request đến instance.
- Public address không được xem là endpoint riêng của từng provider instance.

~~~mermaid
flowchart TB
    subgraph INTERNAL["Mạng nội bộ"]
        R[("Service Registry")]
        O["order-service"]
        I1["inventory instance A"]
        I2["inventory instance B"]
        GW["API Gateway"]
        R --> O
        R --> GW
        O -->|"Internal service call"| I1
        GW -->|"Discovery / route"| I2
    end
    EXT["External client"] -->|"HTTPS api.example.com"| GW
~~~

Không nên đăng ký public hostname của gateway làm địa chỉ của từng instance nếu gateway không thể phân biệt và định tuyến tới đúng instance theo cách mà LoadBalancer mong đợi. Trong kiến trúc gateway, hãy để registry công bố endpoint nội bộ cho gateway; gateway mới là điểm công bố public.

## 3. TLS termination là gì?

TLS termination là việc một thành phần trung gian như Nginx, HAProxy, cloud load balancer hoặc Kubernetes ingress giải mã kết nối TLS từ client. Proxy giữ certificate public và chuyển request đến backend.

Luồng cơ bản:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant P as Reverse proxy
    participant A as Spring Boot app

    C->>P: HTTPS request (TLS)
    Note over P: TLS termination / decrypt
    P->>A: HTTP request over private network
    A-->>P: HTTP response
    P-->>C: HTTPS response (TLS)
~~~

Trong mô hình này:

- Client nhìn thấy scheme `https`.
- Proxy nhận TLS ở public port 443.
- Backend có thể chỉ lắng nghe HTTP ở port 8080.
- Proxy thường gửi `X-Forwarded-Proto: https` để thông báo scheme ban đầu.

TLS termination giảm việc quản lý certificate ở từng ứng dụng, nhưng đoạn proxy đến backend vẫn cần được bảo vệ theo mô hình đe dọa. Nếu mạng nội bộ không được tin cậy, hãy dùng TLS re-encryption hoặc mutual TLS giữa proxy và service.

### 3.1. Ba kiểu kết nối thường gặp

| Kiểu | Client → Proxy | Proxy → Backend | Đặc điểm |
|---|---|---|---|
| TLS termination | HTTPS | HTTP | Proxy giải mã TLS; backend nhận HTTP |
| TLS re-encryption | HTTPS | HTTPS | Proxy giải mã request rồi tạo kết nối TLS mới đến backend |
| TLS passthrough | TLS nguyên vẹn | TLS nguyên vẹn | Proxy định tuyến ở mức TCP/SNI mà không giải mã HTTP |

TLS passthrough thường không thể thực hiện routing theo HTTP path hoặc header vì proxy không đọc được nội dung HTTP đã mã hóa. Nó phù hợp khi cần để backend tự kết thúc TLS hoặc cần giữ nguyên TLS đến workload.

TLS re-encryption tạo hai phiên TLS độc lập. Certificate phía backend cần được proxy xác minh; không nên tắt xác minh certificate chỉ để kết nối hoạt động.

## 4. Forwarded headers truyền thông tin request gốc

Sau khi TLS termination, backend chỉ thấy kết nối HTTP từ proxy. Nếu backend tự suy luận scheme, host và port từ socket, nó có thể cho rằng request ban đầu là `http://order-service:8080`.

Proxy có thể gửi các header:

| Header | Ý nghĩa |
|---|---|
| `Forwarded` | Header chuẩn RFC 7239 mang thông tin `for`, `host`, `proto` |
| `X-Forwarded-For` | Địa chỉ IP client ban đầu hoặc chuỗi proxy |
| `X-Forwarded-Host` | Host mà client dùng để truy cập |
| `X-Forwarded-Port` | Port công khai của request |
| `X-Forwarded-Proto` | Scheme ban đầu, thường là `https` |
| `X-Forwarded-Prefix` | Prefix path bên ngoài nếu proxy loại bỏ prefix trước khi chuyển tiếp |

Ví dụ client gọi:

~~~text
https://api.example.com/orders
~~~

Proxy có thể chuyển tiếp tới backend:

~~~http
GET /orders HTTP/1.1
Host: order-service:8080
X-Forwarded-Host: api.example.com
X-Forwarded-Port: 443
X-Forwarded-Proto: https
X-Forwarded-For: 203.0.113.25
~~~

Nếu Spring Boot xử lý forwarded headers đúng, ứng dụng có thể tạo redirect, link tuyệt đối và URL trong response dựa trên địa chỉ public.

### 4.1. Cấu hình Spring Boot 3.x

Với Spring Boot 3.x, property phổ biến là `server.forward-headers-strategy`:

~~~yaml
server:
  forward-headers-strategy: framework
~~~

Các giá trị:

- `NONE`: không xử lý forwarded headers.
- `NATIVE`: dùng hỗ trợ của web server như Tomcat hoặc Jetty.
- `FRAMEWORK`: dùng `ForwardedHeaderFilter` cho Servlet hoặc `ForwardedHeaderTransformer` cho WebFlux.

Nếu web server hỗ trợ tốt các header proxy đang gửi, `NATIVE` thường là lựa chọn hiệu quả. Nếu cần xử lý qua Spring Framework, có thể dùng `FRAMEWORK`.

### 4.2. Cấu hình Spring Boot 4.2

Trong tài liệu Spring Boot 4.2, cấu hình được tổ chức dưới `server.request.header.forwarded.strategy`:

~~~yaml
server:
  request:
    header:
      forwarded:
        strategy: web-server
~~~

Các lựa chọn được mô tả trong tài liệu hiện hành gồm:

- `none`: bỏ qua forwarded headers.
- `web-server`: dùng hỗ trợ của embedded web server.
- `framework`: dùng hỗ trợ của Spring Framework.

Với header chuẩn RFC 7239, có thể cấu hình naming phù hợp:

~~~yaml
server:
  request:
    header:
      forwarded:
        naming: rfc-7239
        strategy: framework
        use-prefix: true
~~~

Property `use-prefix` chỉ cần bật khi proxy gửi `X-Forwarded-Prefix` và ứng dụng cần nhận biết path prefix ban đầu. Hãy dùng đúng tên property và giá trị theo phiên bản Spring Boot của dự án; không sao chép cấu hình 3.x sang 4.2 mà không kiểm tra.

## 5. Cấu hình reverse proxy gửi forwarded headers

Ví dụ Nginx kết thúc TLS và chuyển request HTTP vào backend:

~~~nginx
server {
    listen 443 ssl;
    server_name api.example.com;

    ssl_certificate     /etc/nginx/tls/api.crt;
    ssl_certificate_key /etc/nginx/tls/api.key;

    location / {
        proxy_pass http://order_backend;

        proxy_set_header Host $host;
        proxy_set_header Forwarded "";
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Host $host;
        proxy_set_header X-Forwarded-Port $server_port;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
~~~

Đây là ví dụ minh họa. `order_backend` cần được khai báo trong Nginx upstream hoặc cơ chế service discovery mà Nginx đang dùng. Ví dụ đặt Nginx ở rìa public nên ghi đè `X-Forwarded-For` bằng địa chỉ peer trực tiếp `$remote_addr`. Nếu có load balancer tin cậy ở phía trước, hãy cấu hình proxy nối tiếp giữ chuỗi hop theo đúng trust boundary và chỉ tin các proxy đã cấu hình.

Proxy cần xử lý forwarded headers có chủ đích:

- Loại bỏ hoặc ghi đè header forwarded do client gửi vào.
- Tạo giá trị mới dựa trên kết nối mà proxy thực sự nhận.
- Nếu có nhiều proxy nối tiếp, quy định rõ proxy nào được phép thêm và đọc từng phần của chuỗi.
- Không chuyển tiếp một `X-Forwarded-Host` tùy ý từ Internet vào ứng dụng.

Nếu proxy chỉ nối thêm `$proxy_add_x_forwarded_for`, chuỗi IP có thể chứa nhiều hop. Backend cần biết trust boundary để xác định IP client thực sự.

## 6. Tin cậy proxy và tránh giả mạo forwarded headers

Forwarded headers có thể ảnh hưởng đến redirect, URL tuyệt đối, địa chỉ client, cookie và quyết định bảo mật. Nếu backend chấp nhận các header này từ bất kỳ client nào, attacker có thể tự gửi:

~~~http
X-Forwarded-Proto: https
X-Forwarded-Host: attacker.example
X-Forwarded-For: 127.0.0.1
~~~

Ứng dụng có thể tạo link hoặc redirect đến hostname giả, ghi nhận sai IP client hoặc đánh giá sai nguồn request.

Các biện pháp cần áp dụng:

1. Chỉ cho phép backend nhận traffic từ reverse proxy hoặc network segment được kiểm soát.
2. Cấu hình proxy xóa và ghi đè các forwarded header đầu vào.
3. Chỉ bật xử lý forwarded headers khi ứng dụng nằm sau proxy tin cậy.
4. Giới hạn danh sách proxy được tin cậy theo IP/subnet.
5. Kiểm thử chuỗi nhiều proxy để xác định chính xác client IP.
6. Không dùng `X-Forwarded-For` làm cơ chế xác thực danh tính.

Với Tomcat, `RemoteIpValve` có thể dùng cấu hình `server.tomcat.remoteip.internal-proxies` để xác định các proxy nội bộ được tin cậy. Không cấu hình tin cậy mọi địa chỉ trong production.

## 7. Tomcat và redirect khi TLS kết thúc ở proxy

Một tình huống thường gặp là người dùng gọi HTTPS, proxy chuyển tiếp HTTP đến Tomcat. Khi ứng dụng tạo redirect, Tomcat có thể nhìn thấy request nội bộ là HTTP nếu forwarded headers không được xử lý trước khi redirect.

Với Spring Boot 3.x và Tomcat, tài liệu Spring Boot lưu ý cấu hình:

~~~yaml
server:
  forward-headers-strategy: native
  tomcat:
    redirect-context-root: false
~~~

Trong Spring Boot 4.2, tên property Tomcat được chuyển thành:

~~~yaml
server:
  request:
    header:
      forwarded:
        strategy: web-server
  tomcat:
    servlet:
      redirect-context-root: false
~~~

Cấu hình cụ thể phụ thuộc phiên bản và loại redirect. Hãy kiểm tra tài liệu embedded web server đúng phiên bản trước khi áp dụng. Sau cấu hình, kiểm thử các response 301/302, login redirect và URL trong response để chắc chắn chúng dùng HTTPS và hostname public.

## 8. Công bố địa chỉ với Eureka

Eureka registration chứa host, port, status URL, health URL và metadata của instance. Consumer dùng thông tin này để tạo URI gọi service.

Các thuộc tính thường gặp:

| Property | Ý nghĩa |
|---|---|
| `eureka.instance.hostname` | Hostname được công bố |
| `eureka.instance.ip-address` | IP được công bố |
| `eureka.instance.prefer-ip-address` | Ưu tiên IP thay cho hostname khi xác định host |
| `eureka.instance.non-secure-port` | Port HTTP được công bố |
| `eureka.instance.non-secure-port-enabled` | Cho phép công bố port không bảo mật |
| `eureka.instance.secure-port` | Port HTTPS được công bố |
| `eureka.instance.secure-port-enabled` | Cho phép công bố port bảo mật |
| `eureka.instance.status-page-url` | URL status page tuyệt đối |
| `eureka.instance.health-check-url` | URL health check tuyệt đối |
| `eureka.instance.home-page-url` | URL home page tuyệt đối |

### 8.1. Mẫu đăng ký endpoint nội bộ

Nếu consumer trong cluster gọi trực tiếp provider qua HTTP nội bộ:

~~~yaml
spring:
  application:
    name: inventory-service

server:
  address: 0.0.0.0
  port: 8080

eureka:
  instance:
    hostname: inventory-1.internal
    prefer-ip-address: false
    non-secure-port-enabled: true
    non-secure-port: 8080
    secure-port-enabled: false
~~~

Trong mẫu này, registry công bố hostname nội bộ và port mà consumer truy cập được. Không đăng ký `0.0.0.0` vì đó chỉ là địa chỉ bind.

Nếu chạy trên container hoặc Kubernetes, hostname/IP cần phân giải được từ mọi consumer có quyền gọi service. Có thể dùng IP pod, DNS nội bộ, hostname của VM hoặc địa chỉ service phù hợp với topology.

### 8.2. Mẫu công bố HTTPS trực tiếp

Nếu từng instance thực sự nhận HTTPS trên port 8443:

~~~yaml
eureka:
  instance:
    hostname: inventory-1.internal
    non-secure-port-enabled: false
    secure-port-enabled: true
    secure-port: 8443
    status-page-url: https://inventory-1.internal:8443/info
    health-check-url: https://inventory-1.internal:8443/health
    home-page-url: https://inventory-1.internal:8443/
~~~

Khi bật secure port và tắt non-secure port, Spring Cloud DiscoveryClient trả URI bắt đầu bằng `https` cho service này. Cần bảo đảm certificate, hostname verification và trust store phía consumer hợp lệ.

### 8.3. Khi TLS termination ở proxy

Nếu TLS chỉ kết thúc ở proxy nhưng Eureka đăng ký từng backend instance để consumer nội bộ gọi trực tiếp, hãy công bố endpoint nội bộ thực tế của backend. Không khai báo secure port 443 của proxy cho từng instance nếu proxy không route đúng từng instance theo host/port đó.

Nếu tất cả consumer đều phải đi qua proxy/gateway, hãy đăng ký gateway như một service hoặc để consumer sử dụng public route đã được cấu hình. Đừng trộn public URL của gateway vào registration nội bộ của provider mà không có route tương ứng.

Eureka cũng có các URL status, health và home page. Nếu dùng proxy để công bố các trang này, có thể đặt URL tuyệt đối phù hợp. Các URL này là metadata riêng; đừng giả định chúng luôn tự động đi theo hostname public khi proxy kết thúc TLS.

## 9. Công bố địa chỉ với Consul

Spring Cloud Consul đăng ký host, port, service ID, name và tags thông qua Consul HTTP API. Theo tài liệu Spring Cloud Consul, ứng dụng mặc định xác định hostname và IP của local instance; có thể ghi đè bằng:

- `spring.cloud.consul.discovery.hostname`
- `spring.cloud.consul.discovery.ip-address`
- `spring.cloud.consul.discovery.prefer-ip-address`

Ví dụ công bố IP nội bộ:

~~~yaml
spring:
  application:
    name: inventory-service
  cloud:
    consul:
      discovery:
        prefer-ip-address: true
        ip-address: 10.0.2.15
~~~

Nếu dùng hostname nội bộ:

~~~yaml
spring:
  cloud:
    consul:
      discovery:
        hostname: inventory-1.internal
        prefer-ip-address: false
~~~

Địa chỉ đăng ký phải truy cập được từ consumer và health check agent. Nếu Consul Agent chạy trên node khác hoặc trong mạng khác, hãy xác minh route từ agent đến endpoint health check.

### 9.1. Health check khi ứng dụng sau proxy

Spring Cloud Consul thường đăng ký HTTP health check trỏ tới `/actuator/health`. Agent sẽ gọi URL được tạo từ địa chỉ và port đăng ký cùng health check path.

Nếu application chỉ nhận request qua public proxy, nhưng Consul Agent lại không truy cập được public endpoint hoặc path health, check có thể chuyển critical dù API bên ngoài vẫn hoạt động. Ngược lại, nếu check đi qua proxy chung, nó có thể kiểm tra gateway thay vì đúng instance.

Với health check theo instance, nên bảo đảm Consul Agent truy cập được endpoint của chính instance đó trong mạng nội bộ. Nếu management server dùng port riêng, hãy cấu hình management service hoặc health check port/path tương ứng.

### 9.2. Public URL và service address là hai dữ liệu khác nhau

Consul registration address thường phục vụ định tuyến đến instance. Public URL có thể được công bố qua ingress, API Gateway, DNS hoặc metadata riêng. Không dùng một trường địa chỉ cho cả hai mục đích nếu chúng có reachability khác nhau.

Khi cần consumer bên ngoài truy cập, hãy thiết kế public route và DNS/TLS ở proxy. Khi consumer nội bộ dùng DiscoveryClient, hãy công bố service address nội bộ có thể truy cập trực tiếp.

## 10. Public route qua API Gateway hoặc Ingress

Một gateway thường là điểm vào chung cho client bên ngoài. Gateway có thể định tuyến theo path hoặc host:

| Public route | Backend |
|---|---|
| `https://api.example.com/orders/**` | `order-service` |
| `https://api.example.com/inventory/**` | `inventory-service` |
| `https://api.example.com/payments/**` | `payment-service` |

Gateway có thể dùng service discovery để tìm backend, nhưng client bên ngoài chỉ biết `api.example.com`. Registry của từng backend có thể vẫn chứa endpoint nội bộ.

Với Kubernetes Ingress, TLS thường kết thúc tại ingress controller. Service/pod phía sau có thể nhận HTTP trong cluster hoặc HTTPS nếu cấu hình re-encryption. `Ingress` và `Service` là hai lớp khác nhau: Ingress công bố host/path; Service cung cấp endpoint nội bộ cho workload.

Không nên đăng ký hostname Ingress của toàn ứng dụng vào Eureka như thể nó là hostname riêng của mỗi pod. Điều đó làm mất thông tin instance và có thể khiến LoadBalancer chọn một địa chỉ chung lặp lại cho nhiều registration.

## 11. Ví dụ end-to-end: HTTPS bên ngoài, HTTP nội bộ

Giả sử:

- Public host: `https://api.example.com`
- Nginx lắng nghe port 443.
- `order-service` chạy ở `10.0.2.15:8080`.
- `inventory-service` chạy ở `10.0.2.16:8081`.
- Consumer nội bộ gọi service qua Eureka.

Topology:

~~~mermaid
flowchart TB
    EXT["External client"]
    NGINX["Nginx / Ingress<br/>TLS termination :443"]
    ORDER["order-service<br/>10.0.2.15:8080"]
    INV["inventory-service<br/>10.0.2.16:8081"]
    EUREKA[("Eureka Server")]

    EXT -->|"HTTPS api.example.com"| NGINX
    NGINX -->|"HTTP internal"| ORDER
    ORDER -->|"DiscoveryClient + LoadBalancer"| EUREKA
    EUREKA -->|"inventory-1.internal:8081"| ORDER
    ORDER -->|"HTTP internal call"| INV
~~~

Nginx chuyển tiếp request đến order-service và thêm forwarded headers. Spring Boot xử lý các header để tạo redirect hoặc absolute URL chính xác. Trong khi đó, order-service gọi inventory-service qua địa chỉ nội bộ do Eureka công bố.

Cấu hình minh họa của `order-service`:

~~~yaml
server:
  port: 8080
  forward-headers-strategy: native

eureka:
  client:
    serviceUrl:
      defaultZone: http://eureka.internal:8761/eureka/
~~~

Cấu hình minh họa của `inventory-service`:

~~~yaml
server:
  address: 0.0.0.0
  port: 8081

eureka:
  instance:
    hostname: inventory-1.internal
    prefer-ip-address: false
    non-secure-port-enabled: true
    non-secure-port: 8081
~~~

Trong Spring Boot 4.2, thay `server.forward-headers-strategy` bằng `server.request.header.forwarded.strategy` theo cấu hình ở phần trước.

Điểm quan trọng là hai đường gọi có thể khác nhau: external client đi qua TLS proxy; internal service-to-service call đi trực tiếp đến advertised address. Nếu chính sách yêu cầu mọi traffic nội bộ cũng phải qua proxy hoặc TLS, hãy thiết kế riêng route và certificate cho đường đó.

## 12. Các lỗi phổ biến

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Consumer nhận `0.0.0.0` từ registry | Dùng bind address làm advertised address | Đặt hostname/IP có thể truy cập |
| Consumer gọi sai port | Registry công bố port container hoặc port proxy không đúng | Kiểm tra host/port thực tế và NAT mapping |
| Browser nhận redirect về `http://` | Backend không xử lý `X-Forwarded-Proto` | Cấu hình forwarded headers đúng phiên bản |
| Link response chứa hostname nội bộ | Ứng dụng dùng Host nội bộ thay cho forwarded host | Kiểm tra proxy và `X-Forwarded-Host` |
| Cookie hoặc redirect sai domain | Proxy header không được xử lý hoặc path prefix bị mất | Kiểm tra forwarded host, proto, prefix |
| Eureka DiscoveryClient trả `http` dù client muốn HTTPS | Secure port chưa được bật hoặc instance metadata sai | Kiểm tra `secure-port-enabled` và `non-secure-port-enabled` |
| Eureka công bố URL health sai | Context path, management path hoặc proxy URL không khớp | Đặt URL/path rõ ràng và kiểm tra metadata |
| Consul health check critical | Agent không truy cập được host/port/path được đăng ký | Thử gọi endpoint từ mạng của agent |
| Public proxy hoạt động nhưng service-to-service lỗi | Registry chứa public hostname không truy cập được từ mạng nội bộ | Tách internal advertised address và public route |
| Client giả mạo forwarded host/IP | Backend tin header từ nguồn không đáng tin | Proxy ghi đè header và giới hạn trusted proxy |

## 13. Checklist triển khai

Trước khi đưa reverse proxy và service discovery vào production, kiểm tra:

1. Phân biệt rõ bind address, advertised address và public address.
2. Đảm bảo advertised host/port có thể truy cập từ mọi consumer cần dùng.
3. Không đăng ký `0.0.0.0`, loopback hoặc container hostname không thể phân giải từ consumer.
4. Xác định TLS termination, re-encryption hay passthrough.
5. Nếu proxy kết thúc TLS, gửi forwarded headers chính xác.
6. Cấu hình Spring Boot xử lý forwarded headers theo đúng phiên bản.
7. Chỉ tin forwarded headers từ proxy được kiểm soát.
8. Proxy xóa hoặc ghi đè forwarded headers do client gửi vào.
9. Kiểm tra Eureka secure port hoặc Consul service address theo topology thực tế.
10. Đảm bảo health check agent truy cập đúng endpoint của từng instance.
11. Không công bố public gateway URL như địa chỉ riêng của từng backend instance.
12. Kiểm thử redirect, absolute URL, cookie, callback và health URL.
13. Kiểm tra certificate chain và hostname verification trên các đoạn TLS.
14. Ghi log cả địa chỉ client gốc và peer address để hỗ trợ troubleshooting.

## 14. Ghi nhớ

- Reverse proxy nhận request thay mặt backend; TLS termination giải mã TLS ở proxy.
- Bind address là nơi ứng dụng lắng nghe; advertised address là nơi consumer dùng để gọi instance; public address là nơi client bên ngoài truy cập.
- Forwarded headers cho backend biết scheme, host, port, IP và prefix ban đầu.
- Spring Boot 3.x dùng `server.forward-headers-strategy`; Spring Boot 4.2 dùng `server.request.header.forwarded.strategy`.
- Chỉ xử lý forwarded headers từ proxy tin cậy; proxy cần xóa/ghi đè header do client gửi.
- Eureka có `hostname`, `prefer-ip-address`, `secure-port` và các cờ bật/tắt port để công bố endpoint phù hợp.
- Consul có `hostname`, `ip-address` và `prefer-ip-address` để điều khiển địa chỉ service registration.
- Health check cần truy cập đúng instance; đi qua proxy chung có thể kiểm tra sai đối tượng.
- Public gateway route và internal service registration nên được thiết kế như hai phạm vi địa chỉ riêng.

Reverse proxy, TLS termination và service registry cùng tham gia vào đường đi của request nhưng có trách nhiệm khác nhau. Khi địa chỉ được công bố phản ánh đúng mạng mà consumer đang sử dụng, forwarded headers được tin cậy và TLS được cấu hình rõ trên từng chặng, service discovery sẽ định tuyến ổn định cả trong mạng nội bộ lẫn qua public gateway.

## Tài liệu tham khảo

- [Spring Boot 3.5 — Running Behind a Front-end Proxy Server](https://docs.spring.io/spring-boot/3.5/how-to/webserver.html)
- [Spring Boot 4.2 — Embedded Web Servers and Forwarded Headers](https://docs.spring.io/spring-boot/how-to/webserver.html)
- [Spring Cloud Netflix — Registering a Secure Application and Eureka Metadata](https://docs.spring.io/spring-cloud-netflix/reference/spring-cloud-netflix.html)
- [Spring Cloud Netflix — Configuration Properties](https://docs.spring.io/spring-cloud-netflix/reference/configprops.html)
- [Spring Cloud Consul — Configuring the Service Hostname and IP Address](https://docs.spring.io/spring-cloud-consul/reference/discovery.html)
- [RFC 7239 — Forwarded HTTP Extension](https://www.rfc-editor.org/rfc/rfc7239)
