# hasRole, hasAuthority và tiền tố ROLE_ trong phân quyền HTTP

> **Chủ đề:** Spring Security – reactive  
> **Ngữ cảnh:** Phân quyền HTTP với Spring WebFlux  
> **Trọng tâm:** Hiểu cách `hasRole` và `hasAuthority` so sánh `GrantedAuthority`, khi nào Spring Security thêm `ROLE_`, cách xây dựng `SecurityWebFilterChain` đúng thứ tự, và cách kiểm tra bằng `WebTestClient` với các tài khoản có quyền thực tế.

## 1. Vì sao cùng một user có thể qua hasRole nhưng không qua hasAuthority?

Xét hai rule cho endpoint trong Spring Security WebFlux:

```java
.pathMatchers("/api/admin").hasRole("ADMIN")
.pathMatchers("/api/raw-admin").hasAuthority("ADMIN")
```

Chúng **không tương đương** khi danh sách quyền của người dùng chứa `ROLE_ADMIN` nhưng không chứa `ADMIN`.

- `hasRole("ADMIN")` theo quy ước mặc định tìm authority có tên **`ROLE_ADMIN`**.
- `hasAuthority("ADMIN")` yêu cầu đúng authority **`ADMIN`**, **không thêm** `ROLE_`.
- `hasAuthority("ROLE_ADMIN")` yêu cầu đúng authority **`ROLE_ADMIN`**, nên tương đương về điều kiện khớp trong trường hợp mặc định với `hasRole("ADMIN")`.
- `hasRole("ROLE_ADMIN")` là cách gọi sai theo API role chuẩn: role argument đã có prefix; đừng thêm prefix hai lần.
- Người đã **authentication thành công** nhưng thiếu authority được yêu cầu vẫn có thể nhận **403 Forbidden**. Thiếu credentials ở endpoint được bảo vệ thường nhận **401 Unauthorized**.

Cốt lõi của đề bài là: **role là một quy ước đặt tên trên chuỗi authority, không phải một kiểu `GrantedAuthority` hoàn toàn tách biệt**. Khi dự đoán kết quả, hãy kiểm tra chính xác hai chuỗi: authority **được cấp** và authority **được yêu cầu**.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích quan hệ giữa `Authentication`, `GrantedAuthority`, role và quyền chi tiết.
2. Dự đoán kết quả `hasRole`, `hasAnyRole`, `hasAuthority`, `hasAnyAuthority` với các chuỗi được cấp.
3. Dùng đúng `User.withUsername(...).roles(...)` và `.authorities(...)`, tránh lặp `ROLE_` hoặc ghi đè tập quyền.
4. Viết phân quyền HTTP bằng `ServerHttpSecurity.authorizeExchange(...)` và `SecurityWebFilterChain`, khác với Servlet `HttpSecurity`.
5. Hiểu ảnh hưởng của thứ tự matcher, prefix, case sensitivity và cách ánh xạ authorities từ JWT/identity provider.
6. Viết ứng dụng WebFlux Java 17+ và test trường hợp đủ quyền/thiếu quyền với HTTP Basic credentials thật.
7. Phân biệt HTTP authorization với reactive method security, từ đó tránh lệch cấu hình giữa hai tầng.

## 2. Phân biệt Authentication, GrantedAuthority, role và permission

Trong Spring Security, thông tin về người gọi thường nằm ở một đối tượng `Authentication`:

```java
// Chữ ký minh họa: đoạn này chưa phải file Java độc lập.
Authentication authentication = ...;
String username = authentication.getName();
Collection<? extends GrantedAuthority> granted =
    authentication.getAuthorities();
```

- `Authentication`: đại diện trạng thái xác thực của principal; có tên, credentials (có thể đã được xóa), authorities và cờ authentication.
- `GrantedAuthority`: giao diện mô tả một quyền được cấp cho principal. Ví dụ `SimpleGrantedAuthority("ROLE_ADMIN")` có `getAuthority()` trả về chuỗi `ROLE_ADMIN`.
- **Role:** thường là quyền cấp độ nhóm/chức năng được **đặt tên theo quy ước `ROLE_`**, chẳng hạn `ROLE_ADMIN`, `ROLE_READER`.
- **Permission/authority cụ thể:** cũng được biểu diễn bằng `GrantedAuthority`, ví dụ `report:read`, `order:approve`, `SCOPE_reports.read`.
- **Principal:** người hay thực thể đang được xác thực. Một client JWT, người dùng Basic, session login hay service identity đều có thể được chuyển thành `Authentication`; framework không đoán vai trò từ tên tài khoản.

Ví dụ danh sách authorities:

```text
Authentication name: alice
Authorities:
  ROLE_READER
  report:read
  SCOPE_reports.read
```

Từ danh sách đó:

| Điều kiện HTTP | Authority cần khớp | Kết quả |
| --- | --- | --- |
| `hasRole("READER")` | `ROLE_READER` | Đúng |
| `hasRole("ADMIN")` | `ROLE_ADMIN` | Sai |
| `hasAuthority("ROLE_READER")` | `ROLE_READER` | Đúng |
| `hasAuthority("READER")` | `READER` | Sai |
| `hasAuthority("report:read")` | `report:read` | Đúng |
| `hasAuthority("SCOPE_reports.read")` | `SCOPE_reports.read` | Đúng |
| `hasAuthority("reports.read")` | `reports.read` | Sai |
| `hasAnyRole("ADMIN", "READER")` | `ROLE_ADMIN` **hoặc** `ROLE_READER` | Đúng |

**So khớp tên quyền là so khớp chuỗi** trong thiết lập chuẩn này. `ADMIN` khác `ROLE_ADMIN`, `report:read` khác `REPORT:READ`, `SCOPE_reports.read` khác `reports.read`. Không có phép chuyển đổi tự động giữa mọi naming convention.

### 2.1. “Đã đăng nhập” chưa có nghĩa “đủ quyền”

Trong HTTP Basic, form login hoặc JWT, authentication manager có thể xác định user là hợp lệ. Sau đó **authorization** mới xét policy cho endpoint. User `reader` có `ROLE_READER` nhưng không có `ROLE_ADMIN` sẽ đăng nhập được mà vẫn nhận 403 ở endpoint quản trị.

```text
Request
  |
  v
Authentication (Basic / session / JWT)
  |
  +-- Không có chứng cứ hợp lệ --------------> 401 / challenge hoặc flow đăng nhập
  |
  +-- Authentication thành công
          |
          v
   AuthorizationWebFilter
          |
          +-- hasRole / hasAuthority đúng ----> handler/controller
          |
          +-- Quyền không đủ -----------------> AccessDeniedException
                                                    |
                                                    v
                                             thường 403 Forbidden
```

Đây là sơ đồ giản lược. Spring Security có nhiều filter, handler và entry point khác nhau; response cụ thể còn tùy cơ chế authentication, cấu hình CSRF và trạng thái principal. **Đừng dùng 403 để kết luận mật khẩu sai** hoặc **dùng 401 để kết luận user thiếu role**.

## 3. hasRole("ADMIN") thực sự kiểm tra gì?

Trong cấu hình mặc định của Spring Security WebFlux, `hasRole("ADMIN")` là tiện ích tương đương với việc đòi authority `ROLE_ADMIN`.

```java
// Đoạn nằm trong authorizeExchange(...):
.pathMatchers("/admin").hasRole("ADMIN")
```

Hệ thống kiểm tra `Authentication.getAuthorities()` có `ROLE_ADMIN` hay không. Không cần, và không nên, viết `.hasRole("ROLE_ADMIN")`. Trong API role manager tiêu chuẩn, argument đã chứa `ROLE_` có thể bị từ chối bằng `IllegalArgumentException` để tránh nhầm prefix.

