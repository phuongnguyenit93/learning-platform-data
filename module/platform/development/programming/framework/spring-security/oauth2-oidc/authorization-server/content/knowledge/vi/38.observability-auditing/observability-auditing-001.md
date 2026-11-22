# Ghi log sự kiện đăng nhập, consent, phát hành và thu hồi token

Trong một OAuth 2.0 / OpenID Connect Authorization Server, việc ghi lại ai đã đăng nhập, client nào xin quyền, người dùng đã chấp thuận những scope nào và token nào đã được cấp hoặc thu hồi giúp đội vận hành điều tra sự cố và chứng minh lịch sử truy cập. Những dữ liệu này cũng hỗ trợ phát hiện hành vi bất thường, chẳng hạn một client đột nhiên xin thêm scope nhạy cảm hoặc một tài khoản liên tục thất bại khi đăng nhập.

Với Spring Security và Spring Authorization Server, các sự kiện nằm ở nhiều điểm trong vòng đời xác thực và ủy quyền. Spring Security có cơ chế phát sự kiện xác thực; Spring Authorization Server lưu consent và trạng thái authorization thông qua các service chuyên biệt. Vì vậy, cần đặt điểm ghi nhận tại đúng ranh giới nghiệp vụ và định nghĩa rõ ý nghĩa của từng sự kiện.

## 1. Phân biệt log vận hành và nhật ký kiểm toán

Log vận hành giúp trả lời câu hỏi hệ thống đang hoạt động thế nào: request mất bao lâu, endpoint nào trả lỗi, database có chậm hay không. Nhật ký kiểm toán (audit log) trả lời câu hỏi về hành động bảo mật: ai thực hiện, hành động nào xảy ra, với client nào, vào thời điểm nào và kết quả ra sao.

Hai loại dữ liệu có thể cùng được xuất dưới dạng log có cấu trúc, nhưng yêu cầu lưu trữ khác nhau:

| Tiêu chí | Log vận hành | Nhật ký kiểm toán |
|---|---|---|
| Mục đích | Chẩn đoán lỗi và theo dõi hiệu năng | Điều tra và chứng minh hoạt động bảo mật |
| Nội dung | Endpoint, thời gian xử lý, mã lỗi, trace ID | Chủ thể, client, hành động, kết quả, scope, mã lý do |
| Tính toàn vẹn | Có thể xoay vòng và lấy mẫu theo chính sách vận hành | Cần kiểm soát sửa/xóa, truy cập và thời hạn lưu |
| Mức chi tiết | Phục vụ kỹ thuật | Đủ để tái dựng sự kiện nhưng không làm lộ bí mật |

Không ghi mật khẩu, client secret, authorization code, access token, refresh token, ID Token hoặc PKCE verifier vào bất kỳ loại log nào. Không serialize toàn bộ đối tượng **Authentication**, request, response hay **OAuth2Authorization** để ghi log: các đối tượng này có thể chứa credential hoặc dữ liệu cá nhân.

## 2. Xác định điểm ghi nhận trong vòng đời OAuth2/OIDC

Một Authorization Server thường cần theo dõi ít nhất các nhóm sự kiện sau:

| Sự kiện | Điểm ghi nhận phù hợp | Dữ liệu nghiệp vụ chính |
|---|---|---|
| Đăng nhập thành công/thất bại | Sự kiện xác thực của Spring Security | Chủ thể, phương thức xác thực, kết quả, mã lý do |
| Xác thực OAuth2 client | Điểm xác thực client | Client ID, phương thức xác thực client, kết quả |
| Consent được cấp/thay đổi/gỡ bỏ | **OAuth2AuthorizationConsentService** | Principal, client ID, tập authority/scope thay đổi |
| Token được cấp | Thay đổi trạng thái được lưu qua **OAuth2AuthorizationService** | Principal, client ID, grant type, loại token, scope |
| Token bị thu hồi | Chuyển trạng thái token sang invalidated trong authorization | Token type, dấu vân tay token, tác nhân và lý do |
| Authorization bị xóa | **OAuth2AuthorizationService.remove** | Authorization ID nội bộ, client ID, lý do xóa |

