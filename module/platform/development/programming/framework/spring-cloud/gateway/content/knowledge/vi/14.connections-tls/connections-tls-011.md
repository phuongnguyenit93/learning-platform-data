# Cấu hình proxy đầu ra khi môi trường triển khai yêu cầu

## 1. Bối cảnh: Gateway không phải lúc nào cũng được phép gọi trực tiếp Internet

Trong hệ thống microservices, **Spring Cloud Gateway** nhận HTTP request từ client, khớp route predicate, chạy filter chain rồi gọi API ở backend. Thông thường, với route như `https://partner-api.example.test`, Gateway sử dụng Reactor Netty `HttpClient` để thiết lập kết nối trực tiếp đến host đích.

Tuy nhiên, nhiều môi trường doanh nghiệp hoặc Kubernetes production áp dụng chính sách **egress**:

- Pod hoặc máy chạy Gateway **không được kết nối trực tiếp** đến Internet.
- Mọi kết nối HTTP(S) ra ngoài phải đi qua một **forward proxy** do tổ chức quản lý để áp dụng allowlist, kiểm toán và kiểm soát mạng.
- API nội bộ (ví dụ `orders.default.svc.cluster.local`) nên đi **trực tiếp qua mạng nội bộ**, không vòng qua proxy Internet.
- Proxy có thể yêu cầu username/password, hạn chế cổng `CONNECT`, hoặc cho phép truy cập một số hostname nhất định.

Một Gateway có thể làm việc đúng ở máy lập trình viên nhưng liên tục lỗi khi deploy, vì máy local đi Internet trực tiếp còn cluster bắt buộc có **proxy đầu ra**.

Mục tiêu của bài thuộc chương **Kết nối và TLS** trong module **SPRING_CLOUD_GATEWAY** là cấu hình **proxy mà Gateway dùng để gọi upstream**, hiểu hành vi HTTP `CONNECT`, tránh gửi traffic nội bộ qua proxy, quản lý thông tin xác thực, kiểm thử HTTP/HTTPS và chẩn đoán lỗi network/TLS.

> **Phạm vi:** tập trung vào **Spring Cloud Gateway Server WebFlux** sử dụng Reactor Netty `HttpClient` để định tuyến HTTP(S). Những thuộc tính ở các phiên bản Gateway 5.x thường có tiền tố `spring.cloud.gateway.server.webflux`; các dự án WebFlux 4.x có thể dùng `spring.cloud.gateway`. Chọn đúng starter, release train và namespace của dự án; không sao chép cấu hình của **Gateway Server MVC** sang WebFlux.

## 2. Phân biệt ba khái niệm đều mang tên “proxy”

Từ “proxy” xuất hiện ở nhiều vị trí trong một hệ thống nên cần phân biệt rõ:

| Loại | Vị trí | Trách nhiệm | Ví dụ |
| --- | --- | --- | --- |
| **Reverse proxy / API Gateway** | Nằm trước microservices, tiếp nhận request của client | Chọn route, filter, định tuyến tới backend | Spring Cloud Gateway |
| **Ingress / load balancer đầu vào** | Nằm trước Gateway | Chấm dứt TLS, cân bằng tải Gateway, kiểm soát truy cập | Ingress Controller, cloud LB |
| **Forward proxy đầu ra (egress proxy)** | Nằm trên đường Gateway kết nối ra upstream | Kiểm soát, chuyển tiếp hoặc tạo tunnel ra mạng đích | HTTP proxy của doanh nghiệp |
| **Service mesh egress gateway** | Có thể là hop do sidecar/mesh quản lý | Áp dụng chính sách egress cấp mesh | Egress gateway do nền tảng vận hành |

Bài này xử lý **hàng thứ ba**: cấu hình Gateway kết nối **qua một forward proxy khi nó đóng vai trò HTTP client**. Tính năng đó khác hoàn toàn với `X-Forwarded-For`, `Forwarded`, `PreserveHostHeader`, `SetRequestHeader` hay route `forward:`.

Sơ đồ đường đi khi proxy đầu ra được bật:

```mermaid
flowchart LR
    C["Client"] -->|"HTTPS public"| G["Spring Cloud Gateway\nServer WebFlux"]
    G --> P{"Host đích có được bypass?"}
    P -->|"Không"| E["Forward proxy\nproxy.corp.internal:3128"]
    E -->|"CONNECT / tunnel"| O["API đối tác\npartner-api.example.test:443"]
    P -->|"Có"| I["Service nội bộ\norders.default.svc.cluster.local:8081"]
    O --> G
    I --> G
    G --> C
```

Proxy đầu ra chỉ nằm trên **chặng Gateway → upstream**. Việc client kết nối Gateway bằng HTTPS không tự thiết lập proxy đầu ra; và dùng egress proxy cũng không tự cấu hình HTTPS từ client đến Gateway.

## 3. Gateway dùng HTTP client nào để định tuyến?

Trong **Gateway Server WebFlux**, khi route URI đã được giải quyết thành `http://...` hoặc `https://...`, **Netty Routing Filter** dùng Reactor Netty `HttpClient` để gửi request ra backend. Nếu route bắt đầu bằng `lb://SERVICE-ID`, LoadBalancer thường chọn một `ServiceInstance` rồi biến URL logic thành URL HTTP(S) trước khi HTTP client gửi đi.

Luồng khái quát:

```mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant G as Spring Cloud Gateway
    participant L as Route / LoadBalancer
    participant P as Forward proxy
    participant U as Upstream
    C->>G: GET /partners/orders/42
    G->>L: Chọn route và resolve target URI
    L-->>G: https://partner-api.example.test/orders/42
    G->>P: Kết nối proxy + HTTP CONNECT
    P->>U: Thiết lập đường đến host đích
    G->>U: TLS + HTTP request qua tunnel
    U-->>G: HTTP response qua tunnel
    G-->>C: Status, headers, body
```

