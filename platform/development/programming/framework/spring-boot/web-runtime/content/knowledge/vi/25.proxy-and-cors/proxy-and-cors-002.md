# Forwarded, X-Forwarded-* và server.forward-headers-strategy trong Spring Boot

**Ngữ cảnh:** Spring Boot → web-runtime → Proxy và CORS. Bài học trình bày RFC 7239 `Forwarded`, các header `X-Forwarded-*` và property `server.forward-headers-strategy` để tái tạo request gốc sau reverse proxy; đồng thời phân biệt MVC và WebFlux, phân tích sai lệch scheme/host/port/prefix, redirects, CORS, cookies, client IP và các rủi ro bảo mật.

**Môi trường ví dụ:** Java 17+, Maven, Spring Boot **3.5.16**, Spring MVC/embedded Tomcat. Spring Boot 3.5.16 là bản cuối của dòng 3.5 còn được phát hành OSS (tháng 6/2026). Dùng ví dụ để hiểu cơ chế; với production hãy nâng lên nhánh/bản vá đang được duy trì, chẳng hạn Spring Boot 4.x phù hợp với nền tảng hoặc sử dụng hỗ trợ thương mại. Không để một bản framework đã kết thúc OSS support đứng ngoài chính sách cập nhật bảo mật.

## 1. Bài toán: HTTPS ở proxy, HTTP ở backend

Một trình duyệt yêu cầu:

~~~http
GET /shop/orders HTTP/1.1
Host: app.example.test
~~~

URL hiển thị là `https://app.example.test/shop/orders`. Reverse proxy (Nginx, load balancer, ingress) terminate TLS ở cổng 443 rồi gọi backend Spring Boot bằng `http://10.0.0.20:8080/orders`. Proxy đã đổi ba điều: **scheme**, **host/port** và có thể **path prefix**.

~~~text
Client Browser                  Trusted Reverse Proxy                 Spring Boot
https://app.example.test:443    203.0.113.10:443                      10.0.0.20:8080
GET /shop/orders                        │                              GET /orders
       │                                │                                    │
       ├────── TLS/HTTPS ──────────────►│                                    │
       │                                │ strip external fake headers         │
       │                                │ set verified metadata              │
       │                                ├──── HTTP internal ─────────────────►│
       │                                │                                    │
       │                                │                 Servlet connection: │
       │                                │                 scheme=http        │
       │                                │                 host=10.0.0.20     │
       │                                │                 port=8080          │
       │                                │                                    │
       │                                │  with forwarded processing:        │
       │                                │  scheme=https, host=app...,        │
       │                                │  port=443, prefix=/shop            │
       ◄───────── HTTP response ────────┴────────────────────────────────────┘
~~~

Không có thông tin forwarded đáng tin, server có thể tạo:
- `Location: http://10.0.0.20:8080/login` hoặc link tuyệt đối tới host nội bộ;
- URL CSS/JS sai khi proxy cắt `/shop`, gây 404;
- callback OAuth/OIDC sai hostname, scheme hoặc prefix;
- swagger/OpenAPI `servers`, HATEOAS links, email reset password trỏ nhầm host;
- `request.isSecure()==false` dù browser đã kết nối HTTPS với proxy;
- IP trong logs/rate limiting là IP proxy, không phải IP client.

**Một yêu cầu quan trọng:** metadata forwarded **không chứng minh** request thật sự đến từ browser với scheme/host đã khai báo. Đây chỉ là **header HTTP mà client có thể tự gửi**. Ứng dụng chỉ được dùng nó khi một **trusted edge proxy** đã loại giá trị không tin cậy, xác định lại request gốc và khóa đường mạng trực tiếp tới backend.

## 2. RFC 7239 `Forwarded`: cú pháp và ý nghĩa

