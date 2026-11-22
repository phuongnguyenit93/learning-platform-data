# Cấp claims nội bộ từ danh tính bên ngoài theo chính sách

## 1. Vì sao phải ánh xạ danh tính liên kết?

Một Authorization Server nội bộ có thể dựa vào Identity Provider (IdP) bên ngoài để xác thực người dùng: nhà cung cấp danh tính của doanh nghiệp, đối tác hoặc một OpenID Provider khác. IdP bên ngoài xác thực người dùng và trả về ID Token cùng các claims như **sub**, **email**, **groups**, **department** hoặc **acr**.

Authorization Server nội bộ vẫn phải tự quyết định danh tính nội bộ nào đang đăng nhập, người đó thuộc tenant nào, có vai trò gì và client được nhận những claims nào. Claims bên ngoài là dữ liệu đầu vào từ một trust domain khác. Chúng cần được xác minh, liên kết với tài khoản nội bộ và chuyển đổi theo chính sách trước khi dùng để cấp token.

Bài thuộc chương **Liên kết danh tính** của module **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER**. Nội dung tập trung vào federated login qua OpenID Connect, ánh xạ claims bên ngoài thành identity/authority nội bộ, rồi phát hành ID Token, access token và UserInfo từ Spring Authorization Server 1.5.8.

Bài này nói về **federated authentication và claim transformation** tại runtime. Đây không phải hướng dẫn triển khai OpenID Federation 1.0 trust framework với Entity Statement, Trust Mark hay Federation Operator.

Sau bài học, bạn có thể:
1. Phân biệt upstream IdP, downstream Authorization Server, client và Resource Server.
2. Hiểu luồng OIDC Login khi Authorization Server dùng IdP bên ngoài để xác thực người dùng.
3. Dùng cặp issuer/subject để liên kết external identity với internal account.
4. Xây dựng chính sách cho phép, chuẩn hóa, ánh xạ và từ chối claims.
5. Dùng Spring Security OidcUserService để liên kết người dùng và tạo principal nội bộ.
6. Ánh xạ external groups thành internal authorities theo allowlist.
7. Cấp claims nội bộ vào ID Token, access token và UserInfo bằng extension points của Spring Authorization Server.
8. Bảo vệ tenant isolation, account linking, claim freshness và dữ liệu cá nhân.
9. Kiểm thử cả quá trình xác thực upstream, mapping và token issuance.

## 2. Các vai trò trong mô hình liên kết danh tính

| Thành phần | Vai trò | Dữ liệu chịu trách nhiệm |
| --- | --- | --- |
| **Upstream Identity Provider** | Xác thực người dùng bên ngoài | ID Token, UserInfo và claims nguồn |
| **Spring Authorization Server nội bộ** | Đóng vai trò downstream OP/AS cho hệ thống nội bộ | Internal subject, tenant, roles, entitlements và token nội bộ |
| **OAuth2/OIDC Client** | Yêu cầu đăng nhập và nhận token từ AS nội bộ | Claims được AS nội bộ phát hành |
| **Resource Server** | Xác minh access token nội bộ và áp dụng authorization | Audience, scopes và internal authorization claims |
| **Internal Identity Directory** | Nguồn dữ liệu danh tính và quyền nội bộ | Account status, tenant membership, roles, profile và policy |

Upstream IdP trả lời câu hỏi: “Người dùng đã được xác thực ở trust domain bên ngoài nào?”. Internal Identity Directory trả lời câu hỏi: “Người dùng đó là tài khoản nội bộ nào và hiện được phép làm gì?”.

Không nên để upstream IdP quyết định toàn bộ quyền nội bộ chỉ bằng một claim groups hoặc roles. AS nội bộ cần có chính sách riêng để xác định dữ liệu nào được tin cậy, cách chuyển đổi và phạm vi phát hành.

## 3. Luồng xác thực và phát hành token

~~~mermaid
sequenceDiagram
    autonumber
    participant U as Browser / User
    participant C as Internal Client
    participant AS as Internal Authorization Server
    participant IDP as External OIDC Provider
    participant DIR as Internal Identity Directory

    C->>AS: Authorization Request
    AS->>AS: No local authenticated session
    AS-->>U: Redirect to upstream IdP
    U->>IDP: OIDC Authorization Request
    IDP-->>U: Redirect with authorization code
    U->>AS: Callback with code
    AS->>IDP: Token Request
    IDP-->>AS: ID Token + Access Token
    AS->>AS: Validate upstream ID Token
    AS->>IDP: UserInfo request (if configured)
    IDP-->>AS: External claims
    AS->>DIR: Resolve (issuer, registration, subject)
    DIR-->>AS: Internal account + policy + authorities
    AS->>AS: Establish internal authenticated session
    AS-->>C: Authorization code
    C->>AS: Token Request
    AS->>AS: Build claims from internal policy
    AS-->>C: Internal ID Token + Access Token
~~~

Trình tự chính:

1. Client gửi Authorization Request tới Authorization Server nội bộ.
2. Nếu chưa có local authenticated session, Spring Security chuyển browser tới upstream IdP qua OIDC Login.
3. AS nhận authorization code từ upstream IdP và đổi code lấy token.
4. Spring Security xác minh ID Token theo cấu hình Client Registration và có thể gọi UserInfo Endpoint.
5. OidcUserService nhận external identity, tra cứu hoặc provision tài khoản nội bộ theo policy.
6. AS tạo một local authenticated principal gắn với internal account và authorities.
7. Spring Authorization Server tiếp tục Authorization Code flow cho client nội bộ.
8. Khi đổi code lấy token, AS phát hành token mới với issuer, subject và claims thuộc trust domain nội bộ.

