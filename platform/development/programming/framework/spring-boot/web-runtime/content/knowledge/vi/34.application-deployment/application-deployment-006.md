# Reverse proxy, ingress và đường dẫn công khai khi có context path

**Module:** Spring Boot - web-runtime  
**Chủ đề cha:** Triển khai ứng dụng

## 1. Vì sao API chạy đúng trong container nhưng sai khi ra Internet?

Giả sử một ứng dụng Spring Boot chạy tại địa chỉ nội bộ:

~~~text
http://catalog-service:8080/api/items/42
~~~

Người dùng chỉ được sử dụng URL công khai:

~~~text
https://api.example.test/shop/api/items/42
~~~

Reverse proxy, API gateway hoặc Kubernetes Ingress có thể kết thúc TLS, đổi host/port và thay đổi đường dẫn. Một request GET có thể đi đúng tới controller và trả 200, nhưng response 201 Created lại chứa header Location như sau:

~~~http
HTTP/1.1 201 Created
Location: http://catalog-service:8080/api/items/43
~~~

URL này lộ hostname nội bộ, thiếu HTTPS và thiếu phần **/shop**. Client bên ngoài có thể không mở được; trình duyệt có thể chặn nội dung HTTP trong trang HTTPS. Lỗi tương tự xuất hiện trong redirect 302, self links, HATEOAS, OAuth2 callback, Swagger UI hoặc đường dẫn CSS/JavaScript.

Đôi khi URL lại bị nhân đôi:

~~~text
https://api.example.test/shop/shop/api/items/42
~~~

Hoặc trả 404 dù controller tồn tại, vì proxy đã strip **/shop** trong khi Tomcat vẫn chạy với **server.servlet.context-path=/shop**.

**Hai vấn đề cần giải riêng:**

1. **Inbound routing:** proxy gửi path nào vào backend? Servlet context path và @RequestMapping có match không?
2. **Outbound URL generation:** khi xây Location, redirect và links, backend dùng public scheme, host, port và prefix nào?

Một ứng dụng có thể đúng ở câu 1 nhưng sai ở câu 2. Bài này giải thích cách cấu hình nhất quán và cách xác minh cả hai.

### Mục tiêu học tập

Sau bài, bạn có thể:

- Phân biệt public URL, upstream URL, Servlet context path, Spring MVC mapping và Ingress path.
- So sánh proxy **preserve**, **strip** và **replace** path prefix.
- Dùng đúng **server.servlet.context-path** và tránh cộng trùng prefix trong controller.
- Hiểu **Forwarded**, **X-Forwarded-Host**, **X-Forwarded-Proto**, **X-Forwarded-Port**, **X-Forwarded-Prefix**, **X-Forwarded-For**.
- Chọn **server.forward-headers-strategy=none/native/framework** theo topology.
- Hiểu sự khác biệt của **proxy_pass** có/không có URI trailing slash và ingress-nginx rewrite-target.
- Viết ứng dụng **Spring Boot 3.3 / Java 17+** tạo URI bằng **ServletUriComponentsBuilder**.
- Kiểm GET links, POST **201 Location**, redirect **302 Location** qua HTTP thật và qua proxy.
- Đánh giá Host-header poisoning, OAuth2 redirects, cookies, static assets, CORS, Actuator và probes.
- Xây checklist deployment có thể dùng khi chuyển ứng dụng sang Kubernetes.

## 2. Mô hình các URL tại từng hop

Một request có thể trải qua:

~~~text
Browser:
  https://api.example.test/shop/api/items/42
       |
       v
Ingress / Nginx / Load balancer
  TLS: HTTPS -> backend HTTP
  Host: api.example.test -> catalog-service
  Prefix: maybe preserve/strip/replace /shop
       |
       v
Spring Boot / embedded Tomcat :8080
  Servlet context path
       |
       v
DispatcherServlet + @RequestMapping("/api/items")
  GET /{id}
       |
       v
Response: body JSON, Location, redirect, links
       |
       v
Proxy -> Browser
~~~

Các khái niệm:

| Khái niệm | Ví dụ | Ai chịu trách nhiệm? |
| --- | --- | --- |
| Public origin | https://api.example.test | DNS, TLS và proxy public. |
| Public path | /shop/api/items/42 | Public routing contract. |
| Upstream origin | http://catalog-service:8080 | Internal service/network. |
| Upstream request path | /api/items/42 hoặc /shop/api/items/42 | Proxy rewrite configuration. |
| Servlet context path | rỗng, /shop hoặc /internal | Spring Boot server.servlet.context-path. |
| MVC handler mapping | /api/items/{id} | @RequestMapping/@GetMapping. |
| Forwarded prefix | /shop | Trusted proxy metadata phục vụ effective URL. |
| Generated public URL | https://api.example.test/shop/api/items/43 | Spring URI builder, redirect, HATEOAS, v.v. |

**Servlet context path không phải một chuỗi tự động được cộng vào mọi URL mà proxy gửi.** Nó quyết định vị trí application được mount tại Servlet container. Nếu backend có context path **/shop**, request trực tiếp phải chứa /shop trước MVC mapping. Nếu backend chạy root context, /shop là concern của proxy hoặc client-facing link building.

Để sửa lỗi, luôn viết ra phương trình:

~~~text
Public path -> Proxy rewrite -> Upstream path
Upstream path - Servlet context path -> MVC mapping
Generated public origin/prefix -> Link, Location, redirect
~~~

Nếu phương trình này không khớp ở một hop, cấu hình có thể gây 404, redirect loop hoặc host/path sai.

## 3. Ba phương án triển khai thường gặp

Giả sử client cần truy cập **/shop/api/items/42** còn MVC handler mapping là **/api/items/{id}**.

| Phương án | Public path | Path backend nhận | Context path backend | Metadata X-Forwarded-Prefix |
| --- | --- | --- | --- | --- |
| **Preserve** | /shop/api/items/42 | /shop/api/items/42 | /shop | Không bắt buộc; host/proto vẫn cần nếu public khác backend. |
| **Strip** | /shop/api/items/42 | /api/items/42 | rỗng | /shop khi cần generated public URLs. |
| **Replace** | /shop/api/items/42 | /internal/api/items/42 | /internal | /shop để phản ánh prefix public thay cho internal. |

### Preserve path

Backend mount đúng **/shop**:

~~~properties
server.servlet.context-path=/shop
~~~

Proxy giữ nguyên path. Handler **@GetMapping("/api/items/{id}")** hoạt động dưới /shop. Khi host/proto public khác backend, dùng trusted forwarded headers để sinh URI đúng scheme/host.

### Strip path

Backend mount root (không cấu hình context path). Proxy cắt /shop, gửi /api/items/42. Để server tạo public link chứa /shop, proxy thêm **X-Forwarded-Prefix: /shop** và Boot xử lý bằng framework strategy.

### Replace path

Backend legacy mount **/internal**; proxy đổi /shop thành /internal, đồng thời cho server biết public prefix /shop. Với Spring Framework xử lý X-Forwarded-Prefix đúng, generated links nên phản ánh /shop thay vì /internal.