Header chuẩn [RFC 7239](https://www.rfc-editor.org/rfc/rfc7239.html) dùng các cặp `name=value`, ngăn bởi `;` trong một hop; nhiều hop/proxy ngăn bởi `,`.

~~~http
Forwarded: for=198.51.100.21;proto=https;host=app.example.test
~~~

| Tham số | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `for` | Node kết nối tới proxy tại một hop, thường biểu diễn IP client | `for=198.51.100.21` |
| `proto` | Scheme mà proxy quan sát, ví dụ HTTP/HTTPS | `proto=https` |
| `host` | Host request mà proxy nhận | `host=app.example.test` |
| `by` | Interface hoặc node của chính proxy, tùy chọn | `by=203.0.113.10` |

Đối với chuỗi proxy:

~~~http
Forwarded: for=198.51.100.21;proto=https;host=app.example.test, for=10.0.0.7;proto=http;by=10.0.0.8
~~~

Thành phần đầu thường do proxy đầu tiên ghi, phần sau do các proxy tiếp theo append. Nhưng **không có nghĩa** phần tử đầu là sự thật: nếu client đã thêm một `Forwarded` giả trước khi tới edge, và edge chỉ append mà không xóa, chuỗi có thể bắt đầu bằng dữ liệu không tin cậy.

IPv6 và giá trị có dấu `:` hoặc dấu ngoặc cần dùng quoted-string theo cú pháp RFC:

~~~http
Forwarded: for="[2001:db8::21]:51000";proto=https;host="app.example.test:443"
~~~

Cũng có thể gặp `for=unknown` hoặc ID bị làm mờ (ví dụ `for=_hidden`). Không tự phân tích mọi trường hợp bằng `String.split(",")` rồi `split(";")`: quoted strings, escaping, IPv6, nhiều header cùng tên và dữ liệu lỗi làm parser ngây thơ dễ sai.

**Cảnh báo từ RFC:** Mọi node trên đường đi, kể cả client, có thể thay đổi thông tin; phải quản trị trusted proxies và truyền dữ liệu an toàn giữa chúng trước khi tin header.

## 3. Họ `X-Forwarded-*`: convention phổ biến

Dù RFC 7239 đã chuẩn hóa `Forwarded`, nhiều CDN và ingress vẫn dùng các header cũ dạng:

~~~http
X-Forwarded-For: 198.51.100.21, 10.0.0.7
X-Forwarded-Proto: https
X-Forwarded-Host: app.example.test
X-Forwarded-Port: 443
X-Forwarded-Prefix: /shop
~~~

| Header | Thông tin | Giới hạn |
| --- | --- | --- |
| **`X-Forwarded-For`** | IP/node ở các hop, thường cách nhau bằng dấu phẩy | Phần tử đầu có thể giả nếu edge không reset; cần trusted proxy policy |
| **`X-Forwarded-Proto`** | Scheme bên phía người dùng: `https` hoặc `http` | Không nói hop backend có TLS hay không |
| **`X-Forwarded-Host`** | Host công khai lúc proxy nhận request | Có thể bị giả để tạo URL độc hại |
| **`X-Forwarded-Port`** | Public port, ví dụ 443/8443 | Không phải port của servlet socket |
| **`X-Forwarded-Prefix`** | Public URL prefix như `/shop` | Cách rewrite/replace phụ thuộc proxy, web stack và framework |
| `X-Forwarded-Ssl` | Convention cũ, thường `on` hoặc `off` | Nên ưu tiên `X-Forwarded-Proto` rõ ràng |
| `X-Real-IP` | Header riêng của một số proxy | Không mặc nhiên được mọi framework coi như XFF |

`X-Forwarded-*` là nhóm de-facto, **không có một chuẩn chung** buộc Nginx, AWS ALB, Envoy, Traefik và các ingress giữ cùng hành vi. Xem tài liệu hạ tầng trước khi chọn property Spring.

### 3.1. Nhiều proxies và `X-Forwarded-For`

~~~text
Client 198.51.100.21
         │
         ▼
Proxy A 10.0.0.7
         │
         ▼
Proxy B 10.0.0.8
         │
         ▼
Spring Boot 10.0.0.20

Một chain do proxy tin cậy có thể tạo:
X-Forwarded-For: 198.51.100.21, 10.0.0.7
Socket peer gần nhất ở backend: 10.0.0.8
~~~

Nếu client gửi sẵn `X-Forwarded-For: 1.2.3.4` trước Proxy A, việc append không kiểm tra có thể tạo `1.2.3.4, 198.51.100.21, 10.0.0.7`. **Đừng lấy `split(",")[0]` làm IP tin cậy để authorization/rate limiting.** IP phải được diễn giải theo chain và CIDR các proxy thực sự tin cậy, bắt đầu từ peer network đã biết.

### 3.2. Cả hai họ header xung đột

~~~http
Forwarded: proto=http;host=evil.example.test
X-Forwarded-Proto: https
X-Forwarded-Host: app.example.test
~~~

Nếu hệ thống chứa hai họ khác nhau, Spring có thể ưu tiên một họ theo version/cấu hình và sinh sai origin. **Proxy ở ranh giới Internet phải xóa cả `Forwarded` lẫn `X-Forwarded-*` do client cung cấp**, rồi chỉ tạo một contract nhất quán tới backend. Với các phiên bản Spring Framework mới có API chọn rõ họ header, nên cấu hình khớp chính xác proxy contract; vẫn không được bỏ bước vệ sinh đầu vào ở edge.

## 4. `server.forward-headers-strategy`: NONE, NATIVE, FRAMEWORK

Spring Boot dùng property:

~~~properties
server.forward-headers-strategy=framework
~~~

Ba giá trị của enum `ServerProperties.ForwardHeadersStrategy`:

| Giá trị | Người xử lý | Phù hợp | Giới hạn quan trọng |
| --- | --- | --- | --- |
| **`NONE`** | Boot **không** xử lý forwarded metadata bằng hỗ trợ tích hợp | Không proxy hoặc tự cấu hình request normalization | App có thể nhìn scheme/host backend; **không** tự xóa headers ở edge |
| **`NATIVE`** | Embedded server, ví dụ Tomcat `RemoteIpValve` | Proxy thường gửi `X-Forwarded-For`/`X-Forwarded-Proto`, container có trusted proxies đúng | Hành vi `Forwarded`/Prefix/Host/Port tùy server và config |
| **`FRAMEWORK`** | Spring MVC `ForwardedHeaderFilter` hoặc WebFlux `ForwardedHeaderTransformer` | Cần tái dựng external scheme/host/port và prefix theo API Spring | **Không xác thực** header tới từ proxy hay kẻ tấn công |

Trong `application.properties` có thể viết `none`, `native`, `framework` (Boot relaxed binding); enum Java dùng chữ hoa.

**Mặc định không phải lúc nào cũng giống nhau:** Spring Boot 3.5 mặc định **`NATIVE` trên supported Cloud Platforms** mà Boot nhận diện, còn môi trường khác thường là **`NONE`**. Không suy ra environment chỉ vì app chạy trên container/Kubernetes. Để dễ audit, hãy đặt giá trị **explicit trong profile deployment** và kiểm chứng request thật.

Không dùng property cũ `server.use-forward-headers=true` của những bài hướng dẫn trước Boot 2.2 để thay cho property hiện tại. Không nhầm `server.forward-headers-strategy` với `server.servlet.context-path`, `spring.webflux.base-path` hay policy CORS.

### 4.1. NONE

~~~properties
server.forward-headers-strategy=none
~~~

Với app lab nghe `http://localhost:8080` và không có filter custom, `request.getScheme()` thông thường là `http`, `getServerName()` là `localhost`, `getServerPort()` là 8080.

`NONE` chỉ nói rằng **Boot không bật cơ chế tích hợp** qua property này. Các thư viện/tự đăng ký filter khác vẫn có thể đọc header. Đừng hiểu rằng sử dụng NONE cho phép public proxy forward trực tiếp các header tự khai báo mà không nguy hiểm.

### 4.2. NATIVE với Tomcat

~~~properties
server.forward-headers-strategy=native
server.tomcat.remoteip.remote-ip-header=x-forwarded-for
server.tomcat.remoteip.protocol-header=x-forwarded-proto

# Hữu ích khi Tomcat sau proxy terminate TLS và redirect context root:
server.tomcat.redirect-context-root=false
~~~

Embedded Tomcat hỗ trợ `RemoteIpValve` để điều chỉnh một số request attributes từ headers và **trusted proxy ranges**. `server.tomcat.remoteip.internal-proxies` là regex cho địa chỉ proxy được tin cậy trong logic Tomcat. Hãy đặt theo mạng thật; không làm rỗng để “trust all” trong production. Một backend có thể truy cập trực tiếp từ Internet mà tin mọi proxy là nguy cơ giả IP/host.

Spring Boot hướng dẫn `server.tomcat.redirect-context-root=false` để `X-Forwarded-Proto` được xử lý trước redirect context-root, giúp tránh trả HTTP redirect sai scheme.

**Không đồng nhất `NATIVE` và `FRAMEWORK`:** chức năng xử lý `X-Forwarded-Prefix` hoặc RFC `Forwarded`, cùng thứ tự normalization và client-IP behavior, thay đổi theo Tomcat/Jetty/Netty/Undertow. Native không có nghĩa “đã hỗ trợ hết mọi header X-Forwarded”.

### 4.3. FRAMEWORK với MVC và WebFlux

~~~properties
server.forward-headers-strategy=framework
~~~

- **Spring MVC/Servlet:** Spring Boot tích hợp `org.springframework.web.filter.ForwardedHeaderFilter`, wrap request/response để `getScheme()`, `getServerName()`, `getServerPort()`, `isSecure()`, URL builders và `sendRedirect()` phản ánh metadata gốc. Filter cũng loại forwarded headers ở request xuống các tầng sau.
- **Spring WebFlux/Reactive:** sử dụng `org.springframework.web.server.adapter.ForwardedHeaderTransformer` để thay đổi `ServerHttpRequest` trước handler resolution, rồi loại forwarded header khỏi request đã biến đổi.

**Không tự thêm `@Bean ForwardedHeaderFilter` nếu property FRAMEWORK đã bật chức năng đó**, trừ khi bạn thật sự quản trị registration/filter ordering riêng và biết cách tránh xử lý hai lần. Trộn container native valve với framework filter không có kiểm soát có thể dẫn đến host/scheme/prefix không nhất quán.

### 4.4. So sánh nhìn thấy

Giả sử backend socket nhận:

~~~http
GET /inspect HTTP/1.1
Host: localhost:8080
X-Forwarded-Proto: https
X-Forwarded-Host: app.example.test
X-Forwarded-Port: 443
~~~

Khi không xử lý header, URL nhận diện có thể là `http://localhost:8080/inspect`. Khi xử lý đúng metadata **từ proxy tin cậy**, các giá trị cho external request thường là:

| Thuộc tính | Không xử lý | Xử lý đúng |
| --- | --- | --- |
| Scheme | `http` | `https` |
| Server name | `localhost` | `app.example.test` |
| Server port | `8080` | `443` |
| `isSecure()` | `false` | `true` |
| Absolute URL | `http://localhost:8080/inspect` | `https://app.example.test/inspect` |

Đây là kết quả mong muốn của **hệ thống đã có trusted proxy contract**, không phải bằng chứng rằng header giả gửi từ máy bất kỳ hợp lệ.

## 5. Ví dụ chạy được: kiểm tra scheme/host/port và redirect với Spring MVC

Tạo project Maven ở thư mục `forwarded-demo`, dùng **hai Java classes**, không cần database. Chạy trên localhost **chỉ cho mục đích học**; không mở cổng app ra Internet khi `FRAMEWORK` tin request headers.

~~~text
forwarded-demo/
├── pom.xml
└── src/main/
    ├── java/com/example/forwarded/
    │   ├── ForwardedDemoApplication.java
    │   └── InspectController.java
    └── resources/application.properties
~~~

### 5.1. `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.16</version>
    <relativePath/>
  </parent>
  <groupId>com.example</groupId>
  <artifactId>forwarded-demo</artifactId>
  <version>0.0.1-SNAPSHOT</version>
  <properties><java.version>17</java.version></properties>
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

### 5.2. `src/main/resources/application.properties`

~~~properties
server.port=8080

# Chỉ cho lab localhost. Không cho client Internet vào trực tiếp app.
server.forward-headers-strategy=framework
~~~

### 5.3. `src/main/java/com/example/forwarded/ForwardedDemoApplication.java`

~~~java
package com.example.forwarded;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ForwardedDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ForwardedDemoApplication.class, args);
    }
}
~~~

