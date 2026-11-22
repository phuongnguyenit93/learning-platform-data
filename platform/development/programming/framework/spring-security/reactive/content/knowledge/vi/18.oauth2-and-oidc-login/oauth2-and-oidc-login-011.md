# Lưu người dùng nội bộ và liên kết tài khoản ngoài bằng định danh ổn định

## 1. Bài toán: đăng nhập Google hôm nay, đổi email ngày mai, tài khoản vẫn là một

Ứng dụng Spring Security reactive/WebFlux có thể cho người dùng đăng nhập bằng Google hoặc một OpenID Provider (OP) thông qua OAuth2/OIDC. Sau khi provider xác thực xong, ứng dụng vẫn cần một **người dùng nội bộ** để lưu hồ sơ, đơn hàng, quyền theo tenant, lịch sử và các tài nguyên thuộc quyền sở hữu. Không nên sử dụng email bên ngoài làm khóa chính của các bảng nghiệp vụ.

Ví dụ:
- Lần đầu, Alice đăng nhập Google với email `alice@old.example`. Ứng dụng tạo local user `u-100`.
- Sau đó Alice đổi email tại provider thành `alice@new.example` nhưng **subject vẫn như cũ**.
- Alice đăng nhập lại: phải truy ra **đúng `u-100`**, không tạo user mới và không chuyển quyền sở hữu dữ liệu.
- Bob sở hữu một tài khoản Google khác nhưng sau này nhận lại địa chỉ email cũ của Alice. Bob **không được** đăng nhập vào `u-100` bằng email trùng.
- Alice muốn liên kết thêm một Identity Provider khác để dùng hai cách đăng nhập vào một tài khoản. Việc đó phải xuất phát từ **phiên local đã xác thực + ý định liên kết tường minh + xác thực provider mới**, không được tự nhập một email trùng rồi coi là đã liên kết.

**Nguyên tắc quan trọng nhất của OIDC:** sau khi ID Token đã được xác minh, **cặp `(iss, sub)`** mới là định danh bên ngoài ổn định để gắn với local user. Các claim như `email`, `preferred_username`, `name` và số điện thoại đều có thể đổi, tái sử dụng hoặc trùng; `email_verified=true` cũng **không** biến email thành khóa liên kết an toàn giữa hai account. OIDC Core mục 5.7 quy định chính cặp issuer + subject là định danh mà relying party có thể dựa vào cho người dùng bên ngoài.

### Kết quả học tập

Sau bài này bạn có thể:
1. Phân biệt local user ID, OAuth2 client registration ID, OIDC `iss`/`sub`, email, ID Token và access token.
2. Thiết kế bảng `local_users` và `external_identities` có unique constraint đúng, không phụ thuộc email.
3. Xây luồng first login, subsequent login, thay đổi email, explicit account linking, unlinking, conflict và account recovery.
4. Hiểu **pairwise subject**, trường hợp nhiều issuer và các nguy cơ account takeover khi auto-link theo email.
5. Dùng Spring Security WebFlux `oauth2Login`, `OidcUser` và `ServerAuthenticationSuccessHandler` để đồng bộ local user ở thời điểm đăng nhập.
6. Viết service reactive an toàn với chiến lược idempotency, tránh tạo hai user khi login đồng thời; hiểu giới hạn của store in-memory so với transaction/unique constraints của DB.
7. Chạy một project Java 17+ Spring Boot 3.3.13 và bộ test với `WebTestClient`, `mockOidcLogin()` và `StepVerifier`.
8. Tách riêng việc **nhận biết external identity** với việc **phê duyệt liên kết tài khoản**, authorization, quản lý session và lưu OAuth2 tokens.

## 2. Từ OAuth2 đến OIDC: ứng dụng thực sự tin vào đâu?

### 2.1. OAuth2 authorization khác OIDC authentication

OAuth2 cung cấp framework ủy quyền, trong đó access token dùng để gọi resource server. **Access token không mặc định là chứng thư định danh người dùng cho mọi client**. OpenID Connect bổ sung lớp authentication bên trên OAuth2, đặc biệt là **ID Token** chứa các claim xác định end-user trong một bối cảnh issuer.

Luồng thường gặp:

~~~text
Browser                     WebFlux app                   OIDC Provider
   │                            │                              │
   │ GET /oauth2/authorization/google                          │
   ├───────────────────────────►│                              │
   │                            │ Authorization Request        │
   │◄───────302 đến OP──────────┼─────────────────────────────►│
   │                            │                              │
   │          User đăng nhập / đồng ý ở provider                │
   │                            │                              │
   │ GET /login/oauth2/code/google?code=...&state=...          │
   ├───────────────────────────►│                              │
   │                            │ đổi code lấy tokens          │
   │                            ├─────────────────────────────►│
   │                            │◄── ID Token/access token ────┤
   │                            │                              │
   │                            │ Validate ID Token: ký, iss,  │
   │                            │ aud, exp, nonce/state...     │
   │                            │                              │
   │                            │ (verified iss, sub)          │
   │                            ▼                              │
   │                     external_identities                    │
   │                      ├─ đã có → local user cũ             │
   │                      └─ chưa có → tạo local user+link     │
   │                            │                              │
   │◄──── redirect /me ─────────┤                              │
   │                            │                              │
~~~

Spring Security WebFlux xử lý những khâu OAuth2/OIDC protocol phức tạp (authorization code, state, token exchange, ID Token validation, callback) khi `oauth2Login` được cấu hình đúng. **Chỉ sau khi authentication từ cơ chế đó thành công**, ứng dụng mới nên dùng external identity để truy vấn/tạo local user.

Không chấp nhận một API công khai có body `{"iss":"...","sub":"..."}` rồi tự coi là đã xác thực. Đây là dữ liệu có thể giả mạo. Cũng không giải mã Base64 JWT không xác minh chữ ký/audience/issuer rồi lấy `sub` để liên kết.

### 2.2. Ba loại ID đừng nhầm

| Giá trị | Ví dụ | Ai cấp? | Mục đích |
| --- | --- | --- | --- |
| Local user ID | UUID `73ab...` | Database ứng dụng | Khóa chính trong đơn hàng, hồ sơ, quyền và audit |
| OIDC issuer `iss` | `https://accounts.google.com` | OIDC Provider đã được xác minh | Namespace phát hành subject |
| OIDC subject `sub` | Chuỗi opaque của provider | Provider trong namespace của issuer | Định danh người dùng của OP cho relying party |
| Client registration ID | `google`, `corp-oidc` | Cấu hình Spring client | Chọn provider/client để bắt đầu OAuth2 flow |
| Email | `alice@example.org` | Claim hồ sơ từ OP | Liên hệ/hiển thị; không là khóa liên kết bảo mật |
| `email_verified` | `true` hoặc `false` | Claim từ OP | Tín hiệu provider đã kiểm chứng email theo quy trình của họ, không là quyền sở hữu local account |
| Access token | Chuỗi opaque/JWT | Authorization Server | Gọi protected resource theo scopes |
| ID Token | JWT OIDC | OP | Thông tin authentication được client xác minh |

**`registrationId` không tự là issuer.** Hai registration khác nhau có thể trỏ tới cùng issuer, hoặc một registration được đổi tên trong cấu hình; ngược lại cùng subject value ở hai issuer khác nhau là hai identity khác nhau.

Đối với OIDC chuẩn, dùng cặp **issuer canonical đã được xác minh + subject nguyên văn** để định danh external account. Không chỉ dựa vào `sub`, không gắn user với `registrationId` đơn lẻ.

### 2.3. OIDC chỉ đảm bảo cặp issuer + subject

Ví dụ:

~~~text
(iss="https://idp-a.example", sub="123") → external user A
(iss="https://idp-b.example", sub="123") → external user B
~~~

Hai người này **không** được hợp nhất vì sub cùng là `123`.

Các giá trị `sub` có thể là opaque, case-sensitive, chứa ký tự không có ý nghĩa với ứng dụng. Không `toLowerCase()`, parse thành số, cắt prefix, hash không kiểm soát hoặc chuẩn hóa tùy tiện `sub`. Với `iss`, phải đối chiếu đúng issuer được cấu hình/trusted; chỉ áp dụng alias mapping khi có tài liệu chính thức và đã được security review.

Ví dụ Google có những biểu diễn issuer được tài liệu hóa; nếu migration cần canonicalize một alias, phải **xác minh token từ Google trước** rồi mới map alias theo rule được phê duyệt. Không áp dụng “bỏ scheme và lấy hostname” cho mọi issuer, vì có thể gộp những OP khác nhau.

## 3. Vì sao email không được dùng để tự liên kết tài khoản?

### 3.1. Account takeover qua email trùng

Giả sử một ứng dụng cũ lưu:

~~~text
users:
  id = u-100
  email = employee@company.example
~~~

Khi có OAuth2 login lần đầu, code sai:

~~~java
// PHẢN VÍ DỤ: KHÔNG tìm local account theo email để tự login/link.
return userRepository.findByEmail(oidcUser.getEmail())
    .switchIfEmpty(userRepository.createFromEmail(...));
~~~

Có thể xảy ra:
- Email được đổi/thu hồi và cấp cho một người khác.
- Provider A có quy tắc verified email khác provider B.
- Email chưa được xác minh nhưng vẫn có trong UserInfo.
- Hai identity có cùng email hợp lệ trong các miền ngữ cảnh khác nhau.
- `email_verified=true` chỉ chứng nhận một sự kiện ở provider, **không chứng minh người đăng nhập được nhận quyền của local user hiện có**.

Nếu email trùng tự động cấp quyền truy cập `u-100`, user mới có thể lấy toàn bộ dữ liệu cũ. Đây là lỗi **account takeover**.

### 3.2. Email thay đổi nhưng local ID phải giữ

~~~text
Login 1:
  (iss=Google, sub=opaque-A, email=old@example.org)
     → external link L1 → local user u-100

Login 2:
  (iss=Google, sub=opaque-A, email=new@example.org)
     → external link L1 → local user u-100
~~~

Ứng dụng có thể cập nhật email hồ sơ (tùy chính sách email verification và yêu cầu xác nhận lại), nhưng **không cập nhật owner ID của bảng orders/documents** và không tạo local account mới.

Email chỉ là metadata. Local user ID bất biến là referent của các domain entities:
- `orders.user_id`.
- `documents.owner_id`.
- `memberships.user_id`.
- `audit_events.actor_user_id`.
- `permissions.user_id`.

Không lưu `iss/sub` lặp lại vào từng bảng nghiệp vụ nếu mục tiêu chỉ là liên kết login. Giữ một bảng external identity → local user để có thể hỗ trợ nhiều provider.

### 3.3. `email_verified` có thể dùng làm gì?

Tín hiệu email đã verified có thể giúp chọn cách liên hệ, khuyến nghị xác minh bổ sung hoặc điều kiện gửi email; tùy policy và độ tin cậy của issuer. Nhưng:
- Không tự dùng nó làm chứng minh “cùng người với local account cũ”.
- Không tự gán role nội bộ `ADMIN` theo domain email mà chưa kiểm tổ chức, tenant và chính sách provisioning.
- Nếu email được thay đổi ở provider, việc đổi email liên hệ nội bộ phải tuân theo chính sách bảo mật, không tự đổi địa chỉ nhận mã recovery nếu cần xác nhận.
- Đừng hiển thị `email_verified=false` như “provider không xác thực danh tính”: đó là claim về email, không phải toàn bộ OIDC authentication.

## 4. Thiết kế data model: local user tách khỏi external identity

Sơ đồ logic:

~~~text
local_users
┌─────────────────────────────────────────┐
│ id (UUID PK)                            │
│ status                                  │
│ display_name / contact_email            │
│ created_at / updated_at                 │
└───────────────┬─────────────────────────┘
                │ 1
                │
                │ n
external_identities
┌─────────────────────────────────────────┐
│ id (PK)                                 │
│ local_user_id (FK → local_users.id)      │
│ issuer  (normalized trusted issuer)     │
│ subject (opaque, case-sensitive)        │
│ registration_id (metadata)              │
│ linked_at / last_login_at               │
│ provider_email (metadata only)          │
│ provider_email_verified                 │
│ UNIQUE(issuer, subject)                 │
└─────────────────────────────────────────┘
~~~

PostgreSQL ví dụ:

~~~sql
CREATE TABLE local_users (
    id UUID PRIMARY KEY,
    status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
    display_name VARCHAR(200),
    contact_email VARCHAR(320),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (status IN ('ACTIVE', 'LOCKED', 'DELETED'))
);

CREATE TABLE external_identities (
    id BIGSERIAL PRIMARY KEY,
    local_user_id UUID NOT NULL
        REFERENCES local_users(id),
    issuer VARCHAR(500) NOT NULL,
    subject VARCHAR(500) NOT NULL,
    registration_id VARCHAR(100) NOT NULL,
    provider_email VARCHAR(320),
    provider_email_verified BOOLEAN NOT NULL DEFAULT FALSE,
    linked_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_login_at TIMESTAMPTZ,
    UNIQUE (issuer, subject),
    CHECK (length(issuer) > 0 AND length(subject) > 0)
);

CREATE INDEX ix_external_identities_local_user
    ON external_identities(local_user_id);

-- Nếu business chỉ cho một account mỗi issuer trên một local user:
-- CREATE UNIQUE INDEX ux_local_user_issuer
--     ON external_identities(local_user_id, issuer);
~~~

**Các ràng buộc quan trọng:**
1. `local_users.id` được ứng dụng/DB cấp, tồn tại độc lập với việc user đổi provider.
2. `external_identities(issuer, subject)` phải có **UNIQUE** để một external identity không thể trỏ sang hai local users.
3. `external_identities.local_user_id` là FK, có thể nhiều external identities nối tới một local user để hỗ trợ liên kết Google + corporate IdP.
4. `registration_id` hữu ích cho audit/routing, **không** thay unique key của OIDC identity.
5. `provider_email` và verified flag là metadata. **Không UNIQUE email để ép auto-merge**.
6. Nếu cho phép nhiều external subjects từ cùng issuer liên kết vào một local user (nhiều tổ chức/sector), cân nhắc có nên đặt `UNIQUE(local_user_id,issuer)` hay không; ràng buộc phụ phải phù hợp business.
7. Kiểu dữ liệu của `subject` cần giữ nguyên case. So sánh collation/case folding của DB phải phù hợp; không dùng kiểu `citext` hoặc collation case-insensitive cho sub.
8. Production cần kế hoạch delete/deactivate, retain audit, quy định giới hạn độ dài và xử lý giá trị claim cực đoan, thay vì tin mọi chuỗi dài tùy ý.

### 4.1. Ví dụ dữ liệu sau nhiều lần login

~~~text
local_users:
  u-100 | Alice | ACTIVE
  u-200 | Bob   | ACTIVE

external_identities:
  https://accounts.google.com | google-sub-A | u-100 | alice-new@...
  https://login.corp.example  | corp-sub-77  | u-100 | alice@corp...
  https://accounts.google.com | google-sub-B | u-200 | bob@...
~~~

Alice được dùng hai nguồn đăng nhập nhưng vẫn có **một local_user_id `u-100`**. Bob có thể có cùng email hiển thị với Alice ở một thời điểm, nhưng khóa external khác và local user vẫn khác.

## 5. Quy trình first login, login lại và thay đổi email

### 5.1. Lần đầu đăng nhập OIDC

1. Browser khởi động `/oauth2/authorization/{registrationId}` qua Spring Security.
2. Spring Security xử lý `state`, callback, authorization code, đổi token, xác minh ID Token (signature, issuer, audience, expiration và các điều kiện như nonce phù hợp).
3. Sau khi authentication **thật sự thành công**, lấy `iss` và `sub` từ validated `OidcUser.getIdToken()`.
4. Chuẩn hóa issuer **chỉ** theo policy đã kiểm chứng (nếu có alias được thừa nhận); giữ subject nguyên văn.
5. Truy vấn `external_identities` theo unique key:
   - Nếu có liên kết: nạp đúng local user và kiểm status (ACTIVE/LOCKED).
   - Nếu chưa có: theo chính sách sản phẩm, tạo local user mới hoặc chuyển sang trang onboarding/pending approval; **không auto-link theo email**.
6. Cập nhật `last_login_at` và metadata được phép; không biến metadata thành quyền truy cập.
7. Chỉ sau khi local account được chấp nhận, hoàn tất login session, redirect về route nội bộ an toàn.

### 5.2. Login lần sau

Truy vấn bằng cùng `(iss,sub)` và nhận lại cùng local user ID. Thay đổi tên/email/avatar không làm đổi quan hệ. Nếu local user bị `LOCKED`, phải chặn login dù OP vẫn xác thực OIDC thành công; một ID Token hợp lệ chỉ xác minh external account, **không tự bỏ qua trạng thái tài khoản nội bộ**.

### 5.3. Hai login gần như đồng thời

Nếu hai tab đăng nhập cùng external identity chưa có trong DB:

~~~text
Request A                         Request B
  Lookup(iss, sub) → not found      Lookup(iss, sub) → not found
  Insert local user u-101           Insert local user u-102
  Insert external link             Insert external link
           └── Chỉ một INSERT được phép thắng UNIQUE(iss, sub).
~~~

Nếu chỉ làm `findByKey().switchIfEmpty(create())` không có transaction/unique constraint, có thể tạo hai local users rồi dẫn tới dữ liệu tách đôi.

**Yêu cầu production:** database enforce `UNIQUE(issuer,subject)`, việc tạo user + external link được làm trong **transaction**, và nhánh thua race phải rollback cả user tạm rồi **đọc lại winner** ở một transaction mới hoặc retry toàn bộ transaction từ ranh giới thích hợp. Không chỉ bắt `DuplicateKeyException` ở giữa transaction PostgreSQL đã abort rồi tiếp tục query trong cùng transaction.

