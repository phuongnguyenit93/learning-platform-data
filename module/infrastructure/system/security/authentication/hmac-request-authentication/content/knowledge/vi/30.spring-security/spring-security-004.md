# Authentication manager trong Spring Security cho HMAC request authentication

## 1. AuthenticationManager giải quyết vấn đề gì?

Trong Spring Security, một HTTP request đi qua **SecurityFilterChain** trước khi vào controller. Với xác thực HMAC, filter nhận các trường như key ID, timestamp, nonce và chữ ký, nhưng bản thân filter không nên chứa toàn bộ logic tìm secret, kiểm tra trạng thái credential, tạo canonical request và đánh giá replay. Spring Security cung cấp giao diện **AuthenticationManager** để thực hiện quyết định xác thực theo một hợp đồng thống nhất:

~~~java
public interface AuthenticationManager {
    Authentication authenticate(Authentication authentication)
        throws AuthenticationException;
}
~~~

Đầu vào là một đối tượng `Authentication` **chưa được tin cậy**. Đầu ra khi thành công là một `Authentication` đã được xác thực, có principal và các authority do server xác định. Nếu thất bại, cơ chế xác thực phát sinh một `AuthenticationException`. `AuthenticationManager` là giao diện; `ProviderManager` là một triển khai phổ biến, ủy quyền cho danh sách `AuthenticationProvider`.

Với module **SECURITY_AUTHENTICATION_HMAC_REQUEST_AUTHENTICATION**, ta cần xác thực request HTTP bằng shared secret và canonical request được định nghĩa rõ: method, URI, một số header và body/body digest. Ngoài HMAC đúng, hệ thống phải kiểm tra timestamp, nonce chống replay, trạng thái credential khi xoay khóa, quan hệ client/tenant và sự nhất quán qua proxy/gateway. `AuthenticationManager` giúp đặt những bước thuộc **authentication** vào một đường xử lý có thể kiểm thử và tái sử dụng, trong khi **authorization** vẫn kiểm tra quyền gọi từng endpoint sau khi xác thực thành công.

### Ví dụ nghiệp vụ

API `POST /api/hmac/payments` được đối tác A gọi với key ID `partner-a-k4`. Đối tác tạo chữ ký `HmacSHA256` bằng K4 trên canonical request theo hợp đồng. Server cần biết:

1. Request khai key ID nào, client/tenant nào, timestamp/nonce ra sao?
2. Credential `partner-a-k4` có tồn tại, thuộc đúng đối tác và đang ACTIVE không?
3. Server dựng lại **chính xác các bytes được ký** hay đã bị gateway rewrite?
4. HMAC có khớp với secret của đúng key ID không?
5. Timestamp còn trong cửa sổ chấp nhận và nonce chưa dùng chưa?
6. Nếu xác thực thành công, đối tác A có được phép tạo khoản thanh toán này không?

Các câu 1–5 thuộc pipeline authentication. Câu 6 thuộc authorization nghiệp vụ. Một request có chữ ký HMAC đúng **không tự động có quyền** gọi mọi API.

## 2. Các thành phần Spring Security cần phân biệt

| Thành phần | Vai trò trong giải pháp HMAC |
| --- | --- |
| `SecurityFilterChain` | Chọn và chạy tập filter phù hợp với đường dẫn HTTP |
| `OncePerRequestFilter` | Adapter lấy thông tin từ `HttpServletRequest`, gọi manager và gắn kết quả xác thực |
| `Authentication` | Token đầu vào chưa xác thực và đối tượng kết quả đã xác thực |
| `AuthenticationManager` | Giao diện nhận token và quyết định xác thực |
| `ProviderManager` | Chuyển yêu cầu cho provider hỗ trợ kiểu token tương ứng |
| `AuthenticationProvider` | Thực thi cách xác thực cụ thể; ở đây là HMAC request |
| `SecurityContextHolder` | Giữ `SecurityContext` trong phạm vi luồng xử lý đang hoạt động |
| `AuthenticationEntryPoint` | Tạo phản hồi HTTP cho thất bại/chưa có xác thực, thường 401 |
| `AuthorizationManager` / `authorizeHttpRequests` | Kiểm tra quyền sau khi đã có principal được xác thực |
| `CredentialRegistry` / secret manager | Lưu mapping key → client, trạng thái, secret reference và vòng đời khóa |
| `ReplayStore` | Ghi nhận nonce nguyên tử và kiểm soát cửa sổ chống phát lại |

Sơ đồ xử lý:

~~~mermaid
flowchart TD
    A["HTTP request"] --> B["SecurityFilterChain"]
    B --> C["HmacAuthenticationFilter"]
    C --> D["AuthenticationManager.authenticate(token chưa tin cậy)"]
    D --> E["ProviderManager"]
    E --> F["HmacAuthenticationProvider"]
    F --> G["Tra credential, trạng thái, secret"]
    G --> H["Canonical request + HMAC + timestamp + nonce"]
    H --> I{"Thành công?"}
    I -->|Không| X["AuthenticationException → 401"]
    I -->|Có| J["Authentication đã xác thực"]
    J --> K["SecurityContextHolder"]
    K --> L["AuthorizationManager"]
    L --> M{"Có quyền?"}
    M -->|Không| Y["403 hoặc phản hồi che giấu tài nguyên theo policy"]
    M -->|Có| N["Controller + service"]
~~~

**AuthenticationManager không phải authorization manager.** Kết quả `isAuthenticated() == true` cho biết server đã xác nhận danh tính theo cơ chế HMAC; nó không bảo đảm principal được phép truy cập tenant, resource hoặc thao tác đang yêu cầu.

## 3. ProviderManager chọn provider như thế nào?

`ProviderManager` giữ một hoặc nhiều `AuthenticationProvider`. Mỗi provider có hai phương thức chính:

~~~java
public interface AuthenticationProvider {
    Authentication authenticate(Authentication authentication)
        throws AuthenticationException;

    boolean supports(Class<?> authentication);
}
~~~

