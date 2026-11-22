# Liên kết tài khoản an toàn và không tin email chưa được xác minh

> **Bối cảnh:** Spring Security Servlet, đăng nhập bằng OAuth2/OpenID Connect (OIDC) và liên kết tài khoản của nhà cung cấp danh tính (Identity Provider, IdP) vào một tài khoản ứng dụng đã tồn tại. Nội dung tập trung vào việc chống **account takeover** (chiếm đoạt tài khoản) và bảo vệ nguồn gốc của danh tính.

## Mục tiêu học tập

Sau bài học, bạn có thể phân biệt **đăng nhập IdP**, **liên kết danh tính ngoài** và **cấp quyền cho tài khoản nội bộ**; xác định cặp khóa OIDC `(iss, sub)`; giải thích chính xác giới hạn của `email_verified`; thiết kế luồng liên kết phải chứng minh quyền sở hữu **cả hai tài khoản**; và triển khai đúng các điểm kiểm soát Spring Security, cơ sở dữ liệu, session, state và callback.

**Quy tắc nền tảng:** Cùng email **không có nghĩa** hai tài khoản cùng một chủ. Không bao giờ tự liên kết một IdP identity chưa được gắn với local user chỉ vì email giống nhau, đặc biệt khi email chưa được xác minh. Kể cả email đã verified, việc gộp tài khoản đang tồn tại vẫn cần chính sách và bằng chứng sở hữu rõ ràng.

## 1. Bài toán: một người dùng, nhiều phương thức đăng nhập

Ứng dụng của bạn có local account:

```text
local_users
  id         = 42
  username   = mai
  email      = mai@example.org
  status     = ACTIVE
  role       = MEMBER
```

Người dùng nhấn “Đăng nhập với IdP”. Sau khi hoàn tất OpenID Connect, IdP trả ID Token (ví dụ minh họa các claim danh tính):

```json
{
  "iss": "https://idp.example.org",
  "sub": "user-abc-123",
  "aud": "my-application-client-id",
  "email": "mai@example.org",
  "email_verified": false
}
```

Nếu backend lấy `email` trong token để chạy `SELECT * FROM local_users WHERE email=?` rồi coi user #42 là người vừa đăng nhập, một kẻ tấn công chỉ cần tạo danh tính IdP có email khai báo giống email của nạn nhân. Đây là **vulnerable account linking**, có thể dẫn tới chiếm đoạt dữ liệu và quyền nội bộ.

**Luồng sai:**

```text
OIDC authentication thành công cho (iss=idp, sub=attacker-01)
   → email = mai@example.org (chưa xác minh)
   → tìm local account theo email
   → gán session vào local user #42        ❌
```

**Luồng đúng:**

```text
OIDC authentication thành công
   → kiểm tra (iss, sub) bằng identity đã xác minh
   → tra external_account_links(issuer, subject)
        ├─ Đã liên kết user #42 → nạp local user #42, áp chính sách account/role
        └─ Chưa liên kết → chưa có local account nào được chứng minh;
                           yêu cầu user đăng nhập local account để liên kết,
                           hoặc đi qua quy trình đăng ký MỚI riêng biệt
```

Khi **liên kết thêm một IdP** cho tài khoản #42, cần người dùng chứng minh họ đang kiểm soát local account #42, chủ động yêu cầu liên kết, rồi hoàn thành xác thực với đúng IdP account sẽ liên kết. Chỉ sau hai bằng chứng đó mới ghi bản ghi liên kết.

## 2. OAuth2, OIDC, ID Token và các claim định danh

**OAuth 2.0** tập trung vào ủy quyền: ứng dụng lấy access token theo grant để gọi tài nguyên ở một dịch vụ khác. Một **access token không mặc nhiên là ID Token**, và không nên dùng payload không được kiểm chứng của nó làm bằng chứng ai vừa đăng nhập. **OpenID Connect** thêm các quy tắc xác thực user và **ID Token**.

| Claim/dữ liệu | Ý nghĩa | Có nên dùng làm khóa nhận diện local account? |
|---|---|---|
| `iss` | Issuer URL của IdP phát hành ID Token | **Có, cùng với `sub`**, khi token đã được xác minh |
| `sub` | Subject ID, duy nhất trong phạm vi issuer và chính sách OIDC subject của client | **Có, cùng với `iss`** |
| `email` | Email của user do IdP cung cấp; có thể đổi, trùng, được cấp lại | **Không** |
| `email_verified` | IdP tuyên bố đã thực hiện bước xác nhận email tại thời điểm kiểm tra | **Không**, là metadata về email |
| `preferred_username`, `name`, `picture` | Thông tin hiển thị | **Không** |
| `aud` | Client/audience của ID Token | Phải xác minh trong **token validation**, không là user key |
| OAuth access token | Quyền gọi tài nguyên được cấp cho client | Không thay cho OIDC login |
| Spring `registrationId` | Tên cấu hình OAuth Client trong ứng dụng (ví dụ `corp`) | Không thay thế cặp `iss + sub` |

