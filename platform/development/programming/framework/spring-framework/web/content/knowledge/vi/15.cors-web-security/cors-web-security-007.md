# ForwardedHeaderFilter, header do proxy cung cấp và ranh giới tin cậy trong Spring MVC

> **Phạm vi:** Spring Web MVC (Servlet stack), Java 17+, Spring Boot 3.x/Spring Framework 6.x, triển khai sau Nginx/ingress/load balancer/reverse proxy. Bài học giải thích `Forwarded` và `X-Forwarded-*`, cách Spring khôi phục scheme/host/port/prefix của URL công khai, cấu hình `ForwardedHeaderFilter` và `server.forward-headers-strategy`, cũng như **ranh giới tin cậy giữa client, proxy và ứng dụng**. Header forwarded do HTTP client tự gửi là **dữ liệu không đáng tin**; chỉ được sử dụng sau khi một proxy được kiểm soát đã **xóa và tái tạo** chúng. Bài có ví dụ Spring Boot chạy được, kiểm tra local, ví dụ cấu hình proxy minh họa, chiến lược chỉ loại bỏ header và checklist kiểm thử an toàn.

## 1. Bài toán thực tế: public HTTPS nhưng backend nhìn thấy HTTP

Giả sử người dùng mở:

```text
https://app.example.test/api/orders
```

Một reverse proxy nhận HTTPS, kết thúc TLS rồi gọi ứng dụng Java trong mạng riêng:

```text
Browser
  https://app.example.test:443
       |
       | TLS
       v
Trusted reverse proxy / ingress
       |
       | HTTP nội bộ
       v
Spring Boot / Tomcat
  http://10.10.0.15:8080/api/orders
```

Nếu ứng dụng chỉ đọc metadata của kết nối nội bộ, nó có thể thấy:

| Thuộc tính Servlet | Backend trực tiếp | Người dùng bên ngoài |
| --- | --- | --- |
| `request.getScheme()` | `http` | `https` |
| `request.getServerName()` | `10.10.0.15` hoặc internal hostname | `app.example.test` |
| `request.getServerPort()` | `8080` | `443` |
| `request.isSecure()` | `false` | Kết nối browser → proxy có TLS |
| Context/prefix | Có thể không có | Có thể là `/portal` |

Điều này ảnh hưởng đến link do server sinh, ví dụ:
- Header `Location` của redirect.
- URI tài nguyên được trả trong JSON hoặc HTML.
- URL trong email, canonical URL, OpenAPI server URL hay callback URL nếu code dựa vào request.
- Logic xử lý secure redirects/cookies hoặc các quyết định phụ thuộc scheme/host nếu được triển khai không cẩn thận.

Một ứng dụng cấu hình sai có thể tạo liên kết như `http://10.10.0.15:8080/api/orders/42` thay vì `https://app.example.test/api/orders/42`. Forwarded headers là cơ chế truyền **thông tin về yêu cầu công khai gốc** qua các proxy, không phải giấy chứng nhận danh tính người dùng.

## 2. Header chuẩn Forwarded và các header X-Forwarded-*

### 2.1. Chuẩn RFC 7239: một header tổng hợp

```http
Forwarded: for=192.0.2.10;proto=https;host=app.example.test
```

Ý nghĩa các tham số thường gặp:

- `for`: client hoặc hop trước từ góc nhìn proxy ghi header. Có thể là địa chỉ IP, mã hóa theo cách quy định, hoặc identifier không phải IP; **không tự động xác thực client**.
- `proto`: scheme ban đầu như `https`.
- `host`: hostname (có thể kèm port) ban đầu.
- `by`: proxy interface/địa chỉ được proxy khai báo.

Nhiều proxy có thể tạo một chuỗi `Forwarded` với nhiều phần tử, ví dụ phân tách bằng dấu phẩy. Header chỉ có giá trị để quyết định “client gốc” nếu biết chính xác proxy nào đáng tin, cách mỗi hop thêm/sửa trường và liệu dữ liệu client đã bị xóa từ đầu hay chưa.

### 2.2. Các header X-Forwarded không chuẩn nhưng phổ biến

```http
X-Forwarded-For: 192.0.2.10
X-Forwarded-Proto: https
X-Forwarded-Host: app.example.test
X-Forwarded-Port: 443
X-Forwarded-Prefix: /portal
```

| Header | Mục đích | Nguy cơ khi tin mù |
| --- | --- | --- |
| `Forwarded` | Chuẩn RFC 7239, gồm `for/proto/host/by` | Giả mạo client, scheme, host |
| `X-Forwarded-For` | Một hay nhiều địa chỉ theo các hop | Sai IP audit/rate-limit/quyền nếu client tự thêm |
| `X-Forwarded-Proto` | Scheme public `http/https` | Liên kết HTTP/HTTPS sai, ảnh hưởng security assumptions |
| `X-Forwarded-Host` | Host công khai | Host-header poisoning, email/reset link/redirect tới domain giả |
| `X-Forwarded-Port` | Port công khai | URI sai host/port, sai redirect |
| `X-Forwarded-Prefix` | Tiền tố path công khai khi proxy rewrite route | Link sai path, có thể bị lợi dụng khi prefix do client kiểm soát |
| `X-Forwarded-Ssl` | Chỉ báo TLS trong một số hệ thống | Không phải nguồn xác thực TLS độc lập |

**Không coi `X-Forwarded-For` là identity hoặc authentication.** Nó không chứng minh người dùng là ai; người dùng có thể chia sẻ IP, đi qua NAT/VPN, hoặc cố tình tự gửi một chuỗi có vẻ giống địa chỉ được tin cậy.

### 2.3. Ví dụ nhiều hop

```text
Client (192.0.2.10)
    |
Edge proxy (10.0.0.2)
    |
Internal ingress (10.0.0.3)
    |
Backend (10.0.0.15)
```

Nếu edge đã loại bỏ mọi giá trị không đáng tin, nó có thể đặt `X-Forwarded-For: 192.0.2.10`. Ingress phía sau có thể append địa chỉ edge nếu cả hai thuộc trust chain rõ ràng. Nhưng nếu edge dùng `$proxy_add_x_forwarded_for` trên một header do client tự cung cấp mà không scrub, chuỗi đầu có thể là IP giả.

