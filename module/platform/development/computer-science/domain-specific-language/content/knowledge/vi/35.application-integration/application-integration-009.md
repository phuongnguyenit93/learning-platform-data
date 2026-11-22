# Cấu hình host

Trong tích hợp ứng dụng, host là môi trường hoặc điểm kết nối mà một thành phần phần mềm sử dụng để cung cấp hay truy cập dịch vụ. Cấu hình host mô tả cách ứng dụng được đặt trong môi trường đó và cách các thành phần khác tìm thấy, kết nối, xác thực và trao đổi dữ liệu với nó.

Với một DSL tích hợp ứng dụng (*application integration DSL*), cấu hình host có thể khai báo tên dịch vụ, hostname, địa chỉ bind, port, protocol, base URL, TLS, proxy, route, authentication, timeout, health check và các thiết lập phụ thuộc môi trường. DSL biến các giá trị này thành một mô hình có cấu trúc để compiler, integration runtime hoặc deployment tool kiểm tra và sử dụng.

Ví dụ:

~~~text
host "catalog-api" {
    environment = "staging"
    endpoint {
        scheme = "https"
        hostname = "catalog.staging.example.com"
        port = 443
        basePath = "/api"
    }
    tls {
        enabled = true
        trustProfile = "internal-ca"
    }
    healthCheck {
        path = "/health/ready"
        interval = 15s
        timeout = 3s
    }
}
~~~

Đây là cú pháp minh họa. Một DSL thực tế có thể dùng cấu trúc khác, nhưng cần làm rõ host nào được cấu hình, địa chỉ nào được bind, endpoint nào được công bố và quy tắc bảo mật nào áp dụng.

## 1. Host trong tích hợp ứng dụng

Từ host có nhiều nghĩa tùy ngữ cảnh. Trong tích hợp ứng dụng, cần phân biệt ít nhất ba khái niệm:

- **Host application:** ứng dụng chủ hoặc nền tảng chứa, gọi hoặc mở rộng thành phần tích hợp.
- **Network host:** máy chủ hoặc địa chỉ mạng mà một dịch vụ chạy trên đó.
- **Hostname trong URL:** phần hostname của địa chỉ dùng để định vị một endpoint.

Ví dụ, một plugin DSL có thể chạy bên trong host application là hệ thống quản lý đơn hàng. Plugin gọi network host catalog.internal.example.com qua endpoint HTTPS có base path /api.

### 1.1. Host application

Host application là ứng dụng lớn hơn cung cấp môi trường cho module, plugin, adapter hoặc extension hoạt động. Host application có thể quản lý lifecycle, configuration, logging, security context và dependency injection.

~~~text
Host application: Order Management System
Extension:        Pricing DSL adapter
Runtime:          Integration runtime
External service: pricing.internal.example.com
~~~

Trong trường hợp này, cấu hình host application có thể xác định extension được nạp như thế nào, cấu hình nào được kế thừa, service nào được đăng ký và quyền nào được cấp.

### 1.2. Network host

Network host là máy hoặc địa chỉ mà ứng dụng có thể kết nối. Host có thể được xác định bằng DNS name, IP address hoặc service discovery name.

~~~text
catalog.internal.example.com
10.20.5.18
catalog-api.service.local
~~~

Hostname thường ổn định hơn IP vì DNS hoặc service discovery có thể ánh xạ hostname đến địa chỉ hiện tại.

### 1.3. Hostname trong URL

~~~text
https://catalog.example.com:8443/api/v2/items?limit=20
        |       |              |   |             |
        scheme  host           port path          query
~~~

Hostname xác định host đích; port xác định cổng dịch vụ; path xác định resource hoặc route. Một cấu hình host tốt không gộp tất cả thành một chuỗi khó kiểm tra nếu các thành phần cần được thay đổi độc lập.

### 1.4. Host và service

Host là nơi hoặc địa chỉ kết nối; service là chức năng mà ứng dụng cung cấp. Một host có thể cung cấp nhiều service qua các port hoặc path khác nhau. Một service cũng có thể chạy trên nhiều host instance để tăng khả năng chịu lỗi và mở rộng.

## 2. Mục tiêu của cấu hình host

Cấu hình host cần giúp hệ thống trả lời các câu hỏi:

1. Thành phần tích hợp chạy trong host application nào?
2. Dịch vụ nằm ở đâu và được định danh bằng tên nào?
3. Ứng dụng bind vào interface và port nào?
4. Client kết nối bằng protocol nào?
5. Endpoint công khai và endpoint nội bộ có khác nhau không?
6. TLS và trust policy nào được áp dụng?
7. Proxy, gateway và routing được cấu hình ra sao?
8. Client xác thực với host bằng cách nào?
9. Timeout, retry và connection pool có giới hạn nào?
10. Hệ thống xác định host khỏe mạnh bằng cách nào?
11. Giá trị nào khác nhau giữa development, staging và production?
12. Làm sao kiểm tra cấu hình trước khi chạy?

### 2.1. Cấu hình có thể tái sử dụng

~~~text
hostProfile "internal-api" {
    scheme = "https"
    port = 443
    tlsProfile = "internal-ca"
}

client "catalog-client" {
    host = hostProfile("internal-api")
    hostname = "catalog.internal.example.com"
}
~~~

Tái sử dụng giúp giảm cấu hình lặp, nhưng cần tránh làm một profile chung chứa quá nhiều ngoại lệ khiến khó hiểu giá trị hiệu lực.

### 2.2. Cấu hình tĩnh và cấu hình runtime

Một số giá trị được biết khi build hoặc deploy, như service name và default port. Những giá trị khác chỉ có khi runtime khởi động, như secret, DNS result hoặc port được cấp động.

DSL cần xác định giai đoạn resolve từng giá trị để tránh đọc secret hoặc gọi network trong lúc compile nếu không cần thiết.

## 3. Mô hình host trong DSL

Một mô hình host có thể chia thành các phần:

~~~text
HostConfiguration
├── Identity
├── ApplicationContext
├── Binding
├── AdvertisedEndpoint
├── Protocol
├── TLS
├── ProxyAndRouting
├── Authentication
├── ConnectionPolicy
├── Health
└── EnvironmentOverrides
~~~

### 3.1. Identity

Identity chứa tên logic, ID, namespace hoặc service name. Nó giúp các module tham chiếu host mà không cần lặp hostname và port ở mọi nơi.

### 3.2. Binding

Binding xác định interface và port mà server lắng nghe trên máy hoặc container.

### 3.3. Advertised endpoint

Advertised endpoint là địa chỉ client sử dụng để truy cập dịch vụ. Nó có thể khác binding address do reverse proxy, load balancer, NAT hoặc service mesh.

