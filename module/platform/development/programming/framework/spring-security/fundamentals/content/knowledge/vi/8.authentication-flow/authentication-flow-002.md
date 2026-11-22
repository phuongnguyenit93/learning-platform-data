# AuthenticationManager nhận và trả về Authentication trong Spring Security

Trong Spring Security, **`AuthenticationManager`** là điểm giao tiếp trung tâm của quá trình xác thực: nó **nhận một đối tượng `Authentication` biểu diễn yêu cầu chưa được xác minh**, kiểm tra yêu cầu qua cơ chế xác thực được cấu hình và **trả về một `Authentication` kết quả đáng tin cậy nếu thành công**. Nếu không thể xác thực, phương thức báo lỗi bằng một `AuthenticationException` thích hợp.

Hai bên của phương thức có thể cùng kiểu interface Java `Authentication` nhưng **không cùng mức độ tin cậy**:

- **Đầu vào:** thông tin do client cung cấp hoặc filter trích xuất, ví dụ username/password, chưa được xem là danh tính đã xác thực.
- **Đầu ra:** principal đã được xác minh, trạng thái authenticated và các `GrantedAuthority` được cấp từ nguồn tin cậy. Credentials nhạy cảm có thể đã được xóa.
- **Thất bại:** phương thức **ném exception**, không cấp một đối tượng authentication thành công giả.
- **Sau khi nhận kết quả:** thành phần gọi manager, thường là security filter, xử lý `SecurityContext`, session hoặc cơ chế token theo luồng tương ứng.

Trọng tâm bài này là câu hỏi: **`AuthenticationManager.authenticate(...)` thật sự nhận gì, làm gì, trả gì, ai sử dụng kết quả và tại sao không nên tự gán authenticated=true?** Ví dụ sử dụng **Spring Boot 3.x với Spring Security 6.5, Java 17+, Spring MVC/Servlet**; những API hoặc hành vi dành cho Spring Security 7, OAuth2 hay WebFlux cần kiểm tra theo phiên bản đang dùng.

## 1. Hợp đồng của AuthenticationManager

Interface `AuthenticationManager` nằm trong package `org.springframework.security.authentication`. Hợp đồng cốt lõi được mô tả bằng một phương thức:

```java
public interface AuthenticationManager {
    Authentication authenticate(Authentication authentication)
            throws AuthenticationException;
}
```

Đây là hình dạng rút gọn để học, không phải toàn bộ khai báo Javadoc. Các tên thường gặp:

| Thành phần | Vai trò | Cách dùng |
| --- | --- | --- |
| `AuthenticationManager` | Interface xác định **hợp đồng xác thực** | Bên gọi truyền `Authentication` vào `authenticate` |
| `ProviderManager` | Triển khai `AuthenticationManager` thông dụng | Điều phối nhiều `AuthenticationProvider` |
| `AuthenticationProvider` | Xác thực một loại `Authentication` cụ thể | Kiểm tra credentials/nguồn identity; có thể không hỗ trợ kiểu request |
| `Authentication` | Yêu cầu hoặc kết quả xác thực | `principal`, `credentials`, `authorities`, `isAuthenticated` |
| `AuthenticationException` | Nhóm lỗi xác thực | Password sai, tài khoản bị khóa, không hỗ trợ token... |
| `SecurityContextHolder` | Nơi truy cập `SecurityContext` hiện tại | Được filter/luồng caller cập nhật sau xác thực thành công |

`AuthenticationManager` **không phải** cơ chế phân quyền. Nó trả danh tính và authorities đủ tin cậy để các rule như `hasRole("ADMIN")` hoặc `hasAuthority("report:read")` kiểm tra sau đó.

### 1.1. Vì sao đầu vào và đầu ra đều là Authentication?

Spring Security dùng chung abstraction `Authentication` cho hai vai trò:

1. Mang bằng chứng xác thực và danh tính đang được tuyên bố tới manager.
2. Mang kết quả đã xác minh về lại filter, controller hoặc service có trách nhiệm thiết lập ngữ cảnh.

Ví dụ đầu vào:

```java
Authentication request =
    UsernamePasswordAuthenticationToken.unauthenticated(
        "alice", "password-from-client"
    );
```

Sau đó:

```java
Authentication result = authenticationManager.authenticate(request);
```

Lúc này `request.isAuthenticated()` là `false`, còn `result.isAuthenticated()` trong luồng xác thực thành công tiêu chuẩn là `true`. `result.getPrincipal()` có thể là `UserDetails` đã xác minh; `result.getAuthorities()` là các quyền được gắn từ user store/provider. `result.getCredentials()` có thể đã trở thành `null` do cơ chế xóa dữ liệu nhạy cảm.

### 1.2. Điều gì không được làm?

Không tạo kết quả “thành công” từ dữ liệu chưa kiểm tra:

```java
// Anti-pattern: không có bước kiểm tra credentials hoặc nguồn quyền.
Authentication forged =
    UsernamePasswordAuthenticationToken.authenticated(
        requestBody.username(),
        null,
        requestBody.roles().stream()
            .map(SimpleGrantedAuthority::new)
            .toList()
    );
```

Factory `authenticated(...)` **chỉ tạo một object mang trạng thái đã xác thực**. Nó không chứng minh username/password hợp lệ, không kiểm tra token và không xác minh `roles` do client khai. Chỉ thành phần trong trust boundary thật sự đã xác thực mới được tạo kết quả đáng tin.

## 2. Đọc giá trị Authentication trước và sau authenticate()

Giả sử Alice gửi username/password đúng; user store đang cấp `ROLE_USER` và `report:read`.

| Thuộc tính | `Authentication` đầu vào | `Authentication` kết quả thành công |
| --- | --- | --- |
| `getPrincipal()` | Thường là chuỗi `"alice"` do client khai | Thường là đối tượng `UserDetails` đã được tìm và xác minh |
| `getCredentials()` | Raw password được đưa cho provider | Có thể được xóa (`null`) sau khi xác thực |
| `getAuthorities()` | Thường rỗng/chưa có quyền đáng tin cậy | Có `ROLE_USER`, `report:read` theo user store |
| `isAuthenticated()` | `false` với `unauthenticated(...)` | `true` nếu provider trả kết quả đã xác minh |
| `getName()` | Có thể trả tên do client khai | Tên theo principal đã được xác minh |
| Độ tin cậy | Chưa được chấp nhận | Được provider xác thực thành công |
| Cách ứng dụng dùng | Làm bằng chứng cần kiểm tra | Đưa vào security context và kiểm tra chính sách |

`getName() == "alice"` ở **đầu vào** không phải bằng chứng Alice thật. `getName() == "alice"` ở **đầu ra** có ý nghĩa sau khi provider kiểm tra credentials và trạng thái user theo đúng trust policy.

Đừng giả định manager luôn **sửa chính object đầu vào**. Provider có thể tạo **một đối tượng Authentication mới** hoặc có cách biểu diễn khác. Code ứng dụng phải sử dụng **giá trị được trả về** từ `authenticate`:

```java
Authentication request = UsernamePasswordAuthenticationToken
    .unauthenticated("alice", password);

Authentication verified = manager.authenticate(request);

// Đúng: sử dụng verified.
// Sai: bỏ qua verified rồi coi request ban đầu là đã xác thực.
```

Không ép kiểu đầu vào hoặc đầu ra thành `UsernamePasswordAuthenticationToken` nếu hệ thống có nhiều cơ chế xác thực. `Authentication` là interface; kiểu cụ thể phụ thuộc provider và phương thức xác thực.

## 3. Luồng Servlet thực tế: ai gọi AuthenticationManager?

Một request điển hình dùng HTTP Basic hoặc form login:

