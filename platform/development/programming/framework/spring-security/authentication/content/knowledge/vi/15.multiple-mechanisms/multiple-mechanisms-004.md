# Xác định thứ tự khi một yêu cầu có nhiều loại thông tin xác thực

## 1. Một HTTP request có thể mang nhiều credential cùng lúc

Trong ứng dụng Spring Security Servlet, một request có thể đồng thời có:

- Cookie `JSESSIONID` trỏ tới HTTP session đã đăng nhập bằng form.
- Header `Authorization: Basic …` chứa username/password.
- Header `Authorization: Bearer …` chứa access token.
- Header tự định nghĩa như `X-API-Key`.
- Chứng chỉ client TLS, hoặc danh tính do reverse proxy đáng tin cậy chuyển tiếp.
- Remember-me cookie hoặc thông tin từ cơ chế đăng nhập khác.

Ví dụ request dưới đây mang **hai nguồn chứng thực khác nhau**:

~~~http
GET /api/me HTTP/1.1
Host: example.test
Cookie: JSESSIONID=<browser-session-id>
Authorization: Basic <base64-api-user-password>
~~~

Giả sử session thuộc `web-alice` nhưng Basic credential thuộc `api-reader`. Vậy backend dùng danh tính nào để đánh giá quyền?

Không có quy tắc phổ quát kiểu **“cookie luôn thắng”**, **“Authorization luôn thắng”** hoặc **“credential có độ bảo mật cao nhất tự động thắng”**. Kết quả phụ thuộc vào cấu hình Spring Security: request đi vào `SecurityFilterChain` nào, filter nào được bật, cách mỗi filter nhận diện credential, filter nào có thể kết thúc request, và đối tượng `Authentication` cuối cùng trong `SecurityContext`.

Một chi tiết dễ bỏ qua: `Authorization` thông thường chứa **một authentication scheme tại một thời điểm** (ví dụ `Basic` *hoặc* `Bearer`). Không ghép hai scheme vào cùng một giá trị. Nếu client/proxy gửi nhiều header `Authorization` hoặc header mâu thuẫn, cần xử lý theo chính sách rõ ràng (thường từ chối request mơ hồ), không tin vào cách container chọn “dòng đầu” hay “dòng cuối”.

Bài này xét **Spring Boot 3.x, Spring Security 6.x, Java 17+ và ứng dụng Servlet/Spring MVC**. Nó tập trung vào cách **xác định thứ tự và chọn nguồn danh tính** khi có nhiều cơ chế, không biến mọi cơ chế thành một cấu hình duy nhất.

## 2. Phải phân biệt bốn loại “thứ tự”

Khi debug một request có nhiều credential, hãy hỏi bốn câu theo thứ tự sau:

| Lớp quyết định | Thành phần | Câu hỏi cần trả lời |
| --- | --- | --- |
| **1. Thứ tự chọn chain** | `FilterChainProxy` và `SecurityFilterChain`, `@Order`, `securityMatcher` | Request này được *chain nào* xử lý? |
| **2. Thứ tự filter trong chain** | `SecurityContextHolderFilter`, filter xác thực, `AnonymousAuthenticationFilter`, `AuthorizationFilter`… | Filter nào *thực sự chạy*, đọc credential nào, có ghi lại context hoặc kết thúc request không? |
| **3. Thứ tự provider/manager** | `AuthenticationManager`, thường là `ProviderManager` và các `AuthenticationProvider` | Sau khi một filter tạo token xác thực, provider nào kiểm tra token đó trước? |
| **4. Chính sách nguồn danh tính** | Thiết kế API/web, session policy, authentication entry point, rule quyền | Ứng dụng **muốn** chấp nhận, bỏ qua hay từ chối các credential đồng thời? |

Bốn thứ tự này **không thay thế lẫn nhau**:

- Đặt `@Order(1)` cho một `SecurityFilterChain` **không** có nghĩa HTTP Basic luôn có độ ưu tiên hơn JWT ở mọi URL.
- Thêm `.requestMatchers("/api/**").authenticated()` vào phần authorization **không** tự chọn chain API; cần `http.securityMatcher(...)` ở cấp chain.
- Thay đổi thứ tự `AuthenticationProvider` không tự thay đổi thứ tự `BasicAuthenticationFilter` và `BearerTokenAuthenticationFilter`.
- Cho phép hai phương thức login trong cùng chain không tạo ra quy tắc tự động “fallback khi phương thức trước sai”.

**Mục tiêu tốt nhất:** chọn cơ chế xác thực được phép theo **endpoint hoặc protocol contract**, sau đó kiểm thử cặp credential xung đột. Tránh phụ thuộc vào thứ tự filter vô tình hình thành do cấu hình.

## 3. Bước 1: FilterChainProxy chọn chain đầu tiên khớp request

Spring Security Servlet nhận request qua `FilterChainProxy`. Một ứng dụng có thể đăng ký nhiều bean `SecurityFilterChain`:

~~~text
Request: GET /api/me, Cookie + Authorization: Basic
                     |
                     v
              FilterChainProxy
                     |
           @Order(1) apiChain
           securityMatcher("/api/**")?
                     |
                    YES
                     |
                CHỌN apiChain
                     |
            Không xét webChain nữa
                     |
            Các filter của apiChain
                     |
                Controller
~~~

Chỉ **chain đầu tiên khớp** được gọi. Spring Security không lấy filter của chain API ghép với filter của chain Web. Cũng không chuyển sang chain thấp hơn nếu chain đầu tiên trả `401`, `403` hoặc xác thực thất bại.

Giả sử hai chain:

~~~java
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    http.securityMatcher("/api/**");
    // ...
    return http.build();
}

@Bean
SecurityFilterChain webChain(HttpSecurity http) throws Exception {
    // Không khai báo securityMatcher -> fallback cho request còn lại.
    // ...
    return http.build();
}
~~~

