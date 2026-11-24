# Support identity verification — Xác minh danh tính khi hỗ trợ khôi phục tài khoản

## 1. Vì sao bộ phận hỗ trợ là một ranh giới bảo mật?

Khi mất mật khẩu, MFA, passkey hoặc thiết bị xác thực, người dùng có thể không còn khả năng đi qua luồng đăng nhập thông thường. Bộ phận hỗ trợ giúp họ tiếp cận quy trình thay thế, nhưng cũng trở thành mục tiêu của kẻ muốn chiếm tài khoản bằng cách thuyết phục một nhân viên có quyền cao.

Trong SECURITY_AUTHENTICATION_ACCOUNT_RECOVERY, xác minh qua hỗ trợ phải trả lời một câu hỏi cụ thể: **người đang yêu cầu có đủ bằng chứng để được phép thực hiện hành động khôi phục trên đúng tài khoản này hay chưa?**

Việc mở được ticket, đọc đúng thông tin cá nhân hoặc nói chuyện thuyết phục không tự trả lời câu hỏi đó. Nhân viên cần một quy trình có chính sách, công cụ xác minh và giới hạn quyền, thay vì quyết định theo cảm giác.

Hỗ trợ có thể điều phối các bước xác minh, xem kết quả cần thiết và chuyển hồ sơ cho người phê duyệt. Việc thay credential vẫn phải được backend kiểm tra và thực hiện bằng quyền khôi phục có phạm vi rõ ràng.

