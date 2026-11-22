# Kiểm thử AuthenticationProvider.supports và các kết quả authenticate trong Spring Security

## 1. Mục tiêu: kiểm đúng hợp đồng, không chỉ kiểm một lần đăng nhập

Trong Spring Security Servlet, một `AuthenticationProvider` xử lý một hoặc nhiều kiểu `Authentication` cụ thể. Nhiều provider có thể được lắp vào `ProviderManager`; vì vậy kiểm thử thành phần cần kiểm tra **hai phương thức cùng lúc**:

~~~java
boolean supports(Class<?> authentication);

Authentication authenticate(Authentication authentication)
        throws AuthenticationException;
~~~

- `supports(...)` trả lời **provider có thể xem xét loại token được đưa vào không?** Nó không xác minh username/password và không bảo đảm lần `authenticate(...)` tiếp theo sẽ thành công.
- `authenticate(...)` có ba nhóm kết quả: **trả Authentication đã xác thực**, **trả null để nhường quyền quyết định**, hoặc **ném AuthenticationException khi xác thực thất bại**.
- `ProviderManager` kết hợp các provider theo thứ tự, kiểm `supports(...)` trước và xử lý `null`, thành công hoặc exception theo contract của framework.

Nếu chỉ test “đúng password trả user”, ta dễ bỏ sót các lỗi có tác động lớn: provider chấp nhận sai token type, `supports=true` nhưng ném lỗi cho request của provider khác, coi `null` như đăng nhập thất bại, bỏ qua tài khoản bị khóa, hoặc vô tình giữ credential trong authentication đã thành công.

Bài học thuộc nhóm **Kiểm thử thành phần**. Ví dụ sử dụng **Java 17+, Spring Boot 3.5.x và Spring Security 6.5.x**, chủ yếu kiểm lớp provider/manager bằng **JUnit 5 không khởi động web server hoặc ApplicationContext**. Các quy tắc hợp đồng cũng là cơ sở khi làm việc với Spring Security 7, nhưng hãy dùng Javadoc tương ứng phiên bản dự án.

## 2. Mối quan hệ giữa Authentication, Provider và Manager

~~~text
Servlet authentication filter
    |
    | Authentication request
    |  (ví dụ UsernamePasswordAuthenticationToken chưa trusted)
    v
AuthenticationManager (thường là ProviderManager)
    |
    +-- Provider A: supports(Class)?
    |      |
    |      +-- false -> bỏ qua
    |      +-- true  -> authenticate(...)
    |                   +-- null -> hỏi provider kế tiếp
    |                   +-- Authentication đã xác thực -> dùng kết quả
    |                   +-- AuthenticationException -> xử lý theo loại lỗi
    |
    +-- Provider B: supports(Class)? ...
    |
    +-- parent AuthenticationManager (nếu có và cần fallback)
    |
    +-- kết quả cuối: thành công HOẶC AuthenticationException
    v
Filter/caller lưu SecurityContext hoặc trả HTTP response
~~~

**Ranh giới trách nhiệm:**

- `AuthenticationProvider` **không** tự tạo HTTP redirect, 401/403 hay persist `SecurityContext`. Nó kiểm một cơ chế authentication.
- `AuthenticationManager` điều phối, quyết định có provider nào thực sự xác thực thành công.
- Filter/caller có trách nhiệm sử dụng kết quả manager, tạo SecurityContext và quản lý HTTP/session theo luồng đăng nhập.
- Authorization như `hasRole("ADMIN")` diễn ra sau authentication; user xác thực thành công vẫn có thể bị từ chối tài nguyên vì thiếu quyền.

### 2.1. Token request và token kết quả

Hai factory của `UsernamePasswordAuthenticationToken` hữu ích cho kiểm thử:

~~~java
// Input từ caller: CHƯA được xác thực.
Authentication request =
    UsernamePasswordAuthenticationToken.unauthenticated(
        "alice", "password-from-user");

// Output chỉ được tạo sau khi provider đã kiểm proof:
Authentication result =
    UsernamePasswordAuthenticationToken.authenticated(
        "alice", null,
        List.of(new SimpleGrantedAuthority("ROLE_USER")));
~~~

Hai đoạn trên là **mảnh ví dụ**, có import Spring Security thích hợp. `request.isAuthenticated()` là `false`, còn `result.isAuthenticated()` là `true`.

Trong production, **không tạo token trusted từ form input chỉ để unit test pass**; authenticated token phải là sản phẩm của provider đáng tin sau khi đã kiểm chứng credential và account status.

## 3. Hợp đồng supports(Class<?>) cần kiểm những gì?

Javadoc `AuthenticationProvider.supports(Class<?>)` định nghĩa khả năng hỗ trợ **loại Authentication**:

~~~java
@Override
public boolean supports(Class<?> authenticationType) {
    return UsernamePasswordAuthenticationToken.class
        .isAssignableFrom(authenticationType);
}
~~~

Ý nghĩa:

- `supports(UsernamePasswordAuthenticationToken.class) == true`.
- Nếu `MyPasswordToken extends UsernamePasswordAuthenticationToken`, `supports(MyPasswordToken.class) == true` nhờ `isAssignableFrom(...)`.
- `supports(TestingAuthenticationToken.class) == false` nếu provider không nhận loại đó.
- Không dùng `authenticationType == UsernamePasswordAuthenticationToken.class` khi thực sự muốn hỗ trợ các subclass hợp lệ.
- Ngược lại, nếu thiết kế chỉ an toàn với **exact token class**, kiểm đúng class có thể là chủ đích; phải nêu rõ trong test và tài liệu.

**Không nhầm hướng gọi của `isAssignableFrom`:**

~~~java
UsernamePasswordAuthenticationToken.class
    .isAssignableFrom(MyPasswordToken.class);   // true

MyPasswordToken.class
    .isAssignableFrom(UsernamePasswordAuthenticationToken.class); // false
~~~

Điều quan trọng: `supports(Class<?>)` chỉ nhận **class**, không nhận username, password, session hay token instance; nó không phải nơi xác minh credential. Hành vi đúng phải ổn định cho cùng một class trong điều kiện bình thường và không có side effect không cần thiết.

### 3.1. supports(true) vẫn có thể trả null

Javadoc nói rõ: provider trả `true` **chưa bảo đảm** provider xử lý được instance cụ thể. Ví dụ hai provider cùng xử lý `UsernamePasswordAuthenticationToken` nhưng mỗi provider phụ trách một **realm** khác nhau. Provider A có thể nói supports(type)=true rồi trả `null` cho account thuộc realm B; ProviderManager sẽ thử B.

Điều này khác hoàn toàn với **credential sai trong realm mà provider thực sự sở hữu**. Nếu password đã được kiểm và không khớp, provider nên ném `BadCredentialsException`; không nên `return null` vô điều kiện chỉ vì muốn “cho provider khác thử mật khẩu nữa”.

## 4. Ba dạng kết quả authenticate(Authentication)

| Kết quả | Contract | Khi nào hợp lý | Kiểm thử |
| --- | --- | --- | --- |
| `Authentication` không null | Provider đã xác minh và tạo kết quả đầy đủ, đáng tin | Correct credentials, account hợp lệ | `assertTrue(isAuthenticated())`, principal, authorities, credentials |
| `null` | Provider **không thể quyết định** về request này | Request khác realm/mechanism dù cùng token class | `assertNull(...)` và test fallback của ProviderManager |
| `AuthenticationException` | Provider đã thử xác thực nhưng không thành công | Password sai, tài khoản khóa/hết hạn, lỗi provider | `assertThrows(...)` đúng subclass và hậu quả manager |

### 4.1. Kết quả thành công phải có gì?

Thông thường provider trả:

- `isAuthenticated() == true` **chỉ sau xác minh đáng tin**.
- Principal đúng user đã kiểm, không đơn thuần tin username do client nhập.
- `GrantedAuthority` được lấy từ nguồn quyền đã kiểm, không tin role từ JSON client.
- Credentials không cần thiết thì đặt `null`, tránh đưa password trở lại session/cache.
- Details/audit metadata phù hợp, nhưng không log raw password hoặc Bearer token.

Nếu provider trả đối tượng không null **nhưng chưa authenticated**, đó là kết quả đáng nghi: `ProviderManager` coi non-null là đã có bên ra quyết định và có thể dừng thử provider khác. Test phải kiểm `isAuthenticated()`, không chỉ `assertNotNull(...)`.

### 4.2. Trả null không phải authenticated=false

`null` nghĩa là **“tôi không nhận trách nhiệm xác thực request này”**, không phải một token anonymous, không phải user bị sai mật khẩu và không phải 401 ngay tại provider.

Với một request chưa có provider xử lý thành công, nếu **tất cả provider bị skip hoặc trả null**, `ProviderManager` thường ném `ProviderNotFoundException` (khi không có parent thành công). Phân biệt lỗi cấu hình hỗ trợ token với sai credential.

### 4.3. Ném AuthenticationException

Các lớp điển hình:

- `BadCredentialsException`: credential không đúng.
- `LockedException`, `DisabledException`, `AccountExpiredException`: lỗi trạng thái tài khoản; đều thuộc nhóm `AccountStatusException`.
- `CredentialsExpiredException`: credentials hết hạn, cũng là loại account status exception.
- `AuthenticationServiceException` / `InternalAuthenticationServiceException`: lỗi xử lý authentication/service; không nên coi đó là “password sai”.
- `ProviderNotFoundException`: không có provider tương ứng trong chuỗi (thường do manager phát ra).

Một unit test tốt kiểm **class exception** và các bất biến an toàn, không kiểm chính xác message mà ứng dụng có thể đổi vì i18n, và không hiển thị thông tin nội bộ ra client.

## 5. ProviderManager xử lý kết quả theo thứ tự như thế nào?

Theo Javadoc Spring Security 6.5:

1. Provider có `supports(type)=false` **bị bỏ qua**; `authenticate` của nó không được gọi.
2. Provider supports=true nhưng trả `null`: manager **thử provider kế tiếp**.
3. Provider supports=true trả kết quả **không null**: manager **dừng**, dùng kết quả và không thử provider sau.
4. Provider ném `BadCredentialsException` hoặc một `AuthenticationException` thông thường: manager có thể **thử provider kế tiếp**; nếu provider sau xác thực thành công, kết quả thành công được dùng và lỗi trước đó không thắng.
5. Provider ném `AccountStatusException` (ví dụ `LockedException`): manager **dừng ngay**, không hỏi provider kế tiếp. Đây là điểm bảo mật quan trọng: tài khoản bị khóa không được “thử sang provider khác” để vượt kiểm soát.
6. Nếu không provider nào thành công nhưng có exception thông thường, **exception cuối cùng được ném** theo thứ tự thực tế.
7. Nếu không provider nào xác thực được và không có exception thích hợp, thường `ProviderNotFoundException`.
8. Nếu cấu hình **parent AuthenticationManager**, nó có thể được thử khi các provider con không quyết định thành công; cần kiểm rõ đường fallback.

Một số lỗi hệ thống nghiêm trọng như `InternalAuthenticationServiceException` cũng có đường xử lý fail-fast trong implementation phù hợp; không thiết kế fallback khi IdP/DB bị lỗi dựa trên giả định mọi exception đều được manager bỏ qua.

### 5.1. Bảng tình huống cần test

| Provider 1 | Provider 2 | Kết quả cần kiểm |
| --- | --- | --- |
| `supports=false` | success | Provider 1 không gọi `authenticate` |
| `supports=true, return null` | success | Provider 2 được gọi |
| success | success | Provider 2 **không được gọi** |
| `BadCredentialsException` | success | Kết quả success của provider 2 có thể thắng |
| `BadCredentialsException("one")` | `BadCredentialsException("two")` | Ném exception cuối khi không ai thành công |
| `LockedException` | success | Dừng ngay ở LockedException |
| null | null | Không có kết quả; ProviderNotFoundException khi không parent |
| Không provider hỗ trợ | Không | ProviderNotFoundException |
| null | parent success | Fallback lên parent nếu có |
| success chứa CredentialsContainer | — | Manager mặc định gọi eraseCredentials trước khi trả |

**Lưu ý bảo mật:** việc cho một provider thành công “đè” lỗi mật khẩu của provider khác **không phải lúc nào cũng mong muốn**. Nếu các provider cùng thẩm quyền cho một account nhưng có chính sách khác nhau, thiết kế thứ tự/provider realm hoặc account-state checks cẩn thận để không tạo bypass. Không sửa test cho pass bằng cách vô hiệu kiểm tra account status.

## 6. Chiến lược kiểm thử thành phần

Nên chia thành ba tầng:

**Tầng A — unit test provider trực tiếp:** không có web server hoặc Spring Context. Kiểm `supports` với token class hợp lệ/sai/subclass; kiểm `authenticate` với credential đúng/sai, account hoặc realm ngoài phạm vi, không leak credential.

**Tầng B — unit test ProviderManager:** lắp nhiều provider giả lập có counter/spy để chứng minh thứ tự, skip, null, exception, fallback và erase credentials. Đây là nơi kiểm semantics phối hợp mà unit test provider riêng không chứng minh được.

**Tầng C — integration test filter chain:** với `MockMvc` hoặc HTTP thật, kiểm filter nào tạo token type gì, manager wiring, response 401/redirect, `SecurityContext`, event publishing. Dùng `@WithMockUser` hoặc `with(user(...))` chỉ đặt authentication vào context, **không chứng minh authenticate(...) đã chạy**; cần request thực sự qua filter/manager.

Trong module **Kiểm thử thành phần**, ưu tiên A và B; không cần bật toàn bộ Spring Boot ApplicationContext để test 2 method contract.

## 7. Project Maven JUnit 5 chạy được với Java 17+

Ví dụ này gồm:

- Một provider demo có hai realm: user `alice` thuộc phạm vi xử lý; username có tiền tố `external:` được **defer** (trả null) cho provider khác.
- Credential được kiểm bằng `BCryptPasswordEncoder` thay vì so plaintext.
- Provider trả authenticated token với `ROLE_USER` khi thành công.
- Một class JUnit kiểm cả `supports(...)` và mọi kết quả `authenticate(...)`, cùng chuỗi provider của `ProviderManager`.

Đây là lab độc lập với database/IdP, để tập trung vào contract. Hash/password demo không dùng trong production. Ứng dụng thật nên dùng `UserDetailsService`, chính sách account status, PasswordEncoder được quản lý, rate limit, kiểm logs/PII và mô hình realm nhất quán.

### 7.1. Cấu trúc project

~~~text
provider-contract-lab/
├── pom.xml
└── src/
    ├── main/java/demo/auth/PasswordProvider.java
    └── test/java/demo/auth/PasswordProviderContractTest.java
~~~

### 7.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>provider-contract-lab</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
~~~

Spring Boot parent cung cấp Java 17 compiler settings và JUnit Platform/Surefire phù hợp. Không cần `@SpringBootTest` trong unit tests phía dưới.

### 7.3. PasswordProvider.java — provider đang được kiểm thử

