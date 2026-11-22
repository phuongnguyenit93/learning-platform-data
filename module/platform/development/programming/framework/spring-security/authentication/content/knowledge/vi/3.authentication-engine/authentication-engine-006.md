# ProviderNotFoundException khi không có provider phù hợp

**Module:** Spring Security – authentication. **Nhóm kiến thức:** Bộ máy xác thực.

## 1. Hiểu đúng ngoại lệ

`ProviderNotFoundException` là một `AuthenticationException` được `ProviderManager` dùng khi **không có thành phần xác thực nào đưa ra được kết quả cho kiểu `Authentication` của request** và không có ngoại lệ xác thực khác cần trả ra thay thế. Một thông báo thường gặp có dạng:

~~~text
No AuthenticationProvider found for org.springframework.security.authentication.UsernamePasswordAuthenticationToken
~~~

Tên class ở cuối thông báo cho biết **kiểu đối tượng Authentication** đang được xử lý. Ngoại lệ này thường nói về **ghép nối sai giữa request token và AuthenticationProvider/AuthenticationManager**, không mặc nhiên cho biết username sai, mật khẩu sai hoặc database không có người dùng.

Ví dụ dễ hình dung: ứng dụng có `DaoAuthenticationProvider` để xác thực `UsernamePasswordAuthenticationToken`, nhưng custom filter lại gửi một loại `Authentication` khác vào cùng `ProviderManager`. Nếu không có provider cho loại mới, manager không có cách kiểm chứng credential và ném `ProviderNotFoundException`.

**Phân biệt tên gọi:**

- **`Authentication`**: đối tượng mô tả request hoặc kết quả xác thực; ví dụ `UsernamePasswordAuthenticationToken`, token yêu cầu bearer/JWT, các loại token tùy chỉnh.
- **`AuthenticationProvider`**: thành phần biết cách đánh giá **một hoặc vài loại** `Authentication`.
- **`AuthenticationManager`**: API điều phối quá trình xác thực; `ProviderManager` là implementation phổ biến.
- **`ProviderNotFoundException`**: không có đường xử lý xác thực thích hợp cho request đang được đưa vào manager. Đây **không phải HTTP 404**, cũng không có nghĩa Spring container nhất thiết thiếu một bean.
- **`BadCredentialsException`**: có đường xử lý credential nhưng credential được cung cấp không hợp lệ. Hai ngoại lệ chỉ ra hai hướng chẩn đoán khác nhau.

## 2. ProviderManager quyết định chọn provider như thế nào?

`ProviderManager` nhận danh sách `AuthenticationProvider` có thứ tự. Mỗi provider cung cấp hai phương thức chủ chốt:

~~~java
boolean supports(Class<?> authentication);

Authentication authenticate(Authentication authentication)
        throws AuthenticationException;
~~~

Cách đọc hợp đồng:

1. `provider.supports(request.getClass())` trả về **false** → manager **bỏ qua** provider đó; không gọi `authenticate(...)` của nó.
2. `supports(...)` trả về **true** → provider **có khả năng đánh giá** loại token; manager mới gọi `authenticate(...)`.
3. `authenticate(...)` trả về một `Authentication` khác `null` → có kết quả; manager dừng duyệt và trả đối tượng đó (sau bước xử lý thành công).
4. `authenticate(...)` trả về **null** → provider chưa quyết định được; manager có thể thử provider tiếp theo.
5. Provider ném `AuthenticationException` → manager ghi nhận ngoại lệ và tùy loại lỗi có thể tiếp tục thử provider khác; `AccountStatusException` và `InternalAuthenticationServiceException` là những trường hợp chặn ngay trong triển khai `ProviderManager`.
6. Nếu không có kết quả cục bộ và manager có **parent AuthenticationManager**, parent được thử. Trường hợp parent trả kết quả, quá trình xác thực vẫn có thể thành công.
7. Khi không có kết quả, nếu một `AuthenticationException` phù hợp đã được ghi nhận thì manager ném ngoại lệ đó; nếu không có lỗi nào như vậy, manager tạo `ProviderNotFoundException`.