`supports(...)` cho biết provider **có khả năng nhận kiểu token đó**. Nó không khẳng định chữ ký đúng, key tồn tại hay request sẽ thành công.

Khi manager nhận một token, nó xem xét các provider hỗ trợ kiểu token tương ứng. Provider có thể trả một `Authentication` xác thực thành công hoặc báo lỗi. Với cấu hình nhiều provider, việc provider trả `null` hoặc ném một số ngoại lệ có thể dẫn tới thử provider khác theo quy tắc của `ProviderManager`; các ngoại lệ tình trạng tài khoản có thể làm chuỗi dừng sớm. Vì vậy, nếu mục tiêu là **một hợp đồng HMAC duy nhất**, hãy cấu hình một manager với provider HMAC rõ ràng và không xây dựng cơ chế “thử lần lượt mọi secret/key version” qua nhiều provider.

Ví dụ:

~~~java
@Bean
AuthenticationManager hmacAuthenticationManager(
        HmacAuthenticationProvider hmacProvider) {
    return new ProviderManager(List.of(hmacProvider));
}
~~~

Trong một ứng dụng có form login, bearer token và HMAC, mỗi đường có thể dùng **filter chain/manager phù hợp**. Không dùng `UsernamePasswordAuthenticationToken` làm đầu vào HMAC chỉ để “tận dụng” provider username/password, bởi điều đó làm mờ loại bằng chứng đang được xác minh và khiến provider không liên quan có thể nhận request.

### Cần tránh ba nhầm lẫn

- **`supports()` không thay thế kiểm tra credential.** Nó chỉ kiểm tra kiểu class.
- **`AuthenticationManager` không tự đọc HTTP request.** Filter hoặc adapter phải tạo token từ request.
- **Kết quả của manager không tự đi vào `SecurityContextHolder` khi gọi trực tiếp từ custom filter.** Filter phải đưa kết quả đã xác thực vào context trước khi cho request đi tiếp.

## 4. Hợp đồng request HMAC làm đầu vào cho manager

Giả sử API yêu cầu:

~~~http
POST /api/hmac/payments?currency=VND HTTP/1.1
Host: api.example.test
Content-Type: application/json
X-Client-Id: partner-a
X-Key-Id: partner-a-k4
X-Tenant-Id: tenant-a
X-Timestamp: 2026-11-28T04:00:00Z
X-Nonce: a63f79d2-e2fc-4a4b-9f97-3a9bcfd14ce8
X-Signature: <base64-hmac-sha256>

{"amount":250000}
~~~

Chuỗi signature trong ví dụ là **placeholder**, không phải một vector HMAC dùng để kiểm chứng. Hợp đồng ký `HMAC-REQUEST-V1` có thể chọn các dòng UTF-8:

~~~text
HMAC-REQUEST-V1
POST
/api/hmac/payments?currency=VND
partner-a
partner-a-k4
tenant-a
2026-11-28T04:00:00Z
a63f79d2-e2fc-4a4b-9f97-3a9bcfd14ce8
<sha256-hex-cua-body-bytes>
~~~

Cần xác định rõ dấu xuống dòng, ký tự kết thúc, thuật toán hash body, cách chuẩn hóa path/query, cách xử lý query trùng, header trùng và byte gốc của body. Nếu `X-Key-Id` hoặc `X-Tenant-Id` ảnh hưởng đến xác thực/định tuyến, chúng phải được ràng buộc nhất quán vào hợp đồng ký. Ký tenant ID **không** đồng nghĩa client được phép truy cập tenant đó: vẫn cần đối chiếu owner tenant và policy.

Công thức minh họa:

\[
S = \operatorname{Base64}
\left(\operatorname{HMAC\mbox{-}SHA256}
(K_{\text{partner-a-k4}},\ \operatorname{UTF8}(\text{canonicalRequest}))\right)
\]

Server phải dùng đúng secret của `partner-a-k4` để kiểm tra. Không thử K3, K2 hay “key mới nhất” khi chữ ký K4 sai; key rotation có thể cho nhiều version ACTIVE, nhưng mỗi request phải định danh chính xác version dùng để ký.

### Vì sao adapter HTTP quan trọng?

`AuthenticationManager` làm việc với object Java, không làm việc trực tiếp với `HttpServletRequest`. Lớp adapter/filter phải:

- Giới hạn kích thước request và header, từ chối key ID, timestamp, nonce không đúng định dạng.
- Phát hiện header trùng và dạng biểu diễn mơ hồ, không lấy ngẫu nhiên một giá trị.
- Xây dựng canonical URI theo hợp đồng, chú ý `contextPath`, query, percent-encoding và rewrite ở gateway.
- Băm **bytes thực tế** của request body, không serialize lại JSON rồi tưởng bytes giống phía client.
- Cho controller/service vẫn đọc được body sau khi adapter xác minh HMAC. Nếu filter đã tiêu thụ input stream, cần một request wrapper hỗ trợ đọc lại có giới hạn, hoặc kiến trúc verify ở tầng có thể dùng cùng body bytes.
- Không tin `X-Original-URI` hoặc `X-Forwarded-Host` do client tự cung cấp. Chỉ dùng dữ liệu forwarded từ gateway đáng tin và hợp đồng ký đã được kiểm thử.

`ContentCachingRequestWrapper` chỉ cache những bytes **đã được đọc**; việc bọc request không tự động bảo đảm toàn bộ body đã có trong cache và cũng không tự tạo cơ chế cho downstream đọc lại sau khi stream bị tiêu thụ. Nếu verifier cần body trước controller, hãy thiết kế wrapper/buffer đọc lại đúng cách và áp đặt giới hạn kích thước.

## 5. Định nghĩa token HMAC chưa được xác thực

Nên dùng một kiểu token riêng để `ProviderManager` điều phối đúng provider. Token ban đầu chỉ mang **bằng chứng mà client gửi** và các giá trị canonical do tầng HTTP đáng tin tạo; chưa chứa authority do client tự khai.

Ví dụ Java 17 / Spring Security 6:

~~~java
import java.util.List;
import java.util.Objects;
import org.springframework.security.authentication.AbstractAuthenticationToken;