~~~java
package demo.auth;

import java.util.List;

import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;

public final class PasswordProvider implements AuthenticationProvider {

    private final PasswordEncoder encoder = new BCryptPasswordEncoder();
    private final String alicePasswordHash =
            encoder.encode("lab-secret-123");

    @Override
    public boolean supports(Class<?> authenticationType) {
        // Chấp nhận token class và subclasses thuộc loại này.
        return UsernamePasswordAuthenticationToken.class
                .isAssignableFrom(authenticationType);
    }

    @Override
    public Authentication authenticate(Authentication authentication) {
        // Defensive: không cố đọc credentials của token type khác.
        if (!(authentication instanceof UsernamePasswordAuthenticationToken)) {
            return null;
        }

        // Demo: realm ngoài phạm vi của provider hiện tại.
        // supports(type) vẫn true vì cùng class, nhưng provider defer.
        String username = authentication.getName();
        if (username.startsWith("external:")) {
            return null;
        }

        Object credential = authentication.getCredentials();
        if (!"alice".equals(username)
                || !(credential instanceof String password)
                || !encoder.matches(password, alicePasswordHash)) {
            throw new BadCredentialsException("Invalid credentials");
        }

        // Chỉ provider tin cậy tạo authenticated token.
        return UsernamePasswordAuthenticationToken.authenticated(
                "alice",
                null,
                List.of(new SimpleGrantedAuthority("ROLE_USER")));
    }
}
~~~

**Đọc kỹ nhánh null:** `external:...` là một **realm minh họa** để cho phép provider khác quyết định; không phải cách fallback an toàn mặc định của mọi hệ đa tenant. Realms cần được xác định từ dữ liệu đáng tin (issuer, tenant, client registration) và thử authentication theo policy tránh credential confusion. Mọi username khác `alice` trong phạm vi provider bị coi là bad credentials.

**Đọc kỹ nhánh thành công:** `UsernamePasswordAuthenticationToken.authenticated(...)` chỉ được gọi sau `PasswordEncoder.matches(...)`. `credentials=null` tránh giữ plaintext trong authenticated token.

### 7.4. PasswordProviderContractTest.java — JUnit 5 đầy đủ

~~~java
package demo.auth;

import java.util.List;
import java.util.function.Function;

import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.LockedException;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.ProviderNotFoundException;
import org.springframework.security.authentication.TestingAuthenticationToken;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

import static org.junit.jupiter.api.Assertions.*;

class PasswordProviderContractTest {

    private static UsernamePasswordAuthenticationToken request() {
        return UsernamePasswordAuthenticationToken.unauthenticated(
                "alice", "lab-secret-123");
    }

    static final class ChildPasswordToken
            extends UsernamePasswordAuthenticationToken {
        ChildPasswordToken(String username, String password) {
            super(username, password);
        }
    }

    // Stub chủ động đếm số lần authenticate được gọi.
    // Hỗ trợ thử null / success / failure tùy Function.
    static final class ProbeProvider implements AuthenticationProvider {
        final Class<?> type;
        final Function<Authentication, Authentication> behavior;
        int calls;

        ProbeProvider(Class<?> type,
                Function<Authentication, Authentication> behavior) {
            this.type = type;
            this.behavior = behavior;
        }

        @Override
        public boolean supports(Class<?> authenticationType) {
            return type.isAssignableFrom(authenticationType);
        }

        @Override
        public Authentication authenticate(Authentication authentication) {
            calls++;
            return behavior.apply(authentication);
        }
    }

    private static Authentication trusted(String name) {
        return UsernamePasswordAuthenticationToken.authenticated(
                name,
                null,
                List.of(new SimpleGrantedAuthority("ROLE_USER")));
    }

    @Test
    void supportsChecksTypeAndSubclassButNotPassword() {
        PasswordProvider provider = new PasswordProvider();
        assertTrue(provider.supports(
                UsernamePasswordAuthenticationToken.class));
        assertTrue(provider.supports(ChildPasswordToken.class));
        assertFalse(provider.supports(TestingAuthenticationToken.class));
        assertFalse(provider.supports(Authentication.class));
    }

    @Test
    void authenticatesValidCredentialsAndSetsAuthorities() {
        Authentication actual = new PasswordProvider().authenticate(request());

        assertNotNull(actual);
        assertTrue(actual.isAuthenticated());
        assertEquals("alice", actual.getName());
        assertNull(actual.getCredentials());
        assertTrue(actual.getAuthorities().stream()
                .anyMatch(a -> "ROLE_USER".equals(a.getAuthority())));
    }

    @Test
    void rejectsBadCredentialsWithTypedException() {
        Authentication wrong =
            UsernamePasswordAuthenticationToken.unauthenticated(
                "alice", "wrong-password");

        assertThrows(BadCredentialsException.class,
                () -> new PasswordProvider().authenticate(wrong));
    }

