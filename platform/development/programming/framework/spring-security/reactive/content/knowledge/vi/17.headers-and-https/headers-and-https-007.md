# Strict-Transport-Security và điều kiện triển khai HTTPS trong Spring Security reactive

## 1. Mục tiêu bài học

Khi ứng dụng Spring WebFlux phục vụ trang đăng nhập, cookie phiên, REST API hoặc nội dung nhạy cảm, **TLS/HTTPS là điều kiện cơ bản để bảo vệ dữ liệu khi truyền trên mạng**. Nhưng chỉ đặt redirect từ `http://` sang `https://` chưa xử lý hết tình huống kết nối HTTP ban đầu bị kẻ tấn công trên đường truyền can thiệp. **HTTP Strict Transport Security (HSTS)** giúp trình duyệt đã biết chính sách của website **chủ động nâng cấp các lần truy cập sau lên HTTPS**, đồng thời không cho người dùng đơn giản bỏ qua lỗi chứng chỉ với host đang bị ràng buộc HSTS.

Bài học này hướng dẫn:

1. Hiểu ý nghĩa header `Strict-Transport-Security`, các chỉ thị `max-age`, `includeSubDomains`, `preload` và hành vi của browser.
2. Phân biệt **HSTS**, **TLS**, **redirect HTTP → HTTPS** và **preload list**.
3. Nắm đúng mặc định HSTS của Spring Security **reactive**, API `ServerHttpSecurity.headers(...).hsts(...)` và giới hạn “chỉ ghi trên request HTTPS”.
4. Thiết lập HTTPS cho Spring Boot WebFlux Java 17+ ở local bằng keystore tự ký, tự kiểm tra header qua `curl`, rồi hiểu điều kiện dùng chứng chỉ công khai trong production.
5. Xử lý reverse proxy, TLS termination, `Forwarded`/`X-Forwarded-Proto`, proxy trust boundary và tình huống ứng dụng không nhận diện scheme HTTPS.
6. Lập kế hoạch tăng `max-age` dần, kiểm tra subdomain, cân nhắc preload và rollback mà không làm người dùng bị khóa khỏi website.
7. Viết test matrix và checklist triển khai an toàn trên hạ tầng nhiều node/CDN/ingress.

**Nguyên tắc quan trọng:** HSTS là **chính sách browser nhớ về một hostname**. HSTS **không cấp chứng chỉ, không bật TLS cho server, không thay thế redirect ở lần truy cập đầu và không bảo vệ toàn bộ loại HTTP client**.

## 2. Vì sao HTTPS redirect chưa đủ?

Giả sử một người dùng nhập `example.com` hoặc click liên kết `http://example.com/login`.

~~~text
Lần truy cập đầu, host chưa có HSTS trong browser:

Browser --HTTP--> http://example.com/
         |                |
         |         301/308 redirect
         |                v
         +------------> HTTPS
                           |
                    Response có:
                    Strict-Transport-Security
                           |
                           v
                   Browser ghi nhớ host

Lần truy cập sau, khi HSTS đang hiệu lực:

Người dùng gõ http://example.com/login
                           |
                           v
           Browser tự nâng cấp trước khi gửi request
                           |
                           v
                 HTTPS trực tiếp tới host
~~~

Ở **lần truy cập đầu** của một domain chưa được browser biết chính sách HSTS, request HTTP có thể bị kẻ tấn công mạng thay đổi trước khi redirect đến HTTPS. Sau khi browser nhận một response **HTTPS hợp lệ** có HSTS, browser nhớ quy tắc và chủ động chuyển `http://` thành `https://` ở lần sau. HSTS giảm nguy cơ **SSL stripping / protocol downgrade** và giúp từ chối các kết nối HTTPS có chứng chỉ lỗi đối với host đã được bảo vệ.

Điểm giới hạn:

- Nếu user chưa từng thấy HSTS và domain chưa nằm trong preload list, vẫn tồn tại **first-visit problem**.
- HSTS chỉ được browser ghi nhận từ **HTTPS response có chứng chỉ TLS được tin cậy**; header gửi trên HTTP không có hiệu lực bảo mật.
- HSTS không sửa một chứng chỉ hết hạn, không tự tạo TLS listener, không thay thế cơ chế xác thực/phân quyền hay xử lý lỗ hổng XSS.
- Browser là nơi thực thi HSTS. `curl` hay một HTTP client tùy chỉnh có thể không lưu/tuân chính sách đó theo mặc định.
- Các liên kết và tài nguyên mixed content (HTTP ảnh/script, WebSocket `ws://`) vẫn phải được sửa và kiểm thử; HSTS không thể thay một chính sách tải tài nguyên an toàn toàn diện.

## 3. Cú pháp và ý nghĩa của Strict-Transport-Security

Ba dạng thường gặp:

~~~http
Strict-Transport-Security: max-age=300
Strict-Transport-Security: max-age=31536000; includeSubDomains
Strict-Transport-Security: max-age=63072000; includeSubDomains; preload
~~~

### 3.1. max-age

`max-age` là **số giây** mà user agent ghi nhớ chính sách HSTS tính từ lần nhận header hợp lệ gần nhất.

| Giá trị | Thời hạn | Khi nào cân nhắc |
| --- | --- | --- |
| `max-age=300` | 5 phút | Bước canary/rollout ban đầu |
| `max-age=604800` | 7 ngày | Giai đoạn xác minh ổn định |
| `max-age=2592000` | 30 ngày | Theo dõi trước thời hạn dài |
| `max-age=31536000` | 365 ngày | Chính sách dài hạn khi HTTPS sẵn sàng |
| `max-age=63072000` | 730 ngày | Một cấu hình dài hạn thường dùng khi cân nhắc preload |
| `max-age=0` | Hủy policy HSTS **do chính host này đã lưu** nếu header được nhận qua HTTPS hợp lệ | Rollback có giới hạn, **không** xóa preload hoặc chính sách host cha |

Mỗi response HTTPS hợp lệ phát lại HSTS sẽ **gia hạn lại mốc hết hạn** từ thời điểm response, không phải chỉ tính từ lần cài đầu tiên. Nếu bạn bỏ header đi hôm nay, browser đã học chính sách vẫn giữ nó cho đến khi hết `max-age` (hoặc nhận `max-age=0` hợp lệ).

### 3.2. includeSubDomains

~~~http
Strict-Transport-Security: max-age=31536000; includeSubDomains
~~~

Chỉ thị này mở rộng chính sách từ hostname hiện tại xuống **mọi subdomain bên dưới**, bao gồm các cấp lồng nhau.

