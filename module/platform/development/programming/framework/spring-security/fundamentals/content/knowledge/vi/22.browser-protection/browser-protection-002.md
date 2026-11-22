# Cache-Control cho nội dung chứa dữ liệu nhạy cảm

## 1. Vấn đề cần giải quyết

Giả sử người dùng đăng nhập vào ứng dụng ngân hàng để xem số dư, hồ sơ hoặc lịch sử giao dịch. Sau khi họ đăng xuất, máy chủ đã vô hiệu hóa phiên. Tuy vậy, **trình duyệt, proxy, CDN hoặc một tầng cache khác có thể đã giữ bản sao response chứa dữ liệu nhạy cảm**. Nếu bản sao bị dùng lại, người tiếp theo ở cùng máy hoặc người dùng khác đi qua shared cache có thể nhìn thấy dữ liệu cũ.

Một response riêng tư bị cấu hình sai:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: public, max-age=3600

{"account":"demo","balance":"100000000"}
~~~

`public` có thể cho phép shared HTTP cache giữ response, còn `max-age=3600` biểu thị freshness đến một giờ theo quy tắc HTTP. Đây là chính sách không phù hợp cho một số dư riêng tài khoản.

Với nội dung có độ nhạy cao, thường chọn:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
~~~

Spring Security có bộ mặc định bảo vệ rộng hơn khi security headers còn được bật:

~~~http
Cache-Control: no-cache, no-store, max-age=0, must-revalidate
Pragma: no-cache
Expires: 0
~~~

**Mục tiêu bài học:** giải thích chính xác các directive của `Cache-Control`; biết vì sao `no-cache`, `private` và `max-age=0` khác `no-store`; xác định lớp cache nào nguy hiểm; cấu hình Spring Security để response riêng tư không bị lưu nhưng static assets vẫn cache được; kiểm thử qua MockMvc, browser và CDN; và hiểu giới hạn của HTTP headers sau khi logout.

Phạm vi ví dụ chính: **Spring Security 6.5 / Servlet, Spring Boot 3.5.16 và Java 17**, có phần mở rộng cho WebFlux. Ví dụ sử dụng dữ liệu giả và không yêu cầu môi trường đăng nhập thực tế.

## 2. HTTP cache lưu dữ liệu ở những lớp nào?

~~~text
Browser
  | Browser HTTP cache
  v
CDN / reverse proxy / gateway
  | Shared HTTP cache
  v
Spring Security filter chain
  v
Spring MVC / WebFlux
  v
Business service / database
~~~

### 2.1. Private cache trong trình duyệt

Browser có thể lưu HTML, CSS, JavaScript, images và API response để giảm network requests. Cách lưu phụ thuộc HTTP response headers, request method, status code, trình duyệt, cấu hình browser và lịch sử cache của URL. Trên máy dùng chung, dữ liệu tài khoản hoặc thông tin bí mật không nên được giữ như một bản sao có thể phát lại từ HTTP cache.

### 2.2. Shared cache ở proxy, gateway và CDN

Một shared cache phục vụ nhiều client. Nếu CDN đặt cache key chỉ theo URL `/api/profile` mà không xét dữ liệu riêng người dùng, response A có thể được trả cho B. Việc gửi cùng cookie hay Authorization header **không thay thế kiểm tra chính sách cache**. Các quy tắc CDN “cache all”, cache key thiếu ngữ cảnh tài khoản, hoặc override `Cache-Control` của origin là nguy cơ thực tế phải đánh giá.

`private` chỉ dẫn **shared HTTP cache tuân thủ chuẩn không lưu** response; `no-store` mạnh hơn, yêu cầu cả private và shared HTTP caches không lưu. Với thông tin bí mật hoặc dữ liệu tài chính, `no-store` thường là lựa chọn rõ ràng.

### 2.3. Những thứ không được quản lý hoàn toàn bằng HTTP Cache-Control

- **Back/forward cache (bfcache):** browser có thể giữ snapshot của trang hoặc DOM để khôi phục khi nhấn Back. Cơ chế này khác HTTP cache; `no-store` có thể ảnh hưởng eligibility tùy browser/phiên bản nhưng không bảo đảm xóa mọi snapshot.
- **Service Worker Cache API:** ứng dụng tự viết logic `CacheStorage` có thể lưu response bên ngoài HTTP cache thông thường. Phải kiểm soát logic cache riêng, không tự ghi nội dung nhạy cảm vào offline cache và dọn dữ liệu khi logout.
- **SPA state và web storage:** Redux, React state, DOM, IndexedDB, `localStorage` và biến JavaScript không bị xóa chỉ vì server trả `no-store`.
- **File đã tải, screenshot và logs:** Cache-Control không xóa dữ liệu đã tải xuống, log proxy hoặc ảnh chụp màn hình.
- **Backend caches:** Redis, application cache, database/query cache cần phân quyền và chính sách tồn tại dữ liệu riêng; HTTP header không điều khiển các kho đó.

