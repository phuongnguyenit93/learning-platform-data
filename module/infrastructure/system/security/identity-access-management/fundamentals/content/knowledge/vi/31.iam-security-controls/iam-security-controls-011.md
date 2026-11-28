# Protect recovery flow

## 1. Khôi phục tài khoản là một đường cấp lại quyền kiểm soát

Một hệ thống có thể dùng mật khẩu tốt, MFA và phương thức chống phishing nhưng vẫn bị chiếm tài khoản qua nút “Quên mật khẩu”. Nếu quy trình khôi phục cho phép người không đủ bằng chứng đổi mật khẩu, bỏ MFA hoặc gắn bộ xác thực mới, những lớp bảo vệ lúc đăng nhập sẽ bị đi vòng.

**Protect recovery flow** là bảo vệ toàn bộ quá trình lấy lại quyền truy cập khi người dùng mất hoặc không sử dụng được phương thức xác thực hiện tại. Mục tiêu là giúp đúng chủ thể khôi phục tài khoản, đồng thời ngăn người khác lợi dụng quy trình để chiếm quyền kiểm soát.

Các trường hợp thường gặp gồm:

- Quên mật khẩu nhưng vẫn kiểm soát phương thức xác thực khác.
- Mất điện thoại, khóa bảo mật hoặc bộ xác thực.
- Không còn truy cập được email hoặc số điện thoại đã đăng ký.
- Nghi tài khoản bị chiếm và cần thay thông tin xác thực.
- Cần hỗ trợ thủ công vì không còn phương thức tự phục vụ hợp lệ.

Mỗi trường hợp có bằng chứng và mức rủi ro khác nhau. Không nên gom tất cả thành một thao tác “gửi đường dẫn qua email rồi mở toàn bộ tài khoản”.

## 2. Phân biệt các thao tác khôi phục

| Thao tác | Điều được thay đổi | Điều không nên tự động suy ra |
| --- | --- | --- |
| Đặt lại mật khẩu | Bí mật đăng nhập dựa trên mật khẩu | Người dùng đã được phép bỏ qua MFA |
| Khôi phục một yếu tố | Khả năng sử dụng một phương thức xác thực | Được thêm mọi phương thức mà không kiểm tra |
| Đổi địa chỉ khôi phục | Nơi nhận bằng chứng hoặc thông báo về sau | Địa chỉ mới chứng minh quyền sở hữu tài khoản cũ |
| Khôi phục toàn tài khoản | Khả năng thiết lập lại quyền kiểm soát theo chính sách | Được khôi phục mọi quyền nghiệp vụ trước đây |
| Xử lý tài khoản bị chiếm | Thông tin xác thực, phiên và các thay đổi liên quan | Đổi mật khẩu là đủ để chấm dứt mọi truy cập của kẻ tấn công |

Một token đặt lại mật khẩu chỉ nên cho phép đúng mục đích đó. Nếu người dùng còn phải đáp ứng MFA để đăng nhập, việc đặt lại mật khẩu không tự biến thành một phiên đã hoàn thành MFA.

Tương tự, khôi phục quyền đăng nhập không phải một quy trình cấp lại vai trò quản trị đã bị thu hồi. Sau khôi phục, quyền truy cập tài nguyên vẫn phải được đánh giá theo trạng thái hiện tại.

## 3. Mô hình nguy cơ của recovery flow

Các đường lạm dụng cần được tính đến bao gồm:

- Thử địa chỉ hoặc tên tài khoản để xác định ai đã đăng ký.
- Gửi nhiều yêu cầu khôi phục để gây phiền nhiễu hoặc làm gián đoạn người dùng.
- Đoán, đánh cắp, phát lại hoặc sử dụng đồng thời token khôi phục.
- Chiếm hộp thư hoặc số điện thoại được dùng làm đường khôi phục.
- Dùng một phiên bị chiếm để thay kênh khôi phục hoặc thêm MFA của kẻ tấn công.
- Thuyết phục helpdesk bỏ MFA dựa vào thông tin công khai hoặc áp lực thời gian.
- Lợi dụng liên kết sai tài khoản, sai tenant hoặc sai mục đích.
- Giữ lại phiên, token hoặc phương thức xác thực đã có sau khi nạn nhân đặt lại mật khẩu.

