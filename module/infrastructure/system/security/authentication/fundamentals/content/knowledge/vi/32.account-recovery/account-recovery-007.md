# Recovery notification

> **Chương:** Account recovery  
> **Module:** SECURITY_AUTHENTICATION_FUNDAMENTALS  
> **Trọng tâm:** Thông báo an toàn cho người dùng về các sự kiện khôi phục tài khoản, lựa chọn kênh liên hệ đã xác minh, hạn chế lộ thông tin và cung cấp cách phản ứng khi có yêu cầu khôi phục trái phép.

## 1. Recovery notification là gì?

**Recovery notification (thông báo khôi phục tài khoản)** là thông điệp bảo mật được gửi khi có sự kiện quan trọng trong quy trình khôi phục quyền truy cập, chẳng hạn bắt đầu yêu cầu khôi phục, hoàn tất đặt lại credential, thay đổi phương thức khôi phục hoặc thu hồi phiên sau khi khôi phục.

Mục tiêu của thông báo là giúp chủ tài khoản nhận biết hoạt động liên quan đến tài khoản, phát hiện yêu cầu không do mình khởi tạo và biết cách phản ứng qua kênh chính thức. Thông báo cũng tạo dấu vết vận hành để hệ thống và đội hỗ trợ điều tra sự cố.

Ví dụ, người dùng mất điện thoại và bắt đầu khôi phục tài khoản bằng recovery code. Hệ thống gửi cảnh báo đến địa chỉ email đã xác minh từ trước, thông báo rằng quy trình khôi phục đã bắt đầu và hướng dẫn cách báo cáo nếu họ không thực hiện yêu cầu. Sau khi khôi phục thành công, hệ thống gửi thông báo thứ hai, nêu các thay đổi bảo mật quan trọng và khuyến nghị kiểm tra thiết bị/phiên đang hoạt động.

Thông báo không phải bằng chứng rằng người nhận là chủ tài khoản, cũng không phải một bước phê duyệt khôi phục trừ khi giao thức được thiết kế rõ ràng như vậy. Người có quyền truy cập hộp thư hoặc số điện thoại có thể không phải chủ tài khoản; kênh liên hệ có thể bị chiếm, chuyển tiếp hoặc dùng chung.

### Kết quả học tập

Sau bài này, người học có thể:

- Xác định các sự kiện recovery cần gửi thông báo.
- Phân biệt thông báo bắt đầu, đang chờ, hoàn tất, thất bại và thay đổi bảo mật.
- Chọn kênh đã xác minh trước đó và xử lý trường hợp kênh vừa bị thay đổi.
- Thiết kế nội dung không tiết lộ quá nhiều dữ liệu hoặc sự tồn tại của tài khoản.
- Cung cấp đường báo cáo hoạt động trái phép mà không biến email thành credential.
- Xử lý thông báo bị trễ, gửi trùng, thất bại hoặc đến sai người.
- Liên kết notification với session revocation, credential replacement và audit.

## 2. Vì sao thông báo là một phần của account recovery?

Khôi phục tài khoản là một thời điểm rủi ro cao. Người dùng có thể đã mất thiết bị, mất credential hoặc không còn truy cập được kênh xác thực chính. Kẻ tấn công cũng có thể lợi dụng quy trình này để chiếm tài khoản bằng social engineering, SIM swap, email compromise hoặc khai thác hỗ trợ khách hàng.

Thông báo giúp giảm thời gian phát hiện sự cố. Nếu một yêu cầu khôi phục không do chủ tài khoản thực hiện, họ có thể phản ứng trước khi kẻ tấn công thay credential, thêm phương thức khôi phục hoặc tạo session mới.

Một thiết kế tốt phải trả lời:

- Sự kiện nào cần thông báo và ở thời điểm nào?
- Gửi tới kênh nào, và kênh đó được xác minh từ khi nào?
- Thông báo chứa bao nhiêu thông tin để người dùng nhận biết nhưng không giúp attacker?
- Người nhận có thể báo cáo hoặc yêu cầu trợ giúp bằng cách nào?
- Nếu thông báo không gửi được thì recovery có tiếp tục không?
- Làm sao tránh gửi thông báo đến địa chỉ vừa được attacker thêm vào?

### Thông báo không thay thế kiểm soát recovery

