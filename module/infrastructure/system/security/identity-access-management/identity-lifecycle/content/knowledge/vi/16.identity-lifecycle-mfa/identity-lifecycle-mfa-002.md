# Knowledge factor trong MFA: yếu tố người dùng biết và cách quản lý an toàn

**Knowledge factor (yếu tố kiến thức)** là nhóm yếu tố xác thực dựa trên **thông tin bí mật mà chủ thể biết**, thường được diễn đạt là *something you know*. Ví dụ điển hình gồm **mật khẩu (password)**, **cụm mật khẩu (passphrase)** và **mã PIN** trong những ngữ cảnh phù hợp. Trong **Multi-Factor Authentication (MFA)**, knowledge factor có thể được kết hợp với yếu tố thuộc nhóm khác, chẳng hạn một authenticator mật mã mà người dùng sở hữu, nhằm giảm khả năng kẻ tấn công đăng nhập chỉ bằng thông tin bí mật bị lộ.

Tuy nhiên, **hai câu hỏi bí mật không tạo ra hai yếu tố MFA**, và **mật khẩu cộng PIN riêng biệt cũng không tự trở thành MFA** nếu cả hai đều chỉ là thông tin cần ghi nhớ. Chất lượng của MFA phụ thuộc vào **loại yếu tố, mức độc lập của các authenticator, cách ràng buộc với chủ thể, khả năng chống lừa đảo và an toàn của quy trình khôi phục**.

Bài học thuộc chương **MFA** của mô-đun **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**, tìm hiểu quản lý vòng đời danh tính IAM theo mô hình **Joiner–Mover–Leaver**. Khi Joiner, người dùng được xác minh danh tính, tạo tài khoản và đăng ký phương thức xác thực. Khi Mover, chính sách và mức yêu cầu xác thực có thể thay đổi theo vai trò hoặc đặc quyền. Khi Leaver, tài khoản và các đường truy cập phải bị thu hồi phù hợp, bao gồm cả phiên và token đã cấp. Những thành phần **IdP, SSO, SCIM, RBAC/ABAC, tài khoản dịch vụ và kiểm toán** tạo thành ngữ cảnh vận hành cho knowledge factor.

**Điểm cốt lõi:** Knowledge factor là một cách chứng minh quyền kiểm soát tài khoản, **không phải bằng chứng đủ để xác minh nhân thân pháp lý, cũng không phải quyết định cấp quyền**. Phải phân biệt **identity proofing**, **authentication** và **authorization** trong toàn bộ vòng đời IAM.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Định nghĩa knowledge factor và phân biệt với **possession factor** (*something you have*) và **inherence factor** (*something you are*).
2. Nhận biết password, passphrase, PIN và câu hỏi bảo mật; đánh giá được vai trò và giới hạn của từng loại.
3. Giải thích vì sao **hai bước yêu cầu cùng nhóm kiến thức** không được coi là MFA thực sự.
4. Mô tả một luồng đăng nhập có knowledge factor tại **IdP/SSO** và bước bổ sung yếu tố khác khi chính sách yêu cầu.
5. Phân tích rủi ro phishing, credential stuffing, password spraying, lộ cơ sở dữ liệu mật khẩu và chiếm quy trình reset.
6. Trình bày nguyên tắc chọn, truyền, lưu, kiểm chứng và thay đổi mật khẩu mà không làm lộ bí mật.
7. Liên hệ vòng đời của authenticator với **Joiner–Mover–Leaver**, tài khoản dịch vụ, RBAC/ABAC và quản lý phiên/token.
8. Thiết kế thông báo lỗi, kênh hỗ trợ và chỉ số kiểm toán vừa hữu ích vừa không tiết lộ dữ liệu nhạy cảm.

## 2. Knowledge factor là gì và chứng minh được điều gì?

Giả sử hệ thống có một tài khoản thuộc về nhân viên An. Khi An nhập mật khẩu, hệ thống xác thực kiểm tra **người đang thao tác có cung cấp đúng bí mật gắn với tài khoản** hay không. Nếu kiểm tra thành công, hệ thống có một tín hiệu về quyền kiểm soát tài khoản, nhưng chưa thể suy ra chắc chắn người gõ mật khẩu là An: mật khẩu có thể bị đánh cắp, chia sẻ hoặc lừa cung cấp.

Cần tách các khái niệm:

| Khái niệm | Câu hỏi cần trả lời | Ví dụ |
|---|---|---|
| **Identity proofing** | Người đăng ký là ai và cơ sở xác minh đáng tin cậy đến đâu? | Xác minh danh tính trong onboarding |
| **Identity/account** | Bí mật hoặc authenticator gắn với account nào? | `personId=P-1042` ánh xạ với account IdP |
| **Knowledge factor** | Người đang xác thực có biết bí mật đã đăng ký không? | Mật khẩu hoặc PIN phù hợp ngữ cảnh |
| **MFA** | Có bằng chứng từ hơn một nhóm yếu tố phù hợp không? | Mật khẩu + khóa bảo mật được sử dụng đúng giao thức |
| **Authorization** | Account đã xác thực được làm gì? | Đọc báo cáo theo vai trò và dự án |
| **Session/token** | Sau khi xác thực, khả năng truy cập được duy trì thế nào? | Cookie phiên, access token có thời hạn |

**Biết đúng mật khẩu không mặc nhiên làm cho mọi tài nguyên được phép truy cập.** Ứng dụng vẫn phải áp RBAC/ABAC ở tầng nghiệp vụ/API. Tương tự, khi tài khoản của Leaver đã bị vô hiệu hóa, việc người đó còn nhớ mật khẩu không được trở thành lý do cho phép đăng nhập.

### 2.1. Các nhóm yếu tố xác thực

| Nhóm | Ý nghĩa | Ví dụ | Điểm cần lưu ý |
|---|---|---|---|
| **Knowledge** | Thông tin bí mật người dùng biết | Password, passphrase, PIN | Có thể bị đoán, tái sử dụng, lừa tiết lộ |
| **Possession** | Thiết bị hoặc authenticator người dùng kiểm soát | Khóa bảo mật vật lý, thiết bị giữ khóa riêng, ứng dụng tạo mã OTP | Cần bảo vệ khỏi mất/chiếm thiết bị, sao chép hoặc relay tùy cơ chế |
| **Inherence** | Đặc điểm sinh trắc của cá nhân | Dấu vân tay, khuôn mặt trong thiết kế được phép | Có sai số, rủi ro riêng tư; thường dùng để mở khóa authenticator cục bộ |

Một mã dùng một lần **được sinh từ authenticator sở hữu** thường đóng vai trò bằng chứng của possession, dù người dùng phải *đọc và nhập mã*. Việc dùng tay gõ một con số không biến mã đó thành knowledge factor; **nguồn gốc và cơ chế kiểm chứng** mới quyết định loại yếu tố.

## 3. Những loại knowledge factor thường gặp

### 3.1. Password – mật khẩu

Mật khẩu là chuỗi bí mật được người dùng ghi nhớ hoặc lưu trong **trình quản lý mật khẩu (password manager)**. Nó thường được kiểm tra bởi IdP hoặc dịch vụ xác thực phù hợp.

