# Xóa credentials sau xác thực và giới hạn vòng đời thông tin nhạy cảm

Mai đăng nhập vào một ứng dụng Spring Security bằng tên người dùng và mật khẩu. Để xác minh Mai, chương trình phải nhận mật khẩu trong thời gian ngắn, chuyển nó cho thành phần xác thực và so sánh với password hash đã lưu. Nhưng **sau khi xác thực xong, chương trình có còn cần giữ mật khẩu ấy trong `Authentication`, `SecurityContext` hoặc session không?**

Trong phần lớn luồng đăng nhập bằng mật khẩu, câu trả lời là **không**. Giữ raw password lâu hơn cần thiết làm tăng thiệt hại nếu có log sai, heap dump, session serialization, lỗi phân quyền hoặc một đối tượng bị vô tình chuyển sang tầng khác. Spring Security có cơ chế dọn dẹp liên quan `ProviderManager`, `CredentialsContainer` và `eraseCredentials()` để giảm thời gian tham chiếu tới các bí mật đã hoàn thành nhiệm vụ.

Tuy nhiên, cần hiểu chính xác giới hạn: **xóa credentials khỏi một object Java không đồng nghĩa mọi bản sao của dữ liệu đã biến mất khỏi RAM**. Một `String` bất biến, bản sao trong request, log, cache, token hoặc vùng nhớ khác có thể vẫn tồn tại. Đó là lý do bài học này kết hợp **cơ chế framework** với **thiết kế vòng đời dữ liệu nhạy cảm từ lúc nhận đến lúc hủy**.

Mục tiêu: sau bài này, bạn phân biệt được raw credentials với password hash và identity, biết khi nào Spring Security gọi `eraseCredentials()`, tránh lỗi cache `UserDetails`, biết xử lý custom authentication an toàn, và có thể tự chạy một ví dụ Java 17+ để quan sát credentials trước/sau xác thực.

## 1. Credentials là gì? Không phải mọi thuộc tính trong Authentication đều cần xóa

Trong Spring Security, `Authentication` mô tả **một yêu cầu xác thực** hoặc **danh tính đã được xác thực**. Những phần thường gặp:

| Thành phần | Vai trò | Ví dụ | Có nên giữ sau khi xác thực? |
| --- | --- | --- | --- |
| `principal` | Ai đang được nhận diện | `UserDetails`, username, JWT, custom principal | Giữ **định danh tối thiểu cần thiết**; loại bỏ secret không cần thiết |
| `credentials` | Bằng chứng dùng để chứng minh danh tính | Password, token bearer, assertion | Thường **không giữ raw secret** sau khi kiểm tra; xem nhu cầu từng cơ chế |
| `authorities` | Các quyền mà provider cấp cho principal | `ROLE_USER`, `DOC_READ` | Có thể cần cho authorization, nhưng vẫn phải xử lý quyền bị thu hồi |
| `details` | Metadata tùy cơ chế/request | IP, session ID hoặc thông tin thiết bị nếu được cấu hình | Chỉ giữ dữ liệu có mục đích rõ, hạn chế riêng tư |
| `isAuthenticated()` | Trạng thái của kết quả xác thực | `true` sau khi provider tin bằng chứng | Không phải credentials; không tự chứng minh quyền với từng tài nguyên |

**Credentials** là thứ được đưa ra để chứng minh quyền sử dụng danh tính. Với form login, đó thường là *mật khẩu gốc* vừa nhập. Với JWT Resource Server, bearer token đóng vai trò bằng chứng của request; với OAuth2/OIDC, cũng có thể có authorization code, refresh token, client secret hoặc assertion theo flow. Với MFA có thể có OTP hoặc recovery code.

**Không đồng nhất ba đối tượng sau:**

- **Raw password:** bí mật vừa được người dùng cung cấp, nên sống rất ngắn trong request/xử lý xác thực.
- **Password hash được lưu:** dữ liệu để xác minh mật khẩu sau này, phải tồn tại bền vững trong kho credentials được bảo vệ. Hash vẫn nhạy cảm và không nên lộ ra client/log.
- **Authenticated identity:** ID và quyền cần thiết để nhận diện người gọi trong request hiện tại hoặc session, về nguyên tắc không cần giữ raw password.

Nếu `UserDetails` có `getPassword()`, thông thường đó là **hash đã lưu**, không phải raw password. Việc Spring Security xóa trường password khỏi **bản sao `UserDetails` trên principal** không có nghĩa xóa hash khỏi database. Phân biệt này rất quan trọng khi đọc code và debug.

## 2. Vòng đời mong muốn của mật khẩu trong một lần đăng nhập

Có thể hình dung một luồng servlet dùng username/password:

~~~text
1. Browser gửi POST /login qua HTTPS
        username + raw password
                  |
                  v
2. UsernamePasswordAuthenticationFilter
        tạo Authentication request chưa xác thực
        principal=username, credentials=raw password
                  |
                  v
3. AuthenticationManager (thường ProviderManager)
        gọi AuthenticationProvider thích hợp
                  |
                  v
4. DaoAuthenticationProvider
        UserDetailsService lấy user + password hash
        PasswordEncoder.matches(raw password, hash)
                  |
             đúng | sai
                  |------------------------------------+
                  v                                    |
5. Authentication thành công                           |
        principal + authorities                        |
        credentials có thể còn tạm thời                |
                  |                                    v
                  v                         AuthenticationException
6. ProviderManager dọn credentials              xử lý lỗi/cleanup
        nếu return Authentication hỗ trợ
        CredentialsContainer
                  |
                  v
7. Filter xử lý SecurityContext / session
        giữ identity + quyền phù hợp
        không cần raw password
                  |
                  v
8. Controller/service thực hiện authorization
        chỉ dùng ID/quyền, không dùng password
~~~

**Điểm quan trọng về thời điểm:** dọn credentials của `ProviderManager` xảy ra sau khi một provider đã xác thực **thành công** và trả về `Authentication`. Không mặc định rằng các dữ liệu của **request ban đầu**, các bản sao trong servlet request body, log hay các đối tượng đang được nơi khác giữ tham chiếu cũng được dọn.

Một custom controller gọi `AuthenticationManager` trực tiếp phải chịu trách nhiệm quản lý input của chính nó. Một custom provider cũng phải quyết định đối tượng kết quả chứa gì. Đừng nghĩ chỉ cần bật Spring Security thì mọi vùng nhớ có password sẽ tự được làm sạch.

## 3. Cơ chế mặc định của ProviderManager

Trong Spring Security Servlet, `AuthenticationManager` là hợp đồng:

~~~java
Authentication authenticate(Authentication authentication)
        throws AuthenticationException;
~~~

Triển khai thường dùng là `ProviderManager`, điều phối một hoặc nhiều `AuthenticationProvider`.

