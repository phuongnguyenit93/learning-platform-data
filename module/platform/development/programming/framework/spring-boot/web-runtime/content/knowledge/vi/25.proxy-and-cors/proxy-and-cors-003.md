# Phân biệt xử lý header chuyển tiếp tại máy chủ với tại Spring Framework

## 1. Vấn đề thực tế: request gốc là HTTPS nhưng ứng dụng nhìn thấy HTTP

Giả sử người dùng truy cập `https://app.example.test/portal/orders`. Load balancer hoặc reverse proxy nhận TLS, rồi chuyển request vào một Spring Boot application đang chạy HTTP tại `10.0.0.15:8080`. Với kết nối trực tiếp giữa proxy và ứng dụng, web server có thể nhận thấy:

```text
scheme       = http
serverName   = 10.0.0.15 hoặc backend host
serverPort   = 8080
remoteAddr   = địa chỉ IP của proxy
requestURI   = /orders
```

Nhưng URL mà người dùng thực sự thấy là:

```text
https://app.example.test/portal/orders
```

Nếu ứng dụng xây đường dẫn tuyệt đối, chuyển hướng đăng nhập, tạo liên kết email, phát sinh `Location` header hoặc đánh giá request có an toàn không, việc hiểu sai **scheme, host, port, client IP và external path prefix** có thể gây lỗi:

- `Location: http://10.0.0.15:8080/login` hoặc redirect sang HTTP dù browser đi qua HTTPS.
- Link trong JSON, HTML và thông báo email dùng host nội bộ.
- Redirect đến `/orders` thay vì `/portal/orders` khi proxy đã bỏ prefix.
- `HttpServletRequest.isSecure()` là `false` sau TLS termination, làm logic yêu cầu HTTPS hoặc xây URL hoạt động sai.
- Log/rate-limit nhầm tất cả request đều từ cùng IP proxy.
- Nếu tin header do client tự gửi, attacker có thể giả mạo public host/IP và làm hỏng link hoặc kiểm soát redirect.

Spring Boot có property **`server.forward-headers-strategy`** với ba lựa chọn `NONE`, `NATIVE`, `FRAMEWORK`. Bài này giải thích vì sao **NATIVE xử lý ở tầng web server/container**, còn **FRAMEWORK xử lý bằng các thành phần Spring Framework**, cách chọn và kiểm chứng, đồng thời phân biệt nó với **CORS**.

Phạm vi: Spring Boot **3.3.x**, Spring Framework 6.1.x, Java 17+; ví dụ thực hành dùng Spring Boot 3.3.13, Java 21, Spring MVC với embedded Tomcat; có so sánh Spring WebFlux. Các HTTP headers từ bên ngoài luôn được xem là **không đáng tin** cho đến khi đi qua ranh giới proxy có kiểm soát.

## 2. Header chuyển tiếp là gì và ai chịu trách nhiệm đặt chúng?

Một reverse proxy có thể gửi thông tin về request gốc qua header chuẩn RFC 7239 hoặc các header phổ biến có tiền tố `X-Forwarded-`:

| Header | Ý nghĩa thông thường | Ví dụ |
| --- | --- | --- |
| `Forwarded` | Header chuẩn RFC 7239, có tham số `for`, `proto`, `host`, có thể gồm nhiều hops | `for=192.0.2.10;proto=https;host=app.example.test` |
| `X-Forwarded-For` | Danh sách địa chỉ qua các proxy, liên quan client IP | `192.0.2.10, 10.0.0.5` |
| `X-Forwarded-Proto` | Scheme client đã sử dụng ở một proxy đáng tin | `https` |
| `X-Forwarded-Host` | Host public mà proxy muốn truyền | `app.example.test` |
| `X-Forwarded-Port` | Public-facing port | `443` |
| `X-Forwarded-Prefix` | Path prefix bên ngoài đã được proxy thêm hoặc bỏ khi chuyển tiếp | `/portal` |
| `X-Forwarded-Ssl` | Header non-standard một số hạ tầng dùng làm tín hiệu TLS | `on` |

Header `Forwarded` và nhóm `X-Forwarded-*` là **metadata được gửi trong HTTP**. Browser/HTTP client có thể tự tạo chúng khi không bị mạng trung gian chặn; Spring không thể tự xác định từ giá trị header rằng header do proxy hay attacker gửi.

Ví dụ một mô hình request:

```text
Browser: https://app.example.test/portal/orders
      |
      | TLS đến edge
      v
Trusted edge proxy
      | Tháo prefix /portal, chuyển tiếp HTTP đến :8080
      | X-Forwarded-Proto: https
      | X-Forwarded-Host: app.example.test
      | X-Forwarded-Port: 443
      | X-Forwarded-Prefix: /portal
      | X-Forwarded-For: 192.0.2.10
      v
Embedded web server: HTTP /orders
      |
      v
Spring MVC / WebFlux request handling
```

Tại edge, proxy phải **loại bỏ các giá trị `Forwarded` và `X-Forwarded-*` mà client không đáng tin đã gửi**, rồi chỉ thiết lập giá trị mới dựa trên kết nối và cấu hình được tin cậy. Nếu có nhiều proxies, các bên phải thống nhất **trusted chain** và cách biểu diễn chuỗi hops. Cách làm này cần cả **chính sách mạng** (chỉ nhận traffic backend từ proxies đáng tin) và **header normalization** ở edge.

## 3. Ba giá trị của `server.forward-headers-strategy`

Spring Boot 3.3 cung cấp enum `NONE`, `NATIVE`, `FRAMEWORK`:

```properties
# Chọn một trong ba giá trị:
server.forward-headers-strategy=NONE
# server.forward-headers-strategy=NATIVE
# server.forward-headers-strategy=FRAMEWORK
```

| Strategy | Nơi xử lý | Cơ chế chính | Khi phù hợp |
| --- | --- | --- | --- |
| `NONE` | Không bật xử lý forwarded headers của Boot | Server/app nhìn nhận thông tin của kết nối backend theo mặc định | Không dùng proxy hoặc không muốn tin header chuyển tiếp |
| `NATIVE` | Embedded server/container | Tính năng riêng của Tomcat, Jetty, Undertow hoặc Reactor Netty | Proxy gửi các header mà server hỗ trợ trực tiếp; thường `X-Forwarded-For` và `X-Forwarded-Proto` |
| `FRAMEWORK` | Spring Framework | Servlet `ForwardedHeaderFilter`; WebFlux `ForwardedHeaderTransformer` | Cần tính năng xử lý header ở mức Spring, đặc biệt host/scheme/prefix và URL/redirect khi native chưa đủ |