**ID Token của upstream không được chuyển nguyên trạng cho client nội bộ.** Token đó có issuer và audience dành cho client registration của AS nội bộ tại upstream IdP. AS nội bộ phải phát hành ID Token mới theo issuer và subject của chính mình.

Upstream access token là credential mà AS nội bộ dùng để gọi API của upstream IdP theo quyền đã cấp. Không chuyển token này cho client nội bộ như access token của hệ thống. Nếu downstream cần truy cập tài nguyên thay mặt người dùng ở upstream, thiết kế delegation/token exchange riêng với audience, scope và consent rõ ràng.

## 4. Phân biệt external claims và internal claims

External claims mô tả điều upstream IdP biết hoặc khẳng định. Internal claims mô tả quyết định danh tính và authorization mà AS nội bộ chịu trách nhiệm.

| Nhóm | Ví dụ | Nguồn có thể tin cậy | Cách sử dụng |
| --- | --- | --- | --- |
| External identity | iss, sub | ID Token đã được xác minh | Liên kết external identity |
| Contact/profile | email, email_verified, name, locale | IdP theo trust policy | Gợi ý hoặc đồng bộ profile |
| External organization | groups, department, organization | IdP/Directory ngoài | Chuyển đổi qua mapping policy |
| Authentication context | acr, amr, auth_time | IdP nếu semantics đã được thỏa thuận | Đánh giá assurance theo policy xác thực |
| Internal identity | sub, internal_user_id | Internal Identity Directory | Định danh người dùng trong AS nội bộ |
| Internal authorization | roles, tenant_id, entitlements | Internal policy engine/directory | Cấp quyền cho client và Resource Server |
| Account lifecycle | account_status, disabled_at | Internal account system | Chặn đăng nhập/cấp token |

Một claim có cùng tên không có nghĩa có cùng ngữ nghĩa. Ví dụ, groups từ IdP bên ngoài không tự động tương đương roles của hệ thống nội bộ. Department không nhất thiết là tenant. email_verified=true chỉ là assertion của issuer; AS nội bộ phải quyết định có chấp nhận assertion đó cho mục đích cụ thể hay không.

## 5. Định danh external identity bằng issuer và subject

Với OIDC, định danh ổn định của người dùng tại một issuer là cặp:

~~~text
external_identity = (issuer, subject)
                  = (iss, sub)
~~~

OIDC Core quy định sub là định danh duy nhất trong phạm vi issuer và không được tái cấp cho người dùng khác. Cặp iss và sub là định danh ổn định mà Relying Party có thể dựa vào. Các claims như email, phone number, preferred username và name không có bảo đảm ổn định hoặc duy nhất tương tự.

Không dùng email làm khóa chính để tự động liên kết tài khoản. Email có thể thay đổi, được tái sử dụng hoặc xuất hiện ở nhiều trust domain. Ngay cả khi email_verified=true, email vẫn là thuộc tính liên hệ, không phải external subject identifier.

### 5.1. Pairwise subject và nhiều Client Registration

Một số IdP dùng pairwise subject identifier: cùng một người dùng có thể nhận sub khác nhau đối với các client hoặc sector khác nhau. Vì vậy, nếu AS nội bộ cấu hình nhiều upstream Client Registration tới cùng một issuer, khóa liên kết cần giữ thêm ngữ cảnh registration/sector.

Ví dụ schema:

~~~text
external_identity
-----------------
id
issuer
subject_scope_key
upstream_registration_id
subject
internal_user_id
linked_at
link_method
status
UNIQUE(issuer, subject_scope_key, subject)
~~~

Nếu issuer dùng public subject, subject_scope_key có thể là giá trị cố định như public; cặp (iss, sub) vẫn là định danh OIDC. Với pairwise subject, subject_scope_key là sector identifier tương ứng. Registration ID vẫn hữu ích cho audit và tra cứu cấu hình, nhưng các registration cùng sector có thể chia sẻ cùng một subject identity; không tạo khóa khác nhau chỉ vì chúng có registration ID khác nhau.

Không chuẩn hóa iss bằng cách bỏ path, đổi chữ hoa/thường hoặc xóa dấu slash tùy tiện. So sánh issuer theo giá trị đã được cấu hình và xác minh; issuer là giá trị phân biệt chữ hoa/thường.

### 5.2. Internal subject phải do AS nội bộ quản lý

AS nội bộ cần một internal user ID ổn định, ví dụ UUID hoặc opaque identifier. ID Token nội bộ nên dùng internal subject này làm sub, theo policy subject identifier của AS.

Không sao chép external sub thành local sub theo mặc định. Làm như vậy sẽ để lộ định danh của upstream IdP, gây xung đột giữa issuer và làm khó việc hợp nhất nhiều nguồn danh tính.

## 6. Liên kết tài khoản và Just-in-Time Provisioning

Khi người dùng đăng nhập lần đầu từ một IdP, AS cần quyết định có thể liên kết external identity với internal account theo cách nào.

| Chiến lược | Cách hoạt động | Điều kiện kiểm soát |
| --- | --- | --- |
| Pre-provisioned linking | Quản trị viên liên kết external identity với internal account trước | Phù hợp workforce/partner có quy trình onboarding |
| Just-in-Time (JIT) provisioning | Tạo internal account khi người dùng đăng nhập lần đầu | Chỉ bật cho issuer, domain, tenant và profile được allowlist |
| Explicit account linking | Người dùng đã đăng nhập tài khoản nội bộ và xác thực thêm external identity | Cần re-authentication/step-up và audit |
| Directory synchronization | Đồng bộ account và group từ hệ thống nguồn qua SCIM hoặc connector | Có quy trình xử lý disable, rename, transfer và deletion |