### 5.4. `src/main/java/com/example/forwarded/InspectController.java`

~~~java
package com.example.forwarded;

import jakarta.servlet.http.HttpServletRequest;
import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ResponseBody;
import org.springframework.web.servlet.support.ServletUriComponentsBuilder;

@Controller
public class InspectController {

    @GetMapping("/inspect")
    @ResponseBody
    public Map<String, Object> inspect(HttpServletRequest request) {
        Map<String, Object> values = new LinkedHashMap<>();
        values.put("scheme", request.getScheme());
        values.put("secure", request.isSecure());
        values.put("serverName", request.getServerName());
        values.put("serverPort", request.getServerPort());
        values.put("contextPath", request.getContextPath());
        values.put("url", ServletUriComponentsBuilder
                .fromCurrentContextPath()
                .path("/inspect")
                .toUriString());
        return values;
    }

    @GetMapping("/go")
    public String go() {
        return "redirect:/inspect";
    }
}
~~~

`@Controller` với `@ResponseBody` ở riêng `/inspect` giúp tạo JSON. `/go` trả **logical redirect view**, không phải JSON. Nếu thay class bằng `@RestController`, chuỗi `"redirect:/inspect"` thường bị ghi nguyên dạng thành response body, **không redirect**. Các lệnh `mvn` bên dưới lấy dependencies và biên dịch; không thể chỉ chạy `javac InspectController.java` nếu thiếu Spring/Servlet classpath.