Ưu điểm là dễ triển khai và được nhiều hệ thống hỗ trợ. Hạn chế là người dùng có thể tái sử dụng giữa dịch vụ, bị lừa nhập vào trang giả, bị keylogger ghi lại hoặc để lộ qua dữ liệu bị đánh cắp.

**Password manager không làm mật khẩu “không còn là knowledge factor”** trong phân loại xác thực của hệ thống; nó giúp người dùng tạo và sử dụng bí mật dài, riêng biệt mà không phải tự nhớ tất cả. Tuy nhiên, an toàn của trình quản lý, thiết bị và quy trình khôi phục vẫn cần được đánh giá.

### 3.2. Passphrase – cụm mật khẩu

Passphrase là một dạng mật khẩu có thể gồm nhiều từ hoặc một câu dài. Khi được chọn từ nguồn đủ ngẫu nhiên và không dùng những câu dễ đoán, passphrase có thể mang lại **độ dài tốt** và dễ nhập hơn đối với một số người dùng.

**Độ dài không tự bảo đảm mạnh** nếu cụm từ là câu nổi tiếng, tên tổ chức hoặc chuỗi thường gặp. Độ mạnh phụ thuộc vào cách tạo, mức phổ biến, bí mật còn được bảo vệ và cơ chế chống thử đoán.

### 3.3. PIN – mã số bí mật

PIN thường gồm một dãy số ngắn, nhưng **ngữ cảnh kiểm tra PIN rất quan trọng**:

- **PIN kiểm tra từ xa như mật khẩu:** Nếu hệ thống cho nhập PIN trực tiếp để đăng nhập, PIN là knowledge factor và cần giới hạn thử đoán, kênh bảo vệ cùng chính sách phù hợp.
- **PIN mở khóa authenticator cục bộ:** Ví dụ PIN trên khóa bảo mật hoặc thiết bị giữ passkey có thể kích hoạt khóa riêng được thiết bị bảo vệ. Trong trường hợp đó, máy chủ thường kiểm chứng **phản hồi mật mã của authenticator**, không nhận PIN. PIN là bước *user verification/activation* tại thiết bị, còn khóa bí mật và cơ chế possession có vai trò riêng.

Không nên diễn giải “PIN + mật khẩu trên cùng biểu mẫu” là MFA chỉ vì người dùng nhập hai giá trị. Nếu cả hai là bí mật ghi nhớ được gửi đến cùng máy chủ, hệ thống vẫn đang dùng **hai knowledge secrets**, không phải hai nhóm yếu tố độc lập.

### 3.4. Câu hỏi bí mật (security questions)

Các câu hỏi như “tên thú cưng đầu tiên”, “trường tiểu học” hoặc “nơi sinh” thường được gọi là **knowledge-based authentication (KBA)**. Nhưng đáp án có thể công khai, suy đoán được, được chia sẻ qua mạng xã hội hoặc không ổn định theo thời gian.

**Không nên coi câu hỏi bảo mật tự khai là một yếu tố độc lập làm tăng từ password-only lên MFA.** Chúng cũng không nên là đường khôi phục mặc định cho tài khoản quan trọng: người biết hoặc tìm ra đáp án có thể chiếm account dù không có mật khẩu.

### 3.5. Mã khôi phục có cần được phân loại cẩn thận?

Một **recovery code** được cấp ngẫu nhiên cho người dùng có thể là một loại bí mật hoặc phương tiện khôi phục theo thiết kế, nhưng **không được tự động gắn nhãn knowledge factor hay MFA** chỉ vì nó là chuỗi ký tự. Mức bảo đảm phụ thuộc vào cách mã được tạo, lưu, bảo vệ, sử dụng một lần và quy trình xác minh bổ sung.

Mã khôi phục, PIN và OTP đều có thể “trông như chuỗi số”, nhưng **vai trò bảo mật không giống nhau**. Cần phân loại theo cơ chế thay vì hình thức.

## 4. Hai bước không đồng nghĩa với MFA

**Two-step verification** mô tả số bước, còn **multi-factor authentication** mô tả số **nhóm yếu tố độc lập** được dùng trong xác thực theo thiết kế.

| Tổ hợp | Có tự tạo MFA không? | Lý do |
|---|---|---|
| Mật khẩu + câu hỏi bí mật | **Không** | Cùng dựa vào thông tin người dùng biết |
| Mật khẩu + PIN nhập từ xa | **Không** | Hai knowledge secrets |
| Mật khẩu + mật khẩu khác | **Không** | Vẫn là cùng nhóm |
| Mật khẩu + OTP từ authenticator sở hữu độc lập | **Có thể có** | Knowledge và possession nếu enrollment, ràng buộc và kiểm chứng đúng |
| Mật khẩu + khóa bảo mật có thử thách mật mã | **Có thể có** | Knowledge và possession trong thiết kế phù hợp |
| Khóa/passkey được bảo vệ bằng xác minh người dùng tại thiết bị | **Có thể đáp ứng MFA** | Cơ chế khóa sở hữu + PIN/sinh trắc kích hoạt theo khả năng authenticator và chính sách |
| Mật khẩu + mã gửi qua email cùng account đã mở trong phiên | **Không nên mặc định coi là MFA mạnh** | Độc lập kênh và khả năng bị chiếm có thể không đáp ứng mục tiêu |
| Mật khẩu + SMS OTP | **Có thể là hai nhóm** | Nhưng chống phishing, SIM swap và mức bảo đảm cần đánh giá riêng |

**Phân biệt yếu tố độc lập với mức chống phishing:** Mật khẩu + TOTP thường là MFA theo nhóm yếu tố, nhưng mã vẫn có thể bị lừa người dùng cung cấp qua trang đăng nhập giả. MFA chống phishing như các cơ chế FIDO2/WebAuthn phù hợp thường bảo vệ tốt hơn trước kiểu tấn công đó.

### 4.1. Ví dụ rõ ràng

Một ứng dụng yêu cầu:

1. Nhập mật khẩu.
2. Trả lời “Tên người bạn thân nhất thời thơ ấu là gì?”.

Hai bước có thể khiến người dùng thấy nhiều kiểm tra hơn, nhưng **không làm hệ thống có hai nhóm yếu tố**. Một kẻ tấn công biết hoặc thu thập được cả hai bí mật có thể vượt qua luồng này mà không cần kiểm soát một authenticator khác.

### 4.2. Khi PIN tham gia vào passkey

Trong một luồng WebAuthn, authenticator có thể yêu cầu PIN để mở khóa cục bộ rồi ký một thử thách phù hợp với **origin/RP ID** bằng khóa riêng. Dịch vụ không xác minh PIN như một bí mật đăng nhập riêng mà kiểm tra **chứng cứ mật mã từ authenticator**. Vì vậy cần đánh giá khả năng xác minh người dùng và các thuộc tính authenticator, không đơn giản đếm “PIN + chữ ký = hai biểu mẫu”.

## 5. Luồng đăng nhập có knowledge factor tại IdP

Trong doanh nghiệp dùng **SSO**, ứng dụng thường chuyển người dùng tới IdP. IdP kiểm tra tài khoản, phương thức xác thực và chính sách, sau đó trả kết quả cho ứng dụng qua giao thức OIDC hoặc SAML phù hợp.

