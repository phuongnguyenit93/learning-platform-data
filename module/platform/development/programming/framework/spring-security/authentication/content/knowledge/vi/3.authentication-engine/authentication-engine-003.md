# AuthenticationProvider.supports chọn loại Authentication được hỗ trợ

Trong Spring Security, ứng dụng có thể có nhiều cơ chế xác thực cùng lúc: username/password, API key, OTP, chứng chỉ, bearer token hoặc cơ chế riêng của hệ thống. Một `AuthenticationManager` cần biết **`AuthenticationProvider` nào có khả năng xử lý loại yêu cầu `Authentication` vừa nhận**. Hợp đồng trả lời câu hỏi đó là `AuthenticationProvider.supports(Class<?> authentication)`.

**Ý chính:** `supports()` phân luồng theo **kiểu Java của đối tượng `Authentication`**, không kiểm mật khẩu, không xác nhận token hợp lệ, không tự gán quyền và không lựa chọn URL. Trả `true` chỉ nói rằng provider *có thể xem xét* loại token; quyết định thực sự nằm ở `authenticate(Authentication)`. Phân biệt hai bước này giúp tránh lỗi provider không chạy, provider bắt nhầm token hoặc vô tình bỏ qua kiểm tra credential.

Bài học thuộc chủ đề **Bộ máy xác thực** của Spring Security; các ví dụ tập trung vào `AuthenticationManager`, `ProviderManager` và `AuthenticationProvider` trong ứng dụng Servlet/Java. Cách tổ chức reactive với `ReactiveAuthenticationManager` là mô hình API khác.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vì sao `ProviderManager` hỏi `supports(authentication.getClass())` trước khi gọi `authenticate(authentication)`.
2. Phân biệt `supports() = false`, `supports() = true` với `authenticate() = null`, kết quả xác thực thành công và `AuthenticationException`.
3. Dùng đúng `SomeAuthenticationToken.class.isAssignableFrom(authenticationClass)`, nhận biết sự khác biệt so với so sánh chính xác `==` và chiều `isAssignableFrom` sai.
4. Thiết kế các provider cho loại token khác nhau, hoặc nhiều provider hỗ trợ cùng một loại, mà không vô tình bỏ qua bảo mật.
5. Dự đoán hành vi khi provider đầu từ chối, provider sau thành công, tất cả đều không xử lý được, hoặc tài khoản bị khóa/vô hiệu hóa.
6. Xây dựng và chạy ví dụ Java 17+ nhỏ với `ProviderManager`, đọc output và viết kiểm thử xác nhận provider được lựa chọn đúng.

## 2. Bốn thành phần và ranh giới trách nhiệm

| Thành phần | Trả lời câu hỏi gì? | Ví dụ |
| --- | --- | --- |
| `Authentication` | “Yêu cầu xác thực này mang loại token, principal và credential gì?”; sau khi xác thực có thể chứa principal và authorities đã được chấp nhận. | `UsernamePasswordAuthenticationToken`, token API key tự định nghĩa, `BearerTokenAuthenticationToken`. |
| `AuthenticationManager` | “Thử xác thực yêu cầu này và trả lại kết quả đã xác thực, hoặc báo thất bại.” | Hợp đồng `authenticate(Authentication)`. |
| `ProviderManager` | “Trong các provider được cấu hình, cái nào hỗ trợ loại token này; gọi chúng theo thứ tự thế nào?” | Một manager chứa provider mật khẩu và provider API key. |
| `AuthenticationProvider` | “Tôi có khả năng xử lý **kiểu** `Authentication` này không? Nếu có, bằng chứng cụ thể có hợp lệ không?” | `supports(Class<?>)` để chọn kiểu; `authenticate(Authentication)` để kiểm chứng. |

Một filter xác thực trong `SecurityFilterChain` thường tạo một `Authentication` *chưa xác thực* từ request rồi gọi `AuthenticationManager.authenticate(...)`. Manager trả lại đối tượng `Authentication` đã xác thực hoặc ném ngoại lệ. Filter/cơ chế gọi manager chịu trách nhiệm đưa kết quả vào `SecurityContext`, xử lý phản hồi thành công/thất bại và lưu ngữ cảnh qua request nếu thiết kế cần.

```text
HTTP request
  |
  v
Authentication filter / authentication mechanism
  | Tạo Authentication chưa xác thực (ví dụ UsernamePasswordAuthenticationToken)
  v
AuthenticationManager (thường là ProviderManager)
  | 
  +--> Provider A.supports(request.getClass())? -- false --> bỏ qua A
  |
  +--> Provider B.supports(request.getClass())? -- true
  |         |
  |         +--> Provider B.authenticate(request)
  |                     |-- Authentication thành công --> dừng, trả kết quả
  |                     |-- null --> thử provider có thể xử lý tiếp theo
  |                     +-- AuthenticationException --> xử lý theo quy tắc manager
  |
  +--> Provider C ... (nếu cần) --> parent manager (nếu được cấu hình)
  |
  v
Authentication result / AuthenticationException
  |
  v
SecurityContext và bước authorization của ứng dụng
```

**Hai tầng lựa chọn riêng nhau:**

- `SecurityFilterChain`, `RequestMatcher` và các filter quyết định **request HTTP nào** chạy cơ chế nào, và từ HTTP request tạo loại `Authentication` nào.
- `AuthenticationProvider.supports()` quyết định **provider nào** được quyền thử xử lý **loại đối tượng `Authentication` Java** do cơ chế đó tạo.