Ví dụ, response của `example.com` có `includeSubDomains` sẽ tác động tới `www.example.com`, `api.example.com`, `legacy.example.com` và `dev.internal.example.com` khi browser đã học policy của host cha. Nó **không** áp ngược từ `login.example.com` lên `example.com`, cũng không tự tác động đến domain sibling ngoài phạm vi host đó.

**Rủi ro lớn:** nếu một subdomain chỉ chạy HTTP, hoặc dùng chứng chỉ tự ký/đã hết hạn, HSTS ở domain cha có thể khiến browser không truy cập được subdomain đó. Cần kiểm kê **cả subdomain nội bộ**, hệ thống cũ, static assets, callback, SSO, API, staging và các hostname chưa dùng thường xuyên trước khi bật cho domain cha.

### 3.3. preload

~~~http
Strict-Transport-Security: max-age=63072000; includeSubDomains; preload
~~~

`preload` là **tín hiệu xin tham gia HSTS preload list**, không có nghĩa “bật header là domain lập tức được tất cả browser cài sẵn”. Domain còn phải đạt điều kiện của [hstspreload.org](https://hstspreload.org/) và được chấp nhận/triển khai qua các bản phát hành browser.

Preload giải quyết một phần **first-visit problem**, nhưng có ràng buộc rất lâu dài: mọi subdomain, kể cả nội bộ, có thể bị browser bắt buộc dùng HTTPS; gỡ khỏi danh sách preload có thể mất nhiều tháng và không đồng bộ ở mọi browser. **Không bật `preload(true)` theo mặc định chỉ vì tài liệu có ví dụ.** HSTS preload service hiện còn khuyến cáo phải cân nhắc kỹ vì lợi ích bổ sung của preload so với HSTS có thể nhỏ trong những môi trường browser đã chủ động nâng cấp HTTP.

### 3.4. Ghi nhớ theo hostname, không chỉ theo cổng

Policy HSTS được gắn với **hostname/domain name** chứ không chỉ một URL/path. Browser không học chính sách HSTS riêng biệt cho `/login` hay `/api`. Khi có hiệu lực, HSTS ảnh hưởng các lần truy cập HTTP đến host đó, không chỉ endpoint phát ra header ban đầu.

Không dùng IP literal, tên phát triển tùy tiện hoặc một host chung chia sẻ nhiều môi trường làm phép thử “preload production”. Với môi trường local, tên `localhost` và chứng chỉ tự ký có đặc tính triển khai khác domain công khai; một lệnh `curl -k` chỉ chứng minh server phát header, **không chứng minh browser đã tin chứng chỉ và lưu policy**.

## 4. Điều kiện HSTS có tác dụng

Cần phân biệt **header tồn tại trong response** với **browser thực sự chấp nhận HSTS**.

| Điều kiện | Nếu thiếu thì sao? |
| --- | --- |
| Server hoặc edge **phục vụ HTTPS thật** | Không thể dùng HSTS thay cho handshake TLS |
| Chứng chỉ hợp lệ cho đúng hostname, đủ chain, còn hạn và từ CA được client tin | Browser có thể từ chối kết nối; không được mong browser học HSTS từ TLS không đáng tin |
| Response gửi qua HTTPS theo kết nối client, hoặc ứng dụng nhận diện đúng scheme sau trusted proxy | Spring Security writer có thể không thêm header nếu hiểu request là HTTP |
| Header `Strict-Transport-Security` cú pháp hợp lệ | Browser có thể bỏ qua |
| Browser đã thấy HSTS hợp lệ hoặc domain đang trong preload list | Request HTTP đầu tiên vẫn có nguy cơ bị can thiệp |
| Những hostname/subdomain được ràng buộc đều sẵn sàng HTTPS | `includeSubDomains` hoặc preload có thể làm hỏng truy cập |
| DNS, port 443, load balancer, CDN, ingress, certificate renewal hoạt động | HSTS có thể khiến sự cố HTTPS thành tình huống khó hoặc không thể vượt qua |
| Không có lớp CDN/proxy khác phát header mâu thuẫn | Tránh nhiều policy khó kiểm chứng trên một response |

**Không làm như sau:** phát `Strict-Transport-Security` trên một endpoint HTTP và cho rằng browser sẽ tin nó; disable certificate validation trên client và tuyên bố HSTS đang bảo vệ; ép `includeSubDomains` trên domain gốc khi còn legacy HTTP-only services.

## 5. HSTS mặc định trong Spring Security reactive

### 5.1. Header mặc định

Spring Security WebFlux **bật HSTS theo mặc định** trong nhóm security response headers. Theo Javadoc của `StrictTransportSecurityServerHttpHeadersWriter` và `ServerHttpSecurity.HeaderSpec.HstsSpec`:

- `maxAge` mặc định là **1 năm** (tương đương `31536000` giây).
- `includeSubdomains` mặc định **true**.
- `preload` mặc định **false**.
- Writer chỉ thêm `Strict-Transport-Security` **khi request được nhận diện là secure/HTTPS**.

Do đó, đối với ứng dụng có HTTPS hoạt động và đang giữ header mặc định, phản hồi có thể mang:

~~~http
Strict-Transport-Security: max-age=31536000; includeSubDomains
~~~

**Đặc biệt:** một cấu hình Spring Security “không đụng headers” vẫn có thể đang phát chính sách **một năm và bao gồm subdomain**! Trước khi đưa một hostname sản xuất lên HTTPS, kiểm tra chính sách hiện hành và toàn bộ phạm vi domain. Nếu chưa sẵn sàng ràng buộc subdomain, cần **chủ động cấu hình `includeSubdomains(false)` và `maxAge` ngắn** trong giai đoạn rollout.

`preload=false` mặc định là thông tin quan trọng: đừng lẫn default Spring Security với một số ví dụ hướng dẫn bật preload minh họa.

### 5.2. API đúng cho WebFlux

Với reactive, cấu hình tại:

~~~java
.headers(headers -> headers
        .hsts(hsts -> hsts
                .maxAge(Duration.ofSeconds(300))
                .includeSubdomains(false)
                .preload(false)))
~~~

Đây là **snippet trong method cấu hình `ServerHttpSecurity`**, cần import `java.time.Duration`. Tên method là `includeSubdomains` (chữ “d” thường trong `Subdomains`), và `maxAge` nhận `java.time.Duration`.

Không copy cú pháp Servlet:

~~~java
// Servlet-only API, KHÔNG dùng với ServerHttpSecurity:
http.headers(headers -> headers
        .httpStrictTransportSecurity(hsts -> hsts
                .maxAgeInSeconds(31536000)
                .includeSubDomains(true)));
~~~

Hai đoạn trên là những **snippet so sánh**, không phải hai phần cần chạy cùng lúc. `HttpSecurity`/`SecurityFilterChain` dùng cho Servlet, còn bài này dùng `ServerHttpSecurity`/`SecurityWebFilterChain`.

### 5.3. Không disable toàn bộ headers

Một số cấu hình cũ có:

~~~java
.headers(headers -> headers.disable())
~~~

Đây là **anti-pattern nếu dùng chỉ để “sửa lỗi HSTS”**: nó có thể bỏ nhiều header bảo vệ khác như `X-Content-Type-Options`, chống clickjacking, cache control. Nếu có nhu cầu tắt riêng HSTS trong môi trường được quản trị bằng edge, chọn cấu hình có phạm vi hẹp:

~~~java
.headers(headers -> headers
        .hsts(hsts -> hsts.disable()))
~~~

Đây là snippet có chủ ý dành cho trường hợp **TLS/HSTS đã được xử lý tại một điểm duy nhất khác** và được kiểm thử; không phải khuyến nghị tắt HSTS trên production. Không để CDN, load balancer và app phát các header HSTS mâu thuẫn/khác thời hạn rồi phó mặc browser.

### 5.4. HSTS không tự redirect HTTP

Header HSTS trong response HTTPS và redirect HTTP→HTTPS là hai trách nhiệm riêng. Spring Security WebFlux cung cấp:

~~~java
.redirectToHttps(Customizer.withDefaults())
~~~

Đây là snippet tùy chọn, có tác dụng với các **request HTTP thực sự đến được security chain** và được framework nhận diện là HTTP. Nếu ứng dụng **chỉ lắng nghe HTTPS trên cổng 8443**, không có HTTP listener để Spring trả redirect khi client gửi HTTP. Ở production, thường đặt redirect trên CDN, ingress, gateway hoặc reverse proxy ở cổng 80.

## 6. HTTPS bắt buộc phải có trước khi tăng max-age

### 6.1. TLS certificate

Trong môi trường production, bảo đảm:

1. Chứng chỉ bao phủ đúng **hostname** mà browser dùng (SAN), không chỉ đúng IP hay một hostname khác.
2. Đầy đủ intermediate certificate chain, được CA mà browser tin cậy ký, chưa hết hạn.
3. Dịch vụ HTTPS khả dụng ổn định trên public entry point (thường cổng 443), bao gồm CDN và các ingress.
4. Có tự động gia hạn chứng chỉ, cảnh báo trước khi hết hạn, kiểm tra cập nhật secret ở mọi node.
5. Hỗ trợ phiên bản/cipher TLS hiện đại (TLS 1.2/1.3 phù hợp policy), không cho truyền bí mật qua HTTP.
6. Kiểm tra login, logout, cookie, API, callback OAuth2, WebSocket `wss://`, static assets, mobile và app cũ.
7. Xác nhận kết nối **giữa proxy và backend** theo trust boundary: TLS tại edge không có nghĩa lưu lượng nội bộ mặc nhiên an toàn nếu mạng nội bộ không được bảo vệ.

Khi TLS không còn hoạt động, user có HSTS **không thể click bỏ qua cảnh báo chứng chỉ** để tiếp tục vào host. Đây là lợi ích chống MITM nhưng cũng là rủi ro vận hành cần chuẩn bị.

### 6.2. Redirect từ HTTP

Nên có route `http://app.example.com` được xử lý ở edge bằng **301/308 redirect tới HTTPS** ngay cả khi HSTS đã bật: khách lần đầu, bot và client không hỗ trợ HSTS vẫn cần chuyển hướng. Redirect không thay thế HSTS vì response redirect đầu tiên vẫn có thể bị mạng HTTP không tin cậy chặn.

Ví dụ đoạn cấu hình Nginx **chỉ minh họa listener HTTP redirect**, chưa chứa toàn bộ cấu hình TLS listener, upstream và chứng chỉ:

~~~nginx
server {
    listen 80;
    server_name app.example.com;
    return 308 https://app.example.com$request_uri;
}
~~~

Chọn canonical hostname cố định thay vì tin `Host` header tùy tiện trong redirect, tránh open redirect/misrouting. Ở server TLS listener riêng cần cấu hình certificate, proxy, header HSTS và các chính sách tương ứng. Không đơn giản “dán” block này vào production rồi cho rằng có HTTPS hoàn chỉnh.

### 6.3. Cookies và application URLs

Chỉ có HSTS không đủ. Với session login:

- Cookie xác thực phải có `Secure`, `HttpOnly` và `SameSite` phù hợp.
- URL sinh từ controller, link trong email, OAuth2 callback/redirect URI, OpenAPI server URL và frontend API base URL phải dùng HTTPS/canonical host đúng.
- Không nhúng script từ HTTP trong page HTTPS; cân nhắc CSP và kiểm tra mixed content.
- Các endpoint GET không được làm thay đổi trạng thái; giữ CSRF cho cookie-based POST/PUT/DELETE.
- Tránh redirect loop do reverse proxy và backend không thống nhất scheme.

## 7. Ví dụ chạy được: Spring Boot WebFlux HTTPS + HSTS ngắn hạn

Bài thực hành dùng **Java 17+**, Maven, Spring Boot **4.1.2**, Spring Reactive Web và Spring Security. Demo đặt HTTPS trực tiếp trên cổng 8443, dùng keystore tự ký để kiểm tra **server phát HSTS header**. Vì certificate tự ký không được browser công khai tin cậy, ví dụ **không kiểm thử sự chấp nhận HSTS của browser trên Internet**.

### 7.1. Tạo project

Tạo project bằng [Spring Initializr](https://start.spring.io/): group `com.example`, artifact `reactive-hsts-demo`, Maven, Java 17+, dependencies `Spring Reactive Web` và `Spring Security`. File `pom.xml` tối giản:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>reactive-hsts-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
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
            <artifactId>spring-boot-starter-security</artifactId>
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

Để Spring Boot BOM chọn phiên bản Spring Security và Reactor tương thích. Không thêm `spring-boot-starter-web`, vì đó là stack Servlet/MVC, khác WebFlux.

### 7.2. Sinh keystore local bằng keytool

Tạo thư mục `src/main/resources` nếu chưa có. Trên máy có JDK 17+, chạy trong thư mục project:

~~~bash
mkdir -p src/main/resources

keytool -genkeypair \
  -alias local-https \
  -keyalg RSA -keysize 2048 \
  -storetype PKCS12 \
  -keystore src/main/resources/dev-keystore.p12 \
  -storepass changeit -keypass changeit \
  -validity 90 \
  -dname "CN=localhost, OU=Development, O=Example, L=Test, ST=Test, C=US" \
  -ext "SAN=dns:localhost,ip:127.0.0.1" \
  -noprompt
~~~

Đây là command Bash/Linux/macOS. Trên Windows PowerShell, tạo directory bằng `New-Item -ItemType Directory -Force src/main/resources`, rồi gọi `keytool` trên **một dòng**, bỏ dấu backslash nối dòng.

Sau khi chạy, file `src/main/resources/dev-keystore.p12` chứa **private key local**. Không commit keystore/private key hoặc password thật lên Git; `changeit` chỉ dùng cho ví dụ local. Chứng chỉ self-signed không thể thay thế certificate public CA cho production.

### 7.3. application.properties

Tạo `src/main/resources/application.properties`:

~~~properties
server.port=8443
server.ssl.enabled=true
server.ssl.key-store=classpath:dev-keystore.p12
server.ssl.key-store-password=changeit
server.ssl.key-store-type=PKCS12
server.ssl.key-alias=local-https

demo.hsts.max-age-seconds=300
~~~

Đây là cách bật **HTTPS trực tiếp tại Reactor Netty/embedded server** của Boot ở cổng 8443. Demo **không mở cổng HTTP 8080 riêng**, vì vậy không có điểm nào trên cổng 8080 để trả redirect nếu client gõ HTTP. Redirect ở edge hoặc HTTP connector là một cấu hình **khác**.

### 7.4. Java source đầy đủ

Tạo `src/main/java/com/example/hstsdemo/ReactiveHstsDemoApplication.java`:

~~~java
package com.example.hstsdemo;

import java.time.Duration;
import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;
import org.springframework.http.MediaType;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@SpringBootApplication
@EnableWebFluxSecurity
public class ReactiveHstsDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReactiveHstsDemoApplication.class, args);
    }

    @Bean
    SecurityWebFilterChain security(
            ServerHttpSecurity http, Environment environment) {

        long maxAgeSeconds = environment.getProperty(
                "demo.hsts.max-age-seconds", Long.class, 300L);

        if (maxAgeSeconds < 0) {
            throw new IllegalArgumentException(
                    "demo.hsts.max-age-seconds must not be negative");
        }

        return http
                .authorizeExchange(routes -> routes
                        .anyExchange().permitAll())
                .httpBasic(basic -> basic.disable())
                .formLogin(form -> form.disable())
                .headers(headers -> headers
                        .hsts(hsts -> hsts
                                .maxAge(Duration.ofSeconds(maxAgeSeconds))
                                .includeSubdomains(false)
                                .preload(false)))
                .build();
    }

    @RestController
    static class Pages {

        @GetMapping(value = "/", produces = MediaType.TEXT_PLAIN_VALUE)
        Mono<String> index() {
            return Mono.just("HTTPS_DEMO_OK");
        }

        @GetMapping(value = "/health",
                produces = MediaType.APPLICATION_JSON_VALUE)
        Mono<Map<String, String>> health() {
            return Mono.just(Map.of("status", "UP"));
        }
    }
}
~~~

