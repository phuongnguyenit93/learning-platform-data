# Kết thúc TLS tại proxy so với kết nối TLS tới ứng dụng

## 1. Mục tiêu bài học

Một người dùng mở `https://shop.example.com` và thấy biểu tượng khóa trong trình duyệt. Điều đó chứng minh kết nối **từ trình duyệt đến điểm TLS mà nó kết nối** được bảo vệ và xác minh theo chính sách TLS của client, nhưng **không tự chứng minh** mọi chặng từ reverse proxy/load balancer tới ứng dụng Spring Boot đều sử dụng TLS.

Trong một hệ thống web hiện đại, có ít nhất ba thiết kế:

1. **TLS termination tại reverse proxy:** browser dùng HTTPS tới proxy, proxy chuyển HTTP thuần trong mạng backend tới Spring Boot.
2. **TLS trực tiếp tới ứng dụng:** browser hoặc client HTTPS kết nối thẳng vào embedded Tomcat/Jetty/Undertow/Reactor Netty có TLS; Spring Boot giữ certificate/private key của endpoint đó.
3. **TLS termination và re-encryption:** browser HTTPS tới proxy, proxy **tạo một kết nối HTTPS mới** đến Spring Boot; mỗi chặng có phiên TLS riêng và cần kiểm tra chứng chỉ riêng.

Bài nằm trong nhóm **TLS và HTTP/2** của Spring Boot web runtime. Sau khi học, bạn có thể:

- Vẽ đúng ranh giới mã hóa và vị trí private key trong từng topology.
- Phân biệt TLS termination, TLS passthrough ở L4 và TLS re-encryption giữa proxy với origin.
- Giải thích vì sao `request.isSecure()`, `request.getScheme()` và redirect URL có thể báo `http` dù browser đang dùng HTTPS.
- Cấu hình `server.forward-headers-strategy` và hiểu rủi ro spoofing `Forwarded` / `X-Forwarded-*`.
- Cấu hình HTTPS trực tiếp trong Spring Boot bằng `server.ssl.*` hoặc SSL bundle, kiểm tra certificate và ALPN.
- Viết và chạy một lab Spring Boot 3.3.5/Java 17 với NGINX proxy, keytool, OpenSSL và curl.
- Xác định HTTP/2 đang chạy ở **chặng nào**; không đánh đồng HTTP/2 với việc tất cả các chặng đều dùng TLS.
- Ra quyết định có căn cứ dựa trên mạng đáng tin cậy, tuân thủ, mTLS, hiệu năng, vận hành chứng chỉ và yêu cầu bảo mật.

**Phạm vi chính:** ứng dụng Spring Boot 3.3.x, Java 17+, Spring MVC với embedded Tomcat. Các nguyên tắc TLS và forwarded headers cũng dùng cho WebFlux/Reactor Netty, nhưng API request và adapter cấu hình khác.

## 2. Những thuật ngữ không được đánh đồng

**TLS** (Transport Layer Security) mã hóa và xác thực một kết nối mạng giữa hai TLS peers. Trong HTTPS, HTTP message được truyền bên trong kết nối TLS. TLS peer có thể là trình duyệt–proxy, hoặc proxy–ứng dụng; TLS không nhất thiết bao phủ một luồng request từ đầu đến cuối nếu nó bị terminate rồi tạo kết nối mới.

**TLS termination:** nơi giải mã kết nối TLS đầu vào. Reverse proxy có certificate và private key thích hợp để trình duyệt xác minh nó. Sau khi decrypt, proxy đọc được request HTTP và có thể thực hiện routing, cache, WAF, rate limiting hoặc sửa header.

**Upstream / origin:** ứng dụng hoặc server ở phía sau proxy. Với Spring Boot, đó thường là embedded Tomcat ở port 8080 hoặc 8443.

**Re-encryption:** proxy bắt đầu một kết nối TLS **độc lập** đến upstream sau khi đã kết thúc kết nối TLS của client. Đây không phải một đường hầm TLS duy nhất chạy xuyên proxy: proxy vẫn đọc được request giữa hai phiên TLS.

**TLS passthrough:** proxy/load balancer lớp 4 chỉ chuyển dòng TCP/TLS byte tới ứng dụng, thông thường không giải mã payload. Certificate và private key endpoint do ứng dụng phía sau giữ. L4 proxy có thể dựa vào SNI trong ClientHello để quyết định backend nếu hỗ trợ, nhưng không thể thực hiện routing dựa trên HTTP URL/path đã mã hóa nếu không terminate TLS.

**HTTP/2:** phiên bản giao thức HTTP với multiplexing và framing riêng. Trên public web, HTTP/2 thường hoạt động qua TLS dưới tên `h2` và thương lượng ALPN; trong mạng backend cũng có thể sử dụng HTTP/2 cleartext `h2c` nếu server/proxy hỗ trợ. Hai chặng có thể có phiên bản HTTP khác nhau.

**Forwarded headers:** metadata mà proxy đáng tin cậy gửi đến backend về scheme/host/port/IP gốc mà client đã dùng, chẳng hạn `X-Forwarded-Proto: https`. Header này không tự tạo mã hóa; nó chỉ **mô tả** request ở chặng trước.

**Chứng chỉ TLS:** certificate chứa public key và danh tính endpoint được CA/trust store xác minh. Private key phải được bảo vệ; tên DNS/IP của endpoint cần nằm trong SAN của chứng chỉ để client xác minh đúng hostname.

## 3. Ba sơ đồ chính và ranh giới bảo vệ

### 3.1. Phương án A — HTTPS đến proxy, HTTP đến Spring Boot

~~~text
           TLS được mã hóa                HTTP trong backend
Browser ==================> NGINX/LB --------------------> Spring Boot
  |    HTTPS :443            |        HTTP :8080               |
  |                          |                                 |
  |    kiểm tra edge cert    |  có thể đọc/sửa header/body      |
  |                          |                                 |
  '----- Tin cậy proxy ------'---- phụ thuộc mạng nội bộ -------'
                               ^
                        TLS kết thúc tại đây
~~~

Browser chỉ thiết lập TLS với proxy. Spring Boot có thể chạy:

~~~properties
server.port=8080
server.ssl.enabled=false
~~~

**Ưu điểm:** quản lý chứng chỉ tập trung ở proxy/ingress/load balancer; ứng dụng nhẹ cấu hình TLS hơn; proxy có thể làm WAF, HTTP/2, redirect, cache, rate limiting, chia tải theo host/path.

**Điều kiện an toàn:** chặng proxy→app **không được giả định tự bảo mật**. Nếu đi qua mạng có attacker, shared LAN, peering hoặc các node không đáng tin cậy, nội dung và cookie/auth header có thể bị đọc/sửa. Cần cô lập backend bằng private network, security group/firewall, service mesh hoặc dùng TLS cho chặng này.

**Quan sát dễ sai:** tại Spring Boot, socket vào là HTTP, nên `request.isSecure()` có thể là `false` và `getScheme()` là `http`. Ứng dụng cần hiểu thông tin HTTPS gốc qua forwarded headers **chỉ khi đường truyền tới backend thực sự được kiểm soát**.

### 3.2. Phương án B — HTTPS trực tiếp đến Spring Boot

~~~text
Browser ================================> Spring Boot
         HTTPS :8443                          |
         cert + private key tại ứng dụng       |
                                               |
                   TLS kết thúc tại ứng dụng --'
~~~

Ứng dụng lắng nghe HTTPS và thực hiện handshake, certificate selection, cipher/protocol negotiation. Ví dụ:

~~~properties
server.port=8443
server.ssl.enabled=true
server.ssl.key-store=file:/etc/app/tls/app.p12
server.ssl.key-store-type=PKCS12
server.ssl.key-store-password=CHANGE_WITH_SECRET
server.ssl.key-alias=app
~~~

Đây là ví dụ **cấu hình kiến trúc**, không phải lệnh dùng nguyên password trong production. Kho khóa phải tồn tại, private key và certificate phải khớp, password lấy từ secret manager/environment injection. Trình duyệt kết nối trực tiếp và xác minh certificate của app.

**Ưu điểm:** bảo vệ kết nối đến tận server app; có thể dùng mTLS tại app; ít phụ thuộc proxy cho tính chính xác của `scheme`.

**Đánh đổi:** mỗi instance cần quản lý certificate, rotation, DNS/SAN, trust, cipher/protocol, observability; khi nhiều replica, yêu cầu triển khai key material thống nhất hoặc giải pháp cấp phát phù hợp. Không có reverse proxy cũng đồng nghĩa những chức năng do proxy đảm nhiệm cần triển khai ở nơi khác nếu vẫn cần.

