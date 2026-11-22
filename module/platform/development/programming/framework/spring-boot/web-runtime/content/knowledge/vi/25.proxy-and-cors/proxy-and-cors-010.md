# allowCredentials và giới hạn sử dụng origin ký tự đại diện

## 1. Mục tiêu và điểm cần nhớ

Một frontend chạy tại `https://app.example.com` gọi API ở `https://api.example.com`. Hai URL có **origin khác nhau**, nên browser áp dụng CORS (Cross-Origin Resource Sharing) đối với request do JavaScript gửi. Nếu API dùng cookie đăng nhập/session, browser cần biết liệu response có được chia sẻ cho **origin gọi cụ thể** khi request mang credentials hay không.

Trong Spring MVC và Spring WebFlux, `allowCredentials` là cấu hình quan trọng, nhưng đi kèm giới hạn nghiêm ngặt:

> Khi bật `allowCredentials(true)`, **không dùng `allowedOrigins("*")`**. Hãy chỉ định danh sách origin tin cậy hoặc dùng `allowedOriginPatterns(...)` có phạm vi kiểm soát chặt. Với request credentialed, header `Access-Control-Allow-Origin` không được mang giá trị literal `*`.

Ví dụ hợp lệ với frontend được phép:

~~~http
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Vary: Origin
~~~

Ví dụ không hợp lệ đối với browser khi gửi credentials:

~~~http
Access-Control-Allow-Origin: *
Access-Control-Allow-Credentials: true
~~~

Đây không chỉ là khuyến nghị của framework: browser không cho phép credentialed CORS response sử dụng wildcard `*` ở `Access-Control-Allow-Origin`. Spring Framework từ 5.3 còn **kiểm tra cấu hình** và có thể ném `IllegalArgumentException` khi `allowedOrigins` chứa `*` cùng `allowCredentials=true`.

Sau bài này, bạn có thể:

1. Xác định origin theo **scheme + hostname + port**, phân biệt cross-origin với cross-site.
2. Giải thích ý nghĩa `Access-Control-Allow-Origin`, `Access-Control-Allow-Credentials`, `Access-Control-Allow-Methods` và `Access-Control-Allow-Headers`.
3. So sánh `allowedOrigins` và `allowedOriginPatterns` của Spring, hiểu vì sao pattern có thể dùng cùng credentials nhưng wildcard quá rộng vẫn nguy hiểm.
4. Cấu hình CORS cho Spring MVC và WebFlux mà không nhầm annotation/configurer giữa hai stack.
5. Chạy ví dụ Spring Boot 3.3.5/Java 17 với frontend khác port, cookie session, `fetch(credentials: "include")` và preflight.
6. Biết cách tích hợp với Spring Security, CSRF, SameSite/Secure cookie và reverse proxy.
7. Chẩn đoán lỗi browser như “Credential is not supported if the CORS header ... is `*`”, 403 preflight, thiếu cookie hoặc header CORS trùng lặp.

**Phạm vi:** CORS ở web runtime. Bài minh họa cookie session để thấy credentialed request, không xây dựng một hệ thống xác thực người dùng đầy đủ.

## 2. Origin là gì? Vì sao khác site?

Một **origin** được xác định bằng bộ ba **scheme (giao thức), host (tên miền/IP) và port**. Các origin sau khác nhau:

| Trang hoặc API | So với `https://app.example.com` | Lý do |
| --- | --- | --- |
| `https://app.example.com` | Cùng origin | Cùng scheme, host và port mặc định 443 |
| `http://app.example.com` | Khác origin | Scheme `http` khác `https` |
| `https://api.example.com` | Khác origin | Host khác |
| `https://app.example.com:8443` | Khác origin | Port khác |
| `https://app.example.com:443` | Cùng origin về mặt port chuẩn | Cùng HTTPS và port mặc định |
| `http://localhost:5173` so với `http://localhost:8080` | Khác origin | Port 5173 khác 8080 |

**Origin không chứa path:** `https://api.example.com/v1` và `https://api.example.com/v2` thuộc cùng origin, vì chỉ khác path. Bởi vậy `allowedOrigins("https://app.example.com/login")` không phải cách khai báo một origin cụ thể theo path.

**Cross-origin không nhất thiết cross-site.** Ví dụ `http://localhost:5173` và `http://localhost:8080` là khác origin do port nhưng thường được browser coi là **same-site** theo mô hình site hiện hành. Ngược lại, `https://shop.example.com` và `https://third-party.test` là cross-site. CORS kiểm soát quyền đọc response của JavaScript theo **origin**; cookie `SameSite` lại đánh giá **site** và scheme theo quy tắc cookie. Hai hệ thống kiểm soát này liên quan nhưng không đồng nhất.

Browser thường thêm request header `Origin` khi JavaScript gửi cross-origin request:

~~~http
Origin: https://app.example.com
~~~

Server kiểm tra Origin dựa trên chính sách CORS. Không được dùng `Origin` làm bằng chứng nhận dạng user: HTTP client khác browser có thể tự tạo header bất kỳ, còn `Origin: null` có thể xuất hiện từ sandboxed iframe, `file:` hay các ngữ cảnh opaque origin. Với API riêng tư, phải có authentication và authorization độc lập.

## 3. CORS làm gì và không làm gì?

**Same-origin policy** bảo vệ các trang web bằng cách hạn chế JavaScript ở origin A đọc dữ liệu của origin B nếu B chưa cho phép. CORS là cơ chế HTTP để **server B chủ động mở quyền chia sẻ response** cho origin A theo điều kiện định trước.

CORS không phải:

- Một bộ lọc xác thực (authentication): một origin được phép không có nghĩa người gọi đã đăng nhập.
- Một bộ phân quyền (authorization): người dùng A không được đọc đơn hàng của B dù họ cùng origin được tin cậy.
- Một firewall chặn mọi client: `curl`, mobile app hoặc backend-to-backend client không bị chính sách CORS của browser cưỡng chế.
- Biện pháp CSRF đầy đủ: một request “simple” có thể đến server và thay đổi trạng thái trước khi browser quyết định có cho JS đọc response hay không.
- Chứng minh HTTPS hoặc cookie hoạt động: những vấn đề này phụ thuộc TLS, cookie policy và HTTP client.

**CORS chủ yếu kiểm soát quyền truy cập response từ JavaScript trong browser.** Nó có thể ngăn browser gửi actual request sau khi preflight thất bại, nhưng không đảm bảo ngăn mọi request nguy hiểm đến server.

### 3.1. Ba dạng request cần phân biệt

| Loại | Cơ chế | Ví dụ |
| --- | --- | --- |
| Same-origin | Không cần CORS | JS từ `https://app.example.com` gọi API cùng origin |
| Cross-origin “simple” | Browser gửi actual request, sau đó kiểm tra CORS response | GET với các header thuộc danh sách CORS-safelisted |
| Cross-origin có preflight | Browser gửi `OPTIONS` để xin phép trước, rồi mới gửi actual request nếu preflight qua | POST JSON với `Content-Type: application/json`, DELETE, custom header |

Thuật ngữ “simple request” là cách gọi thực hành trong tài liệu CORS; điều kiện chính xác dựa trên method/header/content type safelist, không phải chỉ xem request có ít dữ liệu.

## 4. Các header quyết định credentialed CORS

### 4.1. Header client gửi

~~~http
Origin: https://app.example.com
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type,x-csrf-token
~~~

Trong đó `Access-Control-Request-*` xuất hiện trong **preflight OPTIONS**, nhằm mô tả actual request dự kiến.

### 4.2. Header server phản hồi

~~~http
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Access-Control-Allow-Methods: GET, POST
Access-Control-Allow-Headers: content-type,x-csrf-token
Access-Control-Max-Age: 1800
Vary: Origin, Access-Control-Request-Method, Access-Control-Request-Headers
~~~