Email cảnh báo không chứng minh yêu cầu khôi phục là hợp lệ. SMS gửi mã cũng không tự chứng minh người nhận là chủ tài khoản nếu số điện thoại vừa bị chiếm. Quy trình recovery vẫn phải kiểm tra bằng chứng, chính sách và rủi ro; notification là lớp nhận biết và phản ứng bổ sung.

## 3. Các sự kiện nên thông báo

Không phải mọi lần người dùng mở trang recovery đều cần gửi cảnh báo. Hãy chọn sự kiện có ý nghĩa bảo mật, tránh gửi quá nhiều thông báo khiến người dùng bỏ qua cảnh báo thật.

| Sự kiện | Thời điểm gửi | Mục tiêu |
|---|---|---|
| Recovery request được tiếp nhận | Sau khi hệ thống ghi nhận yêu cầu | Báo người dùng có quy trình khôi phục đang diễn ra |
| Recovery cần thêm bằng chứng | Khi chuyển sang trạng thái chờ | Giải thích rằng chưa có thay đổi credential |
| Recovery được chấp thuận | Khi quyết định chấp thuận đã được ghi nhận | Báo trước hoặc thông báo việc hoàn tất theo chính sách |
| Credential được đặt lại | Sau khi cập nhật thành công | Cảnh báo thay đổi phương thức đăng nhập |
| Recovery method được thêm/thay đổi | Sau khi thay đổi có hiệu lực | Giúp phát hiện thay đổi email/điện thoại hoặc yếu tố dự phòng trái phép |
| Recovery thất bại hoặc bị từ chối | Khi kết quả có ý nghĩa với chủ tài khoản | Báo có hoạt động đáng chú ý và cung cấp đường hỗ trợ |
| Session/token bị thu hồi | Sau khi thu hồi hoặc khi quy trình kết thúc | Giải thích vì sao người dùng phải đăng nhập lại |
| Tài khoản được mở khóa | Sau khi trạng thái thay đổi | Báo tài khoản có thể truy cập lại |
| Recovery bị hủy | Khi người dùng hoặc hệ thống hủy yêu cầu | Xác nhận trạng thái đã kết thúc |
| Có yêu cầu recovery lặp bất thường | Khi đạt ngưỡng cảnh báo phù hợp | Báo nguy cơ lạm dụng mà không tiết lộ logic phát hiện |

### Tách các mốc thời gian

Một quy trình có thể kéo dài nhiều giờ hoặc nhiều ngày. Không dùng một thông báo duy nhất cho mọi trạng thái. Cần phân biệt:

1. **Received:** hệ thống đã nhận yêu cầu.
2. **Pending:** yêu cầu đang chờ bằng chứng, kiểm tra hoặc thời gian chờ.
3. **Approved:** yêu cầu đã được chấp thuận theo chính sách.
4. **Completed:** credential/trạng thái tài khoản đã thực sự thay đổi.
5. **Rejected/Expired/Cancelled:** yêu cầu không hoàn tất.

Thông báo “đã nhận yêu cầu” không được diễn đạt như “tài khoản đã khôi phục”. Thông báo “đã chấp thuận” cũng không đồng nghĩa credential mới đã được thiết lập thành công.

## 4. Chọn kênh nhận thông báo

Kênh nhận notification nên được xác minh trước sự kiện recovery và độc lập hợp lý với kênh đang được dùng để khôi phục. Không nên mặc định gửi cảnh báo tới địa chỉ email hoặc số điện thoại vừa được cung cấp trong chính yêu cầu recovery.

### Các kênh thường gặp

| Kênh | Ưu điểm | Rủi ro/giới hạn |
|---|---|---|
| Email đã xác minh trước đó | Có thể chứa hướng dẫn và thông tin hỗ trợ | Hộp thư có thể bị chiếm, chuyển tiếp hoặc dùng chung |
| SMS tới số đã xác minh trước đó | Nhanh, phổ biến | SIM swap, chuyển số, mất điện thoại và độ tin cậy thấp hơn trong một số threat model |
| Push notification trên ứng dụng đã đăng ký | Có thể gắn với thiết bị/phiên ứng dụng | Push token có thể cũ, thiết bị bị mất hoặc ứng dụng không còn cài |
| Thông báo trong ứng dụng | Có ngữ cảnh và lịch sử rõ | Chỉ hữu ích nếu người dùng còn truy cập một phiên an toàn |
| Kênh hỗ trợ đã xác minh | Hữu ích cho quy trình thủ công hoặc rủi ro cao | Có thể bị social engineering hoặc quá tải |

