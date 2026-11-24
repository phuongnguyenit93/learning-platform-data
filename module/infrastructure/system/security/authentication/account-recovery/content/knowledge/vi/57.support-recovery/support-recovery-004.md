# Support evidence checklist

## 1. Checklist bằng chứng dùng để quyết định điều gì?

Khi xử lý yêu cầu khôi phục tài khoản, nhân viên hỗ trợ có thể nhận được ảnh giấy tờ, email, ảnh màn hình, mô tả thiết bị bị mất hoặc kết quả xác minh từ hệ thống. Nếu chỉ đếm số tài liệu đã nhận, nhiều thông tin yếu có thể bị hiểu nhầm thành đủ bằng chứng sở hữu tài khoản.

Support evidence checklist là danh sách các điều kiện phải được đối chiếu đối với bằng chứng của một hồ sơ hỗ trợ. Mỗi mục cần nói rõ điều gì phải được chứng minh, nguồn nào được chấp nhận, ai kiểm tra và kết quả đó còn giá trị trong phạm vi nào.

Checklist có ba nhiệm vụ:

- Giúp người xử lý không bỏ sót điều kiện bắt buộc của quy trình.
- Tách lời khai, tài liệu đã nhận và kết quả đã xác minh.
- Tạo hồ sơ quyết định có thể bàn giao và đối chiếu.

Một checklist đã điền không tự cấp quyền khôi phục. Việc phê duyệt và thực thi vẫn phải kiểm tra quyền, trạng thái request và điều kiện hiện hành của tài khoản.

