# Kiểm thử ProviderManager với nhiều AuthenticationProvider và manager cha trong Spring Security

## 1. Vì sao phải kiểm thử cấu hình nhiều provider?

Trong Spring Security, `AuthenticationManager` nhận một `Authentication` chưa được tin cậy rồi xác thực nó. Implementation được dùng rộng rãi ở Servlet stack là `ProviderManager`: nó duyệt danh sách `AuthenticationProvider` theo thứ tự và có thể chuyển tiếp sang **parent `AuthenticationManager`** nếu các provider ở cấp hiện tại không tạo được kết quả xác thực.

Khi chỉ có một provider, kiểm thử “credential đúng thì login được” có vẻ đủ. Với **nhiều provider** và **manager cha**, những bug bảo mật tinh vi hơn xuất hiện:

- Provider xử lý password nội bộ thất bại nhưng một provider khác chấp nhận cùng request theo quy tắc yếu hơn.
- `supports(...)` khai báo quá rộng nên provider nhận nhầm token type; hoặc khai báo quá hẹp khiến manager báo không có provider phù hợp.
- Provider trả `null` đúng ý “không xử lý”, nhưng test lại nhầm với exception “credential sai”.
- `LockedException` hoặc lỗi dịch vụ xác thực bị fallback sai sang parent, cho phép vượt qua chính sách khóa.
- Parent bị gọi khi child đáng lẽ đã xác thực thành công; sự kiện xác thực bị publish trùng hoặc credentials không được xóa.
- Unit test chỉ dùng `MockMvc.with(user(...))`, bỏ qua toàn bộ `ProviderManager` thật mà vẫn tuyên bố đã kiểm tra chain authentication.

Bài tập trung vào **kiểm thử thành phần**: kiểm chứng chính xác `ProviderManager.authenticate(...)`, `AuthenticationProvider.supports(...)`, `AuthenticationProvider.authenticate(...)`, kết quả hoặc ngoại lệ, thứ tự và parent delegation. Các ví dụ JUnit dùng Java 17+, Spring Security 6.5.x, JUnit Jupiter 5 và Mockito. Một ví dụ Java thuần cuối bài giúp tự quan sát first-success-wins mà không cần khởi chạy Spring Boot.

### Sau bài này, bạn làm được

1. Diễn giải luồng **supports → authenticate → result/null/exception → parent → event/credential erase**.
2. Viết unit test có assertion **đúng provider được gọi/không được gọi**, không chỉ kiểm status 200/401.
3. Kiểm tra nhiều provider cùng hỗ trợ một `Authentication`, provider hỗ trợ loại token khác nhau, và parent được sử dụng đúng lúc.
4. Phân biệt `ProviderNotFoundException`, `BadCredentialsException`, `LockedException`, `InternalAuthenticationServiceException` và hiệu lực của các exception đó đối với fallback.
5. Kiểm chứng ưu tiên ngoại lệ khi child/parent đều thất bại.
6. Kiểm chứng xóa credential sau authentication và nguyên tắc không publish trùng sự kiện.
7. Nhận biết khi nào phải mở rộng thành integration test `SecurityFilterChain`/login filter, password encoder, DAO hoặc external IdP.

**Baseline:** Spring Security **6.5.11** để đối chiếu javadoc, Java 17+, Gradle/JUnit 5. Nếu dùng Spring Security 7.x hay cấu hình tùy biến khác, hãy đối chiếu source/javadoc và chạy lại cùng bộ regression tests. Phần này mô tả **Servlet/blocking `ProviderManager`**, không thay thế reactive `ReactiveAuthenticationManager`.

## 2. Vị trí của ProviderManager trong kiến trúc xác thực

```text
Incoming request
       |
       v
Authentication filter (form, Basic, Bearer, custom ...)
       |
       v
Unauthenticated Authentication token
       |
       v
AuthenticationManager.authenticate(authentication)
       |
       v
ProviderManager (child)
       |
       +--> Provider #1.supports(token.class)?
       |        false: skip
       |        true: authenticate(token)
       |              +--> Authentication: SUCCESS, stop
       |              +--> null: next provider
       |              +--> ordinary AuthenticationException: remember, continue
       |              +--> AccountStatusException / internal service error: STOP
       |
       +--> Provider #2 ...
       |
       +--> no local success -> parent AuthenticationManager, if present
       |
       +--> authenticated result or AuthenticationException
       |
       +--> erase credentials / publish events as configured
       v
Filter success/failure handling, SecurityContext/session, response
```

Đừng đảo ngược vai trò:

| Thành phần | Trách nhiệm |
| --- | --- |
| `Authentication` request | Mang principal/credentials/details cần kiểm tra; thường `isAuthenticated() = false` lúc đầu |
| `AuthenticationProvider` | Xác định có hỗ trợ **loại token** không; khi được gọi, xác minh và trả token đã xác thực, `null` hoặc exception |
| `ProviderManager` | Phối hợp **thứ tự providers**, xử lý kết quả/ngoại lệ, thử parent, xóa credential và publish events |
| Parent `AuthenticationManager` | Cơ chế fallback ở tầng quản lý; có thể là `ProviderManager` khác hoặc implementation riêng |
| `AuthenticationFilter` | Lấy credentials từ HTTP, gọi manager và xử lý success/failure |
| `SecurityContext` | Nơi kết quả auth được giữ/khôi phục theo kiến trúc request/session |
| Authorization | Kiểm tra role, authority, scope, ownership **sau khi** authentication đã có |

**Đúng nghĩa unit test:** có thể tự tạo `ProviderManager` bằng `new ProviderManager(...)` trong JUnit mà không cần HTTP request, application context hay database. Đây là ưu thế khi cần cô lập thứ tự và parent; nhưng nó cũng có giới hạn: không kiểm chứng filter, request matcher, session hay endpoint.

## 3. Bốn method và kiểu dữ liệu phải nắm

### 3.1. AuthenticationManager

```java
public interface AuthenticationManager {
    Authentication authenticate(Authentication authentication)
            throws AuthenticationException;
}
```

`AuthenticationManager` không tự nói có bao nhiêu provider; `ProviderManager` là implementation điều phối các providers.

### 3.2. AuthenticationProvider

```java
public interface AuthenticationProvider {
    Authentication authenticate(Authentication authentication)
            throws AuthenticationException;
    boolean supports(Class<?> authentication);
}
```

Trong interface contract:

- `supports(Class<?>) = false`: manager **không gọi `authenticate`** của provider đó cho request loại hiện tại.
- `supports(...) = true`: provider **có thể xem xét** token type; **không hứa** xác thực chắc chắn. Nó vẫn có thể trả `null` để provider tiếp theo xử lý.
- `authenticate(...)` trả **Authentication không null**: provider xác thực thành công; manager chọn kết quả và ngừng duyệt các provider con.
- `authenticate(...)` trả `null`: provider không đưa ra quyết định; manager tiếp tục.
- `authenticate(...)` throw `AuthenticationException`: xác thực thất bại; cách tiếp tục phụ thuộc **loại exception**.

Không nên viết custom provider trả một `Authentication` với `isAuthenticated=true` mà chưa kiểm chứng credential/issuer/challenge thật. Các object `UsernamePasswordAuthenticationToken.authenticated(...)` trong unit test chỉ là fixtures đã được kiểm soát, không phải cách xác thực production.

### 3.3. ProviderManager constructors

Spring Security 6.5 hỗ trợ:

```java
new ProviderManager(List.of(providerA, providerB));

new ProviderManager(List.of(localProvider), parentManager);

new ProviderManager(providerA, providerB);
```

Constructor thứ hai nhận `List<AuthenticationProvider>` và parent `AuthenticationManager`. Parent là **manager xác thực dự phòng**, không phải `ApplicationContext.getParent()` hay Java class inheritance.

Không cấu hình danh sách providers rỗng **và** parent null: manager yêu cầu ít nhất một nguồn xác thực. Đừng đưa `null` vào danh sách providers. Thứ tự trong `List` là dữ liệu quan trọng của chính sách.

### 3.4. Authentication token dùng trong bài

Chúng ta dùng `UsernamePasswordAuthenticationToken` để thấy rõ:

```java
UsernamePasswordAuthenticationToken request =
        UsernamePasswordAuthenticationToken.unauthenticated(
                "alice", "demo-password");

Authentication accepted =
        UsernamePasswordAuthenticationToken.authenticated(
                "alice", "secret-that-will-be-erased",
                List.of(new SimpleGrantedAuthority("ROLE_USER")));
```

