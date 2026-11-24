# Password reuse: rủi ro tái sử dụng mật khẩu trong IAM

## 1. Password reuse là gì?

**Password reuse** (*tái sử dụng mật khẩu*) là việc dùng **cùng một mật khẩu hoặc một biến thể dễ suy đoán** để xác thực tại nhiều tài khoản, ứng dụng, môi trường hoặc giai đoạn khác nhau. Ví dụ, một nhân viên dùng cùng bí mật đăng nhập cho email công ty, công cụ quản lý mã nguồn và tài khoản trên dịch vụ bên ngoài. Nếu một dịch vụ bị lộ thông tin xác thực, các tài khoản khác có thể bị tấn công dù chính những hệ thống đó chưa bị xâm nhập.

Trong **Identity and Access Management (IAM)**, password reuse là vấn đề của **vòng đời phương tiện xác thực**, không chỉ là lời khuyên đặt mật khẩu mạnh. Rủi ro có thể xuất hiện từ ngày **Joiner** tạo tài khoản đầu tiên, tích lũy khi **Mover** được cấp thêm ứng dụng/quyền và tiếp tục tồn tại sau **Leaver** nếu các tài khoản, mật khẩu cục bộ hoặc credential của dịch vụ chưa bị thu hồi.

Cần phân biệt ba hành vi:

- **Dùng lại đúng một bí mật:** cùng mật khẩu cho hai tài khoản không liên quan.
- **Dùng biến thể theo mẫu:** thêm tên ứng dụng, số tăng dần hoặc thay đổi vài ký tự; kẻ tấn công biết một mật khẩu có thể dự đoán những biến thể còn lại.
- **Dùng chung mật khẩu giữa nhiều người:** nhiều nhân viên biết mật khẩu của cùng một tài khoản. Đây là vấn đề *shared credentials*; không hoàn toàn đồng nghĩa reuse, nhưng cũng làm mất khả năng quy trách nhiệm và thu hồi theo từng người.

**Mục tiêu bài học:** xác định những đường lan truyền rủi ro do reuse, phân biệt các phương thức tấn công, kiểm soát bằng mật khẩu riêng biệt, password manager, MFA/phương thức chống phishing, IdP/SSO, đồng bộ SCIM, và phát hiện truy cập tồn dư bằng đối soát tài khoản.

## 2. Vì sao một mật khẩu bị lộ ảnh hưởng nhiều tài khoản?

Mật khẩu là một **shared secret** giữa người sử dụng và cơ chế xác minh tương ứng. Nếu kẻ tấn công có một cặp thông tin đăng nhập bị lộ ở nguồn A, họ có thể thử đăng nhập ở nguồn B bằng cùng thông tin hoặc biến thể gần giống. Không cần xâm nhập hệ thống B để tận dụng sự tái sử dụng này.

~~~mermaid
flowchart TD
    A["Người dùng dùng cùng mật khẩu<br/>cho dịch vụ ngoài và tài khoản công việc"] --> B["Một dịch vụ bị lộ credential"]
    B --> C["Kẻ tấn công có cặp định danh / mật khẩu"]
    C --> D["Thử đăng nhập vào IdP hoặc ứng dụng khác"]
    D --> E{"Đường xác thực còn chấp nhận?"}
    E -->|"Không"| F["Chặn, ghi nhận và điều tra theo rủi ro"]
    E -->|"Có"| G["Có thể chiếm phiên hoặc tài khoản"]
    G --> H["Truy cập dữ liệu theo quyền của tài khoản"]
    H --> I["Có thể mở rộng tác động nếu quyền quá rộng"]
~~~

Hệ quả phụ thuộc nhiều yếu tố: email/tên đăng nhập có tương ứng không, tài khoản có MFA hay passkey, IdP có giám sát đăng nhập bất thường không, resource server thực thi quyền gì và credential còn hiệu lực không.

**Mật khẩu mạnh nhưng bị dùng lại vẫn có rủi ro.** Độ dài và tính khó đoán giảm nguy cơ dò mật khẩu từ đầu; chúng không ngăn một mật khẩu đã bị lộ ở nơi khác được thử lại nguyên vẹn.

### Ví dụ với ba hệ thống

| Hệ thống | Tài khoản | Tình trạng | Tác động khi dùng lại mật khẩu |
| --- | --- | --- | --- |
| Diễn đàn ngoài công ty | Tài khoản cá nhân | Cơ sở dữ liệu credential bị lộ | Có thể trở thành nguồn bí mật bị lộ |
| IdP doanh nghiệp | Tài khoản nhân viên | Có quyền SSO vào nhiều ứng dụng | Tấn công đăng nhập có thể ảnh hưởng nhiều ứng dụng |
| Kho mã nguồn | Tài khoản cục bộ | Không liên kết IdP/MFA đầy đủ | Có thể là đường truy cập khác dù IdP đã được bảo vệ |

Rủi ro tăng khi quyền truy cập rộng hoặc có nhiều tài khoản nằm ngoài vòng quản lý IAM. Vì vậy cần kết hợp **bảo vệ bí mật** với **quản trị entitlement, trạng thái tài khoản và truy cập tại hệ thống đích**.

## 3. Phân biệt các kiểu tấn công liên quan đến mật khẩu