### 3.4. Protocol và security

Phần này quy định HTTP, HTTPS, gRPC, WebSocket hoặc protocol khác, cùng TLS, certificate và authentication.

### 3.5. Connection policy

Connection policy điều khiển timeout, retry, pool, keep-alive, circuit breaker và giới hạn tài nguyên.

### 3.6. Environment

Environment xác định profile và giá trị hiệu lực cho local, test, staging hoặc production.

## 4. Hostname và DNS

DNS ánh xạ hostname sang một hoặc nhiều địa chỉ IP. Ứng dụng thường nên kết nối bằng hostname thay vì gắn cứng một IP nếu môi trường hỗ trợ DNS ổn định.

### 4.1. Fully qualified domain name

FQDN là tên miền đầy đủ, ví dụ:

~~~text
catalog.api.example.com
~~~

Tên miền cần được quản lý trong DNS zone phù hợp. Cấu hình nên tránh phụ thuộc vào hostname chỉ tồn tại trên máy của một developer.

### 4.2. Internal và public hostname

~~~text
Public:   catalog.example.com
Internal: catalog.service.local
~~~

Public hostname được truy cập từ Internet hoặc mạng công khai theo policy. Internal hostname chỉ phân giải trong mạng riêng hoặc service discovery nội bộ.

Không nên dùng public endpoint cho luồng nội bộ nếu điều đó làm tăng bề mặt tấn công hoặc đi vòng qua network path không cần thiết.

### 4.3. DNS resolution

Khi client kết nối, DNS resolver có thể trả một hoặc nhiều IP. Kết quả có thể được cache theo TTL. Cấu hình host cần tính đến việc IP thay đổi và không nên cache vô thời hạn.

### 4.4. DNS failure

Các tình huống thường gặp:

- Hostname không tồn tại.
- DNS server không phản hồi.
- Bản ghi chưa được cập nhật.
- Client dùng resolver hoặc search domain khác dự kiến.
- Split-horizon DNS trả kết quả khác nhau giữa mạng nội bộ và bên ngoài.

Diagnostics nên phân biệt lỗi DNS với lỗi TCP connection, TLS handshake hoặc HTTP response.

### 4.5. DNS và failover

DNS có thể trả nhiều địa chỉ hoặc thay đổi record để hỗ trợ failover. Tuy nhiên, TTL, resolver cache và client connection pool có thể làm failover không tức thời.

### 4.6. Host alias

Alias giúp một tên ổn định trỏ đến dịch vụ hoặc môi trường. Cần quản lý vòng đời alias và tránh tái sử dụng alias khiến client vô tình kết nối đến hệ thống khác.

## 5. Bind address và advertised address

Server cần bind vào một địa chỉ local để lắng nghe kết nối. Client cần một địa chỉ có thể truy cập từ mạng của nó. Hai địa chỉ này có thể khác nhau.

### 5.1. Bind address

~~~text
server {
    bindAddress = "0.0.0.0"
    port = 8080
}
~~~

Địa chỉ 0.0.0.0 thường có nghĩa lắng nghe trên mọi IPv4 interface. Nó không phải địa chỉ mà client nên dùng để truy cập từ xa.

### 5.2. Loopback

~~~text
bindAddress = "127.0.0.1"
~~~

Loopback chỉ nhận kết nối từ cùng host. Đây là lựa chọn phù hợp cho service chỉ được truy cập qua local proxy hoặc sidecar, nhưng sẽ không nhận kết nối trực tiếp từ máy khác.

### 5.3. Bind vào interface cụ thể

~~~text
bindAddress = "10.20.5.18"
~~~

Bind vào một interface cụ thể giúp giới hạn phạm vi lắng nghe. Tuy nhiên, cấu hình này phụ thuộc network interface có tồn tại trong môi trường đích hay không.

### 5.4. Advertised address

~~~text
server {
    bindAddress = "0.0.0.0"
    port = 8080
    advertisedHost = "catalog.example.com"
    advertisedPort = 443
    advertisedScheme = "https"
}
~~~

Ví dụ server lắng nghe HTTP ở port 8080 phía sau reverse proxy, còn client kết nối HTTPS ở port 443. Nếu ứng dụng tạo absolute URL hoặc redirect, nó cần biết advertised endpoint.

### 5.5. IPv4 và IPv6

Một host có thể hỗ trợ IPv4, IPv6 hoặc cả hai. Cấu hình cần xác định cách parse địa chỉ, cách chọn interface và cách biểu diễn IPv6 trong URL. IPv6 literal trong URL thường được đặt trong dấu ngoặc vuông.

### 5.6. Port

Port là số nguyên trong khoảng 1 đến 65535. Port thấp có thể cần quyền đặc biệt tùy hệ điều hành. Port 0 thường yêu cầu hệ điều hành chọn port khả dụng; nếu dùng port động, runtime cần công bố port thực tế cho client hoặc service discovery.

## 6. Endpoint và URL

Endpoint là địa chỉ cùng thông tin cần thiết để gọi một dịch vụ. Trong HTTP integration, endpoint thường gồm scheme, hostname, port và base path.

~~~text
https://catalog.example.com:8443/api/v2
~~~

### 6.1. Tách endpoint thành thành phần

~~~text
endpoint "catalog" {
    scheme = "https"
    host = "catalog.example.com"
    port = 8443
    basePath = "/api/v2"
}
~~~

Tách thành phần giúp validator kiểm tra scheme, port, hostname và path riêng.

### 6.2. Default port

HTTP thường dùng port 80 và HTTPS thường dùng port 443 nếu không chỉ định port. DSL cần quy định có materialize default port hay để URL resolver xử lý.

### 6.3. Base path

Base path giúp client gọi nhiều resource trên cùng API:

~~~text
basePath = "/api/v2"
~~~

Khi ghép path, cần quy định xử lý dấu slash để tránh tạo đường dẫn lặp slash hoặc vô tình bỏ mất segment.

### 6.4. Query parameter

Query parameter thường thuộc request cụ thể, không nên gộp vào host identity nếu nó thay đổi theo thao tác. Ví dụ page=2 là tham số truy vấn, không phải một phần của host.

### 6.5. URL normalization

Có thể chuẩn hóa hostname về lowercase và xử lý default port. Path có semantics riêng, vì vậy không nên tự đổi case hoặc decode/encode tùy tiện.

### 6.6. Endpoint validation

Validator nên kiểm tra scheme có được hỗ trợ không, hostname hoặc IP có đúng format không, port nằm trong phạm vi hợp lệ, base path có cú pháp phù hợp, URL không chứa credential nhúng trực tiếp và protocol/TLS setting có tương thích không.

## 7. Protocol và transport

