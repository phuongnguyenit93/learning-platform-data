# Account identifier — Định danh tài khoản trong hệ thống xác thực

> **Chương:** Account  
> **Chủ đề:** Account identifier  
> **Bối cảnh:** Module SECURITY_AUTHENTICATION_FUNDAMENTALS nghiên cứu cách xác thực danh tính qua credential, mật khẩu, MFA, passkey, chứng chỉ, token và phiên; từ đó thiết kế luồng đăng nhập, liên kết danh tính và khôi phục tài khoản có ranh giới tin cậy rõ ràng.

## 1. Account identifier là gì?

**Account identifier** là giá trị dùng để **tham chiếu hoặc tìm một tài khoản trong một phạm vi đã xác định**. Tài khoản là hồ sơ do hệ thống quản lý, có trạng thái, các credential đăng nhập, thông tin liên hệ, chính sách và các quan hệ quyền truy cập. Định danh giúp hệ thống biết **đang nói đến tài khoản nào**; bản thân định danh **không chứng minh bên gọi đang sở hữu tài khoản**.

Ví dụ, một người có thể đăng nhập vào cùng tài khoản bằng tên đăng nhập *minh.nguyen*, email *minh@example.org* hoặc passkey đã đăng ký. Ba cách bắt đầu đăng nhập này có thể dẫn đến một tài khoản nội bộ có ID bất biến *acc-1742*. Khi người dùng đổi email, ID nội bộ vẫn nên giữ nguyên.

Cần tách ba câu hỏi:

1. **Xác định tài khoản:** chuỗi người dùng cung cấp tương ứng với tài khoản nào?
2. **Xác thực:** bên tương tác có đưa ra bằng chứng hợp lệ về quyền kiểm soát credential của tài khoản đó không?
3. **Phân quyền:** tài khoản/chủ thể đã xác thực có được thực hiện hành động đang yêu cầu không?

Đăng nhập bằng một email đã biết không đồng nghĩa với xác thực. Việc biết ID tài khoản, kể cả ID khó đoán, cũng không cho phép truy cập tài khoản. Một API vẫn phải kiểm tra token/phiên và quyền trên từng tài nguyên.

### Mục tiêu học tập

Sau bài này, người học có thể:

- Phân biệt ID nội bộ ổn định, tên đăng nhập, email/số điện thoại, ID credential và định danh liên kết từ nhà cung cấp danh tính.
- Chọn **phạm vi duy nhất** cho identifier trong ứng dụng một tenant hoặc nhiều tenant.
- Thiết kế quy tắc chuẩn hóa, kiểm tra trùng, đăng ký, thay đổi, thu hồi và tái sử dụng identifier.
- Mô tả đường đi an toàn từ identifier do client cung cấp đến account ID, kiểm tra credential, principal và phiên.
- Phân tích rủi ro dò tài khoản, nhầm tài khoản, liên kết sai danh tính, chiếm quyền qua khôi phục và vượt ranh giới tenant.

## 2. Các loại định danh không thay thế cho nhau

| Loại | Ví dụ | Được dùng cho | Điều cần nhớ |
| --- | --- | --- | --- |
| **Internal account ID** | UUID của một bản ghi tài khoản | Khóa chính, quan hệ dữ liệu, audit nội bộ, tạo principal | Ổn định, không phụ thuộc email; không phải bí mật hay bằng chứng đăng nhập. |
| **Username / login name** | *minh.nguyen* | Người dùng nhận biết và tìm tài khoản khi đăng nhập | Có thể đổi; phải định nghĩa namespace, chuẩn hóa và quy tắc chống trùng. |
| **Email / số điện thoại** | *minh@example.org*, số dạng E.164 | Liên lạc, gửi xác minh, hoặc đăng nhập nếu sản phẩm cho phép | Là thông tin có thể đổi chủ; trạng thái “đã xác minh” cần có thời điểm và mục đích. |
| **External subject ID** | Cặp *(issuer, subject)* từ OpenID Connect | Ánh xạ danh tính từ IdP vào tài khoản ứng dụng | Subject có ý nghĩa trong phạm vi issuer; không suy từ tên hay email. |
| **Credential ID** | ID passkey/WebAuthn | Tìm khóa công khai hoặc vật liệu xác minh đã đăng ký | Chỉ ra credential cần kiểm tra, không thay thế ID tài khoản. |
| **Session ID** | Chuỗi ngẫu nhiên trong cookie phiên | Tìm trạng thái phiên sau khi đăng nhập | Là bí mật kiểu bearer: ai cầm được có thể sử dụng trong giới hạn phiên. |
| **Resource ID** | ID hóa đơn, hồ sơ hoặc đơn hàng | Tham chiếu đối tượng nghiệp vụ | Phải kiểm tra quyền sở hữu/quyền truy cập độc lập. |

Trong mã nguồn, nên đặt tên có ngữ nghĩa như **accountId**, **loginIdentifier**, **credentialId**, **externalIssuer**, **externalSubject**, **sessionId**. Dùng biến chung chung như *id* hoặc *user* xuyên nhiều lớp dễ dẫn đến kiểm tra sai đối tượng.

