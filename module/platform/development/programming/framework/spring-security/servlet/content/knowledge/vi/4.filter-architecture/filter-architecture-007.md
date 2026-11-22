# AuthorizationFilter và vị trí kiểm tra quyền truy cập trong Spring Security Servlet

## 1. AuthorizationFilter giải quyết vấn đề gì?

Trong ứng dụng Servlet dùng Spring Security, **xác thực** (*authentication*) và **phân quyền** (*authorization*) là hai quyết định khác nhau:

- **Xác thực:** request có đại diện cho một người dùng hoặc principal được xác nhận hay không? Nếu có, danh tính và các authority của họ là gì?
- **Phân quyền:** request này có được phép truy cập tài nguyên cụ thể với danh tính/authority hiện tại hay không?

`AuthorizationFilter` là một **Servlet Filter** trong chuỗi Spring Security, chịu trách nhiệm thực thi quy tắc **phân quyền ở tầng HTTP request**. Nó thường nhận quyết định từ một `AuthorizationManager<ServletRequest>`, rồi:

1. **Cho phép:** gọi `chain.doFilter(request, response)` để request tiếp tục đến filter sau hoặc ứng dụng.
2. **Từ chối:** ném ngoại lệ thuộc họ `AccessDeniedException`; phần xử lý ngoại lệ bảo mật ở phía trước có thể biến ngoại lệ thành HTTP 401, HTTP 403 hoặc chuyển hướng phù hợp với cấu hình.

Nó **không tự xác thực username/password**, không phải controller, và cũng **không trực tiếp quyết định status 401/403 cho mọi trường hợp**. Việc tạo response cuối thường do các thành phần khác như `ExceptionTranslationFilter`, `AuthenticationEntryPoint` và `AccessDeniedHandler` phối hợp.

Bài này tập trung vào cơ chế của `AuthorizationFilter`, vị trí của nó trong bộ lọc Servlet và cách quy tắc `authorizeHttpRequests` tác động lên request.

## 2. Vị trí trong kiến trúc filter: kiểm tra quyền trước khi vào endpoint

Spring Security tích hợp với Servlet container thông qua chuỗi lọc. Một luồng **khái niệm** thường gặp có dạng:

```text
HTTP request
  |
  v
Servlet container FilterChain
  |
  v
DelegatingFilterProxy ("springSecurityFilterChain")
  |
  v
FilterChainProxy
  |  chọn SecurityFilterChain đầu tiên khớp request
  v
[SecurityContext / authentication-related filters]
  |
  v
[AnonymousAuthenticationFilter, nếu được cấu hình]
  |
  v
ExceptionTranslationFilter
  |  bao quanh các filter phía dưới để xử lý ngoại lệ bảo mật
  v
AuthorizationFilter
  |  đánh giá quy tắc authorizeHttpRequests
  +---- DENY ---> AccessDeniedException
  |                ^
  |                | ExceptionTranslationFilter xử lý
  |                +--> entry point / access denied handler
  |
  +---- ALLOW ---> chain.doFilter(...)
                    |
                    v
              phần còn lại của chain
                    |
                    v
              DispatcherServlet
                    |
                    v
              Controller / endpoint
```

Sơ đồ chỉ trình bày **vị trí và trách nhiệm chính**, không phải danh sách đầy đủ hay thứ tự bất biến của mọi phiên bản/cấu hình. Authentication filters có thể khác nhau giữa HTTP Basic, form login, bearer token, OAuth2, v.v. Filter tự viết cũng có thể được thêm vào trước hoặc sau `AuthorizationFilter`.

Ba tầng cần tách bạch:

| Thành phần | Vai trò |
| --- | --- |
| Servlet container `FilterChain` | Quản lý việc chuyển tiếp giữa các Servlet Filter và đích cuối. |
| `FilterChainProxy` | Chọn và chạy **một** `SecurityFilterChain` phù hợp trong danh sách đã cấu hình. |
| `SecurityFilterChain` | Chứa tập security filters áp dụng cho một nhóm request; nó **không đồng nghĩa** với một rule `requestMatchers`. |
| `AuthorizationFilter` | Đánh giá phân quyền HTTP ở vị trí của nó trong chain được chọn; nếu cho phép thì tiếp tục. |
| `ExceptionTranslationFilter` | Bắt các ngoại lệ xác thực/phân quyền phát sinh từ các thành phần phía dưới, chuyển thành cơ chế phản hồi bảo mật. |