Host config cần xác định protocol mà client và server dùng để trao đổi dữ liệu.

### 7.1. HTTP và HTTPS

HTTP là giao thức request-response phổ biến cho web API. HTTPS là HTTP chạy trên TLS để bảo vệ dữ liệu truyền và xác minh server.

### 7.2. HTTP/1.1, HTTP/2 và HTTP/3

Các phiên bản HTTP có khác biệt về framing, multiplexing và transport. Client/server cần thống nhất phiên bản được hỗ trợ và cách thương lượng protocol.

### 7.3. gRPC

gRPC thường dùng HTTP/2 và schema message được định nghĩa bằng Protocol Buffers. Host config có thể cần authority, TLS, service name và deadline.

### 7.4. WebSocket

WebSocket cung cấp kết nối hai chiều lâu dài. Cấu hình cần quan tâm handshake, proxy upgrade, idle timeout và giới hạn connection.

### 7.5. TCP và UDP

Một integration có thể dùng protocol tầng transport trực tiếp. Khi đó cấu hình cần host, port, TLS nếu có, framing, encoding và timeout đọc/ghi.

### 7.6. Protocol compatibility

Không nên giả định chỉ cần hostname và port là đủ. Client và server phải tương thích về protocol, version, serialization và authentication scheme.

## 8. TLS và certificate

TLS bảo vệ dữ liệu truyền giữa client và server. Host config cần xác định khi nào TLS được bật và client tin cậy certificate nào.

### 8.1. TLS cho outbound connection

Khi DSL cấu hình client gọi một host:

~~~text
client "catalog-client" {
    endpoint = "https://catalog.internal.example.com"
    tls {
        verifyServerCertificate = true
        trustStore = secretRef("internal-ca-bundle")
    }
}
~~~

Client xác minh certificate chain và hostname theo trust policy.

### 8.2. TLS cho inbound server

Server có thể cần certificate và private key để phục vụ HTTPS:

~~~text
server "catalog" {
    listenPort = 8443
    tls {
        certificate = secretRef("catalog-cert")
        privateKey = secretRef("catalog-key")
    }
}
~~~

Private key phải được lấy từ secret manager hoặc secure volume. Không lưu plaintext private key trong file DSL hoặc source control.

### 8.3. Certificate chain

Certificate có thể được ký bởi intermediate CA và root CA. Client cần trust anchor phù hợp và chain đầy đủ. Thiếu intermediate certificate có thể khiến handshake thất bại dù certificate leaf còn hạn.

### 8.4. Hostname verification

Certificate cần phù hợp hostname mà client sử dụng, thường qua Subject Alternative Name. Tắt hostname verification làm suy yếu xác thực server và không nên được dùng như cách sửa lỗi cấu hình.

### 8.5. Mutual TLS

mTLS yêu cầu cả client và server trình certificate để xác thực lẫn nhau. Host config có thể cần client certificate, key reference và trust profile của server.

### 8.6. Certificate rotation

Certificate có thời hạn. Cần có quy trình rotation, overlap certificate cũ/mới, reload và cảnh báo trước expiry.

### 8.7. TLS version và cipher policy

Có thể giới hạn phiên bản TLS và cipher suite theo policy bảo mật. Không nên bật protocol cũ chỉ để tương thích một client chưa được nâng cấp mà không đánh giá rủi ro.

### 8.8. TLS termination

TLS có thể kết thúc tại application, load balancer, API gateway hoặc reverse proxy. Nếu proxy kết thúc TLS rồi gửi HTTP nội bộ, cần bảo vệ đoạn mạng nội bộ và xác định đúng forwarded scheme/host.

## 9. Reverse proxy và load balancer

Reverse proxy nhận request từ client rồi chuyển tiếp đến một hoặc nhiều backend service.

~~~text
Client
  |
  | HTTPS :443
  v
Reverse Proxy / Load Balancer
  |
  | HTTP hoặc HTTPS :8080
  v
Application Host
~~~

### 9.1. Vì sao dùng reverse proxy?

- Công bố một endpoint ổn định.
- Kết thúc TLS ở một điểm tập trung.
- Route request đến nhiều backend.
- Cân bằng tải.
- Áp dụng rate limit hoặc request filtering.
- Ẩn topology nội bộ.
- Thu thập access log và metrics.

### 9.2. Forwarded headers

Proxy có thể gửi các header như Forwarded, X-Forwarded-For, X-Forwarded-Host và X-Forwarded-Proto.

Ứng dụng chỉ nên tin forwarded headers từ proxy được tin cậy. Nếu nhận header giả từ client bất kỳ, ứng dụng có thể tạo URL sai hoặc ghi nhận IP nguồn không chính xác.

### 9.3. Trusted proxy range

Host config có thể chỉ định địa chỉ hoặc network range của proxy được phép cung cấp forwarded metadata. Danh sách này cần được cập nhật cùng hạ tầng mạng.

### 9.4. Load balancing

Load balancer có thể phân phối request theo round-robin, least connections, weighted routing hoặc consistent hashing. Health check cần loại backend không khỏe khỏi pool.

### 9.5. Sticky session

Sticky session cố định một client vào backend trong một khoảng thời gian. Nó có thể cần thiết với ứng dụng giữ session trong memory, nhưng làm giảm tính linh hoạt khi scale hoặc failover.

### 9.6. Proxy timeout

Timeout ở client, proxy và backend cần tương thích. Nếu proxy timeout ngắn hơn thời gian xử lý hợp lệ, request có thể bị cắt dù backend vẫn tiếp tục làm việc.

## 10. Virtual host và routing

Một server có thể phục vụ nhiều ứng dụng hoặc domain trên cùng IP và port. Virtual host hoặc routing rule xác định request thuộc dịch vụ nào.

### 10.1. Host-based routing

~~~text
route {
    host = "catalog.example.com"
    backend = service("catalog")
}

route {
    host = "orders.example.com"
    backend = service("orders")
}
~~~

### 10.2. Path-based routing

~~~text
route {
    pathPrefix = "/catalog/"
    backend = service("catalog")
}

route {
    pathPrefix = "/orders/"
    backend = service("orders")
}
~~~

### 10.3. Route precedence

Nếu nhiều route cùng match, DSL cần quy định thứ tự hoặc specificity. Ví dụ path prefix cụ thể hơn thường cần ưu tiên hơn prefix tổng quát.

### 10.4. Rewrite

Proxy có thể rewrite path trước khi gửi backend. Cần xác định rewrite diễn ra trước hay sau route matching và cách giữ query string.

### 10.5. Redirect

Redirect HTTP sang HTTPS hoặc đổi hostname cần tránh loop. Nếu ứng dụng ở sau proxy, nó cần nhận biết scheme bên ngoài một cách đáng tin cậy.

