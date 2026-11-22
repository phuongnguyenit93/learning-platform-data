# eraseCredentialsAfterAuthentication và tác động đến đối tượng dùng chung

Trong Spring Security, `ProviderManager` mặc định bật tùy chọn **`eraseCredentialsAfterAuthentication`**. Sau khi xác thực **thành công**, manager kiểm tra kết quả `Authentication`: nếu kết quả triển khai `CredentialsContainer`, nó gọi `eraseCredentials()` trước khi trả về cho bên gọi. Mục tiêu là giảm thời gian mật khẩu hoặc dữ liệu nhạy cảm tiếp tục nằm trong các object Java, nhất là object có thể được đưa vào `SecurityContext` và HTTP session.

Tuy nhiên, nếu kết quả `Authentication` chứa một tham chiếu đến đúng object `UserDetails` đang nằm trong cache, việc xóa thông tin nhạy cảm có thể **làm biến đổi chính object dùng chung**. Khi ấy cache vẫn giữ key, nhưng password hash bên trong object đã thành `null`; request xác thực tiếp theo có thể thất bại hoặc phải tải lại dữ liệu từ nguồn lưu trữ.

Bài này giải thích đầy đủ **khi nào xóa, xóa cái gì, vì sao aliasing xảy ra, cách tái hiện bằng Java 17, các phương án sửa và cách kiểm thử**. Chủ đề nằm trong nhóm **Bộ máy xác thực** của Spring Security Authentication; không nhầm nó với logout, đổi mật khẩu hoặc thu hồi token.

## 1. Vai trò của cờ eraseCredentialsAfterAuthentication

Một luồng username/password điển hình:

~~~text
Client cung cấp username và password
                |
                v
Filter nhận yêu cầu đăng nhập
                |
                v
Authentication request (chưa xác thực; credentials=raw password)
                |
                v
ProviderManager.authenticate(request)
                |
                +--> AuthenticationProvider
                |       |
                |       +--> UserDetailsService/cache tải UserDetails
                |       +--> PasswordEncoder.matches(raw, passwordHash)
                |       +--> Trả Authentication thành công
                |
                +--> Nếu eraseCredentialsAfterAuthentication=true:
                |       Nếu result instanceof CredentialsContainer:
                |           result.eraseCredentials()
                |
                v
Authentication result đã xác thực
                |
                v
Filter/handler xử lý SecurityContext/session tùy cấu hình
~~~

`AuthenticationManager.authenticate` định nghĩa hợp đồng xác thực; `ProviderManager` là một implementation phổ biến và là nơi có cờ trên. Mặc định của `ProviderManager` là **`true`**. Nếu tự triển khai một `AuthenticationManager` hoàn toàn khác, không tự suy ra nó cũng thực hiện erasure trừ khi implementation có hợp đồng tương đương.

| Câu hỏi | Kết luận |
|---|---|
| Khi nào manager gọi erasure? | Sau khi tìm được kết quả thành công và trước khi trả kết quả |
| Có gọi cho mọi `Authentication` không? | Chỉ nếu kết quả hỗ trợ `CredentialsContainer` và cờ đang bật |
| Có chắc xóa mọi secret trong object graph? | Không; tùy implementation `eraseCredentials()` của từng object |
| Có xóa credentials khỏi bản ghi database không? | Không; không phải lệnh cập nhật password hash trong DB |
| Có xóa request token gốc và mọi bản sao String không? | Không có bảo đảm như vậy |
| Có tự thu hồi session/JWT không? | Không; đó là cơ chế vòng đời xác thực riêng |

API cấu hình điển hình (đoạn minh họa, `providers` chưa khai báo ở đây):

~~~java
ProviderManager manager = new ProviderManager(providers);
boolean current = manager.isEraseCredentialsAfterAuthentication();
manager.setEraseCredentialsAfterAuthentication(true);
~~~

Cách làm thông thường là **giữ nguyên `true`**, sau đó sửa thiết kế tham chiếu nếu cache bị ảnh hưởng.

## 2. CredentialsContainer hoạt động như thế nào?

`org.springframework.security.core.CredentialsContainer` có contract:

~~~java
public interface CredentialsContainer {
    void eraseCredentials();
}
~~~

Nó không định nghĩa một trường `password` chung. Đối tượng triển khai phải biết cần loại bỏ tham chiếu nào. Những loại liên quan thường gặp:

- `AbstractAuthenticationToken` triển khai `CredentialsContainer` và khi xóa sẽ xem xét **`getCredentials()`, `getPrincipal()` và `getDetails()`**. Nếu một trong ba object đó cũng triển khai `CredentialsContainer`, method xóa tương ứng của object được gọi.
- `UsernamePasswordAuthenticationToken` còn đặt trường `credentials` của token thành `null` khi erasure thực hiện.
- `org.springframework.security.core.userdetails.User` là implementation `UserDetails` mutable có `eraseCredentials()` đặt password hash field của **instance đó** thành `null`.
- Custom principal/token chứa bí mật phải được thiết kế thích hợp: nếu không triển khai `CredentialsContainer`, framework không tự dò từng field bằng reflection.

Luồng tham chiếu minh họa:

~~~text
Authentication result S (CredentialsContainer)
  |- credentials  --> password object / secret
  |- principal    --> UserDetails U (CredentialsContainer)
  '- details      --> Details D (có thể là CredentialsContainer)

S.eraseCredentials()
  |- credentials.eraseCredentials() nếu implement interface
  |- U.eraseCredentials()           nếu implement interface
  '- D.eraseCredentials()           nếu implement interface
  '- Với UsernamePasswordAuthenticationToken: credentials = null
~~~

Chú ý **khác biệt giữa các loại dữ liệu nhạy cảm**:

1. Raw password ở request là bí mật do client gửi. Thường không nên đưa vào kết quả sau khi kiểm tra thành công.
2. Password hash trong `UserDetails` cũng nhạy cảm nhưng thường cần còn tồn tại ở nguồn đáng tin để xác thực lần tiếp theo. Xóa hash trên **bản sao dùng riêng cho request** có thể phù hợp; xóa hash trên **object cache gốc** là rủi ro.
3. Principal thường chỉ cần ID, username và authorities; không nên giữ raw password, refresh token, private key, connection secret hay entity JPA giàu dữ liệu.

Erasure trong Java thường **hủy tham chiếu**, không phải bảo đảm ghi đè mọi byte cũ trong RAM. Ví dụ, đặt một trường `String password` thành `null` không chứng minh rằng mọi bản sao String đã được xóa khỏi heap ngay lập tức. Vì thế cách phòng vệ tốt gồm ít copy secret, không log bí mật và rút ngắn thời gian lưu giữ.

### 2.1. Một lưu ý về đường xác thực thất bại

Manager chỉ có bước xóa trên **kết quả thành công** ở hợp đồng đang xét. Khi provider ném `AuthenticationException`, không được mặc định request token của lần thất bại đã tự sạch. Với custom login/filter, không đưa raw password hoặc token vào log/error response; quản lý reference của request và vòng đời bí mật phù hợp.

## 3. Aliasing: tại sao cache bị thay đổi mà không gọi cache.put?

Giả sử cache lưu một object `U`. Một provider sau khi kiểm tra hash trả `Authentication` có principal tham chiếu tới `U`.

~~~text
Cache: "linh" --------> UserDetails U
                             |
                             | passwordHash="$2a$..."
                             ^
                             |
Authentication result -------+  (cùng Java object, không phải bản sao)
       |
       v
ProviderManager gọi result.eraseCredentials()
       |
       v
U.eraseCredentials()
       |
       v
U.password = null
       |
       v
Cache vẫn trỏ đến U, nhưng U.password đã là null
~~~

Đó là **reference aliasing**: nhiều biến/đường dẫn cùng trỏ đến một object. Lệnh `UserDetails other = cachedUser;` chỉ tạo thêm tham chiếu; không sao chép UserDetails. Ngay cả khi `cachedUser.equals(principal)` là `true`, chưa chắc chúng là cùng instance vì `equals` có thể so theo username. Muốn xác minh dùng chung instance trong test, dùng `cachedUser == result.getPrincipal()`.

Nếu cache trả đúng instance cho nhiều request, một lần đăng nhập hoàn tất có thể tác động tới những request khác. Với đối tượng mutable, thời điểm xóa và thời điểm `PasswordEncoder.matches(...)` diễn ra trên các thread khác nhau có thể tạo lỗi khó tái hiện.

### 3.1. Cache thường gặp

