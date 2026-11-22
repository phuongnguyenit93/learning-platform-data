# Liên kết tài khoản có xác minh và ngăn account takeover

## 1. Bối cảnh và phạm vi

Một ứng dụng có thể cho người dùng đăng nhập bằng mật khẩu, passkey và nhiều OpenID Provider (OP) khác nhau. Người dùng có thể muốn liên kết tài khoản công ty, tài khoản cá nhân hoặc một nhà cung cấp đăng nhập thứ hai để làm phương thức truy cập dự phòng.

Federated account linking là việc ứng dụng gắn một federated identity với một tài khoản nội bộ đã tồn tại. Khi người dùng xác thực tại Identity Provider (IdP), ứng dụng dùng định danh đã liên kết để tìm đúng local account.

Đây là thao tác có thể thay đổi quyền kiểm soát tài khoản. Nếu ứng dụng tự động ghép hai tài khoản chỉ vì email giống nhau, kẻ tấn công có thể gắn danh tính của họ vào tài khoản nạn nhân hoặc chiếm quyền truy cập vào tài khoản được tạo trước.

Trong hệ thống Spring, cần phân định vai trò:

- Spring Security OAuth2 Client xử lý đăng nhập với IdP bên ngoài, kiểm tra OIDC response và cung cấp OIDC principal.
- Account/Identity service của ứng dụng quyết định danh tính bên ngoài được liên kết với tài khoản nội bộ nào.
- Spring Authorization Server có thể đóng vai trò broker hoặc OpenID Provider nội bộ, phát token cho ứng dụng downstream sau khi người dùng đã được ánh xạ thành tài khoản nội bộ.

Spring Authorization Server không tự cung cấp một mô hình account-linking hoàn chỉnh. Ứng dụng cần quản lý liên kết trong domain/account store của mình và chỉ cấp quyền sau khi xác minh đầy đủ.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt local account, external identity, IdP và RP.
2. Xác định federated identity bằng issuer và subject.
3. Giải thích vì sao email hoặc username không phải khóa liên kết.
4. Thiết kế quy trình link yêu cầu xác thực tài khoản hiện tại và xác minh IdP mới.
5. Ngăn CSRF, login CSRF, session swapping và callback injection.
6. Nhận diện account pre-hijacking và lỗi tự động merge.
7. Thiết kế schema, unique constraint và transaction cho identity mapping.
8. Tích hợp Spring Security OIDC Login với account-linking service.
9. Phân biệt luồng login thông thường với luồng link identity.
10. Thiết kế unlink, recovery, audit, notification và kiểm thử chống takeover.

## 2. Các vai trò và dữ liệu cần phân biệt

| Thành phần | Ý nghĩa | Ví dụ |
|---|---|---|
| Local account | Tài khoản mà ứng dụng quản lý | account_id = 8f... |
| External identity | Định danh của một người dùng tại IdP | issuer + subject |
| Identity Provider (IdP/OP) | Bên xác thực người dùng và phát assertion | Corporate OIDC Provider |
| Relying Party (RP) | Ứng dụng nhận assertion và tạo phiên nội bộ | Spring Security OAuth2 Client |
| Identity link | Bản ghi nối external identity với local account | account_id ↔ issuer/sub |
| Authorization Server nội bộ | Phát token cho client downstream | Spring Authorization Server |

Một người có thể có nhiều external identity nhưng vẫn dùng một local account. Ví dụ, người dùng liên kết tài khoản công ty và tài khoản cá nhân với cùng hồ sơ nội bộ.

External identity không phải local account. Email, tên hiển thị và avatar là thuộc tính hồ sơ; chúng có thể thay đổi và không nên quyết định quyền sở hữu tài khoản.

## 3. Khóa định danh OIDC: issuer kết hợp subject

Với OpenID Connect, định danh ổn định của End-User tại một issuer là cặp:

- iss: Issuer Identifier của OpenID Provider.
- sub: Subject Identifier do issuer cấp.

OIDC Core quy định iss và sub kết hợp là định danh ổn định duy nhất mà RP có thể dựa vào. sub phải duy nhất trong phạm vi issuer và không được gán lại cho End-User khác. Các claim như email, phone_number, preferred_username và name không có bảo đảm ổn định hoặc duy nhất tương tự.

Vì vậy, ứng dụng nên dùng khóa logic:

~~~text
FederatedIdentityKey = (issuer, subject)
~~~

Không dùng riêng sub vì hai IdP khác nhau có thể phát cùng giá trị subject. Không tự chuẩn hóa issuer bằng cách bỏ path, đổi chữ hoa/thường hoặc xóa dấu slash; so sánh theo Issuer Identifier đã xác minh và cấu hình tin cậy.

### 3.1. Subject là opaque identifier

sub là định danh máy đọc. Không phân tích cấu trúc, không giả định nó chứa email hoặc username và không cho người dùng tự nhập subject để liên kết.

Ứng dụng chỉ lấy subject từ ID Token đã được xác minh. Không nhận iss hoặc sub từ form, query parameter hay JSON request của browser.

### 3.2. Pairwise subject và nhiều Client Registration

Một số OP dùng pairwise subject identifier để không cho các RP khác nhau dễ dàng liên kết cùng một người dùng. Khi đó cùng một End-User có thể nhận các sub khác nhau theo sector/client context.

Không giả định một subject nhận từ client registration A sẽ giống subject của registration B. Nếu hệ thống dùng nhiều OIDC client registration với cùng IdP, hãy xác định sector identifier và chiến lược định danh trước. Dùng đúng registration đã cấu hình cho luồng link; nếu cần di chuyển registration, cần quy trình migration được xác minh tại IdP.

## 4. Vì sao không được tự động liên kết bằng email?

Email là thuộc tính liên hệ, không phải federated identifier. OIDC Core nêu rõ RP MUST NOT dùng email, phone_number, preferred_username hoặc name làm định danh duy nhất.

Ngay cả khi IdP trả email_verified=true, điều đó chỉ là thông tin về trạng thái xác minh email theo chính sách của issuer. Nó không chứng minh external identity thuộc về local account đang mở trong browser, cũng không chứng minh người đang giữ local session có quyền thêm phương thức đăng nhập mới.

