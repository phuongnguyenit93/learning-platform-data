# Xây AuthenticationProvider và kiểm tra dữ liệu đầu vào

> **Chủ đề:** Spring Security – Servlet stack, Java 17+, Spring Boot 3.x và Spring Security 6.x. Học cách viết một `AuthenticationProvider` cho **cơ chế xác thực tùy chỉnh**, phân định rõ *kiểm tra hình thức input*, *xác minh credential từ nguồn tin cậy*, *kiểm tra trạng thái/hiệu lực* và *cấp Authentication đã xác thực*. Ví dụ chính dùng **API key gồm ID và secret** để người học thấy một luồng khác username/password. Những đoạn Spring bên dưới cần dự án Spring Boot cùng dependencies; phần Java SE độc lập có thể chạy trực tiếp bằng JDK 17.

## 1. Vì sao phải viết AuthenticationProvider?

Spring Security đã có sẵn provider cho những phương thức thông dụng, ví dụ `DaoAuthenticationProvider` cho username/password, provider cho JWT, opaque token, v.v. Không nên viết lại provider chỉ để thay cách đọc tài khoản: nếu vẫn dùng username/password tiêu chuẩn, hãy ưu tiên `UserDetailsService` và `PasswordEncoder`.

Provider tự tạo phù hợp khi cách đưa ra bằng chứng/kiểm tra khác cơ chế đã có, chẳng hạn:

- API key do ứng dụng cấp cho dịch vụ gọi API.
- Mã dùng một lần gắn với challenge và tài khoản, có thời hạn và chống replay.
- Thiết bị hoặc chứng chỉ có quy trình đối chiếu riêng.
- Một vé đăng nhập/attestation nội bộ có định dạng và cơ chế xác thực đặc thù.

Lý do chính của việc tạo provider là **đóng gói quy tắc xác minh bằng chứng**, để servlet filter không phải trực tiếp truy vấn database hay quyết định quyền.

### Sơ đồ luồng

~~~text
Request HTTP đến Servlet container
  |
  v
FilterChainProxy -> SecurityFilterChain khớp đường dẫn
  |
  v
Authentication filter phù hợp cơ chế
  |  (đọc header/body, kiểm tra cỡ và cấu trúc ban đầu)
  |  tạo Authentication CHƯA xác thực
  v
AuthenticationManager (thường ProviderManager)
  |
  | chọn AuthenticationProvider theo supports(tokenType)
  v
Custom AuthenticationProvider.authenticate(requestToken)
  |
  | 1. kiểm tra loại token / dữ liệu đầu vào
  | 2. xác định bản ghi credential từ nguồn đáng tin
  | 3. kiểm tra enabled, expiry, revocation, attempt policy...
  | 4. xác minh secret/chữ ký/hash bằng thuật toán thích hợp
  | 5. lấy danh tính và GrantedAuthority phía server
  v
Authentication ĐÃ xác thực hoặc AuthenticationException
  |
  v
Filter đặt Authentication vào SecurityContext của request
  |
  v
AuthorizationFilter / Controller / response
~~~

**Authentication (authn)** trả lời “bằng chứng có hợp lệ không, đây là ai?”. **Authorization (authz)** trả lời “danh tính ấy có được phép làm hành động này không?”. Đừng để client chọn `GrantedAuthority` rồi chép nguyên vào authenticated result.

## 2. Hợp đồng AuthenticationProvider: supports và authenticate

Interface cốt lõi có hai method:

~~~java
public interface AuthenticationProvider {
    Authentication authenticate(Authentication authentication)
            throws AuthenticationException;

    boolean supports(Class<?> authentication);
}
~~~

Đây là **chữ ký API được rút gọn** để giải thích, không phải định nghĩa lại interface trong project. `Authentication`, `AuthenticationException` và `AuthenticationProvider` là các kiểu của Spring Security.

### `supports(Class<?>)`

- Cho `ProviderManager` biết provider **có khả năng** xử lý *loại* authentication request nào.
- Không kiểm tra mật khẩu/secret, không truy cập database và không quyết định authentication thành công.
- Với token riêng, dùng `MyToken.class.isAssignableFrom(authentication)` nếu cần hỗ trợ subclass hợp lệ. Với token khác, trả `false`.
- Kết quả true **không bảo đảm** provider sẽ xác minh được credential cụ thể. `authenticate(...)` vẫn phải kiểm tra toàn bộ bằng chứng.

### `authenticate(Authentication)`

- Nhận token đại diện cho **lời khai chưa xác thực**.
- Thành công: trả `Authentication` đáng tin cậy, `isAuthenticated()==true`, principal và authorities lấy từ nguồn server, credentials nhạy cảm đã loại bỏ khi có thể.
- Thất bại: ném một `AuthenticationException` thích hợp, thường `BadCredentialsException` cho bằng chứng không hợp lệ.
- Một provider có thể trả `null` để một provider khác có cơ hội xử lý; tuy nhiên với một token thuộc sở hữu provider và credential rõ ràng bị từ chối, **đừng trả null như thể đã thành công**. Mỗi ứng dụng phải hiểu cấu hình nhiều provider, thứ tự và cách `ProviderManager` xử lý exception.
- Lỗi kết nối database, timeout và lỗi lập trình **không** được âm thầm đổi thành authentication thành công hoặc tự bỏ qua verifier.

Với `ProviderManager`, việc chọn provider dựa trên token type; có nhiều provider thì các provider có thể được thử theo thứ tự, tùy kết quả và loại exception. Một provider ném `BadCredentialsException` không bảo đảm không có provider sau được thử trong mọi cấu hình. Do đó, **phải xét toàn bộ tập provider** để chắc rằng không có đường fallback yếu bất ngờ.

## 3. Phân biệt dữ liệu đầu vào và bằng chứng đã được kiểm chứng

Trong ví dụ API key, client gửi:

~~~http
GET /api/read HTTP/1.1
Host: api.example.test
X-Api-Key: client01.abcdefghijklmnopqrstuvwxyz012345
~~~

Giá trị trên là **dữ liệu demo**, dễ đoán và **không dùng làm API key production**. API key thật phải được tạo bằng bộ sinh số ngẫu nhiên mật mã (`SecureRandom`), đủ entropy (chẳng hạn 32 byte ngẫu nhiên cho phần secret), gửi qua TLS và được bảo vệ như password.

Ví dụ chọn cấu trúc:

~~~text
<key-id>.<secret>
    |
    +-- key-id: 8..32 ký tự [A-Za-z0-9_-]
    +-- secret: 32..128 ký tự [A-Za-z0-9_-]
~~~

Tại sao tách hai phần?

