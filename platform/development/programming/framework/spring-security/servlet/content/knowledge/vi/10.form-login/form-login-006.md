# RequestCache, SavedRequest và khôi phục yêu cầu sau đăng nhập (Spring Security Servlet)

## 1. Bài toán: người dùng đang ở đâu trước khi đăng nhập?

Giả sử một người chưa đăng nhập mở đường dẫn được bảo vệ:

```text
GET /private/report?tab=history
```

Ứng dụng sử dụng Spring Security Servlet và form login. Thay vì đánh mất nơi người dùng định đến, hệ thống có thể ghi nhớ yêu cầu ban đầu, chuyển họ đến trang đăng nhập, rồi **sau khi xác thực thành công** đưa trình duyệt quay lại URL đã yêu cầu.

Ba khái niệm trọng tâm:

- **`RequestCache`** là interface quy định cách lưu, tra cứu, tìm request khớp và xóa yêu cầu đã ghi nhớ.
- **`SavedRequest`** là mô tả đã lưu của một request HTTP (thường gồm URL gốc và một số thuộc tính request cần thiết); nó không phải bản sao có thể chạy lại mọi thao tác HTTP.
- **Khôi phục sau đăng nhập** trong form login thường nghĩa là **redirect trình duyệt đến URL đã lưu**, sau đó trình duyệt tạo một HTTP request mới; không phải server tự phát lại request cũ với body, phương thức và tác dụng phụ nguyên vẹn.

Trong đường xử lý mặc định, `HttpSessionRequestCache` lưu `SavedRequest` ở `HttpSession`, `ExceptionTranslationFilter` tham gia lưu request khi authentication là bắt buộc, và `SavedRequestAwareAuthenticationSuccessHandler` thường chọn URL đã lưu làm đích redirect sau xác thực thành công.

**Phạm vi:** đây là luồng Spring Security **Servlet** với **đăng nhập biểu mẫu và session**. Luồng API stateless, HTTP Basic hoặc JWT không nhất thiết sử dụng redirect/saved request theo cùng cách.

## 2. Phân biệt các thành phần và trách nhiệm

| Thành phần | Là gì? | Vai trò trong luồng |
| --- | --- | --- |
| `RequestCache` | Interface | Lưu yêu cầu, lấy yêu cầu đã lưu, lấy request khớp và xóa khi phù hợp. |
| `HttpSessionRequestCache` | Implementation của `RequestCache` | Thường lưu `SavedRequest` trong `HttpSession`. |
| `SavedRequest` | Interface | Đại diện thông tin của request đã ghi nhớ; có `getRedirectUrl()`. |
| `DefaultSavedRequest` | Implementation phổ biến | Giữ thông tin về request gốc để hỗ trợ chuyển hướng và một số thao tác khôi phục. |
| `ExceptionTranslationFilter` | Security filter | Khi gặp lỗi bảo mật cần bắt đầu xác thực, có thể dùng `RequestCache` để lưu request rồi kích hoạt `AuthenticationEntryPoint`. |
| `LoginUrlAuthenticationEntryPoint` | Authentication entry point cho form login | Redirect tới trang login, ví dụ `/login`. |
| `UsernamePasswordAuthenticationFilter` | Authentication filter | Xử lý POST login theo cấu hình; xác thực username/password. |
| `SavedRequestAwareAuthenticationSuccessHandler` | Success handler | Sau đăng nhập thành công, ưu tiên URL saved request nếu các lựa chọn cấu hình không ghi đè. |
| `RequestCacheAwareFilter` | Security filter | Truy vấn `RequestCache` để lấy request khớp và có thể bọc request theo thông tin đã lưu. |
| `SecurityContextRepository` | Interface lưu ngữ cảnh | Duy trì `SecurityContext` khi đăng nhập; là trách nhiệm **khác** với lưu URL trước đăng nhập. |

Đường dẫn đã lưu và trạng thái đăng nhập được lưu **vì hai mục đích khác nhau**:

- `SecurityContext` / `Authentication` trả lời “request mới là của ai?”.
- `SavedRequest` trả lời “trước khi phải đăng nhập, trình duyệt muốn mở tài nguyên nào?”.

Có `SavedRequest` không đồng nghĩa đã được xác thực. Có `SecurityContext` hợp lệ cũng không tự bảo đảm còn URL nào cần redirect.

## 3. Luồng đầy đủ: từ GET bị chặn đến GET sau đăng nhập

Một diễn tiến phổ biến:

```text
[1] Browser: GET /private/report?tab=history
             |
             v
    Spring Security filters
             |
     request cần authenticated
             |
             v
    ExceptionTranslationFilter
       | 
       +-- RequestCache.saveRequest(request, response)
       |     -> SavedRequest lưu theo chính sách cache
       |        (thường HttpSessionRequestCache)
       |
       +-- LoginUrlAuthenticationEntryPoint
                 -> HTTP 302 Location: /login

[2] Browser: GET /login
             |
             v
    Trang đăng nhập (trang mặc định hoặc trang tự làm)

[3] Browser: POST /login
             | username/password + CSRF token thích hợp
             v
    Authentication filter + AuthenticationManager
             |
         xác thực thành công
             |
             v
    Lưu Authentication/SecurityContext theo policy
             |
             v
    SavedRequestAwareAuthenticationSuccessHandler
       |
       +-- RequestCache.getRequest(...)
       |       -> đọc SavedRequest nếu còn
       |
       +-- HTTP 302 Location: /private/report?tab=history

[4] Browser: GET /private/report?tab=history
             |
             v
    Security filters khôi phục Authentication từ session
             |
    phân quyền request mới
             |
             v
    Controller trả nội dung, nếu request được phép
```

