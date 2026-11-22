# Định danh người dùng OIDC bằng cặp issuer và subject

Trong **OpenID Connect (OIDC)**, ứng dụng **Relying Party (RP/client)** cần một khóa định danh ổn định để trả lời câu hỏi: *“Người vừa đăng nhập có đúng là tài khoản nội bộ đã biết trước đó không?”* Câu trả lời chuẩn là **cặp `(iss, sub)` từ một ID Token đã được xác minh**, không phải email, username, số điện thoại, tên hiển thị hoặc một `sub` đứng riêng.

- **`iss` (Issuer):** định danh chính xác của **OpenID Provider (OP)** phát hành ID Token, ví dụ `https://login.example.test/realms/staff`.
- **`sub` (Subject):** định danh người dùng **duy nhất trong phạm vi issuer đó** và theo OIDC Core không được tái cấp cho người dùng khác.
- **`(iss, sub)`:** khóa liên kết người dùng bên ngoài với **một tài khoản nội bộ**; chỉ có ý nghĩa tin cậy khi token và toàn bộ ngữ cảnh OIDC đã được xác minh.

Ví dụ hai OP có thể cùng phát `sub="12345"` cho **hai người hoàn toàn khác nhau**:

| Issuer | Subject | Định danh RP phải coi |
| --- | --- | --- |
| `https://idp-a.example.test` | `12345` | Người A của OP A |
| `https://idp-b.example.test` | `12345` | Người B của OP B |
| `https://idp-a.example.test` | `67890` | Người C của OP A |

**Không bao giờ** tra cứu người dùng chỉ theo `sub=12345` khi ứng dụng tin nhiều OP. Đặc biệt trong kiến trúc **identity broker** (môi giới danh tính), OP mà ứng dụng trực tiếp tin có thể là **broker**, không phải upstream IdP thực hiện mật khẩu/MFA. Cặp danh tính mà RP nhìn thấy khi đó là **`(broker_iss, broker_sub)`**, không tự động là cặp của upstream.

Bài thuộc **Spring Security – federation → OIDC và môi giới**, tập trung vào thiết kế khóa danh tính, phân biệt public/pairwise subject, broker và upstream OP, account linking, Spring Security OAuth2 Login, phân quyền theo tenant, ví dụ Java 17 có stdout xác định và bài kiểm thử bảo mật.

## 1. OIDC, OP, RP và identity broker là gì?

**OIDC** bổ sung lớp **authentication/identity** trên OAuth 2.0. Với Authorization Code Flow, RP gửi người dùng tới OP, nhận authorization code, trao đổi code lấy token, sau đó xác minh **ID Token** để biết OP đã xác thực subject nào.

| Khái niệm | Giải thích | Vai trò với định danh |
| --- | --- | --- |
| **OP / Issuer** | Hệ thống phát hành ID Token | Không gian tên của `sub` |
| **RP / OAuth2 Client** | Ứng dụng tin một hoặc nhiều OP | Lưu mapping `(iss,sub)` → account nội bộ |
| **ID Token** | JWT chứa claims xác thực, được xác minh theo OIDC | Nguồn `iss`, `sub`, `aud` và ngữ cảnh login |
| **UserInfo** | Endpoint cung cấp claims bổ sung | Có `sub`; phải khớp `sub` của ID Token |
| **Identity broker** | OP trung gian liên kết nhiều upstream IdP | Phát `iss` và `sub` của **chính broker** cho RP |
| **Upstream IdP** | Google, LDAP bridge, SAML IdP hoặc OP phía trước broker | Cung cấp bằng chứng cho broker, không nhất thiết RP trực tiếp xác minh |
| **Local account** | Hồ sơ người dùng trong database của ứng dụng | ID ổn định để gắn dữ liệu, quyền, tenant |
| **Federated identity link** | Bản ghi liên kết issuer+subject với account | Cầu nối danh tính đã được quản trị |

### Hai kiến trúc phổ biến

**RP kết nối trực tiếp nhiều OP:**

~~~text
                   Spring Security RP
                      /         \
                     /           \
          OP Corp / issuer A   OP Partner / issuer B
                  |                 |
                sub A             sub B
                   \               /
                  Identity links trong DB
                           |
                      Local accounts
~~~

**RP kết nối qua một identity broker:**

~~~text
              Spring Security RP
                     |
       ID Token iss = https://broker.example.test
       ID Token sub = broker-user-271
                     |
                 OIDC Broker
                /           \
             Upstream A    Upstream B
              (OIDC)        (SAML)
               |             |
          upstream sub    SAML NameID
                     |
          Chính sách liên kết của broker
~~~

Ở mô hình thứ hai, RP thường **không có đầy đủ token/bằng chứng gốc của upstream**. RP chỉ trực tiếp xác minh ID Token của broker và tin broker trong phạm vi hợp đồng. Không tự coi `sub` của broker là `sub` của upstream.

## 2. ID Token là nguồn định danh; phải xác minh trước khi dùng

Ví dụ payload JSON đã giải mã để đọc:

~~~json
{
  "iss": "https://login.example.test/realms/staff",
  "sub": "usr-7h2v8",
  "aud": "portal-web",
  "iat": 1794042000,
  "exp": 1794045600,
  "email": "person@example.test",
  "email_verified": true,
  "name": "Người dùng minh họa"
}
~~~

Đây là **payload minh họa**, không phải JWT đã được ký; các mốc thời gian chỉ để hiểu các claims. **Giải mã Base64URL không phải xác minh token.** Chỉ lấy `iss` và `sub` **sau khi** OIDC client library đã kiểm tra đúng:

1. **Chữ ký/JWS:** dùng khóa và thuật toán đã được phép cho OP, từ cấu hình/JWKS đáng tin; chống `alg=none` và algorithm confusion.
2. **Issuer:** `iss` **khớp chính xác** issuer đã được đăng ký/discovery cho client hiện tại.
3. **Audience:** `aud` chứa `client_id` của RP; thực hiện quy tắc `azp` khi áp dụng, đặc biệt khi có nhiều audience.
4. **Thời gian:** `exp`, `iat` và các điều kiện thời gian theo chính sách, clock skew hữu hạn.
5. **Nonce:** nếu luồng gửi `nonce`, kiểm tra nonce trả về để chống token injection/replay.
6. **Authorization response:** `state`/correlation, redirect URI, code exchange và PKCE khi phù hợp với OAuth client.
7. **Nguồn UserInfo:** nếu lấy `sub` từ UserInfo, nó phải **khớp chính xác** `sub` từ ID Token đã xác minh.
8. **Client/provider binding:** ID Token của OP A không được chấp nhận làm ID Token của cấu hình OP B.

**Tuyệt đối không** lấy `iss` trong một JWT chưa xác minh rồi tự động tải JWKS của bất kỳ URL nào do token gợi ý. Có thể đọc claim làm **hint** để tìm một OP thuộc allowlist cấu hình, nhưng phải hoàn tất signature/issuer/audience validation đúng OP đó trước khi tin nội dung.

## 3. Tại sao cặp (iss, sub) mới là định danh ổn định?

OIDC Core, mục **Claim Stability and Uniqueness**, nói rõ chỉ `iss` và `sub` **dùng cùng nhau** là định danh mà RP có thể dựa vào để nhận biết End-User ổn định.

**Phản ví dụ:**

~~~text
OP A phát sub = "42"  cho người A
OP B phát sub = "42"  cho người B

Nếu khóa database = sub:
    key "42" -> có nguy cơ ghi đè hoặc gộp A và B