| Kỹ thuật | Cách hoạt động ở mức khái niệm | Liên hệ với password reuse | Kiểm soát trọng tâm |
| --- | --- | --- | --- |
| **Credential stuffing** | Sử dụng nhiều cặp định danh/mật khẩu đã bị lộ để thử trên dịch vụ khác | **Trực tiếp tận dụng reuse** giữa các tài khoản | Mật khẩu riêng, MFA chống phishing, phát hiện tự động hóa |
| **Password spraying** | Thử một hoặc vài mật khẩu phổ biến trên nhiều tài khoản | Không cần biết mật khẩu đã lộ của một người | Chặn mật khẩu phổ biến, rate limit và phát hiện đăng nhập bất thường |
| **Brute-force guessing** | Đoán nhiều giá trị bí mật đối với một tài khoản/nhóm đích | Có thể tận dụng các biến thể yếu | Giới hạn thử, mật khẩu dài và kiểm soát rủi ro |
| **Phishing** | Lừa chủ thể cung cấp bí mật hoặc xác thực tại điểm giả mạo | Mật khẩu bị lấy có thể được thử trên nhiều nơi | Passkey/WebAuthn, giáo dục, bảo vệ đăng nhập |
| **Password database compromise** | Kẻ tấn công có bản lưu xác minh mật khẩu từ hệ thống | Có thể dẫn tới lộ mật khẩu được tái sử dụng nếu bí mật bị khôi phục | Băm mật khẩu đúng cách, salt, kiểm soát dữ liệu |
| **Shared-account misuse** | Nhiều người sử dụng cùng account/bí mật | Không phải reuse xuyên dịch vụ nhưng làm mất tính cá nhân hóa | Account riêng, phân quyền và quản trị đặc quyền |

Không nên gộp mọi đăng nhập thất bại thành “credential stuffing”. Các chiến dịch tấn công và lỗi người dùng có dấu hiệu khác nhau; **phân loại đúng giúp chọn biện pháp và tránh làm khóa nhầm hàng loạt nhân viên hợp lệ**.

## 4. Những nguồn dẫn tới tái sử dụng mật khẩu trong doanh nghiệp

1. **Quá nhiều tài khoản cục bộ:** cùng một nhân viên phải nhớ nhiều mật khẩu ở những ứng dụng chưa dùng SSO.
2. **Quy trình onboarding thủ công:** tài khoản mới được cấp mật khẩu mặc định giống nhau hoặc nhân viên tự đặt lại bằng bí mật quen thuộc.
3. **Ứng dụng cũ (*legacy*):** vẫn sử dụng local login song song với IdP dù doanh nghiệp đã triển khai SSO.
4. **Tài khoản đặc quyền:** mật khẩu quản trị bị dùng lại trên nhiều máy chủ, môi trường hoặc hệ thống.
5. **Chia sẻ bí mật qua tài liệu/ticket:** bí mật được sao chép và được nhiều người sử dụng.
6. **Thói quen thay đổi theo chu kỳ:** người dùng đổi hậu tố hoặc số nhưng giữ mẫu gốc vì phải thay thường xuyên.
7. **Tài khoản dịch vụ:** một password hoặc secret được cấu hình cho nhiều workload, môi trường và dịch vụ.
8. **Tuyển dụng lại (*rehire*):** credential cũ vô tình được kích hoạt lại, gây nguy cơ kế thừa phiên hoặc quyền trước đây.

Mỗi nguyên nhân cần hướng xử lý khác nhau. Với người dùng, có thể ưu tiên password manager và passkeys. Với workload, cần **danh tính máy riêng, secret manager, credential ngắn hạn hoặc cơ chế federation** thay vì yêu cầu bot dùng mật khẩu của nhân viên.

## 5. Password reuse khác gì với một mật khẩu yếu?

Hai rủi ro có thể cùng xuất hiện nhưng cần đánh giá riêng:

| Tình huống | Có reuse? | Có thể là mật khẩu dễ đoán? | Nhận xét |
| --- | --- | --- | --- |
| Một mật khẩu dài, ngẫu nhiên dùng cho hai dịch vụ | Có | Không nhất thiết | Nếu bị lộ ở một nơi, nơi còn lại có nguy cơ |
| Mật khẩu phổ biến chỉ dùng ở một dịch vụ | Không | Có | Dễ bị đoán hoặc spraying |
| Các mật khẩu khác nhau nhờ đổi một ký tự/hậu tố | Có tính tái sử dụng theo mẫu | Có thể | Một bí mật bị lộ giúp suy đoán bí mật khác |
| Các mật khẩu ngẫu nhiên độc lập do manager tạo | Không theo thiết kế | Rất khó đoán nếu đủ độ dài | Giảm rủi ro lan truyền giữa dịch vụ |
| Passkey riêng theo RP/origin | Không dùng mật khẩu chia sẻ theo cách truyền thống | Không áp dụng theo cùng nghĩa | Cơ chế khóa bất đối xứng và ràng buộc origin |

Hướng thiết kế tốt không phải bắt người dùng nghĩ ra nhiều “quy tắc biến đổi” mật khẩu. **Mỗi tài khoản nên có bí mật dài, khó đoán và độc lập** nếu ứng dụng còn cần password; việc tạo và lưu có thể giao cho password manager.

## 6. Nguyên tắc phòng ngừa cho người dùng