~~~text
Authentication request (ví dụ UsernamePasswordAuthenticationToken)
                       |
                       v
             ProviderManager
                       |
      +----------------+----------------+
      |                                 |
 Provider A.supports(type)?       Provider B.supports(type)?
      |                                 |
     false                              true
      |                                 |
      v                                 v
     skip                  Provider B.authenticate(request)
                                           |
                              +------------+------------+
                              |                         |
                           result != null            null
                              |                         |
                              v                         v
                            SUCCESS             thử provider tiếp
                                                        |
                                                        v
                                         parent AuthenticationManager?
                                           |              |
                                         SUCCESS       không xử lý
                                           |              |
                                           v              v
                                        SUCCESS     có lỗi trước đó?
                                                      |       |
                                                     có     không
                                                      |       |
                                                      v       v
                                             throw lỗi đã ghi   ProviderNotFoundException
~~~

**Điểm tinh tế:** `supports(...) == true` **không bảo đảm** việc đăng nhập sẽ thành công, thậm chí không bảo đảm provider có thể ra quyết định. Provider vẫn có quyền trả `null`. Vì vậy “không provider nào xử lý được” rộng hơn “không provider nào có `supports(...) == true`”.

Ngoài ra, một provider có thể ném `BadCredentialsException`, nhưng provider phía sau lại xác thực thành công; khi đó kết quả thành công thắng ngoại lệ trước. Ngược lại, khi không provider nào thành công và đã tồn tại lỗi xác thực phù hợp, thường **ngoại lệ cuối cùng** được trả về, thay vì sinh thêm `ProviderNotFoundException`. Đừng mặc định “mật khẩu sai luôn dẫn tới ProviderNotFoundException”.

## 3. Điều kiện gây ProviderNotFoundException

| Tình huống | `supports(...)` | `authenticate(...)` | Kết quả cuối nếu không có parent/provider khác |
| --- | --- | --- | --- |
| Mọi provider đều không nhận kiểu request | Tất cả `false` | Không được gọi | `ProviderNotFoundException` |
| Có provider nhận kiểu request nhưng đều trả `null` | Có ít nhất một `true` | Không provider nào ra quyết định | `ProviderNotFoundException` |
| Có provider ném `BadCredentialsException` và không provider sau thành công | Ít nhất một `true` | Có lỗi xác thực | Thường là `BadCredentialsException` |
| Một provider trả authenticated result hợp lệ | Có provider `true` | Trả `Authentication` khác null | Thành công, không có ProviderNotFoundException |
| Provider cục bộ không xử lý, parent xử lý được | Cục bộ không kết luận | Parent trả kết quả | Thành công |
| Provider cục bộ không xử lý và parent cũng trả `ProviderNotFoundException` | Không có kết quả | Không nơi nào giải quyết | Cuối cùng `ProviderNotFoundException` nếu không có lỗi khác ưu tiên |

**Không có provider trong danh sách** cũng cần hiểu đúng: `ProviderManager` bình thường yêu cầu có ít nhất một provider **hoặc** parent manager ngay khi khởi tạo. Việc gọi `new ProviderManager(List.of())` mà không có parent có thể thất bại bởi kiểm tra cấu hình trước khi tới bước `authenticate(...)`; đừng dùng cách đó để mô phỏng lỗi runtime.

## 4. Các nguyên nhân thường gặp trong ứng dụng thật

### 4.1. Filter tạo sai loại Authentication

Ví dụ `DaoAuthenticationProvider` hỗ trợ `UsernamePasswordAuthenticationToken`, nhưng custom filter tạo `TestingAuthenticationToken` hoặc một `CustomOtpAuthenticationToken`. Manager chỉ có Dao provider nên không có nơi xác thực loại mới.