Sơ đồ mô tả luồng khái niệm; thứ tự chính xác của các filter khác, cách tạo session, tham số query phục vụ request-cache optimization và quyết định response có thể khác theo phiên bản/cấu hình.

Những điều cần chú ý:

1. Request gốc bị chặn **trước khi controller xử lý** theo luồng thông thường. Không phải controller tự ghi nhớ URL.
2. Session/cookie phải sống qua redirect tới login và redirect trở về. Nếu mất cookie/session, server có thể không tìm lại được saved request.
3. Form login thành công nhưng user vẫn không có quyền truy cập URL ban đầu có thể tiếp tục nhận HTTP 403; saved request không cấp thêm quyền.
4. Handler redirect chỉ hướng trình duyệt. **HTTP GET ở bước [4] là request mới** và vẫn đi qua security filters.
5. Khi login sai, nhánh success handler không chạy; thông thường user trở về trang login với thông báo lỗi phù hợp, không đến URL đã lưu.

## 4. Hợp đồng RequestCache và các thao tác cần biết

Spring Security Servlet cung cấp `org.springframework.security.web.savedrequest.RequestCache`, với các thao tác chủ chốt:

```java
// Chữ ký phương thức theo ý tưởng của RequestCache; không phải class chạy độc lập.
void saveRequest(HttpServletRequest request, HttpServletResponse response);

SavedRequest getRequest(
    HttpServletRequest request,
    HttpServletResponse response
);

HttpServletRequest getMatchingRequest(
    HttpServletRequest request,
    HttpServletResponse response
);

void removeRequest(
    HttpServletRequest request,
    HttpServletResponse response
);
```

Đây là các method cần hiểu theo hợp đồng, không nên tự copy thành định nghĩa interface cạnh tranh với Spring Security.

### 4.1. saveRequest: ghi nhớ request phù hợp

`saveRequest` được gọi khi Spring Security cần ghi nhớ request bị gián đoạn để bắt đầu authentication. Với `HttpSessionRequestCache`, thông tin thường được cất trong session dưới dạng một `SavedRequest`.

Không phải request nào cũng được lưu: request thuộc luồng nào, matcher của cache, session policy và nhánh exception translation quyết định. Một GET công khai bình thường không cần bị lưu chỉ vì nó được gọi trước khi login.

### 4.2. getRequest: đọc saved request nếu có

`getRequest` tìm lại `SavedRequest` theo request/response và kho lưu hiện có. Đây là thứ `SavedRequestAwareAuthenticationSuccessHandler` có thể dùng để tìm URL điều hướng.

Lời gọi `getRequest` **không có nghĩa** browser đang gửi lại request gốc. Nó chỉ truy xuất thông tin đã lưu.

### 4.3. getMatchingRequest: tìm request *mới* khớp saved request

Sau khi trình duyệt được redirect về URL cũ, `RequestCacheAwareFilter` có thể dùng `getMatchingRequest`. Nếu request mới thỏa điều kiện match, repository có thể trả một `HttpServletRequest` được bọc để trình bày một số thông tin phù hợp từ `SavedRequest`, đồng thời xử lý/xóa entry cache theo implementation.

Ở các cấu hình Spring Security 6, truy vấn saved request có thể được tối ưu bằng một tham số nhận diện trên request (ví dụ `continue` tùy cấu hình). Vì vậy **đừng giả định** `getMatchingRequest` luôn đọc session trên mọi request, hay chỉ cần URL giống nhau là mọi implementation đều trả wrapper.

### 4.4. removeRequest: xóa saved request khi không dùng nữa

`removeRequest` xóa thông tin đã ghi nhớ theo ngữ nghĩa của cache. Việc này hữu ích nếu ứng dụng cố ý chuyển người dùng tới đích khác, hủy luồng hoặc muốn tránh sử dụng URL cũ trong tương lai.

**Không phải cứ gọi `getRequest` là lập tức xóa entry.** Trong một luồng redirect, handler có thể cần để saved request tồn tại cho request tiếp theo; việc loại bỏ có thể diễn ra ở các thời điểm khác nhau theo handler và cache.

## 5. SavedRequest giữ những gì và không giữ những gì?

`SavedRequest` có `getRedirectUrl()` để đưa browser đến URL phù hợp; `DefaultSavedRequest` còn có thể lưu các đặc điểm request như đường dẫn, scheme, host/port, query, method, headers, parameters, locale hoặc cookies tùy implementation. Không nên phụ thuộc một danh sách tuyệt đối bất biến mà không xem phiên bản.

Ví dụ:

```text
Original:
  method: GET
  URL:    https://app.example.test/private/report?tab=history
  Accept: text/html
  Cookie: session=...

SavedRequest:
  redirect target ~= https://app.example.test/private/report?tab=history
  + metadata hỗ trợ matching/wrapping theo implementation
```

