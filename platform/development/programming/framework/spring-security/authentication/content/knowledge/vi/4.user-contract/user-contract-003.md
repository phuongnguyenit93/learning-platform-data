# UserDetailsManager và các thao tác quản lý tài khoản

**Ngữ cảnh:** Spring Security – authentication. **Nhóm kiến thức:** Hợp đồng người dùng.

## 1. UserDetailsManager giải quyết bài toán nào?

Trong Spring Security, một **tài khoản người dùng** có hai vòng đời liên quan nhưng khác nhau:

1. **Đọc danh tính để xác thực:** Khi người dùng đăng nhập bằng username/password, cơ chế xác thực cần tìm tài khoản, mật khẩu đã băm, trạng thái khóa/hết hạn và quyền. Đó là trách nhiệm của `UserDetailsService` qua `loadUserByUsername(String username)`.
2. **Quản lý dữ liệu tài khoản:** Khi đăng ký người dùng, đổi vai trò, khóa tài khoản, đổi mật khẩu hoặc xóa user, ứng dụng cần các thao tác ghi dữ liệu. `UserDetailsManager` mở rộng `UserDetailsService` để cung cấp hợp đồng cho các thao tác đó.

**Quan hệ kế thừa:**

~~~text
                  UserDetails
                     ^
                     | đối tượng chứa thông tin account
                     |
              UserDetailsService
              + loadUserByUsername(username)
                     ^
                     | extends
                     |
              UserDetailsManager
              + createUser(user)
              + updateUser(user)
              + deleteUser(username)
              + changePassword(oldPassword, newPassword)
              + userExists(username)
                     ^
          +----------+----------------------+
          |          |                      |
 InMemoryUserDetailsManager   JdbcUserDetailsManager   LdapUserDetailsManager
    bộ nhớ, demo/test             JDBC database            thư mục LDAP
~~~

`UserDetailsManager` nằm trong package `org.springframework.security.provisioning`. Nó là **interface**, không phải một REST controller hay API quản lý admin tự động. Spring Security không tự cung cấp cho client các endpoint tạo, xóa, nâng quyền chỉ vì bạn khai báo một bean có kiểu này.

Ví dụ hai câu hỏi khác nhau:

- “Mật khẩu của `linh` có hợp lệ không?” → `DaoAuthenticationProvider` gọi `UserDetailsService.loadUserByUsername(...)`, kết hợp `PasswordEncoder` kiểm tra credential rồi trả `Authentication`.
- “Administrator cần thêm tài khoản `linh` với quyền người đọc” → nghiệp vụ kiểm tra quyền administrator, tạo `UserDetails` chứa password hash và gọi `UserDetailsManager.createUser(...)`.

**Không đồng nhất account management với authentication.** Việc user được tạo thành công không đồng nghĩa user đã đăng nhập; ngược lại, user đã đăng nhập không mặc nhiên có quyền sửa tài khoản người khác.

## 2. Hợp đồng đầy đủ và ý nghĩa từng phương thức

`UserDetailsManager extends UserDetailsService` nên tổng cộng có một phương thức đọc kế thừa và năm phương thức quản lý:

| Phương thức | Chức năng | Đầu vào/chủ thể | Trả về |
| --- | --- | --- | --- |
| `loadUserByUsername(String username)` | Nạp tài khoản để phục vụ xác thực | Username cần tìm | `UserDetails` hoặc `UsernameNotFoundException` |
| `userExists(String username)` | Kiểm tra tài khoản có tồn tại theo chính sách tra cứu của implementation | Username | `boolean` |
| `createUser(UserDetails user)` | Tạo tài khoản mới | `UserDetails` đã được chuẩn bị hợp lệ | `void` |
| `updateUser(UserDetails user)` | Cập nhật dữ liệu tài khoản đã có | `UserDetails` với trạng thái mong muốn | `void` |
| `deleteUser(String username)` | Xóa user theo cơ chế lưu trữ của implementation | Username | `void` |
| `changePassword(String oldPassword, String newPassword)` | Đổi mật khẩu **của người dùng hiện tại** | Mật khẩu cũ, mật khẩu mới theo định dạng provider yêu cầu | `void` |

### Đọc đúng nghĩa của `changePassword`

Phương thức **không nhận username đích**. Implementation thường dựa trên `Authentication` hiện tại trong `SecurityContextHolder` để biết tài khoản nào đổi mật khẩu. `oldPassword` có thể được dùng để xác thực lại nếu một `AuthenticationManager` thích hợp được cấu hình; không được mặc định rằng mọi implementation **luôn** kiểm tra mật khẩu cũ. Khi lập trình luồng đổi mật khẩu, ứng dụng phải bảo đảm kiểm tra đủ yếu tố bảo mật.

`newPassword` trong các implementation điển hình như `InMemoryUserDetailsManager`/`JdbcUserDetailsManager` thường là **giá trị mật khẩu đã được mã hóa bằng PasswordEncoder theo định dạng lưu trữ**, không phải raw password để tự động băm. Kiểm tra hợp đồng và cấu hình cụ thể trước khi sử dụng. Mật khẩu mới do client gửi phải được kiểm tra chính sách và mã hóa ở tầng dịch vụ đáng tin trước khi truyền xuống nơi lưu.