### 3.3. Phương án C — Terminate ở proxy rồi TLS tới Spring Boot

~~~text
Browser ================ HTTPS ================> NGINX/LB
                                                     |
                                   proxy đọc HTTP và tạo kết nối mới
                                                     |
Proxy ================= HTTPS/mTLS =================> Spring Boot
           backend certificate được proxy kiểm tra
~~~

Chặng 1 và chặng 2 đều được mã hóa, nhưng là **hai TLS sessions riêng** với hai quyết định về trust và certificate. Proxy thấy HTTP request ở giữa hai chặng nên vẫn làm routing, logging, WAF hoặc sửa header.

Cấu hình NGINX phía upstream thường dùng:

~~~nginx
proxy_pass https://127.0.0.1:8443;
proxy_ssl_server_name on;
proxy_ssl_name localhost;
proxy_ssl_trusted_certificate /tmp/tls-lab/app.crt;
proxy_ssl_verify on;
~~~

Trong lab này, upstream certificate có SAN `localhost`, và NGINX kết nối đến IP `127.0.0.1` nhưng xác minh tên `localhost` theo `proxy_ssl_name`. **Không để `proxy_ssl_verify off` trong production**: HTTPS đến backend mà không xác minh đúng certificate/hostname sẽ thiếu lớp xác thực peer, dễ rủi ro MITM trong những môi trường không hoàn toàn tin cậy.

**Ưu điểm:** HTTPS ở edge và mã hóa/trust ở backend; có thể kết hợp với mTLS và kiểm soát danh tính workload. **Đánh đổi:** hai TLS handshakes (dù có keep-alive/session reuse), hai bộ config certificate/CA, CPU và thời gian xử lý TLS tăng. Cần thiết kế rotation và monitoring cho cả hai chặng.

## 4. Bảng so sánh để chọn topology

| Tiêu chí | TLS tại proxy + HTTP backend | TLS trực tiếp tại app | TLS tại proxy + TLS backend |
| --- | --- | --- | --- |
| Browser HTTPS | Có | Có | Có |
| Kết nối proxy→app | HTTP thuần | Không có proxy L7 trong phương án trực tiếp | HTTPS |
| Ứng dụng cần private key TLS | Không | Có | Có |
| Proxy thấy HTTP body | Có | Không có proxy L7 | Có |
| Backend traffic được mã hóa | Không | Đường trực tiếp được mã hóa | Có |
| Proxy có thể route theo path/cookie | Có | Không, trừ khi có lớp khác | Có |
| Có thể xác thực upstream bằng certificate | Không ở chặng HTTP | Client xác thực app | Proxy xác thực app |
| TLS handshake tại app | Không | Có | Có |
| Config forwarded headers | Thường cần cho URL/cookie | Thường không cần | Có thể cần cho host/port công khai |
| HTTP/2 phía browser | Proxy quyết định | App quyết định | Proxy quyết định |
| HTTP/2 ở upstream | Có thể độc lập bật/tắt | Không có upstream riêng | Proxy và app phải cùng hỗ trợ |
| Quản lý certificate | Tập trung ở proxy | Phân phối tới app | Hai bên, nhiều certificate/trust policy |

**Không có lựa chọn luôn tốt nhất.** Dùng proxy TLS termination và HTTP nội bộ có thể phù hợp khi mạng backend thật sự được bảo vệ và policy cho phép; tổ chức yêu cầu mã hóa mọi lưu lượng east–west thường dùng re-encryption/mTLS/service mesh; hệ thống nhỏ không cần proxy có thể dùng HTTPS trực tiếp. Kiến trúc thực tế còn phụ thuộc ingress, managed load balancer, Kubernetes, hạ tầng PKI và compliance.

## 5. Vì sao app thấy http dù người dùng truy cập https?

Giả sử NGINX nhận:

~~~http
GET /go HTTP/2
Host: shop.example.com
:scheme: https
~~~

Đây là **minh họa ngữ nghĩa request HTTP/2**: pseudo-headers trong thực tế là `:method`, `:scheme`, `:authority`, `:path`, không phải các dòng HTTP/1.1; đoạn trên không phải raw wire-format copy đầy đủ.

Proxy terminate TLS rồi gọi backend:

~~~http
GET /go HTTP/1.1
Host: shop.example.com
X-Forwarded-Proto: https
X-Forwarded-Host: shop.example.com
X-Forwarded-Port: 443
X-Forwarded-For: 203.0.113.25
~~~

Ở tầng socket, backend nhận HTTP. Nếu không xử lý forwarded metadata, các API request thường dựa trên **chặng proxy→app**, ví dụ `getScheme() = "http"`, `isSecure() = false`, `getServerPort() = 8080` (khi backend nhìn cổng local và header không chỉ định host/port khác).

Hậu quả:

1. **Redirect sai:** server sinh `Location: http://shop.example.com/...` thay vì HTTPS; browser có thể báo mixed scheme hoặc tạo vòng redirect.
2. **Absolute link sai:** URL trong email, JSON HATEOAS hoặc HTML có `http://`/port nội bộ.
3. **Cookie không có Secure:** code dùng `request.isSecure()` để quyết định `Set-Cookie: ...; Secure` có thể bỏ flag dù browser đang ở HTTPS.
4. **IP logging sai:** `request.getRemoteAddr()` chỉ thấy proxy, làm rate limit/audit theo IP kém chính xác.
5. **Xác định URL gốc sai:** base path/host/port bị thay, nhất là proxy mount ứng dụng ở một path prefix.

Các vấn đề trên không được giải quyết bằng cách chỉ bật certificate ở proxy. Backend cần **được cấu hình nhận metadata đúng, có ranh giới tin cậy rõ ràng**.

## 6. Forwarded và X-Forwarded-*: chính xác và an toàn

### 6.1. Các header phổ biến

| Header | Giá trị minh họa | Ý nghĩa |
| --- | --- | --- |
| `Forwarded` (RFC 7239) | `for=203.0.113.25;proto=https;host=shop.example.com` | Metadata chuẩn hóa, có thể biểu diễn nhiều hop |
| `X-Forwarded-Proto` | `https` | Scheme phía client với proxy |
| `X-Forwarded-Host` | `shop.example.com` | Host công khai |
| `X-Forwarded-Port` | `443` | Port công khai |
| `X-Forwarded-For` | `203.0.113.25` | IP client/chuỗi các hop tùy topology |
| `X-Forwarded-Prefix` | `/shop` | Prefix route mà proxy thêm hoặc gỡ |
| `X-Real-IP` | `203.0.113.25` | IP gốc theo quy ước cụ thể của proxy |

RFC 7239 `Forwarded` và nhóm `X-Forwarded-*` có thể cùng tồn tại. Chính sách nên xác định **một đường nguồn tin cậy**, tránh nhận dữ liệu mâu thuẫn từ hai họ header.

### 6.2. server.forward-headers-strategy trong Spring Boot 3.3

~~~properties
# Không dùng forwarded header để thay đổi request view:
server.forward-headers-strategy=none

# Để embedded server tự xử lý khi được hỗ trợ:
server.forward-headers-strategy=native

# Sử dụng cơ chế của Spring Framework:
server.forward-headers-strategy=framework
~~~

- **`none`:** không tự áp các header forwarded vào URL/scheme/request.
- **`native`:** tận dụng server native support; với Tomcat, thường dùng cơ chế remote IP valve. Phù hợp khi proxy cấp `X-Forwarded-For` và `X-Forwarded-Proto` theo quy ước server hỗ trợ.
- **`framework`:** Spring MVC dùng `ForwardedHeaderFilter`, WebFlux dùng `ForwardedHeaderTransformer` khi thích hợp. Có thể hữu ích khi cần xử lý `Forwarded`, prefix hoặc host semantics ngoài khả năng native cụ thể.

Theo tài liệu Spring Boot 3.3, một số platform cloud được nhận dạng có thể mặc định `NATIVE`, còn môi trường khác mặc định `NONE`. **Đặt tường minh** trong triển khai quan trọng để không phụ thuộc môi trường hoặc thay đổi ngầm.

Với Tomcat và TLS terminate tại proxy, tài liệu Spring Boot 3.3 khuyến nghị:

~~~properties
server.tomcat.redirect-context-root=false
~~~

Thiết lập này giúp forwarded scheme được áp dụng trước một số redirect context-root do Tomcat thực hiện.