record HmacEvidence(
    String keyId,
    String claimedClientId,
    String requestedTenantId,
    String timestamp,
    String nonce,
    String signatureBase64,
    String canonicalRequest
) {}

public final class HmacAuthenticationToken
        extends AbstractAuthenticationToken {

    private final HmacEvidence evidence;

    public HmacAuthenticationToken(HmacEvidence evidence) {
        super(List.of());
        this.evidence = Objects.requireNonNull(evidence);
        super.setAuthenticated(false);
    }

    public HmacEvidence evidence() {
        return evidence;
    }

    @Override
    public Object getPrincipal() {
        // Đây mới là định danh được KHAI trong request.
        return evidence.claimedClientId();
    }

    @Override
    public Object getCredentials() {
        return evidence.signatureBase64();
    }
}
~~~

Đoạn ví dụ tập trung vào token đầu vào. Ở ứng dụng thực tế, mỗi `public` top-level type cần file Java thích hợp; bản ghi `HmacEvidence` có thể được dùng ở phạm vi package. Chưa có `HmacAuthenticationToken` nào được phép coi là trusted chỉ vì `getPrincipal()` trả client ID.

`canonicalRequest` **không được lấy từ một chuỗi do client trực tiếp khai báo**. Nó phải được dựng tại adapter từ HTTP request thực tế theo hợp đồng ký đã duyệt. Nếu upstream có thể truyền một chuỗi “canonical” tùy ý xuống provider, kẻ tấn công có thể đưa vào chuỗi khác với request được controller thực thi.

Để hạn chế rò rỉ, token thành công nên chỉ giữ principal và authorities tin cậy. Không lưu shared secret trong `Authentication`, `SecurityContext`, exception, MDC hoặc HTTP response. Chữ ký HMAC cũng là dữ liệu nhạy cảm phục vụ xác minh, tránh log trực tiếp.

## 6. HmacAuthenticationProvider: trung tâm của quyết định xác thực

Một provider HMAC nhận token chưa tin cậy, tra đúng credential, đánh giá trạng thái, xác minh chữ ký và kiểm tra chống replay. Sau đó nó trả một `Authentication` đã xác thực.

Đoạn mẫu sau dùng các interface của ứng dụng để giữ rõ trách nhiệm. `Evidence` và `HmacAuthenticationToken` ở phần trước là input; `CredentialRegistry`, `HmacSignatureVerifier` và `ReplayGuard` do đội triển khai cung cấp.

~~~java
import java.time.Clock;
import java.time.Instant;
import java.util.List;
import java.util.Optional;
import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.CredentialsExpiredException;
import org.springframework.security.authentication.DisabledException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

enum KeyState {
    PENDING, ACTIVE, SUSPENDED, REVOKED, RETIRED
}

record HmacCredential(
    String keyId,
    String clientId,
    String ownerTenantId,
    String secretRef,
    boolean clientEnabled,
    boolean tenantEnabled,
    KeyState keyState,
    Instant validFrom,
    Instant expiresAt
) {}

record HmacPrincipal(
    String clientId,
    String ownerTenantId,
    String requestedTenantId,
    String keyId
) {}

interface CredentialRegistry {
    Optional<HmacCredential> findByKeyId(String keyId);
}

interface HmacSignatureVerifier {
    // Tự đọc secretRef từ kho bí mật, xây canonical bytes đúng hợp đồng.
    boolean verify(
        String secretRef,
        String canonicalRequest,
        String signatureBase64
    );
}

interface ReplayGuard {
    // Kiểm tra timestamp và ghi nonce nguyên tử toàn cụm.
    boolean acceptIfFresh(
        String keyId,
        String timestamp,
        String nonce,
        Instant serverNow
    );
}

public final class HmacAuthenticationProvider
        implements AuthenticationProvider {

    private final CredentialRegistry registry;
    private final HmacSignatureVerifier verifier;
    private final ReplayGuard replayGuard;
    private final Clock clock;

    public HmacAuthenticationProvider(
            CredentialRegistry registry,
            HmacSignatureVerifier verifier,
            ReplayGuard replayGuard,
            Clock clock) {
        this.registry = registry;
        this.verifier = verifier;
        this.replayGuard = replayGuard;
        this.clock = clock;
    }

    @Override
    public boolean supports(Class<?> authentication) {
        return HmacAuthenticationToken.class
            .isAssignableFrom(authentication);
    }

    @Override
    public Authentication authenticate(Authentication authentication) {
        HmacEvidence proof =
            ((HmacAuthenticationToken) authentication).evidence();

        HmacCredential key = registry.findByKeyId(proof.keyId())
            .orElseThrow(() ->
                new BadCredentialsException("authentication_failed"));

        if (!key.clientId().equals(proof.claimedClientId())) {
            throw new BadCredentialsException("authentication_failed");
        }

        if (!key.clientEnabled() || !key.tenantEnabled()) {
            throw new DisabledException("authentication_failed");
        }

        if (key.keyState() != KeyState.ACTIVE) {
            throw new BadCredentialsException("authentication_failed");
        }

        Instant now = clock.instant();
        if (now.isBefore(key.validFrom())
                || !now.isBefore(key.expiresAt())) {
            throw new CredentialsExpiredException(
                "authentication_failed");
        }

        if (!verifier.verify(
                key.secretRef(),
                proof.canonicalRequest(),
                proof.signatureBase64())) {
            throw new BadCredentialsException("authentication_failed");
        }

        if (!replayGuard.acceptIfFresh(
                key.keyId(), proof.timestamp(),
                proof.nonce(), now)) {
            throw new BadCredentialsException("authentication_failed");
        }

        // Tenant được yêu cầu đã nằm trong dữ liệu HMAC được ký.
        // Nó CHƯA tự trở thành tenant được phép; authorization
        // phải kiểm tra owner/grant/action/resource trước nghiệp vụ.
        HmacPrincipal principal = new HmacPrincipal(
            key.clientId(),
            key.ownerTenantId(),
            proof.requestedTenantId(),
            key.keyId()
        );

        return UsernamePasswordAuthenticationToken.authenticated(
            principal,
            null,
            List.of(new SimpleGrantedAuthority("ROLE_HMAC_CLIENT"))
        );
    }
}
~~~