Khi provider trả về kết quả thành công, `ProviderManager` **mặc định cố gắng xóa credentials** của `Authentication` kết quả nếu nó triển khai `CredentialsContainer`. Tương ứng với cấu hình:

~~~java
// Fragment khi bạn tự tạo ProviderManager.
ProviderManager manager = new ProviderManager(provider);

boolean enabled = manager.isEraseCredentialsAfterAuthentication();
// Mặc định là true.
~~~

Trong thư viện có thuộc tính:

~~~java
manager.setEraseCredentialsAfterAuthentication(false);
~~~

**Đây là ví dụ về công tắc có tồn tại, KHÔNG phải khuyến nghị tắt nó.** Tắt dọn credentials có thể làm raw password hoặc một secret khác còn trong `Authentication`/session lâu hơn cần thiết. Chỉ cân nhắc khi đã hiểu nguyên nhân kỹ thuật, rủi ro, vòng đời dữ liệu và có một giải pháp bảo vệ tương đương; với ứng dụng bình thường nên giữ mặc định.

Ở mức khái niệm, công việc hậu xác thực gần giống:

~~~java
// Pseudocode mô tả hành vi; KHÔNG copy để thay thế ProviderManager.
Authentication result = provider.authenticate(input);

if (result != null && eraseAfterAuthentication
        && result instanceof CredentialsContainer container) {
    container.eraseCredentials();
}

return result;
~~~

Lưu ý pseudocode không biểu diễn đầy đủ việc thử nhiều provider, parent manager, các exception và event; nó chỉ cho thấy **đối tượng nào được dọn** và **khi nào**.

Sau khi provider trả kết quả thành công, bộ lọc xử lý việc đưa `Authentication` vào `SecurityContext` và lưu/khôi phục context theo cơ chế đã cấu hình. Nếu kết quả chứa ít bí mật hơn, nguy cơ lộ trong session/serialization giảm xuống.

### Tại sao cơ chế này có giá trị?

Nếu một `UsernamePasswordAuthenticationToken` còn chứa raw password, và ứng dụng lưu nó trong session, giá trị bí mật có thể tồn tại đến khi session hết hạn hoặc bị vô tình đưa vào cache, debug, crash dump. Xóa credentials trước khi giữ `Authentication` lâu dài giúp giảm bề mặt rủi ro.

Nhưng kết quả dọn còn phụ thuộc **kiểu `Authentication` trả về** và việc `eraseCredentials()` có được triển khai đúng không. Không phải mọi object tùy biến đều tự hiểu việc xóa secret bên trong nó.

## 4. CredentialsContainer và phương thức eraseCredentials()

Interface nằm ở:

~~~java
org.springframework.security.core.CredentialsContainer
~~~

Hợp đồng rất nhỏ:

~~~java
public interface CredentialsContainer {
    void eraseCredentials();
}
~~~

Đây là chữ ký giản lược để học. Interface báo rằng object có thông tin nhạy cảm cần được giải phóng, và `eraseCredentials()` là nơi thực hiện việc đó.

Những lớp Spring Security quen thuộc có triển khai interface này gồm:

- `UsernamePasswordAuthenticationToken`.
- `AbstractAuthenticationToken` và nhiều lớp con.
- `org.springframework.security.core.userdetails.User`.
- Nhiều loại token/đối tượng xác thực của từng cơ chế, tùy phiên bản.

Cách gọi có tính **lan truyền**: `AbstractAuthenticationToken.eraseCredentials()` kiểm tra `credentials`, `principal` và `details`; nếu object con triển khai `CredentialsContainer`, nó gọi `eraseCredentials()` cho object ấy. `UsernamePasswordAuthenticationToken` cũng xóa tham chiếu đến trường credentials của chính token.

Ví dụ `Authentication` có thể là:

~~~text
UsernamePasswordAuthenticationToken
  principal = UserDetails(User)
    username = "mai"
    password = "{bcrypt}..."
    authorities = [ROLE_USER]
  credentials = "raw-password-vua-nhap"
  details = WebAuthenticationDetails(...)
~~~

Sau khi result token được dọn phù hợp:

~~~text
UsernamePasswordAuthenticationToken
  principal = UserDetails(User)
    username = "mai"
    password = null
    authorities = [ROLE_USER]
  credentials = null
  details = thông tin không nhạy cảm hoặc metadata đã được quản lý
~~~

Đây là **ví dụ cho kiểu `User` của Spring Security**, không phải cam kết mọi `UserDetails` sẽ có `password=null`. Một custom `UserDetails` chỉ triển khai `UserDetails` mà không có `CredentialsContainer` có thể tiếp tục giữ hash bên trong principal ngay cả khi token đã xóa `credentials`.

### Quan trọng: eraseCredentials không xóa mọi trường

`eraseCredentials()` **không phải lệnh xóa toàn bộ principal hoặc các authorities**. Danh tính và quyền vẫn có thể cần cho những lần gọi tiếp theo. Nó cũng không tự xóa object `details` nếu object ấy không triển khai hợp đồng xóa phù hợp.

Do đó, nếu một custom principal có `String accessToken`, `String otp` hoặc `String passwordHash` nhưng không triển khai dọn dẹp, bí mật vẫn có thể tồn tại. Hãy chủ động giảm dữ liệu trong principal thay vì phụ thuộc vào một tên phương thức.

## 5. Ví dụ Java 17+ chạy được: quan sát dọn credentials sau xác thực

Ví dụ standalone dùng các lớp Spring Security thật. Mục tiêu không phải xây dựng website, mà là **quan sát kết quả `ProviderManager.authenticate`** với username/password.

Chương trình kiểm tra:

1. `ProviderManager` mặc định bật dọn credentials.
2. Xác thực bằng password hợp lệ trả kết quả `authenticated=true`.
3. `Authentication.getCredentials()` của **kết quả** thành `null`.
4. `UserDetails.getPassword()` trên principal kiểu `User` cũng thành `null`.
5. Request token ban đầu được dọn riêng bằng `finally`.
6. Lần đăng nhập tiếp theo vẫn thành công vì `UserDetailsService` tạo **một object mới mỗi lần**, không dùng lại principal đã bị dọn.

### 5.1. Tạo project Gradle

Cấu trúc:

~~~text
credential-lifetime-demo/
  build.gradle
  src/main/java/CredentialLifetimeDemo.java
~~~

Tạo `build.gradle`:

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.security:spring-security-core:7.1.2'
    implementation 'org.springframework.security:spring-security-crypto:7.1.2'
}

application {
    mainClass = 'CredentialLifetimeDemo'
}
~~~

