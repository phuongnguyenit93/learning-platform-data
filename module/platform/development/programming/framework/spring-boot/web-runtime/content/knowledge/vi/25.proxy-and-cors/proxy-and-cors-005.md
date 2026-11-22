# Tạo redirect, liên kết tuyệt đối và cookie đúng địa chỉ công khai

Khi triển khai ứng dụng Spring Boot phía sau **reverse proxy, load balancer, ingress hoặc CDN**, địa chỉ mà ứng dụng nhìn thấy thường **khác địa chỉ mà trình duyệt thực sự truy cập**. Ví dụ:

- Người dùng mở: `https://shop.example.test/account`.
- NGINX nhận HTTPS ở cổng 443, giải mã TLS rồi chuyển HTTP đến `http://127.0.0.1:8080/account`.
- Spring Boot chỉ nhìn kết nối đến từ proxy nếu không được cấu hình xử lý forwarded headers.
- Controller tạo `Location: http://127.0.0.1:8080/login`, email chứa liên kết nội bộ hoặc session cookie thiếu `Secure`: tất cả đều có thể sai khi chạy production.

Bài này hướng dẫn cách khiến **redirect, liên kết tuyệt đối và cookie** phù hợp **địa chỉ công khai** mà browser nhìn thấy, đồng thời tránh tin các header do người dùng giả mạo. Trọng tâm là **Spring Boot 3.x + Spring MVC/Servlet + Java 17+**, có phần mở rộng WebFlux, Spring Security/OAuth2 và nhiều proxy hops.

**Nguyên tắc chính:** xác định một **public origin/base URL đáng tin**, thiết lập **trust boundary** ở proxy, chuyển đủ thông tin scheme/host/port/prefix, để framework xử lý URL dựa trên request đã được hiệu chỉnh, và cấu hình cookie riêng theo chính sách HTTPS/domain/path của trình duyệt. **Không thể sửa toàn bộ vấn đề chỉ bằng CORS hoặc chỉ bằng cách bật một thuộc tính Boot.**

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt URL nội bộ giữa proxy và ứng dụng với URL public mà client cần thấy.
- Giải thích `Host`, `Forwarded`, `X-Forwarded-Proto`, `X-Forwarded-Host`, `X-Forwarded-Port` và `X-Forwarded-Prefix`.
- Chọn `server.forward-headers-strategy=none/native/framework` trong Spring Boot 3.x và giải thích điều kiện tin cậy.
- Viết redirect `redirect:/...` và tạo absolute URL bằng `ServletUriComponentsBuilder` hoặc bằng public-base-url được cấu hình, biết khi nào dùng cách nào.
- Cấu hình session cookie và cookie tự tạo với `Secure`, `HttpOnly`, `SameSite`, `Domain`, `Path`; phân biệt session cookie của Servlet container và của Spring Session.
- Phân tích các lỗi HTTPS→HTTP redirect, port `8080` lọt vào URL, prefix bị thiếu/nhân đôi, redirect_uri OAuth2 sai và cookie không gửi.
- Thử nghiệm một ví dụ Spring Boot Java 17+ chạy được, có cấu hình NGINX minh họa và lệnh `curl`.
- Thiết kế an toàn trước Host header injection, forged forwarded headers, open redirect và cross-origin cookie misuse.

## 2. Vì sao địa chỉ của server khác địa chỉ công khai?

Xét luồng request:

```text
                  Public browser
        GET https://shop.example.test/account
                           |
                           | TLS / HTTPS :443
                           v
             NGINX edge / ingress / LB
                           |
                           | HTTP :8080 (mạng nội bộ)
                           | Host: shop.example.test
                           | X-Forwarded-Proto: https
                           | X-Forwarded-Host: shop.example.test
                           | X-Forwarded-Port: 443
                           v
             Spring Boot / embedded Tomcat
                           |
                           v
                 @Controller handler
```

Ở chặng proxy→Boot, socket thực tế có thể dùng scheme `http`, local port `8080`, và remote address là địa chỉ proxy. Nếu ứng dụng tạo absolute URL dựa trên thông tin kết nối nội bộ mà không hiệu chỉnh, nó có thể sinh sai:

```text
Sai:  http://shop.example.test:8080/done
Sai:  http://127.0.0.1:8080/done
Đúng: https://shop.example.test/done
```

Địa chỉ đúng phụ thuộc **public deployment thực tế**. Một ứng dụng khác có thể công khai dưới `https://portal.example.test/app` hoặc dùng cổng không chuẩn; không áp đặt `https://shop.example.test` lên mọi hệ thống.

### 2.1. Ba loại địa chỉ phải phân biệt

| Loại | Ví dụ | Dùng để làm gì? |
| --- | --- | --- |
| Địa chỉ socket của ứng dụng | `http://127.0.0.1:8080` | Proxy gọi origin, health check nội bộ |
| Địa chỉ public origin | `https://shop.example.test` | Scheme + hostname + port public nếu có |
| Public base URL gồm prefix | `https://shop.example.test/portal` | Liên kết client cần nhìn thấy khi app xuất hiện dưới một prefix |

**Origin** là scheme + host + port; **base URL** có thể còn chứa path prefix. Cookie `Domain` và `Path` là quy tắc riêng để browser quyết định gửi cookie; chúng không được suy từ đường dẫn filesystem hoặc upstream IP.

### 2.2. Dấu hiệu nhận biết cấu hình proxy URL sai

- Browser từ HTTPS bị đưa sang HTTP; có thể bị cảnh báo mixed content, loop ép HTTPS hoặc đăng nhập thất bại.
- HTTP `Location` chứa `localhost`, IP private, `:8080` hoặc thiếu `/portal`.
- Email “xác minh địa chỉ” trỏ về hostname nội bộ, người dùng bên ngoài không mở được.
- `redirect_uri` của OAuth2/OIDC là `http://...`, không trùng URI đã đăng ký với nhà cung cấp identity.
- Session cookie phát ra nhưng không được browser gửi ở request sau do `Secure`, `Domain`, `Path` hoặc `SameSite`.
- Một proxy/CDN có nhiều cấp tự nối hoặc làm mất `X-Forwarded-Prefix`, dẫn đến đường dẫn gấp đôi hoặc 404.
- Link trong JSON/HATEOAS, OpenAPI docs, HTML canonical URL hoặc `Location` của 201 Created chứa hostname không công khai.

## 3. Các header mô tả request gốc

### 3.1. Host và scheme thực tế

`Host` là request header mà HTTP/1.1 dùng để xác định authority/virtual host. Với HTTP/2/3 có khái niệm `:authority`. Proxy có thể chuyển `Host` công khai xuống upstream hoặc đổi sang host nội bộ. Nhưng `Host` ở request đến từ internet **không tự là nguồn tin đáng tin** cho các liên kết nhạy cảm; có thể bị kiểm soát hoặc giả mạo nếu edge không validate hostname.

Nếu ứng dụng tạo URL bằng cách ghép `request.getServerName()` và `request.getScheme()` khi chưa xử lý proxy, giá trị có thể phản ánh chặng kết nối nội bộ. Đừng chữa bằng cách tự nối chuỗi từ nhiều header tùy ý.

### 3.2. RFC 7239: Forwarded

Proxy có thể phát một header tiêu chuẩn:

```http
Forwarded: for=203.0.113.25;proto=https;host=shop.example.test
```

Nó cho biết địa chỉ client/hop, protocol và host do proxy ghi nhận. Khi qua nhiều proxies, giá trị có thể là một danh sách hop. Không tự lấy “phần tử đầu tiên” rồi tin nó nếu không có chính sách proxy đáng tin: dữ liệu có thể được nối từ request do client gửi.

### 3.3. Họ X-Forwarded-*

Nhiều hạ tầng dùng các header de facto:

```http
X-Forwarded-For: 203.0.113.25
X-Forwarded-Proto: https
X-Forwarded-Host: shop.example.test
X-Forwarded-Port: 443
X-Forwarded-Prefix: /portal
```

| Header | Ý nghĩa thường gặp | Sai sót phổ biến |
| --- | --- | --- |
| `X-Forwarded-For` | Chuỗi IP của client/proxies | Tin IP giả để bypass rate limit/access control |
| `X-Forwarded-Proto` | Scheme công khai `http`/`https` | Mất thông tin TLS termination, sinh redirect http |
| `X-Forwarded-Host` | Host công khai từ góc nhìn client | Host header injection nếu không có allowlist |
| `X-Forwarded-Port` | Port công khai | URL lộ `:8080` hoặc bỏ port custom |
| `X-Forwarded-Prefix` | Prefix công khai khi proxy rewrite path | Redirect/link/cookie bị sai `/portal` |
| `X-Forwarded-Ssl` | Thông tin HTTPS kiểu vendor/legacy | Nhầm với chuẩn chung, xử lý không nhất quán |