**Không tự cộng /shop vào từng @RequestMapping**, nếu /shop đã được Servlet container mount. Không thêm context path chỉ vì client nhìn thấy /shop khi proxy đã strip nó. **X-Forwarded-Prefix không làm Servlet container tự tạo một context path**, mà diễn đạt góc nhìn bên ngoài để các URI builders phản ánh public path.

## 4. server.servlet.context-path và các loại base path khác

Ví dụ:

~~~properties
server.port=8080
server.servlet.context-path=/shop
~~~

Controller:

~~~java
@RestController
@RequestMapping("/api/items")
class ItemController {
    @GetMapping("/{id}")
    public String get(@PathVariable long id) {
        return "item:" + id;
    }
}
~~~

Đây là snippet minh họa, không phải class trong demo chính phía sau. Request trực tiếp đúng là:

~~~text
GET http://localhost:8080/shop/api/items/42
~~~

Request **GET http://localhost:8080/api/items/42** không vào cùng context. Đừng nhầm với:

- **spring.mvc.servlet.path**: prefix mapping của DispatcherServlet, là tầng khác Servlet context path.
- **management.endpoints.web.base-path**: đường dẫn Actuator (mặc định /actuator).
- **management.server.base-path**: base path khi management server chạy port riêng.
- **spring.webflux.base-path**: base path của WebFlux reactive stack, không tương đương Servlet context path.
- **Ingress path**: quy tắc định tuyến ở ingress controller, có thể rewrite hoặc không.
- **Frontend base URL/HTML base href**: ảnh hưởng browser routes/assets; không tự được sửa bằng servlet context path.

Nếu bạn đặt cùng /shop vào Servlet context, DispatcherServlet path và cả @RequestMapping, URL có thể bị nhân prefix nhiều lần.

**Actuator cùng port:** khi management endpoints dùng cùng servlet listener, default /actuator tương đối với servlet context path. Ví dụ backend context /shop → đường trực tiếp thường là **/shop/actuator/health** nếu health được expose.

**Actuator khác port:** khi có **management.server.port** riêng, management.endpoints.web.base-path tính theo management.server.base-path, không tự lấy main servlet context path. Health probe phải kiểm đúng port/path backend, khác URL public qua ingress.

## 5. Forwarded headers giúp backend hiểu góc nhìn của client

Proxy có thể truyền thông tin chuẩn RFC 7239:

~~~http
Forwarded: proto=https;host=api.example.test
~~~

Hoặc các headers de facto:

~~~http
X-Forwarded-Host: api.example.test
X-Forwarded-Proto: https
X-Forwarded-Port: 443
X-Forwarded-Prefix: /shop
X-Forwarded-For: 203.0.113.8
~~~

| Header | Ý nghĩa | Lỗi khi thiếu hoặc sai |
| --- | --- | --- |
| **Forwarded** | Host/proto/for/by gốc, theo RFC 7239. | Server không nhận biết public origin khi proxy thay đổi. |
| **X-Forwarded-Host** | Public hostname, có thể kèm port. | Link dùng catalog-service hoặc 127.0.0.1. |
| **X-Forwarded-Proto** | Public http/https scheme. | Redirect về http dù browser dùng HTTPS. |
| **X-Forwarded-Port** | Public port, ví dụ 443. | Link lộ :8080 hoặc không đúng public port. |
| **X-Forwarded-Prefix** | Public path prefix, ví dụ /shop. | Link thiếu /shop sau khi proxy strip. |
| **X-Forwarded-For** | Client và proxy IP chain. | Server thấy địa chỉ proxy thay vì client; dễ giả nếu không sanitize. |

**X-Forwarded-Prefix phải chứa path prefix, không phải full URL.** Ví dụ chính xác là /shop, không phải https://api.example.test/shop. Nó cũng không thay đổi path mà reverse proxy đã gửi vào container; request routing và generated URI là hai công việc khác nhau.

Một số proxy viết header **Forwarded** chuẩn, một số viết X-Forwarded-*. Không nên để hai dạng mang giá trị host/proto mâu thuẫn. Phải xác định tầng nào được quyền ghi đè và Spring/container chọn loại nào.

### Vấn đề bảo mật

Client Internet cũng có thể tự gửi X-Forwarded-Host và X-Forwarded-Prefix giả. Spring không biết header đó do trusted proxy thêm hay do attacker gửi. Chỉ bật interpretation khi:

1. Edge proxy **xóa toàn bộ Forwarded/X-Forwarded-*** do client công khai gửi.
2. Edge hoặc trusted hop **ghi lại giá trị đúng** theo virtual host/TLS/route được kiểm soát.
3. Backend chỉ nhận traffic từ trusted proxy/network; không lộ raw application port ra Internet.
4. Có allowlist public host hoặc fixed public origin khi dịch vụ chỉ dùng một domain.
5. Có test spoofed headers qua public edge để bảo đảm Location/self không bị thay.

Nếu không, attacker có thể gây **host-header poisoning**, open redirect hoặc sinh links độc hại trong login, email, password reset và JSON response. **ForwardedHeaderFilter không thay thế bước loại bỏ headers giả tại edge.**

## 6. Ba chế độ server.forward-headers-strategy

Spring Boot 3.3 hỗ trợ:

~~~properties
server.forward-headers-strategy=framework
~~~

Các giá trị:

| Strategy | Cơ chế | Khi sử dụng |
| --- | --- | --- |
| **none** | Boot không áp dụng forwarded headers strategy. | Không có trusted proxy, hoặc public URL xử lý bằng cấu hình riêng. |
| **native** | Giao cho web server/container như Tomcat RemoteIpValve. | Dùng native scheme/host/client IP behavior và đã kiểm các headers nó hỗ trợ. |
| **framework** | Servlet MVC dùng **ForwardedHeaderFilter**; reactive WebFlux dùng **ForwardedHeaderTransformer**. | Thường phù hợp khi cần X-Forwarded-Prefix và URL/redirect generation qua proxy. |

**Boot 3.3 docs** cho biết native đủ cho các thông tin phổ biến như X-Forwarded-For/Proto với proxy phù hợp. Nếu cần xử lý thêm, đặc biệt prefix, framework thường là phương án thực tiễn. Không khẳng định native xử lý X-Forwarded-Prefix giống nhau trên Tomcat/Jetty/Undertow/Reactor Netty; phải test trên container thật.

**Mặc định strategy tùy cloud platform được Boot nhận biết**. Trong một số môi trường cloud nó có thể chọn native; ở nơi khác none. Đừng trông cậy vào default vô hình khi public prefix quan trọng: đặt rõ và kiểm actual behavior.

### Cơ chế của ForwardedHeaderFilter

Trong Servlet stack, filter wrap request/response để **getScheme()**, **getServerName()**, **getServerPort()**, effective context path/request URI và redirect URL được diễn giải từ forwarded metadata. Sau đó URI builders như **ServletUriComponentsBuilder** hoặc **WebMvcLinkBuilder** có thể tạo link theo public origin/prefix.

**Không tự khai báo thêm một ForwardedHeaderFilter bean** chỉ vì đã đặt framework strategy. Boot có auto-configuration. Double registration/filter order sai có thể làm behavior khó xác định. Nếu tự đăng ký filter hoặc removeOnly mode, phải hiểu ordering, REQUEST/ASYNC/ERROR dispatch và trust policy.

### Trường hợp Tomcat redirect context root