`unauthenticated(...)` là **request fixture**; `authenticated(...)` biểu diễn result provider đã kiểm tra. Spring Security 6.5 cung cấp hai factory này. Với test, credentials chỉ là chuỗi giả, **không** phải mật khẩu thực hoặc secret production.

## 4. Luật duyệt nhiều provider: first-success-wins nhưng không phải first-error-wins

### 4.1. Hành vi cốt lõi

Giả sử danh sách: `[P1, P2, P3]` và request type `UsernamePasswordAuthenticationToken`:

| P1 | P2 | P3 | Kết quả |
| --- | --- | --- | --- |
| `supports=false` | thành công | không cần | P1 bị bỏ qua, dùng P2 |
| `supports=true, authenticate=null` | thành công | không cần | Dùng P2 |
| `BadCredentialsException` | thành công | không cần | **Dùng P2**; lỗi P1 không thắng |
| thành công | không được hỏi | không được hỏi | **Dùng P1**, dừng ngay |
| `BadCredentialsException("first")` | `BadCredentialsException("second")` | `null` | Không thành công; **ngoại lệ cuối cùng** `"second"` được ném (nếu không có parent thay đổi kết quả) |
| `LockedException` | không được hỏi | không được hỏi | **Ném ngay** `LockedException` |
| `InternalAuthenticationServiceException` | không được hỏi | không được hỏi | **Ném ngay**, không fallback qua provider tiếp theo |
| tất cả `supports=false` | — | — | Không có parent → `ProviderNotFoundException` |
| tất cả `null` | — | — | Không có parent → `ProviderNotFoundException` khi không còn exception nào |

Hai loại ngoại lệ cần đặc biệt lưu ý:

- `AccountStatusException` và các subclass như `LockedException`, `DisabledException`, `AccountExpiredException`, `CredentialsExpiredException`: **không tiếp tục thử provider khác** sau khi gặp chúng.
- `InternalAuthenticationServiceException`: vấn đề nội bộ của dịch vụ xác thực; **không fallback sang provider khác** vì có thể biến outage thành bypass.

`BadCredentialsException` thông thường lại có thể được provider phía sau xử lý. Đây là thiết kế của `ProviderManager`, nên nếu hai provider có các quy tắc nhận password khác nhau thì **thứ tự và chính sách hỗ trợ token type là vấn đề bảo mật**, không chỉ vấn đề hiệu năng.

### 4.2. Vì sao ngoại lệ BadCredentials có thể được “ghi đè”?

Hai provider có thể cùng hỗ trợ loại `UsernamePasswordAuthenticationToken`:

```text
P1: supports=true
    authenticate -> BadCredentialsException
           |
           v
P2: supports=true
    authenticate -> authenticated alice
           |
           v
ProviderManager -> authenticated alice
```

Điều này **có thể là chủ đích** nếu mỗi provider phục vụ một identity domain an toàn và có quy tắc fallback đúng. Nhưng nếu P1 kiểm tra password chính sách mới và P2 vẫn chấp nhận password cũ/yếu, kết quả là **security downgrade**. Muốn chặn fallback ở trạng thái đặc biệt phải dùng chính sách/provider composition có thể audit, không “cầu mong exception sẽ tự chấm dứt chain”.

### 4.3. `supports=true` không phải câu trả lời “đã xác thực”

Provider trả `supports=true` rồi `null` là hoàn toàn hợp lệ; nó nói “tôi có thể đánh giá loại token này, nhưng request cụ thể không thuộc trường hợp tôi chịu trách nhiệm”. Test cần kiểm tra cả hai pha: hỗ trợ theo class và quyết định theo nội dung.

## 5. Parent AuthenticationManager được gọi khi nào?

`ProviderManager` có thể có parent, ví dụ:

```text
ChildProviderManager
   +-- local username/password provider
   +-- local API-key provider
   |
   +-- parent AuthenticationManager
         +-- shared enterprise provider
         +-- shared emergency/account-policy provider
```

Nguyên tắc thực thi trong Spring Security 6.5: **nếu các provider cấp child chưa trả được kết quả xác thực**, manager **có thể gọi parent**. Điều này bao gồm những tình huống:

1. Không provider con nào `supports` request type.
2. Một hay nhiều provider con `supports=true` nhưng đều trả `null`.
3. Một provider con ném **AuthenticationException thông thường** và không provider con nào trả kết quả thành công, nên parent vẫn có cơ hội xác thực.

Tình huống 3 rất quan trọng: đừng diễn giải “chỉ khi không provider nào hỗ trợ” thành quy tắc chặt rằng một lần `BadCredentialsException` luôn chặn parent. Javadoc và thực thi của `ProviderManager` 6.5 cho phép parent được thử khi chưa có kết quả thành công, trừ các ngoại lệ chấm dứt sớm.

**Parent không được thử** nếu:

- Một provider con đã trả `Authentication` không null.
- Một provider con ném `AccountStatusException`.
- Một provider con ném `InternalAuthenticationServiceException`.

### 5.1. Kết quả từ parent

| Local result | Parent result | Hành vi đáng kiểm thử |
| --- | --- | --- |
| Không local result | Authenticated `Authentication` | Dùng parent result |
| Local BadCredentials | Parent authenticated | Parent **có thể thắng**, request thành công |
| Không local result | Parent `BadCredentialsException` | Ném parent exception |
| Local BadCredentials "local" | Parent BadCredentials "parent" | Parent exception là lỗi cuối |
| Local BadCredentials | Parent `ProviderNotFoundException` | Parent “không xử lý” được bỏ qua; giữ exception local |
| Không local result hoặc exception | Parent `ProviderNotFoundException` | Nếu không có lỗi local trước, ném `ProviderNotFoundException` |

Đối với **manager phân tầng**, một parent là cơ chế xử lý request ở cấp lớn hơn. Nó **không mặc nhiên an toàn hơn provider con**; một provider parent chấp nhận password yếu vẫn có thể tạo đường vòng khi child có chính sách nghiêm ngặt. Định nghĩa rõ ai được fallback, cho token type nào, giữa những realm nào.

### 5.2. Parent có thể là một ProviderManager khác

Spring Security reference mô tả nhiều child ProviderManagers dùng chung parent, chẳng hạn nhiều `SecurityFilterChain` có cơ chế auth riêng nhưng chia sẻ một provider tổ chức. Khi test, cần kiểm:

- Child A gọi provider local A rồi parent; child B gọi local B rồi cùng parent.
- Không để local A được gọi trong chain B.
- Parent dùng authentication loại nào, có chung policy khóa tài khoản hay không.
- Không gắn parent/child thành **vòng lặp**; sẽ gây vòng gọi vô hạn.
- Các provider dùng shared store/thread-safe dependency nếu được gọi đồng thời.

## 6. Exception precedence và dừng chuỗi: câu hỏi thường sai trong test

### 6.1. ProviderNotFoundException khác BadCredentialsException

`ProviderNotFoundException` nói manager không tìm được provider có khả năng xác thực loại request; nó là **lỗi cấu hình/khả năng xử lý**, không chứng minh credential của người dùng sai.

`BadCredentialsException` nói credential đã bị từ chối bởi một provider có kiểm tra request. Nếu một provider khác/parent sau đó trả authenticated result, manager có thể thành công. Nếu không, exception cuối có thể được ném.

Vì vậy:

```java
// Không coi mọi AuthenticationException là "password sai".
if (exception instanceof ProviderNotFoundException) {
    // Kiểm tra cấu hình provider / token type / parent.
}
```

Đây là trích đoạn quản trị lỗi để giải thích; **không** trả exception nội bộ chi tiết ra HTTP response cho user.

### 6.2. AccountStatusException phải chấm dứt

`LockedException` thuộc `AccountStatusException`. Nếu provider có đủ bằng chứng rằng account bị khóa, để provider khác vẫn xác thực cùng identity có thể phá chính sách khóa. `ProviderManager` chấm dứt chuỗi ngay khi exception này được ném.

Kiểm thử chính xác phải assert:

- Exception class là `LockedException`.
- Provider 2 **không** được gọi `supports` hoặc `authenticate`.
- Parent `authenticate` **không** được gọi.

Chỉ assert “login failed” là quá yếu: một cấu hình sai có thể ném lỗi cuối cùng nhưng đã gọi các provider không nên thử.

### 6.3. InternalAuthenticationServiceException chấm dứt