### 6.3. Ranh giới tin cậy là điều kiện bắt buộc

**Header HTTP client có thể tự tạo.** Một attacker có thể gửi:

~~~http
X-Forwarded-Proto: https
X-Forwarded-For: 127.0.0.1
X-Forwarded-Host: attacker.example
~~~

Nếu app tin vô điều kiện, attacker có thể làm sai scheme, IP, link hoặc logic phụ thuộc host/protocol. Với `framework`, Filter/Transformer đọc header; bản thân chúng **không thể đoán header đến từ proxy hay từ client giả mạo**.

Các biện pháp:

1. **Chỉ cho phép proxy đáng tin gọi backend**: firewall, network policy, security group, listener private/loopback, service identity/mTLS nếu cần. Không public port HTTP backend ra Internet.
2. **Edge proxy phải xóa/ghi đè** các header `Forwarded` và `X-Forwarded-*` từ client bên ngoài. Một chuỗi proxy nhiều tầng cần chính sách rõ ràng về hop được tin.
3. **Đặt cấu hình trusted proxies/remote IP** đúng phiên bản container, và kiểm thử với những IP thật. Đừng đoán rằng `$proxy_add_x_forwarded_for` an toàn khi edge nhận client tự truyền XFF.
4. **Kiểm soát Host:** giới hạn domain/host được chấp nhận ở proxy và ứng dụng; tránh dùng host tùy ý từ request để tạo password-reset link hoặc redirect nhạy cảm.
5. **Không dùng forwarded header thay authentication**: `X-Forwarded-For` không phải bằng chứng danh tính user, và `X-Forwarded-Proto: https` không tạo mã hóa trên backend.

Lệnh test trong local có thể gửi giả header trực tiếp vào `localhost:8080`; điều đó **không chứng minh** Internet user cũng được phép gọi backend trong production. Ranh giới mạng phải được cưỡng chế độc lập.

## 7. Lab nền tảng Spring Boot 3.3.5, Java 17+

Ví dụ sau có thể chạy bằng Maven/Java 17 và không cần database. Hai endpoint giúp quan sát những gì Spring Boot nghĩ về request:

- `GET /info` trả JSON về scheme, secure, host, port, IP và protocol mà app nhìn thấy.
- `GET /go` trả `302 Found` với `Location` tuyệt đối tạo từ request context; dùng để chứng minh scheme/host/port.
- `GET /cookie` đặt cookie demo; minh họa ý nghĩa của `request.isSecure()` trong quá trình phát cookie.

**Quan trọng:** endpoint trả thông tin request và cookie là **công cụ học tập, không nên xuất công khai nguyên trạng trong production**; cần tránh lộ hạ tầng và không dùng quyết định secure cookie phụ thuộc một header không được tin cậy.

### 7.1. Cấu trúc tệp

~~~text
tls-topology-lab/
├── pom.xml
└── src/main/
    ├── java/com/example/tlslab/
    │   ├── TlsTopologyApplication.java
    │   └── RequestProbeController.java
    └── resources/
        └── application.properties
~~~

### 7.2. Maven: pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>tls-topology-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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

`spring-boot-starter-web` gồm Spring MVC, Jackson và embedded Tomcat theo cấu hình mặc định của Boot 3.3.

### 7.3. application.properties: app HTTP nội bộ

**Tệp `src/main/resources/application.properties`:**

~~~properties
# Local lab chỉ bind IPv4 loopback.
server.address=127.0.0.1
server.port=8080
server.ssl.enabled=false

# Chỉ nhận forwarded headers sau khi chạy qua proxy tin cậy.
server.forward-headers-strategy=none
server.tomcat.redirect-context-root=false
~~~

Trong local, binding loopback tránh mở port 8080 ra mọi network interface. Trong production, proxy và app có thể ở các host/container riêng; khi đó bind vào **private interface** thích hợp và firewall chặn nguồn không tin cậy. Đừng copy `127.0.0.1` nguyên vào Kubernetes pods rồi ngạc nhiên khi ingress bên ngoài pod không truy cập được.

### 7.4. Lớp khởi động

**Tệp `src/main/java/com/example/tlslab/TlsTopologyApplication.java`:**

~~~java
package com.example.tlslab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TlsTopologyApplication {
    public static void main(String[] args) {
        SpringApplication.run(TlsTopologyApplication.class, args);
    }
}
~~~

### 7.5. Controller quan sát request

**Tệp `src/main/java/com/example/tlslab/RequestProbeController.java`:**

~~~java
package com.example.tlslab;

import java.net.URI;
import java.util.LinkedHashMap;
import java.util.Map;

import jakarta.servlet.http.HttpServletRequest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseCookie;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.support.ServletUriComponentsBuilder;

@RestController
public class RequestProbeController {

    @GetMapping("/info")
    public Map<String, Object> info(HttpServletRequest request) {
        Map<String, Object> data = new LinkedHashMap<>();
        data.put("scheme", request.getScheme());
        data.put("secure", request.isSecure());
        data.put("serverName", request.getServerName());
        data.put("serverPort", request.getServerPort());
        data.put("remoteAddr", request.getRemoteAddr());
        data.put("protocol", request.getProtocol());
        return data;
    }

    @GetMapping("/go")
    public ResponseEntity<Void> redirect() {
        URI location = ServletUriComponentsBuilder
                .fromCurrentContextPath()
                .path("/info")
                .build()
                .toUri();
        return ResponseEntity.status(HttpStatus.FOUND)
                .location(location)
                .build();
    }

    @GetMapping("/cookie")
    public ResponseEntity<String> cookie(HttpServletRequest request) {
        // Chỉ minh họa request.isSecure(); không dùng chính sách
        // phát cookie động này ở môi trường không có trusted proxy.
        ResponseCookie cookie = ResponseCookie.from("demo", "1")
                .path("/")
                .httpOnly(true)
                .secure(request.isSecure())
                .sameSite("Lax")
                .build();

        return ResponseEntity.ok()
                .header(HttpHeaders.SET_COOKIE, cookie.toString())
                .body("cookie-created");
    }
}
~~~

Giải thích:

- `request.getScheme()` và `request.isSecure()` phản ánh dữ liệu mà tầng server/request wrapper tin tại thời điểm controller đọc.
- `request.getServerName()`, `getServerPort()` được dùng khi tạo absolute URL. Nếu forwarded metadata được xử lý đúng, chúng có thể phản ánh public host/port.
- `request.getRemoteAddr()` thay đổi theo cách proxy/native/framework xử lý IP, không tự động luôn là IP user thực.
- `getProtocol()` thường phản ánh protocol của **chặng proxy→app**. Nó **không bắt buộc** đổi thành HTTP/2 chỉ vì client nói HTTP/2 với NGINX.
- `/go` dựng một redirect absolute để có thể so `Location` trước/sau cấu hình forwarded headers.
- `/cookie` cố tình dùng `secure(request.isSecure())` nhằm thấy hệ quả khi app hiểu sai HTTPS gốc. Với ứng dụng chỉ phục vụ public HTTPS trong production, hãy áp chính sách cookie secure cố định/phù hợp và không dựa vô điều kiện vào metadata client tự khai báo.

### 7.6. Chạy trực tiếp app HTTP

Tại thư mục `tls-topology-lab`, sử dụng JDK 17+ và Maven 3.9+:

~~~bash
mvn spring-boot:run
~~~

Trong terminal khác:

~~~bash
curl -sS http://127.0.0.1:8080/info
curl -i http://127.0.0.1:8080/go
curl -i http://127.0.0.1:8080/cookie
~~~

Với cấu hình hiện tại, nội dung JSON có phần tương đương:

~~~json
{
  "scheme": "http",
  "secure": false,
  "serverName": "127.0.0.1",
  "serverPort": 8080,
  "remoteAddr": "127.0.0.1",
  "protocol": "HTTP/1.1"
}
~~~

Đây là **ví dụ giá trị trong lab**, không phải output cố định ở mọi OS/client. `/go` thường trả `302 Found` với Location dẫn đến `http://127.0.0.1:8080/info`. `/cookie` trả body `cookie-created` với header `Set-Cookie` có `HttpOnly`, `SameSite=Lax` nhưng không có `Secure` vì request chưa phải HTTPS.

Đến đây, chưa có proxy và chưa có TLS; đây là baseline.

## 8. Lab A — NGINX kết thúc TLS rồi proxy HTTP đến app

