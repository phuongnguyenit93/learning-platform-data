# Thiết kế Authentication token riêng với đầu vào chưa được tin cậy

## Mục tiêu bài học

Trong Spring Security, một request từ HTTP, header, cookie, JSON body hoặc hệ thống bên ngoài có thể mang dữ liệu **tự xưng**: tên người dùng, API key, mã OTP, tenant, role hoặc định danh dịch vụ. Dữ liệu đó chưa trở thành bằng chứng xác thực chỉ vì ta đã đặt nó trong một đối tượng triển khai interface **Authentication**.

Bài học này tập trung vào cách thiết kế **custom Authentication token** cho dữ liệu chưa được tin cậy, dùng **AuthenticationProvider** để xác minh, sau đó tạo một kết quả đã xác thực mà các bước phân quyền có thể tin cậy.

Sau khi học, bạn có thể:

1. Phân biệt **authentication request token** với **authenticated result token** và giải thích vai trò của thuộc tính **isAuthenticated**.
2. Tự xây dựng token kế thừa **AbstractAuthenticationToken** với constructor an toàn, authorities trống ở trạng thái đầu vào và phương thức **setAuthenticated(true)** bị chặn.
3. Viết **AuthenticationProvider** đọc token đầu vào, kiểm tra bí mật bằng dữ liệu do server quản lý và trả về một token mới có principal và quyền do server quyết định.
4. Nối provider vào **ProviderManager** và kiểm chứng cả luồng thành công, sai credential, cố tự đánh dấu trusted.
5. Nhận diện bẫy bảo mật như lấy role từ JSON, tin client-supplied user ID, ghi log secret, giữ credential trong context, hoặc đưa request token thẳng vào SecurityContext.

## 1. Authentication không có nghĩa là đã xác thực

**Authentication** vừa là kiểu dữ liệu biểu diễn *yêu cầu xác thực*, vừa có thể là kiểu dữ liệu biểu diễn *kết quả đã xác thực*. Hai trạng thái có ý nghĩa bảo mật khác nhau:

| Thuộc tính | Trước khi xác minh | Sau khi xác minh thành công |
| --- | --- | --- |
| **isAuthenticated()** | **false** | **true** |
| **principal** | Chưa có danh tính đáng tin; có thể là username tự khai hoặc null | Định danh/account do server đã xác minh |
| **credentials** | Bí mật được gửi tới để kiểm tra, ví dụ API key | Nên xóa hoặc không giữ nếu không cần |
| **authorities** | Rỗng; không nhận quyền từ client | Quyền lấy từ nguồn đáng tin cậy phía server |
| **nguồn dữ liệu** | HTTP header/body/cookie, dữ liệu người gọi có thể giả mạo | Kết quả kiểm tra qua provider và kho dữ liệu đáng tin |
| **được đặt vào SecurityContext?** | **Không** như danh tính đã đăng nhập | Có, tại điểm tích hợp xác thực thành công |

Ví dụ:

~~~http
GET /reports HTTP/1.1
Host: localhost:8080
X-API-Key: some-client-value
X-User: admin
X-Role: ROLE_ADMIN
~~~

Ba header trên chỉ chứng minh client **đã gửi các chuỗi ký tự đó**. Server phải xác thực API key hoặc chứng cứ phù hợp rồi mới suy ra ai đang gọi và họ có quyền gì. Tuyệt đối không tạo một token với principal = **admin**, authority = **ROLE_ADMIN** và trạng thái authenticated = **true** chỉ vì request khai như vậy.

Khi gọi **AuthenticationManager.authenticate(requestToken)**, manager chuyển token đến một provider phù hợp. Provider có trách nhiệm chuyển từ *yêu cầu chưa được tin* thành *kết quả đáng tin* hoặc từ chối. Phần code nhận HTTP không được tự xác nhận danh tính.

## 2. Luồng xử lý và ranh giới tin cậy

~~~text
Nguồn chưa tin cậy
  HTTP header / JSON / cookie / message bên ngoài
       |
       v
[Validation về định dạng, kích thước, sự hiện diện]
       |
       v
Custom Authentication token
  isAuthenticated = false
  principal = chưa xác minh
  credentials = bí mật nhận được
  authorities = []
       |
       v