### Ưu tiên kênh đã có trước recovery

Ví dụ, nếu người dùng yêu cầu đổi email khôi phục từ A sang B, thông báo bảo mật nên được gửi tới A đã xác minh trước đó, ít nhất trong giai đoạn chuyển tiếp theo chính sách. Gửi chỉ tới B sẽ cho phép attacker vừa thay kênh vừa kiểm soát thông báo về thay đổi đó.

Nếu mọi kênh cũ đều không còn truy cập được, không tự động tin kênh mới chỉ vì người yêu cầu nhập được địa chỉ hoặc số điện thoại. Cần dùng quy trình xác minh thay thế, thời gian chờ và kiểm soát rủi ro phù hợp.

### Kênh dự phòng và độc lập

Hai địa chỉ email chuyển tiếp về cùng một hộp thư không phải hai kênh độc lập. SMS và email trên cùng một điện thoại bị chiếm cũng có thể cùng thất bại. Đánh giá sự độc lập theo khả năng một sự cố đơn lẻ làm attacker kiểm soát nhiều kênh.

## 5. Nội dung thông báo an toàn

Một recovery notification nên đủ cụ thể để người dùng nhận ra sự kiện, nhưng không tiết lộ bí mật, dữ liệu định danh quá mức hoặc chi tiết giúp attacker điều chỉnh tấn công.

Thông tin thường hữu ích:

- Tên dịch vụ/tổ chức gửi thông báo.
- Loại sự kiện: yêu cầu recovery, thay đổi credential hoặc hoàn tất khôi phục.
- Thời điểm gần đúng và múi giờ rõ ràng.
- Trạng thái hiện tại: đã nhận, đang chờ, hoàn tất hoặc bị hủy.
- Một phần thông tin ngữ cảnh không nhạy cảm nếu thực sự cần, chẳng hạn loại thiết bị hoặc khu vực gần đúng.
- Hướng dẫn truy cập ứng dụng/website chính thức để xem chi tiết.
- Cách báo cáo nếu người nhận không thực hiện yêu cầu.
- Kênh hỗ trợ chính thức và mã tham chiếu không mang quyền truy cập.

Không nên đưa vào notification:

- Mật khẩu, recovery code, OTP hoặc token.
- Toàn bộ mã định danh cá nhân, số giấy tờ hoặc dữ liệu proofing.
- Session ID, access token, refresh token hoặc device marker.
- Câu trả lời recovery secret hoặc chi tiết bằng chứng đã nộp.
- URL chứa credential hoặc token có thể dùng để hoàn tất recovery.
- Thông tin về tài khoản khác hoặc dữ liệu nội bộ không cần thiết.

### Mã tham chiếu không phải bí mật xác thực

Một mã tham chiếu có thể giúp đội hỗ trợ tìm sự kiện trong audit log. Mã này không được dùng như recovery code, không cấp quyền xem dữ liệu nhạy cảm và không thay thế xác minh người liên hệ.

### Thông báo cho đúng đối tượng

Nếu email có thể được chia sẻ hoặc chuyển tiếp, tránh hiển thị thông tin chi tiết như số tài khoản đầy đủ, địa chỉ nhà hoặc tên pháp lý nếu không cần. Dùng nội dung trung tính và yêu cầu người dùng đăng nhập vào ứng dụng chính thức để xem chi tiết sau khi xác thực.

## 6. Mẫu notification

### Khi nhận yêu cầu recovery

~~~text
Tiêu đề: Có yêu cầu khôi phục tài khoản

Chúng tôi đã nhận được yêu cầu khôi phục quyền truy cập tài khoản của bạn
vào lúc 14:32 ngày 22/11.

Yêu cầu đang được xử lý. Tài khoản và phương thức đăng nhập hiện tại
chưa được thay đổi chỉ vì thông báo này.

Nếu bạn không thực hiện yêu cầu, hãy mở ứng dụng hoặc website chính thức
bằng cách tự nhập địa chỉ, sau đó chọn mục Bảo mật để báo cáo hoạt động
không nhận ra. Bạn cũng có thể liên hệ bộ phận hỗ trợ qua kênh được công bố
trong ứng dụng.

Chúng tôi sẽ không yêu cầu bạn gửi mật khẩu, OTP hoặc recovery code qua email.
~~~

### Khi recovery hoàn tất

~~~text
Tiêu đề: Tài khoản đã được khôi phục