```text
Client
  |  username/password trong Basic header hoặc login form
  v
SecurityFilterChain
  |
  +-- Authentication filter nhận request
  |      |
  |      +-- Tạo Authentication yêu cầu xác thực
  |      |       principal = username khai báo
  |      |       credentials = password
  |      |       authenticated = false
  |      |
  |      v
  |  AuthenticationManager.authenticate(request)
  |      |
  |      v
  |  ProviderManager
  |      |
  |      v
  |  AuthenticationProvider phù hợp
  |      |
  |      +-- Kiểm tra danh tính / bằng chứng / trạng thái tài khoản
  |      +-- Gán authorities từ nguồn tin cậy
  |      |
  |      +-- THẤT BẠI -> AuthenticationException
  |      |       -> failure handler / entry point, tùy cơ chế
  |      |
  |      +-- THÀNH CÔNG -> Authentication đã xác minh
  |              |
  |              +-- Credentials có thể được xóa
  |              v
  |        Filter nhận result
  |              |
  |              +-- SecurityContext / SecurityContextRepository
  |              +-- Session hoặc xử lý token khi phù hợp
  |              v
  +-- AuthorizationFilter / method authorization
  |      |
  v      v
 Controller / Service
```

Sơ đồ là **mô hình trách nhiệm**, không cam kết thứ tự filter chính xác trong mọi cơ chế. Một request có thể bị chặn bởi CSRF trước khi tới controller; với session, Authentication có thể được khôi phục mà không gọi password provider ở mỗi request.

### 3.1. Filter tạo input, manager không đọc HTTP trực tiếp

`AuthenticationManager.authenticate` chỉ nhận một đối tượng `Authentication`; nó không có tham số `HttpServletRequest` hay `HttpServletResponse`. Một filter cụ thể như `BasicAuthenticationFilter` hoặc `UsernamePasswordAuthenticationFilter` chịu trách nhiệm đọc request, tạo token phù hợp và chuyển tới manager.

Điều này giúp các phương thức xác thực khác nhau cùng dùng contract chung. HTTP Basic và form login có thể đều tạo `UsernamePasswordAuthenticationToken`, nhưng không nhất thiết mọi cơ chế đều dùng kiểu đó.

### 3.2. AuthenticationManager không trực tiếp xuất 401/403

Manager thường **ném exception** nếu authentication thất bại. Phần chuyển exception thành HTTP response thuộc security filter/handler:

- HTTP Basic thiếu hoặc sai thông tin thường trả **401 Unauthorized** và challenge `WWW-Authenticate`.
- Form login thất bại có thể redirect về `/login?error` thay vì trả JSON 401.
- User đã được xác thực nhưng thiếu `ROLE_ADMIN` thường nhận **403 Forbidden** từ **authorization**.
- CSRF token sai có thể cũng tạo 403, không nhất thiết liên quan authorities.

Một caller không thuộc HTTP (ví dụ command-line job) có thể bắt `AuthenticationException` và xử lý theo cách riêng, vì `AuthenticationManager` không gắn trực tiếp với status code.

### 3.3. AuthenticationEntryPoint và AuthenticationFailureHandler

`AuthenticationEntryPoint` khởi tạo yêu cầu xác thực cho client khi một tài nguyên cần credentials. `AuthenticationFailureHandler` thường xử lý lỗi của một lần submit login theo cơ chế phù hợp. Hai thành phần này không phải là `AuthenticationManager`.

Tùy filter và exception handling, cùng một `BadCredentialsException` có thể được trình bày khác nhau ở web, API hoặc test. Hãy kiểm tra cơ chế được chọn chứ không suy ra trạng thái HTTP chỉ từ tên exception.

## 4. AuthenticationProvider và ProviderManager phối hợp thế nào?

Phần lớn ứng dụng không tự triển khai trực tiếp `AuthenticationManager`. Spring Security sử dụng `ProviderManager` với một hoặc nhiều `AuthenticationProvider`.

Mô hình:

```text
AuthenticationManager  (interface)
        |
        v
ProviderManager         (implementation)
        |
        +-- Provider A: DaoAuthenticationProvider
        |       hỗ trợ UsernamePasswordAuthenticationToken
        |
        +-- Provider B: JWT / SAML / custom provider tùy hệ thống
        |       hỗ trợ kiểu token riêng
        |
        +-- Provider C: một cơ chế đặc thù khác
        |
        +-- Parent AuthenticationManager (nếu được cấu hình)
        |
        +-- Result Authentication hoặc AuthenticationException
```

Đừng coi mỗi provider luôn chạy. `ProviderManager` xét khả năng hỗ trợ và kết quả của các provider theo cấu hình.

### 4.1. Hợp đồng AuthenticationProvider

Một provider có hai phương thức chính:

```java
public interface AuthenticationProvider {
    Authentication authenticate(Authentication authentication)
            throws AuthenticationException;

    boolean supports(Class<?> authentication);
}
```

Ở đây:

- `supports(...)` nói provider **có khả năng xử lý kiểu Authentication nào**.
- Nếu provider **không hỗ trợ** kiểu request, manager có thể bỏ qua và xét provider khác.
- Nếu được gọi nhưng **không thể đưa ra kết luận**, provider có thể trả `null` để nơi điều phối thử provider tiếp theo.
- Nếu xác minh **thành công**, provider trả Authentication kết quả.
- Nếu credentials hoặc điều kiện xác thực **thất bại**, provider có thể ném `AuthenticationException` phù hợp.

**Cần phân biệt:** provider có thể trả null để biểu thị “không có quyết định”; đối với caller của `AuthenticationManager`, contract thông thường là **trả đối tượng đã xác thực hoặc ném exception**, không dùng null như “đăng nhập thành công chưa có user”.

### 4.2. Nhiều provider và parent manager

`ProviderManager` có thể phối hợp nhiều provider. Một số provider chỉ hỗ trợ username/password; một provider khác hỗ trợ kiểu token custom. Khi parent `AuthenticationManager` được cấu hình, manager con có thể ủy quyền xử lý về parent theo điều kiện thực tế.

Điều này hữu ích trong ứng dụng có nhiều `SecurityFilterChain`:

```text
/api/** chain -> manager API -> provider token
                         |
                         +-- parent manager dùng chung

/web/** chain -> manager Web -> provider password
                         |
                         +-- parent manager dùng chung
```

Sơ đồ là ví dụ kiến trúc có thể thiết kế, **không có nghĩa Boot tự dựng tất cả những manager đó**. Với nhiều chain/provider, phải xác định chính xác manager/filter nào xử lý request cụ thể, tránh tình huống một provider được dùng ngoài phạm vi được phép.

### 4.3. Khi provider không hỗ trợ loại token

Nếu gửi một kiểu `Authentication` mà **không provider nào xử lý** và không có parent đáp ứng, `ProviderManager` có thể ném `ProviderNotFoundException`.

Ví dụ không nên nhầm `supports(UsernamePasswordAuthenticationToken.class)` với việc luôn đăng nhập thành công. `supports` chỉ chỉ ra loại request được hiểu. Provider vẫn cần xác minh username/password và các điều kiện tài khoản.

### 4.4. Tại sao không nên tạo ProviderManager tùy tiện?

Tự tạo nhiều `ProviderManager` hoặc inject manager không gắn với HTTP chain có thể làm request bị xử lý bằng provider ngoài dự kiến. Khi cần xuất manager thành bean, hãy cấu hình rõ `AuthenticationProvider`, `UserDetailsService`, `PasswordEncoder` và liên kết với chain khi phù hợp.

Với ứng dụng web username/password bình thường, Spring Boot và Spring Security đã có khả năng cấu hình manager/provider từ bean user store; **không nhất thiết cần viết bean AuthenticationManager thủ công**. Chỉ tạo một manager riêng khi có nhu cầu rõ ràng như direct call ở một service hoặc muốn tự thiết kế chuỗi provider.

## 5. DaoAuthenticationProvider: ví dụ xác thực username/password

`DaoAuthenticationProvider` là một `AuthenticationProvider` sử dụng `UserDetailsService` và `PasswordEncoder` để xác minh username/password.