Đừng nhầm metadata đã lưu với dữ liệu có thể được **replay an toàn**. Những thứ không nên mặc nhiên kỳ vọng được khôi phục nguyên vẹn:

- Request body được stream một lần (multipart upload, JSON lớn, form POST có side effect).
- Mọi trạng thái server-side của controller hay transaction đang dang dở.
- Authorization của user vừa đăng nhập: quyền được kiểm tra lại trên request mới.
- Kết quả POST gốc, giá trị CSRF token của một request độc lập hoặc tác dụng phụ HTTP.
- Mọi header do proxy/browser sinh ra trong request ban đầu.

**RequestCache không phải cơ chế transaction replay.** Nếu sản phẩm cần khôi phục giỏ hàng, bản nháp hoặc quy trình nhiều bước sau login, hãy lưu dữ liệu nghiệp vụ có kiểm soát trong kho phù hợp; chỉ dùng saved request để hỗ trợ điều hướng.

## 6. Redirect trở lại URL khác với phát lại HTTP request

Một trường hợp dễ hiểu sai:

```text
Chưa đăng nhập:
  POST /checkout/confirm
  body: shippingAddress=...&paymentSelection=...

Sau form login thành công:
  HTTP 302 Location: /checkout/confirm
  Browser thường tạo GET /checkout/confirm
```

Điều đó **không có nghĩa** server phát lại POST trước đó. Với redirect 302 thông thường, browser thường chuyển sang GET; hành vi chính xác phụ thuộc mã redirect và client. Không tự gắn `307` hoặc `308` để giữ method/body trong một luồng authentication khi chưa phân tích rủi ro replay giao dịch.

Hệ quả:

- Nếu endpoint chỉ hỗ trợ POST, GET sau login có thể nhận 405 hoặc một response khác mong đợi.
- Việc gửi lại body nhạy cảm hoặc thao tác có side effect có thể gây lỗi/nhân đôi lệnh.
- CSRF token thuộc một request có quy tắc riêng; không dựa vào request cache để vượt qua CSRF.
- Với luồng “POST sau khi đăng nhập”, thiết kế phổ biến hơn là dẫn người dùng đến trang GET/step của giao dịch, xác thực trạng thái và để họ chủ động submit lại.

Một kiến trúc an toàn hơn:

```text
GET /checkout/confirm-page
    -> nếu chưa login: ghi nhớ GET, redirect login
    -> sau login: quay lại trang GET, dựng dữ liệu từ server
    -> người dùng xác nhận
POST /checkout/confirm (CSRF + authorization + idempotency check)
    -> xử lý một lần theo kiểm soát nghiệp vụ
```

Đừng dùng `SavedRequest` như nơi chứa dữ liệu thanh toán, mật khẩu, token hoặc thông tin có quyền riêng tư cao. Trường hợp cần dữ liệu nháp phải có chính sách thời hạn, quyền truy cập, giới hạn kích thước và bảo mật phù hợp.

## 7. RequestCache và Session: vì sao cookie rất quan trọng?

Với `HttpSessionRequestCache`, request ban đầu và request login sau đó cần liên kết đến đúng `HttpSession`. Browser thường dùng session cookie để liên kết.

Giả sử:

```text
GET /private/report
  -> server: lưu saved request vào session S1
  -> browser: nhận cookie nhận diện S1

GET /login, POST /login
  -> browser: gửi lại cookie phù hợp
  -> server: tìm saved request trong session hiện hành
  -> success handler: redirect về /private/report
```

Nếu cookie bị chặn, đổi domain/path không phù hợp, session hết hạn hoặc bị vô hiệu hóa, login thành công có thể sử dụng fallback target thay vì URL gốc.

**Session fixation protection:** Spring Security có thể thay đổi session ID khi đăng nhập thành công. Đây là cơ chế bảo vệ, không mặc định có nghĩa saved request biến mất. Tuy nhiên test và hệ thống thực cần dùng session sau xác thực cho request tiếp theo, không dựa vào một session identifier hardcode.

Khi chạy trên nhiều node, session cần có chiến lược chia sẻ/định tuyến phù hợp; `RequestCache` không tự bảo đảm mọi server cùng đọc được session. Với ứng dụng stateless, lưu SavedRequest vào HTTP session có thể đi ngược chính sách.

## 8. Spring Security 6: default, request-cache optimization và lựa chọn khác

### 8.1. HttpSessionRequestCache

`HttpSessionRequestCache` phù hợp với form login dựa trên session và muốn điều hướng về URL được yêu cầu trước xác thực. Ở các cấu hình Spring Security Servlet thông thường, framework có thể cung cấp nó mặc định.

Với Spring Security 6, cơ chế khớp saved request được tối ưu để hạn chế truy xuất session không cần thiết. Một số cấu hình dùng tham số nhận diện, chẳng hạn `continue`. Tên tham số và hành vi thực tế cần được xác minh theo version/cấu hình đang dùng; **đừng hardcode tham số này vào mọi link** hoặc tự sửa query của URL lưu mà chưa hiểu request cache.

Nếu yêu cầu tối ưu hoặc logic match đặc biệt, có thể cấu hình `HttpSessionRequestCache` một cách tường minh; cần kiểm thử đầy đủ luồng redirect trên phiên bản sử dụng.