Email có thể thay đổi theo thời gian, được IdP tái sử dụng sau khi tài khoản cũ bị đóng, có alias hoặc quy tắc chuẩn hóa khác nhau giữa các hệ thống, và được xác minh ở một thời điểm nhưng không còn thuộc quyền kiểm soát của cùng một người.

Do đó:

- Dùng cặp (iss, sub) làm khóa external identity.
- Có thể lưu email như snapshot phục vụ hiển thị hoặc thông báo.
- Không dùng email trùng nhau để tự động merge hoặc link account.
- Không dùng email_verified thay cho xác thực lại tài khoản nội bộ.

Email có thể hỗ trợ tìm hồ sơ để bắt đầu một quy trình account resolution có kiểm soát, nhưng quyết định liên kết phải dựa trên bằng chứng đủ mạnh rằng external identity thực sự thuộc về chủ tài khoản nội bộ.

## 5. Các nguyên tắc bảo mật cho account linking

Một quy trình link an toàn cần duy trì các bất biến sau:

1. Người dùng đã xác thực vào local account trước khi bắt đầu link.
2. Với thao tác nhạy cảm, người dùng phải re-authenticate hoặc step-up bằng phương thức đã gắn với local account.
3. Người dùng hoàn tất một OIDC authentication transaction riêng với IdP mới.
4. Callback được ràng buộc với đúng browser session, đúng local account và đúng IdP đã chọn.
5. ID Token được xác minh trước khi trích xuất issuer và subject.
6. Một external identity chỉ thuộc về tối đa một local account trong phạm vi RP.
7. Không có đường tự động merge chỉ dựa trên email hoặc profile claims.
8. Việc link/unlink có audit và notification.
9. Việc unlink phải vô hiệu quyền đăng nhập của external identity đã bị gỡ.
10. Cơ sở dữ liệu phải bảo vệ các bất biến bằng unique constraint và transaction, không chỉ bằng kiểm tra ở tầng Java.

NIST SP 800-63C-4 Section 3.8.1 quy định RP SHALL yêu cầu một authenticated session với tài khoản subscriber cho mọi chức năng linking. Session này SHOULD yêu cầu xác thực bằng một federated identifier hiện có trước khi liên kết federated identifier mới.

## 6. Threat model: kẻ tấn công có thể chiếm tài khoản bằng cách nào?

### 6.1. Tự động merge theo email

Nạn nhân đã có local account bằng mật khẩu. Kẻ tấn công tạo hoặc kiểm soát một external account dùng email giống nạn nhân. Nếu ứng dụng tự động gắn external identity đó vào local account có email trùng, kẻ tấn công có thêm phương thức đăng nhập vào tài khoản nạn nhân.

### 6.2. Account pre-hijacking

Account pre-hijacking xảy ra khi attacker thực hiện hành động trước lúc nạn nhân hoàn tất tạo tài khoản. Một ví dụ là attacker tạo local password account bằng email của nạn nhân. Sau đó, nạn nhân đăng nhập bằng IdP và ứng dụng tự merge theo email. Tài khoản nội bộ vẫn giữ password do attacker biết, khiến attacker tiếp tục truy cập sau khi nạn nhân sử dụng SSO.

Nghiên cứu USENIX Security 2022 ghi nhận nhiều dạng pre-hijacking, trong đó có Classic-Federated Merge Attack. Vì vậy, luồng signup, login và linking phải được thiết kế cùng nhau; chỉ bảo vệ endpoint link là chưa đủ.

### 6.3. Login CSRF hoặc callback injection

Attacker khởi tạo đăng nhập với IdP của chính họ, sau đó tìm cách đưa callback/authorization response đó vào browser đang đăng nhập local account của nạn nhân. Nếu ứng dụng không ràng buộc transaction với session và intent link, external identity của attacker có thể bị gắn vào account nạn nhân.

### 6.4. Session swapping

Người dùng bắt đầu link trên tài khoản A. Trong lúc chuyển hướng tới IdP, session bị thay đổi, đăng xuất hoặc chuyển sang tài khoản B. Nếu callback chỉ lấy account ID từ state do browser gửi hoặc từ dữ liệu không được ràng buộc, identity có thể bị gắn nhầm.

### 6.5. Race condition

Hai request cùng lúc cố gắng liên kết một external identity với hai local account. Nếu ứng dụng chỉ kiểm tra tồn tại trước khi insert, cả hai request có thể cùng vượt qua bước kiểm tra và tạo liên kết xung đột.

### 6.6. IdP giả hoặc issuer confusion

Attacker gửi một issuer tùy ý, khai thác discovery URL không được kiểm soát hoặc làm ứng dụng nhầm callback từ IdP này sang IdP khác. Kết quả có thể là tin một identity do issuer không được phép phát hành.

## 7. Luồng account linking an toàn

~~~mermaid
sequenceDiagram
    actor U as Người dùng
    participant APP as Ứng dụng / RP
    participant DB as Account & Identity Store
    participant IDP as External OIDC Provider

    U->>APP: POST /account/identities/{provider}/link
    APP->>APP: Kiểm tra CSRF và local session
    APP->>APP: Re-auth / step-up nếu policy yêu cầu
    APP->>DB: Tạo PendingLink gắn account + session + issuer
    APP-->>U: Redirect tới OIDC Authorization Endpoint
    U->>IDP: Authentication Request + state + nonce + PKCE
    IDP->>IDP: Xác thực người dùng tại IdP
    IDP-->>U: Redirect callback + authorization code + state
    U->>APP: GET /login/oauth2/code/{registrationId}
    APP->>APP: Kiểm tra state, PKCE, ID Token và nonce
    APP->>DB: Tìm PendingLink và xác minh session binding
    APP->>APP: Trích issuer + subject từ ID Token đã xác minh
    APP->>DB: Transaction + unique (issuer, subject)
    DB-->>APP: Identity linked
    APP->>DB: Ghi audit + notification outbox
    APP-->>U: Giữ local account session và hiển thị kết quả
~~~

Callback của IdP chỉ chứng minh người dùng đã xác thực với IdP. Nó không tự quyết định local account đích. Local account đích phải được xác định từ transaction server-side đã tạo trước đó.