Ví dụ identity database bị lỗi, AS/LDAP backend trả tình trạng không thể kiểm tra danh tính. Nếu provider biến outage thành `BadCredentialsException`, `ProviderManager` có thể tiếp tục thử provider khác. Cần phân loại đúng lỗi nội bộ thành `InternalAuthenticationServiceException` khi phù hợp. Unit test phải xác minh không có fallback.

**Fail closed không có nghĩa luôn trả 401 cho caller**: HTTP status/observability của outage là chuyện riêng; phần unit test manager kiểm tra rằng **không tạo Authentication thành công** và không truy vấn fallback trái policy.

### 6.4. AuthenticationException thông thường còn được tiếp tục

Không dùng `LockedException` chỉ vì muốn ép dừng chuỗi cho mọi password sai; loại exception có semantics riêng về trạng thái account. Nếu policy muốn từ chối fallback vì credential “thuộc realm A và đã sai”, hãy tách auth token type, manager routing, provider composition hoặc một quyết định từ một centralized provider, không lạm dụng exception sai ý nghĩa.

## 7. Chuẩn bị project JUnit 5 + Mockito

Trong project **Spring Boot 3.5.x có sẵn Gradle plugin**, Java 17+, thêm dependencies:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-boot-starter-test` cung cấp JUnit Jupiter, Mockito và assertions; `spring-security-test` giúp khi bạn cần test HTTP hoặc security context. Các test ở mục 8 là **unit tests** thuần của `ProviderManager`, không bắt buộc Spring context, database, server port hay `MockMvc`.

Nếu dùng Maven, dùng dependency management của Spring Boot và `spring-boot-starter-test` với scope test; cấu hình Surefire hỗ trợ JUnit 5. Dù dùng Gradle/Maven, **không** tự hard-code hai version khác nhau của `spring-security-core` và `spring-security-test` khi có BOM quản lý.

### 7.1. Cây thư mục

```text
src/
  main/
    java/...
  test/
    java/
      demo/
        security/
          ProviderManagerBehaviorTest.java
build.gradle
```

Các test xây dựng đối tượng thật:

```java
ProviderManager manager =
        new ProviderManager(List.of(primaryProvider, secondaryProvider), parent);
```

Không dùng `@SpringBootTest` nếu mục tiêu chỉ là thứ tự providers: khởi động cả context làm test chậm, phụ thuộc configuration không cần thiết và làm khó chẩn đoán lỗi.

## 8. Bộ JUnit 5 hoàn chỉnh: nhiều provider và parent

Đặt file **`src/test/java/demo/security/ProviderManagerBehaviorTest.java`**. Code dùng **Java 17**, Mockito API của Spring Boot test starter và Spring Security 6.5. Có thể copy nguyên file vào project đã khai báo dependencies ở mục 7.

```java
package demo.security;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.mockito.InOrder;

import org.springframework.security.authentication.AuthenticationEventPublisher;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.InternalAuthenticationServiceException;
import org.springframework.security.authentication.LockedException;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.ProviderNotFoundException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

class ProviderManagerBehaviorTest {

    private static final Class<UsernamePasswordAuthenticationToken> PASSWORD =
            UsernamePasswordAuthenticationToken.class;

    private static UsernamePasswordAuthenticationToken request() {
        return UsernamePasswordAuthenticationToken
                .unauthenticated("alice", "demo-password");
    }

    private static Authentication accepted(String principal) {
        return UsernamePasswordAuthenticationToken.authenticated(
                principal,
                "temporary-secret",
                List.of(new SimpleGrantedAuthority("ROLE_USER")));
    }

    private static AuthenticationProvider provider(
            boolean supportsPassword) {
        AuthenticationProvider p = mock(AuthenticationProvider.class);
        when(p.supports(PASSWORD)).thenReturn(supportsPassword);
        return p;
    }

    @Test
    void unsupportedProviderIsSkippedThenSecondSucceeds() {
        AuthenticationProvider first = provider(false);
        AuthenticationProvider second = provider(true);
        AuthenticationManager parent = mock(AuthenticationManager.class);

        when(second.authenticate(any(Authentication.class)))
                .thenReturn(accepted("alice"));

        ProviderManager manager =
                new ProviderManager(List.of(first, second), parent);
        Authentication result = manager.authenticate(request());

        assertTrue(result.isAuthenticated());
        assertEquals("alice", result.getName());
        verify(first, never()).authenticate(any(Authentication.class));
        verify(second).authenticate(any(Authentication.class));
        verifyNoInteractions(parent);
    }

    @Test
    void nullMeansDeclineAndLaterProviderCanSucceed() {
        AuthenticationProvider first = provider(true);
        AuthenticationProvider second = provider(true);

        when(first.authenticate(any(Authentication.class)))
                .thenReturn(null);
        when(second.authenticate(any(Authentication.class)))
                .thenReturn(accepted("bob"));

        ProviderManager manager = new ProviderManager(List.of(first, second));
        Authentication result = manager.authenticate(request());

        assertEquals("bob", result.getName());
        InOrder order = inOrder(first, second);
        order.verify(first).supports(PASSWORD);
        order.verify(first).authenticate(any(Authentication.class));
        order.verify(second).supports(PASSWORD);
        order.verify(second).authenticate(any(Authentication.class));
    }

    @Test
    void firstSuccessStopsWithoutConsultingSecondOrParent() {
        AuthenticationProvider first = provider(true);
        AuthenticationProvider second = provider(true);
        AuthenticationManager parent = mock(AuthenticationManager.class);

        when(first.authenticate(any(Authentication.class)))
                .thenReturn(accepted("first"));

        ProviderManager manager =
                new ProviderManager(List.of(first, second), parent);

        assertEquals("first", manager.authenticate(request()).getName());
        verify(second, never()).authenticate(any(Authentication.class));
        verify(second, never()).supports(any());
        verifyNoInteractions(parent);
    }

    @Test
    void badCredentialsFromFirstCanBeOverriddenBySecondSuccess() {
        AuthenticationProvider first = provider(true);
        AuthenticationProvider second = provider(true);
        when(first.authenticate(any(Authentication.class)))
                .thenThrow(new BadCredentialsException("first failed"));
        when(second.authenticate(any(Authentication.class)))
                .thenReturn(accepted("second"));

        ProviderManager manager = new ProviderManager(List.of(first, second));

        Authentication result = manager.authenticate(request());
        assertEquals("second", result.getName());
        verify(first).authenticate(any(Authentication.class));
        verify(second).authenticate(any(Authentication.class));
    }

    @Test
    void lastOrdinaryAuthenticationExceptionWinsWithoutParent() {
        AuthenticationProvider first = provider(true);
        AuthenticationProvider second = provider(true);
        when(first.authenticate(any(Authentication.class)))
                .thenThrow(new BadCredentialsException("first"));
        when(second.authenticate(any(Authentication.class)))
                .thenThrow(new BadCredentialsException("second"));

        ProviderManager manager = new ProviderManager(List.of(first, second));

        BadCredentialsException ex = assertThrows(
                BadCredentialsException.class,
                () -> manager.authenticate(request()));
        assertEquals("second", ex.getMessage());
    }

    @Test
    void lockedAccountStopsBeforeSecondProviderAndParent() {
        AuthenticationProvider first = provider(true);
        AuthenticationProvider second = provider(true);
        AuthenticationManager parent = mock(AuthenticationManager.class);
        when(first.authenticate(any(Authentication.class)))
                .thenThrow(new LockedException("locked"));

        ProviderManager manager =
                new ProviderManager(List.of(first, second), parent);

        assertThrows(LockedException.class,
                () -> manager.authenticate(request()));
        verify(second, never()).supports(any());
        verify(second, never()).authenticate(any(Authentication.class));
        verifyNoInteractions(parent);
    }

    @Test
    void internalAuthenticationServiceErrorStopsWithoutFallback() {
        AuthenticationProvider first = provider(true);
        AuthenticationProvider second = provider(true);
        AuthenticationManager parent = mock(AuthenticationManager.class);
        when(first.authenticate(any(Authentication.class)))
                .thenThrow(new InternalAuthenticationServiceException(
                        "identity service unavailable"));

        ProviderManager manager =
                new ProviderManager(List.of(first, second), parent);

        assertThrows(InternalAuthenticationServiceException.class,
                () -> manager.authenticate(request()));
        verify(second, never()).authenticate(any(Authentication.class));
        verifyNoInteractions(parent);
    }