Ý nghĩa:

- `Access-Control-Allow-Origin`: chỉ **một origin cụ thể** hoặc wildcard `*` khi không dùng credentials theo trường hợp cho phép; không phải danh sách nhiều origin phân cách dấu phẩy.
- `Access-Control-Allow-Credentials: true`: browser được phép chia sẻ response của credentialed CORS request nếu các điều kiện khác cũng hợp lệ. `true` là giá trị hợp lệ; khi không cho phép, thường **bỏ header**, không phải đặt `false`.
- `Access-Control-Allow-Methods`: những HTTP method được phép trên actual request sau preflight.
- `Access-Control-Allow-Headers`: những request headers được phép, ví dụ `Content-Type` hay `X-CSRF-Token`.
- `Access-Control-Max-Age`: cho phép browser cache **kết quả preflight** trong giới hạn do browser áp dụng; không phải HTTP response cache của dữ liệu API.
- `Vary`: báo cho shared caches rằng response CORS có thể phụ thuộc `Origin` hoặc thông tin preflight, tránh trộn lẫn quyền giữa các origin.

Header `Access-Control-Allow-Origin` phải phù hợp với `Origin` thực tế (hoặc wildcard hợp lệ trong non-credentialed case). Khi cho nhiều origin tin cậy, server **chọn và phản hồi một origin khớp mỗi request**, không xuất:

~~~http
Access-Control-Allow-Origin: https://app.example.com, https://admin.example.com
~~~

Dòng này không phải cú pháp hợp lệ để cho browser truy cập từ hai origin.

### 4.3. `Access-Control-Expose-Headers` là chuyện khác

Browser mặc định chỉ cho JavaScript đọc một số response headers safelisted. Nếu ứng dụng muốn JS đọc response header như `X-Request-Id`, cần cấu hình exposed header tương ứng:

~~~http
Access-Control-Expose-Headers: X-Request-Id
~~~

Spring cho phép dùng `*` trong một số cấu hình `allowedHeaders`, `allowedMethods`, `exposedHeaders` ngay cả khi credentials bật; cách Spring phát header có sắc thái riêng (mục 7). **Không nhầm wildcard của những trường này với wildcard ở `allowedOrigins`:** ràng buộc quan trọng nhất trong bài là `Access-Control-Allow-Origin` không được là `*` khi browser sử dụng credentials.

## 5. allowCredentials nghĩa là gì?

Trong Spring:

~~~java
registry.addMapping("/api/**")
        .allowedOrigins("https://app.example.com")
        .allowCredentials(true);
~~~

`allowCredentials(true)` yêu cầu Spring cho phép request mang thông tin credentials theo CORS, thông qua header `Access-Control-Allow-Credentials: true` khi origin phù hợp.

Credentials mà browser quản lý có thể bao gồm **cookie**, **HTTP authentication credentials** và **TLS client certificate** trong những ngữ cảnh tương ứng. Việc client tự đặt `Authorization` header còn phụ thuộc request configuration, CORS preflight và auth flow; không phải mọi bearer-token API đều cần `allowCredentials(true)`.

Điểm thường nhầm:

- `allowCredentials(true)` **không tự gửi cookie**. Frontend `fetch` phải dùng mode phù hợp (`credentials: "include"` cho cross-origin), cookie cũng phải có Domain/Path/SameSite/Secure phù hợp và không bị browser chặn.
- `allowCredentials(true)` **không tự thiết lập session**, không tạo login và không sinh CSRF token.
- `allowCredentials(false)` hoặc không cấu hình không có nghĩa mọi request HTTP bị server từ chối; CORS là cơ chế browser sử dụng khi truy cập dữ liệu cross-origin.
- Nếu gửi cookie đến API nhưng API trả `Access-Control-Allow-Origin: *`, browser vẫn **chặn JavaScript truy cập response**. Cookie có thể đã được gửi ở actual simple request trước khi browser kiểm tra response CORS.
- CORS cho phép **origin**, không phân biệt user cụ thể. Mọi trang/mã JavaScript được chạy trên origin được tin đều nhận được quyền theo chính sách đó.

### 5.1. Vai trò của fetch credentials mode

~~~javascript
// Mặc định: credentials: "same-origin"
// Không tự gửi cookie trong cross-origin fetch.
fetch("https://api.example.com/me");

// Yêu cầu browser gửi/nhận cookie cho cross-origin request,
// trong phạm vi cookie policy hiện hành.
fetch("https://api.example.com/me", {
  credentials: "include"
});
~~~

Với `XMLHttpRequest` dùng `xhr.withCredentials = true` trước khi `send()`. Với `EventSource`, có tùy chọn `withCredentials: true` cho request cross-origin phù hợp.

**`credentials: "include"` không vượt qua chính sách browser.** Cookie có thể bị chặn do SameSite, Secure, Domain, Path, cross-site tracking restrictions, privacy settings hoặc third-party cookie blocking. Có `Access-Control-Allow-Credentials: true` không đảm bảo browser đã gửi cookie thành công.

### 5.2. Preflight có gửi cookie không?

Về mô hình chuẩn và tài liệu Spring Security, **CORS preflight OPTIONS không mang cookie session `JSESSIONID` như actual request**. Browser kiểm tra quyền cross-origin trước khi gửi actual request mang credentials. Vì vậy preflight bị filter authentication chặn (401/403/redirect login) là lỗi cấu hình rất phổ biến.

Quy trình:

~~~text
Frontend app.example.com
    |
    | OPTIONS /api/order
    | Origin: https://app.example.com
    | Access-Control-Request-Method: POST
    | Access-Control-Request-Headers: content-type,x-csrf-token
    v
API / CORS layer
    |
    | Chỉ cho origin + method + headers đã cấu hình
    | Access-Control-Allow-Origin: https://app.example.com
    | Access-Control-Allow-Credentials: true
    v
Browser chấp nhận preflight?
    |
    +-- Không -> DỪNG actual request, báo CORS error
    |
    '-- Có -> POST actual request có thể mang session cookie
               (nếu fetch và cookie policy cho phép)
               |
               v
           AuthN/AuthZ/CSRF/Business logic
               |
               v
           Response tiếp tục cần CORS headers phù hợp
~~~

Preflight hợp lệ **không tự chứng minh** actual request sẽ được 200. Actual request có thể bị 401/403 vì authentication/authorization/CSRF, và response lỗi cũng cần CORS headers chính xác để frontend đọc được chi tiết lỗi phù hợp.

## 6. Vì sao wildcard origin và credentials xung đột?

### 6.1. Cấu hình sai

~~~java
// Sai khi kết hợp credentialed CORS:
registry.addMapping("/api/**")
        .allowedOrigins("*")
        .allowCredentials(true);
~~~

Nếu framework cho phát cả hai header:

~~~http
Access-Control-Allow-Origin: *
Access-Control-Allow-Credentials: true
~~~

browser sẽ không cho JavaScript của credentialed request đọc response. MDN thường báo lỗi dạng:

~~~text
Reason: Credential is not supported if the CORS header
'Access-Control-Allow-Origin' is '*'
~~~

Spring Framework 5.3+ cung cấp `CorsConfiguration.validateAllowCredentials()`. Khi cấu hình `allowedOrigins` chứa `*` và `allowCredentials=true` được kiểm tra/áp dụng, Spring có thể ném `IllegalArgumentException` thay vì phát một kết hợp CORS sai chuẩn. **Thời điểm phát hiện** phụ thuộc đường cấu hình và thời điểm handler/CORS processor chạy; đừng mặc định mọi dự án đều hỏng ngay lúc startup.

### 6.2. Cấu hình đúng cho ít origin

