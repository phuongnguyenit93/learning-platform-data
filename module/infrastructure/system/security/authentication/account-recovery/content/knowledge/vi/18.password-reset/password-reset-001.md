# Điều kiện cho phép đặt lại mật khẩu

## 1. Điều kiện đặt lại mật khẩu là một quyết định cấp quyền

**Password reset eligibility** là tập điều kiện mà hệ thống phải kiểm tra trước khi cho phép thay mật khẩu qua luồng khôi phục. Quyết định này trả lời câu hỏi: với tài khoản, bằng chứng, trạng thái bảo mật và chính sách hiện tại, người đang yêu cầu có được đặt lại đúng thông tin xác thực đó hay không?

Trong chương **Password Reset**, cần phân biệt việc tiếp nhận một yêu cầu với việc thực sự cho đổi mật khẩu. Một biểu mẫu “Quên mật khẩu” có thể được mở cho mọi người, nhưng máy chủ không vì thế mà có nghĩa vụ cấp token hoặc thay mật khẩu cho mọi định danh được gửi lên.

Trong phạm vi `SECURITY_AUTHENTICATION_ACCOUNT_RECOVERY`, mục tiêu là khôi phục quyền truy cập khi người dùng mất mật khẩu, MFA, passkey hoặc thiết bị xác thực, đồng thời giảm nguy cơ chiếm đoạt tài khoản. Vì vậy, điều kiện đặt lại mật khẩu phải phối hợp với đánh giá rủi ro, xác minh danh tính, token dùng một lần, chống lạm dụng và kiểm soát phiên đăng nhập.

Một token hợp lệ là bằng chứng quan trọng, nhưng không phải lời hứa vô điều kiện rằng tài khoản luôn được đặt lại mật khẩu. Trong thời gian token còn hạn, tài khoản có thể bị đình chỉ, chuyển sang SSO bắt buộc, thay kênh khôi phục hoặc hoàn tất một lần đổi mật khẩu khác. Quyền thực hiện phải được kiểm tra lại tại thời điểm ghi thay đổi.

Ví dụ, An nhận liên kết đặt lại mật khẩu lúc 09:00. Lúc 09:03, tổ chức chuyển tài khoản của An sang cơ chế chỉ đăng nhập qua nhà cung cấp danh tính. Nếu An mở liên kết lúc 09:05, hệ thống không được tự tạo lại một đường mật khẩu cục bộ chỉ vì token chưa hết hạn.

Sau bài học, người học có thể xác định các điều kiện cần kiểm tra, thiết kế kết quả quyết định nội bộ, xử lý những trạng thái tài khoản khác nhau và bảo đảm rằng quyền đặt lại không vô tình trở thành quyền bỏ qua các cơ chế bảo vệ khác.

## 2. Xác định đúng thao tác đang được xin phép

Không phải mọi thao tác gán một mật khẩu mới đều là đặt lại mật khẩu.

| Thao tác | Bối cảnh | Điều kiện cần phân biệt |
|---|---|---|
| Đổi mật khẩu khi đang đăng nhập | Người dùng chủ động thay bí mật còn biết hoặc còn phương thức xác thực phù hợp | Cần xác thực lại cho hành động nhạy cảm theo chính sách |
| Đặt lại mật khẩu đã quên | Không dùng được mật khẩu hiện tại, cần một bằng chứng khôi phục khác | Không thể bắt buộc nhập đúng mật khẩu đã quên; phải có cơ chế xác minh thay thế đủ tin cậy |
| Đặt mật khẩu lần đầu | Tài khoản chưa có thông tin xác thực mật khẩu | Là đăng ký hoặc kích hoạt phương thức mới, không mặc nhiên là reset |
| Thêm mật khẩu vào tài khoản chỉ dùng passkey | Tạo thêm một đường xác thực | Cần chính sách đăng ký phương thức và đánh giá ảnh hưởng tới mức bảo vệ |
| Xử lý mất MFA hoặc thiết bị | Mật khẩu có thể vẫn còn nhưng thiếu yếu tố khác | Không được coi việc đổi mật khẩu là đã xác minh quyền bỏ MFA |
| Khôi phục tài khoản SSO | Nhà cung cấp danh tính quản lý mật khẩu | Cần đi đúng nơi có thẩm quyền quản lý thông tin xác thực |

Nếu hệ thống dùng chung một endpoint cho nhiều hành động, quyền được cấp vẫn phải có phạm vi rõ. Token cho `RESET_PASSWORD` không được dùng như token cho `DISABLE_MFA`, `CHANGE_RECOVERY_EMAIL` hoặc `REGISTER_PASSKEY`.

Tương tự, quyền đặt lại mật khẩu không có nghĩa tài khoản được đăng nhập ngay, được khôi phục mọi quyền ứng dụng hay được hủy một quyết định đình chỉ của tổ chức.

## 3. Có ba thời điểm phải đánh giá điều kiện

### 3.1. Tiếp nhận yêu cầu

Đây là lúc một người gửi định danh vào biểu mẫu quên mật khẩu. Người gửi có thể là chủ tài khoản, người gõ nhầm hoặc đối thủ. Hệ thống kiểm tra định dạng, giới hạn lạm dụng và tuyến xử lý, đồng thời tránh tiết lộ tài khoản có tồn tại hay không.

Kết quả công khai ở bước này chỉ nên xác nhận việc tiếp nhận theo cách trung tính. Nó không nên trở thành một API cho biết “địa chỉ này có mật khẩu cục bộ”, “tài khoản đang khóa” hoặc “MFA đang bật”.