### Đọc đúng nghĩa của `userExists`

`userExists("linh") == false` tại thời điểm gọi không tạo lời hứa rằng `createUser(...)` sau đó chắc chắn thành công: hai request có thể cùng kiểm tra rồi cùng tạo. Với kho dữ liệu bền vững, **unique constraint** tại storage cùng xử lý conflict/transaction mới quyết định tính duy nhất của username.

### Đọc đúng nghĩa của `updateUser`

`updateUser` có thể thay đổi password hash, authorities hoặc các cờ account tùy theo implementation. Nó không tự biết trường nào trong request là “chỉ muốn sửa”. Khi tạo `UserDetails` mới để update, phải giữ đúng các trường cần bảo toàn và không cho người dùng tự gán vai trò ADMIN.

## 3. UserDetails chứa dữ liệu gì?

`UserDetails` là giao diện mô tả dữ liệu cần thiết cho Spring Security kiểm tra đăng nhập và xây dựng danh tính:

| Thuộc tính/phương thức | Ý nghĩa và lưu ý |
| --- | --- |
| `getUsername()` | Login name / định danh mà `UserDetailsService` tra cứu |
| `getPassword()` | Mật khẩu **đã băm/mã hóa theo PasswordEncoder**, không phải chuỗi mật khẩu gốc |
| `getAuthorities()` | Các `GrantedAuthority` được **server quyết định** (ví dụ `ROLE_USER`, `ROLE_EDITOR`) |
| `isEnabled()` | Tài khoản còn được phép đăng nhập theo chính sách hay không |
| `isAccountNonLocked()` | Có đang bị khóa tài khoản hay không |
| `isAccountNonExpired()` | Tài khoản còn hiệu lực không |
| `isCredentialsNonExpired()` | Credentials còn hiệu lực không |

Với implementation `User` có sẵn, có thể tạo một object bất biến về cấu hình account bằng builder:

~~~java
PasswordEncoder encoder = new BCryptPasswordEncoder();

UserDetails account = User.withUsername("linh")
        .password(encoder.encode("example-secret-only"))
        .roles("USER") // tự ánh xạ thành ROLE_USER
        .disabled(false)
        .accountLocked(false)
        .build();
~~~

**Đây là đoạn minh họa cần import/dependency và không độc lập chạy một mình.** Những cờ boolean là đầu vào chính sách, không nên lẫn lộn với trạng thái đã đăng nhập của `Authentication`. Việc dựng một `UserDetails` hợp lệ không tự tạo session/token. Dữ liệu bên trong `UserDetails` cũng không phải mô hình nghiệp vụ đầy đủ của hồ sơ người dùng (địa chỉ, billing, thiết lập cá nhân…); các phần đó có thể nằm trong entity/service riêng.

**Role và authority:** `.roles("USER")` thêm tiền tố `ROLE_`; `.authorities("ROLE_USER", "document:read")` dùng chuỗi authority theo dạng đã khai báo. Không thêm tiền tố `ROLE_` hai lần khi dùng `roles(...)`. Phân quyền được thực thi bằng `AuthorizationManager`, `@PreAuthorize` hoặc cấu hình tương ứng sau xác thực.

## 4. Quy trình tạo tài khoản bằng createUser

Một quy trình đăng ký tài khoản có kiểm soát thường là:

~~~text
POST /signup hoặc /admin/users
      |
      v
Xác định actor và quyền tạo tài khoản
      |
      v
Validate username, password policy, thông tin tối thiểu
      |
      v
Kiểm tra dữ liệu nghiệp vụ + unique constraint tại storage
      |
      v
PasswordEncoder.encode(rawPassword)
      |
      v
Server ấn định quyền ban đầu (ví dụ ROLE_USER)
      |
      v
UserDetailsManager.createUser(validatedUserDetails)
      |
      v
Audit event + kích hoạt quy trình xác minh email nếu cần
~~~

**Trước khi gọi:**

- Quyết định rõ **ai được tạo user**. Tài khoản tự đăng ký thường chỉ được nhận quyền mặc định; việc tạo admin thuộc luồng riêng có kiểm soát.
- Chuẩn hóa username/email theo chính sách nghiệp vụ, nhưng không tự ý thay đổi case và Unicode nếu hệ thống nhận dạng tên phân biệt chúng. Cấu hình uniqueness đồng nhất với cách tra cứu user của implementation.
- Kiểm tra độ dài, password strength, chính sách chống reuse; đưa raw password vào `PasswordEncoder.encode(...)`, lưu hash. Không log raw password hay trả hash về client.
- Cập nhật cùng transaction nếu còn cần tạo hồ sơ nghiệp vụ, liên kết tenant, hoặc audit record trong database. Nếu phát sinh sự kiện ngoài transaction, dùng outbox/biện pháp retry phù hợp để tránh dữ liệu mồ côi.