### 5.5. Chạy và quan sát response

Từ root project:

~~~bash
java -version
mvn spring-boot:run
~~~

Gọi trực tiếp (không forwarded headers):

~~~bash
curl -sS http://localhost:8080/inspect
~~~

Các trường quan trọng của JSON thông thường:

~~~json
{
  "scheme": "http",
  "secure": false,
  "serverName": "localhost",
  "serverPort": 8080,
  "contextPath": "",
  "url": "http://localhost:8080/inspect"
}
~~~

Giả lập reverse proxy tạo **`Forwarded` RFC 7239**:

~~~bash
curl -sS \
  -H 'Forwarded: for=198.51.100.21;proto=https;host=app.example.test' \
  http://localhost:8080/inspect
~~~

Với filter FRAMEWORK mặc định trong stack mẫu, kết quả nên cho thấy:

~~~json
{
  "scheme": "https",
  "secure": true,
  "serverName": "app.example.test",
  "serverPort": 443,
  "contextPath": "",
  "url": "https://app.example.test/inspect"
}
~~~

Giả lập proxy dùng **`X-Forwarded-*`**:

~~~bash
curl -sS \
  -H 'X-Forwarded-Proto: https' \
  -H 'X-Forwarded-Host: app.example.test' \
  -H 'X-Forwarded-Port: 443' \
  http://localhost:8080/inspect
~~~

Kiểm tra redirect:

~~~bash
curl -i \
  -H 'X-Forwarded-Proto: https' \
  -H 'X-Forwarded-Host: app.example.test' \
  -H 'X-Forwarded-Port: 443' \
  http://localhost:8080/go
~~~

`/go` nên cho **302 Found**; quan sát `Location` trỏ tới URL ngoài `https://app.example.test/inspect` hoặc dạng redirect hợp lệ tương đương do stack/container thực tế tạo. Domain `app.example.test` chỉ là **tên mẫu không có DNS public**; không làm `curl -L` đến đó rồi cho rằng lỗi DNS là lỗi Spring.

**Lưu ý bảo mật:** Ở đây chính `curl` gửi header gốc để thấy filter hoạt động. Trong production, nếu client cũng có thể tự làm vậy đến app thì đó là lỗ hổng trust boundary; chỉ nên nhận metadata do **proxy đã sanitize**.

### 5.6. Thử ba chiến lược

Trong `application.properties`, thay đúng một giá trị, restart app, gửi các lệnh trên:

~~~properties
server.forward-headers-strategy=none
~~~

Kỳ vọng app vẫn thấy origin backend; không tự tái dựng scheme/host qua Boot.

~~~properties
server.forward-headers-strategy=native
~~~

Trên Tomcat, một phần header X-Forwarded có thể được hỗ trợ qua `RemoteIpValve` và trusted peer rules. **Không dùng kết quả localhost để kết luận môi trường public an toàn**, vì loopback thường được xem là internal/trusted proxy.

~~~properties
server.forward-headers-strategy=framework
~~~

Spring filter xử lý forwarded metadata. Nếu cần prefix/redirect phức tạp, hãy kiểm tra thực nghiệm. Không để hai cơ chế native/framework đồng thời chạy trên cùng request khi chưa xác định rõ thứ tự, tránh double rewriting.

## 6. `X-Forwarded-Prefix` và URL rewrite

Giả sử public route là `https://app.example.test/shop/inspect` nhưng proxy **strip** `/shop` trước khi forward tới `http://localhost:8080/inspect`. Khi tạo external links, backend cần biết prefix public; proxy có thể đặt:

~~~http
X-Forwarded-Proto: https
X-Forwarded-Host: app.example.test
X-Forwarded-Port: 443
X-Forwarded-Prefix: /shop
~~~

Spring Framework có cơ chế hỗ trợ `X-Forwarded-Prefix` để URL builders và một số redirect phản ánh prefix ngoài, tùy framework version/stack. Với ví dụ `FRAMEWORK`, thử:

~~~bash
curl -sS \
  -H 'X-Forwarded-Proto: https' \
  -H 'X-Forwarded-Host: app.example.test' \
  -H 'X-Forwarded-Port: 443' \
  -H 'X-Forwarded-Prefix: /shop' \
  http://localhost:8080/inspect
~~~

Kỳ vọng external URL được tái dựng theo dạng `https://app.example.test/shop/inspect` khi behavior của filter và prefix contract phù hợp. Nếu thấy thiếu hoặc đúp `/shop`, kiểm tra **request path backend thật**, servlet context path, reverse proxy rewrite, `ForwardedHeaderFilter`/`ForwardedHeaderTransformer` và version. Không sửa bằng cách luôn nối chuỗi `"/shop"` trong mọi controller.

### 6.1. Ba biến thể prefix

Theo tài liệu Spring Framework, prefix có thể:
1. **Override:** client gọi `/api/{path}`, backend chạy ở `/app1/{path}`, header `X-Forwarded-Prefix: /api` thay `/app1` khi tạo public URL.
2. **Remove:** client gọi `/{path}`, backend nội bộ ở `/app1/{path}`; proxy gửi prefix rỗng để client không phải biết `/app1`.
3. **Prepend:** client gọi `/api/app1/{path}`, backend ở `/app1/{path}`; public prefix trở thành `/api/app1`.

Đó **không phải phép cộng chuỗi đơn giản**. Contract phụ thuộc proxy rewrite và server context path. Ví dụ `server.servlet.context-path=/shop` tạo context path nội bộ thật trong Servlet; `X-Forwarded-Prefix: /shop` mô tả public URL và **không đồng nghĩa** phải bật cả hai. WebFlux có `spring.webflux.base-path` riêng.