    @Test
    void returnsNullWhenUnableToProcessInstance() {
        PasswordProvider provider = new PasswordProvider();

        assertNull(provider.authenticate(
                new TestingAuthenticationToken("alice", "anything")));

        Authentication outsideRealm =
            UsernamePasswordAuthenticationToken.unauthenticated(
                    "external:bob", "anything");

        assertTrue(provider.supports(outsideRealm.getClass()));
        assertNull(provider.authenticate(outsideRealm));
    }

    @Test
    void managerSkipsProvidersThatDoNotSupportTokenClass() {
        ProbeProvider unrelated = new ProbeProvider(
                TestingAuthenticationToken.class, ignored -> trusted("wrong"));
        ProviderManager manager = new ProviderManager(
                unrelated, new PasswordProvider());

        assertEquals("alice", manager.authenticate(request()).getName());
        assertEquals(0, unrelated.calls);
    }

    @Test
    void managerContinuesAfterNullThenStopsOnSuccess() {
        ProbeProvider abstains = new ProbeProvider(
                UsernamePasswordAuthenticationToken.class, ignored -> null);
        ProbeProvider shouldNotRun = new ProbeProvider(
                UsernamePasswordAuthenticationToken.class,
                ignored -> trusted("unexpected"));
        ProviderManager manager = new ProviderManager(
                abstains, new PasswordProvider(), shouldNotRun);

        Authentication actual = manager.authenticate(request());

        assertEquals("alice", actual.getName());
        assertEquals(1, abstains.calls);
        assertEquals(0, shouldNotRun.calls);
    }

    @Test
    void ordinaryFailureCanBeOverriddenByLaterSuccess() {
        ProbeProvider initialFailure = new ProbeProvider(
                UsernamePasswordAuthenticationToken.class,
                ignored -> {
                    throw new BadCredentialsException("first");
                });

        ProviderManager manager = new ProviderManager(
                initialFailure, new PasswordProvider());

        assertEquals("alice", manager.authenticate(request()).getName());
        assertEquals(1, initialFailure.calls);
    }

    @Test
    void accountStatusExceptionStopsFallbackImmediately() {
        ProbeProvider locked = new ProbeProvider(
                UsernamePasswordAuthenticationToken.class,
                ignored -> {
                    throw new LockedException("Account locked");
                });
        ProbeProvider fallback = new ProbeProvider(
                UsernamePasswordAuthenticationToken.class,
                ignored -> trusted("wrong"));

        ProviderManager manager = new ProviderManager(locked, fallback);
        assertThrows(LockedException.class,
                () -> manager.authenticate(request()));
        assertEquals(1, locked.calls);
        assertEquals(0, fallback.calls);
    }

    @Test
    void allNullMeansNoProviderAuthenticated() {
        ProbeProvider abstains = new ProbeProvider(
                UsernamePasswordAuthenticationToken.class, ignored -> null);

        ProviderManager manager = new ProviderManager(abstains);
        assertThrows(ProviderNotFoundException.class,
                () -> manager.authenticate(request()));
        assertEquals(1, abstains.calls);
    }

    @Test
    void noSupportingProviderThrowsProviderNotFound() {
        ProbeProvider unrelated = new ProbeProvider(
                TestingAuthenticationToken.class,
                ignored -> trusted("never"));

        ProviderManager manager = new ProviderManager(unrelated);
        assertThrows(ProviderNotFoundException.class,
                () -> manager.authenticate(request()));
        assertEquals(0, unrelated.calls);
    }

    @Test
    void lastOrdinaryAuthenticationExceptionIsPropagated() {
        ProbeProvider first = new ProbeProvider(
                UsernamePasswordAuthenticationToken.class, ignored -> {
                    throw new BadCredentialsException("first");
                });
        ProbeProvider second = new ProbeProvider(
                UsernamePasswordAuthenticationToken.class, ignored -> {
                    throw new BadCredentialsException("second");
                });

        ProviderManager manager = new ProviderManager(first, second);
        BadCredentialsException failure =
                assertThrows(BadCredentialsException.class,
                        () -> manager.authenticate(request()));

        assertEquals("second", failure.getMessage());
        assertEquals(1, first.calls);
        assertEquals(1, second.calls);
    }

    @Test
    void parentManagerIsFallbackWhenChildAbstains() {
        ProbeProvider child = new ProbeProvider(
                UsernamePasswordAuthenticationToken.class, ignored -> null);
        AuthenticationManager parent = ignored -> trusted("parent-user");

        ProviderManager manager = new ProviderManager(
                List.of(child), parent);

        assertEquals("parent-user",
                manager.authenticate(request()).getName());
        assertEquals(1, child.calls);
    }

    @Test
    void managerErasesCredentialsOfReturnedTokenByDefault() {
        ProbeProvider provider = new ProbeProvider(
                UsernamePasswordAuthenticationToken.class,
                ignored -> UsernamePasswordAuthenticationToken.authenticated(
                        "alice", "temporary-secret",
                        List.of(new SimpleGrantedAuthority("ROLE_USER"))));
        ProviderManager manager = new ProviderManager(provider);

        Authentication actual = manager.authenticate(request());

        assertTrue(actual.isAuthenticated());
        assertNull(actual.getCredentials());
    }
}
~~~

### 7.5. Chạy test và đánh giá kết quả