Đây là đoạn **minh họa vị trí matcher**, chưa phải cấu hình đầy đủ; phần code chạy được có ở mục 8.

Một bảng routing:

| URL request | Chain được chọn | Điều gì quyết định? |
| --- | --- | --- |
| `GET /api/me` | API | `@Order(1)` được xét trước, matcher `/api/**` khớp. |
| `GET /api/admin` | API | Cùng prefix API. |
| `GET /web/me` | Web | Không khớp API; web fallback. |
| `POST /login` | Web | Không khớp API; form login filter của web xử lý. |
| `GET /unknown` | Web | Fallback bảo vệ cả route mới; không để khoảng trống. |

### 3.1. securityMatcher khác requestMatchers

Trong một chain:

~~~java
http
    .securityMatcher("/api/**")
    .authorizeHttpRequests(authorize -> authorize
        .requestMatchers("/api/admin").hasRole("ADMIN")
        .anyRequest().authenticated()
    );
~~~

- `securityMatcher("/api/**")`: chain này có **được chọn cho request** hay không?
- `requestMatchers("/api/admin")`: sau khi chain đã được chọn, đường dẫn cụ thể này cần **quyền gì**?
- `anyRequest()` trong chain API chỉ áp dụng cho **những request đã vào chain API**; không biến chain thành fallback toàn hệ thống.

Nếu tất cả chain đều có matcher hẹp và URL không khớp chain nào, URL có thể **không được Spring Security bảo vệ**. Hãy luôn thiết kế fallback hoặc một chính sách bao phủ toàn bộ không gian URL được phục vụ.

### 3.2. @Order không phải “độ ưu tiên của credential”

`@Order(1)` cao hơn `@Order(2)` trong quá trình **chọn chain**. Nhưng nếu cả Basic và Bearer đều được bật *trong cùng một chain*, `@Order` của bean chain không quyết định Basic hay Bearer thắng. Lúc này cần xem bộ filter thực tế và chính sách cho credential xung đột.

## 4. Bước 2: Filter nào có mặt và chạy theo thứ tự nào?

Trong một chain Servlet phổ biến, quá trình có thể hình dung:

~~~text
SecurityContextHolderFilter / SecurityContextRepository
     → (khôi phục Authentication từ session, hoặc context rỗng)
CORS / CSRF / security headers (nếu cấu hình)
     → Các filter authentication được bật
        (form login, Basic, Bearer, custom, remember-me...)
     → AnonymousAuthenticationFilter nếu vẫn chưa xác thực
     → ExceptionTranslationFilter
     → AuthorizationFilter
     → Controller
~~~

Đây là **sơ đồ khái niệm**, không phải danh sách đầy đủ hoặc vị trí chính xác của mọi filter cho mọi phiên bản. Spring Security có thứ tự filter xác định; hãy xem log danh sách filter thật ở runtime thay vì đoán từ thứ tự các dòng DSL trong code.

Ba hành vi của một filter xác thực là then chốt:

1. **Không thấy credential đúng scheme:** filter có thể bỏ qua và gọi filter tiếp theo.
2. **Có credential hợp lệ:** filter có thể tạo một `Authentication` đã chứng thực và đặt vào `SecurityContextHolder`.
3. **Credential sai hoặc không phù hợp:** filter có thể xóa context rồi gọi `AuthenticationEntryPoint`, trả 401 hoặc dừng xử lý. Vì vậy không thể mặc định “thử mọi cơ chế cho đến khi một cái đúng”.

Ví dụ nếu chain bật cả `httpBasic` và session-based form login: khi request đến, context từ session có thể đã được khôi phục. Một Basic header sau đó có thể được xử lý, bỏ qua, thay thế authentication hoặc làm request thất bại tùy điều kiện bên trong filter và phiên bản/cấu hình. Không có hợp đồng chung rằng **session luôn thắng Basic**. Cũng không được suy từ việc `SecurityContextHolderFilter` chạy trước để kết luận danh tính session là danh tính cuối.

Tương tự, nếu cùng chain bật `oauth2ResourceServer` cho Bearer, `BearerTokenAuthenticationFilter` chỉ xem Bearer token theo resolver được cấu hình. Khi token sai, nó có thể gọi entry point và kết thúc request ngay, chứ không nhất thiết quay về session hợp lệ.

### 4.1. SecurityContext không phải nơi “gộp mọi người dùng”

`SecurityContextHolder.getContext().getAuthentication()` là danh tính được nhìn thấy tại thời điểm đọc context. Nó không phải một danh sách cùng lúc gồm:

~~~text
Authenticated by session: alice
Authenticated by Basic: bob
Authenticated by Bearer: carol
~~~

và cũng không mặc định tự hợp nhất role của các principal đó. Bất cứ cơ chế “gộp” nào đều cần thiết kế và kiểm chứng riêng (ví dụ xác thực đa yếu tố trên **cùng danh tính**), không được vô tình trộn quyền của các tài khoản khác nhau.

Khi một filter tạo `Authentication` mới, hãy xác định nó có thay thế context hiện hành không, có lưu xuống `SecurityContextRepository` không, và request sau có kế thừa trạng thái không. Trong Spring Security 6, custom filter/controller muốn **lưu authentication qua request khác** cần lưu context chủ động bằng repository thích hợp.

### 4.2. STATELESS và session cookie ảnh hưởng đến kết quả