AuthenticationManager (ProviderManager)
       |
       +---- chọn AuthenticationProvider bằng supports(...)
       |
       v
AuthenticationProvider.authenticate(...)
       |
       +---- tra cứu dữ liệu do server kiểm soát
       +---- xác minh credential
       +---- kiểm tra trạng thái tài khoản/tenant/phạm vi quyền
       |
       +---- thất bại --> AuthenticationException
       |
       +---- thành công --> tạo Authentication kết quả MỚI
                                isAuthenticated = true
                                principal = danh tính đã kiểm chứng
                                credentials = null
                                authorities = quyền từ server
                                       |
                                       v
                         SecurityContext của request
                                       |
                                       v
                         Authorization kiểm tra quyền
~~~

Chỉ cho token đi qua **AuthenticationManager** vẫn chưa đồng nghĩa user đã được đăng nhập trong HTTP request. **AuthenticationManager** trả kết quả; một filter/controller đảm nhiệm bước đặt kết quả vào **SecurityContextHolder**. Nếu dùng session, còn phải xem **SecurityContextRepository** và chính sách lưu context. Nếu dùng API stateless, request kế tiếp phải mang chứng cứ xác thực mới.

Ở ranh giới này có hai điều tách biệt:

- **Authentication**: danh tính/credential có thực sự được xác minh hay chưa?
- **Authorization**: danh tính đã xác minh có quyền vào tài nguyên hay không?

Một API key hợp lệ có thể tạo authenticated token với chỉ quyền **SCOPE_reports.read**; gọi endpoint đòi **SCOPE_reports.write** vẫn phải bị từ chối.

## 3. Thiết kế token bằng AbstractAuthenticationToken

**AbstractAuthenticationToken** thuộc package **org.springframework.security.authentication**. Class này triển khai phần chung của **Authentication**, bao gồm authorities, trạng thái authenticated, details và xử lý xóa thông tin nhạy cảm.

Khi tự tạo token, nên làm rõ các bất biến:

- **Tạo từ input bên ngoài:** public constructor/factory chỉ cho ra **isAuthenticated() == false**.
- **Authorities của input:** rỗng, không có cách truyền authorities bất kỳ từ request vào constructor tạo token đầu vào.
- **Trusted result:** chỉ được tạo sau kiểm tra thành công trong provider hoặc authentication mechanism đáng tin; dùng factory riêng, ưu tiên hạn chế phạm vi truy cập.
- **Không tự nâng quyền:** override **setAuthenticated(true)** để ném **IllegalArgumentException**. Có thể chấp nhận **setAuthenticated(false)** theo hợp đồng interface.
- **Bí mật:** tránh đưa raw password/API key vào **principal**, **details**, tên token, log, exception, JSON response hoặc token đã xác thực.
- **Không đổi nội dung đã xác minh:** các trường principal và authorities của kết quả trusted nên cố định; nếu cần chỉnh quyền, phải tạo kết quả xác thực mới dựa trên kiểm tra tin cậy.

Hãy đặc biệt thận trọng với hai constructor/kiểu factory của những token Spring Security cung cấp sẵn. Ví dụ, **UsernamePasswordAuthenticationToken.unauthenticated(...)** tạo yêu cầu chưa xác thực, còn **UsernamePasswordAuthenticationToken.authenticated(...)** tạo kết quả được tin cậy theo **trách nhiệm của code gọi**. Factory tạo authenticated token **không tự kiểm tra password**. Nếu code xử lý HTTP gọi nhầm factory trusted bằng dữ liệu người dùng, đó là lỗ hổng logic.

### Vì sao không cho client tự đặt isAuthenticated = true?

**isAuthenticated** là một phần hợp đồng tin cậy mà các thành phần khác sử dụng. Giá trị **true** cho biết đối tượng đã vượt qua quy trình xác thực theo cơ chế của ứng dụng. Nếu một request có thể trực tiếp tạo authenticated token và đặt vào context, nó có thể bỏ qua bước kiểm tra credential. Chỉ dựa vào kiểu Java **Authentication** hoặc việc có principal không đủ để suy ra đã xác thực.