[OWASP Multifactor Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html#resetting-mfa) lưu ý rằng hỗ trợ lấy lại quyền truy cập khi mất MFA phải tránh tạo đường vượt MFA cho kẻ tấn công. Danh sách bằng chứng cần phục vụ điều kiện đó thay vì trở thành thủ tục đánh dấu cho đủ ô.

## 2. Chọn chính sách trước khi chọn bằng chứng

Không có một bộ “ba giấy tờ bất kỳ” phù hợp cho mọi tài khoản và mọi loại khôi phục.

Trước khi thu thập, cần xác định:

| Ngữ cảnh | Câu hỏi phải trả lời |
| --- | --- |
| Phạm vi tài khoản | Đúng dịch vụ, tenant và tài khoản nào? |
| Hành động yêu cầu | Đặt lại mật khẩu, thay MFA, ràng buộc passkey hay thay thông tin recovery? |
| Tình trạng truy cập | Còn phương thức nào có thể xác thực theo chính sách? |
| Nền tảng danh tính | Tài khoản có hồ sơ identity proofing đã được thiết lập không? |
| Rủi ro hiện tại | Có nghi ngờ bị chiếm quyền hoặc phương thức bị lộ không? |
| Quy trình được phép | Những tổ hợp bằng chứng và đường ngoại lệ nào đã được phê duyệt? |
| Phiên bản áp dụng | Chính sách và checklist phiên bản nào được sử dụng? |

[NIST SP 800-63B-4](https://pages.nist.gov/800-63-4/sp800-63b/events/#account-recovery-methods) phân biệt các phương thức khôi phục và nêu yêu cầu khác nhau theo nền tảng danh tính, mức đảm bảo. Phương thức đặc thù ứng dụng phải dựa trên phân tích rủi ro được tài liệu hóa. Nhân viên hỗ trợ không nên tự thay tổ hợp bắt buộc bằng những dữ liệu dễ thu thập hơn.

Checklist trong bài là mô hình thiết kế minh họa. Nó không xác định thay tổ hợp bằng chứng bắt buộc của NIST hoặc chính sách riêng của một sản phẩm.

Nếu hành động thay đổi từ đặt lại mật khẩu sang thay MFA hoặc thay cả địa chỉ recovery, phải đánh giá lại phạm vi. Không mặc định kết quả đủ cho hành động đầu tiên cũng đủ cho hành động mới.

## 3. Phân loại bằng chứng và giới hạn của từng loại

| Loại thông tin hoặc bằng chứng | Điều có thể hỗ trợ chứng minh | Giới hạn cần kiểm tra |
| --- | --- | --- |
| Mã khôi phục được trình qua bộ xác minh | Đáp ứng điều kiện khôi phục được hệ thống định nghĩa | Đúng tài khoản, mục đích, request, hạn dùng và quy tắc một lần |
| Kết quả xác thực bằng phương thức còn dùng được | Kiểm soát credential đã ràng buộc theo cơ chế xác thực | Phương thức còn hợp lệ và mức xác thực đủ cho hành động |
| Kiểm soát kênh đã đăng ký | Khả năng nhận thông tin tại kênh được phép | Kênh có thể bị chiếm, vừa thay hoặc không đủ khi đứng riêng |
| Recovery contact đã thiết lập | Đáp ứng quy trình liên hệ dự phòng | Không tự biến người quen mới được khai báo thành contact đáng tin |
| Kết quả identity proofing hoặc reproofing | Xác minh theo quy trình danh tính được áp dụng | Phải gắn với danh tính và tài khoản đã thiết lập đúng cách |
| Lịch sử giao dịch hoặc hành vi | Hỗ trợ đối chiếu và đánh giá rủi ro | Có thể bị biết, lấy cắp hoặc không đủ làm bằng chứng quyết định |
| Ảnh màn hình hoặc nội dung email | Hỗ trợ hiểu diễn biến hoặc tìm hồ sơ | Không tự chứng minh tính xác thực hoặc quyền sở hữu tài khoản |
| Tên, ngày sinh, địa chỉ khai báo | Hỗ trợ tìm kiếm hoặc đối chiếu | Có thể là dữ liệu công khai hoặc đã bị lộ |

Không coi một bản chụp màn hình nói “đã xác minh” là kết quả xác minh có thẩm quyền. Cần lấy kết quả từ hệ thống, nguồn hoặc người kiểm tra được quy trình cho phép.

Một địa chỉ email mới có thể được xác nhận để liên lạc về hồ sơ. Điều đó không tự chứng minh quyền sở hữu tài khoản hoặc quyền nhận mã recovery cho tài khoản.

Cũng không nên coi số lượng bằng chứng là thước đo duy nhất. Ba ảnh chụp cùng một email không tạo ra ba nguồn độc lập.

## 4. Đánh giá chất lượng bằng chứng theo nhiều chiều

Một bằng chứng có vẻ phù hợp vẫn có thể không dùng được trong quyết định hiện tại.

### Nguồn và tính xác thực

Bằng chứng đến từ nơi nào, ai phát hành, ai thu thập và bằng cách nào xác nhận nó chưa bị thay thế hoặc giả mạo? Tệp do người yêu cầu tải lên và kết quả kiểm tra từ một hệ thống được tin cậy là hai nguồn khác nhau.

### Ràng buộc với tài khoản và hành động

Kết quả phải liên quan đúng tài khoản, tenant, request và mục đích. Một lần xác nhận email liên lạc không được đổi nhãn thành xác nhận quyền thay MFA.

### Thời điểm và hiệu lực

Cần biết bằng chứng được kiểm tra khi nào, có hết hạn hoặc bị thu hồi không, và điều kiện nào làm kết quả không còn phù hợp.

### Tính độc lập và nguồn bị chiếm

Hai bằng chứng phụ thuộc cùng hộp thư có thể cùng bị ảnh hưởng nếu hộp thư đã bị chiếm. Không coi việc chúng có hai định dạng khác nhau là đã đáp ứng yêu cầu độc lập.

### Mâu thuẫn và phạm vi kết luận

Nếu một bằng chứng chỉ chứng minh việc kiểm soát kênh liên lạc, ghi đúng kết luận đó. Nếu có thông tin mâu thuẫn, phải đánh giá hoặc chuyển xử lý, không bỏ qua vì những ô khác đã được đánh dấu.

Với tài liệu danh tính, [NIST SP 800-63A-4](https://pages.nist.gov/800-63-4/sp800-63a/proofing/) phân biệt resolution, validation và verification: xác định danh tính được khai, kiểm tra tính xác thực của bằng chứng và xác nhận người trình là người gắn với bằng chứng. Nhận một ảnh giấy tờ không đồng nghĩa đã hoàn thành cả ba công việc.

## 5. Mẫu checklist làm việc

Bảng dưới là mẫu câu hỏi cho hồ sơ, không phải kết quả kiểm tra một người dùng cụ thể.

| Mục | Nội dung cần đối chiếu | Nguồn hoặc kết quả cần lưu |
| --- | --- | --- |
| C1. Chính sách | Đúng loại khôi phục và phiên bản chính sách chưa? | Policy reference, phiên bản, hành động yêu cầu |
| C2. Đối tượng | Đúng tài khoản, tenant và request chưa? | Tham chiếu đã được máy chủ đối chiếu |
| C3. Khả năng áp dụng | Bằng chứng thuộc loại được phép dùng cho trường hợp này không? | Yêu cầu chính sách mà bằng chứng phục vụ |
| C4. Nguồn | Có nguồn kiểm tra có thẩm quyền không? | Verifier reference hoặc principal người kiểm tra |
| C5. Xác thực nội dung | Tính hợp lệ hoặc tính xác thực đã được đánh giá theo quy trình chưa? | Kết quả kiểm tra và lý do có kiểm soát |
| C6. Ràng buộc người yêu cầu | Kết quả liên hệ với người yêu cầu hiện tại bằng cách nào? | Interaction, verification transaction hoặc cơ chế liên kết |
| C7. Hiệu lực | Còn thời hạn và chưa bị vô hiệu theo chính sách không? | Thời điểm kiểm tra, hạn hoặc điều kiện mất hiệu lực |
| C8. Dùng một lần | Quy tắc tiêu thụ hoặc chống phát lại được đáp ứng chưa? | Tham chiếu trạng thái và kết quả từ bộ xác minh |
| C9. Tổ hợp | Đủ tổ hợp bắt buộc và tính độc lập chưa? | Kết quả từng yêu cầu, không chỉ tổng số tài liệu |
| C10. Mâu thuẫn | Có dấu hiệu bị chiếm hoặc kết quả không nhất quán không? | Đánh giá và đường xử lý phù hợp |
| C11. Quyền xử lý | Người xem xét, người duyệt có đúng quyền không? | Principal, hồ sơ phân công, phê duyệt nếu cần |
| C12. Dấu vết | Có thể dựng lại ai kiểm tra gì, khi nào và theo căn cứ nào không? | Evidence reference, audit event và nhận xét an toàn |

Một bằng chứng không nhất thiết đáp ứng mọi mục. Ví dụ, kết quả xác thực credential không có cùng cách validation với giấy tờ. Checklist cần định nghĩa điều kiện áp dụng theo loại bằng chứng thay vì bắt nhân viên đánh dấu máy móc.

“N/A” chỉ hợp lệ khi chính sách xác định mục đó không áp dụng, kèm lý do. Không dùng N/A để thay cho “chưa kiểm tra” hoặc “khách không cung cấp được”.

## 6. Thu thập và kiểm tra qua kênh được thiết kế

Nhân viên nên yêu cầu người dùng thực hiện bước xác minh qua giao diện chính thức, nơi bộ xác minh có thể kiểm tra ràng buộc và trạng thái. Không thu mã khôi phục hoặc OTP trong ghi chú ticket để một người khác kiểm tra sau.

Hồ sơ hỗ trợ thường chỉ cần giữ:

- Loại bằng chứng và yêu cầu chính sách mà nó phục vụ.
- Tham chiếu tới giao dịch hoặc kho bằng chứng được bảo vệ.
- Kết quả, phạm vi và thời điểm kiểm tra.
- Principal hoặc thành phần đã thực hiện kiểm tra.
- Những điều kiện làm kết quả hết hiệu lực.

Không sao chép mật khẩu, OTP, mã dự phòng, token, seed MFA hoặc private key vào checklist. Không đưa ảnh giấy tờ nguyên bản vào log vận hành chỉ để tiện bàn giao.

Nếu quy trình cần tài liệu danh tính, sử dụng nơi thu thập và lưu giữ phù hợp, với quyền truy cập và thời hạn được xác định. Người có quyền xem trạng thái checklist không mặc nhiên có quyền tải mọi bằng chứng.

Nếu người dùng tự gửi bí mật qua kênh không phù hợp, áp dụng quy trình xử lý đã được định nghĩa. Không tiếp tục chuyển tiếp bí mật cho nhiều nhân viên hoặc coi đó là lý do bỏ qua kiểm tra chính thức.

Không thu thêm dữ liệu chỉ để “phòng khi cần”. Mỗi trường cần có mục đích gắn với một yêu cầu thực tế.

## 7. Ghi trạng thái từng mục một cách rõ ràng

Chỉ một cột “đã có” dễ làm lẫn việc đã nhận và đã xác minh.

| Trạng thái minh họa | Ý nghĩa |
| --- | --- |
| MISSING | Chưa có thông tin hoặc bằng chứng được yêu cầu |
| RECEIVED | Đã tiếp nhận nhưng chưa có kết quả kiểm tra |
| PENDING | Đang chờ kiểm tra hoặc chờ kết quả có thẩm quyền |
| ACCEPTED_FOR_REQUIREMENT | Đã đáp ứng một yêu cầu cụ thể trong phạm vi được ghi |
| REJECTED | Không đáp ứng yêu cầu được xét |
| STALE | Kết quả không còn đủ mới hoặc không còn hiệu lực |
| OUT_OF_SCOPE | Bằng chứng không phục vụ hành động hoặc đối tượng hiện tại |
| CONFLICT | Có mâu thuẫn cần đánh giá trước khi quyết định |
| NOT_APPLICABLE | Không áp dụng theo chính sách đã xác định |

Một mục ACCEPTED_FOR_REQUIREMENT không có nghĩa toàn bộ hồ sơ đã được phê duyệt. Nó chỉ có giá trị đối với yêu cầu được nêu.

Ví dụ cấu trúc một mục nội bộ:

```json
{
  "checkRef": "check_example_17",
  "caseRef": "case_example_84",
  "recoveryRequestRef": "rr_example_52",
  "policyRef": "support-mfa-recovery",
  "policyVersion": "3-example",
  "requirementRef": "RECOVERY_EVIDENCE_A",
  "evidenceRef": "evidence_example_91",
  "evidenceKind": "RECOVERY_VERIFICATION_RESULT",
  "status": "ACCEPTED_FOR_REQUIREMENT",
  "checkedAt": "2026-11-24T12:00:00Z",
  "checkedBy": {
    "kind": "SERVICE",
    "principalRef": "svc_recovery_verifier"
  },
  "subjectRef": "acct_example_24",
  "allowedAction": "REPLACE_MFA",
  "verificationTransactionRef": "verify_example_38",
  "invalidatedBy": [
    "REQUEST_CLOSED",
    "RELEVANT_SECURITY_STATE_CHANGED",
    "POLICY_VALIDITY_WINDOW_EXCEEDED"
  ]
}
```

Các giá trị chỉ là minh họa; không có bí mật hoặc tài liệu định danh nguyên bản. Tham chiếu phải trỏ tới dữ liệu có thẩm quyền và được kiểm soát truy cập, không phải chuỗi do người yêu cầu tự khai.

Nhận xét tự do nên giải thích lý do cần thiết một cách có kiểm soát. Không viết nội dung như “đã thấy mã 123456” hoặc chép toàn bộ dữ liệu giấy tờ.

## 8. Quy tắc một lần và kết quả đã xác minh

Một mã khôi phục có thể được tiêu thụ ngay khi trình thành công, trước khi nhân viên hoàn tất việc xem hồ sơ. Khi đó, checklist cần tham chiếu kết quả kiểm tra đã được ràng buộc và ghi nhận đúng, không yêu cầu người dùng trình lại mã đã dùng.

Cần phân biệt:

- Mã nguồn đang được đem trình lần đầu.
- Kết quả xác minh đã được ghi cho đúng request và mục đích.
- Quyền khôi phục giới hạn được tạo sau khi đủ điều kiện.
- Việc dùng quyền đó để thực hiện thay đổi cụ thể.

Bằng chứng đã tiêu thụ đúng trong một bước xác minh không tự trở thành “không hợp lệ” chỉ vì nó không thể trình lại. Ngược lại, một kết quả cũ không được tái sử dụng để cấp một quyền mới ngoài phạm vi ban đầu.

Checklist phải lấy trạng thái từ nơi xử lý có thẩm quyền, không từ ảnh chụp cho biết mã “chưa dùng”. Nếu có cạnh tranh giữa nhiều request, cơ chế một lần phải được bảo vệ ở nguồn chung phù hợp.

Không làm mã đã dùng hợp lệ trở lại chỉ vì nhân viên cần hoàn thiện hồ sơ hoặc vì một bước tiếp theo bị lỗi. Cách retry và đối chiếu phải giữ đúng hợp đồng dùng một lần.

## 9. Đưa ra quyết định theo yêu cầu, không theo tổng điểm tùy ý

Một cách quyết định minh họa:

```text
Xác định chính sách và hành động yêu cầu
  -> tìm các bằng chứng được phép áp dụng
  -> kiểm tra từng điều kiện bắt buộc
  -> kiểm tra tổ hợp và quan hệ phụ thuộc
  -> xử lý mâu thuẫn, nghi vấn bị chiếm và kết quả hết hiệu lực
  -> yêu cầu bổ sung hoặc chuyển thẩm quyền nếu cần
  -> chỉ chuyển quyết định đủ điều kiện khi mọi cổng bắt buộc đã đạt
```

Không dùng “đạt 8/12 mục” để bù cho một điều kiện bắt buộc còn thiếu. Điểm rủi ro có thể là một đầu vào của chính sách, nhưng không tự thay thế bằng chứng mà quy trình yêu cầu.

Một người có thể có nhiều thông tin lịch sử đúng nhưng không có tổ hợp được phép để thay MFA. Ngược lại, một hồ sơ có ít tài liệu nhưng có kết quả xác minh đúng loại có thể đáp ứng chính sách. Quyết định cần theo ý nghĩa bằng chứng.

Nếu có dấu hiệu gian lận, không tự kết luận người yêu cầu là kẻ tấn công chỉ vì một điểm không khớp. Có thể có thay đổi tên, lỗi dữ liệu hoặc nhu cầu hỗ trợ tiếp cận. Chuyển đường đánh giá hoặc ngoại lệ được phép mà không tự hạ mức đảm bảo.

Việc duyệt bởi hai người, nếu chính sách yêu cầu, là kiểm soát trách nhiệm. Hai người cùng nhìn một bằng chứng yếu không tự làm bằng chứng đó mạnh hơn hoặc độc lập hơn.

## 10. Kiểm tra lại tại điểm phê duyệt và thực thi

Hồ sơ có thể kéo dài nhiều ngày. Kết quả đủ điều kiện lúc xem xét ban đầu có thể không còn phù hợp khi thao tác thật sự được thực hiện.

Các thay đổi có thể cần đánh giá lại gồm:

- Request đã đóng, hết hạn hoặc bị thu hồi.
- Phạm vi hành động hoặc tài khoản mục tiêu đã thay đổi.
- Credential liên quan bị thu hồi hoặc bị xác định đã lộ.
- Địa chỉ recovery vừa bị thay đổi.
- Một lần khôi phục khác đã thay đổi trạng thái bảo mật tài khoản.
- Quyền nhân viên hoặc hiệu lực phê duyệt không còn đáp ứng chính sách.
- Phiên bản chính sách thay đổi và quy định chuyển tiếp yêu cầu đánh giá lại.

Không mặc định mọi cập nhật policy đều làm mất hiệu lực mọi hồ sơ; tổ chức cần quy tắc phiên bản và chuyển tiếp rõ ràng. Nhưng cũng không mặc định hồ sơ được quyền dùng mãi chính sách cũ.

Tại điểm thực thi, máy chủ cần kiểm tra lại những điều kiện hiện hành bắt buộc. Một ảnh checklist hoặc trạng thái “đã duyệt” do giao diện gửi không thay thế kiểm tra đó.

Nếu việc cấp quyền khôi phục diễn ra sau đánh giá, quyền phải có phạm vi và hiệu lực riêng. Nó không nên trở thành một liên kết đăng nhập toàn quyền chỉ vì checklist đã hoàn thành.

## 11. Bàn giao, bảo vệ dữ liệu và khả năng đối chiếu

Một bản bàn giao nên cho người tiếp nhận biết:

| Nội dung | Điều cần giữ rõ |
| --- | --- |
| Quyết định đang xét | Hành động, tài khoản, tenant và request |
| Chính sách áp dụng | Phiên bản và đường khôi phục được chọn |
| Bằng chứng đã kiểm tra | Tham chiếu, nguồn, thời điểm và kết quả cụ thể |
| Giới hạn | Điều chưa chứng minh, kết quả hết hạn hoặc mâu thuẫn |
| Trách nhiệm | Ai kiểm tra, ai phê duyệt nếu có, ai có quyền thực thi |
| Bước tiếp theo | Bổ sung, xem xét ngoại lệ, từ chối hoặc chuyển đủ điều kiện |

Không dùng câu “đã xác minh khách hàng” nếu hồ sơ chỉ xác nhận họ nhận được thư tại địa chỉ liên lạc mới. Không để một lần chuyển nhân viên biến kết quả PENDING thành ACCEPTED mà không có kiểm tra mới.

Nhật ký cần tách người yêu cầu, nhân viên xem xét và tài khoản mục tiêu. Việc sửa kết quả phải có nguồn, lý do và dấu vết; không âm thầm thay lịch sử để hợp thức hóa quyết định đã thực hiện.

Quyền xem checklist, quyền đọc bằng chứng nguyên bản và quyền thực hiện recovery nên được phân biệt. Theo dõi truy cập nhạy cảm và quản lý bản xuất hoặc bản sao theo mục đích.

Đặt thời hạn lưu cho từng loại dữ liệu. Khi chỉ cần giữ kết quả và tham chiếu, không mặc định phải giữ toàn bộ giấy tờ hoặc hội thoại vĩnh viễn.

## 12. Tình huống minh họa

### Nhiều ảnh chụp nhưng chỉ một nguồn

Người yêu cầu gửi ảnh inbox, ảnh thông báo và một PDF được tải từ cùng hộp thư. Checklist ghi nhận chúng liên quan cùng nguồn kiểm soát. Không tự tính thành ba bằng chứng độc lập khi hộp thư là phần đang bị nghi chiếm.

### Giấy tờ hợp lệ nhưng chưa gắn với tài khoản

Một tài liệu có thể vượt qua kiểm tra tính xác thực, nhưng hồ sơ vẫn chưa chứng minh người trình liên quan tới tài khoản cần khôi phục. Không chuyển kết quả validation thành quyền thay MFA.

### Mã khôi phục đã được xác minh ở bước trước

Nhân viên xem kết quả từ bộ xác minh, đối chiếu request và phạm vi. Không yêu cầu gửi lại mã trong chat, không phục hồi mã đã dùng và không dùng kết quả đó cho một request mới.

### Hồ sơ đủ điều kiện nhưng tài khoản vừa thay trạng thái

Trước khi thực thi, hệ thống phát hiện một thay đổi bảo mật liên quan. Checklist và quyết định được đối chiếu lại theo chính sách; không cố hoàn tất chỉ vì nhân viên đã đánh dấu đủ ô hôm trước.

### Người dùng không thể cung cấp loại tài liệu thông thường

Nhân viên chuyển quy trình hỗ trợ hoặc ngoại lệ được tổ chức cho phép, ghi rõ bằng chứng còn thiếu và thẩm quyền cần thiết. Không tự thay bằng câu hỏi dễ đoán hoặc một lời xác nhận miệng.

Support evidence checklist có giá trị khi mỗi kết quả thể hiện đúng yêu cầu đã được chứng minh, nguồn kiểm tra và phạm vi hiệu lực. Điều đó giúp xử lý nhất quán và bàn giao rõ ràng mà không biến số lượng tài liệu hoặc dấu tích của nhân viên thành quyền chiếm tài khoản.