- `key-id` là **chỉ mục tra cứu**, không phải chứng cứ xác thực; nếu ai biết ID thì vẫn không có quyền.
- `secret` mới là phần bí mật; hệ thống chỉ lưu **digest của secret ngẫu nhiên mạnh** hoặc HMAC phù hợp, không lưu plaintext secret ở kho dữ liệu.
- Điều kiện độ dài và ký tự giúp cắt input sai sớm, giảm chi phí DB/query/hash và loại giá trị có ký tự header nguy hiểm.
- Hash của token entropy cao có thể dùng SHA-256 trong mô hình này; **không suy rộng SHA-256 trần sang mật khẩu do con người chọn**. Password nên dùng thuật toán password hashing có work factor như BCrypt/Argon2id/PBKDF2 phù hợp chính sách.
- Format hợp lệ **không chứng minh** secret đúng: cần tra cứu key ID, so digest theo cách giảm rò rỉ thời gian và kiểm tra revocation/expiry.

### Các tầng kiểm tra

| Tầng | Ví dụ cần kiểm tra | Nếu sai |
| --- | --- | --- |
| HTTP boundary / filter | Có đúng một header? Có quá dài? Đúng endpoint? | Từ chối an toàn hoặc chuyển cho chain nếu thiếu key và endpoint có cơ chế riêng. |
| Parser định dạng | Đúng `id.secret`, tập ký tự/độ dài, không chứa whitespace/CRLF, không có nhiều dấu chấm. | Không gọi DB, không tạo authenticated token. |
| Credential store | ID có bản ghi? Bản ghi còn hiệu lực, chưa thu hồi? | Từ chối, không tiết lộ user/key tồn tại. |
| Verifier | Digest của secret có khớp bản ghi tin cậy? | `BadCredentialsException`; không cấp authorities. |
| Provider result | Principal, authorities lấy từ server và đúng scope của credential? | Chỉ tạo authenticated result khi tất cả điều kiện thành công. |
| Authorization | Endpoint cần `SCOPE_READ` hay quyền khác? | Có thể trả 403 dù đã xác thực. |

**Quan trọng:** Các kiểm tra như regex, `trim()`, `isBlank()`, length hoặc parse JSON chỉ nói về **định dạng**. Chúng không thể thay thế kiểm tra bí mật/chữ ký và chính sách hiệu lực.

## 4. Thiết kế token riêng: chỉ provider được tạo authenticated result

Spring Security dùng `Authentication` như dữ liệu truyền giữa filter, manager và provider. Với cơ chế tùy chỉnh, không cần ép tất cả request vào `UsernamePasswordAuthenticationToken`: một kiểu token riêng giúp `supports` rõ ràng và tránh provider khác nhận nhầm credential.

Tạo `src/main/java/com/example/customauth/ApiKeyAuthenticationToken.java`:

~~~java
package com.example.customauth;

import java.util.Collection;
import java.util.List;
import org.springframework.security.authentication.AbstractAuthenticationToken;
import org.springframework.security.core.GrantedAuthority;

public final class ApiKeyAuthenticationToken
        extends AbstractAuthenticationToken {

    private final Object principal;
    private Object credentials;

    private ApiKeyAuthenticationToken(
            Object principal,
            Object credentials,
            Collection<? extends GrantedAuthority> authorities,
            boolean verified) {
        super(authorities);
        this.principal = principal;
        this.credentials = credentials;
        // Chỉ factory nằm trong class này gọi super để đặt true.
        super.setAuthenticated(verified);
    }

    public static ApiKeyAuthenticationToken forRequest(String rawApiKey) {
        return new ApiKeyAuthenticationToken(
                "unverified-api-key", rawApiKey, List.of(), false);
    }

    public static ApiKeyAuthenticationToken verified(
            String serviceName,
            Collection<? extends GrantedAuthority> authorities) {
        return new ApiKeyAuthenticationToken(
                serviceName, null, authorities, true);
    }

    @Override
    public Object getPrincipal() {
        return principal;
    }

    @Override
    public Object getCredentials() {
        return credentials;
    }

    @Override
    public void eraseCredentials() {
        super.eraseCredentials();
        credentials = null;
    }

    @Override
    public void setAuthenticated(boolean authenticated) {
        if (authenticated) {
            throw new IllegalArgumentException(
                    "Use the verified factory inside a trusted provider");
        }
        super.setAuthenticated(false);
    }
}
~~~

**Mục đích thiết kế:**

- Factory `forRequest(...)` luôn tạo token **chưa xác thực**, rỗng authorities. Không tin principal hay quyền từ header.
- Factory `verified(...)` được provider dùng **sau khi xác minh**; constructor private là rào cản lập trình cơ bản.
- Method `setAuthenticated(true)` trên một instance do bên ngoài nắm giữ bị từ chối. Tuy nhiên factory `verified(...)` vẫn là public trong mã minh họa để provider gọi: **không phải một ranh giới bảo mật chống mã Java không đáng tin trong cùng tiến trình**. Ứng dụng phải kiểm soát nơi gọi factory bằng thiết kế/module, code review và kiểm thử. Không bao giờ nhận cờ verified do client gửi.
- `getCredentials()` của token đầu vào giữ raw key trong phạm vi cần xử lý; token đầu ra dùng `null`. Không log/tokenize object có secrets; String trong Java không thể xóa bytes khỏi heap tức thì.
- Đối tượng `Authentication` kết quả **không phải HTTP session**. Với API stateless, nó chỉ tồn tại trong context của request hiện tại.

Nếu hệ thống dùng OTP hoặc chữ ký thay API key, có thể thay phần verifier và kiểu credential, nhưng nguyên tắc token đầu vào false → provider xác minh → token kết quả true vẫn giữ nguyên.

## 5. Parser đầu vào tái sử dụng: `ApiKeyFormat.java`

Tạo file:

~~~java
package com.example.customauth;

import java.util.Optional;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public final class ApiKeyFormat {

    private static final Pattern KEY_SHAPE = Pattern.compile(
            "([A-Za-z0-9_-]{8,32})\\.([A-Za-z0-9_-]{32,128})"
    );

    private ApiKeyFormat() {}

    public record Parts(String keyId, String secret) {}

    public static Optional<Parts> parse(String raw) {
        // 32 ký tự ID + 1 dấu chấm + 128 ký tự secret.
        if (raw == null || raw.length() > 161) {
            return Optional.empty();
        }

        Matcher match = KEY_SHAPE.matcher(raw);
        if (!match.matches()) {
            return Optional.empty();
        }

        return Optional.of(new Parts(match.group(1), match.group(2)));
    }
}
~~~

Đây là **bộ kiểm tra hình thức**, không phải verifier xác thực. Một số quyết định rõ ràng:

1. `Matcher.matches()` yêu cầu **toàn chuỗi** khớp regex, không cho phép thêm ký tự lạ ở đầu/cuối.
2. Không gọi `trim()` rồi chấp nhận dữ liệu sai; HTTP header chứa khoảng trắng/CRLF cần bị từ chối chứ không “chỉnh hộ” thành key khác.
3. `raw.length()` giới hạn kích cỡ trước khi regex tạo nhóm, giảm chi phí xử lý input bất thường.
4. `[A-Za-z0-9_-]` là tập ASCII nhỏ; ví dụ không hỗ trợ Unicode lookalike hoặc dấu chấm bổ sung.
5. Một key có đúng hình thức nhưng secret không đủ entropy vẫn **không đạt yêu cầu cấp phát key thật**. Validator phải đi kèm quy trình cấp key từ `SecureRandom`.

Đặt validator ở server và dùng lại khi tạo demo fixture/test. Nếu có nhu cầu đổi format, phải version hóa/ràng buộc để không vô tình chấp nhận secret theo giao thức cũ ngoài policy.

## 6. Kho credential: chỉ lưu hash/digest và metadata tin cậy

Tạo `ApiKeyRecord.java`:

~~~java
package com.example.customauth;

import java.time.Instant;
import java.util.List;
import org.springframework.security.core.GrantedAuthority;

public record ApiKeyRecord(
        String id,
        String subject,
        byte[] secretDigest,
        boolean enabled,
        Instant expiresAt,
        List<GrantedAuthority> authorities) {

    public ApiKeyRecord {
        // Sao chép để không ai bên ngoài sửa trực tiếp digest/quyền.
        secretDigest = secretDigest.clone();
        authorities = List.copyOf(authorities);
    }

    @Override
    public byte[] secretDigest() {
        return secretDigest.clone();
    }
}
~~~

Tạo `ApiKeyStore.java`:

~~~java
package com.example.customauth;

import java.util.Optional;

public interface ApiKeyStore {
    Optional<ApiKeyRecord> findById(String id);
}
~~~

Bản ghi chứa: ID, tên dịch vụ/subject, digest của secret, trạng thái enabled, thời hạn và authorities **do server cấp**. Không có phương thức nhận quyền từ request.

Trong production, `ApiKeyStore` thường đọc từ database có unique ID và policy thu hồi, ví dụ câu SQL **minh họa**:

~~~sql
SELECT key_id, subject_id, secret_digest, enabled, expires_at
FROM service_api_keys
WHERE key_id = ?;
~~~

Dấu `?` là tham số bind, không nối string từ client vào SQL. Authorities có thể được tải từ bảng scope gắn với key. Không lưu raw key, không xuất digest ra API. Giao dịch cập nhật key/thu hồi phải có audit và phân quyền admin rõ ràng.

### Hàm digest cho secret entropy cao

Tạo `ApiKeyDigests.java`:

~~~java
package com.example.customauth;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;

public final class ApiKeyDigests {

    private ApiKeyDigests() {}

    public static byte[] sha256(String secret) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            return digest.digest(
                    secret.getBytes(StandardCharsets.US_ASCII));
        } catch (NoSuchAlgorithmException ex) {
            throw new IllegalStateException("SHA-256 is not available", ex);
        }
    }
}
~~~

**Phạm vi đúng:** phần `secret` của API key **được sinh ngẫu nhiên đủ mạnh**, không phải password do người dùng tự chọn. SHA-256 của 256-bit random secret không có cùng rủi ro dictionary attack như SHA-256 của password yếu. Dù vậy, có thể dùng HMAC với server-side pepper/key để tăng bảo vệ theo threat model; cần quản lý/rotation pepper riêng. Đừng chuyển ví dụ này thành nơi lưu password của account.

Nếu lưu digest trong DB với kiểu binary/hex, quy định rõ format, encoding và index. Để so hai digest, dùng `MessageDigest.isEqual(a, b)` thay `Arrays.equals(...)` trong đường xác thực bí mật; dù vậy, **toàn bộ API không tự động constant-time** vì việc tồn tại key ID, thời gian query và các nhánh khác vẫn có thể tạo khác biệt. Dùng rate limiting, giám sát và các biện pháp thích hợp.

## 7. Provider thật: định dạng → lookup → hiệu lực → verify → result

Tạo `ApiKeyAuthenticationProvider.java`:

~~~java
package com.example.customauth;

import java.security.MessageDigest;
import java.time.Instant;
import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.core.Authentication;

public final class ApiKeyAuthenticationProvider
        implements AuthenticationProvider {

    private final ApiKeyStore store;

    public ApiKeyAuthenticationProvider(ApiKeyStore store) {
        this.store = store;
    }

    @Override
    public boolean supports(Class<?> authenticationType) {
        return ApiKeyAuthenticationToken.class.isAssignableFrom(
                authenticationType);
    }

    @Override
    public Authentication authenticate(Authentication input) {
        if (!(input instanceof ApiKeyAuthenticationToken token)) {
            return null;
        }

        if (!(token.getCredentials() instanceof String raw)) {
            throw new BadCredentialsException("Invalid API key");
        }

        ApiKeyFormat.Parts parts = ApiKeyFormat.parse(raw)
                .orElseThrow(() ->
                    new BadCredentialsException("Invalid API key"));

        ApiKeyRecord record = store.findById(parts.keyId())
                .orElseThrow(() ->
                    new BadCredentialsException("Invalid API key"));

        if (!record.enabled()
                || !Instant.now().isBefore(record.expiresAt())) {
            throw new BadCredentialsException("Invalid API key");
        }

        byte[] presented = ApiKeyDigests.sha256(parts.secret());
        byte[] expected = record.secretDigest();

        if (!MessageDigest.isEqual(expected, presented)) {
            throw new BadCredentialsException("Invalid API key");
        }

        return ApiKeyAuthenticationToken.verified(
                record.subject(), record.authorities());
    }
}
~~~

### Mổ xẻ từng bước

**Bước 1 — Type guard.** `supports` phải khớp token type. Kiểm tra `instanceof` trong `authenticate` là defense-in-depth khi provider được gọi trực tiếp. Không tự nhận `UsernamePasswordAuthenticationToken` hoặc JWT bearer token nếu không phải trách nhiệm của provider này.

**Bước 2 — Chỉ nhận credential đúng kiểu.** Nếu token không có raw key dạng String, báo lỗi; không gọi `toString()` tùy tiện trên object từ client rồi chuyển thành secret.

**Bước 3 — Parse giới hạn input.** `ApiKeyFormat.parse` kiểm tra format trước khi query. Token rất dài, Unicode bất thường, nhiều dấu chấm, whitespace hoặc ký tự điều khiển bị từ chối.

**Bước 4 — Lookup phía server.** `keyId` chỉ là chỉ mục. Không đọc tên subject/authorities từ body/header do người dùng truyền. Trường hợp key ID không tồn tại và key sai dùng cùng thông báo `Invalid API key`; không public “ID này có tồn tại”.