### 10.6. Default route

Default route có thể nhận request không khớp route nào. Trong môi trường bảo mật, default thường nên từ chối hoặc trả lỗi rõ ràng thay vì chuyển mọi request đến một backend bất kỳ.

## 11. Service discovery

Trong hệ thống động, địa chỉ instance có thể thay đổi khi scale, restart hoặc reschedule. Service discovery cho phép client tìm endpoint hiện tại theo service identity.

### 11.1. Static endpoint

~~~text
endpoint = "https://catalog.internal.example.com"
~~~

Static endpoint đơn giản và phù hợp với hệ thống ít thay đổi.

### 11.2. DNS-based discovery

Client resolve service name qua DNS. DNS có thể trả một hoặc nhiều địa chỉ.

### 11.3. Registry-based discovery

Service registry lưu instance đang hoạt động và metadata. Client hoặc proxy truy vấn registry để tìm backend.

### 11.4. Platform service name

Container orchestrator có thể cung cấp service name ổn định, ví dụ:

~~~text
http://catalog-api.namespace.svc.cluster.local
~~~

Tên cụ thể phụ thuộc nền tảng và namespace.

### 11.5. Discovery health

Không phải mọi instance đăng ký đều sẵn sàng nhận traffic. Discovery cần kết hợp readiness/health status và cơ chế loại bỏ instance stale.

### 11.6. Discovery cache

Client có thể cache kết quả để giảm truy vấn. TTL quá dài làm chậm failover; TTL quá ngắn tăng tải lên registry hoặc DNS.

## 12. Cấu hình outbound client và inbound server

Host config cần phân biệt chiều kết nối.

### 12.1. Outbound client

Outbound client chủ động kết nối đến dịch vụ khác. Cấu hình thường gồm remote endpoint, TLS trust, authentication credential, proxy, connect timeout và request timeout, retry, circuit breaker và connection pool.

Ví dụ:

~~~text
client "inventory" {
    endpoint = "https://inventory.internal.example.com"
    connectTimeout = 2s
    requestTimeout = 8s
    tlsProfile = "internal-ca"
    auth = credentialRef("inventory-client")
}
~~~

### 12.2. Inbound server

Inbound server nhận request từ thành phần khác. Cấu hình thường gồm bind address và listen port, protocol và TLS certificate, virtual host hoặc route, authentication/authorization policy, request size limit, idle timeout và graceful shutdown, health endpoint.

Ví dụ:

~~~text
server "catalog" {
    bindAddress = "0.0.0.0"
    port = 8080
    requestLimit = 10MB
    gracefulShutdown = 30s
}
~~~

### 12.3. Một ứng dụng vừa là client vừa là server

Một integration service thường vừa nhận webhook vừa gọi API bên ngoài. Nên mô hình hóa inbound listener và outbound client thành các cấu hình riêng, dù chúng có thể dùng chung host identity hoặc TLS profile.

## 13. Authentication và authorization

Kết nối được đến host không có nghĩa request được phép thực hiện. Authentication xác định danh tính; authorization xác định quyền của danh tính đó.

### 13.1. API key

API key thường được gửi qua header hoặc cơ chế riêng. Key cần được lưu trong secret manager, có scope và rotation.

### 13.2. Basic authentication

Basic authentication gửi username/password được mã hóa theo Base64, không phải mã hóa bảo mật. Chỉ sử dụng qua TLS và ưu tiên phương thức hiện đại hơn nếu có.

### 13.3. OAuth 2.0

Client có thể lấy access token từ authorization server rồi gửi đến API resource server. Host config cần phân biệt token endpoint, resource endpoint, client identity, scope và credential source.

### 13.4. JWT

JWT có thể mang claims và được ký. Resource server cần xác minh signature, issuer, audience, expiry và các claim liên quan.

### 13.5. Mutual TLS identity

mTLS có thể xác thực client ở tầng TLS. Authorization vẫn cần xác định certificate identity được phép gọi resource nào.

### 13.6. Authorization policy

Server có thể khai báo policy theo route:

~~~text
route "/admin/**" {
    requireRole("catalog-admin")
}

route "/items/**" {
    requireScope("catalog.read")
}
~~~

### 13.7. Không hardcode credential

Không đưa API key, password, token hoặc private key vào DSL source, repository, log hay artifact. DSL nên tham chiếu secret bằng logical name hoặc secret reference.

## 14. Secret và cấu hình nhạy cảm

Host configuration thường chứa dữ liệu nhạy cảm như password, client secret, certificate private key hoặc token.

### 14.1. Secret reference

~~~text
auth {
    type = "oauth2-client-credentials"
    clientId = "catalog-integration"
    clientSecret = secretRef("catalog/oauth-client-secret")
}
~~~

Secret reference chỉ xác định secret cần lấy. Runtime dùng identity được cấp quyền để đọc secret từ secret manager.

### 14.2. Tách secret khỏi config thường

Hostname, port và timeout thường không bí mật. Credential và private key cần được quản lý riêng để có thể rotation và giới hạn truy cập.

### 14.3. Secret injection

Secret có thể được đưa vào process qua file mount, environment injection hoặc secret provider API. Cần tránh để secret xuất hiện trong process listing, crash dump hoặc debug output.

### 14.4. Rotation

Khi secret thay đổi, client cần refresh credential hoặc reconnect theo quy tắc. Rotation nên tránh downtime và có thể hỗ trợ thời gian overlap giữa credential cũ và mới.

### 14.5. Redaction

Diagnostics có thể báo thiếu secret hoặc secret reference không resolve được, nhưng không được in giá trị secret.

## 15. Timeout và connection management

Host integration cần giới hạn thời gian và tài nguyên để một dịch vụ chậm không làm cạn tài nguyên của client.

### 15.1. Connect timeout

Connect timeout giới hạn thời gian thiết lập kết nối TCP hoặc transport.

### 15.2. TLS handshake timeout

TLS handshake có thể cần thời gian riêng, đặc biệt khi xác minh certificate hoặc thực hiện client authentication.

### 15.3. Request timeout

Request timeout giới hạn tổng thời gian chờ phản hồi của một request. Cần phân biệt với connect timeout.

### 15.4. Read và write timeout

Read timeout giới hạn thời gian chờ dữ liệu; write timeout giới hạn thời gian gửi dữ liệu. Với stream dài, idle timeout có thể phù hợp hơn một deadline cố định.

### 15.5. Connection pool

Connection pool tái sử dụng kết nối để giảm chi phí handshake và thiết lập transport. Cần cấu hình giới hạn tổng connection, connection mỗi host, idle timeout và thời gian sống tối đa.

