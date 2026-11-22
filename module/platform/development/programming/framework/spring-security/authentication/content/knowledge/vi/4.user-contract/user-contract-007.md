# UsernameNotFoundException và xử lý tài khoản không tồn tại

Trong Spring Security, `UsernameNotFoundException` là ngoại lệ diễn tả **không tìm được người dùng tương ứng với username** khi tầng tải dữ liệu xác thực thực thi hợp đồng `UserDetailsService.loadUserByUsername(...)`. Tuy vậy, **ngoại lệ xuất hiện trong tầng tải dữ liệu không đồng nghĩa lỗi được công khai cho người đăng nhập**. Với `DaoAuthenticationProvider`, hành vi mặc định là **che giấu lỗi không tìm thấy người dùng dưới dạng `BadCredentialsException`**, giống trường hợp nhập sai mật khẩu. Điều này giúp giảm nguy cơ kẻ tấn công dò tài khoản có tồn tại hay không.

Bài này thuộc nhóm **Hợp đồng người dùng** của Spring Security Authentication. Bạn sẽ hiểu lúc nào nên ném `UsernameNotFoundException`, cách provider xử lý ngoại lệ, cách phân biệt dữ liệu không tồn tại với sự cố hệ thống, những lỗ hổng account enumeration và cách viết code/test Java 17 thực tế.

## 1. Vị trí của UsernameNotFoundException trong luồng xác thực

Một request login username/password đi qua các tầng tương tự:

~~~text
Client: username + password
        |
        v
Filter tạo Authentication chưa xác thực
        |
        v
AuthenticationManager / ProviderManager
        |
        v
DaoAuthenticationProvider
        |
        +--> UserDetailsService.loadUserByUsername(username)
        |       |
        |       +--> Có user: trả UserDetails đầy đủ
        |       |
        |       '--> Không có user:
        |                throw UsernameNotFoundException
        |
        +--> Mặc định hideUserNotFoundExceptions = true
        |       |
        |       '--> Chuyển lỗi không tìm thấy -> BadCredentialsException
        |
        +--> Nếu có user: kiểm tra status và password hash
        |       |
        |       +--> Mật khẩu sai -> BadCredentialsException
        |       '--> Hợp lệ -> Authentication đã xác thực
        |
        v
Filter / AuthenticationEntryPoint / failure handler
        |
        v
Phản hồi HTTP hoặc redirect theo cấu hình
~~~

Sơ đồ trên nêu luồng **khái niệm**. Một ứng dụng có thể có nhiều `AuthenticationProvider` hoặc cơ chế xác thực khác; các lỗi và hành vi chuyển HTTP sẽ phụ thuộc provider/filter thực sự được dùng.

### 1.1. Ngoại lệ nằm trong gói nào?

~~~java
import org.springframework.security.core.userdetails.UsernameNotFoundException;
~~~

`UsernameNotFoundException` là subclass của `AuthenticationException`, do đó có thể được framework xử lý như một lỗi xác thực. Nhưng cách công khai ra API không nhất thiết giữ nguyên tên exception đó.

| Tầng | Khi username không tồn tại | Ý nghĩa |
|---|---|---|
| `AccountRepository` | Ví dụ trả `Optional.empty()` | Kết quả tra cứu dữ liệu, chưa là lỗi bảo mật |
| `UserDetailsService` | Ném `UsernameNotFoundException` | Tuân thủ hợp đồng tải user của Spring Security |
| `DaoAuthenticationProvider` mặc định | Thường chuyển thành `BadCredentialsException` | Không phân biệt công khai “không có user” và “sai password” |
| `AuthenticationManager` | Ném lỗi xác thực cuối cùng nếu không provider nào thành công | Hợp đồng xác thực; chưa phải mã HTTP |
| Login filter/failure handler | Ví dụ trả 401 hoặc redirect với thông báo chung | Cách trình bày lỗi tùy cơ chế web |

**Không suy từ HTTP 401 rằng username chắc chắn không tồn tại.** Cùng một phản hồi có thể đến từ account không có, mật khẩu sai, token sai hoặc chính sách xác thực khác.

## 2. Hợp đồng của UserDetailsService.loadUserByUsername

Giao diện Spring Security:

~~~java
public interface UserDetailsService {
    UserDetails loadUserByUsername(String username)
            throws UsernameNotFoundException;
}
~~~

Đây là **chữ ký rút gọn của giao diện framework**, không phải class cần tự định nghĩa khi dùng Spring Security. Hợp đồng cơ bản:

1. **Input** `username` là giá trị mà cơ chế authentication dùng để tra người dùng; nó không nhất thiết là email, UUID hay trường `name` của bảng dữ liệu.
2. **Tìm thấy user**: trả một `UserDetails` **không phải `null`**, chứa những thông tin framework cần cho xác thực: username, password hash (nếu dùng password), authorities và cờ trạng thái.
3. **Không tìm thấy**: ném `UsernameNotFoundException`. Đừng trả `null`, vì `null` vi phạm contract và có thể bị provider xử lý như lỗi dịch vụ nội bộ.
4. **Tra cứu thất bại do sự cố hệ thống**: không giả vờ “user không tồn tại”. Ví dụ database timeout/connection failure nên đi theo luồng lỗi hạ tầng để vận hành có thể phát hiện và login fail closed.
5. **Không tự xác thực password tại đây** trong trường hợp dùng `DaoAuthenticationProvider` chuẩn: thông thường `UserDetailsService` tải dữ liệu, còn provider/`PasswordEncoder` kiểm tra password. Những kiến trúc provider tùy chỉnh có thể khác.

JavaDoc của `UserDetailsService` cũng đề cập trường hợp người dùng không có `GrantedAuthority` như một khả năng phát sinh `UsernameNotFoundException`. Tuy nhiên, không nên tùy tiện đồng nhất **“user tồn tại nhưng chưa được cấp vai trò”** với **“không có account”** trong mô hình nghiệp vụ. Hãy định nghĩa chính sách rõ: có được xác thực rồi bị từ chối quyền truy cập hay không, hay phải từ chối ngay trong luồng xác thực.

### 2.1. Username không nhất thiết trùng khóa chính

Ví dụ database có:

~~~text
accounts
  id:           4c...UUID
  email:        linh@example.com
  login_name:   linh
  password_hash: $2a$... (giá trị minh họa)
  status:       ACTIVE
~~~

`loadUserByUsername("linh")` có thể tra theo `login_name`. Nếu dùng email làm thông tin đăng nhập, service có thể chuẩn hóa email trước khi tra theo quy tắc đã được xác định. Nhưng ID nội bộ bền vững của account vẫn có thể là UUID. **Tên đăng nhập để tìm dữ liệu** và **định danh nghiệp vụ để liên kết order/tenant/audit** là hai mục đích khác nhau.

Với ứng dụng đa tenant, cùng username có thể xuất hiện trong nhiều tổ chức. Lúc đó lookup phải dùng khóa thực tế như `(tenantId, username)` nếu chính sách cho phép; lấy `tenantId` từ client không có nghĩa nó đáng tin. Đảm bảo xác minh tenant context và membership tại server.

### 2.2. Có nên tự chuẩn hóa username không?

Cần thiết kế nhất quán giữa đăng ký, lưu DB, tìm kiếm và login. Ví dụ lowercase email có thể hợp lý cho một chính sách sản phẩm, nhưng không phải mọi identifier đều có cùng quy tắc case sensitivity. Tránh tự tiện `toLowerCase()` cho mọi username và tránh `trim()`/Unicode normalization nếu chưa thống nhất hợp đồng dữ liệu.

Nên có unique constraint tương ứng với quy tắc lookup. Nếu query trả nhiều account cho một định danh vốn phải duy nhất, đó là lỗi toàn vẹn dữ liệu, **không** nên chọn ngẫu nhiên một record để xác thực.

## 3. Vì sao DaoAuthenticationProvider che giấu lỗi không tìm thấy?

`DaoAuthenticationProvider` kế thừa `AbstractUserDetailsAuthenticationProvider`. Cấu hình quan trọng:

~~~java
provider.setHideUserNotFoundExceptions(true);
~~~

Đây là **đoạn minh họa trong cấu hình provider**, không tự biên dịch độc lập; `provider` phải là instance thích hợp. Giá trị mặc định là `true`, nên thông thường không cần gọi setter.

Theo contract của `AbstractUserDetailsAuthenticationProvider`:

- Nếu username không tồn tại, provider mặc định báo **`BadCredentialsException`**.
- Nếu username tồn tại nhưng password sai, provider cũng báo **`BadCredentialsException`**.
- Đặt `setHideUserNotFoundExceptions(false)` có thể làm `UsernameNotFoundException` được ném ra ngoài khi account không tồn tại; tài liệu Spring Security **coi cách này kém an toàn hơn**.
- Những ngoại lệ trạng thái account như `DisabledException` hoặc `LockedException` là tình huống khác: chúng không mặc nhiên bị biến thành lỗi username không tồn tại. Lớp web vẫn nên hạn chế thông tin lộ qua public response.

### 3.1. Hai thông điệp quan trọng khác nhau

**Thông điệp nội bộ:** “Không tìm thấy user theo username này.”  
**Thông điệp public:** “Thông tin đăng nhập không hợp lệ.”

Tầng dữ liệu xác thực cần biết không có record để dừng lookup hợp lệ, nhưng client không cần biết account có tồn tại. Ngay cả khi bạn dùng generic message, **HTTP status, redirect URL, response body shape, headers và latency** khác nhau vẫn có thể tiết lộ dữ liệu. Vì vậy, giảm account enumeration là công việc của cả chuỗi endpoint, không chỉ một setter.