### 6.1. Mỗi tài khoản một mật khẩu riêng

Không dùng mật khẩu của email cá nhân cho tài khoản công việc; không dùng mật khẩu IdP cho ứng dụng có local login khác; không dùng mật khẩu nhân viên cho tài khoản quản trị, hệ thống CI/CD hoặc dịch vụ bên ngoài.

Sự độc lập quan trọng hơn việc ghi nhớ một công thức. Ví dụ, mẫu “tên hệ thống + mật khẩu gốc” vẫn có thể bị dự đoán sau một lần rò rỉ; trong khi mật khẩu được sinh ngẫu nhiên và riêng cho từng dịch vụ không có mối liên hệ dễ khai thác.

### 6.2. Dùng password manager

Một password manager đáng tin cậy có thể tạo và điền mật khẩu ngẫu nhiên độc lập cho từng site hoặc account, giảm gánh nặng ghi nhớ. Cần có:

- Phương án bảo vệ vault: mật khẩu chính mạnh, duy nhất và MFA/phương thức thích hợp khi có hỗ trợ.
- Quy trình kiểm soát thiết bị, phục hồi tài khoản và chia sẻ credential theo chính sách tổ chức.
- Ràng buộc điền thông tin theo **đúng tên miền**, cảnh báo khi chuyển sang website giả mạo.
- Chính sách tách tài khoản cá nhân và công việc, quy định dữ liệu nào được phép đồng bộ hoặc chia sẻ.
- Kế hoạch thu hồi quyền truy cập vault khi nhân viên rời tổ chức hoặc đổi nhóm.

Password manager giúp **giảm** reuse nhưng không tự bảo đảm an toàn tuyệt đối: phishing, thiết bị bị chiếm quyền, recovery yếu hoặc vault bị chia sẻ sai vẫn có thể gây sự cố.

### 6.3. Ưu tiên xác thực chống phishing khi hỗ trợ

**Passkey/WebAuthn** dùng mật mã khóa công khai và ràng buộc với relying party (RP)/origin, giúp tránh việc nhập cùng shared secret ở nhiều website. Khi được thiết kế và kiểm chứng đúng, đây là lựa chọn có tính **phishing-resistant**. Mỗi ứng dụng cần kiểm tra các điều kiện thích hợp như RP ID, origin, challenge, chữ ký và user verification khi chính sách yêu cầu.

Nếu vẫn phải dùng mật khẩu, **MFA** cung cấp lớp bảo vệ bổ sung. Tuy nhiên, mật khẩu cộng mã TOTP hoặc SMS không tự tạo thành phương thức chống phishing; mã OTP có thể bị chuyển tiếp theo thời gian thực. Với tài khoản nhạy cảm hoặc đặc quyền, cần cân nhắc authenticator chống phishing theo chính sách.

## 7. Chính sách mật khẩu giúp giảm reuse như thế nào?

Một chính sách tốt cần giảm động lực dùng các mẫu dễ đoán và bảo vệ đăng nhập thực tế.

| Quy tắc thiết kế | Mục đích | Lưu ý triển khai |
| --- | --- | --- |
| **Ưu tiên độ dài và khả năng dùng passphrase** | Tăng độ khó đoán | Hỗ trợ chuỗi dài phù hợp; không bắt người dùng nghĩ ra biến thể phức tạp |
| **Không bắt quy tắc tổ hợp ký tự máy móc khi không cần thiết** | Tránh tạo mẫu dễ dự đoán | Chính sách phải theo yêu cầu tổ chức và chuẩn áp dụng |
| **Cho phép paste và password manager** | Khuyến khích mật khẩu ngẫu nhiên riêng biệt | Không chặn tự động điền hoặc dán vô lý |
| **Chặn mật khẩu phổ biến hoặc đã bị lộ** | Giảm khả năng dùng bí mật đã nằm trong tập tấn công | Dùng kiểm tra bảo vệ quyền riêng tư, không gửi plaintext tùy tiện |
| **Không ép thay định kỳ vô lý khi không có dấu hiệu rủi ro** | Tránh người dùng chỉ tăng số ở cuối mật khẩu | Thay ngay khi có dấu hiệu lộ hoặc theo yêu cầu bảo mật thực tế |
| **Giới hạn đoán mật khẩu** | Hạn chế brute-force và spraying | Rate limit, phát hiện bot và bảo vệ khỏi tấn công khóa tài khoản |
| **Hỗ trợ MFA/phương thức chống phishing** | Giảm tác động khi mật khẩu bị lộ | Không thay cho thu hồi account, token và quyền |
| **Khôi phục tài khoản an toàn** | Ngăn kẻ tấn công đổi mật khẩu qua quy trình yếu | Có identity proofing và kiểm toán khi cần |

**Không thể xác nhận chắc chắn rằng hai mật khẩu ở hai nhà cung cấp khác nhau có trùng nhau chỉ bằng cách xem hash**. Mỗi dịch vụ có thể dùng salt, thuật toán, tham số và mô hình lưu trữ khác nhau. IAM không nên đòi thu thập plaintext từ nhiều hệ thống chỉ để “kiểm tra reuse”; cách an toàn hơn là giảm nhu cầu dùng password và kiểm tra những bí mật đã bị lộ với quy trình bảo vệ phù hợp.

## 8. Lưu trữ và xác minh mật khẩu ở hệ thống đích

