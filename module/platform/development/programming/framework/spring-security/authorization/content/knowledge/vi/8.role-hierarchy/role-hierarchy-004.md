# Đưa hierarchy vào AuthorizationManager theo phiên bản

## 1. Bài toán: đã khai báo role hierarchy nhưng quy tắc vẫn từ chối?

Trong Spring Security, nhiều ứng dụng có các vai trò theo cấp bậc: người quản trị có thể thực hiện một số chức năng của nhân viên, nhân viên có thể đọc dữ liệu của người xem. Thay vì gán từng role thấp hơn trực tiếp cho mọi người dùng, ta định nghĩa **role hierarchy**.

Ví dụ:

```text
ROLE_ADMIN
    |
    v
ROLE_MANAGER
    |
    v
ROLE_READER
    |
    v
report:read

ROLE_AUDITOR
    |
    v
audit:view
```

Dấu mũi tên có nghĩa **role/authority bên trên bao hàm authority bên dưới**. Nếu người dùng được cấp trực tiếp `ROLE_ADMIN`, một bộ kiểm tra có áp dụng hierarchy có thể xem người ấy như có cả `ROLE_MANAGER`, `ROLE_READER` và `report:read`.

Nhưng một vấn đề rất thường gặp:

1. Ứng dụng khai báo bean `RoleHierarchy`.
2. Rule HTTP dùng `.hasAuthority("report:read")`; annotation method dùng `@PreAuthorize("hasRole('READER')")`.
3. Người dùng chỉ có `ROLE_ADMIN` trong `Authentication.getAuthorities()`.
4. Một số request/method được cho phép, một số bị 403.

Nguyên nhân có thể là **từng AuthorizationManager đang sử dụng các cấu hình hierarchy khác nhau, một manager tùy chỉnh không hề áp dụng hierarchy, hoặc API cấu hình đã thay đổi theo phiên bản Spring Security**.

Bài học này tập trung vào **đưa role hierarchy vào đúng điểm ra quyết định**, đặc biệt phân biệt các dòng Spring Security 6.x và 7.x, thay vì chỉ dừng ở cách viết chuỗi `ROLE_ADMIN > ROLE_USER`.

### Chuỗi quyết định cần hiểu

```text
Nguồn danh tính đáng tin (DB / IdP / JWT / session)
                  |
                  v
Authentication
  authorities trực tiếp: [ROLE_ADMIN]
                  |
                  v
AuthorizationManager
  + RoleHierarchy được gắn đúng?
                  |
         +--------+--------+
         |                 |
        Có               Không
         |                 |
         v                 v
  Reachable authorities   Chỉ authority trực tiếp
  [ROLE_ADMIN, ...]        [ROLE_ADMIN]
         |                 |
         v                 v
  hasRole("READER")       hasRole("READER")
       true                    false
```

**Quan trọng:** hierarchy là cách **đánh giá những authority có thể đạt tới từ quyền đã cấp**, không tự động sửa vĩnh viễn tập quyền gốc được lưu ở nguồn danh tính. `Authentication.getAuthorities()` vẫn có thể chỉ trả `ROLE_ADMIN` dù manager dùng hierarchy để cho phép `ROLE_READER`.

## 2. Nắm chắc RoleHierarchy, GrantedAuthority và AuthorizationManager

| Thành phần | Nhiệm vụ | Ví dụ |
| --- | --- | --- |
| `GrantedAuthority` | Một authority được xác thực và gắn với principal | `ROLE_ADMIN` |
| `RoleHierarchy` | Tính các authority có thể đạt tới bằng quan hệ bao hàm | `ROLE_ADMIN > ROLE_READER` |
| `RoleHierarchyImpl` | Implementation phổ biến của `RoleHierarchy` | `fromHierarchy(...)` |
| `AuthorityAuthorizationManager<T>` | Kiểm tra yêu cầu về role/authority với `Authentication` | `hasRole("READER")` |
| `AuthorizationManager<T>` | Hợp đồng ra quyết định trên một đối tượng được bảo vệ | Request hoặc method invocation |
| `RequestMatcherDelegatingAuthorizationManager` | Chọn một manager theo URL/method khi phân quyền HTTP | `/api/reports/**` |
| `DefaultMethodSecurityExpressionHandler` | Tạo ngữ cảnh SpEL cho `@PreAuthorize`, `@PostAuthorize` | `hasAuthority('report:read')` |
| `AuthorizationManagerFactory<T>` | Tạo các manager với cấu hình nhất quán trong Spring Security 7.0+ | `hasRole(...)`, `hasAuthority(...)` |
| `Authentication` | Mang principal và authorities do cơ chế xác thực tạo ra | `ROLE_ADMIN`, `SCOPE_reports.read` |

Một role hierarchy **không phải** là một nguồn định danh. Nó không xác minh token, không tra cứu người dùng, không biết owner của bản ghi và không bảo đảm một người có quyền ở tenant A cũng có quyền ở tenant B.

### 2.1. Hướng của mũi tên rất quan trọng

```text
ROLE_ADMIN > ROLE_MANAGER
ROLE_MANAGER > ROLE_READER
ROLE_READER > report:read
```

Điều này có nghĩa:

- Người có `ROLE_ADMIN` bao hàm `ROLE_MANAGER`, `ROLE_READER`, `report:read`.
- Người có `ROLE_MANAGER` bao hàm `ROLE_READER`, `report:read`; **không** bao hàm `ROLE_ADMIN`.
- Người có `ROLE_READER` bao hàm `report:read`; **không** có quyền quản lý.
- Người chỉ có `report:read` không vì vậy trở thành người có `ROLE_READER`.

Hierarchy có **tính bắc cầu**: nếu A bao hàm B và B bao hàm C thì A bao hàm C. Đừng viết ngược quan hệ, vì đó là hành động nâng quyền thực sự.

### 2.2. `hasRole` khác `hasAuthority`

Với tiền tố role mặc định:

- `hasRole("ADMIN")` thường kiểm tra `ROLE_ADMIN`.
- `hasRole("READER")` thường kiểm tra `ROLE_READER`.
- `hasAuthority("ROLE_READER")` kiểm tra tên chính xác `ROLE_READER`.
- `hasAuthority("report:read")` kiểm tra tên chính xác `report:read`.
- `hasAuthority("SCOPE_reports.read")` kiểm tra tên chính xác `SCOPE_reports.read`, không đồng nghĩa `report:read`.

Một manager **được nối với hierarchy đúng cách** có thể đánh giá các authority đạt tới theo đồ thị. Manager không có hierarchy có thể chỉ xem quyền trực tiếp. Vì vậy phải xác minh không chỉ **tên chuỗi**, mà còn **manager nào đang làm phép kiểm tra**.

Không truyền `hasRole("ROLE_ADMIN")` theo thói quen với API mặc định tự thêm `ROLE_`. Dùng `hasRole("ADMIN")` hoặc `hasAuthority("ROLE_ADMIN")` nhất quán. Nếu ứng dụng thay prefix bằng `GrantedAuthorityDefaults` hoặc factory riêng, phải đảm bảo tên role, mapper và hierarchy đồng bộ.

### 2.3. Role và permission có thể cùng nằm trong hierarchy

Không nhất thiết mọi node đều phải có tiền tố `ROLE_`. Tài liệu Spring Security về method security có ví dụ tương đương:

```text
ROLE_ADMIN > permission:read
```

