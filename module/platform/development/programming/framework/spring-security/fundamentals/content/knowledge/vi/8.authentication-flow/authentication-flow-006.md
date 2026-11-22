# AuthenticationException và phân biệt thông tin sai với lỗi hệ thống

Mai gõ sai mật khẩu, ứng dụng trả lời rằng đăng nhập thất bại. Mười phút sau, Mai nhập đúng mật khẩu nhưng kho dữ liệu tài khoản đang mất kết nối. Lần này ứng dụng cũng không thể hoàn tất đăng nhập. **Hai request đều chưa tạo được kết quả xác thực đáng tin cậy, nhưng nguyên nhân hoàn toàn khác nhau.**

Nếu lập trình viên bắt mọi exception rồi trả “sai mật khẩu”, người dùng sẽ tiếp tục thử đi thử lại khi database đang hỏng; bộ đếm sai mật khẩu thậm chí có thể khóa nhầm tài khoản. Ngược lại, nếu ứng dụng trả thẳng lỗi kết nối database ra trình duyệt, nó làm lộ chi tiết nội bộ. Spring Security có phân cấp `AuthenticationException` để phân biệt những loại thất bại này.

Bài học giải thích **`AuthenticationException` là gì, nó được tạo và xử lý ở đâu trong luồng Spring Security, cách nhận diện thông tin đăng nhập không hợp lệ so với sự cố hệ thống, cách chuyển thành thông báo/HTTP response an toàn, cách log và kiểm thử**. Ví dụ sử dụng Java 17+ và Spring Security để thấy sự khác nhau ở cấp exception trước khi đưa vào Servlet.

## 1. Một lần đăng nhập thất bại có ít nhất ba nguyên nhân

Xét ba trường hợp:

| Trường hợp | Sự thật bên trong | Cách xử lý đúng về mặt hệ thống |
| --- | --- | --- |
| Người dùng đưa mật khẩu không khớp với hash đã lưu | Thông tin đăng nhập không hợp lệ | Từ chối xác thực, không tạo phiên; đếm/thực thi chính sách chống thử đoán nếu phù hợp |
| Người dùng đúng, nhưng tài khoản đã bị khóa hoặc vô hiệu | Danh tính có thể tồn tại, nhưng chính sách trạng thái cấm xác thực | Từ chối đăng nhập; theo chính sách, hướng tới kênh xác minh hoặc khôi phục an toàn |
| Không đọc được tài khoản do DB/identity provider lỗi | Không đủ dữ liệu tin cậy để quyết định đúng hay sai | **Fail closed**: không cấp Authentication; ghi nhận sự cố hạ tầng và trả thông báo dịch vụ tạm không khả dụng |

Còn nhiều tình huống khác: không có `AuthenticationProvider` phù hợp, JWT không hợp lệ, thời gian gọi dịch vụ định danh hết hạn, lỗi cấu hình hash, chính sách yêu cầu MFA hoặc thông tin xác thực hết hạn.

Điểm xuất phát là **không được nhập nhằng “chưa xác thực thành công” với “người dùng nhập sai mật khẩu”**. Cả hai có thể kết thúc không có login thành công, nhưng cách vận hành, giám sát và phản hồi bên ngoài cần khác nhau.

### Nhìn theo ba tầng

~~~text
TẦNG 1: KIỂM TRA BẰNG CHỨNG
  password/token có hợp lệ?
  -> sai -> từ chối vì credentials

TẦNG 2: KIỂM TRA TRẠNG THÁI / CHÍNH SÁCH IDENTITY
  account enabled, non-locked, non-expired?
  -> không -> từ chối theo chính sách

TẦNG 3: KHẢ NĂNG XỬ LÝ CỦA HỆ THỐNG
  repository/identity service có trả dữ liệu đáng tin?
  -> không -> lỗi dịch vụ; KHÔNG giả vờ đã kiểm tra sai password
~~~

Đây là sơ đồ tư duy, không phải thứ tự kiểm tra cố định của mọi provider. Trong Spring Security, một provider có thể thực hiện kiểm tra trạng thái trước khi so mật khẩu, và các bản vá bảo mật còn có thể làm phép kiểm bổ sung để giảm rò rỉ qua thời gian phản hồi.

## 2. AuthenticationException thuộc tầng nào?

Trong Spring Security, kiểu gốc là:

~~~java
org.springframework.security.core.AuthenticationException
~~~

Nó là một **abstract class kế thừa `RuntimeException`**, dùng để biểu diễn sự cố khiến một yêu cầu `Authentication` không được xác thực hợp lệ. Một số đặc điểm quan trọng:

- `AuthenticationManager.authenticate(Authentication)` có thể trả về `Authentication` đã xác thực **hoặc ném `AuthenticationException`**.
- Các `AuthenticationProvider` khác nhau có thể ném các subtype thể hiện lý do: mật khẩu sai, trạng thái user bị cấm, thiếu provider, không xử lý được dịch vụ...
- `AuthenticationException` có `getMessage()` và có thể có `getCause()`, nhưng **không được mặc định coi message/cause là dữ liệu an toàn để trả cho client**.
- Nó thuộc **đăng nhập/xác thực**, khác với `AccessDeniedException` thường liên quan quyết định **phân quyền** sau hoặc trong quá trình kiểm soát truy cập.

Mô hình gọi phổ biến:

~~~text
HTTP request chứa thông tin xác thực
             |
             v
Authentication filter / login controller
             |
             v
AuthenticationManager
    (thường là ProviderManager)
             |
             v
AuthenticationProvider phù hợp
             |
             +--> kết quả hợp lệ -> Authentication đã được xác thực
             |
             +--> sai bằng chứng -> BadCredentialsException
             |
             +--> trạng thái cấm -> AccountStatusException subtype
             |
             +--> sự cố xử lý -> AuthenticationServiceException subtype
             |
             +--> không có provider -> ProviderNotFoundException (ở manager)
             |
             v
Bộ xử lý thất bại phù hợp với cơ chế login
             |
             v
HTTP response / redirect / audit / metric
~~~

**Không phải mọi lỗi trong authentication code đều tự trở thành `AuthenticationException`.** Lỗi `NullPointerException`, bug lập trình, lỗi serialization hoặc cấu hình sai có thể vẫn là `RuntimeException` khác và được xử lý bởi tầng lỗi hệ thống. Một số provider chuyển exception của repository thành `AuthenticationServiceException` hoặc `InternalAuthenticationServiceException`; cơ chế đó phụ thuộc implementation.

