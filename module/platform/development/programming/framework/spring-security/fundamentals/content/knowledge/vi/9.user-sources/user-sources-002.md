# UserDetails với username, password, authorities và trạng thái tài khoản

Khi Spring Security xác thực bằng username/password, hệ thống thường phải lấy thông tin tài khoản từ một nguồn đáng tin cậy: database, kho người dùng hoặc dịch vụ danh tính. **UserDetails** là hợp đồng mô tả những thông tin mà cơ chế xác thực cần biết về tài khoản: **username, password đã được lưu theo cơ chế an toàn, granted authorities và bốn trạng thái tài khoản**. Đây là một trong những kiểu quan trọng nhất để hiểu vì sao cùng một password đúng nhưng một người dùng đăng nhập thành công, người khác lại bị khóa hoặc hết hạn.

Bài thuộc nhóm **Nguồn người dùng** của Spring Security. Trọng tâm là cấu trúc UserDetails, ý nghĩa của mỗi phương thức, cách UserDetailsService cung cấp dữ liệu cho DaoAuthenticationProvider, và cách trạng thái account ảnh hưởng quá trình xác thực. Bài dùng **Java 17+, Spring Boot 3.3.6, Spring Security 6.x** cùng một demo có thể chạy bằng Maven và test MockMvc/JUnit. Các tài khoản, mật khẩu và dữ liệu đều là mẫu để chạy trên localhost, không dùng làm thiết kế lưu danh tính production.

## 1. Mô hình tư duy đúng: UserDetails là mô tả tài khoản cho security

Một user trong hệ thống nghiệp vụ có thể có hàng chục thuộc tính: ID, tên hiển thị, email, địa chỉ, tenant, ngày đăng ký, chính sách thanh toán, ngôn ngữ và lịch sử thay đổi. Spring Security không cần mang toàn bộ đối tượng ấy để kiểm password. Nó cần một **hợp đồng tập trung vào xác thực và quyền**.

~~~text
Database / identity store
  AccountRow:
    user_id, username, password_hash,
    enabled, locked, expires_at, password_expires_at,
    roles/permissions, tenant_id, ...
               |
               v
UserDetailsService.loadUserByUsername(username)
               |
               v
UserDetails:
  getUsername()
  getPassword()
  getAuthorities()
  isEnabled()
  isAccountNonLocked()
  isAccountNonExpired()
  isCredentialsNonExpired()
               |
               v
DaoAuthenticationProvider + PasswordEncoder
               |
               v
Authentication được xác thực hoặc AuthenticationException
               |
               v
Authorization ở HTTP/Service kiểm role, permission, resource
~~~

**UserDetails không tự đi kiểm mật khẩu, không tự tra database và không tự trả HTTP 401/403.** Nó là đối tượng chứa dữ liệu. UserDetailsService tìm và trả đối tượng đó; AuthenticationProvider thực thi kiểm chứng credential và trạng thái account; phần còn lại của Spring Security quyết định response và quyền truy cập.

Sự phân chia này giúp một database entity phục vụ nghiệp vụ, trong khi UserDetails chỉ tiết lộ dữ liệu tối thiểu cần để xử lý authentication. Khi cần thêm tenantId hoặc accountId cho nghiệp vụ, hãy thiết kế nguồn dữ liệu và lớp principal rõ ràng, không tự động đưa mọi trường nhạy cảm của entity vào SecurityContext.

## 2. Hợp đồng UserDetails gồm những phương thức nào?

Interface **org.springframework.security.core.userdetails.UserDetails** có các thành phần cốt lõi sau:

~~~java
// Mô tả chữ ký chính của UserDetails, không phải toàn bộ source framework.
public interface UserDetails extends java.io.Serializable {

    Collection<? extends GrantedAuthority> getAuthorities();

    String getPassword();

    String getUsername();

    boolean isAccountNonExpired();

    boolean isAccountNonLocked();

    boolean isCredentialsNonExpired();

    boolean isEnabled();
}
~~~

Từ Spring Security 6.x, một số phương thức boolean có thể có default implementation; **ý nghĩa hợp đồng vẫn cần được hiểu và override/cấu hình rõ khi sản phẩm có trạng thái tài khoản**. Mã phía trên là chữ ký rút gọn để học, không phải file nên sao chép thay cho interface gốc.

| Phương thức | Giá trị biểu diễn | Cách sử dụng |
| --- | --- | --- |
| **getUsername()** | Tên định danh dùng trong cơ chế username/password. | Xác định user cần tra cứu, làm Authentication.getName() khi phù hợp. |
| **getPassword()** | Thông tin password đã lưu, thông thường là **hash** theo PasswordEncoder. | DaoAuthenticationProvider/PasswordEncoder so khớp password được gửi với hash lưu. |
| **getAuthorities()** | Tập GrantedAuthority đại diện quyền đã cấp. | Xây Authentication; các rule hasRole/hasAuthority sử dụng về sau. |
| **isEnabled()** | true nếu tài khoản được kích hoạt. | false thường khiến provider từ chối xác thực. |
| **isAccountNonLocked()** | true nếu tài khoản **không bị khóa**. | false thường khiến provider ném LockedException. |
| **isAccountNonExpired()** | true nếu tài khoản **chưa hết hạn**. | false thường khiến provider ném AccountExpiredException. |
| **isCredentialsNonExpired()** | true nếu credential **chưa hết hạn**. | false thường khiến provider ném CredentialsExpiredException. |

**Quy tắc dễ nhớ:** Ba cờ có dạng **Non...** đều cần **true** khi bình thường. Riêng enabled cũng cần true. Đừng lẫn boolean của database kiểu locked=true với isAccountNonLocked=true. Khi ánh xạ từ entity sang UserDetails phải đổi dấu đúng:

~~~java
// Ví dụ khi database lưu locked = true nghĩa là đang bị khóa.
boolean accountNonLocked = !databaseUser.isLocked();
~~~

Một lỗi dấu phủ định sẽ tạo ra hành vi nguy hiểm: tài khoản đáng lẽ bị khóa lại được coi là hợp lệ hoặc ngược lại. Hãy có test cho cả hai trạng thái.

## 3. Username: tên định danh của một tài khoản

**getUsername()** trả username mà cơ chế xác thực sử dụng. Trong Spring Security, kiểu trả về là **String**; ý nghĩa thực tế có thể là login name, email đã chuẩn hóa hoặc một ID có thể đăng nhập tùy thiết kế.

Ví dụ:

~~~text
username trong kho tài khoản: "alice"
UserDetails.getUsername(): "alice"
Authentication.getName(): "alice" (theo cơ chế principal thông thường)
~~~

**Username không nhất thiết là ID nội bộ bất biến.** Nhiều hệ thống cho phép đổi email hoặc login name, trong khi khóa chính của user trong database không đổi. Nếu cần kiểm owner hoặc tenant, nên dựa trên định danh nội bộ đáng tin cậy đã ánh xạ qua principal/service thay vì so trực tiếp một email có thể đổi với ownerId.

### 3.1. Username phải có quy tắc chuẩn hóa rõ

Những điểm dễ sai:

- **Case sensitivity:** ALICE và alice có phải một tài khoản không? Quyết định theo datastore và business rule, không tự chuyển lowercase ở một nơi rồi quên nơi khác.
- **Unicode normalization:** các chuỗi nhìn giống nhau có thể có biểu diễn Unicode khác nhau; hệ thống cần quy tắc lưu/tra nhất quán.
- **Uniqueness:** username cần unique trong phạm vi định danh được thiết kế; ở hệ thống đa tenant có thể cần tenantId + username.
- **Account enumeration:** thông báo lỗi khác nhau giữa “username không tồn tại” và “mật khẩu sai” có thể làm lộ danh sách tài khoản.
- **Lookup key:** không dùng username client gửi để bỏ qua việc xác minh credential; username là thông tin tra cứu, không phải bằng chứng người gọi là chủ tài khoản.

Trong demo, username được dùng theo chuỗi chính xác và chỉ có vài tài khoản mẫu. Ứng dụng thật cần chuẩn hóa, uniqueness constraint và chính sách chống enumeration ngay ở tầng nguồn danh tính.

### 3.2. Nếu đăng nhập bằng email thì getUsername() là gì?

Có thể thiết kế UserDetailsService nhận email làm tên đăng nhập và trả UserDetails có getUsername() là email đã chuẩn hóa. Cũng có thể dùng một định danh riêng cho principal trong Authentication sau xác thực. Điều cần nhất quán là **cơ chế tra user, danh tính trả về và policy liên kết dữ liệu**.

Không dùng query parameter userId trên endpoint /api/me để quyết định current user. Lấy principal từ Authentication/SecurityContext đã được hệ thống xác thực.

## 4. Password: hash được lưu, không phải mật khẩu thô

**getPassword() thường trả password hash đã được lưu**, không phải password người dùng vừa nhập. Khi dùng DaoAuthenticationProvider:

~~~text
Client gửi password (sensitive)
         |
         v
Authentication filter tạo token chứa raw password tạm thời
         |
         v
