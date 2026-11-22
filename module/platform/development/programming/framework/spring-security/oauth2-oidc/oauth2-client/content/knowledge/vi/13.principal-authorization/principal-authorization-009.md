# 13.9. Xử lý email thay đổi, email chưa xác minh và trùng tài khoản

## 1. Một email có phải là danh tính của người đăng nhập?

Giả sử ứng dụng **Employee Portal** sử dụng **Spring Security OAuth 2.0 Client** để đăng nhập qua OpenID Connect (OIDC). Người dùng vừa hoàn tất Authorization Code Flow, Spring Security đã xác minh ID Token và tạo principal `OidcUser`. Hồ sơ có những claim:

~~~json
{
  "iss": "https://login.example.test/realms/company",
  "sub": "employee-0042",
  "preferred_username": "minh.nguyen",
  "name": "Nguyễn Văn Minh",
  "email": "minh.nguyen@example.test",
  "email_verified": true
}
~~~

Một cách viết ứng dụng ban đầu có thể là:

~~~java
// Ý tưởng không nên dùng làm chính sách liên kết danh tính:
String email = oidcUser.getEmail();
User user = users.findByEmail(email)
    .orElseGet(() -> users.createWithEmail(email));
~~~

Cách làm này ngắn, nhưng đặt ra nhiều câu hỏi nguy hiểm:

- Người dùng **đổi email** trong hệ thống danh tính thì dữ liệu cũ của họ còn truy cập được không?
- IdP trả email nhưng `email_verified=false` thì có nên coi đó là chủ sở hữu địa chỉ email?
- Một email được cấp lại cho nhân viên mới có làm người mới truy cập được dữ liệu của người cũ không?
- Hai IdP khác nhau báo cùng một email thì có phải cùng người dùng?
- Đã có **tài khoản local** với email đó; đăng nhập SSO có nên tự động liên kết vào tài khoản local không?
- Hai yêu cầu đăng nhập đồng thời cùng thấy “chưa có user” thì có tạo hai tài khoản trùng nhau không?
- Nếu email đang dùng để cấp quyền quản trị hoặc xác định tenant, việc đổi email có làm thay đổi quyền mà không qua phê duyệt không?

**Nguyên tắc thiết kế:** đối với OIDC, định danh bên ngoài đáng tin cậy nhất để liên kết tài khoản trong phạm vi OP là **cặp (`iss`, `sub`)** được lấy từ danh tính đã xác thực. **Email là thuộc tính hồ sơ/liên lạc**; trạng thái `email_verified` có ý nghĩa về quá trình OP xác minh địa chỉ, nhưng **không biến email thành khóa liên kết tự động an toàn giữa mọi hệ thống**.

Bài học này tập trung vào **principal và phân quyền**, vì sai lầm trong việc liên kết email có thể dẫn trực tiếp đến **account takeover**, lộ dữ liệu hoặc cấp nhầm quyền. Ví dụ sử dụng Java 17+, Spring Boot 3, Spring Security 6 trên **Servlet/Spring MVC**, nhưng các quy tắc định danh cũng áp dụng khi dùng WebFlux. Mọi hostname và ID là dữ liệu minh họa.

## 2. Tách bốn lớp: authentication, identity, profile và authorization

Đừng gộp các khái niệm sau vào cùng một cột `email`:

| Lớp | Câu hỏi cần trả lời | Dữ liệu tiêu biểu |
|---|---|---|
| **Authentication** | Ai vừa được OP xác thực theo giao thức OIDC? | ID Token đã kiểm tra, issuer, subject, thời gian và ngữ cảnh xác thực |
| **External identity** | Danh tính đó liên kết với tài khoản nào của Portal? | `(issuer, subject)`, registration/provider, trạng thái liên kết |
| **Profile/contact** | Gọi người dùng thế nào và liên hệ tới đâu? | Email, email_verified, name, preferred_username, phone, picture |
| **Authorization** | Người đó có thể làm gì trong Portal? | Internal user ID, tenant membership, role, permissions, resource ownership |

Ví dụ:

~~~text
OIDC Provider
  iss = https://login.example.test/realms/company
  sub = employee-0042
  email = minh.nguyen@example.test
           │
           │ OIDC login thành công + chính sách liên kết
           ▼
ExternalIdentity
  (issuer, subject) -> internalUserId = 8e23...
           │
           ▼
AppUser
  id = 8e23...
  status = ACTIVE
  displayName = Nguyễn Văn Minh
           │
           +--> ContactEmail (có thể thay đổi, có trạng thái kiểm chứng)
           │
           +--> TenantMembership + Roles/Permissions
~~~

**Đăng nhập thành công ở IdP không có nghĩa được cấp mọi quyền của Portal.** Spring Security có thể coi principal đã authenticated, trong khi Portal vẫn cần kiểm tra danh tính đó **đã được provision/link** với internal user chưa, có đang active và có đủ quyền truy cập tài nguyên hay không.

## 3. Những claim OIDC liên quan trực tiếp

| Claim | Ý nghĩa thường dùng | Có nên làm khóa account? |
|---|---|---|
| `iss` | Issuer của OP phát hành ID Token | Dùng cùng `sub` để tạo namespace danh tính |
| `sub` | Subject identifier của người dùng tại issuer | **Có**, dưới namespace issuer |
| `email` | Địa chỉ email trong hồ sơ | **Không**, không làm khóa xác thực duy nhất |
| `email_verified` | OP cho biết đã có bước xác minh email theo cách OP quản lý | Không; là tín hiệu về email, không chứng minh hai account là một |
| `preferred_username` | Username thuận tiện cho con người | Không, có thể thay đổi hoặc trùng |
| `name` | Họ tên hiển thị | Không, không bảo đảm duy nhất |
| `picture` | URL ảnh hồ sơ | Không |
| `aud` | Đối tượng nhận ID Token | Dùng trong validation ID Token, không phải user key |
| `auth_time`, `acr`, `amr` | Ngữ cảnh/thời điểm/phương thức xác thực, khi được cấp | Có thể dùng trong chính sách xác thực nâng cao; không thay subject |

### 3.1. Email_verified không phải lúc nào cũng có

OIDC cho phép provider trả claim `email_verified` dạng Boolean khi có thông tin phù hợp. Ứng dụng phải phân biệt:

~~~text
email_verified = true
email_verified = false
email_verified = null / claim không có
~~~

**Không có claim** không tương đương `true`. Nếu nghiệp vụ cần email đã được xác minh thì cả `false` và `null` đều không đáp ứng điều kiện, trừ khi tổ chức có **một bằng chứng kiểm chứng khác** được ghi nhận có kiểm soát.

Việc yêu cầu scope `email` không bảo đảm OP luôn phát cả `email` và `email_verified`. Scope là yêu cầu; kết quả còn phụ thuộc OP, consent, cấu hình client và chính sách claim.

### 3.2. ID Token và UserInfo không giống dữ liệu do browser tự gửi

Trong OIDC login tiêu chuẩn, Spring Security xác minh ID Token theo các quy tắc cần thiết như issuer, audience, chữ ký và thời hạn. Sau đó có thể lấy thêm claim từ **UserInfo endpoint** khi provider và grant cho phép.

UserInfo trả về claim `sub` phải khớp subject của ID Token. Nếu không, không được dùng UserInfo đó làm hồ sơ của người đang đăng nhập.

Tránh cách thiết kế:

~~~http
POST /login/map-user HTTP/1.1
Content-Type: application/json

{"email":"admin@example.test","email_verified":true,"sub":"admin"}
~~~

rồi tin ngay dữ liệu này là bằng chứng sở hữu tài khoản. JSON do frontend gửi **không thay thế** OIDC principal được Spring Security tạo sau một login hợp lệ.

### 3.3. Thời điểm quan sát email_verified

`email_verified=true` phản ánh thông tin provider tuyên bố **tại thời điểm/cơ chế cấp claims**. Nó không tự động chứng minh rằng:

- Email không bao giờ đổi.
- Địa chỉ đó không thể được tái cấp cho người khác.
- Người dùng đang tiếp tục kiểm soát mailbox ở mọi thời điểm tương lai.
- Một account local hoặc account ở IdP khác có cùng email thuộc về đúng người đó.
- Người dùng còn tư cách nhân viên hay còn quyền quản trị.