**Cần phân biệt:** chính sách cache HTTP chỉ là một lớp; ứng dụng vẫn phải kiểm tra authentication, authorization, session revocation, logout và dữ liệu còn ở client.

## 3. Ý nghĩa thực tế của các Cache-Control directive

| Directive (response) | Ý nghĩa | Phù hợp |
| --- | --- | --- |
| `no-store` | Cache HTTP tuân thủ chuẩn không được cố ý lưu response | Tokens, số dư, thông tin tài khoản nhạy cảm, khóa bí mật |
| `no-cache` | Có thể **lưu**, nhưng phải **revalidate với origin trước khi dùng lại** | Dữ liệu có thể giữ nhưng cần xác minh trước mỗi lần tái dùng |
| `private` | Private cache có thể lưu; shared cache không được lưu | Nội dung theo user nhưng chấp nhận browser giữ bản sao |
| `public` | Cho phép shared cache lưu nếu các điều kiện khác hợp lệ | Static/public content giống nhau cho mọi người |
| `max-age=N` | Response có thể được coi là fresh trong khoảng N giây | Public assets hoặc nội dung được phép cache |
| `s-maxage=N` | Freshness dành cho shared cache, ưu tiên hơn max-age ở shared cache | Chính sách CDN cho nội dung công khai |
| `must-revalidate` | Khi đã stale, không được dùng lại nếu chưa revalidate | Nội dung được phép cache nhưng không phục vụ bản stale |
| `immutable` | Báo resource khó thay đổi trong thời gian freshness | Asset có content hash trong tên hoặc URL versioned |

### 3.1. `no-cache` vẫn cho phép lưu

Ví dụ:

~~~http
Cache-Control: private, no-cache
ETag: "profile-v6"
~~~

Browser có thể lưu response body trong private cache. Khi muốn dùng lại, nó phải xác minh với origin (chẳng hạn gửi `If-None-Match`). Nếu server trả `304 Not Modified` một cách hợp lệ và đã kiểm tra quyền, browser có thể dùng body cũ. **Nếu yêu cầu không giữ bản sao**, `no-cache` không đủ: dùng `no-store`.

### 3.2. `no-store` không phải lệnh xóa mọi dữ liệu cũ

~~~http
Cache-Control: no-store
~~~

Đây là directive ngăn lưu trong HTTP caches tuân thủ chuẩn. Nó **không xóa các bản sao đã được lưu trước đó**, cũng không bảo đảm xóa browser history, Service Worker cache tùy biến, localStorage hay file đã tải. Nếu response cũ còn fresh và cache không liên hệ origin, server mới cập nhật header vẫn có thể chưa được hỏi lại.

Đối với **response chứa access token, refresh token hoặc credentials** theo OAuth 2.0, RFC 6749 mục 5.1 quy định:

~~~http
Cache-Control: no-store
Pragma: no-cache
~~~

### 3.3. `private` khác `no-store`

~~~http
Cache-Control: private, max-age=300
~~~

Ví dụ trên có thể giữ profile cá nhân trong browser khoảng 5 phút nếu còn fresh, nhưng shared cache không được lưu. Đây có thể là quyết định hợp lý cho nội dung ít nhạy sau khi cân nhắc thiết bị/UX. Với mã khôi phục, sao kê tài chính, thông tin y tế hoặc API key, ưu tiên `no-store`.

### 3.4. `max-age=0` không có nghĩa cấm lưu

`max-age=0` thường làm response stale ngay, còn `must-revalidate` yêu cầu revalidate khi đã stale. Hai directive này **không cấm tạo bản sao cache**. Spring Security ghép các directive với `no-store` để tăng phòng vệ và hỗ trợ các triển khai HTTP cũ.

### 3.5. `Pragma` và `Expires` mang tính tương thích

`Pragma: no-cache` là cơ chế lịch sử của HTTP/1.0; `Expires: 0` đánh dấu thời điểm đã hết hạn theo nhiều hệ thống cũ. Với response hiện đại chứa dữ liệu cực kỳ nhạy cảm, không thay `Cache-Control: no-store` bằng riêng `Pragma`/`Expires`.

### 3.6. Request header và response header không giống nhau

Client có thể gửi:

~~~http
GET /account HTTP/1.1
Host: app.example.org
Cache-Control: no-cache
~~~

Header trên request chủ yếu yêu cầu cache revalidate khi trả dữ liệu. **Nó không buộc server đánh dấu response là không được lưu.** Để bảo vệ response riêng tư, phải có chính sách ở **response** và ở những tầng proxy chịu trách nhiệm cache.

## 4. Lựa chọn cache policy theo loại dữ liệu