Các tên header không có nghĩa mọi hạ tầng phát đủ tất cả. `X-Forwarded-Prefix` không nằm trong cú pháp tiêu chuẩn RFC 7239. Với app công khai ở root path, thường không cần prefix; với path rewriting phải kiểm thử theo Spring Framework và connector phiên bản thực tế.

## 4. Cơ chế chuẩn của Spring Boot: forward-headers-strategy

Trong Spring Boot 3.3, thuộc tính quan trọng:

```properties
server.forward-headers-strategy=framework
```

Có ba lựa chọn:

| Giá trị | Cách thực hiện | Khi phù hợp |
| --- | --- | --- |
| `none` | Bỏ qua xử lý forwarded headers theo cơ chế Boot | App không đặt sau proxy tin cậy; không muốn client giả header ảnh hưởng |
| `native` | Dùng hỗ trợ của embedded web server (ví dụ Tomcat RemoteIpValve) | Proxy gửi các header chuẩn mà container xử lý được, thường đủ cho scheme/client IP |
| `framework` | Dùng cơ chế Spring Framework như `ForwardedHeaderFilter` cho Servlet, `ForwardedHeaderTransformer` cho reactive | Cần Spring điều chỉnh request/redirect theo scheme, host, port và đôi khi prefix |

Boot 3.3 mô tả nếu proxy gửi `X-Forwarded-For` và `X-Forwarded-Proto`, chế độ `native` có thể đủ. Nếu cần nhiều hơn, có thể dùng `framework`. Giá trị mặc định phụ thuộc môi trường: Boot có thể tự chọn `native` trên một số cloud platform được nhận diện, và ở môi trường khác mặc định `none`. **Không giả định runtime đang ở chế độ nào**; đặt rõ ở môi trường triển khai nếu public URL phụ thuộc vào nó.

Đối với Servlet, `ForwardedHeaderFilter` làm request/response phản ánh thông tin từ header proxy đáng tin. Khi handler gọi `request.getScheme()`, `getServerName()`, `getServerPort()`, `isSecure()` hoặc dùng `ServletUriComponentsBuilder`, kết quả có thể dựa trên địa chỉ public thay vì socket nội bộ.

**Quan trọng:** `ServletUriComponentsBuilder` từ Spring Framework 5.1 trở đi **không tự đọc trực tiếp** `Forwarded`/`X-Forwarded-*`. Nó xây URL từ request mà framework/container đã xử lý. Không được vừa tự parse forwarded headers trong controller, vừa bật `ForwardedHeaderFilter` rồi “sửa hai lần”.

### 4.1. ForwardedHeaderFilter trong ứng dụng Servlet

Với cấu hình `server.forward-headers-strategy=framework`, Boot có thể đăng ký `ForwardedHeaderFilter` phù hợp. Không cần thêm bean thứ hai theo thói quen, vì hai filter trùng chức năng có thể tạo xung đột hoặc khiến việc debug khó hơn.

Spring Framework có chế độ `removeOnly`: nhận dạng các header và **loại bỏ mà không dùng chúng**. Đây là lựa chọn hợp lý ở boundary không muốn app tin forwarded data; nó không giải quyết bài toán tạo URL public nếu đó là thông tin duy nhất về origin gốc.

Spring Framework các phiên bản mới có thể cho cấu hình chi tiết về dùng `Forwarded` hay `X-Forwarded-*` và xử lý `X-Forwarded-Prefix`; API và mặc định thay đổi theo bản phát hành. Trong ví dụ Java 17+ của bài, chỉ dùng scheme/host/port để tránh phụ thuộc vào chi tiết prefix của các bản khác nhau.

### 4.2. Tomcat và redirect tới context root

Tài liệu Spring Boot 3.3 lưu ý: nếu **Tomcat** chạy sau proxy kết thúc TLS, nên cân nhắc:

```properties
server.tomcat.redirect-context-root=false
```

Thuộc tính giúp forwarded protocol được áp dụng trước những redirect tới context root trong trường hợp liên quan. Đây không phải “bật HTTPS” cho toàn bộ ứng dụng, và không thay thế cấu hình proxy headers/host. Với Jetty, Undertow hoặc WebFlux/Reactor Netty, phải kiểm tra semantics của server tương ứng.

### 4.3. Khi nào không bật trust forwarded headers?

Nếu cổng 8080 của origin được lộ trực tiếp ra internet, client có thể gửi:

```http
Host: internal-app.example
X-Forwarded-Proto: https
X-Forwarded-Host: attacker.example
```

Ứng dụng bật `framework` nhưng không có trust boundary sẽ có nguy cơ tạo liên kết về domain giả mạo. Do đó **trước khi bật framework/native trên production**, cần khóa network để origin chỉ nhận từ proxy được phép và cấu hình proxy **xóa/ghi đè header từ client**.

## 5. Trust boundary: vị trí phải đặt đúng

### 5.1. Không có cách nào để Spring tự nhận biết header thật hay giả

`ForwardedHeaderFilter` nhận giá trị header HTTP. Tự bản thân header không có chữ ký/độ tin cậy; một client có thể gửi cùng tên nếu proxy cho qua. Hướng bảo vệ đúng là:

1. Edge proxy chỉ chấp nhận hostname và TLS/port công khai hợp lệ.
2. Edge **loại bỏ `Forwarded` và toàn bộ `X-Forwarded-*` không tin cậy** từ request client.
3. Edge tự phát các giá trị mà nó thực sự biết: public scheme/host/port, client IP theo chính sách.
4. Nếu có CDN/LB đứng trước edge, chỉ tin thông tin từ hop đó sau khi xác minh đường kết nối/allowlist và quy tắc rewrite.
5. Origin chỉ mở trên network nội bộ, không cho người dùng trực tiếp truy cập cổng app.
6. Ứng dụng sử dụng dữ liệu đã xử lý của request, không parse thủ công header raw.

Đặc biệt nguy hiểm khi dùng `X-Forwarded-Host` để tạo link reset password hay liên kết trong email: một giá trị độc hại có thể gây **Host header poisoning/password-reset link injection**. Các URL bảo mật, callback nhận từ bên thứ ba và link trong email nên được sinh từ **public-base-url cấu hình/allowlist** thay vì phụ thuộc hoàn toàn request headers.

### 5.2. NGINX tại TLS edge

Ví dụ NGINX **nhận TLS trực tiếp từ browser** tại host đã được vận hành tin cậy. Đây là snippet một `server` block thuộc ngữ cảnh `http`; các đường dẫn chứng chỉ là minh họa và cần thay trong hạ tầng thật:

```nginx
server {
    listen 443 ssl;
    server_name shop.example.test;

    ssl_certificate     /etc/nginx/tls/fullchain.pem;
    ssl_certificate_key /etc/nginx/tls/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;

        # Chỉ chuyển hostname đã được virtual host/allowlist chấp nhận.
        proxy_set_header Host $host;

        # Xóa RFC 7239 do client tự cung cấp.
        proxy_set_header Forwarded "";

        # Ghi đè các X-Forwarded-* cần dùng, không chuyển dữ liệu thô.
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Host  $host;
        proxy_set_header X-Forwarded-Port  $server_port;
        proxy_set_header X-Forwarded-For   $remote_addr;

        # Không có public prefix ở topology này.
        proxy_set_header X-Forwarded-Prefix "";
    }
}
```

**Cần thêm cấu hình thực tế**: default vhost xử lý hostname lạ, HTTP→HTTPS redirect ở listener 80 nếu sản phẩm cần, certificate renewals, TLS hardening, network ACL, logging, timeout, upload/body limits và deployment orchestration. `server_name` trong một server block **không tự thay thế** host allowlist cho mọi request: phải bảo đảm hostname không khớp bị từ chối, thay vì rơi vào vhost mặc định vẫn proxy vào app.

Tại sao dùng `proxy_set_header X-Forwarded-For $remote_addr;` thay vì luôn dùng `$proxy_add_x_forwarded_for`? Trong ví dụ **edge đầu tiên trực tiếp nhìn client**, đặt từ `$remote_addr` tránh nối một `X-Forwarded-For` giả do client gửi. Với nhiều proxies/CDN hợp lệ, cần một chuỗi chính sách trusted hops/real IP riêng; không được đơn giản giữ nguyên dữ liệu do Internet gửi vào.

**Không copy y nguyên nếu NGINX đứng sau CDN**: lúc đó `$scheme` ở NGINX có thể là HTTP nội bộ và `$remote_addr` là IP của CDN, không phải browser. Phải xác lập chặng đáng tin, xác định public protocol tại edge phù hợp, và chỉ dùng thông tin do CDN/LB được xác thực chuyển đến.