**Bước 5 — Kiểm tra trạng thái.** Key bị disable hoặc hết hạn không hợp lệ dù secret đúng. Điều kiện `Instant.now().isBefore(record.expiresAt())` khiến key **hết hạn ngay tại mốc expiry**. Trong hệ thống thật, cần kiểm tra cả revocation, tenant, allowed scope, rotation và clock-skew policy tùy giao thức.

**Bước 6 — So digest.** Chỉ secret đúng mới được cấp result. Việc so digest thuộc provider, không đặt trong servlet filter/controller.

**Bước 7 — Tạo result đã xác thực.** `record.subject()` và `record.authorities()` đến từ nguồn server. Result không giữ raw API key. Nếu ứng dụng cần phân biệt service identity với end-user identity, principal nên là kiểu riêng và policies phải biết điều đó; không mặc định service API key tương đương một người dùng đăng nhập đầy đủ.

### Vì sao provider không gọi SecurityContextHolder?

Hợp đồng provider là **xác minh và trả kết quả**. Servlet authentication filter/manager tích hợp mới quản lý context, request lifecycle và HTTP response. Nếu provider tự `SecurityContextHolder.setContext(...)`, nó bị gắn với giao thức HTTP và dễ gây rò rỉ giữa request/thread hoặc hỏng flow khác.

### Vì sao không có `UsernameNotFoundException`?

Đây là API key authentication, không phải username/password qua `UserDetailsService`. Với API key, dùng `BadCredentialsException` cho credential invalid là phù hợp. Với token OTP/custom certificate, exception cụ thể có thể khác; quan trọng là không cấp Authentication mới khi verifier không thành công.

## 8. Servlet filter nhận header, gọi manager, xử lý lỗi an toàn

Tạo `ApiKeyHeaderFilter.java`:

~~~java
package com.example.customauth;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.util.Enumeration;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.filter.OncePerRequestFilter;

public final class ApiKeyHeaderFilter extends OncePerRequestFilter {

    private static final String HEADER_NAME = "X-Api-Key";
    private final AuthenticationManager manager;

    public ApiKeyHeaderFilter(AuthenticationManager manager) {
        this.manager = manager;
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {

        Enumeration<String> values = request.getHeaders(HEADER_NAME);

        if (!values.hasMoreElements()) {
            // Chưa có chứng cứ: ủy quyền tiếp cho authorization policy.
            chain.doFilter(request, response);
            return;
        }

        String raw = values.nextElement();

        if (values.hasMoreElements()) {
            // Header lặp có thể bị các proxy/framework ghép khác nhau.
            response.sendError(HttpServletResponse.SC_UNAUTHORIZED);
            return;
        }

        final Authentication verified;
        try {
            verified = manager.authenticate(
                    ApiKeyAuthenticationToken.forRequest(raw));
        } catch (AuthenticationException ex) {
            SecurityContextHolder.clearContext();
            // Không phản chiếu secret, ID tồn tại hoặc exception message.
            response.sendError(HttpServletResponse.SC_UNAUTHORIZED);
            return;
        }

        SecurityContext context = SecurityContextHolder.createEmptyContext();
        context.setAuthentication(verified);
        SecurityContextHolder.setContext(context);

        try {
            chain.doFilter(request, response);
        } finally {
            // Không mang principal của request này sang thread/request khác.
            SecurityContextHolder.clearContext();
        }
    }
}
~~~

**Tại sao filter này không tự so hash?** Vì filter chỉ đọc header và giao việc cho `AuthenticationManager`. Như vậy provider có thể được unit test độc lập; HTTP filter có thể được integration test qua MockMvc.

**Tại sao bắt exception chỉ quanh `manager.authenticate`?** Nếu bắt toàn bộ `chain.doFilter(...)` như một lỗi login thì một lỗi từ controller hoặc authorization downstream có thể bị chẩn đoán sai, thậm chí cố gửi `401` sau khi response đã được commit. Ví dụ chỉ bắt `AuthenticationException` nảy sinh ở giai đoạn authentication.

**Tại sao thiếu header được chuyển tiếp?** Một endpoint công khai có thể không đòi key. Với endpoint protected, authorization sẽ nhìn thấy không có authenticated principal và từ chối theo cấu hình. Nếu hệ thống bắt buộc key ở mọi path, có thể từ chối ngay trong filter, nhưng phải định nghĩa rõ policy cho health endpoint.

**Tại sao xử lý header trùng?** Nhiều proxy có thể ghép header lặp thành chuỗi có dấu phẩy hoặc giữ nhiều giá trị. Policy ở đây là một key duy nhất; cả trường hợp ghép thành chuỗi không hợp regex cũng bị provider loại.

**Chú ý xử lý async:** `OncePerRequestFilter` có chính sách dispatch riêng; `SecurityContextHolder` mặc định dựa vào thread hiện tại. Trong ứng dụng có async/error dispatch, cần kiểm tra cơ chế context propagation, cleanup và filter dispatch cho đúng; không giả định một lần set context đủ cho mọi background task.

## 9. Cấu hình Spring Security 6: chỉ đăng ký filter một lần

Tạo `SecurityConfig.java`:

~~~java
package com.example.customauth;

import jakarta.servlet.http.HttpServletResponse;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;
import org.springframework.security.web.context.NullSecurityContextRepository;

@Configuration
public class SecurityConfig {

    @Bean
    ApiKeyAuthenticationProvider apiKeyProvider(ApiKeyStore store) {
        return new ApiKeyAuthenticationProvider(store);
    }

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(
            HttpSecurity http,
            ApiKeyAuthenticationProvider provider) throws Exception {

        AuthenticationManager manager = new ProviderManager(provider);

        http
            .securityMatcher("/api/**")
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .securityContext(context -> context
                .securityContextRepository(
                    new NullSecurityContextRepository()))
            .exceptionHandling(ex -> ex
                .authenticationEntryPoint((request, response, problem) ->
                    response.sendError(
                        HttpServletResponse.SC_UNAUTHORIZED)))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public").permitAll()
                .requestMatchers("/api/read").hasAuthority("SCOPE_READ")
                .anyRequest().denyAll())
            .addFilterBefore(
                new ApiKeyHeaderFilter(manager),
                UsernamePasswordAuthenticationFilter.class);

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain fallback(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
            .anyRequest().denyAll());
        return http.build();
    }
}
~~~

**Giải thích quan trọng:**

