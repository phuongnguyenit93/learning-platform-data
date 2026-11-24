# Error message usability

> **Chương:** Trải nghiệm người dùng  
> **Module:** SECURITY_AUTHENTICATION_FUNDAMENTALS  
> **Trọng tâm:** Thiết kế thông báo lỗi xác thực dễ hiểu, có hướng dẫn hành động phù hợp và bảo vệ thông tin tài khoản, credential cũng như trạng thái bảo mật.

## 1. Error message usability là gì?

**Error message usability** là khả năng giúp người dùng hiểu điều gì vừa xảy ra, biết bước tiếp theo và tiếp tục công việc mà không phải đoán hoặc lặp lại thao tác vô ích. Trong luồng xác thực, thông báo lỗi còn phải bảo vệ thông tin nhạy cảm: không tiết lộ tài khoản có tồn tại, factor nào đã đăng ký, token nào được chấp nhận hoặc chi tiết nội bộ của hệ thống.

Ví dụ, khi người dùng nhập sai password, thông báo nên nói rõ thông tin đăng nhập chưa được chấp nhận và gợi ý kiểm tra hoặc dùng quy trình khôi phục chính thức. Không nên cho biết email có tồn tại hay không. Khi một người đã xác minh quyền kiểm soát tài khoản và đang đăng ký passkey, hệ thống có thể hiển thị hướng dẫn cụ thể hơn về bước tiếp theo vì lúc đó ngữ cảnh và mức tin cậy đã khác.

Một thông báo như “Authentication error 401” có thể đúng với lập trình viên nhưng không giúp người dùng giải quyết vấn đề. Ngược lại, một thông báo quá chi tiết có thể vô tình tiết lộ trạng thái tài khoản hoặc tạo cơ hội cho attacker. Thiết kế tốt phải cân bằng tính rõ ràng, khả năng hành động, bảo mật, khả năng tiếp cận và tính nhất quán.

### Kết quả học tập

Sau bài này, người học có thể:

- Viết thông báo lỗi ngắn gọn, cụ thể và hướng người dùng tới hành động tiếp theo.
- Phân biệt thông báo ở trạng thái chưa xác thực và sau khi đã xác minh người dùng.
- Giảm account enumeration qua nội dung, status, redirect và timing.
- Thiết kế thông báo cho password, MFA, passkey, token, session, federation và recovery.
- Giải thích lỗi dependency mà không quy nhầm thành lỗi credential.
- Xây dựng nội dung đa ngôn ngữ, dễ đọc và hỗ trợ công nghệ trợ năng.
- Kiểm thử usability, privacy và security của thông báo lỗi.

## 2. Một thông báo lỗi tốt cần làm gì?

Một thông báo hữu ích thường trả lời được ba câu hỏi:

1. **Điều gì vừa xảy ra?** Mô tả trạng thái bằng từ ngữ người dùng hiểu.
2. **Người dùng có thể làm gì tiếp theo?** Đưa ra hành động khả thi và an toàn.
3. **Nếu vẫn không được thì tìm trợ giúp ở đâu?** Cung cấp đường hỗ trợ chính thức hoặc mã tham chiếu không nhạy cảm.

Ví dụ:

| Thông báo yếu | Thông báo hữu ích hơn |
|---|---|
| Error 401 | Thông tin đăng nhập chưa được chấp nhận. Hãy kiểm tra và thử lại. |
| Invalid input | Hãy nhập địa chỉ email theo định dạng hợp lệ. |
| Session error | Phiên đăng nhập đã hết hạn. Hãy đăng nhập lại để tiếp tục. |
| MFA failed | Chưa thể xác minh mã. Hãy kiểm tra mã mới nhất hoặc thử phương thức khác đã thiết lập. |
| Internal server error | Dịch vụ đăng nhập tạm thời không khả dụng. Hãy thử lại sau ít phút. |

Thông báo không cần giải thích toàn bộ cơ chế mật mã hoặc cấu trúc backend. Nó cần cho người dùng biết trạng thái và hành động phù hợp.

### Nguyên tắc viết

- Dùng câu ngắn, từ phổ thông và giọng điệu bình tĩnh.
- Nêu hành động, không đổ lỗi cho người dùng.
- Tránh mã lỗi kỹ thuật ở phần nội dung chính.
- Không dùng câu mơ hồ như “Có lỗi xảy ra” nếu có thể hướng dẫn rõ hơn.
- Không hứa chắc điều hệ thống chưa xác minh.
- Không đưa nhiều hướng dẫn mâu thuẫn trong cùng một thông báo.
- Giữ nhất quán tên gọi cho password, passkey, mã xác minh, phiên và tài khoản.

## 3. Bảo mật phụ thuộc vào trạng thái xác thực

Không phải lúc nào cũng có thể hiển thị cùng một mức chi tiết. Nội dung phù hợp phụ thuộc vào điều hệ thống đã biết và bằng chứng người dùng đã cung cấp.

### Trước khi xác minh tài khoản

Ở login, forgot password hoặc public registration, người gửi request có thể là attacker. Không tiết lộ:

- Tài khoản hoặc email có tồn tại hay không.
- Tài khoản đang active, disabled hay locked.
- Người dùng đã đăng ký TOTP, push, SMS, passkey hay recovery email nào.
- Tên, số lượng hoặc định danh factor của một account.
- Lý do nội bộ khiến một account cụ thể bị hạn chế.

Dùng thông báo công khai nhất quán cho các trường hợp có thể bị dùng để enumeration. Ví dụ, yêu cầu reset password có thể trả lời: “Nếu thông tin này gắn với tài khoản, hướng dẫn khôi phục sẽ được gửi tới kênh đã đăng ký.”

### Sau khi xác minh quyền kiểm soát

Khi người dùng đã hoàn tất một proof phù hợp, ứng dụng có thể đưa ra hướng dẫn cụ thể hơn, chẳng hạn:

- “Thiết bị bảo mật này chưa hoàn tất đăng ký. Hãy bắt đầu lại quy trình thêm passkey.”
- “Mã khôi phục này đã được sử dụng. Hãy tạo bộ mã mới sau khi đăng nhập.”
- “Bạn cần xác minh lại trước khi thay đổi email khôi phục.”

Mức chi tiết phải phù hợp với assurance đã đạt. Chỉ xác minh một email hoặc một yếu tố yếu không nhất thiết đủ để tiết lộ toàn bộ cấu hình bảo mật.

## 4. Tránh account enumeration mà vẫn hữu ích

**Account enumeration** là việc dùng phản hồi của ứng dụng để suy ra tài khoản nào tồn tại, đang hoạt động hoặc có phương thức xác thực nào. Attacker có thể dùng thông tin đó cho phishing, credential stuffing, social engineering và recovery abuse.

### Các điểm cần nhất quán

- Nội dung phản hồi khi username không tồn tại và password sai.
- Status code và cấu trúc response của API công khai.
- Redirect sau login hoặc recovery.
- Cookie được tạo hoặc xóa.
- Thời gian xử lý có thể quan sát.
- Phản hồi của endpoint gửi OTP hoặc reset link.
- Thông báo khi đăng ký email đã được dùng.

Không chỉ thay câu chữ nhưng để status code, response size hoặc redirect khác nhau rõ rệt. Các khác biệt này vẫn có thể tiết lộ thông tin.

### Ví dụ login

Thông báo công khai:

> Thông tin đăng nhập không hợp lệ. Hãy kiểm tra và thử lại hoặc dùng quy trình khôi phục chính thức.

Backend vẫn có thể ghi reason code riêng như account_not_found hoặc password_mismatch trong hệ thống log được bảo vệ. Không đưa các reason code nhạy cảm đó vào response cho unauthenticated caller.

### Ví dụ forgot password

Thông báo công khai:

> Nếu thông tin bạn nhập gắn với tài khoản, hướng dẫn khôi phục sẽ được gửi tới kênh đã đăng ký.

Không hiển thị “Email chưa được đăng ký” hoặc “Đã gửi đến m***@example.com” trước khi người dùng chứng minh quyền kiểm soát account. Khi đã xác minh, có thể hiển thị kênh che bớt thông tin theo policy.

## 5. Thông báo lỗi password

Password có nhiều trường hợp lỗi khác nhau nhưng không phải trường hợp nào cũng nên phân biệt công khai.

### Password không đúng

Gợi ý:

> Thông tin đăng nhập không hợp lệ. Hãy kiểm tra và thử lại.

Có thể kèm liên kết “Quên mật khẩu?” nếu đây là đường recovery chính thức. Không nói email có tồn tại, password sai hay account bị khóa trong phản hồi public.

### Input không hợp lệ

Nếu lỗi chỉ liên quan định dạng trước khi xác định account, có thể hướng dẫn cụ thể:

- “Hãy nhập địa chỉ email theo định dạng hợp lệ.”
- “Trường mật khẩu không được để trống.”
- “Giá trị vượt quá độ dài tối đa được hỗ trợ.”

Không cắt ngắn password âm thầm. Nếu hệ thống có giới hạn đầu vào, thông báo rõ giới hạn mà không phản ánh password đã nhập.

### Password mới không đạt policy

Trong một flow đã xác minh người dùng, có thể nói:

> Mật khẩu mới chưa đáp ứng yêu cầu. Hãy dùng mật khẩu dài hơn và tránh mật khẩu phổ biến hoặc đã bị lộ.

Hiển thị yêu cầu trước khi submit nếu có thể. Không bắt người dùng thử đi thử lại mà không biết tiêu chí. Hỗ trợ password manager, paste và autofill.

### Password bị từ chối do rate limit

Thông báo:

> Bạn đã thử nhiều lần trong thời gian ngắn. Hãy đợi một lúc rồi thử lại hoặc dùng kênh hỗ trợ chính thức.

Không tiết lộ số lần thử còn lại, ngưỡng khóa chính xác hoặc account state cho unauthenticated caller. Không khóa vĩnh viễn chỉ dựa vào số lần nhập sai vì attacker có thể gây denial of service cho người dùng.

