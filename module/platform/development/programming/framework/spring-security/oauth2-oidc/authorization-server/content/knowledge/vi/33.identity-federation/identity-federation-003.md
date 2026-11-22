# Ánh xạ external principal sang tài khoản và subject nội bộ

## 1. Identity Federation trong kiến trúc Authorization Server

Identity Federation là việc một hệ thống chấp nhận kết quả xác thực từ một miền tin cậy khác. IdP chịu trách nhiệm xác thực người dùng; hệ thống nội bộ quyết định tài khoản local nào tương ứng và quyền nào được cấp.

Trong bài này, upstream IdP dùng OpenID Connect. Ứng dụng nội bộ hoạt động đồng thời như:

- **OIDC client/RP:** chuyển hướng người dùng tới IdP bên ngoài, nhận authorization response và xác minh ID Token.
- **Identity broker:** ánh xạ external principal sang local account.
- **Authorization Server:** dùng local account làm principal khi xử lý authorization request và phát hành token cho RP của hệ thống.

Identity Federation không có nghĩa là chuyển nguyên access token của IdP cho các ứng dụng nội bộ. Token upstream có audience, issuer, scope và chính sách riêng. Authorization Server nội bộ cần phát hành token của chính mình theo client registration, scope, consent và policy local.

### 1.1. Luồng tổng quát

~~~mermaid
sequenceDiagram
    autonumber
    participant B as Browser
    participant AS as Local Authorization Server
    participant IDP as External OIDC Provider
    participant MAP as Identity Mapping Service
    participant DB as Local Identity Store
    participant RP as Internal Relying Party

    B->>AS: GET /oauth2/authorize
    AS->>B: Redirect tới External IdP
    B->>IDP: OIDC Authorization Request
    IDP->>B: Authorization Response
    B->>AS: Callback với authorization code và state
    AS->>IDP: Token Request
    IDP-->>AS: ID Token và Access Token
    AS->>AS: Xác minh ID Token và UserInfo
    AS->>MAP: Resolve (iss, sub)
    MAP->>DB: Tìm external_identity
    DB-->>MAP: Local account hoặc chưa liên kết
    MAP->>DB: Provision/link theo policy nếu được phép
    MAP-->>AS: Local account principal
    AS->>AS: Tạo local authentication/session
    AS->>RP: Authorization Code / local ID Token
    RP->>AS: Token Request
    AS-->>RP: Local Access Token và ID Token
~~~

Luồng này có hai lần phát hành token khác nhau:

1. IdP bên ngoài phát hành token cho OIDC client nội bộ.
2. Authorization Server nội bộ phát hành token cho RP nội bộ.

RP chỉ cần biết issuer và subject của Authorization Server nội bộ. Việc người dùng đăng nhập bằng corporate IdP nào được xử lý ở lớp federation.

### 1.2. Phân biệt các định danh

| Giá trị | Phạm vi | Dùng để |
| --- | --- | --- |
| External `iss` | Một OIDC Provider/realm | Xác định issuer đã xác thực principal. |
| External `sub` | Một issuer | Nhận diện End-User trong issuer đó. |
| `registrationId` | Cấu hình OAuth2 Client local | Chọn cấu hình kết nối upstream IdP. |
| Local account ID | Database nội bộ | Quan hệ, khóa ngoại và nghiệp vụ nội bộ. |
| Local `sub` | Issuer OIDC nội bộ | Định danh End-User mà RP nhận được trong local ID Token. |

`registrationId` là tên cấu hình như `corporate` hoặc `partner-login`. Nó không phải định danh protocol và có thể đổi khi refactor cấu hình. Local account ID có thể là UUID hoặc khóa database. Local `sub` nên là định danh opaque, ổn định và không được tái sử dụng.

## 2. External identity phải được nhận diện bằng issuer và subject

OpenID Connect Core xác định cặp `iss` và `sub` là định danh ổn định mà RP có thể dựa vào. `sub` phải duy nhất trong phạm vi issuer, không được tái gán cho End-User khác và là chuỗi phân biệt chữ hoa/chữ thường. Các claim như `email`, `phone_number`, `preferred_username` và `name` không có bảo đảm tương tự về tính duy nhất hoặc ổn định.

Ví dụ hai IdP có thể cùng trả về:

~~~json
{
  "sub": "248289761001",
  "email": "alex@example.com"
}
~~~

Nếu chỉ dùng `sub` làm khóa, hai người dùng từ hai issuer khác nhau có thể bị gộp nhầm. Nếu chỉ dùng email, email thay đổi hoặc được tái sử dụng có thể dẫn đến account takeover.

Khóa định danh cần lưu là:

~~~text
external_identity_key = (issuer, subject)
~~~

Ví dụ:

| Issuer | Subject | Kết quả |
| --- | --- | --- |
| `https://idp-a.example.com` | `user-100` | External identity A |
| `https://idp-b.example.com` | `user-100` | External identity B |
| `https://idp-a.example.com` | `user-200` | External identity C |

Ba cặp trên là ba external identities khác nhau dù một số giá trị subject trùng nhau.

### 2.1. Dùng issuer đã được xác minh từ ID Token

Lấy issuer từ ID Token sau khi Spring Security đã xử lý OIDC authentication và validation. Không nhận `iss` từ query parameter, request body, header tùy ý hoặc profile do browser gửi lên.

Issuer phải khớp chính xác issuer được cấu hình/discovery cho upstream provider. Thành phần path của issuer cũng là một phần của định danh. Ví dụ `https://login.example.com` và `https://login.example.com/tenant-a` là hai issuer khác nhau.

Không tự ý lowercase issuer/subject, bỏ path hoặc port, xóa dấu slash để gộp issuer, hoặc thay subject bằng email. Nếu tổ chức thay issuer trong quá trình migration, xử lý bằng quy trình liên kết/migration có kiểm soát.

### 2.2. Pairwise subject từ upstream IdP

Một OIDC Provider có thể cấp pairwise subject khác nhau cho các sector/client khác nhau để ngăn các RP đối chiếu hoạt động của cùng một người dùng. Vì vậy, cùng một người có thể xuất hiện với hai external `sub` khác nhau nếu hệ thống đăng ký hai OIDC client thuộc hai sector khác nhau.

Trong trường hợp đó, coi hai cặp `iss`/`sub` là hai external identities riêng. Nếu cần gắn chúng vào cùng local account, yêu cầu người dùng xác thực và liên kết rõ ràng. Không tự gộp chúng chỉ vì email giống nhau.

## 3. Thiết kế local account và external identity store

Local account là nguồn dữ liệu chuẩn cho nghiệp vụ nội bộ. External identity chỉ là một phương thức đăng nhập được liên kết với account.