**Chọn một chiến lược có chủ đích**. Tránh vừa bật native rewrite, vừa tự cài một `ForwardedHeaderFilter` xử lý lại cùng headers mà không hiểu thứ tự; dễ có kết quả lệch nhau hoặc không đoán được header đã được tiêu thụ ở tầng nào.

Theo tài liệu Spring Boot 3.3, trên **supported cloud platforms** chiến lược mặc định có thể là `NATIVE`; ở các môi trường khác, mặc định là `NONE`. Vì vậy hai môi trường cùng code mà không khai báo property có thể khác hành vi. Khi cấu hình production phía sau proxy, nên **đặt property tường minh** và kiểm tra effective configuration của môi trường thực.

Một điểm tinh tế: `NONE` nghĩa là **Boot không tự xử lý** forwarded headers; nó không có nghĩa các header thô đã bị xóa khỏi `HttpServletRequest.getHeader(...)`. Nếu chính ứng dụng hoặc thư viện khác tự đọc các header ấy, hoặc operator đã cài Valve/filter thủ công, cần kiểm tra riêng. Không dùng `getHeader("X-Forwarded-For")` làm IP đáng tin chỉ vì đặt `NONE`.

## 4. Xử lý `NATIVE`: container hiểu request trước các filter/controller

Khi dùng `NATIVE`, Spring Boot để **HTTP server/container** làm công việc chuyển thông tin từ forwarded headers vào các API request tương ứng. Với Spring MVC mặc định dùng embedded Tomcat, thành phần tiêu biểu là **Tomcat `RemoteIpValve`**.

Sơ đồ trách nhiệm:

```text
TCP connection từ proxy
       |
       v
Tomcat Connector
       |
       v
Tomcat RemoteIpValve (khi NATIVE và được cấu hình phù hợp)
       |  Đọc header theo cấu hình/trust rules
       |  Điều chỉnh perceived remote IP/scheme/secure/host/port
       v
Servlet filter chain (Spring Security, v.v.)
       |
       v
DispatcherServlet -> Controller
```

Vì thao tác ở **container pipeline**, nhiều phần của ứng dụng có thể thấy các request properties đã được điều chỉnh từ trước khi Spring MVC chạy. Cơ chế cụ thể phụ thuộc Tomcat, Jetty, Undertow hoặc Reactor Netty; không nên gọi mọi implementation là “RemoteIpValve” vì đó là khái niệm của **Tomcat**.

Ví dụ khai báo khi proxy gửi `X-Forwarded-For` và `X-Forwarded-Proto`:

```properties
server.forward-headers-strategy=NATIVE
server.tomcat.redirect-context-root=false
```

`server.tomcat.redirect-context-root=false` đặc biệt đáng chú ý khi **Tomcat đứng sau TLS-terminating proxy**: theo hướng dẫn Spring Boot 3.3, nó cho phép `X-Forwarded-Proto` được xét trước một số redirect do context root gây ra.

Những property Tomcat liên quan:

```properties
server.tomcat.remoteip.remote-ip-header=x-forwarded-for
server.tomcat.remoteip.protocol-header=x-forwarded-proto

# Cần xác định rõ các proxy đáng tin theo topology thực tế.
# server.tomcat.remoteip.internal-proxies=...
```

Tên `remote-ip-header`/`protocol-header` dùng khi cần đổi **tên header** mà proxy gửi. Thuộc tính `internal-proxies` liên quan kiểm soát proxy nội bộ được Tomcat tin cậy; nó dùng quy tắc riêng (regex trong `RemoteIpValve`) và không được điền tùy tiện hoặc làm thành một mẫu cho phép mọi địa chỉ. Cần kiểm tra default trust rules và địa chỉ socket của **proxy gần ứng dụng nhất**, bao gồm IPv4/IPv6.

Tùy server implementation, `NATIVE` có thể không hỗ trợ tất cả các header hoặc không xử lý external prefix như Spring Framework. **Spring Boot 3.3 nêu rõ**: với phổ biến `X-Forwarded-For` và `X-Forwarded-Proto`, `NATIVE` thường đủ; nếu không đủ, cân nhắc `FRAMEWORK`.

## 5. Xử lý `FRAMEWORK`: Spring bao request hoặc biến đổi request

Với Spring MVC/Servlet:

```properties
server.forward-headers-strategy=FRAMEWORK
```

Spring Boot dùng **Spring Framework `ForwardedHeaderFilter`**. Filter này nhìn forwarded headers từ request, tạo **request/response wrappers** để code phía sau thấy scheme/host/port và các thông tin thích hợp theo góc nhìn public client. Nó cũng **loại các forwarded header liên quan khỏi request đã được bọc** để tầng sau không tiếp tục bị ảnh hưởng bởi cách đọc raw headers một cách ngẫu nhiên.

```text
Tomcat HTTP Connector -> Servlet request ban đầu
       |
       v
ForwardedHeaderFilter (Spring Framework)
       |  Đọc Forwarded / X-Forwarded-*
       |  Bọc HttpServletRequest / HttpServletResponse
       v
Các filters/controller nhìn request wrapper
       |
       v
Spring MVC HandlerMapping, URL builder, redirect
```

Điểm quan trọng là **tầng xử lý khác**: `FRAMEWORK` không biến Tomcat thành một proxy hoặc thay đổi TLS trên kết nối HTTP; nó giúp Spring nhìn request theo thông tin mà proxy đã xác nhận. Việc request socket thật ở backend là HTTP không đổi. Vì vậy kiểm tra transport security thực tế phải dựa trên cấu hình TLS ở proxy/backend, không chỉ `request.isSecure()` sau khi rewrite.

`ForwardedHeaderFilter` cũng can thiệp xử lý redirect bằng wrapper response, giúp một số `sendRedirect(...)` hoặc việc tạo URL dựa trên request phản ánh host/scheme public. Với `X-Forwarded-Prefix`, Framework có thể hỗ trợ kịch bản application nằm dưới một external path prefix mà proxy đã strip. **Đừng khẳng định mọi biến thể prefix/rewrite đều hoạt động giống nhau**: còn phụ thuộc cách proxy viết prefix, framework version, servlet context path và loại redirect.

Trong Spring WebFlux tương ứng là **`ForwardedHeaderTransformer`**, vốn biến đổi `ServerHttpRequest` trước khi xử lý reactive request. Không đăng ký `ForwardedHeaderFilter` của Servlet rồi mong nó áp dụng cho Reactor Netty/WebFlux.

## 6. So sánh chi tiết giữa NATIVE và FRAMEWORK