**Phân biệt account và identity:** một người có thể sở hữu nhiều tài khoản; một tài khoản có thể liên kết nhiều cách đăng nhập; cùng một danh tính bên ngoài có thể được ánh xạ theo chính sách tenant. Tài khoản là đối tượng hệ thống quản lý, không phải khẳng định tuyệt đối về một con người ngoài đời.

## 3. Các thuộc tính của account identifier được thiết kế tốt

### 3.1. Tính duy nhất phải có phạm vi rõ ràng

“Duy nhất” luôn cần câu trả lời **trong hệ thống, tenant, tổ chức hay nhà cung cấp nào**.

- **ID nội bộ:** thường duy nhất trong toàn bộ cơ sở dữ liệu/ứng dụng; UUID ngẫu nhiên giúp sinh ID mà ít phải điều phối, nhưng vẫn cần ràng buộc UNIQUE/PRIMARY KEY.
- **Username:** có thể duy nhất toàn hệ thống hoặc chỉ trong từng tenant. Hai công ty độc lập có thể cùng dùng username *admin*.
- **Email:** có thể dùng ở nhiều tenant hoặc nhiều tài khoản theo nghiệp vụ. Không mặc định buộc mỗi email chỉ có một tài khoản toàn hệ thống.
- **External identity:** với OpenID Connect, khóa đối chiếu thông thường là cặp **(issuer, subject)**; nếu kiến trúc có các liên kết theo tenant thì phải thể hiện thêm phạm vi tenant trong mô hình và chính sách.

Ví dụ: **tenant A / minh** và **tenant B / minh** có thể là hai tài khoản khác nhau. Khi đăng nhập, phải xác định tenant đáng tin cậy trước khi tra username. Việc client tự gửi một tenant ID bất kỳ không đủ để xác lập quyền trong tenant đó.

### 3.2. Ổn định theo vòng đời

ID nội bộ nên được tạo một lần khi mở tài khoản và giữ nguyên qua các sự kiện: đổi email, đổi username, bổ sung passkey, thay mật khẩu, chuyển phương thức MFA. Dùng email làm khóa chính có thể khiến việc đổi email làm hỏng liên kết hồ sơ, lịch sử thanh toán hoặc bản ghi audit.

Một tài khoản bị đóng hoặc xóa có thể vẫn cần tham chiếu trong log/audit theo chính sách lưu giữ dữ liệu. Không tự động gán lại ID cũ cho người mới. **Tái sử dụng địa chỉ email hoặc username** là vấn đề chính sách riêng, không đồng nghĩa tái sử dụng account ID.

### 3.3. Không mang ý nghĩa bảo mật giả tạo

Định danh có thể là số tăng dần, UUID hoặc chuỗi ngẫu nhiên. ID khó đoán giúp giảm một số hành vi dò tuần tự, nhưng **không thay thế kiểm tra quyền**. Kẻ tấn công biết account ID vẫn phải không thể xem hoặc sửa dữ liệu nếu chưa được xác thực và phân quyền.

Một identifier công khai cũng không nên bộc lộ thông tin không cần thiết như số định danh cá nhân, ngày sinh, mã nhân viên nhạy cảm hoặc thứ tự tạo tài khoản nếu sản phẩm không có nhu cầu. Chọn ID mờ (opaque) có thể hỗ trợ giảm rò rỉ cấu trúc, nhưng vẫn phải áp dụng kiểm soát truy cập.

### 3.4. Có quy tắc so khớp nhất quán

Nếu *Minh.Nguyen* và *minh.nguyen* được coi là một tên đăng nhập, mọi nơi phải sử dụng **cùng hàm canonicalization** và cùng ràng buộc dữ liệu. Nếu khâu đăng ký cho phép hai tên nhưng khâu đăng nhập chuẩn hóa thành một, người dùng có thể đăng nhập nhầm hoặc bị chiếm namespace.

Quy tắc phải được quyết định theo **loại identifier**, không áp dụng một hàm lower-case chung cho email, username, ID nội bộ, OIDC subject và token.

## 4. Chọn identifier theo mục đích sử dụng

Một mô hình thực tế thường có:

~~~text
Account
  id              = 9b24... (ID nội bộ ổn định)
  tenantId        = tenant-A
  state           = ACTIVE

Login identifier (0..n)
  username        = "minh.nguyen"      (đã chuẩn hóa theo policy)
  email           = "minh@example.org" (đã xác minh, có thể thay đổi)
  phone           = "+84901234567"     (đã xác minh, có thể thay đổi)

Authenticator / credential (0..n)
  password_verifier
  passkey_credential_id_1
  totp_authenticator_id_1

Federated identity (0..n)
  (issuer = "https://id.example.org", subject = "abc123")
~~~

Các thông tin này thuộc **cùng account ID**, nhưng có tính chất và cách xác minh riêng. **Không phải mọi account đều phải có username hoặc email.** Tài khoản kỹ thuật, tài khoản khách, tài khoản chỉ dùng passkey hay danh tính liên kết có thể có lộ trình đăng nhập khác; yêu cầu sản phẩm sẽ quyết định tập trường bắt buộc.