### 3.2. Tại sao mặc định lại được chọn?

Nếu endpoint công khai trả:

~~~text
Login "linh@example.com"   -> Sai mật khẩu
Login "khongco@example.com" -> Tài khoản không tồn tại
~~~

kẻ tấn công có thể thử một danh sách email để tìm địa chỉ đã đăng ký, sau đó tập trung password spraying, phishing hoặc social engineering. Trả cùng lỗi cho hai trường hợp làm giảm thông tin họ có thể rút ra từ lỗi login.

**Không có nghĩa mọi lỗi phải thành công hoặc tất cả lỗi phải có cùng HTTP 200.** Đăng nhập sai vẫn là thất bại; HTTP 401 hoặc redirect có thể phù hợp. Yêu cầu an toàn là **không tạo khác biệt quan sát được làm lộ việc username có tồn tại**, trừ những quy trình đã xác minh người yêu cầu và thực sự cần thông tin đó.

## 4. Phân biệt lỗi không có account với các trường hợp lân cận

| Tình huống | Nguồn phát hiện | Cách xử lý thường gặp |
|---|---|---|
| Không tìm thấy username | `UserDetailsService`/repository | Ném `UsernameNotFoundException`, để provider che thành `BadCredentialsException` mặc định |
| Username đúng nhưng password sai | `DaoAuthenticationProvider` + encoder | `BadCredentialsException` |
| Account disabled | Kiểm tra trạng thái account | `DisabledException` trong luồng xác thực thích hợp |
| Account locked | Kiểm tra trạng thái account | `LockedException` trong luồng xác thực thích hợp |
| Password hết hạn | Chính sách credential | Ngoại lệ/trạng thái tương ứng, không bịa thành username missing |
| Account chưa xác minh email | Quy tắc nghiệp vụ | Có thể dùng trạng thái không đủ điều kiện login; thiết kế rõ flow xác minh |
| Database timeout hoặc mất kết nối | Repository/DB client | Lỗi dịch vụ nội bộ, không đổi tùy tiện thành “user không tồn tại” |
| Không đủ quyền xem một tài nguyên | Authorization | Không phải `UsernameNotFoundException`; AuthN và AuthZ khác nhau |
| External IdP có subject hợp lệ nhưng chưa liên kết account local | Identity mapping/provisioning | Chính sách liên kết hoặc từ chối riêng; không tự gộp theo email |
| Username tồn tại ở tenant khác | Lookup có phạm vi tenant | Không làm lộ account của tenant khác; áp dụng chính sách lookup đúng |

### 4.1. Không biến outage thành UsernameNotFoundException

Một anti-pattern:

~~~java
try {
    return repository.findByLoginName(username)
            .orElseThrow(...);
} catch (Exception e) {
    throw new UsernameNotFoundException("Not found");
}
~~~

Đây là **mã phản ví dụ**, `repository` và `...` chỉ mang tính sơ đồ, không phải đoạn để biên dịch. Bắt mọi exception làm một khiến DB down, lỗi SQL, mất mạng và record không tồn tại bị trộn lẫn; có thể làm lệch metrics, retry và cảnh báo. Phân biệt `Optional.empty()` với exception của repository; để lỗi dịch vụ hạ tầng được ghi nhận ở nhánh riêng và không cấp authenticated token.

### 4.2. Khi có nhiều AuthenticationProvider

`ProviderManager` có thể thử nhiều provider. Một `BadCredentialsException` từ provider thứ nhất **không luôn** kết thúc toàn bộ chuỗi nếu provider sau có thể xử lý và thành công. Nếu ứng dụng hỗ trợ nhiều realm, phải định nghĩa rõ routing và chống fallback làm suy yếu kiểm tra credential.

Nếu một provider xác thực tài khoản ở domain A và provider khác chấp nhận cùng username nhưng chính sách yếu hơn, việc chuyển lỗi khác nhau không được mở đường bypass. Bảo vệ account enumeration không thay thế chính sách provider ordering.

## 5. Cài đặt UserDetailsService với repository

Một implementation có thể theo cấu trúc:

~~~text
Authentication request
     -> DaoAuthenticationProvider
         -> AccountUserDetailsService
             -> AccountRepository.findByLoginName(...)
                 -> Optional<AccountEntity>
         -> PasswordEncoder.matches(...)
     -> Authentication success / exception
~~~

Ví dụ **đoạn tích hợp Spring Boot**, giả định dự án đã định nghĩa `AccountRepository`, `AccountEntity`, các cột và phép ánh xạ trạng thái:

~~~java
@Service
public class AccountUserDetailsService implements UserDetailsService {

    private final AccountRepository repository;