| Tiêu chí | `NATIVE` | `FRAMEWORK` |
| --- | --- | --- |
| Ai đọc header? | Server/container thực tế | Spring Framework |
| Với Servlet Tomcat | Thường là `RemoteIpValve` | `ForwardedHeaderFilter` |
| Với WebFlux | Server adapter/native support phù hợp | `ForwardedHeaderTransformer` |
| Thời điểm áp dụng | Trong pipeline web server, trước servlet filter chain | Trong filter/request-adapter của Spring |
| Điều chỉnh scheme/secure/host/port | Theo hỗ trợ của server + cấu hình | Theo cách xử lý Forwarded/X-Forwarded của Spring |
| Xử lý `X-Forwarded-For` | Tomcat Valve có logic remote IP và trusted proxy chain | Có logic framework riêng; không mặc nhiên giống mọi giá trị remote IP native |
| `X-Forwarded-Prefix` | Không bảo đảm được hỗ trợ đầy đủ ở mọi container | Thường phù hợp hơn cho prefix dùng bởi Spring URL builders |
| Redirect do container tạo quá sớm | Có thể cần cấu hình Tomcat chuyên biệt | Filter có thể không sửa redirect đã gửi **trước khi filter chạy** |
| `HttpServletRequest` | Có thể đã được chỉnh ở container level | Wrapper cung cấp request view cho downstream |
| Kiểm soát proxy tin cậy | Tùy container (ví dụ Tomcat internal/trusted proxy rules) | Framework **không thể tự biết** forwarded header đến từ proxy đáng tin |
| CORS | Không tự cấp quyền cross-origin | Không tự cấp quyền cross-origin |
| Lời khuyên | Dùng khi native đủ cho topology và có trust config đúng | Dùng khi tính năng Spring wrapper/prefix cần thiết và edge đã sanitize |

**Không có lựa chọn nào tự động làm một mạng proxy không đáng tin trở nên an toàn.** Nếu attacker có thể trực tiếp gọi backend kèm `X-Forwarded-Host: evil.example`, việc chấp nhận header ấy có thể dẫn tới URL độc hại hoặc host-header injection.

`FRAMEWORK` còn có chế độ **`removeOnly`** trong API `ForwardedHeaderFilter` cho cấu hình thủ công: chỉ loại headers, **không sử dụng chúng**. Đây là lựa chọn riêng trong tình huống muốn loại thông tin không tin cậy; nó không đồng nghĩa `server.forward-headers-strategy=NONE`, vì `NONE` không tự xóa header thô. Nếu Boot đã tự đăng ký filter theo `FRAMEWORK`, không thêm một filter thứ hai một cách tùy tiện.

## 7. Cấu hình proxy: điểm quan trọng nhất là trust boundary

Một hướng xử lý an toàn cần có **ranh giới tin cậy ở edge**:

1. Chỉ proxy/load balancer đã được phép kết nối đến backend; dùng firewall, security groups, Kubernetes NetworkPolicy hoặc mTLS nội bộ theo hạ tầng.
2. Edge **xóa** các header `Forwarded` và `X-Forwarded-*` từ client không đáng tin, gồm cả dạng chuẩn RFC 7239.
3. Edge tạo lại **một convention header nhất quán** theo kết nối đã xác minh: host, proto, port, IP và prefix nếu cần.
4. Nếu có nhiều proxy hops, xác định rõ proxy nào tiếp tục thêm/ghi đè danh sách `for` và IP nào được coi là client có thể tin cậy.
5. Spring Boot cấu hình `NATIVE` hoặc `FRAMEWORK` khớp dữ liệu edge thực tế, và application không tự parse raw headers ở các phần khác.

**Ví dụ NGINX minh họa** khi chính NGINX là **edge duy nhất**, có virtual host công khai `app.example.test`, HTTPS termination ở NGINX và Spring Boot nghe localhost port 8080. Đoạn này chỉ là khối `location`, **không phải cấu hình TLS hoàn chỉnh** (cần server, listen 443 ssl, certificate, proxy/firewall riêng):

```nginx
location /portal/ {
    # Dấu / cuối proxy_pass: strip prefix /portal/ cho backend.
    proxy_pass http://127.0.0.1:8080/;

    # Không chuyển nguyên Forwarded do client gửi vào backend.
    proxy_set_header Forwarded "";

    # Canonical public host, không phản chiếu tùy ý Host của client.
    proxy_set_header Host app.example.test;
    proxy_set_header X-Forwarded-Host app.example.test;
    proxy_set_header X-Forwarded-Proto https;
    proxy_set_header X-Forwarded-Port 443;
    proxy_set_header X-Forwarded-Prefix /portal;

    # Chỉ dùng kiểu này khi NGINX thực sự là edge nhận client.
    proxy_set_header X-Forwarded-For $remote_addr;
}
```

Đoạn `proxy_set_header Forwarded ""` yêu cầu NGINX không chuyển tiếp header RFC 7239 đến backend; NGINX còn ghi đè những header X-Forwarded liệt kê bằng giá trị từ cấu hình/kết nối. Nếu có thêm các header forwarded khác mà backend xử lý, phải sanitize **tất cả** chúng theo chính sách, không chỉ những tên được nêu. Kiểm tra cấu hình proxy thực của hạ tầng trước khi coi đây là an toàn.

Nếu hệ thống có **CDN trước NGINX**, `$remote_addr` là IP kết nối từ CDN, không chắc là IP của browser. Khi đó cần cấu hình real-IP/trusted proxies cho NGINX và xử lý chuỗi client IP đúng topology; không đổi `X-Forwarded-For` sang `$proxy_add_x_forwarded_for` một cách mù quáng vì có thể giữ giá trị do client tự bịa.

## 8. Tình huống prefix `/portal`: điểm khác biệt quan trọng

Giả sử client gọi:

```text
GET https://app.example.test/portal/orders
```

Proxy strip `/portal` trước khi chuyển backend:

```text
GET http://127.0.0.1:8080/orders
X-Forwarded-Proto: https
X-Forwarded-Host: app.example.test
X-Forwarded-Prefix: /portal
```

Controller nội bộ vẫn map `@GetMapping("/orders")`. Nhưng khi nó tạo **link tuyệt đối ra ngoài** hoặc redirect, kết quả lý tưởng là:

```text
https://app.example.test/portal/orders
```

không phải:

```text
http://127.0.0.1:8080/orders
https://app.example.test/orders
```

`NATIVE` đủ cho `X-Forwarded-For`/`X-Forwarded-Proto` trong nhiều cấu hình Tomcat nhưng **không có cam kết portable rằng native container hiểu `X-Forwarded-Prefix`**. `FRAMEWORK` là giải pháp Spring Boot khuyến nghị khi native support không đủ. Với MVC, `ForwardedHeaderFilter`/Spring request wrapper có thể giúp `ServletUriComponentsBuilder` và các Spring link builders nhận biết prefix được forward.

