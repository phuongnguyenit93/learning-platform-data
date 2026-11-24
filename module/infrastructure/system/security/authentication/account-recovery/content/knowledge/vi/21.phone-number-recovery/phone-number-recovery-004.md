# Phone number change delay — Khoảng chờ khi thay đổi số điện thoại

Trong chương **Phone Number Recovery** của module `SECURITY_AUTHENTICATION_ACCOUNT_RECOVERY`, **phone number change delay** là cơ chế trì hoãn việc trao quyền xác thực hoặc khôi phục tài khoản cho một số điện thoại mới. Khoảng chờ tạo cơ hội phát hiện, phản đối và xử lý thay đổi trái phép trước khi kẻ tấn công dùng số của họ để chiếm quyền.

Cơ chế này đặc biệt quan trọng khi số điện thoại nhận mã đăng nhập, SMS MFA hoặc token reset mật khẩu. Tuy vậy, thời gian trôi qua không chứng minh danh tính. Thiết kế an toàn phải kết hợp xác minh người yêu cầu, xác nhận quyền kiểm soát số mới, thông báo qua kênh đã thiết lập, kiểm tra rủi ro và quản lý session.

Bài học xây dựng một mô hình tham khảo: số mới ở trạng thái chờ, chưa có quyền recovery; sau khoảng chờ, người dùng phải chủ động hoàn tất và cung cấp bằng chứng còn hiệu lực. Thời lượng và điều kiện cụ thể là chính sách của sản phẩm, không phải một con số bắt buộc cho mọi ứng dụng.

## 1. Khoảng chờ đang bảo vệ thao tác nào?

### 1.1. Phân biệt ba loại thời gian

| Cơ chế | Mục tiêu | Trong khoảng đó, số mới được làm gì? |
|---|---|---|
| Trì hoãn kích hoạt số mới | Ngăn thay kênh xác thực hoặc recovery quá nhanh | Chỉ nhận challenge để chứng minh quyền kiểm soát, chưa nhận quyền đăng nhập/reset |
| Hạn chế sau khi đã đổi số | Giảm rủi ro ở một số thao tác nhạy cảm sau thay đổi | Quyền tùy thiết kế; phải xác định rõ từng thao tác bị hạn chế |
| Cooldown gửi lại SMS | Chống spam, chi phí và lạm dụng OTP | Không tự quyết định thời điểm số mới có quyền |

Nếu sản phẩm lưu số mới làm `ACTIVE` ngay rồi chỉ cấm rút tiền 24 giờ, đó không phải mô hình trì hoãn kích hoạt. Kẻ tấn công vẫn có thể reset mật khẩu hoặc nhận mã đăng nhập trong thời gian ấy nếu các endpoint khác không bị chặn.

Mô hình trong bài chọn:

~~~text
Số mới đã nhận đúng OTP
  -> bằng chứng kiểm soát số trong một giao dịch cụ thể

Đủ thời gian chờ
  -> được xem xét bước hoàn tất

Đủ thời gian + đủ bằng chứng hiện tại + chính sách còn hợp lệ
  -> có thể commit binding mới
~~~

Không có bước nào tự suy ra “đã đăng nhập”, “đã đủ MFA” hoặc “được xóa passkey” chỉ từ việc chờ đủ lâu.

### 1.2. Thay số trong ứng dụng khác với SIM swap

Hai sự kiện cần phân biệt:

- **Thay số trong ứng dụng:** tài khoản chuyển từ số A sang số B qua một quy trình của sản phẩm.
- **SIM swap hoặc chuyển quyền điều khiển số:** số A vẫn giữ nguyên trong database, nhưng người nhận SMS đã thay đổi ở phía mạng viễn thông.

Khoảng chờ cho A -> B không phát hiện được mọi trường hợp số A bị chiếm mà không có request đổi số. Những rủi ro đó cần được đánh giá tại cả bước gửi mã, xác thực và recovery.