### 15.6. Keep-alive

Keep-alive cho phép tái sử dụng kết nối. Client và proxy cần tương thích về idle timeout để tránh sử dụng connection đã bị peer đóng.

### 15.7. Deadline propagation

Trong hệ thống gọi lồng nhau, deadline của request nên được truyền xuống service tiếp theo. Không nên để mỗi tầng chờ timeout đầy đủ khiến tổng thời gian vượt quá giới hạn của caller.

## 16. Retry, backoff và circuit breaker

Retry giúp xử lý lỗi tạm thời, nhưng retry không đúng có thể khuếch đại sự cố.

### 16.1. Retryable failure

Các lỗi có thể retry tùy tình huống:

- Connection reset.
- Temporary DNS failure.
- HTTP 429 theo hướng dẫn retry.
- Một số HTTP 5xx.
- Service unavailable tạm thời.

Lỗi xác thực hoặc request sai thường không nên retry vô hạn.

### 16.2. Exponential backoff

~~~text
delay(n) = min(maxDelay, baseDelay * 2^n)
~~~

Jitter thêm độ ngẫu nhiên để nhiều client không retry đồng thời.

### 16.3. Retry budget

Cần giới hạn số lần thử, tổng thời gian và tổng request phụ phát sinh. Retry budget giúp tránh một request tạo ra quá nhiều tải.

### 16.4. Idempotency

Retry một GET thường ít rủi ro hơn retry một thao tác tạo đơn hàng hoặc trừ tiền. Với thao tác có side effect, cần idempotency key hoặc cơ chế deduplication.

### 16.5. Circuit breaker

~~~text
Closed
  | lỗi vượt ngưỡng
  v
Open
  | hết thời gian chờ
  v
Half-open
  | probe thành công --> Closed
  | probe thất bại ----> Open
~~~

Circuit breaker tạm ngừng gọi host đang lỗi để bảo vệ caller và backend.

### 16.6. Retry và circuit breaker phối hợp

Retry xử lý lỗi tạm thời ở một request; circuit breaker ngăn tiếp tục gọi một dependency đang không khỏe. Cần quy định thứ tự áp dụng, số lần retry và cách tính failure.

## 17. Health check và readiness

Health check giúp nền tảng biết host hoặc service có đang hoạt động và có sẵn sàng nhận traffic hay không.

### 17.1. Liveness

Liveness cho biết process còn sống và không bị treo. Nếu liveness thất bại liên tục, orchestrator có thể restart process.

### 17.2. Readiness

Readiness cho biết service đã sẵn sàng nhận request. Một service có thể sống nhưng chưa ready vì đang load config, warm cache hoặc chờ dependency.

### 17.3. Startup check

Startup check cho phép ứng dụng có thời gian khởi động dài trước khi liveness check bắt đầu áp dụng.

### 17.4. Health endpoint

~~~text
healthCheck {
    livenessPath = "/health/live"
    readinessPath = "/health/ready"
    interval = 10s
    timeout = 2s
    failureThreshold = 3
}
~~~

### 17.5. Dependency health

Readiness có thể kiểm tra database hoặc dịch vụ bắt buộc. Tuy nhiên, nếu mọi dependency chập chờn đều làm liveness thất bại, hệ thống có thể restart hàng loạt. Cần xác định dependency nào thực sự quyết định khả năng phục vụ.

### 17.6. Health check không nên tiết lộ thông tin

Endpoint health công khai không nên trả stack trace, connection string, secret hoặc chi tiết topology nội bộ. Có thể cung cấp endpoint chi tiết riêng với access control.

## 18. Cấu hình theo môi trường

Host và endpoint thường khác nhau giữa local, test, staging và production.

~~~text
environment "development" {
    catalogHost = "localhost"
    catalogPort = 8080
}

environment "staging" {
    catalogHost = "catalog.staging.example.com"
    catalogPort = 443
}

environment "production" {
    catalogHost = "catalog.example.com"
    catalogPort = 443
}
~~~

### 18.1. Base configuration

Định nghĩa các giá trị dùng chung như timeout, protocol hoặc route mặc định.

### 18.2. Environment override

Mỗi environment chỉ ghi đè các giá trị khác biệt. Cần xác định precedence giữa default, config file, environment variable, secret provider và command-line override.

### 18.3. Không hardcode production secret

Production credential phải được lấy từ secret manager hoặc identity provider. Không đưa secret vào file environment được commit.

### 18.4. Kiểm soát environment selection

Một pipeline cần biết environment đích một cách tường minh. Tránh để default vô tình chọn production hoặc để local configuration được dùng khi deploy.

### 18.5. Validate profile

Validator có thể kiểm tra profile production yêu cầu HTTPS, certificate verification, authentication, health check và timeout phù hợp.

## 19. Configuration precedence và biến môi trường

Một hệ thống thường nhận cấu hình từ nhiều nguồn:

~~~text
Built-in defaults
       <
Shared host profile
       <
Environment config
       <
Environment variables / secret provider
       <
Explicit runtime overrides
~~~

Nguồn có mức ưu tiên cao hơn có thể ghi đè nguồn trước. Thứ tự chính xác cần được công bố và kiểm thử.

### 19.1. Naming convention

Biến môi trường nên có prefix rõ:

~~~text
CATALOG_HOST=catalog.internal.example.com
CATALOG_PORT=443
CATALOG_CONNECT_TIMEOUT=2s
~~~

### 19.2. Type conversion

Environment variable thường là chuỗi. Runtime cần parse port thành integer, timeout thành duration và boolean theo cú pháp xác định. Giá trị sai phải tạo diagnostics rõ ràng.

### 19.3. Missing variable

Nếu biến bắt buộc không có, runtime nên báo tên cấu hình thiếu và nguồn được mong đợi, không in secret hay giá trị nhạy cảm.

### 19.4. Effective configuration

Một lệnh inspect có thể hiển thị cấu hình hiệu lực và nguồn của từng giá trị:

~~~bash
dsl host inspect catalog --environment staging
~~~

Output cần redacted secret và không tiết lộ credential.

## 20. Host application và extension lifecycle

Khi DSL được nhúng vào một host application, cấu hình còn liên quan đến cách extension được nạp và vận hành.

### 20.1. Registration

Host application có thể đăng ký adapter, connector hoặc DSL module:

~~~text
hostApplication "order-platform" {
    extensions {
        load("pricing-adapter")
        load("catalog-connector")
    }
}
~~~

### 20.2. Lifecycle

Extension có thể có các giai đoạn initialize, start, ready, stop và dispose. Cấu hình host cần xác định thứ tự khởi tạo và dependency giữa extension.

