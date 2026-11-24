# Low risk recovery: khôi phục tài khoản khi rủi ro thấp

## 1. Rủi ro thấp có ý nghĩa gì?

Low risk recovery là nhánh khôi phục dành cho yêu cầu có đủ bằng chứng hợp lệ, không xuất hiện dấu hiệu bắt buộc tăng cường xác minh và chỉ thực hiện một thay đổi được cho phép. Mục tiêu là giúp chủ tài khoản lấy lại khả năng truy cập với ít thao tác cần thiết, trong khi vẫn giới hạn cơ hội chiếm đoạt tài khoản.

Ví dụ, Linh quên mật khẩu nhưng vẫn giữ khóa bảo mật đã đăng ký, còn kiểm soát địa chỉ khôi phục đã xác minh và không có cảnh báo tài khoản bị xâm nhập. Hệ thống có thể cho Linh đặt lại mật khẩu qua một luồng tự phục vụ. Việc này không đồng nghĩa Linh được gỡ MFA, thay email khôi phục và đăng ký thiết bị mới trong cùng giao dịch.

Cần phân biệt ba khái niệm:

- **Rủi ro của yêu cầu:** khả năng yêu cầu đang do kẻ tấn công thực hiện.
- **Độ tin cậy của bằng chứng:** điều gì thực sự chứng minh người yêu cầu có quyền khôi phục.
- **Tác động của hành động:** quyền hoặc bí mật nào sẽ thay đổi nếu yêu cầu thành công.

Một yêu cầu ít bất thường vẫn có thể thiếu bằng chứng. Một bằng chứng hợp lệ cũng không tự cho phép mọi hành động có tác động lớn. Nhãn “LOW” phải gắn với tài khoản, giao dịch và hành động cụ thể.

