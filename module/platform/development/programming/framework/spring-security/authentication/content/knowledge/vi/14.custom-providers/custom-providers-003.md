# Cài đặt \`supports\` và kiểm tra chính xác loại thông tin xác thực trong AuthenticationProvider tùy chỉnh

## 1. Mục tiêu bài học

Khi ứng dụng Spring Security có nhiều cơ chế xác thực — ví dụ username/password, API key, OTP, certificate hoặc một loại token nội bộ — mỗi `AuthenticationProvider` chỉ nên xử lý đúng kiểu yêu cầu mà nó hiểu. Phương thức `supports(Class<?> authentication)` là “cửa chọn provider” đầu tiên; việc kiểm tra chính xác đối tượng trong `authenticate(Authentication)` là lớp phòng vệ tiếp theo.

Sau bài này, bạn có thể:

- Hiểu `AuthenticationProvider.supports` nhận **lớp token** (một đối tượng `Class<?>`), không nhận chuỗi phương thức đăng nhập hay giá trị password.
- Viết `supports` trả `true` **chỉ** với lớp token mà provider thực sự có thể xử lý; phân biệt so sánh kiểu chính xác (`==` hoặc `equals`) với việc nhận cả lớp con (`isAssignableFrom`).
- Biết `ProviderManager` dùng `supports` để chọn provider và trường hợp trả `null`, ném `AuthenticationException` hoặc không tìm thấy provider.
- Bảo vệ `authenticate` khỏi ép kiểu sai, token đã được đánh dấu xác thực không hợp lệ và credentials không đúng dạng; trả một `Authentication` đã xác minh chỉ sau khi kiểm tra credential thực sự.
- Kiểm thử cả loại token **được hỗ trợ** và **không được hỗ trợ** thay vì chỉ kiểm thử một trường hợp đăng nhập thành công.

Phạm vi là **Spring Security Servlet/Core, Java 17+, AuthenticationProvider tùy chỉnh**. Ví dụ chạy trực tiếp với `spring-security-core`, không cần dựng web server. Phần gắn vào HTTP filter được nêu để làm rõ trách nhiệm giữa các lớp.

## 2. Hiểu đúng vai trò của \`supports\`

Hợp đồng của `AuthenticationProvider` trong Spring Security 6.x:

~~~java
public interface AuthenticationProvider {
    Authentication authenticate(Authentication authentication)
        throws AuthenticationException;

    boolean supports(Class<?> authentication);
}
~~~

Ở mức khái niệm, luồng như sau:

~~~text
Client gửi credentials
        |
        v
Filter / Controller tạo một Authentication CHƯA xác thực
        |
        v
AuthenticationManager (thường là ProviderManager)
        |
        +--> provider A.supports(request.getClass()) == false -> bỏ qua A
        |
        +--> provider B.supports(request.getClass()) == true
                        |
                        v
                  B.authenticate(request)
                        |
            +-----------+-----------+
            |           |           |
      Authentication   null     AuthenticationException
       thành công       |            |
            |      thử provider    ghi nhận lỗi;
            |       tiếp theo     có thể thử provider khác
            v
     Trả kết quả về caller
~~~

Các ý cần nắm:

1. `supports(Class<?>)` nói **“tôi có khả năng xem xét loại token này”**, không nói “mật khẩu đúng”, “người dùng hợp lệ”, hay “yêu cầu đã được xác thực”.
2. `ProviderManager` thường lấy `authentication.getClass()` rồi hỏi lần lượt các provider trong danh sách. Provider trả `false` thì không được gọi `authenticate` cho yêu cầu đó.
3. `supports` trả `true` **không bảo đảm** provider sẽ chấp nhận tất cả đối tượng cùng loại. Nó vẫn có thể trả `null` nếu không thể quyết định và muốn provider phù hợp tiếp theo xét tiếp.
4. Nếu provider xác minh thành công và trả một `Authentication` **khác null**, `ProviderManager` dừng và dùng kết quả đó. Nếu provider ném `AuthenticationException`, manager có thể tiếp tục thử các provider phù hợp khác, tùy loại lỗi; không coi mọi exception là chấm dứt tuyệt đối. `AccountStatusException` là ví dụ được xử lý ngừng ngay.
5. Khi không provider nào hỗ trợ/hoàn thành xác thực và không có parent manager giải quyết, `ProviderManager` ném `ProviderNotFoundException`. Đây là vấn đề đăng ký provider hoặc loại token, không đồng nghĩa với một password sai.
6. `supports` không phải authorization. Kết quả authenticated còn phải trải qua `SecurityContext`, rule của từng endpoint hoặc method security.