~~~java
registry.addMapping("/api/**")
        .allowedOrigins(
                "https://app.example.com",
                "https://admin.example.com")
        .allowedMethods("GET", "POST")
        .allowCredentials(true);
~~~

Mỗi request được kiểm tra theo một origin cụ thể. Với:

~~~http
Origin: https://admin.example.com
~~~

response hợp lệ có thể chứa:

~~~http
Access-Control-Allow-Origin: https://admin.example.com
Access-Control-Allow-Credentials: true
Vary: Origin
~~~

Không có cách an toàn/đúng chuẩn đơn giản nào để sử dụng literal `*` ở `Access-Control-Allow-Origin` cùng credentials. Đừng cố khắc phục bằng cách tắt CORS trên browser, thêm `mode: "no-cors"` hoặc dùng extension bỏ kiểm tra origin: đó không phải giải pháp triển khai thực tế.

### 6.3. Nếu không cần cookie/credentials

Với API dữ liệu công khai, không cần client credentials, có thể chấp nhận mọi origin:

~~~java
registry.addMapping("/public/**")
        .allowedOrigins("*")
        .allowedMethods("GET");
~~~

Trong trường hợp non-credentialed, response `Access-Control-Allow-Origin: *` có thể hợp lệ. Frontend nên sử dụng `credentials: "omit"` khi gọi API public nếu không cần bất kỳ credentials nào.

**Không nên để “API public” chứa dữ liệu nhạy cảm hoặc thao tác thay đổi trạng thái mà không cần authentication.** CORS public chỉ nói rằng browser được phép đọc dữ liệu từ origin khác; nó không thay thế security policy.

## 7. allowedOrigins so với allowedOriginPatterns

### 7.1. allowedOrigins: danh sách origin cụ thể

~~~java
.allowedOrigins("https://app.example.com", "https://admin.example.com")
~~~

Đây thường là lựa chọn dễ review và an toàn nhất khi tập origin tin cậy hữu hạn. Giá trị gồm **scheme, host và port** (nếu khác port mặc định), không có path. Kiểm tra chính xác từng môi trường: dev, staging, production có thể dùng các origin khác nhau.

Lưu ý:

- `https://app.example.com` khác `http://app.example.com`.
- `http://localhost:5173` khác `http://localhost:3000`.
- `https://app.example.com/` có dấu slash cuối không nên dùng như biểu diễn origin chuẩn.
- Danh sách không phải regex và không chấp nhận wildcard host dạng `https://*.example.com` theo semantics của `allowedOriginPatterns`.

### 7.2. allowedOriginPatterns: khớp theo mẫu, nhưng phản hồi origin thực

Spring Framework hỗ trợ:

~~~java
.allowedOriginPatterns("https://*.example.com")
.allowCredentials(true)
~~~

Theo `CorsConfiguration`, khi pattern khớp `https://team.example.com`, Spring phản hồi:

~~~http
Access-Control-Allow-Origin: https://team.example.com
Access-Control-Allow-Credentials: true
~~~

Thay vì phản hồi literal `*` hoặc toàn bộ pattern. Do đó cách này **có thể hoạt động cùng credentials** về mặt kỹ thuật.

Các ví dụ pattern được API Spring mô tả:

~~~text
https://*.example.com
https://*.example.com:[8080,8081]
https://*.example.com:[*]
~~~

Các mẫu trên có thể khớp subdomain và các port đã quy định. Đây là cú pháp **pattern Spring**, không phải regex tùy ý và không phải path pattern. Đừng dùng `allowedOriginPatterns` chỉ để gắn dấu slash hoặc query string vào origin.

**Rủi ro lớn:** nếu một subdomain bất kỳ trong `*.example.com` do khách hàng, bên thứ ba hoặc user kiểm soát, đó **không phải tập origin tin cậy** chỉ vì cùng domain gốc. Một subdomain bị takeover, trang lưu trữ nội dung người dùng hoặc tài khoản tenant khác cũng có thể được quyền đọc dữ liệu CORS có credentials.

### 7.3. Pattern "*" với credentials: kỹ thuật hợp lệ không đồng nghĩa an toàn

~~~java
// Spring có thể khớp mọi origin và trả về origin thực tế.
// TUYỆT ĐỐI KHÔNG DÙNG cho API bí mật/session như chính sách rộng mặc định.
.allowedOriginPatterns("*")
.allowCredentials(true)
~~~

Cách này có thể vượt qua rào cản “không phát literal `*`” vì Spring **echo origin thực tế**. Nhưng nó đồng nghĩa **mọi website đều có thể được phép đọc response của credentialed request** nếu browser gửi credentials. Về bảo mật, đây thường là cách cấu hình sai nghiêm trọng cho API session/cookie.

**Quy tắc:** khi có credentials, chỉ allow origin mà bạn **kiểm soát và tin tưởng đầy đủ JavaScript chạy trên đó**. Nếu nhiều tenant có hostname khác nhau, cân nhắc danh sách đã xác minh trong DB/config, có giới hạn và chính sách ownership rõ ràng. Không phản chiếu `Origin` một cách vô điều kiện thành header CORS.

### 7.4. Đừng nhầm wildcard của các thuộc tính khác

Theo tài liệu Spring Framework, khi `allowCredentials=true`:

- `allowedOrigins("*")`: **không hợp lệ**; phải dùng origin cụ thể hoặc pattern.
- `allowedOriginPatterns("https://*.example.com")`: có thể hợp lệ; Spring trả **origin đã khớp**.
- `allowedMethods("*")`: Spring xử lý bằng cách phản hồi method được yêu cầu trong preflight thay vì dùng wildcard `*` khi có credentials.
- `allowedHeaders("*")`: Spring có thể phản hồi headers mà preflight yêu cầu thay vì literal `*` khi có credentials.
- `exposedHeaders("*")`: Spring có thể phát literal `*` ngay cả khi credentials bật do giới hạn biết trước toàn bộ response headers; đừng dựa vào hành vi đó nếu cần tương thích chặt giữa browser hoặc truy cập header cụ thể.

Dù API cho dùng wildcard method/header, **least privilege** vẫn khuyến khích liệt kê method và header thật sự cần. Đặc biệt đừng “sửa CORS nhanh” bằng cách đổi mọi mục thành `*` khi chưa kiểm tra threat model.

## 8. Lab chạy được: Spring MVC, session cookie và hai origin localhost

Dựng một backend Spring Boot 3.3.5/Java 17 tại `http://localhost:8080` và một frontend HTML chạy trên `http://localhost:5173`. Khác port nghĩa là **cross-origin**, nên browser áp CORS. Tuy nhiên chúng cùng hostname `localhost` và scheme HTTP, nên thường là **same-site**: demo cookie có thể hoạt động với SameSite=Lax trong môi trường local, không cần tạo TLS/cookie cross-site phức tạp.

**Bài lab không có login và không có security filter.** Giá trị `counter` trong session chỉ minh họa cookie round-trip. Không đưa endpoint thay đổi trạng thái không có CSRF/authentication này vào production.

### 8.1. Cấu trúc project

~~~text
cors-credentials-demo/
├── pom.xml
├── frontend/
│   └── index.html
└── src/main/
    ├── java/com/example/corsdemo/
    │   ├── CorsDemoApplication.java
    │   ├── CorsConfig.java
    │   └── CounterController.java
    └── resources/
        └── application.properties
~~~

### 8.2. pom.xml

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
    <artifactId>cors-credentials-demo</artifactId>
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

`spring-boot-starter-web` cung cấp MVC, embedded Tomcat và Jackson. Dự án không cần thư viện CORS riêng; `WebMvcConfigurer` và `CorsRegistry` thuộc Spring Web MVC.

### 8.3. application.properties