Cần kiểm tra thực tế vì path có thể còn phụ thuộc `server.servlet.context-path`, proxy `proxy_pass` có dấu `/` cuối, servlet mapping và version xử lý prefix. **Không chỉ nhìn `request.getRequestURI()` để kết luận URL bên ngoài đã đúng**. Hãy gọi API thực sự sinh `Location`/HATEOAS link và kiểm tra từ public URL.

`X-Forwarded-Prefix` không phải cài đặt để “chuyển” mọi API endpoint sang `/portal/**` bên trong ứng dụng; nó biểu diễn public prefix cho các thành phần nhận thức về forwarded headers. Routing trong backend vẫn phụ thuộc path mà proxy thật sự gửi.

## 9. Ví dụ Spring Boot MVC chạy được để quan sát khác biệt

Dựng một ứng dụng nhỏ trả về request metadata được Servlet API nhìn thấy và một endpoint sinh absolute redirect. Dùng **Spring Boot 3.3.13, Java 21** trên project có Gradle Wrapper.

**`build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**`src/main/java/com/example/forward/ForwardApplication.java`:**

```java
package com.example.forward;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ForwardApplication {
    public static void main(String[] args) {
        SpringApplication.run(ForwardApplication.class, args);
    }
}
```

**`src/main/java/com/example/forward/RequestInfoController.java`:**

```java
package com.example.forward;

import java.net.URI;

import jakarta.servlet.http.HttpServletRequest;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.support.ServletUriComponentsBuilder;

@RestController
public class RequestInfoController {

    public record RequestView(
            String scheme,
            String host,
            int port,
            boolean secure,
            String remoteAddress,
            String requestUri,
            String contextPath,
            String visibleUrl) {
    }

    @GetMapping("/inspect")
    public RequestView inspect(HttpServletRequest request) {
        return new RequestView(
                request.getScheme(),
                request.getServerName(),
                request.getServerPort(),
                request.isSecure(),
                request.getRemoteAddr(),
                request.getRequestURI(),
                request.getContextPath(),
                ServletUriComponentsBuilder.fromCurrentRequestUri()
                        .toUriString());
    }

    @GetMapping("/jump")
    public ResponseEntity<Void> jump() {
        URI location = ServletUriComponentsBuilder
                .fromCurrentContextPath()
                .path("/inspect")
                .build()
                .toUri();

        return ResponseEntity.status(HttpStatus.FOUND)
                .location(location)
                .build();
    }
}
```

`RequestView` là Java record nên phù hợp Java 17+. `visibleUrl` được tính bằng Spring `ServletUriComponentsBuilder` từ request hiện hành; nếu proxy rewrite, trường này giúp phát hiện sự khác biệt so với URL public mà client thấy. `jump()` tạo `Location` từ context path hiện hành, là một phép kiểm chứng **absolute URL generation**, không chỉ thay đổi JSON hiển thị.

**`src/main/resources/application.properties`:**

```properties
server.port=8080
server.forward-headers-strategy=NONE

# Khi thử với Tomcat + TLS terminating proxy:
# server.tomcat.redirect-context-root=false
```

Chạy:

```bash
./gradlew bootRun
```

Test từ loopback:

```bash
curl -s http://127.0.0.1:8080/inspect
curl -i http://127.0.0.1:8080/jump
```

Với `NONE`, scheme/host/port của `inspect` sẽ phản ánh kết nối HTTP backend. `Location` của `jump` có thể tương tự `http://127.0.0.1:8080/inspect`. `remoteAddress` là IP của socket client/proxy đang kết nối đến server. Giá trị host, địa chỉ và status headers thực tế còn phụ thuộc cách gọi/cấu hình mạng; chỉ so sánh **các trường quan tâm**, không dựa trên toàn bộ JSON cố định.

## 10. Thí nghiệm ba chế độ trên cùng một request

Trong môi trường **development cô lập**, có thể giả lập một trusted proxy bằng cách gửi header thủ công từ localhost. Cách này chỉ phục vụ học hành vi rewrite; **không cho phép public client gửi header tùy ý trên production backend**.

Trước tiên chạy chế độ `NONE` của ví dụ:

```bash
curl -s -H 'X-Forwarded-Proto: https' \
  -H 'X-Forwarded-Host: app.example.test' \
  -H 'X-Forwarded-Port: 443' \
  -H 'X-Forwarded-Prefix: /portal' \
  http://127.0.0.1:8080/inspect
```

Với `NONE`, các thông tin scheme/host/port thường vẫn ở góc nhìn backend, vì Boot không bật xử lý header. Đổi thành:

```properties
server.forward-headers-strategy=NATIVE
```

restart, gửi cùng request. Với Tomcat được cấu hình/trust đúng, có thể thấy scheme `https`, `secure=true` và thông tin được container xử lý. Không bắt buộc public prefix được thể hiện như `FRAMEWORK`; nếu Tomcat không tin socket peer hoặc config RemoteIpValve không áp dụng, cần kiểm tra các điều kiện native.

Sau đó đổi sang:

```properties
server.forward-headers-strategy=FRAMEWORK
```

restart, gửi lại request và so sánh. Thử thêm:

```bash
curl -i -H 'X-Forwarded-Proto: https' \
  -H 'X-Forwarded-Host: app.example.test' \
  -H 'X-Forwarded-Port: 443' \
  -H 'X-Forwarded-Prefix: /portal' \
  http://127.0.0.1:8080/jump
```

Quan sát **`Location`** và các trường `scheme`, `host`, `port`, `contextPath`, `visibleUrl`. Với `FRAMEWORK`, trong trường hợp headers hợp lệ, các link/redirect được xây thông qua Spring có khả năng phản ánh external origin và prefix tốt hơn native container không hỗ trợ prefix.

**Lưu ý về stdout:** Mã JSON `remoteAddress`, `requestUri`, `contextPath`, `visibleUrl` và headers có thể khác giữa container/OS/version; bài này không dựng một JSON “chính xác” chung cho cả ba chế độ. Kết quả mong muốn là **so sánh theo từng thuộc tính**, không khẳng định một IP hoặc một `Location` cụ thể trong mọi môi trường.

Đối với cấu hình thật, lặp lại phép thử **thông qua public proxy URL**, không chỉ gửi spoofed headers trực tiếp. Chỉ public request mới chứng minh rewrite, TLS termination và header normalization khớp nhau.

## 11. `Forwarded` chuẩn RFC 7239 và `X-Forwarded-*` không phải một thứ

Chuẩn RFC 7239 dùng một header với các tham số, ví dụ:

```http
Forwarded: for=192.0.2.10;proto=https;host=app.example.test
```

Các header de facto tương đương về mục đích:

```http
X-Forwarded-For: 192.0.2.10
X-Forwarded-Proto: https
X-Forwarded-Host: app.example.test
X-Forwarded-Port: 443
```