| Loại response | Gợi ý | Giải thích |
| --- | --- | --- |
| OAuth token endpoint, access/refresh token, mã khôi phục, mật khẩu mới sinh | `no-store`; với OAuth response thêm `Pragma: no-cache` theo RFC | Không giữ credential trong HTTP caches |
| API số dư, tài liệu nội bộ, thông tin định danh nhạy cảm, trang admin | `no-store` | Hạn chế tối đa bản sao trong HTTP caches |
| Download PDF/CSV chứa dữ liệu riêng | `no-store` | Không lưu trong HTTP cache; vẫn phải bảo vệ file sau khi download |
| Dashboard ít nhạy, theo user | Có thể cân nhắc `private, no-cache` nếu chấp nhận browser lưu | Cho phép browser cache nhưng phải revalidate |
| HTML app shell công khai, thường cập nhật | `no-cache` hoặc freshness ngắn | Browser có thể tái dùng sau xác minh |
| CSS/JS công khai có tên gắn content hash | `public, max-age=31536000, immutable` nếu URL bất biến | Tăng hiệu năng mà không lưu dữ liệu user |
| Logo, font và ảnh công khai | `public, max-age` phù hợp | Dùng shared/browser caches hợp lý |
| Error response vô tình chứa thông tin nhạy cảm | `no-store` | Không chỉ bảo vệ status 200 |

Đây là các mẫu lựa chọn dựa trên rủi ro, không phải quy tắc cố định của Spring Security cho mọi ứng dụng. Nội dung công khai không nhất thiết phải được cache; nội dung có login cũng không nhất thiết đều bí mật. Cần đánh giá **độ nhạy thực sự của body**.

## 5. Spring Security bảo vệ cache như thế nào?

Theo tài liệu Spring Security 6.5, khi cấu hình security response headers mặc định còn hiệu lực, framework phát:

~~~http
Cache-Control: no-cache, no-store, max-age=0, must-revalidate
Pragma: no-cache
Expires: 0
~~~

Ở Servlet stack, các thành phần như `HeaderWriterFilter` và `CacheControlHeadersWriter` tạo hoặc quản lý nhóm header. **Đừng mặc định coi toàn bộ response cuối đã an toàn**: nếu ứng dụng tự đặt `Cache-Control`, Spring Security có thể nhường cho cấu hình đó. Security filter chain bị bỏ qua hoặc proxy ghi đè header cũng có thể làm thay đổi kết quả.

### 5.1. Nếu controller không tự đặt Cache-Control

~~~java
@GetMapping("/account/profile")
Map<String, String> profile(Authentication auth) {
    return Map.of("user", auth.getName());
}
~~~

Đây là **một method Spring MVC**, không phải chương trình Java độc lập. Nếu request đi qua filter chain có security headers mặc định và chưa có header khác ghi đè, response thường được Spring Security gắn bộ header no-store phía trên.

### 5.2. Nếu controller tự đặt Cache-Control

~~~java
@GetMapping("/public/news")
ResponseEntity<String> news() {
    return ResponseEntity.ok()
        .cacheControl(CacheControl.maxAge(Duration.ofMinutes(10)).cachePublic())
        .body("Thông báo công khai");
}
~~~

Đây là mảnh code đặt trong controller; imports cần gồm `ResponseEntity`, `CacheControl` của Spring HTTP và `java.time.Duration`. Header `Cache-Control: max-age=600, public` được ứng dụng đặt có chủ đích cho nội dung công khai. Nhưng áp dụng policy ấy vào một API dữ liệu khách hàng sẽ tạo rủi ro lộ dữ liệu.

### 5.3. Không tắt header mặc định khi không có lớp thay thế

Mảnh cấu hình Servlet dưới đây **vô hiệu hóa riêng cache-control mặc định**:

~~~java
.headers(headers -> headers
    .cacheControl(cache -> cache.disable()))
~~~

Và cách này **vô hiệu hóa toàn bộ security response headers** được Spring Security thêm theo cấu hình:

~~~java
.headers(headers -> headers.disable())
~~~

Không bật chúng chỉ để CSS/JS được cache. Hãy đặt chính sách riêng cho assets công khai. Việc disable toàn bộ còn ảnh hưởng đến các header an ninh khác như `X-Content-Type-Options` hoặc `X-Frame-Options`.

### 5.4. `permitAll` và `web.ignoring`

Một route được cấu hình `permitAll()` vẫn đi qua Spring Security filter chain; security headers có thể tiếp tục được áp dụng. Route được bỏ qua bằng `web.ignoring()` không đi qua chuỗi filter này và có thể không nhận header từ Spring Security. Đừng bỏ qua filter cho API có dữ liệu nhạy cảm.

### 5.5. Cập nhật phiên bản để tránh lỗi phát header

Spring đã công bố cảnh báo **CVE-2026-22732** liên quan đến một số trường hợp Servlet security response headers không được ghi. Với các nhánh Spring Security 6.5, cần bản vá từ **6.5.9** trở lên; ứng dụng nên dùng phiên bản được duy trì và kiểm chứng. Dù đã nâng cấp, vẫn phải có test kiểm tra header vì còn nguy cơ từ controller/proxy hoặc security matcher sai.

## 6. Ví dụ Java 17 + Spring Boot + Spring Security (Servlet)

Ứng dụng dưới đây phân biệt hai endpoint:

- `GET /account/me`: buộc xác thực, chứa dữ liệu giả lập riêng tư, gắn `Cache-Control: no-store` tường minh.
- `GET /public/news`: công khai, giống nhau cho mọi user, cho phép cache tối đa 10 phút.