### 3.2. Cấp thử thách hoặc bằng chứng khôi phục

Máy chủ xác định nội bộ rằng có một tài khoản phù hợp, cơ chế reset được hỗ trợ, chính sách cho phép mở luồng và có đường chuyển bằng chứng đáng tin cậy. Sau đó mới tạo token, gửi thử thách hoặc hướng người dùng sang một bước xác minh khác.

Việc gửi một liên kết tới kênh đã xác minh là một bước trong giao thức. Chỉ nhập địa chỉ email vào biểu mẫu chưa chứng minh người gửi kiểm soát hộp thư đó. Chính việc hoàn thành thử thách mới có thể cung cấp bằng chứng tương ứng.

### 3.3. Ghi mật khẩu mới

Trước khi ghi, cần xác minh bằng chứng, kiểm tra hiệu lực dùng một lần và đánh giá lại điều kiện tài khoản theo trạng thái hiện tại. Không dựa hoàn toàn vào quyết định từ lúc cấp token.

| Giai đoạn | Câu hỏi máy chủ phải trả lời | Điều chưa được suy ra |
|---|---|---|
| Tiếp nhận | Có thể xử lý yêu cầu này mà không bị lạm dụng không? | Người gửi là chủ tài khoản |
| Cấp bằng chứng | Có đường khôi phục được phép cho tài khoản này không? | Người gửi đã hoàn tất bằng chứng |
| Ghi thay đổi | Bằng chứng hiện tại có đủ quyền cho đúng thao tác không? | Mọi yếu tố khác hoặc mọi phiên đều đã được xử lý |

Một thiết kế có thể gọi các quyết định nội bộ là `canAcceptRequest`, `canIssueChallenge` và `canCommitReset`. Không gộp chúng thành một cờ `canReset` do máy khách quyết định.

## 4. Các nhóm điều kiện phải xét cùng nhau

### 4.1. Tài khoản và thông tin xác thực đích

Máy chủ cần xác định đúng tài khoản, đúng tenant nếu có và đúng thông tin xác thực do mình quản lý. Email giống nhau ở hai tổ chức không có nghĩa là cùng một chủ thể bảo mật.

Thông tin xác thực mật khẩu phải tồn tại hoặc hành động tạo mới phải được cho phép rõ ràng bởi một luồng khác. Không dùng endpoint reset để âm thầm thêm mật khẩu vào tài khoản chưa từng hỗ trợ phương thức này.

### 4.2. Trạng thái vòng đời

Trạng thái tài khoản cho biết có đang hoạt động, chờ kích hoạt, bị đình chỉ, đang xóa hay đã xóa. Mỗi trạng thái cần có chính sách reset cụ thể, không chỉ một phép kiểm tra `active == true` áp dụng cho mọi tình huống.

### 4.3. Kênh và bằng chứng khôi phục

Cần biết bằng chứng đến từ đâu, đã hoàn tất chưa, có còn hạn, gắn với tài khoản nào và có đủ cho hành động dự kiến không. Kênh vừa được thêm hoặc thay đổi có thể cần xử lý khác kênh đã được xác minh từ trước.

### 4.4. Chính sách xác thực và tổ chức

Chính sách có thể quy định chỉ dùng SSO, không cho reset tự phục vụ đối với một nhóm tài khoản, yêu cầu thêm bằng chứng hoặc chuyển tới quy trình quản trị. Các điều kiện này phải được thực thi ở máy chủ, kể cả khi giao diện không hiển thị nút quên mật khẩu.

### 4.5. Rủi ro và các lệnh chặn bảo mật

Một lệnh chặn sau sự cố, dấu hiệu kênh khôi phục bị chiếm hoặc thay đổi bảo mật đáng ngờ có thể làm bằng chứng thông thường không còn đủ. Tuy nhiên, rủi ro tăng không nhất thiết dẫn tới cấm vĩnh viễn; kết quả có thể là yêu cầu thêm bằng chứng, trì hoãn có kiểm soát hoặc chuyển tuyến.

### 4.6. Hiệu lực đồng thời

Ngay cả khi từng điều kiện từng đúng, cần bảo đảm chúng còn đúng khi ghi mật khẩu. Token đã dùng, phiên bản thông tin xác thực đã đổi hoặc chính sách mới có hiệu lực phải được nhìn thấy trước khi commit.

Một biểu thức khái niệm cho giai đoạn cuối là:

```text
allowCommitReset =
    đúng chủ thể và thông tin xác thực đích
    AND hành động reset được chính sách hiện tại hỗ trợ
    AND trạng thái vòng đời cho phép hành động đó
    AND không có lệnh chặn áp dụng cho hành động
    AND bằng chứng đủ mức, còn hạn và chưa dùng
    AND phiên bản ràng buộc vẫn khớp
    AND yêu cầu đạt điều kiện chống lạm dụng
```

Đây là một tập điều kiện bắt buộc. Không cộng một “điểm rủi ro thấp” để bù cho token đã dùng hoặc tài khoản không còn được phép có mật khẩu cục bộ.

## 5. Ma trận trạng thái tài khoản

Ma trận dưới đây là chính sách minh họa để thiết kế, không phải quy tắc bắt buộc cho mọi sản phẩm.