Ví dụ, `supports(UsernamePasswordAuthenticationToken.class)` không nói gì về URL `/login`, HTTP method, tên user, tenant hay mật khẩu đúng/sai. Phương thức này chỉ nhận một `Class<?>`, không nhận HTTP request hay instance có chứa giá trị credential.

## 3. Hợp đồng chính xác của AuthenticationProvider

Giao diện rút gọn:

```java
public interface AuthenticationProvider {
    Authentication authenticate(Authentication authentication)
            throws AuthenticationException;

    boolean supports(Class<?> authentication);
}
```

Về bản chất, hai phương thức có trách nhiệm khác nhau.

### 3.1 `supports(Class<?>)`: kiểm khả năng xử lý kiểu token

- **Đầu vào:** một đối tượng `Class<?>`, ví dụ `UsernamePasswordAuthenticationToken.class`.
- **`true`:** provider có thể *xem xét sâu hơn* đối tượng thuộc loại này. **Không đảm bảo** `authenticate()` sẽ thành công, hay sẽ trả non-null.
- **`false`:** provider nói rằng loại token đó không thuộc phạm vi mình, nên `ProviderManager` **bỏ qua `authenticate()` của provider này**.
- Không dùng `supports()` để kiểm password, gọi API xác minh JWT, tra database, kiểm tenant từ request hoặc phân quyền trên tài nguyên. Phương thức không có đủ dữ liệu cho việc đó và được gọi trong quá trình lựa chọn provider.
- Cần kiểm đúng kiểu và bảo vệ logic trong `authenticate()`, ngay cả khi thông thường manager đã kiểm `supports()`; API provider có thể bị gọi trực tiếp trong test hoặc bởi code custom.

Javadoc nói rõ `supports() = true` chỉ cho phép đánh giá thêm; `authenticate()` **vẫn có thể trả `null`** để thử provider tiếp theo. Cần nhớ câu này vì nhiều người nhầm `supports()` là “đã xác thực thành công”.

### 3.2 `authenticate(Authentication)`: kiểm credential và ra quyết định

Một provider đã được chọn có ba kết quả chính:

| Kết quả của `authenticate()` | Ý nghĩa tại manager | Ví dụ |
| --- | --- | --- |
| Trả về `Authentication` **khác `null`** đã xác thực | Có kết quả thành công, `ProviderManager` dừng tìm provider khác và trả kết quả. | Hash password khớp, principal hợp lệ, quyền được lấy từ nguồn tin cậy. |
| Trả về `null` | Provider **không thể đưa ra kết luận** cho instance cụ thể; manager thử provider kế tiếp đủ điều kiện. | Provider chuyên một biến thể token, nhưng instance này cần provider khác xem xét. |
| Ném `AuthenticationException` | Có lỗi/thất bại xác thực. Manager áp dụng quy tắc ngoại lệ và provider kế tiếp/parent như mô tả phần 4. | `BadCredentialsException`, `LockedException`, `DisabledException`. |

Không trả về một đối tượng `authenticated=true` khi chưa xác minh credential. `authenticate()` thành công phải trả principal và authorities từ logic tin cậy, không dựa vào `role`/`isAdmin` do client tự gửi.

**Không dùng `null` để biểu thị “mật khẩu sai” khi provider chính là bên có trách nhiệm xác minh mật khẩu đó.** Nếu đúng loại và đúng phạm vi mà bằng chứng không hợp lệ, thông thường ném `BadCredentialsException` hoặc ngoại lệ cụ thể. `null` là cách nhường cho provider khác khi không đủ khả năng xử lý instance, không phải cơ chế che giấu lỗi và cho phép fallback nguy hiểm.

## 4. ProviderManager lựa chọn provider theo thứ tự thế nào?

Giả sử manager chứa danh sách `[A, B, C]`, mỗi provider có `supports` và `authenticate`. Với đầu vào `input`:

1. Lấy **runtime class** của `input`. Lần lượt hỏi `A.supports(type)`, `B.supports(type)`, `C.supports(type)` theo thứ tự cấu hình, trừ khi đã có kết quả hoặc ngoại lệ buộc dừng.
2. Nếu `supports(type) = false`, provider ấy không được gọi `authenticate`.
3. Nếu `supports(type) = true`, gọi `authenticate(input)`:
   - **Non-null:** nhận kết quả; không gọi các provider còn lại.
   - **`null`:** tiếp tục thử provider sau.
   - **`AuthenticationException`:** lưu/xử lý thất bại; một provider sau có thể thành công và khi đó kết quả thành công được ưu tiên trong trường hợp cho phép thử tiếp.
4. Nếu không có provider địa phương nào xác thực được, **parent `AuthenticationManager` tùy chọn** có thể được thử theo cấu hình.
5. Nếu không tìm được provider xử lý thành công và **không có ngoại lệ phù hợp đã được giữ lại**, `ProviderManager` có thể ném `ProviderNotFoundException`. Ngoại lệ này thường báo loại token không được cấu hình provider phù hợp, nhưng cũng có thể xuất hiện khi các provider đều không đưa ra quyết định.
6. Nếu một provider ném `AccountStatusException`, như `LockedException` hoặc `DisabledException`, `ProviderManager` **dừng xét các provider còn lại** theo hợp đồng triển khai; không được coi đây là tín hiệu “thử cách đăng nhập khác để vượt khóa”.