**supports(Class<?>)** cũng không phải bước kiểm tra credential: nó chỉ xác định một provider có thể xử lý *kiểu token* nào. Công việc xác minh thực tế phải nằm trong **authenticate(...)**.

## 4. Ví dụ chạy được: Custom API-key token và AuthenticationProvider

Chúng ta xây dựng ví dụ Java 17+ nhỏ, tập trung vào luồng xác thực và không cần khởi động web server:

- Input là một **API key** do client gửi, được coi là *untrusted*.
- **ApiKeyToken.unauthenticated(...)** tạo đối tượng có credentials nhưng chưa có principal/authorities.
- **ApiKeyProvider** kiểm tra SHA-256 của giá trị được gửi với mẫu lưu phía server, dùng phép so sánh mảng byte thích hợp.
- Nếu khớp, provider tạo **ApiKeyToken.verified(...)** với principal **reporting-service**, quyền **SCOPE_reports.read** và không giữ raw API key.
- Nếu không khớp, provider ném **BadCredentialsException**. Luồng không cấp Authentication đã xác thực.
- Cuối cùng, demo thử việc tự gọi **setAuthenticated(true)** trên token đầu vào và nhận lỗi.

**Giới hạn bảo mật của ví dụ:** key **training-api-key** và giá trị băm trong bộ nhớ chỉ dùng để minh họa. Hệ thống thực phải cấp API key đủ entropy bằng CSPRNG, lưu hash/HMAC hoặc token verifier phù hợp, quản lý secret ngoài mã nguồn, hỗ trợ thu hồi, rotation và kiểm soát rate limit. SHA-256 trong ví dụ không biến một key dễ đoán thành bí mật mạnh.

### 4.1. Dự án Gradle

Tạo một project Gradle Java 17, nội dung **build.gradle**:

~~~groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.security:spring-security-core:6.5.11'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'example.ApiKeyDemo'
}
~~~

Ví dụ cố định phiên bản Spring Security 6.5.11 để minh họa hợp đồng API đã xác định. Khi đưa vào một dự án Spring Boot có BOM quản lý dependency, thường nên để BOM chọn phiên bản các thành phần Spring Security nhất quán.

Tạo file **src/main/java/example/ApiKeyDemo.java**:

~~~java
package example;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.Arrays;
import java.util.Collection;
import java.util.List;
import java.util.Objects;

import org.springframework.security.authentication.AbstractAuthenticationToken;
import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

public final class ApiKeyDemo {

    private ApiKeyDemo() {
    }

    /*
     * Một token dùng cả hai giai đoạn, nhưng chỉ provider tin cậy
     * được gọi factory verified(...) ở luồng thành công.
     */
    static final class ApiKeyToken extends AbstractAuthenticationToken {

        private final String principal;
        private String rawKey;

        private ApiKeyToken(
                String principal,
                String rawKey,
                Collection<? extends GrantedAuthority> authorities,
                boolean verified) {
            super(authorities);
            this.principal = principal;
            this.rawKey = rawKey;
            // Gọi trên superclass để không mở cửa setAuthenticated(true)
            // cho code đang giữ token đầu vào.
            super.setAuthenticated(verified);
        }

        public static ApiKeyToken unauthenticated(String incomingKey) {
            if (incomingKey == null || incomingKey.isBlank()) {
                throw new IllegalArgumentException("API key must be present");
            }
            return new ApiKeyToken(null, incomingKey, List.of(), false);
        }

        // Factory trusted không public; provider gọi SAU khi kiểm tra.
        private static ApiKeyToken verified(
                String accountId,
                Collection<? extends GrantedAuthority> authorities) {
            Objects.requireNonNull(accountId, "accountId");
            Objects.requireNonNull(authorities, "authorities");
            return new ApiKeyToken(accountId, null, authorities, true);
        }

        @Override
        public Object getPrincipal() {
            return principal;
        }

        @Override
        public Object getCredentials() {
            return rawKey;
        }

        @Override
        public void setAuthenticated(boolean authenticated) {
            if (authenticated) {
                throw new IllegalArgumentException(
                    "Cannot trust input token via setAuthenticated(true)"
                );
            }
            super.setAuthenticated(false);
        }