Với route bypass proxy, Gateway đi trực tiếp đến upstream, không qua `P`. Sơ đồ là kiến trúc logic; không có nghĩa proxy bắt buộc biết nội dung HTTPS được bảo vệ bên trong tunnel.

**Phạm vi tác động:** các property `httpclient.proxy.*` được dùng cho Reactor Netty HTTP client **do Gateway cấu hình cho Netty routing**. Đừng suy ra mọi cuộc gọi outbound của ứng dụng đều đi qua nó:

- Một `WebClient` do developer tự tạo có thể sử dụng `HttpClient` khác.
- Eureka/Consul client, OAuth2 token client, SDK object storage hoặc database driver có thể dùng client riêng.
- Route `forward:///local-handler` dispatch tới handler trong cùng tiến trình, không nhất thiết tạo kết nối HTTP ra ngoài.
- `RedirectTo` trả HTTP 3xx để **client** truy cập URL mới; nó không dùng egress proxy của Gateway để đi theo redirect.
- Định tuyến WebSocket, TCP hoặc plugin tùy biến có thể có hành vi khác cần đối chiếu đúng phiên bản.

Nếu tổ chức yêu cầu **toàn bộ egress** phải đi qua một điểm kiểm soát, phải kết hợp cấu hình của từng HTTP client với network policy/service mesh/firewall, không chỉ một nhóm thuộc tính của Spring Cloud Gateway.

## 4. Những thuộc tính proxy quan trọng

Các thuộc tính dưới đây thuộc nhóm `httpclient.proxy` của **Gateway Server WebFlux**. Tên đầy đủ phụ thuộc namespace ở phiên bản:

| Khóa tương đối | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `host` | Hostname/IP của proxy đầu ra | `proxy.corp.internal` |
| `port` | Cổng mà Gateway dùng để kết nối đến proxy | `3128` |
| `type` | Loại proxy Reactor Netty hỗ trợ | `http`, `socks4`, `socks5` |
| `username` | Tên tài khoản proxy khi cần authentication | Lấy từ secret/deployment |
| `password` | Mật khẩu proxy tương ứng | Lấy từ secret/deployment |
| `non-proxy-hosts-pattern` | **Java regex** khớp hostname cần truy cập trực tiếp | `localhost\|.*\\.internal\\.example` |

Các khóa `host`, `port`, `username`, `password` là **thông tin của proxy**, không phải thông tin đăng nhập microservice. `Authorization: Bearer ...` dùng để xác thực với API đích khác với thông tin **Proxy-Authorization** dùng trong việc thiết lập tunnel với proxy.

Trong ví dụ chính, ta chọn proxy loại `http`, phổ biến ở mạng doanh nghiệp. Nếu môi trường thực sự cung cấp SOCKS4/SOCKS5, hãy chọn `type` phù hợp và xác minh cơ chế DNS/auth được hạ tầng hỗ trợ. Không giả định mọi kiểu xác thực proxy phức tạp đều được cấu hình chỉ bằng username/password.

### 4.1. Không dùng URI đầy đủ làm proxy.host

Ví dụ **sai**:

```yaml
proxy:
  host: http://proxy.corp.internal:3128
  port: 3128
```

`host` nên chỉ chứa **hostname hoặc địa chỉ IP**, còn `port` là số riêng và `type` chỉ loại proxy:

```yaml
proxy:
  type: http
  host: proxy.corp.internal
  port: 3128
```

Không đặt username/password vào host hoặc URL proxy theo kiểu `http://user:password@...`; chuỗi như vậy dễ bị log, nhầm trong parsing và không đúng ý nghĩa của trường `host`.

## 5. Cấu hình Gateway WebFlux 5.x: HTTP proxy cho upstream bên ngoài

Giả sử hai route:

- `GET /partners/**` đến API đối tác `https://partner-api.example.test`, **bắt buộc đi qua egress proxy**.
- `GET /internal/orders/**` đến `http://orders.default.svc.cluster.local:8081`, **đi trực tiếp trong Kubernetes**.

Ví dụ trong `application.yml` với prefix mới:

```yaml
spring:
  application:
    name: api-gateway
  cloud:
    gateway:
      server:
        webflux:
          httpclient:
            proxy:
              type: http
              host: ${EGRESS_PROXY_HOST}
              port: ${EGRESS_PROXY_PORT:3128}
              non-proxy-hosts-pattern: '(localhost|127\.0\.0\.1|.*\.svc\.cluster\.local|.*\.internal\.example)'
            connect-timeout: 3000
            response-timeout: 10s
          routes:
            - id: partner-api
              uri: https://partner-api.example.test
              predicates:
                - Path=/partners/**
              filters:
                - StripPrefix=1

            - id: orders-internal
              uri: http://orders.default.svc.cluster.local:8081
              predicates:
                - Path=/internal/orders/**
              filters:
                - StripPrefix=1
```

**Giải thích từng phần:**

1. `httpclient.proxy` cấu hình **Reactor Netty HttpClient** phục vụ tuyến HTTP(S), không chỉ riêng một route. Quy tắc bypass giúp phân luồng theo **host đích thực tế**.
2. `${EGRESS_PROXY_HOST}` là placeholder **không có fallback**: deployment có proxy bắt buộc mà không cấp biến nên không được âm thầm dùng localhost hoặc proxy giả.
3. `${EGRESS_PROXY_PORT:3128}` có fallback cổng minh họa; thay đúng cổng do team network cấp.
4. `non-proxy-hosts-pattern` là **biểu thức chính quy Java**, không phải `NO_PROXY` theo cú pháp shell. Biểu thức ví dụ bao phủ `localhost`, `127.0.0.1`, các host kết thúc bằng `.svc.cluster.local` và `.internal.example`.
5. Regex được đặt trong **nháy đơn YAML** để giữ nguyên ký tự gạch chéo ngược; dấu chấm trong regex phải được escape khi muốn khớp dấu chấm thật của tên miền.
6. `connect-timeout` và `response-timeout` là các tham số HTTP client bổ sung, **không tự tạo** retry, circuit breaker hoặc chứng chỉ TLS.
7. `StripPrefix=1` biến `/partners/orders/42` thành `/orders/42`; route internal biến `/internal/orders/42` thành `/orders/42`. Predicate chọn route **trước khi** filter đổi path.