Javadoc của `ProviderManager` mô tả: provider thường được thử theo thứ tự cho tới khi có kết quả non-null; nếu các provider trước báo lỗi nhưng provider sau thành công, kết quả sau được dùng; nếu không có thành công, ngoại lệ cuối thích hợp có thể được ném. Vì thế **`BadCredentialsException` ở provider A không luôn có nghĩa provider B sẽ không được thử**. Hãy thiết kế trách nhiệm và thứ tự provider để không tạo đường vòng xác thực ngoài ý muốn. Một số lỗi nghiêm trọng khác cũng có xử lý đặc biệt; không dựa vào giả định “mọi exception đều được fallback”.

Bảng dự đoán, giả sử **không có parent manager**:

| A | B | Kết quả |
| --- | --- | --- |
| `supports=false` | `supports=true`, thành công | B xác thực, A bị bỏ qua. |
| `supports=true`, `authenticate=null` | `supports=true`, thành công | B xác thực sau khi A nhường. |
| `supports=true`, thành công | B bất kỳ | B không được thử; dùng kết quả A. |
| `supports=true`, `BadCredentialsException` | `supports=true`, thành công | B có thể thành công; lỗi ở A không phải lúc nào dừng toàn bộ. |
| `supports=true`, `LockedException` | B có hỗ trợ | Dừng ngay bằng lỗi trạng thái tài khoản. |
| `supports=false` | `supports=false` | `ProviderNotFoundException`. |
| `supports=true`, `authenticate=null` | `supports=false` | Không ai đưa ra quyết định; thường `ProviderNotFoundException`. |
| `supports=true`, `BadCredentialsException` | `supports=false` | Không có kết quả thành công; báo lỗi credential tương ứng. |

**Có provider khác cùng hỗ trợ một loại token** là điều bình thường nhưng cần chủ đích: thứ tự, việc trả `null`, ngoại lệ và nguồn thẩm quyền phải có thiết kế. Đừng lắp thêm một provider dễ dãi ở cuối để “cứu” mọi trường hợp login thất bại.

### Parent manager không phải provider cuối bình thường

`ProviderManager` có thể được cấu hình một `parent AuthenticationManager`, thường để tái sử dụng cơ chế xác thực chung. Parent là **manager**, không phải một phần tử của `List<AuthenticationProvider>`. Khi các provider địa phương không tạo được kết quả (trừ trường hợp dừng sớm theo hợp đồng), manager có thể chuyển cho parent. Khi gỡ lỗi, kiểm cả provider list lẫn parent; đừng nhìn danh sách local rồi khẳng định không còn chỗ xử lý.

## 5. Viết supports đúng kiểu Java

### 5.1 `isAssignableFrom` và chiều so sánh

Mẫu thường dùng:

```java
@Override
public boolean supports(Class<?> authenticationClass) {
    return UsernamePasswordAuthenticationToken.class
            .isAssignableFrom(authenticationClass);
}
```

Cách đọc: “`UsernamePasswordAuthenticationToken` có phải là **lớp cha hoặc chính lớp** của kiểu `authenticationClass` hay không?” Kết quả:

| Runtime class đưa vào | Biểu thức trên |
| --- | --- |
| `UsernamePasswordAuthenticationToken.class` | `true` |
| Một subclass của `UsernamePasswordAuthenticationToken` | `true` |
| Một loại token hoàn toàn khác, ví dụ `TestingAuthenticationToken.class` | `false` |
| `Authentication.class` (interface cha) | `false` |

Trong Java, `A.class.isAssignableFrom(B.class)` là `true` nếu một biến kiểu A có thể nhận một instance B. Đổi chiều như sau là **sai đối với mục tiêu chọn token A cùng subclass của A**:

```java
// Sai hướng: có thể từ chối subclass, hoặc khớp kiểu cha quá rộng.
return authenticationClass
        .isAssignableFrom(UsernamePasswordAuthenticationToken.class);
```

Thậm chí viết `Authentication.class.isAssignableFrom(authenticationClass)` để tiện sẽ trả `true` cho phần lớn token triển khai `Authentication`; provider ấy có nguy cơ “giành” những kiểu không thuộc trách nhiệm.

### 5.2 So sánh chính xác khi cần giới hạn subclass

Nếu token con dùng semantics khác, provider **không nên tự động chấp nhận subclass**. Có thể viết:

```java
@Override
public boolean supports(Class<?> authenticationClass) {
    return UsernamePasswordAuthenticationToken.class == authenticationClass;
}
```

`==` chỉ hỗ trợ đúng runtime class; `isAssignableFrom` hỗ trợ thêm subclass. Không có lựa chọn đúng tuyệt đối cho mọi thiết kế: hãy quyết định rõ provider có thật sự hiểu hợp đồng của subclass không. Chẳng hạn một `OtpAuthenticationToken extends UsernamePasswordAuthenticationToken` giữ OTP trong trường credentials có thể bị password provider bắt nhầm; thường an toàn và rõ ràng hơn khi tạo **loại token riêng** cho cơ chế khác.

### 5.3 `supports` không xem giá trị instance

Ví dụ sau **không thể** thực hiện đúng trong `supports(Class<?>)`:

- “Chỉ nhận username bắt đầu bằng `staff-`” — cần principal instance, không có trong `Class<?>`.
- “Chỉ xác thực JWT có issuer A” — cần token và các claims sau kiểm chứng, không có trong type.
- “Chỉ nhận OTP còn hạn” — cần dữ liệu OTP và nguồn xác minh.
- “Chỉ nhận POST `/login`” — cần HTTP request và request matcher, không phải provider type.
- “Chỉ chọn provider khi tenant là `tenant-17`” — cần thông tin đã được xác thực từ request hoặc architecture định tuyến manager phù hợp.

