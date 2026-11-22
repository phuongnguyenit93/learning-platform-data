# Từ ứng dụng chưa bảo vệ đến endpoint công khai và endpoint cần đăng nhập

## 1. Bài thực hành sẽ tạo ra điều gì?

Bắt đầu từ một ứng dụng **Spring Boot MVC không cài Spring Security**: cả `GET /api/public` và `GET /api/profile` đều trả dữ liệu cho khách chưa đăng nhập. Sau đó, lần lượt bổ sung Spring Security, quan sát hành vi bảo vệ mặc định, viết `SecurityFilterChain` để **giữ `/api/public` công khai** và **yêu cầu xác thực với `/api/profile`**, cuối cùng viết kiểm thử tự động chứng minh chính sách đó.

Bài tập tập trung vào **authentication (xác thực) và HTTP request authorization (ủy quyền ở mức request)**. Nó chưa xây dựng tài khoản trong database, giao diện đăng nhập, JWT hay OAuth2. Các phần đó cần học sau khi đã hiểu rõ ranh giới công khai và đăng nhập của một ứng dụng đơn giản.

Kết quả cuối:

| HTTP request | Mong đợi | Lý do |
| --- | --- | --- |
| `GET /api/public`, không gửi credentials | **200** | Được gắn `permitAll()` |
| `GET /api/public`, credentials hợp lệ | **200** | Tài nguyên công khai vẫn truy cập được |
| `GET /api/profile`, không gửi credentials | **401** | `authenticated()` + HTTP Basic |
| `GET /api/profile`, sai mật khẩu | **401** | Xác thực thất bại |
| `GET /api/profile`, credentials hợp lệ | **200** | Đã xác thực |
| `GET /api/missing`, chưa xác thực | **401** | `anyRequest().authenticated()` áp dụng trước khi đến MVC |
| `GET /api/missing`, đã xác thực | **404** | Đi qua lớp bảo mật rồi nhưng không có controller |

**Phân biệt:** 401 là cần/chưa đạt xác thực, 403 thường là đã xác thực nhưng không đủ quyền (hoặc bị lớp bảo vệ như CSRF từ chối), 404 là không tìm thấy tài nguyên/handler. Mã trả về phụ thuộc SecurityFilterChain, entry point và controller thực tế; bảng này là hợp đồng của cấu hình **HTTP Basic** được viết trong bài.

## 2. Chuẩn bị và cấu trúc dự án

Ví dụ dùng **Java 17**, **Spring Boot 3.3.5**, **Spring Security 6.x** do BOM của Spring Boot quản lý, **Gradle Groovy DSL**, **Spring MVC/Servlet**, JUnit 5 và MockMvc. Đây là một bộ phiên bản mẫu cố định để thực hành; dự án thật phải chọn cặp Boot/Security tương thích của chính nó. Có thể chạy bằng JDK 17 hoặc mới hơn phù hợp với Gradle và Boot. Không cần database, Docker hay frontend.

Tạo project Gradle Spring Boot từ Spring Initializr hoặc dự án trống đã có Gradle Wrapper; khai báo package `example.securitydemo`, Java 17, dependency ban đầu chỉ có **Spring Web**. Nếu dùng Initializr đang cung cấp phiên bản khác, hãy chọn phiên bản được hỗ trợ và điều chỉnh Gradle tương ứng; đừng pha trộn starter khác thế hệ. Giữ `gradlew` / `gradlew.bat` do project generator cung cấp.

Cấu trúc các tệp do chúng ta viết:

~~~text
security-demo/
├── settings.gradle
├── build.gradle
├── gradlew                        # do Gradle Wrapper cung cấp
├── gradlew.bat                    # do Gradle Wrapper cung cấp
├── gradle/wrapper/...
└── src/
    ├── main/java/example/securitydemo/
    │   ├── SecurityDemoApplication.java
    │   ├── DemoController.java
    │   └── SecurityConfig.java    # chỉ thêm ở bước 5
    └── test/java/example/securitydemo/
        └── SecurityBoundaryTests.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'security-demo'