    @Test
    void parentHandlesRequestWhenAllLocalProvidersDecline() {
        AuthenticationProvider first = provider(false);
        AuthenticationProvider second = provider(true);
        AuthenticationManager parent = mock(AuthenticationManager.class);

        when(second.authenticate(any(Authentication.class)))
                .thenReturn(null);
        when(parent.authenticate(any(Authentication.class)))
                .thenReturn(accepted("parent"));

        ProviderManager manager =
                new ProviderManager(List.of(first, second), parent);

        assertEquals("parent", manager.authenticate(request()).getName());
        verify(first, never()).authenticate(any(Authentication.class));
        verify(second).authenticate(any(Authentication.class));
        verify(parent).authenticate(any(Authentication.class));
    }

    @Test
    void parentMaySucceedAfterOrdinaryLocalFailure() {
        AuthenticationProvider local = provider(true);
        AuthenticationManager parent = mock(AuthenticationManager.class);

        when(local.authenticate(any(Authentication.class)))
                .thenThrow(new BadCredentialsException("local-reject"));
        when(parent.authenticate(any(Authentication.class)))
                .thenReturn(accepted("parent"));

        ProviderManager manager =
                new ProviderManager(List.of(local), parent);

        assertEquals("parent", manager.authenticate(request()).getName());
        verify(parent).authenticate(any(Authentication.class));
    }

    @Test
    void parentOrdinaryExceptionOverridesLocalException() {
        AuthenticationProvider local = provider(true);
        AuthenticationManager parent = mock(AuthenticationManager.class);

        when(local.authenticate(any(Authentication.class)))
                .thenThrow(new BadCredentialsException("local"));
        when(parent.authenticate(any(Authentication.class)))
                .thenThrow(new BadCredentialsException("parent"));

        ProviderManager manager =
                new ProviderManager(List.of(local), parent);

        BadCredentialsException ex = assertThrows(
                BadCredentialsException.class,
                () -> manager.authenticate(request()));
        assertEquals("parent", ex.getMessage());
    }

    @Test
    void parentProviderNotFoundPreservesEarlierLocalException() {
        AuthenticationProvider local = provider(true);
        AuthenticationManager parent = mock(AuthenticationManager.class);

        when(local.authenticate(any(Authentication.class)))
                .thenThrow(new BadCredentialsException("local"));
        when(parent.authenticate(any(Authentication.class)))
                .thenThrow(new ProviderNotFoundException("not found"));

        ProviderManager manager =
                new ProviderManager(List.of(local), parent);

        BadCredentialsException ex = assertThrows(
                BadCredentialsException.class,
                () -> manager.authenticate(request()));
        assertEquals("local", ex.getMessage());
    }

    @Test
    void noSupportingProviderAndNoParentThrowsProviderNotFound() {
        AuthenticationProvider local = provider(false);
        ProviderManager manager = new ProviderManager(List.of(local));

        assertThrows(ProviderNotFoundException.class,
                () -> manager.authenticate(request()));
        verify(local, never()).authenticate(any(Authentication.class));
    }

    @Test
    void resultCredentialsAreErasedAndRequestDetailsCopied() {
        AuthenticationProvider local = provider(true);
        when(local.authenticate(any(Authentication.class)))
                .thenReturn(accepted("alice"));

        UsernamePasswordAuthenticationToken incoming = request();
        incoming.setDetails("correlation-from-filter");
        ProviderManager manager = new ProviderManager(List.of(local));

        Authentication result = manager.authenticate(incoming);

        assertTrue(result.isAuthenticated());
        assertNull(result.getCredentials());
        assertEquals("correlation-from-filter", result.getDetails());
    }

    @Test
    void parentProviderManagerPublishesSuccessEventOnlyOnce() {
        AuthenticationProvider local = provider(false);
        AuthenticationProvider parentProvider = provider(true);
        when(parentProvider.authenticate(any(Authentication.class)))
                .thenReturn(accepted("parent"));
        AuthenticationEventPublisher events =
                mock(AuthenticationEventPublisher.class);

        ProviderManager parent =
                new ProviderManager(List.of(parentProvider));
        parent.setAuthenticationEventPublisher(events);

        ProviderManager child =
                new ProviderManager(List.of(local), parent);
        child.setAuthenticationEventPublisher(events);

        Authentication result = child.authenticate(request());

        assertTrue(result.isAuthenticated());
        verify(events, times(1))
                .publishAuthenticationSuccess(any(Authentication.class));
    }
}
```

### 8.1. Cách chạy và ý nghĩa

```bash
./gradlew test --tests demo.security.ProviderManagerBehaviorTest
```

Trên Windows dùng `gradlew.bat test --tests demo.security.ProviderManagerBehaviorTest`. Với Spring Boot project và dependency đúng, kỳ vọng **14 tests PASS**. Không có stdout nghiệp vụ cố định từ JUnit/Gradle vì version/task logging khác nhau; điều cần kiểm tra là test report ghi đủ 14 và **0 failed**.

**Các test này dùng Mockito stubs** để cô lập logic manager. Chúng không chứng minh password đã được BCrypt kiểm tra, LDAP/IdP thật hoạt động hoặc session/authorization HTTP an toàn. Ngoài ra, mục tiêu của test thứ 9 là mô tả hành vi fallback của Spring Security 6.5, **không phải khuyến nghị cho mọi hệ thống rằng BadCredentials luôn nên fallback**.

### 8.2. Giải thích những assertion quan trọng

- `verify(first, never()).authenticate(...)` chứng minh `supports=false` khiến provider được bỏ qua.
- `InOrder` kiểm chứng provider 1 được đánh giá trước provider 2, không chỉ dựa vào tên principal của kết quả.
- `verify(second, never()).supports(any())` và `verifyNoInteractions(parent)` chứng minh short-circuit khi đã có success hoặc `LockedException`; phương thức `supports` cũng không được hỏi thêm.
- `assertThrows(ProviderNotFoundException.class, ...)` phân biệt cấu hình không hỗ trợ request type với “mật khẩu sai”.
- `result.getCredentials() == null` kiểm tra mặc định xóa credential trên returned `Authentication`.
- `getDetails()` thể hiện framework có thể copy details từ request gốc sang result khi result chưa có details.
- Event publisher test dùng **hai ProviderManager thật**. Nếu parent chỉ là Mockito mock trả result và không publish event, test “một sự kiện được phát bởi child” có thể đưa ra kết luận sai.

### 8.3. Các lỗi khi copy test

1. Import sai `AuthenticationProvider` ở package riêng của một SDK khác.
2. Chưa có `mockito-core`/Boot starter test trong test classpath.
3. JUnit 4 `@Test` trộn với Jupiter `@Test` khi build đã bật JUnit Platform.
4. Trả `UsernamePasswordAuthenticationToken.unauthenticated(...)` từ provider rồi mong `isAuthenticated()==true`; phải trả object đã xác thực **sau** khi provider xác minh.
5. Mockito stubbing method `authenticate` nhưng quên `supports=true`: manager sẽ không bao giờ gọi stub.
6. Dùng `HashSet` cho providers và mong thứ tự cố định: `ProviderManager` nhận **List**, không sắp xếp.
7. Mock trực tiếp `ProviderManager.authenticate` thay vì tạo instance thật: bài test lúc đó chỉ kiểm tra Mockito, không còn kiểm tra manager logic.
8. Assertion trên message exception ở production dễ brittle khi i18n/framework đổi message; bài cố ý dùng các exception tự ném với message test cố định.

## 9. Kiểm thử khi các provider hỗ trợ **hai kiểu Authentication khác nhau**

Test mục 8 dùng cùng `UsernamePasswordAuthenticationToken` để tập trung vào thứ tự, hỗ trợ/không hỗ trợ và parent. Trong hệ thống thực tế, mỗi provider có thể phục vụ **một loại authentication riêng** như username-password, Bearer access token, X.509 pre-auth hoặc OTP.

Điểm cần test: `supports(Class<?>)` nhận **class**, không nhận request instance. Chỉ sau khi supports trả true, `authenticate(Authentication)` mới nhận instance để phân biệt credential, username, issuer và tenant.

### 9.1. Token riêng để làm rõ type routing

Ví dụ định nghĩa **custom request token** trong test file cùng package:

```java
package demo.security;

import java.util.Collections;

import org.springframework.security.authentication.AbstractAuthenticationToken;