## 7. Nginx tại edge: loại header giả, tạo metadata mới

Đây là ví dụ Nginx **trực tiếp nhận Internet**, terminate TLS, rồi proxy vào Spring Boot **chỉ mở tại loopback**. Đường cert/key chỉ là ví dụ, không có dữ liệu bí mật. Khi Nginx ở sau CDN/load balancer khác, cần thiết kế trusted hop khác ở mục 7.2.

~~~nginx
server {
    listen 443 ssl;
    server_name app.example.test;

    ssl_certificate     /etc/nginx/tls/fullchain.pem;
    ssl_certificate_key /etc/nginx/tls/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8080;

        # Chỉ phục vụ public host đã chọn, không phản xạ Host tuỳ ý.
        proxy_set_header Host app.example.test;

        # Loại forwarded metadata do client tự gửi.
        proxy_set_header Forwarded "";
        proxy_set_header X-Forwarded-Ssl "";
        proxy_set_header X-Forwarded-Prefix "";

        # Ghi đè metadata đã được edge quan sát.
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-Host app.example.test;
        proxy_set_header X-Forwarded-Port 443;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
~~~

Điều kiện:
- Backend cổng 8080 **không được public**. Nên bind vào loopback hoặc giới hạn firewall/security group/NetworkPolicy chỉ trusted proxies kết nối.
- Nginx phải có vhost/default-server xử lý Host không hợp lệ (không forward tất cả tên lạ về app). `server_name` đơn lẻ không thay toàn bộ chính sách default vhost.
- Các `proxy_set_header` trên **ghi đè** header X-Forwarded do client tự gắn. `proxy_set_header Forwarded "";` loại họ chuẩn để nó không xung đột với họ X-* tin cậy.
- Khi proxy có TLS termination, backend HTTP không tự có TLS; nếu mạng hop nội bộ nằm ngoài vùng tin cậy, dùng TLS/mTLS nội bộ theo chính sách.
- Nếu muốn public prefix, cần config `location`/`proxy_pass` path rewrite nhất quán và đặt `X-Forwarded-Prefix` phù hợp. Dấu `/` cuối trong `proxy_pass` có thể thay cách Nginx xây upstream URI, nên cần thử thật cả đường dẫn, assets và redirects.
- Tên domain `app.example.test` chỉ dành cho documentation. Thay bằng hostname, certificate và DNS của deployment thực.

### 7.1. `$remote_addr` vs `$proxy_add_x_forwarded_for`

Nginx `$proxy_add_x_forwarded_for` lấy header `X-Forwarded-For` **đã nhận** rồi **append `$remote_addr`**. Nếu client độc hại đã gửi `X-Forwarded-For: 1.2.3.4`, proxy có thể chuyển:

~~~http
X-Forwarded-For: 1.2.3.4, 198.51.100.21
~~~

Nếu backend lấy item đầu làm IP tin cậy, attacker có thể chọn IP tùy ý. Với edge **không có proxy tin cậy phía trước**, dùng `X-Forwarded-For $remote_addr` để ghi đè rõ ràng. Trong một chain đã được chuẩn hóa từ edge, proxy nội bộ mới có thể append theo thiết kế.

### 7.2. Nginx sau CDN/load balancer

Khi CDN/LB ở trước Nginx, `$remote_addr` có thể là **IP CDN**, không phải IP browser. Module Nginx realip hỗ trợ `set_real_ip_from` và `real_ip_header` cho một số CIDR trusted. Chỉ đặt CIDR chính thức của CDN/LB và kiểm tra đúng hop; không dùng `set_real_ip_from 0.0.0.0/0` để trust cả Internet.

Hạ tầng có thể dùng PROXY protocol, kết nối mTLS giữa hops hoặc CDN-provided header riêng. Không tự chọn header mà không xác minh. Sau khi giải quyết real IP, backend có thể nhận client-IP đã được chuẩn hóa, nhưng **IP không phải danh tính user** và không thay authentication/authorization.

## 8. WebFlux: `ForwardedHeaderTransformer`

Trong Spring WebFlux, request đi qua `DispatcherHandler` và reactive APIs chứ không phải Servlet `DispatcherServlet`. Khi dùng `FRAMEWORK`, thành phần chính là `ForwardedHeaderTransformer`.

| Khía cạnh | Spring MVC | Spring WebFlux |
| --- | --- | --- |
| Starter web | `spring-boot-starter-web` | `spring-boot-starter-webflux` |
| Dispatcher | `DispatcherServlet` | `DispatcherHandler` |
| FRAMEWORK handling | `ForwardedHeaderFilter` | `ForwardedHeaderTransformer` |
| Request | `HttpServletRequest` | `ServerHttpRequest` |
| URL origin | Servlet API/`ServletUriComponentsBuilder` | `ServerHttpRequest.getURI()` và reactive URI builders |
| Property chung | `server.forward-headers-strategy=framework` | `server.forward-headers-strategy=framework` |

Đoạn code **chỉ minh họa**, không độc lập (cần project Spring WebFlux với imports/application context):

~~~java
@GetMapping("/reactive/inspect")
Mono<Map<String, String>> inspect(ServerHttpRequest request) {
    URI uri = request.getURI();
    return Mono.just(Map.of(
        "scheme", uri.getScheme(),
        "host", uri.getHost(),
        "path", uri.getPath()
    ));
}
~~~

Khi thêm cả `spring-boot-starter-web` và `spring-boot-starter-webflux`, Boot thông thường ưu tiên MVC/Servlet application type; không kết luận app là WebFlux chỉ vì có `WebClient`, `Mono` hoặc dependency reactive.

### 8.1. removeOnly và chọn họ header

`ForwardedHeaderFilter`/`ForwardedHeaderTransformer` hỗ trợ **removeOnly**, để **loại headers** nhưng **không dùng chúng** điều chỉnh scheme/host/port. Đây là behavior riêng của filter/transformer, **khác** `server.forward-headers-strategy=none` của Boot. Nếu cần chỉ sanitize header trong app, hãy đăng ký đúng bean/filter với `removeOnly=true` và kiểm soát registration/order; không thêm vào app đang dùng Boot auto filter mà không đánh giá double-processing.

Ở các phiên bản Framework có constructor chọn cụ thể `Forwarded` chuẩn hoặc `X-Forwarded-*`, cấu hình chọn họ theo trusted proxy contract. Một số security improvements được đưa vào patch version của Spring Framework 6.2.x và 7.1; luôn kiểm tra API chính xác và áp dụng bản vá mới.

### 8.2. Thứ tự xử lý

MVC filter dùng wrapper cho request/response nên phải được đăng ký **trước** các filter khác cần biết scheme/host, kể cả trong trường hợp redirect xảy ra sớm. Khi tự đăng ký filter, cần chú ý `REQUEST`, `ASYNC` và `ERROR` dispatch types; dựa vào Boot auto-configuration trước khi viết registration thủ công. WebFlux transformer chạy ở giai đoạn reactive request transformation, không phải Servlet filter.

## 9. Redirect, canonical URL và các hậu quả bảo mật

**Redirect `Location`**, URL trong email/reset token, OAuth callback, HATEOAS links và OpenAPI docs có thể dựng từ request hiện tại. Khi Spring tin host từ forwarded header giả, attacker có thể chuyển link sang domain do họ kiểm soát — một dạng **host header poisoning** và có thể dẫn đến open redirect/token leak.

Đối với URL nhạy cảm:
- ưu tiên cấu hình **canonical public base URL** trong application config và allowlist hostname, thay vì tùy ý lấy request Host;
- proxy chỉ chấp nhận các hostname public hợp lệ, strip/override các forwarded headers từ client;
- xác nhận OAuth/OIDC redirect URIs phải khớp danh sách callback đã đăng ký;
- không tạo password-reset URL chứa secret/token từ một host do request không kiểm chứng;
- kiểm tra `Location` trên response thực đi qua proxy, không chỉ response app nội bộ.

`server.forward-headers-strategy=framework` có thể giúp redirect **đúng địa chỉ ngoài** nhưng **không tự tạo ranh giới trust**. Một browser gửi HTTPS đến proxy, backend nhận HTTP có thể vẫn cần `Secure` cookie, HSTS và forwarded scheme đúng. Tuy nhiên giá trị `X-Forwarded-Proto=https` **không mã hóa hop proxy→backend**.

Ví dụ cookie policy cho Servlet session (tùy thiết kế):

~~~properties
server.servlet.session.cookie.secure=true
server.servlet.session.cookie.http-only=true
~~~

`SameSite`, HSTS, reverse proxy policy và các cookie ứng dụng khác cần xem riêng. Không sửa mixed-content bằng CORS: nếu HTML HTTPS tham chiếu resource `http://...`, hãy sửa URL/scheme generation, không phải chỉ mở Cross-Origin policy.

## 10. CORS và forwarded headers có quan hệ như thế nào?

**Origin** của browser gồm `scheme://host:port`; khác bất kỳ phần nào có thể là **cross-origin**.

~~~text
https://app.example.test      là origin A
http://app.example.test       khác A vì scheme
https://api.example.test      khác A vì hostname
https://app.example.test:8443 khác A vì port
~~~

`Origin` do browser gửi (trong CORS flow) **không phải** `Forwarded`, `X-Forwarded-Host` hoặc `X-Forwarded-Proto`. Spring Boot bật forwarded header strategy **không tự cho phép CORS**, cũng không tự trả `Access-Control-Allow-Origin`.

- Nếu frontend và API có cùng public origin qua proxy, browser có thể không cần CORS dù backend có HTTP socket.
- Nếu thực sự cross-origin, phải cấu hình allowed origins, methods, headers, credentials và xử lý `OPTIONS` preflight trong Web MVC/WebFlux/Spring Security/ingress.
- Khi sử dụng credentialed CORS, không phản xạ Origin bất kỳ và không dùng wildcard `*` như một cách “mở cho nhanh”.
- Lỗi CORS có thể bị che bởi redirect HTTP→HTTPS, 401/403 ở `OPTIONS`, lỗi cookie/SameSite, cache hoặc proxy; cần xem browser Network tab.

Một mảnh MVC minh họa (không thuộc project lab ở mục 5):

~~~java
@Configuration
class PublicWebCorsConfig implements WebMvcConfigurer {
    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
                .allowedOrigins("https://app.example.test")
                .allowedMethods("GET", "POST")
                .allowedHeaders("Content-Type", "Authorization");
    }
}
~~~