| Mô hình | Rủi ro |
|---|---|
| Singleton Map chứa `UserDetails` và service trả nguyên entry | Manager xóa hash ngay trên entry |
| `@Cacheable` của `loadUserByUsername` trả cùng reference trong cùng process | Principal dùng chung với cache |
| `UserCache` dùng trong `DaoAuthenticationProvider` | Tùy cách provider/cache trả object và fallback, cache có thể bị ảnh hưởng |
| Tạo một `UserDetails` mới cho mỗi login | Erasure thường chỉ tác động lên instance của lần đó |
| Principal chỉ chứa ID/username mới tạo | Không còn reference tới password hash trong cache |
| Cache lưu object bất biến, provider dựng bản sao mutable theo request | Bản sao bị xóa, cache gốc được giữ nguyên |

Không phải mọi `DaoAuthenticationProvider` đều có cùng biểu hiện “login lần hai chắc chắn thất bại”. Một số đường thực thi có khả năng nạp lại `UserDetails` từ source sau khi kiểm tra cache thất bại; chương trình có thể tiếp tục đăng nhập nhưng tăng truy vấn và làm cache mất tác dụng. Cần đo cache hits, số lần gọi database và độ trễ, ngoài việc kiểm tra kết quả login.

## 4. Ví dụ thực thi Java 17: tái hiện lỗi và sửa bằng principal tách rời

Chương trình Java dưới đây dùng Spring Security Core và Crypto trực tiếp, không cần Spring Boot hay web server. Nó tạo hai kịch bản độc lập:

- **UNSAFE:** custom provider đặt nguyên `cachedUser` (chính instance `User` mà cache đang dùng) vào principal trả về.
- **SAFE:** provider xác thực bằng `cachedUser` nhưng trả principal `String` chỉ chứa username đã được kiểm tra, không giữ reference tới object cached. Trong dự án thật, nên dùng một projection bất biến có ID nội bộ ổn định.

Cả hai `ProviderManager` đều sử dụng mặc định `eraseCredentialsAfterAuthentication=true`. Thay đổi duy nhất ảnh hưởng lỗi chính là **danh tính instance được trả cho authentication**, không phải tắt erasure.

### 4.1. Cấu trúc project và Gradle

~~~text
credentials-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/example/CredentialsDemo.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'credentials-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'application'
}

group = 'example'
version = '1.0'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.security:spring-security-core:6.3.8'
    implementation 'org.springframework.security:spring-security-crypto:6.3.8'
}

application {
    mainClass = 'example.CredentialsDemo'
}
~~~

Phiên bản trong demo được pin để các API nêu trong bài có cùng hệ quy chiếu; Spring Boot thật thường quản lý phiên bản Spring Security qua dependency management/BOM. Yêu cầu JDK 17+, Gradle tương thích và tải dependency lần đầu từ Maven Central.

### 4.2. Mã nguồn độc lập

Tạo `src/main/java/example/CredentialsDemo.java` với nội dung:

~~~java
package example;

import java.util.List;

import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;

public final class CredentialsDemo {

    public static void main(String[] args) {
        PasswordEncoder encoder = new BCryptPasswordEncoder();
        runScenario("UNSAFE", false, encoder);
        runScenario("SAFE", true, encoder);
    }

    private static void runScenario(String label,
                                    boolean detachPrincipal,
                                    PasswordEncoder encoder) {
        // Một entry UserDetails được dùng lại cho hai lần đăng nhập.
        UserDetails cachedUser = User.withUsername("linh")
                .password(encoder.encode("demo-pass"))
                .authorities("notes:read")
                .build();

        AuthenticationProvider provider =
                new DemoProvider(cachedUser, encoder, detachPrincipal);
        ProviderManager manager = new ProviderManager(List.of(provider));
        // Để nguyên cấu hình mặc định eraseCredentialsAfterAuthentication=true.

        for (int attempt = 1; attempt <= 2; attempt++) {
            Authentication request =
                    UsernamePasswordAuthenticationToken.unauthenticated(
                            "linh", "demo-pass");

            try {
                Authentication result = manager.authenticate(request);
                System.out.println(label + "#" + attempt
                        + " OK, credentialsNull="
                        + (result.getCredentials() == null)
                        + ", cachedHashPresent="
                        + (cachedUser.getPassword() != null));
            } catch (AuthenticationException ex) {
                System.out.println(label + "#" + attempt
                        + " FAIL=" + ex.getClass().getSimpleName()
                        + ", cachedHashPresent="
                        + (cachedUser.getPassword() != null));
            }
        }
    }

