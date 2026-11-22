# hasAnyAuthority, hasAnyRole và kiểm tra một trong nhiều quyền trong Spring Security

## Mục tiêu

Sau bài học, bạn có thể phân biệt `hasAnyAuthority` với `hasAnyRole`, diễn giải đúng điều kiện **“có ít nhất một trong các quyền được liệt kê”**, sử dụng hai API khi cấu hình HTTP và `@PreAuthorize`, xử lý tiền tố `ROLE_`, ghép điều kiện OR/AND theo chính sách nghiệp vụ, và kiểm thử những ca có quyền/thiếu quyền trong Spring Security trên Servlet stack.

## 1. “Một trong nhiều quyền” nghĩa là gì?

Trong Spring Security, `Authentication` đại diện người đang được xác thực. Danh sách `GrantedAuthority` của nó chứa các **chuỗi quyền đã cấp**, chẳng hạn:

```text
report:read
report:export
ROLE_EDITOR
ROLE_ADMIN
SCOPE_profile
```

Một chính sách có thể cho phép đọc báo cáo khi người gọi sở hữu **quyền xem** `report:read` **hoặc** **quyền xuất** `report:export`. Đây là phép **OR**: chỉ cần **một điều kiện đúng**. Với tập quyền thực tế `G` và tập quyền được chấp nhận `R`, điều kiện tổng quát là:

```text
allow = tồn tại r thuộc R sao cho r thuộc G

Ví dụ:
G = {"report:read", "ROLE_SUPPORT"}
R = {"report:read", "report:export"}

G ∩ R = {"report:read"}  =>  ALLOW
```

**Không cần có tất cả các quyền** trong `R`. Nếu người dùng không có quyền nào khớp, điều kiện thất bại. Đây chỉ là **một điều kiện phân quyền**: request vẫn có thể bị từ chối bởi rule khác, thiếu xác thực, kiểm tra sở hữu tài nguyên hoặc CSRF.

### Bảng quyết định

Giả sử ứng dụng sử dụng những authority chính xác ở cột đầu và chưa cấu hình role hierarchy:

| GrantedAuthority của người dùng | `hasAnyAuthority("report:read", "report:export")` | `hasAnyRole("EDITOR", "ADMIN")` |
| --- | --- | --- |
| `report:read` | **true** | **false** |
| `report:export` | **true** | **false** |
| `report:read`, `report:export` | **true** | **false** |
| `ROLE_EDITOR` | **false** | **true** |
| `ROLE_ADMIN`, `report:read` | **true** | **true** |
| `ROLE_SUPPORT` | **false** | **false** |
| Không có authority nào | **false** | **false** |

Từ bảng có thể thấy quyền chức năng kiểu `report:read` và role kiểu `ROLE_EDITOR` không tự động tương đương. Spring Security không suy ra “người có `ROLE_ADMIN` đương nhiên có `report:read`”, trừ khi ứng dụng **cấp cả hai authority** hoặc cấu hình cơ chế như role hierarchy một cách tường minh.

## 2. hasAnyAuthority: khớp một trong nhiều authority

`hasAnyAuthority("a", "b", ...)` trả kết quả cho phép nếu `Authentication` có **ít nhất một** `GrantedAuthority` trùng với một chuỗi được truyền vào, theo cách đánh giá của bộ phân quyền đang sử dụng.

Ví dụ:

```java
// Trong authorizeHttpRequests:
.requestMatchers(HttpMethod.GET, "/api/reports/**")
    .hasAnyAuthority("report:read", "report:export")
```

Ý nghĩa: mọi request `GET` khớp đường dẫn này phải có **`report:read` HOẶC `report:export`**. Người chỉ có `report:read` vẫn đủ; người chỉ có `report:export` cũng đủ. Nếu quyền thực tế tên `SCOPE_report.read` mà policy kiểm tra `report:read`, hai chuỗi **không khớp**, dù con người cho rằng ý nghĩa tương tự.

### So với hasAuthority