Chúng **không hoàn toàn giống cú pháp**. `Forwarded` có thể gồm nhiều phần tử, quoted strings, IPv6 và dấu phân cách cần parse đúng chuẩn. `X-Forwarded-*` không có một tiêu chuẩn duy nhất bao trùm mọi cách chain/proxy xử lý. Container native và Spring Framework có thể hỗ trợ các tập header khác nhau hoặc có quy tắc ưu tiên khác.

**Nguyên tắc:** edge proxy nên chọn convention duy nhất, xóa convention còn lại hoặc normalize theo chính sách, tránh gửi `Forwarded: proto=http` đồng thời `X-Forwarded-Proto: https` rồi phụ thuộc ngẫu nhiên vào thư viện nào được ưu tiên.

Trong Spring Framework 6.1, `ForwardedHeaderFilter` và `ForwardedHeaderTransformer` có logic hỗ trợ cả chuẩn `Forwarded` lẫn các biến thể X-Forwarded thông dụng; phải xác minh cách phối hợp nếu môi trường gửi header không chuẩn. Không tự viết parser bằng `split(",")[0]` rồi coi đó là IP client đáng tin.

## 12. `X-Forwarded-For` và địa chỉ client: không dùng phần tử đầu một cách mù quáng

Một request có thể đi qua nhiều proxies:

```text
client 192.0.2.10
   -> CDN 198.51.100.20
   -> ingress 10.2.0.8
   -> Spring Boot
```

Header `X-Forwarded-For` có thể trở thành chuỗi:

```text
192.0.2.10, 198.51.100.20
```

Nhưng attacker có thể tự gửi giá trị đầu tiên trước khi traffic đến CDN nếu CDN/ingress chỉ append mà không sanitize. Vì vậy đoạn:

```java
// Không dùng làm cơ sở authz/rate-limit/audit tin cậy:
String claimedIp = request.getHeader("X-Forwarded-For")
        .split(",")[0].trim();
```

không phải thuật toán xác định IP client chuẩn. Hãy xác định **điểm bắt đầu tin cậy**: proxies nào thực sự được hạ tầng kiểm soát, chúng rewrite hay append header, socket peer nào được phép, và server/container biết trust chain đến đâu.

Tomcat `RemoteIpValve` có cấu hình trusted/internal proxy phù hợp cho các trường hợp này. Trong Spring Framework filter, việc wrap request theo header **không tự xác minh danh sách IP proxies**. Nếu rate limiting, geolocation, policy theo IP hoặc forensic logging là yêu cầu quan trọng, phải sử dụng một cơ chế lấy client address đã được trust boundary chuẩn hóa và test cả chuỗi nhiều hops.

`X-Forwarded-For` là **địa chỉ được khẳng định bởi network path**, không phải danh tính người dùng. Nó không thay thế authentication, authorization hay session validation.

## 13. Redirect HTTP → HTTPS: đừng tạo vòng lặp vì scheme sai

Ví dụ một application đứng sau TLS termination:

```text
Client HTTPS -> Edge HTTPS -> Backend HTTP :8080
```

Nếu app kiểm tra `request.isSecure()` khi chưa xử lý `X-Forwarded-Proto`, nó thấy `false` và có thể chuyển hướng đến HTTPS mặc dù client đã dùng HTTPS. Kết quả có thể là **redirect loop** khi browser theo redirect rồi gửi lại request qua proxy.

Chọn forwarded strategy phù hợp khiến downstream code nhìn thấy public scheme `https` và tránh logic tự redirect dựa trên backend scheme. Dù vậy việc enforce HTTPS thường dễ và nhất quán hơn ở **edge**, với redirect HTTP public port 80 sang HTTPS public port 443 và chính sách HSTS phù hợp.

Với Tomcat native mode, Spring Boot 3.3 đặc biệt khuyến nghị:

```properties
server.forward-headers-strategy=NATIVE
server.tomcat.redirect-context-root=false
```

khi TLS kết thúc tại proxy và cần `X-Forwarded-Proto` được tôn trọng trước redirect context root. Nếu redirect được Tomcat gửi **trước khi Servlet filter chạy**, `FRAMEWORK` không thể quay ngược thời gian để sửa redirect đã gửi; kiểm tra vị trí phát sinh redirect là bước chẩn đoán then chốt.

Một redirect tới URL sai có thể do ứng dụng hardcode hostname, OAuth callback URL cấu hình riêng, Spring Security, proxy rewrite hoặc response `Location` do edge phát ra; **không mặc định quy mọi redirect sai cho `server.forward-headers-strategy`**.

## 14. CORS là cơ chế khác với forwarded headers

**Forwarded headers** nhằm khôi phục thông tin **request bên ngoài proxy**: scheme, host, port, client IP và prefix.

**CORS (Cross-Origin Resource Sharing)** là **chính sách truy cập từ JavaScript trong browser** giữa các origins. Một origin gồm `scheme + host + port`. Khi trang ở `https://spa.example.test` gọi API ở `https://api.example.test`, đó là cross-origin, bất kể backend API chạy HTTP phía sau proxy.

| Khía cạnh | Forwarded headers | CORS |
| --- | --- | --- |
| Mục đích | Dựng request URL/public origin chính xác sau proxy | Browser quyết định JS có thể đọc response cross-origin hay không |
| Header request chính | `Forwarded`, `X-Forwarded-*` | `Origin`, với preflight có `Access-Control-Request-Method/Headers` |
| Response header liên quan | Có thể tác động `Location`, URL/links tạo ra | `Access-Control-Allow-Origin`, `Access-Control-Allow-Methods`, ... |
| Nơi xử lý | Native server hoặc Spring forwarded filter/transformer | Spring MVC/WebFlux CORS handlers, Spring Security hoặc edge proxy |
| Có phải authn/authz? | Không | Không |
| Chuyển `HTTP` thành `HTTPS` thật? | Không | Không |
| Tự cho mọi frontend gọi API? | Không | Chỉ khi được cấu hình chính sách CORS thích hợp |

**Đặt `server.forward-headers-strategy=FRAMEWORK` không đồng nghĩa bật CORS**, và thêm `@CrossOrigin` không khiến `request.getScheme()` chuyển từ `http` thành `https`. Hai cơ chế có thể cần phối hợp nhưng có nhiệm vụ độc lập.

Việc framework thấy đúng public scheme/host đôi khi ảnh hưởng đánh giá same-origin hoặc URL sinh ra. Nhưng điều đó không thay thế việc cấu hình CORS allowlist, credentials policy và xử lý preflight. Ngược lại, CORS pass không chứng minh proxy forwarding an toàn.