Trong thư mục project, với JDK 17+ và Maven:

~~~bash
mvn test
~~~

Maven tải dependencies rồi chạy test. Với mã nguồn và dependencies tương thích, kỳ vọng:

~~~text
Tests run: 13, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
~~~

Đây là **trích đoạn kết quả kỳ vọng**, không phải toàn bộ stdout (Maven bổ sung timestamps, tên class, quá trình build và độ dài chạy). Nếu có lỗi compilation, kiểm JDK version, Boot BOM, package/path Java, dependency resolution trước khi diễn giải thành hành vi Spring.

Trên Windows PowerShell/CMD cũng dùng `mvn test`; với Maven Wrapper thì dùng `mvnw.cmd test`. Không cần chạy `spring-boot:run` vì project này là **module unit test**, không có `@SpringBootApplication`. Điều đó là có chủ đích.

### 7.6. Tại sao không dùng mock toàn bộ AuthenticationProvider?

Mockito rất hữu ích khi chỉ muốn kiểm `ProviderManager` gọi đúng order:

~~~java
// Fragment Mockito; không phải test class độc lập.
when(provider.supports(UsernamePasswordAuthenticationToken.class))
    .thenReturn(true);
when(provider.authenticate(any(Authentication.class)))
    .thenReturn(null);
~~~

Nhưng chỉ dùng mock không chứng minh **provider thật** check password, account state hay tạo authorities đúng. Kết hợp **real provider test** và **stub/spy manager tests** như ví dụ giúp kiểm rõ contract mà không cần khởi động full web app.

## 8. Những điều nên assert và không nên assert

### 8.1. Bảng kiểm theo method

| Đối tượng | Assert cần thiết | Vì sao |
| --- | --- | --- |
| `supports(...)` | true cho token đúng, false cho type khác | Không nhầm mechanism |
| `supports(...)` | true cho subclass nếu chủ đích | Không bỏ sót token subtype |
| `authenticate(valid)` | authenticated true | Không trả token chưa tin |
| `authenticate(valid)` | principal đúng | Không user confusion |
| `authenticate(valid)` | authorities tối thiểu đúng | Bảo đảm role/scope |
| `authenticate(valid)` | credentials null/được xóa | Không giữ password |
| `authenticate(wrong)` | đúng AuthenticationException | Không nuốt lỗi |
| `authenticate(unhandled)` | null khi đúng ngữ nghĩa | Cho manager fallback |
| `ProviderManager` | skip unsupported providers | Không gọi sai provider |
| `ProviderManager` | null -> next | Không coi null là failure terminal |
| `ProviderManager` | success -> stop | Tránh xác thực chồng chéo |
| `ProviderManager` | LockedException -> stop | Không bypass account status |
| `ProviderManager` | fail then success | Hiểu precedence các providers |
| `ProviderManager` | all null -> ProviderNotFound | Phát hiện thiếu wiring |
| `ProviderManager` | parent fallback | Kiểm cấu hình multiple chains |
| `ProviderManager` | erase credentials | Bảo vệ session và cached secrets |

### 8.2. Những assert dễ sai

- **Chỉ `assertNotNull(authenticate(...))`:** chưa bảo đảm `isAuthenticated()`, principal, authorities đúng.
- **`assertThrows(BadCredentialsException.class)` với mọi lỗi:** tài khoản locked/disabled, provider lỗi, unsupported token có nghĩa khác.
- **Kỳ vọng `supports(...)` kiểm password:** method chỉ nhận `Class<?>`.
- **Kỳ vọng mọi provider throw exception đều dừng:** exception thông thường có thể được provider sau ghi đè; `AccountStatusException` mới là nhóm hard stop tiêu biểu.
- **Kỳ vọng `null` tương đương bad credentials:** null nghĩa không quyết định.
- **Kỳ vọng manager luôn ném lỗi đầu tiên:** nếu nhiều AuthenticationException và không success, lỗi cuối thường được dùng.
- **Kỳ vọng mọi mock context đều gọi provider:** `@WithMockUser` đặt SecurityContext trước, không chạy provider.
- **Kỳ vọng output Authentication có raw password:** người nhận nên nhận credential đã xóa/không có.

## 9. Kiểm thử các AuthenticationProvider có sẵn

Khi không tự viết provider, vẫn nên kiểm contract và cấu hình bằng integration tests phù hợp.

| Provider/flow | Input class thường gặp | Điểm kiểm thử ưu tiên |
| --- | --- | --- |
| `DaoAuthenticationProvider` | `UsernamePasswordAuthenticationToken` | PasswordEncoder, account lock/disabled, UserDetailsService, authorities |
| `JwtAuthenticationProvider` | `BearerTokenAuthenticationToken` | Chữ ký/JWK, `iss`, `aud`, `exp`, scopes, invalid token |
| `PreAuthenticatedAuthenticationProvider` | `PreAuthenticatedAuthenticationToken` | Trust boundary với reverse proxy, UserDetailsService, không tin spoofed headers |
| `CasAuthenticationProvider` | CAS-specific service-ticket token ở phiên bản tương ứng | Ticket validator, service URL binding, replay, errors |
| `LdapAuthenticationProvider` | Username/password token | Bind, LDAPS/TLS, disabled account policy, role mapping |
| Custom `AuthenticationProvider` | Custom `Authentication` | supports policy, validation, exceptions, null/fallback |