| Trạng thái | Hướng xử lý có thể phù hợp | Điều cần tránh |
|---|---|---|
| Đang hoạt động, có mật khẩu cục bộ | Cho mở luồng reset khi có kênh và bằng chứng phù hợp | Cho đổi mật khẩu chỉ từ việc biết định danh |
| Mật khẩu hết hạn | Có thể cho reset hoặc chuyển sang luồng cập nhật được phép | Nhầm hết hạn mật khẩu với tài khoản đã bị đình chỉ |
| Bị giới hạn đăng nhập do nhiều lần sai | Có thể vẫn cho khôi phục theo chính sách | Dùng khóa do người ngoài gây ra để chặn mọi cơ hội khôi phục của chủ tài khoản |
| Bị quản trị viên đình chỉ | Có thể chặn reset, hoặc cho đổi bí mật nhưng giữ đình chỉ, tùy chính sách | Tự bật lại quyền đăng nhập sau reset |
| Có lệnh chặn bảo mật do sự cố | Yêu cầu xử lý sự cố hoặc bằng chứng bổ sung theo lệnh chặn | Coi token được cấp trước lệnh chặn là ngoại lệ tự động |
| Chờ xác minh hoặc chờ kích hoạt | Chuyển sang quy trình kích hoạt phù hợp | Dùng reset để bỏ qua điều kiện đăng ký còn thiếu |
| Đang chờ xóa | Thực thi chính sách riêng về khôi phục và xóa | Âm thầm hủy yêu cầu xóa chỉ vì có yêu cầu quên mật khẩu |
| Đã xóa | Không reset một chủ thể đã kết thúc vòng đời | Tạo lại tài khoản hoặc khôi phục quyền từ token cũ |
| Chỉ dùng SSO | Định tuyến tới nơi quản lý thông tin xác thực theo chính sách | Tạo mật khẩu cục bộ để đi vòng qua SSO |
| Chỉ dùng passkey | Dùng luồng khôi phục hoặc đăng ký phương thức được phép | Biến quên mật khẩu thành cách thêm một mật khẩu không được chính sách cho phép |

Điểm cần phân biệt là **đủ điều kiện thay mật khẩu** và **đủ điều kiện đăng nhập**. Một tổ chức có thể muốn người đang bị đình chỉ thay bí mật đã lộ, trong khi vẫn không cho truy cập. Nếu sản phẩm hỗ trợ điều đó, hai quyết định phải được biểu diễn riêng, không dùng chung cờ trạng thái.

Các mã lý do trong ma trận phục vụ xử lý nội bộ. Không đưa nguyên trạng thái của một tài khoản vào phản hồi công khai của biểu mẫu quên mật khẩu.

## 6. Mật khẩu cục bộ, SSO, passkey và tài khoản hỗn hợp

### 6.1. Chỉ reset thông tin xác thực thuộc thẩm quyền của dịch vụ

Với tài khoản dùng nhà cung cấp danh tính, ứng dụng có thể chỉ giữ một bản ghi người dùng nội bộ mà không quản lý mật khẩu. Bản ghi đó không tạo ra quyền đặt mật khẩu cục bộ.

Nếu tổ chức bắt buộc SSO, một đường reset cục bộ còn sót có thể bỏ qua các chính sách tập trung của tổ chức. Hệ thống phải kiểm tra mô hình xác thực hiện hành ở phía máy chủ, không chỉ ẩn nút trên giao diện.

Việc tài khoản từng có mật khẩu cục bộ cũng chưa đủ. Cấu hình có thể đã chuyển sang SSO; token cũ không được làm sống lại phương thức đã bị vô hiệu hóa.

### 6.2. Tài khoản có nhiều phương thức cần quyết định theo từng phương thức

Một tài khoản có thể được phép dùng cả mật khẩu, passkey và SSO. Khi đó, phải xác định cụ thể phương thức mật khẩu có còn được bật và có được reset hay không. Không áp dụng quy tắc “có SSO thì luôn cấm reset” hoặc “có mật khẩu trong cơ sở dữ liệu thì luôn cho reset” cho mọi tài khoản hỗn hợp.

Nếu passkey còn dùng được, hệ thống có thể dùng nó làm bằng chứng xác thực lại theo chính sách. Nếu passkey bị mất, không được tự động giảm yêu cầu bằng chứng xuống chỉ còn biết email.

### 6.3. Một định danh có thể ánh xạ tới nhiều tài khoản

Trong hệ thống nhiều tenant, cùng một email có thể xuất hiện ở những tài khoản khác nhau. Luồng phải xác định tenant từ một ngữ cảnh đáng tin cậy hoặc có bước chọn tổ chức phù hợp, đồng thời tránh tiết lộ quan hệ thành viên cho người chưa có quyền biết.

Token cần gắn với chủ thể và thông tin xác thực đích đã được xác định. Không cho máy khách đổi `tenantId`, `accountId` hoặc địa chỉ nhận để chuyển quyền reset sang tài khoản khác.

## 7. Bằng chứng nào có thể làm người yêu cầu đủ điều kiện?

### 7.1. Kênh liên hệ không đồng nghĩa với quyền sở hữu

Một địa chỉ email trong hồ sơ có thể chưa được xác minh, đã cũ hoặc vừa bị thay đổi. Việc trường email không rỗng không đủ để coi nó là kênh khôi phục đáng tin cậy.

Máy chủ phải xác định kênh đã được đăng ký và được phép dùng cho khôi phục. Không nhận một địa chỉ bất kỳ trong request rồi gửi token tới đó chỉ vì người gửi nói không còn truy cập được email cũ.

Nếu cho thay kênh khi mất truy cập, đó là một luồng xác minh riêng. Cho đổi kênh trước rồi dùng ngay kênh mới làm bằng chứng reset có thể tạo một vòng tự xác nhận không có bằng chứng độc lập.