Nếu nhiều provider cùng nhận một token class nhưng phục vụ nhiều nguồn tài khoản, provider có thể nhận `supports=true` rồi **quyết định trong `authenticate`** có thể xử lý instance hay nên trả `null`. Cần ràng buộc an toàn để ngăn một provider “fallback” vượt qua thất bại thực sự. Với tenant/issuer có ranh giới tin cậy riêng, có thể dùng **manager khác nhau** và một `AuthenticationManagerResolver` phù hợp, hoặc token types phân biệt, tùy thiết kế.

## 6. Ví dụ Java 17+ chạy được: cùng một manager, ba providers

Ví dụ nhỏ dùng **Spring Security Core 6.5.x** mà không cần Spring Boot hay HTTP server để người học quan sát chính xác hành vi `supports`. Có ba provider:

- `ObservePasswordProvider` hỗ trợ kiểu username/password nhưng trả `null` có chủ đích để minh họa “supports=true chưa đủ”; không kiểm bí mật.
- `DemoPasswordProvider` hỗ trợ username/password, kiểm một credential demo rồi trả authentication thành công hoặc ném `BadCredentialsException`.
- `DemoApiKeyProvider` chỉ hỗ trợ `ApiKeyToken` do ứng dụng tự định nghĩa, rồi kiểm API key demo.

`TestingAuthenticationToken` được dùng **chỉ trong bài test** để tạo trường hợp không provider nào supports. Giá trị mật khẩu/API key cố định chỉ để tái hiện output; không triển khai cách lưu/so khớp này trong ứng dụng thật.

### 6.1 Tạo dự án

Yêu cầu JDK 17+ và Gradle (hoặc Gradle wrapper của dự án). Cấu trúc:

```text
provider-supports-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/ProviderSupportsDemo.java
```

File `settings.gradle`:

```groovy
rootProject.name = 'provider-supports-demo'
```

File `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.security:spring-security-core:6.5.6'
}

application {
    mainClass = 'demo.ProviderSupportsDemo'
}
```

File `src/main/java/demo/ProviderSupportsDemo.java`:

```java
package demo;

import java.util.Collection;
import java.util.List;

import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.TestingAuthenticationToken;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.authentication.AbstractAuthenticationToken;

public final class ProviderSupportsDemo {

    public static void main(String[] args) {
        AuthenticationProvider observer = new ObservePasswordProvider();
        AuthenticationProvider password = new DemoPasswordProvider();
        AuthenticationProvider apiKey = new DemoApiKeyProvider();

        ProviderManager manager = new ProviderManager(
                List.of(observer, password, apiKey));

        System.out.println("password-supports-password="
                + password.supports(UsernamePasswordAuthenticationToken.class));
        System.out.println("password-supports-api-key="
                + password.supports(ApiKeyToken.class));

        attempt(manager, "password-valid",
                UsernamePasswordAuthenticationToken.unauthenticated(
                        "alice", "local-password"));
        attempt(manager, "api-key-valid",
                ApiKeyToken.unauthenticated("local-api-key"));
        attempt(manager, "password-invalid",
                UsernamePasswordAuthenticationToken.unauthenticated(
                        "alice", "incorrect"));
        attempt(manager, "unsupported-token",
                new TestingAuthenticationToken("anyone", "ignored"));
    }

    private static void attempt(
            ProviderManager manager,
            String label,
            Authentication request) {

        System.out.println("-- " + label + " --");
        try {
            Authentication result = manager.authenticate(request);
            List<String> roles = result.getAuthorities().stream()
                    .map(GrantedAuthority::getAuthority)
                    .sorted()
                    .toList();

            System.out.println("principal=" + result.getName());
            System.out.println("authorities=" + roles);
        } catch (AuthenticationException exception) {
            System.out.println("failure="
                    + exception.getClass().getSimpleName());
        }
    }

    private static final class ObservePasswordProvider
            implements AuthenticationProvider {

        @Override
        public boolean supports(Class<?> authenticationClass) {
            return UsernamePasswordAuthenticationToken.class
                    .isAssignableFrom(authenticationClass);
        }

        @Override
        public Authentication authenticate(Authentication request) {
            System.out.println("observer: pass to next provider");
            return null; // Chưa quyết định; provider kế tiếp được thử.
        }
    }

    private static final class DemoPasswordProvider
            implements AuthenticationProvider {

        @Override
        public boolean supports(Class<?> authenticationClass) {
            return UsernamePasswordAuthenticationToken.class
                    .isAssignableFrom(authenticationClass);
        }

        @Override
        public Authentication authenticate(Authentication request) {
            System.out.println("password: verify");
            if (!"alice".equals(request.getName())
                    || !"local-password".equals(request.getCredentials())) {
                throw new BadCredentialsException("Invalid demo credentials");
            }

            return UsernamePasswordAuthenticationToken.authenticated(
                    "alice",
                    null,
                    List.of(new SimpleGrantedAuthority("ROLE_USER")));
        }
    }

    private static final class DemoApiKeyProvider
            implements AuthenticationProvider {

        @Override
        public boolean supports(Class<?> authenticationClass) {
            return ApiKeyToken.class.isAssignableFrom(authenticationClass);
        }

        @Override
        public Authentication authenticate(Authentication request) {
            System.out.println("api-key: verify");
            if (!(request instanceof ApiKeyToken)
                    || !"local-api-key".equals(request.getCredentials())) {
                throw new BadCredentialsException("Invalid demo API key");
            }
            return ApiKeyToken.verified("report-service");
        }
    }

    private static final class ApiKeyToken
            extends AbstractAuthenticationToken {

        private final Object principal;
        private final Object credentials;

        private ApiKeyToken(String key) {
            super(List.of());
            this.principal = "unverified-api-key";
            this.credentials = key;
            super.setAuthenticated(false);
        }

        private ApiKeyToken(
                String principal,
                Collection<? extends GrantedAuthority> authorities) {
            super(authorities);
            this.principal = principal;
            this.credentials = null; // Không giữ API key ở kết quả thành công.
            super.setAuthenticated(true);
        }

        static ApiKeyToken unauthenticated(String key) {
            return new ApiKeyToken(key);
        }

        static ApiKeyToken verified(String service) {
            return new ApiKeyToken(
                    service,
                    List.of(new SimpleGrantedAuthority("ROLE_SERVICE")));
        }

        @Override
        public Object getPrincipal() {
            return principal;
        }

        @Override
        public Object getCredentials() {
            return credentials;
        }
    }
}
```