Tài liệu Spring Boot 3.3 nêu khi TLS được terminate ở front proxy, nên kiểm:

~~~properties
server.tomcat.redirect-context-root=false
~~~

Cấu hình giúp **X-Forwarded-Proto** được xử lý trước khi Tomcat redirect đường context root để thêm dấu **/**. Nếu không, request HTTPS tới **/shop** có thể bị redirect tới **http://.../shop/** không đúng public scheme.

**Đây là property liên quan Tomcat**, không thay server.servlet.context-path, không tự sửa rewrite và không thay yêu cầu TLS ở edge.

## 7. Nginx preserve prefix: chú ý proxy_pass không có slash cuối

Giả sử ứng dụng chạy backend với:

~~~properties
server.servlet.context-path=/shop
server.forward-headers-strategy=framework
server.tomcat.redirect-context-root=false
~~~

Một Nginx server block **chỉ dùng trong local lab**:

~~~nginx
server {
    listen 8088;
    server_name localhost;

    location = /shop {
        return 308 /shop/;
    }

    location /shop/ {
        # Chi co upstream host:port, khong co URI trailing slash.
        proxy_pass http://127.0.0.1:8080;

        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Port $server_port;
        proxy_set_header X-Forwarded-For $remote_addr;
    }
}
~~~

Trong layout này, **http://localhost:8088/shop/api/items/42** tới backend dưới path **/shop/api/items/42**. Controller mapping **/api/items/{id}** vẫn đúng vì Servlet context path là /shop.

Không cần cố tình thêm X-Forwarded-Prefix ở kiểu preserve khi backend đã nhận cùng prefix; nếu ingress thật tự tạo header ấy, phải test interaction thay vì thêm prefix thủ công lần nữa.

**Đây không phải production TLS configuration.** Ở môi trường public cần HTTPS certificate, allowlisted Host và edge sanitation. Biến Nginx **$host** ở lab phụ thuộc inbound Host; production không được coi mọi Host từ Internet là public canonical hostname.

## 8. Nginx strip prefix: proxy_pass có slash cuối

Ứng dụng backend root context:

~~~properties
# Khong dat server.servlet.context-path=/shop.
server.forward-headers-strategy=framework
~~~

Local Nginx server block:

~~~nginx
server {
    listen 8088;
    server_name localhost;

    location = /shop {
        return 308 /shop/;
    }

    location /shop/ {
        # URI "/" thay prefix matching /shop/.
        proxy_pass http://127.0.0.1:8080/;

        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Port $server_port;
        proxy_set_header X-Forwarded-Prefix /shop;
        proxy_set_header X-Forwarded-For $remote_addr;
    }
}
~~~

Ở đây, request **/shop/api/items/42** được chuyển thành **/api/items/42** cho backend. Trong hai snippets cố định trên, dấu **/** cuối **proxy_pass** chính là điểm khác biệt quan trọng: có URI **/** thì Nginx thay matched location prefix bằng **/**; không có URI thì thông thường giữ path gốc.

**Quy tắc này phụ thuộc cấu hình.** Nếu Nginx dùng regex location, variables, rewrite directives hoặc proxy_pass URI dạng khác, semantics có thể thay đổi. Luôn test upstream request path thật, đừng áp quy tắc trailing slash của hai snippets cho mọi trường hợp.

Generated link thông qua effective request context có thể trở thành:

~~~text
http://localhost:8088/shop/api/items/42
~~~

với Nginx lab local ở HTTP port 8088. Trên public ingress HTTPS đúng cấu hình, scheme/host/port public phải tương ứng:

~~~text
https://api.example.test/shop/api/items/42
~~~

### Bẫy: dùng context path=/shop nhưng proxy đã strip

Nếu Nginx gửi **/api/items/42** trong khi Servlet application mount ở **/shop**, server sẽ trả 404 trước khi controller match. Thêm X-Forwarded-Prefix=/shop chỉ giúp URL generation, **không tự thay backend servlet context path**. Phải chọn hoặc preserve path, hoặc để context root trong kiểu strip.

## 9. Khi public prefix khác internal context path

Legacy application deploy với:

~~~properties
server.servlet.context-path=/internal
server.forward-headers-strategy=framework
~~~

Nhưng public URL bắt buộc dùng /shop:

~~~text
Public:   https://api.example.test/shop/api/items/42
Upstream: http://catalog-service:8080/internal/api/items/42
Header:   X-Forwarded-Prefix: /shop
~~~

Proxy phải **rewrite /shop thành /internal** khi gửi request backend để Servlet routing đúng. Header X-Forwarded-Prefix nói cho app biết prefix công khai khi sinh links. Với Spring Framework xử lý forwarded prefix thích hợp, generated URLs cần phản ánh /shop chứ không phải /internal.

Đừng tự tạo URL bằng cách ghép **/shop + /internal + /api/items**. Hãy dùng URI builders dựa trên effective request context và test qua public ingress. Cách này hợp với ứng dụng legacy, nhưng phức tạp hơn preserve hoặc strip, nên cần contract tests cho Location, redirects và assets.

## 10. Kubernetes Ingress: path matching không phải rewrite

**Ingress API chuẩn** quy định host/path routing và backend Service. Nó không quy định mọi cách rewrite hoặc việc sinh X-Forwarded-Prefix. Nhiều annotation chỉ có ý nghĩa đối với **một controller cụ thể**.

### 10.1. Ingress preserve path

Snippet Ingress:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: catalog-preserve
spec:
  ingressClassName: nginx
  rules:
    - host: api.example.test
      http:
        paths:
          - path: /shop
            pathType: Prefix
            backend:
              service:
                name: catalog-svc
                port:
                  number: 8080
~~~

Nếu controller chuyển nguyên path, backend phải phục vụ **/shop/api/items/42**, thường bằng **server.servlet.context-path=/shop**.

**pathType: Prefix** là cách match URL theo segment semantics, không có nghĩa tự cắt /shop. Manifest trên minh họa routing path, **chưa bao gồm TLS, Service, Deployment hay security hardening**, không phải cấu hình production hoàn chỉnh.

### 10.2. Ingress-nginx rewrite path

Một ví dụ controller-specific cho ingress-nginx:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: catalog-strip
  annotations:
    nginx.ingress.kubernetes.io/use-regex: "true"
    nginx.ingress.kubernetes.io/rewrite-target: /$2
spec:
  ingressClassName: nginx
  rules:
    - host: api.example.test
      http:
        paths:
          - path: /shop(/|$)(.*)
            pathType: ImplementationSpecific
            backend:
              service:
                name: catalog-svc
                port:
                  number: 8080
~~~

Trong ingress-nginx hỗ trợ rule này, request **/shop/api/items/42** có thể rewrite thành **/api/items/42** nhờ capture group thứ hai **$2**. **Backend root context** sẽ match controller.

**YAML không chứng minh X-Forwarded-Prefix được tự thêm.** Phải kiểm controller/gateway có thực sự đưa **X-Forwarded-Prefix: /shop** hay không. Nếu không, cấu hình theo đúng controller và trust boundary; đừng vội bật tùy ý configuration-snippet vì nhiều cluster chặn cơ chế này nhằm giảm security risk.