Nếu một ứng dụng buộc phải dùng mật khẩu cục bộ, an toàn lưu trữ vẫn là lớp phòng vệ quan trọng. Mỗi password cần được xác minh qua **password hashing chuyên dụng** như Argon2id (khi phù hợp), scrypt, bcrypt hoặc PBKDF2 với tham số được lựa chọn và cập nhật theo chuẩn/chính sách của môi trường.

Các điểm cốt lõi:

- **Salt duy nhất và ngẫu nhiên** cho từng bản ghi theo thuật toán sử dụng; hạn chế khả năng khai thác bảng tra cứu sẵn và các hash trùng nhau.
- **Chi phí tính toán phù hợp**, có kiểm soát hiệu năng và kế hoạch nâng cấp tham số theo thời gian.
- **Không lưu plaintext**, không mã hóa có thể giải ngược rồi xem đó là cơ chế thay thế hash chuyên dụng nếu không có yêu cầu thiết kế đặc biệt.
- **Không ghi mật khẩu vào log, URL, analytics, ticket hoặc trace**.
- Có thể đánh giá **pepper** được quản lý tách khỏi kho hash khi phù hợp với thiết kế bảo mật, nhưng không coi pepper là thay thế salt và thuật toán hash đúng.
- Xác thực qua kết nối bảo mật và có biện pháp chống thử sai, giám sát truy cập bất thường.

Salt và hash mạnh **không ngăn password reuse giữa nhiều hệ thống**, nhưng chúng giảm khả năng biến một vụ lộ kho xác minh thành mật khẩu rõ có thể đem đi thử ở nơi khác. Nếu plaintext đã bị lộ qua phishing, malware hoặc log, hashing của hệ thống không giải quyết được vụ lộ đó.

## 9. Kiểm tra mật khẩu bị lộ và giới hạn quyền riêng tư

Khi người dùng tạo hoặc thay đổi mật khẩu, hệ thống có thể kiểm tra xem nó thuộc **tập mật khẩu đã bị lộ hoặc rất phổ biến** hay không. Mục tiêu là không chấp nhận một bí mật có khả năng đã được kẻ tấn công biết.

Những nguyên tắc vận hành:

1. Thực hiện kiểm tra qua cơ chế **được tổ chức phê duyệt**, không truyền plaintext tới dịch vụ bên ngoài không đáng tin cậy.
2. Có thể dùng tập dữ liệu cục bộ, cơ chế truy vấn bảo vệ thông tin hoặc phương án giảm lộ dữ liệu phù hợp.
3. Không log plaintext hay kết quả có thể khôi phục được mật khẩu của người dùng.
4. Kết quả “không tìm thấy trong tập bị lộ” **không chứng minh** mật khẩu chưa từng được dùng ở hệ thống khác.
5. Khi phát hiện mật khẩu nằm trong tập rò rỉ, yêu cầu chọn **mật khẩu mới, độc lập**, đồng thời xem xét bảo vệ tài khoản và phiên hiện có theo mức rủi ro.

Tập mật khẩu bị lộ có thể không đầy đủ, có độ trễ cập nhật và không thể quan sát mọi mật khẩu ngoài Internet. Bởi vậy, đây chỉ là **một tín hiệu phòng vệ**, không phải phương pháp xác nhận tuyệt đối về reuse.

## 10. IdP và SSO: giảm số mật khẩu, không xóa mọi rủi ro

**IdP (Identity Provider)** quản lý xác thực tập trung; **Single Sign-On (SSO)** cho phép nhiều ứng dụng tin vào kết quả xác thực do IdP cung cấp thông qua các giao thức như OIDC hoặc SAML khi triển khai phù hợp. Khi người dùng không phải tự đặt mật khẩu cục bộ cho mỗi ứng dụng, khả năng reuse và việc quản lý nhiều bí mật sẽ giảm.

Tuy nhiên:

- **Mật khẩu IdP trở thành credential quan trọng** vì có thể mở nhiều ứng dụng. Nếu bị lộ, tác động có thể rộng.
- Ứng dụng có thể vẫn cho phép **đăng nhập local/fallback** độc lập; đường này cần kiểm kê và bảo vệ.
- SSO **không tự loại bỏ** PAT, API key, khóa SSH hoặc session riêng của ứng dụng.
- Một IdP password mạnh vẫn cần kiểm soát đánh cắp phiên, MFA, phishing và recovery.
- Ứng dụng chỉ nên chấp nhận assertion/token từ issuer tin cậy, kiểm tra chữ ký, audience, thời hạn và ngữ cảnh theo giao thức.

### Vai trò của SCIM

**SCIM (System for Cross-domain Identity Management)** giúp đồng bộ user và group tới ứng dụng có hỗ trợ, từ đó giảm nhu cầu tạo account cục bộ thủ công. Tuy nhiên **SCIM không tự quản lý mọi mật khẩu cục bộ, token hoặc phiên**. Khi deprovisioning, cần kiểm tra account ứng dụng và những đường xác thực riêng, không chỉ phản hồi SCIM thành công.

