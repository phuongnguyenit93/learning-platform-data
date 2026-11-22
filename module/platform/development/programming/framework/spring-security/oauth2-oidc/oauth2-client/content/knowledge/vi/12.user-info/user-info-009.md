# 12.9. Bổ sung dữ liệu hồ sơ từ dịch vụ người dùng nội bộ

## 1. Tình huống: đăng nhập qua OIDC nhưng hồ sơ nghiệp vụ nằm trong hệ thống riêng

Trong một ứng dụng Spring Security OAuth 2.0/OIDC Client, người dùng thường đăng nhập qua **OpenID Provider (OP)** như một hệ thống SSO của doanh nghiệp. Sau khi xác thực, Client nhận ID Token và có thể gọi UserInfo Endpoint để lấy các claim OIDC chuẩn như tên, email, ảnh đại diện hoặc locale.

Tuy nhiên, ứng dụng không chỉ cần các thông tin đó. Ví dụ, một cổng quản lý cho thuê có thể cần:

- Mã người dùng **nội bộ** để liên kết hợp đồng và lịch sử giao dịch.
- Phòng ban, chi nhánh, đơn vị kinh doanh và tên hiển thị được chuẩn hóa.
- Trạng thái tài khoản nội bộ: đang hoạt động, bị khóa, chưa được phê duyệt.
- Vai trò ứng dụng: <code>EMPLOYEE</code>, <code>SUPPORT</code>, <code>BILLING_ADMIN</code>.
- Các thuộc tính nghiệp vụ như hạn mức phê duyệt, cấp truy cập dữ liệu, đơn vị sở hữu.

Những dữ liệu này thường được quản lý bởi **dịch vụ người dùng nội bộ** (*internal user service*), không phải OP. Vì vậy, ứng dụng cần **bổ sung dữ liệu hồ sơ** sau khi xác thực OIDC mà không làm mất những thuộc tính tin cậy từ ID Token và UserInfo.

Ta gọi quy trình này là **profile enrichment**: dùng danh tính đã được OP xác minh để tìm bản ghi nội bộ, lấy dữ liệu nghiệp vụ đã được dịch vụ nội bộ xác thực, rồi xây dựng principal/authorization context thích hợp.

> **Phân biệt ngay từ đầu:** OP chứng minh **người dùng nào đã đăng nhập**; dịch vụ người dùng nội bộ cho biết **người đó tương ứng tài khoản nghiệp vụ nào và được phép làm gì trong ứng dụng**. Bổ sung hồ sơ không phải là sửa ID Token của OP.

## 2. Các nguồn dữ liệu và ranh giới tin cậy

Một hệ thống thường có ít nhất ba nguồn dữ liệu:

| Nguồn | Dữ liệu thường có | Ai chịu trách nhiệm? |
|---|---|---|
| **ID Token** | <code>iss</code>, <code>sub</code>, <code>aud</code>, <code>exp</code>, tên/email nếu OP cung cấp | OpenID Provider; Spring Security xác minh token |
| **OIDC UserInfo** | Tên, email, ảnh đại diện, locale và các claim profile được OP công bố | OpenID Provider; Client truy vấn bằng access token phù hợp |
| **Internal User Service** | Internal user ID, phòng ban, trạng thái, role, đơn vị, quyền nghiệp vụ | Dịch vụ người dùng/authorization nội bộ |

Ví dụ hai nguồn có thể trả:

**OIDC ID Token đã được xác minh:**

~~~json
{
  "iss": "https://idp.example.org/realms/workforce",
  "sub": "6d90a0c3-7d90-4b35-8be5-51a1c8e08f45",
  "aud": "rental-portal",
  "email": "alex@example.org",
  "email_verified": true
}
~~~

**Response từ dịch vụ người dùng nội bộ:**

~~~json
{
  "id": "9f14ac31-1ce1-4ee5-9e30-d0e7a8f4341a",
  "displayName": "Alex Nguyen",
  "department": "Customer Operations",
  "active": true,
  "roles": ["EMPLOYEE", "SUPPORT"]
}
~~~

Các ID, tên miền và thông tin hồ sơ trong ví dụ đều là dữ liệu giả.

Ta cần giữ riêng:

1. **Danh tính từ OP:** cặp <code>(issuer, subject)</code>, được xác minh từ ID Token.
2. **Danh tính nội bộ:** <code>internalUserId</code>, do hệ thống nghiệp vụ quản lý.
3. **Thông tin hiển thị:** tên, avatar, email; có thể có nhiều nguồn và quy tắc ưu tiên.
4. **Quyền:** role/permission nội bộ đã được kiểm tra, không mặc nhiên lấy từ một claim bất kỳ.

Không lấy <code>email</code> làm khóa duy nhất để tìm và liên kết tài khoản nội bộ chỉ vì nó dễ đọc.

### 2.1. Vì sao phải dùng cặp (iss, sub)?

OIDC định nghĩa <code>sub</code> là định danh End-User **trong phạm vi issuer**. Cùng một chuỗi <code>sub</code> đến từ hai issuer khác nhau không mặc nhiên chỉ cùng một người.

Ví dụ:

~~~text
Issuer A: https://idp.example.org/realms/tenant-a
Subject:  12345

Issuer B: https://idp.example.org/realms/tenant-b
Subject:  12345
~~~

Hai trường hợp phải được xem là **hai danh tính bên ngoài khác nhau**, trừ khi có quy trình liên kết tài khoản được kiểm chứng riêng.

Thiết kế khóa ánh xạ phù hợp:

~~~text
ExternalIdentity(issuer, subject)  →  InternalUserId
~~~

Với database, có thể lưu một bảng:

~~~sql
CREATE TABLE external_identities (
    issuer           VARCHAR(512) NOT NULL,
    subject          VARCHAR(255) NOT NULL,
    internal_user_id UUID NOT NULL,
    created_at       TIMESTAMP NOT NULL,
    PRIMARY KEY (issuer, subject)
);
~~~

Đây là schema minh họa. Cần chọn độ dài cột, kiểu dữ liệu thời gian và chỉ mục phù hợp database, đồng thời áp dụng ràng buộc tham chiếu đến bảng user nội bộ nếu kiến trúc cho phép.

**Không tự động liên kết theo email**: email có thể thay đổi, có thể được tái sử dụng hoặc chưa được xác minh. Ngay cả <code>email_verified=true</code> cũng không chứng minh hai tài khoản từ hai issuer là cùng một tài khoản nghiệp vụ được phép gộp. Account linking phải là một quy trình riêng có bước xác minh và kiểm soát.

## 3. Kiến trúc bổ sung hồ sơ sau OIDC Login

Trong Servlet OAuth2 Login, Spring Security có cơ chế <code>OidcUserService</code> để lấy và xây dựng <code>OidcUser</code> sau bước trao đổi token.

Ta có thể **delegate** cho <code>OidcUserService</code> mặc định thực hiện logic OIDC/UserInfo trước, sau đó dùng subject/issuer đã xác minh để truy vấn dịch vụ nội bộ.

~~~mermaid
flowchart TD
    A["Browser bắt đầu OIDC Login"] --> B["Authorization Code Flow tại OP"]
    B --> C["Spring Security trao đổi token"]
    C --> D["OidcUserService mặc định"]
    D --> E["ID Token / UserInfo đã xử lý"]
    E --> F["Lấy (iss, sub) tin cậy"]
    F --> G["InternalProfileGateway"]
    G --> H["Internal User Service"]
    H --> I{"Có user nội bộ và active?"}
    I -->|Không| X["Từ chối login hoặc provisioning theo policy"]
    I -->|Có| J["Lấy internal ID, display name, roles"]
    J --> K["Tạo principal giàu dữ liệu hơn"]
    K --> L["SecurityContext / HTTP session"]
    L --> M["Controller / Method Security"]