## 8. Bắt đầu link từ một local account đã xác thực

Endpoint bắt đầu link nên là POST, có CSRF protection và yêu cầu người dùng đang đăng nhập:

~~~http
POST /account/identities/workforce/link HTTP/1.1
Host: app.example.com
Cookie: SESSION=...
X-CSRF-TOKEN: ...
Content-Type: application/x-www-form-urlencoded
~~~

Server thực hiện:

1. Lấy local account ID từ principal đã xác thực.
2. Kiểm tra account đang active và không bị khóa.
3. Kiểm tra phương thức xác thực hiện tại có đủ mạnh theo policy.
4. Yêu cầu re-authentication/step-up nếu thao tác nhạy cảm hoặc session đã quá cũ.
5. Kiểm tra provider registration nằm trong allowlist.
6. Tạo pending link transaction có thời hạn ngắn.
7. Redirect browser tới authorization endpoint của đúng provider.

Không dùng GET để thực hiện thay đổi trạng thái. Không cho browser truyền trực tiếp account ID đích trong request body để quyết định account được link.

### 8.1. Re-authentication và step-up

Liên kết thêm một phương thức đăng nhập có thể giúp người dùng khôi phục tài khoản, nhưng cũng mở thêm một con đường cho attacker. Vì vậy, hãy yêu cầu xác thực lại bằng một phương thức đã gắn với local account trước khi link.

Tùy mức rủi ro, có thể yêu cầu nhập lại mật khẩu hiện tại, xác thực passkey hoặc MFA, xác thực lại qua federated identity đang được liên kết, hoặc xác thực bổ sung bởi help desk/quy trình recovery có kiểm soát.

Không coi việc vừa đăng nhập bằng IdP mới là bằng chứng cho quyền kiểm soát local account cũ.

## 9. Pending link transaction và session binding

Không đưa account ID, email hoặc quyền quyết định link vào query parameter có thể sửa. Tạo transaction server-side:

~~~java
public record PendingIdentityLink(
    String stateHash,
    UUID localAccountId,
    String localSessionBinding,
    String registrationId,
    String expectedIssuer,
    Instant createdAt,
    Instant expiresAt,
    LinkStatus status
) {
}
~~~

Đây là model minh họa. Transaction nên chứa hash của state hoặc transaction identifier khó đoán, local account ID lấy từ authenticated principal, dấu ràng buộc browser session, registration ID và issuer dự kiến, thời điểm tạo/hết hạn và trạng thái PENDING/CONSUMED/EXPIRED/FAILED.

State không chứa raw account ID. Dữ liệu nhạy cảm được lưu server-side, không tin nội dung state do browser gửi lại nếu chưa được Spring Security xác minh.

### 9.1. State, nonce và PKCE

Trong OIDC Authorization Code Flow:

- state liên kết authorization response với request và browser session.
- nonce liên kết ID Token với authentication request, giúp chống replay.
- PKCE ràng buộc authorization code với client đã khởi tạo request.

Các giá trị phải theo transaction, khó đoán, dùng một lần và được ràng buộc với browser session. Không dùng state hoặc nonce cố định. Không tắt kiểm tra state/nonce chỉ để callback chạy được.

Spring Security OAuth2 Login đã có cơ chế quản lý authorization request và xác minh response. Nếu tùy biến AuthorizationRequestResolver hoặc AuthorizationRequestRepository, phải giữ nguyên các kiểm tra đó và bảo đảm pending link transaction được ràng buộc cùng session.

Với public client, Spring Security tự dùng PKCE khi registration được cấu hình là public. Với confidential client, nếu policy yêu cầu PKCE, có thể bật bằng authorization request customizer:

~~~java
@Bean
OAuth2AuthorizationRequestResolver authorizationRequestResolver(
        ClientRegistrationRepository registrations) {

    DefaultOAuth2AuthorizationRequestResolver resolver =
        new DefaultOAuth2AuthorizationRequestResolver(
            registrations,
            DefaultOAuth2AuthorizationRequestResolver
                .DEFAULT_AUTHORIZATION_REQUEST_BASE_URI);

    resolver.setAuthorizationRequestCustomizer(
        OAuth2AuthorizationRequestCustomizers.withPkce());

    return resolver;
}
~~~

Gắn resolver này vào oauth2Login bằng authorizationEndpoint(...).authorizationRequestResolver(...). Nếu IdP hỗ trợ, có thể bổ sung prompt=login hoặc max_age cho luồng link; vẫn phải kiểm tra auth_time khi đã yêu cầu max_age. Không tự ghi đè state, nonce hoặc code_verifier do Spring Security quản lý.

### 9.2. Thời hạn và tiêu thụ một lần

Pending link nên có TTL ngắn, ví dụ vài phút theo UX và policy. Khi callback thành công hoặc thất bại cuối cùng, transaction phải được tiêu thụ hoặc đóng. Callback lặp lại không được tạo thêm liên kết.

Không giữ pending link vô thời hạn trong session. Xóa transaction khi người dùng hủy, logout, đổi local account hoặc session hết hạn.

## 10. Cấu hình provider OIDC tin cậy trong Spring Security

Chỉ cho phép các IdP được quản trị viên cấu hình trước. Không nhận issuer/discovery URL tùy ý từ browser.

Ví dụ cấu hình Spring Boot:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          workforce:
            provider: workforce-idp
            client-id: app-linking-client
            client-secret: SECRET_FROM_SECRET_MANAGER
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
        provider:
          workforce-idp:
            issuer-uri: https://idp.example.com
~~~

Ứng dụng dùng issuer discovery để lấy authorization endpoint, token endpoint và JWKS URI. Trong production, dùng HTTPS, quản lý client secret trong secret manager, cố định issuer/registration ID, kiểm soát redirect URI chính xác và không cho người dùng chọn arbitrary issuer hoặc discovery URL.

### 10.1. Không tự tải khóa từ issuer trong token

Không tin iss, jku, x5u hoặc URL do JWT header/claim tự cung cấp để tải khóa. Dùng issuer đã cấu hình và JWKS endpoint lấy từ discovery đã xác minh.