| Trường hợp | Gợi ý thiết kế | Lý do |
| --- | --- | --- |
| Khóa ngoại cho hóa đơn, đơn hàng | Internal account ID | Không hỏng khi đổi username/email. |
| Biểu mẫu đăng nhập | Username/email/phone theo chính sách, kèm tenant context nếu có | Thuận tiện cho người dùng; cần ánh xạ chính xác. |
| Hiển thị hồ sơ | Display name tách khỏi login identifier | Tên hiển thị không phải khóa duy nhất. |
| Kết nối SSO | Issuer + subject từ IdP đã tin cậy | Tránh nhầm hai IdP hoặc hai subject. |
| Audit | Internal account ID + ngữ cảnh sự kiện; tối thiểu hóa PII | Giữ quan hệ lịch sử khi định danh liên hệ thay đổi. |
| Đường dẫn API chứa account ID | Tham chiếu tài nguyên cộng kiểm tra quyền server-side | ID không phải bằng chứng được truy cập. |

## 5. Canonicalization: biến đầu vào thành giá trị tra cứu

**Canonicalization** là chuyển một chuỗi nhập vào thành dạng thống nhất phục vụ so khớp. Bài toán tưởng đơn giản nhưng dễ tạo hai lỗi trái chiều: **collision** (hai giá trị khác nhau thành một) và **split identity** (hai cách viết của cùng một tên lại tạo hai tài khoản).

### 5.1. Username

Ứng dụng có thể chọn chỉ cho username ASCII với quy tắc không phân biệt chữ hoa/chữ thường, dài 3–32 ký tự, cho phép chữ, số, dấu chấm, gạch dưới và gạch nối. Khi đó server có thể bỏ khoảng trắng biên theo chính sách, đổi sang chữ thường bằng locale cố định rồi kiểm tra regex. Ví dụ:

~~~text
Đầu vào:    "  Minh.Nguyen  "
Canonical:  "minh.nguyen"
Display:    "Minh.Nguyen" (nếu sản phẩm lưu cách hiển thị riêng)

Đăng ký "MINH.NGUYEN" về sau
  -> từ chối do đã trùng canonical username trong cùng tenant.
~~~

Nếu hỗ trợ Unicode, cần định nghĩa rõ chuẩn Unicode normalization, so sánh không phân biệt hoa/thường, độ dài và cách xử lý ký tự dễ gây nhầm nhìn (confusable). Không tùy tiện biến hai tên trông gần giống thành một ID, hoặc để hai thành phần dùng hai cách chuẩn hóa khác nhau. Tập tên cấm như *admin*, *support*, *root* cũng là chính sách sản phẩm cần áp dụng nhất quán.

### 5.2. Email

Ở mức cú pháp, domain email không phân biệt chữ hoa/chữ thường; phần trước dấu @ có các quy tắc phức tạp và có thể phụ thuộc nhà cung cấp. **Không được tự động xóa dấu chấm, cắt phần sau dấu +, hoặc hạ chữ thường phần local-part cho mọi nhà cung cấp.** Những thủ thuật của một nhà cung cấp email không phải chuẩn toàn cầu.

Ứng dụng cần công bố chính sách so khớp email của chính mình, kiểm tra định dạng, lưu địa chỉ hiển thị, xác minh khả năng nhận email khi cần và quản lý việc đổi chủ địa chỉ. Nếu chính sách cho phép dùng email để đăng nhập, phải duy trì chỉ mục nhất quán với chính sách đó. Email **đã được xác minh tại thời điểm đăng ký** không phải bằng chứng rằng hộp thư luôn thuộc cùng người trong tương lai.

### 5.3. Số điện thoại

Có thể lưu dạng chuẩn quốc tế **E.164** (ví dụ +84901234567) sau khi phân tích mã quốc gia bằng thư viện phù hợp. Không lấy việc số trông đúng định dạng làm bằng chứng sở hữu: phải có thủ tục xác minh riêng. Số di động có thể chuyển chủ; SMS chịu rủi ro chuyển SIM, chuyển hướng và phishing. Đổi số điện thoại hoặc sử dụng số làm yếu tố khôi phục phải là thao tác bảo mật có kiểm soát.

### 5.4. ID nội bộ và subject từ IdP

UUID hoặc ID do server cấp không cần xử lý như username. Với OIDC, **subject là chuỗi mờ được so sánh chính xác theo quy tắc giao thức**, không tùy tiện trim, lower-case hay suy từ email. **Issuer** cũng phải được xác minh theo cấu hình IdP được tin cậy, thay vì lấy nguyên chuỗi client nhập để tạo quan hệ tin cậy.

## 6. Một mô hình lưu trữ đơn giản nhưng có ràng buộc

Ví dụ sau mang tính minh họa theo PostgreSQL. Tên trường và chi tiết được điều chỉnh theo nghiệp vụ, nhưng mô hình quan hệ rất quan trọng:

~~~sql
CREATE TABLE accounts (
    id          UUID PRIMARY KEY,
    tenant_id   UUID NOT NULL,
    state       TEXT NOT NULL CHECK (state IN ('ACTIVE', 'LOCKED', 'CLOSED')),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, id)
);