Theo **OpenID Connect Core `5.7`**, cặp `iss` và `sub` là định danh duy nhất/ổn định mà relying party có thể dựa vào; `email` có thể đổi hoặc bị sử dụng lại. `sub` là chuỗi phân biệt chữ hoa/thường và có thể là **pairwise subject** tùy chính sách của IdP, client hoặc sector identifier. Việc migrate client/provider phải có quy trình đối chiếu; không tự nối danh tính mới vào người dùng cũ chỉ vì email trùng.

### 2.1. Hiểu đúng `email_verified`

- **`true`:** IdP khẳng định họ đã có bước xác nhận end-user kiểm soát email tại thời điểm xác minh. Đây **không** phải cam kết vĩnh viễn rằng email không thay đổi chủ, cũng không chứng minh người đó sở hữu một local account có email khớp.
- **`false`:** không có xác nhận email. Không tự dùng email này để đăng nhập vào local account đang tồn tại, liên kết, nâng quyền, hay đánh dấu email của ứng dụng đã verified.
- **Thiếu claim:** phải xem trạng thái email là **không được xác minh theo claim đó**. Không suy luận `true` vì email thuộc tên miền doanh nghiệp, vì user có tên giống nhau, hay vì IdP nổi tiếng.
- **Claim bị gửi ở UserInfo:** nếu dùng `email` và `email_verified` từ UserInfo, bắt buộc đối chiếu `sub` từ UserInfo **khớp chính xác** `sub` ID Token và kiểm tra nguồn/provider đúng; không ghép cờ verified của một người với email của một người khác.

Quan trọng: **Không dùng `email_verified=true` làm căn cứ duy nhất để gộp hai tài khoản đã có dữ liệu hoặc quyền.** Email không phải khóa bất biến của OIDC. Có thể dùng email verified cho những việc như hiển thị hồ sơ, liên hệ, hoặc áp dụng quy trình xác minh riêng, nếu chính sách IdP/ứng dụng cho phép.

### 2.2. Khi `email_verified=false` nhưng user chủ động liên kết

Nếu chủ local user #42 đã đăng nhập, xác thực lại gần đây, và hoàn tất OIDC login với danh tính ngoài có `(iss,sub)` hợp lệ, ứng dụng **có thể** cho phép gắn danh tính ngoài đó vào #42 theo chính sách tin cậy IdP, dù email IdP không trùng hoặc chưa verified. Việc liên kết an toàn đến từ **bằng chứng quyền kiểm soát local account + bằng chứng kiểm soát external account + ý định liên kết**, không phải từ email IdP. Tuy nhiên, email IdP vẫn **không được đánh dấu verified** hay dùng làm email khôi phục nếu chưa được chứng minh riêng.

### 2.3. Provider chỉ có OAuth2, không hỗ trợ OIDC

Với provider OAuth2 không phát ID Token chuẩn, ứng dụng phải làm theo tài liệu provider: sử dụng access token đúng API/đối tượng, lấy provider user ID bền vững và định nghĩa namespace/provider/tenant rõ ràng. Các trường tùy biến `email`, `verified` của provider **không tự động** mang ngữ nghĩa OIDC. Không suy diễn rằng OAuth access token là bằng chứng danh tính dành cho application. Bài này ưu tiên OIDC vì `iss + sub` có ý nghĩa xác thực được chuẩn hóa.

## 3. Năm tình huống chiếm đoạt tài khoản phổ biến

### 3.1. Email spoofing ở IdP

Attacker tạo user IdP, tự khai email `victim@example.org`, `email_verified=false`. Backend dùng email để tìm local user và cấp quyền cho attacker.

**Ngăn chặn:** lookup local login chỉ qua bảng liên kết chính thức theo `(iss,sub)`. IdP account chưa được link phải trải qua luồng khác.

### 3.2. Email verified nhưng bị cấp lại hoặc đổi chủ

Một email từng thuộc người A, sau đó chuyển cho B; IdP có thể đã verified ở một thời điểm. Việc cùng email không chứng minh B là chủ tài khoản nội bộ A. Đặc tả OIDC cũng không bảo đảm `email` duy nhất và bất biến.

**Ngăn chặn:** không tự merge local account cũ bằng email kể cả `email_verified=true`; yêu cầu local login/reauth và explicit link.

### 3.3. Link CSRF, session swap, đăng nhập nhầm IdP account

Nếu ứng dụng không gắn OAuth callback với hành động chủ động của local user, attacker có thể khiến victim xác nhận callback cho **IdP account của attacker**. Sau đó attacker đăng nhập IdP của mình và có thể truy cập local account của victim.

