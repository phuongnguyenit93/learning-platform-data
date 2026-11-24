# Factor change notification

## 1. Vì sao phải báo khi phương thức xác thực thay đổi?

Thay phương thức xác thực có thể thay đổi người có khả năng đăng nhập. Một kẻ tấn công đang giữ session bị đánh cắp có thể cố gắn passkey của họ, thay ứng dụng MFA hoặc xóa phương thức của chủ tài khoản. Nếu thay đổi diễn ra âm thầm, chủ tài khoản có thể chỉ phát hiện sau khi bị mất quyền truy cập.

Factor change notification là thông báo về thay đổi đã xảy ra đối với phương thức xác thực được ràng buộc với tài khoản. Nó giúp người nhận nhận biết thay đổi và phản ứng khi không phải người thực hiện.

Trong bài này, “phương thức” có thể là ứng dụng TOTP, khóa bảo mật, passkey hoặc số điện thoại được dùng để nhận mã xác thực. Không đồng nhất số thiết bị với số loại yếu tố: hai ứng dụng TOTP không tự trở thành hai loại yếu tố độc lập.

Thông báo thay phương thức khác với thông báo hoàn tất khôi phục. Một quy trình khôi phục có thể gồm nhiều thay đổi phương thức, còn một người đang đăng nhập bình thường cũng có thể thêm khóa bảo mật mà không thực hiện khôi phục tài khoản.