| Biểu thức | Điều kiện |
| --- | --- |
| `hasAuthority("report:read")` | Phải có đúng `report:read` |
| `hasAnyAuthority("report:read", "report:export")` | Có `report:read` **hoặc** `report:export` (hoặc cả hai) |
| `hasAuthority("report:read") and hasAuthority("report:export")` | Phải có **cả hai** |
| `hasAuthority("report:read") or hasAuthority("report:export")` | Tương đương ý tưởng của `hasAnyAuthority` trong ví dụ hai quyền |

Khi bạn muốn “**chỉ một trong các quyền là đủ**”, nên dùng `hasAnyAuthority` vì ngắn và truyền tải đúng mục tiêu. Khi chính sách yêu cầu **đồng thời hai quyền**, dùng phép `and` trong SpEL hoặc một `AuthorizationManager` kết hợp theo AND phù hợp, **không dùng `hasAnyAuthority`**.

**Lưu ý bảo mật:** chọn danh sách các quyền thay thế có **cùng mức truy cập được chấp nhận cho thao tác đó**. Ví dụ, cho `report:export` thay thế `report:read` là một quyết định nghiệp vụ có chủ đích. Nếu `report:export` phải bảo vệ nghiêm hơn, không thể tự ý suy ra nó thay thế quyền xem trong mọi endpoint.

## 3. hasAnyRole: khớp một trong nhiều role

`hasAnyRole("EDITOR", "ADMIN")` là cách viết dành cho role. Với cấu hình mặc định, Spring Security diễn giải thành yêu cầu có ít nhất một authority:

```text
ROLE_EDITOR
ROLE_ADMIN
```

Tiền tố mặc định là **`ROLE_`**. Vì vậy:

```java
.requestMatchers(HttpMethod.POST, "/api/reports/**")
    .hasAnyRole("EDITOR", "ADMIN")
```

Có cùng ý định mặc định với:

```java
.requestMatchers(HttpMethod.POST, "/api/reports/**")
    .hasAnyAuthority("ROLE_EDITOR", "ROLE_ADMIN")
```

### Phân biệt chuỗi truyền vào

| Dữ liệu thực trong `Authentication.getAuthorities()` | Biểu thức | Kết quả mặc định |
| --- | --- | --- |
| `ROLE_EDITOR` | `hasAnyRole("EDITOR", "ADMIN")` | Cho phép |
| `ROLE_EDITOR` | `hasAnyAuthority("ROLE_EDITOR", "ROLE_ADMIN")` | Cho phép |
| `ROLE_EDITOR` | `hasAnyAuthority("EDITOR", "ADMIN")` | Từ chối |
| `EDITOR` | `hasAnyRole("EDITOR", "ADMIN")` | Từ chối |
| `report:read` | `hasAnyRole("EDITOR", "ADMIN")` | Từ chối |

**Quy tắc dễ nhớ:** với quy ước `ROLE_` mặc định, truyền `"EDITOR"`, `"ADMIN"` vào `hasAnyRole`; dùng **đúng chuỗi có tiền tố** khi gọi `hasAnyAuthority`. Đừng truyền `"ROLE_EDITOR"` vào `hasAnyRole` để “chắc ăn”: đây không phải dạng gọi được khuyến nghị và một số biến thể API kiểm tra/không chấp nhận tiền tố có sẵn.

Có thể tùy chỉnh role prefix bằng cấu hình Spring Security; khi đó phải đảm bảo **nơi cấp quyền, nơi kiểm tra và test** đều cùng một quy ước. Nếu dùng **RoleHierarchy** (ví dụ quản trị viên thừa hưởng authority của người biên tập), kết quả có thể dựa vào authority hiệu lực sau khi áp dụng hierarchy; bảng trên giả định chưa có hierarchy.

### “Role” có phải kiểu dữ liệu riêng trong Spring Security?

Ở tầng quyết định cơ bản, role thường được biểu diễn thành `GrantedAuthority` bắt đầu bằng `ROLE_`. `hasAnyRole` cung cấp **cú pháp tiện dụng** và quy ước tiền tố. Việc gán `ROLE_ADMIN` cho người dùng **không tự biến thành mọi quyền khác**. Ứng dụng phải cấp các authority nghiệp vụ, định nghĩa mapping từ nhóm/role hoặc cấu hình hierarchy.