**Ngăn chặn:** OAuth `state`, OIDC `nonce`, PKCE theo profile, CSRF protection, **link intent** dùng một lần ở server gắn với session/local account/provider, xác thực lại và màn hình confirm. `state` đúng là cần thiết nhưng chưa đủ nếu logic không kiểm tra **ai yêu cầu liên kết**.

### 3.4. Hai account cùng liên kết một external subject

Hai local accounts cùng cố gắn một `(iss,sub)`. Nếu ứng dụng làm “SELECT chưa thấy → INSERT” không có unique constraint, cả hai request đồng thời có thể thành công hoặc tạo dữ liệu mâu thuẫn.

**Ngăn chặn:** unique constraint tại database, transaction, idempotency và chính sách conflict: nếu external account đã thuộc local user khác thì **từ chối**, không tự chuyển chủ sở hữu.

### 3.5. Nhận ID Token không hợp lệ hoặc IdP khác tenant

Attacker tự tạo JWT có `sub`, `email` như ý rồi gửi cho backend. Base64 decode đọc được payload không có nghĩa token đã được IdP tin cậy ký và dành cho ứng dụng.

**Ngăn chặn:** xác minh chữ ký, thuật toán, `iss` theo ClientRegistration allowlist, `aud` phù hợp client, thời hạn `exp`, luồng `nonce/state` và sự nhất quán dữ liệu UserInfo. Định danh/tenant ngoài phạm vi cho phép phải bị từ chối.

## 4. Thiết kế bảng liên kết an toàn

Giữ **ID local bất biến** độc lập với identity bên ngoài. Ví dụ PostgreSQL, giả định đã có bảng `local_users(id BIGINT PRIMARY KEY, ...)`:

```sql
CREATE TABLE external_account_links (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    local_user_id BIGINT NOT NULL REFERENCES local_users(id),
    issuer VARCHAR(512) NOT NULL,
    subject VARCHAR(255) NOT NULL,
    linked_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT external_link_key_unique UNIQUE (issuer, subject),
    CONSTRAINT external_link_key_not_empty CHECK (issuer <> '' AND subject <> '')
);

CREATE INDEX external_links_by_local_user
    ON external_account_links(local_user_id);
```

**Các bất biến dữ liệu:**

1. Một `(issuer,subject)` chỉ có **một** owner local, ngay cả khi nhiều request xảy ra đồng thời.
2. Đổi email local hoặc IdP không làm đổi khóa link.
3. Không dùng `email`, `name`, `preferred_username` hoặc `registrationId` làm unique key thay `iss+sub`.
4. Khi một external account đã thuộc user #99, user #42 không thể âm thầm “giành” bằng câu `UPDATE local_user_id=42`. Cần quy trình chuyển quyền có xác minh riêng.
5. Nếu sản phẩm cho phép một local user có nhiều external accounts, bảng này hỗ trợ; nếu chỉ cho một account mỗi provider, thêm unique business rule được duyệt riêng.
6. Nếu provider có multi-tenant hoặc subject cấp theo từng client, lưu định danh/tenant cần thiết và kiểm tra khi migrate. Đừng mặc định hai cấu hình trùng tên đăng nhập hay trùng email là cùng user.

Login qua OIDC đã được xác minh sẽ tìm:

```sql
SELECT local_user_id
FROM external_account_links
WHERE issuer = :validated_iss
  AND subject = :validated_sub;
```

Khi link sau khi xác thực cả hai phía:

```sql
INSERT INTO external_account_links(local_user_id, issuer, subject)
VALUES (:authenticated_local_user_id, :validated_iss, :validated_sub);
```

Đặt transaction cùng cơ chế tiêu thụ link intent và xử lý `UNIQUE` conflict. Nếu insert bị xung đột, tải owner hiện tại: trùng owner có thể trả `ALREADY_LINKED`; khác owner trả `CONFLICT`. Cần giải quyết race trong database, không chỉ dùng `synchronized` của một JVM.

## 5. Luồng login: chỉ nhận local owner đã có link

```text
Browser
   → Spring Security OAuth2 Login, Authorization Code Flow
   → IdP xác thực account ngoài
   → callback /login/oauth2/code/{registrationId}
   → Spring xác minh token và OIDC ID Token
   → identity = (iss, sub)
   → SELECT owner FROM external_account_links WHERE issuer=? AND subject=?
       ├── owner tồn tại, còn active
       │     → thiết lập local Authentication cho owner
       │     → quyền / roles được lấy từ chính sách ứng dụng
       └── chưa có link
             → KHÔNG tìm local_users theo email rồi auto merge
             → yêu cầu local login để link hoặc đi qua onboarding tạo user MỚI
```