- Chain `SessionCreationPolicy.STATELESS` không dùng HTTP session để lấy `SecurityContext` cho xác thực và không tạo session phục vụ security context. Nó thích hợp cho Basic, Bearer hoặc credential theo từng request.
- Chain form login thông thường lưu `SecurityContext` trong session; browser gửi session cookie ở request tiếp theo.
- Với request có cả cookie và Basic header, nếu **API chain stateless chỉ bật Basic**, Basic là nguồn danh tính mà chain đó chấp nhận; cookie Web dù có cũng không dùng để xác thực request API.
- Nếu **web chain chỉ bật form login/session**, header Basic không được một `BasicAuthenticationFilter` trong chain đó xử lý; session là nguồn danh tính. Nếu không có session hợp lệ, người dùng cần login qua form.

**Không nhầm** “stateless” với “tắt toàn bộ CSRF/CORS” hoặc “browser sẽ không gửi cookie”. Browser vẫn có thể gửi cookie tùy thuộc site/policy; vấn đề là chain có dùng cookie đó để lấy authentication không.

## 5. Bước 3: AuthenticationProvider chỉ được xét sau khi filter tạo token

Giả sử `BasicAuthenticationFilter` đọc một header Basic hợp lệ về cú pháp và tạo `UsernamePasswordAuthenticationToken`. Nó chuyển đối tượng này tới `AuthenticationManager`. Manager thường dùng `ProviderManager` để xét các `AuthenticationProvider` theo thứ tự.

~~~text
BasicAuthenticationFilter
     └─ UsernamePasswordAuthenticationToken
           └─ ProviderManager
                 ├─ Provider A: supports(token)?
                 │      ├─ không → bỏ qua
                 │      ├─ null → xét provider tiếp theo
                 │      ├─ success → trả Authentication
                 │      └─ AuthenticationException → xử lý theo loại
                 └─ Provider B ...
~~~

Điểm khác biệt với việc chọn chain:

- `AuthenticationProvider.supports(Class<?>)` xét **loại Authentication token**, không xét URI để chọn Spring Security filter chain.
- `return null` từ provider có nghĩa chưa xử lý được instance, manager có thể thử provider khác.
- `BadCredentialsException` thông thường có thể được ghi nhận rồi manager vẫn xét provider sau; nếu provider sau thành công, manager có thể trả kết quả thành công.
- Các trường hợp như `AccountStatusException` hoặc `InternalAuthenticationServiceException` được `ProviderManager` xử lý dừng sớm.
- Provider thành công không có nghĩa filter authentication khác trong cùng chain cũng phải chạy.

Vì thế **thứ tự provider** khác **thứ tự cơ chế authentication**. Khi Basic và Bearer cùng tồn tại, mỗi cơ chế thường tạo loại token riêng (ví dụ `UsernamePasswordAuthenticationToken` và `BearerTokenAuthenticationToken`); cần kiểm tra cả filter, manager và provider.

Không dùng provider fallback làm lối đi vòng khi một credential mạnh bị từ chối. Nếu policy tuyên bố Bearer token sai phải bị từ chối, đừng biến lỗi đó thành `null` để một API key yếu hơn hoặc cookie session vô tình chấp nhận request.

## 6. Thiết kế chính sách ưu tiên trước khi viết filter

Một chiến lược dễ kiểm thử là **tách endpoint theo nguồn credential được phép**:

| Nhóm endpoint | Nguồn xác thực được chấp nhận | Credential khác có trong request | Thất bại đúng nghĩa |
| --- | --- | --- | --- |
| `/api/**` dành cho chương trình | Basic hoặc Bearer (chọn **một** chuẩn cho từng nhóm API) | Cookie session của browser bị API chain stateless bỏ qua | Thiếu/sai credential API → 401; không fallback session. |
| `/web/**` dành cho browser | Form login + HTTP session | Header Basic/Bearer không được chain Web xử lý nếu filter đó không bật | Thiếu session → chuyển login; session hợp lệ nhưng thiếu role → 403. |
| `/admin/**` | Cơ chế mạnh và quyền quản trị đã định nghĩa | Không tự nâng quyền bằng “credential thứ hai” vô danh | Không đáp ứng authentication/policy → deny. |
| Endpoint thật sự hỗ trợ nhiều scheme cùng URL | Chính sách ưu tiên **được viết ra**: chọn một hoặc từ chối đồng thời | Kiểm tra loại header, cookie và token ở một lớp thống nhất | Credential có mặt nhưng sai → fail closed, không âm thầm downgrade. |

Có hai cách thiết kế hợp lý tùy sản phẩm:

**Cách A — phân vùng rõ endpoint (ưu tiên cho ứng dụng hỗn hợp web/API):** `/api/**` dùng token/header stateless; `/web/**` dùng session. Không cần hai filter đua nhau thay `SecurityContext`. Khi API nhận cả cookie và header, chỉ nguồn được phép trên API chain có tác dụng.

**Cách B — cùng URL phải chấp nhận nhiều cơ chế:** định nghĩa thứ tự/chính sách ở cấp request, ví dụ “nếu có `Authorization` thì **bắt buộc** kiểm tra header; dù header sai cũng không fallback cookie; nếu không có header mới xét session”, hoặc “nếu đồng thời có hai nguồn thì từ chối 400/401”. Cần implement qua `RequestMatcher`, authentication converter/filter hoặc một thành phần điều phối được kiểm thử; không chỉ trông chờ vào thứ tự cấu hình hai DSL.

Với dữ liệu nhạy cảm, một chính sách **từ chối credential mơ hồ** dễ bảo vệ và debug hơn cố hòa trộn danh tính. Tuy nhiên phải cân nhắc browser có thể tự đính kèm cookie vào request API dù client chủ động gửi header, nên nếu chọn từ chối cả hai thì cần thiết kế origin/domain/cookie scope cho phù hợp.

### 6.1. “Có header” khác “header hợp lệ”

Khi policy nói header phải thắng session, cần xét ba tình huống:

1. **Không có `Authorization`**: theo thiết kế có thể dùng cookie session.
2. **Có `Authorization: Bearer <token>` nhưng token sai/hết hạn**: **không** được âm thầm bỏ Bearer để dùng cookie session; như vậy có thể tạo downgrade path.
3. **Có `Authorization` với scheme lạ hoặc malformed**: cần chính sách rõ ràng; thông thường từ chối thay vì coi như “không có header”.

Đừng dùng logic kiểu “nếu JWT parse lỗi thì để request tiếp tục với user cookie” nếu chính sách bảo mật yêu cầu token là nguồn quyền ưu tiên. Phân biệt “không cung cấp credential” với “cung cấp credential nhưng không hợp lệ”.

## 7. Ví dụ request xung đột: quyết định trước rồi đối chiếu

Giả sử cookie session Web chứa principal `web-alice`, Basic header chứa principal `api-reader`. Hệ thống quy định:

- `GET /api/me` → API chain chỉ dùng Basic, stateless, yêu cầu `ROLE_API`.
- `GET /web/me` → Web chain chỉ dùng form login/session, yêu cầu `ROLE_WEB`.
- `POST /login` / `POST /logout` → Web chain, theo chuẩn form login và CSRF.
- Tài khoản thử nghiệm `api-reader` có `ROLE_API`, `web-alice` có `ROLE_WEB`.

Các kết quả mong đợi:

| Request | Credential | Kết quả |
| --- | --- | --- |
| `GET /api/me` | Cookie của `web-alice` **và** Basic đúng của `api-reader` | **200**, principal `api-reader`. |
| `GET /api/me` | Chỉ cookie session `web-alice` | **401**; API không dùng session. |
| `GET /api/me` | Cookie `web-alice` + Basic `api-reader` sai password | **401**; không dùng cookie để “cứu” credential API sai. |
| `GET /api/me` | Basic đúng của `web-alice`, chỉ có `ROLE_WEB` | **403**; xác thực được nhưng thiếu quyền API. |
| `GET /web/me` | Cookie `web-alice` và Basic đúng của `api-reader` | **200**, principal `web-alice`. |
| `GET /web/me` | Chỉ Basic đúng của `api-reader`, không có session | **302** về login; Web chain không bật Basic. |
| `GET /api/me` | `Authorization: Bearer …`, không có Basic | **401**; ví dụ chưa cấu hình Bearer. |
| `GET /web/me` | Cookie hết hạn + Basic đúng | **302** về login; không có Basic fallback. |

Bảng này là **hợp đồng chính sách của ví dụ dưới đây**, không phải hành vi mặc định của mọi ứng dụng Spring Security. Nếu ứng dụng khác bật Basic, Bearer và form login trong cùng chain thì phải viết test riêng.

## 8. Ví dụ chạy được: hai chain loại bỏ sự mơ hồ

Ví dụ sử dụng **Spring Boot 3.x, Spring Security 6.x và Java 17+**. API và Web cùng nằm trong một backend nhưng chấp nhận credential theo phạm vi đường dẫn. Không cần JWT server để minh họa quy tắc; HTTP Basic ở API đủ chứng minh xung đột với cookie session.

### 8.1. Dependencies và cấu trúc

Tạo dự án Spring Initializr với Java 17+, Spring Web và Spring Security. Nếu dùng Gradle, dependencies:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Đây là phần cấu hình **đưa vào dự án Spring Boot có plugin và dependency management**, không phải toàn bộ `build.gradle`. Java ở các file có package `com.example.multischeme`.

~~~text
src/main/java/com/example/multischeme/
  MultiSchemeApplication.java
  SecurityConfig.java
  IdentityController.java
src/test/java/com/example/multischeme/
  CredentialPriorityTest.java
~~~

### 8.2. MultiSchemeApplication.java

~~~java
package com.example.multischeme;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MultiSchemeApplication {
    public static void main(String[] args) {
        SpringApplication.run(MultiSchemeApplication.class, args);
    }
}
~~~

### 8.3. SecurityConfig.java

~~~java
package com.example.multischeme;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .anyRequest().hasRole("API")
            )
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            )
            .formLogin(AbstractHttpConfigurer::disable)
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    SecurityFilterChain browserSecurity(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .requestMatchers("/web/**").hasRole("WEB")
                .anyRequest().authenticated()
            )
            .httpBasic(AbstractHttpConfigurer::disable)
            .formLogin(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("api-reader")
                .password(encoder.encode("api-pass"))
                .roles("API")
                .build(),
            User.withUsername("web-alice")
                .password(encoder.encode("web-pass"))
                .roles("WEB")
                .build()
        );
    }
}
~~~

Giải thích rõ từng quyết định:

1. `@Order(1)` và `securityMatcher("/api/**")`: API chain được thử trước; chỉ áp dụng cho đường dẫn `/api/**`.
2. `anyRequest().hasRole("API")` **không** có nghĩa mọi Basic user đều được phép vào API. Principal phải có `ROLE_API`.
3. `SessionCreationPolicy.STATELESS`: API không lấy `SecurityContext` từ session. Vì thế cookie `JSESSIONID` của người đăng nhập Web không đủ để xác thực API.
4. `formLogin(AbstractHttpConfigurer::disable)` ở API: nếu không có Basic credential, API trả 401/challenge theo cơ chế Basic, không redirect sang trang login.
5. Web chain không khai báo `securityMatcher`: làm fallback, giữ các URL `/login`, `/logout` trong phạm vi được bảo vệ.
6. `httpBasic(AbstractHttpConfigurer::disable)` ở Web: Basic header không tạo phiên login Web.
7. `formLogin(Customizer.withDefaults())`: Web dùng login qua form và HTTP session.
8. Hai tài khoản demo dùng chung `UserDetailsService` nhưng khác role. Đổi username/password trong source chỉ dành cho local demo; production phải lưu credential an toàn và dùng HTTPS.