### 8.2. NullRequestCache

`NullRequestCache` không ghi nhớ yêu cầu để phục hồi theo session. Đây là một lựa chọn thường thích hợp với REST API stateless:

```java
// Đoạn cấu hình đặt trong SecurityFilterChain bean, không chạy độc lập.
http.requestCache(cache -> cache.requestCache(new NullRequestCache()));
```

Cần import `org.springframework.security.web.savedrequest.NullRequestCache` và biến `http` là `HttpSecurity` đang cấu hình.

Nhưng **NullRequestCache không tự biến toàn bộ ứng dụng thành stateless**; còn phải thiết kế session management, security context, authentication entry point và các filter khác. Ngược lại, cấu hình `SessionCreationPolicy.STATELESS` mà vẫn kỳ vọng browser quay lại URL được lưu trong session thường là mâu thuẫn mục tiêu.

### 8.3. API JSON và form login là hai trải nghiệm khác nhau

Với SPA/mobile API, một response 401 JSON rõ ràng để client tự dẫn tới login rồi tự nhớ route có thể phù hợp hơn redirect HTML. `RequestCache` vẫn là abstraction của framework, nhưng không phải mọi API đều nên bật lưu request và trả redirect.

**Không dùng một saved-request trong session làm nguồn điều hướng đáng tin cậy vô điều kiện cho client khác**. Nếu tự dựng `returnUrl` query hoặc header, cần kiểm tra URL đích để tránh open redirect.

## 9. SavedRequestAwareAuthenticationSuccessHandler: chọn đích sau login

Trong form login mặc định, handler thuộc họ `SavedRequestAwareAuthenticationSuccessHandler` thường xử lý success redirect. Nó có khả năng lấy URL từ `RequestCache`, nhưng cấu hình có thể thay đổi thứ tự ưu tiên.

Tư duy cơ bản:

```text
Authentication success
      |
      v
Cấu hình "luôn tới default target"?
      |
      +-- Có --> redirect URL mặc định đã cấu hình
      |
      +-- Không --> Có tham số targetUrl được phép sử dụng?
                     |
                     +-- Có --> redirect theo policy đã cấu hình
                     |
                     +-- Không --> Có SavedRequest?
                                   |
                                   +-- Có --> redirect SavedRequest.getRedirectUrl()
                                   |
                                   +-- Không --> redirect default target
```

Cần hiểu đúng hai trường hợp đối lập:

**Trường hợp A:** người dùng mở `/private/report`, bị chuyển tới login, sau đó đăng nhập thành công. Saved request vẫn tồn tại và cấu hình không ghi đè ⇒ handler thường redirect về `/private/report`.

**Trường hợp B:** người dùng truy cập trực tiếp trang login và đăng nhập, chưa có saved request ⇒ handler dùng default target (có thể là `/` nếu chưa tùy chỉnh).

### 9.1. Tùy chỉnh defaultSuccessUrl

Ví dụ:

```java
// Một lựa chọn riêng cho form login:
http.formLogin(form -> form
    .defaultSuccessUrl("/dashboard", true)
);
```

`true` ở đây yêu cầu **luôn dùng default success URL**, vì vậy có thể **bỏ qua URL SavedRequest làm đích**. Nếu mục tiêu là quay lại nơi ban đầu, không cấu hình kiểu “always use default target” một cách vô tình.

Với lựa chọn false hoặc mặc định tương ứng, handler có thể vẫn ưu tiên saved request khi có. Phân tích trên là quy tắc form-login success handler thông thường, không áp dụng nếu ứng dụng thay bằng success handler riêng.

### 9.2. Custom AuthenticationSuccessHandler

Khi tự thay success handler bằng lambda viết response JSON, logic saved-request redirect của default handler có thể **không còn hoạt động**. Nếu muốn giữ hành vi phục hồi, cần chủ động tích hợp `RequestCache` hoặc ủy quyền cho handler thích hợp.

Không tự lấy `SavedRequest.getRedirectUrl()` rồi redirect sang host bất kỳ mà thiếu xác minh host/context path. Kiểm tra reverse-proxy headers và cấu hình trusted proxy để tránh Host header poisoning hoặc open redirect trong triển khai cụ thể.

## 10. Ví dụ Spring Boot 3/Java 17 chạy được: GET bị chặn, login và trở lại URL cũ

Ví dụ dùng **Spring Boot 3.3.5 + Spring Security Servlet + Maven + Java 17**. Mục tiêu là tạo một `HttpSessionRequestCache` tường minh, một route được bảo vệ, form login chuẩn và kiểm thử lưu/đọc SavedRequest.

### 10.1. Cấu trúc dự án

```text
saved-request-demo/
  pom.xml
  src/
    main/java/demo/savedrequest/
      SavedRequestDemoApplication.java
      SecurityConfig.java
      PageController.java
    test/java/demo/savedrequest/
      SavedRequestFlowTest.java
```

### 10.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>saved-request-demo</artifactId>
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
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

### 10.3. Lớp khởi động

`src/main/java/demo/savedrequest/SavedRequestDemoApplication.java`:

```java
package demo.savedrequest;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SavedRequestDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(SavedRequestDemoApplication.class, args);
    }
}
```

### 10.4. SecurityConfig

`src/main/java/demo/savedrequest/SecurityConfig.java`:

```java
package demo.savedrequest;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.savedrequest.HttpSessionRequestCache;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails learner = User.withUsername("lan")
            .password(encoder.encode("demo-password"))
            .roles("USER")
            .build();
        return new InMemoryUserDetailsManager(learner);
    }

    @Bean
    HttpSessionRequestCache requestCache() {
        return new HttpSessionRequestCache();
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            HttpSessionRequestCache cache) throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/public").permitAll()
                .anyRequest().authenticated())
            .requestCache(config -> config.requestCache(cache))
            .formLogin(form -> form.permitAll());

        return http.build();
    }
}
```

Giải thích:

1. `HttpSessionRequestCache` được đăng ký tường minh để test có thể kiểm tra saved request thông qua cùng instance.
2. `authorizeHttpRequests` yêu cầu đăng nhập cho `/private/report`; `/` và `/public` có thể truy cập anonymous.
3. `formLogin(form -> form.permitAll())` bật form login và cho phép truy cập các endpoint login thích hợp; không cần tự viết controller `POST /login`.
4. `BCryptPasswordEncoder` hash password demo khi tạo user. Đây là tài khoản học tập, không phải cách cấp tài khoản production.
5. Không gán `defaultSuccessUrl("/dashboard", true)` hoặc custom success handler, để có thể quan sát behavior dùng saved request.
6. Ví dụ dựa vào session; không đồng thời cấu hình `SessionCreationPolicy.STATELESS`.

### 10.5. Controller

`src/main/java/demo/savedrequest/PageController.java`:

```java
package demo.savedrequest;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PageController {

    @GetMapping("/")
    String home() {
        return "home";
    }

    @GetMapping("/public")
    String publicPage() {
        return "public";
    }

    @GetMapping("/private/report")
    String report(Authentication authentication,
                  @RequestParam(defaultValue = "overview") String tab) {
        return "report:" + authentication.getName() + ":" + tab;
    }
}
```

`@RestController` đơn giản hóa kết quả body để kiểm chứng flow; form login mặc định vẫn có trang đăng nhập HTML do Spring Security cung cấp.

### 10.6. MockMvc: chứng minh request đã lưu và redirect về URL gốc

`src/test/java/demo/savedrequest/SavedRequestFlowTest.java`:

```java
package demo.savedrequest;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.security.web.savedrequest.HttpSessionRequestCache;
import org.springframework.security.web.savedrequest.SavedRequest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SavedRequestFlowTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    HttpSessionRequestCache requestCache;

    @Test
    void protectedUrlIsSavedAndRestoredAfterFormLogin()
            throws Exception {

        MvcResult first = mvc.perform(
                get("/private/report?tab=history"))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        String loginRedirect = first.getResponse().getRedirectedUrl();
        assertNotNull(loginRedirect);
        assertTrue(loginRedirect.contains("/login"));

        SavedRequest saved = requestCache.getRequest(
            first.getRequest(), first.getResponse()
        );
        assertNotNull(saved);
        assertTrue(saved.getRedirectUrl()
            .contains("/private/report?tab=history"));

        MockHttpSession beforeLogin =
            (MockHttpSession) first.getRequest().getSession(false);
        assertNotNull(beforeLogin);

        MvcResult loggedIn = mvc.perform(post("/login")
                .session(beforeLogin)
                .with(csrf())
                .param("username", "lan")
                .param("password", "demo-password"))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        String target = loggedIn.getResponse().getRedirectedUrl();
        assertNotNull(target);
        assertTrue(target.contains("/private/report?tab=history"));

        // Lấy session sau login để không phụ thuộc session fixation ID.
        MockHttpSession afterLogin =
            (MockHttpSession) loggedIn.getRequest().getSession(false);
        assertNotNull(afterLogin);

        mvc.perform(get("/private/report?tab=history")
                .session(afterLogin))
            .andExpect(status().isOk())
            .andExpect(content().string("report:lan:history"));
    }

    @Test
    void publicUrlDoesNotRequireAuthentication() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));
    }

    @Test
    void directLoginWithoutSavedRequestUsesFallback()
            throws Exception {
        mvc.perform(post("/login")
                .with(csrf())
                .param("username", "lan")
                .param("password", "demo-password"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/"));
    }

    @Test
    void wrongPasswordDoesNotEnterSuccessRedirectFlow()
            throws Exception {
        mvc.perform(post("/login")
                .with(csrf())
                .param("username", "lan")
                .param("password", "wrong-password"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login?error"));
    }
}
```

Các điểm kiểm thử đáng chú ý:

- Test đầu gọi **GET thật qua MockMvc filter chain**, không tạo một `SavedRequest` giả trong test. `requestCache.getRequest(...)` kiểm tra việc cache đã có saved URL.
- Test giữ session giữa request bị chặn và login. Sau login, test lấy session hiện hành rồi gửi request GET mới tới đích; controller nhận principal `lan`.
- Sử dụng `.with(csrf())` để mô phỏng form login có CSRF token hợp lệ theo mặc định của Spring Security.
- Không so sánh cứng scheme/host/port của `getRedirectUrl` vì URL có thể là absolute URL với `http://localhost` trong MockMvc.
- Test thất bại password chỉ kiểm tra nhánh failure URL, không đánh đồng nó với saved-request success flow.