    private static final class DemoProvider
            implements AuthenticationProvider {
        private final UserDetails cachedUser;
        private final PasswordEncoder encoder;
        private final boolean detach;

        private DemoProvider(UserDetails cachedUser,
                             PasswordEncoder encoder, boolean detach) {
            this.cachedUser = cachedUser;
            this.encoder = encoder;
            this.detach = detach;
        }

        @Override
        public Authentication authenticate(Authentication request)
                throws AuthenticationException {
            if (!cachedUser.getUsername().equals(request.getName())
                    || !(request.getCredentials() instanceof String)) {
                throw new BadCredentialsException("Invalid credentials");
            }
            String raw = (String) request.getCredentials();
            if (!encoder.matches(raw, cachedUser.getPassword())) {
                throw new BadCredentialsException("Invalid credentials");
            }

            // UNSAFE: cùng UserDetails như cache.
            // SAFE: principal mới chỉ là username, không giữ hash.
            Object principal = detach
                    ? cachedUser.getUsername() : cachedUser;

            // Chỉ để trình diễn manager xóa credentials của result.
            // Provider production nên trả null khi không cần secret.
            return UsernamePasswordAuthenticationToken.authenticated(
                    principal, raw, cachedUser.getAuthorities());
        }

        @Override
        public boolean supports(Class<?> type) {
            return UsernamePasswordAuthenticationToken.class
                    .isAssignableFrom(type);
        }
    }
}
~~~

### 4.3. Chạy và kết quả mong đợi

Nếu thư mục project có Gradle Wrapper:

~~~bash
./gradlew run
~~~

Nếu chưa có wrapper nhưng đã cài Gradle phù hợp, chạy `gradle run`. Trên PowerShell có wrapper, dùng `.\gradlew.bat run`. Đầu ra của riêng chương trình (bỏ qua log Gradle):

~~~text
UNSAFE#1 OK, credentialsNull=true, cachedHashPresent=false
UNSAFE#2 FAIL=BadCredentialsException, cachedHashPresent=false
SAFE#1 OK, credentialsNull=true, cachedHashPresent=true
SAFE#2 OK, credentialsNull=true, cachedHashPresent=true
~~~

Giải thích logic:

1. `cachedUser` được tạo từ `User.withUsername(...).build()`, nên là object thực tế triển khai `CredentialsContainer`. Giá trị hash BCrypt thay đổi do salt ngẫu nhiên giữa các lần chạy; kiểm tra `matches` vẫn cho kết quả nhất quán.
2. Provider kiểm tra đúng username và raw password với hash từ `cachedUser`.
3. Trong UNSAFE lần 1, principal kết quả trỏ vào **cùng UserDetails instance**. `ProviderManager` xóa credentials trên result, dẫn đến `User.eraseCredentials()` trên principal; `cachedUser.getPassword()` thành `null`.
4. UNSAFE lần 2 gọi provider với cùng cache entry đã mất hash. `PasswordEncoder.matches(...)` không còn một hash hợp lệ và provider ném `BadCredentialsException`. Demo custom provider này không có nhánh nạp lại DB.
5. Trong SAFE, principal là username `String` đã được xác thực; result không giữ `cachedUser`, nên manager chỉ xóa credential trên token kết quả. Hash cache gốc còn nguyên, cả hai lần xác thực đều thành công.
6. `credentialsNull=true` xuất hiện vì demo cố tình đặt raw password trong result rồi để manager xóa. Đây chỉ là cách quan sát trực tiếp erasure; trong code production nên tránh đặt raw password vào result ngay từ đầu.

Điểm học tập không nằm ở việc luôn dùng `String` làm principal. Ứng dụng thực thường cần `accountId`, `tenantId` hoặc profile tối thiểu trong một principal/DTO **bất biến và không có secret**, rồi truy vấn account hiện tại từ repository khi cần.

### 4.4. Thử nghiệm về cờ nhưng không áp dụng tùy tiện

Có thể thêm lệnh sau ngay sau khi tạo `ProviderManager` trong demo **chỉ để quan sát khác biệt**:

~~~java
manager.setEraseCredentialsAfterAuthentication(false);
~~~

Khi tắt, manager không gọi erasure trên result, nên trong ví dụ UNSAFE cache hash không bị xóa bởi cơ chế này; nhưng `result.getCredentials()` sẽ vẫn giữ raw password từ provider demo. Trong ứng dụng web, nếu result được lưu vào `SecurityContext`/session, điều này làm tăng nguy cơ lộ credential.