~~~mermaid
flowchart LR
    HR["HRIS / nguồn bảo trợ"] --> IAM["IAM: vòng đời, chính sách và phê duyệt"]
    IAM --> IDP["IdP: xác thực, MFA / passkey"]
    IDP -->|"SSO"| A["Ứng dụng A"]
    IDP -->|"SSO"| B["Ứng dụng B"]
    IDP -->|"SCIM / API khi hỗ trợ"| P["Provisioning tài khoản / nhóm"]
    P --> A
    P --> B
    IAM --> C["Ứng dụng C có local account"]
    C --> R["Đối soát local password / PAT / quyền"]
    A --> R
    B --> R
~~~

## 11. RBAC/ABAC và tác động sau khi credential bị chiếm

Password reuse liên quan trực tiếp tới **authentication**, nhưng mức độ tổn thất còn tùy **authorization**. Nếu tài khoản bị chiếm có role quản trị hoặc quyền truy cập dữ liệu rộng, sự cố có thể nghiêm trọng hơn một tài khoản chỉ đọc thông tin ít nhạy cảm.

**RBAC (Role-Based Access Control)** cấp quyền theo role; **ABAC (Attribute-Based Access Control)** dùng thuộc tính chủ thể, tài nguyên và ngữ cảnh. Hai mô hình cần được thực thi ở backend/API để giới hạn hành động sau khi đăng nhập.

Ví dụ, nhân viên thuộc organization A không mặc nhiên có quyền đọc mọi tài liệu A. Dù kẻ tấn công đã xác thực bằng mật khẩu đúng, API vẫn phải kiểm tra role, resource scope, phân loại dữ liệu và điều kiện chính sách. **Đăng nhập thành công không đồng nghĩa có quyền truy cập mọi tài nguyên.**

Nguyên tắc phòng vệ nhiều lớp:

- Dùng **least privilege** khi cấp role/entitlement ban đầu.
- Tách tài khoản thông thường và tài khoản đặc quyền khi chính sách yêu cầu.
- Với hành động nhạy cảm, yêu cầu **step-up** hoặc xác thực chống phishing phù hợp.
- Giảm quyền trực tiếp/ACL không kiểm soát và rà soát quyền kế thừa.
- Có thể áp dụng kiểm tra ngữ cảnh/rủi ro, nhưng không dùng tín hiệu vị trí hoặc thiết bị làm căn cứ duy nhất.
- Nếu xác nhận credential bị lộ, không chỉ đổi mật khẩu: cần xem xét session/token và hành vi đã thực hiện.

## 12. Password reuse trong Joiner lifecycle

Khi người dùng mới gia nhập, quy trình **Joiner** thường bao gồm xác minh danh tính, tạo account và cấp quyền ban đầu. Đây là thời điểm tốt để **ngăn reuse ngay từ đầu**.

Một quy trình mẫu:

1. HRIS hoặc nguồn bảo trợ xác nhận người, loại quan hệ lao động, organization, ngày bắt đầu và thời hạn.
2. IAM liên kết person/worker/identity bằng ID đáng tin cậy, tránh tạo trùng hoặc nối nhầm account.
3. Tạo IdP account theo chính sách; ưu tiên passkey/phương thức chống phishing khi thích hợp.
4. Nếu cần mật khẩu, yêu cầu **bí mật độc lập**, có độ dài phù hợp; không phát mật khẩu dùng chung cho nhiều nhân viên.
5. Thiết lập password manager, MFA và kênh recovery an toàn trước khi cấp quyền nhạy cảm.
6. Sử dụng SSO/SCIM để giảm local account, nhưng kiểm tra các ứng dụng không hỗ trợ.
7. Đối soát quyền hiệu lực theo RBAC/ABAC và xác nhận không có tài khoản phụ hay mật khẩu mặc định không quản lý.

### Vấn đề mật khẩu ban đầu

Không nên gửi cùng một mật khẩu khởi tạo cho hàng loạt nhân viên hoặc lưu password tạm thời trong ticket chia sẻ. Một quy trình bootstrap phù hợp có thể dùng đường kích hoạt một lần, thời hạn ngắn, kênh có bảo vệ và bước xác minh danh tính thích hợp. Sau khi được sử dụng, quyền tiếp tục đăng nhập phải gắn với phương tiện chứng thực riêng của chủ thể.

Khi một người đã có account do **rehire**, không tự kích hoạt lại mật khẩu/phiên cũ mà không xác minh danh tính và quyền còn hợp lệ.

## 13. Password reuse trong Mover lifecycle

**Mover** là giai đoạn thay đổi vai trò, phòng ban, dự án, tổ chức hoặc phạm vi trách nhiệm. Người dùng có thể được cấp thêm ứng dụng và quyền đặc biệt; nếu mỗi tài khoản mới lại dùng cùng bí mật, bề mặt lan truyền rủi ro tăng lên.

Ví dụ, một kỹ sư chuyển từ phát triển ứng dụng sang vận hành sản xuất:

| Thay đổi | Rủi ro reuse | Kiểm soát cần thiết |
| --- | --- | --- |
| Cấp tài khoản đặc quyền | Dùng mật khẩu thường cho admin | Tài khoản/credential riêng và MFA chống phishing theo chính sách |
| Bổ sung hệ thống legacy | Người dùng đặt lại mật khẩu quen thuộc | Password manager, quy tắc mật khẩu độc lập, đối soát account |
| Chuyển organization/tenant | Credential cũ vẫn mở tài nguyên cũ | Thu hồi quyền cũ, kiểm tra account/session và local login |
| Chuyển trách nhiệm bot | Dùng secret cá nhân để vận hành bot | Chuyển owner, workload identity và secret được quản lý |