        @Override
        public void eraseCredentials() {
            super.eraseCredentials();
            rawKey = null;
        }
    }

    static final class ApiKeyProvider implements AuthenticationProvider {

        // Digest của key mẫu, tính từ dữ liệu do server nắm giữ.
        private final byte[] expectedDigest;

        ApiKeyProvider(String configuredKey) {
            this.expectedDigest = sha256(configuredKey);
        }

        @Override
        public Authentication authenticate(Authentication authentication) {
            if (!(authentication instanceof ApiKeyToken token)) {
                return null; // Provider khác có thể xử lý token khác.
            }

            try {
                if (token.isAuthenticated()) {
                    throw new BadCredentialsException("Invalid API key");
                }

                String suppliedKey = (String) token.getCredentials();
                if (suppliedKey == null) {
                    throw new BadCredentialsException("Invalid API key");
                }

                byte[] suppliedDigest = sha256(suppliedKey);
                boolean matches;
                try {
                    matches = MessageDigest.isEqual(
                        suppliedDigest, expectedDigest
                    );
                } finally {
                    Arrays.fill(suppliedDigest, (byte) 0);
                }

                if (!matches) {
                    throw new BadCredentialsException("Invalid API key");
                }

                // Principal và quyền đến từ phía server, KHÔNG từ input.
                return ApiKeyToken.verified(
                    "reporting-service",
                    List.of(new SimpleGrantedAuthority("SCOPE_reports.read"))
                );
            } finally {
                // Đừng để request token giữ lại credential lâu hơn cần thiết.
                token.eraseCredentials();
            }
        }

        @Override
        public boolean supports(Class<?> authenticationType) {
            return ApiKeyToken.class.isAssignableFrom(authenticationType);
        }
    }

    private static byte[] sha256(String value) {
        try {
            return MessageDigest.getInstance("SHA-256")
                .digest(value.getBytes(StandardCharsets.UTF_8));
        } catch (NoSuchAlgorithmException ex) {
            throw new IllegalStateException("SHA-256 unavailable", ex);
        }
    }

    public static void main(String[] args) {
        ProviderManager manager = new ProviderManager(List.of(
            new ApiKeyProvider("training-api-key")
        ));

        ApiKeyToken request = ApiKeyToken.unauthenticated("training-api-key");
        System.out.println("before=" + request.isAuthenticated());

        Authentication result = manager.authenticate(request);
        System.out.println("after=" + result.isAuthenticated());
        System.out.println("principal=" + result.getName());
        System.out.println(
            "authorities=" + result.getAuthorities().stream()
                .map(GrantedAuthority::getAuthority)
                .toList()
        );
        System.out.println(
            "credentials_absent=" + (result.getCredentials() == null)
        );

        try {
            manager.authenticate(ApiKeyToken.unauthenticated("wrong-key"));
        } catch (BadCredentialsException ex) {
            System.out.println("invalid=rejected");
        }

        try {
            ApiKeyToken.unauthenticated("unverified")
                .setAuthenticated(true);
        } catch (IllegalArgumentException ex) {
            System.out.println("self_trust=rejected");
        }
    }
}
~~~

Từ thư mục chứa **build.gradle** và Gradle wrapper, chạy:

~~~bash
./gradlew run --quiet
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat run --quiet
~~~

Kết quả stdout của chương trình:

~~~text
before=false
after=true
principal=reporting-service
authorities=[SCOPE_reports.read]
credentials_absent=true
invalid=rejected
self_trust=rejected
~~~

Chương trình cần thư viện Spring Security qua Gradle classpath; không thể biên dịch chỉ bằng lệnh **javac ApiKeyDemo.java** mà không thêm các JAR dependency.

### 4.2. Giải thích lần lượt các quyết định trong code

**A. Public factory chỉ tạo input chưa được tin cậy.** Hàm **unauthenticated(...)** không nhận principal hoặc authorities từ caller. Nó chỉ nhận raw key và tạo token có authorities rỗng, trạng thái false. Kiểm tra **isBlank()** là kiểm tra input tối thiểu, không phải xác thực.