Theo cấu hình hiện đại dùng `authorizeHttpRequests`, `AuthorizationFilter` thường nằm **gần cuối chuỗi security filters chuẩn**, sau các filter thiết lập ngữ cảnh/xác thực và sau `ExceptionTranslationFilter`. Nói “gần cuối” chính xác hơn “luôn là filter cuối”: có thể có custom filters hoặc container filters khác, và thứ tự thực tế phải xem cấu hình đang chạy.

### Tại sao `ExceptionTranslationFilter` đứng trước `AuthorizationFilter`?

Khi `AuthorizationFilter` phát hiện không đủ quyền, nó ném một ngoại lệ kiểu `AccessDeniedException`. `ExceptionTranslationFilter` ở phía trước đang bao quanh lời gọi tới các filter phía sau, nên có thể bắt ngoại lệ và lựa chọn hành động:

- Principal chưa xác thực theo cơ chế đang dùng: kích hoạt `AuthenticationEntryPoint` (ví dụ HTTP 401 với Basic/Bearer, hoặc redirect đến trang đăng nhập với form login).
- Principal đã được xác thực nhưng thiếu quyền: chuyển cho `AccessDeniedHandler` (thường trả HTTP 403).

`ExceptionTranslationFilter` **không phải thành phần đưa ra quyết định quyền truy cập**. Nó chuyển ngoại lệ thành phản hồi thích hợp; chính `AuthorizationFilter` / `AuthorizationManager` kiểm tra quy tắc HTTP request trong trường hợp đang xét.

## 3. AuthorizationFilter thực hiện những bước nào?

Với một request đã đi vào chuỗi security filter được chọn, quá trình có thể hiểu như sau:

1. Những filter ở phía trước thiết lập `SecurityContext` và xử lý cơ chế xác thực được cấu hình; khi phù hợp có thể xuất hiện `AnonymousAuthenticationToken` cho request chưa đăng nhập.
2. `AuthorizationFilter` có quyền truy cập `HttpServletRequest` (qua giao diện `ServletRequest`) và một cách lấy `Authentication` hiện tại.
3. `AuthorizationManager<ServletRequest>` đánh giá request theo các quy tắc, chẳng hạn `permitAll`, `authenticated`, `hasRole`, `hasAuthority` hoặc một policy tự viết.
4. Nếu **được phép**, `AuthorizationFilter` gọi `chain.doFilter`; controller có cơ hội chạy nếu các thành phần sau không chặn.
5. Nếu **bị từ chối**, nó **không** gọi tiếp chain theo nhánh đó và ngoại lệ bảo mật đi ngược lên để được xử lý.

Một cách mô tả **giản lược**, không phải mã nguồn nguyên văn của framework:

```java
// Pseudocode mô tả ý tưởng, không phải một lớp Java độc lập.
AuthorizationResult result =
    authorizationManager.authorize(authenticationSupplier, request);

if (result != null && !result.isGranted()) {
    throw new AccessDeniedException("Forbidden");
}

chain.doFilter(request, response);
```

**Lưu ý về API:** các phiên bản Spring Security có khác biệt về kiểu kết quả, phương thức và ngoại lệ cụ thể. Ví dụ trên chỉ minh họa hai nhánh ALLOW/DENY; không dùng để copy thay implementation của `AuthorizationFilter`. Một số cơ chế policy có thể biểu diễn quyết định bằng các kiểu như `AuthorizationDecision` / `AuthorizationResult`; hãy dùng API đúng với dependency thực tế.

### Cách lấy Authentication có thể là lazy

Hệ thống phân quyền có thể nhận `Supplier<Authentication>`, nhờ đó không nhất thiết phải lấy `Authentication` ngay nếu một quy tắc không cần tới danh tính. Ví dụ, một request khớp `permitAll()` có thể được cho phép mà không cần truy cập `Authentication` trong quá trình quyết định. Điều này giải thích vì sao “được permit” và “đã xác thực” hoàn toàn khác nhau.

**`permitAll()` cho phép request đi qua bước phân quyền HTTP này; nó không chứng minh request đã đăng nhập, cũng không bỏ qua toàn bộ security filter chain.**

## 4. Quy tắc được chọn ở đâu: `securityMatcher` và `requestMatchers`

Có **hai mức matching** quan trọng, rất dễ nhầm:

**Mức 1 – Chọn chuỗi:** `FilterChainProxy` xét các `SecurityFilterChain` theo thứ tự đã cấu hình và dùng **chuỗi đầu tiên khớp request**. Ví dụ, một chain có `http.securityMatcher("/api/**")` chỉ áp dụng cho nhóm đường dẫn đó.

**Mức 2 – Chọn quy tắc trong chuỗi:** `AuthorizationFilter` của chuỗi đã chọn dựa vào `AuthorizationManager` mà `authorizeHttpRequests` xây dựng, để áp dụng rule tương ứng, chẳng hạn `requestMatchers("/admin/**").hasRole("ADMIN")`. Với cấu hình matcher tuần tự điển hình, **quy tắc khớp đầu tiên** được áp dụng.

```text
Incoming request: GET /admin/panel
     |
     v
FilterChainProxy:
  chain #1 securityMatcher("/api/**")      -> không khớp
  chain #2 (fallback cho các request khác) -> khớp
     |
     v
AuthorizationFilter của chain #2:
  requestMatchers("/public/**") -> không khớp
  requestMatchers("/admin/**")  -> khớp, cần ROLE_ADMIN
  anyRequest().authenticated() -> không xét tới
```

Nếu **không có SecurityFilterChain nào khớp**, request không đi qua chuỗi security filters của Spring Security tại vị trí proxy đó; hậu quả có thể là endpoint không được Spring Security bảo vệ. Vì vậy khi cấu hình nhiều chains, cần kiểm tra vùng request được bao phủ và định nghĩa fallback phù hợp.

`securityMatcher(...)` và `requestMatchers(...)` khác vai trò: cái đầu giới hạn **phạm vi của cả security chain**, cái sau định nghĩa **quy tắc phân quyền bên trong chain đã chọn**.

## 5. Quy tắc hiện đại với `authorizeHttpRequests`

Trong Spring Security 6.x với ứng dụng Spring Boot 3.x, cách khai báo phân quyền HTTP thường dùng DSL:

```java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    http.authorizeHttpRequests(auth -> auth
            .requestMatchers("/public/**").permitAll()
            .requestMatchers("/admin/**").hasRole("ADMIN")
            .anyRequest().authenticated()
        )
        .httpBasic(Customizer.withDefaults());

    return http.build();
}
```

Đây là **đoạn cấu hình thuộc một lớp `@Configuration`**, cần import các kiểu `@Bean`, `HttpSecurity`, `SecurityFilterChain`, `Customizer` và môi trường Spring Boot/Spring Security tương ứng. Ví dụ chạy đầy đủ nằm ở phần tiếp theo.

Cách đọc các rule:

- `/public/**`: ai cũng được qua bước phân quyền HTTP, kể cả anonymous.
- `/admin/**`: cần authority `ROLE_ADMIN`; `hasRole("ADMIN")` mặc định kiểm tra authority với tiền tố `ROLE_`.
- `anyRequest().authenticated()`: các request còn lại cần principal đã xác thực theo định nghĩa của Spring Security.
- `httpBasic(...)`: bật HTTP Basic để ví dụ có cơ chế challenge rõ ràng khi người dùng chưa xác thực.

**Thứ tự cực kỳ quan trọng.** Nếu khai báo matcher tổng quát trước matcher hẹp, quy tắc tổng quát có thể che khuất quy tắc hẹp, hoặc DSL có thể từ chối cấu hình không hợp lệ sau `anyRequest()`. Nên đặt rule cụ thể trước và `anyRequest()` ở cuối.

### `hasRole` và `hasAuthority`

- `hasRole("ADMIN")`: theo tiền tố vai trò mặc định, yêu cầu authority `ROLE_ADMIN`.
- `hasAuthority("ROLE_ADMIN")`: kiểm tra chính xác chuỗi `ROLE_ADMIN`, thường tương đương với ví dụ trên.
- `hasAuthority("ADMIN")`: kiểm tra chính xác `ADMIN`, **không tương đương** nếu người dùng chỉ có `ROLE_ADMIN`.
- `authenticated()`: kiểm tra đã xác thực, **không đồng nghĩa** có quyền admin.

Tiền tố mặc định có thể được cấu hình lại; khi làm dự án thực, xem authority thực tế trong `Authentication` và chính sách của ứng dụng.

## 6. Ví dụ Spring Boot 3 + Java 17: kiểm chứng request bị cho phép hoặc từ chối

Ví dụ gồm ứng dụng Servlet tối giản dùng Spring MVC, một `SecurityFilterChain`, ba endpoint và kiểm thử `MockMvc`. Tất cả request kiểm thử là **GET**, để tập trung vào `AuthorizationFilter` mà không lẫn với kiểm tra CSRF cho thao tác thay đổi dữ liệu.