Ví dụ cố định cùng một bản Spring Security stable đã phát hành để dễ thực hành độc lập; Java yêu cầu từ 17. Trong dự án Spring Boot thật, hãy dùng `spring-boot-starter-security` và để Spring Boot BOM quản lý phiên bản Security, thay vì copy những dòng version riêng.

### 5.2. Tệp Java đầy đủ

Tạo `src/main/java/CredentialLifetimeDemo.java`:

~~~java
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;

public class CredentialLifetimeDemo {

    public static void main(String[] args) {
        PasswordEncoder encoder = new BCryptPasswordEncoder();

        // Chỉ là mật khẩu giả dùng trong ví dụ, không dùng ở sản phẩm thật.
        String storedHash = encoder.encode("demo-password");

        // Tạo UserDetails MỚI cho mỗi lần gọi; không trả lại một
        // User object đã bị eraseCredentials() ở lần login trước.
        UserDetailsService users = username -> {
            if (!"mai".equals(username)) {
                throw new UsernameNotFoundException("Unknown username");
            }
            return User.withUsername("mai")
                    .password(storedHash)
                    .roles("USER")
                    .build();
        };

        DaoAuthenticationProvider provider =
                new DaoAuthenticationProvider(users);
        provider.setPasswordEncoder(encoder);

        ProviderManager manager = new ProviderManager(provider);
        System.out.println("erase-enabled="
                + manager.isEraseCredentialsAfterAuthentication());

        UsernamePasswordAuthenticationToken firstInput =
                UsernamePasswordAuthenticationToken.unauthenticated(
                        "mai", "demo-password");

        Authentication firstResult;
        try {
            firstResult = manager.authenticate(firstInput);
        } finally {
            // Manager dọn RESULT; caller xử lý INPUT do mình giữ.
            firstInput.eraseCredentials();
        }

        UserDetails firstPrincipal =
                (UserDetails) firstResult.getPrincipal();

        System.out.println("first-authenticated="
                + firstResult.isAuthenticated());
        System.out.println("result-credentials-empty="
                + (firstResult.getCredentials() == null));
        System.out.println("principal-password-empty="
                + (firstPrincipal.getPassword() == null));
        System.out.println("input-credentials-empty="
                + (firstInput.getCredentials() == null));

        UsernamePasswordAuthenticationToken secondInput =
                UsernamePasswordAuthenticationToken.unauthenticated(
                        "mai", "demo-password");
        try {
            Authentication second = manager.authenticate(secondInput);
            System.out.println("second-authenticated="
                    + second.isAuthenticated());
        } finally {
            secondInput.eraseCredentials();
        }
    }
}
~~~

Với JDK 17+ và Gradle phù hợp, từ thư mục chứa `build.gradle` chạy:

~~~bash
java -version
gradle run --quiet
~~~

Đầu ra do chính các `println` tạo ra:

~~~text
erase-enabled=true
first-authenticated=true
result-credentials-empty=true
principal-password-empty=true
input-credentials-empty=true
second-authenticated=true
~~~

**Đây là đầu ra có thể suy ra từ API được dùng**, không phụ thuộc chuỗi bcrypt ngẫu nhiên, nên không in giá trị hash cụ thể. Chương trình đã tách rõ đối tượng input, kết quả và principal.

Giải thích:

- `DaoAuthenticationProvider` dùng `PasswordEncoder.matches` kiểm tra mật khẩu với `storedHash`.
- `ProviderManager` nhận `Authentication` thành công rồi gọi dọn credentials trên **kết quả** mặc định.
- `UsernamePasswordAuthenticationToken` bỏ tham chiếu tới raw credentials trong kết quả; principal là `User`, nên `User.eraseCredentials()` bỏ tham chiếu tới password hash trên principal.
- `firstInput` là object khác và được ứng dụng chủ động gọi `eraseCredentials()` trong `finally`.
- `storedHash` vẫn còn ở biến nguồn dùng làm cơ sở xác minh (mô phỏng kho lưu trữ). Lần login sau được nạp `User` mới từ nó, nên tiếp tục thành công.

**Giới hạn quan trọng:** password demo là `String` literal trong class Java. Lệnh `eraseCredentials()` dọn **tham chiếu của object đã chọn**, không bảo đảm xóa các byte/ký tự tạo thành `String` khỏi mọi vùng bộ nhớ. Trong production, không hardcode mật khẩu; sử dụng HTTPS, nguồn dữ liệu và cách giữ bí mật phù hợp.

### 5.3. Vì sao không dùng lại cùng một User object?

Nếu viết `UserDetailsService` kiểu sau, bạn có thể gặp lỗi:

~~~java
// VÍ DỤ CÓ VẤN ĐỀ KHI DÙNG LẠI CÙNG MỘT ĐỐI TƯỢNG:
UserDetails oneSharedUser = User.withUsername("mai")
        .password(storedHash)
        .roles("USER")
        .build();

UserDetailsService users = username -> oneSharedUser;
~~~

Sau lần login thành công đầu tiên, `ProviderManager` có thể khiến password trong `oneSharedUser` bị xóa qua cùng tham chiếu. Lần login sau, provider cần hash để kiểm tra nhưng nhận object đã bị biến đổi. Điều này có thể làm xác thực thất bại hoặc dẫn tới lỗi, tùy implementation.

Trong ví dụ chạy được ở trên, `users` trả **một `User` mới** mỗi lần. Cần phân biệt:

~~~text
ĐÚNG VỀ RANH GIỚI OBJECT:
  Kho lưu trữ có password hash bền vững
          |
  Mỗi login tạo UserDetails bản mới
          |
  ProviderManager erase trên principal bản mới
          |
  Kho lưu trữ không bị thay đổi

CÓ NGUY CƠ:
  Cache có UserDetails instance dùng chung
          |
  Login lấy đúng instance ấy
          |
  Result principal giữ cùng tham chiếu
          |
  ProviderManager erase -> cache bị sửa theo
          |
  Login sau không còn password hash để kiểm tra
~~~

Đó là lỗi **đồng nhất ownership/reference** giữa một object được phép dọn và một object cần tồn tại để xác minh lần sau. Đây không phải bằng chứng phải tắt cơ chế xóa bí mật; giải pháp nên là tách object vòng đời ngắn khỏi dữ liệu cache/persistence có mục đích khác.

## 6. Caching UserDetails: nơi lỗi dọn credentials thường bộc lộ

Ứng dụng lớn có thể cache user để giảm truy vấn database. Đây là tình huống đáng chú ý vì `User` của Spring Security là object **mutable** và triển khai `CredentialsContainer`.

Ví dụ:

~~~text
cache["mai"] -> User(username="mai", password="{bcrypt}...", ...)
                       |
                       +--- UserDetailsService trả cùng object
                                   |
                                   v
                             Authentication principal
                                   |
                                   v
                        ProviderManager.eraseCredentials()
                                   |
                                   v