## 3. Các subtype quan trọng cần nhớ

| Loại exception | Khi nào có thể xuất hiện | Cần hiểu thế nào |
| --- | --- | --- |
| `BadCredentialsException` | Mật khẩu hoặc credentials không hợp lệ; thường cũng dùng cho username không tồn tại | Request không chứng minh được danh tính; không tiết lộ bên ngoài chi tiết account tồn tại hay không |
| `UsernameNotFoundException` | `UserDetailsService` không tìm được user | Trong `DaoAuthenticationProvider`, mặc định thường được che thành `BadCredentialsException` |
| `LockedException` | Account bị khóa | Subtype của `AccountStatusException`; không nhất thiết mật khẩu sai |
| `DisabledException` | Account bị vô hiệu hóa | Subtype của `AccountStatusException`; có thể cần quy trình kích hoạt/khôi phục |
| `AccountExpiredException` | Account đã hết thời hạn sử dụng | Khác với token hoặc subscription riêng lẻ hết hạn |
| `CredentialsExpiredException` | Bằng chứng đăng nhập, thường là mật khẩu, đã hết hạn theo chính sách | Khác với “password không khớp”; cần luồng đổi/reset phù hợp |
| `AuthenticationServiceException` | Không thể xử lý yêu cầu xác thực do sự cố hệ thống | Ví dụ kho người dùng/identity service không khả dụng; cần báo tình trạng hạ tầng |
| `InternalAuthenticationServiceException` | Sự cố xử lý phát sinh **trong hệ thống nội bộ**; là subtype của `AuthenticationServiceException` | Có thể phân biệt với lỗi từ hệ thống ngoài; không biến thành “sai password” |
| `ProviderNotFoundException` | Không có provider/manager nào xử lý kiểu `Authentication` được yêu cầu | Thường gợi ý cấu hình authentication chưa đúng, không phải user nhập sai |
| `InsufficientAuthenticationException` | Mức xác thực của chủ thể chưa đủ tin cậy cho một yêu cầu | Có thể cần bước xác thực bổ sung, không mặc định là mật khẩu sai |
| `AuthenticationCredentialsNotFoundException` | Không tìm được `Authentication` cần thiết trong security context | Thường xảy ra khi policy yêu cầu xác thực nhưng ngữ cảnh chưa có thông tin phù hợp |

Với JWT, OAuth2/OIDC, SAML2 hoặc cơ chế MFA, bạn sẽ gặp những subtype/luồng lỗi riêng; vẫn phải xem **bằng chứng không hợp lệ**, **thiếu mức xác thực** và **sự cố dịch vụ xác minh** là những trường hợp khác nhau.

### Phân cấp lớp rút gọn

~~~text
RuntimeException
    |
    +-- AuthenticationException                 (abstract)
           |
           +-- BadCredentialsException
           +-- UsernameNotFoundException
           +-- AccountStatusException           (abstract)
           |      +-- LockedException
           |      +-- DisabledException
           |      +-- AccountExpiredException
           |      +-- CredentialsExpiredException
           |
           +-- AuthenticationServiceException
           |      +-- InternalAuthenticationServiceException
           |
           +-- ProviderNotFoundException
           +-- InsufficientAuthenticationException
           +-- AuthenticationCredentialsNotFoundException
           +-- ... các dạng khác ...
~~~

Sơ đồ chỉ tập trung những loại có ích cho bài học, không liệt kê toàn bộ class hierarchy của Spring Security.

## 4. BadCredentialsException không nhất thiết nghĩa “username chắc chắn tồn tại”

Trong ứng dụng dùng `DaoAuthenticationProvider` và `UserDetailsService`, hai request có thể là:

~~~text
username = "mai"       password = "khong-dung"
username = "khong-co"  password = "bat-ky"
~~~

Trong cấu hình thông dụng, provider có lựa chọn `hideUserNotFoundExceptions` mặc định **true**. Theo đó:

- Username có thật nhưng password không khớp -> `BadCredentialsException`.
- Username không tồn tại và `UserDetailsService` ném `UsernameNotFoundException` -> provider thường **chuyển** thành `BadCredentialsException`.

Mục đích là không biến thông báo đăng nhập thành công cụ **dò danh sách username/email hợp lệ (account enumeration)**.

Tránh tự đổi cấu hình như sau mà không có lý do bảo mật được đánh giá:

~~~java
// KHÔNG KHUYẾN KHÍCH CHO ĐĂNG NHẬP CÔNG KHAI:
provider.setHideUserNotFoundExceptions(false);
~~~

Khi đó caller có thể thấy `UsernameNotFoundException` khác với mật khẩu sai; nếu mapping lỗi ra response cũng khác, kẻ tấn công dễ đoán được account nào tồn tại.

Một ứng dụng có thể vẫn cần biết người dùng bị khóa hay mật khẩu hết hạn để hỗ trợ đúng người. Hãy thực hiện **sau bước xác minh danh tính phù hợp**, qua kênh có kiểm soát hoặc một flow khôi phục an toàn. Không vì nhu cầu hỗ trợ mà trả nguyên trạng thái nội bộ cho người bất kỳ gửi username.

**Quan trọng:** khác biệt mã HTTP, URL chuyển hướng, thời gian phản hồi, HTML, kích thước body và rate limiting cũng có thể làm lộ thông tin. Chỉ đổi string message thành chung chung là chưa đủ.

## 5. AuthenticationServiceException: hệ thống không thể quyết định đúng/sai

Giả sử:

- Kho user ở database tạm thời không kết nối được.
- Dịch vụ định danh từ xa hết thời gian chờ.
- Không đọc được vật liệu xác minh cần thiết do một dịch vụ phụ thuộc ngừng hoạt động.
- Lớp repository báo lỗi không thể truy xuất dữ liệu xác thực nhất quán.

Đây là những trường hợp **không đủ điều kiện để tin tưởng kết quả xác thực**, khác với việc `PasswordEncoder.matches(raw, hash)` đã chạy và trả `false`.

Spring Security định nghĩa `AuthenticationServiceException` cho lỗi không thể xử lý yêu cầu vì vấn đề hệ thống. `InternalAuthenticationServiceException` chuyên biệt hóa trường hợp **lỗi phát sinh bên trong hệ thống**; việc phân loại này hữu ích cho log, metric và cách xử lý lỗi từ nhà cung cấp ngoài.

