# Password reset policy — Chính sách đặt lại mật khẩu

## 1. Mục tiêu và phạm vi

Trong chương **Password Reset** của module **SECURITY_AUTHENTICATION_ACCOUNT_RECOVERY**, bài học này trình bày cách thiết kế chính sách đặt lại mật khẩu để người dùng lấy lại quyền truy cập mà không tạo đường tắt chiếm đoạt tài khoản.

Một chính sách reset cần trả lời được: **ai được đặt lại mật khẩu nào, dựa trên bằng chứng gì, quyền đó có hiệu lực bao lâu và hệ thống phải thu hồi những gì sau thay đổi?**

Chính sách không chỉ gồm độ dài mật khẩu và thời gian sống của liên kết. Nó là hợp đồng giữa sản phẩm, dịch vụ xác thực, bộ phận hỗ trợ và vận hành.

Sau bài học, người học có thể:

- Phân loại đổi mật khẩu, quên mật khẩu và khôi phục tài khoản bị chiếm.
- Xác định bằng chứng cần có theo loại tài khoản và tình trạng rủi ro.
- Định nghĩa điều kiện của mật khẩu mới, quyền reset và vòng đời yêu cầu.
- Thiết kế việc thu hồi session, giữ nguyên yêu cầu MFA và xử lý lỗi.
- Biểu diễn quyết định bằng dữ liệu có phiên bản để triển khai và audit.

Các bảng, tham số và mã giả trong bài là **chính sách tham khảo của một sản phẩm minh họa**, không phải cấu hình mặc định bắt buộc của NIST hoặc OWASP. Khi áp dụng, cần đối chiếu mô hình đe dọa, mức đảm bảo được yêu cầu và khả năng thực thi của toàn hệ thống.

## 2. Phân biệt các luồng trước khi viết chính sách

| Luồng | Người dùng còn gì? | Mục tiêu | Ranh giới cần giữ |
| --- | --- | --- | --- |
| Đổi mật khẩu chủ động | Có phiên hợp lệ và có thể xác thực lại | Thay mật khẩu trong điều kiện bình thường | Session đang mở không tự đủ để thay bí mật |
| Quên mật khẩu | Không nhớ mật khẩu, còn phương thức được chấp nhận | Cấp quyền đặt một mật khẩu mới | Không bắt nhập mật khẩu đã quên; dùng bằng chứng khác |
| Thay mật khẩu bằng authenticator còn lại | Có thể xác thực bằng phương tiện khác đủ điều kiện | Gắn mật khẩu thay thế theo chính sách | Không hạ mức kiểm tra vì đây là mật khẩu |
| Khôi phục sau chiếm đoạt | Có thể mất cả session, kênh recovery hoặc MFA | Khôi phục quyền kiểm soát thực tế | Đổi mật khẩu đơn lẻ có thể chưa đuổi được đối tượng |
| Quản trị viên hỗ trợ | Có hồ sơ và quyền xử lý được giao | Hướng dẫn hoặc cho phép quy trình xác minh | Không biết hoặc gửi mật khẩu mới thay người dùng |
| Tài khoản chỉ dùng SSO | Mật khẩu thuộc identity provider | Chuyển đến đúng cơ quan quản lý credential | Ứng dụng không tự tạo mật khẩu cục bộ |
| Tài khoản chỉ dùng passkey | Không có mật khẩu cục bộ | Dùng luồng phù hợp với passkey | Không tự thêm đường đăng nhập bằng mật khẩu yếu hơn |