Nếu hệ thống hỗ trợ nhiều issuer, phải giữ liên hệ rõ ràng giữa registration ID, issuer, callback URI và token validation policy để tránh mix-up.

## 11. Xác minh ID Token trước khi liên kết

Chỉ lấy external identity sau khi OIDC authentication thành công và ID Token được xác minh.

Các kiểm tra OIDC quan trọng gồm:

- Chữ ký ID Token hợp lệ theo khóa của issuer tin cậy.
- iss khớp chính xác Issuer Identifier đã cấu hình/discovery.
- aud chứa client_id của registration đang xử lý.
- azp được kiểm tra khi có và theo yêu cầu OIDC.
- exp chưa hết hạn.
- iat nằm trong khoảng chấp nhận.
- nonce khớp nonce đã gửi trong authentication request.
- auth_time được kiểm tra khi request max_age hoặc yêu cầu auth_time.
- Thuật toán ký nằm trong allowlist theo registration.

Không chỉ decode JWT rồi đọc payload. ID Token phải qua validation; không dùng access token thay ID Token để xác định danh tính người dùng.

### 11.1. Vai trò của Spring Security OidcUserService

Spring Security cung cấp OidcUserService cho OIDC Login. Framework dùng nó để xử lý UserInfo khi cần và trả về OidcUser. OidcIdTokenDecoderFactory cung cấp JwtDecoder phục vụ xác minh chữ ký ID Token.

Khi dùng Spring Security OAuth2 Login mặc định, hãy giữ validation của framework. Nếu custom decoder, user service hoặc authorization request resolver, phải bảo toàn issuer, audience, signature, expiry, nonce và các kiểm tra liên quan.

### 11.2. Lấy identity từ ID Token đã xác minh

Sau khi authentication thành công, lấy:

~~~java
OidcUser oidcUser = ...; // Principal do Spring Security tạo sau OIDC validation

OidcIdToken idToken = oidcUser.getIdToken();

String issuer = idToken.getClaimAsString(IdTokenClaimNames.ISS);
String subject = idToken.getSubject();

String email = idToken.getClaimAsString(IdTokenClaimNames.EMAIL);
Boolean emailVerified =
    idToken.getClaim(IdTokenClaimNames.EMAIL_VERIFIED);
~~~

Các giá trị issuer và subject là dữ liệu identity. Email và email_verified chỉ là thuộc tính tùy chọn; không dùng chúng để chọn local account.

## 12. Thiết kế bảng external identity

Một schema đơn giản:

~~~sql
CREATE TABLE external_identity (
    id                  UUID PRIMARY KEY,
    local_account_id    UUID NOT NULL,
    issuer              VARCHAR(1024) NOT NULL,
    subject             VARCHAR(255) NOT NULL,
    registration_id     VARCHAR(100) NOT NULL,
    email_snapshot      VARCHAR(320),
    email_verified      BOOLEAN,
    linked_at           TIMESTAMP NOT NULL,
    linked_by           VARCHAR(255),
    status              VARCHAR(30) NOT NULL,
    CONSTRAINT fk_external_identity_account
        FOREIGN KEY (local_account_id)
        REFERENCES local_account(id),
    CONSTRAINT uq_external_identity_issuer_subject
        UNIQUE (issuer, subject)
);

CREATE INDEX ix_external_identity_account
    ON external_identity(local_account_id);
~~~

Kiểu UUID và kiểu timestamp có thể điều chỉnh theo database. Unique constraint trên (issuer, subject) bảo đảm một external identity không được gắn vào hai local account.

Hai cột issuer và subject phải được so sánh theo semantics phân biệt chữ hoa/thường của OIDC. Không lowercase, trim hoặc canonicalize giá trị trước khi lưu. Nếu database mặc định dùng collation không phân biệt hoa/thường, hãy chọn collation/kiểu lưu trữ phù hợp hoặc tạo khóa nhị phân từ hai giá trị nguyên bản.

registration_id giúp audit biết identity được xác minh qua cấu hình client nào. Nó không thay thế issuer/subject làm federated key.

### 12.1. Lưu email chỉ như snapshot

Nếu cần hiển thị tài khoản liên kết, có thể lưu email snapshot và cờ email_verified tại thời điểm link. Không dùng các cột này để tìm hoặc xác định identity trong lần đăng nhập tiếp theo.

Nếu người dùng đổi email tại IdP, identity key vẫn giữ nguyên khi issuer và subject không đổi.

### 12.2. Bảo vệ unique constraint

Không chỉ gọi existsByIssuerAndSubject rồi mới insert. Hai request đồng thời vẫn có thể cùng thấy “chưa tồn tại”. Unique constraint là lớp bảo vệ cuối cùng; service cần bắt lỗi conflict và trả kết quả an toàn.

## 13. Transaction service để liên kết identity

Service chỉ nhận OIDC principal đã được framework xác minh và local account ID lấy từ authenticated session:

~~~java
@Service
@RequiredArgsConstructor
public class AccountIdentityLinkService {

    private final ExternalIdentityRepository identities;
    private final TrustedProviderRegistry providers;
    private final AccountRepository accounts;

    @Transactional
    public LinkResult link(
            UUID localAccountId,
            String registrationId,
            OidcIdToken idToken) {

        LocalAccount account = accounts
            .findActiveById(localAccountId)
            .orElseThrow(AccountNotAvailableException::new);

        String issuer = idToken.getClaimAsString("iss");
        String subject = idToken.getSubject();

        providers.requireExpectedIssuer(registrationId, issuer);

        ExternalIdentity existing =
            identities.findByIssuerAndSubject(issuer, subject)
                .orElse(null);

        if (existing != null) {
            if (existing.getLocalAccountId().equals(localAccountId)) {
                return LinkResult.ALREADY_LINKED;
            }

            throw new IdentityAlreadyLinkedException();
        }

        ExternalIdentity identity = ExternalIdentity.link(
            localAccountId,
            issuer,
            subject,
            registrationId,
            idToken.getClaimAsString("email"),
            Boolean.TRUE.equals(
                idToken.getClaim("email_verified")));

        identities.save(identity);

        return LinkResult.LINKED;
    }
}
~~~

