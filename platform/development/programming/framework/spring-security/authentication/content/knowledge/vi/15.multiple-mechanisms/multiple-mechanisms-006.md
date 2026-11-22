# Đa tổ chức và lựa chọn kho danh tính từ dữ liệu đã được kiểm soát

> **Bối cảnh:** Nhiều cơ chế xác thực trong Spring Security Authentication, nhánh **Servlet**. Bài học tập trung vào ứng dụng nhiều tổ chức (*multi-tenant/multi-organization*) cần chọn đúng kho danh tính, `AuthenticationManager` hoặc nhà cung cấp danh tính. Ví dụ chạy bằng **Java 17+, Spring Boot 3.3.5, Spring Security 6.x**. Quy tắc bao trùm: **dữ liệu do client gửi có thể đề xuất đích đăng nhập, nhưng nguồn cấu hình do server quản lý phải xác định kho nào được phép sử dụng; kết quả xác thực phải ràng buộc đúng tổ chức.**

## 1. Bài toán: cùng username nhưng thuộc hai tổ chức

Giả sử hệ thống quản lý hai tổ chức độc lập:

- **north** có một tài khoản `sam`, mật khẩu demo `north-pass123`, quyền `ROLE_ANALYST`.
- **south** cũng có tài khoản `sam` nhưng mật khẩu demo `south-pass456`, quyền `ROLE_VIEWER`.

Cùng chuỗi username **không có nghĩa là cùng principal trên toàn hệ thống**. Danh tính thực tế là cặp logic **`(tenantId, userId)`**, ví dụ `(north, sam)` và `(south, sam)`. Hai tài khoản có thể có password, trạng thái, roles, IdP và chính sách MFA khác nhau.

Khi client gọi:

```http
GET /tenants/north/me HTTP/1.1
Authorization: Basic c2FtOm5vcnRoLXBhc3MxMjM=
```

server phải chứng minh credential thuộc kho **north**, không tìm username trên mọi kho rồi chọn kết quả đầu tiên. Nếu client đổi URL thành `/tenants/south/me` nhưng vẫn mang password của **north**, request phải bị từ chối.

**Điểm tinh tế:** chuỗi `north` nằm trong path vẫn là **dữ liệu client điều khiển**. Ta không được tin rằng chỉ vì client tự chọn URL `north` thì client là thành viên north. Tuy nhiên, path đó có thể là *khóa định tuyến ứng viên* khi server kiểm tra nó qua **danh sách tenant đã đăng ký**, chọn đúng manager độc lập, rồi **xác thực credential ngay trong kho đã chọn**. Việc chọn kho và chứng minh danh tính là hai bước khác nhau.

### Các dữ liệu nào được tin?

| Thông tin | Có thể do client điều khiển? | Cách sử dụng an toàn |
| --- | --- | --- |
| `/tenants/north/...` | Có | Chỉ dùng làm tên ứng viên để đối chiếu registry/route đã được server cho phép |
| `X-Tenant: south` | Có | Không tự động chọn DataSource/manager từ header; cần chính sách xác minh rõ ràng |
| Username `sam` | Có | Chỉ là khóa tra cứu bên trong kho đã chọn; chưa phải danh tính đã xác thực |
| Password, API key, Bearer token | Có | Bằng chứng phải kiểm tra bằng provider/decoder tương ứng |
| `role=ADMIN`, `authenticated=true` | Có | **Không cấp quyền hoặc trạng thái đã xác thực** từ các giá trị này |
| `tenantId -> AuthenticationManager` | Do server provision | Registry được kiểm soát; chỉ map tới manager/IdP đã cấu hình |
| `userId -> authorities` của tenant | Nguồn danh tính tin cậy sau kiểm tra | Áp dụng quyền **trong phạm vi tenant** |
| JWT `iss` trước khi verify chữ ký | Có thể bị giả mạo | Chỉ dùng như khóa tìm **issuer đã allowlist**; phải verify token trước khi tin claims |

Không nhận JDBC URL, hostname IdP, JWK URL, schema database hoặc chuỗi kết nối trực tiếp từ request để tạo kho xác thực. Làm như vậy có thể dẫn đến chọn sai tenant, SSRF, truy cập database tùy ý hoặc leo thang đặc quyền.

## 2. Tách rõ ba câu hỏi: định tuyến, xác thực, phân quyền