Mảnh này cần imports và SecurityFilterChain phù hợp nếu app dùng Spring Security. **CORS không phải authorization** và không ngăn client không phải browser truy cập API.

## 11. IP client, rate limiting và access logs

Cần phân biệt **IP socket peer**, **IP được proxy báo là client**, và **IP đã được hệ thống xác thực theo trusted proxy policy**. Một số native implementations như Tomcat `RemoteIpValve` có thể điều chỉnh `getRemoteAddr()`. Nhưng không nên khẳng định mọi `FRAMEWORK` implementation sẽ thay servlet remote address như nhau: `ForwardedHeaderFilter` chủ yếu tác động scheme/host/port và redirect.

**Không dùng** đoạn code này để làm IP allowlist:

~~~java
// PHẢN VÍ DỤ: KHÔNG an toàn trên edge không sanitize XFF.
String ip = request.getHeader("X-Forwarded-For").split(",")[0];
if (ip.equals("10.0.0.99")) {
    // cấp quyền...
}
~~~

Nó có thể tin một IP do client tự nhập. Thay vào đó, cấu hình trusted proxy/IP ranges trong ingress/gateway/container, dùng observed peer khi phù hợp, và áp dụng authorization theo identity (session/JWT/mTLS) cho các quyết định truy cập quan trọng.

