# Support recovery intake

## 1. Tiếp nhận hỗ trợ là bước nào trong luồng khôi phục?

Support recovery intake là bước nhận yêu cầu trợ giúp khi người dùng không thể lấy lại quyền truy cập bằng các phương thức hiện có. Tình huống có thể là mất mật khẩu, mất điện thoại MFA, không dùng được passkey, mất khóa bảo mật hoặc nghi ngờ tài khoản đã bị chiếm.

Kết quả của bước này là một hồ sơ đủ rõ để chuyển đúng quy trình xử lý. Việc tạo hồ sơ không chứng minh người gửi là chủ tài khoản và không tự cho phép đặt lại mật khẩu, gỡ MFA hay đổi địa chỉ khôi phục.

Ba trạng thái cần được tách biệt:

| Điều đã đạt | Ý nghĩa |
| --- | --- |
| Đã tiếp nhận yêu cầu | Hệ thống đã lưu được thông tin cần thiết để xử lý |
| Đã xác minh đủ điều kiện | Bằng chứng đã được kiểm tra theo chính sách phù hợp |
| Đã khôi phục quyền truy cập | Các thay đổi được phép đã hoàn tất theo hợp đồng nghiệp vụ |

Nếu giao diện hoặc nhân viên nói “đã duyệt khôi phục” ngay sau khi tạo ticket, người yêu cầu có thể hiểu rằng đã được cấp quyền dù chưa qua xác minh.