~~~mermaid
flowchart TD
    A["Người dùng mở ứng dụng"] --> B["Chuyển hướng IdP / SSO<br/>theo giao thức đã cấu hình"]
    B --> C{"Account và engagement<br/>còn đủ điều kiện?"}
    C -->|Không| X["Từ chối, ghi vết<br/>và hướng dẫn phù hợp"]
    C -->|Có| D["Nhận knowledge factor<br/>qua kênh xác thực bảo vệ"]
    D --> E{"Bí mật được kiểm chứng<br/>và không bị chặn?"}
    E -->|Không| Y["Thông báo chung,<br/>giới hạn thử và theo dõi"]
    E -->|Có| F{"Chính sách yêu cầu<br/>possession / step-up?"}
    F -->|Có| G["Xác minh authenticator<br/>thuộc nhóm khác"]
    G --> H{"Yếu tố bổ sung đạt?"}
    H -->|Không| X
    H -->|Có| I["IdP phát kết quả<br/>xác thực hợp lệ"]
    F -->|Không| I
    I --> J["Ứng dụng kiểm chứng<br/>token/assertion"]
    J --> K["Thiết lập phiên có bảo vệ"]
    K --> L["Ứng dụng/API kiểm tra<br/>RBAC/ABAC từng hành động"]
    L --> M{"Đủ quyền và điều kiện?"}
    M -->|Có| N["Cho phép trong phạm vi"]
    M -->|Không| O["Từ chối hành động"]
~~~

**Sơ đồ mang tính khái niệm:** Không phải mọi phiên đều hỏi mật khẩu. IdP có thể chấp nhận phiên đã xác thực hợp lệ, yêu cầu passkey thay mật khẩu hoặc thực hiện bước tăng cường theo chính sách. Hình chỉ minh họa nhánh **knowledge factor** và cách nó kết hợp với các kiểm soát khác.

### 5.1. Những gì phải được kiểm tra ngoài mật khẩu

- **Trạng thái account:** Active, disabled, locked, thời điểm hiệu lực, tình trạng Leaver.
- **Chính sách rủi ro:** Nguồn đăng nhập, thiết bị, ứng dụng nhạy cảm, dấu hiệu bất thường.
- **Authenticator được phép:** Người dùng đã đăng ký phương thức nào, yếu tố bổ sung có đủ mức bảo đảm?
- **Giao thức liên kết:** RP/SP kiểm chứng chữ ký, issuer, audience, thời hạn và quan hệ giao dịch của token/assertion.
- **Phiên ứng dụng:** Cookie/token được bảo vệ, có timeout và khả năng thu hồi theo chính sách.
- **Authorization:** RBAC/ABAC kiểm tra vai trò, thuộc tính, phạm vi và trạng thái hiện hành.

Ngay cả khi mật khẩu đã được kiểm chứng, ứng dụng vẫn có thể trả **403 Forbidden** đối với một thao tác không được phép. Đó không mặc nhiên là lỗi mật khẩu.

## 6. Độ mạnh của một knowledge factor phụ thuộc vào điều gì?

Một mật khẩu không chỉ có thuộc tính “đúng/sai”; còn có nhiều yếu tố ảnh hưởng đến khả năng bị đoán hoặc lộ:

| Chiều đánh giá | Câu hỏi cần xem xét |
|---|---|
| **Độ dài và cách tạo** | Bí mật đủ khó đoán, không phải chuỗi/biểu thức phổ biến? |
| **Tính duy nhất** | Có được dùng riêng cho dịch vụ này, tránh tái sử dụng? |
| **Mức lộ** | Đã xuất hiện trong danh sách rò rỉ hoặc bị phơi bày qua thiết bị, log? |
| **Cơ chế lưu trữ** | Verifier lưu dạng hash có salt bằng thuật toán phù hợp? |
| **Giới hạn thử đoán** | Có rate limiting, phát hiện tấn công và xử lý lockout an toàn? |
| **Kênh nhập/truyền** | Bí mật có được gửi qua kết nối được bảo vệ đến đúng IdP? |
| **Khả năng chống phishing** | Người dùng có bị dẫn tới trang giả hoặc bị tấn công relay? |
| **Đăng ký và khôi phục** | Kẻ khác có thể đặt lại mật khẩu bằng một quy trình yếu không? |
| **Trạng thái vòng đời** | Khi Leaver, account/session có bị chặn dù bí mật vẫn đúng? |

**Không tự đánh giá mật khẩu mạnh chỉ vì có chữ hoa, số và ký tự đặc biệt.** Một chuỗi theo mẫu dễ đoán như `CompanyName2026!` có thể trông “đủ loại ký tự” nhưng vẫn rất phổ biến hoặc suy đoán được.

## 7. Nguyên tắc thiết kế chính sách mật khẩu

Chính sách phải phù hợp mức rủi ro và các tiêu chuẩn tổ chức áp dụng. Những thực hành thường có ích gồm:

### 7.1. Ưu tiên độ dài và bí mật khó đoán

- Cho phép **mật khẩu dài và passphrase**; tránh giới hạn độ dài quá thấp khiến người dùng buộc phải dùng chuỗi ngắn.
- Cho phép các ký tự phù hợp với giao diện; xử lý encoding và normalization rõ ràng, nhất quán.
- Kiểm tra mật khẩu mới với **danh sách bí mật phổ biến, đã lộ hoặc dễ đoán**, theo phương thức bảo vệ dữ liệu thích hợp.
- Khuyến khích tạo bí mật riêng biệt bằng **password manager**; cho phép người dùng dán mật khẩu và tích hợp autofill phù hợp.
- Không yêu cầu mật khẩu trùng với tên, năm sinh, tên công ty hoặc các thông tin dễ suy ra.

### 7.2. Tránh quy tắc làm tăng ma sát mà ít lợi ích

Những yêu cầu đổi mật khẩu định kỳ cứng nhắc hoặc các mẫu ký tự bắt buộc quá phức tạp có thể khiến người dùng chuyển từ `Winter2026!` sang `Spring2027!` mà không thực sự giảm rủi ro.

Một chính sách hiện đại nên **đổi/reset khi có căn cứ bị lộ, nghi ngờ chiếm quyền, thay đổi authenticator hoặc lý do chính sách cụ thể**; không xem đổi mật khẩu thường xuyên là thay thế cho MFA hay giám sát. Quy định trong một số môi trường có thể khác, nên tổ chức phải xác nhận nghĩa vụ áp dụng.

### 7.3. Bảo vệ lúc nhập và gửi

- Chỉ nhập mật khẩu vào **trang/ứng dụng xác thực đáng tin cậy** qua kênh được bảo vệ.
- Không gửi mật khẩu qua chat, email, tài liệu dự án hoặc ticket hỗ trợ.
- Không yêu cầu người dùng đọc mật khẩu hay OTP cho helpdesk.
- Không đưa bí mật vào URL, tham số truy vấn, analytics hoặc log.
- Cân nhắc các thiết kế nhập liệu hỗ trợ người dùng kiểm tra lỗi đánh máy và tiếp cận phù hợp mà không làm lộ bí mật ngoài ý muốn.

### 7.4. Không dùng password hint như đường lộ thông tin