CREATE TABLE login_identifiers (
    id               UUID PRIMARY KEY,
    tenant_id        UUID NOT NULL,
    account_id       UUID NOT NULL,
    kind             TEXT NOT NULL CHECK (kind IN ('USERNAME', 'EMAIL', 'PHONE')),
    canonical_value  TEXT NOT NULL,
    display_value    TEXT NOT NULL,
    verified_at      TIMESTAMPTZ,
    active           BOOLEAN NOT NULL DEFAULT TRUE,
    FOREIGN KEY (tenant_id, account_id) REFERENCES accounts (tenant_id, id)
);

-- Ví dụ policy: một identifier đang hoạt động chỉ thuộc một
-- tài khoản trong mỗi tenant, cho từng kind.
CREATE UNIQUE INDEX uq_active_login_identifier
ON login_identifiers (tenant_id, kind, canonical_value)
WHERE active = TRUE;

CREATE TABLE federated_identities (
    id          UUID PRIMARY KEY,
    tenant_id   UUID NOT NULL,
    account_id  UUID NOT NULL,
    issuer      TEXT NOT NULL,
    subject     TEXT NOT NULL,
    FOREIGN KEY (tenant_id, account_id) REFERENCES accounts (tenant_id, id),
    UNIQUE (tenant_id, issuer, subject)
);
~~~

**Giải thích quyết định trong ví dụ:**

- Có khóa ngoại **(tenant_id, account_id)** để ngăn gắn một identifier vào account của tenant khác. Mỗi yêu cầu vẫn phải được kiểm tra quyền tenant tại tầng ứng dụng.
- Ràng buộc UNIQUE được áp dụng **trong database**, tránh điều kiện chạy đua khi hai request cùng kiểm tra “tên còn trống” rồi cùng ghi.
- Cột **active** thể hiện chính sách khi đổi/thu hồi alias; lịch sử có thể giữ lại nhưng không được tra như alias đang hoạt động.
- Trường **verified_at** cho biết đã có sự kiện xác minh; nó không tự quyết định alias có được dùng để đăng nhập, cấp quyền hay reset. Chính sách phải xét thêm loại, thời điểm, trạng thái và cách xác minh.
- Việc đặt duy nhất theo **(tenant_id, issuer, subject)** phù hợp ví dụ nhiều tenant có account riêng. Với thiết kế có một danh tính toàn cục, có thể cần ràng buộc khác. Phải quyết định trước khi triển khai.
- Schema mới thể hiện **mapping identifier**, chưa biểu diễn lưu mật khẩu, khóa passkey, token, phiên, trạng thái xác minh đang chờ hay cơ chế chống lạm dụng.

**Lưu ý về email chưa xác minh:** Nếu cho phép ai cũng đăng ký và giữ độc quyền một email chưa xác minh vô thời hạn, kẻ tấn công có thể chiếm chỗ email của người khác. Nên thiết kế trạng thái đăng ký chờ, thời hạn xác minh, chống lạm dụng và quy trình giải quyết xung đột. Không coi bản ghi đang chờ là bằng chứng quyền sở hữu email.

## 7. Luồng đăng ký: ai được nhận một identifier?

Khi người dùng yêu cầu tạo tài khoản với username và email, server nên tách **cấp account ID** khỏi **xác minh quyền kiểm soát email**.

~~~mermaid
flowchart TD
    A["Người dùng nhập username / email"] --> B["Server kiểm tra cú pháp và policy"]
    B --> C["Chuẩn hóa theo loại identifier"]
    C --> D{"Có xung đột theo namespace?"}
    D -- "Có" --> E["Thông báo phù hợp / xử lý xung đột"]
    D -- "Không" --> F["Tạo yêu cầu đăng ký có thời hạn"]
    F --> G["Kiểm tra bằng chứng sở hữu kênh nếu cần"]
    G --> H{"Bằng chứng hợp lệ?"}
    H -- "Không" --> I["Giữ pending hoặc hết hạn"]
    H -- "Có" --> J["Ghi account + mapping bằng giao dịch có UNIQUE"]
    J --> K["Cho phép đăng nhập theo policy"]
~~~

Các bất biến cần giữ:

1. Account ID được sinh bởi hệ thống, không chấp nhận một account ID tùy ý do client muốn chiếm.
2. Mỗi alias hoạt động ánh xạ tới **không quá một account trong phạm vi duy nhất đã chọn**.
3. Xác minh email/số điện thoại gắn với **đúng tài khoản, đúng giá trị, đúng mục đích và đúng yêu cầu**; token/code ngắn hạn, có giới hạn thử và không được tái sử dụng.
4. Hai yêu cầu trùng nhau đồng thời phải được database giải quyết bằng ràng buộc và xử lý lỗi dự kiến. “Kiểm tra trước rồi insert” đơn thuần không đủ.
5. Trạng thái tài khoản và alias phải thể hiện rõ: đang chờ, đang hoạt động, đã thay đổi, bị thu hồi hoặc bị khóa theo thiết kế.
6. Dữ liệu đầu vào ở client và đường dẫn URL chỉ là **gợi ý tra cứu**; kết quả xác minh từ server mới cho phép xác lập phiên.