### 5.3. Đường nội bộ và đường public có thể khác nhau

Nếu NGINX đặt trong container khác, `127.0.0.1:8080` trỏ tới **container NGINX**, không phải Spring Boot. Với Docker Compose hay Kubernetes, dùng DNS service phù hợp (ví dụ `http://spring-app:8080`) và xác nhận network isolation.

Khi triển khai HTTPS public nhưng HTTP origin, bảo mật đường nội bộ phụ thuộc network. Nếu hop nội bộ đi qua mạng không đáng tin, cần thêm TLS/mTLS hoặc phương án bảo vệ thích hợp, không mặc định “đã có HTTPS ở browser” nghĩa là mọi hop đều mã hóa.

## 6. Ví dụ Spring Boot 3.x Java 17+: redirect, absolute links và cookies

Ứng dụng sau có các endpoint:

- `GET /inspect`: hiển thị scheme, host, port, secure và hai absolute links.
- `GET /go`: chuyển tới `/done` bằng `redirect:`.
- `GET /done`: đích redirect trả văn bản `done`.
- `POST /session`: tạo một `HttpSession` để quan sát session cookie.
- `POST /demo-cookie`: tạo một cookie trình duyệt minh họa với `Secure`, `HttpOnly`, `SameSite` và `Path`.

Đây là ví dụ **Spring Boot MVC, không dùng Spring Security và không tạo đăng nhập thật**. Không dùng endpoint `/session` và `/demo-cookie` như chính sách xác thực production.

### 6.1. Tạo dự án