Quy trình cần có câu trả lời cho cả kẻ tấn công chưa biết gì về tài khoản và người đã kiểm soát một phần thông tin của nạn nhân. Việc biết mật khẩu cũ hoặc đọc được một email không luôn đủ để thực hiện mọi thay đổi bảo mật.

## 4. Thiết kế luồng theo từng trạng thái

Một luồng tự phục vụ có thể được chia như sau:

```text
Yêu cầu khôi phục
        |
        v
Tiếp nhận và kiểm soát lạm dụng
        |
        v
Phát bằng chứng qua phương thức đã được liên kết hợp lệ
        |
        v
Xác minh bằng chứng + tài khoản + mục đích + hiệu lực
        |
        v
Cho phép đúng thao tác khôi phục giới hạn
        |
        v
Ghi thay đổi + tiêu thụ bằng chứng + xử lý phiên liên quan
        |
        v
Thông báo, kiểm toán và quay lại luồng truy cập phù hợp
```

Trạng thái “đã gửi yêu cầu” chưa có nghĩa người gửi là chủ tài khoản. Chỉ gửi email khôi phục không nên tự đổi mật khẩu, xóa MFA hoặc kết thúc mọi phiên đang hoạt động; nếu không, người ngoài có thể gây gián đoạn chỉ bằng việc biết địa chỉ tài khoản.

Trạng thái “đã xác minh một token khôi phục” cũng không nhất thiết là “đã có phiên ứng dụng đầy đủ”. Có thể cấp một phiên khôi phục ngắn hạn, chỉ cho phép thao tác được xác định, rồi yêu cầu đăng nhập theo chính sách sau khi hoàn tất.

Điều này giúp tránh việc token phục vụ một thao tác nhỏ bị biến thành quyền truy cập toàn bộ ứng dụng.

## 5. Tiếp nhận yêu cầu mà không tiết lộ hoặc gây gián đoạn

### 5.1. Phản hồi không xác nhận tài khoản không cần thiết

Một thông báo chung có thể là:

> Nếu tài khoản phù hợp tồn tại và đủ điều kiện, hướng dẫn khôi phục sẽ được gửi qua phương thức đã đăng ký.

Không nên trả tên, trạng thái tài khoản, địa chỉ đầy đủ hoặc danh sách yếu tố MFA cho bất kỳ người gọi chưa xác minh nào. Nội dung phản hồi, mã lỗi và những khác biệt thời gian dễ nhận biết đều cần được xem xét trong thiết kế chống dò tài khoản.

Phản hồi chung không có nghĩa phải giả rằng thao tác gửi đã thành công ở mọi tình huống nội bộ. Hệ thống vẫn cần quan sát lỗi và trạng thái xử lý để vận hành, nhưng không đưa chi tiết nhạy cảm đó ra cho người gọi chưa có quyền.

### 5.2. Kiểm soát tần suất theo nhiều chiều

Giới hạn có thể xét theo tài khoản hoặc định danh yêu cầu, nguồn kết nối và dấu hiệu lạm dụng khác. Chỉ giới hạn theo IP có thể không đủ với nguồn phân tán, đồng thời có thể ảnh hưởng nhiều người cùng dùng NAT.

Không thiết kế việc khóa tài khoản một cách dễ bị kích hoạt chỉ từ các yêu cầu khôi phục bên ngoài. Cần phân biệt kiểm soát việc gửi, kiểm soát thử bằng chứng và trạng thái tài khoản thật.

Khi có nhiều yêu cầu, phải định nghĩa hiệu lực của các token. Có thể chọn chỉ giữ một số yêu cầu hợp lệ hoặc dùng phiên bản khôi phục để kiểm soát, nhưng cần hiểu tác động: vô hiệu hóa token cũ sau mỗi yêu cầu mới có thể bị lợi dụng để cản người dùng hoàn tất. Chính sách phải cân bằng việc hạn chế bằng chứng tồn đọng với khả năng phục hồi thực tế.