Ví dụ khi tự viết `UserDetailsService`:

~~~java
// Fragment: accountRepository là thành phần ứng dụng phải cung cấp.
@Override
public UserDetails loadUserByUsername(String username) {
    try {
        return accountRepository.findForAuthentication(username)
            .map(accountMapper::toUserDetails)
            .orElseThrow(() -> new UsernameNotFoundException("Not found"));
    } catch (UsernameNotFoundException exception) {
        throw exception;
    } catch (DataAccessException exception) {
        throw new InternalAuthenticationServiceException(
            "Cannot read authentication repository", exception);
    }
}
~~~

Đây là **mảnh minh họa trong một service có Spring Data**, không chạy độc lập: cần imports, repository, mapper và transaction phù hợp. Mã cố ý:

1. Giữ `UsernameNotFoundException` cho trường hợp **truy vấn thành công nhưng không tìm thấy account**.
2. Chuyển lỗi hạ tầng `DataAccessException` sang `InternalAuthenticationServiceException` kèm cause để chẩn đoán trong nội bộ.
3. **Không** bắt mọi `Exception` rồi ném `UsernameNotFoundException` hoặc `BadCredentialsException`.
4. **Không** trả danh sách rỗng/user mẫu khi DB đang hỏng để “cứ cho login chạy tiếp”.

Trong thực tế `DaoAuthenticationProvider` có thể đã chuyển các lỗi repository không phải `UsernameNotFoundException` thành subtype dịch vụ phù hợp. Chỉ thêm lớp mapping riêng khi nó đem lại giá trị và không che mất nguyên nhân.

### Phân biệt “dịch vụ bị hỏng” với “dữ liệu không tìm thấy”

~~~text
Query database thành công, result = empty
  -> danh tính không được tìm thấy
  -> UsernameNotFoundException (provider có thể che thành BadCredentials)

Query database ném lỗi kết nối/time-out
  -> KHÔNG biết account có tồn tại hoặc password có đúng không
  -> AuthenticationServiceException subtype / lỗi hệ thống

Query thành công, có user/hash, PasswordEncoder.matches = false
  -> credentials không khớp
  -> BadCredentialsException
~~~

Không biến trạng thái “không biết” thành “sai” chỉ vì cả hai đều không cấp quyền.

## 6. Thứ tự kiểm tra trong DaoAuthenticationProvider và ProviderManager

Một luồng username/password điển hình:

~~~text
POST /login
    |
    v
UsernamePasswordAuthenticationFilter
    |
    v
AuthenticationManager (ProviderManager)
    |
    v
DaoAuthenticationProvider
    |
    +-- UserDetailsService.loadUserByUsername(...)
    |        |
    |        +-- not found -> UsernameNotFoundException
    |        +-- datastore fails -> AuthenticationServiceException subclass
    |        +-- returns UserDetails + password hash
    |
    +-- checks account status (enabled/locked/expired)
    +-- PasswordEncoder kiểm tra raw password với hash
    +-- checks credentials status
    |
    +-- thành công -> Authentication
    +-- thất bại -> AuthenticationException
    |
    v
Filter xử lý thành công/thất bại theo cấu hình
~~~

Bản thân `AuthenticationManager` không phát HTTP status. Nó xử lý một `Authentication` và trả `Authentication` đã xác thực hoặc ném exception. **HTTP response thuộc lớp web/filter/controller**.

`ProviderManager` có thể thử nhiều `AuthenticationProvider` theo thứ tự, tùy loại token và kết quả. Một `BadCredentialsException` từ provider đầu không luôn là kết quả cuối nếu một provider sau có khả năng xác thực thành công. Nhưng những trường hợp như `AccountStatusException` hoặc `InternalAuthenticationServiceException` thường khiến `ProviderManager` **dừng ngay**, không thử một provider khác. Đọc đúng cấu hình thực tế trước khi suy ra exception cuối cùng.

`ProviderNotFoundException` báo rằng không có provider phù hợp với kiểu `Authentication`; nó thường liên quan wiring hoặc chiến lược xác thực. Không trả cho người dùng “mật khẩu sai” rồi đóng sự cố này.

### Không dùng exception class như một mật khẩu thứ hai

Có ứng dụng cố ý thay exception thành `BadCredentialsException` để “ẩn” mọi thứ. Việc ẩn chi tiết với người dùng ngoài là hợp lý, nhưng **loại lỗi nội bộ vẫn phải được giữ đúng trong log/metric**. Bạn có thể trả chung thông báo đăng nhập không thành công mà vẫn ghi rõ hệ thống vừa gặp sự cố hạ tầng.

Phân loại sai sẽ dẫn đến những quyết định vận hành sai: khóa nhầm account, tăng đếm `failedPasswordAttempts`, đánh giá sai tỷ lệ brute force, không phát hiện DB outage hoặc retry một lỗi do mật khẩu sai mãi mãi.

## 7. Ví dụ chạy độc lập Java 17+: đúng mật khẩu, sai mật khẩu, user không tồn tại và lỗi kho dữ liệu

Ví dụ này gọi **`AuthenticationManager`/ `DaoAuthenticationProvider` thật** của Spring Security. Nó không có Servlet/HTTP, không tạo phiên, không lưu JWT và không quản lý database; mục đích duy nhất là quan sát **loại exception sau một lần xác thực**.

Chúng ta dùng `UserDetailsService` trong memory với ba hành vi cố định:

- `mai`: tìm thấy, mật khẩu đúng là `correct-password`.
- Username khác `mai`, ngoại trừ `repository-offline`: không tìm thấy user.
- `repository-offline`: mô phỏng lỗi hạ tầng bằng `InternalAuthenticationServiceException`.

### 7.1. Tạo cấu trúc Gradle

~~~text
authentication-error-demo/
  build.gradle
  src/main/java/AuthenticationErrorDemo.java
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
}

application {
    mainClass = 'AuthenticationErrorDemo'
}
~~~

Ví dụ là chương trình standalone, nên khóa Spring Security 7.1.2 để người học có một bộ mã xác định. **Trong Spring Boot thật**, dùng `spring-boot-starter-security` và để BOM của Boot quản lý version các Spring Security modules. Đoạn mã chạy trên Java 17+, cần Gradle phù hợp và quyền tải thư viện lần đầu.

### 7.2. Tệp Java hoàn chỉnh

