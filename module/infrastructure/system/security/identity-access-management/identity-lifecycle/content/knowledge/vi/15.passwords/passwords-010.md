# Kiểm tra chính sách mật khẩu trong IAM

**Kiểm tra chính sách mật khẩu (password policy validation and verification)** là hoạt động xác định, thực thi và kiểm chứng các quy tắc bảo vệ mật khẩu trong toàn bộ vòng đời tài khoản. Một chính sách tốt không chỉ hỏi mật khẩu có đủ dài hay không; nó phải giảm nguy cơ đoán mật khẩu, sử dụng mật khẩu bị lộ, chiếm tài khoản, bỏ qua quy trình đổi mật khẩu và việc các hệ thống áp dụng quy định không nhất quán.

Bài thuộc chương **Mật khẩu** của module **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**. Trong mô hình **Joiner–Mover–Leaver (JML)**, người dùng được xác minh và cấp tài khoản khi gia nhập, có thể thay đổi quyền khi chuyển vai trò, rồi bị thu hồi truy cập khi nghỉ việc. Chính sách mật khẩu kết nối với **IdP/SSO**, MFA, đồng bộ tài khoản qua **SCIM**, **RBAC/ABAC**, tài khoản dịch vụ, quản lý phiên và kiểm toán để giảm **quyền truy cập tồn dư**.

**Tình huống dẫn nhập:** Một nhân viên đăng ký mật khẩu dài nhưng nằm trong danh sách mật khẩu bị lộ; giao diện web từ chối, trong khi API đổi mật khẩu của ứng dụng cũ lại chấp nhận. Hoặc nhân viên nghỉ việc bị khóa SSO nhưng vẫn đăng nhập được bằng mật khẩu cục bộ của SaaS. Cả hai ví dụ cho thấy kiểm tra chính sách phải bao gồm **đúng quy tắc, đúng điểm thực thi và đúng vòng đời**, không chỉ một trường nhập liệu trên trang web.

## 1. Mục tiêu của việc kiểm tra chính sách mật khẩu

Một chương trình quản lý mật khẩu cần đạt đồng thời các mục tiêu:

1. **Chặn mật khẩu dễ đoán hoặc đã bị lộ** ngay ở thời điểm thiết lập hoặc đổi mật khẩu.
2. **Khuyến khích mật khẩu đủ dài, độc nhất**, có thể được tạo và lưu bằng trình quản lý mật khẩu.
3. **Không đặt yêu cầu gây hại**, chẳng hạn bắt đổi mật khẩu định kỳ vô điều kiện hoặc ép các mẫu ký tự phức tạp khó nhớ nhưng dễ đoán.
4. **Bảo vệ mật khẩu trong quá trình xử lý và lưu trữ**, không ghi bản rõ vào hệ thống, log, analytics hoặc mã nguồn.
5. **Ngăn brute force, credential stuffing và account enumeration** tại thời điểm đăng nhập.
6. **Bảo vệ các luồng thay đổi/reset/recovery**, vốn có thể bị lạm dụng để chiếm tài khoản.
7. **Thi hành nhất quán tại các kênh**: IdP, portal web, ứng dụng di động, API, AD/LDAP và công cụ quản trị khi liên quan.
8. **Có bằng chứng kiểm thử và kiểm toán** cho các điều kiện bắt buộc, ngoại lệ, lỗi đồng bộ và sự kiện JML.

Phải phân biệt ba hoạt động:

| Hoạt động | Câu hỏi | Ví dụ điều kiện kiểm tra |
| --- | --- | --- |
| **Password policy validation** | Mật khẩu mới có đáp ứng quy định khi tạo/đổi/reset không? | Độ dài, blocklist, tính hợp lệ của dữ liệu đầu vào. |
| **Password authentication verification** | Mật khẩu người dùng nhập có khớp với credential đã lưu không? | Xác minh hash mật khẩu bằng KDF, giới hạn thử. |
| **Policy compliance verification** | Các hệ thống có thật sự áp cùng chính sách và không có đường bypass không? | Kiểm thử API, admin reset, IdP, hệ thống đích và log. |

**Độ mạnh của mật khẩu không phải một quyền truy cập.** Người dùng nhập đúng mật khẩu vẫn phải đáp ứng chính sách MFA, session và **authorization** theo tài nguyên; ngược lại, nhân viên đã có mật khẩu mạnh nhưng chuyển vai trò hoặc nghỉ việc phải bị thu hồi quyền tương ứng.

## 2. Nguyên tắc chính sách hiện đại

Các khung hướng dẫn như **NIST SP 800-63B** nhấn mạnh việc ưu tiên độ dài, chống mật khẩu phổ biến/bị lộ, bảo vệ quá trình xác thực và giảm gánh nặng không cần thiết cho người dùng. Khi áp dụng một tiêu chuẩn cụ thể, phải xác định **phiên bản và mức bảo đảm** đang được tổ chức phê duyệt; ví dụ dưới đây là mẫu thiết kế, không phải tuyên bố chứng nhận tuân thủ một phiên bản chuẩn.

| Khía cạnh | Thực hành nên ưu tiên | Điều không nên mặc định |
| --- | --- | --- |
| **Độ dài tối thiểu** | Đủ dài theo chính sách và việc mật khẩu được dùng đơn yếu tố hay trong MFA; một số khung hiện đại đặt yêu cầu cao hơn cho đăng nhập chỉ bằng mật khẩu. | Một giới hạn ngắn chỉ vì giao diện cũ không hỗ trợ chuỗi dài. |
| **Độ dài tối đa** | Cho phép mật khẩu dài và passphrase; hỗ trợ ít nhất hàng chục ký tự theo tiêu chuẩn đã chọn. | Cắt ngầm mật khẩu trước khi lưu hoặc trước khi hash. |
| **Blocklist** | Kiểm tra mật khẩu thường gặp, đã bị lộ và các biến thể dễ đoán theo chính sách. | Cho phép mật khẩu vì nó có đủ chữ hoa, số và dấu đặc biệt. |
| **Quy tắc thành phần** | Ưu tiên độ dài và kiểm tra yếu; cho phép ký tự đa dạng, dấu cách và Unicode theo khả năng hệ thống. | Bắt buộc đồng thời chữ hoa, chữ thường, số, ký tự đặc biệt như một biện pháp an toàn duy nhất. |
| **Thay đổi định kỳ** | Yêu cầu đổi khi có dấu hiệu lộ, nghi xâm nhập hoặc lý do bảo mật được xác định. | Ép đổi sau mỗi 30/60/90 ngày mà không có căn cứ rủi ro. |
| **Password history** | Dùng khi chính sách/điều kiện cần nhằm giảm tái sử dụng credential nguy hiểm, với lưu trữ an toàn. | Tin rằng chỉ cấm vài mật khẩu cũ sẽ chặn được các biến thể dễ đoán. |
| **Trải nghiệm nhập** | Cho phép paste/autofill và sử dụng password manager; hỗ trợ hiển thị/tắt hiển thị mật khẩu an toàn. | Chặn paste, yêu cầu nhập lại thủ công nhiều lần hoặc bắt câu hỏi bảo mật dễ đoán. |
| **Xác minh đăng nhập** | Rate limit, bảo vệ trước credential stuffing, theo dõi bất thường. | Chỉ dựa vào quy tắc lúc tạo mật khẩu để bảo vệ brute force. |
| **Lưu trữ** | Hash với password KDF được thiết kế phù hợp, salt ngẫu nhiên riêng từng bản ghi và tham số có thể nâng cấp. | Hash nhanh không salt, mã hóa có thể giải mã làm kho mật khẩu chính hoặc lưu bản rõ. |