**Chi tiết quan trọng:** `ApiKeyToken` có constructor riêng cho request chưa xác thực và constructor riêng cho kết quả đã xác thực, trong đó `credentials=null`. Chỉ code provider nội bộ tạo kết quả thành công. Ví dụ không chứng minh việc bảo vệ API key thật vì dùng chuỗi demo cố định; hệ thống thực tế cần khóa có entropy đủ lớn, kho lưu an toàn, so sánh/đối chiếu an toàn, rotation, scope, rate limit và kiểm soát logging.

### 6.2 Chạy

Nếu dự án có Gradle wrapper:

```bash
./gradlew run --console=plain
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat run --console=plain
```

Nếu chưa có wrapper nhưng đã cài Gradle phù hợp, chạy `gradle run --console=plain`. Lệnh `javac` đơn lẻ **không đủ** vì ví dụ import các thư viện Spring Security từ Maven Central.

Phần **stdout của chương trình Java** (bỏ qua dòng tiến độ Gradle) theo đúng thứ tự:

```text
password-supports-password=true
password-supports-api-key=false
-- password-valid --
observer: pass to next provider
password: verify
principal=alice
authorities=[ROLE_USER]
-- api-key-valid --
api-key: verify
principal=report-service
authorities=[ROLE_SERVICE]
-- password-invalid --
observer: pass to next provider
password: verify
failure=BadCredentialsException
-- unsupported-token --
failure=ProviderNotFoundException
```

**Đọc output:**

1. Provider password khớp `UsernamePasswordAuthenticationToken` nhưng không khớp `ApiKeyToken`.
2. Khi password hợp lệ, observer có `supports=true` nhưng trả `null`; manager gọi tiếp password provider, vì vậy hiện cả hai dòng `observer` và `password`.
3. Với API key, hai password provider bị bỏ qua hoàn toàn; chỉ `DemoApiKeyProvider` in `api-key: verify`.
4. Password sai trả `BadCredentialsException`, nghĩa là token đúng loại nhưng bằng chứng xác thực sai. Provider API key không supports password token nên không tạo một nhánh “cứu” lỗi.
5. `TestingAuthenticationToken` không được provider nào hỗ trợ, nên manager không tìm thấy cơ chế xác thực và ném `ProviderNotFoundException`. Không có dòng `observer`/`password`/`api-key` cho case này.

Trong thực tế, sử dụng `PasswordEncoder` với hash để kiểm mật khẩu, sử dụng secret store hoặc token verifier phù hợp để kiểm API key, không hardcode credential và không ghi credential trong log. Ví dụ chỉ giúp nhìn rõ cơ chế dispatch trong `ProviderManager`.

### 6.3 Vì sao kết quả phải là Authentication mới, đáng tin?

Đầu vào có thể chứa credential và chưa được xác thực. Sau `authenticate` thành công, provider trả đối tượng đại diện principal, authorities **được xác lập từ nguồn tin cậy**, lý tưởng không giữ raw secret. `ProviderManager` mặc định cố gắng xóa credentials từ kết quả nếu kết quả triển khai `CredentialsContainer`; điều đó **không chắc đã xóa mọi bản sao** secret trong request, heap hay log.

Một phương pháp sai là coi input token có `isAuthenticated() == true` do code không tin cậy dựng lên là bằng chứng, rồi trả nó lại mà không kiểm credential. Dù `supports()` đúng, provider vẫn phải xác minh thực sự.

## 7. Áp dụng vào Spring Boot / Spring Security Servlet

Trong ứng dụng thực, cần đủ ba mắt xích:

1. **Cơ chế nhận request:** filter hoặc cơ chế Spring Security tạo đúng loại `Authentication`. HTTP Basic/form login thông thường tạo `UsernamePasswordAuthenticationToken`; custom API key cần code nhận key an toàn và tạo `ApiKeyToken` chưa xác thực.
2. **AuthenticationManager có provider:** manager mà filter **thực sự sử dụng** phải chứa provider có `supports(type)` đúng. Đăng ký một bean `AuthenticationProvider` chưa chứng minh filter/chain hiện tại sẽ sử dụng nó.
3. **Kết quả ngữ cảnh:** sau khi xác thực, flow phải đưa `Authentication` thành công vào `SecurityContext` và quản lý persistence/cleanup theo cấu hình. Authorization kiểm quyền của principal cho tài nguyên cụ thể.

Ví dụ cấu hình mang tính **minh họa thành phần**, chưa phải ứng dụng/HTTP filter hoàn chỉnh:

```java
// Có một danh sách provider đã được khởi tạo/inject hợp lệ:
AuthenticationManager manager = new ProviderManager(
        List.of(passwordProvider, apiKeyProvider));

// Trong một authentication filter đáng tin, sau khi nhận và
// kiểm giới hạn request, tạo token chưa xác thực:
Authentication request =
        ApiKeyToken.unauthenticated(extractedApiKey);

// ProviderManager chọn provider dựa trên kiểu ApiKeyToken.
Authentication verified = manager.authenticate(request);

// Sau đó cơ chế filter áp dụng SecurityContext/session/lỗi/cleanup
// theo hợp đồng Spring Security; không tự bỏ qua chuỗi filter.
```

Đoạn trên **không phải class Java chạy độc lập**, chỉ minh họa chỗ gọi. `ApiKeyToken` của chương 6 là private nested class để làm demo; khi triển khai thật, cần một lớp token có visibility và package phù hợp.

Ở Spring Security Servlet, nếu định nghĩa một `SecurityFilterChain` riêng cho `/api/**` và một chain khác cho form login, mỗi chain có thể dùng cơ chế xác thực/manager khác nhau. Hãy kiểm **request matcher của chain**, filter có được cài hay chưa, manager nào được inject và provider list tương ứng, trước khi kết luận `supports()` bị lỗi.

Đối với OAuth2 resource server, Spring Security đã có cơ chế bearer-token và `JwtAuthenticationProvider`/`OpaqueTokenAuthenticationProvider` tương ứng. Khi bài toán chỉ là xác minh access token chuẩn, ưu tiên cấu hình resource server và validator được hỗ trợ; không tự viết provider kiểm JWT bằng decode Base64.

## 8. Các lỗi thực tế và cách sửa

### 8.1 `supports()` luôn false do sai chiều isAssignableFrom

Sai:

```java
@Override
public boolean supports(Class<?> tokenClass) {
    return tokenClass.isAssignableFrom(MyLoginToken.class);
}
```

Nếu input là subclass của `MyLoginToken`, biểu thức trên có thể là `false` dù provider cần hỗ trợ nó. Đúng (khi có chủ đích hỗ trợ subclass):

```java
@Override
public boolean supports(Class<?> tokenClass) {
    return MyLoginToken.class.isAssignableFrom(tokenClass);
}
```

Kiểm thử độc lập các giá trị class ngay từ đầu; lỗi này thường tạo `ProviderNotFoundException` hoặc một provider khác nhận nhầm request.

### 8.2 Provider quá rộng tự coi mọi Authentication là của mình

Sai:

```java
@Override
public boolean supports(Class<?> tokenClass) {
    return Authentication.class.isAssignableFrom(tokenClass);
}
```

Provider sẽ khẳng định hỗ trợ gần như mọi token, kể cả anonymous, bearer hoặc cơ chế khác. Nếu `authenticate` cast bừa sang `UsernamePasswordAuthenticationToken`, sẽ có `ClassCastException`; nếu trả authentication thành công một cách dễ dãi, còn có thể tạo lỗ hổng bảo mật.

Đúng: chỉ nhận class thật sự hiểu; dùng `instanceof` khi kiểm tra an toàn trong `authenticate`, không ép kiểu trước khi xác minh và không coi `supports=true` là xác thực thành công.

### 8.3 supports đúng, nhưng filter không tạo loại token mong đợi

Provider viết `supports(ApiKeyToken.class)=true` mà filter lại gửi `UsernamePasswordAuthenticationToken`. Manager **không suy luận theo header `X-API-Key`** để tự chuyển thành `ApiKeyToken`. Cần kiểm flow HTTP → filter → token class → manager. Đăng ký provider mà thiếu cơ chế tạo token cũng không mang lại luồng đăng nhập API key.

### 8.4 supports true nhưng provider trả null cho mọi instance

Nếu provider định nhận loại token và kiểm chứng thực sự, `return null` vô điều kiện là lỗi logic: manager bỏ qua và có thể gọi provider khác hoặc kết thúc bằng `ProviderNotFoundException`. Chỉ trả `null` khi provider **chủ động không thể quyết định cho instance đó** và có hợp đồng fallback rõ ràng.

### 8.5 Token đúng loại nhưng mật khẩu sai bị xem là “unsupported”

Không sửa lỗi này bằng cách `supports=false` khi password không đúng: `supports()` không có password instance và không chịu trách nhiệm kiểm credential. Phân biệt:

- **Unsupported type:** loại `Authentication` không được cấu hình provider; sửa filter/token type/provider list.
- **Invalid credential:** provider phù hợp được gọi nhưng xác minh thất bại; sửa credential, verifier, user store hoặc policy và báo lỗi xác thực thích hợp.
- **Provider abstains:** provider được gọi nhưng không thể quyết định cho instance; kiểm logic `return null`, thứ tự và parent.

### 8.6 Nhiều provider cùng xử lý UsernamePasswordAuthenticationToken

Giả sử LDAP provider và local database provider đều hỗ trợ username/password. Nếu local provider ném `BadCredentialsException`, một provider sau **có thể** được thử và xác thực thành công. Đây có thể là chủ đích cho nhiều user store hoặc là đường vòng nguy hiểm khi cùng username đại diện các chủ thể khác nhau.

Thiết kế cần xác định **namespace danh tính, thứ tự ưu tiên, chính sách khóa/vô hiệu hóa, hành vi khi user không thuộc provider và khi password sai**, cách gắn authoritative principal và audit. Không cho phép provider thứ hai lách qua trạng thái `LockedException` của provider thứ nhất. Với cùng username ở nhiều nguồn, đảm bảo ánh xạ tài khoản rõ ràng trước khi cấp quyền; tránh “ai kiểm đúng bí mật nào cũng thành cùng tài khoản”.