Nếu sản phẩm tạo tài khoản ẩn danh trước khi người dùng thêm email, cần chính sách riêng khi gộp tài khoản ẩn danh với tài khoản hiện có: chứng minh quyền kiểm soát cả hai ngữ cảnh trước khi chuyển dữ liệu nhạy cảm.

## 8. Luồng đăng nhập: từ login identifier đến principal

Giả sử nhân viên đăng nhập bằng username *minh.nguyen*. Hệ thống có tenant A, password và passkey, yêu cầu MFA phù hợp với loại tài khoản.

~~~text
[Client không đáng tin]
  gửi username = "minh.nguyen"
       tenant context theo luồng sản phẩm
       bằng chứng của phương thức đã chọn
             |
             v
[Server xác định tenant hợp lệ]
  -> canonicalize username theo chính sách
  -> tìm đúng alias đang hoạt động trong tenant
  -> lấy internal account ID
  -> kiểm tra trạng thái account
  -> xác minh credential/passkey/MFA phù hợp
  -> tạo principal(account ID, tenant ID, auth time, method)
  -> tạo phiên hoặc token an toàn
             |
             v
[API tài nguyên]
  -> xác minh phiên/token
  -> kiểm tra tenant và quyền trên tài nguyên
~~~

Với mật khẩu, verifier cần kiểm tra bí mật đã được đăng ký qua cơ chế lưu bộ xác minh mật khẩu an toàn, chẳng hạn Argon2id với tham số phù hợp. Với passkey/WebAuthn, server phải xác minh challenge, origin, RP ID, chữ ký và các điều kiện user presence/user verification theo chính sách, rồi xác định account đã sở hữu credential đó. Tên đăng nhập chỉ giúp **tìm vùng dữ liệu cần xác minh**.

Nếu không tìm thấy username, phản hồi công khai nên tránh tiết lộ quá mức việc tài khoản có tồn tại hay không; vẫn cần chống thử mật khẩu hàng loạt, credential stuffing và giới hạn tốc độ theo nhiều chiều. Thiết kế cẩn thận đường sai của xác minh để giảm khác biệt thời gian dễ bị lợi dụng, nhưng không giả định thông báo chung là biện pháp duy nhất.

Ví dụ giả mã:

~~~java
LoginResult login(TenantContext tenant, String rawUsername, Evidence evidence) {
    TenantId tenantId = resolveAuthorizedTenant(tenant);
    String username = canonicalizeUsername(rawUsername);
    Optional<Account> candidate =
        accountRepository.findActiveByUsername(tenantId, username);

    enforceAbuseControls(tenantId, username, requestContext);

    // Tầng verifier che giấu chi tiết thất bại đối với client.
    VerifiedAuthentication verified =
        credentialVerifier.verify(candidate, evidence, requestContext);

    if (!verified.isAcceptable()) {
        throw genericLoginFailure();
    }

    Account account = verified.account();
    Principal principal = new Principal(
        account.id(), account.tenantId(),
        verified.method(), verified.authenticatedAt());

    return sessionService.createFreshSession(principal);
}
~~~

Đây là **giả mã**, không phải một hàm Java dùng ngay trong production. Việc trả giá trị khi không tìm thấy account, chống timing leak, chống replay, chống brute force, triển khai challenge và lưu session cần dựa trên thư viện/giao thức đã kiểm chứng.

Một trường hợp đặc biệt là **đăng nhập không cần nhập tên** bằng passkey có khả năng khám phá tài khoản (discoverable credential). Authenticator có thể trả thông tin đủ cho server tìm credential rồi suy ra account. Khi đó **credential ID và xác minh chữ ký** hỗ trợ tìm đúng tài khoản; vẫn cần ID tài khoản nội bộ ổn định cho phiên và quyền. Không được suy tài khoản từ một chuỗi credential ID chưa được xác minh.

## 9. Đăng nhập liên kết: issuer + subject thay cho suy đoán từ email

Trong OpenID Connect (OIDC), IdP gửi thông tin định danh cho Relying Party (RP). Trường **sub** là subject identifier do IdP cấp; để phân biệt các nhà phát hành, ứng dụng phải xét **iss** và **sub** cùng nhau.

~~~text
Đăng nhập từ IdP A:
  iss = https://login.company-a.example
  sub = 00u7fh...            -> account nội bộ acc-1742

Đăng nhập từ IdP B:
  iss = https://identity.company-b.example
  sub = 00u7fh...            -> có thể là account khác

Email ở hai IdP đều là:
  minh@example.org          -> chưa đủ để kết luận cùng một account
~~~

**Vì sao?** Hai IdP khác nhau có thể cấp cùng giá trị sub cho hai chủ thể hoàn toàn độc lập. Ngược lại, một IdP có thể dùng subject theo cặp (pairwise subject) nên cùng một người có sub khác nhau giữa các ứng dụng; cũng không được đoán đó là cùng người từ cấu trúc sub.

