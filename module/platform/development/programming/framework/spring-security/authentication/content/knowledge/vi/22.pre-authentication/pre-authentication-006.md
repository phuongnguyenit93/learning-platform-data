# JEE pre-authentication và danh tính do Servlet Container cung cấp trong Spring Security

## 1. Bối cảnh và mục tiêu

Trong một ứng dụng Java web chạy trên **Servlet Container** (ví dụ Apache Tomcat, một Jakarta EE application server), chính container có thể xác thực người dùng trước khi request đến ứng dụng. Khi đó Spring Security không cần hỏi lại mật khẩu; nó **tiếp nhận danh tính đã được container xác minh** để tạo đối tượng `Authentication` và thực thi chính sách truy cập của ứng dụng.

Đó là mô hình **pre-authentication (tiền xác thực)**. “JEE” là tên lịch sử của cơ chế tích hợp Java EE; trong Spring Boot 3/Spring Security 6 dùng namespace `jakarta.servlet.*` của Jakarta EE. Tên class của Spring Security vẫn là `J2eePreAuthenticatedProcessingFilter`.

Sau bài này, bạn cần giải thích và kiểm chứng được:

1. Ai thực sự xác thực: **Servlet Container**, qua realm/security domain và cơ chế đăng nhập mà nó cấu hình (BASIC, FORM hoặc cơ chế do container hỗ trợ).
2. Container cung cấp tên người dùng bằng `HttpServletRequest.getUserPrincipal()` và vai trò bằng `isUserInRole(String)`.
3. `J2eePreAuthenticatedProcessingFilter` lấy tên người dùng đã xác thực; `PreAuthenticatedAuthenticationProvider` hoàn thiện Spring `Authentication`, bao gồm authorities.
4. `J2eeBasedPreAuthenticatedWebAuthenticationDetailsSource` có thể chuyển container roles sang Spring `GrantedAuthority`, chẳng hạn `STAFF` → `ROLE_STAFF`.
5. Với request đã được container xác thực, `hasRole("ADMIN")` của Spring Security quyết định quyền truy cập nghiệp vụ. Một principal hợp lệ **không có nghĩa** được vào mọi endpoint.
6. Không có principal đáng tin cậy ở request đầu vào thì pre-auth **không tự tạo danh tính**. Test phải chứng minh trường hợp thiếu principal bị từ chối.

Ví dụ tập trung vào **Servlet stack**. Nó không cấu hình Spring WebFlux, không đọc Reactor Context và không dùng Spring Security form login để thay vai trò của container.

## 2. Ranh giới tin cậy: ai xác thực, ai phân quyền?

Có hai lớp khác nhau:

| Lớp | Trách nhiệm | Dấu hiệu/cơ chế |
| --- | --- | --- |
| Servlet Container | Xác thực credential (hoặc chấp nhận SSO theo cấu hình server), quản lý realm/security domain, gắn principal và JEE roles vào request | `request.getUserPrincipal()`; `request.isUserInRole("ADMIN")` |
| Spring Security | Tiếp nhận danh tính do container cung cấp, tạo `SecurityContext`/`Authentication`, ánh xạ roles và áp dụng `authenticated()`, `hasRole(...)`, method security nếu được bật | `J2eePreAuthenticatedProcessingFilter`, `PreAuthenticatedAuthenticationProvider`, `AuthorizationFilter` |

Luồng phổ biến:

```text
Browser / HTTP client
     |
     | 1. HTTP request + credential/SSO evidence
     v
Servlet Container (realm + login mechanism)
     | 2. xác thực thành công
     | 3. gắn Principal và danh sách role vào Servlet request
     v
Spring Security FilterChainProxy
     |
     | J2eePreAuthenticatedProcessingFilter
     |   -> request.getUserPrincipal().getName()
     |   -> PreAuthenticatedAuthenticationToken
     |   -> AuthenticationManager / PreAuthenticatedAuthenticationProvider
     |   -> lấy GrantedAuthority từ details hoặc UserDetailsService
     |   -> SecurityContextHolder
     v
AuthorizationFilter: authenticated(), hasRole("ADMIN"), ...
     |
     v
Controller / service
```

**Không nhầm lẫn:** `PreAuthenticatedAuthenticationProvider` không kiểm tra lại username/password. Nó tin giả định **nguồn danh tính bên ngoài đã xác thực**. Nếu container không thiết lập authentication đúng cách, hoặc một lớp proxy có thể bị client giả mạo mà ứng dụng vẫn tin, toàn bộ mô hình sụp đổ.

