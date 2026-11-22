# GrantedAuthority và SimpleGrantedAuthority trong Spring Security

Khi người dùng đăng nhập thành công, ứng dụng cần biết **người đó là ai** và **người đó được cấp những quyền gì**. Trong Spring Security, thông tin danh tính được thể hiện qua `Authentication`, còn các quyền gắn với danh tính đó được biểu diễn bằng các đối tượng **`GrantedAuthority`**. Triển khai phổ biến nhất để lưu một quyền dạng chuỗi là **`SimpleGrantedAuthority`**.

Ví dụ, một người dùng có thể có các authority sau:

```text
ROLE_USER
report:read
invoice:approve
```

Ba chuỗi này không có cùng ý nghĩa nghiệp vụ: `ROLE_USER` thường là một vai trò, `report:read` là quyền đọc báo cáo, còn `invoice:approve` là quyền phê duyệt hóa đơn. Nhưng đối với cơ chế kiểm tra authority dạng chuỗi, chúng đều có thể được đưa vào `Authentication.getAuthorities()` dưới dạng `SimpleGrantedAuthority`.

**Điểm cần ghi nhớ:** `GrantedAuthority` cho biết quyền nào đã được **gắn với chủ thể sau một quá trình xác thực/ánh xạ đáng tin cậy**. Nó không tự xác thực password, không quyết định đúng/sai của mọi chính sách nghiệp vụ và không thay thế việc kiểm tra owner, tenant hay trạng thái của một bản ghi cụ thể.

Bài này trình bày khái niệm, API, cách tạo/lấy/kiểm tra quyền, mối quan hệ với role và OAuth2 scope, giới hạn của authority dạng chuỗi, cách tích hợp trong **Spring Boot 3 / Spring Security 6, Java 17+**, và một bài Java 17 độc lập để luyện cách suy luận. Các đoạn sử dụng `HttpSecurity` thuộc **Spring MVC / Servlet**; WebFlux sử dụng cấu hình tương ứng của hệ reactive.

## 1. Phân biệt principal, credentials, authorities và quyết định truy cập

`Authentication` là interface thể hiện yêu cầu xác thực hoặc người dùng hiện tại đã được xác thực. Ba thuộc tính thường được nhắc tới:

| Thuộc tính | Câu hỏi trả lời | Ví dụ |
| --- | --- | --- |
| `principal` | **Ai** đang được đại diện? | User ID `u-100`, username `alice`, JWT subject |
| `credentials` | **Bằng chứng nào** được dùng để chứng minh danh tính? | Password, bearer token hoặc chứng chỉ, tùy cơ chế |
| `authorities` | Chủ thể đã được **cấp những quyền/nhãn quyền nào**? | `ROLE_USER`, `ROLE_ADMIN`, `report:read`, `SCOPE_orders.read` |
| **Authorization policy** | Chủ thể đó **có được làm hành động này với tài nguyên này** không? | `hasAuthority("report:read")`, policy kiểm tra owner/tenant |

Ví dụ, Alice đã được xác thực có `ROLE_USER` và `report:read`. Rule `hasAuthority("report:read")` có thể cho phép Alice vào endpoint xem báo cáo. Nhưng nếu báo cáo ID 500 thuộc công ty khác, ứng dụng vẫn cần kiểm tra phạm vi dữ liệu, quan hệ sở hữu hoặc các điều kiện nghiệp vụ khác. Việc có một authority **không mặc nhiên** mở mọi resource.

Sơ đồ khái niệm:

```text
Credentials từ client
       |
       v
AuthenticationManager / AuthenticationProvider
       |  kiểm tra password/token và nguồn danh tính
       v
Authentication đã xác thực
       |
       +-- principal    -> ai?
       +-- credentials  -> thường được xóa/giảm tồn tại sau xác thực
       +-- authorities  -> Collection<GrantedAuthority>
                                |
                                v
                    AuthorizationManager / @PreAuthorize
                                |
                                v
                    Domain policy: owner/tenant/state
                                |
                                v
                         ALLOW hoặc DENY
```

Đây là mô hình trách nhiệm. Luồng xác thực thực tế phụ thuộc HTTP Basic, form login, OAuth2/OIDC, JWT và cách ứng dụng lưu `SecurityContext`; không phải mọi request đều xác thực lại bằng username/password.

## 2. Interface GrantedAuthority: một quyền cấp cho Authentication

### 2.1. Định nghĩa cốt lõi

Trong Spring Security, `GrantedAuthority` là một interface ở package `org.springframework.security.core`. Hình dạng cơ bản:

```java
public interface GrantedAuthority extends java.io.Serializable {
    String getAuthority();
}
```

Trong Javadoc hiện đại, `getAuthority()` có thể trả **`null`** nếu authority quá phức tạp để biểu diễn chính xác bằng một chuỗi. Đoạn khai báo rút gọn trên phục vụ giải thích, chưa thể hiện annotation nullability của từng phiên bản.

Trách nhiệm:

- **`GrantedAuthority`** nói “đây là một quyền/nhãn quyền được cấp”.
- **`getAuthority()`** trả chuỗi đại diện, khi chuỗi đủ để một `AuthorizationManager` kiểm tra.
- **`Authentication.getAuthorities()`** trả `Collection<? extends GrantedAuthority>` cho danh tính hiện tại.
- **`AuthorizationManager`** hoặc các biểu thức như `hasAuthority` giải thích authority đó trong ngữ cảnh bảo vệ một request/method.

Một `GrantedAuthority` **không có sẵn thông tin password**, không tự gọi database và không tự quyết định quyền trên tài nguyên cụ thể. Nó là dữ liệu đầu vào của chính sách authorization.

### 2.2. Ví dụ trả về chuỗi

```java
GrantedAuthority authority =
    new SimpleGrantedAuthority("report:read");

String value = authority.getAuthority();
// value bằng "report:read"
```

`SimpleGrantedAuthority` nằm ở package:

```java
import org.springframework.security.core.authority.SimpleGrantedAuthority;
```

Khi code đọc `authentication.getAuthorities()`, mỗi phần tử có thể được biểu diễn bằng chuỗi này.

### 2.3. Khi nào getAuthority() có thể trả null?

Một authority phức tạp có thể mô tả “được duyệt hóa đơn của các khách hàng nằm trong tập X với ngưỡng tiền Y”, khó biểu diễn thành một String duy nhất mà vẫn đủ chính xác. Nếu custom implementation trả `null`, các rule so sánh chuỗi thông thường như `hasAuthority("invoice:approve")` **không tự hiểu object ấy**. Khi đó phải có `AuthorizationManager` hoặc thành phần chính sách **biết rõ kiểu dữ liệu custom** và đánh giá các trường riêng.

Ví dụ minh họa (fragment, không phải chương trình Java độc lập):

```java
final class AccountScopedAuthority implements GrantedAuthority {
    private static final long serialVersionUID = 1L;

    private final Set<String> allowedAccountIds;

    AccountScopedAuthority(Set<String> allowedAccountIds) {
        this.allowedAccountIds = Set.copyOf(allowedAccountIds);
    }

    Set<String> allowedAccountIds() {
        return allowedAccountIds;
    }

    @Override
    public String getAuthority() {
        return null; // Cần AuthorizationManager hiểu kiểu custom này.
    }
}
```

Trong một ứng dụng thật, cần import `GrantedAuthority`, `Set` và xây dựng chính sách xử lý `AccountScopedAuthority` đầy đủ. Đừng tạo custom authority chỉ để chứa một chuỗi đơn giản; `SimpleGrantedAuthority` đã đáp ứng tốt nhu cầu đó.

**Thực tế:** dùng authority dạng chuỗi cho vai trò, scope và permission mức ứng dụng; dùng domain policy hoặc policy engine cho quyết định dựa trên object, tenant, amount và trạng thái.

## 3. SimpleGrantedAuthority: triển khai đơn giản nhất

### 3.1. Tạo và đọc một quyền

`SimpleGrantedAuthority` là lớp có sẵn của Spring Security, nhận một chuỗi authority trong constructor.

```java
GrantedAuthority userRole =
    new SimpleGrantedAuthority("ROLE_USER");

GrantedAuthority reportPermission =
    new SimpleGrantedAuthority("report:read");

System.out.println(userRole.getAuthority());
System.out.println(reportPermission.getAuthority());
```

**Output của đoạn code, khi đặt trong chương trình Java có Spring Security dependency:**

```text
ROLE_USER
report:read
```

Chuỗi truyền vào được giữ làm authority. `SimpleGrantedAuthority` không tự đổi `"ADMIN"` thành `"ROLE_ADMIN"`, không tự thêm `SCOPE_` và không tự giải mã JWT. Việc đặt tên nhất quán do ứng dụng hoặc converter quyết định.

### 3.2. String authority là giá trị so khớp chính xác

Hai đối tượng biểu diễn cùng một authority:

```java
var a = new SimpleGrantedAuthority("ROLE_USER");
var b = new SimpleGrantedAuthority("ROLE_USER");
var c = new SimpleGrantedAuthority("ROLE_ADMIN");

System.out.println(a.equals(b)); // true
System.out.println(a.equals(c)); // false
```

`SimpleGrantedAuthority` dùng giá trị chuỗi authority để so sánh bằng `equals`/`hashCode`. Đây là đặc tính hữu ích khi lưu trong `Set` hoặc kiểm tra một quyền có tồn tại không. Không có cơ chế tự hiểu nghĩa “USER nhỏ hơn ADMIN” từ tên chuỗi.

Cũng cần lưu ý:

- `"ROLE_USER"` và `"role_user"` là **hai chuỗi khác nhau**.
- `"report:read"` và `"report:write"` là **hai quyền khác nhau**.
- `"ADMIN"` và `"ROLE_ADMIN"` không tự tương đương.
- Nếu có prefix custom hoặc role hierarchy, hiệu lực kiểm tra đến từ cấu hình **authorization**, không phải từ constructor `SimpleGrantedAuthority`.
- Constructor yêu cầu một chuỗi authority có nội dung. Đừng tạo authority rỗng hoặc dùng `null` như cách biểu diễn “không có quyền”; không có quyền nên được biểu diễn bằng danh sách authority phù hợp.

### 3.3. Một quyền và một tập quyền

Một instance `SimpleGrantedAuthority` mô tả một nhãn quyền. Một người dùng thường có **nhiều authorities**:

```java
List<GrantedAuthority> authorities = List.of(
    new SimpleGrantedAuthority("ROLE_USER"),
    new SimpleGrantedAuthority("report:read"),
    new SimpleGrantedAuthority("invoice:approve")
);
```

Nếu cần loại trùng, có thể dùng `Set`, nhưng khi làm việc với `Authentication.getAuthorities()` không nên tự giả định collection trả về là `Set`, có thể sửa đổi được, hoặc có thứ tự cụ thể. Để hiển thị một danh sách ổn định:

```java
List<String> names = authentication.getAuthorities()
    .stream()
    .map(GrantedAuthority::getAuthority)
    .filter(java.util.Objects::nonNull)
    .sorted()
    .toList();
```

Đoạn này xử lý cả trường hợp custom `GrantedAuthority` trả `null`. Không nên đưa danh sách authorities của tất cả user ra public API tùy tiện; chỉ trả phần dữ liệu phù hợp với mục đích và chính sách bảo mật.

### 3.4. SimpleGrantedAuthority không phải người dùng

Đừng nhầm:

```text
UserDetails / principal
    -> mô tả một người dùng hoặc chủ thể

Authentication
    -> biểu diễn trạng thái xác thực của chủ thể
    -> chứa collection authorities

SimpleGrantedAuthority
    -> chỉ biểu diễn MỘT chuỗi quyền đã cấp
```

Việc tạo:

```java
new SimpleGrantedAuthority("ROLE_ADMIN");
```

không làm người đang gọi request trở thành admin. Chỉ khi nguồn danh tính đáng tin cậy cấp authority đó và provider/converter tạo `Authentication` phù hợp, policy mới có thể sử dụng nó. Không cho phép client gửi một chuỗi `ROLE_ADMIN` rồi tự gắn vào `SecurityContext`.

## 4. Role, authority và scope: nhận diện prefix

### 4.1. hasRole và hasAuthority là hai cách kiểm tra khác nhau

| Kiểm tra trong Spring Security | Giá trị authority cần có (mặc định) | Kết luận |
| --- | --- | --- |
| `hasRole("USER")` | `ROLE_USER` | Cho phép nếu có role USER |
| `hasRole("ADMIN")` | `ROLE_ADMIN` | Cho phép nếu có role ADMIN |
| `hasAuthority("ROLE_ADMIN")` | `ROLE_ADMIN` | So khớp chính xác cùng chuỗi |
| `hasAuthority("ADMIN")` | `ADMIN` | Khác với `ROLE_ADMIN` |
| `hasAuthority("report:read")` | `report:read` | Kiểm tra permission cụ thể |
| `hasAuthority("SCOPE_orders.read")` | `SCOPE_orders.read` | Kiểm tra authority thường ánh xạ từ OAuth2 scope |
| `hasAnyAuthority("report:read","report:write")` | Một trong hai chuỗi | Kết hợp các quyền độc lập |

Trong cấu hình mặc định của Spring Security, `hasRole("ADMIN")` là cách thuận tiện để yêu cầu `ROLE_ADMIN`. Prefix mặc định có thể được tùy chỉnh; đừng viết logic dựa vào assumption đã thay đổi mà không kiểm tra cấu hình thực tế.

Ví dụ Alice có:

```text
ROLE_USER
report:read
```

Khi gọi:

```java
.requestMatchers("/api/reports").hasAuthority("report:read")
.requestMatchers("/api/admin").hasRole("ADMIN")
```

Alice có thể vượt qua rule đọc báo cáo nhưng không có role admin. **Authentication hợp lệ và role USER không tự làm xuất hiện ROLE_ADMIN.**

### 4.2. User.withUsername(...).roles(...) so với authorities(...)

Với builder tích hợp trong Spring Security:

```java
UserDetails reader = User.withUsername("reader")
    .password(encodedPassword)
    .roles("USER")
    .build();
```

`roles("USER")` đưa authority có prefix `ROLE_USER` vào user được tạo. Nếu muốn thêm permission không phải role, có thể dùng:

```java
UserDetails reader = User.withUsername("reader")
    .password(encodedPassword)
    .authorities("ROLE_USER", "report:read")
    .build();
```

**Không chain `.roles("USER").authorities("report:read")` rồi mặc định cả hai được cộng dồn:** các method builder thiết lập danh sách quyền; tùy API, lời gọi sau có thể thay thế danh sách trước. Hãy chỉ định đầy đủ các authority mong muốn trong một lời gọi hoặc kiểm tra rõ kết quả `getAuthorities()` bằng test.

`.roles("ROLE_USER")` là cách dùng sai quy ước trong builder vì `roles` dự kiến nhận tên role **không có** prefix. Dùng `.roles("USER")` hoặc `.authorities("ROLE_USER")` cho rõ ý định.

### 4.3. Role hierarchy không tự tồn tại từ tên

Một ứng dụng có thể muốn `ADMIN > USER`, tức admin có mọi quyền dành cho USER. Nhưng nếu chỉ tạo:

```java
new SimpleGrantedAuthority("ROLE_ADMIN")
```

thì object này **không tự chứa ROLE_USER**. Nếu policy `hasRole("USER")` cần chấp nhận admin, có thể:

1. Gán đồng thời `ROLE_ADMIN` và `ROLE_USER` cho admin; hoặc
2. Cấu hình một `RoleHierarchy` tương thích và bảo đảm authorization component sử dụng hierarchy đó.

Không suy ra các chuỗi `ROLE_SUPER_ADMIN`, `ROLE_ADMIN`, `ROLE_USER` có thứ bậc dựa trên tên. Kiểm tra bằng test cả trường hợp admin có/không có quyền kế thừa ở đúng version/config.

### 4.4. Scope từ JWT và tiền tố SCOPE_

Trong OAuth2 Resource Server, converter mặc định thường ánh xạ scope `orders.read` từ claim `scope` hoặc `scp` của token **đã được xác minh** thành `SCOPE_orders.read`.

```text
Token claim (đã verify): scope = "orders.read orders.write"
                 |
                 v
JwtGrantedAuthoritiesConverter
                 |
                 v
SimpleGrantedAuthority("SCOPE_orders.read")
SimpleGrantedAuthority("SCOPE_orders.write")
```

Tuy nhiên:

- Converter và prefix có thể được cấu hình khác; phải đọc config thực tế.
- Chữ ký token, issuer, audience, thời hạn và các kiểm tra tin cậy khác **phải được xác minh trước** khi dùng claims làm quyền.
- `SCOPE_orders.read` chỉ thể hiện scope đọc cấp khái quát, không tự cho phép đọc đơn hàng của tenant khác.
- Không dùng nguyên JSON claim `roles` do client tự gửi trong body làm authority.

## 5. GrantedAuthority đi vào Authentication như thế nào?

### 5.1. Username/password

Ví dụ ứng dụng dùng `UserDetailsService` và `DaoAuthenticationProvider`:

```text
Client gửi username/password
         |
         v
AuthenticationProvider kiểm tra credentials
         |
         +-- UserDetailsService.loadUserByUsername(username)
         |       |
         |       +-- UserDetails.getAuthorities()
         |                ROLE_USER, report:read
         |
         +-- PasswordEncoder.matches(raw, storedHash)
         |
         v
Authentication thành công
         |
         +-- principal = user đã xác minh
         +-- credentials = có thể được xóa sau xác thực
         +-- authorities = quyền từ nguồn đáng tin cậy
         |
         v
SecurityContext -> AuthorizationManager
```

`UserDetailsService` cung cấp thông tin người dùng; `PasswordEncoder` thực hiện so khớp password theo cơ chế phù hợp; provider quyết định xác thực thành công hoặc thất bại. Authorities từ user store là dữ liệu để authorization sử dụng.

### 5.2. JWT

Với JWT resource server, `JwtDecoder` xác minh token theo cấu hình và `JwtAuthenticationConverter` ánh xạ principal/authorities. Mặc định thông thường là `JwtAuthenticationToken` với authority scope. Nếu cần map role custom từ IdP, chỉ thực hiện chuyển đổi sau khi token đã được xác minh theo trust policy; tránh coi mọi claim tên `role` là sự thật.

### 5.3. Form login và session

Sau form login, `Authentication` đã xác thực có thể được lưu trong `SecurityContext` gắn với session theo chính sách hiện tại. Những authority trong session là trạng thái **được chụp khi context được tạo** hoặc khôi phục. Nếu quyền user thay đổi trong database, các phiên/tokens còn hoạt động **không nhất thiết tự cập nhật ngay**. Ứng dụng cần chính sách refresh, revoke hoặc kiểm tra quyền runtime phù hợp với mức rủi ro.

### 5.4. Anonymous không đồng nghĩa user login

`AnonymousAuthenticationToken` có thể xuất hiện trong context của một request public. Nó có thể mang authority `ROLE_ANONYMOUS` và có cờ `isAuthenticated() == true` ở mức token. Nhưng policy `authenticated()` của Spring Security có ngữ nghĩa loại trừ anonymous.

Do đó, không dùng `authentication != null` hoặc kiểm tra thủ công `isAuthenticated()` như một shortcut thay cho `authenticated()`, `hasAuthority` hoặc các rule policy khác.

## 6. Từ danh sách GrantedAuthority tới quyết định authorization

Một rule HTTP thông dụng:

```java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/public").permitAll()
    .requestMatchers("/api/reports").hasAuthority("report:read")
    .requestMatchers("/api/admin").hasRole("ADMIN")
    .anyRequest().authenticated()
);
```

`authorizeHttpRequests` thuộc cấu hình Spring Security Servlet hiện đại. Nó gắn rule với request; tùy rule, `AuthorizationManager` sử dụng `Authentication` hiện tại và danh sách authorities để quyết định cho phép.

Ở tầng service, method security có thể dùng:

```java
@PreAuthorize("hasAuthority('report:read')")
public ReportDto readReport(long id) {
    return reportPolicy.readAuthorizedReport(id);
}
```

Đây là fragment. Ứng dụng phải bật `@EnableMethodSecurity` và gọi phương thức qua ranh giới proxy phù hợp. `reportPolicy` cần được hiện thực để kiểm tra quyền của principal trên report ID cụ thể; `hasAuthority` một mình chỉ kiểm tra authority đã cấp.

### 6.1. Vai trò của authorities trong chính sách

| Câu hỏi | Có thể dùng SimpleGrantedAuthority? | Lớp cần thiết khác |
| --- | --- | --- |
| Đã được cấp quyền `report:read`? | Có | Đọc từ `Authentication.getAuthorities()` |
| Có role `ROLE_ADMIN`? | Có | Role matcher/prefix đúng |
| Token có scope `orders.read` đã được verify? | Có, sau khi converter ánh xạ | Token verification, issuer/audience/thời hạn |
| Có được xem Order ID 123 của người khác? | Không đủ | Object/tenant/owner authorization |
| Có được duyệt invoice ở trạng thái `PENDING`? | Không đủ | Business-state policy, transaction |
| Có được dùng quota vượt mức không? | Không đủ | Rate/quota policy |
| Có được truy cập account ID thuộc whitelist động không? | Chuỗi khái quát thường không đủ | Domain lookup hoặc custom policy |

Đừng thiết kế một authority cho **mỗi** object ID trong một hệ thống có hàng triệu object trừ khi có lý do rất cụ thể. Các collection authorities quá lớn làm tăng chi phí xác thực, token/session size và độ khó khi thu hồi quyền. Authorization theo domain object phù hợp hơn cho quyền thay đổi theo từng bản ghi.

### 6.2. Phân biệt deny vì authority với lỗi authentication

- **401 Unauthorized** (thường với HTTP Basic): thiếu hoặc sai credentials ở endpoint yêu cầu login.
- **403 Forbidden**: đã xác thực nhưng thiếu authority/role hoặc bị một cơ chế khác từ chối như CSRF.
- **200 OK**: request được phép và controller trả thành công trong ví dụ.
- **404 Not Found**: endpoint hoặc object không tồn tại; ứng dụng có thể cố ý ẩn sự tồn tại của tài nguyên theo chính sách phù hợp.

Một HTTP 403 **không chứng minh riêng** rằng thiếu `SimpleGrantedAuthority`; CSRF, rule trên object hoặc filter khác cũng có thể gây từ chối. Khi kiểm thử authority với POST, cần gửi CSRF token hợp lệ theo cấu hình để không bị một lớp khác chặn trước.

## 7. Ví dụ Spring Boot 3 hoàn chỉnh: cấp và kiểm tra authorities

Bộ ví dụ sau dùng **Spring MVC/Servlet, Spring Security 6, Java 17+**. Mục tiêu là xem rõ sự khác biệt giữa danh sách authority và các rule `hasRole`, `hasAuthority`, `@PreAuthorize`.

Có ba tài khoản demo:

| Username | Password local | Authorities |
| --- | --- | --- |
| `reader` | `reader-pass` | `ROLE_USER`, `report:read` |
| `approver` | `approver-pass` | `ROLE_USER`, `invoice:approve` |
| `admin` | `admin-pass` | `ROLE_USER`, `ROLE_ADMIN`, `report:read`, `invoice:approve` |

Chính sách:

- `GET /api/public`: ai cũng truy cập được.
- `GET /api/whoami`: user đã xác thực; trả tên và danh sách authority đã sort.
- `GET /api/user-zone`: cần role USER.
- `GET /api/admin`: cần role ADMIN.
- `GET /api/reports`: cần authentication tại HTTP và `report:read` ở service.
- `POST /api/invoice-approvals`: cần `invoice:approve` và CSRF token hợp lệ trong mô hình demo.

### 7.1. Dependency Gradle

Trong dự án Spring Boot 3 đã có plugin, repository và dependency management phù hợp, phần `dependencies` của `build.gradle` (Groovy DSL):

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Đây không phải toàn bộ file Gradle; dự án cần Spring Boot plugin và Java toolchain. Với Maven, sử dụng các starter tương ứng và `spring-security-test` ở `test` scope. Để Spring Boot BOM quản lý phiên bản Spring Security, tránh trộn các module có version không tương thích.

### 7.2. Lớp main

Tạo `src/main/java/example/authorities/AuthorityDemoApplication.java`:

```java
package example.authorities;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AuthorityDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(AuthorityDemoApplication.class, args);
    }
}
```

### 7.3. SecurityConfig: cấp quyền từ nguồn đáng tin cậy

Tạo `src/main/java/example/authorities/SecurityConfig.java`:

```java
package example.authorities;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
            .password(encoder.encode("reader-pass"))
            .authorities("ROLE_USER", "report:read")
            .build();

        UserDetails approver = User.withUsername("approver")
            .password(encoder.encode("approver-pass"))
            .authorities("ROLE_USER", "invoice:approve")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin-pass"))
            .authorities(
                "ROLE_USER", "ROLE_ADMIN",
                "report:read", "invoice:approve"
            )
            .build();

        return new InMemoryUserDetailsManager(reader, approver, admin);
    }

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/whoami")
                    .authenticated()
                .requestMatchers(HttpMethod.GET, "/api/user-zone")
                    .hasRole("USER")
                .requestMatchers(HttpMethod.GET, "/api/admin")
                    .hasRole("ADMIN")
                .requestMatchers(HttpMethod.GET, "/api/reports")
                    .authenticated()
                .requestMatchers(HttpMethod.POST, "/api/invoice-approvals")
                    .hasAuthority("invoice:approve")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .csrf(Customizer.withDefaults())
            .build();
    }
}
```

Tại đây:

1. `UserDetailsService` cấp quyền từ dữ liệu server kiểm soát; password demo được băm bằng BCrypt. Trong production cần nguồn danh tính thật và cách quản lý credential phù hợp.
2. `.authorities("ROLE_USER", "report:read")` gắn **hai chuỗi authority** cho reader, tương đương các `SimpleGrantedAuthority` tương ứng.
3. `.hasRole("USER")` nhìn kiếm `ROLE_USER`, còn `.hasRole("ADMIN")` tìm `ROLE_ADMIN` theo prefix mặc định.
4. `.hasAuthority("invoice:approve")` tìm **đúng chuỗi**; role USER không tự đủ cho invoice approval.
5. `.authenticated()` chỉ yêu cầu danh tính tin cậy, không đủ để đọc báo cáo nếu service còn có `@PreAuthorize`.
6. `.csrf(Customizer.withDefaults())` giữ lớp bảo vệ CSRF; POST cần token tương ứng. Các request GET ở demo không cần CSRF token.
7. `anyRequest().denyAll()` ngăn những route chưa khai báo trở thành public ngoài ý muốn.

Không nhầm phương thức `.authorities(...)` của builder với một endpoint cho client tự cấp quyền: đây là **bean cấu hình được người phát triển kiểm soát**, không phải dữ liệu JSON do client gửi.

### 7.4. Controller và service

Tạo `src/main/java/example/authorities/AuthorityController.java`:

```java
package example.authorities;

import java.util.List;
import java.util.Map;
import java.util.Objects;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
class AuthorityController {

    private final ReportService reportService;

    AuthorityController(ReportService reportService) {
        this.reportService = reportService;
    }

    @GetMapping("/public")
    Map<String, String> publicInfo() {
        return Map.of("message", "public");
    }

    @GetMapping("/whoami")
    Map<String, Object> whoami(Authentication authentication) {
        List<String> authorities = authentication.getAuthorities()
            .stream()
            .map(GrantedAuthority::getAuthority)
            .filter(Objects::nonNull)
            .sorted()
            .toList();

        return Map.of(
            "username", authentication.getName(),
            "authorities", authorities
        );
    }

    @GetMapping("/user-zone")
    Map<String, String> userZone() {
        return Map.of("message", "user-zone");
    }

    @GetMapping("/admin")
    Map<String, String> admin() {
        return Map.of("message", "admin");
    }

    @GetMapping("/reports")
    Map<String, String> reports() {
        return Map.of("message", reportService.readReport());
    }

    @PostMapping("/invoice-approvals")
    Map<String, String> approveInvoice() {
        // Demo không ghi dữ liệu thật.
        return Map.of("message", "approved");
    }
}

@Service
class ReportService {

    @PreAuthorize("hasAuthority('report:read')")
    public String readReport() {
        return "report";
    }
}
```

Khi `GET /api/reports` được gọi, HTTP layer chỉ yêu cầu user đã login. Sau đó controller gọi **một bean Spring riêng** là `ReportService`. Method security từ `@EnableMethodSecurity` kiểm tra `report:read` trước khi chạy `readReport()`. Nếu approver không có authority này, Spring Security từ chối.

Vì `ReportService` là bean riêng được gọi qua dependency injection, lời gọi đi qua ranh giới mà Spring AOP/method security có thể áp dụng. Một `@PreAuthorize` được gọi nội bộ qua `this.method()` trong cùng bean có thể bỏ qua proxy, nên đừng mặc định annotation luôn chặn self-invocation.

**Hạn chế ví dụ:** `Map` response chỉ trả tên user và chuỗi quyền trong demo; production cần cân nhắc thông tin nào được lộ cho client. `approveInvoice()` chỉ trả chuỗi, không cập nhật hóa đơn; chưa có kiểm tra owner, tenant, trạng thái invoice hoặc transaction. Khi triển khai nghiệp vụ thật, các ràng buộc đó phải được bổ sung.

### 7.5. Chạy thủ công

Trong root dự án Spring Boot có Gradle Wrapper:

```bash
./gradlew bootRun
```

Trên Windows:

```powershell
.\gradlew.bat bootRun
```

Với ứng dụng demo trên `http://localhost:8080`:

```bash
# Public GET: 200
curl -i http://localhost:8080/api/public

# Thiếu authentication: HTTP Basic thường trả 401
curl -i http://localhost:8080/api/whoami

# Reader: có ROLE_USER, report:read
curl -i -u reader:reader-pass http://localhost:8080/api/whoami

# Reader có report:read: 200
curl -i -u reader:reader-pass http://localhost:8080/api/reports

# Approver thiếu report:read: 403 từ method security
curl -i -u approver:approver-pass http://localhost:8080/api/reports

# Reader thiếu ROLE_ADMIN: 403
curl -i -u reader:reader-pass http://localhost:8080/api/admin

# Admin có ROLE_ADMIN: 200
curl -i -u admin:admin-pass http://localhost:8080/api/admin

# Reader thiếu invoice:approve: POST thiếu CSRF có thể đã bị CSRF chặn
curl -i -X POST -u reader:reader-pass \
  http://localhost:8080/api/invoice-approvals
```

Dòng POST cuối **không kiểm chứng riêng thiếu authority**, vì mặc định CSRF đang bật. Để test rule quyền trên POST, dùng MockMvc `with(csrf())` trong mục tiếp theo hoặc triển khai cơ chế CSRF token thật. Tránh tắt CSRF toàn cục chỉ để gọi curl dễ hơn.

HTTP Basic chỉ Base64-encode username/password, vì vậy môi trường thật cần HTTPS. `curl -u` với password trên là giá trị demo cục bộ; không đưa secret thật vào history/process list hoặc log.

### 7.6. Kết quả JSON của whoami

Khi reader đăng nhập hợp lệ, response minh họa:

```json
{
  "username": "reader",
  "authorities": ["ROLE_USER", "report:read"]
}
```

Danh sách được sort để kết quả ổn định, nhưng thứ tự **các field JSON** do serializer quyết định. Response không chứa password hay password hash. Một `SimpleGrantedAuthority` chỉ mang chuỗi quyền, không chứa định danh user.

## 8. Kiểm thử với Spring Security Test và MockMvc

Để chứng minh cách `GrantedAuthority` ảnh hưởng authorization, viết test cả trường hợp có quyền, thiếu quyền, không có user và CSRF không hợp lệ. Dự án ví dụ đã thêm `spring-security-test` vào test classpath.

Tạo `src/test/java/example/authorities/AuthoritySecurityTest.java`:

```java
package example.authorities;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class AuthoritySecurityTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicEndpointAllowsAnonymous() throws Exception {
        mvc.perform(get("/api/public"))
            .andExpect(status().isOk());
    }

    @Test
    void privateEndpointRequiresAuthentication() throws Exception {
        mvc.perform(get("/api/whoami"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void wrongPasswordIsNotAuthentication() throws Exception {
        mvc.perform(get("/api/whoami")
                .with(httpBasic("reader", "wrong-password")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void readerHasExpectedAuthorities() throws Exception {
        mvc.perform(get("/api/whoami")
                .with(httpBasic("reader", "reader-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username").value("reader"))
            .andExpect(jsonPath("$.authorities[0]").value("ROLE_USER"))
            .andExpect(jsonPath("$.authorities[1]").value("report:read"));
    }

    @Test
    void reportRequiresMethodAuthority() throws Exception {
        mvc.perform(get("/api/reports")
                .with(httpBasic("reader", "reader-pass")))
            .andExpect(status().isOk());

        mvc.perform(get("/api/reports")
                .with(httpBasic("approver", "approver-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminRequiresRoleAdmin() throws Exception {
        mvc.perform(get("/api/admin")
                .with(httpBasic("reader", "reader-pass")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/api/admin")
                .with(httpBasic("admin", "admin-pass")))
            .andExpect(status().isOk());
    }

    @Test
    void invoiceApprovalRequiresAuthority() throws Exception {
        mvc.perform(post("/api/invoice-approvals")
                .with(httpBasic("reader", "reader-pass"))
                .with(csrf()))
            .andExpect(status().isForbidden());

        mvc.perform(post("/api/invoice-approvals")
                .with(httpBasic("approver", "approver-pass"))
                .with(csrf()))
            .andExpect(status().isOk());
    }

    @Test
    void csrfStillProtectsAuthorizedUser() throws Exception {
        mvc.perform(post("/api/invoice-approvals")
                .with(httpBasic("approver", "approver-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void userZoneChecksRoleUser() throws Exception {
        mvc.perform(get("/api/user-zone")
                .with(httpBasic("approver", "approver-pass")))
            .andExpect(status().isOk());
    }
}
```

Chạy:

```bash
./gradlew test --tests example.authorities.AuthoritySecurityTest
```

Trên Windows:

```powershell
.\gradlew.bat test --tests example.authorities.AuthoritySecurityTest
```

**Kỳ vọng theo cấu hình mẫu:** cả **9 phương thức test** thành công. Đây là kết quả dự kiến từ mã nguồn, **không phải chứng nhận đã chạy test trong tài liệu**. Nếu môi trường project khác, xác minh Boot/Security dependency, controller, proxy method security và test setup trước khi kết luận.

Các điểm mà test chứng minh:

| Test | Điều được kiểm tra | Kết luận |
| --- | --- | --- |
| Anonymous public/private | Authentication và rule HTTP | Public cho phép; private yêu cầu identity |
| Password sai | AuthenticationProvider | Không cấp user đáng tin cậy từ credentials sai |
| Reader whoami | `Authentication.getAuthorities()` | Các chuỗi authority đúng với user store |
| Report reader/approver | `@PreAuthorize` tại service | Có/thiếu `report:read` tạo kết quả khác nhau |
| Admin reader/admin | `hasRole("ADMIN")` | `ROLE_ADMIN` mới đáp ứng role |
| POST reader/approver có CSRF | `hasAuthority("invoice:approve")` | Quyền được kiểm tra khi request vượt qua CSRF |
| POST approver thiếu CSRF | Exploit protection | Đủ authority vẫn có thể bị chặn bởi CSRF |
| User zone | Role prefix | `ROLE_USER` khớp `hasRole("USER")` |

### 8.1. Dùng @WithMockUser và user() khi muốn cô lập authority

Trong một test chỉ kiểm tra authorization, có thể giả lập:

```java
@WithMockUser(authorities = {"ROLE_USER", "report:read"})
@Test
void reportIsVisibleToReader() {
    // MockMvc request to a protected controller
}
```

hoặc:

```java
mvc.perform(get("/api/reports")
        .with(user("reader").authorities(
            new SimpleGrantedAuthority("ROLE_USER"),
            new SimpleGrantedAuthority("report:read")
        )));
```

Đoạn ví dụ trên **chỉ là fragment kiểm thử** cần context/imports phù hợp. `@WithMockUser` và `user()` tạo một Authentication giả lập trong test, **không kiểm tra password thật**. Khi muốn chứng minh user store và `PasswordEncoder` hoạt động, bài test dùng `httpBasic(...)` như phần 8 sẽ đi qua authentication provider của ứng dụng.

### 8.2. Kiểm tra đúng nguyên nhân 403

Một test dùng POST mà không gửi CSRF token có thể nhận 403 **trước khi** kiểm tra authority. Do đó, bài test “reader thiếu `invoice:approve`” ở trên dùng `with(csrf())` để đảm bảo request không bị CSRF chặn. Test khác cố tình bỏ CSRF để chứng minh protection còn hoạt động.

Trong hệ thống thật, ngoài status code, kiểm tra không có record nào bị sửa, không gửi message hoặc thanh toán khi quyền bị từ chối. HTTP 403 không tự chứng minh thiếu side effect nếu nghiệp vụ đã chạy trước exception.

## 9. Java 17 độc lập: authority là chuỗi và quyết định cần điều kiện rõ ràng

Ví dụ sau **chạy bằng JDK 17 thuần**, không cần dependency Spring. Nó mô phỏng authority dạng chuỗi bằng Java `record` để người học suy luận trước khi đi vào Spring Security. Nó **không phải** một implementation bảo mật production; biến `authenticated` và tập quyền chỉ là dữ liệu mô phỏng.

Tạo file **`AuthorityDecisionDemo.java`**:

```java
import java.util.Set;

public class AuthorityDecisionDemo {

    record Grant(String name) {}

    record User(
        String name,
        boolean authenticated,
        Set<Grant> grants
    ) {}

    static boolean hasAuthority(User user, String required) {
        return user != null
            && user.authenticated()
            && user.grants() != null
            && user.grants().contains(new Grant(required));
    }

    static boolean hasRole(User user, String role) {
        return hasAuthority(user, "ROLE_" + role);
    }

    static boolean canReadOrder(User user, String ownerId) {
        return hasAuthority(user, "order:read")
            && user.name().equals(ownerId);
    }

    public static void main(String[] args) {
        User reader = new User(
            "alice", true,
            Set.of(new Grant("ROLE_USER"),
                   new Grant("report:read"),
                   new Grant("order:read"))
        );

        User admin = new User(
            "admin", true,
            Set.of(new Grant("ROLE_ADMIN"))
        );

        User guest = new User("guest", false, Set.of());

        System.out.println("Equal grants: "
            + new Grant("ROLE_USER").equals(new Grant("ROLE_USER")));
        System.out.println("Reader has USER role: "
            + hasRole(reader, "USER"));
        System.out.println("Reader has ADMIN role: "
            + hasRole(reader, "ADMIN"));
        System.out.println("Reader report read: "
            + hasAuthority(reader, "report:read"));
        System.out.println("Reader report READ: "
            + hasAuthority(reader, "report:READ"));
        System.out.println("Admin has USER role: "
            + hasRole(admin, "USER"));
        System.out.println("Guest has USER role: "
            + hasRole(guest, "USER"));
        System.out.println("Alice own order: "
            + canReadOrder(reader, "alice"));
        System.out.println("Alice Bob order: "
            + canReadOrder(reader, "bob"));
    }
}
```

Chạy:

```bash
javac AuthorityDecisionDemo.java
java AuthorityDecisionDemo
```

**Stdout chính xác:**

```text
Equal grants: true
Reader has USER role: true
Reader has ADMIN role: false
Reader report read: true
Reader report READ: false
Admin has USER role: false
Guest has USER role: false
Alice own order: true
Alice Bob order: false
```

Giải thích:

1. Hai Java record `Grant` có cùng giá trị chuỗi được `equals` xem bằng nhau, tương tự ý tưởng so khớp giá trị của `SimpleGrantedAuthority`.
2. `hasRole(reader, "USER")` thêm prefix `ROLE_`, kiểm tra đúng chuỗi `ROLE_USER`.
3. Reader thiếu `ROLE_ADMIN` nên check admin thất bại.
4. Chuỗi `report:read` và `report:READ` khác chữ hoa/chữ thường, không tự tương đương.
5. Admin chỉ có `ROLE_ADMIN`, không tự có `ROLE_USER`. Muốn kế thừa phải gán thêm hoặc cấu hình hierarchy.
6. Guest không được xác thực nên bị chặn dù giả sử có thể có chuỗi quyền nào đó.
7. Alice có `order:read` nhưng chỉ vượt qua policy đọc đơn **của Alice**; một order của Bob vẫn bị từ chối.

**Giới hạn rất quan trọng:** chương trình tự tạo `User(authenticated=true, grants=...)`, không kiểm tra credentials hoặc xác minh nguồn authority. Không tin các record này khi xây API thật. Trong Spring Security, `AuthenticationProvider`, `SecurityContext` và cơ chế authorization chính thức phải chịu trách nhiệm xây dựng và sử dụng danh tính/quyền đã được xác minh.

## 10. Cấp GrantedAuthority từ database, token hay hệ thống bên ngoài

### 10.1. Khi dùng database làm nguồn quyền

Giả sử database lưu:

```text
users
  id, username, password_hash, status

roles
  id, code                  # USER, ADMIN, ...

user_roles
  user_id, role_id

permissions
  id, code                  # report:read, invoice:approve

role_permissions
  role_id, permission_id
```

Khi load user, backend có thể chuyển role sang chuỗi `ROLE_ + code` và permission thành chuỗi như `report:read`, rồi tạo các `SimpleGrantedAuthority` thích hợp. Nguồn dữ liệu phải là cơ sở dữ liệu/trust boundary của ứng dụng, không phải mảng roles do client gửi.

Fragment minh họa (cần `RoleRepository`, entity và service thật):

```java
List<GrantedAuthority> authorities = roleCodes.stream()
    .map(code -> new SimpleGrantedAuthority("ROLE_" + code))
    .map(a -> (GrantedAuthority) a)
    .toList();
```

Nếu cần cả permissions, tạo một tập quyền có quy tắc rõ ràng và loại trùng theo nội dung. **Kiểm tra dữ liệu mã quyền** khi nạp từ DB: không cho phép một người dùng thường tự sửa role/permission của mình, không trộn tenant và không bỏ qua trạng thái tài khoản.

### 10.2. Khi dùng JWT

Token có thể mang scope hoặc role; sau khi ký/verify đúng issuer, audience, expiry và cấu hình trust, converter có thể tạo authorities. Ví dụ:

```text
JWT đã được verify:
sub = "user-100"
scope = "report.read invoice.read"

Authorities sau ánh xạ theo converter:
SCOPE_report.read
SCOPE_invoice.read
```

Nếu application policy viết `hasAuthority("report:read")` nhưng converter tạo `SCOPE_report.read`, rule sẽ không khớp. Không nên giải quyết bằng cách “cho phép mọi request”; hãy thống nhất **vocabulary** của quyền, cấu hình converter nếu cần và test payload thật.

### 10.3. Khi quyền thay đổi trong lúc session/token còn sống

Authorities thường được gắn vào `Authentication` tại thời điểm xác thực hoặc khôi phục/convert token. Nếu admin thu hồi quyền của một user, token hoặc session cũ không nhất thiết lập tức bị cập nhật. Tùy nghiệp vụ, cần:

- Token TTL phù hợp, có refresh/thu hồi khi cần;
- Session invalidation hoặc cơ chế tái nạp authorities;
- Permission check runtime đối với hành động nhạy cảm;
- Audit quyền được cấp/thu hồi;
- Test rằng quyền mới thực sự có hiệu lực đúng thời điểm.

Cấp quyền là một phần quản trị danh tính. Đừng nhầm “database đã sửa quyền” với “mọi `Authentication` hiện có đã đổi”.

### 10.4. Khi nhiều tenant dùng cùng tên role

Hai người có thể cùng mang `ROLE_MANAGER` nhưng thuộc tenant A/B khác nhau. Một authority dạng chuỗi toàn cục **không chứa mặc định ranh giới tenant**. Có thể dùng claim/context đã xác minh cho tenant và policy kiểm tra tenant cụ thể, hoặc mô hình custom có chủ đích. Không dựa vào `tenantId` do frontend đưa vào body làm bằng chứng quyền.

Một policy có thể là:

```text
ALLOW viewInvoice nếu:
  principal được xác thực
  AND có invoice:read
  AND principal và invoice ở tenant hợp lệ
  AND principal là owner hoặc được cấp quyền xem trong tenant
  AND trạng thái invoice cho phép
```

Các điều kiện này cần được kiểm tra ở service/repository hoặc policy engine phù hợp, không chỉ bởi `SimpleGrantedAuthority`.

## 11. Những lỗi phổ biến khi làm việc với SimpleGrantedAuthority

### 11.1. Gắn ADMIN nhưng check ROLE_ADMIN

```java
new SimpleGrantedAuthority("ADMIN"); // Chỉ là authority "ADMIN"
```

Nếu rule là `hasRole("ADMIN")` với prefix mặc định, chuỗi cần có là `ROLE_ADMIN`. Vì vậy rule không khớp. Có hai lựa chọn rõ ràng:

- Cấp `new SimpleGrantedAuthority("ROLE_ADMIN")` và dùng `hasRole("ADMIN")`.
- Cấp `new SimpleGrantedAuthority("ADMIN")` và dùng `hasAuthority("ADMIN")`.

Không xen kẽ quy ước mà không có chính sách mapping.

### 11.2. Dùng hasRole("ROLE_ADMIN") sai convention

`hasRole` thường nhận **tên role không có prefix**. Trong nhiều matcher, truyền `ROLE_ADMIN` vào `hasRole` có thể gây lỗi hoặc hành vi không như mong muốn do prefix được áp dụng. Dùng `hasRole("ADMIN")`, hoặc `hasAuthority("ROLE_ADMIN")` nếu cần so đúng chuỗi.

### 11.3. Kỳ vọng một authority tự bao hàm authority khác

`ROLE_ADMIN` không tự bao gồm `ROLE_USER`, `invoice:approve` hoặc `report:read`. Nếu muốn inheritance, cấu hình RoleHierarchy đúng hoặc cấp rõ các permission liên quan. Phải kiểm thử cả quyền kế thừa lẫn những quyền không nên kế thừa.

### 11.4. Nhầm authorities với danh sách API được gọi

`getAuthorities()` là tập các quyền **đã được cấp**. Nó không tự ánh xạ “authority A = endpoint X” nếu không có `authorizeHttpRequests`, `@PreAuthorize` hoặc policy khác định nghĩa điều đó. Một user có `report:read` nhưng endpoint thiếu authorization vẫn có thể bị mở sai; ngược lại, endpoint yêu cầu quyền khác sẽ không được phép.

### 11.5. Tự nhận quyền qua request body/header

Anti-pattern:

```java
// Không làm: request.roles() do client kiểm soát.
var granted = request.roles().stream()
    .map(SimpleGrantedAuthority::new)
    .toList();
```

Không cấp authorities theo danh sách tự khai của client. Phải dùng user store, provider hoặc token đã được verify và kiểm tra nguồn claim theo trust policy.

### 11.6. Chỉ check isAuthenticated()

Một user login thành công không có nghĩa được làm mọi việc. Với endpoint nhạy cảm, yêu cầu đúng authority và thêm object/domain policy. `isAuthenticated()` cũng có caveat với anonymous token; dùng policy `authenticated()` của Spring Security thay vì tự suy luận.

### 11.7. Dùng quyền toàn cục cho mọi object

`order:read` có thể là permission mở tính năng, nhưng không tự chứng minh quyền đọc `orderId=123`. Bổ sung owner, tenant, quy tắc ủy quyền và giới hạn truy vấn. Đây là lỗi **IDOR/BOLA** thường gặp khi authorization chỉ kiểm tra role.

### 11.8. Bỏ quên CSRF khi test POST

Nếu `POST /api/invoice-approvals` trả 403, không thể kết luận luôn thiếu `invoice:approve`. CSRF token thiếu cũng có thể chặn trước. Dùng `with(csrf())` khi muốn cô lập authority trong MockMvc; giữ test riêng xác nhận CSRF còn hoạt động.

### 11.9. Giữ authorities cũ sau khi thu hồi role

Khi session hoặc token còn hiệu lực, authorities cũ có thể tồn tại. Thiết kế refresh/revocation cho quyền nhạy cảm, hạn chế thời gian sống và kiểm tra policy runtime nếu cần. Đừng coi việc thay một record quyền trong DB là tác động tức thì tới mọi token.

### 11.10. Để lộ thông tin quyền quá mức

Đôi khi frontend cần biết user có một số chức năng để hiển thị nút. Nhưng API trả tất cả quyền nội bộ có thể lộ thông tin vận hành không cần thiết. Đừng gửi password, token, hash hoặc đối tượng `Authentication` nguyên vẹn. Trả DTO tối thiểu cho use case.

### 11.11. Cho rằng String authority là permission bất biến trên mọi môi trường

Một chuỗi `ADMIN` có thể có ý nghĩa khác giữa hệ thống A và B. Hãy định nghĩa vocabulary, owner của quyền, cách cấp/thu hồi, mapping từ IdP và chính sách kiểm thử. Với OAuth2, token scope không nhất thiết trùng role nội bộ.

### 11.12. Sửa 403 bằng cách permitAll

Nếu một user thiếu authority, việc đổi `hasAuthority(...)` thành `permitAll()` có thể mở chức năng cho tất cả. Hãy chẩn đoán: authorities thực tế là gì, prefix có đúng không, JWT converter có map scope đúng không, method security có bật không, và có đang gặp CSRF/object policy không.

## 12. Quy trình debug một lỗi hasRole/hasAuthority

Khi một request bị 403 hoặc một quyền bất ngờ được cho phép:

1. **Xác định endpoint và HTTP method**: request có đi đúng `SecurityFilterChain` không? Có chain order hay matcher bị nhầm không?
2. **Xác thực đã thành công chưa?** Với HTTP Basic, password đúng/sai; với JWT, token được verify chưa? Anonymous có bị xử lý đúng không?
3. **Đọc danh sách authority một cách an toàn**: `authentication.getAuthorities()` chứa chính xác chuỗi nào? Log tên quyền có cần che/bớt theo chính sách bảo mật không?
4. **Kiểm tra prefix/case**: `ROLE_USER` hay `USER`? `SCOPE_read` hay `read`? `report:read` hay `report:READ`?
5. **Kiểm tra rule**: `hasRole("ADMIN")`, `hasAuthority("ROLE_ADMIN")` hay `hasAuthority("ADMIN")`?
6. **Kiểm tra nguồn**: user store, database, provider, JWT converter, IdP hoặc custom mapper nào đã cấp authority?
7. **Kiểm tra method security**: `@EnableMethodSecurity` có bật, method có được gọi qua proxy không?
8. **Kiểm tra object**: user thuộc tenant/owner nào; object có trạng thái cho phép không?
9. **Kiểm tra lớp bảo vệ khác**: CSRF, request matcher, CORS/browser constraints, session expiry, exception handler.
10. **Kiểm tra trạng thái quyền mới/cũ**: session hoặc token có giữ authorities trước khi cập nhật quyền không?
11. **Dùng test âm tính**: user cùng role nhưng thiếu permission, user khác tenant, user anonymous, request CSRF thiếu.
12. **Xác nhận không có side effect** khi quyền bị từ chối: database, message queue và external service không bị tác động.

Không cần ghi password hoặc bearer token ra log để biết user đang có quyền gì. Nếu dùng debug logging, giới hạn môi trường/thời gian và kiểm soát nội dung nhạy cảm.

## 13. Checklist thiết kế hệ quyền dựa trên GrantedAuthority

**Định nghĩa và cấp quyền**

- Các tên authority có quy ước rõ ràng: `ROLE_*` cho role, permission dạng `resource:action` hoặc scope theo chuẩn IdP.
- Có nguồn đáng tin cậy cấp/thu hồi role và permission; client không thể tự khai quyền.
- Authentication provider hoặc token converter map authorities nhất quán.
- Dữ liệu user, role, permission và tenant được kiểm tra ở trust boundary.
- Password/token được xác minh, tránh ghi log hoặc serialize bí mật.
- Role hierarchy nếu có được khai báo và kiểm thử, không suy ra từ tên.

**Sử dụng và kiểm tra**

- HTTP rules và method rules dựa trên quyền thực sự cần cho hành động.
- Có mặc định deny hoặc policy cụ thể cho endpoint nhạy cảm.
- Phân biệt rõ `hasRole` và `hasAuthority`, prefix và chữ hoa/chữ thường.
- Không dùng một authority chung thay thế kiểm tra owner/tenant/business state.
- Một request bị từ chối không tạo side effect nghiệp vụ.
- Với API session/cookie, CSRF protection được chọn đúng threat model.
- Khi quyền đổi, session/token được refresh/thu hồi theo yêu cầu thời gian hiệu lực.

**Kiểm thử và vận hành**

- Có test 401 cho credentials thiếu/sai.
- Có test 403 cho user đã xác thực nhưng thiếu authority.
- Có test 200 cho user có authority phù hợp.
- Có test method security với lời gọi qua bean thực.
- Có test CSRF riêng để không nhầm nguyên nhân 403.
- Có test quyền trên object, tenant, trạng thái và quyền vừa bị thu hồi.
- Có audit/metrics đủ điều tra nhưng không rò rỉ thông tin xác thực.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** `GrantedAuthority` và `SimpleGrantedAuthority` khác nhau thế nào?

**Câu 2.** `Authentication.getAuthorities()` trả gì? Một authority có chứa password người dùng không?

**Câu 3.** Nếu user có `SimpleGrantedAuthority("ROLE_USER")`, biểu thức `hasRole("USER")` có thể khớp không? `hasAuthority("USER")` thì sao?

**Câu 4.** Một user có `ROLE_ADMIN`. Anh ta có mặc nhiên mang `ROLE_USER` không? Muốn kế thừa cần gì?

**Câu 5.** Vì sao `hasAuthority("report:READ")` khác `hasAuthority("report:read")`?

**Câu 6.** Nếu JWT hợp lệ có scope `orders.read`, tại sao rule `hasAuthority("orders.read")` có thể không khớp?

**Câu 7.** Vì sao không nên đưa mọi order ID của một user thành hàng nghìn `SimpleGrantedAuthority`?

**Câu 8.** Tại sao user có `order:read` vẫn phải kiểm tra owner/tenant?

**Câu 9.** Khi test một POST có quyền invoice approval, vì sao phải cung cấp CSRF token hợp lệ nếu ứng dụng bật CSRF?

**Câu 10.** Tại sao không được dùng `new SimpleGrantedAuthority(request.role())` trực tiếp từ dữ liệu client?

**Câu 11.** Khi quyền bị thu hồi trong DB, mọi `Authentication` đang hoạt động có tự đổi không?

**Câu 12.** Khi custom `GrantedAuthority.getAuthority()` trả null, điều gì cần thiết để policy sử dụng được object đó?

**Gợi ý đáp án**

1. `GrantedAuthority` là interface mô tả quyền; `SimpleGrantedAuthority` là implementation chứa một chuỗi quyền.
2. Collection các đối tượng quyền đã gắn vào Authentication; authority không phải kho chứa password.
3. Với prefix mặc định, `hasRole("USER")` tìm `ROLE_USER` nên khớp; `hasAuthority("USER")` tìm đúng `USER`, không khớp với `ROLE_USER`.
4. Không. Cấp thêm `ROLE_USER` hoặc cấu hình `RoleHierarchy` được policy sử dụng.
5. So khớp chuỗi phân biệt chữ hoa/chữ thường.
6. Converter mặc định thường tạo `SCOPE_orders.read`. Rule phải khớp chuỗi đã được map hoặc thay converter có chủ đích.
7. Dễ làm Authentication/token/session phình to, khó cập nhật và thu hồi; kiểm tra quyền object trong domain policy phù hợp hơn.
8. Quyền hành động cấp khái quát không chứng minh quyền trên object cụ thể.
9. Để test authority khi request đã vượt qua lớp CSRF; nếu không request có thể bị CSRF chặn trước.
10. Client có thể tự gửi `ROLE_ADMIN`; authority phải được gán từ nguồn tin cậy sau xác thực.
11. Không nhất thiết. Cần cơ chế làm mới, revoke hoặc runtime policy phù hợp.
12. Một `AuthorizationManager`/delegate hiểu custom authority và đánh giá dữ liệu chuyên biệt.

## 15. Tài liệu tham khảo

- [Spring Security – Authorization Architecture: GrantedAuthority và SimpleGrantedAuthority](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html)
- [Spring Security – Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)
- [Spring Security – Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security – Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Security – OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security – Testing with MockMvc](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/)
- [Spring Security – GrantedAuthority API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/GrantedAuthority.html)
- [Spring Security – SimpleGrantedAuthority API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/authority/SimpleGrantedAuthority.html)