**Chỉ cấp quyền mới mà không thu hồi quyền cũ** dẫn tới *privilege accumulation*. Việc thay mật khẩu, kể cả thành mật khẩu khác, không thay thế bước thu hồi các role, group, entitlement và ACL đã hết căn cứ.

## 14. Password reuse trong Leaver lifecycle

Khi nhân viên hoặc nhà thầu rời tổ chức, IAM cần thu hồi **tất cả đường truy cập gắn với quan hệ làm việc đã kết thúc**, không chỉ khóa một mật khẩu tại IdP.

Các hạng mục cần kiểm tra:

1. **IdP account** và khả năng đăng nhập mới.
2. **Tài khoản cục bộ** trên SaaS/on-premise không đồng bộ với IdP.
3. **Mật khẩu được chia sẻ** mà người nghỉ việc từng biết: cần thay hoặc loại bỏ cơ chế dùng chung.
4. **Session, refresh token, access token và PAT** có thể tiếp tục hoạt động sau khi mật khẩu đổi.
5. **Secret manager, API key, SSH key và workload credential** mà người đó có quyền xem hoặc sao chép.
6. **Entitlement, group, role và ACL** được cấp qua nhiều đường, kể cả quyền dự án cũ.
7. **Quyền của quan hệ khác** nếu người đó vẫn có hợp đồng hợp lệ với một organization khác.

**Đổi mật khẩu không tự chấm dứt session/token đã cấp.** Tùy ứng dụng, cần revoke grant, kết thúc phiên, kiểm tra resource server và đọc lại trạng thái quyền. **SCIM inactive** cũng không chứng minh PAT độc lập của một ứng dụng đã mất hiệu lực.

Nếu một mật khẩu dùng chung giữa nhiều nhân viên, sự kiện Leaver là tín hiệu quan trọng để **loại bỏ shared account hoặc xoay bí mật**; chỉ thay mật khẩu của tài khoản cá nhân rời đi không làm mất kiến thức về shared secret mà họ đã có.

## 15. Tài khoản dịch vụ, workload và mật khẩu dùng chung

Trong tự động hóa, password reuse có thể diễn ra khi nhiều máy chủ, ứng dụng hoặc pipeline cùng dùng một secret. Đây là rủi ro vì một workload bị xâm nhập có thể làm lộ credential tới nhiều tài nguyên khác.

| Mô hình | Rủi ro | Hướng cải thiện |
| --- | --- | --- |
| Cùng một password cho nhiều service account | Một nơi lộ làm ảnh hưởng nhiều dịch vụ | Secret riêng theo workload và môi trường |
| Mật khẩu quản trị chung trên nhiều máy | Dễ lan rộng đặc quyền | Danh tính/credential quản trị riêng, quản lý đặc quyền |
| PAT cá nhân lưu trong pipeline | Bot phụ thuộc tài khoản nhân viên | Workload identity, quyền tối thiểu, hạn và owner rõ |
| Secret lưu cứng trong mã nguồn | Dễ bị sao chép hoặc lan vào artifact/log | Secret manager và cơ chế cấp phát an toàn |
| Credential dài hạn không xoay khi owner đổi | Người cũ có thể giữ bản sao | Chuyển owner, đánh giá khả năng lộ, xoay/thu hồi |
| Workload đã ngừng nhưng secret còn hoạt động | Quyền truy cập tồn dư | Thu hồi identity và credential không còn dùng |

Khi có thể, ưu tiên **workload federation, token ngắn hạn hoặc khóa được quản lý** thay vì password dài hạn. Nếu vẫn bắt buộc dùng password, phải cấp riêng, bảo vệ trong kho secret, giới hạn quyền, quản lý thời hạn và kiểm toán việc sử dụng.

**Không tự động tắt bot sản xuất hợp lệ chỉ vì chủ sở hữu nhân sự nghỉ việc**. Quy trình đúng là xác định owner mới, đánh giá workload và thay credential có nguy cơ lộ; nếu workload không còn nhiệm vụ, thu hồi theo vòng đời riêng.

## 16. Phát hiện, giám sát và phản ứng với rủi ro reuse

Không phải IAM có thể đọc mật khẩu rõ ở mọi ứng dụng để biết chúng trùng nhau. Các tín hiệu có thể khai thác **mà không thu thập plaintext** gồm:

| Tín hiệu | Có thể gợi ý điều gì? | Giới hạn |
| --- | --- | --- |
| Mật khẩu mới thuộc tập đã bị lộ | Bí mật đã có trong nguồn dữ liệu tấn công | Không chứng minh mật khẩu đã dùng ở tài khoản khác |
| Nhiều lần đăng nhập thất bại theo mẫu bot | Có thể là stuffing, spraying hoặc dò đoán | Cần phân biệt với lỗi người dùng và tích hợp |
| Một tài khoản đăng nhập từ ngữ cảnh rủi ro bất thường | Có thể đã bị chiếm credential | Không tự xác nhận nguyên nhân là reuse |
| Account legacy dùng local login không MFA | Đường truy cập dễ bị tấn công lại credential | Chưa chứng minh người dùng đang dùng lại password |
| Shared account có nhiều người sử dụng | Mất khả năng quy trách nhiệm và kiểm soát bí mật | Đây là dùng chung credential, không nhất thiết reuse xuyên dịch vụ |
| Credential xuất hiện trong kho bí mật không quản trị | Khả năng lưu/lan truyền bí mật sai quy trình | Cần điều tra phạm vi thực tế |
| Truy cập sau mốc Leaver | Token, local account hoặc quyền tồn dư | Có thể do nhiều nguyên nhân, không chỉ reuse |