    public AccountUserDetailsService(AccountRepository repository) {
        this.repository = repository;
    }

    @Override
    public UserDetails loadUserByUsername(String username)
            throws UsernameNotFoundException {

        AccountEntity account = repository.findByLoginName(username)
                .orElseThrow(() ->
                        new UsernameNotFoundException("Invalid credentials"));

        return User.withUsername(account.getLoginName())
                .password(account.getPasswordHash())
                .authorities("profile:read")
                .disabled(!account.isEnabled())
                .accountLocked(account.isLocked())
                .build();
    }
}
~~~

**Đây không phải file Java standalone:** cần imports Spring phù hợp, `AccountRepository`/`AccountEntity` tồn tại và chính sách cấp quyền thực. Chuỗi authority `"profile:read"` chỉ là ví dụ; **không cấp quyền cố định cho mọi account** trong ứng dụng thật. Trạng thái `locked/disabled` cần ánh xạ từ domain theo quy tắc xác thực.

Luồng đúng ở đây là:

1. Repository tìm record theo identifier đã được chuẩn hóa và ràng buộc unique theo chính sách.
2. Nếu `Optional.empty()` thì ném `UsernameNotFoundException`, không trả `null` hoặc fake entity.
3. Nếu tìm thấy thì tạo `UserDetails`; đừng trả thẳng JPA entity chứa mật khẩu, quan hệ lazy và dữ liệu riêng tư nếu không cần.
4. Provider kiểm tra hash bằng `PasswordEncoder` đáng tin (ví dụ BCrypt/Argon2 tùy cấu hình) và status account.
5. Provider/filter quản lý kết quả, context, lỗi và phản hồi public. `UserDetailsService` không được tự gửi email hay HTTP response trong lúc load user.

**Quan trọng:** `UsernameNotFoundException` có thể chứa message do developer đặt để hỗ trợ chẩn đoán, nhưng đừng truyền nguyên message đó ra response public hoặc logs chứa dữ liệu nhạy cảm. Có thể log một mã sự kiện, provider, correlation ID hoặc nội dung đã giảm nhận dạng theo chính sách observability.

## 6. Ví dụ Java 17 chạy được: trực tiếp thấy sự khác biệt giữa service và login

Ta xây dựng ứng dụng **console** dùng Spring Security Core/Crypto để nhìn được ngoại lệ thực tế mà không phụ thuộc response HTTP. Demo cố tình tạo `UserDetails` mới mỗi lần load để tránh lưu một mutable principal có password hash trong một cache dùng chung.

Kịch bản gồm:

- Gọi trực tiếp `loadUserByUsername("ghost")`: nhận `UsernameNotFoundException`.
- Gọi `AuthenticationManager.authenticate(...)` với username `ghost`: nhận **`BadCredentialsException`** vì provider mặc định che giấu tên không tìm thấy.
- Đăng nhập `linh` bằng sai mật khẩu: cũng nhận `BadCredentialsException`.
- Đăng nhập `khoa` (account disabled): nhận `DisabledException`.
- Đăng nhập `linh` bằng mật khẩu đúng: được xác thực và trả principal phù hợp.

### 6.1. Tạo project

~~~text
missing-user-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/example/MissingUserDemo.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'missing-user-demo'
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
    mainClass = 'example.MissingUserDemo'
}
~~~

Phiên bản Spring Security 6.3.8 được cố định cho bài console; trong dự án Spring Boot thật nên ưu tiên dependency management/BOM của bản Boot đang dùng. Để chạy cần JDK 17+, Gradle tương thích và có thể truy cập dependency ở Maven Central khi tải lần đầu.

### 6.2. Mã Java hoàn chỉnh

Tạo `src/main/java/example/MissingUserDemo.java`:

~~~java
package example;

import java.util.List;

import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;

public final class MissingUserDemo {

    public static void main(String[] args) {
        PasswordEncoder encoder = new BCryptPasswordEncoder();
        String hash = encoder.encode("demo-pass");

        UserDetailsService users = username -> {
            if ("linh".equals(username)) {
                // Tạo instance mới ở mỗi lần load, không chia sẻ object
                // UserDetails chứa hash với Authentication result.
                return User.withUsername("linh")
                        .password(hash)
                        .authorities("profile:read")
                        .build();
            }
            if ("khoa".equals(username)) {
                return User.withUsername("khoa")
                        .password(hash)
                        .authorities("profile:read")
                        .disabled(true)
                        .build();
            }
            throw new UsernameNotFoundException("Account not found");
        };

        try {
            users.loadUserByUsername("ghost");
        } catch (UsernameNotFoundException ex) {
            System.out.println("DIRECT ghost -> "
                    + ex.getClass().getSimpleName());
        }

        DaoAuthenticationProvider provider = new DaoAuthenticationProvider();
        provider.setUserDetailsService(users);
        provider.setPasswordEncoder(encoder);
        // Mặc định: hideUserNotFoundExceptions == true.

        AuthenticationManager manager =
                new ProviderManager(List.of(provider));

        login(manager, "ghost", "demo-pass", "ghost");
        login(manager, "linh", "wrong-pass", "linh/wrong");
        login(manager, "khoa", "demo-pass", "khoa/disabled");
        login(manager, "linh", "demo-pass", "linh/correct");
    }