Ví dụ khi xây dựng chính sách doanh nghiệp có thể đặt độ dài tối thiểu **15 ký tự cho mật khẩu đóng vai trò yếu tố duy nhất** và **8 ký tự khi được sử dụng cùng MFA**, đồng thời cho phép mật khẩu dài **ít nhất 64 ký tự**, theo định hướng của các khung hiện đại. Đây là **ngưỡng tham khảo để thiết kế và kiểm thử**, không thay thế việc kiểm tra quy định, phiên bản chuẩn và trường hợp đặc biệt của tổ chức.

**Mật khẩu dài nhưng phổ biến vẫn yếu.** Một câu dài đã bị lộ hoặc xuất hiện trong danh sách mật khẩu thông dụng cần bị từ chối, trong khi một passphrase dài, độc nhất và không nằm trong blocklist có thể phù hợp hơn mật khẩu ngắn bị ép chứa đủ loại ký tự.

## 3. Thiết kế một password policy có thể kiểm thử

Chính sách nên mô tả **điều kiện đầu vào**, **quy tắc bắt buộc**, **nguồn blocklist**, **kênh áp dụng**, **cách xử lý lỗi** và **chủ sở hữu**.

~~~yaml
policyId: workforce-password-v4
accountScope: HUMAN
ownerTeam: iam-security
enforcedBy:
  - workforce-idp
  - trusted-password-reset-service
  - delegated-administration-api
rules:
  minimumLengthWithoutMfa: 15
  minimumLengthWithMfa: 8
  supportedLengthAtLeast: 64
  allowSpaces: true
  allowUnicode: true
  allowPasteAndAutofill: true
  requireCompositionClasses: false
  prohibitCommonOrCompromisedPasswords: true
  prohibitContextSpecificObviousPasswords: true
  prohibitRoutineExpiryWithoutRisk: true
security:
  rateLimitAuthenticationAttempts: true
  passwordStorage: ADAPTIVE_SALTED_PASSWORD_KDF
  auditPolicyDecisionsWithoutSecrets: true
  requireProtectedResetFlow: true
governance:
  version: 4
  exceptionApprovalRequired: true
  revalidateOnPasswordSetAndReset: true
~~~