**Đã chứng minh IdP account** không đồng nghĩa đã chứng minh local account nào. Khi login chưa linked, backend không được tự gán quyền dựa trên username/email trùng. Nếu sản phẩm có auto-provision user **mới**, nó phải là một quy trình riêng, bảo đảm không chiếm user cũ và tuân thủ invitation, domain/tenant, policies đã phê duyệt.

Nếu đã linked nhưng local account bị khóa, bị xóa hoặc quyền bị thu hồi, ứng dụng vẫn phải tôn trọng trạng thái đó. Một IdP token hợp lệ không được tự khôi phục local user đã disabled.

## 6. Luồng link: chứng minh cả hai tài khoản, gắn intent một lần

1. **Local user đã đăng nhập** vào chính account cần liên kết; server lấy local user ID từ principal/session được xác thực, không lấy từ form `userId`.
2. **Xác thực lại gần đây** (step-up) với mật khẩu/passkey/MFA theo mức nhạy cảm. Không nhận biến `reauth=true` từ request như bằng chứng.
3. Server tạo **link intent** gồm local user ID, session binding, provider/registration được phép, flow ID ngẫu nhiên, thời gian hết hạn ngắn và cờ chưa sử dụng. Chống CSRF tại endpoint bắt đầu.
4. Khởi động **OAuth2 Authorization Code Flow** cho đúng provider, dùng `state`, redirect URI đã đăng ký, nonce OIDC và PKCE khi phù hợp. Không nhận issuer/authorization endpoint tùy ý từ client.
5. IdP xác thực người dùng của **external account** và gửi callback; Spring Security xác minh protocol, ID Token và đối chiếu provider.
6. Ứng dụng khôi phục đúng intent bằng tương quan với OAuth request/`state` và session đã ràng buộc; xác nhận chưa dùng, chưa hết hạn, local owner còn active và step-up còn hiệu lực. Không dùng email IdP, query parameter hoặc ID do client nhập để chọn owner.
7. Hiển thị thông tin IdP account sẽ liên kết và yêu cầu user xác nhận **chính xác account đó**; bảo vệ xác nhận khỏi CSRF/replay.
8. Transaction: tiêu thụ intent một lần, kiểm tra `(iss,sub)` đã có owner chưa và insert vào `external_account_links`. Nếu đã thuộc local user khác, từ chối; có unique constraint để chống race.
9. Giữ/khôi phục **đúng local principal** sau callback. Ghi audit, hiển thị link đã thêm; không giữ raw IdP principal như đã được cấp mọi quyền nội bộ.

Lưu ý khi triển khai: `oauth2Login` mặc định có thể đưa một `OAuth2AuthenticationToken` vào `SecurityContext` sau callback. Trong **linking flow**, ứng dụng cần có lớp quản lý local session/owner và nguyên tắc lưu `SecurityContext`; không được nghĩ rằng callback của IdP tự động giữ nguyên local user trước đó. Nếu có nhiều IdP, chống login/link mix-up và xác nhận đúng issuer của phiên đang chờ.

### 6.1. Quyết định theo từng trường hợp

| Trường hợp | Kết quả đúng |
|---|---|
| ID Token OIDC hợp lệ, `(iss,sub)` đã gắn user #42 đang active | Login user #42 theo quyền nội bộ |
| External identity mới có cùng email với #42, `email_verified=false` | **Không** auto-link/login #42 |
| External identity mới có cùng email với #42, `email_verified=true` | **Không** auto-link/login #42 chỉ từ email |
| User #42 đã chứng minh local session, reauth, xác thực IdP và confirm intent | Có thể link external identity đó theo policy |
| External identity đã thuộc user #99 | Từ chối link vào #42; không chuyển owner |
| Callback sai state/session hoặc intent đã dùng | Từ chối, không ghi bảng link |
| ID Token sai chữ ký, issuer, audience hoặc hết hạn | Từ chối trước khi xử lý dữ liệu user |
| UserInfo `sub` không khớp ID Token `sub` | Không dùng UserInfo, từ chối xác thực |
| Không có email hoặc thiếu `email_verified` | Không coi email verified; vẫn nhận diện được qua `iss+sub` nếu token hợp lệ |

## 7. Java 17: mô phỏng chính sách an toàn có thể chạy độc lập

Ví dụ dưới đây là **mô hình chính sách** để hiểu vì sao không tra theo email. Nó giả định ID Token đã được xác minh và hai cờ step-up/confirm **được server xác thực**, không lấy từ client. Nó chưa làm OIDC, quản lý session, database transaction hoặc CSRF.

Lưu file `AccountLinkingPolicyDemo.java`:

```java
import java.util.HashMap;
import java.util.Map;

public class AccountLinkingPolicyDemo {

    record ExternalKey(String issuer, String subject) {}

    record ExternalIdentity(
        ExternalKey key,
        String email,
        Boolean emailVerified
    ) {}

    static class LinkStore {
        private final Map<ExternalKey, Long> owners = new HashMap<>();

        // Email KHÔNG được dùng để tìm local account.
        synchronized String login(ExternalIdentity identity) {
            Long ownerId = owners.get(identity.key());
            return ownerId == null
                ? "REQUIRE_LOCAL_SIGN_IN"
                : "LOCAL_USER_" + ownerId;
        }

        // Trong ứng dụng thật, hai boolean này phải do server xác minh.
        synchronized String link(
            long localUserId,
            boolean freshReauthentication,
            boolean confirmedIntent,
            ExternalIdentity identity
        ) {
            if (!freshReauthentication || !confirmedIntent) {
                return "REJECT_PROOF_REQUIRED";
            }
            Long oldOwner = owners.putIfAbsent(
                identity.key(), localUserId);
            if (oldOwner == null) {
                return "LINKED";
            }
            return oldOwner == localUserId
                ? "ALREADY_LINKED"
                : "CONFLICT_OTHER_OWNER";
        }
    }

    public static void main(String[] args) {
        LinkStore store = new LinkStore();

        var unverified = new ExternalIdentity(
            new ExternalKey("https://idp.example.org", "sub-A"),
            "mai@example.org", false);
        var verifiedSameEmail = new ExternalIdentity(
            new ExternalKey("https://idp.example.org", "sub-B"),
            "mai@example.org", true);

        System.out.println("Unverified: " + store.login(unverified));
        System.out.println("Verified: " + store.login(verifiedSameEmail));
        System.out.println("No reauth: " +
            store.link(42, false, true, unverified));
        System.out.println("Explicit link: " +
            store.link(42, true, true, unverified));
        System.out.println("After link: " + store.login(unverified));
        System.out.println("Second owner: " +
            store.link(99, true, true, unverified));
    }
}
```

Lệnh biên dịch/chạy với JDK 17+:

```bash
javac AccountLinkingPolicyDemo.java
java AccountLinkingPolicyDemo
```

Stdout chính xác:

```text
Unverified: REQUIRE_LOCAL_SIGN_IN
Verified: REQUIRE_LOCAL_SIGN_IN
No reauth: REJECT_PROOF_REQUIRED
Explicit link: LINKED
After link: LOCAL_USER_42
Second owner: CONFLICT_OTHER_OWNER
```

Điểm cần hiểu: **email đã verified mà trùng địa chỉ vẫn không auto-link**. Cặp `(issuer,subject)` của `verifiedSameEmail` khác cặp của `unverified` và không có liên kết đã được chấp thuận. Liên kết chủ động được phép sau hai bằng chứng độc lập ngay cả khi external email chưa verified; điều đó **không làm email ngoài trở thành email verified của ứng dụng**.

## 8. Spring Security 6 / Spring Boot 3: dùng ID Token đã xác minh

Ví dụ áp dụng cho dự án **Servlet**, Java 17+, Gradle và Spring Boot 3.x.

### 8.1. Dependency

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
```

Đây là OAuth2 Client/Login trong Spring Security. `spring-boot-starter-oauth2-resource-server` dành cho việc xác minh bearer token của request API, **không thay thế** tự động cho OAuth2 Login client.

### 8.2. Cấu hình provider cố định (OIDC discovery)

`src/main/resources/application.yml`:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corp:
            provider: corp
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            scope: [openid, profile, email]
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
        provider:
          corp:
            issuer-uri: ${OIDC_ISSUER_URI}
```

`OIDC_ISSUER_URI` phải được quản trị cấu hình từ trước theo IdP/tenant tin cậy, không cho client tự quyết định. Client secret nằm trong secret manager/environment; redirect URI phải khớp cấu hình IdP, qua HTTPS trong production. `openid` scope cho biết luồng OIDC, sử dụng ID Token để xác thực danh tính.

Spring Security xác minh ID Token qua cơ chế OIDC Login khi cấu hình đúng, bao gồm các yêu cầu như signature, issuer/audience, thời gian và các điều kiện protocol. Không decode JWT bằng Base64 rồi tự tin claim, không tắt validation khi custom decoder hoặc thêm OIDC user service.

### 8.3. Trích xuất khóa sau khi framework xác minh OIDC

Đây là một Java record dùng với dependencies trên, **được gọi sau khi OIDC authentication đã thành công**, không phải hàm kiểm tra chữ ký JWT. Lưu `src/main/java/com/example/security/ValidatedExternalIdentity.java`:

```java
package com.example.security;

import org.springframework.security.oauth2.core.oidc.OidcIdToken;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;

public record ValidatedExternalIdentity(
    String issuer,
    String subject,
    String email,
    boolean emailVerified
) {

    public static ValidatedExternalIdentity from(OidcUser user) {
        OidcIdToken token = user.getIdToken();

        String issuer = token.getClaimAsString("iss");
        String subject = token.getClaimAsString("sub");
        String email = token.getClaimAsString("email");
        boolean verified = Boolean.TRUE.equals(
            token.getClaimAsBoolean("email_verified"));

        if (issuer == null || issuer.isBlank()
                || subject == null || subject.isBlank()) {
            throw new IllegalArgumentException(
                "Missing OIDC issuer or subject");
        }

        return new ValidatedExternalIdentity(
            issuer, subject, email, verified);
    }
}
```

**Tại sao cách này đúng trong phạm vi ví dụ?**

- `OidcUser` đến từ pipeline Spring Security đã xác thực với nhà cung cấp được tin cậy; ví dụ **không** tự parse một JSON/JWT lấy từ request.
- Lấy cả `email` và `email_verified` từ **cùng ID Token**; nếu IdP trả qua UserInfo, phải xác minh `sub` khớp, nguồn dữ liệu và chính sách trước khi lấy.
- Chỉ `iss` và `sub` tham gia khóa liên kết. Email có thể `null`; thiếu verified được coi là `false`.
- Record chỉ tạo dữ liệu danh tính; nó **không** tự tìm hoặc ghép với local account. Không xem `emailVerified` là một permission.
- Nếu môi trường đa tenant, lớp xử lý gọi record còn phải so issuer/provider/tenant với config allowlist và định danh mong đợi của link intent.

### 8.4. Điểm tích hợp trong Spring Security

Spring cung cấp các thành phần:

- `http.oauth2Login(...)`: bắt đầu/hoàn tất authorization code login; URL khởi tạo mặc định `/oauth2/authorization/{registrationId}` và callback `/login/oauth2/code/{registrationId}`.
- `oauth2Login().userInfoEndpoint().oidcUserService(...)`: tùy biến xử lý user profile hoặc nạp authorities nếu cần.
- `oauth2Login().successHandler(...)`: tích hợp logic login/linking sau khi OIDC authentication thành công.
- `OAuth2AuthenticationToken`: có principal và `authorizedClientRegistrationId`, giúp đối chiếu với provider dự kiến.
- `OAuth2AuthorizationRequestRepository`: liên hệ authorization request với callback; **link intent** nghiệp vụ cũng phải ràng buộc chặt với flow/`state`.
- `SecurityContext` và `SecurityContextRepository`: phải giữ/lưu đúng principal **local account** sau login hoặc link. Nếu callback đang ở principal IdP, không để principal ấy được cấp quyền local khi chưa có mapping.

Ví dụ **chỉ về điểm móc**, không phải một cấu hình Spring Boot đầy đủ:

```java
http.oauth2Login(oauth2 -> oauth2
    .successHandler(accountMappingOrLinkSuccessHandler)
);
```

`accountMappingOrLinkSuccessHandler` là handler do ứng dụng **phải tự triển khai** với local repository, link intent store, transaction và khôi phục security context. Không tồn tại sẵn lớp tên đó trong Spring Security. Cũng không được cấu hình `oauth2Login(...)` rồi coi mọi `OAuth2AuthenticationToken` là một local user được cấp quyền: callback OIDC thành công chỉ xác thực **external account**, chưa quyết định owner nội bộ.

### 8.5. Pseudocode xử lý callback, chỉ rõ điều kiện bảo mật

Đây là **thuật toán nghiệp vụ minh họa**, không phải Java class độc lập để copy vào project:

```text
onOidcCallback(verifiedOidcUser, authorizationState, currentSession):
    ext = (verifiedOidcUser.idToken.iss, verifiedOidcUser.idToken.sub)
    require ext.iss is expected trusted issuer for this registration

    if linkIntentExistsFor(authorizationState):
        intent = loadAndValidateIntent(
            authorizationState,
            sameBoundSession,
            expectedProvider,
            unexpired,
            unused,
            localOwnerStillEnabled,
            recentLocalReauthentication
        )
        require userConfirmedThisExternalIdentity
        transaction:
            atomicallyConsumeIntentExactlyOnce(intent)
            owner = findLocalOwner(ext.iss, ext.sub)
            if owner exists and owner != intent.localUserId:
                reject conflict
            if owner absent:
                insertLink(intent.localUserId, ext.iss, ext.sub)
                // UNIQUE(issuer,subject) resolves concurrent race
        restoreAuthenticatedLocalPrincipal(intent.localUserId)
        show linked account success
    else:
        owner = findLocalOwner(ext.iss, ext.sub)
        if owner exists and owner is active:
            establishAuthenticatedLocalPrincipal(owner)
        else:
            do not search existing local users by email to auto-link
            show safe sign-in/link or new-account onboarding
```

Cách lưu intent có thể là session store/Redis/database có TTL và atomic consume. Phải bảo đảm callback từ **login thường** không tự giả làm callback từ **liên kết**, và ngược lại; không dựa vào query string `?link=true` hoặc `localUserId=42` do client tự cung cấp.