### API mà Servlet Container cung cấp

Trước khi lớp bảo mật của ứng dụng can thiệp, request thực sự được container bảo vệ có thể được quan sát như sau:

```java
import jakarta.servlet.http.HttpServletRequest;
import java.security.Principal;

Principal principal = request.getUserPrincipal();
String username = principal == null ? null : principal.getName();
boolean hasAdminRole = request.isUserInRole("ADMIN");
String authMechanism = request.getAuthType();
```

Đây là **đoạn minh họa bên trong mã đã có biến `request`**, không phải class độc lập. `getUserPrincipal()` có thể trả `null` nếu container chưa xác thực; `isUserInRole(...)` chỉ có ý nghĩa khi container đã thiết lập role mapping tương ứng. `getAuthType()` có thể trả `BASIC`/`FORM` hoặc tên cơ chế được container hỗ trợ và cũng có thể `null`, tùy server/cách đăng nhập.

**Lưu ý quan sát:** Sau khi request đi qua `SecurityContextHolderAwareRequestFilter`, Spring Security có thể *wrap* `HttpServletRequest` để các phương thức `getUserPrincipal()` / `isUserInRole()` phản ánh Spring `Authentication`. Vì vậy, gọi các phương thức đó **trong controller** không luôn là bằng chứng độc lập về dữ liệu gốc mà container đã cung cấp. Điểm tích hợp đúng cần kiểm tra là request trước filter pre-auth hoặc dấu vết từ chính container.

## 3. Các thành phần Spring Security JEE pre-auth

### 3.1. `J2eePreAuthenticatedProcessingFilter`

Filter này kế thừa `AbstractPreAuthenticatedProcessingFilter`. Nó lấy **tên principal** từ `HttpServletRequest.getUserPrincipal()`. Container authentication không có API chung để đưa mật khẩu gốc sang Spring; vì thế filter dùng giá trị credentials **giả/dummy**, không phải password do ứng dụng kiểm tra.

Khi có principal và Spring context chưa có authentication, filter tạo `PreAuthenticatedAuthenticationToken` rồi chuyển đến `AuthenticationManager`. Nếu chưa có principal, không có danh tính để tiền xác thực. Với cấu hình chỉ cho pre-auth, request tới endpoint bảo vệ cần bị từ chối.

### 3.2. `PreAuthenticatedAuthenticationProvider`

Provider chấp nhận `PreAuthenticatedAuthenticationToken` và gọi `AuthenticationUserDetailsService<PreAuthenticatedAuthenticationToken>` để lấy user/authorities. Hai hướng đi hợp lệ:

- **Dùng container roles:** `PreAuthenticatedGrantedAuthoritiesUserDetailsService` đọc danh sách `GrantedAuthority` từ `Authentication.getDetails()`; details **phải** triển khai `GrantedAuthoritiesContainer`.
- **Dùng vai trò nghiệp vụ trong ứng dụng:** `UserDetailsByNameServiceWrapper` tra cứu `UserDetailsService` bằng tên đã được container xác thực, lấy trạng thái tài khoản và quyền nội bộ. Bạn cần quản lý đồng bộ tên tài khoản / liên kết identity và ngăn xung đột mapping.

Provider không tự gửi lệnh xác thực sang LDAP/Tomcat realm; việc đó đã là trách nhiệm phía container. Không cấu hình `DaoAuthenticationProvider` để tái kiểm tra password giả của pre-auth token.

### 3.3. `J2eeBasedPreAuthenticatedWebAuthenticationDetailsSource`

Đây là cầu nối giữa JEE roles và Spring Security authorities:

1. Danh sách role **có thể ánh xạ** được xác định qua `MappableAttributesRetriever`, ví dụ `STAFF` và `ADMIN`.
2. Với mỗi tên role đó, details source gọi `request.isUserInRole(role)`. Chỉ role mà container khẳng định người dùng có quyền mới được giữ lại.
3. `Attributes2GrantedAuthoritiesMapper` chuyển tên role của container thành `GrantedAuthority`. Mapper đơn giản mặc định thêm prefix `ROLE_` nếu chưa có.
4. `PreAuthenticatedGrantedAuthoritiesUserDetailsService` nhận authorities từ details, tạo user details cho Spring Security.

Nếu container trả `isUserInRole("ADMIN") == true`, mặc định Spring nhận `ROLE_ADMIN`. Quy tắc `hasRole("ADMIN")` tương đương tìm `ROLE_ADMIN`; còn `hasAuthority("ROLE_ADMIN")` dùng tên authority đầy đủ. Không viết `hasRole("ROLE_ADMIN")` khi đang dùng prefix chuẩn.