DaoAuthenticationProvider
         |--> UserDetailsService.loadUserByUsername(username)
         |--> UserDetails.getPassword()  // encoded hash đã lưu
         |--> PasswordEncoder.matches(raw, storedHash)
         |
         +--> Đúng và trạng thái hợp lệ: Authentication thành công
         +--> Sai: AuthenticationException
~~~

Các nguyên tắc:

1. Không lưu plain text password.
2. Không chỉ dùng Base64, SHA-256 không salt hoặc một hash nhanh làm password storage theo kiểu tự chế.
3. Dùng PasswordEncoder phù hợp như BCryptPasswordEncoder hoặc DelegatingPasswordEncoder với cấu hình hash an toàn.
4. **encode()** tạo hash khi đăng ký/đổi mật khẩu; **matches(raw, encoded)** dùng lúc đăng nhập.
5. Không tự so sánh encoded hash bằng phép equals với raw password.
6. Không hash lại password khi chỉ đang **tra cứu UserDetails**: getPassword() phải trả **hash đã lưu**, không tạo hash mới từ một giá trị “mật khẩu thật” để đối chiếu.
7. Không đưa password hash, raw password, API key, recovery code vào response JSON, exception message hoặc log.
8. Khi đổi thuật toán/work factor, thiết kế migration/rehash theo chính sách và kiểm tra khả năng tương thích với hash cũ.

### 4.1. BCrypt được dùng ra sao?

~~~java
PasswordEncoder encoder = new BCryptPasswordEncoder();

String storedHash = encoder.encode("demo-pass");

boolean correct = encoder.matches("demo-pass", storedHash);
boolean incorrect = encoder.matches("wrong", storedHash);
~~~

**Output logic đáng tin:**

~~~text
correct = true
incorrect = false
~~~

Chuỗi storedHash mỗi lần chạy có thể khác nhau vì salt. Không đưa một hash cụ thể vào tài liệu rồi xem là output bắt buộc. Trong code ví dụ, password giả chỉ phục vụ localhost; không commit hoặc in secret thật ra log/console.

Một ví dụ Java 17 độc lập để chạy ngay (không cần Spring) nhằm minh họa vì sao cùng một giá trị đầu vào có thể được xử lý theo salt:

~~~java
// File: HashDemo.java. Mô phỏng hash có salt chỉ để giải thích khái niệm,
// KHÔNG phải thuật toán lưu password production.
public class HashDemo {
    public static void main(String[] args) {
        String raw = "demo-pass";
        String stored = "salt-A:" + raw.hashCode();

        System.out.println("raw=" + raw);
        System.out.println("storedIsRaw=" + stored.equals(raw));
    }
}
~~~

Chạy bằng:

~~~bash
javac HashDemo.java
java HashDemo
~~~

Output xác định:

~~~text
raw=demo-pass
storedIsRaw=false
~~~

Mã HashDemo trên là **minh họa phân biệt hai chuỗi**, tuyệt đối không dùng hashCode() để lưu password thật. Ví dụ Spring Boot ở phần thực hành dùng BCryptPasswordEncoder đúng công cụ.

## 5. Authorities: UserDetails mang những quyền gì?

**getAuthorities()** trả một tập **GrantedAuthority**; thường được biểu diễn bằng **SimpleGrantedAuthority** với một String:

~~~java
// Mảnh code Java trong nơi đã import Spring Security Core.
List<GrantedAuthority> permissions = List.of(
    new SimpleGrantedAuthority("ROLE_USER"),
    new SimpleGrantedAuthority("orders:read")
);
~~~

Các authority được đưa vào Authentication sau xác thực. Spring Security sử dụng chúng để áp dụng các biểu thức như:

~~~java
// Mảnh biểu thức trong SecurityFilterChain:
.hasRole("USER")                   // thường kiểm authority "ROLE_USER"
.hasAuthority("orders:read")       // kiểm chính xác chuỗi "orders:read"
.hasAuthority("SCOPE_orders.read") // kiểm authority từ OAuth scope nếu có
~~~

**Role, permission và scope không tự tương đương.** Ví dụ ROLE_USER không tự có orders:read; authority SCOPE_orders.read không tự tạo bởi UserDetails thường, trừ khi hệ thống cấp/mapping có chủ đích. Đừng cấp ROLE_ADMIN dựa trên một header X-Role hoặc JWT payload chưa được xác minh.

### 5.1. Spring Security User builder: roles và authorities

Với lớp có sẵn **org.springframework.security.core.userdetails.User**, có thể viết:

~~~java
UserDetails alice = User.withUsername("alice")
    .password(encodedPassword)
    .roles("USER")
    .build();
~~~

roles("USER") thêm authority **ROLE_USER** theo prefix thông dụng. Khi muốn thêm cả permission tùy biến:

~~~java
UserDetails alice = User.withUsername("alice")
    .password(encodedPassword)
    .authorities("ROLE_USER", "orders:read")
    .build();
~~~

**Không giả định .roles(...).authorities(...) luôn cộng dồn**: builder có thể thay thế danh sách đã đặt tùy cách gọi; để rõ ràng, ví dụ này dùng **một lệnh authorities(...)** chứa toàn bộ chuỗi cần cấp.

### 5.2. Không suy ra quyền từ tên tài khoản

Một tài khoản có username admin không tự có ROLE_ADMIN. Một user có email thuộc domain công ty cũng không tự có quyền nhân viên, trừ khi hệ thống có quy tắc xác minh nguồn đáng tin và chính sách cấp quyền rõ ràng. Kiểm **Authentication.getAuthorities()** là cách đánh giá quyền ở Spring Security, sau đó vẫn phải xét owner/tenant/resource policy.

### 5.3. Tránh trả authorities ra ngoài nếu không có mục đích

Trong bài học, endpoint /api/me có thể trả username và danh sách authority mẫu để quan sát. Trong ứng dụng thật, chỉ lộ những thông tin cần cho UI và nghiệp vụ; quyền nhạy cảm hoặc chi tiết nội bộ nên được xử lý phía server.

## 6. Bốn trạng thái tài khoản: ý nghĩa và cách diễn giải

Spring Security dùng các cờ UserDetails để báo account có thể xác thực bằng cơ chế tương ứng hay không.

| isEnabled | isAccountNonLocked | isAccountNonExpired | isCredentialsNonExpired | Diễn giải |
| --- | --- | --- | --- | --- |
| true | true | true | true | Tài khoản bình thường theo bốn cờ. |
| false | true | true | true | Tài khoản bị vô hiệu hóa/chưa được kích hoạt. |
| true | false | true | true | Tài khoản bị khóa. |
| true | true | false | true | Tài khoản đã hết hạn sử dụng. |
| true | true | true | false | Credential đã hết hạn, có thể cần đổi mật khẩu. |
| false | false | false | false | Nhiều điều kiện từ chối đồng thời; exception cụ thể phụ thuộc thứ tự check. |

**True ở ba cờ Non... là tốt**, **false là trạng thái bị từ chối**. Chú ý phần phủ định trong tên hàm. Đọc nhanh isAccountNonLocked() như “tài khoản không bị khóa” sẽ tránh lỗi đảo boolean.

### 6.1. isEnabled(): tài khoản có được kích hoạt không?

Các trường hợp nghiệp vụ có thể khiến enabled=false:

- Chưa xác minh email hoặc chưa hoàn tất bước onboarding bắt buộc.
- Tài khoản bị vô hiệu hóa bởi bộ phận quản trị.
- Tài khoản đã ngừng hoạt động và chính sách yêu cầu chặn đăng nhập.
- Một trạng thái cấm truy cập được xác nhận theo quy trình.

Không tự suy đoán rằng enabled=false có nghĩa “email chưa xác minh”; đó là ý nghĩa do sản phẩm đặt ra. Spring Security chủ yếu biết **boolean**, không biết toàn bộ lifecycle của tài khoản. Nếu cần phân biệt lý do, lưu thông tin ở domain model và áp dụng chính sách response an toàn.

DaoAuthenticationProvider có thể phát sinh **DisabledException** khi tài khoản không enabled. Một endpoint HTTP Basic thường chuyển lỗi xác thực thành 401; không nên phơi lý do chi tiết cho người dùng chưa xác thực.

### 6.2. isAccountNonLocked(): tài khoản có bị khóa không?

Nếu **isAccountNonLocked() = false**, DaoAuthenticationProvider thường dùng **LockedException**.

Cần phân biệt hai thứ:

- **Trạng thái khóa đã lưu**: UserDetails báo locked.
- **Cơ chế tự khóa sau N lần sai mật khẩu**: hệ thống phải tự thiết kế đếm lần thất bại, rate limiting, lockout policy và cập nhật nguồn danh tính.

Spring Security **không mặc định tạo một hệ thống khóa tài khoản sau 5 lần sai** chỉ vì UserDetails có phương thức isAccountNonLocked(). Nếu muốn tính năng này, cần thiết kế xử lý concurrency, reset counter, chống brute-force, audit và quy trình mở khóa; đừng tin counter từ request client.

Trong thiết kế bảo mật, khóa vô thời hạn có thể bị lợi dụng để gây từ chối dịch vụ đối với tài khoản người khác. Tùy sản phẩm có thể chọn rate limit, trì hoãn, kiểm tra bổ sung hoặc khóa tạm thời với kênh phục hồi.