### 20.3. Configuration injection

Host application có thể cung cấp config context hoặc service registry cho extension. Extension cần khai báo phần cấu hình mà nó yêu cầu và default phù hợp.

### 20.4. Dependency injection

Một adapter có thể yêu cầu HTTP client, logger hoặc credential provider. Host application cung cấp các dependency này theo contract.

### 20.5. Version compatibility

Extension cần xác định host API version được hỗ trợ. Runtime nên từ chối hoặc cảnh báo khi extension yêu cầu API không tương thích.

### 20.6. Isolation

Extension không nên mặc nhiên truy cập mọi file, network hoặc credential của host application. Cần quyền tối thiểu và boundary rõ.

## 21. Cấu hình host cho nhiều tenant

Ứng dụng tích hợp nhiều tenant có thể cần host profile hoặc endpoint riêng cho từng tenant.

### 21.1. Tenant context

Tenant identity cần được lấy từ nguồn đáng tin cậy và gắn với request context. Không nên để client tự chọn tenant tùy ý nếu điều đó có thể truy cập dữ liệu tenant khác.

### 21.2. Tenant-specific endpoint

Một số SaaS cấp endpoint riêng theo tenant hoặc region. Host resolver có thể ánh xạ tenant ID sang endpoint được đăng ký.

### 21.3. Tenant-specific credentials

Credential cần được tách theo tenant và scope. Không dùng chung một token có quyền truy cập mọi tenant nếu không cần thiết.

### 21.4. Isolation

Connection pool, cache và retry state có thể cần phân tách theo tenant để tránh rò rỉ dữ liệu hoặc noisy neighbor.

### 21.5. Configuration drift

Khi host profile của tenant thay đổi, cần versioning và audit để biết request trước đó dùng cấu hình nào.

## 22. Host configuration trong container và cloud

Host trong môi trường container/cloud có thể là service name, pod, VM, load balancer hoặc managed endpoint.

### 22.1. Container port và service port

Container có thể listen ở port 8080, trong khi service được công bố ở port 80 hoặc 443. Cần phân biệt container port, service port và external port.

### 22.2. Environment variable injection

Orchestrator có thể inject host, port hoặc secret reference vào container. Cấu hình cần kiểm tra giá trị đã được inject và tránh nhúng môi trường cụ thể vào image.

### 22.3. Service mesh

Service mesh có thể quản lý mTLS, routing, retry và telemetry ở sidecar hoặc data plane. Cần xác định trách nhiệm nào thuộc ứng dụng, trách nhiệm nào thuộc mesh để tránh cấu hình chồng lặp.

### 22.4. Ingress và gateway

Ingress hoặc API gateway cung cấp entry point bên ngoài. Host config cần đồng bộ hostname, certificate, route và backend service.

### 22.5. Cloud endpoint

Managed database, queue hoặc API thường có endpoint riêng. Không nên suy ra endpoint từ tên resource nếu cloud provider có thể thay đổi format; nên dùng output hoặc service discovery chính thức.

## 23. Validation cấu hình host

Host configuration cần được validate trước khi deploy hoặc trước khi client/server khởi động.

### 23.1. Structural validation

Kiểm tra field có được phép xuất hiện, field bắt buộc và nested block đúng schema.

### 23.2. Type validation

Ví dụ:

- Port phải là integer.
- Timeout phải là duration dương.
- Enabled phải là boolean.
- Hostname phải là string hoặc host type phù hợp.

### 23.3. Constraint validation

Port nằm trong khoảng hợp lệ; timeout không âm; path có format đúng; pool size nằm trong giới hạn.

### 23.4. Cross-field validation

Ví dụ:

- HTTPS yêu cầu TLS profile hoặc certificate phù hợp.
- mTLS yêu cầu client certificate và trust configuration.
- Port 443 không tự động chứng minh TLS đã bật.
- Nếu proxy TLS termination được bật, backend protocol cần được khai báo.
- Nếu health check bật, path và interval phải hợp lệ.

### 23.5. Environment validation

Kiểm tra production không dùng localhost, không tắt certificate verification và không chứa credential literal trong source.

### 23.6. Reachability check

Reachability là kiểm tra runtime hoặc preflight: DNS resolve được, TCP kết nối được và endpoint phản hồi. Đây không phải static schema validation vì kết quả phụ thuộc network và thời điểm.

### 23.7. Validation phases

~~~text
Parse DSL
   |
   v
Validate schema and types
   |
   v
Resolve environment and secrets
   |
   v
Validate cross-field policy
   |
   v
Optional network preflight
   |
   v
Start integration
~~~

## 24. Diagnostics và cấu hình hiệu lực

Thông báo lỗi cần nêu trường nào sai, giá trị nào được nhận, giá trị nào được mong đợi và nguồn cấu hình nếu có thể.

Ví dụ:

~~~text
host/catalog/tls.verifyServerCertificate:
  production profile must not disable certificate verification

host/catalog/endpoint.port:
  expected integer between 1 and 65535; found 70000

host/catalog/auth.clientSecret:
  secret reference could not be resolved
~~~

### 24.1. Source location

Nếu giá trị sai đến từ DSL file, diagnostics nên trỏ đến dòng và cột. Nếu đến từ environment variable, hiển thị tên biến và profile tương ứng.

### 24.2. Provenance của config

Một giá trị hiệu lực có thể đến từ default, shared profile, environment file hoặc runtime override. Lưu nguồn giúp điều tra vì sao host đang dùng port hoặc timeout cụ thể.

### 24.3. Redaction

Inspect command và diagnostics không được in password, token, private key hoặc secret value.

### 24.4. Warning và error

Thiếu hostname hoặc port sai có thể là error. Dùng hostname legacy hoặc TLS certificate sắp hết hạn có thể là warning tùy policy. Severity cần nhất quán.

## 25. Observability cho host integration

Sau khi host được cấu hình, cần quan sát được chất lượng kết nối và hoạt động.

### 25.1. Logging

Log có thể ghi host identity, route, status code, latency và correlation ID. Không ghi Authorization header hoặc secret.

### 25.2. Metrics

Metrics hữu ích:

- Connection attempts và failures.
- DNS lookup latency.
- TLS handshake failures.
- Request latency.
- HTTP status code distribution.
- Active connections.
- Retry count.
- Circuit breaker state.
- Health check status.

### 25.3. Distributed tracing

Trace span có thể ghi service name, destination host, protocol và request correlation. Cần tránh đưa PII hoặc credential vào span attributes.

### 25.4. Host identity trong telemetry

Dùng logical service name ổn định thay vì IP động làm label chính. IP có thể được ghi trong trace chi tiết khi cần điều tra, nhưng metric label có cardinality cao có thể gây tốn tài nguyên.