Cấu trúc thư mục:

```text
authorization-filter-demo/
  pom.xml
  src/
    main/
      java/
        demo/
          security/
            AuthorizationDemoApplication.java
            SecurityConfig.java
            EndpointController.java
    test/
      java/
        demo/
          security/
            AuthorizationFlowTest.java
```

### 6.1. Dependencies

File `pom.xml`:

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
    <artifactId>authorization-filter-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
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

Đây là một phiên bản Spring Boot 3.x cụ thể, dùng Java 17. Chạy trong dự án Maven có JDK 17+ và Maven được cài đặt; Maven tải các dependency lần đầu nếu chưa có trong cache.

### 6.2. Lớp khởi động

`src/main/java/demo/security/AuthorizationDemoApplication.java`:

```java
package demo.security;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AuthorizationDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(AuthorizationDemoApplication.class, args);
    }
}
```

### 6.3. Cấu hình phân quyền

`src/main/java/demo/security/SecurityConfig.java`:

```java
package demo.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/public/**").permitAll()
                .requestMatchers("/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }
}
```

Cấu hình này tạo một security chain mặc định cho request web; DSL `authorizeHttpRequests` làm cho cơ chế phân quyền HTTP tương ứng dùng `AuthorizationFilter`. Đây là ví dụ **HTTP Basic để quan sát kết quả**; ứng dụng thực có thể thay bằng form login, OAuth2 Resource Server hoặc một cơ chế xác thực khác mà vẫn cần quy tắc phân quyền.

### 6.4. Ba endpoint dễ quan sát

`src/main/java/demo/security/EndpointController.java`:

```java
package demo.security;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class EndpointController {

    @GetMapping("/public/ping")
    String publicPing() {
        return "public";
    }

    @GetMapping("/private/ping")
    String privatePing() {
        return "private";
    }

    @GetMapping("/admin/ping")
    String adminPing() {
        return "admin";
    }
}
```

### 6.5. Kiểm thử bằng MockMvc và tài khoản giả lập

`src/test/java/demo/security/AuthorizationFlowTest.java`:

```java
package demo.security;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class AuthorizationFlowTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicEndpointAllowsAnonymous() throws Exception {
        mvc.perform(get("/public/ping"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));
    }

    @Test
    void privateEndpointChallengesAnonymous() throws Exception {
        mvc.perform(get("/private/ping"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void privateEndpointAllowsAuthenticatedUser() throws Exception {
        mvc.perform(get("/private/ping")
                .with(user("reader").roles("USER")))
            .andExpect(status().isOk())
            .andExpect(content().string("private"));
    }

    @Test
    void adminEndpointChallengesAnonymous() throws Exception {
        mvc.perform(get("/admin/ping"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void adminEndpointDeniesOrdinaryUser() throws Exception {
        mvc.perform(get("/admin/ping")
                .with(user("reader").roles("USER")))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminEndpointAllowsAdmin() throws Exception {
        mvc.perform(get("/admin/ping")
                .with(user("alice").roles("ADMIN")))
            .andExpect(status().isOk())
            .andExpect(content().string("admin"));
    }
}
```

Các `user("...").roles("...")` là **principal giả lập trong bài kiểm thử** do `spring-security-test` tạo, không cần lưu mật khẩu thật trong ví dụ. `@AutoConfigureMockMvc` thiết lập MockMvc có tích hợp các Servlet Filters của ứng dụng. Việc gọi `get(...)` là request thông qua HTTP MVC test pipeline, không phải gọi trực tiếp phương thức controller.

Trong thư mục có `pom.xml`, chạy:

```bash
mvn test
mvn spring-boot:run
```

`mvn test` chạy sáu phép thử; nếu đúng cấu hình, cả sáu assertion thành công. Output của Maven có thông tin môi trường/thời gian nên **không có stdout cố định** để chép nguyên văn. Lệnh `mvn spring-boot:run` khởi động server, để có thể thử GET `http://localhost:8080/public/ping`. Kết quả phần thân của request công khai là `public`; response status là 200. Với request chưa đăng nhập tới `/private/ping`, cấu hình HTTP Basic trả 401. Không có tài khoản production được cấu hình trong ví dụ này; các tài khoản kiểm thử **không tự trở thành tài khoản có thể đăng nhập qua HTTP Basic ngoài test**.