~~~text
Custom filter -> CustomOtpAuthenticationToken
                      |
                      v
         ProviderManager [DaoAuthenticationProvider]
                      |
                      +-- supports(CustomOtpAuthenticationToken.class) = false
                      |
                      v
             ProviderNotFoundException
~~~

Cách sửa: Nếu thực sự là username/password, hãy gửi đúng token `UsernamePasswordAuthenticationToken.unauthenticated(username, password)`. Nếu là cơ chế OTP/magic link/thiết bị riêng, hãy tạo **provider xác minh loại credential đó** và đăng ký đúng manager; không lách bằng cách ép token mới thành username/password khi ngữ nghĩa khác nhau.

### 4.2. Có provider nhưng provider không được gắn vào manager đang chạy

Một ứng dụng có thể khai báo bean `AuthenticationProvider`, nhưng custom `ProviderManager` được tạo thủ công lại chỉ nhận các provider khác. Hoặc có **nhiều `SecurityFilterChain`**, filter của request hiện tại thuộc chain có AuthenticationManager khác với manager bạn đang nhìn trong cấu hình.

Vì vậy phải truy vết **manager thực sự được filter gọi** và danh sách provider của manager đó, không chỉ kiểm tra “trong Spring Context có bean AuthenticationProvider hay không”. Tùy cách cấu hình, một bean không nhất thiết tự động trở thành provider của mọi manager/chain.

### 4.3. `supports(...)` triển khai sai

Khi tự viết provider, đây là một mẫu thường thấy:

~~~java
@Override
public boolean supports(Class<?> authentication) {
    return CustomOtpAuthenticationToken.class.isAssignableFrom(authentication);
}
~~~

Dòng này có nghĩa “kiểu request chính là `CustomOtpAuthenticationToken` hoặc lớp con”. Nếu đảo thứ tự `isAssignableFrom`, kiểm tra có thể bỏ qua subclass hợp lệ hoặc nhận nhầm lớp cha quá rộng.

Đừng viết `return true` cho mọi loại token chỉ để làm ngoại lệ biến mất. Nếu provider không thể quyết định một loại token, hãy giới hạn `supports(...)` cho đúng kiểu hoặc trả `null` theo hợp đồng; một provider luôn nhận mọi loại mà xử lý tùy tiện có thể làm sai ranh giới xác thực.

### 4.4. Nhầm kiểu token với protocol khác

Form login có thể tạo `UsernamePasswordAuthenticationToken`; OAuth2 Resource Server xử lý Bearer token bằng chuỗi filter/provider phù hợp (ví dụ JWT provider). Nếu custom code lấy bearer token rồi bọc thành token username/password, hoặc đưa bearer request vào manager chỉ có DAO provider, cấu hình không còn khớp.

Không phải mọi implementation của `Authentication` được xử lý bởi `DaoAuthenticationProvider`. Kiểm tra **kiểu đối tượng chính xác** trên request và provider theo cơ chế đã bật.

### 4.5. Provider đúng kiểu nhưng trả `null` ở mọi nhánh

Theo contract, `null` có nghĩa “provider chưa thể quyết định”; provider sau được phép thử. Nếu provider tự viết trả `null` ngay cả khi credential **rõ ràng sai** và không có provider khác, kết quả có thể là `ProviderNotFoundException`, che khuất lỗi credential.

Với loại request provider có trách nhiệm xác minh và **biết chắc thất bại**, nên ném `AuthenticationException` phù hợp (ví dụ `BadCredentialsException`), không trả `null`. Chỉ trả `null` khi thật sự muốn nhường việc quyết định cho provider khác.

### 4.6. Parent AuthenticationManager không có hoặc không phù hợp

`ProviderManager` có thể ủy quyền lên parent nếu các provider cục bộ không ra kết quả. Nếu cấu hình dựa vào parent nhưng parent không được gắn, hoặc parent cũng không xử lý kiểu token, lỗi vẫn có thể xảy ra. Tuy nhiên **không nên thêm parent chung như một bản vá tùy tiện**: cần hiểu ranh giới chain, danh tính và chiến lược xác thực trước khi chia sẻ manager.