**B. Không để code bất kỳ nâng trạng thái bằng setter.** Override **setAuthenticated(true)** ném **IllegalArgumentException**. Trong constructor nội bộ, lời gọi **super.setAuthenticated(verified)** được giới hạn trong logic tạo token. Factory **verified(...)** không public, và quy ước kiến trúc là chỉ provider gọi sau bước đối chiếu credential. Hạn chế quyền gọi factory giúp tránh lỗi lập trình; nó không thay thế việc review code vì các class nội bộ đáng tin vẫn có thể tạo token trusted.

**C. Provider không tin token chỉ vì cùng class.** Provider kiểm tra token thuộc đúng kiểu, đang chưa xác thực, có credentials và có key khớp dữ liệu phía server. Nếu sai, **BadCredentialsException** kết thúc luồng xác thực; không có principal/authorities được cấp.

**D. Trusted result là một đối tượng mới.** Provider không gọi **request.setAuthenticated(true)** và không gắn role trực tiếp lên request token. Nó tạo result không còn raw key, principal là danh tính đã xác minh và authority là quyền do server quyết định.

**E. Dọn credential.** **ApiKeyProvider** gọi **eraseCredentials()** trên request token trong **finally**, kể cả khi thất bại. **ProviderManager** mặc định cũng dọn credential trên kết quả trả về khi kết quả triển khai **CredentialsContainer**. Trong ví dụ result vốn không chứa key. Do Java String là immutable, việc gán trường rawKey về null chỉ bỏ tham chiếu của token, **không cam kết xóa bí mật khỏi mọi bản sao String đang nằm trong bộ nhớ**. Việc hạn chế vòng đời dữ liệu và không ghi log vẫn cần thực hiện.

**F. Digest được so sánh trên dữ liệu server.** **MessageDigest.isEqual(...)** được dùng để so sánh digest. Đây là kỹ thuật minh họa xác minh API key, không đủ để bảo vệ key entropy thấp. Trong hệ thống thực, nên dùng key sinh ngẫu nhiên đủ mạnh và thiết kế schema lưu hash/HMAC, kiểm tra scope, trạng thái thu hồi, ngày hết hạn và rate limit.

**G. Chỉ provider trả về authenticated.** **ProviderManager** tìm provider theo **supports(Class<?>)** và gọi **authenticate(...)**. Phương thức **supports** đúng không đồng nghĩa credential đúng. Nếu nhiều provider hỗ trợ một token, **ProviderManager** có thể thử những provider tiếp theo theo hợp đồng của nó; thiết kế đa provider cần định nghĩa rõ thứ tự và điều kiện từ chối.

## 5. Các bất biến nên kiểm thử

Một custom token an toàn phải đảm bảo đúng các tính chất sau:

| Tình huống | Kỳ vọng |
| --- | --- |
| Tạo từ raw API key hợp lệ về hình thức | **isAuthenticated=false**, authorities rỗng, principal chưa xác minh |
| Client gửi thêm role hoặc accountId tự khai | Không có cách đưa role tự khai vào constructor của token đầu vào |
| Code gọi **setAuthenticated(true)** trên input | **IllegalArgumentException** |
| Credential sai | **AuthenticationException**; không trả token trusted |
| Credential đúng | Provider trả token **mới**, authenticated=true, principal và quyền do server quyết định |
| Trusted result | Không chứa raw credential |
| Provider được hỏi về class khác | **supports(...)** trả false |
| Request sau không có credential trong mô hình stateless | Không tự thừa hưởng kết quả của request trước |
| Endpoint yêu cầu quyền cao hơn | Authorization từ chối dù Authentication hợp lệ |

Có thể bổ sung unit test cho provider dùng kho thông tin xác thực giả lập: key đúng/sai, key bị thu hồi, tenant không hợp lệ, tài khoản bị khóa, quyền được thay đổi ở server. Không dùng *mock* trả thẳng trusted token rồi coi đó là kiểm thử đã xác thực credential.

## 6. Tích hợp token vào ứng dụng Servlet thực

Ví dụ Gradle ở trên minh họa **lõi xác thực**. Trong ứng dụng HTTP, cần một authentication mechanism (filter hoặc controller) làm nhiệm vụ đọc request, tạo token chưa trusted, gọi manager rồi đặt **Authentication kết quả** vào context sau khi thành công.

