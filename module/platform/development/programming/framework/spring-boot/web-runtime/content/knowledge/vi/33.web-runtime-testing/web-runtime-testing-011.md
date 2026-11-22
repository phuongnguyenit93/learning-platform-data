# Kiểm thử cấu hình riêng máy chủ, proxy header, TLS và HTTP/2 trong Spring Boot

> **Module:** Spring Boot - web-runtime · **Nhóm:** Kiểm thử web runtime. Bài này hướng dẫn kiểm thử các hành vi thực sự phụ thuộc **embedded web server** và đường đi mạng: Tomcat/Jetty/Reactor Netty, nhận diện địa chỉ gốc qua reverse proxy, xác thực HTTPS/TLS và thương lượng HTTP/2. Trọng tâm không chỉ là property được khai báo, mà là **server đang chạy có thực hiện đúng** khi client, proxy và TLS handshake tham gia. Ví dụ sử dụng **Java 17+**, **Spring Boot 4.1.2**, Maven, Spring MVC/Tomcat, JUnit, JDK HttpClient, cURL và OpenSSL; có phần mở rộng cho Jetty, WebFlux và CI.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt kiểm thử controller bằng `MockMvc` với **kiểm thử server thật trên TCP port** bằng `@SpringBootTest(webEnvironment=RANDOM_PORT)`. Biết tình huống nào phải dùng cURL/OpenSSL/ingress thật.
2. Hiểu các nhóm cấu hình `server.*` chung, `server.tomcat.*`, `server.jetty.*` và custom `WebServerFactoryCustomizer`; biết rằng một property của Tomcat không tự áp vào Reactor Netty.
3. Kiểm tra `Forwarded` (RFC 7239), `X-Forwarded-For`, `X-Forwarded-Proto`, `X-Forwarded-Host`, `X-Forwarded-Port` và `X-Forwarded-Prefix`, bao gồm trust boundary và rủi ro client giả mạo header.
4. Phân biệt `server.forward-headers-strategy=none|native|framework`, Tomcat RemoteIpValve và Spring `ForwardedHeaderFilter`/WebFlux `ForwardedHeaderTransformer`.
5. Xác minh chứng thư HTTPS, CA trust, hostname/SAN, thời hạn, SNI và TLS handshake mà **không dùng trust-all** hoặc `curl -k`.
6. Cấu hình **SSL bundle PEM** cho server, kiểm `server.ssl.bundle` và cách tương tác với các `server.ssl.*` properties rời; hiểu kiểm thử mTLS là một kịch bản khác server-auth TLS.
7. Bật `server.http2.enabled=true`, phân biệt **h2 qua TLS và ALPN**, **h2c qua cleartext**, cùng trường hợp proxy chỉ dùng HTTP/2 phía ngoài nhưng backend vẫn HTTP/1.1.
8. Viết test thực dùng `@LocalServerPort` và Java 17 `java.net.http.HttpClient` để kiểm forward headers, redirect URL và tình huống bypass proxy trong lab.
9. Xây ma trận tích hợp CI kiểm đúng cả **positive** và **negative**: header injection, wrong hostname/CA, HTTP/2 downgrade, oversized headers, proxy rewrite và deployment TLS termination.
10. Có runbook phát hiện cấu hình sai qua request/response, logs, packet/protocol tools và metrics, không tự suy từ file cấu hình.

## 2. Vì sao chủ đề này không thể chỉ kiểm bằng MockMvc?

Giả sử controller khai báo:

~~~java
@GetMapping("/ping")
String ping() {
    return "pong";
}
~~~

Với `MockMvc`, bạn có thể kiểm route, headers được tạo bởi controller, validation, Spring Security filters và exception handlers trong một **mock Servlet environment**. Nhưng mock MVC test **không bắt buộc khởi tạo một TCP listener**, không thực hiện một TLS handshake, ALPN negotiation, WebSocket upgrade bằng socket thật, HTTP/2 streams hoặc Tomcat connector xử lý giới hạn headers.

~~~text
                         Tests
                           |
              +------------+----------------+
              |                             |
       @WebMvcTest / MockMvc         @SpringBootTest(RANDOM_PORT)
       MockHttpServletRequest         Embedded Tomcat/Jetty/Netty
       Controller + filters           Real TCP request/response
              |                             |
       Logic/mapping contract         Connector, forwarded handling
                                           |
                                  +--------+-------------+
                                  |                      |
                               cURL/JDK                Proxy/Ingress
                               HttpClient              + TLS edge
                                  |                      |
                                  +--- TLS, ALPN, h2 ----+
~~~

| Cần xác minh | MockMvc có đủ không? | Phép thử phù hợp |
| --- | --- | --- |
| `@GetMapping`, body, status, business validation | Thường có | `@WebMvcTest`/`MockMvc` |
| Property bind vào Environment | Có thể kiểm | ApplicationContext/config test |
| Server thực sự bind IP/port | Không | Real server + TCP connect |
| Tomcat max header/connection/threads | Không | Embedded Tomcat thật dưới tải |
| Reverse proxy sửa scheme/host/redirect | Mock filter test chỉ một phần | Direct HTTP test + trusted proxy test |
| Chứng thư, CA chain và hostname | Không | TLS client thật/OpenSSL |
| ALPN h2 vs http/1.1 | Không | TLS negotiation thực |
| h2c prior knowledge/upgrade | Không | HTTP/2-capable client đến connector thật |
| Browser mixed content, secure cookies, HSTS | Không đủ | Browser qua HTTPS edge thật |
| LB sticky routing, Ingress rewrite | Không | Staging với topology tương tự production |

**Nguyên tắc:** một test “application context starts” hoặc “controller GET trả 200” không chứng minh rằng proxy, TLS và HTTP/2 đã hoạt động đúng.

### 2.1. Ba điểm quan sát khác nhau

Đừng gộp các thông số trong một trace:

1. **External client → edge proxy:** URL `https://public.example.test/orders/42`; browser có thể dùng HTTP/2, TLS certificate của proxy.
2. **Edge proxy → Spring Boot:** có thể `http://10.0.0.12:8080/orders/42` qua HTTP/1.1, dù browser ở ngoài dùng HTTPS+h2.
3. **Spring MVC Servlet request:** theo chiến lược forwarded, `getScheme()/isSecure()/getServerName()` có thể phản ánh external origin; `getProtocol()` thường phản ánh **protocol của hop đến backend**, không phải phiên HTTP/2 ở trình duyệt.

Vì vậy response body ghi `"protocol":"HTTP/1.1"` ở backend không phủ nhận việc cURL ở client ngoài đã thương lượng HTTP/2 với proxy.

## 3. Kiểm thử cấu hình riêng từng server

Spring Boot cung cấp các embedded servers với khả năng và cấu hình khác nhau:

| Runtime | Stack điển hình | Nơi cấu hình | Điều phải kiểm thực |
| --- | --- | --- | --- |
| **Tomcat 11** | Spring MVC/Servlet, starter webmvc mặc định | `server.*`, `server.tomcat.*`, `TomcatServletWebServerFactory` | Connector, header parsing, RemoteIpValve, TLS/h2 |
| **Jetty** | Spring MVC/Servlet khi đổi starter | `server.*`, `server.jetty.*`, `JettyServletWebServerFactory` | Jetty-specific settings, modules hỗ trợ h2 |
| **Reactor Netty** | WebFlux reactive server | `server.*`, Netty-specific options/customization | Event loop, h2/h2c, headers, forwarded transformer |
| **Reverse proxy/gateway** | Nginx, Envoy, Apache, ingress/CDN | Không phải properties Spring Boot | External TLS, ALPN, trusted headers, routing/redirect |

**Không nên lấy hướng dẫn Undertow/Tomcat 9 cũ để làm mặc định cho Boot 4.1.2.** Spring Boot 4.1 dùng Tomcat 11 theo tài liệu hiện hành, và HTTP/2 behavior có khác các phiên bản rất cũ. Hãy xác nhận chính xác dependencies phiên bản chạy trong môi trường của bạn.

### 3.1. Cấu hình server chung

~~~properties
server.address=127.0.0.1
server.port=8080
server.http2.enabled=false
server.forward-headers-strategy=none
server.max-http-request-header-size=8KB
~~~

Đây là cấu hình **lab cục bộ** để đo rõ một connector. `server.address=127.0.0.1` giúp tránh expose một endpoint nhận forwarded headers trong môi trường học. Nếu đưa ứng dụng vào Docker/Kubernetes, listener chỉ bind loopback có thể không được Service/Ingress truy cập; production phải chọn địa chỉ bind và network policy đúng.

- `server.max-http-request-header-size` là giới hạn phía HTTP request header, không phải kích thước request JSON body hoặc response header.
- `server.http2.enabled=false` khiến baseline mặc định không bật h2/h2c.
- `server.forward-headers-strategy=none` bỏ qua việc dùng forwarded headers để thay đổi thông tin request trong Spring Boot strategy; không khẳng định mọi filter tự viết cũng sẽ bỏ qua.
- Những giới hạn giao thức có thể được áp ở proxy trước khi đến server; một status 431 từ edge không chứng minh Tomcat của Boot đã từ chối.

### 3.2. Cấu hình Tomcat riêng

~~~properties
# Chỉ ảnh hưởng embedded Tomcat, KHÔNG ảnh hưởng Jetty/Netty.
server.tomcat.threads.max=64
server.tomcat.max-connections=1024
server.tomcat.connection-timeout=5s
server.tomcat.redirect-context-root=false
~~~

- Số worker threads không đồng nghĩa max concurrent clients: keep-alive connections, async I/O và HTTP/2 multiplexing có mô hình riêng.
- Kịch bản request quá nhiều hoặc client chậm cần đo queue, active threads, connection count, timeouts, không suy theo một property.
- `server.tomcat.redirect-context-root=false` quan trọng trong tình huống SSL kết thúc ở proxy: để header `X-Forwarded-Proto` có cơ hội được xử lý trước redirect liên quan context root.
- Không copy `server.tomcat.*` sang WebFlux/Netty rồi chờ thay đổi có hiệu lực.

Tomcat còn có cấu hình RemoteIpValve trong chế độ native, ví dụ `server.tomcat.remoteip.protocol-header` và `server.tomcat.remoteip.internal-proxies`. Đó là một **ranh giới tin cậy**, không phải lời mời tin mọi địa chỉ.

### 3.3. Khi nào cần WebServerFactoryCustomizer?

Nếu một tính năng server cần chỉnh không được Boot đưa thành property, có thể dùng customizer theo đúng factory:

~~~java
// Fragment cho dự án Spring MVC/Tomcat, không phải chương trình độc lập.
@Bean
WebServerFactoryCustomizer<TomcatServletWebServerFactory> tomcatCustomizer() {
    return factory -> {
        // Chỉ cấu hình API Tomcat được yêu cầu sau khi tra Javadoc
        // và có test behavior thật ở connector.
    };
}
~~~

Các types tương ứng trong Boot 4.x:

~~~java
import org.springframework.boot.web.server.WebServerFactoryCustomizer;
import org.springframework.boot.tomcat.servlet.TomcatServletWebServerFactory;
~~~

Đừng vừa tự cài `ForwardedHeaderFilter` vừa bật native RemoteIpValve và sửa scheme nhiều lần mà chưa hiểu thứ tự. Khi thay Jetty, customizer typed Tomcat có thể không còn bean matching; phải có test xác minh cấu hình vẫn được áp đúng.

