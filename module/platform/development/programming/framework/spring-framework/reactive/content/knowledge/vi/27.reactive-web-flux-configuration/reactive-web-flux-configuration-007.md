# `ForwardedHeaderTransformer` và ranh giới tin cậy proxy trong Spring WebFlux

## 1. Bài toán: ứng dụng cần biết request gốc đi từ đâu

Một ứng dụng WebFlux thường chạy phía sau reverse proxy, ingress controller hoặc load balancer. Client truy cập địa chỉ công khai:

```text
https://api.example.com/orders
```

Proxy kết thúc TLS rồi chuyển tiếp request vào mạng nội bộ:

```text
http://orders-service:8080/orders
```

Khi request tới ứng dụng, kết nối TCP trực tiếp là từ proxy tới `orders-service`. Vì vậy, nếu chỉ nhìn request mà server nhận được, ứng dụng có thể thấy:

- Scheme là `http`, dù client dùng HTTPS.
- Host là `orders-service`, không phải `api.example.com`.
- Port là `8080`, không phải `443`.
- Remote address là IP của proxy, không phải IP client ban đầu.
- Path nội bộ có thể chứa context prefix mà client bên ngoài không nhìn thấy.

Proxy có thể chuyển tiếp metadata về request gốc qua các HTTP header. Spring WebFlux cung cấp `ForwardedHeaderTransformer` để đọc các header này, điều chỉnh thông tin request và loại bỏ các header đã xử lý.

Nhưng forwarded headers là dữ liệu do HTTP client có thể tự gửi. Nếu ứng dụng tin chúng mà không kiểm soát proxy, client có thể giả mạo host, scheme hoặc địa chỉ IP. Đây là ranh giới tin cậy quan trọng nhất của chủ đề.

Sau bài học, bạn có thể:

1. Phân biệt `Forwarded` theo RFC 7239 với nhóm `X-Forwarded-*`.
2. Hiểu `ForwardedHeaderTransformer` thay đổi URI và địa chỉ request như thế nào.
3. Đăng ký transformer trong Spring WebFlux và cấu hình Spring Boot.
4. Phân biệt `FRAMEWORK`, `NATIVE` và `NONE`.
5. Thiết kế proxy ở trust boundary để loại bỏ forwarded headers giả mạo.
6. Xử lý nhiều proxy, client IP, external HTTPS và URL prefix.
7. Dùng `removeOnly` khi chỉ cần xóa forwarded headers mà không sử dụng chúng.
8. Kiểm thử hành vi bằng `WebTestClient` và `MockServerHttpRequest`.

## 2. Vì sao proxy làm thay đổi thông tin request?

Xét mô hình:

```text
Browser
  |
  | HTTPS https://api.example.com/orders
  v
Reverse proxy / ingress
  | - TLS termination
  | - public host: api.example.com
  | - public port: 443
  | - client address: 203.0.113.25
  |
  | HTTP http://orders-service:8080/orders
  v
Spring WebFlux
```

Ứng dụng phía sau proxy nhận kết nối từ proxy. Nếu không có forwarded metadata, request có thể được biểu diễn như sau:

| Thông tin | Client nhìn thấy | Backend nhìn thấy |
|---|---|---|
| Scheme | `https` | `http` |
| Host | `api.example.com` | `orders-service` |
| Port | `443` | `8080` |
| Remote address | `203.0.113.25` | IP của proxy |
| Path công khai | `/orders` | Có thể là `/internal/orders` |

Sai lệch này ảnh hưởng nhiều hơn việc hiển thị thông tin:

- Redirect có thể trả URL `http://orders-service:8080/...`.
- Link tuyệt đối trong JSON/HTML có thể chứa host nội bộ.
- Cookie `Secure` hoặc logic kiểm tra HTTPS có thể hoạt động sai.
- OAuth2 redirect URI có thể được tạo với scheme/host không đúng.
- Audit log, rate limit hoặc chính sách theo IP có thể dùng nhầm địa chỉ proxy.
- Ứng dụng đặt sau path prefix có thể tạo link sai.

Forwarded headers cho phép proxy thông báo một số thuộc tính của request trước khi chuyển tiếp. WebFlux cần biến metadata đó thành một request có cùng góc nhìn với client bên ngoài.

## 3. Hai họ forwarded headers

Có hai kiểu header thường gặp.

### 3.1. Header chuẩn `Forwarded` theo RFC 7239

RFC 7239 định nghĩa một header chuẩn có thể chứa nhiều thuộc tính:

```http
Forwarded: for=203.0.113.25;proto=https;host=api.example.com
```

Các thuộc tính quan trọng:

| Thuộc tính | Ý nghĩa |
|---|---|
| `for` | Địa chỉ client hoặc hop đứng trước proxy |
| `by` | Địa chỉ proxy tạo entry |
| `host` | Host ban đầu mà client truy cập |
| `proto` | Protocol ban đầu, thường là `http` hoặc `https` |

Một chuỗi nhiều proxy có thể có nhiều phần tử phân tách bằng dấu phẩy:

```http
Forwarded: for=203.0.113.25;proto=https;host=api.example.com,
           for=10.10.0.12;by=10.10.0.20
```

Giá trị IPv6, identifier được ẩn danh và các chuỗi có ký tự đặc biệt có quy tắc quoting riêng. Không nên tự tách header bằng `split(",")` hoặc `split(";")` để xây dựng logic bảo mật.

### 3.2. Nhóm header `X-Forwarded-*`

Đây là nhóm header phổ biến trước khi RFC 7239 ra đời:

```http
X-Forwarded-For: 203.0.113.25
X-Forwarded-Host: api.example.com
X-Forwarded-Proto: https
X-Forwarded-Port: 443
```

Các header thường gặp:

| Header | Ý nghĩa |
|---|---|
| `X-Forwarded-For` | IP client/hop trước đó |
| `X-Forwarded-Host` | Host công khai |
| `X-Forwarded-Proto` | Scheme công khai |
| `X-Forwarded-Port` | Port công khai |
| `X-Forwarded-Ssl` | Trạng thái SSL, thường `on` hoặc `off` |
| `X-Forwarded-Prefix` | Prefix path công khai được proxy loại bỏ hoặc thay đổi khi chuyển tiếp |