## 6. Token khôi phục phải là một quyền hạn giới hạn

Một token khôi phục là bằng chứng nhạy cảm: ai kiểm soát nó có thể được phép thực hiện thao tác tương ứng. Token cần có độ ngẫu nhiên phù hợp, được sinh bằng bộ sinh số ngẫu nhiên mật mã và khó đoán trong thời gian còn hiệu lực.

Một bản ghi phía server có thể chứa:

```text
recoveryRequestId
tokenDigest
accountId
tenantOrIdentityScope
purpose = password-reset
issuedAt
expiresAt
consumedAt
recoveryVersion
```

Đây là mô hình minh họa. Các trường cần được diễn giải cùng nguồn danh tính và phạm vi tài khoản của hệ thống.

Những ràng buộc quan trọng gồm:

- **Đúng tài khoản:** token đã phát cho A không được dùng để thay mật khẩu B bằng cách đổi một tham số.
- **Đúng mục đích:** token xác minh email hoặc đặt lại mật khẩu không được dùng để tắt MFA hay cấp quyền quản trị.
- **Có thời hạn:** khoảng hiệu lực phù hợp với độ nhạy và cách giao nhận, không tồn tại vô thời hạn.
- **Dùng một lần:** khi hoàn tất, bằng chứng không tiếp tục cho phép lặp lại thay đổi.
- **Có thể vô hiệu hóa:** hệ thống có thể thu hồi yêu cầu hoặc làm mất hiệu lực các bằng chứng liên quan khi cần.
- **Bảo vệ tại nơi lưu:** không lưu và ghi log token bản rõ nếu không cần; với token ngẫu nhiên có độ mạnh phù hợp, có thể lưu digest hoặc giá trị kiểm tra được bảo vệ theo thiết kế.

Token tự chứa không tự có tính dùng một lần chỉ vì có chữ ký và thời hạn. Nếu muốn kiểm soát việc đã sử dụng hoặc thu hồi trước hạn, cần trạng thái hay cơ chế tương đương để thực thi điều đó.

Không gửi token đến địa chỉ do người gọi tùy ý cung cấp thay cho kênh đã được liên kết hợp lệ. Một địa chỉ mới chỉ chứng minh người gọi kiểm soát địa chỉ mới sau khi xác minh, không chứng minh họ sở hữu tài khoản cũ.

## 7. Bảo vệ đường dẫn và việc sử dụng token

Đường dẫn khôi phục nên được xây dựng từ địa chỉ ứng dụng đã cấu hình hoặc nguồn được kiểm soát. Không lấy tùy ý giá trị `Host`, tham số redirect hoặc URL do người gọi gửi để quyết định nơi đặt token.

Ví dụ cấu trúc liên kết:

```text
https://accounts.example/reset?token=<opaque-recovery-token>
```

Đây là địa chỉ minh họa. Token trên URL có thể xuất hiện ở lịch sử, hệ thống giám sát, proxy hoặc các nơi khác tùy cấu hình, nên cần kiểm soát những đường phát tán đó. Trang khôi phục không nên đưa token sang nội dung bên thứ ba hoặc ghi nguyên URL nhạy cảm vào log.

Cũng cần tính đến việc công cụ kiểm tra email, xem trước liên kết hoặc trình duyệt có thể mở URL trước người dùng. Không đặt lại mật khẩu hoặc tiêu thụ bằng chứng chỉ vì có một yêu cầu GET đến liên kết.

Việc thực hiện thay đổi cần một bước xác nhận rõ ràng, phương thức request phù hợp và kiểm tra bằng chứng ở phía server. Với các luồng có session/cookie, còn phải bảo vệ khỏi yêu cầu giả mạo và liên kết thao tác với đúng giao dịch; không giả định có cookie nghĩa là người dùng chủ động yêu cầu thay đổi.