~~~

**Bản `build.gradle` ở bước đầu, chưa có Spring Security:**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
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
~~~

Giải thích: `spring-boot-starter-web` cung cấp Spring MVC, embedded Tomcat và Jackson để trả JSON. Plugin Boot và dependency management giữ các thư viện cùng hệ phiên bản; **không cần khai báo version riêng cho từng starter**. `spring-boot-starter-test` cấp thư viện JUnit/Spring Test cho phần kiểm thử sau.

## 3. Bước 1 — Ứng dụng chưa có lớp bảo vệ

Tệp `src/main/java/example/securitydemo/SecurityDemoApplication.java`:

~~~java
package example.securitydemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SecurityDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(SecurityDemoApplication.class, args);
    }
}
~~~

Tệp `src/main/java/example/securitydemo/DemoController.java`:

~~~java
package example.securitydemo;

import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/api/public")
    public Map<String, String> publicInfo() {
        return Map.of("message", "public");
    }

    @GetMapping("/api/profile")
    public Map<String, String> profile() {
        return Map.of("message", "private");
    }
}
~~~

Chạy ở thư mục chứa `gradlew`:

~~~bash
./gradlew bootRun
~~~

Với PowerShell trên Windows:

~~~powershell
.\gradlew.bat bootRun
~~~

Trong terminal khác, gọi hai endpoint:

~~~bash
curl -i http://localhost:8080/api/public
curl -i http://localhost:8080/api/profile
~~~

Kết quả quan trọng **trước khi cài Security**: cả hai trả `200 OK`, body lần lượt là:

~~~json
{"message":"public"}
~~~

và:

~~~json
{"message":"private"}
~~~

Ở giai đoạn này tên `/api/profile` hoặc biến tên `private` **không tự tạo bảo mật**. Spring MVC chỉ ánh xạ request tới method của controller; nếu không có bộ lọc xác thực/ủy quyền hoặc kiểm soát riêng, khách nào biết URL cũng gọi được.

Câu hỏi tự kiểm: Nếu đưa controller này lên mạng công khai, chỉ giấu URL có đủ bảo vệ dữ liệu riêng tư không? **Không.** URL có thể bị đoán, lộ qua log, lịch sử hoặc chia sẻ. Cần một quy tắc bảo mật cưỡng chế từ phía server.

## 4. Bước 2 — Thêm Spring Security và quan sát mặc định

Dừng ứng dụng rồi thêm đúng một dependency vào phần `dependencies`:

~~~groovy
implementation 'org.springframework.boot:spring-boot-starter-security'
~~~

Khởi động lại bằng `./gradlew bootRun` hoặc `.\gradlew.bat bootRun`. Khi chưa có `SecurityFilterChain` hay `UserDetailsService` tùy chỉnh, Spring Boot tích hợp cấu hình bảo vệ mặc định: yêu cầu đăng nhập cho request và cung cấp cơ chế HTTP Basic/form login theo nội dung negotiation. Trên môi trường phát triển, Boot có thể sinh một mật khẩu tạm cho user mặc định và ghi vào log lúc khởi động. **Mật khẩu đó không phải cơ chế quản lý người dùng cho production.**

Quan sát bằng client không yêu cầu HTML:

~~~bash
curl -i -H "Accept: application/json" http://localhost:8080/api/public
curl -i -H "Accept: application/json" http://localhost:8080/api/profile
~~~

Bạn sẽ thấy cả hai bị yêu cầu đăng nhập (thông thường **401** với client API này). Đây là điểm quan trọng: **thêm starter Security không có nghĩa framework tự biết URL nào của bạn cần công khai**. Với trình duyệt chấp nhận HTML, cơ chế form login mặc định có thể tạo **302** sang trang đăng nhập; khi test status, phải hiểu entry point/client và cấu hình thực tế.

