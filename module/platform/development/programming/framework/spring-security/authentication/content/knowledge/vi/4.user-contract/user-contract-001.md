# UserDetails và dữ liệu mà bộ máy xác thực cần

Trong Spring Security, thông tin người dùng được lưu trong database thường có nhiều trường: mã tài khoản, email, tên hiển thị, số điện thoại, nhóm quyền, trạng thái khóa, lịch sử hoạt động và các thuộc tính nghiệp vụ. **Bộ máy xác thực username/password không cần toàn bộ hồ sơ đó**. Nó cần một hợp đồng tối thiểu để biết *đã tìm đúng tài khoản chưa, nên đối chiếu credential nào, tài khoản còn được phép đăng nhập không, và nếu thành công thì principal có những authority gì*. Hợp đồng đó là `org.springframework.security.core.userdetails.UserDetails`.

Một đối tượng `UserDetails` **không phải bằng chứng đã đăng nhập**, không phải raw password do client vừa gửi, và cũng không tự đưa người dùng vào `SecurityContext`. Nó là **bản mô tả tài khoản do nguồn tin cậy cung cấp** để `DaoAuthenticationProvider` đánh giá trong luồng username/password. Hiểu chính xác dữ liệu mà hợp đồng cung cấp giúp bạn xây dựng `UserDetailsService`, ánh xạ account từ database và khóa/vô hiệu hóa tài khoản một cách dự đoán được.

Bài này tập trung vào **Hợp đồng người dùng** trong module *Spring Security - authentication*, với mã minh họa Java 17+ và Spring Security 6.x (ứng dụng Spring Boot 3.x). Các kiến trúc bearer JWT/OIDC có thể sử dụng loại principal khác; chúng được nhắc đến để xác định ranh giới trách nhiệm của `UserDetails`.

## 1. Mục tiêu

Sau bài học, bạn có thể:

1. Giải thích trách nhiệm của `UserDetails`, `UserDetailsService`, `PasswordEncoder`, `DaoAuthenticationProvider`, `Authentication` và `SecurityContext`, tránh trộn chúng.
2. Đọc đúng toàn bộ phương thức trong `UserDetails`: username, password, authorities và bốn cờ trạng thái có tên mang nghĩa phủ định.
3. Biết cách chuyển account record sang `UserDetails` mà không chuyển dữ liệu nghiệp vụ hoặc bí mật không cần thiết vào principal.
4. Dự đoán kết quả khi username không tồn tại, password sai, account bị khóa/vô hiệu hóa/hết hạn, hoặc password đã hết hạn.
5. Phân biệt `roles(...)` với `authorities(...)`, nguồn dữ liệu quyền và giới hạn kiểm tra authorization.
6. Chạy ví dụ Spring Boot với tài khoản hoạt động và các trạng thái từ chối; kiểm tra kết quả HTTP có thể quan sát.
7. Nhận ra lỗi thường gặp khi cache `UserDetails`, erase credential, normalize username, sử dụng multi-tenant account và xử lý thay đổi trạng thái sau login.

## 2. Phân biệt rõ các đối tượng của luồng xác thực

| Thành phần | Vai trò | Dữ liệu đặc trưng | Không nên làm |
| --- | --- | --- | --- |
| **Account / domain entity** | Bản ghi nghiệp vụ, nguồn dữ liệu có thẩm quyền của tổ chức | ID, email, password hash, trạng thái, thông tin cá nhân, quan hệ doanh nghiệp | Truyền toàn bộ entity, cả thuộc tính riêng tư, tới mọi request/controller. |
| **`UserDetails`** | Bản nhìn an ninh của một tài khoản mà provider cần để xác minh username/password | Username, password verifier, authorities, account flags | Coi đối tượng này là bằng chứng login thành công hoặc chứa raw password đầu vào. |
| **`UserDetailsService`** | Dịch vụ truy xuất account security view bằng username | `loadUserByUsername(String)` trả `UserDetails` | Tự xác thực raw password hay cấp quyền dựa vào header do client gửi. |
| **`PasswordEncoder`** | Kiểm tra raw credential với verifier đã lưu; tạo hash khi cấp/đổi password | `matches(raw, encoded)`, `encode(raw)` | So sánh plain string với hash hay lưu password dạng rõ. |
| **`DaoAuthenticationProvider`** | Provider xác thực username/password bằng UserDetails và PasswordEncoder | Status check, password match, kết quả principal | Đổi trạng thái tài khoản chỉ vì một request tự nói rằng nó được phép. |
| **`Authentication`** | Yêu cầu xác thực ban đầu hoặc kết quả đã xác thực | Principal, credentials, authorities, authentication state | Suy ra `isAuthenticated=true` từ việc có username mà chưa kiểm credential. |
| **`SecurityContext`** | Ngữ cảnh bảo mật của execution/request | `Authentication` đã được thiết lập bởi cơ chế tin cậy | Lưu raw password hoặc giả định mọi thay đổi database tự đồng bộ tức thì. |

Nhìn theo trình tự: **domain account → `UserDetailsService` nạp security view → `DaoAuthenticationProvider` xác minh credential và trạng thái → kết quả `Authentication` → `SecurityContext` → authorization**. Mỗi mắt xích chịu trách nhiệm cho một câu hỏi khác nhau.

### UserDetails khác Principal

Sau khi đăng nhập username/password theo flow chuẩn với `DaoAuthenticationProvider`, `Authentication.getPrincipal()` thường là `UserDetails` được nạp. Nhưng `Authentication.getPrincipal()` có kiểu `Object`, tùy cơ chế có thể là `String`, `Jwt`, `OAuth2User`, đối tượng tùy chỉnh hoặc dạng khác. Vì thế:

- `UserDetails` mô tả dữ liệu tài khoản cho cơ chế cụ thể.
- `Principal` trong `Authentication` mô tả **chủ thể mà cơ chế đã xác thực**.
- `Authentication.getName()` là cách tiện dụng để lấy định danh do đối tượng authentication công bố.
- Không ép kiểu `(UserDetails) authentication.getPrincipal()` trong toàn bộ controller nếu ứng dụng có nhiều authentication mechanism.
- Đăng nhập thành công cũng chưa phải quyền được đọc bản ghi của user khác; bước authorization vẫn phải kiểm tài nguyên thực tế.

## 3. Hợp đồng UserDetails: bảy giá trị cốt lõi

Trong Spring Security 6.x, `UserDetails` định nghĩa ba phương thức dữ liệu và bốn phương thức trạng thái. Giao diện sau là **bản rút gọn để đọc ý nghĩa**, không phải code cần sao chép để tạo lại package Spring Security:

```java
public interface UserDetails extends java.io.Serializable {
    Collection<? extends GrantedAuthority> getAuthorities();
    String getPassword();
    String getUsername();

    default boolean isAccountNonExpired() { return true; }
    default boolean isAccountNonLocked() { return true; }
    default boolean isCredentialsNonExpired() { return true; }
    default boolean isEnabled() { return true; }
}
```

Các default method trả `true` giúp những implementation chỉ cần ba trường cơ bản hoạt động, **nhưng là một rủi ro nếu ứng dụng có chính sách khóa/hết hạn mà quên override**. Một hệ thống có trạng thái khóa trong DB nhưng `UserDetails` luôn trả `true` sẽ không làm provider chặn theo trạng thái đó.

| Phương thức | Provider cần thông tin gì? | Hợp đồng và ví dụ |
| --- | --- | --- |
| `getUsername()` | Tên đăng nhập/định danh của account được nạp | Trả chuỗi không `null`; có thể là username đã canonicalize. |
| `getPassword()` | Giá trị verifier để `PasswordEncoder.matches(...)` đối chiếu raw password | Trong luồng username/password, thường là **password hash đã encode** (ví dụ `{bcrypt}...`), không phải mật khẩu gốc. |
| `getAuthorities()` | Danh sách `GrantedAuthority` mà principal được cấp sau xác thực | Không trả `null`; lấy từ nguồn quyền tin cậy, ví dụ `ROLE_READER`, `orders:read`. |
| `isEnabled()` | Account có được sử dụng để xác thực không? | `true` = enabled, `false` = disabled. |
| `isAccountNonExpired()` | Account vẫn còn hiệu lực hay đã hết hạn? | `true` = chưa hết hạn; `false` = đã hết hạn. |
| `isAccountNonLocked()` | Account hiện có bị khóa không? | `true` = không bị khóa; `false` = bị khóa. |
| `isCredentialsNonExpired()` | Credential/password verifier còn trong thời hạn/chính sách không? | `true` = còn hiệu lực; `false` = credential đã hết hạn. |

**Cảnh báo về dấu phủ định:** `isAccountNonLocked() == false` là **tài khoản bị khóa**, không phải mở khóa. `isCredentialsNonExpired() == false` là **mật khẩu đã hết hạn**. Đặt biến boolean theo đúng nghĩa khi ánh xạ từ DB để tránh đảo ngược điều kiện.

### 3.1 Trường nào là bắt buộc?

Với username/password authentication thông thường:

- `username` phải trỏ tới đúng record theo chính sách tìm kiếm của ứng dụng.
- `password` phải chứa verifier mà `PasswordEncoder` hiện tại hiểu. Không lưu raw password rồi dựa vào `{noop}` ở production.
- `authorities` phải biểu diễn các quyền đã được cấp theo nguồn tin cậy, có thể là những authority tối thiểu để xác định người dùng; bộ sưu tập không được `null`.
- Bốn cờ trạng thái cần khớp trạng thái account và chính sách login. Default `true` không thể tự biết tài khoản đã bị khóa trong database.

Đừng nhầm `UserDetails.getPassword()` với `Authentication.getCredentials()`: giá trị thứ nhất thường là **hash đã lưu** từ server; giá trị thứ hai thường là **credential raw** do request trình ra trước khi được erase. Việc tiếp xúc với hash vẫn nhạy cảm vì nó có thể bị dò mật khẩu offline.

### 3.2 Những dữ liệu không nằm trong hợp đồng

`UserDetails` không buộc phải chứa số điện thoại, địa chỉ, ngày sinh, phương thức thanh toán, thiết lập ngôn ngữ, danh sách đơn hàng, avatar, tenant config hoặc full domain object. Nếu business cần một giá trị ổn định như `accountId` hoặc `tenantId`, có thể dùng **custom principal tối thiểu** hoặc truy vấn service có kiểm quyền. Đừng để `UserDetails` trở thành một bản sao toàn bộ entity mỗi lần xác thực.

Các thông tin về MFA, identity proofing, external IdP, độ mạnh của lần xác thực và thời gian reauthentication có thể cần mô hình/hợp đồng riêng. Bốn status flag không thay thế mọi quyết định đó.

## 4. Đường đi dữ liệu qua DaoAuthenticationProvider

Đây là flow thường gặp với HTTP Basic hoặc form login trong Spring Security Servlet, không áp dụng nguyên dạng cho mọi cơ chế:

```text
Client (username + raw password)
            |
            v
UsernamePasswordAuthenticationFilter / BasicAuthenticationFilter
            |
            | tạo UsernamePasswordAuthenticationToken CHƯA xác thực
            v
AuthenticationManager / ProviderManager
            |
            v
DaoAuthenticationProvider
            |
            +--> UserDetailsService.loadUserByUsername(username)
            |         |
            |         +--> Account store / DB / LDAP / cache
            |                   |
            |                   +--> UserDetails: username, encoded password,
            |                         authorities, enabled/non-expired/non-locked...
            |
            +--> Kiểm trạng thái account
            +--> PasswordEncoder.matches(raw, storedHash)
            +--> Kiểm trạng thái credential còn hiệu lực
            |
            v
Authentication thành công (principal thường là UserDetails)
            |
            v
SecurityContext do filter/cơ chế bảo mật quản lý
            |
            v
Authorization: xét quyền cho action và resource cụ thể
```

Các bước quan trọng:

1. Client gửi credential qua HTTPS đến endpoint/cơ chế được cấu hình.
2. Filter tạo một `Authentication` yêu cầu xử lý, chẳng hạn `UsernamePasswordAuthenticationToken.unauthenticated(username, rawPassword)`.
3. `ProviderManager` chọn provider phù hợp loại token. `DaoAuthenticationProvider` dùng `UserDetailsService` nạp security view theo username. Nạp không đồng nghĩa đã chứng minh password.
4. Provider thực hiện các kiểm tra trạng thái và đối chiếu bằng `PasswordEncoder` theo cơ chế cụ thể. Tài khoản bị khóa/vô hiệu hóa/hết hạn có thể bị chặn dù mật khẩu khớp.
5. Nếu thành công, provider trả một `Authentication` đã xác thực, gồm principal và authorities thích hợp; filter đưa kết quả vào ngữ cảnh.
6. Controller/service đọc principal/authorities đã được xác thực và authorization quyết định hành động. Nó **không cần biết raw password**, thường cũng không cần gọi `UserDetailsService` để đăng nhập lần nữa.

Trong ứng dụng có cache, một số lần xác thực có thể lấy `UserDetails` từ cache thay vì đi database trực tiếp; đây không phải lời đảm bảo load mỗi lần. Cache phải có chính sách làm mới/thu hồi thích hợp khi tài khoản thay đổi.

### Điều gì xảy ra khi lookup thất bại?

`UserDetailsService.loadUserByUsername` trả một `UserDetails` được điền đầy đủ hoặc ném `UsernameNotFoundException` khi không tìm được user; **không trả `null`**. Với `DaoAuthenticationProvider` thông thường, lỗi “không có username” có thể được che thành lỗi credential chung ở ranh giới authentication để giảm nguy cơ account enumeration. Không cung cấp API công khai tiết lộ “username này tồn tại” chỉ vì việc debug sẽ dễ hơn.

### Đừng tự gọi UserDetailsService làm bằng chứng xác thực

Sai:

```java
UserDetails details = userDetailsService.loadUserByUsername(username);

// Sai: chỉ load được user không chứng minh người gửi biết password.
SecurityContextHolder.getContext().setAuthentication(
        UsernamePasswordAuthenticationToken.authenticated(
                details, null, details.getAuthorities()));
```

Đây là ví dụ **lỗi**, không phải chương trình hoàn chỉnh. Đúng là để cơ chế tin cậy gọi `AuthenticationManager.authenticate(...)`, kiểm mật khẩu/credential và trạng thái trước khi thiết lập authentication đã xác thực. Nếu dùng Spring Security đã cấu hình HTTP Basic/form login, framework thực hiện phần lớn chuỗi này.

## 5. Bốn cờ trạng thái: dữ liệu account tạo nên quyết định login

Ví dụ database có ba trạng thái boolean mang nghĩa **khẳng định phủ định**:

```text
enabled = true
accountLocked = true
passwordExpired = false
```

Khi ánh xạ sang `UserDetails`:

```text
isEnabled()                 =  true
isAccountNonLocked()        = !accountLocked        = false
isCredentialsNonExpired()   = !passwordExpired      = true
```

Với `DaoAuthenticationProvider`, trạng thái `isAccountNonLocked=false` khiến login bị từ chối, dù người dùng nhập đúng mật khẩu. Nếu implementation quên map cờ hoặc đảo nghĩa, tài khoản đã khóa có thể được login.

| Trạng thái nguồn | Giá trị trên UserDetails | Hành vi login username/password điển hình |
| --- | --- | --- |
| `enabled=false` | `isEnabled()=false` | Từ chối với `DisabledException` tại provider (response HTTP có thể hiển thị lỗi chung). |
| `expired=true` | `isAccountNonExpired()=false` | Từ chối với `AccountExpiredException`. |
| `locked=true` | `isAccountNonLocked()=false` | Từ chối với `LockedException`. |
| `passwordExpired=true` | `isCredentialsNonExpired()=false` | Từ chối với `CredentialsExpiredException`. |
| Tất cả điều kiện cho phép nhưng raw password sai | Các cờ có thể vẫn `true` | Từ chối với `BadCredentialsException` sau khi so khớp không thành công. |
| Tất cả điều kiện cho phép và password đúng | Các cờ `true` | Provider có thể trả authentication thành công; authorization vẫn là bước riêng. |

**Thứ tự kiểm tra trong một provider cụ thể** quyết định ngoại lệ nội bộ được ném đầu tiên khi có nhiều vấn đề cùng lúc; không giả định mọi provider đều kiểm mọi status flag giống nhau. Khi dùng HTTP Basic, các thất bại trên thường đều biểu hiện bằng **HTTP 401** với cơ chế xử lý lỗi chung. Không dựa vào mã 401 để đoán chắc bị khóa hay sai password.

### Enabled và locked khác nhau về nghiệp vụ

- `enabled=false` thường nghĩa tài khoản chưa kích hoạt hoặc bị vô hiệu hóa theo chính sách.
- `locked=true` thường nghĩa cần chặn login vì số lần sai, tín hiệu an ninh hoặc hành động quản trị.
- `accountExpired=true` có thể dùng cho tài khoản thuê bao/thời hạn cấp quyền nếu sản phẩm thiết kế như vậy; cần phân biệt với việc một hợp đồng nghiệp vụ hết hạn nhưng tài khoản vẫn được login để xem dữ liệu.
- `credentialsExpired=true` biểu diễn credential không còn hợp lệ theo chính sách; một flow đổi mật khẩu/khôi phục tài khoản phải được thiết kế riêng, không đơn giản cho phép mọi request authenticated rồi sửa cờ.

Điểm dễ nhầm: trạng thái **tài khoản** và trạng thái **đăng nhập đã tồn tại** không đồng nhất. Tắt `enabled` trong DB không tự xóa mọi phiên ở server hoặc làm mọi JWT đã cấp mất hiệu lực ngay lập tức; phải xác định cơ chế kiểm lại trạng thái, revocation và thời hạn phiên/token.

### Status flags có phải authorization?

Không. Chúng thường phục vụ **điều kiện chấp nhận authentication**. `getAuthorities()` mô tả quyền cấp cho principal; endpoint vẫn cần kiểm authorization. Ví dụ user `ROLE_READER` có thể login thành công nhưng bị HTTP 403 khi gọi endpoint yêu cầu `ROLE_ADMIN`.

## 6. UserDetailsService: chọn bản ghi nào và điền dữ liệu ra sao?

Hợp đồng truy xuất là:

```java
public interface UserDetailsService {
    UserDetails loadUserByUsername(String username)
            throws UsernameNotFoundException;
}
```

Nó thường là **read-only lookup**, không phải API đăng ký user, reset password hay xác thực trực tiếp raw password. `UserDetailsManager` là hợp đồng bổ sung cho một số thao tác quản lý user; `InMemoryUserDetailsManager` chỉ là implementation thích hợp cho demo/test và trường hợp nhỏ.

**Yêu cầu tối thiểu của loader:**

1. Nhận username đã được xác định ở cơ chế authentication, áp dụng quy tắc canonicalization đã được định nghĩa (ví dụ lowercase email nếu nghiệp vụ cho phép; đừng tự hạ chữ không kiểm soát với mọi định danh).
2. Tra cứu bằng index phù hợp trong **đúng phạm vi tenant/issuer/namespace**. Nếu key đăng nhập không duy nhất trên toàn hệ thống, không được dùng một SQL query thiếu tenant constraint.
3. Không tìm thấy thì ném `UsernameNotFoundException`. Không trả user mặc định, không tự cấp quyền cho account lạ.
4. Có record thì ánh xạ verifier/password hash, authorities tin cậy, trạng thái enabled/locked/expired và các trường cần thiết khác.
5. Trả đối tượng `UserDetails` tương thích với `PasswordEncoder` và provider hiện tại, không đưa thông tin nhạy cảm không cần thiết vào principal.
6. Định nghĩa vòng đời cache và độ mới của trạng thái. Khi account bị khóa hoặc đổi quyền, quyết định cache invalidation/freshness và cách xử lý phiên đã đăng nhập.

Một nơi phổ biến để đặt mapper là lớp adapter an ninh: **domain repository** biết schema và quan hệ dữ liệu; **security adapter** biến chúng thành `UserDetails`. Giữ quyền truy cập DB, transaction và policy ở tầng thích hợp; không nhét HTTP request, email OTP hoặc các service thanh toán vào `UserDetails`.

### Username không nhất thiết là account ID

Một người có thể đổi email mà ID nội bộ không đổi. Một username như `alex` có thể tồn tại ở nhiều tổ chức. Nếu người dùng đăng nhập theo email, hãy phân biệt:

- **Login identifier**: dữ liệu tìm kiếm, có thể đổi theo thời gian.
- **Canonical subject/account ID**: khóa danh tính ổn định mà domain dùng liên kết đơn hàng và tenant.
- **Display name**: tên hiển thị có thể giống nhau, không dùng làm khóa bảo mật.

`getUsername()` có thể là login identifier được canonicalize. Nếu business cần account ID, custom principal có thể chứa ID ổn định hoặc controller/service truy xuất ID từ nguồn tin cậy. Không dùng một chuỗi `username` nhận từ JSON body để bỏ qua principal đã xác thực.

## 7. Ánh xạ AccountRecord thành UserDetails mà không lẫn nghĩa

Đây là **utility mapping hoàn chỉnh** khi ứng dụng có account record và đã có `passwordHash`, `authorities` từ nguồn tin cậy. Nó là code phụ trợ cần thư viện Spring Security trong classpath; chưa có `main` nên không chạy độc lập bằng `java AccountUserMapper`.

File `src/main/java/demo/AccountUserMapper.java`:

```java
package demo;

import java.util.Set;

import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;

public final class AccountUserMapper {

    private AccountUserMapper() {
    }

    public record AccountRecord(
            String accountId,
            String loginName,
            String passwordHash,
            Set<String> grantedAuthorities,
            boolean enabled,
            boolean locked,
            boolean accountExpired,
            boolean passwordExpired) {
    }

    public static UserDetails toUserDetails(AccountRecord account) {
        return User.withUsername(account.loginName())
                .password(account.passwordHash())
                .authorities(account.grantedAuthorities().toArray(String[]::new))
                .disabled(!account.enabled())
                .accountLocked(account.locked())
                .accountExpired(account.accountExpired())
                .credentialsExpired(account.passwordExpired())
                .build();
    }
}
```

Chú ý:

- `passwordHash` **đã** là encoded password theo `PasswordEncoder` của hệ thống. Đừng `encode(...)` lại hash đã lưu mỗi lần load, vì khi đó raw password của client không thể khớp.
- `grantedAuthorities` là các string authority đã được tính từ role/permission store của server; ví dụ `ROLE_READER`, `orders:read`. Không lấy trực tiếp danh sách quyền từ request/hidden field.
- Các flag trong domain dùng tên `locked`, `accountExpired` và `passwordExpired` với nghĩa **true = trạng thái xấu**; builder cũng dùng đúng nghĩa này. Khi dùng implementation `UserDetails` tự viết, các phương thức `is...Non...` phải đảo nghĩa.
- `accountId` được giữ trong domain record nhưng built-in `User` không có accessor account ID. Nếu cần ID trong principal, xây custom `UserDetails` tối thiểu có ID ổn định hoặc tìm lại theo khóa đã được xác minh, kèm kiểm tenant.
- Nên cấp bản sao bất biến/snapshot của dữ liệu cần thiết. Không trả Hibernate entity lazy-loaded trực tiếp làm principal rồi dùng nó qua request khác; có thể gây serialization, transaction, PII và hiệu năng khó đoán.

**Bảo vệ ánh xạ quyền:** Đừng tạo authority dựa trên `request.getParameter("role")`. Khi user có nhiều role, quyết định union/intersection theo policy, tenant và nguồn cấp phát quyền. Authentication chỉ xác nhận user; authorization tiếp tục xét đúng object được thao tác.

### Vai trò của PasswordEncoder khi lưu hash

Ví dụ với `PasswordEncoderFactories.createDelegatingPasswordEncoder()`, giá trị được `encode` thường có prefix thuật toán như `{bcrypt}...`. `DaoAuthenticationProvider` gọi `matches(rawPassword, userDetails.getPassword())`; nó không yêu cầu bạn cung cấp salt tách rời khi định dạng verifier đã chứa tham số và salt tương ứng.

Nếu ứng dụng có hash lịch sử, phải có lộ trình migrate xác định: kiểm thuật toán cũ được cho phép, cập nhật hash an toàn khi có cơ hội và quản lý password upgrade phù hợp. `UserDetailsPasswordService` có thể tham gia cơ chế nâng cấp encoding khi cấu hình provider tương thích, nhưng không mặc định suy ra việc chỉ đổi `PasswordEncoder` sẽ tự nâng cấp tất cả tài khoản.

## 8. Ví dụ Spring Boot 3.x / Security 6.x chạy được

Ví dụ này tạo **năm tài khoản in-memory** có cùng mật khẩu demo nhưng khác trạng thái:

| Username | Trạng thái | Kết quả khi credential đúng |
| --- | --- | --- |
| `alice` | Enabled, chưa hết hạn, không khóa, mật khẩu còn hạn | Đăng nhập thành công; có `ROLE_READER`. |
| `locked` | `accountLocked(true)` | Bị từ chối login. |
| `disabled` | `disabled(true)` | Bị từ chối login. |
| `expired` | `accountExpired(true)` | Bị từ chối login. |
| `old-password` | `credentialsExpired(true)` | Bị từ chối login. |

Mục tiêu là **quan sát các trường mà UserDetails cung cấp** cho provider. Đây là một ứng dụng học tập chạy local, không phải phương án lưu mật khẩu cho production. Cần **Java 17+**, Spring Boot 3.x, hai starter `spring-boot-starter-web` và `spring-boot-starter-security`.

### 8.1 Mã nguồn

File `src/main/java/demo/UserDetailsLessonApplication.java`:

```java
package demo;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class UserDetailsLessonApplication {

    public static void main(String[] args) {
        SpringApplication.run(UserDetailsLessonApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        String demoPassword = "local-only-password";

        UserDetails alice = User.withUsername("alice")
                .password(encoder.encode(demoPassword))
                .roles("READER")
                .build();

        UserDetails locked = User.withUsername("locked")
                .password(encoder.encode(demoPassword))
                .roles("READER")
                .accountLocked(true)
                .build();

        UserDetails disabled = User.withUsername("disabled")
                .password(encoder.encode(demoPassword))
                .roles("READER")
                .disabled(true)
                .build();

        UserDetails expired = User.withUsername("expired")
                .password(encoder.encode(demoPassword))
                .roles("READER")
                .accountExpired(true)
                .build();

        UserDetails passwordExpired = User.withUsername("old-password")
                .password(encoder.encode(demoPassword))
                .roles("READER")
                .credentialsExpired(true)
                .build();

        return new InMemoryUserDetailsManager(
                alice, locked, disabled, expired, passwordExpired);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(authorize -> authorize
                        .requestMatchers("/public").permitAll()
                        .requestMatchers("/api/me").authenticated()
                        .requestMatchers("/api/admin").hasRole("ADMIN")
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}

@RestController
class IdentityController {

    @GetMapping("/public")
    String publicPage() {
        return "public";
    }

    @GetMapping("/api/me")
    Map<String, Object> me(Authentication authentication) {
        return Map.of(
                "username", authentication.getName(),
                "authorities", authentication.getAuthorities().stream()
                        .map(GrantedAuthority::getAuthority)
                        .sorted()
                        .toList());
    }

    @GetMapping("/api/admin")
    String adminArea() {
        return "admin";
    }
}
```

Vì app dùng `UserDetailsService` và `PasswordEncoder` được cấu hình làm bean, Spring Security trong cấu hình username/password tiêu chuẩn có thể tạo/cấu hình provider phù hợp để kiểm chứng credential. Không phải viết lại `DaoAuthenticationProvider` chỉ để đọc bốn flag. Với hệ thống có nhiều authentication manager/filter chain tùy chỉnh, cần xác minh bean và provider được gắn vào chain thực tế.

**Giải thích thành phần:**

- `User.withUsername(...).password(...).roles("READER").build()` tạo một `UserDetails` chuẩn. `roles("READER")` được chuyển thành authority `ROLE_READER`.
- `disabled(true)` trên builder làm `isEnabled()` thành `false`. Tương tự `accountLocked(true)` làm `isAccountNonLocked()` thành `false`; `accountExpired(true)` và `credentialsExpired(true)` cũng mang nghĩa ngược với tên các phương thức `NonExpired`.
- HTTP Basic nhận username/password qua header và dùng cơ chế authentication. HTTP Basic chỉ mã hóa Base64 trên đường truyền, **không mã hóa bảo mật**; production bắt buộc dùng HTTPS.
- Endpoint `/api/me` chỉ trả username và authorities sau khi xác thực; không truy cập `getPassword()` hay `getCredentials()`, không serialize `UserDetails` trực tiếp ra JSON.
- `/api/admin` yêu cầu `ROLE_ADMIN`, trong khi demo user chỉ có `ROLE_READER`. Người dùng đăng nhập thành công vẫn có thể bị 403 vì thiếu quyền.

### 8.2 Cách chạy với dự án Spring Boot

Tạo Spring Boot 3.x project với hai starter nêu trên, đặt file theo package `demo`, rồi chạy bằng build tool của project.

Trên Linux/macOS dùng Gradle wrapper:

```bash
./gradlew bootRun
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Hoặc với Maven wrapper của một project Spring Boot tương đương:

```bash
./mvnw spring-boot:run
```

**Không dùng `javac UserDetailsLessonApplication.java` một mình** vì ví dụ import Spring Framework, Spring Boot và Spring Security; `javac/java` trực tiếp cần classpath phụ thuộc được build tool tạo. Chạy trên local hoặc môi trường test kín, không triển khai tài khoản/mật khẩu demo lên Internet.

### 8.3 Gọi API và kiểm kết quả

Thử từ terminal khác (trên Windows dùng `curl.exe` nếu PowerShell gán alias `curl`):

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/api/me
curl -i -u alice:wrong http://localhost:8080/api/me
curl -i -u alice:local-only-password http://localhost:8080/api/me
curl -i -u locked:local-only-password http://localhost:8080/api/me
curl -i -u disabled:local-only-password http://localhost:8080/api/me
curl -i -u expired:local-only-password http://localhost:8080/api/me
curl -i -u old-password:local-only-password http://localhost:8080/api/me
curl -i -u alice:local-only-password http://localhost:8080/api/admin
```

| Request | Kết quả mong đợi | Diễn giải |
| --- | --- | --- |
| `GET /public` | HTTP 200, body `public` | Không cần credential theo `permitAll()`. |
| `GET /api/me` không credential | HTTP 401 và HTTP Basic challenge | Endpoint yêu cầu authenticated principal. |
| `alice:wrong` | HTTP 401 | Username có tồn tại nhưng raw password không khớp hash. |
| `alice:local-only-password` | HTTP 200, JSON có `username` = `alice` và `authorities` chứa `ROLE_READER` | UserDetails hợp lệ và password đúng. |
| `locked` với password đúng | HTTP 401 | `isAccountNonLocked=false` dẫn tới login bị từ chối. |
| `disabled` với password đúng | HTTP 401 | `isEnabled=false`. |
| `expired` với password đúng | HTTP 401 | `isAccountNonExpired=false`. |
| `old-password` với password đúng | HTTP 401 | `isCredentialsNonExpired=false`. |
| `GET /api/admin` bằng alice | HTTP 403 | Authentication thành công nhưng role không đủ; đây là authorization. |

JSON thành công có nội dung tương đương:

```json
{
  "username": "alice",
  "authorities": ["ROLE_READER"]
}
```

Thứ tự key JSON không được đảm bảo; không dùng exact byte-for-byte JSON làm tiêu chí. Endpoint trả **không có** password hash, raw password hay toàn bộ principal. Nếu thấy HTTP 200 với `locked` hoặc `disabled`, cần xem lại cấu hình manager/provider và object `UserDetails` thực sự được nạp.

**Đọc đúng kết quả:** `401` với `locked`/`disabled` cho thấy authentication bị chặn; endpoint trả lỗi giống nhau không có nghĩa lý do nội bộ giống nhau. Không công khai chi tiết người dùng tồn tại hoặc bị khóa qua error message nếu đó là thông tin nhạy cảm. `403` khi Alice truy cập `/api/admin` chứng minh quyền truy cập được xét **sau** authentication.

## 9. Triển khai UserDetails tùy chỉnh khi domain cần thêm accountId

Spring Security có sẵn `User` triển khai `UserDetails`, phù hợp khi bạn chỉ cần username/password/authorities/status. Custom class hữu ích khi phải gắn **account ID ổn định** cho nghiệp vụ hoặc xử lý security view đặc thù. Tuy nhiên custom class phải giữ đúng contract.

Một thiết kế thường dùng:

```java
package demo;

import java.util.Collection;
import java.util.List;

import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.userdetails.UserDetails;

public final class AccountPrincipal implements UserDetails {

    private final String accountId;
    private final String username;
    private final String passwordHash;
    private final List<GrantedAuthority> authorities;
    private final boolean enabled;
    private final boolean accountNonExpired;
    private final boolean accountNonLocked;
    private final boolean credentialsNonExpired;

    public AccountPrincipal(
            String accountId,
            String username,
            String passwordHash,
            Collection<? extends GrantedAuthority> authorities,
            boolean enabled,
            boolean accountNonExpired,
            boolean accountNonLocked,
            boolean credentialsNonExpired) {
        this.accountId = accountId;
        this.username = username;
        this.passwordHash = passwordHash;
        this.authorities = List.copyOf(authorities);
        this.enabled = enabled;
        this.accountNonExpired = accountNonExpired;
        this.accountNonLocked = accountNonLocked;
        this.credentialsNonExpired = credentialsNonExpired;
    }

    public String getAccountId() {
        return accountId;
    }

    @Override
    public String getUsername() {
        return username;
    }

    @Override
    public String getPassword() {
        return passwordHash;
    }

    @Override
    public Collection<? extends GrantedAuthority> getAuthorities() {
        return authorities;
    }

    @Override
    public boolean isEnabled() {
        return enabled;
    }

    @Override
    public boolean isAccountNonExpired() {
        return accountNonExpired;
    }

    @Override
    public boolean isAccountNonLocked() {
        return accountNonLocked;
    }

    @Override
    public boolean isCredentialsNonExpired() {
        return credentialsNonExpired;
    }
}
```

Đây là **lớp dữ liệu của security adapter**, không có `main` và cần Spring Security dependency để biên dịch; không phải ứng dụng chạy độc lập. Nó chủ ý không chứa email riêng tư, phone, địa chỉ, session secret hoặc domain entity. Trong production, nên cân nhắc việc principal lưu `passwordHash` quá lâu trong session/cache; thiết kế erasure, snapshot và cache phải được lựa chọn theo vòng đời của ứng dụng, như phần 10.

### Mapping trạng thái khi constructor dùng tên non-expired/non-locked

Nếu domain lưu `locked=true`, tham số constructor `accountNonLocked` phải nhận `!locked`. Nếu domain lưu `expired=true`, truyền `!expired` vào `accountNonExpired`. Cần test từng phép đảo boolean, đặc biệt khi dữ liệu lấy từ SQL kiểu `status`/`deleted_at`/`locked_until`.

Đừng lấy thời gian hết hạn từ clock một lần lúc khởi động rồi giữ mãi trong singleton; giá trị `UserDetails` cần đại diện trạng thái đủ mới trong thời điểm kiểm chứng theo policy. Nếu trạng thái tính từ timestamp, sử dụng clock/timezone nhất quán, kiểm đúng điều kiện boundary như `now >= expiresAt`.

### Cân nhắc Serializer và equals/hashCode

Một `UserDetails` có thể xuất hiện trong security context/session, cache hoặc cơ chế phân phối giữa các node. Tránh object graph lớn và lazy entity; giữ dữ liệu gọn và ổn định. Nếu triển khai `equals/hashCode`, chọn danh tính khóa rõ ràng, phù hợp đa tenant; không đưa password hash hoặc thuộc tính thay đổi liên tục vào định danh. Xem xét tính tương thích khi thay đổi serialized class trong session store. Tách thông tin audit khỏi principal thay vì chèn object HTTP request vào đó.

## 10. Authority: dữ liệu xác thực cần, nhưng authorization còn quyết định riêng

`getAuthorities()` trả các `GrantedAuthority` đã gán cho principal, chẳng hạn `ROLE_READER` hoặc `invoices:approve`. `GrantedAuthority.getAuthority()` thường trả một chuỗi; chính sách có thể dùng các loại authority đặc biệt và không phải mọi provider có cùng cách ánh xạ.

Với built-in `User.UserBuilder`:

```java
UserDetails a = User.withUsername("alice")
        .password("{bcrypt}...") // Mã minh họa, không phải hash có thể login.
        .roles("READER", "EDITOR")
        .build();

// Authorities: ROLE_READER, ROLE_EDITOR
```

`roles("READER")` tự thêm prefix `ROLE_`; không truyền `roles("ROLE_READER")` với hy vọng giữ nguyên. Nếu nguồn dữ liệu đã chứa chuỗi đầy đủ `ROLE_READER`, sử dụng `authorities("ROLE_READER")` hoặc mapping tương thích. Phân biệt `hasRole("ADMIN")` (mặc định kiểm `ROLE_ADMIN`) với `hasAuthority("orders:read")` (kiểm chuỗi tương ứng).

Một chủ thể có thể được authentication thành công với authority hợp lệ nhưng không có quyền với object cụ thể. Ví dụ `ROLE_READER` không cho phép tự ý đọc hồ sơ của tenant khác. `@PreAuthorize` và request-level authorization cung cấp một phần kiểm soát; object ownership và business policy vẫn phải được xét tại service/resource phù hợp.

**Nguyên tắc nguồn quyền:** Authorities xuất phát từ role/permission store có kiểm soát hoặc claims từ issuer đã xác thực và ánh xạ đúng. Không cấp authority dựa trên trường `role` trong form, query param hoặc custom header client tự gửi. Nếu role thay đổi sau khi user login, cần có chính sách làm mới session/context và cache.

## 11. Caching, erase credentials và độ mới trạng thái

`UserDetails` chứa password verifier và authorities; việc cache có thể tiết kiệm truy vấn nhưng kéo dài thời gian dữ liệu nhạy cảm hiện diện, đồng thời làm trạng thái cũ tiếp tục được dùng.

### 11.1 Cache làm sai trạng thái như thế nào?

Tình huống:

1. User Alice login, `UserDetails` được load với `enabled=true` và `ROLE_ADMIN`.
2. Hệ thống cache record đó trong 30 phút.
3. Quản trị viên disable Alice hoặc thu hồi quyền ADMIN sau 5 phút.
4. Request mới hoặc một lần authentication tiếp theo vẫn nhìn thấy bản cũ nếu cache không invalidate/refresh; phiên đã xác thực có thể còn authority cũ.

Giải pháp tùy hệ thống: cache TTL nhỏ, event invalidation trên thay đổi account, key gắn tenant/namespace, reauthentication khi hành động nhạy cảm, và kiểm authorization với dữ liệu mới khi cần. **Đổi một flag trong DB không có tác dụng tức thì đối với mọi session/JWT đã cấp** nếu chưa có cơ chế thu hồi hoặc freshness.

### 11.2 eraseCredentials ảnh hưởng object nào?

`ProviderManager` mặc định cố gắng erase credentials trên `Authentication` thành công nếu đối tượng triển khai `CredentialsContainer`. Trong một số trường hợp, hành vi này cũng tác động tới principal/credentials/details là object có thể xóa.

Nếu custom provider trả **chính instance `UserDetails` từ cache** làm principal, việc erase trên kết quả có thể xóa password hash trong cùng instance của cache; lần login tiếp theo có thể thất bại vì không còn hash để đối chiếu. Phải xem cơ chế copy/cache và loại `UserDetails` cụ thể:

- Không chia sẻ một mutable instance chứa hash giữa cache verifier và authenticated principal nếu erasure sẽ phá record dùng lại.
- Dùng security view riêng, bản sao phù hợp hoặc kế hoạch cache/credential erasure có kiểm chứng bằng test.
- Không tắt `eraseCredentialsAfterAuthentication` chỉ để tránh lỗi cache khi chưa phân tích rủi ro giữ bí mật trong memory.
- Không log nguyên `UserDetails` hay serialize tất cả thuộc tính làm API response; thực hiện allowlist DTO cần thiết.

Lưu ý Spring Security 6 có nhiều cơ chế login. Với JWT resource server, principal có thể là `Jwt` chứ không phải `UserDetails`, nên chính sách cache và xóa raw credential khác username/password. Đừng khẳng định mọi authentication đều tra `UserDetailsService`.

### 11.3 Hash khác raw password

`getPassword()` của `UserDetails` trong username/password flow nên là **encoded password verifier**; `Authentication.getCredentials()` trước xác thực thường là raw password do người dùng gửi. Cả hai đều cần bảo vệ khỏi log/dump, nhưng chúng có chức năng và vòng đời khác nhau.

- Hash phải được lưu trong database được bảo vệ, cùng tham số thuật toán/salt phù hợp.
- Raw password chỉ nên tồn tại đủ lâu để kiểm tra; tránh các bản sao phụ trong logs.
- Không gửi password hash sang client để “đăng nhập offline”.
- Xóa một biến Java không chứng minh tất cả bản sao raw password/hash khỏi JVM hoặc hệ thống giám sát.
- Với token và passkey không dùng password, contract verify có thể khác; không cố nhét token vào trường `passwordHash` của domain chỉ để tận dụng `UserDetailsService`.

## 12. Các lỗi triển khai rất thường gặp

### 12.1 Nạp được user rồi coi như đã đăng nhập

**Sai:** Controller gọi `userDetailsService.loadUserByUsername(request.getParameter("username"))` rồi tạo `Authentication` thành công. **Đúng:** Luồng filter/provider phải kiểm credential; business chỉ nhận principal tin cậy sau xác thực.

### 12.2 Lưu plaintext password hoặc hash hai lần

**Sai:** DB lưu password gốc; hoặc dùng `encoder.encode(hashFromDb)` trong loader. **Đúng:** Chỉ encode khi tạo/đổi password; loader trả verifier đã lưu; provider dùng `matches(raw, storedHash)`.

### 12.3 Trả `null` từ loadUserByUsername

**Sai:** `return null` khi không tìm thấy. **Đúng:** Ném `UsernameNotFoundException`. Dùng một nhánh fallback “admin mặc định” trong loader là rủi ro nghiêm trọng.

### 12.4 Đảo nghĩa trạng thái

**Sai:** `isAccountNonLocked() { return record.isLocked(); }`. **Đúng:** `return !record.isLocked();`. Tương tự `nonExpired` là phủ định của expired; kiểm cẩn thận khi mapping timestamp.

### 12.5 Quên override status flags

`UserDetails` có default boolean methods trả `true`. Nếu cần enforce trạng thái thật, phải override/mapping đúng. Kiểm thử tài khoản bị disable/lock/expire cần xác nhận login thất bại, không chỉ test getter.

### 12.6 Lấy role từ payload của request

`getAuthorities()` không được đọc `role=ADMIN` từ client. Quyền phải đến từ server/nguồn đã được tin cậy. Ngoài ra `roles("ADMIN")` thêm `ROLE_`; việc nhầm prefix thường gây HTTP 403 dù login đúng.

### 12.7 Trả cả domain entity làm UserDetails

Dễ gặp lazy loading exception, vòng tham chiếu JSON, lộ password hash/PII hoặc identity không ổn định. Hãy tạo security adapter gọn với ID, verifier, authorities và trạng thái cần thiết. Trả DTO đã lọc ra API.

### 12.8 Cùng username trên nhiều tenant

Nếu service tra `findByUsername("alex")` mà không khóa tenant, có thể nạp account sai tổ chức. Chuẩn hóa identity namespace; kiểm tenant từ ngữ cảnh tin cậy; không cho client tự đổi tenant trong header rồi truy cập như account khác. Cần thiết kế resolver/manager hoặc subject key đa tenant rõ ràng.

### 12.9 Nhầm authentication state với authorization state mới nhất

Session cũ có thể giữ authorities trong `SecurityContext` sau khi DB đổi. Một hệ thống cần quyền thu hồi tức thì phải có cơ chế kiểm lại/invalidating phù hợp, không trông chờ việc `UserDetails` thay đổi trong DB tự đẩy tới mọi session/token.

### 12.10 Ép mọi principal đều là UserDetails

HTTP Basic/form login có thể dùng `UserDetails`; bearer JWT/OIDC thường có loại principal khác. Trong controller sử dụng `Authentication`/`getName()` hoặc adapter có hợp đồng rõ. Với `@AuthenticationPrincipal`, hãy bảo đảm đúng type ứng với security chain đang dùng.

## 13. Checklist thiết kế một UserDetailsService production

- **Identifier:** Có login key duy nhất trong namespace? Cách canonicalize case, Unicode, email thay đổi và tenant đã xác định chưa?
- **Nguồn dữ liệu:** Query có bắt buộc tenant/issuer? Có xử lý account bị xóa, chuyển tenant và soft delete không?
- **Verifier:** Mật khẩu chỉ lưu dạng hash thích hợp; `PasswordEncoder` đọc được format hiện tại và có kế hoạch nâng cấp hash chưa?
- **Trạng thái:** `enabled`/`locked`/`expired`/`passwordExpired` được map đúng cực tính và phản ánh chính sách login?
- **Authorities:** Nguồn quyền có thẩm quyền, scope/tenant đúng, không nhận role do client khai, không null?
- **Principal:** Chỉ giữ account ID, username và dữ liệu phục vụ xác thực cần thiết; hạn chế PII và dữ liệu lazy?
- **Cache:** Có TTL/invalidation khi khóa user, đổi password, đổi quyền, xóa account? Đã test erasure với cached object chưa?
- **Đăng nhập thất bại:** Không rò thông tin tài khoản tồn tại/không tồn tại; log metadata vừa đủ mà không lộ password?
- **Bản ghi phiên/token:** Quy định khi user bị disable hoặc quyền đổi thì session và JWT cũ còn hợp lệ trong bao lâu?
- **Multi-factor và federation:** Nếu cơ chế này có IdP/OTP/passkey, có rõ trách nhiệm nào thuộc provider khác thay vì gán tất cả vào `UserDetails`?
- **Testing:** Các nhánh bad password/unknown user/account flags/authority/tenant/cache đều có phép thử hữu nghĩa?

## 14. Ma trận kiểm thử cho từng dữ liệu mà provider cần

| Case | Dữ liệu đưa vào | Kết quả đúng |
| --- | --- | --- |
| User tồn tại, raw password đúng, mọi status flag hợp lệ | `UserDetails` đầy đủ và hash khớp | Authentication thành công; principal/authorities đúng. |
| User không tồn tại | Loader không tìm được account | Ném `UsernameNotFoundException` ở service; authentication thất bại và client nhận response phù hợp. |
| User tồn tại, password sai | Hash hợp lệ nhưng `matches=false` | Authentication thất bại; không cấp authorities. |
| Hash cũ/unknown prefix | `PasswordEncoder` không xử lý được format | Không chấp nhận mặc định; xử lý migration/encoder an toàn. |
| User bị khóa | `isAccountNonLocked=false` | Login bị từ chối dù raw password đúng. |
| User bị disable | `isEnabled=false` | Login bị từ chối. |
| Account hết hạn | `isAccountNonExpired=false` | Login bị từ chối. |
| Password đã hết hạn | `isCredentialsNonExpired=false` | Login bình thường bị từ chối; recovery/rotation cần flow riêng. |
| Role đúng được nạp | `getAuthorities()` chứa `ROLE_READER` | Endpoint yêu cầu READER có thể cho qua nếu các chính sách khác phù hợp. |
| Role thiếu | Chỉ có `ROLE_READER`, endpoint cần ADMIN | Authentication thành công, authorization từ chối (thường HTTP 403). |
| Request tự gửi `role=ADMIN` | Payload client không phải nguồn quyền | Không tăng quyền. |
| Login trên tenant B với username trùng tenant A | Loader có tenant boundary | Không nạp record của tenant A. |
| Cached UserDetails bị erase hoặc stale | Cache dùng lại instance/hash/status cũ | Không làm hỏng xác thực lần hai; thay đổi state được áp dụng theo freshness policy. |
| Controller trả dữ liệu principal | API response `/api/me` | Không lộ encoded password, raw credential, PII hoặc session secret. |
| JWT authentication trên security chain khác | Principal có thể là Jwt | Business/controller không ép cast tất cả thành UserDetails. |

**Phạm vi kiểm thử quan trọng:** Unit test mapper chỉ chứng minh cách gán giá trị; integration test đi qua security filter/manager và HTTP status mới cho biết tài khoản thực sự bị từ chối. Những case cache/session cần môi trường lưu ngữ cảnh có cùng hành vi production.

## 15. Bài tập tình huống

**Bài 1.** Database có record:

```text
login_name      = "nina"
password_hash   = "{bcrypt}..."
enabled         = true
locked          = true
account_expired = false
password_expired= false
role            = "READER"
```

Hãy xác định `UserDetails` cần trả gì.

**Đáp án:** `getUsername()="nina"`, `getPassword()` chứa hash đã lưu, `getAuthorities()` chứa authority `ROLE_READER` nếu policy dùng role đó. `isEnabled=true`, `isAccountNonLocked=false`, `isAccountNonExpired=true`, `isCredentialsNonExpired=true`. Login username/password thông thường phải bị chặn vì account locked.

**Bài 2.** Một kỹ sư viết:

```java
@Override
public boolean isAccountNonExpired() {
    return account.getExpiredAt() != null;
}
```

Có đúng không?

**Đáp án:** Không. `expiredAt != null` không đủ khẳng định đã hết hạn (vẫn có thể là ngày tương lai); còn hàm `NonExpired` phải trả **true khi account chưa hết hạn**. Cần quy định điều kiện thời gian và clock rõ ràng, ví dụ `expiresAt == null || now.isBefore(expiresAt)` theo policy, chú ý cả timezone và boundary.

**Bài 3.** `loadUserByUsername("alice")` trả object hợp lệ. Có thể dùng object này để tự cấp session đã authenticated mà không kiểm password không?

**Đáp án:** Không. Loader chỉ trả dữ liệu phía server phục vụ xác minh, chưa chứng minh client có credential. Cần provider thực hiện xác thực.

**Bài 4.** `UserDetailsService` trả password hash có prefix `{bcrypt}`. Controller có được xuất hash này khi trả hồ sơ Alice không?

**Đáp án:** Không. Hash là verifier nhạy cảm, người dùng chỉ cần các trường hồ sơ đã được phép xem. Dùng response DTO chỉ gồm dữ liệu được phép; không serialize principal/entity trực tiếp.

**Bài 5.** Alice đã login lúc 09:00 với `ROLE_ADMIN`. Đến 09:05 admin thu hồi role trong DB. Lúc 09:06 Alice gọi API bằng session cũ. `getAuthorities()` mới trong database có bảo đảm API từ chối không?

**Đáp án:** Không tự bảo đảm. Session có thể vẫn chứa authentication snapshot cũ; cần chính sách thu hồi/refresh authorities/kiểm policy mới hoặc invalidate session để bảo đảm thay đổi được phản ánh đúng hạn.

**Bài 6.** Với token OIDC, đoạn code `(UserDetails) authentication.getPrincipal()` có chắc chạy không?

**Đáp án:** Không. Principal type phụ thuộc cơ chế: OIDC/OAuth2/JWT có thể dùng `OAuth2User`, `OidcUser` hoặc `Jwt`. Hãy đọc contract của chain đang dùng hoặc sử dụng adapter thống nhất có kiểm kiểu.

**Bài 7.** Một tài khoản có `enabled=false` nhưng test unit mapper vẫn pass vì `getUsername()` và `getAuthorities()` đúng. Kiểm thử còn thiếu gì?

**Đáp án:** Phải kiểm `isEnabled()=false` và integration test authentication thông qua provider/filter thật phải từ chối đăng nhập; có thể kiểm exception ở tầng provider và HTTP 401 ở API theo cấu hình.

## 16. Tài liệu để đối chiếu

- [Spring Security — UserDetails](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/user-details.html): hợp đồng security view, quản lý credential và lưu ý khi dùng cache.
- [Spring Security — UserDetailsService](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/user-details-service.html): nguồn trả username/password/attributes cho xác thực username-password.
- [Spring Security — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/dao-authentication-provider.html): quy trình nạp `UserDetails` và kiểm bằng `PasswordEncoder`.
- [UserDetails Javadoc (Spring Security 6.3)](https://docs.spring.io/spring-security/site/docs/6.3.x/api/org/springframework/security/core/userdetails/UserDetails.html): đủ ba getter và bốn status flag cùng default method.
- [User.UserBuilder Javadoc](https://docs.spring.io/spring-security/site/docs/6.4.x/api/org/springframework/security/core/userdetails/User.UserBuilder.html): `disabled`, `accountLocked`, `accountExpired`, `credentialsExpired`, `roles` và `authorities`.
- [Spring Security — Password Storage](https://docs.spring.io/spring-security/reference/features/authentication/password-storage.html): `PasswordEncoder` và verifier có format thuật toán.
- [Spring Security — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html): mối quan hệ `Authentication`, `AuthenticationManager`, `AuthenticationProvider` và `SecurityContextHolder`.

**Ghi nhớ:** `UserDetails` là **bản dữ liệu tối thiểu, đáng tin cậy về account để provider kiểm credential và trạng thái**, không phải lời tuyên bố của client và không phải toàn bộ domain user. `UserDetailsService` tìm đúng bản ghi, `PasswordEncoder` kiểm verifier, `DaoAuthenticationProvider` quyết định xác thực, `Authentication` mang kết quả, và authorization vẫn kiểm quyền đối với tài nguyên.