Tạo `src/main/java/AuthenticationErrorDemo.java`:

~~~java
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.AuthenticationServiceException;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.InternalAuthenticationServiceException;
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

public class AuthenticationErrorDemo {

    private static AuthenticationManager createManager() {
        PasswordEncoder encoder = new BCryptPasswordEncoder();
        String hash = encoder.encode("correct-password");

        UserDetailsService users = username -> {
            if ("repository-offline".equals(username)) {
                throw new InternalAuthenticationServiceException(
                        "Simulated authentication repository outage",
                        new IllegalStateException("Simulated connection failure"));
            }

            if (!"mai".equals(username)) {
                throw new UsernameNotFoundException("User not found");
            }

            return User.withUsername("mai")
                    .password(hash)
                    .roles("USER")
                    .build();
        };

        DaoAuthenticationProvider provider = new DaoAuthenticationProvider(users);
        provider.setPasswordEncoder(encoder);
        // hideUserNotFoundExceptions mặc định là true.
        return new ProviderManager(provider);
    }

    private static void attempt(
            AuthenticationManager manager,
            String label,
            String username,
            String password) {

        try {
            Authentication input =
                    UsernamePasswordAuthenticationToken.unauthenticated(
                            username, password);

            Authentication result = manager.authenticate(input);
            System.out.println(label + " -> SUCCESS:" + result.getName());

        } catch (BadCredentialsException exception) {
            System.out.println(label + " -> INVALID_CREDENTIALS");

        } catch (AuthenticationServiceException exception) {
            System.out.println(label + " -> SERVICE_UNAVAILABLE");

        } catch (AuthenticationException exception) {
            System.out.println(label + " -> OTHER_AUTHENTICATION_FAILURE");
        }
    }

    public static void main(String[] args) {
        AuthenticationManager manager = createManager();

        attempt(manager, "correct", "mai", "correct-password");
        attempt(manager, "wrong-password", "mai", "wrong");
        attempt(manager, "unknown-user", "does-not-exist", "any");
        attempt(manager, "repository-down", "repository-offline", "any");
    }
}
~~~

Tất cả dữ liệu người dùng, mật khẩu và lỗi DB đều giả. Mã này không ghi mật khẩu thật vào log, và không cần kết nối tới database hay dịch vụ bên ngoài sau khi dependency đã tải.

Chạy với Java 17+ và Gradle:

~~~bash
gradle run --quiet
~~~

Dòng do chương trình tự in ra theo thứ tự:

~~~text
correct -> SUCCESS:mai
wrong-password -> INVALID_CREDENTIALS
unknown-user -> INVALID_CREDENTIALS
repository-down -> SERVICE_UNAVAILABLE
~~~

Phân tích từng trường hợp:

1. **`correct`:** `UserDetailsService` tìm được Mai và `PasswordEncoder.matches` khớp hash, manager trả `Authentication` đã xác thực.
2. **`wrong-password`:** user có thật nhưng password không khớp, provider ném `BadCredentialsException`.
3. **`unknown-user`:** `UserDetailsService` ném `UsernameNotFoundException`; `DaoAuthenticationProvider` mặc định che sự khác biệt bằng `BadCredentialsException`.
4. **`repository-down`:** service ném `InternalAuthenticationServiceException`, là một `AuthenticationServiceException`, và catch chuyên cho lỗi dịch vụ nhận trường hợp này.
5. Phần `catch (AuthenticationException)` cuối là nhánh dành cho những loại thất bại xác thực **chưa được phân loại riêng**. Nó không đồng nghĩa với bad credentials.

**Vì sao thứ tự các catch quan trọng?** `BadCredentialsException` và `AuthenticationServiceException` cùng kế thừa `AuthenticationException`. Nếu đặt `catch (AuthenticationException)` trước, các catch cụ thể phía sau sẽ không thể nhận được exception tương ứng và Java compiler báo lỗi unreachable catch.

**Tại sao dùng bcrypt và không dùng `{noop}`?** `BCryptPasswordEncoder` tạo hash mật khẩu. Dù đang làm ví dụ về exception, chúng ta vẫn muốn cho thấy đúng luồng xác minh thay vì so sánh plaintext trong production. Chuỗi hash được tạo mỗi lần chạy có salt ngẫu nhiên, nên không in/so sánh nội dung hash cụ thể; output logic vẫn cố định.

### 7.3. Vì sao cùng sai login nhưng không được “retry giống nhau”?

Với `BadCredentialsException`, việc thử lại ngay **cùng username/password** thường không giải quyết được gì. Có thể hướng dẫn người dùng kiểm tra dữ liệu hoặc dùng quy trình khôi phục an toàn. Hệ thống cũng cần rate-limit.

Với `AuthenticationServiceException`, một lần thử lại **có kiểm soát**, sau khi service phục hồi, có thể thành công với chính credentials đó. Nhưng tuyệt đối tránh vòng retry vô hạn tạo bão tải cho database/identity provider đang gặp sự cố. Cần timeout, retry budget và circuit breaker theo thiết kế hệ thống.

Ví dụ standalone không tự retry. Nó chỉ chứng minh phải giữ được **loại nguyên nhân**.

## 8. Chuyển AuthenticationException thành response HTTP

`AuthenticationException` là một exception Java. Nó **không tự mang mã 401, 403, 500 hay 503**. Mã và body HTTP được quyết định bởi filter, `AuthenticationEntryPoint`, `AuthenticationFailureHandler`, controller hoặc error handler thực sự xử lý request.

Một chính sách API có thể là:

| Tình huống | Status gợi ý | Body công khai | Lý do |
| --- | --- | --- | --- |
| Credentials không hợp lệ | `401 Unauthorized` | `{"error":"LOGIN_FAILED"}` | Không xác thực được |
| Không tìm thấy user | `401 Unauthorized` giống thông tin sai | Cùng `LOGIN_FAILED` | Giảm dò username |
| Account locked/disabled trước login | Có thể dùng `401` với body chung; luồng khác sau xác minh | Không lộ trạng thái account cho người lạ | Giảm account enumeration |
| Kho user/IdP không khả dụng | `503 Service Unavailable` nếu ứng dụng cấu hình phân loại lỗi dịch vụ | `{"error":"AUTHENTICATION_UNAVAILABLE"}` | Người dùng không thể khắc phục bằng đổi password |
| Provider chưa cấu hình đúng | `500` hoặc `503` tùy nguyên nhân và policy | `{"error":"INTERNAL_ERROR"}` | Cần điều tra cấu hình nội bộ |
| Đã xác thực nhưng thiếu quyền xem tài nguyên | Thường `403 Forbidden` | `{"error":"FORBIDDEN"}` | Đây là vấn đề phân quyền, không phải login sai |
| Chưa xác thực khi truy cập endpoint bảo vệ | Thường `401` hoặc redirect tới login theo loại client | Thông báo/redirect tương ứng | Đây là yêu cầu cần xác thực, có thể chưa có lần login thất bại |