### 6.6. Bảng giải thích sáu kịch bản kiểm thử

| Request | Principal trong test | Quy tắc được chọn | Kết quả mong đợi |
| --- | --- | --- | --- |
| GET `/public/ping` | Anonymous | `permitAll` | 200, body `public` |
| GET `/private/ping` | Anonymous | `authenticated` | 401 với HTTP Basic |
| GET `/private/ping` | Có `ROLE_USER` | `authenticated` | 200, body `private` |
| GET `/admin/ping` | Anonymous | `hasRole("ADMIN")` | 401 với HTTP Basic |
| GET `/admin/ping` | Có `ROLE_USER` | `hasRole("ADMIN")` | 403 |
| GET `/admin/ping` | Có `ROLE_ADMIN` | `hasRole("ADMIN")` | 200, body `admin` |

Bảng trên mô tả **kết quả cho cấu hình HTTP Basic cụ thể**, không phải khẳng định mọi ứng dụng Spring Security trả cùng mã: chẳng hạn form login có thể redirect đến trang đăng nhập.

## 7. Vì sao 401 và 403 không phải do AuthorizationFilter tự ghi response?

Hãy xét hai request tới `/admin/ping` trong ví dụ:

**A. Chưa đăng nhập:** manager từ chối vì principal không có authority yêu cầu. Ngoại lệ phân quyền được đưa lên `ExceptionTranslationFilter`, nơi cơ chế xác thực xác định cần bắt đầu đăng nhập. Với HTTP Basic, `AuthenticationEntryPoint` có thể tạo phản hồi `401 Unauthorized` cùng thử thách Basic phù hợp.

**B. Đã đăng nhập với `ROLE_USER`:** request thiếu `ROLE_ADMIN`, nhưng principal không cần được challenge đăng nhập lại theo chính sách thông thường. `AccessDeniedHandler` xử lý thiếu quyền và trả `403 Forbidden`.

Nghĩa là một quyết định **DENY** tại `AuthorizationFilter` có thể đưa tới các response khác nhau tùy `Authentication` và các handler. Chỉ nhìn log `AccessDeniedException` không đủ để khẳng định status cuối cùng.

Ngược lại, khi **ALLOW**, request còn đi qua các bước khác. Cho phép ở `AuthorizationFilter` **không bảo đảm cuối cùng nhận 200**: controller có thể trả 404/500, phương thức có thể bị method security từ chối, hoặc các filter khác có thể ngăn request.

## 8. Những điều AuthorizationFilter không làm

### 8.1. Không thay thế authentication filter

`UsernamePasswordAuthenticationFilter`, `BasicAuthenticationFilter`, filter bearer-token và cơ chế xác thực tương ứng xử lý thông tin xác thực theo cấu hình. `AuthorizationFilter` sử dụng trạng thái đã được thiết lập để kiểm tra chính sách truy cập HTTP. Một request chưa đăng nhập nhưng khớp `permitAll` vẫn có thể đi tiếp.

### 8.2. Không thay thế CSRF protection

`permitAll()` không có nghĩa mọi filter khác sẽ bỏ qua request. Ví dụ, một **POST** làm thay đổi dữ liệu có thể bị `CsrfFilter` từ chối do thiếu token, dù đường dẫn được `permitAll()`. Đây không phải bằng chứng `AuthorizationFilter` tự thay đổi chính sách của nó.

Khi debug, phân biệt lỗi do `AuthorizationFilter`, `CsrfFilter`, filter xác thực hoặc controller. Không tắt CSRF cho cả ứng dụng chỉ để “sửa” một response 403 chưa rõ nguyên nhân.

### 8.3. Không thay thế method security

`AuthorizationFilter` kiểm tra request ở tầng web, trước khi thực thi controller trong luồng bình thường. Nếu hệ thống còn bật method security (ví dụ `@EnableMethodSecurity` và `@PreAuthorize`), việc kiểm tra method diễn ra ở điểm gọi method được bảo vệ. Request có thể qua `AuthorizationFilter` nhưng sau đó vẫn bị từ chối ở method, và ngoại lệ có thể được chuyển thành phản hồi HTTP phù hợp bởi security infrastructure.

Quy tắc HTTP và quy tắc method bổ sung cho nhau; không suy luận rằng cho phép ở một tầng sẽ tự động bỏ qua tầng còn lại.

### 8.4. Không tự quản lý tất cả các SecurityFilterChain