### 7.2. Bằng chứng phải phù hợp với rủi ro của hành động

| Bằng chứng hoặc tình huống | Giá trị có thể có | Giới hạn phải xem xét |
|---|---|---|
| Hoàn tất thử thách gửi tới email khôi phục đã được phép | Chứng minh khả năng nhận bằng chứng qua kênh đó tại thời điểm thực hiện | Không bảo đảm hộp thư chỉ do chủ tài khoản kiểm soát; mức tin cậy tùy mô hình đe dọa |
| Phương thức xác thực đã đăng ký còn sử dụng được | Có thể cung cấp bằng chứng mạnh để xác thực lại | Phải kiểm tra đúng chủ thể, độ mới và yêu cầu của phương thức |
| Mã dự phòng hợp lệ | Có thể hỗ trợ khôi phục theo phạm vi được cấp | Là bí mật dùng một lần; mã bị lộ cũng có thể bị đối thủ sử dụng |
| Phiên đang đăng nhập | Cho biết một trạng thái xác thực đã có | Cookie bị lấy cắp không tự chứng minh quyền thay mật khẩu |
| Thông tin tiểu sử hoặc câu hỏi bảo mật | Có thể là thông tin mà người yêu cầu cung cấp | Dễ được biết hoặc đoán; không mặc định đủ để thay yếu tố nhạy cảm |
| Quy trình hỗ trợ xác minh danh tính | Có thể xử lý trường hợp mất mọi phương thức | Cần tiêu chí, phân quyền, kiểm toán và kiểm soát giả mạo; nhân viên không tự bỏ qua chính sách |

Không có một bằng chứng áp dụng giống nhau cho mọi tài khoản. Tài khoản có quyền tác động lớn, kênh khôi phục vừa thay đổi hoặc sự cố đang diễn ra có thể cần điều kiện chặt hơn.

### 7.3. Mất mật khẩu và mất MFA là hai vấn đề khác nhau

Hệ thống có thể cho đặt lại mật khẩu bằng một kênh phù hợp trong khi vẫn yêu cầu MFA ở lần đăng nhập tiếp theo. Vì vậy, không nhất thiết phải có MFA còn hoạt động mới được reset mật khẩu trong mọi chính sách.

Nhưng nếu người dùng cũng mất MFA, hoàn tất reset mật khẩu chưa giải quyết xong quyền truy cập. Cần đưa họ tới luồng khôi phục MFA phù hợp; không tự tắt MFA để làm cho luồng mật khẩu có vẻ hoàn tất.

Nếu một chính sách yêu cầu thêm MFA trước khi reset do mức rủi ro, hệ thống phải có đường xử lý cho người thực sự mất yếu tố đó. Đường xử lý này cần xác minh tương xứng, không phải một nút bỏ qua điều kiện.

### 7.4. Không cho máy khách tự khai mức bằng chứng

Các trường như `emailVerified`, `mfaPassed`, `riskScore` hoặc `isOwner` từ máy khách không phải nguồn có thẩm quyền. Dịch vụ phải đọc kết quả xác minh được bảo vệ phía máy chủ hoặc kiểm tra một bằng chứng có chữ ký, phạm vi và cơ chế chống dùng lại phù hợp.

Tham chiếu tới một phiên khôi phục cũng không tự đủ. Máy chủ phải kiểm tra phiên đó đã hoàn tất những bước nào, có bị thu hồi và còn khớp với trạng thái tài khoản hay không.

## 8. Thiết kế kết quả quyết định nội bộ

Một cờ boolean thường không đủ để điều phối quy trình. Có thể dùng một tập kết quả nội bộ như sau:

| Kết quả | Ý nghĩa | Hướng xử lý |
|---|---|---|
| `ALLOW_CHALLENGE` | Đủ điều kiện mở thử thách khôi phục | Cấp bằng chứng theo kênh và phạm vi được phép |
| `REQUIRE_ADDITIONAL_PROOF` | Bằng chứng hiện có chưa đủ | Yêu cầu bước xác minh bổ sung được chính sách cho phép |
| `ROUTE_TO_IDENTITY_PROVIDER` | Dịch vụ không có thẩm quyền reset mật khẩu này | Chuyển sang luồng của nhà cung cấp danh tính theo ngữ cảnh được phép công khai |
| `ROUTE_TO_CONTROLLED_RECOVERY` | Không còn đường tự phục vụ phù hợp | Chuyển sang quy trình khôi phục có kiểm soát |
| `DEFER` | Tạm chưa cho thao tác, có điều kiện hoặc thời điểm xem xét lại | Trì hoãn có giới hạn và hướng dẫn phù hợp |
| `DENY` | Hành động không được hỗ trợ hoặc bị chặn bởi điều kiện bắt buộc | Không cấp quyền thực hiện |
| `ALLOW_COMMIT` | Đủ điều kiện ghi mật khẩu mới ở bước cuối | Chỉ thực hiện trong ranh giới kiểm tra và cập nhật nguyên tử |

Kết quả có thể đi kèm mã lý do, phiên bản chính sách, bằng chứng còn thiếu và điều kiện phiên sau reset. Không dùng kết quả `ALLOW_CHALLENGE` để bỏ qua việc đánh giá `ALLOW_COMMIT`.

Các quy tắc bắt buộc nên có thứ tự rõ ràng. Ví dụ, kiểm tra hành động được hỗ trợ và lệnh chặn trước khi xem rủi ro có thể giảm bằng bằng chứng bổ sung hay không. Không để một quy tắc “thiết bị quen thuộc” ghi đè lệnh chặn bảo mật.