Địa chỉ `proxy.corp.internal`, `partner-api.example.test` và `orders.default.svc.cluster.local` là **giả định**. Trên môi trường thật, hãy dùng địa chỉ do quản trị mạng cung cấp và chắc chắn Gateway có DNS/network route đến proxy, dịch vụ nội bộ và điểm đích cho phép.

### 5.1. Vì sao không dùng localhost làm proxy host trong container?

`localhost` bên trong container Gateway chỉ **container đó** (trừ trường hợp network mode đặc biệt). Nếu proxy là một service khác trong Docker Compose hoặc Kubernetes, dùng DNS service/tên host đúng mạng triển khai, không đặt `localhost:3128` chỉ vì proxy nghe ở cổng đó trên máy của developer.

## 6. Cấu hình tương ứng ở Gateway Server WebFlux 4.x

Nếu dự án sử dụng namespace WebFlux 4.x phổ biến, nhóm thuộc tính nằm trực tiếp ở `spring.cloud.gateway.httpclient`:

```yaml
spring:
  cloud:
    gateway:
      httpclient:
        proxy:
          type: http
          host: ${EGRESS_PROXY_HOST}
          port: ${EGRESS_PROXY_PORT:3128}
          non-proxy-hosts-pattern: '(localhost|127\.0\.0\.1|.*\.svc\.cluster\.local|.*\.internal\.example)'
        connect-timeout: 3000
        response-timeout: 10s
      routes:
        - id: partner-api
          uri: https://partner-api.example.test
          predicates:
            - Path=/partners/**
          filters:
            - StripPrefix=1
```

Hai ví dụ ở mục 5 và 6 **là hai cách cấu hình thay thế theo phiên bản**, không phải hai block nên chép đồng thời vào cùng project. Nếu tên thuộc tính bị thay đổi mà ứng dụng vẫn khởi động, việc proxy không được áp dụng có thể xuất hiện dưới dạng timeout/connection error thay vì thông báo rõ ràng.

**Kiểm tra effective configuration theo đúng phiên bản** trước khi triển khai; đừng suy luận namespace từ mã Java của một bài hướng dẫn cũ. Tài liệu configuration properties của Spring Cloud Gateway là nguồn đối chiếu trực tiếp cho các khóa `proxy.host`, `proxy.port`, `proxy.type`, `non-proxy-hosts-pattern`, `username` và `password`.

## 7. Proxy authentication: cấp thông tin an toàn

Nếu proxy yêu cầu xác thực, bổ sung **hai thuộc tính** vào block `proxy` ở namespace tương ứng:

```yaml
proxy:
  type: http
  host: ${EGRESS_PROXY_HOST}
  port: ${EGRESS_PROXY_PORT:3128}
  username: ${EGRESS_PROXY_USERNAME}
  password: ${EGRESS_PROXY_PASSWORD}
  non-proxy-hosts-pattern: '(localhost|127\.0\.0\.1|.*\.svc\.cluster\.local|.*\.internal\.example)'
```

Đây là **đoạn con** nằm dưới `httpclient.proxy`, không phải file `application.yml` độc lập. Chỉ thêm `username/password` khi proxy thực sự có authentication và phiên bản/client hỗ trợ cơ chế auth tương ứng.

### 7.1. Truyền giá trị từ deployment

Ví dụ Linux/macOS:

```bash
export SPRING_PROFILES_ACTIVE=egress
export EGRESS_PROXY_HOST=proxy.corp.internal
export EGRESS_PROXY_PORT=3128
# EGRESS_PROXY_USERNAME và EGRESS_PROXY_PASSWORD
# phải được cấp qua secret/deployment an toàn, không gõ bí mật thật vào script.
java -jar target/api-gateway.jar
```

Nếu cấu hình có `${EGRESS_PROXY_USERNAME}` và `${EGRESS_PROXY_PASSWORD}` nhưng deployment không cấp giá trị, việc phân giải cấu hình có thể thất bại. Đối với proxy không yêu cầu xác thực, bỏ các thuộc tính này hẳn thay vì đặt mật khẩu giả.

Trong Kubernetes, có thể tham chiếu Secret:

```yaml
# Phần containers của Deployment, không phải toàn bộ Deployment YAML:
containers:
  - name: gateway
    image: example/api-gateway:1.0.0
    env:
      - name: EGRESS_PROXY_HOST
        value: proxy.corp.internal
      - name: EGRESS_PROXY_PORT
        value: "3128"
      - name: EGRESS_PROXY_USERNAME
        valueFrom:
          secretKeyRef:
            name: gateway-egress-proxy
            key: username
      - name: EGRESS_PROXY_PASSWORD
        valueFrom:
          secretKeyRef:
            name: gateway-egress-proxy
            key: password
```

Kubernetes Secret **không tự giải quyết mọi vấn đề bảo mật**. Cần RBAC/least privilege, mã hóa at rest theo chính sách, tránh in biến môi trường trong log/dump và có quy trình xoay vòng. Thay đổi environment của Pod đang chạy thường cần rollout/restart để tiến trình nhận giá trị mới.

### 7.2. Phân biệt 401 và 407

- **`401 Unauthorized`** thường là upstream/API yêu cầu xác thực người dùng hoặc token.
- **`407 Proxy Authentication Required`** là proxy yêu cầu xác thực để tiếp tục kết nối.