Nhưng cần phân biệt cách **khai báo bằng chuỗi đầy đủ** với cách **dùng builder tự thêm role prefix**. Nếu mục tiêu là nối role với permission tùy ý như `report:read`, cú pháp `RoleHierarchyImpl.fromHierarchy("ROLE_READER > report:read")` trực tiếp và rõ ràng. Builder có prefix phù hợp hơn khi mọi node là **role**.

## 3. Tại sao “theo phiên bản” là trọng tâm?

API phân quyền Spring Security phát triển qua nhiều thế hệ. Cách gắn hierarchy với manager, nguồn tạo manager và phương thức gọi quyết định không hoàn toàn giống nhau.

| Nhóm phiên bản | Cơ chế nổi bật | Cách tư duy khi tích hợp hierarchy |
| --- | --- | --- |
| Spring Security 5.x truyền thống | `authorizeRequests`, `FilterSecurityInterceptor`, `AccessDecisionManager`/voter và expression handler | Cần kiểm tra chính xác điểm tiêu thụ hierarchy; không sao chép cấu hình hiện đại |
| 6.0–6.2 | Ưu tiên `authorizeHttpRequests` và `AuthorizationManager`; method security theo `@EnableMethodSecurity` | Dùng API có thực trong phiên bản đã khóa, không giả định builder mới hơn tồn tại |
| 6.3 | `RoleHierarchyImpl.withDefaultRolePrefix()`/`withRolePrefix()` được giới thiệu; cách gắn manager vẫn dùng API 6.x | Có thể khai báo `RoleHierarchy` và gắn tường minh vào manager |
| 6.4–6.5 | `AuthorizationManager.authorize(...)`/kiểu kết quả mới được phát triển; API cũ `check(...)` vẫn hiện diện trong tài liệu 6.5; hỗ trợ hierarchy cho HTTP/method | Kiểm tra manager nào được sinh bởi DSL, manager nào tự tạo và expression handler |
| 7.0+ | Có `AuthorizationManagerFactory<T>` và `DefaultAuthorizationManagerFactory<T>` để cấu hình các manager được tạo | Định nghĩa factory/roleHierarchy theo API 7.x, không bê nguyên mẫu 6.x |
 
**Không sử dụng hai mẫu cấu hình 6.x và 7.x đồng thời theo kiểu copy-paste.** Chúng mô tả những cách tích hợp theo hệ API khác nhau. Khi triển khai thật, kiểm tra dependency lockfile/Maven hoặc Gradle, xác nhận Spring Security phiên bản thực tế, sau đó chọn một hướng tương ứng.

Nếu dự án còn Spring Security 5.x hoặc 6.0–6.2, tra JavaDoc đúng phiên bản trước khi sử dụng builder từ 6.3 hoặc factory từ 7.0. Không nâng phiên bản chỉ để sao chép một ví dụ nhỏ nếu dự án chưa có kế hoạch tương thích.

## 4. Khai báo RoleHierarchyImpl đúng cách

### 4.1. Cú pháp chuỗi đầy đủ: phù hợp role và permission

Với dòng Spring Security 6.3/6.5, ví dụ:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.security.access.hierarchicalroles.RoleHierarchy;
import org.springframework.security.access.hierarchicalroles.RoleHierarchyImpl;

@Bean
static RoleHierarchy roleHierarchy() {
    return RoleHierarchyImpl.fromHierarchy("""
        ROLE_ADMIN > ROLE_MANAGER
        ROLE_MANAGER > ROLE_READER
        ROLE_READER > report:read
        """);
}
```

Đây là **fragment đặt trong lớp `@Configuration`**, sử dụng Java 17 text block; cần Spring Security dependency. Nó định nghĩa quan hệ:

- `ROLE_ADMIN` có tất cả quyền của `ROLE_MANAGER`.
- `ROLE_MANAGER` có tất cả quyền của `ROLE_READER`.
- `ROLE_READER` có `report:read`.

Phương thức `fromHierarchy(String)` nhận định nghĩa dưới dạng chuỗi. Không nhầm `>` với phép so sánh số trong Java; đây là cú pháp graph hierarchy do Spring Security phân tích.

### 4.2. Builder có tiền tố role: Spring Security 6.3+

Nếu chỉ làm việc với các role cùng một tiền tố:

```java
RoleHierarchy hierarchy = RoleHierarchyImpl
    .withDefaultRolePrefix()
    .role("ADMIN").implies("MANAGER")
    .role("MANAGER").implies("READER")
    .build();
```

Builder theo tiền tố mặc định tạo quan hệ tương đương `ROLE_ADMIN > ROLE_MANAGER > ROLE_READER`. Tài liệu API xác nhận `withDefaultRolePrefix()` và `withRolePrefix(String)` có từ **6.3**.

**Đừng** viết `.role("READER").implies("report:read")` khi đang muốn một permission raw `report:read` mà không kiểm chứng cách builder áp prefix; hãy dùng `fromHierarchy` với authority đầy đủ hoặc xây mapping rõ ràng. Builder không phải công cụ chung để suy diễn tùy ý tenant hoặc permission có cấu trúc.

### 4.3. Kiểm tra closure trước khi gắn vào manager

Cơ chế quan sát kết quả:

```java
import java.util.List;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