**Tệp `src/main/resources/application.properties`:**

~~~properties
server.port=8080
server.address=127.0.0.1

# Cookie session mặc định của Servlet container dùng cho lab.
# Không thay đổi thành SameSite=None khi đang dùng HTTP localhost.
server.servlet.session.timeout=20m
~~~

`server.address=127.0.0.1` chỉ cho backend nghe trên loopback local, hạn chế vô ý phơi port ra mạng. Trong container/Kubernetes, cách bind sẽ khác; ứng dụng production cần mạng và firewall hợp lý. Mặc định tên cookie phiên Servlet thường là `JSESSIONID` nhưng có thể đổi theo config; quan sát `Set-Cookie` thực tế thay vì hardcode.

### 8.4. Lớp Spring Boot

**Tệp `src/main/java/com/example/corsdemo/CorsDemoApplication.java`:**

~~~java
package com.example.corsdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CorsDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(CorsDemoApplication.class, args);
    }
}
~~~

### 8.5. CORS configuration: chỉ tin frontend 5173

**Tệp `src/main/java/com/example/corsdemo/CorsConfig.java`:**

~~~java
package com.example.corsdemo;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class CorsConfig implements WebMvcConfigurer {

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
                .allowedOrigins("http://localhost:5173")
                .allowedMethods("GET", "POST")
                .allowedHeaders("Content-Type")
                .allowCredentials(true)
                .maxAge(1800);
    }
}
~~~

Giải thích:

- `addMapping("/api/**")` áp CORS cho nhóm API đang thử, không tự mở mọi endpoint.
- `allowedOrigins("http://localhost:5173")` cho phép **chính xác frontend dev**; không cho `http://localhost:3000` hoặc `http://127.0.0.1:5173` vì host/port khác.
- `allowedMethods("GET", "POST")` khai báo actual methods mà browser có thể yêu cầu.
- `allowedHeaders("Content-Type")` cho phép preflight của POST JSON trong frontend; các header CORS-safelisted được browser xử lý theo quy tắc riêng.
- `allowCredentials(true)` yêu cầu response CORS được phép dùng cookie và các credentials hợp lệ.
- `maxAge(1800)` cho phép cache preflight tối đa theo chính sách browser; không cache body JSON.

**Không cần thêm `@EnableWebMvc`**: dùng `WebMvcConfigurer` để thêm mapping mà vẫn giữ auto-configuration MVC của Spring Boot.

### 8.6. REST controller lưu counter trong HttpSession

**Tệp `src/main/java/com/example/corsdemo/CounterController.java`:**

~~~java
package com.example.corsdemo;

import java.util.Map;

import jakarta.servlet.http.HttpSession;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/counter")
public class CounterController {

    @GetMapping
    public Map<String, Integer> read(HttpSession session) {
        Integer count = (Integer) session.getAttribute("count");
        return Map.of("count", count == null ? 0 : count);
    }

    @PostMapping
    public Map<String, Integer> increment(HttpSession session) {
        Integer previous = (Integer) session.getAttribute("count");
        int count = (previous == null ? 0 : previous) + 1;
        session.setAttribute("count", count);
        return Map.of("count", count);
    }
}
~~~

`GET /api/counter` trả giá trị hiện có, không tăng; `POST /api/counter` tăng và lưu giá trị trong session. Spring MVC quản lý `HttpSession` và cookie `JSESSIONID` ở browser. Bộ đếm minh họa không phải atomic counter khi nhiều POST đồng thời; session không phải cơ sở dữ liệu giao dịch.

Không hiển thị session ID trong JSON, vì session cookie/ID có thể là bearer secret. Đối với một hệ thống thật, POST thay đổi trạng thái **phải có authentication/authorization và CSRF protection phù hợp** khi dựa trên cookie. Lab tách riêng chỉ nhằm quan sát CORS; không dùng nó như hướng dẫn vô hiệu hóa CSRF trong production.

### 8.7. Frontend khác origin

**Tệp `frontend/index.html`:**

~~~html
<!doctype html>
<html lang="vi">
<head>
  <meta charset="UTF-8">
  <title>CORS credentials demo</title>
</head>
<body>
  <h1>Thử CORS với session cookie</h1>
  <button id="read">Đọc counter</button>
  <button id="increment">Tăng counter</button>
  <pre id="output">Chưa gọi API.</pre>

  <script>
    const apiUrl = "http://localhost:8080/api/counter";
    const output = document.querySelector("#output");

    async function callApi(method) {
      const options = {
        method: method,
        credentials: "include"
      };
      if (method === "POST") {
        options.headers = { "Content-Type": "application/json" };
        options.body = "{}";
      }

      try {
        const response = await fetch(apiUrl, options);
        if (!response.ok) {
          throw new Error("HTTP " + response.status);
        }
        output.textContent = JSON.stringify(await response.json());
      } catch (error) {
        output.textContent = String(error);
      }
    }

    document.querySelector("#read").addEventListener(
      "click", () => callApi("GET"));
    document.querySelector("#increment").addEventListener(
      "click", () => callApi("POST"));
  </script>
</body>
</html>
~~~

**Tại sao POST có preflight?** Frontend đặt `Content-Type: application/json`, không nằm trong những giá trị Content-Type safelisted cho CORS simple request, nên browser thường gửi OPTIONS trước POST. GET không thêm custom header, nên thường không cần preflight. Cả hai request vẫn cần response CORS headers phù hợp.

**Tại sao `credentials:"include"` ở cả hai?** Nếu frontend không yêu cầu credentials khi gọi cross-origin API, browser không tự gửi session cookie nên mỗi lần gọi có thể tạo session mới hoặc không đọc được counter cũ. Dù dùng `include`, cookie vẫn chịu chính sách browser.

### 8.8. Khởi động cả hai origin

Từ thư mục `cors-credentials-demo`, với Java 17+ và Maven:

~~~bash
mvn spring-boot:run
~~~

Mở một terminal khác tại **cùng thư mục gốc**. Nếu có Python 3:

~~~bash
python3 -m http.server 5173 --bind 127.0.0.1 --directory frontend
~~~

Trên Windows có thể dùng:

~~~powershell
py -m http.server 5173 --bind 127.0.0.1 --directory frontend
~~~

Mở đúng:

~~~text
http://localhost:5173/
~~~

Đối với frontend server lắng nghe ở `127.0.0.1`, URL `localhost` thường phân giải tới loopback thích hợp; nếu máy ưu tiên IPv6 nhưng server chỉ nghe IPv4, dùng `http://127.0.0.1:5173/` **và cập nhật đúng allowedOrigins** vì `127.0.0.1` và `localhost` là hai origin khác nhau. Để tránh lệch origin trong bài lab, có thể đổi `--bind localhost` hoặc cấu hình Python server cho địa chỉ phù hợp. Đừng mở file bằng `file://` vì origin/credential policy của `file:` khác HTTP origin bình thường.

Nhấn **Tăng counter** hai lần rồi **Đọc counter**:

~~~text
POST /api/counter -> {"count":1}
POST /api/counter -> {"count":2}
GET  /api/counter -> {"count":2}
~~~

Đây là kết quả **khi browser nhận và gửi lại cùng session cookie**. Giá trị có thể khác nếu cookie jar đã có session từ lần thử trước, nếu bạn mở nhiều tab hoặc có request đồng thời. Kiểm tra Network tab của DevTools để xác nhận thực tế.

## 9. Kiểm tra chính xác bằng curl: preflight, cookie, origin bị từ chối

`curl` là HTTP client, **không tự thực thi chính sách CORS của browser**. Dù vậy, nó hữu ích để kiểm tra headers và status của server. Muốn biết JavaScript trong browser có đọc được response hay không, vẫn phải test browser thực.