## 15. Cấu hình CORS đúng phạm vi, không dùng làm sửa lỗi proxy

Ví dụ Spring MVC chỉ cho frontend `https://spa.example.test` gọi API thuộc `/api/**`. Đoạn dưới là **mẫu tích hợp** trong application Spring Boot MVC, có thể đặt cùng package với `@SpringBootApplication`:

**`src/main/java/com/example/forward/CorsConfiguration.java`**

```java
package com.example.forward;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration(proxyBeanMethods = false)
public class CorsConfiguration implements WebMvcConfigurer {

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
                .allowedOrigins("https://spa.example.test")
                .allowedMethods("GET", "POST")
                .allowedHeaders("Content-Type", "Authorization")
                .maxAge(1800);
    }
}
```

Tên class `CorsConfiguration` trong package ví dụ không phải `org.springframework.web.cors.CorsConfiguration` của framework; để tránh nhầm khi áp dụng vào dự án lớn, có thể đổi thành `WebCorsPolicy`. Đoạn này không cấp `allowCredentials(true)` theo mặc định. Nếu cần cookie-based cross-origin auth, phải có chính sách credentials phù hợp và xử lý CSRF, SameSite, session và OAuth/cookie rules độc lập.

Thử preflight:

```bash
curl -i -X OPTIONS 'http://127.0.0.1:8080/api/data' \
  -H 'Origin: https://spa.example.test' \
  -H 'Access-Control-Request-Method: GET'
```

Kết quả chỉ có ý nghĩa nếu có **mapping `/api/data`** và CORS configuration áp dụng cho route đó. Đoạn mẫu `RequestInfoController` ở phần trước chưa có `/api/data`; để test end-to-end cần tạo controller route `/api/data` hoặc dùng một API thật đang tồn tại. Nếu không, lỗi routing không thể bị hiểu là lỗi CORS.

Nếu Spring Security được dùng, tích hợp CORS đúng vị trí trong security filter chain (thường qua `.cors(...)`) để preflight không bị chặn bởi authentication filter trước khi MVC CORS xử lý. Đừng vừa để NGINX trả `Access-Control-Allow-Origin: *` vừa để Spring cấp origin cụ thể rồi mong hai chính sách hợp nhất đúng.

**Cảnh báo:** với credentialed CORS, không dùng wildcard `"*"` trong `allowedOrigins` cùng `allowCredentials=true`; cấu hình origins cụ thể/allowOriginPatterns phù hợp và giới hạn danh sách được phép.

## 16. WebFlux: `ForwardedHeaderTransformer` không phải Servlet filter

Trong ứng dụng reactive Spring WebFlux, request được biểu diễn bằng `ServerHttpRequest`, không bắt buộc đi qua một Servlet filter như MVC. Khi đặt:

```properties
server.forward-headers-strategy=FRAMEWORK
```

Spring Boot chọn **`ForwardedHeaderTransformer`** của Spring WebFlux để biến đổi request headers và URI theo forwarded metadata trước các tầng reactive xử lý request. Khi dùng `NATIVE`, việc chuyển thông tin do reactive server/container (chẳng hạn Reactor Netty) xử lý theo khả năng native.

Mẫu controller WebFlux trả URI, **không dùng đồng thời với controller Servlet demo trong cùng application**:

```java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@RestController
public class ReactiveInspectController {

    @GetMapping("/inspect")
    public Mono<String> inspect(ServerWebExchange exchange) {
        var uri = exchange.getRequest().getURI();
        return Mono.just(uri.toString());
    }
}
```

Đây là **mẫu tích hợp**, cần `spring-boot-starter-webflux` và chạy trong reactive application. Khi cả starter MVC và WebFlux có mặt, Spring Boot thường mặc định chọn Servlet web application type; không nên nghĩ thêm `spring-boot-starter-webflux` là chắc chắn dùng `ForwardedHeaderTransformer`.

Trong WebFlux, forwarded processing cũng không tự tạo proxy trust: edge phải sanitize, backend phải bị giới hạn đường truy cập và headers phải nhất quán. Thời điểm biến đổi request của WebFlux khác Servlet pipeline; muốn debug hãy xem `ServerHttpRequest.getURI()` và reactive link builders, không dùng Tomcat `RemoteIpValve` khi chạy Reactor Netty.

## 17. Đừng bật cả Native Valve và Framework Filter một cách không kiểm soát

Một cấu hình dễ sai:

```text
Tomcat RemoteIpValve         đọc X-Forwarded-Proto -> request scheme=https
ForwardedHeaderFilter        lại xử lý forwarded headers -> wrapper tiếp tục biến đổi
Custom URL builder           tự parse X-Forwarded-Host lần thứ ba
```

Mỗi tầng có cách xử lý `Forwarded` và `X-Forwarded-*` khác nhau, đôi khi ưu tiên khác nhau hoặc đã loại headers khỏi wrapper. Nếu đồng thời có `ForwardedHeaderFilter` do application tự đăng ký, `server.forward-headers-strategy=NATIVE` không còn đủ mô tả thực tế; ngược lại, một manually added native Valve có thể tác động `FRAMEWORK`.

**Chọn người chịu trách nhiệm chính**. Nếu `NATIVE`, cấu hình proxy rules của container và loại bỏ custom spring filter trùng chức năng; nếu `FRAMEWORK`, tránh native rewrite hai lần trừ khi có lý do được kiểm thử cẩn thận.

Đặc biệt, framework filter cần chạy đủ sớm để các filter/controller phía sau dùng request đã được wrap. Nếu tự đăng ký bằng `FilterRegistrationBean`, phải chọn thứ tự và dispatcher types (REQUEST, ASYNC, ERROR khi phù hợp). Boot auto-configuration đã xử lý nhiều phần này cho `FRAMEWORK`; không nên tự viết filter registration chỉ để lặp lại chức năng Boot.

## 18. Trường hợp `removeOnly` và vô hiệu hóa tin cậy vào header

Spring Framework cung cấp chế độ **chỉ xóa** forwarded headers:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.filter.ForwardedHeaderFilter;

@Configuration(proxyBeanMethods = false)
public class RemoveUntrustedForwardedHeaders {