var reached = roleHierarchy.getReachableGrantedAuthorities(
    List.of(new SimpleGrantedAuthority("ROLE_ADMIN"))
);
```

Với graph ở trên, tập reached sẽ bao gồm `ROLE_ADMIN`, `ROLE_MANAGER`, `ROLE_READER` và `report:read`. Thứ tự collection không nên là ràng buộc của test; so sánh **tập chuỗi authority**.

Đây là bước kiểm tra **graph đúng**. Nó chưa chứng minh HTTP authorization hoặc `@PreAuthorize` đang sử dụng hierarchy ấy; những chốt đó phải được kiểm tra riêng.

### 4.4. Chu trình, mở quyền quá rộng và tính hợp lệ

Nếu viết quan hệ chu kỳ, chẳng hạn A > B và B > A, hierarchy khó diễn đạt một cấp bậc đúng nghĩa. Các implementation như `RoleHierarchyImpl` trong phiên bản được tài liệu hóa phát hiện cycle khi xây đồ thị và có thể ném ngoại lệ cấu hình.

Đừng cố “chữa” bằng cách bỏ qua lỗi, hoặc cho mọi role bao hàm admin. Một thay đổi hierarchy là **thay đổi chính sách bảo mật**; cần code review, test quyền bị từ chối và xác minh những ai nhận authority gián tiếp mới.

## 5. Spring Security 6.x: gắn trực tiếp vào AuthorityAuthorizationManager

Đây là cách **tường minh, dễ kiểm thử** cho một rule HTTP tự tạo: xây manager, gọi `setRoleHierarchy(...)` rồi truyền cho `authorizeHttpRequests(...).access(...)`.

Với Spring Security 6.5, JavaDoc của `AuthorityAuthorizationManager` xác nhận phương thức `setRoleHierarchy(RoleHierarchy)`. Tài liệu 6.5 cũng mô tả hierarchy trong `authorizeHttpRequests`. Đối với manager do chính bạn tạo, cấu hình tường minh giúp tránh phỏng đoán framework có tự tìm bean hierarchy cho **manager tùy chỉnh ấy** hay không.

### 5.1. Ví dụ cấu hình HTTP và method cùng một hierarchy

Đây là **một lớp cấu hình tích hợp Spring Security 6.5 / Spring Boot 3.x**, không phải chương trình Java độc lập. Nó giả định ứng dụng có authentication provider phù hợp, controller báo cáo và dữ liệu nghiệp vụ thực tế.

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.access.expression.method.DefaultMethodSecurityExpressionHandler;
import org.springframework.security.access.expression.method.MethodSecurityExpressionHandler;
import org.springframework.security.access.hierarchicalroles.RoleHierarchy;
import org.springframework.security.access.hierarchicalroles.RoleHierarchyImpl;
import org.springframework.security.authorization.AuthorityAuthorizationManager;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.intercept.RequestAuthorizationContext;

@Configuration
@EnableMethodSecurity
public class RoleHierarchySecurity6Config {

    @Bean
    static RoleHierarchy roleHierarchy() {
        return RoleHierarchyImpl.fromHierarchy("""
            ROLE_ADMIN > ROLE_MANAGER
            ROLE_MANAGER > ROLE_READER
            ROLE_READER > report:read
            """);
    }

    // Với @PreAuthorize/@PostAuthorize: cấu hình expression handler.
    @Bean
    static MethodSecurityExpressionHandler methodSecurityExpressionHandler(
            RoleHierarchy hierarchy) {

        DefaultMethodSecurityExpressionHandler handler =
            new DefaultMethodSecurityExpressionHandler();
        handler.setRoleHierarchy(hierarchy);
        return handler;
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            RoleHierarchy hierarchy) throws Exception {

        AuthorityAuthorizationManager<RequestAuthorizationContext>
            reportReader =
                AuthorityAuthorizationManager.hasAuthority("report:read");

        // ĐIỂM NỐI QUAN TRỌNG cho manager được tạo thủ công.
        reportReader.setRoleHierarchy(hierarchy);

        http.authorizeHttpRequests(auth -> auth
            .requestMatchers(
                HttpMethod.GET, "/api/reports", "/api/reports/**"
            ).access(reportReader)
            .requestMatchers(HttpMethod.GET, "/public/**")
                .permitAll()
            .anyRequest().denyAll()
        );

        return http.build();
    }
}
```

Từng bước:

1. `RoleHierarchy` là **một bean chính sách**. Chỉ có một định nghĩa graph trong ví dụ.
2. `reportReader` là `AuthorityAuthorizationManager<RequestAuthorizationContext>` được tạo bằng `hasAuthority("report:read")`.
3. `reportReader.setRoleHierarchy(hierarchy)` nối graph vào **chính manager này**. Người có authority trực tiếp `ROLE_ADMIN` có thể thỏa yêu cầu `report:read` thông qua reachability.
4. `.access(reportReader)` dùng manager đã cấu hình thay vì tạo một manager khác rồi bỏ lỡ hierarchy. Đây là điểm tích hợp quan trọng nhất ở ví dụ.
5. `@EnableMethodSecurity` và `MethodSecurityExpressionHandler` cấu hình phép đánh giá hierarchy cho các biểu thức pre/post authorization tại method.
6. `anyRequest().denyAll()` đóng các URL/method chưa khai báo **trong chain này**; nếu dùng nhiều chain, vẫn cần fallback phù hợp để bảo vệ toàn ứng dụng.

**Lưu ý phạm vi:** đây là cấu hình tập trung vào authorization. Chưa có form login/JWT resource server, CSRF, CORS, entrypoint xử lý lỗi hoặc object policy. Không copy lên production rồi cho rằng authentication đã được giải quyết.

### 5.2. Có được thay `.access(reportReader)` bằng `.hasAuthority("report:read")`?

Với một số phiên bản và cách cấu hình, Spring Security có hỗ trợ tìm `RoleHierarchy` bean cho manager được DSL xây dựng. Tài liệu 6.5 mô tả cách cấu hình hierarchy dùng cho HTTP. Tuy nhiên, khi đang xây **một ví dụ bảo đảm manager cụ thể có hierarchy**, ta chủ động truyền manager qua `.access(...)`.

Hãy phân biệt:

```text
requestMatchers(...).hasAuthority("report:read")
  -> DSL tự tạo/chọn AuthorizationManager
  -> cần xác minh version và cơ chế inject hierarchy

requestMatchers(...).access(reportReader)
  -> Dùng manager đã được mình setRoleHierarchy
  -> Hiệu lực dễ quan sát và unit test trực tiếp
```

Không kết luận rằng chỉ vì Spring context có bean `RoleHierarchy` thì **mọi custom `AuthorizationManager` trong code tự động dùng nó**. Nếu một manager tùy chỉnh tự duyệt `authentication.getAuthorities()` và so sánh string, nó không có hành vi hierarchy trừ khi logic của nó gọi `RoleHierarchy` hoặc được thiết kế tương đương.

### 5.3. Kiểm tra manager trực tiếp trong Spring Security 6.x

Ví dụ fragment JUnit (cần thư viện Spring Security và JUnit; không chạy độc lập bằng `javac`):

```java
RoleHierarchy hierarchy = RoleHierarchyImpl.fromHierarchy("""
    ROLE_ADMIN > ROLE_MANAGER
    ROLE_MANAGER > ROLE_READER
    ROLE_READER > report:read
    """);

AuthorityAuthorizationManager<Object> manager =
    AuthorityAuthorizationManager.hasAuthority("report:read");

manager.setRoleHierarchy(hierarchy);

Authentication admin =
    new UsernamePasswordAuthenticationToken(
        "alice", "N/A",
        List.of(new SimpleGrantedAuthority("ROLE_ADMIN"))
    );

AuthorizationDecision decision =
    manager.check(() -> admin, new Object());

assertNotNull(decision);
assertTrue(decision.isGranted());
```

Trong test phải import các class `Authentication`, `UsernamePasswordAuthenticationToken`, `SimpleGrantedAuthority`, `AuthorizationDecision`, `RoleHierarchy`, `RoleHierarchyImpl`, `List` cùng static assertions của JUnit. Với Spring Security 6.5, `check(...)` vẫn là API hiển thị trong tài liệu; **không copy thẳng chữ ký test này sang 7.x khi API đã đổi**.

Tạo test đối chứng không gọi `setRoleHierarchy`: nếu user chỉ có `ROLE_ADMIN` và manager kiểm tra raw `report:read`, kết quả thường bị từ chối. Đây là phép thử rất hữu ích để xác nhận **chính xác sự khác biệt do nối hierarchy**.

### 5.4. Method security trong 6.x: một điểm nối khác

Nếu service có:

```java
@PreAuthorize("hasAuthority('report:read')")
public ReportView readReport(long reportId) {
    // Truy vấn giới hạn theo tenant và quyền đối tượng.
}
```

thì cùng roleHierarchy phải được cung cấp cho biểu thức method security, ví dụ qua `DefaultMethodSecurityExpressionHandler#setRoleHierarchy` như lớp cấu hình ở mục 5.1. Đối với `@Secured` và JSR-250, các manager riêng có hỗ trợ hierarchy trong các phiên bản tương ứng; không được cho rằng một bean expression handler tự động tùy biến mọi loại annotation trong mọi cấu hình.