### 9.1. Preflight hợp lệ

~~~bash
curl -i -X OPTIONS "http://localhost:8080/api/counter" \
  -H "Origin: http://localhost:5173" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: content-type"
~~~

Khi Spring MVC xử lý thành công, cần tìm những header tương đương:

~~~http
Access-Control-Allow-Origin: http://localhost:5173
Access-Control-Allow-Credentials: true
Access-Control-Allow-Methods: GET,POST
Access-Control-Allow-Headers: content-type
Access-Control-Max-Age: 1800
~~~

Cách viết khoảng trắng/chữ hoa/thứ tự, status thành công (thường 200 với Spring MVC) và danh sách header `Vary` có thể thay đổi. Đừng so nguyên văn từng byte của response; kiểm tra **ý nghĩa các header**.

**Preflight không cần gửi `JSESSIONID`.** Nếu có Spring Security, phải cho lớp CORS xử lý OPTIONS trước khi filter xác thực chặn nó.

### 9.2. Actual POST với cookie jar

~~~bash
curl -i \
  -c cors-cookies.txt \
  -X POST "http://localhost:8080/api/counter" \
  -H "Origin: http://localhost:5173" \
  -H "Content-Type: application/json" \
  -d "{}"
~~~

Kỳ vọng JSON chứa `"count":1` nếu session mới. Quan sát `Set-Cookie`, thường có cookie `JSESSIONID`. Lệnh curl này **không tự chạy preflight**; bạn đã gửi POST thật một cách độc lập.

Gọi lại cùng cookie:

~~~bash
curl -i \
  -b cors-cookies.txt \
  -H "Origin: http://localhost:5173" \
  "http://localhost:8080/api/counter"
~~~

Kỳ vọng count được giữ. Không nên lấy việc curl gửi được cookie làm bằng chứng browser sẽ cho JS đọc response: curl không áp SameSite, CORS, third-party restrictions giống browser.

### 9.3. Preflight từ origin bị từ chối

~~~bash
curl -i -X OPTIONS "http://localhost:8080/api/counter" \
  -H "Origin: http://localhost:9999" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: content-type"
~~~

Spring thường từ chối request CORS không được phép (ví dụ 403 “Invalid CORS request”), hoặc không trả các header cho phép; chi tiết phụ thuộc lớp xử lý. Điều phải đúng là **không xuất CORS grant** cho origin `localhost:9999` trong cấu hình lab.

Một request `curl` thường vẫn có thể gọi controller nếu server không chặn bằng cơ chế khác; điều này không phải lỗi CORS, vì CORS không phải tường lửa.

### 9.4. Khác origin và thiếu credentials

Sửa tạm frontend thành:

~~~javascript
fetch("http://localhost:8080/api/counter", {
  method: "GET",
  credentials: "omit"
});
~~~

Khi không gửi cookie, server có thể thấy session khác, khiến count trở về 0. Điều này độc lập với việc server vẫn cho origin `localhost:5173`. Nếu muốn phục hồi demo, trả lại `credentials:"include"`.

### 9.5. Thử cấu hình sai một cách có chủ đích

**Chỉ thực hiện trong bản thử nghiệm riêng**, không thay đổi chính sách production:

~~~java
// Ví dụ cấu hình SAI để quan sát validation:
registry.addMapping("/api/**")
        .allowedOrigins("*")
        .allowCredentials(true);
~~~

Khi có request CORS, Spring có thể báo lỗi `IllegalArgumentException` liên quan `allowCredentials`/wildcard hoặc fail tại điểm cấu hình được validate. Nếu một proxy độc lập phát `Access-Control-Allow-Origin: *` cùng `Access-Control-Allow-Credentials: true`, browser sẽ đưa ra CORS error. Sửa lại danh sách origin cụ thể thay vì tắt security.

## 10. @CrossOrigin trên controller: khi nào phù hợp?

Nếu chỉ một controller/method cho phép origin riêng, có thể dùng annotation:

~~~java
@CrossOrigin(
    origins = "https://app.example.com",
    allowCredentials = "true"
)
@GetMapping("/api/profile")
public ProfileView profile() {
    return new ProfileView("Public display name");
}
~~~

Đây là **đoạn minh họa**, không phải file Java độc lập: cần định nghĩa `ProfileView`, đặt trong `@RestController` cùng imports phù hợp. Điểm chính là `@CrossOrigin.allowCredentials` nhận chuỗi `"true"`; nó khác fluent API `.allowCredentials(true)` của `CorsRegistration`.

Ví dụ dùng pattern:

~~~java
@CrossOrigin(
    originPatterns = "https://*.trusted.example",
    allowCredentials = "true"
)
~~~

Cũng chỉ nên áp dụng khi **mọi hostname phù hợp đều thực sự đáng tin**. Không dùng `@CrossOrigin(allowCredentials = "true")` mà bỏ `origins`/`originPatterns` rồi tưởng Spring sẽ tự biết origin an toàn: default `@CrossOrigin` thường cho phép mọi origin, không được kết hợp với credentials theo kiểu wildcard này.

### 10.1. Global + local CORS có thể kết hợp

Spring hỗ trợ cấu hình global trên HandlerMapping cùng `@CrossOrigin` ở controller. Quy tắc combine thường mang tính **cộng danh sách** cho allowed origins, methods và headers; một số thuộc tính đơn trị như `allowCredentials` và `maxAge` có thể được giá trị local override.

Hậu quả: nếu bạn có global `allowedOrigins("*")` rồi thêm annotation local `allowCredentials="true"`, kết quả combine có thể tạo wildcard/credential invalid. Đừng chỉ đọc annotation rồi kết luận policy cuối cùng; phải kiểm tra global + local + filter + proxy config đang thực sự áp dụng.

**Tối ưu bảo trì:** trong một project, chọn một vị trí cấu hình CORS rõ ràng (ví dụ `WebMvcConfigurer` cho cả `/api/**`, hoặc Security CORS source khi cần xử lý trước auth) thay vì rải nhiều cách cấu hình chồng lấn.

## 11. Spring WebFlux: cùng quy tắc, khác configurer và session API

Trong WebFlux, dùng `org.springframework.web.reactive.config.WebFluxConfigurer` và `org.springframework.web.reactive.config.CorsRegistry`:

~~~java
package com.example.reactivecors;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.config.CorsRegistry;
import org.springframework.web.reactive.config.WebFluxConfigurer;

@Configuration
public class ReactiveCorsConfig implements WebFluxConfigurer {

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
                .allowedOrigins("http://localhost:5173")
                .allowedMethods("GET", "POST")
                .allowedHeaders("Content-Type")
                .allowCredentials(true)
                .maxAge(1800);
    }
}
~~~

**Đoạn trên là cấu hình đầy đủ của một project WebFlux**, nhưng **không được thêm vào project Spring MVC** của mục 8, vì đó là hai stack khác nhau. Để thử riêng WebFlux, tạo project thứ hai với `spring-boot-starter-webflux` và không kèm `spring-boot-starter-web`; thêm controller reactive và frontend tương ứng.

Ví dụ controller WebFlux **độc lập khi được đặt trong dự án WebFlux**:

~~~java
package com.example.reactivecors;

import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.WebSession;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/counter")
public class ReactiveCounterController {

    @GetMapping
    public Mono<Map<String, Integer>> read(WebSession session) {
        int count = session.getAttributeOrDefault("count", 0);
        return Mono.just(Map.of("count", count));
    }

    @PostMapping
    public Mono<Map<String, Integer>> increment(WebSession session) {
        int previous = session.getAttributeOrDefault("count", 0);
        int count = previous + 1;
        session.getAttributes().put("count", count);
        return Mono.just(Map.of("count", count));
    }
}
~~~