Ví dụ hướng gọi:

~~~java
// Minh họa trong service đã được bảo vệ, không phải controller hoàn chỉnh.
UserDetails user = User.withUsername(inputUsername)
        .password(passwordEncoder.encode(rawPassword))
        .roles("USER")
        .build();

if (!userDetailsManager.userExists(user.getUsername())) {
    userDetailsManager.createUser(user);
}
~~~

Kiểm tra `userExists` ở đây chỉ giúp đưa thông báo dễ hiểu. **Không dùng nó thay unique constraint của database**; vẫn phải xử lý tình huống request khác tạo username trước. Nếu ứng dụng cần bảo vệ tránh dò tài khoản, phản hồi đăng ký/khôi phục phải cân nhắc thông báo không tiết lộ tài khoản tồn tại.

## 5. Cập nhật tài khoản bằng updateUser

`updateUser(UserDetails user)` thường được dùng khi thay đổi trạng thái tài khoản hoặc quyền. Khi dùng builder `User.withUserDetails(existing)`, có thể giữ phần dữ liệu đã có rồi thay các trường mong muốn:

~~~java
// Minh họa: admin đã được xác thực và được authorize trước khi chạy.
UserDetails existing =
        userDetailsManager.loadUserByUsername("linh");

UserDetails updated = User.withUserDetails(existing)
        .authorities("ROLE_USER", "ROLE_EDITOR")
        .build();

userDetailsManager.updateUser(updated);
~~~

**Nguy cơ phổ biến:** Bước “nhận object từ request rồi update nguyên bản” có thể làm mất authorities, thay password hash bằng plaintext, mở khóa tài khoản hoặc tự nâng quyền. Mọi trường nhạy cảm phải được chọn và quyết định từ chính sách server; đừng dùng auto-binding trực tiếp DTO/JSON thành `UserDetails` để cập nhật.

Với hệ thống có nhiều nguồn thông tin, có thể cần cập nhật **hồ sơ** bằng service domain, còn tài khoản và quyền cập nhật qua một abstraction phù hợp, thay vì nhồi mọi thay đổi vào `UserDetailsManager`. Chính sách nghiệp vụ như “không được xóa admin cuối cùng”, “không được tự nâng quyền” hoặc “cấm sửa role cao hơn role đang có” là trách nhiệm của service, không được giao phó cho interface quản lý user.

**Thay đổi role có hiệu lực khi nào?** Nếu hệ thống đang giữ `Authentication` trong HTTP session hoặc token, bản authorities cũ có thể còn tồn tại đến khi context/token được làm mới. Cần thiết kế cơ chế reload, session invalidation, token revocation/thời hạn ngắn hay reauthentication theo rủi ro. Chỉ gọi `updateUser` không bảo đảm mọi request đang hoạt động lập tức thấy role mới.

## 6. Xóa tài khoản bằng deleteUser

`deleteUser(username)` yêu cầu implementation xóa tài khoản theo cơ chế của nó, nhưng **không tự đảm bảo**:

- Xóa mọi record nghiệp vụ liên quan hoặc đáp ứng quy định lưu trữ;
- Kết thúc mọi session còn hiệu lực, thu hồi access/refresh token;
- Phát sự kiện audit hoặc thông báo vận hành;
- Giải phóng liên kết hồ sơ, quyền sở hữu tài nguyên, tenant hoặc group;
- Áp dụng chính sách **soft delete** hay giữ dữ liệu để khôi phục.

Ví dụ:

~~~java
// Chỉ gọi khi actor có quyền xóa và chính sách domain cho phép.
userDetailsManager.deleteUser("linh");
~~~

Trong hệ thống thực, **vô hiệu hóa tài khoản** (`enabled=false`) có thể là lựa chọn thích hợp hơn xóa vật lý để giữ lịch sử và đáp ứng nghiệp vụ; đó là quyết định ứng dụng. Khi xóa hoặc khóa user, cần xử lý cách các phiên đang hoạt động bị chặn tiếp tục truy cập. Kết quả/sai lệch khi xóa user không tồn tại phụ thuộc implementation; đừng giả định tất cả cùng là idempotent hay ném cùng ngoại lệ.

## 7. Đổi mật khẩu bằng changePassword – trọng tâm bảo mật

### 7.1. Không nhận username đích

Chữ ký:

~~~java
void changePassword(String oldPassword, String newPassword);
~~~

Không có tham số username. Với implementation chuẩn dựa vào security context, tài khoản đích là **người dùng đã được xác thực trong request hiện tại**. Điều đó phù hợp thao tác **tự đổi mật khẩu**. Luồng **admin reset mật khẩu của người khác** là nghiệp vụ riêng, cần quyền bổ sung và audit, không nên giả mạo context người dùng khác rồi gọi `changePassword`.

Một luồng self-service an toàn:

~~~text
Người dùng đã đăng nhập
      |
      v
Kiểm tra session, CSRF và chính sách step-up/MFA nếu cần
      |
      v
Nhận oldPassword + newPassword qua HTTPS
      |
      v