Cần Linux hoặc môi trường tương thích có NGINX, OpenSSL, Bash, Java 17, Maven và curl. Lab dùng port cao `9443` nên không yêu cầu root để bind port. Thư mục `/tmp/tls-lab` chỉ dùng cho thử nghiệm; không đặt private key thật vào đường dẫn công khai.

### 8.1. Sinh certificate self-signed ở edge

Trong Bash:

~~~bash
mkdir -p /tmp/tls-lab

openssl req -x509 -nodes -newkey rsa:2048 -sha256 \
  -days 7 \
  -keyout /tmp/tls-lab/edge.key \
  -out /tmp/tls-lab/edge.crt \
  -subj "/CN=localhost" \
  -addext "subjectAltName=DNS:localhost,IP:127.0.0.1"

chmod 600 /tmp/tls-lab/edge.key
~~~

Chứng chỉ có SAN `localhost`/`127.0.0.1` để curl có thể xác minh hostname của demo. Đây là **chứng chỉ tự ký, không được browser công khai tin mặc định**. Production phải sử dụng CA được client tin, vòng đời cấp phát/renewal, private-key protection và cấu hình cipher/protocol phù hợp.

### 8.2. File NGINX chạy local

Tạo **`/tmp/tls-lab/nginx.conf`** đúng nội dung dưới đây:

~~~nginx
worker_processes 1;
pid /tmp/tls-lab/nginx.pid;
error_log /tmp/tls-lab/error.log info;

events {
    worker_connections 512;
}

http {
    access_log /tmp/tls-lab/access.log;

    server {
        listen 127.0.0.1:9443 ssl;
        server_name localhost;

        ssl_certificate /tmp/tls-lab/edge.crt;
        ssl_certificate_key /tmp/tls-lab/edge.key;
        ssl_protocols TLSv1.2 TLSv1.3;

        location / {
            proxy_pass http://127.0.0.1:8080;
            proxy_http_version 1.1;

            # Host của request được proxy chuyển tiếp.
            proxy_set_header Host $http_host;

            # Xóa metadata chuẩn do client tự gửi.
            proxy_set_header Forwarded "";

            # Edge proxy tự điền metadata cho backend.
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_set_header X-Forwarded-Host $host;
            proxy_set_header X-Forwarded-Port $server_port;
            proxy_set_header X-Forwarded-For $remote_addr;
            proxy_set_header X-Real-IP $remote_addr;

            # Không tin prefix/SSL header từ client.
            proxy_set_header X-Forwarded-Prefix "";
            proxy_set_header X-Forwarded-Ssl "";
        }
    }
}
~~~

Đây là proxy local **một hop**. `X-Forwarded-For $remote_addr` cố tình ghi đè giá trị cũ; không dùng `$proxy_add_x_forwarded_for` từ Internet edge nếu chưa loại header do client gửi. Nếu có nhiều proxy, cần chain-of-trust và `real_ip`/CIDR riêng, không dùng nguyên công thức local để suy ra client IP ở production.

**Lưu ý:** file trên chỉ cấu hình proxy tối thiểu cho học tập. Production phải có kiểm soát Host/domain, proxy timeouts/limits, health checks, logging không lộ secret, chặn backend access, TLS certificate renewal và những header forwarded khác do ứng dụng/proxy chain dùng. Với browser WebSocket/upgrade, cũng cần xử lý Upgrade/Connection phù hợp; cấu hình này chưa mô phỏng các tính năng đó.

Kiểm tra và chạy NGINX:

~~~bash
nginx -t -c /tmp/tls-lab/nginx.conf
nginx -c /tmp/tls-lab/nginx.conf
~~~

Nếu NGINX đã chạy và file cấu hình đã được khởi động, không khởi động chồng thêm một process cùng port 9443. Khi sửa cấu hình:

~~~bash
nginx -t -c /tmp/tls-lab/nginx.conf
nginx -s reload -c /tmp/tls-lab/nginx.conf
~~~

### 8.3. Khởi động app với native forwarded headers

Dừng instance Spring Boot đang chạy trước đó, rồi chạy trong thư mục dự án:

~~~bash
mvn spring-boot:run \
  -Dspring-boot.run.arguments="--server.forward-headers-strategy=native"
~~~

Nếu Maven/shell không nhận cách truyền tham số trên, có thể build JAR rồi chạy rõ ràng:

~~~bash
mvn clean package
java -jar target/tls-topology-lab-0.0.1-SNAPSHOT.jar \
  --server.forward-headers-strategy=native
~~~

**Chỉ chạy một instance bind port 8080.** Tại đây Spring Boot vẫn nhận HTTP trên port 8080; property `native` không tự bật TLS. Tomcat dựa vào header từ trusted proxy để khôi phục scheme/host/port gốc.

### 8.4. Gọi HTTPS qua NGINX

~~~bash
curl -sS --cacert /tmp/tls-lab/edge.crt \
  https://localhost:9443/info

curl -i --cacert /tmp/tls-lab/edge.crt \
  https://localhost:9443/go

curl -i --cacert /tmp/tls-lab/edge.crt \
  https://localhost:9443/cookie
~~~

Điểm cần quan sát:

- `/info` trong lab có thể trả `"scheme":"https"` và `"secure":true` dù **kết nối NGINX→app thực chất là HTTP**.
- Với forwarded port được xử lý đúng, `/go` trả `Location` bắt đầu bằng `https://localhost:9443/info`, không phải port 8080.
- `/cookie` lúc này có thể có flag `Secure` nhờ request wrapper nhận đúng scheme gốc.
- `getProtocol()` thường vẫn là `HTTP/1.1` vì NGINX dùng `proxy_http_version 1.1` ở chặng upstream, dù browser có thể giao tiếp HTTP/2 với NGINX nếu edge được cấu hình.

Nếu `native` không đủ cho một kiểu header, host, prefix đặc thù, thử `framework` **sau khi đã bảo đảm trust boundary**:

~~~properties
server.forward-headers-strategy=framework
~~~

Không bật đồng thời thủ công `ForwardedHeaderFilter` và auto-config của Boot khi chưa có lý do; cần tránh xử lý forwarded headers hai lần hoặc theo thứ tự sai.

### 8.5. Chẩn đoán redirect loop

Giả sử proxy redirect mọi HTTP request về HTTPS, nhưng ứng dụng không hiểu `X-Forwarded-Proto`, thấy request từ proxy là HTTP và cũng redirect sang HTTPS. Kết quả có thể là vòng lặp hoặc Location sai khi client cứ quay về edge.

**Phương án khắc phục:**

1. Quy định rõ **một lớp** chịu trách nhiệm redirect HTTP→HTTPS (thường edge) để tránh logic trùng.
2. Bảo đảm proxy chuyển scheme/host/port thật và chỉ proxy được phép gửi header này.
3. Đặt `server.forward-headers-strategy` đúng stack/server.
4. Kiểm tra `Location` từng hop bằng `curl -i`; đừng chỉ dùng browser tự follow redirect vì khó thấy nguyên nhân.

Trong lab, `/go` là redirect HTTP 302 chủ động nhằm quan sát URI, không phải chính sách ép HTTPS.

## 9. Lab B — HTTPS trực tiếp ở embedded Spring Boot

Giữ nguyên project và controller, nhưng để app tự nhận TLS ở port `8443`. Vì cấu hình server SSL chỉ bật một connector chính qua properties trong lab, lúc này app **không còn HTTP 8080** trừ khi bạn cấu hình thêm connector bằng Java.

### 9.1. Tạo keystore PKCS12 bằng keytool

Trong Bash, dùng `keytool` của JDK 17:

~~~bash
mkdir -p /tmp/tls-lab

keytool -genkeypair \
  -alias app \
  -keyalg RSA -keysize 2048 \
  -validity 7 \
  -storetype PKCS12 \
  -keystore /tmp/tls-lab/app.p12 \
  -storepass changeit \
  -keypass changeit \
  -dname "CN=localhost, OU=Lab, O=Example, C=VN" \
  -ext "SAN=DNS:localhost,IP:127.0.0.1"

keytool -exportcert -rfc \
  -alias app \
  -keystore /tmp/tls-lab/app.p12 \
  -storepass changeit \
  -file /tmp/tls-lab/app.crt
~~~

`app.p12` chứa private key và certificate phục vụ TLS; `app.crt` là certificate công khai được export để client/proxy trong lab tin tưởng. Password `changeit` **chỉ là giá trị demo**. Production không commit keystore hay password vào Git; dùng secret mounts, secret management và chính sách quyền file.

### 9.2. Chạy Spring Boot HTTPS

Dừng process app HTTP đang chạy. Nếu đã build JAR ở mục 8.3, chạy:

~~~bash
java -jar target/tls-topology-lab-0.0.1-SNAPSHOT.jar \
  --server.port=8443 \
  --server.ssl.enabled=true \
  --server.ssl.key-store=file:/tmp/tls-lab/app.p12 \
  --server.ssl.key-store-type=PKCS12 \
  --server.ssl.key-store-password=changeit \
  --server.ssl.key-alias=app \
  --server.forward-headers-strategy=none \
  --server.http2.enabled=true
~~~

Trong cấu hình trên, `server.address=127.0.0.1` từ file application.properties vẫn giữ nguyên, nên listener chỉ phục vụ local. Để triển khai thực, app có thể bind vào private address hoặc interface hợp lệ, đồng thời enforce firewall/security group.

**Đặc điểm quan trọng:** `server.ssl.key-store` và `server.ssl.key-store-password` cấp key material trực tiếp cho embedded Tomcat. Khi `server.http2.enabled=true` và TLS/configuration phù hợp, Tomcat có thể thương lượng `h2` qua ALPN với client hỗ trợ.

### 9.3. Kiểm tra chứng chỉ và HTTP response

~~~bash
curl -i --cacert /tmp/tls-lab/app.crt \
  https://localhost:8443/info

curl -i --cacert /tmp/tls-lab/app.crt \
  https://localhost:8443/go

curl -i --cacert /tmp/tls-lab/app.crt \
  https://localhost:8443/cookie
~~~

Trong lab, `/info` báo `scheme=https`, `secure=true` mà **không cần forwarded headers**, vì socket app là TLS thật. `/go` thường trỏ tới `https://localhost:8443/info`.

Kiểm tra handshake/certificate:

~~~bash
openssl s_client \
  -connect 127.0.0.1:8443 \
  -servername localhost \
  -alpn h2,http/1.1 \
  -CAfile /tmp/tls-lab/app.crt
~~~

Trong output, quan sát certificate chain/verify result, TLS protocol và `ALPN protocol` được thương lượng. Không cố chép một stdout cố định: ciphers và ALPN phụ thuộc client, JDK, Tomcat, OpenSSL và bản build.

Nếu `curl` hỗ trợ HTTP/2:

~~~bash
curl --http2 -sS -o /dev/null \
  -w 'HTTP version: %{http_version}\n' \
  --cacert /tmp/tls-lab/app.crt \
  https://localhost:8443/info
~~~

Kỳ vọng version `2` khi cả client và app thương lượng HTTP/2 thành công. Nếu client không build kèm HTTP/2, `curl --http2` có thể báo lỗi; đó **không phải** bằng chứng server không hỗ trợ HTTP/2.

**Đừng dùng `curl -k` để “sửa” lỗi certificate trong production.** `-k` chỉ là cách bỏ qua xác minh TLS tạm thời trong lab; dùng `--cacert` với certificate CA/trust anchor phù hợp mới kiểm tra được mối quan hệ trust ở ví dụ này.

### 9.4. SSL bundles thay cho key-store properties

Spring Boot 3.3 hỗ trợ named **SSL bundles**. Có thể thay nhóm `server.ssl.key-store*` bằng:

~~~properties
server.port=8443
spring.ssl.bundle.jks.backend.key.alias=app
spring.ssl.bundle.jks.backend.keystore.location=file:/tmp/tls-lab/app.p12
spring.ssl.bundle.jks.backend.keystore.password=changeit
spring.ssl.bundle.jks.backend.keystore.type=PKCS12
server.ssl.bundle=backend
~~~

Đây là **cấu hình thay thế**, không phải dòng bổ sung đè lên cùng các property discrete `server.ssl.key-store`. Theo tài liệu Boot 3.3, `server.ssl.bundle` **không được kết hợp** với nhóm discrete keystore/PEM options của `server.ssl`.

SSL bundle cũng hỗ trợ trust material/PEM và cơ chế reload khi thành phần consuming hỗ trợ. Việc certificate được cấp mới, đổi private key, reload hoặc đổi CA chain cần có kế hoạch rotation và smoke test, không chỉ dựa vào restart ngẫu nhiên.

## 10. Lab C — NGINX HTTPS tới Spring Boot HTTPS (re-encryption)

Tiếp tục để Spring Boot chạy ở `https://127.0.0.1:8443` như Lab B. Edge NGINX vẫn nhận TLS ở `9443`, nhưng thay upstream HTTP ở Lab A bằng HTTPS.

Trong `/tmp/tls-lab/nginx.conf`, giữ `server`, certificate edge và các header tin cậy của Lab A; thay **toàn bộ khối `location /`** bằng:

~~~nginx
location / {
    # HTTPS tới backend; NGINX tạo TLS session mới.
    proxy_pass https://127.0.0.1:8443;
    proxy_http_version 1.1;

    # Tên upstream để gửi SNI và xác minh SAN.
    proxy_ssl_server_name on;
    proxy_ssl_name localhost;

    # Self-signed demo cert của ứng dụng; trong production
    # phải dùng CA chain tin cậy của upstream.
    proxy_ssl_trusted_certificate /tmp/tls-lab/app.crt;
    proxy_ssl_verify on;
    proxy_ssl_verify_depth 2;

    proxy_set_header Host $http_host;
    proxy_set_header Forwarded "";

    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-Host $host;
    proxy_set_header X-Forwarded-Port $server_port;
    proxy_set_header X-Forwarded-For $remote_addr;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-Prefix "";
    proxy_set_header X-Forwarded-Ssl "";
}
~~~

Nginx kiểm chứng upstream certificate với `proxy_ssl_verify on` và trust anchor `app.crt`. Nếu certificate bị thay mà NGINX chưa tin hoặc tên `localhost` không có trong SAN, kết nối upstream sẽ lỗi — đây là **phản ứng bảo mật mong muốn**, không phải lý do để tắt xác minh.

Kiểm tra/reload:

~~~bash
nginx -t -c /tmp/tls-lab/nginx.conf
nginx -s reload -c /tmp/tls-lab/nginx.conf
~~~

Gọi qua edge:

~~~bash
curl -i --cacert /tmp/tls-lab/edge.crt \
  https://localhost:9443/info

curl -i --cacert /tmp/tls-lab/edge.crt \
  https://localhost:9443/go
~~~

**Giải thích kết quả:**

- Browser/curl chỉ xác minh **edge certificate**. NGINX mới là bên xác minh **backend certificate** bằng `proxy_ssl_verify on`.
- Spring Boot nhìn thấy kết nối TLS ở port 8443 nên `request.isSecure()` thường là `true` dù chưa xử lý forwarded headers.
- Nhưng public port bên ngoài là **9443**, không phải backend 8443. Nếu app tạo absolute URL và chưa khôi phục forwarded host/port, `Location` có thể dùng port 8443 hoặc host nội bộ thay vì 9443.
- Vì vậy **HTTPS upstream không thay thế hoàn toàn việc xử lý forwarded host/port**. Nếu app cần dựng public URI, bật `server.forward-headers-strategy=native` hoặc `framework` với trust boundary phù hợp như Lab A. Sau khi thay property phải restart ứng dụng hoặc cấu hình lại tương ứng.
- Frontend TLS và backend TLS có thể sử dụng chứng chỉ **khác nhau**. Không cần sao chép private key edge sang tất cả backend; tốt hơn là cấp danh tính upstream riêng.

### 10.1. Chọn mTLS nếu cần xác thực proxy ở backend

TLS upstream thông thường cho phép NGINX xác minh server app. **Mutual TLS (mTLS)** yêu cầu app cũng xác minh **client certificate của proxy**, giúp backend chỉ chấp nhận workload có certificate đáng tin, bên cạnh network policy. Đây là bảo vệ kết nối/machine identity, **không thay** xác thực người dùng cuối.

Trên NGINX, các directive liên quan là:

~~~nginx
# Minh họa cơ chế mTLS; cần PKI/certificate phù hợp
# trước khi bật trong hệ thống thực.
proxy_ssl_certificate /etc/nginx/tls/proxy-client.crt;
proxy_ssl_certificate_key /etc/nginx/tls/proxy-client.key;
proxy_ssl_trusted_certificate /etc/nginx/tls/backend-ca.crt;
proxy_ssl_verify on;
~~~

Ở Spring Boot/Tomcat, cần cấu hình keystore phía server, truststore tin CA đã cấp proxy client cert và policy `server.ssl.client-auth` tương ứng, ví dụ `need`; cấp phát chứng chỉ đúng SAN/EKU, xác minh rotate/revoke. Đoạn này là **mã cấu hình minh họa**, không phải lab hoàn chỉnh vì các certificate CA/client chưa được tạo.