**Nhận xét:**

- `SecurityWebFilterChain` và `ServerHttpSecurity` là API WebFlux, không phải `HttpSecurity` của Servlet.
- Demo intentionally dùng `permitAll()` để tập trung vào HTTPS/HSTS. **Không lấy rule này áp vào API có dữ liệu người dùng**; production vẫn phải cấu hình authentication và authorization.
- `maxAge(Duration.ofSeconds(300))` tạo chính sách **5 phút**, phù hợp test có kiểm soát.
- `includeSubdomains(false)` tránh ràng buộc các subdomain không liên quan khi đang học.
- `preload(false)` không xin đưa host vào preload list.
- Khi server nhận request HTTPS hợp lệ, Spring Security writer thêm `Strict-Transport-Security` trước khi commit response.
- Application không tự tạo TLS certificate. Boot load PKCS#12 đã được `keytool` tạo trong bước trước.
- `Mono<String>` và `Mono<Map<...>>` cho phép controller xử lý theo reactive stack; không dùng `block()`.
- `GET /health` là endpoint demo, **không phải Spring Boot Actuator**. Trong production cần quyết định endpoint health nào được expose, quyền truy cập và dữ liệu nào được trả.

### 7.5. Chạy ứng dụng

Trong thư mục có `pom.xml`:

~~~bash
./mvnw clean package
./mvnw spring-boot:run
~~~

Windows: `.\mvnw.cmd clean package` rồi `.\mvnw.cmd spring-boot:run`. Nếu không có Maven wrapper, dùng `mvn` đã cài.

Truy cập cổng **8443** qua HTTPS. Vì certificate local tự ký, lệnh `curl` thông thường sẽ không tin certificate:

~~~bash
curl -i https://localhost:8443/
~~~

Kết quả thường gặp là lỗi TLS verification như `SSL certificate problem: self-signed certificate` hoặc lỗi tương đương, **không phải bug của HSTS**.

Để **chỉ kiểm tra header được server phát trong local**, có thể dùng `-k`:

~~~bash
curl -k -i https://localhost:8443/
curl -k -i https://localhost:8443/health
~~~

Kết quả mong đợi cho `GET /`:

~~~http
HTTP/1.1 200 OK
Strict-Transport-Security: max-age=300
Content-Type: text/plain;charset=UTF-8

HTTPS_DEMO_OK
~~~

Thứ tự headers và những header bổ sung do framework tạo có thể khác; quan trọng là **status 200**, body `HTTPS_DEMO_OK` và một header HSTS tương ứng `max-age=300`, **không có `includeSubDomains` hoặc `preload`** trong demo. Một số response có thể có header cache hoặc bảo mật khác.

**Lưu ý an toàn:** `curl -k` bỏ kiểm tra chain/chứng chỉ **chỉ để thử local**. Nó **không chứng minh** browser đã ghi nhớ HSTS, và tuyệt đối không sử dụng `-k` như cách kiểm thử production TLS. Trong production, dùng `curl -i https://app.example.com/` **không có `-k`** để kiểm tra chứng chỉ được tin cậy.