Tạo project từ [Spring Initializr](https://start.spring.io/), chọn Java 17+, Spring Boot **3.x** (ví dụ 3.3.x), Gradle/Groovy và dependency **Spring Web**. Phần dependency chính của `build.gradle` do Initializr tạo:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

Đây là **đoạn Gradle**, không phải toàn bộ `build.gradle`. Initializr tạo Boot plugin, repository, Java toolchain và Gradle Wrapper phù hợp. Với Boot 4.x, có khác biệt tên starter, vì vậy dùng đúng major version tương thích code mẫu.

Tạo cấu trúc:

```text
src/main/
  java/demo/
    PublicUrlApplication.java
  resources/
    application.properties
```

### 6.2. Java hoàn chỉnh

File `src/main/java/demo/PublicUrlApplication.java`:

```java
package demo;

import java.time.Duration;
import java.util.Map;

import jakarta.servlet.http.HttpServletRequest;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpHeaders;
import org.springframework.http.ResponseCookie;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.ResponseBody;
import org.springframework.web.servlet.support.ServletUriComponentsBuilder;
import org.springframework.web.util.UriComponentsBuilder;

@SpringBootApplication
public class PublicUrlApplication {

    public static void main(String[] args) {
        SpringApplication.run(PublicUrlApplication.class, args);
    }
}

@Controller
class PublicUrlController {

    private final String publicBaseUrl;

    PublicUrlController(
            @Value("${app.public-base-url}") String publicBaseUrl) {
        this.publicBaseUrl = publicBaseUrl;
    }

    @GetMapping("/inspect")
    @ResponseBody
    public Map<String, String> inspect(HttpServletRequest request) {
        String derived = ServletUriComponentsBuilder
                .fromContextPath(request)
                .path("/done")
                .build()
                .toUriString();

        String canonical = UriComponentsBuilder
                .fromUriString(publicBaseUrl)
                .path("/done")
                .build()
                .toUriString();

        return Map.of(
                "scheme", request.getScheme(),
                "host", request.getServerName(),
                "port", Integer.toString(request.getServerPort()),
                "secure", Boolean.toString(request.isSecure()),
                "derivedUrl", derived,
                "configuredUrl", canonical);
    }

    @GetMapping("/go")
    public String go() {
        return "redirect:/done";
    }

    @GetMapping("/done")
    @ResponseBody
    public String done() {
        return "done\n";
    }

    @PostMapping("/session")
    @ResponseBody
    public String startSession(HttpServletRequest request) {
        request.getSession(true).setAttribute("demo", "created");
        return "session-created\n";
    }

    @PostMapping("/demo-cookie")
    public ResponseEntity<String> demoCookie() {
        ResponseCookie cookie = ResponseCookie
                .from("visitor_choice", "yes")
                .path("/")
                .secure(true)
                .httpOnly(true)
                .sameSite("Lax")
                .maxAge(Duration.ofHours(1))
                .build();

        return ResponseEntity.ok()
                .header(HttpHeaders.SET_COOKIE, cookie.toString())
                .body("cookie-set\n");
    }
}
```

**Vì sao ví dụ biên dịch được?**

- Chỉ `PublicUrlApplication` là `public` và tên file khớp class; `PublicUrlController` cùng package `demo` được Spring scan.
- `@Controller` dùng `return "redirect:/done"` cho redirect, không trả text body.
- `@ResponseBody` chỉ dùng trên handlers muốn viết JSON/text trực tiếp.
- `ServletUriComponentsBuilder.fromContextPath(request)` tạo URL từ scheme, host, port, context path của **request đã được chuẩn hóa**.
- `UriComponentsBuilder.fromUriString(publicBaseUrl)` tạo link từ một base URL **cấu hình đáng tin**, không dựa vào header client; cách này phù hợp khi tạo link email, OAuth callback cố định hoặc chạy không có HTTP request.
- `ResponseCookie` cho phép viết `Set-Cookie` với thuộc tính an toàn tường minh, nhưng **không tự làm cookie trở thành session**. Session container do `request.getSession(true)` quản lý riêng.

Code tạo `/inspect` ở mỗi request nhưng không lưu trạng thái trong field mutable. Trường `publicBaseUrl` là cấu hình cố định; nếu trong production cần nhiều tenant/host, hãy ánh xạ tenant đã xác thực tới **allowlist public origins** thay vì dùng bất kỳ `Host` được gửi đến.

### 6.3. application.properties

File `src/main/resources/application.properties`:

```properties
server.port=8080

# Chỉ dùng phía sau proxy tin cậy và origin không mở trực tiếp ra internet.
server.forward-headers-strategy=framework
server.tomcat.redirect-context-root=false

# Public URL cố định dùng cho liên kết bảo mật/email ngoài request.
app.public-base-url=https://shop.example.test

# Cookie session mặc định của Servlet container, dành cho môi trường HTTPS.
server.servlet.session.cookie.http-only=true
server.servlet.session.cookie.secure=true
server.servlet.session.cookie.same-site=lax
server.servlet.session.cookie.path=/
```

Đây là cấu hình **đích production sau TLS proxy**. Khi chạy local HTTP tại `http://localhost:8080`, cookie `Secure` sẽ được đánh dấu yêu cầu HTTPS; browser bình thường có thể không gửi nó trên HTTP (browser có ngoại lệ khi chạy localhost, không được dựa vào đó ở production). Có thể dùng một profile local riêng để thử cookie không Secure, nhưng không lấy giá trị đó làm production default.

Giá trị `app.public-base-url` là property ứng dụng tự định nghĩa, **không phải property có sẵn của Spring Boot**. Thay nó bằng hostname và optional path prefix đã được vận hành/allowlist công bố. Với `https://shop.example.test/portal`, builder `.path("/done")` sẽ tạo link `https://shop.example.test/portal/done` nếu base không có trailing slash bất thường.

### 6.4. Chạy

Từ thư mục có Gradle Wrapper:

```bash
./gradlew bootRun
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Đây là ứng dụng cần dependency Spring nên `javac PublicUrlApplication.java` đơn lẻ không đủ classpath; dùng Gradle/Maven tạo project rồi chạy. Nếu port 8080 bị chiếm, dừng process cũ hoặc cấu hình port khác và cập nhật lệnh kiểm thử.

### 6.5. Test local không có forwarded headers

```bash
curl -sS http://localhost:8080/inspect
```

Nếu chạy trực tiếp HTTP ở 8080 mà không có forwarded headers, ví dụ JSON có các giá trị tương đương:

```json
{
  "scheme": "http",
  "host": "localhost",
  "port": "8080",
  "secure": "false",
  "derivedUrl": "http://localhost:8080/done",
  "configuredUrl": "https://shop.example.test/done"
}
```

Thứ tự các property trong JSON không được đảm bảo; đây là output **giá trị minh họa**, tương ứng request cục bộ mặc định. Điểm cần nhìn là sự khác biệt giữa **derivedUrl** theo request và **configuredUrl** theo public URL cố định.

### 6.6. Test forwarded headers giả lập trong môi trường local

**Chỉ để thử tính năng trong môi trường phát triển cô lập**, có thể gửi header như một proxy tin cậy:

```bash
curl -sS \
  -H 'X-Forwarded-Proto: https' \
  -H 'X-Forwarded-Host: shop.example.test' \
  -H 'X-Forwarded-Port: 443' \
  http://localhost:8080/inspect
```

Với `server.forward-headers-strategy=framework`, output dự kiến:

```json
{
  "scheme": "https",
  "host": "shop.example.test",
  "port": "443",
  "secure": "true",
  "derivedUrl": "https://shop.example.test/done",
  "configuredUrl": "https://shop.example.test/done"
}
```

Về mặt HTTP, cổng mặc định 443 thường không xuất hiện trong URL `https://...`, dù `getServerPort()` có thể trả 443. JSON ở đây là **ví dụ minh họa một lần chạy có xử lý forwarded headers**; nếu cấu hình chưa tác dụng, derivedUrl vẫn là HTTP nội bộ.

Lệnh này cố tình minh họa rằng một **request trực tiếp** có thể giả forwarded headers khi app được cấu hình tin chúng. **Không cho phép người dùng Internet truy cập trực tiếp origin với cấu hình tin header này**. Bảo mật nằm ở proxy/network boundary, không nằm ở cặp tên header.

### 6.7. Test redirect

```bash
curl -i \
  -H 'X-Forwarded-Proto: https' \
  -H 'X-Forwarded-Host: shop.example.test' \
  -H 'X-Forwarded-Port: 443' \
  http://localhost:8080/go
```

Dự kiến response có status redirect, thường `302 Found`, với `Location` trỏ hợp lệ tới `https://shop.example.test/done` hoặc một **relative Location** được browser giải quyết đúng theo cấu hình redirect. Hành vi absolute/relative Location có thể phụ thuộc filter/container/redirect strategy; vì vậy hãy kiểm tra **URL đích mà browser thực sự sẽ sử dụng** và đừng khẳng định một chuỗi Location duy nhất cho mọi version.

**Không chạy `curl -L` theo redirect ra domain mẫu** nếu chưa có domain tương ứng đang hoạt động. Domain `example.test` trong ví dụ là reserved domain phục vụ tài liệu, không phải hostname thật để gọi qua Internet.

### 6.8. Test cookie và session

Thử tạo cookie minh họa:

```bash
curl -i -X POST http://localhost:8080/demo-cookie
```

Kiểm tra header tương đương:

```http
Set-Cookie: visitor_choice=yes; Path=/; Max-Age=3600; Secure; HttpOnly; SameSite=Lax
```

Các thuộc tính có thể xuất hiện theo thứ tự khác. Cookie là **host-only** khi không có `Domain`. Nếu browser truy cập public URL `https://shop.example.test`, cookie được cấp với scope host public; backend nội bộ `127.0.0.1` không phải một cookie Domain do browser tự nhìn thấy. Lệnh curl trực tiếp tới localhost chỉ cho thấy cấu trúc header, không chứng minh browser sẽ gửi cookie trên một site HTTPS thật.

Thử session do Servlet container quản lý:

```bash
curl -i -X POST http://localhost:8080/session
```

Trong MVC/Tomcat không có Spring Session và khi session được tạo, response thường có `Set-Cookie: JSESSIONID=...` cùng các thuộc tính theo cấu hình. Không trộn hai cookie này: `visitor_choice` là cookie demo được tạo bằng `ResponseCookie`; `JSESSIONID` là cookie tham chiếu tới `HttpSession` của servlet container.

Không đưa session ID thật vào log, chat hoặc commit. Khi test public qua HTTPS proxy, xem browser DevTools/`curl -i` để xác minh cookie `Secure`, `HttpOnly`, `SameSite`, `Domain`, `Path` và việc browser gửi lại cookie trong request đúng.

## 7. Tạo absolute URL: request-derived hay configured canonical?

### 7.1. Khi nào dùng URL suy từ request đã chuẩn hóa?

Dùng khi cần xây link self/reference theo **host public hợp lệ của request hiện tại**, ví dụ ứng dụng multi-host đã có host routing an toàn hoặc tạo resource link trong HTTP response:

```java
String url = ServletUriComponentsBuilder
        .fromContextPath(request)
        .path("/orders/42")
        .build()
        .toUriString();
```

Đây là **snippet** trong handler có `HttpServletRequest request`. Nó lấy scheme/host/port/context path từ request đã qua `ForwardedHeaderFilter` hoặc cơ chế native. **Không tự parse `X-Forwarded-Host`** trong controller để ghép URL: vừa khó xử lý port/prefix, vừa mở cửa host spoofing.

Có thể dùng `ServletUriComponentsBuilder.fromCurrentContextPath()` trong phạm vi MVC request thread, nơi `RequestContextHolder` có request. Không dùng cách này từ background scheduler, Kafka listener, email async worker hoặc startup task khi không có request hiện tại.

### 7.2. Khi nào phải dùng public-base-url cấu hình sẵn?

Một URL dùng trong email đổi mật khẩu, callback OAuth2, webhook, file export được chia sẻ hoặc job không có request nên dựa trên **canonical public base URL** được định nghĩa trong cấu hình/hệ thống tenant đã xác thực:

```properties
app.public-base-url=https://shop.example.test
```

```java
String link = UriComponentsBuilder
        .fromUriString(publicBaseUrl)
        .path("/orders/42")
        .build()
        .toUriString();
```

Đây là snippet giả sử `publicBaseUrl` đã được inject/validate, không phải chương trình độc lập. Ưu điểm: không phụ thuộc vào client-supplied Host/Forwarded headers, có thể dùng khi không có request. Nhược điểm: cần quản lý hostname theo môi trường và có thể cần ánh xạ tenant→public URL khi multi-tenant.

**Không dùng một biến do user truyền trực tiếp làm hostname**, ví dụ `?baseUrl=https://evil.example`. Nếu cho phép nhiều domain, định nghĩa danh sách chính thức, xác minh tenant/permission, host, scheme, port, prefix và không phát link tới domain tùy ý.

### 7.3. HTML link tương đối thường tốt hơn absolute link

Trong HTML nội bộ cùng website, một link tương đối hoặc root-relative thường ít phụ thuộc scheme/host hơn:

```html
<a href="/account">Tài khoản</a>
```

Nếu ứng dụng được public dưới `/portal`, hardcode `/account` sẽ **bỏ qua prefix**. Với Thymeleaf/Spring MVC, dùng expression tạo URL theo context path:

```html
<a th:href="@{/account}">Tài khoản</a>
```

Trong ứng dụng có forwarded prefix được xử lý đúng, expression/context có thể bảo toàn đường dẫn public theo framework. Hãy test khi reverse proxy rewrite prefix; không giả định mọi version tự động xử lý. Đối với email, hệ thống ngoài hoặc callback yêu cầu URL đầy đủ, dùng absolute URL từ nguồn được phép.

## 8. Tạo redirect đúng sau reverse proxy

### 8.1. Relative redirect trong Spring MVC

Controller `@Controller` có thể trả:

```java
@GetMapping("/signin-success")
public String signinSuccess() {
    return "redirect:/account";
}
```

Đây là snippet, không phải cơ chế đăng nhập thật. `redirect:` là một **view prefix đặc biệt**; framework tạo redirect response. Dấu `/` ở đầu giúp biểu thị đường dẫn ứng dụng theo semantics của redirect view, nhưng URL cuối vẫn chịu ảnh hưởng context path, prefix và redirect strategy của framework.

Nếu redirect sau **POST**, Spring MVC thường dùng response 302 trong cấu hình thường gặp; tùy kiến trúc có thể chọn HTTP 303 See Other để nhấn mạnh client chuyển thành GET theo PRG. Không gán 301/308 vĩnh viễn cho điều hướng login hoặc route tạm: cache/browser có thể giữ redirect lâu hơn mong muốn.

### 8.2. Redirect tuyệt đối tới URL ngoài

Khi cần chuyển tới trang khác có domain được phép, dùng allowlist và URI đã xác thực. Không:

```java
@GetMapping("/next")
public String next(@RequestParam String url) {
    return "redirect:" + url; // OPEN REDIRECT
}
```

Đây là **phản ví dụ**: attacker có thể tạo link hợp lệ trông như website của bạn nhưng chuyển sang phishing site. Dùng route ID ánh xạ tới danh sách đích cố định, hoặc URL parser/host allowlist nghiêm ngặt nếu nghiệp vụ cần external redirect. Không chỉ kiểm tra `startsWith("https://shop.example.test")` vì `shop.example.test.evil.test` cũng bắt đầu bằng chuỗi đó.

### 8.3. Login redirect loop và HTTPS termination

Vòng lặp thường gặp:

```text
Browser GET https://shop.example.test/login
 -> TLS proxy HTTP upstream
 -> Backend tưởng request là http
 -> Security yêu cầu https và redirect
 -> Browser lại GET https://shop.example.test/login
 -> Lặp
```

Sửa đúng gốc: proxy ghi protocol public một cách đáng tin, Boot xử lý forwarded headers, cấu hình HTTPS/security match điều kiện thực, và kiểm tra không có nhiều lớp cùng ép redirect sai. Không “chữa” bằng tắt bảo vệ HTTPS hoặc chấp nhận login qua HTTP.

### 8.4. Location 201 Created và URL trong API

Khi tạo resource trong REST API, response `201 Created` có thể cần header `Location` chứa URL public:

```java
URI location = UriComponentsBuilder
        .fromUriString(publicBaseUrl)
        .path("/api/orders/{id}")
        .buildAndExpand(orderId)
        .toUri();

return ResponseEntity.created(location).build();
```

Đây là **snippet**, giả sử có `publicBaseUrl` đã xác thực và `orderId`, không phải đoạn code runnable độc lập. Nếu hostname public phải được suy từ request theo tenant, chỉ lấy từ request đã xử lý forwarded headers **và đã xác minh host**. Không lấy raw `Host` vào header `Location` một cách không kiểm soát.

## 9. Path prefix công khai và vấn đề bị nhân đôi

Giả sử browser mở:

```text
https://portal.example.test/portal/orders/42
```

Nhưng NGINX chuyển tới Boot:

```text
http://127.0.0.1:8080/orders/42
```

Proxy đã **bỏ prefix `/portal`** ở đường upstream. Nếu Spring tạo absolute links từ path nội bộ mà không được thông báo prefix, link có thể thiếu `/portal`. Một hạ tầng dùng `X-Forwarded-Prefix: /portal` để mô tả public prefix.

### 9.1. NGINX rewrite prefix minh họa

**Snippet thay cho `location /` của một NGINX vhost đã có TLS và các forwarded header an toàn:**

```nginx
location /portal/ {
    proxy_pass http://127.0.0.1:8080/;

    proxy_set_header Host $host;
    proxy_set_header Forwarded "";
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-Host $host;
    proxy_set_header X-Forwarded-Port $server_port;
    proxy_set_header X-Forwarded-For $remote_addr;

    # Prefix công khai do chính proxy xác định, không tin input client.
    proxy_set_header X-Forwarded-Prefix /portal;
}
```

Dấu `/` sau `proxy_pass http://127.0.0.1:8080/;` có ý nghĩa khi NGINX thay thế phần URI khớp location; ở cấu hình này, public `/portal/go` được chuyển thành upstream `/go`. Đổi dấu slash mà không kiểm thử có thể dẫn đến upstream nhận sai path.

**Quan trọng:** khả năng áp dụng `X-Forwarded-Prefix` thay đổi theo Spring Framework và cách cấu hình filter. Một số phiên bản mới hơn cho chọn riêng việc dùng forwarded prefix. Do đó không lấy ví dụ trên làm lời hứa rằng mọi Boot version đều tự render `/portal` đúng mà không cần cấu hình. Hãy thử `/inspect` và `/go` qua chính vhost khi đã deploy.

### 9.2. Đừng vừa giữ prefix vừa cộng thêm prefix

Hai phương án phổ biến:

- Proxy giữ nguyên `/portal` và ứng dụng được cấu hình context path/route phù hợp.
- Proxy strip `/portal`, app chạy ở root và nhận forwarded prefix đáng tin để tạo public links.

Tránh vừa có `server.servlet.context-path=/portal` **vừa** proxy strip/ghi `X-Forwarded-Prefix=/portal` không phối hợp; có thể sinh `/portal/portal/...` hoặc route mismatch. Quyết định topology theo một hợp đồng cố định và test cả links, redirects, static assets, OAuth callback và cookie Path.

### 9.3. Prefix ảnh hưởng cookie Path ra sao?

Nếu website public dưới `/portal` nhưng cookie lại đặt `Path=/internal`, browser sẽ **không gửi** cookie khi yêu cầu `/portal/account`. Ngược lại `Path=/` bao phủ cả website, có thể rộng hơn cần thiết. Với session cookie, hãy xác định public scope:

```properties
server.servlet.session.cookie.path=/portal
```

Đây là lựa chọn cho deployment có prefix, **không** dùng đồng thời với `path=/` trong ví dụ root trước đó. Spring Session có thể dùng `CookieSerializer` riêng với cookie path dựa trên context path nội bộ; khi đó cần cấu hình path public phù hợp theo cơ chế Spring Session đang dùng.

Cookie `Path` là filter gửi cookie của browser, **không phải** cơ chế phân quyền hay bảo vệ cô lập hoàn toàn giữa các ứng dụng cùng host.

## 10. Cookie đúng địa chỉ công khai: browser nhìn thấy điều gì?

### 10.1. Cookie không chứa scheme/port theo cách URL chứa

Cookie không “trỏ về địa chỉ” bằng một URL đầy đủ. Browser quyết định lưu/gửi cookie chủ yếu theo **response host**, `Domain`, `Path`, `Secure`, `SameSite`, expiration và chính sách trình duyệt. Port không phải thuộc tính cookie scoping giống authority của URL; một cookie không được tách riêng chỉ vì port khác trên cùng host trong mọi quy tắc thông thường.

Ví dụ browser truy cập `https://shop.example.test/`, proxy chuyển vào `http://127.0.0.1:8080`, app trả:

```http
Set-Cookie: JSESSIONID=opaque-value; Path=/; Secure; HttpOnly; SameSite=Lax
```

Browser thấy response phát từ **shop.example.test**, không thấy hostname upstream trong `Set-Cookie`. Khi **không có Domain**, cookie thường là host-only, chỉ áp dụng cho host public mà response thuộc về. Đây là mặc định nên ưu tiên nếu chỉ một hostname cần phiên.

### 10.2. Những thuộc tính bắt buộc hiểu

| Thuộc tính | Ý nghĩa | Lỗi thường gặp |
| --- | --- | --- |
| `Secure` | Browser chỉ gửi cookie trên kết nối an toàn theo chính sách cookie | TLS kết thúc ở proxy, backend tưởng HTTP và không bật Secure |
| `HttpOnly` | JavaScript không đọc cookie qua `document.cookie` | Session ID bị lộ qua script hoặc công cụ không cần thiết |
| `SameSite=Lax` | Hạn chế một số request cross-site, thường phù hợp web app cùng site | Login/callback hoặc iframe cross-site không hoạt động như kỳ vọng |
| `SameSite=Strict` | Hạn chế cross-site mạnh hơn | Người dùng theo link từ site khác không mang cookie vào flow cần session |
| `SameSite=None` | Cho phép ngữ cảnh cross-site theo chính sách browser | Thiếu `Secure` khiến browser từ chối hoặc không gửi |
| `Domain` | Mở phạm vi cookie theo domain được phép | Đặt Domain thành host nội bộ hoặc rộng quá mức |
| `Path` | Giới hạn đường dẫn browser gửi cookie | App public `/portal` nhưng cookie chỉ có `Path=/internal` |
| `Max-Age` / `Expires` | Hạn tồn tại của cookie trong browser | Lẫn với thời gian sống của session ở server |
| `SameSite` và CORS | Hai lớp chính sách độc lập | Tưởng cho phép CORS là browser tự gửi session cookie |

**Secure không phụ thuộc backend có nhận HTTP hay không.** Trình duyệt đang dùng HTTPS bên ngoài; với session cookie production có thể cấu hình `server.servlet.session.cookie.secure=true` để đảm bảo `Secure` ngay cả khi origin nhận HTTP nội bộ.

### 10.3. Host-only hay Domain rộng?

Với ứng dụng chỉ ở `shop.example.test`, thường **không đặt `Domain`** để cookie là host-only. Nếu thật sự cần chia sẻ giữa `shop.example.test` và `account.example.test`, domain rộng hơn có thể cần, nhưng tăng phạm vi rủi ro; đánh giá subdomain trust và cookie name collision.

Không đặt `Domain=127.0.0.1` hoặc `Domain=internal-service.local` cho response công khai ở `shop.example.test`; browser sẽ không xem đó là domain hợp lệ của response.

### 10.4. Cookie prefixes

Browser có thêm các ràng buộc cho tên cookie bắt đầu bằng `__Secure-` hoặc `__Host-`:

- `__Secure-...` phải được thiết lập với `Secure` từ ngữ cảnh HTTPS phù hợp.
- `__Host-...` yêu cầu `Secure`, `Path=/` và **không có `Domain`**.

Ví dụ cho cookie ứng dụng riêng:

```http
Set-Cookie: __Host-visitor_choice=yes; Path=/; Secure; HttpOnly; SameSite=Lax
```

Đây là cookie minh họa. Không tự đổi tên cookie session container sang `__Host-...` nếu chưa cấu hình thống nhất browser, Spring Security, Spring Session và các integrations liên quan. Nếu app public dưới path `/portal` và cần `Path=/portal`, tên `__Host-` không phù hợp vì bắt buộc `Path=/`.

## 11. Servlet session cookie và Spring Session cookie

### 11.1. Session do embedded servlet container quản lý

Với Spring Boot MVC/Servlet thông thường, cookie tên `JSESSIONID` (trừ khi cấu hình khác) có thể dùng những property:

```properties
server.servlet.session.cookie.name=JSESSIONID
server.servlet.session.cookie.secure=true
server.servlet.session.cookie.http-only=true
server.servlet.session.cookie.same-site=lax
server.servlet.session.cookie.path=/
```

`server.servlet.session.cookie.domain` có thể đặt khi thật sự cần shared-domain cookie; đa số app chỉ một hostname nên **để trống**. `server.servlet.session.timeout` quản lý server-side inactivity, khác `cookie.max-age`. Khi browser còn ID mà server đã hết session, cookie không làm session cũ sống lại.

Spring Boot 3.3 hỗ trợ `server.servlet.session.cookie.same-site` cho các embedded servlet containers được auto-configure theo tài liệu chính thức. Luôn test `Set-Cookie` trong runtime thật, nhất là khi có security framework hoặc proxy rewrite cookie.

### 11.2. Session do Spring Session Redis/JDBC quản lý

Nếu có Spring Session, ứng dụng có thể dùng `DefaultCookieSerializer` để phát session cookie với tên thường là `SESSION`. Một bean `CookieSerializer` có thể cấu hình:

```java
@Bean
CookieSerializer cookieSerializer() {
    DefaultCookieSerializer serializer = new DefaultCookieSerializer();
    serializer.setCookieName("SESSION");
    serializer.setCookiePath("/");
    serializer.setUseSecureCookie(true);
    serializer.setUseHttpOnlyCookie(true);
    serializer.setSameSite("Lax");
    return serializer;
}
```

Đây là **snippet** chỉ dùng trong một dự án đã có Spring Session phù hợp, cần import `@Bean`, `CookieSerializer` và `DefaultCookieSerializer`. Nó **không** thuộc ứng dụng Java tối giản phần 6. Đừng thêm vào để “chữa cookie” khi ứng dụng chỉ sử dụng embedded Tomcat session: sẽ tạo thêm nhầm lẫn và dependency.

Spring Session có thể dùng giá trị `request.isSecure()` để quyết định Secure flag mặc định nếu không đặt rõ; request phải được hiểu đúng sau TLS proxy. Cấu hình rõ `setUseSecureCookie(true)` có thể thích hợp cho production HTTPS-only. Đối với domain và path, xem chính bean serializer nào là nguồn cuối cùng của `Set-Cookie`, đừng mặc định property Servlet container sẽ thay đổi mọi custom cookie.

### 11.3. Cookie tự tạo bằng ResponseCookie

`ResponseCookie` dùng cho cookie ứng dụng (preference, chọn giao diện...) và hỗ trợ rõ `Secure`/`HttpOnly`/`SameSite`/`Path`/`Domain`/`Max-Age`. Nó **không** giữ server session tự động và không thay thế công cụ xác thực. Nếu cookie chứa định danh nhạy cảm, cần thiết kế integrity/confidentiality, expiry, rotation và CSRF theo yêu cầu bảo mật, không chỉ gắn `HttpOnly`.

## 12. SameSite, CORS và các flow liên site

Tên nhóm bài có chữ **CORS**, nhưng CORS không giải quyết trực tiếp vấn đề URL public. Phân biệt:

- **Forwarded headers**: để server biết scheme/host/port/prefix công khai và tạo redirects/links đúng.
- **Cookie SameSite**: để browser quyết định gửi cookie theo top-level site và request context.
- **CORS**: để browser quyết định JavaScript ở origin A có được đọc response từ origin B hay không.
- **CSRF protection**: giảm nguy cơ trình duyệt gửi authenticated request thay đổi trạng thái trái ý người dùng.
- **Spring Security redirect_uri**: tham số callback phải khớp cấu hình provider và public URL; không được phép tùy ý theo untrusted Host.

### 12.1. CORS cho credentials

Nếu một SPA ở `https://ui.example.test` gọi API ở `https://api.example.test`, hai hostname có thể là **cross-origin** dù thuộc cùng site. Browser fetch thường cần `credentials: "include"` khi muốn gửi cookie cross-origin, API phải cho phép origin cụ thể và bật `Access-Control-Allow-Credentials: true` theo chính sách.

Không dùng `Access-Control-Allow-Origin: *` cùng credentials. CORS phải liệt kê/kiểm tra origin được phép; nếu framework phản chiếu bất kỳ Origin client gửi mà không kiểm soát, đó không phải cơ chế an toàn. Ngoài CORS, cookie vẫn phải được gửi theo `Domain`/`Path`/`Secure`/`SameSite`. Nếu thật sự cross-site (khác registrable site), `SameSite=None; Secure` có thể cần, nhưng browser còn có chính sách third-party cookie riêng.

### 12.2. OAuth2/OIDC redirect_uri và HTTPS

Giả sử ứng dụng đăng nhập qua OAuth2 provider. Khi bắt đầu login, Spring Security có thể tạo một redirect_uri public, ví dụ:

```text
https://shop.example.test/login/oauth2/code/provider
```

Nếu app tưởng scheme là `http`, URI tạo ra có thể là `http://shop.example.test/login/oauth2/code/provider` hoặc lộ `:8080`. Provider từ chối vì `redirect_uri` không trùng URI đã đăng ký hoặc browser bị chuyển sai protocol.

Giải pháp: cấu hình proxy trust đúng, public hostname/prefix đúng và đăng ký callback URI **chính xác** theo Spring Security/provider configuration; trong nhiều trường hợp có thể cấu hình redirect URI template một cách tường minh. Không sửa bằng cách đăng ký wildcard redirect URI rộng hoặc chấp nhận mọi Host để “linh hoạt”.

### 12.3. CSRF và SameSite

SameSite hỗ trợ giới hạn cookie trong vài ngữ cảnh cross-site, nhưng không thay thế CSRF token cho mọi luồng. Khi dùng authentication cookie/session, các POST/PUT/DELETE phải có CSRF strategy phù hợp. Trong Spring Security, kiểm tra token repository, form/SPA integration và callback exemption thật sự cần thiết. Đừng tắt CSRF toàn ứng dụng chỉ vì reverse proxy làm mất cookie.

## 13. Khi có CDN, ingress hoặc nhiều proxy hops

### 13.1. Ai là nguồn sự thật cho public origin?

Chuỗi có thể là:

```text
Browser HTTPS :443
 -> CDN / WAF
 -> Load Balancer
 -> Kubernetes Ingress
 -> Spring Boot HTTP :8080
```

Một hop nội bộ có thể nhìn HTTP dù browser đi HTTPS. Nếu ingress ghi `X-Forwarded-Proto: http` bằng `$scheme` của chính hop nội bộ, backend nhận thông tin sai. Cần chỉ rõ hop nào chịu trách nhiệm xác định **viewer scheme**, và các hop sau chỉ truyền giá trị đó khi nó đến từ **hop đã được xác thực và tin cậy**. Không lấy chuỗi header do browser đưa sẵn làm bằng chứng.

### 13.2. Bảng thông tin cần kiểm tra tại từng chặng

| Chặng | Scheme quan sát | Host quan sát | Giá trị forwarded nên có |
| --- | --- | --- | --- |
| Browser → CDN | HTTPS | shop.example.test | CDN biết viewer scheme và public host |
| CDN → LB | Có thể HTTP hoặc HTTPS | Có thể host origin/LB | CDN truyền metadata theo cấu hình tin cậy |
| LB → ingress | Có thể HTTP | Service/ingress hostname | Không làm rơi viewer scheme/host đã xác thực |
| Ingress → Boot | Thường HTTP nội bộ | Có thể service host | Forwarded/X-Forwarded-* được chuẩn hóa duy nhất |
| Boot controller | Request đã xử lý | Public origin | `getScheme()`/builder phản ánh địa chỉ public |

Đây là bảng tư duy, **không** cam kết hành vi mặc định của một CDN/LB cụ thể. AWS ALB, NGINX Ingress, Traefik, Envoy, Cloudflare, Spring Cloud Gateway và CDN khác nhau về cách đặt/append headers, tin client IP và xử lý prefix.

### 13.3. Tránh tin hai định dạng mâu thuẫn

Nếu request tới Boot chứa cả:

```http
Forwarded: proto=http;host=wrong.example
X-Forwarded-Proto: https
X-Forwarded-Host: shop.example.test
```

Phải hiểu chính xác framework ưu tiên nguồn nào theo phiên bản; đừng cho phép hai chuỗi giá trị mâu thuẫn lọt từ biên internet vào. Một policy dễ kiểm soát là **edge loại bỏ cả hai họ header do client gửi và chỉ tạo định dạng được phép**, các hops tiếp theo phối hợp nhất quán. Việc thêm bean/filter thủ công không thay thế trách nhiệm của edge.

## 14. Debug URL, redirect và cookie theo từng bước

### 14.1. Quan sát response từ browser-facing endpoint

```bash
curl -i https://shop.example.test/go
```

Kiểm tra `Location`:

- Có đúng scheme HTTPS không?
- Host có đúng hostname public không?
- Có lộ `localhost`/`10.x`/`:8080` không?
- Có giữ path prefix `/portal` nếu cần không?
- Có redirect loop không? Dùng `curl -v` và giới hạn số redirects, đừng chỉ bật `-L` không kiểm tra.

### 14.2. Kiểm tra cookie qua HTTPS

```bash
curl -i -X POST https://shop.example.test/session
```

Quan sát `Set-Cookie` và browser DevTools:

- `Secure` có hiện trên cookie phiên không?
- `HttpOnly` có đúng không?
- `SameSite` có tương thích flow login/iframe/SPAs không?
- `Domain` có bị đặt sai internal hostname hoặc quá rộng không?
- `Path` có đúng `/` hoặc `/portal` không?
- Browser có thông báo **blocked cookie** không, tại request nào?
- Cookie có được gửi lại trên request tới API/route cần session không?

Đừng dán session ID vào issue/chat public. Nếu cần chia sẻ log, che phần giá trị cookie và token.

### 14.3. So sánh origin và public URL

Trong **môi trường local cô lập**, so sánh:

```bash
curl -sS http://localhost:8080/inspect
```

với phiên bản mô phỏng forwarded headers ở mục 6.6 và phiên bản đi qua NGINX public. Nếu app vẫn thấy `scheme=http` sau proxy, xử lý forwarded headers chưa đúng; nếu app thấy `scheme=https` nhưng cookie thiếu Secure, kiểm tra cấu hình cookie/container hoặc Spring Session serializer.

### 14.4. Chẩn đoán redirect loop

Nếu request `https://.../login` luôn trở lại chính URL, thu thập một chuỗi có thứ tự status/Location, không follow vô hạn:

```bash
curl -v --max-redirs 5 -L https://shop.example.test/login
```

Kiểm tra nơi phát từng `Location` (proxy, Spring Security, controller), khác biệt scheme/host/path và cookies. Đừng tắt HTTPS redirect hoặc bỏ auth chỉ vì vòng lặp; tìm hop đang hiểu sai public protocol hoặc thiếu session/CSRF.

### 14.5. Thử host header poisoning trong môi trường kiểm thử

Từ một môi trường kiểm thử được cho phép, gửi hostname không có trong allowlist qua edge; kỳ vọng bị từ chối trước khi tới Boot. Nếu app tạo absolute link chứa hostname lạ, trust boundary/host validation chưa đủ. Không kiểm tra host injection trên hệ thống không được cấp quyền.

## 15. Những lỗi triển khai thường gặp

| Triệu chứng | Nguyên nhân có khả năng | Khắc phục |
| --- | --- | --- |
| `Location: http://...` dù browser dùng HTTPS | Proxy TLS termination nhưng Boot chưa xử lý forwarded protocol | Set đúng `X-Forwarded-Proto` và chiến lược forwarded headers |
| `Location: https://host:8080/...` | Port internal lọt vào URL | Forward public port hoặc dùng configured canonical URL |
| Redirect nhảy sang `localhost` | Host của socket/upstream bị dùng để sinh URL | Forward host public đúng, kiểm tra request-derived builder |
| Redirect có `/portal/portal` | Context path và forwarded prefix chồng nhau | Chọn một hợp đồng rewrite và test |
| Redirect thiếu `/portal` | Proxy strip prefix nhưng app không biết public prefix | Cấu hình prefix phù hợp theo framework version |
| Cookie session thiếu Secure | Servlet thấy HTTP nội bộ, cấu hình cookie mặc định chưa chuẩn | Ép `server.servlet.session.cookie.secure=true` khi production HTTPS |
| Browser không gửi cookie | Domain/Path/SameSite/Secure/expiry sai | Xem browser DevTools và request Cookie |
| Cookie bị gửi tới nhiều subdomains hơn cần | `Domain` quá rộng | Ưu tiên host-only cookie |
| Spring Session phát `SESSION` chứ không phải `JSESSIONID` | CookieSerializer của Spring Session | Kiểm tra session store và serializer |
| OAuth2 provider báo redirect_uri mismatch | Callback URL chứa http/internal host/prefix sai | Sửa public headers/canonical config và URI provider |
| Reset password link chứa domain lạ | Host/Forwarded header do client thao túng | Edge strip/overwrite, canonical allowlist |
| Login liên tục redirect về login | Cookie mất/blocked hoặc session không tồn tại | Kiểm tra cookie + session store + security flow |
| `X-Forwarded-Proto=https` nhưng `getScheme()=http` | Chưa bật đúng strategy hoặc filter bị bypass | Xác nhận Boot profile và hop headers |
| CORS đã bật nhưng cookie vẫn không gửi | CORS không thay `SameSite`/cookie scope | Cấu hình cả credentials, cookie và CSRF đúng |
| CDN thấy HTTPS nhưng ingress thấy HTTP | Trust chain làm mất viewer protocol | Sửa từng hop theo nguồn đáng tin |
| Proxy chỉnh `proxy_redirect` mà app vẫn tạo link sai | Chỉ rewrite một số Location, không sửa JSON/email/cookie | Giải quyết URL public ở gốc và kiểm thử các đường khác |

## 16. Security và vận hành production

### 16.1. Chặn truy cập trực tiếp origin

Nếu origin có thể được client ngoài Internet gọi thẳng, forwarded headers không đáng tin. Network policy, security groups, private bind/interface hoặc firewall cần hạn chế kết nối tới các proxies hợp lệ. Thêm Host allowlist và default-vhost reject ở edge. Đừng chấp nhận “chỉ biết URL port 8080 là đủ an toàn”: truy cập trực tiếp vẫn có thể xảy ra từ công cụ scan hay mạng nội bộ kém cô lập.

### 16.2. Không tin địa chỉ client để phân quyền

`X-Forwarded-For` có thể hữu ích cho audit/log/rate limit **khi** chuỗi trusted proxies được định nghĩa đúng. Không quyết định phân quyền tài khoản chỉ dựa vào IP lấy từ raw header. Nếu need allowlisting theo IP, dùng cơ chế đã nhận diện reliable client IP ở gateway/WAF và test spoofing.

### 16.3. Absolute URL nhạy cảm phải có allowlist

Email reset password, email verify, OAuth callback và file share links nên dùng cấu hình canonical/public base URL hoặc tenant URL map đáng tin. Validation nên kiểm tra URI scheme, hostname, port, path prefix và không cho phép user input tạo redirect target ngoài ý muốn.

### 16.4. Môi trường local khác production

Đừng bật `server.forward-headers-strategy=framework` ở cổng local rồi cho rằng bất kỳ client Internet nào gửi `X-Forwarded-Host` là hợp lệ. Trong dev, test header spoofing để hiểu rủi ro. Trong production, bảo vệ origin bằng proxy trust boundary, test HTTPS thật và browser cookie handling; cấu hình `Secure` làm cookie không hoạt động trên plain HTTP của một hostname public là đúng chính sách bảo mật.

### 16.5. Proxy header forwarding là dữ liệu đầu vào có ảnh hưởng bảo mật

Forwarded protocol/host quyết định redirect target, callback URL, security checks, cookie behavior và đôi khi CSRF origin comparisons. Thay đổi proxy config phải đi cùng regression tests. Không đẩy một sửa đổi trên ingress mà không kiểm tra cả Spring Security, HTML links, REST Location, session cookie và CDN cache rules.

### 16.6. Cookie name và sharing giữa ứng dụng

Nếu nhiều apps cùng host và cookie `Path=/` với trùng tên `JSESSIONID`, chúng có thể ghi đè/nhầm cookie trên browser. Chọn tên/path/scope phù hợp; nếu muốn share login giữa apps phải thiết kế session store, domain, authentication và CSRF, không chỉ đặt cùng cookie name. Cookie domain/path không cung cấp isolation bảo mật tuyệt đối; cần kiến trúc security rõ.

## 17. Bộ kiểm thử trước khi triển khai

| Trường hợp | Input | Tiêu chí đạt |
| --- | --- | --- |
| Không proxy local | GET `/inspect` trên localhost | `scheme=http`, internal link đúng local |
| Sau HTTPS proxy | GET `/inspect` qua public host | `scheme=https`, host/port public |
| Redirect thường | GET `/go` qua proxy | Location được browser giải thành public `/done` |
| Absolute link | GET `/inspect` | Request-derived và canonical đều hợp lệ với public host |
| HTTPS termination | POST `/session` | Cookie `Secure` hiện diện nếu chính sách yêu cầu |
| Custom cookie | POST `/demo-cookie` | `Path=/`, `Secure`, `HttpOnly`, `SameSite=Lax` |
| Không có cookie Domain | Browser request cùng host | Host-only, không lộ internal host |
| Prefix rewrite | GET `/portal/inspect` qua proxy | Link/redirect giữ `/portal` đúng một lần |
| OAuth callback | Login qua nhà cung cấp thử nghiệm | redirect_uri khớp URI đã đăng ký |
| Host header giả | Gửi hostname ngoài allowlist ở edge | Request bị từ chối, không sinh link độc hại |
| Forwarded giả từ client | Client gửi tự chế `X-Forwarded-*` vào edge | Edge bỏ/ghi đè, backend không tin giá trị lạ |
| CORS + cookie | Browser ở origin khác hợp lệ | Credentials/Origin/SameSite/CSRF theo policy |
| HTTP public | Truy cập `http://...` | Redirect tới HTTPS theo chiến lược, không vòng lặp |
| Mỗi môi trường | Dev/staging/prod public base URL riêng | Không xuất link staging trong email prod |

Nếu chỉ một test `curl -H X-Forwarded-Proto: https` thành công thì **chưa đủ** để xác minh production: nó chứng minh framework có thể đọc header, không chứng minh proxy trust boundary đang an toàn.

## 18. Câu hỏi ôn tập

**1.** Vì sao Spring Boot sinh `http://...:8080` trong `Location` dù browser đang ở HTTPS?  
**Đáp án:** Backend có thể chỉ thấy chặng HTTP nội bộ đến cổng 8080; forwarded protocol/host/port chưa được xử lý hoặc bị ghi đè sai.

**2.** `server.forward-headers-strategy=framework` có làm mọi header `X-Forwarded-Host` đáng tin không?  
**Đáp án:** Không. Cần trusted edge proxy loại bỏ header do client gửi và khóa truy cập trực tiếp origin. Framework không tự biết header do ai tạo.

**3.** Có thể tạo link email bằng `ServletUriComponentsBuilder.fromCurrentRequest()` trong scheduled job không?  
**Đáp án:** Không nên: job không có HTTP request được bind. Dùng public-base-url cấu hình/tenant map đáng tin.

**4.** Browser nhận cookie từ `https://shop.example.test` nhưng backend chạy `http://127.0.0.1:8080`. Có cần `Domain=127.0.0.1` không?  
**Đáp án:** Không; browser nhìn host public. Ưu tiên không đặt Domain (host-only) nếu chỉ một hostname cần cookie.

**5.** Nếu app public dưới `/portal`, cookie `Path=/internal` có gửi đến `/portal/orders` không?  
**Đáp án:** Không. Path phải khớp public request path theo quy tắc browser; thường đặt `Path=/portal` hoặc `/` tùy scope mong muốn.

**6.** Vì sao `SameSite=None` có thể vẫn không giúp cookie gửi cross-origin?  
**Đáp án:** Cần `Secure`, đúng Domain/Path, CORS credentials policy nếu có fetch XHR, CSRF và browser third-party cookie restrictions.

**7.** CORS có làm `request.getScheme()` đổi từ http thành https không?  
**Đáp án:** Không. Đó là nhiệm vụ trust forwarded headers/proxy, khác với quyền đọc cross-origin response.

**8.** Tại sao không dùng `return "redirect:" + nextUrl` khi `nextUrl` do client gửi?  
**Đáp án:** Nó tạo open redirect; phải dùng allowlist/route mapping xác thực.

**9.** Khi Spring Session Redis phát `SESSION` và custom `CookieSerializer`, property nào nên được kiểm tra để chỉnh cookie?  
**Đáp án:** Kiểm tra chính Spring Session cookie serializer và Boot integration; không suy rằng mọi `server.servlet.session.cookie.*` đều trực tiếp đổi custom cookie.

**10.** Nếu app dùng `server.servlet.context-path=/portal` và proxy đã gửi `X-Forwarded-Prefix=/portal`, lỗi gì có thể xảy ra?  
**Đáp án:** Tùy topology có thể nhân đôi prefix hoặc khiến route không match; chọn cách rewrite duy nhất và test URL/redirect/cookie.

## 19. Checklist triển khai

- [ ] Đã ghi rõ public origin/base URL và các internal upstream routes cho từng môi trường.
- [ ] Edge proxy chấp nhận đúng hostname, từ chối host lạ và giữ HTTPS public.
- [ ] Proxy xóa/ghi đè **cả** `Forwarded` và `X-Forwarded-*` từ client không đáng tin.
- [ ] Spring Boot `server.forward-headers-strategy` được chọn theo môi trường; origin không lộ trực tiếp.
- [ ] `request.getScheme()`, `getServerName()`, `getServerPort()` sau proxy phản ánh public request.
- [ ] Redirect `Location` không chứa http/internal host/port sai hoặc prefix bị lặp.
- [ ] Absolute links trong HTML, JSON, email, reset password và callbacks đúng public base URL.
- [ ] URL nhạy cảm được tạo từ canonical config/allowlist, không từ raw request headers.
- [ ] Nếu có public path prefix, proxy rewrite/context path và forwarded prefix được thử trên version thật.
- [ ] Session cookie có Secure/HttpOnly/SameSite/Domain/Path đúng browser-facing hostname/path.
- [ ] Phân biệt servlet container `JSESSIONID` với Spring Session `SESSION` và custom `CookieSerializer`.
- [ ] CORS credentials, SameSite và CSRF được kiểm tra cùng flow chứ không xem là một vấn đề.
- [ ] HTTPS redirect/OAuth2 login/Logout/Callback được thử ở trình duyệt thật, không có redirect loop.
- [ ] Đã thử direct-origin access và spoofed Host/Forwarded headers trong môi trường được phép.
- [ ] Đã kiểm tra nhiều hops CDN→LB→ingress, không hop nào ghi sai original public protocol.
- [ ] Theo dõi số redirect loops, login failures, cookie rejection, callback mismatch và link lỗi sau rollout.

## Tài liệu tham khảo

1. [Spring Boot 3.3 — Running Behind a Front-end Proxy Server](https://docs.spring.io/spring-boot/3.3/how-to/webserver.html)
2. [Spring Boot 3.3 — Servlet Web Applications and SameSite Cookies](https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html)
3. [Spring Boot 3.3 — Common Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/)
4. [Spring Framework — Forwarded Headers and ForwardedHeaderFilter](https://docs.spring.io/spring-framework/reference/web/webmvc/filters.html)
5. [Spring Framework 6.1 — ServletUriComponentsBuilder Javadoc](https://docs.spring.io/spring-framework/docs/6.1.8/javadoc-api/org/springframework/web/servlet/support/ServletUriComponentsBuilder.html)
6. [Spring Session 3.3 — Custom Cookie](https://docs.spring.io/spring-session/reference/3.3/guides/java-custom-cookie.html)
7. [Spring Session — DefaultCookieSerializer API](https://docs.spring.io/spring-session/docs/3.3.x/api/org/springframework/session/web/http/DefaultCookieSerializer.html)
8. [RFC 7239 — Forwarded HTTP Extension](https://www.rfc-editor.org/rfc/rfc7239)
9. [RFC 6265 — HTTP State Management Mechanism](https://www.rfc-editor.org/rfc/rfc6265)
10. [MDN — Set-Cookie](https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Set-Cookie)

**Kết luận:** muốn tạo redirect, absolute links và cookie đúng trong Spring Boot sau reverse proxy, phải giải quyết **cùng lúc** ba lớp: (1) trusted proxy bảo toàn và chuẩn hóa **public scheme/host/port/prefix**, (2) Spring Boot/framework tiêu thụ thông tin đó đúng cách hoặc dùng **canonical base URL** cho liên kết nhạy cảm, và (3) cookie được cấp theo **HTTPS/domain/path mà browser thấy**, không theo địa chỉ nội bộ của JVM. Test thật qua edge mới chứng minh cấu hình hoạt động và an toàn.