OWASP coi việc thay yếu tố MFA là hành động rủi ro cao, khuyến nghị kiểm tra lại bằng yếu tố đã đăng ký khi còn khả dụng và không chỉ dựa vào session hiện tại. Khi người dùng mất yếu tố, cần một quy trình recovery được thiết kế tương ứng, không bỏ yêu cầu xác minh vì có nhân viên tham gia. [Nguồn: OWASP Multifactor Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html#changing-mfa-factors).

## 2. Bốn câu hỏi khác nhau trong một hồ sơ hỗ trợ

| Câu hỏi | Điều cần xác định | Điều chưa được phép suy ra |
| --- | --- | --- |
| Đang nói về tài khoản nào? | Tài khoản và tenant từ dữ liệu có thẩm quyền | Người biết định danh là chủ tài khoản |
| Bằng chứng có đáng tin cậy không? | Nguồn, tính hợp lệ và kết quả kiểm tra bằng chứng | Người gửi bằng chứng là chủ thể của bằng chứng |
| Người yêu cầu có gắn với bằng chứng không? | Quyền kiểm soát hoặc sự liên kết theo phương pháp được chấp thuận | Mọi hành động trên tài khoản đều được phép |
| Hành động recovery có được phép không? | Mục đích, rủi ro, chính sách và phạm vi được phê duyệt | Được thay mọi credential hoặc đổi mọi thông tin liên hệ |

NIST SP 800-63A-4 phân biệt xác định danh tính, kiểm tra tính hợp lệ của bằng chứng và xác minh sự liên kết của người tham gia với danh tính đã được kiểm tra. Phân biệt này giúp tránh việc coi một ảnh giấy tờ là toàn bộ quá trình xác minh. Bài dùng các khái niệm đó để thiết kế hỗ trợ recovery, không tự tuyên bố quy trình minh họa đạt một IAL hoặc AAL cụ thể. [Nguồn: NIST SP 800-63A-4 — Identity Proofing](https://pages.nist.gov/800-63-4/sp800-63a.html).

Ví dụ, một người có ảnh giấy tờ mang tên Nguyễn An chưa chứng minh rằng họ đang là Nguyễn An. Ngay cả khi xác minh được danh tính thực tế của họ, vẫn cần xác định tài khoản yêu cầu khôi phục trước đây đã được gắn đáng tin cậy với danh tính đó hay chưa.

Với tài khoản đăng ký bằng bí danh và chưa từng xác minh danh tính thực tế, một giấy tờ mới xuất trình không tự chứng minh quyền sở hữu tài khoản. Không lấy tên hiển thị tự khai hoặc sự trùng tên làm cầu nối còn thiếu.

NIST SP 800-63B-4 nêu rằng recovery bằng lặp lại identity proofing cần đối chiếu với danh tính đã thiết lập trước đó; tài khoản chưa được identity-proofed không có lựa chọn reproofing theo cơ chế này. Do đó, kế hoạch recovery phải phù hợp với bằng chứng và quan hệ đã có, thay vì bổ sung một “lối tắt giấy tờ” tại quầy hỗ trợ. [Nguồn: NIST SP 800-63B-4 — Account Recovery](https://pages.nist.gov/800-63-4/sp800-63b.html#account-recovery).

## 3. Những kiểu tấn công cần đưa vào thiết kế

Kẻ tấn công có thể đã biết tên, email, số điện thoại, lịch sử giao dịch hoặc thông tin nhân sự của nạn nhân. Chúng cũng có thể kiểm soát một session, hộp thư hoặc số điện thoại đã bị chiếm.

| Tình huống | Rủi ro | Kiểm soát cần thiết |
| --- | --- | --- |
| Tự nhận là lãnh đạo cần xử lý khẩn | Nhân viên bỏ qua bước bắt buộc | Quy trình không đổi theo cấp bậc tự khai; escalation theo chính sách |
| Biết nhiều thông tin cá nhân | Thông tin lộ lọt bị coi là bí mật xác thực | Không dùng kiến thức tĩnh làm bằng chứng quyết định |
| Yêu cầu đổi email rồi gửi mã vào email mới | Kẻ tấn công tự tạo kênh chứng minh cho mình | Tách xác minh khỏi thay đổi kênh liên hệ |
| Giả caller ID hoặc tên hiển thị | Kênh giao tiếp bị nhầm là danh tính đã xác minh | Callback hoặc challenge qua kênh tin cậy đã có |
| Đưa ảnh chụp màn hình đã đăng nhập | Session bị chiếm hoặc ảnh bị chỉnh sửa | Xác minh bằng giao thức và kết quả backend |
| Gửi giấy tờ đánh cắp hoặc video giả | Hình ảnh có vẻ thuyết phục nhưng không đủ tin cậy | Phương pháp proofing có kiểm tra nguồn và người tham gia phù hợp |
| Mở nhiều ticket với nhiều nhân viên | Tìm người dễ chấp thuận hơn | Liên kết hồ sơ và giữ lịch sử quyết định |
| Sửa mục tiêu ticket sau khi được duyệt | Phê duyệt bị dùng cho hành động khác | Ràng buộc quyết định với snapshot và phạm vi bất biến |
| Nhân viên nội bộ lạm dụng quyền | Tự xác minh rồi tự đổi credential | Quyền tối thiểu, phân tách nhiệm vụ và audit |
| Dùng lại quyết định phê duyệt cũ | Một bằng chứng cấp nhiều lần quyền recovery | Hết hạn, dùng một lần và kiểm tra trạng thái hiện thời |

Không cần kết luận người yêu cầu là kẻ tấn công mới áp dụng các giới hạn. Các giới hạn là điều kiện thông thường của hành động nhạy cảm, áp dụng nhất quán cho mọi hồ sơ tương ứng.

## 4. Chọn bằng chứng theo chính sách và quan hệ với tài khoản

### Ưu tiên phương pháp đã được chuẩn bị trước

Một tài khoản có thể đã đăng ký yếu tố dự phòng, recovery code hoặc recovery contact. Hỗ trợ nên hướng người dùng vào trình xác minh chính thức cho các phương pháp được phép, thay vì tự yêu cầu họ đọc bí mật qua cuộc gọi.

Những phương pháp có thể được xem xét tùy chính sách:

| Phương pháp | Giá trị có thể cung cấp | Giới hạn phải đánh giá |
| --- | --- | --- |
| Yếu tố đã đăng ký còn sử dụng được | Chứng minh quyền kiểm soát yếu tố gắn với tài khoản | Phải phù hợp mục đích; session đang mở không thay thế yếu tố |
| Recovery code đã phát trước | Quyền recovery được hệ thống cấp từ trước | Dùng một lần, còn hiệu lực và kiểm tra qua verifier |
| Challenge tới kênh đã xác minh trước | Chứng minh quyền kiểm soát kênh đó | Kênh có thể bị chiếm; không tự đủ cho mọi hành động |
| Recovery contact đã thiết lập trước | Hỗ trợ theo quan hệ recovery đã đăng ký | Phải kiểm tra đúng contact và phạm vi chính sách |
| Xác minh lại danh tính đã gắn với tài khoản | Đối chiếu với quan hệ định danh có từ trước | Cần phương pháp và nguồn phù hợp, không chỉ nhìn ảnh |
| Nguồn tổ chức có thẩm quyền | Đối chiếu nhân sự hoặc quyền quản trị đã thiết lập | Không tin email giới thiệu mới hoặc người tự nhận là quản lý |

Không có quy tắc chung rằng “hai bằng chứng bất kỳ” luôn đủ. Hai ảnh chụp cùng lấy từ một email bị chiếm không tạo ra hai nguồn độc lập. Một email và số điện thoại được đổi cùng lúc bởi kẻ tấn công cũng không nhất thiết bổ sung mức tin cậy đáng kể.

Một cuộc gọi đến số đã lưu có thể hữu ích trong một chính sách, nhưng không xóa rủi ro chuyển hướng cuộc gọi hoặc chiếm số. Một địa chỉ email quen thuộc cũng không mặc định là kênh an toàn khi sự cố đang nghi ngờ liên quan tới chính hộp thư đó.

### Các thông tin chỉ có vai trò hỗ trợ

Ngày sinh, địa chỉ, tên người thân, tên thiết bị, vài số cuối của thông tin thanh toán, mã hóa đơn hoặc nội dung email cũ có thể giúp tìm hồ sơ hoặc phát hiện mâu thuẫn. Không nên coi việc trả lời đúng các câu hỏi đó là bằng chứng duy nhất để thay MFA hoặc chuyển quyền tài khoản.

NIST SP 800-63A-4 không cho phép knowledge-based verification/authentication làm phương pháp identity verification trong phạm vi hướng dẫn đó. Đây cũng là cơ sở để tránh thiết kế help desk dựa vào câu hỏi kiến thức cá nhân tĩnh. [Nguồn: NIST SP 800-63A-4 — Identity Verification](https://pages.nist.gov/800-63-4/sp800-63a.html#identity-verification).

Không công khai dữ liệu đang lưu rồi yêu cầu người gọi xác nhận “đúng hay sai”. Cách đó có thể vừa tiết lộ thông tin nạn nhân, vừa giúp người gọi vượt qua các bước tiếp theo.

### Không yêu cầu người dùng tiết lộ bí mật cho nhân viên

Nhân viên không cần biết mật khẩu hiện tại, mã OTP đăng nhập, seed MFA, private key, session cookie hoặc toàn bộ recovery code.

Nếu recovery code là phương thức được chấp thuận, người dùng nhập vào giao diện verifier chính thức; nhân viên chỉ xem kết quả và phạm vi được xác nhận. Tương tự, kết quả kiểm tra yếu tố nên đến từ backend, không từ ảnh chụp màn hình do người dùng gửi.

Không yêu cầu cài công cụ điều khiển máy từ xa hoặc chia sẻ toàn bộ màn hình có bí mật chỉ để chứng minh quyền sở hữu. Kênh thu thập bằng chứng phải có phạm vi và hướng dẫn rõ ràng.

## 5. Phân loại yêu cầu trước khi thu thập bằng chứng

Mỗi hồ sơ cần có mục đích cụ thể. “Không đăng nhập được” là mô tả sự cố, chưa phải phạm vi cấp quyền.

| Loại yêu cầu | Điều cần làm rõ | Thao tác không tự đi kèm |
| --- | --- | --- |
| Mất mật khẩu | Còn yếu tố hoặc phương thức recovery nào? | Tắt MFA hoặc đổi email |
| Mất MFA | Mất một yếu tố hay toàn bộ lựa chọn xác thực? | Đặt mật khẩu thay người dùng |
| Mất passkey | Còn credential khác hoặc đường recovery nào? | Khôi phục private key từ server |
| Mất thiết bị | Những authenticator và session nào bị ảnh hưởng? | Thu hồi mọi tài khoản hoặc tenant liên quan |
| Nghi tài khoản bị chiếm | Kênh nào còn đáng tin cậy và bằng chứng nào có thể đã lộ? | Tin session hoặc hộp thư hiện tại một cách mặc định |
| Yêu cầu từ tổ chức | Người yêu cầu có quyền quản trị đã được xác định không? | Chuyển quyền sở hữu cá nhân theo lời giới thiệu |

Nếu yêu cầu thực tế là đăng ký yếu tố mới sau khi đã xác thực bằng yếu tố còn lại, cần áp dụng luồng binding/replacement phù hợp. Không hạ mức kiểm soát chỉ vì ticket được gắn nhãn “hỗ trợ”.

NIST phân biệt account recovery với trường hợp quên mật khẩu nhưng vẫn xác thực được bằng authenticator khác. Trong bài, bộ phận hỗ trợ cần phân loại đúng để chọn quy trình, thay vì dùng một quyền “reset everything” cho mọi tình huống. [Nguồn: NIST SP 800-63B-4 — Account Recovery](https://pages.nist.gov/800-63-4/sp800-63b.html#account-recovery).

Chỉ thu thập loại bằng chứng cần cho quy trình được chọn. Một dịch vụ không cần xác minh danh tính thực tế không nên mặc định yêu cầu giấy tờ và sinh trắc học cho mọi lần đặt lại mật khẩu.

## 6. Quy trình hỗ trợ có các điểm quyết định rõ ràng

Một workflow minh họa:

~~~mermaid
flowchart TD
    A[Tiếp nhận và xác định mục đích] --> B[Đánh giá phương thức recovery được phép]
    B --> C[Thu thập qua kênh được bảo vệ]
    C --> D[Kiểm tra bằng chứng và liên kết tài khoản]
    D --> E{Đủ điều kiện chính sách?}
    E -->|Chưa đủ| F[Bổ sung hoặc chuyển tuyến phù hợp]
    E -->|Không đạt| G[Từ chối hoặc đóng hồ sơ]
    E -->|Đạt| H[Phê duyệt có phạm vi]
    H --> I[Chờ và thông báo nếu chính sách yêu cầu]
    I --> J[Backend kiểm tra lại trước thực thi]
    J --> K[Recovery dùng một lần và xử lý session]
~~~

### Tiếp nhận

Tạo case_id, ghi mục đích được yêu cầu và nguồn tiếp nhận. Giới hạn dữ liệu khai báo ban đầu, không coi lời khai là dữ kiện đã xác minh.

Phản hồi công khai không nên cho người ngoài suy ra tài khoản tồn tại hay các phương thức đã đăng ký. Với đặt lại mật khẩu, OWASP khuyến nghị phản hồi nhất quán cho tài khoản tồn tại và không tồn tại; hệ thống hỗ trợ cũng cần tránh lộ các khác biệt qua ticket receipt hoặc câu trả lời tự động. [Nguồn: OWASP Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html#forgot-password-request).

### Đánh giá rủi ro

Xem xét loại tài khoản, quyền quản trị, thay đổi kênh liên hệ gần đây, sự kiện bảo mật và mâu thuẫn bằng chứng. Các tín hiệu này quyết định kiểm tra bổ sung hoặc chuyển tuyến, không tự thay thế bằng chứng.

Không để việc tự khai “đang ở nước ngoài” hoặc “điện thoại bị mất” vô hiệu hóa các kiểm soát phát hiện rủi ro. Đồng thời, một vị trí mới không tự chứng minh gian lận; người dùng hợp lệ cũng có thể đổi thiết bị và địa điểm.

### Thu thập và đánh giá

Người dùng cung cấp bằng chứng qua kênh đã được chọn. Hệ thống ghi nhận evidence_ref, nguồn, kết quả kiểm tra và phiên bản bundle. Nhân viên chỉ xem những phần cần cho nhiệm vụ.

Một kết quả “bằng chứng đã được tải lên” khác với “bằng chứng đã được kiểm tra hợp lệ”, và cả hai đều khác với “đã xác nhận liên kết với tài khoản”.

### Phê duyệt và thực thi

Quyết định cần ghi rõ hành động được cho phép, điều kiện bổ sung, thời điểm hết hạn và dữ liệu đã được xét duyệt. Backend kiểm tra lại các điều kiện tại thời điểm sử dụng, vì trạng thái tài khoản có thể thay đổi sau khi nhân viên phê duyệt.

Nếu thiếu bằng chứng, chuyển sang phương thức hoặc tuyến xử lý khác đã được chính sách cho phép. Không tự tạo một câu hỏi phụ dễ hơn để đạt đủ số bước trên giao diện.

## 7. Phân quyền giữa người tiếp nhận, người đánh giá và hệ thống

Một nhân viên có thể hỗ trợ nhiều bước, nhưng quyền kỹ thuật không nên cho phép họ tự bỏ qua những bước còn thiếu.

| Vai trò | Có thể được phép | Không mặc định được phép |
| --- | --- | --- |
| Người tiếp nhận | Tạo hồ sơ, giải thích quy trình, đề nghị đúng loại bằng chứng | Tắt MFA, đổi email, phát session |
| Người đánh giá | Xem bằng chứng cần thiết, ghi nhận kết quả theo phương pháp | Tự sửa dữ kiện tài khoản để làm bằng chứng khớp |
| Người phê duyệt | Chấp thuận phạm vi recovery trong thẩm quyền | Phê duyệt quyền rộng hơn hồ sơ đã đánh giá |
| Recovery service | Kiểm tra quyết định và thực thi thao tác được phép | Tin riêng trạng thái “approved” trên hệ thống ticket |
| Nhóm bảo mật | Xử lý dấu hiệu xâm nhập hoặc ngoại lệ được định nghĩa | Dùng ngoại lệ không có phạm vi hoặc không có audit |

Với thao tác rủi ro cao, có thể yêu cầu người phê duyệt độc lập với người đánh giá. Đây là kiểm soát bổ sung theo chính sách, không phải quy tắc rằng cứ có hai nhân viên là mọi bằng chứng yếu trở nên đủ mạnh.

Quyền của nhân viên cần gắn với tenant, loại tài khoản và loại hành động. Một người được xem ticket không tự có quyền xem toàn bộ hồ sơ định danh hoặc thực thi recovery cho quản trị viên của tenant khác.

Công cụ hỗ trợ nên cho thấy các trạng thái có cấu trúc: nguồn đã xác nhận, bước còn thiếu, thời hạn và phạm vi. Không cung cấp một nút “bypass” chung để sửa trực tiếp account record, chạy SQL hoặc đặt credential thay người dùng.

Nếu có cơ chế khẩn cấp, nó phải là một quy trình ngoại lệ riêng với quyền hạn, lý do, phê duyệt, phạm vi và dấu vết tương ứng. Tên gọi “khẩn cấp” không biến lời khai thành bằng chứng.

## 8. Biến kết quả xác minh thành một quyết định có phạm vi

Một trạng thái trên ticket chỉ hỗ trợ điều phối công việc. Quyền thực thi recovery cần được lưu và kiểm tra trong hệ thống có thẩm quyền.

Ví dụ một bản ghi quyết định nội bộ:

~~~json
{
  "decision_id": "decision-ref-82",
  "case_id": "case-ref-17",
  "case_version": 6,
  "tenant_ref": "tenant-ref-3",
  "account_ref": "account-ref-41",
  "purpose": "MFA_REPLACEMENT",
  "allowed_action": "START_MFA_REENROLLMENT",
  "policy_version": "support-mfa-v4",
  "evidence_bundle_ref": "evidence-bundle-ref-9",
  "evidence_bundle_version": 4,
  "account_security_epoch": 12,
  "recovery_contact_version": 7,
  "reviewer_ref": "staff-ref-21",
  "approver_ref": "staff-ref-35",
  "approved_at": "2026-11-24T05:00:00Z",
  "not_before": "2026-11-24T05:15:00Z",
  "expires_at": "2026-11-24T05:30:00Z",
  "state": "APPROVED"
}
~~~

Các ID và thời gian chỉ là minh họa. Khoảng chờ và hạn dùng phải do chính sách thực tế xác định; không sao chép các con số này như một mức an toàn phổ quát.

Bản ghi trên không phải bearer token để gửi cho người dùng. decision_id chỉ là tham chiếu, không đủ để được thực thi. Nếu có grant hoặc đường dẫn dành cho người dùng, đó phải là cơ chế cấp quyền riêng, được bảo vệ, ràng buộc mục đích và dùng một lần.

allowed_action = START_MFA_REENROLLMENT không có nghĩa tắt toàn bộ MFA, đổi email, đặt mật khẩu mới hoặc tạo một session đầy đủ. Những hành động khác cần phạm vi và điều kiện riêng.

### Gắn quyết định với dữ liệu đã được xét duyệt

case_version và evidence_bundle_version giúp chỉ ra snapshot đã được đánh giá. Bundle đã phê duyệt cần bất biến hoặc có cơ chế phát hiện thay đổi. Nếu đổi tài khoản đích, mục đích hoặc bằng chứng, không giữ nguyên phê duyệt cũ rồi tiếp tục.

account_security_epoch và recovery_contact_version cho phép phát hiện một số thay đổi bảo mật kể từ lúc phê duyệt. Chúng phải là giá trị từ dữ liệu có thẩm quyền, không do nhân viên gõ vào hoặc cập nhật lại cho khớp khi sử dụng.

Khi tài khoản vừa thay yếu tố, vừa đổi kênh liên hệ hoặc xuất hiện sự kiện bảo mật mới, cần đánh giá lại theo chính sách. Không “làm mới” bản ghi phê duyệt bằng cách chỉ đổi timestamp hoặc epoch.

### Không dùng việc đổi kênh để tự chứng minh

Một chuỗi nguy hiểm là:

~~~text
Người gọi khai mất mọi yếu tố.
Nhân viên đổi email theo đề nghị.
Hệ thống gửi mã tới email mới.
Người gọi nhập đúng mã.
Nhân viên kết luận đã chứng minh quyền sở hữu tài khoản.
~~~

Mã chỉ chứng minh người gọi kiểm soát email do chính họ vừa chọn. Nó không chứng minh quan hệ trước đó với tài khoản.

Nếu quy trình hợp lệ cuối cùng cho phép thêm kênh mới, việc đó phải xảy ra sau khi đủ điều kiện độc lập và trong phạm vi được phê duyệt. Không dùng chính kênh mới làm bằng chứng duy nhất để phê duyệt thay đổi đó.

## 9. Backend kiểm tra lại trước khi cấp quyền recovery

Một quy trình thực thi minh họa:

~~~text
nhận yêu cầu sử dụng quyết định
xác minh chủ thể và quyền gọi dịch vụ
tải account, decision và workflow có thẩm quyền
khóa hoặc kiểm soát cập nhật đồng thời theo thứ tự nhất quán

kiểm tra:
    quyết định chưa dùng, chưa thu hồi và chưa hết hạn
    đã tới not_before nếu có thời gian chờ
    tenant, account, purpose và action khớp chính xác
    snapshot bằng chứng vẫn là snapshot đã được phê duyệt
    policy cho phép sử dụng quyết định này ở trạng thái hiện tại
    epoch và các version bảo mật còn phù hợp
    không có hold hoặc quyết định bảo mật mới ngăn thực thi

commit:
    đánh dấu quyết định đã dùng
    tạo hoặc chuyển workflow sang đúng bước được cho phép
    ghi audit/outbox tương ứng
~~~

Ví dụ này cấp quyền vào bước đăng ký lại MFA. Nếu hệ thống chọn dùng quyết định để trực tiếp thực hiện một thay đổi khác, phải định nghĩa rõ thay đổi đó và commit tính dùng một lần cùng thao tác cần bảo vệ.

Không đánh dấu quyết định đã dùng trong một transaction rồi thực hiện một thay đổi không idempotent ở dịch vụ khác mà không có kế hoạch phục hồi. Với thành phần bên ngoài, cần operation_id, trạng thái trung gian và đối soát; timeout không luôn có nghĩa thao tác chưa xảy ra.

Retry cùng một thao tác phải trả lại hoặc tiếp tục kết quả theo hợp đồng. Nó không được tạo thêm quyền recovery. Nếu quyết định hết hạn trước khi người dùng hoàn tất, không gia hạn ngầm; cần đánh giá hoặc phát hành lại theo chính sách.

Ở bước người dùng sử dụng quyền thực sự, backend vẫn kiểm tra token dùng một lần, hạn dùng, mục đích, giới hạn thử và trạng thái tài khoản. Ticket được phê duyệt không thay thế những kiểm tra đó.

Không khôi phục private key passkey hoặc seed MFA cũ bằng một quyết định hỗ trợ. Quy trình có thể cho phép đăng ký credential mới và thu hồi credential bị mất theo phạm vi đã xác định.

## 10. Thông báo, thời gian chờ và kiểm soát session

### Thông báo là khả năng phát hiện và phản ứng

Thông báo qua các kênh tin cậy đã có giúp chủ tài khoản biết yêu cầu hoặc thay đổi quan trọng. Nội dung nên nêu loại hành động, thời điểm và đường phản hồi chính thức, không chứa mật khẩu, OTP hoặc toàn bộ bằng chứng.

Không coi email gửi thành công là bằng chứng người dùng đã đọc. Không coi việc không có ai phản đối trong thời gian chờ là kết quả identity verification.

Nếu một kênh nghi đã bị chiếm, cần áp dụng phương án thông báo và xác minh theo đánh giá rủi ro. Không dùng sự im lặng của kênh đó để xóa tín hiệu rủi ro.

Thời gian chờ có thể giúp phát hiện hoặc ngăn một số thay đổi vội vã, nhưng không sửa được bằng chứng không đủ. Một hồ sơ không đủ điều kiện sau khi chờ vẫn không đủ điều kiện.

### Không tự tạo ra khóa tài khoản từ lời khai chưa xác minh

Người ngoài có thể cố gửi nhiều hồ sơ “mất thiết bị” để làm nạn nhân mất quyền truy cập. Việc mở ticket không nên mặc định tắt mọi credential hoặc khóa toàn bộ tài khoản.

Giới hạn lần thử, chống gửi trùng, giới hạn tải và việc gom các hồ sơ liên quan cần áp dụng cho kênh hỗ trợ. Hành động phòng vệ ảnh hưởng tài khoản phải dựa trên chính sách và dữ kiện phù hợp, không chỉ một lời khai chưa xác minh.

Không dùng một quyết định từ chối hồ sơ làm lý do tự động đặt lại mật khẩu hoặc thu hồi session của người bị nhắm tới.

### Sau khi recovery thực sự được thực hiện

Cần có chính sách về credential cũ, recovery grant khác và session đang tồn tại. Phạm vi tùy loại recovery và tình huống xâm nhập; không coi việc đăng ký yếu tố mới tự thu hồi các session cũ.

Có thể dùng security epoch, danh sách thu hồi hoặc tác vụ dịch vụ session theo thiết kế. Nếu việc thu hồi còn đang chờ ở dịch vụ bên ngoài, phải giữ trạng thái đó rõ ràng và kiểm soát khoảng chờ theo chính sách; không báo “mọi session đã vô hiệu” chỉ vì đã gửi lệnh.

Người dùng tiếp tục qua cơ chế đăng nhập được thiết kế sau recovery. Nhân viên không cần lấy session đăng nhập thay người dùng hoặc gửi credential mới qua ticket.

## 11. Quản lý bằng chứng và dấu vết quyết định

Hồ sơ hỗ trợ có thể chứa thông tin nhạy cảm hơn log đăng nhập thông thường. Nên tách metadata điều phối khỏi nội dung bằng chứng.

| Nhóm | Dữ liệu phù hợp | Giới hạn |
| --- | --- | --- |
| Ticket điều phối | Case ID, mục đích, trạng thái, bước tiếp theo | Không chứa bí mật hoặc bản sao toàn bộ giấy tờ |
| Kho bằng chứng | Nội dung cần thiết theo phương pháp đã chọn | Quyền đọc hẹp, kênh bảo vệ và thời hạn lưu |
| Kết quả xác minh | Evidence ref, phương pháp, kết quả, thời điểm, phiên bản | Không đánh đồng “đã thu thập” với “đã xác minh” |
| Quyết định | Người đánh giá, người phê duyệt, phạm vi, policy, snapshot | Chống sửa âm thầm sau phê duyệt |
| Audit | Sự kiện tiếp nhận, đánh giá, quyết định và thực thi | Không chứa raw token, OTP hoặc hồ sơ định danh đầy đủ |

Một audit trail có thể gồm:

~~~text
support.case.opened
support.evidence.recorded
support.evidence.evaluated
support.recovery.reviewed
support.recovery.approved
support.recovery.denied
support.recovery.authorization.consumed
recovery.authenticator.enrolled
recovery.authenticator.revoked
recovery.session_revocation.completed
~~~

Các tên này là ví dụ thiết kế. Sự kiện approval không được phát với ý nghĩa credential đã thay đổi; sự kiện thực thi chỉ phát khi hành động tương ứng đã được xác nhận.

Ghi nhận truy cập bằng chứng, thay đổi snapshot và chuyển người xử lý. Không cho một nhân viên âm thầm xóa quyết định từ chối rồi mở lại ticket như chưa từng có vấn đề.

Việc liên kết hồ sơ nên dùng ID nội bộ và phạm vi tenant đáng tin cậy. Không ghi số giấy tờ, email hoặc toàn bộ transcript vào metric label. Không tự sao chép nội dung bằng chứng vào bản export audit hoặc công cụ phân tích bên thứ ba.

Quy trình cần nói rõ dữ liệu nào phải giữ, giữ bao lâu và ai có thể truy cập. Chỉ thu thập dữ liệu phục vụ phương pháp xác minh được chọn; không tích lũy thêm giấy tờ vì “có thể hữu ích về sau”.

## 12. Hai tình huống đối chiếu

### Người dùng hợp lệ còn recovery code

Một người mất điện thoại có MFA, nhưng còn recovery code đã được phát khi thiết lập tài khoản.

Nhân viên hướng dẫn họ tới verifier chính thức. Backend kiểm tra code thuộc đúng tài khoản, còn hiệu lực, chưa dùng và áp dụng giới hạn lần thử. Nhân viên không yêu cầu đọc code qua cuộc gọi hoặc dán vào ticket.

Nếu chính sách cho phép code này mở bước đăng ký lại MFA, hệ thống cấp đúng quyền đó. Người dùng đăng ký yếu tố mới qua luồng được bảo vệ; việc thu hồi yếu tố mất và xử lý session được thực hiện theo chính sách.

Kết quả của hỗ trợ là giúp người dùng đi qua một đường recovery đã có, đồng thời giữ nguyên cơ chế dùng một lần và kiểm tra của backend.

### Người gọi biết nhiều thông tin nhưng chỉ có kênh mới

Một người tự nhận là quản trị viên quan trọng, đọc đúng tên công ty, email, số hóa đơn và đề nghị đổi sang một email mới để nhận liên kết recovery.

Thông tin đó có thể giúp tìm hồ sơ, nhưng chưa chứng minh quyền thực hiện thay đổi. Nhân viên không đổi email rồi dùng email mới làm bằng chứng và không bỏ bước vì yêu cầu khẩn.

Hồ sơ được chuyển tới phương thức recovery hoặc tuyến đánh giá phù hợp đã được quy định. Nếu không có bằng chứng đủ điều kiện, chưa cấp quyền recovery. Phản hồi giải thích bước có thể thực hiện và đường hỗ trợ tiếp theo mà không làm lộ thêm thông tin tài khoản.

Nếu người gọi thực sự là chủ tài khoản nhưng đã mất mọi phương thức hợp lệ, sự khó khăn đó vẫn cần được xử lý bằng quy trình được thiết kế trước. Nó không biến dữ liệu yếu thành bằng chứng mạnh.

## 13. Khi không đủ bằng chứng hoặc phương pháp chuẩn không sử dụng được

Một hệ thống cần có kết quả rõ ràng ngoài APPROVED:

- **NEEDS_MORE_EVIDENCE**: thiếu bằng chứng cụ thể mà chính sách cho phép bổ sung.
- **REFERRED**: chuyển tới tuyến có thẩm quyền hoặc phương pháp phù hợp khác.
- **DENIED**: dữ kiện không đạt yêu cầu hoặc có mâu thuẫn không được giải quyết.
- **EXPIRED**: hồ sơ hoặc quyết định đã quá thời hạn.
- **CANCELLED**: yêu cầu được hủy qua cơ chế có thẩm quyền.

Đây là các trạng thái minh họa; mỗi trạng thái cần lý do và bước tiếp theo phù hợp. Không dùng UNKNOWN như một dạng chấp thuận tạm.

Cần có phương án tiếp cận cho người dùng không thể thực hiện một phương pháp cụ thể, chẳng hạn quy trình hoặc kênh được hỗ trợ khác. Phương án thay thế vẫn phải đạt yêu cầu của chính sách; nhân viên không tự giảm yêu cầu chỉ vì giao diện chuẩn khó sử dụng.

Nếu cần khiếu nại hoặc xét duyệt lại, hồ sơ mới phải giữ liên hệ với quyết định trước và chỉ ra dữ kiện mới hoặc sai sót cần xem xét. Không để người yêu cầu đổi nhân viên liên tục rồi được đánh giá như một hồ sơ hoàn toàn mới.

Xác minh qua hỗ trợ đạt mục đích khi người dùng có đường trở lại tài khoản theo bằng chứng phù hợp, nhân viên chỉ có quyền cần thiết và backend cấp đúng hành động đã được cho phép. Sự thuyết phục trong cuộc hội thoại không thay thế liên kết với tài khoản, còn một quyết định phê duyệt không được mở rộng thành quyền thay đổi không giới hạn.