### 7.6. Thử request HTTP và hiểu giới hạn

~~~bash
curl -i http://localhost:8443/
~~~

Lệnh này đang nói HTTP plaintext với cổng **chỉ hiểu TLS**; có thể thất bại handshake hoặc nhận response lỗi, **không mong một redirect 301/308**. Trong demo không có HTTP listener; HSTS là **response header trên HTTPS**, không phải chức năng tự mở cổng 80/8080.

Để chứng minh redirect, cần thêm HTTP ingress/edge hoặc cấu hình HTTP connector riêng; ở production nên để load balancer/CDN/ingress xử lý cổng 80 rồi chuyển sang 443. Nếu backend thật sự nhận cả request HTTP và bạn muốn Spring Security redirect, có thể dùng `.redirectToHttps(Customizer.withDefaults())` trong chain phù hợp. Chỉ nên bật sau khi bảo đảm forwarded scheme chính xác để tránh vòng lặp.

### 7.7. Thay max-age theo cấu hình

Thử sửa `demo.hsts.max-age-seconds=604800` và khởi động lại, sau đó quan sát header `max-age=604800` qua `curl -k -i`. Đây chỉ là kiểm tra **server emission** trong local; không cố phát long-lived HSTS cho một domain chung dùng thử nghiệm của người khác.

Khi cân nhắc production, phải thay đổi thêm `includeSubdomains(false)` thành `true` **chỉ sau khi toàn bộ subdomain đáp ứng HTTPS**. Không bật preload trong ví dụ tự học.

## 8. TLS termination tại reverse proxy / load balancer

Trong nhiều hệ thống, browser **HTTPS → CDN/ingress/ALB**, rồi proxy gọi Spring WebFlux bằng **HTTP nội bộ**:

~~~text
Browser
  | HTTPS TLS (public certificate valid)
  v
CDN / reverse proxy / ingress :443
  | TLS terminated
  | X-Forwarded-Proto: https (do proxy tin cậy đặt)
  v
Spring WebFlux service :8080 (HTTP nội bộ, private network)
  |
  v
SecurityWebFilterChain / HSTS headers
~~~

Nếu Spring WebFlux nhìn request vào từ proxy là **`http://`** và chưa được cấu hình xử lý forwarded headers, `StrictTransportSecurityServerHttpHeadersWriter` có thể **không thêm HSTS**, dù browser đã nói chuyện với edge bằng HTTPS. Ngược lại, nếu server tin **`X-Forwarded-Proto: https` do client tùy ý giả mạo**, cả redirect và generated URL/security decisions có thể sai.

### 8.1. Forwarded headers là dữ liệu phải có trust boundary

Spring Boot hỗ trợ:

~~~properties
server.forward-headers-strategy=framework
~~~

Với WebFlux, strategy này dùng cơ chế của Spring Framework để xử lý `Forwarded`/`X-Forwarded-*` (qua `ForwardedHeaderTransformer` tương ứng). Một lựa chọn khác là `native` nếu embedded server/platform hỗ trợ và được cấu hình đúng:

~~~properties
server.forward-headers-strategy=native
~~~

**Đây là các phương án riêng, không khai báo hai dòng cạnh nhau trong một cấu hình thật.**

Chỉ bật forwarded-header support khi:

1. Ứng dụng được đặt **sau proxy bạn quản trị/đã xác định tin cậy**.
2. Proxy **xóa hoặc ghi đè** mọi `Forwarded`/`X-Forwarded-*` do client bên ngoài gửi, rồi gắn thông tin scheme/host/port chính xác.
3. Backend không bị truy cập trực tiếp từ Internet, hoặc có cơ chế chặn/phân biệt request không đi qua proxy.
4. Có test request HTTPS ở browser → proxy → backend được nhận diện scheme https và URL redirect đúng.
5. Không phát sinh redirect loop HTTP↔HTTPS hoặc tạo redirect theo host do client tùy ý kiểm soát.

**Không dùng sự tồn tại đơn thuần của `X-Forwarded-Proto` để tin một request là HTTPS**. Header có thể do client tự đưa vào; nếu ứng dụng dựa nó để bypass logic bảo mật khi không có proxy trust boundary, đó là lỗ hổng cấu hình.

### 8.2. Đặt HSTS tại Spring hay tại edge?

Cả hai cách có thể đúng, nhưng cần **một policy thống nhất**.

| Đặt HSTS ở đâu | Ưu điểm | Điều cần chú ý |
| --- | --- | --- |
| **Spring Security WebFlux** | Policy nằm cùng code/security chain; dễ kiểm thử | App phải hiểu scheme HTTPS sau proxy; mọi public response cần đi qua chain |
| **CDN / load balancer / ingress** | Kiểm soát tại public TLS boundary, cả trang lỗi CDN/redirect | Cấu hình đúng cho mọi hostname/route, tránh duplicate header từ app |
| **Cả hai cùng phát** | Có thể trùng policy nếu cố ý phối hợp | Rủi ro hai giá trị khác nhau, khó biết user agent xử lý; không nên tùy tiện |

Ở production, nếu edge phát HSTS trên HTTPS responses, có thể chủ động tắt **riêng HSTS writer** tại Spring để tránh duplicate, nhưng vẫn giữ các security response headers khác. Nếu giữ Spring là nơi phát HSTS, phải kiểm tra 200, redirect HTTPS, response lỗi 4xx/5xx và các đường CDN caching phù hợp.

**Không đưa HSTS header vào HTTP response từ edge rồi cho rằng browser sẽ ghi nhận nó.** HSTS chỉ đáng tin nếu được gửi trên HTTPS.

### 8.3. Kiểm thử qua public domain

Khi có domain công khai, certificate CA hợp lệ và edge HTTPS đang hoạt động:

~~~bash
curl -i https://app.example.com/
curl -I https://app.example.com/login
curl -I http://app.example.com/
~~~

Đây là **ví dụ địa chỉ placeholder cho deployment**, không phải domain đang hoạt động. Chỉ thực thi sau khi thay bằng hostname thực.

Cần xác nhận:

- HTTPS kết nối hợp lệ **không dùng `-k`**, chứng chỉ đúng hostname.
- Response HTTPS có **một** HSTS policy dự kiến ở điểm public edge.
- HTTP trả 301/308 đến URL `https://...` với host/path đã chuẩn hóa. Có thể dùng mã redirect khác theo mục đích, nhưng tránh redirect loop.
- Không lộ credential/session cookie trên HTTP; cookie auth mang `Secure`.
- Nếu có web login, trang login và response lỗi cũng không bị strip HSTS không chủ đích.
- Nếu proxy gọi backend HTTP, backend chỉ chấp nhận traffic từ proxy và forwarded headers được sanitize.