## 5. Demo chạy được: năm trạng thái xử lý

Bài demo Java 17 dùng **Spring Security Core 6.5.11** trong một ứng dụng Gradle độc lập. Nó minh họa:

1. Provider DAO gặp **loại token không hỗ trợ** → `ProviderNotFoundException`.
2. Cùng manager nhận **đúng loại token + mật khẩu đúng** → thành công.
3. Đúng loại token + **mật khẩu sai** → `BadCredentialsException`.
4. Provider nhận loại token nhưng **trả null** → `ProviderNotFoundException`.
5. Child manager chưa quyết định nhưng **parent manager** kiểm tra được → thành công.

`TestingAuthenticationToken` được dùng **chỉ để làm mẫu cho kiểu Authentication không khớp**; nó là lớp phục vụ test, không phải token được khuyên dùng trong đăng nhập thực tế.

Tạo thư mục:

~~~text
provider-lookup/
├── build.gradle
└── src/main/java/example/ProviderLookupDemo.java
~~~

**build.gradle:**

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
    mainClass = 'example.ProviderLookupDemo'
}
~~~

**src/main/java/example/ProviderLookupDemo.java:**

~~~java
package example;

import java.util.List;

import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.ProviderNotFoundException;
import org.springframework.security.authentication.TestingAuthenticationToken;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.InMemoryUserDetailsManager;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;

public final class ProviderLookupDemo {

    public static void main(String[] args) {
        PasswordEncoder encoder = new BCryptPasswordEncoder();
        var account = User.withUsername("mai")
                .password(encoder.encode("training-password"))
                .roles("READER")
                .build();
        var users = new InMemoryUserDetailsManager(account);

        DaoAuthenticationProvider dao = new DaoAuthenticationProvider(users);
        dao.setPasswordEncoder(encoder);
        AuthenticationManager manager = new ProviderManager(dao);

        // Trường hợp 1: DaoAuthenticationProvider không hỗ trợ token test.
        System.out.println("supports.testing="
                + dao.supports(TestingAuthenticationToken.class));
        try {
            manager.authenticate(
                    new TestingAuthenticationToken("mai", "training-password"));
            System.out.println("case1=unexpected-success");
        } catch (ProviderNotFoundException expected) {
            System.out.println("case1=ProviderNotFoundException");
        }

        // Trường hợp 2: đúng loại token; kiểm tra password thật.
        System.out.println("supports.password="
                + dao.supports(UsernamePasswordAuthenticationToken.class));
        Authentication correct = manager.authenticate(
                UsernamePasswordAuthenticationToken.unauthenticated(
                        "mai", "training-password"));
        boolean hasReaderRole = correct.getAuthorities().stream()
                .anyMatch(a -> "ROLE_READER".equals(a.getAuthority()));
        System.out.println("case2.user=" + correct.getName());
        System.out.println("case2.authenticated=" + correct.isAuthenticated());
        System.out.println("case2.reader=" + hasReaderRole);
        System.out.println("case2.credentialsErased="
                + (correct.getCredentials() == null));

        // Trường hợp 3: hỗ trợ đúng loại, nhưng credential sai.
        try {
            manager.authenticate(
                    UsernamePasswordAuthenticationToken.unauthenticated(
                            "mai", "wrong-password"));
            System.out.println("case3=unexpected-success");
        } catch (BadCredentialsException expected) {
            System.out.println("case3=BadCredentialsException");
        }

        // Provider này nhận UsernamePasswordAuthenticationToken
        // nhưng luôn nhường quyết định cho provider khác.
        AuthenticationProvider undecided = new AuthenticationProvider() {
            @Override
            public Authentication authenticate(Authentication request) {
                return null;
            }

            @Override
            public boolean supports(Class<?> type) {
                return UsernamePasswordAuthenticationToken.class
                        .isAssignableFrom(type);
            }
        };

        // Trường hợp 4: supports=true nhưng không kết quả, không parent.
        AuthenticationManager onlyUndecided = new ProviderManager(undecided);
        try {
            onlyUndecided.authenticate(
                    UsernamePasswordAuthenticationToken.unauthenticated(
                            "mai", "training-password"));
            System.out.println("case4=unexpected-success");
        } catch (ProviderNotFoundException expected) {
            System.out.println("case4=ProviderNotFoundException");
        }

        // Trường hợp 5: child không quyết định nhưng parent xử lý được.
        AuthenticationManager child = new ProviderManager(
                List.of(undecided), manager);
        Authentication fromParent = child.authenticate(
                UsernamePasswordAuthenticationToken.unauthenticated(
                        "mai", "training-password"));
        System.out.println("case5.parentFallback="
                + fromParent.isAuthenticated());
    }
}
~~~