Đoạn sau là **mã minh họa bên trong authentication filter đã được cấu hình**, không phải class Java độc lập:

~~~java
// rawHeader được đọc từ request.getHeader("X-API-Key").
// authenticationManager và request/response đến từ filter.
Authentication requestToken =
    ApiKeyToken.unauthenticated(rawHeader);

Authentication verified =
    authenticationManager.authenticate(requestToken);

SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(verified);
SecurityContextHolder.setContext(context);

// Filter chain tiếp tục xử lý trong phạm vi context đã xác thực.
// Với ứng dụng stateless: cần đảm bảo context được dọn khi kết thúc
// request; không tự lưu vào HttpSession chỉ vì token đã xác thực.
~~~

Để đoạn này hoạt động trong project riêng, class token cần được tổ chức thành type có phạm vi truy cập phù hợp thay vì nested class của demo; các dependency, import và việc xử lý filter chain phải được cung cấp bởi ứng dụng.

### Những gì filter/controller phải xử lý ngoài ví dụ

1. **Chỉ đọc nguồn đầu vào đã định nghĩa:** ví dụ chỉ chấp nhận một header **X-API-Key** theo hợp đồng API. Giới hạn độ dài; quyết định rõ cách xử lý header lặp, thiếu hoặc sai định dạng. Không cho header **X-Role** ảnh hưởng quyền.
2. **Phân biệt lỗi HTTP:** thiếu/sai credential thường trả **401 Unauthorized**; đã xác thực nhưng không đủ quyền thường trả **403 Forbidden**. Không công khai key, hash hoặc dữ liệu xác minh trong response.
3. **Chọn chính sách phiên:** API key thường được xác thực lại trên mỗi request theo mô hình **STATELESS**. Không dùng HttpSession để lưu raw key. Nếu chủ động thiết kế login có phiên, phải xét **SessionAuthenticationStrategy** và **SecurityContextRepository.saveContext(...)**.
4. **Dọn SecurityContext:** filter tự viết nên quản lý lifecycle an toàn, ví dụ **try/finally** để tránh lây Authentication giữa các request/luồng. Không tự bỏ qua filter chain bảo vệ phân quyền.
5. **Khớp SecurityFilterChain:** filter phải nằm đúng vị trí và đúng chain cần bảo vệ. Với cơ chế do framework hỗ trợ, có thể dùng **AbstractAuthenticationProcessingFilter** cùng success/failure handler và cấu hình repository/session strategy phù hợp.
6. **Mọi request liên quan đều cần xác thực:** nếu ứng dụng dùng stateless, việc controller tự gọi **authenticate** trên endpoint login rồi trả 200 chưa khiến những endpoint khác tự nhận biết user. Authentication phải có trong SecurityContext của **request đang truy cập tài nguyên**.
7. **Giới hạn khả năng sử dụng key:** quản lý scopes, expiry, revoke/rotation, mối quan hệ account/tenant và log sự kiện đã loại bỏ bí mật. Khả năng dùng một key không mặc nhiên cấp toàn bộ quyền của account.

### Khác biệt giữa API key token và pre-authentication token

Một số hệ thống nhận danh tính từ reverse proxy hoặc mTLS gateway đã kiểm tra certificate. Dù phía sau gateway nói “người dùng này đã xác minh”, ứng dụng vẫn phải xác định **có tin được gateway và kênh truyền đó hay không**. Header như **X-User** từ Internet không trở nên an toàn chỉ vì bạn đặt nó vào class có tên **PreAuthenticated...**.

Dữ liệu từ bên ngoài vẫn là untrusted ở ranh giới ứng dụng cho đến khi đã xác minh nguồn và chính sách tin cậy. Nếu proxy là thành phần tin cậy, phải bảo đảm client trực tiếp không thể tự tạo/ghi đè header đó, kết nối nội bộ được bảo vệ, và bộ xác thực phía server chỉ cấp quyền sau khi kiểm tra điều kiện phù hợp.

## 7. Nếu token chứa nhiều trường: tenant, OTP, device hoặc credential khác

Ví dụ API key dùng một credential. Custom token còn có thể mang:

- **tenantId**: chỉ là tenant được yêu cầu, chưa chứng minh người dùng thuộc tenant đó.
- **username/email**: là định danh tự khai, chưa phải principal đã xác thực.
- **OTP**: phải được xác minh thời hạn, ràng buộc với user/challenge, số lần thử và chống phát lại.
- **deviceId**: là thông tin do client cung cấp; không được coi là thiết bị đáng tin nếu thiếu chứng cứ cryptographic.
- **request metadata**: IP hoặc user agent có thể giúp đánh giá rủi ro, nhưng cần xác minh nguồn proxy và không dùng làm chứng cứ duy nhất.

Một thiết kế mẫu:

~~~text
UntrustedTenantLoginToken:
  requestedTenant = từ JSON
  claimedUsername = từ JSON
  password = từ JSON
  authenticated = false
  authorities = []

Provider:
  1. xác thực mật khẩu bằng PasswordEncoder và kho user server
  2. kiểm tra user thuộc requestedTenant
  3. kiểm tra trạng thái user, MFA/OTP nếu yêu cầu
  4. lấy quyền hiệu lực của user trong tenant từ server
  5. trả token mới có principal = verifiedUserId,
     tenantId = verifiedTenantId, authorities = verifiedRoles
~~~

Không dùng **requestedTenant** trực tiếp làm tenant trong token trusted nếu chưa kiểm tra membership. Tương tự, không sao chép **requestedRoles** sang **GrantedAuthority**. **Authentication details** có thể giữ metadata phục vụ audit, nhưng không phải vị trí thích hợp để cất password hoặc đưa quyền tự khai vào logic phân quyền.

Nếu đã có provider chuẩn đáp ứng cơ chế credential, ưu tiên tận dụng nó. Ví dụ username/password tiêu chuẩn thường dùng **UsernamePasswordAuthenticationToken** và **DaoAuthenticationProvider**; custom token có giá trị khi bạn thực sự cần mô hình credential hay metadata khác, không chỉ để đổi tên class.

## 8. Bảo vệ mức độ tin cậy theo thời gian

Một token đã xác thực **không có nghĩa quyền còn hiệu lực mãi mãi**. Với session dài hoặc token cache, quyền/đăng ký account có thể bị thu hồi sau lần xác thực đầu tiên. Thiết kế cần quyết định:

- **Khi nào kiểm tra lại credential:** mọi request, mỗi lần login, hay theo TTL/cache?
- **Khi nào làm mới authorities:** khi yêu cầu hoặc khi dữ liệu user thay đổi?
- **Khi nào thu hồi:** account bị khóa, key bị xoay, token hết hạn, tenant membership bị gỡ?
- **Với nhiều instance:** cache, key store và chính sách revoke có nhất quán không?
- **Giới hạn truy cập:** role/scope trong trusted result có đúng ngữ cảnh endpoint và tenant không?

Đừng hiểu **isAuthenticated=true** là vé đi mọi nơi. Mọi endpoint vẫn cần authorization rõ ràng, ưu tiên quyền tối thiểu.

### Kiểm soát input và secret

- Giới hạn kích thước và loại ký tự của đầu vào trước khi tạo token. Không dùng trực tiếp string chưa kiểm tra trong truy vấn SQL, đường dẫn file hoặc tên bean.
- Nếu credential là mật khẩu, dùng **PasswordEncoder.matches(...)** với hash đã lưu; tránh so sánh plaintext, tự thiết kế thuật toán mật khẩu hoặc hash SHA-256 đơn giản cho password.
- Nếu credential là API key entropy cao, lưu digest/HMAC có chiến lược quản trị phù hợp, tránh log toàn bộ key; cân nhắc key identifier để truy vấn hiệu quả trước khi so sánh secret.
- Xử lý lỗi theo thông điệp chung, giảm rò thông tin user/key có tồn tại hay không. Giới hạn tần suất thử và theo dõi thất bại.
- Không lưu raw credential trong **SecurityContext**, cookie tùy tiện, log, MDC, exception message hoặc event telemetry.

## 9. Mười lỗi thường gặp