Dùng **Java 17**, Maven, **Spring Boot 3.5.16** và Spring Security do Boot quản lý. Đây là phiên bản minh họa đã phát hành; khi đưa vào sản phẩm, chọn dòng Spring Boot còn nhận cập nhật bảo mật, nâng cấp dependencies và bật HTTPS. Mẫu dùng HTTP Basic và `{noop}` password **chỉ để học**.

Cấu trúc:

~~~text
sensitive-cache-demo/
├── pom.xml
└── src/
    ├── main/java/example/cache/SensitiveCacheApplication.java
    └── test/java/example/cache/SensitiveCacheApplicationTests.java
~~~

**`pom.xml`**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.16</version>
    <relativePath/>
  </parent>
  <groupId>example</groupId>
  <artifactId>sensitive-cache-demo</artifactId>
  <version>1.0.0</version>
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
      <artifactId>spring-boot-starter-security</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-test</artifactId>
      <scope>test</scope>
    </dependency>
    <dependency>
      <groupId>org.springframework.security</groupId>
      <artifactId>spring-security-test</artifactId>
      <scope>test</scope>
    </dependency>
  </dependencies>
</project>
~~~

**`src/main/java/example/cache/SensitiveCacheApplication.java`**:

~~~java
package example.cache;

import java.time.Duration;
import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class SensitiveCacheApplication {
    public static void main(String[] args) {
        SpringApplication.run(SensitiveCacheApplication.class, args);
    }

    @Bean
    SecurityFilterChain security(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**").permitAll()
                .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults())
            // Giữ default security headers; không gọi headers.disable().
            .build();
    }

    @Bean
    UserDetailsService users() {
        return new InMemoryUserDetailsManager(
            User.withUsername("demo")
                .password("{noop}demo123") // chỉ dành cho demo
                .roles("USER")
                .build());
    }

    @RestController
    static class Endpoints {
        @GetMapping("/account/me")
        ResponseEntity<Map<String, String>> account(Authentication auth) {
            return ResponseEntity.ok()
                .cacheControl(CacheControl.noStore())
                .body(Map.of(
                    "user", auth.getName(),
                    "balance", "SENSITIVE_DEMO_DATA"));
        }

        @GetMapping("/public/news")
        ResponseEntity<Map<String, String>> news() {
            return ResponseEntity.ok()
                .cacheControl(CacheControl.maxAge(Duration.ofMinutes(10))
                    .cachePublic())
                .body(Map.of("news", "PUBLIC_ANNOUNCEMENT"));
        }
    }
}
~~~

**Vì sao code được viết như vậy?**

1. `authorizeHttpRequests` chặn `/account/me` khi chưa xác thực; `/public/**` được phép truy cập không cần login.
2. `httpBasic` cho phép thử bằng `curl`. Trong sản phẩm cần TLS, lưu mật khẩu đã hash phù hợp và đánh giá CSRF nếu browser tự gửi credentials ở các method thay đổi dữ liệu.
3. `CacheControl.noStore()` đặt cache policy rõ ràng cho nội dung nhạy cảm; vẫn có ích nếu security headers mặc định bị thay đổi trong một cấu hình khác.
4. `CacheControl.maxAge(Duration.ofMinutes(10)).cachePublic()` được dùng **chỉ** cho thông báo công khai.
5. Mẫu không truy cập dữ liệu thật, không phát access token, không cấu hình CDN. Các response chứa chuỗi demo.

Chạy:

~~~bash
mvn spring-boot:run

# Endpoint công khai: dự kiến HTTP 200 và max-age=600, public
curl -i http://localhost:8080/public/news

# Endpoint riêng tư thiếu credentials: dự kiến 401
curl -i http://localhost:8080/account/me

# Endpoint riêng tư có credentials demo: dự kiến HTTP 200 + no-store
curl -i -u demo:demo123 http://localhost:8080/account/me
~~~

Body của response private có thể tương tự `{"balance":"SENSITIVE_DEMO_DATA","user":"demo"}`; **thứ tự keys trong JSON object không ổn định**, đừng kiểm thử bằng so sánh nguyên chuỗi body. Hãy kiểm tra giá trị, status và cache headers.

### 6.1. Kiểm thử MockMvc

**`src/test/java/example/cache/SensitiveCacheApplicationTests.java`**:

~~~java
package example.cache;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SensitiveCacheApplicationTests {
    @Autowired
    MockMvc mvc;

    @Test
    void sensitiveResponseIsNoStore() throws Exception {
        mvc.perform(get("/account/me").with(httpBasic("demo", "demo123")))
            .andExpect(status().isOk())
            .andExpect(header().string("Cache-Control",
                containsString("no-store")));
    }

    @Test
    void publicResponseHasPublicFreshness() throws Exception {
        mvc.perform(get("/public/news"))
            .andExpect(status().isOk())
            .andExpect(header().string("Cache-Control",
                containsString("public")))
            .andExpect(header().string("Cache-Control",
                containsString("max-age=600")));
    }

    @Test
    void privateResponseRequiresAuthentication() throws Exception {
        mvc.perform(get("/account/me"))
            .andExpect(status().isUnauthorized());
    }
}
~~~