`X-Forwarded-*` là quy ước phổ biến, không phải một nhóm header chuẩn thống nhất trong RFC 7239. Mỗi proxy có thể hỗ trợ một tập header khác nhau. Ứng dụng cần biết proxy đang gửi loại nào.

### 3.3. Ví dụ request đi qua proxy

Request backend có thể trông như sau:

```http
GET /orders HTTP/1.1
Host: orders-service:8080
X-Forwarded-For: 203.0.113.25
X-Forwarded-Host: api.example.com
X-Forwarded-Proto: https
X-Forwarded-Port: 443
```

Backend vẫn nhận kết nối HTTP nội bộ, nhưng forwarded headers mô tả request công khai mà client đã gửi.

`ForwardedHeaderTransformer` có thể dùng thông tin này để điều chỉnh request URI và địa chỉ tương ứng trước khi tạo `ServerWebExchange`.

## 4. `ForwardedHeaderTransformer` làm gì?

`ForwardedHeaderTransformer` thuộc package:

```java
org.springframework.web.server.adapter.ForwardedHeaderTransformer
```

Đây là cơ chế của Spring WebFlux, tương ứng với `ForwardedHeaderFilter` ở Servlet stack.

Khi được đăng ký, transformer:

1. Kiểm tra request có forwarded headers hay không.
2. Đọc thông tin host, port, scheme từ `Forwarded` hoặc `X-Forwarded-*`.
3. Có thể cập nhật remote/local address từ thông tin `for`/`by`.
4. Xử lý `X-Forwarded-Prefix` theo cấu hình.
5. Xóa các forwarded headers đã xử lý khỏi request.
6. Trả về request đã được điều chỉnh để WebFlux tạo exchange và tiếp tục xử lý.

Mô hình:

```text
Incoming ServerHttpRequest
        |
        v
ForwardedHeaderTransformer
        |
        +---- Không có forwarded headers
        |          |
        |          v
        |     Giữ request gốc
        |
        +---- Có forwarded headers
                   |
                   v
             Đọc metadata
                   |
                   v
          Cập nhật URI/address
                   |
                   v
          Xóa forwarded headers
                   |
                   v
          ServerWebExchange
                   |
                   v
          WebFilter / Controller
```

Transformer chạy sớm, trước khi `ServerWebExchange` được tạo. Nhờ đó controller, WebFilter và các thành phần downstream có thể nhìn thấy request đã được điều chỉnh.

### 4.1. Request URI được điều chỉnh

Ví dụ request gốc tới backend:

```text
http://orders-service:8080/orders/42
```

Header proxy gửi:

```http
Forwarded: for=203.0.113.25;proto=https;host=api.example.com:443
```

Sau khi được xử lý, URI mà ứng dụng nhìn thấy có thể là:

```text
https://api.example.com:443/orders/42
```

Các API thường bị ảnh hưởng:

```java
ServerHttpRequest request = exchange.getRequest();

URI uri = request.getURI();

String scheme = uri.getScheme();
String host = uri.getHost();
int port = uri.getPort();
String path = uri.getRawPath();

InetSocketAddress remoteAddress = request.getRemoteAddress();
```

Không cần tự đọc header rồi sửa URI trong từng controller. Transformer cung cấp cách xử lý tập trung ở tầng WebFlux.

### 4.2. Remote address có thể được cập nhật

Nếu có:

```http
X-Forwarded-For: 203.0.113.25
```

transformer có thể cập nhật `ServerHttpRequest.getRemoteAddress()` theo địa chỉ được chuyển tiếp.

Điều này thuận tiện cho logging hoặc tạo request metadata. Tuy nhiên, sau khi transformer chạy, remote address có thể đại diện cho client theo forwarded header thay vì TCP peer trực tiếp là proxy.

Vì vậy, không dùng remote address đã được điều chỉnh để xác định proxy nào đang kết nối trực tiếp. Việc kiểm tra peer/trust boundary cần được thực hiện ở tầng mạng hoặc tầng có quyền truy cập địa chỉ kết nối thực.

### 4.3. Forwarded headers được xóa sau khi xử lý

Sau khi transformer sử dụng metadata, các header như `Forwarded`, `X-Forwarded-For`, `X-Forwarded-Host`, `X-Forwarded-Proto` và các header liên quan được loại bỏ khỏi request đã điều chỉnh.

Điều này tránh để downstream code vô tình xử lý lại cùng dữ liệu. Nếu controller cần thông tin, hãy đọc URI hoặc remote address đã được điều chỉnh.

Không viết code dựa trên giả định rằng controller vẫn luôn nhìn thấy `X-Forwarded-For` sau khi transformer đã chạy.

## 5. Đăng ký transformer trong Spring WebFlux

`WebHttpHandlerBuilder` có thể tự phát hiện một bean tên chính xác là `forwardedHeaderTransformer`.

Trong Spring Framework thuần, có thể đăng ký:

```java
@Configuration
public class ForwardedHeaderConfiguration {

    @Bean
    public ForwardedHeaderTransformer forwardedHeaderTransformer() {
        return new ForwardedHeaderTransformer();
    }
}
```

Tên bean được giữ là `forwardedHeaderTransformer` để WebFlux phát hiện và sử dụng.

Không cần tạo một `WebFilter` tự đọc forwarded headers. Transformer được xử lý sớm hơn, trước khi exchange được tạo.

### 5.1. Không nhầm `ForwardedHeaderFilter` với transformer

| Thành phần | Stack | Vai trò |
|---|---|---|
| `ForwardedHeaderFilter` | Spring MVC / Servlet | Bọc request/response Servlet để áp dụng forwarded headers |
| `ForwardedHeaderTransformer` | Spring WebFlux / Reactive | Điều chỉnh `ServerHttpRequest` trước khi tạo exchange |

Nếu ứng dụng dùng `spring-boot-starter-webflux`, hãy dùng `ForwardedHeaderTransformer`.

`ForwardedHeaderFilter` thuộc Servlet stack. Không đăng ký nó như một `WebFilter` reactive.

## 6. Cấu hình Spring Boot: FRAMEWORK, NATIVE và NONE

Spring Boot có thuộc tính:

```properties
server.forward-headers-strategy=FRAMEWORK
```

Ba lựa chọn chính:

| Giá trị | Ý nghĩa |
|---|---|
| `FRAMEWORK` | Dùng cơ chế xử lý forwarded headers của Spring Framework; WebFlux dùng `ForwardedHeaderTransformer` |
| `NATIVE` | Dùng hỗ trợ forwarded headers của embedded server/container |
| `NONE` | Không bật cơ chế xử lý forwarded headers |

Với WebFlux, cấu hình Spring Framework:

```properties
server.forward-headers-strategy=FRAMEWORK
```

Hoặc YAML:

```yaml
server:
  forward-headers-strategy: FRAMEWORK
```

Boot sẽ cấu hình hỗ trợ forwarded headers ở tầng Framework theo strategy này.

### 6.1. Khi nào chọn FRAMEWORK?

Chọn `FRAMEWORK` khi:

- Muốn xử lý forwarded headers theo Spring WebFlux.
- Cần cùng hành vi trên các connector khác nhau.
- Muốn sử dụng `ForwardedHeaderTransformer`.
- Cần `removeOnly` hoặc muốn kiểm soát bean transformer.

### 6.2. Khi nào chọn NATIVE?

`NATIVE` yêu cầu embedded server xử lý forwarded headers. Hành vi cụ thể phụ thuộc connector/server và phiên bản.

Nếu dùng native support, hãy đọc tài liệu đúng embedded server đang chạy. Đừng giả định các container xử lý tất cả header giống hệt nhau.

### 6.3. Tránh xử lý hai lần

Không nên đồng thời bật xử lý forwarded headers ở cả native server và Spring Framework nếu không có thiết kế rõ ràng.

Nếu cả hai tầng cùng điều chỉnh URI hoặc remote address, request có thể bị biến đổi hai lần hoặc có kết quả khó dự đoán.

Hãy chọn một chiến lược rõ ràng:

- `FRAMEWORK`: Spring xử lý.
- `NATIVE`: container xử lý.
- `NONE`: không xử lý.

## 7. Ranh giới tin cậy: vì sao forwarded headers nguy hiểm?

HTTP client có thể tự gửi header:

```http
X-Forwarded-For: 127.0.0.1
X-Forwarded-Host: admin.internal
X-Forwarded-Proto: https
```

Nếu request đi thẳng tới ứng dụng và transformer tin các giá trị này, ứng dụng có thể tưởng request đến từ localhost, host quản trị nội bộ hoặc kết nối HTTPS.

Đây là giả mạo request metadata.

`ForwardedHeaderTransformer` không xác thực rằng header được thêm bởi proxy đáng tin cậy. Nó không phải proxy allowlist, không xác thực chữ ký và không kiểm tra rằng địa chỉ kết nối trực tiếp thuộc proxy hợp lệ.

### 7.1. Proxy ở trust boundary phải loại bỏ dữ liệu client gửi

Quy tắc quan trọng:

> Proxy đầu tiên tại ranh giới tin cậy phải xóa forwarded headers do client bên ngoài gửi vào, rồi tạo lại các giá trị forwarded từ metadata mà chính proxy xác định được.

Cần xử lý cả hai họ:

- `Forwarded`
- Tất cả `X-Forwarded-*` mà ứng dụng hoặc hạ tầng sử dụng

Nếu proxy chỉ thêm một giá trị vào header có sẵn từ client, attacker có thể đưa giá trị giả vào chuỗi.

Ví dụ nguy hiểm:

```http
X-Forwarded-For: 127.0.0.1
```

Proxy nối thêm IP client thật mà không xóa header cũ:

```http
X-Forwarded-For: 127.0.0.1, 203.0.113.25
```

Nếu một thành phần downstream tin phần tử đầu tiên mà không có chính sách trust rõ ràng, nó có thể nhận IP giả.

### 7.2. Proxy nên tạo header từ kết nối mà nó xác minh

Một proxy ở biên có thể tạo:

```http
X-Forwarded-For: 203.0.113.25
X-Forwarded-Host: api.example.com
X-Forwarded-Proto: https
X-Forwarded-Port: 443
```

Các giá trị này phải được tạo từ kết nối và host mà proxy đã kiểm tra.

Nếu proxy nhận request qua một proxy upstream khác, cần cấu hình trust chain ở tầng proxy. Không tự động tin mọi địa chỉ có trong header do client gửi.

### 7.3. Chặn truy cập trực tiếp tới backend

Ngay cả khi proxy đã cấu hình đúng, ứng dụng vẫn có thể bị tấn công nếu client kết nối trực tiếp tới backend và gửi forwarded headers giả.

Nên áp dụng các lớp bảo vệ:

- Backend chỉ nhận traffic từ subnet/security group của proxy.
- Kubernetes NetworkPolicy chỉ cho ingress/gateway được kết nối tới service.
- Không expose trực tiếp port backend ra Internet.
- Proxy ở edge phải xóa header forwarded từ request bên ngoài.
- Chỉ tạo lại những header nằm trong contract của hệ thống.
- Hostname công khai nên được giới hạn theo domain được phép.

`ForwardedHeaderTransformer` xử lý metadata; việc kiểm soát ai được gửi metadata là trách nhiệm của kiến trúc mạng và proxy.

## 8. Cấu hình reverse proxy an toàn

Ví dụ Nginx chuyển tiếp HTTPS tới ứng dụng WebFlux chạy HTTP nội bộ:

```nginx
server {
    listen 443 ssl;
    server_name api.example.com;

    location / {
        proxy_pass http://orders-service:8080;

        proxy_set_header Host $host;

        # Bỏ header chuẩn do client gửi vào.
        proxy_set_header Forwarded "";

        # Ghi lại metadata từ kết nối mà proxy trực tiếp nhận.
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Port $server_port;

        # Không dùng prefix nếu proxy không rewrite path.
        proxy_set_header X-Forwarded-Prefix "";
        proxy_set_header X-Forwarded-Ssl "";
    }
}
```

Đây là cấu hình minh họa cho một proxy biên. Trong môi trường nhiều proxy, cần cấu hình real IP/trusted upstream phù hợp và chỉ nối tiếp thông tin từ proxy đã xác minh.

Nếu ứng dụng dùng thêm header `X-Forwarded-*` khác, proxy cũng phải xóa hoặc ghi đè các header đó theo contract. Không để các giá trị do client cung cấp đi xuyên qua trust boundary.