1. **Định tuyến tenant:** Request đang nhắm tới namespace/tổ chức nào, và server có cho phép namespace đó không?
2. **Xác thực:** Credential của request có đúng **theo kho danh tính của tenant đã chọn** không? Danh tính đã xác minh là ai?
3. **Phân quyền:** Danh tính đó có quyền thực hiện thao tác cụ thể trên **tài nguyên thuộc cùng tenant** không?

Không gộp ba câu trên thành một lệnh `if` đọc `tenantId`, `role` và `password` từ JSON rồi trả HTTP 200.

Ví dụ mô hình tổng quát:

```text
Request client
  | path/host/issuer hint (chưa đáng tin)
  | credential (chưa xác thực)
  v
Canonical route + server-owned Tenant Registry
  | kiểm tra slug có đăng ký/ACTIVE không
  | map slug -> manager/issuer/store đã provision
  | unknown tenant -> reject, không fallback sang global store
  v
Authentication mechanism được chỉ định
  | HTTP Basic / session login / Bearer / API key ...
  v
AuthenticationManager dành riêng cho tenant
  | ProviderManager -> AuthenticationProvider phù hợp
  | -> UserDetailsService, password hash / decoder / IdP của tenant
  | -> kiểm tra credential, account flags, issuer, audience...
  v
Authentication được xác minh
  | principal được gắn tenant đã kiểm chứng
  | authorities do nguồn phía server cấp, không từ request
  v
SecurityContextHolder
  v
Authorization + resource ownership checks
  | đủ quyền và đúng tenant -> 200
  | thiếu/sai credential -> 401
  | đã xác thực nhưng thiếu quyền -> 403
  | cross-tenant resource -> từ chối
```

Trong Spring Security Servlet, `FilterChainProxy` chọn **`SecurityFilterChain` đầu tiên phù hợp** dựa trên request matcher và thứ tự `@Order`. Cơ chế xác thực trong chain (ví dụ `BasicAuthenticationFilter`) gọi `AuthenticationManager`; provider kiểm tra credential và trả `Authentication` đã xác thực; kết quả được đặt trong `SecurityContext` để các rule phân quyền phía sau xử lý.

Khi chỉ có vài namespace tĩnh, nhiều `SecurityFilterChain` với các `securityMatcher` cụ thể thường đơn giản và dễ kiểm toán. Khi tenant thay đổi động, cần một **registry đã provision** và một cơ chế resolver được thiết kế chặt chẽ hơn. Dù dùng cách nào, tenant selector ban đầu vẫn không được coi là bằng chứng đăng nhập.

### Bất biến an toàn

- **Chọn đúng kho trước khi so password**; không lấy mọi tenant rồi thử cùng credential cho đến khi thành công.
- **Một tenant không có quyền dùng manager của tenant khác** chỉ vì username trùng nhau.
- **Tài khoản được xác minh phải ràng buộc với tenant đích**; một user đã login vào north không tự có quyền với south.
- **Quyền được tính theo tenant**: `ROLE_ANALYST` tại north không đương nhiên là `ROLE_ANALYST` tại south.
- **Tenant không tồn tại hoặc đã vô hiệu hóa phải fail closed**; không có "mặc định dùng public/global manager" làm đường vòng.
- **Dữ liệu kinh doanh phải lọc tenant ở tầng truy cập dữ liệu**; thành công ở authentication không tự động bảo vệ mọi truy vấn repository.

## 3. Ví dụ Spring Boot chạy được với hai kho danh tính độc lập

Ta xây dựng hai kho `InMemoryUserDetailsManager` để quan sát rõ isolation. Mỗi kho có cùng username `sam` nhưng password và role khác nhau. Hai `DaoAuthenticationProvider` được tạo riêng; mỗi provider kiểm tra mật khẩu bằng `BCryptPasswordEncoder` và đọc đúng kho.

**Chọn tenant qua cấu hình server:** Registry ánh xạ cố định `north -> northManager` và `south -> southManager`. Hai `SecurityFilterChain` dùng các đường dẫn đã được server đăng ký; client có thể chọn URL nhưng không thể tự thêm manager thứ ba hoặc tự cấp quyền. Endpoint không đọc `X-Tenant`, `X-Role` hay `X-Authenticated`.

### 3.1. Cấu trúc

```text
tenant-auth-demo/
├── pom.xml
├── src/main/java/com/example/tenants/TenantAuthApplication.java
└── src/test/java/com/example/tenants/TenantAuthApplicationTests.java
```

**`pom.xml`**:

```xml
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
    <artifactId>tenant-auth-demo</artifactId>
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

**`src/main/java/com/example/tenants/TenantAuthApplication.java`**:

```java
package com.example.tenants;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.Map;