~~~

Trình tự chi tiết:

1. Browser được redirect tới OP; người dùng đăng nhập.
2. OP trả authorization code, Spring Security thực hiện token exchange.
3. Bộ xử lý OIDC của Spring Security xác minh ID Token; <code>OidcUserService</code> có thể truy vấn UserInfo khi điều kiện provider/scope phù hợp.
4. Ứng dụng đọc <code>iss</code> và <code>sub</code> từ dữ liệu OIDC đã qua kiểm tra.
5. Client gọi **internal user service** bằng kênh bảo mật do hệ thống quản lý.
6. Internal service tìm bản ghi theo <code>(iss, sub)</code> và trả hồ sơ.
7. Ứng dụng kiểm tra trạng thái user và ánh xạ những role được phép.
8. Một custom <code>OidcUser</code> giữ nguyên thông tin OIDC đồng thời cung cấp <code>internalUserId</code> và metadata nội bộ.
9. Các request tiếp theo dùng principal và/hoặc truy vấn dịch vụ nội bộ theo chính sách dữ liệu mới nhất.

### 3.1. Sequence diagram

~~~mermaid
sequenceDiagram
    autonumber
    participant B as Browser
    participant C as Spring Security Client
    participant OP as OpenID Provider
    participant U as Internal User Service
    B->>C: GET /oauth2/authorization/company
    C-->>B: 302 tới OP, state/nonce/PKCE tùy flow
    B->>OP: Đăng nhập
    OP-->>B: Callback với code và state
    B->>C: GET /login/oauth2/code/company?code=...&state=...
    C->>OP: Token request
    OP-->>C: ID Token / access token
    C->>C: Xác minh ID Token, dựng OidcUser
    opt Khi phù hợp với OIDC UserInfo
        C->>OP: GET UserInfo với access token của OP
        OP-->>C: UserInfo claims
    end
    C->>C: Lấy issuer + subject từ danh tính đã xác minh
    C->>U: Resolve external identity bằng service credential
    U-->>C: Internal user ID, active, department, roles
    C->>C: Ánh xạ authority + tạo principal bổ sung
    C-->>B: Login success / session
~~~

**Không đưa access token phát cho OP/UserInfo sang internal user service một cách mặc định.** Access token có audience và phạm vi sử dụng riêng; một internal API chỉ được chấp nhận token đó nếu nó thực sự là resource server được cấp token dành cho mình và đã xác minh đầy đủ. Thông thường nên dùng **service-to-service credential** riêng cho internal API.

## 4. Chọn đúng extension point trong Spring Security

Spring Security cung cấp các điểm mở rộng khác nhau:

| Điểm mở rộng | Dùng cho | Khi nên chọn |
|---|---|---|
| <code>OAuth2UserService&lt;OidcUserRequest, OidcUser&gt;</code> | Quá trình load người dùng **OIDC** | Cần lấy UserInfo rồi bổ sung user nội bộ |
| <code>OidcUserService</code> | Implementation chuẩn của OIDC user service | Làm delegate để giữ hành vi OIDC chuẩn |
| <code>oauth2Login().userInfoEndpoint().oidcUserService(...)</code> | Gắn custom OIDC service vào login flow | Cách tích hợp chính trong bài |
| <code>oauth2Login().userInfoEndpoint().userService(...)</code> | OAuth 2.0 Login **không dùng OIDC** | Provider không có scope <code>openid</code>/ID Token OIDC |
| <code>GrantedAuthoritiesMapper</code> | Ánh xạ authorities sau khi user được load | Chỉ cần chuyển đổi authorities mà không cần principal tùy biến |
| <code>AuthenticationSuccessHandler</code> | Điều hướng và tác vụ sau đăng nhập | Không lý tưởng để thay thế toàn bộ quy trình tạo OidcUser |
| Domain service trong controller/service | Tra cứu hồ sơ khi dùng ứng dụng | Hồ sơ thay đổi thường xuyên hoặc không muốn gắn vào session |

Trong bài này, chọn **custom OidcUserService có delegate** vì cần cả dữ liệu nội bộ lẫn authority sau khi xác minh OIDC.

> Với OAuth2 Login thuần, dùng <code>userService(...)</code> và <code>OAuth2User</code> thay vì áp dụng máy móc <code>OidcUserService</code>. Hai flow liên quan nhưng không giống nhau.

### 4.1. Vì sao không tự parse ID Token?

ID Token có thể là JWT ký bằng khóa của OP. Spring Security đã cung cấp logic xác minh issuer, audience, chữ ký, thời gian và các ràng buộc OIDC khi cấu hình đúng. Tự parse payload bằng cách tách chuỗi JWT rồi decode Base64URL chỉ cho thấy **dữ liệu tự khai chưa đáng tin cậy**.

Custom user service cần hoạt động **sau** logic OIDC của framework, không thay nó. Không lấy <code>iss</code>/<code>sub</code> từ URL callback, query parameter do browser gửi hoặc payload JWT chưa xác minh để gọi API nội bộ.

## 5. Thiết kế dữ liệu hồ sơ nội bộ

Ví dụ Java 17 với một record dùng làm snapshot hồ sơ:

~~~java
package example.security.profile;

import java.io.Serializable;
import java.util.Set;
import java.util.UUID;

public record InternalUserProfile(
        UUID id,
        String displayName,
        String department,
        boolean active,
        Set<String> roles
) implements Serializable {
    private static final long serialVersionUID = 1L;
}
~~~

Các trường:

- <code>id</code>: khóa nội bộ ổn định để liên kết bảng dữ liệu nghiệp vụ.
- <code>displayName</code>: tên hiển thị do hệ thống nghiệp vụ quản lý.
- <code>department</code>: thông tin tổ chức; không mặc định dùng làm quyền truy cập.
- <code>active</code>: trạng thái có được phép sử dụng hệ thống hay không.
- <code>roles</code>: các role nội bộ theo taxonomy do ứng dụng kiểm soát.

Đây chỉ là snapshot cho bài học. Dịch vụ user thật có thể có version, thời gian cập nhật, trạng thái provisioning hoặc thông tin tenant. **Không đưa dữ liệu nhạy cảm không cần thiết** như ngày sinh, giấy tờ, số tài khoản vào principal chỉ để hiển thị một màn hình nhỏ.

Interface truy vấn dịch vụ:

~~~java
package example.security.profile;

import java.util.Optional;

public interface InternalProfileGateway {

    Optional<InternalUserProfile> findByExternalIdentity(
            String issuer,
            String subject);
}
~~~

Với interface này, <code>Optional.empty()</code> có nghĩa là **không tìm thấy ánh xạ người dùng**. Nó không được dùng để biểu diễn chung tất cả lỗi mạng, lỗi xác thực service hoặc lỗi server.

Phân biệt trạng thái giúp ứng dụng ra quyết định đúng:

| Kết quả | Ý nghĩa | Chính sách điển hình |
|---|---|---|
| Có user và <code>active=true</code> | Danh tính có tài khoản nội bộ đang hoạt động | Tiếp tục bước dựng principal/role |
| Không tìm thấy user | Chưa được liên kết/provisioned | Từ chối hoặc chạy luồng JIT provisioning được cho phép |
| Có user nhưng <code>active=false</code> | User bị khóa/không còn hiệu lực nội bộ | Không cho login vào ứng dụng |
| HTTP 401/403 khi gọi internal API | Service credential/quyền service bị lỗi | Lỗi hệ thống; không coi là user không tồn tại |
| Timeout/HTTP 5xx | Internal service tạm thời không hoạt động | Fail closed với quyền nhạy cảm; tránh tạo user giả |
| Payload sai schema | API nội bộ không tương thích hoặc dữ liệu hỏng | Báo lỗi tích hợp; không bịa role mặc định |