Có thể ghi điều kiện tương đương dưới dạng authority **trong cấu hình sử dụng tiền tố mặc định**:

```java
.pathMatchers("/admin").hasAuthority("ROLE_ADMIN")
```

Nhưng **đừng nói mọi biến thể cấu hình hasRole trong mọi tầng đều cố định như vậy**. Có cách thay đổi quy ước prefix trong các hệ thống expression/method security; hơn nữa, HTTP rule, method rule và JWT converter có thể có cơ chế cấu hình khác nhau. Phần 11 sẽ chỉ rõ ranh giới này.

### 3.1. hasAnyRole là phép OR, không phải AND

```java
.pathMatchers("/api/manage").hasAnyRole("ADMIN", "EDITOR")
```

Mặc định yêu cầu **ít nhất một** trong `ROLE_ADMIN` hoặc `ROLE_EDITOR`. Nó **không đòi cả hai**. Không cần viết hai rule cho cùng một path rồi kỳ vọng tự động tạo phép AND; nếu cần điều kiện phức hợp, hãy thiết kế `ReactiveAuthorizationManager` hoặc kiểm tra sâu hơn ở tầng nghiệp vụ.

### 3.2. Role không có quan hệ phân cấp mặc định

`ROLE_ADMIN` **không tự động** bao hàm `ROLE_READER` chỉ vì từ “ADMIN” có vẻ cấp cao hơn. Nếu muốn admin cũng truy cập được endpoint reader, có thể:

- Gán **cả hai** authorities cho admin;
- Dùng `hasAnyRole("ADMIN", "READER")` ở endpoint thích hợp;
- Thiết kế **role hierarchy** được Spring Security hỗ trợ và cấu hình đúng tại tầng authorization;
- Dùng quyền nghiệp vụ độc lập như `report:read` để không ràng buộc quá nhiều vào tên role.

Không suy diễn role hierarchy nếu chưa có cấu hình. Khi một user bị 403 dù được gọi là “admin” trong cơ sở dữ liệu, hãy kiểm tra danh sách `GrantedAuthority` thực sự sau authentication.

## 4. hasAuthority("...") thực sự kiểm tra gì?

`hasAuthority` yêu cầu **tên authority chính xác**, không tự thêm `ROLE_` hay `SCOPE_`.

```java
.pathMatchers("/api/report").hasAuthority("report:read")
.pathMatchers("/api/scoped").hasAuthority("SCOPE_reports.read")
.pathMatchers("/api/raw-admin").hasAuthority("ADMIN")
```

Ba rule trên yêu cầu ba chuỗi **khác nhau**:

```text
report:read
SCOPE_reports.read
ADMIN
```

Vì thế:

- `ROLE_ADMIN` không vượt qua `hasAuthority("ADMIN")`.
- `ADMIN` không vượt qua `hasAuthority("ROLE_ADMIN")`.
- `SCOPE_reports.read` không vượt qua `hasAuthority("report:read")`.
- `report:read` không vượt qua `hasAuthority("SCOPE_reports.read")`.

Nếu một user có nhiều authority, mỗi rule chỉ cần kiểm tra xem **authority nó cần có nằm trong tập được cấp hay không**.

### 4.1. hasAnyAuthority là phép OR theo tên chính xác

```java
.pathMatchers("/api/view")
.hasAnyAuthority("report:read", "report:admin")
```

Điều kiện đúng khi có ít nhất một trong hai chuỗi `report:read` hoặc `report:admin`, không phải khi `report:admin` tự suy ra `report:read`. Một hệ thống có thể quy ước mọi admin phải sở hữu cả hai quyền, nhưng đó là **chính sách cấp quyền**, không phải phép so sánh mặc định của `hasAuthority`.

### 4.2. Nên dùng role hay authority?

| Bài toán | Cách diễn đạt thường rõ ràng | Ghi chú |
| --- | --- | --- |
| Trang quản trị dành cho nhóm `ADMIN` | `hasRole("ADMIN")` | Quy ước `ROLE_ADMIN` |
| Báo cáo dành cho nhóm `READER` | `hasRole("READER")` | Quy ước `ROLE_READER` |
| Quyền đọc báo cáo bất kể thuộc nhóm nào | `hasAuthority("report:read")` | Permission cụ thể |
| Scope OAuth2/JWT mặc định | `hasAuthority("SCOPE_reports.read")` | Tùy cơ chế ánh xạ scope |
| Đối tác cấp thẳng chuỗi `ADMIN` | `hasAuthority("ADMIN")` | Không giả định đã thành `ROLE_ADMIN` |
| User được vào nếu là ADMIN hoặc EDITOR | `hasAnyRole("ADMIN", "EDITOR")` | OR |
| Endpoint cần một trong hai scope | `hasAnyAuthority("SCOPE_a", "SCOPE_b")` | OR |

Không có quy định rằng mọi quyền fine-grained phải dùng format `resource:action`: đó là một quy ước thiết kế. Trong API lớn, ưu tiên chuẩn hóa naming convention để tránh hàng loạt `ROLE_`/`SCOPE_`/`ADMIN` khác nhau mà không có tài liệu.

## 5. User.roles(...) và User.authorities(...): nguồn gốc của prefix

Khi dựng `UserDetails` bằng `org.springframework.security.core.userdetails.User`:

```java
UserDetails admin = User.withUsername("admin")
    .password(passwordHash)
    .roles("ADMIN")
    .build();
```

Phương thức `.roles("ADMIN")` tạo authority **`ROLE_ADMIN`**. Về tên authority, nó tương đương:

```java
UserDetails admin = User.withUsername("admin")
    .password(passwordHash)
    .authorities("ROLE_ADMIN")
    .build();
```

Ngược lại:

```java
UserDetails raw = User.withUsername("raw")
    .password(passwordHash)
    .authorities("ADMIN")
    .build();
```

User `raw` có authority tên **`ADMIN`**, không có `ROLE_ADMIN`.

### 5.1. Những cách gọi dễ sai

| Lệnh builder | Authority tạo ra | Nhận xét |
| --- | --- | --- |
| `.roles("ADMIN")` | `ROLE_ADMIN` | Đúng, theo quy ước role |
| `.roles("USER", "ADMIN")` | `ROLE_USER`, `ROLE_ADMIN` | Đúng |
| `.authorities("ROLE_ADMIN")` | `ROLE_ADMIN` | Đúng, đặt authority trực tiếp |
| `.authorities("ADMIN")` | `ADMIN` | Đúng về cú pháp, **không** giống `ROLE_ADMIN` |
| `.authorities("report:read")` | `report:read` | Đúng, permission cụ thể |
| `.roles("ROLE_ADMIN")` | Không tạo theo cách mong đợi | **Sai:** `roles` đã thêm prefix, API chuẩn từ chối role có prefix |
| Gọi `.roles(...)` rồi `.authorities(...)` | Không có nghĩa chắc chắn cộng dồn | Có thể **ghi đè** danh sách quyền trong builder |

Nếu một user cần **cả role lẫn permission**, hãy chỉ định **một tập authority cuối cùng**, ví dụ:

```java
UserDetails reader = User.withUsername("reader")
    .password(passwordHash)
    .authorities("ROLE_READER", "report:read")
    .build();
```

Cách này tránh giả định rằng gọi liên tiếp `.roles("READER").authorities("report:read")` sẽ thêm permission vào danh sách role ban đầu. Với provider thực tế (DB/LDAP/JWT/OIDC), không dùng `User.UserBuilder` thì mapping thường do bộ chuyển đổi `Authentication` riêng thực hiện.

### 5.2. Một helper Java 17 thuần để hình dung chuỗi authority

Class bên dưới **không chạy Spring Security và không thay thế kiểm tra phân quyền thực**; nó chỉ mô phỏng việc tìm tên authority để bạn tự xác minh sự khác biệt `ROLE_ADMIN` và `ADMIN`.