## 4. Áp dụng hai lựa chọn ở mức HTTP

Trong ứng dụng Spring Boot dùng Spring Security Servlet, các rule được đặt trong `SecurityFilterChain`. Cấu hình đầy đủ cho phần authorization dưới đây sử dụng cú pháp Spring Security 6.x:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
            // Endpoint công khai
            .requestMatchers("/actuator/health").permitAll()

            // Có ít nhất một trong hai authority được chấp nhận
            .requestMatchers(HttpMethod.GET, "/api/reports/**")
                .hasAnyAuthority("report:read", "report:export")

            // Có ít nhất một trong hai role được chấp nhận
            .requestMatchers(HttpMethod.POST, "/api/reports/**")
                .hasAnyRole("EDITOR", "ADMIN")

            // Không công khai endpoint chưa có policy
            .anyRequest().denyAll()
        );
        // Chỉ minh họa một cơ chế authentication:
        http.httpBasic(Customizer.withDefaults());
        return http.build();
    }
}
```

Để chạy trong dự án thực, cần dependency Spring Security, cơ chế cấp `Authentication`/authorities và cấu hình session/token/CSRF phù hợp. Ví dụ trên **không tự tạo** users, roles, nguồn dữ liệu hoặc REST controller. `httpBasic` chỉ giúp đặt ví dụ vào một khung xác thực dễ hiểu; sản phẩm có thể dùng form login, session hoặc OAuth2 Resource Server.

Phân tích từng request:

| Request | GrantedAuthority của người gọi | Quyết định ở tầng HTTP |
| --- | --- | --- |
| `GET /api/reports/8` | `report:read` | Qua rule GET |
| `GET /api/reports/8` | `report:export` | Qua rule GET |
| `GET /api/reports/8` | `ROLE_ADMIN` | Bị từ chối: GET cần authority `report:read` hoặc `report:export` |
| `POST /api/reports` | `ROLE_EDITOR` | Qua rule POST |
| `POST /api/reports` | `ROLE_ADMIN` | Qua rule POST |
| `POST /api/reports` | `report:read` | Bị từ chối: POST cần role EDITOR hoặc ADMIN |
| `DELETE /api/reports/8` | Bất kỳ | `denyAll` theo cấu hình này |

**“Qua rule” không bảo đảm HTTP 2xx.** Request còn phụ thuộc đăng nhập, controller, validation, business rule, dữ liệu, CSRF và những lớp bảo vệ khác. Ví dụ `POST` với Basic authentication có thể bị `403` do CSRF token trong cấu hình yêu cầu CSRF, dù có `ROLE_EDITOR`.

### Thứ tự matcher và OR có mục đích

Trong `authorizeHttpRequests`, các rule được xét **theo thứ tự** và request dùng luật khớp đầu tiên. Không nên viết hai matcher y hệt để kỳ vọng cộng dồn quyền:

```java
// SAI nếu muốn "report:read HOẶC report:export":
.requestMatchers(HttpMethod.GET, "/api/reports/**")
    .hasAuthority("report:read")
.requestMatchers(HttpMethod.GET, "/api/reports/**")
    .hasAuthority("report:export")
```

Matcher đầu đã khớp thì matcher thứ hai không làm phương án dự phòng. Viết thành **một rule**:

```java
// ĐÚNG với chính sách OR:
.requestMatchers(HttpMethod.GET, "/api/reports/**")
    .hasAnyAuthority("report:read", "report:export")