Quy trình khôi phục tài khoản của bạn đã hoàn tất vào lúc 15:05 ngày 22/11.
Một phương thức đăng nhập đã được cập nhật theo yêu cầu.

Nếu bạn thực hiện thay đổi này, hãy đăng nhập qua ứng dụng chính thức và
kiểm tra danh sách thiết bị, phiên đang hoạt động cùng các phương thức
khôi phục đã đăng ký.

Nếu bạn không thực hiện yêu cầu, hãy báo cáo ngay qua kênh hỗ trợ chính thức
để chúng tôi có thể bảo vệ tài khoản và thu hồi các phiên liên quan.
~~~

Đây là mẫu minh họa. Thay nội dung trong từng trường hợp theo trạng thái thực tế; không nói credential đã thay đổi nếu thao tác chưa thành công.

## 7. Không biến notification thành đường dẫn phishing

Email hoặc SMS về recovery là mục tiêu hấp dẫn cho phishing. Kẻ tấn công có thể gửi thông báo giả, chèn link tới website nhái hoặc yêu cầu người dùng trả lời bằng OTP.

Thiết kế notification của tổ chức nên:

- Dùng tên người gửi và domain nhất quán, dễ nhận biết.
- Không yêu cầu người dùng trả lời email bằng mật khẩu, OTP hoặc recovery code.
- Ưu tiên hướng dẫn người dùng tự mở ứng dụng/website chính thức.
- Nếu có link, dùng domain chính thức, HTTPS và tránh URL rút gọn hoặc redirect không kiểm soát.
- Không đặt token recovery dài hạn trong query string hoặc fragment.
- Không dùng thông báo khẩn cấp giả tạo để ép người dùng thao tác vội.
- Nêu rõ tổ chức không yêu cầu gửi secret qua email/SMS.

### Link hành động có thể nguy hiểm

Một link “Hủy recovery” hoặc “Đây không phải tôi” có thể hữu ích, nhưng nếu link mang bearer token có quyền hủy hoặc thay đổi recovery thì ai có được email cũng có thể thao tác. Cần cân nhắc:

- Đưa người dùng đến trang chính thức rồi yêu cầu xác thực phù hợp.
- Ràng buộc thao tác với session và CSRF protection.
- Dùng token một lần, thời hạn ngắn và phạm vi rất hẹp nếu thực sự cần link hành động.
- Không cho link notification tự động hoàn tất đăng nhập hoặc đổi credential.
- Có phương án hỗ trợ nếu người dùng đã mất quyền truy cập tất cả kênh cũ.

Thông báo có thể mở đường dẫn trợ giúp, nhưng bản thân việc mở email không được xem là xác thực.

## 8. Hướng dẫn phản ứng khi người dùng không nhận ra yêu cầu

Một cảnh báo chỉ hữu ích nếu người nhận biết phải làm gì. Hướng dẫn nên ngắn, nhất quán và có thể thực hiện ngay.

Các bước phản ứng có thể gồm:

1. Không nhấp vào link lạ hoặc trả lời bằng OTP/recovery code.
2. Tự mở ứng dụng/website chính thức bằng bookmark hoặc địa chỉ đã biết.
3. Nếu còn đăng nhập, xem trạng thái recovery và danh sách session/thiết bị.
4. Báo cáo yêu cầu không nhận ra qua chức năng bảo mật hoặc hỗ trợ chính thức.
5. Nếu có bằng chứng tài khoản bị chiếm, yêu cầu thu hồi session/token và credential liên quan.
6. Kiểm tra email/điện thoại khôi phục, passkey, MFA và thiết bị mới được thêm.
7. Đổi credential hoặc re-proof theo hướng dẫn từ kênh hỗ trợ đã xác minh.

Không yêu cầu người dùng tự điều tra IP hoặc xác định chính xác vị trí. Những dữ liệu đó có thể không chính xác và dễ gây nhầm lẫn.

### Nút báo cáo không phải nút phê duyệt

Một thao tác “Không phải tôi” có thể gửi tín hiệu để hệ thống đánh giá hoặc tạm giữ recovery. Nó không nên lập tức khóa vĩnh viễn tài khoản chỉ từ một cú nhấp chưa xác minh, vì attacker có thể lạm dụng chức năng để gây từ chối dịch vụ. Hãy xác minh người báo cáo và áp dụng chính sách phản ứng có tỷ lệ.