## 6. Tạo principal có cả OIDC identity và hồ sơ nội bộ

Có hai cách phổ biến:

1. Dựng một <code>DefaultOidcUser</code> mới với authorities đã bổ sung. Cách này đơn giản nếu ứng dụng chỉ cần role, còn user ID nội bộ được tra cứu qua service khác.
2. Tạo **wrapper implements <code>OidcUser</code>** chứa delegate OIDC và snapshot hồ sơ nội bộ. Cách này giữ các OIDC claims nguyên bản, đồng thời cung cấp <code>internalUserId</code> mà không giả mạo claim do OP ký.

Trong tình huống cần hiển thị profile và dùng internal ID, wrapper là lựa chọn rõ ràng.

### 6.1. Custom OidcUser wrapper

~~~java
package example.security.profile;

import java.io.Serial;
import java.io.Serializable;
import java.util.Collection;
import java.util.Collections;
import java.util.LinkedHashSet;
import java.util.Map;

import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.oauth2.core.oidc.OidcIdToken;
import org.springframework.security.oauth2.core.oidc.OidcUserInfo;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;

public final class EnrichedOidcUser implements OidcUser, Serializable {

    @Serial
    private static final long serialVersionUID = 1L;

    private final OidcUser delegate;
    private final InternalUserProfile internalProfile;
    private final Collection<? extends GrantedAuthority> authorities;

    public EnrichedOidcUser(
            OidcUser delegate,
            InternalUserProfile internalProfile,
            Collection<? extends GrantedAuthority> authorities) {
        this.delegate = delegate;
        this.internalProfile = internalProfile;
        this.authorities = Collections.unmodifiableSet(
            new LinkedHashSet<>(authorities));
    }

    public InternalUserProfile internalProfile() {
        return internalProfile;
    }

    @Override
    public Collection<? extends GrantedAuthority> getAuthorities() {
        return authorities;
    }

    @Override
    public String getName() {
        return delegate.getName();
    }

    @Override
    public Map<String, Object> getAttributes() {
        return delegate.getAttributes();
    }

    @Override
    public Map<String, Object> getClaims() {
        return delegate.getClaims();
    }

    @Override
    public OidcIdToken getIdToken() {
        return delegate.getIdToken();
    }

    @Override
    public OidcUserInfo getUserInfo() {
        return delegate.getUserInfo();
    }
}
~~~

Wrapper giữ nguyên:

- <code>getIdToken()</code>: ID Token đã được framework xử lý.
- <code>getUserInfo()</code>: UserInfo nếu OP cung cấp và Spring Security sử dụng.
- <code>getClaims()</code>, <code>getAttributes()</code>: dữ liệu OIDC như ở principal gốc.
- <code>getName()</code>: ngữ nghĩa nhận dạng của principal OIDC gốc, không tự đổi thành user ID nội bộ.
- <code>getAuthorities()</code>: authorities mới đã được ứng dụng chọn lọc.
- <code>internalProfile()</code>: snapshot hồ sơ từ dịch vụ nội bộ.

**Vì sao không sửa <code>id_token</code> hoặc claims của nó?** ID Token được OP phát hành và ký. Nếu ứng dụng ghép <code>department</code>, <code>internalUserId</code> hoặc role nội bộ vào map claim rồi tự gọi đó là “ID Token đã xác minh”, người đọc rất dễ nhầm nguồn tin cậy. Tách <code>internalProfile</code> ra khỏi OIDC claims sẽ rõ ràng hơn.

Nếu dùng HTTP session phân tán (ví dụ Spring Session lưu principal), cần bảo đảm toàn bộ object được lưu có khả năng serialization phù hợp với session store, version và mô hình triển khai. Chỉ lưu dữ liệu tối thiểu vì role/profile có thể trở nên cũ.

## 7. Custom OidcUserService: delegate rồi bổ sung dữ liệu

Ta xây dựng <code>OAuth2UserService&lt;OidcUserRequest, OidcUser&gt;</code>, dùng <code>OidcUserService</code> mặc định làm delegate.

### 7.1. Code Java

~~~java
package example.security.profile;

import java.util.Collection;
import java.util.LinkedHashSet;
import java.util.Set;

import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.client.oidc.userinfo.OidcUserRequest;
import org.springframework.security.oauth2.client.oidc.userinfo.OidcUserService;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.security.oauth2.core.user.OAuth2UserService;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClientException;

@Service
public class EnrichingOidcUserService
        implements OAuth2UserService<OidcUserRequest, OidcUser> {

    private static final Set<String> ALLOWED_ROLES = Set.of(
        "EMPLOYEE", "SUPPORT", "BILLING_ADMIN");

    private final OidcUserService delegate = new OidcUserService();
    private final InternalProfileGateway profileGateway;

    public EnrichingOidcUserService(InternalProfileGateway profileGateway) {
        this.profileGateway = profileGateway;
    }

    @Override
    public OidcUser loadUser(OidcUserRequest userRequest)
            throws OAuth2AuthenticationException {

        // Giữ nguyên logic OIDC/UserInfo mặc định của Spring Security.
        OidcUser oidcUser = delegate.loadUser(userRequest);

        // Lấy identity từ ID Token đã đi qua cơ chế OIDC validation.
        String issuer = oidcUser.getIdToken().getClaimAsString("iss");
        String subject = oidcUser.getSubject();
        if (issuer == null || issuer.isBlank()
                || subject == null || subject.isBlank()) {
            throw rejected("invalid_external_identity");
        }

        final InternalUserProfile profile;
        try {
            profile = profileGateway.findByExternalIdentity(issuer, subject)
                .orElseThrow(() -> rejected("internal_account_not_found"));
        } catch (RestClientException ex) {
            // Không chuyển lỗi hạ tầng thành "user không tồn tại".
            throw new OAuth2AuthenticationException(
                new OAuth2Error(
                    "internal_profile_unavailable",
                    "Internal profile service is unavailable",
                    null),
                ex);
        }

        if (!profile.active()) {
            throw rejected("internal_account_disabled");
        }

        Collection<GrantedAuthority> authorities =
            new LinkedHashSet<>(oidcUser.getAuthorities());

        if (profile.roles() != null) {
            profile.roles().stream()
                .filter(ALLOWED_ROLES::contains)
                .map(role -> new SimpleGrantedAuthority("ROLE_" + role))
                .forEach(authorities::add);
        }

        return new EnrichedOidcUser(oidcUser, profile, authorities);
    }

    private static OAuth2AuthenticationException rejected(String code) {
        return new OAuth2AuthenticationException(
            new OAuth2Error(code, "Unable to complete sign-in", null));
    }
}
~~~

Trong code:

1. <code>delegate.loadUser(userRequest)</code> cho phép Spring Security thực hiện việc xây dựng OIDC principal theo cấu hình đã có.
2. <code>iss</code>/<code>sub</code> đến từ ID Token của OIDC principal, **không từ dữ liệu request chưa xác minh**.
3. <code>profileGateway.findByExternalIdentity(...)</code> tìm đúng hồ sơ theo hai khóa.
4. Không có hồ sơ hoặc hồ sơ <code>active=false</code> → **không cho đăng nhập ứng dụng** theo policy minh họa.
5. Lỗi gọi internal API được phân loại khác với “không có user”.
6. Role nội bộ được **allowlist**, chuyển thành authority <code>ROLE_...</code> theo convention của Spring Security.
7. Wrapper giữ dữ liệu OIDC gốc, chỉ bổ sung phần ứng dụng quản lý.