**IngressClass/controller-specific:** annotation nginx.ingress.kubernetes.io không tự áp dụng cho Traefik, Envoy Gateway, NGINX Inc, managed cloud ingress hay các Gateway API implementations khác. Khi đổi controller hoặc Kubernetes version, review rewrite behavior và HTTPS/forwarding headers lại từ đầu.

## 11. Chống Host-header poisoning và open redirect

Một attacker có thể gửi tới public edge:

~~~http
GET /shop/api/items/42 HTTP/1.1
Host: api.example.test
X-Forwarded-Host: attacker.example
X-Forwarded-Proto: https
X-Forwarded-Prefix: /evil
~~~

Nếu edge chuyển nguyên headers giả vào backend và Boot framework tin chúng, API có thể sinh:

~~~http
Location: https://attacker.example/evil/api/items/42
~~~

Điều này có thể đầu độc redirects, resource links, OAuth2 callback hoặc links trong email/password-reset. **ForwardedHeaderFilter không tự xác minh độ tin cậy của headers.**

Bảo vệ:

1. Edge **loại bỏ hoặc ghi đè tất cả Forwarded/X-Forwarded-*** do Internet client gửi.
2. Trusted edge tạo headers từ virtual host, TLS listener và public route đã allowlist.
3. Backend chỉ nhận từ edge/network được phép; đóng public backend listener.
4. Nếu nhiều proxy hops, xác định ai được giữ/ghi đè Forwarded chain.
5. Không cho raw Host hoặc X-Forwarded-Host tự quyết định domain cho email/reset links.
6. Thử spoof header qua **public ingress**, xác nhận self/Location vẫn đúng hostname.
7. Không coi X-Forwarded-For là authenticated user identity.
8. Nếu không có trusted proxy, để strategy none hoặc dùng public base URL cố định do admin cấu hình.

Với Java Servlet app dùng **ForwardedHeaderFilter** tự cấu hình, có chế độ **removeOnly** để bỏ headers mà không sử dụng chúng. Đó là một lựa chọn khi app không tin headers, nhưng phải thiết kế rõ thay vì vừa bật strategy framework vừa tin mọi public requests.

## 12. Demo chạy được: Spring Boot 3.3, Java 17+

Ví dụ này có GET, POST 201 và redirect 302. Các URLs được tạo từ Servlet request context, không hardcode localhost hay public hostname.

**Môi trường:** Spring Boot **3.3.13**, Java 17+, Maven, Spring MVC, embedded Tomcat. Đây là ví dụ tương thích nhánh 3.3; production mới nên chọn nhánh Boot còn được bảo trì.

Cấu trúc:

~~~text
public-path-demo/
  pom.xml
  src/main/java/com/example/publicpath/
    PublicPathApplication.java
    ItemView.java
    CreateItemRequest.java
    ItemController.java
  src/main/resources/
    application.properties
  src/test/java/com/example/publicpath/
    StrippedPrefixHttpTests.java
    PreservedPrefixHttpTests.java
    ItemControllerMvcTests.java
~~~

### 12.1. Maven pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>public-path-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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
~~~

**spring-boot-starter-web** mang Servlet Spring MVC, Tomcat/Jackson phù hợp BOM; starter-test có JUnit Jupiter, MockMvc và SpringBootTest.

### 12.2. application.properties

~~~properties
spring.application.name=public-path-demo
server.port=8080

# Default context root cho demo strip path.
# Khi can preserve: khoi dong voi --server.servlet.context-path=/shop

# Chi dung framework strategy khi reverse proxy thuc su duoc tin.
server.forward-headers-strategy=framework

# Can xem khi Tomcat nam sau TLS termination proxy.
server.tomcat.redirect-context-root=false

server.error.include-message=never
server.error.include-stacktrace=never
~~~

**Không public demo backend port với config tin forwarded headers.** Những headers trong test dưới đây là synthetic để kiểm khi proxy có trách nhiệm sanitize; trong production phải có network policy/edge verification.

### 12.3. Main class

**src/main/java/com/example/publicpath/PublicPathApplication.java**:

~~~java
package com.example.publicpath;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PublicPathApplication {
    public static void main(String[] args) {
        SpringApplication.run(PublicPathApplication.class, args);
    }
}
~~~

### 12.4. DTOs

**src/main/java/com/example/publicpath/ItemView.java**:

~~~java
package com.example.publicpath;

public record ItemView(
        long id,
        String name,
        String self,
        String collection) {
}
~~~

**src/main/java/com/example/publicpath/CreateItemRequest.java**:

~~~java
package com.example.publicpath;

public record CreateItemRequest(String name) {
}
~~~

ItemView có two absolute URL fields để quan sát. Chúng **không phải HAL tự động**; với Spring HATEOAS, linkTo/WebMvcLinkBuilder cũng cần effective request context đúng, nhưng API demo giữ dependency tối giản.

### 12.5. Controller đầy đủ

**src/main/java/com/example/publicpath/ItemController.java**:

~~~java
package com.example.publicpath;

import java.net.URI;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.support.ServletUriComponentsBuilder;

@RestController
@RequestMapping("/api/items")
public class ItemController {

    private record Item(long id, String name) {
    }

    private final Map<Long, Item> items =
            new ConcurrentHashMap<>(Map.of(
                    42L, new Item(42L, "Example item")
            ));

    private final AtomicLong nextId = new AtomicLong(100L);

    private URI itemUri(long id) {
        return ServletUriComponentsBuilder
                .fromCurrentContextPath()
                .path("/api/items/{id}")
                .buildAndExpand(id)
                .toUri();
    }

    private URI collectionUri() {
        return ServletUriComponentsBuilder
                .fromCurrentContextPath()
                .path("/api/items")
                .build()
                .toUri();
    }

    private ItemView view(Item item) {
        return new ItemView(
                item.id(),
                item.name(),
                itemUri(item.id()).toString(),
                collectionUri().toString());
    }