Reauthenticate oldPassword bằng AuthenticationManager
      |
      v
Validate newPassword, chống reuse theo chính sách
      |
      v
Hash newPassword bằng PasswordEncoder
      |
      v
UserDetailsManager.changePassword(old, encodedNew)
      |
      v
Audit + thông báo + xử lý session/token còn hiệu lực
~~~

**Không mặc định implementation luôn reauthenticate.** Chẳng hạn `InMemoryUserDetailsManager.changePassword` chỉ kiểm tra lại `oldPassword` khi đã cấu hình `AuthenticationManager` cho manager đó. Nếu không, implementation có thể cập nhật password của principal từ security context mà không kiểm tra mật khẩu cũ. Do đó ứng dụng cần **cấu hình AuthenticationManager phù hợp và/hoặc xác thực lại rõ ràng ở tầng service**, rồi mới thay đổi credentials.

**Giá trị `newPassword`:** Với các implementation này, bạn cần truyền **password hash** đã tạo bằng `PasswordEncoder.encode(rawNewPassword)`. Truyền plaintext rồi nghĩ manager tự hash sẽ khiến dữ liệu lưu sai định dạng và gây lỗi đăng nhập hoặc yếu bảo mật. Đừng tự viết SHA-256 trần thay password encoder chuyên dụng.

### 7.2. Đổi mật khẩu không tự giải quyết vòng đời phiên

Khi mật khẩu đã đổi, những session cũ, remember-me token hoặc API token phát hành trước đó có thể vẫn còn hiệu lực. Chính sách nên định rõ: logout các thiết bị khác, yêu cầu login lại, revoke refresh token, rút ngắn phiên, thông báo đổi mật khẩu và xử lý trường hợp tài khoản bị chiếm. Với JWT, không thể mặc định thu hồi ngay chỉ vì password hash trong database đổi.

### 7.3. Phân biệt updateUser với changePassword

| Tình huống | API phù hợp về mặt hợp đồng | Lưu ý |
| --- | --- | --- |
| Người dùng tự đổi mật khẩu có cung cấp password cũ | `changePassword(old, encodedNew)` | Kiểm chứng Authentication hiện tại và old password |
| Admin thay role hoặc khóa tài khoản | `updateUser(updatedDetails)` | Authorization cho actor và bảo toàn trường không đổi |
| Admin reset password của user khác | Service nghiệp vụ riêng; có thể cập nhật password hash sau xác minh quyền | Audit, thông báo, invalidate sessions; không giả mạo current user |
| Provider muốn nâng cấp hash sau login | `UserDetailsPasswordService.updatePassword(user, encodedPassword)` nếu dùng | Interface khác, mục đích khác với self-service changePassword |

`UserDetailsPasswordService` là API riêng cho việc cập nhật password hash (ví dụ nâng cấp thuật toán sau xác thực thành công); các implementation có thể hỗ trợ đồng thời. Không đánh đồng `updatePassword` với `changePassword` hoặc `updateUser`.

## 8. Các implementation thường gặp

| Implementation | Lưu trữ | Khi phù hợp | Giới hạn và lưu ý |
| --- | --- | --- | --- |
| `InMemoryUserDetailsManager` | Map trong bộ nhớ tiến trình | Demo, thử nghiệm, test, tài khoản mẫu tạm thời | Không bền vững khi restart, không chia sẻ giữa nhiều instance; không dùng làm hệ thống tài khoản chính |
| `JdbcUserDetailsManager` | Database qua JDBC/`DataSource` | Ứng dụng username/password dựa trên bảng tài khoản/authorities | Cần schema/query/transaction phù hợp; thay đổi group/authority có điều kiện |
| `LdapUserDetailsManager` | Dịch vụ thư mục LDAP | Môi trường tổ chức có danh tính trong LDAP | Cần cấu hình LDAP, cấu trúc directory, password policy/ACL và quyền ghi |

### InMemoryUserDetailsManager

- Cho phép tạo manager rỗng hoặc nhận các `UserDetails` ban đầu.
- Triển khai `UserDetailsService` lẫn các thao tác `UserDetailsManager`.
- Dữ liệu tồn tại trong một process; restart mất các cập nhật runtime.
- Phù hợp để kiểm thử logic CRUD và xác thực mà chưa cần database.

### JdbcUserDetailsManager

`JdbcUserDetailsManager` mở rộng `JdbcDaoImpl` và thực hiện quản lý user dựa trên bảng/queries của JDBC authentication. Với schema mặc định của Spring Security, cần các bảng user và authority tương ứng (`users`, `authorities`) và constraints phù hợp. Khi dùng schema riêng, phải cấu hình các câu SQL đọc/ghi đồng bộ với schema hiện có và database dialect.