Một gợi ý chứa tên, ngày sinh hoặc nửa mật khẩu có thể giúp kẻ tấn công thu hẹp không gian tìm kiếm. Nếu người dùng quên mật khẩu, nên có **quy trình reset an toàn** thay vì hiển thị hint tiết lộ bí mật.

## 8. Kiểm chứng và lưu mật khẩu an toàn ở hệ thống xác thực

Ứng dụng không nên lưu **mật khẩu nguyên văn (plaintext)** hoặc mã hóa có thể giải ngược như cơ chế kiểm chứng thông thường. Hệ thống xác thực nên lưu **password verifier được tạo bởi hàm băm mật khẩu chuyên dụng có salt**, cấu hình phù hợp môi trường và có thể nâng cấp theo thời gian.

### 8.1. Vì sao hash mật khẩu khác hash dữ liệu thông thường?

Các hàm hash nhanh như SHA-256 thuần túy không được thiết kế để làm chi phí thử đoán mật khẩu cao. Khi cơ sở dữ liệu bị lấy cắp, kẻ tấn công có thể thử rất nhiều mật khẩu ứng viên. **Password hashing/KDF** được thiết kế để tăng chi phí thử đoán; ví dụ các lựa chọn tùy môi trường gồm **Argon2id, scrypt, bcrypt hoặc PBKDF2** với tham số và cách sử dụng phù hợp.

- **Salt:** Giá trị riêng cho mỗi verifier giúp chống một số hình thức tái sử dụng kết quả dò và ngăn việc các mật khẩu giống nhau tạo verifier y hệt khi dùng đúng cơ chế.
- **Cost parameters:** Cấu hình tăng chi phí tính toán theo khả năng vận hành và mức bảo vệ mong muốn.
- **Pepper (nếu sử dụng):** Bí mật bổ sung được quản lý tách khỏi cơ sở dữ liệu, có thể giảm một số rủi ro khi chỉ dữ liệu bị lộ; không thay thế salt hay KDF.
- **Migration:** Nâng cấp thuật toán/tham số có kiểm soát khi người dùng đăng nhập hoặc qua quy trình thay đổi phù hợp.

### 8.2. Mã giả kiểm chứng

~~~python
# Pseudocode: chỉ mô tả trách nhiệm, KHÔNG tự triển khai KDF.
def verify_knowledge_factor(account, supplied_password, verifier_service):
    if account is None or not account.login_eligible:
        return "AUTHENTICATION_DENIED"

    if verifier_service.rate_limit_exceeded(account.id):
        return "AUTHENTICATION_DENIED"

    # Password verifier chuyên dụng; dữ liệu bí mật không ghi log.
    is_valid = verifier_service.check_memorized_secret(
        supplied_password,
        stored_verifier=account.password_verifier
    )

    verifier_service.record_result_without_secret(
        account.id,
        success=is_valid
    )

    if not is_valid:
        return "AUTHENTICATION_DENIED"

    # Chưa tạo session truy cập tài nguyên nếu MFA/chính sách
    # còn đòi hỏi điều kiện xác thực khác.
    return "KNOWLEDGE_FACTOR_VERIFIED"
~~~

Đoạn mã **không phải chương trình production**: việc phòng account enumeration, chống timing side-channel, quản lý lỗi và khóa tài khoản, MFA, session binding, transaction correlation, transport security và chính sách rủi ro phải do hệ thống/thư viện xác thực được triển khai và đánh giá đầy đủ.

**Không ghi giá trị `supplied_password`**, thông tin verifier có thể tái sử dụng hoặc mã khôi phục vào log. Đội hỗ trợ chỉ cần trạng thái, loại lỗi và correlation ID có bảo vệ.

## 9. Những cuộc tấn công nhắm vào knowledge factor

| Kiểu tấn công | Cơ chế ở mức khái niệm | Biện pháp giảm thiểu |
|---|---|---|
| **Phishing** | Người dùng nhập bí mật vào trang giả hoặc bị lừa cung cấp | MFA chống phishing, nhận biết IdP thật, phát hiện liên kết nguy hiểm |
| **Credential stuffing** | Dùng thông tin đăng nhập đã rò rỉ từ dịch vụ khác | Mật khẩu duy nhất, blocklist bí mật lộ, MFA, phát hiện tự động |
| **Password spraying** | Thử một số mật khẩu phổ biến trên nhiều account | Rate limiting và phát hiện theo tập account/nguồn, điều tra bất thường |
| **Online brute force** | Thử nhiều ứng viên trên account | Giới hạn tốc độ, chính sách lockout cân bằng chống DoS |
| **Offline guessing** | Đoán từ cơ sở dữ liệu verifier bị đánh cắp | KDF có salt/cost phù hợp, bảo vệ cơ sở dữ liệu, phát hiện sự cố |
| **Keylogging/malware** | Mã độc đọc thao tác nhập hoặc bộ nhớ thiết bị | Thiết bị tin cậy, giảm đặc quyền, phòng mã độc, MFA phù hợp |
| **Shoulder surfing** | Người khác nhìn hoặc ghi lại khi nhập PIN/password | Bảo vệ thiết bị và môi trường nhập, giới hạn hiển thị |
| **Social engineering** | Lừa helpdesk reset hoặc lấy bí mật | Quy trình hỗ trợ và recovery có kiểm chứng, đào tạo |
| **Password reuse** | Một bí mật dùng cho nhiều hệ thống | Trình quản lý mật khẩu, chính sách dùng riêng, kiểm tra rò rỉ |
| **Insider sharing** | Mật khẩu được chia sẻ cho đồng nghiệp/nhà thầu | Danh tính riêng, PAM, ghi vết và quy trình cấp quyền đúng |

**MFA không xóa bỏ hoàn toàn các rủi ro trên.** Một trang phishing có thể lừa người dùng nhập mật khẩu và mã OTP, hoặc tấn công trực tiếp vào phiên đã xác thực. Cần kết hợp bảo vệ đăng nhập, thiết bị, session, token và authorization.

### 9.1. Rate limiting không đồng nghĩa khóa vĩnh viễn

Giới hạn số lần thử giúp giảm khả năng đoán mật khẩu qua mạng, nhưng khóa tài khoản quá dễ có thể bị lạm dụng gây **từ chối dịch vụ (DoS)**. Thiết kế phải xét giới hạn theo account, địa chỉ nguồn, ngữ cảnh, chính sách mở khóa và theo dõi tấn công, không đơn giản cho phép một người bên ngoài khóa vĩnh viễn hàng loạt account.

### 9.2. Phòng lộ sự tồn tại của account

Các thông điệp như “Email này chưa từng tồn tại” hoặc “Mật khẩu đúng nhưng tài khoản đang bị khóa” có thể giúp kẻ tấn công liệt kê người dùng. Ở bề mặt công khai, nên dùng thông báo **đủ hướng dẫn nhưng không tiết lộ trạng thái nhạy cảm**; log nội bộ dành cho người được phép có thể chứa thông tin chi tiết hơn.

## 10. Kết hợp knowledge factor với possession factor