**Đọc đoạn mã theo ý nghĩa kiến trúc:** khi `authenticate` trả kết quả thành công, principal và authority đến từ **registry/policy phía server**, không đến từ header tự khai. `ROLE_HMAC_CLIENT` chỉ là dấu hiệu “đã xác thực bằng HMAC”; nó không cấp quyền truy cập mọi tenant hay mọi endpoint. Cần kiểm tra owner tenant, delegated grant, resource và action trong authorization. Trong mô hình không cho delegation, chính sách có thể yêu cầu `requestedTenantId == ownerTenantId` ngay trước khi cho xử lý nghiệp vụ.

Mã mẫu không bao gồm triển khai thật của registry, việc tạo canonical bytes từ request, đồng bộ trạng thái thu hồi, TTL của nonce store và quản lý exception hạ tầng. Các bước này cần được làm rõ trong hệ thống triển khai thực tế.

### Trạng thái credential và rotation

Một credential có thể ở ACTIVE, PENDING, SUSPENDED, REVOKED hoặc RETIRED. Kết quả `keyState == ACTIVE` chưa đủ nếu đã quá `expiresAt`, hoặc có `revokedAt`/denylist cần kiểm tra. Chính sách thu hồi phải được đánh giá từ **nguồn trạng thái đủ mới**. Nếu registry đã REVOKED K3 nhưng gateway còn cache ACTIVE, provider có thể chấp nhận request sai cho tới khi cache hết hạn. Phải đo và kiểm soát độ trễ thu hồi.

Key rotation có thể cho K3 và K4 đồng thời ACTIVE trong thời gian chuyển tiếp. Provider vẫn phải tra **đúng key ID** trong request và dùng đúng secret tương ứng; không tính HMAC bằng lần lượt mọi key của cùng client. Khi nghi lộ K3, việc REVOKED K3 phải chặn được request mới dù chữ ký, timestamp và nonce đều hợp lệ.

### Thứ tự chống replay và HMAC

`ReplayGuard.acceptIfFresh` được gọi sau khi chữ ký HMAC hợp lệ, để người không có secret không dễ dàng giữ trước nonce của client thật. Nó cần:

- Parse timestamp theo format hợp đồng và kiểm tra cửa sổ bằng thời gian server.
- Dùng thao tác ghi nonce chỉ khi chưa tồn tại, **nguyên tử** và dùng chung giữa các verifier.
- Chọn khóa replay tối thiểu gồm credential/key ID và nonce; nếu scope nonce theo tenant, phải có quy tắc rõ ràng và chống đổi tenant để dùng lại request.
- TTL bao phủ **toàn bộ thời gian chữ ký còn có thể được chấp nhận**. Với cửa sổ đối xứng ±5 phút, TTL cố định thường cần ít nhất 10 phút cộng độ đệm, hoặc TTL tính từ `timestamp + window`.
- Khi replay store không khả dụng, từ chối theo chính sách fail closed, không mặc định cho qua.

`ReplayGuard` cũng có thể kiểm tra timestamp trước bước HMAC để loại request sai format, nhưng việc **ghi nonce** nên được thực hiện sau khi xác minh chữ ký.

## 7. Tách phần mật mã HMAC thành verifier có thể kiểm thử

Một hàm verifier HMAC nên có hợp đồng rõ: nhận `secretRef`, canonical bytes do server dựng và chữ ký Base64 từ request; trả `true` chỉ khi chữ ký đúng. Mã ví dụ dưới đây chỉ minh họa thao tác mật mã (chưa kết nối secret manager thật):

~~~java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.util.Base64;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

final class HmacSha256 {
    private HmacSha256() {}

    static boolean matches(
            byte[] secret,
            String canonicalRequest,
            String signatureBase64) {

        if (secret == null || secret.length == 0
                || canonicalRequest == null
                || signatureBase64 == null
                || signatureBase64.length() > 128) {
            return false;
        }

        byte[] supplied;
        try {
            supplied = Base64.getDecoder().decode(signatureBase64);
        } catch (IllegalArgumentException ex) {
            return false;
        }

        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(secret, "HmacSHA256"));
            byte[] expected = mac.doFinal(
                canonicalRequest.getBytes(StandardCharsets.UTF_8)
            );
            return supplied.length == expected.length
                && MessageDigest.isEqual(supplied, expected);
        } catch (GeneralSecurityException ex) {
            throw new IllegalStateException(
                "HMAC verifier unavailable", ex);
        }
    }
}
~~~

`MessageDigest.isEqual` được dùng để tránh so sánh từng ký tự rồi dừng tại vị trí khác nhau. Cần xác thực độ dài và format signature trước khi decode để tránh chiếm tài nguyên. HMAC key phải được tạo từ nguồn ngẫu nhiên mật mã và quản lý trong kho bí mật; không đặt secret dạng rõ trong Java source, exception, metrics hoặc log.

Nếu verifier đọc secret dạng `byte[]`, hãy xác định đối tượng nào sở hữu mảng để có thể xóa dữ liệu khỏi bộ nhớ khi phù hợp mà không làm hỏng cache secret dùng chung. Không dùng một secret cho nhiều tenant hoặc nhiều key version chỉ vì muốn giảm chi phí quản lý.

## 8. Custom filter gọi AuthenticationManager

Filter là điểm nối HTTP và Spring Security. Nó phải tạo token chưa xác thực, gọi `AuthenticationManager.authenticate(...)` và chỉ đưa kết quả thành công vào `SecurityContextHolder`.

Mẫu sau minh họa cấu trúc. Lớp `HmacRequestExtractor` chịu trách nhiệm parse, canonicalize và bảo đảm body còn đọc được; không minh họa toàn bộ xử lý Servlet input stream.

~~~java
import java.io.IOException;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.web.AuthenticationEntryPoint;
import org.springframework.web.filter.OncePerRequestFilter;