Ứng dụng cần xác định rõ **mức độ tin cậy và thời hạn** của mỗi thuộc tính theo hợp đồng với OP và nhu cầu nghiệp vụ.

## 4. Vì sao nên nhận diện theo issuer + subject?

Trong OIDC, `sub` là một chuỗi định danh subject do OP cấp trong phạm vi issuer, không phải một username toàn cầu. Hai issuer có thể phát cùng `sub` cho hai người khác nhau:

~~~text
Identity A:
  iss = https://login.company.example.test
  sub = 12345

Identity B:
  iss = https://login.partner.example.test
  sub = 12345
~~~

Hai cặp `(iss, sub)` khác nhau, do đó **không được tự động coi là một người dùng**.

Tương tự, cùng email:

~~~text
Identity A:
  iss = https://login.company.example.test
  sub = employee-0042
  email = minh@example.test

Identity B:
  iss = https://login.partner.example.test
  sub = partner-9911
  email = minh@example.test
~~~

không đủ để kết luận cùng chủ tài khoản. Việc liên kết hai external identities vào một **internal user** phải trải qua quy trình được kiểm chứng.

### 4.1. Subject không phải mã nhân viên hoặc email

Nhiều OP coi `sub` là một **opaque identifier**. Ứng dụng nên:

- Lưu nguyên giá trị sau khi xác thực, không cắt, đổi chữ hoa/thường hoặc suy luận định dạng.
- Không tự ghép `sub` từ email, username hay mã nhân viên.
- Giữ issuer là danh tính OP được cấu hình tin cậy, không tự thay bằng hostname đơn giản hóa.
- Có kế hoạch migration nếu OP thay đổi issuer, tenant hoặc cách phát hành subject.

Một số OP phát **pairwise subject** khác nhau cho cùng người dùng giữa các client hoặc sector. Vì vậy, `(iss, sub)` nên được hiểu là **danh tính bên ngoài đã xác thực của client này** theo hợp đồng provider, không phải ID dùng chung giữa mọi ứng dụng.

### 4.2. Phân biệt principal name và khóa nghiệp vụ

Trong Spring Security, `Authentication.getName()` thường nhận giá trị từ `OidcUser.getName()`, mặc định hay là `sub`. Tuy nhiên `user-name-attribute` có thể được cấu hình để dùng `email` hoặc `preferred_username`.

Do đó, **không nên dựa vào `Authentication.getName()` như khóa nội bộ duy nhất mà không xem cấu hình principal**. Với OIDC, nên lấy explicit issuer và subject từ `OidcUser.getIdToken()`, rồi ánh xạ sang **internal user ID**.

## 5. Năm tình huống tài khoản thường gặp

### 5.1. Tình huống A: email đổi, subject giữ nguyên

~~~text
Lần đăng nhập thứ nhất:
  iss = https://login.example.test/realms/company
  sub = employee-0042
  email = minh.nguyen@example.test
  email_verified = true

Lần đăng nhập sau:
  iss = https://login.example.test/realms/company
  sub = employee-0042
  email = minh.tran@example.test
  email_verified = true
~~~

Đây thường vẫn là **một external identity** vì `(iss, sub)` không đổi. Portal nên tìm lại internal user đã liên kết theo cặp đó, tiếp tục giữ các đơn hàng, quyền và lịch sử hợp lệ. Việc cập nhật email liên lạc được thực hiện theo chính sách độc lập.

**Không tạo user mới chỉ vì email mới chưa xuất hiện trong database.** Cũng không nhất thiết chuyển ngay mọi thông báo nhạy cảm sang email mới nếu tổ chức cần quy trình xác minh email riêng.

### 5.2. Tình huống B: email chưa được xác minh

~~~json
{
  "sub": "employee-0042",
  "email": "ceo@example.test",
  "email_verified": false
}
~~~

Người dùng có thể đã đăng nhập OIDC hợp lệ theo `sub` của họ nhưng chưa chứng minh kiểm soát địa chỉ `ceo@example.test`. Không được:

- Tìm tài khoản CEO theo email rồi gắn external identity hiện tại vào đó.
- Cho phép gửi yêu cầu đặt lại tài khoản nhạy cảm chỉ vì email tự khai.
- Cấp vai trò quản trị hoặc cho vào tenant dựa trên email chưa xác minh.
- Ghi đè email liên lạc đã được xác minh của một tài khoản khác.

Có thể cho người dùng vào **trạng thái onboarding hạn chế**, yêu cầu hoàn tất xác minh email độc lập hoặc dùng chính sách tạo tài khoản không phụ thuộc email, tùy yêu cầu nghiệp vụ. Việc họ được phép làm gì trong lúc đó là **authorization policy**, không phải kết quả tất yếu của OIDC authentication.

### 5.3. Tình huống C: email bị tái cấp

~~~text
Năm trước:
  iss = https://login.example.test/realms/company
  sub = employee-old
  email = sales@example.test

Năm nay:
  iss = https://login.example.test/realms/company
  sub = employee-new
  email = sales@example.test
~~~

Ví dụ cho thấy **email có thể chuyển chủ**, đặc biệt với địa chỉ theo vai trò (shared mailbox), nhân viên nghỉ việc hoặc domain đổi chủ. Nếu Portal tra email rồi cấp toàn bộ tài liệu/đơn hàng cũ cho subject mới, đó là một hình thức **account takeover do liên kết sai**.

Đường xử lý an toàn là coi đây là **hai external identities khác nhau**. Subject mới cần được cấp/link account theo chính sách riêng; tài khoản cũ phải được vô hiệu hóa theo quy trình nghỉ việc, không tự chuyển quyền sở hữu dữ liệu chỉ vì mailbox giống nhau.

### 5.4. Tình huống D: hai account có cùng email

Một Portal có thể có:

~~~text
Internal user A:
  ID = user-100
  linked identity = (company, employee-0042)
  email = minh@example.test

Internal user B:
  ID = user-200
  linked identity = (partner, partner-9122)
  email = minh@example.test
~~~

Hai internal users có cùng email có thể là **hai tài khoản tách biệt hợp lệ** hoặc là một trường hợp trùng cần xem xét. Không nên tự động merge dữ liệu, roles hoặc tenant memberships để “dọn trùng”.

Email equality có thể dùng làm **tín hiệu gợi ý phát hiện trùng**, nhưng không là bằng chứng đủ để ghép danh tính.

### 5.5. Tình huống E: account local đã tồn tại trước khi bật SSO

Portal có account local với:

~~~text
user_id = user-100
email = minh@example.test
authentication = local password
~~~

Sau khi bật OIDC, một external identity đăng nhập có cùng email:

~~~text
iss = https://login.example.test/realms/company
sub = employee-0042
email = minh@example.test
email_verified = true
~~~

**Không nên tự động link chỉ dựa vào cùng email**, kể cả khi OP phát `email_verified=true`. Quy trình an toàn có thể yêu cầu người dùng **xác thực vào account local hiện có**, rồi bắt đầu liên kết IdP ở một luồng riêng, hoặc làm theo quy trình quản trị có xác minh chủ sở hữu.

## 6. Ma trận quyết định khi nhận hồ sơ mới từ OIDC

| Tình huống | Cặp `(iss, sub)` | Email | Hành vi khuyến nghị |
|---|---|---|---|
| Đăng nhập lại | Đã liên kết | Không đổi | Dùng internal user hiện có |
| Đổi email | Đã liên kết | Thay đổi | Giữ identity; cập nhật email theo chính sách |
| Email chưa verified | Đã liên kết | `email_verified=false/null` | Không dùng email làm chứng cứ mới; có thể hạn chế chức năng phụ thuộc email |
| Người dùng mới | Chưa liên kết | Chưa có ai dùng | Provision nếu chính sách cho phép hoặc yêu cầu duyệt |
| Email trùng account khác | Chưa liên kết | Có trùng | **Không tự link**; đi vào quy trình kiểm chứng |
| Email trùng nhiều account | Chưa liên kết | Nhiều kết quả | Không chọn account đầu tiên, không tự merge |
| Hai issuer có cùng sub | Hai cặp khác nhau | Có thể giống/khác | Xử lý thành hai external identities |
| Subject cũ bị vô hiệu | Đã liên kết nhưng account bị khóa | Bất kỳ | Từ chối quyền của Portal theo trạng thái account |
| Issuer mới sau migration | Chưa liên kết theo khóa mới | Giống email trước | Migration/link có kiểm soát, không suy từ email |