**Điều kiện bắt buộc:** Tên role của container, cấu hình security-role/role mapping và danh sách mappable roles phải nhất quán. Chỉ đưa `ADMIN` vào danh sách mappable **không cấp** ADMIN cho ai; việc xác nhận role vẫn do container thực hiện qua `isUserInRole`.

## 4. Ví dụ hoàn chỉnh: Spring Boot 3, Java 17, Servlet Container pre-auth

Ví dụ có hai chế độ kiểm chứng:

- **MockMvc:** chạy test trong Spring Boot, mô phỏng các API container để kiểm tra filter, principal và role mapping. Đây là bài kiểm tra tích hợp Spring Security, chưa phải bài kiểm tra realm thực.
- **WAR trên container đã cấu hình bảo mật:** xác thực thật ở container, sau đó Spring thực hiện authorization. Khi chỉ chạy `bootRun` trên embedded Tomcat **chưa cấu hình realm + protection**, `getUserPrincipal()` thường là `null` và endpoint bảo vệ trả `403` theo cấu hình bên dưới. Điều đó là bình thường, không phải lỗi của Spring.

Tạo một dự án nhỏ gồm các file sau.

### 4.1. `build.gradle`

Ví dụ Gradle độc lập, dùng Spring Boot 3.3.5 (Java 17) và Spring Security 6.x do Spring Boot quản lý:

```groovy
plugins {
    id 'java'
    id 'war'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
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
    implementation 'org.springframework.boot:spring-boot-starter-security'

    // WAR triển khai được lên Servlet Container bên ngoài.
    providedRuntime 'org.springframework.boot:spring-boot-starter-tomcat'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Dùng **Spring MVC/Servlet**, không thêm `spring-boot-starter-webflux` cho ví dụ này. Nếu công ty sử dụng BOM/plugin Spring Boot khác, điều chỉnh phiên bản trong môi trường đó nhưng giữ nguyên nguyên lý container authentication.

### 4.2. Application và WAR initializer

File `src/main/java/com/example/jee/JeePreauthApplication.java`:

```java
package com.example.jee;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.boot.web.servlet.support.SpringBootServletInitializer;

@SpringBootApplication
public class JeePreauthApplication extends SpringBootServletInitializer {

    @Override
    protected SpringApplicationBuilder configure(
            SpringApplicationBuilder builder) {
        return builder.sources(JeePreauthApplication.class);
    }

    public static void main(String[] args) {
        SpringApplication.run(JeePreauthApplication.class, args);
    }
}
```

`SpringBootServletInitializer` cho phép deploy WAR lên container hỗ trợ Jakarta Servlet phù hợp (ví dụ Tomcat 10.1 cho ứng dụng Boot 3.3). Hàm `main` vẫn hỗ trợ phát triển/test với embedded Tomcat, nhưng embedded server không tự biết người dùng của realm nếu bạn không cấu hình nó.

### 4.3. Cấu hình Spring Security nhận principal/roles của container

File `src/main/java/com/example/jee/SecurityConfig.java`:

```java
package com.example.jee;

import java.util.Set;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.authority.mapping.SimpleMappableAttributesRetriever;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.Http403ForbiddenEntryPoint;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;
import org.springframework.security.web.authentication.preauth.PreAuthenticatedAuthenticationProvider;
import org.springframework.security.web.authentication.preauth.PreAuthenticatedGrantedAuthoritiesUserDetailsService;
import org.springframework.security.web.authentication.preauth.j2ee.J2eeBasedPreAuthenticatedWebAuthenticationDetailsSource;
import org.springframework.security.web.authentication.preauth.j2ee.J2eePreAuthenticatedProcessingFilter;
import org.springframework.security.web.context.NullSecurityContextRepository;