Tạo `RolePrefixDemo.java`:

```java
import java.util.Set;

public final class RolePrefixDemo {

    public static void main(String[] args) {
        Set<String> granted = Set.of("ROLE_ADMIN", "report:read");

        System.out.println("hasRole(ADMIN)="
            + granted.contains("ROLE_" + "ADMIN"));
        System.out.println("hasAuthority(ADMIN)="
            + granted.contains("ADMIN"));
        System.out.println("hasAuthority(ROLE_ADMIN)="
            + granted.contains("ROLE_ADMIN"));
        System.out.println("hasAuthority(report:read)="
            + granted.contains("report:read"));
        System.out.println("hasRole(READER)="
            + granted.contains("ROLE_" + "READER"));
    }
}
```

Chạy bằng Java 17+:

```bash
javac RolePrefixDemo.java
java RolePrefixDemo
```

**Stdout chính xác:**

```text
hasRole(ADMIN)=true
hasAuthority(ADMIN)=false
hasAuthority(ROLE_ADMIN)=true
hasAuthority(report:read)=true
hasRole(READER)=false
```

Đoạn này chứng minh một phép so khớp tên, **không chứng minh bất kỳ `UserDetails` nào đã vượt qua authentication**. Ở ứng dụng thật, Spring Security còn xem trạng thái xác thực, match request, security chain, role hierarchy nếu có và các authorization managers.

## 6. Phân quyền HTTP reactive: ServerHttpSecurity, không phải HttpSecurity

Trong Spring WebFlux, cấu hình HTTP security sử dụng:

```java
SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
    return http
        .authorizeExchange(exchanges -> exchanges
            .pathMatchers("/api/public").permitAll()
            .pathMatchers("/api/admin").hasRole("ADMIN")
            .pathMatchers("/api/report").hasAuthority("report:read")
            .anyExchange().denyAll()
        )
        .build();
}
```

Đây là **trích đoạn minh họa**, chưa chứa `@Configuration`, authentication mechanism và imports; ví dụ runnable đầy đủ ở mục 9.

**Khác biệt quan trọng:**

| Reactive WebFlux | Servlet |
| --- | --- |
| `ServerHttpSecurity` | `HttpSecurity` |
| `SecurityWebFilterChain` | `SecurityFilterChain` |
| `authorizeExchange(...)` | `authorizeHttpRequests(...)` |
| `pathMatchers(...)` | `requestMatchers(...)` |
| `AuthorizationWebFilter` | Servlet filter chain |
| `ReactiveSecurityContextHolder` | Thường là `SecurityContextHolder` trên thread |

Không copy đoạn `HttpSecurity.authorizeHttpRequests(...)` từ tài liệu Servlet vào dự án WebFlux và mong hoạt động như mã reactive. Đồng thời không kết luận chỉ cần `@EnableWebFluxSecurity` là role/authority được tạo sẵn; authorities đến từ authentication provider hoặc converter.

### 6.1. Thứ tự matcher thay đổi kết quả

Các rule được khai báo theo thứ tự. Với nhiều matcher cùng có thể khớp một request, Spring Security chọn điều kiện theo quy tắc matching/order của security DSL. Ví dụ:

```java
// Minh họa CẤU HÌNH SAI: rule rộng phủ lên rule nhạy cảm.
.authorizeExchange(exchanges -> exchanges
    .pathMatchers("/api/**").authenticated()
    .pathMatchers("/api/admin/**").hasRole("ADMIN")
    .anyExchange().denyAll()
)
```

Ở đây request `/api/admin/users` bị rule rộng `/api/**` match trước và chỉ cần authentication. Điều kiện admin được khai báo sau có thể không còn cơ hội áp dụng.

Cấu hình đúng hơn:

```java
.authorizeExchange(exchanges -> exchanges
    .pathMatchers("/api/admin/**").hasRole("ADMIN")
    .pathMatchers("/api/**").authenticated()
    .anyExchange().denyAll()
)
```

**Mẹo:** rule hẹp/nhạy cảm trước, rule rộng sau, `anyExchange` cuối. Không coi nhiều rule match cùng URL là tự động hợp thành AND. Khi thêm endpoints và nhiều `SecurityWebFilterChain`, kiểm tra cả **thứ tự chọn chain**, không chỉ thứ tự trong một chain.

### 6.2. Phân quyền theo HTTP method

Có thể áp dụng authority cho một method và path:

```java
// Đoạn DSL minh họa, không thuộc project GET-only bên dưới.
.pathMatchers(HttpMethod.GET, "/api/reports/**")
    .hasAuthority("report:read")
.pathMatchers(HttpMethod.POST, "/api/reports/**")
    .hasAuthority("report:write")
```

Cần import `org.springframework.http.HttpMethod`. Một user có `report:read` **không tự có** `report:write`. Với POST sử dụng browser cookies/session, phải xét CSRF riêng; một POST bị 403 có thể do CSRF mà không phải authority.

## 7. Phân biệt 401, 403 và lỗi cấu hình ROLE_

Một số tình huống khi dùng HTTP Basic trong WebFlux:

| Request | Authentication | Authority thực tế | Rule | HTTP thường gặp |
| --- | --- | --- | --- | --- |
| Không có credentials | Chưa xác thực | Không có | `hasRole("ADMIN")` | **401** + `WWW-Authenticate` |
| Password sai | Xác thực thất bại | Không có | `hasRole("ADMIN")` | **401** |
| Password đúng | Xác thực thành công | `ROLE_ADMIN` | `hasRole("ADMIN")` | **200** nếu controller OK |
| Password đúng | Xác thực thành công | `ADMIN` | `hasRole("ADMIN")` | **403** |
| Password đúng | Xác thực thành công | `ADMIN` | `hasAuthority("ADMIN")` | **200** nếu controller OK |
| Password đúng | Xác thực thành công | `ROLE_ADMIN` | `hasAuthority("ADMIN")` | **403** |
| Password đúng | Xác thực thành công | `ROLE_ADMIN` | `hasAuthority("ROLE_ADMIN")` | **200** nếu controller OK |
| Password đúng | Xác thực thành công | `report:read` | `hasAuthority("report:read")` | **200** nếu controller OK |

Lưu ý: Không thể chỉ nhìn mã HTTP **403** để biết nguyên nhân chắc chắn là prefix. CSRF, quyền đối tượng, chain khác, denyAll hoặc policy application cũng có thể trả 403. Hãy kiểm tra authorities và policy một cách có kiểm soát, không in credentials hay raw token ra log.

### 7.1. Không nhầm ROLE_ với SCOPE_

Trong một Spring Security OAuth2 resource server với JWT và converter scope mặc định, claim `scope`/`scp` thường được ánh xạ thành `GrantedAuthority` có tiền tố **`SCOPE_`**. Ví dụ scope `reports.read` có thể thành:

```text
SCOPE_reports.read
```

Khi đó nên viết:

```java
.pathMatchers("/api/jwt-reports")
    .hasAuthority("SCOPE_reports.read")
```

Không mặc định thay bằng `hasRole("reports.read")`: cách đó yêu cầu `ROLE_reports.read`, là một tên khác. JWT không bắt buộc luôn dùng converter mặc định; nếu tổ chức ánh xạ claim roles/groups riêng, cần kiểm tra `Authentication.getAuthorities()` sau converter, chứ không suy từ JSON claim của token.

### 7.2. Đừng nhầm “role admin” của DB với ROLE_ADMIN

Một DB có thể lưu `role_name='ADMIN'`. Lưu như vậy **không tự khiến Spring Security nhận `GrantedAuthority("ROLE_ADMIN")`**. Lớp chuyển đổi `UserDetailsService`/`ReactiveUserDetailsService` phải chọn chính sách:

- Ghi `ROLE_` khi ánh xạ role từ DB, rồi dùng `hasRole("ADMIN")`.
- Giữ nguyên `ADMIN` thành authority, rồi dùng `hasAuthority("ADMIN")`.
- Dùng một converter nhất quán cho cả HTTP security, method security và token policies.

Không được prefix lại chuỗi đã có `ROLE_` thành `ROLE_ROLE_ADMIN`. Không được loại prefix ngẫu nhiên trên toàn bộ authorities vì điều đó có thể làm lệch scope/permission.

## 8. Bảng chân trị quan trọng: dự đoán trước khi chạy test

Giả sử có năm user:

```text
admin   -> ROLE_ADMIN
raw     -> ADMIN
editor  -> ROLE_EDITOR
reader  -> ROLE_READER, report:read
scoped  -> SCOPE_reports.read
```

Bảng dưới dùng `✔` cho phép truy cập, `✘` từ chối quyền **sau khi authentication đã thành công**:

| User | hasRole("ADMIN") | hasAuthority("ADMIN") | hasAuthority("ROLE_ADMIN") | hasAnyRole("ADMIN","EDITOR") | hasAuthority("report:read") |
| --- | --- | --- | --- | --- | --- |
| admin | ✔ | ✘ | ✔ | ✔ | ✘ |
| raw | ✘ | ✔ | ✘ | ✘ | ✘ |
| editor | ✘ | ✘ | ✘ | ✔ | ✘ |
| reader | ✘ | ✘ | ✘ | ✘ | ✔ |
| scoped | ✘ | ✘ | ✘ | ✘ | ✘ |

Một role được nhận diện theo **prefix**, chứ không vì username tên `admin`. User `raw` có `ADMIN` đúng chữ nhưng vẫn không vượt qua `hasRole("ADMIN")`. User `scoped` có scope thích hợp vẫn không vượt qua `hasAuthority("report:read")` nếu chưa được cấp đúng tên quyền đó.

## 9. Project Java 17+ chạy được: Spring Boot WebFlux + role/authority

Project dưới dùng **Spring Boot 3.5.16** và Java 17; phiên bản Boot này có thực trên Maven Central, nhưng đã là **bản kết thúc hỗ trợ OSS của nhánh 3.5**, vì vậy đây là baseline minh họa, **không phải lời khuyên chọn version production mới năm 2026**. Khi triển khai hệ thống mới nên chọn nhánh được hỗ trợ (ví dụ Boot 4.x) và cập nhật theo migration guide.

Ví dụ này sử dụng HTTP Basic để kiểm tra quyền HTTP một cách dễ tái lập. Username/password được cố định **chỉ cho bài học**, password được lưu trong `MapReactiveUserDetailsService` ở dạng hash BCrypt (tạo trong lúc khởi động). Toàn bộ endpoint là **GET**; không cần tắt CSRF. Spring Security vẫn chịu trách nhiệm authentication, trong khi mỗi path rule quyết định authority cần thiết.

### 9.1. Cấu trúc thư mục

```text
role-authority-webflux/
├── pom.xml
└── src/
    ├── main/java/demo/roles/
    │   ├── Application.java
    │   ├── SecurityConfiguration.java
    │   └── ApiController.java
    └── test/java/demo/roles/
        └── RoleAuthorityWebFluxTests.java
```

### 9.2. `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>role-authority-webflux</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
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

Spring Boot parent quản lý phiên bản Spring Security, Reactor và các thư viện phù hợp. Không tự thêm `spring-boot-starter-web` chỉ để được Basic auth, vì starter đó kéo theo Servlet MVC và có thể làm ứng dụng chạy theo web stack khác dự định.

### 9.3. `src/main/java/demo/roles/Application.java`

```java
package demo.roles;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
```

### 9.4. `src/main/java/demo/roles/SecurityConfiguration.java`

```java
package demo.roles;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authentication.UserDetailsRepositoryReactiveAuthenticationManager;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        // Demo password chung cho dễ kiểm thử, KHÔNG dùng tài khoản thật.
        String password = "demo123";

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode(password))
            .roles("ADMIN") // authority được cấp: ROLE_ADMIN
            .build();

        UserDetails raw = User.withUsername("raw")
            .password(encoder.encode(password))
            .authorities("ADMIN") // KHÔNG có ROLE_
            .build();

        UserDetails editor = User.withUsername("editor")
            .password(encoder.encode(password))
            .roles("EDITOR") // ROLE_EDITOR
            .build();

        UserDetails reader = User.withUsername("reader")
            .password(encoder.encode(password))
            .authorities("ROLE_READER", "report:read")
            .build();

        UserDetails scoped = User.withUsername("scoped")
            .password(encoder.encode(password))
            .authorities("SCOPE_reports.read")
            .build();

        UserDetails multi = User.withUsername("multi")
            .password(encoder.encode(password))
            .authorities(
                "ROLE_ADMIN", "report:read", "SCOPE_reports.read")
            .build();

        return new MapReactiveUserDetailsService(
            admin, raw, editor, reader, scoped, multi);
    }

    @Bean
    ReactiveAuthenticationManager authenticationManager(
            MapReactiveUserDetailsService users, PasswordEncoder encoder) {

        UserDetailsRepositoryReactiveAuthenticationManager manager =
            new UserDetailsRepositoryReactiveAuthenticationManager(users);
        manager.setPasswordEncoder(encoder);
        return manager;
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http, ReactiveAuthenticationManager manager) {

        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/api/public").permitAll()
                .pathMatchers("/api/admin").hasRole("ADMIN")
                .pathMatchers("/api/raw-admin").hasAuthority("ADMIN")
                .pathMatchers("/api/admin-exact")
                    .hasAuthority("ROLE_ADMIN")
                .pathMatchers("/api/reader").hasRole("READER")
                .pathMatchers("/api/report").hasAuthority("report:read")
                .pathMatchers("/api/scoped")
                    .hasAuthority("SCOPE_reports.read")
                .pathMatchers("/api/editors")
                    .hasAnyRole("ADMIN", "EDITOR")
                .pathMatchers("/api/me").authenticated()
                .anyExchange().denyAll()
            )
            .httpBasic(basic -> basic.authenticationManager(manager))
            .formLogin(form -> form.disable())
            .build();
    }
}
```

**Vì sao dự án này giúp tránh hiểu lầm:**

- User `admin` được tạo với `.roles("ADMIN")`, nên có `ROLE_ADMIN`.
- User `raw` được tạo với `.authorities("ADMIN")`, nên **không có** `ROLE_ADMIN`.
- User `editor` có `ROLE_EDITOR`, đủ quyền vào `hasAnyRole("ADMIN","EDITOR")` nhưng không đủ quyền `hasRole("ADMIN")`.
- User `reader` có **cả** `ROLE_READER` và `report:read`. Nó không có `ROLE_ADMIN`.
- User `scoped` có `SCOPE_reports.read`, không tự chuyển thành `report:read`.
- User `multi` được cấp ba authority ở dạng tường minh; đây là cách rõ ràng nhất nếu muốn có role + permission + scope đồng thời trong ví dụ.
- `anyExchange().denyAll()` có tác dụng **default deny** cho các request chưa match, tránh vô tình lộ endpoint mới được viết.
- `httpBasic(...)` giúp test bằng credentials thật; `formLogin(...disable())` tránh login page redirect làm nhiễu kết quả 401/403.
- Dùng BCrypt để băm password ở user store demo, nhưng **không hard-code password production**. Với Basic thật ngoài localhost cần HTTPS/TLS và biện pháp chống dò mật khẩu.

### 9.5. `src/main/java/demo/roles/ApiController.java`