    @GetMapping(value = "/{id}",
            produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<ItemView> one(
            @PathVariable("id") long id) {

        Item item = items.get(id);
        if (item == null) {
            return ResponseEntity.notFound().build();
        }
        return ResponseEntity.ok(view(item));
    }

    @PostMapping(
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<ItemView> create(
            @RequestBody CreateItemRequest input) {

        if (input == null || input.name() == null
                || input.name().isBlank()) {
            return ResponseEntity.badRequest().build();
        }

        long id = nextId.getAndIncrement();
        Item created = new Item(id, input.name().trim());
        items.put(id, created);

        return ResponseEntity.created(itemUri(id))
                .body(view(created));
    }

    @GetMapping("/{id}/redirect")
    public ResponseEntity<Void> redirect(
            @PathVariable("id") long id) {

        if (!items.containsKey(id)) {
            return ResponseEntity.notFound().build();
        }

        return ResponseEntity.status(HttpStatus.FOUND)
                .location(itemUri(id))
                .build();
    }
}
~~~

**Phân tích:**

- Controller chỉ map **/api/items** và **/{id}**, không thêm /shop vào từng route.
- **ServletUriComponentsBuilder.fromCurrentContextPath()** lấy effective servlet context của current request, bao gồm origin và context path đã được trusted forwarding xử lý.
- **ResponseEntity.created(itemUri(id))** trả 201 Created cùng Location là absolute URI.
- **ResponseEntity.status(HttpStatus.FOUND).location(...).build()** trả 302 Found và Location; controller không tự điều hướng client ở phía server.
- Body JSON có **self** và **collection** để test links trong representation.
- Data giữ ở ConcurrentHashMap và AtomicLong để chạy độc lập không cần DB; không đủ authorization/validation cho production.
- URI builder chỉ giải quyết URL semantics, không loại bỏ host-header poisoning nếu proxy chưa kiểm trust.

## 13. Chạy demo và thử với curl

Từ thư mục có pom.xml, Java 17+ và Maven:

~~~bash
mvn clean test
mvn spring-boot:run
~~~

Khi server chạy, request trực tiếp (không qua proxy):

~~~bash
curl -si \
  -H 'Accept: application/json' \
  http://127.0.0.1:8080/api/items/42
~~~

Body điển hình:

~~~json
{
  "id": 42,
  "name": "Example item",
  "self": "http://127.0.0.1:8080/api/items/42",
  "collection": "http://127.0.0.1:8080/api/items"
}
~~~

Đây là **direct-backend origin** vì request chưa có forwarded metadata. Giờ mô phỏng một proxy strip /shop và gửi headers phù hợp:

~~~bash
curl -si \
  -H 'Accept: application/json' \
  -H 'X-Forwarded-Host: api.example.test' \
  -H 'X-Forwarded-Proto: https' \
  -H 'X-Forwarded-Port: 443' \
  -H 'X-Forwarded-Prefix: /shop' \
  http://127.0.0.1:8080/api/items/42
~~~

Body hợp lệ phải có **self** với scheme **https**, host **api.example.test**, path **/shop/api/items/42**, và **collection** có path **/shop/api/items**. Một representation điển hình:

~~~json
{
  "id": 42,
  "name": "Example item",
  "self": "https://api.example.test/shop/api/items/42",
  "collection": "https://api.example.test/shop/api/items"
}
~~~

**Port chuẩn 443 có thể được biểu diễn tường minh trong một số URI builders/configurations**. Trong test portable, so sánh scheme/host/path và chấp nhận port -1 hoặc 443 nếu contract không yêu cầu canonical formatting.

### POST 201 Created

~~~bash
curl -si \
  -X POST \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  -H 'X-Forwarded-Host: api.example.test' \
  -H 'X-Forwarded-Proto: https' \
  -H 'X-Forwarded-Prefix: /shop' \
  --data-binary '{"name":"Created via API"}' \
  http://127.0.0.1:8080/api/items
~~~

Kỳ vọng **201**, Location mang public path **/shop/api/items/{id}**. ID do AtomicLong sinh, thường bắt đầu ở 100 nếu đây là create đầu tiên trên JVM mới; không được hardcode 100 trong test khi state có thể thay đổi.

### Redirect 302 Found

~~~bash
curl -si \
  -H 'X-Forwarded-Host: api.example.test' \
  -H 'X-Forwarded-Proto: https' \
  -H 'X-Forwarded-Prefix: /shop' \
  http://127.0.0.1:8080/api/items/42/redirect
~~~

Kỳ vọng **302**, Location là public URI của item 42. **Không dùng curl -L** nếu muốn nhìn nguyên response 302, vì -L tự động follow và có thể che lỗi redirect đầu tiên.

### Khởi động kiểu preserve

Dừng server, rồi:

~~~bash
mvn spring-boot:run \
  -Dspring-boot.run.arguments="--server.servlet.context-path=/shop"
~~~

Backend đúng path bây giờ là **http://127.0.0.1:8080/shop/api/items/42**. Trong preserve mode, không gửi X-Forwarded-Prefix khi public prefix đã hiện trong Servlet context; chỉ cần forwarded host/proto nếu public origin khác backend.

**Cẩn trọng:** những curl gửi fake X-Forwarded-* trong phần này chỉ chạy trên localhost lab, không thể thay thế security test qua trusted edge. Khi backend public mở thẳng, bất kỳ client nào cũng có thể spoof headers tương tự.

## 14. HTTP integration test cho trường hợp strip

Đây là **SpringBootTest(RANDOM_PORT)** qua embedded HTTP server thật, không cần Nginx. Chúng ta giả lập trusted forwarding headers để kiểm URL builder.

Tạo **src/test/java/com/example/publicpath/StrippedPrefixHttpTests.java**:

~~~java
package com.example.publicpath;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties = {"server.forward-headers-strategy=framework"})
class StrippedPrefixHttpTests {

    @LocalServerPort
    int port;

    private final HttpClient client = HttpClient.newBuilder()
            .followRedirects(HttpClient.Redirect.NEVER)
            .build();

    private final ObjectMapper json = new ObjectMapper();

    private HttpRequest.Builder forwarded(String path) {
        return HttpRequest.newBuilder(
                URI.create("http://127.0.0.1:" + port + path))
                .timeout(Duration.ofSeconds(5))
                .header("X-Forwarded-Host", "api.example.test")
                .header("X-Forwarded-Proto", "https")
                .header("X-Forwarded-Port", "443")
                .header("X-Forwarded-Prefix", "/shop");
    }

    private void assertPublicUrl(String link, String path) {
        URI uri = URI.create(link);
        assertEquals("https", uri.getScheme());
        assertEquals("api.example.test", uri.getHost());
        assertEquals(path, uri.getPath());
        assertTrue(uri.getPort() == -1 || uri.getPort() == 443);
    }

    @Test
    void getGeneratesPublicLinks() throws Exception {
        HttpResponse<String> response = client.send(
                forwarded("/api/items/42").GET().build(),
                HttpResponse.BodyHandlers.ofString());

        assertEquals(200, response.statusCode());
        JsonNode body = json.readTree(response.body());

        assertEquals(42, body.path("id").asInt());
        assertPublicUrl(body.path("self").asText(),
                "/shop/api/items/42");
        assertPublicUrl(body.path("collection").asText(),
                "/shop/api/items");
    }

    @Test
    void postGeneratesPublicLocation() throws Exception {
        HttpResponse<String> response = client.send(
                forwarded("/api/items")
                    .header("Content-Type", "application/json")
                    .header("Accept", "application/json")
                    .POST(HttpRequest.BodyPublishers.ofString(
                            "{\"name\":\"New item\"}"))
                    .build(),
                HttpResponse.BodyHandlers.ofString());

        assertEquals(201, response.statusCode());
        JsonNode body = json.readTree(response.body());
        long id = body.path("id").asLong();

        assertPublicUrl(response.headers()
                .firstValue("Location").orElseThrow(),
                "/shop/api/items/" + id);

        assertPublicUrl(body.path("self").asText(),
                "/shop/api/items/" + id);
    }

    @Test
    void redirectGeneratesPublicLocation() throws Exception {
        HttpResponse<String> response = client.send(
                forwarded("/api/items/42/redirect")
                    .GET().build(),
                HttpResponse.BodyHandlers.ofString());

        assertEquals(302, response.statusCode());
        assertPublicUrl(response.headers()
                .firstValue("Location").orElseThrow(),
                "/shop/api/items/42");
    }
}
~~~

**Điểm được chứng minh:** Với root Servlet context và Boot framework strategy, forwarded scheme/host/prefix được dùng trong links và Location khi có HTTP request thật.

**Chưa được chứng minh:** ingress thực đã strip /shop, edge đã sanitize headers, public TLS đúng hoặc DNS hoạt động. Test này chủ động mô phỏng headers nên không kiểm được trust boundary ở proxy.

## 15. HTTP integration test cho trường hợp preserve

Tạo **src/test/java/com/example/publicpath/PreservedPrefixHttpTests.java**:

~~~java
package com.example.publicpath;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties = {
        "server.servlet.context-path=/shop",
        "server.forward-headers-strategy=framework"
    })