Ma trận là **chính sách ứng dụng được đề xuất**, không phải hành vi mặc định tự có của Spring Security. Framework xác thực OIDC; application quyết định provisioning, mapping internal user và cấp quyền.

## 7. Kiến trúc dữ liệu: email không phải primary key

Một thiết kế lưu trữ có thể phân chia:

~~~text
app_user
  id (UUID, primary key)
  status (ACTIVE / PENDING / SUSPENDED / DISABLED)
  display_name
  created_at

external_identity
  id
  user_id (FK -> app_user)
  issuer
  subject
  linked_at
  UNIQUE (issuer, subject)

contact_email
  id
  user_id (FK -> app_user)
  email_original
  email_lookup
  verification_status
  verified_source
  verified_at
  is_primary
  observed_at

tenant_membership
  user_id
  tenant_id
  role / permissions
~~~

Cách tách này giúp:

- Danh tính bên ngoài ổn định theo `issuer + subject`.
- Account nội bộ dùng **ID riêng** cho order, subscription, audit, ownership và quyền.
- Email trở thành **địa chỉ liên hệ** có thể đổi, hủy xác minh, thay thế hoặc có nhiều bản ghi lịch sử.
- Có thể thêm nhiều external identities cho một internal user **sau khi thực hiện account linking an toàn**.
- Tenant membership và roles không bị thay đổi tự động khi email đổi.

### 7.1. SQL ví dụ

Mô hình sau dùng cú pháp gần PostgreSQL để minh họa nguyên tắc; tên cột/kiểu dữ liệu cần điều chỉnh theo database của dự án:

~~~sql
CREATE TABLE app_user (
    id UUID PRIMARY KEY,
    status VARCHAR(32) NOT NULL,
    display_name VARCHAR(255),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE external_identity (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES app_user(id),
    issuer VARCHAR(512) NOT NULL,
    subject VARCHAR(512) NOT NULL,
    linked_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_external_identity UNIQUE (issuer, subject)
);

CREATE TABLE contact_email (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES app_user(id),
    email_original VARCHAR(320) NOT NULL,
    email_lookup VARCHAR(320) NOT NULL,
    verification_status VARCHAR(24) NOT NULL,
    verified_source VARCHAR(128),
    verified_at TIMESTAMPTZ,
    is_primary BOOLEAN NOT NULL DEFAULT FALSE,
    observed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_contact_email_lookup
    ON contact_email (email_lookup);

CREATE INDEX idx_contact_email_user
    ON contact_email (user_id);
~~~

**Tại sao không đặt `UNIQUE(email_lookup)` toàn hệ thống?** Email có thể tồn tại trên nhiều account hoặc một account có nhiều contact emails tùy mô hình. Một unique constraint email toàn hệ thống dễ khiến chương trình **đồng nhất identity sai** hoặc tạo lỗi provisioning không có đường giải quyết. Nếu sản phẩm có quy tắc **mỗi email đã xác minh chỉ được gắn với một account trong một tenant**, hãy mô hình hóa constraint theo **tenant + loại email + trạng thái**, với quy trình xử lý collision rõ ràng; không coi constraint đó là bằng chứng xác thực của người đăng nhập.

Ngược lại, ràng buộc `UNIQUE(issuer, subject)` là điều quan trọng: **một external identity không được đồng thời liên kết với hai internal accounts**. Khi link lại, cần một giao dịch được ủy quyền và ghi nhận audit, không chỉ cập nhật một hàng tùy ý.

### 7.2. Không nên xóa lịch sử thay đổi email ngay lập tức

Trong một số hệ thống, lưu **bản ghi audit đã giới hạn truy cập** về thay đổi email giúp điều tra tranh chấp:

~~~text
2026-01: user-100, email = minh.nguyen@example.test, verified=true
2026-06: user-100, email = minh.tran@example.test, verified=true
~~~

Tuy nhiên email là **dữ liệu cá nhân**. Việc lưu lịch sử phải theo mục đích, thời hạn giữ dữ liệu và quyền truy cập phù hợp; không ghi email, ID Token hay toàn bộ UserInfo vào log vô thời hạn.

## 8. Thiết kế quy trình xử lý claim email từ OIDC

Một pipeline an toàn sau khi Spring Security hoàn tất xác minh OIDC có thể là:

~~~mermaid
flowchart TD
    A["Spring Security xác thực OIDC, tạo OidcUser"] --> B["Lấy (iss, sub) từ ID Token đã kiểm tra"]
    B --> C{"External identity đã liên kết?"}
    C -->|Có| D["Tải app_user theo internal ID"]
    C -->|Chưa| E{"Cho phép auto-provision không?"}
    E -->|Không| F["Chuyển sang invitation / linking / approval"]
    E -->|Có| G["Tạo app_user mới qua transaction và unique (iss,sub)"]
    G --> D
    D --> H{"User còn ACTIVE?"}
    H -->|Không| I["Chặn truy cập tài nguyên hoặc áp dụng quy trình khôi phục"]
    H -->|Có| J["Quan sát email và email_verified"]
    J --> K{"Email đổi / chưa verified / trùng?"}
    K -->|Không| L["Cập nhật thông tin liên hệ theo chính sách"]
    K -->|Có| M["Đánh dấu pending hoặc review, KHÔNG tự merge"]
    L --> N["Áp dụng tenant membership và permissions"]
    M --> N
    N --> O["Trả quyền truy cập theo chính sách ứng dụng"]
~~~

Những điểm quan trọng:

1. **Luôn tra external identity trước email.** Nếu đã có cặp issuer+subject, người dùng đã có account tương ứng kể cả email thay đổi.
2. **Không tự động link danh tính chưa biết với một account khác chỉ vì email giống.**
3. **Auto-provision là chính sách sản phẩm**, có thể bật hoặc tắt; không phải hệ quả bắt buộc của OIDC login.
4. **Trạng thái account và permissions** được kiểm tra độc lập với kết quả `email_verified`.
5. **Collision** cần một quy trình có thể giải quyết mà không tiết lộ chi tiết account khác cho người dùng chưa được cấp quyền.

### 8.1. Giả mã quyết định

~~~text
identityKey = (validatedIdToken.iss, validatedIdToken.sub)
linked = externalIdentityRepository.find(identityKey)

if linked exists:
    user = userRepository.load(linked.internalUserId)
    if user disabled:
        deny access
    observeEmailClaims(user, email, emailVerified)
    authorize based on internal user, tenant and permissions
else:
    if autoProvisionAllowedForThisTrustedIssuerAndContext:
        create new internal user + identity mapping atomically
        do not attach it to a different existing user by matching email
    else:
        require invitation / explicit account linking / admin approval
~~~

**Lưu ý:** một issuer được tin cậy để xác thực không đồng nghĩa tự động được tin cậy để **cấp tư cách thành viên, chức vụ hay quyền admin**. Auto-provision cần điều kiện riêng như invitation, tenant binding hoặc danh sách nhân sự đã được quản lý.

## 9. Cấu hình Spring Security OIDC Client cơ bản

Ví dụ dùng provider ID và registration ID `company`:

~~~yaml
# application.yml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
        provider:
          company:
            issuer-uri: ${OIDC_ISSUER_URI}
            user-name-attribute: sub
~~~

`user-name-attribute: sub` chọn subject làm principal name theo cấu hình provider; **nó không tự tạo bảng external identity hoặc chính sách phân quyền**. Dùng `iss+sub` trong service ứng dụng mới là bước liên kết danh tính.

Biến `OIDC_CLIENT_SECRET` phải được cấp an toàn tại runtime. Không ghi secret thật vào Git, email, log hoặc browser. ID Token và các claim trong bài phải đến từ luồng Spring Security đã xác thực, không đọc JSON do frontend tự cung cấp.

Dependencies Servlet:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Ví dụ SecurityFilterChain:

~~~java
package com.example.portal.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain portalSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .build();
    }
}
~~~