    private static void login(AuthenticationManager manager,
                              String username, String password,
                              String label) {
        Authentication request =
                UsernamePasswordAuthenticationToken.unauthenticated(
                        username, password);
        try {
            Authentication result = manager.authenticate(request);
            System.out.println("LOGIN " + label
                    + " -> OK, name=" + result.getName()
                    + ", authenticated=" + result.isAuthenticated()
                    + ", credentialsNull="
                    + (result.getCredentials() == null));
        } catch (AuthenticationException ex) {
            System.out.println("LOGIN " + label + " -> "
                    + ex.getClass().getSimpleName());
        }
    }
}
~~~

Các class và imports cho chương trình console được khai báo trong cùng một file với `public final class MissingUserDemo`. Nếu ứng dụng chạy bằng một Gradle plugin và version khác, hãy đối chiếu JavaDoc của version đó; demo không tự khởi động web server, không đặt HTTP session và không phát JWT.

### 6.3. Chạy và đọc kết quả

Từ thư mục project có Gradle Wrapper tương thích:

~~~bash
./gradlew run
~~~

Nếu không có wrapper, có thể dùng `gradle run` với Gradle đã cài. Trên PowerShell, wrapper thường chạy bằng `.\gradlew.bat run`.

Đầu ra từ các lệnh `System.out.println` trong chương trình (không tính log Gradle):

~~~text
DIRECT ghost -> UsernameNotFoundException
LOGIN ghost -> BadCredentialsException
LOGIN linh/wrong -> BadCredentialsException
LOGIN khoa/disabled -> DisabledException
LOGIN linh/correct -> OK, name=linh, authenticated=true, credentialsNull=true
~~~

**Tại sao các dòng lại khác nhau?**

1. `users.loadUserByUsername("ghost")` là lời gọi **trực tiếp** tới contract. Service tự ném `UsernameNotFoundException`, không qua provider để đổi loại lỗi.
2. `manager.authenticate(...)` chạy qua `DaoAuthenticationProvider` và cài đặt che giấu mặc định; username ghost được trả về như bad credentials.
3. Với `linh` và mật khẩu sai, account được tìm thấy, nhưng `PasswordEncoder.matches(...)` thất bại: cùng `BadCredentialsException`.
4. Với `khoa`, account tồn tại nhưng disabled. Provider kiểm tra trạng thái và ném `DisabledException`.
5. Với `linh` đúng mật khẩu, manager trả authentication đã xác thực. `ProviderManager` mặc định cố xóa credential khỏi result, nên `result.getCredentials() == null`.

Hash BCrypt sinh salt ngẫu nhiên nên chuỗi hash nội bộ mỗi lần chạy có thể khác, nhưng **stdout nêu trên không phụ thuộc giá trị hash cụ thể**. Bài demo dùng mật khẩu mẫu `demo-pass` chỉ trong môi trường học; không dùng mật khẩu đó cho tài khoản thật.

### 6.4. Nếu tắt hideUserNotFoundExceptions thì sao?

Để khảo sát khác biệt *chỉ trong một test nội bộ*, thêm:

~~~java
provider.setHideUserNotFoundExceptions(false);
~~~

ngay trước khi tạo manager ở chương trình demo. Khi đó lệnh `LOGIN ghost` có thể ném `UsernameNotFoundException` thay vì `BadCredentialsException`; dòng nhập sai mật khẩu của `linh` vẫn là `BadCredentialsException`.

**Không áp dụng mặc định này cho login public.** Cấu hình bộc lộ khác biệt về kiểu lỗi, dễ bị lộ qua exception handler, status, response body hoặc metrics không được cách ly. Nếu cần phân tích loại lỗi ở server, hãy dùng logging/monitoring nội bộ có kiểm soát thay vì đổi contract public.

## 7. Phòng tránh dò sự tồn tại tài khoản (account enumeration)

### 7.1. Login response

Với username/password sai, một API JSON có thể trả thông báo chung:

~~~json
{
  "error": "invalid_credentials",
  "message": "Thông tin đăng nhập không hợp lệ"
}
~~~

Ví dụ JSON này là **minh họa schema API**, không phải phản hồi mặc định của Spring Security. Trong HTTP Basic, client có thể nhận status 401 và header `WWW-Authenticate`; form login thường redirect tới trang thất bại. Chọn đúng giao thức nhưng tránh khác biệt dựa trên “account có tồn tại không”.