### 25.5. Alerting

Alert có thể dựa trên tỷ lệ lỗi, latency percentile, TLS expiry, DNS failure hoặc circuit breaker open duration.

## 26. Troubleshooting host connection

Khi integration không kết nối được host, nên xác định tầng gặp lỗi thay vì thay đổi nhiều thiết lập cùng lúc.

~~~text
Configuration
    |
    v
DNS resolution
    |
    v
Network route / Firewall
    |
    v
TCP connection
    |
    v
TLS handshake
    |
    v
HTTP / Application protocol
    |
    v
Authentication
    |
    v
Authorization / Business response
~~~

### 26.1. DNS error

Kiểm tra hostname, DNS zone, resolver, search suffix và record TTL. Không sửa bằng cách hardcode IP nếu vấn đề gốc là DNS configuration chưa đúng.

### 26.2. Connection refused

Thường cho biết host có thể reachable nhưng không có process lắng nghe ở port đó, hoặc firewall chủ động reject. Kiểm tra bind address, listen port và service state.

### 26.3. Connection timeout

Có thể do route, firewall drop packet, endpoint không phản hồi hoặc network congestion. Phân biệt connect timeout với request timeout.

### 26.4. TLS handshake failure

Kiểm tra certificate chain, expiry, hostname/SAN, trust store, TLS version, client certificate và thời gian hệ thống.

### 26.5. HTTP 401 và 403

401 thường liên quan authentication thiếu hoặc không hợp lệ. 403 thường cho biết identity đã được nhận diện nhưng không có quyền. Cần kiểm tra token issuer, audience, scope, role và policy.

### 26.6. HTTP 404

Có thể do base path, route, API version hoặc reverse proxy rewrite sai.

### 26.7. HTTP 502, 503 và 504

Các mã này thường liên quan gateway hoặc backend availability. Kiểm tra upstream health, proxy route, timeout và service discovery.

### 26.8. Sai advertised host

Ứng dụng có thể tạo redirect hoặc absolute URL đến hostname nội bộ không truy cập được từ client. Kiểm tra forwarded headers và advertised endpoint.

## 27. Security considerations

Host configuration quyết định nơi ứng dụng kết nối và cổng nào được mở. Sai cấu hình có thể tạo lộ dịch vụ, kết nối nhầm host hoặc làm suy yếu xác thực.

### 27.1. Bind tối thiểu

Chỉ bind vào interface cần thiết. Không mặc định lắng nghe trên mọi interface nếu service chỉ cần local access.

### 27.2. TLS verification

Không tắt certificate verification trong production. Nếu certificate không được tin cậy, sửa trust chain hoặc certificate deployment.

### 27.3. Egress allowlist

Outbound integration có thể giới hạn host hoặc domain được phép truy cập. Điều này giảm rủi ro SSRF và kết nối đến endpoint ngoài dự kiến.

### 27.4. SSRF

Nếu hostname hoặc URL đến từ input không tin cậy, attacker có thể khiến service gọi localhost, metadata endpoint hoặc mạng nội bộ. Cần validate scheme, hostname, resolved IP, redirect và network egress.

### 27.5. DNS rebinding

Một hostname có thể phân giải sang địa chỉ khác theo thời gian. Với luồng nhạy cảm, cần kiểm tra cả kết quả DNS và địa chỉ thực tế được kết nối theo policy.

### 27.6. Credential scope

Credential chỉ nên có quyền tối thiểu trên host và API cần dùng. Không tái sử dụng một credential quản trị cho mọi integration.

### 27.7. Configuration injection

Không ghép giá trị không tin cậy vào DSL hoặc shell command. Dùng parser và API có kiểu; escape/validate theo đúng ngữ cảnh.

### 27.8. Network segmentation

Internal service nên nằm trong network segment phù hợp. Hostname nội bộ không thay thế firewall, authorization hoặc workload identity.

## 28. Host configuration lifecycle

Host configuration có vòng đời từ khai báo đến vận hành:

1. Define: mô tả host trong DSL.
2. Resolve: kết hợp profile, environment và secret reference.
3. Validate: kiểm tra schema, policy và các quan hệ.
4. Provision: tạo network resource hoặc listener nếu cần.
5. Start: khởi tạo client/server và connection pool.
6. Observe: theo dõi health, latency và error.
7. Rotate: cập nhật certificate, credential hoặc endpoint.
8. Drain: ngừng nhận request mới và hoàn tất request đang chạy.
9. Stop: đóng listener, connection và resource.

### 28.1. Graceful shutdown

Server nên ngừng nhận request mới, chờ request đang xử lý trong một khoảng thời gian, đóng connection và giải phóng resource. Timeout shutdown cần tương thích với orchestrator termination grace period.

### 28.2. Dynamic reload

Một số thiết lập có thể reload an toàn, như log level hoặc endpoint profile. Thiết lập khác cần restart, như bind address hoặc một số TLS provider. DSL/runtime cần xác định field nào hỗ trợ hot reload.

### 28.3. Atomic configuration update

Khi thay nhiều giá trị có quan hệ, nên áp dụng thành một version cấu hình nhất quán. Tránh trạng thái nửa cũ nửa mới, ví dụ certificate mới nhưng trust profile chưa được cập nhật.

### 28.4. Configuration version

Gắn version hoặc revision cho host profile giúp biết instance đang chạy cấu hình nào và hỗ trợ rollback cấu hình.

## 29. Ví dụ tổng hợp: host client và server

Một integration service vừa nhận request vừa gọi catalog API:

~~~text
application "order-integration" {
    environment = env("APP_ENV", default = "development")

    server "inbound" {
        bindAddress = "0.0.0.0"
        port = 8080
        advertisedEndpoint = "https://orders.example.com"
        tlsTermination = "gateway"

        route "/webhooks/orders" {
            handler = "orderWebhook"
            authentication = "signed-webhook"
        }

        healthCheck {
            liveness = "/health/live"
            readiness = "/health/ready"
        }
    }

    client "catalog" {
        endpoint {
            scheme = "https"
            hostname = env("CATALOG_HOST")
            port = 443
            basePath = "/api/v2"
        }

        tls {
            verifyServerCertificate = true
            trustProfile = "internal-ca"
        }

        auth {
            type = "oauth2-client-credentials"
            clientId = "order-integration"
            clientSecret = secretRef("catalog/client-secret")
            scope = ["catalog.read"]
        }

        connection {
            connectTimeout = 2s
            requestTimeout = 8s
            maxConnections = 40
            keepAlive = true
        }

        retry {
            maxAttempts = 3
            initialDelay = 200ms
            maxDelay = 2s
            retryOn = ["TIMEOUT", "HTTP_503"]
        }
    }
}
~~~