Nếu chưa bật `@EnableMethodSecurity` thì annotation `@PreAuthorize` không tự có hiệu lực chỉ nhờ có dependency Spring Security. Nếu method được gọi bằng self-invocation trong cùng instance, Spring AOP proxy cũng có thể bị bỏ qua. Cần kiểm thử phương thức qua bean/proxy và tiếp tục bảo vệ tenant/owner tại tầng dữ liệu.

### 5.5. Hierarchy cho authority nhưng không tự thay đổi dữ liệu JWT

Nếu principal của Resource Server chỉ mang `SCOPE_reports.read`, hierarchy graph gồm `ROLE_ADMIN > ...` không tạo được `ROLE_ADMIN`. Ngược lại, JWT có claim `roles:["ADMIN"]` không tự biến thành `ROLE_ADMIN` nếu chưa có bộ chuyển claim-to-authority phù hợp.

Tách rõ:

```text
JWT đã xác minh
 -> JwtAuthenticationConverter/authority mapper
 -> Authentication authorities trực tiếp
 -> AuthorizationManager + RoleHierarchy
 -> quyết định permission
 -> policy tài nguyên (tenant/owner)
```

Không thêm shortcut “nếu token có bất kỳ role text admin nào thì cấp ROLE_ADMIN” mà không xác minh issuer, audience, trust của claim và bảng mapping được duyệt.

## 6. Spring Security 7.x: đưa hierarchy vào AuthorizationManagerFactory

Spring Security **7.0 giới thiệu `AuthorizationManagerFactory<T>`**, theo tài liệu Authorization Architecture của dự án. Mục đích là cung cấp nơi cấu hình dùng chung cho những manager được tạo ở request-based và method-based authorization, thay vì phải tự gọi setter trên từng manager do DSL tạo.

Một implementation tiêu chuẩn là `DefaultAuthorizationManagerFactory<T>`. Nó cho phép cấu hình:

- `RoleHierarchy`.
- Tiền tố role (thông thường `ROLE_`).
- `AuthenticationTrustResolver` và các quy tắc tạo manager khác tùy API thực tế.

### 6.1. Cấu hình factory theo kiểu Spring Security 7.x

Đây là **fragment tích hợp cho Spring Security 7.x**, tách biệt với lớp cấu hình 6.x phía trên:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.access.hierarchicalroles.RoleHierarchy;
import org.springframework.security.access.hierarchicalroles.RoleHierarchyImpl;
import org.springframework.security.authorization.AuthorizationManagerFactory;
import org.springframework.security.authorization.DefaultAuthorizationManagerFactory;

@Configuration
public class RoleHierarchySecurity7Config {

    @Bean
    static RoleHierarchy roleHierarchy() {
        return RoleHierarchyImpl.fromHierarchy("""
            ROLE_ADMIN > ROLE_MANAGER
            ROLE_MANAGER > ROLE_READER
            ROLE_READER > report:read
            """);
    }

    @Bean
    <T> AuthorizationManagerFactory<T> authorizationManagerFactory(
            RoleHierarchy hierarchy) {

        DefaultAuthorizationManagerFactory<T> factory =
            new DefaultAuthorizationManagerFactory<>();
        factory.setRoleHierarchy(hierarchy);
        return factory;
    }
}
```

Đối chiếu với tài liệu 7.x: factory được đưa vào nơi Spring Security tạo các `AuthorizationManager` thông dụng. Khi dùng các DSL/annotation mà factory đó hỗ trợ, chúng có thể chia sẻ chính sách hierarchy thống nhất.

**Không xem factory bean là bằng chứng tất cả chốt phân quyền trong ứng dụng đều đã cập nhật.** Những manager custom tự tạo, expression handler đã được tùy biến, rule dựa trên `PermissionEvaluator`, bảo mật dữ liệu, phiên bản thư viện phụ hoặc ứng dụng có nhiều cấu hình method security cần được kiểm tra. Với `@PreAuthorize` SpEL, tài liệu cũng trình bày cấu hình `MethodSecurityExpressionHandler` gắn hierarchy; bảo đảm thực tế bằng integration test, không bằng việc chỉ thấy factory tồn tại trong context.

### 6.2. API quyết định của manager trong 7.x

Ở dòng 6.x, nhiều ví dụ hướng dẫn dùng:

```java
AuthorizationDecision result =
    manager.check(authenticationSupplier, context);
```

Trong tài liệu Spring Security 7.x, hợp đồng tập trung vào:

```java
AuthorizationResult result =
    manager.authorize(authenticationSupplier, context);
```

Hai đoạn là **mảnh code mô tả khác biệt API**, không phải các chương trình Java độc lập, và cần import kiểu tương ứng. Không thay chữ `check` thành `authorize` hoặc ngược lại trên toàn dự án mà chưa xem chữ ký của bản đang dùng.

Phân biệt:

- **Cấu hình hierarchy:** graph và nơi gắn graph vào factory/manager.
- **Thực thi quyết định:** method `check(...)` hoặc `authorize(...)` theo phiên bản.
- **Xử lý kết quả:** kiểm tra granted/denied, xử lý kết quả không đưa ra quyết định khi có thể, ném/điều phối lỗi phù hợp.

Với code 7.x mới, ưu tiên API 7.x như tài liệu; với dự án 6.5 đang hoạt động, không cần tự động chuyển toàn bộ code sang factory của 7.x.

### 6.3. Prefix và role builder trong 7.x

Nếu dùng `DefaultAuthorizationManagerFactory.setRolePrefix(...)` với giá trị khác `ROLE_`, phải đồng bộ nó với:

- Tên `GrantedAuthority` do authentication converter/IdP mapper phát hành.
- Cách `hasRole(...)` của manager được tạo.
- `RoleHierarchyImpl.withRolePrefix(...)` hoặc định nghĩa graph bằng chuỗi đầy đủ.
- Những manager custom và rule chính sách ở các tầng khác.

Không chỉ đổi prefix một nơi rồi chờ mọi authority tự được đổi tên. Với hierarchy chứa permission như `report:read`, định nghĩa bằng chuỗi đầy đủ thường ít nhầm hơn.

### 6.4. Vì sao factory giúp tránh tình trạng “rule A hiểu hierarchy, rule B không hiểu”?

Khi các manager thông dụng được khởi tạo từ một factory dùng chung, cấu hình hierarchy và prefix có thể được quản lý tại một điểm thay vì gắn nhiều setter theo từng route. Tuy nhiên:

- Custom manager không sử dụng factory vẫn có thể bỏ qua hierarchy.
- Một manager `hasAuthority("report:approve")` không tự cho phép user admin nếu hierarchy không định nghĩa quan hệ tới `report:approve`.
- Method security có expression handler tùy chỉnh riêng cần được rà soát.
- Tenant và quyền trên đối tượng không tự xuất hiện từ role graph.

Factory **chuẩn hóa cấu hình manager**, không thay thế việc mô tả đúng chính sách nghiệp vụ.

## 7. So sánh hai hướng cấu hình từ góc nhìn bảo mật

| Tiêu chí | 6.x với manager tường minh | 7.x với factory |
| --- | --- | --- |
| Đơn vị tích hợp | Một `AuthorityAuthorizationManager<T>` cụ thể | Nơi tạo các `AuthorizationManager<T>` được hỗ trợ |
| Điểm gắn graph | `manager.setRoleHierarchy(roleHierarchy)` | `factory.setRoleHierarchy(roleHierarchy)` |
| Dùng trong HTTP | `requestMatchers(...).access(manager)` | DSL manager được factory tạo theo 7.x |
| Áp dụng cho custom manager | Phải gắn hoặc tích hợp tường minh | Custom manager ngoài factory vẫn cần xử lý |
| Method security | Kiểm tra `MethodSecurityExpressionHandler`/interceptors | Kiểm tra factory và expression handling đúng bản |
| Debug lỗi 403 | Manager nào được gọi? Có hierarchy? | Factory nào sinh manager? Có custom override? |
| Kiểm thử | Unit test `manager.check(...)` của bản 6.x + MockMvc | Test manager/DSL theo `authorize(...)` của bản 7.x + MockMvc |
| Điều không thay thế | Identity trust, object authorization | Identity trust, object authorization |

Điểm giống nhau bất biến: **cần một tập role hierarchy đã được review, một cơ chế xác thực đáng tin, các permission tường minh và test cho cả permit lẫn deny**.

## 8. Mô phỏng bằng Java 17 độc lập: kiểm tra quyền bắc cầu

Để hiểu chính xác thuật toán về mặt tư duy, hãy chạy chương trình Java thuần sau. Nó không cần Spring Security; nó mô phỏng một đồ thị role/authority và dùng **BFS** để lấy tập authority đạt tới.

Lưu `RoleHierarchyManagerDemo.java`:

```java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeSet;