### 6.3. isAccountNonExpired(): tài khoản đã hết hạn chưa?

Nếu **isAccountNonExpired() = false**, provider có thể ném **AccountExpiredException**. Ví dụ một tài khoản hợp đồng thời vụ bị hết hiệu lực sau ngày kết thúc.

Cờ này không tự biết current time hoặc expiration date. **UserDetailsService phải tính cờ từ dữ liệu đáng tin** khi tạo UserDetails, hoặc lấy trạng thái do hệ thống identity quyết định. Trong ứng dụng thật, cần xác định timezone, ranh giới thời điểm và thời gian của nguồn dữ liệu để tránh lỗi hết hạn sớm/muộn.

Nếu entity có expiryTimestamp, ví dụ:

~~~java
// Mảnh minh họa: expiresAt thuộc kiểu java.time.Instant.
boolean nonExpired =
    expiresAt == null || expiresAt.isAfter(Instant.now());
~~~

Dấu > có nghĩa tài khoản được coi hết hạn **tại hoặc sau** thời điểm expiresAt. Đây là một lựa chọn chính sách; cần ghi rõ kỳ vọng và test ranh giới, không để ngữ nghĩa phụ thuộc timezone mặc định của server.

### 6.4. isCredentialsNonExpired(): mật khẩu/credential còn hạn không?

Nếu **isCredentialsNonExpired() = false**, provider có thể ném **CredentialsExpiredException**. Một ứng dụng có thể dùng cờ này khi password cần thay đổi theo chính sách hoặc đã bị thu hồi.

**Account expired** và **credentials expired** khác nhau:

- Account expired: danh tính/tài khoản không còn được phép sử dụng trong mô hình tương ứng.
- Credentials expired: chính credential dùng cho xác thực đã hết hiệu lực; account có thể vẫn còn tồn tại và có cơ chế khôi phục/đổi mật khẩu khác.

Khi password hết hạn, không dùng endpoint API bảo vệ bởi cùng password hết hạn để thực hiện “đổi password” mà không thiết kế luồng xác minh phù hợp: người dùng có thể không đăng nhập được. Cần thiết kế flow recovery/reset hoặc một cơ chế xác minh bổ sung đủ tin cậy.

### 6.5. Khi nhiều trạng thái cùng sai thì sao?

**Thứ tự kiểm của provider ảnh hưởng exception được ném trước.** Trong luồng DaoAuthenticationProvider/AbstractUserDetailsAuthenticationProvider thông dụng, các kiểm tra pre-authentication như locked, disabled, account expired xảy ra trước kiểm password; credentials expired thường là post-authentication check. Đừng phụ thuộc vào thứ tự hiển thị lỗi này làm hợp đồng public API, vì framework có thể thay đổi và ứng dụng có custom provider/checker.

Ví dụ tài khoản vừa locked vừa disabled có thể bị báo khóa trước nếu checker ưu tiên locked. Bảo vệ thông tin account bằng thông báo lỗi công khai tổng quát, trong khi log nội bộ chỉ giữ mã nguyên nhân đủ cần thiết và không lộ credential.

## 7. UserDetailsService trả UserDetails, nhưng không xác thực password

**UserDetailsService** là interface để tải UserDetails:

~~~java
// Chữ ký mô tả interface của Spring Security.
UserDetails loadUserByUsername(String username)
        throws UsernameNotFoundException;
~~~

**Nhiệm vụ chính:** tìm tài khoản theo username và trả đúng UserDetails với password hash, authorities và trạng thái.

Nó **không tự thực hiện PasswordEncoder.matches(...)**, không tự quyết định HTTP response và không phải AuthenticationManager.

Một request được xử lý điển hình như sau:

~~~mermaid
flowchart TD
    A["HTTP Basic: username + password"] --> B["BasicAuthenticationFilter"]
    B --> C["UsernamePasswordAuthenticationToken chưa xác thực"]
    C --> D["ProviderManager"]
    D --> E["DaoAuthenticationProvider"]
    E --> F["UserDetailsService.loadUserByUsername"]
    F --> G["UserDetails: username / hash / authorities / flags"]
    G --> H["Account checks + PasswordEncoder.matches"]
    H --> I{"Hợp lệ?"}
    I -- "Có" --> J["Authentication được xác thực"]
    I -- "Không" --> K["AuthenticationException"]
    J --> L["Authorization + Controller"]
    K --> M["AuthenticationEntryPoint: thường 401"]
~~~

Trong code hoàn chỉnh, DaoAuthenticationProvider đã biết UserDetailsService và PasswordEncoder được cấu hình, nên nó gọi loadUserByUsername đúng lúc.

### 7.1. Khi user không tồn tại

UserDetailsService nên ném **UsernameNotFoundException** khi không tìm thấy; không trả null hoặc một user giả có quyền cao:

~~~java
@Override
public UserDetails loadUserByUsername(String username) {
    UserDetails user = repositoryFindByUsername(username);
    if (user == null) {
        throw new UsernameNotFoundException("Account not found");
    }
    return user;
}
~~~

Đây là **mảnh code minh họa**; repositoryFindByUsername cần một implementation thật, không tự chạy độc lập. Trong DaoAuthenticationProvider, theo cấu hình mặc định phổ biến, thông tin không tìm thấy user có thể được **ẩn thành BadCredentialsException** để giảm khả năng liệt kê tài khoản qua lỗi xác thực. Vì vậy:

- Gọi UserDetailsService trực tiếp: có thể thấy UsernameNotFoundException.
- Gọi AuthenticationManager với username không tồn tại: có thể nhận BadCredentialsException.
- Gọi API HTTP Basic: thường nhận 401 mà không phân biệt rõ tài khoản tồn tại hay không.

Không lấy thông điệp của exception rồi trả nguyên văn ra API cho client chưa xác thực.

### 7.2. Nếu username theo tenant thì sao?

Phương thức loadUserByUsername(String) chỉ có tham số username. Một hệ thống đa tenant có thể cần:

- Quy tắc username unique toàn hệ thống, hoặc
- Một cơ chế đáng tin xác định tenant trong authentication request/context rồi tra đúng miền danh tính, hoặc
- AuthenticationProvider chuyên biệt với token chứa tenant được kiểm chứng.

Không dùng header X-Tenant do client tự chọn để biến cùng một username thành quyền của tenant khác. Với multi-tenant login cần kiểm chứng tenant routing, nguồn cấp quyền và scope của Authentication rõ ràng.

### 7.3. UserDetailsManager là gì?

**UserDetailsManager** mở rộng UserDetailsService với một số thao tác quản lý tài khoản như tạo, cập nhật, xóa user và thay đổi password theo implementation.

Một số implementation thường gặp:

- **InMemoryUserDetailsManager**: thích hợp demo/test hoặc cấu hình rất nhỏ.
- **JdbcUserDetailsManager**: hỗ trợ mô hình schema JDBC tiêu chuẩn của Spring Security, cần kiểm database schema và quyền kết nối.
- **Custom UserDetailsService**: đọc từ bảng user/role/permission của ứng dụng.
- **ReactiveUserDetailsService**: dành cho WebFlux/reactive, trả Mono<UserDetails>; không thể bê nguyên interface đồng bộ vào pipeline reactive và cho rằng I/O tự nonblocking.

Một UserDetailsService chỉ làm lookup không tự trở thành CRUD manager. Phân biệt trách nhiệm đọc tài khoản và trách nhiệm thay đổi quyền/mật khẩu.

## 8. Spring Security cung cấp sẵn class User và UserBuilder

Bạn **không phải tự implement UserDetails** cho mọi dự án. Lớp **org.springframework.security.core.userdetails.User** đã implement UserDetails và có builder thuận tiện:

~~~java
UserDetails user = User.withUsername("alice")
    .password(encodedPassword)
    .authorities("ROLE_USER", "orders:read")
    .disabled(false)
    .accountLocked(false)
    .accountExpired(false)
    .credentialsExpired(false)
    .build();
~~~

Ở đây các setter của builder dùng dạng **tiêu cực**:

- disabled(false) tương ứng isEnabled() = true.
- accountLocked(false) tương ứng isAccountNonLocked() = true.
- accountExpired(false) tương ứng isAccountNonExpired() = true.
- credentialsExpired(false) tương ứng isCredentialsNonExpired() = true.

Cần phân biệt tên builder với tên UserDetails: **builder.accountLocked(true)** có nghĩa UserDetails.isAccountNonLocked() trả false.

### 8.1. Khi nào nên tự viết UserDetails?

Có thể tự implement UserDetails khi cần đưa một định danh nội bộ vào principal, ví dụ:

- accountId ổn định;
- tenantId đã được xác minh;
- loại principal phân biệt user và service identity;
- username và display name có vòng đời khác nhau.

Nhưng không nên đưa toàn bộ database entity mutable, chứa payment data hoặc PII vào Authentication. Với class riêng, phải đảm bảo các getter, authorities, flags, equals/hashCode khi cần, khả năng serialize an toàn và hành vi xóa credentials nếu object chứa thông tin nhạy cảm.