Trong một mô hình phổ biến, IdP kiểm chứng password trước rồi yêu cầu một authenticator sở hữu. Hệ thống cần bảo đảm yếu tố bổ sung **đã được đăng ký hợp lệ với đúng identity**, được kiểm tra qua giao thức bảo vệ và không thể tự tạo mới trong cùng phiên rủi ro mà không có kiểm soát.

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Người dùng
    participant B as Trình duyệt
    participant I as IdP
    participant T as Authenticator sở hữu
    participant A as Ứng dụng

    U->>B: Mở ứng dụng
    B->>A: Yêu cầu truy cập
    A-->>B: Chuyển hướng IdP
    B->>I: Bắt đầu giao dịch xác thực
    I->>U: Yêu cầu mật khẩu nếu chính sách áp dụng
    U->>I: Gửi knowledge factor qua kênh bảo vệ
    I->>I: Kiểm chứng và kiểm tra rủi ro
    I->>T: Bắt đầu challenge yếu tố sở hữu
    T->>U: Yêu cầu tương tác/xác minh phù hợp
    U->>T: Hoàn thành yêu cầu authenticator
    T-->>I: Kết quả yếu tố sở hữu
    I->>I: Kiểm chứng, đánh giá MFA và chính sách
    I-->>B: Kết quả SSO có thể kiểm chứng
    B->>A: Trả kết quả theo giao thức
    A->>A: Kiểm chứng và tạo phiên
    A-->>B: Phiên ứng dụng hợp lệ
~~~

Sơ đồ minh họa, không quy định API giữa IdP và authenticator là mạng trực tiếp. Tùy WebAuthn, TOTP hay cơ chế khác, phần tử và kênh thực tế khác nhau.

### 10.1. Phân biệt “đã kiểm chứng password” với “MFA đã hoàn tất”

Một hệ thống tốt theo dõi các trạng thái riêng:

| Trạng thái | Ý nghĩa |
|---|---|
| `PASSWORD_REQUIRED` | Cần knowledge factor trước khi tiếp tục |
| `KNOWLEDGE_VERIFIED` | Bí mật đúng nhưng chính sách có thể chưa đạt |
| `SECOND_FACTOR_REQUIRED` | Cần authenticator thuộc nhóm khác |
| `MFA_VERIFIED` | Các điều kiện đa yếu tố đã đạt |
| `STEP_UP_REQUIRED` | Hành động/ứng dụng cần mức xác thực mới hoặc mạnh hơn |
| `LOGIN_DENIED` | Không đáp ứng điều kiện xác thực hoặc trạng thái tài khoản |
| `SESSION_ESTABLISHED` | Ứng dụng đã kiểm chứng kết quả và tạo phiên hợp lệ |

Tên trạng thái chỉ là **ví dụ thiết kế**; không phải schema chuẩn của một IdP cụ thể. Không cho phép hành động nhạy cảm chỉ dựa trên trạng thái `KNOWLEDGE_VERIFIED` nếu policy yêu cầu MFA.

## 11. Knowledge factor và passkey: không nhầm PIN cục bộ với mật khẩu tài khoản

**Passkey/WebAuthn** dựa trên mật mã khóa công khai: authenticator giữ khóa riêng và ký thử thách ràng buộc với ứng dụng/nguồn gốc phù hợp. Người dùng có thể sử dụng PIN hoặc sinh trắc để **mở khóa authenticator**. Bên dịch vụ kiểm chứng chữ ký và các điều kiện WebAuthn, không cần nhận PIN bí mật như mật khẩu của tài khoản.

| Cách đăng nhập | Vai trò của knowledge factor | Điều máy chủ xác minh chủ yếu |
|---|---|---|
| Password-only | Mật khẩu tài khoản là bí mật dùng xác thực | Verifier mật khẩu |
| Password + TOTP | Mật khẩu là knowledge; TOTP từ authenticator là yếu tố bổ sung phù hợp | Cả verifier mật khẩu và bằng chứng từ authenticator |
| Password + FIDO2 security key | Mật khẩu là knowledge; khóa là possession | Mật khẩu + phản hồi mật mã/chính sách WebAuthn |
| Passkey + PIN cục bộ | PIN kích hoạt hoặc xác minh người dùng tại authenticator | Phản hồi WebAuthn và cờ/thuộc tính theo policy |
| Hai mật khẩu | Hai bí mật ghi nhớ | Hai verifier knowledge, **không phải MFA** |

Một số loại passkey có cơ chế đồng bộ giữa thiết bị. Chính sách bảo đảm cần đánh giá khả năng đồng bộ, bảo vệ tài khoản đồng bộ, user verification, nguồn gốc và cách recovery. **Không nên tự khẳng định mọi passkey luôn cùng mức bảo đảm hoặc luôn cần mật khẩu trước khi sử dụng.**

## 12. Khôi phục mật khẩu và thay đổi knowledge factor

Quy trình **password reset/account recovery** là một đường truy cập đặc biệt nhạy cảm: nếu kẻ tấn công có thể đặt mật khẩu mới dễ dàng, MFA ở đăng nhập thông thường có thể bị vô hiệu hóa trên thực tế.

### 12.1. Luồng reset cần làm gì?

1. Người dùng khởi tạo yêu cầu từ kênh chính thức; hệ thống tránh tiết lộ account có tồn tại hay không.
2. Hệ thống áp chính sách chống lạm dụng, rate limiting và kiểm soát rủi ro.
3. Người yêu cầu phải **chứng minh quyền được khôi phục** bằng quy trình có mức bảo đảm phù hợp, có thể cần authenticator đã đăng ký, quy trình hỗ trợ đáng tin cậy hoặc proofing lại khi cần.
4. Nếu đủ điều kiện, người dùng đặt mật khẩu mới đáp ứng chính sách; verifier được cập nhật an toàn.
5. Các phiên, token và authenticator liên quan được đánh giá để thu hồi, thay thế hoặc giữ theo chính sách; đặc biệt khi có dấu hiệu chiếm quyền.
6. Hệ thống ghi log không chứa bí mật, thông báo qua kênh đáng tin cậy và cho người dùng đường hỗ trợ nếu không phải họ yêu cầu.

**Không yêu cầu helpdesk nhận mật khẩu hiện tại hoặc OTP của người dùng.** Đường recovery không nên chỉ phụ thuộc vào các câu hỏi bảo mật dễ tìm đáp án nếu mức rủi ro đòi bảo đảm cao hơn.

### 12.2. Mất authenticator không phải là lý do bỏ MFA vô điều kiện

Khi người dùng đổi điện thoại, mất khóa bảo mật hoặc thiết bị hỏng, tổ chức cần **phương án enrollment lại có kiểm chứng**. Có thể chuẩn bị authenticator dự phòng, mã khôi phục được quản lý đúng cách hoặc quy trình xác minh qua bộ phận hỗ trợ. Tùy mức rủi ro, cần khóa authenticator cũ và phát hiện dấu hiệu account takeover.

Tạo một phương thức MFA mới chỉ vì người dùng biết mật khẩu có thể làm suy yếu MFA nếu mật khẩu đã bị lộ. Bảo vệ đường đăng ký và recovery ít nhất phải phù hợp với mức rủi ro của quyền truy cập mà nó mở ra.

## 13. Knowledge factor trong vòng đời Joiner–Mover–Leaver