Thông tin nào được hiển thị cho người dùng phải được quyết định riêng theo mức xác thực hiện có. Mã lý do nội bộ không nên tự động trở thành thông báo công khai.

## 9. Hợp đồng API không được làm lộ điều kiện tài khoản

### 9.1. Giao diện công khai chỉ tiếp nhận yêu cầu

Một hợp đồng minh họa:

```http
POST /password-reset/requests
Content-Type: application/json

{
  "loginIdentifier": "<dinh-danh-nguoi-dung>"
}
```

Phản hồi có thể dùng cùng một hình thức cho những định danh có định dạng hợp lệ:

```json
{
  "message": "Nếu có luồng khôi phục phù hợp, hướng dẫn sẽ được gửi qua kênh đã đăng ký."
}
```

Không trả các trường công khai như:

```text
accountExists = true
hasLocalPassword = false
accountSuspended = true
recoveryEmail = <dia-chi-day-du>
canReset = true
```

Sự khác biệt ở mã HTTP, cấu trúc body, thời gian xử lý hoặc hành vi giới hạn theo tài khoản có thể làm lộ thông tin dù câu chữ đã giống nhau. Cần thiết kế xử lý và phản hồi để giảm các khác biệt quan sát được; chỉ thêm một khoảng chờ cố định không bảo đảm giải quyết vấn đề.

Giới hạn nguồn truy cập có thể được thông báo theo chính sách, nhưng không nên làm lộ một tài khoản tồn tại chỉ vì riêng tài khoản đó đã đạt ngưỡng nội bộ. Có thể tiếp nhận bằng phản hồi trung tính trong khi chặn việc cấp thêm bằng chứng ở phía sau.

### 9.2. Không cho người chưa xác minh chọn đường yếu hơn

Máy khách có thể gửi ý định thao tác hoặc ngữ cảnh giao diện, nhưng không được tự chọn chính sách bảo mật. Những trường như `skipMfa`, `forceLocalPassword` hoặc `ignoreAccountLock` không được trở thành điều kiện cho phép.

Nếu hệ thống hiển thị hướng dẫn SSO theo tổ chức, cần bảo đảm ngữ cảnh tổ chức được phép công khai. Không tiết lộ một người là thành viên của tenant chỉ từ việc người ngoài nhập email của họ.

### 9.3. Mở liên kết không phải hoàn tất reset

Trình quét thư và trình duyệt có thể truy cập liên kết trước người dùng. Một yêu cầu `GET` không nên đổi mật khẩu, tự mở khóa tài khoản hoặc tiêu thụ quyền reset cuối cùng.

Thao tác ghi mật khẩu cần một yêu cầu thay đổi trạng thái rõ ràng, có bảo vệ phù hợp với cơ chế phiên và chống giả mạo yêu cầu. Token bí mật không được xuất hiện trong log, công cụ phân tích hoặc dữ liệu chuyển tới bên thứ ba của trang reset.

## 10. Token hợp lệ nhưng điều kiện có thể đã thay đổi

### 10.1. Gắn bằng chứng với đối tượng và phiên bản

Một bản ghi thử thách có thể gồm:

```text
password_reset_challenge:
  challenge_id
  token_verifier
  account_id
  tenant_id
  credential_id
  action = RESET_PASSWORD
  credential_version_at_issue
  recovery_epoch_at_issue
  recovery_channel_id
  recovery_channel_version_at_issue
  policy_version_at_issue
  issued_at
  expires_at
  consumed_at
```

Máy chủ chỉ lưu giá trị kiểm chứng của token theo thiết kế bảo vệ phù hợp, không đưa token rõ vào audit hoặc log. Token phải khó đoán, có hạn dùng và phạm vi cụ thể. Những thuộc tính trên là ví dụ mô hình dữ liệu, không phải tất cả đều phải gửi cho trình duyệt.

`policy_version_at_issue` hữu ích cho truy vết, nhưng quyết định cuối vẫn phải dùng chính sách hiện hành. Hệ thống có thể vô hiệu hóa token khi thay đổi chính sách liên quan hoặc yêu cầu thêm bước theo chính sách mới. Không mặc định mọi thay đổi cấu hình nhỏ đều phải chặn mọi token; cần nêu rõ quy tắc tương thích và thu hồi.

### 10.2. Những thay đổi cần đánh giá lại

- Mật khẩu đã được đổi hoặc reset bằng một luồng khác.
- Kênh khôi phục đã bị thay, bị thu hồi hoặc bị đánh dấu không đáng tin cậy.
- Tài khoản bị đình chỉ, kết thúc vòng đời hoặc đặt dưới lệnh chặn bảo mật.
- Chính sách chuyển sang SSO bắt buộc hoặc vô hiệu hóa phương thức mật khẩu.
- Bằng chứng trung gian hoặc phiên khôi phục đã bị thu hồi.
- Xuất hiện yêu cầu xác minh bổ sung áp dụng cho thao tác đang chờ.

Thời hạn token chỉ giới hạn thời gian sử dụng. Nó không thay thế kiểm tra các thay đổi trên.

### 10.3. Không dùng dữ liệu đọc trễ để cho phép ghi

Điều kiện cuối phải được kiểm tra trên nguồn có thẩm quyền và tính nhất quán phù hợp. Một cache còn giữ trạng thái “đang hoạt động” sau khi tài khoản đã bị chặn không được dùng để cho phép reset.