public final class EmailCodeAuthenticationToken
        extends AbstractAuthenticationToken {

    private final String username;
    private final String code;

    public EmailCodeAuthenticationToken(String username, String code) {
        super(Collections.emptyList());
        this.username = username;
        this.code = code;
        super.setAuthenticated(false);
    }

    @Override
    public Object getCredentials() {
        return code;
    }

    @Override
    public Object getPrincipal() {
        return username;
    }
}
```

Lưu file `src/test/java/demo/security/EmailCodeAuthenticationToken.java`. Đây chỉ là **token request**, không kiểm tra email code thật và không tự đánh dấu authenticated. Đặc biệt **không** dùng `setAuthenticated(true)` từ code client/controller để “vượt” manager; chỉ trusted provider được trả kết quả authenticated phù hợp.

Một provider riêng có thể khai báo:

```java
@Override
public boolean supports(Class<?> authentication) {
    return EmailCodeAuthenticationToken.class
            .isAssignableFrom(authentication);
}
```

Đoạn trên là trích đoạn **trong một AuthenticationProvider custom**, không phải một file runnable độc lập. Nó chỉ phân loại type. `authenticate` phải kiểm tra code server-side, TTL, one-time/replay, account state, rate limit và trả một `Authentication` đã authenticated hoặc exception theo policy.

### 9.2. Tại sao cần test class-specific support?

Nếu provider OTP viết `supports(Authentication.class)` theo nghĩa “tôi xử lý mọi loại token”, hoặc implementation `supports(Class<?>)` luôn trả true, nó có thể nhận cả password token và làm fallback không mong muốn. Tương tự, một provider dùng string conversion để kiểm tra token type có thể bị loại subclass. Dùng:

```java
EmailCodeAuthenticationToken.class.isAssignableFrom(authentication)
```

khi muốn chấp nhận chính xác class/subclass của token mình hiểu. Nhưng chấp nhận subclass cũng có rủi ro nếu subclass có semantic khác; test tương ứng. Đừng ép mọi provider hỗ trợ `UsernamePasswordAuthenticationToken` chỉ để tái sử dụng một form login có sẵn.

### 9.3. Thêm bài test hỗ trợ phân loại

Trong bộ test, tạo hai mock providers: passwordProvider hỗ trợ `UsernamePasswordAuthenticationToken.class`; emailCodeProvider hỗ trợ `EmailCodeAuthenticationToken.class`. Khi gửi email code, xác minh passwordProvider không gọi `authenticate` và ngược lại. Không cần HTTP server để bắt regression về `supports`.

## 10. Parent manager: thiết kế test riêng cho trường hợp nhiều child dùng chung

Giả sử ứng dụng có hai vùng: `/employee/**` và `/partner/**`, mỗi vùng có provider đăng nhập đặc thù và cả hai chia sẻ provider central identity:

```text
Employee AuthenticationManager
      |
      +-- employee-specific provider
      |
      +-------+
              |
              v
          Shared Parent
          +-- common identity provider
              ^
              |
      +-------+
      |
Partner AuthenticationManager
      |
      +-- partner-specific provider
```

Một test suite production nên có:

1. Employee credential do local employee provider chấp nhận → parent không được gọi.
2. Partner credential do local partner provider chấp nhận → parent không được gọi.
3. Credential đúng chuẩn shared identity → local declines → parent chấp nhận.
4. Credential sai nhưng thuộc realm employee → quyết định có được fallback hay không; **không** mặc định an toàn khi parent chấp nhận.
5. Account bị disabled/locked ở local hoặc shared directory → không bypass bằng một provider khác.
6. Child A và Child B gọi song song → providers có shared dependencies thread-safe; counter/metrics chính xác.
7. Login nhiều lần không tạo duplicate authentication success/failure events.
8. Mỗi chain chỉ nhận token type và security context phù hợp; parent không được suy ra quyền từ path của request chưa được tin cậy.

**Parent manager không phải kế thừa role.** Nếu child nhận Authentication từ parent, granted authorities vẫn là kết quả xác thực/authorization mapping do provider tạo. Đừng tự thêm `ROLE_ADMIN` chỉ vì fallback sang parent đã thành công.

## 11. Kiểm thử precedence của exception ở cấp child và parent

Một implementation kiểm tra nhiều realm có thể gặp nhiều exception. Hãy tách hai câu hỏi:

- **Có provider nào đã tạo authenticated result không?**
- Nếu không, **exception nào được ném và do đâu?**

Ví dụ bảng test bổ sung:

| Child P1 | Child P2 | Parent | Kết quả |
| --- | --- | --- | --- |
| Unsupported | Unsupported | Unsupported | `ProviderNotFoundException` |
| `null` | `null` | không parent | `ProviderNotFoundException` |
| `BadCredentials("A")` | `null` | không parent | `BadCredentials("A")` |
| `BadCredentials("A")` | `BadCredentials("B")` | không parent | `BadCredentials("B")` |
| `BadCredentials("A")` | `null` | Success | Success từ parent |
| `BadCredentials("A")` | `null` | `BadCredentials("P")` | `BadCredentials("P")` |
| `BadCredentials("A")` | `null` | `ProviderNotFoundException` | `BadCredentials("A")` |
| `LockedException` | không được gọi | không được gọi | `LockedException` |
| `InternalAuthenticationServiceException` | không được gọi | không được gọi | Lỗi dịch vụ nội bộ |
| Success | không được gọi | không được gọi | Success từ child đầu tiên |

Không dùng status 401 của HTTP để suy ra chính xác provider đã ném exception nào: một `AuthenticationEntryPoint` hoặc failure handler có thể ánh xạ nhiều exceptions sang cùng một body lỗi chung theo chính sách chống account enumeration.

### 11.1. Đặc biệt với parent ProviderNotFound

Nếu parent ném `ProviderNotFoundException` còn child đã ném `BadCredentialsException` trước đó, manager con có thể giữ lỗi child. Đây là chi tiết cần test theo Spring Security version, không coi “parent lỗi” luôn thay thế local exception.

### 11.2. Tránh test phụ thuộc vào log message

Mục tiêu của test component là **kết quả, thứ tự và side effects**, không phải một chuỗi log internal `"Authenticating request with..."` có thể thay đổi. Nếu cần trace, bật DEBUG/TRACE trong môi trường test với credential giả và không dùng raw password/token thật.

## 12. Xóa credentials sau khi xác thực: logic và bẫy cache

### 12.1. Mặc định ProviderManager làm gì?

Sau khi có result đã xác thực, `ProviderManager` mặc định gọi `eraseCredentials()` nếu returned `Authentication` implements `CredentialsContainer`. `UsernamePasswordAuthenticationToken` là một trường hợp như vậy. Điều này giảm thời gian tồn tại của password/raw credential trong memory/session.

```text
Provider result: principal=alice, credentials="temporary-secret"
        |
        v
ProviderManager authenticates
        |
        v
CredentialsContainer.eraseCredentials()
        |
        v
Returned Authentication: credentials=null
```

Test `result.getCredentials() == null` ở mục 8 kiểm chứng default này.

### 12.2. Có thể tắt nhưng không nên tùy tiện

Spring Security có:

```java
ProviderManager manager = new ProviderManager(List.of(provider));
manager.setEraseCredentialsAfterAuthentication(false);
```

Đây là API thực tế, nhưng **không phải cấu hình khuyến nghị mặc định**. Tắt xóa credential có thể để lại password/raw token trong `SecurityContext` hoặc session. Nếu một application cố ý giữ credential để gọi dịch vụ khác, nên xem lại kiến trúc ủy quyền và cách lưu secret, không mặc định giữ raw password vô thời hạn.

### 12.3. CredentialsContainer và cached UserDetails

Nếu principal/details/result chứa object implements `CredentialsContainer` và object đó cũng được cache/reuse giữa requests, hành vi erase có thể làm hỏng khả năng dùng lại đối tượng cached (ví dụ credential bị null trên cached principal). Spring Security documentation cảnh báo cần thiết kế copy/immutable snapshot hoặc chính sách cache phù hợp; đừng tắt credential erase một cách vô thức để chữa triệu chứng.

Để test trường hợp này: dùng provider thật hoặc fixture principal implements `CredentialsContainer`, xác minh erase được gọi trên returned result đúng một lần và không vô tình xóa nguồn dữ liệu dùng lại. Không đặt password hash thật trong test logs.

## 13. Authentication events: tại sao test parent phải cẩn thận?

`ProviderManager` hỗ trợ `AuthenticationEventPublisher`. Mặc định khi bạn tạo một manager bằng constructor trực tiếp trong unit test, event publisher là một implementation không phát sự kiện; muốn kiểm tra event cần **gắn publisher**:

```java
AuthenticationEventPublisher publisher =
        mock(AuthenticationEventPublisher.class);

ProviderManager manager = new ProviderManager(List.of(provider));
manager.setAuthenticationEventPublisher(publisher);
```

Một `DefaultAuthenticationEventPublisher` trong Spring application sẽ ánh xạ các exception phổ biến sang failure events và publish success events. Nhưng event delivery là chức năng có thể tùy biến, không nên dựa vào việc một Mockito parent tự phát event khi stub `authenticate`.

### 13.1. Chi tiết khi có parent

Spring Security 6.5 cố giảm duplicate authentication events khi manager con nhận kết quả/lỗi từ parent. Vì vậy:

- **Unit test parent là mock**: mock chỉ trả Authentication, không tự phát event; không thể lấy số event phát ra để đánh giá toàn bộ production pipeline.
- **Hai ProviderManager thật**: cấu hình publisher đúng kiến trúc, test số event cuối cùng. Bộ test mục 8 dùng chung mock publisher cho parent và child để kiểm tra success event không bị nhân đôi.
- **Custom parent**: cần biết manager nào chịu trách nhiệm publish; không coi child sẽ tự tạo event khi parent custom không làm.
- **Failure events**: mapping exception class sang event có thể phụ thuộc publisher; test publisher implementation nếu policy audit/monitoring dựa vào event type.

Đừng viết code production publish cùng một sự kiện thủ công ở provider, success handler, child manager, parent manager mà không có idempotency/correlation. Một lần login có thể bị đếm thành nhiều sự kiện hoặc nhiều cảnh báo gian lận.

### 13.2. Kiểm thử an toàn với event

`verify(publisher, times(1)).publishAuthenticationSuccess(...)` giúp kiểm số lần ở unit level. Với integration test Spring ApplicationContext, có thể dùng `@EventListener` hoặc test event collector để kiểm chứng số sự kiện và principal/metadata **được phép ghi log**; không sao chép raw credentials vào events.

## 14. Unit test ProviderManager khác với unit test AuthenticationProvider

Để tránh test lẫn tầng:

| Test level | Đối tượng chính | Cần mock gì? | Điều được chứng minh |
| --- | --- | --- | --- |
| `ProviderManager` unit test | Manager thật | Providers/parent giả lập | Thứ tự, supports, null, exception, parent, erase, events |
| `DaoAuthenticationProvider` unit test | DAO provider thật | `UserDetailsService`, PasswordEncoder tùy test | Password comparison, account locked/disabled/expired |
| Custom OTP provider unit test | Provider thật | Token service/repository | TTL, one-time consume, account check |
| JWT/opaque provider unit test | Provider/manager thật | `JwtDecoder` / introspector | Token validation/claims theo contract |
| Servlet filter integration | SecurityFilterChain thật | External backend thay thế | HTTP request, filter calls, SecurityContext, success/failure handlers |
| End-to-end login | Full deployed app + IdP/DB | Ít hoặc không mock security-critical dependencies | Quá trình đăng nhập và chính sách nghiệp vụ thực tế |

**Anti-pattern:** mock `AuthenticationManager.authenticate(...)` rồi assert API trả 200, sau đó gọi đó là “kiểm thử ProviderManager”. Test ấy không chạy `ProviderManager`. Ngược lại, unit test Manager không có HTTP filter **không chứng minh** header/cookie/CSRF/Session fixation được xử lý đúng.

### 14.1. Tại sao MockMvc.with(user(...)) không test authentication?

`SecurityMockMvcRequestPostProcessors.user("alice")` tạo principal giả cho HTTP request, bỏ qua password verification/provider traversal. Nó rất hữu ích để test **authorization**, nhưng không phù hợp nếu mục tiêu là chứng minh parent `AuthenticationManager` được gọi.

Muốn test auth flow HTTP cần request login thực hoặc test authentication filter với provider chain thật/stub, rồi quan sát event/status/session; unit test Manager vẫn là cách tốt nhất để xác định thứ tự.

## 15. Gắn nhiều providers vào ứng dụng Spring Security: cấu hình và test

Trong ứng dụng Servlet, một `SecurityFilterChain` có thể dùng nhiều authentication mechanisms, và Spring Security sẽ dựng `AuthenticationManager` nội bộ theo DSL/configurers. Khi muốn thay manager bằng custom `ProviderManager`, phải cấu hình rõ phạm vi và kiểm tra side effects.

Ví dụ **trích đoạn trong method cấu hình** (không phải project runnable độc lập):

```java
@Bean
SecurityFilterChain filterChain(
        HttpSecurity http,
        AuthenticationProvider ldapProvider,
        AuthenticationProvider localPasswordProvider)
        throws Exception {

    AuthenticationManager sharedParent =
            new ProviderManager(List.of(localPasswordProvider));

    AuthenticationManager child =
            new ProviderManager(List.of(ldapProvider), sharedParent);

    http
            .authenticationManager(child)
            .authorizeHttpRequests(auth -> auth
                    .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults());

    return http.build();
}
```

**Cảnh báo:** Đây là **cấu trúc minh họa**. Provider LDAP/DAO phải được cấu hình và test thật, account-status policy phải nhất quán; builder `http.authenticationManager(child)` có thể ảnh hưởng các filter cơ chế khác. Nếu bạn khai báo manager này dưới một `SecurityFilterChain`, không suy ra nó tự trở thành global manager cho mọi chain khác.

Không đặt một “fallback localPasswordProvider” với password yếu hơn LDAP chỉ để giữ hệ thống hoạt động khi directory outage. Khi LDAP không kiểm tra được, provider nên báo đúng loại lỗi dịch vụ, và runbook xử lý outage phải được định nghĩa; nếu không, bạn vô tình tạo **authentication bypass**.

### 15.1. Kết hợp nhiều filter chains

Giả sử:

```java
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    return http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                    .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults())
            .build();
}

@Bean
@Order(2)
SecurityFilterChain webChain(HttpSecurity http) throws Exception {
    return http
            .authorizeHttpRequests(auth -> auth
                    .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .build();
}
```

Đoạn này **không đủ để triển khai đúng provider chains**; chỉ minh họa lựa chọn `SecurityFilterChain` theo request. Cấu hình shared parent/local managers cần được gắn tường minh vào chains nếu đó là architecture mong muốn. Tránh coi hai `SecurityFilterChain` mặc nhiên chia sẻ mọi provider qua một parent.

### 15.2. Chọn provider theo token type thay vì dựa vào URL không đáng tin

Nếu API có Bearer token và browser có form login, có thể dùng **các loại `Authentication` khác nhau** và `supports(Class<?>)` phù hợp. `ProviderManager` không tự nhận request path/HTTP headers, trừ thông tin được filter chuyển vào request details. Không nên dựa trên `request.getParameter("provider")` do client điều khiển để quyết định bỏ qua provider nghiêm ngặt.

## 16. Tích hợp HTTP với MockMvc: test đúng hai lớp

Để chứng minh integration hoạt động:

1. Cấu hình một `SecurityFilterChain` thực với form login/filter, authentication manager và các provider đã chọn.
2. Với `MockMvc`, gửi `POST /login` theo method/form đúng, có CSRF token nếu bật mặc định.
3. Kiểm tra login success/failure response và kết quả `SecurityContext`.
4. Dùng Mockito `verify(...)` trên provider/parent **được inject vào chain thực**, không mock `AuthenticationManager.authenticate`.
5. Thử anonymous, user locked, provider unsupported, wrong password và authenticated-but-forbidden.
6. Tách test HTTP redirect/401 khỏi test provider exception precedence; lỗi HTTP có thể đi qua failure handler và mã status khác tùy config.

Ví dụ **trích đoạn MockMvc** (chưa phải file test hoàn chỉnh):

```java
mvc.perform(formLogin()
                .user("alice")
                .password("test-password"))
        .andExpect(authenticated().withUsername("alice"));
```

Đây là helper `SecurityMockMvcRequestBuilders.formLogin()` và `SecurityMockMvcResultMatchers.authenticated()`, cần static imports và test context; cấu hình phải có form login thật. `formLogin()` helper gửi form login request, **khác** `with(user("alice"))` tạo sẵn một principal.

Nếu dùng API Basic, `httpBasic("alice","password")` là helper khác. Với Bearer, dùng request header/token thực hoặc test Resource Server thích hợp; không dùng formLogin helper cho Bearer API.

## 17. Spring WebFlux không dùng ProviderManager Servlet

WebFlux có các kiểu:

- `ReactiveAuthenticationManager` trả `Mono<Authentication>`.
- `DelegatingReactiveAuthenticationManager` cho phép thử nhiều reactive managers theo hợp đồng Reactor.
- Một manager không xử lý được có thể trả `Mono.empty()`, lỗi xác thực trả `Mono.error(AuthenticationException)` và thành công trả `Mono.just(Authentication)`.
- HTTP security dùng `ServerHttpSecurity`, `SecurityWebFilterChain`, `ReactiveSecurityContextHolder`.

**Không** lấy `ProviderManager` Servlet rồi gọi trực tiếp blocking LDAP/JDBC trong Netty event loop. Cách kiểm thử Reactive cần dùng `StepVerifier`/Reactor Test và kiểm tra composition/error semantics của `DelegatingReactiveAuthenticationManager` trong version cụ thể.

Ví dụ **trích đoạn định hướng**, không phải chương trình độc lập:

```java
ReactiveAuthenticationManager first = authentication -> Mono.empty();

ReactiveAuthenticationManager second = authentication ->
        Mono.just(UsernamePasswordAuthenticationToken.authenticated(
                "alice", null,
                List.of(new SimpleGrantedAuthority("ROLE_USER"))));

ReactiveAuthenticationManager delegating =
        new DelegatingReactiveAuthenticationManager(first, second);

StepVerifier.create(delegating.authenticate(
                UsernamePasswordAuthenticationToken.unauthenticated(
                        "alice", "demo")))
        .assertNext(result -> assertTrue(result.isAuthenticated()))
        .verifyComplete();
```

Đoạn này cần imports Reactor `Mono`, `StepVerifier`, Spring Security Reactive interfaces và JUnit assertions; **không** kiểm tra Servlet `ProviderManager`. Với Reactive chain phức tạp, kiểm tra terminal events và không gọi `block()`/`subscribe()` thủ công trong production.

## 18. AuthenticationException, authorization và HTTP status: ba tầng không đồng nhất

Khi `ProviderManager` ném `BadCredentialsException`, code test biết loại lỗi. Nhưng khi request chạy qua HTTP:

- `UsernamePasswordAuthenticationFilter` thường gọi `AuthenticationFailureHandler`, có thể redirect về `/login?error`.
- HTTP Basic có thể trả `401` và `WWW-Authenticate: Basic`.
- Bearer Resource Server có `BearerTokenAuthenticationEntryPoint` và challenge semantics RFC 6750.
- Người dùng **đã xác thực** nhưng thiếu quyền thường nhận `403 Forbidden` từ authorization/`AccessDeniedHandler`.

Vì vậy, test manager **không nên assert HTTP 401 hoặc 302** — nó không biết HTTP response. Ngược lại, chỉ xem HTTP 401 **không thể chứng minh** child hay parent provider đã được gọi đúng thứ tự.

Để hạn chế user enumeration, không trả message nội bộ như `"alice locked after 5 attempts"` trong HTTP error body công khai. Audit có thể ghi mã lý do đã chuẩn hóa mà không log raw credentials.

## 19. Bài tập Java 17 độc lập: quan sát fallback và first success

Một chương trình Java thuần sau mô phỏng **logic ra quyết định** kiểu provider/parent. Nó **không** triển khai giao diện Spring Security, không xác thực password thật và không thay thế `ProviderManager`; dùng để nhìn rõ thứ tự.

Lưu thành `ProviderChainModel.java`:

```java
import java.util.List;
import java.util.Optional;

public class ProviderChainModel {

    record Request(String method, String identity) {}

    interface Provider {
        boolean supports(Request request);
        Optional<String> authenticate(Request request);
    }

    static String authenticate(
            Request request,
            List<Provider> providers,
            Provider parent) {

        for (Provider provider : providers) {
            if (!provider.supports(request)) {
                continue;
            }
            Optional<String> result = provider.authenticate(request);
            if (result.isPresent()) {
                return result.get();
            }
        }

        if (parent != null && parent.supports(request)) {
            return parent.authenticate(request).orElse("DENIED");
        }
        return "DENIED";
    }

    public static void main(String[] args) {
        Provider passkey = new Provider() {
            public boolean supports(Request r) {
                return "passkey".equals(r.method());
            }
            public Optional<String> authenticate(Request r) {
                return Optional.of("PASSKEY:" + r.identity());
            }
        };

        Provider localPassword = new Provider() {
            public boolean supports(Request r) {
                return "password".equals(r.method());
            }
            public Optional<String> authenticate(Request r) {
                return Optional.empty();
            }
        };

        Provider parentPassword = new Provider() {
            public boolean supports(Request r) {
                return "password".equals(r.method());
            }
            public Optional<String> authenticate(Request r) {
                return Optional.of("PARENT:" + r.identity());
            }
        };

        List<Provider> child =
                List.of(passkey, localPassword);

        System.out.println(authenticate(
                new Request("passkey", "alice"), child, parentPassword));
        System.out.println(authenticate(
                new Request("password", "bob"), child, parentPassword));
        System.out.println(authenticate(
                new Request("unknown", "carol"), child, parentPassword));
    }
}
```

Biên dịch và chạy bằng JDK 17+:

```bash
javac ProviderChainModel.java
java ProviderChainModel
```

Stdout **chính xác**:

```text
PASSKEY:alice
PARENT:bob
DENIED
```

Ví dụ cố ý **không mô phỏng exception precedence, event publisher, credential erase và context**. Những phần này phải kiểm tra với JUnit/ProviderManager thật ở mục 8, không suy từ chương trình mô hình đơn giản.

### Bài tập mở rộng

Sửa parentPassword để chỉ trả `Optional.of(...)` cho danh tính thuộc một realm cụ thể, và đổi test để bảo đảm user không thuộc realm đó bị DENIED. Sau đó thêm một “provider lỗi dịch vụ” vào mô hình và thử mô phỏng fail-closed; đối chiếu rằng `InternalAuthenticationServiceException` của ProviderManager thật dừng chuỗi, không như một `Optional.empty()`.

## 20. Ma trận kiểm thử ProviderManager nhiều tầng

| # | Đầu vào/cấu hình | Điều phải assert |
| --- | --- | --- |
| 1 | P1 supports=false, P2 success | P1 không authenticate; P2 success |
| 2 | P1 supports=true, returns null, P2 success | Thứ tự P1 → P2 |
| 3 | P1 success, P2 cũng có thể success | P2 không được hỏi; P1 thắng |
| 4 | P1 BadCredentials, P2 success | P2 thắng theo 6.5 semantics |
| 5 | P1 BadCredentials, P2 BadCredentials | Last exception P2 |
| 6 | P1 LockedException | Không P2/parent |
| 7 | P1 DisabledException | Không P2/parent |
| 8 | P1 InternalAuthenticationServiceException | Không P2/parent |
| 9 | Tất cả supports=false, không parent | ProviderNotFoundException |
| 10 | Tất cả trả null, không parent | ProviderNotFoundException |
| 11 | Child unsupported, parent success | Parent được gọi |
| 12 | Child null, parent success | Parent được gọi |
| 13 | Child BadCredentials, parent success | Parent có thể thắng |
| 14 | Child BadCredentials, parent BadCredentials | Parent exception được ném |
| 15 | Child BadCredentials, parent ProviderNotFound | Local exception giữ nguyên |
| 16 | Child LockedException, parent support=true | Parent không được gọi |
| 17 | Child InternalAuthenticationServiceException, parent support=true | Parent không được gọi |
| 18 | Child success, parent có side effect | Parent không bị gọi |
| 19 | Request type password | Chỉ provider hỗ trợ password nhận authenticate |
| 20 | Request type custom OTP | Chỉ provider hỗ trợ OTP nhận authenticate |
| 21 | Authenticated token with credentials | CredentialsContainer bị erase theo mặc định |
| 22 | Authenticated token with request details | Details được copy khi result chưa có details |
| 23 | Parent và child cùng publisher | Success event không bị duplicate |
| 24 | Custom AuthenticationEventPublisher | Failure event type được map theo cấu hình |
| 25 | Cached UserDetails implements CredentialsContainer | Không phá cache do erase credentials |
| 26 | Concurrent authentication requests | Provider thread-safe; không lẫn principal |
| 27 | Hai children dùng chung parent | Đúng local/provider chain; không crossover |
| 28 | Một auth type unsupported bởi mọi manager | Fail closed; không mặc định anonymous success |
| 29 | DTO HTTP invalid credentials | Failure handler đúng giao thức; không leak internal exception |
| 30 | Integration form login | Request đi qua manager thật, không chỉ mock principal |
| 31 | Bean wiring khác version | Thứ tự provider/parent trong context đúng với thiết kế |
| 32 | Parent trỏ ngược child | Không có vòng lặp cấu hình |
| 33 | External LDAP/DB timeout | Nội bộ dừng theo lỗi dịch vụ thay vì fallback yếu |
| 34 | Account disabled ở shared parent | Không có local provider mở lại trái policy |

**Nguyên tắc QA:** unit test chức năng điều phối và integration test cấu hình wiring/HTTP đều cần thiết. Không dùng một test happy-path thay thế hàng loạt negative cases về ngoại lệ, parent và credential handling.

## 21. Những lỗi thường gặp khi test hoặc triển khai

### `supports=false` nhưng test đòi `authenticate` được gọi

Đây là kỳ vọng sai. Manager kiểm tra type trước; provider không hỗ trợ thì bị bỏ qua. Nếu provider đáng lẽ xử lý request, sửa logic `supports(Class<?>)` hoặc token type, không ép manager gọi trực tiếp `authenticate`.

### Parent không được gọi dù mình đã cấu hình

Kiểm tra provider con đã trả authenticated result chưa; có `LockedException` hoặc `InternalAuthenticationServiceException` ngắt sớm không; parent có thật sự được đưa vào constructor `ProviderManager(List, AuthenticationManager)` hay chỉ là bean tồn tại trong context chưa được gắn? Test với `verify(parent).authenticate(...)` khi điều kiện phù hợp.

### Parent được gọi sau BadCredentials và chấp nhận password

Đó là một phần hành vi manager. Cần xem thiết kế fallback có đang yếu hơn chính sách local không. Không khắc phục bằng cách giả lập `LockedException` cho password sai; hãy phân biệt realms/token types và thiết kế một authoritative policy tránh downgrade.

### Đáng lẽ ProviderNotFound nhưng nhận BadCredentials

Một provider có thể hỗ trợ request type rồi trả `BadCredentialsException`, hoặc parent cung cấp lỗi đó. `ProviderNotFoundException` chỉ xuất hiện khi không provider/manager nào xác thực và không có AuthenticationException thích hợp khác. Assert đúng điều kiện cấu hình.

### `BadCredentialsException` của P1 không được ném

P2 hoặc parent có thể trả authenticated result, khiến exception trước đó bị bỏ qua. Đây là lý do cần kiểm tra toàn bộ thứ tự provider/parent, không chỉ mock P1.

### Account locked mà vẫn đăng nhập được

Nếu provider kiểm tra account state không được gọi, một provider khác đứng trước có thể thành công trước khi tới provider kiểm tra lock. Hoặc provider không trả đúng `AccountStatusException`. Thiết kế account-status policy nhất quán tại tất cả auth paths, không coi một exception của một provider là “khóa toàn cục” nếu provider đó không được gọi.

### Test luôn PASS dù thay đổi provider order

Có thể bạn đã mock manager thay vì dùng manager thật, hoặc chỉ assert `isAuthenticated()` mà không kiểm `result.getName()`, `verifyNoInteractions` và `InOrder`. Viết fixture có principal/provider result khác nhau để order regression lộ ngay.

### Event được phát hai lần hoặc không có

Xem parent/child publishers và cách cấu hình. Default khi tự tạo `ProviderManager` là null publisher; nếu parent là mock, nó không thực sự phát event. Dùng hai ProviderManager thật hoặc một integration test có application events để kiểm.

### UserDetails cache bị phá sau xác thực

`eraseCredentials()` có thể xóa dữ liệu trên object `CredentialsContainer` được dùng chung. Đừng vội `setEraseCredentialsAfterAuthentication(false)`; kiểm tra cache model và copy-on-authentication.

### Credentials vẫn còn trong session

Kiểm tra type returned `Authentication` có implements `CredentialsContainer` không và custom provider có trả object đúng không. Không tự log credentials trước/sau khi erase trong môi trường có dữ liệu thật.

### `@MockBean` hoặc test fixture không được gọi

Kiểm tra Spring Boot/Test version, bean wiring, manager thực được gắn vào `SecurityFilterChain` nào, request có qua đúng chain không và helper `with(user(...))` có bypass authentication. Với unit test không cần Spring context, tạo object thật trực tiếp để giảm nhầm lẫn.

## 22. Checklist trước khi đưa cấu hình vào production

1. **Token types:** liệt kê mọi `Authentication` subclass xuất hiện từ filters, thiết kế `supports` theo class an toàn và test negative support.
2. **Provider order:** thống nhất thứ tự trong `List`, audit ai có quyền thắng khi nhiều provider cùng hỗ trợ.
3. **Fallback policy:** xác định rõ parent được gọi khi local không thành công; không để realm yếu hơn mở khóa credential bị từ chối bởi realm mạnh hơn.
4. **Fail closed:** `AccountStatusException`/`InternalAuthenticationServiceException` dừng chuỗi; provider không chuyển outage thành `BadCredentialsException` vô cớ.
5. **Parent wiring:** parent phải được cấu hình tường minh, không circular, không dựa vào bean name vô tình.
6. **Exception precedence:** test child/parent errors, `ProviderNotFoundException`, `null` và last exception.
7. **Credentials:** returned token chỉ được authenticated sau kiểm chứng thật, `CredentialsContainer` xóa secret đúng lúc; cache không giữ object bị làm bẩn.
8. **Authentication events:** có `AuthenticationEventPublisher` khi cần audit/monitoring và không publish trùng giữa parent/child.
9. **Separation of layers:** test ProviderManager riêng; test DAO/LDAP/IdP riêng; test filters/HTTP/login/CSRF/session riêng.
10. **Thread safety:** providers/parent manager được chia sẻ giữa nhiều requests, không lưu principal/current credentials trong mutable instance fields.
11. **Account security:** disabled/locked/tenant/issuer checks có hiệu lực trên **tất cả** đường xác thực, không chỉ provider nằm cuối.
12. **Observability:** ghi provider ID/latency/result code ở môi trường tin cậy nhưng không log raw password/token/session ID hoặc internal diagnostic ra response.
13. **Regression:** chạy bộ tests khi đổi provider order, thêm mechanism, nâng Spring Security version hoặc thay parent/child chain structure.
14. **Documentation:** ghi rõ provider nào authoritative cho loại credential nào và trường hợp nào có thể fallback sang parent.

**Kết luận:** `ProviderManager` không chỉ “chọn một provider”. Nó thực thi một **chính sách duyệt có thứ tự**, cho phép provider bỏ qua bằng `supports=false` hoặc `null`, tiếp tục sau một số `AuthenticationException`, ngắt ngay đối với account-status/internal-service failures, có thể hỏi parent, và xử lý credential/events trên kết quả. Muốn cấu hình nhiều provider an toàn, bộ test phải **kiểm chứng cả nhánh không được gọi**, exception precedence và parent fallback, thay vì chỉ assert đăng nhập thành công.

## 23. Tài liệu chính thức

- [Spring Security 6.5 — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html): Authentication, AuthenticationManager, ProviderManager, providers và parent.
- [Spring Security 6.5.11 — ProviderManager API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/ProviderManager.html): iteration, last exception, parent, `setEraseCredentialsAfterAuthentication` và events.
- [Spring Security 6.5.11 — AuthenticationProvider API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/AuthenticationProvider.html): `supports`, `authenticate`, trả `null`.
- [Spring Security 6.5.11 — AuthenticationManager API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/AuthenticationManager.html): giao diện gọi xác thực.
- [Spring Security 6.5.11 — UsernamePasswordAuthenticationToken API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/UsernamePasswordAuthenticationToken.html): factory `unauthenticated`, `authenticated`, xóa credentials.
- [Spring Security 6.5 — Authentication Events](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/events.html): `AuthenticationEventPublisher` và failure/success event mapping.
- [Spring Security 6.5 — Servlet Authentication and Passwords](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html): DAO provider, `UserDetailsService`, PasswordEncoder và account-status checks.
- [Spring Security 6.5 — Multiple SecurityFilterChains](https://docs.spring.io/spring-security/reference/6.5/servlet/configuration/java.html#_multiple_httpsecurity_instances): chain selection và `@Order`.
- [Spring Security — Test](https://docs.spring.io/spring-security/reference/servlet/test/index.html): `spring-security-test`, MockMvc helpers và method/security testing.
- [Spring Security 6.5 — ReactiveAuthenticationManager API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/ReactiveAuthenticationManager.html): `Mono.empty`, `Mono.error` và khác biệt reactive.
- [Spring Security 6.5 — DelegatingReactiveAuthenticationManager API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/DelegatingReactiveAuthenticationManager.html): composition reactive managers.
- [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): generic authentication error messages, lockout, anti-brute-force và tránh authentication bypass.