Quy trình ý nghĩa:

1. Nhận `UsernamePasswordAuthenticationToken` chưa xác thực.
2. Đọc username từ token để gọi `UserDetailsService.loadUserByUsername(...)`.
3. Kiểm tra trạng thái tài khoản theo khả năng provider và loại `UserDetails`.
4. Lấy password hash từ `UserDetails` và dùng `PasswordEncoder.matches(rawPassword, storedHash)` để xác minh.
5. Nếu không hợp lệ, ném lỗi xác thực tương ứng.
6. Nếu hợp lệ, tạo Authentication kết quả với principal đã được xác minh và authorities phù hợp.
7. `ProviderManager` có thể xóa credentials nhạy cảm khỏi kết quả sau đó.

Ví dụ tạo user store:

```java
UserDetails alice = User.withUsername("alice")
    .password(passwordEncoder.encode("demo-alice-pass"))
    .authorities("ROLE_USER", "report:read")
    .build();

UserDetailsService users = new InMemoryUserDetailsManager(alice);
```

Đây là đoạn Spring Security sử dụng class/import và một bean encoder được cấu hình; không biên dịch độc lập bằng `javac` nếu thiếu dependencies.

**Những điều cần nhớ:**

- `loadUserByUsername` **không tự so sánh password**; nó trả dữ liệu để provider kiểm tra.
- `PasswordEncoder` **không tự cấp quyền**; nó kiểm tra tính khớp của raw password với hash.
- `AuthenticationManager` điều phối qua provider, không tự đọc SQL hay JWT theo một cách mặc định cho tất cả ứng dụng.
- `getAuthorities()` của kết quả thường đến từ user store/provider/converter **đáng tin cậy**, không đến từ mảng roles do client tự gửi.
- `PasswordEncoder.encode(raw)` có thể dùng salt, vì vậy không so hai lần `encode` bằng chuỗi equals; phải dùng `matches`.
- Password demo chỉ dùng trong học tập; triển khai thật cần HTTPS, quản lý secret và user database/IdP theo kiến trúc.

### 5.1. Vai trò của UserDetails

`UserDetails` mô tả principal ở nhiều luồng username/password. Nó có username, password hash, authorities và trạng thái tài khoản như enabled, account non-locked. Sau thành công, `Authentication.getPrincipal()` thường là một `UserDetails` thay vì chuỗi username đầu vào.

Nhưng không nên viết:

```java
UserDetails user = (UserDetails) authentication.getPrincipal();
```

ở mọi nơi nếu ứng dụng có JWT/OIDC hoặc custom provider. Với JWT resource server, principal có thể là `Jwt`; với OAuth2 login có thể là `OAuth2User`. Hãy dựa vào cơ chế đã được cấu hình, hoặc dùng adapter chuẩn hóa subject ID.

## 6. Exception contract: khi nào authenticate thất bại?

`AuthenticationManager.authenticate(...)` có thể ném các subclass của `AuthenticationException`.

| Exception / nhóm | Tình huống thường gặp | Ý nghĩa |
| --- | --- | --- |
| `BadCredentialsException` | Username/password không được chấp nhận | Credentials không hợp lệ theo provider |
| `DisabledException` | Tài khoản bị vô hiệu hóa và manager có thể kiểm tra trạng thái | Không nên xác thực như tài khoản đang active |
| `LockedException` | Tài khoản bị khóa và manager kiểm tra được | Từ chối tài khoản bị khóa |
| `CredentialsExpiredException` | Credentials đã hết hạn theo chính sách | Cần quy trình cập nhật credentials |
| `ProviderNotFoundException` | Không provider/parent nào hỗ trợ kiểu Authentication được đưa vào | Manager thiếu khả năng xử lý request |
| `AuthenticationServiceException` | Lỗi dịch vụ xác thực / hệ thống liên quan | Không mặc nhiên coi là password sai |

Theo contract Javadoc, nếu có thể kiểm tra tài khoản disabled/locked, các điều kiện đó phải được ưu tiên phù hợp trước khi kiểm tra credentials để tránh thử password trên tài khoản đã bị vô hiệu/khóa. Chi tiết thông báo trả về **không nên tiết lộ** account tồn tại hay không cho client.

### 6.1. Vì sao không dùng null để báo thất bại?

Trong code gọi `AuthenticationManager`, pattern là:

```java
try {
    Authentication verified = manager.authenticate(request);
    // Sử dụng verified đã xác thực.
} catch (AuthenticationException failure) {
    // Xử lý xác thực thất bại, không cấp quyền.
}
```

**Không viết** `if (manager.authenticate(request) == null)` để kiểm tra password sai theo kiểu API thông thường; đây không phải contract mà client của manager nên dựa vào. Hãy dùng exception và hành vi của provider/filter đã được định nghĩa.

### 6.2. Không trả nguyên exception ra response

Với REST hoặc form login tự thiết kế, nên dùng cơ chế entry point/failure handler phù hợp. Thông báo cho client có thể là “Thông tin đăng nhập không hợp lệ” thay vì đưa toàn bộ nguyên nhân account disabled, user không tồn tại hoặc password sai, để giảm user enumeration. Nội bộ vẫn cần audit và metric phù hợp, không log raw credentials, password hash, access token hoặc session cookie.

### 6.3. Không nuốt lỗi dịch vụ thành một Authentication thành công

Nếu database user hoặc IdP không phản hồi, policy phải **từ chối hoặc báo lỗi có kiểm soát**, không dựng Authentication authenticated từ thông tin client tự khai. Fail closed có thể trả 503 cho lỗi hạ tầng thay vì 401/403; đó là quyết định API riêng, không phải lý do để cho request đi tiếp.

## 7. Xóa credentials sau xác thực: một chi tiết dễ gây hiểu nhầm

`ProviderManager` mặc định có cơ chế xóa credentials khỏi Authentication thành công khi phù hợp, thường qua `CredentialsContainer.eraseCredentials()`. Với `UsernamePasswordAuthenticationToken`, credentials thường bị xóa sau xác thực.

Ví dụ:

```java
Authentication request =
    UsernamePasswordAuthenticationToken.unauthenticated(
        "alice", "demo-alice-pass"
    );

Authentication result = manager.authenticate(request);

System.out.println(result.isAuthenticated());   // true, nếu thành công
System.out.println(result.getCredentials());    // thường null
```

Đừng khẳng định mọi provider/token luôn cho `getCredentials()==null`. Cơ chế xác thực có thể giữ thông tin khác; điều cần làm là **không lưu trữ hoặc log bí mật ngoài nhu cầu hợp lệ**.

### 7.1. Credentials rỗng không phải logout

Nếu `result.isAuthenticated()==true` và principal/authorities hợp lệ, `getCredentials()==null` sau khi xóa bí mật không có nghĩa người dùng đã đăng xuất. Thực tế Spring Security còn cần ngữ cảnh session/token/context phù hợp để quyết định request tiếp theo.

Đồng thời, **isAuthenticated true chưa đủ** để cấp mọi quyền; với anonymous token, cờ này có thể true ở mức object, còn policy `authenticated()` của Spring Security phân biệt anonymous.

### 7.2. Thận trọng với UserDetails được cache

Nếu provider và cache dùng chung tham chiếu một `UserDetails`, xóa credentials trên Authentication kết quả có thể xóa cả password field của object trong cache. Lần xác thực tiếp theo có thể không còn hash để kiểm tra.

Các cách xử lý phù hợp gồm:

- Trả bản sao UserDetails khi truy xuất từ cache/provider;
- Thiết kế cache không chia sẻ object có thể bị xóa credentials;
- Kiểm tra vòng đời caching, provider và password hash;
- Chỉ thay đổi `eraseCredentialsAfterAuthentication` sau khi đánh giá rủi ro giữ dữ liệu nhạy cảm trong bộ nhớ.