**Quan trọng:** cấu hình `anyRequest().authenticated()` chỉ đòi người dùng đã được IdP xác thực; nó **không đủ** để bảo đảm người dùng có internal account đang active hoặc quyền truy cập tài nguyên của Portal. Các API nghiệp vụ phải kiểm tra provisioning/mapping/authorization như những mục tiếp theo. Nếu Portal cần chặn user chưa provision ngay trong bước login, cần một integration point riêng và chính sách xử lý lỗi/onboarding rõ ràng.

## 10. Lấy issuer, subject và email từ OidcUser an toàn

Trong Servlet, sau một OIDC login thành công:

~~~java
package com.example.portal.identity;

import org.springframework.security.oauth2.core.oidc.user.OidcUser;

public record OidcIdentityKey(String issuer, String subject) {

    public static OidcIdentityKey from(OidcUser principal) {
        String issuer =
            principal.getIdToken().getIssuer().toString();
        String subject =
            principal.getIdToken().getSubject();
        return new OidcIdentityKey(issuer, subject);
    }
}
~~~

Và phân biệt email cùng trạng thái verification:

~~~java
package com.example.portal.identity;

import org.springframework.security.oauth2.core.oidc.user.OidcUser;

public record ObservedEmail(
    String value,
    Boolean verified
) {
    public static ObservedEmail from(OidcUser principal) {
        return new ObservedEmail(
            principal.getEmail(),
            principal.getEmailVerified()
        );
    }

    public boolean isVerified() {
        return value != null
            && !value.isBlank()
            && Boolean.TRUE.equals(verified);
    }
}
~~~

Trong Java record trên, ba trường hợp được phân biệt đúng:

~~~java
new ObservedEmail("minh@example.test", true).isVerified();  // true
new ObservedEmail("minh@example.test", false).isVerified(); // false
new ObservedEmail("minh@example.test", null).isVerified();  // false
~~~

**Không tự suy luận** `verified=true` nếu email được trả trong UserInfo. Không sử dụng `Boolean.parseBoolean` trên một dữ liệu tùy ý rồi biến nó thành nguồn tin cậy; hãy dùng principal đã qua validation và kiểm soát hợp đồng claim với OP.

### 10.1. Khi claim không có, UI nên làm gì?

Có thể hiển thị:

~~~text
Địa chỉ liên hệ: Chưa được cung cấp
Trạng thái email: Chưa xác minh
Hành động: Xác minh địa chỉ email
~~~

Tránh hiển thị “Email đã xác minh” chỉ vì tài khoản OIDC vừa login thành công. OIDC xác thực **danh tính tại OP**, không phải đảm bảo mọi claim hồ sơ đều đúng chuẩn nghiệp vụ của Portal.

## 11. Ánh xạ OidcUser sang internal user ID

Một service nghiệp vụ nên **lấy internal user qua issuer+subject**, không qua email:

~~~java
package com.example.portal.identity;

import java.util.UUID;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class IdentityMappingService {

    private final ExternalIdentityRepository identities;
    private final AppUserRepository users;

    public IdentityMappingService(
        ExternalIdentityRepository identities,
        AppUserRepository users
    ) {
        this.identities = identities;
        this.users = users;
    }

    @Transactional(readOnly = true)
    public UUID requireActiveUserId(OidcUser principal) {
        OidcIdentityKey key = OidcIdentityKey.from(principal);

        UUID userId = identities
            .findUserId(key.issuer(), key.subject())
            .orElseThrow(() ->
                new AccountNotLinkedException());

        if (!users.isActive(userId)) {
            throw new AccountDisabledException();
        }

        return userId;
    }
}
~~~

`ExternalIdentityRepository`, `AppUserRepository`, `AccountNotLinkedException` và `AccountDisabledException` là các abstraction/domain types **do ứng dụng định nghĩa**, không phải class có sẵn của Spring Security. Code minh họa luồng mapping, không phải ví dụ JPA hoàn chỉnh.

**Vì sao không fallback sang email khi không tìm thấy identity?**

~~~java
// Không nên:
return identities.findUserId(issuer, subject)
    .orElseGet(() -> users.findByEmail(principal.getEmail()).getId());
~~~

Nếu subject mới chỉ tình cờ có email của người khác, fallback đó **trao quyền truy cập account cũ cho danh tính mới**. Khi chưa có mapping, cần đi qua invitation, provisioning hoặc explicit account linking theo chính sách.

### 11.1. API nghiệp vụ phải dùng internal user ID

Một controller minh họa:

~~~java
package com.example.portal.web;

import java.util.UUID;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import com.example.portal.identity.IdentityMappingService;

@RestController
public class AccountController {

    private final IdentityMappingService mapping;

    public AccountController(IdentityMappingService mapping) {
        this.mapping = mapping;
    }

    @GetMapping("/api/me/id")
    public UUID currentUserId(
        @AuthenticationPrincipal OidcUser principal
    ) {
        return mapping.requireActiveUserId(principal);
    }
}
~~~

Đây là endpoint **chỉ trả internal user ID** để minh họa mapping; việc trả ID cho frontend không làm nó trở thành một secret và không tự thay thế authorization trên các endpoint khác.

Với `/api/orders/{id}`, ngoài việc tìm internal user, ứng dụng cần kiểm tra user có quyền với **order ID cụ thể** hay không. Đừng chỉ kiểm tra `.authenticated()` hoặc so email trong URL với email của principal.

## 12. Xử lý account chưa liên kết ngay trong bước OIDC Login

Nếu sản phẩm không cho truy cập Portal trước khi có internal account, có thể sử dụng một **OidcUserService tùy chỉnh** trong Servlet OAuth2 Login để kiểm tra mapping trước khi coi đăng nhập hoàn tất.

Ví dụ logic **chỉ chấp nhận external identity đã được liên kết**:

~~~java
package com.example.portal.config;

import java.util.HashSet;
import java.util.Set;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.client.oidc.userinfo.OidcUserRequest;
import org.springframework.security.oauth2.client.oidc.userinfo.OidcUserService;
import org.springframework.security.oauth2.client.userinfo.OAuth2UserService;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.oidc.user.DefaultOidcUser;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import com.example.portal.identity.IdentityMappingService;

@Configuration
public class PortalOidcUserConfig {

    @Bean
    OAuth2UserService<OidcUserRequest, OidcUser> portalOidcUserService(
        IdentityMappingService mapping
    ) {
        OidcUserService delegate = new OidcUserService();

        return request -> {
            OidcUser oidcUser = delegate.loadUser(request);

            // Không lookup bằng email: issuer + subject được lấy từ ID Token.
            try {
                mapping.requireActiveUserId(oidcUser);
            } catch (RuntimeException e) {
                // Không rò rỉ email/account của người khác qua lỗi login.
                throw new OAuth2AuthenticationException(
                    new OAuth2Error("portal_account_not_available"),
                    "Portal account not available"
                );
            }

            Set<GrantedAuthority> authorities =
                new HashSet<>(oidcUser.getAuthorities());
            authorities.add(new SimpleGrantedAuthority("PORTAL_USER"));

            return new DefaultOidcUser(
                authorities,
                oidcUser.getIdToken(),
                oidcUser.getUserInfo(),
                "sub"
            );
        };
    }
}
~~~

Cấu hình SecurityFilterChain kết nối:

~~~java
@Bean
SecurityFilterChain portalSecurity(
    HttpSecurity http,
    OAuth2UserService<OidcUserRequest, OidcUser> portalOidcUserService
) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/", "/error").permitAll()
            .anyRequest().hasAuthority("PORTAL_USER"))
        .oauth2Login(login -> login
            .userInfoEndpoint(userInfo -> userInfo
                .oidcUserService(portalOidcUserService)))
        .build();
}
~~~

Đây là **một phương án thay thế** SecurityFilterChain ở mục 9, không phải chain thứ hai cần giữ nguyên trong cùng dự án. Các import của đoạn DSL là những class đã xuất hiện trong ví dụ SecurityFilterChain trước đó cộng với `OAuth2UserService`, `OidcUserRequest` và `OidcUser`.

**Lưu ý quan trọng:**