```java
package demo.roles;

import java.util.stream.Collectors;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class ApiController {

    @GetMapping("/api/public")
    public Mono<String> publicRoute() {
        return Mono.just("public OK");
    }

    @GetMapping("/api/admin")
    public Mono<String> adminRoute() {
        return Mono.just("admin OK");
    }

    @GetMapping("/api/raw-admin")
    public Mono<String> rawAdminRoute() {
        return Mono.just("raw authority OK");
    }

    @GetMapping("/api/admin-exact")
    public Mono<String> adminExactRoute() {
        return Mono.just("role authority OK");
    }

    @GetMapping("/api/reader")
    public Mono<String> readerRoute() {
        return Mono.just("reader OK");
    }

    @GetMapping("/api/report")
    public Mono<String> reportRoute() {
        return Mono.just("report OK");
    }

    @GetMapping("/api/scoped")
    public Mono<String> scopedRoute() {
        return Mono.just("scope OK");
    }

    @GetMapping("/api/editors")
    public Mono<String> editorsRoute() {
        return Mono.just("editors OK");
    }

    @GetMapping("/api/me")
    public Mono<String> authorities() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(authentication -> "authorities="
                + authentication.getAuthorities().stream()
                    .map(GrantedAuthority::getAuthority)
                    .sorted()
                    .collect(Collectors.joining(",")));
    }
}
```

Endpoint `/api/me` để **quan sát trong demo** tập `GrantedAuthority` thật được Spring Security đặt vào reactive security context. Không công khai toàn bộ authorities trong production nếu đó là thông tin nhạy cảm về phân quyền nội bộ; tốt hơn là đọc từ server logs/metrics đã kiểm soát hoặc chỉ cung cấp quyền cần thiết cho UX.

Trong đoạn code, import `Authentication` không được dùng trực tiếp ở body (có thể bỏ), nhưng không làm file không biên dịch được. Nếu IDE báo unused import, hãy xóa import thừa để code style sạch.

## 10. Bộ test WebTestClient: xác thực thật, kiểm tra quyền thật

Đây là nơi chứng minh quy tắc prefix. `@WithMockUser` hay `mockUser()` có thể hữu ích để test **chính sách authorization** nhưng không chứng minh password encoder và converter Basic hoạt động. Bộ test dưới sử dụng **`Authorization: Basic` thật** qua `setBasicAuth`, từ đó kiểm tra cả cơ chế xác thực và authority được cấp.

### 10.1. `src/test/java/demo/roles/RoleAuthorityWebFluxTests.java`

```java
package demo.roles;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class RoleAuthorityWebFluxTests {

    @Autowired
    ApplicationContext context;

    private WebTestClient client;

    @BeforeEach
    void setup() {
        client = WebTestClient
            .bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    private WebTestClient.ResponseSpec getAs(String path, String username) {
        return client.get().uri(path)
            .headers(headers -> headers.setBasicAuth(username, "demo123"))
            .exchange();
    }

    @Test
    void publicEndpointAllowsAnonymous() {
        client.get().uri("/api/public")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("public OK");
    }

    @Test
    void protectedEndpointWithoutCredentialsNeedsAuthentication() {
        client.get().uri("/api/admin")
            .exchange()
            .expectStatus().isUnauthorized()
            .expectHeader().exists(HttpHeaders.WWW_AUTHENTICATE);
    }

    @Test
    void invalidPasswordIsAuthenticationFailure() {
        client.get().uri("/api/admin")
            .headers(h -> h.setBasicAuth("admin", "wrong"))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void rolesAdminPassesHasRoleAdmin() {
        getAs("/api/admin", "admin")
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("admin OK");
    }

    @Test
    void rawAuthorityAdminDoesNotPassHasRoleAdmin() {
        getAs("/api/admin", "raw")
            .expectStatus().isForbidden();
    }

    @Test
    void rawAuthorityAdminPassesHasAuthorityAdmin() {
        getAs("/api/raw-admin", "raw")
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("raw authority OK");
    }

    @Test
    void roleAdminDoesNotPassHasAuthorityAdmin() {
        getAs("/api/raw-admin", "admin")
            .expectStatus().isForbidden();
    }

    @Test
    void roleAdminPassesExactRoleAuthority() {
        getAs("/api/admin-exact", "admin")
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("role authority OK");
    }

    @Test
    void rawAdminDoesNotPassExactRoleAuthority() {
        getAs("/api/admin-exact", "raw")
            .expectStatus().isForbidden();
    }

    @Test
    void readerRolePassesHasRoleReader() {
        getAs("/api/reader", "reader")
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("reader OK");
    }

    @Test
    void readerPermissionPassesHasAuthorityReportRead() {
        getAs("/api/report", "reader")
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("report OK");
    }

    @Test
    void adminWithoutReportPermissionIsForbidden() {
        getAs("/api/report", "admin")
            .expectStatus().isForbidden();
    }

    @Test
    void jwtStyleScopeAuthorityIsExact() {
        getAs("/api/scoped", "scoped")
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("scope OK");
    }

    @Test
    void jwtStyleScopeIsNotPlainReportPermission() {
        getAs("/api/report", "scoped")
            .expectStatus().isForbidden();
    }

    @Test
    void editorPassesHasAnyRoleAdminOrEditor() {
        getAs("/api/editors", "editor")
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("editors OK");
    }

    @Test
    void adminAlsoPassesHasAnyRoleAdminOrEditor() {
        getAs("/api/editors", "admin")
            .expectStatus().isOk();
    }

    @Test
    void rawAdminDoesNotPassHasAnyRoleAdminOrEditor() {
        getAs("/api/editors", "raw")
            .expectStatus().isForbidden();
    }

    @Test
    void multipleExplicitAuthoritiesPermitAllMatchingRoutes() {
        getAs("/api/admin", "multi")
            .expectStatus().isOk();
        getAs("/api/report", "multi")
            .expectStatus().isOk();
        getAs("/api/scoped", "multi")
            .expectStatus().isOk();
    }

    @Test
    void exactAuthoritiesAreVisibleInReactiveSecurityContext() {
        getAs("/api/me", "raw")
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("authorities=ADMIN");

        getAs("/api/me", "admin")
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("authorities=ROLE_ADMIN");
    }

    @Test
    void unspecifiedRouteUsesDefaultDeny() {
        getAs("/api/unlisted", "admin")
            .expectStatus().isForbidden();
    }
}
```

Có **20 phương thức `@Test`** (một vài phương thức thực hiện nhiều HTTP request). Dùng chung một `WebTestClient` để tạo request mới trong từng test; `setBasicAuth` gửi Basic header đúng dạng. Bộ test kiểm tra `hasRole`, `hasAnyRole`, `hasAuthority`, role raw không prefix, scope không tự đổi tên, 401 khi chưa xác thực, 403 khi thiếu quyền và default deny.

**Một lưu ý về test “đã xác thực”:** Để chỉ test authorization mà không phụ thuộc BCrypt, có thể dùng `client.mutateWith(mockUser("someone").authorities(...))`. Tuy nhiên khi mục tiêu là xác định mapping UserDetails + Basic flow, test credentials thật như ở trên có giá trị hơn. Không trộn kết quả từ mock vào kết luận rằng Basic authentication đã được kiểm chứng.

### 10.2. Tổng hợp kết quả