### 8.1. Vì sao dùng `$remote_addr` ở proxy biên?

`$remote_addr` là peer mà Nginx đang nhận kết nối trực tiếp. Khi Nginx là edge proxy, nó có thể dùng giá trị đó để ghi lại client address đã quan sát.

Nếu Nginx đứng sau một load balancer khác, `$remote_addr` có thể là địa chỉ load balancer. Khi đó phải cấu hình trusted real-IP source và proxy chain rõ ràng. Không bật tin cậy toàn bộ nguồn IP.

### 8.2. Đừng dùng `$proxy_add_x_forwarded_for` một cách máy móc

`$proxy_add_x_forwarded_for` thường nối `$remote_addr` vào giá trị `X-Forwarded-For` hiện có.

Nếu giá trị hiện có đến trực tiếp từ client mà chưa được làm sạch, chuỗi mới vẫn chứa dữ liệu giả mạo.

Chỉ append khi proxy đã xác minh và làm sạch chuỗi từ upstream đáng tin cậy. Ở edge proxy, overwrite thường là cách dễ kiểm soát hơn.

## 9. Nhiều proxy và chuỗi địa chỉ client

Một request có thể đi qua nhiều hop:

```text
Client
  |
  v
Edge proxy
  |
  v
Internal load balancer
  |
  v
Ingress
  |
  v
WebFlux application
```

Các proxy có thể tạo một chuỗi:

```http
X-Forwarded-For: client-ip, proxy-1, proxy-2
```

Hoặc:

```http
Forwarded: for=client-ip;proto=https,
           for=proxy-1,
           for=proxy-2
```

Các giá trị trong chuỗi chỉ đáng tin khi từng hop được quản lý theo một trust policy rõ ràng.

### 9.1. Không coi phần tử đầu tiên là IP đáng tin mặc định

Nhiều hệ thống dùng phần tử đầu tiên trong `X-Forwarded-For` làm client IP. Điều đó chỉ đúng nếu proxy tại trust boundary đã loại bỏ header giả mạo ban đầu và các proxy tiếp theo tuân thủ contract.

Nếu không, client có thể tự thêm phần tử đầu tiên giả rồi proxy chỉ append các địa chỉ khác vào sau.

### 9.2. Xác định proxy nào được phép thêm metadata

Trong hệ thống nhiều proxy:

1. Xác định proxy nào là trust boundary.
2. Xóa forwarded headers từ traffic không đáng tin.
3. Định nghĩa proxy nào được phép append thông tin vào chain.
4. Đặt giới hạn và quy tắc chọn client address.
5. Chặn đường truy cập trực tiếp tới backend.
6. Kiểm thử cả request đi đúng chuỗi và request cố giả mạo header.

`ForwardedHeaderTransformer` không thay thế một trusted-proxy allowlist. Nó xử lý các giá trị được cung cấp theo header contract; việc xác định nguồn nào được phép tạo các giá trị đó phải được giải quyết ở hạ tầng.

## 10. `X-Forwarded-Prefix`: ứng dụng được publish dưới path khác

Một trường hợp phổ biến là proxy công khai một path prefix khác với path backend.

Ví dụ:

```text
Public:
https://example.com/api/orders

Backend:
http://orders-service:8080/orders
```

Proxy có thể gửi:

```http
X-Forwarded-Prefix: /api
```

Transformer dùng prefix để điều chỉnh context path và URL request theo góc nhìn bên ngoài.

Một số kiểu triển khai:

| Mapping | Prefix proxy gửi | Mục đích |
|---|---|---|
| `/api/{path}` → backend `/{path}` | `/api` | Thêm prefix công khai |
| `/app1/{path}` → backend `/{path}` | `/app1` | Giữ prefix ứng dụng |
| `/api/app1/{path}` → backend `/app1/{path}` | `/api/app1` | Thay đổi prefix công khai |
| `/app1/{path}` → public `/{path}` | Prefix rỗng | Loại bỏ prefix nội bộ |

`X-Forwarded-Prefix` không thuộc RFC 7239. Nó là một header quy ước riêng và cần được proxy tạo đúng.

### 10.1. Prefix và route mapping

Không tự nối `X-Forwarded-Prefix` vào mọi controller path. Transformer điều chỉnh request/context path ở tầng framework. Hãy kiểm thử route thực tế với mapping của ứng dụng, đặc biệt khi có:

- `@RequestMapping`
- WebFlux functional routes
- Context path
- Static resource paths
- Redirect
- URL generation

Nếu proxy không rewrite path, không gửi prefix giả định.

## 11. `removeOnly`: xóa forwarded headers mà không sử dụng

Có trường hợp ứng dụng không muốn sử dụng forwarded metadata nhưng vẫn cần loại bỏ các header này để downstream không vô tình đọc chúng.

`ForwardedHeaderTransformer` có thuộc tính:

```java
setRemoveOnly(true)
```

Ví dụ cấu hình Spring Framework:

```java
@Configuration
public class ForwardedHeaderConfiguration {

    @Bean
    public ForwardedHeaderTransformer forwardedHeaderTransformer() {
        ForwardedHeaderTransformer transformer =
                new ForwardedHeaderTransformer();

        transformer.setRemoveOnly(true);

        return transformer;
    }
}
```

Trong chế độ này:

- `Forwarded` và `X-Forwarded-*` được loại bỏ.
- URI không được điều chỉnh theo các header đó.
- Remote/local address không được cập nhật từ forwarded metadata.
- Request tiếp tục với thông tin từ kết nối backend thực tế.

Dùng `removeOnly` khi:

- Backend không cần biết public scheme/host/client IP.
- Muốn bảo đảm code downstream không đọc forwarded headers tùy tiện.
- Proxy chưa được cấu hình đủ tin cậy để sử dụng forwarded metadata.
- Ứng dụng có chính sách xử lý request metadata riêng.

`removeOnly` không xác thực proxy và không ngăn client kết nối trực tiếp. Nó chỉ bỏ qua forwarded values và xóa chúng.

### 11.1. Không bật hai cơ chế xử lý cùng lúc