### 3.4. Cách xác nhận server thực sự đang dùng

- Xem Maven dependency tree/Boot startup logs và server factory bean type.
- Dùng `mvn dependency:tree` để kiểm `spring-boot-starter-tomcat`, `spring-boot-starter-jetty` hoặc Reactor Netty nằm trong classpath.
- Chạy test cổng thật và kiểm header/protocol/TLS behavior.
- Với limit/timeouts, phải tạo traffic vượt ngưỡng một cách có kiểm soát và quan sát error/path thực.
- Khi đổi server, chạy lại toàn bộ test matrix: property cùng tên không đảm bảo cùng timing hoặc status code.

## 4. Hiểu và kiểm thử proxy forwarding headers

Một reverse proxy có thể kết thúc TLS và chuyển vào backend HTTP:

~~~text
Client                     Reverse proxy                Spring Boot
https://api.example.test    TLS edge                     HTTP backend
HTTP/2 over TLS             HTTP/1.1 to :8080
       |                          |                          |
       +--- HTTPS /orders/42 ---->|
                                  +--- GET /orders/42 ------->
                                  |   Host: backend:8080
                                  |   X-Forwarded-Proto: https
                                  |   X-Forwarded-Host: api.example.test
                                  |   X-Forwarded-Port: 443
                                  |   X-Forwarded-For: client IP
                                  |                          |
                                  |             Spring computes external origin
                                  |<--- Location: https://api.example.test/... 
       |<--- HTTPS response -------+
~~~

Nếu forwarded headers không được xử lý, app có thể tạo `Location: http://backend:8080/login`, absolute links sai scheme/host, OAuth redirect_uri sai, cookies thiếu `Secure` hoặc swagger/openapi server URL sai. Nếu **tin header do Internet client tùy ý chèn**, app có thể bị host-header poisoning, open redirect, hỏng security decision hoặc lộ token qua link.

### 4.1. Các headers thường gặp

| Header | Ý nghĩa | Kiểm tra |
| --- | --- | --- |
| `Forwarded: for=...;proto=https;host=...` | Chuẩn RFC 7239 cho origin và các hops | Parser và quyền tin header |
| `X-Forwarded-For` | Chuỗi IP client/proxy, có thể nhiều entries | Không mù quáng tin entry đầu |
| `X-Forwarded-Proto` | Scheme client→proxy, ví dụ https | `request.getScheme()`/redirect |
| `X-Forwarded-Host` | Host public ban đầu | Absolute URL/host validation |
| `X-Forwarded-Port` | Port client-facing | URI builder, redirect port |
| `X-Forwarded-Prefix` | Prefix được proxy rewrite | Context path/links; khả năng tùy stack |
| `X-Forwarded-Ssl` | Một quy ước legacy | Chỉ dùng nếu proxy/handler hỗ trợ |

HTTP `Host` và forwarded host là dữ liệu **được đưa qua mạng**, không phải tên miền đáng tin tự động. Ở trust boundary, proxy phải **strip cả `Forwarded` và mọi `X-Forwarded-*` do client gửi**, sau đó tự gắn giá trị đã kiểm theo kết nối thật. Không chỉ strip một họ mà để họ còn lại lọt qua.

### 4.2. Ba chế độ Boot

~~~properties
server.forward-headers-strategy=none
~~~

Không dùng headers để điều chỉnh origin. Phù hợp baseline lab, hoặc ứng dụng nhận trực tiếp requests mà không có trusted proxy.

~~~properties
server.forward-headers-strategy=native
~~~

Dùng cơ chế riêng của container, như Tomcat RemoteIpValve. Có thể quản lý danh sách proxies tin cậy, header names và các quy tắc native. Hành vi khác giữa Tomcat/Jetty/Netty; phải test bằng request có **địa chỉ nguồn proxy thực**.

~~~properties
server.forward-headers-strategy=framework
~~~

Dùng hỗ trợ Spring Framework: `ForwardedHeaderFilter` trên MVC và `ForwardedHeaderTransformer` trên WebFlux. Hỗ trợ thay đổi scheme/host/port và links theo headers. Tuy nhiên **framework không tự xác định được header nào do proxy đáng tin đặt**: nếu backend public, client có thể giả mạo.

Trong Boot 4.1, ở một số cloud environments được nhận diện, default có thể là `NATIVE`; ngoài ra thường là `NONE`. Trong test, **đặt strategy tường minh**, không phụ thuộc cloud detection làm thay đổi kỳ vọng.

### 4.3. Hạn chế của native vs framework

Tomcat RemoteIpValve có thiết lập `internal-proxies` theo regex và giải quyết remote IP/scheme theo các headers nó hỗ trợ. Spring Framework filter thuận tiện cho forwarded host/prefix và links nhưng **không phải một allowlist proxy IP**. Với Tomcat native, `X-Forwarded-Prefix`/RFC 7239 `Forwarded` có thể có hỗ trợ khác với `X-Forwarded-Proto`/`X-Forwarded-For`: không dự đoán mọi header đều như nhau.

Spring Framework 7.1 mô tả chọn rõ dạng headers cho filter/transformer, và có tùy chọn dùng prefix riêng. Khi cần customization, tra đúng minor version và docs `spring.mvc.forwarded-headers.header-format`/`spring.webflux.forwarded-headers.header-format`; không hardcode giả định filter tự dùng cả hai chuẩn ở mọi phiên bản.

### 4.4. X-Forwarded-For: thứ tự hops và trusted chain

Ví dụ chuỗi:

~~~text
X-Forwarded-For: 198.51.100.10, 10.0.1.10, 10.0.2.20
~~~

Giả sử client ngoài là 198.51.100.10 và qua hai proxies nội bộ. Nhưng nếu edge **không xóa incoming X-Forwarded-For**, attacker có thể đẩy một IP giả vào đầu chuỗi. Do đó:

- Cấu hình trusted proxy CIDRs/addresses trong gateway/Tomcat đúng môi trường.
- Ở edge, overwrite incoming forwarded headers và ghi IP thực của peer kết nối.
- Ở các proxies sau, nối chuỗi chỉ từ thông tin đã được **xác minh**.
- Không dùng `split(",")[0]` làm căn cứ authorization/rate limit/audit cho Internet clients khi trust boundary chưa chuẩn.

Trong Tomcat, **để trống internal-proxies có thể tạo cấu hình tin tất cả proxies** tùy cách binding. Đó là anti-pattern nghiêm trọng, không dùng trong production.

### 4.5. Redirect và absolute URL

Giả sử client gọi:

~~~http
GET /go HTTP/1.1
Host: backend.internal:8080
X-Forwarded-Proto: https
X-Forwarded-Host: shop.example.test
X-Forwarded-Port: 443
~~~

Controller tạo redirect bằng Spring URI builder từ current request. Ở chế độ `framework` với headers đáng tin trong **lab**, Location nên trỏ `https://shop.example.test/probe`. Với `none`, nó nên phản ánh backend origin thay vì tin các forwarded headers. Đây là phép thử quan trọng hơn chỉ echo header raw.

**Không nên** đổi lại Host từ request bất kỳ thành external link mà không kiểm allowlist domain, nhất là password reset/OAuth. Một redirect đúng scheme nhưng host do attacker chọn vẫn có thể gây open redirect/link poisoning.

## 5. Dự án chạy được: test servlet server và forwarding

Mục tiêu lab:

- Spring MVC/Tomcat trên loopback `127.0.0.1:8080`.
- `GET /probe` báo scheme, host, port, secure flag, request protocol và absolute URL.
- `GET /go` tạo redirect Location dựa trên request hiện tại.
- Test JUnit chạy embedded server trên random port để so sánh `none` và `framework`.
- Hai profiles riêng để thử TLS+h2 và h2c bằng cURL/OpenSSL.

### 5.1. Cấu trúc thư mục

~~~text
web-runtime-integration-lab/
  pom.xml
  src/main/java/com/example/webtest/
    WebRuntimeApplication.java
    ProbeController.java
  src/main/resources/
    application.properties
    application-proxy.properties
    application-tls.properties
    application-h2c.properties
  src/test/java/com/example/webtest/
    ForwardedHeadersTest.java
    NoForwardedHeadersTest.java
  tls/                                # tạo bởi OpenSSL, KHÔNG commit
    localhost.crt
    localhost.key
    localhost.pk8.key
  .gitignore
~~~

### 5.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>web-runtime-integration-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webmvc</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webmvc-test</artifactId>
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

Spring Boot 4.1.2 đã có `spring-boot-starter-webmvc-test` dùng cho tests. Không copy thói quen Boot 3 `spring-boot-starter-web`/tự import các package cũ mà chưa kiểm version. JUnit/Jackson test và Spring Boot test dependencies được starter quản lý.

### 5.3. WebRuntimeApplication.java

~~~java
package com.example.webtest;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebRuntimeApplication {
    public static void main(String[] args) {
        SpringApplication.run(WebRuntimeApplication.class, args);
    }
}
~~~

### 5.4. ProbeController.java

~~~java
package com.example.webtest;

import java.net.URI;
import java.util.LinkedHashMap;
import java.util.Map;

import jakarta.servlet.http.HttpServletRequest;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.support.ServletUriComponentsBuilder;

@RestController
public class ProbeController {

    @GetMapping("/probe")
    public Map<String, Object> probe(HttpServletRequest request) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("scheme", request.getScheme());
        result.put("host", request.getServerName());
        result.put("port", request.getServerPort());
        result.put("secure", request.isSecure());
        result.put("protocol", request.getProtocol());
        result.put("requestUrl", request.getRequestURL().toString());
        result.put("absoluteLink",
                ServletUriComponentsBuilder.fromCurrentRequestUri()
                        .toUriString());
        return result;
    }

    @GetMapping("/go")
    public ResponseEntity<Void> redirectToProbe() {
        URI target = ServletUriComponentsBuilder
                .fromCurrentContextPath()
                .path("/probe")
                .build()
                .toUri();
        return ResponseEntity.status(HttpStatus.FOUND)
                .location(target)
                .build();
    }
}
~~~

Code dùng `jakarta.servlet.http.HttpServletRequest` phù hợp Servlet stack hiện đại, không phải `javax.servlet.*` cũ. `request.getProtocol()` là HTTP protocol của request backend đang được server xử lý, không tự đổi thành `HTTP/2.0` chỉ vì proxy ở ngoài đã dùng h2.

`absoluteLink` dùng Spring URI builder; mục đích là kiểm khác biệt **redirect/link generation** khi ForwardedHeaderFilter hoạt động. Đây là API diagnostic không nên xuất IP/internal backend hostname hay thông tin nhạy cảm cho public users. Trong app thật, giới hạn route /probe theo management plane.

### 5.5. application.properties

~~~properties
# Baseline rõ ràng, chỉ trên loopback.
server.address=127.0.0.1
server.port=8080
server.forward-headers-strategy=none
server.http2.enabled=false
server.ssl.enabled=false

server.max-http-request-header-size=8KB
server.tomcat.threads.max=64
server.tomcat.max-connections=1024
server.tomcat.connection-timeout=5s
server.tomcat.redirect-context-root=false
~~~