### 5.4. Phân biệt “tự tạo account mới” và “tự liên kết vào account hiện có”

Hai hành động có ý nghĩa bảo mật rất khác:
- **Auto-provision:** nếu external identity chưa có, tạo **một local user mới** với ID mới, không lấy account theo email.
- **Explicit link:** một local user hiện có chủ động chứng minh mình quản lý **cả local session và external account mới**, rồi hệ thống nối external identity mới tới local user ấy.

Không thể xem auto-provision lần đầu là một hành động đã chứng minh quyền truy cập vào account nội bộ có cùng email.

## 6. Liên kết thêm nhà cung cấp: cần một giao thức riêng

Giả sử user đang đăng nhập local `u-100` bằng Google, muốn liên kết corporate IdP.

Luồng an toàn:

~~~text
User local u-100 đã authenticated
            │
            ▼
Chọn "Liên kết tài khoản công ty"
            │
            ▼
POST /account/links/start
  CSRF hợp lệ, xác thực lại khi cần
            │
            ▼
Server tạo link intent trong session/trusted store:
  localUserId=u-100
  targetRegistrationId=corp
  intentId=random
  expiresAt=...
  state/correlation gắn với OIDC flow
            │
            ▼
Redirect sang corporate OIDC provider
            │
            ▼
Callback OIDC sau khi validate code/state/id_token
            │
            ▼
Lấy (trusted iss, sub) của account công ty
            │
            ▼
Một transaction:
  Đọc link intent còn hạn, một lần sử dụng,
  gắn đúng user+session+provider đã yêu cầu;
  nếu (iss,sub) đã link user khác → CONFLICT;
  nếu chưa link → INSERT external link tới u-100;
  nếu đã link chính u-100 → idempotent success.
            │
            ▼
Xóa intent, audit event, thông báo thành công
~~~

**Phần khó không phải SQL INSERT mà là chứng minh hai phía của hành động liên kết.** Bảo vệ:
- Session local phải được xác thực, có thể yêu cầu recent login/MFA trước khi liên kết.
- Nút bắt đầu liên kết dùng **POST và CSRF**; không tạo link chỉ bằng GET hoặc email.
- OAuth2 authorization `state`/nonce và link intent cần ràng buộc session, user ID, registrationId, thời hạn, mục đích và tính one-time; tránh login CSRF và mix-up attacks.
- Callback phải là xác thực **account provider mới**, không dùng form client gửi một `sub` tùy ý.
- Không trộn luồng “sign in” với “link account” dựa vào email hoặc một query param `?linkUser=u-100`.
- Khi có conflict, không tự di chuyển liên kết từ user khác; báo lỗi rõ ràng nhưng không lộ dữ liệu của user đó.
- Nếu callback mở trên nhiều tab, quản lý race theo state/intent; không gắn nhầm vào một phiên vừa đổi user.
- Dùng unique constraints/transaction và audit trước khi công bố liên kết có hiệu lực.
- Việc liên kết **không tự động** nâng cấp role/tenant membership; nội bộ vẫn quyết định quyền.

### 6.1. Nếu external identity đã liên kết local user khác?

Ví dụ corporate `(iss=corp,sub=77)` hiện gắn `u-200`, nhưng user `u-100` cố liên kết. Phải từ chối (`409 Conflict` hoặc error policy tương ứng), chứ không xóa link cũ và chuyển sang `u-100`.

Nếu sản phẩm thực sự muốn hợp nhất hai local accounts, phải có **quy trình account merge riêng**, xác minh cả hai tài khoản, kiểm dữ liệu, quyền, tenant và nhật ký; không thực hiện chỉ vì email trùng.

### 6.2. Unlink an toàn

Xóa external link có thể khiến user không còn cách đăng nhập:
- Yêu cầu reauthentication/MFA cho thao tác gỡ liên kết nhạy cảm.
- Kiểm account còn ít nhất một phương thức đăng nhập được xác minh/khôi phục hợp lệ; hoặc áp chính sách account deactivation tương ứng.
- Xác nhận người dùng và audit before/after.
- Thu hồi session/tokens nếu chính sách yêu cầu; unlink trong DB **không tự revoke token đã cấp tại OP**.
- Tránh cho người khác chiếm lại liên kết trong khoảng race; dùng transaction, unique constraints và quy trình giải quyết tranh chấp.
- Không để một user unlink external identity của account khác bằng ID do client gửi.

## 7. Pairwise subject, đổi client ID và multi-tenant

OIDC có hai cách subject phổ biến: **public** và **pairwise**. Với pairwise subject, cùng một end-user ở provider có thể nhận `sub` **khác nhau cho các relying parties/sector identifiers khác nhau**. Vì vậy:
- Không giả định cùng OP + cùng email = cùng external identity.
- Khi đổi OAuth2/OIDC client registration hoặc sector identifier, giá trị `sub` có thể thay đổi tùy provider policy.
- Nếu cần migration, dùng quy trình provider-supported, người dùng xác minh lại và liên kết tường minh; không tự merge theo email.
- Hai `registrationId` trong Spring Boot trỏ tới cùng issuer chưa chắc tương đương cùng danh tính theo mọi hoàn cảnh; quy tắc OIDC vẫn dựa trên issuer+subject thực nhận và đã verify.

Trong hệ thống multi-tenant còn có:
- Local user có thể là global identity, còn membership/role nằm trong bảng riêng `tenant_memberships`.
- Nếu local user được scope theo tenant, mô hình unique và link policy phải chỉ rõ một external identity có được dùng với nhiều tenants không; không để một login bên tenant A tự cấp vai trò tenant B.
- `groups` hoặc `roles` claim từ IdP không tự cấp `ROLE_ADMIN` nội bộ nếu issuer, tenant scope và mapping chưa được phê duyệt.
- Nếu provider bị mất quyền truy cập, local account status hoặc enterprise offboarding có thể yêu cầu disable sessions và revoke memberships.

## 8. Ví dụ SQL/transaction cho ứng dụng R2DBC thực tế

### 8.1. Lookup external identity

~~~sql
SELECT u.id, u.status, u.display_name, u.contact_email
FROM external_identities e
JOIN local_users u ON u.id = e.local_user_id
WHERE e.issuer = :trustedIssuer
  AND e.subject = :trustedSubject;
~~~

`trustedIssuer` và `trustedSubject` phải được trích từ **validated identity**; không nhận tự do qua JSON body trên API không được bảo vệ.

Kết quả:
- Có row ACTIVE → dùng local ID.
- Có row LOCKED → dừng đăng nhập, không tự mở khóa vì OP login thành công.
- Không có row → theo policy auto-provision hoặc onboarding, tuyệt đối không `SELECT WHERE email = ...` để tự chiếm account.

### 8.2. Tạo local user và link trong transaction

~~~sql
BEGIN;

INSERT INTO local_users (id, status, display_name)
VALUES (:newLocalUserUuid, 'ACTIVE', :displayName);

INSERT INTO external_identities
    (local_user_id, issuer, subject, registration_id,
     provider_email, provider_email_verified)
VALUES
    (:newLocalUserUuid, :trustedIssuer, :trustedSubject,
     :trustedRegistrationId, :emailMetadata, :emailVerified);

COMMIT;
~~~

Nếu unique conflict ở `(issuer,subject)`, rollback **toàn bộ transaction** rồi lấy lại local user đã được request thắng tạo. Trong PostgreSQL, không giả định có thể tiếp tục các query tùy ý sau duplicate-key error **bên trong cùng transaction đã bị abort**. Với R2DBC, dùng `TransactionalOperator` hoặc `@Transactional` đúng reactive transaction context và retry ở ngoài transaction boundary.

### 8.3. Link thêm identity vào local user hiện tại

~~~sql
BEGIN;

-- Đọc/lock link intent còn hạn, thuộc chính session/account hiện tại
-- và đã hoàn tất OIDC callback đúng provider; thao tác consume một lần.

INSERT INTO external_identities
    (local_user_id, issuer, subject, registration_id)
VALUES
    (:authenticatedLocalUserId,
     :verifiedIssuer,
     :verifiedSubject,
     :verifiedRegistrationId);

-- UNIQUE(issuer,subject) bắt xung đột do race/chiếm liên kết.
-- Trường hợp identity đã gắn cùng user có thể xử lý idempotent
-- bằng một nhánh SELECT/check có transaction thích hợp.

COMMIT;
~~~

**Không** chạy một câu `UPDATE external_identities SET local_user_id=:newId WHERE issuer=:iss AND subject=:sub` khi chưa có quy trình account merge được phê duyệt. Lệnh đó có thể “cướp” một external identity đã liên kết user khác.

### 8.4. Ví dụ reactive transaction boundary

**Pseudo-code kiến trúc, không phải file Java độc lập**:

~~~java
Mono<LocalUser> provisionAfterVerifiedLogin(VerifiedOidcIdentity identity) {
    return lookupExisting(identity.key())
        .switchIfEmpty(
            transactionalOperator.transactional(
                createLocalUserAndLink(identity) // cả 2 INSERT trong 1 TX
            )
        );
}
~~~

Đoạn này minh họa **ý định về transaction**, chưa xử lý race. `lookupExisting` và `createLocalUserAndLink` là API do app định nghĩa. Production cần bắt unique conflict và retry **trọn transaction** hoặc đọc lại sau rollback, đồng thời xử lý account locked, cancellation, replica lag và operation idempotency.

## 9. Project chạy được: WebFlux + OIDC login + local identity store

Ví dụ học tập dùng **Java 17+**, **Spring Boot 3.3.13**, Gradle 8.x, Spring Security reactive OAuth2 Client. Bài cố định phiên bản để thuận tiện đối chiếu API; production dùng bản Spring Boot/Security đang được hỗ trợ.

Mục đích:
- Spring Security cấu hình OAuth2/OIDC login với provider Google.
- Sau khi **Spring Security xác minh đăng nhập OIDC thực sự**, success handler dùng `iss+sub` để lookup/create local user.
- `GET /me` đọc local user đã được provision từ external identity; **không** tự tạo user trên GET.
- Local users và links được mô phỏng bằng hai maps + synchronized critical section **chỉ cho JVM demo** để giữ uniqueness nội bộ.
- Có API service `linkAfterConfirmedFlow(...)` cho explicit linking, nhưng **không expose HTTP endpoint** vì project không triển khai toàn bộ session-bound OAuth2 linking intent. Tests gọi service sau khi đã mô phỏng một flow được xác minh.
- Các tests có thể chạy **offline**, bằng mock OIDC principal/Spring Security Test. Muốn hoàn tất login Google thật phải dùng client ID/secret và redirect URI thực đã đăng ký.

### 9.1. Cấu trúc

~~~text
webflux-oidc-local-identity/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/demo/
    │   │   ├── OidcLocalIdentityApplication.java
    │   │   ├── ExternalIdentity.java
    │   │   ├── LocalIdentityStore.java
    │   │   ├── SecurityConfig.java
    │   │   └── ProfileController.java
    │   └── resources/application.properties
    └── test/java/demo/
        └── LocalIdentityTests.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'webflux-oidc-local-identity'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

`src/main/resources/application.properties`:

~~~properties
# Dùng cấu hình provider Google tích hợp sẵn của Spring Boot.
# Hai giá trị demo chỉ đủ để ứng dụng khởi động/test offline;
# LOGIN GOOGLE THẬT CẦN thay bằng credentials đã đăng ký tại Google.
spring.security.oauth2.client.registration.google.client-id=offline-demo-client
spring.security.oauth2.client.registration.google.client-secret=offline-demo-secret
spring.security.oauth2.client.registration.google.scope=openid,profile,email
~~~

`offline-demo-client` và `offline-demo-secret` **không phải credentials thật**, nên browser không thể hoàn tất login Google với chúng. Test ở mục 10 dùng Spring Security Test để giả lập identity đã verify. Để chạy Google thật, cấp credentials theo cơ chế secrets an toàn và đăng ký redirect URI công khai dạng `{baseUrl}/login/oauth2/code/google` với proxy/TLS/hostname chính xác.

Đừng commit client secret production. Không lấy `OIDC client id` từ user input để tự chọn audience tin cậy.

### 9.2. Main class

`src/main/java/demo/OidcLocalIdentityApplication.java`:

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OidcLocalIdentityApplication {
    public static void main(String[] args) {
        SpringApplication.run(OidcLocalIdentityApplication.class, args);
    }
}
~~~

### 9.3. ExternalIdentity: chỉ tạo từ validated OIDC principal trong ứng dụng thật

`src/main/java/demo/ExternalIdentity.java`:

~~~java
package demo;

import org.springframework.security.oauth2.core.oidc.user.OidcUser;

// Package-private: data object của dịch vụ, không phải request body API.
record ExternalIdentity(
    String issuer,
    String subject,
    String email,
    boolean emailVerified
) {
    record Key(String issuer, String subject) {}

    Key key() {
        // Email intentionally NOT part of the identity key.
        return new Key(issuer, subject);
    }

    static ExternalIdentity fromVerifiedGoogleOidc(OidcUser user) {
        if (user == null || user.getIdToken() == null) {
            throw new IllegalArgumentException("Missing verified ID Token");
        }

        var token = user.getIdToken();
        String iss = token.getClaimAsString("iss");
        String sub = token.getSubject();

        if (sub == null || sub.isBlank() || sub.length() > 500) {
            throw new IllegalArgumentException("Invalid OIDC subject");
        }

        // Chỉ chấp nhận hai issuer alias mà tài liệu Google mô tả.
        // QUAN TRỌNG: phải gọi sau khi Spring Security đã validate
        // Google ID Token (signature, aud, iss, exp, nonce...).
        if ("accounts.google.com".equals(iss)) {
            iss = "https://accounts.google.com";
        }

        if (!"https://accounts.google.com".equals(iss)) {
            throw new IllegalArgumentException("Unexpected OIDC issuer");
        }

        String email = token.getClaimAsString("email");
        boolean verified = Boolean.TRUE.equals(
            token.getClaimAsBoolean("email_verified"));

        return new ExternalIdentity(iss, sub, email, verified);
    }
}
~~~

**Giải thích và cảnh báo:**
- `fromVerifiedGoogleOidc` **không xác minh chữ ký của ID Token**. Nó chỉ trích claims từ một `OidcUser` đã được Spring Security đăng nhập/verify trước đó. Một `OidcUser` tự tạo trong test không chứng minh signature.
- Chuỗi `iss` được so với allowlist Google; alias `accounts.google.com` chỉ được canonicalize **sau** khi đã qua provider verification thật. Không tùy tiện normalize các OP khác như vậy.
- `sub` được giữ đúng case và giá trị opaque. Không trim hoặc lower-case.
- `email` và `emailVerified` chỉ là metadata, không nằm trong `Key`.
- Provider khác cần adapter + issuer allowlist riêng; không gọi phương thức `fromVerifiedGoogleOidc` cho JWT/OAuth2 UserInfo bất kỳ.

### 9.4. LocalIdentityStore: unique identity và explicit link

`src/main/java/demo/LocalIdentityStore.java`:

~~~java
package demo;

import java.util.HashMap;
import java.util.Map;
import java.util.UUID;

import org.springframework.stereotype.Component;

import reactor.core.publisher.Mono;

@Component
class LocalIdentityStore {

    record LocalUser(
        UUID id,
        String lastSeenEmail,
        boolean emailVerified,
        boolean enabled
    ) {}

    static final class LinkConflictException extends RuntimeException {
        LinkConflictException() {
            super("External identity is already linked");
        }
    }

    private final Map<UUID, LocalUser> users = new HashMap<>();
    private final Map<ExternalIdentity.Key, UUID> links =
        new HashMap<>();

    // MÔ PHỎNG: critical section ngắn trong một JVM.
    // Production phải thay bằng reactive database + UNIQUE + TX.
    Mono<LocalUser> signIn(ExternalIdentity identity) {
        return Mono.fromSupplier(() -> {
            synchronized (this) {
                UUID existing = links.get(identity.key());

                if (existing != null) {
                    LocalUser oldUser = users.get(existing);
                    if (oldUser == null) {
                        throw new IllegalStateException("Dangling link");
                    }
                    if (!oldUser.enabled()) {
                        throw new IllegalStateException("Account disabled");
                    }

                    // Email chỉ là metadata; ID không thay đổi.
                    LocalUser updated = new LocalUser(
                        oldUser.id(),
                        identity.email(),
                        identity.emailVerified(),
                        true
                    );

                    users.put(existing, updated);
                    return updated;
                }

                UUID localId = UUID.randomUUID();
                LocalUser created = new LocalUser(
                    localId,
                    identity.email(),
                    identity.emailVerified(),
                    true
                );

                users.put(localId, created);
                links.put(identity.key(), localId);
                return created;
            }
        });
    }

    Mono<LocalUser> find(ExternalIdentity.Key key) {
        return Mono.fromSupplier(() -> {
            synchronized (this) {
                UUID id = links.get(key);
                return id == null ? null : users.get(id);
            }
        });
    }

    // CHỈ ĐƯỢC GỌI SAU flow link đã xác minh BOTH:
    //  (1) authenticated local user + CSRF/re-auth
    //  (2) OIDC callback mới + state/session-bound link intent
    // Project KHÔNG expose method này qua HTTP request.
    Mono<LocalUser> linkAfterConfirmedFlow(
            UUID authenticatedLocalUserId,
            ExternalIdentity verifiedNewIdentity) {

        return Mono.fromSupplier(() -> {
            synchronized (this) {
                LocalUser local = users.get(authenticatedLocalUserId);
                if (local == null || !local.enabled()) {
                    throw new IllegalArgumentException(
                        "Local account unavailable");
                }

                UUID owner = links.get(verifiedNewIdentity.key());

                if (owner != null
                    && !owner.equals(authenticatedLocalUserId)) {

                    throw new LinkConflictException();
                }

                // Nếu đã link chính user này: idempotent.
                links.putIfAbsent(
                    verifiedNewIdentity.key(),
                    authenticatedLocalUserId
                );
                return local;
            }
        });
    }
}
~~~