**Đây là pseudoconfiguration** minh họa, không phải schema chạy trực tiếp cho một IdP. Các trường \`WithMfa\` phải phản ánh **thiết kế xác thực thực tế**: không được cho người dùng chỉ chọn một checkbox “Tôi có MFA” ở frontend để được hưởng ngưỡng yếu hơn; chính sách phải biết tài khoản và các đường đăng nhập có thật sự yêu cầu MFA phù hợp hay không.

### Xác định phạm vi chính sách

Một tổ chức có thể cần nhiều profile:

- **Workforce account:** nhân viên, nhà thầu, tài khoản chuyên dụng cho người.
- **Privileged human account:** tài khoản quản trị có MFA chống phishing và quy trình recovery mạnh.
- **Customer account:** người dùng ngoài tổ chức, có nhu cầu hỗ trợ và đánh giá rủi ro khác.
- **Legacy/local account:** hệ thống cũ không hỗ trợ IdP; cần bù trừ và kế hoạch cải tiến.
- **Non-human/service identity:** ưu tiên workload federation, managed identity, mTLS hoặc credential kỹ thuật; không áp quy tắc mật khẩu ghi nhớ cho mọi workload một cách máy móc.

Quy tắc cần nhất quán trong phạm vi được định nghĩa, nhưng không bắt buộc mọi loại danh tính đều phải dùng một password policy giống nhau.

## 4. Kiểm tra độ dài và định dạng đầu vào

Độ dài là điều kiện dễ nhìn thấy nhưng dễ triển khai sai:

1. **Đo bằng quy ước nhất quán** theo tiêu chuẩn và nền tảng, thường là số ký tự/code point thay vì số byte UTF-8.
2. **Hỗ trợ chuỗi dài** để người dùng sử dụng passphrase và password manager.
3. **Không tự cắt (truncate)** phần mật khẩu vượt giới hạn. Nếu có giới hạn kỹ thuật hợp lý, phải từ chối có giải thích thay vì hash một tiền tố.
4. **Cho phép dấu cách và ký tự đa dạng** khi thành phần xác thực thực sự hỗ trợ nhất quán.
5. **Không tự trim** dấu cách đầu/cuối nếu chính sách không cho phép: \`" passphrase "\` khác \`"passphrase"\` nếu hệ thống định nghĩa như vậy.
6. **Thống nhất Unicode normalization** khi cần, tránh client/server áp khác nhau dẫn đến người dùng không đăng nhập được.
7. **Kiểm thử nhiều lớp truyền dữ liệu**: frontend, JSON parser, API gateway, IdP, database, KDF và ứng dụng legacy có thể dùng giới hạn khác nhau.

### Lưu ý Unicode

Một ký tự nhìn thấy có thể được biểu diễn bằng nhiều code point. Ví dụ một chữ có dấu có thể được mã hóa thành dạng ký tự ghép hoặc dạng dựng sẵn. Nếu hệ thống dùng Unicode normalization (chẳng hạn NFC), việc xử lý phải **nhất quán ở cả lúc tạo và lúc xác thực**, được đánh giá theo yêu cầu của chuẩn và không biến thành quy tắc loại bỏ ký tự bất ngờ.

Trong Java, \`String.length()\` đếm **UTF-16 code units**, không tương đương số Unicode code point trong mọi trường hợp. Ví dụ kiểm tra số code point:

~~~java
// Chỉ minh họa phép đo; không phải toàn bộ password validator.
int codePointLength = password.codePointCount(0, password.length());
if (codePointLength < minRequiredLength) {
    return PasswordDecision.reject("TOO_SHORT");
}
~~~

**Không gửi password thật vào log** khi ghi nhận lỗi độ dài. Phần log nên chứa mã lỗi, policy version và kênh phát sinh; ngay cả độ dài cụ thể cũng cần cân nhắc mức độ cần thiết.

### Những edge case phải thử

| Input | Điều cần kiểm tra |
| --- | --- |
| Rỗng hoặc null | Từ chối an toàn; không gây exception tiết lộ stack trace. |
| Ngắn hơn tối thiểu một ký tự | Từ chối chính xác tại ranh giới. |
| Bằng đúng tối thiểu | Chấp nhận **nếu** các quy tắc khác đều đạt. |
| Bằng 64 ký tự hoặc độ dài dài hơn cấu hình | Không cắt ngầm; xử lý theo giới hạn công bố. |
| Có dấu cách giữa hoặc ở hai đầu | Xử lý đúng theo quy tắc, không tự trim. |
| Có emoji và ký tự ngoài BMP | Không nhầm byte/UTF-16 code unit với code point. |
| Ký tự có dấu ở dạng ghép | Normalization/verification nhất quán nếu áp dụng. |
| Ký tự điều khiển hoặc ký tự không được hỗ trợ | Từ chối có mã lỗi rõ ràng khi có căn cứ giao thức/kỹ thuật; không dùng quy tắc mơ hồ. |
| Chuỗi rất lớn vượt giới hạn xử lý của hệ thống | Từ chối có giới hạn tài nguyên, tránh DoS và không truncate. |

## 5. Blocklist: kiểm tra mật khẩu phổ biến và bị lộ

Một trong các kiểm tra quan trọng nhất khi thiết lập mật khẩu là đối chiếu với **danh sách các giá trị không nên dùng**, thường bao gồm:

- Mật khẩu xuất hiện thường xuyên trong các bộ dữ liệu thực tế hoặc bộ từ điển tấn công.
- Mật khẩu đã được công bố từ các vụ rò rỉ credential.
- Chuỗi dễ đoán theo ngữ cảnh: tên công ty, tên sản phẩm, tên dịch vụ, tên tài khoản hoặc biến thể đơn giản khi có cơ sở chính sách.
- Các mẫu cực kỳ phổ biến như chuỗi bàn phím hoặc thay chữ bằng số một cách dễ đoán.

### Luồng kiểm tra

~~~mermaid
flowchart LR
    P["Người dùng gửi mật khẩu mới qua kênh bảo vệ"] --> V["Kiểm tra độ dài/định dạng"]
    V --> B["Kiểm tra blocklist tin cậy"]
    B --> D{"Bị cấm hoặc không đạt policy?"}
    D -->|Có| R["Từ chối + phản hồi không tiết lộ secret"]
    D -->|Không| H["Hash bằng password KDF + salt riêng"]
    H --> S["Lưu verifier và metadata an toàn"]
~~~

**Không gửi mật khẩu bản rõ tới một dịch vụ kiểm tra bên ngoài không được đánh giá và phê duyệt.** Một hệ thống có thể dùng blocklist nội bộ hoặc cơ chế kiểm tra theo giao thức bảo vệ riêng tư phù hợp, với hợp đồng xử lý dữ liệu, bảo mật truyền tải và hạn chế lộ danh tính/mật khẩu.

### Kiểm tra theo trạng thái thất bại

Nếu dịch vụ blocklist đang không sẵn sàng, chính sách phải quy định rõ **fail closed**, hoãn thiết lập credential, dùng bản sao blocklist đã xác minh hoặc xử lý ngoại lệ được duyệt. Không nên tự động bỏ qua bước kiểm tra và tuyên bố mật khẩu đã đạt chính sách đầy đủ.

Với danh sách rất lớn, cần quản lý version, thời điểm cập nhật, nguồn dữ liệu, toàn vẹn bản cập nhật và SLA. Một mật khẩu có thể không nằm trong danh sách khi tạo nhưng xuất hiện trong nguồn rò rỉ sau đó; tổ chức cần cơ chế đánh giá và xử lý theo rủi ro, không lưu mật khẩu bản rõ để kiểm tra lại.

## 6. Vì sao không nên phụ thuộc regex “đủ bốn loại ký tự”?

Các chính sách truyền thống thường yêu cầu ít nhất một chữ hoa, một chữ thường, một chữ số và một ký tự đặc biệt. Chúng có thể đẩy người dùng về mẫu dễ đoán như \`TenCongTy2026!\`, sau đó đổi thành \`TenCongTy2027!\` khi bị ép đổi định kỳ.

Một regex thành phần có thể đánh dấu **PASS** cho mật khẩu dễ đoán và **FAIL** cho passphrase dài, độc nhất. Do đó:

- Dùng **độ dài và blocklist** làm kiểm soát chính tại thời điểm thiết lập.
- Khuyến khích password manager tạo mật khẩu ngẫu nhiên, dài và độc nhất cho từng dịch vụ.
- Chỉ áp rule thành phần nếu có yêu cầu chuẩn/khả năng tương thích được xác định, kèm đánh giá tác động.
- Đừng dùng một “điểm entropy” tự tính từ số nhóm ký tự để khẳng định mật khẩu không thể bị đoán.
- Không biến UI strength meter thành kết luận kiểm toán: meter chỉ là hỗ trợ người dùng nếu được thiết kế đúng.

### Ví dụ dễ hiểu

| Mật khẩu giả định | Kiểm tra theo độ dài | Kiểm tra theo blocklist | Nhận xét |
| --- | --- | --- | --- |
| \`Password123!\` | Có thể đạt ngưỡng độ dài thấp. | Nên bị chặn nếu nằm trong blocklist. | Đủ loại ký tự không đồng nghĩa mạnh. |
| \`CompanyName2026!\` | Có thể đủ dài. | Có thể bị chặn theo ngữ cảnh. | Tên tổ chức + năm là mẫu dễ đoán. |
| Một passphrase dài, độc nhất do người dùng tạo | Có thể đạt. | Cần kiểm tra thực tế. | Không nên tự từ chối vì thiếu ký tự đặc biệt. |
| Mật khẩu ngẫu nhiên dài từ password manager | Thường đạt. | Vẫn kiểm tra. | Cần hỗ trợ paste/autofill và lưu an toàn. |

Không nên đưa mật khẩu mẫu ở đây vào hệ thống thật. Đây là **dữ liệu kiểm thử/dạy học**, không phải gợi ý password để sử dụng.

## 7. Kiểm tra việc lưu trữ mật khẩu: KDF, salt và tham số

Chính sách mật khẩu không chỉ kiểm tra giá trị người dùng chọn. Nó phải bảo đảm verifier **không lưu mật khẩu có thể đọc lại** và chống được tấn công offline khi kho dữ liệu bị lộ.

### Mô hình lưu trữ

~~~text
password input (chỉ tồn tại trong xử lý được bảo vệ)
    |
    +-- kiểm tra policy cho mật khẩu mới
    |
    +-- tạo salt ngẫu nhiên riêng cho credential
    |
    +-- password KDF với tham số được phê duyệt
    |
    +-- lưu {algorithm, version, params, salt, derived hash}
    |
    +-- xóa/giảm thời gian tồn tại bản rõ trong khả năng nền tảng
~~~

Các lựa chọn phổ biến gồm **Argon2id**, **scrypt**, **bcrypt** hoặc **PBKDF2** tùy nền tảng và yêu cầu tuân thủ. Việc lựa chọn và tham số cần tuân thủ hướng dẫn hiện hành của tổ chức, đánh giá khả năng chống tấn công offline, khả năng vận hành và nâng cấp. Một thuật toán được chấp nhận trong hoàn cảnh này không nhất thiết là lựa chọn tối ưu cho mọi hệ thống.

**Salt** phải đủ ngẫu nhiên và riêng cho từng credential; nó không cần phải bí mật. **Pepper**, nếu được sử dụng, là bí mật cấp hệ thống cần lưu trong vault/HSM hoặc khu vực quản lý khóa riêng, không ghép vào cùng kho hash một cách vô nghĩa.

Không dùng một lần **MD5, SHA-1 hoặc SHA-256 trực tiếp** làm cơ chế lưu trữ password vì chúng quá nhanh để chống đoán hàng loạt khi dữ liệu hash bị lộ. Cũng không chỉ mã hóa password bằng khóa giải mã chung rồi xem là thay thế password hashing.

### Rehash khi công nghệ thay đổi

Khi chính sách tăng tham số KDF hoặc thay thuật toán, hệ thống có thể rehash sau **lần xác thực thành công** nếu có điều kiện phù hợp, đồng thời có lộ trình cho tài khoản ít hoạt động. Không yêu cầu ghi lại mật khẩu bản rõ vào database để migrate.

Đo thời gian và chi phí KDF trên hạ tầng thực, có kiểm soát tải và phòng chống DoS ở endpoint đăng nhập. **KDF mạnh và rate limiting là hai lớp bảo vệ bổ sung**, không thay thế nhau.

## 8. Kiểm tra tại thời điểm đăng nhập: rate limit và chống enumeration

Một mật khẩu hợp lệ vẫn có thể bị đoán hoặc bị đánh cắp. Do đó hệ thống xác thực phải kiểm tra nhiều yếu tố **ở runtime**:

1. Chuẩn hóa và xác định đúng tài khoản theo nguồn có thẩm quyền, tránh gộp nhầm danh tính.
2. Kiểm tra tài khoản có được phép đăng nhập theo trạng thái HR/IdP hay không.
3. So khớp mật khẩu qua KDF verifier an toàn, không so plaintext.
4. Áp **rate limiting/throttling** trên tài khoản, nguồn truy cập và các tín hiệu rủi ro thích hợp.
5. Giảm khả năng **enumeration** bằng phản hồi và thời gian xử lý không tiết lộ thông tin không cần thiết.
6. Phát hiện credential stuffing, password spraying và đăng nhập bất thường.
7. Nếu xác thực đúng, vẫn kiểm tra MFA, session policy và authorization trước khi truy cập.

### Rate limit phải được thiết kế cẩn thận

| Kiểu tấn công | Đặc điểm | Kiểm soát hữu ích |
| --- | --- | --- |
| **Brute force theo một tài khoản** | Thử nhiều mật khẩu của cùng user. | Giới hạn theo tài khoản, backoff, giám sát và MFA. |
| **Password spraying** | Một mật khẩu thử với rất nhiều user. | Giám sát mẫu theo nguồn/mật khẩu suy luận được, giới hạn phân tán và tín hiệu tổ chức. |
| **Credential stuffing** | Tự động thử tổ hợp user/password đã lộ. | Blocklist, kiểm tra mật khẩu bị lộ, MFA và phân tích lưu lượng rủi ro. |
| **Account lockout abuse** | Cố tình khiến nhiều tài khoản bị khóa để gây gián đoạn. | Hạn chế/điều tiết thích ứng thay vì khóa cứng vô hạn. |
| **User enumeration** | Phân biệt user tồn tại bằng thông báo, thời gian hoặc API. | Phản hồi thống nhất, kiểm soát timing và giới hạn thông tin. |

Không áp một mức chặn theo IP toàn cầu quá thô nếu môi trường có NAT và người dùng chia sẻ mạng; cũng không chỉ giới hạn theo IP vì attacker có thể phân tán nguồn. Chính sách cần đo false positive, hỗ trợ phục hồi hợp lệ và theo dõi hiệu quả chống tấn công.

## 9. Kiểm tra các luồng đổi mật khẩu, reset và recovery

**Thay đổi mật khẩu khi đã đăng nhập**, **reset khi quên mật khẩu** và **admin reset** là ba đường với mô hình tin cậy khác nhau; tất cả đều phải được bảo vệ và áp password policy nhất quán.

| Luồng | Điều kiện bảo vệ trọng tâm | Dấu hiệu lỗ hổng |
| --- | --- | --- |
| **Change password** | Phiên đăng nhập hợp lệ; reauthentication/step-up nếu nhạy cảm; kiểm mật khẩu mới. | Session bị chiếm có thể đổi password không cần kiểm tra bổ sung. |
| **Forgot password** | Recovery token ngẫu nhiên, một lần, giới hạn thời hạn; xác minh yêu cầu đúng account. | Link reset tái sử dụng, token không hết hạn hoặc bị lộ qua log/URL ngoài ý muốn. |
| **Admin-assisted reset** | Role hỗ trợ được phân quyền; ticket/lý do, xác minh người yêu cầu và audit. | Helpdesk chỉ hỏi tên/ngày sinh rồi cấp password tạm. |
| **Password recovery sau compromise** | Kiểm soát phiên/token, MFA, authenticator và trạng thái tài khoản trước khi mở lại. | Chỉ đổi mật khẩu nhưng session của attacker vẫn dùng được. |
| **First password/bootstrap** | Credential khởi tạo giới hạn, dùng một lần, gắn với đúng chủ thể và luồng enrollment. | Mật khẩu mặc định dùng chung hoặc được cấp qua kênh không đáng tin. |

### Quy trình reset an toàn

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant UI as Reset portal
    participant IAM as IdP / Recovery service
    participant AUD as Audit
    U->>UI: Yêu cầu reset
    UI->>IAM: Khởi tạo request có kiểm soát
    IAM-->>UI: Phản hồi không tiết lộ user tồn tại
    IAM->>U: Gửi liên kết/mã reset qua kênh đã xác minh
    U->>IAM: Trình token reset + mật khẩu mới
    IAM->>IAM: Xác minh token, account, TTL, one-time use
    IAM->>IAM: Kiểm policy, blocklist và hash password mới
    IAM->>IAM: Consume token; áp chính sách session/token
    IAM->>AUD: Log sự kiện và thông báo thay đổi
    IAM-->>U: Kết quả
~~~

Token recovery phải đủ khó đoán, **được bảo vệ khi lưu**, ngắn hạn, sử dụng một lần, gắn với đúng account và mục đích. Nếu có nhiều yêu cầu reset song song, hệ thống cần xử lý trạng thái và concurrency sao cho token cũ không thể tiếp tục dùng trái chính sách.

Không dùng **security questions** dựa trên dữ liệu dễ tra cứu như ngày sinh hoặc tên người thân như một biện pháp tin cậy duy nhất để vượt MFA. Với tài khoản có đặc quyền, recovery phải đạt mức bảo đảm phù hợp, có thể cần phê duyệt độc lập.

**Đổi password không tự đồng nghĩa logout mọi session.** Hệ thống cần xác định rõ chính sách thu hồi refresh token, session cũ, remembered devices, API token và các phiên SaaS. Khi có dấu hiệu lộ, nên xử lý những đường truy cập này theo incident response và kiểm chứng thực tế.

## 10. Một chính sách, nhiều điểm thực thi

Trong doanh nghiệp, mật khẩu có thể được đặt qua nhiều kênh:

- Giao diện đăng ký user và self-service reset.
- API tạo/đổi mật khẩu của ứng dụng.
- IdP, AD/LDAP hoặc hệ thống SSO.
- Console quản trị, helpdesk, batch import và script nội bộ.
- Ứng dụng legacy có local login tách biệt.
- Luồng đồng bộ/migration account giữa các hệ thống.

Nếu mỗi kênh tự áp quy tắc khác nhau, attacker hoặc nhân viên có thể vô tình dùng đường yếu nhất. Vì vậy **server-side policy enforcement tại nơi sở hữu credential** là bắt buộc; frontend chỉ nên dùng kiểm tra sơ bộ để giúp trải nghiệm người dùng.

### Kiến trúc đề xuất

~~~mermaid
flowchart TD
    WEB["Web / Mobile / Self-service"] --> API["Credential Management API"]
    HELP["Helpdesk / Admin UI"] --> API
    MIG["Migration / Legacy adapter"] --> API
    API --> AUTH["Kiểm quyền thay đổi credential"]
    AUTH --> POL["Password Policy Service"]
    POL --> BL["Blocklist / Risk controls"]
    POL --> STORE["IdP credential store + password KDF"]
    STORE --> LOG["Audit không chứa secrets"]
    API --> LOG
~~~

**Tránh để ứng dụng tự lưu mật khẩu riêng khi đã có IdP** trừ khi có nhu cầu thực tế và quy trình quản trị rõ ràng. SCIM được dùng chủ yếu để đồng bộ Users/Groups và **không phải giao thức kiểm tra độ mạnh hay xác minh mật khẩu**. Không tự động đồng bộ mật khẩu bản rõ sang mọi SaaS chỉ vì cần provisioning tài khoản.

### Admin bypass phải được kiểm soát

Một console quản trị có thể có quyền **reset** hoặc phát hành credential tạm, nhưng không nên mặc định được bỏ qua blocklist/độ dài. Ngoại lệ (ví dụ tài khoản legacy không hỗ trợ chính sách mới) phải có owner, lý do, giới hạn, hạn hết hiệu lực và kế hoạch cải thiện.

## 11. Ví dụ Java: PasswordPolicyValidator

Mã sau minh họa **cấu trúc kiểm tra quy tắc khi đặt mật khẩu mới**. Đây là pseudocode gần với Java, không phải thư viện bảo mật hoàn chỉnh; cần dùng thành phần IAM/IdP và password hashing chuẩn đã được kiểm thử.

~~~java
enum PasswordRejection {
    TOO_SHORT,
    TOO_LONG_FOR_SUPPORTED_INPUT,
    COMMON_OR_COMPROMISED,
    CONTEXT_SPECIFIC_WEAK,
    POLICY_UNAVAILABLE
}

record PasswordValidation(boolean accepted, PasswordRejection reason) {
    static PasswordValidation pass() {
        return new PasswordValidation(true, null);
    }
    static PasswordValidation deny(PasswordRejection reason) {
        return new PasswordValidation(false, reason);
    }
}

// Interface minh họa: kiểm tra blocklist không để lộ password ra log.
interface ProtectedBlocklist {
    boolean isProhibited(CharSequence password, PasswordContext context);
}

class PasswordPolicyValidator {
    private final ProtectedBlocklist blocklist;
    private final PolicyConfig config;

    PasswordValidation validateNewPassword(
            CharSequence candidate, PasswordContext context) {

        if (candidate == null) {
            return PasswordValidation.deny(PasswordRejection.TOO_SHORT);
        }

        // Phải định nghĩa rõ cách đếm ký tự/normalization trong triển khai thật.
        String value = candidate.toString();
        int length = value.codePointCount(0, value.length());
        int minLength = config.requiredLengthForVerifiedPolicy(context);

        if (length < minLength) {
            return PasswordValidation.deny(PasswordRejection.TOO_SHORT);
        }
        if (length > config.maximumSupportedLength()) {
            return PasswordValidation.deny(
                PasswordRejection.TOO_LONG_FOR_SUPPORTED_INPUT);
        }

        if (!blocklist.isAvailable()) {
            return PasswordValidation.deny(PasswordRejection.POLICY_UNAVAILABLE);
        }
        if (blocklist.isProhibited(value, context)) {
            return PasswordValidation.deny(
                PasswordRejection.COMMON_OR_COMPROMISED);
        }
        if (config.contextRules().isObvious(value, context)) {
            return PasswordValidation.deny(
                PasswordRejection.CONTEXT_SPECIFIC_WEAK);
        }
        return PasswordValidation.pass();
    }
}
~~~

**Lưu ý về mã minh họa:**

- \`config.requiredLengthForVerifiedPolicy()\` phải dựa trên chính sách từ server/IdP, **không nhận cờ MFA từ client**.
- \`blocklist.isAvailable()\` và \`contextRules().isObvious()\` là các phương thức ý tưởng, cần triển khai thực; ví dụ không thể compile nguyên văn nếu thiếu các kiểu này.
- Việc dùng \`String\` trong ví dụ giúp dễ đọc nhưng trong JVM nó làm tăng thời gian tồn tại của secret trong memory và khó xóa ngay. Trong hệ thống thực cần giảm tối đa bản sao password, áp bảo vệ tiến trình và sử dụng API chuyên dụng khi khả thi.
- Phép kiểm tra **không nên log \`candidate\`, \`value\` hoặc context nhạy cảm**.
- Việc xử lý Unicode normalization, ký tự không hợp lệ và giới hạn tài nguyên phải nhất quán với IdP đang xác minh mật khẩu.
- Sau khi validator PASS, password phải được hash bằng KDF đúng tham số trước khi lưu; **PASS chính sách không đủ để lưu bản rõ**.

### Pseudocode cho endpoint đổi mật khẩu

~~~java
// Pseudocode: định danh và quyền đổi mật khẩu do backend xác minh.
void changePassword(TrustedSession session,
                    SecretInput currentPassword,
                    SecretInput newPassword) {
    Account account = identityRepository.requireAccount(session.subjectId());

    if (!session.isValid() || !account.isAllowedToChangePassword()) {
        throw new AccessDeniedException("credential_change_not_allowed");
    }
    if (!session.meetsRecentReauthenticationRequirement()) {
        throw new StepUpRequiredException();
    }
    if (!passwordVerifier.matches(account.passwordHash(), currentPassword)) {
        throttler.recordFailure(account.id());
        throw new AuthenticationException("invalid_credential");
    }

    PasswordValidation decision = passwordPolicy.validateNewPassword(
        newPassword.asProtectedChars(), serverContextFor(account));
    if (!decision.accepted()) {
        throw new PasswordPolicyException(decision.reason());
    }

    // Update credential version + revoke reset tokens atomically.
    credentialStore.replaceWithAdaptiveHash(account, newPassword);
    recoveryService.invalidateOutstandingResetTokens(account.id());
    sessionService.applyPostPasswordChangeSessionPolicy(account.id());
    audit.recordCredentialChangedWithoutPassword(account.id());
}
~~~

Code chỉ minh họa thứ tự kiểm soát. Triển khai thực cần transaction/concurrency protection, anti-CSRF, quản lý secret trong bộ nhớ, response không tiết lộ dữ liệu và cơ chế xử lý sự cố.

## 12. Bộ kiểm thử tự động cho password policy

Một bộ kiểm thử tốt cần có **ca hợp lệ, ca bị từ chối và ca cố tình bypass**. Dưới đây là ma trận mẫu; kết quả phải được diễn giải theo cấu hình policy thực tế thay vì sao chép máy móc.

| ID | Tình huống | Kỳ vọng |
| --- | --- | --- |
| P01 | Mật khẩu rỗng hoặc null. | Từ chối với mã lỗi an toàn. |
| P02 | Độ dài thấp hơn tối thiểu một ký tự. | Từ chối \`TOO_SHORT\`. |
| P03 | Độ dài bằng tối thiểu, không nằm trong blocklist. | Chấp nhận nếu các điều kiện còn lại đạt. |
| P04 | Mật khẩu dài 64 ký tự/chuỗi dài được hỗ trợ. | Không truncate; hoạt động nhất quán từ tạo tới login. |
| P05 | Mật khẩu trong blocklist dù có hoa/số/ký tự đặc biệt. | Từ chối. |
| P06 | Mật khẩu có từ ngữ dễ đoán gắn với tài khoản/tổ chức theo rule. | Từ chối nếu khớp chính sách đã định nghĩa. |
| P07 | Passphrase dài, độc nhất, có dấu cách nhưng không có số. | Không bị từ chối chỉ vì thiếu loại ký tự nếu policy không bắt thành phần. |
| P08 | Ký tự Unicode, emoji, dạng tổ hợp. | Xử lý nhất quán giữa UI, API, KDF và login. |
| P09 | Trình duyệt paste/autofill mật khẩu từ password manager. | Được phép, không khóa do hành vi paste. |
| P10 | Độ dài vượt giới hạn tài nguyên công bố. | Từ chối rõ, không cắt ngầm, không làm treo hệ thống. |
| P11 | Dịch vụ blocklist không hoạt động. | Áp fail-mode đã phê duyệt, không tự báo PASS vô căn cứ. |
| P12 | Đổi mật khẩu từ session hết hạn hoặc sai chủ thể. | Từ chối, không thay credential. |
| P13 | Đổi mật khẩu mà không đáp ứng recent authentication. | Yêu cầu step-up theo policy. |
| P14 | Reset token đã dùng hoặc quá hạn. | Không thể dùng lại. |
| P15 | Reset token của tài khoản A dùng để đổi password B. | Từ chối và audit. |
| P16 | API trực tiếp bỏ qua kiểm tra trên frontend. | Backend vẫn từ chối đầu vào trái policy. |
| P17 | Helpdesk reset mật khẩu qua kênh quản trị. | Vẫn áp chính sách; có quyền, lý do và audit. |
| P18 | Sai mật khẩu lặp lại từ cùng tài khoản hoặc phân tán nguồn. | Throttle/risk controls kích hoạt theo quy định. |
| P19 | User không tồn tại và user có thật nhưng password sai. | Phản hồi không tiết lộ account tồn tại ngoài mức cần thiết. |
| P20 | Nhân viên Leaver nhập đúng mật khẩu cũ. | Không thể đăng nhập bằng account đã bị thu hồi. |
| P21 | User đổi password trong IdP nhưng SaaS có local credential. | Phát hiện/kiểm soát đường đăng nhập cục bộ theo inventory. |
| P22 | Hệ thống nâng phiên bản password KDF. | Hash mới theo tham số mới; tài khoản cũ có lộ trình rehash an toàn. |

### Kiểm thử theo ranh giới

Các phép thử nên dùng giá trị **sinh ngẫu nhiên trong môi trường test** hoặc chuỗi được thiết kế để kiểm quy tắc. Không sử dụng mật khẩu thật của nhân viên. Với mỗi profile chính sách, kiểm thử **min-1**, **min**, **min+1**, giá trị gần max, blocklist hit và blocklist miss.

Phân biệt bài thử **validator** (chỉ kiểm nhận giá trị mới) và **end-to-end** (đặt mật khẩu → đăng nhập → đổi/reset → thu hồi). Một validator PASS nhưng login không nhận được cùng mật khẩu do Unicode hoặc truncate vẫn là lỗi nghiêm trọng.

## 13. Kiểm thử tích hợp giữa IdP, API và ứng dụng cũ

Một hệ thống có thể có chính sách đúng ở IdP nhưng vẫn bị bypass qua endpoint khác. Ma trận kiểm tra tích hợp:

| Kênh | Cần kiểm tra | Lỗi thường gặp |
| --- | --- | --- |
| **Self-service web** | Frontend hiển thị quy tắc; backend từ chối đúng. | Chỉ kiểm regex ở JavaScript, gọi API trực tiếp bypass. |
| **Mobile/API** | Cùng policy/version, xử lý Unicode và giới hạn nhất quán. | Mobile dùng bản policy cũ. |
| **Admin/helpdesk** | Quyền reset, xác minh yêu cầu, audit và blocklist. | Admin đặt mật khẩu yếu vì “quyền hỗ trợ”. |
| **IdP/SSO** | Quy tắc password, MFA, rate limit và trạng thái account. | IdP áp chính sách khác tài khoản cục bộ. |
| **AD/LDAP** | Fine-grained policy, account lockout và đường thay password. | Hệ thống legacy dùng chính sách domain cũ hoặc ngoại lệ không được ghi. |
| **SCIM/connector** | Tài khoản, nhóm và trạng thái đồng bộ chính xác. | Giả định SCIM đồng nghĩa đồng bộ password an toàn. |
| **Migration/batch import** | Nhập credential theo cơ chế an toàn; buộc reset khi cần. | Import mật khẩu bản rõ, bỏ qua chính sách, để lại tài khoản mặc định. |
| **Local SaaS account** | Có local login không, mật khẩu/phiên có thể bị thu hồi không. | Nhân viên Leaver vẫn login qua URL không SSO. |

### Không nhầm SCIM với xác thực mật khẩu

SCIM được thiết kế cho quản lý tài nguyên identity như Users và Groups. Một số triển khai có thuộc tính mật khẩu, nhưng **không nên vì có SCIM mà gửi mật khẩu bản rõ đến mọi ứng dụng**. Hợp đồng tích hợp phải nêu rõ nguồn nào sở hữu credential và cách ứng dụng xử lý đăng nhập. IdP/SSO giúp tập trung xác thực, song các local account và session độc lập phải được kiểm kê.

## 14. Kiểm toán: chứng minh chính sách đang được thực thi

Chính sách password có thể được viết trong tài liệu nhưng không có hiệu lực tại hệ thống đích. Cần lưu **bằng chứng thực thi**, không lưu bí mật.

| Nhóm sự kiện | Metadata nên có | Câu hỏi kiểm toán |
| --- | --- | --- |
| Policy publish/change | Policy ID, version, owner, approver, target system, timestamp. | Ai sửa quy tắc, áp từ thời điểm nào? |
| Password set/change | Subject ID, action, result, policy version, kênh, correlation ID. | Endpoint nào chấp nhận hoặc từ chối? |
| Validation rejection | Mã lý do tổng quát, target, request ID. | Có đường nào không chặn password trái policy không? |
| Blocklist update | Version, nguồn, thời điểm và kết quả kiểm toàn vẹn. | Blocklist có được duy trì đúng không? |
| Authentication failure | Account reference, tín hiệu rủi ro đã được phép, rate-limit decision. | Có password spraying hoặc credential stuffing không? |
| Recovery/admin reset | Actor, target account, approval/ticket, phương thức xác minh, kết quả. | Có reset trái phép hoặc bypass policy không? |
| Credential storage migration | KDF version, tiến độ rehash, lỗi, thời điểm. | Credential cũ có được nâng bảo vệ không? |
| JML deprovision | Trạng thái IdP, ứng dụng, local account, phiên/token, verifiedAt. | Người chuyển/nghỉ đã mất quyền đúng chưa? |

**Tuyệt đối không ghi password, TOTP seed, recovery token, session cookie, access/refresh token hoặc pepper vào log.** Với các mã lỗi, tránh trả cho client thông tin quá chi tiết về việc một tài khoản có tồn tại, có MFA hay đang bị khóa hay không.

Các chỉ số hữu ích:

- **Policy enforcement coverage:** tỷ lệ kênh tạo/đổi/reset password được kiểm tra bằng cùng profile đã duyệt.
- **Blocked password rate:** tỷ lệ bị từ chối theo nhóm lý do, không cần ghi giá trị.
- **Compromised-password rejection coverage:** tỷ lệ cơ chế blocklist hoạt động tại mọi đường đặt password.
- **Rate-limit effectiveness:** tấn công bị giảm nhưng tỷ lệ khóa nhầm hợp lệ trong giới hạn chấp nhận.
- **Reset abuse signals:** số lần reset bất thường, token bị sử dụng lại, yêu cầu helpdesk rủi ro.
- **Legacy/local account exposure:** số hệ thống còn lưu và xác thực mật khẩu tách khỏi IdP.
- **Credential storage migration progress:** tỷ lệ verifier theo phiên bản KDF/param mong muốn.
- **Residual access after Leaver:** tài khoản hoặc phiên còn dùng được sau mốc thu hồi.

Đừng tối ưu KPI bằng cách tăng số lần từ chối hợp lệ. Chính sách cần cân bằng **bảo mật, khả năng sử dụng, quyền riêng tư và hỗ trợ người dùng**, nhất là người cần trợ năng hoặc có hạn chế thiết bị.

## 15. Mật khẩu trong Joiner–Mover–Leaver

| Sự kiện | Quản lý password và authenticator | Liên hệ quyền truy cập | Điều cần xác minh |
| --- | --- | --- | --- |
| **Joiner** | Tạo IdP account, cấp luồng bootstrap an toàn, yêu cầu thiết lập mật khẩu nếu dùng password và đăng ký MFA theo chính sách. | Chỉ cấp baseline sau proofing, approval và thời điểm có hiệu lực. | Không có mật khẩu mặc định dùng chung hoặc account active trước ngày cho phép. |
| **Mover** | Có thể giữ password nếu không có dấu hiệu lộ; đánh giá lại yêu cầu MFA/authentication assurance cho role mới. | Gỡ quyền vai trò cũ, cấp quyền mới theo RBAC/ABAC và SoD. | Không ép đổi mật khẩu vô cớ để thay cho việc thu hồi role/ACL. |
| **Leaver** | Disable đường đăng nhập, revoke session/refresh token, kiểm tra local passwords/credentials khi có. | Deprovision quyền tại IdP, ứng dụng, vault và SaaS. | Người nghỉ không thể dùng password cũ hoặc session cũ để truy cập. |
| **Rehire** | Xác minh quan hệ mới, đánh giá credential cũ; đăng ký lại theo policy khi cần. | Không tự khôi phục quyền của lần làm việc trước. | Account/email không bị liên kết nhầm hoặc mở quyền cũ. |
| **Compromise** | Reset/rotate credential, xử lý MFA, session, token và điều tra. | Tạm chặn quyền rủi ro cao, phục hồi có kiểm soát. | Không còn đường truy cập từ credential/phiên bị lộ. |

**Điểm quan trọng:** đổi mật khẩu khi Mover không thay thế việc **thu hồi entitlement cũ**; khóa mật khẩu khi Leaver không tự chấm dứt **API token, session SaaS hoặc quyền truy cập qua service account**.

### Tình huống Joiner

Nhân viên An gia nhập phòng Tài chính. HRIS và IAM đã xác minh đúng người, đúng ngày hiệu lực. IdP cho An đăng ký mật khẩu qua luồng bootstrap một lần; server kiểm độ dài và blocklist, lưu KDF hash, rồi hướng dẫn đăng ký passkey/MFA. Tài khoản Finance chỉ có role được duyệt sau mốc hiệu lực. Nếu An chọn mật khẩu nằm trong blocklist, mọi kênh đặt mật khẩu phải từ chối nhất quán.

### Tình huống Mover

An chuyển sang vị trí phê duyệt tài chính. Chính sách mới yêu cầu authenticator chống phishing và recent authentication, nhưng **không có lý do mặc định buộc đổi password** chỉ vì chức danh đổi. IAM cần gỡ quyền cũ, cấp quyền mới sau SoD/approval, đồng thời bảo đảm bước step-up đáp ứng assurance của giao dịch.

### Tình huống Leaver

Khi An nghỉ việc, IdP disable account, chặn đăng nhập mới, thu hồi phiên/token theo hệ thống hỗ trợ. Connector SCIM cập nhật SaaS, nhưng cần đọc lại local account và session vì một số ứng dụng vẫn chấp nhận password riêng. Workflow không được báo “đã xong” khi còn một đường truy cập ngoài SSO.

## 16. Service account và password policy

Tài khoản dịch vụ, ứng dụng tự động hoặc CI/CD job thường không có con người nhập password mỗi lần chạy. Không nên gắn cơ chế **ép đổi mật khẩu ghi nhớ** của nhân viên lên workload rồi dùng giải pháp lưu password cứng trong script.

Ưu tiên trong phạm vi kỹ thuật cho phép:

1. **Managed identity hoặc workload identity federation**, lấy token ngắn hạn đúng workload.
2. **mTLS**, private-key client authentication hoặc certificate gắn dịch vụ có quản lý vòng đời.
3. Nếu bắt buộc dùng password/API key của hệ thống legacy, quản lý trong **secret manager**, scope tối thiểu, rotation, phát hiện lộ và kế hoạch thay thế.
4. Tách credential theo ứng dụng/môi trường, không dùng chung một mật khẩu cho tất cả job.
5. Bảo vệ **con người quản trị** service account bằng MFA và quyền PAM/IGA; không biến workload thành tài khoản nhân viên dùng chung.

Khi chủ sở hữu service account chuyển vai trò hoặc rời công ty, kiểm tra quyền vault, CI/CD, repository, trust policy và credential họ từng biết. Dịch vụ có thể cần hoạt động tiếp với owner mới; không xóa bừa danh tính kỹ thuật vì một nhân viên nghỉ việc.

## 17. Quy trình kiểm chứng khi áp dụng chính sách mới

Việc cập nhật password policy trong IdP cần **quản lý thay đổi có kiểm chứng** thay vì sửa cấu hình trên production rồi tin đã thành công.

~~~mermaid
flowchart TD
    REQ["Yêu cầu đổi policy + owner/approval"] --> DESIGN["Xác định profile, phạm vi, risk"]
    DESIGN --> TEST["Test unit, integration, security, accessibility"]
    TEST --> PILOT["Pilot / canary có giám sát"]
    PILOT --> DEPLOY["Triển khai cấu hình theo version"]
    DEPLOY --> READ["Readback policy tại từng IdP/API/target"]
    READ --> CHECK["Kiểm thử tạo, đổi, reset và đăng nhập"]
    CHECK --> DEC{"Đạt tiêu chí?"}
    DEC -->|Có| AUDIT["Đóng thay đổi và lưu evidence"]
    DEC -->|Không| FIX["Rollback hoặc fix có kiểm soát"]
    FIX --> TEST
~~~

**Bước 1 – Phân tích hiện trạng.** Kiểm kê phiên bản policy, nguồn credential, kênh tạo/đổi/reset, đặc điểm người dùng, khả năng Unicode/độ dài và các app legacy. Ghi lại phạm vi quyền chủ quản và lý do ngoại lệ.

**Bước 2 – Thiết kế và rà soát.** Xác định phiên bản tiêu chuẩn, mức ngưỡng, blocklist, KDF, throttling, recovery, khả năng dùng password manager, thông báo cho người dùng và kế hoạch hỗ trợ.

**Bước 3 – Kiểm thử.** Chạy test validator, endpoint API, IdP, ứng dụng mobile, admin reset, account có MFA, local account và quy trình JML. Thử các edge case Unicode, retry, blocklist unavailable và session cũ.

**Bước 4 – Triển khai theo đợt.** Pilot có giám sát và chuẩn bị cách khôi phục. Nếu phải di chuyển credential, không thu thập lại mật khẩu bản rõ hoặc ép reset hàng loạt khi không cần thiết; có kế hoạch rehash/migration phù hợp.

**Bước 5 – Readback và xác minh.** Đọc lại policy đang áp tại từng nơi sở hữu credential, chạy bộ kiểm thử canary từ các kênh được phép; lưu kết quả theo policy version/target.

**Bước 6 – Theo dõi drift và ngoại lệ.** Cảnh báo khi ứng dụng mới mở endpoint password đặt sai chuẩn hoặc admin tạo ngoại lệ không được phê duyệt. Kiểm toán định kỳ và sửa độ lệch.

### Tiêu chí nghiệm thu

Một thay đổi password policy đạt yêu cầu khi:

- Các kênh bắt buộc áp đúng policy version và không có đường bypass đã biết.
- Những mật khẩu trong blocklist bị từ chối ở thời điểm tạo/đổi/reset.
- Password dài, hợp lệ và Unicode được xử lý nhất quán tới lần đăng nhập sau.
- Mật khẩu được lưu qua password KDF được phê duyệt, không có plaintext trong log hoặc database.
- Rate limiting và recovery policy hoạt động, có bằng chứng không tiết lộ tài khoản/secret.
- IdP, local account và trạng thái JML không mở quyền ngoài chính sách.
- Mọi ngoại lệ có owner, hạn xử lý và cơ chế kiểm soát bù trừ được phê duyệt.

## 18. Tình huống thực hành: ứng dụng cũ bỏ qua blocklist

**Bối cảnh:** Tổ chức dùng IdP tập trung để xác thực. Password policy mới đã chặn mật khẩu phổ biến và khuyến khích passphrase. Nhưng ứng dụng Quản lý kho vẫn có endpoint \`POST /local-password/reset\` tự quản lý credential.

### 18.1. Phát hiện

Trong bài kiểm thử tích hợp, nhóm IAM đặt mật khẩu giả định nằm trong blocklist qua portal IdP và bị từ chối đúng. Với cùng mật khẩu kiểm thử, endpoint của ứng dụng kho lại trả thành công. Người dùng vẫn đăng nhập local khi SSO lỗi, vì vậy **đường yếu này thực sự làm giảm hiệu quả chính sách**.

### 18.2. Phân tích nguyên nhân

- Giao diện mới gọi API policy của IdP, nhưng endpoint cũ chỉ kiểm tối thiểu 8 ký tự.
- Local credential store dùng thuật toán hashing cũ.
- Admin support có quyền reset trực tiếp mà không qua workflow phê duyệt.
- Offboarding chỉ disable IdP, chưa đồng bộ trạng thái local account.

### 18.3. Kế hoạch sửa

1. Xác định mục tiêu: vô hiệu hóa local login nếu không cần, hoặc đưa local password lifecycle về một dịch vụ quản lý credential đáng tin.
2. Tạm áp hạn chế truy cập đối với endpoint rủi ro và kiểm soát support reset trong lúc sửa.
3. Tích hợp password policy server-side vào **mọi** đường đặt/reset; bảo đảm blocklist và quy tắc độ dài thống nhất.
4. Chuyển dữ liệu hash và tham số KDF theo kế hoạch bảo mật; không export password bản rõ.
5. Bổ sung unit/integration tests và test deprovision: Leaver không thể dùng local password để vào hệ thống kho.
6. Readback policy, đo lỗi và ghi bằng chứng; đóng ngoại lệ khi đường bypass đã được xử lý.

### 18.4. Kết quả mong muốn

IdP và ứng dụng kho dùng các chính sách tương thích, không có endpoint tạo mật khẩu yếu hoặc lưu plaintext, và việc khóa danh tính khi Leaver chặn cả SSO lẫn local login. **Không tuyên bố đã đạt nếu chỉ sửa regex trên trang web mà API cũ vẫn chấp nhận mật khẩu trái chính sách.**

## 19. Sai lầm thường gặp và cách khắc phục

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Chỉ yêu cầu đủ chữ hoa, số, dấu đặc biệt. | Mẫu dễ đoán vẫn được chấp nhận. | Ưu tiên độ dài, blocklist, rate limiting. |
| Bắt đổi mật khẩu theo lịch không có rủi ro. | Người dùng tạo chuỗi biến thể dễ đoán, tăng gánh nặng hỗ trợ. | Chỉ yêu cầu đổi theo dấu hiệu lộ và chính sách có căn cứ. |
| Chặn paste và password manager. | Người dùng dùng password ngắn/tái sử dụng. | Cho phép autofill/paste và passphrase dài. |
| Cắt ngầm mật khẩu vượt giới hạn. | Mất tính duy nhất, người dùng tưởng mọi ký tự được sử dụng. | Từ chối có thông báo; hỗ trợ độ dài đủ lớn. |
| Dùng regex ở frontend làm kiểm soát duy nhất. | API trực tiếp bypass. | Kiểm tra phía server tại nơi lưu credential. |
| Gửi password bản rõ tới API blocklist không đáng tin. | Rò rỉ credential khi đang tạo. | Dùng dịch vụ đã được đánh giá, cơ chế bảo vệ riêng tư hoặc blocklist nội bộ. |
| Hash password một lần bằng SHA-256 không salt. | Dễ tấn công offline khi kho hash lộ. | Password KDF và salt riêng, tham số được quản lý. |
| Log request body của endpoint đổi/reset password. | Secret xuất hiện trong log và công cụ giám sát. | Redact dữ liệu bí mật, thiết kế audit chỉ lưu metadata. |
| Chỉ khóa account khi sai quá nhiều lần mà không xét DoS. | Kẻ xấu khóa hàng loạt nhân viên. | Throttling thích ứng, phát hiện phân tán, hỗ trợ hợp lệ. |
| Reset qua helpdesk chỉ bằng dữ liệu công khai. | Account takeover, bypass MFA. | Recovery đủ bảo đảm, approval và log. |
| Dùng \`iat\` để coi token là vừa nhập lại password/MFA. | Step-up sai do refresh token. | Dùng auth_time/phiên đáng tin theo giao thức. |
| Gỡ quyền ở IdP nhưng local password vẫn hoạt động. | Quyền tồn dư sau Mover/Leaver. | Inventory local accounts, disable và xác minh deprovision. |
| Áp chính sách người dùng cho mọi service account. | Job phải hardcode password hoặc downtime do expiry. | Dùng workload identity/secret management và vòng đời riêng. |

## 20. Câu hỏi tự kiểm tra

**Câu 1.** Một mật khẩu dài và đủ chữ hoa/chữ thường/số/ký tự đặc biệt có chắc an toàn không?

**Trả lời:** Không. Nếu phổ biến, bị lộ hoặc dễ đoán theo ngữ cảnh thì cần bị từ chối theo blocklist/chính sách. Độ dài và các loại ký tự không thay thế kiểm tra này.

**Câu 2.** Vì sao việc tự động trim hoặc truncate password là nguy hiểm?

**Trả lời:** Nó làm thay đổi bí mật người dùng tưởng đã thiết lập, tạo mâu thuẫn giữa các kênh và có thể làm nhiều giá trị khác nhau bị ánh xạ thành cùng một đầu vào hash. Hệ thống phải có quy tắc rõ, xử lý nhất quán và không cắt ngầm.

**Câu 3.** Frontend đã kiểm regex; API có cần kiểm password policy nữa không?

**Trả lời:** Có. Kiểm tra frontend chỉ hỗ trợ trải nghiệm người dùng, có thể bị bypass. Policy phải được thực thi ở phía server/nơi quản lý credential trên mọi đường tạo/đổi/reset.

**Câu 4.** Vì sao không nên dùng SHA-256 trực tiếp để lưu password?

**Trả lời:** SHA-256 là hàm hash nhanh, không được thiết kế làm cơ chế bảo vệ mật khẩu trước tấn công đoán offline với tốc độ lớn. Cần password KDF được phê duyệt, salt riêng và tham số phù hợp.

**Câu 5.** Thay mật khẩu thành công có tự thu hồi mọi session và token không?

**Trả lời:** Không. Điều đó phụ thuộc cơ chế IdP và ứng dụng. Với sự cố lộ credential hoặc Leaver, phải xử lý refresh token, session cũ, local account/API key và kiểm chứng hiệu lực.

**Câu 6.** Khi một người chuyển từ Sales sang Finance, có cần bắt đổi password để thu hồi quyền Sales không?

**Trả lời:** Không. Thu hồi entitlement phải diễn ra qua RBAC/ABAC, nhóm, ACL, ứng dụng và token liên quan. Đổi password chỉ khi có lý do an toàn/assurance phù hợp; nó không thay thế deprovision quyền cũ.

**Câu 7.** Vì sao một ứng dụng legacy có local password có thể là lỗ hổng dù tổ chức đã triển khai SSO?

**Trả lời:** Vì nó có đường xác thực độc lập, có thể dùng password yếu và không chịu lệnh disable/revoke từ IdP. Cần kiểm kê, tích hợp chính sách và xác minh thu hồi tại ứng dụng đích.

**Câu 8.** Khi blocklist service lỗi, hệ thống có nên tự chấp nhận mọi password mới không?

**Trả lời:** Không nên tự bỏ qua. Phải áp fail-mode do chính sách phê duyệt, có thể hoãn thao tác hoặc sử dụng nguồn thay thế tin cậy, đồng thời ghi nhận kết quả và xử lý sự cố.

---

**Ghi nhớ:** Kiểm tra chính sách mật khẩu là **kiểm tra giá trị mật khẩu mới, bảo vệ quá trình xác minh/lưu trữ và kiểm chứng mọi kênh thực thi**. Một quy trình vững chắc ưu tiên **độ dài, mật khẩu độc nhất, blocklist, password KDF, throttling và recovery an toàn**, đồng thời cho phép password manager và tránh các ràng buộc gây phản tác dụng. Trong vòng đời **Joiner–Mover–Leaver**, mật khẩu là một phương tiện xác thực; **IdP/SSO, SCIM, RBAC/ABAC, MFA, session/token và deprovisioning** vẫn phải phối hợp để đảm bảo quyền chỉ tồn tại khi còn hợp lệ.