**Quan trọng:** Nếu `enableAuthorities=false` trong cấu hình JDBC, thao tác create/update/delete sẽ không ghi/xóa authorities theo cách thông thường; thêm nữa, quyền trực tiếp và quyền qua group không phải lúc nào có thể phân biệt chỉ từ `UserDetails`. Với hệ thống phân quyền phức tạp, phải hiểu cách `JdbcUserDetailsManager` quản lý group và role trước khi sửa tài khoản. Dữ liệu profile/tenant vượt khỏi các bảng mặc định nên có domain service riêng.

**Mẫu bean Servlet/JDBC trong Spring Boot** (đoạn mã tích hợp, không độc lập chạy bằng `javac`):

~~~java
@Bean
UserDetailsManager userDetailsManager(DataSource dataSource) {
    return new JdbcUserDetailsManager(dataSource);
}

@Bean
PasswordEncoder passwordEncoder() {
    return new BCryptPasswordEncoder();
}
~~~

Đây chỉ là phần khai báo bean. Ứng dụng còn cần `DataSource`, bảng dữ liệu/SQL phù hợp, `SecurityFilterChain`, chính sách phân quyền endpoint quản lý tài khoản và việc encode password tại tầng service. Với Boot, dependency `spring-boot-starter-security` cùng JDBC starter/driver và phiên bản theo BOM sẽ cung cấp các thành phần liên quan.

### LdapUserDetailsManager

Dùng khi nguồn tài khoản là LDAP. Chỉ tạo instance không có nghĩa đã kết nối và được phép ghi thư mục. Cần địa chỉ LDAP, bind identity, search base, mapping thuộc tính, TLS, ACL, schema và chính sách đổi mật khẩu theo directory; thao tác `changePassword` có thể phụ thuộc chính sách máy chủ LDAP. Không áp dụng giả định “mật khẩu là cột password hash trong bảng JDBC” sang LDAP.

### Khi nào tự triển khai UserDetailsManager?

Ứng dụng có dữ liệu user riêng (JPA, REST identity service, multi-tenant) có thể viết adapter triển khai `UserDetailsManager` và `UserDetailsService` đúng contract. Ví dụ một `UserDetailsService` chỉ đọc có thể đủ cho login; nếu nghiệp vụ quản lý tài khoản phức tạp, một **application service** có quyền cập nhật entity trực tiếp cũng có thể phù hợp hơn việc ép mọi domain model vào một `UserDetailsManager`. Khi tự triển khai, cần rõ semantics từng method, transaction, bảo mật credential và cách nạp authorities.

## 9. Demo Java 17 chạy được: tạo, đọc, cập nhật, đổi mật khẩu và xóa

Ví dụ dưới đây chạy độc lập bằng Gradle với **Spring Security 6.5.11**, không yêu cầu Spring Boot, database hay web server. Demo cho thấy cả năm phương thức quản lý và cách `UserDetailsManager` đồng thời thực hiện `loadUserByUsername`. Mọi mật khẩu trong ví dụ chỉ phục vụ học tập và không được đưa vào sản phẩm.

### 9.1. Cấu trúc thư mục

~~~text
user-manager-demo/
├── build.gradle
└── src/main/java/demo/UserManagerDemo.java
~~~

**File `build.gradle`:**

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.security:spring-security-core:6.5.11'
    implementation 'org.springframework.security:spring-security-crypto:6.5.11'
}

application {
    mainClass = 'demo.UserManagerDemo'
}
~~~

**File `src/main/java/demo/UserManagerDemo.java`:**

~~~java
package demo;

import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;

public final class UserManagerDemo {

    public static void main(String[] args) {
        PasswordEncoder encoder = new BCryptPasswordEncoder();
        InMemoryUserDetailsManager users = new InMemoryUserDetailsManager();

        // 1. Kiểm tra và tạo tài khoản. Mật khẩu lưu là hash BCrypt.
        System.out.println("before.exists=" + users.userExists("linh"));

        UserDetails initial = User.withUsername("linh")
                .password(encoder.encode("demo-old-password"))
                .roles("USER")
                .build();
        users.createUser(initial);

        System.out.println("afterCreate.exists=" + users.userExists("linh"));

        // 2. Đọc lại bằng hợp đồng UserDetailsService.
        UserDetails loaded = users.loadUserByUsername("linh");
        boolean oldPasswordMatches = encoder.matches(
                "demo-old-password", loaded.getPassword());
        System.out.println("loaded.name=" + loaded.getUsername());
        System.out.println("loaded.passwordMatches=" + oldPasswordMatches);
        System.out.println("loaded.roleUser=" + loaded.getAuthorities().stream()
                .anyMatch(a -> "ROLE_USER".equals(a.getAuthority())));

        // 3. Cập nhật roles bằng UserDetails đáng tin, giữ password hash.
        UserDetails edited = User.withUserDetails(loaded)
                .authorities("ROLE_USER", "ROLE_EDITOR")
                .build();
        users.updateUser(edited);

        UserDetails afterUpdate = users.loadUserByUsername("linh");
        System.out.println("afterUpdate.roleEditor="
                + afterUpdate.getAuthorities().stream()
                .anyMatch(a -> "ROLE_EDITOR".equals(a.getAuthority())));

        // 4. Cấu hình manager để changePassword kiểm tra oldPassword.
        DaoAuthenticationProvider dao = new DaoAuthenticationProvider(users);
        dao.setPasswordEncoder(encoder);
        AuthenticationManager authManager = new ProviderManager(dao);
        users.setAuthenticationManager(authManager);

        Authentication verified = authManager.authenticate(
                UsernamePasswordAuthenticationToken.unauthenticated(
                        "linh", "demo-old-password"));

        // Demo giả lập SecurityContext của người dùng đã xác thực.
        SecurityContext context = SecurityContextHolder.createEmptyContext();
        context.setAuthentication(verified);
        SecurityContextHolder.setContext(context);

        try {
            users.changePassword(
                    "demo-old-password",
                    encoder.encode("demo-new-password"));
        } finally {
            SecurityContextHolder.clearContext();
        }

        String storedHash = users.loadUserByUsername("linh").getPassword();
        System.out.println("afterChange.newPasswordMatches="
                + encoder.matches("demo-new-password", storedHash));
        System.out.println("afterChange.oldPasswordMatches="
                + encoder.matches("demo-old-password", storedHash));

        // 5. Xóa account khỏi in-memory store.
        users.deleteUser("linh");
        System.out.println("afterDelete.exists=" + users.userExists("linh"));
    }
}
~~~