**Không** đặt SSL bundle trong base profile; profile TLS mới thêm. Điều này giúp chạy profile h2c mà không vô tình giữ `server.ssl.bundle` đã được khai ở base.

### 5.6. application-proxy.properties

~~~properties
# Chỉ bật khi request tới từ một reverse proxy được tin cậy.
server.forward-headers-strategy=framework
server.tomcat.redirect-context-root=false
~~~

Trong **lab** backend chỉ nghe loopback, có thể gửi forwarded headers bằng cURL để xem framework biến đổi request. Trong production, đừng chuyển sang `framework` khi application vẫn exposed trực tiếp cho Internet và proxy chưa sanitize inputs. Việc filter hiểu `X-Forwarded-Proto` không có nghĩa header đã được xác thực.

### 5.7. application-h2c.properties

~~~properties
# HTTP/2 over cleartext TCP - chỉ dùng trong lab/trusted backend.
server.port=8080
server.ssl.enabled=false
server.http2.enabled=true
~~~

Không dùng h2c để truyền bearer tokens/credentials qua Internet công khai: h2c **không có TLS encryption**. Một proxy có thể bảo vệ hop edge bằng TLS, nhưng backend cleartext cần private network/mTLS sidecar/network policies tùy threat model.

### 5.8. application-tls.properties

~~~properties
server.port=8443
server.http2.enabled=true

# HTTPS identity của embedded Tomcat (inbound).
server.ssl.enabled=true
server.ssl.bundle=labhttps

spring.ssl.bundle.pem.labhttps.keystore.certificate=file:./tls/localhost.crt
spring.ssl.bundle.pem.labhttps.keystore.private-key=file:./tls/localhost.pk8.key
~~~

`server.ssl.bundle` trỏ đến bundle tên `labhttps`. Đây là **server keystore** chứa certificate public và private key; client cần trust certificate/CA public khi gọi. Đừng nhầm `truststore` của outbound RestClient với keystore mà inbound server dùng.

Khi dùng `server.ssl.bundle`, **không trộn** các cấu hình keystore/PEM độc lập như `server.ssl.key-store`, `server.ssl.certificate` và `server.ssl.certificate-private-key`. Những `server.ssl.ciphers`/`enabled-protocols` nếu đặt riêng còn có thể bị bỏ qua khi bundle được chọn; đưa tùy chọn protocol/cipher tương ứng vào `spring.ssl.bundle.pem.labhttps.options.*` theo tài liệu đúng phiên bản.

### 5.9. .gitignore

~~~gitignore
/target/
/tls/
~~~

Không commit private keys. Bỏ qua `tls/` ngay cả khi chứa cert public giúp không vô tình commit private key của lab. Nếu key đã từng commit, .gitignore không thu hồi lịch sử; phải rotate và xử lý theo quy trình secrets incident.

## 6. Kiểm thử tự động dùng server thật và random port

### 6.1. Vì sao RANDOM_PORT?

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
~~~

Theo Spring Boot, `RANDOM_PORT` khởi tạo embedded server thật và để hệ điều hành chọn một cổng chưa dùng. Điều này giảm collision khi CI chạy tests song song. `@LocalServerPort` (Boot 4.1 package `org.springframework.boot.test.web.server.LocalServerPort`) inject cổng sau khi server đã start.

Không sử dụng `@SpringBootTest` mặc định (MOCK) để kết luận port/TLS/h2 đang chạy. Test real server không cần giả mạo TLS qua test request builder khi mục tiêu là giao thức thực.

### 6.2. ForwardedHeadersTest.java

~~~java
package com.example.webtest;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties = {
        "server.address=127.0.0.1",
        "server.ssl.enabled=false",
        "server.http2.enabled=false",
        "server.forward-headers-strategy=framework"
    }
)
class ForwardedHeadersTest {

    @LocalServerPort
    int port;

    @Test
    void trustedProxyHeadersChangeEffectiveOrigin() throws Exception {
        URI uri = URI.create("http://127.0.0.1:" + port + "/probe");

        HttpRequest request = HttpRequest.newBuilder(uri)
                .header("X-Forwarded-Proto", "https")
                .header("X-Forwarded-Host", "edge.example.test")
                .header("X-Forwarded-Port", "443")
                .GET()
                .build();

        try (HttpClient client = HttpClient.newHttpClient()) {
            HttpResponse<String> response = client.send(
                    request, HttpResponse.BodyHandlers.ofString());

            assertEquals(200, response.statusCode());
            String body = response.body();
            assertTrue(body.contains("\"scheme\":\"https\""), body);
            assertTrue(body.contains("\"host\":\"edge.example.test\""), body);
            assertTrue(body.contains("\"port\":443"), body);
            assertTrue(body.contains("\"secure\":true"), body);
            assertTrue(body.contains("https://edge.example.test/probe"), body);
        }
    }

    @Test
    void forwardedHostAffectsAbsoluteRedirect() throws Exception {
        URI uri = URI.create("http://127.0.0.1:" + port + "/go");

        HttpRequest request = HttpRequest.newBuilder(uri)
                .header("X-Forwarded-Proto", "https")
                .header("X-Forwarded-Host", "edge.example.test")
                .header("X-Forwarded-Port", "443")
                .GET()
                .build();

        try (HttpClient client = HttpClient.newBuilder()
                .followRedirects(HttpClient.Redirect.NEVER)
                .build()) {
            HttpResponse<Void> response = client.send(
                    request, HttpResponse.BodyHandlers.discarding());
            assertEquals(302, response.statusCode());
            assertEquals(
                    "https://edge.example.test/probe",
                    response.headers().firstValue("Location").orElseThrow());
        }
    }
}
~~~

**Lưu ý Java:** `java.net.http.HttpClient` implements `AutoCloseable` trong JDK mới hơn Java 17, **không phải Java 17**! Vì bài dùng **Java 17+**, để code chắc chắn biên dịch trên JDK 17, hãy dùng dạng tạo client thông thường và **không sử dụng try-with-resources** cho `HttpClient`. Bản test đúng Java 17 như sau:

~~~java
// Phần thay thế cụ thể cho phần try-with-resources ở test bên trên:
// Dùng HttpClient client = ...; rồi gọi client.send(...) bình thường.
// Ví dụ độc lập chạy với JDK 17:
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

public class HttpClient17Demo {
    public static void main(String[] args) throws Exception {
        HttpClient client = HttpClient.newHttpClient();
        HttpRequest request = HttpRequest.newBuilder(
                URI.create("http://127.0.0.1:8080/probe"))
                .GET()
                .build();
        HttpResponse<String> response = client.send(
                request, HttpResponse.BodyHandlers.ofString());
        System.out.println("HTTP status: " + response.statusCode());
    }
}
~~~

Lệnh chạy demo độc lập (cần app đang lắng nghe 8080):

~~~bash
javac --release 17 HttpClient17Demo.java
java HttpClient17Demo
~~~

Khi app lab chạy và trả HTTP 200, stdout dự kiến:

~~~text
HTTP status: 200
~~~

Nếu không có server, chương trình ném lỗi connect; đây **không** phải stdout mặc định. Trong file `ForwardedHeadersTest.java` để chạy trực tiếp, sửa hai đoạn `try (HttpClient client = ... ) { ... }` thành:

~~~java
// Lần 1:
HttpClient client = HttpClient.newHttpClient();
HttpResponse<String> response = client.send(
        request, HttpResponse.BodyHandlers.ofString());
assertEquals(200, response.statusCode());
// ... các assert bên dưới.

// Lần 2:
HttpClient client = HttpClient.newBuilder()
        .followRedirects(HttpClient.Redirect.NEVER)
        .build();
HttpResponse<Void> response = client.send(
        request, HttpResponse.BodyHandlers.discarding());
assertEquals(302, response.statusCode());
// ... các assert bên dưới.
~~~

Do phạm vi của biến `client` ở hai test methods khác nhau, không conflict. Ví dụ `HttpClient17Demo` là standalone; các replacement blocks là fragment, không tự biên dịch độc lập.

### 6.3. NoForwardedHeadersTest.java

~~~java
package com.example.webtest;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.junit.jupiter.api.Assertions.assertFalse;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties = {
        "server.address=127.0.0.1",
        "server.ssl.enabled=false",
        "server.http2.enabled=false",
        "server.forward-headers-strategy=none"
    }
)
class NoForwardedHeadersTest {

    @LocalServerPort
    int port;

    @Test
    void spoofedHeadersDoNotChangeEffectiveOrigin() throws Exception {
        URI uri = URI.create("http://127.0.0.1:" + port + "/probe");

        HttpRequest request = HttpRequest.newBuilder(uri)
                .header("X-Forwarded-Proto", "https")
                .header("X-Forwarded-Host", "attacker.example.test")
                .header("X-Forwarded-Port", "443")
                .GET()
                .build();

        HttpResponse<String> response = HttpClient.newHttpClient().send(
                request, HttpResponse.BodyHandlers.ofString());

        assertEquals(200, response.statusCode());
        String body = response.body();
        assertTrue(body.contains("\"scheme\":\"http\""), body);
        assertTrue(body.contains("\"host\":\"127.0.0.1\""), body);
        assertTrue(body.contains("\"secure\":false"), body);
        assertFalse(body.contains("\"host\":\"attacker.example.test\""), body);
    }
}
~~~

**Kết quả của hai test cases là khác nhau có chủ đích.** Trong `framework`, test chứng minh filter **có thể sử dụng** forwarded headers, không chứng minh rằng một proxy thực đã sanitize chúng. Trong `none`, test chứng minh Boot strategy không dùng chúng để tạo effective scheme/host trên baseline cấu hình. Test bảo mật production còn phải thực hiện **qua edge thật** và xác minh attacker không thể đưa giá trị giả vào backend.

### 6.4. Phiên bản ForwardedHeadersTest.java chuẩn Java 17 (khuyến nghị dùng)

Để tránh sửa fragments bằng tay, đây là **bản hoàn chỉnh thay thế** cho file 6.2 và tương thích Java 17:

~~~java
package com.example.webtest;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties = {
        "server.address=127.0.0.1",
        "server.ssl.enabled=false",
        "server.http2.enabled=false",
        "server.forward-headers-strategy=framework"
    }
)
class ForwardedHeadersTest {

    @LocalServerPort
    int port;

    @Test
    void trustedProxyHeadersChangeEffectiveOrigin() throws Exception {
        URI uri = URI.create("http://127.0.0.1:" + port + "/probe");

        HttpRequest request = HttpRequest.newBuilder(uri)
                .header("X-Forwarded-Proto", "https")
                .header("X-Forwarded-Host", "edge.example.test")
                .header("X-Forwarded-Port", "443")
                .GET()
                .build();

        HttpClient client = HttpClient.newHttpClient();
        HttpResponse<String> response = client.send(
                request, HttpResponse.BodyHandlers.ofString());

        assertEquals(200, response.statusCode());
        String body = response.body();
        assertTrue(body.contains("\"scheme\":\"https\""), body);
        assertTrue(body.contains("\"host\":\"edge.example.test\""), body);
        assertTrue(body.contains("\"port\":443"), body);
        assertTrue(body.contains("\"secure\":true"), body);
        assertTrue(body.contains("https://edge.example.test/probe"), body);
    }