## 9. Email hồ sơ, email thông báo và kênh khôi phục

Nên phân biệt ít nhất ba trạng thái:

1. **Email local**: do ứng dụng quản lý, với xác minh local riêng (nếu có).
2. **Email IdP**: chỉ là profile claim kèm issuer, thời điểm thu thập và trạng thái đã được IdP xác minh hay chưa.
3. **Email đủ tin cậy để gửi reset password/MFA**: tuân thủ chính sách sở hữu kênh khôi phục của ứng dụng, không tự suy từ external profile.

Không tự ghi đè email khôi phục đã verified ở local account bằng email IdP mới hoặc `email_verified=false`. Khi IdP đổi email nhưng `(iss,sub)` vẫn như cũ, liên kết có thể tiếp tục hợp lệ trong điều kiện provider policy; việc cập nhật email liên hệ phải là quy trình riêng.

Trong UI, tránh thông báo giúp attacker liệt kê email đã đăng ký, như “email này thuộc user #42”. Có thể hiển thị thông điệp chung “Nếu bạn đã có tài khoản, hãy đăng nhập để liên kết phương thức này” mà không xác nhận account tồn tại hay không.

## 10. Unlink, thu hồi, đa tenant và vòng đời tài khoản

- **Unlink** là hành động nhạy cảm: yêu cầu local user xác thực lại, confirm, audit, transaction và cơ chế tránh lockout.
- **Phương thức cuối cùng:** không cho gỡ liên kết đăng nhập duy nhất nếu tài khoản chưa có cách đăng nhập/khôi phục thay thế đáng tin.
- **Account disabled:** khi local user bị khóa hoặc vô hiệu hóa, IdP login có liên kết đúng cũng không tự mở lại quyền.
- **Issuer/client migration:** không gán lại chủ bằng email khi nhà cung cấp đổi tenant, issuer, client ID, subject strategy; cần quy trình migrate được phê duyệt.
- **Nhiều tenant có username/email trùng:** kiểm tra issuer, tenant hoặc quy tắc provider riêng; không merge quyền tenant dựa trên email.
- **IdP bị thu hồi:** triển khai cách hủy external link/session theo rủi ro; không mặc định login token cũ có thể khôi phục link đã revoke.
- **Token & audit:** không lưu/log raw OAuth code, ID/access/refresh token, session cookie hay secret; nếu cần lưu token để gọi API, sử dụng store bảo mật riêng. Audit có thể lưu ID nội bộ, issuer, subject reference đã bảo vệ, thời gian và kết quả liên kết.

## 11. Kịch bản kiểm thử cần có

| Kiểm thử | Dữ liệu | Kỳ vọng |
|---|---|---|
| Email spoof chưa verified | Local #42 có `mai@example.org`; IdP attacker cũng khai email đó, `email_verified=false` | Không auto-link/login #42 |
| Email verified trùng | IdP mới có `email_verified=true` nhưng `sub` chưa linked, email trùng #42 | Không tự gộp #42 |
| Thiếu verified | Có `email`, thiếu `email_verified` | Coi email chưa verified, không dùng làm login key |
| Không có email | Token hợp lệ có `iss+sub`, thiếu email | Login theo link nếu có; nếu chưa linked thì quy trình riêng |
| Đổi email IdP | Cùng `iss+sub`, email đổi | Link owner không đổi; email local không tự bị thay |
| Hai IdP cùng `sub` | Issuer khác nhau, subject trùng ký tự | Hai identity khác nhau |
| Đã linked | `iss+sub` ánh xạ local #42 active | Login #42, roles theo ứng dụng |
| Active link intent | #42 đăng nhập local, step-up, callback OIDC hợp lệ, confirm đúng account | Link duy nhất tới #42 |
| Không có recent reauth | Local session cũ, thiếu step-up | Từ chối link |
| Link CSRF | Attacker cố đưa callback IdP account của họ vào session victim | State/session/intent check thất bại |
| Callback replay | Trùng state/intent sau khi đã dùng | Không tạo/đổi liên kết |
| Wrong provider | Issuer của token khác provider trong intent | Từ chối |
| Sai token | Chữ ký, `aud`, `iss`, exp hoặc nonce không hợp lệ | Từ chối trước policy |
| UserInfo `sub` khác | Subject UserInfo khác ID Token | Từ chối thông tin UserInfo/xác thực |
| Cùng external identity, hai owners | #42 và #99 race insert | Chỉ một owner nhờ unique constraint, bên kia conflict |
| Local disabled | IdP link còn nhưng local account locked | Không cấp quyền |
| Unlink cuối cùng | Không còn phương thức đăng nhập nào khác | Yêu cầu phương thức khôi phục hợp lệ trước khi unlink |