**Không ép mọi provider dùng `UsernamePasswordAuthenticationToken`**. Với JWT/opaque token hoặc X.509, request token type khác; nếu `supports(...)` viết quá rộng, manager có thể đưa sai token vào provider, gây `ClassCastException` hoặc sai cơ chế tin cậy.

Để test integration HTTP:

1. Dùng `spring-security-test` kết hợp `MockMvc` hoặc real HTTP client.
2. Gửi credentials/token qua filter đang kiểm thử, không chỉ inject authenticated principal.
3. Xác nhận request sai token bị từ chối và không tạo authenticated SecurityContext.
4. Kiểm 401/redirect với authentication failure và 403 cho authorization denial theo cấu hình.
5. Kiểm mapping exceptions và event publisher/metrics nếu cần.
6. Kiểm đa `SecurityFilterChain` và manager được sử dụng trong mỗi path.

## 10. Độ an toàn của custom provider và thứ tự fallback

Khi nhiều provider hỗ trợ cùng token type, **thứ tự có thể là quyết định bảo mật**, không chỉ quyết định kỹ thuật.

Ví dụ hệ thống hai nguồn danh tính:

~~~text
Provider A: internal user store
Provider B: external directory
~~~

Nếu `Provider A` trả `BadCredentialsException` cho user nội bộ với password sai, rồi `Provider B` tình cờ xác thực thành công cùng username, manager có thể dùng B. Điều này là hành vi hợp đồng đã biết nhưng có thể **không đúng policy** nếu username/realm không được phân biệt.

Giải pháp:

- Xác định **authority/realm** rõ ràng cho mỗi provider, chọn kiểu Authentication hoặc routing phù hợp.
- Ánh xạ principal sang namespace/issuer/tenant đáng tin; không dùng một username chuỗi làm khóa định danh toàn cục khi các nguồn có thể trùng.
- Account locked/disabled phải được áp đúng nơi có authority; không return null để bỏ qua kiểm tra trạng thái.
- Với error service/IdP outage, chọn fail closed/routing dựa trên policy, không tự động thử nguồn yếu hơn.
- Kiểm provider order và parent fallback trong test; cấu hình thay đổi có thể gây bypass mà unit test riêng provider không thấy.
- Không rò thông tin account tồn tại qua HTTP error messages, logs hay timing quá dễ phân biệt.
- Không log raw `Authentication.getCredentials()` hoặc bearer token trong failure tests.

### 10.1. CredentialsContainer và cache

Sau thành công, `ProviderManager` mặc định xóa credential của output token nếu token implements `CredentialsContainer`. Test nên chứng minh điều này.

Nếu output token giữ reference đến `UserDetails` nằm trong cache và eraseCredentials ảnh hưởng đến object dùng chung, các lần xác thực sau có thể hỏng. Cân nhắc copy principal/cache object thay vì vô hiệu hóa credential erasure toàn cục. Không để password sống lâu trong `HttpSession`.

### 10.2. ProviderManager không tự publish event nếu tự tạo

Một `ProviderManager` tạo thủ công có publisher mặc định không phát event. Nếu cần `AuthenticationSuccessEvent` hoặc failure events, nối bean:

~~~java
// Fragment: publisher đã được tạo/inject từ Spring.
ProviderManager manager = new ProviderManager(providers);
manager.setAuthenticationEventPublisher(authenticationEventPublisher);
~~~

Không lấy việc “không thấy event” làm kết luận provider không được gọi. Với parent và child manager, tránh event trùng khi cả hai đều publish.

## 11. Chẩn đoán lỗi kiểm thử

| Triệu chứng | Nguyên nhân hay gặp | Cách xử lý |
| --- | --- | --- |
| `supports(...)` trả false cho subclass | Dùng `==` thay vì `isAssignableFrom` | Xác định mong muốn, sửa/kiểm chính sách class |
| `ClassCastException` trong `authenticate` | Cast token trước khi kiểm type | Dùng `instanceof`, supports đúng |
| `ProviderNotFoundException` | Không provider nào hỗ trợ hoặc trả non-null | Kiểm token class, wiring manager, parent |
| `BadCredentialsException` bị provider sau “ghi đè” | Manager thử provider tiếp theo | Kiểm order và realm policy |
| `LockedException` nhưng provider sau vẫn chạy (trong custom manager) | Manager tự viết sai contract | Dùng ProviderManager/test hard-stop |
| Unit test provider pass nhưng HTTP 401 | Filter tạo token type khác, sai manager, config chain | Integration test đường đi thật |
| `@WithMockUser` test pass dù provider không chạy | Test inject context | Test với request credentials qua filter |
| Trả Authentication có `isAuthenticated=false` | Provider trả token request thay token trusted | Dùng factory authenticated sau verify |
| Output token còn plaintext password | Provider trả credentials/raw object, chưa erase | Trả null credentials, kiểm manager erase |
| Manager gọi provider 2 dù provider 1 success | Provider 1 thực ra trả null hoặc sai type | Spy thứ tự, kiểm return |
| Mock returns null cho unsupported provider mà không kiểm supports | Test không chứng minh skip | Assert `authenticate` không được gọi |
| Test expect first exception nhưng nhận last | Contract manager lưu exception cuối | Kiểm thứ tự provider |
| Parent manager chạy ngoài dự kiến | Local providers không quyết định | Kiểm parent fallback & policy |
| JUnit import lỗi | Chưa có starter-test hoặc Maven version không phù hợp | Kiểm parent BOM và JDK |
| Tests thất bại ngẫu nhiên | Dùng shared mutable mock/thread, đồng hồ thật | Dùng test instance mới/clock deterministic |