**WebFlux dùng `WebSession`, không phải `jakarta.servlet.http.HttpSession`.** Trong WebFlux reactive, session cookie mặc định thường tên `SESSION` tùy cấu hình, không phải mặc định Servlet `JSESSIONID`. CORS credential semantics **không đổi**: vẫn không được `allowedOrigins("*")` khi `allowCredentials(true)`.

Nếu dùng WebFlux functional routes hoặc cần CORS ở filter level, Spring cung cấp `CorsWebFilter` và `org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource`. Đừng nhầm class reactive này với `org.springframework.web.cors.UrlBasedCorsConfigurationSource` của Servlet/MVC.

### 11.1. Nếu application mang cả hai starter

Với Spring Boot 3.3, nếu classpath có cả `spring-boot-starter-web` và `spring-boot-starter-webflux`, Boot thông thường chọn **Servlet MVC** theo auto-configuration. Việc dùng `WebClient` không tự biến controller thành WebFlux. Luôn xác định stack đang chạy trước khi chọn `WebMvcConfigurer` hay `WebFluxConfigurer`.

## 12. Spring Security: CORS phải được xử lý trước authentication

Khi có Spring Security, một lỗi dễ gặp là preflight OPTIONS chưa có session cookie nhưng security filter đã yêu cầu login, dẫn tới 401/403 hoặc redirect trước khi CORS được đánh giá.

**Nguyên tắc:** đưa CORS handling vào đúng thứ tự **trước Spring Security authentication**. Spring Security có tích hợp CORS; khi dùng Spring MVC và có cấu hình CORS ở MVC, có thể bật CORS integration bằng:

~~~java
// Đoạn cấu hình bổ sung khi project có Spring Security.
// Đây không phải một file chạy độc lập.
@Bean
SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
    http.cors(Customizer.withDefaults())
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated());
    return http.build();
}
~~~

Các import cần có khi đưa vào lớp `@Configuration`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
~~~

Snippet này minh họa `http.cors(Customizer.withDefaults())`. Khi dùng MVC và không định nghĩa `CorsConfigurationSource` riêng, Spring Security có thể dùng cấu hình CORS của Spring MVC. Với nhiều `SecurityFilterChain` hoặc nhiều CORS source, cần chỉ định source cho chain chính xác.

**Không copy snippet này vào project lab mục 8 mà chờ POST hoạt động y nguyên:** thêm Spring Security sẽ kích hoạt authentication và CSRF protection. Một frontend state-changing POST phải có login/session và CSRF token hợp lệ, hoặc sử dụng một thiết kế auth stateless được bảo vệ theo cơ chế khác. **Không tắt CSRF chỉ để làm CORS “hết lỗi”** trên ứng dụng có session cookie.

### 12.1. Preflight không có cookie nhưng actual request phải xác thực

Ví dụ trình tự chính xác:

~~~text
OPTIONS /api/account  (preflight)
  -> CORS kiểm tra Origin, method, headers
  -> được phép; KHÔNG cần JSESSIONID

GET/POST /api/account (actual)
  -> browser có thể gửi JSESSIONID nếu credentials policy cho phép
  -> Spring Security xác thực, phân quyền, kiểm CSRF nếu áp dụng
  -> controller/service xử lý
  -> response có CORS headers đúng để frontend đọc
~~~

Không áp logic “mọi OPTIONS đều là người dùng vô danh nên cấm” lên preflight. Đồng thời không bỏ authentication với actual request chỉ vì origin đã được allow.

### 12.2. Spring Security reactive

Với Spring Security WebFlux, dùng cơ chế reactive phù hợp (ví dụ `CorsWebFilter`/reactive CORS configuration source và tích hợp `ServerHttpSecurity.cors(...)`). Không tái sử dụng Servlet `CorsFilter` hoặc `HttpSecurity` cho WebFlux. Phải bảo đảm CORS đứng trước reactive security filters và kiểm tra preflight/actual request tách biệt.

## 13. Cookie, SameSite và Secure: điều kiện độc lập với allowCredentials

Cấu hình CORS đúng là một phần của yêu cầu. Browser còn quyết định có gửi/nhận cookie không:

| Thuộc tính | Tác dụng | Lưu ý |
| --- | --- | --- |
| `Domain` | Host hoặc domain cookie áp dụng | Cookie host-only của `api.example.com` không tự dùng cho `other.example.com` |
| `Path` | Đường dẫn URL phù hợp | Cookie `Path=/api` không gửi cho đường dẫn không thuộc scope |
| `Secure` | Yêu cầu kết nối an toàn theo browser | Cookie cross-site với `SameSite=None` cần `Secure` theo browser hiện đại |
| `HttpOnly` | Hạn chế JavaScript đọc cookie qua `document.cookie` | Browser vẫn có thể tự gửi cookie theo chính sách |
| `SameSite=Strict` | Hạn chế mạnh request trong cross-site context | Có thể ảnh hưởng SSO/navigation |
| `SameSite=Lax` | Cho phép một số cross-site navigations nhưng hạn chế nhiều request cross-site subresource/fetch | Thường không đủ cho cookie third-party fetch |
| `SameSite=None` | Cho phép cookie trong ngữ cảnh cross-site nếu đáp ứng điều kiện | Đi kèm `Secure` và vẫn chịu third-party cookie restrictions |

**Hai ví dụ khác nhau:**

- `http://localhost:5173` → `http://localhost:8080`: cross-origin vì port khác, nhưng thường same-site; cookie dev có thể hoạt động với thiết lập đơn giản trong môi trường HTTP local.
- `https://frontend.brand-a.example` → `https://api.brand-b.test`: cross-site. Khi cần cookie cross-site, thường phải dùng `SameSite=None; Secure` qua HTTPS và vẫn chịu giới hạn cookie bên thứ ba của browser.

Không có cấu hình `allowCredentials=true` nào vượt qua third-party cookie blocking. Nếu kiến trúc phụ thuộc third-party cookies, cần đánh giá cơ chế login, top-level navigation, same-site deployment, token flow hoặc chính sách browser mới, thay vì cố phản hồi `Access-Control-Allow-Origin: *`.

### 13.1. Đừng nhầm credentials và authorization

Một endpoint dùng bearer token do JavaScript chủ động đặt `Authorization: Bearer ...` có thể cần preflight cho header `Authorization`:

~~~http
Access-Control-Request-Headers: authorization
~~~

Nhưng câu hỏi có cần `allowCredentials(true)` hay không vẫn phụ thuộc **cách client sử dụng Fetch credentials mode và các credentials được browser quản lý**. Không phải cứ có header `Authorization` trong API là bắt buộc phải bật credentialed CORS bằng cookie semantics. Hãy thiết kế CORS policy dựa trên cơ chế xác thực thực tế và yêu cầu frontend.

### 13.2. Session cookie khác đọc cookie bằng JS

`HttpOnly` cookie không được JavaScript đọc qua `document.cookie`, nhưng browser vẫn có thể gửi nó trong `fetch(credentials:"include")` nếu policy cho phép. Đó thường là hành vi mong muốn với session cookie: frontend gọi API, server quyết định phiên từ cookie, còn JS không biết secret session ID.

## 14. CORS không thay thế CSRF protection

Một trang độc hại có thể gây trình duyệt gửi request đến API theo một số cơ chế form/navigation/simple request ngay cả khi nó **không được đọc response** vì CORS. Với session cookie, nếu browser gửi cookie và server xử lý state-changing operation, tác động CSRF vẫn có thể xảy ra.

Ví dụ mô hình rủi ro:

~~~text
Victim đã đăng nhập api.example.com
    |
    v
Trang không đáng tin tạo POST đến api.example.com
    |
    v
Browser có thể gửi request theo cookie policy
    |
    v