cache["mai"].password == null  (do cùng tham chiếu object)
~~~

Hậu quả có thể là: đăng nhập lần đầu thành công, lần thứ hai lỗi dù người dùng nhập đúng mật khẩu. Việc lỗi xảy ra ngay hay sau TTL phụ thuộc cache implementation và flow xác thực.

Các cách giải quyết hợp lý:

1. **Lấy từ repository và tạo UserDetails bản mới** cho từng lần xác thực khi chi phí phù hợp. Demo ở phần 5 dùng cách này.
2. **Nếu dùng cache, trả một bản sao tách biệt** khỏi object được cache, trong đó các dữ liệu cần xác minh được copy có kiểm soát; object trả vào `Authentication` có thể bị dọn mà không thay cache.
3. Với custom `AuthenticationProvider`, **tạo authenticated result chỉ chứa ID/authorities**, không tham chiếu tới `UserDetails` cache có password hash. Cơ chế xử lý credentials ở input vẫn phải được quan tâm.
4. Nếu thiết kế đòi hỏi một lifetime khác, đánh giá kỹ cách sử dụng `setEraseCredentialsAfterAuthentication(false)`. Đây là một trade-off về giữ bí mật lâu hơn, **không nên là giải pháp mặc định** cho cache dùng chung.

Khi dùng `User.withUserDetails(existing)`, hãy kiểm tra xem object mới và các thành phần lồng nhau đã thực sự được copy phù hợp chưa; đừng nhầm một bản sao wrapper với một bản sao sâu của mọi object nhạy cảm.

### Cache giữ password hash có an toàn tuyệt đối không?

Không. Password hash là dữ liệu để kiểm chứng mật khẩu, vẫn nhạy cảm nếu cache bị đọc trái phép, debug hoặc dump. Cần kiểm soát truy cập, mã hóa kênh/kho nếu phù hợp, TTL và vòng đời cache. Việc có cache không cho phép đưa nguyên password hash vào session hay trả API.

Có thể tạo một cache riêng cho hồ sơ và authorities **không chứa hash**, còn việc xác thực mật khẩu truy vấn kho credentials chuyên trách. Kiến trúc cụ thể phụ thuộc tải, SLA và bảo mật, nhưng nên phân rõ nơi nào **cần hash để xác minh** và nơi nào **chỉ cần danh tính**.

## 7. Custom UserDetails: triển khai CredentialsContainer thế nào?

Nếu dự án tự tạo một lớp `UserDetails` có password hash, nên xem xét triển khai `CredentialsContainer` để dọn đúng trường trên bản dùng cho authentication.

Mảnh code minh họa phần liên quan (các phương thức `UserDetails` khác cần được triển khai trong class thật):

~~~java
import org.springframework.security.core.CredentialsContainer;
import org.springframework.security.core.userdetails.UserDetails;

public final class AccountUserDetails
        implements UserDetails, CredentialsContainer {

    private String passwordHash;
    // Những field khác: username, authorities, trạng thái...

    @Override
    public String getPassword() {
        return passwordHash;
    }

    @Override
    public void eraseCredentials() {
        passwordHash = null;
    }

    // Bổ sung các phương thức UserDetails còn lại trong class thật.
}
~~~

**Đây là fragment để hiểu interface, chưa phải class biên dịch độc lập.** Trong ứng dụng production, hãy thực hiện đúng hợp đồng `UserDetails`, tránh `toString()` in hash và tránh dùng nguyên entity được cache hoặc JPA-managed làm principal.

Vì `CredentialsContainer` là một interface cho object có thể được dọn, một Java `record` bất biến mang `String passwordHash` thường không phải lựa chọn phù hợp nếu bạn mong gọi `eraseCredentials()` để thay đổi field đó. Tốt hơn là **không đưa secret vào authenticated principal**, hoặc dùng cấu trúc có ownership/cleanup rõ ràng ở bước xác thực.

Nếu custom principal có các object lồng nhau cũng mang secret, hãy xem chúng có cần cơ chế dọn riêng không. `AbstractAuthenticationToken` gọi `eraseCredentials()` trên các object lồng nhau **nếu chúng cũng triển khai interface**; nó không duyệt phản xạ qua mọi field tùy ý trong class bạn viết.

### Tránh tạo object đã được authenticated trước khi xác minh

Một custom provider có thể tạo result tối thiểu sau khi đã xác minh:

~~~java
// Fragment bên trong AuthenticationProvider, CHỈ sau khi đã xác minh
// mật khẩu/chứng chỉ/token bằng nguồn tin cậy.
return UsernamePasswordAuthenticationToken.authenticated(
        new AccountPrincipal(accountId), // custom identity, không giữ password
        null,                            // không cần raw credentials
        authorities                     // các quyền đã được xác minh
);
~~~

`AccountPrincipal`, `accountId` và `authorities` trong fragment là dữ liệu/kiểu do ứng dụng cung cấp. Nếu viết provider riêng, **tốt nhất trả `Authentication` không chứa secret ngay từ đầu** thay vì coi `CredentialsContainer` là lớp bù cho việc giữ quá nhiều dữ liệu.

Không tự tạo token `authenticated(...)` từ một username/role do client gửi mà chưa xác minh, vì nó đánh dấu danh tính tin cậy trước khi thực hiện bảo mật.

## 8. Xóa tham chiếu khác với zeroization thực sự

Tên `eraseCredentials()` dễ gây hiểu nhầm. Trong Java/JVM có ít nhất ba mức:

| Cách xử lý | Điều thực sự xảy ra | Giới hạn |
| --- | --- | --- |
| Đặt field `credentials=null` | Object không còn giữ tham chiếu ấy | Object khác vẫn có thể giữ cùng secret |
| Xóa các phần tử `char[]`/`byte[]` mà ứng dụng sở hữu | Ghi đè mảng do mình kiểm soát | Không xóa các bản sao, có thể có tối ưu hóa/runtime khác |
| Garbage collection | JVM có thể thu hồi vùng nhớ của object không còn tham chiếu | Không có lời hứa dữ liệu đã bị ghi đè vật lý ngay lập tức |

`String` trong Java là **immutable**. Nếu raw password được tạo thành `String` trong controller, bạn không thể bảo đảm dùng `password = null` sẽ ghi đè dữ liệu ký tự của đối tượng ấy. JVM có thể giữ bản sao khác trong request buffer, log, profiler, thread dump hoặc một component khác.

Một mẫu chỉ dùng JDK 17 để dọn mảng mà ứng dụng sở hữu:

~~~java
char[] password = obtainPasswordFromTrustedInput();
try {
    verifyWithoutCreatingUnnecessaryCopies(password);
} finally {
    java.util.Arrays.fill(password, '\0');
}
~~~