**Kiểm thử tích hợp Spring Security và browser session:**

1. Tạo link intent dưới local principal A, thử callback bằng session B hoặc provider khác → phải từ chối.
2. Sau OIDC callback, kiểm tra principal trong `SecurityContext` chính là local owner đã ánh xạ, không phải external principal được cấp quyền tạm.
3. Thử thay `state`, dùng code đã tiêu thụ, thay issuer hoặc đưa JSON “`email_verified=true`” tự tạo → không bypass được xác minh.
4. Cho hai transaction link cùng `(iss,sub)` ở hai nodes → database vẫn chỉ có một owner.
5. Disable user nội bộ hoặc revoke link; request sau không được khôi phục quyền từ email trùng.
6. Kiểm tra log: không có ID Token, access token, authorization code, refresh token, session secret hoặc PII không cần thiết.

## 12. Những sai lầm cần tránh

| Sai lầm | Cách hiểu/thiết kế đúng |
|---|---|
| “OIDC trả cùng email nên là cùng người.” | Email không phải định danh ổn định/duy nhất; dùng `iss+sub` và link đã duyệt. |
| “`email_verified=true` cho phép gộp tài khoản cũ.” | Verified là thuộc tính email tại thời điểm xác minh, không là quyền sở hữu local account. |
| “Spring OAuth2 Login tự xử lý account linking.” | Framework thực hiện protocol authentication; việc ánh xạ local owner/link intent là logic ứng dụng. |
| “Chỉ cần decode JWT là đủ.” | Phải xác minh signature, issuer, audience, thời gian và điều kiện protocol. |
| “Kiểm tra chưa có link bằng SELECT là tránh được đua ghi.” | Cần unique constraint ở database và transaction. |
| “User đăng nhập IdP là có luôn ROLE_ADMIN ở local.” | Quyền local phải nạp/đánh giá riêng; không tự cấp theo email hoặc profile của IdP. |
| “Tắt CSRF vì OAuth đã có state.” | State bảo vệ OAuth response; endpoint start/confirm link vẫn cần kiểm soát ý định, phiên, reauth và CSRF. |
| “Đổi email thì chuyển liên kết sang user có email mới.” | Link giữ theo `iss+sub`; đổi ownership phải qua quy trình xác minh độc lập. |

## 13. Tự kiểm tra kiến thức

**Câu 1:** `email_verified=false` mà email trùng local user có được đăng nhập local user đó không?  
**Trả lời:** Không. Danh tính ngoài chưa có link không chứng minh quyền truy cập local account bằng email.

**Câu 2:** `email_verified=true` thì có tự động liên kết với local user đã đăng ký cùng email không?  
**Trả lời:** Không nên. OIDC không bảo đảm email không trùng/không đổi; liên kết local account cũ cần bằng chứng sở hữu cả hai tài khoản và ý định rõ ràng.

**Câu 3:** Vì sao phải lưu cặp `iss` và `sub` thay vì chỉ `sub`?  
**Trả lời:** `sub` chỉ có ý nghĩa duy nhất trong phạm vi issuer; hai issuer có thể phát cùng chuỗi subject cho người khác nhau.

**Câu 4:** Chỉ cần OAuth `state` là đủ để liên kết an toàn?  
**Trả lời:** Không. Cần thêm link intent ràng buộc local account, phiên, provider, hạn dùng, xác thực lại, xác nhận và xử lý atomic.

**Câu 5:** Tại sao database phải có `UNIQUE(issuer,subject)`?  
**Trả lời:** Nó ngăn hai local users trở thành owner của cùng external identity khi có request đồng thời.

**Câu 6:** User đổi email ở IdP thì thay đổi bản ghi liên kết thế nào?  
**Trả lời:** Giữ định danh `(iss,sub)`; email liên hệ/khôi phục có quy trình cập nhật và xác minh riêng.

## Tài liệu tham khảo

- [OpenID Connect Core 1.0 — Standard Claims, UserInfo và Claim Stability (`5.1, `5.3.2, `5.7)](https://openid.net/specs/openid-connect-core-1_0.html): `iss`, `sub`, `email_verified`, tính duy nhất/ổn định, kiểm tra UserInfo `sub`.
- [Spring Security — OAuth2 Login Core Configuration](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html): ClientRegistration, issuer URI, redirect callback và cấu hình cơ bản.
- [Spring Security — OAuth2 Login Advanced Configuration](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html): `OidcUserService`, ID Token validation, user mapping và điểm mở rộng.
- [Spring Security — Servlet OAuth2 Overview](https://docs.spring.io/spring-security/reference/servlet/oauth2/index.html): phân biệt OAuth2 Client/Login với Resource Server, vai trò ID Token của OIDC.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700.html): bảo vệ authorization code flow, redirect, mix-up và request/response correlation.