**Vì sao code không dùng email?**
- `signIn` lookup qua `identity.key() = (issuer, subject)`.
- Với key mới, luôn cấp local ID mới. Không gọi `findByEmail`.
- Với key cũ, local ID giữ nguyên dù email thay đổi.
- `linkAfterConfirmedFlow` chỉ chấp nhận local ID của account đã xác thực bằng một flow khác; nó **không phải** API cho client tự gửi local ID/external subject.
- Nếu external identity đã link user khác, ném `LinkConflictException`. Không chuyển quyền sở hữu liên kết.
- Nếu đã link cùng user, thực hiện idempotent.
- `enabled` minh họa kiểm status local, để OP login thành công không tự mở khóa account.

**Giới hạn lớn:** `synchronized` bảo vệ một JVM và `HashMap` trong demo, không phải database, không durable, không hỗ trợ multi-instance, không phải chiến lược reactive I/O. Critical section trong ví dụ rất ngắn và không làm network/DB/blocking I/O; production dùng `R2dbcEntityTemplate`/`DatabaseClient`, unique key và transaction. Không đặt blocking JDBC/file/network bên trong `synchronized` hoặc trên Netty event loop.

### 9.5. SecurityConfig: ghi liên kết sau khi OIDC login thành công

`src/main/java/demo/SecurityConfig.java`:

~~~java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.oauth2.client.authentication.OAuth2AuthenticationToken;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authentication.RedirectServerAuthenticationSuccessHandler;
import org.springframework.security.web.server.authentication.ServerAuthenticationSuccessHandler;

import reactor.core.publisher.Mono;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
class SecurityConfig {

    @Bean
    ServerAuthenticationSuccessHandler provisionOnOidcLogin(
            LocalIdentityStore store) {

        var redirect =
            new RedirectServerAuthenticationSuccessHandler("/me");

        return (filterExchange, authentication) -> {
            if (!(authentication instanceof OAuth2AuthenticationToken oauth)
                || !"google".equals(
                    oauth.getAuthorizedClientRegistrationId())
                || !(oauth.getPrincipal() instanceof OidcUser oidc)) {

                return Mono.error(new BadCredentialsException(
                    "Expected verified Google OIDC login"));
            }

            final ExternalIdentity identity;
            try {
                identity = ExternalIdentity.fromVerifiedGoogleOidc(oidc);
            }
            catch (IllegalArgumentException malformedClaims) {
                return Mono.error(new BadCredentialsException(
                    "Untrusted OIDC identity", malformedClaims));
            }

            // Phải hoàn tất local-user provisioning TRƯỚC
            // khi coi login là thành công về mặt ứng dụng.
            return store.signIn(identity)
                .then(redirect.onAuthenticationSuccess(
                    filterExchange, authentication));
        };
    }

    @Bean
    SecurityWebFilterChain security(
            ServerHttpSecurity http,
            ServerAuthenticationSuccessHandler provisionOnOidcLogin) {

        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/").permitAll()
                .anyExchange().authenticated()
            )
            .oauth2Login(oauth2 -> oauth2
                .authenticationSuccessHandler(provisionOnOidcLogin))
            // Giữ CSRF mặc định cho các thao tác session-based.
            .csrf(Customizer.withDefaults())
            .build();
    }
}
~~~

Giải thích:
1. Spring Security OAuth2 Client cấu hình một `registrationId=google`. OIDC flow dựa trên `scope=openid`; có ID Token, không chỉ một profile email.
2. Handler chỉ xử lý `OAuth2AuthenticationToken` có principal là `OidcUser` và registration `google`. Một authentication kiểu khác không được coi là verified Google identity.
3. `fromVerifiedGoogleOidc` chỉ trích key sau khi Spring Security đã xử lý OIDC login. Không chấp nhận trực tiếp `iss/sub` từ request.
4. `store.signIn(identity)` là publisher; `.then(redirect.onAuthenticationSuccess(...))` đợi nó hoàn tất trước redirect. Không `block()`, không tự `subscribe()`.
5. Sau sign-in, session SecurityContext do Spring Security quản lý. **Local user không tự được biến thành `Authentication.getPrincipal()` của framework**; nếu các service cần local UUID, chúng phải resolve từ verified identity hoặc dùng custom principal/mapping được cấu hình nhất quán.
6. `RedirectServerAuthenticationSuccessHandler` sẽ dùng saved request nếu có, nếu không dùng `/me`; với production kiểm redirect target để không tạo open redirect và không khôi phục unsafe POST mù quáng.
7. Nếu provisioning bị lỗi hoặc local user bị khóa, không được redirect thành công; production cần failure UX/audit phù hợp và bảo đảm không giữ lại authentication được dùng như quyền nội bộ khi bước provisioning thất bại.
8. `csrf(Customizer.withDefaults())` giữ CSRF; không disable để thuận tiện cho thao tác linking.
9. Demo chỉ auto-provision **account hoàn toàn mới**. Nó không gọi `linkAfterConfirmedFlow` từ success handler vì login không đồng nghĩa người dùng yêu cầu link với local account đang tồn tại.

### 9.6. Controller: chỉ đọc local user đã provision

`src/main/java/demo/ProfileController.java`:

~~~java
package demo;

import org.springframework.http.HttpStatus;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Mono;

@RestController
class ProfileController {

    public record MeView(
        String localUserId,
        String lastSeenEmail,
        boolean emailVerified
    ) {}

    private final LocalIdentityStore store;

    ProfileController(LocalIdentityStore store) {
        this.store = store;
    }

    @GetMapping("/")
    Mono<String> home() {
        return Mono.just("Start OIDC login at /oauth2/authorization/google");
    }

    @GetMapping("/me")
    Mono<MeView> me(@AuthenticationPrincipal OidcUser principal) {
        if (principal == null) {
            return Mono.error(new ResponseStatusException(
                HttpStatus.UNAUTHORIZED));
        }

        final ExternalIdentity identity;
        try {
            identity = ExternalIdentity.fromVerifiedGoogleOidc(principal);
        }
        catch (IllegalArgumentException invalid) {
            return Mono.error(new ResponseStatusException(
                HttpStatus.UNAUTHORIZED, "Invalid OIDC principal"));
        }

        return store.find(identity.key())
            .switchIfEmpty(Mono.error(
                new ResponseStatusException(
                    HttpStatus.CONFLICT,
                    "Local account has not been provisioned")))
            .map(user -> new MeView(
                user.id().toString(),
                user.lastSeenEmail(),
                user.emailVerified()
            ));
    }
}
~~~

**Vì sao `GET /me` không tự tạo local user?** GET phải là thao tác đọc. Tạo user trong GET khiến crawler, prefetch, test/middleware hoặc một code path đọc profile gây side effect ngoài ý định. Project thiết kế provisioning ở success handler của OIDC login; controller chỉ lookup.

Không trả raw ID Token, access token, refresh token, client secret, toàn bộ `OidcUser.getClaims()` hoặc session ID. Local UUID thường không phải bí mật, nhưng authorization của resources vẫn phải kiểm quyền theo local user/tenant trên backend.

## 10. Kiểm thử bằng JUnit, StepVerifier và WebTestClient

Bộ test sau **không kết nối Google thật**. Nó cố ý tạo các `ExternalIdentity` đã được mô phỏng là “verified” để thử logic mapping, dùng `mockOidcLogin()` để kiểm WebFlux SecurityContext và test success handler theo unit. Việc mock không chứng minh validation cryptographic của ID Token; cần thêm integration/E2E tests với OIDC Provider thực hoặc test provider đáng tin trong môi trường tích hợp.

`src/test/java/demo/LocalIdentityTests.java`:

~~~java
package demo;