NIST SP 800-63B-4 coi việc thiết lập hoặc đổi số đăng ký cho xác thực ngoài băng qua PSTN là gắn một authenticator mới. Tài liệu cũng yêu cầu quản lý việc dùng PSTN như một phương thức bị hạn chế và khuyến nghị xem xét các tín hiệu như thay SIM, đổi thiết bị hoặc chuyển mạng giữ số. Phạm vi này nói về số dùng cho xác thực, không tự áp dụng cho mọi trường điện thoại liên hệ trong hồ sơ. [NIST SP 800-63B-4 — Authentication Using the Public Switched Telephone Network](https://pages.nist.gov/800-63-4/sp800-63b/authenticators/#authentication-using-the-public-switched-telephone-network).

## 2. Các bất biến phải giữ trong thời gian chờ

Thiết kế nên ghi rõ các điều không được vi phạm:

1. Số `PENDING` không được dùng ở endpoint đăng nhập, reset mật khẩu, bỏ MFA hoặc khôi phục passkey.
2. Một mã gửi để xác nhận số đang chờ không dùng được làm mã đăng nhập.
3. Mỗi tài khoản và mục đích có giới hạn số yêu cầu đang mở theo chính sách.
4. Người chưa được xác minh không được tạo thay đổi, hủy yêu cầu hợp lệ hoặc khóa tài khoản của người khác.
5. Sửa số đích không được giữ lại thời gian đã chờ cho số trước.
6. Hết khoảng chờ không biến bằng chứng cũ thành bằng chứng còn hiệu lực.
7. Quyết định kích hoạt phải kiểm tra trạng thái hiện tại ở phía server trong giao dịch.
8. Số cũ bị xác định mất an toàn phải được vô hiệu theo quy trình thích hợp, không bắt buộc giữ hoạt động tới hết khoảng chờ.
9. Không endpoint, nhân viên hỗ trợ hoặc công cụ quản trị nào được vô tình bỏ qua cùng chính sách.
10. Sau khi kích hoạt, quyền gắn với binding cũ phải bị xử lý theo phiên bản và trạng thái đã định nghĩa.

Không dùng một cột `phone_number` vừa chứa số hiện hành vừa chứa số đang chờ. Cách đó dễ khiến một service chọn nhầm số mới vì nó chỉ biết đọc trường quen thuộc.

Cũng không dùng quy tắc fallback:

~~~text
Không gửi được OTP tới số hiện hành
  -> thử gửi sang pending_phone_number.
~~~

Fallback này trao quyền cho số mới trước khi khoảng chờ kết thúc và có thể trở thành đường chiếm đoạt tài khoản.

## 3. Mối đe dọa và lợi ích thực tế của khoảng chờ

| Tình huống | Khoảng chờ giúp gì? | Điều vẫn phải có |
|---|---|---|
| Kẻ tấn công lấy được session | Tạo thời gian để chủ tài khoản thấy cảnh báo và phản đối | Xác thực lại, giới hạn session và kiểm tra quyền |
| Người dùng bị phishing để đổi số | Giảm khả năng hoàn tất chiếm đoạt ngay trong một phiên | Nội dung xác nhận rõ mục đích và bằng chứng phù hợp |
| Số mới có dấu hiệu vừa thay SIM | Có thời gian bổ sung đánh giá rủi ro | Không coi chờ đủ là tín hiệu chắc chắn hết nguy cơ |
| Chủ tài khoản mất số cũ | Cho phép đường thay thế có kiểm soát | Bằng chứng độc lập, không buộc OTP tới số đã mất |
| Kẻ tấn công giữ được quyền lâu hơn khoảng chờ | Có thể không ngăn được hoàn toàn | Kiểm tra lại trước kích hoạt và xử lý dấu hiệu xâm phạm |
| Người dùng không nhận hoặc không đọc cảnh báo | Lợi ích phát hiện suy giảm | Kênh thông báo độc lập, xử lý lỗi gửi và giao diện rõ |

Khoảng chờ là một lớp phòng vệ, không phải một yếu tố xác thực. Việc người dùng không phản đối cũng không đồng nghĩa họ đã đồng ý: họ có thể đang mất thiết bị, không có mạng hoặc bị kẻ tấn công che thông báo.

OWASP khuyến nghị coi thay yếu tố MFA là thao tác rủi ro cao, xác thực lại bằng phương tiện đã đăng ký, không dựa riêng vào session đang mở và thông báo qua kênh ngoài giao dịch. OWASP cũng nêu việc cân nhắc trì hoãn hoặc xác minh tăng cường cho tài khoản có giá trị cao. Bài này cụ thể hóa một mô hình trì hoãn; không suy ra có thời lượng chuẩn được OWASP ấn định. [OWASP Multifactor Authentication — Changing MFA Factors](https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html#changing-mfa-factors).

## 4. Chọn thời điểm bắt đầu và thời lượng chờ

### 4.1. Không cho tích lũy thời gian từ một yêu cầu chưa đủ điều kiện

Nếu bắt đầu đếm ngay khi tạo bản nháp, kẻ tấn công có thể tạo yêu cầu trước, chờ đủ lâu, rồi mới chiếm session và xác minh số đích để kích hoạt ngay.

Trong mô hình tham khảo, thời điểm bắt đầu là:

~~~text
t0 = max(
  thời điểm chấp nhận quyền yêu cầu đổi số,
  thời điểm xác minh ban đầu số mới,
  thời điểm hoàn tất điều kiện phát cảnh báo bắt buộc
)

ready_at = t0 + delay_duration
expires_at = t0 + completion_window

completion_window > delay_duration
~~~

Tất cả mốc là thời gian do server ghi từ sự kiện có thẩm quyền. Client không gửi một `t0` do họ tự chọn.

“Hoàn tất điều kiện phát cảnh báo” cần được định nghĩa vận hành. Ví dụ, dịch vụ đã xác thực và lưu bền vững việc nhà cung cấp chấp nhận thông báo tới tập kênh độc lập được chính sách yêu cầu. Nhà cung cấp chấp nhận không chứng minh người nhận đã đọc, thậm chí không luôn chứng minh thông báo đã được giao.

Nếu chỉ ghi một hàng outbox nhưng worker đang ngừng hoạt động, không nên hiển thị rằng người dùng đã được cảnh báo. Sản phẩm cần quyết định rõ ngưỡng nào đủ để bắt đầu khoảng chờ, và xử lý rủi ro của ngưỡng đó.

Nếu không có kênh nào đủ điều kiện hoặc phát cảnh báo thất bại, yêu cầu ở trạng thái chờ xử lý thông báo hoặc chuyển đường recovery phù hợp. Không âm thầm coi thất bại gửi là đồng ý.

### 4.2. Thời lượng theo rủi ro, không theo một hằng số tùy ý

| Bối cảnh | Hướng chính sách có thể phù hợp |
|---|---|
| Còn passkey đáng tin, thiết bị quen thuộc, kênh độc lập hoạt động | Khoảng chờ cơ sở và xác minh hoàn tất phù hợp |
| Thay số cùng lúc reset mật khẩu hoặc thay MFA | Kéo dài, thêm bằng chứng hoặc chuyển xem xét |
| Có tín hiệu SIM swap, chuyển mạng hoặc hành vi bất thường | Tạm giữ và đánh giá lại thay vì chỉ cho đồng hồ chạy |
| Tài khoản có quyền quản trị hoặc dữ liệu nhạy cảm | Chính sách chặt hơn, có thể cần người duyệt độc lập |
| Mất mọi phương tiện xác thực | Quy trình recovery riêng với bằng chứng và thời gian đã định nghĩa |

Ví dụ minh họa có thể chọn khoảng chờ 24 giờ và cửa sổ hoàn tất 72 giờ tính từ `t0`. Đây là tham số giảng giải, không phải cam kết rằng 24 giờ đủ chống SIM swap hoặc là yêu cầu của NIST.

Nếu phải tăng thời gian chờ do rủi ro mới:

~~~text
ready_at_mới = max(ready_at_hiện_tại, mốc_do_chính_sách_mới_yêu_cầu)
~~~

Không tự rút ngắn hạn chỉ vì điểm rủi ro giảm ở một lần tính sau. Nếu có cơ chế cho phép rút ngắn, nó phải là một quyết định riêng có bằng chứng, phân quyền và audit.

Mỗi yêu cầu lưu phiên bản chính sách và thời lượng đã chấp nhận. Tuy nhiên, chính sách bị thu hồi hoặc một lệnh giữ an toàn hiện tại vẫn có thể ngăn kích hoạt; lưu phiên bản cũ không cấp quyền bỏ qua quyết định an ninh mới.

### 4.3. Mỗi thời hạn có một chức năng

| Mốc thời gian | Chức năng |
|---|---|
| `challenge_expires_at` | Hạn dùng OTP hoặc challenge xác nhận số |
| `ready_at` | Thời điểm sớm nhất có thể xét kích hoạt |
| `expires_at` | Hạn cuối hoàn tất yêu cầu |
| `evidence_valid_until` | Thời hạn một bằng chứng được phép sử dụng |
| `risk_observed_at` | Độ mới của thông tin rủi ro |
| `resend_after` | Thời điểm được yêu cầu gửi lại SMS |

Không kéo OTP sống suốt 24 giờ chỉ vì khoảng chờ kéo dài 24 giờ. Mã ngắn hạn và hồ sơ thay đổi là hai thực thể có vòng đời khác nhau.

Xác minh lại cùng số sau khi chờ có thể làm mới bằng chứng kiểm soát số mà không khởi động lại toàn bộ thời gian. Điều này chỉ áp dụng nếu số đích, generation và điều kiện chính sách không thay đổi. Đổi sang một số khác phải tạo phạm vi xác minh và khoảng chờ mới.

## 5. Mô hình trạng thái và quyền sử dụng từng số

### 5.1. Vòng đời yêu cầu

~~~mermaid
stateDiagram-v2
    [*] --> PROOF_PENDING: Yêu cầu đã được phép khởi tạo
    PROOF_PENDING --> ALERT_PENDING: Xác nhận số mới
    ALERT_PENDING --> WAITING: Đủ điều kiện cảnh báo, ấn định t0
    WAITING --> APPLIED: Đủ thời gian và đủ điều kiện hiện tại
    WAITING --> HELD: Phản đối hợp lệ hoặc rủi ro mới
    HELD --> WAITING: Được giải quyết theo chính sách
    PROOF_PENDING --> CANCELLED
    ALERT_PENDING --> CANCELLED
    WAITING --> CANCELLED
    HELD --> CANCELLED
    WAITING --> SUPERSEDED: Thay bằng yêu cầu mới có quyền
    PROOF_PENDING --> EXPIRED
    ALERT_PENDING --> EXPIRED
    WAITING --> EXPIRED
    HELD --> EXPIRED
    APPLIED --> [*]
    CANCELLED --> [*]
    SUPERSEDED --> [*]
    EXPIRED --> [*]
~~~

Các trạng thái trước `WAITING` cũng cần hạn tối đa riêng để không giữ dữ liệu, chiếm suất hoặc gửi thông báo vô hạn.

Không nhất thiết lưu một trạng thái `READY` trong database. Có thể tính việc “đã hết khoảng chờ” bằng thời gian server:

~~~text
delay_elapsed =
  state == WAITING
  AND server_now >= ready_at
  AND server_now < expires_at
~~~

Đây chỉ là điều kiện thời gian. Nó không khẳng định người dùng đã đủ quyền kích hoạt.

Ở `HELD`, không cho job đến hạn tự bỏ giữ. Khi giải quyết, quyết định rõ khoảng giữ có được tính vào thời gian chờ hay cần một khoảng mới. Trong ví dụ thận trọng, lần mở lại phải bảo đảm đủ cửa sổ thông báo và không đưa `ready_at` về sớm hơn giá trị đã có.

### 5.2. Số cũ, số mới và số bị thu hồi

| Đối tượng | Có thể nhận gì trong lúc chờ? | Không được tự có quyền gì? |
|---|---|---|
| Số hiện hành còn đáng tin | Mã cho chức năng vốn được phép và cảnh báo phù hợp | Không tự đủ để duyệt mọi thay đổi nếu có dấu hiệu bị chiếm |
| Số hiện hành đã bị thu hồi | Chỉ thông báo không mang quyền nếu chính sách cho phép | OTP đăng nhập, reset hoặc recovery |
| Số mới đang chờ | Challenge `VERIFY_PENDING_PHONE` và thông tin tối thiểu | Đăng nhập, reset, xóa MFA, khôi phục passkey |
| Kênh độc lập đã thiết lập | Cảnh báo và cơ chế phản đối giới hạn | Không tự trở thành quyền đăng nhập nếu chỉ là kênh thông báo |

Một số mất an toàn cần được thu hồi theo quy trình có bằng chứng, ngay cả khi số thay thế chưa hoạt động. Nếu không còn phương tiện dùng được, tài khoản đi qua recovery có kiểm soát; không duy trì một authenticator bị chiếm chỉ để tránh bất tiện.

NIST mô tả việc vô hiệu authenticator khi bị xâm phạm và đánh giá tính xác thực của yêu cầu vô hiệu. Điều đó cần được phân biệt với việc chờ gắn số thay thế. [NIST SP 800-63B-4 — Invalidation](https://pages.nist.gov/800-63-4/sp800-63b/events/#invalidation).

## 6. Khởi tạo và xác minh số mới

### 6.1. Xác thực quyền yêu cầu

Một session đang mở chỉ cho biết phiên trước đó đã được tạo. Nó có thể đã bị đánh cắp. Thay kênh recovery thường cần xác thực lại bằng phương tiện đã đăng ký và đánh giá mức bảo đảm phù hợp với tài khoản.

Nếu còn số cũ và nó đáng tin, một bằng chứng qua số cũ có thể tham gia chính sách. Không xem đó là lựa chọn duy nhất cho mọi trường hợp.

Nếu người dùng mất số cũ nhưng còn passkey, TOTP hoặc recovery code đã thiết lập, dùng luồng phù hợp để chứng minh quyền yêu cầu. Nếu mất cả mật khẩu, MFA và thiết bị, chuyển sang quy trình xác minh khác; không tự bỏ kiểm tra vì “đã chọn chờ lâu”.

Thông tin tên thật, ngày sinh hoặc địa chỉ biết được không tự chứng minh người yêu cầu là chủ tài khoản. Một số mới nhận được OTP cũng chỉ chứng minh quyền kiểm soát số mới trong phạm vi challenge.

### 6.2. Chuẩn hóa và giới hạn số đích

Dùng bộ phân tích số điện thoại phù hợp, có vùng/quốc gia rõ ràng và cùng chính sách với đăng ký. Duy trì biểu diễn chuẩn của sản phẩm, chẳng hạn dạng quốc tế E.164 khi áp dụng.

Không lưu số như kiểu số nguyên làm mất ký tự hoặc quy tắc biểu diễn. Chuẩn hóa đúng không chứng minh số đã được cấp, nhận SMS được hay thuộc về người dùng.

Nếu hỗ trợ một số dùng chung cho gia đình hoặc nhiều tài khoản, liên kết phải gắn với từng tài khoản và tenant. Không mặc định một OTP cho số đó được phép liệt kê hoặc thay đổi mọi tài khoản liên quan.

Nếu sản phẩm yêu cầu số duy nhất trong một phạm vi, thực thi bằng ràng buộc kho dữ liệu tại lúc áp dụng. Không tự gộp tài khoản hoặc chuyển số khỏi tài khoản khác để giải quyết xung đột.

### 6.3. Ràng buộc challenge

Challenge xác nhận số mới cần gắn với:

~~~text
purpose = VERIFY_PENDING_PHONE
account_id, tenant_id
change_id, generation
normalized_new_phone
context_binding
expires_at, attempt_budget
base_security_epoch hoặc phạm vi thu hồi tương đương
~~~

Không chỉ dùng `verifyOtp(phone, code)` rồi chia sẻ kết quả cho mọi endpoint. Không cho đổi `change_id` hoặc số đích trong request verify để tái sử dụng một mã.

Mã phải ngẫu nhiên, ngắn hạn, dùng một lần và có ngân sách đoán. Với OTP ngắn, cần bảo vệ verifier phía server và giới hạn thử theo nhiều chiều; chỉ lưu hash không khóa không ngăn dò toàn bộ không gian mã khi kho dữ liệu bị lộ.

Resend thay generation theo hợp đồng, không đặt lại ngân sách thất bại chung và không làm mất `ready_at` của một yêu cầu đang hợp lệ chỉ vì tin nhắn đến chậm. Worker không được gửi mã cũ như thể nó còn hiện hành.

## 7. Thông báo và phản đối trong cửa sổ chờ

### 7.1. Kênh phải độc lập với số đang thay

Thông báo chỉ gửi tới số mới không tạo cơ hội bảo vệ cho chủ tài khoản nếu đó là số của kẻ tấn công.

Dùng các kênh đã thiết lập như email bảo mật, thiết bị nhận push được tin cậy hoặc số cũ còn phù hợp. Không tự chọn một email vừa được thêm từ cùng session đáng ngờ làm kênh độc lập duy nhất.

Tập kênh cảnh báo cần có nguồn gốc và phiên bản. Nếu người dùng thay kênh cảnh báo trong lúc chờ, đánh giá xem có làm mất cửa sổ phát hiện hay không; không để kẻ tấn công xóa kênh cũ rồi viện lý do “không còn nơi gửi”.

Nội dung nên nêu:

- Có yêu cầu thay số điện thoại bảo mật.
- Thời điểm yêu cầu và thời điểm sớm nhất có thể hoàn tất.
- Số đích được che phù hợp.
- Những quyền chưa được chuyển cho số mới.
- Cách phản đối nếu người nhận không thực hiện yêu cầu.

NIST yêu cầu thông báo độc lập cho các sự kiện tài khoản liên quan theo mô hình của họ và hướng dẫn rõ khi người nhận phản đối. Bài này dùng nguyên tắc thông báo đó để thiết kế cửa sổ chờ, không coi trạng thái giao SMS là bằng chứng người dùng chấp thuận. [NIST SP 800-63B-4 — Account Notifications](https://pages.nist.gov/800-63-4/sp800-63b/events/#account-notifications).

### 7.2. Phản đối không được trở thành đường chiếm đoạt hoặc gây gián đoạn

Một liên kết cảnh báo có thể mang token `REPORT_PHONE_CHANGE`, gắn với sự kiện và tài khoản. Quyền của token phải hẹp: báo sự cố hoặc áp dụng giới hạn an toàn đã định nghĩa, không cho sửa số đích hoặc đăng nhập.

Một lựa chọn khác là yêu cầu người nhận xác thực bằng phương tiện đủ mạnh để hủy. Khi người dùng không thể xác thực bình thường, cần context recovery riêng để tiếp nhận bằng chứng thay vì bỏ hẳn bước xác minh.

GET từ email scanner chỉ hiển thị hướng dẫn, không hủy yêu cầu, tiêu thụ token hoặc khóa tài khoản. Hành động thay đổi trạng thái cần bước chủ đích và kiểm soát thích hợp; đổi sang POST chưa tự bảo đảm người thao tác có quyền.

Nếu chỉ có báo cáo công khai chưa xác minh, không hủy yêu cầu hợp lệ của chủ tài khoản. Ngược lại, nếu đã có phản đối đủ điều kiện và commit trạng thái `HELD`, không cho job lịch trình tự tiếp tục.

### 7.3. Lỗi gửi cảnh báo không được biến thành lối tắt

Lưu riêng các trạng thái như `QUEUED`, `PROVIDER_ACCEPTED`, `DELIVERY_REPORTED`, `FAILED`. Không dùng một cờ `notified=true` để biểu diễn tất cả.

Webhook giao nhận phải được xác thực, chống phát lại và gắn đúng thông báo/generation. Một callback trùng không được đặt lại `t0` hoặc rút ngắn `ready_at`.

Khi nhà cung cấp ngừng dịch vụ, retry có giới hạn và dùng kênh thay thế đã được chính sách cho phép. Không chuyển sang số mới để giả lập rằng đã cảnh báo được chủ tài khoản.

## 8. Thời gian phải được thực thi ở server

### 8.1. Đồng hồ trên giao diện chỉ dùng để hướng dẫn

Response cho người đã được phép quản lý yêu cầu có thể gồm:

~~~json
{
  "changeRef": "change-example-41",
  "state": "WAITING",
  "maskedNewPhone": "+84 *** *** 482",
  "serverNow": "2026-11-23T03:00:00Z",
  "readyAt": "2026-11-24T03:00:00Z",
  "expiresAt": "2026-11-26T03:00:00Z",
  "nextAction": "WAIT"
}
~~~

Các giá trị chỉ minh họa khoảng chờ 24 giờ và cửa sổ hoàn tất 72 giờ. Chúng được trả sau kiểm tra quyền, không phải endpoint tra cứu tài khoản qua số điện thoại.

Client có thể tính đồng hồ đếm ngược để hiển thị. Thay giờ máy, sửa JavaScript hoặc gửi `delayElapsed=true` không làm thay đổi quyết định của backend.

Dùng mốc thời gian tuyệt đối thống nhất, thường lưu UTC. Phân biệt khoảng thời gian 24 giờ với “đến ngày mai theo múi giờ người dùng”; đây không luôn là cùng một quy tắc. Giao diện có thể đổi cách hiển thị nhưng không tự đổi điều kiện server.

### 8.2. Job chỉ đánh thức luồng, không cấp quyền

Không giữ một thread Java bằng `Thread.sleep` trong suốt khoảng chờ. Lưu trạng thái và mốc thời gian bền vững để ứng dụng có thể khởi động lại hoặc chuyển instance.

Scheduler có thể tìm yêu cầu đến hạn để gửi nhắc nhở. Một message như:

~~~json
{
  "eventType": "PHONE_CHANGE_DELAY_ELAPSED",
  "changeRef": "change-example-41",
  "generation": 2
}
~~~

chỉ là tín hiệu xử lý. Worker vẫn phải đọc lại trạng thái hiện tại. Message cũ, gửi sớm, trùng hoặc đến sau lúc hủy không có quyền kích hoạt số.

Trong mô hình của bài, worker không tự kích hoạt. Người dùng phải mở bước hoàn tất, xác minh lại theo chính sách và gửi lệnh thực thi.

Worker trễ có thể khiến thông báo nhắc hoàn tất đến muộn; nó không được làm cho thay đổi có hiệu lực sớm hơn. Không phụ thuộc vào một lần job chạy duy nhất để bảo đảm đúng nghiệp vụ.

### 8.3. Kiểm tra thời gian sau khi chờ khóa

Nếu transaction bắt đầu lúc 10:00 nhưng chờ khóa đến 10:05, cần thời gian phù hợp tại điểm quyết định, không dùng một timestamp bị đóng băng từ đầu request.

Điều kiện thời gian trong ví dụ:

~~~text
current_time >= ready_at
AND current_time < expires_at
AND current_time < final_phone_evidence.valid_until
AND current_time < final_account_evidence.valid_until
~~~

Phải kiểm tra sau khi giữ được các khóa cần thiết. Nếu database có hàm thời gian trả về mốc bắt đầu transaction, cần chọn cơ chế phù hợp với yêu cầu này; không giả định mọi hàm “now” đều có cùng ngữ nghĩa.

Giám sát lệch đồng hồ và thay đổi thời gian lớn. Một bước nhảy đồng hồ về trước không được tự trở thành lý do bỏ qua hàng giờ chờ mà không được phát hiện. Khi không thể tin cậy thời gian, giữ thao tác nhạy cảm và xử lý sự cố theo cơ chế vận hành, thay vì dùng đồng hồ do client gửi.

## 9. Mô hình dữ liệu và giao dịch kích hoạt

### 9.1. Dữ liệu có thẩm quyền

| Thực thể | Dữ liệu tiêu biểu | Trách nhiệm |
|---|---|---|
| `account_security` | account, tenant, security epoch, recovery version, trạng thái giữ | Quyết định quyền truy cập hiện tại |
| `phone_binding` | binding ID, tài khoản, số chuẩn hóa, vai trò, trạng thái, version | Liên kết số thực sự có quyền |
| `phone_change` | change ID, generation, binding gốc/version, số đích, state, t0, ready/expires, policy version | Yêu cầu thay đổi và thời gian chờ |
| `phone_challenge` | purpose, change/generation, verifier, hạn dùng, ngân sách thử | Xác nhận quyền kiểm soát số |
| `recovery_evidence` | loại, nguồn, phạm vi, thời gian, epoch, trạng thái dùng | Bằng chứng đã được hệ thống xác minh |
| `risk_assessment` | tài khoản/số/sự kiện, nguồn tín hiệu, thời điểm, kết quả, hạn dùng | Đầu vào rủi ro có độ mới xác định |
| `notification_attempt` | kênh snapshot, thế hệ, trạng thái gửi, provider reference | Điều kiện phát cảnh báo và khả năng truy vết |
| `change_receipt` | thao tác, context, kết quả đã commit | Retry không thực hiện lại |
| `security_event`, `notification_outbox` | ID, phiên bản, payload tối thiểu | Audit và giao thông báo sau commit |

Đây là mô hình trách nhiệm, không phải schema hoàn chỉnh. Cần khóa ngoại, kiểm tra tenant, ràng buộc trạng thái và quy tắc duy nhất tương ứng với sản phẩm.

Số điện thoại là dữ liệu cá nhân. Chỉ những thành phần cần gửi hoặc xác minh mới được đọc đầy đủ. Khóa HMAC phục vụ giới hạn theo số có thể giảm việc ghi số rõ, nhưng không tự làm dữ liệu trở thành vô danh.

### 9.2. Chụp trạng thái gốc để phát hiện thay đổi xen giữa

Yêu cầu lưu `base_binding_id`, `base_binding_version`, `base_security_epoch` và phiên bản recovery phù hợp. Khi áp dụng, đối chiếu với dữ liệu hiện tại.

Nếu tài khoản đã đổi số qua một luồng khác, bị thu hồi credential hoặc có sự cố làm epoch đổi, không dùng snapshot cũ để ghi đè. Yêu cầu cần được đánh giá lại hoặc tạo lại với quyền thích hợp.

Không sửa các trường gốc của yêu cầu đang chờ để nó “khớp lại” mà không có quyết định xác minh mới. Việc số hiện tại vẫn có cùng chuỗi ký tự không chứng minh binding, chủ thể kiểm soát và phiên bản vẫn như trước.

Nếu số cũ đã được thu hồi trước khi khởi tạo recovery, có thể tạo yêu cầu dựa trên trạng thái đã thu hồi đó bằng bằng chứng độc lập. Điều này khác với việc tự bỏ qua một lần thu hồi xảy ra sau khi yêu cầu đã được cấp quyền.

### 9.3. Kiểm tra rủi ro ở thời điểm hoàn tất

Có thể thu thập tín hiệu nhà mạng hoặc quyết định rủi ro trước transaction rồi lưu kết quả có phạm vi và TTL. Không nên giữ khóa database trong khi chờ một cuộc gọi mạng dài.

Tuy vậy, kết quả phải gắn đúng tài khoản, số đích, generation và sự kiện. Một kết quả từ số khác hoặc đã hết hạn không được coi là đánh giá hiện tại.

Phân biệt `LOW_RISK`, `HIGH_RISK` và `UNKNOWN`. Không có dữ liệu SIM swap không đồng nghĩa “không có SIM swap”. Khi chính sách bắt buộc đánh giá mà dịch vụ lỗi, không tự hạ thành kết quả an toàn; chuyển giữ hoặc đường xử lý được phép.

Ngay cả một kết quả mới cũng không thể bảo đảm không có sự kiện xảy ra sau thời điểm quan sát. Chính sách cần quy định độ mới chấp nhận được và phản ứng khi nhận tín hiệu mới.

### 9.4. Mã giả cho bước hoàn tất

Đoạn sau minh họa ranh giới nghiệp vụ; các phương thức là thành phần giả định, không phải API thư viện hay ứng dụng chạy nguyên trạng:

~~~java
CompletionResult complete(CompletePhoneChange command) {
    inputLimits.check(command);
    recoveryLimiter.check(command.requestContext());

    // Route lấy từ context được server xác minh và change được phép truy cập.
    ChangeRoute route = access.resolveAuthorizedChange(
            command.requestContext(), command.changeRef());

    CompletionResult result = transactions.execute(tx -> {
        LockedPhoneChange state = store.lockInOrder(tx, route);

        access.requireMatchingAccountTenantAndContext(state, command);

        if (state.hasCommittedReceiptFor(command.operationRef())) {
            return receipts.safeResultForSameContext(state, command);
        }

        policy.requireWaitingAndNotHeld(state);
        policy.requireUnchangedBaseBindingAndSecurityVersions(state);

        // Dùng thời gian hiện tại sau khi đã chờ khóa.
        Instant now = tx.currentWallClockTime();

        policy.requireDelayElapsedAndNotExpired(state, now);
        evidence.requireFreshAccountAuthorization(
                state, command.accountEvidenceRef(), now);
        evidence.requireFreshNewPhoneControl(
                state, command.phoneEvidenceRef(), now);
        risk.requireCurrentAcceptableAssessment(state, now);
        notifications.requireWarningPolicySatisfied(state);

        phoneClaims.checkOrAcquireIfProductRequiresExclusiveUse(tx, state);

        PhoneBinding newBinding =
                bindings.activateNewAndRevokeReplacedBinding(tx, state);

        security.bumpEpochAndRecoveryVersion(tx, state.accountId());
        challenges.invalidateSupersededPhoneChallenges(tx, state);
        evidence.consumeForThisChange(tx, state, command);
        changes.markAppliedAndRecordReceipt(tx, state, newBinding, command);
        audit.appendPhoneChangeApplied(tx, state, newBinding);
        outbox.enqueueCompletionNotifications(tx, state, newBinding);

        return CompletionResult.appliedReauthenticationRequired();
    });

    // Thành công chỉ được trả khi transaction đã commit.
    return result;
}
~~~

Hai bằng chứng cuối có trách nhiệm khác nhau: một chứng minh quyền thay kênh của tài khoản, một chứng minh quyền kiểm soát số đích. Không dùng cùng OTP tới số mới để tự đáp ứng cả hai.

Bằng chứng ở thời điểm khởi tạo có thể đã hết hạn sau 24 giờ. Nó cho phép bắt đầu khoảng chờ, không tự cho phép hoàn tất. Bước cuối cần xác thực lại hoặc một cơ chế ủy quyền recovery còn hiệu lực đúng theo chính sách.

`activateNewAndRevokeReplacedBinding` phải tạo binding mới và tăng version; không đổi cờ trên một số mới rồi để binding cũ tiếp tục nhận reset ngầm.

Các thay đổi dữ liệu, tiêu thụ bằng chứng, ghi kết quả và outbox phải cùng commit. Nếu xung đột số hoặc một kiểm tra thất bại, rollback phần áp dụng; không trả thành công hoặc phát token đăng nhập trước commit.

Kiểm tra OTP sai và giới hạn thử vẫn cần được ghi bền vững trong luồng xác minh tương ứng. Không để exception rollback bộ đếm thất bại khiến kẻ tấn công có ngân sách thử vô hạn.

### 9.5. Kích hoạt cạnh tranh với hủy

Đường hoàn tất và đường hủy phải giữ khóa hoặc cập nhật có điều kiện cùng một trạng thái có thẩm quyền.

~~~text
Nếu hủy commit trước:
  WAITING -> CANCELLED
  hoàn tất phải từ chối.

Nếu hoàn tất commit trước:
  WAITING -> APPLIED
  hủy yêu cầu đang chờ không được ghi đè kết quả đã áp dụng.
~~~

Trường hợp thứ hai trở thành xử lý thay đổi đã xảy ra hoặc sự cố bảo mật, không phải lệnh hủy `PENDING`. Không âm thầm khôi phục số cũ, vì số cũ có thể đã mất an toàn.

Một khóa trong JVM hoặc nút bị vô hiệu trên giao diện không bảo đảm thứ tự này giữa nhiều instance.

## 10. Kiểm soát session, OTP và quyền recovery sau áp dụng

### 10.1. Quyền cũ phải mất hiệu lực thực tế

Khi kích hoạt số mới, hệ thống cần xử lý:

- OTP đang mở gửi tới binding cũ.
- Token reset hoặc grant recovery được cấp theo phiên bản cũ.
- Session, remember-me và quyền bỏ qua xác minh không còn phù hợp.
- Cache hoặc projection định tuyến tin nhắn.
- Alias đăng nhập bằng số điện thoại, nếu có.
- Quyền truy cập đã phát sinh trong một sự cố liên quan.

Tăng `security_epoch` hoặc `recovery_version` chỉ hữu ích nếu nơi nhận thực sự đối chiếu phiên bản. JWT tự chứa không tự mất hiệu lực vì có một hàng database vừa đổi.

Nếu một request reset đã kiểm tra OTP cũ trước khi kích hoạt nhưng ghi mật khẩu sau đó, bước ghi phải kiểm tra lại trạng thái hoặc dùng cập nhật có điều kiện trong cơ chế phối hợp chung. Không chỉ chặn việc gửi OTP mới; cần xử lý cả quyền đã phát hành.

Projection nhận sự kiện muộn không được tiếp tục cấp quyền nhạy cảm theo binding cũ. Nơi ra quyết định cần dùng dữ liệu có thẩm quyền hoặc cơ chế bảo đảm mức nhất quán tương ứng. Nếu còn cửa sổ chậm lan truyền, phải nhận diện giới hạn đó.

### 10.2. Không tự tạo session đầy đủ từ bước đổi số

Hoàn tất thay số không mặc nhiên chứng minh người dùng đã đáp ứng mọi yêu cầu đăng nhập. Đặc biệt, context recovery có thể chỉ được phép thay phương tiện liên hệ.

Sau thay đổi, yêu cầu đăng nhập hoặc xác thực lại theo chính sách; nếu cấp session mới thì xoay secret và gắn với phiên bản mới qua đúng cơ chế xác thực. Không đổi `mfaSatisfied=true` chỉ vì số mới nhận OTP.

MFA và passkey khác vẫn chịu vòng đời riêng. Không xóa chúng chỉ để làm bước thay số dễ hoàn tất hơn. Nếu nghi ngờ credential bị thêm trái phép, mở quy trình xử lý sự cố với quyền và bằng chứng phù hợp.

## 11. Chống lạm dụng và các đường bỏ qua khoảng chờ

### 11.1. Không cho gửi lại hoặc đổi kênh làm mất chính sách

Các biến thể cần cùng kiểm soát:

| Đường đi | Lỗi có thể xảy ra |
|---|---|
| Ứng dụng web, mobile hoặc API phiên bản cũ | Một đường ghi số trực tiếp thành ACTIVE |
| SMS chuyển sang cuộc gọi thoại | Endpoint dự phòng không kiểm tra trạng thái pending |
| Đổi số qua trang hồ sơ | Cập nhật trường contact đồng thời làm đổi nơi gửi reset |
| Nhân viên hỗ trợ | Thực hiện lệnh “đã xác minh” rồi bỏ qua delay |
| Import hoặc đồng bộ danh bạ | Ghi đè số xác thực bằng dữ liệu liên hệ |
| Tạo mới tài khoản cùng số | Gộp hoặc di chuyển quyền dựa riêng vào số mới |
| Reset MFA | Cho chọn pending phone như phương tiện đã đăng ký |
| Kích hoạt bằng job nội bộ | Tin message đến hạn thay vì đọc lại policy và trạng thái |

Mọi đường ghi binding có quyền cần đi qua một quyết định nghiệp vụ tương đương. Không dùng một boolean từ client hoặc hệ thống tích hợp như `skipDelay=true`.

Nếu sản phẩm có ngoại lệ khẩn cấp, phải định nghĩa cụ thể ai được phép, bằng chứng nào đủ, phạm vi, lý do và audit. Ngoại lệ là một quyết định có kiểm soát, không phải fallback tự động khi SMS hoặc risk engine lỗi.

### 11.2. Giới hạn tạo, sửa, gửi và hủy yêu cầu

Áp dụng ngân sách cho khởi tạo, gửi SMS, thử OTP, thay số đích, hoàn tất, phản đối và hỗ trợ. Các giới hạn cần phối hợp theo tài khoản, số, tenant, context, nguồn truy cập và tổng ngân sách nhà cung cấp.

Không đặt lại toàn bộ ngân sách khi đổi IP, resend hoặc tạo `change_id` mới. Đồng thời, đừng cho một request công khai chiếm suất thay số của tài khoản để người dùng thật không thể tiếp tục.

Tạo yêu cầu thay thế phải cần quyền đủ mạnh và ghi rõ `SUPERSEDED` cho yêu cầu cũ. Không cho thời gian chờ đã tích lũy của số B chuyển sang số C.

Một người giữ số cũ không được liên tục phá quy trình chỉ vì họ nhận cảnh báo. Quyền phản đối, mức bằng chứng và cách giải quyết tranh chấp phải được xác định, nhất là khi số cũ đã được cấp lại.

### 11.3. Bảo vệ endpoint và dữ liệu nhạy cảm

Các endpoint quản lý yêu cầu cần kiểm tra tài khoản/tenant/context, chống CSRF nếu dùng cookie và xử lý đầu vào có giới hạn. ID ngẫu nhiên không thay thế phân quyền.

Thông tin trạng thái chỉ trả cho người được phép. Không cho tra số bất kỳ để biết đang thuộc tài khoản nào, đã đổi bao nhiêu lần hoặc còn mấy giờ chờ.

Không ghi OTP, token phản đối, cookie, verifier hoặc số đầy đủ vào log chung. Trang có bí mật cần hạn chế cache, referrer và thành phần thu thập dữ liệu không cần thiết.

Outbox dùng ID sự kiện và version để chịu được retry. Không gửi mã rõ qua event audit được nhiều dịch vụ lưu dài hạn; nếu cần giao bí mật cho worker gửi SMS, dùng cơ chế riêng có bảo vệ và TTL phù hợp.

## 12. Trải nghiệm cho người dùng hợp lệ

Một khoảng chờ có ích về an ninh nhưng cũng có thể làm người dùng bị kẹt khi mất điện thoại. Giao diện cần giải thích rõ điều gì đang chờ và đường nào còn sử dụng được.

Trong thời gian chờ, nên cho người đã được phép:

1. Xem trạng thái và mốc sớm nhất có thể hoàn tất theo giờ địa phương.
2. Biết số mới chưa dùng được cho đăng nhập hoặc reset.
3. Dùng phương tiện xác thực khác còn đáng tin.
4. Hủy hoặc sửa yêu cầu qua quy trình có quyền thích hợp.
5. Báo mất số cũ hoặc nghi ngờ tài khoản bị xâm phạm.
6. Hiểu rằng sửa số đích có thể khởi động lại khoảng chờ.
7. Nhận hướng dẫn rõ khi hết hạn, bị giữ hoặc cần hỗ trợ.

Một thông báo có thể là:

> Số mới đang chờ kích hoạt và chưa nhận mã đăng nhập hoặc đặt lại mật khẩu. Bạn có thể tiếp tục bước xác minh từ 10:00 ngày 24/11 theo giờ hiển thị. Nếu bạn không yêu cầu thay đổi này, hãy mở mục bảo mật hoặc làm theo hướng dẫn báo sự cố.

Không hứa “số sẽ tự đổi lúc 10:00” khi thiết kế yêu cầu người dùng chủ động hoàn tất. Không hiển thị “đã an toàn” chỉ vì countdown bằng 0.

Người không thể nhận SMS ở số cũ cần đường recovery khả dụng. Nếu không có đủ bằng chứng ở bất kỳ đường nào, giải thích giới hạn và quy trình hỗ trợ; không buộc họ cung cấp giấy tờ không liên quan rồi mặc định rằng đã chứng minh chủ sở hữu tài khoản.

## 13. Ví dụ xuyên suốt

### 13.1. Người dùng mất số cũ nhưng còn passkey

An mất quyền dùng số A nhưng còn passkey đã đăng ký và một email bảo mật độc lập.

1. An xác thực bằng passkey và đi qua quy trình báo số A không còn sử dụng được. Hệ thống đánh giá yêu cầu thu hồi theo chính sách; không giữ A hoạt động chỉ để chờ số B.
2. An yêu cầu số B làm phương tiện thay thế. Backend tạo yêu cầu gắn với trạng thái tài khoản có thẩm quyền và chưa cho B quyền recovery.
3. An nhập đúng challenge gửi tới B. Backend ghi nhận bằng chứng ban đầu, đúng change và generation.
4. Cảnh báo được xử lý qua email bảo mật đã thiết lập. Khi đủ điều kiện bắt đầu, backend ghi `t0`, `ready_at=t0+24 giờ` và `expires_at=t0+72 giờ`.
5. Trong 24 giờ, B chỉ nhận challenge cho quy trình thay số. Nếu An cần đăng nhập, dùng passkey hoặc phương án còn được phép.
6. Sau `ready_at`, An quay lại, xác thực lại bằng passkey và xác nhận mới quyền kiểm soát B theo chính sách. Các OTP cũ không được kéo dài hiệu lực.
7. Transaction kiểm tra state, thời gian, binding gốc, epoch, bằng chứng và rủi ro. Nếu đủ điều kiện, kích hoạt B, vô hiệu quyền bị thay thế và ghi audit/outbox.
8. An tiếp tục xác thực theo chính sách của tài khoản. Việc hoàn tất không tự xóa MFA hoặc tạo quyền truy cập vượt context đã có.

Nếu An đổi số đích từ B sang C ở bước 5, C không được hưởng 20 giờ An đã chờ cho B. Cần quyền sửa, challenge mới và lịch chờ phù hợp với yêu cầu mới.

### 13.2. Chủ tài khoản phản đối ngay trước hạn

Một kẻ lấy được session tạo yêu cầu thay số. Chủ tài khoản thấy cảnh báo và hoàn tất bước phản đối đủ điều kiện ngay trước thời điểm sớm nhất có thể kích hoạt.

- Nếu phản đối commit `HELD` trước, request hoàn tất dù đến sau `ready_at` vẫn bị chặn.
- Nếu hoàn tất đã commit trước phản đối, backend không giả vờ yêu cầu còn `WAITING`. Nó mở xử lý thay đổi đã xảy ra, thu hồi và bảo vệ quyền truy cập theo chính sách sự cố.
- Nếu chủ tài khoản chỉ bấm GET từ email, thao tác đó chưa phải quyết định hủy. Trang cần hướng dẫn hành động chủ đích phù hợp.

Ranh giới quan trọng là thứ tự commit và trạng thái có thẩm quyền, không phải thứ tự người dùng nhìn thấy thông báo trên màn hình.

### 13.3. Không có thay số trong ứng dụng nhưng có SIM swap

Số A vẫn là binding hiện hành. Hệ thống nhận được tín hiệu A vừa chuyển SIM trong bối cảnh request reset mật khẩu bất thường.

Không có yêu cầu A -> B nên cơ chế delay của bài không tự chạy. Endpoint reset vẫn phải đánh giá kênh A, bằng chứng khác và chính sách rủi ro. Đây là lý do không được coi “tài khoản không có yêu cầu đổi số đang chờ” là kết luận rằng SMS hiện tại an toàn.

## 14. Các tình huống cần kiểm chứng khi triển khai

Bảng này nêu yêu cầu đối chiếu, không phải kết quả kiểm thử đã chạy trên ứng dụng.

| Tình huống | Điều cần chứng minh |
|---|---|
| Đúng OTP số mới nhưng chưa hết khoảng chờ | Không tạo binding có quyền đăng nhập/reset |
| Người gọi sửa đồng hồ client hoặc `readyAt` | Backend giữ mốc do server quyết định |
| Request tạo từ trước nhưng chưa đủ bằng chứng | Không được tích lũy thời gian để kích hoạt ngay khi mới xác minh |
| Gửi lại SMS hoặc callback giao nhận bị trùng | Không rút ngắn delay hoặc đặt lại ngân sách thử |
| Đổi số đích sau khi đã chờ | Challenge và thời gian cũ không chuyển sang số mới |
| Bằng chứng ban đầu hết hạn trước khi hoàn tất | Cần bằng chứng cuối còn hiệu lực theo chính sách |
| Job đến hạn chạy sớm, trùng hoặc sau hủy | Không tự kích hoạt trái trạng thái |
| Transaction chờ khóa lâu | Kiểm tra thời gian và hạn bằng chứng ở điểm quyết định phù hợp |
| Hủy hoặc phản đối cạnh tranh với hoàn tất | Chỉ kết quả đúng theo thứ tự commit được áp dụng |
| Hai instance hoàn tất cùng yêu cầu | Tối đa một binding mới và một kết quả áp dụng |
| Số cũ bị thu hồi trong khi chờ | Không bỏ qua thay đổi version; không tự giữ authenticator mất an toàn |
| Cùng số bị dùng ở tài khoản khác | Xử lý đúng chính sách chia sẻ hoặc xung đột, không tự gộp |
| Thay số qua web, mobile, support hoặc import | Cùng thực thi ràng buộc nghiệp vụ cần thiết |
| Gửi OTP qua voice thay SMS | Không biến kênh dự phòng thành đường bỏ qua delay |
| Tín hiệu risk thiếu, cũ hoặc sai số | Không được coi là kết quả an toàn hiện tại |
| Token reset cũ được dùng sau kích hoạt | Không vượt qua binding/version đã thu hồi |
| Commit xong nhưng mất response | Retry đọc kết quả có quyền, không áp dụng lần hai |
| Cảnh báo thất bại hoặc provider ngừng dịch vụ | Có trạng thái xử lý rõ, không giả lập đã thông báo |
| Restore database về trước lần áp dụng | Không làm quyền đã thu hồi tự sống lại |
| Số không đổi nhưng bị SIM swap | Có kiểm soát ở luồng xác thực/recovery ngoài cơ chế đổi số |
| Log, metric, trace và trang recovery | Không làm lộ bí mật hoặc thông tin tài khoản ngoài phạm vi |

Các kiểm chứng nên quan sát quyền thực tế: số nào nhận token, token nào được chấp nhận, session nào còn hiệu lực và thay đổi nào đã commit. Chỉ kiểm tra response `WAITING` là chưa đủ nếu một service khác vẫn đọc số mới để gửi reset.

Về vận hành, theo dõi thời gian ở từng trạng thái, lỗi cảnh báo, số lần giữ/hủy, xung đột khi áp dụng và các lần bị từ chối do binding/version thay đổi. Dùng nhãn metric có cardinality phù hợp, không đưa số điện thoại hoặc token làm nhãn.

Tỷ lệ hoàn tất cao không tự chứng minh thiết kế an toàn. Tỷ lệ bỏ cuộc cao cũng không tự là lý do bỏ khoảng chờ; cần biết người dùng đang kẹt ở bằng chứng, giao SMS, thông báo hay việc không còn phương tiện xác thực.

## 15. Tài liệu đối chiếu và phạm vi ví dụ

- [NIST SP 800-63B-4 — Authentication Using the Public Switched Telephone Network](https://pages.nist.gov/800-63-4/sp800-63b/authenticators/#authentication-using-the-public-switched-telephone-network): phạm vi dùng PSTN và các tín hiệu rủi ro cần xem xét.
- [NIST SP 800-63B-4 — Post-Enrollment Binding](https://pages.nist.gov/800-63-4/sp800-63b/events/#post-enroll-bind): gắn phương tiện xác thực sau đăng ký.
- [NIST SP 800-63B-4 — Invalidation](https://pages.nist.gov/800-63-4/sp800-63b/events/#invalidation): xử lý thu hồi authenticator.
- [NIST SP 800-63B-4 — Account Notifications](https://pages.nist.gov/800-63-4/sp800-63b/events/#account-notifications): thông báo sự kiện tài khoản và hướng dẫn phản đối.
- [OWASP Multifactor Authentication — Changing MFA Factors](https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html#changing-mfa-factors): bảo vệ việc thay yếu tố xác thực.

Khoảng chờ 24 giờ, cửa sổ 72 giờ, công thức xác định `t0`, các trạng thái, lựa chọn hoàn tất chủ động và mô hình epoch trong bài là thiết kế tham khảo. Không có kết luận rằng chờ đủ thời gian tự bảo đảm chủ tài khoản, chống được mọi SIM swap hoặc đáp ứng một mức bảo đảm NIST. Khi triển khai, cần đối chiếu chính sách bằng chứng, khả năng thông báo, nguồn thời gian và cơ chế thu hồi quyền thực tế.