@Configuration
@EnableWebSecurity
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        // 1. Không xác thực lại password; dùng roles có trong pre-auth details.
        var userDetails = new PreAuthenticatedGrantedAuthoritiesUserDetailsService();
        var provider = new PreAuthenticatedAuthenticationProvider();
        provider.setPreAuthenticatedUserDetailsService(userDetails);
        var manager = new ProviderManager(provider);

        // 2. Danh sách các JEE role có thể ánh xạ.
        var roleNames = new SimpleMappableAttributesRetriever();
        roleNames.setMappableAttributes(Set.of("STAFF", "ADMIN"));

        var detailsSource =
                new J2eeBasedPreAuthenticatedWebAuthenticationDetailsSource();
        detailsSource.setMappableRolesRetriever(roleNames);
        // Mapper mặc định: STAFF -> ROLE_STAFF, ADMIN -> ROLE_ADMIN.

        // 3. Filter lấy tên do Servlet Container cung cấp.
        var preAuthFilter = new J2eePreAuthenticatedProcessingFilter();
        preAuthFilter.setAuthenticationManager(manager);
        preAuthFilter.setAuthenticationDetailsSource(detailsSource);

        // Mỗi HTTP request dựa vào container principal hiện tại.
        // Không dùng Spring HTTP session làm "nguồn nhận dạng" độc lập.
        preAuthFilter.setSecurityContextRepository(
                new NullSecurityContextRepository());

        return http
                .securityContext(context -> context.securityContextRepository(
                        new NullSecurityContextRepository()))
                .sessionManagement(session -> session.sessionCreationPolicy(
                        SessionCreationPolicy.STATELESS))
                .authorizeHttpRequests(authorize -> authorize
                        .requestMatchers("/api/admin").hasRole("ADMIN")
                        .requestMatchers("/api/whoami").authenticated()
                        .anyRequest().denyAll())
                // Pre-auth không có trang login của ứng dụng để chuyển hướng tới.
                .exceptionHandling(exceptions -> exceptions
                        .authenticationEntryPoint(
                                new Http403ForbiddenEntryPoint()))
                // Container có thể dùng BASIC/FORM; Spring không làm login lại.
                .formLogin(AbstractHttpConfigurer::disable)
                .httpBasic(AbstractHttpConfigurer::disable)
                .addFilterBefore(preAuthFilter,
                        UsernamePasswordAuthenticationFilter.class)
                .build();
    }
}
```

**Tại sao cấu hình vậy?**

- `J2eePreAuthenticatedProcessingFilter` lấy username từ **container-provided `getUserPrincipal()`**, không đọc các header do client gửi.
- `ProviderManager(provider)` chỉ chứa provider phục vụ pre-auth; provider sinh authorities từ details do `J2eeBasedPreAuthenticatedWebAuthenticationDetailsSource` tạo.
- `ROLE_` là prefix chuẩn khi đối chiếu `hasRole`. Ở code này danh sách có thể map gồm `STAFF`/`ADMIN`; Spring chỉ nhận role nếu `isUserInRole` của container trả true.
- `NullSecurityContextRepository` ở **cả filter và SecurityContext chain** tránh lưu Spring `Authentication` sang HTTP session rồi tái sử dụng principal cũ khi container identity đã đổi. Container vẫn có thể quản lý session riêng phục vụ cơ chế login của chính nó.
- `SessionCreationPolicy.STATELESS` ở **lớp Spring Security** không có nghĩa yêu cầu container phải stateless. Với container FORM login, cookie/JSESSIONID vẫn có thể dùng để container nhận diện phiên.
- Vì ứng dụng không tự khởi tạo login, `Http403ForbiddenEntryPoint` trả `403` khi Spring không có principal được chấp nhận; đây là response **từ Spring Security** trong thử nghiệm mô phỏng. Ở triển khai thật, container có thể chặn sớm và trả `401 + WWW-Authenticate` hoặc chuyển tới trang login theo `web.xml`, trước khi request tới filter.
- `.formLogin(...disable)` và `.httpBasic(...disable)` chỉ tắt **cơ chế login của Spring Security**; chúng không vô hiệu hóa BASIC/FORM do Servlet Container đã được cấu hình.
- `.addFilterBefore(..., UsernamePasswordAuthenticationFilter.class)` đưa pre-auth filter vào Spring Security filter chain trước vị trí login form, sau các filter chuẩn phụ trách chuẩn bị Security Context.

Đừng đăng ký chính `preAuthFilter` thành một Servlet `Filter` toàn cục khác ngoài chain nếu không cần: chạy filter hai lần ở hai thứ tự khác nhau sẽ làm kết quả khó đoán. Trong ví dụ, filter được tạo bên trong cấu hình chain, tránh Boot tự đăng ký nó thành container filter bean độc lập.

### 4.4. Endpoint cần nhận dạng và phân quyền

File `src/main/java/com/example/jee/ApiController.java`:

```java
package com.example.jee;