| User / credentials | Endpoint | Rule | Kỳ vọng |
| --- | --- | --- | --- |
| Không credentials | `/api/public` | `permitAll` | **200** |
| Không credentials | `/api/admin` | `hasRole("ADMIN")` | **401** |
| `admin:wrong` | `/api/admin` | Basic authentication | **401** |
| `admin:demo123` | `/api/admin` | `hasRole("ADMIN")` | **200** |
| `raw:demo123` | `/api/admin` | `hasRole("ADMIN")` | **403** |
| `raw:demo123` | `/api/raw-admin` | `hasAuthority("ADMIN")` | **200** |
| `admin:demo123` | `/api/raw-admin` | `hasAuthority("ADMIN")` | **403** |
| `admin:demo123` | `/api/admin-exact` | `hasAuthority("ROLE_ADMIN")` | **200** |
| `raw:demo123` | `/api/admin-exact` | `hasAuthority("ROLE_ADMIN")` | **403** |
| `reader:demo123` | `/api/reader` | `hasRole("READER")` | **200** |
| `reader:demo123` | `/api/report` | `hasAuthority("report:read")` | **200** |
| `admin:demo123` | `/api/report` | `hasAuthority("report:read")` | **403** |
| `scoped:demo123` | `/api/scoped` | `hasAuthority("SCOPE_reports.read")` | **200** |
| `scoped:demo123` | `/api/report` | `hasAuthority("report:read")` | **403** |
| `editor:demo123` | `/api/editors` | `hasAnyRole("ADMIN", "EDITOR")` | **200** |
| `raw:demo123` | `/api/editors` | `hasAnyRole("ADMIN", "EDITOR")` | **403** |
| `multi:demo123` | `/api/admin`, `/api/report`, `/api/scoped` | Ba authority tương ứng | **200** |
| `admin:demo123` | `/api/unlisted` | `denyAll` | **403** |

Đừng cố định body lỗi 401/403 nếu chưa tùy biến handler. WebFlux/Boot có thể thay đổi body/header theo content negotiation. Ở bài này các assertion trọng tâm là **status, đúng tên authority và body của response thành công**.

## 11. Chạy Maven và quan sát bằng curl

### 11.1. Chạy test

Trong thư mục project chứa `pom.xml`:

```bash
java -version
mvn -version
mvn clean test
```

Dự kiến Surefire thống kê **20 tests, 0 failures, 0 errors** và Maven kết thúc `BUILD SUCCESS` trên môi trường Java 17+ đã cài dependencies tương thích. Đây là **kết quả dự kiến từ mã ví dụ**; không thể coi là kết quả chạy thật trên máy khi chưa thực thi. Nếu có lỗi, đọc `target/surefire-reports`, kiểm tra version JDK/Maven và các nguồn Java đúng package `demo.roles`.

Khởi động:

```bash
mvn spring-boot:run
```

Trong terminal khác:

```bash
# Public, không cần credentials.
curl -i http://localhost:8080/api/public

# Thiếu credentials => 401 + challenge.
curl -i http://localhost:8080/api/admin

# Cùng một endpoint hasRole("ADMIN"):
curl -i -u admin:demo123 http://localhost:8080/api/admin
curl -i -u raw:demo123 http://localhost:8080/api/admin

# So sánh hasAuthority("ADMIN") và hasAuthority("ROLE_ADMIN"):
curl -i -u raw:demo123 http://localhost:8080/api/raw-admin
curl -i -u admin:demo123 http://localhost:8080/api/raw-admin
curl -i -u admin:demo123 http://localhost:8080/api/admin-exact

# Quyền cụ thể khác role:
curl -i -u reader:demo123 http://localhost:8080/api/report
curl -i -u admin:demo123 http://localhost:8080/api/report

# JWT-style scope vẫn là authority string:
curl -i -u scoped:demo123 http://localhost:8080/api/scoped

# hasAnyRole là OR:
curl -i -u editor:demo123 http://localhost:8080/api/editors
curl -i -u raw:demo123 http://localhost:8080/api/editors

# Xem authorities của người dùng demo (không đưa endpoint này vào production):
curl -i -u raw:demo123 http://localhost:8080/api/me
curl -i -u admin:demo123 http://localhost:8080/api/me
```

Trên PowerShell có thể dùng `curl.exe` thay cho alias `curl`. Với credentials thật, tránh đặt password ngay trong command-line history/process list; dùng secret handling của client và luôn gọi API qua HTTPS. Tất cả password trong block trên là **dữ liệu giả để học**.

### 11.2. Một số kết quả tiêu biểu

`GET /api/admin` với user `admin`:

```http
HTTP/1.1 200 OK
Content-Type: text/plain;charset=UTF-8

admin OK
```

Cùng endpoint với user `raw`:

```http
HTTP/1.1 403 Forbidden
```

`GET /api/raw-admin` với user `raw`:

```http
HTTP/1.1 200 OK
Content-Type: text/plain;charset=UTF-8

raw authority OK
```

`GET /api/admin` không credentials:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="Realm"
```

Giá trị realm/headers khác nhau giữa phiên bản và tùy chỉnh; đây chỉ là ví dụ phản hồi. Trong test, hãy kiểm tra **header tồn tại** thay vì khóa cứng `realm="Realm"` nếu dự án không tự cấu hình một realm cố định.

## 12. Role prefix có tùy biến được không?

**Có các cơ chế tùy biến role prefix**, nhưng phải phân biệt rõ nơi áp dụng:

1. Các biểu thức **method security** (ví dụ `@PreAuthorize("hasRole('ADMIN')")`) có thể sử dụng cấu hình default role prefix theo cơ chế của method security, bao gồm `GrantedAuthorityDefaults` trong cấu hình Spring Security phù hợp.
2. `AuthorityReactiveAuthorizationManager.hasRole("ADMIN")` tiêu chuẩn được mô tả là tạo yêu cầu authority có **prefix `ROLE_`**. Cấu hình `ServerHttpSecurity.authorizeExchange(...).hasRole(...)` thông thường dùng chính cơ chế đó.
3. **Không giả định** chỉ cần thêm một bean `GrantedAuthorityDefaults("APP_")` thì mọi HTTP WebFlux `hasRole`, mọi method expression, mọi user builder và mọi JWT authority converter sẽ đồng loạt đổi sang `APP_`.
4. Muốn HTTP rule kiểm tra chuỗi riêng `APP_ADMIN`, cách rõ ràng, minh bạch và dễ test là **`hasAuthority("APP_ADMIN")`** và ánh xạ identity provider thành chính authority đó.
5. Muốn đồng nhất hệ thống, chuẩn hóa mapper và policy, rồi test từng tầng HTTP, method, và token conversion.

Ví dụ sử dụng prefix tùy chỉnh theo **authority tường minh**:

```java
// Ví dụ minh họa, KHÔNG thay đổi project mục 9:
.pathMatchers("/api/custom-admin")
    .hasAuthority("APP_ADMIN")