**Phạm vi demo:** các endpoint API được minh họa bằng phương thức **GET** chỉ đọc. Spring Security vẫn bật CSRF mặc định; nếu thêm POST/PUT/PATCH/DELETE từ browser hoặc request có cookie tự động, cần đánh giá CSRF riêng. Không suy diễn rằng stateless hoặc HTTP Basic tự động an toàn trước mọi tình huống CSRF.

### 8.4. IdentityController.java

~~~java
package com.example.multischeme;

import java.security.Principal;
import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class IdentityController {

    @GetMapping("/")
    public Map<String, String> home() {
        return Map.of("page", "public");
    }

    @GetMapping("/api/me")
    public Map<String, String> apiMe(Principal principal) {
        return Map.of(
            "channel", "api-basic",
            "username", principal.getName()
        );
    }

    @GetMapping("/web/me")
    public Map<String, String> webMe(Principal principal) {
        return Map.of(
            "channel", "web-session",
            "username", principal.getName()
        );
    }
}
~~~

`Principal` đến từ request đã đi qua Spring Security. Controller không tự đọc cookie hay giải Base64. Giá trị `channel` chỉ để minh họa endpoint nào được gọi; **không phải dữ liệu độc lập chứng minh cách Spring Security xác thực**. Bằng chứng phải đến từ cấu hình filter, phiên và test có credential xung đột.

### 8.5. Chạy thử bằng HTTP client

~~~bash
./gradlew bootRun
~~~

Trên Windows chạy `gradlew.bat bootRun`. Với demo local:

~~~bash
# API chưa có Basic credential -> 401.
curl -i http://localhost:8080/api/me

# Basic đúng và ROLE_API -> 200.
curl -i -u api-reader:api-pass http://localhost:8080/api/me

# Basic đúng nhưng ROLE_WEB -> 403.
curl -i -u web-alice:web-pass http://localhost:8080/api/me

# Web chưa có session -> 302 về /login.
curl -i http://localhost:8080/web/me

# Basic header không tự đăng nhập vào Web chain -> redirect /login.
curl -i -u api-reader:api-pass http://localhost:8080/web/me
~~~

Kết quả JSON thành công từ API:

~~~json
{"channel":"api-basic","username":"api-reader"}
~~~

Khi login Web thành công, `GET /web/me` với session phù hợp trả:

~~~json
{"channel":"web-session","username":"web-alice"}
~~~

Hai account và mật khẩu trên đều là dữ liệu giả. Tham số `-u username:password` trên command line có thể xuất hiện trong lịch sử hoặc process list; không đặt secret thật vào lệnh demo. Môi trường thật phải dùng HTTPS.

Để quan sát tình huống **cùng lúc cookie và Basic header** dễ lặp lại hơn, dùng MockMvc test ở mục tiếp theo. Nó tạo session Web thật từ login và đính kèm Basic credential của người khác trong cùng request.

## 9. Test tích hợp: request có cả cookie và Authorization

Dùng `spring-security-test` cùng `MockMvc` để tạo session đăng nhập Web và kiểm tra API/web với credential đối nghịch. Đặt file:

`src/test/java/com/example/multischeme/CredentialPriorityTest.java`

~~~java
package com.example.multischeme;