Nên kiểm tra cùng một loại response công khai giữa username không tồn tại và password sai: mã HTTP, cấu trúc body, key lỗi, URL redirect, header, cookie, response size và nội dung hiển thị. Đừng đưa exception class, SQL error hoặc username lookup result vào response.

### 7.2. Thời gian phản hồi cũng có thể tiết lộ dữ liệu

Nếu account có thật thì chạy BCrypt, còn account không tồn tại thì return ngay, người đo nhiều request có thể suy ra user nào tồn tại nhờ độ trễ trung bình. `DaoAuthenticationProvider` có logic giảm khác biệt bằng thao tác password encoder trên một hash giả khi không tìm thấy user trong đường xác thực username/password.

Tuy vậy, **đây không phải bảo đảm thời gian cố định tuyệt đối**: cache, database, network, MFA, lockout, application handlers và các query khác vẫn có thể tạo side channel. Đừng xây giải pháp bằng cách đơn giản `Thread.sleep(...)` với thời gian cố định: nó không xóa mọi khác biệt và có thể giúp kẻ tấn công làm quá tải server.

Biện pháp thực tế gồm rate limiting theo nhiều tín hiệu, monitoring, chính sách chống brute-force/password spraying, chống spam, kiểm soát chi phí BCrypt, và kiểm thử latency trong môi trường gần production mà không ghi mật khẩu thật.

### 7.3. Các endpoint khác ngoài login

Kể cả khi login đã che lỗi, các endpoint sau vẫn có thể tiết lộ account:

| Endpoint/quy trình | Câu trả lời có nguy cơ | Cách tiếp cận an toàn hơn |
|---|---|---|
| Quên mật khẩu | “Email này chưa đăng ký” | “Nếu địa chỉ hợp lệ và có tài khoản, chúng tôi sẽ gửi hướng dẫn” |
| Gửi lại email xác minh | “Không thấy tài khoản” | Thông báo chung, giới hạn tần suất gửi |
| Đăng ký | “Email đã được dùng” | Xây policy phù hợp và giảm khả năng dò hàng loạt; không tiết lộ thêm thông tin |
| Mời thành viên | “User X đã tồn tại trong hệ thống” | Hạn chế theo quyền người mời và phạm vi tenant |
| API kiểm tra username còn trống | Dò từng tên trong danh sách | Giới hạn/kiểm soát truy cập và cân nhắc lại nhu cầu public |
| OAuth account linking | Gộp theo email chưa xác minh | Xác thực nguồn/subject và quy trình link có kiểm soát |

Với quên mật khẩu, **thông điệp chung không đủ** nếu chỉ account tồn tại mới gửi mail và chi phí/thời gian/cookie phản hồi khác nhau rõ rệt; cần kiểm thử toàn bộ flow. Token reset phải có thời hạn, dùng một lần hoặc có cơ chế chống dùng lại, và được lưu/đối chiếu an toàn.

### 7.4. Log/audit ở server

Không in raw password, bearer token, password hash hoặc toàn bộ `Authentication` vào log. Với user không tồn tại, nên ghi một event có correlation ID, loại flow, mã lỗi tổng quát, tên provider và context được cho phép theo chính sách dữ liệu; cân nhắc băm/giảm định danh nếu cần phân tích tấn công trên username. **Log nội bộ cũng cần chính sách truy cập, retention và chống lộ PII.**

## 8. Mapping sang HTTP và cách xử lý exception

`UsernameNotFoundException` **không có nghĩa tự động trả HTTP 404**. Nó là lỗi ở contract tra người dùng trong quá trình authentication, không phải “resource REST không tồn tại”. Trả 404 cho username vắng mặt nhưng 401 cho sai password thường tạo account enumeration.

Tùy cấu hình:

- **HTTP Basic**: thành phần authentication entry point có thể trả 401, có `WWW-Authenticate`.
- **Form login**: failure handler thường điều hướng tới trang login với tham số/thông báo thất bại chung.
- **Custom login JSON**: có thể xử lý `AuthenticationException` trong controller/filter phù hợp và ánh xạ sang lỗi public thống nhất.
- **Session/JWT**: cấp session/token chỉ khi xác thực hoàn tất; không cấp token cho user bị từ chối.

Đoạn minh họa *trong một endpoint custom*:

~~~java
try {
    Authentication verified = authenticationManager.authenticate(request);
    // Tiếp tục quy trình success: lập context/session hoặc phát token
} catch (AuthenticationException ex) {
    // Chỉ trả thông điệp công khai chung, không trả ex.getMessage().
    // Việc viết response thực tế tùy filter/controller.
}
~~~