Bước này giúp xác định nguyên nhân: controller không đổi, nhưng request đã đi qua bộ lọc bảo mật do Spring Security đăng ký. Không nên kết luận Spring MVC đã "mất route"; route vẫn tồn tại, chỉ có security chặn trước.

Sơ đồ luồng xử lý đơn giản:

~~~text
Client
  |
  v
Spring Security FilterChainProxy / SecurityFilterChain
  |  (xác thực request: ví dụ BasicAuthenticationFilter)
  |  (kiểm tra quy tắc: AuthorizationFilter)
  v
Spring MVC DispatcherServlet
  |
  v
DemoController
  |
  v
HTTP response

Nếu xác thực/ủy quyền thất bại, request có thể kết thúc ở
Security filter/exception handling mà không đi tới controller.
~~~

Spring Security xử lý **authentication** (request này là ai?) và **authorization** (request này có được tới tài nguyên không?) ở các bước liên quan nhưng khác nhau.

## 5. Bước 3 — Viết chính sách công khai và cần đăng nhập

Mục tiêu cuối: `GET /api/public` truy cập được khi chưa đăng nhập; những request còn lại yêu cầu đã xác thực. Ở đây chỉ chọn HTTP Basic để dễ thấy **401** trong bài tập API. Không bật form login vì ta không xây dựng flow giao diện trình duyệt.

Tệp mới `src/main/java/example/securitydemo/SecurityConfig.java`:

~~~java
package example.securitydemo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers(HttpMethod.GET, "/api/public").permitAll()
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(AbstractHttpConfigurer::disable);

        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails learner = User.withUsername("learner")
            .password(encoder.encode("learning-only-password"))
            .roles("USER")
            .build();

        return new InMemoryUserDetailsManager(learner);
    }
}
~~~

**Đọc đúng từng phần:**

1. `@Configuration` khai báo một cấu hình Spring; `@Bean SecurityFilterChain` cung cấp danh sách và cấu hình filter thực sự xử lý HTTP request. Trong Spring Boot, bean do người dùng khai báo sẽ thay thế phần cấu hình bảo vệ HTTP mặc định có tính chất dự phòng.
2. `authorizeHttpRequests` xét các quy tắc theo thứ tự. `requestMatchers(HttpMethod.GET, "/api/public").permitAll()` chỉ mở **GET** của URL chính xác này; không mặc nhiên mở `/api/public/admin`, mọi method hay toàn bộ ứng dụng.
3. `anyRequest().authenticated()` là hàng rào cuối: request không khớp quy tắc công khai vẫn phải có `Authentication` đã xác thực. Không nên dùng `anyRequest().permitAll()` ở cuối vì như vậy mở mọi route còn lại.
4. `httpBasic(Customizer.withDefaults())` chấp nhận cặp username/password qua header `Authorization: Basic ...` và đưa yêu cầu xác thực vào chuỗi filter. `formLogin(AbstractHttpConfigurer::disable)` loại bỏ redirect đến form login trong bài API này; khi chưa đăng nhập, kết quả mong đợi là HTTP **401** cùng cơ chế challenge của Basic.
5. `PasswordEncoder` dùng BCrypt để so mật khẩu được mã hóa. `UserDetailsService` trả tài khoản demo in-memory, nên không cần database. `roles("USER")` tạo authority `ROLE_USER`; tuy nhiên **quy tắc ở đây chỉ yêu cầu `authenticated()`**, chưa giới hạn vai trò.
6. `learning-only-password` là **mật khẩu cố định chỉ dùng trong bài thực hành trên máy local**. Không hardcode tài khoản demo kiểu này trong production hoặc commit mật khẩu thật. Hệ thống thật cần nguồn danh tính đáng tin cậy (database/LDAP/identity provider), quản lý secret, TLS và vòng đời tài khoản.