    @Bean
    ForwardedHeaderFilter forwardedHeaderFilter() {
        ForwardedHeaderFilter filter = new ForwardedHeaderFilter();
        filter.setRemoveOnly(true);
        return filter;
    }
}
```

Đây là **một mẫu lựa chọn thủ công trên Servlet stack**, không nên thêm vào ứng dụng đã chọn `server.forward-headers-strategy=FRAMEWORK` nếu nó khiến Boot và custom configuration tranh quyền xử lý. Thích hợp hơn khi muốn Spring xử lý request **theo backend connection**, không cho downstream MVC code sử dụng forwarded headers và application chủ động kiểm soát filter order.

Nhưng `removeOnly` không phải giải pháp thay thế edge sanitation. Trước khi request vào application, các tầng web server/Valve, gateway filter hoặc logging middleware đã có thể đọc header. Nếu muốn không tin headers trên toàn hệ thống, chặn/sanitize ở edge và không đăng ký native Valve chấp nhận chúng.

Một số use cases yêu cầu retained raw forwarded headers để audit chính xác. Khi đó log ở **trusted ingress** có thể tốt hơn log từ application đã dùng request wrapper. Không đưa raw user-controlled `X-Forwarded-For` vào identity fields của audit như thể nó là IP đã được xác minh.

## 19. Kiểm thử có kiểm soát: xác nhận chính xác tầng nào đã áp dụng

Dùng ba kiểu quan sát:

**A. Servlet metadata:** `request.getScheme()`, `request.getServerName()`, `request.getServerPort()`, `request.isSecure()`, `request.getRemoteAddr()`.

**B. Generated URL:** `ServletUriComponentsBuilder.fromCurrentRequestUri()` và response `Location` từ `/jump`.

**C. Thực tế mạng/proxy:** gửi request tới **public HTTPS endpoint** và kiểm tra headers mà edge cấp, backend connection thật, redirect chain.

Bảng kiểm thử mẫu (không ghi cố định IP của mọi runtime):

| Tình huống | Đầu vào | Kỳ vọng cần kiểm chứng |
| --- | --- | --- |
| Local direct, `NONE` | `http://127.0.0.1:8080/inspect` | Request nhìn backend scheme/host/port |
| `NONE` + spoofed forwarded headers trên localhost | Gửi `X-Forwarded-Proto: https` | Boot không tự sửa servlet metadata |
| `NATIVE` + trusted local proxy | Gửi header đúng convention Tomcat | Native có thể áp dụng scheme/secure/client IP theo rules |
| `FRAMEWORK` + canonical host/proto | Gửi headers qua proxy đáng tin | Spring wrapper cho public scheme/host/port |
| `FRAMEWORK` + prefix `/portal` | Proxy strip prefix | Generated links và redirects phải có external prefix theo thiết kế |
| Header `Forwarded` và X-Forwarded mâu thuẫn | Test trong staging | Không được chấp nhận production; chỉnh edge normalize |
| Backend public bị gửi spoofed host | Thử kiểm soát trong security test | Backend phải không truy cập trực tiếp được hoặc không tin spoofed headers |
| CORS origin không được phép | `Origin: https://evil.example` | Không được nhận CORS permission ngoài allowlist |
| OAuth/login redirect qua proxy | Truy cập luồng auth thực | Callback và redirect scheme/host/port đúng, không lộ backend host |
| Multiple trusted proxy hops | CDN + ingress + app | Client address và audit fields theo trust policy, không do client tự chọn |

Một regression test đơn giản có thể khẳng định giá trị `Location` từ `/jump` ở **public URL**, nhưng không nên coi tất cả giá trị forwarded fields là định danh đáng tin chỉ vì test này pass.

## 20. Những lỗi phổ biến và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Hướng điều tra |
| --- | --- | --- |
| Link trả về `http://localhost:8080/...` | Không dùng forwarded headers hoặc URL builder hardcode backend | `server.forward-headers-strategy`, controller link code |
| HTTPS bên ngoài nhưng `request.isSecure=false` | Proxy terminate TLS, backend HTTP, strategy/trust rules chưa áp dụng | `X-Forwarded-Proto`, server mode, socket trust |
| 302 redirect loop HTTP/HTTPS | App nhìn sai scheme hoặc redirect tại nhiều tầng | Browser redirect chain, edge redirect, `request.isSecure` |
| `Location` thiếu `/portal` | Proxy strip prefix, NATIVE không xử lý prefix | `X-Forwarded-Prefix`, FRAMEWORK, route rewrites |
| `Location` lặp `/portal/portal` | Proxy và app cùng thêm prefix | So sánh inbound request path, servlet context path, header prefix |
| Remote IP luôn là proxy | XFF không được xử lý hoặc đúng là chưa có trusted chain | Native Valve config, ingress headers |
| Remote IP thành IP bất kỳ do người gọi khai | Tin XFF đầu chuỗi không đáng tin | Edge sanitation, proxy trust, không tự split |
| Phản hồi bị dẫn đến `evil.example` | Host forwarding injection | Khóa backend, sanitize X-Forwarded-Host, canonical host allowlist |
| `FRAMEWORK` bật nhưng redirect ở Tomcat vẫn sai | Redirect được container gửi trước Servlet filter | Tomcat `redirect-context-root`, container configuration |
| Chạy cloud được, local khác hành vi | Default strategy khác giữa supported cloud và other env | Cấu hình property tường minh |
| Đổi NATIVE sang FRAMEWORK gây khác client IP | Khác layer và cách xử lý địa chỉ | Xem RemoteIpValve/ForwardedHeaderFilter behavior |
| CORS preflight 401/403 | Spring Security chặn preflight hoặc CORS chưa áp dụng | Security `.cors(...)`, CORS mappings |
| CORS pass nhưng URL trong JSON sai | CORS không xử lý forwarded URL | Tách kiểm tra link builder khỏi CORS |
| Public HTTPS vẫn thấy sai cert | TLS termination/SSL config ở edge | Kiểm tra proxy certificate, không sửa forwarded headers |
| Chỉ một số API bị sai origin | Endpoint tự build URL bằng hardcoded host/raw header | Audit URL builders và thư viện liên quan |

Chẩn đoán theo thứ tự: **HTTP request thật đến edge → edge sanitization → backend connection → native/framework strategy → handler/link builder → response headers**. Đừng chỉ sửa property `server.forward-headers-strategy` khi lỗi phát sinh do proxy thiếu header hoặc do controller tự ghép `"http://" + host`.

## 21. Bảo mật: host spoofing, secure cookies, redirects và OAuth callback

Forwarded headers có ảnh hưởng tới **cách framework hiểu public origin**, vì vậy sai trust policy có thể gây hậu quả vượt chuyện một URL bị xấu:

- **Host-header injection:** App dùng `X-Forwarded-Host` chưa xác thực để tạo password-reset link hoặc absolute redirect, attacker có thể hướng người dùng sang host do họ kiểm soát.
- **Open redirect:** Một số logic tạo redirect từ scheme/host của request có thể bị điều khiển khi header không được sanitize.
- **Secure channel detection:** App dùng `request.isSecure()` dựa trên forwarded proto; nếu header giả làm HTTPS, app có thể hiểu sai ngữ cảnh bảo vệ của kết nối. TLS thực và HSTS nên enforce tại edge.
- **Cookies:** Các thuộc tính `Secure`, `SameSite`, `Domain`, `Path` hoặc link OAuth/logout có thể phụ thuộc cấu hình host/scheme/prefix. Cần kiểm chứng cùng proxy thật, không chỉ test controller.
- **Rate limit/IP ban:** Nếu IP đến từ XFF không đáng tin, attacker có thể né giới hạn hoặc làm người khác bị khóa nhầm.
- **Audit:** Log nên ghi rõ socket peer, IP theo trusted chain và yêu cầu trace/correlation metadata; không thay một nguồn tin cậy bằng raw client-supplied fields.

Bật `NATIVE` không tự giải quyết toàn bộ các điểm trên, bởi container cũng phải biết **proxy nào được tin**. Bật `FRAMEWORK` không tự tạo danh sách trusted proxies. Lớp kiểm soát quan trọng nhất là **proxy edge và mạng backend**; ứng dụng nên có canonical host configuration khi tạo link nhạy cảm.

Một cách giảm rủi ro là không xây password reset/OAuth callback theo bất kỳ host header tùy ý nào của request; dùng **public base URL cố định được cấu hình** khi nghiệp vụ đòi hỏi độ chắc chắn cao.

## 22. Khi nào nên chọn NONE, NATIVE hoặc FRAMEWORK?

| Kiến trúc/nhu cầu | Lựa chọn ban đầu | Điều kiện bổ sung |
| --- | --- | --- |
| App nhận HTTPS/HTTP trực tiếp, không có proxy | `NONE` | Không tin các forwarded headers đến từ client |
| Proxy đơn giản, Tomcat cần XFF/XFP, không có external prefix | `NATIVE` | Cấu hình/trust `RemoteIpValve`, edge sanitize |
| Proxy strip `/portal`, cần Spring-generated absolute links | `FRAMEWORK` | Edge gửi `X-Forwarded-Prefix`, test redirect/link |
| App WebFlux sau reverse proxy cần restore public origin | `FRAMEWORK` hoặc `NATIVE` theo server | Với FRAMEWORK dùng `ForwardedHeaderTransformer` |
| Kubernetes Ingress/Cloud LB | Đặt giá trị tường minh sau khi hiểu topology | Đừng dựa vào default cloud detection |
| Proxy truyền RFC 7239 `Forwarded` khác với XFF/XFP | Kiểm tra server/framework support thực tế | Đừng gửi hai convention mâu thuẫn |
| Muốn xóa header không đáng tin nhưng không áp dụng | Edge sanitation + có thể filter `removeOnly` | Không bật double-processing |
| CORS của SPA bị chặn | **Không phải chọn strategy để bật CORS** | Cấu hình origin allowlist/CORS Security riêng |
| Không tin IP từ header cho rate limiting | Proxy/net trust rules trước | Không tự parse XFF first element |

**Nguyên tắc thực dụng:** bắt đầu từ **những headers mà trusted proxy thật sự cấp**. Nếu `NATIVE` đáp ứng đầy đủ URL/redirect/IP trong stack cụ thể thì giữ đơn giản. Nếu cần xử lý prefix hoặc tính năng Spring nhận thức đầy đủ hơn, chọn `FRAMEWORK` và kiểm chứng trên public URL. Đừng bật cả hai mà không có lý do đã kiểm thử.

## 23. Câu hỏi ôn tập

1. Vì sao request HTTPS công khai có thể đến Spring Boot bằng HTTP mà ứng dụng vẫn cần tạo link `https://...`?
2. `server.forward-headers-strategy=NATIVE` và `FRAMEWORK` khác nhau ở **tầng xử lý** nào trong Spring MVC?
3. Tomcat `RemoteIpValve` khác `ForwardedHeaderFilter` ở điểm nào? Tại sao `NATIVE` không luôn xử lý external prefix giống `FRAMEWORK`?
4. `X-Forwarded-For` có thể bị client giả mạo thế nào? Vì sao không được lấy phần tử đầu bằng `split(",")[0]` để kiểm tra quyền truy cập?
5. Khi nào cần `server.tomcat.redirect-context-root=false`?
6. `Forwarded: for=...;proto=...;host=...` và `X-Forwarded-*` nên được proxy xử lý thế nào để tránh mâu thuẫn?
7. Nếu app bị redirect loop giữa HTTPS và HTTP, cần kiểm tra những tầng nào trước khi sửa `@Controller`?
8. Vì sao `@CrossOrigin` hoặc CORS pass không chứng minh URL generation đúng phía sau proxy?
9. Trong WebFlux, vì sao dùng `ForwardedHeaderTransformer` thay vì Servlet `ForwardedHeaderFilter`?
10. Với endpoint sinh link password reset, vì sao canonical base URL cấu hình sẵn có thể an toàn hơn tin raw forwarded host?
11. Nếu có cả Tomcat Valve tùy chỉnh và Boot `FRAMEWORK`, lỗi double-processing có thể xuất hiện thế nào?
12. Cần kiểm thử gì để chứng minh `/portal` prefix hoạt động chính xác qua proxy mà không bị thêm hai lần?

**Ghi nhớ:** Forwarded headers khôi phục **góc nhìn public request** sau một hoặc nhiều proxy. `NATIVE` giao việc cho **web server/container**, `FRAMEWORK` giao việc cho **Spring Framework**; `NONE` không cho Boot chủ động giải thích chúng. Chọn đúng strategy sau khi thiết lập **trusted proxy boundary**. CORS là chính sách browser cross-origin riêng biệt, không phải cơ chế proxy header forwarding.

### Tài liệu tham khảo chính thức

- Spring Boot 3.3 — Embedded Web Servers, Running Behind a Front-end Proxy Server: https://docs.spring.io/spring-boot/3.3/how-to/webserver.html
- Spring Boot 3.3 — `ForwardHeadersStrategy` enum API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/web/ServerProperties.ForwardHeadersStrategy.html
- Spring Boot 3.3 — Common Application Properties: https://docs.spring.io/spring-boot/3.3/appendix/application-properties/
- Spring Framework — Servlet Filters / Forwarded Headers: https://docs.spring.io/spring-framework/reference/web/webmvc/filters.html
- Spring Framework 6.1 — `ForwardedHeaderFilter` API: https://docs.spring.io/spring-framework/docs/6.1.2/javadoc-api/org/springframework/web/filter/ForwardedHeaderFilter.html
- Spring Framework — WebFlux Forwarded Headers: https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html
- Spring Framework — CORS for MVC: https://docs.spring.io/spring-framework/reference/web/webmvc-cors.html
- RFC 7239 — Forwarded HTTP Extension: https://www.rfc-editor.org/rfc/rfc7239