Ví dụ rút gọn về mapping boolean trong class tự triển khai (không phải file đầy đủ):

~~~java
@Override
public boolean isAccountNonLocked() {
    return !account.isLocked();
}

@Override
public boolean isEnabled() {
    return account.isEnabled();
}

@Override
public boolean isCredentialsNonExpired() {
    return account.getPasswordExpiresAt() == null ||
        account.getPasswordExpiresAt().isAfter(Instant.now());
}
~~~

Các đoạn này giả định account và Instant đã tồn tại/được import. Với sản phẩm, cần cân nhắc việc tính trạng thái tại thời điểm lookup và thời gian sống của Authentication/session/token.

## 9. Dự án chạy được: UserDetails với đủ bốn trạng thái

Demo xây dựng một nguồn tài khoản in-memory giống bảng database, ánh xạ thành UserDetails và dùng DaoAuthenticationProvider. Mỗi lần lookup trả **một đối tượng UserDetails mới** để tránh dùng chung principal mutable với dữ liệu được cache; hàng account mẫu giữ riêng password hash và flags.

Các endpoint:

- **GET /api/public**: cho phép ẩn danh.
- **GET /api/me**: bắt buộc xác thực thành công, trả username và authorities mẫu.
- **GET /api/ops**: bắt buộc ROLE_OPS.

Các tài khoản được cung cấp:

| Username | Password demo | Authorities | Trạng thái |
| --- | --- | --- | --- |
| alice | demo-pass | ROLE_USER, orders:read | Hoạt động. |
| ops | demo-pass | ROLE_OPS, orders:read | Hoạt động, được vào /api/ops. |
| locked | demo-pass | ROLE_USER | Account bị khóa. |
| disabled | demo-pass | ROLE_USER | Account bị vô hiệu hóa. |
| expired | demo-pass | ROLE_USER | Account đã hết hạn. |
| password-expired | demo-pass | ROLE_USER | Credential đã hết hạn. |

**Đây là ví dụ học tập**, không phải danh sách account production. Các password thật phải được quản lý và thay đổi an toàn; demo này không cung cấp luồng đăng ký/đổi mật khẩu/MFA.

### 9.1. Yêu cầu và cấu trúc thư mục

- JDK 17+.
- Maven 3.9+ hoặc Maven Wrapper.
- Cổng 8080 còn trống.
- curl/curl.exe để thử HTTP.

~~~text
user-details-demo/
  pom.xml
  src/main/java/com/example/userdetails/
    UserDetailsDemoApplication.java
    ApiController.java
    DemoAccountService.java
    SecurityConfig.java
  src/test/java/com/example/userdetails/
    UserDetailsContractTests.java
~~~

Tên package trong tất cả source Java là **com.example.userdetails**. Đường dẫn và class phải khớp để Java compile và Spring Boot component scan.

### 9.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.6</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>user-details-demo</artifactId>
    <version>1.0.0</version>

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
~~~

**Giải thích dependency:**

- spring-boot-starter-web: Spring MVC, Servlet container và JSON response.
- spring-boot-starter-security: filter chain, UserDetails, DaoAuthenticationProvider, PasswordEncoder.
- spring-boot-starter-test và spring-security-test: JUnit 5, Spring Boot Test, MockMvc và tiện ích HTTP Basic trong test.

Không ghép thêm spring-boot-starter-webflux cho demo này: đây là ứng dụng **Servlet**. Trong WebFlux server, UserDetailsService đồng bộ được thay bằng cơ chế reactive phù hợp và cấu hình bảo mật dùng ServerHttpSecurity.

### 9.3. UserDetailsDemoApplication.java

~~~java
package com.example.userdetails;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class UserDetailsDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(UserDetailsDemoApplication.class, args);
    }
}
~~~

Lớp main ở package gốc giúp Spring Boot quét @RestController, @Service, @Configuration cùng package.

### 9.4. DemoAccountService.java

Đây là nguồn người dùng mẫu. **AccountRow** mô phỏng một dòng database: username, hash, quyền và bốn cờ ở dạng **positive semantics** để tránh nhầm trong schema. Trong loadUserByUsername, ta ánh xạ các cờ sang UserDetails builder.

~~~java
package com.example.userdetails;

import java.util.List;
import java.util.Map;

import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;

@Service
public class DemoAccountService implements UserDetailsService {

    private final Map<String, AccountRow> accounts;

    public DemoAccountService(PasswordEncoder encoder) {
        this.accounts = Map.of(
            "alice", row("alice", encoder,
                List.of("ROLE_USER", "orders:read"), true, true, true, true),
            "ops", row("ops", encoder,
                List.of("ROLE_OPS", "orders:read"), true, true, true, true),
            "locked", row("locked", encoder,
                List.of("ROLE_USER"), true, false, true, true),
            "disabled", row("disabled", encoder,
                List.of("ROLE_USER"), false, true, true, true),
            "expired", row("expired", encoder,
                List.of("ROLE_USER"), true, true, false, true),
            "password-expired", row("password-expired", encoder,
                List.of("ROLE_USER"), true, true, true, false)
        );
    }

    private static AccountRow row(
            String username,
            PasswordEncoder encoder,
            List<String> authorities,
            boolean enabled,
            boolean nonLocked,
            boolean nonExpired,
            boolean credentialsNonExpired) {
        return new AccountRow(
            username,
            encoder.encode("demo-pass"),
            List.copyOf(authorities),
            enabled,
            nonLocked,
            nonExpired,
            credentialsNonExpired
        );
    }

    @Override
    public UserDetails loadUserByUsername(String username) {
        AccountRow account = accounts.get(username);

        if (account == null) {
            throw new UsernameNotFoundException("Account not found");
        }

        // Tạo snapshot UserDetails MỚI cho mỗi lần lookup.
        // Dữ liệu nguồn AccountRow giữ password hash riêng.
        return User.withUsername(account.username())
            .password(account.passwordHash())
            .authorities(account.authorities().toArray(String[]::new))
            .disabled(!account.enabled())
            .accountLocked(!account.accountNonLocked())
            .accountExpired(!account.accountNonExpired())
            .credentialsExpired(!account.credentialsNonExpired())
            .build();
    }

    private record AccountRow(
            String username,
            String passwordHash,
            List<String> authorities,
            boolean enabled,
            boolean accountNonLocked,
            boolean accountNonExpired,
            boolean credentialsNonExpired) {
    }
}
~~~

**Điểm quan trọng trong code:**

1. Map là kho account mẫu, **không phải database thật**.
2. encoder.encode("demo-pass") chạy khi tạo các AccountRow; mỗi account giữ hash BCrypt riêng. Chúng ta không gọi encode lại khi lookup user.
3. List.copyOf(authorities) giữ danh sách quyền ở nguồn ở dạng không sửa được qua tham chiếu thông thường.
4. Khi user không tồn tại, ném UsernameNotFoundException.
5. UserDetails được tạo **mới** từ AccountRow mỗi lần load. Cách này tránh một số lỗi do password trong UserDetails bị xóa sau xác thực rồi làm thay đổi object dùng chung trong cache.
6. .disabled(!enabled) và .accountLocked(!nonLocked) đổi boolean đúng chiều; tương tự accountExpired và credentialsExpired.
7. ROLE_OPS là một authority được cấp cụ thể, không tự có vì username là ops.
8. Bài không kiểm điều kiện đa tenant. Với database thật phải tra theo phạm vi danh tính được tin cậy, quản lý thời hạn và trạng thái nhất quán với policy.

**Tại sao record AccountRow khác UserDetails?** Record mô tả dữ liệu nguồn; UserDetails là projection phục vụ Spring Security. Không trả record chứa password hash từ REST Controller.

### 9.5. SecurityConfig.java

~~~java
package com.example.userdetails;