Spring không cung cấp một sự kiện audit duy nhất bao phủ toàn bộ các hành động trên. Cần kết hợp sự kiện xác thực của Spring Security với hai abstraction lưu trữ của Spring Authorization Server.

Cũng cần tách đăng nhập người dùng khỏi xác thực client. Khi client gửi **client_secret_basic**, **private_key_jwt** hoặc phương thức xác thực client khác, đó là một lần xác thực của OAuth2 client, không phải người dùng đăng nhập. Nếu gộp hai loại này thành **LOGIN_SUCCEEDED**, báo cáo sẽ gây hiểu nhầm. Hãy phân loại chúng thành các event type riêng.

## 3. Thiết kế cấu trúc audit event

Nên chuẩn hóa các sự kiện thành một cấu trúc chung để có thể ghi vào bảng audit, hệ thống log tập trung hoặc hàng đợi sự kiện. Một bản ghi có thể gồm các trường sau:

| Trường | Ý nghĩa |
|---|---|
| **event_id** | Mã duy nhất của sự kiện |
| **event_type** | Ví dụ **LOGIN_FAILED**, **CONSENT_GRANTED**, **TOKEN_ISSUED**, **TOKEN_REVOKED** |
| **occurred_at** | Thời điểm UTC phát sinh sự kiện |
| **outcome** | **SUCCESS**, **FAILURE** hoặc **REJECTED** |
| **subject_ref** | Định danh người dùng đã được chuẩn hóa hoặc giả danh |
| **client_id** | Client OAuth2 liên quan |
| **grant_type** | Grant type, nếu sự kiện liên quan đến cấp token |
| **scopes** | Danh sách scope được cấp hoặc thay đổi, theo chính sách dữ liệu |
| **token_type** | **access_token**, **refresh_token** hoặc **id_token** |
| **token_fingerprint** | Dấu vân tay một chiều của token, không phải giá trị token |
| **reason_code** | Mã lý do đã chuẩn hóa, không phải thông báo exception tùy ý |
| **correlation_id** / **trace_id** | Liên kết sự kiện với request và trace |
| **source_ip** / **user_agent** | Thông tin nguồn nếu chính sách cho phép thu thập |

Ví dụ một sự kiện cấp access token:

~~~json
{
  "event_id": "01JQ8X5K7M2P4R6T9V0W",
  "event_type": "TOKEN_ISSUED",
  "occurred_at": "2026-11-16T14:20:31Z",
  "outcome": "SUCCESS",
  "subject_ref": "user-7f31",
  "client_id": "web-portal",
  "grant_type": "authorization_code",
  "token_type": "access_token",
  "scopes": ["openid", "profile"],
  "token_fingerprint": "hmac-sha256:8a4f...",
  "correlation_id": "req-9c2d"
}
~~~

**token_fingerprint** có thể được tạo bằng HMAC-SHA-256 với khóa bí mật dành riêng cho mục đích kiểm toán. Cách này cho phép nhận biết hai bản ghi có liên quan đến cùng một token mà không lưu token gốc. Không dùng fingerprint làm nhãn metric vì số lượng giá trị có thể rất lớn.

Chỉ ghi những trường cần thiết. **subject_ref** có thể là mã nội bộ hoặc giá trị giả danh thay cho email và tên thật. Nếu cần ghi scope, chỉ ghi tên scope đã được chuẩn hóa và được chính sách cho phép. Không ghi toàn bộ claim của ID Token hoặc access token.

## 4. Ghi nhận đăng nhập bằng sự kiện Spring Security

Spring Security có **AuthenticationEventPublisher** để phát các sự kiện như **AuthenticationSuccessEvent** và các lớp con của **AbstractAuthenticationFailureEvent**. Có thể lắng nghe những sự kiện này bằng **@EventListener**:

~~~java
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.LockedException;
import org.springframework.security.authentication.event.AbstractAuthenticationFailureEvent;
import org.springframework.security.authentication.event.AuthenticationSuccessEvent;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.UserDetails;

@Component
public class AuthenticationAuditListener {

    private final AuditRecorder auditRecorder;

    public AuthenticationAuditListener(AuditRecorder auditRecorder) {
        this.auditRecorder = auditRecorder;
    }