```

User cần `GrantedAuthority("APP_ADMIN")`, không phải `ROLE_ADMIN`. Đây là hướng ít bất ngờ hơn việc cố thay đổi toàn bộ default role prefix mà không biết scope tác động.

### 12.1. Reactive method security không đồng nghĩa HTTP security

Ví dụ method-level rule:

```java
@PreAuthorize("hasRole('ADMIN')")
public Mono<String> approveReport(String reportId) {
    return service.approve(reportId);
}
```

**Đây là snippet minh họa, không biên dịch độc lập**, thiếu định nghĩa service và import; nếu dùng thật phải bật `@EnableReactiveMethodSecurity` trong cấu hình thích hợp. Một HTTP rule có thể yêu cầu `hasAuthority("report:read")` trước khi controller chạy, trong khi method phía sau lại đòi role ADMIN. Kết quả cuối sẽ là quyền giao nhau của những chốt bảo mật thực sự được áp dụng.

Không dựa vào HTTP path matcher như biện pháp duy nhất bảo vệ dữ liệu đa tenant, đối tượng người dùng, hoặc service bị gọi ngoài HTTP. **Authorization ở nghiệp vụ** phải xét cả resource ownership, tenant boundary và hành động đang thực hiện.

## 13. Quyền từ JWT, OIDC, LDAP và database

Trong ứng dụng production, `GrantedAuthority` thường không được tạo từ `MapReactiveUserDetailsService` như bài học. Nguồn có thể là:

- Database: bảng role, permission, role–permission và user–role.
- LDAP/Active Directory: groups được mapper chuyển sang authorities.
- OAuth2 resource server JWT: scopes và claims `roles`/`groups` được chuyển thành authorities theo converter.
- OIDC: thông tin từ identity provider, token claim và chính sách mapping được ứng dụng kiểm soát.

**Quy tắc chung:** Spring Security kiểm tra **`Authentication.getAuthorities()`**. Một claim như:

```json
{"sub":"123","roles":["ADMIN"],"scope":"reports.read"}
```

**không bảo đảm** tại thời điểm authorization có `ROLE_ADMIN`, `ADMIN`, `SCOPE_reports.read` hay cả ba. Cần xem cơ chế converter đang cấu hình. Các default converters thường có quy ước, nhưng đừng tự giả định rằng một JSON claim bất kỳ được biến thành `GrantedAuthority` đúng định dạng bạn nghĩ.

### 13.1. Map role từ cơ sở dữ liệu

Giả sử DB trả `"ADMIN"` và yêu cầu HTTP là `hasRole("ADMIN")`. Lớp map phải cấp authority `ROLE_ADMIN`:

```java
// Snippet minh họa trong mapper:
String roleFromDatabase = "ADMIN";
GrantedAuthority granted =
    new SimpleGrantedAuthority("ROLE_" + roleFromDatabase);
