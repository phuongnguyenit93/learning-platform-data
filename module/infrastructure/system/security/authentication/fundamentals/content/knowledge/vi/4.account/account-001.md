# Account là gì?

**Account (tài khoản)** là một bản ghi logic mà hệ thống dùng để **đại diện, quản lý và duy trì trạng thái của một chủ thể** theo thời gian. Account thường có **định danh nội bộ ổn định**, các phương thức đăng nhập, thuộc tính hồ sơ, trạng thái hoạt động và các quan hệ để xác định quyền truy cập. Account có thể gắn với người dùng, một tổ chức hoặc một dịch vụ; không nhất thiết tương ứng với đúng một con người.

Trong hệ thống xác thực danh tính (*authentication*), account là **đối tượng được liên kết với kết quả xác thực**. Người dùng chứng minh quyền kiểm soát credential (mật khẩu, passkey, MFA, chứng chỉ hoặc phương thức của nhà cung cấp danh tính); máy chủ xác định credential thuộc account nào; sau đó có thể cấp phiên/token mang ngữ cảnh account để xử lý các yêu cầu tiếp theo. **Account không đồng nghĩa với credential, phiên đăng nhập hay quyền truy cập.**

Ví dụ: Minh có một account trên ứng dụng học tập StudyHub. Minh đăng nhập bằng passkey trên điện thoại hoặc mật khẩu kèm TOTP trên máy tính. Hai phương thức đăng nhập khác nhau, nhưng hồ sơ, khóa học và quyền của Minh vẫn gắn với **cùng một account ID**.

## 1. Account nằm ở đâu trong bức tranh authentication?

| Khái niệm | Vai trò chính | Ví dụ trong StudyHub |
| --- | --- | --- |
| **Chủ thể (subject)** | Thực thể thực hiện hành động hoặc được hệ thống nói đến. | Minh; một tác vụ nền tự động. |
| **Danh tính (identity)** | Tập thuộc tính, định danh và quan hệ mô tả chủ thể trong một ngữ cảnh. | Tên hiển thị, mã học viên, tổ chức. |
| **Account** | Đối tượng hệ thống quản lý ổn định, làm điểm neo cho credential và trạng thái. | Account có ID nội bộ acc_7f32… |
| **Identifier** | Giá trị dùng để tham chiếu, tra cứu hoặc phân biệt account. | Account ID, username, email. |
| **Credential / authenticator** | Bằng chứng hoặc phương tiện chứng minh quyền kiểm soát account. | Password verifier, public key của passkey, khóa bảo mật. |
| **Authentication** | Kiểm tra bằng chứng để xác định chủ thể đang yêu cầu là ai trong hệ thống. | Kiểm tra chữ ký WebAuthn hợp lệ. |
| **Session / token** | Duy trì hoặc chuyển ngữ cảnh xác thực giữa các request. | Cookie phiên ngẫu nhiên, access token cho API. |
| **Authorization** | Quyết định chủ thể được phép thực hiện thao tác nào. | Giảng viên được sửa bài giảng mình sở hữu. |

Các quan hệ trên không phải một đối một tuyệt đối: một người có thể có nhiều account; một account có thể có nhiều credential; credential có thể bị thay thế mà account không đổi; một account có nhiều session đồng thời; một tổ chức có nhiều account thành viên.

### 1.1. Account không phải email hay mật khẩu

Email thường được dùng làm **tên đăng nhập, kênh liên hệ hoặc kênh khôi phục**, nhưng có thể thay đổi, mất quyền kiểm soát hoặc được tái sử dụng. Mật khẩu là một **credential** có thể đổi, bị thu hồi hoặc rò rỉ. Vì vậy cả email lẫn mật khẩu đều không nên là khóa định danh cốt lõi cho dữ liệu lâu dài.

Ví dụ: Minh đổi email từ minh@old.example sang minh@new.example. Khi bảng điểm, khóa học và lịch sử thanh toán tham chiếu **account ID bất biến**, dữ liệu vẫn thuộc đúng tài khoản sau khi cập nhật và xác minh email mới.