Chạy kiểm thử:

~~~bash
mvn test
~~~

Kết quả kỳ vọng: ba test xanh nếu dependencies và môi trường tương thích. Test thứ nhất xác nhận `no-store` xuất hiện trên endpoint private, test thứ hai kiểm tra policy tài nguyên công khai, test cuối xác nhận route riêng tư không cho phép anonymous. **MockMvc chỉ kiểm tra lớp ứng dụng**, không qua CDN hoặc browser HTTP cache; cần kiểm tra production edge riêng.

## 7. Cho phép cache static assets công khai

Bạn có thể tối ưu những file tĩnh **không chứa dữ liệu người dùng** mà vẫn giữ no-store cho tài liệu nhạy cảm.

Ví dụ header với JS có content hash trong filename:

~~~http
GET /assets/main.a94c1d3.js HTTP/1.1
Host: app.example.org

HTTP/1.1 200 OK
Content-Type: text/javascript
Cache-Control: public, max-age=31536000, immutable
~~~

Chỉ dùng `immutable` với URL chứa nội dung không đổi trong thời gian cache; khi build tạo asset mới, URL cần thay đổi. Không dùng chính sách này cho HTML trang tài khoản, token endpoint, dữ liệu user hoặc file riêng tư.

Spring MVC cho phép cấu hình public static resource bằng `WebMvcConfigurer`; đoạn dưới là **mảnh code bổ sung vào ứng dụng Servlet**, không phải main class độc lập:

~~~java
@Configuration
class PublicAssetsConfig implements WebMvcConfigurer {
    @Override
    public void addResourceHandlers(ResourceHandlerRegistry registry) {
        registry.addResourceHandler("/assets/**")
            .addResourceLocations("classpath:/static/assets/")
            .setCacheControl(CacheControl.maxAge(Duration.ofDays(365))
                .cachePublic());
    }
}
~~~

Imports: `org.springframework.context.annotation.Configuration`, `org.springframework.web.servlet.config.annotation.WebMvcConfigurer`, `org.springframework.web.servlet.config.annotation.ResourceHandlerRegistry`, `org.springframework.http.CacheControl` và `java.time.Duration`. Không bật freshness dài cho file không có URL versioned; nếu file có thể bị thay tại cùng đường dẫn, cần thời gian cache ngắn hơn hoặc versioning.

Một số ứng dụng cấu hình static files qua Spring Boot properties hoặc CDN; cần chọn **một nơi chịu trách nhiệm chính** và kiểm tra response cuối cùng, đặc biệt khi security filter chain và cache proxy cùng sửa header.

## 8. Vary, ETag, 304 và nguy cơ sai cache key

### 8.1. `Vary` không thay việc bảo vệ dữ liệu riêng

~~~http
Cache-Control: private, no-cache
Vary: Accept-Language
~~~

`Vary` biểu thị những request headers làm thay đổi response, để cache phân biệt variants. Nhưng `Vary: Cookie` hoặc `Vary: Authorization` **không được coi là biện pháp đủ** cho dữ liệu bí mật. CDN có thể không honor header, normalize cookies, tạo cache key sai hoặc cố tình override. Cần kết hợp với `private` hoặc `no-store` và kiểm tra authorization tại origin.

### 8.2. `ETag` và `If-None-Match` không phải cơ chế bảo mật

Khi response được phép cache, server có thể phát `ETag`. Browser gửi `If-None-Match` để xác minh bản đã lưu; server có thể trả `304 Not Modified` nếu phù hợp. Với endpoint riêng tư, **vẫn phải xác minh user/session/permission trước khi trả 304**. Không trả 304 chỉ vì chuỗi ETag khớp rồi cho phép browser tái sử dụng body của tài khoản khác.

### 8.3. Shared caching với Authorization

HTTP có quy tắc hạn chế shared cache lưu response cho request mang `Authorization`, nhưng có những ngoại lệ khi response chứa directive như `public`, `s-maxage` hoặc `must-revalidate`. Không được kết luận “có Authorization thì CDN chắc chắn không lưu”. Chính sách response và CDN configuration quyết định thực tế; kiểm tra trường hợp A/B dùng cùng URL với credentials khác nhau.

### 8.4. Ví dụ lộ dữ liệu chéo user

~~~text
A -> GET /api/account/42 -> CDN lưu body dưới cache key = URL
B -> GET /api/account/42 -> CDN trả body của A từ cache
~~~

Đây là lỗi nghiêm trọng dù Spring Security đã xác thực request tới origin đúng cách: request B có thể **không bao giờ đến origin** nếu edge trả cache hit. Phải chặn cache trên private routes hoặc thiết kế cache key/rules đủ đúng theo đặc thù sản phẩm, kèm test nhiều danh tính.

## 9. Logout, Back button và các giới hạn thực tế

