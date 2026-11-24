# Recovery policy documentation — Tài liệu chính sách khôi phục tài khoản

## 1. Tài liệu chính sách phải giúp đưa ra quyết định

Một hệ thống khôi phục tài khoản có thể được triển khai bằng nhiều endpoint, hàng đợi, provider thông báo và công cụ hỗ trợ. Nhưng quyết định bảo mật cốt lõi vẫn là: **khi nào một người được phép thay đổi phương thức xác thực hoặc lấy lại quyền truy cập vào một tài khoản?**

Nếu câu trả lời chỉ nằm trong trí nhớ của lập trình viên hoặc trong một số nhánh code, các nhóm rất dễ áp dụng những quy tắc khác nhau:

- Backend yêu cầu recovery code nhưng nhân viên hỗ trợ chỉ hỏi vài thông tin cá nhân.
- Giao diện nói đổi mật khẩu sẽ đăng xuất mọi thiết bị, trong khi access token cũ vẫn có hiệu lực.
- Tài liệu giới thiệu có thời gian chờ, nhưng API nội bộ có thể bỏ qua thời gian đó.
- Luồng mất passkey được chuyển sang email mà không đánh giá mức bảo đảm bị thay đổi.
- Cấu hình mới đã triển khai nhưng người xử lý khiếu nại vẫn đọc chính sách cũ.

**Recovery policy documentation** là tài liệu xác định phạm vi, điều kiện, giới hạn và trách nhiệm của việc khôi phục tài khoản. Nó phải đủ rõ để người thiết kế, người triển khai, người hỗ trợ và người đánh giá cùng đưa ra một quyết định nhất quán trước cùng tình huống.

Trong module khôi phục tài khoản an toàn, tài liệu cần bao quát mất mật khẩu, MFA, passkey và thiết bị; đồng thời thể hiện đánh giá rủi ro, xác minh danh tính, token dùng một lần, chống lạm dụng và kiểm soát session.

Một chính sách tốt không hứa rằng mọi yêu cầu đều được khôi phục thành công. Nó giải thích được cả trường hợp được phép, cần bổ sung bằng chứng, phải chờ và không thể cấp quyền an toàn.

## 2. Phân biệt chính sách với các tài liệu liên quan

Không nên dồn mọi chi tiết vào một trang quá dài rồi coi đó là nguồn duy nhất cho tất cả đối tượng.

| Loại tài liệu | Câu hỏi chính | Ví dụ nội dung |
|---|---|---|
| Policy | Được phép làm gì, với điều kiện nào? | Bằng chứng tối thiểu trước khi thay MFA |
| Standard hoặc control profile | Phải đáp ứng những thông số và kiểm soát nào? | Hạn token, ngân sách thử, yêu cầu lưu secret |
| Procedure | Ai thực hiện những bước nào? | Các bước xử lý một hồ sơ khôi phục thủ công |
| Runbook | Khi có tình huống vận hành cụ thể thì xử lý ra sao? | Provider gửi mã gián đoạn hoặc nghi token bị lộ |
| Protocol/API contract | Các thành phần trao đổi dữ liệu và trạng thái thế nào? | Idempotency, lỗi, callback, version của attempt |
| Hướng dẫn người dùng | Người dùng cần chuẩn bị và thực hiện gì? | Cất recovery code, báo yêu cầu không do mình tạo |
| Threat model | Những đường tấn công nào đang được kiểm soát? | Đánh cắp email rồi reset MFA |
| Hồ sơ quyết định | Vì sao chọn hoặc thay đổi một quy tắc? | Căn cứ cho việc thêm thời gian chờ |

Policy có thể tham chiếu tài liệu khác, nhưng không nên dùng câu “xem implementation” để né những quyết định quan trọng. Nếu quyền được cấp phụ thuộc vào thời gian chờ hoặc loại bằng chứng, người đọc phải tìm được quy tắc có phiên bản và có người chịu trách nhiệm.

Ngược lại, policy không cần sao chép tên mọi cột database hoặc từng dòng retry của SDK. Những chi tiết đó có thể đổi mà không làm thay đổi điều kiện cấp quyền.

### 2.1. Quy tắc chuẩn tắc và nội dung giải thích

Tài liệu nên phân biệt rõ:

- **BẮT BUỘC:** điều kiện phải được thực thi trong phạm vi đã nêu.
- **KHÔNG ĐƯỢC:** hành động bị cấm.
- **NÊN:** lựa chọn mặc định có lý do; nếu khác cần căn cứ và thẩm quyền.
- **CÓ THỂ:** phương án được phép khi các điều kiện liên quan thỏa mãn.

Đây có thể là quy ước soạn thảo của tổ chức. Nếu dùng các từ khóa theo một chuẩn cụ thể, nêu chuẩn và cách áp dụng thay vì trộn nhiều nghĩa.

Ví dụ không đủ rõ:

> Hệ thống nên kiểm tra kỹ trước khi reset MFA.

Ví dụ có thể thực hiện và đánh giá:

> Trước khi cấp quyền thay MFA, hệ thống BẮT BUỘC xác nhận bộ bằng chứng được phép cho loại tài khoản và tình huống mất yếu tố. Một session đang tồn tại, nếu không đạt điều kiện xác thực lại của policy, không được tự dùng làm bằng chứng duy nhất.

Quy tắc thứ hai vẫn cần liên kết tới bảng bằng chứng và yêu cầu xác thực lại, nhưng đã xác định rõ hành động, điều kiện và điều bị cấm.

### 2.2. Ví dụ không tự trở thành chính sách đang có hiệu lực

Bài học này dùng các mã quy tắc, bảng và schema minh họa. Chúng là mẫu thiết kế tài liệu, không phải chính sách đã được phê duyệt hoặc cấu hình đang chạy của một hệ thống cụ thể.

Một bản nháp còn thiếu giá trị quyết định, người phê duyệt hoặc căn cứ kiểm soát phải được đánh dấu là bản nháp. Không đưa các chỗ trống vào production rồi mặc định dùng giá trị dễ nhất.

## 3. Nhận diện tài liệu, chủ sở hữu và hiệu lực

Một policy cần có danh tính ổn định để trả lời “quy tắc nào đã được áp dụng cho lần khôi phục này?”.

Các trường quản trị thường gồm:

| Trường | Mục đích |
|---|---|
| Policy ID | Định danh ổn định của chính sách |
| Revision | Phiên bản nội dung bất biến đã phát hành |
| Status | Draft, approved, active, superseded hoặc retired |
| Owner | Vai trò chịu trách nhiệm nội dung |
| Approver | Vai trò có thẩm quyền phê duyệt |
| Approved at | Mốc phê duyệt |
| Effective from | Mốc dự kiến có hiệu lực |
| Applies to | Sản phẩm, tenant, nhóm tài khoản và luồng áp dụng |
| Control profile | Bộ thông số/kiểm soát liên quan có phiên bản |
| Review trigger | Sự kiện hoặc chu kỳ cần xem xét lại |
| Replaces | Phiên bản cũ được thay thế |
| Related decisions | Hồ sơ phân tích rủi ro và thay đổi liên quan |

Phân biệt **được phê duyệt**, **đến ngày có hiệu lực** và **đã triển khai đầy đủ**. Một tài liệu có ngày hiệu lực không chứng minh mọi node, app mobile hoặc công cụ hỗ trợ đã dùng đúng revision.

Nên có hồ sơ triển khai liên kết revision của policy với phiên bản ứng dụng, cấu hình và phạm vi rollout. Nếu rollout theo nhóm, cần biết nhóm nào thực sự chịu quy tắc nào.