Từ thư mục `user-manager-demo`, dùng JDK 17+ và Gradle tương thích:

~~~bash
gradle -q run
~~~

Nếu có Gradle Wrapper, dùng `./gradlew -q run` (PowerShell trên Windows: `.\gradlew.bat -q run`). Lần đầu Gradle cần mạng để tải dependencies từ Maven Central.

**Kết quả do các lệnh `System.out.println` tạo ra** (không tính log của môi trường/Gradle nếu có):

~~~text
before.exists=false
afterCreate.exists=true
loaded.name=linh
loaded.passwordMatches=true
loaded.roleUser=true
afterUpdate.roleEditor=true
afterChange.newPasswordMatches=true
afterChange.oldPasswordMatches=false
afterDelete.exists=false
~~~

### 9.2. Phân tích kết quả

- `before.exists=false`: kho bộ nhớ bắt đầu trống.
- `afterCreate.exists=true`: `createUser` lưu `UserDetails`; không có login/session nào được tạo lúc này.
- `loaded.passwordMatches=true`: giá trị trong `getPassword()` là BCrypt hash, `PasswordEncoder.matches` dùng raw password để kiểm tra.
- `afterUpdate.roleEditor=true`: `updateUser` đã lưu authorities mới, do server quyết định.
- `users.setAuthenticationManager(authManager)`: ví dụ này **có cấu hình reauthentication**; không được bỏ bước đó rồi mặc định `changePassword` vẫn kiểm tra mật khẩu cũ.
- `SecurityContextHolder.setContext(context)`: mô phỏng người dùng đã đăng nhập để `changePassword` chọn đúng user hiện tại; ứng dụng Servlet thật được security filters quản lý ngữ cảnh theo request.
- `afterChange.newPasswordMatches=true`: password hash mới hợp lệ.
- `afterChange.oldPasswordMatches=false`: raw password cũ không còn khớp hash đang lưu.
- `afterDelete.exists=false`: account đã xóa khỏi kho in-memory; đây không phải bằng chứng mọi session/token bên ngoài đã bị thu hồi.

**Phạm vi demo:** Chương trình cố tình không có web controller, token/session backend, endpoint admin, database hoặc multi-user concurrency. Nó giải thích trực tiếp hợp đồng của manager, không phải template bảo mật cho sản phẩm.

## 10. Tích hợp UserDetailsManager vào Spring Security authentication

Dòng chảy điển hình khi hệ thống dùng username/password:

~~~text
                          +----------------------+
                          |  UserDetailsManager  |
                          |  read + manage users |
                          +-----------+----------+
                                      ^
                                      | implements UserDetailsService
                                      |
POST /login --> AuthenticationFilter --> AuthenticationManager
                                            |
                                            v
                                      DaoAuthenticationProvider
                                            |
                                            +--> loadUserByUsername(...)
                                            +--> PasswordEncoder.matches(...)
                                            +--> check account state
                                            |
                                            v
                                      authenticated Authentication
                                            |
                                            v
                                      SecurityContext
                                            |
                                            v
                                      Authorization check

/admin/users --> service có kiểm quyền --> createUser/updateUser/deleteUser
/me/password --> service đã reauthenticate --> changePassword
~~~

`DaoAuthenticationProvider` chỉ cần interface `UserDetailsService`. Vì `UserDetailsManager extends UserDetailsService`, cùng một implementation có thể phục vụ cả đọc user khi login và cập nhật account khi quản trị. Tuy nhiên, nó **không phải authentication manager**; `UserDetailsManager` không tự xác minh password trong `createUser` và không trả `Authentication` khi cập nhật user.