Không đơn giản dùng:

```java
// ANTI-PATTERN: client có thể tự gửi địa chỉ đứng đầu.
String claimedIp = request.getHeader("X-Forwarded-For")
        .split(",")[0]
        .trim();
```

Nếu phải dùng IP cho security/rate limit, cần **trusted proxy list/CIDR** và một thuật toán/hạ tầng chuẩn hóa chuỗi hops; thường nên dùng native proxy handling hoặc edge policy đã được kiểm soát và kiểm thử kỹ. Đừng tự suy luận trust từ việc header tồn tại.

## 3. Ranh giới tin cậy là vấn đề quan trọng nhất

Một `ForwardedHeaderFilter` **không thể biết** header nào do proxy đáng tin tạo và header nào do client độc hại tự gửi. Đây là lưu ý bảo mật được Spring Framework nêu rõ trong tài liệu.

```text
UNTRUSTED                       TRUSTED
Internet client                   Private deployment zone
    |                                      |
    | GET /api/inspect                    |
    | X-Forwarded-Host: attacker.test      |
    v                                      |
[ Edge proxy: TRUST BOUNDARY ]            |
    |                                      |
    | 1) DELETE client-supplied            |
    |    Forwarded and X-Forwarded-*       |
    | 2) SET authoritative proto/host/port |
    |    and optional prefix/for           |
    | 3) RESTRICT backend network access   |
    v                                      |
[ Spring Boot app: parse sanitized headers ]
    |
[ Generate links using trusted public URI ]
```

**Điều kiện tối thiểu để tin forwarded headers:**

1. Ứng dụng chỉ được truy cập từ proxy/ingress đáng tin qua firewall, network policy hoặc security groups; không công khai cổng backend cho Internet.
2. Proxy **xóa các header `Forwarded` và `X-Forwarded-*` đến từ phía không tin cậy** trước khi thêm giá trị mới, bao gồm cả họ header mà backend hiện **không** dùng.
3. Proxy **tự đặt** scheme, host, port, prefix theo cấu hình/route đã xác thực hoặc theo metadata đáng tin; không giữ lại host tùy tiện client cung cấp nếu host chưa qua allowlist.
4. Các proxy nội bộ phía sau chỉ chấp nhận forwarded chain từ các hop được biết, không tin mọi nguồn trong cùng VPC theo mặc định.
5. Ứng dụng cấu hình nhất quán một cách diễn giải forwarded headers; tránh một lớp tin `Forwarded` còn lớp khác lại ưu tiên `X-Forwarded-Host` do client gửi.
6. Có test cố tình gửi spoofed headers từ bên ngoài để chứng minh proxy loại bỏ chúng.

### 3.1. Vì sao cần loại bỏ cả hai họ header?

Giả sử proxy chỉ ghi đè `X-Forwarded-Proto` nhưng để nguyên:

```http
Forwarded: proto=https;host=attacker.test
X-Forwarded-Proto: https
X-Forwarded-Host: app.example.test
```

Nếu một framework, plugin hoặc filter khác ưu tiên header chuẩn `Forwarded`, request có thể bị xem như đến từ `attacker.test`. Vì vậy nên **scrub cả chuẩn RFC và toàn bộ các trường X-Forwarded liên quan**, rồi phát hành đúng một dạng đáng tin theo hợp đồng giữa proxy và backend.

**Trust boundary nằm ở proxy/mạng**, không nằm ở đoạn code như:

```java
if (request.getHeader("X-Forwarded-Proto") != null) {
    // Không thể tự xác thực đây là proxy.
}
```

### 3.2. Nếu backend có thể truy cập trực tiếp thì sao?

Nếu ứng dụng bật `server.forward-headers-strategy=framework` nhưng cổng `8080` vẫn mở cho client ngoài, kẻ gọi trực tiếp có thể tự gửi:

```http
X-Forwarded-Proto: https
X-Forwarded-Host: attacker.test
```

Filter có thể dùng chúng để dựng request wrapper “như thể request đã đến qua proxy”. Nó **không tự kiểm tra source IP hoặc chữ ký header**. Đây là **misconfiguration** có thể dẫn đến URL poisoning hay sai assumptions. Cách khắc phục đầu tiên là **chặn direct access**, không phải chỉ viết thêm regex ở controller.

## 4. ForwardedHeaderFilter hoạt động thế nào?

`org.springframework.web.filter.ForwardedHeaderFilter` là Servlet Filter của Spring. Khi có forwarded headers và chế độ xử lý được bật, nó tạo `HttpServletRequestWrapper` để cung cấp lại một số thuộc tính của request theo metadata được chuyển tiếp.

Ví dụ các method downstream có thể quan sát kết quả đã được diễn giải:
- `getScheme()`.
- `getServerName()`.
- `getServerPort()`.
- `isSecure()`.
- `getRequestURL()` và URL-building bằng infrastructure của Spring.
- Prefix/context path tùy cấu hình/phiên bản và header được hỗ trợ.

Filter cũng xử lý/ẩn các forwarded headers để tránh những thành phần phía sau lại đọc chúng theo cách khác. Tuy nhiên **việc ẩn khỏi downstream không biến các giá trị đã sử dụng trở thành đáng tin**. An ninh phụ thuộc việc proxy đầu chuỗi đã kiểm soát headers.

### 4.1. Filter ảnh hưởng URL generation ra sao?

Trong MVC:

```java
String publicLink = ServletUriComponentsBuilder
        .fromCurrentContextPath()
        .path("/api/orders/42")
        .toUriString();
```

Đây là **snippet** trong một HTTP request đã đi qua pipeline, cần import `org.springframework.web.servlet.support.ServletUriComponentsBuilder`. Khi Spring dùng thông tin forwarded hợp lệ từ proxy, URI tạo ra có thể là:

```text
https://app.example.test/api/orders/42
```