### Quy trình phản ứng khi nghi ngờ mật khẩu đã bị lộ

1. **Xác nhận tín hiệu** và xác định các tài khoản/ứng dụng liên quan theo ID ổn định; không gộp người dùng chỉ vì email trùng.
2. **Giới hạn truy cập theo rủi ro:** áp dụng biện pháp bảo vệ phù hợp đối với tài khoản bị ảnh hưởng và quyền đặc quyền.
3. **Yêu cầu đổi bí mật bị lộ thành giá trị mới, độc lập**; tránh tái sử dụng một biến thể.
4. **Thu hồi session/token/grant** theo khả năng hệ thống, nhất là khi có khả năng tài khoản đã bị sử dụng trái phép.
5. **Kiểm tra entitlement và hoạt động** để phát hiện truy cập hoặc thay đổi bất thường; không kết luận mọi hành động đã an toàn chỉ sau reset mật khẩu.
6. **Đối soát các ứng dụng local**, PAT, account đặc quyền và workload credential có liên quan.
7. **Lưu bằng chứng và kết quả**, phân công owner, theo dõi hệ thống chưa xác minh; thông báo cho người dùng theo kênh phù hợp.

Với sự cố đang diễn ra, các bước có thể tiến hành song song. Không cần chờ đối soát đầy đủ mới áp dụng biện pháp chặn cần thiết theo quy trình ứng phó đã được ủy quyền.

## 17. Kiểm toán, chỉ số và quyền riêng tư

Mục tiêu kiểm toán là chứng minh tổ chức **đã giảm khả năng reuse và xử lý đường truy cập bị ảnh hưởng**, không phải thu thập mật khẩu để so sánh giữa các hệ thống.

Những thông tin cần lưu:

- Identity ID, account ID hoặc tham chiếu mục tiêu **không chứa bí mật**.
- Nguồn có thẩm quyền, chính sách/version và loại sự kiện Joiner–Mover–Leaver.
- Tình trạng áp dụng password manager, phương thức MFA/phishing-resistant ở mức metadata được phép.
- Kết quả kiểm tra mật khẩu bị lộ dưới dạng **tín hiệu chính sách**, không lưu plaintext.
- Sự kiện tạo/đổi/revoke credential, lịch sử phê duyệt, thời điểm và hệ thống đích.
- Kết quả đọc lại tài khoản, session, token và quyền hiệu lực sau remediation.
- Ngoại lệ, owner và thời hạn khắc phục với những hệ thống không thể xác minh.

Chỉ số có thể theo dõi:

| Chỉ số | Mục đích |
| --- | --- |
| Tỷ lệ ứng dụng bắt buộc đã tích hợp SSO | Giảm số local password phải quản trị |
| Số ứng dụng còn local login ngoài chính sách | Phát hiện đường reuse chưa kiểm soát |
| Số mật khẩu mới bị chặn do nằm trong tập lộ | Đo hiệu lực blocklist (không suy thành tỷ lệ reuse) |
| Tỷ lệ account rủi ro cao dùng phương thức chống phishing | Đo mức bảo vệ khi bí mật bị lộ |
| Số shared account hoặc secret không có owner | Tìm credential tồn dư và không thể truy trách nhiệm |
| Thời gian đến khi session/token bị chặn sau sự cố | Đo độ trễ thu hồi quyền thực tế |
| Số local account còn active sau Leaver | Phát hiện sai lệch deprovisioning |
| Số hạng mục remediation chưa được xác minh | Theo dõi khoảng trống kiểm soát |

Các log xác thực có thể chứa địa chỉ IP, device ID và thông tin cá nhân; cần phân quyền, giới hạn thời gian lưu và tránh ghi nguyên token, mật khẩu, seed OTP hoặc secret. Không có một ngưỡng KPI chung phù hợp mọi tổ chức: cần phân loại theo mức nhạy cảm của tài nguyên và loại danh tính.

## 18. Tình huống thực hành: một bí mật, nhiều tài khoản

**Bối cảnh:** Huy là nhân viên phân tích dữ liệu. Huy có account IdP của tổ chức, account cục bộ trên một công cụ báo cáo cũ và account cá nhân trên một dịch vụ ngoài công ty. Huy dùng cùng mật khẩu cho cả ba. Dịch vụ ngoài công ty thông báo đã xảy ra vụ lộ credential; IdP công ty có MFA dạng OTP, còn công cụ báo cáo cũ không có MFA.

### Câu hỏi 1: Đường nào có rủi ro cao?

**Phân tích:** Cả IdP và công cụ báo cáo đều có thể bị thử bằng credential đã lộ. OTP ở IdP giúp tăng bảo vệ nhưng không phải giải pháp chống phishing tuyệt đối; công cụ cục bộ không MFA đặc biệt dễ bị chiếm nếu mật khẩu trùng và thông tin định danh phù hợp.