### 10.7. Chạy thử

Trong thư mục dự án có `pom.xml`, cài JDK 17+ và Maven:

```bash
mvn test
mvn spring-boot:run
```

Nếu environment và dependencies tương ứng hợp lệ, **4 bài kiểm thử dự kiến pass**. Không có stdout Maven cố định do timestamp, JVM và môi trường khác nhau.

Kết quả HTTP có thể quan sát trong bộ test:

| Bước | HTTP response dự kiến | Ghi chú |
| --- | --- | --- |
| Anonymous GET `/private/report?tab=history` | 302 tới login | URL gốc được lưu vào RequestCache. |
| POST `/login` đúng password và session trước đó | 302 tới URL đã lưu | Success handler chọn saved target. |
| GET lại URL gốc với session sau login | 200, body `report:lan:history` | Một request GET mới; không phải replay request trước. |
| GET `/public` | 200, body `public` | Không cần xác thực. |
| POST `/login` đúng password nhưng không có saved URL | 302 tới `/` | Default target. |
| POST `/login` password sai | 302 tới `/login?error` | Failure handler, không dùng success redirect. |

Ví dụ cố ý không thêm endpoint POST làm thay đổi dữ liệu trong phần test. Điều đó tránh làm người đọc nhầm request cache với công cụ tự động chạy lại POST có tác dụng phụ.

## 11. Java 17 độc lập: mô phỏng lưu URL và điều hướng

Để quan sát ý nghĩa “saved URL” mà không cần chạy server, có thể dùng một mô hình thuần Java. **Đây là code minh họa, không phải implementation `RequestCache` của Spring Security**.

Tạo file `SavedNavigationDemo.java`:

```java
public class SavedNavigationDemo {

    record SavedRequest(String method, String url) {}

    static class Session {
        private SavedRequest saved;

        void save(String method, String url) {
            this.saved = new SavedRequest(method, url);
        }

        String redirectAfterLogin() {
            return saved == null ? "/" : saved.url();
        }

        void clear() {
            saved = null;
        }
    }

    public static void main(String[] args) {
        Session session = new Session();

        session.save("GET", "/private/report?tab=history");

        System.out.println("saved method: " + "GET");
        System.out.println("redirect: " + session.redirectAfterLogin());
        System.out.println("browser request: GET " +
            session.redirectAfterLogin());

        session.clear();
        System.out.println("after clear: " +
            session.redirectAfterLogin());
    }
}
```

Chạy:

```bash
javac SavedNavigationDemo.java
java SavedNavigationDemo
```

Stdout **chính xác** với Java 17:

```text
saved method: GET
redirect: /private/report?tab=history
browser request: GET /private/report?tab=history
after clear: /
```

Mô hình này chỉ ghi nhớ URL và xóa entry, không có Servlet request wrapper, session cookie, CSRF hoặc xác thực thật. Nó giúp phân biệt **ghi nhớ hướng đi** và **request HTTP mới của browser**, còn phần 10 chứng minh pipeline Spring Security thực tế.

## 12. Một số lựa chọn cấu hình thường gặp

### 12.1. Bỏ qua việc lưu request ở các URL không thích hợp

Nếu `favicon.ico`, `/error` hoặc các resource phụ bị yêu cầu xác thực và làm phát sinh request cache, URL mong muốn của người dùng có thể bị thay thế bằng resource phụ. Cách tốt nhất thường là cấu hình authorization/matcher hợp lý cho static resources và error handling, không chỉ “dọn saved request” sau login.

`HttpSessionRequestCache` hỗ trợ matcher để giới hạn những request được lưu; khi đặt custom `RequestMatcher` cần bảo đảm chỉ giữ các request thực sự có ý nghĩa phục hồi sau login, và kiểm thử trực tiếp. Không mặc định tất cả request GET đều nên được cache.

### 12.2. Khi có nhiều SecurityFilterChain

`FilterChainProxy` chọn chain đầu tiên khớp request, sau đó request-cache và login configuration của chain đó mới có ý nghĩa. Một chain API stateless và một chain form-login có thể dùng chính sách khác nhau; đừng vô tình tắt cache ở chain dùng form login vì đã cấu hình `NullRequestCache` ở chain khác.

Ví dụ khái niệm:

```text
/api/**:
  bearer token / stateless
  NullRequestCache
  401 JSON

browser pages:
  session + formLogin
  HttpSessionRequestCache
  redirect login + redirect saved URL
```

Đây là thiết kế hai chain **minh họa**, không phải code có thể copy y nguyên. Cần cấu hình `securityMatcher`, thứ tự `@Order` và fallback phù hợp.

### 12.3. Khi thay success handler hoặc entry point

- Custom `AuthenticationSuccessHandler` cần chủ động quyết định có dùng saved request hay không.
- Custom `AuthenticationEntryPoint` trả 401 JSON thay vì redirect có thể làm thay đổi hoàn toàn trải nghiệm login.
- Filter authentication khác form login có thể không dùng `SavedRequestAwareAuthenticationSuccessHandler`.
- Cơ chế `RequestCache` và cơ chế lưu `SecurityContext` phải phối hợp với cùng mô hình session, nhưng chúng vẫn là hai trách nhiệm độc lập.