Server xử lý chuyển tiền/đổi email nếu thiếu CSRF/auth checks
    |
    v
Browser chặn JS đọc response không đủ để đảo ngược giao dịch
~~~

Các biện pháp bổ sung:

1. Dùng CSRF token với các request thay đổi trạng thái khi dựa trên cookie/session.
2. Kiểm tra authentication và authorization ở server, không dựa vào `Origin` một mình.
3. Thiết lập SameSite phù hợp; không xem nó như thay thế vô điều kiện cho CSRF protection.
4. Cân nhắc kiểm tra `Origin`/`Referer` ở những thao tác nhạy cảm khi thích hợp; chúng là tín hiệu bổ sung và có thể vắng trong một số hoàn cảnh.
5. Tránh thay đổi trạng thái quan trọng bằng GET; thiết kế method semantics đúng.
6. Đặt `Content-Type` và JSON parsing chặt chẽ cho API, nhưng vẫn không xem preflight là biện pháp CSRF độc lập tuyệt đối.

`allowCredentials=true` tăng phạm vi tin cậy đối với JavaScript ở các origin được allow. Do đó origin được phép phải được kiểm soát an toàn (chống XSS, subdomain takeover, nội dung do user đăng, third-party scripts). **Một XSS trên origin tin cậy có thể dùng CORS để đọc dữ liệu API của user.**

## 15. Proxy, gateway, CDN: chỉ một nơi làm chủ CORS

Trong hệ thống thật, CORS có thể được cấu hình ở:

- Spring MVC/WebFlux (HandlerMapping).
- Spring Security CORS integration/filter.
- API gateway hoặc NGINX/Ingress reverse proxy.
- CDN/edge function.
- Một middleware bên ngoài.

Nếu nhiều tầng đều thêm:

~~~http
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Origin: *
~~~

hoặc gộp thành danh sách phân cách dấu phẩy, browser thường coi response không hợp lệ. **Chọn một nơi authoritative** để tạo CORS headers hoặc phối hợp chặt để không trùng.

### 15.1. Những câu hỏi cần kiểm tra

1. Browser gửi `Origin` nào đến edge? Edge có chuyển nguyên `Origin` hay lọc?
2. Preflight `OPTIONS` được edge trả ngay hay chuyển cho Spring? Nếu edge xử lý, policy edge có trùng server không?
3. `Access-Control-Allow-Credentials` có được thêm cho đúng route và origin không?
4. `Vary: Origin` có được giữ đúng trong cache? Cache key có bao gồm Origin/variants nếu cần?
5. Header `Set-Cookie` có bị proxy rewrite Domain/Path/SameSite/Secure không?
6. Proxy có chặn `OPTIONS`, phát 302 login hoặc 404 trước khi request đến Spring không?
7. Header CORS trên response lỗi 401/403/500 có giống chính sách các response thành công không?
8. Có tầng nào tự echo mọi `Origin` rồi đặt `Allow-Credentials: true` không? Đó là nguy cơ lộ response cho các website không được tin.

CORS là chính sách **phía server đáp cho browser**, không phải chuyện proxy tự có trust khi nhìn thấy `Origin`. Người gọi ngoài browser có thể tự tạo header này; backend cần authorization riêng.

## 16. Checklist triển khai production

- [ ] Liệt kê rõ frontend origins cần truy cập API theo từng môi trường: scheme, host, port.
- [ ] Khi có cookie/session, dùng `allowCredentials=true` chỉ với tập origin thực sự đáng tin.
- [ ] Không kết hợp `allowedOrigins("*")` với `allowCredentials(true)`.
- [ ] Nếu dùng `allowedOriginPatterns`, review từng pattern; không dùng wildcard khớp origin do user/tenant không đáng tin kiểm soát.
- [ ] Không echo `Origin` vô điều kiện thành `Access-Control-Allow-Origin`.
- [ ] Chỉ cho methods và headers cần thiết theo API contract; tránh `*` rộng khi không cần.
- [ ] Frontend dùng `credentials:"include"` khi thật sự cần cookie cross-origin.
- [ ] Cookie Domain/Path/SameSite/Secure/HttpOnly hoạt động theo đúng site, TLS và browser policy.
- [ ] Preflight OPTIONS không bị authentication filter, gateway hoặc redirect chặn sai.
- [ ] Actual request vẫn được authentication, authorization và CSRF kiểm soát độc lập.
- [ ] Response lỗi cũng có CORS headers hợp lệ nếu cần frontend đọc thông tin lỗi.
- [ ] Không có header CORS trùng lặp giữa Spring Security, MVC/WebFlux và proxy.
- [ ] Có `Vary: Origin` phù hợp cho response biến đổi theo origin và cache kiểm soát đúng.
- [ ] Đã thử allowed/disallowed origin bằng browser, không chỉ dùng curl.
- [ ] Đã thử preflight và actual request, có/không cookie, đúng/sai origin, HTTP và HTTPS.
- [ ] Đã xác định stack MVC hay WebFlux thật sự trước khi chọn configurer.

## 17. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân khả dĩ | Hướng khắc phục |
| --- | --- | --- |
| Browser: “Credential is not supported ... `*`” | `Access-Control-Allow-Origin: *` khi fetch có credentials | Dùng allowed origins cụ thể, giữ allowCredentials=true nếu cần |
| Spring báo `IllegalArgumentException` về credentials/wildcard | `allowedOrigins("*")` kết hợp `allowCredentials=true` | Sửa config, không tắt validation |
| Browser báo thiếu `Access-Control-Allow-Credentials` | Server chưa bật allowCredentials hoặc proxy bỏ header | Kiểm tra actual response và CORS source thực tế |
| `Access-Control-Allow-Origin` thiếu | Origin không được allow hoặc request không qua CORS handler đúng | Kiểm tra `Origin`, route và stack |
| Frontend có `credentials:"include"` nhưng session không giữ | Cookie không được gửi, SameSite/Secure/Domain/Path hoặc third-party blocking | Xem cookie jar/DevTools, host/schema và response Set-Cookie |
| OPTIONS bị 401/302 login | Spring Security/proxy xử lý trước CORS | Bật CORS integration đúng thứ tự và cho preflight qua |
| OPTIONS bị 403 “Invalid CORS request” | Origin/method/header không khớp policy | So Request-Method/Request-Headers với config |
| POST JSON bị chặn dù GET hoạt động | POST yêu cầu preflight do JSON/custom headers | Kiểm tra OPTIONS riêng, allowed methods/headers |
| POST nhận 403 sau preflight thành công | Có thể do CSRF/auth, không phải CORS | Kiểm tra SecurityFilterChain và CSRF token |
| Browser nhận nhiều ACAO headers | Spring và gateway cùng cấu hình CORS | Chọn một nguồn phát header |
| Chỉ localhost chạy được, staging không | Origin staging khác scheme/host/port | Bổ sung origin staging đã xác minh |
| Browser hiển thị CORS error dù server log trả 200 | Response thiếu header allow hoặc cookie policy; JS không được đọc | Xem Network response/console, không chỉ status server |
| `Access-Control-Allow-Origin: null` | Request có opaque/null Origin hoặc cấu hình phản chiếu nguy hiểm | Không cho “null” origin trừ trường hợp đã đánh giá bảo mật rất kỹ |
| `Access-Control-Allow-Origin` chứa hai URL có dấu phẩy | Server cố trả danh sách trong một header | Chọn duy nhất origin đang gọi nếu thuộc allowlist |
| `@CrossOrigin` có credentials nhưng global config vẫn lỗi | Global/local combine có thể tạo wildcard | Kiểm tra cấu hình kết hợp, loại bỏ wildcard |
| CORS chỉ lỗi qua CDN | Cache chưa tách variant theo `Origin`, proxy rewrite | Kiểm tra `Vary`, cache key và edge configuration |