| Giai đoạn | Biến cố | Vận hành knowledge factor | Kiểm soát liên quan |
|---|---|---|---|
| **Joiner** | Cá nhân được xác minh và đủ điều kiện tạo account | Thiết lập phương thức ban đầu qua kênh an toàn nếu dùng mật khẩu; khuyến khích authenticator mạnh | IdP, SSO, MFA enrollment, mốc hiệu lực |
| **Mover** | Thay vai trò/dự án/địa điểm, mức rủi ro tăng | Xem xét yêu cầu MFA mạnh hơn hoặc step-up; không nhất thiết đổi mật khẩu chỉ vì đổi bộ phận | RBAC/ABAC, entitlement, session |
| **Leaver** | Quan hệ hoặc hợp đồng hết hạn | Chặn account và đường truy cập theo chính sách; không chỉ đổi mật khẩu | Deprovision qua IdP/SCIM/API, session/token revocation |
| **Rejoiner** | Cá nhân quay lại tổ chức | Xác minh đúng chủ thể, đánh giá lại authenticator/recovery và trạng thái account | Không phục hồi vô điều kiện quyền và credential cũ |
| **Suspected compromise** | Nghi ngờ mật khẩu lộ/chiếm account | Reset/thu hồi credential và phiên, điều tra phương thức MFA theo quy trình | Incident response, kiểm toán, cảnh báo |
| **Account recovery** | Quên bí mật, mất thiết bị | Xác minh lại quyền kiểm soát, enrollment an toàn, cập nhật verifier | Chống social engineering và bypass MFA |

### 13.1. Joiner: không gửi mật khẩu yếu để “làm nhanh onboarding”

Ví dụ HR đã xác nhận nhân viên Lan bắt đầu làm việc ngày 05/12. IAM có thể tạo account trước ngày bắt đầu, nhưng phải quản lý mốc kích hoạt và bảo đảm Lan nhận hướng dẫn đăng nhập từ kênh chính thức. Nếu tổ chức dùng mật khẩu ban đầu, quy trình kích hoạt phải bảo vệ bí mật, giới hạn sử dụng và yêu cầu thay hoặc đăng ký authenticator theo chính sách.

Cần kiểm tra **đúng người** nhận account: việc ai đó mở được email thông báo không tự chứng minh đã vượt qua identity proofing tương ứng.

### 13.2. Mover: quyền thay đổi không đồng nghĩa mật khẩu phải đổi

An chuyển từ nhóm Sales sang Finance. An có thể tiếp tục dùng cùng mật khẩu/passkey để chứng minh quyền kiểm soát identity. IAM phải **tính lại quyền**, cấp phần cần thiết cho Finance và thu hồi quyền Sales không còn hợp lệ.

Nếu Finance chứa dữ liệu nhạy cảm, chính sách có thể yêu cầu MFA chống phishing hoặc step-up mới khi thực hiện thao tác quan trọng. Tuy nhiên, **chỉ đổi mật khẩu không tự thu hồi role, token hoặc quyền chia sẻ cũ**.

### 13.3. Leaver: nhớ mật khẩu không được giúp tiếp tục truy cập

Khi contractor kết thúc hợp đồng, cần vô hiệu hóa quyền đăng nhập và các entitlement theo mốc quy định. Lệnh disable ở IdP có thể chặn login mới, nhưng **phiên ứng dụng, refresh token, personal access token hoặc account local** có thể còn tồn tại theo kiến trúc.

Không thể kết luận Leaver hoàn tất chỉ vì mật khẩu cũ đã bị đổi hoặc người dùng “không biết mật khẩu mới”. Hệ thống phải kiểm tra **khả năng truy cập thực tế**, quyền hiệu dụng tại ứng dụng và những credential/phiên cần xử lý.

### 13.4. Rejoiner: không khôi phục mật khẩu/nhóm cũ một cách máy móc

Một người trở lại sau một năm có thể có account đã disabled. Tổ chức có thể tái sử dụng hồ sơ identity hoặc account theo chính sách, nhưng phải kiểm tra trạng thái proofing, authenticator, liên hệ khôi phục, nhóm quyền và các đường truy cập cũ. Cần thiết lập lại phương thức xác thực nếu nguồn tin cậy không còn đầy đủ.

## 14. IdP, SSO, SCIM, RBAC/ABAC và knowledge factor

Bản đồ sau giúp thấy knowledge factor chỉ là **một thành phần** của quản trị danh tính:

~~~mermaid
flowchart LR
    H["HR / VMS<br/>Joiner-Mover-Leaver"] --> I["IAM / IGA<br/>Identity, trạng thái, quyền"]
    I --> D["IdP<br/>Account + authenticator"]
    D --> K["Knowledge verifier<br/>khi phương thức áp dụng"]
    D --> F["MFA + SSO<br/>kết quả xác thực"]
    I --> S["SCIM / API<br/>Cấp phát và thu hồi"]
    S --> A["Ứng dụng / API<br/>Authorization RBAC/ABAC"]
    F --> A
    A --> R["Đối soát quyền hiệu dụng<br/>session và token"]
    R --> I
~~~

| Thành phần | Liên hệ knowledge factor | Không thay thế được |
|---|---|---|
| **IdP** | Kiểm chứng password hoặc quản lý authenticator theo chính sách | Proofing ban đầu, authorization nghiệp vụ |
| **SSO/OIDC/SAML** | Chuyển kết quả xác thực sang ứng dụng tin cậy | Tự cấp/thu hồi mọi quyền ứng dụng |
| **SCIM/API** | Đồng bộ account, trạng thái và nhóm | Tự thu hồi mọi token hoặc xác minh password |
| **RBAC** | Xác định quyền theo vai trò | Xác thực chủ thể đang đăng nhập |
| **ABAC** | Xác định quyền theo thuộc tính/ngữ cảnh | Chứng minh mật khẩu hoặc thiết bị hợp lệ |
| **Kiểm toán** | Ghi loại yếu tố, kết quả và quyết định chính sách | Được phép ghi mật khẩu, OTP hay mã bí mật nguyên văn |

### 14.1. SSO giảm số mật khẩu, không tự làm MFA

SSO cho phép nhiều ứng dụng dựa vào một phiên IdP hợp lệ, giảm nhu cầu đăng nhập riêng và số bí mật cần quản lý. Tuy vậy, nếu IdP chỉ dùng mật khẩu và không yêu cầu yếu tố khác, **việc truy cập ba ứng dụng bằng SSO không tự biến thành MFA**.

Một lý do thiết kế MFA ở IdP là đặt điểm kiểm soát nhất quán cho nhiều ứng dụng, sau đó để ứng dụng yêu cầu step-up khi hành động nhạy cảm cần mức bảo đảm cao hơn.

### 14.2. SCIM không nên đồng bộ mật khẩu một cách tùy tiện

Một số hệ thống và giao thức có trường liên quan mật khẩu, nhưng **không nên mặc định sao chép mật khẩu IdP xuống mọi ứng dụng**. Truy cập liên kết qua SSO hoặc cơ chế provisioning được thiết kế phù hợp thường giúp giới hạn nơi bí mật phải xuất hiện. Khả năng hỗ trợ từng trường và phương thức authentication ở ứng dụng đích cần được đánh giá riêng.

## 15. Knowledge factor và tài khoản dịch vụ