Nếu không có forwarded metadata và request vào Tomcat trực tiếp:

```text
http://localhost:8080/api/orders/42
```

Các URI trên là ví dụ với **context path rỗng**; nếu có `server.servlet.context-path`, reverse proxy rewrite hay `X-Forwarded-Prefix`, cần kiểm tra kết quả thực theo topology. Không tự cộng hai lần tiền tố.

### 4.2. Response redirect

Filter có thể wrap cả `HttpServletResponse` để điều chỉnh `sendRedirect(...)` theo public scheme/host/port từ request đã chuẩn hóa. `setRelativeRedirects(true)` thay behavior để hỗ trợ relative redirects theo cơ chế `RelativeRedirectFilter`.

**Không cam kết mọi redirect luôn trả absolute URL:** kết quả phụ thuộc cách ứng dụng tạo `Location`, loại redirect, cấu hình filter, container và các response wrappers. Khi test, phải kiểm tra HTTP status và header `Location` thực tế; đặc biệt lưu ý redirects từ Spring Security/OAuth2 hoặc redirect từ container xảy ra trước khi filter chạy.

### 4.3. Thứ tự filter

Vì các filter hoặc handler sau có thể dùng `getScheme()/getServerName()` để tạo link, `ForwardedHeaderFilter` cần chạy **trước** những thành phần cần đọc metadata đã chuẩn hóa. Spring Framework nêu ví dụ nên đứng trước `RequestContextFilter`.

Nếu auto-config của Spring Boot đang tạo filter qua `server.forward-headers-strategy=framework`, **không tự khai báo thêm một ForwardedHeaderFilter thứ hai** trừ khi bạn hiểu rõ registration/filter order. Double processing giữa container/native và Framework có thể làm hành vi khó đoán.

## 5. Spring Boot: NONE, NATIVE, FRAMEWORK

Spring Boot cung cấp property:

```properties
server.forward-headers-strategy=none
```

Ba giá trị:

| Strategy | Ai diễn giải headers? | Khi nào cân nhắc |
| --- | --- | --- |
| `NONE` | Boot không bật forwarded header handling thay ứng dụng | Không có trusted proxy hoặc không muốn dùng headers |
| `NATIVE` | Servlet container xử lý, ví dụ Tomcat RemoteIpValve | Khi container hỗ trợ các headers cần dùng và có cách kiểm soát trusted proxies phù hợp |
| `FRAMEWORK` | Spring Web sử dụng ForwardedHeaderFilter trên Servlet stack | Khi cần tích hợp của Spring như URL/prefix/redirect handling và proxy đã scrub headers |

Theo tài liệu Spring Boot 3.5, trên một số cloud platform được hỗ trợ, mặc định có thể là `NATIVE`; ở môi trường khác mặc định có thể là `NONE`. **Không suy đoán strategy đang chạy**: kiểm tra cấu hình effective, deployment profiles, container và version cụ thể.

### 5.1. Chọn FRAMEWORK

```properties
# Chỉ an toàn sau trusted proxy đã sanitize forwarded headers.
server.forward-headers-strategy=framework
```

Spring Boot dùng Spring Framework forwarded header support trong Servlet app. Dùng khi proxy đã đáp ứng đầy đủ trust boundary và backend không thể bị truy cập trực tiếp từ Internet.

Ưu điểm là builder/Servlet wrapper nhìn thấy scheme/host/port public cho nhiều loại MVC response. Nhược điểm bảo mật là nếu ingress để lọt client-supplied forwarded headers, **ứng dụng có thể tin giá trị giả**.

### 5.2. Chọn NATIVE

```properties
server.forward-headers-strategy=native
```

Với embedded Tomcat, hạ tầng như `RemoteIpValve` có thể hiểu những header phổ biến như `X-Forwarded-For` và `X-Forwarded-Proto` theo cấu hình. Container có các thiết lập tên header và trusted/internal proxies tùy version. Ví dụ cấu hình tên custom:

```properties
server.tomcat.remoteip.remote-ip-header=x-forwarded-for
server.tomcat.remoteip.protocol-header=x-forwarded-proto
```

**Lưu ý:** các property chỉ định tên header, **không phải tự tạo allowlist của proxy đáng tin**. Cần kiểm tra `internal-proxies`/`trusted-proxies` tương ứng và network isolation theo tài liệu container. Không nghĩ `NATIVE` luôn hỗ trợ `X-Forwarded-Prefix` giống FRAMEWORK: khả năng diễn giải prefix/path tùy container và cách ingress rewrite.

### 5.3. Chọn NONE

```properties
server.forward-headers-strategy=none
```

Dùng khi không có trusted proxy hoặc khi ứng dụng cố tình **không dùng** forwarded metadata. Cấu hình NONE không nhất thiết “xóa vật lý các header đầu vào”: code tự gọi `request.getHeader("X-Forwarded-Host")` vẫn có thể thấy header do client gửi nếu chưa có bộ lọc loại bỏ. Nếu cần strip tất cả headers khỏi Servlet request downstream, dùng `ForwardedHeaderFilter` ở chế độ `removeOnly` như mục 6.

### 5.4. Một số vấn đề liên quan Tomcat và TLS termination

Spring Boot có khuyến nghị khi dùng Tomcat với proxy kết thúc TLS:

```properties
server.tomcat.redirect-context-root=false
```

Property này giúp tránh redirect tới context root diễn ra trước khi metadata forwarded proto được áp dụng trong những topology thích hợp. Không nên dùng nó như “cách sửa mọi redirect”. Kiểm tra redirect thực và thứ tự xử lý container/filters.

## 6. Chế độ removeOnly: loại bỏ nhưng KHÔNG tin forwarded headers

Nếu application không cần diễn giải forwarded headers hoặc muốn bảo đảm code downstream không tùy tiện đọc chúng, có thể dùng:

```java
ForwardedHeaderFilter filter = new ForwardedHeaderFilter();
filter.setRemoveOnly(true);
```

Ý nghĩa: filter **che/loại bỏ** các `Forwarded` / `X-Forwarded-*` headers khỏi view downstream, nhưng **không dùng chúng** để ghi đè host/scheme/port. Theo Javadoc Spring đây là một chế độ được hỗ trợ chính thức.