NIST phân biệt tín hiệu gian lận với yếu tố xác thực: tín hiệu như vị trí hoặc mạng có thể hỗ trợ quyết định, nhưng không thay thế yếu tố xác thực hoặc tự nâng mức bảo đảm của một giao dịch. Vì vậy, thiết bị quen và IP quen chỉ bổ sung ngữ cảnh; chúng không đủ để cấp quyền khôi phục. [NIST SP 800-63B, Authentication Assurance Levels](https://pages.nist.gov/800-63-4/sp800-63b.html#aal)

## 2. Xác định hành động trước khi phân loại

Trong module khôi phục tài khoản, người dùng có thể mất mật khẩu, MFA, passkey hoặc cả thiết bị xác thực. Các tình huống này cần chính sách riêng vì khả năng chứng minh quyền kiểm soát còn lại khác nhau.

| Yêu cầu | Bằng chứng còn lại trong ví dụ | Cách xử lý có thể áp dụng |
| --- | --- | --- |
| Quên mật khẩu | Khóa bảo mật dự phòng đã đăng ký và kênh liên hệ ổn định | Xem xét nhánh tự phục vụ chỉ đặt lại mật khẩu |
| Mất một passkey | Vẫn có passkey khác đáp ứng chính sách xác thực | Xác thực bằng passkey còn lại, rồi quản lý phương thức bị mất |
| Mất ứng dụng MFA | Có mã khôi phục đã cấp trước đó | Dùng chính sách riêng cho phục hồi MFA; đánh giá tác động trước khi cấp quyền |
| Mất mọi phương thức | Chỉ nhớ tên, ngày sinh hoặc thông tin công khai | Chuyển sang quy trình xác minh bổ sung |
| Muốn thay email khôi phục | Chỉ kiểm soát email mới cung cấp trong yêu cầu | Chưa đủ cơ sở để dùng email mới làm bằng chứng khôi phục |

Các dòng trên là ví dụ thiết kế, không phải quy tắc rằng mọi tài khoản có cùng tập bằng chứng đều được phê duyệt. Tài khoản quản trị, tài khoản có quyền thanh toán hoặc tài khoản thuộc tổ chức có thể cần yêu cầu bảo đảm cao hơn.

Nếu người dùng vẫn đăng nhập được bằng một phương thức hợp lệ khác, hệ thống nên tận dụng quy trình quản lý phương thức xác thực sau khi tái xác thực. Không cần ép mọi trường hợp mất thiết bị đi qua nhánh khôi phục khi mất toàn bộ khả năng đăng nhập.

## 3. Điều kiện vào nhánh rủi ro thấp

Có thể thiết kế cổng quyết định theo ba lớp, áp dụng theo thứ tự.

### 3.1. Điều kiện bắt buộc về bằng chứng

Hệ thống xác định trước loại bằng chứng được chấp nhận cho từng hành động. Bằng chứng phải được kiểm tra ở máy chủ, gắn đúng tài khoản, còn hiệu lực và chưa bị thu hồi.

Ví dụ, một assertion của khóa bảo mật phải được bộ xác minh của hệ thống chấp nhận cho giao dịch hiện tại. Việc trình duyệt gửi trường hasSecurityKey=true không có giá trị chứng minh. Tương tự, một chuỗi trông giống mã khôi phục chưa phải là mã hợp lệ cho đến khi máy chủ kiểm tra và quản lý việc sử dụng nó.

Bằng chứng được tạo trong chính yêu cầu hiện tại không tự trở thành lịch sử đáng tin. Kẻ tấn công có thể khai báo một email mới rồi chứng minh họ kiểm soát email đó; điều này chưa chứng minh email mới thuộc chủ tài khoản cần khôi phục.

### 3.2. Điều kiện loại khỏi nhánh nhanh

Trong chính sách minh họa, các tình huống sau yêu cầu chuyển nhánh:

- Có báo cáo phương thức xác thực hoặc tài khoản đang bị chiếm quyền.
- Dữ liệu liên hệ khôi phục vừa thay đổi hoặc đang có thay đổi chưa xác minh.
- Có giao dịch khôi phục khác đang xử lý cùng tài khoản.
- Hành động yêu cầu nằm ngoài phạm vi tự phục vụ đã phê duyệt.
- Thiếu dữ liệu cần thiết để quyết định, hoặc dịch vụ cung cấp tín hiệu quan trọng gặp lỗi.

“Không có cảnh báo” khác với “không nhận được dữ liệu cảnh báo”. Hệ thống cần biểu diễn riêng trạng thái KNOWN_CLEAR, ALERT và UNKNOWN, thay vì dùng một giá trị boolean mặc định là an toàn.

Chuyển nhánh không nhất thiết là từ chối người dùng. Hệ thống có thể yêu cầu một bằng chứng độc lập, chờ dữ liệu hoạt động trở lại hoặc chuyển sang hỗ trợ theo chính sách phù hợp.

### 3.3. Tín hiệu hỗ trợ

Sau khi thỏa mãn các điều kiện bắt buộc, hệ thống mới dùng tín hiệu ngữ cảnh để đánh giá mức bất thường.

| Tín hiệu | Giá trị hỗ trợ | Giới hạn cần hiểu |
| --- | --- | --- |
| Thiết bị từng xác thực thành công | Cho thấy tính liên tục của môi trường sử dụng | Cookie có thể bị sao chép; máy có thể dùng chung hoặc bị kiểm soát |
| Mạng thường sử dụng | Giảm một số bất thường về vị trí truy cập | IP dùng chung, VPN và mạng di động làm tín hiệu nhiễu |
| Kênh khôi phục đã được xác minh từ trước | Cung cấp một đường liên hệ có lịch sử | Hộp thư hoặc số điện thoại vẫn có thể bị chiếm đoạt |
| Ít yêu cầu thất bại gần đây | Giảm dấu hiệu dò mã ở phạm vi quan sát | Tấn công có thể phân tán theo thời gian và hạ tầng |
| Hành động có phạm vi hẹp | Giới hạn hậu quả nếu có sai sót | Thay đổi mật khẩu vẫn có thể là hành động nhạy cảm |

Không cộng điểm cho nhiều tín hiệu tương quan như thể chúng là bằng chứng độc lập. Cookie thiết bị, phiên trình duyệt và IP cùng lấy từ một máy bị xâm nhập có thể cùng bị kiểm soát bởi một kẻ tấn công.

## 4. Một luồng tự phục vụ có giới hạn

Xét chính sách minh họa cho tài khoản thông thường:

- Chỉ hỗ trợ RESET_PASSWORD trong nhánh nhanh.
- Người dùng vẫn có phương thức xác thực đã đăng ký đáp ứng yêu cầu của chính sách.
- Kênh thông báo và dữ liệu khôi phục không có thay đổi đang tranh chấp.
- Không có tín hiệu buộc chuyển sang quy trình xử lý nghi ngờ chiếm quyền.
- Sau khi đặt mật khẩu, người dùng đăng nhập qua cơ chế thông thường và tiếp tục đáp ứng MFA nếu tài khoản yêu cầu.

~~~mermaid
flowchart TD
    A["Nhận yêu cầu đặt lại mật khẩu"] --> B["Tạo giao dịch và áp dụng chống lạm dụng"]
    B --> C["Kiểm tra bằng chứng theo chính sách"]
    C --> D{"Đủ bằng chứng?"}
    D -- "Chưa đủ" --> E["Yêu cầu xác minh bổ sung"]
    D -- "Đủ" --> F{"Có cảnh báo hoặc dữ liệu quan trọng chưa rõ?"}
    F -- "Có" --> G["Chuyển nhánh và giữ nguyên bảo vệ tài khoản"]
    F -- "Không" --> H["Cấp quyền khôi phục giới hạn"]
    H --> I["Người dùng xác nhận mật khẩu mới"]
    I --> J["Đánh giá lại và áp dụng thay đổi nguyên tử"]
    J --> K["Thu hồi quyền khôi phục, xử lý session và thông báo"]
    K --> L["Đăng nhập theo chính sách hiện hành"]
~~~

Kết quả của bước đánh giá là quyền tiếp tục một giao dịch, chưa phải phiên đăng nhập đầy đủ. Giao diện cần diễn đạt đúng phạm vi: “Bạn có thể đặt lại mật khẩu” rõ ràng hơn “Danh tính đã được xác minh hoàn toàn”.

Nếu người dùng đổi yêu cầu từ đặt mật khẩu sang gỡ MFA, hệ thống phải tạo quyết định mới cho hành động mới. Không tái sử dụng nhãn rủi ro thấp của hành động trước.

## 5. Dữ liệu của quyết định phải gắn với giao dịch

Một quyết định chỉ có riskLevel=LOW thiếu ngữ cảnh để thực thi an toàn. Máy chủ cần biết quyết định đó cho ai, cho việc gì, dựa vào bằng chứng nào và còn hiệu lực đến lúc nào.

Ví dụ cấu trúc nội bộ:

~~~text
RecoveryDecision
  transactionId
  accountId
  action = RESET_PASSWORD
  result = ALLOW_RESTRICTED_RECOVERY
  policyVersion
  reasonCodes
  evidenceReferences
  evaluatedAt
  expiresAt
  accountSecurityVersion
~~~

evidenceReferences trỏ đến kết quả xác minh có kiểm soát truy cập, không chứa nguyên token, mã khôi phục hoặc mật khẩu. accountSecurityVersion là một cơ chế minh họa để phát hiện dữ liệu bảo mật của tài khoản đã thay đổi từ khi ra quyết định.

Các mã lý do có thể gồm VALID_REGISTERED_AUTHENTICATOR, RECOVERY_CHANNEL_STABLE hoặc RECENT_RECOVERY_CHANGE. Phản hồi công khai không cần công bố toàn bộ các mã này, vì chúng có thể giúp kẻ tấn công suy ra điều kiện vận hành hoặc sự tồn tại của tài khoản.

Điểm rủi ro cũng không phải xác suất bị chiếm đoạt nếu hệ thống chưa hiệu chỉnh và đánh giá nó theo nghĩa xác suất. Ví dụ score=12 chỉ là giá trị trong mô hình nội bộ; không nên diễn giải thành “12% nguy cơ” khi chưa có cơ sở.

## 6. Token và quyền khôi phục giới hạn

OWASP khuyến nghị phản hồi nhất quán cho tài khoản tồn tại và không tồn tại, hạn chế yêu cầu tự động, đồng thời bảo vệ token đặt lại bằng tính ngẫu nhiên phù hợp, thời hạn và tính dùng một lần. Nhánh rủi ro thấp vẫn cần những kiểm soát nền này. [OWASP Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html)

Trong thiết kế minh họa, một token khôi phục dẫn đến một bản ghi máy chủ:

~~~text
RecoveryGrant
  grantId
  tokenDigest
  transactionId
  accountId
  allowedAction = RESET_PASSWORD
  expiresAt
  state = ISSUED | CONSUMED | REVOKED
  accountSecurityVersion
~~~

Token thô là bí mật mang quyền truy cập, cần được bảo vệ trong truyền tải và tránh xuất hiện trong log hoặc dữ liệu phân tích. Với token ngẫu nhiên có entropy cao, máy chủ có thể tra cứu bằng digest hoặc HMAC theo thiết kế lưu trữ đã chọn. Mã số ngắn cần thêm giới hạn số lần thử vì không gian tìm kiếm nhỏ hơn nhiều.

Quyền này chỉ cho phép đặt mật khẩu cho tài khoản đã ràng buộc. Nó không cho phép:

- Chọn lại accountId qua tham số do trình duyệt gửi.
- Thay email hoặc số điện thoại khôi phục.
- Vô hiệu hóa MFA hoặc thêm passkey mới.
- Đọc dữ liệu tài khoản, xuất dữ liệu hoặc tạo API key.
- Tự kéo dài thời hạn vì người dùng tải lại trang.

Khi dùng cookie cho phiên khôi phục giới hạn, cần tách phạm vi quyền khỏi phiên đăng nhập và áp dụng bảo vệ yêu cầu thay đổi trạng thái phù hợp, chẳng hạn chống CSRF. Khi dùng link email, việc mở trang không nên tự thực hiện thay đổi mật khẩu: trình quét link có thể truy cập URL trước người dùng.

Các thời hạn phải được chọn theo mô hình đe dọa và trải nghiệm của hệ thống. “Token còn hiệu lực 10 phút” có thể là một giá trị minh họa trong thiết kế, không phải thời hạn chung bắt buộc cho mọi hệ thống.

## 7. Đánh giá lại tại thời điểm thay đổi

Quyết định ban đầu có thể hết giá trị trước khi người dùng nhấn xác nhận. Trong khoảng đó, người dùng có thể báo mất thiết bị, hệ thống phát hiện xâm nhập hoặc dữ liệu khôi phục bị sửa từ một phiên khác.

Dưới đây là mã giả diễn tả thứ tự xử lý, không phải một triển khai hoàn chỉnh:

~~~text
completePasswordRecovery(rawToken, newPassword):
    validatePasswordPolicy(newPassword)
    preparedHash = passwordHasher.hash(newPassword)

    begin transaction
        grant = findGrantForUpdate(digest(rawToken))
        require grant exists
        require grant.state == ISSUED
        require currentTime < grant.expiresAt
        require grant.allowedAction == RESET_PASSWORD

        account = findAccountForUpdate(grant.accountId)
        require account.securityVersion == grant.accountSecurityVersion
        require account has no new blocking security event
        require required evidence remains valid

        set account.passwordHash = preparedHash
        increment account.securityVersion
        mark grant CONSUMED
        revoke other password-reset grants for account
        apply configured session invalidation
        append durable audit event
        append durable notification event
    commit transaction
~~~

Các kiểm tra khi hoàn tất phải dựa vào trạng thái máy chủ. Trình duyệt không được tự khai risk=LOW rồi yêu cầu backend bỏ qua xác minh.

Khóa bản ghi hoặc một phép cập nhật có điều kiện giúp tránh việc hai yêu cầu đồng thời sử dụng cùng quyền khôi phục. Cơ chế thực tế cần phù hợp với cơ sở dữ liệu; mục tiêu là chỉ một lần thay đổi có thể tiêu thụ grant.

Việc tính hash mật khẩu có thể thực hiện trước giao dịch ngắn, nhưng endpoint cần giới hạn tải để tránh bị khai thác tài nguyên. Không đưa tác vụ gửi email qua mạng vào giữa giao dịch giữ khóa. Có thể ghi một sự kiện outbox bền vững trong cùng giao dịch, sau đó xử lý gửi và retry bên ngoài.

Nếu dữ liệu tín hiệu nằm ngoài cơ sở dữ liệu giao dịch, cần cơ chế kiểm tra độ mới và phát hiện thay đổi phù hợp. Một trường phiên bản cục bộ không tự bao phủ mọi sự kiện từ hệ thống bên ngoài.

## 8. Session sau khôi phục

Đặt lại mật khẩu và kiểm soát session là hai phần của cùng kết quả bảo mật. Nếu session cũ vẫn có quyền hoạt động, thay mật khẩu chưa chắc đã cắt được đường truy cập của một tác nhân khác.

Chính sách minh họa trong bài chọn:

1. Hoàn tất thay mật khẩu và vô hiệu hóa các quyền đặt lại còn tồn đọng.
2. Thu hồi refresh token và các session theo phạm vi đã quy định.
3. Kết thúc phiên khôi phục giới hạn.
4. Yêu cầu người dùng đăng nhập lại với mật khẩu mới và MFA hiện hành.
5. Gửi thông báo về thay đổi qua kênh đã đăng ký phù hợp.

OWASP khuyến nghị người dùng đăng nhập qua cơ chế thông thường sau khi đặt mật khẩu, đồng thời xử lý việc vô hiệu hóa session hiện có. [OWASP, User Resets Password](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html#user-resets-password)

Đối với access token tự chứa, thu hồi refresh token chưa nhất thiết vô hiệu hóa ngay access token đã phát hành. Hệ thống phải xác định rõ cách thực thi thu hồi, chẳng hạn kiểm tra phiên bản bảo mật của tài khoản khi nhận yêu cầu, quản lý session phía máy chủ hoặc chấp nhận một cửa sổ hiệu lực được giới hạn và đã đánh giá.

Không cấp quyền bỏ qua MFA chỉ vì thao tác đặt mật khẩu thành công. Nếu người dùng đồng thời mất MFA, đó là một yêu cầu phục hồi khác với điều kiện riêng.

## 9. Ba tình huống làm rõ ranh giới

### Tình huống A: quên mật khẩu, vẫn giữ khóa bảo mật

Linh sử dụng trình duyệt quen và vẫn có khóa bảo mật đã đăng ký. Máy chủ xác minh khóa cho giao dịch hiện tại, không thấy thay đổi bảo mật đang tranh chấp và chính sách tài khoản cho phép nhánh tự phục vụ.

Hệ thống cấp quyền RESET_PASSWORD. Sau khi đổi mật khẩu, Linh đăng nhập lại qua quy trình yêu cầu MFA. Thiết bị quen hỗ trợ đánh giá; bằng chứng từ khóa và chính sách của hành động mới là cơ sở cho quyền được cấp.

### Tình huống B: IP quen nhưng mất toàn bộ phương thức

Nam dùng mạng gia đình nên địa chỉ IP trông bình thường. Nam không còn mật khẩu, mã khôi phục hay phương thức xác thực đã đăng ký.

IP quen không bù được bằng chứng còn thiếu. Hệ thống chuyển sang xác minh bổ sung. Quyết định này không tự khẳng định Nam là kẻ tấn công; nó phản ánh việc nhánh nhanh chưa có đủ cơ sở.

### Tình huống C: đang khôi phục thì có cảnh báo mới

Một yêu cầu ban đầu đủ điều kiện đặt lại mật khẩu. Trước khi hoàn tất, chủ tài khoản báo nghi ngờ bị chiếm quyền từ một kênh khác.

Hệ thống đánh dấu sự kiện bảo mật và thu hồi hoặc ngăn sử dụng quyền khôi phục đang chờ. Lần xác nhận tiếp theo phải kiểm tra trạng thái mới và chuyển sang quy trình xử lý tài khoản nghi bị xâm nhập. Không tiếp tục chỉ vì lần đánh giá trước đã trả về LOW.

## 10. Vận hành nhánh nhanh và xử lý sự cố

Nhánh tự phục vụ cần có giới hạn tốc độ ở nhiều chiều như tài khoản, nguồn yêu cầu, giao dịch và điểm xác minh. Giới hạn chỉ theo IP có thể bỏ sót tấn công phân tán hoặc gây khó cho nhiều người dùng chung mạng.

Khi dịch vụ email ngừng hoạt động, hệ thống không nên cho phép đổi mật khẩu mà không có bằng chứng chỉ để giữ tỷ lệ hoàn thành. Khi dịch vụ rủi ro không trả lời, hệ thống cần phân biệt dữ liệu bắt buộc với tín hiệu tùy chọn; dữ liệu bắt buộc chưa rõ phải dẫn tới chờ hoặc chuyển nhánh.

Các chỉ số hữu ích gồm:

- Tỷ lệ người dùng hợp lệ hoàn tất và thời gian hoàn tất.
- Tỷ lệ chuyển nhánh, phân theo nguyên nhân thay vì chỉ một tổng số.
- Số grant hết hạn, bị thu hồi hoặc bị sử dụng lại.
- Số báo cáo khôi phục trái phép sau khi giao dịch thành công.
- Mức độ chậm hoặc thiếu dữ liệu từ các dịch vụ cung cấp tín hiệu.

Tỷ lệ hoàn thành cao chưa đủ để chứng minh chính sách an toàn. Cần xem cùng báo cáo chiếm quyền, độ trễ phát hiện và tác động lên các nhóm người dùng có môi trường ít ổn định như mạng di động hoặc thiết bị dùng chung.

Lưu dữ liệu tín hiệu theo mục đích rõ ràng và giới hạn truy cập. Một nhánh khôi phục thuận tiện không cần thu thập vô hạn lịch sử thiết bị hay vị trí chính xác. Dữ liệu lưu trong log nên đủ để giải thích quyết định và điều tra sự cố, đồng thời tránh chứa bí mật có thể dùng để thực hiện khôi phục.

## 11. Bài tập thiết kế

Một tài khoản có email khôi phục đã xác minh, cookie thiết bị được tạo sáu tháng trước và bốn yêu cầu đặt lại mật khẩu trong thời gian ngắn. Người dùng yêu cầu thay mật khẩu và gỡ MFA vì vừa mất điện thoại.

Hãy xác định:

1. Cần tách yêu cầu thành những hành động bảo mật nào?
2. Tín hiệu nào là ngữ cảnh, bằng chứng nào có thể xác minh quyền khôi phục?
3. Cookie cũ có chứng minh người đang sử dụng là chủ tài khoản không?
4. Chính sách nào quyết định điều kiện được phục hồi MFA?
5. Nếu chỉ cho phép thay mật khẩu, backend cần chặn những quyền nào trong phiên khôi phục?
6. Khi có báo cáo chiếm quyền trước bước xác nhận, quyết định ban đầu cần thay đổi ra sao?

Một phương án thiết kế phù hợp phải chỉ rõ bằng chứng bắt buộc cho từng hành động, các điều kiện chuyển nhánh và cơ chế thực thi quyền ở máy chủ. Chỉ gắn nhãn “rủi ro thấp” cho toàn bộ yêu cầu chưa giải quyết được các câu hỏi đó.