[OWASP Multifactor Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html#changing-mfa-factors) xem thay phương thức MFA là hành động có rủi ro cao, khuyến nghị không chỉ dựa vào session đang hoạt động và thông báo qua kênh ngoài luồng khi phương thức được thay đổi.

Thông báo là lớp phát hiện bổ sung. Nó không thay thế xác thực lại, kiểm tra rủi ro hoặc quy trình khôi phục danh tính phù hợp khi phương thức cũ đã bị mất.

## 2. Mô tả chính xác loại thay đổi

Một câu chung chung như “cài đặt bảo mật đã cập nhật” thường không đủ để người nhận nhận ra điều gì đã xảy ra.

| Loại sự kiện | Điều đã thay đổi | Cách diễn đạt có ích |
| --- | --- | --- |
| Thêm phương thức | Một phương thức mới được ràng buộc và đạt điều kiện sử dụng | “Một khóa bảo mật mới đã được thêm” |
| Thay phương thức | Phương thức mới được đưa vào sử dụng và phương thức cũ được xử lý theo chính sách thay thế | “Ứng dụng xác thực đã được thay; ứng dụng cũ đã bị vô hiệu hóa” nếu đúng thực tế |
| Thu hồi phương thức | Một phương thức không còn được chấp nhận cho tài khoản | “Passkey có nhãn … đã bị xóa khỏi tài khoản” |
| Đình chỉ tạm thời | Phương thức bị tạm ngừng, chưa phải thu hồi vĩnh viễn | “Khóa bảo mật đã bị tạm ngừng sử dụng” |
| Tắt yêu cầu MFA | Chính sách đăng nhập của tài khoản bị giảm hoặc thay đổi | “Yêu cầu MFA đã bị tắt” nếu sản phẩm cho phép và thao tác đã hợp lệ |
| Thay số điện thoại xác thực | Ràng buộc số nhận mã xác thực được thay đổi | Nêu loại thay đổi và che bớt số, tránh gửi toàn bộ số cũ và mới |

Đổi tên hiển thị của một passkey có thể chỉ là thay metadata; không nên thông báo rằng khóa mật mã đã được thay. Ngược lại, một credential mới được ràng buộc không nên bị che thành thao tác đổi nhãn.

Với số điện thoại, cần phân biệt số nhận OTP, số liên hệ hỗ trợ và số nhận thông báo. Cùng một số có thể đảm nhận nhiều vai trò, nhưng đổi một vai trò không tự chứng minh các vai trò khác cũng đã được cập nhật.

Đối với passkey, nêu đúng phạm vi máy chủ kiểm soát: xóa ràng buộc credential tại dịch vụ không phải lời hứa rằng mọi bản sao trên thiết bị hoặc dịch vụ đồng bộ đã bị xóa. Không dùng thông báo để khẳng định việc xóa dữ liệu ngoài phạm vi đã xác nhận.

## 3. Sự kiện xảy ra khi nào?

Một màn hình cho biết “đã quét QR” hoặc “đã nhận yêu cầu thêm passkey” chưa có nghĩa phương thức đã được đưa vào sử dụng. Có thể vẫn còn bước chứng minh quyền sở hữu, phê duyệt hoặc thời gian trì hoãn.

Một mô hình minh họa:

```text
Yêu cầu thay phương thức
  -> xác thực lại hoặc hoàn tất điều kiện khôi phục
  -> chuẩn bị và xác minh phương thức mới
  -> áp dụng chính sách và thay đổi ràng buộc
  -> ghi nhận thay đổi có hiệu lực
  -> phát thông báo về kết quả đã ghi nhận
```

Nếu còn chờ, thông báo phải dùng ngôn ngữ chờ. Không gửi “MFA đã được thay” trước khi ràng buộc mới đạt trạng thái cho phép sử dụng.

Một thao tác thay thế có thể có hai tác động: kích hoạt phương thức mới và thu hồi phương thức cũ. Khi hai tác động chưa cùng hoàn tất, cần thể hiện trạng thái thực tế. Ví dụ, hệ thống có thể thông báo “đã thêm khóa mới; việc thu hồi khóa cũ đang chờ xử lý” nếu đó là trạng thái sản phẩm cho phép, thay vì gọi toàn bộ thao tác là thay thế thành công.

Một phương thức bị nghi lộ có thể cần thu hồi nhanh theo chính sách, kể cả khi chưa thêm được phương thức mới. Không trì hoãn xử lý nguy cơ chỉ để tạo một thông báo “thay thế” đẹp hơn.

[NIST SP 800-63B-4](https://pages.nist.gov/800-63-4/sp800-63b/events/) yêu cầu thông báo bằng cơ chế độc lập với giao dịch khi ràng buộc thêm authenticator; với vô hiệu hóa authenticator, tài liệu dùng mức khuyến nghị SHOULD. Mục 4.6 quy định thông báo tài khoản và hướng dẫn người nhận liên hệ khi phủ nhận sự kiện. Mức bắt buộc của từng sự kiện cần được phân biệt khi áp dụng tiêu chuẩn.

Các trạng thái và tên sự kiện trong bài là thiết kế minh họa, không phải schema do NIST quy định.

## 4. Kênh nhận phải giúp chủ tài khoản biết sự kiện

Chỉ hiển thị thông báo trong session vừa thay MFA có thể không giúp chủ tài khoản phát hiện một session đã bị chiếm. Chỉ gửi đến phương thức vừa được thêm cũng có cùng vấn đề: người đang kiểm soát phương thức mới có thể là kẻ tấn công.

Một chính sách chọn người nhận cần trả lời:

1. Kênh nào đã được thiết lập và xác minh từ trước?
2. Kênh nào độc lập với thay đổi đang diễn ra?
3. Kênh nào đã được báo mất, bị xâm phạm hoặc không còn hợp lệ?
4. Kênh thay thế nào được phép dùng khi kênh chính không thể nhận?
5. Nếu tài khoản không còn kênh phù hợp, ai xử lý ngoại lệ và người dùng nhận chỉ dẫn ở đâu?

Địa chỉ nhận phải được quyết định từ dữ liệu tài khoản có thẩm quyền. Không chấp nhận trường `notifyTo` tùy ý trong request để thay thế toàn bộ người nhận của cảnh báo bảo mật.

Ví dụ, khi đổi số nhận OTP từ số kết thúc 0142 sang 7780, gửi duy nhất SMS đến số mới không bảo đảm chủ tài khoản được biết. Có thể cần email thông báo đã xác minh hoặc một kênh độc lập khác theo chính sách. Gửi tới số cũ cũng không mặc nhiên an toàn: số đó có thể đã bị mất, tái cấp hoặc bị chiếm.

Nếu đồng thời thay địa chỉ liên hệ, cần xử lý riêng quyền thay đổi địa chỉ và kế hoạch gửi cảnh báo. Không tự động tin địa chỉ mới vì nó xuất hiện trong transaction đã được chấp nhận.

Lưu quyết định chọn người nhận hoặc tham chiếu có phiên bản giúp giải thích vì sao cảnh báo được gửi đến một kênh. Trước lúc chuyển phát, nếu có bằng chứng kênh đã mất an toàn, áp dụng chính sách ngoại lệ và ghi dấu vết thay vì âm thầm chuyển sang địa chỉ do người thực hiện vừa thêm.

## 5. Nội dung cần nêu trước và sau thay đổi

Một thông báo tốt cho phép người nhận trả lời ba câu: điều gì đã thay đổi, khi nào xảy ra và phải làm gì nếu không nhận ra.

| Thông tin | Cách trình bày |
| --- | --- |
| Tài khoản và dịch vụ | Dùng tên dịch vụ rõ ràng, che bớt định danh tài khoản nếu cần |
| Loại hành động | Thêm, thay, thu hồi hoặc tạm ngừng phương thức |
| Loại phương thức | Ứng dụng xác thực, passkey, khóa bảo mật hoặc số nhận OTP |
| Trạng thái phương thức cũ | Còn hoạt động, đã thu hồi hoặc đang chờ; chỉ nêu điều đã xác nhận |
| Thời điểm sự kiện | Ngày, giờ và múi giờ rõ ràng |
| Nguồn khởi tạo | Tự phục vụ, quy trình khôi phục hoặc hỗ trợ, nếu dữ liệu có thẩm quyền xác nhận |
| Hành động tiếp theo | Kiểm tra mục Bảo mật hoặc liên hệ kênh hỗ trợ chính thức |
| Mã tham chiếu | Để tra cứu sự kiện, không mang quyền đăng nhập |

Nhãn phương thức có thể do người dùng đặt. Một kẻ tấn công có thể chọn nhãn giống phương thức cũ hoặc chứa nội dung gây hiểu nhầm. Không dùng nhãn làm định danh duy nhất và không chèn nhãn thô vào HTML, tiêu đề email hoặc hướng dẫn hành động. Giới hạn độ dài, escape theo ngữ cảnh và dùng mô tả do máy chủ kiểm soát khi cần.

Không gửi seed TOTP, QR cài đặt, OTP, mã dự phòng, mật khẩu, token khôi phục hoặc private key trong cảnh báo thay phương thức. Cảnh báo không phải kênh bàn giao bí mật của phương thức mới.

Với push hoặc SMS, cân nhắc dữ liệu hiện trên màn hình khóa. Có thể thông báo ngắn và dẫn người nhận tự mở ứng dụng chính thức để xem chi tiết sau khi đáp ứng điều kiện truy cập.

Địa chỉ IP và vị trí gần đúng, nếu dùng, chỉ là ngữ cảnh hỗ trợ nhận biết. Không mô tả vị trí suy ra từ IP như bằng chứng chắc chắn về người thực hiện.

## 6. Hai mẫu thông báo có phạm vi khác nhau

### Thay ứng dụng MFA sau khi mất thiết bị

Mẫu sau giả định phương thức mới đã hoạt động và phương thức cũ thực sự đã bị vô hiệu hóa:

```text
Tiêu đề: Ứng dụng xác thực của tài khoản đã được thay

Lúc 15:10 ngày 24/11/2026 (UTC+07:00), ứng dụng xác thực
của tài khoản có định danh a*** đã được thay
qua quy trình khôi phục tài khoản.

Ứng dụng xác thực trước đó không còn được chấp nhận
để xác thực vào tài khoản này.

Nếu bạn thực hiện thay đổi:
Hãy mở ứng dụng hoặc trang web chính thức,
vào Bảo mật để kiểm tra các phương thức đang hoạt động.

Nếu bạn không thực hiện:
Hãy sử dụng mục Trợ giúp bảo mật trên trang web chính thức.
Nếu không thể đăng nhập, dùng kênh hỗ trợ công khai
được công bố tại đó và cung cấp mã tham chiếu bên dưới.

Mã tham chiếu: FACTOR-EXAMPLE-310

Không gửi mật khẩu, OTP hoặc mã khôi phục khi trả lời thư.
```

Thông báo không khẳng định mọi session cũ đã kết thúc. Thu hồi phương thức và thu hồi session là hai tác động khác nhau.

### Thêm một passkey, giữ các phương thức hiện có

```text
Tiêu đề: Một passkey mới đã được thêm vào tài khoản

Một passkey mới đã được thêm vào tài khoản của bạn
lúc 15:25 ngày 24/11/2026 (UTC+07:00).

Các phương thức hiện có không bị xóa bởi thao tác thêm này.

Nếu không nhận ra thay đổi, hãy tự mở ứng dụng hoặc
trang web chính thức, kiểm tra mục Bảo mật và liên hệ hỗ trợ
qua kênh được công bố nếu bạn không thể truy cập tài khoản.

Mã tham chiếu: FACTOR-EXAMPLE-311
```

Câu về phương thức hiện có chỉ dùng khi kết quả ghi xác nhận như vậy. Không dùng một mẫu “thay thế” cho mọi thao tác thêm hoặc xóa.

## 7. “Tôi không thực hiện” cần dẫn đến xử lý có kiểm soát

Người nhận thông báo có thể cần phản ứng ngay, nhưng sở hữu email hoặc mở một liên kết không tự chứng minh quyền quản lý tài khoản.

Một liên kết báo cáo có thể dẫn đến trang tiếp nhận nghi vấn và hướng dẫn. Nó không nên trực tiếp tạo session đăng nhập, gắn phương thức mới hoặc khôi phục phương thức cũ.

Phần mềm quét email có thể mở liên kết trước người dùng. Vì vậy, yêu cầu GET chỉ để xem thông tin không được âm thầm vô hiệu hóa tài khoản hoặc hoàn tác thay đổi.

Nếu có hành động đình chỉ phương thức nghi ngờ bị gắn trái phép, hệ thống cần xác định điều kiện xác minh và mức tác động phù hợp. Không thể áp dụng một yêu cầu xác minh quá khó khiến chủ tài khoản bị chiếm hoàn toàn không có cách báo cáo, nhưng cũng không nên cho bất kỳ người có bản sao email nào khóa toàn tài khoản.

Có thể tách:

- Tiếp nhận báo cáo nghi vấn với dữ liệu tối thiểu và kiểm soát lạm dụng.
- Đối chiếu sự kiện với tài khoản, phương thức và ngữ cảnh có thẩm quyền.
- Áp dụng biện pháp bảo vệ phù hợp với độ tin cậy và rủi ro.
- Xác minh đủ trước khi cấp phương thức mới hoặc quyền truy cập.

Nếu phương thức cũ bị thu hồi vì mất thiết bị hoặc bị lộ, không tự kích hoạt lại nó để “hoàn tác” sau khi người nhận phủ nhận sự kiện. Có thể phải thu hồi phương thức mới và tiến hành một luồng khôi phục an toàn khác.

Nếu chỉ đình chỉ tạm thời, quy trình tái kích hoạt cần có điều kiện riêng. Cần phân biệt đình chỉ có thể đảo ngược theo chính sách với thu hồi ràng buộc đã kết thúc.

## 8. Ghi sự kiện và chuyển phát đáng tin cậy

Ý định thông báo cần gắn với thay đổi đã commit. Một thiết kế có thể ghi bản ghi thay đổi phương thức và sự kiện outbox trong cùng transaction, sau đó một bộ gửi xử lý các sự kiện đã commit.

Mã giả dưới đây mô tả ranh giới, không phải triển khai hoàn chỉnh:

```text
BEGIN
  kiểm tra quyền thay phương thức và trạng thái hiện tại
  áp dụng ràng buộc mới hoặc thu hồi theo chính sách
  kiểm tra số bản ghi thay đổi đúng dự kiến
  ghi bản tóm tắt trạng thái trước và sau
  ghi FactorChanged cùng ý định thông báo
COMMIT

Bộ gửi:
  chỉ đọc sự kiện đã commit
  lấy kế hoạch người nhận đã được quyết định
  tạo nội dung theo loại thay đổi thực tế
  chuyển phát và theo dõi từng người nhận, từng kênh
```

Không giữ transaction chờ email hoặc chờ người dùng đọc thư. Đổi lại, không đánh dấu “thông báo đã tới chủ tài khoản” chỉ vì transaction chứa outbox đã commit.

Một sự kiện minh họa:

```yaml
eventId: evt_factor_example_42
eventType: FactorChanged
accountRef: acct_example_18
changeRef: change_example_71
operation: REPLACE
factorKind: TOTP
previousFactorRef: factor_example_old
previousStateAfterChange: REVOKED
newFactorRef: factor_example_new
newStateAfterChange: ACTIVE
initiatedVia: ACCOUNT_RECOVERY
occurredAt: "2026-11-24T08:10:00Z"
accountSecurityRevision: 23
recipientPlanRef: recipients_example_v4
```

Payload chỉ chứa tham chiếu và thông tin tối thiểu. Những tham chiếu đó vẫn là dữ liệu cần phân quyền; không công khai chúng như bằng chứng xác thực.

Nếu thay đổi ràng buộc và thu hồi nằm ở các hệ thống khác nhau, trạng thái phải phản ánh từng tác động thực tế. Không tạo `previousStateAfterChange: REVOKED` từ một lệnh đang nằm trong hàng đợi.

Một `changeRef` có thể liên kết sự kiện thêm và thu hồi thuộc cùng ý định. Chỉ gộp thành thông báo thay thế khi dữ liệu đủ để mô tả đúng cả hai, không gộp chỉ vì hai sự kiện có thời gian gần nhau.

## 9. Retry, thứ tự và mệt mỏi cảnh báo

Một thay đổi không nên tạo hàng chục cảnh báo giống nhau do request được gửi lại. Tuy nhiên, chống lặp không được làm mất thông báo của một thay đổi khác.

Khóa chống lặp có thể gồm `eventId + recipientRef + channel`. Không dùng riêng `accountId`, vì cùng tài khoản có thể thêm khóa mới rồi thu hồi một khóa khác ngay sau đó.

Với nhiều sự kiện, phiên bản bảo mật hoặc số thứ tự có thể hỗ trợ đối chiếu. Ví dụ:

```text
15:25 thêm passkey A
15:30 thu hồi passkey A
15:40 email về lần thêm mới được chuyển phát
```

Email đến lúc 15:40 phải giữ thời điểm 15:25 và mô tả đây là sự kiện lúc đó. Khi người dùng mở trang Bảo mật, trạng thái mới nhất phải cho thấy passkey A đã bị thu hồi. Không cho phép cảnh báo cũ làm máy chủ tự phục hồi trạng thái ACTIVE.

Theo dõi riêng các giai đoạn: đã tạo ý định, nhà cung cấp đã chấp nhận, có tín hiệu chuyển phát, lỗi tạm thời và lỗi vĩnh viễn. Tín hiệu chuyển phát không chứng minh người nhận đã đọc; lượt mở email cũng không phải hành động đồng ý.

Retry cần có giới hạn và xử lý lỗi theo từng kênh. Không rollback thay đổi bảo mật đã hoàn tất hoặc làm token khôi phục dùng lại được chỉ vì dịch vụ email thất bại.

Để hạn chế mệt mỏi cảnh báo:

- Phân biệt yêu cầu chưa xác minh với thay đổi phương thức đã có hiệu lực.
- Chống trùng cùng sự kiện, nhưng giữ dấu vết các thay đổi thực sự khác nhau.
- Giới hạn chức năng gửi lại mà người dùng có thể gọi.
- Không cho người thực hiện tự tắt cảnh báo bắt buộc ngay trong thao tác thay phương thức.
- Theo dõi tồn đọng và cảnh báo vận hành khi thông báo nhạy cảm bị chậm.

Việc gộp thông báo, nếu được phép, vẫn phải liệt kê đúng loại thay đổi và không làm mất thời điểm hoặc khả năng phủ nhận từng sự kiện.

## 10. Áp dụng trong các tình huống khôi phục

### Chủ tài khoản mất khóa bảo mật

Quy trình khôi phục xác minh đủ điều kiện và thu hồi ràng buộc khóa bị mất. Thông báo nêu rõ khóa đó không còn được chấp nhận. Nếu việc thêm khóa thay thế chưa hoàn tất, không nói tài khoản đã có khóa mới sử dụng được.

### Kẻ tấn công có một session cũ

Đường thay phương thức vẫn cần kiểm tra quyền và xác minh phù hợp; gửi email sau đó không bù cho việc cho phép thay MFA chỉ bằng session. Nếu một thay đổi trái phép xảy ra, cảnh báo qua kênh độc lập giúp chủ tài khoản nhận biết và báo cáo.

### Nhân viên hỗ trợ thay phương thức

Thao tác có thể được khởi tạo qua kênh hỗ trợ, nhưng cảnh báo vẫn phải xuất phát từ thay đổi có thẩm quyền đã ghi nhận. Không để nhân viên tùy ý bỏ người nhận cảnh báo hoặc sửa nội dung thành một sự kiện khác. Nhật ký nội bộ phải đủ để đối chiếu hành động được phép mà không đưa dữ liệu nội bộ nhạy cảm vào email.

### Người dùng thêm rồi xóa phương thức trong thời gian ngắn

Cả hai thay đổi đều có ý nghĩa. Hệ thống có thể gửi riêng hoặc nhóm theo chính sách, nhưng phải mô tả rõ đã thêm rồi đã xóa. Không coi việc phương thức hiện không còn hoạt động là lý do xóa dấu vết lần ràng buộc trước đó.

Thông báo thay phương thức có ích khi người nhận nhận ra đúng tác động đến khả năng đăng nhập và có đường ứng phó rõ ràng. Tính chính xác của sự kiện, kênh độc lập và quyền hạn của hành động tiếp theo phải được thiết kế cùng nhau.