**Service account/workload identity** là danh tính không thuộc một người tương tác qua bàn phím. Hệ thống không nên thiết kế job chạy ban đêm bằng cách lưu mật khẩu nhân viên trong file cấu hình hoặc yêu cầu người trực ca nhập OTP mỗi lần job khởi động.

Các cơ chế phù hợp hơn có thể gồm:

| Ngữ cảnh | Phương thức nên cân nhắc | Trách nhiệm |
|---|---|---|
| Dịch vụ chạy trên nền tảng hỗ trợ managed identity | Danh tính workload do nền tảng cung cấp | Xác định owner, quyền và môi trường |
| Dịch vụ gọi API theo cơ chế OAuth | Client credentials với client authentication thích hợp | Giới hạn scope, audience và quản lý credential |
| Dịch vụ chứng minh khóa riêng | mTLS/chứng thư hoặc token ràng buộc với khóa | Quản trị khóa, certificate và revocation |
| Legacy job cần secret | Secret manager, credential riêng cho workload | Rotate, giảm quyền, log và kế hoạch loại bỏ secret tĩnh |

Credential máy **không phải knowledge factor của một nhân viên** chỉ vì được viết dưới dạng chuỗi trong cấu hình. Cần phân loại đúng danh tính workload, owner kỹ thuật, phạm vi API và vòng đời credential.

Khi người quản trị service account rời tổ chức, phải kiểm tra họ có từng biết hoặc tải secret hay không; **thu hồi quyền quản lý và xoay vòng credential khi rủi ro/chính sách yêu cầu**, đồng thời bảo vệ tính liên tục của workload. Không tự xóa một account máy đang phục vụ production mà chưa đánh giá phụ thuộc.

## 16. Tình huống thực hành 1: mật khẩu và câu hỏi bí mật

**Bối cảnh:** Một hệ thống nội bộ yêu cầu nhân viên đăng nhập bằng password. Sau khi nhập đúng, hệ thống hỏi “Tên thú cưng đầu tiên của bạn?” và quảng cáo là “MFA hai lớp”.

**Phân tích:**

1. Password là knowledge factor.
2. Đáp án câu hỏi bí mật cũng là kiến thức, thường không phải bí mật chất lượng cao.
3. Hai bước không tự tạo hai nhóm yếu tố; nhãn “MFA” gây hiểu lầm.
4. Kẻ tấn công có thể thu thập thông tin đời tư hoặc dữ liệu từ nguồn khác để tìm đáp án.
5. Cần đánh giá chuyển sang authenticator thuộc nhóm khác có cơ chế phù hợp rủi ro, ưu tiên chống phishing khi có thể.

**Bài học:** MFA là vấn đề **cấu trúc yếu tố và chất lượng kiểm chứng**, không phải số màn hình hỏi thông tin.

## 17. Tình huống thực hành 2: password reset trở thành điểm yếu

**Bối cảnh:** Hệ thống của doanh nghiệp yêu cầu password + security key để đăng nhập. Khi quên mật khẩu, người dùng chỉ cần trả lời câu hỏi bí mật và nhận mật khẩu mới qua email do họ tự khai trước đó. Một nhà thầu đã rời dự án vẫn biết đáp án câu hỏi của account.

**Rủi ro:** Quy trình recovery có thể **bỏ qua nhiều kiểm soát MFA của luồng thông thường**. Nếu email hoặc dữ liệu KBA bị chiếm, account có thể được đặt lại trái phép. Với Leaver, bản thân account không còn điều kiện truy cập nên recovery cũng **không được mở lại** quyền làm việc.

**Hướng xử lý:**

- Bảo đảm account và engagement đang đủ điều kiện **trước khi cho phép recovery**.
- Dùng quy trình khôi phục có xác minh thích hợp và kênh đã được bảo vệ; không tự tin vào một câu hỏi bí mật.
- Giới hạn yêu cầu reset, ghi log, cảnh báo sự kiện rủi ro.
- Đánh giá thu hồi phiên, authenticator và token đã phát trước đó nếu nghi ngờ account takeover.
- Tách reset knowledge factor khỏi quyết định cấp quyền và kích hoạt tài khoản.

## 18. Tình huống thực hành 3: đổi vai trò nhưng phiên cũ còn quyền

**Bối cảnh:** Thu chuyển từ Sales sang Finance. Thu vẫn biết password và hoàn tất MFA đúng; ứng dụng vẫn còn phiên chứa quyền xem dữ liệu khách hàng của Sales.

**Vấn đề không nằm ở đâu?** Không nhất thiết nằm ở password. Người dùng có thể xác thực đúng là Thu, nhưng quyền nghiệp vụ không được cập nhật.

**Cần làm gì?**

1. Xác nhận sự kiện Mover từ nguồn có thẩm quyền.
2. Cập nhật RBAC/ABAC, gỡ quyền Sales không còn hợp lệ; thêm quyền Finance có căn cứ.
3. Đồng bộ qua IdP, SCIM/API hoặc cơ chế từng ứng dụng.
4. Kiểm tra phiên, token và cache chứa claim cũ; áp giới hạn thu hồi theo chính sách.
5. Readback quyền hiệu dụng ở ứng dụng và API, không chỉ nhìn kết quả login.
6. Nếu Finance cần mức bảo đảm cao hơn, yêu cầu step-up/authenticator phù hợp nhưng không lấy MFA làm thay thế authorization.

**Kết luận:** **Knowledge factor đúng + MFA đúng** vẫn có thể đi kèm **authorization sai** nếu Mover không xử lý quyền cũ.

## 19. Kiểm toán và chỉ số chất lượng liên quan knowledge factor

Không nên lưu mật khẩu hay PIN để “làm bằng chứng”. Log nên chỉ thể hiện **yếu tố nào được yêu cầu, kết quả thành công/thất bại, chính sách nào áp dụng và nguồn dữ liệu danh tính**.

| Nhóm | Bằng chứng hữu ích | Không được mặc định lưu |
|---|---|---|
| Sự kiện đăng nhập | Correlation ID, thời điểm, client, trạng thái | Plaintext password, OTP, PIN |
| Kiểm chứng yếu tố | Knowledge verified/failed, loại authenticator theo chính sách | Giá trị bí mật hoặc password verifier có thể lạm dụng |
| MFA/step-up | Yêu cầu và kết quả, mức bảo đảm nếu có | Dữ liệu sinh trắc thô không cần thiết |
| Rủi ro | Tín hiệu tấn công, rate limit, cảnh báo bất thường | Thông tin thiết bị/vị trí quá mức cần thiết |
| Recovery | Ai yêu cầu, phương thức xác minh, kết quả, người phê duyệt | Recovery code nguyên văn |
| JML | Account/engagement có hiệu lực, lần đổi quyền, mốc Leaver | Toàn bộ hồ sơ HR hoặc giấy tờ cá nhân |
| Session/token | Trạng thái, ID tham chiếu bảo vệ, thời điểm thu hồi | Token có thể dùng trực tiếp |

Một số chỉ số gợi ý:

- **MFA coverage:** Tỷ lệ account/ứng dụng thuộc phạm vi bắt buộc đang đáp ứng chính sách yếu tố.
- **Phishing-resistant coverage:** Tỷ lệ truy cập nhạy cảm sử dụng authenticator chống phishing khi chính sách yêu cầu.
- **Password reset rate:** Số lần reset và nguyên nhân; phân biệt nhu cầu hợp lệ với dấu hiệu tấn công.
- **Account recovery exception rate:** Tỷ lệ trường hợp cần hỗ trợ thủ công hoặc kiểm tra bổ sung, theo rủi ro.
- **Credential compromise incidents:** Sự kiện bí mật bị lộ, password spraying/stuffing và biện pháp phản ứng.
- **Time to revoke after Leaver:** Từ thời điểm chấm dứt tới khi mọi đường truy cập bắt buộc không còn hiệu lực.
- **Authentication failure analysis:** Phân tích theo nguyên nhân mà không làm lộ account tồn tại hay bí mật.
- **User support impact:** Trở ngại đăng nhập, mất authenticator, khả năng tiếp cận và thời gian khắc phục an toàn.

**Không có một ngưỡng duy nhất phù hợp mọi môi trường.** Đánh giá thành công phải kết hợp **mức bảo đảm xác thực, tính an toàn của recovery, khả năng truy cập hợp lệ và trạng thái quyền thực tế**.

## 20. Câu hỏi tự kiểm tra

**Câu 1.** Ứng dụng yêu cầu mật khẩu và PIN riêng để đăng nhập. Đây đã là MFA chưa?

**Gợi ý:** Chưa. Nếu cả hai chỉ là thông tin người dùng biết, hệ thống đang sử dụng hai knowledge secrets.

**Câu 2.** Người dùng nhập mã TOTP từ ứng dụng xác thực. Vì sao mã không được phân loại đơn giản là “knowledge” chỉ vì người dùng nhìn thấy nó?

**Gợi ý:** Loại yếu tố phụ thuộc **authenticator tạo mã và cơ chế kiểm chứng**, không chỉ cách mã được nhập.

**Câu 3.** PIN dùng để mở khóa passkey khác PIN gửi trực tiếp tới server ở điểm nào?

**Gợi ý:** PIN cục bộ kích hoạt/kiểm chứng người dùng tại authenticator; server thường kiểm chứng phản hồi mật mã. PIN từ xa có thể được dùng như knowledge secret tại verifier.

**Câu 4.** Một kẻ tấn công biết password nhưng không có khóa bảo mật. MFA giúp gì?

**Gợi ý:** Yếu tố sở hữu được xác minh độc lập có thể ngăn đăng nhập chỉ bằng password; mức bảo vệ tùy phương thức và các đường recovery/phiên.

**Câu 5.** Có nên yêu cầu mọi nhân viên đổi password khi chuyển từ Sales sang Finance?

**Gợi ý:** Không phải mặc định. Phải cập nhật quyền RBAC/ABAC và đánh giá yêu cầu authenticator/step-up theo vai trò mới; đổi mật khẩu khi có căn cứ chính sách hoặc rủi ro.

**Câu 6.** Người đã nghỉ việc còn nhớ đúng mật khẩu nhưng account bị disable. Có nên cho đăng nhập?

**Gợi ý:** Không. Trạng thái Leaver và chính sách truy cập phải được thực thi; cần xử lý cả phiên/token và account đích còn tồn dư.

**Câu 7.** Nhân viên quên mật khẩu, helpdesk xin mã OTP để “xác minh nhanh”. Cách đó có phù hợp không?

**Gợi ý:** Không nên yêu cầu người dùng tiết lộ OTP hoặc mật khẩu cho nhân viên hỗ trợ. Phải dùng quy trình recovery chính thức có bảo vệ.

**Câu 8.** Một service account chạy job hằng đêm cần gọi API. Nên dùng mật khẩu cá nhân của trưởng nhóm không?

**Gợi ý:** Không. Cần danh tính workload riêng, credential và owner kỹ thuật được quản lý, quyền tối thiểu và kế hoạch thu hồi.

## 21. Checklist thiết kế knowledge factor trong IAM

- [ ] **Phân loại đúng:** Password, passphrase và PIN được hiểu theo cơ chế; không nhầm hai bí mật ghi nhớ thành MFA.
- [ ] **Identity:** Account gắn đúng subject đã được proofing và nguồn quản lý có thẩm quyền.
- [ ] **Mật khẩu:** Cho phép bí mật khó đoán, dùng riêng; hỗ trợ password manager và hạn chế bí mật phổ biến/đã lộ.
- [ ] **Truyền và lưu:** Không ghi plaintext password; dùng kênh bảo vệ, KDF/password verifier có salt và tham số phù hợp.
- [ ] **Đăng nhập:** Có chống đoán trực tuyến, bảo vệ chống enumeration và xử lý lockout an toàn.
- [ ] **MFA:** Khi policy yêu cầu, authenticator từ nhóm khác được đăng ký/kiểm chứng đúng; cân nhắc chống phishing.
- [ ] **PIN/passkey:** Đã phân biệt PIN thiết bị cục bộ với knowledge secret gửi tới server, không “đếm đôi” yếu tố.
- [ ] **Recovery:** Reset mật khẩu/đổi authenticator được xác minh theo rủi ro, không chỉ dựa câu hỏi bí mật.
- [ ] **IdP/SSO:** Ứng dụng kiểm chứng kết quả OIDC/SAML, không nhầm authentication với provisioning hoặc authorization.
- [ ] **RBAC/ABAC:** API kiểm tra entitlement hiện hành, kể cả khi knowledge factor và MFA đã đạt.
- [ ] **Joiner:** Chỉ kích hoạt account đúng thời điểm, enrollment và hướng dẫn đăng nhập từ kênh chính thức.
- [ ] **Mover:** Đánh giá lại role, scope, step-up và phiên chứa quyền cũ; không chỉ đổi mật khẩu.
- [ ] **Leaver:** Disable/deprovision, xử lý phiên/token và account local, đối soát quyền truy cập tồn dư.
- [ ] **Service account:** Không dùng credential con người cho workload; owner, quyền và vòng đời bí mật rõ ràng.
- [ ] **Kiểm toán:** Có kết quả xác thực, policy version, correlation ID nhưng không thu thập bí mật.
- [ ] **Tính tiếp cận:** Người dùng có phương án đăng nhập/khôi phục an toàn khi mất thiết bị hoặc khó sử dụng phương thức mặc định.

**Ghi nhớ:** **Knowledge factor** là yếu tố xác thực dựa trên **thông tin bí mật mà chủ thể biết**, điển hình là password, passphrase hoặc PIN theo ngữ cảnh. Hai knowledge secrets **không tự tạo MFA**; MFA cần các nhóm yếu tố phù hợp và cơ chế kiểm chứng an toàn. Trong quản lý vòng đời IAM, knowledge factor phải được bảo vệ từ **Joiner** (đăng ký), qua **Mover** (điều chỉnh yêu cầu theo rủi ro) đến **Leaver** (vô hiệu hóa tài khoản và thu hồi phiên/token). Kết hợp **IdP/SSO, SCIM, RBAC/ABAC, kiểm toán và quản trị tài khoản dịch vụ** mới giúp bảo vệ truy cập hợp lệ mà không giữ lại quyền dư thừa.