## 6. Thông báo lỗi MFA và mã xác minh

MFA có thể gồm TOTP, push, security key, passkey, certificate hoặc yếu tố do tổ chức quản lý. Mỗi loại có hành động khắc phục khác nhau.

### TOTP sai hoặc hết hạn

Gợi ý:

> Chưa thể xác minh mã. Hãy nhập mã mới nhất từ ứng dụng xác thực và kiểm tra thời gian trên thiết bị đang đặt tự động.

Không cho biết mã sai ở chữ số nào hoặc tiết lộ cửa sổ thời gian nội bộ. Nếu có khả năng clock skew, hướng dẫn kiểm tra thời gian tự động thay vì nới cửa sổ chấp nhận vô hạn.

### Push bị từ chối hoặc hết hạn

Gợi ý:

> Yêu cầu xác minh chưa được chấp thuận. Nếu bạn không khởi tạo yêu cầu này, hãy từ chối và báo cáo qua kênh bảo mật chính thức.

Không khuyến khích người dùng approve một prompt cũ chỉ để hoàn tất login. Hiển thị rõ context như tên ứng dụng hoặc hành động nếu thiết kế hỗ trợ, đồng thời có cách báo cáo prompt không mong muốn.

### Không nhận được mã

Gợi ý:

> Chưa nhận được mã? Hãy kiểm tra kết nối và thử gửi lại sau khi bộ đếm cho phép. Nếu vẫn không nhận được, dùng phương thức dự phòng đã thiết lập.

Nút gửi lại phải có cooldown và rate limit. Không tạo nhiều OTP đồng thời khiến người dùng không biết mã nào còn hiệu lực.

### Không thể dùng factor hiện tại

Trước khi người dùng được xác minh, không liệt kê các factor account đang có. Sau proof phù hợp, có thể hướng dẫn dùng phương thức dự phòng hoặc quy trình recovery.

## 7. Thông báo lỗi passkey và WebAuthn

Passkey phụ thuộc browser, hệ điều hành, authenticator, RP ID, origin và trạng thái thiết bị. Lỗi kỹ thuật có thể có nhiều nguyên nhân; người dùng cần được hướng dẫn bằng hành động dễ thực hiện.

### Ví dụ thông báo

| Tình huống | Thông báo gợi ý |
|---|---|
| Người dùng hủy hộp thoại | Bạn đã hủy xác minh. Hãy thử lại khi sẵn sàng. |
| Không tìm thấy passkey phù hợp | Không thể hoàn tất bằng thiết bị này. Hãy thử thiết bị hoặc phương thức đã thiết lập khác. |
| Thiết bị không hỗ trợ | Trình duyệt hoặc thiết bị hiện tại chưa hỗ trợ phương thức này. Hãy cập nhật hoặc dùng phương thức khác. |
| Challenge hết hạn | Yêu cầu xác minh đã hết hạn. Hãy bắt đầu lại từ trang đăng nhập. |
| Lỗi origin/RP ID | Không hiển thị chi tiết nội bộ; ghi reason code để đội kỹ thuật điều tra. |
| Cần user verification | Hãy mở khóa thiết bị hoặc hoàn tất xác minh sinh trắc học/PIN theo hướng dẫn của thiết bị. |

Không nói rằng server đã nhận hoặc lưu private key. WebAuthn không gửi private key lên website. Không yêu cầu người dùng gửi credential ID, authenticator response hoặc ảnh chứa thông tin bảo mật cho helpdesk.

### Khi đăng ký passkey

Giải thích trước:

- Passkey được dùng để đăng nhập vào dịch vụ này.
- Người dùng cần hoàn tất thao tác trên thiết bị/authenticator.
- Không chia sẻ PIN thiết bị hoặc thông tin sinh trắc học.
- Có phương thức recovery phù hợp nếu mất thiết bị.

Nếu registration thất bại, giữ dữ liệu form không nhạy cảm khi an toàn để tránh nhập lại, nhưng không lưu hoặc log raw assertion.

## 8. Thông báo lỗi token và session

Người dùng thường không cần biết JWT, signature hay introspection. Họ cần biết phiên có còn dùng được và cách tiếp tục.

### Session hết hạn

Gợi ý:

> Phiên đăng nhập đã hết hạn. Hãy đăng nhập lại để tiếp tục.

Nếu có dữ liệu chưa lưu, cảnh báo trước khi session hết hạn và cho phép lưu bản nháp an toàn khi phù hợp. Không tự động giữ session vô thời hạn chỉ để tránh làm phiền.

### Bị đăng xuất do bảo vệ tài khoản

Gợi ý:

> Vì lý do bảo mật, bạn cần đăng nhập lại trước khi tiếp tục.

Không hiển thị chi tiết risk signal, IP hoặc detection rule cho unauthenticated caller. Sau khi người dùng xác minh lại, cung cấp hướng dẫn kiểm tra hoạt động tài khoản nếu policy cho phép.

### Token không hợp lệ hoặc dependency lỗi

Với end-user, có thể yêu cầu đăng nhập lại nếu token hết hạn. Nếu IdP hoặc dịch vụ xác minh đang không khả dụng, thông báo đúng trạng thái:

> Dịch vụ đăng nhập tạm thời không khả dụng. Hãy thử lại sau ít phút.

Không báo “Mật khẩu không đúng” khi backend không thể liên hệ IdP. Không yêu cầu người dùng đổi password để khắc phục lỗi hệ thống.

## 9. Thông báo lỗi đăng nhập liên kết và SSO

Luồng OpenID Connect hoặc SSO có thể chuyển người dùng qua nhiều domain. Thông báo phải giúp họ hiểu bước tiếp theo và tránh tạo cơ hội phishing.

### Các trạng thái

- IdP yêu cầu đăng nhập hoặc MFA.
- Người dùng hủy đăng nhập tại IdP.
- Callback không hoàn tất.
- Phiên IdP hết hạn.
- Ứng dụng không nhận được phản hồi từ IdP.
- Tài khoản không được phép truy cập ứng dụng theo policy.

### Copy gợi ý

- “Bạn đã hủy đăng nhập. Hãy quay lại ứng dụng nếu muốn thử lại.”
- “Không thể kết nối tới dịch vụ đăng nhập của tổ chức. Hãy thử lại sau.”
- “Bạn chưa thể truy cập ứng dụng này. Nếu cho rằng đây là nhầm lẫn, hãy liên hệ quản trị viên qua kênh chính thức.”

Không hiển thị authorization code, state, nonce, ID token, access token, issuer metadata hoặc redirect URL nội bộ. Không hướng người dùng tới một domain đăng nhập không được xác minh.

## 10. Thông báo lỗi account recovery

Recovery là thời điểm người dùng dễ lo lắng và dễ bị lừa. Thông báo phải rõ ràng nhưng không tiết lộ account state hoặc trao quyền qua một link không an toàn.

### Request reset

Thông báo public:

> Nếu thông tin bạn nhập gắn với tài khoản, hướng dẫn sẽ được gửi tới kênh đã đăng ký.

Không xác nhận account tồn tại. Không hiển thị địa chỉ email/số điện thoại đầy đủ trước khi proof-of-control phù hợp.

### Link hết hạn hoặc đã dùng

Trong trang recovery sau khi người dùng mở link:

> Liên kết khôi phục không còn hiệu lực. Hãy bắt đầu yêu cầu mới từ trang chính thức.

Không hiển thị token hoặc query string. Khi link được dùng thành công, vô hiệu hóa token và không tái sử dụng nó để tự động cấp session ngoài policy.

### Cần xác minh bổ sung

Gợi ý:

> Chúng tôi cần xác minh thêm trước khi thay đổi phương thức khôi phục. Hãy tiếp tục theo hướng dẫn trên trang chính thức.

Không yêu cầu người dùng gửi password, OTP, recovery code hoặc private key cho nhân viên hỗ trợ.

## 11. Thông báo lỗi do policy và quyền truy cập

Một người dùng có thể xác thực thành công nhưng không được phép thực hiện hành động. Không nên gọi đó là lỗi password.

### Authentication failure

Không xác minh được credential hoặc challenge. Hướng dẫn người dùng thử lại, kiểm tra factor hoặc recovery theo trạng thái.

### Authorization denial

Principal đã được xác minh nhưng thiếu quyền. Thông báo:

> Bạn không có quyền thực hiện thao tác này. Nếu bạn cần quyền truy cập, hãy gửi yêu cầu qua quy trình được tổ chức phê duyệt.

Không tiết lộ role, group hoặc permission nội bộ nếu người dùng không cần biết. Không tự động chuyển hướng sang login khi user chỉ thiếu permission, vì điều đó khiến họ lặp lại xác thực mà không giải quyết vấn đề.

### Account bị hạn chế

Trước xác minh, dùng thông báo public nhất quán. Sau khi xác minh phù hợp, có thể đưa hướng dẫn liên hệ support, thời điểm thử lại hoặc yêu cầu review. Không hiển thị chi tiết detection rule hay bằng chứng có thể giúp attacker né kiểm soát.

## 12. Thông báo lỗi do hệ thống và dependency

Các lỗi như IdP timeout, session store unavailable, KMS/HSM failure hoặc network outage không phải lỗi người dùng.

### Cách viết

- “Dịch vụ đăng nhập tạm thời không khả dụng. Hãy thử lại sau ít phút.”
- “Không thể hoàn tất xác minh lúc này. Thông tin của bạn chưa được thay đổi.”
- “Yêu cầu chưa hoàn tất. Hãy thử lại sau; nếu vấn đề tiếp diễn, liên hệ hỗ trợ và cung cấp mã tham chiếu.”

Chỉ nói “thông tin chưa được thay đổi” nếu hệ thống biết chắc giao dịch chưa commit. Với thao tác có kết quả chưa xác định, hãy nói rõ cần kiểm tra trạng thái trước khi retry để tránh tạo hành động trùng.

### Retry an toàn