**Chạy:** từ thư mục `provider-lookup`, dùng JDK 17+ và Gradle tương thích:

~~~bash
gradle -q run
~~~

Nếu dự án có Gradle Wrapper, dùng `./gradlew -q run` (Windows: `gradlew.bat -q run`). Các thư viện sẽ được tải lần đầu khi có mạng và Maven Central truy cập được.

**stdout do chương trình in** (bỏ qua log riêng của công cụ build nếu môi trường bật thêm logging):

~~~text
supports.testing=false
case1=ProviderNotFoundException
supports.password=true
case2.user=mai
case2.authenticated=true
case2.reader=true
case2.credentialsErased=true
case3=BadCredentialsException
case4=ProviderNotFoundException
case5.parentFallback=true
~~~

**Giải thích kết quả:**

- `supports.testing=false` xác nhận DAO provider bỏ qua `TestingAuthenticationToken`. Không có provider khác hoặc parent, nên trường hợp 1 phát sinh `ProviderNotFoundException`. Mật khẩu trong token này **chưa hề được DAO kiểm chứng**.
- `supports.password=true` cho biết provider có thể xử lý `UsernamePasswordAuthenticationToken`. Password đúng sinh authenticated result, user `mai` và quyền `ROLE_READER` từ server-side `UserDetails`.
- `case2.credentialsErased=true` là hành vi mặc định của `ProviderManager` sau thành công khi result hỗ trợ xóa credential, không phải nguyên nhân của lỗi provider lookup.
- `case3=BadCredentialsException` phân biệt một yêu cầu **đúng kiểu nhưng sai credential** với kiểu token không được hỗ trợ.
- `case4=ProviderNotFoundException` cho thấy **`supports=true` chưa đủ**: provider trả `null`, không còn nơi nào đưa ra quyết định.
- `case5.parentFallback=true` minh họa parent manager xử lý khi child không có kết quả. Parent trong demo chỉ dùng cùng cấu hình DAO; ứng dụng thật phải kiểm soát rõ ranh giới tin cậy.

**An toàn của demo:** mật khẩu cố định và user in-memory chỉ dành cho học tập. Đừng dùng mật khẩu demo, `TestingAuthenticationToken` hoặc provider luôn trả null như một phương thức đăng nhập thật. Không log raw credentials.

## 6. Debug theo thứ tự, xác định chính xác mắt xích sai

### Bước 1 – Xác định lớp Authentication đưa vào manager

Ở nơi filter gọi `authenticate(...)`, xác định lớp chính xác:

~~~java
// Đoạn minh họa trong filter/controller đã có biến "requestAuth".
// Chỉ ghi tên kiểu, KHÔNG ghi credential hoặc toString() của token.
logger.debug("Authentication request type: {}",
        requestAuth.getClass().getName());
~~~

Thông báo `No AuthenticationProvider found for ...` thường giúp nhận diện class này. Kiểm tra xem custom filter có tạo đúng token với cơ chế đăng nhập được cấu hình không.