## 11. TLS passthrough khác re-encryption như thế nào?

~~~text
A. TLS passthrough L4
Client ===================== TLS =====================> Spring Boot
         [TCP proxy chỉ chuyển bytes, không giải mã HTTP]

B. TLS terminate + re-encrypt L7
Client ========= TLS 1 =========> Proxy
                                   |
                          decrypt + inspect + route
                                   |
Proxy ============ TLS 2 =============================> Spring Boot
~~~

Một L4 proxy passthrough có thể route bằng địa chỉ/port hoặc SNI được nhìn thấy trong ClientHello nếu phù hợp, nhưng không có quyền truy cập URL `/checkout`, header `Cookie` hay JSON body đã mã hóa.

Với re-encryption L7, proxy thấy được các HTTP fields và có thể sửa chúng, sau đó bảo vệ lại đường đi bằng TLS mới. Vì vậy **TLS tới backend không đồng nghĩa với end-to-end encryption mà proxy không thể đọc**.

Nếu yêu cầu pháp lý/bảo mật là “không có thành phần trung gian đọc được dữ liệu nghiệp vụ”, cần thiết kế application-level encryption hoặc TLS passthrough phù hợp, đồng thời đánh đổi khả năng inspection/WAF/path routing tại proxy.

## 12. HTTP/2: thương lượng theo từng chặng

HTTP/2 trên browser và HTTP/2 tại app là **hai câu hỏi khác nhau**.

### 12.1. Khi proxy terminate TLS

~~~text
Browser -- HTTPS + ALPN h2 --> NGINX
NGINX  -- HTTP/1.1 ----------> Spring Boot
~~~

Browser có thể thấy HTTP/2, còn `request.getProtocol()` ở Spring Boot là `HTTP/1.1`. Điều này hoàn toàn bình thường. HTTP/2 multiplexing ở phía client không tự kéo dài thành multiplexing ở upstream.

NGINX phiên bản mới có thể cấu hình:

~~~nginx
server {
    listen 443 ssl;
    http2 on;
    # TLS certificate và proxy_pass cần cấu hình riêng
}
~~~

`http2 on` dùng cho NGINX hỗ trợ cú pháp directive này (ví dụ 1.25.1+); các phiên bản cũ thường dùng `listen 443 ssl http2;`. Đoạn trên là **cấu hình minh họa chưa độc lập**, không thay thế file NGINX lab. NGINX `proxy_pass http://...` thường vẫn nói HTTP/1.x với upstream, không tự biến thành HTTP/2 chỉ vì phía browser dùng h2.

### 12.2. HTTPS trực tiếp tại app

~~~text
Browser -- HTTPS + ALPN h2 --> Spring Boot
~~~

Trong Spring Boot 3.3, bật `server.http2.enabled=true` và TLS phù hợp để embedded server có thể thương lượng `h2`:

~~~properties
server.port=8443
server.http2.enabled=true
server.ssl.enabled=true
~~~

Ba dòng trên **chưa đủ để chạy HTTPS nếu thiếu certificate/private key**; dùng key-store hoặc SSL bundle như Lab B. Tomcat 10.1 trong Boot 3.3 hỗ trợ HTTP/2 với JDK/TLS phù hợp; phiên bản JDK/client và cipher/ALPN vẫn ảnh hưởng kết quả.

### 12.3. HTTP/2 cleartext h2c

Spring Boot 3.3 mô tả hỗ trợ `h2` (qua TLS) và `h2c` (cleartext TCP) với một số embedded servers. `h2c` có thể hữu ích **trong mạng nội bộ** sau TLS termination, nhưng:

- h2c **không mã hóa**; không thay thế TLS khi backend network cần bảo mật.
- Proxy upstream phải hỗ trợ/được cấu hình dùng h2c; không được giả định NGINX `proxy_pass http://...` sẽ dùng h2c.
- Hãy kiểm chứng bằng công cụ/proxy logs ở **chặng upstream**, không chỉ nhìn Chrome DevTools của browser.

### 12.4. Nhiều thuật ngữ HTTP/2 khác

- **ALPN:** TLS extension để client/server thống nhất protocol, ví dụ `h2` hoặc `http/1.1`.
- **SNI:** TLS ClientHello metadata dùng để chọn certificate/backend theo hostname. SNI **không** xác thực HTTP Host header.
- **Multiplexing:** nhiều stream HTTP/2 trên cùng kết nối; không đồng nghĩa mọi request trên backend có cùng thread hoặc connection pool.
- **Connection reuse:** giảm handshake overhead; proxy có thể tái sử dụng kết nối upstream theo policy độc lập với client.

## 13. TLS, redirect HTTPS, HSTS và cookie trong thực tế

### 13.1. HTTP sang HTTPS: nên cưỡng chế ở đâu?

Với edge termination, thường:

~~~text
HTTP :80 -> 301/308 -> https://public-host/...
HTTPS :443 -> NGINX -> backend
~~~

Redirect ở proxy giúp người dùng nâng cấp sang HTTPS **trước** khi vào app. Ở backend, tránh một redirect logic thứ hai không hiểu forwarded scheme; điều đó dễ gây vòng lặp.

Dùng `301`, `302`, `307` hoặc `308` theo semantics method/cache phù hợp; không thay đổi các method quan trọng bằng redirect không chủ đích khi thiết kế API. Trong lab dùng port 9443 thay vì 443, nên không cấu hình HSTS hoặc redirect public 80/443.

### 13.2. HSTS

`Strict-Transport-Security` báo browser chỉ kết nối HTTPS cho hostname trong một thời gian. Nó được browser chấp nhận trên một response HTTPS hợp lệ; không tự mã hóa chặng proxy→backend và không thay thế certificate verification.

Trong production, HSTS nên được cân nhắc ở **edge HTTPS**, với domain, includeSubDomains, preload và khả năng phục hồi phù hợp. Không bật `includeSubDomains` hoặc preload theo kiểu thử nghiệm nếu các subdomain chưa sẵn sàng HTTPS.

### 13.3. Secure / HttpOnly / SameSite cookies

- `Secure`: browser chỉ gửi cookie qua kết nối được xem là an toàn theo chính sách trình duyệt; rất quan trọng với session cookie trên public HTTPS.
- `HttpOnly`: hạn chế truy cập cookie qua JavaScript, không thay thế chống XSS/CSRF.
- `SameSite`: hạn chế một số ngữ cảnh cross-site, cần cân nhắc SSO và cross-origin login.
- `Domain`/`Path`: giới hạn phạm vi gửi cookie, không phải hệ thống authorization.

Nếu proxy terminate TLS và backend hiểu `request.isSecure() = false`, code phát cookie dựa vào flag này có thể thiếu `Secure`. Cấu hình forwarded trust đúng **và** chính sách cookie production rõ ràng; không nên dựa duy nhất vào một header do client có thể giả.

### 13.4. Spring Security và OAuth/OIDC callback

OAuth/OIDC login thường có redirect URI cần khớp host/scheme/port public đã đăng ký. Nếu app tạo `http://internal:8080/login/oauth2/code/...`, provider có thể từ chối callback hoặc người dùng bị redirect sai.

Kiểm tra forwarded headers, reverse-proxy host/path rewriting, cookie scope và `Location`. Đừng nới lỏng OAuth redirect URI validation để che lỗi cấu hình proxy.

## 14. Certificate validation, SNI, CA và xoay vòng khóa

### 14.1. Trình duyệt và proxy xác minh các peer khác nhau

Trong re-encryption:

~~~text
Browser ---- verify edge cert: shop.example.com ----> NGINX
NGINX  ---- verify app cert: backend.internal ------> Spring Boot
~~~

Mỗi verify cần:

- Certificate hợp lệ theo thời gian và chính sách trust anchor/CA.
- SAN chứa đúng DNS name/IP mà peer dùng để xác minh.
- Public/private key khớp; chain đầy đủ; server hỗ trợ TLS protocol/cipher phù hợp.
- Thiết kế revocation/rotation theo chính sách hạ tầng.

**Không dùng certificate public của proxy làm bằng chứng rằng app TLS upstream được xác minh.** Cũng không nhầm `proxy_ssl_server_name on` (gửi SNI) với `proxy_ssl_verify on` (xác minh chain/host). Hai mục đích khác nhau và cùng quan trọng.

### 14.2. Công khai port/backend certificate