Đây là **fragment về ownership của mảng**, với hai phương thức do ứng dụng tự định nghĩa; không phải ví dụ Spring `PasswordEncoder` (API `encode`/`matches` thường nhận `CharSequence`). Không được đánh đồng mảng zero-filled với việc đã xóa mọi bản sao trên heap.

Trên thực tế, Servlet form params và rất nhiều API xử lý mật khẩu bằng `String`, nên không thể loại bỏ hết thời gian tồn tại của raw password. Chiến lược hữu ích là **giảm số lần copy, tránh giữ lâu, không lưu log/cache/session, dọn những tham chiếu bạn sở hữu và giới hạn khả năng chụp bộ nhớ trái phép**.

### Một nguyên tắc thực tế: bí mật sống ngắn nhưng hash cần được lưu

Không cố xóa password hash khỏi **database** sau mỗi lần đăng nhập; nó cần thiết cho những lần xác minh sau. Hãy phân biệt bản ghi gốc trong credential store với bản sao được nạp vào `UserDetails`/principal và có thể bỏ đi sau xác thực.

Nếu bạn cần thay mật khẩu, hãy thực hiện **quy trình đổi/reset** và cập nhật hash mới; `eraseCredentials()` không thay thế `PasswordEncoder.encode(...)`, password rotation hay token revocation.

## 9. Khác biệt giữa dọn credentials và xóa SecurityContext

Trong Servlet, Spring Security thường quản lý `SecurityContextHolder` bằng `ThreadLocal` cho request và dọn context khi request hoàn tất. Có hai loại thao tác khác nhau:

- `Authentication.eraseCredentials()` (qua `CredentialsContainer`): dọn các trường bí mật ở những object liên quan.
- `SecurityContextHolder.clearContext()`: bỏ `SecurityContext` gắn với thread hiện tại, tránh rò danh tính sang một công việc/request khác dùng lại thread.

Cả hai đều quan trọng nhưng **không hoán đổi được**.

Ví dụ khi tự viết code chạy trong một thread và chủ động cài context:

~~~java
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(authenticatedResult);
try {
    SecurityContextHolder.setContext(context);
    runTaskAsAuthenticatedPrincipal();
} finally {
    SecurityContextHolder.clearContext();
}
~~~

Đây là fragment, yêu cầu import và implementation của `runTaskAsAuthenticatedPrincipal`. Trong web flow Spring Security chuẩn, framework filter đảm nhận thiết lập/dọn context; đừng tự thêm một cleanup làm mất Authentication giữa request nếu không hiểu lifecycle.

**`clearContext()` không có nghĩa xóa session ở server, thu hồi JWT, xóa cookie phía browser hoặc xóa password hash.** Nó chủ yếu ảnh hưởng ngữ cảnh gắn với thread. Logout/thu hồi phiên/token là một câu chuyện khác, phải xử lý riêng.

### Session và SecurityContextRepository

Ở một ứng dụng stateful, `SecurityContext` có thể được lưu và khôi phục từ HTTP session thông qua `SecurityContextRepository`. Vì thế nên đảm bảo result sau login có **principal tối thiểu, credentials đã được dọn và `details` không chứa bí mật** trước khi nó được lưu lâu hơn.

Ở ứng dụng stateless, mỗi request có thể tự mang một bearer token. Lúc đó **không có session password-login để xóa**, nhưng token và những bản sao của nó trong request/log/context vẫn cần được bảo vệ. Không suy luận rằng `eraseCredentialsAfterAuthentication=true` tự vô hiệu hóa bearer token hoặc xóa access token của client.

### Thread khác và asynchronous work

`SecurityContextHolder` mặc định sử dụng `ThreadLocal`. Khi bạn tạo thread, chạy `@Async`, dùng executor hoặc message consumer, ngữ cảnh bảo mật có thể không tự có mặt hoặc không tự được xóa ở chỗ bạn kỳ vọng. Sử dụng cơ chế propagation do Spring Security cung cấp (ví dụ các delegating security context wrappers) khi thực sự cần truyền danh tính.

Không copy toàn bộ request, mật khẩu hoặc `Authentication` chứa secret vào queue/job bất đồng bộ. Truyền **ID và quyền phù hợp với nghiệp vụ**, hoặc chứng cứ ủy quyền đã được thiết kế rõ. Ở background job, phải có chính sách authorization riêng, không giữ raw password từ request.

## 10. Thông tin nhạy cảm không chỉ có mật khẩu

`eraseCredentials()` là một cơ chế dọn object, nhưng chiến lược bảo vệ hệ thống phải bao phủ nhiều dạng bí mật:

| Dữ liệu | Thời điểm cần dùng | Vòng đời hợp lý | Rủi ro nếu vô tình giữ lâu |
| --- | --- | --- | --- |
| Raw password đăng nhập | Xác minh với hash trong login request | Không lưu bền vững, loại bỏ tham chiếu sớm nhất có thể | Lộ trong log, heap dump, session |
| Password hash | Xác minh mật khẩu mới nhập | Giữ trong credential store có kiểm soát; bản sao trên principal có thể dọn | Offline password guessing nếu hash bị lộ |
| OTP/TOTP code | Xác minh yếu tố thứ hai | Chỉ dùng trong cửa sổ ngắn theo chính sách; không log | Replay/đoán mã trong thời gian còn hiệu lực |
| Recovery code | Khôi phục khi mất yếu tố xác thực | Mỗi mã có quy tắc một lần và lưu trữ an toàn | Kẻ lạ dùng để chiếm tài khoản |
| Password reset token | Xác minh quyền đặt lại mật khẩu | Ngắn hạn, một lần, hủy sau sử dụng | Chiếm quyền đặt lại mật khẩu |
| OAuth authorization code + PKCE verifier | Hoàn tất trao đổi mã | Dùng trong flow rồi dọn các bản sao thừa | Chiếm mã/đổi mã ngoài ý muốn |
| Access token / JWT | Chứng minh quyền cho API đến khi hết hạn | TTL và cơ chế quản lý/thu hồi tương ứng | Bị dùng lại khi bị đánh cắp |
| Refresh token | Xin cấp lại access token | Giữ ở nơi bảo vệ, rotation/revocation khi phù hợp | Truy cập kéo dài nếu lộ |
| Session ID/cookie | Gắn request với phiên đã xác thực | Cookie bảo vệ, timeout, logout/invalidation | Chiếm session nếu bị đánh cắp |
| Client secret/API key/private key | Xác thực ứng dụng/máy hoặc ký | Kho bí mật riêng, kiểm soát truy cập/rotation | Xâm phạm nhiều tài nguyên |