Quy trình thông thường:

1. User A đăng nhập và nhận response private có `Cache-Control: no-store`.
2. User A logout; server thu hồi session/token phù hợp.
3. Người khác dùng cùng browser nhấn Back tới trang tài khoản.
4. Browser có thể thực hiện network request, dùng snapshot từ bfcache hoặc SPA state tùy môi trường.

Header `no-store` giảm nguy cơ HTTP cache lưu response mới, **nhưng không tự dọn các nguồn dữ liệu khác**.

- **bfcache:** có thể restore DOM snapshot. Hành vi thay đổi theo browser/version; kiểm tra thực tế với Back/Forward.
- **SPA store:** nếu app không xóa state khi logout, dữ liệu A có thể còn trong bộ nhớ của JavaScript.
- **Service Worker:** có thể tự giữ response trong Cache API.
- **Tab khác:** vẫn có thể giữ UI trước logout, dù request mới bị từ chối.
- **File download:** CSV/PDF đã tải về vẫn còn trên thiết bị.
- **Browser extension/screenshot/log:** không bị xóa bởi response header.

Để hạn chế lộ giao diện, SPA cần xóa state trên logout, quản lý nhiều tab, che dữ liệu khi cần kiểm tra lại phiên và không gọi UI-only protection là authorization thực sự. Server luôn phải từ chối request mới nếu phiên đã hết hiệu lực.

### 9.1. Khôi phục trang từ bfcache

Browser có thể phát sự kiện `pageshow` với `event.persisted` khi tài liệu được khôi phục từ bfcache. Ứng dụng SPA có thể dùng tín hiệu này để **ẩn thông tin cũ ngay và kiểm tra lại phiên**, trước khi đưa dữ liệu nhạy cảm ra màn hình. Ví dụ dưới đây chỉ là mảnh frontend tích hợp:

~~~javascript
window.addEventListener("pageshow", async (event) => {
  if (!event.persisted) return;

  document.body.classList.add("session-recheck");
  const response = await fetch("/api/session-status", {
    credentials: "same-origin",
    cache: "no-store"
  });

  if (response.ok) {
    window.location.reload();
  } else {
    window.location.replace("/login");
  }
});
~~~

Endpoint `/api/session-status` và class `session-recheck` do ứng dụng phải tự cung cấp; đoạn trên không phải API mặc định của Spring Security. Một ứng dụng thật cần che dữ liệu phù hợp ngay trong các giai đoạn loading/restore, xử lý lỗi mạng an toàn và không để dữ liệu lộ trong một khung hình ngắn trước khi kiểm tra.

### 9.2. Clear-Site-Data khi logout

Browser có hỗ trợ có thể phản ứng với header:

~~~http
Clear-Site-Data: "cache", "storage"
~~~

Nó có thể giúp dọn một số dạng dữ liệu phía browser theo phạm vi quy định, nhưng hiệu lực phụ thuộc user agent và không xóa cache trên CDN hoặc mọi bản sao trên máy. Directive `"cookies"` cần dùng thận trọng vì có phạm vi tác động rộng. Đừng coi `Clear-Site-Data` là cơ chế khắc phục tức thời cho dữ liệu đã bị rò rỉ.

## 10. WebFlux: cùng mục tiêu, API khác

Spring Security WebFlux dùng `ServerHttpSecurity`, `SecurityWebFilterChain` và reactive WebFilters thay cho `HttpSecurity`/Servlet filters. Mặc định framework cũng cung cấp cache security headers khi chain tương ứng áp dụng.

Cấu hình minh họa **trong ứng dụng Spring WebFlux riêng**, không copy nguyên vào Servlet application:

~~~java
@Bean
SecurityWebFilterChain security(ServerHttpSecurity http) {
    return http
        .authorizeExchange(a -> a
            .pathMatchers("/public/**").permitAll()
            .anyExchange().authenticated())
        .httpBasic(Customizer.withDefaults())
        .build();
}
~~~

Imports: `org.springframework.context.annotation.Bean`, `org.springframework.security.config.Customizer`, `org.springframework.security.config.web.server.ServerHttpSecurity` và `org.springframework.security.web.server.SecurityWebFilterChain`. Đặt method trong `@Configuration`.

Một reactive controller cũng có thể đặt riêng response policy:

~~~java
@GetMapping("/account/reactive")
Mono<ResponseEntity<String>> sensitive() {
    return Mono.just(ResponseEntity.ok()
        .cacheControl(CacheControl.noStore())
        .body("DEMO_PRIVATE_DATA"));
}
~~~

Imports tương ứng: `GetMapping`, `Mono`, `ResponseEntity` và `CacheControl`. Đây chỉ là mảnh method, không chạy độc lập; route phải được bảo vệ bằng Spring Security trong ứng dụng thật.

Nếu cần vô hiệu hóa riêng cache-control writer ở WebFlux, cú pháp là:

~~~java
.headers(headers -> headers.cache(cache -> cache.disable()))
~~~