Một ứng dụng có nhiều `SecurityFilterChain` có thể phân nhóm API/public/admin. `FilterChainProxy` lựa chọn chain, rồi `AuthorizationFilter` trong chain đó mới xử lý. Do đó, muốn biết một request chịu rule nào phải **xác định chain khớp trước**.

## 9. Hai mức cấu hình ảnh hưởng tới vị trí kiểm tra quyền

### 9.1. Phân quyền ở cuối chuỗi được chọn

Trong đa số cấu hình DSL thông thường, authentication/security context được thiết lập trước `AuthorizationFilter`. Điều này hợp lý vì rule như `hasRole("ADMIN")` cần dữ liệu authority.

Tuy nhiên nếu tự thêm một filter chạy **sau** `AuthorizationFilter`, filter đó chỉ nhận request đã được phép qua điểm kiểm tra HTTP; việc nó chạy sau không chứng minh các quy tắc bảo mật khác đã hoàn thành. Ngược lại, filter đặt **trước** `AuthorizationFilter` có thể xử lý request trước khi quyết định HTTP authorization xảy ra.

Thêm custom filter nên có mục đích và vị trí rõ ràng. Đừng đặt filter tạo response thành công trước authorization rồi vô tình chặn toàn bộ phần kiểm tra quyền.

### 9.2. Nhiều security chains và fallback

Ví dụ minh họa **cấu hình khác**, không dán đồng thời với `SecurityConfig` của phần 6 khi chưa chủ động thay thế:

```java
@Configuration
public class MultipleChainsConfig {

    @Bean
    @Order(1)
    SecurityFilterChain internal(HttpSecurity http) throws Exception {
        http.securityMatcher("/internal/**")
            .authorizeHttpRequests(auth -> auth
                .anyRequest().hasRole("OPS"))
            .httpBasic(Customizer.withDefaults());
        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain rest(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults());
        return http.build();
    }
}
```

Đoạn trên cần imports `Configuration`, `Bean`, `Order`, `HttpSecurity`, `SecurityFilterChain`, `Customizer` và được dùng trong dự án có dependency Spring Security tương ứng. Với `GET /internal/report`, chain `@Order(1)` khớp và yêu cầu `ROLE_OPS`; request `GET /other` đi tới chain fallback, chỉ yêu cầu xác thực. `anyRequest()` trong từng chain **không mở rộng** phạm vi `securityMatcher` của chain đó.

Nếu không có chain fallback bao phủ `/other`, Spring Security sẽ không áp dụng các filter thuộc chain ở đây cho request này. Một ứng dụng có yêu cầu an ninh cao nên kiểm tra kỹ mọi đường dẫn, cả route không có trong controller, thay vì mặc định “chắc chắn có AuthorizationFilter ở mọi request”.

### 9.3. Legacy FilterSecurityInterceptor

Ở các cấu hình Spring Security cũ, bạn có thể gặp `FilterSecurityInterceptor` gắn với DSL `authorizeRequests` và cách kiểm tra quyền kiểu cũ. Với `authorizeHttpRequests` hiện đại, `AuthorizationFilter` cùng `AuthorizationManager` là mô hình trọng tâm. Khi đọc log hoặc source của dự án, **kiểm tra loại filter đang được đăng ký thực tế**, không coi cả hai tên là cùng một instance hoặc buộc mọi phiên bản dùng cùng một pipeline.

## 10. Dispatcher types: cùng HTTP request vẫn có thể bị kiểm tra nhiều lần

Servlet có nhiều loại dispatch, như `REQUEST`, `FORWARD`, `ERROR` và `ASYNC`. Filter có chạy ở một dispatch cụ thể hay không phụ thuộc đăng ký của Servlet container/Spring Boot, cấu hình security và điều kiện dispatch.

Khi `AuthorizationFilter` được gọi ở một dispatch khác, việc kiểm tra quyền **có thể diễn ra lại**. Ví dụ một request đã được phép đến controller nhưng sau đó được forward tới trang hiển thị có quy tắc khác. Một xử lý lỗi có thể chuyển đến `/error`; nếu security chain áp dụng cho `ERROR` và rule của bạn đòi hỏi xác thực, trang lỗi cũng có thể bị chặn.

Có thể cấu hình cho phép các dispatcher cần thiết, **sau khi cân nhắc phạm vi ứng dụng**:

```java
// Đặt trong DSL authorizeHttpRequests của HttpSecurity:
.dispatcherTypeMatchers(
    DispatcherType.FORWARD,
    DispatcherType.ERROR
).permitAll()
```