- Ví dụ chỉ cấp `PORTAL_USER` khi mapping tồn tại và internal account active; nó **không** cấp vai trò admin hay tenant permissions.
- Mọi domain exception bị chuyển thành lỗi login chung trong minh họa. Ở production, chỉ nên bắt **những exception nghiệp vụ dự kiến**; lỗi database/mạng cần được xử lý, giám sát và báo vận hành phù hợp thay vì im lặng coi là account chưa được cấp. Không sử dụng broad catch để che các lỗi hạ tầng.
- Việc thay principal bằng `DefaultOidcUser` phải bảo toàn ID Token, UserInfo và authorities gốc cần thiết. Không tự tin bất kỳ email mới xuất hiện mà thêm authority quản trị.
- Tùy mô hình sản phẩm, người dùng chưa linked có thể cần một **luồng onboarding riêng** thay vì bị từ chối login. Khi đó thiết kế security boundary phải bảo đảm họ chỉ truy cập trang onboarding, không truy cập API nghiệp vụ trước khi liên kết.

## 13. Auto-provision người dùng mới: điều kiện và transaction

Không phải sản phẩm nào cũng cần mời/duyệt trước mọi login. Nếu Portal được thiết kế auto-provision từ một OP doanh nghiệp đã được quản lý, vẫn cần các kiểm soát:

1. OP/issuer phải nằm trong **danh sách tin cậy đã cấu hình**, không chọn động từ request không tin cậy.
2. Phải có quy tắc **được phép tạo account** (ví dụ tenant invitation, danh sách nhân viên hoặc entitlement từ nguồn được kiểm soát), không chỉ email domain.
3. Tạo internal user và external identity trong **cùng transaction**.
4. Database ràng buộc **UNIQUE(issuer, subject)** để xử lý đua tranh.
5. Nếu email trùng, **không auto merge** với internal user cũ.
6. Ghi audit sự kiện tạo account và nguồn chính sách, không lưu token/secret trong audit.
7. Cấp quyền tối thiểu ban đầu; quyền nâng cao phải theo quy trình kiểm soát.

### 13.1. Race condition với hai callback đồng thời

Giả sử browser gửi hai authorization flow sát nhau hoặc có retry tại tầng ứng dụng:

~~~text
Request A: find(iss,sub) -> chưa tồn tại
Request B: find(iss,sub) -> chưa tồn tại
Request A: tạo app_user A + external_identity
Request B: tạo app_user B + external_identity
~~~

Nếu chỉ dựa vào `findBy...` trước khi insert, có thể tạo hai user. Cần **unique constraint ở database** và transaction:

~~~text
transaction:
  check/find external identity
  create app_user (nếu policy cho phép)
  insert external_identity(issuer, subject, user_id)
commit
~~~

Khi request thứ hai gặp unique constraint violation, rollback transaction đó rồi **đọc lại identity đã được tạo hợp lệ**, không ghi đè mapping bằng email hoặc tự động merge hai users.

Trong production, retry cần phân loại lỗi cẩn thận; việc cạnh tranh unique constraint không có nghĩa mọi lỗi persistence có thể retry vô hạn.

### 13.2. Disabled user và auto-provision

Một external identity đã được liên kết tới user ở trạng thái **DISABLED/SUSPENDED** không nên được tự tạo lại thành user mới chỉ vì bước đăng nhập không tìm thấy user active. Truy vấn cần phân biệt:

~~~text
linked identity không tồn tại
linked identity tồn tại nhưng account disabled
linked identity đã bị thu hồi liên kết
~~~

Các trạng thái này có hậu quả bảo mật khác nhau. Đặc biệt, **disabled** phải chặn quyền Portal ngay cả khi OP vẫn tiếp tục xác thực người dùng.

## 14. Email đổi: cập nhật hồ sơ, không đổi quyền sở hữu dữ liệu

Một trình tự điển hình sau khi identity đã liên kết:

~~~mermaid
sequenceDiagram
    participant OP as OIDC Provider
    participant Portal as Employee Portal
    participant Identity as Identity Service
    participant DB as User Database

    OP-->>Portal: OIDC principal với iss, sub, email mới
    Portal->>Identity: Resolve (iss, sub)
    Identity->>DB: Tra external_identity
    DB-->>Identity: internalUserId = user-100
    Identity->>DB: Quan sát claim email và verification
    Identity->>Identity: Áp dụng chính sách contact email
    Identity-->>Portal: user-100 và trạng thái email
    Portal->>DB: Kiểm tra permissions của user-100
    DB-->>Portal: Membership/permissions
    Portal-->>Portal: Tiếp tục phiên với cùng internalUserId
~~~

Quy tắc vận hành có thể là:

- Nếu email mới đã verified từ một OP đáng tin và chính sách cho phép đồng bộ, cập nhật **contact email** của **cùng internal user**.
- Nếu email mới chưa verified, giữ email liên lạc đã xác minh trước đó và đánh dấu email mới là **pending verification**.
- Nếu email mới đang xuất hiện ở account khác, gắn cờ **collision**; không merge hay chuyển quyền sở hữu.
- Nếu claim email biến mất, không tự xóa internal user hoặc external identity. Có thể giữ thông tin liên hệ cũ với trạng thái/nguồn xác minh rõ ràng.
- Nếu business process dùng email làm username để đăng nhập local, việc đổi cần xử lý riêng tại local authentication layer.

### 14.1. Khác biệt “được OP xác minh” và “được Portal xác minh”

Portal có thể có một quy trình tự gửi email confirmation để kiểm tra mailbox. Khi đó cần lưu **nguồn xác minh**:

~~~text
email = minh@example.test
status = VERIFIED
source = OIDC_PROVIDER_COMPANY
observed_at = ...
verified_at = ...
~~~

hoặc:

~~~text
email = minh@example.test
status = VERIFIED
source = PORTAL_EMAIL_CHALLENGE
verified_at = ...
~~~

Hai nguồn có thể có mức độ tin cậy khác nhau theo nghiệp vụ. Không nên gộp mọi trường hợp vào một Boolean `isEmailVerified` mà không thể trả lời **ai xác minh, xác minh khi nào, còn hiệu lực không và có thể bị thu hồi không**.

## 15. Email chưa verified: giới hạn gì và xác minh như thế nào?

Việc `email_verified=false` không nhất thiết có nghĩa OIDC login vô hiệu: **subject đã được xác thực** vẫn có thể hợp lệ. Nhưng email đó **chưa đủ độ tin cậy** cho các chức năng phụ thuộc quyền kiểm soát mailbox.

Ví dụ ma trận:

| Chức năng | Nếu OIDC login hợp lệ, email chưa verified |
|---|---|
| Hiển thị thông tin cơ bản của chính mình | Có thể cho phép theo quyền tài khoản |
| Xem đơn hàng thuộc internal user đã liên kết | Cần kiểm tra quyền/ownership; không dựa trên email |
| Đổi email liên lạc chính | Có thể yêu cầu xác minh địa chỉ mới |
| Nhận hóa đơn/thông báo chứa dữ liệu nhạy cảm | Cân nhắc chặn đến khi email mới được xác minh |
| Link với account local theo email | **Không tự động cho phép** |
| Cấp role admin vì email giống địa chỉ quản trị | **Không cho phép** |
| Tự động gia nhập tenant bằng domain email | **Không đủ bằng chứng** |

### 15.1. Luồng verify email do Portal thực hiện

Khi sản phẩm quyết định tự kiểm tra mailbox, có thể triển khai:

1. Người dùng **đã xác thực** đề nghị thêm/thay contact email trong account nội bộ của chính họ.
2. Server tạo **token ngẫu nhiên, một lần**, gắn với internal user ID, email đích, mục đích và thời hạn.
3. Server gửi link/token confirmation tới email đó qua kênh phù hợp.
4. Khi người dùng hoàn tất, server xác minh token và ràng buộc chính xác **user + email + purpose**.
5. Cập nhật contact email đã verified trong transaction; vô hiệu token cũ.
6. Nếu email đã thuộc một account khác, không âm thầm chuyển hoặc merge; đưa vào quy trình giải quyết collision.

Không dùng **JWT ID Token** hoặc **OAuth access token** như mã xác minh email tự chế. Token xác minh email là một credential nghiệp vụ riêng, nên lưu hash của token ngẫu nhiên khi phù hợp và không để giá trị thật nằm trong log.

### 15.2. Không rò rỉ thông tin người khác qua thông báo lỗi

Thay vì:

~~~text
Email này thuộc về người dùng tên Nguyễn Văn Minh,
account ID=user-100 và đã có role PORTAL_ADMIN.
~~~

hãy dùng phản hồi chung:

~~~text
Không thể hoàn tất liên kết địa chỉ này.
Vui lòng dùng quy trình xác minh hoặc liên hệ bộ phận hỗ trợ.
~~~

Các chi tiết về account trùng và bằng chứng truy cập chỉ nên hiển thị cho tác nhân hỗ trợ **đã được phân quyền**.

## 16. Trùng tài khoản: phát hiện không đồng nghĩa tự merge

Có thể phát hiện collision khi một external identity mới xuất hiện với email trùng:

~~~text
New external identity:
  iss = https://login.company.example.test
  sub = employee-8888
  email = shared@example.test
  email_verified = true

Existing internal user:
  id = user-100
  linked = (https://login.legacy.example.test, legacy-042)
  email = shared@example.test
~~~

Hệ thống có thể ghi nhận:

~~~text
POTENTIAL_DUPLICATE_EMAIL
  candidate_external_identity = (issuer, subject)
  matching_contact_email = shared@example.test
  resolution = REVIEW_REQUIRED
~~~

Nhưng **không** tự cập nhật:

~~~sql
-- Ví dụ thao tác nguy hiểm: không thực hiện chỉ dựa trên email trùng.
UPDATE external_identity
SET user_id = 'user-100'
WHERE issuer = 'https://login.company.example.test'
  AND subject = 'employee-8888';
~~~

Nếu làm vậy, external identity mới có thể được trao ngay **toàn bộ dữ liệu/role của account cũ**.

### 16.1. Chính sách giải quyết collision

Có thể phân loại:

- **Hai identities thực sự cùng một người**: cần quy trình link có bằng chứng.
- **Hai người khác nhau dùng shared mailbox**: có thể giữ hai internal users và cấm dùng email đó làm chứng cứ sở hữu account.
- **Email bị tái cấp**: không chuyển quyền sở hữu tài khoản cũ.
- **Dữ liệu import sai**: cần sửa dữ liệu có audit, không merge tự động.
- **Account local và account SSO cùng email**: yêu cầu xác thực cả hai account hoặc quy trình hỗ trợ được ủy quyền.
- **Tài khoản bị chiếm đoạt/nghi ngờ gian lận**: tạm ngừng linking, đánh giá rủi ro và kiểm tra phiên hiện tại.

Không có một câu lệnh SQL “merge by email” an toàn cho tất cả các tình huống trên.

## 17. Account linking an toàn

Nếu người dùng thực sự sở hữu hai external identities và muốn dùng chung một internal account, cần **bằng chứng kiểm soát cả hai phía** hoặc quy trình quản trị tương đương.

Ví dụ một luồng explicit linking:

~~~mermaid
sequenceDiagram
    actor U as Người dùng
    participant Portal as Portal
    participant OP1 as Provider A
    participant OP2 as Provider B
    participant DB as Identity Database

    U->>Portal: Đăng nhập bằng Provider A
    Portal->>OP1: OIDC authorization flow
    OP1-->>Portal: Danh tính A hợp lệ
    Portal->>DB: A -> internal user-100
    U->>Portal: Yêu cầu liên kết Provider B
    Portal->>Portal: Kiểm tra account/session và chính sách reauthentication
    Portal->>OP2: OIDC flow để chứng minh kiểm soát identity B
    OP2-->>Portal: Danh tính B hợp lệ
    Portal->>DB: Kiểm tra B chưa link sang user khác
    Portal->>DB: Transaction link B -> user-100 + audit
    Portal-->>U: Liên kết hoàn tất
~~~

Các kiểm soát cần có:

1. Người dùng phải có **phiên Portal hợp lệ** cho internal user đích; có thể yêu cầu **reauthentication gần thời điểm liên kết**.
2. External identity mới phải được chứng minh qua **một OIDC login riêng** đối với IdP mới, với state/nonce/PKCE và redirect URI được xác minh.
3. Không chấp nhận `issuer` và `sub` do browser nhập tay để “link account”.
4. Từ chối hoặc chuyển xét duyệt nếu identity mới **đã liên kết với internal user khác**.
5. Transaction phải bảo vệ `UNIQUE(issuer, subject)` và ghi audit liên kết.
6. Giữ nguyên quyền của internal user đích; không cộng gộp role của hai account chỉ vì thao tác link.
7. Nếu cho phép unlink, bảo đảm người dùng vẫn có cách đăng nhập/khôi phục an toàn; tránh khóa account vĩnh viễn ngoài ý muốn.

**Cảnh báo về hai luồng đăng nhập:** OAuth2 login thông thường có thể thay Authentication hiện tại khi callback hoàn tất. Một tính năng account linking cần giữ bằng chứng **internal user đích đã xác thực** qua state/session hoặc một giao dịch linking riêng có tính toàn vẹn. Không triển khai bằng cách “sau callback, lấy email của hai principal rồi merge”; phải thiết kế ranh giới giữa login chính và proof-of-possession cho identity thứ hai.

### 17.1. Link account bằng email verification có đủ không?

Việc sở hữu mailbox có thể là **một tín hiệu bổ sung**, nhưng thường không chứng minh một người có quyền sở hữu account khác đã có lịch sử/roles nhạy cảm. Nếu sản phẩm có quy trình **email-based account recovery/linking**, cần đánh giá khả năng tái cấp email, mức đảm bảo của OP, thời điểm kiểm chứng, MFA/step-up, cảnh báo và chính sách chống chiếm đoạt. Với tài khoản đặc quyền, nên yêu cầu kiểm tra mạnh hơn một email confirmation.

## 18. Email domain và phân quyền tenant

Một lỗi quen thuộc:

~~~java
// Không dùng làm điều kiện duy nhất để cấp quyền truy cập tenant:
if (user.getEmail().endsWith("@example.test")) {
    grantAuthority("TENANT_ADMIN");
}
~~~

Các vấn đề:

- Email có thể chưa verified.
- Domain email có thể thuộc shared mailbox, alias hoặc tài khoản đối tác.
- Người dùng có thể đổi email trong khi tenant membership chưa thay.
- Chưa chắc mọi nhân viên của tổ chức đều được cấp quyền Portal.
- Chuỗi so sánh đơn giản không thay thế được chính sách tenant/role của doanh nghiệp.

Một thiết kế phù hợp hơn:

~~~text
OIDC verified principal
   -> (issuer, subject)
   -> internal user ID
   -> tenant memberships do Portal quản lý
   -> roles và permissions của user trong tenant
   -> authorization theo resource
~~~

Email domain có thể là **gợi ý để chọn tenant trong onboarding** nếu chính sách cho phép, nhưng **không tự động cấp admin hoặc quyền dữ liệu**.

### 18.1. Phân quyền phải dựa trên nguồn đáng tin cậy

Nếu Portal dựa vào nhóm/role từ IdP, cần ánh xạ claim/authority theo nguồn đã được xác minh, audience/issuer được tin cậy và chính sách role mapping rõ ràng. Không cho client gửi `{"role":"ADMIN"}` qua frontend rồi coi đó là authority.

Ví dụ kiểm soát quyền tại application:

~~~java
http.authorizeHttpRequests(authorize -> authorize
    .requestMatchers("/admin/**").hasAuthority("PORTAL_ADMIN")
    .anyRequest().authenticated()
);
~~~

Điều kiện `PORTAL_ADMIN` phải được cấp qua quy trình authorization riêng, không đơn giản là email hoặc preferred_username bằng một giá trị cụ thể.

Ngay cả khi route chỉ đòi `PORTAL_USER`, tầng service vẫn cần kiểm tra **ownership** hoặc **tenant membership** đối với từng bản ghi nghiệp vụ.

## 19. Chuẩn hóa email để tìm kiếm: cần thận trọng

Email thường được tìm kiếm không phân biệt hoa/thường, nhưng **không thể áp dụng một thuật toán tùy tiện cho mọi domain/mailbox**.

Ví dụ:

~~~text
MINH.NGUYEN@EXAMPLE.TEST
minh.nguyen@example.test
~~~

Một chính sách lookup có thể coi hai cách viết là tương đương theo hợp đồng của tổ chức. Nhưng những biến đổi như:

- Xóa dấu chấm trong phần local.
- Bỏ suffix sau dấu `+`.
- Loại bỏ ký tự không phải ASCII.
- Tự động thay Unicode hoặc chuẩn hóa toàn bộ local-part.

không đúng cho mọi nhà cung cấp email.

Khuyến nghị:

1. **Lưu email gốc** để hiển thị và điều tra theo phạm vi được phép.
2. Có **email_lookup** đã normalize theo **chính sách rõ ràng**, tối thiểu xử lý khoảng trắng nhập liệu và domain phù hợp.
3. Không dùng normalized email làm external identity key.
4. Khi phát hiện trùng, xem đó là **candidate collision**, không thực hiện auto-link.
5. Đảm bảo các phép so sánh Unicode/IDN/case folding phù hợp với provider và hạ tầng thực tế.

Ví dụ `alice+finance@example.test` và `alice@example.test` **có thể** cùng mailbox với một số nhà cung cấp, nhưng không thể giả định như vậy với mọi email domain. Nếu Portal tự loại suffix plus để merge account, hệ thống có thể ghép nhầm tài khoản.

## 20. Các trường hợp nâng cao

### 20.1. IdP thay issuer hoặc tenant

Nếu OP di chuyển từ:

~~~text
https://login.old.example.test/realms/company
~~~

sang:

~~~text
https://login.new.example.test/realms/company
~~~

thì cặp `(iss, sub)` cũng thay đổi dù `sub` có vẻ giống. **Không tự nối hai danh tính bằng email**.

Quy trình migration cần nguồn mapping đáng tin cậy, thời hạn chuyển đổi, kiểm tra trên tập người dùng, rollback và audit. Nếu có dữ liệu cũ đã gắn sai theo email, cần remediation cụ thể thay vì áp dụng quy tắc merge rộng hơn.

### 20.2. Pairwise subject thay đổi theo client

Một OP có thể phát `sub` khác nhau cho cùng con người khi Portal đổi client registration/sector configuration. Sự kiện đó cần kế hoạch migration hoặc linking đã được kiểm chứng; không dùng preferred_username/email để “đoán” tất cả subject cũ.

### 20.3. Người dùng bị xóa hoặc khóa ở IdP

Khi OP không cho đăng nhập, Portal không nên dựa trên email còn lưu trong database để tiếp tục tạo danh tính. Với session Portal còn hiệu lực, chính sách revocation/session expiration và kiểm tra account trạng thái ACTIVE cần được thiết kế theo rủi ro.

**Một phiên OIDC login trước đó không tự bảo đảm nhân viên còn quyền truy cập tại thời điểm hiện tại.** Nếu nghiệp vụ yêu cầu cập nhật quyền ngay, cần cơ chế provisioning/deprovisioning và kiểm tra thời hạn session phù hợp.

### 20.4. Email bị loại khỏi UserInfo ở lần đăng nhập sau

Nếu OP không còn trả email do scope hoặc chính sách mới, Portal không nên:

- Gán email thành chuỗi rỗng rồi xóa dữ liệu liên lạc một cách bất ngờ.
- Xóa account hoặc external identity.
- Tự tra một account khác chỉ vì email null.

Cần giữ phân biệt giữa **claim không có trong lần quan sát này** và **provider khẳng định email cũ đã bị thu hồi**. Chính sách cập nhật hồ sơ có thể yêu cầu xác minh lại hoặc thông báo cho người dùng.

### 20.5. Dùng email để gửi password reset cho account local

Nếu Portal vẫn hỗ trợ local username/password song song với SSO, reset password theo email là một **luồng xác thực riêng**. Không cho phép bất kỳ principal OIDC nào có cùng email tự đổi password account local nếu chưa qua account linking/reauthentication hoặc recovery policy đủ mạnh.

## 21. Kiểm thử các nhánh của chính sách danh tính

Vì lỗi account linking có hậu quả cao, nên kiểm thử **quyết định nghiệp vụ** độc lập với việc HTTP OIDC login hoạt động:

| Case | Đầu vào | Kết quả mong đợi |
|---|---|---|
| Login lại | Cùng issuer+subject, email không đổi | Cùng internal user |
| Đổi email | Cùng issuer+subject, email mới đã verified | Cùng internal user; cập nhật liên hệ theo policy |
| Email chưa verified | Identity đã linked, email_verified=false | Không tự link khác; hạn chế tác vụ phụ thuộc email |
| Claim verified thiếu | email_verified=null | Không mặc định true |
| Email trùng account khác | Subject mới, email giống user cũ | Không tự liên kết |
| Hai issuer trùng subject | Issuer khác, sub giống | Hai external identity khác nhau |
| Email bị tái cấp | Subject mới, cùng email | Không chuyển quyền account cũ |
| Account disabled | Identity đúng nhưng user disabled | Không cấp quyền Portal |
| Hai callback concurrent | Cùng issuer+subject tạo mới | Chỉ một external identity mapping thành công |
| UserInfo thiếu email | Có issuer+sub hợp lệ | Không mất identity; xử lý profile thiếu theo policy |
| Email đổi nhưng role cố định | Same identity | Không tự cấp/thu hồi role chỉ do email |
| Link identity đã gắn user khác | B bị link từ trước | Từ chối hoặc manual review, không overwrite |

### 21.1. Unit test cho email_verified

Ví dụ kiểm tra helper `ObservedEmail` bằng JUnit 5:

~~~java
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class ObservedEmailTest {

    @Test
    void missingVerifiedClaimMustNotBeTrusted() {
        ObservedEmail email =
            new ObservedEmail("minh@example.test", null);
        assertFalse(email.isVerified());
    }

    @Test
    void explicitlyFalseVerifiedClaimMustNotBeTrusted() {
        ObservedEmail email =
            new ObservedEmail("minh@example.test", false);
        assertFalse(email.isVerified());
    }

    @Test
    void verifiedEmailMustHaveNonEmptyValue() {
        assertFalse(new ObservedEmail(null, true).isVerified());
        assertFalse(new ObservedEmail(" ", true).isVerified());
        assertTrue(new ObservedEmail("minh@example.test", true).isVerified());
    }
}
~~~

Đây là unit test của **logic Java**, không phải test xác minh OIDC ID Token. Trong integration test, Spring Security Test có thể mô phỏng principal bằng `oidcLogin()`; khi cần xác minh issuer, callback, token exchange và OIDC discovery, phải dùng môi trường kiểm thử phù hợp hoặc mock server cho IdP.

### 21.2. Test phân biệt cặp issuer+subject

~~~java
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class OidcIdentityKeyTest {

    @Test
    void sameSubjectFromTwoIssuersIsDifferentIdentity() {
        OidcIdentityKey company =
            new OidcIdentityKey("https://login.company.test", "42");
        OidcIdentityKey partner =
            new OidcIdentityKey("https://login.partner.test", "42");

        assertNotEquals(company, partner);
    }
}
~~~

Để test provisioning race condition, chỉ unit test `findBy...` là chưa đủ: cần integration test database với **unique constraint thực** và transaction/rollback khi có hai request đồng thời.

## 22. Troubleshooting: khi người dùng phản ánh “bị mất tài khoản”

| Triệu chứng | Khả năng nguyên nhân | Hướng điều tra |
|---|---|---|
| Đổi email xong không thấy đơn hàng cũ | Hệ thống tra user bằng email, tạo account mới | Đối chiếu issuer+subject trước/sau và internal user mapping |
| Hai account cùng email bị gộp sai | Auto-link theo email hoặc normalize quá mạnh | Kiểm tra audit linking, rollback và quyền dữ liệu |
| Đăng nhập SSO lấy dữ liệu account local | Có fallback tìm local user bằng email | Dừng auto-link, yêu cầu xác minh quyền sở hữu hai account |
| Email_verified=false nhưng vẫn được cấp quyền admin | Authorization dựa trên email/domain | Kiểm tra nguồn role/tenant membership và chính sách kiểm chứng |
| Email_verified không có mà UI ghi “verified” | Mặc định null thành true hoặc dùng logic sai | Kiểm tra claim mapping và điều kiện Boolean.TRUE |
| Hai IdP cùng sub gây collision | Chỉ dùng sub làm unique key toàn hệ thống | Thêm issuer namespace, migration dữ liệu |
| Sau đổi issuer bị coi là account mới | Khóa external identity thay đổi | Migration/link danh tính có chứng cứ |
| Hai callback cùng lúc tạo hai user | Check-then-insert không có unique constraint | Transaction và UNIQUE(issuer,subject) |
| User bị khóa vẫn truy cập được API | Chỉ kiểm tra authenticated, không kiểm tra internal status | Authorization layer và session/revocation |
| Claim email không có sau cập nhật IdP | Scope/consent/UserInfo thay đổi | Kiểm tra provider và policy xử lý missing data |
| SSO thành công nhưng Portal chặn account | Chưa provision, link chưa duyệt hoặc user disabled | Phân biệt authentication thành công với quyền Portal |
| Link account cũ thất bại | Identity mới đã liên kết với user khác | Xử lý tranh chấp có audit, không overwrite |

**Không ghi toàn bộ ID Token, access token, refresh token, session cookie hay thông tin cá nhân vào log để debug.** Có thể ghi **event ID, issuer được cấu hình, mã trạng thái mapping, internal user ID pseudonymized theo chính sách và loại lỗi**, với quyền truy cập/tồn trữ thích hợp.

## 23. Bảo mật và phản ứng khi phát hiện merge sai

Nếu phát hiện một external identity đã được liên kết sai sang account khác do trùng email, coi đây là **sự cố phân quyền/dữ liệu** chứ không chỉ là lỗi hồ sơ.

Các bước cần phối hợp với bộ phận vận hành/bảo mật:

1. **Ngăn truy cập sai tiếp diễn**: tạm vô hiệu mapping đáng ngờ hoặc phiên/permissions có liên quan theo quy trình được phê duyệt.
2. **Xác định phạm vi**: external identities nào, internal users nào, tenant/resources nào bị ảnh hưởng, trong khoảng thời gian nào.
3. **Kiểm tra audit và tính toàn vẹn**: các thao tác đọc/sửa dữ liệu, quyền đã cấp, thay đổi email/role.
4. **Khôi phục mapping chính xác**: dựa trên issuer+subject và chứng cứ, không tiếp tục suy từ email.
5. **Đánh giá token/session còn hoạt động** và áp dụng revoke/logout/expire khi cần.
6. **Khắc phục gốc**: bỏ logic find-by-email-and-link, thêm uniqueness/transaction, bổ sung test collision và quy trình manual review.
7. **Xử lý nghĩa vụ thông báo** theo chính sách bảo mật và quy định dữ liệu áp dụng.

Nếu có dữ liệu bị ghi vào sai account, chỉ “unlink identity” có thể chưa đủ; cần xem liệu quyền truy cập hoặc dữ liệu đã bị chuyển và có phải hoàn nguyên hay không.

## 24. Checklist trước khi triển khai

| Câu hỏi | Điều kiện mong đợi |
|---|---|
| Principal OIDC lấy từ nguồn nào? | OIDC login do Spring Security xác minh, không phải JSON tự khai |
| Khóa external identity là gì? | `(issuer, subject)` |
| App có internal user ID riêng không? | Có; dùng cho ownership và dữ liệu nghiệp vụ |
| Email có được dùng làm primary key/linking key không? | Không |
| Có phân biệt `email_verified=true/false/null` không? | Có |
| Claim email bị thiếu thì sao? | Không mất identity; có chính sách xử lý hồ sơ thiếu |
| Email thay đổi thì sao? | Giữ internal user theo identity; cập nhật contact email phù hợp |
| Có email collision thì sao? | Không auto merge; có luồng review/linking |
| Hai IdP cùng sub/email có bị ghép không? | Không; issuer namespace được giữ |
| Identity mới đã gắn account khác? | Không thể overwrite tùy ý; được phát hiện bằng unique constraint |
| Auto-provision có điều kiện không? | Có, theo issuer/tenant/invitation và least privilege |
| Disabled user có tiếp tục được truy cập không? | Không, kể cả IdP login thành công |
| Có authorization ở API nghiệp vụ không? | Có, dựa internal ID, tenant, resource và quyền |
| Link account có reauthentication và audit không? | Có, tùy mức nhạy cảm của account |
| Có transaction/unique cho race condition không? | Có `UNIQUE(issuer, subject)` |
| Có kiểm thử email đổi, unverified, recycled, collision? | Có các case rõ ràng |
| Logging có tránh token/email không cần thiết không? | Có, với chính sách dữ liệu cá nhân |

## 25. Bài tập tự áp dụng

### Bài tập 1 — Email đổi nhưng subject giữ nguyên

~~~text
Ngày 1: iss=company, sub=A42, email=minh.nguyen@example.test
Ngày 2: iss=company, sub=A42, email=minh.tran@example.test
~~~

**Câu hỏi:** Có nên tạo một internal account mới và chuyển toàn bộ đơn hàng sang đó?

**Hướng giải:** Không. Tìm mapping theo issuer+subject để giữ internal user; thay đổi thông tin liên hệ theo chính sách. Ownership/permissions không thay chỉ vì email đổi.

### Bài tập 2 — Email trùng nhưng subject khác

~~~text
Existing: iss=company, sub=OLD, email=sales@example.test
New:      iss=company, sub=NEW, email=sales@example.test
~~~

**Câu hỏi:** Có thể tự động link subject NEW vào account OLD vì email_verified=true không?

**Hướng giải:** Không. Email có thể bị tái cấp hoặc là shared mailbox. Cần provisioning/linking có bằng chứng và kiểm tra account cũ, không tự trao quyền.

### Bài tập 3 — Email chưa được xác minh

~~~json
{"sub":"guest-101","email":"admin@example.test","email_verified":false}
~~~

**Câu hỏi:** OAuth2 Login hợp lệ có đủ để gọi `/admin` không?

**Hướng giải:** Không. Cần authorization policy và role/permission do nguồn tin cậy cấp. Email chưa verified càng không phải bằng chứng quyền admin.

### Bài tập 4 — Account local trùng email

~~~text
Local account user-100: minh@example.test
New OIDC identity B: minh@example.test, verified=true
~~~

**Câu hỏi:** Quy trình nào an toàn hơn auto-link?

**Hướng giải:** Người dùng xác thực vào account local hiện có, thực hiện một OIDC login riêng để chứng minh quyền kiểm soát identity B, và liên kết trong transaction sau kiểm tra B chưa thuộc account khác. Với account nhạy cảm, cần thêm reauthentication/step-up hoặc admin review.

### Bài tập 5 — Hai request đồng thời

Hai callback cho cùng `(issuer, subject)` đến hai node, cả hai đều thấy chưa có mapping.

**Câu hỏi:** Điều gì ngăn tạo hai account?

**Hướng giải:** Transaction kết hợp constraint `UNIQUE(issuer, subject)`. Khi có conflict, rollback request thua rồi đọc lại mapping đã được tạo, không thực hiện merge theo email.

## 26. Tổng kết

Trong ứng dụng **Spring Security OAuth 2.0/OIDC Client**, **email không phải một định danh đăng nhập bất biến**. Nó có thể đổi, vắng mặt, chưa được xác minh, bị tái cấp hoặc xuất hiện trên nhiều account/IdP. `email_verified=true` là thông tin về kiểm chứng địa chỉ theo OP, **không** là bằng chứng đầy đủ để tự liên kết tài khoản và cũng **không cấp quyền truy cập**.

Thiết kế bền vững là dùng **`(iss, sub)` của OIDC principal đã được xác thực** để tìm **external identity**, ánh xạ sang **internal user ID** của Portal, và kiểm tra **account status + tenant membership + permissions** một cách độc lập. Email, preferred_username và name được quản lý ở lớp hồ sơ/liên lạc với trạng thái, lịch sử và chính sách xác minh riêng.

Khi email thay đổi, **giữ nguyên identity và ownership**; khi email chưa verified, **không dùng làm chứng cứ mới**; khi email trùng, **không tự merge hoặc auto-link**. Các thao tác provision, link, unlink và migrate danh tính cần transaction, uniqueness, kiểm soát quyền, audit và quy trình xử lý xung đột. Ranh giới rõ giữa **authentication**, **identity mapping**, **profile** và **authorization** là chìa khóa phòng tránh account takeover trong các ứng dụng đăng nhập liên kết nhiều nhà cung cấp.