Đừng viết `supports` dựa vào username/password, quyền người dùng hoặc nội dung JSON: tham số ở đây là **lớp Java**, không phải instance chứa credentials.

## 3. Kiểm tra kiểu: \`equals\`, \`==\` hay \`isAssignableFrom\`?

Giả sử ta có lớp `ApiKeyAuthenticationToken` riêng cho API key. Có ba cách viết thường gặp:

~~~java
// A. Chỉ đúng lớp ApiKeyAuthenticationToken
@Override
public boolean supports(Class<?> authentication) {
    return ApiKeyAuthenticationToken.class.equals(authentication);
}
~~~

~~~java
// B. Tương đương A khi so sánh Class chính xác
@Override
public boolean supports(Class<?> authentication) {
    return authentication == ApiKeyAuthenticationToken.class;
}
~~~

~~~java
// C. Hỗ trợ cả các lớp con của ApiKeyAuthenticationToken
@Override
public boolean supports(Class<?> authentication) {
    return ApiKeyAuthenticationToken.class.isAssignableFrom(authentication);
}
~~~

So sánh:

| Cách | `ApiKeyAuthenticationToken.class` | Lớp con `SpecialApiKeyAuthenticationToken.class` (nếu cho phép kế thừa) | `UsernamePasswordAuthenticationToken.class` |
| --- | --- | --- | --- |
| `ApiKeyAuthenticationToken.class.equals(authentication)` | `true` | `false` | `false` |
| `authentication == ApiKeyAuthenticationToken.class` | `true` | `false` | `false` |
| `ApiKeyAuthenticationToken.class.isAssignableFrom(authentication)` | `true` | `true` | `false` |

Chọn theo hợp đồng của provider:

- **Chọn kiểm tra chính xác** khi provider chỉ hiểu một loại token đặc thù, không có ý định hỗ trợ lớp con hoặc mở rộng giao thức. Đây là lựa chọn của ví dụ.
- **Chọn `isAssignableFrom`** khi việc hỗ trợ subtype là **có chủ đích**, và logic trong `authenticate` xử lý an toàn mọi subtype được nhận. Đây cũng là mẫu mà một số provider tích hợp của Spring Security sử dụng cho nhóm token của chúng.
- Trong cả hai cách, tránh đảo chiều: `authentication.isAssignableFrom(ApiKeyAuthenticationToken.class)` có thể trả `true` cho lớp rất rộng như `Authentication.class` hoặc `Object.class`, khiến provider báo rằng nó hỗ trợ những kiểu không mong muốn.
- Tránh `return true;` cho mọi class, cũng đừng viết `Authentication.class.isAssignableFrom(authentication)` nếu provider thực sự chỉ biết một token cụ thể. Hầu hết token đều triển khai `Authentication`; biểu thức đó sẽ quá rộng.

**Lưu ý:** `Class<?>` không nói được kiểu dữ liệu bên trong `getCredentials()`. Ngay cả khi token đúng class, vẫn phải kiểm tra instance chưa được xác thực, credentials đúng kiểu và giá trị hợp lệ trong `authenticate`.

## 4. Ví dụ đầy đủ Java 17+: một provider chỉ nhận API key token

Để nhìn rõ `supports` mà không bị nhiễu bởi controller, form login hay cấu hình HTTP, ví dụ này dùng **Spring Security Core 6.5.x** và `ProviderManager`. Một token tùy chỉnh riêng được tạo cho API key; `UsernamePasswordAuthenticationToken` cố tình **không** được provider hỗ trợ.

> Đây là ví dụ học cơ chế routing. API key hard-code trong code chỉ để chạy demo, **không được sử dụng trong production**. Hệ thống thực tế cần lưu secret an toàn, có khả năng thu hồi/xoay key, giới hạn truy cập, audit, HTTPS và chính sách xác thực phù hợp.