- Có retry delay hoặc Retry-After khi phù hợp.
- Không yêu cầu refresh liên tục.
- Với hành động tạo giao dịch hoặc thay đổi credential, dùng idempotency hoặc trạng thái kiểm tra để tránh thực hiện hai lần.
- Không retry vô hạn với IdP/MFA provider.
- Khi dependency lỗi, không fail-open và không bỏ qua MFA.

## 13. Cấu trúc một error message

Một thành phần lỗi có thể gồm:

1. **Title:** tên trạng thái ngắn.
2. **Description:** điều vừa xảy ra bằng ngôn ngữ đơn giản.
3. **Action:** nút hoặc liên kết tiếp theo.
4. **Help:** đường hỗ trợ chính thức nếu cần.
5. **Reference:** mã tham chiếu không nhạy cảm để hỗ trợ điều tra.

Ví dụ:

~~~text
Không thể hoàn tất đăng nhập

Dịch vụ xác minh tạm thời không khả dụng. Tài khoản của bạn chưa được đăng nhập.

[Thử lại]

Nếu vấn đề tiếp diễn, liên hệ bộ phận hỗ trợ qua cổng trợ giúp chính thức.
Mã tham chiếu: RQ-7F31
~~~

Chỉ hiển thị nút hành động khi nó thực sự khả dụng. Nếu retry có thể tạo giao dịch trùng hoặc khóa account, cần kiểm tra trạng thái trước khi đề xuất.

## 14. Inline error, form-level error và page-level error

Đặt lỗi ở vị trí giúp người dùng tìm thấy và hiểu nó.

| Vị trí | Dùng khi | Ví dụ |
|---|---|---|
| Inline | Một trường cụ thể có lỗi định dạng hoặc thiếu dữ liệu | Email không đúng định dạng |
| Form-level | Cả thao tác không thành công | Thông tin đăng nhập không hợp lệ |
| Page-level | Dịch vụ hoặc toàn bộ flow không khả dụng | Dịch vụ đăng nhập tạm thời không khả dụng |
| Field hint | Hướng dẫn trước khi nhập | Dùng mã mới nhất từ ứng dụng xác thực |
| Toast/status | Kết quả ngắn của thao tác không làm mất ngữ cảnh | Yêu cầu đã được gửi |

Không chỉ dựa vào màu đỏ để biểu thị lỗi. Kết hợp icon, nhãn, văn bản và vị trí. Khi lỗi nằm ở field, liên kết thông báo với input để screen reader đọc được.

### Giữ dữ liệu đã nhập

Nếu submit thất bại vì lỗi mạng hoặc dependency, có thể giữ identifier và các trường không nhạy cảm để người dùng không nhập lại. Password, OTP và recovery code cần được xử lý theo policy; không lưu vào local storage, analytics hoặc form state kéo dài ngoài nhu cầu an toàn.

## 15. Accessibility và trải nghiệm bàn phím

Thông báo lỗi phải dùng được với người sử dụng screen reader, keyboard, zoom và thiết bị hỗ trợ.

- Dùng văn bản rõ, không chỉ màu sắc hoặc icon.
- Đặt focus vào summary lỗi hoặc trường cần sửa theo hành vi nhất quán.
- Liên kết lỗi với trường nhập bằng cơ chế accessibility của nền tảng.
- Thông báo thay đổi trạng thái bằng live region phù hợp, tránh đọc lặp quá nhiều.
- Giữ thứ tự tab hợp lý.
- Nút retry, recovery và help có tên dễ hiểu.
- Không tự động xóa nội dung người dùng nhập khi có lỗi không liên quan.
- Cho phép paste và password manager.
- Không yêu cầu thao tác kéo-thả hoặc tương tác khó tiếp cận làm phương thức xác thực duy nhất.
- Với timeout, cảnh báo trước và hỗ trợ gia hạn an toàn khi policy cho phép.

### Tránh thông báo gây nhầm

Không dùng “Invalid” mà không chỉ rõ trường hoặc hành động. Không đặt focus vào một control đã biến mất. Không hiển thị lỗi chỉ trong toast tự biến mất nếu người dùng cần đọc hoặc thực hiện hành động.

## 16. Localization và ngôn ngữ nhất quán

Thông báo xác thực thường xuất hiện ở thời điểm người dùng căng thẳng. Dịch máy từng câu mà không thống nhất thuật ngữ có thể làm người dùng hiểu sai.

### Quy tắc localization

- Dùng từ phổ thông và câu ngắn.
- Giữ một thuật ngữ nhất quán cho tài khoản, phiên, mã xác minh, passkey và phương thức khôi phục.
- Không ghép chuỗi bằng cách nối các mảnh ngôn ngữ khiến câu sai ngữ pháp.
- Hỗ trợ ký tự Unicode và tên người dùng hợp lệ.
- Không giả định mọi người dùng có cùng định dạng ngày, giờ hoặc số điện thoại.
- Không đặt thông tin nhạy cảm vào chuỗi dịch.
- Kiểm tra độ dài vì bản dịch có thể dài hơn và làm vỡ giao diện.
- Có người bản ngữ hoặc reviewer hiểu lĩnh vực xác minh nội dung quan trọng.