Nếu đổi token lấy một phiên khôi phục hạn chế, phiên đó cần có thời hạn và quyền giới hạn. Bằng chứng hoặc phiên khôi phục không nên được chấp nhận ở những API nghiệp vụ không thuộc quy trình.

## 8. Tiêu thụ token và cập nhật thông tin xác thực phải nhất quán

Một lỗi phổ biến là kiểm tra token chưa dùng, cập nhật mật khẩu rồi mới đánh dấu đã dùng bằng một bước độc lập. Hai request đồng thời có thể cùng vượt qua lần kiểm tra ban đầu.

Cần có cơ chế nguyên tử hoặc kiểm soát đồng thời tương đương để chỉ một thao tác hoàn tất hợp lệ. Ví dụ mã giả:

```text
resetPassword(rawToken, newPassword):
    enforceRecoveryAttemptLimits()
    digest = recoveryTokenDigest(rawToken)
    request = recoveryRequests.findByDigest(digest)
    require request exists

    validateNewPasswordPolicy(newPassword)
    passwordHash = passwordHasher.hash(newPassword)

    transaction:
        current = recoveryRequests.lockAndReload(request.id)
        account = accounts.lockAndReload(current.accountId)

        require current.purpose == "password-reset"
        require current.consumedAt is null
        require current.expiresAt > trustedCurrentTime()
        require current.recoveryVersion == account.recoveryVersion
        require account.isEligibleForThisRecovery

        accounts.replacePasswordHash(account.id, passwordHash)
        recoveryRequests.markConsumed(current.id)
        accounts.advanceRecoveryVersion(account.id)
        securityActions.recordRequiredFollowUp(account.id)

    return RECOVERY_CHANGE_COMMITTED
```

Đây là mã giả, không phải triển khai hoàn chỉnh. Các bản ghi phải được liên kết đúng phạm vi; cần có kiểm tra hợp lệ phù hợp trước công việc tốn tài nguyên và kiểm tra lại mọi điều kiện có thể thay đổi tại điểm ghi. Giá trị `passwordHash` phải được tạo bằng cơ chế lưu mật khẩu phù hợp.

Trong ví dụ, tăng `recoveryVersion` làm các bằng chứng đang dùng phiên bản cũ không còn được chấp nhận. Một hệ thống có thể dùng cách khác, nhưng phải có quy tắc rõ về các yêu cầu còn tồn tại sau khi khôi phục thành công.

Nếu xử lý phiên hoặc thu hồi token ở hệ thống khác, một giao dịch cơ sở dữ liệu cục bộ không tự bao phủ toàn bộ việc đó. Cần lưu công việc tiếp nối một cách bền vững, thử lại khi lỗi và theo dõi trạng thái. Không báo “mọi phiên đã bị thu hồi” chỉ vì đã ghi yêu cầu thu hồi vào hàng đợi.

## 9. Bảo vệ khôi phục MFA và đổi kênh khôi phục

### 9.1. Tránh biến đặt lại mật khẩu thành bỏ MFA

Người quên mật khẩu nhưng còn một yếu tố khác có thể đi theo luồng khác người đã mất mọi phương thức. Không tự động xóa MFA chỉ vì hoàn tất bước đặt lại mật khẩu.

Khi người dùng báo mất bộ xác thực, cần xác minh bằng phương thức dự phòng hoặc quy trình khôi phục đáp ứng chính sách. Nếu chỉ gửi một liên kết đến hộp thư đang bị chiếm rồi tắt toàn bộ MFA, kẻ tấn công có thể dùng chính đường đó để vượt lớp bảo vệ.

Một mã dự phòng dùng một lần cần được bảo vệ, theo dõi trạng thái tiêu thụ và không lặp lại tác dụng nếu có request đồng thời. Nếu mã đã lộ, phải có cách vô hiệu hóa và cấp lại theo quy trình phù hợp.

### 9.2. Đổi email hoặc số điện thoại là thay đổi bảo mật