| Sai sót | Hậu quả | Cách đúng |
| --- | --- | --- |
| Tạo custom token từ JSON với **isAuthenticated=true** | Bỏ qua ranh giới xác thực | Input token luôn false |
| Constructor public nhận **authorities** từ client | Role injection, có thể tự cấp quyền | Chỉ provider tra quyền từ server |
| Nhận principal **admin** từ header rồi coi là đã xác minh | Giả mạo danh tính | Kiểm tra credential và ánh xạ principal từ server |
| Gọi **setAuthenticated(true)** sau parse JSON | Biến dữ liệu chưa tin thành trusted | Chỉ provider trả kết quả đã xác thực |
| Provider chỉ kiểm tra **supports(...)** rồi trả success | Không xác minh chứng cứ thực tế | Kiểm tra credential trong **authenticate(...)** |
| Khi sai credential trả token authenticated=false thay vì lỗi | Caller có thể xử lý nhầm như thành công | Ném **AuthenticationException** khi thực sự từ chối |
| Trả token trusted nhưng còn giữ raw API key/password | Bí mật sống lâu trong context/session | Xóa credential và giới hạn vòng đời |
| Đọc **X-Role** để tạo **GrantedAuthority** | Bypass authorization | Quyền phải lấy từ kho server |
| Tạo result đúng nhưng không set **SecurityContext** | Endpoint sau không thấy Authentication | Filter/controller tích hợp context đúng cách |
| Dùng token trusted từ session mà không có chính sách revoke | Quyền đã thu hồi có thể còn tác dụng | Xác định TTL, invalidation và recheck policy |

## 10. Câu hỏi tự kiểm tra

**Câu 1.** Một controller đọc JSON gồm username/password/roles và tạo custom Authentication với **isAuthenticated=true**. Vấn đề chính là gì?

**Trả lời:** controller đã cho dữ liệu do client khai đi qua ranh giới tin cậy mà chưa được AuthenticationProvider xác minh; trường roles đặc biệt không được dùng để cấp quyền trực tiếp.

**Câu 2.** Vì sao **supports(ApiKeyToken.class)** trả true không có nghĩa API key hợp lệ?

**Trả lời:** supports chỉ xác định provider xử lý kiểu token, còn phương thức authenticate mới phải đối chiếu credential với dữ liệu tin cậy.

**Câu 3.** Provider kiểm tra key đúng rồi gọi **requestToken.setAuthenticated(true)**. Nên cải thiện thế nào?

**Trả lời:** tạo token kết quả **mới**, principal/authorities do server quyết định, không chứa raw key; input token không cho tự đánh dấu trusted.

**Câu 4.** API key đúng nhưng client yêu cầu quyền **SCOPE_reports.write** qua header, server chỉ cấp **SCOPE_reports.read**. Client có được ghi báo cáo không?

**Trả lời:** không. Authentication thành công không thay đổi quyền do provider/server cấp; authorization phải từ chối quyền không có.

**Câu 5.** Vì sao **eraseCredentials()** trên một String không chắc chắn xóa bí mật hoàn toàn khỏi JVM?

**Trả lời:** String immutable; bỏ tham chiếu trong token không xóa các bản sao khác hoặc nội dung bộ nhớ ngay lập tức. Hạn chế lưu/truyền/log secret vẫn cần.

**Câu 6.** Một endpoint JSON login gọi **AuthenticationManager.authenticate(...)** và nhận result true. Request GET kế tiếp tự động có Authentication không?

**Trả lời:** không nhất thiết. Phải tích hợp kết quả vào SecurityContext đúng vòng đời; nếu muốn duy trì qua session cần repository, còn stateless phải xác thực từng request.

**Câu 7.** Nếu người dùng đăng nhập hợp lệ cho tenant A nhưng gửi thêm tenant B trong JSON thì nên làm gì?

**Trả lời:** provider phải kiểm tra membership/tenant access từ nguồn tin cậy; không gắn tenant B vào kết quả trusted chỉ vì user nhập B.

## Tài liệu chính thức

- [Spring Security 6.5 — Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html)
- [AbstractAuthenticationToken API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/AbstractAuthenticationToken.html)
- [Authentication interface API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/Authentication.html)
- [AuthenticationProvider API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/AuthenticationProvider.html)
- [ProviderManager API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/ProviderManager.html)
- [Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html)