import java.util.Map;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ApiController {

    @GetMapping("/api/whoami")
    public Map<String, Object> whoAmI() {
        Authentication authentication =
                SecurityContextHolder.getContext().getAuthentication();

        return Map.of(
                "name", authentication.getName(),
                "authorities", authentication.getAuthorities().stream()
                        .map(GrantedAuthority::getAuthority)
                        .sorted()
                        .toList());
    }

    @GetMapping("/api/admin")
    public String adminOnly() {
        return "admin-ok";
    }
}
```

Trong `/api/whoami`, Spring Security đã kiểm tra `authenticated()` trước khi handler chạy. `SecurityContextHolder` thuộc Servlet filter thread context cho request hiện tại. Response cho user `alice` có role `STAFF` dự kiến:

```json
{
  "name": "alice",
  "authorities": ["ROLE_STAFF"]
}
```

Endpoint `/api/admin` yêu cầu `ROLE_ADMIN`. Người dùng đã đăng nhập ở container nhưng chỉ có role `STAFF` phải nhận `403`.

## 5. Cấu hình bảo vệ ở **Servlet Container** (WAR thật)

Code Spring ở trên **không có nhiệm vụ tạo realm hoặc xác thực credential**. Với WAR triển khai lên server ngoài, bạn phải có bảo mật container thật.

Ví dụ mô tả khai báo `src/main/webapp/WEB-INF/web.xml` dành cho container Jakarta Servlet 6.0:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<web-app xmlns="https://jakarta.ee/xml/ns/jakartaee"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="https://jakarta.ee/xml/ns/jakartaee
                             https://jakarta.ee/xml/ns/jakartaee/web-app_6_0.xsd"
         version="6.0">
    <security-constraint>
        <web-resource-collection>
            <web-resource-name>Secured API</web-resource-name>
            <url-pattern>/api/*</url-pattern>
        </web-resource-collection>
        <auth-constraint>
            <role-name>STAFF</role-name>
            <role-name>ADMIN</role-name>
        </auth-constraint>
    </security-constraint>

    <login-config>
        <auth-method>BASIC</auth-method>
        <realm-name>DemoRealm</realm-name>
    </login-config>

    <security-role>
        <role-name>STAFF</role-name>
    </security-role>
    <security-role>
        <role-name>ADMIN</role-name>
    </security-role>
</web-app>
```

Ý nghĩa:

- `/api/*` phải vượt qua kiểm tra container, có một trong hai role `STAFF`/`ADMIN` trước khi request tới ứng dụng.
- `<login-config>` chọn HTTP BASIC **do container** thực hiện; phải có **realm thực sự được container cấu hình** cho `DemoRealm`/ứng dụng và ánh xạ user → role. Chỉ khai báo `web.xml`, không định nghĩa realm/user store, **không đủ** để đăng nhập.
- `<security-role>` khai báo tên vai trò, **không tự cấp role** cho user.
- `isUserInRole("ADMIN")` sẽ chỉ đúng nếu container đã ánh xạ role đó; xem tài liệu của server khi các group trong LDAP/AD phải map sang JEE roles.
- Với phiên bản Servlet khác, cấu trúc schema và cách đóng gói có thể khác; ví dụ trên nhằm minh họa mô hình chuẩn ở Jakarta Servlet 6.0, không phải cấu hình realm dành cho mọi server.

Khi xây dựng: `./gradlew clean bootWar` (Windows: `gradlew.bat clean bootWar`). Triển khai file WAR tạo trong `build/libs/` vào container tương thích. Nếu WAR tên là `jee-preauth-0.0.1-SNAPSHOT.war`, URL triển khai thường có context path tương ứng, ví dụ `https://host/jee-preauth-0.0.1-SNAPSHOT/api/whoami`; tên context thực tế do cách deploy/container quyết định. Dùng HTTPS vì BASIC gửi thông tin đăng nhập được mã hóa Base64, không phải được mã hóa bảo mật.

**Quan trọng:** nếu bạn chỉ chạy `./gradlew bootRun` với Tomcat nhúng chưa khai báo container authentication, endpoint sẽ trả `403`; không bật Spring form login để “chữa” triệu chứng này. Cần cung cấp container realm hợp lệ hoặc chạy MockMvc test ở mục tiếp theo.

## 6. Kiểm thử tự động: mô phỏng principal/roles của container

Bài kiểm thử dưới đây kiểm chứng Spring tiếp nhận danh tính và ánh xạ role. Nó cố tình **không dùng `SecurityMockMvcRequestPostProcessors.user("alice")`**, vì công cụ đó tạo authentication ở Spring Security và có thể làm test pass dù `J2eePreAuthenticatedProcessingFilter` không hoạt động.