### Ví dụ thuật ngữ

| Thuật ngữ | Cách dùng nhất quán |
|---|---|
| Password | Mật khẩu |
| Passkey | Passkey (khóa truy cập) khi cần giải thích lần đầu |
| Session | Phiên đăng nhập |
| Verification code | Mã xác minh |
| Recovery code | Mã khôi phục |
| Sign in | Đăng nhập |
| Sign out | Đăng xuất |
| Identity provider | Nhà cung cấp danh tính (IdP) |

Không dịch passkey thành mật khẩu hoặc mã OTP. Đây là các cơ chế khác nhau và hướng dẫn khắc phục cũng khác nhau.

## 17. Error message và chống phishing

Thông báo lỗi có thể bị attacker giả mạo trong email, SMS, trang web hoặc cuộc gọi hỗ trợ.

### Thiết kế an toàn

- Không đưa link đăng nhập tới domain không quen thuộc hoặc không được tổ chức công bố.
- Khi cần recovery, hướng người dùng tự mở ứng dụng/website chính thức.
- Không yêu cầu người dùng gửi OTP, recovery code hoặc password qua email/chat/phone.
- Không hiển thị toàn bộ email hoặc số điện thoại trước khi xác minh phù hợp.
- Không dùng giọng đe dọa như “Tài khoản sẽ bị xóa ngay” để thúc ép.
- Thông báo bảo mật nên nêu hoạt động và hành động bảo vệ mà người dùng có thể thực hiện.
- Cung cấp đường báo cáo login/MFA prompt không do người dùng khởi tạo.

### Ví dụ thông báo bảo mật

> Có một yêu cầu đăng nhập cần xác minh. Nếu bạn không khởi tạo yêu cầu này, hãy từ chối và mở trang bảo mật chính thức để kiểm tra hoạt động tài khoản.

Không gửi link chứa bearer recovery token dài hạn trong thông báo nếu có thể dùng đường dẫn tới trang chính thức để người dùng tự bắt đầu quy trình.

## 18. Error message trong API và machine client

API error contract dành cho developer/client cần ổn định và có thể xử lý tự động. Nội dung kỹ thuật không nên được hiển thị nguyên xi cho end-user.

### Phân tách field

- HTTP status: phân loại kết quả giao thức.
- Stable error code: cho client biết nhóm xử lý.
- Safe detail: thông điệp công khai.
- Request reference: liên hệ support.
- Retry metadata: chỉ khi client có thể retry an toàn.

Ví dụ:

~~~json
{
  "type": "https://api.example.test/problems/session-expired",
  "title": "Session expired",
  "status": 401,
  "detail": "Phiên đăng nhập đã hết hạn. Hãy đăng nhập lại để tiếp tục.",
  "code": "SESSION_EXPIRED",
  "request_id": "req-7f31"
}
~~~

Không trả stack trace, SQL error, token claim đầy đủ, key ID bí mật hoặc thông tin account nội bộ. Client không nên phân tích chuỗi detail để quyết định logic; dùng status và code đã tài liệu hóa.

### Phân biệt lỗi thường gặp

- 401: credential thiếu, không hợp lệ hoặc hết hạn theo contract.
- 403: đã xác thực nhưng không đủ quyền.
- 429: rate limit hoặc cooldown.
- 5xx/503: dịch vụ hoặc dependency không thể xử lý.

Status cụ thể cần theo API contract và protocol đang dùng. Không đổi một dependency outage thành 401 chỉ để buộc người dùng đăng nhập lại.

## 19. Nội dung cho helpdesk và hỗ trợ

Thông báo nên giúp người dùng tìm được kênh trợ giúp chính thức, đồng thời bảo vệ nhân viên hỗ trợ khỏi social engineering.

### Hướng dẫn helpdesk

- Nêu cách mở cổng hỗ trợ chính thức.
- Yêu cầu mã tham chiếu, thời điểm và bước đã thực hiện; không yêu cầu secret.
- Không yêu cầu password, OTP, recovery code hoặc private key.
- Xác minh danh tính theo quy trình độc lập trước khi reset MFA hoặc thay recovery method.
- Không tiết lộ account state qua một cuộc gọi chưa xác minh.
- Ghi nhận hành động hỗ trợ và người phê duyệt trong audit.

### Ví dụ

> Nếu bạn vẫn không đăng nhập được, hãy mở cổng hỗ trợ nội bộ từ bookmark hoặc trang chủ của tổ chức và cung cấp mã tham chiếu RQ-7F31. Nhân viên hỗ trợ sẽ không yêu cầu bạn đọc mật khẩu hoặc mã xác minh.

Không dùng mã tham chiếu tuần tự có thể đoán để lộ số lượng incident hoặc thông tin người dùng.

## 20. Thông báo cho thao tác nhạy cảm

Khi người dùng đổi password, thêm passkey, thay recovery method hoặc revoke session, thông báo phải xác nhận kết quả và chỉ rõ hành động tiếp theo.

### Thành công