public class RoleHierarchyManagerDemo {
    private static final Map<String, Set<String>> IMPLIES = Map.of(
        "ROLE_ADMIN", Set.of("ROLE_MANAGER"),
        "ROLE_MANAGER", Set.of("ROLE_READER"),
        "ROLE_READER", Set.of("report:read"),
        "ROLE_AUDITOR", Set.of("audit:view")
    );

    record Actor(String id, String tenantId, Set<String> granted) {}

    static Set<String> reachable(Set<String> granted) {
        if (granted == null) {
            return Set.of();
        }

        Set<String> result = new HashSet<>();
        Deque<String> pending = new ArrayDeque<>(granted);

        while (!pending.isEmpty()) {
            String authority = pending.removeFirst();
            if (result.add(authority)) {
                pending.addAll(
                    IMPLIES.getOrDefault(authority, Set.of())
                );
            }
        }

        return Set.copyOf(result);
    }

    static boolean hasAuthority(
            Actor actor, String required) {
        return actor != null
            && required != null
            && reachable(actor.granted()).contains(required);
    }

    static boolean canRead(
            Actor actor, String reportTenant) {
        return actor != null
            && reportTenant != null
            && reportTenant.equals(actor.tenantId())
            && hasAuthority(actor, "report:read");
    }

    static void display(String label, Set<String> granted) {
        System.out.println(
            label + ": " + new TreeSet<>(reachable(granted))
        );
    }