Một phiên đã đăng nhập nhưng không đủ mức hoặc không đủ mới không nên tùy ý thay kênh khôi phục. Cần xác thực lại hoặc bằng chứng bổ sung phù hợp trước khi liên kết kênh mới.

Xác minh email mới giúp chứng minh khả năng nhận thư tại địa chỉ đó. Nó không thay thế việc xác minh người đang yêu cầu đổi là chủ thể được phép thay đổi tài khoản.

Thông báo qua kênh cũ hoặc kênh độc lập có thể giúp phát hiện thay đổi trái phép. Tuy nhiên, thông báo sau sự kiện không phải bằng chứng cho phép trước sự kiện; kênh cũ cũng có thể đã bị mất hoặc bị chiếm. Nếu sử dụng thời gian chờ, giới hạn tạm thời hoặc hủy thay đổi, phải có quy tắc rõ và kiểm tra được hiệu lực.

### 9.3. Có phương thức dự phòng nhưng không mở đường yếu tùy ý

Phương thức dự phòng giúp phục hồi khi mất thiết bị, nhưng cần được đánh giá như một đường truy cập thật. Mức bảo vệ tổng thể có thể bị chi phối bởi đường thay thế dễ bị lạm dụng nhất.

Với tài khoản đặc quyền, có thể cần thêm người duyệt độc lập, xác minh chặt hơn hoặc giới hạn quyền trong giai đoạn khôi phục. Không cho người dùng tự dùng hai tài khoản của mình để tạo vẻ ngoài của sự phê duyệt độc lập.

## 10. Helpdesk, tài khoản liên kết và danh tính workload

### 10.1. Khôi phục qua người hỗ trợ

Helpdesk cần biết phạm vi được phép làm, bằng chứng phải thu thập, khi nào chuyển cấp và ai phê duyệt. Sự khẩn cấp, chức danh cao hoặc việc người gọi biết thông tin nội bộ không tự thay thế bằng chứng sở hữu tài khoản.

Không dùng ngày sinh, địa chỉ công khai hoặc tên người quản lý làm căn cứ duy nhất. Việc xác minh phải phù hợp với quan hệ và dữ liệu mà tổ chức thực sự quản lý, đồng thời chỉ thu thập dữ liệu cần thiết.

Các thao tác nhạy cảm cần được ghi nhận theo người thực hiện. Nhân viên hỗ trợ không cần biết mật khẩu mới hoặc giữ mã MFA của người dùng để hoàn tất quy trình.

### 10.2. Tài khoản SSO hoặc liên kết danh tính

Nếu ứng dụng dựa vào một nhà cung cấp danh tính bên ngoài, cần xác định nơi sở hữu phương thức xác thực và nơi có quyền khôi phục. Một ứng dụng không nên tạo đường mật khẩu cục bộ mới chỉ để đi vòng chính sách của bên cung cấp danh tính mà không có mô hình đã phê duyệt.

Liên kết lại tài khoản sau khôi phục cũng phải giữ đúng định danh và tenant. Trùng email hoặc tên hiển thị không đủ để tự gộp hai chủ thể hoặc chuyển quyền giữa các nguồn danh tính.

### 10.3. Danh tính workload

Với service hoặc pipeline, mất bí mật thường dẫn đến quy trình xoay vòng, cấp lại hoặc thu hồi thông tin xác thực dựa trên danh tính workload và hạ tầng quản lý. Không nên dùng hộp thư cá nhân hay tài khoản admin của một nhân viên làm đường khôi phục mặc định cho mọi dịch vụ.

Khi cấp lại, cần xác định workload nào còn hợp lệ, bí mật cũ còn tác dụng ở đâu và quyền mới có đúng phạm vi cần thiết không.

## 11. Xử lý sau khi khôi phục thành công

Sau một thay đổi đã được xác minh, hệ thống cần áp dụng chính sách xử lý những quyền truy cập còn tồn tại. Phạm vi có thể gồm:

- Phiên cục bộ của ứng dụng và phiên liên quan ở hệ thống danh tính.
- Access token, refresh token và những cơ chế gia hạn khác.
- Bộ xác thực cũ, mã dự phòng và yêu cầu khôi phục còn hiệu lực.
- Khóa hoặc thông tin xác thực khác được gắn vào tài khoản trong thời gian nghi ngờ.
- Thay đổi kênh khôi phục, quyền hoặc thông tin bảo mật cần rà soát.

Tài khoản bị chiếm cần cách xử lý khác một lần quên mật khẩu thông thường. Không mặc định tất cả phiên phải giữ nguyên, cũng không mặc định thay mật khẩu tự kết thúc chúng. Phải có chính sách và cơ chế thực thi tương ứng.

Đặc biệt, token tự chứa còn hạn có thể tiếp tục được tài nguyên chấp nhận nếu nơi đó không có cơ chế cập nhật trạng thái hoặc thu hồi bổ sung. Cần kiểm chứng thời gian chặn thực tế, không chỉ kiểm tra trang đăng nhập đã từ chối mật khẩu cũ.

Thông báo hoàn tất cần đủ để người dùng nhận ra thay đổi và biết cách báo cáo nếu không phải họ thực hiện. Không gửi mật khẩu mới hoặc token bí mật trong thông báo.

## 12. Kiểm toán và tình huống kiểm chứng

Nhật ký nên cho phép truy từ yêu cầu khôi phục đến thay đổi đã thực hiện và tác vụ tiếp nối. Những trường thường hữu ích gồm định danh yêu cầu, tài khoản và phạm vi, mục đích, nguồn bằng chứng, kết quả, thời điểm, người hỗ trợ nếu có và mã tương quan.

Không ghi token thô, mật khẩu, mã dự phòng hoặc dữ liệu xác minh nhạy cảm không cần thiết vào log. Quyền xem bằng chứng và nhật ký khôi phục cũng phải được giới hạn.

| Tình huống | Điều cần xác nhận |
| --- | --- |
| Yêu cầu cho tài khoản tồn tại và không tồn tại | Không dễ suy ra thông tin tài khoản từ phản hồi ngoài ý muốn |
| Gửi nhiều yêu cầu cho một nạn nhân | Không tự đổi thông tin xác thực hoặc khóa mọi phiên chỉ vì khởi tạo yêu cầu |
| Đổi account ID hoặc tenant đi kèm token | Token chỉ tác động đúng tài khoản và phạm vi đã liên kết |
| Dùng token sai mục đích | Không thể dùng token đặt lại mật khẩu để bỏ MFA hoặc cấp quyền |
| Token hết hạn hoặc đã tiêu thụ | Không còn cho phép thay đổi |
| Hai request dùng cùng token đồng thời | Chỉ thao tác hợp lệ duy nhất được hoàn tất |
| Công cụ quét email mở liên kết trước người dùng | Không tự thay đổi tài khoản hoặc tiêu thụ token chỉ vì GET |
| Client cung cấp host hoặc redirect tùy ý | Token không bị đưa sang địa chỉ do người gọi điều khiển |
| Phiên cũ yêu cầu đổi kênh khôi phục | Bị yêu cầu đáp ứng đúng điều kiện bảo mật |
| Người đã mất vai trò admin khôi phục đăng nhập | Không tự lấy lại vai trò đã bị thu hồi |
| Thu hồi phiên ở hệ thống khác bị lỗi | Có trạng thái, thử lại và kiểm chứng; không báo hoàn tất sai |
| Người gọi helpdesk gây áp lực nhưng thiếu bằng chứng | Quy trình không bị bỏ qua vì yếu tố xã hội |

Recovery flow được bảo vệ khi mỗi bước giữ đúng ranh giới: tiếp nhận chưa phải xác minh, token chỉ cho phép đúng thao tác, thay đổi được ghi nhất quán và quyền truy cập còn tồn tại được xử lý có bằng chứng. Khả năng phục hồi phải phục vụ chủ tài khoản mà không trở thành con đường dễ hơn để người khác chiếm tài khoản đó.