Nếu gặp 407 khi mở tunnel, không được sửa JWT route predicate hoặc token upstream một cách mù quáng. Cần xem thông tin đăng nhập proxy, cơ chế authentication mà proxy đòi hỏi và proxy log. Một số proxy enterprise dùng các cơ chế ngoài username/password đơn giản; lúc đó phải trao đổi với đội network để xác định phương án được hỗ trợ.

Không ghi `Proxy-Authorization`, Basic credential, access token hoặc HTTP body chứa thông tin nhạy cảm vào log/wiretap.

## 8. HTTP CONNECT: điểm khác biệt dễ gây lỗi

Reactor Netty hỗ trợ proxy thông qua Netty `ProxyProvider`. **Với HTTP proxy, tài liệu Reactor Netty mô tả client dùng `CONNECT` để tạo tunnel cho cả đích HTTP và HTTPS**. Đây là khác biệt so với một số HTTP client truyền thống gửi `GET http://host/path` trực tiếp đến forward proxy.

Ví dụ khi Gateway muốn đến `https://partner-api.example.test:443`:

```text
Gateway -> Proxy TCP:  proxy.corp.internal:3128

Gateway -> Proxy HTTP: CONNECT partner-api.example.test:443 HTTP/1.1
Proxy -> Gateway HTTP: 200 Connection Established
Gateway <-> Upstream:   TLS handshake trong tunnel
Gateway -> Upstream:    GET /orders/42 (được mã hóa qua TLS)
```

Từ bên ngoài, người dùng vẫn gọi URL của Gateway. `CONNECT` là hoạt động nội bộ giữa HTTP client của Gateway và forward proxy để mở đường đến host/port upstream.

### 8.1. Không phải proxy nào cũng cho CONNECT đến cổng 80

Một số doanh nghiệp chỉ cho `CONNECT` đến port 443; một số proxy đòi xác thực hoặc allowlist hostname. Khi Gateway gọi một đích `http://...:80` bằng cơ chế proxy của Reactor Netty, proxy có thể từ chối `CONNECT host:80` dù lệnh `curl -x proxy http://host` thông thường chạy được.

Hãy xác minh với đội network rằng proxy **hỗ trợ HTTP CONNECT ở những cổng đích cần dùng**, kể cả đích HTTP nếu có. Nếu chính sách chỉ cho `CONNECT` port 443, giải pháp hợp lý thường là dùng HTTPS upstream hoặc điều chỉnh thiết kế/hạ tầng được phê duyệt, không tự vượt qua proxy.

### 8.2. CONNECT tunnel không đồng nghĩa mọi chặng đều được mã hóa

| Tình huống | Điều được bảo vệ |
| --- | --- |
| Gateway → HTTP proxy, CONNECT → **HTTPS** upstream | Traffic HTTP của ứng dụng trong tunnel được TLS bảo vệ giữa Gateway và TLS endpoint của upstream, khi không có TLS interception |
| Gateway → HTTP proxy, CONNECT → **HTTP** upstream | Tunnel có thể chở HTTP **plaintext**, không tự tạo TLS |
| Proxy doanh nghiệp có TLS inspection | Proxy có thể chấm dứt và thiết lập lại TLS theo chính sách; cần quản lý CA, quyền và audit |
| Gateway gọi thẳng HTTPS upstream bằng bypass | Không qua proxy; TLS vẫn cần kiểm tra chứng chỉ/hostname |

“HTTP proxy” nói về **loại proxy protocol**, không có nghĩa cứ bật `type: http` thì hop từ Gateway đến proxy được mã hóa TLS. Nếu yêu cầu bảo vệ thông tin xác thực proxy hoặc dữ liệu kết nối, cần hiểu chính xác topology, loại proxy và các lớp mã hóa của nền tảng.

## 9. Bypass proxy: non-proxy-hosts-pattern là Java regex

Một Gateway có thể gọi cả API công khai và service nội bộ. Nếu đẩy tất cả traffic qua proxy Internet, bạn có thể gặp:

- Proxy không phân giải được DNS Kubernetes `.svc.cluster.local`.
- Proxy chặn dải IP nội bộ hoặc service không công khai.
- Traffic nội bộ đi vòng, tăng latency hoặc vi phạm phân vùng mạng.
- Service discovery `lb://` trả instance IP mà proxy không truy cập được.
- Proxy bị quá tải vì phải xử lý traffic east-west vốn không cần egress.

Thuộc tính `non-proxy-hosts-pattern` nhận **Java regular expression cho tên host cần đi trực tiếp**. Ví dụ:

```yaml
non-proxy-hosts-pattern: '(localhost|127\.0\.0\.1|.*\.svc\.cluster\.local|.*\.internal\.example)'
```

Các trường hợp:

| Host của URI đích | Match regex ví dụ? | Đường đi dự kiến |
| --- | --- | --- |
| `localhost` | Có | Trực tiếp |
| `127.0.0.1` | Có | Trực tiếp |
| `orders.default.svc.cluster.local` | Có | Trực tiếp |
| `auth.internal.example` | Có | Trực tiếp |
| `partner-api.example.test` | Không | Qua proxy |
| `10.20.1.12` | **Không** | Có thể qua proxy, trừ khi bổ sung pattern đúng |

**Đặc biệt với `lb://`:** route logic chỉ có service ID, nhưng sau bước load balancing, Gateway có thể nhận địa chỉ **IP** của instance. Cấu hình chỉ bypass `.svc.cluster.local` có thể **không** match IP nội bộ này. Phải quan sát **host/port thực tế mà HTTP client nhận**, rồi chỉnh regex hoặc thiết kế định tuyến phù hợp.

Để bypass một dải IP cụ thể, dùng Java regex có giới hạn, ví dụ `10\\.20\\.\\d+\\.\\d+` nếu hạ tầng chỉ sử dụng `10.20.x.x` cho những endpoint muốn kết nối trực tiếp. Regex **không phải CIDR parser** và không phải network firewall; khi cần kiểm soát ở cấp mạng, hãy dùng network policy/firewall/egress gateway thật sự.