import java.nio.charset.StandardCharsets;
import java.util.Base64;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CredentialPriorityTest {

    @Autowired
    private MockMvc mvc;

    private static String basic(String username, String password) {
        String raw = username + ":" + password;
        return "Basic " + Base64.getEncoder().encodeToString(
            raw.getBytes(StandardCharsets.UTF_8));
    }

    private MockHttpSession loginWeb() throws Exception {
        MvcResult result = mvc.perform(
                post("/login")
                    .with(csrf())
                    .param("username", "web-alice")
                    .param("password", "web-pass")
            )
            .andExpect(status().is3xxRedirection())
            .andReturn();

        MockHttpSession session =
            (MockHttpSession) result.getRequest().getSession(false);
        assertNotNull(session, "Form login phải tạo phiên Web");
        return session;
    }

    @Test
    void apiChoosesBasicWhenBothCredentialsExist() throws Exception {
        MockHttpSession browserSession = loginWeb();

        mvc.perform(
                get("/api/me")
                    .session(browserSession)
                    .header(HttpHeaders.AUTHORIZATION,
                        basic("api-reader", "api-pass"))
            )
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.channel").value("api-basic"))
            .andExpect(jsonPath("$.username").value("api-reader"));
    }

    @Test
    void apiDoesNotAcceptBrowserSessionByItself() throws Exception {
        MockHttpSession browserSession = loginWeb();

        mvc.perform(get("/api/me").session(browserSession))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void invalidBasicDoesNotFallBackToValidSession() throws Exception {
        MockHttpSession browserSession = loginWeb();

        mvc.perform(
                get("/api/me")
                    .session(browserSession)
                    .header(HttpHeaders.AUTHORIZATION,
                        basic("api-reader", "wrong-password"))
            )
            .andExpect(status().isUnauthorized());
    }

    @Test
    void apiAuthenticatesButRejectsWrongRole() throws Exception {
        mvc.perform(
                get("/api/me")
                    .header(HttpHeaders.AUTHORIZATION,
                        basic("web-alice", "web-pass"))
            )
            .andExpect(status().isForbidden());
    }

    @Test
    void webChoosesSessionWhenBothCredentialsExist() throws Exception {
        MockHttpSession browserSession = loginWeb();

        mvc.perform(
                get("/web/me")
                    .session(browserSession)
                    .header(HttpHeaders.AUTHORIZATION,
                        basic("api-reader", "api-pass"))
            )
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.channel").value("web-session"))
            .andExpect(jsonPath("$.username").value("web-alice"));
    }

    @Test
    void basicAloneDoesNotAuthenticateWeb() throws Exception {
        mvc.perform(
                get("/web/me")
                    .header(HttpHeaders.AUTHORIZATION,
                        basic("api-reader", "api-pass"))
            )
            .andExpect(status().is3xxRedirection());
    }

    @Test
    void unsupportedBearerDoesNotAuthenticateBasicApi() throws Exception {
        MockHttpSession browserSession = loginWeb();

        mvc.perform(
                get("/api/me")
                    .session(browserSession)
                    .header(HttpHeaders.AUTHORIZATION,
                        "Bearer example.invalid.token")
            )
            .andExpect(status().isUnauthorized());
    }
}
~~~

Chạy:

~~~bash
./gradlew test --tests com.example.multischeme.CredentialPriorityTest
~~~

Hoặc trên Windows:

~~~powershell
.\gradlew.bat test --tests com.example.multischeme.CredentialPriorityTest
~~~

Khi code được đặt trong dự án đúng Spring Boot 3.x, có đầy đủ dependency và các assertion pass, Gradle sẽ báo `BUILD SUCCESSFUL`; test không in ra chuỗi stdout cố định. Đây là **kỳ vọng kiểm thử**, không phải bản ghi đã chạy.

Ý nghĩa của bảy test:

| Test | Điều cần chứng minh |
| --- | --- |
| `apiChoosesBasicWhenBothCredentialsExist` | Cookie Web thuộc user khác không thay danh tính Basic trên API. |
| `apiDoesNotAcceptBrowserSessionByItself` | API không dựa vào session Web; có cookie vẫn 401 nếu thiếu Basic. |
| `invalidBasicDoesNotFallBackToValidSession` | Basic sai → 401, không tự chuyển sang session hợp lệ. |
| `apiAuthenticatesButRejectsWrongRole` | Username/password đúng không đồng nghĩa đủ role: 403. |
| `webChoosesSessionWhenBothCredentialsExist` | Web vẫn dùng `web-alice`; Basic API header không thay principal Web. |
| `basicAloneDoesNotAuthenticateWeb` | Basic header trên Web route không biến thành login session. |
| `unsupportedBearerDoesNotAuthenticateBasicApi` | Không phải cứ có `Authorization` là được chấp nhận; API này chỉ bật Basic. |

Điểm hay của phép thử có **hai username khác nhau** là không thể “trùng hợp đúng người” rồi đánh giá sai precedence. Không nên chỉ dùng cùng một user ở cả cookie và header: request 200 một mình không cho biết filter nào thực sự đã xác thực.

Tuy nhiên, chính sách API ở ví dụ còn kiểm tra `ROLE_API`, nên nếu test API với cookie user Web nhưng header Basic đúng user Web thì **403** (authenticated nhưng thiếu quyền); muốn chứng minh session bị bỏ qua, phải dùng test **cookie Web không có Basic → 401** như trên.

## 10. Nếu một URL thật sự cần chấp nhận cả Bearer và session?

Ví dụ một endpoint `/profile` được ứng dụng browser gọi với session, nhưng mobile app gọi với Bearer token. Có thể có lúc browser giữ session đồng thời JavaScript gửi `Authorization: Bearer …`. Đây là tình huống cần **hợp đồng precedence** rõ ràng:

~~~text
Hợp đồng đề xuất A: Header ưu tiên nếu có mặt
------------------------------------------------
Authorization header xuất hiện?
  YES → chỉ chấp nhận scheme đã khai báo
         token hợp lệ → xác thực bằng token
         token sai/malformed/hết hạn → 401, KHÔNG fallback cookie
  NO  → kiểm tra session
         session hợp lệ → xác thực bằng session
         session không hợp lệ → 401 hoặc redirect theo client
~~~

Hoặc:

~~~text
Hợp đồng đề xuất B: Từ chối các request mơ hồ
---------------------------------------------
Có cả Bearer và cookie xác thực?
  YES → 400/401 theo API contract, không chọn ngầm
  NO  → chỉ xử lý cơ chế duy nhất được cung cấp
~~~

Lựa chọn A thích hợp khi cần giữ tương thích clients; lựa chọn B chặt chẽ khi không có lý do hỗ trợ đa nguồn trên một request. Trong mọi trường hợp, status, challenge và mô hình CSRF/cookie phải được xác định.

### 10.1. Vì sao chỉ bật cả oauth2ResourceServer và formLogin chưa đủ?

Một cấu hình như sau **không tự biểu đạt** “Bearer luôn thắng session”:

~~~java
// Chỉ là minh họa cấu hình nhiều cơ chế; không phải policy hoàn chỉnh.
http
    .oauth2ResourceServer(oauth2 -> oauth2.jwt(
        org.springframework.security.config.Customizer.withDefaults()))
    .formLogin(org.springframework.security.config.Customizer.withDefaults());
~~~

Các filter sẽ có thứ tự thực thi cụ thể, nhưng **không thể suy ra toàn bộ semantics chỉ từ thứ tự gọi DSL**. Cần xem:

- `BearerTokenAuthenticationFilter` có nhận diện header không? Resolver chấp nhận scheme nào?
- `SecurityContext` có đang khôi phục từ session không?
- Khi Bearer token sai, filter có kết thúc request bằng `AuthenticationEntryPoint` không?
- Khi token hợp lệ, filter có ghi đè authentication hiện hành không?
- Request có CSRF token, cookie, role/authority và request-cache tương thích hay không?
- Quy tắc HTTP response có phân biệt browser redirect và API 401 đúng ý không?

Cấu hình Bearer chạy thật còn cần resource-server dependency và `JwtDecoder`/issuer/JWK phù hợp; đoạn trên **không độc lập chạy được**. Ví dụ runnable ở mục 8 cố ý dùng Basic để tập trung vào việc xác định precedence.

### 10.2. Chọn chain theo credential cũng là một lựa chọn, nhưng cần thận trọng

`SecurityFilterChain` có thể dùng `RequestMatcher` tùy chỉnh, bao gồm điều kiện theo header. Chẳng hạn, một chain ưu tiên cho endpoint hỗn hợp khi nhận `Authorization`, một chain session cho request không có header. Nhưng khi xây policy này:

1. Định nghĩa rõ request có `Authorization` **sai cú pháp hoặc scheme lạ** sẽ vào chain nào; không coi như header vắng mặt.
2. Không chuyển request sang session chain chỉ vì chain header trả 401. `FilterChainProxy` **không** fallback sang chain tiếp theo sau khi chain đã chọn bị từ chối.
3. Không đưa input không đáng tin từ header vào cách chọn quyền/trust level mà không có validation.
4. Kiểm tra request với header lặp, mâu thuẫn qua proxy, và mọi biến thể chữ hoa/thường của scheme.
5. Bảo đảm một fallback chain bảo vệ toàn bộ URL còn lại; không để request “rơi ngoài Spring Security”.

Nếu cần thay đổi filter order thủ công, dùng `addFilterBefore`, `addFilterAfter` hoặc `addFilterAt` với hiểu biết về filter đang tồn tại. **Việc đặt một custom filter trước Basic không tự định nghĩa precedence** nếu nó không xử lý chính xác context, lỗi, dừng request và session. Nhiều trường hợp nên thiết kế lại routing hoặc dùng filter xác thực thống nhất thay vì xếp thêm filter.

## 11. Cách đọc log để biết thật sự ai xử lý request

Khi có nhiều mechanism, đoán từ response `200` là chưa đủ. Có thể bật log ở môi trường phát triển:

~~~properties
logging.level.org.springframework.security=DEBUG
logging.level.org.springframework.security.web.FilterChainProxy=TRACE
~~~

Cấu hình này giúp xem filter chain bảo vệ URL và các filter thực thi. Log cụ thể thay đổi theo version và cấp độ log; **không hardcode trông chờ vào một dòng log duy nhất**.

Quy trình debug:

1. **Xác định URL sau proxy/context-path.** Đôi khi reverse proxy rewrite `/v1/api` thành `/api`, làm matcher khác dự đoán.
2. **Nhìn chain được chọn.** Với `/api/me`, phải là API chain, không phải Web fallback.
3. **In/quan sát danh sách filter trong chain.** Có `BasicAuthenticationFilter` hoặc `BearerTokenAuthenticationFilter` không? Chain Web có vô tình bật Basic không?
4. **Đánh giá sự hiện diện credential, không ghi giá trị.** Có `Authorization` không, scheme là gì, cookie phiên có mặt không? Không log Basic base64/JWT/secret/session ID.
5. **Xem exception hoặc entry point đầu tiên kết thúc request.** Bad password có thể trả 401 trước khi authorization chạy; thiếu role thường trả 403 sau authentication.
6. **Xem principal tại controller** hoặc bằng test tích hợp. Dùng username khác nhau để phân biệt khi test. Không log cả `Authentication.getCredentials()` hoặc raw principal chứa bí mật.
7. **Kiểm tra persistence:** API `STATELESS` không khôi phục session; Web `HttpSessionSecurityContextRepository` có context sau form login hay không?
8. **Thử một credential mỗi lần, rồi cả hai, rồi một credential sai.** Trường hợp “một sai + một đúng” thường bộc lộ fallback ngoài ý muốn.

Bảng chẩn đoán nhanh:

| Hiện tượng | Khả năng cần kiểm tra |
| --- | --- |
| API nhận session cookie mà vẫn 200 dù thiếu header | API đang dùng repository/session hoặc vô tình vào Web chain. |
| API gửi token sai nhưng vẫn 200 nhờ cookie | Có cơ chế fallback không chủ ý, filter bỏ qua lỗi hoặc chain chọn theo điều kiện sai. |
| Web gửi Basic header thì bật hộp thoại HTTP Basic | Web chain có Basic entry point/filter hoặc request đi nhầm vào API chain. |
| Request Basic hợp lệ nhận 403 | Authentication có thể đúng nhưng thiếu role/scope; kiểm tra `AccessDeniedHandler`. |
| Có session hợp lệ và Bearer sai nhưng chỉ nhận 401 | Một filter Bearer có thể kết thúc request trước khi session được dùng; cần xem policy. |
| Endpoint mới không bị Spring Security kiểm soát | Không chain nào match hoặc `securityMatcher` quá hẹp. |
| Không thể biết user nào thắng khi cả hai cùng tên | Test lại với **hai principal khác nhau** và assert danh tính trong controller. |

## 12. Bảo mật khi nhiều nguồn danh tính cùng tồn tại

### 12.1. Tránh credential downgrade

Một access token hết hạn không có nghĩa client được phép chuyển sang một cookie phiên cũ để vẫn truy cập API. Nếu policy cho phép token là nguồn ưu tiên khi có mặt, **token sai phải bị từ chối**. Fallback chỉ được thực hiện khi được thiết kế rõ và không làm yếu yêu cầu bảo mật của tài nguyên.

### 12.2. Không trộn quyền từ hai principal khác nhau

Không tự cộng `ROLE_ADMIN` của session A với `scope=write` của bearer token B rồi tạo “super principal” C. Những quyền này có thể thuộc hai tài khoản hoàn toàn khác nhau. Nếu một request cần hai yếu tố xác thực, phải xác minh chúng thuộc **cùng principal** và áp dụng workflow MFA có state và proof phù hợp, không gộp bừa các `Authentication`.

### 12.3. Cookie session và CSRF vẫn là vấn đề riêng

Một Web chain dựa vào session cần CSRF protection cho các hành động thay đổi trạng thái theo chính sách. HTTP Basic khi browser tự gửi credential cũng có thể chịu CSRF risk. CORS quyết định JavaScript từ origin khác có thể đọc response; nó **không** thay CSRF. Xác định precedence thành công không tự bảo đảm an toàn trước CSRF, session fixation, credential stuffing hoặc XSS.

### 12.4. HTTP challenge phải hợp đối tượng client

API Basic thường trả `401` với `WWW-Authenticate: Basic …`, browser form login thường redirect tới `/login`. Nếu trộn entry point, một HTTP client có thể nhận HTML thay vì JSON, hoặc browser xuất hiện hộp thoại Basic ngoài ý muốn. Tách chain theo URL giúp chọn response phù hợp và có thể kiểm thử độc lập.

### 12.5. Tài khoản và secret phải được quản lý độc lập với routing

`@Order` và `securityMatcher` không mã hóa password, không thu hồi token, không cách ly user store. Với các kênh có mức độ tin cậy khác nhau, cần cân nhắc `AuthenticationManager`/provider khác nhau, authority, token audience, MFA hoặc session policy riêng. Đừng lấy đường dẫn URL làm bằng chứng duy nhất cho quyền cao; endpoint vẫn phải kiểm tra principal và authority đã xác thực.

### 12.6. Không log credential để quan sát ưu tiên

Đối với Basic, Base64 có thể giải lại thành username/password; JWT, API key, session ID cũng là bí mật. Logging/tracing phải redaction dữ liệu, dùng correlation ID và phân loại nguồn credential (Basic/Bearer/session) **không ghi nguyên giá trị**. Tránh bật DEBUG/TRACE chi tiết trên production kéo dài mà chưa đánh giá dữ liệu nhạy cảm.

## 13. Checklist kiểm thử trước khi triển khai

Với mỗi nhóm URL, phải trả lời được:

| Câu hỏi | Bằng chứng |
| --- | --- |
| Chain nào được chọn khi URL khớp nhiều matcher? | Log `FilterChainProxy` và test theo `@Order`. |
| Nếu URL không khớp matcher ưu tiên, chain fallback nào xử lý? | Test các path ngoài prefix. |
| Filter authentication nào thực sự tồn tại trong chain? | Danh sách filter ở DEBUG/startup hoặc kiểm tra cấu hình. |
| Request chỉ có cookie session thì sao? | Kỳ vọng rõ 200 hoặc 401/302 tùy endpoint. |
| Request chỉ có Basic/Bearer thì sao? | Kỳ vọng 200/401 theo scheme đã cấu hình. |
| Request có cả cookie và header của **hai user khác nhau** thì sao? | Assert principal chính xác trong controller. |
| Header có mặt nhưng credential sai, cookie vẫn đúng? | Kiểm tra không có fallback/downgrade ngoài ý muốn. |
| Credential đúng nhưng thiếu role/scope? | 403, phân biệt với 401. |
| Header mang scheme không hỗ trợ hoặc trùng lặp? | Reject/ignore theo contract đã công bố; không chọn ngầm từ proxy. |
| Sau logout hoặc hết hạn session, API còn phụ thuộc cookie không? | Kiểm thử độc lập session và header. |
| CSRF/CORS/session fixation có được xử lý đúng? | Test POST/login/logout/cross-origin, không chỉ GET. |
| Log có lộ Authorization, Cookie, password, JWT không? | Kiểm tra redaction và policy vận hành. |

Mỗi test nên dùng **danh tính riêng biệt** để thấy rõ nguồn nào thực sự được dùng. Phải test cả happy path, sai credential, thiếu credential, thiếu quyền, và request có nhiều credential đồng thời.

## 14. Kết luận

Khi một request có nhiều thông tin xác thực, hãy lần lượt xác định:

1. **Chain nào được chọn?** `@Order` + `securityMatcher`; **chỉ chain đầu tiên khớp** được xử lý.
2. **Filter nào chạy và có quyền xử lý credential nào?** Filter order ảnh hưởng đến context và khả năng dừng request; không có “cookie luôn thắng” hay “header luôn thắng” mặc định.
3. **AuthenticationManager/Provider nào kiểm tra token?** Thứ tự provider là vấn đề khác với thứ tự filter/chain; `supports`, `null` và exception có semantics riêng.
4. **Chính sách kiến trúc mong muốn là gì?** Ưu tiên credential theo endpoint/protocol hoặc từ chối tín hiệu mơ hồ; invalid credential không được âm thầm downgrade.
5. **Kết quả có được chứng minh bằng test không?** Test request có cả cookie Web và Basic/Bearer thuộc người khác, thêm test credential sai, rồi assert principal và status thật.

Đối với ứng dụng gồm browser và API, **API stateless header-based ở chain riêng + Web form session ở chain fallback** là một thiết kế minh bạch, dễ quan sát và dễ test. Khi buộc hỗ trợ nhiều phương thức trên cùng URL, cần một policy rõ ràng và kiểm thử sâu thay vì dựa vào thứ tự khai báo DSL.

### Tài liệu tham khảo

- Spring Security 6.5 — Java Configuration, Multiple HttpSecurity Instances: https://docs.spring.io/spring-security/reference/6.5/servlet/configuration/java.html
- Spring Security 6.5 — Servlet Architecture and Filter Ordering: https://docs.spring.io/spring-security/reference/6.5/servlet/architecture.html
- Spring Security 6.5 — Authentication Architecture: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html
- Spring Security 6.5 — Basic Authentication: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/basic.html
- Spring Security 6.5 — Session Management / Stateless Authentication: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html
- Spring Security 6.5 — OAuth2 Resource Server: https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/index.html
- Spring Security 6.5 — CSRF: https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html
- Spring Security 6.5 — MockMvc Testing: https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/index.html