**Vì vậy, giải pháp chính cho vấn đề object dùng chung là tách tham chiếu hoặc copy object thích hợp, giữ erasure mặc định bật.**

## 5. Giải pháp production: kiểm soát ownership và vòng đời object

### 5.1. Tạo principal an toàn, tách khỏi cache

Ví dụ một principal bất biến:

~~~java
record CurrentActor(java.util.UUID accountId, String username) {}
~~~

Sau khi kiểm tra credential và trạng thái tài khoản bằng dữ liệu đáng tin, provider tạo object mới:

~~~java
CurrentActor actor = new CurrentActor(account.id(), account.username());
Authentication verified =
        UsernamePasswordAuthenticationToken.authenticated(
                actor, null, grantedAuthorities);
~~~

Hai đoạn này là **mã minh họa trong ứng dụng có sẵn `account` và `grantedAuthorities`**, không phải một chương trình hoàn chỉnh khi chép tách rời. Không đưa password hash, raw token, JPA entity hoặc object cache vào `CurrentActor`. `accountId` là ID nội bộ ổn định; `username` có thể đổi.

Đảm bảo provider dùng authorities **được cấp từ server**, không copy role do client tự khai báo. Erasure chỉ là một lớp bảo vệ; kết quả authentication vẫn phải được tạo sau khi xác minh đầy đủ.

### 5.2. Trả một bản sao UserDetails per request

Nếu provider cần principal kiểu `UserDetails`, có thể để cache giữ bản gốc và trả **instance khác**, chẳng hạn tạo bản sao ngay trong `UserDetailsService`/adapter:

~~~java
UserDetails perRequest = User.withUserDetails(cachedUser).build();
~~~

Đoạn này giả định `cachedUser` có hash còn nguyên. `User.withUserDetails` tạo `User` chuẩn; cần tự xử lý các field bổ sung nếu app dùng custom `UserDetails` (ID nội bộ, tenant, flags khác). Sau đó provider có thể trả `perRequest`, để erasure tác động lên bản sao mà không làm mất dữ liệu của cache gốc.

**`UserDetails copy = cachedUser;` hoàn toàn không phải bản sao.** Nó chỉ thêm một biến trỏ vào cùng object. Khi clone, kiểm tra cả các field lồng nhau: nếu principal mới vẫn giữ reference đến một mutable object chứa secret, aliasing có thể còn tồn tại.

### 5.3. Kiểm soát cache, invalidation và concurrency

Với `UserCache` hoặc `@Cacheable`, đặt ra các câu hỏi cụ thể:

- Cache giữ `UserDetails` mang password hash, account entity hay projection nào?
- Getter từ cache trả cùng instance hay tạo bản sao?
- Khi đổi password, khóa account, đổi quyền thì invalidate entry theo hợp đồng nào?
- Có bao nhiêu instance `ProviderManager` và filter chain cùng tham gia; manager nào thực sự được dùng?
- Provider có đường fallback nạp lại `UserDetailsService` nếu cache hit chứa dữ liệu không dùng được?
- Có thể đồng thời request A gọi `PasswordEncoder.matches(...)` khi request B đang erasure principal cùng instance không?
- Audit có in toàn bộ principal/token, credentials hoặc hash ra log không?

Với số lượng đăng nhập nhỏ, **không cache UserDetails chứa hash** đôi khi giảm hẳn độ phức tạp và nguy cơ. Nếu dùng cache, bảo vệ hash như dữ liệu nhạy cảm: TTL, quyền truy cập, kiểm soát log và quy trình invalidate.

### 5.4. Khi nào cân nhắc tắt eraseCredentialsAfterAuthentication?

API `ProviderManager#setEraseCredentialsAfterAuthentication(false)` có tồn tại và tài liệu Spring Security nêu như một lựa chọn khi cache sử dụng object chia sẻ. Nhưng đó là **đánh đổi**: result có thể giữ raw password, API key hoặc dữ liệu bí mật lâu hơn trong memory, đặc biệt nếu principal/details chứa dữ liệu nhạy cảm.

Chỉ cân nhắc tùy chọn này khi đã phân tích provider/token/result cụ thể và có biện pháp giới hạn dữ liệu nhạy cảm; ưu tiên trả projection detached hoặc sao chép dữ liệu hợp lệ trước. Đừng tắt cờ toàn cục chỉ để làm hết một lỗi xác thực mà chưa chứng minh nguyên nhân.