### 9.1. Sự khác nhau giữa regex và NO_PROXY

`NO_PROXY` thường được nhiều CLI/container tool hiểu như danh sách host/domain/IP, với cách hỗ trợ wildcard, dấu chấm đầu domain hoặc CIDR **khác nhau giữa từng tool**. Trong Gateway, `non-proxy-hosts-pattern` là regex Java.

Ví dụ **không nên chép nguyên văn** vào property regex:

```text
NO_PROXY=localhost,.svc.cluster.local,10.0.0.0/8
```

Đây không phải regex cho `non-proxy-hosts-pattern`. Trong Java regex, `.` là ký tự bất kỳ, `*` là quantifier và `10.0.0.0/8` không đại diện CIDR. Cần biên dịch/kiểm thử pattern phù hợp trước khi áp dụng.

Trong nhiều môi trường, cách đơn giản hơn là **chạy một Gateway chỉ phục vụ nhóm outbound riêng**, hoặc dùng policy mạng và DNS được kiểm soát, thay vì duy trì một regex dài khó review.

### 9.2. DNS được phân giải ở đâu?

Với HTTP proxy được cấu hình và không có custom resolver, Reactor Netty thường **ủy quyền việc phân giải hostname đích cho proxy**, thay vì tự DNS lookup tất cả remote host tại Gateway. Khi một host bị bypass, Gateway phải truy cập trực tiếp và thường cần DNS của chính môi trường Gateway.

Nếu developer cấu hình DNS resolver tùy biến cho Reactor Netty, hành vi phân giải có thể thay đổi; resolver phải phân giải được host khi cần, kể cả lúc dùng proxy. Cần phân biệt:

- Gateway không phân giải được **hostname của proxy**.
- Proxy không phân giải được **hostname của upstream**.
- Gateway không phân giải được **hostname được bypass**.
- Host thực tế sau `lb://` là IP, không match regex hostname.

Đây là bốn lỗi khác nhau. Kiểm tra DNS đúng từ nơi đang thực hiện kết nối, đừng chỉ `nslookup` upstream trong Gateway rồi kết luận proxy cũng phân giải được.

## 10. Profiles và biến môi trường: chỉ bật egress proxy ở nơi cần

Một cách vận hành tốt là để cùng một artifact chạy với **hai cấu hình mạng khác nhau**:

- `local`: API thử nghiệm truy cập trực tiếp, **không khai báo** nhóm proxy.
- `staging` hoặc `prod`: môi trường yêu cầu egress proxy, khai báo `httpclient.proxy` và cấp credentials qua secret.

Có thể đặt proxy vào `application-egress.yml` rồi kích hoạt profile `egress` đồng thời với profile môi trường tương ứng, ví dụ:

```bash
export SPRING_PROFILES_ACTIVE=prod,egress
export EGRESS_PROXY_HOST=proxy.corp.internal
export EGRESS_PROXY_PORT=3128
java -jar target/api-gateway.jar
```

Cấu hình trong `application-egress.yml` cần dùng **đúng namespace** của phiên bản và tham số `${EGRESS_PROXY_HOST}` bắt buộc. Bật profile `egress` mà thiếu host/port nên được phát hiện sớm trong deployment.

**Lưu ý về `HTTP_PROXY`, `HTTPS_PROXY`, `NO_PROXY` và JVM flags:** nhiều công cụ như curl tự hỗ trợ những biến này, hoặc Java client truyền thống dùng `-Dhttp.proxyHost`/`-Dhttps.proxyHost`. Nhưng **không được giả định Reactor Netty HttpClient do Spring Cloud Gateway tạo sẽ tự đọc/áp dụng toàn bộ các biến và system properties đó**.

Đối với Gateway route HTTP(S), hãy cấu hình tường minh `spring.cloud.gateway...httpclient.proxy.*` hoặc cơ chế tùy biến HTTP client **được phiên bản hỗ trợ**, sau đó kiểm chứng proxy logs. Đừng suy ra rằng chỉ cần `export HTTPS_PROXY=...` là route Gateway nhất định đi qua proxy.

### 10.1. Phạm vi cấu hình là HTTP client chung, không phải tùy ý từng route

Nhóm `httpclient.proxy.*` cấu hình proxy trên **HTTP client dùng chung** của Gateway. Nó không đồng nghĩa có một field `proxy` bên trong mỗi route YAML để tự chọn proxy khác nhau.

Nếu yêu cầu:

- API A qua proxy của nhóm đối tác A;
- API B qua proxy B;
- API nội bộ không qua proxy;

thì **một** cấu hình `httpclient.proxy.host` cộng `non-proxy-hosts-pattern` chỉ biểu đạt được một phần. Nên xem xét tách Gateway/egress component theo chính sách, dùng service mesh/egress gateway, hoặc viết tùy biến có kiểm thử và bảo trì rõ ràng trên đúng phiên bản. Không tự cho rằng từng `RouteDefinition` có property proxy độc lập được Spring hỗ trợ.

## 11. TLS, HTTPS và xác minh chứng chỉ ở chặng upstream

Cấu hình egress proxy **không thay thế** cấu hình TLS client:

1. Gateway chọn URL upstream `https://partner-api.example.test`.
2. Gateway kết nối HTTP proxy và yêu cầu tunnel `CONNECT partner-api.example.test:443`.
3. Sau khi tunnel được cho phép, Netty `HttpClient` thực hiện **TLS handshake với TLS endpoint** phía trong tunnel.
4. Chứng chỉ, hostname/SNI, CA/truststore và yêu cầu mTLS vẫn phải hợp lệ.
5. HTTP request thực tế được gửi sau khi TLS handshake thành công.