    public static void main(String[] args) {
        Actor admin = new Actor(
            "a", "tenant-A", Set.of("ROLE_ADMIN")
        );
        Actor manager = new Actor(
            "m", "tenant-A", Set.of("ROLE_MANAGER")
        );
        Actor reader = new Actor(
            "r", "tenant-A", Set.of("ROLE_READER")
        );
        Actor auditor = new Actor(
            "u", "tenant-A", Set.of("ROLE_AUDITOR")
        );

        display("admin effective", admin.granted());
        display("manager effective", manager.granted());
        display("auditor effective", auditor.granted());
        display("unknown effective", Set.of("ROLE_UNKNOWN"));

        System.out.println(
            "admin reads tenant-A: " + canRead(admin, "tenant-A")
        );
        System.out.println(
            "admin reads tenant-B: " + canRead(admin, "tenant-B")
        );
        System.out.println(
            "auditor reads tenant-A: " + canRead(auditor, "tenant-A")
        );
        System.out.println(
            "reader reads tenant-A: " + canRead(reader, "tenant-A")
        );
        System.out.println(
            "admin approves: "
                + hasAuthority(admin, "report:approve")
        );
    }
}
```

Chạy với JDK 17 hoặc mới hơn:

```bash
javac RoleHierarchyManagerDemo.java
java RoleHierarchyManagerDemo
```

Kết quả chuẩn:

```text
admin effective: [ROLE_ADMIN, ROLE_MANAGER, ROLE_READER, report:read]
manager effective: [ROLE_MANAGER, ROLE_READER, report:read]
auditor effective: [ROLE_AUDITOR, audit:view]
unknown effective: [ROLE_UNKNOWN]
admin reads tenant-A: true
admin reads tenant-B: false
auditor reads tenant-A: false
reader reads tenant-A: true
admin approves: false
```

Giải thích:

1. Graph bắc cầu từ `ROLE_ADMIN` xuống `report:read`, vì vậy admin có quyền đọc qua hierarchy dù không được cấp trực tiếp permission string.
2. Auditor có `audit:view` nhưng không có `report:read`. Đồ thị độc lập không tạo quyền ngoài quan hệ đã khai báo.
3. Role không được biết trong graph vẫn chỉ chứa chính nó; không tự trở thành admin.
4. Admin có quyền đọc nhưng **không có** `report:approve`, vì ví dụ không khai báo quan hệ tương ứng. Một role cấp cao trong một nhánh không tự bao hàm mọi permission của toàn hệ thống.
5. Admin cũng không được đọc báo cáo tenant B dù có `report:read`: đó là điều kiện **ngoài hierarchy**, phải kiểm tra theo tài nguyên.
6. Dùng `TreeSet` khi in giúp thứ tự các authority trong stdout cố định.

**Giới hạn của chương trình:** thuật toán BFS minh họa có cơ chế visited để tránh lặp vô hạn, nhưng không kiểm tra cấu hình cycle như `RoleHierarchyImpl`; không có `Authentication` thật, JWT decoder hay Spring `AuthorizationManager`. Dùng nó để học **reachability**, sau đó cần kiểm thử manager và filter/method trong ứng dụng Spring thật.

## 9. Tích hợp nhất quán giữa HTTP, method và quyền đối tượng

### 9.1. HTTP và method không tự có chung một manager

Giả sử:

```text
HTTP rule: GET /api/reports/** -> hasAuthority("report:read")
Service:   @PreAuthorize("hasAuthority('report:read')")
User:      authorities trực tiếp [ROLE_ADMIN]
Hierarchy: ROLE_ADMIN > ROLE_READER > report:read
```

Nếu HTTP manager có hierarchy nhưng method expression handler không có, request có thể qua HTTP rồi bị 403 tại service. Ngược lại, nếu method hiểu hierarchy nhưng HTTP không, user có thể bị từ chối trước khi đến service.

Do đó cần test **hai lớp riêng**, không chỉ unit test `RoleHierarchy.getReachableGrantedAuthorities(...)`. Mục tiêu là cùng một principal, cùng policy chức năng thì các điểm kiểm tra dùng cùng ý nghĩa authority.

### 9.2. Một role cao không tự bỏ qua object-level authorization

Giả sử user có `ROLE_ADMIN` và hierarchy dẫn tới `report:read`, nhưng report 17 thuộc tenant khác. Quyết định cuối có thể là:

```text
ALLOW =
  authenticated
  AND reachedAuthority("report:read")
  AND sameTenant(principal, report)
  AND canReadThisReport(principal, report)
```

Không nên cho phép admin đọc mọi tenant chỉ vì từ “ADMIN” mang sắc thái quyền cao. Nếu hệ thống thực sự có global admin, cần policy rõ, phê duyệt, kiểm toán, MFA/step-up và test giới hạn dữ liệu.

### 9.3. SoD và quyền nhạy cảm

Role hierarchy là **quan hệ bao hàm**, không phải cơ chế xử lý xung đột vai trò hay phân tách nhiệm vụ. Nếu `ROLE_APPROVER > ROLE_CREATOR` trong một quy trình yêu cầu người tạo và người duyệt khác nhau, hierarchy có thể làm tăng tập quyền chức năng nhưng **không giải quyết** quy tắc “không được tự duyệt”.

Bắt buộc kiểm tra người thực hiện, người tạo, trạng thái/hạn mức và số cấp duyệt tại service/transaction. Đừng tạo một mega-role `ROLE_SUPERADMIN` bao trùm mọi quyền nhạy cảm chỉ để sửa một số 403, vì đây có thể là thay đổi đặc quyền nghiêm trọng.

### 9.4. JWT, nhóm và chính sách đa tenant

Nếu nguồn danh tính phát hành groups/roles theo tenant:

- Chỉ ánh xạ role sau khi đã xác thực issuer/audience và nguồn claim.
- Không ghép một role từ tenant A với quyền ứng dụng toàn cục nếu phạm vi role thực chỉ là tenant A.
- Không dùng scope JWT `SCOPE_reports.read` và role app `ROLE_READER` như hai tên đồng nghĩa trừ khi có mapping chính sách tường minh.
- Đừng để role hierarchy áp dụng gián tiếp cho mọi API/tenant nếu các nhóm cùng tên nhưng khác namespace.
- Nếu thông tin role được lưu trong session/JWT, cơ chế thu hồi quyền và cache phải được thiết kế riêng; đổi hierarchy hoặc group không tự làm token cũ biến mất.

Trong hệ thống phân quyền tinh vi, permission có phạm vi theo tenant nên được biểu diễn bằng policy/permission store rõ, không cố nhét mọi tenant vào một hierarchy global không có ngữ cảnh.

## 10. Kiểm thử để biết hierarchy đã thực sự đi vào manager nào

### 10.1. Ma trận chức năng

| Principal trực tiếp | Hierarchy mong đợi | Rule | Kết quả khi manager được nối đúng |
| --- | --- | --- | --- |
| `ROLE_ADMIN` | ADMIN ⇒ MANAGER ⇒ READER ⇒ `report:read` | `hasRole("MANAGER")` | Cho phép |
| `ROLE_ADMIN` | Như trên | `hasRole("READER")` | Cho phép |
| `ROLE_MANAGER` | MANAGER ⇒ READER ⇒ `report:read` | `hasAuthority("report:read")` | Cho phép |
| `ROLE_READER` | READER ⇒ `report:read` | `hasRole("ADMIN")` | Từ chối |
| `ROLE_AUDITOR` | AUDITOR ⇒ `audit:view` | `hasAuthority("report:read")` | Từ chối |
| `ROLE_UNKNOWN` | Không có cạnh | `hasRole("READER")` | Từ chối |
| `ROLE_ADMIN` | Như trên | `hasAuthority("report:approve")` | Từ chối |
| `ROLE_ADMIN` | Như trên | Đọc report ở tenant khác | Từ chối theo object policy |
| Chưa xác thực | Không có authority hợp lệ | Report endpoint bảo vệ | Không được vào |
| Role đúng nhưng account inactive | Phụ thuộc xác thực/trạng thái | Report endpoint bảo vệ | Không được tiếp tục theo chính sách |

Mỗi hàng có ý nghĩa **khi cùng graph và cùng manager thật sự sử dụng hierarchy**. Nếu kết quả khác, xác định manager nào đang thực thi chứ không vội thêm quyền vào principal.

### 10.2. Test graph độc lập

Với bean `RoleHierarchy`:

```java
Set<String> reached = roleHierarchy
    .getReachableGrantedAuthorities(
        List.of(new SimpleGrantedAuthority("ROLE_ADMIN"))
    )
    .stream()
    .map(GrantedAuthority::getAuthority)
    .collect(Collectors.toSet());

assertTrue(reached.contains("ROLE_MANAGER"));
assertTrue(reached.contains("ROLE_READER"));
assertTrue(reached.contains("report:read"));
assertFalse(reached.contains("report:approve"));
```

Đây là **fragment trong JUnit test**; cần import `RoleHierarchy`, `SimpleGrantedAuthority`, `GrantedAuthority`, `List`, `Set`, `Collectors` và assertions. Test này chỉ xác nhận định nghĩa hierarchy và không chứng minh HTTP/method đã áp dụng nó.

### 10.3. MockMvc kiểm tra HTTP decision

Trong ứng dụng Spring MVC có `spring-security-test`, có thể giả lập principal mang **chỉ ROLE_ADMIN** để xem rule `report:read` được hưởng qua hierarchy hay không.

```java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

// Trong @Test có MockMvc, controller và report fixture:
mockMvc.perform(get("/api/reports/17")
        .with(user("alice").roles("ADMIN")))
    .andExpect(status().isOk());
```

Test này chỉ trả 200 khi có controller, fixture, authentication và object policy phù hợp; trong sản phẩm thật, report 17 phải thuộc phạm vi của alice. `user(...).roles("ADMIN")` tạo authority `ROLE_ADMIN` ở test, không tự cấp `ROLE_READER`. **Nếu có 200 chỉ nhờ `ROLE_ADMIN` được expand trong manager**, đây là bằng chứng tích hợp có ích.

Tạo test đối chứng `roles("READER")` hoặc `roles("UNKNOWN")`; user không có quyền phải bị 403 khi đã xác thực, và phải xác nhận không có side effect. Với API JWT resource server, helper `jwt()` giả lập authorities không chứng minh chữ ký/audience thật, vì vậy cần test decoder riêng.

### 10.4. Test method security

Với bean service đã gắn:

```java
@PreAuthorize("hasAuthority('report:read')")
public ReportView readReport(long id) { ... }
```

Gọi trực tiếp qua Spring bean/proxy với `@WithMockUser(roles="ADMIN")`, `roles="READER"` và `roles="AUDITOR"`. Không test bằng cách new service ngoài Spring context hoặc tự gọi trong cùng instance, vì như vậy có thể không qua proxy.

Nếu HTTP test cho phép mà method test từ chối, kiểm tra `MethodSecurityExpressionHandler#setRoleHierarchy` và các bean cấu hình của phiên bản hiện dùng. Nếu method cho phép mà HTTP từ chối, kiểm tra manager do HTTP DSL tạo, custom factory và rule `.access(...)`.

### 10.5. Test chuyển phiên bản

Trước và sau nâng từ 6.x sang 7.x, cùng một test suite nên bao phủ:

1. User có role cao có được thừa hưởng quyền thấp đúng không?
2. User role thấp có **không** lấy được quyền cao không?
3. Custom HTTP managers có còn dùng cùng hierarchy không?
4. `@PreAuthorize`/`@Secured`/JSR-250 có còn thực thi đúng rule không?
5. Role prefix có bị đổi không, nhất là với `ROLE_` và `SCOPE_`?
6. Tenant, owner và quy trình duyệt có tiếp tục chặn khi hierarchy mở thêm quyền chức năng không?
7. Có lỗi compile do API `check`/`authorize` hoặc factory không tồn tại không?
8. Có rule nào trở thành `permitAll()` hoặc chỉ `authenticated()` khi refactor cấu hình không?
9. Việc thay đổi hierarchy có vượt số người được phép nhận quyền nhạy cảm không?
10. Đường xử lý ngoài HTTP (job, message consumer) có còn gọi chính sách service không?

## 11. Chẩn đoán 403 khi đã cấu hình hierarchy

Cách chẩn đoán không nên là “thêm `ROLE_READER` vào mọi user admin cho chắc”. Hãy đi theo chuỗi:

```text
Principal từ nguồn xác thực đáng tin?
  |
  v
Authentication.getAuthorities() có ROLE_ADMIN?
  |
  v
RoleHierarchy bean/graph có ADMIN > ... > report:read?
  |
  v
getReachableGrantedAuthorities([ROLE_ADMIN]) đúng?
  |
  v
Chốt đang gọi manager NÀO?
  |
  +-- HTTP DSL .hasAuthority(...)?
  +-- HTTP custom .access(manager)?
  +-- @PreAuthorize expression handler?
  +-- @Secured / JSR250?
  +-- Spring Security 7 factory?
  +-- Custom manager tự đọc raw authorities?
  |
  v
Manager ấy đã nhận cùng hierarchy?
  |
  v
Rule role prefix/authority string khớp?
  |
  v
Object policy tenant/owner/status cho phép?
  |
  v
ALLOW / DENY và ghi lý do phù hợp
```

### 11.1. Một số triệu chứng và nguyên nhân

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| Test `RoleHierarchy` pass, HTTP 403 | HTTP manager chưa gắn hierarchy | Kiểm tra `setRoleHierarchy`/factory/DSL |
| HTTP cho phép, `@PreAuthorize` từ chối | Method expression handler chưa nhận hierarchy | Kiểm tra `@EnableMethodSecurity` và handler |
| Role `ADMIN` không có `ROLE_ADMIN` | Sai convention/prefix | Đối chiếu GrantedAuthority và matcher |
| Manager cho role thấp quyền cao | Chiều `>` viết ngược hoặc mapping sai | Review graph và test deny |
| `ROLE_ADMIN` không bao hàm `report:approve` | Graph không có cạnh tới permission đó | Đây có thể là chính sách đúng |
| JWT chỉ có `SCOPE_reports.read` | Không có `ROLE_ADMIN` trong nguồn authorities | Kiểm tra mapper JWT và trust của claim |
| Custom manager vẫn 403 | Nó so raw `Authentication.getAuthorities()` | Tích hợp hierarchy trực tiếp hoặc dùng manager chuẩn |
| Chỉ một tenant bị 403 | Object policy/tenant scope | Không sửa global hierarchy để bỏ kiểm tra tenant |
| Nâng lên 7.x lỗi class/method | Dùng API 6.x lẫn 7.x | Chọn đúng factory/authorize API theo version |
| Đổi hierarchy nhưng session cũ vẫn có quyền | Phiên/token và quyền hiệu lực | Thiết kế refresh/revocation thích hợp |
| 403 trong POST dù role đúng | Có thể lỗi CSRF | Cô lập CSRF test và authorization test |

### 11.2. Log đúng và tránh rò rỉ

Log tối thiểu nên ghi correlation ID, tên rule, kết quả allow/deny, issuer đã xác minh (nếu liên quan), mã lý do, tenant theo chính sách. Không ghi raw JWT, mật khẩu, session cookie hoặc toàn bộ claims nhạy cảm. Không cần log toàn bộ graph ở mỗi request; cấu hình graph được version và kiểm toán riêng.

## 12. Lỗi thường gặp và bài học rút ra

| Lỗi | Hệ quả | Cách phòng tránh |
| --- | --- | --- |
| Có bean `RoleHierarchy` rồi tin mọi custom manager tự dùng | HTTP/method sai lệch | Gắn manager tường minh hoặc dùng factory phù hợp, test |
| Dùng `AuthorityAuthorizationManager.setRoleHierarchy` như API 7.x duy nhất | Chuyển phiên bản khó, bỏ qua factory mới | Dùng cấu hình theo API bản đã khóa |
| Sao chép `AuthorizationManagerFactory` vào 6.x | Không có class/API phù hợp | Factory được giới thiệu từ 7.0 |
| Dùng builder 6.3 trong Spring Security cũ hơn | Lỗi compile | Kiểm tra phiên bản, chọn API tồn tại |
| Dùng `hasRole("ROLE_ADMIN")` ở convention mặc định | Prefix không khớp/hợp đồng sai | `hasRole("ADMIN")` hoặc `hasAuthority("ROLE_ADMIN")` |
| Role hierarchy viết ngược chiều | Nâng quyền cho role thấp | Kiểm thử cả permit và deny |
| Trộn `SCOPE_` với `ROLE_` không có mapping | Scope được hiểu sai thành role | Phân biệt nguồn và chuyển đổi authority |
| Xây mega-role để “hết 403” | Mở quyền không cần thiết | Thiết kế permission tối thiểu, review bảo mật |
| Dựa vào hierarchy để vượt tenant | IDOR/BOLA | Kiểm tra tenant/owner tại service/data |
| Nghĩ hierarchy sửa `Authentication.getAuthorities()` | Debug nhầm trực tiếp/gián tiếp | Kiểm `getReachableGrantedAuthorities` và manager |
| Dùng custom manager raw loop mà quên graph | Không hưởng kế thừa | Gọi RoleHierarchy hoặc manager chuẩn |
| Chỉ unit test graph | Không biết HTTP/method có nối đúng | Integration tests từng chốt |
| Không kiểm tra self-invocation | Method annotation có thể không chạy | Test qua Spring AOP proxy |
| Vòng role cycle hoặc graph ngoài ý định | Cấu hình lỗi hoặc quyền rối | Validate graph, fail startup, review |
| Dùng hierarchy làm thay SoD | Tự phê duyệt/vi phạm workflow | Service policy độc lập |
| Thu hồi nhóm rồi tin JWT/session đã đổi ngay | Quyền cũ còn đến khi token/session hết hiệu lực | Revocation/TTL/authority reload |
| Thấy 403 liền đổi thành `authenticated()` | Mở đường truy cập nhạy cảm | Chẩn đoán manager, prefix, CSRF, object policy |

## 13. Quy trình triển khai thực tế

1. **Xác nhận phiên bản.** Dùng Maven/Gradle dependency tree hoặc BOM của dự án để xác nhận Spring Security 6.x hay 7.x. Không quyết định bằng tên Spring Boot một cách suy đoán.
2. **Thiết kế graph.** Viết các cạnh `ROLE_A > ROLE_B` và `ROLE_X > permission:y` với chủ sở hữu nghiệp vụ; xác định cấp bậc phù hợp và các quyền **không được** kế thừa.
3. **Chọn API tạo graph.** Spring 6.3+ có builder role prefix; `fromHierarchy(String)` rõ ràng cho chuỗi authority đầy đủ.
4. **Tích hợp HTTP.** Với Spring Security 6.x khi tự xây manager, nối `setRoleHierarchy` và đưa manager vào `.access(...)`. Với 7.x, cấu hình factory theo tài liệu và xác minh manager DSL thật sự dùng factory ấy.
5. **Tích hợp method.** Bật `@EnableMethodSecurity`, cấu hình expression handler/manager phù hợp, kiểm thử `@PreAuthorize`.
6. **Kiểm tra prefix.** Phân biệt role `ROLE_`, JWT scope `SCOPE_` và permission raw.
7. **Giữ object policy.** Thiết kế tenant/owner/share/status/SoD; không để role graph trở thành quyền toàn cục ngoài ý định.
8. **Kiểm thử trực tiếp graph.** Xác nhận reachable set đúng và không có quan hệ cấm.
9. **Kiểm thử HTTP + method.** Test đủ quyền, quyền thấp, role lạ, sai tenant, user chưa xác thực và hành động nhạy cảm.
10. **Quản trị thay đổi.** Role hierarchy là chính sách cấp quyền; cần review, CI regression, audit và rollback khi triển khai.
11. **Giám sát và thu hồi.** Kiểm tra phiên/JWT/cache, vòng đời quyền và lịch sử thay đổi; phản ứng khi role bị thu hồi hoặc graph thay đổi.
12. **Đánh giá sau nâng cấp.** Đọc JavaDoc đúng version về factory, method `check/authorize` và manager có áp dụng hierarchy hay không.

## 14. Bài tập củng cố

### Bài 1 — Dự đoán quyền bắc cầu

Cho graph `ROLE_ADMIN > ROLE_MANAGER > ROLE_READER > report:read`, dự đoán tập authorities của user chỉ có `ROLE_MANAGER`. Tìm những authority **không** được kế thừa. Sau đó chạy chương trình `RoleHierarchyManagerDemo.java` và so sánh.

### Bài 2 — HTTP manager có và không có hierarchy

Trên Spring Security 6.5, tạo hai `AuthorityAuthorizationManager<Object>` cùng yêu cầu `report:read`. Chỉ gọi `setRoleHierarchy` cho một cái. Dùng principal chỉ có `ROLE_ADMIN` và kiểm tra quyết định của cả hai. Đạt khi test chứng minh sự khác biệt là do cấu hình manager.

### Bài 3 — Method khác HTTP

Dùng cấu hình 6.5, đặt `@PreAuthorize("hasAuthority('report:read')")` lên service. Tạo test HTTP có role admin được phép nhưng method có thể bị từ chối nếu expression handler không được nối. Sửa handler đúng và chạy cả hai test. **Không mở quyền HTTP để làm test pass.**

### Bài 4 — Thử cấu hình Spring Security 7

Nếu dự án đang ở 7.x, tạo bean `AuthorizationManagerFactory<T>` với `DefaultAuthorizationManagerFactory<T>.setRoleHierarchy(...)`. Kiểm thử cùng user và cùng hierarchy trên HTTP và method; xác minh chốt custom ngoài factory không tự được thay đổi. Không sao chép lớp config 6.x vào project 7.x.

### Bài 5 — Thêm permission nhạy cảm

Giả sử muốn bổ sung `report:approve` cho role quản lý. Liệt kê rủi ro, các user được hưởng gián tiếp, ảnh hưởng đến quy trình “người tạo khác người duyệt”, test deny và cách rollback. Giải thích vì sao thêm một cạnh hierarchy có thể ảnh hưởng hàng nghìn user dù không sửa bảng membership.

### Bài 6 — Kiểm tra tenant và quyền nguồn

Người dùng admin tenant A có `ROLE_ADMIN` và do hierarchy được `report:read`. Hãy viết policy readReport(id) chỉ lấy báo cáo thuộc tenant được xác minh. Test rằng report tenant B bị từ chối, dù manager HTTP và method đều cho phép quyền chức năng.

## 15. Tự kiểm tra cuối bài

1. **`RoleHierarchy` làm gì?** Tính tập quyền có thể đạt tới từ những authority đã cấp theo quan hệ bao hàm.
2. **Khai báo bean hierarchy có bảo đảm mọi custom manager tự dùng không?** Không; phải biết manager nào đang thực hiện và cách nó được cấu hình.
3. **Spring Security 6.x có cách gắn tường minh nào?** Với `AuthorityAuthorizationManager`, dùng `setRoleHierarchy(...)`; dùng `.access(manager)` để bảo đảm HTTP rule dùng manager ấy.
4. **Spring Security 7.0+ có thành phần mới gì?** `AuthorizationManagerFactory<T>` và `DefaultAuthorizationManagerFactory<T>` phục vụ tạo manager dùng cấu hình chung.
5. **Builder `withDefaultRolePrefix()` có từ bản nào?** Theo JavaDoc, từ Spring Security 6.3.
6. **`hasRole("READER")` thường kiểm tra gì?** `ROLE_READER` theo convention mặc định, có thể hưởng role gián tiếp nếu manager áp dụng hierarchy.
7. **Người có `ROLE_MANAGER` có tự đạt `ROLE_ADMIN` khi graph ADMIN > MANAGER không?** Không; quan hệ đi từ trên xuống.
8. **Có `ROLE_ADMIN` có nghĩa `Authentication.getAuthorities()` luôn chứa `ROLE_READER`?** Không; hierarchy có thể chỉ được dùng trong lúc đánh giá manager.
9. **Scope JWT `SCOPE_reports.read` có tự thành `ROLE_READER` không?** Không; cần mapping được phê duyệt nếu chính sách muốn liên kết.
10. **Hierarchy có thay kiểm tra tenant, owner và phân tách nhiệm vụ không?** Không.
11. **Nếu HTTP cho qua nhưng method 403, kiểm tra gì?** Expression handler/manager method, role hierarchy wiring, prefix và object policy.
12. **Chỉ test `getReachableGrantedAuthorities` đã đủ không?** Không; còn phải test HTTP, method và dữ liệu.
13. **Có nên thêm admin vào mọi biểu thức để sửa 403?** Không; phải tìm nguyên nhân và giữ nguyên quyền tối thiểu.
14. **Thay hierarchy ảnh hưởng user nào?** Bất kỳ user có role dẫn tới các authority mới, kể cả gián tiếp; cần phân tích phạm vi và test hồi quy.
15. **Nâng 6.x lên 7.x cần nhớ gì?** Kiểm tra factory mới, API quyết định manager, expression handler và bảo đảm chính sách thực tế không đổi ngoài ý muốn.

**Ghi nhớ:** định nghĩa `ROLE_ADMIN > ROLE_USER` mới chỉ là **chính sách quan hệ**. Để quyền kế thừa hoạt động, **AuthorizationManager đang thực hiện quyết định phải sử dụng hierarchy ấy**. Với 6.x có thể nối tường minh vào `AuthorityAuthorizationManager` và method expression handler; với 7.x có `AuthorizationManagerFactory` mới để thống nhất nhiều manager. Dù dùng phiên bản nào, hierarchy chỉ giải quyết quyền chức năng **theo chiều kế thừa đã khai báo**, không thay thế xác thực nguồn, tenant/object policy, SoD hoặc kiểm thử quyền bị từ chối.

### Tài liệu chính thức để kiểm chứng theo phiên bản

- [Spring Security 6.5 – Authorization Architecture / Hierarchical Roles](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/architecture.html)
- [Spring Security 6.5 – AuthorityAuthorizationManager API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/AuthorityAuthorizationManager.html)
- [Spring Security 6.5 – RoleHierarchyImpl API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/access/hierarchicalroles/RoleHierarchyImpl.html)
- [Spring Security 6.5 – Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html)
- [Spring Security 7.0+ – Authorization Architecture / AuthorizationManagerFactory](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html)
- [Spring Security 7.0+ – Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)