Đây là **mảnh cấu hình**, cần import `jakarta.servlet.DispatcherType` và đặt đúng vị trí trong chuỗi matcher trước `anyRequest()`. Việc cho phép toàn bộ FORWARD/ERROR là quyết định bảo mật cụ thể, không phải chỉ dẫn mặc định cho mọi dự án: nếu forward có thể tới nội dung nhạy cảm, phải xem xét chính sách tương ứng. Đừng bật/tắt dispatcher rules chỉ dựa trên giả định một HTTP request chỉ đi qua security một lần.

## 11. `permitAll()` không giống bỏ qua Spring Security

Có khác biệt giữa:

- **`requestMatchers("/public/**").permitAll()`:** request vẫn đi vào `SecurityFilterChain` được chọn; `AuthorizationFilter` cho phép ở bước HTTP authorization, còn các filter khác có thể chạy như thường lệ.
- **Cấu hình bỏ qua qua `WebSecurityCustomizer#ignoring`:** request khớp có thể bỏ qua toàn bộ security filter chain; điều này cũng làm mất các khả năng cung cấp bởi security filters, chẳng hạn thiết lập một số security headers.

Trong đa số trường hợp muốn làm endpoint công khai nhưng vẫn duy trì cơ chế bảo mật HTTP chung, `permitAll()` là cách biểu đạt chính sách rõ ràng hơn. Việc bỏ qua toàn bộ security chain cần lý do thiết kế cụ thể.

## 12. Chẩn đoán request bị từ chối đúng vị trí

Khi gặp một request 401/403 hoặc controller không chạy, hãy điều tra theo thứ tự nguyên nhân:

1. **Xác định request thật:** method, path, context path, dispatcher type và trạng thái authentication. Đừng ghi password, session identifier hoặc bearer token vào log.
2. **Xác định SecurityFilterChain được chọn:** nếu có nhiều chain, kiểm tra `securityMatcher` và `@Order`; đừng nhảy ngay vào `requestMatchers` của một chain không khớp.
3. **Xác định filter tạo ra chặn:** đã tới `AuthorizationFilter` chưa? Hay `CsrfFilter`, filter xác thực hoặc custom filter đã kết thúc trước đó?
4. **Xác định rule phân quyền:** request khớp `permitAll`, `authenticated`, `hasRole`, `hasAuthority` hay fallback nào? Kiểm tra thứ tự matcher và authority thực tế (ví dụ `ROLE_ADMIN`).
5. **Theo dõi kết quả DENY:** ngoại lệ tới `ExceptionTranslationFilter` chưa? Thành phần nào là `AuthenticationEntryPoint` hay `AccessDeniedHandler` đang hoạt động? Điều này giải thích khác biệt 401/403/302.
6. **Nếu ALLOW nhưng vẫn lỗi:** xem các thành phần phía sau, method security, controller, exception handling và các dispatch tiếp theo.

Trong môi trường phát triển, có thể bật log để quan sát chuỗi xử lý:

```properties
logging.level.org.springframework.security=DEBUG
```

Log DEBUG hữu ích nhưng không nhất thiết thể hiện mọi quyết định chi tiết; mức TRACE có thể cung cấp thêm thông tin. Khi xử lý dữ liệu thật, xem nội dung log để tránh rò rỉ thông tin nhạy cảm và chỉ bật mức chi tiết trong môi trường kiểm soát phù hợp.

### Các hiểu lầm rất hay gặp

| Hiểu lầm | Sửa cách hiểu |
| --- | --- |
| “AuthorizationFilter chạy trước mọi filter xác thực.” | Trong chuỗi hiện đại thông thường, authentication/context filters chạy phía trước; phải xem thứ tự thực tế nếu có custom filter. |
| “AuthorizationFilter trực tiếp ghi status 401 hoặc 403.” | Nó đánh giá quyền và có thể ném ngoại lệ. Exception translation/entry point/handler quyết định phản hồi cuối. |
| “Có `permitAll` nên request bypass toàn bộ bảo mật.” | Chỉ cho phép qua bước HTTP authorization tương ứng; CSRF, headers và các filter khác vẫn có thể áp dụng. |
| “`hasRole("ADMIN")` kiểm tra authority `ADMIN`.” | Mặc định kiểm tra `ROLE_ADMIN`. |
| “`authenticated` nghĩa là có quyền truy cập tất cả endpoint.” | Nó chỉ yêu cầu đã xác thực; các endpoint có role/authority riêng vẫn có thể từ chối. |
| “`anyRequest` áp dụng cho mọi chain trong ứng dụng.” | Nó áp dụng trong `SecurityFilterChain` đang cấu hình, sau điều kiện chọn chain. |
| “Một HTTP request chỉ bị kiểm tra quyền đúng một lần.” | Cần xem dispatcher types, các lần dispatch và filter registration. |
| “AuthorizationFilter cho phép tức là controller chắc chắn trả 200.” | Sau điểm đó vẫn có thể có filter khác, method security, exception hoặc response khác 200. |
| “HTTP 403 luôn là thiếu role.” | CSRF, custom filter hoặc controller cũng có thể tạo 403. Cần truy vết nơi quyết định thực tế. |