**Bảng trên mô tả một thiết kế chủ động, không tuyên bố Spring Security tự động trả 503 cho mọi `AuthenticationServiceException`.** Mặc định form login có thể chuyển về `/login?error`, HTTP Basic có thể gửi challenge 401 hoặc xử lý khác tùy đường đi của exception. Muốn phân biệt response, cần cấu hình **đúng cơ chế đang xử lý login** và kiểm thử hành vi end-to-end.

### 401, 403 và 503 khác nhau về nghĩa

- **401:** request cần bằng chứng xác thực hợp lệ. Ở HTTP Basic, response thường có `WWW-Authenticate` để client biết cách xác thực.
- **403:** phía server từ chối thao tác theo chính sách dù request có thể đã được xác thực; một request thiếu CSRF token cũng có thể bị từ chối với 403 mà nguyên nhân không nằm ở mật khẩu.
- **503:** dịch vụ tạm không xử lý được request. Một server không đọc được kho user nên **không thể kết luận password sai**, nhưng cũng không được cấp quyền.
- **500:** lỗi phía server không được xử lý như trường hợp business/authentication dự kiến, ví dụ bug lập trình hoặc cấu hình sai.

Mã HTTP cần phù hợp giao thức và hợp đồng client. Dùng mã khác nhau có thể hỗ trợ client, nhưng cũng có thể tạo **kênh phụ dò trạng thái account** nếu khác biệt dựa trên việc tài khoản có tồn tại hay bị khóa. Luôn đánh giá cả phản hồi công khai lẫn yêu cầu hỗ trợ.

## 9. FailureHandler, AuthenticationEntryPoint và ExceptionTranslationFilter khác nhau

Đây là vị trí rất dễ bắt nhầm exception.

### 9.1. Đăng nhập bằng form: AuthenticationFailureHandler

Khi form login được xử lý qua `UsernamePasswordAuthenticationFilter`/`AbstractAuthenticationProcessingFilter`, một thất bại xác thực sẽ dẫn tới `AuthenticationFailureHandler`. `SimpleUrlAuthenticationFailureHandler` có thể redirect về trang login với tham số lỗi.

Nếu muốn API nhận POST login qua **cơ chế form login** và trả JSON có phân loại lỗi dịch vụ, bạn có thể cấu hình một handler riêng. Đây là **fragment trong cấu hình SecurityFilterChain Servlet**, không phải class chạy độc lập:

~~~java
http.formLogin(form -> form
    .failureHandler((request, response, exception) -> {
        response.setHeader("Cache-Control", "no-store");
        response.setContentType("application/json;charset=UTF-8");

        if (exception instanceof AuthenticationServiceException) {
            response.setStatus(503);
            response.getWriter().write(
                "{\"error\":\"AUTHENTICATION_UNAVAILABLE\"}");
        } else {
            response.setStatus(401);
            response.getWriter().write(
                "{\"error\":\"LOGIN_FAILED\"}");
        }
    })
);
~~~

Cấu hình trên giả định một request login được xử lý bởi form-login filter và frontend đang mong JSON. Nó **không tự thiết lập CSRF token, provider, trang login hay xử lý trạng thái tài khoản sau khi login**. Các form HTML truyền thống có thể thích hợp hơn với redirect cố định tới trang lỗi an toàn; phải thiết kế theo loại client thực tế.

Lưu ý tên kiểu `AuthenticationServiceException` cần import package `org.springframework.security.authentication`. Không đẩy `exception.getMessage()` hoặc stack trace thẳng vào response. Không để response chứa dữ liệu nhạy cảm từ request.

### 9.2. Truy cập endpoint cần đăng nhập: AuthenticationEntryPoint

Một request `GET /private` chưa có credentials có thể được `ExceptionTranslationFilter` đưa vào `AuthenticationEntryPoint` để bắt đầu flow xác thực. Chẳng hạn, với form login có thể redirect đến `/login`; với HTTP Basic, có thể trả 401 kèm challenge.

Đây **không nhất thiết là một lần người dùng đã nhập sai mật khẩu**. `AuthenticationEntryPoint` được dùng khi cần yêu cầu xác thực theo flow đã định; không mặc định coi mọi request ẩn danh vào `/private` là một lần thử password thất bại.

### 9.3. HTTP Basic xử lý lỗi ở filter khác

`BasicAuthenticationFilter` đọc credentials trong header `Authorization`, gọi authentication manager rồi xử lý thất bại theo cơ chế Basic/entry point tương ứng. Chỉ cấu hình `formLogin().failureHandler(...)` **không đảm bảo** những lỗi từ HTTP Basic sẽ đi qua handler form login.

Nếu ứng dụng có nhiều chain (`/api/**` và phần web), hãy xem **chain và filter nào thực sự xử lý request** trước khi cấu hình error mapping.

### 9.4. @ControllerAdvice không bắt được mọi lỗi Spring Security

Một `@RestControllerAdvice` có thể xử lý exception do controller/service ném trong Spring MVC. Nhưng nhiều exception xác thực phát sinh **trong security filter chain, trước khi request tới controller**. Vì vậy một `@ExceptionHandler(AuthenticationException.class)` đơn lẻ trong MVC không đảm bảo chặn được mọi thất bại login.

Nếu bạn tự gọi `AuthenticationManager.authenticate(...)` trong controller, bạn phải quyết định cách bắt exception tại đó. Nếu dùng built-in form login hoặc Basic filter, ưu tiên điểm mở rộng của cơ chế ấy.

## 10. Thiết kế error response: an toàn với người dùng và hữu ích với người vận hành

Một hệ thống tốt có **hai góc nhìn khác nhau**:

~~~text
                 AuthenticationException
                          |
                 Phân loại nội bộ
                  /               \
                 /                 \
        VALIDATION/POLICY         SERVICE FAILURE
                |                      |
                v                      v
      Response chung cho người     Response tạm không khả dụng
      dùng chưa xác minh           (không lộ backend)
                |                      |
                +----------+-----------+
                           |
                           v
              Audit + metrics + correlation ID
              theo đúng loại nguyên nhân
~~~

**Giao diện bên ngoài:** đủ rõ để người dùng biết tiếp theo nên làm gì, nhưng không công bố username có tồn tại, tài khoản bị điều tra hay hệ thống database dùng loại nào. Những trạng thái nhạy cảm có thể được hướng dẫn qua email đã xác minh hoặc phiên hỗ trợ đã xác thực.

**Quan sát nội bộ:** phân loại và theo dõi số lỗi `INVALID_CREDENTIALS`, `ACCOUNT_STATUS`, `AUTH_SERVICE_UNAVAILABLE`, `NO_PROVIDER`, latency và tỷ lệ thành công. Đội vận hành cần biết có sự cố dịch vụ hay không.

### Những gì không nên log

- Raw password, OTP, recovery code, `Authorization` header, JWT/access token/refresh token.
- Session ID/cookie, đầy đủ `Authentication` hoặc object request chứa credentials.
- Toàn bộ giá trị `exception.getAuthenticationRequest()` nếu phiên bản API cung cấp trường này: đối tượng có thể tham chiếu request chứa dữ liệu nhạy cảm.
- Chuỗi kết nối chứa mật khẩu database, secret của identity provider hoặc stack trace nguyên vẹn vào public response.

Có thể ghi **exception class**, category, trace/correlation ID, endpoint đã chuẩn hóa, thời điểm, service và thông tin account đã xử lý theo chính sách bảo vệ dữ liệu. Stack trace chi tiết nên vào kênh vận hành giới hạn quyền truy cập, với cơ chế lọc bí mật phù hợp.

**Không gắn nhãn cá nhân trong metrics có cardinality cực lớn**: tránh dùng username/email làm label của Prometheus. Có thể cần audit riêng theo account ID đã băm hoặc lưu an toàn, với retention và quyền truy cập tương ứng.

### Đếm sai mật khẩu và khóa tài khoản

Chính sách chống brute-force có thể tăng bộ đếm khi `BadCredentialsException`. Nhưng cần suy xét tình huống username không tồn tại, nhiều provider, cache và concurrency. **Không tăng bộ đếm “mật khẩu sai” cho `AuthenticationServiceException`** vì hệ thống chưa hề xác minh được password đúng hay sai.

Một ví dụ policy ở tầng quan sát:

| Internal category | Có nên tăng failed-password counter? | Có nên cảnh báo vận hành? |
| --- | --- | --- |
| Sai credentials được xác nhận | Theo policy/rate limit | Theo ngưỡng, xem xét brute force |
| Username không tồn tại | Không gắn vào một account giả; vẫn có thể rate limit nguồn request | Theo ngưỡng enumeration |
| Account locked/disabled/expired | Không mặc định xem như password sai | Theo chính sách audit trạng thái |
| Authentication service down | **Không** | **Có**, sự cố dịch vụ |
| ProviderNotFound/cấu hình sai | Không | Có, cần điều tra cấu hình |

Nếu ứng dụng tự viết `UserDetailsService`, đừng làm `catch (Exception e) { throw new BadCredentialsException("Bad login"); }` vì nó làm mất hoàn toàn ranh giới trên.

## 11. Sai lầm thường gặp khi xử lý AuthenticationException

1. **“Mọi `AuthenticationException` nghĩa password sai.”** Không: có cả lỗi hệ thống, trạng thái, cấu hình và mức xác thực.
2. **“Database timeout nghĩa user không tồn tại.”** Không: nguồn dữ liệu chưa đưa ra câu trả lời đáng tin.
3. **“`UsernameNotFoundException` lúc nào cũng hiện tới client.”** Không: `DaoAuthenticationProvider` thường che thành `BadCredentialsException`.
4. **“Bật `hideUserNotFoundExceptions=false` giúp bảo mật tốt hơn.”** Nó có thể làm lộ user enumeration.
5. **“Trả `exception.getMessage()` là hữu ích cho người dùng.”** Message nội bộ có thể chứa thông tin hạ tầng hoặc trạng thái nhạy cảm.
6. **“Lỗi xác thực nên luôn trả 403.”** 401/403 có ngữ nghĩa khác; CSRF/authorization cũng có thể tạo 403.
7. **“`AuthenticationServiceException` tự trả 503.”** Không: HTTP status do filter/handler/controller quyết định.
8. **“Thêm form-login failure handler là xử lý được HTTP Basic/JWT.”** Không: những cơ chế đó có điểm xử lý lỗi riêng.
9. **“Thêm `@ControllerAdvice` là bắt toàn bộ lỗi bảo mật.”** Filter chain có thể phát sinh exception trước MVC.
10. **“Lỗi DB nên retry login liên tục.”** Gây tải thêm khi hệ thống đang hỏng.
11. **“Lỗi DB nên tăng failed-password counter.”** Sai: chưa kiểm tra được mật khẩu.
12. **“Có `BadCredentialsException` tức tài khoản chắc chắn tồn tại.”** Không, provider có thể dùng cùng exception cho username không tồn tại.
13. **“Mọi account locked phải được thông báo công khai.”** Thông báo phân biệt trạng thái có thể tạo account enumeration.
14. **“Chuyển tất cả lỗi thành 401 thì không cần metrics.”** Mất khả năng phân biệt outage với brute force; vẫn cần quan sát.
15. **“Cứ catch `RuntimeException` rồi trả 401 cho an toàn.”** Có thể giấu bug nghiêm trọng và đánh lừa client.
16. **“ProviderNotFoundException là mật khẩu sai.”** Có thể do không có provider xử lý token, cần kiểm tra cấu hình.
17. **“Đăng nhập thất bại thì luôn cần đặt lại mật khẩu.”** Sai với lỗi dịch vụ hoặc thiếu mức xác thực.
18. **“Đăng nhập bằng JWT sẽ có đủ các exception như DaoAuthenticationProvider.”** Không; JWT/resource server có bộ filter/provider/exception riêng.
19. **“Không có SecurityContext ở controller nghĩa đã thử mật khẩu và thất bại.”** Chưa chắc đã có thao tác xác thực nào được thực hiện.
20. **“Log toàn bộ authentication request giúp dễ debug.”** Rủi ro rò credentials/token; cần lọc và tách thông tin nhạy cảm.