    @Test
    void forwardedHostAffectsAbsoluteRedirect() throws Exception {
        URI uri = URI.create("http://127.0.0.1:" + port + "/go");

        HttpRequest request = HttpRequest.newBuilder(uri)
                .header("X-Forwarded-Proto", "https")
                .header("X-Forwarded-Host", "edge.example.test")
                .header("X-Forwarded-Port", "443")
                .GET()
                .build();

        HttpClient client = HttpClient.newBuilder()
                .followRedirects(HttpClient.Redirect.NEVER)
                .build();

        HttpResponse<Void> response = client.send(
                request, HttpResponse.BodyHandlers.discarding());

        assertEquals(302, response.statusCode());
        assertEquals(
                "https://edge.example.test/probe",
                response.headers().firstValue("Location").orElseThrow());
    }
}
~~~

**Trong project tree, lưu duy nhất file chuẩn tại mục 6.4**, không lưu thêm bản 6.2 hoặc ghép hai class tên giống nhau. Ví dụ đầu giải thích bẫy JDK API và phần sau là code chính thức cho Java 17.

### 6.5. Chạy test

~~~bash
mvn test
~~~

Test Maven/Surefire sẽ phát hiện class names kết thúc bằng `Test`. Nếu thành công, JUnit report các tests pass; số lượng tests và cách format output phụ thuộc Maven Surefire/JUnit version. Không bịa một chuỗi stdout cố định.

**Phạm vi đã kiểm:** Tomcat server thực, routing, Servlet request wrappers từ forward strategy, absolute redirect behavior, request headers qua TCP. **Chưa kiểm:** TLS handshake, thật sự có proxy trusted/sanitization và ALPN; các bước đó được kiểm bên dưới.

## 7. Chạy baseline và thử proxy headers thủ công

### 7.1. Baseline HTTP không tin forwarded headers

~~~bash
mvn spring-boot:run
~~~

Tại terminal khác:

~~~bash
curl -sS http://127.0.0.1:8080/probe
curl -i http://127.0.0.1:8080/go
~~~

Với baseline `none`, JSON `/probe` có scheme `http`, secure `false`, port 8080 và HTTP protocol thông thường là `HTTP/1.1`. Absolute URL/Location trỏ loopback. Không hardcode thứ tự JSON properties hoặc toàn bộ headers vào automated test nếu không cần.

### 7.2. Bật framework forwarding

Dừng process trước, rồi:

~~~bash
mvn spring-boot:run \
  -Dspring-boot.run.profiles=proxy
~~~

Với Maven trên Windows PowerShell, cách Maven diễn giải dấu `-D` có thể cần bọc toàn bộ option trong quotes. Có thể thay bằng:

~~~bash
java -jar target/web-runtime-integration-lab-0.0.1-SNAPSHOT.jar \
  --spring.profiles.active=proxy
~~~

Lệnh JAR cần chạy `mvn package` trước; không chạy cả hai server cùng lúc trên một port.

Gọi với headers giả lập do trusted proxy đặt:

~~~bash
curl -sS \
  -H 'X-Forwarded-Proto: https' \
  -H 'X-Forwarded-Host: edge.example.test' \
  -H 'X-Forwarded-Port: 443' \
  http://127.0.0.1:8080/probe
~~~

Khi `framework` đang bật, effective scheme/host/port thường là `https`, `edge.example.test`, `443`. Redirect:

~~~bash
curl -i \
  -H 'X-Forwarded-Proto: https' \
  -H 'X-Forwarded-Host: edge.example.test' \
  -H 'X-Forwarded-Port: 443' \
  http://127.0.0.1:8080/go
~~~

Với controller demo và headers được framework tin, `Location` nên là `https://edge.example.test/probe`. **Đây là test functionality, không phải test trust boundary.** Bất kỳ client nào chạm trực tiếp vào localhost lab cũng có thể đưa các headers này; production phải khiến chỉ trusted proxies kết nối backend.

### 7.3. Kiểm chuẩn Forwarded vs X-Forwarded-*

Một request RFC 7239:

~~~bash
curl -i \
  -H 'Forwarded: for=192.0.2.10;proto=https;host=edge.example.test' \
  http://127.0.0.1:8080/go
~~~

Spring Framework có hỗ trợ Forwarded; **chế độ header format** và bộ lọc được dùng theo version/cấu hình có thể khiến test cần dùng một họ headers được chọn rõ. Không gửi đồng thời `Forwarded` và `X-Forwarded-*` mâu thuẫn rồi dự đoán “cái nào chắc chắn thắng” nếu chưa kiểm documentation/runtime.

Nếu proxy dùng `X-Forwarded-Prefix: /public`, test absolute links và redirect để đảm bảo prefix được ghép **một lần**, không bị thiếu hoặc nhân đôi. Chọn rõ header format/prefix handling theo Spring MVC 7.1 nếu cần. Không hardcode đường dẫn prefix từ client tùy ý như một property tin cậy.

### 7.4. Security negative test: attacker giả mạo forwarded host

~~~bash
curl -i \
  -H 'X-Forwarded-Proto: https' \
  -H 'X-Forwarded-Host: attacker.example.test' \
  -H 'X-Forwarded-Port: 443' \
  http://127.0.0.1:8080/go
~~~

Trong lab `framework`, Location **có thể** thành `https://attacker.example.test/probe`. Đó là bằng chứng vì sao backend không được exposed trực tiếp khi đang tin forwarded headers. **Không sử dụng kết quả này để tạo open redirect trên một dịch vụ công khai**; chỉ chạy ở localhost.

Trong staging/production, phép thử thực là gửi headers giả **đến public edge**, không phải trực tiếp backend. Expected: proxy strip/overwrite và Spring nhận **origin hợp lệ đã được kiểm**, không chuyển Location sang attacker host. Nếu Location bị nhiễm giá trị attacker, phải sửa proxy trust boundary, Host allowlist, forwarding strategy trước khi triển khai.

## 8. Native forwarding và Tomcat RemoteIpValve

Với `server.forward-headers-strategy=native`, Boot dựa vào server container. Tomcat hỗ trợ `RemoteIpValve` để xử lý remote IP/protocol từ trusted proxies. Có thể cấu hình (fragment):

~~~properties
server.forward-headers-strategy=native
server.tomcat.remoteip.remote-ip-header=x-forwarded-for
server.tomcat.remoteip.protocol-header=x-forwarded-proto

# Chỉ là ví dụ mạng nội bộ có CIDR được diễn đạt bằng regex phù hợp:
server.tomcat.remoteip.internal-proxies=10\.\d{1,3}\.\d{1,3}\.\d{1,3}
~~~

**Không copy regex này vào production một cách máy móc.** Regex biểu diễn nhóm địa chỉ cần được thiết kế/test theo proxy IPs thật, IPv6, hops và security boundaries. Tomcat có defaults cho internal proxies; các mạng nội bộ trong Docker/k8s thay đổi theo cluster.

### 8.1. Vì sao cURL trực tiếp localhost có thể cho kết quả khác?

RemoteIpValve chỉ tin forwarded headers khi peer địa chỉ nguồn được xem là proxy tin cậy theo policy. Nếu bạn thử từ một địa chỉ **không thuộc trusted set**, Tomcat có thể bỏ qua hoặc xử lý khác với test trên loopback. Đó là hành vi an toàn, không phải lỗi.

Phép thử native đúng nhất:

1. Deploy proxy test có IP xác định và sanitize headers.
2. Kiểm app chỉ nhận backend traffic từ subnet/NetworkPolicy đó.
3. Gửi request qua proxy để kiểm request.getScheme/getRemoteAddr và Location.
4. Gửi request từ nguồn khác hoặc spoofed headers để đảm bảo không được tin.
5. So với framework mode để chọn chiến lược đáp ứng nhu cầu (prefix/RFC7239/trusted IP).

**Không** đặt `server.tomcat.remoteip.internal-proxies=` rỗng chỉ để mọi cURL test “xanh”. Theo tài liệu Boot, điều đó có thể làm Tomcat **tin mọi proxy**, không an toàn trong production.

## 9. SSL/TLS: kiểm server thật chứ không chỉ property

### 9.1. Thành phần TLS handshake

~~~text
TLS client                          Spring Boot HTTPS server
    |                                       |
    +-- ClientHello: SNI=localhost -------->|
    |       ALPN=h2,http/1.1                |
    |<--------- ServerHello + certificate --+
    |                                       |
    +-- Validate cert chain to trusted CA
    +-- Check SAN matches hostname/IP in URL
    +-- Check notBefore/notAfter, key usage, policy
    +-- Verify TLS handshake succeeds
    |                                       |
    +-- HTTP/2 or HTTP/1.1 request -------->|
    |<-------------- response --------------+
~~~

**TLS success** cần cả cryptographic handshake và đúng **danh tính server**. Chỉ dùng `https://...` hoặc một socket có mã hóa không đủ nếu client tắt hostname verification.

### 9.2. Keystore vs truststore

- **Server keystore**: certificate chain + **private key của server**, được Tomcat sử dụng để chứng minh danh tính.
- **Client truststore**: CA/server public certificate mà client tin khi kiểm server.
- **Server truststore cho mTLS**: CA/cert của **client identities** mà server chấp nhận khi `client-auth=need`.
- **Client keystore cho mTLS**: certificate+private key của **client**, server xác thực phía gọi.

Không copy private key của server sang client để “fix certificate unknown”. Với HTTPS server-auth bình thường, client chỉ cần trust CA/cert public phù hợp, không cần client keypair.

### 9.3. Tạo self-signed certificate có SAN cho lab

Chạy ở project root Linux/macOS/WSL với OpenSSL hỗ trợ `-addext`:

~~~bash
umask 077
mkdir -p tls

openssl req -x509 -newkey rsa:2048 -sha256 -nodes \
  -keyout tls/localhost.key \
  -out tls/localhost.crt \
  -days 7 \
  -subj '/CN=localhost' \
  -addext 'subjectAltName=DNS:localhost,IP:127.0.0.1'

# Xuất PKCS#8 PEM key, được Spring Boot khuyến nghị cho server PEM.
openssl pkcs8 -topk8 -nocrypt \
  -in tls/localhost.key \
  -out tls/localhost.pk8.key

chmod 600 tls/localhost.key tls/localhost.pk8.key

openssl x509 -in tls/localhost.crt -noout \
  -subject -issuer -dates -ext subjectAltName
~~~

- `-nodes` tạo key **không được mã hóa** để thuận tiện cho lab; chỉ chạy ở môi trường cô lập. Production dùng secret manager/ACL/rotation và không commit keys.
- SAN gồm `DNS:localhost` và `IP Address:127.0.0.1`. Khi gọi URL bằng IP thì cần **IP SAN**; `CN=localhost` không thay được SAN.
- PKCS#8 PEM key bắt đầu bằng `BEGIN PRIVATE KEY` (hoặc ENCRYPTED PRIVATE KEY với key mã hóa). Kiểm định dạng, không nhầm với PKCS#1.
- Certificate self-signed cho lab chỉ được tin khi client xác nhận public certificate qua nguồn tin cậy, không mang đi làm CA chung.

### 9.4. Bật TLS+h2 profile

Dừng HTTP baseline, chạy:

~~~bash
mvn package

java -jar target/web-runtime-integration-lab-0.0.1-SNAPSHOT.jar \
  --spring.profiles.active=tls
~~~