Nếu proxy doanh nghiệp thực hiện **TLS inspection**, certificate mà Gateway nhìn thấy có thể do CA doanh nghiệp cấp thay vì CA public gốc. Trường hợp đó phải có phê duyệt/policy rõ ràng và trust đúng CA được quản lý. Không tự thêm CA không rõ nguồn hoặc tắt xác minh hostname.

### 11.1. Không dùng insecure trust manager làm cách sửa nhanh

Một số phiên bản có thuộc tính `httpclient.ssl.use-insecure-trust-manager`. **Không dùng `true` trong production** để vượt qua lỗi chứng chỉ; như vậy mất bảo đảm xác minh danh tính upstream.

Nếu lỗi `SSLHandshakeException`, cần xác minh certificate chain, SAN/hostname, SNI, policy TLS phiên bản/cipher và khả năng TLS interception của proxy. Nếu gặp lỗi `HTTP CONNECT` **trước khi TLS bắt đầu**, sửa truststore có thể không giải quyết được vấn đề vì tunnel còn chưa được thiết lập.

### 11.2. Chứng chỉ inbound khác chứng chỉ outbound

Một Gateway có thể có:

- **TLS inbound:** client → ingress/Gateway, cấu hình server certificate.
- **TLS outbound:** Gateway → API đích trong tunnel, cấu hình trust/mTLS của HTTP client.
- **Proxy authentication:** Gateway → forward proxy, cấu hình tài khoản proxy khi cần.

Đây là **ba ranh giới** khác nhau. Có HTTPS inbound không bảo đảm outbound HTTPS; có proxy username/password không bảo đảm đã xác thực JWT với upstream.

## 12. Kiểm thử ở local/staging trước khi đưa vào production

Một phép thử tốt cần **xác minh đường kết nối**, không chỉ thấy HTTP status 200.

### 12.1. Kiểm tra proxy riêng bằng curl

Trên máy có quyền kết nối proxy và đích thử nghiệm:

```bash
# Cú pháp curl chỉ để kiểm tra network/proxy, không xác minh Gateway đã dùng proxy.
curl -v --proxy http://proxy.corp.internal:3128 \
  https://partner-api.example.test/health
```

Dùng `-v` để xem giai đoạn `CONNECT`, HTTP status và dấu hiệu TLS. Thay URL mẫu bằng endpoint kiểm thử do tổ chức quản lý. **Không đưa password trực tiếp vào URL/lệnh curl chia sẻ** vì có thể bị lưu trong history và log.

Lưu ý: curl có hành vi proxy/CONNECT riêng, **không đồng nghĩa** 100% với Reactor Netty. Đặc biệt, một proxy có thể chấp nhận HTTP request dạng forward truyền thống nhưng không chấp nhận `CONNECT` đến cổng HTTP; test Netty vẫn cần thiết.

### 12.2. Gọi Gateway thay vì gọi trực tiếp upstream

Khi Gateway đang chạy `http://localhost:8080` trong môi trường thử nghiệm:

```bash
curl -i http://localhost:8080/partners/health
curl -i http://localhost:8080/internal/orders/42
```

Quan sát cả hai tuyến:

- `partner-api`: proxy log/access policy có ghi `CONNECT partner-api.example.test:443`; upstream nhận path `/health`.
- `orders-internal`: proxy log **không** có kết nối tới `orders.default.svc.cluster.local` (nếu bypass match); service trực tiếp nhận `/orders/42`.
- Không dựa duy nhất vào `200 OK`: response có thể bị cache hoặc do một upstream khác trả. Kết hợp route ID, request ID, proxy access log và upstream counters khi cần.

Để kiểm tra bypass, có thể thử với **một proxy mock/egress proxy test** có log và một upstream mock có nhận diện request. Không dùng proxy cá nhân/không đáng tin để kiểm thử dữ liệu thật.

### 12.3. Ma trận kiểm thử khuyến nghị

| Ca | Mô tả | Dấu hiệu cần kiểm tra |
| --- | --- | --- |
| P1 | Gateway có proxy, gọi HTTPS external | Có CONNECT 443, TLS và response của upstream |
| P2 | Gateway có proxy, gọi HTTP external | Proxy có cho CONNECT tới cổng HTTP không? |
| P3 | Gọi host khớp `non-proxy-hosts-pattern` | Không có CONNECT, kết nối trực tiếp |
| P4 | Gọi `lb://internal-service` trả IP | Regex có bypass được **IP sau chọn instance** không? |
| P5 | Proxy yêu cầu auth nhưng không cấp credentials | 407 hoặc lỗi thiết lập tunnel phù hợp |
| P6 | Proxy chặn hostname/port | 403/407/5xx/timeout tùy proxy; xem proxy log |
| P7 | Upstream HTTPS dùng CA chưa tin cậy | TLS handshake lỗi sau hoặc trong quá trình tunnel |
| P8 | Proxy không hoạt động | Connection timeout/refused, upstream không được gọi |
| P9 | Không bật profile `egress` | Gateway cố truy cập trực tiếp; có thể thất bại vì network policy |
| P10 | Sai namespace `httpclient.proxy.*` | Property không được áp dụng; không có traffic qua proxy |
| P11 | Service nội bộ thuộc `.svc.cluster.local` nhưng gọi bằng IP | Bypass theo suffix không đủ; kiểm tra hostname thực tế |

**Các mã status trong bảng không phải bảo đảm của Gateway:** proxy, hạ tầng và error handler có thể biến đổi lỗi kết nối thành 5xx khác nhau. Quan trọng là xác định **lớp tạo lỗi**.

### 12.4. Kiểm tra route lb:// và discovery

Nếu Gateway dùng `lb://ORDER-SERVICE`:

1. `ReactiveLoadBalancerClientFilter` chọn một `ServiceInstance`.
2. URL cụ thể có host/port và `isSecure` để xác định HTTP hay HTTPS.
3. HTTP client quyết định có proxy/bypass dựa trên **địa chỉ kết nối cụ thể** và cấu hình.
4. Nếu instance công bố `isSecure=false` nhưng route/infra yêu cầu HTTPS, proxy không tự sửa mismatch này.