## 12. Checklist thực hành trước khi hoàn thành

**Contract supports**

- [ ] True cho loại token được thiết kế, false cho token ngoài phạm vi.
- [ ] Định nghĩa rõ subclass behavior và direction của `isAssignableFrom`.
- [ ] Không thực hiện password check hay gọi external IdP trong `supports(Class<?>)`.
- [ ] Không giả định `supports=true` bảo đảm kết quả non-null.

**Contract authenticate**

- [ ] Valid request tạo trusted Authentication, principal và authorities chính xác.
- [ ] Bad credentials ném `AuthenticationException` đúng loại.
- [ ] Unknown/unowned realm có thể trả null **theo policy có chủ đích**.
- [ ] Account locked/disabled không được cho fallback sai.
- [ ] Không trả authenticated result từ client-supplied role.
- [ ] Không để lộ credentials và details trong output/log.

**ProviderManager behavior**

- [ ] Skip provider `supports=false`.
- [ ] Continue sau null; stop sau success.
- [ ] Hiểu last exception vs later success.
- [ ] Hard-stop với `AccountStatusException`.
- [ ] ProviderNotFound khi không có kết quả/phù hợp.
- [ ] Parent fallback rõ và không vô tình bypass policy.
- [ ] EraseCredentials cho output implements CredentialsContainer.
- [ ] Event publishing được nối khi cần, không duplicated.

**Integration/operations**

- [ ] Filter thật đang tạo đúng token class.
- [ ] HTTP response và SecurityContext đúng sau login success/failure.
- [ ] Không nhầm `AuthenticationProvider` với `ReactiveAuthenticationManager` của WebFlux.
- [ ] Không dùng `@WithMockUser` làm bằng chứng provider đã chạy.
- [ ] Có negative tests cho account status và provider outage.
- [ ] Test code không in token/password thật hoặc gây side effects ngoài phạm vi.

## 13. Câu hỏi tự kiểm tra

1. `supports(Class<?>)` nhận tham số gì? Có thể dùng nó kiểm đúng password không?
2. `supports(...) == true` có buộc `authenticate(...)` trả token non-null không?
3. Vì sao `null` khác `BadCredentialsException`?
4. Khi nào `ProviderManager` bỏ qua một provider mà không gọi authenticate?
5. Nếu provider A trả `null` và B xác thực thành công, kết quả là gì?
6. Nếu provider A ném `BadCredentialsException` và B thành công, manager xử lý ra sao?
7. Nếu provider A ném `LockedException` thì B có được gọi không?
8. Nếu mọi provider trả null hoặc không supports token, manager thường ném gì?
9. Nếu có hai exception thông thường và không có success, exception nào được ném?
10. Vì sao chỉ kiểm `assertNotNull(authenticate(...))` là chưa đủ?
11. Vì sao không nên dùng `UsernamePasswordAuthenticationToken.authenticated(...)` trực tiếp với form input?
12. Vì sao không nên kiểm flow provider chỉ bằng `with(user(...))` của MockMvc?
13. Khi nào parent AuthenticationManager được thử?
14. Tại sao việc xóa credentials mặc định là quan trọng?

**Kết luận:** một provider đúng phải **supports chính xác loại token**, **authenticate đúng và an toàn** với cả thành công/null/exception; một manager đúng phải **bảo toàn thứ tự, fallback và hard-stop**. Bộ JUnit kiểm cả hai cấp là cách hiệu quả nhất để bắt lỗi wiring và tránh các đường vượt kiểm soát authentication khi thêm provider mới.

## 14. Tài liệu chính thức

- [Spring Security 6.5 — AuthenticationProvider API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/AuthenticationProvider.html)
- [Spring Security 6.5 — ProviderManager API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/ProviderManager.html)
- [Spring Security 6.5 — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html)
- [Spring Security 6.5 — Authentication interface](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/Authentication.html)
- [Spring Security 6.5 — UsernamePasswordAuthenticationToken](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/UsernamePasswordAuthenticationToken.html)
- [Spring Security 6.5 — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html)
- [Spring Security 6.5 — Testing](https://docs.spring.io/spring-security/reference/6.5/servlet/test/index.html)
- [JUnit 5 — Writing Tests](https://junit.org/junit5/docs/current/user-guide/#writing-tests)