### Câu hỏi 2: Chỉ thay mật khẩu IdP đã đủ chưa?

**Phân tích:** Chưa. Huy cần đổi những mật khẩu đã dùng lại thành **giá trị riêng biệt**, ưu tiên di chuyển ứng dụng cũ sang SSO/MFA nếu hỗ trợ. Nếu nghi đã có truy cập trái phép, cần kiểm tra session/token và quyền thực tế của cả hai account, không chỉ đổi bí mật của IdP.

### Câu hỏi 3: Vai trò của IdP/SSO/SCIM?

**Phân tích:** SSO giảm nhu cầu dùng local password; SCIM có thể hỗ trợ cập nhật/vô hiệu user/group. Nhưng công cụ báo cáo cũ còn local login thì phải quản lý riêng. Cần đối soát account và entitlement tại ứng dụng đích.

### Câu hỏi 4: Nếu Huy chuyển sang phòng khác?

**Phân tích:** Mover phải đánh giá và thu hồi quyền cũ, cấp quyền mới theo RBAC/ABAC. Mật khẩu riêng giảm lan truyền rủi ro, nhưng không thay thế kiểm soát quyền dự án hoặc ACL trực tiếp.

### Câu hỏi 5: Nếu Huy nghỉ việc?

**Phân tích:** Leaver cần chặn tài khoản IdP, deprovision các ứng dụng liên quan, thu hồi session/token/PAT theo khả năng, chuyển giao secret/workload do Huy quản lý và đối soát quyền hiệu lực. Không được bỏ qua local account chỉ vì IdP đã disabled.

### Câu hỏi 6: Có thể kiểm tra reuse bằng cách tải hash mật khẩu từ từng ứng dụng về một kho tập trung?

**Phân tích:** Không nên dùng cách này. Các hash thường được salt và xử lý khác nhau; tập trung hash tăng rủi ro và không phải phương pháp đáng tin để kết luận reuse xuyên hệ thống. Hãy giảm password cục bộ, áp dụng password manager/passkeys, kiểm tra mật khẩu bị lộ qua phương thức bảo vệ quyền riêng tư và giám sát truy cập.

## 19. Checklist thiết kế chống password reuse

| Câu hỏi | Điều cần có bằng chứng |
| --- | --- |
| Người dùng có đang được yêu cầu nhớ nhiều mật khẩu cục bộ? | Kiểm kê app, kế hoạch SSO hoặc bảo vệ từng tài khoản |
| Mỗi tài khoản còn dùng password có bí mật độc lập? | Chính sách, hướng dẫn password manager; không thu thập plaintext để kiểm tra |
| Mật khẩu mới có bị kiểm tra với tập giá trị phổ biến/đã lộ? | Cơ chế blocklist bảo vệ quyền riêng tư |
| Chính sách có gây biến thể theo chu kỳ? | Tránh bắt đổi vô lý và quy tắc làm người dùng chọn mẫu dễ đoán |
| Đăng nhập có chống tự động đoán? | Rate limit, bot defense, giám sát và xử lý khóa nhầm |
| Account nhạy cảm có MFA chống phishing theo chính sách? | Authenticator phù hợp, binding và xác minh thực tế |
| SSO có còn đường local login/fallback? | Kiểm kê và bảo vệ hoặc vô hiệu theo khả năng |
| App SCIM đã thật sự cập nhật account và quyền? | Đọc lại trạng thái ứng dụng và effective access |
| Joiner có password khởi tạo dùng chung? | Bootstrap riêng, hạn ngắn, không lộ secret |
| Mover có cấp thêm app và quyền đặc quyền? | Credential riêng và thu hồi quyền cũ |
| Leaver có local account, PAT, session còn mở? | Deprovision và xác minh từng target |
| Workload có dùng password chung hoặc PAT cá nhân? | Workload identity, secret riêng, owner và vòng đời |
| Khi có credential bị lộ đã xử lý toàn bộ đường truy cập? | Reset phù hợp, revoke session/token và audit |

## 20. Tổng kết

**Password reuse** biến việc một bí mật bị lộ ở **một** nơi thành nguy cơ chiếm quyền ở **nhiều** nơi. Nó khác với việc mật khẩu ngắn hoặc dễ đoán, nhưng hai rủi ro thường khuếch đại lẫn nhau. Cách giảm reuse hiệu quả là **mật khẩu dài, độc lập cho từng account**, password manager, kiểm tra giá trị đã bị lộ, ưu tiên passkeys/WebAuthn và xác thực phù hợp mức rủi ro, cùng với kiểm soát đăng nhập tự động.

Trong vòng đời **Joiner–Mover–Leaver**, IAM cần kiểm soát mật khẩu từ khi tạo account, đánh giá lại các credential khi cấp vai trò mới và thu hồi tài khoản, phiên, token cùng quyền còn tồn tại khi quan hệ làm việc kết thúc. **IdP/SSO** giảm số mật khẩu cục bộ; **SCIM** hỗ trợ vòng đời user/group; **RBAC/ABAC** giới hạn quyền trên tài nguyên; còn **tài khoản dịch vụ** cần danh tính và secret riêng. Cuối cùng, đối soát tại hệ thống đích và lưu bằng chứng kiểm toán mới giúp chứng minh đã giảm **quyền truy cập tồn dư**.