Ví dụ Java config đầy đủ của bean registration (dùng ở **một phương án riêng**, không đồng thời với Boot FRAMEWORK):

```java
package com.example.demo;

import java.util.EnumSet;
import jakarta.servlet.DispatcherType;

import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.Ordered;
import org.springframework.web.filter.ForwardedHeaderFilter;

@Configuration
class ForwardedHeaderRemoveOnlyConfig {

    @Bean
    FilterRegistrationBean<ForwardedHeaderFilter>
    stripForwardedHeaders() {

        ForwardedHeaderFilter filter = new ForwardedHeaderFilter();
        filter.setRemoveOnly(true);

        FilterRegistrationBean<ForwardedHeaderFilter> bean =
                new FilterRegistrationBean<>(filter);
        bean.setOrder(Ordered.HIGHEST_PRECEDENCE + 10);
        bean.setDispatcherTypes(EnumSet.of(
                DispatcherType.REQUEST,
                DispatcherType.ASYNC,
                DispatcherType.ERROR));
        bean.setAsyncSupported(true);
        return bean;
    }
}
```

Khi dùng config này đặt:

```properties
server.forward-headers-strategy=none
```

**Không** dùng cả `server.forward-headers-strategy=framework` và `stripForwardedHeaders()` vì lúc ấy hai thành phần có trách nhiệm xung đột. Nếu `NATIVE` ở container đã dùng header trước khi Servlet Filter chạy, `removeOnly` có thể quá muộn để đảo ngược metadata của container; cần loại bỏ ngay ở proxy hoặc tắt/đổi native handling.

Cũng không nên quảng cáo `removeOnly` như lớp bảo vệ duy nhất trước HTTP request smuggling/host validation. Nó chỉ xử lý một nhóm headers ở tầng Servlet request, không chặn mọi cách sửa Host/TLS metadata.

## 7. Ví dụ runnable Spring Boot 3.x: quan sát public URL

Ví dụ này cố tình dùng **Spring Web** không cần database/security để dễ quan sát headers. Ở chế độ lab, nó cho phép gửi forwarded headers giả **chỉ để chứng minh ảnh hưởng** của FRAMEWORK. **Không cấu hình như vậy trên backend công khai ở production.**

### 7.1. Tạo project