Nếu backend cần HTTPS chỉ để bảo vệ chặng nội bộ, thường cấp certificate nội bộ qua private PKI/service mesh hơn là public DNS certificate. Cần đảm bảo reverse proxy tin CA nội bộ, kiểm tra SAN, và backend chỉ nhận kết nối được cho phép.

### 14.3. Rotation và private key

Khi key/cert hết hạn hoặc rotate:

- Edge phải reload/restart TLS listener hoặc dùng cơ chế hot reload của proxy.
- App có thể reload theo khả năng SSL bundle và embedded server; tính năng thực tế phụ thuộc version/consumer.
- Kiểm tra certificate mới qua từng hop sau rotate, không chỉ xem file trên đĩa đã đổi.
- Đặt cảnh báo trước ngày hết hạn, theo dõi handshake error, `unknown_ca`, hostname mismatch và lỗi mTLS.
- Secret/password/key file không được in ra log, commit source hay đặt trong static assets.

Trong Boot 3.3 có thể cấu hình SSL bundles và tính năng reload ở những consumer hỗ trợ (ví dụ Tomcat/Netty). Đừng giả định mọi thay đổi truststore hoặc mọi embedded server đều hot reload theo cùng cơ chế.

## 15. Hiệu năng: proxy TLS termination có luôn nhanh hơn không?

TLS offload tại proxy có thể giảm CPU/crypto work của app và tập trung certificate management. Nhưng chặng backend HTTP/HTTPS, connection reuse, TLS 1.3, keep-alive, số cores và hạ tầng load balancer đều ảnh hưởng.

| Tín hiệu | TLS tại proxy | TLS trực tiếp / re-encryption |
| --- | --- | --- |
| CPU dùng cho TLS | Tập trung ở proxy | Ở app, hoặc cả proxy và app |
| Certificate management | Ít nơi cấp phát key hơn | Nhiều identity/cert, nhưng có thể tự động hóa |
| Thời gian handshake | Ở edge | Ở edge và/hoặc upstream |
| Network hop | Có thêm proxy | Direct ít hop; re-encryption có proxy và TLS backend |
| Khả năng inspection/WAF | Dễ ở proxy | Direct cần thành phần khác; re-encryption vẫn inspect được |
| Bảo mật đường backend | Phụ thuộc mạng/cơ chế khác | TLS bảo vệ nếu verify cấu hình đúng |

**Không tự kết luận** rằng re-encryption làm request “chậm gấp đôi”: có keep-alive, session resumption, TLS offload và proxy pooling. Đồng thời cũng không bỏ qua overhead thực tế. Nên đo RPS, p95/p99, handshake rate, CPU, TLS error, upstream connect/response time và connection reuse trong workload đại diện.

Lưu ý: HTTP/2 giữa browser và proxy có thể cải thiện multiplexing, nhưng nếu proxy mở quá nhiều HTTP/1.1 connections tới backend, app vẫn có giới hạn worker/thread/connection pool riêng. HTTP/2 không giải quyết nút thắt cơ sở dữ liệu.

## 16. Reverse proxy nhiều tầng và Kubernetes/Ingress

Topology thực tế có thể là:

~~~text
Browser -> CDN TLS -> Cloud LB TLS/HTTP -> Ingress -> Service -> Pod
~~~

Đừng nói đơn giản “TLS terminate tại proxy” mà không ghi **proxy nào** và mọi hop phía sau. Đặt ra các câu hỏi:

1. TLS đầu tiên terminate tại CDN hay cloud LB?
2. Từ CDN tới LB có TLS/certificate validation không?
3. Từ LB tới ingress và từ ingress tới pod là HTTP, HTTPS hay mTLS service mesh?
4. Node/pod/backend port có thể được gọi trực tiếp từ nguồn không đáng tin cậy không?
5. Hop nào tạo/ghi đè `Forwarded` và `X-Forwarded-*`? Chuỗi XFF có được parse theo danh sách trusted proxies không?
6. Host/SNI/public URL có nhất quán khi chuyển qua nhiều lớp không?
7. HTTP/2 tồn tại trên hop nào? Có h2c ở nội bộ không?
8. Certificate/truststore của mọi hop do ai rotate và monitor?

**Ingress TLS secret** cho `example.com` thường chỉ chứng minh ingress có key/cert cho browser→ingress. Backend Service→Pod có thể vẫn là HTTP. Nếu chính sách yêu cầu mã hóa tới pod, cấu hình upstream HTTPS, service mesh mTLS hoặc TLS passthrough phù hợp, không chỉ bật `tls:` ở manifest ingress.

**Lưu ý trust chain:** một ingress đứng sau cloud LB có thể nhận `X-Forwarded-For` do LB tạo. Khi đó ingress phải tin đúng CIDR/IP của LB để khôi phục client IP, không coi header từ mọi Internet client là dữ liệu xác thực.

## 17. Lỗi thường gặp và hướng kiểm tra

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Browser HTTPS nhưng app `getScheme()==http` | TLS terminate tại proxy, forwarded metadata chưa được xử lý | Kiểm tra `X-Forwarded-Proto`, `server.forward-headers-strategy` và trusted proxy |
| `Location` trả `http://...:8080` | App dựng URL theo backend socket | Dùng `/go`, sửa forwarded host/port/proto, kiểm tra context path |
| Cookie phiên thiếu `Secure` | App thấy HTTP hoặc cấu hình cookie chưa đúng | Xem `Set-Cookie` tại client và request scheme tại app |
| Redirect loop HTTP↔HTTPS | Hai tầng cùng redirect nhưng backend không hiểu scheme public | Dùng `curl -i`, xem từng `Location` và redirect policy |
| Backend app tự bật TLS nhưng NGINX `proxy_pass http://` | Sai protocol giữa proxy và upstream | Chuyển đúng `https://` và verify upstream |
| NGINX trả 502 sau bật upstream HTTPS | Certificate mismatch, trust CA, SNI, port hoặc service không chạy | Xem NGINX error log, `openssl s_client`, app listener |
| Re-encryption dùng `proxy_ssl_verify off` | Upstream chưa được xác thực an toàn | Cấp cert đúng SAN/CA, bật verification |
| Browser nói HTTP/2, app nói HTTP/1.1 | Hai hop dùng protocol khác nhau | Kiểm tra ALPN edge và `proxy_http_version` backend |
| IP ghi log toàn bộ là proxy | Không xử lý trusted XFF hoặc proxy chưa gửi chính xác | Kiểm tra `remoteAddr`, XFF chain và proxy CIDR |
| IP ghi log giả 127.0.0.1 từ client ngoài | Tin header do client tự khai báo | Strip/overwrite forwarded headers, chặn direct access |
| App HTTPS trực tiếp nhận lỗi trust | Self-signed/expired/hostname mismatch/chain thiếu | Kiểm tra SAN, CA, SNI, notBefore/notAfter |
| KeyStore có nhưng Spring không khởi động | Sai password, alias, type hoặc đường dẫn | Kiểm tra keytool list, server.ssl config, log nguyên nhân |
| Frontend h2 nhưng upstream h2c không chạy | Proxy không hỗ trợ hoặc chưa bật h2c | Thử protocol trên từng hop, không suy từ browser |
| HSTS gây site không vào HTTP | Browser giữ policy HTTPS từ lần trước | Kiểm tra chính sách HSTS, host/subdomain, đổi thử trong lab |
| OAuth callback redirect sai host | Thiếu forwarded scheme/host/prefix | Kiểm tra redirect URI, proxy headers và application config |
| TLS đã bật ở ingress nhưng nội bộ vẫn HTTP | TLS chỉ terminate tại ingress | Kiểm tra ingress upstream protocol/service mesh và network traffic |

### 17.1. Quy trình debug có hệ thống

1. **Vẽ từng hop:** client → CDN/LB → ingress/reverse proxy → Spring Boot. Ghi rõ port, HTTP/HTTPS, TLS peer và certificate của từng hop.
2. **Xem chặng client:** `curl -v` hoặc `openssl s_client` để xem certificate, protocol, ALPN, verify result. Không dùng `-k` khi muốn kiểm tra trust thực.
3. **Xem chặng proxy→app:** NGINX `proxy_pass http://` hay `https://`? Có `proxy_ssl_verify on` và CA/SNI đúng không?
4. **Xem headers:** `Host`, `Forwarded`, `X-Forwarded-Proto/Host/Port/For` từ hop được tin. Xác nhận edge đã strip giá trị giả.
5. **Xem Spring Boot:** `server.forward-headers-strategy`, `server.ssl.*`, `server.http2.enabled` và server thực sự dùng.
6. **Test redirect/cookie:** gọi `/go` và `/cookie`, kiểm tra `Location`, `Set-Cookie`.
7. **Test security:** thử direct backend access có bị chặn từ nguồn không tin cậy không; tránh dùng test làm lộ service.
8. **Test vận hành:** rotate certificate trong staging, giảm CA trust/đổi SAN có kiểm soát, xác nhận alert và rollback.