<code>ALLOWED_ROLES</code> trong ví dụ là role của **ứng dụng**. Trong dự án thật nên định nghĩa central authorization policy và đồng bộ tên quyền với backend nghiệp vụ. Không tự động chuyển mọi chuỗi mà internal API trả về thành authority — dữ liệu bị cấu hình sai có thể vô tình tạo quyền quản trị.

### 7.2. Trường hợp phải dùng OIDC UserInfo

<code>OidcUserService</code> có thể gọi UserInfo Endpoint tùy điều kiện như scope, cấu hình endpoint và token mà OP cung cấp. Nội dung UserInfo là dữ liệu từ **OP**, không phải từ internal user service.

Không nên gọi UserInfo thủ công bằng user access token ở custom service chỉ để lấy những claim mà delegate đã tải. Nếu cần tùy biến cách tải UserInfo, Spring Security có các cấu hình/điểm mở rộng riêng cho <code>OidcUserService</code>, tùy phiên bản.

Trong mọi trường hợp, dữ liệu UserInfo có yêu cầu bảo mật riêng: OP phải trả claim <code>sub</code> khớp với subject của ID Token theo OIDC. Không lấy UserInfo từ một endpoint tùy ý rồi mặc định nó thuộc cùng danh tính với ID Token.

### 7.3. Nếu cần đồng bộ profile định kỳ

Một lần gọi internal API khi login chỉ tạo **snapshot**. Nếu role thay đổi lúc người dùng đang đăng nhập, principal trong HTTP session không tự thay đổi.

Các lựa chọn:

- Chấp nhận snapshot cho dữ liệu hiển thị ít nhạy cảm đến khi người dùng đăng nhập lại.
- Dùng TTL và cơ chế refresh hồ sơ trong session cho trang hoặc action phù hợp.
- Với quyền nhạy cảm, truy vấn lại nguồn authority/entitlement tại thời điểm thực hiện hành động.
- Dùng event thông báo khóa user/thay đổi role để thu hồi session hoặc làm mới context.

**Không coi snapshot trong session là nguồn sự thật vĩnh viễn** cho những quyền có thể bị thu hồi khẩn cấp.

## 8. Gắn EnrichingOidcUserService vào SecurityFilterChain

Ví dụ Spring Boot 3, Spring Security 6 chạy Servlet:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
~~~