JIT provisioning không đồng nghĩa với tự động gắn external identity vào tài khoản hiện có bằng email. Nếu không tìm thấy external identity đã liên kết:
- Nếu policy yêu cầu pre-provisioning, từ chối đăng nhập và hướng dẫn onboarding.
- Nếu JIT được phép, tạo account nội bộ mới trong tenant được xác định từ nguồn tin cậy.
- Nếu có ứng viên internal account trùng email, yêu cầu quy trình account linking đã xác minh.
- Nếu issuer không nằm trong allowlist, từ chối trước khi tạo account.

Khi liên kết hai tài khoản, cần xác thực quyền kiểm soát cả tài khoản nội bộ và external identity. Không cho một người đã kiểm soát email của người khác tự gắn IdP của mình vào account chỉ bằng một email claim.

## 7. Thiết kế Claim Mapping Policy

Claim mapping nên là policy có version và có thể audit, thay vì một loạt câu lệnh if rải rác trong controller.

Một policy cần xác định:

1. **Issuer allowlist:** issuer nào được phép cung cấp danh tính.
2. **Client registration:** upstream registration nào được dùng và sector/tenant nào tương ứng.
3. **Source claims:** claim nào được đọc từ ID Token hoặc UserInfo.
4. **Trust level:** claim có được xác minh, có freshness ra sao và issuer có được phép khẳng định nó không.
5. **Transformation:** chuẩn hóa kiểu dữ liệu, tên, mã nhóm, locale và giá trị.
6. **Target claim:** thuộc tính nội bộ nào được cập nhật hoặc tạo ra.
7. **Conflict resolution:** khi external claim khác dữ liệu nội bộ, nguồn nào có quyền ưu tiên.
8. **Authorization mapping:** group/attribute nào có thể tạo internal role hoặc entitlement.
9. **Release policy:** client nào được nhận claim nào, theo scope và purpose nào.
10. **Lifecycle:** claim được làm mới, thu hồi hoặc hết hiệu lực như thế nào.

### 7.1. Ví dụ ma trận mapping

| External claim | Điều kiện chấp nhận | Internal representation | Quy tắc |
| --- | --- | --- | --- |
| iss + sub | ID Token hợp lệ, issuer allowlisted | external_identity link | Không thay bằng email |
| email | Issuer được tin cậy và giá trị hợp lệ | contact_email | Không dùng làm primary key |
| email_verified | Issuer có semantics được thỏa thuận | contact_email_verified | Không tự nâng quyền |
| groups | Group ID nằm trong allowlist | internal_roles | Mapping theo issuer + group ID |
| department | Mã phòng ban được directory công nhận | org_unit_id | Không tự suy ra tenant |
| tenant / organization | Mã được ánh xạ tới tenant nội bộ | tenant_membership | Kiểm tra membership nội bộ |
| acr / amr | Issuer và semantics đã được đánh giá | authentication_assurance | Chỉ dùng trong policy xác thực |
| name | Claim hợp lệ | display_name | Dữ liệu profile, không dùng authorization |

### 7.2. Thứ tự ưu tiên khi claims xung đột

Có thể áp dụng thứ tự ưu tiên:

~~~text
Internal security policy / account state
              |
Internal identity directory
              |
Approved federation mapping
              |
Verified upstream profile claims
              |
Unverified / unknown external claims
~~~

Internal account status, tenant membership, roles và entitlements phải được quyết định bởi nguồn nội bộ có thẩm quyền. External IdP chỉ được phép cập nhật các thuộc tính đã được giao quyền rõ ràng. Claim không nằm trong mapping policy phải bị bỏ qua hoặc làm request thất bại tùy mức độ quan trọng.

Không ghi đè giá trị nội bộ chỉ vì upstream IdP gửi cùng tên claim. Ví dụ, nếu tenant_id nội bộ được quản lý bởi hệ thống provisioning, không lấy tenant_id từ request hoặc external claim để thay thế.

## 8. Ánh xạ external groups thành internal authorities

External group thường có cấu trúc riêng theo IdP: tên nhóm, object ID, DN hoặc URI. Internal application lại có roles/permissions riêng. Cần một bảng mapping tường minh:

~~~text
federation_group_mapping
------------------------
issuer
upstream_registration_id
external_group_id
internal_role
policy_version
enabled
UNIQUE(issuer, upstream_registration_id, external_group_id, internal_role)
~~~

Ví dụ:

| Issuer | External group ID | Internal role |
| --- | --- | --- |
| https://idp.corp.example | grp-finance-readers | FINANCE_VIEWER |
| https://idp.corp.example | grp-order-approvers | ORDER_APPROVER |
| https://partner-id.example | p-ops-01 | PARTNER_OPERATIONS |

Không chuyển trực tiếp một giá trị admin, superuser hoặc ROLE_ADMIN từ upstream claim thành quyền quản trị nội bộ. Mapping cần dựa trên issuer, registration, group ID và trạng thái được phê duyệt. Group bị xóa hoặc disabled phải dẫn tới cập nhật authority nội bộ theo SLA đã đặt.

Nếu upstream group claim quá lớn hoặc không phù hợp đưa vào token, dùng SCIM/directory synchronization để lưu membership ở nội bộ. Trong quá trình đăng nhập, chỉ đọc các membership nội bộ đã được đồng bộ và kiểm tra trạng thái hiện tại.

## 9. Cấu hình Spring Security làm OIDC Client tới upstream IdP