@SpringBootApplication
public class TenantAuthApplication {

    public static void main(String[] args) {
        SpringApplication.run(TenantAuthApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean("northUsers")
    UserDetailsService northUsers(PasswordEncoder encoder) {
        UserDetails sam = User.withUsername("sam")
                .password(encoder.encode("north-pass123"))
                .roles("ANALYST")
                .build();
        return new InMemoryUserDetailsManager(sam);
    }

    @Bean("southUsers")
    UserDetailsService southUsers(PasswordEncoder encoder) {
        UserDetails sam = User.withUsername("sam")
                .password(encoder.encode("south-pass456"))
                .roles("VIEWER")
                .build();
        return new InMemoryUserDetailsManager(sam);
    }

    // Chỉ code/configuration tin cậy có quyền provision registry này.
    @Bean
    TenantAuthRegistry tenantAuthRegistry(
            @Qualifier("northUsers") UserDetailsService north,
            @Qualifier("southUsers") UserDetailsService south,
            PasswordEncoder encoder) {

        return new TenantAuthRegistry(Map.of(
                "north", managerFor(north, encoder),
                "south", managerFor(south, encoder)
        ));
    }

    private static AuthenticationManager managerFor(
            UserDetailsService users, PasswordEncoder encoder) {
        DaoAuthenticationProvider provider = new DaoAuthenticationProvider();
        provider.setUserDetailsService(users);
        provider.setPasswordEncoder(encoder);
        return new ProviderManager(List.of(provider));
    }

    static final class TenantAuthRegistry {
        private final Map<String, AuthenticationManager> managers;

        TenantAuthRegistry(Map<String, AuthenticationManager> managers) {
            this.managers = Map.copyOf(managers);
        }

        AuthenticationManager requireRegistered(String tenant) {
            AuthenticationManager manager = managers.get(tenant);
            if (manager == null) {
                throw new IllegalArgumentException("Unregistered tenant");
            }
            return manager;
        }
    }

    // Các route được định nghĩa bởi server; không dùng JDBC URL từ client.
    @Bean
    @Order(1)
    SecurityFilterChain northChain(
            HttpSecurity http, TenantAuthRegistry registry) throws Exception {
        return tenantChain(http, "north", registry.requireRegistered("north"));
    }

    @Bean
    @Order(2)
    SecurityFilterChain southChain(
            HttpSecurity http, TenantAuthRegistry registry) throws Exception {
        return tenantChain(http, "south", registry.requireRegistered("south"));
    }

    private static SecurityFilterChain tenantChain(
            HttpSecurity http, String tenant, AuthenticationManager manager)
            throws Exception {

        String base = "/tenants/" + tenant;
        http
            .securityMatcher(base + "/**")
            .authenticationManager(manager)
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(base + "/reports").hasRole("ANALYST")
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            );

        return http.build();
    }

    // Các path không thuộc hai namespace đã provision phải bị từ chối.
    @Bean
    @Order(3)
    SecurityFilterChain denyOtherPaths(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth.anyRequest().denyAll())
            .httpBasic(AbstractHttpConfigurer::disable)
            .formLogin(AbstractHttpConfigurer::disable);
        return http.build();
    }

    @RestController
    static class TenantController {
        record Profile(String tenant, String username, List<String> authorities) {}

        @GetMapping("/tenants/{tenant}/me")
        Profile me(@PathVariable String tenant, Authentication authentication) {
            List<String> authorities = authentication.getAuthorities().stream()
                    .map(GrantedAuthority::getAuthority)
                    .sorted()
                    .toList();
            return new Profile(tenant, authentication.getName(), authorities);
        }