```

Đoạn này chưa phải file Java độc lập. Nếu DB đã lưu `"ROLE_ADMIN"`, phải kiểm tra prefix trước khi transform, hoặc tốt hơn là thống nhất schema từ đầu. Không tiếp tục nối `ROLE_` không điều kiện, vì rất dễ tạo `ROLE_ROLE_ADMIN`.

### 13.2. Mapping JWT scope và custom role nên tách biệt

Một converter cho scopes có thể tạo `SCOPE_reports.read`. Một mapper riêng cho roles có thể tạo `ROLE_ADMIN`. Hai dạng authority có mục đích khác nhau:

```text
ROLE_ADMIN             -> Role phân công cho người dùng/nhóm
report:read            -> Permission của ứng dụng
SCOPE_reports.read     -> Scope của OAuth2 access token
```

Chúng đều là `GrantedAuthority` khi đã được mapper cấp, nhưng **không tự suy ra lẫn nhau**. Trong ứng dụng thực tế cần thiết kế ai cấp scope, ai có quyền gán role, phạm vi token (audience), tenant và expiry/revocation. Không tin role do client tự gửi qua header tùy ý.

## 14. Các lỗi phổ biến và cách tìm nguyên nhân

| Triệu chứng | Nguyên nhân khả dĩ | Cách kiểm tra/sửa |
| --- | --- | --- |
| User có `ADMIN`, `hasRole("ADMIN")` trả 403 | Thiếu `ROLE_` | Ánh xạ `ROLE_ADMIN` hoặc dùng `hasAuthority("ADMIN")` nếu phù hợp |
| User có `ROLE_ADMIN`, `hasAuthority("ADMIN")` trả 403 | `hasAuthority` so khớp exact | Dùng `hasAuthority("ROLE_ADMIN")` hoặc `hasRole("ADMIN")` |
| Viết `hasRole("ROLE_ADMIN")` bị lỗi khởi động | Role argument đã chứa prefix | Dùng `hasRole("ADMIN")` |
| Viết `.roles("ROLE_ADMIN")` bị lỗi | User builder tự thêm prefix | Dùng `.roles("ADMIN")` |
| Gọi `.roles("ADMIN").authorities("report:read")` mất ROLE_ADMIN | Builder thường thay thế danh sách authorities | Dùng một lần `.authorities("ROLE_ADMIN","report:read")` |
| Role `ADMIN` không tự có quyền `report:read` | Role không mặc định bao hàm permission | Cấp thêm authority hoặc quy định mapping/hierarchy |
| Scope `reports.read` không vượt qua `hasRole("reports.read")` | `ROLE_` khác `SCOPE_` | Dùng `hasAuthority("SCOPE_reports.read")` nếu converter như vậy |
| Uppercase/lowercase quyền khác nhau | String match phân biệt hoa/thường | Chuẩn hóa authority naming tại nguồn |
| Rule admin bị bỏ qua | Rule rộng khai báo trước rule hẹp | Đặt path nhạy cảm trước `/api/**` |
| API dùng JWT nhưng test Basic và kết luận JWT có role | Hai authentication converter khác nhau | Test cơ chế JWT thực, authority mapping trong token |
| Role từ DB có prefix kép `ROLE_ROLE_ADMIN` | Mapper cộng prefix không kiểm tra dữ liệu | Chuẩn hóa role names, tránh double prefix |
| Không credentials nhận 401 | Chưa xác thực | Kiểm tra entry point và authentication mechanism |
| Đã authenticated nhưng không đủ quyền nhận 403 | Authorization từ chối | Xem authority thật và matcher |
| POST 403 dù có `ROLE_ADMIN` | Có thể CSRF, method matcher, rule khác | Kiểm tra CSRF token, security chain, method |
| `hasAnyRole` pass khi chỉ có 1 role | Toán tử OR, không phải AND | Dùng custom policy nếu cần cả hai |
| Method `@PreAuthorize` và HTTP rule cho kết quả khác | Prefix/mapping hoặc policy ở hai tầng không giống nhau | Test và thống nhất cấu hình từng tầng |
| Dự án WebFlux dùng `SecurityFilterChain` | Trộn cấu hình Servlet | Dùng `SecurityWebFilterChain`, `ServerHttpSecurity` |
| Endpoint không khai báo trả 403 thay vì 404 | `anyExchange().denyAll()` chặn trước controller | Đây có thể là default-deny đúng dự kiến |
| Log authority bằng cách in toàn bộ Authentication | Rò credentials hoặc thông tin bảo mật | Chỉ log trạng thái và quyền được cho phép, không log secret |

### 14.1. Quy trình debug thực tế

1. Xác nhận **security chain nào** match request. Nếu có nhiều chain, xem matcher/order của chúng.
2. Xác nhận authentication thực sự **thành công** chưa. HTTP 401 thường không phải lỗi tên role.
3. Kiểm tra `Authentication.getAuthorities()` ở môi trường test hoặc log được kiểm soát; đừng dựa vào tên user/DB role mà chưa map.
4. Viết ra **chuỗi chính xác** mà rule yêu cầu: `hasRole("ADMIN")` → `ROLE_ADMIN` trong thiết lập mặc định; `hasAuthority("ADMIN")` → `ADMIN`.
5. Kiểm tra thứ tự `pathMatchers`, method GET/POST và default deny.
6. Nếu dùng JWT/OIDC, xem converter biến claim ra authorities gì, tránh lộ raw token khi debug.
7. Nếu request đi qua method security hoặc service-level authorization, kiểm tra thêm rule của tầng đó.
8. Nếu request là POST/PUT/DELETE, xem xét CSRF trước khi kết luận 403 do thiếu authority.

## 15. Bài tập luyện tập và đáp án

**Câu 1.** User có duy nhất `GrantedAuthority("ROLE_ADMIN")`. Hai rule `hasRole("ADMIN")` và `hasAuthority("ADMIN")` cho kết quả nào?  
**Đáp án:** Rule thứ nhất đúng, rule thứ hai sai. Nếu muốn dùng `hasAuthority` để khớp, yêu cầu `hasAuthority("ROLE_ADMIN")`.

**Câu 2.** User có duy nhất `GrantedAuthority("ADMIN")`. Gọi `hasRole("ADMIN")` có đúng không?  
**Đáp án:** Không trong HTTP WebFlux với prefix mặc định, vì `hasRole` cần `ROLE_ADMIN`. `hasAuthority("ADMIN")` mới đúng.

**Câu 3.** `.roles("ADMIN")` có tạo ra authority `ADMIN` không?  
**Đáp án:** Nó tạo `ROLE_ADMIN`, không phải `ADMIN`.

**Câu 4.** `.roles("ROLE_ADMIN")` có tạo `ROLE_ROLE_ADMIN` không?  
**Đáp án:** API User builder chuẩn từ chối role đầu vào đã có `ROLE_` thay vì cho phép dùng như vậy. Dùng `.roles("ADMIN")`.

**Câu 5.** Role `ROLE_ADMIN` có mặc nhiên cho quyền `report:read` không?  
**Đáp án:** Không. Phải cấp thêm permission, dùng mapping/hierarchy hoặc viết chính sách cho admin phù hợp.

**Câu 6.** `hasAnyRole("ADMIN", "EDITOR")` yêu cầu cả hai role hay chỉ một?  
**Đáp án:** Chỉ cần ít nhất một. Đây là OR.

**Câu 7.** Scope JWT `reports.read` thường được mapper mặc định thành authority nào?  
**Đáp án:** Trong resource server dùng converter scope mặc định thường là `SCOPE_reports.read`, không phải `ROLE_reports.read`.

**Câu 8.** Tại sao người dùng đăng nhập đúng password nhưng vẫn nhận 403?  
**Đáp án:** Authentication đã thành công nhưng authorization không tìm thấy authority mà endpoint yêu cầu, hoặc có rule khác (CSRF, default deny, object-level permission) từ chối.

**Câu 9.** Có nên dùng `GrantedAuthorityDefaults` rồi coi `hasRole` ở mọi tầng lập tức đổi prefix không?  
**Đáp án:** Không. Cơ chế cấu hình prefix có phạm vi riêng; phải xác minh từng API, đặc biệt WebFlux HTTP rule so với reactive method security. `hasAuthority("APP_ADMIN")` là cách yêu cầu tên đặc thù rõ ràng.

**Câu 10.** User có `ROLE_READER` và `report:read`; `.pathMatchers("/api/report").hasAuthority("report:read")` có cho phép?  
**Đáp án:** Có, nếu người dùng đã được xác thực hợp lệ và không có chốt bảo mật khác từ chối.

**Câu 11.** Nếu `/api/**` yêu cầu `authenticated()` nằm trước `/api/admin/**` yêu cầu `hasRole("ADMIN")`, có lỗi gì?  
**Đáp án:** Rule rộng có thể match trước và chỉ yêu cầu đăng nhập, khiến rule admin không được áp dụng như mong muốn. Đặt matcher hẹp trước.

**Câu 12.** Khi identity provider gửi claim `roles:["ADMIN"]`, có thể kết luận Spring Security đã cấp `ROLE_ADMIN`?  
**Đáp án:** Không. Cần biết chính xác converter ánh xạ claim thành `GrantedAuthority` nào.

### Bài thực hành thêm

1. Sửa `reader` trong demo để chỉ còn `ROLE_READER`, bỏ `report:read`. Chạy lại test `readerPermissionPassesHasAuthorityReportRead` và giải thích vì sao nhận 403.
2. Thử đổi `/api/admin-exact` từ `hasAuthority("ROLE_ADMIN")` thành `hasAuthority("ADMIN")`. Dự đoán user `admin` và `raw` đổi kết quả như thế nào.
3. Thêm endpoint `/api/ops` với `hasAnyAuthority("report:read","SCOPE_reports.read")`; kiểm tra user reader/scoped.
4. Thêm phương thức POST `/api/report` cần `report:write`; giữ CSRF nếu dùng browser-based credentials và xây dựng test gửi CSRF token hợp lệ.
5. Thử khai báo `pathMatchers("/api/**").permitAll()` trước `/api/admin` và viết một test phát hiện rule nhạy cảm bị rule rộng phủ.
6. Nếu ứng dụng có method security, thêm test trên service để xác minh prefix được dùng đúng ở cả HTTP và method, không chỉ ở HTTP.

## 16. Checklist khi triển khai

- [ ] Xác định role naming convention rõ ràng (`ROLE_` hoặc quy ước riêng).
- [ ] Cần phân biệt role cấp nhóm và permission cụ thể; không dùng tên nhóm để thay thế quyền tài nguyên nếu không có chính sách.
- [ ] `hasRole("ADMIN")` dùng tên **không prefix** trong WebFlux HTTP rule mặc định.
- [ ] `hasAuthority("ROLE_ADMIN")` kiểm tra **chuỗi đầy đủ**, không thêm prefix.
- [ ] `User.roles(...)` tự tạo `ROLE_`; `User.authorities(...)` dùng tên đúng như truyền vào.
- [ ] Không cộng dồn `.roles(...)` và `.authorities(...)` một cách mơ hồ.
- [ ] Mapper từ JWT/DB/LDAP/OIDC tạo đúng authorities và tránh double prefix.
- [ ] Phân biệt `SCOPE_` với `ROLE_`, kiểm tra converter thực tế.
- [ ] Rule nhạy cảm khai báo trước rule rộng, `anyExchange().denyAll()` cuối.
- [ ] Có test HTTP 401 không credentials, 403 thiếu quyền, 200 khi đúng role/authority.
- [ ] Có test từng security chain, method security và object/tenant authorization nếu được sử dụng.
- [ ] Không giả định ROLE_ADMIN tự cấp ROLE_READER hoặc mọi permission.
- [ ] Không log raw password/token, giữ HTTPS và password hashing.
- [ ] Với API WebFlux, dùng `SecurityWebFilterChain` và `ServerHttpSecurity`.

## 17. Tóm tắt và nguồn tham khảo

**Quy tắc nhớ nhanh:**

```text
hasRole("ADMIN")                   -> cần "ROLE_ADMIN"
hasAuthority("ADMIN")              -> cần "ADMIN"
hasAuthority("ROLE_ADMIN")         -> cần "ROLE_ADMIN"
hasAnyRole("ADMIN", "EDITOR")       -> cần một trong "ROLE_ADMIN", "ROLE_EDITOR"
hasAnyAuthority("A", "B")           -> cần một trong "A", "B"
User.roles("ADMIN")                -> cấp "ROLE_ADMIN"
User.authorities("ADMIN")          -> cấp "ADMIN"
User.authorities("report:read")    -> cấp "report:read"
```

Tất cả kiểm tra này thuộc **HTTP authorization** khi khai báo qua `ServerHttpSecurity.authorizeExchange`. `ROLE_` không phải phép biến đổi tùy ý áp dụng cho mọi chuỗi quyền; giá trị thực tế lấy từ `Authentication.getAuthorities()`, và người gọi phải xác thực thành công trước khi kiểm tra role/authority của tài nguyên được bảo vệ.

**Tài liệu chính thức:**

- Spring Security 6.5 – `ServerHttpSecurity`, `authorizeExchange`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.html
- Spring Security 6.5 – `ServerHttpSecurity.AuthorizeExchangeSpec.Access`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.AuthorizeExchangeSpec.Access.html
- Spring Security 6.5 – `AuthorityReactiveAuthorizationManager`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/AuthorityReactiveAuthorizationManager.html
- Spring Security 6.5 – `User.UserBuilder` (`roles`/`authorities`): https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/userdetails/User.UserBuilder.html
- Spring Security 6.5 – Reactive Web Security: https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html
- Spring Security 6.5 – Reactive Authorization: https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/authorize-http-requests.html
- Spring Security 6.5 – Reactive Method Security: https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/method.html
- Spring Security 6.5 – Reactive testing with WebTestClient: https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/setup.html
- Spring Boot 3.5.16 release notice (end of OSS support for 3.5.x): https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now/