Nếu chính sách nằm ở một hệ thống khác, cần cơ chế phiên bản hoặc điều phối bảo đảm quyết định không bị sử dụng sau một thay đổi có hiệu lực. Không đánh giá một lần ở đầu request rồi ghi bất chấp phiên bản đã thay đổi.

## 11. Ranh giới giao dịch cho quyết định cuối

Luồng minh họa dưới đây tập trung vào điều kiện reset. Việc kiểm tra chất lượng mật khẩu, cách băm và bảo vệ tài nguyên cần được triển khai bằng cơ chế phù hợp của hệ thống.

```text
completePasswordReset(request):
    validateRequestShapeAndApplyAbuseControls(request)

    # Chỉ dùng token để tìm đúng thử thách; chưa cấp quyền ghi.
    challengeRef = locateAndPrecheckChallenge(request.token)
    validateNewPasswordPolicy(request.newPassword)

    # Tính toán tốn tài nguyên ngoài thời gian giữ khóa khi có thể.
    candidateHash = derivePasswordHash(request.newPassword)

    transaction:
        account = lockAccountSecurityState(challengeRef.accountId)
        credential = lockCredential(challengeRef.credentialId)
        challenge = lockChallenge(challengeRef.challengeId)

        verifyTokenAndChallengeAgain(challenge, request.token)
        require(challenge.action == RESET_PASSWORD)
        require(challenge belongs to account and credential)
        require(challenge is not expired and not consumed)
        require(challenge.credentialVersion == credential.version)
        require(challenge.recoveryEpoch == account.recoveryEpoch)
        requireRecoveryChannelBindingStillValid(challenge, account)

        policy = readAndGuardCurrentApplicablePolicy(account)
        evidence = loadCurrentVerifiedEvidence(challenge, account)
        decision = evaluateCommitEligibility(
            account, credential, policy, evidence,
            authoritativeServerTime()
        )
        require(decision == ALLOW_COMMIT)

        updatePasswordHash(credential, candidateHash)
        incrementCredentialVersion(credential)
        markChallengeConsumed(challenge)
        applyRequiredSessionRevocationState(decision, account)
        insertCommittedResetAuditAndNotificationOutbox(account)

    return completionWithoutAutomaticLogin()
```

Đây là mã giả, không phải một triển khai hoàn chỉnh. Bước kiểm tra ban đầu giúp tránh lãng phí tài nguyên cho token sai hiển nhiên; nó không thay kiểm tra lại dưới khóa. Thời hạn phải được kiểm tra sau khi chờ khóa, không chỉ trước đó.

Các luồng thay đổi liên quan, chẳng hạn đình chỉ tài khoản, thay phương thức xác thực hoặc đổi mật khẩu, cần dùng một cơ chế điều phối tương thích. Nếu chỉ luồng reset khóa dữ liệu nhưng luồng đặt lệnh chặn cập nhật không cùng quy tắc, vẫn có thể xảy ra quyết định dựa trên trạng thái cũ.

Nếu chính sách được quản lý bên ngoài cơ sở dữ liệu này, `readAndGuardCurrentApplicablePolicy` cần một cơ chế bảo đảm phiên bản phù hợp với điểm quyết định cuối. Gọi tên hàm như vậy không tự tạo tính nguyên tử giữa hai hệ thống.

### 11.1. Hai token cùng hợp lệ lúc đầu

Giả sử hai token được cấp cho cùng phiên bản mật khẩu. Khi token thứ nhất hoàn tất reset, phiên bản mật khẩu tăng. Token thứ hai phải bị từ chối vì không còn khớp, dù nó chưa hết hạn và chưa được dùng.

Cơ chế này tránh việc một liên kết cũ thay mật khẩu lần nữa sau khi chủ tài khoản đã hoàn tất khôi phục. Có thể thu hồi các thử thách còn lại bằng phiên bản hoặc cơ chế tương đương, thay vì chỉ đánh dấu riêng token vừa dùng.

### 11.2. Lệnh chặn và reset xảy ra đồng thời

Hệ thống cần xác định một thứ tự có thẩm quyền. Nếu lệnh chặn đã có hiệu lực trước điểm commit reset, quyết định phải phản ánh nó. Nếu reset hoàn tất trước, lệnh chặn sau đó vẫn cần áp dụng lên trạng thái và phiên theo chính sách.

Không thể giải quyết trường hợp này chỉ bằng cách kiểm tra `isBlocked` ở trang đầu tiên của quy trình.

### 11.3. Lỗi trước và sau commit

Nếu giao dịch thất bại trước commit, không được để mật khẩu đã đổi nhưng token chưa được tiêu thụ, hoặc ngược lại. Nếu commit thành công nhưng phản hồi mất, token có thể đã hết quyền dùng; giao diện cần hướng dẫn đăng nhập bằng mật khẩu mới hoặc bắt đầu khôi phục lại khi cần, không thực hiện reset lặp một cách mù quáng.

Thông báo thành công nên được phát từ sự kiện đã commit. Lỗi gửi email sau commit không phải lý do khôi phục mật khẩu cũ hoặc làm token sống lại.

## 12. Tác động tới MFA, passkey và phiên đăng nhập

### 12.1. Reset mật khẩu không nâng cấp bằng chứng đã có

Người vừa hoàn tất reset có quyền đối với hành động đã được xác minh. Không tự coi họ đã vượt qua MFA, chứng minh quyền thay email khôi phục hoặc được phép đăng ký phương thức mới.

Nếu một phiên khôi phục được dùng để đi tiếp, cần giữ nguồn gốc xác thực và phạm vi hạn chế của nó. Không xóa nhãn rủi ro chỉ vì đã gán mật khẩu mới.