import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    AuthenticationManager authenticationManager(
            DemoAccountService accounts,
            PasswordEncoder encoder) {

        DaoAuthenticationProvider provider =
            new DaoAuthenticationProvider();
        provider.setUserDetailsService(accounts);
        provider.setPasswordEncoder(encoder);

        return new ProviderManager(List.of(provider));
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            AuthenticationManager manager) throws Exception {

        return http
            .authenticationManager(manager)
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/ops").hasRole("OPS")
                .requestMatchers(HttpMethod.GET, "/api/me").authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
~~~

**Giải thích từng bean:**

- PasswordEncoder tạo BCrypt để bảo vệ password hash.
- DaoAuthenticationProvider kết hợp DemoAccountService và encoder.
- ProviderManager nhận provider để thực thi AuthenticationManager.authenticate(...).
- http.authenticationManager(manager) gắn manager vào HttpSecurity đang cấu hình, tránh phụ thuộc suy đoán về manager tự động trong ứng dụng nhiều cấu hình.
- /api/public là public chỉ với HTTP GET.
- /api/me chỉ yêu cầu danh tính đã xác thực.
- /api/ops đòi ROLE_OPS; một người hợp lệ có ROLE_USER vẫn bị 403.
- anyRequest().denyAll() chặn URL/method không khai báo.
- HTTP Basic dùng username/password mẫu; trong mạng thực, cần HTTPS, secret policy và cơ chế identity phù hợp.

**Không tắt CSRF mặc định** trong demo. Ba endpoint đều chỉ thực hiện GET. Khi thêm POST/PUT/PATCH/DELETE với browser/cookie hoặc HTTP Basic tự gửi credential, phải thiết kế và kiểm thử CSRF đúng threat model. Không xử lý sự cố 403 bằng cách tự động disable CSRF.

**Phiên bản:** Constructor không tham số của DaoAuthenticationProvider và setter trong code minh họa phù hợp dòng Spring Security 6.3.x được Spring Boot 3.3.6 quản lý. Với dòng mới hơn, kiểm Javadoc đúng version và điều chỉnh nếu API khởi tạo thay đổi.

### 9.6. ApiController.java

~~~java
package com.example.userdetails;

import java.util.List;
import java.util.Map;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ApiController {

    @GetMapping("/api/public")
    public Map<String, String> publicEndpoint() {
        return Map.of("message", "public");
    }

    @GetMapping("/api/me")
    public Map<String, Object> currentUser(Authentication auth) {
        List<String> authorities = auth.getAuthorities().stream()
            .map(GrantedAuthority::getAuthority)
            .sorted()
            .toList();

        return Map.of(
            "username", auth.getName(),
            "authorities", authorities
        );
    }

    @GetMapping("/api/ops")
    public Map<String, String> opsOnly() {
        return Map.of("message", "ops");
    }
}
~~~

Spring Security đã xác thực trước khi controller /api/me chạy; username và authorities được lấy từ Authentication đã được xây bằng dữ liệu nguồn đáng tin. API demo chỉ in thông tin tối thiểu để quan sát. Không gửi UserDetails nguyên object làm JSON: có thể lộ password hash, trạng thái nội bộ hoặc dữ liệu không dành cho client.

### 9.7. Khởi động ứng dụng

Trong thư mục chứa pom.xml:

~~~bash
mvn spring-boot:run
~~~

Nếu server khởi động thành công, mặc định lắng nghe **http://localhost:8080**. Các lệnh sau dùng **curl.exe** trên Windows PowerShell; Linux/macOS thay bằng curl.

**Thử endpoint công khai:**

~~~powershell
curl.exe -i http://localhost:8080/api/public
~~~

Kết quả chính:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"message":"public"}
~~~

Header khác có thể xuất hiện, thứ tự header không cố định.

**Thử endpoint cần đăng nhập mà chưa gửi credential:**

~~~powershell
curl.exe -i http://localhost:8080/api/me
~~~

Kết quả thường là **401 Unauthorized** và header challenge HTTP Basic như **WWW-Authenticate: Basic ...**.

**Thử tài khoản alice hoạt động:**

~~~powershell
curl.exe -i -u alice:demo-pass http://localhost:8080/api/me
~~~

Response body có dạng:

~~~json
{
  "username": "alice",
  "authorities": ["ROLE_USER", "orders:read"]
}
~~~

Vì code sắp xếp authorities trước khi trả, thứ tự phần tử array như trên được định nghĩa ở demo. Thứ tự key trong object JSON không nên được xem là hợp đồng.

**Thử endpoint ROLE_OPS:**

~~~powershell
curl.exe -i -u alice:demo-pass http://localhost:8080/api/ops
curl.exe -i -u ops:demo-pass http://localhost:8080/api/ops
~~~

- Alice xác thực thành công nhưng không có ROLE_OPS, thường nhận **403**.
- Ops xác thực thành công và có ROLE_OPS, nhận **200** với JSON {"message":"ops"}.

### 9.8. Thử bốn trạng thái không hợp lệ

~~~powershell
curl.exe -i -u locked:demo-pass http://localhost:8080/api/me
curl.exe -i -u disabled:demo-pass http://localhost:8080/api/me
curl.exe -i -u expired:demo-pass http://localhost:8080/api/me
curl.exe -i -u password-expired:demo-pass http://localhost:8080/api/me
~~~

**Dự kiến cả bốn nhận 401 theo HTTP Basic**, dù password người dùng nhập khớp hash. Nguyên nhân là UserDetails đánh dấu tài khoản không đáp ứng điều kiện trạng thái.

Không nên xây API production trả thông điệp kiểu "username này bị khóa" cho mọi request chưa xác thực: cần cân bằng UX và nguy cơ user enumeration. Một số ứng dụng cung cấp kênh recovery riêng với xác minh danh tính bổ sung.

**Tự đối chiếu:**

| Request | HTTP dự kiến | Giải thích |
| --- | --- | --- |
| GET /api/public không credential | 200 | URL được permitAll. |
| GET /api/me không credential | 401 | Thiếu authentication. |
| GET /api/me với alice + password đúng | 200 | Đủ bốn cờ trạng thái, password đúng. |
| GET /api/me với alice + password sai | 401 | BadCredentialsException. |
| GET /api/me với locked | 401 | isAccountNonLocked=false; provider từ chối. |
| GET /api/me với disabled | 401 | isEnabled=false; provider từ chối. |
| GET /api/me với expired | 401 | isAccountNonExpired=false; provider từ chối. |
| GET /api/me với password-expired | 401 | isCredentialsNonExpired=false; provider từ chối. |
| GET /api/ops với alice | 403 | Đã xác thực nhưng thiếu ROLE_OPS. |
| GET /api/ops với ops | 200 | Có ROLE_OPS. |

Số status trên phản ánh **SecurityFilterChain + HTTP Basic** của demo, không có nghĩa mọi ứng dụng Spring Security đều trả cùng status: form login có thể redirect, custom entry point có thể trả JSON khác.

## 10. Kiểm thử đầy đủ bằng MockMvc và JUnit

Tạo file **src/test/java/com/example/userdetails/UserDetailsContractTests.java**. Các test phân biệt ba mức:

1. **Hợp đồng dữ liệu** trả từ UserDetailsService: username, password hash, authorities và flags.
2. **Provider/AuthenticationManager**: các exception cho password sai và các trạng thái account.
3. **HTTP/SecurityFilterChain**: 200/401/403 và thông tin principal trong body.