Theo `application-tls.properties`, embedded Tomcat lắng nghe **HTTPS trên 127.0.0.1:8443** và bật HTTP/2. Trên port 8443 không có thêm HTTP connector 8080 mặc định; muốn đồng thời phục vụ HTTP+HTTPS phải cấu hình thêm connector (và redirect policy) riêng.

Một cách khác là:

~~~bash
mvn spring-boot:run \
  -Dspring-boot.run.profiles=tls
~~~

Maven command-line quoting có thể khác PowerShell, Bash hoặc Maven wrapper; nếu launch không dùng đúng profile, xác nhận qua startup log/cổng/TLS trước khi test.

### 9.5. Kiểm chứng cert/hostname bằng cURL

~~~bash
curl -v --cacert tls/localhost.crt \
  https://localhost:8443/probe
~~~

Expected: TLS peer certificate được tin theo CA/cert supplied, hostname `localhost` khớp SAN, trả JSON `scheme=https`, `secure=true`, `port=8443` (unless proxy forwards).

Lệnh theo IP:

~~~bash
curl -v --cacert tls/localhost.crt \
  https://127.0.0.1:8443/probe
~~~

Cũng có thể thành công vì certificate lab chứa IP SAN 127.0.0.1. Nếu thiếu IP SAN, lệnh theo IP phải thất bại hostname verification. Dùng `--cacert` chỉ tác động **cURL command đó**; không làm JDK truststore hay Spring outbound client tự thay đổi.

### 9.6. Negative test: CA không đáng tin

~~~bash
curl -v https://localhost:8443/probe
~~~

Trên máy không có cert self-signed này trong default truststore, cURL thường từ chối cert chưa trusted, trước khi gửi HTTP request. Nếu máy bạn đã cài cert này vào CA store, test có thể **không thất bại**; khi đó cần một truststore cô lập hoặc cert khác chưa tin để test chính xác.

**Không dùng `-k`/`--insecure` và không tạo TrustManager chấp nhận mọi cert** để làm test pass; điều đó vô hiệu hóa phép thử danh tính server.

### 9.7. Negative test: hostname/SAN sai

~~~bash
curl --noproxy '*' \
  --resolve wrong.example.test:8443:127.0.0.1 \
  --cacert tls/localhost.crt \
  -v https://wrong.example.test:8443/probe
~~~

Lệnh ép DNS `wrong.example.test` về 127.0.0.1 nhưng URL hostname vẫn là `wrong.example.test`. Certificate chỉ có SAN localhost/127.0.0.1, nên hostname verification phải thất bại, dù public cert được tin. Nếu thành công bất ngờ, kiểm cURL implementation, proxy, TLS terminator và SAN thật.

`--resolve` không đổi hostname validation thành 127.0.0.1; điều này rất hữu ích khi kiểm SNI và chứng thư cho domain public trước khi đổi DNS.

### 9.8. OpenSSL kiểm SNI, chain, hostname và ALPN

~~~bash
openssl s_client \
  -connect localhost:8443 \
  -servername localhost \
  -CAfile tls/localhost.crt \
  -verify_hostname localhost \
  -verify_return_error \
  -alpn h2,http/1.1 </dev/null
~~~

Kiểm output:

- Verify return code 0 (ok) khi chain/hostname đúng theo OpenSSL trust options.
- ALPN protocol được chọn như `h2` hoặc `http/1.1` nếu được thương lượng.
- Cipher/protocol TLS hợp lệ theo policy.
- Leaf cert, issuer, validity/SAN đúng với listener đang chạy.

Output/số cipher/handshake details thay đổi theo OpenSSL/JDK/Tomcat; **không hardcode** một cipher hoặc TLS 1.3 suite nào cho mọi môi trường. `openssl s_client` có thể mở connection và chờ dữ liệu; `</dev/null` giúp lệnh phù hợp POSIX shell.

Để xem chứng thư live endpoint (đây là inspect, chưa đủ verify hostname/CA nếu không có opts):

~~~bash
openssl s_client -connect localhost:8443 \
  -servername localhost -showcerts </dev/null 2>/dev/null \
  | openssl x509 -noout -subject -issuer \
      -serial -dates -fingerprint -sha256 -ext subjectAltName
~~~

Đừng kiểm chỉ một file `tls/localhost.crt` rồi kết luận Tomcat đang phục vụ cert mới. Cần inspect **certificate được trình ra bởi socket thật**, nhất là khi load balancer có nhiều instances.

### 9.9. Chứng thư sắp hết hạn và clock

~~~bash
openssl x509 -in tls/localhost.crt -noout -dates
openssl x509 -in tls/localhost.crt -noout -checkend 86400
~~~

`-checkend 86400` hỏi liệu cert còn hiệu lực trong ít nhất 24 giờ tới (exit code 0 thường là “còn”, nonzero là “sắp hết hạn/không hợp lệ”). Test này không thay thế chain/SAN/TLS handshake.

Trong CI/staging, kiểm expired cert, missing intermediate, wrong key/certificate pair, unsupported cipher/protocol và SNI mismatch khi thuộc scope của service. Không gửi server private key qua logs/artifacts.

## 10. HTTP/2: bật property khác với chứng minh đã thương lượng thành công

Spring Boot 4.1 hỗ trợ cả:

- **h2:** HTTP/2 qua TLS, thường được chọn qua **ALPN** trong handshake.
- **h2c:** HTTP/2 không mã hóa qua TCP, thường dùng trong trusted internal hops hoặc lab.
- **HTTP/1.1 fallback:** một client/server có thể dùng HTTP/1.1 dù `server.http2.enabled=true` nếu ALPN/protocol support không phù hợp.

### 10.1. HTTP/2 qua TLS

Với profile `tls` đang chạy:

~~~bash
curl -V
curl --http2 --cacert tls/localhost.crt \
  -v https://localhost:8443/probe
~~~

`curl -V` giúp kiểm binary có hỗ trợ HTTP/2 qua nghttp2 hoặc backend tương ứng. Nếu chưa được build với HTTP/2, cURL có thể báo tùy chọn không hỗ trợ. `--http2` **yêu cầu/đề nghị h2**, nhưng kiểm response protocol thật: khi thành công có status line `HTTP/2 200` hoặc verbose nói server accepted h2. Nếu output là HTTP/1.1, phải điều tra ALPN/TLS/server/edge, không kết luận h2 đã bật.

Lệnh đối chứng ép HTTP/1.1:

~~~bash
curl --http1.1 --cacert tls/localhost.crt \
  -v https://localhost:8443/probe
~~~

Kỳ vọng route trả body cùng logic nhưng protocol hiển thị/HTTP request khác. H2 không tự biến dữ liệu JSON body thành một schema khác; nó thay **framing, multiplexing, header compression và flow control** trên transport.

### 10.2. HTTP/2 cleartext (h2c)

Dừng profile `tls`; bật profile `h2c`:

~~~bash
java -jar target/web-runtime-integration-lab-0.0.1-SNAPSHOT.jar \
  --spring.profiles.active=h2c
~~~

Gọi:

~~~bash
curl --http2-prior-knowledge \
  -v http://127.0.0.1:8080/probe
~~~

`--http2-prior-knowledge` gửi h2c trực tiếp theo prior knowledge, không chờ HTTP/1.1 Upgrade. Với Tomcat 11 và Boot hỗ trợ h2c, bạn có thể thấy response HTTP/2; nếu cURL/version/connector không hỗ trợ, test phải fail và giải thích root cause, không im lặng fallback.

Lệnh đối chứng:

~~~bash
curl --http1.1 -v http://127.0.0.1:8080/probe
~~~

**Không triển khai h2c trên Internet nếu cần confidentiality/integrity.** HTTP/2 không đồng nghĩa có TLS; `h2c` vẫn cleartext. Nếu edge terminate TLS và backend dùng h2c, chính sách trust của mạng backend vẫn phải được kiểm.

### 10.3. External h2 không bằng backend h2

~~~text
Browser -- TLS+ALPN h2 --> Ingress / Envoy / Nginx
                               |
                               +-- HTTP/1.1 plaintext --> Spring MVC/Tomcat
                               |
                               +-- or h2c/TLS+h2 ------> Spring Boot
~~~

Kiểm hai hops riêng:

1. Ngoài edge: `curl --http2 https://public-host/probe` và `openssl s_client -alpn h2...` xác nhận TLS+h2 tới edge.
2. Trong trusted network: probe trực tiếp tới Boot backend IP:port bằng cURL HTTP/1.1/h2c/TLS theo topology.
3. Ở app: `request.getProtocol()` phản ánh backend request mà app nhìn thấy, không cho biết chính xác phiên browser→edge.
4. Trong proxy config: xác nhận upstream protocol, connection reuse, timeouts, forwarded headers, HTTP2-to-HTTP1 conversion.
5. Không chỉ nhìn response HTTP/2 ở client rồi tuyên bố `server.http2.enabled` của Boot đang có hiệu lực.

### 10.4. HTTP/2 không phải chỉ là “nhanh hơn”

HTTP/2 có multiplexing, HPACK header compression, stream priority/flow control và các giới hạn ở connection/stream. Kiểm:

- Nhiều requests song song trên một TLS connection.
- Max concurrent streams, stream resets, flow-control stalls và size của headers.
- TLS handshake/ALPN fallback và proxy upstream.
- Client/broker load, latency p95/p99 và memory/CPU.
- Cookies/large headers khi HPACK compression kết hợp header size caps.
- Graceful server shutdown có thể phát HTTP/2 GOAWAY; không tự đồng nghĩa WebSocket close frame.
- HTTP/2 có thể có lợi trên WAN nhưng không đảm bảo tăng RPS với mọi workload, nhất là nếu bottleneck là DB.

### 10.5. HTTP/2 kết hợp WebSocket và gRPC

Một browser có WebSocket classic qua HTTP/1.1 Upgrade không tự chuyển thành HTTP/2 WebSocket RFC 8441 chỉ vì server.http2.enabled. gRPC thường dựa vào HTTP/2 transport và cần kiểm riêng gRPC server stack, metadata, streaming và LB. Không dùng GET /probe đơn giản làm bằng chứng toàn bộ WebSocket/gRPC trên HTTP/2 đã tương thích.

## 11. Chạy TLS và HTTP/2 trong Java 17 client test

Ngoài cURL, JDK 17 có `java.net.http.HttpClient.Version.HTTP_2`. Nó có thể **đề nghị HTTP/2**, nhưng phải kiểm `HttpResponse.version()` để xác nhận giao thức thực được chọn.

Trên lab dùng self-signed cert, có thể tạo PKCS12 truststore từ public certificate:

~~~bash
keytool -importcert -noprompt \
  -alias localserver \
  -file tls/localhost.crt \
  -keystore tls/client-trust.p12 \
  -storetype PKCS12 \
  -storepass changeit
~~~

`changeit` chỉ là password demo. Trong production dùng secret management và không truyền mật khẩu thực qua CLI/history/process list.

### 11.1. Tạo file Http2ClientDemo.java

~~~java
import java.io.InputStream;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;

import javax.net.ssl.SSLContext;
import javax.net.ssl.TrustManagerFactory;

public class Http2ClientDemo {