Spring Authorization Server xử lý protocol endpoints, còn Spring Security xử lý đăng nhập người dùng. Có thể cấu hình OIDC Login trên security filter chain dành cho ứng dụng web nội bộ.

Ví dụ cấu hình external IdP:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corporate:
            provider: corporate
            client-id: ${CORPORATE_IDP_CLIENT_ID}
            client-secret: ${CORPORATE_IDP_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
        provider:
          corporate:
            issuer-uri: https://idp.corp.example
~~~

issuer-uri cho phép Spring Security khám phá metadata của upstream provider. Client ID, secret, redirect URI và scopes phải khớp với cấu hình đã đăng ký tại IdP. Chỉ yêu cầu các scopes cần cho claim mapping; không yêu cầu quyền đọc groups hoặc dữ liệu nhạy cảm nếu policy không cần.

Hai giá trị client ID và client secret trong ví dụ là chỗ đặt cấu hình được cấp từ secret manager hoặc environment-specific configuration. Không lưu raw secret trong Git. Redirect URI được render từ base URL của ứng dụng và registration ID; reverse proxy phải chuyển tiếp scheme/host chính xác để callback khớp URI đã đăng ký ở upstream IdP.

Ví dụ security filter chain cho phần web login:

~~~java
@Bean
@Order(2)
SecurityFilterChain defaultSecurityFilterChain(
        HttpSecurity http,
        OAuth2UserService<OidcUserRequest, OidcUser> federatedOidcUserService)
        throws Exception {

    http
        .authorizeHttpRequests(authorize -> authorize
            .requestMatchers("/assets/**", "/error").permitAll()
            .anyRequest().authenticated()
        )
        .oauth2Login(oauth2 -> oauth2
            .userInfoEndpoint(userInfo -> userInfo
                .oidcUserService(federatedOidcUserService)
            )
        );

    return http.build();
}
~~~

Trong ứng dụng có nhiều security filter chain, chain dành cho Authorization Server endpoints phải được đặt trước và có matcher riêng. Chain web login xử lý /login, /oauth2/authorization/{registrationId} và callback /login/oauth2/code/{registrationId}. Ví dụ trên chỉ minh họa chain login; cần kết hợp với chain protocol endpoints, issuer, JWK và các bean nền tảng của Authorization Server.

Spring Security xác minh upstream ID Token theo OIDC client registration, bao gồm chữ ký, issuer, audience, thời hạn và nonce theo flow. Nếu gọi UserInfo Endpoint, OidcUserService dùng upstream access token để lấy thêm claims; claim sub trong UserInfo phải khớp sub trong ID Token. Không tự decode JWT bằng Base64 rồi tin payload.

## 10. Dùng OidcUserService để liên kết external identity

OidcUserService là extension point phù hợp để:
- Gọi implementation mặc định nhằm xác minh và nạp OIDC user.
- Lấy issuer và subject từ ID Token đã xác minh.
- Tra cứu external identity link.
- Thực hiện JIT provisioning nếu policy cho phép.
- Lấy authorities nội bộ từ account/policy engine.
- Tạo principal có tên ổn định theo internal user ID.

Ví dụ skeleton:

~~~java
@Bean
OAuth2UserService<OidcUserRequest, OidcUser> federatedOidcUserService(
        FederatedIdentityService identityService) {

    OidcUserService delegate = new OidcUserService();

    return userRequest -> {
        OidcUser upstreamUser = delegate.loadUser(userRequest);

        String issuer = upstreamUser.getIdToken().getIssuer().toString();
        String subject = upstreamUser.getSubject();
        String registrationId =
                userRequest.getClientRegistration().getRegistrationId();

        InternalAccount account = identityService.resolveOrProvision(
                issuer,
                registrationId,
                subject,
                upstreamUser.getClaims()
        );

        if (!account.enabled()) {
            throw new OAuth2AuthenticationException(
                    new OAuth2Error(OAuth2ErrorCodes.ACCESS_DENIED)
            );
        }

        Set<GrantedAuthority> authorities = account.authorities().stream()
                .map(SimpleGrantedAuthority::new)
                .collect(Collectors.toUnmodifiableSet());

        Map<String, Object> principalClaims = new HashMap<>();
        principalClaims.put("sub", subject);
        principalClaims.put("internal_user_id", account.id().toString());

        OidcUserInfo principalUserInfo = new OidcUserInfo(principalClaims);

        return new DefaultOidcUser(
                authorities,
                upstreamUser.getIdToken(),
                principalUserInfo,
                "internal_user_id"
        );
    };
}
~~~

FederatedIdentityService là service nghiệp vụ do ứng dụng triển khai. Service cần:
1. Chỉ nhận issuer đã cấu hình tin cậy.
2. Tìm external identity theo issuer, sector/registration context và subject.
3. Nếu chưa tồn tại, áp dụng pre-provisioning/JIT policy.
4. Kiểm tra account nội bộ đang active và chưa bị khóa.
5. Chuyển external claims qua mapping policy có version.
6. Tính authorities từ internal directory và policy.
7. Ghi audit cho link/provision và lần đăng nhập.

Trong ví dụ, DefaultOidcUser dùng claim internal_user_id làm getName(). Vì thế principal mà Spring Authorization Server nhìn thấy có tên là internal user ID. sub trong upstream ID Token vẫn là external subject và chỉ được dùng trong bảng liên kết. Không lấy toàn bộ external claims rồi đưa nguyên vào token nội bộ.

OidcUserInfo được tạo cho principal nội bộ vẫn giữ sub bằng subject trong upstream ID Token để nhất quán với ID Token mà Spring Security đã xác minh. Claim internal_user_id chỉ làm name attribute cho local principal. Khi SAS tạo ID Token mới, principal name này là internal subject của hệ thống nội bộ.

Đoạn code là skeleton minh họa; các kiểu InternalAccount, FederatedIdentityService và cách xử lý exception cần được định nghĩa theo domain. Nếu ứng dụng cần giữ upstream UserInfo để hiển thị, hãy lưu/đọc nó qua profile service có kiểm soát; không dùng nguyên tập claims đó làm authorization context.

## 11. Chọn giữa OidcUserService và GrantedAuthoritiesMapper

Spring Security cung cấp hai cách phổ biến để chuyển external authorities:

| Extension point | Khi nào phù hợp | Khả năng |
| --- | --- | --- |
| GrantedAuthoritiesMapper | Chỉ cần chuyển authority đã có sang authority nội bộ | Nhận collection authorities và map thành collection mới |
| OidcUserService | Cần tra cứu directory, đọc access token, liên kết account và tạo principal | Có OidcUserRequest, upstream access token, ID Token và UserInfo |
| OAuth2UserService | Upstream là OAuth 2.0 Provider không dùng OIDC | Nạp user attributes và tạo OAuth2User |
| Custom authentication service | Cần quy trình linking/step-up nhiều bước | Chủ động điều phối policy và persistence |

Nếu chỉ ánh xạ group claim đơn giản, GrantedAuthoritiesMapper có thể đủ. Nếu cần resolve (iss, sub), JIT provisioning, tenant membership hoặc truy vấn protected API của IdP, delegation-based OidcUserService phù hợp hơn.

Không dùng GrantedAuthoritiesMapper làm nơi duy nhất quản lý account linking nếu logic đó cần transaction, audit, retry hoặc nhiều nguồn dữ liệu.

## 12. Phát hành internal claims vào ID Token và access token

Sau khi OidcUserService trả principal nội bộ, Spring Authorization Server có thể lấy internal user ID qua context.getPrincipal().getName() trong token context.

Cần phân biệt:

| Token/Response | Mục đích | Claims nên chứa |
| --- | --- | --- |
| Upstream ID Token | Bằng chứng đăng nhập tại IdP bên ngoài | External issuer/subject và authentication claims |
| Internal ID Token | Claims xác thực của người dùng tại OP nội bộ | Internal subject, profile claims được phép |
| Internal access token | Quyền truy cập Resource Server | Internal roles, tenant, entitlements theo audience/scope |
| UserInfo | Claims người dùng được client yêu cầu | Profile claims được phép release theo scopes |

Không sao chép toàn bộ upstream ID Token sang internal ID Token. Internal token phải dùng issuer của AS nội bộ, subject nội bộ và audience là client nội bộ tương ứng.

### 12.1. OAuth2TokenCustomizer cho claims nội bộ

Spring Authorization Server cho phép dùng OAuth2TokenCustomizer<JwtEncodingContext> để tùy chỉnh JWT. Một bean có thể xử lý nhiều token type; cần kiểm tra token type trước khi thêm claim.

SAS tự kết nối customizer bean với JWT token generator. Nên gom các chính sách claim vào một customizer và phân nhánh theo token type; không khai báo nhiều bean cùng kiểu để cạnh tranh quyền ghi claims.

~~~java
@Bean
OAuth2TokenCustomizer<JwtEncodingContext> internalClaimsCustomizer(
        InternalClaimsService internalClaimsService) {

    return context -> {
        String internalUserId = context.getPrincipal().getName();

        if (OidcParameterNames.ID_TOKEN.equals(
                context.getTokenType().getValue())) {

            InternalProfile profile =
                    internalClaimsService.loadProfile(internalUserId);

            context.getClaims().claims(claims -> {
                claims.put("name", profile.displayName());

                if (profile.email() != null) {
                    claims.put("email", profile.email());
                    claims.put("email_verified", profile.emailVerified());
                }
            });
        }

        if (OAuth2TokenType.ACCESS_TOKEN.equals(context.getTokenType())
                && AuthorizationGrantType.AUTHORIZATION_CODE.equals(
                        context.getAuthorizationGrantType())) {

            InternalAccessPolicy accessPolicy =
                    internalClaimsService.resolveAccess(
                            internalUserId,
                            context.getRegisteredClient().getClientId(),
                            context.getAuthorizedScopes()
                    );

            context.getClaims().claims(claims -> {
                claims.put("roles", accessPolicy.roles());
                claims.put("tenant_id", accessPolicy.tenantId());
                claims.put("entitlements", accessPolicy.entitlements());
            });
        }
    };
}
~~~

InternalClaimsService phải đọc dữ liệu nội bộ đã được policy chấp nhận. resolveAccess(...) nên giới hạn quyền theo internal account, tenant đang hoạt động, client ID và scopes đã được authorize.

Các điểm cần chú ý:
- ID Token dùng profile claims nội bộ được phép cung cấp cho client; không dùng external email nếu policy chưa chấp nhận.
- Access token chứa authorization claims dành cho Resource Server; không nhồi toàn bộ profile.
- roles, tenant_id và entitlements phải được tính từ internal policy, không lấy trực tiếp từ request parameter.
- Không ghi đè các protocol claims như iss, aud, exp, iat, jti hoặc sub bằng dữ liệu upstream.
- Nếu Authorization Server hỗ trợ cả client_credentials, không gắn user claims vào access token của client-only flow. Ví dụ trên giới hạn phần user authorization cho Authorization Code grant.

Đây là ví dụ cho JWT token generation. Nếu sử dụng opaque access token hoặc custom token generator, cần cấu hình customizer tương ứng với token generator đang dùng.

## 13. Tùy chỉnh OIDC UserInfo theo internal policy

UserInfo Endpoint là OAuth2 protected resource và yêu cầu access token. SAS có thể trả standard claims từ ID Token theo scopes đã yêu cầu. Khi cần policy release riêng, dùng OidcUserInfoEndpointConfigurer.userInfoMapper(...).

Ví dụ mapper lấy internal profile từ subject của access token và chỉ trả claims theo scopes đã được authorize:

~~~java
Function<OidcUserInfoAuthenticationContext, OidcUserInfo> userInfoMapper =
        context -> {
            JwtAuthenticationToken authentication =
                    (JwtAuthenticationToken) context.getAuthentication().getPrincipal();

            String internalUserId = authentication.getToken().getSubject();
            Set<String> scopes = context.getAuthorization().getAuthorizedScopes();

            InternalProfile profile =
                    internalClaimsService.loadProfile(internalUserId);

            Map<String, Object> claims = new HashMap<>();
            claims.put("sub", internalUserId);

            if (scopes.contains(OidcScopes.PROFILE)) {
                claims.put("name", profile.displayName());
                claims.put("preferred_username", profile.preferredUsername());
            }

            if (scopes.contains(OidcScopes.EMAIL) && profile.email() != null) {
                claims.put("email", profile.email());
                claims.put("email_verified", profile.emailVerified());
            }

            return new OidcUserInfo(claims);
        };
~~~

Đăng ký mapper trong Authorization Server configurer:

~~~java
authorizationServer
    .oidc(oidc -> oidc
        .userInfoEndpoint(userInfo -> userInfo
            .userInfoMapper(userInfoMapper)
        )
    );
~~~

Mapper trên giả định access token là JWT và principal là JwtAuthenticationToken, giống mô hình cấu hình UserInfo của SAS. Nếu dùng opaque token hoặc thay đổi cách xác thực UserInfo request, hãy lấy subject/authorization từ context tương ứng thay vì ép kiểu này.

Khi bật OIDC UserInfo Endpoint, cấu hình resource server support và cung cấp JwtDecoder theo hướng dẫn SAS. Ví dụ với JWK source của Authorization Server:

~~~java
@Bean
JwtDecoder jwtDecoder(JWKSource<SecurityContext> jwkSource) {
    return OAuth2AuthorizationServerConfiguration.jwtDecoder(jwkSource);
}
~~~

UserInfo response phải giữ claim sub bằng subject trong ID Token nội bộ. Không trả internal claims chỉ vì chúng có trong database: kiểm tra scope, client, consent, purpose và policy release ở mỗi response.

## 14. Resource Server tiêu thụ internal authorization claims

Resource Server phải xác minh access token nội bộ trước khi đọc roles, tenant_id hoặc entitlements. Chữ ký hợp lệ chỉ xác minh token do issuer tin cậy phát hành; Resource Server vẫn cần kiểm tra issuer, audience, expiry và policy.

Ví dụ chuyển claim roles thành Spring authorities:

~~~java
@Bean
JwtAuthenticationConverter internalJwtAuthenticationConverter() {
    JwtGrantedAuthoritiesConverter scopeConverter =
            new JwtGrantedAuthoritiesConverter();

    JwtAuthenticationConverter converter = new JwtAuthenticationConverter();

    converter.setJwtGrantedAuthoritiesConverter(jwt -> {
        Set<GrantedAuthority> authorities =
                new HashSet<>(scopeConverter.convert(jwt));

        List<String> roles = jwt.getClaimAsStringList("roles");
        if (roles != null) {
            roles.stream()
                    .map(role -> new SimpleGrantedAuthority("ROLE_" + role))
                    .forEach(authorities::add);
        }

        return authorities;
    });

    return converter;
}
~~~

Cấu hình converter với Resource Server JWT support:

~~~java
http.oauth2ResourceServer(resourceServer -> resourceServer
        .jwt(jwt -> jwt
                .jwtAuthenticationConverter(internalJwtAuthenticationConverter())
        )
);
~~~

Đây chỉ là ví dụ authority mapping. Mỗi Resource Server cần xác minh audience phù hợp với chính API đó và không dùng claim tenant_id như bằng chứng duy nhất nếu request còn cần kiểm tra tenant ownership ở database.

Access token có thể còn hiệu lực sau khi group hoặc account bị thu hồi ở upstream. Chọn lifetime, introspection, revocation hoặc policy check trực tiếp theo mức độ nhạy cảm của API. Với thao tác quản trị quan trọng, không dựa vào một access token dài hạn chứa snapshot quyền cũ.

## 15. Multi-tenant và nhiều upstream IdP

Một người dùng có thể đăng nhập qua nhiều IdP hoặc thuộc nhiều tenant. Không nên chọn tenant bằng một query parameter không được xác minh rồi đưa thẳng vào token.

Một quy trình tenant resolution an toàn:
1. Lấy external identity đã được xác minh và internal account đã liên kết.
2. Đọc danh sách tenant membership từ internal directory.
3. Nếu chỉ có một tenant hợp lệ, chọn theo policy.
4. Nếu có nhiều tenant, yêu cầu người dùng chọn qua UI đã được bảo vệ.
5. Kiểm tra tenant được chọn nằm trong membership của internal account.
6. Gắn tenant context vào local session/authorization transaction.
7. Khi phát hành access token, chỉ cấp roles/entitlements trong tenant context đã được xác nhận.

Với nhiều IdP:
- Dùng issuer allowlist và cấu hình Client Registration riêng.
- Lưu registration/sector cùng external identity nếu pairwise subject có thể khác.
- Không tự gộp hai account vì trùng email.
- Có quy trình link/unlink rõ ràng và audit.
- Khi IdP bị ngừng tin cậy, disable registration, chặn login mới và rà soát external identity links.

## 16. Claim freshness, account lifecycle và quyền thu hồi

Claims trong JWT là snapshot tại thời điểm phát hành. Khi một external group bị xóa hoặc internal account bị khóa, token đã phát hành có thể vẫn được chấp nhận đến khi hết hạn nếu Resource Server chỉ xác minh JWT cục bộ.

Cần quy định:
- Thời gian đồng bộ group và account status.
- Thời hạn cache external claims.
- Thời điểm re-evaluate internal policy khi refresh token.
- Cách revoke refresh token và authorization khi user bị disable.
- Access token lifetime cho API có mức rủi ro khác nhau.
- Cách Resource Server nhận biết account hoặc tenant membership đã bị thu hồi.
- Cách xử lý upstream IdP outage và key rotation.

Đối với quyền nhạy cảm, có thể dùng access token ngắn hạn, introspection, revocation-aware policy hoặc kiểm tra trạng thái account/tenant ở service. Không ghi nhận một external group trong token là quyền vĩnh viễn.

## 17. Bảo mật và quyền riêng tư khi mapping claims

- **Issuer trust:** chỉ nhận issuer đã được cấu hình và xác minh; không lấy issuer từ request để tải metadata tùy ý.
- **Signature and token validation:** dùng OIDC client support để xác minh ID Token; không tin payload chỉ vì decode thành JSON.
- **Stable identity:** dùng issuer/subject và registration context phù hợp; không dùng email, username hoặc display name làm khóa.
- **Account linking:** yêu cầu xác minh quyền kiểm soát hai account; không auto-link chỉ bằng email.
- **Claim allowlist:** chỉ đọc các claims cần thiết; bỏ qua hoặc từ chối claims không biết.
- **Group mapping:** map group ID theo issuer và policy version; không chuyển group name tùy ý thành admin role.
- **Tenant isolation:** tenant membership do internal directory xác nhận; không tin tenant ID do browser/client tự gửi.
- **Claim collision:** không ghi đè iss, sub, aud, exp, iat, jti và các claims giao thức.
- **Data minimization:** chỉ phát hành claims mà client/resource server cần; tránh đưa PII vào access token nếu không cần.
- **Logging:** không log raw ID Token, access token, refresh token hoặc toàn bộ claims cá nhân; log external identity key đã pseudonymize và policy outcome.
- **Failure handling:** nếu mapping quyền thất bại hoặc account disabled, dừng đăng nhập/cấp token; không fallback sang quyền mặc định rộng.
- **Policy audit:** lưu mapping version, issuer, source claim, target claim, actor và thời điểm thay đổi.

Nếu lấy thêm dữ liệu từ URL trong claim như picture, website hoặc logo_uri, không tự động tải URL đó từ server nội bộ. Cần kiểm soát SSRF, redirect, kích thước và content type. Claim URL là dữ liệu, không phải chỉ thị để backend gọi mạng.

## 18. Ma trận kiểm thử identity federation và claim mapping

| Tình huống | Hành động | Kết quả mong đợi |
| --- | --- | --- |
| Trusted issuer | Login bằng IdP đã allowlist | OIDC Login thành công sau khi xác minh token |
| Unknown issuer | Login qua issuer chưa cấu hình | Từ chối, không tạo internal account |
| Invalid signature | ID Token ký bằng key không tin cậy | Từ chối xác thực |
| Wrong audience | ID Token không dành cho upstream client registration | Từ chối xác thực |
| Expired ID Token | Dùng token đã hết hạn | Từ chối xác thực |
| Nonce mismatch | Callback có nonce không khớp | Từ chối xác thực |
| Existing external link | Đăng nhập bằng (iss, registration, sub) đã liên kết | Resolve đúng internal account |
| New identity with JIT off | Subject chưa có link | Từ chối và yêu cầu onboarding |
| New identity with JIT on | Subject mới từ issuer được phép | Provision theo policy và tenant allowlist |
| Duplicate email | Hai external subject dùng cùng email | Không tự liên kết hai account |
| Unverified email | email_verified=false | Không đánh dấu local email verified |
| Group not mapped | External group không có mapping | Không tạo internal role |
| Group revoked | Mapping/group bị disable | Authority không được cấp trong lần đánh giá tiếp theo |
| Disabled account | Internal account đã khóa | Không thiết lập local session, không cấp token |
| Tenant escalation | Request chọn tenant ngoài membership | Từ chối |
| ID Token claims | Client xin openid profile | Chỉ phát hành internal profile claims được policy cho phép |
| UserInfo scope | Client không có email scope gọi UserInfo | Không trả email claim |
| Access token audience | Token dùng cho API khác | Resource Server từ chối |
| Upstream outage | IdP không sẵn sàng | Áp dụng availability policy, không bỏ qua xác minh |
| Claim freshness | Internal role đã bị thu hồi | Token mới không còn role; token cũ được xử lý theo revocation/lifetime policy |
| Pairwise subject | Cùng user qua hai registration có sub khác nhau | Không gộp nếu chưa có account linking |
| Unlink identity | Gỡ external identity link | Login sau đó bị từ chối hoặc cần linking lại |

Kiểm thử cần xác minh cả local session, internal account link, audit record, ID Token, access token và UserInfo response. Một login thành công ở upstream chưa chứng minh mapping nội bộ đã đúng.

## 19. Bài tập tình huống

Một doanh nghiệp dùng IdP của công ty mẹ để đăng nhập vào Authorization Server nội bộ. IdP gửi các claims:

~~~json
{
  "iss": "https://login.parent.example",
  "sub": "00u-a8c92",
  "email": "linh@example.com",
  "email_verified": true,
  "groups": [
    "grp-order-readers",
    "grp-finance"
  ],
  "department": "FIN"
}
~~~

Hệ thống nội bộ có account ID usr-4821, tenant tenant-vn, roles ORDER_VIEWER và FINANCE_VIEWER. Client orders-web chỉ cần profile cơ bản và quyền đọc đơn hàng.

Hãy phân tích:

1. Khóa nào dùng để liên kết external identity với usr-4821?
2. Vì sao không dùng email làm khóa liên kết?
3. groups được chuyển thành internal roles qua policy nào?
4. department=FIN có đủ để gán tenant hoặc role hay không?
5. Internal Authorization Server phát hành sub nào trong ID Token nội bộ?
6. Claims nào nên có trong ID Token và access token?
7. Làm thế nào bảo đảm orders-web không nhận thông tin tài chính không cần thiết?
8. Nếu user bị gỡ khỏi grp-order-readers, token đang hoạt động được xử lý ra sao?
9. Nếu người dùng đăng nhập từ một upstream registration khác với pairwise sub mới, làm sao tránh tạo hoặc liên kết nhầm account?
10. Đề xuất test cho duplicate email, unverified email, disabled account, tenant escalation và group revocation.

**Gợi ý:** Lưu external identity bằng issuer + registration/sector + subject. Internal subject vẫn là usr-4821 hoặc opaque ID nội bộ. Chỉ map hai group đã được phê duyệt sang roles nội bộ. Tenant membership lấy từ internal directory. Access token chỉ mang audience, scope và quyền cần cho Orders API; profile claims được release theo scope và consent.

## 20. Checklist triển khai production

1. **Trust:** allowlist issuer và cấu hình OIDC Client Registration theo từng upstream IdP.
2. **Validation:** xác minh chữ ký, issuer, audience, expiry, nonce và UserInfo subject consistency.
3. **Identity key:** dùng (iss, sub); bổ sung registration/sector context khi dùng pairwise subject.
4. **Account linking:** có pre-provisioning, JIT hoặc explicit linking policy; không auto-link bằng email.
5. **Internal subject:** dùng internal stable ID cho subject của OP nội bộ.
6. **Claim policy:** định nghĩa source, trust, transformation, target, conflict và release policy.
7. **Group mapping:** allowlist external group ID theo issuer/registration; map sang internal roles.
8. **Authority source:** lấy roles, tenant và entitlements từ internal directory/policy engine.
9. **Spring Security:** dùng OidcUserService hoặc GrantedAuthoritiesMapper phù hợp; tạo principal có internal identity.
10. **Token customizer:** phân nhánh ID Token và access token; không trộn profile với authorization claims.
11. **UserInfo:** bật endpoint, cung cấp JwtDecoder và custom mapper nếu cần policy release.
12. **Audience/scope:** giới hạn token theo client, Resource Server và quyền được cấp.
13. **Tenant:** xác nhận membership trước khi gắn tenant context vào token.
14. **Freshness:** xác định sync interval, cache TTL, token lifetime và revocation policy.
15. **Lifecycle:** xử lý disable, unlink, IdP offboarding, key rotation và policy versioning.
16. **Privacy:** giảm thiểu PII, redact token/claims trong log và audit theo nguyên tắc cần biết.
17. **Testing:** kiểm thử identity resolution, mapping, token issuance, UserInfo, replay, stale claims và multi-tenant.
18. **Operations:** theo dõi login failure, unknown issuer, unmapped group, JIT provision, account linking và policy denial.

## 21. Tài liệu chuẩn và Spring cần đối chiếu

- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): ID Token validation, issuer, subject, UserInfo và claim stability/uniqueness.
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749.html): OAuth 2.0 Authorization Code flow và vai trò Authorization Server/Client.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700.html): bảo vệ OAuth clients, authorization flows và token handling.
- [Spring Security 6.5 — OAuth 2.0 Login Advanced Configuration](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/login/advanced.html): OidcUserService, GrantedAuthoritiesMapper và mapping authorities từ upstream provider.
- [Spring Authorization Server 1.5.8 — Customize the OIDC UserInfo response](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-userinfo.html): tùy chỉnh ID Token claims và userInfoMapper.
- [Spring Authorization Server 1.5.8 — Add authorities as custom claims in JWT access tokens](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-custom-claims-authorities.html): OAuth2TokenCustomizer<JwtEncodingContext> và token-specific claims.
- [Spring Authorization Server 1.5.8 — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): OIDC UserInfo Endpoint configurer và extension points.
- [Spring Authorization Server 1.5.8 — Core Model Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): token customization và các model component của Authorization Server.

**Ghi nhớ:** Upstream IdP xác thực external identity; Authorization Server nội bộ chịu trách nhiệm liên kết identity, tính internal authorities và phát hành token của chính mình. Dùng issuer/subject cùng registration context để nhận diện external account, không dùng email làm khóa. Chỉ chuyển claims qua mapping policy có allowlist và version; roles, tenant và entitlements phải được xác định từ internal directory hoặc policy engine. Dùng OidcUserService để tạo principal nội bộ, OAuth2TokenCustomizer để phát hành claims đúng token type và userInfoMapper để kiểm soát claims trả cho client. Một external login thành công không đồng nghĩa người dùng được cấp mọi quyền mà IdP bên ngoài công bố.