Đây là **mã phác thảo luồng**, không phải controller Java hoàn chỉnh; biến `authenticationManager` và `request` cần được khai báo trong application. Đừng tự bắt mọi exception thành “sai mật khẩu”: sự cố hạ tầng cần được quan sát, cảnh báo và xử lý fail closed, còn client không nhận stacktrace/nội dung nhạy cảm.

### 8.1. Trường hợp đặc biệt: gọi service từ tầng nghiệp vụ

`UserDetailsService` là contract phục vụ **authentication username/password**. Không nên gọi `loadUserByUsername` từ endpoint `GET /users/{username}` rồi biến `UsernameNotFoundException` thành business 404/200 một cách tự động. Endpoint nghiệp vụ cần domain service và quy tắc phân quyền/ẩn dữ liệu riêng.

Ví dụ: người dùng đã đăng nhập nhưng không được phép xem profile của người khác. Đây là vấn đề **authorization**, không phải username lookup trong login. Tách hai tầng giúp tránh rò dữ liệu và phản hồi sai.

## 9. Những lỗi thường gặp

**Lỗi 1 — Trả `null` khi không tìm thấy user.**  
Sai hợp đồng `UserDetailsService`; có thể dẫn đến lỗi nội bộ thay vì nhánh credentials thất bại. **Sửa:** ném `UsernameNotFoundException` rõ ràng.

**Lỗi 2 — Trả nguyên exception cho client.**  
`UsernameNotFoundException: user X does not exist` dễ làm lộ danh sách tài khoản. **Sửa:** giữ provider che lỗi mặc định và chuẩn hóa public response.

**Lỗi 3 — `setHideUserNotFoundExceptions(false)` để debug lâu dài.**  
Có thể khiến endpoint login phân biệt user không tồn tại với password sai. **Sửa:** debug qua test/log an toàn, không đổi policy công khai.

**Lỗi 4 — Catch mọi lỗi repository rồi ném UsernameNotFoundException.**  
Che mất outage, làm lỗi vận hành khó phát hiện. **Sửa:** chỉ ném khi lookup thành công nhưng không có record; xử lý lỗi hạ tầng riêng.

**Lỗi 5 — Tạo fake user với password mặc định để “đỡ lỗi”.**  
Nếu account giả có cấu hình sai, có thể vô tình đăng nhập được hoặc kích hoạt phân quyền không mong muốn. **Sửa:** dùng đúng exception contract; phòng timing do provider/security design chịu trách nhiệm.

**Lỗi 6 — Dùng HTTP 404 cho username missing trong login.**  
Làm lộ account enumeration. **Sửa:** error mapping cùng loại với sai password theo giao thức login.

**Lỗi 7 — Cho rằng cùng BadCredentialsException nghĩa là đã chống dò account hoàn toàn.**  
Latency, reset password, đăng ký, MFA và account lockout vẫn có thể rò dữ liệu. **Sửa:** kiểm thử và bảo vệ mọi endpoint liên quan.

**Lỗi 8 — Tự gán `UsernameNotFoundException` cho thiếu quyền.**  
Thiếu role/ownership là authz; có user nhưng không đủ quyền không đồng nghĩa user vắng mặt. **Sửa:** tách authentication khỏi resource authorization.

**Lỗi 9 — Login theo email nhưng unique/case rules không thống nhất.**  
Một username có thể trỏ nhiều record hoặc không tìm được người dùng hợp lệ. **Sửa:** thiết kế identifier normalization và unique constraint nhất quán.

**Lỗi 10 — Log thẳng username/password hash để điều tra.**  
Tạo rủi ro dữ liệu nhạy cảm ở log/CI. **Sửa:** dùng correlation ID và telemetry tối thiểu, có phân quyền.

## 10. Kiểm thử cần có

| Kịch bản | Kiểm tra mong đợi |
|---|---|
| Gọi trực tiếp `loadUserByUsername` với user tồn tại | Trả `UserDetails` không null, đúng username, hash/flags/authorities theo policy |
| Gọi trực tiếp với user vắng mặt | Ném `UsernameNotFoundException` |
| Qua `DaoAuthenticationProvider` mặc định với user vắng mặt | `BadCredentialsException` |
| Qua provider với user tồn tại nhưng password sai | Cùng loại lỗi public/bên ngoài như user vắng mặt |
| Bật hide=false trong unit test | Đã hiểu khác biệt và không để lọt vào login public |
| Account disabled/locked | Không cấp authentication thành công; phản hồi public được kiểm soát |
| Repository bị timeout/mất kết nối | Không biến thành account missing, không cấp token, có cảnh báo server |
| Lookup tên khác hoa/thường | Đúng chính sách normalization và unique |
| Multi-tenant trùng username | Không tìm/lộ account ngoài tenant được phép |
| Đăng ký/quên mật khẩu | Không dễ dàng dò tồn tại account qua body/headers/latency |
| Gửi nhiều login thất bại | Rate limiting, giám sát brute-force, không lộ secret |
| Nhiều provider hỗ trợ cùng loại token | Không bypass kiểm tra qua fallback yếu |
| Đã xác thực nhưng thiếu quyền | Authorization từ chối độc lập với user lookup |
| Cache và đổi trạng thái account | Không sử dụng thông tin đã cũ để cho phép đăng nhập trái chính sách |