## 9. Notification trong các giai đoạn recovery

### Trước khi thay đổi credential

Khi yêu cầu mới được tiếp nhận, thông báo tới kênh đã xác minh trước đó giúp người dùng biết quy trình đã bắt đầu. Nếu recovery có thời gian chờ, nêu trạng thái và thời điểm dự kiến theo chính sách, nhưng không tiết lộ chi tiết kiểm tra chống gian lận.

### Trong thời gian chờ

Nếu cần thêm bằng chứng hoặc có cooldown, thông báo nên làm rõ tài khoản chưa được khôi phục và người dùng có thể làm gì tiếp theo. Không gửi nhiều thông báo lặp cho mỗi lần backend retry.

### Khi recovery hoàn tất

Thông báo nên nêu thay đổi đã thực sự có hiệu lực, chẳng hạn credential được đặt lại hoặc phương thức recovery được cập nhật. Nếu một số bước chưa hoàn tất, diễn đạt trạng thái một phần.

### Sau khi recovery hoàn tất

Hệ thống có thể:

- Thu hồi các session cũ theo chính sách.
- Vô hiệu hóa recovery code đã sử dụng.
- Đánh dấu credential bị mất hoặc bị nghi lộ là revoked.
- Yêu cầu đăng ký lại MFA/passkey nếu cần.
- Áp dụng thời gian chờ trước hành động có giá trị cao.
- Gửi cảnh báo riêng khi thêm kênh recovery hoặc authenticator mới.

Notification cần phản ánh đúng các hành động đã thực hiện. Không tuyên bố mọi session đã bị thu hồi nếu một RP offline hoặc token tự chứa vẫn còn hiệu lực.

## 10. Xử lý thay đổi kênh liên hệ

Thay đổi email hoặc số điện thoại là sự kiện nhạy cảm vì các kênh này có thể được dùng cho notification và recovery.

Một quy trình an toàn có thể:

1. Xác thực người yêu cầu bằng phương thức hiện có phù hợp.
2. Xác minh kênh mới theo quy trình riêng.
3. Thông báo tới kênh cũ đã xác minh trước đó.
4. Áp dụng cooldown hoặc giới hạn hành động nhạy cảm nếu rủi ro cao.
5. Cho phép người dùng báo cáo thay đổi không mong muốn.
6. Chỉ chuyển kênh chính sau khi mọi điều kiện đã đạt.
7. Ghi audit về thời điểm, nguồn và kết quả.

Nếu kênh cũ không còn truy cập được, không thể gửi notification tới đó. Khi ấy phải dùng quy trình thay thế có assurance phù hợp và ghi rõ giới hạn. Không để việc thiếu notification tự động làm recovery thất bại trong mọi trường hợp; cũng không dùng kênh mới chưa xác minh làm bằng chứng duy nhất.

## 11. Chống lạm dụng và bảo vệ quyền riêng tư

Notification có thể bị lợi dụng để spam, gây hoảng sợ hoặc dò xem một tài khoản có tồn tại. Kẻ tấn công có thể gửi hàng nghìn yêu cầu recovery để làm ngập email/SMS hoặc đánh lạc hướng chủ tài khoản.

### Rate limit và gộp thông báo

- Giới hạn số yêu cầu recovery theo tài khoản, nguồn và khoảng thời gian.
- Gộp các sự kiện tương tự trong một cửa sổ ngắn nếu không làm mất thông tin quan trọng.
- Dùng cooldown và backoff cho việc gửi lại.
- Phân biệt retry kỹ thuật với yêu cầu recovery mới.
- Giám sát chi phí SMS/email và dấu hiệu abuse.
- Không để endpoint notification trở thành dịch vụ gửi tin nhắn tùy ý.

### Tránh account enumeration

Phản hồi công khai của recovery endpoint nên có nội dung và thời gian xử lý tương đối nhất quán để attacker khó xác định email/số điện thoại có tài khoản hay không. Notification chỉ được gửi sau khi hệ thống đã áp dụng chính sách phù hợp; không tiết lộ cho người khởi tạo rằng địa chỉ đích có phải kênh đã đăng ký hay không.

Ví dụ, giao diện có thể nói “Nếu thông tin phù hợp với tài khoản, chúng tôi sẽ gửi hướng dẫn qua kênh đã đăng ký” thay vì xác nhận một địa chỉ cụ thể tồn tại trong hệ thống.

### Nội dung tối thiểu