import java.util.List;
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.HttpStatus;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.web.server.MockServerWebExchange;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.client.authentication.OAuth2AuthenticationToken;
import org.springframework.security.oauth2.core.oidc.OidcIdToken;
import org.springframework.security.oauth2.core.oidc.user.DefaultOidcUser;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.security.web.server.WebFilterExchange;
import org.springframework.security.web.server.authentication.ServerAuthenticationSuccessHandler;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockOidcLogin;
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class LocalIdentityTests {

    @Autowired
    ApplicationContext context;

    @Autowired
    LocalIdentityStore store;

    @Autowired
    ServerAuthenticationSuccessHandler provisionOnOidcLogin;

    private WebTestClient client;

    @BeforeEach
    void setup() {
        client = WebTestClient.bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    private ExternalIdentity external(
            String issuer, String subject, String email) {

        // Fixture test: giả định key đã được một OP xác minh.
        return new ExternalIdentity(
            issuer, subject, email, true);
    }

    private OidcUser fakeGoogleOidc(
            String subject, String email) {

        OidcIdToken token = OidcIdToken.withTokenValue("test-only")
            .claim("iss", "https://accounts.google.com")
            .claim("sub", subject)
            .claim("email", email)
            .claim("email_verified", true)
            .build();

        return new DefaultOidcUser(
            List.of(new SimpleGrantedAuthority("OIDC_USER")),
            token
        );
    }

    @Test
    void sameIssuerAndSubjectKeepLocalIdAfterEmailChange() {
        var before = external(
            "https://accounts.google.com",
            "stable-sub-01", "old@demo.test");

        var after = external(
            "https://accounts.google.com",
            "stable-sub-01", "new@demo.test");

        StepVerifier.create(
            store.signIn(before).flatMap(first ->
                store.signIn(after).map(second ->
                    new String[] {
                        first.id().toString(),
                        second.id().toString(),
                        second.lastSeenEmail()
                    })))
            .assertNext(result -> {
                assertThat(result[0]).isEqualTo(result[1]);
                assertThat(result[2]).isEqualTo("new@demo.test");
            })
            .verifyComplete();
    }

    @Test
    void sameEmailWithDifferentSubjectsMustNotMerge() {
        var alice = external(
            "https://accounts.google.com",
            "stable-sub-alice-02", "shared@demo.test");
        var bob = external(
            "https://accounts.google.com",
            "stable-sub-bob-02", "shared@demo.test");

        StepVerifier.create(Mono.zip(
            store.signIn(alice), store.signIn(bob)))
            .assertNext(pair ->
                assertThat(pair.getT1().id())
                    .isNotEqualTo(pair.getT2().id()))
            .verifyComplete();
    }

    @Test
    void sameSubjectButDifferentTrustedIssuerIsDifferentIdentity() {
        var first = external(
            "https://idp-a.example", "subject-03", "a@demo.test");
        var second = external(
            "https://idp-b.example", "subject-03", "a@demo.test");

        // Test ở store: giả định hai issuer đều là verified.
        // Production adapter phải validate từng issuer trước khi gọi.
        StepVerifier.create(Mono.zip(
            store.signIn(first), store.signIn(second)))
            .assertNext(pair ->
                assertThat(pair.getT1().id())
                    .isNotEqualTo(pair.getT2().id()))
            .verifyComplete();
    }

    @Test
    void subjectComparisonIsCaseSensitive() {
        var upper = external(
            "https://idp-a.example", "CaseSensitive", "a@demo.test");
        var lower = external(
            "https://idp-a.example", "casesensitive", "a@demo.test");

        StepVerifier.create(Mono.zip(
            store.signIn(upper), store.signIn(lower)))
            .assertNext(pair ->
                assertThat(pair.getT1().id())
                    .isNotEqualTo(pair.getT2().id()))
            .verifyComplete();
    }

    @Test
    void explicitLinkAllowsTwoProvidersForOneLocalUser() {
        var google = external(
            "https://accounts.google.com",
            "link-google-05", "a@demo.test");
        var corporate = external(
            "https://corp.example",
            "link-corp-05", "new@corp.test");

        StepVerifier.create(
            store.signIn(google)
                .flatMap(user ->
                    store.linkAfterConfirmedFlow(
                        user.id(), corporate)
                      .then(store.signIn(corporate))
                      .map(alsoSignedIn ->
                          new boolean[] {
                              user.id().equals(alsoSignedIn.id())
                          })))
            .assertNext(result -> assertThat(result[0]).isTrue())
            .verifyComplete();
    }

    @Test
    void identityAlreadyLinkedToAnotherLocalUserIsConflict() {
        var googleA = external(
            "https://accounts.google.com",
            "first-account-06", "a@demo.test");
        var googleB = external(
            "https://accounts.google.com",
            "second-account-06", "a@demo.test");

        StepVerifier.create(
            store.signIn(googleA)
                .flatMap(userA -> store.signIn(googleB)
                    .flatMap(userB ->
                        store.linkAfterConfirmedFlow(
                            userA.id(), googleB))))
            .expectError(
                LocalIdentityStore.LinkConflictException.class)
            .verify();
    }

    @Test
    void missingOrUntrustedIssuerIsRejectedAtOidcBoundary() {
        OidcIdToken token = OidcIdToken.withTokenValue("untrusted")
            .claim("iss", "https://attacker.example")
            .claim("sub", "unknown-sub-07")
            .build();

        OidcUser user = new DefaultOidcUser(
            List.of(new SimpleGrantedAuthority("OIDC_USER")), token);

        assertThatThrownBy(() ->
            ExternalIdentity.fromVerifiedGoogleOidc(user))
            .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void mockOidcLoginCanReadAlreadyProvisionedLocalUser() {
        var verified = external(
            "https://accounts.google.com",
            "web-profile-08", "reader@demo.test");

        AtomicReference<String> id = new AtomicReference<>();

        StepVerifier.create(store.signIn(verified))
            .assertNext(user -> id.set(user.id().toString()))
            .verifyComplete();

        client.mutateWith(mockOidcLogin()
                .idToken(token -> token
                    .claim("iss", "https://accounts.google.com")
                    .claim("sub", "web-profile-08")
                    .claim("email", "reader@demo.test")
                    .claim("email_verified", true)))
            .get().uri("/me")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.localUserId").isEqualTo(id.get())
            .jsonPath("$.lastSeenEmail")
                .isEqualTo("reader@demo.test");
    }

    @Test
    void mockOidcLoginDoesNotAutoProvisionOnGet() {
        client.mutateWith(mockOidcLogin()
                .idToken(token -> token
                    .claim("iss", "https://accounts.google.com")
                    .claim("sub", "never-provisioned-09")))
            .get().uri("/me")
            .exchange()
            .expectStatus().isEqualTo(HttpStatus.CONFLICT);
    }

    @Test
    void anonymousProfileIsRedirectedToLogin() {
        client.get().uri("/me")
            .exchange()
            .expectStatus().is3xxRedirection();
    }

    @Test
    void oidcAuthenticationSuccessProvisionsBeforeRedirect() {
        String subject = "success-sub-11";
        OidcUser oidc = fakeGoogleOidc(
            subject, "success@demo.test");

        var authentication = new OAuth2AuthenticationToken(
            oidc, oidc.getAuthorities(), "google");

        var exchange = MockServerWebExchange.from(
            MockServerHttpRequest.get(
                "/login/oauth2/code/google"));

        var filterExchange = new WebFilterExchange(
            exchange, e -> Mono.empty());

        StepVerifier.create(
            provisionOnOidcLogin.onAuthenticationSuccess(
                filterExchange, authentication))
            .verifyComplete();

        assertThat(exchange.getResponse().getStatusCode())
            .isEqualTo(HttpStatus.FOUND);

        var key = new ExternalIdentity.Key(
            "https://accounts.google.com", subject);

        StepVerifier.create(store.find(key))
            .assertNext(local ->
                assertThat(local.lastSeenEmail())
                    .isEqualTo("success@demo.test"))
            .verifyComplete();
    }

    @Test
    void repeatSameLinkForSameLocalUserIsIdempotent() {
        var google = external(
            "https://accounts.google.com",
            "link-main-12", "a@demo.test");
        var corporate = external(
            "https://corp.example",
            "link-secondary-12", "a@corp.test");

        StepVerifier.create(store.signIn(google).flatMap(user ->
            store.linkAfterConfirmedFlow(user.id(), corporate)
                .then(store.linkAfterConfirmedFlow(
                    user.id(), corporate))
                .map(linked -> user.id().equals(linked.id()))))
            .expectNext(true)
            .verifyComplete();
    }
}
~~~

**Đọc đúng ý nghĩa tests:**
- Hai lần login cùng `(iss,sub)` và email khác nhau → **một local ID**.
- Hai subjects khác nhau dù email trùng → **hai local IDs**.
- Hai issuers khác nhau dù subject trùng → **hai identities**.
- Subject được so sánh case-sensitive.
- Explicit link **sau khi đã chứng minh đủ hai phía** nối provider thứ hai vào user hiện tại; method demo không mở qua HTTP.
- Link identity đã thuộc account khác → conflict, không “cướp” link.
- Issuer không trong allowlist Google bị từ chối ở adapter.
- `mockOidcLogin()` của Spring Security Test đưa principal giả vào WebFlux SecurityContext để test endpoint đọc profile.
- `GET /me` không tự tạo user; mock login bypass success handler, nên nếu chưa provision phải 409 theo contract demo.
- Test success handler gọi trực tiếp handler với một OIDC fixture và quan sát local account được tạo **trước** redirect; điều này kiểm orchestration của handler, **không chứng minh ID token fixture đã có chữ ký thật**.
- Link cùng external key vào chính local user lần nữa cho kết quả idempotent.

### 10.1. Test này chưa chứng minh được gì?

Mock `OidcIdToken` được tạo bằng Java code không có xác minh chữ ký. Test không thay thế integration test OAuth2/OIDC thực với provider hoặc một test IdP được cấu hình đúng. Không được suy từ `mockOidcLogin` sang kết luận rằng signature, audience, issuer, nonce, PKCE, state, HTTPS redirect URI và JWKS được bảo vệ trong production.

Cũng cần kiểm production case:
- Provider không trả `email` hoặc trả `email_verified=false`.
- Subject pairwise thay đổi khi đổi client/sector.
- Client đăng nhập đồng thời → unique constraint/transaction chỉ sinh một local user.
- Local user bị LOCKED/DELETED vẫn không được dùng dù ID Token hợp lệ.
- Hai account cùng email nhưng khác `iss/sub` không bị merge.
- External identity đã thuộc user khác thì explicit link bị từ chối.
- Callback link có state sai/hết hạn hoặc local session thay đổi thì bị từ chối.
- User unlink phương thức đăng nhập cuối cùng phải bị chặn hoặc chuyển sang flow recovery có xác minh.
- Không reuse một `registrationId` trỏ sang issuer khác sau migration mà không có dữ liệu chuyển đổi được phê duyệt.
- OIDC access/refresh tokens được bảo vệ và không bị log.

### 10.2. Chạy dự án và xem kết quả

Yêu cầu JDK 17+, Gradle 8.x và mạng để tải dependencies lần đầu. Từ thư mục dự án:

~~~bash
gradle test
~~~

Nếu có Gradle Wrapper, dùng `./gradlew test` trên Linux/macOS hoặc `gradlew.bat test` trên Windows. Dự án được thiết kế để test **offline không gọi Google**, sau khi dependencies đã có. Kỳ vọng 12 phương thức test pass khi API/dependencies đúng; **kết quả biên dịch phải được xác nhận bằng cách chạy thực tế**, không coi đoạn hướng dẫn là log Gradle.

Có thể chạy:

~~~bash
gradle bootRun
~~~

Mở `http://localhost:8080/` để đọc hướng dẫn route và `/oauth2/authorization/google` để bắt đầu OAuth2 flow. Với client ID/secret demo, Google sẽ không chấp nhận actual login. Muốn đăng nhập thật, cấu hình credentials và redirect URI đã đăng ký đúng host/scheme/cổng; dùng HTTPS trong môi trường Internet, không dùng HTTP Basic hay hack query `?sub=...` để thay OAuth2 callback.

## 11. Vì sao `OAuth2AuthorizedClient` không thay bảng external identity?

Spring Security có `OAuth2AuthorizedClient`/`ReactiveOAuth2AuthorizedClientService` hoặc repository để giữ thông tin client registration, access token và refresh token của một authorization grant. Đây là cấu trúc **quản lý OAuth2 tokens**, không phải cơ sở dữ liệu local account mapping.

| Cấu trúc | Mục đích |
| --- | --- |
| `ClientRegistration` / `ReactiveClientRegistrationRepository` | Provider endpoints, client ID, scopes, redirect URI và cấu hình OAuth2 |
| `OAuth2AuthenticationToken` | Kết quả authentication hiện tại, principal/authorities/registration ID |
| `OidcUser` và `OidcIdToken` | Identity đã được OIDC login pipeline xác minh |
| `OAuth2AuthorizedClient` | Token được cấp cho client nhằm gọi tài nguyên của provider |
| `local_users` | Danh tính nội bộ lâu dài, làm khóa chính cho nghiệp vụ |
| `external_identities` | Unique link `(trusted iss,sub) → localUserId` |
| `tenant_memberships` | Role/permission theo tenant và chính sách doanh nghiệp |

Đừng lấy refresh token làm “khóa nhận dạng” của user. Token có thể rotate/hết hạn/revoke, trong khi local user ID phải tồn tại độc lập.

Token persistence trong production phải bảo vệ secrets, mã hóa khi lưu, phân quyền, quản lý rotation/revocation; không để token value trong JSON trả về `/me` hoặc application logs.

## 12. Tình huống migration thường khó

### 12.1. Hệ thống cũ chỉ có email

Nếu legacy local users được lưu theo email, **không migrate bằng cách tự động ghép tất cả Google identities có cùng email**. Đường an toàn:
1. Cho user đăng nhập vào **legacy local account** bằng cơ chế cũ hoặc account recovery đáng tin.
2. Từ local session đã xác thực, bắt đầu explicit link flow.
3. Xác thực provider và liên kết `iss/sub` đúng vào local ID trong transaction.
4. Audit và thông báo.
5. Chỉ bỏ cơ chế cũ khi user có cách đăng nhập/khôi phục hợp lệ và chính sách cho phép.

Nếu không thể xác minh tài khoản cũ, chuyển sang quá trình hỗ trợ có xác minh danh tính độc lập; không dùng `email_verified` đơn lẻ để vượt các bước.

### 12.2. Nhà cung cấp thay đổi issuer URL

`iss` là namespace bảo mật, không chỉ một chuỗi kỹ thuật. Nếu một IdP đổi issuer, cần:
- Xác nhận thay đổi bằng tài liệu/kênh quản trị đáng tin.
- Kiểm lại JWKS, redirect, audience/client IDs, discovery metadata và validation.
- Xác định provider có **đảm bảo mapping subject** không.
- Chuyển dữ liệu identity links bằng migration được review, rollback plan và audit.
- Không bỏ điều kiện issuer hoặc normalize tùy tiện để “cho login qua”.

### 12.3. Thay OIDC client/sector làm đổi pairwise subject

Với pairwise `sub`, thay RP/sector có thể tạo subject mới. Không phải account mất danh tính nhưng app không thể tự suy ra hai subjects là một bằng email. Cần provider-assisted migration hoặc explicit re-link bằng cách chứng minh cả hai danh tính.

### 12.4. Gộp hai local users có đơn hàng riêng

Hai local IDs tồn tại có thể có orders, invoices, permissions, tenant memberships và audit độc lập. Account merge không chỉ là cập nhật bảng links. Phải xác minh quyền quản lý cả hai tài khoản, kiểm tác động dữ liệu, xử lý reference ownership, transaction/migration và audit. Không dùng `UPDATE external_identities SET local_user_id=...` làm biện pháp merge tự phát.

## 13. Liên kết tài khoản và Spring Security session/authorization

Sau OIDC login:
- Spring Security có authentication của external provider.
- Service nội bộ cần local user ID để truy vấn quyền theo tenant, tài nguyên sở hữu.
- Không mặc định `Authentication.getName()` là local UUID; nó có thể chính là `sub`/username của provider.
- Không mặc định `OidcUser.getAuthorities()` phản ánh role nội bộ. Authority `SCOPE_profile` thể hiện OAuth2 scope, **không** phải `ROLE_ADMIN`.
- Nếu cần custom principal mang local user ID, hãy áp trong một authentication mapping/service được cấu hình đồng bộ với SecurityContext, xử lý session refresh và quyền thay đổi.
- Trong project demo, endpoint `/me` lookup từ verified external identity; ở production có thể cache mapping theo session/short TTL nhưng phải invalidate khi disable/link/unlink/permission thay đổi.
- Tài nguyên API phải kiểm owner/tenant bằng local ID đã resolve, không kiểm access bằng email.
- Logout session ứng dụng không tự unlink account, không tự revoke mọi token/SSO sessions; cần chính sách OIDC logout/revocation riêng.
- Cookie session, CSRF, OAuth2 state/nonce, PKCE và browser redirect là các lớp bảo vệ khác nhau, phải cùng được kiểm thử.

### 13.1. Thao tác nào cần CSRF?

Bắt đầu liên kết, xác nhận link, unlink hoặc đổi phương thức đăng nhập mặc định thường là những **POST/DELETE** nhạy cảm nếu user xác thực bằng cookie session. Cần CSRF token và fresh auth theo rủi ro. OAuth2 callback của Spring Security có state/correlation protocol riêng; không thay nó bằng một endpoint POST public nhận subject tùy ý.

**Không** tắt CSRF toàn app để “link Google dễ hơn”. Nếu gặp 403, xác định request nào bị CSRF filter từ chối và điều chỉnh flow đúng, không vô hiệu bảo vệ.

## 14. Troubleshooting

| Hiện tượng | Nguyên nhân thường gặp | Cách chẩn đoán |
| --- | --- | --- |
| Đăng nhập lại sinh local user mới | App lookup theo email/registrationId hoặc không lưu link | Truy vấn đúng unique `(iss,sub)`, dùng transaction |
| Đổi email làm mất đơn hàng | User ID bị suy từ email hoặc local account tái tạo | Chuyển ownership sang UUID local bất biến |
| Hai người được login cùng local account | Auto-link theo email/shared username | Dừng auto-merge, audit tài khoản bị ảnh hưởng |
| Callback có Google `sub` nhưng adapter không tìm được key | Issuer alias, case-normalization, thay client/sector | Kiểm issuer verified, canonical mapping có kiểm soát và exact subject |
| Login thành công ở OP nhưng app báo lỗi | Local user LOCKED, DB link conflict hoặc provisioning lỗi | Kiểm local status, unique violations, error UX |
| Hai tab tạo hai tài khoản | Check-then-insert race, thiếu unique/transaction | Unique `(iss,sub)` + retry ngoài transaction boundary |
| Một external account bị link sang user khác | Update link owner trực tiếp hoặc race | UNIQUE + reject conflict, không chuyển owner |
| Email chưa verified nhưng nhận role ADMIN | Dùng email domain để cấp quyền không đủ xác minh | Quyền nội bộ theo tenant/SCIM/membership đáng tin |
| Local user có hai provider nhưng chỉ login một provider được | Link flow chưa ghi đúng issuer/sub, session/cache cũ | Kiểm persisted links và ID Token validation |
| Callback `redirect_uri_mismatch` | URL công khai/proxy/scheme khác registered URI | Cấu hình HTTPS, forwarded headers đáng tin và client registration |
| Endpoint `/me` trả 409 trong mock test | `mockOidcLogin` bỏ qua success handler nên chưa provision | Provision fixture hoặc test trực tiếp success handler |
| Account bị xóa vẫn login được | OP xác minh thành công nhưng app không kiểm status | Chặn local LOCKED/DELETED trước quyền nội bộ |
| Unauthorized sau link/unlink | Session SecurityContext/cache chưa cập nhật | Rà chính sách reauth, cache invalidation và logout |
| Access token bị dùng như user ID | Token rotate, scope khác, không phải stable identity | Dùng verified `iss/sub` |
| Spring MVC OAuth2Login API không khớp | Dùng `HttpSecurity`/Servlet thay `ServerHttpSecurity` | Sử dụng stack reactive và `ReactiveClientRegistrationRepository` |

## 15. Các câu hỏi tự kiểm tra

1. **Khóa ổn định của một OIDC identity là gì?** Cặp `(verified issuer, subject)`, không chỉ `sub`.
2. **Vì sao `registrationId=google` không đủ?** Đó là tên cấu hình Spring client, không phân biệt người dùng và có thể đổi.
3. **Tại sao không dùng email làm primary key?** Email có thể đổi, tái sử dụng, trùng hoặc chưa verified.
4. **`email_verified=true` cho phép auto-link vào local user cùng email không?** Không, chưa chứng minh quyền sở hữu local user hiện tại.
5. **Alice đổi email nhưng `iss/sub` không đổi thì local ID ra sao?** Giữ nguyên, chỉ metadata có thể cập nhật.
6. **Hai issuers có cùng `sub` thì sao?** Là hai external identities khác nhau.
7. **Pairwise subject là gì?** Subject có thể khác giữa các RP/sector, không cho phép suy danh tính từ email.
8. **Lần đầu external identity chưa có thì làm gì?** Tạo local account mới/onboarding theo policy, không merge theo email.
9. **Hai login đồng thời cùng identity gây rủi ro gì?** Tạo trùng user, orphan hoặc race; cần unique/transaction/retry.
10. **Tại sao `UNIQUE(issuer,subject)` quan trọng?** Một external identity không được gắn hai local users kể cả khi race.
11. **Tại sao retry duplicate key ở ngoài transaction?** Transaction PostgreSQL sau lỗi có thể đã abort; cần rollback rồi đọc lại/retry.
12. **Để link provider mới cần chứng minh những gì?** Cả local authenticated session/consent và provider authentication mới, state-bound one-time intent.
13. **Ngoại identity đã link user khác thì sao?** Conflict; không di chuyển sang user hiện tại.
14. **Unlink tất cả login methods có an toàn không?** Có thể khóa user ngoài tài khoản; cần kiểm phương án recovery/reauth.
15. **`OidcUser.getIdToken()` được tạo trong test đã chứng minh chữ ký không?** Không; mock là fixture, cần test OIDC provider thực.
16. **Vì sao không để GET /me tự tạo user?** GET phải đọc, tránh tạo state do prefetch/crawler/monitoring.
17. **OAuth2 access token có phải stable user ID không?** Không; nó dùng để truy cập resource, có thể hết hạn/rotate.
18. **Provider `SCOPE_profile` có tự thành ROLE_USER/ADMIN trong app không?** Không; role/membership nội bộ cần policy riêng.
19. **Một người dùng có thể có hai external identities?** Có, nếu explicit link an toàn tạo nhiều bản ghi cùng local ID.
20. **Đổi issuer hoặc OIDC client có nên auto-merge bằng email?** Không; cần provider-supported migration hoặc chứng minh lại danh tính.

## 16. Checklist triển khai production

- [ ] Dùng local UUID làm khóa chính cho dữ liệu nghiệp vụ.
- [ ] Chỉ nhận OIDC `iss/sub` sau khi signature, issuer, audience, expiry và state/nonce/PKCE được framework/provider xác minh.
- [ ] Có issuer allowlist/canonicalization theo provider được review, giữ nguyên case của subject.
- [ ] Có bảng external identities riêng, unique `(issuer,subject)` và FK tới local user.
- [ ] Không auto-link/auto-merge dựa trên email, kể cả `email_verified=true`.
- [ ] Auto-provision first login (nếu được phép) trong transaction; kiểm local account status.
- [ ] Link existing account có local session, CSRF, fresh auth, state-bound link intent, callback xác minh, replay protection.
- [ ] Conflict khi identity đã gắn user khác; không tự chuyển local_user_id.
- [ ] Race login được xử lý bằng unique constraint/transaction/retry sau rollback.
- [ ] Không cấp role hoặc tenant membership theo email/scope chưa được policy phê duyệt.
- [ ] Metadata provider email/name được xem là có thể đổi; kiểm validation và quyền đổi contact email.
- [ ] Liên kết/gỡ liên kết có audit, reauth, thông báo và account recovery.
- [ ] Refresh/access tokens lưu riêng, bảo vệ secrets và không log/serialize ra API.
- [ ] Cache local mapping có chính sách invalidate khi user disabled/unlinked/roles đổi.
- [ ] Test cùng iss/sub email đổi, cùng email khác sub, cùng sub khác iss và pairwise migration.
- [ ] Test duplicate-link conflict, multiple concurrent logins, transaction rollback và no orphan user.
- [ ] Test callback state/nonce fail, provider mismatch, issuer mismatch, user locked và consent flow.
- [ ] Kiểm HTTPS, trusted forwarded headers, redirect URI, cookie/session và OAuth2 logout/revoke.
- [ ] Với production multi-node, dùng reactive repository thực thay in-memory maps.
- [ ] Không expose public endpoint nhận `issuer`/`subject` như bằng chứng đăng nhập.

## 17. Tài liệu chính thức

- OpenID Connect Core 1.0 — `sub`, `iss`, Claim Stability and Uniqueness, Section 5.7: https://openid.net/specs/openid-connect-core-1_0.html
- Spring Security — OAuth2 WebFlux: https://docs.spring.io/spring-security/reference/reactive/oauth2/
- Spring Security — Reactive OAuth2 Login Core: https://docs.spring.io/spring-security/reference/reactive/oauth2/login/core.html
- Spring Security — Reactive OAuth2 Login Advanced, OIDC User Service và ID Token Verification: https://docs.spring.io/spring-security/reference/reactive/oauth2/login/advanced.html
- Spring Security — Testing OAuth2/OIDC Login with WebTestClient: https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html
- Spring Security 6.3 API — `ServerHttpSecurity.OAuth2LoginSpec.authenticationSuccessHandler`: https://docs.spring.io/spring-security/site/docs/6.3.9/api/org/springframework/security/config/web/server/ServerHttpSecurity.OAuth2LoginSpec.html
- Spring Security 6.3 API — `RedirectServerAuthenticationSuccessHandler`: https://docs.spring.io/spring-security/site/docs/6.3.10/api/org/springframework/security/web/server/authentication/RedirectServerAuthenticationSuccessHandler.html
- Spring Boot 3.3 — OAuth2 Client Auto-configuration: https://docs.spring.io/spring-boot/3.3/reference/web/spring-security.html
- Google — OpenID Connect ID Token claims (`iss` và `sub`): https://developers.google.com/identity/openid-connect/openid-connect
- OWASP — Authentication Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html
- OWASP — Session Management Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html

**Ghi nhớ:** Trong OAuth2/OIDC login WebFlux, **định danh ngoài đã được xác thực = issuer + subject**, còn **định danh nghiệp vụ lâu dài = local user ID**. Email là thuộc tính hồ sơ, không phải bằng chứng để hợp nhất tài khoản. Hãy lưu liên kết trong bảng riêng có unique constraint và transaction, chỉ auto-provision user mới khi phù hợp; muốn liên kết vào user cũ phải thực hiện flow xác minh **cả local account lẫn provider mới** với state/CSRF/reauth. Spring Security giúp xác minh OIDC login, nhưng database và ứng dụng vẫn phải bảo đảm uniqueness, quyền nội bộ và conflict policy.