Nếu dùng Spring Boot `server.forward-headers-strategy=FRAMEWORK`, Boot cấu hình cơ chế Framework. Khi cần tùy biến `removeOnly`, hãy khai báo transformer bean phù hợp và kiểm tra auto-configuration của phiên bản Boot đang dùng để bảo đảm chỉ có một nơi xử lý.

Nếu dùng `NATIVE`, đừng đồng thời để server-native và Spring transformer cùng điều chỉnh request nếu không có thiết kế rõ ràng.

## 12. Ảnh hưởng tới redirect, HTTPS và Spring Security

### 12.1. Redirect cần scheme và host công khai

Nếu backend nhận HTTP nội bộ nhưng client truy cập HTTPS, ứng dụng có thể tạo redirect dựa trên URI đã điều chỉnh:

```text
Client -> https://api.example.com/login
Proxy  -> http://app:8080/login
```

Nếu ứng dụng không biết scheme gốc là HTTPS, redirect có thể trở thành:

```http
Location: http://app:8080/login
```

Sau khi forwarded headers được xử lý đúng, framework có thể tạo URL công khai phù hợp hơn.

### 12.2. Host header ảnh hưởng URL tuyệt đối

Một số chức năng tạo link tuyệt đối hoặc redirect dựa trên host request. Nếu ứng dụng tin `X-Forwarded-Host` tùy tiện, attacker có thể khiến email, redirect hoặc link reset password trỏ tới domain do họ kiểm soát.

Hãy giới hạn host được phép tại proxy/ingress và không dùng forwarded host chưa xác minh để tạo link nhạy cảm.

### 12.3. Spring Security và secure channel

Các chính sách dựa trên scheme/secure request cần nhìn thấy thông tin đã được điều chỉnh đúng. Nếu TLS kết thúc ở proxy, backend có thể nhận HTTP; forwarded transformer giúp WebFlux biết request gốc là HTTPS.

Tuy nhiên, forwarded headers không phải bằng chứng xác thực danh tính client. Không dùng `X-Forwarded-For` để thay thế authentication, authorization hoặc kiểm tra CSRF.

Nếu có Spring Security, kiểm thử cả:

- Redirect HTTPS.
- OAuth2 redirect URI.
- Secure channel policy.
- Cookie Secure.
- Host allowlist.
- Request đi thẳng tới backend với forwarded headers giả.

## 13. `FRAMEWORK` so với `NATIVE` và cách tránh xử lý trùng

| Cấu hình | Thành phần xử lý | Điểm cần chú ý |
|---|---|---|
| `FRAMEWORK` | `ForwardedHeaderTransformer` của Spring WebFlux | Hành vi do Spring Framework quản lý |
| `NATIVE` | Embedded server/connector | Hành vi tùy server và phiên bản |
| `NONE` | Không xử lý forwarded headers | Request giữ metadata của kết nối backend |

Nếu dùng Reactor Netty native forwarded support, server cũng có thể đọc `Forwarded` hoặc `X-Forwarded-*`. Hãy chọn đúng header family mà proxy gửi và đọc tài liệu đúng phiên bản Reactor Netty.

Không nên bật native forwarding rồi lại đăng ký một transformer có cùng trách nhiệm mà không hiểu thứ tự và kết quả biến đổi. Một request có thể bị cập nhật URI hoặc remote address nhiều lần.

Với dự án Spring Boot WebFlux trong bài thực hành, dùng `FRAMEWORK` để thể hiện rõ hành vi của `ForwardedHeaderTransformer`.

## 14. Quan sát request sau khi transform

Controller có thể đọc thông tin request đã được điều chỉnh:

```java
@GetMapping("/request-info")
public Mono<Map<String, Object>> requestInfo(
        ServerWebExchange exchange) {

    ServerHttpRequest request = exchange.getRequest();
    URI uri = request.getURI();

    Map<String, Object> result = new LinkedHashMap<>();
    result.put("scheme", uri.getScheme());
    result.put("host", uri.getHost());
    result.put("port", uri.getPort());
    result.put("path", uri.getRawPath());
    result.put("remoteAddress", request.getRemoteAddress());

    return Mono.just(result);
}
```

Đây là cách quan sát metadata ở application layer. Không trả toàn bộ forwarded headers cho client hoặc log toàn bộ header values.

### Header có còn tồn tại sau transform?

Có thể kiểm tra:

```java
boolean hasForwarded =
        request.getHeaders().containsKey("Forwarded");

boolean hasXForwardedFor =
        request.getHeaders().containsKey("X-Forwarded-For");
```

Nếu transformer đã xử lý, các header tương ứng thường đã bị loại bỏ. Đây là hành vi có chủ đích.

Nếu cần audit raw forwarded headers, hãy ghi lại metadata đã được proxy xác minh tại proxy/access log hoặc một kênh quan sát an toàn trước khi transformer xóa chúng. Không cần giữ nguyên raw values trong controller chỉ để debug.

## 15. Chẩn đoán lỗi thường gặp

### 15.1. Redirect trả HTTP thay vì HTTPS

Kiểm tra:

- Proxy có gửi `X-Forwarded-Proto: https` hoặc `Forwarded: proto=https` không?
- `server.forward-headers-strategy` có đang là `FRAMEWORK` hoặc native strategy phù hợp không?
- Backend có nhận đúng header không?
- Có một proxy khác ghi đè scheme không?
- Có hai tầng cùng xử lý forwarded headers không?

### 15.2. Host trong link là hostname nội bộ

Kiểm tra:

- Proxy có gửi `X-Forwarded-Host` hoặc `Forwarded: host=...` không?
- Host có được ghi đè từ `$host`/public host đã xác minh không?
- Backend có dùng forwarded transformer không?
- Có host allowlist tại proxy hoặc ứng dụng không?

### 15.3. Client IP luôn là IP proxy

Kiểm tra:

- Proxy có gửi `X-Forwarded-For` hoặc `Forwarded: for=...` không?
- Proxy có xóa giá trị client tự gửi trước khi tạo header mới không?
- Framework/native forwarding có được bật không?
- `removeOnly` có đang bật không?
- Controller có đang đọc remote address trước hay sau transformer không?

### 15.4. IP client có thể bị giả mạo

Nếu client có thể kết nối trực tiếp tới backend hoặc edge proxy chỉ append header, IP forwarded không đáng tin.

Sửa ở trust boundary:

1. Chặn đường truy cập trực tiếp tới backend.
2. Xóa forwarded headers do client gửi.
3. Tạo lại metadata từ kết nối đã xác minh.
4. Cấu hình chuỗi proxy và real-IP policy rõ ràng.
5. Kiểm thử request giả mạo từ ngoài.

### 15.5. Route bị sai khi có prefix

Kiểm tra:

- Proxy có rewrite path hay không?
- `X-Forwarded-Prefix` có khớp public path không?
- Prefix có bị gửi lặp không?
- Context path của ứng dụng có đang được cấu hình độc lập không?
- Có transformer/native support xử lý prefix hai lần không?

### 15.6. Forwarded headers không bị xóa

Kiểm tra:

- Transformer có được phát hiện với bean name `forwardedHeaderTransformer` không?
- Boot strategy có phải `FRAMEWORK` không?
- Có đang dùng native strategy thay vì Framework không?
- Request có đi qua WebFlux `WebHttpHandlerBuilder` được cấu hình đúng không?

## 16. Dự án Java 17+ chạy được: ForwardedHeaderTransformer với WebTestClient

Dự án mẫu sử dụng:

- Java 17.
- Spring Boot 3.3.5.
- Spring WebFlux.
- JUnit 5 và Spring Test.
- `WebTestClient` để gửi request có forwarded headers.

Spring Boot 3.3.5 quản lý Spring Framework 6.1.14. Vì vậy ví dụ dùng constructor không tham số của `ForwardedHeaderTransformer` và `setRemoveOnly(boolean)`, tương thích với phiên bản này.

Dự án kiểm tra ba hành vi:

1. `Forwarded` chuẩn thay đổi scheme, host và port của request.
2. `X-Forwarded-*` cũng có thể thay đổi metadata khi không có `Forwarded`.
3. `removeOnly` xóa forwarded headers nhưng giữ nguyên URI nội bộ.

### 16.1. Cấu trúc dự án

```text
forwarded-headers-webflux/
├── pom.xml
└── src/
    ├── main/java/edu/demo/forwarded/
    │   ├── ForwardedApplication.java
    │   ├── RequestInfo.java
    │   └── RequestInfoController.java
    └── test/java/edu/demo/forwarded/
        ├── ForwardedHeadersIntegrationTests.java
        └── ForwardedHeaderTransformerTests.java
```

### 16.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>edu.demo</groupId>
    <artifactId>forwarded-headers-webflux</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

### 16.3. `application.properties`

```properties
server.forward-headers-strategy=FRAMEWORK
```

Cấu hình này yêu cầu Spring Boot sử dụng cơ chế forwarded headers của Spring Framework cho WebFlux.

### 16.4. `ForwardedApplication.java`

```java
package edu.demo.forwarded;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ForwardedApplication {

    public static void main(String[] args) {
        SpringApplication.run(ForwardedApplication.class, args);
    }
}
```

### 16.5. `RequestInfo.java`

```java
package edu.demo.forwarded;

public record RequestInfo(
        String scheme,
        String host,
        int port,
        String path,
        String remoteAddress,
        boolean forwardedHeadersPresent) {
}
```

Record biểu diễn thông tin request sau khi WebFlux xử lý forwarded headers.

### 16.6. `RequestInfoController.java`

```java
package edu.demo.forwarded;

import java.net.InetSocketAddress;
import java.net.URI;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.http.server.reactive.ServerHttpRequest;

import reactor.core.publisher.Mono;

@RestController
public class RequestInfoController {

    @GetMapping("/inspect")
    public Mono<RequestInfo> inspect(ServerWebExchange exchange) {
        ServerHttpRequest request = exchange.getRequest();
        URI uri = request.getURI();

        InetSocketAddress remote = request.getRemoteAddress();

        String remoteAddress =
                remote == null ? null : remote.getHostString();

        boolean forwardedHeadersPresent =
                request.getHeaders().containsKey("Forwarded")
                || request.getHeaders().containsKey("X-Forwarded-For")
                || request.getHeaders().containsKey("X-Forwarded-Host")
                || request.getHeaders().containsKey("X-Forwarded-Proto")
                || request.getHeaders().containsKey("X-Forwarded-Port")
                || request.getHeaders().containsKey("X-Forwarded-Prefix");

        RequestInfo info = new RequestInfo(
                uri.getScheme(),
                uri.getHost(),
                uri.getPort(),
                uri.getRawPath(),
                remoteAddress,
                forwardedHeadersPresent);

        return Mono.just(info);
    }
}
```

Controller đọc URI và remote address đã được WebFlux điều chỉnh. `forwardedHeadersPresent` giúp test xác nhận transformer đã loại bỏ các header được xử lý.

### 16.7. `ForwardedHeadersIntegrationTests.java`

```java
package edu.demo.forwarded;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = "server.forward-headers-strategy=FRAMEWORK")
@AutoConfigureWebTestClient
class ForwardedHeadersIntegrationTests {

    @Autowired
    WebTestClient client;

    @Test
    void standardForwardedHeaderReconstructsPublicRequest() {
        client.get()
                .uri("/inspect")
                .header(
                        "Forwarded",
                        "for=192.0.2.60;proto=https;host=api.example.test:443")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.scheme").isEqualTo("https")
                .jsonPath("$.host").isEqualTo("api.example.test")
                .jsonPath("$.port").isEqualTo(443)
                .jsonPath("$.path").isEqualTo("/inspect")
                .jsonPath("$.forwardedHeadersPresent").isEqualTo(false);
    }

    @Test
    void xForwardedHeadersReconstructPublicRequest() {
        client.get()
                .uri("/inspect")
                .header("X-Forwarded-For", "192.0.2.61")
                .header("X-Forwarded-Host", "portal.example.test")
                .header("X-Forwarded-Proto", "https")
                .header("X-Forwarded-Port", "443")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.scheme").isEqualTo("https")
                .jsonPath("$.host").isEqualTo("portal.example.test")
                .jsonPath("$.port").isEqualTo(443)
                .jsonPath("$.forwardedHeadersPresent").isEqualTo(false);
    }
}
```

Hai test này gửi forwarded headers trực tiếp để xác nhận hành vi của transformer. Trong production, chỉ bật chế độ sử dụng headers khi request đến từ proxy đáng tin cậy và proxy đã làm sạch dữ liệu do client cung cấp.