        @GetMapping("/tenants/{tenant}/reports")
        String reports(@PathVariable String tenant) {
            return "reports:" + tenant;
        }
    }
}
```

### 3.2. Giải thích đúng các lớp trong code

1. `northUsers` và `southUsers` là **hai kho user độc lập**, dù cùng username `sam`. Mỗi bên chứa BCrypt hash và role riêng. Đây là bản demo; kho thật có thể là database/schema/LDAP/IdP khác nhau.
2. `TenantAuthRegistry` được tạo từ `Map.of(...)` **phía server**, chỉ chứa hai manager đã provision. `Map.copyOf` chống sửa map từ bên ngoài. Request không thể tự cung cấp tên manager, địa chỉ DB hoặc nguồn JDBC.
3. `managerFor(...)` tạo `DaoAuthenticationProvider` với đúng `UserDetailsService` của tenant. `ProviderManager` gọi provider đó cho `UsernamePasswordAuthenticationToken` đến từ Basic filter.
4. `northChain` với `securityMatcher("/tenants/north/**")` được chọn trước nếu path phù hợp; nó dùng **north manager** được lấy từ registry. Tương tự south. Hai chain được kiểm soát qua `@Order(1)` và `@Order(2)`.
5. `HttpSecurity.authenticationManager(manager)` cấu hình manager **của riêng chain**. `httpBasic()` dùng nó khi `BasicAuthenticationFilter` nhận header Basic.
6. `hasRole("ANALYST")` đối chiếu authority `ROLE_ANALYST` do kho server cấp. North user được vào `/tenants/north/reports`; South user chỉ có `ROLE_VIEWER` nên khi đã xác thực vẫn bị từ chối.
7. `SessionCreationPolicy.STATELESS` khiến demo không lưu login trong session. Basic credential phải được gửi lại trên mỗi request. Các route demo chỉ dùng GET; nếu thêm thao tác thay đổi dữ liệu qua trình duyệt cần đánh giá CSRF và cơ chế tự gửi credential.
8. Chain cuối dùng `denyAll` để đóng đường truy cập không được đăng ký, thay vì fallback về một kho user toàn cục. Trả mã 4xx cho tenant không tồn tại; mã cụ thể phụ thuộc entry point/exception handling của chain này.

**Đảm bảo đúng namespace:** Controller nhận `tenant` từ path, nhưng chỉ được chạy sau khi một chain dành cho tenant đó đã xác thực thành công. Vì `securityMatcher` của hai chain gắn chặt vào path tương ứng, một cookie/header `X-Tenant` tự khai sẽ không đổi manager. Đây vẫn chỉ là **bảo vệ lớp HTTP**; với API đọc dữ liệu thật còn cần ràng buộc tenant ở query/service như mục 6.

## 4. Chạy và xác minh isolation giữa các tenant

Chạy trong thư mục có `pom.xml`:

```bash
mvn spring-boot:run
```

Thử các trường hợp sau bằng `curl`. Chuỗi password trong đây chỉ phục vụ ví dụ local; hãy dùng HTTPS cho credential thật.

```bash
# 1. North: đúng password của north -> 200.
curl -i -u sam:north-pass123 http://localhost:8080/tenants/north/me

# 2. South: đúng password của south -> 200.
curl -i -u sam:south-pass456 http://localhost:8080/tenants/south/me

# 3. Đem credential north sang south -> 401.
curl -i -u sam:north-pass123 http://localhost:8080/tenants/south/me

# 4. Đem credential south sang north -> 401.
curl -i -u sam:south-pass456 http://localhost:8080/tenants/north/me

# 5. Giả mạo header tenant và role không thể nâng quyền ở south -> 403.
curl -i -u sam:south-pass456 \
    -H 'X-Tenant: north' \
    -H 'X-Role: ROLE_ANALYST' \
    http://localhost:8080/tenants/south/reports

# 6. North có ROLE_ANALYST -> được xem report north (200).
curl -i -u sam:north-pass123 http://localhost:8080/tenants/north/reports