Đây là **minh họa khả năng cấu hình**, không phải lời khuyên mặc định. Chỉ dùng khi tất cả response đã có lớp bảo vệ cache thay thế được kiểm thử. Không trộn `ServerHttpSecurity` vào `HttpSecurity` Servlet.

## 11. Kiểm thử từ browser tới CDN

### 11.1. Kiểm tra tại ứng dụng

~~~bash
curl -i http://localhost:8080/public/news
curl -i http://localhost:8080/account/me
curl -i -u demo:demo123 http://localhost:8080/account/me
~~~

Đối chiếu status, `Cache-Control`, `Pragma`, `Expires`, `Vary`, `Age`, `ETag`, `Set-Cookie` và `Content-Type`. Khi xem response thực tế qua browser, không bật DevTools “Disable cache” rồi kết luận chính sách máy chủ đã đúng: tùy chọn này thay đổi cách browser tự sử dụng cache trong phiên debug.

### 11.2. HEAD không thay GET khi kiểm thử

Có thể dùng `curl -I` cho HEAD, nhưng một số ứng dụng/proxy có xử lý HEAD khác GET. Với response chứa dữ liệu, vẫn phải kiểm tra GET cùng authentication và policy trên response thực sự chứa body.

### 11.3. Ma trận kiểm tra

| Trường hợp | Kết quả mong đợi |
| --- | --- |
| GET thông tin nhạy cảm, đã đăng nhập | Response cuối có `Cache-Control: no-store` |
| GET tài nguyên public versioned | Có freshness/public đúng policy |
| Anonymous gọi endpoint nhạy cảm | 401 hoặc redirect login tùy chain; không có body riêng tư |
| Logout rồi yêu cầu lại nội dung riêng | Server từ chối hoặc yêu cầu đăng nhập mới |
| Back/Forward sau logout | Không để HTTP cache/bfcache/SPA state lộ nội dung cũ |
| User A và user B gọi URL trùng qua CDN | Không bao giờ nhận body của người còn lại |
| Response 302/401/403 hoặc download chứa dữ liệu riêng | Không vô tình bị cache theo quy tắc rộng |
| Revalidation bằng ETag và 304 | Server không bỏ qua quyền truy cập khi revalidate |
| Gateway ép cache all | Endpoint nhạy cảm phải được exempt và đo tại edge |
| Service Worker/Offline | Không cache nội dung riêng tư vào CacheStorage |
| Đổi security matcher, nâng cấp Spring Security | CI và integration tests xác nhận headers không mất |
| Nhiều node và multi-tenant | Cache key và chính sách nhất quán |

### 11.4. Quan sát ở proxy/CDN

Ngoài `Cache-Control`, một số CDN có header cache status như `Age` hoặc header riêng của nhà cung cấp. Đo lặp lại cùng URL với **hai tài khoản test** để kiểm chứng không cache lẫn; không dùng dữ liệu người dùng thật. Kiểm tra các rule bypass, cache key theo cookie/header, `Set-Cookie`, `Authorization`, status codes, `Vary`, thời gian cache và chính sách xử lý stale.

Không chỉ test kết quả GET tại localhost. Một thiết lập CDN có thể bỏ qua hoặc chỉnh sửa header của origin; policy thực tế được quyết định trên toàn đường đi.

## 12. Các lỗi triển khai thường gặp

**Lỗi 1 – Nhầm `no-cache` là không lưu.** Nó vẫn cho phép cache; cần `no-store` nếu không được giữ body.

**Lỗi 2 – Chỉ dùng `private` cho token.** Browser private cache vẫn có thể lưu; token cần `no-store` theo chuẩn liên quan.

**Lỗi 3 – Dùng `max-age=0` thay no-store.** Dữ liệu vẫn có thể tồn tại trong cache và bị revalidate.

**Lỗi 4 – Tin rằng Spring Security luôn cưỡng chế no-store.** Header của controller/gateway có thể ghi đè; security chain có thể bị bỏ qua.

**Lỗi 5 – Tắt mọi security headers để tăng tốc assets.** Điều này bỏ các phòng vệ khác; thay bằng cache policy chọn lọc cho public assets.

**Lỗi 6 – Cấu hình `public` cho API trả dữ liệu account.** Shared cache có thể lưu response riêng tư, gây lộ user A sang user B.

**Lỗi 7 – Dùng `Vary: Cookie` thay authorization.** Vary không cấp quyền và CDN có thể cấu hình cache key sai.

**Lỗi 8 – 304 không kiểm tra session.** Server phải kiểm tra authentication/authorization trước khi cho tái sử dụng body đã lưu.

**Lỗi 9 – Coi logout là lệnh xóa cache.** Logout không tự xóa dữ liệu browser, Service Worker, download hay logs.

**Lỗi 10 – Coi no-store ngăn mọi bfcache.** Browser có thể khôi phục DOM snapshot theo cách riêng, cần thử Back/Forward.

**Lỗi 11 – Chỉ test MockMvc.** MockMvc không đi qua edge/CDN, nơi response headers có thể bị sửa.