### 1.2. Account không chứng minh danh tính ngoài đời

Việc tạo account hoặc xác minh quyền truy cập hộp thư **không mặc nhiên chứng minh tên thật, tuổi hay tư cách pháp lý**. Hệ thống cần bảo đảm danh tính ngoài đời như ngân hàng có thể áp dụng bước **identity proofing** riêng. Ứng dụng học tập có thể chấp nhận account đăng ký bằng email mà không suy diễn email đã xác minh là bằng chứng danh tính pháp lý.

## 2. Mô hình quan hệ của một account

Một account tối thiểu thường có **ID nội bộ, trạng thái và dấu thời gian**. Các dữ liệu khác nên phân tách theo trách nhiệm để có thể thay đổi và thu hồi độc lập.

~~~mermaid
erDiagram
    ACCOUNT ||--o{ CREDENTIAL : "có"
    ACCOUNT ||--o{ IDENTIFIER : "được tìm bằng"
    ACCOUNT ||--o{ EXTERNAL_IDENTITY : "liên kết"
    ACCOUNT ||--o{ SESSION : "có"
    ACCOUNT ||--o{ MEMBERSHIP : "tham gia"
    ORGANIZATION ||--o{ MEMBERSHIP : "gồm"
    ACCOUNT {
      uuid account_id PK
      string status
      datetime created_at
      datetime updated_at
    }
    CREDENTIAL {
      uuid credential_id PK
      string kind
      datetime enrolled_at
      datetime revoked_at
    }
    IDENTIFIER {
      uuid identifier_id PK
      string kind
      boolean verified
    }
    EXTERNAL_IDENTITY {
      uuid link_id PK
      string issuer
      string subject
    }
    SESSION {
      uuid session_id PK
      datetime expires_at
      datetime revoked_at
    }
    MEMBERSHIP {
      uuid membership_id PK
      string role
    }
    ORGANIZATION {
      uuid organization_id PK
    }
~~~

Đây là mô hình minh họa, không bắt buộc mọi hệ thống có tất cả các bảng như vậy. Một số điểm cần lưu ý:

- **Account ID** do hệ thống cấp, ổn định, không phụ thuộc email hoặc tên hiển thị, và không phải bí mật bảo mật.
- **Identifier** có thể là username, email hoặc số điện thoại. Cần quy tắc chuẩn hóa, tính duy nhất trong phạm vi phù hợp và trạng thái xác minh.
- **Credential** được gắn với account qua quy trình ghi danh an toàn. Dữ liệu lưu trữ tùy loại: password verifier, public key và metadata của passkey, thông tin MFA; không lưu mật khẩu rõ hoặc private key passkey của người dùng.
- **External identity** cần lưu cặp **issuer + subject** đáng tin cậy từ nhà cung cấp danh tính; email do IdP trả về không thay thế cặp này.
- **Session** có vòng đời riêng. Đổi credential, tạm ngưng account và thu hồi session là các thao tác khác nhau nhưng có thể kéo theo nhau theo chính sách.
- **Membership / role** cung cấp ngữ cảnh phân quyền. Một account có thể có vai trò khác nhau trong các tổ chức hoặc tenant.

### 2.1. Ví dụ mô hình dữ liệu tối giản

Đoạn SQL minh họa cách tách account khỏi email và credential. Đây **chưa phải schema production** vì chưa thể hiện đầy đủ audit, chính sách phiên, quản lý bí mật và các ràng buộc nghiệp vụ.

~~~sql
CREATE TABLE accounts (
    account_id UUID PRIMARY KEY,
    status VARCHAR(24) NOT NULL
        CHECK (status IN ('PENDING', 'ACTIVE', 'SUSPENDED', 'CLOSED')),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE TABLE account_emails (
    email_id UUID PRIMARY KEY,
    account_id UUID NOT NULL REFERENCES accounts(account_id),
    normalized_email VARCHAR(320) NOT NULL,
    verified_at TIMESTAMP WITH TIME ZONE,
    is_primary BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE account_credentials (
    credential_id UUID PRIMARY KEY,
    account_id UUID NOT NULL REFERENCES accounts(account_id),
    credential_type VARCHAR(40) NOT NULL,
    -- Dữ liệu xác minh được bảo vệ, định dạng tùy loại credential.
    verifier_reference TEXT NOT NULL,
    enrolled_at TIMESTAMP WITH TIME ZONE NOT NULL,
    revoked_at TIMESTAMP WITH TIME ZONE
);
~~~

Trước khi áp dụng thực tế, cần quyết định **email có duy nhất toàn hệ thống hay theo tenant**, cách xử lý email chưa xác minh, Unicode/case folding, việc đổi email và unique constraint/transaction để tránh hai request đồng thời nhận cùng một identifier. Không nên mặc định bỏ dấu chấm hoặc dấu cộng trong mọi địa chỉ email: quy tắc phụ thuộc nhà cung cấp.

## 3. Những loại account thường gặp

| Loại | Mục đích | Điểm cần lưu ý |
| --- | --- | --- |
| **User account** | Gắn hoạt động và dữ liệu với người sử dụng. | Có thể có nhiều credential, thiết bị và phương thức khôi phục. |
| **Guest / temporary account** | Cho dùng một phần chức năng trước đăng ký đầy đủ. | Giới hạn quyền, dữ liệu và tuổi thọ; kiểm soát khi chuyển thành account chính thức. |
| **Service account / workload identity** | Cho tiến trình, job hoặc API gọi dịch vụ khác. | Dùng danh tính máy, credential ngắn hạn hoặc mTLS phù hợp; không tái sử dụng mật khẩu người dùng. |
| **Admin account** | Cho thao tác quản trị nhạy cảm. | Phân quyền tối thiểu, xác thực lại cho hành động quan trọng, ghi audit. |
| **Organization / tenant account** | Đại diện tổ chức hoặc phạm vi gói dịch vụ ở một số sản phẩm. | Phân biệt với user account và membership của từng thành viên. |

Tên gọi phụ thuộc domain. Trong ứng dụng đa tenant, **“account”** đôi khi còn có nghĩa **khách hàng tổ chức** hoặc **hợp đồng sử dụng dịch vụ**. Phải làm rõ trước khi chọn cấu trúc dữ liệu: account dùng để đăng nhập có thể khác đối tượng thanh toán hoặc tenant.

## 4. Vòng đời của account

Account không chỉ có hai trạng thái “đã tạo” và “đã xóa”. Cần mô tả **ai được phép chuyển trạng thái, yêu cầu bằng chứng gì và tác động đến credential/session ra sao**.

~~~mermaid
stateDiagram-v2
    [*] --> PENDING: Bắt đầu đăng ký
    PENDING --> ACTIVE: Hoàn thành yêu cầu kích hoạt
    PENDING --> CLOSED: Hủy hoặc quá hạn
    ACTIVE --> SUSPENDED: Tạm khóa theo chính sách
    SUSPENDED --> ACTIVE: Xem xét và khôi phục hợp lệ
    ACTIVE --> CLOSED: Đóng tài khoản hợp lệ
    SUSPENDED --> CLOSED: Đóng theo quy trình
    CLOSED --> [*]: Lưu trữ / xóa dữ liệu theo chính sách
~~~

State machine này là ví dụ. Độ bảo đảm để kích hoạt có thể khác nhau theo sản phẩm. **SUSPENDED là trạng thái quản trị/nghiệp vụ của account**; còn tạm hạn chế đăng nhập vì nhiều lần thử sai có thể là chính sách riêng có thời hạn, không nhất thiết biến account thành SUSPENDED.

### 4.1. Đăng ký và kích hoạt

1. Nhận thông tin tối thiểu, kiểm tra dữ liệu, hạn chế lộ việc một email đã có account hay chưa nếu tạo rủi ro.
2. Cấp **account ID nội bộ**, đặt trạng thái như PENDING.
3. Xác minh kênh liên hệ nếu yêu cầu. Link hoặc mã xác minh cần khó đoán, có hạn sử dụng, giới hạn thử và không dùng lại.
4. Ghi danh credential an toàn: mật khẩu lưu với KDF chuyên dụng và salt, passkey đăng ký qua WebAuthn, MFA bổ sung theo chính sách.
5. Kích hoạt account khi đủ điều kiện; chỉ cấp phiên đã xác thực đầy đủ khi hoàn tất luồng tương ứng.

Kiểm soát cả **lạm dụng đăng ký** như tạo hàng loạt, spam email xác minh và chiếm identifier. Rate limiting nên cân nhắc nhiều tín hiệu để vừa giảm lạm dụng vừa tránh khóa nhầm người dùng hợp lệ.

### 4.2. Sử dụng thường ngày

Khi đăng nhập, dịch vụ xác thực kiểm tra credential và các điều kiện MFA, sau đó ánh xạ thành **account ID**. Mỗi request tiếp theo cần đánh giá **trạng thái account**, phiên/token và quyền trên tài nguyên theo chính sách. Xác thực thành công không có nghĩa account sẽ hoạt động mãi mãi hoặc được phép làm mọi việc.

Ví dụ khi StudyHub nhận request sửa bài giảng, server phải kiểm tra account còn hoạt động, session hợp lệ, membership trong tổ chức liên quan và quyền sửa **bài giảng cụ thể**. Chỉ kiểm tra token có chữ ký hợp lệ là chưa đủ.

### 4.3. Thay đổi credential và thuộc tính nhạy cảm

Đổi mật khẩu, thêm passkey, xóa MFA, đổi email khôi phục hoặc liên kết IdP mới đều có thể thay đổi **ai kiểm soát account trong tương lai**. Những thao tác này cần xác thực lại gần thời điểm thay đổi với mức bảo đảm phù hợp, kiểm tra quyền, thông báo qua kênh tin cậy và ghi sự kiện bảo mật. Với thay đổi quan trọng, cần quyết định việc thu hồi hoặc đánh giá lại các session đang hoạt động.

### 4.4. Tạm ngưng, khôi phục và đóng account

Tạm ngưng có thể do chính sách, yêu cầu chủ account hoặc dấu hiệu chiếm quyền. Cần xác định phiên đã cấp có bị vô hiệu hóa ngay không, token tự xác minh còn hiệu lực bao lâu và hệ thống nào kiểm tra trạng thái. Khôi phục account từ SUSPENDED phải theo quy trình xác minh và phê duyệt tương ứng, không chỉ đổi cờ trạng thái.

Đóng account cần chính sách về thời gian lưu dữ liệu, quan hệ sở hữu, thu hồi credential/session và quy định pháp lý áp dụng. **Soft delete** có thể hỗ trợ khôi phục hoặc lưu bằng chứng giao dịch; điều đó không có nghĩa account đã đóng vẫn được đăng nhập hoặc dùng token cũ.

## 5. Account tham gia luồng xác thực như thế nào?

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant C as Trình duyệt
    participant A as Dịch vụ xác thực
    participant DB as Account / credential store
    participant API as API StudyHub

    U->>C: Chọn đăng nhập
    C->>A: Gửi yêu cầu xác thực qua HTTPS
    A->>DB: Tìm credential, account và trạng thái
    DB-->>A: Bản ghi phục vụ xác minh
    A->>A: Kiểm chứng credential / MFA cần thiết
    A->>DB: Kiểm tra account, ghi nhận sự kiện
    A-->>C: Cấp session hoặc token phù hợp
    C->>API: Gửi request với session / token
    API->>API: Kiểm tra phiên/token, trạng thái và quyền
    API-->>C: Kết quả truy cập tài nguyên
~~~

Sơ đồ đã giản lược các bước giao thức. Với passkey, authenticator ký challenge và server kiểm tra chữ ký; với OIDC, người dùng có thể được chuyển hướng tới nhà cung cấp danh tính ngoài. Điểm chung là **hệ thống chỉ tạo ngữ cảnh account sau khi kiểm tra đầy đủ bằng chứng và các ràng buộc liên quan**.

### Ví dụ: Một account, nhiều cách đăng nhập

~~~text
Account: acc_7f32...
Status: ACTIVE
Email: minh@study.example (đã xác minh)
Credential A: password verifier + TOTP
Credential B: passkey trên thiết bị của Minh
External identity: (issuer=https://idp.school.example, sub=opaque-123)
Sessions: trình duyệt laptop; ứng dụng di động
Memberships: learner của tổ chức X
~~~

Giả sử Minh mất điện thoại. Khi thu hồi passkey trên thiết bị đó, **account ID và dữ liệu học tập không đổi**; credential dự phòng hợp lệ vẫn có thể giúp Minh đăng nhập nếu hệ thống cho phép. Nhưng xóa passkey hay thay MFA phải là thao tác được xác thực/khôi phục an toàn. Nếu mất tất cả phương thức, account cần **quy trình recovery** phù hợp thay vì bỏ qua xác thực.

## 6. Account và liên kết danh tính từ bên ngoài

Đăng nhập qua hệ thống SSO đặt ra câu hỏi: **account nội bộ nào tương ứng với danh tính được bên ngoài xác thực?**

Trong OpenID Connect (OIDC), ứng dụng kiểm tra ID token và ngữ cảnh luồng theo giao thức, gồm issuer, audience, chữ ký, thời hạn và nonce khi áp dụng. Hệ thống sau đó ánh xạ **cặp issuer + sub** đáng tin cậy sang account nội bộ. Sub chỉ có ý nghĩa trong phạm vi issuer; không giả định cùng một chuỗi sub ở hai issuer luôn cùng người.

| Tình huống | Cách xử lý an toàn |
| --- | --- |
| Cặp issuer + subject đã liên kết account A | Đăng nhập vào A theo chính sách ứng dụng. |
| Chưa có liên kết | Áp dụng quy trình tạo account hoặc liên kết đã thiết kế. |
| Email trong claim trùng email account B | **Không tự động liên kết chỉ dựa vào email.** Cần bằng chứng kiểm soát B và luồng liên kết an toàn. |
| Người dùng gắn thêm IdP | Yêu cầu phiên có độ bảo đảm phù hợp hoặc xác thực lại, kiểm tra tính duy nhất và ghi audit. |
| IdP không còn đáng tin | Dừng sử dụng liên kết theo chính sách; xử lý phiên, account và phương thức dự phòng phù hợp. |

**OAuth 2.0 khác OIDC:** OAuth 2.0 chủ yếu tập trung vào ủy quyền truy cập; chỉ thấy access token không đủ để kết luận danh tính account. OIDC bổ sung lớp xác thực và cách diễn giải danh tính từ OpenID Provider. Dù đăng nhập liên kết, **ứng dụng vẫn phải kiểm tra quyền truy cập tài nguyên trong ngữ cảnh của mình**.

## 7. Ranh giới tin cậy và những rủi ro của account

Quản lý account đi qua các ranh giới: người dùng ↔ trình duyệt, trình duyệt ↔ dịch vụ xác thực, dịch vụ ↔ kho credential, ứng dụng ↔ IdP và người dùng ↔ bộ phận hỗ trợ/khôi phục. Những ranh giới này xác định nơi cần kiểm chứng yêu cầu và kiểm soát thay đổi.

| Rủi ro | Sai lầm thiết kế | Nguyên tắc phòng vệ |
| --- | --- | --- |
| **Account enumeration** | API cho biết email nào có account hoặc thời gian phản hồi quá khác biệt. | Thông báo phù hợp ngữ cảnh, giảm tín hiệu rò rỉ; giới hạn yêu cầu. |
| **Account takeover** | Chỉ cần biết email đã thêm được credential hay đổi số điện thoại. | Xác thực lại, chống CSRF, kiểm tra quyền, thông báo thay đổi nhạy cảm. |
| **Credential stuffing** | Không giới hạn thử mật khẩu rò rỉ và không theo dõi bất thường. | Rate limiting đa tín hiệu, phát hiện lạm dụng, MFA/passkey theo rủi ro. |
| **Phishing / replay** | OTP hoặc token không ràng buộc giao dịch, challenge dùng lại. | Phương thức chống phishing như WebAuthn, challenge ngắn hạn, chống replay. |
| **Liên kết sai account** | Gộp account OIDC theo email trùng hoặc tin IdP không mong đợi. | Kiểm tra giao thức, issuer + subject và thủ tục liên kết có xác thực. |
| **Broken access control** | API tin account ID, tenant ID hoặc role do client gửi. | Lấy danh tính từ phiên/token đã xác minh, kiểm tra quyền ở server. |
| **Session hijacking** | Token/cookie lộ hoặc vẫn hợp lệ sau khi khóa account. | Bảo vệ cookie, chống XSS/CSRF, timeout, thu hồi và đánh giá trạng thái. |
| **Recovery bypass** | Đường quên mật khẩu yếu hơn toàn bộ yêu cầu đăng nhập. | Token khôi phục một lần, giới hạn thử, bằng chứng phù hợp. |
| **Cross-tenant leakage** | Account thuộc tổ chức X xem được dữ liệu tổ chức Y. | Kiểm tra membership và tài nguyên mỗi lần truy cập; không chỉ role toàn cục. |

### 7.1. API không được tin account ID người gọi tự gửi

Ví dụ API nhận GET /accounts/{accountId}/profile. Nếu server chỉ tìm dữ liệu theo accountId trong URL, người dùng đã đăng nhập có thể thử ID khác và đọc hồ sơ sai. Server phải xác định **account thực của caller** từ phiên/token hợp lệ, sau đó kiểm tra quyền đối với accountId được yêu cầu.

~~~text
request GET /accounts/acc_B/profile
  principal = verifySessionOrToken(request)
  require principal.authenticated
  require accountIsAllowed(principal.accountId)
  require canReadProfile(principal, targetAccountId="acc_B")
  return selectedProfileFields
~~~

Đây là mã giả mô tả phân quyền, chưa phải xử lý hoàn chỉnh. Quy tắc “chỉ được xem hồ sơ của mình” hoặc “giảng viên được xem hồ sơ học viên trong lớp” phải do nghiệp vụ xác định và kiểm tra phía server.

## 8. Các bất biến nên giữ khi thiết kế account

**Bất biến** là điều kiện hệ thống phải đảm bảo ngay cả khi có request đồng thời, lỗi mạng hoặc thao tác chạy lại.

1. **Account ID ổn định** và client không thể sửa ID để chiếm dữ liệu account khác.
2. **Identifier hoặc liên kết danh tính ánh xạ theo quy tắc rõ ràng.** Tính duy nhất phải được bảo vệ ở lớp dữ liệu khi thích hợp, không chỉ kiểm tra trước lúc ghi.
3. **Chỉ quy trình có xác thực và phân quyền thích hợp được thêm, xóa hoặc thay credential.**
4. **Credential đã thu hồi không thể tạo phiên mới.** Account bị vô hiệu hóa cần kiểm soát cả session và token đã phát hành theo chính sách.
5. **Trạng thái account, xác thực và quyền là ba kiểm tra riêng.** Account ACTIVE không chứng minh request có credential hợp lệ; session hợp lệ không cấp quyền trên mọi tài nguyên.
6. **Khôi phục account không trở thành cửa sau dễ bị chiếm quyền** qua email, support hoặc thiết bị dự phòng.
7. **Thay đổi nhạy cảm có audit phù hợp** (người yêu cầu, phương thức xác thực, thời gian, kết quả) mà không ghi password, secret MFA, private key hoặc token thô trong log.

Một bất biến quan trọng là **hệ thống không âm thầm làm người dùng mất phương thức khôi phục cuối cùng**. Có thể chặn xóa credential cuối cùng hoặc yêu cầu quy trình thay thế an toàn; lựa chọn phụ thuộc chính sách sản phẩm.

## 9. Bài thực hành: Thiết kế account cho StudyHub

**Yêu cầu giả định:** StudyHub hỗ trợ học viên, giảng viên, quản trị viên và một worker tạo báo cáo tự động. Học viên có thể đăng nhập bằng mật khẩu + MFA hoặc passkey. Giảng viên có thể liên kết IdP trường học. Người dùng có thể thuộc nhiều tổ chức với vai trò khác nhau.

### Bước 1: Vẽ mô hình

Tạo lược đồ với Account, Identifier, Credential, ExternalIdentity, Session, Organization và Membership. Xác định khóa chính, khóa ngoại, ràng buộc duy nhất. Giải thích vì sao email không thay account ID, và vì sao role nên gắn với membership khi quyền khác nhau theo tổ chức.

### Bước 2: Mô tả ba luồng

- **Đăng ký:** tạo account PENDING, xác minh kênh liên hệ, ghi danh credential, kích hoạt.
- **Đăng nhập:** kiểm chứng credential/MFA, kiểm tra trạng thái, cấp phiên an toàn, đánh giá quyền khi gọi API.
- **Khôi phục:** xác minh bằng chứng thay thế, thu hồi/đăng ký lại credential, xem xét session còn lại và thông báo bảo mật.

Với mỗi luồng, đánh dấu **chủ thể hành động, thành phần quyết định, trust boundary, tài sản cần bảo vệ**, và điểm có thể bị phishing, replay hoặc lạm dụng.

### Bước 3: Viết tiêu chí chấp nhận

| Kiểm thử | Kết quả mong đợi |
| --- | --- |
| Minh thay email đã xác minh | Account ID và lịch sử học tập không đổi; email mới cần xác minh theo chính sách. |
| Minh thêm passkey từ phiên bị đánh cắp nhưng không đáp ứng xác thực lại | Server từ chối thay đổi credential. |
| Hai request đồng thời đòi liên kết cùng external identity | Kết quả tuân theo ràng buộc duy nhất; không ghép ngầm hai account. |
| Account ACTIVE nhưng không có session hợp lệ truy cập API | Server từ chối. |
| Học viên tổ chức A đọc tài nguyên riêng của B | Server từ chối theo quyền và tenant. |
| Credential đã thu hồi dùng để đăng nhập | Không cấp phiên mới. |
| Account bị tạm ngưng nhưng token cũ chưa hết hạn | Hệ thống áp dụng chính sách kiểm tra trạng thái/thu hồi; ghi rõ giới hạn nếu token tự xác minh. |
| Link khôi phục đã dùng được gửi lại | Link không còn hiệu lực. |
| Worker có danh tính hợp lệ gọi API quản trị người dùng | Bị từ chối nếu không có quyền tương ứng. |

### Bước 4: Tự giải thích thiết kế

Trình bày: (1) **Account giữ trạng thái gì?** (2) **Credential chứng minh điều gì?** (3) **Ai có quyền đổi credential?** (4) **Vì sao session hợp lệ vẫn phải kiểm tra quyền?** (5) **Nếu account bị đóng hoặc IdP ngừng được tin cậy, điều gì xảy ra với phiên và liên kết danh tính?**

## 10. Ghi nhớ

**Account là đối tượng quản lý liên tục của hệ thống**, không phải mật khẩu hay email dùng để đăng nhập. Credential được ghi danh để chứng minh quyền kiểm soát account; authentication kiểm chứng credential; session/token mang ngữ cảnh đã xác thực; authorization quyết định tài nguyên nào được truy cập. Thiết kế an toàn cần **ID ổn định, liên kết danh tính chính xác, vòng đời rõ, kiểm soát thay đổi credential, quản lý phiên và đường khôi phục đáng tin cậy**.

Khi học tiếp **mật khẩu, MFA, passkey, chứng chỉ, token, session, liên kết danh tính và khôi phục tài khoản**, hãy luôn hỏi: *credential này chứng minh quyền kiểm soát account nào, trước thành phần nào, với mức bảo đảm nào, và hệ thống xử lý thế nào nếu credential bị mất hoặc bị chiếm quyền?*