    @EventListener
    public void onSuccess(AuthenticationSuccessEvent event) {
        Authentication authentication = event.getAuthentication();

        // Chỉ ghi sự kiện đăng nhập người dùng theo quy tắc của ứng dụng.
        if (!isInteractiveUserLogin(authentication)) {
            return;
        }

        auditRecorder.loginSucceeded(safeSubject(authentication));
    }

    @EventListener
    public void onFailure(AbstractAuthenticationFailureEvent event) {
        Authentication authentication = event.getAuthentication();

        if (!isInteractiveUserLogin(authentication)) {
            return;
        }

        auditRecorder.loginFailed(
                safeSubject(authentication),
                safeReasonCode(event.getException())
        );
    }

    private boolean isInteractiveUserLogin(Authentication authentication) {
        // Điều chỉnh nếu ứng dụng dùng kiểu principal tùy chỉnh.
        return authentication != null
                && authentication.getPrincipal() instanceof UserDetails;
    }

    private String safeSubject(Authentication authentication) {
        // subjectReference là hàm ứng dụng để giả danh/chuẩn hóa định danh.
        return subjectReference(authentication.getName());
    }

    private String safeReasonCode(Exception exception) {
        if (exception instanceof BadCredentialsException) {
            return "BAD_CREDENTIALS";
        }
        if (exception instanceof LockedException) {
            return "ACCOUNT_LOCKED";
        }
        return "AUTHENTICATION_PROVIDER_ERROR";
    }
}
~~~

Đoạn mã trên minh họa vị trí tích hợp. **AuditRecorder** và **subjectReference** là thành phần của ứng dụng, cần triển khai theo cơ chế xác thực thực tế. Ví dụ dùng **UserDetails** để nhận diện principal người dùng; nếu ứng dụng dùng kiểu principal tùy chỉnh, hãy thay điều kiện này bằng quy tắc tương ứng. Một **AuthenticationSuccessEvent** có thể phát sinh khi xác thực client hoặc một loại principal khác; vì vậy không nên mặc định mọi sự kiện đều là đăng nhập người dùng.