### 4.1. Tạo dự án Maven

Cấu trúc thư mục:

~~~text
provider-supports-demo/
├── pom.xml
└── src/
    ├── main/java/demo/security/ProviderSupportsDemo.java
    └── test/java/demo/security/ProviderSupportsDemoTest.java
~~~

File `pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo.security</groupId>
    <artifactId>provider-supports-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-core</artifactId>
            <version>6.5.11</version>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.4</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.4.1</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Khi dùng Spring Boot thật, để Boot BOM quản lý phiên bản tương thích của Spring Security và JUnit; không chép đè version này vào dự án hiện có một cách máy móc.

### 4.2. File Java chạy được

File `src/main/java/demo/security/ProviderSupportsDemo.java`:

~~~java
package demo.security;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Collection;
import java.util.List;
import java.util.Objects;

import org.springframework.security.authentication.AbstractAuthenticationToken;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.ProviderNotFoundException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

public class ProviderSupportsDemo {

    /**
     * Kiểu yêu cầu xác thực CHỈ dành cho API key.
     * "final" ngăn subclass âm thầm mở rộng giao thức token.
     */
    static final class ApiKeyAuthenticationToken
            extends AbstractAuthenticationToken {

        private final Object principal;
        private final String apiKey;

        private ApiKeyAuthenticationToken(
                Object principal,
                String apiKey,
                Collection<? extends GrantedAuthority> authorities,
                boolean authenticated) {

            super(authorities);
            this.principal = Objects.requireNonNull(principal);
            this.apiKey = apiKey;
            // Chỉ constructor private được quyền đặt trạng thái trusted.
            super.setAuthenticated(authenticated);
        }

        static ApiKeyAuthenticationToken unauthenticated(String rawApiKey) {
            return new ApiKeyAuthenticationToken(
                "unverified-client", rawApiKey, List.of(), false);
        }

        private static ApiKeyAuthenticationToken verified(String clientName) {
            return new ApiKeyAuthenticationToken(
                clientName,
                null, // Không mang secret sang token đã xác thực.
                List.of(new SimpleGrantedAuthority("ROLE_SERVICE")),
                true);
        }

        @Override
        public Object getPrincipal() {
            return principal;
        }

        @Override
        public Object getCredentials() {
            return apiKey;
        }

        @Override
        public void setAuthenticated(boolean authenticated) {
            if (authenticated) {
                throw new IllegalArgumentException(
                    "Cannot mark an unverified token as authenticated");
            }
            super.setAuthenticated(false);
        }
    }

    static final class ApiKeyAuthenticationProvider
            implements AuthenticationProvider {

        // KHÔNG hard-code secret trong chương trình thật.
        private static final String LEARNING_ONLY_KEY = "demo-api-key";

        @Override
        public boolean supports(Class<?> authenticationType) {
            // Chỉ chấp nhận đúng một concrete class.
            return ApiKeyAuthenticationToken.class.equals(authenticationType);
        }

        @Override
        public Authentication authenticate(Authentication authentication) {
            // Lớp phòng vệ thứ hai: không ép kiểu khi gặp token lạ.
            if (authentication == null
                    || authentication.getClass()
                       != ApiKeyAuthenticationToken.class) {
                return null;
            }

            ApiKeyAuthenticationToken request =
                (ApiKeyAuthenticationToken) authentication;

            if (request.isAuthenticated()
                    || !(request.getCredentials() instanceof String rawKey)
                    || rawKey.isBlank()) {
                throw new BadCredentialsException("Invalid API key");
            }

            byte[] supplied = rawKey.getBytes(StandardCharsets.UTF_8);
            byte[] expected =
                LEARNING_ONLY_KEY.getBytes(StandardCharsets.UTF_8);

            if (!MessageDigest.isEqual(expected, supplied)) {
                throw new BadCredentialsException("Invalid API key");
            }

            // Chỉ provider xác minh thành công mới tạo token trusted.
            return ApiKeyAuthenticationToken.verified("service-client");
        }
    }

    public static void main(String[] args) {
        AuthenticationProvider provider = new ApiKeyAuthenticationProvider();
        AuthenticationManager manager = new ProviderManager(provider);

        System.out.println("supports(api-key)=" +
            provider.supports(ApiKeyAuthenticationToken.class));
        System.out.println("supports(username-password)=" +
            provider.supports(UsernamePasswordAuthenticationToken.class));

        Authentication trusted = manager.authenticate(
            ApiKeyAuthenticationToken.unauthenticated("demo-api-key"));

        System.out.println("principal=" + trusted.getName());
        System.out.println("authenticated=" + trusted.isAuthenticated());

        try {
            manager.authenticate(
                ApiKeyAuthenticationToken.unauthenticated("wrong-key"));
        } catch (BadCredentialsException ex) {
            System.out.println("wrong-key=" +
                ex.getClass().getSimpleName());
        }

        try {
            manager.authenticate(
                UsernamePasswordAuthenticationToken.unauthenticated(
                    "alice", "password"));
        } catch (ProviderNotFoundException ex) {
            System.out.println("other-token=" +
                ex.getClass().getSimpleName());
        }
    }
}
~~~

Chạy trong thư mục chứa `pom.xml` (Maven và JDK 17+ đã cài):

~~~bash
mvn -q -DskipTests compile
mvn -q -Dexec.mainClass=demo.security.ProviderSupportsDemo exec:java
~~~

Các dòng **do chương trình chủ động in ra**:

~~~text
supports(api-key)=true
supports(username-password)=false
principal=service-client
authenticated=true
wrong-key=BadCredentialsException
other-token=ProviderNotFoundException
~~~

Maven hoặc hệ thống logging có thể phát thêm log/warning tùy môi trường. Nội dung mã và tên file/class khớp với package `demo.security`. Vì class phụ thuộc Spring Security, không chạy bằng `javac` thuần nếu chưa khai báo dependency trên classpath; Maven ở trên giải quyết dependency đó.

### 4.3. Vì sao thiết kế này đúng?

**Kiểu token khác biệt và rõ ràng.** `ApiKeyAuthenticationToken` là một `Authentication` riêng, không dùng nhầm `UsernamePasswordAuthenticationToken` để chứa API key. `final` giúp tập kiểu được hỗ trợ không thay đổi bởi việc kế thừa ngoài ý muốn.

**Factory cho trạng thái chưa xác thực.** Bất kỳ đầu vào client nào chỉ được chuyển thành `ApiKeyAuthenticationToken.unauthenticated(...)`. Cờ `authenticated=false` có nghĩa token đang chờ `AuthenticationManager` kiểm chứng.

**Quy tắc `supports` chính xác.** `ApiKeyAuthenticationProvider.supports(...)` trả `true` duy nhất cho `ApiKeyAuthenticationToken.class`. Các token username/password đi qua provider khác (nếu đăng ký), thay vì bị ép kiểu trong provider API key.

**Chốt kiểu trong `authenticate`.** Dù `ProviderManager` thông thường đã gọi `supports` trước, vẫn không nên cho rằng mọi caller đều gọi theo đúng thứ tự: test hay ứng dụng khác có thể gọi trực tiếp `provider.authenticate(foreignToken)`. Code trả `null` cho token không thuộc hợp đồng; nó không ném `ClassCastException`.

**Kiểm tra credentials tại thời điểm xác thực.** Đúng class chưa đủ: API key có thể rỗng, sai, hoặc token bị gắn sai trạng thái. Provider ném `BadCredentialsException` cho dữ liệu mà nó thực sự đã nhận trách nhiệm kiểm chứng nhưng không hợp lệ. Nó chỉ trả token `verified` khi đã xác nhận key demo.

**Đối tượng kết quả không giữ lại key.** Token trusted chứa principal và authorities do server quyết định; `getCredentials()` là `null`. `ProviderManager` cũng có chính sách xóa credentials ở kết quả nếu token implements `CredentialsContainer`; đừng phụ thuộc hoàn toàn vào cơ chế này để xử lý secret ở request đầu vào.

**Giới hạn quyền tạo trusted token.** `setAuthenticated(true)` bị chặn với caller thông thường; provider tạo kết quả qua private factory đã được kiểm soát. Đây là cách tránh nâng quyền nhờ gọi setter; cơ chế phân quyền lớp Java không thay thế việc kiểm soát input và đăng ký provider.

## 5. Kiểm thử đúng, sai và sai loại token

Một provider chỉ được xem là đúng khi nó vừa xác thực được token của mình, vừa **không tranh xử lý** token của provider khác. Kiểm thử ba mức:

1. `supports` trả đúng boolean cho `Class<?>`.
2. `authenticate` trả token trusted khi credential hợp lệ, trả `null` khi gọi trực tiếp với kiểu lạ, và ném lỗi credential khi đúng kiểu nhưng sai secret.
3. `ProviderManager` thực sự bỏ qua provider khi token không được hỗ trợ, từ đó phát sinh `ProviderNotFoundException` nếu manager này không có provider khác và không có parent manager.

File `src/test/java/demo/security/ProviderSupportsDemoTest.java`:

~~~java
package demo.security;

import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.ProviderNotFoundException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;

import static org.junit.jupiter.api.Assertions.*;

class ProviderSupportsDemoTest {

    private final ProviderSupportsDemo.ApiKeyAuthenticationProvider provider =
        new ProviderSupportsDemo.ApiKeyAuthenticationProvider();

    @Test
    void supportsOnlyExactApiKeyTokenClass() {
        assertTrue(provider.supports(
            ProviderSupportsDemo.ApiKeyAuthenticationToken.class));
        assertFalse(provider.supports(
            UsernamePasswordAuthenticationToken.class));
        assertFalse(provider.supports(Authentication.class));
        assertFalse(provider.supports(Object.class));
        assertFalse(provider.supports(null));
    }

    @Test
    void validKeyProducesAuthenticatedResultWithoutCredentials() {
        Authentication result = new ProviderManager(provider).authenticate(
            ProviderSupportsDemo.ApiKeyAuthenticationToken
                .unauthenticated("demo-api-key"));

        assertTrue(result.isAuthenticated());
        assertEquals("service-client", result.getName());
        assertNull(result.getCredentials());
        assertTrue(result.getAuthorities().stream()
            .anyMatch(a -> a.getAuthority().equals("ROLE_SERVICE")));
    }

    @Test
    void invalidKeyIsAuthenticationFailure() {
        assertThrows(BadCredentialsException.class,
            () -> new ProviderManager(provider).authenticate(
                ProviderSupportsDemo.ApiKeyAuthenticationToken
                    .unauthenticated("wrong-key")));
    }

    @Test
    void nullOrBlankKeyIsRejected() {
        assertThrows(BadCredentialsException.class,
            () -> new ProviderManager(provider).authenticate(
                ProviderSupportsDemo.ApiKeyAuthenticationToken
                    .unauthenticated(null)));
        assertThrows(BadCredentialsException.class,
            () -> new ProviderManager(provider).authenticate(
                ProviderSupportsDemo.ApiKeyAuthenticationToken
                    .unauthenticated("")));
    }

    @Test
    void directCallWithForeignTokenReturnsNullWithoutCasting() {
        Authentication other =
            UsernamePasswordAuthenticationToken.unauthenticated(
                "alice", "password");

        assertNull(provider.authenticate(other));
    }

    @Test
    void managerCannotAuthenticateUnregisteredTokenType() {
        assertThrows(ProviderNotFoundException.class,
            () -> new ProviderManager(provider).authenticate(
                UsernamePasswordAuthenticationToken.unauthenticated(
                    "alice", "password")));
    }

    @Test
    void clientCannotMarkUnverifiedTokenAsTrusted() {
        var request = ProviderSupportsDemo.ApiKeyAuthenticationToken
            .unauthenticated("invalid-key");

        assertThrows(IllegalArgumentException.class,
            () -> request.setAuthenticated(true));
        assertFalse(request.isAuthenticated());
    }
}
~~~

Chạy:

~~~bash
mvn -q test
~~~

Nếu dependency được tải và code biên dịch theo phiên bản đã nêu, dự kiến có **7 test thành công**, không có lỗi hoặc failure. Cần chạy trong dự án thực để xác nhận; đây là mã ví dụ cho người học, không phải kết quả kiểm thử đã thực thi ở môi trường production.

Các test bảo vệ những bất biến quan trọng:

| Kiểm thử | Bất biến |
| --- | --- |
| `supportsOnlyExactApiKeyTokenClass` | Provider chỉ nhận đúng `ApiKeyAuthenticationToken` |
| `validKeyProducesAuthenticatedResultWithoutCredentials` | Chỉ key hợp lệ tạo principal trusted và không lộ secret trong kết quả |
| `invalidKeyIsAuthenticationFailure` | Đúng class nhưng sai key phải bị từ chối |
| `nullOrBlankKeyIsRejected` | Không coi giá trị thiếu/rỗng là hợp lệ |
| `directCallWithForeignTokenReturnsNullWithoutCasting` | Gọi trực tiếp với token lạ không dẫn đến `ClassCastException` |
| `managerCannotAuthenticateUnregisteredTokenType` | `ProviderManager` không tự “biến” token lạ thành token API key |
| `clientCannotMarkUnverifiedTokenAsTrusted` | Không thể bật trạng thái trusted chỉ bằng setter |

## 6. Những tình huống dễ hiểu nhầm khi có nhiều provider

### 6.1. `supports` trả `true` nhưng `authenticate` trả `null`

Đây là một kết quả có ý nghĩa: provider **biết loại token**, nhưng không thể hoàn tất xác thực trường hợp cụ thể; manager có thể thử provider tiếp theo có `supports` phù hợp. Ví dụ nhiều nhà cung cấp xác thực cùng hiểu một token nhưng mỗi nhà cung cấp chịu trách nhiệm một tenant. Nếu muốn “không phải tenant của tôi”, có thể trả `null`.

Tuy nhiên, khi provider đã nhận trách nhiệm xác thực một credential và biết credential **sai**, thường phải ném `BadCredentialsException` thay vì trả `null` chỉ để né lỗi. Việc cho phép provider khác tiếp tục sau lỗi phải được thiết kế có chủ đích: `ProviderManager` có thể tiếp tục với một supporting provider khác và một lần xác thực thành công sau đó có thể thay thế lỗi trước đó. Nếu chính sách yêu cầu một credential sai phải chặn tuyệt đối, cần thiết kế thứ tự/provider routing và lỗi đặc biệt đúng semantics, không giả định `BadCredentialsException` luôn dừng mọi fallback.

### 6.2. Nhiều provider hỗ trợ cùng một loại token

~~~java
AuthenticationManager manager = new ProviderManager(
    firstProvider,
    secondProvider
);
~~~

Nếu cả hai trả `supports(TokenType.class) == true`, manager thường thử theo thứ tự. Provider đầu thành công sẽ quyết định kết quả; provider đầu trả `null` có thể nhường cho provider sau. Nếu cả hai xác thực cùng loại nhưng theo quy tắc khác nhau, phải kiểm tra kỹ fallback để tránh “provider sau chấp nhận điều provider trước từ chối”. Đừng cấu hình provider quá rộng cho mọi token chỉ để “bắt được mọi request”.

### 6.3. Không provider nào hỗ trợ

Với manager demo chỉ chứa API key provider, gửi `UsernamePasswordAuthenticationToken` tạo `ProviderNotFoundException`. Trong ứng dụng thực, cần xác nhận:

- Filter/AuthenticationConverter đã tạo **đúng class token** dự kiến.
- Provider đã được đăng ký vào đúng `AuthenticationManager` mà filter gọi.
- Nếu có nhiều `SecurityFilterChain`, request thuộc đúng chain và manager.
- `supports` dùng chiều `isAssignableFrom` hoặc phép so sánh class đúng.
- Không nhầm `AuthenticationProvider` cho Servlet với `ReactiveAuthenticationManager`/`AuthenticationWebFilter` ở WebFlux.

**Không sửa lỗi bằng `supports(...) { return true; }`.** Cách đó chỉ che giấu cấu hình sai và có thể tạo lỗi ép kiểu, định tuyến sai, hoặc auth flow ngoài ý muốn.

### 6.4. Chính xác class hay cả lớp con?

Nếu token được khai báo `final` như demo, `equals` và `isAssignableFrom` có cùng tập concrete class hợp lệ. Nhưng với một token **không final** cho phép subclass, `isAssignableFrom` rộng hơn. Hãy quyết định cụ thể có cho phép subclass nhận quyền xác thực tương tự không, thay vì mặc định chọn kiểu rộng.

Khi cho phép subclass, `authenticate` nên kiểm tra `instanceof` rồi dựa vào hợp đồng đã kiểm chứng của class cha; nếu logic chỉ an toàn cho class gốc, vẫn cần kiểm tra `getClass() == ConcreteToken.class` và từ chối subtype. Khi chỉ support exact type, kiểm tra runtime giống demo giúp ràng buộc nhất quán giữa lời khai và phần xử lý.

## 7. Gắn provider vào luồng Servlet: đúng nơi và đúng nhiệm vụ

Lớp `AuthenticationProvider` không tự đọc HTTP. Một filter hoặc controller tạo một `Authentication` chưa xác thực, rồi gọi `AuthenticationManager`. Ví dụ phần ý tưởng ở filter:

~~~java
// Đoạn minh họa bên trong một authentication converter/filter,
// chưa phải một servlet filter hoàn chỉnh:
String rawKey = request.getHeader("X-API-Key");
if (rawKey == null || rawKey.isBlank()) {
    throw new BadCredentialsException("Missing credentials");
}
Authentication candidate =
    ApiKeyAuthenticationToken.unauthenticated(rawKey);
Authentication result = authenticationManager.authenticate(candidate);
~~~

`authenticationManager` lúc này phải đăng ký `ApiKeyAuthenticationProvider`. Đoạn mã trên chỉ mô tả cách tạo và gửi token; class token của demo đang nested/package-private, nên khi tách sang các package khác cần đặt thành lớp riêng với API factory có phạm vi phù hợp. **Không** đặt API key trên URL hoặc query string; dùng header hoặc kênh xác thực được thiết kế rõ. Production nên ưu tiên cơ chế chuẩn sẵn có của Spring Security nếu đáp ứng yêu cầu.

Nếu ứng dụng còn dùng username/password thông thường, hãy giữ provider username/password riêng. Sơ đồ trách nhiệm:

~~~text
POST /api/login + username/password
    -> UsernamePasswordAuthenticationToken
    -> DaoAuthenticationProvider

GET /api/data + API key
    -> ApiKeyAuthenticationToken
    -> ApiKeyAuthenticationProvider
~~~

`supports` quyết định provider **theo token class**, không theo method HTTP, endpoint, header hay role. Việc phân luồng request/method xảy ra ở `RequestMatcher` và converter/filter (hoặc controller) **trước khi** token được đưa vào manager. Không để provider tự đọc request từ `RequestContextHolder` để quyết định `supports`.

Với web login thật, filter cần xử lý lỗi `AuthenticationException` theo thiết kế, đặt kết quả xác thực vào `SecurityContextHolder` và quyết định có lưu context vào session hay dùng token stateless. Những bước đó **ngoài phạm vi trách nhiệm trực tiếp của `supports`**.

## 8. Các lỗi triển khai thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| `supports(Class<?> c) { return true; }` | Provider tranh xử lý token không thuộc giao thức | So sánh đúng token class |
| `return Authentication.class.isAssignableFrom(c);` | Gần như mọi token Spring Security đều khớp | Dùng concrete token class |
| `return c.isAssignableFrom(MyToken.class);` | So sánh ngược chiều: class cha quá rộng được báo support | `MyToken.class.isAssignableFrom(c)` hoặc exact `equals` |
| Chỉ kiểm tra `instanceof` rồi tin credentials | Đúng class vẫn có thể mang dữ liệu rỗng/sai | Kiểm tra cấu trúc, trạng thái và credential thực tế |
| Cast ngay đầu `authenticate` | Gọi trực tiếp với token khác gây `ClassCastException` | Kiểm tra kiểu trước khi cast |
| Trả `null` khi key sai | Có thể chuyển lỗi sang provider khác ngoài dự kiến | Ném `BadCredentialsException` khi đã chịu trách nhiệm và xác định sai |
| Tạo token trusted trước khi kiểm chứng | Có thể nâng quyền trước khi gọi provider | Request token phải unauthenticated |
| Dùng token username/password cho API key chỉ vì tiện | Provider khác có thể nhận và diễn giải sai credential | Tạo token riêng cho giao thức riêng |
| Tin `supports` là phân quyền route | Loại token không quyết định quyền vào endpoint | Áp dụng authorization trên endpoint và method |
| Quên đăng ký provider vào manager của filter | Lỗi `ProviderNotFoundException` dù provider có tồn tại trong code | Kiểm tra SecurityFilterChain và AuthenticationManager thực sự được dùng |
| Đưa role từ client vào authenticated token | Client có thể tự nhận quyền | Tạo authorities từ dữ liệu server đã xác minh |
| Ghi log API key hoặc giữ secret trong token kết quả | Tăng nguy cơ lộ credential | Redact log, hạn chế lifetime và lưu trữ secret an toàn |

## 9. Checklist review code AuthenticationProvider tùy chỉnh

- [ ] Token đầu vào có concrete class thể hiện đúng cơ chế xác thực (API key, OTP, username/password...).
- [ ] `supports` dùng đúng chữ ký `boolean supports(Class<?> authentication)` và khai báo **đúng tập class** được hỗ trợ.
- [ ] Đã cân nhắc rõ exact class (`equals`/`==`) hay tất cả subtype (`isAssignableFrom`).
- [ ] `authenticate` có kiểm tra kiểu an toàn trước khi cast, kể cả trường hợp bị gọi trực tiếp.
- [ ] `authenticate` kiểm tra trạng thái chưa xác thực và dữ liệu credentials cần thiết.
- [ ] Provider không tự đặt trusted=true trước khi kiểm chứng key/password/OTP.
- [ ] Principal/authorities trong kết quả được tạo từ danh tính đã xác minh, không lấy role từ client.
- [ ] Lỗi credentials sai và trường hợp provider không xử lý được được phân biệt hợp lý (exception và `null`).
- [ ] Có test `supports` cả positive lẫn negative, test với sai credential, sai token class và luồng `ProviderManager`.
- [ ] Đăng ký provider đúng manager/chain; kiểm tra hành vi khi có nhiều provider và parent manager.
- [ ] Secret không xuất hiện trong log, URL, token authenticated hoặc output HTTP; production có quản lý và xoay secret.
- [ ] Sau thành công, quy tắc SecurityContext/session/stateless và authorization được cấu hình riêng tại filter/ứng dụng.

## 10. Câu hỏi tự kiểm tra

1. Vì sao `supports(UsernamePasswordAuthenticationToken.class) == false` không có nghĩa “password của người dùng sai”?
2. Sự khác biệt giữa `MyToken.class.equals(authentication)` và `MyToken.class.isAssignableFrom(authentication)` là gì?
3. Nếu `supports` trả `true`, có chắc Spring Security sẽ xác thực thành công không?
4. Khi nào `authenticate` nên trả `null`? Khi nào nên ném `BadCredentialsException`?
5. Vì sao một provider đã có `supports` đúng vẫn nên kiểm tra token class trong `authenticate`?
6. Điều gì xảy ra nếu manager chỉ đăng ký API key provider nhưng filter gửi `UsernamePasswordAuthenticationToken`?
7. Nếu hai provider cùng support một token, điều gì cần kiểm thử để tránh fallback vô tình chấp nhận credential sai?
8. Vì sao return value của provider cần chứa quyền từ server, thay vì roles gửi từ client?

## 11. Tài liệu chính thức

- Spring Security 6.5 API — `AuthenticationProvider`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/AuthenticationProvider.html
- Spring Security 6.5 API — `ProviderManager` (thứ tự provider, exception, erasure): https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/ProviderManager.html
- Spring Security 6.5 — Authentication Architecture: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html
- Spring Security 6.5 API — `AbstractAuthenticationToken` (trạng thái trusted, credentials): https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/AbstractAuthenticationToken.html
- Spring Security 6.5 API — `ProviderNotFoundException`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/ProviderNotFoundException.html
- Java SE — `Class.isAssignableFrom`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#isAssignableFrom(java.lang.Class)

**Thông điệp cần nhớ:** `supports` chỉ đăng ký **đúng loại Authentication mà provider có thể xem xét**; `authenticate` mới thực hiện kiểm tra credential và phát hành một đối tượng authenticated đáng tin. Kiểm tra **đúng token class** ở cả hai nơi giúp nhiều cơ chế xác thực cùng tồn tại mà không định tuyến nhầm.