**Sử dụng bean từ service:** Trong Spring Boot, có thể inject `UserDetailsManager` vào service đăng ký/quản trị, đồng thời inject `UserDetailsService` (cũng chính là manager) vào `DaoAuthenticationProvider` tùy cấu hình. Khi có nhiều provider hoặc nguồn danh tính, phải bảo đảm provider xác thực đọc đúng kho dữ liệu được nghiệp vụ account cập nhật.

Ví dụ service quản trị ở mức thiết kế:

~~~java
// MÃ MINH HỌA BÊN TRONG SERVICE ĐÃ CẤU HÌNH DEPENDENCY/SECURITY.
// Kiểm tra quyền admin phải thực hiện ở controller/service boundary.
public void registerNormalUser(String username, String rawPassword) {
    UserDetails user = User.withUsername(username)
            .password(passwordEncoder.encode(rawPassword))
            .roles("USER") // role được ấn định phía server
            .build();

    // Storage phải bảo vệ unique username; xử lý race/conflict.
    userDetailsManager.createUser(user);
}
~~~

Đây là **method minh họa chưa độc lập biên dịch**, do `passwordEncoder` và `userDetailsManager` là dependencies của class service chưa được trình bày. Nó cho thấy ranh giới quan trọng: dữ liệu roles đến từ policy ứng dụng chứ không phải payload client.

## 11. Các lỗi hay gặp khi quản lý account

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Chỉ có `UserDetailsService` nhưng gọi `createUser` | Compile không thấy method quản lý | Chọn `UserDetailsManager`/service ghi dữ liệu phù hợp |
| Tưởng `UserDetailsManager` tự tạo REST API | Có thể bỏ qua thiết kế authorization | Tự viết API được bảo vệ và áp dụng policy |
| Lưu plaintext vào `User.withUsername(...).password(...)` | Lộ credential hoặc lỗi xác thực do hash không đúng | Dùng `PasswordEncoder.encode(...)` trước khi lưu |
| Dùng `User.withDefaultPasswordEncoder` cho production | Mã nguồn chứa raw password, nguy cơ lộ và cấu hình demo | Dùng PasswordEncoder bean và dữ liệu bí mật được cấp qua kênh bảo mật |
| Cho browser gửi danh sách `ROLE_ADMIN` rồi tạo user nguyên xi | Leo thang đặc quyền | Server quyết định role mặc định và quyền admin |
| Dùng `userExists` như lock đảm bảo unique | Race condition, tài khoản trùng | Unique constraint + transaction/handling conflict |
| Dùng `updateUser` với object dựng thiếu trường | Ghi đè password hash/role/account status | Nạp account hiện tại, thay trường có chủ đích, validate |
| Gọi `changePassword` khi không có current Authentication | Không xác định user hiện tại, có thể lỗi | Yêu cầu user đăng nhập và kiểm tra SecurityContext |
| Cho rằng `changePassword` luôn kiểm tra `oldPassword` | Người dùng có session bị chiếm có thể đổi mật khẩu mà không biết password cũ | Cấu hình reauthentication/step-up và kiểm thử implementation |
| Truyền `newPassword` dạng raw vào implementation cần hash | Lưu sai định dạng/đăng nhập thất bại | Encode ở service trước khi gọi |
| Tự đổi mật khẩu của user khác bằng cách sửa SecurityContext | Bỏ qua ranh giới danh tính và audit | Dùng admin reset flow riêng với authorization mạnh |
| Xóa user là mọi token/session lập tức vô hiệu | Session hoặc JWT cũ có thể vẫn dùng được | Thiết kế revocation, invalidate và revalidation |
| Đổi role rồi nghĩ user đang đăng nhập có quyền mới ngay | SecurityContext/token vẫn giữ quyền cũ | Refresh danh tính, thu hồi session/token hoặc điều chỉnh TTL |
| Dùng InMemory cho môi trường phân tán | Tài khoản khác nhau giữa các instance, mất khi restart | Dùng database/LDAP/IdP phù hợp |
| Gọi `updateUser` thay đổi quyền mà không audit | Không truy vết leo thang/thu hồi quyền | Log sự kiện an toàn, actor, target, thời gian và thay đổi |

**Đừng log password hash lẫn raw password.** Hash mạnh vẫn là dữ liệu nhạy cảm vì có thể bị tấn công offline. Khi debug, ghi username nội bộ được cho phép, loại thao tác, request ID và kết quả; tránh ghi credentials hoặc toàn bộ `UserDetails`.

## 12. Những điều cần quyết định khi làm hệ thống thật

### Authorization cho thao tác quản lý tài khoản

Trên `/admin/users`, yêu cầu role hoặc permission phù hợp, kiểm tra giới hạn tenant, ngăn tự nâng quyền và cấm vô hiệu hóa người quản trị cuối cùng nếu nghiệp vụ yêu cầu. Với `/me/password`, xác định người dùng hiện tại từ security context, xác thực lại password/MFA và CSRF nếu dùng cookie session. Mỗi thao tác có chính sách authorization khác nhau; `UserDetailsManager` không tự tạo các chính sách đó.

### Tính nhất quán khi ghi