Không lưu secret, API key hoặc dữ liệu người dùng trong các trường quản trị này. Danh tính người phê duyệt và lịch sử sửa cũng cần được quản lý theo quyền truy cập phù hợp.

## 4. Ghi rõ phạm vi và các tình huống khôi phục

### 4.1. Phân biệt tác vụ theo khả năng xác thực còn lại

“Mất mật khẩu” chưa đủ mô tả trạng thái an toàn của tài khoản. Người dùng có thể còn một passkey hợp lệ hoặc đã mất tất cả phương thức xác thực.

Một ma trận phạm vi ban đầu:

| Tình huống | Câu hỏi cần làm rõ | Loại quyết định cần ghi |
|---|---|---|
| Quên mật khẩu, còn authenticator đủ điều kiện | Có thể xác thực lại với mức yêu cầu không? | Thay/binding credential trong phiên đủ điều kiện |
| Mất MFA, còn mật khẩu | Mật khẩu còn lại có đủ cho hành động thay MFA không? | Bộ bằng chứng bổ sung và quyền giới hạn |
| Mất một thiết bị chứa passkey | Còn passkey trên thiết bị khác hoặc authenticator khác không? | Phân biệt mất thiết bị với mất mọi cách xác thực |
| Mất toàn bộ yếu tố | Có phương án recovery đã thiết lập từ trước không? | Recovery code, contact hoặc quy trình phù hợp khác |
| Mất kênh email/điện thoại | Còn kênh độc lập hoặc phương thức hợp lệ nào? | Không xác minh bằng chính kênh đang nghi bị mất |
| Nghi bị chiếm tài khoản | Yếu tố và session nào có thể do kẻ tấn công kiểm soát? | Containment, xác minh và loại bỏ thay đổi trái phép |
| Tài khoản tổ chức hoặc đặc quyền | Ai có quyền quyết định và tài khoản thuộc ai? | Chính sách tenant, phân quyền và kiểm soát bổ sung |