    public static void main(String[] args) throws Exception {
        KeyStore trustStore = KeyStore.getInstance("PKCS12");
        char[] password = "changeit".toCharArray();

        try (InputStream in =
                     Files.newInputStream(Path.of("tls/client-trust.p12"))) {
            trustStore.load(in, password);
        }

        TrustManagerFactory tmf = TrustManagerFactory.getInstance(
                TrustManagerFactory.getDefaultAlgorithm());
        tmf.init(trustStore);

        SSLContext context = SSLContext.getInstance("TLS");
        context.init(null, tmf.getTrustManagers(), null);

        HttpClient client = HttpClient.newBuilder()
                .sslContext(context)
                .version(HttpClient.Version.HTTP_2)
                .build();

        HttpRequest request = HttpRequest.newBuilder(
                URI.create("https://localhost:8443/probe"))
                .GET()
                .build();

        HttpResponse<String> response = client.send(
                request, HttpResponse.BodyHandlers.ofString());

        System.out.println("HTTP status: " + response.statusCode());
        System.out.println("Version: " + response.version());
    }
}
~~~

Đây là **chương trình Java 17 độc lập** ngoài classpath Spring Boot. Nó xây truststore dùng cert public cụ thể, **không tắt hostname verification**. Kết nối qua hostname `localhost` phải khớp SAN của cert server. Nó dùng HTTP/2 nếu negotiation thành công, còn nếu server/client fallback thì `response.version()` có thể báo HTTP_1_1.

Chạy (phải có profile TLS/h2 đang nghe 8443):

~~~bash
javac --release 17 Http2ClientDemo.java
java Http2ClientDemo
~~~

Nếu handshake và HTTP/2 thành công, stdout dạng:

~~~text
HTTP status: 200
Version: HTTP_2
~~~

Nếu thực tế fallback HTTP/1.1, dòng hai là `Version: HTTP_1_1`. Đây là expected **theo điều kiện**, không lời hứa JDK sẽ luôn chọn h2 bất kể server/proxy. Nếu cert sai CA/SAN, chương trình sẽ ném SSLHandshakeException/SSLPeerUnverifiedException và không gửi status 200.

**Không** dùng global `-Dcom.sun.net.ssl.checkRevocation=false` hay custom TrustManager tin mọi cert làm test pass. Đặc biệt, một client chỉ trust lab self-signed cert không đồng nghĩa được phép tin mọi public CA.

### 11.2. Test negative bằng Java

Thay URI thành:

~~~java
// Fragment: nếu URI hostname không có SAN phù hợp, handshake phải fail,
// kể cả khi DNS được route đến server theo một cách có kiểm soát.
URI.create("https://wrong.example.test:8443/probe");
~~~

Chỉ thay URI như vậy sẽ cần DNS route trước, nên để test hostname mismatch **đáng tin** thường dùng cURL `--resolve` hoặc test DNS/hosts setup trong staging. Không sửa hosts toàn hệ thống bừa bãi hoặc tắt hostname check.

### 11.3. Test HTTP/2 không TLS bằng JDK

Với profile `h2c`, Java HttpClient 17 hỗ trợ HTTP/2 upgrade semantics nhưng cách nó chọn h2c có thể phụ thuộc request/implementation và proxy. `curl --http2-prior-knowledge` có hành vi rõ hơn cho connector h2c; nên dùng cURL để assert h2c direct và dùng JDK HttpClient để test TLS+h2. Đừng khẳng định mọi JDK client có chế độ prior-knowledge giống cURL.

## 12. Phần mở rộng: TLS client-auth (mTLS), SNI và nhiều certs

### 12.1. mTLS là một test case khác

Nếu server yêu cầu mTLS:

~~~properties
# Fragment của profile mTLS, phải có CA trust vật liệu đúng:
server.ssl.client-auth=need

# Nếu dùng SSL bundle cho server, khai truststore CA client trong bundle:
spring.ssl.bundle.pem.labhttps.truststore.certificate=file:./tls/client-ca.crt
~~~

Server-auth TLS đã xác minh **server**; mTLS thêm kiểm danh tính **client**. Để test cần tạo client private key/cert đúng CA và curl với:

~~~bash
curl --cacert tls/localhost.crt \
  --cert tls/client.crt \
  --key tls/client.key \
  https://localhost:8443/probe
~~~

Đây là **một phương án minh họa**: các file client-ca.crt/client.crt/client.key phải được cấp phát theo PKI thực hoặc tự tạo riêng trong lab. Không khẳng định lệnh chạy nếu chưa tạo các file đó. Negative tests: thiếu client cert, cert hết hạn, wrong client CA, client key mismatch. Test TLS handshake failure trước HTTP layer, không nhầm với HTTP 401 từ Spring Security.

### 12.2. SNI nhiều hostnames

Nếu một listener TLS phục vụ nhiều domains, client gửi **SNI** để server chọn đúng cert. Spring Boot có `server.ssl.server-name-bundles` trên một số server implementations theo tài liệu. Khi test:

~~~bash
openssl s_client \
  -connect 127.0.0.1:8443 \
  -servername api.example.test \
  -showcerts </dev/null
~~~

Và:

~~~bash
openssl s_client \
  -connect 127.0.0.1:8443 \
  -servername alt.example.test \
  -showcerts </dev/null
~~~

Đừng kết luận một chứng thư hợp lệ chỉ vì leaf có đúng CN; kiểm SAN/hostname và chain cho **từng SNI hostname** bằng options trust/verify phù hợp. Hỗ trợ SNI mapping khác giữa Tomcat/Jetty/Netty, phải kiểm theo runtime. Đừng dùng cert demo localhost để mong xác thực production hostname.

### 12.3. TLS termination tại proxy

Trong topology:

~~~text
Client --HTTPS--> proxy --HTTP--> Boot
~~~

App có thể không bật `server.ssl.bundle`/port HTTPS nội bộ; certificate khách hàng kiểm là **certificate của proxy**. Vẫn phải:

- Xác minh public TLS cert/chain/SAN, SNI và ALPN ở proxy.
- Có chiến lược bảo vệ internal hop (private network, network policy, hoặc TLS/mTLS nếu cần).
- Sanitize forwarded headers trước Boot.
- Kiểm generated URLs/redirects theo external origin.
- Phân biệt `request.isSecure()` do forwarded metadata với **sự tồn tại của TLS thực sự ở backend**. `isSecure=true` sau xử lý header không chứng minh proxy→Boot được mã hóa.

## 13. Kiểm thử reverse proxy thật

Một test riêng lẻ bằng cURL trực tiếp backend chỉ chứng minh Spring **dùng forwarded headers**, không chứng minh headers được thiết lập bởi một proxy đáng tin. Trong staging, thêm một reverse proxy thật và assert:

~~~text
Public test client:
  URL https://edge.example.test/go
  Injected X-Forwarded-Host: attacker.example.test
  Injected Forwarded: host=attacker.example.test;proto=http

Edge:
  - nhận diện Host hợp lệ
  - xóa incoming Forwarded + mọi X-Forwarded-* của client
  - set các headers chuẩn từ connection/TLS/DNS được xác minh
  - route tới backend trusted IP:port

Backend:
  - nhận trusted forwarded data
  - redirect Location trỏ đúng https://edge.example.test/probe
  - không dùng attacker.example.test để tạo absolute URL
~~~

**Cấu hình proxy phụ thuộc sản phẩm, version và topology**. Không đưa vào README một file Nginx production “copy chạy ngay” mà bỏ qua certificate paths, server_name allowlist, XFF trust chain, body size/timeouts và Nginx version. Có thể dùng một fragment ý tưởng:

~~~nginx
# Fragment minh họa nằm trong location của HTTPS server,
# cần allowlisted server_name và network policy ở mức server/infra.
proxy_set_header Host $host;
proxy_set_header Forwarded "";
proxy_set_header X-Forwarded-Proto $scheme;
proxy_set_header X-Forwarded-Host $host;
proxy_set_header X-Forwarded-Port $server_port;
proxy_set_header X-Forwarded-For $remote_addr;
proxy_pass http://127.0.0.1:8080;
~~~

Chỉ dùng `$remote_addr` ở **edge nơi peer là client được xác minh**. Nếu còn trusted intermediary/load balancer trước Nginx, địa chỉ đó có thể là của proxy trước: cần xử lý real IP theo allowlist và nguồn header đáng tin. Không dùng `$proxy_add_x_forwarded_for` tùy tiện nếu incoming XFF có thể do attacker tự đặt.

Một edge phải strip forwarded headers thuộc cả hai họ nếu quyết định dùng chỉ một họ. Chú ý `X-Forwarded-Prefix`/`X-Forwarded-Ssl` và những headers vendor-specific khác nếu hệ thống hiểu chúng.

### 13.1. Test redirect sau proxy

~~~bash
curl -i --http2 https://edge.example.test/go
~~~

Expected:
- External TLS certificate hợp hostname.
- Khi edge hỗ trợ h2, cURL ghi nhận HTTP/2 trên **client→edge hop**.
- `Location` không chứa `http://backend:8080` và không chứa attacker host.
- Nếu app có prefix, absolute path giữ đúng prefix một lần.
- Nếu dùng `Secure` cookies/OAuth redirects, chúng phù hợp external scheme và domain.

Thử negative:

~~~bash
curl -i \
  -H 'X-Forwarded-Host: attacker.example.test' \
  -H 'X-Forwarded-Proto: http' \
  -H 'Forwarded: for=198.51.100.9;host=attacker.example.test;proto=http' \
  https://edge.example.test/go
~~~

Kết quả phải **không** dùng attacker host. Nếu có, đây là vấn đề security boundary nghiêm trọng, không phải test có thể skip bằng cách cập nhật expected value.

## 14. Thử giới hạn server và HTTP parsing

### 14.1. Header size

Baseline có:

~~~properties
server.max-http-request-header-size=8KB
~~~

Một request header rất lớn có thể bị embedded server từ chối trước khi tới MVC controller. Ví dụ POSIX shell:

~~~bash
BIG_VALUE=$(head -c 20000 /dev/zero | tr '\000' 'A')

curl --http1.1 -i \
  -H "X-Large-Test: $BIG_VALUE" \
  http://127.0.0.1:8080/probe
~~~

Đây là **negative test trong lab**, không chạy trên public production endpoints. Status có thể là 400, 431 hoặc kết nối bị đóng tùy container/version/proxy; hãy xác nhận **request không bị xử lý thành công** và memory không tăng bất thường. Không cứng hóa HTTP 431 cho mọi server.

Headers HTTP/2 dùng HPACK nên compressed wire size khác decoded header list size. Nếu test raw TCP HTTP/1.1 header size pass, không đồng nghĩa HTTP/2 header list limit đã pass. Ngược lại, proxy có thể từ chối trước Boot; ghi rõ layer đang kiểm.

### 14.2. Thread/connections/timeouts

Đặt `server.tomcat.threads.max=64` không có nghĩa chỉ hỗ trợ 64 concurrent connections, vì keep-alive/HTTP2 multiplexing/async handling khác request workers. Để kiểm:

1. Dùng load generator có connection/concurrency control (k6, hey, wrk2) trên lab.
2. Giữ cả short requests, slow clients và streaming requests.
3. Quan sát Tomcat busy threads, accepted connections, queue/rejections, latency và error.
4. Kiểm timeout khi client gửi header/body rất chậm, nhưng không nhầm với network timeout của proxy.
5. So với Jetty hoặc WebFlux để thấy limits không chuyển dịch một-một.

