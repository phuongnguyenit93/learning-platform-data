# Áp dụng hasRole, hasAuthority cho nhóm endpoint trong Spring Security

## 1. Mục tiêu và tình huống

Một ứng dụng Java/Spring Boot quản lý tài liệu có nhiều nhóm HTTP endpoint:

- `/api/health` công khai để kiểm tra sức khỏe ứng dụng.
- `/api/admin/**` dành cho quản trị viên.
- `/api/audit/**` dành cho kiểm toán viên hoặc quản trị viên.
- `GET /api/documents` và `GET /api/documents/{id}` dùng cùng quyền đọc.
- `POST /api/documents` dùng quyền tạo.
- `PATCH /api/documents/{id}` dùng quyền sửa.
- `POST /api/documents/{id}/approve` dùng quyền duyệt.
- Các URL khác không nằm trong danh mục được khai báo phải bị từ chối.

Nếu viết một điều kiện riêng cho từng URL mà không có quy tắc nhóm, ta dễ tạo chỗ thiếu bảo vệ, không nhất quán giữa endpoint và khó kiểm thử. Spring Security hỗ trợ **ghép một hoặc nhiều request matcher** với **một quy tắc authorization**. Hai quy tắc thường gặp là `hasRole` và `hasAuthority`.

Sau bài này, bạn sẽ có khả năng:

1. Phân biệt quyền role với quyền action/permission trong `Authentication.getAuthorities()`.
2. Gắn `hasRole`, `hasAnyRole`, `hasAuthority` và `hasAnyAuthority` cho **một nhóm endpoint** trong `authorizeHttpRequests`.
3. Sắp xếp matcher đúng thứ tự, đặc biệt khi URL đặc thù và URL tổng quát có thể cùng khớp.
4. Phân quyền theo HTTP method, không chỉ theo đường dẫn.
5. Xây cấu hình mặc định từ chối, thêm kiểm soát theo đối tượng ở service và test tích hợp.
6. Nhận biết các lỗi phổ biến liên quan prefix `ROLE_`, claim/scope, URL wildcard, `securityMatcher` và CSRF.

**Phạm vi:** phần chính của bài dùng **Spring Security Servlet/MVC với `SecurityFilterChain` và `authorizeHttpRequests`**. Đây không phải cú pháp WebFlux (`SecurityWebFilterChain`). Cấu hình và matcher cụ thể có thể khác giữa các dòng Spring Security, vì thế hãy đối chiếu phiên bản dependency đang được project sử dụng.

## 2. Ý nghĩa chính xác của hasRole và hasAuthority

### 2.1. Cùng dựa trên GrantedAuthority

Sau khi xác thực, đối tượng `Authentication` thường chứa danh sách `GrantedAuthority` — những tên quyền mà ứng dụng đã cấp cho chủ thể. Ví dụ:

```text
ROLE_EDITOR
document:read
document:edit
SCOPE_profile
```

Các tên trên là **chuỗi thực tế để so khớp**, không tự động đồng nghĩa.

| Cấu hình | Cần authority nào theo mặc định? | Ý nghĩa |
| --- | --- | --- |
| `hasRole("EDITOR")` | `ROLE_EDITOR` | Người dùng thuộc role EDITOR |
| `hasAuthority("ROLE_EDITOR")` | `ROLE_EDITOR` | So khớp chính xác tên authority có prefix |
| `hasAuthority("EDITOR")` | `EDITOR` | **Không tương đương** với `hasRole("EDITOR")` |
| `hasAuthority("document:read")` | `document:read` | Quyền thao tác đọc tài liệu |
| `hasAnyRole("AUDITOR", "ADMIN")` | `ROLE_AUDITOR` **hoặc** `ROLE_ADMIN` | Có ít nhất một role |
| `hasAnyAuthority("document:edit", "document:approve")` | Một trong hai permission | Có ít nhất một action permission |

Theo quy ước **mặc định**, `hasRole("EDITOR")` là shortcut kiểm tra authority `ROLE_EDITOR`. Khi dùng `hasRole`, truyền tên **không có** prefix `ROLE_`. Nếu dự án tùy chỉnh role prefix, phải kiểm tra hành vi thực tế của HTTP matcher, method security, role hierarchy và bộ cấp quyền; đừng suy rằng một thay đổi cấu hình đã tự động đồng bộ mọi nơi.

**`hasAuthority` kiểm tra chính xác:** `document:read` khác `DOCUMENT:READ` và khác `SCOPE_document:read`. Chữ hoa/chữ thường, dấu `:`/`_` và prefix đều quan trọng.

### 2.2. Role là nhóm trách nhiệm; permission là hành động

Một convention dễ quản trị:

```text
Roles:
  ROLE_ADMIN
  ROLE_AUDITOR
  ROLE_DOCUMENT_EDITOR

Permissions:
  document:read
  document:create
  document:edit
  document:approve
  document:delete
```

Role thường mô tả nhóm trách nhiệm tương đối ổn định, còn permission mô tả **một năng lực nghiệp vụ**. Ví dụ `ROLE_DOCUMENT_EDITOR` có thể được ánh xạ thành `document:read` và `document:edit` ở nơi cấp authorities, nhưng **Spring Security không tự tạo các permission đó chỉ vì user có role này**.

Hai lựa chọn đều hợp lệ khi có chủ đích:

- Nhóm chức năng quản trị nhỏ và ổn định: `/api/admin/**` yêu cầu `hasRole("ADMIN")`.
- Nhóm hành động tách biệt đọc/sửa/duyệt: sử dụng `hasAuthority("document:read")`, `hasAuthority("document:edit")`, v.v.

Dùng role không thay thế quyền truy cập theo đối tượng. `document:read` cho phép **thử thực hiện chức năng đọc**; nó chưa chứng minh rằng Alice được đọc tài liệu cụ thể của Bob.

### 2.3. `hasAny...` là OR, không phải AND

`hasAnyRole("ADMIN", "AUDITOR")` có nghĩa có **ít nhất một** authority phù hợp. Nó không yêu cầu cả hai. Tương tự, `hasAnyAuthority("report:read", "report:export")` chỉ yêu cầu một trong hai permission.

Nếu nghiệp vụ yêu cầu **đồng thời** role ADMIN **và** permission xuất dữ liệu, hãy thể hiện phép AND bằng custom `AuthorizationManager`/`AuthorizationManagers.allOf(...)` tương ứng với phiên bản và điểm enforcement. Đừng dùng `hasAny...` rồi tưởng đã kiểm tra hai điều kiện.

Ví dụ mảnh cấu hình cho Servlet, khi API/version hỗ trợ các factory tương ứng:

```java
import static org.springframework.security.authorization.AuthorizationManagers.allOf;
import static org.springframework.security.authorization.AuthorityAuthorizationManager.hasAuthority;
import static org.springframework.security.authorization.AuthorityAuthorizationManager.hasRole;

// Bên trong authorizeHttpRequests:
.requestMatchers(HttpMethod.POST, "/api/admin/reports/export")
    .access(allOf(hasRole("ADMIN"), hasAuthority("report:export")))
```

Đoạn trên là **fragment**, không phải chương trình độc lập; cần `HttpMethod`, `HttpSecurity`, `SecurityFilterChain` và cấu hình bean phù hợp. Một request qua nhánh này phải đáp ứng cả hai điều kiện. Dự án dùng phiên bản khác cần đối chiếu chữ ký API thay vì sao chép mù.

## 3. Nhóm endpoint bằng requestMatchers

### 3.1. Một nhóm đường dẫn, một điều kiện

Nếu nhiều endpoint cùng yêu cầu quyền `document:read`, gộp các đường dẫn trong một `requestMatchers`:

```java
.requestMatchers(
        HttpMethod.GET,
        "/api/documents",
        "/api/documents/*"
).hasAuthority("document:read")
```

Điều này yêu cầu cùng permission cho:

```http
GET /api/documents
GET /api/documents/d42
GET /api/documents/d99
```

`/api/documents/*` được minh họa cho **một đoạn path** ngay dưới `/api/documents`. Không mặc định nó bao phủ mọi endpoint lồng sâu như `/api/documents/d42/versions/3`. Cách xử lý pattern phụ thuộc loại `RequestMatcher` được dùng — ví dụ matcher dựa trên `PathPattern` ở cấu hình mới — nên kiểm thử URL thực tế theo chính phiên bản Spring Security/Servlet đang chạy.

### 3.2. Một nhóm chức năng theo prefix đường dẫn

```java
.requestMatchers("/api/admin/**").hasRole("ADMIN")
.requestMatchers("/api/audit/**").hasAnyRole("AUDITOR", "ADMIN")
```

- Mọi request **khớp matcher** `/api/admin/**` yêu cầu role ADMIN.
- Mọi request **khớp matcher** `/api/audit/**` yêu cầu role AUDITOR **hoặc** ADMIN.

Cấu hình theo prefix thuận tiện khi một nhóm route có cùng độ nhạy. Nhưng `/api/admin/**` có thể gồm cả GET/POST/DELETE, và `hasRole("ADMIN")` riêng nó không phân biệt hành động. Với các thao tác nhạy cảm như xóa dữ liệu hoặc xuất bí mật, có thể thêm permission riêng hoặc policy mạnh hơn.

### 3.3. Phân biệt nhóm có chung path nhưng khác HTTP method

Với REST, một path có thể dùng cho nhiều hành động:

| HTTP method + đường dẫn | Hành động | Rule thích hợp |
| --- | --- | --- |
| `GET /api/documents` | Liệt kê tài liệu được phép đọc | `hasAuthority("document:read")` |
| `GET /api/documents/d42` | Đọc chi tiết một tài liệu | `hasAuthority("document:read")` |
| `POST /api/documents` | Tạo tài liệu | `hasAuthority("document:create")` |
| `PATCH /api/documents/d42` | Chỉnh sửa tài liệu | `hasAuthority("document:edit")` |
| `POST /api/documents/d42/approve` | Duyệt tài liệu | `hasAuthority("document:approve")` |
| `DELETE /api/documents/d42` | Xóa tài liệu | `hasRole("DOCUMENT_ADMIN")` hoặc một permission xóa riêng |
| `GET /api/audit/events` | Đọc audit | `hasAnyRole("AUDITOR", "ADMIN")` |
| `GET /api/admin/users` | Chức năng quản trị | `hasRole("ADMIN")` |

Dùng `requestMatchers(HttpMethod.GET, "...")` giúp rule chỉ bảo vệ một **method cụ thể** thay vì vô tình áp dụng cho mọi thao tác trên cùng path. Nếu muốn hỗ trợ `PUT`, `HEAD` hoặc endpoint version mới, hãy thêm rule đúng mục đích, đừng giả định framework luôn suy ra permission tương ứng.

### 3.4. Một rule cho nhiều method?

Nếu hai method có cùng **chính sách nghiệp vụ**, có thể tạo nhiều `requestMatchers(...)` có cùng yêu cầu hoặc một custom matcher nhóm method. Nhưng không nên mặc định `GET`, `POST`, `DELETE` là tương đương chỉ vì cùng path. Cách dễ audit thường là gom cùng action/permission, **không gom mọi request vì trùng URL**.

## 4. Thứ tự matcher: quy tắc nào khớp trước được áp dụng

Trong `authorizeHttpRequests`, các cặp matcher/rule được xét **theo thứ tự khai báo**. Với một request, **rule khớp đầu tiên** được sử dụng; những rule sau không được kết hợp tự động.

### 4.1. Ví dụ sai: matcher chung che matcher đặc thù

```java
.authorizeHttpRequests(auth -> auth
        .requestMatchers("/api/**").authenticated()
        .requestMatchers("/api/admin/**").hasRole("ADMIN")
        .anyRequest().denyAll()
)
```

Request `GET /api/admin/users` khớp `/api/**` trước, nên chỉ cần authenticated. Rule ADMIN đặt sau **không được áp dụng** cho request đó. Đây là một lỗ hổng do **thứ tự** chứ không phải do `hasRole` sai.

### 4.2. Ví dụ đúng: đặc thù trước, tổng quát sau

```java
.authorizeHttpRequests(auth -> auth
        .requestMatchers("/api/admin/**").hasRole("ADMIN")
        .requestMatchers("/api/**").authenticated()
        .anyRequest().denyAll()
)
```

Ở phiên bản này, nhóm admin được chặn trước. Nhưng `/api/**` vẫn chỉ yêu cầu đăng nhập cho các route khác; nếu ứng dụng có chức năng nhạy cảm ngoài admin, cần rule chi tiết hơn. Trong các ứng dụng có yêu cầu nghiêm ngặt, có thể ưu tiên **deny by default** thay vì một catch-all `authenticated()`.

### 4.3. Phân quyền theo method cũng chịu ảnh hưởng thứ tự

Sai:

```java
.requestMatchers("/api/documents/**").hasAuthority("document:read")
.requestMatchers(HttpMethod.DELETE, "/api/documents/*")
    .hasAuthority("document:delete")
```

DELETE có thể bị matcher chung bắt trước và **chỉ cần quyền đọc**. Đúng hơn:

```java
.requestMatchers(HttpMethod.DELETE, "/api/documents/*")
    .hasAuthority("document:delete")
.requestMatchers(HttpMethod.GET, "/api/documents/*")
    .hasAuthority("document:read")
.requestMatchers("/api/documents/**").denyAll()
```

Quy tắc tổng quát `denyAll()` sau cùng chặn các method/path trong nhóm tài liệu chưa được liệt kê. Đây là chiến lược **allowlist**, an toàn hơn việc mở tất cả phương thức rồi cố gắng chặn một số ngoại lệ.

**Cách đọc một cấu hình dài:** đi từ trên xuống, tìm **matcher đầu tiên** áp dụng cho request cụ thể; chỉ sau đó đánh giá `hasRole`/`hasAuthority`. Không cộng dồn các rule theo cách tưởng tượng.

## 5. Cấu hình Spring Security hoàn chỉnh theo nhóm endpoint

Ví dụ dưới đây dùng **Spring Security Servlet** trong dự án có `spring-boot-starter-security` và cấu hình authentication thích hợp. Nó là một lớp `@Configuration` thực tế có thể biên dịch trong project Spring Boot tương thích; để chạy toàn bộ ứng dụng còn cần controller, dependency Spring Web và nguồn xác thực.

Tạo `ApiSecurityConfig.java`:

```java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableWebSecurity
public class ApiSecurityConfig {

    @Bean
    SecurityFilterChain apiFilterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth

            // Endpoint public, khai báo một cách có chủ đích.
            .requestMatchers("/api/health").permitAll()

            // Nhóm role đặc thù phải đứng trước các rule rộng.
            .requestMatchers("/api/admin/**").hasRole("ADMIN")
            .requestMatchers("/api/audit/**")
                .hasAnyRole("AUDITOR", "ADMIN")

            // Nhóm permission theo action HTTP.
            .requestMatchers(
                HttpMethod.GET,
                "/api/documents",
                "/api/documents/*"
            ).hasAuthority("document:read")

            .requestMatchers(HttpMethod.POST, "/api/documents")
                .hasAuthority("document:create")

            .requestMatchers(HttpMethod.PATCH, "/api/documents/*")
                .hasAuthority("document:edit")

            .requestMatchers(
                HttpMethod.POST,
                "/api/documents/*/approve"
            ).hasAuthority("document:approve")

            .requestMatchers(HttpMethod.DELETE, "/api/documents/*")
                .hasRole("DOCUMENT_ADMIN")

            // Không tự cho phép các URL/method còn lại.
            .requestMatchers("/api/documents/**").denyAll()
            .anyRequest().denyAll()
        );

        return http.build();
    }
}
```

**Giải thích các khối:**

1. `/api/health` là một ngoại lệ public **được chỉ định rõ**; request khác không được public chỉ vì cùng prefix `/api`.
2. Nhóm `/api/admin/**` yêu cầu role ADMIN, còn nhóm `/api/audit/**` dùng **OR** giữa AUDITOR và ADMIN.
3. Quyền `document:read` bảo vệ hai endpoint GET dùng cùng loại hành động.
4. Các method POST/PATCH/DELETE và nhánh `approve` có rule riêng; quyền tạo không đồng nghĩa quyền duyệt.
5. `/api/documents/**` còn lại và `anyRequest().denyAll()` từ chối đường dẫn/method chưa khai báo.

**Không có nghĩa là mọi request trong hệ thống chạy được chỉ với lớp này.** Bạn cần cung cấp authentication (session, JWT, login...), ánh xạ role/permission và controller tương ứng; request ghi có thể cần CSRF token theo chính sách. Khi có nhiều `SecurityFilterChain`, cần thêm ràng buộc matching/phân thứ tự phù hợp; xem mục 8.

### 5.1. Vì sao ví dụ không dùng hasRole cho mọi tài liệu?

Role `DOCUMENT_EDITOR` có thể cấp nhiều permissions, nhưng một endpoint nên kiểm tra **đúng khả năng cần dùng**. Nếu chỉ dùng `hasRole("EDITOR")` cho cả GET và PATCH, mọi editor có thể đọc/sửa theo role, khó thể hiện người được chỉ đọc. Permission `document:read` và `document:edit` giúp các quy tắc rõ ràng và mở rộng về sau.

Dự án nhỏ với ít action hoàn toàn có thể chọn role cho một nhóm route. Điều quan trọng là convention ổn định và tránh biến một role toàn cục thành quyền mặc định đối với mọi bản ghi.

### 5.2. Danh mục tên quyền

Để tránh viết sai tên ở nhiều nơi, có thể định nghĩa:

```java
package com.example.security;

public final class Permissions {
    private Permissions() {}

    public static final String DOCUMENT_READ = "document:read";
    public static final String DOCUMENT_CREATE = "document:create";
    public static final String DOCUMENT_EDIT = "document:edit";
    public static final String DOCUMENT_APPROVE = "document:approve";
}
```

Sau đó tham chiếu trong HTTP:

```java
.requestMatchers(HttpMethod.GET, "/api/documents", "/api/documents/*")
    .hasAuthority(Permissions.DOCUMENT_READ)
```

Việc tạo hằng số không tự cấp permission cho người dùng. `Authentication` phải được cấp cùng chuỗi ở nơi tạo authorities. Nếu method security cũng kiểm tra permission này, hãy giữ **cùng contract**; không dùng `hasRole('READER')` tại method nếu HTTP thực sự chỉ yêu cầu `document:read`, trừ khi đó là **hai điều kiện bổ sung có chủ đích**.

## 6. Dữ liệu authority phải khớp các rule

### 6.1. Ví dụ authorities của người dùng

| Người dùng mẫu | Authorities thực tế | Kết quả dự kiến |
| --- | --- | --- |
| Anonymous | Không có authentication hợp lệ | Chỉ qua public rule như `/api/health` |
| Viewer | `ROLE_VIEWER`, `document:read` | Đọc danh sách và chi tiết tài liệu |
| Editor | `ROLE_DOCUMENT_EDITOR`, `document:read`, `document:create`, `document:edit` | Đọc/tạo/sửa, chưa tự có quyền duyệt |
| Approver | `ROLE_APPROVER`, `document:read`, `document:approve` | Đọc và dùng chức năng duyệt |
| Auditor | `ROLE_AUDITOR` | Vào `/api/audit/**`, chưa tự có `document:read` |
| Admin | `ROLE_ADMIN` | Vào `/api/admin/**` và `/api/audit/**`; **không tự có** các permission tài liệu nếu chưa được cấp |
| Document admin | `ROLE_DOCUMENT_ADMIN` | Được thử DELETE ở nhóm document, còn phải qua object policy |

Bảng chỉ mô tả kết quả ở **lớp HTTP authorization**. Nếu request tới ID tài liệu cụ thể, policy ở service vẫn có thể từ chối vì sai tenant, owner, ACL hoặc trạng thái.

### 6.2. Cấp role và cấp permission không giống nhau

Ví dụ `UserDetails` với role:

```java
User.withUsername("alice")
    .password("{noop}dev-only-password")
    .roles("DOCUMENT_EDITOR")
    .build();
```

Trong DSL này, `roles("DOCUMENT_EDITOR")` thường tạo authority `ROLE_DOCUMENT_EDITOR`. Nó **không tạo** `document:edit` cho Alice. Mẫu mật khẩu `{noop}` chỉ dùng để minh họa môi trường thử nghiệm, tuyệt đối không dùng cho production.

Nếu muốn cấp cả permission, nguồn xác thực cần trả `GrantedAuthority` tương ứng hoặc thực hiện mapping role → permission ở một điểm có trách nhiệm rõ ràng. Ví dụ chỉ minh họa:

```java
var authorities = java.util.List.of(
        new SimpleGrantedAuthority("ROLE_DOCUMENT_EDITOR"),
        new SimpleGrantedAuthority("document:read"),
        new SimpleGrantedAuthority("document:edit")
);
```

`SimpleGrantedAuthority` thuộc `org.springframework.security.core.authority`. Đoạn này chỉ tạo danh sách authority; nó không xác thực user hay thiết lập security context.

### 6.3. JWT scope và role prefix

Với OAuth 2.0 Resource Server dùng JWT, một số converter mặc định ánh xạ scope thành authority có prefix `SCOPE_`. Ví dụ scope token `documents.read` thường trở thành `SCOPE_documents.read`, **không tự bằng** `document:read`.

Có hai hướng nhất quán:

- Dùng trực tiếp `hasAuthority("SCOPE_documents.read")` ở các nhóm HTTP tương ứng.
- Map scope/claim đã xác minh thành permission nội bộ `document:read` rồi dùng permission này đồng nhất ở mọi nơi.

Không nên lấy roles/permissions tùy ý từ request body/header để dựng `Authentication`. Với token, phải xác minh signature, issuer, audience và thời hạn cùng các quy tắc ứng dụng trước khi tin vào claim.

## 7. Bài toán mở rộng: một request có nhiều điều kiện

### 7.1. Vai trò và permission là hai chiều có thể kết hợp

Ví dụ export báo cáo tài chính cần vừa là ADMIN vừa có `report:export`. Dùng `hasAnyAuthority("ROLE_ADMIN", "report:export")` sẽ biến phép **AND** thành **OR**: người chỉ có một trong hai quyền sẽ vào được. Điều đó sai nếu chính sách yêu cầu cả hai.

Các trường hợp thường gặp:

| Chính sách thật | Cách diễn đạt |
| --- | --- |
| Có role ADMIN | `hasRole("ADMIN")` |
| Có role ADMIN **hoặc** AUDITOR | `hasAnyRole("ADMIN", "AUDITOR")` |
| Có `document:read` | `hasAuthority("document:read")` |
| Có `document:edit` **hoặc** `document:approve` | `hasAnyAuthority("document:edit", "document:approve")` |
| Có role ADMIN **và** `report:export` | Kết hợp hai authorization manager bằng phép **AND** |
| Có permission đọc **và** được phép trên ID cụ thể | HTTP permission **và** object policy ở service |

Điều kiện bổ sung có thể được hiện thực bằng `AuthorizationManagers.allOf(...)`, custom `AuthorizationManager<RequestAuthorizationContext>` hoặc policy domain tùy phiên bản và kiến trúc. Mọi phép OR/AND phải được ghi trong ma trận quyền và được test.

### 7.2. Bảo vệ riêng nhóm endpoint có rủi ro cao

Nếu `/api/admin/**` gồm GET users và DELETE users, role ADMIN chung có thể quá rộng. Một cách là đặt rule đặc thù **trước** rule theo prefix:

```java
.requestMatchers(HttpMethod.DELETE, "/api/admin/users/*")
    .hasAuthority("user:delete")
.requestMatchers("/api/admin/**").hasRole("ADMIN")
```

Nhưng nếu DELETE chỉ yêu cầu `user:delete` mà **còn bắt buộc role ADMIN**, rule trên **chưa đủ** — request match DELETE sẽ **không đi tiếp** tới rule ADMIN sau. Phải gộp phép AND vào **một** rule, hoặc kiểm tra role bổ sung trong một điểm enforcement khác rõ ràng và có test.

**Bài học:** hai rule khác nhau cho URL giao nhau không có nghĩa Spring Security tự xét cả hai. Chỉ **first match** được dùng trong cùng khối `authorizeHttpRequests`.

### 7.3. Đúng HTTP permission chưa đủ cho từng bản ghi

Với `GET /api/documents/d42`, HTTP kiểm tra `document:read`. Ở service:

```java
// Fragment trong Spring-managed @Service.
// Cần @EnableMethodSecurity nếu dùng @PreAuthorize.
@PreAuthorize("hasAuthority('document:read') and " +
        "@documentPolicy.canRead(authentication, #documentId)")
public DocumentView getDocument(String documentId) {
    return documentService.load(documentId);
}
```

`documentPolicy` là bean **ứng dụng tự viết** để nạp tài liệu đáng tin và kiểm tra tenant, owner, chia sẻ hoặc ACL. `DocumentView` và `documentService` là ví dụ; phương thức trên không phải chương trình độc lập. `#documentId` cần tên tham số khả dụng khi runtime (ví dụ biên dịch với `-parameters`).

Nếu admin có quyền đọc vượt owner/tenant, chính sách đó cũng phải ghi rõ scope; không tự cho `ROLE_ADMIN` quyền đọc mọi tenant. Bảo vệ service có ý nghĩa khi nghiệp vụ còn được gọi qua job hoặc controller khác.

## 8. securityMatcher khác requestMatchers; nhiều filter chain

Hai API có tên gần giống nhưng vai trò khác nhau:

- `http.securityMatcher("/api/**")` giới hạn **phạm vi request mà cả `SecurityFilterChain` này áp dụng**.
- `authorizeHttpRequests(...requestMatchers("/api/admin/**").hasRole("ADMIN"))` chọn **rule authorization trong chain đã được chọn**.

`securityMatcher` không tự thực hiện `hasRole`, và `requestMatchers` không quyết định chain nào được áp dụng. Khi nhiều `SecurityFilterChain` cùng tồn tại, Spring Security chọn **chain đầu tiên phù hợp** theo thứ tự chain; sau đó mới xét các authorization matcher trong chain đó.

### 8.1. Cấu hình nhiều chain cần có fallback

Một ví dụ khái niệm:

```java
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    return http.securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/admin/**").hasRole("ADMIN")
                .anyRequest().denyAll())
            .build();
}

// Một bean SecurityFilterChain khác làm fallback.
// Cần @Order phù hợp, cấu hình xác thực và
// rà soát toàn bộ đường dẫn không thuộc /api/**.
```

Đây là **fragment**, các import và cấu hình đầy đủ phụ thuộc ứng dụng. Nếu chỉ định nghĩa chain có `securityMatcher("/api/**")` mà không có chain khác khớp URL ngoài `/api/**`, các URL ngoài phạm vi đó có thể **không được Spring Security filter chain bảo vệ**. Đây là lỗi cấu trúc khác với một request bị `anyRequest().denyAll()` trong chain.

### 8.2. Servlet path, context path và matcher strategy

Trong Spring MVC/Servlet, đường dẫn matcher có thể bị ảnh hưởng bởi context path, servlet path, cách đăng ký nhiều servlet, `MvcRequestMatcher` hoặc `PathPatternRequestMatcher` tùy phiên bản. Ví dụ app deploy ở context path `/myapp` nhưng route MVC vẫn là `/api/documents`; không nên tùy tiện chèn `/myapp` vào pattern mà chưa kiểm tra contract.

Với nhiều servlet khác nhau, cần sử dụng matcher hỗ trợ servlet path đúng cách; đừng phỏng đoán chỉ từ URL nhìn thấy trên trình duyệt. Một nguyên tắc ổn định là viết integration test dùng route thật, HTTP method thật, context/servlet path đúng môi trường.

### 8.3. Method-level HTTP mapping phải được bảo vệ theo use case

Một controller có thể map `@GetMapping("/api/documents/{id}")`, nhưng service trong hệ thống còn được gọi từ batch, scheduled job hoặc message consumer. Những đường đi đó có thể không chạy qua HTTP filter. Với use case quan trọng, giữ điều kiện nghiệp vụ (object policy, tenant, trạng thái) tại service/domain boundary, không chỉ ở web config.

## 9. permitAll, authenticated, denyAll và vấn đề public

Ba rule hay gặp:

| Rule | Ý nghĩa |
| --- | --- |
| `permitAll()` | Cho phép request qua bước **authorization rule** mà không yêu cầu một authority cụ thể |
| `authenticated()` | Yêu cầu đã xác thực; **chưa quy định quyền nghiệp vụ** |
| `denyAll()` | Không cho phép request qua rule đó |

`permitAll` không đồng nghĩa "bỏ toàn bộ Spring Security filters". Nếu một route public vẫn đi qua filter chain, những thành phần như security headers, CORS hoặc cơ chế xử lý khác vẫn tồn tại theo cấu hình.

### 9.1. Ưu tiên permitAll thay vì bỏ filter chain

Với asset public, thường ưu tiên `requestMatchers("/css/**", "/js/**").permitAll()` thay vì `web.ignoring()`. Bỏ qua toàn bộ filter chain cũng có thể bỏ qua các lớp bảo vệ khác như security headers.

### 9.2. authenticated không bằng authorization theo chức năng

```java
.requestMatchers("/api/**").authenticated()
```

đảm bảo user đã đăng nhập theo nghĩa framework, nhưng không biết người đó là viewer, editor hay approver. Nếu mọi endpoint trong `/api/**` đều được mở chỉ với login, việc phân quyền theo chức năng bị thiếu. Hãy thiết kế allowlist rule cho action nhạy cảm, rồi dùng `denyAll` cho phần còn lại.

### 9.3. Status code không phải chỉ dấu duy nhất của rule

- Chưa xác thực: API thường trả `401`; ứng dụng login form có thể redirect.
- Đã xác thực nhưng thiếu role/authority: thường trả `403`.
- Một route bị `denyAll` cũng thường đưa đến cơ chế access denied tương ứng.
- Request POST/PATCH/DELETE thiếu CSRF token có thể bị `403` **trước khi** logic authority được đánh giá.

Kết quả HTTP còn phụ thuộc `AuthenticationEntryPoint`, `AccessDeniedHandler`, CORS/CSRF và error handler. Khi test phân quyền, kiểm tra vì sao request bị chặn, không dựa riêng vào số `403`.

## 10. CSRF, CORS và method HTTP

### 10.1. CSRF không phải permission

Với ứng dụng dùng session/cookie, thao tác thay đổi trạng thái có thể cần CSRF token. `hasAuthority("document:edit")` có đạt cũng không làm request `PATCH` tự vượt qua CSRF filter. Trong MockMvc test, có thể dùng `.with(csrf())` khi CSRF được bật.

Đừng tắt CSRF toàn cục chỉ để test `hasRole` dễ pass. Nếu API chỉ dùng Bearer token, không dựa trên cookie tự gửi và có threat model rõ ràng, có thể cấu hình CSRF khác; quyết định đó phải tách khỏi bài toán đặt rule.

### 10.2. CORS preflight và OPTIONS

Trình duyệt có thể gửi `OPTIONS` preflight trước một cross-origin request. Preflight thường không mang thông tin session/xác thực giống request chính. Vì vậy cần tích hợp CORS đúng cách để preflight được xử lý hợp lệ **trước/đúng nơi** trong chuỗi bảo mật.

Không nên chữa lỗi preflight bằng việc mở `OPTIONS /**` không kiểm soát và cho rằng mọi API an toàn. Nếu có rule cho `OPTIONS`, kiểm thử với origin, headers và methods được phép; đồng thời bảo đảm request thực vẫn chịu authorization/CSRF thích hợp.

### 10.3. GET, HEAD và route hỗ trợ method khác

Một số controller/framework hỗ trợ HEAD dựa trên mapping GET, nhưng đừng suy rằng **mọi RequestMatcher** và security rule GET luôn bảo vệ đúng HEAD theo ý định. Khi hệ thống có `HEAD`, `OPTIONS`, `PUT`, `DELETE` hoặc method override, cần test những HTTP method thực tế đã được mở. Chỉ bảo vệ GET mà bỏ sót mutation method có thể tạo lỗi authorization nghiêm trọng.

## 11. Ví dụ Java 17+ chạy độc lập: mô phỏng nhóm quyền

Chương trình Java thuần sau **không sử dụng Spring Security**. Nó mô phỏng cách một nhóm endpoint được gán một rule và cách so khớp authority/role mặc định. Mục tiêu là nhìn thấy kết quả của `hasRole`, `hasAuthority` và `hasAnyRole`. Việc match URL thực tế trong Spring Security do `RequestMatcher` xử lý, không phải các predicate đơn giản trong demo này.

Tạo tệp `HttpGroupAuthorizationDemo.java`:

```java
import java.util.Set;

public class HttpGroupAuthorizationDemo {

    enum Group {
        PUBLIC, ADMIN, AUDIT, DOCUMENT_READ,
        DOCUMENT_CREATE, DOCUMENT_EDIT, DOCUMENT_APPROVE, DENIED
    }

    static boolean hasAuthority(Set<String> granted, String required) {
        return granted != null && granted.contains(required);
    }

    static boolean hasRole(Set<String> granted, String role) {
        return hasAuthority(granted, "ROLE_" + role);
    }

    static boolean hasAnyRole(Set<String> granted, String first, String second) {
        return hasRole(granted, first) || hasRole(granted, second);
    }

    static Group group(String method, String path) {
        // Các nhánh xét theo thứ tự, giống ý tưởng first-match.
        if (path.equals("/api/health")) {
            return Group.PUBLIC;
        }
        if (path.equals("/api/admin") || path.startsWith("/api/admin/")) {
            return Group.ADMIN;
        }
        if (path.equals("/api/audit") || path.startsWith("/api/audit/")) {
            return Group.AUDIT;
        }
        if (method.equals("GET")
                && (path.equals("/api/documents")
                    || path.matches("/api/documents/[^/]+"))) {
            return Group.DOCUMENT_READ;
        }
        if (method.equals("POST") && path.equals("/api/documents")) {
            return Group.DOCUMENT_CREATE;
        }
        if (method.equals("PATCH")
                && path.matches("/api/documents/[^/]+")) {
            return Group.DOCUMENT_EDIT;
        }
        if (method.equals("POST")
                && path.matches("/api/documents/[^/]+/approve")) {
            return Group.DOCUMENT_APPROVE;
        }
        return Group.DENIED;
    }

    static String decision(String method, String path, Set<String> authorities) {
        boolean allowed = switch (group(method, path)) {
            case PUBLIC -> true;
            case ADMIN -> hasRole(authorities, "ADMIN");
            case AUDIT -> hasAnyRole(authorities, "AUDITOR", "ADMIN");
            case DOCUMENT_READ ->
                    hasAuthority(authorities, "document:read");
            case DOCUMENT_CREATE ->
                    hasAuthority(authorities, "document:create");
            case DOCUMENT_EDIT ->
                    hasAuthority(authorities, "document:edit");
            case DOCUMENT_APPROVE ->
                    hasAuthority(authorities, "document:approve");
            case DENIED -> false;
        };
        return allowed ? "ALLOW" : "DENY";
    }

    public static void main(String[] args) {
        Set<String> anonymous = Set.of();
        Set<String> viewer = Set.of("ROLE_VIEWER", "document:read");
        Set<String> editor = Set.of(
                "ROLE_DOCUMENT_EDITOR",
                "document:read", "document:create", "document:edit");
        Set<String> auditor = Set.of("ROLE_AUDITOR");
        Set<String> admin = Set.of("ROLE_ADMIN");

        System.out.println("anonymous-health="
                + decision("GET", "/api/health", anonymous));
        System.out.println("anonymous-documents="
                + decision("GET", "/api/documents", anonymous));
        System.out.println("viewer-list="
                + decision("GET", "/api/documents", viewer));
        System.out.println("viewer-edit="
                + decision("PATCH", "/api/documents/d42", viewer));
        System.out.println("editor-edit="
                + decision("PATCH", "/api/documents/d42", editor));
        System.out.println("editor-approve="
                + decision("POST", "/api/documents/d42/approve", editor));
        System.out.println("auditor-audit="
                + decision("GET", "/api/audit/events", auditor));
        System.out.println("auditor-admin="
                + decision("GET", "/api/admin/users", auditor));
        System.out.println("admin-audit="
                + decision("GET", "/api/audit/events", admin));
        System.out.println("admin-doc-read="
                + decision("GET", "/api/documents/d42", admin));
        System.out.println("unlisted-path="
                + decision("GET", "/api/unknown", admin));
    }
}
```

Biên dịch/chạy với **JDK 17 hoặc mới hơn**:

```bash
javac HttpGroupAuthorizationDemo.java
java HttpGroupAuthorizationDemo
```

Stdout dự kiến:

```text
anonymous-health=ALLOW
anonymous-documents=DENY
viewer-list=ALLOW
viewer-edit=DENY
editor-edit=ALLOW
editor-approve=DENY
auditor-audit=ALLOW
auditor-admin=DENY
admin-audit=ALLOW
admin-doc-read=DENY
unlisted-path=DENY
```

**Phân tích:**

- Viewer có `document:read` nên qua nhóm GET, nhưng không có `document:edit` nên PATCH bị chặn.
- Editor có quyền sửa nhưng không có `document:approve`; việc gọi approve phải bị từ chối.
- Auditor có role AUDITOR và Admin có role ADMIN đều được vào nhóm audit vì `hasAnyRole` là OR.
- Admin **không tự được đọc tài liệu** chỉ nhờ `ROLE_ADMIN`; nếu nghiệp vụ cần, phải cấp permission hoặc định nghĩa policy rõ.
- Path không khai báo rơi vào `DENIED`, tương ứng ý tưởng `anyRequest().denyAll()`.

**Ranh giới mô phỏng:** đây là chương trình Java tự viết để minh họa logic, không thực hiện authentication, CSRF, path matching của Spring, filter chain selection hay mã HTTP. Mọi kết quả về quyền trên **từng đối tượng** còn phải được kiểm tra bởi domain policy của ứng dụng thật.

## 12. Kiểm thử nhóm endpoint bằng Spring Security Test

Một cấu hình HTTP có vẻ đúng vẫn có thể gặp lỗi do matcher quá rộng, role không được cấp, route mới chưa được khai báo hoặc điều kiện CSRF/CORS. Vì vậy phải kiểm thử theo **ma trận request và authority**.

### 12.1. Ma trận tối thiểu

| Request | Authorities của principal test | Kỳ vọng tại lớp HTTP authorization |
| --- | --- | --- |
| `GET /api/health` | Anonymous | Cho phép qua authorization rule |
| `GET /api/documents` | `document:read` | Cho phép qua rule |
| `GET /api/documents/d42` | `ROLE_VIEWER` nhưng không có `document:read` | Từ chối |
| `POST /api/documents` | `document:create` | Cho phép qua rule |
| `POST /api/documents` | `document:read` | Từ chối |
| `PATCH /api/documents/d42` | `document:edit` | Cho phép qua rule |
| `POST /api/documents/d42/approve` | `document:edit` | Từ chối |
| `GET /api/audit/events` | `ROLE_AUDITOR` | Cho phép qua rule |
| `GET /api/audit/events` | `ROLE_ADMIN` | Cho phép qua rule |
| `GET /api/admin/users` | `ROLE_AUDITOR` | Từ chối |
| `GET /api/admin/users` | `ROLE_ADMIN` | Cho phép qua rule |
| `GET /api/unknown` | `ROLE_ADMIN` | Từ chối theo fallback |
| `DELETE /api/documents/d42` | `ROLE_DOCUMENT_ADMIN` | Qua HTTP rule; object policy còn có thể từ chối |

“Cho phép qua rule” **không đồng nghĩa HTTP trả 200**: controller có thể không tồn tại, resource không tìm thấy, business validation có thể thất bại hoặc method security có policy chặt hơn.

### 12.2. @WithMockUser: roles khác authorities

Trong `spring-security-test`:

```java
@WithMockUser(roles = "ADMIN")
```

thông thường tạo principal test có authority `ROLE_ADMIN`.

Trong khi:

```java
@WithMockUser(authorities = "document:read")
```

cấp chính xác `document:read`, **không tự cấp** `ROLE_VIEWER`.

Test dùng `roles="DOCUMENT_EDITOR"` không tự thể hiện permission `document:edit` nếu ứng dụng production chỉ ánh xạ role sang permission khi login. Nên test cả quá trình mapping quyền tại nguồn cấp hoặc integration test authentication thực tế.

### 12.3. Mảnh MockMvc test

Ví dụ sau chỉ là **fragment** trong một test class có `MockMvc`, Spring Security Test, controller/fixtures phù hợp và các import; nó không phải chương trình `javac` độc lập:

```java
@Test
@WithMockUser(authorities = "document:read")
void readerCanReachDocumentReadEndpoint() throws Exception {
    mockMvc.perform(get("/api/documents/d42"))
            .andExpect(status().isOk());
}

@Test
@WithMockUser(authorities = "document:read")
void readerCannotEditDocument() throws Exception {
    mockMvc.perform(patch("/api/documents/d42").with(csrf()))
            .andExpect(status().isForbidden());
}

@Test
@WithMockUser(roles = "AUDITOR")
void auditorCannotCallAdminEndpoints() throws Exception {
    mockMvc.perform(get("/api/admin/users"))
            .andExpect(status().isForbidden());
}
```

**Điều kiện quan trọng:** Test đầu chỉ kỳ vọng `200` nếu `d42` tồn tại, controller trả OK và principal còn đạt object policy. Với request không có handler, trạng thái có thể là 404 sau khi qua filter; đừng nhầm thành rule bị lỗi. Test PATCH dùng `with(csrf())` để xác định lỗi 403 đến từ quyền sửa (nếu CSRF đang bật), không phải thiếu CSRF token.

### 12.4. Các ca kiểm thử cần bổ sung

1. **Chồng lấn pattern:** người chỉ đăng nhập không gọi được `/api/admin/**` dù một catch-all route rộng tồn tại.
2. **Sai method:** người có `document:read` không được PATCH/DELETE/POST cùng path; kiểm tra cả HEAD/OPTIONS/PUT khi ứng dụng hỗ trợ.
3. **Sai prefix:** `ROLE_ADMIN` qua `hasRole("ADMIN")`; `ADMIN` không mặc nhiên qua.
4. **Sai kiểu cấp quyền:** `ROLE_DOCUMENT_EDITOR` không tự bằng `document:edit`; `SCOPE_documents.read` không tự bằng `document:read`.
5. **Không có rule:** endpoint mới, đường dẫn nested hoặc URL version mới không được tự mở.
6. **Role OR:** AUDITOR hoặc ADMIN đều vào audit; user không có cả hai bị từ chối.
7. **AND policy:** nếu export yêu cầu role ADMIN và permission export, thiếu một điều kiện phải từ chối.
8. **Object security:** có `document:read` nhưng khác tenant/owner vẫn không được xem bản ghi.
9. **Filter chain:** URL nằm ngoài `securityMatcher` có chain fallback phù hợp và không lọt ngoài Spring Security.
10. **CORS/CSRF:** preflight, request có cookie và thao tác mutation hoạt động đúng theo cấu hình bảo mật.

## 13. Lỗi phổ biến khi phân quyền theo nhóm

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Đặt `/api/**.authenticated()` trước `/api/admin/**.hasRole("ADMIN")` | Nhóm admin chỉ còn yêu cầu login | Đặt rule đặc thù trước; test first-match |
| Dùng `hasAuthority("ADMIN")` trong khi user có `ROLE_ADMIN` | Bị từ chối sai | Dùng `hasRole("ADMIN")` hoặc chuỗi đầy đủ |
| Dùng `hasRole("ROLE_ADMIN")` theo thói quen | Sai contract prefix ở API mặc định | Truyền `ADMIN` cho hasRole |
| Dùng `hasAnyRole("ADMIN","AUDITOR")` để đòi cả hai | Vô tình nới rộng quyền | Dùng phép AND khi bắt buộc cả hai |
| Dùng `hasAuthority("document:read")` cho mọi method trên `/api/documents/**` | Quyền đọc có thể đủ để gọi DELETE/PATCH | Tách theo HTTP method + action |
| Để matcher chung đứng trước matcher nhạy cảm | Rule sau không bao giờ áp dụng | Quy tắc chi tiết trước tổng quát |
| Dùng `authenticated()` là đủ cho toàn API | Thiếu kiểm tra quyền chức năng | Role/permission theo hành động |
| Không có `anyRequest().denyAll()` hoặc fallback phù hợp | Route mới có thể không có policy dự kiến | Dùng allowlist và test endpoint không khai báo |
| Chỉ khai báo `securityMatcher("/api/**")` mà không có chain khác | URL ngoài `/api/**` có thể lọt ngoài filter chain | Xác định rõ chain fallback |
| Coi role admin là quyền mọi tenant | Truy cập vượt phạm vi | Kết hợp role với scope/object policy |
| Lầm `SCOPE_documents.read` là `document:read` | Bị từ chối hoặc mapping sai | Định nghĩa converter và convention thống nhất |
| Bật `permitAll` rồi nghĩ toàn filter chain bị bỏ qua | Hiểu sai security headers/CSRF | Phân biệt bypass filter với authorization rule |
| Tắt CSRF chỉ vì MockMvc 403 | Có thể giảm bảo vệ thao tác dựa trên cookie | Test có `csrf()`; quyết định cấu hình CSRF theo threat model |
| Tin đường dẫn khó đoán là đã phân quyền | IDOR/BOLA | Kiểm tra owner, tenant và ACL ở service |

## 14. Quy trình thiết kế và bảo trì nhóm endpoint

**Bước 1 — Lập bảng action.** Từ API contract, liệt kê HTTP method, path, use case, dữ liệu nhạy cảm và người dùng hợp lệ. Đừng bắt đầu bằng việc tạo wildcard quá rộng.

**Bước 2 — Xác định tên quyền canonical.** Ví dụ `document:read`, `document:create`, `document:edit`, `document:approve`, `user:delete`; role `ROLE_ADMIN`/`ROLE_AUDITOR`. Ghi rõ ý nghĩa và scope của mỗi quyền.

**Bước 3 — Gom theo cùng chính sách, không chỉ cùng URL.** Các GET documents có thể dùng chung permission đọc; thao tác approve phải có quyền khác dù nằm dưới cùng prefix `/api/documents`.

**Bước 4 — Thiết kế thứ tự.** Endpoint public được khai báo rõ; route nhạy cảm và theo method được đặt trước các rule tổng quát; cuối cùng dùng fallback deny. Đối chiếu các pattern có thể chồng lấn.

**Bước 5 — Kiểm tra nguồn authority.** Tập `GrantedAuthority` ở runtime phải khớp `hasRole`/`hasAuthority`. Nếu dùng JWT, xác minh converter, issuer/audience và cách ánh xạ scope/role; nếu dùng username/password, kiểm tra mapping role → permission.

**Bước 6 — Phân quyền trên đối tượng.** Với route có `{id}`, bổ sung tenant, owner, reviewer, ACL, trạng thái tại service/repository. Với list/search/export, truy vấn chỉ được lấy tập tài nguyên được phép.

**Bước 7 — Bảo vệ các đường ngoài HTTP.** Job, event consumer và service call không nên dựa hoàn toàn vào rule web; kiểm tra các invariant nghiệp vụ ở ranh giới thực thi phù hợp.

**Bước 8 — Test matrix.** Bao gồm đúng quyền, thiếu quyền, role-prefix mismatch, method sai, route chồng lấn, fallback, CSRF/CORS và tenant khác. Test bằng cùng dependency Spring Security/Servlet matcher mà production dùng.

**Bước 9 — Review khi API thay đổi.** Mỗi endpoint mới phải có mapping action và test. Với quyền nhạy cảm, review tác động trước khi deploy. Nếu nhiều chain, review `@Order`, `securityMatcher` và fallback song song với `requestMatchers`.

**Bước 10 — Theo dõi quyết định từ chối.** Audit gồm subject ID, action, resource ID, rule/policy, kết quả và timestamp ở mức phù hợp; không ghi token hoặc thông tin nhạy cảm không cần thiết. Khi phát hiện tăng 403, xác định từ authz, CSRF, endpoint, method hay object policy thay vì nới quyền hàng loạt.

## 15. Câu hỏi tự kiểm tra

**Câu 1.** Người dùng có `ROLE_ADMIN` và request `GET /api/admin/users`. `.hasRole("ADMIN")` có cho qua không?

**Trả lời:** Có, ở lớp matcher/authority mặc định, với điều kiện request khớp rule đó và authentication hợp lệ. Các lớp bảo mật khác có thể vẫn từ chối.

**Câu 2.** Người dùng có `ROLE_ADMIN` nhưng không có `document:read`. API `GET /api/documents/d42` dùng `hasAuthority("document:read")`. Có qua không?

**Trả lời:** Không theo dữ liệu authority trên. Role ADMIN không tự động tương đương permission đọc; cần mapping hoặc policy cho phép rõ ràng.

**Câu 3.** Cấu hình có `.requestMatchers("/api/**").authenticated()` trước `.requestMatchers("/api/admin/**").hasRole("ADMIN")`. Vì sao user thường vẫn vào được admin?

**Trả lời:** `AuthorizationFilter` dùng **first-match-wins**; `/api/**` khớp trước nên rule ADMIN sau không được dùng.

**Câu 4.** `hasAnyRole("AUDITOR", "ADMIN")` có cần cả hai role không?

**Trả lời:** Không. Chỉ cần một trong hai. Muốn cả hai phải diễn đạt phép AND.

**Câu 5.** `PATCH /api/documents/d42` có quyền `document:edit` nhưng tài liệu thuộc tenant khác. Có được sửa không?

**Trả lời:** Không. HTTP permission là điều kiện chức năng; service phải kiểm tra object/tenant policy. Quyền theo chức năng không mở quyền trên mọi ID.

**Câu 6.** Thêm endpoint mới `GET /api/documents/d42/versions` nhưng không viết matcher cho nó. Vì sao không nên dựa vào `/api/documents/*`?

**Trả lời:** `*` thường chỉ khớp một đoạn path trong nhiều matcher; endpoint nested cần rule riêng hoặc pattern phù hợp. Fallback `denyAll` và integration test giúp tránh mở nhầm.

**Câu 7.** MockMvc test PATCH trả 403 dù đã cấp `document:edit`. Bước tiếp theo?

**Trả lời:** Kiểm tra CSRF (nếu bật), matcher nào khớp đầu tiên, Authentication thực tế, method security/object policy và controller/exception handler. Không vội thêm quyền admin hoặc tắt CSRF.

**Câu 8.** Khi có nhiều `SecurityFilterChain`, chỉ thêm `anyRequest().denyAll()` trong chain giới hạn `securityMatcher("/api/**")` có bảo vệ mọi URL không?

**Trả lời:** Không. `anyRequest()` chỉ áp dụng **bên trong chain đã được chọn**. Cần xác định chain fallback cho những URL ngoài phạm vi `/api/**`.

**Ghi nhớ:** Nhóm endpoint bằng `requestMatchers`, gán đúng role/permission bằng `hasRole`/`hasAuthority`, đặt rule đặc thù **trước** rule tổng quát, phân biệt HTTP method, dùng fallback **deny by default**, rồi bổ sung quyền theo đối tượng tại service. Độ an toàn phụ thuộc vào **authority thực được cấp**, **request matcher thực được chọn** và **điểm thực thi policy**, không chỉ vào tên annotation hay tên endpoint.

## Tài liệu tham khảo

- Spring Security — Authorize HttpServletRequests: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security — Authorization Architecture: https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html
- Spring Security — Method Security: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Security — Servlet Authentication Architecture: https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html
- Spring Security — Testing Method Security: https://docs.spring.io/spring-security/reference/servlet/test/method.html
- Spring Security — Testing MockMvc: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html
- Spring Security — CSRF: https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html
- Spring Security — CORS: https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html