## 12. Ma trận kiểm thử tối thiểu

Để chứng minh hệ thống phân biệt lỗi đúng, hãy kiểm tra ở **hai lớp**:

- **Unit/integration tại AuthenticationManager/Provider:** xem đúng loại exception nội bộ.
- **HTTP end-to-end qua filter/chain:** xem đúng status/body/redirect, không rò thông tin và không tạo session khi thất bại.

| Tình huống kiểm thử | Tại AuthenticationManager | Response/policy kỳ vọng |
| --- | --- | --- |
| Username đúng, password đúng | `Authentication` thành công | Theo flow, có session/token hoặc response phù hợp |
| Username đúng, password sai | `BadCredentialsException` | Thông báo login thất bại chung; thường 401 cho API |
| Username không tồn tại | Thường bị che thành `BadCredentialsException` | Không lộ khác biệt với mật khẩu sai |
| Tài khoản locked | `LockedException` theo cơ chế provider | Không công khai trạng thái nhạy cảm khi chưa xác minh |
| Tài khoản disabled | `DisabledException` | Chính sách phản hồi an toàn, luồng kích hoạt riêng nếu có |
| Password hết hạn | `CredentialsExpiredException` | Quy trình thay/reset hợp lệ, không cấp toàn quyền |
| DB/repository timeout | `AuthenticationServiceException` subtype hoặc lỗi hệ thống được mapping | Không phát Authentication; cảnh báo vận hành; có thể 503 |
| Không có provider hỗ trợ token | `ProviderNotFoundException` | Không biến thành password sai; kiểm tra wiring |
| User có Authentication nhưng thiếu role | Thường **không phải** login exception mới | Authorization từ chối, thường 403 |
| POST bị CSRF từ chối | Có thể **không gọi AuthenticationManager** | Xử lý CSRF theo filter; thường 403 |
| Form login sai | Failure handler đúng chain được gọi | Redirect/thông báo theo UI policy |
| Basic auth sai | Basic filter/entry point xử lý | Response Basic theo client, không dựa vào form handler |
| OAuth2/JWT signature không hợp lệ | Lỗi validation/token tương ứng | Không cho truy cập, tránh lộ cấu hình token |
| DB down trong giờ cao điểm | Nhóm lỗi service tăng | Alert, retry budget/circuit breaker, không khóa nhầm user |

Với Spring Boot và MockMvc, `@WithMockUser` **không** chứng minh password đã được provider kiểm tra: annotation dựng sẵn `Authentication` để test authorization. Muốn xác minh `BadCredentialsException` hay `AuthenticationServiceException`, hãy gửi request đăng nhập thực qua filter phù hợp hoặc gọi manager thật trong integration test.

### Kiểm tra lỗi được ẩn an toàn nhưng vẫn hữu ích

Khi người dùng có và không có account cùng nhập sai credentials, public response không nên chứa sự khác biệt dễ khai thác trong message, status, URL và timing. Nhưng trong metrics nội bộ, ứng dụng vẫn có thể phân biệt **lỗi hệ thống** với **lỗi do thông tin xác thực** mà không tiết lộ cho caller.

Với outage thật, điều quan trọng là không tạo ra một `Authentication` thành công bằng fallback “cho qua”, cache sai hoặc tài khoản khẩn cấp không được quản trị. **Fail closed** nghĩa là thiếu bằng chứng tin cậy thì không cấp quyền; nó không có nghĩa giấu mọi thông tin lỗi khỏi đội vận hành.

## 13. Những tình huống cần suy nghĩ thêm

### Tình huống A — Repository trả lỗi kết nối

Ứng dụng bắt `DataAccessException` và ném `BadCredentialsException` với message `Invalid username or password`. Vấn đề gì xảy ra?

**Trả lời:** hệ thống đánh mất nguyên nhân service outage, client có thể bị hướng dẫn sửa mật khẩu vô ích, bộ đếm failed-password có thể tăng sai và đội vận hành khó phát hiện. Nên giữ loại lỗi dịch vụ nội bộ, fail closed và chọn response công khai phù hợp mà không lộ chi tiết.

### Tình huống B — Cùng một provider nhận hai username

Một username tồn tại nhưng password sai, username kia không tồn tại. Cả hai ném `BadCredentialsException`. Có sai không?

**Trả lời:** không; đây là hành vi thường được khuyến nghị để giảm rò rỉ thông tin tài khoản. Nhưng còn cần kiểm tra sự khác biệt ở thời gian xử lý, status và body công khai.

### Tình huống C — Admin khóa account đúng lúc người dùng đăng nhập

`DaoAuthenticationProvider` ném `LockedException` dù mật khẩu người dùng đúng. Có nên đếm như một lần sai password?

**Trả lời:** không mặc định. Đây là lỗi trạng thái tài khoản, nên audit riêng và xử lý theo chính sách mở khóa. Cần chú ý race condition nếu trạng thái account thay đổi trong lúc login.

### Tình huống D — Khách truy cập URL cần login nhưng chưa gửi username/password

Hệ thống gọi `AuthenticationEntryPoint` đưa đến trang đăng nhập. Có nghĩa đã xảy ra `BadCredentialsException`?

**Trả lời:** không nhất thiết. Yêu cầu hiện tại chưa có Authentication hợp lệ; request có thể chưa thực hiện một lần xác thực bằng mật khẩu.

### Tình huống E — Có Auth0/Keycloak/IdP bên ngoài

Nếu remote IdP trả về một lỗi HTTP 500, có nên coi là sai mật khẩu của khách?

**Trả lời:** không. Cần phân biệt phản hồi giao thức đáng tin của IdP, lỗi mạng, lỗi cấu hình và bằng chứng không hợp lệ. Không đưa raw message từ IdP ra client hoặc để kẻ không tin cậy kích hoạt log vô hạn. Loại exception tùy integration, không nhất thiết là `DaoAuthenticationProvider`.

### Tình huống F — HTTP API thông báo 401 khi DB down

Có thể xảy ra không? Có phải Spring Security bị lỗi?

**Trả lời:** có thể, tùy điểm xử lý exception và cấu hình. Mã 503 cho sự cố hạ tầng là một lựa chọn thiết kế rõ nghĩa nếu chủ động mapping; Spring Security không bảo đảm mặc định đó cho mọi filter/login mechanism.