Không đưa tên đầy đủ, email/số điện thoại hoàn chỉnh, dữ liệu định danh, lịch sử đăng nhập chi tiết hoặc trạng thái tài khoản nhạy cảm vào thông báo nếu không cần. Có thể che một phần kênh nhận, nhưng phải cân nhắc để người dùng vẫn nhận ra đó là kênh của họ.

### Phân quyền và lưu trữ

- Chỉ dịch vụ notification được phép đọc dữ liệu cần thiết để gửi.
- Không ghi OTP, recovery code hoặc token vào log.
- Bảo vệ template và cấu hình người gửi khỏi bị sửa bởi người không có quyền.
- Giới hạn retention của nội dung và metadata gửi nhận.
- Kiểm soát truy cập vào lịch sử thông báo và audit.
- Xử lý dữ liệu nhà cung cấp email/SMS theo chính sách và nghĩa vụ áp dụng.

## 12. Độ tin cậy của việc gửi và nhận

Gửi request tới nhà cung cấp không đồng nghĩa người dùng đã nhận hoặc đọc thông báo. Cần phân biệt các trạng thái:

| Trạng thái | Ý nghĩa |
|---|---|
| Queued | Hệ thống đã đưa thông báo vào hàng đợi |
| Submitted | Đã gửi yêu cầu tới nhà cung cấp |
| Accepted | Nhà cung cấp chấp nhận xử lý |
| Delivered | Nhà cung cấp báo đã chuyển tới đích theo khả năng của kênh |
| Opened/read | Có tín hiệu mở/đọc, nhưng không chứng minh đúng chủ tài khoản đã xem |
| Bounced/failed | Gửi thất bại hoặc đích không nhận được |
| Suppressed | Bị chặn bởi chính sách, rate limit hoặc trạng thái kênh |

Email open tracking có thể không chính xác do proxy ảnh, privacy protection hoặc hệ thống quét tự động. SMS delivery receipt cũng không chứng minh người nhận hợp pháp đã đọc. Không dùng trạng thái opened làm bằng chứng xác thực hoặc phê duyệt recovery.

### Gửi lại và chống trùng

Notification service nên có event ID/idempotency key để retry không tạo nhiều cảnh báo giống nhau. Tuy nhiên, các sự kiện có ý nghĩa khác nhau như “yêu cầu bắt đầu” và “credential đã thay đổi” cần thông báo riêng.

Nếu provider timeout, hệ thống có thể không biết thông báo đã được gửi hay chưa. Dùng idempotency và trạng thái delivery để giảm gửi trùng; tránh retry vô hạn.

### Khi gửi thất bại

Quy trình recovery cần có chính sách:

- Thử lại có giới hạn qua cùng kênh.
- Dùng kênh dự phòng đã xác minh nếu được phép.
- Ghi trạng thái notification failure để hỗ trợ điều tra.
- Không tiết lộ thông tin qua kênh mới chưa xác minh.
- Với recovery rủi ro cao, cân nhắc giữ trạng thái pending hoặc yêu cầu bước xác minh khác.

Không phải mọi notification failure đều phải hủy recovery. Quyết định phụ thuộc mức assurance, khả năng cảnh báo thay thế và hậu quả nếu người dùng không nhận được cảnh báo.

## 13. Thiết kế notification event và audit

Nên tách sự kiện bảo mật khỏi nội dung gửi đi. Recovery service tạo một event có cấu trúc; notification service chọn template và kênh theo chính sách.

~~~mermaid
flowchart LR
    R["Recovery service"] --> E["Recovery event"]
    E --> P["Notification policy"]
    P --> C["Verified channel registry"]
    C --> Q["Notification queue"]
    Q --> V["Email / SMS / Push provider"]
    V --> D["Delivery status"]
    D --> A["Audit and monitoring"]
    P --> A
~~~

### Trường sự kiện minh họa

| Trường | Mục đích |
|---|---|
| **event_id** | Định danh sự kiện để chống xử lý trùng |
| **account_ref** | Tham chiếu nội bộ đã được bảo vệ |
| **event_type** | recovery.started, recovery.completed, recovery.cancelled... |
| **occurred_at** | Thời điểm sự kiện |
| **correlation_id** | Liên kết các bước trong cùng recovery flow |
| **channel_ref** | Tham chiếu kênh nhận đã xác minh |
| **template_version** | Phiên bản nội dung đã dùng |
| **delivery_state** | Trạng thái gửi/nhận từ provider |
| **policy_version** | Phiên bản quy tắc notification |