### Bước 2 – Xác định manager thật sự được gọi

Tìm nơi filter/controller được cấp `AuthenticationManager`. Với nhiều `SecurityFilterChain`, kiểm tra **request matcher, thứ tự chain** và manager cục bộ của chain đang xử lý request. Một bean provider xuất hiện trong container **không chứng minh** nó nằm trong danh sách của manager đang chạy.

Nếu tự khởi tạo `new ProviderManager(...)`, nhìn chính xác list đã truyền. Nếu dùng cơ chế cấu hình Spring Security, truy vết provider được đăng ký cho chain/manager tương ứng. Khi có parent, cần kiểm tra cả parent.

### Bước 3 – Kiểm tra supports theo đúng class

Một cách kiểm tra giới hạn ở môi trường debug/test:

~~~java
// Đoạn minh họa; chỉ áp dụng khi biến "manager" thực sự
// là ProviderManager của luồng đang chẩn đoán.
if (manager instanceof ProviderManager pm) {
    Class<?> type = requestAuth.getClass();
    for (AuthenticationProvider provider : pm.getProviders()) {
        logger.debug("Provider {} supports {}: {}",
                provider.getClass().getSimpleName(),
                type.getSimpleName(),
                provider.supports(type));
    }
}
~~~

Nếu không có provider nào `supports(type)`, bổ sung provider xử lý **đúng cơ chế xác thực**, hoặc sửa filter để tạo đúng loại token. Nếu có provider `supports=true`, kiểm tra hành vi `authenticate(...)`: kết quả khác `null`, `null`, hay ném `AuthenticationException`.

### Bước 4 – So sánh với ngoại lệ xảy ra thực tế

| Dấu hiệu | Suy luận hữu ích | Bước tiếp theo |
| --- | --- | --- |
| `ProviderNotFoundException` với tên token lạ | Mismatch kiểu token ↔ provider, hoặc manager không đăng ký provider | Kiểm tra token class, supports, manager đang dùng |
| `ProviderNotFoundException` dù `supports=true` | Các provider có thể đã trả `null`, parent không xử lý | Kiểm tra hợp đồng authenticate của custom provider |
| `BadCredentialsException` | Có provider xác minh nhưng credential không hợp lệ; đôi khi che thông tin user không tồn tại | Kiểm tra password encoder, dữ liệu user, password hash và luồng login |
| `LockedException`, `DisabledException`, các `AccountStatusException` | Trạng thái tài khoản ngăn đăng nhập | Kiểm tra chính sách account, không thêm provider khác để vượt qua |
| `InternalAuthenticationServiceException` | Lỗi nội bộ khi xác thực, ví dụ phụ thuộc dịch vụ | Kiểm tra nguyên nhân gốc ở backend, giám sát phụ thuộc |
| Thiếu `SecurityContext` sau login thành công | Khác với provider lookup; có thể là vấn đề lưu context/session | Kiểm tra SecurityContextRepository, session, success handler |

**Không dựa riêng vào HTTP status.** Việc kết quả là 401, 403, redirect form login hay một response tùy biến phụ thuộc `AuthenticationEntryPoint`, failure handler và security filter; `ProviderNotFoundException` không tương ứng cố định với “HTTP 404” hoặc một status duy nhất.

### Bước 5 – Xác minh bằng test có ý nghĩa

Tối thiểu kiểm tra cùng một manager được dùng trong thực tế:

- Token đúng kiểu, credential hợp lệ → `Authentication` đã xác thực.
- Token đúng kiểu nhưng credential sai → ngoại lệ xác thực phù hợp, không tạo success token.
- Token không được hỗ trợ → `ProviderNotFoundException`.
- Nhiều provider hoặc parent → provider thực sự được chọn đúng theo policy; không vô tình xác thực token sai loại.