class PreservedPrefixHttpTests {

    @LocalServerPort
    int port;

    private final HttpClient client = HttpClient.newHttpClient();
    private final ObjectMapper json = new ObjectMapper();

    @Test
    void correctServletContextIsReflectedInSelf()
            throws Exception {

        HttpRequest req = HttpRequest.newBuilder(
                URI.create("http://127.0.0.1:" + port
                        + "/shop/api/items/42"))
                .timeout(Duration.ofSeconds(5))
                .header("X-Forwarded-Host", "api.example.test")
                .header("X-Forwarded-Proto", "https")
                .header("X-Forwarded-Port", "443")
                .GET()
                .build();

        HttpResponse<String> response = client.send(
                req, HttpResponse.BodyHandlers.ofString());

        assertEquals(200, response.statusCode());

        JsonNode body = json.readTree(response.body());
        URI self = URI.create(body.path("self").asText());

        assertEquals("https", self.getScheme());
        assertEquals("api.example.test", self.getHost());
        assertEquals("/shop/api/items/42", self.getPath());
        assertTrue(self.getPort() == -1 || self.getPort() == 443);
    }

    @Test
    void backendRootWithoutServletPrefixIsNotSameRoute()
            throws Exception {

        HttpRequest req = HttpRequest.newBuilder(
                URI.create("http://127.0.0.1:" + port
                        + "/api/items/42"))
                .timeout(Duration.ofSeconds(5))
                .GET().build();

        HttpResponse<String> response = client.send(
                req, HttpResponse.BodyHandlers.ofString());

        assertEquals(404, response.statusCode());
    }
}
~~~

**Mấu chốt:** Trong test preserve, GET backend **/shop/api/items/42** hợp lệ vì Servlet app mount dưới /shop. Request thiếu /shop không vào cùng Servlet context. Test chỉ triển khai một context nên kết quả 404 được kỳ vọng; trong server có các contexts khác, status có thể khác.

**Không thêm X-Forwarded-Prefix cho preserve test** vì public prefix đã hiện trong backend path; đó là khác biệt lớn với strip test.

## 16. MockMvc kiểm controller, nhưng không thay proxy integration

Một test MVC slice nhanh có thể dùng **@WebMvcTest** và **MockMvc**. Tạo **src/test/java/com/example/publicpath/ItemControllerMvcTests.java**:

~~~java
package com.example.publicpath;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.endsWith;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(ItemController.class)
class ItemControllerMvcTests {

    @Autowired
    MockMvc mvc;

    @Test
    void itemMappingAndJsonAreCorrect() throws Exception {
        mvc.perform(get("/api/items/42")
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value(42))
            .andExpect(jsonPath("$.self",
                    endsWith("/api/items/42")));
    }

    @Test
    void unknownItemIs404() throws Exception {
        mvc.perform(get("/api/items/999")
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isNotFound());
    }
}
~~~

MockMvc không đi qua socket, TLS, Nginx hay Kubernetes. Nó kiểm Spring MVC mapping/serialization, nhưng **không chứng minh** proxy rewrite hoặc X-Forwarded-Prefix ngoài thật. Vì vậy cần cả **RANDOM_PORT HTTP integration tests** và **public ingress tests** trong quy trình release.

Chạy suite:

~~~bash
mvn clean test
~~~

Nếu Maven kết thúc exit code 0 và chạy các test classes, code/config thuộc demo đã pass các assertions. Không tự tuyên bố một môi trường đã chạy test chỉ vì bài có lệnh; người học phải tạo project và thực thi trên máy của mình hoặc CI.

## 17. Kiểm tra qua public ingress: chỉ dùng khi đã triển khai

Khi DNS/TLS và ingress đang chạy, dùng public URL:

~~~bash
curl -si \
  -H 'Accept: application/json' \
  https://api.example.test/shop/api/items/42
~~~

Cần xác nhận:

- HTTP 200, JSON có item 42.
- self có **https**, host **api.example.test**, path **/shop/api/items/42**.
- collection có **/shop/api/items**.
- Không có **/shop/shop**, **/internal**, **catalog-service:8080**, localhost hoặc mixed-content http links.
- Không có redirect loop do /shop → /shop/shop.
- Query parameters/encoding được giữ khi route thực có query.

POST qua public ingress:

~~~bash
curl -si \
  -X POST \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  --data-binary '{"name":"Public create"}' \
  https://api.example.test/shop/api/items
~~~

Cần status **201** và **Location** là public HTTPS link. Dùng chính Location do server trả để GET item vừa tạo; không hardcode id.

Kiểm redirect:

~~~bash
curl -si \
  https://api.example.test/shop/api/items/42/redirect
~~~

Cần status **302** và Location hợp lệ. Khi muốn kiểm cả redirect chain có thể dùng **curl -L**, nhưng khi debug phải xem Location của response đầu để không che lỗi.

### Kiểm spoofed forwarded headers ở edge

~~~bash
curl -si \
  -H 'X-Forwarded-Host: attacker.example' \
  -H 'X-Forwarded-Proto: http' \
  -H 'X-Forwarded-Prefix: /evil' \
  https://api.example.test/shop/api/items/42
~~~

Nếu edge được bảo vệ đúng, response **không được chuyển host thành attacker.example hoặc prefix thành /evil**. Đó là security test quan trọng khác với synthetic test gọi trực tiếp backend. Test chỉ trong môi trường được phép, không dùng để quét host của người khác.

## 18. Những liên kết khác dễ bị sai prefix

| Thành phần | Lỗi thường gặp | Cách kiểm |
| --- | --- | --- |
| **POST 201 Location** | http://internal:8080/api/items/100 | Kiểm Location, follow GET qua public origin. |
| **302/303 login/logout redirect** | Chuyển HTTPS về HTTP, thiếu /shop | Kiểm redirect chain và status Location. |
| **Spring HATEOAS** | _links.self/next/collection không có prefix | Kiểm HAL links và WebMvcLinkBuilder linkTo/methodOn. |
| **OAuth2/OIDC** | redirect_uri lệch registered URI | Kiểm scheme/host/prefix ở callback. |
| **Session cookie** | Path=/internal nhưng browser chỉ truy cập /shop | Kiểm Set-Cookie Path, Domain, Secure, SameSite. |
| **Frontend SPA** | fetch("/api/items") gọi origin root | Cấu hình public API base hoặc relative routing đúng. |
| **Static assets** | /assets/app.js bị 404 do thiếu /shop | Kiểm HTML base href và build asset public path. |
| **OpenAPI/Swagger UI** | UI gọi internal URL hoặc swagger-config sai path | Kiểm spec servers và Network tab. |
| **Actuator** | Probe /actuator/health khi backend context=/shop | Dùng backend context và management port thực. |
| **CORS preflight** | OPTIONS 404/403 do proxy rewrite hoặc security | Test Origin/OPTIONS qua public URL. |
| **WebSocket/SSE** | Handshake/stream URI thiếu prefix | Kiểm Upgrade, timeouts và proxy route. |
| **CDN cache** | Cache key bỏ qua host/path/representation | Kiểm response Cache-Control/Vary và proxy cache policy. |