Đừng xem cờ `isSecure` là cờ “có dùng egress proxy hay không”. Nó chỉ liên quan giao thức bảo mật của instance; **proxy selection** là chính sách khác.

## 13. Troubleshooting theo từng tầng kết nối

| Triệu chứng | Khả năng cao | Hướng chẩn đoán |
| --- | --- | --- |
| Gateway ở local gọi API được, lên Kubernetes timeout | Bị chặn egress trực tiếp, chưa bật proxy hoặc proxy DNS sai | Kiểm tra profile, proxy host/port, network policy |
| `curl --proxy` hoạt động, Gateway không đi qua proxy | Chưa có property tương ứng, sai namespace hoặc HTTP client khác | So sánh Gateway Netty route, proxy logs, cấu hình hiệu lực |
| `UnknownHostException` với proxy host | Pod không phân giải được hostname proxy | Kiểm tra DNS tại Pod/namespace của Gateway |
| `UnknownHostException` với upstream qua proxy | Proxy không phân giải được tên upstream, hoặc custom resolver tự resolve | Phân biệt DNS tại proxy và Gateway |
| Proxy trả `407` | Thiếu/sai proxy credentials, cơ chế auth không hỗ trợ | Kiểm tra cấu hình username/password và chính sách proxy |
| Proxy trả `403` hoặc không chấp nhận CONNECT | Allowlist, policy port hoặc phương thức CONNECT bị chặn | Kiểm tra proxy access log, target hostname/port |
| Kết nối HTTPS qua proxy lỗi `SSLHandshakeException` | CA/trust, SNI, cert hostname hoặc TLS interception | Kiểm tra chuỗi TLS sau CONNECT và chứng chỉ |
| HTTP external qua proxy lỗi còn HTTPS thành công | Proxy không cho CONNECT cổng 80 hoặc host bị chặn | Xem policy CONNECT cho HTTP target |
| `orders.default.svc.cluster.local` bị gửi tới egress proxy | Regex bypass thiếu/sai escape hoặc host khác dự kiến | Kiểm tra `non-proxy-hosts-pattern`, host thực nhận |
| Route `lb://` nội bộ vẫn qua proxy | Discovery trả IP/hostname không khớp pattern | Kiểm tra `ServiceInstance` host/port, điều chỉnh regex |
| 404 từ Gateway | Route predicate/path không khớp | Kiểm tra route registration, `StripPrefix`/rewrite |
| 401 từ backend | Token/auth tới backend không đúng | Đừng nhầm với 407 từ proxy |
| 502/503/504, kết nối chập chờn | Proxy outage, timeout, pool saturation, upstream unavailable | Kiểm tra từng hop, Netty metrics, proxy health |
| Mở wiretap thì lộ credentials | Debug quá chi tiết trong production | Tắt wiretap/log nhạy cảm, luân chuyển secret nếu bị lộ |

### 13.1. Cách phân biệt lỗi trước và sau HTTP CONNECT

Một cách chẩn đoán nhanh:

```text
(1) Gateway kết nối được proxy host:port?
        Không -> DNS/network/firewall/connection timeout
        Có
(2) Proxy chấp nhận CONNECT target-host:target-port?
        Không -> 407/403/502/chính sách proxy
        Có
(3) HTTPS handshake với target thành công?
        Không -> CA/hostname/SNI/TLS interception
        Có
(4) Upstream trả HTTP response?
        Không -> timeout/upstream/transport
        Có -> kiểm tra status/header/body và filter chain
```

Luôn xác định chính xác **hostname, port và scheme** mà Gateway dùng. Một route có `lb://` có thể đổi instance giữa các request; chẩn đoán không nên dựa trên giả định mọi request đi cùng backend.

## 14. Bảo mật: proxy không thay thế chính sách API

Egress proxy quản lý **đường đi mạng**, nhưng bảo mật Gateway còn cần:

- **Xác thực và phân quyền:** Spring Security/JWT tại biên và kiểm tra quyền nghiệp vụ tại service phù hợp.
- **Rate limiting:** giới hạn tần suất theo danh tính/API key đáng tin, không chỉ dựa proxy.
- **Circuit breaker, timeout, retry:** xử lý khi proxy/upstream chậm hoặc lỗi; không retry vô điều kiện thao tác ghi không idempotent.
- **TLS đúng chặng:** bảo vệ client → Gateway và Gateway → upstream, quản lý trust và mTLS theo yêu cầu.
- **Quản lý secret:** proxy credentials, JWT secrets và chứng chỉ phải nằm ngoài source code, không vào trace/log.
- **Network enforcement:** proxy bypass là lựa chọn route kết nối, **không phải chính sách firewall**; cần chống đường egress trái phép tại hạ tầng.
- **Observability:** route ID, upstream host đã kiểm soát, proxy status, latency và SSL errors; tránh ghi URL nhạy cảm hoặc body.

Một rủi ro đáng chú ý là **SSRF và lạm dụng egress**: nếu URI route, host đích hoặc header điều khiển upstream bị lấy trực tiếp từ input client, attacker có thể lợi dụng Gateway/proxy để truy cập dịch vụ nội bộ hoặc endpoint metadata. Hãy cố định route đến allowlist backend, kiểm soát DNS/rebinding nếu có dynamic target, áp dụng network policy và không xem việc “có egress proxy” là tấm chắn SSRF tuyệt đối.

### 14.1. Không tiết lộ proxy credentials

`Proxy-Authorization` chỉ dành cho proxy và không nên được sao chép tùy tiện tới upstream. Cần phân biệt header hop-by-hop và request header được Gateway chuyển tiếp. Trong log, không ghi:

- Mật khẩu hoặc tên đăng nhập nhạy cảm của proxy.
- Bearer token, Cookie, Set-Cookie, API key.
- Request/response body chứa dữ liệu người dùng.
- Toàn bộ HTTP headers khi chưa có bộ lọc/redaction.

Khi quay vòng proxy password, cần biết quy trình restart/reload của cấu hình HTTP client. Không mặc định một tiến trình đang chạy tự nhận secret mới từ môi trường nếu không có cơ chế refresh được hỗ trợ.

## 15. Tình huống thiết kế: outbound tới đối tác và nội bộ Kubernetes

Giả sử một Gateway phục vụ ba API:

| API công khai | URI backend | Chính sách mạng |
| --- | --- | --- |
| `/partners/invoices/**` | `https://billing.partner.example.test` | Chỉ đi qua egress proxy đã duyệt |
| `/internal/orders/**` | `lb://order-service` | Gọi trực tiếp các pod/service nội bộ |
| `/status` | `forward:///internal/status` | Xử lý handler WebFlux cục bộ |

Thiết kế đề xuất:

1. Khai báo route và các filter path/header rõ ràng, không nhận host đích tùy ý từ client.
2. Cấu hình proxy HTTP client từ biến môi trường **chỉ trong profile cần egress**.
3. Tạo regex bypass dựa trên **hostname/IP thực tế của các ServiceInstance**, không chỉ tên logic `order-service`.
4. Cấu hình ingress/network policy để bắt buộc outbound public qua proxy, nhưng vẫn cho lưu lượng nội bộ đúng phạm vi.
5. Xác nhận proxy hỗ trợ `CONNECT` đến `billing.partner.example.test:443`.
6. Xác minh TLS certificate/hostname và proxy authentication.
7. Gửi request test; đối chiếu proxy logs, log upstream, route ID và response.
8. Kiểm thử proxy outage: Gateway trả lỗi có kiểm soát, timeout phù hợp và không tạo retry storm.
9. Bảo đảm route forward cục bộ không bị nhầm là outbound HTTP cần proxy.

Nếu trong cùng pool `lb://` có instance khai báo host bằng IP, bypass regex theo `.svc.cluster.local` sẽ không đủ. Đây thường là nơi môi trường staging và production khác nhau dù file cấu hình nhìn gần như giống hệt.

## 16. Checklist trước production

- [ ] Đã xác định **forward proxy đầu ra**, không nhầm với reverse proxy/ingress.
- [ ] Đúng starter Gateway Server WebFlux và namespace `httpclient.proxy` của phiên bản đang dùng.
- [ ] Proxy `host`, `port`, `type` được cấp từ deployment và kiểm chứng DNS/network.
- [ ] Proxy thực sự cho phép `CONNECT` đến hostname/port upstream cần thiết.
- [ ] `username/password` được bảo vệ bằng secret management, có rotation và redaction.
- [ ] `non-proxy-hosts-pattern` là **Java regex**, đã thử đầy đủ hostname nội bộ lẫn IP từ discovery.
- [ ] Không giả định `HTTP_PROXY`/`HTTPS_PROXY`/`NO_PROXY` tự cấu hình tất cả client của Gateway.
- [ ] Tách bạch HTTP proxy, HTTP upstream, HTTPS upstream và TLS interception.
- [ ] CA/truststore, SNI/hostname, mTLS đúng chính sách; không dùng insecure trust manager.
- [ ] Kiểm tra bypass bằng proxy logs, không chỉ theo HTTP 200.
- [ ] Phân biệt lỗi proxy 407 với lỗi auth upstream 401.
- [ ] Phân biệt lỗi CONNECT, TLS handshake, timeout và status upstream.
- [ ] Đã kiểm thử `lb://`, cache/discovery, IP/host khác nhau và proxy outage.
- [ ] `WebClient` custom, discovery/SDK client có cấu hình egress riêng nếu cần.
- [ ] Có network policy, allowlist target, SSRF protection và giám sát retry/circuit breaker.
- [ ] Không có proxy credentials/token trong logs, traces hoặc config công khai.

## 17. Tổng kết

**Cấu hình proxy đầu ra cho Spring Cloud Gateway Server WebFlux** là cấu hình **Reactor Netty HttpClient** dùng để kết nối đến upstream. Những thuộc tính cốt lõi gồm `httpclient.proxy.host`, `port`, `type`, `username`, `password` và `non-proxy-hosts-pattern`; prefix đầy đủ phụ thuộc phiên bản WebFlux 4.x hay 5.x.

Điểm cần nhớ nhất là **một HTTP proxy trong Reactor Netty thường được dùng bằng `CONNECT` kể cả khi upstream dùng HTTP**, nên proxy doanh nghiệp phải cho phép phương thức và cổng tương ứng. Bypass được biểu diễn bằng **Java regex**, không phải giá trị `NO_PROXY` sao chép từ container. Khi route dùng `lb://`, hãy kiểm tra địa chỉ thực của `ServiceInstance` trước khi kết luận bypass đúng.

Proxy là một phần của vận hành kết nối và TLS, không thay thế route predicate, filter chain, xác thực, giới hạn lưu lượng, circuit breaker, retry, service discovery hay observability. Quy trình hiệu quả là **xác định topology → cấu hình theo môi trường → xác minh CONNECT/bypass/TLS → thử lỗi từng chặng → quan sát và bảo vệ bằng network policy**.

### Tài liệu tham khảo

- [Spring Cloud Gateway — Configuration Properties (Proxy cho WebFlux HttpClient)](https://docs.spring.io/spring-cloud-gateway/reference/configprops.html).
- [Spring Cloud Gateway 4.1 — Configuration Properties](https://docs.spring.io/spring-cloud-gateway/reference/4.1/configprops.html).
- [Spring Cloud Gateway Server WebFlux — Global Filters / Netty Routing Filter](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/global-filters.html).
- [Reactor Netty — HTTP Client / Proxy Support](https://projectreactor.io/docs/netty/release/reference/http-client.html).