## 18. Những sai lầm tư duy quan trọng

1. **“Browser thấy khóa HTTPS thì backend cũng HTTPS.”** Không đúng nếu TLS terminate ở proxy rồi chuyển HTTP.
2. **“X-Forwarded-Proto=https nghĩa là request đến app được mã hóa.”** Không. Nó chỉ khai báo scheme ở hop trước; client có thể giả header nếu trust boundary sai.
3. **“Có TLS giữa proxy và app là end-to-end không ai trung gian đọc được.”** Với re-encryption, proxy vẫn decrypt request giữa hai TLS sessions.
4. **“Bật server.http2.enabled=true nghĩa là NGINX sẽ nói h2 upstream.”** Không. Protocol được chọn theo từng hop và khả năng proxy.
5. **“Chỉ cần proxy_pass https:// là backend an toàn.”** Không nếu upstream certificate verification bị tắt hoặc danh tính sai.
6. **“Framework forwarded headers an toàn khi app public.”** Không nếu attacker được gửi header trực tiếp tới app hoặc edge không strip.
7. **“HTTP/2 là cơ chế mã hóa.”** HTTP/2 là phiên bản HTTP; TLS là lớp bảo vệ transport. `h2c` là HTTP/2 cleartext.
8. **“HSTS giúp bảo vệ chặng internal.”** HSTS điều khiển hành vi browser đối với origin public, không mã hóa proxy→app.
9. **“Có mTLS giữa proxy và app thì người dùng đã được đăng nhập.”** mTLS xác thực peer workload/connection; end-user identity là lớp khác.
10. **“Không cần test certificate sau rotation.”** Truststore/chain/SAN/SNI có thể làm proxy trả 502 dù certificate mới đã được chép vào đúng folder.

## 19. Bài tập tự kiểm tra

**Câu 1.** Browser đến NGINX bằng HTTPS và NGINX gửi HTTP đến Spring Boot. `getScheme()` ở app thường là gì trước khi dùng forwarded headers? Sau khi xử lý đúng `X-Forwarded-Proto`?

**Câu 2.** Vì sao hai request đều thấy `https://shop.example.com` ở browser nhưng đường đi backend có thể khác nhau về bảo mật?

**Câu 3.** Trong re-encryption, ai xác minh certificate của backend: browser hay proxy? Khi `proxy_ssl_verify off`, lớp bảo vệ nào bị thiếu?

**Câu 4.** Nếu app Spring Boot tự phục vụ HTTPS trên 8443, các property nào liên quan đến keystore và port? Có tự giữ một HTTP 8080 connector khi chỉ cấu hình server.ssl trong application.properties không?

**Câu 5.** Người dùng có HTTP/2 với edge, nhưng controller `getProtocol()` trả HTTP/1.1. Có phải lỗi không?

**Câu 6.** Tại sao gửi `X-Forwarded-For: 127.0.0.1` từ client ngoài không được phép làm ứng dụng nghĩ đó là IP thật?

**Câu 7.** Một tổ chức yêu cầu mã hóa traffic từ ingress đến pod. Chỉ khai báo certificate tại ingress đã đủ chưa? Có hai hướng triển khai nào?

**Câu 8.** So sánh TLS passthrough với re-encryption về khả năng proxy nhìn HTTP path và body.

**Câu 9.** Vì sao proxy vẫn có thể cần `X-Forwarded-Port`/`X-Forwarded-Host` khi upstream đã dùng HTTPS?

**Câu 10.** Một NGINX upstream HTTPS trả 502 chỉ sau khi thay certificate của app. Nên kiểm tra theo thứ tự những gì thay vì tắt `proxy_ssl_verify`?

**Đáp án gợi ý:**

1. Trước khi xử lý thường là `http`; sau khi tin đúng forwarded scheme có thể là `https`. Điều đó vẫn không đổi HTTP backend thành TLS.
2. Vì TLS chỉ bảo vệ từng phiên giữa peers; chặng từ proxy đến app có thể là HTTP hoặc HTTPS, tùy thiết kế.
3. NGINX/proxy là TLS client tới backend và phải verify backend cert. Tắt verify làm mất xác minh đúng peer/CA/hostname.
4. `server.port`, `server.ssl.enabled`, `server.ssl.key-store`, `server.ssl.key-store-type`, `server.ssl.key-store-password`, `server.ssl.key-alias` hoặc bundle. Boot properties không tự mở thêm HTTP connector khi chính connector đã chuyển sang HTTPS.
5. Không. Chặng client→proxy dùng HTTP/2, chặng proxy→app dùng HTTP/1.1.
6. Vì header là text HTTP có thể bị client giả; chỉ proxy ở trust boundary được tạo/ghi đè và app chỉ nhận từ proxy đáng tin.
7. Chưa đủ. Cấu hình upstream HTTPS với certificate verification hoặc dùng service mesh mTLS; TLS passthrough cũng có thể phù hợp khi điều kiện routing cho phép.
8. Passthrough chỉ chuyển TLS bytes, proxy L4 không đọc HTTP body/path. Re-encryption terminate rồi tạo TLS session mới, proxy vẫn xem/chỉnh HTTP.
9. TLS đảm bảo scheme upstream, nhưng public host/port có thể khác backend; absolute redirect/link phải phản ánh URL client.
10. Xem app listener/port, CA/truststore, SAN/hostname, SNI, certificate chain/expiry, NGINX error log, TLS handshake; sửa trust/cert đúng thay vì tắt verification.

## 20. Checklist triển khai

- [ ] Vẽ được chính xác các TLS endpoints/hops và vị trí private keys.
- [ ] Xác định nơi terminate TLS, nơi có traffic HTTP thuần, nơi re-encrypt/mTLS.
- [ ] Chặn truy cập backend trực tiếp từ client không tin cậy.
- [ ] Edge kiểm soát và ghi đè đầy đủ `Forwarded`/`X-Forwarded-*` đầu vào.
- [ ] `server.forward-headers-strategy` phù hợp với proxy và web stack.
- [ ] Redirect, link, Host và port công khai đúng trong `Location`.
- [ ] Cookie `Secure`/`HttpOnly`/`SameSite` được kiểm chứng ở client.
- [ ] Certificate và SAN/trust của **từng hop** được xác minh, không bỏ qua bằng `-k`/`proxy_ssl_verify off` khi production.
- [ ] HTTP/2/h2/h2c được kiểm tra **riêng từng hop**.
- [ ] HSTS, TLS protocols, session resumption và certificate rotation có policy rõ.
- [ ] Có test proxy 502, lỗi trust, expired certificate, sai host, app restart và rollback.
- [ ] Theo dõi handshake errors, latency, TLS certificate expiry và redirect loops.

## 21. Tài liệu tham khảo

- Spring Boot 3.3 — Embedded Web Servers: SSL, HTTP/2, proxy forwarded headers, reverse proxy: https://docs.spring.io/spring-boot/3.3/how-to/webserver.html
- Spring Boot 3.3 — SSL bundles và key/trust material: https://docs.spring.io/spring-boot/3.3/reference/features/ssl.html
- Spring Boot 3.3 — Common Application Properties: https://docs.spring.io/spring-boot/3.3/appendix/application-properties/
- Spring Framework 6.2 — Forwarded headers và Security Considerations: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/filters.html
- NGINX — Securing HTTP Traffic to Upstream Servers: https://docs.nginx.com/nginx/admin-guide/security-controls/securing-http-traffic-upstream/
- NGINX — proxy_ssl_verify, proxy_ssl_name, proxy_ssl_server_name: https://nginx.org/en/docs/http/ngx_http_proxy_module.html
- RFC 7239 — Forwarded HTTP Extension: https://www.rfc-editor.org/rfc/rfc7239
- RFC 9110 — HTTP Semantics, scheme và authority: https://www.rfc-editor.org/rfc/rfc9110
- RFC 8446 — The Transport Layer Security (TLS) Protocol Version 1.3: https://www.rfc-editor.org/rfc/rfc8446
- RFC 9113 — HTTP/2: https://www.rfc-editor.org/rfc/rfc9113