Không tắt credential erasure chỉ để “làm test pass” mà không hiểu hậu quả.

## 8. Sau authenticate(): ai lưu SecurityContext?

Điểm kiến trúc quan trọng nhất: **một lời gọi trực tiếp `AuthenticationManager.authenticate` không tự biến request HTTP hiện tại hoặc các request tương lai thành đăng nhập có phiên**.

Trong luồng do Spring Security filters quản lý, filter gọi manager rồi xử lý kết quả; filter có thể thiết lập `SecurityContextHolder`, lưu context qua `SecurityContextRepository` và thực hiện session strategy, success handler hay remember-me tùy cơ chế.

Tương phản:

```java
Authentication verified = manager.authenticate(request);

// verified là KẾT QUẢ xác thực.
// Tự gọi manager ở service không bảo đảm:
// - SecurityContextHolder đã được set,
// - HttpSession đã được tạo/lưu,
// - cookie đã được gửi,
// - JWT/refresh token đã được cấp,
// - request sau tự mang identity này.
```

Một ví dụ rút gọn về thiết lập context cho **luồng được thiết kế riêng**, chỉ minh họa bước trên thread hiện tại:

```java
SecurityContext newContext =
    SecurityContextHolder.createEmptyContext();
newContext.setAuthentication(verified);
SecurityContextHolder.setContext(newContext);
```

Đoạn này **chưa phải một login endpoint hoàn chỉnh**. Khi cần duy trì đăng nhập qua request, ứng dụng còn phải sử dụng `SecurityContextRepository.saveContext(...)` theo cơ chế session, xử lý session fixation, CSRF, cookie và success/failure flow phù hợp. Với stateless token API, việc cấp token và kiểm tra trên request sau là một thiết kế riêng. Ưu tiên sử dụng form login/HTTP Basic/OAuth2 integrations được hỗ trợ thay vì tự dựng một login controller thiếu bước bảo vệ.

### 8.1. Tại sao nên tạo SecurityContext mới?

Spring Security hướng dẫn dùng `SecurityContextHolder.createEmptyContext()` rồi gắn Authentication vào context đó trong tình huống phải làm thủ công, thay vì vô điều kiện mutate một context có thể đang được dùng chung. Điều này giảm nguy cơ vấn đề giữa các thread trong các cấu hình đặc thù.

### 8.2. ThreadLocal và bất đồng bộ

Trong mô hình Servlet thông thường, `SecurityContextHolder` dùng một chiến lược dựa trên thread. Điều này không có nghĩa Authentication sẽ tự truyền tới `CompletableFuture`, thread tự tạo hoặc job nền. Khi cần làm việc bất đồng bộ dưới identity của user, phải chọn cơ chế truyền context và hạn chế quyền phù hợp. Không sử dụng một global context chứa admin Authentication cho mọi thread.

### 8.3. Phân biệt authentication và authorization