### 12.2. Không tự động bỏ yếu tố còn lại

MFA và passkey đã đăng ký cần giữ hiệu lực theo chính sách riêng. Trong trường hợp thiết bị bị mất hoặc có dấu hiệu bị chiếm, cần luồng thu hồi hoặc thay thế phù hợp. Việc đổi mật khẩu không tự chứng minh mọi passkey đều bị mất hoặc mọi thiết bị đều còn an toàn.

Ví dụ, người mất điện thoại nhưng còn passkey trên thiết bị khác có thể vẫn có một đường chứng minh mạnh. Ngược lại, người chỉ nhận được email reset không mặc nhiên có quyền hủy passkey của chủ tài khoản.

### 12.3. Chính sách phiên phải có cơ chế thực thi

Một chính sách có thể yêu cầu kết thúc các phiên và refresh token liên quan sau reset, đặc biệt khi có dấu hiệu mật khẩu bị lộ. Phạm vi thu hồi cần được định nghĩa: tất cả phiên, chỉ một nhóm phiên hay các phiên bị đánh dấu rủi ro.

Nếu chọn tăng một phiên bản phiên trong cùng giao dịch, các nơi xác minh phiên phải thực sự kiểm tra phiên bản đó. Token tự chứa được chấp nhận độc lập ở dịch vụ khác không tự mất hiệu lực chỉ vì cơ sở dữ liệu đổi một cột.

Luồng minh họa trong bài không tự đăng nhập sau reset. Người dùng đăng nhập lại theo chính sách hiện tại, bao gồm MFA nếu còn được yêu cầu. Nếu sản phẩm chọn cấp phiên sau khôi phục, đó phải là quyết định xác thực riêng với mức bằng chứng và giới hạn quyền rõ ràng.

## 13. Chống lạm dụng mà không tước đường khôi phục hợp lệ

### 13.1. Không để yêu cầu của người ngoài thay đổi trạng thái tài khoản

Gửi yêu cầu quên mật khẩu chưa phải bằng chứng. Chỉ riêng hành động này không nên làm đổi mật khẩu, mở khóa đình chỉ, đăng xuất chủ tài khoản hoặc hủy mọi liên kết khôi phục trước đó.

Nếu mỗi yêu cầu mới đều vô hiệu hóa ngay token đang có, đối thủ có thể liên tục gửi yêu cầu để chủ tài khoản không hoàn tất được. Cần giới hạn phát hành và gửi thông báo, đồng thời chọn chính sách token đang hoạt động sao cho không tạo một cách gây khóa ngoài đơn giản.

Một lựa chọn là cho phép một số thử thách cùng tồn tại trong giới hạn chặt chẽ, nhưng khi một lần reset thành công thì phiên bản thông tin xác thực làm những thử thách cũ mất hiệu lực. Đây là lựa chọn thiết kế, cần phối hợp với hạn dùng và giới hạn gửi chứ không phải cho cấp token không giới hạn.

### 13.2. Xét lạm dụng trên nhiều phạm vi

Giới hạn có thể kết hợp theo tài khoản, nguồn truy cập, kênh gửi và quy trình khôi phục. Không chỉ dựa vào IP vì đối thủ có nhiều nguồn và nhiều người dùng có thể chung một mạng.

Các tín hiệu rủi ro giúp quyết định thêm bước hoặc trì hoãn, nhưng không nên cho phép một lượng yêu cầu sai do người ngoài tạo ra biến thành lệnh cấm khôi phục vĩnh viễn. Cần đường xử lý cho chủ tài khoản thực sự.

### 13.3. Hỗ trợ không phải ngoại lệ tùy ý

Nhân viên hỗ trợ không nên dựa vào việc biết tên, email hoặc thông tin dễ tìm để cấp mật khẩu mới. Một quy trình hỗ trợ cần có tiêu chí xác minh, phạm vi quyền, cơ chế kiểm toán và điều kiện chuyển cấp phù hợp với tác động của tài khoản.

Nếu có quyền quản trị thay mặt người dùng, cần tách rõ nó khỏi bằng chứng khôi phục của chủ tài khoản. Ghi nhận ai đã phê duyệt và theo chính sách nào; không tạo lịch sử sai rằng người dùng đã tự hoàn tất một thử thách mà thực tế họ chưa làm.

## 14. Ba tình huống áp dụng

### 14.1. Quên mật khẩu nhưng còn MFA

Mai có mật khẩu cục bộ, kênh khôi phục đã được phép và MFA trên thiết bị còn dùng được. Tài khoản đang hoạt động, không có lệnh chặn.

Hệ thống tiếp nhận yêu cầu bằng phản hồi trung tính, đánh giá điều kiện cấp thử thách và yêu cầu bằng chứng theo chính sách. Nếu chính sách của tài khoản cần thêm MFA, Mai hoàn tất bước đó. Trước khi ghi, máy chủ kiểm tra lại trạng thái, phạm vi token và các phiên bản liên quan.

Sau reset, MFA không bị tắt. Mai đăng nhập bằng mật khẩu mới và tiếp tục đáp ứng điều kiện xác thực hiện hành. Các phiên cũ được xử lý theo chính sách thu hồi đã định nghĩa.

### 14.2. Quên mật khẩu và mất cả điện thoại MFA

Nam có thể nhận email khôi phục nhưng không còn điện thoại. Nếu chính sách cho reset mật khẩu bằng bằng chứng qua email phù hợp, Nam có thể đổi mật khẩu mà vẫn chưa được đăng nhập vì thiếu MFA.