Với logging:
- log riêng `observedPeerIp` và `verifiedClientIp` thay vì đặt cả hai vào một field “clientIP” mơ hồ;
- escape/sanitize values từ HTTP headers; giới hạn kích thước và retention;
- cân nhắc privacy, các address nội bộ tiết lộ topology và sự thật rằng IP không luôn là một người dùng duy nhất;
- phát hiện nhiều requests cùng một peer nếu proxy trust configuration đang sai.

## 12. Threat model: các kiểu tấn công do trust forwarding sai

| Rủi ro | Điều kiện | Hậu quả | Giảm thiểu |
| --- | --- | --- | --- |
| Host-header poisoning | Server tin `X-Forwarded-Host` do client tạo | Reset password link/redirect đến domain attacker | Edge override, canonical base URL, host allowlist |
| Fake IP/rate-limit bypass | Code tin phần tử XFF đầu tiên | Bypass giới hạn/IP ACL, logs sai | Trusted proxy chain, edge reset, dùng verified client IP |
| Scheme spoofing | Tin `X-Forwarded-Proto=https` từ untrusted client | `isSecure`, redirect/cookie logic sai | Không public backend, trust boundary |
| Prefix spoofing | Nhận `X-Forwarded-Prefix` chưa sanitize | URL/redirect bất thường, cache key sai | Prefix cố định từ proxy, integration test |
| Header precedence confusion | `Forwarded` và X-* xung đột | Sai origin, logic khác theo version | Reset cả hai rồi dùng một loại |
| Direct backend bypass | Cổng 8080 mở Internet | Bỏ qua proxy rate-limit/auth và tự gửi header | NetworkPolicy/firewall, private listeners |
| Trust-all proxies | Native container tin mọi IP | Bất kỳ client thành “proxy tin cậy” | Internal proxy CIDRs/regex tối thiểu |
| OAuth callback mismatch | Proxy URL và app URL khác | Login loop, token/redirect errors | Kiểm tra scheme/host/port/prefix và registered URI |
| CORS quá rộng | Reflect arbitrary Origin | Browser khác origin đọc dữ liệu theo chính sách sai | Explicit allowedOrigins và credentials rules |

Hãy cập nhật security patches của Boot, Framework, Tomcat/Netty, Nginx/ingress, Spring Security và các components liên quan. Forwarded header normalization là **một lớp** trong thiết kế bảo mật, không thay thế TLS, authN/authZ, CSRF, CORS hay network segmentation.

## 13. Gỡ lỗi trong môi trường proxy

### 13.1. Bảng triệu chứng

| Triệu chứng | Nguyên nhân hay gặp | Hành động |
| --- | --- | --- |
| `Location: http://localhost:8080/...` | Không chuyển metadata scheme/host đến app | Kiểm tra headers tại hop cuối và forward strategy |
| `request.isSecure()==false` dù browser dùng HTTPS | TLS terminate ở proxy, Boot chưa tái dựng scheme | Set/verify trusted `Proto`, FRAMEWORK/NATIVE đúng stack |
| CSS/JS 404 khi ứng dụng ở `/shop` | Prefix rewrite hoặc generated URL sai | Xem `X-Forwarded-Prefix`, context path, static URL |
| Redirect vòng lặp HTTP↔HTTPS | Proxy/app cùng redirect dựa trên scheme khác nhau | Theo dõi Location từng hop |
| `/shop/shop/login` | Prefix bị cộng hai lần | Kiểm tra proxy_pass rewrite/contextPath/forwarded prefix |
| OAuth `redirect_uri_mismatch` | Sinh callback từ internal scheme/host/port | Kiểm tra external absolute URL và allowed redirect URIs |
| `getRemoteAddr()` = IP proxy | Native client-IP policy chưa được áp dụng hoặc chỉ sửa scheme | Xác minh peer, RemoteIpValve, trusted CIDRs |
| User thay XFF là thay được IP trong logs | Không strip incoming header | Edge overwrite + block direct backend |
| Không có CORS dù bật FRAMEWORK | CORS là policy độc lập | Kiểm tra Origin, OPTIONS, Spring Security CORS |
| Trên `NATIVE` xử lý Proto nhưng không xử lý Prefix | Native container có phạm vi khác | Dùng/test FRAMEWORK cho prefix |
| App nhận xung đột Forwarded và X-* | Multiple proxies đặt headers không nhất quán | Quy định một header family, xóa các giá trị còn lại |
| OpenAPI server URL trỏ localhost | Request origin từ internal backend | Forwarded metadata đúng hoặc cấu hình canonical server URL |
| HTTPS ok nhưng cookie bị gửi sai | Secure/SameSite/domain/path chưa đúng | Inspect Set-Cookie và browser behavior |
| Địa chỉ trong redirect là host lạ | Host/forwarded injection hoặc vhost sai | Allowlist host, sanitize at edge, audit |

### 13.2. Thứ tự debug nhanh

1. Vẽ chuỗi hop: browser → CDN → LB → ingress → app; đánh dấu protocol, host/port và prefix ở mỗi hop.
2. Quan sát browser request **public** và response status/`Location`, browser Network tab để bắt mixed-content/CORS/redirect loop.
3. Xem nơi forwarded headers được **tạo lần đầu**, có bị append từ giá trị client tự gửi không.
4. Kiểm tra backend có đường công khai không; khóa network trước khi tin forwarded metadata.
5. Xác nhận Boot app đang chạy **MVC hay WebFlux**, embedded container nào, forward strategy được đặt explicit.
6. Với Tomcat NATIVE, xem `RemoteIpValve`/`internal-proxies`/`protocol-header`/`remote-ip-header`.
7. Với FRAMEWORK, xem filter/transformer registration, ordering, header family và prefix handling trên đúng Framework patch.
8. Gửi test `curl` tới app trong staging để hiểu behavior, rồi **cùng header giả** qua proxy để chứng minh edge đã loại/override.
9. Kiểm tra CORS preflight và cookie flags riêng nếu lỗi xuất hiện trong browser.
10. Tắt hoặc bảo vệ endpoint `/inspect` trước khi đưa production để không lộ metadata hạ tầng.