1. `securityMatcher("/api/**")` chọn chain cho nhóm API. `requestMatchers(...)` trong `authorizeHttpRequests` xác định quyền **trong chain đã chọn**. Không nhầm chúng.
2. `ApiKeyHeaderFilter` được tạo bằng `new` trong cấu hình chain, **không** gắn `@Component` hoặc `@Bean` vào filter này. Nếu Boot tự đăng ký cùng filter làm servlet-container filter, nó có thể chạy ngoài `FilterChainProxy` hoặc chạy hai lần. Cách tạo trực tiếp tránh lỗi double registration trong ví dụ.
3. `addFilterBefore(..., UsernamePasswordAuthenticationFilter.class)` dùng mốc thứ tự filter mà Spring Security đã biết; không có nghĩa demo bật form login. Đây là API-key authentication, không dùng `POST /login`.
4. `ProviderManager(provider)` chứa provider tùy chỉnh cho filter; việc xác minh vẫn được tách khỏi filter. Nếu thêm provider khác, phải review hỗ trợ token và thứ tự, không để fallback yếu xác thực cùng credential.
5. `SessionCreationPolicy.STATELESS` và `NullSecurityContextRepository` minh họa không lưu authenticated principal giữa request. Request sau phải gửi key lại.
6. `csrf(AbstractHttpConfigurer::disable)` ở đây chỉ áp dụng cho **API stateless nhận secret qua header không phải credential tự động gắn với cookie của browser**. Không sao chép thiết lập tắt CSRF vào ứng dụng web form login dùng cookie/session mà không đánh giá threat model.
7. `exceptionHandling.authenticationEntryPoint(...)` trả `401` khi endpoint protected cần xác thực mà request thiếu key. `403` vẫn có thể phát sinh khi đã xác thực nhưng thiếu `SCOPE_READ`.
8. Chain thứ hai deny-all để những endpoint ngoài `/api/**` không bị bỏ qua hoàn toàn khi demo chỉ khai báo một API chain. Trong ứng dụng có UI/form login thật, thay fallback bằng chain chính sách riêng.
9. API key phải truyền trên HTTPS; nếu app ở sau proxy, proxy phải bảo vệ TLS và không log/forward header secret sang điểm đến không tin cậy.

### HTTP status không đồng nghĩa với loại exception duy nhất

- Key thiếu ở `/api/read`: thường `401 Unauthorized` qua entry point.
- Key sai/hết hạn/bị thu hồi: `AuthenticationException` được filter chuyển thành `401` chung.
- Key đúng nhưng thiếu authority: authorization từ chối, thường `403 Forbidden`.
- Endpoint ngoài chain API: fallback deny; status có thể khác tùy handler/entry point, nhưng không được phép truy cập.
- Database lỗi: không được convert thành `200` hoặc tự cấp principal; xác định chính sách `503`/`500` và metric thích hợp tùy vận hành.

## 10. Seed demo API key theo profile, không nhúng production secret

Để các ví dụ chạy được với Spring Boot, tạo một `ApiKeyStore` trong memory khi bật profile `demo`. Tạo `DemoKeyStoreConfig.java`:

~~~java
package com.example.customauth;

import java.time.Instant;
import java.util.List;
import java.util.Optional;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.core.env.Environment;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

@Configuration
@Profile("demo")
public class DemoKeyStoreConfig {

    @Bean
    ApiKeyStore apiKeyStore(Environment environment) {
        String raw = environment.getRequiredProperty("DEMO_API_KEY");

        ApiKeyFormat.Parts parts = ApiKeyFormat.parse(raw)
            .orElseThrow(() ->
                new IllegalStateException("Invalid demo key format"));

        ApiKeyRecord record = new ApiKeyRecord(
                parts.keyId(),
                "svc-demo",
                ApiKeyDigests.sha256(parts.secret()),
                true,
                Instant.parse("2099-01-01T00:00:00Z"),
                List.of(new SimpleGrantedAuthority("SCOPE_READ"))
        );

        return id -> record.id().equals(id)
                ? Optional.of(record)
                : Optional.empty();
    }
}
~~~

Ví dụ sử dụng secret **được đặt ngoài code** qua biến môi trường `DEMO_API_KEY`. Giá trị cố định sau đây **chỉ để thử localhost và test**, không đủ tính bí mật để dùng thật:

~~~text
client01.abcdefghijklmnopqrstuvwxyz012345
~~~

**Trong production**, thay config demo bằng một bean `ApiKeyStore` đọc database hoặc key management service, có rotation/revocation và audit. Key thật nên được tạo bằng `SecureRandom` và chỉ hiển thị cho chủ sở hữu một lần. Dù key ID có thể public, phần secret vẫn phải nằm trong secret manager; không gửi qua query string hoặc log.

### Controller và main application

Tạo `ApiController.java`:

~~~java
package com.example.customauth;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ApiController {

    @GetMapping("/api/public")
    public String publicEndpoint() {
        return "public";
    }

    @GetMapping("/api/read")
    public String read(Authentication authentication) {
        return authentication.getName();
    }
}
~~~

Tạo `CustomAuthApplication.java`:

~~~java
package com.example.customauth;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CustomAuthApplication {
    public static void main(String[] args) {
        SpringApplication.run(CustomAuthApplication.class, args);
    }
}
~~~

Để Spring Boot scan đủ, đặt những class trên trong cùng package `com.example.customauth` hoặc package con thuộc package có `@SpringBootApplication`. Dependency runtime cần có `spring-boot-starter-web` và `spring-boot-starter-security`; test cần `spring-boot-starter-test`, `spring-security-test`.

### Chạy và gọi API

Giả sử đã có project Spring Boot với Maven Wrapper. Trên Unix/macOS:

~~~bash
export SPRING_PROFILES_ACTIVE=demo
export DEMO_API_KEY=client01.abcdefghijklmnopqrstuvwxyz012345
./mvnw spring-boot:run
~~~

Trong terminal khác:

~~~bash
curl -i http://localhost:8080/api/public
curl -i http://localhost:8080/api/read
curl -i -H 'X-Api-Key: client01.abcdefghijklmnopqrstuvwxyz012345' \
  http://localhost:8080/api/read
~~~

Kết quả logic với demo:

- `GET /api/public`: trả `200`, body `public`.
- `GET /api/read` không key: trả `401` theo entry point.
- `GET /api/read` với key demo hợp lệ: trả `200`, body `svc-demo`.
- `GET /api/read` với key sai: trả `401`.
- Gọi `GET /api/read` không key **sau** request hợp lệ vẫn phải `401` vì không lưu context sang request mới.

Không khẳng định toàn bộ header/stdout của `curl -i` giống nhau ở mọi môi trường; chỉ nêu status/body có ý nghĩa cho luồng trong ví dụ. Khi dùng production, không chạy `curl -v` hoặc log command chứa secret vào hệ thống lưu audit nếu có thể lộ key.

## 11. Kiểm thử tích hợp với MockMvc

Tạo `src/test/java/com/example/customauth/ApiKeyAuthenticationIntegrationTest.java`:

~~~java
package com.example.customauth;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest(properties =
    "DEMO_API_KEY=client01.abcdefghijklmnopqrstuvwxyz012345")
@AutoConfigureMockMvc
@ActiveProfiles("demo")
class ApiKeyAuthenticationIntegrationTest {