**SPA rất dễ mắc lỗi:** trang ở **https://example.test/shop/** nhưng JavaScript gọi **fetch("/api/items/42")** sẽ gửi tới **https://example.test/api/items/42**, không phải /shop/api/items/42. Servlet context path không thể tự sửa một literal URL do frontend tạo. Sửa frontend public base path, reverse proxy routing hoặc dùng public URLs được backend cung cấp.

**Cookie path:** khi proxy strip /shop còn container context root, session cookie Path có thể không đúng policy. Nếu cần scope cookie chỉ ở /shop, cấu hình **server.servlet.session.cookie.path=/shop** sau khi đánh giá business/security; đừng bật bừa khi nhiều public prefixes dùng chung cookie.

## 19. Spring Security, OAuth2, CORS và forwarded origin

Spring Security có thể tạo login redirect, saved request redirect hoặc OAuth2 redirect_uri dựa trên effective scheme/host/path. Nếu trusted forwarding xử lý sai, IdP có thể từ chối **redirect_uri_mismatch** vì application tạo callback nội bộ:

~~~text
http://catalog-service:8080/login/oauth2/code/provider
~~~

trong khi IdP đăng ký:

~~~text
https://api.example.test/shop/login/oauth2/code/provider
~~~

Sửa đúng public origin/prefix và registered redirect URI; **không thêm wildcard redirect URIs nguy hiểm** chỉ để bỏ lỗi callback.

**CORS không phải forwarded path handling.** CORS dùng Origin, Access-Control-Allow-* và browser policy. X-Forwarded-Prefix không tự bật CORS; đường OPTIONS preflight phải được ingress/SecurityFilterChain định tuyến và xử lý đúng. Với cookie/session, CSRF protection vẫn cần áp dụng cho unsafe methods.

**Không dùng request Host/X-Forwarded-Host chưa xác minh để sinh password-reset email link.** Khi public origin cố định, một cấu hình canonical public base URL do admin quản lý thường an toàn hơn việc tin header client. Nếu hệ thống hỗ trợ nhiều tenant domains, cần domain allowlist và canonicalization rõ.

## 20. Actuator, health probes và management paths

Với cùng server port:

~~~properties
server.servlet.context-path=/shop
management.endpoints.web.base-path=/actuator
management.endpoints.web.exposure.include=health
~~~

Backend same-port thường có path **/shop/actuator/health**. Nhưng nếu:

~~~properties
management.server.port=8081
management.server.base-path=/manage
management.endpoints.web.base-path=/actuator
~~~

Management endpoints dùng management server base path và port riêng, **không tự đặt dưới main servlet context path**.

Kubelet probe thường gọi trực tiếp PodIP/container port hoặc Service nội bộ, **không bắt buộc qua public Ingress**. Vì vậy probe path nên phản ánh **upstream/backend route**, không mù quáng sao chép public path /shop. Phân biệt readiness/liveness và xem management port separate vs main port.