**Đừng** viết một test `sleep 1s × 100 requests` rồi tuyên bố đã đo TCP timeout, vì wait queue và OS scheduling có thể chi phối. Cần phân biệt connect timeout, request header timeout, keep-alive timeout, async request timeout và TLS handshake timeout.

### 14.3. Request/response compression

Nếu cần kiểm `server.compression.enabled`, chỉ test khi response đủ MIME/size và client gửi `Accept-Encoding: gzip`, rồi inspect `Content-Encoding`. Compression là một bước khác của web runtime; không dùng nó làm bằng chứng về TLS hoặc h2. Một HTTPS server có thể gửi response không nén qua HTTP/2; đó vẫn là HTTPS+h2 hợp lệ.

## 15. CI/CD: thiết kế ma trận thay vì một test xanh duy nhất

### 15.1. Ma trận đề xuất

| Case | Server | Proxy | TLS | HTTP protocol | Assert |
| --- | --- | --- | --- | --- | --- |
| A | Tomcat | Không | Tắt | HTTP/1.1 | HTTP 200 /probe, scheme=http |
| B | Tomcat | Headers giả, strategy none | Tắt | HTTP/1.1 | Không đổi effective origin |
| C | Tomcat | Forwarding framework (localhost) | Tắt | HTTP/1.1 | Scheme/host/redirect đúng external origin |
| D | Tomcat | Proxy trusted thật | TLS ở edge | External h2, backend h1 | Location không nhiễm attacker |
| E | Tomcat | Không | PEM self-signed lab | HTTPS+h2 | Cert/SAN verified, ALPN h2 |
| F | Tomcat | Không | PEM self-signed lab | HTTPS+h1.1 | HTTP/1.1 fallback vẫn hoạt động |
| G | Tomcat | Không | PEM self-signed lab | Negative hostname | Handshake từ chối |
| H | Tomcat | Không | PEM self-signed lab | Negative CA | Handshake từ chối |
| I | Tomcat | Không | Tắt | h2c | cURL prior knowledge chọn h2c |
| J | Tomcat | Không | Tắt | HTTP/1.1 | Oversized header bị từ chối |
| K | Jetty | Proxy trusted | Tùy | h2/h1 | So hỗ trợ và config Jetty riêng |
| L | Reactor Netty | Proxy trusted | Tùy | h2/h2c | Transformer/Netty flow |
| M | TLS terminator/ingress | Có | Public CA | External HTTP/2 | Đúng SNI/cert/scheme, upstream kiểm riêng |
| N | TLS/mTLS | Không | Client cert bắt buộc | h1/h2 | Wrong client cert bị từ chối |

Case A–C tự động trong Maven project; D–N cần cấu hình môi trường/credentials/tooling tương ứng. **Không claim toàn bộ matrix đã chạy** chỉ vì `mvn test` pass.

### 15.2. Quy tắc pass/fail

- HTTP status/response body phải đúng route và config đã chọn.
- Khi test proxy functionality, scheme/host/port/Location phải là expected external values.
- Khi test security, header attacker phải **không** thay đổi generated URL.
- TLS tests phải validate CA/chain/hostname/SNI, không dùng trust-all.
- HTTP/2 tests phải **assert protocol negotiated**, không chỉ assert 200.
- Negative tests phải fail đúng lớp/giai đoạn (TLS handshake vs HTTP 400 vs proxy 502).
- Không bị cắt ngắn response khi proxy rewrites/h2 multiplexing/timeout.
- Khi tắt profile/đổi container, test không bị cache wrong ApplicationContext/port.
- Test có log/diagnostics đủ để phân biệt failing layer, không lộ secrets/cert private keys.

### 15.3. Profile isolation

Nên có profiles rõ ràng:

~~~text
default       -> HTTP/1.1, no forwarding
proxy         -> HTTP/1.1, framework forwarding
h2c           -> HTTP/2 cleartext
tls           -> HTTPS + h2 with SSL bundle
native-proxy  -> tùy chọn riêng, test RemoteIpValve từ trusted proxy
~~~

Không nên bật `tls,proxy,h2c` cùng lúc rồi suy rằng tất cả properties sẽ có nghĩa mong muốn. Test sử dụng mỗi cấu hình riêng, ghi rõ port/client mode. Với TLS profile, cung cấp certs bằng secret/temporary test fixtures và xóa private key khi kết thúc CI.

### 15.4. TestContainer hoặc proxy thật

Với các cảnh báo forwarded header spoofing, chỉ dùng MockMvc hoặc một HTTP client gửi header trực tiếp **không đủ**. Có thể chạy Nginx/Envoy/Traefik trong Testcontainers (hoặc Docker Compose) ở CI và cấu hình trusted network:

- Test traffic qua proxy.
- Inject cả `Forwarded` và `X-Forwarded-*` độc hại.
- Assert proxy strip và backend effective origin đúng.
- Check forwarding chain IP, prefixes, redirects.
- Test TLS ở edge và backend (nếu có) riêng.
- Check h2 client-edge, h1/h2c/h2 proxy-backend riêng.

Đây là **thiết kế bài test**, không có Docker Compose file tự chạy đi kèm, vì cấu hình CA/ports/image/dns/trust boundary cần tùy hạ tầng. Không đặt host networking và allowlists vô hạn chỉ để các integration tests pass.

## 16. Logging, metrics và troubleshooting

### 16.1. Quan sát tối thiểu

| Signal | Dùng để hiểu gì | Cẩn trọng |
| --- | --- | --- |
| Startup log/server info | Container và port đang listen | Không chứng minh ALPN success |
| `/probe` fields | Scheme/host/port/protocol theo backend | Không chứng minh headers trusted |
| cURL `-v`/`--http2` | Giao thức edge thật, TLS cert | Cần kiểm hỗ trợ HTTP2 trong cURL build |
| OpenSSL `s_client` | SNI, certificate, trust, ALPN | Cần -CAfile và -verify_hostname để verify |
| Access logs | HTTP method/path/status/protocol | Mask tokens/query/PII |
| Micrometer `http.server.requests` | Latency/error theo URI templates | Không gắn raw URI/user ID |
| Tomcat metrics | Threads, connections, sessions | Cần connector/MBean settings phù hợp |
| Proxy logs | Upstream/downstream status, TLS, h2, retries | Client-edge và backend protocol là hai hops |
| Packet capture | TLS/HTTP2 frame timing | Privacy/authorization, encrypted payload |
| CPU/GC/memory | Tác động h2/compression/connection load | Không suy từ một cURL |
| Client cert errors | TLS trust/SAN/protocol | Không trả private key/password vào log |

### 16.2. Debug thứ tự đúng

Nếu client nhận redirect `http://internal:8080/login`:

1. Kiểm browser/cURL external URL/scheme.
2. Kiểm LB/proxy đã strip và set forwarded headers chưa.
3. Kiểm Boot `server.forward-headers-strategy` có đúng với trusted environment.
4. Kiểm Tomcat `redirect-context-root=false` nếu thuộc tình huống SSL termination.
5. Kiểm headers ở backend theo logging đã redacted; không dump Authorization.
6. Kiểm controller URI builder và context path/prefix.
7. Kiểm Host allowlist/security rồi thử spoofed header.
8. Không “fix” bằng cách hardcode host public cho mọi môi trường nếu có multi-tenant domains mà chưa đánh giá.

Nếu cURL `--http2` vẫn thấy HTTP/1.1:

1. `curl -V` có hỗ trợ HTTP2?
2. Client đang nói với proxy hay Boot direct?
3. TLS handshake có ALPN `h2`? Dùng `openssl s_client -alpn...`.
4. `server.http2.enabled=true` có nằm trong profile active?
5. Embedded container hỗ trợ h2/h2c theo version/dependencies không?
6. Có SSL bundle/TLS certificate/port đúng?
7. Proxy có downgrade sang HTTP/1.1 upstream không?
8. Có fail vì SNI/TLS policy/header sizes không?
9. Nếu là h2c, dùng `curl --http2-prior-knowledge` đúng port và cleartext.
10. So logs và packet tracing nếu cần, không tắt certificate validation.

Nếu `curl --cacert` pass nhưng Java client báo PKIX:

- cURL truststore cho command không cùng JSSE/JDK truststore.
- Certificate chain/intermediates có thể khác theo SNI/proxy.
- JDK client có thể dùng hostname/URL khác.
- HTTP/2 fallback không gây PKIX; đó là TLS identity validation.
- Không copy server private key vào truststore; chỉ dùng public CA/cert được xác minh.

### 16.3. Security checklist

- [ ] Backend không public Internet khi tin forwarded headers; proxy strip cả hai họ Forwarded/X-Forwarded-*.
- [ ] Proxy peer IP/CIDR allowlist chính xác; không để trống Tomcat internal-proxies để trust tất cả.
- [ ] Host và redirect destination được allowlist/validated khi đưa vào links/password reset/OAuth.
- [ ] HTTPS verifies CA chain, SAN/hostname, validity, key usage, SNI; không dùng trust-all hoặc curl -k.
- [ ] TLS secret/private key chỉ ở secret manager/volume có ACL; không commit/upload vào logs.
- [ ] Port h2c chỉ ở trusted network nếu không mã hóa; không coi h2c là HTTPS.
- [ ] HTTP/2 max header/concurrent streams/frame controls và DoS limits được đánh giá.
- [ ] Không để insecure endpoint /probe hoặc Actuator lộ nội bộ trong production.
- [ ] Reverse proxy HTTPS redirect/HSTS/Cookie Secure được test ở external origin.
- [ ] mTLS nếu áp dụng có cả đúng client identity và server trust; HTTP authorization vẫn cần.

## 17. Những sai lầm thường gặp

| Sai lầm | Vì sao sai? | Cách sửa |
| --- | --- | --- |
| Test `@WebMvcTest` pass nên kết luận TLS/h2 hoạt động | MockMvc không có handshake/ALPN thật | Test random port/cURL/OpenSSL |
| Dùng `server.tomcat.*` trên Netty | Khác server factory/config | Chọn property/Customizer theo runtime |
| Chỉ kiểm property `server.http2.enabled=true` | Có thể fallback h1 | Kiểm HTTP response version và ALPN |
| Thấy browser dùng HTTP/2, suy backend cũng h2 | Proxy có thể h2→h1 | Kiểm từng hop |
| Bật `FRAMEWORK` mà backend public | Client tự giả mạo forwarded host | Network isolation + proxy sanitize |
| Chỉ strip X-Forwarded, giữ Forwarded | Attacker dùng header họ còn lại | Strip cả hai họ ở edge |
| Tin phần tử đầu XFF | Attacker có thể gắn IP giả | Trusted chain, proxy overwrite |
| Đặt Tomcat internal-proxies rỗng | Có thể trust mọi proxy | Explicit IP ranges/regex, test âm tính |
| Expect 404/503 cho mọi TLS error | TLS lỗi trước khi có HTTP | Phân biệt handshake exception |
| Dùng curl -k để “test” cert | Bỏ trust/hostname validation | Dùng --cacert và negative tests |
| SAN chỉ DNS nhưng gọi URL qua IP | IP SAN cần riêng | Dùng hostname đúng/cấp IP SAN |
| Đặt server.ssl.bundle cùng keystore properties rời | Config xung đột/ignored | Dùng một cơ chế TLS rõ ràng |
| Chỉ đọc cert local file | Proxy/pod có thể phục vụ cert khác | Inspect live endpoint với SNI |
| Bật gzip rồi nói đã bật h2 | Compression không liên quan version | Kiểm ALPN/response protocol |
| h2c qua Internet có token | h2c không mã hóa | TLS h2 hoặc private backend hop |
| curl --http2 không kiểm cURL build | Có thể không hỗ trợ nghttp2 | curl -V, assert negotiated |
| HTTP/2 header limit = HTTP/1.1 bytes | HPACK/header list khác | Test cả h2 và h1 |
| Response body đúng nên Host trustworthy | App có thể tin header giả | Test spoofed host/redirect |
| Không test redirect/cookie qua proxy | Absolute URLs/http scheme sai | Kiểm Location/Secure/SameSite |
| Chạy profile TLS+proxy+h2c cùng lúc | Properties đè nhau khó dự đoán | Separate configs, active profile assertions |
| Chỉ test localhost | Ingress/CDN/TLS edge còn lỗi riêng | Staging topology matching |
| Dùng JDK 21 API trong source --release 17 | Không compile trên Java 17 | Kiểm Java API, Maven compile/test |
| In JUnit một client theo redirects tự động | Test có thể bỏ qua Location gốc | Disable redirects để assert 302 |
| Hardcode stdout handshake/cipher | Tùy JDK/OpenSSL/OS | Assert protocol/cert invariant |
| Dùng TLS edge mà không bảo vệ backend hop | Internal traffic có thể bị sniff/spoof | NetworkPolicy, service mTLS theo threat model |