Một local account có thể liên kết nhiều external identities, ví dụ tài khoản công ty và tài khoản đối tác, IdP chính và IdP dự phòng, hoặc nhiều realm/tenant được tổ chức cho phép.

### 3.1. Mô hình dữ liệu

Có thể dùng hai bảng chính:

~~~sql
CREATE TABLE local_account (
    id UUID PRIMARY KEY,
    subject_id VARCHAR(255) NOT NULL UNIQUE,
    status VARCHAR(24) NOT NULL,
    display_name VARCHAR(200),
    email VARCHAR(320),
    email_verified BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE TABLE external_identity (
    id UUID PRIMARY KEY,
    issuer VARCHAR(512) NOT NULL,
    subject VARCHAR(255) NOT NULL,
    account_id UUID NOT NULL REFERENCES local_account(id),
    registration_id VARCHAR(100) NOT NULL,
    email_at_link VARCHAR(320),
    email_verified_at_link BOOLEAN NOT NULL DEFAULT FALSE,
    linked_at TIMESTAMP WITH TIME ZONE NOT NULL,
    last_authenticated_at TIMESTAMP WITH TIME ZONE,
    CONSTRAINT uq_external_identity_issuer_subject
        UNIQUE (issuer, subject)
);

CREATE INDEX ix_external_identity_account_id
    ON external_identity(account_id);
~~~

Ý nghĩa:

- `local_account.id` là khóa nội bộ cho quan hệ database.
- `local_account.subject_id` là local subject được phát hành cho RP.
- `external_identity.issuer` và `external_identity.subject` tạo thành khóa duy nhất của external identity.
- `external_identity.account_id` trỏ tới local account.
- `registration_id` ghi nhận cấu hình client đã dùng để đăng nhập; nó hữu ích cho vận hành nhưng không thay thế issuer/subject.
- `email_at_link` là snapshot phục vụ audit, không phải khóa định danh.

`sub` trong OIDC không vượt quá 255 ký tự ASCII. Độ dài cột issuer trong ví dụ là lựa chọn triển khai, cần điều chỉnh theo issuer URI thực tế. Database phải so sánh issuer và subject theo quy tắc phân biệt chữ hoa/chữ thường; không dùng collation hoặc index case-insensitive để gộp các giá trị này.

### 3.2. Local subject phải ổn định và không tái sử dụng

Khi tạo local account, sinh một subject opaque, ví dụ UUID:

~~~java
String subjectId = UUID.randomUUID().toString();
~~~

Không dùng email, số điện thoại, username hoặc external `sub` làm local subject. Những giá trị này có thể thay đổi, bị tái sử dụng hoặc để lộ thông tin cá nhân.

Khi một external identity bị unlink, local account vẫn giữ nguyên `subject_id`. Khi người dùng chuyển từ IdP A sang IdP B, hệ thống có thể liên kết identity B với account cũ mà không làm thay đổi subject mà RP đã lưu.

Không tái sử dụng local subject của tài khoản đã xóa cho người dùng khác. Nếu cần xóa dữ liệu account, giữ tombstone hoặc registry tối thiểu để bảo đảm subject cũ không được cấp lại.
## 4. Cấu hình OIDC Client kết nối upstream IdP

Spring Security OAuth2 Client cung cấp `ClientRegistration` và `ClientRegistrationRepository` để cấu hình các provider bên ngoài.

Ví dụ cấu hình một corporate IdP bằng issuer discovery:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corporate:
            provider: corporate-idp
            client-id: local-authorization-server
            client-secret: <SECRET_FROM_SECRET_MANAGER>
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
        provider:
          corporate-idp:
            issuer-uri: https://idp.example.com
~~~

Các điểm cần lưu ý:

- `openid` là scope kích hoạt OIDC authentication.
- `profile` và `email` chỉ yêu cầu các nhóm claim cần thiết.
- `client-secret` phải được lấy từ secret manager hoặc cấu hình bảo mật.
- Redirect URI phải được đăng ký chính xác ở upstream IdP.
- `issuer-uri` phải là issuer đã được tổ chức tin cậy và kiểm tra qua discovery.
- Không cho người dùng tự nhập issuer URL để hệ thống tự discovery, vì điều đó có thể tạo SSRF và trust arbitrary provider.

Có thể cấu hình nhiều `ClientRegistration` cho nhiều IdP. Mỗi registration có thể có client ID, secret, redirect URI và scope khác nhau. Identity mapping vẫn dùng issuer và subject đã xác minh.

### 4.1. Chọn provider theo policy

Không nên tự động chấp nhận mọi IdP mà người dùng gửi tới. Danh sách provider được phép cần do quản trị viên cấu hình, kèm theo:

- issuer URI đã xác minh;
- registration ID;
- tenant hoặc nhóm người dùng được phép;
- chính sách auto-provisioning;
- chính sách email/group claim được tin cậy;
- yêu cầu MFA hoặc authentication assurance;
- trạng thái provider đang hoạt động hay đã bị thu hồi.

Nếu một provider bị vô hiệu hóa, ngăn login mới và áp dụng chính sách đối với session/token đã cấp trước đó.

## 5. Tích hợp OidcUserService để ánh xạ external principal

Sau khi OIDC authentication thành công, Spring Security dùng `OidcUserService` để tải thông tin người dùng từ UserInfo Endpoint và tạo `OidcUser`. Có thể delegate cho implementation mặc định để giữ xử lý protocol, sau đó resolve local account.

Không tự decode JWT bằng Base64 rồi tin claim. Việc xác minh chữ ký, issuer, audience, thời hạn, nonce và các điều kiện OIDC cần hoàn tất trước khi sử dụng principal.

### 5.1. Tạo service resolve external identity

Ví dụ service tùy chỉnh:

~~~java
@Component
public final class FederatedOidcUserService
        implements OAuth2UserService<OidcUserRequest, OidcUser> {

    private final OidcUserService delegate;
    private final ExternalIdentityService externalIdentityService;

    public FederatedOidcUserService(
            ExternalIdentityService externalIdentityService) {
        this.delegate = new OidcUserService();
        this.externalIdentityService = externalIdentityService;
    }

    @Override
    public OidcUser loadUser(OidcUserRequest request) {
        OidcUser externalUser = this.delegate.loadUser(request);
        OidcIdToken idToken = externalUser.getIdToken();

        String issuer = Objects.requireNonNull(idToken.getIssuer())
            .toString();
        String subject = Objects.requireNonNull(idToken.getSubject());

        String registrationId = request.getClientRegistration()
            .getRegistrationId();

        ExternalProfile profile =
            ExternalProfile.from(externalUser.getClaims());

        LocalAccount account = this.externalIdentityService.resolve(
            issuer,
            subject,
            registrationId,
            profile
        );

        if (!account.enabled()) {
            throw new OAuth2AuthenticationException(
                new OAuth2Error(OAuth2ErrorCodes.ACCESS_DENIED)
            );
        }

        return new FederatedLocalOidcUser(externalUser, account);
    }
}
~~~

Đây là điểm tích hợp giữa protocol identity và domain account:

1. Delegate xử lý OIDC user loading.
2. Lấy `iss` và `sub` từ ID Token đã được xác minh.
3. Lấy `registrationId` để áp dụng policy provider.
4. Chuyển các profile claim được phép dùng thành `ExternalProfile`.
5. Resolve external identity trong database.
6. Từ chối nếu local account bị khóa, vô hiệu hóa hoặc không được phép đăng nhập.
7. Trả về OIDC principal được gắn local account; success handler ở mục 6 chuyển nó thành local authentication.

Không lấy `registrationId` làm khóa external identity vì tên registration có thể đổi khi cấu hình được tổ chức lại.

### 5.2. Cấu hình OIDC user service

Gắn service vào `oauth2Login`:

~~~java
@Bean
SecurityFilterChain applicationSecurityFilterChain(
        HttpSecurity http,
        FederatedOidcUserService federatedOidcUserService)
        throws Exception {

    http
        .oauth2Login(oauth2 -> oauth2
            .userInfoEndpoint(userInfo -> userInfo
                .oidcUserService(federatedOidcUserService)
            )
        );

    return http.build();
}
~~~

Đây là phần cấu hình cho filter chain xử lý đăng nhập web. Trong ứng dụng có Spring Authorization Server, đặt cấu hình này vào application/login filter chain phù hợp với matcher và thứ tự của Authorization Server filter chain. Không tạo matcher chồng lấn khiến callback `/login/oauth2/code/*` bị filter chain khác bắt trước.

Trong mô hình dùng local subject, gắn thêm `LocalAccountAuthenticationSuccessHandler` như mục 6.2 để chuyển external `OAuth2AuthenticationToken` sang local authentication sau khi OIDC validation hoàn tất. Nếu bỏ bước này, Authorization Server vẫn có thể nhận external principal name.

## 6. Chuẩn hóa authentication thành local principal

Sau OIDC login, giữ external `OidcUser` như bằng chứng danh tính upstream và resolve local account. Không thay `getName()` hoặc `sub` của external `OidcUser` vì chúng phải tiếp tục mô tả đúng ID Token upstream. Sau callback, chuyển `Authentication` sang local principal để Authorization Server dùng local subject.

External OIDC user được bọc cùng local account để success handler có thể chuyển sang local principal sau khi OIDC flow hoàn tất:

~~~java
public final class FederatedLocalOidcUser implements OidcUser {

    private final OidcUser delegate;
    private final LocalAccount account;

    public FederatedLocalOidcUser(
            OidcUser delegate,
            LocalAccount account) {
        this.delegate = delegate;
        this.account = account;
    }

    @Override
    public String getName() {
        return this.delegate.getName();
    }

    @Override
    public Map<String, Object> getClaims() {
        return this.delegate.getClaims();
    }

    @Override
    public Map<String, Object> getAttributes() {
        return this.delegate.getAttributes();
    }

    @Override
    public OidcIdToken getIdToken() {
        return this.delegate.getIdToken();
    }

    @Override
    public OidcUserInfo getUserInfo() {
        return this.delegate.getUserInfo();
    }

    @Override
    public Collection<? extends GrantedAuthority> getAuthorities() {
        return this.account.authorities();
    }

    public LocalAccount account() {
        return this.account;
    }
}
~~~

`FederatedLocalOidcUser` giữ nguyên `getName()` và claims của IdP. Object này chỉ đính kèm local account để success handler có thể hoàn tất bước chuyển đổi.

### 6.1. Tạo principal nội bộ

Mọi phương thức đăng nhập local nên có principal thể hiện cùng một subject:

~~~java
public interface LocalSubjectPrincipal {
    String subject();
}

public record LocalAccountPrincipal(
        UUID accountId,
        String subject)
        implements AuthenticatedPrincipal, LocalSubjectPrincipal {

    @Override
    public String getName() {
        return this.subject;
    }
}
~~~

`AuthenticatedPrincipal.getName()` trả local subject. Có thể dùng `UsernamePasswordAuthenticationToken.authenticated(...)` để tạo authentication local với authorities lấy từ local account.

### 6.2. Chuyển OIDC authentication sang local authentication

Success handler nhận OIDC authentication đã xác minh, lấy local account đính kèm, rồi lưu một authentication local vào cùng SecurityContextRepository:

~~~java
@Component
public final class LocalAccountAuthenticationSuccessHandler
        implements AuthenticationSuccessHandler {

    private final SecurityContextRepository securityContextRepository;
    private final SavedRequestAwareAuthenticationSuccessHandler delegate =
        new SavedRequestAwareAuthenticationSuccessHandler();

    public LocalAccountAuthenticationSuccessHandler(
            SecurityContextRepository securityContextRepository) {
        this.securityContextRepository = securityContextRepository;
    }

    @Override
    public void onAuthenticationSuccess(
            HttpServletRequest request,
            HttpServletResponse response,
            Authentication authentication)
            throws IOException, ServletException {

        if (!(authentication instanceof OAuth2AuthenticationToken oauth2)
                || !(oauth2.getPrincipal() instanceof FederatedLocalOidcUser federated)) {
            throw new ServletException("Expected a federated OIDC principal");
        }

        LocalAccount account = federated.account();
        if (!account.enabled()) {
            SecurityContextHolder.clearContext();
            this.securityContextRepository.saveContext(
                SecurityContextHolder.createEmptyContext(), request, response
            );
            throw new ServletException("Local account is disabled");
        }

        Authentication localAuthentication =
            UsernamePasswordAuthenticationToken.authenticated(
                new LocalAccountPrincipal(account.id(), account.subject()),
                null,
                account.authorities()
            );

        SecurityContext context =
            SecurityContextHolder.createEmptyContext();
        context.setAuthentication(localAuthentication);
        SecurityContextHolder.setContext(context);

        this.securityContextRepository.saveContext(
            context, request, response
        );

        this.delegate.onAuthenticationSuccess(
            request, response, localAuthentication
        );
    }
}
~~~

Cấu hình application filter chain dùng cùng `SecurityContextRepository` cho security context và OAuth2 login:

~~~java
@Bean
SecurityContextRepository securityContextRepository() {
    return new HttpSessionSecurityContextRepository();
}

@Bean
SecurityFilterChain applicationSecurityFilterChain(
        HttpSecurity http,
        SecurityContextRepository securityContextRepository,
        FederatedOidcUserService federatedOidcUserService,
        LocalAccountAuthenticationSuccessHandler successHandler)
        throws Exception {

    http
        .securityContext(context -> context
            .securityContextRepository(securityContextRepository)
        )
        .oauth2Login(oauth2 -> oauth2
            .securityContextRepository(securityContextRepository)
            .userInfoEndpoint(userInfo -> userInfo
                .oidcUserService(federatedOidcUserService)
            )
            .successHandler(successHandler)
        );

    return http.build();
}
~~~

Success handler phải lưu context qua repository được dùng bởi filter chain. Nếu không lưu, local authentication có thể chỉ tồn tại trong request callback và biến mất ở request tiếp theo.

Spring Security lưu `OAuth2AuthorizedClient` theo registration và tên principal upstream trong quá trình OAuth2 login; repository mặc định có thể giữ token trong session. Nếu ứng dụng cần tiếp tục gọi API của IdP sau khi chuyển sang local principal, thiết kế nơi lưu và cách tải authorized client theo external identity riêng, đồng thời mã hóa token khi persist. Nếu không có nhu cầu đó, xóa authorized client sau khi hoàn tất federation hoặc dùng repository theo policy không lưu dài hạn; không giả định token tự biến mất chỉ vì ứng dụng không đọc nó.

### 6.3. Không làm mất quyền local

Local authorities phải lấy từ account/policy nội bộ. Không sao chép nguyên external authorities sang local authentication. Nếu cần group mapping, áp dụng allowlist ở service mapping trước khi tạo `LocalAccountPrincipal`.

Các principal cho password login, passkey hoặc SAML cũng nên dùng `LocalAccountPrincipal` hoặc triển khai cùng contract để Authorization Server luôn nhận local identity.

## 7. Resolve hoặc provision local account

External identity có thể đã được liên kết hoặc chưa. Quyết định tạo account mới phải dựa trên policy của issuer/tenant, không chỉ dựa trên việc người dùng có email.

### 7.1. Luồng resolve

~~~mermaid
flowchart TD
    START["OIDC authentication đã xác minh"] --> KEY["Tạo key (iss, sub)"]
    KEY --> LOOKUP{"External identity đã tồn tại?"}
    LOOKUP -->|Có| ACCOUNT["Tải local account"]
    LOOKUP -->|Không| POLICY{"Issuer được tin cậy và auto-provision được bật?"}
    POLICY -->|Không| LINK["Yêu cầu invitation hoặc account linking"]
    POLICY -->|Có| CREATE["Tạo local account theo tenant policy"]
    CREATE --> SAVE["Lưu external identity mapping"]
    SAVE --> ACCOUNT
    ACCOUNT --> ENABLED{"Account đang hoạt động?"}
    ENABLED -->|Không| DENY["Từ chối đăng nhập"]
    ENABLED -->|Có| PRINCIPAL["Tạo local principal"]
    PRINCIPAL --> END["Hoàn tất local authentication"]
~~~

Một implementation ở tầng domain có thể được diễn đạt như sau:

~~~java
@Transactional
public LocalAccount resolve(
        String issuer,
        String subject,
        String registrationId,
        ExternalProfile profile) {

    ProviderPolicy policy =
        providerPolicyService.requireTrustedIssuer(issuer, registrationId);

    Optional<ExternalIdentity> existing =
        externalIdentityRepository.findByIssuerAndSubject(
            issuer, subject
        );

    if (existing.isPresent()) {
        return accountService.requireEnabled(
            existing.get().accountId()
        );
    }

    if (!policy.autoProvisioningEnabled()) {
        throw new AccountLinkingRequiredException();
    }

    LocalAccount account =
        accountProvisioningService.provision(policy, profile);

    externalIdentityRepository.insert(
        ExternalIdentity.create(
            issuer,
            subject,
            account.id(),
            registrationId,
            profile.email(),
            profile.emailVerified()
        )
    );

    return account;
}
~~~

Đây là skeleton domain, cần bổ sung transaction boundary, exception translation, audit và xử lý race condition theo database đang sử dụng.

### 7.2. Auto-provisioning có điều kiện

Auto-provisioning có thể phù hợp khi tổ chức quản lý một corporate IdP và muốn người dùng đủ điều kiện có local account khi đăng nhập lần đầu.

Policy có thể yêu cầu:

- issuer nằm trong allowlist;
- registration thuộc tenant được cấp phép;
- account nằm trong nhóm hoặc organizational unit được phê duyệt;
- email được xác minh bởi IdP mà tổ chức tin cậy;
- invitation hoặc entitlement đã tồn tại;
- account chưa bị deprovision;
- provider đang ở trạng thái active.

Email domain như `example.com` có thể là một điều kiện phụ, nhưng không tự chứng minh người dùng được phép truy cập tenant. Người ngoài có thể có email cùng domain, hoặc domain có thể được dùng chung cho nhiều tổ chức.

### 7.3. Xử lý hai lần đăng nhập đầu tiên đồng thời

Hai callback đầu tiên của cùng một external identity có thể tới hai node gần như đồng thời. Cả hai request đều không tìm thấy mapping và cùng thử tạo account.

Ràng buộc unique trên `(issuer, subject)` là lớp bảo vệ cuối cùng. Khi xảy ra conflict:

1. Rollback transaction tạo account/link bị xung đột.
2. Đọc lại external identity trong transaction mới.
3. Dùng account đã được request còn lại tạo.
4. Không để account orphan trở thành account đăng nhập độc lập.

Có thể dùng insert-on-conflict hoặc distributed lock nếu database hỗ trợ. Không chỉ dựa vào bước kiểm tra tồn tại ở application vì nó không loại bỏ race condition.


## 8. Không tự động liên kết account bằng email

Đây là một trong những lỗi nguy hiểm nhất trong identity federation.

Giả sử local account đã tồn tại với email `alex@example.com`. Một người dùng đăng nhập từ IdP khác cũng nhận claim email này. Nếu hệ thống tự động gắn external identity mới vào account cũ, người dùng có thể chiếm quyền truy cập dữ liệu của account đó.

`email_verified=true` chỉ cho biết IdP xác nhận email theo chính sách của chính IdP. Nó không tự động chứng minh người dùng đang đăng nhập có quyền kiểm soát local account hiện tại hoặc local account đó thuộc cùng một người.

### 8.1. Quy tắc account linking an toàn

Khi external identity chưa được liên kết:

- Nếu account không tồn tại và policy cho phép auto-provision, tạo account mới.
- Nếu email trùng với local account đã có, không tự động liên kết.
- Nếu người dùng đang đăng nhập local account và muốn thêm IdP, yêu cầu xác thực lại local account.
- Xác thực người dùng với IdP mới trong một linking flow riêng.
- Xác nhận external identity chưa thuộc local account khác.
- Ghi audit event trước khi hoàn tất liên kết.

### 8.2. Linking flow

~~~mermaid
sequenceDiagram
    participant U as User
    participant APP as Local Application
    participant IDP as External IdP
    participant DB as Identity Store

    U->>APP: Đang đăng nhập local account A
    U->>APP: Chọn Link corporate identity
    APP->>APP: Xác thực lại và tạo linking state
    APP->>IDP: OIDC Authorization Request
    IDP-->>APP: Callback đã xác thực
    APP->>APP: Xác minh state, issuer và subject
    APP->>DB: Kiểm tra external identity chưa được link
    DB-->>APP: Chưa được liên kết
    APP->>DB: Gắn external identity vào account A
    APP-->>U: Thông báo liên kết thành công
~~~

Linking intent phải được gắn với local account và browser session đã xác thực. Không nhận account ID đích từ query parameter rồi tin trực tiếp.

Nếu external identity đã được liên kết với account B, không chuyển nó sang account A tự động. Cần quy trình unlink/move có xác minh quyền sở hữu account B hoặc quy trình quản trị đặc biệt.

### 8.3. Account merge là nghiệp vụ riêng

Nếu người dùng có hai local accounts và muốn gộp, việc merge cần đánh giá:

- quyền sở hữu dữ liệu và resource;
- tenant membership;
- consent và lịch sử authorization;
- subscription, billing hoặc ownership nghiệp vụ;
- refresh token, session và thiết bị;
- audit và quy định lưu trữ.

Không dùng account linking như một thao tác merge ngầm.

## 9. Phát hành local subject trong ID Token

Sau khi local principal đã được tạo, Spring Authorization Server cần phát hành ID Token có `sub` là local subject.

OIDC yêu cầu `sub` là định danh của End-User trong phạm vi issuer phát hành ID Token. Vì vậy, nếu local Authorization Server là issuer mà RP tin cậy, subject của token phải thuộc miền định danh local.

### 9.1. Bảo đảm principal name là local subject

`LocalAccountPrincipal.getName()` trả về local subject. Mọi authentication đi vào Authorization Endpoint cần có `Authentication.getName()` là local subject, không phải external `sub` hoặc email.

Để thể hiện rõ chính sách phát hành subject, có thể thêm `OAuth2TokenCustomizer<JwtEncodingContext>` cho ID Token:

~~~java
@Bean
OAuth2TokenCustomizer<JwtEncodingContext> localSubjectCustomizer() {
    return context -> {
        if (!OidcParameterNames.ID_TOKEN.equals(
                context.getTokenType().getValue())) {
            return;
        }

        Object principal = context.getPrincipal().getPrincipal();

        if (!(principal instanceof LocalSubjectPrincipal localPrincipal)) {
            throw new IllegalStateException(
                "ID Token requires a local subject principal"
            );
        }

        context.getClaims().subject(localPrincipal.subject());
    };
}
~~~

Customizer chỉ thay `sub` của ID Token. Nó không thay issuer, audience, nonce, thời gian phát hành hoặc chữ ký do token generator xử lý. Nếu ứng dụng hỗ trợ nhiều loại principal, hãy bảo đảm tất cả user authentication được chuyển thành local principal trước khi đi vào Authorization Endpoint.

Các ví dụ dùng API token customizer của Spring Authorization Server 1.5.x. Khi sử dụng Spring Security 7 tích hợp Authorization Server, kiểm tra package và dependency theo BOM đang dùng.

### 9.2. Không phát hành external subject như local subject

Không nên làm:

~~~java
context.getClaims().subject(externalIdToken.getSubject());
~~~

Cách này khiến RP nội bộ nhìn thấy định danh của upstream IdP. Khi đổi IdP, pairwise subject thay đổi hoặc liên kết thêm provider, danh tính người dùng ở phía RP sẽ thay đổi theo.

Hãy phát hành local subject đã lưu trong local account. External issuer/subject chỉ cần thiết trong identity store và audit nội bộ.

### 9.3. Public subject và pairwise subject ở local OP

OIDC định nghĩa public và pairwise subject types:

- Public subject cho cùng một subject tới các client.
- Pairwise subject tạo subject khác nhau theo sector để hạn chế các client liên kết hoạt động của cùng End-User.

Nếu triển khai public subject, dùng local `subject_id` ổn định. Nếu cần pairwise subject, tạo mapping riêng theo account và sector/sector identifier, lưu bền vững để subject không thay đổi khi secret hoặc thuật toán được xoay. Không dùng trực tiếp upstream pairwise subject làm local pairwise subject.

## 10. Tạo UserInfo response từ local account

Local Authorization Server nên trả UserInfo từ local account. Không chuyển nguyên UserInfo response của upstream IdP tới RP nội bộ.

Lý do:

- Upstream IdP có thể trả claim mà local RP không được phép nhận.
- Email hoặc tên từ IdP có thể khác dữ liệu local đã được xác minh.
- Scope/consent của local client có thể khác scope mà ứng dụng đã xin từ upstream.
- Local account có thể đã bị khóa hoặc thay đổi tenant membership.
- UserInfo `sub` phải khớp `sub` trong local ID Token.

### 10.1. UserInfo mapper

Spring Authorization Server cung cấp `OidcUserInfoEndpointConfigurer.userInfoMapper(...)`. Mapper nhận `OidcUserInfoAuthenticationContext` và có thể đọc authorization cùng token đã được xác thực.

Ví dụ:

~~~java
@Bean
Function<OidcUserInfoAuthenticationContext, OidcUserInfo>
        localUserInfoMapper(LocalAccountService accountService) {

    return context -> {
        OAuth2Authorization authorization =
            context.getAuthorization();

        OAuth2Authorization.Token<OidcIdToken> idTokenHolder =
            authorization.getToken(OidcIdToken.class);

        if (idTokenHolder == null) {
            throw new IllegalStateException(
                "Authorization does not contain an ID Token"
            );
        }

        String subject =
            idTokenHolder.getToken().getSubject();

        LocalAccount account =
            accountService.requireEnabledBySubject(subject);

        Set<String> scopes = authorization.getAuthorizedScopes();
        Map<String, Object> claims = new LinkedHashMap<>();

        claims.put("sub", subject);

        if (scopes.contains(OidcScopes.PROFILE)) {
            putIfPresent(claims, "name", account.displayName());
            putIfPresent(claims, "given_name", account.givenName());
            putIfPresent(claims, "family_name", account.familyName());
        }

        if (scopes.contains(OidcScopes.EMAIL)
                && account.email() != null) {
            claims.put("email", account.email());
            claims.put("email_verified", account.emailVerified());
        }

        return new OidcUserInfo(claims);
    };
}
~~~

Helper:

~~~java
private static void putIfPresent(
        Map<String, Object> claims,
        String name,
        String value) {

    if (value != null && !value.isBlank()) {
        claims.put(name, value);
    }
}
~~~

Gắn mapper vào Authorization Server OIDC configurer:

~~~java
authorizationServer.oidc(oidc ->
    oidc.userInfoEndpoint(userInfo ->
        userInfo.userInfoMapper(localUserInfoMapper)
    )
);
~~~

Đây là fragment tích hợp vào Authorization Server filter chain hiện có.

OIDC UserInfo Endpoint còn cần `JwtDecoder` bean để xác minh Bearer access token theo cấu hình Resource Server của Spring Authorization Server. Nếu endpoint trả lỗi xác thực dù mapper đúng, kiểm tra decoder, issuer/JWK và token audience.

### 10.2. Scope và claim phải nhất quán

Ví dụ:

| Scope đã cấp | Claim có thể trả |
| --- | --- |
| `openid` | `sub` |
| `profile` | `name`, `given_name`, `family_name`, `picture` nếu local profile có dữ liệu. |
| `email` | `email` và `email_verified` theo local verification state. |

Không trả tất cả claim chỉ vì upstream IdP đã cung cấp. Chỉ trả claim local được phép, tương ứng scope/consent của client và chính sách disclosure.

Trong UserInfo response, `sub` phải khớp chính xác subject của ID Token được phát hành trong authorization đó. Nếu account bị khóa sau khi token đã phát, mapper có thể từ chối hoặc giới hạn dữ liệu theo incident/session policy; không tự đổi subject.

## 11. Ánh xạ authority và role từ IdP

External IdP có thể trả OAuth scopes, group claims, application roles, tenant/organization claims hoặc authentication context như `acr` và `amr`. Các giá trị này không mặc nhiên là quyền nội bộ.

### 11.1. Dùng local roles làm nguồn chuẩn

Một lựa chọn an toàn là principal local chỉ chứa authorities lấy từ local account:

~~~java
@Override
public Collection<? extends GrantedAuthority> getAuthorities() {
    return this.account.authorities();
}
~~~

Spring Security dùng authorities trong `OAuth2AuthenticationToken` khi thực hiện authorization tại application. Do đó, nếu wrapper trả authorities từ local account, policy nội bộ không phụ thuộc trực tiếp vào chuỗi group do IdP gửi.

### 11.2. Nếu cần map group claim

Dùng bảng mapping có allowlist:

| Issuer | External group | Local authority | Tenant |
| --- | --- | --- | --- |
| Corporate IdP | `finance-readers` | `ROLE_FINANCE_VIEWER` | `tenant-a` |
| Corporate IdP | `finance-approvers` | `ROLE_FINANCE_APPROVER` | `tenant-a` |
| Partner IdP | `support-agents` | `ROLE_SUPPORT_AGENT` | `tenant-b` |

Không map mọi giá trị group thành `ROLE_ + group`. Một IdP bị cấu hình sai hoặc bị xâm nhập có thể gửi group tên `admin` và nhận quyền quản trị nếu ứng dụng tin trực tiếp.

Quy trình mapping:

1. Xác định issuer đã được tin cậy.
2. Lấy group claim từ ID Token/UserInfo đã xác minh.
3. Chuẩn hóa theo policy provider cụ thể.
4. Tìm mapping được quản trị viên phê duyệt.
5. Kiểm tra tenant membership.
6. Tạo local authorities từ mapping.
7. Ghi audit nếu quyền nhạy cảm được cấp hoặc bị thay đổi.

### 11.3. Không nhầm scope upstream với role local

Scope `openid profile email` chỉ phục vụ OIDC authentication và claim retrieval. Chúng không phải role nội bộ. Một access token upstream có scope `admin-api` cũng không có nghĩa local account được phép có `ROLE_ADMIN`.

Nếu hệ thống cần chứng minh authentication assurance, có thể ánh xạ `acr`/`amr` theo policy đã cấu hình và kiểm tra `auth_time`. Không tự nâng mức xác thực chỉ dựa vào một chuỗi claim mà issuer không được phép phát hành.

## 12. Tenant mapping và ranh giới dữ liệu

Một hệ thống multi-tenant phải xác định account thuộc tenant nào. Không suy luận tenant chỉ từ email domain hoặc query parameter.

Có thể dùng:

- issuer riêng cho mỗi tenant;
- provider policy gắn registration với tenant;
- tenant claim đã được xác minh và allowlist;
- invitation/organization membership local;
- quy trình admin phê duyệt.

Nếu một issuer phục vụ nhiều tenant, local account có thể có nhiều tenant memberships. External identity mapping vẫn nhận diện bằng issuer và subject; tenant membership là quan hệ nghiệp vụ riêng.

Ví dụ:

~~~text
External identity (issuer, subject)
              |
              v
        Local account
              |
              +---- Tenant A membership
              |
              +---- Tenant B membership
~~~

Khi người dùng đăng nhập, hệ thống phải xác định tenant context trước khi cấp quyền. Nếu tenant context do client yêu cầu, kiểm tra người dùng thực sự có membership trong tenant đó.

Không thêm tenant ID do browser gửi vào identity key để làm cho một external identity giả thành nhiều người dùng. Nếu upstream issuer có realm path riêng, chính issuer đầy đủ đã phân biệt realm.


## 13. Vòng đời liên kết danh tính

Identity mapping cần được quản lý như một phần của vòng đời account.

### 13.1. Link thêm IdP

- Người dùng đang đăng nhập vào local account.
- Yêu cầu xác thực lại theo mức bảo đảm phù hợp.
- Khởi tạo OIDC flow với state/nonce gắn với linking intent.
- Xác minh external ID Token.
- Kiểm tra external identity chưa thuộc account khác.
- Lưu mapping và audit.

### 13.2. Unlink IdP

Trước khi unlink:

- kiểm tra account còn phương thức đăng nhập khác;
- yêu cầu xác thực lại;
- kiểm tra external identity có phải phương thức duy nhất hay không;
- vô hiệu hóa authorized client/session upstream nếu cần;
- ghi audit và thông báo cho người dùng.

Không để người dùng tự unlink phương thức duy nhất rồi mất khả năng truy cập account mà không có quy trình recovery.

### 13.3. IdP deprovisioning

Khi nhân viên nghỉ việc hoặc bị thu hồi quyền ở IdP, local system cần có cơ chế đồng bộ:

- SCIM hoặc provisioning event nếu tổ chức hỗ trợ;
- scheduled reconciliation;
- webhook đã xác thực;
- kiểm tra trạng thái account/entitlement theo policy.

Không giả định việc người dùng không đăng nhập trong một khoảng thời gian đồng nghĩa account đã bị xóa. Khi nhận deprovision event, disable local account, revoke sessions/tokens theo policy và lưu audit.

### 13.4. Issuer hoặc subject thay đổi

Nếu IdP đổi issuer, realm hoặc subject format:

1. Xác định danh tính cũ và mới bằng quy trình migration tin cậy.
2. Yêu cầu re-authentication với IdP mới.
3. Xác minh quyền truy cập local account hiện tại.
4. Tạo mapping mới vào account cũ.
5. Giữ lịch sử mapping cũ theo retention/audit.
6. Không tự merge bằng email.

OIDC yêu cầu issuer giữ subject ổn định và không tái gán, nhưng migration giữa các issuer vẫn là một sự kiện cần xử lý rõ ràng.

## 14. Các kiểm soát bảo mật quan trọng

### 14.1. Trust boundary của IdP

Chỉ tin issuer đã được cấu hình. Discovery metadata và JWKS phải được lấy từ endpoint tin cậy. Không chấp nhận issuer do người dùng cung cấp hoặc token ký bởi key không thuộc issuer đã đăng ký.

### 14.2. State, nonce và authorization response

Giữ nguyên các kiểm tra do Spring Security OAuth2 Login thực hiện:

- state gắn với authorization request;
- nonce trong OIDC;
- redirect URI đã đăng ký;
- authorization code flow và token response validation;
- ID Token issuer, audience, signature và thời gian;
- UserInfo subject consistency.

Không tự viết callback đơn giản chỉ nhận `code` rồi gọi token endpoint mà bỏ các validation này.

### 14.3. Email và profile claims

- Không dùng email làm identity key.
- Chỉ cập nhật email local theo policy issuer và trạng thái verified.
- Không tự động thay email đã xác minh local bằng claim chưa xác minh.
- Không tin `preferred_username` là username duy nhất.
- Không render HTML từ profile claim.
- Giới hạn độ dài, ký tự và định dạng dữ liệu.

### 14.4. Session và token lifecycle

Khi local account bị disable hoặc external identity bị unlink:

- ngăn login mới;
- thu hồi local session theo policy;
- revoke refresh token/authorization khi cần;
- xem xét token opaque/introspection và JWT offline validation khác nhau thế nào;
- cập nhật cache account status;
- phát audit event.

Với JWT được Resource Server xác minh offline, thay đổi trạng thái account trong database không tự động làm JWT đã phát hành mất hiệu lực. Dùng TTL ngắn, introspection, denylist hoặc security epoch tùy yêu cầu.

### 14.5. Không lưu upstream token nếu không cần

Nếu chỉ cần xác thực và lấy profile tại thời điểm login, không lưu upstream access/refresh token dài hạn. Nếu cần gọi API IdP sau login:

- lưu authorized client qua Spring Security;
- mã hóa token ở persistence layer;
- giới hạn quyền đọc token;
- đặt refresh/revocation lifecycle;
- không đưa token upstream vào local access token;
- không log bearer token.

## 15. Kiểm thử identity mapping

Cần kiểm thử cả mapping service và toàn bộ OIDC login flow.

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| Cặp issuer/subject đã liên kết | Resolve đúng local account hiện tại. |
| Cùng subject nhưng issuer khác | Tạo external identity khác, không gộp account. |
| Email giống nhau ở hai issuer | Không tự động liên kết. |
| Email thay đổi nhưng issuer/subject không đổi | Vẫn resolve đúng local account. |
| Subject khác nhưng email giống nhau | Không coi là cùng external identity. |
| Issuer không nằm trong allowlist | Từ chối login. |
| ID Token sai issuer/audience/signature/nonce | OIDC authentication thất bại. |
| Account local bị disable | Từ chối login dù upstream authentication thành công. |
| External identity chưa liên kết, auto-provision tắt | Yêu cầu linking/invitation. |
| External identity chưa liên kết, auto-provision được phép | Tạo local account theo policy. |
| Hai callback đầu tiên đồng thời | Chỉ có một mapping cho issuer/subject. |
| External identity đã thuộc account khác | Từ chối linking. |
| User cố link IdP bằng email trùng | Không tự động gắn vào account hiện có. |
| Group claim chứa admin không được allowlist | Không cấp local admin role. |
| Tenant claim không hợp lệ | Không cấp tenant membership. |
| Local ID Token được phát hành | `sub` là local subject. |
| UserInfo response | `sub` khớp local ID Token và claims theo scope. |
| Account bị disable sau khi token được cấp | Session/token được xử lý theo revocation policy. |
| IdP bị deprovision | Không cho đăng nhập mới; session/token được xử lý theo policy. |
| Issuer migration | Mapping mới chỉ được liên kết qua quy trình xác minh. |

### 15.1. Unit test cho identity key

Tối thiểu cần xác nhận:

~~~java
assertNotEquals(
    new ExternalIdentityKey("https://idp-a.example.com", "user-1"),
    new ExternalIdentityKey("https://idp-b.example.com", "user-1")
);

assertNotEquals(
    new ExternalIdentityKey("https://idp-a.example.com", "User-1"),
    new ExternalIdentityKey("https://idp-a.example.com", "user-1")
);
~~~

Test này giúp phát hiện code vô tình lowercase subject hoặc bỏ issuer khi tạo key.

### 15.2. Integration test cho local subject

1. Tạo external IdP test với issuer và subject cố định.
2. Đăng nhập qua Spring Security OIDC client.
3. Xác nhận external identity được lưu và local account được resolve.
4. Gửi authorization request tới local Authorization Server.
5. Đổi authorization code lấy ID Token.
6. Decode và xác minh chữ ký ID Token local.
7. Kiểm tra `iss` là issuer local và `sub` là local subject.
8. Gọi local UserInfo Endpoint bằng access token.
9. Kiểm tra UserInfo `sub` khớp chính xác ID Token `sub`.
10. Thay email upstream và đăng nhập lại; local subject phải giữ nguyên.

## 16. Quan sát và vận hành

Các event hữu ích:

| Event/metric | Mục đích |
| --- | --- |
| Federation login success/failure | Theo dõi chất lượng login theo issuer. |
| Unknown external identity | Phát hiện user mới cần provision/link. |
| Account provisioning success/failure | Theo dõi onboarding. |
| Account linking/unlinking | Audit thay đổi phương thức đăng nhập. |
| Disabled account login attempt | Phát hiện IdP/local lifecycle không đồng bộ. |
| External group mapping change | Kiểm soát thay đổi quyền. |
| Issuer validation failure | Phát hiện sai cấu hình hoặc token không tin cậy. |
| Duplicate identity conflict | Phát hiện callback đồng thời hoặc dữ liệu bất nhất. |
| Upstream token refresh failure | Theo dõi authorized client nếu cần gọi API IdP. |

Log issuer và registration ID ở mức phù hợp, local account ID nội bộ hoặc correlation ID. Tránh log raw ID Token, access token, refresh token, client secret, email không cần thiết hoặc toàn bộ claim set.

Với nhiều Authorization Server instances:

- dùng external identity store và local account database dùng chung;
- bảo đảm unique constraint được áp dụng ở database;
- chia sẻ session store nếu session cần hoạt động trên nhiều node;
- đồng bộ provider policy và group mapping;
- invalidate cache khi account bị disable hoặc identity bị unlink;
- giám sát discovery/JWKS upstream và thời hạn key rotation.

## 17. Các lỗi thường gặp

### 17.1. Dùng email làm khóa identity

Khi email thay đổi hoặc được tái sử dụng, hệ thống có thể gộp nhầm hai người dùng. Dùng issuer và subject.

### 17.2. Dùng registration ID làm identity key

Registration ID là cấu hình local, có thể đổi và có thể có nhiều registration trỏ tới cùng issuer. Lấy issuer từ ID Token đã xác minh.

### 17.3. Dùng external subject làm local subject

RP nội bộ sẽ bị phụ thuộc vào IdP và pairwise subject upstream. Phát hành subject từ local account.

### 17.4. Chỉ đổi subject trong ID Token nhưng quên UserInfo

UserInfo `sub` phải khớp ID Token `sub`. Cấu hình local UserInfo mapper cùng chính sách local subject.

### 17.5. Trả raw upstream claims cho RP

Có thể làm lộ claim vượt quá consent hoặc khác với profile local. Dùng UserInfo mapper và authorized scopes.

### 17.6. Tin group claim như local role

Một claim group do IdP gửi không tự động tương đương role local. Dùng mapping allowlist có tenant scope.

### 17.7. Auto-link bằng email_verified

Verified email không thay thế bằng chứng người dùng sở hữu local account. Yêu cầu local re-authentication và linking flow.

### 17.8. Hai login đầu tiên tạo hai local accounts

Thiếu unique constraint hoặc xử lý conflict. Đặt unique issuer/subject và retry/reload sau transaction conflict.

### 17.9. Account bị disable nhưng vẫn đăng nhập được

Chỉ kiểm tra upstream authentication mà không kiểm tra local account status. Kiểm tra trạng thái local ở mỗi lần federation login và áp dụng deprovision policy.

### 17.10. Thay issuer mà không migration mapping

Cùng subject dưới issuer mới là external identity khác. Dùng quy trình re-link/migration có xác minh.

## 18. Checklist triển khai

- [ ] Chỉ cấu hình issuer đã được tổ chức tin cậy.
- [ ] Dùng OIDC Authorization Code flow và giữ state/nonce validation.
- [ ] External identity key là cặp issuer và subject từ ID Token đã xác minh.
- [ ] Issuer và subject được so sánh chính xác, phân biệt chữ hoa/chữ thường.
- [ ] Registration ID chỉ dùng để chọn provider/configuration.
- [ ] Local account có khóa nội bộ riêng.
- [ ] Local subject opaque, ổn định và không bao giờ tái sử dụng.
- [ ] Có unique constraint cho external issuer/subject.
- [ ] Có foreign key từ external identity tới local account.
- [ ] OidcUserService delegate implementation mặc định trước khi resolve local account.
- [ ] Local principal trả getName() là local subject.
- [ ] Mọi authentication method khác cũng được chuẩn hóa thành local principal.
- [ ] ID Token local phát hành local `sub`.
- [ ] UserInfo local trả `sub` khớp ID Token.
- [ ] UserInfo chỉ trả claim được phép theo scope/consent.
- [ ] Không dùng email hoặc preferred_username làm identity key.
- [ ] Không auto-link account hiện có chỉ vì email trùng.
- [ ] Linking yêu cầu re-authentication và linking intent gắn với session.
- [ ] Auto-provisioning có issuer/tenant/invitation policy.
- [ ] Group/role mapping có allowlist và tenant boundary.
- [ ] Account disabled/deprovisioning được áp dụng cho session/token.
- [ ] Có xử lý callback đồng thời và unique constraint conflict.
- [ ] Có audit cho link, unlink, provision và deprovision.
- [ ] Upstream tokens được lưu an toàn và chỉ khi thực sự cần.
- [ ] Có test cho nhiều issuer, subject case, email collision và subject migration.
- [ ] Có integration test chứng minh local ID Token và UserInfo dùng cùng subject.

**Ghi nhớ:** IdP xác thực external identity; local system quyết định account và quyền nội bộ. Hãy lưu external identity bằng cặp issuer/subject, liên kết nó với local account, rồi phát hành local subject ổn định cho RP. Email và group claim là dữ liệu đầu vào cần policy, không phải định danh hoặc quyền nội bộ mặc định.

## 19. Tài liệu tham khảo

- [OpenID Connect Core 1.0 — ID Token và Subject Stability](https://openid.net/specs/openid-connect-core-1_0.html): `iss`, `sub`, claim stability/uniqueness và subject identifier types.
- [Spring Security — Advanced OAuth2 Login Configuration](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html): `OidcUserService`, `OAuth2UserService`, authority mapping và OIDC login extension points.
- [Spring Authorization Server — Core Model / Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): `OAuth2TokenCustomizer`, `JwtEncodingContext` và token generation.
- [Spring Authorization Server — How-to: Customize the OpenID Connect 1.0 UserInfo response](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-userinfo.html): `OidcUserInfoAuthenticationContext` và `userInfoMapper`.
- [Spring Authorization Server — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): cấu hình UserInfo Endpoint và các extension points.
- [Spring Security — OAuth2 Client](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html): client registration, authorized client và tích hợp OAuth2/OIDC client.
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519.html): cấu trúc JWT và claim semantics.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700.html): các thực hành bảo mật OAuth 2.0 hiện hành.