Không phải dữ liệu nào cũng nên xóa ngay sau **một** lần request: refresh token hoặc session identifier có vòng đời hợp pháp dài hơn. Điều cần làm là **giữ theo đúng mục đích, ở đúng kho và đúng khoảng thời gian**, tránh đưa các dữ liệu đó vào principal hoặc log một cách tùy tiện.

Một JWT không thể thu hồi chỉ bằng cách đặt `authentication.getCredentials()=null` trong server, vì client vẫn có token gốc. Với token cần khả năng thu hồi nhanh, cần thiết kế TTL, denylist, token version, session binding hoặc introspection theo kiến trúc.

## 11. Những vị trí rất dễ vô tình sao chép secrets

Một luồng đăng nhập có thể đi qua nhiều lớp:

~~~text
HTTPS request
  -> reverse proxy / WAF
  -> access log / request tracing
  -> Servlet request
  -> Filter / controller
  -> Authentication token
  -> Authentication provider
  -> UserDetails / database
  -> success/failure handler
  -> session / cache / audit / telemetry
~~~

Ở mỗi ranh giới, cần đặt câu hỏi: **có thật cần giữ username, password, authorization header, cookie hay token trong đối tượng này không?** Nếu không, loại khỏi payload ngay.

Những lỗi thường gặp:

1. Để reverse proxy hoặc APM ghi **request body của `POST /login`**.
2. Dùng `log.debug("auth={}", authentication)` mà không hiểu `toString()`/custom principal có thể chứa gì.
3. Ghi `Authorization: Bearer ...` hoặc `Cookie: JSESSIONID=...` vào log để debug.
4. Trả `exception.getMessage()` trực tiếp ra API khi exception có raw credentials hoặc chi tiết storage.
5. Đưa nguyên DTO đăng nhập vào message queue, cache, audit event hoặc retry payload.
6. Tạo `AccountPrincipal` chứa password hash, refresh token hoặc toàn bộ JPA entity rồi serialise vào session.
7. Lưu OTP/reset token trong browser local storage, analytics URL hoặc referrer ngoài ý muốn.
8. Tạo bảng audit với cột `request_json` rồi lưu nguyên dữ liệu login không lọc.
9. Thêm một interceptor “thu thập mọi HTTP request” mà không có quy tắc redact.
10. Đưa secret vào URL query; URL có thể đi vào history, access log hoặc hệ thống phân tích.

Ngay cả với `ProviderManager` mặc định dọn credentials, một lần log secret **trước** lúc provider trả kết quả vẫn đã gây lộ. Do đó dọn credentials là **một lớp giảm thiểu**, không thay thế các kiểm soát ở các tầng khác.

### Khi cần log để điều tra, nên giữ gì?

Có thể ghi thông tin ít nhạy cảm hơn: request ID, timestamp, loại cơ chế xác thực, kết quả thành công/thất bại, nhóm lỗi, tên service, latency, thông tin actor/account ID được xử lý theo chính sách. Tránh dùng raw username/email làm label metrics nếu tạo dữ liệu cá nhân hoặc cardinality lớn.

Với exception, có thể lưu exception class và stack trace trong **kênh vận hành hạn chế truy cập** sau lọc dữ liệu nhạy cảm. Public response không chứa stack trace, SQL hoặc cấu hình provider.

## 12. Điều gì xảy ra khi đăng nhập thất bại?

Cơ chế mặc định của `ProviderManager` dọn credentials trên **result Authentication thành công**, nên bạn **không được suy ra** raw credentials trong input đã biến mất khi xác thực thất bại.

Một custom controller tự gọi manager có thể viết:

~~~java
// Fragment ở tầng web/service với authenticationManager có sẵn.
// username/password lấy từ request qua cơ chế đã lựa chọn.
UsernamePasswordAuthenticationToken input =
        UsernamePasswordAuthenticationToken.unauthenticated(
                username, password);

try {
    Authentication result = authenticationManager.authenticate(input);
    // Tiếp tục success flow đúng chuẩn, KHÔNG đưa raw input vào session.
    return result;
} finally {
    input.eraseCredentials(); // Chạy cả khi authenticate() ném exception.
}
~~~

Đây là cách dọn object input mà code đang sở hữu. Nó **không đảm bảo** biến `password` bên ngoài hoặc request body chứa raw `String` đã bị xóa khỏi RAM. Nếu `password` là local String, bạn nên giới hạn scope và tránh copy thêm.

Cũng không nên bắt `AuthenticationException` rồi trả `Authentication` thành công rỗng để “không gián đoạn dịch vụ”. Khi bằng chứng không được xác minh, phải **fail closed**. Với kho user không khả dụng, phân biệt `AuthenticationServiceException` với `BadCredentialsException` trong hệ thống; dọn secrets trong cả hai tình huống.

### Đăng nhập nhiều bước (MFA) cần vòng đời riêng

Nếu flow password thành công nhưng còn OTP/MFA, hệ thống có thể giữ **trạng thái thử thách** và một định danh tạm thời. Trạng thái ấy không nên chứa raw password để “đợi đến bước 2”, và không nên được đánh dấu có toàn quyền trước khi hoàn tất xác minh theo policy.

Mã OTP, recovery code, WebAuthn challenge và bearer token cần cơ chế thời hạn, one-time use và bảo vệ riêng. Một kết quả `Authentication` có `credentials=null` không tự bảo đảm MFA đã hoàn thành.

## 13. Khi nào không nên giữ Credential trong Authentication?

Một số quyết định thiết kế thực tế:

| Nhu cầu | Cách nên cân nhắc |
| --- | --- |
| Controller cần biết “ai đang gọi?” | Dùng `Authentication.getName()` hoặc principal ID; không cần raw password |
| Service muốn phân quyền theo role | Dùng `getAuthorities()` kết hợp resource-level authorization; không đọc password |
| Màn hình profile cần display name/email hiện tại | Tra nguồn nghiệp vụ/DTO với quyền phù hợp, không copy nguyên entity có passwordHash vào principal |
| Muốn xác thực lại hành động nhạy cảm | Dùng flow **reauthentication** hoặc step-up riêng; không giữ password cũ trong session |
| Cần liên hệ IdP sau login | Dùng cơ chế token management được bảo vệ, không nhét refresh token vào details của mọi `Authentication` |
| Muốn đổi mật khẩu | Xác minh password cũ/step-up theo chính sách và `encode` password mới; không lấy lại raw password từ session |
| Muốn xử lý lỗi login | Dùng failure handler/entry point, không đưa exception/request có secret vào log |
| Cache user để giảm DB | Thiết kế bản sao và lifetime riêng; không làm mutable principal ảnh hưởng cache |

**Lưu mật khẩu để “dùng lại khi cần” gần như luôn là tín hiệu kiến trúc sai.** Nếu một thao tác yêu cầu bằng chứng mới, hãy xin bằng chứng mới, hoặc dùng một credential/token chuyên dụng đã được thiết kế để ủy quyền cho thao tác ấy.