    private static final String GOOD_KEY =
            "client01.abcdefghijklmnopqrstuvwxyz012345";

    @Autowired MockMvc mvc;
    @Autowired ApiKeyAuthenticationProvider provider;

    @Test
    void publicEndpointNeedsNoKey() throws Exception {
        mvc.perform(get("/api/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));
    }

    @Test
    void validKeyAuthenticatesOnlyTheCurrentRequest() throws Exception {
        mvc.perform(get("/api/read").header("X-Api-Key", GOOD_KEY))
            .andExpect(status().isOk())
            .andExpect(content().string("svc-demo"));

        mvc.perform(get("/api/read"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void invalidSecretsAndUnknownIdsAreRejected() throws Exception {
        mvc.perform(get("/api/read").header(
                "X-Api-Key",
                "client01.abcdefghijklmnopqrstuvwxyz012346"))
            .andExpect(status().isUnauthorized());

        mvc.perform(get("/api/read").header(
                "X-Api-Key",
                "unknown1.abcdefghijklmnopqrstuvwxyz012345"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void malformedAndDuplicateHeadersAreRejected() throws Exception {
        mvc.perform(get("/api/read")
                .header("X-Api-Key", "//bad.example"))
            .andExpect(status().isUnauthorized());

        mvc.perform(get("/api/read")
                .header("X-Api-Key", GOOD_KEY, GOOD_KEY))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void unsupportedAuthenticationTypeIsNotClaimed() {
        assertFalse(provider.supports(
                UsernamePasswordAuthenticationToken.class));
    }

    @Test
    void callerCannotFlipAnUnverifiedTokenToAuthenticated() {
        ApiKeyAuthenticationToken input =
                ApiKeyAuthenticationToken.forRequest(GOOD_KEY);

        assertFalse(input.isAuthenticated());
        assertThrows(IllegalArgumentException.class,
                () -> input.setAuthenticated(true));
    }
}
~~~

Kiểm thử trên thật sự đi qua `FilterChainProxy`/API filter/provider cho những HTTP request của `MockMvc`. Nó xác nhận:

1. Protected endpoint yêu cầu key và public endpoint vẫn truy cập được khi không có key.
2. Secret đúng được ánh xạ tới principal server `svc-demo`; secret khác chỉ một ký tự bị từ chối.
3. Key ID khác nhưng secret trùng không thể xác thực bằng bản ghi của ID cũ.
4. Input không hợp regex hoặc gửi hai header không được chấp nhận.
5. Chứng cứ không lưu giữa request: mỗi request protected phải tự gửi key.
6. Provider không tuyên bố xử lý `UsernamePasswordAuthenticationToken`.
7. Client không thể tự dùng `setAuthenticated(true)` trên token input.

Chạy test trong project có Maven Wrapper:

~~~bash
./mvnw test
~~~

Không bịa stdout cố định của Maven, vì kết quả phụ thuộc version dependency, JDK và môi trường.

### Thêm unit test cho trạng thái và quyền

Dùng một `ApiKeyStore` giả lập trả bản ghi cụ thể, không cần HTTP:

~~~java
package com.example.customauth;

import static org.junit.jupiter.api.Assertions.assertThrows;
import java.time.Instant;
import java.util.List;
import java.util.Optional;
import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

class ApiKeyProviderUnitTest {

    private static final String KEY =
            "client01.abcdefghijklmnopqrstuvwxyz012345";
    private static final String SECRET =
            "abcdefghijklmnopqrstuvwxyz012345";

    @Test
    void disabledOrExpiredCredentialCannotAuthenticate() {
        ApiKeyRecord expired = new ApiKeyRecord(
            "client01",
            "svc-demo",
            ApiKeyDigests.sha256(SECRET),
            true,
            Instant.parse("2000-01-01T00:00:00Z"),
            List.of(new SimpleGrantedAuthority("SCOPE_READ"))
        );

        ApiKeyRecord disabled = new ApiKeyRecord(
            "client01",
            "svc-demo",
            ApiKeyDigests.sha256(SECRET),
            false,
            Instant.parse("2099-01-01T00:00:00Z"),
            List.of(new SimpleGrantedAuthority("SCOPE_READ"))
        );

        ApiKeyAuthenticationProvider expiredProvider =
            new ApiKeyAuthenticationProvider(id -> Optional.of(expired));
        ApiKeyAuthenticationProvider disabledProvider =
            new ApiKeyAuthenticationProvider(id -> Optional.of(disabled));

        assertThrows(BadCredentialsException.class,
            () -> expiredProvider.authenticate(
                ApiKeyAuthenticationToken.forRequest(KEY)));
        assertThrows(BadCredentialsException.class,
            () -> disabledProvider.authenticate(
                ApiKeyAuthenticationToken.forRequest(KEY)));
    }
}
~~~

Test thực tế nên bổ sung các trường hợp secret đúng nhưng **authority không đủ** (endpoint khác yêu cầu scope cao hơn → 403), key bị revoke sau khi đã từng hợp lệ, có nhiều tenant, key hết hạn đúng mốc, store timeout, concurrent rotation, header dài, encoded Unicode và tỷ lệ request thất bại cao. Test không nên lưu key thật hoặc output digest vào report.

### So sánh test unit và integration

| Bài test | Điều chứng minh | Điều chưa chứng minh |
| --- | --- | --- |
| `ApiKeyFormat.parse` unit | Cú pháp input được giới hạn. | Key hợp lệ về bảo mật. |
| `ApiKeyAuthenticationProvider` unit | Quy tắc lookup, trạng thái và so digest. | Filter order, status HTTP hay context. |
| `MockMvc` integration | Servlet filter chain, authn, authz và response của demo. | Quy tắc Host/TLS của reverse proxy production hoặc hiệu suất thật. |
| Deployment test | HTTPS/proxy, secret rotation/revocation, routing thật. | Toàn bộ rủi ro dài hạn nếu không có monitoring/alert. |

Không dùng mock kiểu “trả Authentication true cho mọi input” rồi coi provider đã được test bảo mật; phải có ca chứng minh **credential sai không tạo authenticated result**.

## 12. Ví dụ Java 17 độc lập: xác nhận hình thức, không xác thực bí mật

Mã này chạy bằng JDK 17 không cần Spring và cố ý tách validation khỏi verification. Tạo `ApiKeyFormatDemo.java`:

~~~java
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public final class ApiKeyFormatDemo {

    private static final Pattern SHAPE = Pattern.compile(
        "([A-Za-z0-9_-]{8,32})\\.([A-Za-z0-9_-]{32,128})"
    );

    private static void inspect(String supplied) {
        if (supplied == null || supplied.length() > 161) {
            System.out.println("REJECT: invalid shape");
            return;
        }

        Matcher matcher = SHAPE.matcher(supplied);
        if (!matcher.matches()) {
            System.out.println("REJECT: invalid shape");
            return;
        }

        System.out.println("FORMAT_OK: keyId=" + matcher.group(1));
    }

    public static void main(String[] args) {
        inspect("client01.abcdefghijklmnopqrstuvwxyz012345");
        inspect("client01.short");
        inspect("client01.abcdefghijklmnopqrstuvwxyz012345.extra");
        inspect(null);
    }
}
~~~

Chạy:

~~~bash
javac ApiKeyFormatDemo.java
java ApiKeyFormatDemo
~~~

Stdout **chính xác**:

~~~text
FORMAT_OK: keyId=client01
REJECT: invalid shape
REJECT: invalid shape
REJECT: invalid shape
~~~

Chương trình chỉ xác nhận input thuộc một **ngôn ngữ cú pháp** cho phép; nó **không** tra cứu key ID, không kiểm tra expiry/enable, không so digest và **không cấp quyền**. Đây là cách kiểm tra ranh giới trách nhiệm ở cấp Java SE trước khi dùng Spring.

## 13. Nếu muốn xác thực OTP thay vì API key

Mô hình provider vẫn giống nhưng điều kiện bảo mật của OTP khác hẳn API key dài hạn:

- OTP phải được ràng buộc tới account và một **challenge** do server cấp; không chỉ nhận `username + 6-digit code` rồi tin username.
- Kiểm tra expiration, giới hạn số lần thử, chống brute-force theo account/IP/challenge, và **đánh dấu đã dùng bằng thao tác nguyên tử** trước khi chấp nhận một OTP một lần.
- Với TOTP, phải dùng verifier chuẩn với clock window giới hạn, chống replay/step reuse và có quy trình khôi phục; không tự sinh code bằng `Random` thường.
- Nếu OTP là **yếu tố thứ hai**, chỉ mã OTP đúng **không đủ** để nói người dùng đã hoàn thành toàn bộ MFA; provider/flow phải ràng buộc với bước xác thực thứ nhất và session/challenge đáng tin.
- Khi kết hợp nhiều bước, có thể dùng các token riêng thể hiện trạng thái tạm thời nhưng đừng tự gán đầy đủ authority trước khi các bước bắt buộc hoàn tất.
- OTP không giống API key: secret ngắn có entropy thấp, nên không nên sao chép phương pháp lưu SHA-256 của API key dài ngẫu nhiên vào kho OTP mà thiếu rate limiting, expiry và anti-replay.

Tương tự, nếu xác thực JWT, hãy ưu tiên `JwtDecoder`/provider chuẩn; khi tự viết custom verifier phải kiểm tra **chữ ký, algorithm allowlist, issuer, audience, expiry, nbf, key rotation** và các claim liên quan. `matches(regex)` trên cấu trúc JWT không đủ.

## 14. Các lỗi phổ biến khi viết AuthenticationProvider

### 14.1. Tạo authenticated token trước khi kiểm chứng

~~~java
// PHẢN VÍ DỤ: không làm thế với input chưa tin cậy.
return ApiKeyAuthenticationToken.verified(
    request.getParameter("username"),
    List.of(new SimpleGrantedAuthority("ROLE_ADMIN"))
);
~~~

Đây là **đoạn giả lập lỗ hổng**, không thể dùng như chương trình độc lập vì thiếu ngữ cảnh biến/import. Nếu subject/quyền đến từ client hoặc không có verifier, attacker có thể tự gán danh tính/quyền.

### 14.2. `supports(...)` quá rộng

~~~java
@Override
public boolean supports(Class<?> type) {
    return true; // PHẢN VÍ DỤ.
}
~~~

Nếu provider nhận mọi loại Authentication nhưng lại ép `(ApiKeyAuthenticationToken) input`, nó có thể gây `ClassCastException` hoặc nhận nhầm flow. Chỉ nhận đúng token type. Nếu thật sự có nhiều loại, lập hợp đồng rõ cho từng loại.

### 14.3. Coi kiểm tra định dạng là xác thực

`if (apiKey.matches("[A-Za-z0-9_.-]+")) return authenticated;` là sai. Regex chỉ kiểm tra cú pháp; không chứng minh sở hữu secret, trạng thái key, quyền hay nguồn phát hành.

### 14.4. So bí mật bằng so chuỗi thường

`raw.equals(storedSecret)` vừa đòi lưu plaintext secret, vừa có thể tạo vấn đề timing. Trong ví dụ, store lưu digest và dùng `MessageDigest.isEqual`. Với password do người dùng nhập, dùng `PasswordEncoder.matches` thay vì SHA-256 trần.

### 14.5. Gửi exception message nội bộ cho client

Không phản chiếu key ID, secret, trạng thái tồn tại hoặc stack trace. Các trường hợp “unknown key”, “wrong secret”, “revoked key” có thể cùng thông báo HTTP chung, trong khi telemetry nội bộ có mã lỗi giảm nhạy cảm. Tránh user/key enumeration.

### 14.6. Bắt toàn bộ Exception rồi cho qua

Code kiểu `catch (Exception ex) { return ApiKeyAuthenticationToken.verified(...); }` là fail-open nguy hiểm. Lỗi DB, lỗi parse, timeout phải thất bại an toàn, không cấp result. Nhưng cũng không nên biến mọi lỗi hạ tầng thành “người dùng sai password” rồi mất cảnh báo vận hành.

### 14.7. Trộn role từ client với role từ database

Không lấy `X-Role: ADMIN` hoặc JSON field `roles=["ADMIN"]` làm authority trong result. Quyền chỉ được cấp từ policy/store do server quản lý; mọi request vẫn phải qua authorization riêng.

### 14.8. Đăng ký custom filter hai lần

Một filter là Spring bean có thể bị Boot tự đăng ký vào servlet container **và** được thêm vào Spring Security chain. Kết quả: chạy sai thứ tự hoặc hai lần, tạo hành vi khó dự đoán. Trong ví dụ, filter không phải bean, được tạo bằng `new` chỉ trong `apiChain`.

### 14.9. Nhầm AuthenticationProvider với AuthenticationManager

Provider biết **cách xác minh một kiểu token**. Manager điều phối provider. Filter gọi manager, không gọi thẳng từng provider. Nếu có nhiều chains, xác nhận manager/provider của chain cụ thể và kiểm tra không có đường fallback khác nhận token sai.

### 14.10. Ghi credential vào log hoặc header response

Không log toàn bộ request headers, `Authentication.getCredentials()`, API key, hash, secret hoặc session cookie. Vẫn có thể log correlation ID, loại provider, lỗi cấp cao và key ID đã được xử lý theo chính sách bảo mật; không ghi raw secret.

### 14.11. Quên trạng thái và revocation

Một key khớp digest nhưng bị disable/hết hạn/thu hồi phải bị từ chối. Nếu dùng cache, cần có invalidation/TTL và kế hoạch propagation khi revoke. Cần phân biệt key được *cấp quyền truy cập* và key còn *hiệu lực kỹ thuật*.

### 14.12. Đọc SecurityContext trên thread không đúng

`SecurityContextHolder` mặc định gắn với thread. Không giả định một task `@Async`/`CompletableFuture` tự nhận context của request. Cần cơ chế propagation thích hợp và cleanup; trong hệ thống background, ưu tiên danh tính máy/service riêng thay vì chuyển raw API key qua nhiều executor.

## 15. Thiết kế vận hành và kiểm thử ngoài ví dụ

**Vòng đời key.** Có thao tác tạo bằng `SecureRandom`, hiển thị secret chỉ một lần, lưu digest, chỉ định subject/scopes, expiration, rotation chồng lấn có giới hạn, disable/revoke, ghi audit và xóa key cũ đúng hạn. Nếu có tenant, unique ID và quyền phải ràng buộc tenant từ nguồn đáng tin.

**Độ trễ.** Lookup nhanh bằng key ID có index; giới hạn chiều dài input trước DB; rate limit theo client/key ID/IP ở mức phù hợp; không làm expensive password hash cho mỗi API key 256-bit nếu kiến trúc không yêu cầu. Với credential yếu/low entropy, threat model hoàn toàn khác.

**Điều kiện host/proxy.** API sử dụng HTTPS, kiểm soát trusted proxy và forwarding. Không lấy user identity từ `X-Forwarded-User` hay header tương tự do Internet gửi nếu không có gateway xác thực và ranh giới tin cậy rõ.

**Báo lỗi.** Invalid credential thường 401, thiếu quyền thường 403. Không cho phép việc trả HTTP 200 với object `authenticated=true` do client quyết định. Nếu có lỗi DB, xử lý service availability như một lỗi hệ thống và theo dõi alert mà không làm lộ secrets.

**Metrics bảo mật.** Theo dõi tỷ lệ 401, 403, số request bị từ chối vì malformed/header duplicate, key expiry/revocation, provider latency và số lần update key. Không gắn raw API key vào metric labels vì gây lộ secret/cardinality cao.

### Ma trận test gợi ý

| Ca | Kỳ vọng |
| --- | --- |
| Header thiếu ở endpoint public | 200 nếu policy permitAll. |
| Header thiếu ở endpoint protected | 401, không có principal authenticated. |
| Header sai định dạng, quá dài, có newline | 401, không query store khi parser thất bại. |
| Hai header `X-Api-Key` | 401, không dùng giá trị đầu tiên tùy tiện. |
| Key ID tồn tại, secret sai | 401; không cấp authorities. |
| Key ID không tồn tại | 401; không tiết lộ ID có tồn tại hay không. |
| Key disabled, expired, revoked | 401 dù secret đúng. |
| Key đúng, scope đủ | 200; principal đến từ store. |
| Key đúng, scope thiếu | 403; authentication có thể đúng nhưng authorization không cho qua. |
| Request sau không gửi key | Không tái sử dụng principal của request trước. |
| Store timeout | Fail closed; có metric/alarm và response phù hợp, không tự bypass. |
| Hai security chain | Request khớp đúng chain và provider; không bị fallback provider nhận sai. |
| Credential secret xuất hiện trong log | Test/log review phải phát hiện và loại bỏ. |

## 16. Checklist và tự kiểm tra

**Checklist trước khi phát hành:**

- [ ] Có lý do cụ thể để viết provider riêng thay vì dùng `DaoAuthenticationProvider`, JWT decoder hoặc cơ chế có sẵn.
- [ ] `supports(Class<?>)` chỉ nhận đúng token type.
- [ ] Authentication request do filter tạo bắt đầu với `isAuthenticated()==false`, không có authorities do client cấp.
- [ ] Validator giới hạn kích cỡ và format trước khi thực hiện IO tốn kém.
- [ ] Verifier kiểm tra secret bằng cơ chế phù hợp entropy/thuật toán, có trạng thái enabled, expiry và revocation.
- [ ] Principal và authorities lấy từ nguồn server sau kiểm chứng.
- [ ] Provider ném `AuthenticationException` với bằng chứng sai; không tạo authenticated result nếu verifier thất bại.
- [ ] Filter gọi `AuthenticationManager`, không truy vấn DB/so hash thay provider.
- [ ] SecurityContext chỉ tồn tại đúng phạm vi request và được cleanup.
- [ ] Không double-register filter qua Boot và security chain.
- [ ] HTTPS và bảo vệ secret ở log, config, database, request và response.
- [ ] Test cả validation, provider, HTTP filter, status/authority và multiple requests.
- [ ] Có quy trình key rotation, revoke, audit và xử lý lỗi hạ tầng an toàn.

**Q1. `supports(...)` trả true có nghĩa credential hợp lệ chưa?** Chưa. Nó chỉ cho biết provider có thể xử lý **lớp token** đó. `authenticate(...)` mới kiểm chứng.

**Q2. Kiểm tra regex đủ để xác thực API key không?** Không. Regex chỉ kiểm tra cấu trúc, còn phải tra kho key, kiểm tra expiry/revocation và so secret.

**Q3. Vì sao không cho filter tự đặt `isAuthenticated=true` từ header?** Vì header do client kiểm soát; chỉ provider/verifier đáng tin mới được tạo authenticated result sau thành công.

**Q4. Dùng `SHA-256` cho secret API key được không?** Có thể phù hợp cho secret **ngẫu nhiên entropy rất cao**. Không áp dụng cho password do con người chọn; password cần KDF chuyên dụng có work factor.

**Q5. Vì sao `401` và `403` khác nhau?** `401` thường là thiếu/sai authentication; `403` là đã xác thực nhưng không có quyền theo authorization policy.

**Q6. Tại sao không khai báo `ApiKeyHeaderFilter` là `@Component` trong ví dụ?** Để tránh Boot tự đăng ký thành container filter ngoài security chain khi đã thêm filter bằng `http.addFilterBefore(...)`.

**Q7. Một request hợp lệ có khiến request sau tự xác thực không?** Không với API stateless ở đây. Request sau phải gửi key; context cũ được dọn và không được lưu trong session.

**Q8. Nếu OTP chỉ có sáu chữ số thì dùng cùng hash/chiến lược API key được không?** Không nên. OTP có entropy thấp, cần challenge binding, expiry ngắn, rate limiting và chống replay; không sao chép giả định của API key ngẫu nhiên dài.

**Ghi nhớ:** **Filter lấy input → token chưa xác thực → manager chọn provider → provider kiểm tra hình thức + nguồn tin cậy + bằng chứng + trạng thái → token đã xác thực → context → authorization**. Đặc biệt, **“dữ liệu hợp lệ về cú pháp” không đồng nghĩa “danh tính đã được xác thực”**.