[OWASP Multifactor Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html#resetting-mfa) nhấn mạnh rằng cơ chế hỗ trợ lấy lại quyền truy cập khi mất MFA không được trở thành đường vòng chiếm tài khoản. Tiếp nhận vì vậy cần hỗ trợ người gặp khó khăn mà vẫn giữ nguyên các điều kiện cấp quyền.

## 2. Xác định mục tiêu và giới hạn của intake

Một bước tiếp nhận có thể thực hiện các công việc sau:

- Ghi nhận loại khó khăn và phương thức được báo mất hoặc không dùng được.
- Thu thập định danh cần thiết để tìm hồ sơ theo chính sách.
- Ghi nhận kênh liên lạc và mức độ xác minh của kênh đó.
- Phân biệt mất phương thức với nghi ngờ bị chiếm quyền.
- Hướng dẫn đường tự phục vụ còn phù hợp.
- Tạo mã hồ sơ và chuyển hàng đợi đúng chuyên môn.
- Ghi dấu vết ai tiếp nhận, từ kênh nào và khi nào.

Các thay đổi nhạy cảm cần thuộc một quy trình có quyền và điều kiện riêng. Nhân viên tiếp nhận không nên có nút “bỏ qua MFA” chỉ vì đã nói chuyện với người gọi.

Không lấy mức độ khẩn cấp, sự tự tin của người gọi hoặc việc họ biết nhiều thông tin cá nhân làm kết luận sở hữu tài khoản. Đây đều có thể là yếu tố của một cuộc social engineering.

Một nguyên tắc thiết kế hữu ích là:

> Intake tạo khả năng xử lý hồ sơ; xác minh và phê duyệt mới tạo điều kiện cho hành động khôi phục được phép.

## 3. Chọn kênh tiếp nhận và ghi đúng mức tin cậy

Yêu cầu có thể đến từ biểu mẫu công khai, ứng dụng, chat, email hoặc cuộc gọi. Các kênh không mang cùng mức xác thực.

| Kênh tiếp nhận | Điều có thể biết | Điều không được mặc định |
| --- | --- | --- |
| Biểu mẫu chưa đăng nhập | Có một người gửi dữ liệu khai báo | Người đó là chủ tài khoản |
| Email gửi tới hỗ trợ | Có một thư và thông tin liên quan đến việc gửi thư | Địa chỉ người gửi đủ để cấp quyền khôi phục |
| Cuộc gọi | Có một tương tác thoại | Caller ID hoặc giọng nói chứng minh danh tính |
| Phiên đã đăng nhập | Có principal theo ngữ cảnh xác thực hiện tại | Session chưa bị chiếm hoặc đủ quyền thay MFA |
| Kênh nội bộ của tổ chức | Người gọi đi qua một hệ thống nội bộ | Mọi nhân viên nội bộ được phép khôi phục mọi tài khoản |

Danh tính nhân viên xử lý cũng phải rõ. Dùng principal nhân viên có kiểm soát, tránh chỉ lưu một tên hiển thị hoặc tài khoản chung khi cần quy trách nhiệm.

Nếu khách hàng được chuyển giữa các kênh, giữ liên kết hồ sơ và lịch sử xác minh có nguồn. Không để mỗi nhân viên hiểu rằng người trước đã xác minh chỉ vì hồ sơ có trạng thái “đang xử lý”.

Một lần chuyển cuộc gọi hoặc một tin nhắn từ tài khoản chat mới không tự kế thừa quyền của phiên trước. Phải xác định điều kiện liên kết giữa các tương tác.

## 4. Thu thập dữ liệu tối thiểu và có mục đích

Intake nên hỏi những thông tin giúp phân loại và chuyển xử lý. Không yêu cầu người dùng đổ toàn bộ dữ liệu cá nhân vào ticket.

| Thông tin | Mục đích | Giới hạn |
| --- | --- | --- |
| Dịch vụ hoặc tenant liên quan | Định tuyến đúng hệ thống | Không tiết lộ thông tin tenant khác |
| Định danh tài khoản khai báo | Hỗ trợ tra cứu nội bộ | Chưa phải bằng chứng sở hữu |
| Loại sự cố | Mất mật khẩu, MFA, passkey hoặc thiết bị | Dùng danh mục rõ ràng, có mô tả ngắn nếu cần |
| Phương thức còn dùng được | Tìm đường tự phục vụ hoặc xác minh phù hợp | Chỉ hỏi tình trạng, không hỏi bí mật của phương thức |
| Dấu hiệu bất thường | Phân loại nghi ngờ bị chiếm quyền | Ghi là điều được báo cáo nếu chưa được kiểm chứng |
| Kênh liên lạc đề xuất | Trao đổi về hồ sơ | Không tự biến thành địa chỉ recovery mới |
| Thời điểm phát hiện | Hỗ trợ đánh giá diễn biến | Phân biệt thời gian khai báo và thời gian máy chủ nhận |
| Nhu cầu hỗ trợ tiếp cận | Chọn cách hướng dẫn phù hợp | Không tự hạ điều kiện bảo mật |

Ví dụ câu hỏi phù hợp: “Bạn còn sử dụng được phương thức xác thực nào đã đăng ký?” hoặc “Bạn có nghi ngờ tài khoản đang bị người khác sử dụng không?”.

Không hỏi người dùng gửi mật khẩu, OTP đăng nhập, mã khôi phục hoặc seed MFA vào chat, email hay phần mô tả ticket. Nếu một quy trình hợp lệ cần trình mã khôi phục, người dùng phải nhập tại giao diện xác minh chính thức được thiết kế cho mục đích đó, không gửi bí mật cho nhân viên để ghi chú.

Không yêu cầu ảnh giấy tờ một cách mặc định chỉ vì người dùng gọi hỗ trợ. Nếu có bước xác minh danh tính được phép, bước đó cần mục đích, điều kiện thu thập, nơi lưu và quyền truy cập riêng.

## 5. Tìm tài khoản mà không tiết lộ thông tin

Định danh người dùng nhập giúp hệ thống tra cứu, nhưng phản hồi công khai không nên trở thành công cụ dò tài khoản.

[OWASP Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html#forgot-password-request) khuyến nghị thông điệp nhất quán cho tài khoản tồn tại và không tồn tại, cùng kiểm soát thời gian phản hồi và lạm dụng. Với intake công khai, cần xét cả lời nhắn tự động lẫn cách nhân viên trả lời để tránh tiết lộ cùng thông tin qua kênh khác.

Một lời tiếp nhận có thể là:

```text
Chúng tôi đã nhận thông tin bạn gửi.

Hồ sơ sẽ được kiểm tra theo quy trình hỗ trợ truy cập.
Việc tiếp nhận chưa xác nhận quyền sở hữu tài khoản
và chưa thay đổi các phương thức đăng nhập.

Không gửi mật khẩu, OTP hoặc mã khôi phục trong phần trao đổi.
Chỉ sử dụng các bước được hướng dẫn trên kênh chính thức.
```

Không trả lại địa chỉ email đầy đủ, số điện thoại hay danh sách MFA của tài khoản chỉ để hỏi “có đúng của bạn không?”. Người gọi chưa xác minh có thể thu thập thông tin từ cách xác nhận đó.

Nếu không tìm thấy hoặc không thể xác định duy nhất tài khoản, ghi trạng thái nội bộ phù hợp và chuyển xử lý theo chính sách. Không tự tạo một liên kết tài khoản chỉ vì tên hoặc địa chỉ gần giống.

Thông tin nội bộ rằng hồ sơ đã được liên kết tới một tài khoản vẫn cần quyền truy cập. Nó không nên xuất hiện trong endpoint tra trạng thái công khai không có kiểm soát.

## 6. Tách kênh liên lạc khỏi quyền kiểm soát tài khoản

Một người mất email cũ thường đề nghị hỗ trợ liên hệ qua email mới. Có thể cần một kênh như vậy để trao đổi hướng dẫn, nhưng đây là một lời khai cần được quản lý.

Cần phân biệt:

- Địa chỉ dùng để trao đổi về hồ sơ.
- Địa chỉ được đăng ký nhận thông báo bảo mật.
- Địa chỉ được phép nhận bằng chứng hoặc mã khôi phục.
- Địa chỉ đăng nhập hoặc thông tin liên hệ của tài khoản.

Xác nhận người gửi có thể nhận email tại địa chỉ mới chỉ chứng minh một mức kiểm soát của địa chỉ đó theo cơ chế xác nhận; không chứng minh họ sở hữu tài khoản đang yêu cầu khôi phục.

Không thay địa chỉ recovery của tài khoản ngay tại intake để “gửi link cho tiện”. Nếu làm vậy, kẻ tấn công có thể tự chọn nơi nhận bước khôi phục tiếp theo.

Nếu cần callback, nguồn số gọi lại và mục đích cuộc gọi phải được quy định. Một số vừa được người gọi cung cấp không tự trở thành số đã xác minh của tài khoản. Số đã có từ trước cũng cần xem xét trạng thái mất an toàn hoặc không còn sử dụng.

Không tự khôi phục địa chỉ cũ khi người dùng nói địa chỉ mới không dùng được. Địa chỉ cũ có thể đã bị thay vì bị lộ, mất quyền kiểm soát hoặc được cấp lại cho người khác.

## 7. Phân loại rủi ro để chuyển xử lý, không tự cấp quyền

Một sơ đồ phân loại minh họa:

```text
Nhận yêu cầu
  -> kiểm tra dữ liệu đủ để tiếp nhận
  -> ghi tình trạng phương thức còn dùng được
  -> ghi nghi vấn bị chiếm quyền nếu được báo cáo
  -> tìm đường xử lý được chính sách cho phép
     -> hướng dẫn tự phục vụ
     -> chuyển xem xét hỗ trợ
     -> chuyển đội xử lý sự cố theo tiêu chí
     -> yêu cầu bổ sung thông tin tối thiểu
```

Không tự động tắt toàn bộ tài khoản chỉ vì một người chưa xác minh đánh dấu “tài khoản đã bị hack”. Việc tiếp nhận nghi vấn và việc áp dụng biện pháp bảo vệ cần được phân biệt để tránh tạo công cụ gây từ chối dịch vụ.

Điều này cũng không có nghĩa bỏ qua dấu hiệu nguy hiểm. Những hành động đình chỉ, thu hồi hoặc hạn chế phù hợp cần đi qua cơ chế xử lý có điều kiện, quyền hạn và đánh giá rủi ro đã được xác định.

Các trường hợp cần được chú ý có thể gồm mất cả email lẫn MFA, yêu cầu thay địa chỉ liên lạc ngay lập tức, tài khoản có quyền cao, nhiều hồ sơ tương tự hoặc người gọi cố ép bỏ qua quy trình.

“Khẩn cấp” là thông tin phân loại, không phải quyền vượt kiểm soát. Không hứa bỏ bước xác minh vì người gọi là lãnh đạo, khách hàng lớn hoặc đang chịu áp lực thời gian.

## 8. Chọn đường xác minh phù hợp với nền tảng tài khoản

Intake cần biết đường xử lý nào được chính sách hỗ trợ, nhưng không tự sáng tạo cách xác minh khi người dùng không đáp ứng được đường hiện có.

[NIST SP 800-63B-4](https://pages.nist.gov/800-63-4/sp800-63b/events/#account-recovery-methods) mô tả các nhóm phương thức khôi phục và cho phép phương thức đặc thù ứng dụng dựa trên phân tích rủi ro được tài liệu hóa. Việc có nhân viên hỗ trợ tham gia không tự tạo một ngoại lệ để bỏ mọi yêu cầu.

Nếu tài khoản từng được xác minh danh tính theo một quy trình phù hợp, có thể tồn tại đường xác minh lại gắn với hồ sơ đã thiết lập. Nếu chưa từng có sự ràng buộc đó, một ảnh giấy tờ mới không tự chứng minh người cầm giấy là chủ của tài khoản hiện có.

Trong phạm vi NIST, tài liệu cũng phân biệt tài khoản chưa qua identity proofing với trường hợp có thể sử dụng reproofing. Không nên dùng cùng một lời hứa “chỉ cần giấy tờ là lấy lại được” cho mọi tài khoản. [NIST SP 800-63B-4, yêu cầu khôi phục](https://pages.nist.gov/800-63-4/sp800-63b/events/#recovery-without-identity-proofing)

Tên, ngày sinh, thông tin công khai hoặc ảnh chụp màn hình có thể có ích cho việc tìm hồ sơ, nhưng không nên được coi là bằng chứng đủ chỉ vì người gọi biết chúng.

Nếu không có đường khôi phục được phép, cần báo đúng giới hạn và chuyển quy trình xử lý ngoại lệ nếu tổ chức có quy định. Không cấp quyền bằng một phương thức yếu hơn do nhân viên tự chọn để đóng ticket.

## 9. Quản lý trạng thái intake độc lập với xác minh

Một mô hình trạng thái intake minh họa:

| Trạng thái | Điều được xác nhận |
| --- | --- |
| RECEIVED | Thông tin tối thiểu đã được tiếp nhận và lưu |
| NEEDS_INFORMATION | Thiếu dữ liệu cần thiết để định tuyến |
| ROUTED_TO_SELF_SERVICE | Đã hướng dẫn một đường tự phục vụ phù hợp |
| READY_FOR_REVIEW | Hồ sơ đã đủ để chuyển người có trách nhiệm xem xét |
| CLOSED | Công việc tiếp nhận đã kết thúc theo một lý do xác định |

Những trạng thái này không phải kết quả xác minh danh tính hoặc kết quả thay credential.

Ví dụ hồ sơ nội bộ đã giảm dữ liệu nhạy cảm:

```json
{
  "caseRef": "case_example_901",
  "intakeState": "READY_FOR_REVIEW",
  "receivedAt": "2026-11-24T11:00:00Z",
  "channel": "PUBLIC_SUPPORT_FORM",
  "actor": {
    "kind": "RECOVERY_CLAIMANT",
    "principalRef": null
  },
  "accountLocatorRef": "sensitive_input_example_31",
  "accountBindingState": "UNCONFIRMED",
  "reportedProblem": "LOST_MFA_DEVICE",
  "reportedRemainingMethods": [
    "PASSWORD"
  ],
  "reportedCompromise": false,
  "contact": {
    "valueRef": "sensitive_contact_example_12",
    "verificationState": "UNVERIFIED",
    "purpose": "CASE_COMMUNICATION"
  },
  "assignedQueue": "RECOVERY_REVIEW",
  "recoveryAuthority": "NONE"
}
```

Các giá trị chỉ là ví dụ. Dữ liệu định danh và liên lạc được lưu ở nơi được bảo vệ; tham chiếu không phải quyền tải dữ liệu đó.

`reportedRemainingMethods` và `reportedCompromise` là lời khai, không phải trạng thái tài khoản đã được máy chủ chứng minh. `READY_FOR_REVIEW` chỉ nói hồ sơ đủ để xem xét, còn `recoveryAuthority=NONE` diễn đạt intake chưa cấp quyền khôi phục.

Nếu một hồ sơ được chuyển đi rồi quay lại cần bổ sung, phải giữ nguồn và thời điểm của các thay đổi. Không dùng một nhãn “verified” chung cho cả xác nhận email liên lạc và xác minh quyền sở hữu tài khoản.

## 10. Chống lạm dụng và giữ chuỗi bàn giao

Kênh hỗ trợ công khai có thể bị dùng để tạo hàng loạt hồ sơ, gây quá tải, làm mệt nhân viên hoặc tiếp cận nhiều nhân viên để tìm người dễ bỏ quy trình.

Một thiết kế có thể phối hợp:

- Giới hạn tốc độ và khối lượng theo các phạm vi phù hợp.
- Giới hạn kích thước dữ liệu, nội dung tự do và tệp đính kèm.
- Phát hiện hồ sơ lặp nhưng không tự tiết lộ rằng người khác đã mở hồ sơ.
- Ghi lịch sử chuyển người xử lý để tránh xác minh lại theo tiêu chuẩn thấp hơn.
- Tách quyền tiếp nhận, đánh giá và thực hiện thay đổi nhạy cảm.
- Theo dõi việc yêu cầu đổi kênh, thay thông tin hoặc bỏ bước nhiều lần.

Không khóa tài khoản của nạn nhân chỉ vì có quá nhiều ticket chưa xác minh. Kiểm soát lạm dụng cần bảo vệ khả năng sử dụng của chủ tài khoản và khả năng xử lý của đội hỗ trợ.

Không gộp hai hồ sơ chỉ vì cùng tên, IP hoặc cùng số điện thoại khai báo. Việc liên kết cần có căn cứ và quyền truy cập phù hợp để tránh làm lộ trao đổi của người khác.

Mỗi lần bàn giao nên giữ được: nội dung đã được khai báo, nội dung nào đã được kiểm tra, ai kiểm tra, theo quy trình nào và việc gì còn chưa đạt. Một câu “khách hàng đã qua hỗ trợ trước đó” không đủ.

Mã hồ sơ dùng để tham chiếu, không mặc nhiên cấp quyền đọc toàn bộ ticket. Nếu có trang theo dõi cho người chưa đăng nhập, phải thiết kế cơ chế kiểm soát truy cập riêng thay vì chỉ dựa vào việc biết caseRef.

## 11. Phản hồi, quyền nhân viên và bảo vệ dữ liệu

Nhân viên tiếp nhận cần mẫu hướng dẫn rõ ràng, nhưng không nên công bố ngưỡng chống gian lận hoặc nội dung xác minh nội bộ giúp người gọi điều chỉnh câu chuyện.

Một phản hồi có thể gồm:

```text
Hồ sơ của bạn đã được tiếp nhận với mã tham chiếu được cung cấp.

Bước tiếp theo là kiểm tra thông tin theo quy trình hỗ trợ truy cập.
Chúng tôi chưa thay đổi mật khẩu hoặc phương thức xác thực.

Không gửi mật khẩu, OTP, mã khôi phục hay ảnh giấy tờ trong thư trả lời này.
Nếu cần thêm bước xác minh, hãy thực hiện trên kênh chính thức được hướng dẫn.

Việc có mã hồ sơ không thay thế các điều kiện khôi phục tài khoản.
```

Không hứa chắc thời điểm hoàn tất hoặc kết quả cấp lại quyền khi còn chờ xác minh. Có thể nêu thời gian xử lý dự kiến theo cam kết vận hành thực tế, đồng thời phân biệt thời gian xem hồ sơ với thời gian khôi phục thành công.

Quyền của nhân viên tiếp nhận nên đủ để xem và cập nhật hồ sơ được giao, không tự bao gồm quyền gỡ MFA, sửa passkey, đọc toàn bộ bằng chứng hoặc xuất dữ liệu hàng loạt.

Ghi audit việc tạo hồ sơ, thay đổi dữ liệu liên hệ, chuyển hàng đợi và truy cập nhạy cảm. Tách actor người yêu cầu, nhân viên xử lý và tài khoản mục tiêu; không ghi chủ tài khoản là người khởi tạo khi mới có dữ liệu khai báo.

Đặt chính sách lưu giữ cho ticket, bản ghi cuộc gọi và tệp đính kèm. Không sao chép dữ liệu nhạy cảm sang log vận hành hoặc các kênh trao đổi không có kiểm soát chỉ để bàn giao thuận tiện.

Nếu người dùng tự gửi bí mật hoặc giấy tờ ngoài quy trình, cần xử lý theo cơ chế bảo vệ dữ liệu đã được định nghĩa, tránh tiếp tục chuyển tiếp nguyên nội dung cho nhiều người.

## 12. Tình huống minh họa

### Mất điện thoại MFA nhưng còn phương thức khác

Nhân viên tiếp nhận ghi loại phương thức bị mất và tình trạng phương thức còn lại do người dùng khai báo. Nếu có đường tự phục vụ phù hợp, hướng dẫn người dùng thực hiện tại giao diện chính thức. Không yêu cầu họ đọc OTP cho nhân viên hoặc tắt MFA để rút ngắn thao tác.

### Không còn truy cập email và khóa bảo mật

Hồ sơ được chuyển sang đường xem xét được chính sách cho phép. Email mới được ghi là kênh liên lạc đề xuất với trạng thái rõ ràng; nó không tự trở thành nơi nhận quyền khôi phục.

### Người gọi nói mình là quản lý và cần xử lý ngay

Nhân viên ghi nhận mức độ khẩn cấp, nhưng vẫn giữ điều kiện xác minh và phạm vi quyền. Danh xưng, chức vụ hoặc sự thúc ép không thay thế bằng chứng.

### Người dùng báo tài khoản vừa bị chiếm

Intake ghi nhận nghi vấn và chuyển đúng cơ chế xử lý sự cố. Các biện pháp bảo vệ được đánh giá theo chính sách; việc gửi một báo cáo chưa xác minh không tự cho phép thay credential hoặc khóa toàn bộ tài khoản.

### Hồ sơ trước chưa hoàn tất nhưng người gọi mở hồ sơ mới

Hệ thống đối chiếu và bàn giao theo quyền truy cập phù hợp. Không để hồ sơ mới làm mất lịch sử điều kiện chưa đạt hoặc tạo cơ hội chọn nhân viên khác để né xác minh.

Support recovery intake hiệu quả khi người gặp sự cố nhận được hướng đi rõ ràng và đội xử lý nhận được hồ sơ có cấu trúc, mức tin cậy minh bạch. Giữ ranh giới giữa tiếp nhận, xác minh và cấp quyền giúp hỗ trợ người dùng mà không biến hỗ trợ thành một phương thức chiếm tài khoản.