Không đưa recovery code, token, mật khẩu, raw email nếu không cần hoặc nội dung bằng chứng proofing vào event. Dùng tham chiếu nội bộ và kiểm soát quyền truy cập.

### Audit cần trả lời được

- Sự kiện recovery nào đã kích hoạt notification?
- Chính sách nào chọn kênh và template?
- Kênh đó đã được xác minh khi nào?
- Provider đã nhận yêu cầu gửi và trả trạng thái gì?
- Có retry, suppression hoặc lỗi nào?
- Người dùng đã báo cáo hoạt động trái phép chưa?
- Những hành động bảo vệ tài khoản nào được thực hiện tiếp theo?

Audit phải hỗ trợ điều tra nhưng không trở thành kho bí mật xác thực. Không ghi nguyên văn token hoặc mã dùng một lần.

## 14. Tình huống thực hành: recovery request không do chủ tài khoản khởi tạo

**Bối cảnh:** Một tài khoản nhân viên có email công việc đã xác minh và số điện thoại dự phòng. Kẻ tấn công biết địa chỉ email và bắt đầu recovery sau khi thử nhiều mật khẩu. Người dùng vẫn còn truy cập email nhưng không thực hiện yêu cầu.

### Thiết kế phản ứng

1. Recovery service ghi nhận request và áp dụng rate limit theo tài khoản/nguồn.
2. Hệ thống gửi thông báo bắt đầu tới email đã xác minh trước đó, không gửi chỉ tới địa chỉ mới do request cung cấp.
3. Nội dung nói rõ yêu cầu đang chờ và credential chưa được thay đổi.
4. Người dùng tự mở ứng dụng chính thức, báo cáo “không phải tôi”.
5. Hệ thống xác minh phiên báo cáo và áp dụng chính sách tạm giữ recovery.
6. Risk engine kiểm tra các sự kiện liên quan; đội hỗ trợ có thể yêu cầu xác minh bổ sung.
7. Nếu phát hiện compromise, hệ thống thu hồi session/token đáng ngờ, bảo vệ recovery method và yêu cầu xác thực lại.
8. Notification hoàn tất chỉ được gửi sau khi trạng thái tài khoản thực sự thay đổi.

### Nếu email đã bị chiếm

Thông báo tới email cũ có thể bị attacker đọc. Vì vậy email notification không phải lớp kiểm soát duy nhất. Với tài khoản rủi ro cao, cần nhiều tín hiệu/bằng chứng, kênh độc lập phù hợp, cooldown, kiểm tra hành vi và quy trình hỗ trợ có kiểm soát. Không gửi toàn bộ thông tin khôi phục hoặc credential mới qua email.

### Bài học

- Gửi tới kênh đã xác minh trước recovery giúp giảm nguy cơ attacker tự chuyển hướng cảnh báo.
- Notification bắt đầu và notification hoàn tất là hai sự kiện khác nhau.
- Nút báo cáo cần được bảo vệ khỏi abuse và không tự động khóa tài khoản vô điều kiện.
- Session/token revocation và credential replacement phải do recovery/security policy điều phối.

## 15. Kiểm thử recovery notification

Kiểm thử trong môi trường được phép với tài khoản, kênh và nhà cung cấp thử nghiệm:

| Trường hợp | Kết quả mong đợi |
|---|---|
| Recovery request được tiếp nhận | Gửi thông báo started tới kênh đã xác minh phù hợp |
| Recovery chỉ đang pending | Không thông báo rằng tài khoản đã khôi phục |
| Credential được cập nhật thành công | Gửi thông báo completed sau khi thay đổi có hiệu lực |
| Recovery bị hủy hoặc hết hạn | Thông báo trạng thái đúng nếu chính sách yêu cầu |
| Kênh mới được nhập trong recovery | Không dùng kênh mới làm đích duy nhất trước khi xác minh |
| Email cũ và email mới khác nhau | Kênh cũ nhận cảnh báo thay đổi theo chính sách |
| Người dùng không nhận ra recovery | Có đường báo cáo chính thức và quy trình phản ứng |
| Notification link bị sửa domain | Người dùng không bị chuyển tới domain ngoài allowlist |
| Link notification bị mở bởi người khác | Không thể tự hoàn tất recovery hoặc đăng nhập chỉ bằng việc mở link |
| Email chứa recovery code/token trong log | Kiểm soát redaction phải ngăn lộ secret |
| Attacker gửi nhiều recovery request | Rate limit, gộp hoặc suppression theo chính sách |
| Account không tồn tại | Phản hồi công khai không tiết lộ trạng thái tài khoản |
| Provider timeout | Retry có giới hạn, idempotency và delivery state rõ |
| Provider gửi callback lặp | Cập nhật delivery status idempotent |
| Email open tracking báo opened | Không xem đó là bằng chứng người dùng đã đọc |
| SMS delivery receipt thành công | Không xem đó là bằng chứng chủ tài khoản đã nhận |
| Kênh cũ không truy cập được | Chuyển quy trình thay thế; không tin kênh mới chỉ từ khai báo |
| Notification service ngừng hoạt động | Recovery áp dụng fallback theo mức rủi ro, không âm thầm bỏ qua yêu cầu bắt buộc |
| Người dùng báo cáo request giả | Ghi nhận, xác minh và đánh giá việc giữ/thu hồi recovery |
| Recovery hoàn tất một phần | Nội dung phản ánh đúng phần đã hoàn tất |

### Chỉ số vận hành

- Tỷ lệ notification queued, accepted, delivered, bounced và failed.
- Độ trễ từ recovery event đến notification submission/delivery.
- Tỷ lệ gửi trùng và retry.
- Tỷ lệ người dùng báo cáo recovery không nhận ra.
- Tỷ lệ recovery bị hủy sau cảnh báo.
- Tỷ lệ kênh cũ không còn truy cập được.
- Tỷ lệ account enumeration hoặc notification abuse được phát hiện.
- Thời gian từ báo cáo trái phép đến thu hồi session/credential.

Không tối ưu chỉ theo delivery rate. Một thông báo gửi thành công nhưng đến hộp thư attacker hoặc chứa link nguy hiểm vẫn là một thiết kế thất bại.

## 16. Checklist thiết kế recovery notification

- [ ] Xác định sự kiện nào cần thông báo và thời điểm gửi tương ứng.
- [ ] Phân biệt received, pending, approved, completed, rejected, expired và cancelled.
- [ ] Ưu tiên kênh đã xác minh trước khi recovery bắt đầu.
- [ ] Không gửi chỉ tới email/số điện thoại mới được cung cấp trong yêu cầu.
- [ ] Đánh giá tính độc lập và trạng thái hiện tại của kênh nhận.
- [ ] Nội dung đủ nhận biết sự kiện nhưng không tiết lộ dữ liệu nhạy cảm.
- [ ] Không gửi mật khẩu, OTP, recovery code, session ID hoặc token trong notification.
- [ ] Không coi notification delivery/opened là xác thực hoặc phê duyệt.
- [ ] Hướng dẫn người dùng tự mở ứng dụng/website chính thức và báo cáo hoạt động lạ.
- [ ] Link hành động không tự hoàn tất recovery; domain/redirect được kiểm soát.
- [ ] Có rate limit, idempotency, retry giới hạn và chống notification spam.
- [ ] Phản hồi recovery công khai tránh account enumeration.
- [ ] Có trạng thái delivery và xử lý provider timeout/failure.
- [ ] Có fallback an toàn nếu kênh cũ hoặc notification service không khả dụng.
- [ ] Recovery completion gắn với credential/session changes thực sự đã có hiệu lực.
- [ ] Có quy trình báo cáo, review, session/token revocation và credential replacement.
- [ ] Audit ghi event, policy, channel reference và delivery state nhưng không chứa secret.
- [ ] Đo delivery, abuse, false alert và thời gian phản ứng.

## Ghi nhớ

Recovery notification giúp người dùng nhận biết yêu cầu khôi phục và thay đổi bảo mật, đồng thời tạo cơ hội báo cáo hoạt động không do họ thực hiện. Gửi tới kênh đã xác minh trước recovery, diễn đạt đúng trạng thái và cung cấp đường phản ứng chính thức.

Thông báo không chứng minh người nhận là chủ tài khoản, không thay thế bằng chứng recovery và không phải phê duyệt chỉ vì email/SMS đã được gửi hoặc mở. Không đưa OTP, recovery code hay token vào notification. Kết hợp notification với rate limit, cooldown, audit, session/token revocation và quy trình hỗ trợ an toàn để bảo vệ tài khoản trong suốt vòng đời recovery.