Khi nhận kết quả OIDC, RP cần:

1. Hoàn thành flow đúng giao thức, bảo vệ giao dịch đăng nhập bằng **state**, **nonce**, **PKCE** ở vị trí được quy định.
2. Xác minh chữ ký ID token và các điều kiện cần thiết: **issuer**, **audience**, thời gian hiệu lực, nonce và các ràng buộc theo flow.
3. Chỉ sau khi kiểm tra thành công mới tra bảng ánh xạ danh tính ngoài theo **issuer + subject** (và tenant nếu kiến trúc yêu cầu).
4. Tạo principal từ **account nội bộ đã ánh xạ**. Nếu chưa tồn tại mapping, áp dụng flow đăng ký hoặc liên kết có kiểm soát, không âm thầm ghép theo email.
5. Duy trì phiên RP độc lập với bước xác thực ở IdP, có thời hạn, chính sách logout, thu hồi và phân quyền riêng.

Ngay cả khi IdP cung cấp claim **email_verified = true**, đó không phải bằng chứng đầy đủ để tự động nhập hai tài khoản nội bộ thành một. Trạng thái này xác nhận theo chính sách và thời điểm của IdP; email có thể đổi hoặc được tái cấp, còn tài khoản hiện tại có thể chứa dữ liệu nhạy cảm.

**Liên kết tài khoản:** người dùng cần chủ động bắt đầu liên kết khi đã có phiên tại account nội bộ và xác thực danh tính IdP mới. Server kiểm tra mapping chưa thuộc account khác, áp dụng xác thực lại khi cần, ghi audit và thông báo thay đổi bảo mật. Việc gỡ liên kết cũng phải được kiểm soát để tránh khóa mất đường đăng nhập cuối cùng.

## 10. Identifier thay đổi: đừng đánh mất lịch sử và quyền sở hữu

### Đổi username

Một tài khoản có thể thay username từ *minh.nguyen* sang *minh.n*. Account ID trong dữ liệu nghiệp vụ không đổi. Hệ thống cần cập nhật alias trong giao dịch, thực thi unique constraint, giữ audit phù hợp và quyết định khi nào username cũ được phép tái sử dụng. Nếu username cũ từng xuất hiện trong URL hoặc mention, cần xử lý redirect và tránh chuyển nhầm dữ liệu cho chủ mới.

### Đổi email/số điện thoại

Không cập nhật địa chỉ mới rồi coi nó đã được xác minh. Nên thực hiện thao tác trong phiên đủ tin cậy, yêu cầu xác thực lại theo rủi ro, xác minh quyền kiểm soát địa chỉ mới, gửi thông báo qua kênh cũ khi phù hợp và quản lý thời gian chuyển tiếp. Nếu email hoặc số điện thoại cũ là kênh khôi phục, phải xác định rõ khi nào kênh cũ bị vô hiệu.

### Mất credential và khôi phục

Người dùng có thể quên mật khẩu, mất passkey hoặc thay điện thoại. Khôi phục thực chất là **cho phép thay đổi phương tiện kiểm soát tài khoản**. Do đó việc tìm ra email/số điện thoại của một account chỉ là bước định tuyến; cấp lại credential phải dựa trên bằng chứng bổ sung phù hợp với mức rủi ro.

Một liên kết khôi phục nên có token ngẫu nhiên đủ mạnh, gắn với account ID và mục đích, ngắn hạn, dùng một lần, bị hạn chế thử và không được rò rỉ qua log hoặc bên thứ ba. Sau khi đổi credential cần cân nhắc thu hồi phiên/refresh token và thông báo. Đối với tài khoản nhạy cảm, quy trình hỗ trợ thủ công cũng phải có kiểm tra và ghi nhận rõ ràng.

### Đóng tài khoản, xóa và tái sử dụng

Khi đóng tài khoản, hệ thống cần quyết định alias bị vô hiệu ngay hay được giữ theo thời hạn, xử lý ràng buộc pháp lý/lưu trữ, chặn đăng nhập và thu hồi phiên. Không dùng việc một email mới nhận được mã OTP để tự động **kế thừa** toàn bộ dữ liệu của tài khoản cũ từng gắn với email đó. Đặc biệt, số điện thoại và email doanh nghiệp có thể chuyển cho người khác theo thời gian.

### Merge account

Gộp hai tài khoản có thể ảnh hưởng đơn hàng, vai trò, lịch sử audit, khôi phục và quyền truy cập. Cần có quy trình chứng minh quyền kiểm soát **cả hai account**, giải quyết xung đột và giữ nguồn gốc dữ liệu. Không gộp bằng câu lệnh cập nhật khóa ngoại trên cơ sở chỉ thấy email hoặc tên giống nhau.