Ở lớp MockMvc, đặt trực tiếp principal và user roles vào **MockHttpServletRequest**, tương đương dữ liệu mà container phải cung cấp khi triển khai thật.

File `src/test/java/com/example/jee/JeePreauthTest.java`:

```java
package com.example.jee;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class JeePreauthTest {

    @Autowired
    MockMvc mvc;

    @Test
    void staffPrincipalFromContainerCanReadIdentity() throws Exception {
        mvc.perform(get("/api/whoami").with(request -> {
                    request.setUserPrincipal(() -> "alice");
                    request.addUserRole("STAFF");
                    return request;
                }))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.name").value("alice"))
                .andExpect(jsonPath("$.authorities[0]")
                        .value("ROLE_STAFF"));
    }

    @Test
    void staffCannotEnterAdminEndpoint() throws Exception {
        mvc.perform(get("/api/admin").with(request -> {
                    request.setUserPrincipal(() -> "alice");
                    request.addUserRole("STAFF");
                    return request;
                }))
                .andExpect(status().isForbidden());
    }

    @Test
    void adminRoleFromContainerIsMappedToSpringRole() throws Exception {
        mvc.perform(get("/api/admin").with(request -> {
                    request.setUserPrincipal(() -> "bob");
                    request.addUserRole("ADMIN");
                    return request;
                }))
                .andExpect(status().isOk())
                .andExpect(content().string("admin-ok"));
    }

    @Test
    void missingContainerPrincipalCannotBecomeAuthenticated()
            throws Exception {
        mvc.perform(get("/api/whoami"))
                .andExpect(status().isForbidden());
    }
}
```

Chạy:

```bash
./gradlew test --tests com.example.jee.JeePreauthTest
```

Windows:

```powershell
gradlew.bat test --tests com.example.jee.JeePreauthTest
```

Khi cấu hình hoạt động đúng, kỳ vọng **4 test pass**: container principal `alice` được phản ánh vào Spring, `STAFF` không được quyền admin, `ADMIN` được quyền admin, request thiếu container principal bị từ chối. Những HTTP status này là kết quả **MockMvc + Spring Security chain**, không mô tả mọi status có thể xảy ra khi container thực từ chối credential trước bước Spring.

**Giới hạn của phép thử:** `MockHttpServletRequest.setUserPrincipal(...)` và `addUserRole(...)` chỉ giả lập lớp container. Chúng không chứng minh Tomcat/Jetty/application server đã cấu hình realm, constraint, identity propagation, role mapping, TLS hay session đúng. Sau khi test pass, vẫn phải chạy **integration test qua WAR được triển khai lên chính container dùng trong production**.

## 7. Kiểm chứng đầu-cuối trên Servlet Container thật

Triển khai WAR, xác định chính xác context path và realm, sau đó dùng một client HTTP. Ví dụ sau dùng BASIC do **container** xử lý, không phải Spring Basic:

```bash
# Chưa đăng nhập: container thường trả 401 và WWW-Authenticate
curl -i https://localhost:8443/jee-preauth/api/whoami

# User trong realm đã có STAFF
curl -i -u alice:example-password \
  https://localhost:8443/jee-preauth/api/whoami

# STAFF đã đăng nhập nhưng không có ADMIN
curl -i -u alice:example-password \
  https://localhost:8443/jee-preauth/api/admin

# User đã được container cấp ADMIN
curl -i -u bob:example-password \
  https://localhost:8443/jee-preauth/api/admin
```

Các URL, account và password là **dữ liệu minh họa**, không phải endpoint hay credential đang tồn tại. Không dùng mật khẩu thật trong shell history trên máy dùng chung; khi cần, dùng cơ chế nhập mật khẩu tương tác hoặc secret store an toàn của hệ thống.

| Tình huống | Container | Spring Security | Kết quả mong đợi |
| --- | --- | --- | --- |
| Không có credentials cho endpoint protected | Chặn/trả challenge, thường 401 (BASIC) | Có thể không nhận request | Không lộ dữ liệu |
| Alice đã được container xác thực, có STAFF | `principal=alice`, `isUserInRole("STAFF")=true` | Ánh xạ `ROLE_STAFF`; `authenticated()` pass | `/api/whoami` trả 200, name=alice |
| Alice có STAFF nhưng không ADMIN | Xác thực thành công | `hasRole("ADMIN")` không pass | `/api/admin` trả 403 |
| Bob có ADMIN | Xác thực thành công, ADMIN true | `ROLE_ADMIN` được cấp | `/api/admin` trả 200 |
| Không có principal do container cung cấp nhưng request đến Spring | Không xác thực | Pre-auth không tạo user; `Http403ForbiddenEntryPoint` | 403 trong cấu hình mẫu |