## 18. Checklist kiểm thử cuối cùng

### Cấu hình embedded server

- [ ] Đã xác nhận actual server stack/version và starter dependencies?
- [ ] Test server bind đúng address/port, chặn/nhận traffic đúng network policy?
- [ ] Test header-size/timeout/connection limits qua connector thật, không chỉ MockMvc?
- [ ] Tomcat/Jetty/Netty customizers được kiểm và không bỏ sót khi đổi runtime?
- [ ] Có separate profiles h1, h2c, TLS+h2, proxy; không mix xung đột?

### Proxy headers

- [ ] Positive test scheme/host/port/redirect qua trusted proxy.
- [ ] Negative spoof test cả Forwarded và X-Forwarded-* tại external edge.
- [ ] Proxy strip/rewrite đúng, không giữ header độc hại từ client.
- [ ] Native trusted proxy CIDRs/regex có test nguồn tin và không tin.
- [ ] X-Forwarded-Prefix/redirect_context_root nếu dùng được test đủ.
- [ ] Không lộ internal host trong Location, links, cookies, OpenAPI/OAuth URLs.
- [ ] Không nhầm isSecure() sau header transformation với TLS của backend.

### TLS/HTTP/2

- [ ] Chứng thư đang phục vụ đúng SAN, hostname, chain, expiry, SNI?
- [ ] Client trust public cert/CA đúng, không dùng insecure mode?
- [ ] HTTP/2 over TLS có ALPN h2 và response protocol h2?
- [ ] HTTP/1.1 fallback có được test riêng không?
- [ ] h2c chỉ dùng trên trusted backend, curl prior knowledge thật?
- [ ] HTTP/2 multiplexing/headers/flow-control được load test nếu production dùng?
- [ ] Có kiểm external edge protocol khác upstream backend protocol?
- [ ] mTLS nếu dùng có negative missing/wrong client cert?

### CI/observability

- [ ] `mvn test` chạy embedded random-port tests và assertions thực?
- [ ] cURL/OpenSSL checks chạy đúng test profile/cert, có negative cases?
- [ ] CI không đưa TLS private key hoặc mật khẩu thật vào logs/artifacts?
- [ ] Có deployment staging với proxy/Ingress như production?
- [ ] Có metrics/alerts cho handshake failures, 4xx/5xx, TLS expiry, h2 fallback và redirect anomalies?
- [ ] Mọi exception/security leaks được report đúng layer; không sửa bằng cách tắt validation?

## 19. Câu hỏi tự kiểm tra có đáp án

**Câu 1.** Vì sao `MockMvc` không chứng minh Spring Boot đã bật HTTP/2?

**Đáp án:** MockMvc mô phỏng MVC request/response, không có TCP/TLS handshake hoặc ALPN/h2 framing thật. Cần embedded server/cURL/JDK client và assert negotiated protocol.

**Câu 2.** Khi client ngoài dùng HTTPS/HTTP2, vì sao backend `request.getProtocol()` có thể vẫn là HTTP/1.1?

**Đáp án:** Reverse proxy có thể terminate TLS/h2 và gửi HTTP/1.1 vào Spring Boot. Servlet protocol phản ánh backend hop, không phải toàn bộ đường đi client.

**Câu 3.** Khi nào nên dùng `server.forward-headers-strategy=framework`?

**Đáp án:** Khi Spring cần hiểu forwarded scheme/host/prefix và request chỉ đến từ trusted proxy đã sanitize header. Bản thân filter không phân biệt được client giả mạo.

**Câu 4.** Tại sao không chỉ bỏ incoming X-Forwarded-Host mà giữ Forwarded?

**Đáp án:** Attacker có thể gửi giá trị độc hại qua họ chuẩn Forwarded. Edge phải strip cả hai họ trước khi tạo trusted headers mới.

**Câu 5.** `server.ssl.bundle=labhttps` và `server.ssl.key-store=...` có nên dùng cùng lúc không?

**Đáp án:** Không. Khi dùng SSL bundle, giữ cấu hình keystore/cert/key trong bundle; các server.ssl.* tùy chọn rời có thể xung đột hoặc bị bỏ qua.

**Câu 6.** HTTP/2 có thể chạy không TLS không? Có nên đưa h2c ra Internet?

**Đáp án:** Boot 4 hỗ trợ h2c trên TCP, nhưng h2c không mã hóa. Không dùng cho traffic nhạy cảm qua Internet công khai; dùng TLS h2 hoặc bảo vệ trusted internal hop.

**Câu 7.** `curl --http2 https://...` trả 200 đã đủ chứng minh h2 chưa?

**Đáp án:** Chưa. Phải kiểm response protocol thực được thương lượng; client có thể fallback h1. Đồng thời kiểm `curl -V` có hỗ trợ HTTP2.

**Câu 8.** Vì sao gọi `https://127.0.0.1` có thể fail dù cert có CN=localhost?

**Đáp án:** Client kiểm SAN cho IP literal. Cert cần SAN IP Address:127.0.0.1; CN không tự thay SAN.

**Câu 9.** Test spoof forwarded header qua localhost với framework pass có phải test security pass?

**Đáp án:** Không. Nó chỉ chứng minh header được framework dùng. Security test phải chứng minh proxy public strip incoming giả và backend không exposed.

**Câu 10.** Một header quá lớn làm cURL nhận 400 hoặc socket close; có nên hardcode luôn 431?

**Đáp án:** Không. Parser/proxy/container có behavior riêng; assert request bị từ chối ở đúng layer và không gây memory pressure.

**Câu 11.** mTLS có phải chỉ cần client gửi certificate?

**Đáp án:** Không. Server phải trust client CA/cert và vẫn trình server certificate cho client kiểm. Authorization API tiếp tục là một lớp khác.

**Câu 12.** Vì sao test JUnit RANDOM_PORT tốt hơn DEFINED_PORT trong CI song song?

**Đáp án:** OS chọn cổng khả dụng cho từng test server, giảm xung đột cổng cố định. Tuy nhiên TLS/proxy test vẫn cần topology/cert fixture riêng.

**Câu 13.** Test Java HttpClient 17 gọi `version(HTTP_2)` đã đủ xác nhận HTTP2 chưa?

**Đáp án:** Chưa. Client có thể fallback; phải xem `HttpResponse.version()` và TLS ALPN. Client phải trust CA và kiểm hostname hợp lệ.

**Câu 14.** Cần kiểm gì khi password reset link thành `http://internal-host:8080/...`?

**Đáp án:** Proxy forwarded scheme/host, Boot strategy, Tomcat redirect-context-root, URI builder, host validation và test redirect qua public edge.

## 20. Tài liệu chính thức và tiêu chuẩn

- [Spring Boot — Embedded Web Servers, Forwarded Headers, HTTPS and HTTP/2](https://docs.spring.io/spring-boot/4.1/how-to/webserver.html).
- [Spring Boot — Testing Spring Boot Applications, RANDOM_PORT and RestTestClient](https://docs.spring.io/spring-boot/4.1/reference/testing/spring-boot-applications.html).
- [Spring Boot — Common Application Properties (server.http2, server.forward-headers, Tomcat)](https://docs.spring.io/spring-boot/4.1/appendix/application-properties/).
- [Spring Boot — SSL Bundles (PEM/JKS and server.ssl.bundle)](https://docs.spring.io/spring-boot/4.1/reference/features/ssl.html).
- [Spring Boot — Servlet Web Applications](https://docs.spring.io/spring-boot/4.1/reference/web/servlet.html).
- [Spring Boot — Reactive Web Applications](https://docs.spring.io/spring-boot/4.1/reference/web/reactive.html).
- [Spring Boot — Logging](https://docs.spring.io/spring-boot/4.1/reference/features/logging.html).
- [Spring Boot 4.1.2 release announcement](https://spring.io/blog/2026/10/23/spring-boot-4-1-2-available-now/).
- [Spring Framework — ForwardedHeaderFilter and proxy security](https://docs.spring.io/spring-framework/reference/web/webmvc/filters.html).
- [Spring Framework — ForwardedHeaderTransformer (WebFlux)](https://docs.spring.io/spring-framework/reference/web/webflux/filters.html).
- [Spring Framework — REST Client Testing](https://docs.spring.io/spring-framework/reference/testing/resttestclient.html).
- [Jakarta Servlet — HttpServletRequest](https://jakarta.ee/specifications/servlet/6.1/apidocs/jakarta.servlet/jakarta/servlet/http/httpservletrequest).
- [Oracle JDK 17 — java.net.http.HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html).
- [RFC 7239 — Forwarded HTTP Extension](https://www.rfc-editor.org/rfc/rfc7239).
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110).
- [RFC 9113 — HTTP/2](https://www.rfc-editor.org/rfc/rfc9113).
- [RFC 7301 — TLS ALPN](https://www.rfc-editor.org/rfc/rfc7301).
- [RFC 5280 — X.509 Certificate and CRL Profile](https://www.rfc-editor.org/rfc/rfc5280).
- [OWASP — TLS Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Transport_Layer_Security_Cheat_Sheet.html).

**Kết luận:** Khi kiểm thử web runtime của Spring Boot, **phải chứng minh server, proxy và TLS/HTTP2 đang làm đúng trên kết nối thật**. `MockMvc` phù hợp controller logic nhưng không kiểm connector, ALPN hoặc cert. Dùng random-port integration tests cho forwarding và redirects; cURL/OpenSSL/JDK client cho TLS chain/SAN/SNI và h2/h2c; kiểm từng hop khi có reverse proxy; và luôn có negative tests chống forwarded-header spoofing, wrong CA/hostname và HTTP2 fallback. **Không** tắt xác minh TLS hay mở trust-all để làm test xanh; sự an toàn của production phụ thuộc ranh giới tin cậy, topology và hành vi thực đã được đo.