Cấu hình OIDC provider:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company
            client-id: rental-web-client
            client-secret: ${OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: [openid, profile, email]
        provider:
          company:
            issuer-uri: https://idp.example.org/realms/workforce
~~~

Trong production, Client ID, secret, issuer và redirect URI phải đúng với registration trên OP. Không commit secret thật; giá trị môi trường trong ví dụ là placeholder.

Cấu hình Spring Security:

~~~java
package example.security;

import example.security.profile.EnrichingOidcUserService;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.SimpleUrlAuthenticationFailureHandler;

@Configuration
public class WebSecurityConfig {

    @Bean
    SecurityFilterChain webSecurity(
            HttpSecurity http,
            EnrichingOidcUserService enrichingOidcUserService)
            throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/login", "/error", "/assets/**").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(login -> login
                .userInfoEndpoint(userInfo -> userInfo
                    .oidcUserService(enrichingOidcUserService))
                .failureHandler(
                    new SimpleUrlAuthenticationFailureHandler("/login?error")));

        return http.build();
    }
}
~~~

Ở đây:

- <code>userInfoEndpoint().oidcUserService(...)</code> là nơi custom OIDC user service được gắn vào luồng đăng nhập.
- Spring Security vẫn xử lý Authorization Code Flow, callback, ID Token và cơ chế authentication.
- Khi <code>EnrichingOidcUserService.loadUser(...)</code> ném <code>OAuth2AuthenticationException</code>, đăng nhập được xử lý là **thất bại**, không tự tạo phiên thành công.
- Failure handler trả về trang đăng nhập với thông báo chung; không đưa nguyên lỗi từ internal API, token hoặc thông tin nhạy cảm lên URL.

Mẫu này giả định internal profile service có policy rõ ràng: không tìm thấy user hoặc user bị khóa thì không cho đăng nhập. Ứng dụng có chính sách “đăng nhập hạn chế khi dịch vụ hồ sơ tạm thời lỗi” phải định nghĩa một **vai trò hạn chế** riêng và bảo đảm không mở quyền ngoài dự kiến.

**Nhiều filter chain:** nếu web chain có <code>securityMatcher</code> giới hạn <code>/app/**</code>, cần bao gồm cả các endpoint mặc định <code>/oauth2/authorization/**</code> và <code>/login/oauth2/code/**</code>. Nếu callback bị chain API chọn trước, custom OIDC service có thể không bao giờ chạy.

## 9. Kết nối internal user service qua RestClient

Custom OIDC service ở trên phụ thuộc <code>InternalProfileGateway</code>. Sau đây là một adapter HTTP minh họa với <code>RestClient</code> của Spring Framework 6.1+, phù hợp với Spring Boot 3.2+.

Giả sử internal API có hợp đồng:

~~~http
POST /internal/users/resolve HTTP/1.1
Content-Type: application/json
Authorization: Bearer SERVICE_ACCESS_TOKEN

{
  "issuer": "https://idp.example.org/realms/workforce",
  "subject": "6d90a0c3-7d90-4b35-8be5-51a1c8e08f45"
}
~~~

Response thành công:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "id": "9f14ac31-1ce1-4ee5-9e30-d0e7a8f4341a",
  "displayName": "Alex Nguyen",
  "department": "Customer Operations",
  "active": true,
  "roles": ["EMPLOYEE", "SUPPORT"]
}
~~~

API trả HTTP 404 khi không có mapping, HTTP 401/403 khi service credential không hợp lệ, HTTP 5xx khi hệ thống lỗi. Đây là **hợp đồng minh họa**, không phải endpoint mặc định do Spring Security hoặc OIDC cung cấp.

### 9.1. Cung cấp service token riêng

Để không chuyển nhầm access token của người dùng sang một API khác, định nghĩa một dependency cấp token cho dịch vụ nội bộ:

~~~java
package example.security.profile;

public interface InternalServiceTokenProvider {
    String getAccessTokenForProfileApi();
}
~~~

Ứng dụng thực tế phải cung cấp implementation sử dụng **OAuth 2.0 client credentials**, mTLS hoặc cơ chế service authentication phù hợp. Nếu dùng OAuth2 client credentials, token cần có audience/scope được internal API cấp phép và được cache/refresh theo thời hạn thực tế.

Interface này cố ý **không trả user access token** của OIDC Login. Ứng dụng cũng không nên dùng một chuỗi bearer token cố định viết trực tiếp trong mã nguồn.

### 9.2. HTTP adapter minh họa

~~~java
package example.security.profile;

import java.time.Duration;
import java.util.Optional;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.MediaType;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.RestClient;

@Component
public final class RestInternalProfileGateway
        implements InternalProfileGateway {

    private final RestClient restClient;

    public RestInternalProfileGateway(
            RestClient.Builder restClientBuilder,
            @Value("${app.internal-profile.base-url}") String baseUrl,
            InternalServiceTokenProvider tokenProvider) {

        var requestFactory = new SimpleClientHttpRequestFactory();
        requestFactory.setConnectTimeout(Duration.ofSeconds(2));
        requestFactory.setReadTimeout(Duration.ofSeconds(3));

        this.restClient = restClientBuilder
            .baseUrl(baseUrl)
            .requestFactory(requestFactory)
            .requestInterceptor((request, body, execution) -> {
                request.getHeaders().setBearerAuth(
                    tokenProvider.getAccessTokenForProfileApi());
                return execution.execute(request, body);
            })
            .build();
    }

    @Override
    public Optional<InternalUserProfile> findByExternalIdentity(
            String issuer,
            String subject) {
        try {
            InternalUserProfile profile = restClient
                .post()
                .uri("/internal/users/resolve")
                .contentType(MediaType.APPLICATION_JSON)
                .body(new ExternalIdentityLookup(issuer, subject))
                .retrieve()
                .body(InternalUserProfile.class);

            if (profile == null) {
                throw new IllegalStateException(
                    "Internal profile response body is empty");
            }

            return Optional.of(profile);
        } catch (HttpClientErrorException.NotFound ex) {
            // Hợp đồng API: 404 thực sự có nghĩa chưa có mapping.
            return Optional.empty();
        }
    }

    private record ExternalIdentityLookup(
            String issuer,
            String subject) {
    }
}
~~~

Thuộc tính cấu hình:

~~~yaml
app:
  internal-profile:
    base-url: https://users.internal.example.org
~~~

**Cần hoàn thiện khi triển khai:** bean <code>InternalServiceTokenProvider</code> bằng service authentication hợp lệ, cấu hình TLS trust, giới hạn kết nối và quan sát lỗi. Nếu không có provider token, Spring context sẽ không thể tạo adapter; đó là dependency có chủ đích, không phải token được Spring tự cấp.

Ngoài ra:

- Chỉ sử dụng base URL từ cấu hình tin cậy, không lấy URL người dùng cung cấp để tránh SSRF.
- Kết nối HTTPS với kiểm tra chứng chỉ, không tắt TLS validation.
- Internal API phải xác thực service và kiểm tra authorization; nằm trong mạng nội bộ **không đồng nghĩa đáng tin**.
- Giới hạn response size, đặt connect/read timeout; có thể dùng client HTTP phù hợp yêu cầu production.
- Phân biệt **404** với **401/403/5xx**; không bắt tất cả ngoại lệ rồi trả <code>Optional.empty()</code>.
- Không log nguyên token, header <code>Authorization</code>, cookie OIDC hoặc response chứa PII.

Trong ví dụ, <code>HttpClientErrorException.NotFound</code> được chuyển thành “không có tài khoản”. Những lỗi khác (timeout, HTTP 5xx, lỗi JSON, service authentication) tiếp tục ném exception. Phần custom user service cần phân loại và hiển thị lỗi an toàn. Với lỗi payload malformed không thuộc <code>RestClientException</code> hoặc dữ liệu null, nên có handling riêng theo chính sách lỗi tích hợp của dự án; không tự xem chúng là “user không có mapping”.

### 9.3. Không mặc định chuyển OIDC access token sang internal API

Phân biệt hai kênh HTTP:

~~~text
Spring OIDC Client ---- user access token ----> OP UserInfo Endpoint

Spring OIDC Client ---- service access token ---> Internal User Service
~~~

Access token do OP phát cho UserInfo hoặc API khác có **audience**, scope và chủ thể nhất định. Gửi token đó vào internal service không chỉ có thể thất bại vì audience không khớp mà còn có nguy cơ **token leakage** và lẫn ranh giới ủy quyền.

Nếu cần internal API thực hiện thao tác **thay mặt người dùng**, có thể có thiết kế token exchange/on-behalf-of theo hợp đồng IdP và Resource Server. Đây là một luồng riêng cần kiểm tra audience, scope, delegation và consent, không nên thay bằng việc chuyển tiếp mù user access token.

## 10. Truy cập hồ sơ nội bộ từ Controller và method security

Với <code>EnrichedOidcUser</code> trong Authentication principal, controller có thể lấy các trường cần thiết mà không phải parse token lại.

~~~java
package example.web;

import example.security.profile.EnrichedOidcUser;
import java.util.Map;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class MeController {

    @GetMapping("/me")
    public Map<String, String> me(
            @AuthenticationPrincipal EnrichedOidcUser principal) {
        var profile = principal.internalProfile();

        return Map.of(
            "internalUserId", profile.id().toString(),
            "displayName", profile.displayName(),
            "department", profile.department()
        );
    }
}
~~~

Ví dụ giả định <code>displayName</code> và <code>department</code> không null. Trong API thực tế, nên dùng DTO cụ thể và xử lý null/tùy chọn để tránh <code>Map.of</code> ném exception.

**Không gửi ra frontend toàn bộ <code>OidcUser</code>, <code>OidcIdToken</code>, access token hoặc internal profile chứa PII không cần thiết.** Chỉ trả các trường mà UI được phép nhận.

### 10.1. Role nội bộ thành GrantedAuthority

Trong <code>EnrichingOidcUserService</code>:

~~~java
new SimpleGrantedAuthority("ROLE_BILLING_ADMIN")
~~~

Sau đó, tại endpoint:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class BillingController {

    @PostMapping("/billing/close-period")
    @PreAuthorize("hasRole('BILLING_ADMIN')")
    public String closePeriod() {
        return "Period closure requested";
    }
}
~~~

Kích hoạt method security:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {
}
~~~

<code>hasRole("BILLING_ADMIN")</code> tương ứng authority <code>ROLE_BILLING_ADMIN</code> với role prefix mặc định của Spring Security. Application phải xác định nguồn cấp role tin cậy, kiểm soát thay đổi role và kiểm tra quyền trước hành động thực.

Controller mẫu chỉ minh họa authorization; thao tác đóng kỳ kế toán thật còn cần transaction control, audit, CSRF protection với browser session, validation dữ liệu và domain service.

### 10.2. Không tự coi mọi claim thành quyền

Ví dụ ID Token có:

~~~json
{
  "preferred_username": "alex",
  "groups": ["admins"]
}
~~~

Điều đó **không tự động** chứng minh ứng dụng phải cấp <code>ROLE_BILLING_ADMIN</code>. Claim <code>groups</code> có thể có ý nghĩa tại OP nhưng chưa chắc ánh xạ đúng với role nghiệp vụ của ứng dụng. Chỉ ánh xạ khi có chính sách công nhận issuer/claim rõ ràng, hoặc dựa trên role được internal service có thẩm quyền cung cấp.

## 11. Chiến lược xử lý khi user chưa có trong hệ thống nội bộ

Khi OIDC hợp lệ nhưng <code>(iss, sub)</code> không được tìm thấy, có một số chính sách khả thi.

### 11.1. Chỉ cho đăng nhập người đã được cấp quyền trước

Phù hợp với cổng nội bộ hoặc hệ thống dữ liệu nhạy cảm:

~~~text
OIDC identity hợp lệ
    -> InternalProfileGateway: 404 / không có mapping
    -> OAuth2AuthenticationException("internal_account_not_found")
    -> Login failed với thông báo chung
~~~

Trường hợp này tránh tự tạo tài khoản cho bất cứ danh tính hợp lệ nào của OP. Đội quản trị phải phê duyệt và tạo mapping trước.

### 11.2. Just-in-Time provisioning (JIT)

Một số ứng dụng cho phép tạo hồ sơ nội bộ lần đầu người dùng đăng nhập. Nếu dùng JIT:

1. Chỉ cho phép issuer/client/tenant đã được cấu hình tin cậy.
2. Xác minh ID Token đầy đủ trước khi tạo user.
3. Dùng <code>(iss, sub)</code> làm external identity; áp dụng unique constraint để chống tạo trùng khi nhiều request song song.
4. Tạo user với **quyền tối thiểu**, có thể chờ phê duyệt; không lấy role đặc quyền từ trường tự khai.
5. Đặt rõ trạng thái, nguồn tạo, audit trail và chính sách xóa/khóa tài khoản.
6. Tránh quyết định liên kết tự động với tài khoản hiện có chỉ dựa vào email trùng.

JIT provisioning nên nằm ở **domain service có transaction và idempotency**, không viết trực tiếp thao tác insert database tùy ý trong controller callback.

### 11.3. Liên kết tài khoản đã tồn tại

Nếu người dùng muốn liên kết một OIDC identity mới với tài khoản nội bộ cũ, hãy có quy trình bảo vệ riêng: người dùng chứng minh quyền sở hữu cả danh tính hiện tại và danh tính mới, đáp ứng yêu cầu assurance/reauthentication nếu cần, rồi ghi mapping có audit.

Không tự động hợp nhất tài khoản chỉ vì <code>email</code>, <code>name</code>, <code>preferred_username</code> hoặc số điện thoại trùng nhau.

## 12. Rủi ro dữ liệu cũ trong session và cách xử lý

Ví dụ người dùng đăng nhập lúc 09:00, service trả:

~~~json
{
  "active": true,
  "roles": ["BILLING_ADMIN"]
}
~~~

Đến 10:00, quản trị viên thu hồi quyền <code>BILLING_ADMIN</code> ở internal service. Nếu ứng dụng chỉ giữ authorities trong HTTP session, <code>SecurityContext</code> của người dùng có thể vẫn chứa quyền cũ cho đến khi phiên được cập nhật, hết hạn hoặc đăng nhập lại.

Vì vậy phải lựa chọn nhất quán:

| Loại dữ liệu | Chiến lược thường phù hợp |
|---|---|
| Tên hiển thị, ảnh, locale | Cache ngắn hoặc đến lần login tiếp theo nếu chấp nhận dữ liệu cũ |
| Phòng ban, chi nhánh | TTL và refresh khi cần nếu thay đổi ảnh hưởng phân quyền dữ liệu |
| Role nghiệp vụ phổ thông | Cache có version/TTL và cơ chế invalidation nếu có yêu cầu |
| Quyền duyệt tiền, xuất dữ liệu lớn, khóa tài khoản | Kiểm tra gần thời điểm hành động, revocation hoặc session invalidation |
| Trạng thái bị khóa/terminated | Có cơ chế phát hiện nhanh, không đợi phiên hết hạn quá lâu |

**Session là cache/khung authentication tại thời điểm login**, không phải cơ chế đồng bộ quyền thời gian thực. Nếu cần thu hồi tức thì, phải có một chiến lược bổ sung.

### 12.1. Cách cập nhật quyền khi ứng dụng nhiều instance

Khi chạy nhiều node:

- HTTP session có thể nằm tại node cụ thể hoặc trong Spring Session/Redis.
- Các node cần cùng cách diễn giải authorities và internal user ID.
- Dữ liệu principal được serialize cần tương thích version; tránh giữ object domain nặng và reference không thể serialize.
- Khi đổi role, dùng event/invalidation hoặc xác thực quyền trực tiếp tại domain service để tránh các node giữ snapshot khác nhau.
- Nếu internal service tạm thời không hoạt động, không tự thay role hiện tại thành đặc quyền rộng hơn.

### 12.2. Có nên gọi internal service ở mọi request?

Không luôn cần thiết. Mỗi request đều gọi API nội bộ có thể gây:

- Độ trễ tăng, đặc biệt khi UI gửi nhiều request.
- Áp lực lên internal service và nguy cơ cascade failure.
- Khó kiểm soát timeout/circuit breaker và rate limit.
- Nguy cơ lộ thông tin qua quá nhiều network call/log.

Thường cân bằng bằng cache có thời hạn, đọc lại khi thay đổi nghiệp vụ, kiểm tra quyền ở domain service hoặc áp dụng event-driven invalidation. Tuy nhiên với hành động cực kỳ nhạy cảm, một lần xác minh quyền hiện thời có thể đáng giá hơn việc dùng snapshot cũ.

## 13. Khả năng phục hồi khi dịch vụ hồ sơ gặp sự cố

Bổ sung hồ sơ ngay trong OIDC Login tạo một dependency mới: OP có thể hoạt động bình thường nhưng internal user service tạm thời lỗi. Cần phân loại và đưa ra chính sách rõ.

| Tình huống | Không nên làm | Hành vi phù hợp |
|---|---|---|
| Timeout từ internal service | Giả sử user không tồn tại hoặc tạo user mới | Báo lỗi hệ thống, retry có kiểm soát ở đúng lớp |
| HTTP 401/403 từ internal service | Thử chuyển user access token từ OP sang thay credential | Sửa service authentication/audience/quyền |
| HTTP 404 | Coi là outage hoặc bắt buộc retry vô hạn | Áp dụng chính sách chưa provisioned |
| HTTP 503 | Mặc định cho mọi user quyền <code>ROLE_EMPLOYEE</code> | Fail closed hoặc chế độ hạn chế được thiết kế rõ |
| Response thiếu <code>id</code> hoặc <code>active</code> | Dùng giá trị giả để đăng nhập | Xem là dữ liệu không hợp lệ và từ chối/điều tra |
| User <code>active=false</code> | Vẫn cấp session có quyền vì ID Token hợp lệ | Chặn truy cập theo chính sách nội bộ |

### 13.1. Timeout, circuit breaker và retry

Kết nối nội bộ phải có timeout hợp lý, không treo request đăng nhập vô thời hạn. Trong hệ thống nhiều người dùng, có thể dùng circuit breaker/bulkhead để ngăn outage lan rộng.

Nếu retry, chỉ retry các trường hợp có ngữ nghĩa phù hợp như lỗi mạng tạm thời hoặc HTTP 503 và có **giới hạn số lần/backoff**. Không retry vô hạn HTTP 404 hoặc 403. API tra cứu identity cần có ngữ nghĩa idempotent theo hợp đồng; nếu dùng POST cho lookup, vẫn phải xác nhận server xử lý truy vấn không tạo side effect trước khi áp dụng retry.

### 13.2. Chính sách fail closed và chế độ hạn chế

Với ứng dụng chứa dữ liệu nhạy cảm, nếu không xác minh được user nội bộ hoặc quyền, **không cấp quyền nghiệp vụ** là lựa chọn an toàn.

Một số ứng dụng công khai có thể cho user OIDC đăng nhập ở chế độ “chưa hoàn tất hồ sơ”, nhưng phải:

- Có principal/state riêng cho chế độ hạn chế.
- Chỉ cho phép endpoint công khai và các bước hoàn tất onboarding đã được định nghĩa.
- Không dùng role mặc định để truy cập dữ liệu nghiệp vụ.
- Không coi sự cố 5xx là tương đương người dùng mới chưa được provisioned.

Đây là quyết định sản phẩm/bảo mật, không phải behavior mặc định của <code>OidcUserService</code>.

## 14. Phân biệt ánh xạ danh tính với đồng bộ profile

Hai hành động dễ bị trộn:

**Identity resolution:** xác định một OIDC identity đang trỏ tới user nội bộ nào:

~~~text
(iss, sub) -> internalUserId
~~~

**Profile synchronization:** cập nhật tên, email, ảnh, locale hoặc các trường được OP cho phép đồng bộ vào hồ sơ nội bộ.

Nếu tự động ghi mọi field OIDC vào database mỗi lần login, ứng dụng có thể ghi đè giá trị do nhân sự/chăm sóc khách hàng quản lý. Cần định nghĩa **source of truth** cho từng trường:

| Field | Nguồn ưu tiên minh họa | Hành vi |
|---|---|---|
| External issuer/subject | ID Token đã được xác minh | Chỉ dùng làm khóa liên kết; không cho user tự sửa |
| Internal user ID | Internal user service/database | Không nhận từ claim tùy ý |
| Email dùng cho liên lạc | Có thể là internal profile hoặc OIDC tùy policy | Có quy tắc đối chiếu và kiểm tra <code>email_verified</code> nếu phù hợp |
| Display name | Internal profile hoặc OP | Không tự ghi đè nếu user đã được cho phép chỉnh sửa |
| Department | HR/user service nội bộ | Không mặc nhiên tin claim profile tự khai |
| Roles/permissions | Authorization service nội bộ | Áp dụng chính sách cấp quyền và thu hồi |
| Profile photo | Có thể từ OP/UserInfo | Kiểm soát URL, nguồn hình và riêng tư |

**Bổ sung hồ sơ không mặc nhiên đồng nghĩa ghi dữ liệu ngược vào OP hoặc database.** Nếu muốn sync hai chiều, cần thiết kế separate workflow có quy tắc xung đột, audit, quyền chỉnh sửa và bảo vệ dữ liệu cá nhân.

## 15. Các vấn đề bảo mật quan trọng

### 15.1. Tin dữ liệu OIDC đúng nguồn

- Chỉ lấy issuer/subject từ ID Token đã được xác minh bằng cấu hình OP đáng tin.
- Với UserInfo, bảo đảm subject của UserInfo khớp subject ID Token theo OIDC; để framework xử lý đúng giao thức.
- Không dùng dữ liệu claim chưa xác minh từ frontend làm khóa truy vấn user nội bộ.
- Nếu có nhiều issuer, dùng mapping theo cặp <code>(iss, sub)</code> và policy về issuer được phép.

### 15.2. Service authentication và token audience

- Internal User Service phải xác thực client gọi nó (mTLS, service token hoặc mô hình tương đương).
- Nếu dùng OAuth2 client credentials, token phải có audience và scope dành cho internal API.
- Không chuyển tiếp ID Token làm bearer token cho internal API theo mặc định: ID Token chủ yếu chứng minh authentication với Client, không phải access token cho resource server.
- Không lấy access token dành cho UserInfo hoặc API khác rồi dùng nhầm tại internal API.
- Không đưa service credential vào browser, response JSON hoặc logs.

### 15.3. Quyền và dữ liệu nội bộ

- Định nghĩa allowlist role, phân cấp quyền và chính sách cấp authority.
- Internal API phải kiểm tra rằng caller chỉ đọc dữ liệu được phép; không dựa vào “nội bộ” để bỏ authorization.
- Với request tra cứu bằng issuer/subject, nên có audit và rate limit phù hợp để hạn chế enumeration.
- Không đưa toàn bộ hồ sơ cá nhân vào HTTP session chỉ vì thuận tiện.
- Không tự liên kết account dựa trên email hoặc số điện thoại.

### 15.4. Nguyên tắc tối thiểu hóa dữ liệu

Internal profile có thể chứa PII hoặc thông tin nhạy cảm. Chỉ yêu cầu những trường cần phục vụ use case. Ví dụ trang chào mừng có thể chỉ cần displayName, trong khi kiểm tra quyền cần role. Không ghi hay xuất cả object profile khi chỉ cần một boolean <code>active</code>.

Người dùng có thể truy cập <code>/me</code> để xem dữ liệu được phép, nhưng API response không nên trả credential, danh sách quyền thô không cần thiết hoặc metadata hạ tầng. Áp dụng kiểm soát truy cập và retention theo chính sách dữ liệu của tổ chức.

## 16. Xử lý lỗi và các triệu chứng thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Đăng nhập OP thành công nhưng ứng dụng chuyển về <code>/login?error</code> | Internal profile không tồn tại, bị khóa hoặc internal API lỗi | Phân biệt mã lỗi trong telemetry; kiểm tra mapping/status và service health |
| <code>ClassCastException</code> khi ép principal sang <code>EnrichedOidcUser</code> | Custom user service chưa được gắn vào chain, hoặc endpoint phục vụ OAuth-only principal | Kiểm tra <code>userInfoEndpoint().oidcUserService(...)</code> và chain được chọn |
| User được nhận sai bản ghi nội bộ | Mapping bằng email hoặc không đưa issuer vào khóa | Dùng cặp <code>(iss, sub)</code>, kiểm tra unique constraint/account linking |
| User bị khóa vẫn truy cập được | Session chứa profile cũ hoặc status chỉ kiểm tra lúc login | Thu hồi session và kiểm tra trạng thái tại hành động cần bảo vệ |
| Đổi role nhưng <code>hasRole</code> chưa cập nhật | Authority snapshot trong session | Refresh/invalidate session hoặc kiểm tra quyền trực tiếp |
| UserInfo không có claim email | Scope không được cấp, OP không công bố email hoặc UserInfo không được gọi | Không phụ thuộc email cho identity lookup; kiểm tra UserInfo flow |
| Internal API trả 401 | Service token không hợp lệ/hết hạn hoặc audience sai | Kiểm tra client credentials và cấu hình internal resource server |
| Internal API trả 403 | Service thiếu quyền gọi endpoint lookup | Kiểm tra scope/authorization service-to-service |
| Internal API trả 404 | Không có external identity mapping | Provisioning hoặc chặn login theo policy |
| Internal API trả 502/503 | Lỗi mạng, DNS, gateway, backend quá tải | Timeout/circuit breaker, telemetry và fail-closed policy |
| Đăng nhập chậm | Internal service gọi nối tiếp quá nhiều API | Gộp lookup, dùng cache hợp lý và hạn chế dữ liệu |
| User từ tenant khác được map cùng tài khoản | So khớp <code>sub</code> đơn lẻ hoặc không xác minh issuer | Kiểm tra issuer và ranh giới tenant |
| Spring Session lỗi serialize principal | Custom wrapper chứa object không serializable hoặc thay đổi version | Giữ snapshot DTO nhỏ, serializable và có chiến lược tương thích |
| Callback 404/chưa bao giờ gọi custom service | OAuth2 Login filter/chain không nhận callback | Kiểm tra redirect URI, <code>securityMatcher</code> và thứ tự chain |

### 16.1. Quy trình chẩn đoán theo lớp

~~~text
Browser callback có đến ứng dụng?
    |
    v
Spring Security có chọn đúng OAuth2 Login chain?
    |
    v
ID Token/nonce/state/issuer được xử lý hợp lệ?
    |
    v
OidcUserService mặc định tải user thành công?
    |
    v
Custom OidcUserService đã được gọi?
    |
    v
(iss, sub) có được ánh xạ chính xác?
    |
    v
Internal Service trả 200/404/401/403/5xx?
    |
    v
active/roles/profile hợp lệ theo policy?
    |
    v
Principal + SecurityContext có được lưu và dùng đúng?
~~~

Không đổ mọi lỗi cho OP hoặc cho internal service. Nếu callback không vào đúng chain, custom user service có thể **chưa hề chạy**. Nếu ID Token sai issuer/audience, **không được gọi internal API bằng danh tính đó**.

Log nên dùng registration ID, kết quả lookup, mã HTTP, correlation ID nội bộ và một mã lỗi hữu hạn. Không log ID Token, access token, service token, authorization code, PKCE verifier hoặc toàn bộ profile response chứa PII.

## 17. Bài tập thực hành

### Bài 1 — Thiết kế khóa ánh xạ

Hai OP trả ID Token đã được xác minh:

~~~text
Token A: iss=https://idp.example.org/tenant/a, sub=12345
Token B: iss=https://idp.example.org/tenant/b, sub=12345
~~~

**Câu hỏi:** Có nên dùng <code>sub=12345</code> để tìm user nội bộ không?

**Đáp án:** Không. Dùng cặp <code>(iss, sub)</code>. Hai issuer khác nhau không mặc nhiên chia sẻ cùng không gian danh tính. Cần chính sách account linking riêng nếu nghiệp vụ thực sự muốn gộp.

### Bài 2 — Phân biệt ba loại dữ liệu

Ứng dụng cần:

1. Xác nhận người dùng đang đăng nhập là ai.
2. Biết display name, email và locale của họ.
3. Biết họ có được duyệt hóa đơn hay không.

**Đáp án gợi ý:** (1) dùng ID Token/OIDC authentication đã xác minh; (2) dùng UserInfo và/hoặc profile nội bộ theo source-of-truth policy; (3) dùng role/entitlement từ dịch vụ nội bộ có thẩm quyền và kiểm tra tại backend. Không suy diễn quyền từ email hoặc display name.

### Bài 3 — Mapping role an toàn

Internal API trả:

~~~json
{
  "roles": ["EMPLOYEE", "BILLING_ADMIN", "SUPER_ROOT"]
}
~~~

Ứng dụng chỉ hỗ trợ <code>EMPLOYEE</code>, <code>SUPPORT</code>, <code>BILLING_ADMIN</code>.

**Câu hỏi:** Những authority nào được tạo?

**Đáp án:** Chỉ <code>ROLE_EMPLOYEE</code> và <code>ROLE_BILLING_ADMIN</code> (ngoài authorities OIDC gốc mà policy quyết định giữ lại). Không tự tạo <code>ROLE_SUPER_ROOT</code> nếu ứng dụng không cho phép role đó.

### Bài 4 — Dịch vụ nội bộ gặp lỗi

Người dùng đã xác thực OIDC hợp lệ nhưng internal API trả HTTP 503.

**Câu hỏi:** Có nên tạo profile mới với <code>active=true</code> và <code>roles=["EMPLOYEE"]</code> để tránh người dùng bị chặn?

**Đáp án:** Không. HTTP 503 là lỗi dịch vụ, không phải chứng cứ user mới hay đã được cấp quyền. Với policy yêu cầu hồ sơ nội bộ, nên báo đăng nhập chưa hoàn tất và ghi lỗi hạ tầng an toàn; chỉ cho chế độ hạn chế nếu kiến trúc có quy tắc rõ và không cấp quyền nghiệp vụ.

### Bài 5 — Quyền bị thu hồi khi session còn sống

Người dùng đã login và có <code>ROLE_BILLING_ADMIN</code> trong principal. Sau đó internal service thu hồi quyền, nhưng user chưa logout.

**Câu hỏi:** Vì sao method security có thể vẫn thấy quyền cũ?

**Đáp án:** <code>GrantedAuthority</code> của Authentication thường là snapshot được tạo khi login. Nếu không refresh/thu hồi session hoặc kiểm tra entitlement tại thời điểm hành động, permission cũ vẫn tồn tại. Cần thiết kế refresh/invalidation hoặc authorization trực tiếp cho thao tác nhạy cảm.

### Bài 6 — Tích hợp trên ứng dụng thử nghiệm

1. Tạo ClientRegistration OIDC với issuer, Client ID và redirect URI của OP thử nghiệm.
2. Bật <code>oauth2Login()</code>, kiểm tra nhận được <code>OidcUser</code> từ delegate.
3. Tạo <code>InternalProfileGateway</code> bản fake cho môi trường thử, ánh xạ theo <code>(iss, sub)</code>.
4. Gắn <code>EnrichingOidcUserService</code> vào DSL <code>oidcUserService(...)</code>.
5. Tạo <code>/me</code> chỉ trả <code>internalUserId</code>, display name và các trường được phép.
6. Tạo endpoint bảo vệ bằng <code>@PreAuthorize("hasRole('BILLING_ADMIN')")</code>.
7. Thử các trường hợp: có user active, user bị khóa, mapping không tồn tại, internal service lỗi, provider khác issuer nhưng cùng subject, role không có trong allowlist.
8. Quan sát dữ liệu sau login và bảo đảm không ghi token/secret vào log.

Bài này tập trung vào **cách thiết kế và viết nội dung tích hợp**; việc chạy kiểm thử, đánh giá và content QA được thực hiện trong giai đoạn kiểm tra riêng của dự án.

## 18. Ghi nhớ

- **Profile enrichment** là bước bổ sung dữ liệu nghiệp vụ từ internal user service sau khi danh tính OIDC đã được OP xác thực và Spring Security xử lý.
- Khóa ánh xạ tin cậy là **<code>(iss, sub)</code>**, không phải email hay <code>sub</code> đơn lẻ khi có nhiều issuer.
- Trong Spring Security Servlet OIDC Login, có thể triển khai <code>OAuth2UserService&lt;OidcUserRequest, OidcUser&gt;</code> bằng cách **delegate <code>OidcUserService</code> mặc định**, truy vấn internal API rồi xây principal giàu dữ liệu hơn.
- Dùng <code>oauth2Login().userInfoEndpoint().oidcUserService(...)</code> để gắn custom service; đừng nhầm với <code>userService(...)</code> dành cho OAuth2 Login thông thường.
- Giữ **ID Token/UserInfo claims** tách biệt với **internal profile và authorities**. Không sửa nội dung ID Token đã ký hay tự biến role tùy ý thành quyền.
- Gọi internal API bằng **service authentication dành riêng cho API đó**, không chuyển tiếp mù ID Token hoặc access token dành cho UserInfo.
- Phân biệt **không có user**, **user bị khóa** và **dịch vụ không khả dụng**; với quyền nhạy cảm nên fail closed.
- Hồ sơ/role trong HTTP session thường là **snapshot**; cần chính sách cập nhật/thu hồi quyền phù hợp với mức rủi ro nghiệp vụ.

### Tài liệu tham khảo

- **OpenID Connect Core 1.0:** ID Token, UserInfo Endpoint, subject identifier và quy tắc kiểm tra <code>sub</code>.
- **OpenID Connect Discovery 1.0:** issuer và metadata của OpenID Provider.
- **Spring Security Reference — OAuth2 Login (Servlet):** tùy biến OIDC UserInfo, <code>OidcUserService</code> và <code>userInfoEndpoint()</code>.
- **Spring Security Java API:** <code>OidcUserRequest</code>, <code>OidcUserService</code>, <code>OAuth2UserService</code>, <code>OidcUser</code>, <code>DefaultOidcUser</code>.
- **Spring Security Reference — Authorization / Method Security:** <code>GrantedAuthority</code>, <code>SimpleGrantedAuthority</code>, <code>hasRole</code> và <code>@PreAuthorize</code>.
- **Spring Framework Reference — REST Clients:** <code>RestClient</code>, HTTP request/response, timeouts và error handling.
- **RFC 6749 — The OAuth 2.0 Authorization Framework:** phân biệt Client, Authorization Server, Resource Server, access token và client credentials.