# 7. Tenant lạ không có manager được provision -> bị từ chối (4xx).
curl -i -u sam:north-pass123 http://localhost:8080/tenants/unknown/me
```

Ví dụ JSON cho các phản hồi thành công:

```json
{"tenant":"north","username":"sam","authorities":["ROLE_ANALYST"]}
```

```json
{"tenant":"south","username":"sam","authorities":["ROLE_VIEWER"]}
```

Controller trả response JSON với thứ tự field theo record. Phản hồi 401 có thể kèm `WWW-Authenticate: Basic ...`; body lỗi tùy server. Nếu lỗi 403, nó không có nghĩa password sai: người dùng đã được xác thực trong tenant tương ứng nhưng thiếu quyền cho endpoint. `curl` với `-i` hiển thị status và headers để đối chiếu.

### Tại sao kịch bản (3) và (4) quan trọng?

Chúng chứng minh **không chỉ username** được dùng để chọn user toàn cục. Nếu ứng dụng dùng một `UserDetailsService` chung rồi tìm `sam` ở bất kỳ tenant nào, request (3) có thể vô tình thành công bằng credential của tenant khác. Trong ví dụ, manager của south chỉ nhìn thấy hash của south; password north không khớp. Một người là thành viên của cả hai tenant phải xác minh **đúng ngữ cảnh tenant đang truy cập**.

## 5. Kiểm thử tự động bằng Spring Security + MockMvc

Tạo `src/test/java/com/example/tenants/TenantAuthApplicationTests.java`:

```java
package com.example.tenants;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class TenantAuthApplicationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void identicalUsernameIsVerifiedAgainstEachTenantStore() throws Exception {
        mvc.perform(get("/tenants/north/me")
                    .with(httpBasic("sam", "north-pass123")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.tenant").value("north"))
                .andExpect(jsonPath("$.username").value("sam"))
                .andExpect(jsonPath("$.authorities[0]").value("ROLE_ANALYST"));

        mvc.perform(get("/tenants/south/me")
                    .with(httpBasic("sam", "south-pass456")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.tenant").value("south"))
                .andExpect(jsonPath("$.authorities[0]").value("ROLE_VIEWER"));
    }

    @Test
    void credentialsCannotCrossTenantBoundaries() throws Exception {
        mvc.perform(get("/tenants/south/me")
                    .with(httpBasic("sam", "north-pass123")))
                .andExpect(status().isUnauthorized());

        mvc.perform(get("/tenants/north/me")
                    .with(httpBasic("sam", "south-pass456")))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void clientHeadersCannotOverrideStoreOrGrantRoles() throws Exception {
        mvc.perform(get("/tenants/south/reports")
                    .with(httpBasic("sam", "south-pass456"))
                    .header("X-Tenant", "north")
                    .header("X-Role", "ROLE_ANALYST")
                    .header("X-Authenticated", "true"))
                .andExpect(status().isForbidden());

        mvc.perform(get("/tenants/south/me")
                    .with(httpBasic("sam", "north-pass123"))
                    .header("X-Tenant", "north"))
                .andExpect(status().isUnauthorized());

        mvc.perform(get("/tenants/north/reports")
                    .with(httpBasic("sam", "north-pass123")))
                .andExpect(status().isOk())
                .andExpect(content().string("reports:north"));
    }

    @Test
    void unregisteredTenantNeverFallsBackToAnotherStore() throws Exception {
        mvc.perform(get("/tenants/unknown/me")
                    .with(httpBasic("sam", "north-pass123")))
                .andExpect(status().is4xxClientError());
    }
}
```

Chạy:

```bash
mvn test
```

Các test không chỉ so output của một hàm tự viết: `MockMvc` chạy qua `FilterChainProxy`, `BasicAuthenticationFilter`, manager/provider và rule phân quyền thực. Chúng chứng minh hai kho riêng, credential không dùng xuyên tenant, header giả không đổi manager/role, và tenant không đăng ký bị từ chối. Việc kiểm thử trên source demo khác với thay đổi quyền/cấu hình của một ứng dụng production hiện hữu.

## 6. Thiết kế thực tế: registry, nhiều cơ chế và dữ liệu kinh doanh

### 6.1. Tenant registry cần nằm dưới quyền kiểm soát server

Ứng dụng thật thường lưu bảng cấu hình tenant do quy trình onboarding/administration có kiểm soát tạo ra. Một bản ghi có thể gồm:

| Trường | Ý nghĩa |
| --- | --- |
| `tenantId` | Định danh chuẩn, duy nhất, không đổi tùy tiện |
| `status` | Chỉ dùng tenant `ACTIVE`; suspended/deleted phải bị từ chối |
| `allowedDomains` / route mapping | Domain/path do hệ thống xác nhận và cấp phát |
| `identityProviderType` | Password store, LDAP, OIDC/JWT issuer hoặc API key đã được phê duyệt |
| `identityStoreRef` | Khóa tham chiếu secret/config do server quản lý, không phải JDBC URL do request đưa vào |
| `trustedIssuer`, `audience` | Danh sách issuer/audience hợp lệ cho từng tenant khi dùng Bearer |
| `policyVersion` | Phiên bản cấu hình quyền và chính sách xác thực được audit |
| `enabledMechanisms` | Các cơ chế được phép (Basic, session login, JWT...) theo tenant |

Khi một request mang tenant slug, server chuẩn hóa slug, tra registry, kiểm tra trạng thái và chọn manager/provider/decoder đã provision. **Không tự động tạo manager cho mọi chuỗi tenant mới xuất hiện**. Nếu muốn onboarding động, chỉ thành phần quản trị đã xác thực và được phân quyền mới được sửa registry; runtime chỉ đọc snapshot đáng tin, cache đúng khóa và loại bỏ cache khi cấu hình revoked.

Không lấy `X-Database-Url` hay `X-Issuer-Url` để mở kết nối hoặc tải JWK tùy ý. Điều đó có thể gây SSRF, nhầm kho hoặc làm hệ thống tin vào IdP do attacker chỉ định.

### 6.2. Có thể dùng `AuthenticationManagerResolver<HttpServletRequest>`

Khi số tenant lớn hoặc nhiều tenant dùng **cơ chế khác nhau**, có thể cần resolver chọn manager theo request. Spring Security cung cấp interface:

```java
public interface AuthenticationManagerResolver<C> {
    AuthenticationManager resolve(C context);
}
```

Đây là **trích dẫn API để minh họa khái niệm**, không phải tệp chạy độc lập. Với Servlet, tham số `C` có thể là `HttpServletRequest`. Resolver cần đọc **khóa tenant ứng viên đã được chuẩn hóa**, tra registry đáng tin rồi trả manager đã đăng ký; tenant không tồn tại phải thất bại an toàn.

Ví dụ thuật toán (pseudocode có chủ đích, **không phải Java hoàn chỉnh**):

```text
resolve(request):
    candidate = canonicalRouteResolver.candidateTenant(request)
    config = trustedTenantRegistry.requireActive(candidate)
    manager = managedAuthManagers.require(config.tenantId)
    return manager  // tuyệt đối không tạo manager từ URL tùy ý do client gửi
```

Một số cấu hình như `oauth2ResourceServer(...).authenticationManagerResolver(...)` nhận resolver trực tiếp. Với các filter khác, phải chọn loại filter/cơ chế hỗ trợ hoặc viết adapter đúng contract; **không có nghĩa** tự khai bean resolver sẽ khiến mọi `httpBasic()` hoặc `formLogin()` tự động dùng nó.

Trong demo hai tenant cố định, hai `SecurityFilterChain` cùng `http.authenticationManager(...)` rõ ràng và đủ dùng. Khi thay thành registry runtime, không giữ danh sách manager cũ cho tenant đã bị vô hiệu hóa; cần lifecycle, invalidation và giám sát cấu hình.

### 6.3. Với JWT/OIDC: lựa chọn issuer rồi xác minh token

JWT có thể chứa `iss`, `sub`, `tenant` và `roles`. Trước khi verify chữ ký và claims, những chuỗi này **chưa đáng tin**. Có thể dùng `iss` chưa xác minh như khóa **tra cứu tạm thời** trong danh sách issuer server đã allowlist, nhưng phải:
1. Chỉ chấp nhận issuer có trong registry/tập trusted issuers.
2. Chọn decoder/AuthenticationManager đã cấu hình cho issuer đó.
3. Verify chữ ký, thuật toán được phép, `iss`, `aud`, `exp`/`nbf` và các ràng buộc cần thiết.
4. Gắn tenant được xác minh vào principal, kiểm tra nó khớp tài nguyên đích; ánh xạ scopes/roles sau xác minh.
5. Từ chối unknown issuer, token hợp lệ nhưng sai audience, hoặc token của tenant khác.

Spring Security có `JwtIssuerAuthenticationManagerResolver.fromTrustedIssuers(...)` cho trường hợp nhiều issuer được tin cậy. Với token opaque, provider introspection phải được cấu hình theo trust boundary của tenant; không suy từ một header tự khai để dùng endpoint introspection tùy ý.

**Quan trọng:** `issuer` hợp lệ không đồng nghĩa token có quyền đọc dữ liệu tenant khác; authorization vẫn cần tenant/resource binding. Trường hợp cùng một issuer phục vụ nhiều tenant, phải kiểm tra tenant claim và mối quan hệ membership bằng policy được server xác nhận.

### 6.4. Với session và nhiều cách login

Nếu một ứng dụng hỗ trợ JSON login, form login, Basic, Bearer cùng lúc, hãy phân tích:
- **Cơ chế nào xử lý request này?** Match theo path/endpoint và Authorization scheme; tránh hai filter cùng xử lý trái ý định.
- **Tenant nào được chọn?** Dựa trên route/host đã mapping với registry, hoặc một claim đã được verify ở mức thích hợp.
- **Danh tính nào đã xác minh?** Bao gồm tenant membership và issuer hợp lệ; không dùng một cookie session từ north để ngầm vào south.
- **Context có được lưu không?** Session login dùng `SecurityContextRepository` và các biện pháp session fixation/CSRF; Basic/JWT stateless thường cần xác thực lại trên request mới.

Nếu dùng domain để chọn tenant, `Host`, `Forwarded` và `X-Forwarded-Host` có thể do client giả mạo nếu reverse proxy không lọc. Chỉ dựa vào hostname sau khi proxy đáng tin đã chuẩn hóa và server đã ánh xạ hostname tới tenant được provision. Đừng nhầm `getServerName()` với bằng chứng user thuộc tenant.

### 6.5. Ràng buộc cả truy vấn dữ liệu theo tenant

Authentication isolation **không đủ** để bảo vệ row dữ liệu. Nếu request tới `/tenants/north/invoices/42`, backend phải xác nhận:
- `Authentication` đã xác minh có đúng tenant north hoặc có quyền cross-tenant đặc biệt được policy server cấp.
- Invoice 42 thực sự thuộc north.
- Repository query bao gồm tenant key; không dùng một `findById(42)` toàn cục rồi trả ngay.

Minh họa **đoạn service/repository**, không phải ứng dụng độc lập:

```java
Invoice invoice = invoiceRepository
        .findByTenantIdAndId(authenticatedTenantId, invoiceId)
        .orElseThrow(() -> new ResourceNotFoundException());

authorizationService.requireCanReadInvoice(authentication, invoice);
return invoice;
```

Tên class và repository method ở đây biểu thị một thiết kế domain tùy ứng dụng. Trong hệ thống dùng row-level security, schema-per-tenant hoặc database-per-tenant, vẫn phải có bước thiết lập tenant context đúng nơi và đóng/reset nó để tránh rò rỉ giữa request/thread/connection pool.

### 6.6. Cache và audit cũng cần mang tenant identity

Cache theo mỗi `username` riêng lẻ có thể gộp nhầm `sam` của north và south; dùng khóa dạng `(tenantId, userId, policyVersion)` khi phù hợp. Tương tự, cache `UserDetails`, session, token verification, rate limit và event audit phải xác định tenant đúng, tránh ghi password, API key hoặc Bearer token vào log.

Khi một tenant bị đình chỉ, cần vô hiệu hóa đường xác thực và các phiên/token/cached permissions theo policy. Với cấu hình động, audit ai đã thay đổi registry, secret reference, issuer hoặc đường route. Các thao tác sửa cấu hình tenant cần admin permission và xác thực riêng.

## 7. Bẫy bảo mật thường gặp và cách nhận biết

| Lỗi thiết kế | Vì sao sai | Cách khắc phục |
| --- | --- | --- |
| Chọn database trực tiếp từ `X-Database-Url` | Client chỉ định hạ tầng, có thể SSRF hoặc truy cập kho khác | Dùng registry ánh xạ tenant -> secret/config do server provision |
| Đọc `X-Tenant` rồi tin user thuộc tenant đó | Header do client giả mạo | Xem là hint, chọn manager đã cho phép, **xác thực và kiểm tra membership** |
| Tìm `username` trong mọi tenant rồi chọn first match | Trùng username, dễ nhầm tổ chức | Chọn kho tenant đúng trước khi xác thực |
| Một `AuthenticationManager` fallback global cho tenant lạ | Dễ bỏ qua isolation | Unknown/disabled tenant: fail closed |
| Cho client gửi `roles`, `authenticated` | Leo thang quyền từ dữ liệu chưa xác minh | Chỉ dùng authorities do provider/issuer tin cậy xác minh |
| Parse JWT `iss` rồi tự tin mọi claim | Payload chưa được verify | Allowlist issuer để chọn verifier; verify chữ ký, audience, expiry rồi mới cấp quyền |
| Đã authenticate north nên cho đọc south | Authentication khác authorization | Bind principal tới tenant và kiểm tra tenant/resource ownership |
| Cache `UserDetails` theo username | Sam của hai tenant đè lẫn nhau | Cache key bao gồm tenant và metadata chính sách |
| Dùng sai thứ tự security chains | Route rơi vào chain quá rộng | `@Order` cụ thể trước, fallback cuối, test từng matcher |
| Chỉ bảo vệ filter, repository query toàn cục | Vẫn có thể đọc dữ liệu tổ chức khác | Scope truy vấn theo tenant và kiểm tra object-level authorization |
| Mỗi request tạo DataSource mới từ input | Tốn tài nguyên, kết nối không kiểm soát | Pool/manager provision sẵn, lifecycle và secret quản lý bởi server |

### 401, 403 và 404 trong môi trường nhiều tenant

- **401 Unauthorized**: không có credential hợp lệ cho manager của tenant đang truy cập. Với HTTP Basic thường có challenge `WWW-Authenticate`.
- **403 Forbidden**: đã xác thực nhưng không có quyền của tenant hoặc thao tác đang yêu cầu; ví dụ south user chỉ có `ROLE_VIEWER` truy cập `/reports` yêu cầu `ROLE_ANALYST`.
- **404 Not Found** hoặc mã 4xx chung: có thể dùng cho tenant/resource không đăng ký hoặc không thuộc người dùng theo chính sách hạn chế lộ thông tin. Không tạo một response cố định nếu không biết entry point/handler cụ thể. Quan trọng nhất là **không cho phép và không fallback sang tenant khác**.

Không dùng riêng response code để chứng minh tenant isolation. Cần test cả **credential của A trên route B**, **same username in A/B**, **role không đủ**, **tenant không tồn tại**, **resource thuộc B nhưng request của A**, và **token sai issuer/audience** nếu dùng JWT.

## 8. Lộ trình mở rộng từ demo sang sản phẩm

1. **Định danh tenant chuẩn:** chọn `tenantId` nội bộ ổn định và phân biệt với tên hiển thị/domain.
2. **Provision registry:** route/domain/issuer/method/store reference phải có quy trình quản trị, allowlist, trạng thái ACTIVE và audit.
3. **Bind identity:** tạo principal chứa tenant và id thực, không chỉ username; xác minh tenant membership trong provider/IdP.
4. **Phân tầng cơ chế:** cấu hình chains/resolver theo nhóm endpoint và credential scheme; kiểm tra không có bypass/fallback yếu.
5. **Phân quyền tenant:** roles/scopes được lấy từ server/verified claims, không từ raw request; kiểm tra cả quyền thao tác và sở hữu object.
6. **Giữ cách ly dữ liệu:** theo tenant ở datasource/schema/row query, connection lifecycle, cache, queue và audit.
7. **Bảo vệ credential:** HTTPS, password hash, MFA nếu cần, rate limit, monitoring, secret rotation và token expiry.
8. **Test đối kháng:** credential cross-tenant, tenant hint giả, issuer lạ, token hết hạn, account disabled, sai chain match và unknown tenant.

## 9. Câu hỏi tự kiểm tra

1. Vì sao `tenant=north` trong URL không chứng minh client là thành viên north nhưng vẫn có thể dùng làm khóa định tuyến?
2. Cùng username `sam` ở north/south nên được nhận diện nội bộ như thế nào?
3. `AuthenticationManager` và `AuthenticationProvider` nào kiểm tra password khi request tới `/tenants/south/me`?
4. Nếu lấy password north gửi tới south, vì sao phải nhận 401?
5. Vì sao header `X-Role: ROLE_ANALYST` không thể làm south user vào `/tenants/south/reports`?
6. Lý do cần `denyOtherPaths` ở cuối thay vì một manager toàn cục fallback?
7. Với JWT có `iss` chưa verify, điều gì được phép làm trước bước verify chữ ký, và điều gì tuyệt đối không?
8. Đã đăng nhập north thành công, tại sao `findById(invoiceId)` vẫn có thể làm lộ dữ liệu south?
9. Tại sao cache key chỉ có username thường không đủ trong multi-tenant?
10. Nếu application dùng `Host` để chọn tenant, cần kiểm soát điều gì ở reverse proxy?

**Gợi ý đáp án:** (1) path là client-controlled hint, registry/map tin cậy và provider kiểm chứng membership; (2) `(tenantId,userId)`; (3) manager/DAO provider của south; (4) hash password south không khớp; (5) role lấy từ provider server; (6) fail closed cho tenant lạ; (7) dùng issuer làm khóa allowlist chọn verifier, không tin claim trước khi verify; (8) thiếu tenant-bound query/ownership; (9) trùng username giữa tenant; (10) chuẩn hóa và khóa spoofed forwarded headers, map hostname chỉ từ config server.

## 10. Tham khảo chính thức

- Spring Security — Multiple HttpSecurity / SecurityFilterChain: https://docs.spring.io/spring-security/reference/6.5/servlet/configuration/java.html
- Spring Security — Authentication Architecture: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html
- Spring Security — DaoAuthenticationProvider: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html
- Spring Security — OAuth2 Resource Server Multi-tenancy / AuthenticationManagerResolver: https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/multitenancy.html
- Spring Security — HTTP Basic authentication: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/basic.html
- Spring Security — Authorize HTTP Requests: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html