Ở cấp web, gửi request qua **đúng filter chain** và kiểm tra hiệu ứng login/401/redirect phù hợp. Test đơn thuần một bean provider sẽ không phát hiện cấu hình sai manager trên từng chain.

## 7. Cách sửa theo nguyên nhân, tránh “chữa cháy” bằng cách bỏ xác thực

| Nguyên nhân | Sửa đúng |
| --- | --- |
| Filter gửi sai loại token | Dùng token khớp với protocol và provider mong muốn |
| Custom auth flow chưa có provider | Viết provider xác minh credential thật, giới hạn `supports` và đăng ký vào manager được filter dùng |
| Provider bean không nằm trong manager/chain | Gắn provider vào đúng cấu hình hoặc `ProviderManager` thực tế; kiểm tra thứ tự `SecurityFilterChain` |
| `supports` triển khai sai | Sửa `isAssignableFrom`/kiểu token, có test đúng loại và subclass |
| Provider trả `null` dù có trách nhiệm xử lý | Trả result khi thành công, ném `AuthenticationException` khi biết thất bại; chỉ nhường khi thật sự không quyết định |
| Thiếu parent cần thiết theo thiết kế | Cấu hình parent một cách có kiểm soát; xem xét phân chia domain và chain |
| Hệ thống vốn dùng JWT/mTLS nhưng lại đi qua DAO provider | Chọn đúng authentication mechanism và resource-server/X.509 provider theo stack/cấu hình đã bật |

### Ví dụ đăng ký đúng provider trong Spring Security Servlet

Đoạn cấu hình sau là **minh họa tích hợp**, đặt trong ứng dụng Spring Boot Servlet đã có dependency `spring-boot-starter-security`, `spring-boot-starter-web`, `UserDetailsService` và `PasswordEncoder`. Nó không phải chương trình Java độc lập:

~~~java
@Bean
AuthenticationProvider passwordProvider(
        UserDetailsService users, PasswordEncoder passwordEncoder) {
    DaoAuthenticationProvider provider = new DaoAuthenticationProvider(users);
    provider.setPasswordEncoder(passwordEncoder);
    return provider;
}

@Bean
SecurityFilterChain web(HttpSecurity http,
                        AuthenticationProvider passwordProvider) throws Exception {
    http.authenticationProvider(passwordProvider);
    http.authorizeHttpRequests(a -> a.anyRequest().authenticated());
    http.formLogin(Customizer.withDefaults());
    return http.build();
}
~~~

Ở đây `http.authenticationProvider(passwordProvider)` đăng ký provider cho cấu hình security builder của chain đó; `formLogin` gửi loại authentication tương thích. Ứng dụng đa chain phải kiểm tra `SecurityFilterChain` nào thực sự nhận request, và xác định thêm các thành phần cần thiết trước khi dùng ở production (CSRF/session/entry point/password policy).

**Không sửa bằng cách** gọi `UsernamePasswordAuthenticationToken.authenticated(...)` với username/role từ client hoặc gán thẳng `SecurityContextHolder` mà chưa kiểm chứng credential. Cách đó bỏ qua quy trình xác thực và tạo lỗ hổng impersonation.

## 8. Các lỗi suy luận và lưu ý an toàn