## 14. Kiểm thử cơ chế dọn credentials đúng cách

Có thể test ở ba lớp khác nhau:

**A. Unit/integration của AuthenticationManager:** sau một lần login hợp lệ, kết quả là authenticated nhưng `getCredentials()==null`; nếu principal kiểu `User`, password cũng null. Đây chính là nội dung ví dụ Gradle ở trên.

**B. Đăng nhập lặp lại và cache:** gọi `authenticate` hai lần. Nếu lần đầu làm password hash trong cached `UserDetails` bị xóa, lần thứ hai dễ thất bại. Hãy xác nhận repository/cache không bị biến đổi khi result principal được dọn.

**C. HTTP/request/session/logging:** kiểm tra form/Basic login thật; session không chứa raw password, request-body logging đã redact, API error không lộ secret, và request thất bại cũng không để object nhạy cảm sống ngoài ý muốn.

Ma trận kiểm thử:

| Trường hợp | Kỳ vọng |
| --- | --- |
| Xác thực đúng qua ProviderManager mặc định | Result `isAuthenticated=true`, `getCredentials()==null` nếu token hỗ trợ |
| Principal là `User` của Spring Security | Password field của principal result được dọn |
| Provider trả custom Authentication **không** triển khai CredentialsContainer | Không tự giả định framework có thể dọn mọi field bí mật |
| UserDetailsService tạo bản mới mỗi lần | Login thứ hai vẫn thành công |
| Cache giữ object User mutable dùng chung | Test phát hiện nguy cơ password bị xóa khỏi bản cache |
| Xác thực sai | Không cấp Authentication đáng tin; input cleanup được chạy |
| `AuthenticationException` ném giữa chừng | `finally` vẫn dọn object input do caller tạo |
| Session được tạo sau login | Không lưu raw password/OTP/token nhạy cảm vào principal/details |
| Thread pooled hoàn thành request | SecurityContext được dọn theo cơ chế web phù hợp |
| Logout | Session/token bị xử lý theo chính sách, không chỉ `clearContext()` ở một thread |
| Log truy vết khi login thành công/thất bại | Không có password, OTP, bearer token, Cookie hoặc raw request body |
| Custom provider | Kết quả Authentication chứa ID/authorities cần thiết, không chứa secret không cần |
| Password reset | Mã reset ngắn hạn, đúng tài khoản, một lần; không dựa vào password được giữ từ login |
| Dữ liệu cache và database | Password hash gốc được bảo vệ và không bị xóa nhầm do chia sẻ object với principal |

Với Spring Boot/MockMvc, `@WithMockUser` dựng sẵn một `Authentication` để kiểm thử authorization. Nó **không chạy `DaoAuthenticationProvider` và `ProviderManager` theo flow mật khẩu**. Muốn test credential erasure thật, phải gọi manager thực tế hoặc gửi request login thực qua filter được cấu hình.

### Test riêng cho trường hợp `eraseCredentialsAfterAuthentication=false`

Nếu một hệ thống buộc phải tắt mặc định vì cache, test cần đánh giá rõ:

- Result có giữ password/token trong credentials hay principal không?
- Có thể bị serialize qua session hoặc xuất qua debug/monitoring không?
- Có thời điểm dọn thủ công và quyền truy cập nào bảo vệ nó?
- Có thể thay đổi thiết kế để trả principal bản sao/không có secret thay vì giữ raw credential không?

Một flag “chạy được” không đủ để kết luận thiết kế an toàn. Cần ghi lại lý do và biện pháp giảm rủi ro trước khi đi production.

## 15. Các lỗi tư duy phổ biến

1. **“Spring Security sẽ xóa sạch password khỏi RAM sau login.”** Sai. Thường dọn tham chiếu trên object result; các bản sao khác có thể còn.
2. **“`ProviderManager` dọn luôn input request token.”** Không mặc định; nó nhắm đến **kết quả** được trả về.
3. **“Thấy `Authentication.getCredentials()==null` là chắc chắn không còn password trong principal.”** Chưa chắc với custom principal không hỗ trợ dọn.
4. **“Xóa password trong principal nghĩa là xóa hash khỏi database.”** Không. Object trong memory và credential store có vòng đời khác.
5. **“UserDetails có thể cache cùng object không lo bị sửa.”** `User` mặc định mutable và có thể bị erase làm cache mất hash.
6. **“Tắt `eraseCredentialsAfterAuthentication` là fix cache tốt nhất.”** Không nên là mặc định; ưu tiên copy object hoặc trả principal không mang hash.
7. **“`CredentialsContainer` chỉ xóa raw password.”** Nó còn có thể dọn password hash hoặc secret khác nếu class triển khai đúng.
8. **“Custom Authentication có bất kỳ field `secret` nào thì Spring tự tìm ra.”** Không; framework không quét mọi field qua reflection.
9. **“JWT đã hết hạn nghĩa cần gọi `eraseCredentials()` là xong.”** Token lifetime/validation/revocation là một vấn đề khác.
10. **“`SecurityContextHolder.clearContext()` cũng làm logout mọi thiết bị.”** Không; chỉ tác động đến ngữ cảnh hiện tại.
11. **“Có `permitAll()` thì không có secret nào trong request.”** Không; client vẫn có thể gửi token/password tới URL công khai.
12. **“Không log password ở controller là đủ.”** Reverse proxy, APM, filters và failure handlers cũng có thể ghi dữ liệu.
13. **“`char[]` luôn bảo đảm secret biến mất hoàn toàn.”** Không; có thể có bản sao và giới hạn runtime, chỉ giúp kiểm soát một mảng cụ thể.
14. **“Để refresh token trong `Authentication.details` thì được Spring dọn.”** Không chắc; `details` cần thiết kế riêng, tránh giữ secret ở đó.
15. **“Chỉ thành công mới cần cleanup.”** Sai. Đường thất bại hoặc exception cũng phải dọn input do ứng dụng sở hữu.
16. **“Đăng nhập đúng rồi nên giữ password để tác vụ nền có thể dùng lại.”** Không; background work cần định danh/ủy quyền riêng.
17. **“Hash bcrypt là dữ liệu vô hại, có thể trả trong JSON.”** Không; hash vẫn nhạy cảm và có thể bị tấn công offline khi lộ.
18. **“Đã dùng HTTPS thì không cần quan tâm secret ở log/session.”** TLS bảo vệ đường truyền, không bảo vệ các bản sao nội bộ.
19. **“MFA xong thì mọi OTP/token đều tự bị xóa.”** Cần vòng đời riêng cho từng secret và thành phần.
20. **“Dùng `@WithMockUser` chứng minh cleanup của DaoAuthenticationProvider.”** Không; test ấy bỏ qua quá trình password authentication thật.