Đừng vì 404 ở health probe mà công khai tất cả **/actuator/** endpoints trên ingress. Loggers, env, heapdump, httpexchanges và logfile cần security management plane riêng.

## 21. Chẩn đoán nhanh theo triệu chứng

| Triệu chứng | Nguyên nhân phổ biến | Hành động |
| --- | --- | --- |
| GET public /shop/... trả 404, backend /api/... trả 200 | Proxy chưa strip hoặc backend context không khớp | Viết public → rewrite → upstream → servlet mapping. |
| GET backend /api/... trả 404 khi context=/shop | Backend path thiếu Servlet prefix | Giữ /shop khi proxy forward, hoặc đổi backend root. |
| Link trả /shop/shop | Prefix được nối thủ công nhiều tầng | Loại chỗ cộng dư, dùng URI builder và test. |
| POST Location trả hostname nội bộ | Không xử lý forwarded host/scheme | Xác minh edge headers, strategy và builder. |
| Link đúng host nhưng thiếu /shop | XFP thiếu hoặc native không hỗ trợ prefix | Trusted XFP + framework, hoặc public base URI config. |
| Redirect HTTPS → HTTP | XFP/Proto sai hoặc Tomcat root redirect quá sớm | Kiểm X-Forwarded-Proto, server.tomcat.redirect-context-root=false. |
| Location dẫn tới attacker.example | Headers giả vượt trust boundary | Strip/overwrite ở edge, host allowlist, private backend. |
| Cookie không gửi sau login | Path/Domain/Secure/SameSite sai | Kiểm Set-Cookie trên public response. |
| OAuth2 redirect_uri_mismatch | Public origin/prefix sinh sai | Kiểm callback URL và IdP registered URI. |
| CSS/JS 404 nhưng API 200 | Frontend asset base không có /shop | Sửa SPA public path và proxy static location. |
| Kubernetes probe 404 | Dùng public path thay backend path | Xác định context path/management port chính xác. |
| Ingress rewrite không chạy | Annotation/controller khác hoặc regex sai | Kiểm IngressClass và rules thật. |
| CORS OPTIONS 403 | Security hoặc route bị rewrite sai | Test Origin/OPTIONS qua ingress. |
| MockMvc xanh nhưng public sai | MockMvc không đi qua proxy | Test RANDOM_PORT và public topology. |
| Có Forwarded headers nhưng URI vẫn sai | none/native/filter/order hoặc hardcoded URLs | Kiểm strategy, effective request và code. |

## 22. Runbook sửa lỗi không gây thêm rủi ro

1. Ghi rõ **public URL đầy đủ** người dùng cần mở, bao gồm scheme, host, port và prefix.
2. Ghi **actual upstream request URI** mà ingress/proxy chuyển vào backend; không đoán từ Ingress manifest.
3. Kiểm **server.servlet.context-path**, **spring.mvc.servlet.path** và @RequestMapping.
4. Chọn rõ preserve, strip hay replace. Không bật tất cả prefix layers cùng lúc.
5. Kiểm **Forwarded/X-Forwarded-*** thực được trusted proxy tạo. Không tin inbound headers chưa sanitize.
6. Chọn **server.forward-headers-strategy** phù hợp với prefix behavior.
7. Dùng ServletUriComponentsBuilder hoặc framework link builders thay hardcoded origin.
8. Test GET body links, 201 Location, 302 redirect và follow actual generated URL.
9. Test session cookie Path, OAuth2 callback, SPA assets và health endpoints.
10. Test spoofed forwarded headers qua public edge.
11. Tích hợp tests vào CI và canary rollout; có cách rollback Ingress rules/context config.

**Đo bằng metrics/traces đúng tầng:** Backend status 404 có thể đến từ controller hoặc Servlet context, còn 502/503 có thể đến từ ingress không kết nối được service. Không chỉ xem một log backend rồi suy proxy đúng. Tránh log Authorization/Cookie/body khi debug.

## 23. Checklist triển khai production

- [ ] Có bảng public URL → proxy rewrite → upstream URI → Servlet context → MVC mapping.
- [ ] Cấu hình đúng **server.servlet.context-path** cho kiểu preserve/strip/replace đã chọn.
- [ ] Không cộng cùng prefix ở @RequestMapping, DispatcherServlet path, frontend và proxy.
- [ ] Đã kiểm **server.forward-headers-strategy** và embedded server/version.
- [ ] Với path rewrite, **X-Forwarded-Prefix** được đưa bởi trusted proxy và Spring xử lý đúng.
- [ ] Với TLS termination Tomcat, kiểm **server.tomcat.redirect-context-root=false**.
- [ ] Edge loại bỏ untrusted Forwarded/X-Forwarded-* và set canonical values.
- [ ] Backend được cô lập khỏi direct public traffic, có Host allowlist khi cần.
- [ ] GET links/self, POST 201 Location và 302/303 redirects dùng public scheme/host/path.
- [ ] Không có /shop/shop, /internal, http://internal hoặc service:8080 trong generated public links.
- [ ] Nginx proxy_pass slash behavior và ingress rewrite-target/capture groups đã được test.
- [ ] IngressClass/controller-specific annotations đúng sản phẩm đang triển khai.
- [ ] Actuator management port/base-path được tính riêng, không expose dữ liệu quản trị.
- [ ] Frontend SPA, static assets, Swagger UI/OpenAPI servers và public API base đúng prefix.
- [ ] OAuth2 callback, session cookies, CSRF/CORS và proxy routing đã được kiểm.
- [ ] Có MockMvc mapping tests, RANDOM_PORT forwarded tests và public ingress end-to-end tests.
- [ ] Security test spoof X-Forwarded-Host/Proto/Prefix qua public edge thành công.
- [ ] Khi upgrade Boot/Framework/ingress controller, chạy lại URL contract tests.

## 24. Câu hỏi tự kiểm tra

**1. server.servlet.context-path=/shop có tác dụng gì?**  
Triển khai Servlet application dưới /shop ở backend; MVC mappings được tính tương đối với context đó.

**2. Nếu proxy đã strip /shop và backend nhận /api/items/42 thì context path nào phù hợp?**  
Root context (rỗng).

**3. Nếu proxy giữ nguyên /shop mà backend context path=/shop thì có cần X-Forwarded-Prefix để route không?**  
Không; forwarded metadata chỉ dùng khi cần phản ánh public origin/prefix cho URL generation.

**4. Header nào thường truyền public prefix khi strip?**  
X-Forwarded-Prefix: /shop.

**5. Header nào mô tả HTTPS ở public side sau TLS termination?**  
X-Forwarded-Proto: https hoặc Forwarded proto=https.

**6. Vì sao Location có thể hiện http://service:8080?**  
App dựng URL từ upstream origin thay vì trusted public forwarded information.

**7. server.forward-headers-strategy=framework sử dụng gì cho Servlet Spring MVC?**  
Spring Framework ForwardedHeaderFilter.

**8. NATIVE có tự hỗ trợ X-Forwarded-Prefix trên mọi server/version không?**  
Không nên giả định; cần kiểm cụ thể, framework thường phù hợp prefix rewrite.

**9. X-Forwarded-Host có thể tin trực tiếp từ Internet không?**  
Không. Edge phải loại bỏ header giả và ghi giá trị canonical đã được kiểm soát.

**10. Vì sao Ingress pathType Prefix không tự strip prefix?**  
Nó quy định điều kiện match/routing; rewrite là chức năng bổ sung của controller.

**11. Vì sao proxy_pass có slash cuối quan trọng trong Nginx examples?**  
Trong các example location prefix ở trên, URI / làm Nginx thay location prefix; không có URI thì giữ upstream path gốc.

**12. Tại sao GET 200 chưa đủ để xác nhận cấu hình reverse proxy?**  
Location/redirect/self/cookie/OAuth callback có thể vẫn sai public host, scheme hoặc path.

**13. MockMvc có kiểm được real ingress rewrite không?**  
Không. Cần HTTP integration và public topology tests.

**14. Khi Actuator chạy management.port riêng, endpoint path có tự nằm dưới Servlet context path chính không?**  
Không; phải tính theo management server base path.

**15. Vì sao session Cookie Path có thể gây lỗi login khi public prefix khác internal context?**  
Browser chỉ gửi cookie ở những path phù hợp; Path=/internal không match /shop.

**16. WebFlux dùng context base path nào?**  
spring.webflux.base-path và forwarded handling theo reactive stack; không dùng Servlet context path y như MVC.

**17. server.tomcat.redirect-context-root=false giúp giải quyết tình huống nào?**  
Cho phép X-Forwarded-Proto được xét trước Tomcat redirect context root khi TLS terminate ở proxy.

**18. Làm sao kiểm nguy cơ host-header poisoning?**  
Gửi X-Forwarded-Host giả qua public edge và xác nhận output vẫn sử dụng canonical host.

**19. X-Forwarded-Prefix có tự sửa upstream URI đã bị rewrite sai không?**  
Không. Proxy routing và Servlet mapping phải đúng độc lập với metadata URL generation.

**20. Thứ cần kiểm sau khi đổi Ingress controller là gì?**  
Path rewrite, forwarded headers, TLS scheme, public Location/redirect/links và security trust boundary.

## 25. Tài liệu tham khảo chính thức

- **Spring Boot 3.3 – Embedded Web Servers / Running Behind a Front-end Proxy Server:** https://docs.spring.io/spring-boot/3.3/how-to/webserver.html — forward-headers-strategy, native/framework, Tomcat redirect-context-root.
- **Spring Boot 3.3 – Common Application Properties:** https://docs.spring.io/spring-boot/3.3/appendix/application-properties/ — context-path, forwarded headers, session cookie path, management base-path.
- **Spring Framework – MVC Forwarded Headers:** https://docs.spring.io/spring-framework/reference/web/webmvc/filters.html — X-Forwarded-Prefix scenarios, ForwardedHeaderFilter và trust boundary.
- **Spring Framework – ServletUriComponentsBuilder Javadoc:** https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/servlet/support/ServletUriComponentsBuilder.html — fromCurrentContextPath và URI building.
- **Spring Boot 3.3 – Test Spring Boot Applications:** https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html — MockMvc, @WebMvcTest, @SpringBootTest(RANDOM_PORT), @LocalServerPort.
- **Spring Boot 3.3 – Actuator Endpoints:** https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html — web base path/health/readiness, exposure.
- **Kubernetes Ingress:** https://kubernetes.io/docs/concepts/services-networking/ingress/ — pathType/host/service routing.
- **ingress-nginx rewrite example:** https://github.com/kubernetes/ingress-nginx/blob/main/docs/examples/rewrite/README.md — use-regex/rewrite-target/capture groups, controller-specific.
- **NGINX ngx_http_proxy_module:** https://nginx.org/en/docs/http/ngx_http_proxy_module.html#proxy_pass — trailing URI/replacement behavior.
- **RFC 7239 Forwarded HTTP Extension:** https://www.rfc-editor.org/rfc/rfc7239 — standard Forwarded header.
- **RFC 9110 HTTP Semantics:** https://www.rfc-editor.org/rfc/rfc9110.html — Location, redirects, host/authority.