## 9. Rollout HSTS an toàn theo giai đoạn

HSTS không phải switch “bật rồi đổi lại ngay”: browser có thể cache chính sách dài hạn. Nên lập kế hoạch theo **domain cụ thể**, có owner cho hạ tầng TLS, subdomain và proxy.

### 9.1. Các bước đề xuất

1. **Kiểm kê:** lập danh sách tất cả hostname/subdomain, bao gồm các cấp sâu, internal services, legacy, staging, OAuth callbacks, CDN, service worker, WebSocket và mobile clients.
2. **HTTPS trước:** triển khai certificate hợp lệ, redirect HTTP→HTTPS, sửa mixed content và URL sinh ra từ ứng dụng; giám sát TLS errors.
3. **Xem default hiện hành:** Spring Security có thể đang phát `max-age=31536000; includeSubDomains`; đừng giả định “chưa cấu hình nghĩa là chưa bật”.
4. **Canary:** bắt đầu tại hostname/subdomain kiểm soát được với `max-age=300`, `includeSubDomains=false`, `preload=false` nếu chưa audit toàn domain.
5. **Tăng dần:** sau khi ổn định, cân nhắc `604800` (1 tuần), `2592000` (1 tháng), rồi `31536000` (1 năm), giám sát ít nhất đến hết một kỳ tương ứng trước khi tăng tiếp trong quy trình thay đổi quan trọng.
6. **Thêm subdomains khi an toàn:** chỉ bật `includeSubDomains` sau khi chứng minh mọi subdomain trong phạm vi được hỗ trợ HTTPS, kể cả host có DNS nội bộ.
7. **Preload (nếu thực sự cần):** đánh giá riêng, phê duyệt của chủ sở hữu domain và theo điều kiện [hstspreload.org](https://hstspreload.org/); không coi đây là bước bắt buộc cho mọi web app.
8. **Giám sát liên tục:** hạn chứng chỉ, renew failures, 4xx/5xx, redirect loops, TLS handshake, synthetic monitoring từ mạng ngoài, các subdomain ít dùng.

Bảng lộ trình ví dụ:

| Pha | Header | Phạm vi | Gate lên pha sau |
| --- | --- | --- | --- |
| A – thử nghiệm | `max-age=300` | Một hostname được kiểm soát | HTTPS và 200/3xx/4xx đúng |
| B – một tuần | `max-age=604800` | Cùng hostname | Không có TLS/redirect/cookie lỗi |
| C – một tháng | `max-age=2592000` | Cùng hostname hoặc subdomain đã xác minh | Theo dõi đủ kỳ, không broken links |
| D – dài hạn | `max-age=31536000` | Chỉ khi TLS vận hành ổn định | Có certificate rotation, disaster recovery |
| E – mở rộng | `...; includeSubDomains` | Cả domain được audit | Tất cả subdomain HTTPS |
| F – preload tùy chọn | `...; includeSubDomains; preload` | Domain đủ điều kiện | Phê duyệt hậu quả dài hạn |

**Không có một lộ trình universal cho mọi tổ chức.** Nếu domain gốc chứa subdomain legacy HTTP, không tăng chính sách của domain gốc với `includeSubDomains` chỉ vì hostname chính đã đáp ứng HTTPS.

### 9.2. Vì sao preload rủi ro cao?

Để đủ điều kiện submit preload theo các hướng dẫn hiện hành, website cần:

- Certificate hợp lệ.
- Redirect HTTP→HTTPS trên **cùng hostname** nếu nhận HTTP tại port 80.
- Mọi subdomain đều phục vụ HTTPS, kể cả những tên nội bộ đã đưa vào phạm vi domain.
- HTTPS response trên base domain có HSTS `max-age` **ít nhất 31536000 giây**, `includeSubDomains` và `preload`.
- Những HTTPS redirect bổ sung cũng phải có HSTS ở response cần thiết.

Không phải chỉ có header đúng là xong: muốn preload cần được submit/chấp nhận; thay đổi xuất hiện trong browser update và việc xóa khỏi preload list có thể mất rất lâu. Cơ chế preload **không phải nút rollback tức thì**.

## 10. Rollback và xử lý sự cố

### 10.1. max-age=0 có tác dụng gì?

Nếu muốn xóa policy HSTS đã được một host trực tiếp lưu:

~~~http
Strict-Transport-Security: max-age=0
~~~

Browser phải nhận header này qua **HTTPS hợp lệ** từ đúng host. Một response HTTP chứa `max-age=0` **không xóa được** policy, bởi browser không tin HSTS qua HTTP.

Nếu host đang nằm dưới một chính sách `includeSubDomains` của **host cha**, xóa policy riêng tại host con không giải trừ chính sách cha. Nếu domain đã preload, phát `max-age=0` cũng không làm domain biến mất ngay khỏi preload list đã phát hành. Nếu host đang mất TLS và người dùng HSTS không thể vào HTTPS, bạn cũng không thể “gửi nhanh max-age=0 qua HTTP” để cứu.

### 10.2. Lập phương án khôi phục **trước** khi tăng tuổi HSTS

- Luôn có kế hoạch khôi phục certificate/secret, DNS, listener 443 và TLS termination.
- Duy trì quyền truy cập hạ tầng quản trị ngoài website đang được HSTS bảo vệ (không dựa độc nhất vào một HTTP-only subdomain bị chặn).
- Khi đổi CDN/ingress hoặc cert, test trước ở staging.
- Giám sát những client không phải browser, vì chúng có thể không thực thi HSTS giống Chrome/Firefox.
- Nếu phát hiện subdomain HTTP-only trước khi bật chính sách dài, sửa trước khi tăng max-age.
- Nếu đã phát policy dài, ngay cả sau khi tắt header, browser đã lưu vẫn có thể tiếp tục nâng cấp HTTP đến hết kỳ.

### 10.3. HSTS không bảo vệ tất cả lỗi SSL/TLS

HSTS không thay thế:

- Chứng chỉ từ CA được tin cậy, đúng SAN, còn hạn.
- Cấu hình cipher/protocol TLS hiện đại.
- Cookie `Secure` và chính sách không lộ secrets trên HTTP.
- HTTPS trên tất cả backend mà threat model yêu cầu.
- CSP/mixed-content blocking, CSRF protection, authentication/authorization.
- Kiểm tra certificate khi client `WebClient` gọi upstream; đừng cấu hình trust-all SSL context chỉ để request “chạy”.

## 11. Bảng chẩn đoán lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách điều tra |
| --- | --- | --- |
| HTTPS 200 nhưng thiếu HSTS | Security headers bị disable, chain khác match, proxy strip header, Spring hiểu request HTTP | Xem chain, response ở edge, forwarded scheme |
| HTTP response có HSTS nhưng browser vẫn dùng HTTP | Browser bỏ qua HSTS từ HTTP | Phải phục vụ và kiểm tra HTTPS |
| `curl -k` thấy HSTS nhưng browser không nhớ | Cert tự ký/không tin; curl không làm bài test HSTS browser | Dùng domain/cert hợp lệ cho browser E2E |
| Header chỉ ở 200, thiếu trên 301/403/500 | Edge/route khác phát response, header config không bao phủ | Kiểm tra cả redirect/error responses |
| Redirect loop giữa HTTP và HTTPS | Proxy TLS termination nhưng backend không biết forwarded proto | Trust proxy, ForwardedHeaderTransformer / NATIVE |
| Chỉ prod không có HSTS | SSL termination ở proxy, app nhận scheme http | Cấu hình trusted forwarded header hoặc đặt HSTS tại edge |
| Site và subdomains bị khóa sau bật includeSubDomains | Subdomain không có TLS/cert hợp lệ | Audit/cấp TLS trước, rollback có giới hạn |
| Gõ http mà browser tự đổi thành https dù server HTTP không redirect | Browser đã cache HSTS hoặc domain preloaded | Kiểm tra browser HSTS state và policy cha |
| Xóa header nhưng browser vẫn bắt HTTPS | max-age chưa hết hoặc preloaded | HSTS không biến mất ngay khi bỏ header |
| Gửi max-age=0 qua HTTP vẫn không phục hồi | Browser không tin HTTP header | Cần HTTPS hợp lệ; còn policy cha/preload |
| API client vẫn gọi HTTP | Client không hỗ trợ/không lưu HSTS | Enforce HTTPS ở server/edge, client URL |
| Một domain phát 2 header với tuổi khác nhau | App và CDN cùng cấu hình | Chọn điểm phát header thống nhất |
| Browser lỗi chứng chỉ không cho bypass | HSTS enforce, cert invalid | Sửa chứng chỉ thật; không tắt kiểm tra TLS |
| Mở domain thật qua IP và HSTS không như mong đợi | HSTS theo hostname, cert SAN/Host khác | Dùng hostname chính thức |

### 11.1. Phân biệt lỗi của SSL với lỗi security header

Nếu `curl https://...` không handshake được, **không đổ lỗi cho HSTS** trước khi xác định DNS, port 443, certificate chain và TLS protocol. Nếu HTTPS hoạt động nhưng header không có, hãy kiểm tra Spring Security writer, reverse proxy và điểm nào thực sự phát public response.

Nếu response 401/403, đó là authentication/authorization; HSTS nên được kiểm tra **độc lập với HTTP status** và không được dùng để thay thế việc kiểm soát quyền.

## 12. Kiểm thử và tiêu chí nghiệm thu

### 12.1. Local smoke test

Trên project demo phần 7:

~~~bash
# Có HSTS response, chỉ bỏ qua cert vì môi trường tự ký
curl -k -i https://localhost:8443/

# Kiểm tra JSON endpoint cũng có header
curl -k -i https://localhost:8443/health

# Không tự có HTTP redirect do chỉ bật TLS listener 8443
curl -i http://localhost:8443/
~~~

Mong đợi hai HTTPS response đầu có header `Strict-Transport-Security: max-age=300`. Lệnh cuối là test khác giao thức với cổng TLS, **không** được coi là fail của HSTS khi server không có HTTP listener.

### 12.2. Production acceptance test

| Nhóm test | Bước thực hiện | Điều kiện đạt |
| --- | --- | --- |
| TLS | `curl -i https://app.example.com/` không dùng -k | Kết nối chứng chỉ hợp lệ |
| HSTS | Kiểm tra HTTPS 200/3xx/4xx | Có header phù hợp, không duplicate |
| Redirect | `curl -I http://app.example.com/` | Redirect HTTPS canonical |
| First-visit | Browser mới không có HSTS state | Có redirect an toàn nhưng hiểu nguy cơ lần đầu |
| Cached policy | Browser đã học policy, thử link HTTP | Browser nâng cấp trước network HTTP |
| includeSubDomains | Test danh sách subdomain thực tế | Mỗi subdomain có TLS hoạt động |
| Cert rotation | Roll/renew certificate ở canary | Không bị broken TLS |
| Proxy scheme | Backend sau trusted proxy | Không redirect loop; HSTS xuất hiện ở public edge |
| Security headers | Kiểm tra header khác | Không mất CSP/X-Frame-Options/nosniff do disable all |
| Cookie auth | Login, logout, callback | Cookie Secure, URL HTTPS, không lộ plaintext |
| CDN error | Thử 301/404/503 có kiểm soát | Chính sách HSTS nhất quán trong phạm vi quản lý |
| Rollback | Thử trong domain canary | Hiểu max-age đã cache và trường hợp không thể đảo ngược nhanh |

Không dùng `curl -k` khi công bố kết quả chứng chỉ hợp lệ cho production. Browser test phải dùng profile/cookie/HSTS state **được cô lập**; nếu profile đã cache một policy khác từ trước thì test có thể đánh lừa.

### 12.3. Test bằng Java/WebTestClient

Có thể viết unit test cho lớp `StrictTransportSecurityServerHttpHeadersWriter` hoặc integration test WebFlux Security khi request có scheme `https`. Khi dùng `MockServerWebExchange`, **phải giả lập request secure đúng cách**; gửi một request mock dạng `http://` rồi mong HSTS xuất hiện sẽ tạo false negative.

Gợi ý test giả định (snippet **không phải class test đầy đủ**):

~~~java
MockServerWebExchange exchange = MockServerWebExchange.from(
        MockServerHttpRequest.get("https://app.example.com/"));

StrictTransportSecurityServerHttpHeadersWriter writer =
        new StrictTransportSecurityServerHttpHeadersWriter();
writer.setMaxAge(Duration.ofSeconds(300));
writer.setIncludeSubDomains(false);
writer.setPreload(false);

StepVerifier.create(writer.writeHttpHeaders(exchange))
        .verifyComplete();

String header = exchange.getResponse().getHeaders()
        .getFirst("Strict-Transport-Security");
assertEquals("max-age=300", header);
~~~

Cần Spring Test, Reactor Test, JUnit và imports phù hợp. Đây chỉ là **snippet để diễn giải contract**, không chứng minh toàn bộ HTTP server đã bật HTTPS: test TLS thực tế vẫn cần chạy server có certificate hoặc qua public edge. Nếu mock request HTTPS không có đủ SSL info cho bộ writer ở phiên bản của bạn, hãy dùng integration test từ HTTPS listener thật thay vì sửa test thành “giả secure bằng header spoof”.

## 13. Checklist triển khai production

1. Đã xác định public hostnames, internal subdomains, root domain và các domain liên quan cần bảo vệ.
2. TLS/HTTPS thật hoạt động ổn định với certificate CA đáng tin, SAN đúng, full chain và auto-renew.
3. Có redirect HTTP→HTTPS tại entry point phù hợp, kể cả khách lần đầu.
4. Đã kiểm tra Spring Security mặc định có HSTS một năm/includeSubDomains hay chưa, không dựa vào giả định.
5. Chỉ tăng `max-age` sau khi test/monitor trong một thời gian đủ đại diện.
6. `includeSubDomains` chỉ bật khi tất cả subdomains, kể cả nội bộ, hoạt động qua HTTPS.
7. `preload` chỉ bật sau security review/owner approval; hiểu thời gian thêm/xóa khỏi preload list.
8. CDN, ingress, app thống nhất điểm phát HSTS; không có header duplicate/mâu thuẫn.
9. Backend sau TLS proxy nhận diện đúng request scheme, chỉ tin `X-Forwarded-*` từ proxy đáng tin.
10. Browser/client-generated URL, OAuth2 redirect URI, cookie `Secure`, static assets và WebSocket đều dùng HTTPS.
11. Không dùng `curl -k` để tuyên bố kiểm thử TLS production thành công.
12. HSTS không thay thế CSRF, authentication, authorization, CSP hoặc TLS certificate management.
13. Có cảnh báo khi certificate sắp hết hạn, health check HTTPS, synthetic test và kế hoạch phục hồi.
14. Không dùng `headers.disable()` chỉ để thay đổi policy HSTS; preserve các header còn lại.
15. Có test với browser profile mới và profile đã học HSTS, nhiều hostname và subdomain.
16. Có runbook rollback hiểu `max-age=0` chỉ hiệu lực qua HTTPS và không tức thì với preload/host cha.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** Spring Security reactive mặc định có thêm Strict-Transport-Security trên request HTTP không?

**Đáp án:** Không. HSTS writer chỉ thêm header khi request được nhận diện là HTTPS/secure. Nếu public client dùng HTTPS nhưng backend sau proxy nhận request HTTP, cần xử lý forwarded scheme tin cậy hoặc để edge phát header.

**Câu 2.** Header `Strict-Transport-Security: max-age=31536000; includeSubDomains` nghĩa là gì?

**Đáp án:** Browser ghi nhớ trong khoảng một năm tính từ response hợp lệ gần nhất rằng hostname và các subdomain thuộc phạm vi phải dùng HTTPS.

**Câu 3.** Một website chỉ có HTTP redirect tới HTTPS đã hoàn toàn tránh được SSL stripping chưa?

**Đáp án:** Chưa. Request HTTP đầu tiên của người dùng chưa biết HSTS vẫn có thể bị can thiệp. HSTS có tác dụng sau khi browser học policy, còn preload có thể giúp với lần đầu khi domain đã được đưa vào danh sách.

**Câu 4.** Tại sao `curl -k` không chứng minh browser đã được bảo vệ bởi HSTS?

**Đáp án:** `-k` bỏ qua certificate validation; browser chỉ tin HSTS từ HTTPS tin cậy. `curl` cũng không nhất thiết lưu HSTS như browser.

**Câu 5.** Có nên bật `preload(true)` ngay khi ứng dụng đã có certificate không?

**Đáp án:** Không. Preload đòi mọi subdomain có HTTPS, max-age dài, các điều kiện riêng và việc thêm/gỡ kéo dài. Phải đánh giá chính sách toàn domain trước khi quyết định.

**Câu 6.** Vì sao API sau reverse proxy không phát HSTS dù người dùng truy cập HTTPS?

**Đáp án:** TLS kết thúc ở proxy nên backend có thể hiểu request là HTTP. Cần dùng forwarded headers do proxy đáng tin đặt và cấu hình WebFlux tương ứng, hoặc phát HSTS tại edge.

**Câu 7.** Có thể gửi `max-age=0` trên HTTP để cứu website đang lỗi certificate không?

**Đáp án:** Không. Browser bỏ qua HSTS header trên HTTP; chỉ nhận xóa policy từ HTTPS hợp lệ. Chính sách của host cha và preload còn có thể tiếp tục áp dụng.

**Câu 8.** Vì sao demo dùng `includeSubdomains(false)` và `max-age=300`?

**Đáp án:** Đó là cấu hình thận trọng cho thử nghiệm HSTS emission, tránh khóa subdomain và giữ thời gian cache ngắn. Production nên nâng tuổi chỉ sau khi HTTPS đã được xác minh.

## 15. Tài liệu chính thức và tham khảo

- [Spring Security — HTTP, Redirect to HTTPS và HSTS trong WebFlux](https://docs.spring.io/spring-security/reference/reactive/exploits/http.html)
- [Spring Security — Security HTTP Response Headers (Reactive)](https://docs.spring.io/spring-security/reference/reactive/exploits/headers.html)
- [Javadoc — ServerHttpSecurity.HeaderSpec.HstsSpec](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.HeaderSpec.HstsSpec.html)
- [Javadoc — StrictTransportSecurityServerHttpHeadersWriter](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/header/StrictTransportSecurityServerHttpHeadersWriter.html)
- [Javadoc — ServerHttpSecurity, redirectToHttps](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.html)
- [Spring Boot — Running Behind a Front-end Proxy Server](https://docs.spring.io/spring-boot/4.1/how-to/webserver.html)
- [MDN — Strict-Transport-Security](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Strict-Transport-Security)
- [HSTS Preload — Requirements and Deployment Recommendations](https://hstspreload.org/)
- [RFC 6797 — HTTP Strict Transport Security](https://www.rfc-editor.org/rfc/rfc6797.html)
- [OWASP — HTTP Strict Transport Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/HTTP_Strict_Transport_Security_Cheat_Sheet.html)