Với JDBC, database có thể cần transaction cho việc tạo user và authorities, update nhiều bảng, xóa user/role và audit. Phải thiết kế lock/unique constraint, rollback và xử lý retry an toàn. Với LDAP, thao tác ghi chịu các giới hạn ACL và transaction semantics khác JDBC.

### Vòng đời tài khoản

Phải phân biệt **khóa tạm**, **disable**, **xóa**, **password reset** và **đổi mật khẩu có old password**. Đây là các hành động có tác động khác nhau đến UX, pháp lý lưu trữ, audit và session/token. `UserDetailsManager` là lớp thao tác dữ liệu, không định nghĩa toàn bộ policy vòng đời.

### Cập nhật danh tính đang hoạt động

Xác thực có thể lấy authorities vào `Authentication` khi login. Sau đó context trong session, token đã ký hoặc cache vẫn có thể giữ bản cũ. Thiết kế thay đổi quyền/khóa user phải tính đến thời điểm áp dụng trên các request đang chạy. Không giả định một dòng `updateUser(...)` có thể ngay lập tức vô hiệu JWT phát hành trước đó.

### Multi-tenant và username

`UserDetailsService.loadUserByUsername(String)` chỉ nhận một chuỗi username. Nếu hai tenant có cùng username, ứng dụng phải xác định rõ quy ước định danh toàn cục (ví dụ username scoped với tenant) hoặc adapter/service nhận được tenant context theo cách an toàn. Không để client tự chọn tenant tùy ý khi truy vấn tài khoản có quyền cao hơn.

## 13. Tự kiểm tra

**Câu 1:** Khác nhau quan trọng nhất giữa `UserDetailsService` và `UserDetailsManager`?  
**Trả lời:** Service định nghĩa tra cứu account để xác thực; Manager kế thừa service và thêm thao tác ghi/quản lý account.

**Câu 2:** `changePassword("old", "new")` tự đổi password của username nào?  
**Trả lời:** Tài khoản được lấy từ Authentication hiện tại theo contract của implementation, không có tham số username đích. Cần xác thực lại old password và encode new password đúng cách.

**Câu 3:** User gửi JSON `{"username":"linh","roles":["ADMIN"]}` để đăng ký. Có nên gọi `createUser` với roles từ JSON?  
**Trả lời:** Không. Server phải áp chính sách role mặc định; cấp ADMIN là thao tác khác có kiểm quyền.

**Câu 4:** `userExists(...)` trả false, sau đó `createUser(...)` có chắc không trùng không?  
**Trả lời:** Không; giữa hai lệnh có thể có request khác tạo account. Storage cần unique constraint và xử lý conflict.

**Câu 5:** `updateUser` đã bỏ `ROLE_ADMIN` nhưng session cũ vẫn chứa role này. Đó là lỗi gì?  
**Trả lời:** Cần quản lý lifecycle của `Authentication`/session/token và chiến lược cập nhật hoặc thu hồi quyền; thay đổi account record không tự sửa mọi identity đã cấp.

**Câu 6:** Chạy `InMemoryUserDetailsManager` trên ba instance có tạo kho chung không?  
**Trả lời:** Không. Mỗi process giữ map riêng; dữ liệu không đồng bộ và mất sau restart.

**Câu 7:** `deleteUser` có nghĩa xóa cả các bản ghi nghiệp vụ, lịch sử và mọi refresh token không?  
**Trả lời:** Không. Nó xử lý phần account theo implementation; phần còn lại cần service/transaction/revocation policy của ứng dụng.

## 14. Tài liệu chính thức

- [Spring Security 6.5 – UserDetailsManager API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/provisioning/UserDetailsManager.html): đầy đủ `createUser`, `updateUser`, `deleteUser`, `changePassword`, `userExists`, quan hệ kế thừa `UserDetailsService`.
- [Spring Security 6.5 – InMemoryUserDetailsManager](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/provisioning/InMemoryUserDetailsManager.html): storage trong bộ nhớ, constructors và các thao tác quản lý.
- [Spring Security 6.5 – JdbcUserDetailsManager](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/provisioning/JdbcUserDetailsManager.html): JDBC user/group management và các thuộc tính cấu hình.
- [Spring Security 6.5 – In-Memory Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/in-memory.html): cấu hình InMemory và giới hạn trong production.
- [Spring Security 6.5 – JDBC Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/jdbc.html): schema, `DataSource` và JdbcUserDetailsManager.
- [Spring Security 6.5 – Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html): `AuthenticationManager`, provider, `SecurityContext` và vòng đời xác thực.
- [OWASP – Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): quản lý tài khoản, password policy và kiểm soát rủi ro.

**Điều cần nhớ:** `UserDetailsManager` cho ứng dụng **hợp đồng quản lý tài khoản**; `UserDetailsService` nạp dữ liệu cho quá trình xác thực, còn `AuthenticationManager`/`AuthenticationProvider` kiểm chứng credential. Chính sách đăng ký, quyền quản trị, hash password, audit, transaction và thu hồi phiên vẫn phải được thiết kế ở tầng ứng dụng.