### 17.1. Quy trình debug 7 bước

1. **Xác định origin:** frontend URL thực tế, scheme/host/port; không đoán từ hostname API.
2. **Mở DevTools Network:** xem `OPTIONS` (nếu có) và actual request. Đọc `Origin`, `Access-Control-Request-Method`, `Access-Control-Request-Headers`.
3. **Kiểm tra response preflight:** `Access-Control-Allow-Origin` có khớp origin, `Allow-Methods/Headers` có đủ, `Allow-Credentials` có đúng không?
4. **Kiểm tra actual request:** request có gửi cookie hoặc Authorization theo thiết kế không? Response có các CORS headers tương ứng không?
5. **Kiểm tra cookie:** `Set-Cookie`, Domain, Path, SameSite, Secure, third-party policy, localhost vs 127.0.0.1.
6. **Kiểm tra Spring + Security + proxy:** có cấu hình trùng, preflight bị auth chặn, CORS khác nhau giữa success/error không?
7. **Thử negative cases:** origin lạ bị từ chối, method/header không cho phép bị từ chối, API thực sự vẫn áp phân quyền/CSRF.

Browser thường không cho JavaScript đọc chi tiết lỗi CORS từ response cross-origin bị chặn. Server log vẫn có thể cho biết status thực tế, vì thế **đừng sửa business controller trước khi xác định request bị chặn ở tầng CORS, auth hay proxy**.

## 18. Bài tập tự kiểm tra

**Câu 1.** `https://app.example.com` và `https://api.example.com` khác origin ở thành phần nào? Nếu hai trang chỉ khác path thì sao?

**Câu 2.** Khi `allowCredentials(true)`, vì sao `allowedOrigins("*")` không hợp lệ? Spring xử lý như thế nào?

**Câu 3.** Vì sao `allowedOriginPatterns("https://*.example.com")` có thể dùng với credentials trong Spring, nhưng vẫn có rủi ro?

**Câu 4.** CORS policy chỉ cho `GET` và `POST`; frontend POST `application/json`. Browser có thể gửi request nào trước actual POST?

**Câu 5.** Một GET cross-origin không preflight, browser chặn JS đọc response. Server có chắc đã không nhận request không?

**Câu 6.** Trong lab port 5173→8080, vì sao cần `credentials:"include"` dù hai trang thường same-site?

**Câu 7.** Browser gửi cookie theo `credentials:"include"` nhưng API trả `Access-Control-Allow-Origin: *`. Client có đọc JSON response được không?

**Câu 8.** `allowCredentials(true)` có tự giải quyết `SameSite=None; Secure` và third-party cookie blocking không?

**Câu 9.** Khi thêm Spring Security, OPTIONS bị 401 còn GET nội bộ thành công. Thứ tự middleware nào cần xem?

**Câu 10.** Một application có global `allowedOrigins("*")` và local `@CrossOrigin(allowCredentials="true")`. Vì sao có thể bị lỗi dù annotation ở controller không nhắc đến `*`?

**Câu 11.** Một API phản hồi `Access-Control-Allow-Origin: https://a.example, https://b.example`. Header này có cho phép hai origin đúng chuẩn không?

**Câu 12.** Tại sao CORS không thay thế được CSRF token khi dựa trên session cookie?

**Đáp án định hướng:**

1. Host khác; path không tham gia định nghĩa origin.
2. Browser cấm ACAO literal `*` với credentialed response; Spring có validation và có thể ném `IllegalArgumentException` khi config bị áp dụng.
3. Spring phát origin cụ thể đã khớp chứ không phát `*`. Tuy nhiên mọi subdomain khớp có thể được phép đọc response theo credentials; subdomain không tin cậy là rủi ro.
4. `OPTIONS` preflight với `Access-Control-Request-Method: POST` và `Access-Control-Request-Headers: content-type`.
5. Không; request simple có thể được gửi và xử lý trước khi browser chặn đọc response.
6. `fetch` mặc định `credentials:"same-origin"`, nên cross-origin (khác port) không tự gửi cookie dù thường same-site.
7. Không. Browser chặn quyền đọc credentialed CORS response với wildcard origin.
8. Không; cookie policy là lớp độc lập, third-party blocking vẫn có thể ngăn cookie.
9. CORS phải được xử lý trước auth; dùng Security CORS integration và kiểm tra gateway/proxy.
10. Global/local combine có thể vẫn chứa wildcard, mâu thuẫn với credentials.
11. Không. ACAO nhận một origin cụ thể hoặc wildcard hợp lệ, không phải danh sách nhiều origin.
12. Vì CORS chủ yếu kiểm soát JS đọc response; request thay đổi trạng thái có thể vẫn đến server và mang cookie theo cookie policy.

## 19. Tóm tắt lựa chọn thực tế

| Nhu cầu | CORS configuration phù hợp |
| --- | --- |
| Public API không cần credentials | Có thể dùng `allowedOrigins("*")`, không bật `allowCredentials(true)` |
| Frontend riêng gọi API có cookie session | Danh sách `allowedOrigins("https://app.example.com")`, `allowCredentials(true)`, cookie/CSRF chuẩn |
| Nhiều frontend tin cậy hữu hạn | Liệt kê từng origin cụ thể, chỉ phản hồi origin đang gọi |
| Subdomain tin cậy được kiểm soát hoàn toàn | Có thể cân nhắc `allowedOriginPatterns`, review pattern và ownership |
| Subdomain có user-generated content/tenant tự quản | Không dùng wildcard bao trùm để cho credentials; dùng allowlist đã xác minh |
| Không thể kiểm soát trust của các origin ngoài | Không mở credentialed CORS cho tất cả origin; thiết kế lại auth/kiến trúc |
| Có Spring Security | Tích hợp CORS trước auth, giữ CSRF/authorization cho actual requests |
| API nằm sau gateway/CDN | Chọn một nơi quản lý CORS, xử lý `Vary` và headers xuyên tầng |

**Kết luận:** `allowCredentials(true)` là quyết định **trao quyền đọc dữ liệu cho JavaScript tại các origin được tin**, không phải một nút sửa lỗi CORS. Với session/cookie, giữ allowlist nhỏ, không dùng `allowedOrigins("*")` và không dùng `allowedOriginPatterns("*")` như cách “lách” ràng buộc. Xác thực, CSRF, cookie policy và kiểm tra CORS phải được triển khai cùng nhau.

## 20. Tài liệu tham khảo

- Spring Framework — CORS trong Spring MVC, Credentialed Requests, Global Configuration: https://docs.spring.io/spring-framework/reference/web/webmvc-cors.html
- Spring Framework — CORS trong Spring WebFlux: https://docs.spring.io/spring-framework/reference/web/webflux-cors.html
- Spring Framework 6.1 — `CorsConfiguration` API (`allowedOrigins`, `allowedOriginPatterns`, `validateAllowCredentials`, `combine`): https://docs.spring.io/spring-framework/docs/6.1.1/javadoc-api/org/springframework/web/cors/CorsConfiguration.html
- Spring Security — CORS tích hợp Servlet/MVC: https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html
- Spring Security — CORS tích hợp Reactive WebFlux: https://docs.spring.io/spring-security/reference/reactive/integrations/cors.html
- MDN — HTTP CORS và preflight: https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS
- MDN — CORS error khi dùng credentials với ACAO wildcard: https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS/Errors/CORSNotSupportingCredentials
- MDN — Access-Control-Allow-Credentials: https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Access-Control-Allow-Credentials
- MDN — Access-Control-Allow-Origin: https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Access-Control-Allow-Origin
- MDN — Set-Cookie, SameSite và Secure: https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie
