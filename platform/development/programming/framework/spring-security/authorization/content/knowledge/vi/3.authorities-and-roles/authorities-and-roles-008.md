# Nhất quán quy ước tên quyền giữa cấu hình HTTP và method security

## 1. Vì sao một quyền phải có cùng ý nghĩa ở mọi lớp?

Trong ứng dụng Spring Security, một yêu cầu có thể đi qua ít nhất hai điểm phân quyền: **cấu hình HTTP** trong `SecurityFilterChain` và **method security** khi gọi phương thức của Spring bean. Cả hai lớp đều đọc các `GrantedAuthority` thuộc `Authentication`, nhưng lại có thể dùng cách gọi khác nhau:

```java
// Cổng HTTP
.requestMatchers(HttpMethod.GET, "/api/documents/*")
    .hasAuthority("document:read")

// Cổng method, trên service
@PreAuthorize("hasRole('READER')")
```

Hai điều kiện này **không tương đương** theo mặc định. `hasAuthority("document:read")` tìm authority đúng chuỗi `document:read`, trong khi `hasRole("READER")` thường tìm `ROLE_READER`. Người dùng có thể qua lớp này nhưng bị chặn ở lớp kia dù nhóm phát triển nghĩ cả hai đều là “quyền đọc tài liệu”.

Tình huống ngược lại cũng nguy hiểm: cấu hình HTTP yêu cầu `ROLE_ADMIN` nhưng method chỉ kiểm tra `authenticated()`, hoặc hai endpoint gọi chung một service nhưng định nghĩa quyền mâu thuẫn. Có thể khiến kiểm thử trên một đường đi “pass” trong khi job nội bộ, endpoint khác, hoặc luồng gọi dịch vụ có hành vi không được dự kiến.

**Mục tiêu bài học:** đặt tên role/permission nhất quán; hiểu chính xác `hasAuthority`, `hasRole` và prefix mặc định; tổ chức một danh mục tên quyền dùng được bởi HTTP, method và kiểm thử; phát hiện mismatch từ JWT/login/role mapping; giữ nguyên lớp phân quyền theo đối tượng mà nghiệp vụ cần.

## 2. Chuỗi authority thực tế là nguồn so khớp

Một đối tượng `Authentication` chứa tập `GrantedAuthority`. Với `SimpleGrantedAuthority`, mỗi phần tử chứa một chuỗi. Các biểu thức phân quyền sẽ so với các chuỗi được cấp, không tự suy từ tên role nghiệp vụ hay màn hình UI.

Ví dụ người dùng Alice sau xác thực có authorities:

```text
ROLE_EDITOR
document:read
document:edit
```

Khi đó:

| Biểu thức | Chuỗi cần có theo mặc định | Kết quả với Alice |
| --- | --- | --- |
| `hasAuthority("ROLE_EDITOR")` | `ROLE_EDITOR` | **true** |
| `hasRole("EDITOR")` | `ROLE_EDITOR` | **true** |
| `hasAuthority("EDITOR")` | `EDITOR` | **false** |
| `hasAuthority("document:read")` | `document:read` | **true** |
| `hasAuthority("document:edit")` | `document:edit` | **true** |
| `hasRole("READER")` | `ROLE_READER` | **false** |
| `hasAuthority("DOCUMENT:READ")` | `DOCUMENT:READ` | **false** |
| `hasAuthority("SCOPE_document:read")` | `SCOPE_document:read` | **false** |

Các chuỗi `document:read`, `DOCUMENT:READ`, `ROLE_READER` và `SCOPE_document:read` **không mặc nhiên tương đương**. Viết hoa/viết thường, dấu phân cách, prefix và namespace là một phần của contract.

### 2.1. `hasAuthority` so khớp chuỗi đầy đủ

Trong HTTP:

```java
.requestMatchers(HttpMethod.GET, "/api/documents/*")
    .hasAuthority("document:read")
```

Trong method security:

```java
@PreAuthorize("hasAuthority('document:read')")
```

Khi cả hai được cấu hình theo cùng một chuỗi, cùng `Authentication` có `document:read` sẽ đạt kiểm tra permission ở **cả hai lớp**. `hasAuthority` không tự thêm `ROLE_`, `SCOPE_` hoặc đổi tên `document_read` sang `document:read`.

Đối với nhiều permission, có thể dùng `hasAnyAuthority(...)` khi **ít nhất một** quyền là đủ; dùng logic `and` hoặc cơ chế tương ứng khi **mọi** quyền đều bắt buộc. Không được thay `and` bằng `or` chỉ để khắc phục một lỗi đặt tên.

### 2.2. `hasRole` là cách viết tiện lợi có prefix

Với **quy ước mặc định** `ROLE_`:

```text
hasRole("ADMIN")      ≈ hasAuthority("ROLE_ADMIN")
hasRole("EDITOR")     ≈ hasAuthority("ROLE_EDITOR")
hasAnyRole("A","B")  ≈ hasAnyAuthority("ROLE_A","ROLE_B")
```

Phía method security cũng hỗ trợ các biểu thức `hasRole('ADMIN')` và `hasAuthority('ROLE_ADMIN')`. `hasRole` nhận **tên role nghiệp vụ không kèm prefix** trong cách sử dụng chuẩn. Đừng truyền `hasRole("ROLE_ADMIN")` theo thói quen, vì các API có thể từ chối role đã kèm prefix hoặc xử lý prefix khác kỳ vọng; hãy truyền `"ADMIN"` và thống nhất prefix ở cấu hình.

Spring Security cho phép tùy chỉnh role prefix, chẳng hạn bằng `GrantedAuthorityDefaults`, và các phiên bản/cách cấu hình authorization có điểm mở rộng khác nhau. **Nếu đã đổi prefix**, đừng mặc định toàn bộ HTTP matcher, method expression, role hierarchy, test và converter đều đã theo cùng quy ước. Cần kiểm tra hiệu lực trong phiên bản Spring Security của project và viết integration test cho cả hai lớp. Với nhiều dự án, giữ `ROLE_` mặc định giúp giảm rủi ro.

### 2.3. `Role` khác `permission` dù cùng là `GrantedAuthority`

Một cách đặt tên rõ nghĩa là:

```text
Role:
  ROLE_DOCUMENT_EDITOR
  ROLE_DOCUMENT_REVIEWER
  ROLE_TENANT_ADMIN

Permission:
  document:read
  document:edit
  document:approve
  user:invite
```

Role mô tả trách nhiệm hoặc nhóm quyền, còn permission mô tả một hành động nghiệp vụ. Một role có thể cấp nhiều permission, ví dụ:

```text
ROLE_DOCUMENT_EDITOR
    ├─ document:read
    └─ document:edit

ROLE_DOCUMENT_REVIEWER
    ├─ document:read
    └─ document:approve
```

Spring Security không tự hiểu `ROLE_DOCUMENT_EDITOR` sẽ suy ra `document:edit`. Muốn kiểm tra theo permission, ứng dụng cần **cấp đúng authority đó** (ví dụ khi tải người dùng) hoặc cấu hình role hierarchy/cơ chế mapping có chủ đích. Đừng đưa logic ánh xạ rải rác vào từng endpoint.

## 3. Chọn một convention dùng chung trong dự án

Ví dụ convention cho ứng dụng quản lý tài liệu:

| Nhóm | Cú pháp | Ví dụ | Ý nghĩa |
| --- | --- | --- | --- |
| Role | `ROLE_<BUSINESS_ROLE>` | `ROLE_DOCUMENT_EDITOR` | Nhóm trách nhiệm ổn định; khi gọi `hasRole` dùng `DOCUMENT_EDITOR` |
| Permission | `<resource>:<action>` | `document:read` | Khả năng sử dụng hành động nghiệp vụ |
| Scope OAuth 2.0 dạng authority | `SCOPE_<scope>` theo converter mặc định | `SCOPE_documents.read` | Quyền/phạm vi từ access token, **chỉ khi** đã xác minh token |
| Phân quyền theo object | Quy tắc trên dữ liệu server | `document.ownerId == currentUserId` | Điều kiện bổ sung, không phải role mới cho mỗi ID |
| Tenant/membership | Dữ liệu có scope | `tenant=alpha; role=EDITOR` | Role/permission có hiệu lực trong đúng phạm vi |

Convention trên là **ví dụ có thể áp dụng**, không phải cú pháp bắt buộc của Spring Security. Dự án có thể dùng `permission:document:read` hoặc `DOCUMENT_READ`, nhưng phải thống nhất nguồn cấp và mọi nơi tiêu thụ.

### Các nguyên tắc đặt tên nên ghi thành quy ước

1. **Phân biệt namespace:** `ROLE_` dành cho role, `document:read` dành cho permission; không dùng `ADMIN` lúc thì role, lúc thì permission.
2. **Duy trì đúng chữ hoa/chữ thường:** ví dụ role viết hoa, permission viết thường với `:`; tránh dựa vào việc “người đọc hiểu giống nhau”.
3. **Tên permission gắn với nghiệp vụ:** `invoice:approve` khác `invoice:edit`; không lấy HTTP `POST` làm permission cho mọi lệnh ghi.
4. **Tránh dùng role để lưu dữ liệu động:** `ROLE_EDITOR_TENANT_ALPHA_DOCUMENT_42` thường là dấu hiệu role explosion; dùng role + scope + policy trên resource.
5. **Đặt quyền tại một nơi được sở hữu rõ ràng:** có danh mục permission, người/nhóm chịu trách nhiệm đổi contract và quy tắc review.
6. **Không đổi tên âm thầm:** đổi `document:read` sang `documents:read` là thay đổi contract, phải cập nhật nơi cấp authority, HTTP, method và test cùng lúc.
7. **Không cấp quyền mặc định khi tên lạ/không tồn tại:** dùng nguyên tắc deny by default.

Một tên “đẹp” nhưng chỉ có trong code không giúp ích nếu `Authentication.getAuthorities()` thực tế chứa chuỗi khác.

## 4. Những kiểu mismatch thường gặp

### 4.1. HTTP kiểm tra role, method kiểm tra permission

```java
// HTTP
.requestMatchers(HttpMethod.GET, "/api/documents/*")
    .hasRole("DOCUMENT_EDITOR")

// Method
@PreAuthorize("hasAuthority('document:read')")
```

Đây là **hai điều kiện khác nhau**: một điều kiện đòi `ROLE_DOCUMENT_EDITOR`, điều kiện kia đòi `document:read`. Nếu business chủ đích yêu cầu **cả vai trò lẫn permission**, điều này hợp lệ, nhưng phải được tài liệu hóa và test. Nếu hai lớp chỉ đang diễn đạt *cùng một quyền đọc*, cách viết không nhất quán và có thể từ chối người dùng chỉ có `ROLE_DOCUMENT_VIEWER` dù họ có `document:read`.

### 4.2. HTTP kiểm tra `hasAuthority("ROLE_ADMIN")`, method kiểm tra `hasAuthority("ADMIN")`

```text
Authentication authorities: [ROLE_ADMIN]

HTTP required:     ROLE_ADMIN  → ALLOW
Method required:   ADMIN       → DENY
```

Lỗi vì method thiếu prefix, không phải vì method security “khó hơn” HTTP. Hai cách tương đương cho role mặc định là `hasRole('ADMIN')` hoặc `hasAuthority('ROLE_ADMIN')`.

### 4.3. Một lớp dùng role, lớp kia dùng scope từ JWT

OAuth 2.0 Resource Server dùng JWT thường ánh xạ scope thành authority có tiền tố `SCOPE_`. Ví dụ access token chứa scope `documents.read` có thể cho authority:

```text
SCOPE_documents.read
```

Điều này **không tự sinh ra** `ROLE_DOCUMENT_VIEWER` hay `document:read`. Vì vậy:

```java
// Có thể là cách đúng nếu bảo vệ scope OAuth:
.hasAuthority("SCOPE_documents.read")

// Chỉ đúng nếu đã cấp/mapping permission nghiệp vụ:
.hasAuthority("document:read")
```

Cần xác định chiến lược:

- **Dùng scope token trực tiếp:** HTTP và method cùng yêu cầu `SCOPE_documents.read`, đồng thời kiểm tra resource-level policy nếu cần.
- **Chuyển từ claim/scope đáng tin sang permission nội bộ:** dùng converter hoặc dịch vụ phân quyền có kiểm chứng để cấp `document:read`; sau đó **cả hai lớp** kiểm tra `document:read`.

Không coi claim tùy ý hoặc giá trị do client gửi là authority. Token phải được xác minh chữ ký, issuer, audience (theo yêu cầu ứng dụng), thời hạn và các ràng buộc liên quan trước khi tin vào quyền.

### 4.4. Cả hai lớp dùng cùng chuỗi nhưng khác ý nghĩa

Giả sử `report:read` ở HTTP có nghĩa “xem báo cáo tổng hợp”, còn ở method có nghĩa “đọc mọi bản ghi báo cáo kể cả dữ liệu bí mật”. Đây là **mismatch ngữ nghĩa** dù tên bằng nhau. Cần định nghĩa permission rõ phạm vi và thêm policy theo đối tượng, loại dữ liệu hoặc action riêng như `report:export`.

### 4.5. Chỉ bật HTTP security, quên bật method security

`@PreAuthorize` trên service không bảo đảm hoạt động nếu method security chưa được kích hoạt. Với cấu hình hiện đại, dùng `@EnableMethodSecurity` trên lớp `@Configuration`. Spring Boot Starter Security không mặc định bật mọi annotation phân quyền method.

Các trường hợp gọi trực tiếp giữa các method trong cùng bean (*self-invocation*) cũng có thể bỏ qua Spring AOP proxy. Cần kiểm tra điểm chặn thật sự và các đường gọi qua controller, scheduler, consumer.

## 5. Luồng cấp quyền: phải thống nhất từ nơi tạo Authentication

Một sơ đồ hợp lý:

```text
UserDetailsService / AuthenticationProvider / JWT converter
                          │
                          ▼
          Authentication + GrantedAuthority[]
                          │
          ┌───────────────┴─────────────────┐
          ▼                                 ▼
SecurityFilterChain                 Method security
hasAuthority("document:read")       @PreAuthorize("hasAuthority('document:read')")
          │                                 │
          └─────────────┬───────────────────┘
                        ▼
                Business policy
          tenant / owner / state / MFA
                        │
                        ▼
                  ALLOW / DENY
```

**Thứ tự kiểm tra vận hành** thường là HTTP security trước khi controller được gọi, sau đó interceptor ở điểm gọi method. Nhưng sơ đồ không có nghĩa request matcher luôn bao phủ mọi cách gọi method: job, event consumer hoặc service khác có thể gọi method mà không đi qua HTTP. Phải chọn điểm enforcement phù hợp với các đường truy cập thực tế.

### Các nguồn authority phổ biến

- **Đăng nhập username/password:** `UserDetails`/`AuthenticationProvider` cấp authorities. Một `UserDetailsService` có thể gắn `ROLE_DOCUMENT_EDITOR` và các permission đã map.
- **JWT/OAuth 2.0:** bộ giải mã và converter tạo `Authentication`. Mặc định scope có thể hiện dưới `SCOPE_...`, còn role/permission ứng dụng phải được ánh xạ có chủ ý.
- **Role hierarchy:** có thể cho role cấp cao hàm ý role/authority khác; cần cấu hình và kiểm thử nhất quán ở HTTP và method. Đừng giả định một hierarchy đã tự áp dụng ở mọi kiểu biểu thức và mọi phiên bản cấu hình.
- **Policy theo đối tượng:** dựa trên dữ liệu tài nguyên/membership hiện hành do server xác minh. Không nên biến hàng nghìn quyền theo ID cụ thể thành authorities dài trong token.

**Lưu ý về thu hồi:** authority trong JWT sống lâu có thể vẫn còn hiệu lực sau khi role bị thu hồi ở cơ sở dữ liệu. Chọn thời hạn token, kiểm tra membership và chiến lược invalidation phù hợp với rủi ro nghiệp vụ.

## 6. Tổ chức hằng số quyền dùng chung cho HTTP và method

Một cách phòng lỗi chính tả là định nghĩa danh mục authority trong Java. Ví dụ file `src/main/java/com/example/security/SecurityAuthorities.java`:

```java
package com.example.security;

public final class SecurityAuthorities {
    private SecurityAuthorities() {}

    public static final String ROLE_DOCUMENT_EDITOR = "ROLE_DOCUMENT_EDITOR";
    public static final String DOCUMENT_READ = "document:read";
    public static final String DOCUMENT_EDIT = "document:edit";
    public static final String DOCUMENT_APPROVE = "document:approve";
}
```

Những hằng số này chỉ giải quyết **tên**. Chúng không tự cấp quyền cho người dùng; nơi tạo `Authentication` phải cấp chính xác chuỗi tương ứng. Đặt tên class/package theo codebase thực tế, tránh để mỗi module tạo một phiên bản trái nhau.

### 6.1. Dùng cùng quyền ở HTTP

Ví dụ cấu hình Servlet Spring Security, **đoạn tích hợp** được đặt trong class `@Configuration` có imports và dependencies phù hợp:

```java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    return http.authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/api/documents/*")
                .hasAuthority(SecurityAuthorities.DOCUMENT_READ)
            .requestMatchers(HttpMethod.PATCH, "/api/documents/*")
                .hasAuthority(SecurityAuthorities.DOCUMENT_EDIT)
            .requestMatchers(HttpMethod.POST, "/api/documents/*/approve")
                .hasAuthority(SecurityAuthorities.DOCUMENT_APPROVE)
            .anyRequest().denyAll()
    ).build();
}
```

`SecurityAuthorities` cần được import từ `com.example.security`. Đoạn này chỉ minh họa các route đã liệt kê; endpoint danh sách, download/export, batch, delete... cần rule chính xác riêng. Rule `anyRequest().denyAll()` từ chối route chưa được khai báo, một mặc định an toàn khi xây danh sách endpoint cho phép. Việc match route còn phụ thuộc cấu hình Spring MVC/Servlet cụ thể và cần integration test.

Nếu ứng dụng dùng CSRF với session/cookie, thao tác `PATCH`/`POST` có thể bị chặn vì thiếu CSRF token dù authority đúng. Trong kiểm thử phải tách lỗi CSRF khỏi lỗi authorization; không tắt CSRF toàn cục chỉ để làm test đi qua.

### 6.2. Dùng lại cùng quyền trong `@PreAuthorize`

Một chuỗi annotation cần là biểu thức SpEL. Có thể truy xuất hằng số `public static final` qua toán tử `T(...)`, sử dụng **tên class đầy đủ**:

```java
@PreAuthorize(
    "hasAuthority(T(com.example.security.SecurityAuthorities).DOCUMENT_READ)")
public Document readDocument(String documentId) {
    return documentRepository.findById(documentId).orElseThrow();
}
```

Đây là **mảnh code minh họa trong Spring-managed service**: `Document`, `documentRepository`, imports và cấu hình security cần có ở project. Vì SpEL truy cập hằng số từ class `com.example.security.SecurityAuthorities`, HTTP và method dùng cùng **giá trị nguồn**. Nếu đổi `DOCUMENT_READ` thành chuỗi quyền khác, chỉ thay một hằng số và cập nhật nguồn cấp quyền cùng test.

Cách viết ngắn với literal cũng hợp lệ:

```java
@PreAuthorize("hasAuthority('document:read')")
```

Nhưng với nhiều điểm kiểm tra hoặc dễ đổi tên, hằng số/composed annotation và kiểm thử contract giúp tránh các chuỗi không đồng bộ. Lựa chọn cấu trúc nên vừa đủ, không cần một framework policy mới chỉ vì vài authority.

### 6.3. Kết hợp permission nhất quán với kiểm tra đối tượng

Quyền `document:read` **không** có nghĩa là được xem mọi tài liệu. Có thể kết hợp bean policy ứng dụng:

```java
@PreAuthorize(
    "hasAuthority(T(com.example.security.SecurityAuthorities).DOCUMENT_READ) " +
    "and @documentAccess.canRead(authentication, #documentId)")
public Document readDocument(String documentId) {
    return documentRepository.findById(documentId).orElseThrow();
}
```

Bean `documentAccess` phải tải đúng resource, kiểm tra tenant, owner/quyền chia sẻ/trạng thái; `#documentId` cần metadata tên tham số (ví dụ biên dịch với `-parameters` hoặc khai báo tên rõ cho SpEL). Kiểm tra đối tượng là **điều kiện bổ sung có chủ ý**; không phải mâu thuẫn giữa hai tên quyền.

Với thao tác có side effect, policy và ghi dữ liệu cần được đặt trong ranh giới transaction/điều kiện cập nhật thích hợp để tránh trạng thái resource thay đổi sau khi kiểm tra. Không mặc định dùng `@PostAuthorize` cho thao tác đã ghi: đánh giá sau khi thực thi có thể quá muộn để ngăn tác động phụ.

### 6.4. Nếu muốn dùng role thay cho permission

Một dự án nhỏ có thể nhất quán dùng role ở cả hai nơi:

```java
// HTTP:
.requestMatchers("/admin/**").hasRole("ADMIN")

// Method:
@PreAuthorize("hasRole('ADMIN')")
```

Điều kiện này kỳ vọng `ROLE_ADMIN` theo mặc định. Nếu muốn kiểm tra permission chi tiết hơn, đồng bộ cả hai lớp sang `hasAuthority("user:invite")` hoặc các authority khác **sau khi** nơi cấp quyền đã ánh xạ tương ứng.

**Không kết luận mọi API phải có hai lớp kiểm tra trùng nhau.** HTTP thường bảo vệ bề mặt request; method có thể kiểm tra use case nhạy cảm và policy resource. Đòi hỏi ở mỗi lớp phải là một quyết định thiết kế rõ ràng: hoặc cùng permission, hoặc hai điều kiện bổ sung được tài liệu hóa và test.

## 7. Ví dụ Java 17+ chạy độc lập: kiểm tra tên quyền

Chương trình này không phụ thuộc Spring, tái hiện quy ước so khớp mặc định của `hasAuthority` và `hasRole` để nhìn thấy tác động của prefix. Khi chạy trong Spring, biểu thức còn phụ thuộc `Authentication`, role prefix/cấu hình và điểm thực thi authorization; demo tập trung vào **quy tắc so khớp chuỗi**.

Tạo file `AuthorityNamingDemo.java`:

```java
import java.util.Set;

public class AuthorityNamingDemo {
    private static final String ROLE_PREFIX = "ROLE_";
    private static final String DOCUMENT_READ = "document:read";
    private static final String DOCUMENT_EDIT = "document:edit";

    static boolean hasAuthority(Set<String> authorities, String required) {
        return authorities != null && authorities.contains(required);
    }

    static boolean hasRole(Set<String> authorities, String role) {
        return hasAuthority(authorities, ROLE_PREFIX + role);
    }

    static String decision(Set<String> authorities, String required) {
        return hasAuthority(authorities, required) ? "ALLOW" : "DENY";
    }

    public static void main(String[] args) {
        Set<String> alice = Set.of("ROLE_EDITOR", DOCUMENT_READ);

        System.out.println("role-EDITOR=" + hasRole(alice, "EDITOR"));
        System.out.println("raw-EDITOR=" + hasAuthority(alice, "EDITOR"));
        System.out.println("raw-ROLE_EDITOR="
                + hasAuthority(alice, "ROLE_EDITOR"));
        System.out.println("read-lowercase="
                + hasAuthority(alice, DOCUMENT_READ));
        System.out.println("read-uppercase="
                + hasAuthority(alice, "DOCUMENT:READ"));

        // Hai lớp cùng kiểm tra một permission trong tập authority.
        System.out.println("http-read=" + decision(alice, DOCUMENT_READ));
        System.out.println("method-read=" + decision(alice, DOCUMENT_READ));
        System.out.println("http-edit=" + decision(alice, DOCUMENT_EDIT));
        System.out.println("method-edit=" + decision(alice, DOCUMENT_EDIT));

        // Scope OAuth là authority khác nếu không có mapping chủ ý.
        Set<String> tokenAuthorities = Set.of("SCOPE_document:read");
        System.out.println("scope-without-mapping="
                + decision(tokenAuthorities, DOCUMENT_READ));
        System.out.println("scope-with-explicit-check="
                + decision(tokenAuthorities, "SCOPE_document:read"));
    }
}
```

Biên dịch/chạy với JDK 17 trở lên:

```bash
javac AuthorityNamingDemo.java
java AuthorityNamingDemo
```

Stdout chính xác:

```text
role-EDITOR=true
raw-EDITOR=false
raw-ROLE_EDITOR=true
read-lowercase=true
read-uppercase=false
http-read=ALLOW
method-read=ALLOW
http-edit=DENY
method-edit=DENY
scope-without-mapping=DENY
scope-with-explicit-check=ALLOW
```

Điểm cần rút ra:

- `hasRole("EDITOR")` kiểm tra `ROLE_EDITOR` trong mô hình mặc định; `hasAuthority("EDITOR")` yêu cầu **đúng** `EDITOR` và vì vậy thất bại.
- Khi HTTP và method cùng yêu cầu `document:read`, chúng nhất quán: Alice đạt cả hai. Chưa có `document:edit` thì cả hai cùng từ chối.
- `SCOPE_document:read` không tự bằng `document:read`. Phải chọn cùng một convention hoặc ánh xạ từ scope sang permission **một cách có chủ đích**.

Trong hệ thống thật, không tự cho phép client gửi danh sách `authorities` như tham số và áp dụng trực tiếp. Bộ xác thực/ủy quyền có trách nhiệm xây `Authentication` đáng tin.

## 8. Kiểm thử HTTP và method như một contract chung

Một thay đổi quyền chỉ an toàn khi test cả nơi cấp quyền và nơi sử dụng. Đừng chỉ test login thành công hoặc nhìn xem UI có ẩn nút.

### 8.1. Ma trận quan trọng nhất

Giả sử endpoint `GET /api/documents/d42` và service `readDocument("d42")` cùng yêu cầu `document:read`:

| Authorities thật của Authentication | HTTP yêu cầu `document:read` | Method yêu cầu `document:read` | Ý nghĩa |
| --- | --- | --- | --- |
| `document:read` | ALLOW | ALLOW | Đúng convention |
| `ROLE_DOCUMENT_VIEWER` | DENY | DENY | Role chưa được ánh xạ sang permission |
| `ROLE_DOCUMENT_VIEWER`, `document:read` | ALLOW | ALLOW | Role + permission được cấp rõ ràng |
| `document:edit` | DENY | DENY | Edit không tự đồng nghĩa read nếu không có rule cấp thêm |
| `SCOPE_documents.read` | DENY | DENY | Scope chưa mapping sang permission nội bộ |
| `DOCUMENT:READ` | DENY | DENY | Sai chữ hoa/thường |
| Không có authorities | DENY | DENY | Deny by default |

Nếu chính sách yêu cầu `read` cũng được cấp qua `edit`, điều đó cần thể hiện bằng mapping/role hierarchy hoặc một policy có chủ ý. **Không đoán rằng quyền edit luôn bao gồm read**.

### 8.2. Khác biệt giữa `@WithMockUser.roles` và `@WithMockUser.authorities`

Trong test của Spring Security:

```java
@WithMockUser(roles = "DOCUMENT_VIEWER")
```

thường tạo một `Authentication` có authority `ROLE_DOCUMENT_VIEWER`.

Trong khi:

```java
@WithMockUser(authorities = "document:read")
```

tạo authority đúng chuỗi `document:read`. Hai annotation này không tự tạo cùng tập quyền.

Test dùng `@WithMockUser(roles="DOCUMENT_VIEWER")` có thể pass với `hasRole('DOCUMENT_VIEWER')` nhưng thất bại với `hasAuthority('document:read')`. Nếu production thực sự ánh xạ role → permission khi đăng nhập, test chỉ với mock role **không mô phỏng đầy đủ mapping đó**. Nên có integration test với luồng Authentication/converter production hoặc test mapping một cách riêng biệt.

### 8.3. Danh sách test cần bao phủ

1. **HTTP layer:** route đúng method và path; có/thiếu authority; route không khớp; fallback `denyAll`.
2. **Method layer:** method `@PreAuthorize` có thực sự được chặn trong một Spring-managed bean không; lời gọi qua proxy; gọi nội bộ/self-invocation.
3. **Cấp quyền:** user/password, JWT converter, role hierarchy/membership tạo authority đúng ký tự; không chỉ giả định từ role trong database.
4. **Cùng một quyền:** khi cấp `document:read`, cả hai lớp qua; khi thiếu, cả hai lớp chặn. Nếu cố ý dùng hai điều kiện khác nhau, ghi rõ và test kết quả của phép **AND**.
5. **Object policy:** dù có `document:read`, khác tenant hoặc không có quan hệ với tài liệu thì không được đọc.
6. **An ninh request:** nếu ứng dụng dùng CSRF, test thao tác ghi có CSRF token hợp lệ để tránh nhầm lỗi `403` do CSRF với lỗi authority.
7. **Đường ngoài HTTP:** job/consumer/service vẫn phải áp dụng các invariant nghiệp vụ nhạy cảm.
8. **Thay đổi tên:** sau refactor permission, xác minh không còn literal cũ trong config, annotations, token mapping, test và dữ liệu gán quyền.

### 8.4. Ví dụ test logic nhỏ để đối chiếu

Đây là **mảnh kiểm thử minh họa**, chỉ hoạt động khi project có controller, service, mock data, dependencies Spring Security Test và cấu hình security như đã mô tả:

```java
@Test
@WithMockUser(authorities = "document:read")
void readerCanCallHttpReadFunction() throws Exception {
    mockMvc.perform(get("/api/documents/d42"))
           .andExpect(status().isOk());
}

@Test
@WithMockUser(authorities = "document:edit")
void editOnlyCannotCallHttpReadFunction() throws Exception {
    mockMvc.perform(get("/api/documents/d42"))
           .andExpect(status().isForbidden());
}
```

Test `200 OK` ở đây chỉ đúng nếu dữ liệu `d42` tồn tại, người dùng test đạt object policy, controller trả `200` và không có rule khác. Test thực tế phải chuẩn bị fixture và cả test gọi service để kiểm tra method security, thay vì mặc định “qua authority” tức là HTTP luôn `200`.

Đối với người dùng **chưa xác thực**, một endpoint yêu cầu login thường trả `401` trong API phù hợp hoặc chuyển hướng login với ứng dụng form login. Với người đã xác thực nhưng thiếu authority, thường là `403`. Giá trị chính xác phụ thuộc authentication entry point và exception handling của project.

## 9. Thiết kế an toàn khi có hai lớp kiểm tra

### 9.1. Hai lớp có thể bổ sung nhau, nhưng phải rõ ràng

Có ba mô hình thường gặp:

| Thiết kế | HTTP | Method | Phù hợp khi |
| --- | --- | --- | --- |
| **Cùng quyền chức năng** | `document:read` | `document:read` | Muốn khóa cùng capability tại hai ranh giới |
| **HTTP rộng, method hẹp hơn** | `authenticated()` | `document:read` + object policy | Nhiều đường nghiệp vụ gọi chung service; cần chốt ở service |
| **HTTP theo nhóm API, method theo action chuyên biệt** | `ROLE_SUPPORT` hoặc gateway rule | `ticket:close` + policy | Hai lớp thể hiện hai điều kiện bổ sung có chủ đích |

Một request đi qua cả hai sẽ cần **đạt tất cả kiểm tra đang được áp dụng**. Không có cơ chế mặc định “nếu HTTP cho phép thì bỏ qua `@PreAuthorize`”. Cũng không nên thiết kế mâu thuẫn ngoài ý định, chẳng hạn HTTP đòi một role mà nhóm người dùng hợp lệ không được cấp, còn method đòi permission khác.

### 9.2. Không trộn authority naming với object authorization

Tên `document:read` chỉ là quyền vào chức năng. Quyết định trên tài nguyên còn có thể yêu cầu:

```text
ALLOW READ(document) =
    hasAuthority("document:read")
    AND sameTenant(authentication, document)
    AND (isOwner(authentication, document)
         OR isAssignedReviewer(authentication, document))
```

Tạo authority tên `document:d42:read` cho mọi bản ghi có thể khiến token rất lớn và quyền khó thu hồi. Thông thường nên dùng quan hệ/scope/policy bên server, đặc biệt khi số object lớn.

### 9.3. Chính sách mặc định phải chặt chẽ

Trong `SecurityFilterChain`, sắp xếp matcher từ đặc thù tới tổng quát và bảo vệ endpoint nhạy cảm bằng rule cụ thể. Một matcher tổng quát `/api/**` với `permitAll()` đặt trước có thể khiến matcher yêu cầu role ở sau không được áp dụng cho request đã match trước.

Với method security, xem xét annotation trên class, method/interface và quy tắc ưu tiên trong phiên bản framework. Tránh mặc định có `@PreAuthorize` là mọi đường gọi đều qua proxy. Khi nhiều lớp được sử dụng, test route thực và service boundary phải là chứng cứ.

## 10. Quy trình sửa một project đang dùng tên quyền lộn xộn

Giả sử codebase tồn tại các cách viết `ADMIN`, `ROLE_ADMIN`, `ROLE_DOCUMENT_EDITOR`, `document.read`, `document:read` và `SCOPE_documents.read`.

**Bước 1 — Kiểm kê nơi so khớp quyền.** Tìm `hasRole`, `hasAuthority`, `hasAnyRole`, `hasAnyAuthority`, `@PreAuthorize`, `@Secured`, `@RolesAllowed`, custom `AuthorizationManager`, role hierarchy, controller/service và nơi tạo `Authentication`. Không suy rằng mọi annotation đều bật; ví dụ `@Secured` cần cấu hình cho phép theo cách sử dụng cụ thể.

**Bước 2 — Đọc authority thực sự được cấp.** Trong môi trường phát triển/kiểm thử, kiểm tra có kiểm soát `Authentication.getAuthorities()`. Không in access token, dữ liệu nhạy cảm hoặc claim riêng tư vào log. Dữ liệu thực của Authentication là điểm đối chiếu cuối cùng cho quy ước tên.

**Bước 3 — Lập danh mục canonical.** Ví dụ dùng `ROLE_*` cho role và `document:read` cho quyền chức năng, ghi rõ nguồn cấp và ý nghĩa từng permission; xác định cơ chế chuyển từ scope/role sang permission. Chọn một cách mà nhóm có thể giữ nhất quán.

**Bước 4 — Cố định mapping ở ranh giới.** Ánh xạ role/claim/membership sang authority tại nơi xác thực hoặc một policy adapter có chủ sở hữu. Tránh mỗi controller tự dịch role theo công thức riêng.

**Bước 5 — Đồng bộ HTTP và method.** Đối chiếu “cùng một ý nghĩa permission?” ở mỗi endpoint/service. Dùng hằng số, annotation có nghĩa hoặc test static kiểm tra literal khi hữu ích. Chỉ giữ điều kiện khác nhau nếu đó là **rule bổ sung có chủ ý**.

**Bước 6 — Test đường thành công và bị từ chối.** Với từng permission, ít nhất test đúng authority, chỉ có role, chỉ có scope, không có quyền, authority sai chữ hoa/thường, resource ngoài tenant, và từng đường gọi HTTP/service. Kiểm tra tác động CSRF khi test endpoint ghi.

**Bước 7 — Chuyển đổi có kiểm soát.** Nếu thay tên đã được token/user/DB sử dụng, có kế hoạch migrate dữ liệu gán quyền và phiên đang hoạt động. Đừng vô tình cho phép cả tên cũ lẫn tên mới mãi mãi mà không có thời hạn/giới hạn và audit phù hợp.

**Bước 8 — Giữ contract lâu dài.** Khi thêm action như `document:export`, cập nhật nguồn cấp quyền, HTTP matcher, method guard, object policy và test trong cùng thay đổi. Review tên quyền như một phần của API bảo mật, không phải chi tiết đặt tên tùy hứng.

## 11. Các lỗi phổ biến và cách nhận biết nhanh

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra/sửa |
| --- | --- | --- |
| Đăng nhập thành công nhưng method `403` | `@PreAuthorize` yêu cầu authority khác tập được cấp | Xem authorities thực và SpEL |
| HTTP pass, method fail | `hasRole('X')` vs `hasAuthority('x:read')` không tương đương | Chuẩn hóa yêu cầu; nếu là hai điều kiện cố ý, cấp đủ cả hai |
| Test dùng `roles="ADMIN"` pass, production JWT fail | Mock tạo `ROLE_ADMIN` nhưng converter tạo `SCOPE_...` | Test converter/login thực; đồng bộ convention |
| Dùng `hasAuthority("ADMIN")` trong khi user có `ROLE_ADMIN` | Thiếu prefix ở so khớp exact string | Dùng `hasRole('ADMIN')` hoặc `hasAuthority('ROLE_ADMIN')` |
| `@PreAuthorize` không chặn | Chưa bật method security, bean không qua proxy hoặc self-invocation | Kiểm tra `@EnableMethodSecurity` và đường gọi thực |
| Người có quyền đọc thấy tài liệu người khác | Chỉ kiểm tra permission chức năng, thiếu resource policy | Kiểm tra tenant/owner/ACL tại service |
| Sửa endpoint làm một endpoint khác mở quyền | Matcher quá rộng hoặc thứ tự matcher sai | Test tất cả route liên quan và fallback deny |
| Chuyển custom role prefix làm behavior lệch | Cấu hình prefix không đồng nhất ở HTTP/method/test | Kiểm tra điểm mở rộng theo phiên bản, integration test |
| Đổi tên permission nhưng user cũ mất quyền | Token/DB/cache còn tên cũ | Migrate nơi cấp, invalidate/refresh token-cache khi cần |
| Không phân biệt lỗi CSRF và permission | Request ghi bị CSRF filter từ chối trước policy | Kiểm tra CSRF trong integration test riêng |

## 12. Tự kiểm tra

**Câu 1.** Người dùng có đúng authority `ROLE_ADMIN`. `hasRole('ADMIN')` và `hasAuthority('ADMIN')` trả gì theo prefix mặc định?

**Đáp án:** `hasRole('ADMIN')` đạt vì kỳ vọng `ROLE_ADMIN`. `hasAuthority('ADMIN')` không đạt vì so khớp chính xác `ADMIN`, khác chuỗi được cấp.

**Câu 2.** API dùng `hasAuthority('document:read')`; method dùng `hasRole('READER')`. Có phải hai cách nói cùng một quyền?

**Đáp án:** Không mặc định. Chúng yêu cầu `document:read` và `ROLE_READER`. Chỉ là cùng capability nếu ứng dụng đã thiết kế/cấp đủ cả hai và kiểm thử điều đó; nếu không, nên đồng bộ cùng permission.

**Câu 3.** Access token đã xác minh có scope `documents.read`. `hasAuthority('document:read')` có tự pass không?

**Đáp án:** Không. Trong resource server JWT theo convention mặc định, scope thường thành `SCOPE_documents.read`. Muốn yêu cầu permission nghiệp vụ khác cần mapping được định nghĩa và test.

**Câu 4.** Method đã có `@PreAuthorize("hasAuthority('document:read')")`. Vì sao vẫn có thể lộ dữ liệu?

**Đáp án:** Permission chức năng không chứng minh quyền trên tài liệu cụ thể. Phải kiểm tra object policy (tenant, owner, chia sẻ, trạng thái...) ở ranh giới phù hợp; đồng thời annotation phải thực sự được Spring method security áp dụng.

**Câu 5.** Cấu hình HTTP dùng `hasRole('EDITOR')`, method dùng `hasAuthority('ROLE_EDITOR')`. Có nhất quán không?

**Đáp án:** Trong cấu hình prefix mặc định `ROLE_`, cả hai cùng kiểm tra `ROLE_EDITOR`. Vẫn nên ưu tiên một convention rõ ràng và test nếu đã tùy chỉnh prefix.

**Câu 6.** Khi đồng bộ tên quyền giữa hai lớp, có nên bỏ hết các kiểm tra khác để tránh `403`?

**Đáp án:** Không. Chỉ sửa mismatch vô ý. Những điều kiện bổ sung như tenant, owner, resource state, MFA, permission riêng cho action hoặc CSRF phải tiếp tục được thực thi theo chính sách.

**Ghi nhớ:** **Một quyền nghiệp vụ phải có một tên canonical và một ý nghĩa canonical** từ lúc tạo `Authentication`, qua HTTP matcher, method security đến test. `hasRole` có quy tắc prefix; `hasAuthority` so khớp đúng chuỗi; scope OAuth là namespace riêng. Nhất quán tên là điều kiện cần, còn phân quyền theo đối tượng và thực thi tại đúng ranh giới vẫn là điều kiện bắt buộc.

## Tài liệu tham khảo

- Spring Security — Authorization Architecture: https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html
- Spring Security — Authorize HttpServletRequests: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security — Method Security: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Security — OAuth 2.0 Resource Server JWT: https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/jwt.html
- Spring Security — `@WithMockUser` API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/test/context/support/WithMockUser.html
