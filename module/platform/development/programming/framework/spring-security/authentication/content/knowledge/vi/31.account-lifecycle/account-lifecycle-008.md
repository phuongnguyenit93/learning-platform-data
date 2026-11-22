# Liên kết, gỡ liên kết tài khoản ngoài với danh tính nội bộ

## 1. Khái niệm và yêu cầu cốt lõi

Tài khoản nội bộ (local account) là bản ghi danh tính do ứng dụng quản lý, có ID ổn định, dữ liệu nghiệp vụ, vai trò và trạng thái. Tài khoản ngoài (external identity) là danh tính được xác thực bởi OpenID Provider (OIDC) hoặc nhà cung cấp OAuth2 phù hợp. **Account linking** liên kết một danh tính ngoài đã được xác minh với một tài khoản nội bộ mà chủ sở hữu đã xác thực và chấp thuận. **Unlink** loại bỏ quan hệ này để identity ngoài không còn đăng nhập vào local account qua mapping ấy.

Ví dụ: Alice có local user ID `u-123`. Alice đăng nhập bằng password/passkey và chọn liên kết một tài khoản OIDC để lần sau có thể dùng SSO. Backend phải chắc chắn: chính Alice của `u-123` vừa yêu cầu, danh tính OIDC thực sự thuộc Alice, OAuth transaction thuộc đúng phiên linking, và identity ngoài chưa thuộc local user khác.

**Không bao giờ tự ghép theo email.** OIDC Core quy định `iss` + `sub` là cặp định danh ổn định; `email`, `email_verified`, `preferred_username` và tên hiển thị không có bảo đảm unique, bất biến hoặc không được tái cấp. `email_verified=true` không chứng minh người dùng đã đồng ý liên kết vào local account này.

Bài học phân biệt:

| Thao tác | Ý nghĩa | Không đồng nghĩa |
| --- | --- | --- |
| External login | OP xác thực và ứng dụng tra existing link để lấy local user | Tự động tạo liên kết theo email |
| Link account | Thêm mapping external identity → local ID với consent và fresh authentication | Gộp hai local accounts |
| Unlink account | Vô hiệu mapping đã tồn tại | Xóa tài khoản ở OP hoặc xóa dữ liệu local |
| OAuth authorized client | Lưu access token/refresh token để gọi API ngoài | Khóa đăng nhập liên kết |
| Merge accounts | Hợp nhất dữ liệu/roles/billing của hai local accounts | Một bước bình thường của OAuth2 login |

**Mục tiêu học tập:** chọn external key đúng, thiết kế link/unlink chống account takeover, xử lý session và provider token sau thay đổi, tránh race và biết các điểm Spring Security cung cấp nhưng không làm thay logic nghiệp vụ.

## 2. Chọn khóa danh tính và schema an toàn

Với OIDC, khóa chính cho liên kết là:

~~~text
local_user_id = "u-123"
external_key = (
    issuer  = "https://idp.example.test/realms/main",
    subject = "00uAK1pQ"
)
~~~

`issuer` phải là issuer từ ID token đã được xác minh, không phải URI do request chưa xác thực đưa tới. `subject` là subject đã được verify trong issuer ấy. Hai issuer khác nhau có thể dùng cùng `sub`. Một provider có pairwise subject có thể cấp `sub` khác theo client/sector; cần kế hoạch migration đáng tin nếu đổi client ID/sector, không tự ghép theo email.

Schema PostgreSQL tham khảo:

~~~sql
CREATE TABLE local_account (
    id VARCHAR(64) PRIMARY KEY,
    status VARCHAR(20) NOT NULL,
    security_version BIGINT NOT NULL DEFAULT 0
);

CREATE TABLE external_identity (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    local_user_id VARCHAR(64) NOT NULL
        REFERENCES local_account(id),
    issuer VARCHAR(512) NOT NULL,
    subject VARCHAR(255) NOT NULL,
    registration_id VARCHAR(120) NOT NULL,
    linked_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (issuer, subject)
);

CREATE INDEX idx_external_identity_user
    ON external_identity(local_user_id);
~~~