- “Mật khẩu đã được cập nhật.”
- “Passkey đã được thêm vào tài khoản.”
- “Phiên đăng nhập trên thiết bị đã được kết thúc.”
- “Phương thức khôi phục đã được cập nhật.”

Chỉ hiển thị thành công sau khi server xác nhận thao tác đã commit.

### Kết quả chưa xác định

Nếu request timeout sau khi server có thể đã commit, không khẳng định thất bại hoặc thành công. Hướng dẫn kiểm tra trạng thái:

> Chưa thể xác nhận kết quả thao tác. Hãy kiểm tra trạng thái trong trang bảo mật trước khi thử lại.

Điều này tránh người dùng lặp thao tác thêm factor, rotate key hoặc tạo recovery code ngoài ý muốn.

### Bị từ chối theo policy

Gợi ý:

> Không thể hoàn tất thay đổi này lúc này. Hãy xác minh lại danh tính hoặc liên hệ quản trị viên qua kênh chính thức.

Không tiết lộ rule nội bộ, risk score hoặc điều kiện detection có thể bị né tránh.

## 21. Content pattern và thư viện thông báo

Tổ chức nên duy trì một thư viện thông báo đã được review thay vì để từng màn hình tự viết copy.

Một content entry có thể gồm:

- Stable message ID.
- Ngữ cảnh và trạng thái authentication.
- Audience: end-user, admin hoặc machine client.
- Title, description và action.
- Mức độ nhạy cảm và enumeration consideration.
- Bản dịch đã review.
- Accessibility notes.
- Owner và version.
- Test case liên quan.

### Ví dụ thư viện

| Message ID | Ngữ cảnh | Nội dung chính |
|---|---|---|
| AUTH-LOGIN-01 | Credential không được chấp nhận | Thông tin đăng nhập không hợp lệ. Hãy thử lại. |
| AUTH-LOGIN-02 | Dịch vụ đăng nhập lỗi | Dịch vụ đăng nhập tạm thời không khả dụng. |
| AUTH-MFA-01 | Mã xác minh chưa hợp lệ | Chưa thể xác minh mã. Hãy kiểm tra mã mới nhất. |
| AUTH-SESSION-01 | Phiên hết hạn | Phiên đăng nhập đã hết hạn. Hãy đăng nhập lại. |
| AUTH-RECOVERY-01 | Yêu cầu recovery public | Nếu thông tin gắn với tài khoản, hướng dẫn sẽ được gửi tới kênh đã đăng ký. |
| AUTH-ACCESS-01 | Thiếu quyền | Bạn không có quyền thực hiện thao tác này. |

Không tái sử dụng một message ID cho các trạng thái có ý nghĩa khác nhau. Khi thay nội dung, kiểm tra ảnh hưởng tới localization, automation test và support documentation.

## 22. Những anti-pattern cần tránh

- **Chỉ hiển thị mã lỗi:** người dùng không biết phải làm gì.
- **Đổ lỗi:** “Bạn đã nhập sai” trong khi dependency có thể đang lỗi.
- **Tiết lộ account state:** giúp attacker dò tài khoản.
- **Quá kỹ thuật:** hiển thị stack trace, claim hoặc exception.
- **Quá chung chung:** “Có lỗi xảy ra” mà không có hướng xử lý.
- **Retry không an toàn:** yêu cầu bấm lại thao tác có thể đã commit.
- **Mất dữ liệu form:** xóa identifier hoặc thông tin không nhạy cảm sau lỗi mạng.
- **Chỉ dùng màu:** người mù màu hoặc screen reader không nhận biết.
- **Toast tự biến mất:** thông tin quan trọng biến mất trước khi đọc.
- **Link recovery đáng ngờ:** đưa người dùng tới domain không xác minh.
- **Hứa quá mức:** “Tài khoản của bạn hoàn toàn an toàn” khi hệ thống chưa điều tra.
- **Nói sai nguyên nhân:** báo password sai khi IdP timeout.
- **Dùng thuật ngữ lẫn lộn:** gọi passkey là OTP hoặc session là token.

## 23. Kiểm thử usability và security của error message

Kiểm thử với các trạng thái và người dùng khác nhau, không chỉ review câu chữ trong tài liệu.

| Trường hợp | Kết quả mong đợi |
|---|---|
| Account tồn tại, password sai | Thông báo public an toàn |
| Account không tồn tại | Nội dung/shape không tiết lộ account state |
| Forgot password cho account khác nhau | Response công khai nhất quán |
| IdP timeout | Báo dịch vụ tạm thời lỗi, không báo password sai |
| MFA code sai/hết hạn | Hướng dẫn lấy mã mới, không tiết lộ secret |
| Push không do user khởi tạo | Hướng dẫn từ chối và báo cáo |
| Passkey bị hủy | Có thể thử lại mà không hiểu nhầm là compromise |
| Passkey origin mismatch | Public message an toàn; internal reason đủ điều tra |
| Session hết hạn | Hướng dẫn đăng nhập lại |
| User thiếu permission | Thông báo access denied, không bắt login lặp |
| Rate limit | Có hướng dẫn chờ/thử lại phù hợp |
| Recovery token hết hạn | Hướng dẫn bắt đầu quy trình mới từ trang chính thức |
| Dependency lỗi sau thao tác nhạy cảm | Không khẳng định kết quả nếu chưa biết trạng thái commit |
| API trả stack trace | Test phải thất bại |
| Response chứa token hoặc account detail | Test privacy phải thất bại |
| Screen reader đọc lỗi | Nội dung và focus được thông báo đúng |
| Chỉ dùng màu đỏ để báo lỗi | Accessibility test phát hiện |
| Ngôn ngữ dài hơn | Layout không che nội dung/action |
| Retry action có thể tạo giao dịch trùng | Có kiểm tra trạng thái hoặc idempotency |
| Link hỗ trợ giả mạo | Chỉ dùng domain/kênh chính thức đã công bố |