**Điểm dễ nhầm:** `permitAll()` chỉ cho qua **bước kiểm tra quyền truy cập URL**; request vẫn đi qua các filter khác. Ví dụ client gửi **sai header Basic** tới chính `/api/public` thì filter xác thực có thể trả 401 trước khi `permitAll()` được xét. `permitAll()` cũng không tự vô hiệu hóa CSRF, CORS hoặc header bảo vệ.

## 6. Bước 4 — Gọi API và đối chiếu từng trạng thái

Khởi động lại ứng dụng sau khi thêm `SecurityConfig`. Nếu dùng Windows PowerShell, dùng **`curl.exe`**, vì trong Windows PowerShell cũ, tên `curl` có thể là alias của `Invoke-WebRequest`.

### 6.1. Khách chưa đăng nhập tới endpoint công khai

~~~bash
curl -i http://localhost:8080/api/public
~~~

Kỳ vọng `HTTP 200`, JSON:

~~~json
{"message":"public"}
~~~

### 6.2. Khách chưa đăng nhập tới endpoint cần đăng nhập

~~~bash
curl -i http://localhost:8080/api/profile
~~~

Kỳ vọng `HTTP 401 Unauthorized`. Với HTTP Basic, server thường trả thêm `WWW-Authenticate: Basic ...` để mô tả cơ chế đăng nhập. Không có body `{"message":"private"}`, vì controller chưa được gọi.

### 6.3. Gửi cặp username/password đúng

~~~bash
curl -i --basic -u 'learner:learning-only-password' \
  http://localhost:8080/api/profile
~~~

Kỳ vọng `HTTP 200` và body:

~~~json
{"message":"private"}
~~~

Trên PowerShell, dùng một dòng:

~~~powershell
curl.exe -i --basic -u "learner:learning-only-password" http://localhost:8080/api/profile
~~~

`curl -u` tạo header Basic từ username/password. Header này chỉ **mã hóa Base64**, không phải mã hóa bảo mật dữ liệu đường truyền. Trong triển khai thực tế, bắt buộc dùng **HTTPS** để tránh lộ credentials trên mạng.

### 6.4. Gửi mật khẩu sai

~~~bash
curl -i --basic -u 'learner:wrong-password' \
  http://localhost:8080/api/profile
~~~

Kỳ vọng **401**, dù username tồn tại. Sự khác biệt giữa kết quả đúng và sai cho thấy Spring Security thực sự kiểm chứng credentials, không phải chỉ kiểm tra header có hiện diện.

### 6.5. Gọi URL không tồn tại

~~~bash
curl -i http://localhost:8080/api/missing
curl -i --basic -u 'learner:learning-only-password' \
  http://localhost:8080/api/missing
~~~

Kỳ vọng lần lượt **401** (không qua policy) và **404** (qua policy, nhưng MVC không có handler). Đây là minh họa vì sao chỉ nhìn một status đơn lẻ chưa đủ chẩn đoán nguyên nhân.

Lưu ý: lệnh `curl -i` in cả response header; header cụ thể như `Date`, `Cache-Control`, `Content-Length` hay body lỗi có thể khác theo môi trường. Chỉ so các trạng thái và dữ liệu mà hợp đồng bài tập thực sự yêu cầu.

## 7. Bước 5 — Viết kiểm thử hồi quy bằng MockMvc

Gắn test library của Spring Security vào `build.gradle` cùng với starter Security ở `implementation`. Toàn bộ phần `dependencies` **cuối cùng** là:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Giữ nguyên những phần plugin, `group`, `java`, `repositories` và `tasks.named('test')` ở `build.gradle` bước 2. Spring Boot quản lý version thư viện test tương thích.

Tạo `src/test/java/example/securitydemo/SecurityBoundaryTests.java`:

~~~java
package example.securitydemo;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityBoundaryTests {

    @Autowired
    MockMvc mockMvc;

    @Test
    void publicEndpointAllowsAnonymous() throws Exception {
        mockMvc.perform(get("/api/public"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.message").value("public"));
    }

    @Test
    void publicEndpointAlsoAllowsAuthenticatedUser() throws Exception {
        mockMvc.perform(
                get("/api/public")
                    .with(httpBasic("learner", "learning-only-password")))
            .andExpect(status().isOk());
    }

    @Test
    void profileRejectsAnonymous() throws Exception {
        mockMvc.perform(get("/api/profile"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void profileRejectsWrongPassword() throws Exception {
        mockMvc.perform(
                get("/api/profile")
                    .with(httpBasic("learner", "wrong-password")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void profileAllowsCorrectCredentials() throws Exception {
        mockMvc.perform(
                get("/api/profile")
                    .with(httpBasic("learner", "learning-only-password")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.message").value("private"));
    }

    @Test
    void unknownPathIsStillProtectedForAnonymous() throws Exception {
        mockMvc.perform(get("/api/missing"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void unknownPathReturnsNotFoundAfterAuthentication() throws Exception {
        mockMvc.perform(
                get("/api/missing")
                    .with(httpBasic("learner", "learning-only-password")))
            .andExpect(status().isNotFound());
    }

    @Test
    void invalidBasicCredentialsFailEvenOnPublicEndpoint() throws Exception {
        mockMvc.perform(
                get("/api/public")
                    .with(httpBasic("learner", "wrong-password")))
            .andExpect(status().isUnauthorized());
    }
}
~~~

Chạy:

~~~bash
./gradlew test --tests "example.securitydemo.SecurityBoundaryTests"
~~~

Trên Windows:

~~~powershell
.\gradlew.bat test --tests "example.securitydemo.SecurityBoundaryTests"
~~~

**Kết quả mong đợi:** cả **8 test thành công** và Gradle báo `BUILD SUCCESSFUL`. Số dòng log cụ thể có thể thay đổi giữa các phiên bản. Đây là hành vi kỳ vọng từ ví dụ đã cấu hình, không phải bản ghi kết quả đã chạy trong chính môi trường của người đọc.

**Vì sao cách test này đáng tin hơn gọi thẳng controller?** `@SpringBootTest` khởi động Spring application context thật của bài tập; `@AutoConfigureMockMvc` cấu hình `MockMvc` trong ngữ cảnh Boot cùng các filter đã đăng ký (mặc định thêm filter). `httpBasic(...)` mô phỏng request mang credentials để Spring Security kiểm tra qua filter. Nếu chỉ `new DemoController().profile()` hoặc dùng `MockMvcBuilders.standaloneSetup` mà bỏ filter, test `200` sẽ không chứng minh endpoint được bảo vệ.

**Phân biệt hai loại test:** `@WithMockUser` hữu ích để kiểm tra quyền khi đã có một `Authentication` giả lập; nó không chứng minh mật khẩu đi qua `PasswordEncoder` hoặc HTTP Basic. Trong bài tổng hợp này, dùng `httpBasic` để kiểm chứng đầy đủ đường xác thực cơ bản. Khi cần kiểm thử quyền cấp role, có thể thêm `@WithMockUser(roles = "USER")` để tập trung vào authorization, nhưng phải hiểu mục đích khác nhau.

## 8. Giải thích cơ chế từ request đến controller

### Khi request không có credentials tới `/api/public`

1. Request đi vào servlet filter chain.
2. Không có thông tin HTTP Basic cần xác thực; ngữ cảnh có thể được xem là anonymous.
3. `AuthorizationFilter` chọn rule `GET /api/public` và thấy `permitAll()`.
4. Request vào `DispatcherServlet`, tìm `DemoController.publicInfo()`, trả JSON và status 200.

### Khi request không có credentials tới `/api/profile`

1. Security filter chain không xác thực được người dùng vì request chưa có credentials.
2. Không có rule công khai tương ứng, nên `anyRequest().authenticated()` áp dụng.
3. Request bị từ chối; cơ chế xử lý lỗi bảo mật gọi HTTP Basic entry point.
4. Client nhận **401** và có thể thử lại với Authorization header; method `profile()` không được gọi.

### Khi request có đúng credentials tới `/api/profile`

1. `BasicAuthenticationFilter` giải mã định dạng Basic và gọi quá trình xác thực.
2. Authentication provider truy vấn `UserDetailsService` để lấy user `learner` và hash BCrypt.
3. `PasswordEncoder.matches(...)` kiểm tra mật khẩu; thành công thì tạo `Authentication` đã xác thực.
4. Rule `authenticated()` được thỏa mãn; controller chạy, trả 200 và JSON.

Sơ đồ logic:

~~~text
GET /api/profile
       |
       v
Có header Basic? ---- không ----> Authentication chưa đạt
       |                                  |
      có                                  v
       |                          authenticated() từ chối
       v                                  |
Kiểm chứng user + password                 v
       |                                 401
       +---- sai -----------------------> 401
       |
      đúng
       |
       v
authenticated() cho phép
       |
       v
DemoController.profile()
       |
       v
200 {"message":"private"}
~~~

**Lưu ý về ranh giới:** `authenticated()` chỉ yêu cầu một danh tính hợp lệ. Nó **chưa chứng minh** người dùng được đọc bản ghi của người khác; đối với dữ liệu thật cần thêm phân quyền theo vai trò/chủ sở hữu ở controller/service/data layer. `profile()` của bài chỉ trả JSON giả lập để tập trung vào security pipeline.

## 9. Những thay đổi nhỏ có thể làm rò rỉ endpoint

| Sai sót | Hậu quả | Cách sửa/kiểm tra |
| --- | --- | --- |
| Dùng `.anyRequest().permitAll()` | Mở toàn bộ route chưa có rule cụ thể | Dùng `anyRequest().authenticated()` hoặc `denyAll()` tùy chính sách |
| Dùng `/api/**` với `permitAll()` | Vô tình công khai cả `/api/profile` | Matcher chính xác cho URL và HTTP method cần công khai |
| Test gọi thẳng controller | Security filter không tham gia | Test qua `MockMvc` có cấu hình Spring Security hoặc HTTP thật |
| Nhầm 401 và 403 | Chẩn đoán sai thiếu đăng nhập với thiếu quyền | Xem entry point, `Authentication`, authorization rule và CSRF |
| Dùng sai mật khẩu nhưng nghĩ `permitAll` phải trả 200 | Basic auth filter chặn credentials sai trước policy | Thử lại **không gửi Authorization header**, test riêng trường hợp sai creds |
| Chỉ test 200 với đúng user | Không phát hiện tài nguyên vô tình được mở cho anonymous | Bắt buộc test cả anonymous và sai mật khẩu |
| Giữ user/password cố định trong mã production | Dễ lộ credential | Dùng identity store, mã hóa mật khẩu, secrets và cơ chế rotation |
| Tắt toàn bộ Spring Security để sửa lỗi | Mất lớp bảo vệ cho toàn app | Kiểm tra filter chain, matcher, entry point và test trước khi đổi policy |
| Thấy 404 rồi cho rằng request an toàn | Có thể chỉ là URL sai/missing handler | Test endpoint **đang tồn tại** và xác minh 401/200 trên nó |
| Chỉ cấp bảo mật trên đường dẫn client đang dùng | Có thể bỏ sót context/servlet path hoặc route alias | Rà soát mapping thực và phép thử cho các URL biên |

### Vì sao không tùy tiện tắt CSRF?

Ví dụ chính dùng **GET**, không thay đổi trạng thái máy chủ. Cấu hình ở bước 5 **giữ cơ chế CSRF mặc định** của Spring Security. Nếu mở rộng thêm `POST /api/orders` dùng session/cookie hoặc browser login, phải kiểm thử request thiếu/sai/đúng CSRF token theo mô hình xác thực. `permitAll()` ở mức URL không đồng nghĩa tự động bỏ bảo vệ CSRF. API chỉ dùng bearer token không cookie có thể có thiết kế CSRF khác, nhưng cần đánh giá cơ chế lưu/đính kèm credentials trước khi quyết định.

Ví dụ minh họa test dành cho một endpoint POST **nếu bạn đã bổ sung controller tương ứng** (đoạn sau không chạy độc lập trong phiên bản project GET-only):

~~~java
// Cần import SecurityMockMvcRequestPostProcessors.csrf và post(...)
mockMvc.perform(post("/api/orders")
        .with(httpBasic("learner", "learning-only-password")))
    .andExpect(status().isForbidden());

mockMvc.perform(post("/api/orders")
        .with(httpBasic("learner", "learning-only-password"))
        .with(csrf()))
    .andExpect(status().isCreated());
~~~

Để assertion thứ hai đúng, controller phải thực sự trả **201 Created** và request phải vượt qua các kiểm tra nghiệp vụ. Không lấy `csrf()` như giải pháp bỏ qua bảo mật; đây là token test hợp lệ theo cơ chế Spring Security Test.

## 10. Tự mở rộng từ đăng nhập sang phân quyền vai trò

Sau khi tám test cơ bản đều xanh, thử thêm một endpoint `GET /api/admin` và yêu cầu chỉ `ADMIN` được phép. Giữ nguyên `/api/public` công khai và `/api/profile` chỉ cần đã đăng nhập.

Trong `SecurityConfig`, thêm rule **trước** `anyRequest()`:

~~~java
.authorizeHttpRequests(authorize -> authorize
    .requestMatchers(HttpMethod.GET, "/api/public").permitAll()
    .requestMatchers(HttpMethod.GET, "/api/admin").hasRole("ADMIN")
    .anyRequest().authenticated()
)
~~~

Đoạn trên **thay thế phần `authorizeHttpRequests` tương ứng**, không dán thêm lời gọi trùng nhau vào phương thức. Hãy tạo `@GetMapping("/api/admin")` trong controller trước khi test.

Thử ba tình huống với endpoint tồn tại:

- Khách chưa đăng nhập: **401** trong cấu hình HTTP Basic của bài.
- `learner` (có `ROLE_USER`): **403**, vì đã xác thực nhưng không có `ROLE_ADMIN`.
- User mới có `roles("ADMIN")` và mật khẩu hợp lệ: **200**.

`hasRole("ADMIN")` tìm authority `ROLE_ADMIN` theo prefix mặc định; nếu dùng `hasAuthority("...")`, hãy viết đúng chuỗi authority cần kiểm tra. Đây là bước nâng cấp **authorization** độc lập với yêu cầu tối thiểu `authenticated()`.

## 11. Cách tự chẩn đoán khi kết quả khác dự kiến

**`/api/public` vẫn trả 401 cho anonymous:** kiểm tra có thực sự khởi động mã mới, có `SecurityConfig` nằm dưới package được Spring Boot component scan, matcher có đúng method/URL, có thêm `SecurityFilterChain` khác, và request có mang credentials sai hay không.

**`/api/profile` trả 200 cho anonymous:** kiểm tra `anyRequest().authenticated()` còn tồn tại, cấu hình có bị thay bởi filter chain khác, test có gắn security filter và request có kèm cookie/Authorization header từ lần trước không.

**`/api/profile` trả 401 với đúng credentials:** kiểm tra username/password trong `curl`, bean `UserDetailsService` có được tạo, có lỗi encoder và log xử lý authentication không. Không chuyển mật khẩu sang `{noop}` trong production để chữa lỗi.

**401 đổi thành 302:** có thể form login đã được kích hoạt bởi cấu hình khác, hoặc client có `Accept` khác. Bài dùng explicit `httpBasic` và tắt `formLogin` để có status ổn định cho API.

**403 với POST:** phân biệt CSRF token và quyền; kiểm tra method HTTP, SecurityFilterChain, entry point, session/cookie. Bài GET-only không yêu cầu vô hiệu hóa CSRF.

**404 với request đã đăng nhập:** controller có khớp route không? `@GetMapping` đúng path chưa? Có `server.servlet.context-path` khác hoặc servlet prefix không? 404 không nhất thiết là lỗi Security.

Khi gỡ lỗi, có thể bật logging bảo mật ở **môi trường local** bằng cấu hình có kiểm soát, ví dụ `logging.level.org.springframework.security=DEBUG`; tuyệt đối không chia sẻ password, token, cookie hoặc HTTP Authorization header trong log công khai. Tắt bớt log khi đã xác định được nguyên nhân.

## 12. Bài tập nghiệm thu và tiêu chí đạt

1. Chạy phiên bản **chưa có Spring Security**, chứng minh `/api/public` và `/api/profile` đều 200 khi anonymous.
2. Thêm starter nhưng chưa tự khai báo `SecurityFilterChain`; chứng minh cả hai đều đòi đăng nhập theo cấu hình mặc định.
3. Thêm `SecurityConfig` từ bài, chạy lại cùng URL với anonymous, credentials sai và credentials đúng; ghi bảng status 200/401/200 đúng mục đích.
4. Chạy tám test. Cố tình đổi `permitAll()` của `/api/public` thành `authenticated()`, quan sát test `publicEndpointAllowsAnonymous` đỏ; trả cấu hình đúng và test xanh lại.
5. Viết giải thích vì sao anonymous gọi URL không có controller có thể nhận 401 trước khi nhận 404, và vì sao `permitAll` không cứu một Basic credential sai.
6. Hoàn thành phần tùy chọn `/api/admin`: thêm role ADMIN, test anonymous/USER/ADMIN, giải thích vì sao USER nhận 403.
7. Liệt kê các ràng buộc cần nâng cấp trước production: identity store, TLS, secret management, kiểm soát dữ liệu theo chủ sở hữu, CSRF/CORS/session, logging và test hồi quy.

**Đạt bài khi:** bạn có ứng dụng thực sự chạy, chỉ đúng một endpoint GET được mở công khai theo thiết kế, endpoint còn lại yêu cầu đăng nhập, và bộ kiểm thử phát hiện được cả lỗi **chặn nhầm public** lẫn lỗi **mở nhầm private**. Bạn giải thích được cơ chế `SecurityFilterChain → authentication → authorization → controller` bằng trạng thái HTTP quan sát được.

## 13. Tài liệu chính thức để đối chiếu

- [Spring Security — Servlet Security Architecture](https://docs.spring.io/spring-security/reference/servlet/architecture.html): thứ tự và vai trò các filter.
- [Spring Security — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): `requestMatchers`, `permitAll`, `authenticated`, rule ordering và `hasRole`.
- [Spring Security — Java Configuration](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html): `HttpSecurity` và `SecurityFilterChain`.
- [Spring Security — Username/Password Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/index.html): `UserDetailsService`, authentication provider, encoder.
- [Spring Security — Servlet Testing](https://docs.spring.io/spring-security/reference/servlet/test/index.html): tích hợp kiểm thử bảo mật với Spring Test/MockMvc.
- [Spring Security — Testing CSRF Protection](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html): hỗ trợ `csrf()`.
- [Spring Boot — Build Systems](https://docs.spring.io/spring-boot/reference/using/build-systems.html): Gradle và dependency management.

Tài liệu `/reference/` trực tuyến thường hiển thị phiên bản hiện hành. Khi học với ví dụ cố định Spring Boot 3.3.5, hãy chọn **version selector** phù hợp với phiên bản Spring Security của BOM dự án nếu chi tiết API/default có khác. Mọi thay đổi major version phải được đối chiếu với migration guide của phiên bản đích.