Hệ thống phải nói rõ bước mật khẩu đã hoàn tất và chuyển Nam tới luồng khôi phục MFA. Không tự tắt MFA để tránh một màn hình lỗi. Nếu chính sách yêu cầu thêm bằng chứng trước cả reset mật khẩu, Nam cần đi qua quy trình khôi phục tương ứng.

Trong cả hai trường hợp, “được reset mật khẩu” và “đã khôi phục đầy đủ quyền truy cập” là hai kết luận khác nhau.

### 14.3. Token được cấp trước khi tài khoản chuyển sang SSO

Linh nhận token khi tài khoản còn được phép dùng mật khẩu cục bộ. Trước khi Linh gửi mật khẩu mới, tổ chức bật chính sách chỉ dùng SSO.

Ở bước commit, máy chủ thấy phương thức đích không còn đủ điều kiện và không ghi mật khẩu. Token cũ không được tạo ngoại lệ. Hướng dẫn công khai cần phù hợp với ngữ cảnh đã xác minh; hệ thống có thể chuyển Linh sang tuyến đăng nhập tổ chức mà không công khai trạng thái thành viên cho người ngoài.

Audit ghi nhận việc từ chối theo chính sách hiện hành và phiên bản liên quan, không ghi token hoặc mật khẩu mới.

## 15. Các tình huống kiểm chứng và hồ sơ quyết định

### 15.1. Tiêu chí hành vi

| Tình huống | Kết quả mong đợi |
|---|---|
| Định danh không tồn tại | Không đổi dữ liệu, không tiết lộ kết quả tra cứu qua phản hồi công khai |
| Có tài khoản nhưng không hỗ trợ mật khẩu cục bộ | Không tự tạo phương thức mới bằng endpoint reset |
| Tài khoản hỗn hợp có mật khẩu được phép reset | Đánh giá đúng phương thức và chính sách, không cấm chỉ vì tài khoản cũng có SSO |
| Tài khoản đang đình chỉ | Không tự hủy đình chỉ sau reset; thực thi chính sách riêng cho việc đổi bí mật |
| Tài khoản chờ kích hoạt | Không dùng reset để bỏ qua điều kiện kích hoạt còn thiếu |
| Kênh nhận do người gửi tùy ý cung cấp | Không dùng làm đích nhận quyền khôi phục nếu chưa qua luồng xác minh phù hợp |
| Token đúng nhưng đã hết hạn hoặc đã dùng | Không cho ghi mật khẩu |
| Token thuộc tài khoản hoặc tenant khác | Không cho chuyển chủ thể bằng tham số từ máy khách |
| Mật khẩu đã được đổi sau lúc cấp token | Token cũ không còn quyền thay lại mật khẩu |
| Kênh khôi phục bị thu hồi sau lúc cấp token | Đánh giá lại ràng buộc và từ chối hoặc yêu cầu thêm bằng chứng theo chính sách |
| Chính sách chuyển sang SSO bắt buộc | Token cũ không khôi phục đường mật khẩu cục bộ |
| Hai yêu cầu hoàn tất reset chạy đồng thời | Chỉ thao tác còn đáp ứng điều kiện phiên bản được commit |
| Lệnh chặn có hiệu lực trước điểm ghi | Quyết định cuối phản ánh lệnh chặn trên nguồn có thẩm quyền |
| Mất MFA nhưng bằng chứng reset mật khẩu đã đủ | Không tự tắt MFA; xử lý phần khôi phục yếu tố riêng |
| Chỉ nhận được yêu cầu quên mật khẩu | Không đăng xuất chủ tài khoản hoặc tự thu hồi mọi khả năng khôi phục |
| Lỗi ghi trước commit | Không có trạng thái mật khẩu đã đổi nhưng token vẫn dùng lại được |
| Lỗi thông báo sau commit | Không phục hồi mật khẩu cũ hoặc làm token sống lại |
| Token đã mở bởi trình quét liên kết | Chưa tự đổi mật khẩu, mở khóa hoặc hoàn tất quyền reset |

Đây là các tình huống để người triển khai kiểm chứng thiết kế. Chúng không phải kết quả thử nghiệm của một hệ thống cụ thể.

### 15.2. Ghi lại quyết định đủ để giải thích, không ghi bí mật

Một bản ghi nội bộ có thể gồm:

```text
event_type = PASSWORD_RESET_ELIGIBILITY_DECIDED
account_id hoặc tham chiếu nội bộ phù hợp
tenant_id
action = RESET_PASSWORD
phase = ISSUE_CHALLENGE hoặc COMMIT_RESET
decision
internal_reason_code
policy_version
credential_version
evidence_type
operation_id
timestamp
```

Không ghi mật khẩu cũ, mật khẩu mới, token rõ, cookie phiên hoặc toàn bộ bằng chứng nhạy cảm. Quyền đọc mã lý do nội bộ và thời gian lưu cũng cần được kiểm soát vì trạng thái tài khoản là thông tin có giá trị.

Hồ sơ quyết định nên giúp trả lời: ai hoặc quy trình nào xin quyền, cho thông tin xác thực nào, bằng bằng chứng nào, dưới chính sách nào và tại thời điểm nào. Điều kiện đặt lại mật khẩu chỉ hoàn chỉnh khi quyết định đó được ràng buộc với thao tác thực tế, không mở rộng sang quyền khôi phục khác và không tiếp tục có hiệu lực sau khi trạng thái bảo mật đã thay đổi.