## 13. Bảo mật: không biến URL lưu thành chỗ phát sinh lỗi mới

### 13.1. Open redirect và host/proxy headers

Một hệ thống có URL redirect được điều khiển từ query, header hoặc reverse proxy cần chống chuyển hướng ra domain không được phép. `SavedRequest` được tạo từ request server nhận, nhưng tuyệt đối không suy ra mọi URL trả về từ header bên ngoài đều đáng tin.

Nếu tự viết success handler:

- Ưu tiên relative path nội bộ khi có thể; với URL tuyệt đối, kiểm tra scheme/host/port theo allowlist.
- Chỉ tin `Forwarded` hoặc `X-Forwarded-*` từ proxy đáng tin, cấu hình container/framework phù hợp.
- Không nối chuỗi URL thiếu kiểm tra từ query parameter vào `sendRedirect`.
- Kiểm thử với input độc hại, đường dẫn encoded hoặc host header bị thao túng.

### 13.2. SavedRequest không thay thế authorization

Người dùng có thể được redirect về `/admin` sau khi login nhưng vẫn không có `ROLE_ADMIN`. Tại request mới, `AuthorizationFilter` vẫn áp dụng quy tắc bảo vệ. Đừng thêm “bypass authorization nếu URL là SavedRequest” vì sẽ mở lỗ hổng.

### 13.3. Dữ liệu session, kích thước và thời hạn

Saved request có thể chứa metadata phản ánh URL và một số thông tin HTTP. Cần kiểm soát request quá lớn, URL chứa dữ liệu nhạy cảm, session expiry, số lượng lần ghi và các trường hợp nhiều tab cùng tương tác.

Không chèn access token, mật khẩu hoặc dữ liệu cá nhân nhạy cảm vào query string để “sau login lấy lại”. URL có thể xuất hiện trong history, log và referer ngoài dự kiến.

### 13.4. Các thao tác thay đổi trạng thái

Không dùng redirect sau login để tự gửi lại POST thanh toán, xóa dữ liệu hoặc thay đổi mật khẩu. Các thao tác có side effect cần CSRF protection khi thích hợp, authorization, validation và idempotency riêng. Nếu cần khôi phục công việc dở dang, lưu draft an toàn phía server rồi mở lại bằng GET.

## 14. Debug: vì sao login thành công nhưng không trở lại URL cũ?

Thực hiện lần lượt theo dòng chảy:

1. **Request gốc có thật sự bị chặn để bắt đầu authentication không?** Nếu endpoint công khai hoặc filter khác chặn sớm, `ExceptionTranslationFilter` có thể không save request như mong muốn.
2. **Đúng SecurityFilterChain chưa?** Xem `securityMatcher` và cấu hình request cache của chain thực tế.
3. **Có lưu vào RequestCache không?** Sau GET được bảo vệ, kiểm tra session và `getRequest`, dùng test hoặc breakpoint thay vì đoán.
4. **Session/cookie có được giữ qua GET login và POST login không?** Kiểm tra cookie policy, session expiration, proxy, SameSite, HTTP/HTTPS và session fixation.
5. **Authentication có thành công không?** Nếu login thất bại, success handler không chạy; phân biệt response `/login?error`.
6. **Success handler nào đang dùng?** Có `SavedRequestAwareAuthenticationSuccessHandler` hay custom handler? `alwaysUseDefaultTargetUrl` hoặc target parameter có ghi đè không?
7. **Redirect URL cuối là gì?** Đọc HTTP `Location`; tuyệt đối không log credential/token.
8. **Request mới sau redirect có đúng method/path/query không?** GET sau redirect là một request khác; không trông chờ POST body cũ.
9. **User còn quyền truy cập đích không?** Nếu không đủ quyền, redirect thành công vẫn có thể dẫn đến 403.
10. **Có nhiều tab hoặc request resource phụ ghi đè cache không?** Kiểm tra matcher/cache policy và luồng đồng thời.
11. **Có cấu hình stateless/NullRequestCache không?** Nếu có, việc không phục hồi theo session có thể là thiết kế chủ đích.
12. **Có yêu cầu đặc biệt với `getMatchingRequest` không?** Trong Spring Security 6, request-cache optimization và tham số match có thể ảnh hưởng cách wrapper/cache được xử lý sau redirect.

Trong môi trường phát triển, có thể xem log:

```properties
logging.level.org.springframework.security=DEBUG
```

Log DEBUG giúp thấy authentication/redirect/filter tương ứng trong nhiều trường hợp nhưng không chắc in toàn bộ state của RequestCache. Khi cần xác minh vị trí lưu/đọc, dùng breakpoint hoặc integration test với `HttpSessionRequestCache`. Không xuất cookie/session ID/password vào log production.

### Bảng lỗi thường gặp