Tại [Spring Initializr](https://start.spring.io/), tạo Maven project với Java 17+, Spring Boot 3.x, dependency **Spring Web**. Dependency POM:

```xml
<dependency>
  <groupId>org.springframework.boot</groupId>
  <artifactId>spring-boot-starter-web</artifactId>
</dependency>
```

Đây là fragment; Initializr cung cấp đầy đủ POM/versions/plugins.

### 7.2. Demo Java hoàn chỉnh

Tạo `src/main/java/com/example/demo/DemoApplication.java`:

```java
package com.example.demo;

import jakarta.servlet.http.HttpServletRequest;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.support.ServletUriComponentsBuilder;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}

record RequestInfo(
        String scheme,
        String host,
        int port,
        boolean secure,
        String contextPath,
        String requestUrl,
        String generatedLink) {
}

@RestController
class InspectController {

    @GetMapping("/api/inspect")
    public RequestInfo inspect(HttpServletRequest request) {

        String generatedLink = ServletUriComponentsBuilder
                .fromCurrentContextPath()
                .path("/api/resource/42")
                .toUriString();

        return new RequestInfo(
                request.getScheme(),
                request.getServerName(),
                request.getServerPort(),
                request.isSecure(),
                request.getContextPath(),
                request.getRequestURL().toString(),
                generatedLink);
    }
}
```

Mọi field của record là thông tin mà controller **thấy sau khi xử lý Servlet filter chain**. Endpoint `/api/resource/42` ở đây chỉ là **link mẫu được tạo**, không phải resource thật đã đăng ký. Ứng dụng không sử dụng forwarded host để thực hiện network call.

### 7.3. application.properties cho lab

Tạo `src/main/resources/application.properties`:

```properties
server.forward-headers-strategy=framework
# Chỉ bind loopback khi kiểm thử trên máy cá nhân:
server.address=127.0.0.1
server.port=8080
```

Trong môi trường này, chỉ process trên máy cá nhân có thể gọi cổng loopback. Production thường yêu cầu network/private-interface policy khác; không sao chép nguyên settings lab.

Chạy bằng:

```bash
# Linux/macOS
./mvnw spring-boot:run

# Windows
mvnw.cmd spring-boot:run
```

### 7.4. Request không có forwarded headers

```bash
curl -sS 'http://127.0.0.1:8080/api/inspect'
```

Các trường quan trọng trong JSON thường tương đương:

```json
{
  "scheme": "http",
  "host": "127.0.0.1",
  "port": 8080,
  "secure": false,
  "contextPath": "",
  "requestUrl": "http://127.0.0.1:8080/api/inspect",
  "generatedLink": "http://127.0.0.1:8080/api/resource/42"
}
```

Chúng phụ thuộc Host thực của request và cấu hình server; đây là đầu ra dự kiến theo lệnh curl dùng IP loopback, không đại diện proxy production.

### 7.5. Mô phỏng một proxy có forwarded headers

```bash
curl -sS 'http://127.0.0.1:8080/api/inspect' \
  -H 'X-Forwarded-Proto: https' \
  -H 'X-Forwarded-Host: app.example.test' \
  -H 'X-Forwarded-Port: 443'
```

Với Spring Framework forwarded header handling được bật, các trường quan trọng có thể trở thành:

```json
{
  "scheme": "https",
  "host": "app.example.test",
  "port": 443,
  "secure": true,
  "contextPath": "",
  "requestUrl": "https://app.example.test/api/inspect",
  "generatedLink": "https://app.example.test/api/resource/42"
}
```

**Đây đồng thời là minh họa tấn công** nếu người ngoài được phép gọi backend trực tiếp. Client tự đặt `X-Forwarded-Host` mà server chấp nhận thì generated links bị điều khiển bởi client. Cơ chế này **chỉ an toàn** khi headers trong request thật tới backend là do proxy đáng tin tạo ra sau khi xóa input không tin cậy.

### 7.6. Mô phỏng giả mạo host

```bash
curl -sS 'http://127.0.0.1:8080/api/inspect' \
  -H 'X-Forwarded-Proto: https' \
  -H 'X-Forwarded-Host: attacker.example.test' \
  -H 'X-Forwarded-Port: 443'
```

Trong lab đang bật FRAMEWORK, `host` và `generatedLink` có thể chứa `attacker.example.test`. Đây là behavior cần được **ngăn từ ranh giới proxy trong production**, không phải cách triển khai hợp lệ để lấy public host.

**Sau khi học xong, đổi strategy sang NONE nếu chạy service có thể bị truy cập từ mạng không tin cậy và chưa có trusted reverse proxy bảo vệ.**

### 7.7. Thử chế độ NONE để đối chiếu

Đổi config:

```properties
server.forward-headers-strategy=none
server.address=127.0.0.1
server.port=8080
```

Khởi động lại, gọi lệnh có `X-Forwarded-Host: attacker.example.test` như trên. Vì Boot không dùng forwarded strategy, các Servlet fields/link ở demo thông thường tiếp tục phản ánh URL kết nối trực tiếp `127.0.0.1:8080`. Nhưng nếu bạn tự viết code lấy `request.getHeader("X-Forwarded-Host")`, chuỗi header thô vẫn có thể hiện diện: NONE **không phải** một request header firewall.

## 8. Cấu hình reverse proxy minh họa: scrub rồi set

Ví dụ dưới đây là **fragment Nginx cho một topology cố định**, không phải cấu hình TLS production hoàn chỉnh. Nó giả định `app.example.test` đã được kiểm soát, proxy là HTTPS entry point, app chỉ nghe trên loopback `127.0.0.1:8080`, và không có routing prefix.

```nginx
# Đặt bên trong server/location HTTPS đã cấu hình TLS.
location / {
    proxy_pass http://127.0.0.1:8080;

    # Host backend nhất quán với public host hợp lệ.
    proxy_set_header Host app.example.test;

    # Xóa Forwarded chuẩn do client tự gửi.
    proxy_set_header Forwarded "";

    # Ghi đè bằng thông tin authoritative của edge proxy.
    proxy_set_header X-Forwarded-Proto https;
    proxy_set_header X-Forwarded-Host app.example.test;
    proxy_set_header X-Forwarded-Port 443;
    proxy_set_header X-Forwarded-For $remote_addr;

    # Không cho client tự gán các biến thể khác.
    proxy_set_header X-Forwarded-Ssl "";
    proxy_set_header X-Forwarded-Prefix "";
}
```

**Điều kiện đúng:** snippet phải được áp tại edge trust boundary, không bị một config Nginx inherited hoặc proxy phía trước/phía sau ghi đè trái chính sách. Cần xác nhận Nginx thực sự không chuyển các forwarded headers không liệt kê theo cách gây xung đột. Trong hệ thống phức tạp, scrub đầy đủ những tên header ứng dụng và toàn bộ middleware hỗ trợ, kể cả `Forwarded`, `X-Forwarded-For`, `X-Forwarded-Host`, `X-Forwarded-Proto`, `X-Forwarded-Port`, `X-Forwarded-Prefix` và các biến thể mà stack thực tế đọc.

Dòng `X-Forwarded-For $remote_addr` dùng IP của **kết nối tới Nginx**. Nếu Nginx thật sự là edge, đó là IP bên ngoài mà edge nhìn thấy. Nếu có CDN/proxy đáng tin ở trước Nginx, `$remote_addr` thường là IP của CDN, không phải client; muốn client thật cần thiết kế trusted-real-IP policy tại edge và đảm bảo CDN scrub headers trước.

### 8.1. Vì sao không mặc định dùng $proxy_add_x_forwarded_for?

Nginx có biến `$proxy_add_x_forwarded_for` để append IP hiện tại vào header `X-Forwarded-For` đã có. Nếu phần đã có do client tự gửi và chưa scrub, kết quả giữ cả IP giả do client đưa vào:

```text
Client: X-Forwarded-For: 1.2.3.4 (giả)
Proxy append: 1.2.3.4, 192.0.2.10
```

Một ứng dụng lấy phần tử đầu sẽ nhận IP giả. Việc append chỉ nên áp dụng khi **chuỗi trước đã được xây từ các hop tin cậy**, và hệ thống đọc chuỗi theo chính sách trusted proxies rõ ràng.

### 8.2. Có nhiều hostname public thì sao?

Không hardcode một host nếu sản phẩm hợp lệ dùng nhiều tenant domains. Nhưng **không được** chấp nhận mọi giá trị Host rồi copy nguyên vào `X-Forwarded-Host`. Proxy nên:
- Match `server_name`/routing rules dựa trên allowlist hostname/tenant domain hợp lệ.
- Từ chối default/unknown Host hoặc chuyển tới canonical host.
- Chỉ set `X-Forwarded-Host` bằng host đã qua validation/routing.
- Nếu app phải build password-reset/email links, ưu tiên public base URL nằm trong cấu hình/tài khoản tenant đã xác thực thay vì phụ thuộc raw request header.

### 8.3. X-Forwarded-Prefix khi gateway rewrite path

Ví dụ URL public là:

```text
https://app.example.test/portal/api/inspect
```

Proxy bỏ `/portal` và gửi backend:

```text
http://127.0.0.1:8080/api/inspect
```

Proxy có thể đặt `X-Forwarded-Prefix: /portal` để Spring dựng link công khai đúng context khi cơ chế/framework/version hỗ trợ. **Không** thêm `/portal` vào cả route backend lẫn code builder nếu framework đã áp dụng prefix; nếu làm vậy có thể xuất hiện `/portal/portal/...`.

Khả năng xử lý prefix khác nhau giữa `FRAMEWORK` và native container. Một số phiên bản Spring Framework cung cấp cấu hình riêng để bật việc sử dụng `X-Forwarded-Prefix`; cần kiểm tra Javadoc phiên bản thực của `ForwardedHeaderFilter`. Với API Spring hiện đại có constructor chọn family header và tùy chọn prefix, **không tự sao chép method từ Javadoc 7.x vào bản 6.x cũ**.

## 9. Nguy cơ an toàn web nếu tin header giả

### 9.1. Host header injection / password reset poisoning

Nếu code tạo email reset password như sau:

```java
String link = ServletUriComponentsBuilder
        .fromCurrentContextPath()
        .path("/reset")
        .queryParam("token", token)
        .toUriString();
```

Đây là snippet phụ thuộc `token`. Khi forwarded host có thể do attacker kiểm soát, URL trong email có thể trở thành:

```text
https://attacker.example.test/reset?token=...
```

Người dùng nhận email tưởng hợp lệ nhưng truy cập domain khác và có thể làm lộ token. **Cách phòng mạnh hơn:** tạo URL nhạy cảm từ **canonical public base URL đã cấu hình và được allowlist**; proxy cũng phải scrub forwarded headers và validate Host.

### 9.2. Open redirect và Location poisoning

Chuyển host của request thành host public không tự sinh open redirect, nhưng nhiều redirect helper có thể dùng host/scheme từ request. Nếu host này không tin cậy, attacker có thể ảnh hưởng `Location`. Với redirect đến URL tùy chọn như `next=...` vẫn cần kiểm tra relative path hoặc allowlist đích độc lập; ForwardedHeaderFilter **không** bảo vệ redirect parameter.

### 9.3. CORS: forwarded headers không quyết định Origin hợp lệ

`Origin: https://frontend.example.test` là request header được browser dùng trong cơ chế CORS. `X-Forwarded-Host: app.example.test` mô tả URL public theo proxy; hai khái niệm không đồng nghĩa.

Không viết CORS policy kiểu:

```java
// ANTI-PATTERN: lấy host/proxy metadata không tin cậy làm allowlist.
String origin = request.getHeader("Origin");
response.setHeader("Access-Control-Allow-Origin", origin);
response.setHeader("Access-Control-Allow-Credentials", "true");
```

Phản chiếu tùy ý Origin (đặc biệt cùng credentials) là nguy hiểm. Dùng danh sách origin đáng tin và credential policy riêng; forwarded headers không thay kiểm tra CORS. CORS cũng **không phải authentication hoặc CSRF protection**.

### 9.4. Cookie Secure và HTTPS

Nếu TLS kết thúc ở proxy, backend có thể thấy `http`/`isSecure=false` nếu không có handling tương ứng. Điều này có thể ảnh hưởng code tùy chỉnh hoặc framework dựa trên secure-request signal khi đặt cookies/redirects. Tuy nhiên không lấy `X-Forwarded-Proto=https` từ client làm “chứng minh đã có TLS”; proxy phải đảm bảo kết nối public thật được mã hóa.

Đối với session cookies: cấu hình `Secure`, `HttpOnly`, `SameSite`, TLS và security requirements theo mô hình của ứng dụng. Đừng dựa duy nhất vào `isSecure()` nếu architecture/cấu hình proxy không được kiểm soát.

### 9.5. OAuth2/OIDC callback và redirect_uri

OAuth2 client applications có thể tạo `redirect_uri` từ request và registered client settings. Forwarded host/scheme sai có thể khiến redirect URI không khớp hoặc bị tạo sai domain. Dùng registered redirect URI exact match, canonical public URLs, trusted proxy configuration và integration tests trên topology thực. Không để forwarded host tùy ý quyết định nơi gửi authorization code/token.

### 9.6. IP-based rate limit/audit

Nếu code dùng `X-Forwarded-For` phần tử đầu cho “IP thật”, kẻ gọi có thể spoof IP để né quota hoặc vu khống địa chỉ khác. Chỉ tin địa chỉ từ trusted chain do edge xác minh. Với security-critical identity, vẫn dùng authenticated principal/session/token và risk policy; IP là tín hiệu bổ sung, không phải chứng thư danh tính.

## 10. Checklist triển khai cùng Spring Security

| Trường hợp | Thực hành |
| --- | --- |
| HTTP ingress | Xác thực TLS/certificate, giới hạn public hosts |
| Backend port | Chỉ cho proxy/ingress truy cập; không expose NodePort/backend Internet |
| Forwarded headers | Scrub và tái tạo cả RFC `Forwarded` lẫn `X-Forwarded-*` ở edge |
| App strategy | Chọn `NONE/NATIVE/FRAMEWORK` có chủ đích, tránh xử lý kép |
| Client IP | Trusted proxy CIDRs/chain; không parse first XFF raw |
| CORS | Allowlist origins riêng; không tin Origin hay forwarded host tùy ý |
| CSRF | Bảo vệ state-changing requests khi dùng cookie/session authentication |
| Session cookie | Secure/HttpOnly/SameSite và security configuration phù hợp |
| Authentication | Spring Security identity; không dùng forwarded headers làm user ID |
| URL generation | Canonical public base URL cho link nhạy cảm |
| Logs/metrics | Không log raw Authorization/cookies/reset tokens; phân biệt remote proxy và verified client IP |
| Host validation | Allowlist public domains ở ingress/app; từ chối unknown Host |
| Redirect/callback | Test Location, OAuth redirect_uri, absolute links sau TLS termination |
| Security tests | Thử spoof header từ Internet/direct backend/bên trong network |

**Filter order quan trọng nhưng không đủ:** nếu một middleware khác đã đọc forwarded headers **trước** `ForwardedHeaderFilter` hoặc container đã biến request metadata ở tầng native, một filter chạy sau không thể sửa lại mọi quyết định trước đó. Vì vậy phải đặt trust boundary ngay ở mạng/proxy đầu vào.

## 11. Các test cần có trước khi cho traffic thật

### 11.1. Test qua proxy thật, không chỉ curl trực tiếp backend

| Test | Request từ phía public | Kỳ vọng |
| --- | --- | --- |
| A | HTTPS + Host công khai hợp lệ | URI/link trả về sử dụng `https://app.example.test` |
| B | Client thêm `X-Forwarded-Host: attacker.test` | Edge xóa header giả; link vẫn theo public host hợp lệ |
| C | Client thêm `Forwarded: host=attacker.test;proto=http` | Edge xóa header RFC giả; không có host/scheme poisoning |
| D | Client thêm `X-Forwarded-For: 1.2.3.4` | Hệ thống xác định IP theo trusted chain, không tin phần tử giả |
| E | Client đổi `Host` sang hostname không được cấp | Edge trả reject/redirect canonical đúng policy |
| F | Client thử truy cập trực tiếp backend:8080 | Bị chặn bởi network policy/firewall |
| G | Request qua route có `X-Forwarded-Prefix` | Link không thiếu/trùng prefix |
| H | Redirect 302/303 và OAuth callbacks | `Location`/redirect_uri khớp canonical host, scheme, path |
| I | App đổi strategy NONE/NATIVE/FRAMEWORK | Behavior khớp cấu hình và không có double normalization |

**Quan trọng:** test B/C/D phải gửi header spoof **từ ngoài trust boundary**, không chỉ gửi trực tiếp đến localhost app đang chạy trong lab. Nếu chỉ test backend, bạn đang chứng minh tính năng của filter, **không** chứng minh proxy đã scrub.

### 11.2. MockMvc test cho filter (unit/integration-in-app)

Thêm dependency `spring-boot-starter-test` rồi tạo test:

```java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = "server.forward-headers-strategy=framework")
@AutoConfigureMockMvc
class ForwardedMetadataTest {

    @Autowired
    MockMvc mvc;

    @Test
    void canReadForwardedMetadataInControlledTest() throws Exception {
        mvc.perform(get("/api/inspect")
                        .header("X-Forwarded-Proto", "https")
                        .header("X-Forwarded-Host", "app.example.test")
                        .header("X-Forwarded-Port", "443"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.scheme").value("https"))
                .andExpect(jsonPath("$.host").value("app.example.test"))
                .andExpect(jsonPath("$.secure").value(true));
    }
}
```

Đây là test **trên app**, không phải test reverse proxy; nó xác minh request wrapper/framework behavior khi header đã có. Tùy Boot version, filter registration trong MockMvc test context có thể phụ thuộc cách auto-configure filters. Nếu test không thấy behavior, hãy xác minh filter được đăng ký thay vì chuyển ngay sang parse raw headers.

### 11.3. Test host poisoning từ phía ingress

Một security regression test có giá trị là gửi yêu cầu vào **public URL thật** với cả hai loại forwarded headers giả:

```bash
curl -i 'https://app.example.test/api/inspect' \
  -H 'Forwarded: proto=http;host=attacker.example.test' \
  -H 'X-Forwarded-Host: attacker.example.test' \
  -H 'X-Forwarded-Proto: http'
```

Kỳ vọng hệ thống **không** tạo absolute link tới `attacker.example.test`, không tự nhận request public là HTTP chỉ vì header giả, và không bypass quyền. Status/body chính xác có thể phụ thuộc chính sách chặn header lạ của proxy; điều quan trọng là **không tin giá trị giả**.

**Không áp lệnh trên để kết luận ở một hệ thống bạn không sở hữu/không được phép test.** Trong môi trường lab hoặc staging được cấp quyền, đây là test cấu hình thông thường.

## 12. Troubleshooting: sai HTTPS/Host/prefix/redirect

| Triệu chứng | Nguyên nhân khả dĩ | Điều cần kiểm tra |
| --- | --- | --- |
| Link từ ứng dụng là `http://...:8080` | App chưa dùng metadata proxy | Strategy; proxy set `X-Forwarded-Proto/Host/Port` |
| `https` đúng nhưng host vẫn internal | Proxy chưa set hoặc app ưu tiên header khác | Cả `Forwarded` và `X-Forwarded-Host` |
| Link có `/portal/portal/...` | Prefix được thêm hai lần | Proxy path rewrite, context path và prefix |
| Redirect 302 quay lại HTTP | TLS termination/redirect trước forwarded handling | Tomcat redirect context root, filter order và `Location` |
| OAuth redirect_uri mismatch | App sinh URI khác registered value | Canonical public URL/forwarded policy |
| `isSecure()` false sau HTTPS proxy | Strategy none/native chưa đúng hoặc proto header thiếu | Container config, trusted proxy, X-Forwarded-Proto |
| Filter không chạy | Framework strategy chưa bật, servlet filter order/dispatcher types | Filter registration, REQUEST/ASYNC/ERROR |
| Filter chạy hai lần | Vừa Boot FRAMEWORK vừa tự đăng ký filter | Chọn một cơ chế |
| IP audit bị giả | App lấy phần tử đầu của XFF do client gửi | Scrub tại edge + trusted chain algorithm |
| Internal health URL đổi host bất ngờ | Gửi headers forwarded vào internal request | Dùng NONE/removeOnly cho traffic không qua trusted proxy |
| Direct backend request giả mạo scheme/host | Port backend exposed + FRAMEWORK | Network isolation và edge scrub |
| CORS origin lạ được phản chiếu | Policy CORS viết từ request input | Allowed origins tường minh |
| Password reset email trỏ domain khác | Host poisoning | Base URL cấu hình, host allowlist, proxy header scrub |
| `X-Forwarded-Prefix` không có tác dụng | Native không hỗ trợ hoặc framework/version config | Kiểm tra chiến lược và API version |
| Chặn header bằng removeOnly nhưng app vẫn “https” | Container đã xử lý NATIVE trước filter | Tắt native, scrub tại edge và test request metadata |
| Không xem được forwarded headers ở controller | ForwardedHeaderFilter cố ý ẩn chúng | Dùng normalized request fields; debug tại proxy an toàn |

### 12.1. Cách debug có hệ thống

1. Xác định topology thật: client → CDN? → WAF? → ingress? → backend. Ai là **edge of trust**?
2. Chụp cấu hình hiệu lực ở edge: đã xóa và set **cả hai họ** forwarded headers chưa?
3. Kiểm tra backend có nhận trực tiếp request từ Internet/VPC untrusted không.
4. Kiểm tra `server.forward-headers-strategy` effective trên đúng environment/profile và Servlet container.
5. Tại app, so sánh `request.getScheme()`, `getServerName()`, `getServerPort()` và link builder output với public URL mong muốn.
6. Nếu native/container, kiểm tra trusted/internal proxies và header names.
7. Nếu Framework, kiểm tra filter registration, order và prefix support.
8. Test từ phía public **có header spoof**, không chỉ request không có header.
9. Test redirect, secure cookies, OAuth callback, CORS và link nhạy cảm.
10. Giới hạn debug logs: không đưa token, cookie, thông tin khách hàng vào output chẩn đoán.

## 13. Kiến thức dễ nhầm

**Câu 1.** Có `ForwardedHeaderFilter` thì ứng dụng tự phân biệt header của proxy với header của client được không?

**Đáp án:** Không. Filter không biết nguồn gốc đáng tin; edge proxy phải scrub rồi set headers, backend phải bị hạn chế direct access.

**Câu 2.** `X-Forwarded-For` có chứng minh địa chỉ IP thực của người dùng không?

**Đáp án:** Không. Nó chỉ là dữ liệu HTTP; phải biết trusted proxy chain và loại bỏ header giả từ client trước khi sử dụng.

**Câu 3.** `server.forward-headers-strategy=framework` khác `native` như thế nào?

**Đáp án:** FRAMEWORK dùng Spring ForwardedHeaderFilter, NATIVE dùng container hỗ trợ forwarded headers. Khả năng đọc prefix và thuật toán trusted proxies có thể khác; không bật cả hai tùy tiện.

**Câu 4.** Khi nào dùng `removeOnly=true`?

**Đáp án:** Khi cần xóa forwarded headers khỏi downstream mà **không sử dụng thông tin trong chúng**. Nó không khôi phục public URL và không thay edge/proxy trust boundary.

**Câu 5.** Server đằng sau proxy nhìn thấy HTTP, user dùng HTTPS. Có thể tin client gửi `X-Forwarded-Proto=https` để xác định HTTPS không?

**Đáp án:** Chỉ sau khi giá trị ấy do proxy đáng tin tạo ra sau khi xóa client input. Nếu backend mở trực tiếp cho client, câu trả lời là không.

**Câu 6.** Forwarded headers có thay CORS allowlist, CSRF protection hoặc authentication không?

**Đáp án:** Không. Chúng mô tả metadata của request qua proxy; Origin policy, CSRF token, identity và authorization là các cơ chế độc lập.

**Câu 7.** Nếu proxy chỉ xóa `X-Forwarded-Host` nhưng không xóa `Forwarded` thì đã đủ an toàn chưa?

**Đáp án:** Chưa. Một thành phần có thể ưu tiên header RFC `Forwarded` vẫn chứa host giả.

**Câu 8.** Nếu public URL có `/portal` nhưng backend không có prefix, phải làm gì?

**Đáp án:** Cấu hình path rewrite/prefix ở gateway và Spring strategy/version phù hợp; kiểm tra URL builder không thiếu hoặc thêm lặp `/portal`.

## 14. Tài liệu chính thức

- [Spring Framework — Servlet Filters và Forwarded Headers](https://docs.spring.io/spring-framework/reference/web/webmvc/filters.html): RFC 7239, X-Forwarded headers, ForwardedHeaderFilter, trust boundary và dispatcher types.
- [Spring Framework 6.2 — ForwardedHeaderFilter Javadoc](https://docs.spring.io/spring-framework/docs/6.2.7/javadoc-api/org/springframework/web/filter/ForwardedHeaderFilter.html): wrapper semantics, `setRemoveOnly`, `setRelativeRedirects`.
- [Spring Boot 3.5 — Running Behind a Front-end Proxy Server](https://docs.spring.io/spring-boot/3.5/how-to/webserver.html#howto.webserver.use-behind-a-proxy-server): chiến lược NATIVE/FRAMEWORK, redirect/Tomcat.
- [Spring Boot 3.5 — ForwardHeadersStrategy Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/web/ServerProperties.ForwardHeadersStrategy.html): `NONE`, `NATIVE`, `FRAMEWORK`.
- [RFC 7239 — Forwarded HTTP Extension](https://www.rfc-editor.org/rfc/rfc7239): cú pháp và chuỗi proxy hops.
- [Spring Framework — ServletUriComponentsBuilder Javadoc](https://docs.spring.io/spring-framework/docs/6.2.7/javadoc-api/org/springframework/web/servlet/support/ServletUriComponentsBuilder.html): tạo URI dựa vào Servlet request.
- [Spring Security — Servlet Architecture](https://docs.spring.io/spring-security/reference/servlet/architecture.html): filter chain, security context và trust architecture.
- [OWASP — Host Header Injection](https://owasp.org/www-project-web-security-testing-guide/latest/4-Web_Application_Security_Testing/07-Input_Validation_Testing/17-Testing_for_Host_Header_Injection): rủi ro và kiểm thử Host header poisoning.
- [Nginx — proxy_set_header](https://nginx.org/en/docs/http/ngx_http_proxy_module.html#proxy_set_header): chính sách header chuyển tiếp tới upstream.

**Ghi nhớ cuối cùng:** ForwardedHeaderFilter giải quyết **độ chính xác của scheme/host/port/prefix khi ứng dụng đứng sau proxy**; nó **không chứng thực** giá trị forwarded headers. Một kiến trúc an toàn phải có proxy edge **loại bỏ header không tin cậy**, set metadata theo route/TLS thực sự, giới hạn đường truy cập backend, dùng đúng strategy `NONE/NATIVE/FRAMEWORK` và kiểm thử host/proto/IP spoofing. Với đường dẫn tuyệt đối nhạy cảm như reset-password hoặc OAuth callbacks, cân nhắc **canonical configured public URL** thay vì tin request metadata.