1. **“Thêm bất kỳ AuthenticationProvider nào là hết lỗi.”** Chỉ provider hỗ trợ đúng request type và được gắn vào đúng manager mới có tác dụng.
2. **“`supports=true` nghĩa là provider xác thực thành công.”** Sai: provider có thể trả `null` hoặc ném `AuthenticationException`.
3. **“No AuthenticationProvider found nghĩa là DI không tìm thấy bean.”** Không chắc; manager hiện tại có thể không dùng bean đó hoặc loại token không khớp.
4. **“Không có provider trong constructor thì manager runtime sẽ ném ProviderNotFoundException.”** Không đúng với kiểm tra khởi tạo của `ProviderManager` không có parent.
5. **“Mật khẩu sai thì ra ProviderNotFoundException.”** Với DAO provider đúng kiểu, thường là `BadCredentialsException`.
6. **“Để tránh lỗi, provider nên hỗ trợ mọi subclass của Authentication.”** Không. Điều đó làm rộng phạm vi tin cậy vượt cơ chế dự định.
7. **“Cứ catch ProviderNotFoundException rồi cấp anonymous/authenticated token để API chạy.”** Không. Việc cấp danh tính tin cậy khi chưa xác minh là lỗi an ninh.
8. **“Provider trả null để báo credential sai.”** Không nên; khi đã xác định credential sai, phải dùng `AuthenticationException` phù hợp.
9. **“Chỉ cần sửa AuthenticationManager bean toàn cục.”** Ứng dụng có thể có nhiều chain, mỗi chain có manager riêng.
10. **“HTTP 404 là bằng chứng của ProviderNotFoundException.”** Không. 404 biểu diễn không tìm thấy tài nguyên HTTP, độc lập với ý nghĩa class ngoại lệ.
11. **“Log cả Authentication để debug.”** Nguy hiểm vì token có thể mang credentials/metadata. Chỉ log tên class, provider type và thông tin đã được kiểm soát.

## 9. Câu hỏi tự kiểm tra

**Câu 1.** `DaoAuthenticationProvider.supports(TestingAuthenticationToken.class)` trả `false`. Nếu manager chỉ có DAO provider thì mật khẩu đúng có được kiểm tra không?  
**Trả lời:** Không. Manager bỏ qua provider vì **sai loại token**; không tồn tại provider/parent khác xử lý thì `ProviderNotFoundException`.

**Câu 2.** Hai provider đều `supports(...) == true` nhưng đều trả `null`. Manager không có parent và không phát sinh ngoại lệ khác. Kết quả?  
**Trả lời:** `ProviderNotFoundException`, vì không provider nào đưa ra kết luận.

**Câu 3.** Provider A ném `BadCredentialsException`, provider B phía sau xác thực thành công request và trả non-null `Authentication`. Ngoại lệ nào được trả?  
**Trả lời:** Không có ngoại lệ được ném ra ở kết quả cuối; manager trả kết quả từ B, trừ những loại ngoại lệ buộc dừng ngay theo hợp đồng.

**Câu 4.** Ứng dụng có hai `SecurityFilterChain`. Một chain hỗ trợ login form, chain kia xử lý API bearer. Có nên mặc định cùng một manager cho cả hai?  
**Trả lời:** Không. Cần kiểm tra yêu cầu, request matcher và trust policy từng chain; mỗi chain phải có provider xử lý đúng kiểu token và quyền truy cập dự kiến.

**Câu 5.** Một bean custom provider đã tồn tại trong container nhưng vẫn lỗi ProviderNotFoundException. Điều đầu tiên phải kiểm tra là gì?  
**Trả lời:** Request có đi qua **manager chứa provider đó** và `supports(request.getClass())` có đúng hay không.

## 10. Tham khảo chính thức

- [Spring Security – Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html): `AuthenticationManager`, `ProviderManager` và chuỗi provider.
- [ProviderNotFoundException – API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/ProviderNotFoundException.html): điều kiện ngoại lệ và quan hệ với `AuthenticationException`.
- [ProviderManager – API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/ProviderManager.html): vòng lặp qua provider, xử lý `null`, lỗi, parent và credentials.
- [AuthenticationProvider – API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/AuthenticationProvider.html): hợp đồng `supports`/`authenticate`.
- [DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html): provider cho username/password, `UserDetailsService`, `PasswordEncoder`.

**Ghi nhớ:** Khi gặp `ProviderNotFoundException`, lần theo **kiểu Authentication → manager thật đang xử lý → providers của manager → supports(...) → authenticate(...) → parent**. Sửa nơi cấu hình và cơ chế credential không khớp; không bỏ qua kiểm tra danh tính chỉ để làm ngoại lệ biến mất.