| Biểu hiện | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| Sau login luôn về `/` dù trước đó mở URL riêng | Không có SavedRequest; cache không lưu; success handler override target | Kiểm tra `saveRequest`, session, `alwaysUseDefaultTargetUrl` và custom success handler. |
| Sau login về `/login` hoặc `/error` | URL phụ không được permit, hoặc request khác ghi đè saved target | Kiểm tra matcher và resource/error routes. |
| Đích sau login bị 403 | Đăng nhập thành công nhưng thiếu quyền | Đánh giá authorization của request mới, không bỏ kiểm tra. |
| Đích sau login bị 405 | Request gốc là POST, redirect tạo GET | Thiết kế lại workflow GET/POST; không mong request replay. |
| Mất URL khi đổi domain/subdomain | Session cookie không được gửi phù hợp | Kiểm tra cookie Domain/Path/SameSite/Secure và proxy. |
| API mobile nhận 302 HTML thay vì 401 JSON | Đang đi qua chain form login / entry point web | Tách đúng API chain và authentication entry point. |
| Redirect sang host lạ | Custom redirect logic hoặc trusted-proxy/Host handling không an toàn | Kiểm tra allowlist và chỉ tin proxy hợp lệ. |
| Saved request không tự bị xóa như dự đoán | `getRequest` không nhất thiết remove; matching optimization/cấu hình khác | Hiểu `getMatchingRequest` / `removeRequest` và test vòng đời. |
| Hai tab login dẫn về URL “không đúng tab” | Saved request session có thể được ghi lại khi nhiều yêu cầu cạnh tranh | Thiết kế multi-tab UX riêng nếu cần, không giả định mỗi tab có một cache độc lập. |

## 15. Câu hỏi tự kiểm tra

**Câu 1.** Anonymous mở `GET /private/report` và bị redirect đến login. Thành phần nào thường đưa request vào cache?

**Đáp án:** Trong luồng form login điển hình, `ExceptionTranslationFilter` khi khởi động authentication sẽ yêu cầu `RequestCache.saveRequest(...)`. `HttpSessionRequestCache` là nơi lưu trong session khi được dùng.

**Câu 2.** `SavedRequest` và `SecurityContext` có giống nhau không?

**Đáp án:** Không. `SavedRequest` giữ thông tin request trước login, còn `SecurityContext` giữ trạng thái `Authentication` để xác định danh tính cho request đang xử lý và các request tiếp theo theo chính sách.

**Câu 3.** Sau login thành công, server có tự phát lại `POST /checkout/confirm` cùng body ban đầu không?

**Đáp án:** Không được mặc định như vậy. Handler thường redirect browser tới URL lưu, trình duyệt tạo một request mới, phổ biến là GET với redirect 302. Cần thiết kế riêng cho thao tác có side effect.

**Câu 4.** Có SavedRequest nhưng controller vẫn không chạy, response là 403. Tại sao?

**Đáp án:** Saved request không cấp quyền. Request sau redirect vẫn qua authorization, và user có thể không đủ authority.

**Câu 5.** Tại sao `defaultSuccessUrl("/dashboard", true)` có thể làm mất hành vi quay lại trang cũ?

**Đáp án:** Vì cờ `true` yêu cầu luôn dùng default target trong success handler tương ứng, ghi đè saved target.

**Câu 6.** Tại sao `NullRequestCache` phù hợp với nhiều API stateless?

**Đáp án:** Vì API thường cần trả 401 và để client tự xử lý login/route; không cần giữ saved request trong session. Tuy nhiên còn phải cấu hình session và authentication phù hợp.

**Câu 7.** `getRequest` và `getMatchingRequest` khác nhau ở đâu?

**Đáp án:** `getRequest` trả SavedRequest được lưu nếu có; `getMatchingRequest` cố tìm một HTTP request hiện tại khớp saved request, có thể trả wrapper và xử lý vòng đời cache theo implementation. Đừng giả định đọc là xóa.

**Câu 8.** Khi có nhiều tab cùng một session, mỗi tab chắc chắn được khôi phục đúng URL của chính nó không?

**Đáp án:** Không có bảo đảm chỉ nhờ một `HttpSessionRequestCache` đơn giản; các request khác có thể thay đổi saved target. Nếu UX yêu cầu phân biệt tab/flow, cần thiết kế trạng thái riêng.

## 16. Ghi nhớ cốt lõi

- `RequestCache` quản lý thông tin request bị gián đoạn; `SavedRequest` là mô tả đã lưu; `HttpSessionRequestCache` thường dùng session.
- `ExceptionTranslationFilter` có thể lưu request và khởi động login; `SavedRequestAwareAuthenticationSuccessHandler` chọn redirect về saved URL sau login thành công theo policy.
- Browser **gửi HTTP request mới** đến URL được redirect; server không tự tái thực thi POST body hoặc transaction đã bắt đầu.
- `RequestCacheAwareFilter`/`getMatchingRequest` hỗ trợ matching và có thể xử lý vòng đời SavedRequest, nhưng behavior phụ thuộc cache implementation và Spring Security version.
- Session/cookie, success handler, default target, security chain và request-cache matcher quyết định liệu URL gốc có được phục hồi hay không.
- Saved request **không bỏ qua authorization** và không thay thế CSRF, idempotency, kiểm tra URL redirect hoặc quản lý dữ liệu nháp.
- Kiểm thử thực tế theo chuỗi **GET protected → saved URL → POST login + CSRF → Location saved URL → GET mới với session → authorization/controller**.