## 6. Những hiểu lầm cần loại bỏ

**“Sau đăng nhập, password hash trong database cũng bị xóa.”** Sai: cơ chế này thay đổi các object Java đáp ứng `CredentialsContainer`, không phát sinh câu SQL cập nhật mật khẩu.

**“Cache có bản sao object nên an toàn.”** Chưa chắc: cache thường giữ reference; lấy ra từ map không tự clone. Cần kiểm tra bằng `==` trong test.

**“Nếu cache hash thành null thì chắc cache entry đã bị xóa.”** Không đúng: key có thể vẫn nằm trong map và trỏ tới object bị mutate.

**“Tất cả các lần login thứ hai đều thất bại.”** Không. Kết quả còn phụ thuộc provider/cache và khả năng nạp lại dữ liệu. Cần kiểm tra cả chất lượng cache và số lần truy vấn.

**“Xóa credentials thì cũng logout mọi session, thu hồi token.”** Không. Logout/session invalidation/token revocation là các hành vi khác.

**“Tắt erasure để khắc phục lỗi không có tác dụng phụ.”** Sai: dữ liệu nhạy cảm có thể được giữ trong `Authentication` kết quả và cả session/log nếu ứng dụng vô ý lưu.

**“Custom Authentication implements CredentialsContainer là đủ.”** Chưa chắc: `eraseCredentials()` phải thực sự dọn field secret hoặc container lồng nhau phù hợp. Tốt hơn là không lưu secret trong result.

**“Erasure dọn sạch mọi bản sao String khỏi RAM.”** Không có hợp đồng như vậy. Nulling field giảm reference; JVM không bảo đảm mọi byte cũ biến mất ngay.

**“Sau authenticate tôi có thể dùng result.getCredentials() để gọi service khác.”** Không nên; kết quả có thể đã xóa secret. Thiết kế flow chỉ cần principal/authorities; đừng dùng password của người dùng làm credential thay mặt cho các dịch vụ khác.

## 7. Chẩn đoán lỗi một cách có hệ thống

Khi một hệ thống login hoạt động lần đầu nhưng chập chờn ở các lần tiếp theo:

1. Kiểm tra `ProviderManager.isEraseCredentialsAfterAuthentication()` trên manager **thực sự** xử lý loại request đang lỗi.
2. Tạo integration test xác thực cùng username hai lần và giữ một handle riêng đến cached entry.
3. Trước/sau lần 1, chỉ đo boolean `cachedUser.getPassword() != null`; không in hash hoặc raw secret.
4. Kiểm tra `authentication.getPrincipal() == cachedUser`. Dùng `==` cho identity; `equals()` có thể đúng chỉ vì username giống nhau.
5. Đếm `loadUserByUsername`/cache hit/cache miss. Login thành công nhưng phải tải DB lại ở mỗi lần cũng là tín hiệu.
6. Tìm nơi tạo authenticated token: có đặt cùng `UserDetails`/mutable entity vào principal hay không?
7. Thử phiên bản trả principal detached. Nếu vấn đề biến mất và cache không đổi, tiếp tục kiểm thử phân quyền và trạng thái account.
8. Thêm concurrency test nhiều request xác thực cùng account; tránh shared mutable reference giữa provider và result.

Không đưa `toString()` của Authentication, request body chứa password, nguyên JWT hoặc hash vào log khi điều tra. Quan sát bằng ID vô hại, kiểu class và trạng thái boolean, tránh làm dữ liệu bí mật xuất hiện trong hệ thống logging.

## 8. Ma trận kiểm thử nên có

| Kịch bản | Kết quả mong đợi |
|---|---|
| Xác thực thành công, erasure mặc định | `Authentication` thành công, credentials của result không còn khi token hỗ trợ xóa |
| Principal `UserDetails` dùng chung với cache | Test tái hiện erasure có thể làm hash của cache thành null |
| Provider trả principal an toàn, detached | Cache gốc không bị mutate, xác thực lần hai vẫn bình thường |
| Cache có bản sao per request | Erasure chỉ tác động đến bản sao, không làm hỏng nguồn cache |
| Cache hit sau login thành công | Không bị giảm hiệu quả bất thường hay phát sinh truy vấn DB không mong muốn |
| Hai login đồng thời | Không race vì một request làm mất hash của request khác |
| Custom token chứa secret | `eraseCredentials()` thật sự dọn field bí mật được sở hữu |
| Authentication thất bại | Không giả định credential của request lỗi được manager dọn theo nhánh thành công |
| Đổi mật khẩu/khóa account | Cache được invalidate đúng chính sách, session/token xử lý riêng |
| Tắt erasure trong test | Nhìn thấy được secret tồn tại lâu hơn trong result của demo |
| SecurityContext/session | Không serialize raw password, hash, private key hay token nhạy cảm không cần thiết |