## 11. Các sai lầm bảo mật liên quan đến account identifier

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Coi account ID hoặc email là bí mật xác thực | Biết ID là được truy cập, dễ dẫn đến IDOR/BOLA | Luôn xác thực phiên/token và phân quyền ở từng tài nguyên. |
| Dùng email làm primary key | Đổi email phá quan hệ; email chuyển chủ gây nhầm tài khoản | Dùng ID nội bộ ổn định, email là alias có vòng đời. |
| Xác định account qua tham số client mà không kiểm tra bằng chứng | Account takeover, confused deputy | Verifier quyết định principal sau khi kiểm tra credential. |
| Chuẩn hóa tên khác nhau giữa đăng ký và đăng nhập | Trùng namespace, nhầm tài khoản | Một canonicalization policy cho từng loại và UNIQUE ở DB. |
| Chỉ kiểm tra username unique tại ứng dụng | Hai request đồng thời có thể tạo trùng | Ràng buộc UNIQUE và transaction, xử lý lỗi collision. |
| Đăng nhập tenant A nhưng tra username tenant B | Lộ dữ liệu và vượt ranh giới tenant | Scope tenant từ ngữ cảnh tin cậy; unique và FK theo tenant, kiểm tra quyền. |
| Gộp SSO theo email giống nhau | Nhầm danh tính giữa IdP hoặc email được tái cấp | Mapping theo issuer + subject, liên kết có xác thực cả hai phía. |
| Reset tài khoản chỉ bằng OTP của giao dịch khác | Replay hoặc mạo danh account khác | Ràng buộc OTP/token với account, mục đích, challenge và thời hạn. |
| API tin accountId trong request body thay vì principal | Người dùng sửa accountId để tác động tài khoản khác | Lấy actor từ phiên/token đã kiểm tra; xác thực quyền với target account. |
| Phản hồi “email này chưa tồn tại” ở mọi nơi | Dò được danh sách tài khoản | Phản hồi phù hợp, giới hạn tốc độ, giám sát và chống lạm dụng. |
| Log thẳng token, OTP, dữ liệu định danh nhạy cảm | Lộ credential, lộ PII | Masking/redaction, phân quyền log, giới hạn lưu giữ. |

### Ví dụ: IDOR do nhầm actor và target

~~~http
PATCH /api/accounts/acc-9911/profile
Authorization: Bearer <access-token-của-acc-1742>
Content-Type: application/json

{"displayName":"Đã bị sửa"}
~~~

Nếu server chỉ kiểm tra token hợp lệ rồi lấy **acc-9911** từ URL để cập nhật, tài khoản 1742 có thể sửa người khác. Server phải lấy **actorAccountId** từ token/phiên đã kiểm tra, lấy **targetAccountId** từ URL, rồi quyết định actor có quyền cập nhật target hay không. Với API “sửa hồ sơ của tôi”, có thể không cần nhận target account ID do client chọn.

### Ví dụ: enumeration trong quên mật khẩu

Thông báo “Không tìm thấy email này” cho tài khoản không tồn tại nhưng “Đã gửi mail” cho tài khoản có thật tạo một kênh dò. Có thể hiển thị thông điệp chung như: “Nếu thông tin khớp một tài khoản đủ điều kiện, hướng dẫn sẽ được gửi”. Tuy nhiên phản hồi chung vẫn phải kết hợp giới hạn tốc độ, chống tự động hóa và giám sát để giảm dò qua thời gian hoặc hành vi phụ.

## 12. Các bất biến để review trong code và database

Một hệ thống quản lý identifier nên xác định rõ các **bất biến** — những điều phải luôn đúng sau mọi request, kể cả khi có lỗi hoặc concurrency:

1. Mỗi account có **internal account ID ổn định** và thuộc đúng namespace/tenant.
2. Mỗi login identifier đang hoạt động ánh xạ về không quá một account trong namespace mà sản phẩm đã định nghĩa.
3. Mỗi credential đã đăng ký thuộc đúng account; một phản hồi xác thực chỉ có giá trị khi **bằng chứng được verifier kiểm tra thành công**.
4. Mỗi mapping OIDC được tra theo issuer + subject trong phạm vi đã định; ID token đến từ issuer và audience đáng tin cậy.
5. Không có thay đổi identifier nhạy cảm nào chỉ dựa vào việc client biết account ID hoặc tên đăng nhập.
6. Mã xác minh, token đổi email và token khôi phục phải có phạm vi **account + mục đích + giao dịch + thời hạn** thích hợp; ngăn phát lại theo giao thức.
7. Principal trong phiên chứa account ID xác định bởi server; quyền truy cập được kiểm tra **mỗi lần dùng tài nguyên**.
8. Account bị khóa/đóng, credential bị thu hồi và alias bị vô hiệu không thể được sử dụng như trạng thái đang hoạt động.
9. Audit lưu được actor, target, hành động, kết quả và thời điểm, nhưng không ghi trực tiếp password, OTP, session ID hay token bearer.
10. Database unique constraint và transaction xử lý xung đột ngay cả khi có nhiều yêu cầu đồng thời.

### Kịch bản kiểm thử tối thiểu