## 14. Checklist triển khai production

- Chỉ trusted proxies có thể kết nối tới backend. Cổng nội bộ không lộ Internet.
- Edge strip/override cả `Forwarded` lẫn `X-Forwarded-*` không tin cậy; chỉ một chính sách header được công bố rõ.
- Cho `server.forward-headers-strategy` một giá trị explicit theo môi trường; không trộn xử lý native/framework vô ý.
- Nếu dùng NATIVE, cài trusted proxy regex/CIDRs chính xác, không trust-all.
- Nếu có public path prefix, test đường vào, redirects, static assets, links, OpenAPI và context path.
- Test URL sinh ra phải có đúng scheme/host/port kể cả khi TLS terminate trước app.
- Với auth callbacks/password-reset, dùng canonical allowed origin; không tin request host arbitrary.
- Kiểm tra HTTP cookies `Secure`/`HttpOnly`/`SameSite`, HSTS, mixed content và TLS ở các hop.
- CORS đặt theo public origins thực, xử lý preflight và credential policy riêng.
- IP tin cậy dùng cho security/rate limit phải là output của trusted proxy policy, không phải raw XFF string.
- Regression tests bao gồm header spoof, xung đột Forwarded vs X-*, nhiều hop, redirect/prefix, direct backend access và host khác whitelist.
- Cập nhật mọi thành phần proxy và Spring; chú ý bản vá ForwardedHeaderFilter/ForwardedHeaderTransformer trên phiên bản đang dùng.

## 15. Câu hỏi tự kiểm tra

1. Vì sao server có thể thấy `http://localhost:8080` khi browser truy cập `https://app.example.test`?
2. Trong `Forwarded`, các cặp `for`, `proto`, `host`, `by` mô tả gì? Dấu `;` và `,` tách những gì?
3. `X-Forwarded-For: 1.2.3.4, 198.51.100.21` có chứng minh `1.2.3.4` là client thật không?
4. `NONE`, `NATIVE` và `FRAMEWORK` khác nhau ở tầng xử lý nào?
5. MVC dùng `ForwardedHeaderFilter`, WebFlux dùng class gì?
6. Bật `server.forward-headers-strategy=framework` có tự tin cậy được IP proxy không?
7. `X-Forwarded-Prefix: /shop` và `server.servlet.context-path=/shop` có phải luôn cấu hình cùng nhau không?
8. Vì sao dùng `@RestController` trả `"redirect:/login"` không tạo 302 như `@Controller`?
9. `request.isSecure()==true` sau một forwarded header có chứng minh kết nối proxy→backend dùng TLS không?
10. `X-Forwarded-Host` và `Origin` trong CORS có cùng semantics không?
11. Tại sao `$proxy_add_x_forwarded_for` không nên dùng bừa tại edge không sanitize?
12. Điều gì xảy ra nếu cả `Forwarded` và X-* cùng tới backend nhưng khác host?
13. Vì sao reset-password URLs và OAuth callback URLs phải dùng host có kiểm soát?
14. Nếu thêm WebFlux starter vào MVC app, server mặc định chắc chắn chuyển sang WebFlux không?
15. Nếu Nginx ở sau CDN, `$remote_addr` có chắc là browser IP không?
16. Vì sao `server.forward-headers-strategy=none` không đảm bảo mọi library bỏ qua raw header?
17. Làm sao kiểm tra edge proxy đã chống client-header spoofing?
18. Có thể dùng forwarded headers để tự động bật CORS và cho phép credentials cross-origin không?
19. Vì sao `server.tomcat.redirect-context-root=false` hữu ích ở Tomcat sau TLS-terminating proxy?
20. Khi browser load CSS sai path `/shop/shop/css`, bạn sẽ kiểm tra những thành phần nào?

**Đáp án gợi ý:** (1) TLS terminate và proxy rewrite; (2) thông tin node/protocol/host/proxy, `;` các pairs, `,` các hop; (3) không, leftmost có thể bị giả; (4) NONE không xử lý, NATIVE server container, FRAMEWORK Spring Filter/Transformer; (5) `ForwardedHeaderTransformer`; (6) không, phải strip ở edge và giới hạn mạng; (7) không, tùy rewrite; (8) RestController trả response body literal; (9) không; (10) không; (11) có thể giữ XFF giả rồi append; (12) chính sách mơ hồ/sai origin; (13) phòng host-header poisoning; (14) thường không, Boot chọn MVC; (15) có thể là CDN IP; (16) raw header vẫn đi qua request và code khác có thể dùng; (17) gửi malicious headers trên staging qua edge và so backend metadata; (18) không, CORS độc lập; (19) xử lý forwarded proto trước redirect; (20) proxy_pass, context path, X-Forwarded-Prefix, filter, links.

## 16. Tài liệu chính thức

- RFC 7239, **Forwarded HTTP Extension**: https://www.rfc-editor.org/rfc/rfc7239.html
- Spring Boot 3.5, **Running Behind a Front-end Proxy Server**: https://docs.spring.io/spring-boot/3.5/how-to/webserver.html
- Spring Boot 3.5, **ServerProperties.ForwardHeadersStrategy**: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/web/ServerProperties.ForwardHeadersStrategy.html
- Spring Framework 6.2, **MVC Forwarded Headers and ForwardedHeaderFilter**: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/filters.html
- Spring Framework 6.2, **WebFlux ForwardedHeaderTransformer**: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/reactive-spring.html
- Nginx, **proxy_set_header và $proxy_add_x_forwarded_for**: https://nginx.org/en/docs/http/ngx_http_proxy_module.html
- Nginx, **ngx_http_realip_module**: https://nginx.org/en/docs/http/ngx_http_realip_module.html
- Spring Boot, **3.5.16 last OSS release announcement**: https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now/