### 16.8. `ForwardedHeaderTransformerTests.java`

```java
package edu.demo.forwarded;

import org.junit.jupiter.api.Test;

import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.web.server.adapter.ForwardedHeaderTransformer;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;

class ForwardedHeaderTransformerTests {

    @Test
    void removeOnlyDiscardsHeadersWithoutChangingRequestUri() {
        ServerHttpRequest original =
                MockServerHttpRequest
                        .get("http://internal.example:8080/inspect")
                        .header("X-Forwarded-Proto", "https")
                        .header("X-Forwarded-Host", "public.example.test")
                        .build();

        ForwardedHeaderTransformer transformer =
                new ForwardedHeaderTransformer();

        transformer.setRemoveOnly(true);

        ServerHttpRequest transformed =
                transformer.apply(original);

        assertEquals(
                "http",
                transformed.getURI().getScheme());

        assertEquals(
                "internal.example",
                transformed.getURI().getHost());

        assertEquals(
                8080,
                transformed.getURI().getPort());

        assertFalse(
                transformed.getHeaders()
                        .containsKey("X-Forwarded-Proto"));

        assertFalse(
                transformed.getHeaders()
                        .containsKey("X-Forwarded-Host"));
    }
}
```

Test này xác nhận `removeOnly` giữ nguyên URI nội bộ và loại bỏ các header được gửi vào.

### 16.9. Chạy test

Từ thư mục có `pom.xml`:

```bash
mvn test
```

Khi Maven tải được dependencies và assertion đúng, bộ test có ba trường hợp:

1. RFC 7239 `Forwarded` thay đổi scheme/host/port và header được xóa.
2. `X-Forwarded-*` thay đổi scheme/host/port và header được xóa.
3. `removeOnly` loại bỏ header nhưng giữ nguyên scheme/host/port ban đầu.

Kết quả mong đợi:

```text
Tests run: 3, Failures: 0, Errors: 0, Skipped: 0
```

Đây là kết quả cần đối chiếu sau khi chạy Maven; tài liệu không tuyên bố đã thực thi test trong môi trường biên soạn.

## 17. Những lỗi thường gặp và cách sửa

| Lỗi | Hậu quả | Cách sửa |
|---|---|---|
| Tin mọi `X-Forwarded-For` từ client | Client giả mạo IP | Edge proxy xóa giá trị ngoài và tạo lại |
| Chỉ xóa `X-Forwarded-*` mà bỏ `Forwarded` | Header chuẩn vẫn có thể bị giả mạo | Xử lý cả hai họ header |
| Proxy chỉ append vào XFF có sẵn | Giá trị client giả vẫn nằm trong chuỗi | Sanitize ở trust boundary trước khi append |
| Expose trực tiếp backend | Client bỏ qua proxy và gửi forwarded header giả | Firewall, security group hoặc NetworkPolicy |
| Dùng `ForwardedHeaderFilter` trong WebFlux | Sai abstraction stack | Dùng `ForwardedHeaderTransformer` |
| Đăng ký bean sai tên | WebFlux không tự phát hiện transformer | Dùng tên `forwardedHeaderTransformer` |
| Đặt transformer thành `WebFilter` | Xử lý quá muộn so với exchange creation | Dùng transformer ở WebHttpHandlerBuilder |
| Không cấu hình forward strategy trong Boot | URI vẫn là host/scheme nội bộ | Dùng `FRAMEWORK` hoặc native strategy phù hợp |
| Bật native và Framework cùng lúc | Request có thể bị điều chỉnh hai lần | Chọn một cơ chế |
| Dùng `removeOnly` nhưng mong scheme thành HTTPS | Header bị xóa và không được sử dụng | Chỉ dùng removeOnly khi muốn bỏ qua metadata |
| Đọc XFF trong controller sau transform | Header có thể đã bị xóa | Đọc `getRemoteAddress()` đã điều chỉnh |
| Dùng remote address đã transform để xác thực proxy | Địa chỉ có thể là client IP forwarded | Kiểm tra peer ở tầng mạng/proxy |
| Tin `X-Forwarded-Host` để tạo link tùy ý | Host header poisoning, link giả mạo | Host allowlist và proxy overwrite |
| Không xử lý path prefix | Link và context path sai | Cấu hình `X-Forwarded-Prefix` đúng contract |
| Cho phép nhiều proxy append không kiểm soát | Chuỗi client IP có thể bị giả mạo | Định nghĩa trusted proxy chain |
| Tự parse Forwarded bằng split | Xử lý sai quoting, IPv6 và nhiều hop | Dùng Spring transformer/parser |
| Cho rằng transformer xác thực proxy | Sai mô hình bảo mật | Proxy/network layer phải xác định trust |

## 18. Checklist production

### Proxy và network boundary

- Backend chỉ nhận traffic từ proxy/ingress được phép.
- Không có đường truy cập trực tiếp từ Internet tới backend.
- Proxy đầu tiên xóa `Forwarded` và toàn bộ `X-Forwarded-*` do client gửi.
- Proxy tạo lại host, proto, port và client address từ metadata đã xác minh.
- Chuỗi nhiều proxy có quy tắc append/overwrite rõ ràng.
- Host công khai nằm trong allowlist.
- Prefix chỉ được gửi khi proxy thực sự rewrite path.

### Spring WebFlux

- Dùng `ForwardedHeaderTransformer` cho reactive stack.
- Transformer được đăng ký đúng tên nếu tự cấu hình bean.
- `server.forward-headers-strategy` phù hợp với môi trường.
- Chỉ một tầng xử lý forwarded headers.
- `removeOnly` được chọn đúng mục tiêu.
- Controller đọc URI/remote address đã được điều chỉnh.
- Không dựa vào raw forwarded header sau khi transformer đã xóa.

### Security và ứng dụng

- Không dùng forwarded IP làm authentication.
- Không dùng IP đã transform để xác định proxy peer.
- Redirect và absolute URL dùng host đã được kiểm soát.
- OAuth2 redirect URI không lấy từ host tùy ý.
- HTTPS policy được test sau TLS termination.
- Log không ghi raw headers chứa dữ liệu nhạy cảm.
- Rate limit theo IP có trust policy cho proxy chain.

### Testing và vận hành