[NIST SP 800-63B-4, phần Account Recovery](https://pages.nist.gov/800-63-4/sp800-63b.html#account-recovery) phân biệt recovery khi mất các authenticator cần thiết với việc thay mật khẩu trong trường hợp vẫn xác thực được bằng authenticator khác. Tài liệu nội bộ nên giữ sự phân biệt này để không áp dụng nhầm đường recovery yếu hơn.

### 4.2. Không suy mức bảo đảm chỉ từ tên phương thức

Hai mã gửi qua email không tự trở thành hai yếu tố độc lập. Email và số điện thoại cùng được khôi phục qua một tài khoản bị chiếm có thể có điểm lỗi chung.

Tương tự, gắn nhãn “có MFA” hoặc “có passkey” chưa đủ mô tả toàn bộ bảo đảm của tài khoản. Cần hiểu cách authenticator được đăng ký, điều kiện sử dụng và tác động khi thay thế.

Nếu tổ chức tuyên bố đáp ứng một mức AAL hoặc IAL, policy phải chỉ ra phiên bản chuẩn, phạm vi và yêu cầu áp dụng. Không tự gán AAL2 chỉ vì thấy hai bước xác minh trong giao diện.

### 4.3. Xác định những đối tượng ngoài phạm vi

Chính sách cũng cần nêu rõ giới hạn, chẳng hạn:

- Khôi phục tài khoản của ứng dụng không đồng nghĩa khôi phục tài khoản email của người dùng.
- Thu hồi quyền xác thực tại relying party không có nghĩa xóa được khóa trên mọi thiết bị hoặc kho đồng bộ passkey.
- Tài khoản do identity provider quản lý có thể cần xử lý tại IdP, nhưng hệ thống vẫn phải quản lý session và quyền cục bộ của mình.
- Khôi phục quyền truy cập không tự đồng nghĩa mở lại những hành động đang bị hạn chế vì lý do khác.

Các giới hạn giúp nhóm hỗ trợ đưa ra lời giải thích đúng và giúp thiết kế test không dựa trên một bảo đảm không tồn tại.

## 5. Ghi tài liệu cho mô hình bằng chứng và rủi ro

### 5.1. Mỗi loại bằng chứng cần điều kiện sử dụng

Đừng chỉ liệt kê “email, SMS, recovery code, hỗ trợ thủ công”. Với mỗi loại, cần mô tả:

1. Nó chứng minh điều gì và không chứng minh điều gì.
2. Nó được thiết lập hoặc liên kết với tài khoản như thế nào.
3. Khi nào nó có thể đã bị lộ hoặc mất độ tin cậy.
4. Nó có cần kết hợp với phương thức khác không.
5. Nó cho phép hành động nào.
6. Khi nào phải vô hiệu hoặc không chấp nhận.
7. Bằng chứng và kết quả được ghi audit ở mức nào.

Ví dụ, việc kiểm soát một địa chỉ mới chỉ chứng minh khả năng nhận thông tin ở địa chỉ đó trong điều kiện kiểm tra. Nó không tự chứng minh người đang thao tác là chủ của tài khoản cũ.

Đối với recovery khi nghi bị chiếm quyền, không dựa riêng vào yếu tố liên hệ vừa được thêm hoặc sửa. Phải có căn cứ đáng tin trước đó theo policy và mức bảo đảm cần thiết.

### 5.2. Bảng phương án phải ghi cả trường hợp không được dùng

Một mẫu bảng nội bộ:

| Phương án | Điều kiện được xem xét | Giới hạn phải ghi | Kết quả được phép |
|---|---|---|---|
| Authenticator còn hoạt động | Đạt yêu cầu xác thực lại cho hành động | Không dùng session cũ thay thế mọi kiểm tra | Cấp quyền thay authenticator theo scope |
| Saved recovery code | Đã cấp trước, còn hiệu lực, được kiểm tra an toàn | Quy tắc kết hợp phụ thuộc loại tài khoản | Tiếp tục luồng recovery đã phê duyệt |
| Issued recovery code | Kênh đã thiết lập và được chấp nhận cho tình huống | Nguy cơ email bị chiếm, SIM swap, mã đến chậm | Hoàn tất bước chứng minh theo quy tắc |
| Recovery contact | Đã đăng ký trước và có quy trình phù hợp | Không phải người quen bất kỳ gọi xác nhận | Thực hiện đúng quy trình contact |
| Xác minh lại danh tính | Có căn cứ liên kết tới tài khoản và quy trình được duyệt | Không phải mọi tài khoản đều có hồ sơ proofing ban đầu | Quyết định theo profile liên quan |
| Hỗ trợ thủ công | Có vai trò, công cụ và loại bằng chứng được phép | Không tạo lối bỏ qua kiểm soát | Quyết định giới hạn, có audit |

Bảng này chưa tự định nghĩa đầy đủ tổ hợp nào đủ cho một mức bảo đảm cụ thể. Policy thực tế cần chỉ rõ những tổ hợp được phép cho từng phạm vi, thay vì để nhân viên tự ghép.

NIST SP 800-63B-4 mô tả các lớp phương thức recovery và yêu cầu khác nhau theo bối cảnh IAL/AAL; phương án riêng của ứng dụng cần dựa trên phân tích rủi ro và được ghi tài liệu. Khi tuyên bố tuân thủ, phải đối chiếu đầy đủ [phần 4.2](https://pages.nist.gov/800-63-4/sp800-63b.html#account-recovery), không chỉ chọn một phương án thuận tiện trong bảng.

### 5.3. Tín hiệu rủi ro không phải bằng chứng sở hữu tuyệt đối

IP, thiết bị quen thuộc, vị trí, lịch sử giao dịch và thời điểm thay kênh liên hệ có thể hỗ trợ đánh giá rủi ro. Chúng cũng có thể bị giả mạo, dùng chung hoặc thay đổi hợp lệ.

Policy nên quy định tín hiệu nào có thể:

- Tăng yêu cầu xác minh.
- Áp dụng thời gian chờ.
- Chuyển kiểm tra thủ công.
- Từ chối một phương án.
- Hỗ trợ ưu tiên điều tra.

Không biến một IP quen thuộc hoặc câu trả lời từ thông tin công khai thành quyền reset MFA độc lập.

Không ghi quy tắc mơ hồ như “nếu trông có vẻ đáng tin thì bỏ qua”. Trường hợp ngoại lệ cần tiêu chí, thẩm quyền, giới hạn và hồ sơ quyết định.

## 6. Viết các quy tắc cấp quyền có thể kiểm tra

Mỗi quy tắc quan trọng nên có ID ổn định. Một mẫu cấu trúc:

~~~text
Rule ID:
Scope:
Trigger:
Required evidence:
Decision:
Permitted actions:
Prohibited actions:
Validity and invalidation:
Failure handling:
Audit evidence:
Owner:
Related controls and scenarios:
~~~

Ví dụ sau mô tả một quy tắc minh họa:

~~~text
Rule ID: RCV-AUTHZ-01
Scope: Các luồng cấp recovery grant của sản phẩm.
Trigger: Bộ bằng chứng đã đạt yêu cầu tại bước xét duyệt.
Required evidence:
  Kết quả verifier và policy decision có nguồn được tin cậy,
  liên kết đúng attempt và tài khoản mục tiêu.
Decision:
  Chỉ cấp grant cho hành động đã được chấp thuận.
Permitted actions:
  Thực hiện đúng thao tác thay credential/authenticator được định danh.
Prohibited actions:
  Dùng grant làm session truy cập đầy đủ.
  Dùng grant để đổi một kênh hoặc yếu tố khác ngoài scope.
Validity and invalidation:
  Theo control profile đang áp dụng và quy tắc thu hồi hiện hành.
Failure handling:
  Không cấp quyền khi thiếu, hết hạn hoặc không khớp bằng chứng.
Audit evidence:
  Rule revision, decision, scope và reference không chứa secret.
~~~

Đây là ví dụ về hình thức quy tắc. Để phát hành, các tham chiếu như control profile phải được giải quyết thành tài liệu và thông số cụ thể đã phê duyệt.

### 6.1. Quy tắc nên mô tả cả nhánh từ chối

Quy tắc “cho phép reset nếu token hợp lệ” thường còn thiếu:

- Token thuộc tenant nào?
- Token dùng cho mục đích nào?
- Token có liên kết với attempt và subject đúng không?
- Token đã được dùng hoặc thay thế chưa?
- Account có bị thay đổi security version kể từ lúc phát không?
- Policy hoặc incident hold hiện tại có cấm thực hiện không?
- Hai request đồng thời được phân xử như thế nào?
- Nếu commit thành công nhưng trả response thất bại thì retry ra sao?

Mỗi câu hỏi có thể được trả lời ở policy, profile hoặc protocol tương ứng, nhưng cần có đường dẫn truy vết rõ.

### 6.2. Không để yêu cầu bảo mật chỉ nằm trong client

Thời gian chờ, số lần thử, giới hạn scope và quyền hoàn tất phải được thực thi ở thành phần có thẩm quyền phía server.

Tài liệu có thể hướng dẫn client hiển thị đồng hồ hoặc nút bị vô hiệu, nhưng không coi đó là điểm kiểm soát bảo mật. Một client cũ hoặc API caller trực tiếp vẫn phải chịu cùng điều kiện.

## 7. Ghi tài liệu cho token, mã và giới hạn lạm dụng

Policy cần quy định nguyên tắc; control profile chứa các giá trị cụ thể theo loại phương thức và phạm vi áp dụng.

### 7.1. Vòng đời secret và recovery grant

Các mục cần ghi:

- Cách sinh secret phù hợp với loại phương thức và yêu cầu an toàn.
- Cách bảo vệ dữ liệu verifier và khóa liên quan.
- Liên kết tenant, tài khoản, attempt, purpose và generation.
- Thời điểm bắt đầu hiệu lực, hết hiệu lực và quy tắc đồng hồ.
- Điều kiện tiêu thụ một lần và thực thi nguyên tử.
- Khi nào mã cũ vô hiệu nếu phát lại hoặc thay thế.
- Hành vi khi dùng sai, dùng trùng, hết hạn hoặc bị thu hồi.
- Phạm vi hủy các mã/grant chưa dùng sau recovery hoặc sự cố.
- Quyền truy cập dữ liệu và những nơi không được ghi secret.

Không áp một thời hạn duy nhất cho mọi saved recovery code, mã gửi qua kênh liên hệ và recovery grant. Các loại này có mục đích và điều kiện khác nhau; hạn phải được quyết định theo profile và yêu cầu áp dụng.

[OWASP Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html) nêu các nguyên tắc mã/token ngẫu nhiên an toàn, bảo vệ lưu trữ, dùng một lần và hết hạn phù hợp cho luồng reset. Khi chuyển chúng thành chính sách, cần chỉ rõ từng kiểm soát được thực thi ở đâu.

### 7.2. Phân biệt các loại giới hạn

| Giới hạn | Câu hỏi policy cần trả lời |
|---|---|
| Verify budget | Một challenge hoặc attempt được thử bằng chứng bao nhiêu lần? |
| Resend budget | Bao nhiêu lần gửi lại và trong khoảng nào? |
| Attempt creation budget | Bao nhiêu attempt có thể tạo cho cùng phạm vi? |
| Cooldown | Sau một hành động, phải chờ bao lâu trước khi thử lại? |
| Recovery hold | Trước thao tác nhạy cảm cần chờ hoặc duyệt gì? |
| Manual review target | Thời gian xử lý mong muốn của nhóm hỗ trợ là bao lâu? |

Các khái niệm này không thay thế nhau. Hết verify budget không nhất thiết yêu cầu khóa toàn bộ khả năng đăng nhập của tài khoản. Manual review target cũng không phải lời hứa tự động cấp quyền khi đã chờ đủ lâu.

### 7.3. Đừng tạo điều kiện gây từ chối dịch vụ cho chủ tài khoản

Nếu một request công khai có thể khóa đăng nhập của bất kỳ tài khoản nào được nêu tên, recovery trở thành công cụ quấy rối.

Tài liệu cần nói rõ tác động của rate limit lên attempt, channel, tài khoản, tenant và nguồn request. Đồng thời ghi cách xử lý người dùng hợp lệ bị ảnh hưởng, mà vẫn không tiết lộ tài khoản có tồn tại.

Resend không được âm thầm xóa toàn bộ ngân sách thử sai. Nếu thay thế mã hoặc đổi attempt, các giới hạn tổng hợp vẫn cần được xem xét theo thiết kế chống lạm dụng.

## 8. Ghi state machine và các điểm quyết định

Một sơ đồ minh họa cho tài liệu:

~~~mermaid
flowchart TD
    A[Yêu cầu được ghi nhận] --> B[Chọn phương án được phép]
    B --> C[Thu và kiểm tra bằng chứng]
    C --> D{Đủ điều kiện?}
    D -->|Chưa đủ| E[Chờ bổ sung hoặc kết thúc]
    D -->|Bị cấm| F[Từ chối có ghi nhận]
    D -->|Đủ| G{Cần hold hoặc duyệt?}
    G -->|Có| H[Chờ và kiểm tra lại điều kiện]
    G -->|Không| I[Cấp quyền giới hạn]
    H --> I
    I --> J[Thực hiện thay đổi được phép]
    J --> K[Hoàn tất kiểm soát sau recovery]
    K --> L[Kết thúc thành công]
~~~

Sơ đồ hỗ trợ hiểu luồng nhưng chưa đủ thay thế bảng transition. Với mỗi transition, nên mô tả actor, precondition, side effect, giới hạn retry và điều kiện vô hiệu.

### 8.1. Những điểm cần có định nghĩa rõ

- “Đã nhận yêu cầu” có nghĩa đã lưu attempt hay chỉ đã nhận HTTP request?
- “Đã gửi mã” là provider accepted, delivered hay người dùng đã chứng minh nhận được?
- “Bằng chứng đạt” cho phép cấp quyền gì và trong bao lâu?
- “Đã duyệt thủ công” là một input cho policy hay có thể trực tiếp thay credential?
- “Hoàn tất” có bao gồm kiểm soát session bắt buộc không?
- “Hết hạn” áp dụng cho challenge, grant hay toàn attempt?
- “Hủy” có tác động tới những attempt/grant nào?

Không có định nghĩa rõ, các nhóm có thể cùng dùng từ “verified” nhưng hiểu những quyền hoàn toàn khác nhau.

### 8.2. Bằng chứng đã đạt có thể không còn dùng được ở bước cuối

Giữa lúc xác minh và lúc commit, tài khoản có thể đổi yếu tố, mã bị thu hồi hoặc incident hold được bật. Policy cần nói điều kiện nào phải kiểm tra lại trước khi thực hiện thao tác.

Không mặc định rằng một decision cũ có hiệu lực vô hạn. Grant nên có phạm vi và liên kết bảo mật để tránh dùng bằng chứng của trạng thái tài khoản cũ cho trạng thái mới.

Hành vi khi có xung đột cũng cần được ghi: hủy, yêu cầu xác minh lại, giữ chờ hoặc từ chối. Không tự chọn tiếp tục chỉ vì giao diện đã hiển thị “xác minh thành công”.

### 8.3. Lỗi một phần và tính idempotent

Nếu credential đã đổi nhưng bước finalization lỗi, hệ thống phải biết nó đang ở trạng thái nào, quyền nào đã có hiệu lực và bước nào được phép retry.

Policy xác định yêu cầu an toàn và điều kiện hoàn tất. Protocol/runbook mô tả cách khôi phục tính nhất quán. Không phát thông báo thành công đầy đủ trong khi một điều kiện bảo mật bắt buộc chưa được đáp ứng.

## 9. Quy định quyền và session sau recovery

Một tài liệu chỉ nói “reset thành công” thường bỏ sót câu hỏi quan trọng nhất: sau đó ai còn truy cập được tài khoản và được làm gì?

### 9.1. Recovery grant khác session sử dụng ứng dụng

Policy cần phân biệt ít nhất:

- Trạng thái đang tham gia recovery.
- Quyền giới hạn để thực hiện một thao tác recovery.
- Session đã xác thực theo cơ chế thông thường.
- Quyền thực hiện hành động nhạy cảm sau recovery.

Một grant cho phép đặt mật khẩu mới không nên mặc nhiên cho phép đọc dữ liệu, đổi email, thêm passkey và thực hiện giao dịch. Nếu các hành động ấy được phép, phải có quy tắc rõ cho từng scope.

Đối với password reset, hướng dẫn OWASP khuyến nghị người dùng đăng nhập theo cơ chế thông thường sau khi đặt mật khẩu, thay vì tự động tạo một phiên đăng nhập đầy đủ. Chính sách cần xác định hành vi này nhất quán giữa web, mobile và API. Tham khảo [Forgot Password: User Resets Password](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html#user-resets-password).

### 9.2. Tài liệu hóa phạm vi vô hiệu hóa

Một bảng cần có cho từng loại recovery:

| Đối tượng | Quyết định cần ghi |
|---|---|
| Session hiện có | Giữ, xác thực lại, giới hạn hay thu hồi trong tình huống nào? |
| Refresh token | Thu hồi những token/family nào và khi nào? |
| Access token | Cơ chế nào làm mất quyền và độ trễ tối đa là bao nhiêu? |
| Trusted device hoặc remember-me | Có còn được dùng sau thay đổi không? |
| Authenticator nghi bị lộ | Bị đình chỉ hoặc vô hiệu như thế nào? |
| Recovery token/grant chưa dùng | Những đối tượng nào bị hủy để tránh khôi phục ngược? |
| Recovery code dự phòng | Khi nào tiêu thụ, tái cấp hoặc thay thế theo phương án? |
| API key và quyền ứng dụng khác | Có thuộc phạm vi sự cố hay cần quy trình riêng? |

Không viết “đăng xuất mọi thiết bị ngay lập tức” nếu kiến trúc chỉ thu hồi refresh token còn access token tự chứa vẫn được chấp nhận đến hết hạn. Hoặc thay đổi cơ chế để đáp ứng yêu cầu, hoặc mô tả đúng giới hạn và rủi ro được chấp nhận.

Đối với tài khoản nghi bị chiếm, policy phải xem xét cả session và thay đổi yếu tố khôi phục do kẻ tấn công thực hiện. Chỉ đổi mật khẩu có thể chưa khôi phục quyền kiểm soát. Xem [OWASP: Account Recovery After Suspected Compromise](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html#account-recovery-after-suspected-compromise).

### 9.3. Hạn chế sau recovery cần có điều kiện mở

Một số sản phẩm có thể hạn chế đổi kênh liên hệ hoặc thực hiện hành động nhạy cảm trong một khoảng sau recovery. Nếu áp dụng, tài liệu cần nêu:

1. Những hành động bị hạn chế.
2. Thời điểm bắt đầu và kết thúc.
3. Điều kiện xác minh hoặc kiểm tra bổ sung.
4. Ai có quyền giải quyết khiếu nại.
5. Điều gì xảy ra nếu người dùng bắt đầu recovery khác.
6. Cách thông báo và hỗ trợ khả năng tiếp cận.

Thời gian chờ không tạo ra bằng chứng danh tính. Đợi đủ lâu không tự bù được một quy trình xác minh thiếu căn cứ.

## 10. Quy định thay đổi kênh và authenticator

Thay email, số điện thoại hoặc thêm authenticator là một đường chiếm tài khoản phổ biến nếu được phép ngay trong lúc recovery còn yếu.

### 10.1. Phân biệt xác minh kênh mới với ủy quyền thay kênh cũ

Một người có thể tạo email mới và nhận mã ở đó. Điều này không chứng minh họ có quyền thay email khôi phục của tài khoản mục tiêu.

Policy cần ghi:

- Điều kiện ủy quyền thay kênh.
- Cách chứng minh quyền kiểm soát kênh mới.
- Có cần thông báo qua kênh đã thiết lập trước không.
- Thời điểm kênh mới được phép dùng cho recovery.
- Điều kiện hủy hoặc xử lý thay đổi không được cho phép.
- Các token/grant nào bị vô hiệu khi liên kết kênh thay đổi.

Không tự động khôi phục kênh liên hệ cũ chỉ vì nó từng tồn tại; kênh ấy có thể đã bị bỏ hoặc bị chiếm. Quy trình phải đánh giá trạng thái an toàn hiện tại và lịch sử liên kết có liên quan.

### 10.2. Mất thiết bị chứa passkey không có một đáp án duy nhất

Tài liệu cần phân biệt passkey gắn với thiết bị và passkey được đồng bộ theo cơ chế của provider, cùng các authenticator khác vẫn còn sử dụng được.

Không hướng dẫn hỗ trợ “xóa mọi passkey rồi cho đăng nhập bằng email” như một thủ tục mặc định. Cần xác minh đúng phạm vi, quyết định authenticator nào không còn được tin cậy và điều kiện binding authenticator mới.

Hệ thống có thể vô hiệu credential được lưu ở phía relying party mà không xóa được bản sao khóa trên thiết bị của người dùng. Tài liệu phải nói rõ hành động của hệ thống và giới hạn của hành động đó.

### 10.3. Không dựa riêng vào session đang mở để thay MFA

Một session có thể đã bị đánh cắp hoặc được tạo với mức xác thực không đủ. Chính sách thay yếu tố cần quy định yêu cầu xác thực lại, đánh giá rủi ro và thông báo phù hợp.

[OWASP Multifactor Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html#resetting-mfa) nhấn mạnh phương án reset MFA phải được chọn theo bối cảnh và không trở thành đường bỏ qua MFA. Vì vậy, tài liệu không nên chuyển một khó khăn hỗ trợ thành quyền reset không có kiểm soát.

## 11. Thông báo, giải thích và quyền của người dùng

### 11.1. Xác định sự kiện nào cần thông báo

Một ma trận thông báo có thể gồm:

| Sự kiện | Mục đích thông báo |
|---|---|
| Khởi tạo recovery theo điều kiện policy | Giúp phát hiện yêu cầu không mong muốn |
| Cấp hoặc thay recovery code | Nhận biết thay đổi khả năng khôi phục |
| Bước chờ hoặc duyệt được kích hoạt | Giải thích trạng thái và bước tiếp theo |
| Thay credential/authenticator | Phát hiện thay đổi trái phép |
| Thay kênh liên hệ | Giúp nhận biết nguy cơ chuyển quyền kiểm soát |
| Recovery hoàn tất | Xác nhận kết quả và hướng dẫn bảo vệ tài khoản |
| Yêu cầu bị đình chỉ do sự cố | Giải thích cách nhận hỗ trợ an toàn |

Không mặc định gửi mọi chi tiết tới tất cả địa chỉ từng xuất hiện trong hồ sơ. Cần quy tắc chọn địa chỉ đã thiết lập, trạng thái an toàn của kênh và yêu cầu áp dụng theo loại tài khoản.

Nếu áp dụng NIST SP 800-63B-4, phải đối chiếu đầy đủ các điều kiện thông báo tương ứng trong [Account Notifications](https://pages.nist.gov/800-63-4/sp800-63b.html#account-notifications). Bảng minh họa ở đây không thay thế các yêu cầu ấy.

### 11.2. Public response và nội dung nội bộ có thể khác độ chi tiết

Endpoint công khai cần hạn chế rò rỉ sự tồn tại của tài khoản, cấu hình MFA hoặc số điện thoại liên kết. Tài liệu nên phân biệt:

- Thông điệp trả cho người chưa được xác minh.
- Trạng thái được phép hiển thị sau khi đủ điều kiện.
- Reason code dành cho hệ thống hoặc nhân viên có quyền.
- Nội dung audit phục vụ điều tra.

Thông điệp chung không được biến thành báo cáo nội bộ sai sự thật. Hệ thống vẫn cần lưu quyết định đúng để vận hành và giải quyết khiếu nại.

Các lỗi, độ trễ và luồng chuyển trang cũng cần được xem xét, không chỉ một câu chữ. Một endpoint trả cùng text nhưng khác hành vi theo tài khoản vẫn có thể rò rỉ thông tin.

### 11.3. Có một lối báo cáo yêu cầu không do người dùng tạo

Tài liệu người dùng cần chỉ ra cách báo recovery trái phép, cách liên hệ hỗ trợ và những thông tin nào không nên chia sẻ.

Một đường “đây không phải tôi” không được tự trở thành bearer credential có thể thay đổi mọi quyền của tài khoản. Tác động của nút này cần được thiết kế rõ: ghi nhận báo cáo, mở quy trình xử lý hoặc thực hiện một hành động bảo vệ có phạm vi đã đánh giá.

Thông báo không nên chứa mật khẩu hoặc recovery secret không cần thiết. Hướng dẫn hỗ trợ phải nhất quán về việc không yêu cầu người dùng đọc OTP, recovery code hay mật khẩu cho nhân viên qua kênh chat/gọi thông thường; việc nộp bằng chứng phải qua cơ chế được phê duyệt.

## 12. Chính sách cho hỗ trợ thủ công và ngoại lệ

### 12.1. Hỗ trợ thủ công là một luồng có kiểm soát

Một quy trình thủ công cần có:

- Vai trò được tiếp nhận hồ sơ và vai trò được xét duyệt.
- Điều kiện nhận diện đúng tài khoản và tenant.
- Các loại bằng chứng được phép thu hoặc kiểm tra.
- Những dữ liệu tuyệt đối không dùng làm bằng chứng duy nhất.
- Công cụ, quyền hạn và giới hạn thao tác.
- Điều kiện cần thêm người phê duyệt hoặc chuyển chuyên trách.
- Thời hạn của quyết định và phạm vi grant được cấp.
- Cách ghi audit, thông báo và xử lý khiếu nại.

Quyền mở ticket không bằng quyền duyệt. Quyền duyệt cũng không nhất thiết bằng quyền thực hiện mọi thay đổi.

Việc hai nhân viên cùng đồng ý giúp phân tách trách nhiệm nhưng không tự biến bằng chứng yếu thành mạnh. Chính sách vẫn phải quy định căn cứ quyết định.

### 12.2. Ngăn thao túng qua hội thoại

Kẻ tấn công có thể biết tên, lịch sử mua hàng hoặc thông tin công khai của nạn nhân, rồi gây áp lực vì “đang cần gấp”.

Tài liệu cần đưa ra phản hồi và tuyến xử lý cho:

- Yêu cầu bỏ qua thời gian chờ.
- Đề nghị đổi sang địa chỉ liên hệ do người gọi vừa cung cấp.
- Yêu cầu gửi mã cho người tự xưng là quản trị viên.
- Hồ sơ có thông tin mâu thuẫn.
- Trường hợp người yêu cầu có quan hệ công việc với nhân viên hỗ trợ.
- Các lần liên hệ nhiều nhân viên để tìm người dễ chấp thuận.

Người hỗ trợ cần có cách chuyển hồ sơ và giải thích quyết định mà không phải tự sáng tác bằng chứng hoặc làm lộ kiểm soát nhạy cảm.

### 12.3. Ngoại lệ cần hồ sơ và giới hạn rõ

Một hồ sơ ngoại lệ thường ghi:

~~~text
Exception reference:
Requested action:
Reason normal path cannot be used:
Affected scope:
Evidence evaluated:
Risk and compensating controls:
Approver and authority:
Allowed actions:
Validity and expiration:
Revocation conditions:
Audit and notification requirements:
Follow-up owner:
~~~

Ngoại lệ không có nghĩa xóa lịch sử quyết định hoặc cấp một tài khoản quản trị chung cho người yêu cầu. Nếu không đạt mức an toàn tối thiểu, kết quả có thể là từ chối hoặc chỉ cung cấp hỗ trợ không làm thay đổi quyền.

Cơ chế truy cập khẩn cấp của nhân viên vận hành phải được định nghĩa riêng. Không lấy “break-glass” của quản trị hệ thống làm phương án mặc định để khôi phục tài khoản người dùng.

### 12.4. Không có bằng chứng đủ thì không cấp quyền

Nếu người dùng mất mọi phương thức đã thiết lập và tài khoản không có quy trình xác minh phù hợp, hỗ trợ không nên hứa “chắc chắn lấy lại được”.

Policy nên giải thích các lựa chọn được phép: bổ sung bằng chứng theo quy trình, chuyển cấp có thẩm quyền, chờ điều kiện khác hoặc không khôi phục được. Các hỗ trợ về dữ liệu, thanh toán hay tạo tài khoản mới, nếu có, cần chính sách riêng và không mặc nhiên chuyển quyền sở hữu tài khoản cũ.

## 13. Xử lý khi dependency không hoạt động

Một policy phải hoạt động cả khi thành phần xác minh, provider hoặc kho trạng thái gặp lỗi.

| Tình huống | Yêu cầu cần làm rõ |
|---|---|
| Provider gửi thông báo lỗi | Chờ, retry hoặc chuyển phương án đã được duyệt; không coi accepted là delivered |
| Verifier không truy cập được | Không cấp quyền dựa trên việc chưa kiểm tra được |
| Policy engine thiếu cấu hình | Không âm thầm chọn điều kiện dễ hơn |
| Kho grant mất kết nối | Không cấp quyền không thể kiểm tra single-use hoặc trạng thái thu hồi |
| Dữ liệu session thu hồi chậm | Áp dụng trạng thái an toàn và không tuyên bố hoàn tất sai |
| Audit/record bắt buộc không ghi được | Hành vi dừng, chờ hoặc hạn chế phải được quyết định trước theo mức rủi ro |
| Có nghi ngờ key hoặc secret bị lộ | Dùng quy trình containment và vô hiệu hóa phạm vi liên quan |
| Kênh thông báo nghi bị chiếm | Chọn kênh và quy trình khác được policy cho phép |

Cần phân biệt “không có bằng chứng rằng bị từ chối” với “đã có quyết định cho phép”. Timeout không phải approve.

Nếu hỗ trợ offline hoặc queued operation, policy phải nêu điều kiện nào được đánh giá lúc tiếp nhận và điều kiện nào phải kiểm tra lại lúc thực thi. Một quyết định hợp lệ hôm qua có thể đã bị thu hồi trước khi job hôm nay chạy.

Runbook nên chứa thao tác vận hành cụ thể, nhưng policy phải quyết định rõ có được cấp quyền trong trạng thái suy giảm hay không.

## 14. Multi-tenant và tài khoản có đặc quyền

### 14.1. Có nền kiểm soát chung và phạm vi bổ sung

Trong hệ thống nhiều tenant, tài liệu cần xác định:

- Kiểm soát tối thiểu áp dụng chung.
- Những tham số tenant được phép cấu hình.
- Những thay đổi tenant phải được phê duyệt riêng.
- Quy tắc xử lý cấu hình mâu thuẫn hoặc thiếu.
- Ai có quyền thay đổi policy và ngày hiệu lực.
- Khả năng truy vết revision theo từng tenant.

Không để một tenant tùy ý hạ kiểm soát của tài khoản dùng chung trên toàn nền tảng. Cần xác định tài khoản là danh tính toàn cục, danh tính cục bộ tenant hay thành viên được liên kết.

Một quản trị viên tenant có thể có quyền quản lý membership mà không có quyền khôi phục danh tính toàn cục của người dùng. Sự khác biệt này cần được ghi rõ cả trong tài liệu hỗ trợ và phân quyền API.

### 14.2. Liên kết phạm vi phải được kiểm tra ở mọi bước

Attempt, bằng chứng, grant và thao tác cuối đều cần gắn với đúng tenant và subject theo mô hình danh tính. Không dựa riêng vào header do client tự khai để quyết định toàn bộ phạm vi.

Policy nên yêu cầu từ chối sử dụng bằng chứng hoặc grant sai tenant, sai tài khoản hoặc sai purpose. Protocol mô tả cách liên kết và cách xử lý callback không có đủ ngữ cảnh.

### 14.3. Tài khoản đặc quyền cần quy tắc riêng có chủ sở hữu

Quy trình cho người quản trị, người có quyền tài chính hoặc tài khoản vận hành có thể cần kiểm soát bổ sung. Tài liệu phải xác định cách nhận diện nhóm và hành vi khi quyền thay đổi trong lúc recovery.

Không chỉ kiểm tra nhóm ở lúc bắt đầu rồi bỏ qua mọi thay đổi về sau. Nếu account được nâng quyền giữa luồng, phải có quy tắc để không hoàn tất bằng một bộ điều kiện cũ thấp hơn.

Tài khoản dịch vụ hoặc tài khoản máy có thể cần quy trình luân chuyển credential khác; không mặc định áp luồng người dùng có email vào mọi loại danh tính.

## 15. Quản lý phiên bản và các attempt đang chạy

### 15.1. Bốn phiên bản có thể khác nhau

| Phiên bản | Đại diện cho |
|---|---|
| Document revision | Nội dung chính sách được phê duyệt |
| Policy/config revision | Tập điều kiện và thông số đang được thực thi |
| Evidence/schema version | Cách biểu diễn bằng chứng hoặc quyết định |
| Application release | Bản mã ứng dụng triển khai kiểm soát |

Một build mới không tự có nghĩa policy đổi. Ngược lại, một feature flag hoặc cấu hình có thể làm đổi hành vi bảo mật mà không đổi build.

Audit nên liên kết được các phiên bản có ý nghĩa ở từng điểm quyết định. Không cần nhét toàn bộ nội dung policy vào từng log, nhưng phải có reference để tra lại bản bất biến tương ứng.

### 15.2. Không chỉ ghi “attempt dùng policy lúc tạo”

Pin revision giúp tái hiện quyết định, nhưng cần thêm quy tắc cho điều kiện hiện tại:

- Authenticator vừa bị báo lộ.
- Recovery address bị vô hiệu.
- Tenant bị đình chỉ.
- Incident hold hoặc kill switch được bật.
- Grant hoặc generation đã bị thu hồi.
- Phát hiện policy cũ có lỗ hổng.

Policy phải nói rõ những điều kiện nào luôn có hiệu lực ở bước cuối, kể cả attempt đã bắt đầu bằng revision cũ.

Một thiết kế có thể giữ revision gốc để giải thích luồng nhưng buộc kiểm tra current deny/revocation trước thao tác nhạy cảm. Đây là lựa chọn cần được mô tả, không phải kết quả tự nhiên của việc lưu một version string.

### 15.3. Quy tắc chuyển tiếp cho thay đổi bình thường

Khi nâng revision, phải quyết định các attempt đang chạy:

1. Được tiếp tục tới một thời hạn xác định.
2. Phải bổ sung hoặc xác minh lại.
3. Được chuyển trạng thái bằng một quy trình đã thiết kế.
4. Bị hủy và bắt đầu lại.

Không áp sự nới lỏng của policy mới cho bằng chứng cũ nếu chưa đánh giá tương thích. Cũng không kéo dài hiệu lực token cũ chỉ vì profile mới cho thời hạn khác.

Thông báo người dùng và kế hoạch hỗ trợ cần được chuẩn bị nếu thay đổi làm nhiều attempt đang chạy bị ảnh hưởng.

### 15.4. Rollback phải tách triển khai khỏi quyền bảo mật

Rollback code không được vô tình phục hồi token đã tiêu thụ, authenticator đã thu hồi hoặc bằng chứng từng bị đánh dấu không còn tin cậy.

Tài liệu thay đổi cần ghi tương thích schema, điều kiện mà bản cũ không thể thực thi an toàn và giới hạn rollback. Nếu phiên bản trước không hiểu một kiểm soát bắt buộc mới, quay lại nó có thể không phải một lựa chọn hợp lệ.

## 16. Mẫu khung policy để tổ chức nội dung

Một cấu trúc thực dụng có thể như sau:

~~~text
1. Mục đích và mục tiêu an toàn
2. Phạm vi và các đối tượng không thuộc phạm vi
3. Thuật ngữ và quy ước chuẩn tắc
4. Vai trò, thẩm quyền và trách nhiệm
5. Nhóm tài khoản, tình huống mất yếu tố và mức yêu cầu
6. Bằng chứng được phép và tổ hợp điều kiện
7. Quy tắc cấp recovery grant và giới hạn scope
8. Token, retry, resend, cooldown và thời gian chờ
9. Vòng đời attempt và xử lý lỗi một phần
10. Thay credential, authenticator và recovery channel
11. Session, quyền và hạn chế sau recovery
12. Thông báo, hỗ trợ, khiếu nại và khả năng tiếp cận
13. Ngoại lệ, dependency failure và xử lý sự cố
14. Audit, dữ liệu cá nhân và lưu giữ
15. Multi-tenant và nhóm đặc quyền
16. Versioning, rollout, transition và rollback
17. Traceability, tiêu chí nghiệm thu và review
18. Phụ lục profile, decision records và tài liệu liên quan
~~~

Không bắt buộc mọi tổ chức dùng cùng số mục. Điều quan trọng là tìm được mỗi quyết định cần thiết mà không phải suy diễn từ nhiều đoạn mâu thuẫn.

Một đoạn metadata minh họa:

~~~yaml
policyId: RCV-POLICY-EXAMPLE
revision: draft-1
status: DRAFT
ownerRole: Identity Security Owner
approvalRole: Security Policy Authority
scope:
  product: Example Application
  flows:
    - password-replacement
    - mfa-recovery
    - passkey-recovery
    - compromised-account-recovery
controlProfileRef: RCV-CONTROL-PROFILE-DRAFT
decisionRecords:
  - RCV-DECISION-EXAMPLE-01
~~~

Đoạn YAML này là ví dụ nằm trong tài liệu, không phải file cấu hình có thể triển khai. Tên vai trò và reference phải được giải quyết theo tổ chức thực tế trước khi chuyển status sang một trạng thái có hiệu lực.

### 16.1. Một quy tắc hoàn chỉnh phải nối tới thông số đang áp dụng

Nếu control profile quy định thời hạn hoặc ngân sách, cần có giá trị cụ thể, đơn vị, điểm bắt đầu đo, phạm vi reset và điều kiện thay đổi. Không để chuỗi “ngắn”, “hợp lý” hoặc “thử quá nhiều” là toàn bộ yêu cầu.

Các tham số khác loại cần tách riêng. Ví dụ validity của challenge, validity của grant, deadline của attempt và thời gian giữ quyết định duyệt không nên dùng chung một trường chỉ vì đều đo bằng thời gian.

### 16.2. Những gì nên viết ở phụ lục quyết định

Một decision record có thể ghi:

- Vấn đề hoặc đường tấn công cần giải quyết.
- Các lựa chọn đã cân nhắc.
- Phương án được chọn và lý do.
- Ảnh hưởng tới người dùng, hỗ trợ và khả năng tiếp cận.
- Các rủi ro còn lại.
- Dữ liệu hoặc sự kiện sẽ khiến quyết định cần xem xét lại.

Điều này giúp người bảo trì hiểu vì sao tồn tại một rule. Họ sẽ ít xóa nó chỉ vì nhìn thấy sự phức tạp trong code.

## 17. Truy vết từ quy tắc tới thực thi và tình huống kiểm tra

Tài liệu policy có thể đọc rất hay nhưng vẫn không được thực thi. Cần nối mỗi quy tắc quan trọng với điểm kiểm soát và cách quan sát kết quả.

Một bảng minh họa:

| Rule ID | Quyết định | Điểm thực thi cần có | Tình huống đối chiếu | Dữ liệu quan sát không chứa secret |
|---|---|---|---|---|
| RCV-SCOPE-01 | Grant chỉ dùng đúng purpose/tenant/subject | Verifier và endpoint hoàn tất | Dùng grant sai tenant hoặc đổi action | Decision và scope mismatch |
| RCV-ONCE-01 | Một grant chỉ có một lần tiêu thụ hợp lệ | Transition nguyên tử ở nguồn trạng thái | Hai request đồng thời | Một commit hợp lệ, các request còn lại bị xử lý an toàn |
| RCV-EVID-01 | Bộ bằng chứng phải đạt yêu cầu của flow | Policy decision và kiểm tra bước cuối | Evidence thiếu hoặc không còn tin cậy | Rule revision và decision |
| RCV-HOLD-01 | Hold bắt buộc không được client bỏ qua | Server transition | Sửa client hoặc gọi API trực tiếp | Hold active, action denied |
| RCV-SESSION-01 | Điều kiện session theo policy được hoàn tất | Session/authz control plane | Session cũ tiếp tục truy cập | Trạng thái thực thi và độ trễ đã định nghĩa |
| RCV-SUPPORT-01 | Hỗ trợ chỉ có quyền trong phạm vi cho phép | Công cụ nội bộ và authorization | Nhân viên không đủ quyền duyệt | Actor role, decision và reference |
| RCV-REVOKE-01 | Current revocation được tôn trọng | Bước cấp quyền/thực hiện | Grant bị thu hồi sau xác minh | Denial theo trạng thái hiện tại |

Các tên trên là ví dụ về truy vết, không phải báo cáo đã chạy kiểm thử cho một hệ thống hiện có.

### 17.1. Tình huống kiểm tra không chỉ có happy path

Nên có mô tả kết quả mong đợi cho:

- Token hết hạn ngay ranh giới.
- Hai lần tiêu thụ đồng thời.
- Resend sau nhiều lần thử sai.
- Thay kênh liên hệ trong lúc recovery đang chờ.
- Provider callback trễ, trùng hoặc không xác minh được.
- Actor hỗ trợ có quyền ở tenant khác.
- Policy revision thay đổi giữa xác minh và commit.
- Session protection chưa đạt dù credential đã thay.
- Audit bắt buộc không thể ghi.
- Thiếu cấu hình policy.
- Người dùng chỉ có client cũ.
- Người dùng dùng công nghệ hỗ trợ và không thực hiện được một bước giao diện cụ thể.

Một quy tắc không có kết quả mong đợi trong nhánh lỗi thường sẽ bị quyết định tùy hứng ở thời điểm nguy hiểm nhất.

### 17.2. Quan sát việc thực thi, không chỉ việc phát request

Nếu policy yêu cầu thu hồi quyền session, một log “revocation requested” chưa đủ. Nếu policy yêu cầu chờ, một sự kiện “đã hiển thị countdown” chưa đủ.

Tài liệu phải xác định bằng chứng vận hành nào phản ánh hành vi thực sự, cùng giới hạn của bằng chứng đó. Điều này giúp tránh nhầm “có log” với “đã đáp ứng kiểm soát”.

## 18. Audit, dữ liệu và lưu giữ

### 18.1. Những gì cần giải thích được sau một quyết định

Hồ sơ nên đủ để trả lời:

- Attempt thuộc phạm vi nào và xử lý loại recovery gì?
- Những rule/revision nào được dùng?
- Loại bằng chứng nào đã được kiểm tra và kết quả ra sao?
- Actor hoặc thành phần nào ra quyết định?
- Grant có scope gì, khi nào được cấp/tiêu thụ/thu hồi?
- Credential, authenticator hoặc session nào bị ảnh hưởng ở mức reference?
- Có ngoại lệ, hold hoặc lỗi một phần không?
- Thông báo đã được yêu cầu và có kết quả giao ở mức nào?

Audit không nên chứa chính các secret dùng để khôi phục tài khoản. Cũng không nên lưu bản chụp tài liệu danh tính trong log ứng dụng tổng quát chỉ để tiện kiểm tra.

### 18.2. Phân biệt kết quả verifier với dữ liệu bằng chứng thô

Nhiều quyết định chỉ cần reference và kết quả của verifier; dữ liệu nhạy cảm thô, nếu thực sự cần thu, phải có kho và quyền truy cập phù hợp.

Policy cần xác định mục đích xử lý, người được xem, thời gian lưu và cách xử lý dữ liệu liên quan sự cố. Không tự chọn thời hạn lưu “vĩnh viễn” vì sợ thiếu dữ liệu về sau.

Thời hạn và nghĩa vụ cụ thể tùy bối cảnh áp dụng. Tài liệu nên trỏ tới chính sách lưu giữ và quản trị dữ liệu được tổ chức xác định, thay vì bịa một con số chung cho mọi quốc gia hoặc loại dữ liệu.

### 18.3. Giữ được lịch sử mà không giữ mọi secret

Có thể lưu các reference để đối soát, state version, policy revision, outcome và thời điểm. Việc điều tra một token đã được dùng không nhất thiết yêu cầu giữ token thô.

Nếu phát hiện secret đã lọt vào log, xử lý như một sự cố dữ liệu theo quy trình tương ứng. Không phát tán thêm bản log qua tài liệu hoặc ticket công khai.

## 19. Công bố, đào tạo và duy trì tài liệu

### 19.1. Phân tầng nội dung theo người đọc

Nội dung người dùng cần dễ hiểu: điều kiện chuẩn bị, phương án được hỗ trợ, thời gian chờ được công bố, quyền sau recovery và cách báo sai phạm.

Nội dung hỗ trợ cần rõ quyết định: bằng chứng được phép, thao tác được cấp quyền, cách chuyển tuyến và cách giải thích từ chối.

Nội dung kỹ thuật cần rõ enforcement: state transition, version, scope, invalidation và quan sát.

Một số chi tiết phát hiện lạm dụng có thể được hạn chế truy cập, nhưng bảo mật của luồng không được phụ thuộc hoàn toàn vào việc giấu một quy tắc. Các kiểm soát cấp quyền vẫn phải có hiệu lực khi kẻ tấn công biết cách hệ thống hoạt động.

### 19.2. Một thay đổi policy cần cập nhật cả những nơi dẫn xuất

Các nơi dễ lệch gồm:

- Trang trợ giúp và bản dịch.
- Nội dung email/SMS/push.
- Kịch bản hỗ trợ và training.
- API contract và reason mapping.
- Control profile, feature flag và cấu hình.
- Tình huống kiểm thử.
- Dashboard và định nghĩa metric.
- Runbook sự cố và hồ sơ truy vết.

Nếu bản dịch chưa cập nhật, cần có cách xử lý rõ và an toàn cho người dùng bị ảnh hưởng. Không coi việc trang chính đã sửa là đủ.

### 19.3. Review theo thay đổi rủi ro và bằng chứng vận hành

Các trigger xem xét lại có thể gồm:

- Bổ sung authenticator hoặc phương án recovery.
- Thay provider hoặc mô hình danh tính.
- Sự cố chiếm tài khoản hoặc lộ secret.
- Phát hiện chặn nhầm hoặc thất bại ở nhóm người dùng cụ thể.
- Thay đổi khả năng session revocation.
- Chuẩn tham chiếu hoặc yêu cầu áp dụng thay đổi.
- Phát hiện công cụ hỗ trợ có khả năng vượt policy.
- Khác biệt giữa tài liệu và hành vi triển khai.

Tỷ lệ recovery thành công cao không tự chứng minh policy tốt. Cần đọc cùng dữ liệu lạm dụng, khôi phục trái phép, chặn nhầm, độ trễ và khoảng trống telemetry. Một cải thiện trải nghiệm chỉ có ý nghĩa khi vẫn giữ điều kiện cấp quyền an toàn.

## 20. Ví dụ chuyển một câu mơ hồ thành quy tắc dùng được

### Ví dụ 1: “Có email thì được reset MFA”

Vấn đề: chưa xác định email được thiết lập lúc nào, có bị nghi chiếm không, có đủ cho loại tài khoản không và hành động reset bao gồm quyền gì.

Cách ghi tốt hơn:

> Chỉ chấp nhận phương án email trong những tổ hợp recovery đã được phê duyệt cho nhóm tài khoản và tình huống tương ứng. Kênh vừa được người yêu cầu thêm trong cùng luồng không được tự dùng làm căn cứ duy nhất cho quyền thay MFA. Mọi grant phải giới hạn đúng thao tác được xét duyệt.

### Ví dụ 2: “Token có hiệu lực trong một thời gian ngắn”

Vấn đề: không có đơn vị, điểm bắt đầu, loại token và sự kiện vô hiệu.

Cách ghi tốt hơn:

> Hạn token được lấy từ control profile có phiên bản cho đúng phương án. Tài liệu profile xác định thời điểm bắt đầu, điều kiện hết hạn, quy tắc phát lại, ngân sách thử và các sự kiện thu hồi. Server kiểm tra các điều kiện ấy khi sử dụng token.

Profile thực tế vẫn phải có giá trị cụ thể; câu chính sách không thay thế phần đó.

### Ví dụ 3: “Support có thể xử lý trường hợp đặc biệt”

Vấn đề: một câu có thể mở toàn bộ đường bỏ qua bảo mật.

Cách ghi tốt hơn:

> Nhân viên chỉ được dùng các quyền và loại bằng chứng ghi trong quy trình hỗ trợ tương ứng. Trường hợp ngoài phạm vi phải chuyển vai trò có thẩm quyền; việc chuyển tuyến không tự cấp quyền khôi phục. Ngoại lệ có reference, phạm vi, thời hạn và audit.

### Ví dụ 4: “Đổi mật khẩu xong thì tài khoản đã an toàn”

Vấn đề: có thể còn session của kẻ tấn công, authenticator trái phép hoặc recovery link chưa dùng.

Cách ghi tốt hơn:

> Điều kiện hoàn tất phụ thuộc tình huống recovery. Với nghi ngờ chiếm quyền, quy trình phải xử lý các đối tượng xác thực và session liên quan theo phạm vi đã xác định, đồng thời kiểm tra những thay đổi recovery không được cho phép trước khi tuyên bố khôi phục quyền kiểm soát.

### Ví dụ 5: “Dùng policy mới nhất”

Vấn đề: không tái hiện được quyết định, không biết attempt đang chạy xử lý ra sao và không phân biệt rule mới với lệnh thu hồi khẩn cấp.

Cách ghi tốt hơn:

> Mỗi điểm quyết định ghi revision đã thực thi. Chính sách chuyển tiếp xác định cách xử lý attempt hiện có. Các điều kiện từ chối và thu hồi hiện hành được kiểm tra theo quy tắc đã công bố trước khi thực hiện hành động nhạy cảm.

Tài liệu chính sách có giá trị khi người đọc xác định được **điều kiện cấp quyền, phạm vi hành động, cách xử lý thất bại và nguồn bằng chứng cho quyết định**. Nó cần nối được tới triển khai và vận hành, đồng thời đủ rõ để người dùng không phải dựa vào những lời hứa vượt quá khả năng bảo vệ thực tế của hệ thống.
