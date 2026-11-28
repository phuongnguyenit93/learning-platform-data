# Multi-factor authentication — Xác thực đa yếu tố

## 1. MFA bảo vệ điều gì?

**Multi-factor authentication (MFA)** yêu cầu bằng chứng từ ít nhất hai loại yếu tố xác thực khác nhau. Mục tiêu là làm cho việc biết hoặc đánh cắp một bí mật không đủ để hoàn tất xác thực.

Ví dụ, An dùng mật khẩu để đăng nhập cổng nhân sự. Nếu mật khẩu bị lộ ở một dịch vụ khác, kẻ tấn công có thể thử nó trên cổng này. Khi cổng còn yêu cầu bằng chứng từ authenticator mà An kiểm soát, chỉ có mật khẩu chưa đủ để truy cập.

OWASP phân biệt ba nhóm yếu tố cơ bản: điều người dùng biết, thứ người dùng có và đặc điểm của người dùng. Hai bí mật cùng thuộc một nhóm không tự tạo thành MFA. [OWASP Multifactor Authentication Cheat Sheet — Introduction](https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html#introduction).

MFA giảm nguy cơ chiếm tài khoản, nhưng hiệu quả phụ thuộc phương thức và toàn bộ vòng đời. Một màn hình nhập OTP không bảo vệ được hệ thống nếu API cho phép bỏ qua nó hoặc helpdesk có thể tùy tiện tắt yêu cầu MFA.

## 2. Phân biệt yếu tố với số bước và số thiết bị

| Nhóm yếu tố | Ý nghĩa | Ví dụ |
|---|---|---|
| Something you know | Bí mật mà người dùng biết | Mật khẩu, PIN dùng đúng vai trò |
| Something you have | Quyền kiểm soát authenticator hoặc khóa | Thiết bị TOTP, khóa bảo mật, phương tiện giữ khóa riêng |
| Something you are | Đặc điểm được so khớp bằng cơ chế sinh trắc học | Vân tay hoặc khuôn mặt trong cơ chế phù hợp |

Ba khái niệm cần tách rõ:

- **Số bước:** có bao nhiêu lần người dùng thao tác.
- **Số thiết bị:** có bao nhiêu vật thể tham gia.
- **Số loại yếu tố:** có những loại bằng chứng nào thực sự được xác minh.

Trong ví dụ học tập, mật khẩu rồi PIN trên cùng website là hai bước nhưng đều thuộc nhóm “biết”. Hai mật khẩu khác nhau cũng không tự tạo hai loại yếu tố. Ngược lại, một authenticator có thể kết hợp quyền kiểm soát khóa với PIN hoặc sinh trắc học để thực hiện một sự kiện xác thực đa yếu tố.

NIST SP 800-63B-4 cho phép một multi-factor authenticator hoặc tổ hợp các yếu tố riêng theo yêu cầu của mức áp dụng. Tín hiệu rủi ro như IP hoặc vị trí không thay thế một yếu tố xác thực. [NIST SP 800-63B-4 — Authentication Assurance Levels](https://pages.nist.gov/800-63-4/sp800-63b/aal/).

Không suy ra MFA chỉ từ giao diện có hai ô nhập. Cần theo dõi bằng chứng được tạo thế nào, verifier kiểm tra điều gì và bằng chứng được gắn với tài khoản nào.

## 3. Các cách triển khai thường gặp

| Phương thức kết hợp minh họa | Cách người dùng chứng minh | Điểm cần đánh giá |
|---|---|---|
| Mật khẩu + TOTP | Biết mật khẩu và có khả năng tạo mã từ seed | Bảo vệ seed, thời gian, số lần thử và chống dùng lại |
| Mật khẩu + mã SMS | Biết mật khẩu và nhận mã tại số đã đăng ký | Rủi ro chiếm số, hạ tầng gửi và phương án thay thế |
| Mật khẩu + phê duyệt push | Biết mật khẩu và phản hồi từ thiết bị đã gắn | Ràng buộc yêu cầu, chống phê duyệt nhầm và gửi dồn dập |
| Mật khẩu + khóa mật mã | Biết mật khẩu và tạo proof bằng khóa đã gắn | Giao thức, nguồn khóa, yêu cầu hiện diện hoặc xác minh người dùng |
| Passkey với user verification phù hợp | Dùng khóa và kích hoạt bằng PIN hoặc sinh trắc học | Kiểm tra kết quả user verification và yêu cầu của profile |

Bảng dùng để định hướng phân tích, không kết luận mọi cấu hình trong một hàng đều đáp ứng cùng mức bảo đảm. CISA lưu ý các dạng MFA không có mức chống tấn công giống nhau; phishing, push bombing và chiếm số điện thoại ảnh hưởng các phương thức khác nhau. [CISA — Implementing Phishing-Resistant MFA](https://www.cisa.gov/sites/default/files/publications/fact-sheet-implementing-phishing-resistant-mfa-508c.pdf).

### 3.1. TOTP không phải mã do máy chủ gửi qua SMS

TOTP tạo mã từ shared secret và yếu tố thời gian; thiết bị sinh mã không cần nhận một SMS mới cho mỗi lần đăng nhập. Verifier có dữ liệu cần thiết để tính và kiểm tra mã theo cơ chế. [RFC 6238 — Time-Based One-Time Password Algorithm](https://www.rfc-editor.org/rfc/rfc6238.html).

QR dùng lúc đăng ký TOTP thường mang thông tin cần để thiết lập seed. Nếu ảnh QR bị lộ, kẻ khác có thể có cùng cơ sở tạo mã. Quét được QR không tự chứng minh yếu tố đã được gắn an toàn; quy trình còn cần xác nhận và chuyển trạng thái đúng.

### 3.2. Passkey có thể gộp trải nghiệm mà vẫn dùng nhiều yếu tố

FIDO giải thích passkey có thể kết hợp quyền kiểm soát khóa với PIN hoặc sinh trắc học khi RP yêu cầu user verification. Thông tin sinh trắc học trong cơ chế xác minh cục bộ không cần được gửi cho website như một ảnh vân tay hoặc khuôn mặt. [FIDO Alliance — Passkeys](https://fidoalliance.org/passkeys/).

Một thao tác chạm để xác nhận hiện diện không tự chứng minh đã có user verification. Phía máy chủ phải kiểm tra kết quả mà giao thức cung cấp theo policy. Cũng không nên suy ra “không nhập mật khẩu” đồng nghĩa “chỉ có một yếu tố”.

## 4. Tính độc lập và giới hạn của bằng chứng

MFA nhằm tránh việc một bí mật bị lộ là đủ để truy cập. Tuy nhiên, các yếu tố có thể cùng bị ảnh hưởng bởi một sự cố.

Ví dụ, nếu mật khẩu và bản sao seed TOTP đều nằm trong một kho mà kẻ tấn công đã kiểm soát hoàn toàn, chúng có thể bị lấy cùng lúc. Điều này không biến mọi cách dùng chung thiết bị thành không phải MFA; nó cho thấy cần đánh giá nguồn thỏa hiệp chung, khả năng bảo vệ và cách phục hồi.

Sinh trắc học cũng cần được hiểu trong cơ chế cụ thể. NIST không coi một đặc điểm sinh trắc học tự thân là authenticator độc lập; việc sử dụng gắn với physical authenticator và các yêu cầu liên quan. [NIST SP 800-63B-4 — AAL2 Permitted Authenticator Types](https://pages.nist.gov/800-63-4/sp800-63b/aal/#aal2).

Trong thiết kế, hãy hỏi: nếu một thành phần bị chiếm, kẻ tấn công có lấy được cả hai bằng chứng không? Nếu điện thoại mất, còn đường nào để người dùng hợp lệ lấy lại quyền truy cập? Nếu bộ phận hỗ trợ bị lừa, họ có thể thay mọi yếu tố không?

## 5. Đăng ký và gắn yếu tố là một thao tác bảo mật

Authenticator binding là việc thiết lập liên kết giữa authenticator và tài khoản. NIST yêu cầu quản lý bản ghi yếu tố đã gắn, đặc tính của chúng và các sự kiện vòng đời; bổ sung authenticator cần điều kiện xác thực tương ứng và thông báo theo quy trình. [NIST SP 800-63B-4 — Authenticator Binding](https://pages.nist.gov/800-63-4/sp800-63b/events/).

Với TOTP, một luồng minh họa có thể gồm:

1. Xác định đúng tài khoản và quyền thực hiện đăng ký.
2. Tạo thông tin thiết lập cho authenticator mới ở trạng thái chờ.
3. Người dùng thiết lập ứng dụng và cung cấp mã xác nhận.
4. Máy chủ kiểm tra mã bằng cơ chế phù hợp.
5. Chỉ sau thành công mới đánh dấu yếu tố là hoạt động.
6. Cung cấp hướng dẫn dự phòng và thông báo cần thiết.

Đây là ví dụ thiết kế, không phải thuật toán bắt buộc cho mọi loại authenticator. Với khóa công khai, đăng ký có giao thức khác và cần kiểm tra kết quả theo giao thức đó.

Không cho rằng một session bất kỳ là đủ để thay toàn bộ phương tiện xác thực. Nếu session đã bị đánh cắp, kẻ tấn công có thể gắn yếu tố của mình và khóa người dùng thật ở ngoài. Đường bổ sung sau enrollment cần được thiết kế khác với bootstrap của một tài khoản mới chưa có yếu tố.

Bản ghi chưa xác nhận không nên tự xuất hiện như phương thức đủ điều kiện hoàn tất MFA. Ngược lại, nếu người dùng hủy đăng ký, dữ liệu thiết lập đang chờ phải được xử lý theo policy để tránh bỏ lại một đường kích hoạt ngoài dự kiến.

## 6. Backend phải phân biệt trạng thái chưa hoàn tất và hoàn tất

Xét ứng dụng yêu cầu mật khẩu cùng TOTP cho An. Một chuỗi trạng thái minh họa là:

```text
ANONYMOUS
  → Mật khẩu hợp lệ
MFA_PENDING
  → TOTP hợp lệ, đúng subject, đúng giao dịch và còn hiệu lực
AUTHENTICATED_FOR_POLICY
```

Tên trạng thái là do ví dụ đặt. Điểm quan trọng là quyền trong `MFA_PENDING` phải được giới hạn. Nó có thể cho phép tiếp tục challenge hoặc hủy, nhưng không tự được đọc hồ sơ vốn yêu cầu hoàn tất MFA.

Giao dịch chờ cần được ràng buộc với subject, mục đích, thời hạn và tiến trình xác thực. Client không được đổi `subjectId` tùy ý hoặc gửi `mfaComplete=true` để thay bằng chứng.

Ví dụ, request thứ nhất kiểm tra mật khẩu của An, nhưng request OTP lại gửi `userId=Binh`. Nếu máy chủ lấy user từ field mới mà không ràng buộc với giao dịch, hai bước có thể bị ghép sai. Từng bằng chứng đúng riêng lẻ cũng không tạo thành xác thực đúng cho cùng một chủ thể.

Trong kiến trúc nhiều instance, trạng thái giao dịch và việc tiêu thụ proof dùng một lần cần được phối hợp. Không chỉ lưu cờ trong bộ nhớ của một instance rồi giả định request sau luôn đến đúng instance đó.

## 7. OTP và push cần kiểm soát vượt ra ngoài phép so khớp

NIST đưa ra yêu cầu theo từng loại authenticator, gồm chống thử đoán, giới hạn hiệu lực và chống replay khi áp dụng. Yêu cầu OTP hoặc out-of-band cần được triển khai theo đúng cơ chế; không dùng chung một phép so chuỗi cho mọi loại proof. [NIST SP 800-63B-4 — Authenticator and Verifier Requirements](https://pages.nist.gov/800-63-4/sp800-63b/authenticators/).

Trong một bộ test TOTP, cần kiểm tra mã sai, mã ngoài cửa sổ cho phép, mã đã dùng và hai request đồng thời. Đồng hồ phía client không được tùy ý quyết định thời gian mà verifier tin cậy.

Với push, phản hồi phê duyệt phải được liên kết với yêu cầu thích hợp. Người dùng cần đủ ngữ cảnh để không phê duyệt một yêu cầu do người khác khởi tạo. Gửi lại vô hạn các prompt có thể biến mệt mỏi hoặc thao tác nhầm thành lần chấp nhận.

CISA mô tả number matching là biện pháp giảm nguy cơ phê duyệt mù và push fatigue. Nó không làm mọi cơ chế push trở thành phishing-resistant. [CISA — Implementing Number Matching in MFA Applications](https://www.cisa.gov/sites/default/files/publications/fact-sheet-implement-number-matching-in-mfa-applications-508c.pdf).

Không ghi OTP, seed, private key hoặc recovery code vào log. Metric vận hành nên dùng kết quả, loại phương thức và mã giao dịch đã được xử lý phù hợp, thay vì giá trị bí mật.

## 8. MFA không đồng nghĩa chống phishing trong mọi trường hợp

Một mã ngắn được người dùng nhập thủ công có thể bị lấy qua trang giả và chuyển tiếp ngay tới dịch vụ thật. Tính “dùng một lần” ngăn một số kiểu replay sau sử dụng, nhưng không tự ngăn việc dùng mã lần đầu bởi kẻ tấn công.

CISA phân biệt các phương thức có khả năng chống phishing với OTP hoặc push thông thường. Rủi ro chiếm số ảnh hưởng SMS/voice, còn push bombing khai thác việc phê duyệt prompt; các nguy cơ không giống nhau. [CISA — Threats to MFA](https://www.cisa.gov/sites/default/files/publications/fact-sheet-implementing-phishing-resistant-mfa-508c.pdf).

Ví dụ, một thông báo tự nhận “bộ phận IT” yêu cầu An đọc mã TOTP qua điện thoại. Nếu An cung cấp mã đúng lúc, kẻ có mật khẩu có thể hoàn tất đăng nhập. Đây không phải lỗi do thuật toán TOTP sinh mã sai; bằng chứng đã được chuyển cho bên không được phép.

Vì vậy, hướng dẫn người dùng, kênh hỗ trợ và lựa chọn phương thức phải đi cùng nhau. Không khẳng định “đã bật MFA nên mọi phishing đều thất bại”.

## 9. Phiên, step-up và các đường đăng nhập khác

Sau một sự kiện xác thực, session giúp duy trì tương tác mà không lặp lại mọi yếu tố ở mỗi request. Session secret và việc tái xác thực có vòng đời riêng. [NIST SP 800-63B-4 — Session Management](https://pages.nist.gov/800-63-4/sp800-63b/session/).

Một ứng dụng có thể yêu cầu step-up khi thực hiện thao tác nhạy cảm. Ví dụ, An đã đăng nhập để đọc hồ sơ nhưng khi thay phương tiện recovery, policy yêu cầu xác thực lại với mức và độ mới phù hợp.

Bản ghi ngữ cảnh nội bộ có thể tách như sau. Đây là schema minh họa, không phải claim chuẩn:

```yaml
subjectId: subject-an
authenticationContext:
  policyId: customer-login-v3
  completedMethods:
    - PASSWORD
    - TOTP
  completedAt: 2026-11-26T03:00:00Z
  state: COMPLETE
authorizationContext:
  tenantId: tenant-a
  roles:
    - CUSTOMER
```

Không suy ra một AAL cụ thể chỉ từ mảng tên phương thức. Cần đánh giá toàn bộ authenticator, verifier, giao thức và policy theo tiêu chuẩn áp dụng. Dấu thời gian cũng cần có ý nghĩa rõ: thời điểm phát token không luôn là thời điểm người dùng thực hiện lại MFA.

Nếu dùng IdP, RP cần nhận và kiểm tra thông tin tin cậy đủ cho policy của mình. Một redirect thành công không tự chứng minh phương thức hoặc độ mới mong muốn. Cách diễn giải kết quả phải được thống nhất với IdP; thiếu dữ liệu không nên bị coi là đã đáp ứng.

Đồng thời, kiểm kê web, mobile, API cũ, local login dự phòng và recovery. Một tài khoản được đánh dấu “MFA enabled” không có nghĩa mọi đường đi thực tế đều thực thi MFA.

## 10. Khôi phục và thu hồi phải được thiết kế trước khi mất yếu tố

Mất điện thoại, hỏng khóa hoặc thay thiết bị là các tình huống vận hành bình thường. NIST phân biệt các sự kiện binding, mất, bị đánh cắp, compromise và recovery; phương pháp khôi phục cần đáp ứng điều kiện của tài khoản và mức áp dụng. [NIST SP 800-63B-4 — Authenticator Event Management](https://pages.nist.gov/800-63-4/sp800-63b/events/).

Trong ví dụ doanh nghiệp, An có một phương tiện dự phòng đã đăng ký hoặc mã recovery được bảo vệ riêng. Khi mất điện thoại, hệ thống dùng quy trình phù hợp để khôi phục và gắn authenticator mới. Không được tự coi việc An biết tên, phòng ban hoặc mã nhân viên công khai là đủ để tắt MFA.

Cần phân biệt reset mật khẩu với khôi phục một yếu tố bị mất. Nếu reset chỉ được phép thay mật khẩu, nó không tự được xóa yếu tố TOTP đang bắt buộc. Nếu quy trình recovery cho phép thay yếu tố, phải xác định bằng chứng, thẩm quyền, thông báo và trạng thái sau thay đổi.

Khi authenticator cũ bị báo mất hoặc compromise, hệ thống cần xử lý khả năng sử dụng của nó theo quy trình. Với sự cố chiếm tài khoản, còn phải xem các phiên đang tồn tại và thay đổi recovery do kẻ tấn công đã tạo; chỉ đặt mật khẩu mới có thể chưa lấy lại toàn bộ quyền kiểm soát.

Không để phương án dự phòng trở thành lựa chọn yếu tùy ý ở mọi lần đăng nhập. Ngoại lệ hỗ trợ cần được ghi nhận và có phạm vi rõ ràng; nhân viên hỗ trợ không nên tự chọn một đường bỏ qua mà hệ thống không kiểm soát.

## 11. Một ví dụ quyết định truy cập đầy đủ

Ứng dụng quản lý chi trả giả định có ba điều kiện cho việc sửa nơi nhận tiền: đã hoàn tất policy MFA yêu cầu, xác thực còn đủ mới và có quyền sửa tài khoản chi trả đích.

An đăng nhập bằng mật khẩu, chưa nhập TOTP rồi gửi request sửa tài khoản nhận tiền. Backend phải từ chối hoặc yêu cầu hoàn tất bước còn thiếu, dù giao diện đã hiển thị tên An.

Sau khi An hoàn tất MFA, một request nhắm vào tài khoản thuộc tenant khác vẫn phải bị từ chối vì thiếu quyền. MFA chứng minh về xác thực, không tạo quyền sở hữu mọi tài nguyên.

Nếu session của An đã cũ so với policy của thao tác, ứng dụng yêu cầu bước tái xác thực thích hợp. Đây là quyết định của policy có tài liệu, không phải việc hỏi OTP lại theo cảm tính ở một số màn hình.

Kết quả cần nối được với subject, tài nguyên, policy và sự kiện xác thực. Một cờ `mfa=true` không có nguồn gốc hoặc thời điểm rõ ràng rất khó dùng để giải thích những quyết định này.

## 12. Những ca kiểm thử giúp phát hiện đường bỏ qua

Các ca dưới đây là bộ gợi ý cho ứng dụng thử nghiệm, không phải checklist chứng nhận một tiêu chuẩn:

| Tình huống | Kết quả cần kiểm tra |
|---|---|
| Đúng mật khẩu và đúng yếu tố bổ sung | Hoàn tất đúng policy cho đúng subject |
| Chỉ đúng mật khẩu | Không truy cập chức năng yêu cầu MFA đầy đủ |
| Nhảy thẳng tới endpoint hoàn tất | Không chấp nhận khi thiếu trạng thái và proof trước đó |
| OTP của giao dịch A gửi cho giao dịch B | Không ghép proof sai phạm vi |
| Mã hết hạn hoặc đã dùng | Không có lần chấp nhận mới trái cơ chế |
| Hai request cùng tiêu thụ proof | Kết quả không bị chấp nhận lặp do race |
| Đổi field user hoặc tenant ở bước sau | Không đổi chủ thể của giao dịch xác thực |
| Gọi API cũ hoặc ứng dụng mobile | Thực thi đúng yêu cầu của đường đi |
| Thêm yếu tố bằng session không đủ điều kiện | Không gắn yếu tố ngoài policy |
| Reset mật khẩu trên tài khoản có MFA | Không tự bỏ yếu tố còn bắt buộc |
| Dịch vụ MFA timeout hoặc lỗi | Không tự hạ yêu cầu để cho qua |
| Authenticator đã bị thu hồi | Không sử dụng lại chỉ vì proof mật mã còn kiểm tra được |

Kiểm thử cần có ca thành công để bảo đảm các ca âm không pass chỉ vì toàn bộ cấu hình MFA đang hỏng. Phân biệt test validator, test trạng thái backend và test đầu-cuối; một mock luôn trả thành công không chứng minh phương tiện MFA thật đã được kiểm tra.

Ở môi trường vận hành, theo dõi thay đổi yếu tố, thất bại sau khi mật khẩu đúng, lượng push bất thường và tỷ lệ recovery. Dữ liệu này cần được bảo vệ và tối thiểu hóa; không thu thập bí mật để phục vụ dashboard.

## 13. Tự kiểm tra cách hiểu

**Mật khẩu cộng PIN trên cùng website có tự là MFA không?**

Không. Chúng có thể là hai bước của cùng loại yếu tố “biết”.

**Một lần dùng passkey có thể đáp ứng MFA không?**

Có thể, khi cơ chế kết hợp quyền kiểm soát khóa với user verification phù hợp và phía xác minh kiểm tra đúng yêu cầu. Không kết luận từ số màn hình.

**TOTP là mã dùng một lần thì có chống mọi phishing không?**

Không. Kẻ tấn công có thể lấy và chuyển tiếp mã trước khi người dùng sử dụng tại dịch vụ thật.

**Đã bật MFA trên tài khoản có nghĩa mọi phiên đã hoàn tất MFA không?**

Không. Cấu hình tài khoản và kết quả của từng sự kiện xác thực là hai loại trạng thái khác nhau.

**MFA thành công có cho phép bỏ kiểm tra quyền không?**

Không. Tenant, role, tài nguyên và hành động vẫn cần authorization riêng.