Đọc logs của container và Spring riêng để xác định tầng nào đã chặn request. Một HTTP 401 ở container **không** nhất thiết là lỗi trong `PreAuthenticatedAuthenticationProvider`; một HTTP 403 từ Spring sau khi xác thực có thể là lỗi mapping roles hoặc phân quyền.

## 8. Hai cách cấp authorities và lúc nào nên dùng

### A. Tin JEE roles của container (ví dụ ở mục 4)

- Container đã quản lý danh sách user và role đúng, ví dụ một realm kết nối LDAP/AD và map group → `STAFF`/`ADMIN`.
- Dùng `J2eeBasedPreAuthenticatedWebAuthenticationDetailsSource`, `PreAuthenticatedGrantedAuthoritiesUserDetailsService`.
- Ít phải truy vấn lại kho user trong ứng dụng.
- Thay đổi role cần được container cập nhật/áp dụng đúng theo vòng đời phiên, cache và cấu hình server.

### B. Nhận **danh tính** từ container, nhưng lấy **quyền nghiệp vụ** từ ứng dụng

Ví dụ ứng dụng có database lưu account status, tenant, phòng ban và quyền riêng. Có thể thay `PreAuthenticatedGrantedAuthoritiesUserDetailsService` bằng `UserDetailsByNameServiceWrapper<PreAuthenticatedAuthenticationToken>`:

```java
UserDetailsByNameServiceWrapper<PreAuthenticatedAuthenticationToken> wrapper =
        new UserDetailsByNameServiceWrapper<>();

wrapper.setUserDetailsService(applicationUserDetailsService);
provider.setPreAuthenticatedUserDetailsService(wrapper);
```

Đây là đoạn thay thế bên trong đoạn cấu hình đã có `provider` và `applicationUserDetailsService`, cần import `UserDetailsByNameServiceWrapper` và `PreAuthenticatedAuthenticationToken`; **không phải một chương trình Java độc lập**. `applicationUserDetailsService` thực hiện `loadUserByUsername(name)` để lấy quyền nội bộ. Với cách này, thông tin `isUserInRole` do container cung cấp **không tự** thành quyền ứng dụng; bạn phải quyết định khi nào tin vai trò container, khi nào dùng nguồn quyền nội bộ và cách hòa giải.

**Yêu cầu bảo mật:** khóa định danh ứng dụng phải ánh xạ ổn định với identity do container xác thực. Không nên lấy riêng local-part của email, tự bỏ domain/realm hoặc so khớp username không phân biệt namespace khi có thể trùng giữa các tổ chức.

## 9. Những lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra |
| --- | --- | --- |
| `getUserPrincipal() == null` | Container chưa bật security constraint/realm, hoặc đang chạy embedded Tomcat không thiết lập container auth | Kiểm tra cấu hình container, `web.xml`, đường dẫn được bảo vệ và login mechanism |
| Login thành công ở container nhưng Spring vẫn 403 ở `hasRole("ADMIN")` | Container role không có, sai case, `isUserInRole` false hoặc mappable roles không khớp | Đo role tại ranh giới container, so sánh `ADMIN`, `ROLE_ADMIN`, `hasRole` |
| Có principal nhưng authority rỗng | Quên details source, role mapping, hoặc dùng `PreAuthenticatedGrantedAuthoritiesUserDetailsService` với details không triển khai `GrantedAuthoritiesContainer` | Kiểm tra `setAuthenticationDetailsSource`, `setMappableRolesRetriever`, mapping |
| Spring authentication có `ROLE_ADMIN` dù user không có ADMIN | Container role mapping hoặc nguồn quyền nghiệp vụ cấu hình quá rộng | Kiểm tra nguồn cấp role; chỉ ánh xạ roles mà container xác nhận |
| Nhận 401 trước khi vào controller | Servlet Container đã chặn bởi authentication challenge | Kiểm tra access log/container realm trước khi debug Spring Security |
| Đăng nhập lại bất ngờ sau một request | Container session cookie/SSO ticket không được gửi tiếp, hết hạn hoặc cấu hình route sai | Xem cookie/JSESSIONID, domain, SameSite, proxy, cấu hình session store |
| `ClassNotFoundException: javax.servlet...` khi dùng Boot 3 | Dùng thư viện/container thời Java EE `javax.servlet` | Boot 3 cần Jakarta Servlet `jakarta.servlet`, dùng Tomcat 10.1 hoặc server tương thích |
| Request có user giả từ header lạ | Ứng dụng tự tin vào `X-User` hoặc header khác từ internet | Dùng API principal đáng tin từ container; chặn spoofing tại edge, không chấp nhận header tùy tiện |
| Bài test pass dù không có container auth | Test dùng `user()` / `@WithMockUser` tạo principal trực tiếp trong Spring | Test riêng `setUserPrincipal`/`addUserRole` và một vòng end-to-end qua container thật |
| User A đổi sang B nhưng vẫn thấy quyền A | Spring session giữ `Authentication` cũ hoặc các lớp cache không đồng bộ | Xem cấu hình lưu SecurityContext, principal-change handling, logout và session invalidation |