Trong ví dụ:

- Server bind port 8080 và được gateway công bố qua HTTPS.
- Webhook route dùng cơ chế authentication riêng.
- Client catalog gọi outbound endpoint qua HTTPS.
- TLS certificate verification được bật.
- OAuth client secret lấy từ secret manager.
- Timeout, connection pool và retry được khai báo rõ.
- Liveness và readiness endpoint được tách riêng.

Trước khi chạy, validator cần resolve environment, kiểm tra hostname, port, secret reference, TLS profile và các giá trị timeout. Runtime preflight có thể kiểm tra DNS và reachability nếu policy yêu cầu.

## 30. Ví dụ profile host theo môi trường

Có thể tách host profile dùng chung với environment-specific values:

~~~text
hostProfile "catalog-default" {
    scheme = "https"
    port = 443
    basePath = "/api/v2"
    connectTimeout = 2s
    requestTimeout = 8s
    verifyServerCertificate = true
}

environment "development" {
    host "catalog" extends hostProfile("catalog-default") {
        hostname = "localhost"
        port = 8443
        trustProfile = "developer-ca"
    }
}

environment "production" {
    host "catalog" extends hostProfile("catalog-default") {
        hostname = "catalog.internal.example.com"
        trustProfile = "production-ca"
        auth = credentialRef("catalog-production")
    }
}
~~~

Khi có inheritance hoặc profile composition, DSL cần quy định giá trị nào được ghi đè, collection được thay thế hay cộng dồn, field bắt buộc nào không thể bị bỏ, secret reference có được kế thừa không và cách xem cấu hình hiệu lực.

## 31. Các sai lầm thường gặp

**Nhầm bind address với advertised address.** Server có thể lắng nghe trên 0.0.0.0:8080 nhưng client phải kết nối qua domain HTTPS ở port 443.

**Dùng localhost trong cấu hình triển khai.** Localhost trong container hoặc máy chủ là chính môi trường đó, không phải máy developer hay service khác.

**Hardcode IP động.** IP có thể đổi khi service restart, scale hoặc chuyển vùng; hostname/service discovery thường phù hợp hơn.

**Gộp mọi thứ vào một URL không được validate.** Tách scheme, hostname, port và base path giúp phát hiện lỗi và quản lý override tốt hơn.

**Tắt TLS verification để sửa lỗi certificate.** Điều này che lỗi trust chain và cho phép kết nối đến host giả mạo.

**Tin forwarded headers từ mọi client.** Attacker có thể giả mạo host hoặc địa chỉ nguồn nếu ứng dụng không giới hạn trusted proxy.

**Không phân biệt connect timeout và request timeout.** Một request có thể kết nối nhanh nhưng xử lý rất lâu, hoặc ngược lại.

**Retry thao tác không idempotent.** Retry tạo đơn hàng hoặc trừ tiền có thể gây side effect lặp nếu không có idempotency key.

**Để credential trong DSL source.** Secret có thể bị commit, copy vào artifact hoặc xuất hiện trong log.

**Coi health check là business API.** Health endpoint nên đơn giản, ổn định và không để lộ thông tin nội bộ.

**Không quản lý config precedence.** Giá trị hiệu lực có thể khác dự kiến khi environment variable ghi đè profile.

**Không kiểm tra route precedence.** Hai route cùng match có thể chuyển request đến backend sai.

**Không ghi nhận cấu hình hiệu lực.** Khi sự cố xảy ra, nhóm vận hành không biết instance đang dùng profile/revision nào.

## 32. Ghi nhớ

- Host có thể chỉ host application, network host hoặc hostname trong URL; cần xác định nghĩa theo ngữ cảnh.
- Host configuration mô tả identity, binding, advertised endpoint, protocol, TLS, routing, authentication và connection policy.
- Bind address là nơi server lắng nghe; advertised address là địa chỉ client sử dụng.
- DNS và service discovery giúp tìm host động; TTL và cache ảnh hưởng failover.
- Endpoint nên được mô hình hóa bằng scheme, hostname, port và base path.
- Outbound client và inbound server có nhóm cấu hình khác nhau.
- TLS cần certificate chain, hostname verification, trust policy và quy trình rotation.
- Reverse proxy và load balancer ảnh hưởng route, forwarded headers, timeout và advertised URL.
- Authentication xác minh danh tính; authorization quyết định quyền truy cập.
- Secret cần được tham chiếu từ secret manager, không hardcode trong DSL.
- Timeout, retry, circuit breaker và connection pool cần phối hợp để giới hạn tài nguyên.
- Liveness, readiness và startup check có mục đích khác nhau.
- Environment profile và configuration precedence cần rõ ràng, có thể truy vết.
- Validation tĩnh cần tách khỏi network preflight phụ thuộc môi trường.
- Host config cần được bảo vệ trước SSRF, DNS rebinding, credential exposure và network misconfiguration.
- Cấu hình host có lifecycle: resolve, validate, start, observe, rotate, drain và stop.

## 33. Câu hỏi tự kiểm tra

1. Host có những nghĩa nào trong tích hợp ứng dụng?
2. Phân biệt host application, network host và hostname trong URL.
3. Bind address và advertised address khác nhau như thế nào?
4. Vì sao không nên mặc định dùng localhost trong cấu hình production?
5. DNS resolution, TTL và service discovery ảnh hưởng kết nối ra sao?
6. Một endpoint HTTP thường gồm những thành phần nào?
7. HTTPS khác HTTP như thế nào và TLS certificate được xác minh ra sao?
8. Mutual TLS dùng certificate của những bên nào?
9. Reverse proxy và load balancer giải quyết những vấn đề gì?
10. Vì sao chỉ nên tin forwarded headers từ proxy được tin cậy?
11. Phân biệt inbound server và outbound client configuration.
12. Authentication và authorization khác nhau như thế nào?
13. Vì sao secret nên được tham chiếu thay vì hardcode trong DSL?
14. Connect timeout, request timeout, read timeout và idle timeout khác nhau ra sao?
15. Retry, exponential backoff, idempotency và circuit breaker phối hợp như thế nào?
16. Liveness và readiness check có mục đích khác nhau nào?
17. Configuration precedence giúp giải quyết vấn đề gì khi có nhiều nguồn cấu hình?
18. Những validation nào có thể chạy tĩnh và những kiểm tra nào cần network preflight?
19. Nêu một số rủi ro bảo mật khi hostname hoặc URL đến từ input không tin cậy.
20. Hãy thiết kế cấu hình host cho một API vừa nhận webhook qua gateway vừa gọi một dịch vụ nội bộ bằng OAuth và mTLS.