- **Trùng tên:** trong cùng tenant, đăng ký *Minh.Nguyen* rồi *minh.nguyen* phải tuân theo cùng policy và không tạo hai alias hoạt động trùng canonical.
- **Khác tenant:** hai tenant có thể có username giống nhau nếu namespace được thiết kế như vậy; login không thể dùng tenant A để tra dữ liệu tenant B.
- **Đổi email:** account ID và liên kết dữ liệu cũ không đổi; email mới chưa qua xác minh không được dùng như email đã xác minh.
- **SSO:** hai token có cùng sub nhưng khác iss không được tự động ánh xạ cùng account; token sai audience bị từ chối.
- **Race condition:** hai request cùng chiếm một username không được cùng thành công nhờ unique constraint.
- **Dò tài khoản:** luồng đăng nhập/quên mật khẩu có phản hồi và giới hạn lạm dụng phù hợp.
- **Sửa hồ sơ:** token của account A không thể sửa account B khi thiếu quyền, bất kể biết account ID của B.
- **Khôi phục:** mã đúng nhưng hết hạn, đã sử dụng, khác account hoặc khác mục đích phải bị từ chối.
- **Thu hồi:** alias ngừng hoạt động và credential đã bị thu hồi không còn cho phép đăng nhập.

## 13. Bài tập tình huống

Một nền tảng học trực tuyến phục vụ hai tổ chức **Alpha** và **Beta**. Cả hai đều có nhân viên tên đăng nhập *lan*. Lan của Alpha đăng nhập bằng passkey, Lan của Beta đăng nhập qua IdP doanh nghiệp. Nhân viên Alpha thay email từ *lan@alpha.example* sang *lan.new@alpha.example*; vài tháng sau email cũ được cấp cho nhân viên khác.

**Yêu cầu thiết kế:**

1. Chọn khóa chính và ràng buộc duy nhất cho tài khoản, username và danh tính SSO.
2. Mô tả người dùng chọn tenant theo cách nào và server kiểm tra phạm vi đó ra sao.
3. Giải thích tại sao người mới nhận *lan@alpha.example* không thể đăng nhập để thừa hưởng dữ liệu cũ chỉ bằng việc chứng minh quyền kiểm soát email.
4. Thiết kế thao tác thêm IdP mới vào tài khoản của Lan mà không tự động gộp tài khoản do email giống nhau.
5. Chỉ ra bước xác thực và bước phân quyền khi Lan truy cập chứng chỉ khóa học.

**Hướng giải đề xuất:** Dùng internal UUID làm account ID, scope username theo tenant và lưu federated identity bằng (tenant, issuer, subject) nếu mỗi tenant có account riêng; không cấp quyền từ email. Tenant được xác lập theo route/host/cấu hình đăng nhập tin cậy rồi được kiểm tra ở server; account chỉ được chọn sau khi xác minh credential/IdP tương ứng. Khi đổi email, giữ account ID và ghi lịch sử thay đổi; người nhận email cũ không được tự kế thừa credential và dữ liệu. Việc thêm IdP yêu cầu phiên account hiện tại cùng bằng chứng từ IdP mới, kiểm tra trùng liên kết và audit. API lấy principal từ phiên, sau đó kiểm tra quyền của principal trên chứng chỉ được yêu cầu.

### Câu hỏi tự đánh giá

1. Vì sao UUID khó đoán không thể thay thế kiểm tra quyền của API?
2. Một username là duy nhất toàn hệ thống hay theo tenant? Điều gì quyết định câu trả lời?
3. Email đã xác minh có đồng nghĩa người dùng giữ quyền sở hữu email mãi mãi không?
4. Vì sao hai định danh SSO có cùng sub nhưng khác iss phải được phân biệt?
5. Vì sao không chuẩn hóa OIDC subject theo quy tắc username?
6. Vì sao chỉ kiểm tra username còn trống trước lệnh INSERT vẫn chưa đủ?
7. Trong reset mật khẩu, identifier được dùng để làm gì và bằng chứng xác thực thật sự đến từ đâu?

**Đáp án ngắn:** (1) ID là tham chiếu, không phải bằng chứng; (2) chính sách namespace; (3) không, địa chỉ có thể đổi chủ; (4) sub có ý nghĩa theo issuer; (5) subject là định danh mờ cần so khớp chính xác; (6) có race condition, cần unique constraint; (7) identifier tìm account, còn token/quy trình khôi phục đủ tin cậy cho phép thay credential.

## 14. Tổng kết

**Account identifier trả lời “đang nói đến tài khoản nào?”, không trả lời “ai có quyền sử dụng tài khoản đó?”.** Thiết kế tốt thường dùng ID nội bộ ổn định, lưu username/email/phone như các alias có phạm vi duy nhất và vòng đời rõ ràng, lưu danh tính liên kết theo issuer + subject và lưu credential riêng. Mỗi bước xác thực chuyển từ **định danh được khai báo** qua **bằng chứng đã kiểm tra** đến **principal và phiên**; từng API sau đó tiếp tục kiểm tra quyền.

Khi review một thiết kế, hãy luôn hỏi: **Identifier này là loại gì? Duy nhất ở đâu? Ai cấp và xác minh nó? Nó có thể thay đổi hoặc đổi chủ không? Điều gì xảy ra khi hai request đồng thời dùng cùng identifier? Bằng chứng nào cho phép ánh xạ nó vào principal, và ai có quyền dựa vào kết luận đó?**