NIST phân biệt việc thay mật khẩu khi còn xác thực được bằng authenticator khác với account recovery khi không còn đủ phương tiện để đạt mức xác thực mong muốn. Sự phân loại này ảnh hưởng tới yêu cầu gắn credential và bằng chứng cần dùng. [NIST SP 800-63B-4, Account Recovery](https://pages.nist.gov/800-63-4/sp800-63b/events/#recovery)

Trong bài, từ **reset** chỉ việc cấp quyền đặt lại mật khẩu. Không mặc nhiên bao gồm đổi email, xóa TOTP, gỡ passkey hoặc mở lại tài khoản đã bị quản trị viên đình chỉ.

## 3. Các nguyên tắc làm nền cho chính sách

### 3.1. Xác định đúng nơi sở hữu mật khẩu

Dịch vụ cần xác định tài khoản có mật khẩu cục bộ hay do hệ thống bên ngoài quản lý. Với tài khoản SSO, giao diện có thể hướng dẫn đến IdP theo cấu hình tin cậy; không nhận một URL do người yêu cầu tự cung cấp.

Một tenant có thể hỗ trợ cả SSO lẫn tài khoản cục bộ. Phân loại phải dựa trên bản ghi tài khoản và chính sách tenant, không chỉ đoán từ hậu tố email.

### 3.2. Tách bằng chứng khỏi tín hiệu rủi ro

Bằng chứng giúp chứng minh quyền kiểm soát theo phương thức được chấp nhận. Tín hiệu rủi ro cho biết cần điều tra, tăng kiểm tra hoặc giới hạn thao tác.

Ví dụ:

- Một authenticator đã gắn với tài khoản, được xác thực lại đúng cách, là bằng chứng trong nhánh được cấu hình.
- Một mã recovery được kiểm tra theo quy trình có thể là bằng chứng trong bộ phương thức được chấp nhận.
- IP quen, vị trí thường dùng và cookie thiết bị là ngữ cảnh.
- Biết tên, ngày sinh hoặc kể đúng lịch sử công việc không tự tạo quyền reset.

Điểm rủi ro thấp không bù cho việc thiếu bằng chứng tối thiểu. Hai email trong cùng hộp thư cũng không phải hai nguồn độc lập.

### 3.3. Cấp quyền hẹp, không cấp luôn phiên ứng dụng

Một quyền reset chỉ nên cho phép đặt mật khẩu của đúng tài khoản trong đúng luồng. Nó không được dùng để đọc dữ liệu cá nhân, tạo API key hoặc đổi phương tiện recovery.

Đặt mật khẩu thành công không làm người yêu cầu tự động đạt MFA. Với tài khoản bắt buộc yếu tố thứ hai, lần đăng nhập tiếp theo vẫn phải đáp ứng yêu cầu đó.

### 3.4. Không thay đổi tài khoản từ yêu cầu chưa xác minh

Việc một người nhập email vào biểu mẫu không đủ để:

- Khóa đăng nhập bình thường.
- Thu hồi mật khẩu hoặc session đang hoạt động.
- Đổi địa chỉ nhận mã.
- Đặt cờ bắt buộc đổi mật khẩu.
- Xóa yêu cầu recovery hợp lệ của chủ tài khoản.

Các hàng rào chống lạm dụng có thể hạn chế việc gửi yêu cầu mới. Hành động rộng hơn đối với tài khoản cần căn cứ và thẩm quyền phù hợp.

## 4. Ma trận quyết định reset

### 4.1. Dữ liệu đầu vào của quyết định

Chính sách tham khảo xét các nhóm thông tin:

| Nhóm | Ví dụ |
| --- | --- |
| Đối tượng | Tenant, tài khoản, nơi quản lý credential, vai trò đặc quyền |
| Trạng thái | Active, disabled, đang tranh chấp, đang bị hạn chế bởi xử lý sự cố |
| Bằng chứng | Phương thức, kết quả, thời điểm, thời hạn, ràng buộc với yêu cầu |
| Cấu hình an ninh | MFA bắt buộc, kênh recovery, phiên bản cấu hình |
| Nguy cơ | Thay đổi kênh gần đây, hành vi bất thường, lịch sử yêu cầu |
| Khả năng thực thi | Có thu hồi được session và cập nhật credential nhất quán không? |

Chỉ lấy những dữ liệu cần cho quyết định. Không thu thập thêm giấy tờ hoặc dữ liệu thiết bị chỉ vì biểu mẫu có thể chứa chúng.

### 4.2. Bảng xử lý minh họa

| Trường hợp | Kết quả chính sách | Điều kiện hoặc bước tiếp theo |
| --- | --- | --- |
| Tài khoản cục bộ thông thường, kênh recovery đã thiết lập, đủ bằng chứng theo profile | Cho phép quyền PASSWORD_RESET giới hạn | Thời hạn ngắn, đúng tài khoản, không có điều kiện chặn |
| Có authenticator khác đủ điều kiện | Chuyển nhánh xác thực lại để thay mật khẩu | Kiểm tra phương tiện và yêu cầu của nhánh binding |
| Có MFA nhưng chỉ mất mật khẩu | Giữ nguyên cấu hình MFA | Bằng chứng cho việc reset theo profile; không tự xóa yếu tố thứ hai |
| Mất cả mật khẩu và toàn bộ MFA | Chuyển account recovery | Cần bộ bằng chứng của luồng đó; không coi email đơn lẻ mặc nhiên đủ |
| Mật khẩu hoặc session có dấu hiệu bị chiếm | Nhánh xử lý sự cố | Xét lại kênh recovery, session, token và thay đổi trái phép |
| Tài khoản đặc quyền | Nhánh đặc quyền | Bằng chứng phù hợp và phê duyệt theo phân tách nhiệm vụ |
| Email recovery vừa thay trong hoàn cảnh đáng ngờ | Tạm dừng hoặc yêu cầu xác minh bổ sung | Không chỉ tin địa chỉ mới đang có trong DB |
| Tài khoản do IdP quản lý | Chuyển đến IdP tin cậy | Không tạo credential cục bộ ngoài chính sách |
| Tài khoản disabled do quản trị | Giữ trạng thái disabled | Reset mật khẩu không phải quyền khôi phục tư cách truy cập |
| Không còn phương thức được chấp nhận | Chưa cấp quyền reset | Hướng dẫn quy trình thay thế được phê chuẩn, nếu có |

“Cho phép” trong bảng là cho phép một thao tác giới hạn, không có nghĩa đã hoàn tất recovery.

Một profile chỉ dùng liên kết email cho tài khoản thông thường cần chấp nhận rõ nguy cơ hộp thư bị chiếm. Không áp dụng profile đó cho mọi loại tài khoản và không tuyên bố nó đáp ứng AAL2 chỉ vì token dài hoặc email đã được xác minh.

### 4.3. Mức đảm bảo và ngoại lệ

Nếu hệ thống có yêu cầu AAL hoặc IAL, cần ánh xạ từng phương thức recovery tới yêu cầu tương ứng. Hai nhân viên cùng duyệt không tự tạo thành hai yếu tố xác thực và không tự nâng mức đảm bảo.

Quy trình xác minh lại danh tính cũng không thể được giả định tồn tại cho mọi tài khoản. Cần có quan hệ phù hợp với danh tính đã thiết lập, phương pháp được chấp nhận và dữ liệu cần thiết.

NIST có yêu cầu recovery khác nhau theo IAL và AAL, đồng thời yêu cầu thông báo recovery. Một chính sách sản phẩm cần kiểm tra các điều kiện đó nếu tuyên bố áp dụng tiêu chuẩn, thay vì suy từ một nhãn “high risk”. [NIST SP 800-63B-4, Recovery Requirements by IAL/AAL](https://pages.nist.gov/800-63-4/sp800-63b/events/#recovery-requirements)

Ngoại lệ phải có phạm vi, người có thẩm quyền, hạn hiệu lực và lý do có thể audit. Yêu cầu khẩn cấp hoặc chức danh của người gọi không tự miễn bằng chứng.

## 5. Chính sách cho mật khẩu mới

### 5.1. Một hợp đồng dùng chung giữa đăng ký, đổi và reset

Đường reset phải gọi cùng chính sách kiểm tra mật khẩu đang được sử dụng cho việc thiết lập credential. Không duy trì một regex đơn giản hơn chỉ vì người dùng đang ở trang quên mật khẩu.

NIST SP 800-63B-4 yêu cầu tối thiểu 15 ký tự khi mật khẩu được dùng như cơ chế đơn yếu tố; mật khẩu chỉ dùng trong MFA có thể ngắn hơn nhưng tối thiểu 8 ký tự. Khi tính độ dài Unicode, mỗi code point được tính là một ký tự. NIST cũng khuyến nghị cho phép độ dài tối đa ít nhất 64 ký tự. [NIST SP 800-63B-4, Password Verifiers](https://pages.nist.gov/800-63-4/sp800-63b/authenticators/#passwordver)

Sản phẩm minh họa chọn tối thiểu 15 và tối đa 128 code point cho mọi mật khẩu cục bộ, đồng thời có giới hạn byte đủ lớn để xử lý an toàn. Đây là lựa chọn nội bộ; không phải quy định mọi hệ thống phải dùng đúng 128.

Các quy tắc của profile minh họa:

- Chấp nhận passphrase, Unicode và khoảng trắng theo hợp đồng nhập liệu.
- Không âm thầm cắt chuỗi, bỏ dấu hoặc chuyển chữ thường.
- Kiểm tra toàn bộ mật khẩu với blocklist đã được duyệt.
- Không yêu cầu một mẫu cố định gồm chữ hoa, chữ thường, số và ký tự đặc biệt.
- Cho phép trình quản lý mật khẩu, dán và tự điền.
- Hiển thị lý do từ chối mật khẩu mới mà không đưa bí mật vào thông báo hoặc log.

NIST giải thích ở bộ hướng dẫn triển khai Revision 4 rằng không áp đặt composition rules và không bắt đổi mật khẩu định kỳ tùy tiện. Thay đổi do có bằng chứng compromise là tình huống khác với lịch đổi mỗi 90 ngày. [NIST Digital Identity Guidelines, Implementation FAQ](https://pages.nist.gov/800-63-4-Implementation-Resources/faqs/index.html)

### 5.2. Chuẩn hóa và kiểm tra blocklist

Nếu hỗ trợ chuẩn hóa Unicode, lưu phiên bản xử lý và sử dụng cùng quy tắc khi tạo lẫn xác minh credential. Không mang quy tắc so sánh câu trả lời bảo mật sang mật khẩu: việc tự lowercase hoặc bỏ khoảng trắng có thể thay đổi bí mật mà người dùng định chọn.

Blocklist nên bao gồm các giá trị phổ biến, đã lộ hoặc đặc biệt dễ đoán trong ngữ cảnh ứng dụng. Không cấm một passphrase dài chỉ vì nó chứa một từ đơn trong từ điển.

Không gửi mật khẩu đầy đủ tới dịch vụ bên thứ ba để kiểm tra. Có thể dùng dữ liệu blocklist nội bộ hoặc một cơ chế tra cứu được đánh giá phù hợp về quyền riêng tư. Chính sách cần quy định trạng thái khi thành phần kiểm tra không sẵn sàng; ví dụ dùng bản dữ liệu cục bộ còn hiệu lực hoặc tạm hoãn commit.

### 5.3. Lưu mật khẩu và chính sách tái sử dụng

Mật khẩu mới cần được bảo vệ bằng thuật toán lưu mật khẩu đã được phê chuẩn với salt riêng; không lưu plaintext hoặc chỉ dùng hash nhanh. OWASP cung cấp hướng dẫn lựa chọn hàm băm như Argon2id và cách quản trị tham số. [OWASP Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)

Khi buộc thay do compromise, profile minh họa không cho chọn lại chính mật khẩu đang bị thay. Nếu có yêu cầu lịch sử mật khẩu, cần quy định rõ phạm vi và thời hạn giữ verifier cũ; không giữ vô hạn hoặc giữ plaintext để đối chiếu.

Độ dài, hash mạnh và blocklist không sửa được việc cấp quyền reset cho sai người. Chính sách mật khẩu và chính sách xác minh phải cùng được đáp ứng.

## 6. Chính sách tiếp nhận và gửi yêu cầu

### 6.1. Phản hồi không tiết lộ tài khoản

Một thông điệp tiếp nhận phù hợp có thể là:

> Nếu thông tin phù hợp với tài khoản đủ điều kiện, hướng dẫn đặt lại mật khẩu sẽ được gửi qua kênh đã đăng ký.

Không trả thông điệp khác nhau như “email không tồn tại”, “tài khoản này có MFA” hoặc “đây là quản trị viên”. Cũng cần xét status code, kích thước response và thời gian xử lý, không chỉ câu chữ.

OWASP khuyến nghị phản hồi nhất quán để chống liệt kê tài khoản, bảo vệ trước gửi yêu cầu quá mức và dùng token có tính ngẫu nhiên an toàn, dùng một lần, có hạn. [OWASP Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html)

Xử lý bất đồng bộ có thể giúp giảm khác biệt thời gian rõ rệt. Không nên hứa toàn bộ endpoint luôn có thời gian giống hệt nhau; cơ chế còn cần được thiết kế để tránh cạn hàng đợi và spam kênh gửi.

### 6.2. Kênh nhận và các thay đổi gần đây

Chỉ dùng kênh recovery đã được thiết lập theo chính sách. Không cho client nhập một email khác rồi dùng nó làm đích gửi chỉ vì email đó “dễ truy cập hơn”.

Khi kênh vừa thay đổi, policy engine cần xem căn cứ của thay đổi và các dấu hiệu compromise. Một khoảng chờ có thể tạo cơ hội phát hiện, nhưng không biến địa chỉ chưa đáng tin thành bằng chứng hợp lệ.

Không tự khôi phục địa chỉ cũ mà không đánh giá: nó có thể đã được thay vì người dùng mất quyền kiểm soát. Cũng không gửi dữ liệu nhạy cảm tới tất cả địa chỉ lịch sử.

### 6.3. Giới hạn gửi và chính sách resend

Thiết kế tham khảo dùng nhiều hạn mức: theo tài khoản, nguồn mạng, thiết bị, tenant và năng lực nhà cung cấp. Hạn mức phải được chia sẻ giữa các instance.

Ví dụ sản phẩm chọn tối đa hai reset link đang hoạt động cho một tài khoản và ba lần gửi trong một giờ. Các giá trị này chỉ minh họa; cần đánh giá khả năng gửi email, hành vi người dùng và nguy cơ tấn công.

Khi đạt giới hạn, có thể gộp hoặc trì hoãn yêu cầu mới. Không tự thu hồi link hợp lệ đang có chỉ vì một người chưa xác thực tiếp tục bấm quên mật khẩu. Nếu mỗi lần gửi vô danh đều vô hiệu hóa link trước, đối tượng có thể khiến chủ tài khoản không bao giờ hoàn tất.

Resend không được xóa ngân sách thử hoặc kéo dài vô hạn thời hạn tuyệt đối. Sau một lần đặt mật khẩu thành công, toàn bộ quyền reset liên quan đến phiên bản mật khẩu cũ phải hết hiệu lực.

CAPTCHA, nếu có, chỉ là lớp chống tự động hóa. Nó không chứng minh quyền sở hữu tài khoản và cần có phương án tiếp cận cho người dùng gặp khó khăn khi tương tác.

## 7. Chính sách cho token và reset session

### 7.1. Nội dung quyền được cấp

Một bản ghi quyền reset cần biểu diễn tối thiểu:

~~~text
request_id
tenant_id
account_id
purpose = PASSWORD_RESET
credential_version
recovery_config_version
evidence_reference
policy_version
issued_at
expires_at
status
token_digest
~~~

Credential version giúp quyền cũ hết hiệu lực khi mật khẩu đã thay. Recovery config version giúp phát hiện thay đổi kênh hoặc cấu hình an ninh có ảnh hưởng đến quyết định.

Không cho token PASSWORD_RESET được dùng ở endpoint đổi email, đăng ký passkey hoặc reset MFA. Bất kỳ thay đổi phạm vi nào cũng cần quyết định mới.

### 7.2. Các lựa chọn minh họa

Profile tham khảo chọn token opaque sinh từ 32 byte ngẫu nhiên mật mã, mã hóa Base64URL, có hiệu lực tuyệt đối 15 phút. DB lưu digest của token và trạng thái; token gốc chỉ xuất hiện trong luồng phân phối được bảo vệ.

Vì token này có entropy cao được máy sinh, digest phục vụ tra cứu và không cần dùng cùng cơ chế băm chậm như mật khẩu người dùng tự chọn. Không suy rộng lựa chọn đó sang OTP ngắn dễ đoán.

URL reset được tạo từ origin tin cậy theo cấu hình, không dựa trực tiếp vào Host, X-Forwarded-Host hoặc URL do client gửi. Token không được đưa vào log, analytics, nội dung hỗ trợ hoặc thông báo lỗi.

Nếu hàng đợi email cần giữ token hoặc liên kết để gửi, payload đó cũng là bí mật. Cần bảo vệ truy cập, mã hóa phù hợp, thời gian giữ ngắn và không lưu bản raw trong audit. Outbox chỉ lưu ID không tự đủ nếu worker không có cách phân phối bí mật an toàn; thiết kế cần nói rõ lựa chọn này.

### 7.3. GET không gây reset

GET từ liên kết nên mở trang giải thích và biểu mẫu thích hợp, không đổi mật khẩu, không đăng nhập và không tự hoàn thành recovery. Trình quét email có thể truy cập liên kết trước người dùng.

Một lựa chọn là dùng bước POST chủ động để trao đổi token thành **reset session** giới hạn. Bước đó kiểm tra token, các bằng chứng khác của profile và điều kiện hiện tại. Việc tiêu thụ token và tạo session phải nguyên tử.

Reset session chỉ có quyền PASSWORD_RESET, dùng cookie riêng được bảo vệ và có cơ chế chống CSRF thích hợp. Ví dụ sản phẩm giới hạn session trong 10 phút nhưng không vượt thời điểm hết hạn tuyệt đối của token ban đầu:

~~~text
reset_session_expires_at =
    min(token_expires_at, exchange_time + 10 minutes)
~~~

Như vậy việc trao đổi không tạo thêm 10 phút sau khi quyền ban đầu đã hết hạn. Nếu chọn chính sách khác, cần nêu rõ thời hạn của từng loại quyền và lý do, tránh kéo dài ngầm.

Trang reset dùng HTTPS, hạn chế cache, đặt chính sách referrer phù hợp và không tải tracker bên thứ ba. Đối tượng có token vẫn cần được kiểm tra theo phạm vi và trạng thái; URL dài không tự chống được rò rỉ.

### 7.4. Token hợp lệ chưa phải lúc nào cũng đủ

Một token có thể đúng digest nhưng quyền reset vẫn không được sử dụng nếu:

- Đã dùng, hết hạn hoặc bị thu hồi.
- Không khớp tài khoản, tenant hoặc mục đích.
- Mật khẩu đã đổi kể từ khi token được cấp.
- Cấu hình recovery thay đổi và chưa được đánh giá lại.
- Bằng chứng bắt buộc của profile còn thiếu hoặc đã hết hạn.
- Tài khoản chuyển sang trạng thái bị chặn.
- Chính sách hiện hành có lệnh chặn mới.

Kiểm tra thời hạn bằng đồng hồ phía máy chủ. Quy định rõ thời điểm bằng expires_at được coi là hết hạn; profile minh họa dùng điều kiện now < expires_at.

Không tăng TTL chỉ vì hệ thống gửi email chậm hoặc người dùng mở lại trang. Có thể cấp quyền mới qua quy trình được kiểm soát thay vì sửa lịch sử của quyền cũ.

## 8. Vòng đời và thời điểm áp dụng thay đổi

~~~mermaid
stateDiagram-v2
    [*] --> RECEIVED
    RECEIVED --> PROOF_PENDING: Đủ điều kiện gửi hoặc xác minh
    PROOF_PENDING --> AUTHORIZED: Bằng chứng đạt chính sách
    AUTHORIZED --> RESET_SESSION: Cấp quyền biểu mẫu giới hạn
    RESET_SESSION --> COMMITTING: Mật khẩu mới đạt và điều kiện còn hiệu lực
    COMMITTING --> COMPLETED: Credential và hàng rào bắt buộc đã áp dụng
    COMMITTING --> RECOVERY_REQUIRED: Cần tiếp tục xử lý an toàn
    RECOVERY_REQUIRED --> COMMITTING: Tiếp tục operation đã ghi
    PROOF_PENDING --> EXPIRED
    AUTHORIZED --> EXPIRED
    RESET_SESSION --> EXPIRED
    AUTHORIZED --> STALE: Cấu hình thay đổi
    RESET_SESSION --> STALE: Cấu hình thay đổi
~~~

Sơ đồ là mô hình rút gọn. Trước COMMITTING, yêu cầu có thể bị từ chối, hủy hoặc thu hồi theo thẩm quyền. Các trạng thái AUTHORIZED và RESET_SESSION có thể được tạo trong cùng transaction khi trao đổi token.

Không tiêu thụ quyền reset chỉ vì người dùng nhập mật khẩu mới chưa đạt policy. Có thể cho sửa lại trong thời hạn và hạn mức phù hợp. Ngược lại, không giữ một quyền đã dùng sau khi commit thành công.

### 8.1. Điều kiện phải được kiểm tra lại ở commit

Giữa lúc mở trang và lúc gửi mật khẩu mới, có thể đã xảy ra đổi email recovery, một lần reset khác hoặc cảnh báo gian lận. Vì vậy, kiểm tra lúc mở form không đủ.

Một commit hợp lệ cần bảo đảm đồng thời:

1. Reset session còn hoạt động và đúng phạm vi.
2. Bằng chứng, snapshot và chính sách hiện hành vẫn cho phép.
3. Mật khẩu mới đã qua policy đang có hiệu lực.
4. Bản ghi credential chưa thay ngoài dự kiến.
5. Quyền reset được tiêu thụ cùng thay đổi mật khẩu.
6. Phiên bản thu hồi session và sự kiện bắt buộc được ghi bền vững.

Mật khẩu có thể được kiểm tra và tạo hash ngoài transaction dài sau khi đã có quyền reset hợp lệ và ngân sách tài nguyên. Khi commit, vẫn kiểm tra lại phiên bản policy và trạng thái tài khoản. Không giữ khóa DB trong lúc chờ một dịch vụ mạng kiểm tra blocklist.

Nếu DB rollback, không để trạng thái token đã bị tiêu thụ vĩnh viễn trong một kho khác mà không có tiến trình tiếp tục an toàn. Cũng không báo thành công khi mật khẩu chưa được lưu.

### 8.2. Hai yêu cầu hoàn tất đồng thời

Giả sử hai reset session đều được cấp từ credential_version = 11.

- Yêu cầu A đổi mật khẩu và tăng version lên 12.
- Yêu cầu B chỉ được commit nếu điều kiện version = 11 còn đúng.
- Khi điều kiện không còn đúng, B bị từ chối là stale; không ghi đè mật khẩu của A.
- Những token khác cùng version 11 không còn dùng được.

Có thể triển khai bằng khóa trên tài khoản, cập nhật có điều kiện hoặc cơ chế tương đương. Việc kiểm tra token ở một lệnh đọc rồi cập nhật nhiều bản ghi không có ràng buộc nguyên tử sẽ không tạo tính dùng một lần.

Idempotency chỉ nên giúp người gọi hợp lệ đọc lại kết quả của cùng operation hoặc tiếp tục bước kỹ thuật an toàn. Cùng key với payload khác phải bị từ chối; chỉ biết idempotency key không được nhận reset session.

## 9. Chính sách session và quyền sau reset

### 9.1. Profile tham khảo chọn thu hồi gì?

| Thành phần | Sau reset mật khẩu thông thường | Khi nghi ngờ tài khoản bị chiếm |
| --- | --- | --- |
| Mật khẩu cũ | Mất hiệu lực | Mất hiệu lực hoặc bị đình chỉ sớm theo ứng cứu |
| Reset token và reset session cũ | Hết hiệu lực theo version hoặc trạng thái | Thu hồi cả quyền recovery liên quan trong phạm vi sự cố |
| Session ứng dụng | Profile minh họa thu hồi toàn bộ | Thu hồi toàn bộ và giữ hạn chế nếu chưa kết thúc điều tra |
| Refresh token | Thu hồi các family liên quan | Xét toàn bộ grant hoặc family trong phạm vi sự cố |
| Remember-MFA và trusted device | Vô hiệu hóa độ tin cậy theo profile | Rà soát và thu hồi theo nguy cơ thực tế |
| TOTP, passkey, khóa bảo mật | Giữ nguyên nếu không thuộc phạm vi cần xử lý | Kiểm kê và thu hồi phương tiện bị chiếm theo quy trình riêng |
| API key hoặc OAuth grant riêng | Theo chính sách credential tương ứng | Đánh giá, thu hồi nếu có căn cứ; không giả định tự hết hiệu lực |

Thu hồi toàn bộ session ở nhánh thông thường là lựa chọn của sản phẩm minh họa. Tổ chức có thể dùng profile khác, nhưng phải nêu rõ lựa chọn và giải thích nguy cơ của việc giữ phiên còn sống.

Không tự động đăng nhập sau reset trong profile này. Người dùng đi qua luồng đăng nhập bình thường và hoàn thành MFA nếu tài khoản yêu cầu.

### 9.2. Thu hồi phải có hiệu lực tại nơi kiểm tra truy cập

Xóa cookie chỉ tác động đến trình duyệt hiện tại. OWASP nhấn mạnh rằng bản sao session ID đã bị đánh cắp không mất hiệu lực chỉ vì cookie bị xóa ở phía client. [OWASP Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html#expire-and-max-age-attributes)

Một cơ chế là tăng session epoch của tài khoản và kiểm tra epoch khi cấp, refresh và sử dụng session. Với JWT chỉ kiểm chữ ký và hạn, token cũ có thể vẫn được chấp nhận đến khi hết hạn nếu không có cơ chế thu hồi khác.

Nếu hệ thống có nhiều API, cần xác định nơi nào kiểm tra epoch, cache tối đa bao lâu và tác vụ nào phải chặn ngay. Đẩy một sự kiện thu hồi không chứng minh mọi API đã áp dụng nó.

Khi phải chờ xác nhận từ nhiều dịch vụ, giữ COMMITTING và hàng rào recovery cho các quyền cần chặn. Nếu kiến trúc dùng cache mà không bảo đảm chặn ngay, cần giai đoạn dựng hàng rào và đợi xác nhận phù hợp trước khi coi reset hoàn tất.

Session ở IdP và ở ứng dụng có thể có vòng đời riêng. Chính sách cần xét việc người dùng có thể quay lại ứng dụng qua một phiên IdP còn sống hay không.

## 10. Thông báo và phản đối thay đổi

Thông báo cần giúp chủ tài khoản phát hiện một hành động ngoài ý muốn, đồng thời không phát tán quyền reset.

Profile minh họa có các loại thông báo:

- Hướng dẫn thực hiện cho một yêu cầu đủ điều kiện phân phối.
- Cảnh báo khi nhánh rủi ro cao được xác minh hoặc cần chờ.
- Xác nhận mật khẩu đã đổi, kèm thời điểm và cách báo không phải chủ tài khoản thực hiện.
- Hướng dẫn xử lý khi operation đang chờ hoặc cần hỗ trợ.

Không gửi mật khẩu mới, hash, token cũ hoặc toàn bộ dữ liệu định danh vào thư xác nhận. Thông báo hoàn tất không chứa một liên kết có thể đảo ngược mật khẩu hoặc đăng nhập bằng một lần bấm.

Địa chỉ nhận cảnh báo phải dựa trên kênh được đánh giá phù hợp. Nếu chỉ gửi vào hộp thư nghi đã bị chiếm, không thể trông đợi cảnh báo tự bảo vệ chủ tài khoản.

Một liên kết báo “tôi không thực hiện” có thể tạo cảnh báo hoặc tạm dừng đúng luồng. Nó không được trở thành quyền đổi email hoặc khóa vô thời hạn toàn bộ tài khoản mà thiếu kiểm tra bổ sung.

Không phản đối trong thời gian chờ không có nghĩa người yêu cầu đã được xác minh. Thời gian chờ là một biện pháp bổ sung, không thay bằng chứng.

Nếu hệ thống thông báo lỗi, sự kiện cần được lưu để thử lại và có cảnh báo vận hành. Với profile yêu cầu thông báo trước khi kết thúc thời gian chờ, phải quy định điều kiện bắt đầu đếm chờ và cách xử lý khi không gửi được.

## 11. Biểu diễn chính sách thành hợp đồng có phiên bản

### 11.1. Tài liệu chính sách cần có gì?

Một phiên bản chính sách nên mô tả:

| Thành phần | Nội dung |
| --- | --- |
| Chủ sở hữu | Nhóm chịu trách nhiệm nội dung và nhóm vận hành |
| Phạm vi | Loại tài khoản, tenant, credential và luồng áp dụng |
| Điều kiện bằng chứng | Phương pháp được chấp nhận, độ mới, tính độc lập và yêu cầu ràng buộc |
| Điều kiện chặn | Disabled, tranh chấp, compromise chưa xử lý hoặc thiếu khả năng thực thi |
| Giới hạn quyền | Mục đích, đối tượng, thời hạn và số lần dùng |
| Mật khẩu mới | Phiên bản kiểm tra, blocklist, lưu trữ và tái sử dụng |
| Nghĩa vụ sau thay đổi | Thu hồi token, session, thông báo và audit |
| Ngoại lệ | Người có quyền, giới hạn, thời hạn và cách xem xét |
| Sự cố kỹ thuật | Giữ trạng thái nào, có được chuyển phương thức không |
| Hiệu lực | Ngày áp dụng, tương thích yêu cầu đang chạy và cách thay phiên bản |

Một quyết định allow phải mang theo **obligations**, tức các hành động bắt buộc để hoàn tất. Ví dụ “được reset” nhưng không có dịch vụ nào biết phải thu hồi refresh token là một hợp đồng chưa đầy đủ.

### 11.2. Cấu hình minh họa

Đoạn YAML sau chỉ minh họa hình thức biểu diễn; không phải cấu hình triển khai của module:

~~~yaml
policyId: local-password-reset
version: 4

scope:
  credentialOwner: LOCAL
  requireExistingPasswordCredential: true

evidencePolicyRef: approved-reset-evidence-v4
passwordPolicyRef: local-password-policy-v6

grant:
  purpose: PASSWORD_RESET
  opaqueTokenRandomBytes: 32
  absoluteTtlSeconds: 900
  maximumActiveTokensPerAccount: 2

resetSession:
  ttlSeconds: 600
  boundedByOriginalGrantExpiry: true
  applicationAccess: false

revalidation:
  requireCurrentCredentialVersion: true
  requireCurrentRecoveryConfigVersion: true
  applyCurrentBlockingRules: true

completion:
  invalidateSiblingResetRights: true
  revokeApplicationSessions: ALL
  revokeRefreshTokens: RELATED_FAMILIES
  automaticallySignIn: false
  preserveMfaRequirement: true
  notifyOwner: true

failure:
  missingRequiredEvidence: REQUIRE_MORE_EVIDENCE
  unresolvedPolicyReference: BLOCK
  securityContextChanged: REEVALUATE
  requiredRevocationPending: KEEP_RECOVERY_FENCE
~~~

Hai policy reference phải trỏ tới hợp đồng đã được định nghĩa và phê chuẩn, bao gồm các tiêu chí ở phần 4 và 5. Một tên có chữ approved không tự bảo đảm bất cứ điều gì. Dịch vụ cần từ chối kích hoạt cấu hình nếu tham chiếu không tồn tại hoặc không tương thích.

Các giới hạn chống gửi lặp theo mạng, tenant và nhà cung cấp được quản lý ở lớp chống lạm dụng, nhưng không được làm mất giới hạn theo tài khoản. Nếu có nhiều tầng cấu hình, cần quy tắc ưu tiên rõ ràng để override không âm thầm bỏ một cổng bắt buộc.

### 11.3. Thứ tự quyết định

Một thứ tự tham khảo:

1. Xác định nơi sở hữu credential và luồng đúng.
2. Áp dụng điều kiện chặn hiện hành.
3. Kiểm tra snapshot, phiên bản và tính hợp lệ của bằng chứng.
4. Kiểm tra bằng chứng có đủ cho profile mục tiêu.
5. Áp dụng điều kiện tăng kiểm tra hoặc phê duyệt.
6. Xác định thời hạn và các nghĩa vụ khi hoàn tất.
7. Trả quyết định có phạm vi và reason code.

Các điều kiện chặn không bị ghi đè bởi một điểm rủi ro thuận lợi. Chỉ người có quyền sửa chính sách mới thay hợp đồng đó, và sự thay đổi cần để lại dấu vết.

## 12. Mã giả Java cho quyết định chính sách

Ví dụ dưới đây tập trung vào quyết định, không phải controller hoặc thư viện xác minh:

~~~java
ResetDecision evaluateReset(ResetContext context) {
    AccountSnapshot account = context.account();
    ResetPolicy policy = policies.currentFor(account.tenantId());

    if (account.credentialOwner() != LOCAL) {
        return routeToTrustedCredentialOwner(account);
    }

    if (!account.hasPasswordCredential()) {
        return deny(NO_LOCAL_PASSWORD_CREDENTIAL);
    }

    if (!account.isEligibleForAccess()) {
        return deny(ACCOUNT_NOT_ELIGIBLE);
    }

    if (incidents.requiresControlledRecovery(account)) {
        return routeToIncidentRecovery(INCIDENT_REVIEW_REQUIRED);
    }

    if (!context.matchesCurrentSecurityVersions(account)) {
        return reevaluate(SECURITY_CONTEXT_CHANGED);
    }

    EvidenceDecision evidence = evidencePolicies.evaluate(
        policy.evidencePolicyRef(), context, clock.instant());

    if (!evidence.isSufficientAndFresh()) {
        return requireMoreEvidence(evidence.missingRequirements());
    }

    RiskDecision risk = riskPolicies.evaluate(context);
    if (risk.hasBlockingCondition()) {
        return review(RISK_REVIEW_REQUIRED);
    }

    if (!approvals.meetsRequiredQuorum(context, policy, risk)) {
        return review(APPROVAL_PENDING);
    }

    Instant deadline = deadlines.minimumOf(
        policy.maximumGrantExpiry(clock.instant()),
        evidence.expiresAt(),
        context.requestAbsoluteExpiry());

    if (!clock.instant().isBefore(deadline)) {
        return deny(RESET_WINDOW_EXPIRED);
    }

    return allowPasswordReset(
        account.tenantId(), account.accountId(),
        account.credentialVersion(), account.recoveryConfigVersion(),
        policy.version(), deadline, policy.completionObligations());
}
~~~

Các hàm trên có hợp đồng cụ thể:

- Nơi sở hữu credential và URL chuyển hướng đến từ cấu hình tin cậy.
- Bằng chứng phải được xác minh phía máy chủ và gắn với đúng request.
- Một trạng thái UNKNOWN của rủi ro không được tự hiểu là rủi ro thấp; policy cần định nghĩa hướng xử lý.
- Quorum xét đúng người, đúng phạm vi và quyết định chưa hết hạn.
- Deadline không vượt hạn bằng chứng hoặc hạn tuyệt đối của yêu cầu.

Quyết định được lưu để giải thích lịch sử, nhưng đến commit vẫn phải kiểm tra các điều kiện hiện hành. Một bản policy cũ không được dùng để né lệnh chặn khẩn cấp mới.

Không nhận một boolean từ client như verified=true hoặc một tên role do request tự khai rồi cấp quyền reset. Các giá trị đầu vào của policy cần được xây dựng từ nguồn có thẩm quyền.

## 13. Khi các thành phần lỗi hoặc thay đổi đồng thời

| Sự cố | Trạng thái hoặc hành vi phù hợp trong thiết kế tham khảo |
| --- | --- |
| Không đọc được policy bắt buộc | Chưa cấp quyền; cảnh báo cấu hình |
| Xác minh bằng chứng timeout | Chưa đủ bằng chứng; không chuyển thành allow |
| Gửi thư chậm | Giữ thời hạn quyền rõ ràng; không tự kéo dài vô hạn |
| Blocklist tạm lỗi | Dùng phương án đã phê chuẩn hoặc hoãn commit |
| Tạo password hash thất bại | Chưa thay mật khẩu; người dùng có thể thử lại trong hạn |
| Commit DB rollback | Giữ tính nhất quán của credential và quyền reset |
| Thay mật khẩu xong nhưng thu hồi session chưa được xác nhận | COMMITTING hoặc RECOVERY_REQUIRED; giữ hàng rào bắt buộc |
| Gửi thông báo kết quả lỗi | Giữ sự kiện bền vững và thử lại theo chính sách |
| Client mất response sau commit | Đọc lại trạng thái operation bằng ngữ cảnh hợp lệ |
| Phát hiện gian lận khi đang hoàn tất | Chuyển xử lý sự cố; không tự mở quyền bình thường |

Nếu kho credential, session store và hệ thống gửi thông báo khác nhau, có thể dùng operation ID cùng transactional outbox để tiếp tục công việc. Consumer cần xử lý lặp an toàn.

Outbox giải quyết việc không mất ý định gửi sự kiện khi tiến trình chết sau commit. Nó không làm các hệ thống từ xa trở thành một transaction và không tự đảm bảo thu hồi đã có hiệu lực.

Không rollback bằng cách bật lại mật khẩu được xác định đã bị lộ. Một lỗi thu hồi session cần hàng rào và tiến trình khắc phục phù hợp, thay vì trả credential nguy hiểm về trạng thái dùng được.

Thông điệp cho người dùng cần phân biệt “mật khẩu đã thay, đang hoàn tất kiểm soát truy cập” với “chưa thay mật khẩu”. Không báo hoàn tất toàn bộ khi vẫn còn nghĩa vụ bắt buộc chưa đáp ứng.

## 14. Vai trò của hỗ trợ, audit và giám sát

### 14.1. Nhân viên hỗ trợ làm gì?

Nhân viên hỗ trợ có thể hướng dẫn, tạo hồ sơ và thực hiện bước xác minh đã được giao. Họ không cần biết mật khẩu mới, không yêu cầu người dùng đọc reset token và không tự thay địa chỉ nhận mã để xử lý nhanh hơn.

Nhánh đặc quyền có thể yêu cầu hai người độc lập. Hệ thống phải nhận diện cùng một nhân sự dùng hai tài khoản, kiểm tra tenant và quyền hiện hành, đồng thời yêu cầu xác thực nội bộ đủ mới.

Không dùng một nút bỏ qua mọi kiểm tra dành cho tất cả nhân viên. Quy trình khẩn cấp cần quyền có thời hạn và phạm vi, với điều kiện được quản trị rõ ràng.

### 14.2. Những gì nên được ghi nhận

Audit nên có request ID, operation ID, tenant, account ID nội bộ, policy version, loại bằng chứng, thời điểm, actor, reason code và các nghĩa vụ đã hoàn tất.

Không ghi mật khẩu, token, URL chứa token hoặc hồ sơ xác minh đầy đủ vào log thông thường. Tham chiếu bằng chứng nên trỏ tới kho được phân quyền riêng.

Các reason code minh họa gồm:

~~~text
NO_LOCAL_PASSWORD_CREDENTIAL
ACCOUNT_NOT_ELIGIBLE
EVIDENCE_REQUIRED
EVIDENCE_EXPIRED
APPROVAL_PENDING
SECURITY_CONTEXT_CHANGED
GRANT_EXPIRED
GRANT_ALREADY_USED
PASSWORD_POLICY_REJECTED
SESSION_REVOCATION_PENDING
~~~

Reason code nội bộ có thể chi tiết hơn thông báo trước xác thực. API không cần tiết lộ tài khoản bị disabled hoặc có quyền quản trị chỉ để giúp vận hành đọc log.

### 14.3. Đo hiệu quả của policy

Nên xem đồng thời thời gian hoàn tất, tỷ lệ người dùng bị kẹt, số lần gửi bị giới hạn, độ trễ thu hồi session, số phản đối và sự cố chiếm đoạt sau reset.

Tỷ lệ hoàn tất cao không tự chứng minh an toàn. Tỷ lệ từ chối cao cũng không tự chứng minh kiểm soát tốt; có thể policy đang chặn người hợp lệ hoặc kênh gửi bị lỗi.

Khi sửa policy, lưu phiên bản và quy tắc áp dụng cho yêu cầu đang chạy. Những yêu cầu bị ảnh hưởng bởi điều kiện an ninh mới cần được đánh giá lại; không tự kéo dài TTL để giữ chỉ số hoàn tất.

## 15. Ví dụ xuyên suốt và các nhánh quyết định

Người dùng An quên mật khẩu của tài khoản cục bộ có MFA.

1. An gửi yêu cầu; giao diện trả thông điệp tiếp nhận chung và hệ thống áp dụng giới hạn gửi.
2. Máy chủ xác định credential thuộc ứng dụng, chọn đúng profile và ghi snapshot cấu hình.
3. An hoàn thành phương thức được profile chấp nhận; nếu không đạt bằng chứng, hệ thống chưa cấp quyền reset.
4. Reset session chỉ cho phép chọn mật khẩu mới, không đọc dữ liệu hoặc thay MFA.
5. An nhập một passphrase đáp ứng policy. Máy chủ kiểm tra blocklist và tạo verifier phù hợp.
6. Khi commit, máy chủ kiểm tra lại hạn, bằng chứng, credential version và recovery config version.
7. Mật khẩu được thay cùng việc tiêu thụ quyền reset, tăng phiên bản và ghi nghĩa vụ thu hồi.
8. Sau khi các hàng rào bắt buộc hiệu lực, hệ thống báo kết quả và hướng dẫn đăng nhập lại.
9. An vẫn phải thực hiện MFA theo cấu hình hiện có.

Các nhánh khác:

- Nếu An không còn MFA, luồng chuyển sang account recovery; việc biết email không tự miễn điều kiện còn thiếu.
- Nếu cấu hình recovery thay đổi lúc An đang mở form, reset session trở thành stale và cần đánh giá lại.
- Nếu đây là tài khoản SSO, ứng dụng đưa An tới cơ quan quản lý credential đã cấu hình.
- Nếu tài khoản bị chiếm, nhóm xử lý rà soát session, phương tiện và thay đổi trái phép; chỉ đổi mật khẩu chưa kết thúc vụ việc.
- Nếu một reset khác hoàn tất trước, yêu cầu hiện tại không được ghi đè lên mật khẩu mới bằng quyền của version cũ.

Một policy đầy đủ phải nối được **đủ bằng chứng → cấp quyền giới hạn → mật khẩu đạt yêu cầu → commit nhất quán → thu hồi quyền cũ → đăng nhập lại đúng mức đảm bảo**. Mỗi mắt xích cần điều kiện và thành phần chịu trách nhiệm rõ ràng.