Nếu khóa database = (iss, sub):
    (https://op-a.example.test, "42") -> A
    (https://op-b.example.test, "42") -> B
~~~

Cần nhấn mạnh: `iss` là **chuỗi định danh OP**, không chỉ là domain. Hai issuer cùng host nhưng khác path có thể là **hai OP/tenant namespaces khác nhau**:

- `https://login.example.test/realms/sales`
- `https://login.example.test/realms/hr`

Cả hai có thể phát `sub="42"`. Chúng là **hai khóa khác nhau**.

Tương tự, `https://op.example.test` và `https://op.example.test/` không được tự coi là đồng nhất trong hệ thống identity lookup. OIDC yêu cầu **exact matching** issuer theo discovery/ID Token. Nếu nhà cung cấp thay issuer URI, đó là thay đổi identity namespace cần migration có kiểm soát, không phải thay đổi vô hại.

**`sub` là opaque identifier:** ứng dụng không được suy ra tổ chức, email, thứ tự cấp, giới tính hoặc vai trò từ cấu trúc chuỗi `sub`. Nó có thể là số dạng string, UUID-like, chuỗi hash hoặc định dạng riêng và nên được **giữ nguyên nguyên văn**.

## 4. Vì sao không dùng email, preferred_username hoặc phone_number làm khóa?

| Claim | Hữu ích để làm gì? | Vì sao không là khóa liên kết duy nhất? |
| --- | --- | --- |
| `email` | Hiển thị và liên hệ | Có thể thay đổi, được cấp lại cho người khác, trùng giữa OP |
| `email_verified` | OP khẳng định đã kiểm tra quyền kiểm soát email theo chính sách của họ | Không chứng minh hai accounts ở hai OP là cùng một người/tài khoản ứng dụng |
| `preferred_username` | Tên hiển thị hoặc login hint | Có thể đổi hoặc trùng giữa tổ chức |
| `phone_number` | Liên hệ/step-up theo chính sách | Số điện thoại có thể chuyển chủ |
| `name`, `given_name` | UX/profile | Không unique và có thể đổi |
| `picture` | Avatar | Không liên quan identity proof |
| `sub` đơn lẻ | Nhận diện trong phạm vi issuer | Không unique trên mọi OP |
| **`iss + sub`** | **Khóa liên kết OP subject** | **Được OIDC bảo đảm theo phạm vi issuer** |

Ví dụ một nhân viên rời công ty, email `finance@example.test` được tái cấp cho người mới. Nếu hệ thống cũ dùng email làm primary key liên kết, người mới có thể bị truy cập dữ liệu hoặc quyền trước đó. Với issuer+sub, hai người phải có hai định danh khác nhau nếu OP tuân thủ đặc tả.

**Ngay cả `email_verified=true` cũng không cho phép tự động ghép hai account.** Claim đó chỉ diễn đạt một thuộc tính về email theo OP; nó không thay quy trình xác nhận chủ sở hữu tài khoản nội bộ và kiểm soát account takeover.

Một số hệ thống cần email làm **chỉ mục tìm kiếm hỗ trợ**; khi đó lưu nó như profile attribute có thể cập nhật, không làm unique identity link hoặc nguồn quyền nâng cao.

## 5. Public subject và pairwise subject

OIDC Core định nghĩa **hai loại subject identifier**:

| Loại | Ý nghĩa | Hệ quả |
| --- | --- | --- |
| **public** | OP có thể phát cùng `sub` cho cùng user ở nhiều clients | Các RPs có thể nhận biết cùng OP subject nếu chính sách cho phép |
| **pairwise** | OP phát `sub` khác nhau theo **Sector Identifier** | Giảm khả năng liên kết hoạt động của user giữa các RP |
| **`subject_types_supported`** | Trường trong OIDC Discovery metadata | Cho biết OP hỗ trợ public/pairwise |

**Pairwise không nhất thiết mỗi client đều có sub khác:** hai clients cùng **sector identifier** có thể nhận **cùng pairwise sub** cho một End-User; hai sectors khác nhau phải nhận các subject identifiers khác nhau. Vì vậy không diễn giải đơn giản “pairwise = theo mọi client_id”, mà cần xét **sector** và cấu hình OP.

Ví dụ:

~~~text
OP issuer = https://identity.example.test

User nội bộ của OP: user-789

Client Portal: sector = portal.example.test
ID Token: (iss, sub = "p-8af2")

Client HRM: sector = hrm.example.test
ID Token: (iss, sub = "p-31cd")

=> Cùng người tại OP nhưng hai cặp (iss,sub) khác nhau.
=> RP không được tự suy ra cùng người từ email hoặc một thuật toán đoán sub.
~~~

### sector_identifier_uri

Khi dùng pairwise, OP xác định subject theo **Sector Identifier**. Nếu client có `sector_identifier_uri`, tài liệu đăng ký phù hợp sẽ mô tả các redirect URIs của nhóm client; nếu không, sector thường dựa trên host của redirect URI theo quy tắc đăng ký. Việc đổi domain/sector hoặc client registration có thể dẫn đến **`sub` mới**, ngay cả khi người dùng không đổi.

**Vận hành quan trọng:** Khi chuyển từ public sang pairwise, đổi sector identifier hoặc tách/ghép clients, phải lên kế hoạch **migration identity links**. Không coi `sub` thay đổi là lý do để tự động tạo tài khoản có toàn bộ quyền cũ hoặc nối tài khoản dựa trên email.

## 6. Tính chính xác của issuer: case, path, slash và discovery

Theo OpenID Connect, `iss` trong ID Token là issuer identifier dùng HTTPS, có thể gồm host, port, path, **không có query hoặc fragment**. Issuer trong discovery metadata và `iss` của ID Token phải **trùng khớp chính xác**.

Một số ví dụ:

| Issuer A | Issuer B | Coi cùng khóa định danh? |
| --- | --- | --- |
| `https://idp.example.test` | `https://idp.example.test` | Có, nếu `sub` cũng giống và token hợp lệ |
| `https://idp.example.test` | `https://idp.example.test/tenant` | **Không** |
| `https://idp.example.test/tenant-a` | `https://idp.example.test/tenant-b` | **Không** |
| `https://idp.example.test` | `https://idp.example.test/` | **Không tự coi là đồng nhất** |
| `https://old-login.example.test` | `https://new-login.example.test` | **Không**, cần migration có xác thực |
| Cùng issuer, `sub="A42"` | Cùng issuer, `sub="a42"` | **Không**, subject là case-sensitive string |

Khi lưu khóa trong database:

- Giữ **đúng giá trị issuer và subject được OP phát**, đã qua xác minh.
- Dùng **so sánh case-sensitive, exact** cho cả hai; tránh collation/case folding âm thầm.
- Không lowercase toàn bộ issuer path/subject hoặc trim `sub` để “tối ưu”.
- Không dùng `URI.normalize()`, bỏ trailing slash hoặc ghép URL theo heuristic để coi hai issuer là giống nhau.
- Ghi nhận **registration/client configuration** dùng để kiểm tra token, nhưng không thay thế `iss` bằng registrationId.
- Nếu issuer thuộc OP đã được phê duyệt thay đổi hợp lệ, xử lý bằng **một migration rõ ràng**, không tạo alias issuer ngầm.

**Chú ý:** API URL/URI trong Java có thể chuẩn hóa một số biểu diễn khi so sánh. Khi tạo identity key, nên lấy **chuỗi `iss` gốc từ claim của ID Token đã được library xác minh** và lưu nguyên văn.

## 7. ID Token, UserInfo và access token không hoán đổi được

Trong hệ thống Spring Security có cả login web và backend API, rất dễ lẫn ba loại dữ liệu:

| Nguồn | Dùng để làm gì? | Lưu ý identity |
| --- | --- | --- |
| **OIDC ID Token** | RP xác thực End-User qua OP | Cặp `iss,sub` là khóa nhận diện người dùng |
| **OIDC UserInfo Response** | Bổ sung claims/profile khi có quyền truy cập | `sub` **phải khớp** ID Token, không độc lập làm danh tính |
| **OAuth access token** | Client truy cập API/Resource Server | `sub` có thể mang nghĩa khác theo token/profile và loại grant |
| **Refresh token** | Lấy token mới theo quyền được cấp | Không phải khóa người dùng |
| **Local app session** | Lưu authenticated context của ứng dụng | Dùng local account ID và policy riêng |

Nếu endpoint UserInfo trả:

~~~json
{
  "sub": "someone-else",
  "email": "person@example.test"
}
~~~

trong khi ID Token đã xác minh có `sub="usr-7h2v8"`, RP **phải từ chối kết quả UserInfo này** theo OIDC; không được ghép claims của subject khác vào phiên hiện tại.

**Access token JWT không mặc nhiên là ID Token.** Với client credentials, `sub` có thể biểu diễn client/service chứ không phải End-User. Ở Resource Server, cần xác minh issuer, audience và các ràng buộc token theo profile API, rồi ánh xạ identity/authorization phù hợp. Không dùng một `sub` từ access token bất kỳ để nối thẳng với tài khoản OIDC người dùng.

## 8. Mô hình database: external identity link thay vì email làm primary key

Một mô hình an toàn có **local_account** và bảng liên kết danh tính bên ngoài:

~~~text
local_account
  id (PK)
  status
  created_at
       ^
       | 1 account có thể có nhiều external identities
       |
federated_identity
  id (PK)
  local_account_id (FK)
  issuer (exact string)
  subject (exact string)
  provider_registration (audit/routing, không thay iss)
  linked_at
  verified_at
  link_method
  UNIQUE(issuer, subject)
~~~

Ví dụ DDL **PostgreSQL** (giả định bảng `local_account(id)` đã tồn tại):

~~~sql
CREATE TABLE federated_identity (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    local_account_id BIGINT NOT NULL
        REFERENCES local_account(id),
    issuer TEXT COLLATE "C" NOT NULL,
    subject VARCHAR(255) COLLATE "C" NOT NULL,
    provider_registration VARCHAR(100),
    linked_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (issuer, subject),
    CHECK (length(issuer) > 0),
    CHECK (length(subject) > 0)
);

CREATE INDEX idx_federated_identity_account
    ON federated_identity(local_account_id);
~~~

**Vì sao UNIQUE(issuer, subject)?** Không cho cùng một danh tính OP được liên kết đồng thời tới hai local accounts, ngăn race condition và account takeover. Mặc định nên có một external identity pair → một local account tại một thời điểm; khi cần chuyển liên kết phải dùng quy trình explicit.

**Vì sao không UNIQUE(email)?** Email không là định danh bất biến theo OIDC và có thể thay đổi/recycle.

**Vì sao dùng collation case-sensitive?** `sub` và issuer cần so sánh chính xác. Ví dụ trên dùng `COLLATE "C"` của PostgreSQL để minh họa deterministic case-sensitive matching; **không copy nguyên DDL sang MySQL/SQL Server** mà không kiểm tra semantics/collation thực tế.

**Không dùng `client_id` làm khóa ghép thay cho `iss`:** cùng một OP có thể đổi client registration hoặc một broker cung cấp nhiều clients nhưng vẫn cùng issuer; trong khi pairwise `sub` có thể đổi theo sector. `client_id` hữu ích để audit/migration, nhưng không phải định danh OP subject theo chuẩn.

### Giao dịch đồng thời

Khi hai browser hoàn tất login cùng lúc cho một danh tính mới, ứng dụng phải:

1. Xác minh token và chính sách provisioning.
2. Trong transaction, tra cứu `(issuer,subject)`.
3. Nếu không có và được phép tạo, insert link với **unique constraint**.
4. Nếu gặp unique violation, đọc lại link hiện có và xác minh nó thuộc account dự kiến.
5. Không silently reassign identity link sang account khác.
6. Audit các lần link/unlink và áp dụng optimistic/concurrency control.

Chỉ dùng `SELECT rồi INSERT` không có UNIQUE constraint dễ tạo hai local accounts cho cùng một OIDC identity khi có race.

## 9. Luồng nhận diện người dùng sau OIDC authentication

~~~text
Browser chọn OP đã đăng ký
       |
Authorization Code + state/PKCE
       |
Token Endpoint -> ID Token
       |
Spring Security OIDC Client:
  verify JWS, issuer, audience, exp, nonce...
       |
Get verified iss + sub từ ID Token
       |
Federated Identity Service
  SELECT ... WHERE issuer = ? AND subject = ?
       |
    +-- Found, active ----------------> local account
    |
    +-- Not found --------------------> onboarding / policy
    |                                     |
    |                           approved JIT? tạo tài khoản
    |                           else: pending / denied
    |
    +-- Suspended / disabled ----------> deny
       |
Kiểm tra tenant membership / app entitlements
       |
SecurityContext + app session, domain authorization
~~~

**Không biến `OidcUser.getName()` thành local account ID** mà không xem cấu hình. Spring Security có thể hiển thị `sub` làm principal name mặc định, nhưng ứng dụng federation nhiều issuer cần dùng một **khóa ghép** để lookup. Với pairwise identifiers, việc cùng một user có nhiều `sub` ở các clients cũng cần thiết kế account linking riêng.

Nếu domain service cần local account ID, hãy truyền nó qua **authenticated session/principal adapter** hoặc lookup service đã được phê duyệt; không để mọi controller tự tìm account bằng email.

## 10. Spring Security OAuth2 Login khác SAML2 Login ở điểm nào?

| Hệ thống đăng nhập | Spring Security DSL | Nguồn định danh |
| --- | --- | --- |
| SAML 2.0 SP | `http.saml2Login(...)` | SAML issuer + NameID (và format/qualifiers theo profile) |
| OIDC RP | `http.oauth2Login(...)` với scope `openid` | **ID Token `iss` + `sub`** |
| OAuth2 login không OIDC | `http.oauth2Login(...)` nhưng provider không có OIDC | Provider-specific `OAuth2User` attributes, không có OIDC ID Token |
| JWT Resource Server | `http.oauth2ResourceServer(...)` | Access token claims theo cấu hình API, **không đồng nghĩa OIDC login** |

**Đề bài liên quan OIDC và identity broker**, dù module tổng là Spring Security federation. Để tích hợp một broker **đóng vai OIDC OP**, SP của bạn cần Spring Security **OAuth2 Client/OIDC Login**, không phải tự đưa ID Token vào `saml2Login`. Nếu broker nói chuyện SAML với upstream, đó là **chi tiết federation ở phía broker**, không biến protocol của RP với broker thành SAML.

Một ứng dụng có thể đồng thời hỗ trợ SAML2 Login và OIDC Login, nhưng phải có **hai lớp xác minh token riêng**, sau đó quy về một mô hình local-account/tenant-authority thống nhất.

## 11. Cấu hình hai OIDC providers trong Spring Boot

Với **Spring Boot 3.x, Spring Security 6.x, Java 17+**, cần Spring MVC/Servlet, Spring Security và `spring-boot-starter-oauth2-client`. Khi sử dụng discovery, mỗi provider được cấu hình issuer riêng.

`src/main/resources/application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corp:
            provider: corp-op
            client-id: corp-portal
            client-secret: "${CORP_OIDC_CLIENT_SECRET}"
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: [openid, profile, email]
          broker:
            provider: broker-op
            client-id: broker-portal
            client-secret: "${BROKER_OIDC_CLIENT_SECRET}"
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: [openid, profile, email]
        provider:
          corp-op:
            issuer-uri: "https://login.example.test/realms/staff"
          broker-op:
            issuer-uri: "https://broker.example.test/realms/federation"
~~~

Đây là **cấu hình minh họa**, không thể chạy login nếu không có OP/issuer thật, client IDs, client secrets bảo vệ, redirect URIs đã đăng ký và discovery/JWKS hợp lệ. Không commit secrets vào Git; dùng environment/secret manager và HTTPS. Các domain `example.test` chỉ là ví dụ.

Các URL Spring Security thường sử dụng:

| URL | Mục đích |
| --- | --- |
| `/oauth2/authorization/corp` | Bắt đầu OAuth2/OIDC login với client registration `corp` |
| `/oauth2/authorization/broker` | Bắt đầu login qua broker OP |
| `/login/oauth2/code/corp` | Callback authorization code cho `corp` |
| `/login/oauth2/code/broker` | Callback authorization code cho `broker` |

**Không nhầm `registrationId=corp` với `iss`.** Registration ID là tên cấu hình trong Spring; `iss` thực sự phải đến từ ID Token được xác minh và khớp issuer của provider.

Khi dùng issuer discovery, Spring lấy các endpoints và JWKS từ OP metadata. Việc cấu hình `issuer-uri` không cho phép token tùy ý chọn issuer khác hoặc chạy theo URL do browser truyền vào.

## 12. Đọc issuer và subject đã xác minh trong Spring Security

Khi Spring Security **OIDC Login** thành công, principal thường implements `OidcUser`; có thể đọc ID Token qua `getIdToken()`. Javadoc `IdTokenClaimAccessor` cũng có `getIssuer()` và `getSubject()`.

Ví dụ một controller chỉ in **local identity key đã làm sạch** cho người quản trị đã xác thực (không nên public endpoint này):

~~~java
package com.example.web;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.OidcIdToken;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class IdentityDebugController {

    @GetMapping("/internal/oidc-identity")
    public String identity(@AuthenticationPrincipal OidcUser user) {
        OidcIdToken token = user.getIdToken();
        String issuer = token.getClaimAsString("iss");
        String subject = token.getSubject();

        // Không trả toàn bộ ID Token hoặc claims PII ra response.
        return "issuer=" + issuer + "; subject=" + subject;
    }
}
~~~

**Đây là class thuộc một dự án Spring Boot**, không phải chương trình Java standalone. Để an toàn phải bảo vệ endpoint này bằng authorization dành cho người quản trị hoặc **loại hẳn khỏi production**. `@AuthenticationPrincipal` phải thực sự nhận `OidcUser`; nếu endpoint còn cho phép SAML hoặc anonymous, cần handler riêng/type checking.

**Tại sao dùng `token.getClaimAsString("iss")`?** Để lấy chuỗi issuer đúng theo claim đã được xác minh, tránh vô tình chuyển đổi URL thành dạng khác trước khi làm key database. `token.getIssuer()` cũng có nhưng trả về `java.net.URL` trong nhiều phiên bản Spring Security; với khóa lưu trữ cần giữ string OIDC gốc và exact matching.

**Không dùng controller để thực hiện user provisioning.** Account resolution nên được thực hiện tập trung trước khi ứng dụng tin người dùng là một local account hợp lệ.

## 13. Extension point: OidcUserService và account-link lookup

Spring Security có `OidcUserService` để tải OIDC principal sau xử lý OIDC login. Có thể **delegate** tới implementation mặc định rồi gọi một service của ứng dụng để resolve `(iss,sub)`.

Ví dụ **Spring Security 6.x / Servlet**, phần service `LocalIdentityLinker` do ứng dụng tự triển khai với database và policy. Mẫu cố ý **không tự động ghép tài khoản theo email**.

`src/main/java/com/example/security/OidcIdentityConfig.java`:

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.client.oidc.userinfo.OidcUserService;
import org.springframework.security.oauth2.client.userinfo.OAuth2UserService;
import org.springframework.security.oauth2.client.oidc.userinfo.OidcUserRequest;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class OidcIdentityConfig {

    // Interface của ứng dụng; cần implementation/bean sử dụng DB thật.
    public interface LocalIdentityLinker {
        boolean isActiveLinkedAccount(String issuer, String subject);
    }

    @Bean
    OAuth2UserService<OidcUserRequest, OidcUser> oidcUserService(
            LocalIdentityLinker linker) {

        OidcUserService delegate = new OidcUserService();

        return request -> {
            OidcUser verifiedUser = delegate.loadUser(request);
            String issuer =
                verifiedUser.getIdToken().getClaimAsString("iss");
            String subject = verifiedUser.getIdToken().getSubject();
            String expectedIssuer =
                request.getClientRegistration()
                    .getProviderDetails().getIssuerUri();

            if (issuer == null || issuer.isBlank()
                    || subject == null || subject.isBlank()
                    || expectedIssuer == null
                    || !issuer.equals(expectedIssuer)) {
                throw new OAuth2AuthenticationException(
                    new OAuth2Error("invalid_oidc_identity"),
                    "OIDC issuer or subject is not trusted");
            }

            if (!linker.isActiveLinkedAccount(issuer, subject)) {
                throw new OAuth2AuthenticationException(
                    new OAuth2Error("unlinked_oidc_identity"),
                    "No active local account is linked");
            }

            // Trả principal đã được OIDC provider xử lý.
            // Domain services phải tiếp tục kiểm tra tenant/quyền.
            return verifiedUser;
        };
    }

    @Bean
    SecurityFilterChain filterChain(
            HttpSecurity http,
            OAuth2UserService<OidcUserRequest, OidcUser> oidcUserService)
            throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/login").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(oauth -> oauth
                .userInfoEndpoint(userInfo ->
                    userInfo.oidcUserService(oidcUserService)))
            .build();
    }
}
~~~

**Mẫu là integration code có phụ thuộc Spring**, không chạy bằng `javac` thuần JDK và không có stdout cố định. Cần cung cấp một bean `LocalIdentityLinker` thật, database schema, active-account check, client registrations và OP. Nếu muốn cho phép JIT provisioning, thiết kế workflow riêng thay vì đổi kết quả `false` thành “auto create admin”.

**Ranh giới tin cậy:** Spring Security phải kiểm chứng OIDC ID Token, các điều kiện issuer/audience/signature/nonce trước khi business service sử dụng `iss/sub`. Không thay `OidcUserService` bằng code tự Base64-decode token từ HTTP request rồi lookup account.

**Giới hạn của snippet:** Nó chỉ **cho phép hoặc chặn một danh tính đã linked**, chưa thay `Authentication.getName()` thành local account ID và chưa cấp role. Nếu ứng dụng cần principal nội bộ, hãy thiết kế custom principal/lookup context hoặc saved account ID có kiểm soát; không suy đoán `getName()` luôn unique giữa nhiều OP.

### Đặt validation ở đâu?

- **ID Token protocol validation:** thư viện Spring Security/OIDC, không nằm trong SQL linker.
- **Local identity resolution:** service/DAO tra cứu chính xác `issuer + subject`.
- **Provisioning & linking:** workflow nghiệp vụ có explicit authorization và audit.
- **Tenant membership & roles:** domain policy server-side.
- **Session management:** Spring Security, không tự lấy email claim để chia sẻ session giữa tenants.

## 14. Trang chọn OP và vấn đề nhiều provider

Khi có nhiều OIDC providers, Spring Security dùng `ClientRegistrationRepository` để quản lý clients; `InMemoryClientRegistrationRepository` có thể duyệt registrations cho trang login mặc định khi cấu hình phù hợp.

~~~text
GET /private
     |
     v
Trang login /login
   [OIDC Corp]     -> /oauth2/authorization/corp
   [OIDC Broker]   -> /oauth2/authorization/broker
     |
     v
Authorization Code Flow
     |
     v
Verified ID Token
     |
     v
(issuer, subject) -> local account
~~~

**Quan trọng:** `/oauth2/authorization/{registrationId}` khởi động **OAuth2/OIDC login**, không phải endpoint SAML `/saml2/authenticate/{registrationId}`. Dùng đường dẫn sai có thể khiến ứng dụng chọn nhầm security filter chain hoặc không có registration hợp lệ.

Với hàng trăm tenant, không nên liệt kê công khai mọi issuer/registration. Có thể dùng mã tổ chức hoặc domain hint, nhưng chỉ map qua **server-side allowlist** tới một provider đã đăng ký; sau callback vẫn phải kiểm tra account+tenant membership. Không cho nhập trực tiếp `issuer-uri` hoặc JWKS URL bất kỳ từ browser vì tạo SSRF/trust injection.

## 15. Identity broker: issuer mà RP thấy là của ai?

Một identity broker có thể liên kết upstream SAML IdP, upstream OIDC OP, LDAP hoặc hệ thống đăng nhập khác. Broker xác thực/biến đổi nguồn upstream rồi phát một **ID Token mới** cho RP.

~~~text
Browser
   |
   v
RP: https://portal.example.test
   |
   | OIDC Login (client của broker)
   v
Broker OP: https://broker.example.test/realms/main
   |
   +--> Upstream OIDC OP A
   |
   +--> Upstream SAML IdP B
   |
   +--> Upstream enterprise directory
   |
   v
Broker phát ID Token:
    iss = https://broker.example.test/realms/main
    sub = b-user-6201
   |
   v
RP kiểm chứng ID Token của BROKER
   |
   v
Identity link:
    (broker issuer, b-user-6201) -> local-account-9
~~~

**Lỗi rất phổ biến:** Nhìn thấy upstream IdP hiển thị trên màn hình login rồi lưu `(upstream_iss, broker_sub)`. Hai giá trị **không thuộc cùng một hệ thống phát ID Token**, dẫn tới khóa danh tính giả. Theo chuẩn OIDC, RP phải nhận cặp `iss/sub` từ **chính ID Token của OP mà nó tin**.

Nếu broker bổ sung custom claims như:

~~~json
{
  "iss": "https://broker.example.test/realms/main",
  "sub": "b-user-6201",
  "identity_provider": "partner-a",
  "upstream_subject": "employee-8271"
}
~~~

thì `identity_provider` và `upstream_subject` là **claims do broker tự định nghĩa**, **không phải hai claims chuẩn OIDC Core để thay thế `iss/sub`**. Chúng chỉ có thể được dùng cho mục đích riêng khi:

1. ID Token từ broker đã được xác minh.
2. Có hợp đồng nghĩa và độ tin cậy với broker.
3. Broker chứng minh upstream identity mapping được quản lý an toàn.
4. Scope/tenant/assurance phù hợp.
5. Không ghép ngẫu nhiên upstream subject của nhà cung cấp khác.

**Lưu ý:** Broker có thể đổi cách ánh xạ upstream identity, tách/ghép tenants hoặc đổi `sub` khi di chuyển kho người dùng. Khi đó RP cần migration link có kiểm chứng, dù upstream user vẫn là một người.

## 16. Upstream identity và downstream identity: không trộn namespaces

Nếu ứng dụng cần biết người dùng đăng nhập qua upstream nào để thực thi policy, nên lưu **hai lớp thông tin có quan hệ rõ ràng**:

| Lớp | Ví dụ | Được kiểm chứng bởi ai? |
| --- | --- | --- |
| **Downstream OIDC identity** | `(https://broker.example.test, b-user-6201)` | RP kiểm chứng ID Token của broker |
| **Upstream identity** | `(https://op-a.example.test, 7182)` | Broker kiểm chứng upstream OP; RP chỉ tin qua hợp đồng broker |
| **Local account** | `account-9` | Application account database |
| **Tenant membership** | `tenant-north` | Application/domain policy |
| **Assurance/MFA** | `acr`/`amr` do broker phát | RP tin broker theo chính sách, không giả định thay thế upstream evidence |

**Không tự gộp accounts** bằng cách giả sử `broker.sub == upstream.sub`, cũng không dựa vào `email_verified` như phép chứng minh hai OP users là cùng một local user. Một broker có thể phát **cùng broker sub** bất kể người dùng xác thực qua upstream A hay B, nếu broker đã liên kết hai upstream accounts; trong trường hợp đó **broker chịu trách nhiệm liên kết an toàn**.

Nếu RP yêu cầu phân quyền theo upstream IdP, broker phải cung cấp các claims có hợp đồng và được ký, hoặc một API được bảo vệ, cùng chính sách chống giả mạo và độ tin cậy. Không đọc upstream info từ query parameter trên redirect để cấp quyền.

## 17. Account linking: khi nào hai cặp (iss,sub) cùng trỏ tới một account?

Một ứng dụng có thể cho người dùng liên kết nhiều danh tính đã xác minh với một local account:

~~~text
local-account-9
   |
   +-- (issuer corp, sub corp-user-1001)
   |
   +-- (issuer broker, sub broker-user-6201)
   |
   +-- (issuer partner, sub partner-88)
~~~

**Đây là các links độc lập**, không có nghĩa các cặp OIDC “bằng nhau”. Việc chúng trỏ cùng local account là **quyết định account linking của SP** có bằng chứng.

### Quy trình linking an toàn

1. Người dùng đã đăng nhập một **local account** với session đáng tin, đạt mức assurance cần thiết.
2. Người dùng chọn **thêm phương thức đăng nhập**; server tạo một linking intent ngắn hạn, gắn session/CSRF/state và target.
3. Ứng dụng khởi tạo OIDC login với OP thứ hai bằng client registration đã phê duyệt.
4. Spring Security xác minh ID Token mới: signature, issuer, audience, nonce, state và các điều kiện OIDC.
5. Lấy cặp `(iss,sub)` của OP thứ hai và kiểm tra nó **chưa liên kết với account khác**.
6. Áp chính sách step-up/MFA và consent nếu nghiệp vụ yêu cầu.
7. Trong transaction, thêm link vào cùng local account, dựa vào unique constraint.
8. Audit OP, subject fingerprint/identifier thích hợp, phương thức liên kết, người thực hiện và thời điểm; không ghi raw ID Token.
9. Nếu link đã thuộc account khác, **từ chối hoặc đưa vào quy trình phục hồi có kiểm chứng**, không silently reassign.
10. Khi unlink, kiểm tra tài khoản còn ít nhất một phương thức truy cập/phục hồi hợp lệ; không để attacker tước toàn bộ phương thức login của nạn nhân.

### Tuyệt đối tránh

- Tự liên kết khi email từ hai OP giống nhau, kể cả email_verified=true.
- Tin một `sub` do browser tự truyền để tạo link.
- Nhận link dựa vào thông tin upstream do broker chưa ký hoặc chưa xác minh.
- Cho người dùng thay account ID trong request rồi nối một OP identity vào tài khoản người khác.
- Chuyển link đang thuộc account A sang account B chỉ vì email bị đổi hoặc OP có thông tin profile mới.

## 18. JIT provisioning và vòng đời tài khoản

**Just-in-Time (JIT) provisioning** là tạo local account mới ở lần OIDC login đầu tiên khi danh tính `(iss,sub)` chưa có trong database. Tính năng này **không nên mặc định bật cho mọi OP**.

Một chính sách an toàn phân biệt:

| Tình trạng | Hành vi |
| --- | --- |
| Link đã có, local account active | Cho tiếp tục các bước authorization |
| Link đã có, local account suspended | Từ chối theo account policy |
| Link chưa có, OP được phép JIT cho tenant | Tạo account quyền tối thiểu theo workflow đã duyệt |
| Link chưa có, OP không được phép JIT | Đưa vào onboarding/deny; không auto-merge theo email |
| Subject trùng nhưng issuer khác | Coi là danh tính khác, không dùng link cũ |
| Broker báo upstream account đổi | Cần kiểm chứng hợp đồng broker/migration, không overwrite tự động |
| Subject bị nghi recycle hoặc OP vi phạm stability | Điều tra/bảo vệ tài khoản, không tự trao quyền dựa claims cũ |

JIT provisioning cần quyết định rõ: ai được phép đăng ký, tenant nào được cho phép, có cần invitation hay domain proof, ai phê duyệt roles, khi nào thu hồi account và làm sao tránh account enumeration.

**Đặc biệt:** Nếu OP vô tình **tái sử dụng `sub`** trái đặc tả, đó là lỗi nghiêm trọng về identity lifecycle. RP không thể chữa bằng email; cần ngừng trust/điều tra và phối hợp OP.

## 19. Tenant isolation và authorization sau khi tìm được local account

Cặp `iss/sub` xác định **định danh external user** trong phạm vi OP, **không tự xác định tất cả tenant được phép**. Một tài khoản có thể thuộc nhiều tenant, có quyền khác nhau hoặc bị khóa ở một tenant.

~~~text
ID Token validated
    |
    v
(iss,sub) -> local_account_id
    |
    v
active account? ---- no --> deny
    |
   yes
    |
    v
request tenant (client hint) -> validate server-side membership
    |
    v
roles/entitlements from application policy
    |
    v
resource-level authorization
~~~

Nếu một OP được nhiều tenant cùng dùng, chỉ dựa vào issuer để gán tenant là sai. Nếu một broker có nhiều upstream providers, chỉ dựa vào custom `identity_provider` claim để gán quyền admin cũng không an toàn khi hợp đồng trust/claim mapping chưa được xác minh.

**Ví dụ:**

- Cặp `(iss,sub)` của An có link tới `account-9`.
- `account-9` là Viewer ở tenant North và Approver ở tenant South.
- An chọn North trên UI: ứng dụng phải kiểm tra North membership rồi chỉ cấp/kiểm tra quyền của North.
- Dù `OidcUser` có `email=admin@example.test`, không tự cấp `ROLE_ADMIN`.

Điều kiện cho một thao tác như duyệt thanh toán gồm identity, tenant membership, role và quyền trên object; không dừng ở authentication.

## 20. Java 17 độc lập: khóa cặp, chống nhầm subject và issuer

Ví dụ Java 17 dưới đây mô phỏng kho liên kết: cùng subject ở hai issuer **không trỏ cùng account**; issuer có trailing slash khác là một khóa khác; hai external identities có thể chủ đích liên kết cùng local account sau khi có bằng chứng.

Tạo file **OidcCompositeIdentityDemo.java**:

~~~java
import java.util.Map;
import java.util.Objects;

public class OidcCompositeIdentityDemo {

    record OidcKey(String issuer, String subject) {
        OidcKey {
            Objects.requireNonNull(issuer, "issuer");
            Objects.requireNonNull(subject, "subject");
            if (issuer.isBlank() || subject.isBlank()) {
                throw new IllegalArgumentException("Empty issuer or subject");
            }
        }
    }

    private static final Map<OidcKey, String> LINKS = Map.of(
        new OidcKey("https://op-a.example.test", "42"), "ACCOUNT-A",
        new OidcKey("https://op-b.example.test", "42"), "ACCOUNT-B",
        new OidcKey("https://broker.example.test", "b-101"), "ACCOUNT-A"
    );

    static String localAccount(String issuer, String subject) {
        return LINKS.getOrDefault(new OidcKey(issuer, subject),
                "NOT_LINKED");
    }

    public static void main(String[] args) {
        System.out.println(localAccount(
                "https://op-a.example.test", "42"));
        System.out.println(localAccount(
                "https://op-b.example.test", "42"));
        System.out.println(localAccount(
                "https://broker.example.test", "b-101"));
        System.out.println(localAccount(
                "https://op-a.example.test/", "42"));
        System.out.println(localAccount(
                "https://op-a.example.test", "43"));
    }
}
~~~

Chạy bằng Java 17+:

~~~bash
javac OidcCompositeIdentityDemo.java
java OidcCompositeIdentityDemo
~~~

**Stdout chính xác:**

~~~text
ACCOUNT-A
ACCOUNT-B
ACCOUNT-A
NOT_LINKED
NOT_LINKED
~~~

**Giải thích:**

1. OP A + `sub=42` nhận ra ACCOUNT-A.
2. OP B + **cùng** `sub=42` nhận ra ACCOUNT-B: không có cross-issuer collision.
3. Broker + `sub=b-101` cũng trỏ ACCOUNT-A vì **một identity link riêng đã được phê duyệt**.
4. Issuer có trailing slash là chuỗi khác, không tự alias.
5. OP A + subject chưa liên kết `43` bị từ chối theo policy.

**Giới hạn:** `Map.of` mô phỏng một bảng links sau khi account linking đã được xác minh. Chương trình **không parse JWT**, không xác minh ID Token, không dùng JWKS/nonce, không tự cấp quyền. Input của `localAccount` trong production phải xuất phát từ **claims đã được OIDC library kiểm chứng**, không phải query parameters. Trong database thật, dùng UNIQUE(issuer,subject) và transactions thay vì Map cố định.

## 21. Các kịch bản pairwise làm thay đổi subject

### Client A và Client B dùng hai sectors khác nhau

~~~text
Issuer: https://op.example.test
User thực tại OP: U-17

Client A, sector-a -> sub = pw-111
Client B, sector-b -> sub = pw-222

Không được tự coi hai cặp là cùng một local account.
Muốn liên kết: cần broker/OP identity mapping hoặc linking proof.
~~~

### Chuyển domain redirect URI

Nếu OP tính pairwise subject dựa vào sector và một client chuyển từ `old.example.test` sang `new.example.test`, `sub` có thể thay đổi. Cần phối hợp **sector_identifier_uri** hoặc migration hỗ trợ bởi OP, không tự lấy email làm cầu nối.

### Split/merge client registration

Khi tách một OIDC client thành nhiều clients, `sub` có thể giống hoặc khác tùy sector policy của OP. Không đặt kỳ vọng từ client_id đơn lẻ; kiểm tra `subject_types_supported`, sector config và hành vi thực tế bằng test accounts.

### Bật broker giữa RP và OP cũ

Trước:

~~~text
RP -> OP Corp:
 (iss=https://corp.example.test, sub=corp-77)
~~~

Sau:

~~~text
RP -> Broker:
 (iss=https://broker.example.test, sub=broker-88)
~~~

Đây là **hai identity pairs khác nhau**, dù broker bên trong đang xác thực cùng user ở Corp. Nếu muốn giữ local account, cần một **migration linking** từ danh tính OP cũ sang broker identity đã được kiểm chứng.

## 22. Thay issuer, đổi OP hoặc nâng cấp identity broker

Một thay đổi ở `iss` có thể xảy ra do chuyển domain, thay realm/tenant path, đổi nhà cung cấp, thêm broker hoặc tái kiến trúc OP.

**Không làm:**

~~~text
if (iss_old != iss_new) {
    // "Khả năng cao là cùng người vì email giống nhau"
    // -> tự sửa identity link cũ thành issuer mới
}
~~~

**Quy trình migration có kiểm soát:**

1. **Inventory:** lấy danh sách `(issuer,subject)` hiện hành, local accounts, tenants và các ứng dụng phụ thuộc.
2. **Định nghĩa nguồn chứng cứ:** OP/broker cung cấp migration mapping qua một kênh đáng tin, được ký/kiểm tra, hoặc người dùng thực hiện linking sau khi xác thực cả hai danh tính.
3. **Canary:** kiểm tra một tập tài khoản nhỏ, chú ý sub pairwise/public, issuer path và subject casing.
4. **Dual-link:** trong thời gian chuyển tiếp có thể cho account sở hữu hai external links đã xác minh; không xóa link cũ trước khi clients chuyển hết.
5. **Collision handling:** nếu một cặp issuer+sub mới đang thuộc local account khác, dừng và điều tra; không ghi đè.
6. **Tenant authorization:** không sao chép vai trò không còn phù hợp chỉ vì danh tính đã đổi OP.
7. **Session lifecycle:** xác định khi nào sessions cũ phải bị thu hồi và khi nào user reauth.
8. **Audit:** người duyệt, chứng cứ, timestamp, mapping version và khả năng rollback.
9. **Cutover:** đổi registration/issuer của OIDC clients sau khi các links mới đã được kiểm tra.
10. **Retire:** chỉ bỏ cấu hình OP cũ khi không còn client/session/identity flow hợp lệ cần nó, theo chính sách.

**Không biến issuer aliasing thành ngoại lệ vĩnh viễn trong code**, vì alias quá rộng có thể làm trộn hai trust namespaces vốn độc lập.

## 23. Bảo mật UserInfo và account linking qua broker

Khi OP cung cấp `UserInfo Endpoint`, một số claims có thể đến từ nguồn bổ sung, nhưng `sub` phải khớp ID Token. Nếu một broker trả dữ liệu profile tổng hợp từ upstream:

- Broker phải xác minh upstream trước khi phát ID Token/UserInfo.
- RP phải xác minh broker ID Token và quan hệ UserInfo–ID Token.
- Các custom attributes như `upstream_provider`, `external_user_id`, `groups` cần hợp đồng về nguồn và thời hạn.
- Không tự coi group từ upstream IdP A có quyền quản trị tenant B chỉ vì broker phát cùng email.
- Không đưa một upstream `sub` sang issuer của broker để tạo composite key.
- Khi broker account linking bị thay đổi, cần logging, review và khả năng phát hiện takeover.
- Nếu UserInfo chứa claim lạ/khác, xử lý theo policy; không đổi primary identity key từ `iss/sub` sang email.

Trong một số kiến trúc, broker chính là **source of truth** cho danh tính downstream; khi đó RP nên lưu identity link **theo broker issuer + broker subject** và để broker quản lý upstream links. Nếu RP cần quản lý upstream links riêng vì yêu cầu tuân thủ, nên lưu chúng trong **bảng phụ có nguồn và bằng chứng rõ ràng**, không tự sử dụng làm login primary key.

## 24. Rủi ro bảo mật và biện pháp kiểm soát

| Rủi ro | Triệu chứng | Biện pháp |
| --- | --- | --- |
| **Cross-issuer collision** | Hai OP có cùng `sub` bị coi là một user | Unique key `(iss,sub)`, exact matching |
| **Email-based takeover** | Email được cấp lại, user mới vào account cũ | Không link tự động theo email |
| **Unvalidated ID Token** | Ứng dụng chỉ decode JWT, không verify | Dùng Spring OIDC validation, kiểm chữ ký/issuer/audience |
| **Token substitution** | ID Token của client/OP khác được chấp nhận | Bound issuer/aud/azp/state/nonce đúng client |
| **Wrong issuer normalization** | Bỏ path/slash/lowercase issuer gây gộp namespace | Giữ issuer exact; migration explicit |
| **Pairwise subject drift** | Đổi sector dẫn tới `sub` mới | Lập kế hoạch sector/migration, không lấy email nối tự động |
| **Broker upstream confusion** | Dùng upstream issuer cùng broker sub | Chỉ dùng verified downstream ID Token `iss/sub` |
| **Account-link race** | Hai local accounts cùng có một external identity | UNIQUE(issuer,subject), transaction |
| **Cross-tenant privilege** | Một OIDC login cấp quyền ở mọi tenant | Kiểm tra membership/role/resource riêng |
| **Over-trust email_verified** | Ghép accounts ở hai providers dù không có proof | Linking workflow có MFA/step-up và audit |
| **UserInfo subject mismatch** | UserInfo trả claims của user khác | Reject nếu UserInfo.sub khác IDToken.sub |
| **Unauthorized JIT** | OP bất kỳ tạo account nội bộ | Allowlist provisioning theo OP/tenant/invitation |
| **Dynamic issuer SSRF** | Browser đưa URL issuer/JWKS tuỳ ý | Allowlist ClientRegistration/OP metadata |
| **Access-token confusion** | Access token của service được coi là ID Token user | Phân biệt token types, audiences và grant |
| **Stale entitlement** | Account đã khóa nhưng SP session vẫn còn | Session expiry/revocation và domain checks |

**Không sửa lỗi bằng cách** tắt signature validation, bỏ `aud` hay `nonce`, tin mọi issuer cùng hostname, hoặc tự cho user mới vào account có cùng email.

## 25. Ma trận kiểm thử xác định danh tính

| Case | Dữ liệu/kịch bản | Kết quả mong đợi |
| --- | --- | --- |
| 01 | Cùng issuer, cùng sub, ID Token hợp lệ | Trả về cùng identity link |
| 02 | Cùng sub, issuer khác | **Hai identities khác nhau** |
| 03 | Cùng issuer, sub khác | **Hai identities khác nhau** |
| 04 | Issuer khác bởi path | Không coi là cùng OP |
| 05 | Issuer khác trailing slash | Không auto-alias |
| 06 | Subject khác case | Không tự lowercase |
| 07 | Email giống, issuer/sub khác | Không auto-link |
| 08 | Email_verified false | Không dùng làm proof/account key |
| 09 | Email được thay sau login | Identity link không đổi |
| 10 | UserInfo.sub khác ID Token.sub | Reject |
| 11 | Token sai chữ ký | Reject trước identity lookup |
| 12 | Token issuer không nằm trong client config | Reject |
| 13 | Token aud không chứa client_id | Reject |
| 14 | Token hết exp | Reject |
| 15 | Nonce sai khi có gửi nonce | Reject |
| 16 | Broker ID Token có issuer broker + sub broker | Link theo broker identity |
| 17 | Broker cung cấp upstream_subject custom | Không thay composite key |
| 18 | Pairwise sub đổi khi sector đổi | Phải xử lý migration/linking |
| 19 | New identity chưa được approve JIT | Deny hoặc onboarding |
| 20 | Local account suspended | Không cấp session có quyền |
| 21 | Identity link đang thuộc local account khác | Deny re-link, đưa vào review |
| 22 | Hai login flows cùng tạo một identity link | UNIQUE constraint ngăn duplicate |
| 23 | User thuộc tenant X, chọn tenant Y | Domain authorization từ chối Y |
| 24 | Access token client_credentials có sub | Không dùng như end-user ID Token |
| 25 | Issuer-uri của OP đổi domain | Migration có bằng chứng, không alias tự động |
| 26 | Hai OP dùng cùng client registrationId string tại hai app | Dùng `iss/sub`, không dùng registrationId làm identity |
| 27 | Thay OP bằng broker nhưng cùng email | Chỉ link qua proof/migration đã duyệt |
| 28 | Custom IdP URL từ browser | Không tải/join dynamic trust source |
| 29 | Unlink phương thức cuối cùng | Kiểm tra account recovery/step-up |
| 30 | Login thành công nhưng quyền tenant thiếu | Authentication có thể PASS, authorization phải DENY |

**Kiểm thử tích hợp:** Chỉ test `Map<OidcKey,AccountId>` là chưa đủ. Cần tích hợp với ít nhất hai OP/broker test accounts, kiểm chứng JWT/ID Token thật, các response thay đổi `iss/sub`, flow linking, concurrent transactions và các request sau login trên tài nguyên tenant. Không log raw tokens trong test artifacts không được bảo vệ.

## 26. Chẩn đoán lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Đăng nhập OP A được, OP B lại vào cùng account | Lookup chỉ theo `sub` hoặc email | Sửa theo `(iss,sub)` và kiểm tra unique schema |
| Người dùng đổi email rồi thấy account mới | Email được dùng làm key | Dùng identity link ổn định, cập nhật email như profile |
| Sau chuyển broker, user bị tạo account trùng | `iss/sub` broker khác OP cũ | Migration/linking có chứng cứ |
| Khi đổi redirect domain, user được `sub` mới | Pairwise sector thay đổi | Làm việc với OP, kiểm tra sector_identifier_uri |
| OP issuer khác 1 dấu slash, token bị từ chối | Exact issuer validation | Sửa metadata/client config sau khi xác thực đúng OP, không bỏ verify |
| ID Token có `sub` nhưng login báo sai `aud` | Token cấp cho client khác | Dùng đúng clientId/registration và token flow |
| UserInfo lỗi subject mismatch | OP/UserInfo trả nhầm người hoặc token thay thế | Reject, kiểm tra OP và access token |
| Spring login thành công nhưng không thấy local account | Chưa linked hoặc JIT bị tắt | Onboarding/linking workflow, không tra theo email |
| Bản ghi trùng khi login song song | Thiếu UNIQUE constraint hoặc transaction | Thêm constraint và xử lý conflict |
| Có cùng `sub` ở hai clients | OP dùng public hoặc cùng sector pairwise | Không tự giả định ngữ nghĩa nếu không xác minh cấu hình |
| Có `sub` khác cho cùng user giữa clients | OP dùng pairwise khác sector | Cần proof linking |
| API JWT sub không tìm thấy user | Token là access token có scope/subject khác | Dùng resource-server policy, phân biệt token type |
| Chỉ role của tenant B bị sai | Authorization gộp tenant hoặc broker claims | Kiểm tra membership và mapping scope |
| App cho phép email_verified để auto-link | Rủi ro account takeover | Tắt auto-link, migration existing links nếu cần |
| Cấu hình `OidcUserService` bị cast lỗi | Login có thể là OAuth2 không OIDC/SAML | Dùng filter chain hoặc handler theo authentication type |

**Ghi log tối thiểu:** OIDC client registration ID, issuer identifier (theo chính sách), subject đã pseudonymize/hash nếu cần, local account ID, link method, tenant scope, correlation ID và mã lỗi. Không log ID Token nguyên bản, access/refresh tokens, client secrets hoặc thông tin cá nhân không cần thiết.

## 27. Runbook thay đổi issuer hoặc broker

**Trước thay đổi:**

1. Thống kê issuer hiện tại, client IDs, `sub` public/pairwise, sector identifiers, tenant mappings và identity links.
2. Xác định ai làm owner mapping giữa OP cũ và OP/broker mới.
3. Kiểm tra evidence nguồn: signed migration manifest, OP/broker admin API đáng tin hoặc user-driven dual-auth linking.
4. Thiết kế rollback, audit và cơ chế xử lý collision.

**Trong giai đoạn chuyển tiếp:**

1. Cấu hình OP/broker mới qua issuer discovery/JWKS đã phê duyệt.
2. Cho phép cả hai login methods khi policy cho phép, nhưng **không coi hai identity pairs tự bằng nhau**.
3. Chạy canary accounts, kiểm tra subject stability và cách broker tạo downstream `sub`.
4. Tạo **external identity link thứ hai** tới local account sau khi proof được xác minh.
5. Kiểm tra account disabled, roles/tenants và không phát sinh duplicate accounts.
6. Quan sát race/linking errors, không ghi đè cặp đã thuộc account khác.

**Sau chuyển đổi:**

1. Xác nhận mọi client/session/tenant đều dùng cặp identity mới đúng.
2. Kiểm tra reauthentication, logout/revocation và access to tenant resources.
3. Ngừng cho login qua issuer cũ khi không còn nhu cầu, theo change policy.
4. Retire mapping cũ khi đã hết giai đoạn bảo lưu và có phương án recovery.
5. Lưu audit/approval, không xóa log/chứng cứ cần cho điều tra.

**Trường hợp tài khoản bị chiếm quyền hoặc OP mất tin cậy:** Áp dụng security incident response, có thể chặn login và thu hồi session/tokens ngay thay vì giữ dual-link/overlap theo lịch bình thường.

## 28. Câu hỏi tự đánh giá

**1. Vì sao không thể dùng sub đơn lẻ làm khóa người dùng trong ứng dụng có nhiều OP?**  
Vì `sub` chỉ được bảo đảm unique trong **một issuer**. Hai OP có thể phát cùng sub cho hai người khác nhau.

**2. Email đã được `email_verified=true` tại hai OP có chứng minh đây là một local account không?**  
Không. Email có thể đổi/tái cấp, và verification từ OP không thay quy trình account linking của ứng dụng.

**3. Issuer `https://op.test` và `https://op.test/realm` có cùng identity namespace không?**  
Không. OIDC issuer path là một phần định danh và phải khớp chính xác.

**4. Khi OP dùng pairwise subject, hai clients có thể nhận cùng sub không?**  
Có thể nếu chúng thuộc cùng sector identifier. Nếu khác sectors, chúng nhận pairwise identifiers khác nhau.

**5. RP đăng nhập qua broker nhưng upstream là OP A. RP phải dùng issuer nào làm identity key?**  
Dùng `iss` của **broker ID Token mà RP đã xác minh**, cùng `sub` của token đó; upstream identity chỉ là thông tin riêng có hợp đồng/bằng chứng.

**6. Dùng `OidcUser.getName()` làm primary key database có an toàn trong multi-issuer không?**  
Không đảm bảo, vì giá trị hiển thị có thể chỉ là `sub` hoặc được cấu hình khác. Hãy lấy verified ID Token `iss` và `sub` riêng.

**7. UserInfo trả sub khác ID Token thì sao?**  
Phải từ chối kết quả UserInfo, không trộn claims của người khác.

**8. Tại sao việc đổi issuer URI cần migration?**  
Vì issuer mới tạo identity namespace mới; exact matching khiến cặp cũ và cặp mới khác nhau, ngay cả khi cùng người.

**9. Cùng local account có thể liên kết hai cặp (iss,sub) không?**  
Có, khi có **explicit linking proof** được phê duyệt; đó là hai external identities khác nhau trỏ về một account.

**10. Có cần authorization theo tenant sau khi tìm được local account?**  
Có. Xác thực danh tính và cho phép truy cập dữ liệu/role của từng tenant là hai vấn đề độc lập.

## 29. Checklist triển khai production

- [ ] Chỉ lấy `iss` và `sub` từ **OIDC ID Token đã được xác minh** hoặc claims được library bảo đảm liên kết với token.
- [ ] Bảo đảm ID Token signature, issuer, audience/client_id, `azp` khi áp dụng, `exp`, nonce, state và code flow được kiểm tra.
- [ ] `iss`/discovery issuer phải exact match; không dùng dynamic issuer hoặc JWKS URL không được cho phép.
- [ ] Dùng cặp **`(issuer,subject)`** làm external identity key, không dùng email hoặc `sub` đơn lẻ.
- [ ] Database có UNIQUE(issuer,subject), collation case-sensitive và transaction-safe linking.
- [ ] Giữ chính xác string issuer/sub; không lowercase subject hoặc tự bỏ issuer path/slash.
- [ ] Hiểu OP subject type là **public** hay **pairwise**, kiểm tra sector và chính sách client registration.
- [ ] Nếu UserInfo được dùng, xác minh `UserInfo.sub == IDToken.sub`.
- [ ] Khi dùng broker, phân biệt **downstream broker identity** với **upstream identity** và custom claims.
- [ ] Account linking giữa hai OP/broker cần proof, CSRF/state protection, step-up khi cần và audit.
- [ ] JIT provisioning chỉ bật theo OP/tenant policy; không auto-link chỉ vì email_verified.
- [ ] Domain authorization kiểm tra local account active, tenant membership và resource-level entitlements.
- [ ] Không dùng access token của client credentials như ID Token của End-User.
- [ ] Có kế hoạch migration khi issuer, broker, redirect sector hoặc pairwise subject thay đổi.
- [ ] Kiểm thử cross-issuer same-sub, email collision, exact issuer, UserInfo mismatch và concurrent linking.
- [ ] Không log raw tokens, client secrets, PII hoặc subject identifiers không cần thiết.
- [ ] Có runbook account takeover, issuer migration và phương án unlink/recovery an toàn.

## 30. Kết luận

**Trong OpenID Connect, khóa định danh đáng tin cho một End-User là `(iss,sub)` lấy từ ID Token đã được xác minh.** `sub` chỉ có nghĩa trong namespace issuer; email, username và số điện thoại không có cùng bảo đảm stability/uniqueness. Khi OP hỗ trợ pairwise subjects, một người có thể có nhiều `sub` ở các sectors; ứng dụng không được tự đoán chúng tương đương.

**Trong mô hình identity broker**, RP trực tiếp tin **broker-issued ID Token**, nên phải lưu **broker issuer + broker subject**; upstream identity cần được broker quản lý hoặc truyền qua cơ chế có hợp đồng và xác minh riêng. Nếu muốn nhiều danh tính đăng nhập về một local account, hãy sử dụng **bảng identity links, UNIQUE(issuer,subject), quy trình account linking rõ ràng và tenant authorization server-side**.

Spring Security hỗ trợ OIDC qua `oauth2Login`, `OidcUser` và `OidcUserService`. Thư viện đảm nhiệm OIDC protocol validation, còn ứng dụng phải quản trị local-account links, policy, provisioning và quyền. **Không đánh đổi tính chính xác danh tính lấy sự tiện lợi bằng cách ghép theo email hoặc tự tin mọi JWT có `sub`.**

### Tài liệu chính thức

- OpenID Connect Core 1.0 (Errata Set 2), mục **5.7 Claim Stability and Uniqueness**, mục **8 Subject Identifier Types** và **16.15 Issuer Identifier**: https://openid.net/specs/openid-connect-core-1_0.html
- OpenID Connect Discovery 1.0 (Errata Set 2), định nghĩa `issuer` và `subject_types_supported`: https://openid.net/specs/openid-connect-discovery-1_0-errata2.html
- OpenID Connect Dynamic Client Registration 1.0, `sector_identifier_uri`: https://openid.net/specs/openid-connect-registration-1_0.html
- Spring Security — OAuth2 Login Core Configuration: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html
- Spring Security — OAuth2 Login Advanced Configuration, OidcUserService và ID Token signature verification: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html
- Spring Security Javadoc — OidcUser: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/core/oidc/user/OidcUser.html
- Spring Security Javadoc — IdTokenClaimAccessor: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/core/oidc/IdTokenClaimAccessor.html
- Spring Security — OAuth2 Resource Server JWT: https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html