- Test `Forwarded` chuẩn.
- Test `X-Forwarded-*`.
- Test header bị xóa sau transform.
- Test `removeOnly`.
- Test request không có forwarded headers.
- Test path prefix nếu deployment có rewrite.
- Test request giả mạo đi thẳng tới backend.
- Có log/metrics từ proxy để đối chiếu với thông tin request ở ứng dụng.

## 19. Bài tập tự kiểm tra

**Bài 1.** Vì sao backend thấy `http://orders-service:8080` dù client truy cập HTTPS?

**Đáp án:** Proxy kết thúc TLS rồi chuyển tiếp bằng HTTP tới backend. Nếu không có forwarded metadata, backend chỉ thấy kết nối nội bộ.

**Bài 2.** `Forwarded` và `X-Forwarded-Proto` khác nhau thế nào?

**Đáp án:** `Forwarded` là header chuẩn RFC 7239 chứa các thuộc tính `for`, `by`, `host`, `proto`; `X-Forwarded-Proto` là header quy ước riêng để truyền scheme.

**Bài 3.** `ForwardedHeaderTransformer` có xác thực proxy gửi header không?

**Đáp án:** Không. Nó xử lý giá trị header. Proxy và network boundary phải bảo đảm chỉ proxy đáng tin mới có thể tạo forwarded metadata được ứng dụng sử dụng.

**Bài 4.** Vì sao proxy biên cần xóa cả `Forwarded` và `X-Forwarded-*`?

**Đáp án:** Client có thể gửi một hoặc cả hai họ. Nếu chỉ xóa một họ, ứng dụng có thể nhận dữ liệu giả từ họ còn lại.

**Bài 5.** `server.forward-headers-strategy=FRAMEWORK` có ý nghĩa gì với WebFlux?

**Đáp án:** Yêu cầu Spring Boot dùng cơ chế xử lý forwarded headers của Spring Framework, trong reactive stack là `ForwardedHeaderTransformer`.

**Bài 6.** `removeOnly=true` làm gì?

**Đáp án:** Xóa forwarded headers nhưng không dùng chúng để thay đổi URI hoặc địa chỉ request.

**Bài 7.** Vì sao không nên dùng `getRemoteAddress()` sau transform để kiểm tra proxy nào kết nối trực tiếp?

**Đáp án:** Transformer có thể cập nhật remote address từ `for`/`X-Forwarded-For` thành địa chỉ client. Địa chỉ peer TCP thật cần được kiểm tra ở tầng network/server trước khi tin forwarded data.

**Bài 8.** `X-Forwarded-Prefix` dùng cho trường hợp nào?

**Đáp án:** Proxy public một path prefix khác với path backend, và cần thông báo prefix công khai để framework tạo URL/context path đúng.

**Bài 9.** Vì sao `$proxy_add_x_forwarded_for` có thể nguy hiểm ở edge proxy?

**Đáp án:** Nó nối địa chỉ mới vào header hiện có. Nếu giá trị hiện có do client gửi và chưa được làm sạch, chuỗi vẫn chứa địa chỉ giả mạo.

**Bài 10.** Nên chọn `FRAMEWORK` hay `NATIVE`?

**Đáp án:** Chọn theo embedded server và nhu cầu kiểm soát. `FRAMEWORK` dùng transformer Spring; `NATIVE` dùng cơ chế server. Tránh bật cả hai cùng xử lý một request.

## 20. Ghi nhớ

- Proxy thay đổi scheme, host, port, remote address và đôi khi cả path khi chuyển tiếp request.
- `Forwarded` là header chuẩn RFC 7239; `X-Forwarded-*` là nhóm header quy ước phổ biến.
- `ForwardedHeaderTransformer` xử lý forwarded metadata trước khi tạo `ServerWebExchange`, điều chỉnh request và xóa các header đã dùng.
- Trong WebFlux, dùng `ForwardedHeaderTransformer`; `ForwardedHeaderFilter` thuộc Servlet stack.
- WebFlux tự phát hiện bean tên `forwardedHeaderTransformer`.
- Spring Boot có `FRAMEWORK`, `NATIVE` và `NONE`; chỉ nên có một tầng xử lý.
- `removeOnly=true` xóa header và bỏ qua metadata.
- Transformer không xác thực nguồn proxy và không thay thế trusted-proxy policy.
- Edge proxy phải xóa forwarded headers do client gửi rồi tạo lại metadata đã xác minh.
- Backend nên chỉ nhận kết nối từ proxy đáng tin.
- Remote address sau transform có thể là client IP; không dùng nó để xác định TCP peer.
- Host, scheme và prefix được forwarded có thể ảnh hưởng redirect, URL tuyệt đối, OAuth2 và security policy.
- Nhiều proxy cần một quy tắc chain rõ ràng; không tin XFF chỉ vì phần tử đầu tiên có vẻ hợp lệ.

Khi cấu hình forwarded headers, hãy trả lời ba câu hỏi: **proxy nào được phép tạo metadata, proxy đã loại bỏ dữ liệu client gửi chưa, và ứng dụng đang xử lý forwarded headers ở đúng một tầng hay chưa?**

## Tài liệu chính thức

- Spring Framework 6.2, **WebFlux Reactive Core – Forwarded Headers and Security Considerations**: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/reactive-spring.html
- Spring Framework 6.1, **`ForwardedHeaderTransformer` API**: https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/web/server/adapter/ForwardedHeaderTransformer.html
- Spring Framework 6.1, **`ForwardedHeaderUtils` API**: https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/web/util/ForwardedHeaderUtils.html
- Spring Boot 3.3, **Running Behind a Front-end Proxy Server**: https://docs.spring.io/spring-boot/3.3/reference/howto.html
- Spring Boot 3.3, **`ServerProperties.ForwardHeadersStrategy` API**: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/web/ServerProperties.ForwardHeadersStrategy.html
- IETF, **RFC 7239 – Forwarded HTTP Extension**: https://www.rfc-editor.org/rfc/rfc7239
- Spring Framework 6.1, **`MockServerHttpRequest` API**: https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/mock/http/server/reactive/MockServerHttpRequest.html
- Spring Framework 6.2, **WebTestClient**: https://docs.spring.io/spring-framework/reference/6.2/testing/webtestclient.html