~~~java
package com.example.userdetails;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.authentication.AccountExpiredException;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.CredentialsExpiredException;
import org.springframework.security.authentication.DisabledException;
import org.springframework.security.authentication.LockedException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class UserDetailsContractTests {

    @Autowired DemoAccountService accounts;
    @Autowired PasswordEncoder encoder;
    @Autowired AuthenticationManager manager;
    @Autowired MockMvc mvc;

    private Authentication request(String user, String password) {
        return UsernamePasswordAuthenticationToken.unauthenticated(
            user, password);
    }

    @Test
    void userDetailsHasUsernameAndAuthorities() {
        UserDetails alice = accounts.loadUserByUsername("alice");

        assertThat(alice.getUsername()).isEqualTo("alice");
        assertThat(alice.getAuthorities())
            .extracting(GrantedAuthority::getAuthority)
            .contains("ROLE_USER", "orders:read");
        assertThat(alice.isEnabled()).isTrue();
        assertThat(alice.isAccountNonLocked()).isTrue();
        assertThat(alice.isAccountNonExpired()).isTrue();
        assertThat(alice.isCredentialsNonExpired()).isTrue();
    }

    @Test
    void storedPasswordIsHashAndEncoderMatchesRawInput() {
        UserDetails alice = accounts.loadUserByUsername("alice");

        assertThat(alice.getPassword()).isNotEqualTo("demo-pass");
        assertThat(encoder.matches("demo-pass", alice.getPassword()))
            .isTrue();
        assertThat(encoder.matches("wrong", alice.getPassword()))
            .isFalse();
    }

    @Test
    void lockedUserHasNonLockedFalse() {
        UserDetails locked = accounts.loadUserByUsername("locked");
        assertThat(locked.isAccountNonLocked()).isFalse();
        assertThat(locked.isEnabled()).isTrue();
    }

    @Test
    void disabledUserHasEnabledFalse() {
        UserDetails disabled = accounts.loadUserByUsername("disabled");
        assertThat(disabled.isEnabled()).isFalse();
    }

    @Test
    void expiredUserHasNonExpiredFalse() {
        UserDetails expired = accounts.loadUserByUsername("expired");
        assertThat(expired.isAccountNonExpired()).isFalse();
    }

    @Test
    void expiredPasswordHasCredentialsNonExpiredFalse() {
        UserDetails user = accounts.loadUserByUsername("password-expired");
        assertThat(user.isCredentialsNonExpired()).isFalse();
        assertThat(user.isAccountNonExpired()).isTrue();
    }

    @Test
    void unknownUserIsNotFoundAtDataSource() {
        assertThatThrownBy(
            () -> accounts.loadUserByUsername("does-not-exist"))
            .isInstanceOf(UsernameNotFoundException.class);
    }

    @Test
    void validPasswordAuthenticatesAndReturnsAuthorities() {
        Authentication result =
            manager.authenticate(request("alice", "demo-pass"));

        assertThat(result.isAuthenticated()).isTrue();
        assertThat(result.getName()).isEqualTo("alice");
        assertThat(result.getAuthorities())
            .extracting(GrantedAuthority::getAuthority)
            .contains("ROLE_USER", "orders:read");
    }

    @Test
    void wrongPasswordIsRejected() {
        assertThatThrownBy(
            () -> manager.authenticate(request("alice", "wrong")))
            .isInstanceOf(BadCredentialsException.class);
    }

    @Test
    void lockedAccountIsRejectedByDaoProvider() {
        assertThatThrownBy(
            () -> manager.authenticate(request("locked", "demo-pass")))
            .isInstanceOf(LockedException.class);
    }

    @Test
    void disabledAccountIsRejectedByDaoProvider() {
        assertThatThrownBy(
            () -> manager.authenticate(request("disabled", "demo-pass")))
            .isInstanceOf(DisabledException.class);
    }

    @Test
    void expiredAccountIsRejectedByDaoProvider() {
        assertThatThrownBy(
            () -> manager.authenticate(request("expired", "demo-pass")))
            .isInstanceOf(AccountExpiredException.class);
    }

    @Test
    void expiredCredentialsAreRejectedByDaoProvider() {
        assertThatThrownBy(
            () -> manager.authenticate(
                request("password-expired", "demo-pass")))
            .isInstanceOf(CredentialsExpiredException.class);
    }

    @Test
    void publicEndpointIsAccessibleAnonymously() throws Exception {
        mvc.perform(get("/api/public"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.message").value("public"));
    }

    @Test
    void privateEndpointRejectsAnonymous() throws Exception {
        mvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void privateEndpointAcceptsActiveUser() throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("alice", "demo-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username").value("alice"))
            .andExpect(jsonPath("$.authorities[0]").value("ROLE_USER"))
            .andExpect(jsonPath("$.authorities[1]").value("orders:read"));
    }

    @Test
    void privateEndpointRejectsWrongBasicPassword()
            throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("alice", "wrong")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void lockedBasicAccountGetsUnauthorized() throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("locked", "demo-pass")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void roleUserDoesNotGetOpsAccess() throws Exception {
        mvc.perform(get("/api/ops")
                .with(httpBasic("alice", "demo-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void opsRoleGetsOpsAccess() throws Exception {
        mvc.perform(get("/api/ops")
                .with(httpBasic("ops", "demo-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.message").value("ops"));
    }

    @Test
    void fakeRoleHeaderCannotAuthenticate() throws Exception {
        mvc.perform(get("/api/ops")
                .header("X-Role", "OPS"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void undeclaredRouteIsDeniedEvenWithValidUser()
            throws Exception {
        mvc.perform(get("/api/unknown")
                .with(httpBasic("alice", "demo-pass")))
            .andExpect(status().isForbidden());
    }
}
~~~

Chạy:

~~~bash
mvn test
~~~

**22 kiểm thử** bao phủ contract, password hash, 4 account flags, lookup không tồn tại, manager/provider, HTTP Basic và authorization. Trong ứng dụng thực tế có database, cần thêm integration tests cho queries, tenant, password upgrades, concurrency, account state changes và không có side effects khi bị từ chối.

Đây là bộ test được cung cấp để người học **chạy tại máy**, không phải kết quả Maven đã được thực thi trong quá trình viết tài liệu. Nếu test không qua với dependency/version khác, đọc stack trace, kiểm import, account flags, cấu hình security chain và endpoint matching trước khi sửa policy.

### 10.1. Test tầng nào chứng minh điều gì?

| Tầng kiểm thử | Chứng minh được | Chưa tự chứng minh |
| --- | --- | --- |
| UserDetailsService trực tiếp | Đúng dữ liệu username, hash, authorities và flags. | Password đã được kiểm, token đã được xác minh. |
| AuthenticationManager trực tiếp | DaoAuthenticationProvider dùng hash và trạng thái, từ chối credential không hợp lệ. | HTTP filter, cookie/session, TLS và gateway. |
| MockMvc | Request chạy qua SecurityFilterChain/Controller test, status và body phù hợp. | Reverse proxy, ingress, user store production, real database và mạng. |
| HTTP curl khi app chạy | Response qua HTTP stack thực tại localhost. | Chính sách TLS/IdP production và quyền owner/tenant trên dữ liệu thật. |

Cần giữ cả test **trường hợp thành công và thất bại**. Một test login thành công không đủ chứng minh locked/disabled/password-expired không bị bỏ qua.

## 11. Khi nào UserDetails khác Authentication principal?

Trong cơ chế username/password dùng DaoAuthenticationProvider, principal trong Authentication thành công thường là **UserDetails** hoặc có thể là username String theo cấu hình. Nhưng **không phải mọi cơ chế authentication đều dùng UserDetails**.

Ví dụ:

- HTTP Basic/form login qua DaoAuthenticationProvider: UserDetails thường được tải và đưa vào Authentication.
- OAuth2 login/OIDC: principal có thể là OAuth2User hoặc OidcUser.
- JWT Resource Server: principal có thể là Jwt hoặc kiểu được converter tạo.
- Service identity/mTLS: principal có thể là loại chuyên biệt theo cơ chế xác thực.
- Anonymous request: principal có thể đại diện anonymous, không phải account trong user store.

Vì vậy code dưới đây dễ vỡ:

~~~java
// Anti-pattern: không đúng cho mọi kiểu Authentication.
UserDetails user = (UserDetails) authentication.getPrincipal();
~~~

Nếu hệ thống thật dùng nhiều phương thức đăng nhập, principal có thể là Jwt hoặc một loại khác → ClassCastException. Khi chỉ cần username, thường dùng **Authentication.getName()**; khi cần userId/tenant, thiết kế một principal adapter chuẩn hóa theo cơ chế identity đã được xác minh.

### 11.1. UserDetails có phải một database entity không?

**Không bắt buộc, và thường nên tách.** Database entity có thể thay đổi theo ORM/session và chứa thông tin nhạy cảm; UserDetails là projection đủ dùng cho security.

Một cách tách lớp:

~~~text
Database entity / repository
         |
         v
AccountService / UserDetailsService
         |
         v
UserDetails snapshot
         |
         v
AuthenticationManager / provider
         |
         v
SecurityContext Authentication
         |
         v
Domain service kiểm quyền theo object
~~~

Các dữ liệu như số tiền, danh sách đơn, địa chỉ, hash reset token hoặc history không nên nhồi vào principal. Khi code cần user profile, hãy gọi Service/repository với id đã xác thực và chính sách truy cập phù hợp.

## 12. Credentials erasure và bảo vệ password hash trong bộ nhớ

Sau xác thực thành công, ProviderManager mặc định cố **xóa credentials nhạy cảm** khỏi Authentication kết quả nếu implementation hỗ trợ **CredentialsContainer**. Điều này hạn chế raw password tồn tại trong SecurityContext, session hoặc log về sau.

Nhưng cần phân biệt:

- **Raw password** từ request: cần được giữ trong thời gian ngắn nhất.
- **Password hash** lấy từ UserDetails: vẫn là dữ liệu nhạy cảm, không được trả về API.
- **Authentication credentials**: có thể được xóa sau thành công.
- **Principal/UserDetails**: một số implementation như User có thể tham gia cơ chế xóa credentials; hành vi phụ thuộc class và cách đối tượng được chia sẻ.

### 12.1. Lỗi cache thường gặp

Giả sử UserDetailsService trả **đúng object UserDetails mutable đang được giữ trong cache**. Một luồng sau xác thực xóa credentials trên principal, khiến password hash của object được cache bị xóa. Lần đăng nhập tiếp theo lấy cùng object có thể gặp lỗi vì getPassword() không còn hash.

Các cách tiếp cận:

1. Trả một **bản sao/snapshot UserDetails** dành riêng cho mỗi Authentication khi cần.
2. Cache các AccountRow/domain DTO có hash riêng, sau đó ánh xạ thành UserDetails mới khi lookup.
3. Kiểm implementation UserDetails, CredentialsContainer và UserCache thực tế khi thêm caching.
4. Viết test **đăng nhập nhiều lần**, kiểm nguồn user không bị thay đổi ngoài ý muốn.
5. Chỉ thay đổi eraseCredentialsAfterAuthentication khi có lý do bảo mật/hiệu năng và đã phân tích rủi ro; tắt xóa credentials làm tăng dữ liệu nhạy cảm sống lâu hơn.

Trong demo, **AccountRow giữ hash**, còn loadUserByUsername dựng UserDetails mới. Đây là cách thể hiện ranh giới dữ liệu để tránh vô tình sửa nguồn account do cơ chế xóa credentials trên Authentication.

**Không kết luận rằng hash đã biến mất khỏi JVM sau khi eraseCredentials() được gọi.** Một String copy, cache hoặc log có thể vẫn tồn tại; GC không cho bảo đảm xóa ngay mọi byte. Cần thêm kiểm soát logs, dumps, quyền truy cập bộ nhớ và quản lý secret.

## 13. Trạng thái account thay đổi trong khi user đã đăng nhập

Một hệ thống có thể dùng session cookie hoặc access token có thời hạn. Khi account bị khóa/vô hiệu hóa ở database, điều gì xảy ra với một phiên đã xác thực trước đó?

**Không mặc định** mọi request dùng session/JWT đều gọi UserDetailsService và kiểm bốn flags một lần nữa.

- **HTTP Basic** thường gửi credential với từng request; provider có thể tải user và kiểm trạng thái khi cần xác thực.
- **Form login + session** có thể giữ Authentication đã xác thực trong SecurityContext giữa nhiều request; thay đổi trạng thái account ở DB không nhất thiết ngay lập tức chấm dứt phiên.
- **JWT access token** thường được xác minh bằng chữ ký/claims, không tự tải UserDetails hoặc biết tài khoản vừa bị khóa. Việc thu hồi tức thời cần thiết kế riêng.
- **Cached authorities** có thể bị cũ nếu role/permission đổi mà principal hoặc token chưa được refresh.

Các giải pháp phụ thuộc threat model: session invalidation, token revocation/introspection, token ngắn hạn, kiểm trạng thái động cho tác vụ nhạy cảm, version của quyền và cơ chế ép đăng nhập lại. Hệ thống cần định nghĩa SLA cho việc thu hồi quyền và kiểm thử qua nhiều instance.

**Trạng thái UserDetails là snapshot ở thời điểm load.** Nó không phải kênh đồng bộ bảo đảm mọi thay đổi account tức thì tác động tới tất cả session/token.

## 14. Các lỗi phổ biến khi implement UserDetails

### 14.1. Đảo nghĩa nonLocked và accountLocked

~~~java
// Nếu entity.locked=true nghĩa là bị khóa, dòng này SAI:
return entity.isLocked(); // trong isAccountNonLocked()

// Ý nghĩa đúng cần là:
return !entity.isLocked();
~~~

Đây là lỗi rất dễ mắc vì một bên lưu locked, bên kia hỏi nonLocked.

### 14.2. Lưu password thô trong getPassword()

Nếu một implementation trả raw password, hệ thống có thể vô tình lưu bí mật trong principal/session và PasswordEncoder hoạt động sai. Password phải được lưu và trả theo dạng hash phù hợp với encoder.

### 14.3. Hash lại password trong loadUserByUsername

Nếu database đã có BCrypt hash, không gọi encoder.encode(hash) nữa; việc đó tạo hash mới của chuỗi hash cũ và làm matches(raw, doubleHash) thất bại. Chỉ encode password khi tạo/đổi credential theo quy trình.

### 14.4. Tự kiểm password trong UserDetailsService

UserDetailsService có nhiệm vụ tra cứu; để DaoAuthenticationProvider gọi PasswordEncoder.matches theo hợp đồng. Nếu muốn một cơ chế xác thực đặc biệt, thiết kế AuthenticationProvider phù hợp thay vì giấu logic password ở service tra user.

### 14.5. Trả null khi không có user

UserDetailsService nên ném UsernameNotFoundException. Trả null có thể dẫn đến lỗi framework khó hiểu và không tuân theo contract.

### 14.6. Cấp quyền từ input của client

Không tạo authorities bằng request header "X-Role: ADMIN" hoặc trường role trong form đăng ký chưa qua policy. Quyền được nạp từ nguồn tin cậy và phải xét role assignment, tenant, scope, audit và least privilege.

### 14.7. Coi ROLE_USER bao gồm mọi permission

Role, permission và scope là các authority khác nhau. ROLE_USER không tự có orders:read; muốn dùng cả hai phải cấp hoặc map theo policy rõ ràng.

### 14.8. Không kiểm account flags trong custom provider

DaoAuthenticationProvider có xử lý trạng thái khi dùng đúng cấu hình. Một **custom AuthenticationProvider** có thể không tự kiểm isEnabled()/isAccountNonLocked() nếu tác giả quên. Khi dùng custom provider, cần quyết định rõ có dùng UserDetails không, kiểm những trạng thái nào, và viết test khóa/vô hiệu hóa/hết hạn.

### 14.9. Trả UserDetails thẳng từ REST API

UserDetails thường chứa password hash và cờ nội bộ. Không serialize object này nguyên vẹn; trả response DTO được chọn lọc, ví dụ username và permission hiển thị khi nghiệp vụ cần.

### 14.10. Nhầm 401 và 403

- 401 điển hình: thiếu credential hoặc credential/tình trạng account không đạt kiểm tra authentication.
- 403 điển hình: Authentication hợp lệ nhưng thiếu quyền, hoặc cơ chế khác như CSRF chặn request.
- 302 tới login: có thể xuất hiện với form login cho browser.
- 404: có thể do route/object không tồn tại hoặc chính sách che giấu resource.

Đừng suy ra chính xác vì sao account bị khóa chỉ từ HTTP status. Cần phân biệt tầng filter/provider/authorization trong log bảo mật nội bộ.

### 14.11. Tự tạo UserDetails với isEnabled() luôn true

Nếu database lưu trạng thái disabled nhưng implementation bỏ qua nó hoặc luôn trả true, tài khoản đã bị cấm vẫn có thể đăng nhập bằng password cũ. Trạng thái phải đến từ nguồn tin cậy, được cập nhật và test.

### 14.12. Dựa vào username/email mutable làm ownerId

Email có thể thay đổi; một path parameter userId có thể bị giả. Với quyền dữ liệu, dùng ID ổn định, tenant đã xác minh và kiểm tra object-level authorization.

### 14.13. Khóa account sau sai password mà không xét DoS

Tự khóa account vĩnh viễn sau vài lần thử sai có thể bị kẻ tấn công lợi dụng chặn người dùng hợp lệ. Hãy thiết kế rate limit, unlock flow, fraud detection và đo tải theo chính sách.

### 14.14. Không test trùng tên, phân biệt hoa thường và tenant

Một database có thể dùng collation không phân biệt case trong khi application dùng Map case-sensitive. Nếu cùng username tồn tại ở nhiều tenant, phải xác định khóa tra cứu đúng; không tra một user rồi cấp quyền ở tenant khác.

### 14.15. Không test cập nhật quyền/trạng thái sau đăng nhập

Các session/token đang hoạt động có thể mang authority hoặc trạng thái cũ. Cần chính sách thu hồi và kiểm thử chu kỳ sống của Authentication, không chỉ test một lần login mới.

## 15. Khi kết hợp với OAuth2, JWT và LDAP

UserDetails rất quan trọng với **DaoAuthenticationProvider** và username/password, nhưng Spring Security có nhiều mô hình xác thực khác:

| Cơ chế | UserDetails có luôn được dùng không? | Điểm cần hiểu |
| --- | --- | --- |
| Form login + DAO | Thường có. | UserDetailsService + PasswordEncoder + account flags. |
| HTTP Basic + DAO | Thường có. | BasicAuthenticationFilter chuyển credential cho DAO. |
| LDAP | Tùy provider và mapper. | Dữ liệu user/authority có thể lấy từ LDAP; cần map/trạng thái phù hợp. |
| OAuth2/OIDC login | Không nhất thiết. | Principal thường là OAuth2User/OidcUser và metadata token khác. |
| JWT Resource Server | Không mặc định. | JWT được decoder/converter xử lý; các cờ UserDetails không tự kiểm. |
| Opaque token Resource Server | Không mặc định. | Token introspection và authority mapping theo policy. |
| WebFlux reactive username/password | Dùng hợp đồng tương ứng, có thể ReactiveUserDetailsService. | Trả Mono<UserDetails>, quản lý security context bằng Reactor. |
| Machine-to-machine / mTLS | Không nhất thiết. | Principal có thể đại diện service, không phải user trong bảng người dùng. |

Khi chuyển từ Basic sang JWT, nếu trước đó account bị disable khiến DAO từ chối login, việc JWT decoder chỉ kiểm token chữ ký/expiry **không tự bảo đảm disable account ngay giữa vòng đời token**. Cần thiết kế thu hồi hoặc dynamic account status check nếu nghiệp vụ yêu cầu.

Tương tự, một resource server có thể dùng JWT claims chứa roles/scopes. Nó không tự dùng UserDetails#getAuthorities() từ database nếu chưa có mapping và lookup chủ động.

## 16. Từ in-memory sang database thật: checklist thiết kế

Nếu triển khai với Spring Data JPA/JDBC, hãy xác định:

1. **Schema**: username unique theo phạm vi đúng, password_hash, enabled, locked, expires_at, credentials_expires_at; không lưu raw password.
2. **Role/permission**: bảng liên kết hoặc source đáng tin; tránh eager load toàn bộ object graph nhạy cảm chỉ để trả authorities.
3. **Transaction và consistency**: account vừa bị disable trong khi request login đang xử lý cần có quyết định policy cụ thể.
4. **Password encoder**: thuật toán, work factor, phiên bản/identifier và migration từ legacy hash.
5. **Lookup errors**: username không tồn tại → UsernameNotFoundException; DB unavailable → lỗi dịch vụ phù hợp, không tự trả một user mặc định.
6. **Cache**: TTL và invalidation khi đổi password/role/locked flags; không cache UserDetails mutable rồi để eraseCredentials làm biến đổi nguồn.
7. **Audit**: trạng thái account thay đổi khi nào/ai phê duyệt; không log password hash hoặc full token.
8. **Lockout**: chính sách số lần thất bại, rate limiting, chống account enumeration và unlock flow.
9. **Multi-tenant**: định danh đúng tenant, quyền theo owner/tenant và tài nguyên; một login hợp lệ không có nghĩa được truy cập mọi row.
10. **Revocation**: session/token hiện hữu chịu ảnh hưởng thế nào khi đổi quyền/disable.
11. **Tests**: username không có, mật khẩu sai, bốn flags, quyền thấp, role thay đổi, thiếu quyền object, dữ liệu trùng/case/Unicode.
12. **Operations**: HTTPS, secret store, DB least privilege, backup, log redaction, rotation và cập nhật Spring Security.

Với Spring Data JPA, một implementation UserDetailsService thường dùng repository tìm account rồi ánh xạ entity sang UserDetails. Không nhất thiết thêm password check vào repository; hãy giữ việc xác thực ở AuthenticationProvider.

## 17. Quy trình debug khi password đúng nhưng vẫn nhận 401

Khi người dùng chắc chắn đã nhập đúng mật khẩu nhưng /api/me vẫn trả 401, kiểm theo thứ tự:

1. **SecurityFilterChain nào áp dụng?** URL/method có khớp chain dùng Basic/DAO hay đã rơi vào một chain khác?
2. **Authentication filter có đọc được credential không?** Header Authorization: Basic có đúng format, encoding và được gateway chuyển tới backend không?
3. **AuthenticationManager có DaoAuthenticationProvider?** Provider được filter sử dụng có đúng UserDetailsService và PasswordEncoder không?
4. **Username lookup có tìm đúng account?** Kiểm case, Unicode, tenant và DB source; tránh in thông tin nhạy cảm.
5. **getPassword() là hash đúng thuật toán?** Không phải raw password, double-hash hoặc hash bị xóa do cache/credentials erasure?
6. **PasswordEncoder.matches có hoạt động?** So sánh raw input với hash đã lưu; kiểm prefix nếu dùng DelegatingPasswordEncoder.
7. **Bốn flags có đúng không?** isEnabled, isAccountNonLocked, isAccountNonExpired, isCredentialsNonExpired; phân biệt cờ đảo nghĩa từ DB.
8. **Account đã bị đổi trạng thái hoặc cache cũ?** Cân nhắc lifecycle dữ liệu, TTL và consistency.
9. **Exception thực sự là gì?** BadCredentialsException, LockedException, DisabledException, AccountExpiredException hay CredentialsExpiredException? Xem log nội bộ đã lọc secret.
10. **HTTP response có bị proxy/entry point thay đổi?** 401/302/403 có thể do các tầng khác nhau; xác định nguồn đầu tiên từ chối.
11. **Có liên quan authorization không?** Nếu provider đã xác thực đúng nhưng thiếu role, endpoint thường trả 403, không phải do password.
12. **Có thể tái hiện bằng test?** Dùng AuthenticationManager test trực tiếp trạng thái, rồi MockMvc kiểm đúng HTTP status.

**Không xử lý lỗi 401 bằng cách cho permitAll hoặc tắt SecurityFilterChain.** Cần sửa đúng nguyên nhân: dữ liệu UserDetails, encoder, status, provider wiring hoặc chính sách client.

## 18. Bài tập tự luyện

**Bài tập 1 — Nhận diện contract.** Kể đủ bảy phương thức chính của UserDetails. Phân loại phương thức trả String, Collection và boolean; giải thích tại sao ba cờ Non... bình thường đều true.

**Bài tập 2 — Đảo boolean.** Database có cột locked=true. Viết isAccountNonLocked() đúng. Hãy tạo test khi locked=false và khi locked=true.

**Bài tập 3 — Giải thích lỗi password.** Một developer lưu BCrypt hash trong database, nhưng trong loadUserByUsername lại gọi encoder.encode(hash) và trả hash mới. Vì sao password đúng bị từ chối?

**Bài tập 4 — Authorities.** User có ROLE_USER và orders:read. hasRole("ADMIN") có qua không? hasAuthority("orders:read") có qua không? Vì sao ROLE_USER không tự có mọi permission?

**Bài tập 5 — Trạng thái.** Alice có mật khẩu đúng nhưng isCredentialsNonExpired=false. Exception nào thường xuất hiện với DaoAuthenticationProvider? HTTP Basic thường trả status gì?

**Bài tập 6 — UsernameNotFound.** Khi loadUserByUsername không tìm thấy account, nên trả null hay ném UsernameNotFoundException? AuthenticationManager có thể trả lỗi công khai nào?

**Bài tập 7 — In-memory và production.** Vì sao InMemoryUserDetailsManager hoặc Map mẫu phù hợp bài lab nhưng không đủ cho quản lý danh tính thật?

**Bài tập 8 — Nguồn dữ liệu và principal.** Một database entity chứa username, password_hash, phone, paymentInfo, tenantId và 20 trường khác. Hãy thiết kế một UserDetails projection chỉ mang những trường cần, sau đó nêu cách Service lấy data nghiệp vụ theo ID đáng tin.

**Bài tập 9 — Account lifecycle.** User vừa bị disable ở database nhưng vẫn có JWT hiệu lực thêm 30 phút. Vì sao đổi UserDetails.isEnabled() ở DB chưa chắc chặn được API ngay? Đề xuất chiến lược thu hồi phù hợp.

**Bài tập 10 — Caching.** Một UserDetails mutable được cache và ProviderManager erase credentials sau login. Lỗi nào có thể xuất hiện ở lần login tiếp theo? Vì sao demo tạo snapshot mới?

**Bài tập 11 — Đa tenant.** Hai tenant có cùng username "alice". Chỉ gọi loadUserByUsername("alice") có đủ để tìm đúng người chưa? Hãy đề xuất nguồn định danh tenant đáng tin.

**Bài tập 12 — Kiểm thử.** Viết thêm test tài khoản disabled trong HTTP Basic nhận 401, rồi thêm test provider trực tiếp ném DisabledException để phân biệt phản hồi HTTP với lỗi ở tầng xác thực.

### Checklist ghi nhớ

- **UserDetails mô tả account cho security**, không tự xác thực password và không phải toàn bộ entity nghiệp vụ.
- **getUsername()** là định danh theo chính sách lookup; **getPassword()** thường trả hash đã lưu.
- **getAuthorities()** trả GrantedAuthority; ROLE_ và permission string cần được cấp từ nguồn đáng tin.
- **isEnabled() = true**, **isAccountNonLocked() = true**, **isAccountNonExpired() = true**, **isCredentialsNonExpired() = true** là trạng thái bình thường.
- **Account locked, disabled, expired, credentials expired** có ý nghĩa khác nhau và có thể tạo những AuthenticationException khác.
- **UserDetailsService chỉ lookup**, **DaoAuthenticationProvider + PasswordEncoder** xác minh credential và trạng thái account.
- **UsernameNotFoundException** là tín hiệu tra cứu không có user; API không nên để lộ sự tồn tại của tài khoản.
- **Role khác quyền đối tượng**: authenticated()/hasRole không tự thay check owner/tenant ở domain Service.
- **UserDetails là snapshot**; session/JWT có thể tiếp tục còn hiệu lực khi trạng thái account đã đổi, nếu chưa có cơ chế thu hồi.
- **Không serialize password hash, raw password hoặc toàn bộ UserDetails ra HTTP response**.
- **Kiểm thử bốn cờ ở cả tầng dữ liệu, provider và HTTP**, chứ không chỉ login 200.

## Tài liệu tham khảo

- [Spring Security — UserDetails JavaDoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/userdetails/UserDetails.html): username, password, authorities và bốn trạng thái account.
- [Spring Security — UserDetailsService](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/user-details-service.html): hợp đồng tìm user.
- [Spring Security — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/dao-authentication-provider.html): kết hợp UserDetailsService, PasswordEncoder và UserDetails.
- [Spring Security — Password Storage](https://docs.spring.io/spring-security/reference/features/authentication/password-storage.html): PasswordEncoder, thuật toán và lưu trữ credential.
- [Spring Security — Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html): ProviderManager, Authentication và SecurityContext.

**Lưu ý phiên bản:** Mã ví dụ dùng Spring Boot 3.3.6 và Spring Security 6.3.x, phù hợp cho việc minh họa API trong bài học. Khi làm dự án thật, hãy chọn dòng được hỗ trợ, áp dụng bản vá và xác minh chi tiết API/constructor với version hiện tại của dependencies.

## Kết luận

**UserDetails là bản mô tả account phục vụ xác thực username/password**: getUsername() xác định tài khoản, getPassword() cung cấp hash, getAuthorities() cung cấp quyền đã cấp, còn bốn cờ trạng thái báo tài khoản có đủ điều kiện sử dụng hay không. UserDetailsService chịu trách nhiệm nạp dữ liệu từ nguồn đáng tin, DaoAuthenticationProvider dùng PasswordEncoder và account checks để xác minh, còn Spring Security chuyển kết quả sang Authentication và thực thi authorization. Tách rõ những trách nhiệm này, ánh xạ đúng dấu boolean, bảo vệ password hash và kiểm thử mọi trạng thái sẽ giúp tránh các lỗi đăng nhập, rò bí mật và cấp quyền sai.