### Usability test với người dùng

Đặt câu hỏi sau mỗi tình huống:

- Người dùng hiểu điều gì vừa xảy ra không?
- Họ biết bước tiếp theo không?
- Họ có phân biệt được lỗi của mình với lỗi dịch vụ không?
- Họ có biết nơi tìm trợ giúp chính thức không?
- Họ có bị yêu cầu chia sẻ secret không?
- Thông báo có thể đọc bằng bàn phím và screen reader không?

Không yêu cầu người tham gia dùng password hoặc tài khoản thật. Dùng test identity và dữ liệu giả lập.

## 24. Đo lường chất lượng thông báo

Metric usability có thể giúp nhận ra thông báo khó hiểu hoặc flow tạo nhiều lỗi lặp.

Có thể theo dõi:

- Tỷ lệ người dùng hoàn tất bước tiếp theo sau khi thấy lỗi.
- Tỷ lệ thử lại thành công sau thông báo.
- Tỷ lệ abandon theo loại trạng thái.
- Số lần mở help link hoặc bắt đầu recovery.
- Tỷ lệ lỗi lặp lại cùng một attempt.
- Số ticket hỗ trợ liên quan đến một message ID.
- Tỷ lệ accessibility test pass.

Không thu thập nội dung password, OTP, token hoặc toàn bộ text người dùng nhập để phân tích usability. Metric nên dùng message ID và nhóm trạng thái hữu hạn; drill-down tới account chỉ qua quy trình có quyền.

Không tối ưu chỉ số retry thành công bằng cách nới lỏng kiểm soát xác thực. Mục tiêu là giảm nhầm lẫn và giúp người dùng hợp lệ hoàn tất đúng quy trình.

## 25. Checklist thiết kế error message usability

- [ ] Thông báo nói rõ trạng thái bằng ngôn ngữ người dùng hiểu.
- [ ] Có hành động tiếp theo an toàn và khả thi.
- [ ] Không tiết lộ account existence, lock state hoặc MFA enrollment trước proof phù hợp.
- [ ] Nội dung, status, redirect và timing được xem xét chống enumeration.
- [ ] Phân biệt credential failure, authorization denial và dependency error.
- [ ] Password error không tiết lộ chi tiết password hoặc account.
- [ ] MFA message hướng dẫn đúng loại factor và không khuyến khích approve prompt lạ.
- [ ] Passkey/WebAuthn message có hướng dẫn thiết bị mà không lộ protocol secret.
- [ ] Session/token expiry có hướng dẫn đăng nhập lại phù hợp.
- [ ] Recovery message không lộ account và không gửi người dùng tới domain không tin cậy.
- [ ] API error code ổn định; detail không chứa stack trace hoặc secret.
- [ ] Retry chỉ được gợi ý khi an toàn; thao tác chưa rõ kết quả có cách kiểm tra trạng thái.
- [ ] Inline/form/page error được đặt đúng vị trí.
- [ ] Hỗ trợ keyboard, screen reader, zoom và không chỉ dựa vào màu.
- [ ] Thuật ngữ và bản dịch nhất quán.
- [ ] Helpdesk không yêu cầu password, OTP, recovery code hoặc private key.
- [ ] Thao tác nhạy cảm chỉ báo thành công sau khi server xác nhận commit.
- [ ] Có thư viện message ID, owner, version và test.
- [ ] Có usability test và security test cho enumeration/privacy.
- [ ] Metric không thu thập secret hoặc dữ liệu cá nhân không cần thiết.

## Ghi nhớ

Error message tốt giúp người dùng hiểu trạng thái và biết bước tiếp theo, nhưng chỉ tiết lộ mức thông tin phù hợp với trạng thái xác thực. Trước khi xác minh, thông báo login và recovery cần nhất quán để tránh account enumeration. Sau khi proof phù hợp, có thể đưa hướng dẫn cụ thể hơn về factor, thiết bị hoặc quy trình hỗ trợ.

Hãy phân biệt lỗi credential, quyền truy cập và dependency; không yêu cầu người dùng chia sẻ secret; không khẳng định kết quả khi giao dịch chưa rõ trạng thái. Viết ngắn gọn, hỗ trợ accessibility và localization, kiểm thử cả usability lẫn side channel để trải nghiệm tốt không làm suy yếu bảo mật.