Đây là schema **minh họa**, không phải migration hoàn chỉnh. Nếu chọn soft-delete, dùng trạng thái ACTIVE/REVOKED, audit/tombstone và unique constraint/partial unique index phù hợp để bảo đảm **một external key chỉ thuộc tối đa một local account ACTIVE**. Tạo index unique ở DB quan trọng hơn chỉ kiểm tra `findByIssuerAndSubject`: hai request đồng thời có thể cùng nhìn thấy “chưa tồn tại”.

Nếu provider **chỉ hỗ trợ OAuth2**, không có OIDC ID token, phải dùng identifier bất biến từ resource endpoint đáng tin cùng **provider/tenant namespace** được cấu hình chính xác. Không được giả định OAuth2 access token tự mang một `sub` có semantics OIDC; cần tài liệu của từng provider.

Không biến email, picture, scope, access token hoặc refresh token thành khóa sở hữu local account. Các trường này có vòng đời và tính bảo đảm khác nhau.

## 3. Flow link: cả local account và external identity phải được chứng minh

### Bước A — chủ tài khoản nội bộ bắt đầu link

1. Chỉ cho phép `POST /settings/external-links/start` từ local session đã authenticated; bật bảo vệ **CSRF** đối với browser.
2. Bắt **fresh re-authentication/step-up** phù hợp với rủi ro, đặc biệt nếu account có MFA. Cookie đăng nhập từ nhiều ngày trước không đủ để thay đường đăng nhập.
3. Server lấy `localUserId` từ principal nội bộ đã tin cậy, **không từ body/query**. Kiểm tra account ACTIVE, provider được phép, liên kết có thể thêm và policy không chặn.
4. User chọn provider và xác nhận consent. Server tạo bản ghi pending `purpose=LINK` với expiration ngắn, user ID, registration ID, session binding, security version và nonce/state được bảo vệ.
5. Bắt đầu **Authorization Code + PKCE** và OIDC nonce theo protocol. `state` phải ngẫu nhiên, gắn transaction và không được tái sử dụng; redirect URI từ allowlist đã đăng ký.

### Bước B — external identity được xác thực

6. Browser được redirect đến issuer đã chọn. OP xác thực external user; callback trả `code` và `state`.
7. OAuth/OIDC client kiểm tra response tương ứng request: `state`/PKCE, issuer, redirect URI, nonce khi có, ID token signature/algorithm, `iss`, `aud`, `exp`/thời gian; ứng dụng dùng thư viện chuẩn thay vì tự parse claims từ URL.
8. Lấy key `(validated iss, validated sub)`. **Không sử dụng email hoặc nickname** để quyết định local account cần link.
9. Nạp pending LINK từ server-side state và **ràng buộc lại** với local authenticated session/purpose/provider/user/version. User logout/login account khác trong tab song song thì callback bị từ chối.
10. Dùng DB transaction + unique constraint để insert mapping. Nếu external key đã thuộc user khác, trả conflict mà không tự merge hay chuyển ownership. Nếu đã thuộc chính user này, có thể trả idempotent theo policy.
11. Consume pending intent một lần, audit và thông báo qua kênh đã xác minh trước đó; rà soát session/security version; trả trang Settings đã liên kết.

~~~text
Authenticated local session (Alice, u-123)
    -> POST start LINK, CSRF + fresh step-up
    -> Pending LINK[u-123, provider-A, session, state, expiry]
    -> Redirect OP A + PKCE/nonce
    -> OP callback: code + state
    -> Validate OAuth2/OIDC transaction
    -> Validated issuer + subject
    -> Re-check pending user, local session, purpose, expiry
    -> DB unique(issuer,subject) + atomic insert
    -> Notify, audit, cleanup pending
~~~

### Một pending intent cần có gì?

| Trường | Mục đích |
| --- | --- |
| `id` và `purpose=LINK` | Phân biệt với login thông thường, chống callback gắn nhầm |
| `localUserId` | Đích đến được lấy từ auth nội bộ, bất biến trong flow |
| `registrationId` và issuer allowlist | Chống provider mix-up |
| `stateHash` | Tra transaction một lần, tránh raw state trong database/log |
| `nonce` + PKCE verifier/challenge | Ràng buộc OIDC token và authorization code |
| `sessionBinding` | Không cho callback ở session người khác |
| `securityVersion` | Nhận ra local session bị thu hồi/thay đổi giữa flow |
| `expiresAt`, `consumedAt` | TTL và replay protection |
| `returnPath` allowlisted | Không open redirect tới domain attacker |