Đây là skeleton minh họa. Các class domain, repository và exception thuộc ứng dụng.

### 13.1. Kiểm tra provider/issuer

TrustedProviderRegistry phải ánh xạ registration ID tới issuer đã cấu hình. So sánh issuer trong ID Token đã xác minh với issuer mong đợi của registration. Không cho phép callback tự quyết định issuer đích.

### 13.2. Xử lý identity đã được liên kết

- Nếu identity đã liên kết với cùng local account, trả kết quả idempotent.
- Nếu identity đã liên kết với account khác, từ chối và chuyển sang quy trình recovery/account merge có xác minh.
- Không trả chi tiết account đích cho caller không có quyền.
- Không tự di chuyển identity giữa hai account chỉ vì email trùng.

### 13.3. Xử lý race condition

Khi insert gặp unique constraint violation, đọc lại identity trong một transaction phù hợp và phân loại kết quả: đã link cùng account hay conflict với account khác. Không bỏ qua lỗi database rồi báo link thành công.

Nếu có outbox notification, ghi outbox event trong cùng transaction với identity link để notification không bị mất khi process dừng giữa chừng.

## 14. Tích hợp Spring Security OAuth2 Login

Spring Security cung cấp OAuth2 Login qua Authorization Code Flow. Với OIDC, scope openid khiến framework dùng OIDC-specific components như OidcUserService.

Ví dụ cấu hình:

~~~java
@Configuration
@EnableWebSecurity
@RequiredArgsConstructor
class FederatedLoginSecurityConfig {

    private final AuthenticationSuccessHandler
        accountLinkAwareSuccessHandler;