## 13. Bài tập suy luận theo dòng chảy

**Tình huống 1 – Hai quyền khác nhau.** Một user có authority `ROLE_USER` gửi `GET /admin/ping`. Rule là `hasRole("ADMIN")` và app dùng HTTP Basic. `AuthorizationFilter` cho phép hay từ chối? Status thông thường?

**Đáp án:** Từ chối do thiếu `ROLE_ADMIN`. Khi principal đã xác thực, `ExceptionTranslationFilter` và `AccessDeniedHandler` thường tạo 403. Đừng kết luận 401 chỉ vì người dùng “không vào được”.

**Tình huống 2 – Một request công khai.** Anonymous gọi `GET /public/ping` khớp `permitAll()`. Có phải `AuthorizationFilter` xác thực anonymous thành một tài khoản hợp lệ trước khi vào controller?

**Đáp án:** Không. `permitAll` cho phép mà không yêu cầu danh tính đã xác thực. Request tiếp tục theo chain; không nên coi bước này là cơ chế đăng nhập.

**Tình huống 3 – Matcher nằm trong chain không được chọn.** Chain #1 có `securityMatcher("/api/**")` và bên trong định nghĩa `requestMatchers("/admin/**").hasRole("ADMIN")`. Request `GET /admin/ping` có chịu rule admin này không?

**Đáp án:** Không, vì chuỗi #1 không khớp `/admin/ping`. Phải xác định chain khác có khớp không; matcher trong chain không được chọn sẽ không kiểm tra request này.

**Tình huống 4 – GET được, POST bị 403.** Cùng đường dẫn `/public/update` đã cấu hình `permitAll`, GET chạy được nhưng POST không có CSRF token bị 403. Có phải AuthorizationFilter bỏ qua `permitAll`?

**Đáp án:** Chưa có cơ sở. `CsrfFilter` có thể chặn POST trước điểm kiểm tra HTTP authorization. Phải xác định filter phát sinh lỗi, không sửa policy bằng cách tắt CSRF tùy tiện.

**Tình huống 5 – Đến được controller nhưng vẫn bị từ chối.** Request vượt qua `AuthorizationFilter`, nhưng phương thức service có `@PreAuthorize` từ chối. Có mâu thuẫn không?

**Đáp án:** Không. Đó là hai điểm kiểm tra khác nhau: HTTP request-level và method-level. Việc qua được tầng thứ nhất không xóa kiểm tra tại tầng thứ hai.

## 14. Ghi nhớ để áp dụng

- `AuthorizationFilter` thực hiện **HTTP request authorization**, thường qua `AuthorizationManager<ServletRequest>`, và chỉ gọi tiếp `chain.doFilter` khi request được phép.
- Nó hoạt động **trong SecurityFilterChain đã được FilterChainProxy chọn**; `securityMatcher` chọn chain, `requestMatchers` chọn policy trong chain.
- Với DSL `authorizeHttpRequests`, hãy đặt matcher cụ thể trước `anyRequest`. Kiểm tra chính xác `ROLE_` prefix khi dùng `hasRole`.
- **`ExceptionTranslationFilter` ở phía trước** có nhiệm vụ xử lý ngoại lệ bảo mật từ các filter phía dưới; mã 401, 403 hoặc redirect phụ thuộc cơ chế xác thực và handler.
- `permitAll()` không bỏ qua toàn bộ security filters, không thay thế CSRF, không tự xác thực người dùng và không bảo đảm response 200.
- Debug theo thứ tự **chain được chọn → filter chặn → matcher/policy → principal/authority → exception translation → response**, đồng thời xét dispatcher types, custom filters và method security.