### 8.7 Kiểm supports nhưng quên security context và phân quyền

Một unit test gọi `manager.authenticate(token)` thành công **không tự bảo đảm** filter trong ứng dụng đã lưu `SecurityContext` đúng hoặc request đến controller có principal. Sau authentication còn các trách nhiệm: session/stateless lifecycle, security context per request, xử lý thất bại, CSRF theo kiến trúc, và authorization của từng action/resource.

### 8.8 Bị lỗi 401/403 thì sửa supports ngay

Một lỗi HTTP `401` có thể do filter không chạy, header sai, provider không được cài, credential sai, token sai audience hoặc entry point. Một lỗi `403` có thể do thiếu quyền hoặc CSRF, dù authentication thành công. Quan sát từng bước và **phân biệt authentication với authorization**, tránh đoán nguyên nhân từ status code.

## 9. Cách debug và kiểm thử có hệ thống

Không log password, bearer token, API key hoặc nguyên `Authentication` object có thể chứa credential. Có thể ghi metadata đã làm sạch như request ID, **tên class token**, **tên provider**, kết quả `supports`, sự kiện attempt/success/failure và loại exception. Nếu dùng logging Spring Security trong môi trường dev, phải kiểm chính sách dữ liệu bí mật và tắt thông tin chi tiết ở production.

### 9.1 Checklist khi một provider không được gọi

1. Request có đi vào đúng `SecurityFilterChain` và authentication filter không?
2. Filter tạo **runtime class** nào cho `Authentication`? Không suy từ header/URL; kiểm class của object trước lời gọi manager.
3. Filter gọi **manager instance nào**? Provider vừa định nghĩa có nằm trong danh sách của manager đó không?
4. `supports(request.getClass())` có trả `true` không? Kiểm chiều `isAssignableFrom` và subclass.
5. Nếu supports true, `authenticate` có bị gọi không? Có trả `null` hoặc ném exception? Provider nào xử lý tiếp?
6. Có `parent AuthenticationManager`, multiple chains hoặc thứ tự providers ảnh hưởng kết quả không?
7. Nếu authentication thành công nhưng endpoint vẫn từ chối, authorization rule hoặc security context có đúng không?

### 9.2 Ma trận kiểm thử nhỏ

| Đầu vào / tình huống | Kiểm tra đúng |
| --- | --- |
| Token thuộc loại provider hỗ trợ | `supports` true; `authenticate` được gọi đúng provider. |
| Token thuộc loại khác | `supports` false; `authenticate` của provider không được gọi. |
| Subclass của token | Kết quả đúng theo hợp đồng chọn `isAssignableFrom` hay `==` đã quyết định. |
| Provider đầu hỗ trợ nhưng trả `null` | Provider kế tiếp được gọi; không coi `null` là success. |
| Provider đầu trả authentication non-null | Provider phía sau không được gọi. |
| Credential đúng loại nhưng sai | Thất bại bằng `AuthenticationException` thích hợp, không cấp principal giả. |
| Không provider nào supports | `ProviderNotFoundException` khi không có parent/ngoại lệ khác. |
| Tài khoản bị khóa/vô hiệu hóa | Không fallback sang provider khác để vượt kiểm soát `AccountStatusException`. |
| Cùng token class được nhiều provider hỗ trợ | Đúng thứ tự và đúng chính sách cấp quyền từ nguồn tin cậy. |
| SecurityFilterChain khác / manager khác | Provider được gọi theo manager thực sự của chain, không theo bean “nghĩ là đã đăng ký”. |
| Raw token/API key bị lộ trong debug log | Sửa ranh giới logging; test đảm bảo credential không xuất hiện. |
| Authentication thành công nhưng action bị cấm | Authorization trả từ chối như chính sách, không sửa `supports` để cấp thêm quyền. |

Ở unit test đơn giản, bạn có thể dùng `ProviderManager` trực tiếp như chương 6, thậm chí cung cấp provider giả trả `null` để xác nhận thứ tự. Với integration test Servlet, thực hiện request HTTP thật qua filter chain và kiểm cả `401`/`403`, principal, authority, session behavior và không lộ secret.

## 10. Tình huống tư duy trước–sau

### Tình huống A — API key gửi vào provider mật khẩu

**Trước:** Filter đọc `X-API-Key` nhưng tạo `UsernamePasswordAuthenticationToken(key, "")` để tái sử dụng manager. Password provider nghĩ token đúng loại, thử tìm username bằng key, gây lỗi login hoặc rò rỉ thông tin.

**Sau:** Filter được ủy quyền tạo `ApiKeyToken` riêng; `ApiKeyProvider.supports(ApiKeyToken.class)` là `true`, password provider trả `false`. Bên kiểm API key ánh xạ secret sang service principal và authorities phía server, sau đó trả token đã xác thực. Đường đi và trust boundary rõ ràng.

### Tình huống B — fallback làm mất chính sách khóa

**Trước:** Local DB provider thấy tài khoản khóa nhưng trả `null`, rồi LDAP provider xác thực bằng username giống nhau. Kết quả: tài khoản vốn bị khóa có thể được chấp nhận qua nguồn khác.