Manager xác minh danh tính và tạo authorities; còn `AuthorizationManager` hoặc rule của Spring Security đánh giá quyền truy cập:

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/admin").hasRole("ADMIN")
    .anyRequest().authenticated()
)
```

User Alice có thể đã được manager xác thực nhưng thiếu `ROLE_ADMIN`, nên GET `/api/admin` vẫn bị chặn. `isAuthenticated()` không thay thế `hasRole`, `hasAuthority` và kiểm tra owner/tenant.

## 9. Ví dụ Spring Boot 3 / Spring Security 6.5: manager thật và kết quả thật

Bài thực hành dùng Java 17+, Spring MVC và HTTP Basic, nhưng **công khai một bean `AuthenticationManager`** để có thể gọi trực tiếp trong `CommandLineRunner` và bài test. Phần cấu hình tạo `ProviderManager` với một `DaoAuthenticationProvider`. API HTTP dùng **chính manager đó** qua `HttpSecurity.authenticationManager(manager)`, giúp kết nối mô hình lý thuyết với hệ thống thực.

Hai tài khoản demo:

| Username | Password thử nghiệm | Authorities | Trạng thái |
| --- | --- | --- | --- |
| `alice` | `demo-alice-pass` | `ROLE_USER`, `report:read` | enabled |
| `admin` | `demo-admin-pass` | `ROLE_USER`, `ROLE_ADMIN` | enabled |
| `disabled` | `demo-disabled-pass` | `ROLE_USER` | disabled |

Để chạy ví dụ dùng đúng **Spring Boot 3.x quản lý một phiên bản Spring Security 6.5 tương thích**; API constructor `DaoAuthenticationProvider(UserDetailsService)` có trong Spring Security 6.5. Nếu dự án Boot 3 cũ hơn đang giải quyết Spring Security 6.0–6.4, hãy tra đúng Javadoc/constructor hoặc nâng dependency đồng bộ theo BOM thay vì trộn từng JAR.

### 9.1. Dependency Gradle

Trong một dự án Spring Boot đã cấu hình plugins, repository, Java toolchain và dependency management, phần `dependencies` của `build.gradle` Groovy DSL:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Đây là **đoạn dependency**, không phải toàn bộ Gradle project. Với Maven, dùng hai starter tương đương và `spring-security-test` ở test scope. Không hardcode version Spring Security khác Boot BOM mà chưa kiểm tra tương thích.

### 9.2. Main class

Tạo `src/main/java/example/authmanager/AuthenticationManagerDemoApplication.java`:

```java
package example.authmanager;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AuthenticationManagerDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(AuthenticationManagerDemoApplication.class, args);
    }
}
```

### 9.3. SecurityConfig: định nghĩa và gắn manager

Tạo `src/main/java/example/authmanager/SecurityConfig.java`:

```java
package example.authmanager;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("demo-alice-pass"))
            .authorities("ROLE_USER", "report:read")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("demo-admin-pass"))
            .authorities("ROLE_USER", "ROLE_ADMIN")
            .build();

        UserDetails disabled = User.withUsername("disabled")
            .password(encoder.encode("demo-disabled-pass"))
            .authorities("ROLE_USER")
            .disabled(true)
            .build();

        return new InMemoryUserDetailsManager(alice, admin, disabled);
    }

    @Bean
    AuthenticationManager authenticationManager(
            UserDetailsService users,
            PasswordEncoder encoder
    ) {
        DaoAuthenticationProvider provider =
            new DaoAuthenticationProvider(users);
        provider.setPasswordEncoder(encoder);

        return new ProviderManager(provider);
    }

    @Bean
    SecurityFilterChain webSecurity(
            HttpSecurity http,
            AuthenticationManager manager
    ) throws Exception {
        return http
            .authenticationManager(manager)
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/identity")
                    .authenticated()
                .requestMatchers(HttpMethod.GET, "/api/admin")
                    .hasRole("ADMIN")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
```

Từng thành phần có nhiệm vụ rõ ràng:

1. `PasswordEncoder` hash password khi khởi tạo user store. Không dùng plaintext hay `{noop}` cho tài khoản thật.
2. `UserDetailsService` lưu user và các quyền đáng tin cậy trong bộ nhớ để demo; production sẽ dùng DB/IdP.
3. `DaoAuthenticationProvider` lấy user từ store và kiểm tra password bằng encoder.
4. `ProviderManager` điều phối provider và là implementation `AuthenticationManager` được expose thành Spring bean.
5. `HttpSecurity.authenticationManager(manager)` dùng manager này cho security chain đã tạo.
6. `httpBasic` bật filter xử lý HTTP Basic; đây là nơi HTTP request được chuyển thành Authentication đầu vào.
7. `authorizeHttpRequests` là **authorization**: dù login thành công vẫn cần role đúng cho `/api/admin`.
8. `anyRequest().denyAll()` chặn các HTTP URL chưa khai báo. Dự án thật có thể có các route public/login khác phải khai báo rõ ràng.
9. Security CSRF mặc định còn bật cho các method cần bảo vệ; ví dụ này chỉ dùng GET để tập trung vào authenticate.

Cấu hình này minh họa rõ **quan hệ manager–provider**, không phải gợi ý rằng mọi ứng dụng Spring Boot đều phải tự khai báo provider và manager.

### 9.4. Quan sát trực tiếp authenticate ở lúc startup

Tạo `src/main/java/example/authmanager/AuthenticationInspector.java`:

```java
package example.authmanager;

import java.util.stream.Collectors;

import org.springframework.boot.CommandLineRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;

@Configuration
public class AuthenticationInspector {

    @Bean
    CommandLineRunner inspectManager(AuthenticationManager manager) {
        return args -> {
            Authentication request =
                UsernamePasswordAuthenticationToken.unauthenticated(
                    "alice", "demo-alice-pass"
                );

            System.out.println(
                "demo.request.authenticated=" + request.isAuthenticated()
            );
            System.out.println(
                "demo.request.authorities=" + request.getAuthorities().size()
            );

            Authentication result = manager.authenticate(request);

            String authorities = result.getAuthorities().stream()
                .map(GrantedAuthority::getAuthority)
                .sorted()
                .collect(Collectors.joining(","));

            System.out.println(
                "demo.result.name=" + result.getName()
            );
            System.out.println(
                "demo.result.authenticated=" + result.isAuthenticated()
            );
            System.out.println(
                "demo.result.authorities=" + authorities
            );
            System.out.println(
                "demo.result.credentialsErased="
                    + (result.getCredentials() == null)
            );
        };
    }
}
```

Khi ứng dụng khởi động thành công, giữa các dòng Spring Boot log có **sáu dòng demo dự kiến**:

```text
demo.request.authenticated=false
demo.request.authorities=0
demo.result.name=alice
demo.result.authenticated=true
demo.result.authorities=ROLE_USER,report:read
demo.result.credentialsErased=true
```

Đó là **kết quả dự kiến theo mã và ProviderManager trong cấu hình trên**, không phải stdout đã được ghi nhận từ một lần chạy thực tế tại đây. Log thời gian startup, version, cổng web và thứ tự thông báo framework có thể khác. Ta chỉ so sánh các dòng bắt đầu bằng `demo.`.

Vì `ProviderManager` mặc định xóa credentials từ token kết quả, flag `credentialsErased` trong ví dụ này dự kiến là `true`. Tuy nhiên, không mặc định áp dụng kết luận đó cho mọi implementation/custom provider.

**Điểm quan trọng:** gọi manager ở `CommandLineRunner` kiểm tra username/password và nhận Authentication, nhưng nó **không tự tạo cookie đăng nhập hay gắn Alice với các HTTP request sau đó**. Mỗi HTTP request tới API vẫn cần cơ chế authentication của chính nó.

### 9.5. Controller dùng Authentication từ security context

Tạo `src/main/java/example/authmanager/IdentityController.java`:

```java
package example.authmanager;

import java.util.List;
import java.util.Map;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class IdentityController {

    @GetMapping("/api/identity")
    Map<String, Object> identity(Authentication authentication) {
        List<String> authorities = authentication.getAuthorities().stream()
            .map(GrantedAuthority::getAuthority)
            .sorted()
            .toList();

        return Map.of(
            "name", authentication.getName(),
            "authorities", authorities
        );
    }

    @GetMapping("/api/admin")
    Map<String, String> admin() {
        return Map.of("message", "admin allowed");
    }
}
```

Controller nhận `Authentication` được filter đặt vào request/security context sau khi HTTP Basic đi qua manager. Controller không lấy identity từ `userId` trong query string hoặc header tùy ý của client, và không cần tự gọi `manager.authenticate` lần nữa.

Response của Alice có thể là:

```json
{
  "name": "alice",
  "authorities": ["ROLE_USER", "report:read"]
}
```

Thứ tự **các trường JSON** có thể khác tùy serializer, còn danh sách authorities đã được sắp xếp trong code. Không trả `authentication.getCredentials()` hoặc serialize nguyên `Authentication` ra API.

### 9.6. Chạy bằng HTTP client

Trong root dự án:

```bash
./gradlew bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Giả sử ứng dụng chạy ở `http://localhost:8080`:

```bash
# Không có Basic credentials: 401
curl -i http://localhost:8080/api/identity

# Alice có password đúng: 200 và danh tính Alice
curl -i -u alice:demo-alice-pass http://localhost:8080/api/identity

# Password sai: 401
curl -i -u alice:wrong-pass http://localhost:8080/api/identity

# Tài khoản disabled: xác thực bị từ chối
curl -i -u disabled:demo-disabled-pass \
  http://localhost:8080/api/identity

# Alice đã xác thực, nhưng thiếu ROLE_ADMIN: 403
curl -i -u alice:demo-alice-pass http://localhost:8080/api/admin

# Admin có ROLE_ADMIN: 200
curl -i -u admin:demo-admin-pass http://localhost:8080/api/admin
```

Trong PowerShell, viết mỗi lệnh trên một dòng thay vì dùng `\` nối dòng của Bash. Các mật khẩu chỉ là dữ liệu demo cục bộ. **HTTP Basic dùng Base64, không mã hóa credentials**, nên production phải dùng HTTPS và cách quản lý secret đúng; `curl -u` chứa password trên command line có thể xuất hiện trong history/process list.

Kết quả minh họa:

| Request | Status dự kiến | Nguyên nhân |
| --- | --- | --- |
| GET `/api/identity` không credentials | 401 | Endpoint yêu cầu authentication |
| GET `/api/identity` với Alice/password đúng | 200 | DaoAuthenticationProvider chấp nhận |
| GET `/api/identity` với password sai | 401 | BadCredentialsException được filter xử lý |
| GET `/api/identity` với tài khoản disabled | 401 | Authentication không thành công |
| GET `/api/admin` với Alice | 403 | Authentication đúng nhưng authority thiếu |
| GET `/api/admin` với Admin | 200 | Authentication đúng và có `ROLE_ADMIN` |

## 10. Integration tests kiểm tra cả manager, provider và filter

Test cần chứng minh hai điều độc lập:

1. `AuthenticationManager.authenticate` trực tiếp xử lý request và trả result chính xác, ném exception phù hợp khi lỗi.
2. HTTP Basic filter sử dụng manager để xử lý API và security context đúng cho request, còn authorization có thể từ chối một user đã đăng nhập.

Với `spring-boot-starter-test` và `spring-security-test`, tạo `src/test/java/example/authmanager/AuthenticationManagerFlowTest.java`:

```java
package example.authmanager;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.DisabledException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class AuthenticationManagerFlowTest {

    @Autowired
    AuthenticationManager manager;

    @Autowired
    MockMvc mvc;

    @Test
    void inputIsNotAuthenticatedYet() {
        Authentication request =
            UsernamePasswordAuthenticationToken.unauthenticated(
                "alice", "demo-alice-pass"
            );

        assertThat(request.isAuthenticated()).isFalse();
        assertThat(request.getName()).isEqualTo("alice");
        assertThat(request.getAuthorities()).isEmpty();
    }

    @Test
    void managerReturnsAuthenticatedResultWithAuthorities() {
        Authentication request =
            UsernamePasswordAuthenticationToken.unauthenticated(
                "alice", "demo-alice-pass"
            );

        Authentication result = manager.authenticate(request);

        assertThat(result).isNotSameAs(request);
        assertThat(result.isAuthenticated()).isTrue();
        assertThat(result.getName()).isEqualTo("alice");
        assertThat(result.getPrincipal()).isInstanceOf(UserDetails.class);
        assertThat(result.getAuthorities().stream()
            .map(GrantedAuthority::getAuthority)
            .toList())
            .contains("ROLE_USER", "report:read");
        assertThat(result.getCredentials()).isNull();
    }

    @Test
    void wrongPasswordThrowsAuthenticationException() {
        Authentication request =
            UsernamePasswordAuthenticationToken.unauthenticated(
                "alice", "wrong-password"
            );

        assertThatThrownBy(() -> manager.authenticate(request))
            .isInstanceOf(BadCredentialsException.class);
    }

    @Test
    void disabledAccountIsRejected() {
        Authentication request =
            UsernamePasswordAuthenticationToken.unauthenticated(
                "disabled", "demo-disabled-pass"
            );

        assertThatThrownBy(() -> manager.authenticate(request))
            .isInstanceOf(DisabledException.class);
    }

    @Test
    void directManagerCallDoesNotSetSecurityContext() {
        SecurityContextHolder.clearContext();
        try {
            Authentication result = manager.authenticate(
                UsernamePasswordAuthenticationToken.unauthenticated(
                    "alice", "demo-alice-pass"
                )
            );

            assertThat(result.isAuthenticated()).isTrue();
            assertThat(SecurityContextHolder.getContext()
                .getAuthentication()).isNull();
        } finally {
            SecurityContextHolder.clearContext();
        }
    }

    @Test
    void anonymousRequestNeedsBasicAuthentication() throws Exception {
        mvc.perform(get("/api/identity"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void validBasicCredentialsAreAccepted() throws Exception {
        mvc.perform(get("/api/identity")
                .with(httpBasic("alice", "demo-alice-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.name").value("alice"));
    }

    @Test
    void invalidBasicCredentialsAreRejected() throws Exception {
        mvc.perform(get("/api/identity")
                .with(httpBasic("alice", "wrong-password")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void authorizationStillChecksRoleAfterAuthentication()
            throws Exception {
        mvc.perform(get("/api/admin")
                .with(httpBasic("alice", "demo-alice-pass")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/api/admin")
                .with(httpBasic("admin", "demo-admin-pass")))
            .andExpect(status().isOk());
    }
}
```

Chạy:

```bash
./gradlew test --tests example.authmanager.AuthenticationManagerFlowTest
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests example.authmanager.AuthenticationManagerFlowTest
```

**Kỳ vọng:** chín phương thức test đều pass với đúng Spring Boot 3/Spring Security 6.5, cấu hình và controller ở trên. Đây là **kỳ vọng từ thiết kế test**, chưa phải kết quả test đã thực thi trong bài học này. Khi nâng version, cần kiểm tra lại API constructor và default behavior theo BOM.

### 10.1. Phân biệt test manager với test HTTP

| Kiểu test | Thành phần được kiểm tra | Không tự chứng minh |
| --- | --- | --- |
| Gọi `manager.authenticate(...)` | Contract input, output, password, account status, authority | HTTP filter đã áp dụng, session/cookie được lưu |
| MockMvc `httpBasic(...)` | Cách filter nhận credentials và provider xử lý request | Một flow form login hoặc token khác chắc chắn đúng |
| Test `hasRole("ADMIN")` | Authorization từ kết quả authentication | Account object thuộc đúng tenant |
| `@WithMockUser` / `user()` | Policy với Authentication giả lập | Username/password thật đi qua provider |
| Test CSRF riêng | Protection trên request thay đổi trạng thái | Role/permission chính xác nếu request bị CSRF chặn sớm |

Nếu chỉ kiểm tra method trả chuỗi trong controller, bạn có thể bỏ lỡ cấu hình Spring Security bị vô hiệu hóa. Bài test bảo mật nên có cả ca được phép, ca bị từ chối và, với nghiệp vụ có side effect, xác nhận database/queue không thay đổi khi request bị chặn.

### 10.2. Điểm cần cẩn trọng với kết quả tests

- Không assert `getCredentials()==null` với *mọi* loại Authentication: test này dành riêng cho `ProviderManager` + token username/password trong ví dụ.
- Không assert mọi provider luôn tạo instance Java mới: với thiết kế khác, provider có thể xử lý object khác. Test này mô tả hành vi của DaoAuthenticationProvider trong setup đã nêu.
- Không assert tất cả 403 đều do thiếu role: CSRF hoặc domain policy có thể gây 403.
- Không dùng `@WithMockUser` để chứng minh account disabled hoặc password hash đúng.
- Khi test method security, phải có `@EnableMethodSecurity` và lời gọi qua Spring bean/proxy phù hợp.
- Khi dùng role hierarchy hoặc prefix custom, thay assertions đúng chính sách thực.

## 11. Java 17 độc lập: mô phỏng input → manager → output

Nếu chưa có Spring Boot, chương trình sau dùng **JDK 17 thuần**, mô phỏng cùng một kiểu record mang hai trạng thái trước và sau xác thực. Mục tiêu là thấy rõ vì sao **không thể tin input**, vì sao caller phải dùng **return value**, và vì sao exception không được biến thành success.

**Lưu ý bắt buộc:** đây là mô hình học tập với chuỗi bí mật demo cố định và so sánh đơn giản; **không phải password authentication an toàn**. Trong ứng dụng thật, dùng AuthenticationManager/Provider, PasswordEncoder và kho danh tính được thiết kế đúng.

Tạo **`ManagerContractDemo.java`**:

```java
import java.util.List;

public class ManagerContractDemo {

    record AuthState(
        String principal,
        String credentials,
        List<String> authorities,
        boolean authenticated
    ) {}

    static final class AuthenticationFailed
            extends RuntimeException {
        AuthenticationFailed() {
            super("Authentication rejected");
        }
    }

    interface AuthManager {
        AuthState authenticate(AuthState request);
    }

    static final class DemoManager implements AuthManager {
        @Override
        public AuthState authenticate(AuthState request) {
            if (request == null
                    || !"alice".equals(request.principal())
                    || !"demo-secret".equals(request.credentials())) {
                throw new AuthenticationFailed();
            }

            return new AuthState(
                "alice",
                null,
                List.of("ROLE_USER", "report:read"),
                true
            );
        }
    }

    public static void main(String[] args) {
        AuthManager manager = new DemoManager();

        AuthState request = new AuthState(
            "alice", "demo-secret", List.of(), false
        );

        System.out.println(
            "request.authenticated=" + request.authenticated()
        );
        System.out.println(
            "request.authorities=" + request.authorities().size()
        );

        AuthState result = manager.authenticate(request);

        System.out.println(
            "result.principal=" + result.principal()
        );
        System.out.println(
            "result.authenticated=" + result.authenticated()
        );
        System.out.println(
            "result.authorities="
                + String.join(",", result.authorities())
        );
        System.out.println(
            "result.credentialsErased="
                + (result.credentials() == null)
        );

        try {
            manager.authenticate(new AuthState(
                "alice", "wrong", List.of(), false
            ));
        } catch (AuthenticationFailed ignored) {
            System.out.println("wrongPassword=rejected");
        }
    }
}
```

Biên dịch và chạy:

```bash
javac ManagerContractDemo.java
java ManagerContractDemo
```

**Stdout chính xác theo logic Java của chương trình:**

```text
request.authenticated=false
request.authorities=0
result.principal=alice
result.authenticated=true
result.authorities=ROLE_USER,report:read
result.credentialsErased=true
wrongPassword=rejected
```

Đọc kết quả:

1. Request biết username và credential nhưng **chưa authenticated**, authorities rỗng.
2. Manager (mô phỏng) kiểm tra bằng chứng, tạo **một object kết quả mới**, có authority đúng.
3. Caller dùng `result`; không giả định object `request` tự được đổi trạng thái.
4. Kết quả giả lập đã xóa credential nhưng vẫn có principal/authority.
5. Nếu credential sai, phương thức ném exception, không tạo Authentication thành công.
6. Chương trình không có `SecurityContextHolder`, session hay Spring filter; nó chỉ mô phỏng hợp đồng, không bảo vệ web thật.

Việc mô hình dùng `List<String>` thay cho `GrantedAuthority` là chủ ý để chạy không cần thư viện Spring. Trong ứng dụng thật, authorities là `Collection<? extends GrantedAuthority>`, và manager/provider xác thực với cơ chế bảo mật thích hợp.

## 12. Các kiểu Authentication khác nhau vẫn đi qua hợp đồng chung

`AuthenticationManager` không đồng nghĩa “username/password manager”. Các hệ thống có thể dùng:

| Cơ chế | Input Authentication | Provider phù hợp | Output dùng cho authorization |
| --- | --- | --- | --- |
| HTTP Basic | Thường `UsernamePasswordAuthenticationToken` chưa xác thực | `DaoAuthenticationProvider` hoặc provider username/password tương tự | Principal đã xác minh + roles/authorities |
| Form login | Thường `UsernamePasswordAuthenticationToken` | `DaoAuthenticationProvider` / custom provider | UserDetails/authorities, sau đó web login flow có thể lưu session |
| JWT resource server | Token Authentication thích hợp theo cơ chế | `JwtAuthenticationProvider` hoặc cơ chế converter/decoder tương ứng | `JwtAuthenticationToken` có principal/authorities từ JWT đã verify |
| OIDC/OAuth2 login | Các token phục vụ OAuth2/OIDC flow | Provider tương ứng | `OAuth2AuthenticationToken`/principal tùy cơ chế |
| Pre-authenticated proxy | Token pre-authentication | Provider tin cậy đúng ranh giới | Principal đã xác nhận từ cơ chế pre-auth |
| Custom credential | `Authentication` custom | `AuthenticationProvider` custom | Kết quả sau khi custom verification thành công |

**Không ép mọi input thành `UsernamePasswordAuthenticationToken`**. Với JWT, phải verify chữ ký, issuer, audience, thời hạn và nguồn tin cậy; với pre-auth, phải xác định cách ngăn header giả mạo; với custom provider, phải đảm bảo kết quả thật sự được xác minh.

### 12.1. Khi nhiều manager cùng tồn tại

Một ứng dụng có thể có manager global, manager local cho `SecurityFilterChain` hoặc parent manager. Một service inject `AuthenticationManager` không nhất thiết dùng **chính instance** mà mọi filter khác đang sử dụng nếu ứng dụng tự cấu hình nhiều manager.

Khi debug, xem:

- Bean `AuthenticationManager` nào được inject vào caller?
- `HttpSecurity.authenticationManager(...)` có được gán không?
- Mỗi chain có `@Order`, `securityMatcher` nào?
- Provider list và `supports` có nhận đúng token type không?
- Có parent manager được cấu hình không?
- Các authority mapping có nhất quán giữa password và token flow không?

Không đoán rằng “đã có một AuthenticationManager bean nên mọi loại token đều được chấp nhận”.

### 12.2. Direct authenticate không phải cấp access token

Một số code tự viết login có vẻ như:

```java
Authentication verified = manager.authenticate(request);
// return JWT nào đó?
```

`verified` chỉ là Authentication result. Nếu hệ thống muốn cấp token, cần **một quy trình phát hành token được thiết kế riêng**: xác định claims, scope/audience, thời hạn, khóa ký, refresh/revoke, storage và policy bảo vệ endpoint login. Spring Security Resource Server là thành phần **xác minh** access token của API; nó không tự biến mọi lời gọi `authenticate` thành một access token được phát hành.

## 13. Anti-patterns và cách sửa

### 13.1. Dùng getName() của token đầu vào làm identity thật

`request.getName()` trước xác thực có thể chỉ là username do client khai. Dùng nó để lấy dữ liệu nhạy cảm là sai. Phải chờ `authenticate` thành công và dùng principal đã xác minh từ result hoặc context do filter cung cấp.

### 13.2. Bỏ qua Authentication trả về

`manager.authenticate(request);` rồi dùng `request` như thể cờ authenticated và authorities đã được cập nhật là lỗi thường gặp. Provider có thể trả object khác. Phải giữ và sử dụng `Authentication verified = ...`.

### 13.3. Trả null hoặc authenticated=false rồi cho request đi tiếp

Trong contract của manager, xác thực thất bại phải được xử lý bằng exception phù hợp; một result chưa được xác minh không phải là login thành công. Caller không được tự chữa bằng cách set authenticated=true.

### 13.4. Tự tạo role từ request body

`new SimpleGrantedAuthority(clientSuppliedRole)` không biến dữ liệu client thành quyền đáng tin. Nguồn authority phải được provider/decoder/mapping kiểm soát, sau khi xác minh danh tính và nguồn token.

### 13.5. Tự làm HTTP status trong AuthenticationManager

Manager không có vai trò trả response HTTP 401/403/302. Filter, entry point, access-denied handler và framework web điều phối tương tác client. Giữ AuthenticationManager độc lập với HTTP cho phép tái sử dụng hợp đồng trong những luồng khác.

### 13.6. Dùng ProviderNotFoundException như lỗi password

`ProviderNotFoundException` thường cho biết không có provider nào hỗ trợ kiểu Authentication; kiểm tra provider list, `supports`, manager được inject và chain. Password sai trong luồng DAO thường là `BadCredentialsException`, không phải thiếu provider.

### 13.7. Log nguyên Authentication hoặc credentials

Một `Authentication` có thể chứa principal và dữ liệu xác thực nhạy cảm, đặc biệt ở input. Không log raw password, bearer token, session ID hoặc header `Authorization`. Nếu cần audit, ghi metadata tối thiểu như loại auth, principal ID đã được phép ghi, thời điểm và loại kết quả.

### 13.8. Giữ credentials quá lâu hoặc tắt erasure vô căn cứ

ProviderManager xóa credentials để giảm rủi ro lộ bí mật. Nếu cache có shared object, thiết kế lại cache/đối tượng trước khi tắt erasure. Không dựa vào erasure để thay TLS hoặc secret management.

### 13.9. Cho rằng authenticated=true đồng nghĩa được làm mọi việc

Authentication chỉ tạo danh tính và authorities; `hasRole`, `hasAuthority` và domain authorization còn phải đánh giá tài nguyên cụ thể. User hợp lệ vẫn có thể bị 403.

### 13.10. Tự quản lý SecurityContext sai vòng đời

Nếu gọi manager trong login controller tự viết và chỉ set context trên thread, request tiếp theo có thể không có login; session chưa được lưu đúng, CSRF/session fixation/logout chưa xử lý. Dùng integration được Spring Security hỗ trợ hoặc thiết kế đầy đủ vòng đời context/repository.

### 13.11. Dùng @WithMockUser để “chứng minh” authenticate thật

`@WithMockUser` tạo Authentication giả lập cho test authorization; nó bỏ qua password provider. Test xác thực phải gọi manager thật hoặc gửi HTTP Basic/form/token qua filter phù hợp.

### 13.12. Hiểu isAuthenticated() của anonymous sai

Một `AnonymousAuthenticationToken` có thể có `isAuthenticated()==true` ở mức object. Rule `authenticated()` của Spring Security có logic phân biệt anonymous; không tự thay bằng biểu thức `authentication != null && authentication.isAuthenticated()`.

### 13.13. Không tính đến thay đổi quyền

Session/token có thể giữ authorities chụp ở thời điểm login. Khi role bị thu hồi, Authentication đang tồn tại không tự cập nhật lập tức; cần refresh, revoke, TTL hoặc policy kiểm tra runtime tùy rủi ro.

### 13.14. Tạo nhiều provider mà không kiểm tra thứ tự

Một provider hỗ trợ cùng kiểu Authentication nhưng có logic khác có thể thay đổi kết quả khi đứng trước/sau. Kiểm tra thứ tự provider, contract khi trả null/exception và parent fallback bằng tests âm tính; không để cơ chế ít tin cậy vô tình chấp nhận request mà cơ chế mạnh hơn từ chối.

## 14. Checklist debug khi authenticate không trả kết quả như mong đợi

| Dấu hiệu | Kiểm tra trước tiên | Nhóm lỗi |
| --- | --- | --- |
| `BadCredentialsException` | Password, user lookup, encoder/hash và status account | Xác thực bị từ chối |
| `DisabledException` / `LockedException` | Trạng thái account trong user store | Quy tắc tài khoản |
| `ProviderNotFoundException` | Kiểu Authentication, provider `supports`, parent manager | Cấu hình manager/provider |
| Login thành công nhưng API sau vẫn 401 | Filter, context repository, session/token, cookie | Lưu/khôi phục identity |
| Login thành công nhưng API admin 403 | Authority, role prefix, authorization rule | Phân quyền |
| `getCredentials()==null` sau login | Erasure có đang hoạt động? | Bình thường trong nhiều provider |
| Principal là Jwt thay vì UserDetails | Cơ chế authentication hiện tại | Lựa chọn kiểu dữ liệu |
| Test @WithMockUser pass, password thật fail | Chưa test provider hoặc encoder | Phạm vi test |
| Password đúng nhưng tài khoản disabled | Kiểm tra trạng thái trước/khi xác thực | Account policy |
| POST login custom 403 | CSRF token, chain/method policy | Exploit protection |
| Service tự gọi authenticate nhưng context rỗng | Không set/persist context sau direct call | Lỗi vòng đời context |
| JWT signature đúng nhưng scope sai | Converter, issuer/audience, authority mapping | Token trust & authorization |

### 14.1. Trình tự chẩn đoán nhanh

1. Xác định đúng `SecurityFilterChain` và cơ chế đang chạy (HTTP Basic, form, token hoặc custom).
2. Kiểm tra token input được tạo với kiểu nào, `isAuthenticated` ban đầu, principal/credentials có mặt hay không; **không in credentials**.
3. Xác định `AuthenticationManager` instance được dùng, danh sách `AuthenticationProvider` và parent.
4. Kiểm tra provider phù hợp `supports` loại token đang nhận.
5. Kiểm tra user lookup, password encoder, token decoder và account status.
6. Khi thất bại, phân loại exception; không mặc định mọi lỗi thành `BadCredentialsException`.
7. Khi thành công, đọc **result**: principal type, authorities, `isAuthenticated` và chính sách credential erasure.
8. Kiểm tra filter đã lưu `SecurityContext` hay request tiếp theo phải mang lại token.
9. Khi bị 403, phân biệt authorization, CSRF và object policy.
10. Khi có quyền trên object, kiểm tra owner, tenant và trạng thái nghiệp vụ từ dữ liệu server.
11. Viết integration tests cho cả đường thành công lẫn âm tính.
12. Kiểm tra logs an toàn, không chia sẻ password/token.

### 14.2. Những câu hỏi nên tự hỏi khi đọc code người khác

- Ai tạo Authentication đầu vào, nguồn nào đang được coi là chưa tin?
- Manager/provider đã dùng thuật toán/nguồn kiểm chứng nào?
- Có callback/handler nào bắt exception và chuyển thành HTTP response?
- Result có khác request không và caller có giữ result không?
- Ai cấp authorities và có thể bị client giả mạo hay không?
- Sau xác thực ai giữ SecurityContext, ai lưu phiên/token?
- Quyền action/resource được đánh giá tại đâu?
- Khi user bị khóa hoặc quyền bị thu hồi, session/token hiện có sẽ xử lý thế nào?
- Một test thành công có thật sự đi qua AuthenticationManager hay chỉ dùng mock user?
- Nếu các cơ chế authentication cùng tồn tại, provider/chain có ranh giới đúng không?

## 15. Câu hỏi tự kiểm tra

**Câu 1.** Tại sao `AuthenticationManager.authenticate` nhận và trả cùng kiểu `Authentication`, trong khi hai object có mức tin cậy khác nhau?

**Câu 2.** Nếu request chứa username `alice` và password dạng chuỗi, tại sao không nên dùng `request.getName()` để xác định user thật trước khi gọi manager?

**Câu 3.** `ProviderManager` khác `DaoAuthenticationProvider` thế nào?

**Câu 4.** Khi provider không thể xử lý kiểu Authentication, vai trò của `supports`, `null` và `ProviderNotFoundException` là gì?

**Câu 5.** Password sai với provider username/password thường dẫn tới kết quả Java thế nào?

**Câu 6.** Vì sao `Authentication result = manager.authenticate(request)` tốt hơn việc bỏ qua giá trị trả về?

**Câu 7.** `result.getCredentials()==null` sau xác thực có nghĩa manager đã logout user không?

**Câu 8.** Sau khi direct call `authenticate` thành công từ một service, vì sao request HTTP tiếp theo có thể vẫn chưa đăng nhập?

**Câu 9.** Vai trò của `GrantedAuthority` trong Authentication result là gì? Nó có tự cho Alice xem mọi đơn hàng không?

**Câu 10.** HTTP Basic sai password trả 401, nhưng user đã xác thực thiếu ADMIN trả 403: hai lớp nào quyết định chúng?

**Câu 11.** Tại sao test `@WithMockUser` pass không chứng minh user store và `PasswordEncoder` hoạt động?

**Câu 12.** Nếu JWT từ client có claim `ROLE_ADMIN` nhưng chưa verify chữ ký/issuer/audience, có thể tạo Authentication authenticated từ claim đó không?

**Câu 13.** Khi dùng nhiều `SecurityFilterChain`, điều gì có thể khiến một AuthenticationManager khác được sử dụng so với manager inject trong service?

**Câu 14.** Nếu quyền admin bị thu hồi, vì sao Authentication hiện có trong session không nhất thiết tự mất authority ngay?

**Đáp án gợi ý**

1. Interface phục vụ cả yêu cầu và kết quả; trước provider là dữ liệu cần kiểm tra, sau provider là danh tính/quyền đã xác minh.
2. Username đầu vào do client khai, chưa có bằng chứng; nó có thể là bất kỳ chuỗi nào.
3. ProviderManager điều phối các provider; DaoAuthenticationProvider thực thi xác thực username/password qua UserDetailsService/PasswordEncoder.
4. `supports` xác định loại token provider hiểu; provider có thể trả null để nơi điều phối thử tiếp; thiếu provider xử lý có thể ra ProviderNotFoundException.
5. Ném AuthenticationException thích hợp, thường BadCredentialsException; không có kết quả xác thực thành công.
6. Provider có thể tạo Authentication result mới với principal/authorities/trạng thái khác.
7. Không. Credentials có thể được xóa để giảm rò rỉ; không phải logout.
8. Direct call không tự set và persist SecurityContext, không tự phát hành session cookie hay token.
9. Đó là quyền khái quát được gắn cho chủ thể; cần thêm policy trên owner/tenant/object.
10. Authentication/filter/entry point xử lý 401; authorization từ chối quyền gây 403 (trong trường hợp phù hợp).
11. Mock user giả lập context, không đưa password qua manager/provider thật.
12. Không. Claims phải đến từ token đã được verify theo trust policy trước khi ánh xạ quyền.
13. Cấu hình manager local, chain matcher/order, provider/parent hoặc bean injection khác nhau.
14. Session/token chứa thông tin quyền đã được tạo trước đó; cần chính sách refresh, revoke hoặc runtime check.

## 16. Tài liệu tham khảo chính thức

- [Spring Security 6.5 – Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html)
- [Spring Security 6.5 – DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html)
- [Spring Security 6.5 – Username/Password Authentication and AuthenticationManager bean](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/index.html)
- [Spring Security 6.5 – HTTP Basic Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/basic.html)
- [Spring Security – AuthenticationManager API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/AuthenticationManager.html)
- [Spring Security – ProviderManager API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/ProviderManager.html)
- [Spring Security 6.5 – Authorization Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/architecture.html)
- [Spring Security 6.5 – MockMvc Test](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/)