```

Đặt đường dẫn đặc thù trước `/api/**` hoặc `/**` để tránh rule rộng che mất rule hẹp. `anyRequest().denyAll()` bảo đảm endpoint mới không tự được cấp quyền chỉ vì chưa có matcher.

## 5. Áp dụng trong method security

Không phải mọi lời gọi service đều đi qua HTTP controller: còn job nền, message consumer, lịch chạy hoặc service khác. Vì vậy, có thể kiểm tra quyền ngay **trước khi gọi method nghiệp vụ** bằng `@PreAuthorize`.

### 5.1. Hai ví dụ cơ bản

```java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class ReportPermissionService {

    @PreAuthorize("hasAnyAuthority('report:read', 'report:export')")
    public String viewSummary() {
        return "Report summary";
    }

    @PreAuthorize("hasAnyRole('EDITOR', 'ADMIN')")
    public String createDraft() {
        return "Draft created";
    }
}
```

Ứng dụng phải bật `@EnableMethodSecurity` trong configuration. Khi Spring-managed proxy nhận lời gọi `viewSummary()`, người gọi cần `report:read` **hoặc** `report:export`. Với `createDraft()`, người gọi cần `ROLE_EDITOR` **hoặc** `ROLE_ADMIN` theo quy ước mặc định.

Hai kiểm tra ở đây thuộc **hai method khác nhau**; không có ý nghĩa “người dùng cần vừa role vừa authority”. Chỉ khi viết biểu thức phối hợp hoặc thêm các lớp bảo vệ khác, bạn mới có điều kiện bổ sung.

### 5.2. Kết hợp “một trong nhiều quyền” với ràng buộc bắt buộc

Một nghiệp vụ đọc báo cáo riêng tư có thể cho phép hai authority thay thế nhau **nhưng vẫn phải đúng tenant và quyền sở hữu**:

```java
@PreAuthorize(
    "hasAnyAuthority('report:read', 'report:export') and " +
    "@reportAccess.canRead(authentication, #reportId)"
)
public Report read(@P("reportId") long reportId) {
    return repository.findById(reportId).orElseThrow();
}
```

Đây là **mã tích hợp minh họa** trong service Spring: `Report`, `repository` và bean `reportAccess` do ứng dụng định nghĩa. `@P` thuộc `org.springframework.security.access.method.P` để cung cấp tên biến `#reportId` cho SpEL, tránh phụ thuộc compiler giữ tên tham số. Bean `reportAccess` phải kiểm tra tenant/owner/share dựa trên bản ghi từ server, không chỉ kiểm tra người dùng biết ID.

Logic của biểu thức là:

```text
ALLOW =
    (report:read OR report:export)
    AND policy.canRead(currentUser, reportId)
```

Khác với:

```java
// Chỉ phù hợp nếu nghiệp vụ CHO PHÉP bỏ qua kiểm tra object
// khi có role ADMIN:
@PreAuthorize(
    "hasAnyAuthority('report:read', 'report:export') or hasRole('ADMIN')"
)
```

Biểu thức `or hasRole('ADMIN')` làm admin bỏ qua nhánh kiểm tra khác nếu bạn đưa chính sách ở nhánh OR sai vị trí. Với hệ thống đa tenant, phải quyết định tường minh admin có được truy cập chéo tenant hay không. Nếu mọi người đều phải tuân thủ tenant, đặt `sameTenant` ở nhánh `AND` chung, kể cả admin.

### 5.3. Các giới hạn cần nắm

- `@EnableMethodSecurity` phải được bật tường minh. Có annotation `@PreAuthorize` trong source code không bảo đảm hệ thống thực sự kiểm tra nếu chưa bật method security.
- Các interceptor thông thường dùng Spring AOP proxy; `this.viewSummary()` trong **cùng bean** thường bỏ qua proxy, còn đối tượng tạo bằng `new` bên ngoài container không được Spring bảo vệ.
- `@PreAuthorize` được kiểm tra **trước** method. `@PostAuthorize` kiểm tra **sau** khi method trả về, không dùng làm cổng bảo vệ duy nhất cho lệnh có side effect.
- Nếu nhiều annotation loại khác nhau cùng áp dụng, mỗi bộ kiểm tra có thể tạo thêm điều kiện cần đạt; đừng mặc định chúng gộp theo OR. Không lặp nhiều `@PreAuthorize` trên cùng method để “đủ quyền nào thì qua”.
- Nếu gọi service ngoài HTTP request, việc gắn `Authentication` cho worker/job cần được thiết kế rõ ràng; thiếu security context thường dẫn đến bị từ chối, không tự cho phép.

## 6. Mã Java 17 độc lập mô phỏng phép kiểm tra

Ví dụ sau dùng `Set<String>` mô phỏng danh sách GrantedAuthority. Nó minh họa **ý nghĩa logic** của `hasAnyAuthority` và quy ước tiền tố role mặc định, **không thay thế** implementation của Spring Security; không xét role hierarchy, cấu hình prefix tùy biến hay tình trạng authentication.

Lưu đúng tên **`AnyRightsDemo.java`**:

```java
import java.util.Arrays;
import java.util.Set;

public class AnyRightsDemo {

    static boolean hasAnyAuthority(Set<String> granted, String... required) {
        return Arrays.stream(required).anyMatch(granted::contains);
    }

    static boolean hasAnyRole(Set<String> granted, String... roles) {
        return Arrays.stream(roles)
            .map(role -> "ROLE_" + role)
            .anyMatch(granted::contains);
    }

    public static void main(String[] args) {
        Set<String> granted = Set.of(
            "report:read",
            "ROLE_SUPPORT",
            "SCOPE_profile"
        );

        System.out.println("Read or export: "
            + hasAnyAuthority(granted, "report:read", "report:export"));

        System.out.println("Edit or delete: "
            + hasAnyAuthority(granted, "report:edit", "report:delete"));

        System.out.println("Support or admin role: "
            + hasAnyRole(granted, "SUPPORT", "ADMIN"));

        System.out.println("Editor or admin role: "
            + hasAnyRole(granted, "EDITOR", "ADMIN"));

        System.out.println("Authority without ROLE_ prefix: "
            + hasAnyAuthority(granted, "SUPPORT", "ADMIN"));

        System.out.println("OAuth scope authority exact match: "
            + hasAnyAuthority(granted, "SCOPE_profile", "SCOPE_email"));

        System.out.println("Empty granted authorities: "
            + hasAnyAuthority(Set.of(), "report:read", "report:export"));
    }
}
```

Chạy bằng **JDK 17 trở lên**:

```bash
javac AnyRightsDemo.java
java AnyRightsDemo
```

**Stdout chính xác**:

```text
Read or export: true
Edit or delete: false
Support or admin role: true
Editor or admin role: false
Authority without ROLE_ prefix: false
OAuth scope authority exact match: true
Empty granted authorities: false
```

Giải thích: `granted` chỉ có `report:read`, nên policy đầu trả `true` mà không cần `report:export`. Nó có `ROLE_SUPPORT`, nên `hasAnyRole("SUPPORT", "ADMIN")` là `true`. Nhưng chuỗi `"SUPPORT"` không nằm trong `GrantedAuthority`: `hasAnyAuthority("SUPPORT", "ADMIN")` phải là `false`. `SCOPE_profile` được nhận ra vì ta kiểm tra **đúng chuỗi**, không có bước tự chuyển nó thành role.

## 7. Chuỗi authority đến từ đâu?

### 7.1. In-memory users và UserDetails

Nếu dùng `UserDetails`, bạn có thể cấp authority trực tiếp:

```java
UserDetails reader = User.withUsername("reader")
    .password("{noop}demo-password")
    .authorities("report:read", "ROLE_SUPPORT")
    .build();
```

Đây là snippet mô tả cách gán quyền cho user học tập, cần import `UserDetails` và `User` từ `org.springframework.security.core.userdetails`. `{noop}` chỉ để biểu diễn dữ liệu thử nghiệm; không dùng mật khẩu mẫu và encoder NoOp cho tài khoản production. Khi dùng `.roles("SUPPORT")` trong builder mặc định, builder tạo authority `ROLE_SUPPORT`; nếu muốn kiểm soát chuỗi chính xác có tiền tố hoặc tên quyền nghiệp vụ, dùng `.authorities(...)` phù hợp.

### 7.2. JWT/OAuth2 Resource Server

Trong nhiều cấu hình OAuth2 Resource Server, Spring Security ánh xạ scope của token thành authority có tiền tố `SCOPE_`; ví dụ scope `report.read` có thể trở thành `SCOPE_report.read`. Vì vậy:

```java
.hasAnyAuthority("SCOPE_report.read", "SCOPE_report.export")
```

chỉ hoạt động đúng khi converter thực tế sinh những chuỗi này. Nếu hệ thống muốn dùng `report:read` hoặc `ROLE_EDITOR` từ claim tùy biến, phải định nghĩa mapping/converter từ claim sang `GrantedAuthority` một cách nhất quán. Không mặc định “có claim role=EDITOR” đồng nghĩa với “đã có authority ROLE_EDITOR”; việc ánh xạ phụ thuộc cấu hình xác thực.

**Cách chẩn đoán đúng:** xem tập `GrantedAuthority` đã được server xác thực và ánh xạ, so sánh **chính xác** với chuỗi trong rule; dùng log an toàn ở môi trường phát triển, không ghi access token hoặc thông tin nhạy cảm vào log. Tránh tự bổ sung role chỉ dựa trên trường do client gửi.

### 7.3. Role prefix và hierarchy

Theo mặc định, phương thức role kiểm tra tiền tố `ROLE_`. Nếu ứng dụng tùy chỉnh role prefix, cách đánh giá có thể khác quy ước thông thường. Role hierarchy có thể mở rộng authority hiệu lực, ví dụ `ROLE_ADMIN` được khai báo thừa hưởng `ROLE_EDITOR`; khi đó chính sách yêu cầu EDITOR có thể cho ADMIN qua dù danh sách ban đầu không chứa trực tiếp `ROLE_EDITOR`. Việc này đòi hỏi **cấu hình hierarchy** được tích hợp với bộ đánh giá tương ứng, không được giả định chỉ vì có hai role trông giống quan hệ cha–con.

## 8. Khi nào dùng OR, khi nào dùng AND?

**Dùng OR** khi các quyền là **phương án thay thế thực sự** cho cùng hành động:

```text
Xem báo cáo tổng hợp:
    report:read OR report:export

Truy cập trang hỗ trợ:
    ROLE_SUPPORT OR ROLE_ADMIN
```

**Dùng AND** khi nghiệp vụ đòi **đồng thời** các điều kiện:

```text
Duyệt khoản thanh toán:
    payment:approve
    AND MFA đã hoàn tất
    AND sameTenant
    AND NOT requesterIsApprover
```

`hasAnyAuthority("payment:approve", "mfa:verified")` sẽ **sai** trong tình huống này: người chỉ có `mfa:verified` cũng được cho qua. Thay vào đó, dùng `hasAuthority("payment:approve") and ...` cùng điều kiện MFA và dữ liệu thật; MFA là trạng thái xác thực/bối cảnh cần được xác minh, không nên tự tin tưởng một chuỗi authority do client gửi.

### Kết hợp authority và role

Trong method security có thể viết:

```java
@PreAuthorize(
    "hasAnyRole('SUPPORT', 'ADMIN') and " +
    "hasAnyAuthority('ticket:read', 'ticket:manage')"
)
```

Nghĩa là **(SUPPORT hoặc ADMIN) VÀ (ticket:read hoặc ticket:manage)**. Người dùng chỉ có `ROLE_ADMIN` nhưng không có authority ticket phù hợp **không qua** kiểm tra này, trừ khi hệ thống cấu hình cấp quyền thừa kế/tương ứng. Nếu muốn **role admin là ngoại lệ** cho một phần chính sách, hãy đặt dấu ngoặc và định nghĩa rõ những kiểm tra nào admin vẫn phải tuân thủ.

Nếu quyền truy cập còn phụ thuộc **tenant, owner, status** của bản ghi, `hasAnyAuthority` hoặc `hasAnyRole` chỉ giải quyết bước kiểm tra tập quyền. Hãy kết hợp policy riêng với `@PreAuthorize`/`AuthorizationManager` hoặc query có điều kiện; không coi quyền vào URL đồng nghĩa quyền đọc mọi ID.

## 9. Kiểm thử bằng bảng ca và Spring Security Test

Đừng chỉ test trường hợp có cả hai quyền. Phải kiểm tra từng phương án độc lập và người hoàn toàn không có quyền.

| Tình huống | Endpoint GET cần `report:read` hoặc `report:export` | Endpoint POST cần role EDITOR hoặc ADMIN |
| --- | --- | --- |
| Chỉ `report:read` | Cho qua quyền | Bị từ chối |
| Chỉ `report:export` | Cho qua quyền | Bị từ chối |
| Cả hai authority báo cáo | Cho qua quyền | Bị từ chối nếu không có role |
| Chỉ `ROLE_EDITOR` | Bị từ chối | Cho qua quyền |
| Chỉ `ROLE_ADMIN` | Bị từ chối | Cho qua quyền |
| Chỉ `ROLE_SUPPORT` | Bị từ chối | Bị từ chối |
| Không xác thực | Từ chối theo cơ chế authentication | Từ chối theo cơ chế authentication |
| Có quyền cơ sở nhưng truy cập bản ghi tenant khác | HTTP rule có thể cho qua | Business/object policy vẫn phải chặn |

Với `spring-security-test` và `MockMvc`, có thể tạo principal kiểm thử:

```java
@WithMockUser(authorities = {"report:read"})
// Kiểm thử GET /api/reports/8: vượt qua kiểm tra quyền HTTP.

@WithMockUser(authorities = {"report:export"})
// Cũng vượt qua kiểm tra quyền HTTP GET.

@WithMockUser(roles = {"EDITOR"})
// Có authority ROLE_EDITOR; vượt qua kiểm tra role của POST.

@WithMockUser(authorities = {"ROLE_ADMIN"})
// Cũng vượt qua kiểm tra role của POST theo prefix mặc định.
```

Đây là **các cấu hình annotation cho từng test**, không phải một class Java độc lập để biên dịch nguyên đoạn. Trong test thực, đặt **mỗi** `@WithMockUser` lên method test riêng. `roles = {"EDITOR"}` mặc định thêm `ROLE_`; `authorities = {"ROLE_ADMIN"}` sử dụng chuỗi có sẵn. Test `POST` phải xử lý CSRF theo cấu hình (ví dụ `with(csrf())` nếu hệ thống bật CSRF), nếu không có thể nhận `403` vì thiếu token dù role đúng.

Ngoài status HTTP, kiểm tra service được gọi khi được phép, **không được gọi khi bị từ chối**, và dữ liệu không bị thay đổi ở trường hợp bị từ chối. Đối với method security, phải gọi **Spring bean thực qua proxy**, không tự gọi method trên object tạo bằng `new` rồi khẳng định annotation đã hoạt động.

### Phân biệt các nguyên nhân bị từ chối

- **401** thường là thiếu thông tin xác thực hợp lệ với cơ chế entry point yêu cầu đăng nhập.
- **403** thường là đã xác thực nhưng không đủ authority/role; cũng có thể do CSRF hoặc kiểm tra phân quyền ở tầng khác.
- Rule ở HTTP đạt nhưng service bị `AccessDeniedException` là **hai lớp kiểm tra** đang hoạt động, không có nghĩa `hasAnyAuthority` sai.
- Controller trả **404** vì bản ghi không tồn tại hoặc chính sách ẩn sự tồn tại dữ liệu là quyết định xử lý API riêng.

Kết quả HTTP cụ thể tùy cơ chế authentication, exception handling, CSRF và các policy khác; test phải đặt đúng ngữ cảnh thay vì coi mọi `403` là lỗi role.

## 10. Các lỗi thường gặp và cách tránh

1. **Nhầm “any” với “all”:** `hasAnyAuthority("a", "b")` cho qua khi chỉ có `a`. Nếu cần cả hai, dùng điều kiện AND rõ ràng.
2. **Bỏ quên tiền tố role:** `hasAnyRole("ADMIN", "EDITOR")` kiểm tra `ROLE_ADMIN`/`ROLE_EDITOR` mặc định; `hasAnyAuthority("ADMIN", "EDITOR")` kiểm tra hai chuỗi hoàn toàn khác.
3. **Truyền `ROLE_ADMIN` vào `hasAnyRole`:** nên truyền tên role chưa có tiền tố với cấu hình mặc định để tránh lỗi hoặc diễn giải không thống nhất.
4. **Tưởng role tự chứa mọi authority nghiệp vụ:** `ROLE_ADMIN` không tự trở thành `report:read` nếu chưa cấp quyền hoặc cấu hình hierarchy.
5. **Giả định scope trong JWT có cùng tên với authority yêu cầu:** kiểm tra mapping `SCOPE_`/claim converter và chuỗi thực trong `Authentication`.
6. **Tách hai matcher y hệt để tạo OR:** rule khớp đầu quyết định; dùng một `hasAnyAuthority(...)` hoặc `hasAnyRole(...)`.
7. **Dùng phép OR làm đường vòng bỏ qua owner/tenant:** điều kiện bắt buộc cần nằm ngoài nhánh OR và áp dụng với mọi người, kể cả admin nếu chính sách quy định.
8. **Chỉ bảo vệ controller:** lời gọi service từ luồng khác có thể bỏ qua HTTP. Dùng method security và bảo vệ dữ liệu theo ID.
9. **Chưa bật `@EnableMethodSecurity` hoặc self-invocation:** annotation có thể không thực thi. Kiểm tra qua Spring-managed bean.
10. **Test nhầm nguồn 403:** CSRF, authentication, proxy hoặc ràng buộc nghiệp vụ có thể khiến request bị từ chối sau khi qua rule authority.
11. **Mặc định mở quyền cho endpoint mới:** đặt `anyRequest().denyAll()`; chỉ thêm quyền sau khi xác định yêu cầu nghiệp vụ.
12. **Cấp quyền thay thế quá rộng:** không thêm role hoặc authority vào danh sách OR chỉ vì “giúp người dùng truy cập được”; mỗi lựa chọn phải được chính sách cho phép và kiểm thử.

## 11. Quy trình chọn API cho nghiệp vụ

1. Liệt kê **tất cả** quyền/role thực tế của `Authentication` sau khi ánh xạ.
2. Hỏi “chỉ cần **một trong các quyền** hay bắt buộc **tất cả**?”; ghi điều kiện bằng OR/AND trước khi viết code.
3. Nếu so khớp **chuỗi GrantedAuthority bất kỳ**, dùng `hasAnyAuthority("a", "b")`. Nếu so khớp **vai trò** theo quy ước prefix, dùng `hasAnyRole("EDITOR", "ADMIN")`.
4. Gắn rule ở HTTP cho chặn sớm và ở service nếu nghiệp vụ có nhiều đường vào; cấu hình fallback từ chối.
5. Thêm điều kiện bất biến như tenant, owner, trạng thái tài liệu ở method/object/query; không để chúng bị bỏ qua bởi OR.
6. Kiểm thử từng quyền thay thế riêng lẻ, trường hợp không có quyền, role prefix, JWT mapping, CSRF, method proxy và dữ liệu ngoài phạm vi.

**Tự kiểm tra:** Alice có đúng `report:export` và `ROLE_SUPPORT`, không có `report:read` hay `ROLE_ADMIN`. Alice có vượt qua `hasAnyAuthority("report:read", "report:export")` không? **Có**, vì ít nhất một authority khớp. Alice có vượt qua `hasAnyRole("ADMIN", "EDITOR")` không? **Không**, vì không có `ROLE_ADMIN` hoặc `ROLE_EDITOR`. Nếu endpoint yêu cầu **cả** quyền báo cáo và role quản trị, kết quả chung vẫn là **từ chối**.

## Tài liệu tham khảo

- Spring Security, *Authorize HttpServletRequests*: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security, *Method Security*: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Security, *Authorization Architecture*: https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html
- Spring Security, *Testing Method Security*: https://docs.spring.io/spring-security/reference/servlet/test/method.html