Đảm bảo **AuthenticationManager**/**ProviderManager** đang sử dụng **AuthenticationEventPublisher**. Cấu hình Spring Boot thường cung cấp cơ chế này khi dùng cấu hình tự động; nếu tự tạo **ProviderManager**, hãy kiểm tra và cấu hình publisher tương ứng. Với cơ chế xác thực tùy chỉnh, xác minh rằng thành phần đó thực sự phát sự kiện hoặc bổ sung điểm ghi nhận tại nơi xác thực hoàn tất.

Đối với đăng nhập thất bại, chỉ ghi mã lý do đã chuẩn hóa như **BAD_CREDENTIALS**, **ACCOUNT_LOCKED** hoặc **AUTHENTICATION_PROVIDER_ERROR**. Không ghi mật khẩu người dùng, credential của request hay toàn bộ nội dung exception vì thông báo có thể chứa dữ liệu nhạy cảm.

## 5. Ghi nhận consent qua OAuth2AuthorizationConsentService

Spring Authorization Server dùng **OAuth2AuthorizationConsentService** để đọc, lưu và gỡ bỏ consent của một principal đối với một registered client. Đây là ranh giới phù hợp để kiểm toán thay đổi quyền đã chấp thuận.

Có thể bọc implementation hiện tại bằng một decorator. Ví dụ phần xử lý khi lưu consent:

~~~java
public void save(OAuth2AuthorizationConsent consent) {
    OAuth2AuthorizationConsent previous = delegate.findById(
            consent.getRegisteredClientId(),
            consent.getPrincipalName()
    );

    delegate.save(consent);

    if (!sameAuthorities(previous, consent)) {
        if (previous == null) {
            auditRecorder.consentGranted(consent);
        } else {
            auditRecorder.consentUpdated(previous, consent);
        }
    }
}
~~~

Khi gỡ consent, ghi nhận sau khi thao tác lưu trữ thành công:

~~~java
public void remove(OAuth2AuthorizationConsent consent) {
    delegate.remove(consent);
    auditRecorder.consentRemoved(consent);
}
~~~

Decorator hoàn chỉnh cần triển khai và ủy quyền cả ba phương thức của **OAuth2AuthorizationConsentService**: **findById**, **save** và **remove**. **sameAuthorities** là hàm của ứng dụng, so sánh tập authority trước và sau khi lưu. Chỉ ghi **CONSENT_UPDATED** khi tập quyền thực sự thay đổi để tránh tạo nhiều bản ghi trùng khi cùng một consent được lưu lại.

Khi ghi audit, lấy **registeredClientId**, **principalName** và các authority cần thiết từ consent. Có thể chuẩn hóa authority thành tên scope theo quy ước của ứng dụng. Không ghi nội dung màn hình consent, toàn bộ request hay dữ liệu cá nhân không cần thiết.

**remove** cho biết consent đã bị gỡ khỏi kho lưu trữ, nhưng bản thân phương thức không nhất thiết cho biết ai yêu cầu hoặc vì lý do nào. Nếu cần phân biệt người dùng chủ động thu hồi, quản trị viên thu hồi hay quy trình hệ thống dọn dữ liệu, hãy truyền ngữ cảnh tác nhân và reason code từ service nghiệp vụ gọi thao tác đó. Không suy đoán tác nhân chỉ từ việc phương thức **remove** được gọi.

## 6. Ghi nhận phát hành và thu hồi token qua OAuth2AuthorizationService

**OAuth2AuthorizationService** quản lý trạng thái authorization đã được cấp. Các phương thức quan trọng gồm **findById**, **findByToken**, **save** và **remove**. Một decorator quanh service đang được Authorization Server sử dụng có thể so sánh trạng thái trước và sau khi lưu để phát hiện token mới hoặc token chuyển sang trạng thái bị vô hiệu hóa.

Ví dụ khung decorator:

~~~java
public final class AuditingAuthorizationService
        implements OAuth2AuthorizationService {

    private final OAuth2AuthorizationService delegate;
    private final AuditRecorder auditRecorder;

    public AuditingAuthorizationService(
            OAuth2AuthorizationService delegate,
            AuditRecorder auditRecorder) {
        this.delegate = delegate;
        this.auditRecorder = auditRecorder;
    }

    @Override
    public OAuth2Authorization findById(String id) {
        return delegate.findById(id);
    }

    @Override
    public OAuth2Authorization findByToken(
            String token,
            OAuth2TokenType tokenType) {
        return delegate.findByToken(token, tokenType);
    }

    @Override
    public void save(OAuth2Authorization authorization) {
        OAuth2Authorization previous =
                delegate.findById(authorization.getId());

        delegate.save(authorization);

        // So sánh token và metadata trước/sau khi lưu.
        // Ghi TOKEN_ISSUED hoặc TOKEN_REVOKED khi có chuyển trạng thái phù hợp.
        auditRecorder.recordAuthorizationTransitions(
                previous,
                authorization
        );
    }

    @Override
    public void remove(OAuth2Authorization authorization) {
        delegate.remove(authorization);
        auditRecorder.authorizationRemoved(authorization);
    }
}
~~~

**recordAuthorizationTransitions** là logic audit của ứng dụng. Khi triển khai, hãy xem các token trong **OAuth2Authorization** gồm access token, refresh token và ID Token; so sánh sự hiện diện, fingerprint và metadata trước/sau khi lưu. Chỉ ghi **TOKEN_ISSUED** khi token mới được tạo hoặc token mới thay thế token cũ theo quy tắc đã định nghĩa. Điều này cũng giúp nhận diện lần cấp access token mới trong luồng refresh token.

Không nên ghi **TOKEN_ISSUED** chỉ vì **OAuth2TokenGenerator** được gọi. Generator cho biết token đã được tạo trong quá trình xử lý, nhưng việc lưu authorization có thể thất bại sau đó. Điểm ghi nhận sau khi **OAuth2AuthorizationService.save** thành công phản ánh token đã được lưu vào trạng thái authorization của server. Nếu cần chứng minh response đã được gửi tới client, đó là một sự kiện khác ở tầng HTTP; không nên diễn giải việc lưu thành công là bằng chứng client chắc chắn đã nhận response.

Để phát hiện thu hồi, kiểm tra chuyển trạng thái metadata của token sang invalidated. Không dùng riêng điều kiện “token không còn active” để kết luận đã thu hồi: token hết hạn cũng không active. Cần phân biệt **isInvalidated()** với **isExpired()** hoặc các trạng thái khác. Khi token được đánh dấu invalidated, ghi **TOKEN_REVOKED** cùng token type, client ID, subject, fingerprint và reason code nếu biết.

Phương thức **remove** có thể được dùng để xóa toàn bộ authorization. Hãy ghi **AUTHORIZATION_REMOVED** sau khi thao tác xóa thành công và phân biệt sự kiện này với việc thu hồi riêng access token hoặc refresh token. Nếu thao tác xóa được kích hoạt bởi tác vụ dọn dữ liệu, ghi tác nhân hệ thống và reason code tương ứng.

Decorator phải bọc đúng instance **OAuth2AuthorizationService** được cấu hình cho Spring Authorization Server. Nếu ứng dụng dùng JDBC hoặc implementation tùy chỉnh, giữ nguyên implementation đó làm delegate để không làm thay đổi hành vi lưu trữ. Tránh tạo hai service độc lập khiến luồng xử lý ghi vào một nơi còn luồng audit lại đọc từ nơi khác.

## 7. Đảm bảo ngữ nghĩa và tính toàn vẹn của audit

Cần thống nhất thời điểm và ý nghĩa của mỗi event type. Ví dụ:

- **LOGIN_SUCCEEDED**: Spring Security đã xác thực thành công principal thuộc nhóm đăng nhập người dùng.
- **CONSENT_GRANTED**: consent mới đã được lưu thành công.
- **CONSENT_UPDATED**: tập quyền trong consent đã thay đổi và được lưu.
- **TOKEN_ISSUED**: token mới đã được lưu trong authorization.
- **TOKEN_REVOKED**: metadata của token đã chuyển sang trạng thái invalidated.
- **AUTHORIZATION_REMOVED**: authorization đã được xóa khỏi kho lưu trữ.

Một request thu hồi token có thể không tìm thấy token, hoặc token đã bị thu hồi trước đó. Giao thức có thể trả response thành công theo quy tắc của endpoint, nhưng audit không nên ghi rằng trạng thái token vừa thay đổi nếu không có chuyển trạng thái thực tế. Nếu cần theo dõi cả yêu cầu thu hồi, hãy ghi một event riêng như **TOKEN_REVOCATION_REQUESTED** và ghi kết quả xử lý độc lập.

Nếu audit được lưu trong database, có thể dùng bảng append-only với quyền ứng dụng chỉ được insert, hoặc transactional outbox để ghi sự kiện audit trong cùng transaction với thay đổi authorization/consent. Cách này giảm nguy cơ dữ liệu nghiệp vụ đã commit nhưng sự kiện audit bị mất. Nếu audit được gửi tới hệ thống bên ngoài, dùng outbox hoặc cơ chế retry có kiểm soát; tránh gọi một dịch vụ mạng chậm trực tiếp trong luồng cấp token.

Không được âm thầm bỏ qua lỗi ghi audit đối với các sự kiện bắt buộc. Chính sách khi audit store gặp sự cố phải được xác định rõ: từ chối thao tác nhạy cảm để bảo toàn yêu cầu kiểm toán, hoặc lưu vào hàng đợi bền vững để gửi lại. Việc chọn cách nào phụ thuộc yêu cầu sẵn sàng và tuân thủ của hệ thống. Cần có cảnh báo khi hàng đợi audit bị tồn đọng hoặc ghi thất bại.

Bảo vệ kho audit bằng phân quyền đọc, mã hóa khi truyền và khi lưu, thời hạn lưu rõ ràng và theo dõi mọi truy cập vào dữ liệu audit. Với yêu cầu chống sửa đổi, có thể dùng kho append-only, quyền tách biệt giữa ứng dụng và người quản trị, hoặc cơ chế kiểm tra toàn vẹn theo lô. Không cấp quyền xóa/sửa bản ghi audit thông thường cho tài khoản runtime của Authorization Server.

## 8. Kết hợp log, trace và metric

Dùng log có cấu trúc JSON để hệ thống tập trung có thể lọc theo **event_type**, **client_id**, **subject_ref** và **correlation_id**. Đặt timestamp theo UTC và thống nhất định dạng giữa các service. Gắn correlation ID hoặc trace ID xuyên suốt login, authorization request, token request và thao tác revoke để điều tra một luồng nhiều bước.

Có thể tạo metric đếm số lần đăng nhập thành công/thất bại, consent được cấp và token được phát hành/thu hồi. Metric chỉ nên dùng nhãn có số lượng giá trị giới hạn, ví dụ **event_type**, **outcome**, **grant_type** hoặc nhóm client đã chuẩn hóa. Không đưa username, IP, token fingerprint hay correlation ID vào nhãn metric vì sẽ tạo cardinality rất lớn và làm tăng chi phí lưu trữ.

Khi lấy địa chỉ IP từ header proxy, chỉ tin các header do reverse proxy đáng tin cậy ghi và cấu hình đúng danh sách proxy. Không mặc định mọi giá trị **X-Forwarded-For** từ client đều chính xác. Với user agent và địa chỉ IP, chỉ thu thập khi có mục đích rõ ràng, giới hạn quyền truy cập và thời gian lưu theo chính sách dữ liệu.

Cần cấu hình che dữ liệu nhạy cảm ở tầng HTTP và hệ thống log. Query string của authorization endpoint có thể chứa authorization code hoặc state; token endpoint và revocation endpoint có thể nhận credential trong header hoặc body. Không ghi nguyên request URL, Authorization header, form body hoặc response body của các endpoint này nếu chưa có bộ lọc loại bỏ dữ liệu nhạy cảm.

## 9. Lưu ý về thu hồi JWT và resource server

Với access token dạng JWT, resource server có thể xác minh chữ ký và thời hạn token ngay tại chỗ mà không hỏi Authorization Server ở mỗi request. Khi Authorization Server đánh dấu token là invalidated trong kho authorization, một resource server chỉ kiểm tra chữ ký JWT cục bộ có thể chưa nhận biết việc thu hồi.

Nếu cần thu hồi có hiệu lực nhanh, kiến trúc phải có cơ chế để resource server kiểm tra trạng thái, chẳng hạn dùng opaque token với introspection, danh sách chặn được đồng bộ, hoặc một cơ chế kiểm tra thu hồi tương đương. Một lựa chọn khác là dùng access token có thời hạn ngắn để giới hạn khoảng thời gian token còn được chấp nhận. Audit ghi nhận **TOKEN_REVOKED** giúp điều tra và đối chiếu, nhưng bản thân bản ghi audit không làm cho resource server tự động từ chối JWT đã phát hành.

## 10. Kiểm thử các sự kiện kiểm toán

Kiểm thử nên xác minh cả sự kiện được tạo và nội dung nhạy cảm không bị rò rỉ:

1. Đăng nhập thành công và thất bại đều tạo đúng event type; client authentication không bị phân loại nhầm thành đăng nhập người dùng.
2. Consent lần đầu tạo **CONSENT_GRANTED**; thay đổi scope tạo **CONSENT_UPDATED**; gỡ consent tạo **CONSENT_REMOVED**.
3. Authorization code được đổi lấy access token tạo sự kiện cấp token sau khi authorization được lưu thành công.
4. Luồng refresh token ghi nhận access token mới và refresh token được xoay vòng nếu cấu hình có rotation.
5. Thu hồi token đang hoạt động tạo **TOKEN_REVOKED**; token hết hạn không bị ghi nhầm thành token vừa thu hồi.
6. Xóa authorization tạo **AUTHORIZATION_REMOVED**, tách biệt với thu hồi một token.
7. Audit store lỗi hoặc outbox bị tồn đọng được xử lý theo chính sách đã định nghĩa và phát cảnh báo.
8. Log không chứa password, client secret, authorization code, PKCE verifier, access token, refresh token hoặc ID Token nguyên bản.

Khi các sự kiện được đặt đúng điểm trong vòng đời xác thực, consent và authorization, đội vận hành có thể truy vết hoạt động của Authorization Server mà vẫn giữ bí mật token và thông tin xác thực. Cấu trúc audit thống nhất cũng giúp kết nối log với trace, phát hiện bất thường và đáp ứng yêu cầu kiểm toán trong quá trình vận hành OAuth 2.0/OpenID Connect.