## 16. Câu hỏi tự kiểm tra

**Câu 1.** Khi `DaoAuthenticationProvider` xác minh đúng mật khẩu, đối tượng nào chịu trách nhiệm dọn credentials của `Authentication` thành công trong cấu hình phổ biến?

*Trả lời:* `ProviderManager` gọi `eraseCredentials()` trên result nếu nó triển khai `CredentialsContainer` và tính năng được bật (mặc định).

**Câu 2.** `getCredentials()==null` có chứng minh mọi bản sao raw password đã biến mất khỏi JVM không?

*Trả lời:* Không. Đó là trạng thái của một object; String, request buffer và các bản sao khác có thể còn trong bộ nhớ.

**Câu 3.** Một `UserDetailsService` trả đúng cùng instance `User` từ cache. Vì sao lần login tiếp theo có thể sai?

*Trả lời:* Khi object đó được gắn vào principal của kết quả, `eraseCredentials()` có thể xóa password hash trong chính instance cache. Cần dùng bản sao tách biệt hoặc thiết kế provider trả principal tối thiểu.

**Câu 4.** Có nên tắt `setEraseCredentialsAfterAuthentication` chỉ để giải quyết lỗi cache?

*Trả lời:* Đây là tùy chọn có thật nhưng giữ secret lâu hơn; nên ưu tiên tách cache khỏi principal hoặc dùng bản sao. Nếu buộc phải tắt, đánh giá và kiểm thử rủi ro.

**Câu 5.** Vì sao `UserDetails#getPassword()` trên principal result có thể là `null` dù đăng nhập đúng?

*Trả lời:* Vì `User` triển khai `CredentialsContainer` và framework đã dọn password hash khỏi bản principal sau xác thực, trong khi bản hash ở nguồn lưu trữ vẫn tồn tại.

**Câu 6.** Đăng nhập sai ném `BadCredentialsException`. Có thể tin rằng ProviderManager đã dọn input request của ứng dụng chưa?

*Trả lời:* Không. Khi tự sở hữu request token, nên dọn trong `finally` và tránh copy raw credentials; việc dọn result mặc định áp dụng cho kết quả thành công.

**Câu 7.** Khác nhau giữa `eraseCredentials()` và `SecurityContextHolder.clearContext()`?

*Trả lời:* Một thao tác dọn secret trong các object có hỗ trợ; thao tác kia bỏ ngữ cảnh xác thực khỏi thread hiện tại. Không thao tác nào tự thay cho logout/revocation toàn hệ thống.

**Câu 8.** Có nên đưa toàn bộ entity Account chứa password hash vào `Authentication.principal`?

*Trả lời:* Không nên. Principal nên mang ID và metadata cần thiết; entity có dữ liệu nhạy cảm và vòng đời khác, dễ bị giữ lâu hoặc serialize.

**Câu 9.** Muốn lưu quyền truy cập vào background job sau login, có nên đẩy cả Authentication cùng mật khẩu vào queue?

*Trả lời:* Không. Truyền ID/claims/quyền được thiết kế cho job và thực hiện authorization riêng; không giữ raw password từ request.

**Câu 10.** Một bearer token vẫn còn hợp lệ ở client dù server gọi `eraseCredentials()`. Vì sao?

*Trả lời:* Xóa tham chiếu trên object server không thu hồi bản token client đang sở hữu. Cần TTL/validation/revocation phù hợp để giới hạn token bị đánh cắp.

## 17. Checklist trước khi hoàn tất một luồng xác thực

- [ ] Raw password/token chỉ tồn tại trong những thành phần thật sự cần xử lý và không bị ghi log, cache, analytics hoặc session.
- [ ] Cơ chế xác thực trả về `Authentication` với principal/authorities tối thiểu; credentials của result được dọn khi có thể.
- [ ] `ProviderManager` giữ `eraseCredentialsAfterAuthentication=true` trừ khi có quyết định kỹ thuật rõ ràng.
- [ ] Custom `Authentication`/principal có cơ chế dọn bí mật nếu buộc phải chứa secret, hoặc tốt hơn là không chứa ngay từ đầu.
- [ ] Input token do ứng dụng tự tạo được dọn trong `finally` ở cả nhánh thành công/thất bại.
- [ ] `UserDetailsService` và cache không trả shared mutable `User` bị erasure làm mất password hash cần dùng ở lần login sau.
- [ ] Password hash trong DB/credential store vẫn được bảo vệ, không lộ ra API và không bị dọn nhầm.
- [ ] Session/`SecurityContext` không giữ raw password; logout/session invalidation được thực hiện theo chính sách.
- [ ] JWT/access/refresh tokens có vòng đời, kho lưu và chiến lược thu hồi riêng.
- [ ] Thread/security context được quản lý đúng trên Servlet, async task và background worker.
- [ ] HTTP trace, reverse proxy, APM, exception log và audit đã redact credentials và các token nhạy cảm.
- [ ] Code và kiểm thử không đưa mật khẩu production vào literal, stdout, command history hoặc test fixtures bị chia sẻ.
- [ ] Có integration test cho hai lần login liên tiếp, login lỗi, credential cleanup và cache ownership.
- [ ] Đã xem lại các flow password reset, MFA và step-up authentication thay vì dựa vào password được giữ từ login.
- [ ] Ứng dụng có chính sách heap dump, giám sát, quyền truy cập log và xử lý sự cố phù hợp với dữ liệu nhạy cảm.

Một cách nhớ hữu ích là phân ba trách nhiệm: **`PasswordEncoder` xác minh bằng chứng**, **`ProviderManager` có thể dọn credentials của kết quả**, và **thiết kế ứng dụng quyết định các bản sao của secret được giữ ở đâu và trong bao lâu**. Không bước nào thay thế cho hai bước còn lại; bảo mật tốt là để bí mật xuất hiện ở ít chỗ nhất và chỉ tồn tại đủ lâu cho đúng nhiệm vụ.

### Tài liệu đối chiếu

- [Spring Security — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)
- [Spring Security — CredentialsContainer](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/credentials-container.html)
- [Spring Security — UserDetails và Credentials Management](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/user-details.html)
- [Spring Security — ProviderManager API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/ProviderManager.html)
- [Spring Security — CredentialsContainer API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/CredentialsContainer.html)
- [Spring Security — UsernamePasswordAuthenticationToken API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/UsernamePasswordAuthenticationToken.html)
- [Spring Security — User API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/userdetails/User.html)
- [Spring Security — DaoAuthenticationProvider API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/dao/DaoAuthenticationProvider.html)
- [Spring Security — SecurityContextHolder](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html#servlet-authentication-securitycontextholder)
- [OWASP — Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)
- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