### Một số điểm vận hành cần thống nhất

- **Ranh giới tin cậy:** chỉ container/identity layer được cấu hình bảo mật mới được khẳng định principal. Không dùng `request.getHeader("X-User")` như một thay thế cho `getUserPrincipal()` trừ khi có gateway đáng tin, mTLS/đường mạng riêng và lớp xác minh/chống spoofing phù hợp.
- **Đăng nhập và logout:** Spring Security pre-auth không tự định nghĩa login/logout của container. Nếu container xử lý BASIC hoặc FORM, cơ chế bắt đầu/kết thúc phiên phụ thuộc container/SSO; chỉ gọi Spring logout có thể chưa hủy danh tính bên ngoài.
- **Quyền và roles:** xác thực người dùng không cấp mặc định `ROLE_ADMIN`. Mô hình JEE roles và Spring roles có thể độc lập; định nghĩa rõ nguồn quyền ưu tiên, mapping và refresh.
- **Session/identity change:** ứng dụng phải tránh giữ authentication cũ khi container principal thay đổi hoặc bị thu hồi. Ví dụ đặt context repository không lưu Spring session để tái đọc identity ở mỗi request; nếu dùng session persistence, cân nhắc `setCheckForPrincipalChanges(true)` và chính sách invalidation.
- **Bảo vệ request:** tiếp tục dùng HTTPS, kiểm soát CORS, CSRF theo loại client/credential, HTTP security headers và authorization trên endpoint. Pre-auth không thay thế các lớp bảo vệ đó.
- **Không đoán từ response:** một 401, 403 hay redirect cần được gắn với lớp tạo ra response: container realm, gateway, filter pre-auth, entry point hay authorization rule.

## 10. Checklist tự đánh giá

Một triển khai JEE pre-auth được xem là đúng với yêu cầu khi có bằng chứng cho đủ chuỗi:

1. Servlet Container xác thực user thật và cung cấp principal qua `getUserPrincipal()`; client không thể tự chọn principal bằng header giả.
2. `isUserInRole` phản ánh role container đã cấp, có mapping rõ ràng về tên và phạm vi.
3. `J2eePreAuthenticatedProcessingFilter` chuyển tên đã xác thực sang Spring `PreAuthenticatedAuthenticationToken`; provider hoàn thiện authorities.
4. Spring Security endpoint thể hiện đúng `authenticated()` và `hasRole(...)`: user STAFF đọc được danh tính, không vào admin; user ADMIN vào được admin.
5. Request không có container principal vẫn bị chặn. Bài test không dùng `mockUser()` để che giấu lỗi tích hợp.
6. Với triển khai WAR thực, đã xác minh riêng realm, session/SSO, container challenge và role mapping; test MockMvc chỉ xác nhận phần Spring.

### Tài liệu đối chiếu

- [Spring Security Reference – Pre-Authentication Scenarios](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/preauth.html)
- [Spring Security API – J2eePreAuthenticatedProcessingFilter](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/preauth/j2ee/J2eePreAuthenticatedProcessingFilter.html)
- [Spring Security API – J2eeBasedPreAuthenticatedWebAuthenticationDetailsSource](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/preauth/j2ee/J2eeBasedPreAuthenticatedWebAuthenticationDetailsSource.html)
- [Spring Security API – PreAuthenticatedAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/preauth/PreAuthenticatedAuthenticationProvider.html)
- [Spring Security API – PreAuthenticatedGrantedAuthoritiesUserDetailsService](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/preauth/PreAuthenticatedGrantedAuthoritiesUserDetailsService.html)
- [Spring Security API – SimpleAttributes2GrantedAuthoritiesMapper](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/authority/mapping/SimpleAttributes2GrantedAuthoritiesMapper.html)