`state`, PKCE và `nonce` bổ trợ nhau nhưng không hoàn toàn thay thế nhau. Khi ứng dụng có nhiều authorization server, phải áp dụng biện pháp chống **authorization-server mix-up**, chẳng hạn issuer binding/redirect URI riêng theo provider khi phù hợp. Không nhận issuer mới qua query để tải key tùy ý.

### Ví dụ nguy cơ multi-tab/session swap

Tab A: Alice đã đăng nhập và bắt đầu link Google. Tab B: Alice logout, Bob login vào cùng browser. Callback từ tab A quay lại. Nếu code chỉ đọc `SecurityContextHolder.getContext().getAuthentication()` lúc callback rồi gắn Google vào “người hiện tại”, nó có thể liên kết danh tính của Alice vào tài khoản Bob. Pending LINK cần giữ **userId từ lúc start** và xác nhận **local identity/session hiện tại vẫn khớp**. Nếu session ID rotate sau re-auth, phải có cơ chế session binding đúng thiết kế, không giả định raw `JSESSIONID` không bao giờ đổi.

**Fail closed:** state/nonce/PKCE sai, hết hạn, callback lặp, issuer không tin cậy, user/session/version thay đổi hoặc external key thuộc local user khác đều không tạo mapping. Ghi log metadata an toàn nhưng không log code, token hay cookie.

## 4. Spring Security 6.x: oauth2Login hỗ trợ xác minh, không tự link