    @Bean
    SecurityFilterChain applicationSecurity(HttpSecurity http)
            throws Exception {

        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/login/**", "/oauth2/**").permitAll()
                .requestMatchers("/account/identities/**").authenticated()
                .anyRequest().authenticated())
            .oauth2Login(oauth2 -> oauth2
                .userInfoEndpoint(userInfo -> userInfo
                    .oidcUserService(new OidcUserService()))
                .successHandler(accountLinkAwareSuccessHandler));

        return http.build();
    }
}
~~~

Đây là cấu hình rút gọn. Ứng dụng cần ClientRegistrationRepository và các thành phần OAuth2 Client tương ứng.

OidcUserService dùng để tải/chuẩn hóa OIDC principal. Việc lưu liên kết phải được thực hiện trong account-linking service sau khi xác định đúng pending link transaction; không nên tự ghi link trong OidcUserService vì service này cũng có thể chạy trong login thông thường.

## 15. Phân biệt callback login với callback link

Một callback OIDC có thể phục vụ hai ý định khác nhau:

- **Login:** người dùng muốn đăng nhập vào ứng dụng bằng external identity.
- **Link:** người dùng đã đăng nhập local account và muốn thêm external identity vào account hiện tại.

Không phân biệt hai ý định chỉ bằng query parameter như mode=link. Ý định link phải được lưu trong pending transaction server-side, gắn với local account và browser session.

Khi callback thành công:

1. Spring Security xác minh authorization response và tạo OIDC Authentication.
2. Success handler tìm pending link transaction tương ứng với callback đã được xác minh.
3. Kiểm tra transaction chưa hết hạn/chưa dùng và vẫn gắn với đúng local session.
4. Kiểm tra local account vẫn active và người dùng vẫn có quyền link.
5. Gọi AccountIdentityLinkService với ID Token đã xác minh.
6. Ghi audit/notification.
7. Giữ hoặc khôi phục local account authentication.
8. Redirect về trang quản lý identity.

### 15.1. Không biến external principal thành local account ngoài ý muốn

OAuth2 Login mặc định tạo Authentication từ external principal. Trong link flow, success handler phải phân biệt pending link với login thông thường và không để external principal thay thế local account session.

Pseudocode cho success handler:

~~~java
HttpSession session = request.getSession(false);

if (session != null
        && authentication instanceof OAuth2AuthenticationToken oauth2
        && oauth2.getPrincipal() instanceof OidcUser externalUser
        && pendingLinkRepository.hasValidatedCallback(request, session)) {
    PendingIdentityLink pending =
        pendingLinkRepository.consumeValidatedCallback(request, session);

    accountIdentityLinkService.link(
        pending.localAccountId(),
        pending.registrationId(),
        externalUser.getIdToken());

    localSessionRestorer.restore(
        pending.localAccountId(), request, response);
    return;
}

normalLoginSuccessHandler.onAuthenticationSuccess(
    request, response, authentication);
~~~

Đây là pseudocode mô tả luồng, không phải một class có thể copy nguyên trạng. pendingLinkRepository chỉ trả transaction sau khi Spring Security đã xác minh authorization response và state/session binding. localSessionRestorer phải tải lại local principal từ account store và lưu SecurityContext qua SecurityContextRepository; không nhận principal/account ID từ browser.

Có thể lưu local account ID và session binding trong pending transaction server-side, sau đó tái tạo/khôi phục local Authentication qua cơ chế session của ứng dụng. Nếu session gốc đã mất hoặc account hiện tại không còn khớp transaction, hủy link và yêu cầu người dùng bắt đầu lại.

Không lưu Authentication hoặc account ID trong cookie do browser tự quản lý mà không có integrity/binding phù hợp.

### 15.2. Nếu dùng callback riêng

Một ứng dụng có thể thiết kế callback endpoint riêng cho linking hoặc một authorization request resolver/repository riêng. Khi làm vậy, vẫn phải giữ nguyên code exchange, state, PKCE, nonce, ID Token validation, issuer binding và redirect URI validation. Không tự xây một callback “đọc JWT rồi insert” bỏ qua OIDC client pipeline.

## 16. Luồng login thông thường cũng phải dùng identity mapping an toàn

Khi người dùng đăng nhập qua IdP, ứng dụng tìm external identity theo cặp issuer/subject:

- Nếu đã liên kết, tải local account tương ứng và tạo local session.
- Nếu chưa có, áp dụng chính sách provisioning đã công bố.
- Nếu email trùng với local account khác, không tự động gắn identity vào account đó.
- Nếu cần kết nối với hồ sơ có sẵn, chuyển sang account resolution/recovery có bằng chứng đủ mạnh.

Không dùng tên hiển thị, email hoặc username để tìm local account rồi coi đó là quyền đăng nhập.

### 16.1. Just-in-time provisioning

Nếu sản phẩm cho phép tạo local account mới khi một federated identity chưa tồn tại, tạo account mới và gắn identity (iss, sub) vừa xác minh. Không lấy email trùng làm lý do merge vào một account khác.

Nếu tổ chức cần account pre-provisioning, phải có trust agreement và thuộc tính đủ mạnh để resolve đúng subscriber. NIST SP 800-63C-4 Section 3.8.2 yêu cầu RP bảo đảm các thuộc tính được yêu cầu đủ để xác định duy nhất subscriber và không liên kết account với federated identifier không thuộc subscriber.

## 17. Account linking khác account merging

**Linking** gắn thêm một phương thức đăng nhập vào cùng local account. **Merging** chuyển dữ liệu, quyền, giao dịch hoặc lịch sử từ hai local account khác nhau vào một account.

Hai thao tác có rủi ro khác nhau. Link một external identity đã được xác minh không chứng minh rằng hai local account có cùng chủ sở hữu.

Nếu cần merge, yêu cầu người dùng chứng minh quyền kiểm soát cả hai local account hoặc dùng quy trình recovery/identity proofing đã được phê duyệt; hiển thị rõ dữ liệu và quyền sẽ chuyển; kiểm tra xung đột tenant/role/ownership; dùng transaction có audit; thông báo khi phù hợp và giữ khả năng điều tra/rollback theo policy.

Không merge chỉ vì hai account có cùng email, tên, số điện thoại hoặc avatar.

## 18. Ngăn account pre-hijacking trong signup và recovery

Account pre-hijacking thường bắt đầu trước khi nạn nhân hoàn tất đăng ký. Một thiết kế an toàn cần:

- Xác minh email theo quy trình riêng trước khi dùng email làm kênh recovery hoặc liên hệ quan trọng.
- Không tự merge local-password account và federated account dựa trên email trùng.
- Không cho một external identity chưa xác minh nhận quyền trên local account đã tồn tại.
- Khi email trùng, hướng người dùng đăng nhập vào account hiện tại rồi chủ động link identity mới.
- Nếu người dùng không còn truy cập account cũ, dùng recovery/identity resolution có kiểm soát.
- Không để một tài khoản pre-created chưa xác minh email tự động trở thành account đích của federated login.
- Ghi nhận và thông báo thay đổi phương thức đăng nhập.

Nếu external identity đã liên kết với account khác, thông báo cho caller rằng identity không thể được liên kết. Không tiết lộ email, tên hoặc trạng thái tài khoản đích nếu người dùng không có quyền xem thông tin đó.

## 19. Unlink, recovery và tài khoản không còn phương thức đăng nhập

Unlink cũng là thao tác nhạy cảm. Trước khi xóa identity:

1. Yêu cầu local session hợp lệ và re-authentication theo policy.
2. Xác minh identity được yêu cầu gỡ thực sự thuộc local account hiện tại.
3. Kiểm tra account còn phương thức đăng nhập hoặc recovery khác.
4. Nếu đây là phương thức cuối cùng, yêu cầu thêm phương thức mới hoặc chuyển sang recovery đã xác minh.
5. Xóa/disable mapping trong transaction.
6. Từ chối mọi login mới qua identity đã gỡ.
7. Thu hồi session/token liên quan theo policy.
8. Ghi audit và gửi notification.

NIST SP 800-63C-4 yêu cầu RP disallow access vào account qua federated identifier đã bị gỡ. NIST cũng yêu cầu thông báo khi thêm federated identifier mới hoặc gỡ identifier mà account vẫn được giữ lại.

Nếu account không còn federated identifier, authenticator thay thế hoặc recovery path, ứng dụng phải có policy rõ ràng. Có thể disable account trong thời gian điều tra/recovery hoặc terminate theo retention policy.

## 20. Spring Authorization Server trong kiến trúc identity broker

~~~mermaid
flowchart TB
    U[End-User]
    IDP1[Corporate OIDC IdP]
    IDP2[Consumer OIDC IdP]
    APP[Identity Broker Application]
    MAP[(Local Account + External Identity Store)]
    SAS[Spring Authorization Server]
    CLIENT[Downstream OAuth/OIDC Clients]
    API[Resource Servers]

    U --> IDP1
    U --> IDP2
    IDP1 --> APP
    IDP2 --> APP
    APP <--> MAP
    APP --> SAS
    SAS --> CLIENT
    CLIENT --> API
~~~

Trong mô hình này, Spring Security OAuth2 Client xác thực người dùng tại upstream IdP; account store ánh xạ external identity về local account; Spring Authorization Server phát token nội bộ cho downstream clients; Resource Server kiểm tra token nội bộ theo issuer, audience và policy của hệ thống.

RegisteredClient đại diện cho ứng dụng OAuth/OIDC gọi Authorization Server. Nó không phải bản ghi external identity của người dùng. Không lưu account links trong RegisteredClient hoặc ClientSettings.

### 20.1. Subject của token nội bộ

Downstream client nên nhận một local subject ổn định của hệ thống, ví dụ local account ID dạng opaque. Không dùng email hoặc upstream sub làm subject nội bộ nếu muốn người dùng có thể liên kết nhiều IdP mà không đổi danh tính ở các ứng dụng downstream.

Khi một người dùng liên kết thêm IdP, local account không đổi; do đó subject nội bộ cũng không cần đổi. Không phát tán issuer/subject upstream nếu client downstream không có nhu cầu và quyền nhận dữ liệu đó.

### 20.2. Phân quyền không chỉ dựa trên linked identity

Việc một IdP đã được liên kết chỉ chứng minh phương thức đăng nhập được gắn với account. Nó không mặc nhiên cấp role, tenant membership hoặc quyền quản trị từ claim của IdP.

Áp dụng policy riêng cho external groups, organization, domain và role. Chỉ ánh xạ claim sau khi xác minh issuer, audience, nguồn claim và trust agreement.

## 21. Kiểm soát authorization request và re-authentication tại IdP

Với provider hỗ trợ, ứng dụng có thể yêu cầu xác thực mới bằng tham số OIDC như:

- prompt=login để yêu cầu OP thực hiện lại bước đăng nhập.
- max_age để giới hạn tuổi của lần xác thực; khi dùng, RP cần kiểm tra auth_time trong ID Token.
- acr_values để yêu cầu authentication context phù hợp nếu IdP hỗ trợ và có semantics được thống nhất.

Đây là yêu cầu gửi tới IdP; khả năng đáp ứng phụ thuộc OP. Không coi việc chỉ thêm prompt=login là đủ nếu IdP không xác minh lại authenticator hoặc policy yêu cầu MFA cụ thể.

Với local account, re-authentication bằng một authenticator hiện có vẫn là lớp kiểm soát riêng. Nếu provider không hỗ trợ step-up, ứng dụng phải dùng phương thức local khác hoặc từ chối link theo risk policy.

## 22. Kiểm thử account linking và takeover resistance

### 22.1. Test định danh

| Kịch bản | Kết quả mong đợi |
|---|---|
| Cùng issuer + subject | Tìm cùng external identity |
| Cùng subject, issuer khác | Hai external identity khác nhau |
| Email giống nhau, issuer/subject khác | Không tự động link |
| email_verified=false | Không ảnh hưởng khóa identity |
| Email thay đổi, issuer/subject giữ nguyên | Vẫn nhận đúng local account |
| Subject đã link với account khác | Từ chối link, không merge |
| Pairwise subject khác do registration/sector | Không tự giả định là cùng identity |

### 22.2. Test OIDC transaction

- State sai, thiếu hoặc replay.
- Nonce sai hoặc nonce đã dùng.
- PKCE verifier không khớp.
- ID Token sai chữ ký hoặc thuật toán ngoài allowlist.
- Issuer không khớp registration.
- Audience không chứa client_id.
- ID Token hết hạn.
- Auth time quá cũ khi yêu cầu max_age.
- Callback từ registration khác.
- Redirect URI hoặc issuer bị thay đổi.
- Pending link hết hạn hoặc session binding không khớp.

### 22.3. Test local account và session

- Người dùng chưa đăng nhập gọi endpoint link.
- CSRF token thiếu hoặc sai.
- Session đã đổi account sau khi bắt đầu link.
- Người dùng logout trước callback.
- Local account bị khóa trong lúc redirect.
- Link callback không có pending transaction.
- External login callback bị gửi vào luồng link.
- Re-authentication thất bại.
- Session fixation protection và session rotation sau thao tác nhạy cảm.

### 22.4. Test persistence và concurrency

- Hai request cùng link một identity vào cùng account.
- Hai account khác nhau đồng thời link cùng issuer/subject.
- Identity đã tồn tại cùng account (idempotent).
- Identity đã tồn tại account khác (conflict).
- Database unique constraint được kích hoạt.
- Notification outbox rollback cùng transaction khi insert thất bại.
- Unlink đồng thời với login.
- Login sau unlink phải bị từ chối.

### 22.5. Test account pre-hijacking

Mô phỏng tình huống:

1. Attacker tạo local account bằng email nạn nhân nhưng chưa chứng minh quyền sở hữu.
2. Nạn nhân đăng nhập bằng IdP có cùng email.
3. Hệ thống phải không tự merge.
4. Nạn nhân phải đăng nhập/recover local account theo quy trình phù hợp rồi mới link IdP.
5. Attacker không được giữ phương thức đăng nhập vào account sau khi nạn nhân hoàn tất xác minh.

## 23. Audit, notification và observability

Các event nên ghi nhận:

~~~text
IDENTITY_LINK_STARTED
IDENTITY_LINK_REAUTH_REQUIRED
IDENTITY_LINK_VALIDATION_FAILED
IDENTITY_LINK_CREATED
IDENTITY_LINK_ALREADY_EXISTS
IDENTITY_LINK_CONFLICT
IDENTITY_LINK_EXPIRED
IDENTITY_UNLINK_STARTED
IDENTITY_UNLINKED
IDENTITY_LOGIN_SUCCEEDED
IDENTITY_LOGIN_REJECTED
ACCOUNT_RECOVERY_REQUIRED
~~~

Audit nên có local account ID, registration ID, issuer, subject fingerprint/hash nếu cần giảm lộ định danh, correlation ID, transaction ID, thời gian, kết quả và mức re-auth đã đạt.

Không ghi raw ID Token, access token, refresh token, client secret hoặc session cookie. Email snapshot cũng cần tuân theo chính sách PII.

### 23.1. Notification

Thông báo cho người dùng khi identity được thêm hoặc gỡ. Nội dung nên nêu provider nào được thêm/gỡ, thời điểm, thiết bị/session nếu có, hành động nếu người dùng không thực hiện và kênh recovery/support đáng tin cậy.

Notification không được chứa token, authorization code hoặc link có quyền đăng nhập trực tiếp.

### 23.2. Metrics

Theo dõi link success/failure theo registration ID, conflict do identity đã thuộc account khác, state/nonce/issuer/audience validation failure, link attempt không có re-auth, unlink attempt khi account không còn phương thức thay thế, account recovery sau conflict và lỗi unique constraint/transaction rollback.

Không dùng email, subject hoặc account ID làm metric label có cardinality cao.

## 24. Các lỗi triển khai thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Dùng email làm federated key | Link nhầm người hoặc account takeover | Dùng exact issuer + subject |
| Auto-merge khi email_verified=true | Kẻ tấn công có thể giữ phương thức đăng nhập vào account | Yêu cầu local session và xác thực lại |
| Link khi chưa đăng nhập local account | Attacker có thể chọn account đích | Lấy account từ authenticated principal |
| Dùng account_id trong query để link | Thay đổi account đích bằng tampering | Lưu target account server-side |
| Bỏ kiểm tra state/nonce/PKCE | Callback injection và replay | Giữ transaction binding của OIDC |
| Tin issuer từ browser/JWT header | Issuer confusion | Dùng provider allowlist và discovery tin cậy |
| Link trong OidcUserService cho mọi login | Login thường có thể vô tình thay đổi account mapping | Thực hiện link trong dedicated flow/success handler |
| Callback link thay local Authentication | Người dùng bị chuyển account hoặc mất context | Khôi phục local principal sau khi link |
| Chỉ kiểm tra exists rồi insert | Race condition | Unique constraint và transaction |
| Link identity đã thuộc account khác | Một identity truy cập nhiều account | Từ chối và chuyển recovery/merge |
| Unlink phương thức cuối cùng | Account bị khóa ngoài ý muốn | Yêu cầu phương thức thay thế/recovery |
| Không thông báo khi link/unlink | Người dùng không phát hiện takeover | Audit và notification |
| Đưa upstream sub vào token nội bộ | Lộ định danh IdP và khó thay provider | Dùng local subject ổn định |
| Tin group/role claim trực tiếp | Leo thang quyền | Ánh xạ theo trust policy |

## 25. Checklist production

### Account và identity model

- [ ] Local account và external identity là hai thực thể riêng.
- [ ] OIDC identity key là cặp (iss, sub) chính xác.
- [ ] Subject được xử lý như opaque identifier.
- [ ] Không dùng email, username, name hoặc phone làm federated key.
- [ ] Email và email_verified chỉ là profile snapshot.
- [ ] Có unique constraint trên issuer/subject.
- [ ] Có index tra cứu identity theo local account.
- [ ] Pairwise subject và nhiều registration đã được xem xét.

### Link flow

- [ ] Link chỉ bắt đầu từ authenticated local session.
- [ ] Endpoint bắt đầu link dùng POST và CSRF protection.
- [ ] Có re-authentication/step-up theo risk policy.
- [ ] Provider và issuer nằm trong allowlist.
- [ ] Pending transaction gắn local account, browser session và registration.
- [ ] State, nonce và PKCE theo transaction, dùng một lần.
- [ ] Callback chỉ dùng OIDC pipeline đã xác minh.
- [ ] ID Token issuer, audience, signature, expiry và nonce được validate.
- [ ] Auth time được kiểm tra nếu yêu cầu max_age.
- [ ] Callback không tự thay local account Authentication.
- [ ] Link service chỉ nhận identity từ OIDC principal đã xác minh.

### Persistence và account lifecycle

- [ ] Link được ghi trong transaction.
- [ ] Race condition được bảo vệ bằng unique constraint.
- [ ] Identity đã thuộc account khác bị từ chối.
- [ ] Account merge có quy trình xác minh riêng.
- [ ] Unlink vô hiệu quyền đăng nhập của identity đã gỡ.
- [ ] Không cho unlink phương thức cuối cùng nếu chưa có recovery.
- [ ] Có audit, notification và outbox phù hợp.
- [ ] Có account recovery cho trường hợp mất mọi phương thức truy cập.

### Spring và Authorization Server

- [ ] Spring Security OAuth2 Client dùng OIDC Login cho upstream IdP.
- [ ] OidcUserService chỉ tải/chuẩn hóa principal; domain service quyết định link.
- [ ] OAuth2 success handler phân biệt login với link intent server-side.
- [ ] Spring Authorization Server phát token dựa trên local principal.
- [ ] RegisteredClient không được dùng để lưu user identity links.
- [ ] Token subject nội bộ ổn định, không dùng email/upstream subject.
- [ ] Downstream roles/claims được ánh xạ theo policy riêng.

### Kiểm thử và vận hành

- [ ] Có test email collision và account pre-hijacking.
- [ ] Có test state/nonce/PKCE và issuer mix-up.
- [ ] Có test wrong audience, signature và expired token.
- [ ] Có test session swapping và callback replay.
- [ ] Có concurrency test cho cùng external identity.
- [ ] Có test unlink và login sau unlink.
- [ ] Có metrics, audit, alert và runbook.
- [ ] Log không chứa token, session cookie hoặc credential thô.

### Kiến thức cốt lõi

Account linking là thao tác gắn thêm một federated identifier vào local account. Với OIDC, khóa identity phải là cặp **issuer và subject** đã được xác minh. Email, kể cả email_verified, không phải bằng chứng đủ để tự động ghép hai account.

Người dùng phải có authenticated session với local account và nên re-authenticate bằng một phương thức hiện có trước khi link. OIDC callback phải được ràng buộc với transaction và browser session, sau đó ID Token mới được dùng để trích issuer/subject. Database cần unique constraint và transaction để ngăn race condition hoặc một external identity bị gắn vào nhiều account.

Trong Spring Security, OAuth2 Client/OIDC Login xử lý upstream authentication; account-linking service chịu trách nhiệm quyết định mapping; Spring Authorization Server có thể phát token downstream dựa trên local account principal. Tách ba trách nhiệm này giúp ngăn việc external login vô tình thay thế local session hoặc cấp quyền vào account sai. Link, unlink và recovery đều cần audit, notification và kiểm thử account takeover.

## Tài liệu tham khảo

- [OpenID Connect Core 1.0 incorporating errata set 2 — ID Token Validation](https://openid.net/specs/openid-connect-core-1_0.html#IDTokenValidation)
- [OpenID Connect Core 1.0 incorporating errata set 2 — Claim Stability and Uniqueness](https://openid.net/specs/openid-connect-core-1_0.html#ClaimStability)
- [NIST SP 800-63C-4 — Digital Identity Guidelines: Federation and Assertions](https://pages.nist.gov/800-63-4/sp800-63c.html)
- [NIST SP 800-63C-4 — Section 3.8.1 Account Linking](https://pages.nist.gov/800-63-4/sp800-63c.html#sec-account-linking)
- [OWASP Authentication Cheat Sheet — Secure Federated Account Linking](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html#secure-federated-account-linking)
- [OWASP Authentication Cheat Sheet — Require Re-authentication for Sensitive Features](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html#reauthentication)
- [OWASP OAuth 2.0 Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/OAuth2_Cheat_Sheet.html)
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700.html)
- [Spring Security — OAuth2 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html)
- [Spring Security — Advanced OAuth2 Login Configuration and OidcUserService](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html)
- [Sudhodanan and Paverd — Pre-hijacked Accounts, USENIX Security 2022](https://www.usenix.org/conference/usenixsecurity22/presentation/sudhodanan)