**Lỗi 12 – Chỉ xét response HTTP 200.** Error/redirect/download nhạy cảm cũng cần policy rõ ràng; kiểm thử mọi luồng.

**Lỗi 13 – Chỉ dùng `Pragma: no-cache` cho OAuth response.** RFC 6749 `5.1` yêu cầu `Cache-Control: no-store` và `Pragma: no-cache`.

**Lỗi 14 – Sửa header mới rồi tin đã xóa response cũ.** Cache hiện có có thể vẫn giữ bản sao trước khi origin được hỏi lại; phải có kế hoạch purge và đánh giá rủi ro rò rỉ.

## 13. Checklist triển khai

1. **Phân loại routes:** token, dữ liệu nhạy, dashboard, downloads, HTML shell, static resources; chọn policy có cơ sở.
2. **Cấu hình từng response:** no-store cho bí mật; private/no-cache khi được phép giữ ở browser; public cache dài chỉ cho public versioned assets.
3. **Giữ security headers đúng cách:** tránh disable toàn bộ; kiểm tra các security chains, matcher và đường bypass.
4. **Bảo vệ origin:** authenticate và authorize cả request thông thường lẫn conditional request `ETag/304`, xử lý logout và session expiry.
5. **Kiểm tra mọi lớp cache:** browser HTTP cache, bfcache, Service Worker, proxy, CDN, app cache.
6. **Chống dữ liệu rò:** tránh log token, không đưa credential vào URL, tránh cache user-specific response ở CDN.
7. **Kiểm thử nhiều danh tính:** cùng URL với hai tài khoản, sau logout, Back/Forward, private browsing, tải file, errors/redirects.
8. **Kiểm thử CI và production edge:** bảo đảm headers tồn tại sau nâng cấp dependencies, thay đổi router/security filter hoặc CDN rules.

## 14. Câu hỏi tự kiểm tra

**Q1.** `Cache-Control: no-cache` có đảm bảo trình duyệt không lưu bản sao hồ sơ không?  
**Đáp án:** Không. Nó cho phép lưu nhưng yêu cầu revalidate trước khi dùng lại.

**Q2.** `Cache-Control: private` khác gì `no-store`?  
**Đáp án:** Private ngăn shared cache lưu nhưng vẫn cho phép browser cache; no-store yêu cầu HTTP caches không giữ bản sao.

**Q3.** Spring Security gửi mặc định những cache headers nào?  
**Đáp án:** `Cache-Control: no-cache, no-store, max-age=0, must-revalidate`, `Pragma: no-cache` và `Expires: 0` khi default security headers còn hiệu lực.

**Q4.** Controller của ứng dụng tự đặt `Cache-Control: public, max-age=3600` trên profile. Spring Security có chắc ghi đè thành no-store không?  
**Đáp án:** Không. Tài liệu Spring Security cho phép response được tùy biến; phải sửa policy ngay tại lớp phát header và kiểm thử kết quả cuối.

**Q5.** Vì sao sau logout vẫn phải thử nút Back?  
**Đáp án:** Ngoài HTTP cache còn có bfcache, SPA state, Service Worker và tab đã mở.

**Q6.** Tại sao không dùng `public, max-age=31536000` cho HTML hồ sơ chỉ vì file JS của nó có content hash?  
**Đáp án:** HTML chứa dữ liệu theo user khác với static asset công khai. Chỉ content không đổi và an toàn cho mọi người mới phù hợp cache dài.

**Q7.** Với response trả OAuth access token/refresh token, RFC 6749 yêu cầu gì?  
**Đáp án:** `Cache-Control: no-store` và `Pragma: no-cache`.

**Q8.** Kiểm thử MockMvc đã chứng minh an toàn ở CDN chưa?  
**Đáp án:** Chưa. MockMvc chỉ kiểm tra ứng dụng; phải đo response tại edge và cache hit/miss với nhiều danh tính.

## 15. Tài liệu tham khảo

- [Spring Security 6.5 – Servlet HTTP Security Response Headers](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/headers.html): headers mặc định, cache-control customization và disable.
- [Spring Security 6.5 – WebFlux HTTP Security Response Headers](https://docs.spring.io/spring-security/reference/6.5/reactive/exploits/headers.html): cấu hình reactive.
- [Spring Framework – HTTP Caching](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-caching.html): Spring MVC `CacheControl`, ETag và 304.
- [RFC 9111 – HTTP Caching](https://www.rfc-editor.org/rfc/rfc9111.html): định nghĩa no-store, no-cache, private, public và revalidation.
- [RFC 6749 – OAuth 2.0, mục 5.1 Access Token Response](https://www.rfc-editor.org/rfc/rfc6749.html#section-5.1): yêu cầu bảo vệ token response.
- [MDN – Cache-Control header](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Cache-Control): mô tả directive và giới hạn.
- [MDN – HTTP Caching](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Caching): browser/shared cache, static assets, old stored responses.
- [Spring Security Advisory – CVE-2026-22732](https://spring.io/security/cve-2026-22732/): lý do cần giữ phiên bản đã vá và test header thực tế.