Với ứng dụng Spring Boot 3.x / Java 17+, khai báo thư viện `spring-boot-starter-oauth2-client` và cấu hình provider tin cậy. Ví dụ `application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          external-a:
            provider: external-idp
            client-id: demo-client
            client-secret: configured-in-secret-manager
            authorization-grant-type: authorization_code
            scope: [openid, profile, email]
        provider:
          external-idp:
            issuer-uri: https://idp.example.test/realms/main
~~~

Các URL ở `example.test` chỉ minh họa, không phải IdP thật. `client-secret` phải lấy từ secret store/env trong production, không hardcode. Với public clients, PKCE/client authentication policy khác.

Cấu hình cơ sở:

~~~java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http)
        throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/login", "/error").permitAll()
            .requestMatchers("/settings/external-links/**")
                .authenticated()
            .anyRequest().authenticated())
        .oauth2Login(Customizer.withDefaults())
        .build();
}
~~~

Cần import `HttpSecurity`, `SecurityFilterChain`, `Customizer`. **Đây chỉ là snippet bật login và bảo vệ Settings**, không phải hệ thống link/unlink hoàn chỉnh. `.authenticated()` không đủ để bảo đảm fresh MFA/re-auth; service phải có policy này, và route callback chuyên dụng phải được cấu hình hợp lý với giao thức.

### Lấy ID ngoài từ OidcUser đã được xác minh

Khi OAuth2/OIDC login thành công theo framework, Spring Security có thể tạo `OAuth2AuthenticationToken` với principal `OidcUser`. Có thể lấy `issuer + subject` như sau (snippet đặt trong class Java có imports và phương thức):

~~~java
import org.springframework.security.oauth2.client.authentication.OAuth2AuthenticationToken;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;

record ExternalKey(String issuer, String subject) {}

static ExternalKey externalKey(OAuth2AuthenticationToken auth) {
    if (!(auth.getPrincipal() instanceof OidcUser oidcUser)) {
        throw new IllegalArgumentException("OIDC identity required");
    }
    var idToken = oidcUser.getIdToken();
    if (idToken.getIssuer() == null
            || idToken.getSubject() == null) {
        throw new IllegalArgumentException("missing issuer/subject");
    }
    return new ExternalKey(
        idToken.getIssuer().toString(),
        idToken.getSubject());
}
~~~

**Giới hạn:** snippet lấy thông tin từ ID token **sau** khi framework đã xác minh OIDC flow. Nếu tự gọi `OidcIdToken` constructor từ claims chưa kiểm chứng, snippet không tạo ra bảo mật. `getEmail()` và `email_verified` chỉ là thuộc tính phụ, không phải khóa identity.

### Bẫy khi dùng successHandler cho linking

`oauth2Login()` mặc định là **luồng đăng nhập**. Nó có thể đặt `OAuth2AuthenticationToken` (external principal) làm Authentication hiện tại sau callback, không giữ nguyên principal nội bộ Alice. Vì vậy không được viết “callback thành công → lấy currentUser() → insert mapping” nếu currentUser() lúc đó là người ngoài.

Một cách đúng là **tách flow LINK khỏi LOGIN**, dùng pending intent server-side và callback chuyên dụng dựa trên OAuth2 client/validator của Spring; hoặc tích hợp sâu vào `oauth2Login().successHandler(...)` và authorization request repository với ràng buộc session đã tồn tại, sau đó khôi phục/lưu `SecurityContext` nội bộ bằng `SecurityContextRepository` theo chính sách.

Success handler **một mình** không tạo được account linking an toàn. Khi callback chỉ muốn LINK nhưng Spring OAuth2Login đã lưu authorized client/token theo external principal, phải đánh giá cleanup/re-association `OAuth2AuthorizedClient` và không duy trì bearer/refresh token không cần thiết.

Không triển khai bộ xử lý code/token tự chế chỉ để giữ local session; luôn dùng protocol client/validator tin cậy.

### Hai kho dữ liệu khác nhau

| Nơi lưu | Dùng để làm gì? |
| --- | --- |
| `external_identity(issuer,sub,user_id)` | Xác định external login có quyền mở local account nào |
| `OAuth2AuthorizedClientService` / repository | Lưu OAuth access/refresh token để client gọi API provider |
| `SecurityContextRepository` / HttpSession | Duy trì Authentication giữa các HTTP request local |
| User/role store nội bộ | Phân quyền và trạng thái tài khoản trong ứng dụng |

Mất refresh token không tự xóa mapping liên kết; gỡ mapping không tự revoke mọi access token tại IdP. Phải thiết kế đúng vòng đời từng thành phần.

## 5. Gỡ liên kết (unlink) và xử lý quyền truy cập còn lại

Unlink là thao tác nhạy cảm, bởi nó thay đổi cách tài khoản nội bộ có thể được truy cập. Luồng an toàn:

1. `POST /settings/external-links/{linkId}/unlink` với CSRF; user authenticated bằng principal nội bộ.
2. Fresh re-auth/step-up với phương thức hiện có, không chỉ phiên cookie cũ. Kiểm tra account active.
3. Server load link bằng ID và xác minh **link.localUserId == authenticated localUserId** (ngăn IDOR). Không tin `userId` từ JSON body.
4. Kiểm tra **sau unlink có còn phương thức đăng nhập/khôi phục thực sự dùng được**: password/passkey đã xác minh, external link khác còn ACTIVE hoặc recovery policy. Đếm số dòng không đủ nếu provider khác đang disable.
5. DB transaction: lock account/link, kiểm tra lại owner và version, revoke/delete mapping, tăng `security_version`, ghi audit + outbox notification.
6. Bắt các session cũ re-evaluate hoặc invalidate theo policy, đặc biệt nếu link bị gỡ do nghi compromise. Điều hướng trang Settings.
7. Cleanup OAuth authorized client và yêu cầu revoke grant tại provider khi phù hợp; không khẳng định “đã thu hồi hết” nếu không có xác nhận. Gửi cảnh báo tới contact đã xác minh **trước khi đổi**.

~~~text
POST unlink
  -> authenticated local user + CSRF + fresh step-up
  -> check ownership + alternate viable login method
  -> transaction with lock/version
  -> revoke mapping + bump security_version + audit
  -> notify, invalidate stale sessions, cleanup tokens/grants
  -> future login through removed (iss,sub) must fail
~~~

**Không xóa đường đăng nhập cuối cùng một cách âm thầm.** Khi user chỉ có một linked IdP và không có password/passkey/recovery, phải block unlink hoặc chuyển sang workflow recovery/onboarding phương thức khác. NIST SP 800-63C yêu cầu RP có chính sách rõ khi tài khoản không còn federated identifier và không còn phương thức truy cập/khôi phục.

### Unlink không phải logout hoặc delete provider account

- Unlink: xóa/vô hiệu mapping external → local, chặn lần login tiếp theo qua identity đó.
- Logout local: xóa local Authentication/session.
- Logout ở OP: kết thúc phiên SSO tại provider, không nhất thiết đồng bộ ngay tới app.
- Revoke OAuth grant: hạn chế client tiếp tục dùng access/refresh token tại provider; tùy provider/API.
- Xóa external account: hành động tại provider, không thuộc unlink app.
- Xóa local account: vòng đời dữ liệu nội bộ riêng (có thể có retention/legal constraints).

**Sau unlink, cấm fallback auto-link bằng email**. Nếu ứng dụng có “just-in-time provisioning”, login lại bằng external key đã gỡ có thể được hướng dẫn onboarding tài khoản mới hoặc quy trình liên kết lại có xác minh, nhưng **không được tái truy cập account cũ nhờ email trùng**.

Thông báo bảo mật nên dùng kênh đã verified trước thay đổi, nêu provider, thời gian và cách khóa account nếu không phải chủ tài khoản. Audit metadata gồm local user, issuer/provider, operation, thời gian, actor, kết quả và request ID; không ghi raw code, refresh/access token hoặc session cookie.

## 6. Java 17 chạy độc lập: kiểm tra uniqueness và unlink-last-method

Đây là **domain simulation** sau khi OIDC identity đã được xác minh ở tầng protocol. Mã không gọi IdP, không xác minh chữ ký JWT và không bảo vệ HTTP/CSRF; nó chỉ diễn đạt quy tắc **không chiếm link của người khác** và **không gỡ đường truy cập cuối**. Có thể compile bằng JDK 17 mà không cần Spring.

Lưu file `ExternalLinkDemo.java`:

~~~java
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;

public class ExternalLinkDemo {

    record Key(String issuer, String subject) {
        Key {
            Objects.requireNonNull(issuer);
            Objects.requireNonNull(subject);
            if (issuer.isBlank() || subject.isBlank()) {
                throw new IllegalArgumentException("empty key");
            }
        }
    }

    enum Link { LINKED, ALREADY_LINKED, CONFLICT }
    enum Unlink { UNLINKED, NOT_OWNER, NOT_LINKED, LAST_METHOD }

    private final Map<Key, String> owner = new HashMap<>();

    // Demo chỉ atomic trong một JVM. Production dùng DB transaction
    // cùng UNIQUE(issuer, subject), row locking.
    synchronized Link link(String localUserId, Key external) {
        Objects.requireNonNull(localUserId);
        Objects.requireNonNull(external);

        String existing = owner.get(external);
        if (existing == null) {
            owner.put(external, localUserId);
            return Link.LINKED;
        }
        return existing.equals(localUserId)
            ? Link.ALREADY_LINKED
            : Link.CONFLICT;
    }

    synchronized Unlink unlink(
            String localUserId, Key external, boolean viableBackup) {
        Objects.requireNonNull(localUserId);
        Objects.requireNonNull(external);
        String current = owner.get(external);
        if (current == null) return Unlink.NOT_LINKED;
        if (!current.equals(localUserId)) return Unlink.NOT_OWNER;
        if (!viableBackup) return Unlink.LAST_METHOD;
        owner.remove(external);
        return Unlink.UNLINKED;
    }

    public static void main(String[] args) {
        ExternalLinkDemo store = new ExternalLinkDemo();
        Key key = new Key("https://idp.example.test", "sub-77");

        System.out.println("first=" + store.link("alice", key));
        System.out.println("again=" + store.link("alice", key));
        System.out.println("conflict=" + store.link("bob", key));
        System.out.println("wrongOwner="
            + store.unlink("bob", key, true));
        System.out.println("lastMethod="
            + store.unlink("alice", key, false));
        System.out.println("removeWithBackup="
            + store.unlink("alice", key, true));
        System.out.println("newLink="
            + store.link("bob", key));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac ExternalLinkDemo.java
java ExternalLinkDemo
~~~

Stdout chính xác, không phụ thuộc thời gian/random:

~~~text
first=LINKED
again=ALREADY_LINKED
conflict=CONFLICT
wrongOwner=NOT_OWNER
lastMethod=LAST_METHOD
removeWithBackup=UNLINKED
newLink=LINKED
~~~

**Các giới hạn cần hiểu:** `localUserId` phải được lấy từ authenticated principal; demo nhận tham số đơn thuần để học quy tắc. `viableBackup` trong production phải do service **tự kiểm tra** bằng trạng thái account/phương thức đăng nhập trong cùng transaction, không đọc boolean từ form. `synchronized` chỉ đồng bộ trong một JVM, không bảo vệ nhiều node; dùng database unique index, transaction/locking và kiểm tra concurrency. Sau unlink, ví dụ cho phép Bob link identity: hệ thống thật có thể cần cooling period, tombstone hoặc giải quyết tranh chấp trước khi gán identity đã từng thuộc user khác.

### JUnit 5 cho quy tắc domain

Nếu đã có JUnit Jupiter, tạo file `ExternalLinkDemoTest.java` ở cùng package với demo:

~~~java
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class ExternalLinkDemoTest {
    @Test
    void existingExternalIdentityCannotBeStolen() {
        var store = new ExternalLinkDemo();
        var key = new ExternalLinkDemo.Key(
            "https://idp.example.test", "subject");

        assertEquals(ExternalLinkDemo.Link.LINKED,
            store.link("alice", key));
        assertEquals(ExternalLinkDemo.Link.ALREADY_LINKED,
            store.link("alice", key));
        assertEquals(ExternalLinkDemo.Link.CONFLICT,
            store.link("bob", key));
    }

    @Test
    void unlinkChecksOwnerAndLastMethod() {
        var store = new ExternalLinkDemo();
        var key = new ExternalLinkDemo.Key(
            "https://idp.example.test", "subject");
        store.link("alice", key);

        assertEquals(ExternalLinkDemo.Unlink.NOT_OWNER,
            store.unlink("bob", key, true));
        assertEquals(ExternalLinkDemo.Unlink.LAST_METHOD,
            store.unlink("alice", key, false));
        assertEquals(ExternalLinkDemo.Unlink.UNLINKED,
            store.unlink("alice", key, true));
    }

    @Test
    void sameSubFromDifferentIssuerIsDifferentIdentity() {
        var store = new ExternalLinkDemo();
        var first = new ExternalLinkDemo.Key("issuer-1", "same-sub");
        var second = new ExternalLinkDemo.Key("issuer-2", "same-sub");

        assertEquals(ExternalLinkDemo.Link.LINKED,
            store.link("alice", first));
        assertEquals(ExternalLinkDemo.Link.LINKED,
            store.link("bob", second));
    }
}
~~~

Test domain không chứng minh OAuth state/nonce/PKCE/session security hay race trên DB production. Những vấn đề ấy đòi integration tests riêng.

## 7. Kiểm thử bảo mật và lỗi thường gặp

### Test matrix

| Tình huống | Kết quả mong muốn |
| --- | --- |
| Link với OIDC identity mới và local step-up hợp lệ | Một mapping `iss/sub → localUserId`, audit và notification |
| Bắt đầu link không có local session | Bị từ chối; không auto-link theo email |
| Callback sau khi logout Alice và login Bob | Từ chối vì pending local identity/session mismatch |
| ID token sai issuer/audience/chữ ký/expiry | Từ chối, không ghi DB |
| `state`, PKCE hoặc `nonce` sai | Từ chối, không tạo link |
| Authorization response từ provider khác | Từ chối mix-up |
| Callback trùng state | Chỉ một lần consume, không replay |
| External key đã thuộc local account khác | 409/deny; không tự merge hoặc chuyển owner |
| Hai request link cạnh tranh ở hai node | Unique constraint, chỉ một commit thắng |
| Email giống nhưng `sub` khác | Không auto-link |
| Unlink link ID của người khác | 403/404 theo policy, không đổi mapping |
| Unlink bằng session cũ chưa re-auth | Cần fresh step-up, không cho xóa |
| Unlink phương thức đăng nhập cuối | Chặn hoặc controlled recovery |
| Unlink xong, identity cũ login lại | Không vào local account cũ kể cả email khớp |
| Session cũ sau unlink | Invalidate/re-evaluate theo security_version |
| OAuth authorized client/token còn trong store | Cleanup/revoke theo policy, không nhầm unlink với revoke |
| Provider account disabled hoặc local account locked | Không cấp local session |
| Thay đổi role/tenant ở IdP | Kiểm tra policy local, không tự trao quyền nội bộ |

Đừng kết luận OAuth flow an toàn chỉ vì test Spring Security `oidcLogin()` tạo được một principal trong `MockMvc`; postprocessor này chủ yếu giả lập Authentication, không thực hiện OAuth callback đầy đủ hoặc xác minh thật chữ ký, state, PKCE/nonce. Cần thêm integration test với IdP test/dummy issuer, JWT ký hợp lệ và sai, hai phiên browser, DB transaction concurrency và token cleanup.

### Mười lỗi kiến trúc chính

1. Auto-link theo `email` hoặc `email_verified` mà không có local authenticated consent.
2. Sử dụng `sub` đơn lẻ thay `iss + sub`, gây collision giữa issuer.
3. Đưa user ID từ request làm chủ sở hữu link thay vì principal nội bộ.
4. Không bind pending state với purpose, session, registration và expiry.
5. Dùng callback link như OAuth login mặc định rồi để external principal thay local account.
6. Bỏ re-auth cho thao tác thêm/gỡ phương thức đăng nhập nhạy cảm.
7. Kiểm tra trùng chỉ ở application layer mà thiếu DB unique constraint.
8. Tự merge hai local accounts khi conflict, gây lộ dữ liệu và quyền.
9. Unlink không chặn fallback auto-link hoặc không có phương thức truy cập thay thế.
10. Nhầm OAuth token/grant, local session và external link: mỗi thứ có vòng đời và cách revoke riêng.

### Checklist trước production

- [ ] Chọn stable local account ID và external key `(validated issuer, validated subject)`.
- [ ] Link bắt đầu từ local session authenticated + CSRF + fresh re-auth/step-up.
- [ ] Pending LINK lưu server-side, có TTL, state, PKCE, nonce, provider allowlist và session binding.
- [ ] Callback kiểm tra OAuth/OIDC đầy đủ; local identity/securityVersion vẫn đúng trước commit.
- [ ] Có DB unique constraint, transaction, chống duplicate/replay và conflict ownership.
- [ ] Unlink kiểm tra user sở hữu link và vẫn còn viable alternate/recovery.
- [ ] Bảo đảm logout/token cleanup/session invalidation đúng chính sách, không tuyên bố revoke sai.
- [ ] Thông báo và audit không tiết lộ token, code, cookie hoặc PII không cần thiết.
- [ ] Test negative cases: login CSRF, state injection, swap session, race, last-method, stale session.
- [ ] Provider có chính sách issuer/tenant/pairwise subject và onboarding/merge riêng.

**Kết luận:** Spring Security hỗ trợ xác thực OIDC/OAuth2, nhưng **liên kết tài khoản ngoài với ID nội bộ là nghiệp vụ bảo mật của ứng dụng**. Luôn đòi authenticated local session, external identity đã verify, ràng buộc transaction chống CSRF/replay và lưu mapping theo cặp `iss + sub`. Khi unlink, phải chặn đăng nhập bằng identity đã gỡ mà không vô tình làm mất phương thức phục hồi tài khoản.

## 8. Tài liệu chuẩn

- OpenID Connect Core 1.0, Claim Stability and Uniqueness: https://openid.net/specs/openid-connect-core-1_0.html
- NIST SP 800-63C-4, Account Linking: https://pages.nist.gov/800-63-4/sp800-63c.html
- OWASP Authentication Cheat Sheet — Secure Federated Account Linking: https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html
- OWASP OAuth2 Cheat Sheet — state/PKCE/nonce/mix-up: https://cheatsheetseries.owasp.org/cheatsheets/OAuth2_Cheat_Sheet.html
- Spring Security — OAuth2 Client/Login: https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/index.html
- Spring Security — Advanced OAuth2 Login: https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/login/advanced.html
- Spring Security 6.5 — OidcUser Javadoc: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/core/oidc/user/OidcUser.html
- Spring Security — Authorized Clients: https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/client/authorized-clients.html
- RFC 9700 — OAuth 2.0 Security Best Current Practice: https://www.rfc-editor.org/rfc/rfc9700.html