### 10.1. Câu hỏi tự ôn tập

**1. `UserDetailsService.loadUserByUsername` trả gì nếu không tìm thấy username?**  
Ném `UsernameNotFoundException`; không trả `null`.

**2. Vì sao login với username không tồn tại thường báo `BadCredentialsException`?**  
Vì `AbstractUserDetailsAuthenticationProvider` che giấu `UsernameNotFoundException` theo mặc định để giảm dò sự tồn tại tài khoản.

**3. Nếu đặt `hideUserNotFoundExceptions=false`, điều gì thay đổi?**  
Provider có thể phát ra `UsernameNotFoundException` trực tiếp. Dùng như vậy cho public login có thể làm lộ thông tin; không nên đổi tùy tiện.

**4. Database bị lỗi kết nối có nên ném `UsernameNotFoundException` không?**  
Không. Account lookup thất bại vì outage khác với kết quả tra cứu hợp lệ nhưng rỗng.

**5. Username đúng nhưng không có quyền vào tài nguyên thì có nên coi là user không tồn tại?**  
Không. Cần xử lý authorization, không dùng username lookup để thay thế.

**6. Tất cả login failures trả cùng JSON có đủ chống account enumeration?**  
Chưa đủ: còn timing, headers, redirect, các endpoint reset/registration và chính sách lockout.

**7. Tại sao không trả HTTP 404 cho username không tồn tại khi đăng nhập?**  
Vì nó có thể tạo phản hồi khác với nhập sai password và tiết lộ user nào đã đăng ký.

**8. Với OIDC/JWT, có luôn dùng UserDetailsService và UsernameNotFoundException?**  
Không. Đó là contract điển hình của username/password qua DaoAuthenticationProvider. Bearer JWT/OIDC có chuỗi provider/identity mapping riêng; không ép cơ chế nào cũng dùng cùng exception.

## 11. Checklist áp dụng

- [ ] `loadUserByUsername` trả `UserDetails` đầy đủ hoặc ném `UsernameNotFoundException`, không trả `null`.
- [ ] Chỉ xem `Optional.empty()` là lookup không tìm thấy; xử lý outage và lỗi toàn vẹn dữ liệu bằng nhánh khác.
- [ ] Giữ `hideUserNotFoundExceptions=true` cho login username/password public trừ khi có lý do bảo mật được thẩm định.
- [ ] Dùng public error chung cho username vắng mặt và password sai; không lộ exception message.
- [ ] Thống nhất normalization, uniqueness, tenant scope và mô hình định danh.
- [ ] Dùng password encoder mạnh và chính sách rate limit; kiểm thử timing, log và endpoint phụ trợ.
- [ ] Không đưa raw password/hash/token hoặc thông tin riêng tư vào log, error body hay URL.
- [ ] Test đủ unknown user, wrong password, disabled/locked, storage outage và nhiều provider.
- [ ] Tách authentication lookup khỏi business user lookup và authorization.
- [ ] Khi dùng session/JWT, chỉ cấp credential phiên sau khi xác thực thành công và đáp ứng chính sách account.

**Ghi nhớ:** `UsernameNotFoundException` là **tín hiệu nội bộ hợp lệ của hợp đồng tải người dùng**. Nhưng login công khai cần **không cho kẻ tấn công dễ phân biệt “tài khoản không tồn tại” với “mật khẩu sai”**. Dùng đúng contract ở `UserDetailsService`, giữ cơ chế che lỗi mặc định ở `DaoAuthenticationProvider` và bảo vệ toàn bộ luồng login/khôi phục/đăng ký thay vì chỉ đổi một câu thông báo.

### Tài liệu chính thức

- [Spring Security — UserDetailsService JavaDoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/userdetails/UserDetailsService.html): contract `loadUserByUsername`, giá trị trả về không null và `UsernameNotFoundException`.
- [Spring Security — AbstractUserDetailsAuthenticationProvider JavaDoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/dao/AbstractUserDetailsAuthenticationProvider.html): `setHideUserNotFoundExceptions` và lựa chọn mặc định.
- [Spring Security — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/dao-authentication-provider.html): tải user và kiểm tra password.
- [Spring Security — Username/Password Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/): chuỗi xác thực và cấu hình với `AuthenticationManager`.
- [Spring Security — UsernameNotFoundException JavaDoc](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/core/userdetails/UsernameNotFoundException.html): ý nghĩa ngoại lệ và phân cấp `AuthenticationException`.