## 14. Checklist triển khai trước khi đưa vào production

- [ ] Phân biệt **credentials invalid**, **account status** và **authentication service failure** trong mô hình lỗi nội bộ.
- [ ] Không catch toàn bộ exception từ kho user rồi đổi thành `BadCredentialsException`.
- [ ] `UserDetailsService` trả `UsernameNotFoundException` khi *thật sự không tìm thấy*, còn lỗi DB/IdP được giữ làm lỗi hệ thống.
- [ ] `DaoAuthenticationProvider` dùng `PasswordEncoder` phù hợp và cơ chế che user không tồn tại theo yêu cầu an toàn.
- [ ] Form login, Basic, JWT, OAuth2 hoặc custom controller có **điểm bắt lỗi đúng luồng**.
- [ ] Response bên ngoài không lộ trạng thái account/stack trace, hostname, SQL, thông tin hệ thống.
- [ ] Mã 401, 403, 500, 503 được chọn theo hợp đồng client, không phụ thuộc việc bắt exception tràn lan.
- [ ] Không tạo phiên/token khi không đủ bằng chứng xác thực.
- [ ] Không tăng failed-password counter khi lỗi dịch vụ chưa kiểm tra được password.
- [ ] Không retry vô hạn khi kho user/IdP mất kết nối.
- [ ] Audit/metrics phân biệt lỗi hệ thống và credentials; có correlation ID để điều tra.
- [ ] Không log password/OTP/token, session ID hoặc toàn bộ Authentication request.
- [ ] Kiểm thử account enumeration qua message, status, thời gian phản hồi và luồng reset.
- [ ] Test HTTP thật đi qua filter, vì `@WithMockUser` không kiểm tra quá trình login.
- [ ] Cập nhật bản vá Spring Security và thư viện xác thực, kiểm tra lỗi timing hoặc thông tin tài khoản bị tiết lộ theo advisory liên quan.

## 15. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao `AuthenticationException` không phải từ đồng nghĩa của `BadCredentialsException`?

*Trả lời:* `AuthenticationException` là lớp gốc cho nhiều kiểu thất bại xác thực, gồm sai credentials, account status, lỗi dịch vụ, thiếu provider hoặc thiếu mức xác thực. `BadCredentialsException` chỉ là một subtype.

**Câu 2.** `UserDetailsService` trả `UsernameNotFoundException`, vì sao bên ngoài đôi khi vẫn thấy `BadCredentialsException`?

*Trả lời:* `DaoAuthenticationProvider` mặc định có thể che lỗi không có user bằng lỗi chung `BadCredentialsException` để tránh username enumeration.

**Câu 3.** Mật khẩu đúng nhưng database không thể truy vấn. Có thể kết luận người dùng đăng nhập sai không?

*Trả lời:* Không. Hệ thống chưa xác minh được bằng chứng; cần fail closed, xử lý lỗi dịch vụ và không làm bẩn bộ đếm mật khẩu sai.

**Câu 4.** Exception `InternalAuthenticationServiceException` thuộc nhánh nào?

*Trả lời:* Nó kế thừa `AuthenticationServiceException`, được dùng cho lỗi nội bộ không thể xử lý yêu cầu xác thực.

**Câu 5.** Vì sao `catch (AuthenticationException)` phải đặt sau các catch cụ thể?

*Trả lời:* Vì Java chọn catch theo thứ tự; bắt lớp cha trước khiến nhánh bắt lớp con phía sau không thể tới được.

**Câu 6.** `AuthenticationManager.authenticate` trả `Authentication` thành công có đồng nghĩa người dùng được phép xem hồ sơ người khác không?

*Trả lời:* Không. Authorization là bước quyết định theo action/resource sau xác thực; có thể từ chối 403.

**Câu 7.** Form login có failure handler trả 503 khi lỗi dịch vụ. Vì sao cùng cấu hình ấy chưa đủ để HTTP Basic trả 503?

*Trả lời:* Basic sử dụng filter và xử lý entry point riêng; handler của form login không tự được gọi cho Basic.

**Câu 8.** Lỗi DB bị đổi thành `BadCredentialsException` rồi UI trả 401 chung. Hệ thống vẫn “an toàn” vì không lộ lỗi DB chứ?

*Trả lời:* Chưa đủ. Không cấp quyền là cần thiết, nhưng phân loại sai làm hỏng metrics, lockout policy và recovery. Response chung và phân loại nội bộ đúng có thể đồng thời tồn tại.

**Câu 9.** `AuthenticationServiceException` có tự quyết định status HTTP không?

*Trả lời:* Không. Nó là một Java exception; filter/handler/entry point/controller chuyển nó thành HTTP behavior.

**Câu 10.** Vì sao không nên in nguyên `AuthenticationException.getAuthenticationRequest()` vào log?

*Trả lời:* Đối tượng request xác thực có thể chứa hoặc tham chiếu credential nhạy cảm. Chỉ ghi dữ liệu tối thiểu đã lọc và thông tin lỗi phù hợp cho vận hành.

Điểm cần ghi nhớ khi đọc một luồng đăng nhập là: **“Bằng chứng bị chứng minh là sai” khác với “hệ thống không thể kiểm tra bằng chứng”.** Spring Security cung cấp các subtype `AuthenticationException` để biểu diễn khác biệt ấy. Giữ đúng loại lỗi trong hệ thống, nhưng trả thông báo công khai an toàn, giúp tránh cả lỗi bảo mật lẫn sai sót vận hành.

### Tài liệu tham khảo

- [Spring Security — AuthenticationException API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/AuthenticationException.html)
- [Spring Security — AuthenticationManager API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/AuthenticationManager.html)
- [Spring Security — BadCredentialsException](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/BadCredentialsException.html)
- [Spring Security — AuthenticationServiceException](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/AuthenticationServiceException.html)
- [Spring Security — InternalAuthenticationServiceException](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/InternalAuthenticationServiceException.html)
- [Spring Security — AbstractUserDetailsAuthenticationProvider](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/dao/AbstractUserDetailsAuthenticationProvider.html)
- [Spring Security — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/dao/DaoAuthenticationProvider.html)
- [Spring Security — Form Login](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/form.html)
- [Spring Security — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)
- [Spring Security — AuthenticationFailureHandler](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/authentication/AuthenticationFailureHandler.html)
- [OWASP — Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)
- [OWASP — Error Handling Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Error_Handling_Cheat_Sheet.html)