record ExtractedHmacRequest(
    HmacEvidence evidence,
    HttpServletRequest replayableRequest
) {}

interface HmacRequestExtractor {
    // Phải ném AuthenticationException khi request thiếu/mơ hồ/sai format.
    // replayableRequest giữ nguyên dữ liệu nghiệp vụ cho downstream.
    ExtractedHmacRequest extract(HttpServletRequest request)
        throws AuthenticationException;
}

public final class HmacAuthenticationFilter
        extends OncePerRequestFilter {

    private final AuthenticationManager manager;
    private final HmacRequestExtractor extractor;
    private final AuthenticationEntryPoint entryPoint;

    public HmacAuthenticationFilter(
            AuthenticationManager manager,
            HmacRequestExtractor extractor,
            AuthenticationEntryPoint entryPoint) {
        this.manager = manager;
        this.extractor = extractor;
        this.entryPoint = entryPoint;
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {

        ExtractedHmacRequest parsed;
        Authentication authenticated;

        try {
            parsed = extractor.extract(request);
            var attempt = new HmacAuthenticationToken(parsed.evidence());
            authenticated = manager.authenticate(attempt);
        } catch (AuthenticationException ex) {
            SecurityContextHolder.clearContext();
            entryPoint.commence(request, response, ex);
            return;
        }

        SecurityContext context =
            SecurityContextHolder.createEmptyContext();
        context.setAuthentication(authenticated);
        SecurityContextHolder.setContext(context);

        try {
            chain.doFilter(parsed.replayableRequest(), response);
        } finally {
            SecurityContextHolder.clearContext();
        }
    }
}
~~~

Điểm quan trọng: đây là **filter tự gọi `AuthenticationManager`**. Nếu đặt nó trước `ExceptionTranslationFilter`, ngoại lệ phát sinh ngay trong filter sẽ không tự động được `ExceptionTranslationFilter` ở phía sau bắt; bởi vậy filter đã trực tiếp bắt `AuthenticationException` rồi gọi `AuthenticationEntryPoint`. Các lỗi hạ tầng (registry/vault/replay store không khả dụng) cần được ánh xạ rõ thành từ chối xác thực hoặc response sự cố theo hợp đồng và tuyệt đối **không fail open**.

Nếu dùng `AbstractAuthenticationProcessingFilter` thay vì `OncePerRequestFilter`, framework có cơ chế `attemptAuthentication`, success/failure handlers riêng. Cả hai cách đều hợp lệ; cần nhất quán với filter chain và kiểm thử phản hồi. Không nên vừa tự ghi response vừa để filter khác xử lý lại cùng một lỗi.

**Chú ý SecurityContext:** Spring Security tự quản lý một số bước mở/đóng context qua `SecurityContextHolderFilter`; custom filter cần tạo context mới cho request, đặt kết quả vào đó và tránh để context bị giữ lại trong thread pool. Khi sử dụng async dispatch, cần kiểm tra cách context được truyền và dọn riêng theo cơ chế async của Spring Security. Cấu hình stateless không có nghĩa context được phép tái sử dụng giữa request.

## 9. Cấu hình SecurityFilterChain cho API HMAC stateless

Một cấu hình hướng Spring Security 6, Java 17:

~~~java
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpStatus;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.AuthenticationEntryPoint;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.HttpStatusEntryPoint;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;

@Configuration
class HmacSecurityConfiguration {

    @Bean
    AuthenticationManager hmacAuthenticationManager(
            HmacAuthenticationProvider provider) {
        return new ProviderManager(List.of(provider));
    }

    @Bean
    @Order(1)
    SecurityFilterChain hmacSecurityChain(
            HttpSecurity http,
            AuthenticationManager hmacAuthenticationManager,
            HmacRequestExtractor extractor) throws Exception {

        AuthenticationEntryPoint entryPoint =
            new HttpStatusEntryPoint(HttpStatus.UNAUTHORIZED);

        HmacAuthenticationFilter filter =
            new HmacAuthenticationFilter(
                hmacAuthenticationManager, extractor, entryPoint);

        return http
            .securityMatcher("/api/hmac/**")
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .csrf(csrf -> csrf.disable())
            .exceptionHandling(errors -> errors
                .authenticationEntryPoint(entryPoint))
            .authorizeHttpRequests(authz -> authz
                .anyRequest().authenticated())
            .addFilterBefore(
                filter, UsernamePasswordAuthenticationFilter.class)
            .build();
    }
}
~~~

Các lớp `HmacAuthenticationProvider`, `HmacRequestExtractor` cần được đăng ký thành bean hoặc được cung cấp từ cấu hình ứng dụng. Đây là ví dụ cấu trúc cho endpoint `/api/hmac/**`; ứng dụng có thể cần thêm filter chain cho endpoint khác cùng chính sách `@Order` rõ ràng.

**CSRF:** ví dụ disable CSRF chỉ cho chain dành riêng cho API máy–máy stateless xác thực mỗi request bằng HMAC, không sử dụng cookie/session trình duyệt để xác thực. Nếu có endpoint dựa trên cookie/session, không được mở rộng `csrf.disable()` bừa sang các endpoint đó. Các lớp như TLS, giới hạn request body, log an toàn và quyền API vẫn cần thiết.

**Authorization:** `.anyRequest().authenticated()` mới chứng minh người gọi đã xác thực; chưa kiểm tra quyền cụ thể. Ví dụ `POST /api/hmac/payments` còn cần quyết định `principal, tenant, action=CREATE_PAYMENT, resource` trong một `AuthorizationManager`, policy service hoặc method security. Đừng gán `ROLE_ADMIN` cho mọi HMAC client chỉ để vượt 403.

### Nhiều filter chain và thứ tự áp dụng

Spring Security chọn chain phù hợp theo thứ tự cấu hình. Nếu HMAC chain bị match sai hoặc một chain rộng hơn đứng trước, HMAC filter có thể không chạy. Hãy kiểm thử:

- `/api/hmac/payments` thực sự đi qua HMAC chain.
- `/api/public/health` và các đường khác không bị ép dùng HMAC ngoài ý muốn.
- Endpoint nội bộ không bypass lớp xác thực khi gọi trực tiếp, nếu nó dựa vào gateway để kiểm tra.
- Hệ thống không vô tình đăng ký HMAC filter cả như Servlet filter toàn cục **lẫn** security filter, dẫn đến chạy hai lần và nonce bị coi là replay.

Nếu framework tự động đăng ký một bean `Filter` vào Servlet container, hãy kiểm tra cơ chế đăng ký để tránh filter chạy ngoài `SecurityFilterChain`. Một số triển khai chọn tạo filter trực tiếp trong bean `SecurityFilterChain` như ví dụ để giới hạn phạm vi.

## 10. Phân loại lỗi xác thực và phản hồi HTTP

Provider nên phát sinh `AuthenticationException` phù hợp, nhưng **không công khai nguyên nhân nhạy cảm**. Mã lỗi nội bộ có thể dùng để audit và cảnh báo.

| Tình huống | Xử lý nội bộ | Phản hồi bên ngoài |
| --- | --- | --- |
| Thiếu `X-Key-Id`, header trùng | Request extractor từ chối | 401 hoặc mã lỗi hợp đồng được chuẩn hóa |
| Key ID không tồn tại | `BadCredentialsException` | 401, không xác nhận key có tồn tại |
| Chữ ký HMAC sai | `BadCredentialsException` | 401 chung |
| Credential bị REVOKED/RETIRED | Từ chối trạng thái | 401 chung |
| Client bị DISABLED | `DisabledException` hoặc mã nội bộ | 401 chung |
| Credential hết `expiresAt` | `CredentialsExpiredException` | 401 chung |
| Timestamp ngoài cửa sổ | Từ chối request không còn mới | 401 chung |
| Nonce đã dùng | Từ chối replay | 401 chung |
| HMAC đúng nhưng thiếu quyền API/tenant | Authorization từ chối | Thường 403, hoặc 404 theo chính sách che tài nguyên |
| Registry/secret manager/replay store lỗi | Không chấp nhận thiếu kiểm tra; cảnh báo | 401/503 theo chính sách đã thiết kế, không rò chi tiết |

`AuthenticationEntryPoint` tạo phản hồi khi xác thực không đạt. `AccessDeniedHandler` tham gia xử lý thiếu quyền với principal đã xác thực. Cần cấu hình nhất quán để phân biệt **authentication** và **authorization** trong log, nhưng người gọi không dùng được các phản hồi để dò secret, key version hoặc tình trạng client.

Trong code xử lý exception, tránh bắt `Exception` rồi tiếp tục chain hoặc gắn một principal giả nhằm “giữ availability”. Nếu phụ trợ xác thực không thể chứng minh credential hợp lệ, hệ thống cần **fail closed**.

### Timing và thông tin log

Một key ID không tồn tại có thể cần một số xử lý giúp giảm khả năng bị dò qua chênh lệch thời gian; không hứa toàn bộ database/network pipeline “constant-time”. So sánh MAC phải dùng phép so sánh an toàn về timing trên bytes đúng độ dài. Rate limiting, hạn chế chi phí xử lý request sai và monitoring là những lớp bảo vệ bổ sung.

Không log chữ ký, secret, canonical request chứa body nhạy cảm hoặc header nguyên trạng. Có thể ghi key ID đã che, principal sau khi xác thực, correlation ID, mã lỗi hữu hạn và ID verifier; lưu quyền đọc/retention thích hợp.

## 11. Kiểm thử AuthenticationManager và filter HMAC

Có ba lớp kiểm thử bổ sung cho nhau:

- **Unit:** provider nhận token HMAC, tra credential, quyết định trạng thái/expiry, gọi verifier và replay guard, trả principal/authorities tin cậy.
- **Contract/crypto:** signer độc lập và verifier tạo cùng canonical bytes và chữ ký; test thay đổi tenant, URI, query, header, body và key version.
- **Integration/E2E:** `MockMvc` hoặc môi trường HTTP thật chạy qua `SecurityFilterChain`, proxy/gateway, secret manager/replay store và authorization để kiểm tra phản hồi và side effect.

### Ma trận test cho manager/provider

| Test ID | Điều kiện | Kết quả mong đợi |
| --- | --- | --- |
| AM-01 | Token đúng kiểu, key ACTIVE, HMAC đúng, nonce mới | Provider trả Authentication đã xác thực, principal đúng |
| AM-02 | Token không phải HMAC token | `supports()` false; manager không giao cho HMAC provider |
| AM-03 | Key ID không tồn tại | Thất bại xác thực |
| AM-04 | HMAC sai dù key ACTIVE | Thất bại xác thực; không ghi nonce |
| AM-05 | Credential REVOKED | Không chấp nhận dù chữ ký đúng |
| AM-06 | Client/tenant DISABLED | Từ chối bất kể key còn ACTIVE |
| AM-07 | `serverNow == expiresAt` | Từ chối vì thời gian hiệu lực dạng nửa mở |
| AM-08 | Timestamp ngoài cửa sổ ±5 phút | Từ chối |
| AM-09 | Timestamp hợp lệ nhưng nonce trùng | Từ chối replay |
| AM-10 | Cùng nonce gửi đồng thời qua hai node | Chỉ một nonce được ghi thành công |
| AM-11 | Key K3/K4 cùng ACTIVE khi rotation | Mỗi request được xác minh chỉ bằng version khai báo |
| AM-12 | Client khai K4 nhưng ký bằng secret K3 | HMAC sai, không fallback |
| AM-13 | Claimed client không khớp credential owner | Từ chối |
| AM-14 | HMAC đúng nhưng thiếu grant tenant | Authentication có thể thành công; authorization phải từ chối |
| AM-15 | Registry/vault/replay store mất kết nối | Fail closed, không xử lý nghiệp vụ |
| AM-16 | Provider thành công | Authentication không mang shared secret làm credentials |

Ví dụ một unit test khung:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.core.Authentication;

class HmacAuthenticationManagerTest {

    private final AuthenticationManager manager = buildTestManager();

    @Test
    void validHmacReturnsAuthenticatedPrincipal() {
        HmacEvidence proof = validSignedEvidence(
            "partner-a-k4", "partner-a", "tenant-a", "nonce-test-01");

        Authentication result =
            manager.authenticate(new HmacAuthenticationToken(proof));

        assertTrue(result.isAuthenticated());
        assertInstanceOf(HmacPrincipal.class, result.getPrincipal());
        assertNull(result.getCredentials());
    }

    @Test
    void wrongSignatureIsRejected() {
        HmacEvidence proof = signedEvidenceWithWrongMac();

        assertThrows(
            BadCredentialsException.class,
            () -> manager.authenticate(new HmacAuthenticationToken(proof))
        );
    }

    // buildTestManager(), validSignedEvidence() và
    // signedEvidenceWithWrongMac() là fixture của dự án test.
}
~~~

Đoạn này là **khung kiểm thử**, cần hiện thực fixture bằng secret test và `Clock` cố định. Khi xác minh tích hợp, đừng mock `AuthenticationManager` rồi kết luận toàn bộ HMAC đã đúng; phải có ít nhất một tập test chạy **provider, verifier mật mã và replay store thật** với test vector độc lập.

### Kiểm thử filter và SecurityContext

Một `MockMvc` test nên kiểm tra:

1. Không có HMAC headers ở đường bắt buộc → 401, controller không chạy.
2. HMAC đúng → controller thấy `SecurityContextHolder.getContext().getAuthentication()` đã xác thực với principal từ registry.
3. HMAC sai → 401, không để lại context xác thực và không chạy controller.
4. Chữ ký đúng nhưng principal thiếu quyền → 403 hoặc kết quả theo chính sách tài nguyên; không nhầm thành lỗi chữ ký.
5. Body JSON vẫn đọc được tại controller sau khi filter xác minh chữ ký trên **body bytes gốc**.
6. Hai request liên tiếp trên thread dùng lại không làm rò principal/context của request trước.
7. Một filter không chạy hai lần khiến nonce hợp lệ bị đánh dấu replay.
8. Cấu hình nhiều chain áp dụng đúng đường HMAC, không chặn nhầm endpoint khác.

## 12. Proxy/gateway, nhiều instance và những lỗi triển khai hay gặp

### 12.1. Gateway rewrite URI nhưng verifier dùng URI khác signer

Client ký `/api/hmac/payments?currency=VND`; proxy đổi path hoặc query; verifier dựng canonical bytes khác. Kết quả `SIGNATURE_MISMATCH`. Phải thống nhất điểm ký và điểm xác minh, các header forwarded được tin cậy, cách chuẩn hóa URI và kiểm thử xuyên proxy. Không giải quyết bằng cách bỏ URI ra khỏi hợp đồng ký mà không đánh giá tác động.

### 12.2. Đọc body trong filter làm controller nhận body rỗng

Một filter tính SHA-256 bằng `request.getInputStream().readAllBytes()`, sau đó controller dùng `@RequestBody` nhận stream đã hết. Cần wrapper/buffer có giới hạn và khả năng đọc lại, hoặc kiến trúc tạo digest tại một điểm dùng chung bytes. Test E2E phải chứng minh body controller nhận đúng nội dung đã ký.

### 12.3. Manager thành công nhưng filter quên set SecurityContext

`authenticate()` trả một token xác thực nhưng `SecurityContextHolder` vẫn rỗng; authorization có thể từ chối hoặc dùng context cũ. Filter phải tạo `SecurityContext` mới và gắn kết quả trước khi cho request đi tiếp.

### 12.4. Provider tự đặt authority dựa trên header

Kẻ tấn công gửi `X-Roles: ADMIN` rồi ký HMAC bằng secret hợp lệ của client thường. Chữ ký chỉ chứng minh người gửi sở hữu secret; quyền thực tế phải đến từ chính sách server. Không lấy role, tenant hoặc resource permission chỉ từ header do client kiểm soát.

### 12.5. Fallback khi key rotation

Client gửi key ID K4 nhưng provider thử K3 nếu K4 không khớp. Điều này che lỗi cấu hình, làm thu hồi khó kiểm soát và tạo đường chấp nhận key ngoài hợp đồng. Chọn **một key đúng theo ID**; mỗi version có secret riêng và trạng thái riêng.

### 12.6. Nonce store riêng mỗi instance

Request có HMAC hợp lệ được gửi lần đầu tới instance A rồi phát lại tới B; mỗi node chỉ kiểm tra `HashSet` cục bộ. B chấp nhận replay. Sử dụng store nguyên tử chia sẻ, TTL bao phủ cửa sổ và test đồng thời/xuyên node.

### 12.7. Chỉ kiểm tra trạng thái trong cache lâu hạn

Key đã REVOKED ở nguồn nhưng gateway giữ ACTIVE 60 giây. Không được gọi đó là “thu hồi tức thời”. Cần thiết kế freshness, invalidation và chính sách fail closed khi không xác minh được trạng thái mới. Với yêu cầu chặn mọi request bắt đầu sau commit thu hồi, phải có điểm kiểm tra có tính nhất quán đủ mạnh hoặc từ chối khi mất kết nối.

### 12.8. Multi-tenant: xác thực xong chọn tenant từ header

Provider trả principal owner tenant A, downstream lại dùng `X-Tenant-Id: tenant-b` để truy vấn. Đây là lỗi confused deputy. Tenant đích cần nằm trong canonical request được ký **và** phải có grant phù hợp, rồi downstream chỉ dùng effective tenant context đã qua authorization. HMAC đúng không thay thế kiểm tra tenant.

## 13. Theo dõi vận hành và giám sát AuthenticationManager

Một pipeline rõ ràng cần quan sát được các nguyên nhân thất bại mà không tiết lộ secret.

| Metric/audit | Mục đích |
| --- | --- |
| Tỷ lệ authenticate thành công/thất bại theo service/region | Đo sức khỏe đường xác thực |
| Phân nhóm lỗi `BAD_SIGNATURE`, `REPLAY`, `KEY_REVOKED`, `EXPIRED` | Điều tra lỗi client, xâm nhập, rotation |
| Latency tra credential và secret manager | Phát hiện chậm do phụ trợ xác thực |
| Latency nonce store và tỷ lệ atomic-insert thất bại | Phát hiện replay hoặc sự cố phân tán |
| Số request dùng key version cũ khi rotation | Biết client đã chuyển hay chưa |
| Độ trễ cập nhật trạng thái REVOKED/DISABLED ở từng gateway | Kiểm chứng thời gian thu hồi thực |
| Số lần authorization denied sau HMAC thành công | Tách vấn đề quyền khỏi vấn đề chữ ký |
| Sự cố canonicalization theo route/proxy version | Theo dõi khác biệt cấu hình gateway |

Không đặt raw key ID, principal hoặc tenant ID cardinality cao làm nhãn metric vô hạn; dùng log bảo mật với correlation ID và chính sách truy cập phù hợp cho điều tra từng request. Không ghi shared secret, HMAC signature, request body nhạy cảm hoặc canonical request đầy đủ.

Cần dashboard phân biệt **lỗi xác thực** (`AuthenticationException`) với **từ chối quyền** (`AccessDeniedException`) để đội vận hành không nhầm vụ việc bị deny vì tenant với lỗi key rotation.

## 14. Bài tập thực hành: tìm lỗi trong luồng AuthenticationManager

Một ứng dụng Spring Security có filter HMAC chạy trước `UsernamePasswordAuthenticationFilter`. Đối tác A có K3 đã REVOKED, K4 ACTIVE. Gateway X cache K3=ACTIVE trong 60 giây. Filter đọc body để ký rồi gọi `authenticationManager.authenticate` với token chứa `X-Key-Id: K3`. Provider thử K3, nếu chữ ký không khớp thì fallback K4. Sau đó filter gắn `principal=partner-a` vào `SecurityContextHolder`; controller dùng `X-Tenant-Id` để chọn database. Nonce chỉ được lưu trong bộ nhớ của từng instance.

Hãy xác định ít nhất sáu lỗi thiết kế và nêu thay đổi cần thiết:

1. Khi registry đã REVOKED K3, điều kiện nào bảo đảm cache ở gateway X không tiếp tục chấp nhận K3?
2. Provider có được thử K4 khi request khai K3 không? Vì sao?
3. Nếu filter đã đọc input stream, làm thế nào giữ body đúng cho controller và canonical request?
4. Sau khi xác thực `partner-a`, nguồn tenant hiệu lực phải được quyết định ở đâu?
5. Hai request giống timestamp/nonce gửi tới hai instance phải có kết quả thế nào?
6. Nếu `authenticationManager.authenticate` ném `AuthenticationException` trong filter đặt trước `ExceptionTranslationFilter`, ai tạo response?
7. Nếu chữ ký HMAC đúng nhưng thiếu quyền tenant, HTTP status và log nội bộ nên phản ánh loại lỗi nào?

**Gợi ý:** thu hồi phải được thực thi bằng trạng thái đủ mới/fail closed; lookup đúng key ID và không fallback; canonical body bytes và body downstream cần wrapper có khả năng đọc lại; effective tenant phải được xác thực, phân quyền và truyền qua context đáng tin; nonce store phải atomic và dùng chung; filter tự bắt lỗi xác thực hoặc dùng bộ lọc có failure handler phù hợp; authorization denied phải được phân biệt với authentication failed.

## 15. Checklist hoàn thành tích hợp HMAC với AuthenticationManager

Trước khi coi một triển khai Spring Security đã sẵn sàng, xác nhận:

- Token HMAC đầu vào là kiểu chưa được xác thực, không chứa authority do client tự khai.
- `AuthenticationManager` được nối với đúng `AuthenticationProvider` hỗ trợ HMAC, không có fallback sang secret khác.
- Provider dùng đúng credential, trạng thái client/key/tenant đủ mới, khoảng hiệu lực theo đồng hồ server và secret bảo vệ trong secret manager.
- Canonical request có hợp đồng ký byte-for-byte, ràng buộc method/URI/header/body/tenant/key ID cần thiết; proxy/gateway dùng thống nhất.
- HMAC được tính bằng thuật toán được server cho phép, chữ ký được so sánh an toàn về timing và input được giới hạn.
- Timestamp/nonce được kiểm tra chống replay, nonce ghi nguyên tử toàn cụm sau khi HMAC hợp lệ, TTL đủ dài.
- Filter gắn `Authentication` thành công vào `SecurityContextHolder`, dọn context và xử lý `AuthenticationException` đúng điểm.
- API HMAC stateless có `SecurityFilterChain` chính xác, không vô tình áp đặt chính sách CSRF/session lên route khác.
- Authorization xét principal, effective tenant, action và resource; HMAC hợp lệ không tự tạo quyền API.
- Body vẫn đọc được sau khi verify; filter không chạy hai lần; async request không rò SecurityContext.
- Key rotation, revoke, stale cache, registry/vault/replay store failure và đường bypass gateway đều đã được kiểm thử.
- Metrics/audit đủ nhận biết lỗi nhưng không làm lộ secret, chữ ký hoặc dữ liệu nghiệp vụ nhạy cảm.

**AuthenticationManager là điểm điều phối quyết định xác thực, không phải nơi chứa tất cả xử lý HTTP hay mọi quy tắc phân quyền.** Với HMAC request authentication, thiết kế đúng là: filter chuẩn bị bằng chứng và canonical request, `AuthenticationManager` chọn provider HMAC, provider xác minh credential/HMAC/replay, filter lưu principal đã xác thực vào SecurityContext, rồi Spring Security và lớp nghiệp vụ áp dụng authorization với tenant và tài nguyên cụ thể. Khi các ranh giới này rõ ràng, việc kiểm thử và xử lý sự cố qua gateway, nhiều client, key rotation và hệ thống phân tán trở nên có kiểm soát.