**Sau:** Xác định danh tính và chính sách khóa tại authority phù hợp. Khi có trạng thái khóa thật, trả ngoại lệ trạng thái tài khoản; không dùng `null` để biến “bị khóa” thành “không biết xử lý”. Nếu user thuộc namespace LDAP độc lập, thiết kế định danh và manager tách bạch để không mập mờ.

### Tình huống C — nhìn supports rồi tưởng token đã hợp lệ

**Trước:** Code tùy chỉnh gọi `provider.supports(token.getClass())` rồi tự tạo `Authentication` thành công, không gọi `authenticate`.

**Sau:** `supports` chỉ là bước chọn provider; luôn dùng `AuthenticationManager.authenticate` theo luồng chuẩn, cho provider kiểm đúng credential, chữ ký, issuer, audience, hạn và trạng thái liên quan.

### Tình huống D — manager có đúng provider nhưng vẫn ProviderNotFoundException

**Trước:** Kỹ sư thấy bean `ApiKeyProvider`, kiểm `supports(ApiKeyToken.class) == true` trong unit test, nhưng HTTP request vẫn thất bại.

**Sau:** Theo dấu chain/filter thực đang xử lý request, kiểm nó tạo `ApiKeyToken` hay token loại khác và gọi đúng manager. Cần cấu hình chính xác filter/provider trên cùng security chain; bean tồn tại không tự khởi động một cơ chế xác thực chưa được đăng ký.

## 11. Tự đánh giá

**Câu 1.** `supports(UsernamePasswordAuthenticationToken.class)` trả `true`. Người dùng nhập sai password; đây có phải bug của `supports`?

**Đáp án:** Không. `supports` chỉ xác nhận provider hiểu loại token; password đúng/sai do `authenticate` kiểm tra. Đúng loại nhưng sai credential thường được báo bằng `BadCredentialsException`.

**Câu 2.** Provider A `supports=true` và `authenticate=null`; provider B cũng `supports=true` và trả authentication thành công. Manager làm gì?

**Đáp án:** Gọi B sau A, sử dụng authentication do B trả. `null` của A nghĩa là chưa quyết định, không phải xác thực thành công hoặc thất bại cuối cùng.

**Câu 3.** `ProviderNotFoundException` có nhất thiết nghĩa user không tồn tại trong database không?

**Đáp án:** Không. Đây thường là lỗi không có provider được cấu hình hỗ trợ/đưa ra kết quả cho **loại Authentication** đã truyền; cần kiểm token class, provider list, chain và parent.

**Câu 4.** Vì sao `MyToken.class.isAssignableFrom(authenticationClass)` thường đúng hơn biểu thức đảo chiều?

**Đáp án:** Nó trả true cho chính `MyToken` và các subclass của `MyToken`; biểu thức đảo chiều có thể bỏ sót subclass hoặc nhận một kiểu cha quá rộng.

**Câu 5.** Có nên trả `null` khi account đã khóa để thử provider sau không?

**Đáp án:** Không, nếu khóa thuộc chính sách có thẩm quyền cho account đó. Nên dùng ngoại lệ trạng thái thích hợp để không biến khóa thành fallback. `ProviderManager` có quy tắc dừng khi gặp `AccountStatusException`.

**Câu 6.** `supports` có thể biết JWT vừa nhận có audience đúng API không?

**Đáp án:** Không; tham số chỉ là `Class<?>`. Validator trong `authenticate` hoặc cơ chế authentication cụ thể phải kiểm token thực và ràng buộc audience.

**Câu 7.** Provider authentication trả về role lấy trực tiếp từ `X-Role: ADMIN` do client gửi. Đúng chưa?

**Đáp án:** Sai. Đúng kiểu token và trả non-null chưa đủ bảo đảm an toàn; principal và authorities phải đến từ quá trình xác minh và nguồn quyền tin cậy, không do client tự cấp.

**Câu 8.** Có cần viết `AuthenticationProvider` riêng để xác thực mọi JWT API không?

**Đáp án:** Không. Nếu dùng OAuth2 resource server chuẩn, Spring Security có cơ chế/bộ kiểm JWT hoặc opaque token. Custom provider chỉ cần khi nghiệp vụ/cơ chế xác thực thực sự có yêu cầu riêng.

## 12. Tài liệu gốc và hướng đọc

- Spring Security — [Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html): sơ đồ `AuthenticationManager`, `ProviderManager`, `AuthenticationProvider`, `SecurityContextHolder` và các nhánh xác thực.
- Spring Security 6.5 — [AuthenticationProvider Javadoc](https://docs.spring.io/spring-security/site/docs/6.5.6/api/org/springframework/security/authentication/AuthenticationProvider.html): hợp đồng `supports(Class<?>)`, `authenticate(Authentication)`, `null` và ngoại lệ.
- Spring Security — [ProviderManager Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/ProviderManager.html): thứ tự providers, parent, ưu tiên ngoại lệ, kết quả non-null và credential erasure.
- Spring Security — [UsernamePasswordAuthenticationToken Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/UsernamePasswordAuthenticationToken.html): cách tạo token request/result và trạng thái authentication.
- Spring Security — [DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/dao-authentication-provider.html): cơ chế user/password dùng `UserDetailsService` và `PasswordEncoder`.
- Spring Security — [OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): dùng cơ chế chuẩn để xác minh bearer JWT.

**Quy tắc nhớ nhanh:** `supports()` trả lời **“provider này hiểu *loại* Authentication không?”**; `authenticate()` trả lời **“bằng chứng *cụ thể* có hợp lệ và kết quả là ai?”**; `ProviderManager` điều phối thứ tự và fallback; filter tạo token đúng loại; authorization kiểm quyền sau xác thực.