### 8.1. Bài tập phân tích

**Câu 1.** Vì sao `UserDetails cached = repository.load(...)` và `Authentication principal = cached` có thể tạo lỗi?  
**Đáp án:** Chúng có thể trỏ cùng object mutable. Manager xóa credentials trên principal, tức là thay đổi object mà cache/repository adapter còn giữ.

**Câu 2.** Có phải việc `cached.equals(result.getPrincipal()) == true` luôn chứng minh cùng instance?  
**Đáp án:** Không. Hai object khác nhau có thể `equals`; dùng identity `==` khi kiểm tra aliasing.

**Câu 3.** Đã tắt cờ erasure và đăng nhập lần hai thành công. Có đủ để kết luận giải pháp đúng cho production?  
**Đáp án:** Không. Phải xem có raw credentials/secret còn trong Authentication, context hoặc session. Tách principal/copy object thường là giải pháp an toàn hơn.

**Câu 4.** Lần login tiếp theo vẫn thành công dù hash trong cached object bị null. Có nghĩa cache ổn?  
**Đáp án:** Chưa. Provider có thể fallback tải dữ liệu mới; cần quan sát cache hit, database load và độ trễ.

**Câu 5.** Nếu custom authentication result không triển khai `CredentialsContainer`, manager có tự xóa private key trong một field bất kỳ không?  
**Đáp án:** Không. Cần trả result không chứa secret hoặc triển khai erasure đúng hợp đồng.

**Câu 6.** Xóa raw password khỏi result có thay thế cơ chế thu hồi access token sau khóa tài khoản không?  
**Đáp án:** Không. Erasure xử lý bộ nhớ của object đã xác thực; revoke/token validity/session management là trách nhiệm khác.

## 9. Checklist thiết kế trước khi triển khai

- Giữ `eraseCredentialsAfterAuthentication=true` trừ khi có lý do và kiểm soát rủi ro cụ thể.
- Không mang raw password, password hash, API token hay entity JPA vào principal của result khi không cần.
- Biết chính xác cache đang giữ **instance** nào; không coi thêm biến/tham chiếu là bản sao.
- Nếu provider dùng UserDetails mutable từ cache, tạo principal detached hoặc UserDetails copy đúng nghĩa.
- Test cả lần login sau cache hit và test song song; đo số truy vấn load user.
- Định nghĩa chính sách invalidate cache khi password, authority hoặc trạng thái account đổi.
- Không xem erasure là logout, revoke JWT, đổi mật khẩu hay xóa dữ liệu database.
- Không ghi credentials/result đầy đủ vào log/test output, kể cả lúc có lỗi.
- Với nhiều filter chain/parent manager, kiểm tra manager thực sự được áp dụng cho flow cần thay đổi.

**Ghi nhớ:** `eraseCredentialsAfterAuthentication` bảo vệ credentials sau một lần xác thực thành công; **tác động lên object dùng chung phát sinh vì nhiều nơi sở hữu cùng tham chiếu mutable**. Giữ chức năng xóa bí mật và làm rõ ranh giới copy/ownership giúp hệ thống vừa an toàn vừa không làm hỏng cache.

### Tài liệu chính thức

- [Spring Security – Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html): `ProviderManager` và tác động tới cached user object.
- [Spring Security – CredentialsContainer](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/credentials-container.html): contract và ý nghĩa của credential erasure.
- [Spring Security – UserDetails](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/user-details.html): khuyến nghị quản lý password và object dùng trong cache.
- [Spring Security – AbstractAuthenticationToken](https://docs.spring.io/spring-security/site/docs/6.3.0/api/org/springframework/security/authentication/AbstractAuthenticationToken.html): erasure trên credentials, principal, details.
- [Spring Security – ProviderManager](https://docs.spring.io/spring-security/site/docs/6.3.0/api/org/springframework/security/authentication/ProviderManager.html): API cấu hình `eraseCredentialsAfterAuthentication`.
