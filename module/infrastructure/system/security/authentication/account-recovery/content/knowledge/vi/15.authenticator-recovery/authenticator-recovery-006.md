# Authenticator reset approval — Phê duyệt đặt lại phương tiện xác thực

## 1. Mục tiêu và phạm vi bài học

Trong chương **Authenticator Recovery** của module **SECURITY_AUTHENTICATION_ACCOUNT_RECOVERY**, bài học này giải quyết một câu hỏi: **ai được phép phê duyệt việc đặt lại authenticator, dựa trên bằng chứng nào và trong những giới hạn nào?**

Authenticator là phương tiện chứng minh quyền truy cập tài khoản, chẳng hạn ứng dụng TOTP, khóa bảo mật hoặc passkey. Khi người dùng mất điện thoại, mất khóa hoặc không còn truy cập được phương tiện xác thực, việc cho phép đăng ký phương tiện mới có thể trao toàn bộ tài khoản cho người đưa ra yêu cầu. Vì vậy, phê duyệt reset là một quyết định an ninh có phạm vi cụ thể.

Sau bài học, người học có thể:

- Phân biệt xác minh người yêu cầu, phê duyệt reset, thực thi reset và cấp phiên đăng nhập.
- Xây dựng chính sách quyết định theo bằng chứng, mức đảm bảo và nguy cơ chiếm đoạt tài khoản.
- Thiết kế quyền của nhân viên hỗ trợ, người phê duyệt và dịch vụ thực thi.
- Ràng buộc quyết định với đúng tài khoản, phương tiện, phiên bản yêu cầu và thời hạn.
- Xử lý đồng thời, token dùng một lần, thu hồi session và lỗi giữa nhiều dịch vụ.

Các bảng quyết định, trạng thái, tên API và mã giả dưới đây là **thiết kế tham khảo của bài học**. Chúng cần được điều chỉnh theo mô hình đe dọa, quy trình xác minh danh tính và kiến trúc triển khai. Các mốc thời gian minh họa không phải ngưỡng bắt buộc của NIST hay OWASP.

## 2. Phê duyệt chính xác là phê duyệt điều gì?

Một quyết định rõ ràng có thể được diễn đạt như sau:

> Cho phép tài khoản U, trong tenant T, thay authenticator A đã khai báo bị mất bằng một authenticator thuộc loại B, thông qua luồng đăng ký giới hạn R, trước thời điểm E, sau khi hoàn thành các điều kiện C.

Quyết định này không có nghĩa là “người cầm mã được toàn quyền với tài khoản”.

| Khâu | Câu hỏi cần trả lời | Kết quả phù hợp |
| --- | --- | --- |
| Tiếp nhận yêu cầu | Người yêu cầu muốn thay gì, vì lý do nào? | Hồ sơ recovery đang chờ xử lý |
| Xác minh | Bằng chứng có đủ để gắn người yêu cầu với tài khoản không? | Kết quả xác minh có phương pháp, thời gian và phạm vi |
| Phê duyệt | Chính sách có cho phép thay phương tiện này trong bối cảnh hiện tại không? | Quyết định giới hạn, có thể hết hạn hoặc bị thu hồi |
| Thực thi | Quyết định còn hiệu lực và phương tiện mới đã được chứng minh quyền kiểm soát chưa? | Cập nhật authenticator và các hàng rào bảo vệ |
| Đăng nhập sau reset | Người dùng có xác thực được bằng cấu hình mới không? | Session ứng dụng mới theo chính sách đăng nhập |

Một người có thể vượt qua xác minh nhưng chưa được phép reset ngay, ví dụ vì tài khoản đang có tranh chấp quyền sở hữu. Ngược lại, một nhân viên có quyền duyệt không được bỏ qua xác minh chỉ vì họ quen người yêu cầu.

Nếu người dùng vẫn có thể xác thực đủ mức đảm bảo bằng phương tiện đã đăng ký khác, tình huống có thể thuộc luồng gắn hoặc thay authenticator thông thường. NIST phân biệt trường hợp này với recovery khi không còn đủ phương tiện để xác thực ở mức mong muốn. [NIST SP 800-63B-4, Authenticator Event Management](https://pages.nist.gov/800-63-4/sp800-63b/events/)

**Phạm vi reset cần tối thiểu:** mất một khóa bảo mật không mặc nhiên dẫn đến xóa toàn bộ passkey, đổi email, đổi mật khẩu và tắt MFA. Mỗi thay đổi bổ sung cần một căn cứ và quyền riêng.

## 3. Mô hình đe dọa dành riêng cho phê duyệt reset

### 3.1. Đường tấn công điển hình

Kẻ tấn công có mật khẩu bị lộ nhưng không có yếu tố thứ hai. Họ gọi bộ phận hỗ trợ, tự nhận vừa mất điện thoại và yêu cầu xóa TOTP. Nếu bộ phận hỗ trợ coi việc biết mật khẩu, ngày sinh hoặc mã nhân viên là đủ, kẻ tấn công sẽ biến recovery thành đường vòng vượt MFA.

Những tình huống khác cần đưa vào thiết kế:

| Năng lực của đối tượng | Điểm có thể bị lợi dụng | Kiểm soát trong thiết kế tham khảo |
| --- | --- | --- |
| Kiểm soát email của nạn nhân | Nhận cả mã xác minh và thư thông báo | Không cộng hai tín hiệu cùng hộp thư thành hai bằng chứng độc lập |
| Chiếm một session đang mở | Yêu cầu thêm passkey rồi xóa khóa cũ | Yêu cầu bằng chứng mới phù hợp với nhánh xử lý |
| Giả giọng, giả video hoặc dùng dữ liệu công khai | Thuyết phục helpdesk bằng câu chuyện khẩn cấp | Kịch bản xác minh cố định; xác minh lại qua kênh đã thiết lập |
| Chiếm tài khoản nhân viên hỗ trợ | Tự tạo và tự duyệt hồ sơ | Quyền hẹp, kiểm tra tenant, phân tách người xử lý |
| Gửi nhiều yêu cầu song song | Tái sử dụng bằng chứng hoặc lợi dụng hai lần duyệt | Liên kết bằng chứng với yêu cầu, khóa và kiểm tra phiên bản |
| Sửa yêu cầu sau khi đã duyệt | Biến reset một khóa thành reset toàn bộ MFA | Quyết định gắn với snapshot bất biến |
| Đăng ký thêm credential trong lúc recovery | Giữ đường truy cập sau khi nạn nhân khôi phục | Kiểm kê authenticator và phát hiện thay đổi phiên bản |

### 3.2. Bằng chứng và tín hiệu rủi ro là hai thứ khác nhau

Bằng chứng xác minh hỗ trợ kết luận về quyền sở hữu hoặc quyền kiểm soát. Tín hiệu rủi ro hỗ trợ quyết định cần kiểm tra thêm hay có dấu hiệu gian lận.

- Mã khôi phục đã cấp trước và được xác thực thành công là một loại bằng chứng.
- Kết quả kiểm tra danh tính theo quy trình được chấp nhận là một loại bằng chứng.
- IP quen thuộc, quốc gia thường dùng hoặc thiết bị có cookie cũ là tín hiệu ngữ cảnh.
- Câu chuyện hợp lý, tên người quản lý hoặc thái độ hợp tác không tự tạo ra bằng chứng kỹ thuật.

Không cho phép điểm rủi ro thấp bù cho việc thiếu bằng chứng tối thiểu. Hai tín hiệu thuận lợi cũng không tự tạo thành MFA.

OWASP xem việc thay yếu tố xác thực là thao tác rủi ro cao, khuyến nghị xác thực lại và cảnh báo không chỉ dựa vào session đang tồn tại. [OWASP Multifactor Authentication Cheat Sheet, Changing MFA Factors](https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html#changing-mfa-factors)

## 4. Chính sách ra quyết định

### 4.1. Các điều kiện trước khi xét duyệt

Thiết kế tham khảo sử dụng năm nhóm điều kiện:

1. **Đúng đối tượng:** tài khoản và tenant được xác định phía máy chủ; actor có quyền thao tác với đối tượng đó.
2. **Đủ bằng chứng:** phương pháp recovery được tổ chức chấp nhận cho mức đảm bảo mục tiêu, còn hiệu lực và đúng yêu cầu.
3. **Đúng phạm vi:** danh sách authenticator cần thay hoặc thu hồi được xác định rõ.
4. **Đủ thẩm quyền:** người phê duyệt có vai trò phù hợp; đáp ứng phân tách nhiệm vụ nếu chính sách yêu cầu.
5. **Không có điều kiện chặn:** không có tranh chấp chưa xử lý, bằng chứng bị thu hồi hoặc biến động an ninh chưa đánh giá.

Điều kiện 2 là cổng bắt buộc. Chỉ sau khi vượt qua cổng này, đánh giá rủi ro mới quyết định có cần thêm người duyệt, thời gian chờ hoặc điều tra hay không.

### 4.2. Bảng quyết định minh họa

| Hoàn cảnh | Hướng xử lý | Điều kiện để đi tiếp |
| --- | --- | --- |
| Còn một authenticator khác đủ mức đảm bảo | Chuyển sang luồng thay authenticator có xác thực lại | Chứng minh kiểm soát phương tiện còn lại và kiểm tra chính sách |
| Không còn MFA nhưng có bộ bằng chứng recovery đáp ứng chính sách | Có thể duyệt tự động theo quy tắc | Không có điều kiện chặn; quyết định vẫn có phạm vi và audit |
| Chỉ biết mật khẩu và dữ liệu hồ sơ công khai | Chưa đủ điều kiện duyệt | Bổ sung phương thức recovery được chấp nhận |
| Email nhận mã vừa được thay đổi | Tạm dừng đánh giá; kiểm tra chuỗi thay đổi | Có căn cứ độc lập; không tin địa chỉ mới chỉ vì nó đang nằm trong hồ sơ |
| Tài khoản quản trị có bằng chứng hợp lệ | Chuyển nhánh phê duyệt đặc quyền | Hai người phù hợp, độc lập và còn đủ quyền tại thời điểm thực thi |
| Có dấu hiệu credential bị chiếm hoặc có tranh chấp | Chuyển xử lý sự cố; chưa cấp quyền reset | Điều tra và chính sách xử lý sự cố quyết định bước kế tiếp |
| Không còn bất kỳ phương pháp recovery được chấp nhận nào | Từ chối phê duyệt ở trạng thái hiện tại | Hướng dẫn quy trình thay thế đã được tổ chức phê chuẩn, nếu có |

“Chưa đủ điều kiện” khác với “chứng minh người yêu cầu là kẻ tấn công”. Sản phẩm cần diễn đạt rõ điều còn thiếu, đồng thời tránh tiết lộ dữ liệu có thể giúp lần yêu cầu sau giả mạo tốt hơn.

Nếu dùng khái niệm **AAL** — mức đảm bảo xác thực — cần đánh giá toàn bộ phương thức recovery và quy trình gắn authenticator theo yêu cầu áp dụng. Việc hai nhân viên bấm duyệt hoặc chọn thời gian chờ dài không tự nâng AAL.

### 4.3. Không suy diễn tính độc lập của bằng chứng

Email xác nhận và email thông báo gửi vào cùng hộp thư chỉ có một điểm kiểm soát. SMS và ứng dụng xác thực trên cùng điện thoại có thể cùng bị mất hoặc bị truy cập khi điện thoại bị chiếm.

Trong hồ sơ, cần mô tả khả năng cùng thất bại thay vì chỉ đếm số lượng bằng chứng. Một người quản lý xác nhận quan hệ lao động có thể bổ sung ngữ cảnh; điều đó không mặc nhiên chứng minh người đang gọi là chủ tài khoản.

## 5. Hồ sơ để người duyệt có thể ra quyết định

Giao diện duyệt cần hiển thị đủ dữ kiện và ảnh hưởng của hành động.

| Nhóm dữ liệu | Nội dung nên có |
| --- | --- |
| Định danh hồ sơ | Mã yêu cầu, tenant, tài khoản đã che một phần, thời điểm tạo |
| Yêu cầu thực tế | Loại authenticator bị mất; các ID dự kiến thu hồi; loại phương tiện được phép đăng ký |
| Xác minh | Phương pháp, bên xác minh, kết quả, thời điểm, thời hạn, tham chiếu bằng chứng |
| Rủi ro | Biến động thiết bị, thay đổi kênh recovery, các yêu cầu gần đây, dấu hiệu cần điều tra |
| Chính sách | Phiên bản chính sách, điều kiện bắt buộc, số người duyệt, thời gian chờ |
| Ảnh hưởng | Session nào bị thu hồi; có hạn chế tác vụ nhạy cảm sau recovery không |
| Trách nhiệm | Người tiếp nhận, người xác minh, các quyết định trước và lý do |

Người duyệt nên thấy một mô tả cụ thể như:

> Thu hồi khóa bảo mật kết thúc bằng 81D2; cho phép đăng ký một passkey có user verification; kết thúc các phiên cũ sau khi hoàn tất. Yêu cầu không bao gồm đổi email hoặc hạ yêu cầu MFA.

Ghi chú tự do là dữ liệu không đáng tin cậy: escape nội dung trên giao diện, kiểm soát liên kết và tệp đính kèm, tránh thực thi HTML. Không hiển thị QR TOTP, recovery code, token reset hoặc giấy tờ đầy đủ cho người không cần truy cập.

Hồ sơ nên lưu tham chiếu tới kho bằng chứng được phân quyền, thay vì sao chép dữ liệu định danh nhạy cảm vào nhiều hệ thống ticket.

## 6. Vai trò, phân tách nhiệm vụ và phê duyệt đặc quyền

Thiết kế tham khảo phân chia quyền như sau:

| Vai trò | Có thể làm | Giới hạn |
| --- | --- | --- |
| Người yêu cầu | Cung cấp bằng chứng, xem tiến độ phù hợp, hủy yêu cầu của mình | Không tự xác nhận bằng chứng là hợp lệ |
| Nhân viên tiếp nhận | Tạo hồ sơ, hướng dẫn, chuyển nhóm | Không tự cấp quyền reset |
| Nhân viên xác minh | Thực hiện quy trình được giao, ghi kết quả | Không tự nâng tiêu chuẩn đạt hoặc sửa lịch sử |
| Người phê duyệt | Duyệt hoặc từ chối theo phạm vi được phân công | Không duyệt ngoài tenant hoặc vượt mức quyền |
| Dịch vụ thực thi | Tiêu thụ quyết định hợp lệ và áp dụng thay đổi | Không tự bỏ qua điều kiện thiếu |
| Nhóm an ninh | Điều tra tranh chấp, xử lý ngoại lệ được quản trị | Mọi hành động vẫn có danh tính, căn cứ và audit |

Với tài khoản đặc quyền, quy tắc hai người phải kiểm tra **hai danh tính nhân sự khác nhau**, không chỉ hai username. Không cho cùng người dùng tài khoản phụ để duyệt lần thứ hai. Có thể yêu cầu một người thuộc nhóm an ninh, tùy tổ chức.

Người duyệt cần xác thực lại đủ mới cho thao tác nhạy cảm. Máy chủ kiểm tra quyền ở từng quyết định và kiểm tra lại khi thực thi nếu quyền duyệt có thể đã bị thu hồi.

Trường hợp người dùng không còn authenticator không phải lý do giảm yêu cầu đối với nhân viên duyệt. Nhân viên là một ranh giới tin cậy khác và vẫn phải dùng biện pháp bảo vệ tài khoản nội bộ.

Luồng khẩn cấp cần chính sách riêng: quyền cấp theo thời hạn, phạm vi được kiểm soát và dấu vết đánh giá sau sự kiện. Không triển khai một cờ cho phép mọi nhân viên bỏ qua xác minh với lý do “khẩn cấp”.

## 7. Vòng đời yêu cầu và quyết định

### 7.1. Trạng thái có ý nghĩa nghiệp vụ rõ ràng

~~~mermaid
stateDiagram-v2
    [*] --> SUBMITTED
    SUBMITTED --> VERIFYING
    VERIFYING --> UNDER_REVIEW: Bằng chứng đạt điều kiện
    UNDER_REVIEW --> COOLDOWN: Đã đủ người duyệt, cần chờ
    UNDER_REVIEW --> APPROVED: Đã đủ người duyệt, không cần chờ
    COOLDOWN --> APPROVED: Hết chờ và kiểm tra lại đạt
    APPROVED --> ENROLLING: Cấp quyền đăng ký giới hạn
    ENROLLING --> FINALIZING: Chứng minh kiểm soát phương tiện mới
    FINALIZING --> COMPLETED: Các hàng rào bắt buộc đã hiệu lực
    FINALIZING --> RECOVERY_REQUIRED: Lỗi cần tiếp tục xử lý an toàn
    RECOVERY_REQUIRED --> FINALIZING: Tiếp tục bằng cùng operation
    VERIFYING --> REJECTED
    UNDER_REVIEW --> REJECTED
    APPROVED --> STALE: Điều kiện đã thay đổi
    ENROLLING --> STALE: Điều kiện đã thay đổi
~~~

Sơ đồ rút gọn không vẽ mọi cạnh. Các trạng thái trước khi bắt đầu áp dụng thay đổi có thể chuyển sang **CANCELED** hoặc **EXPIRED** theo chính sách. Trong **FINALIZING**, hủy phải trở thành một thao tác xử lý sự cố hoặc bù trừ có kiểm soát; không chỉ xóa yêu cầu khi credential đã thay đổi.

- **COOLDOWN:** đã có quyết định sơ bộ nhưng chưa được phép dùng quyền reset.
- **APPROVED:** đủ điều kiện để cấp quyền đăng ký; chưa tạo session ứng dụng.
- **ENROLLING:** người yêu cầu chỉ được thực hiện các bước gắn authenticator trong phạm vi đã duyệt.
- **FINALIZING:** đang áp dụng cấu hình và đồng bộ các hàng rào an ninh.
- **COMPLETED:** thay đổi và điều kiện hoàn tất đều đã được xác nhận.
- **STALE:** quyết định không còn áp dụng được vì snapshot thay đổi; cần đánh giá và duyệt lại.
- **RECOVERY_REQUIRED:** tiến trình có thể đã áp dụng một phần; hệ thống giữ hàng rào và chuyển xử lý an toàn.

Lần duyệt đầu trong chính sách hai người chỉ thêm một quyết định con vào hồ sơ. Nó không được chuyển yêu cầu sang APPROVED khi chưa đủ quorum.

### 7.2. Thời gian chờ không thay thế bằng chứng

Ví dụ một sản phẩm chọn chờ 12 giờ cho nhánh mất toàn bộ phương tiện và cho phép grant đăng ký tồn tại 10 phút. Hai con số này chỉ minh họa hai mục đích khác nhau: tạo cơ hội phát hiện gian lận và giới hạn thời gian sử dụng quyền đã cấp.

Khi thời gian chờ kết thúc, hệ thống cần kiểm tra lại:

- Bằng chứng và các quyết định có còn hạn không?
- Có phản đối hoặc cảnh báo mới chưa?
- Quyền của người duyệt và chính sách hiện tại có còn cho phép không?
- Cấu hình an ninh của tài khoản có còn khớp snapshot không?

Nếu bằng chứng hết hạn trước khi kết thúc chờ, phải xác minh lại. Không gia hạn bằng chứng chỉ bằng cách kéo dài TTL của yêu cầu.

## 8. Ràng buộc quyết định với đúng thao tác

### 8.1. Snapshot được duyệt

Một approval nên tham chiếu tới một snapshot bất biến gồm:

~~~text
tenant_id
account_id
request_id
request_revision
operation = REPLACE_AUTHENTICATOR
target_authenticator_ids
allowed_replacement_type
required_verification_properties
evidence_bundle_digest
policy_version
security_config_version
session_revocation_plan
not_before
expires_at
~~~

**security_config_version** biểu diễn các thay đổi có ảnh hưởng đến recovery: thêm hoặc xóa authenticator, thay kênh recovery, thay trạng thái tranh chấp và các sự kiện tương ứng. Không dùng một bộ đếm tăng ở mọi lần đăng nhập nếu điều đó khiến mọi yêu cầu đang chờ liên tục mất hiệu lực.

**request_revision** tăng khi nội dung cần phê duyệt thay đổi. Việc sửa danh sách khóa cần thu hồi, đổi loại phương tiện mới hoặc thay bộ bằng chứng phải làm các quyết định cũ không còn hiệu lực.

Nếu tạo digest, máy chủ cần serialize dữ liệu theo quy tắc ổn định. Digest chỉ giúp phát hiện khác biệt khi bản gốc được bảo vệ; nó không tự chứng minh ai đã duyệt. Tính xác thực của quyết định đến từ kiểm soát truy cập, bản ghi bền vững hoặc cơ chế ký phù hợp với ranh giới dịch vụ.

### 8.2. Kiểm tra ở thời điểm sử dụng

Giả sử yêu cầu được duyệt lúc 09:00 để thay khóa A. Đến 09:05, tài khoản đổi email recovery hoặc xuất hiện passkey B chưa được xác nhận. Đến 09:06, người yêu cầu dùng grant cũ.

Nếu hệ thống chỉ đọc trạng thái APPROVED, quyết định có thể được áp dụng vào một hoàn cảnh khác với hoàn cảnh người duyệt đã xem. Đây là lỗi **time-of-check to time-of-use**, tức điều kiện thay đổi giữa lúc kiểm tra và lúc dùng kết quả.

Thiết kế tham khảo chặn bằng cả hai lớp:

1. Liên kết quyết định với revision và phiên bản cấu hình an ninh.
2. Kiểm tra điều kiện hiện hành tại các điểm chuyển trạng thái nhạy cảm, bao gồm lần commit thay đổi cuối.

Một phiên bản chính sách được lưu giúp giải thích quyết định lịch sử. Nó không cho phép né một lệnh chặn khẩn cấp mới có hiệu lực. Khi chính sách thay đổi, quy tắc tương thích phải được định nghĩa; nếu không xác định được, yêu cầu chuyển về đánh giá lại.

Nguyên tắc kiểm tra quyền thực thi phía máy chủ và bảo vệ dữ liệu được phê duyệt tương ứng với hướng dẫn về transaction authorization của OWASP. [OWASP Transaction Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Transaction_Authorization_Cheat_Sheet.html)

## 9. Quyền reset dùng một lần và phiên recovery giới hạn

### 9.1. Phân biệt ba loại dữ liệu

| Thành phần | Vai trò | Có được dùng để đăng nhập ứng dụng không? |
| --- | --- | --- |
| Bằng chứng recovery | Hỗ trợ xác minh yêu cầu | Theo quy trình recovery; không mặc nhiên là session |
| Quyết định approval | Ghi nhận việc cho phép một thay đổi | Không |
| Grant hoặc recovery session | Cho phép thực hiện đúng luồng đăng ký đã duyệt | Không, chỉ có quyền recovery giới hạn |

Một email “yêu cầu đã được duyệt” cũng không phải quyền đăng nhập.

Nếu triển khai grant dạng opaque token, một lựa chọn minh họa là sinh 32 byte bằng bộ sinh số ngẫu nhiên mật mã, mã hóa Base64URL và chỉ lưu digest phía máy chủ. Digest của token có entropy cao khác với cách lưu mật khẩu hoặc OTP ngắn; không áp dụng máy móc cùng một thuật toán cho mọi loại bí mật.

Bản ghi phía máy chủ cần chứa request, revision, tenant, account, scope, thời hạn và trạng thái tiêu thụ. Scope có thể là **ENROLL_REPLACEMENT_AUTHENTICATOR**; API nghiệp vụ phải từ chối credential này.

Đối với password reset token, OWASP yêu cầu tính ngẫu nhiên an toàn, thời hạn và tính dùng một lần. Bài học áp dụng các thuộc tính đó cho grant recovery có trạng thái, đồng thời bổ sung ràng buộc với quyết định reset. [OWASP Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html)

### 9.2. Trao đổi và tiêu thụ nguyên tử

Một mô hình dễ kiểm soát:

1. Người yêu cầu trình grant cho endpoint chuyên biệt.
2. Máy chủ khóa bản ghi liên quan và kiểm tra lại điều kiện approval.
3. Trong cùng transaction, đánh dấu grant đã dùng và tạo recovery session giới hạn.
4. Client nhận cookie recovery riêng với thuộc tính bảo vệ phù hợp.
5. Recovery session chỉ được dùng để hoàn thành yêu cầu tương ứng.

Nếu transaction thất bại, không để lại trạng thái grant đã bị tiêu thụ nhưng chưa có recovery session. Nếu response bị mất sau commit, cơ chế tiếp tục cần xác thực lại đúng người yêu cầu; không trả recovery session cho bất kỳ ai chỉ biết mã idempotency.

“Dùng một lần” phải được thực thi bằng chuyển trạng thái nguyên tử hoặc cập nhật có điều kiện. Kiểm tra chưa dùng, rồi cập nhật ở hai transaction độc lập tạo ra cửa sổ để hai request cùng được chấp nhận.

Các bước tạo challenge và xác minh phương tiện mới có thể gọi lại hợp lệ trong recovery session. Điều đó khác với cho phép grant gốc được trao đổi nhiều lần.

### 9.3. Không gây thay đổi từ liên kết được quét

GET từ email nên mở trang giải thích, không trực tiếp phê duyệt hoặc reset. Trình quét liên kết và cơ chế xem trước có thể truy cập URL mà người dùng chưa chủ động xác nhận.

Bước thay đổi trạng thái dùng phương thức thích hợp, xác nhận rõ thao tác và cơ chế chống CSRF nếu dựa vào cookie. Trang recovery không tải tracker bên thứ ba; token không được đi vào log, telemetry, lịch sử hỗ trợ hoặc Referer. Kiểm soát HTTPS, cache và cách chuyển token thành session thuộc phần triển khai bắt buộc.

Địa chỉ email hoặc số điện thoại vừa được người yêu cầu cung cấp trong ticket không tự trở thành đích nhận grant. Thay đổi đích recovery là một quyết định riêng.

## 10. Phác thảo xử lý trong dịch vụ Java

Mã giả dưới đây minh họa ranh giới transaction và điều kiện bất biến. Các kiểu và repository là ký hiệu thiết kế, không phải thư viện có thể sao chép để chạy ngay.

### 10.1. Ghi nhận một quyết định phê duyệt

~~~java
@Transactional
ApprovalOutcome approve(ApproveCommand command, StaffPrincipal staff) {
    // Account được xác định từ request phía server.
    RequestLocator locator = requests.locate(command.requestId());
    access.requireCanReview(staff, locator.tenantId(), locator.accountId());

    // Mọi đường ghi liên quan dùng cùng thứ tự khóa: account -> request.
    AccountSecurity account = accounts.lockSecurity(locator.accountId());
    ResetRequest request = requests.lock(command.requestId());

    request.requireSameTarget(locator);
    request.requireRevision(command.expectedRevision());
    request.requireState(UNDER_REVIEW);

    Policy policy = policies.currentFor(account);
    staffAuth.requireFreshAuthentication(staff, policy.approverAuthRule());
    access.requireCurrentApprovalAuthority(staff, request, account);
    separation.requireEligiblePerson(staff.personId(), request, policy);

    evidence.requireSufficientAndFresh(request, account, policy);
    risk.requireNoBlockingCondition(request, account, policy);
    snapshots.requireMatchesCurrentSecurity(request, account);

    // Ràng buộc unique theo request + revision + personId.
    approvals.insertUniqueDecision(
        request.id(), request.revision(), staff.personId(),
        request.snapshotDigest(), command.reasonCode()
    );

    Quorum quorum = approvals.validQuorum(request, account, policy);
    if (quorum.isSatisfied()) {
        request.recordApprovalWindow(
            policy.notBefore(clock.instant()),
            policy.expiresAt(clock.instant())
        );
        request.moveTo(policy.requiresCooldown() ? COOLDOWN : APPROVED);
    }

    audit.appendDecision(request, staff.personId(), command.reasonCode());
    return ApprovalOutcome.from(request);
}
~~~

Các helper trong ví dụ có hợp đồng nghiệp vụ rõ ràng: kiểm tra bằng chứng không chỉ là so sánh một cột verified với true; quorum phải xét quyết định đúng snapshot, chưa hết hạn và có người duyệt còn hợp lệ.

Một unique constraint giúp ngăn hai lần duyệt của cùng một người bị đếm thành hai. Bản ghi quyết định và audit phải bền vững cùng transaction. Nếu đẩy audit sang hệ thống khác, dùng bản ghi outbox trong transaction để tránh mất sự kiện khi tiến trình chết sau commit.

### 10.2. Commit phương tiện thay thế

Chứng minh kiểm soát phương tiện mới được thực hiện trước; kết quả được lưu dưới dạng bản ghi pending phía máy chủ, liên kết với challenge và recovery session. Không chấp nhận một cờ từ client nói rằng “đã xác minh”.

~~~java
@Transactional
FinalizeOperation beginFinalize(
        UUID recoverySessionId,
        UUID pendingEnrollmentId,
        String idempotencyKey) {

    RecoveryLocator locator =
        recoverySessions.locateAuthenticated(recoverySessionId);

    AccountSecurity account = accounts.lockSecurity(locator.accountId());
    ResetRequest request = requests.lock(locator.requestId());
    RecoverySession session = recoverySessions.lock(recoverySessionId);

    session.requireMatches(request, account);
    session.requireNotRevokedAndScoped(ENROLL_REPLACEMENT_AUTHENTICATOR);

    // Retry chỉ đọc lại đúng operation của cùng session, request và payload.
    var prior = operations.findBoundOperation(
        request.id(), session.id(), pendingEnrollmentId, idempotencyKey);
    if (prior.isPresent()) {
        return prior.get();
    }

    session.requireActiveAndUnexpired(clock.instant());
    request.requireState(ENROLLING);
    Policy policy = policies.currentFor(account);
    approvals.requireStillUsable(request, account, policy, clock.instant());
    snapshots.requireMatchesCurrentSecurity(request, account);
    risk.requireNoBlockingCondition(request, account, policy);

    PendingEnrollment pending =
        enrollments.lockVerifiedPending(pendingEnrollmentId);
    pending.requireBoundTo(session, request);
    pending.requireFreshAndUnconsumed(clock.instant());
    pending.requireMeets(request.replacementRequirements());

    FinalizeOperation operation = operations.createBound(
        request, session, pending, idempotencyKey);

    // Chặn phiên/credential cũ theo kế hoạch trước khi mở quyền bình thường.
    account.beginRecoveryFence(operation.id());
    account.incrementSessionEpoch();
    authenticators.revokeApprovedTargets(request.targetAuthenticatorIds());
    authenticators.attachPendingReplacement(pending, account, operation.id());

    pending.consume();
    session.consumeFor(operation.id());
    request.moveTo(FINALIZING);
    account.incrementSecurityConfigVersion();

    audit.appendFinalizeStarted(request, operation);
    outbox.appendRequiredSecurityActions(operation, request.sessionPlan());
    return operation;
}
~~~

Ở ví dụ này, replacement vẫn chưa được dùng để tạo session ứng dụng cho đến khi hoàn tất các hàng rào bắt buộc. Cùng một idempotency key với payload khác phải bị từ chối; unique constraint và khóa bảo vệ việc chỉ tạo một operation.

Các bảng cùng cơ sở dữ liệu có thể được cập nhật nguyên tử. Các hệ thống ngoài transaction cần cơ chế hoàn tất ở phần tiếp theo. Không gọi một loạt API thu hồi từ xa trong transaction rồi giả định rollback cơ sở dữ liệu có thể hoàn tác tất cả.

Nếu tài khoản chỉ mất thiết bị mà credential chưa có dấu hiệu bị chiếm, thời điểm thu hồi có thể gắn với lần thay thế thành công. Nếu đã xác nhận credential bị chiếm, việc đình chỉ hoặc thu hồi cần đi theo nhánh sự cố ngay khi phù hợp, không đợi người yêu cầu hoàn thành recovery.

## 11. Hoàn tất khi có nhiều dịch vụ

Reset thường liên quan đến kho credential, session store, dịch vụ refresh token, trusted device và hệ thống gửi thông báo. Một transaction cơ sở dữ liệu không thể đảm bảo mọi thành phần từ xa thay đổi cùng lúc.

Thiết kế tham khảo dùng **recovery fence**: hàng rào tạm thời chặn việc cấp hoặc sử dụng quyền nhạy cảm trong khi recovery chưa hoàn tất.

Quy trình hoàn tất:

1. Ghi nhận operation, hàng rào và các thay đổi cục bộ một cách nguyên tử.
2. Worker đọc outbox, áp dụng các hành động bắt buộc với operation ID để tránh làm trùng.
3. Từng thành phần xác nhận đã áp dụng phiên bản thu hồi tương ứng.
4. Bộ điều phối kiểm tra các xác nhận, trạng thái sự cố và tính hợp lệ của cấu hình sau reset.
5. Chỉ khi đạt điều kiện mới chuyển COMPLETED, mở quyền đăng nhập phù hợp và gửi thông báo kết quả.

**Điều kiện kiến trúc của ví dụ Java:** nơi cấp token và các API thuộc phạm vi bảo vệ phải thực thi fence hoặc session epoch từ nguồn có thẩm quyền. Nếu chúng chỉ dùng cache cũ, việc tăng epoch trong cơ sở dữ liệu chưa chặn được session tại các API đó.

Khi không thể tra cứu trạng thái tập trung, cần một giai đoạn dựng fence và đợi các điểm thực thi xác nhận trước khi cho phép tiến trình vượt ranh giới an ninh. Không coi việc đẩy một sự kiện vào hàng đợi là bằng chứng mọi dịch vụ đã thu hồi quyền.

| Sự cố | Cách giữ trạng thái an toàn |
| --- | --- |
| Gửi email bị lỗi | Lưu sự kiện để thử lại; theo dõi độ trễ và áp dụng chính sách kênh thay thế |
| Dịch vụ thu hồi session chưa xác nhận | Giữ FINALIZING và fence; chưa báo hoàn tất |
| Tiến trình chết sau commit | Worker tiếp tục từ outbox và operation đã lưu |
| Client gửi lại yêu cầu sau mất response | Trả tiến độ operation đã gắn với đúng người gọi; không reset lần nữa |
| Xác minh phương tiện mới thất bại | Không commit thay đổi thay thế; giới hạn số lần thử |
| Phát hiện gian lận trong FINALIZING | Giữ hoặc tăng hạn chế; chuyển xử lý sự cố |
| Hoàn tất một phần rồi lỗi lâu dài | RECOVERY_REQUIRED; người vận hành xử lý từ dấu vết đã lưu |

Một lỗi tạm thời của nhà cung cấp thông báo không được làm mất sự kiện thông báo. Với nhánh mà chính sách yêu cầu thông báo trước và một khoảng chờ, chưa đáp ứng được điều kiện thông báo thì chưa bắt đầu tính khoảng chờ theo nhánh đó. Cần định nghĩa rõ mốc là hệ thống chấp nhận gửi hay nhà cung cấp xác nhận giao; không dựa vào việc người dùng mở email.

Không tự động khôi phục credential cũ đã được xác định bị chiếm để “rollback cho tiện”. Thao tác bù trừ phải bảo toàn mục tiêu an ninh và có thể cần xác minh mới.

## 12. Phương tiện mới và session sau reset

### 12.1. Chứng minh quyền kiểm soát authenticator thay thế

Phê duyệt không đủ để kết luận phương tiện mới hoạt động đúng.

- Với TOTP, tạo secret mới và yêu cầu mã hợp lệ trước khi kích hoạt; bảo vệ secret pending, giới hạn thử và hủy bản pending hết hạn.
- Với passkey, dùng challenge một lần gắn với tài khoản, yêu cầu và recovery session; xác minh kết quả đăng ký ở máy chủ, bao gồm origin, RP ID và các thuộc tính mà chính sách yêu cầu.
- Nếu loại passkey được phê duyệt yêu cầu user verification, kiểm tra kết quả xác minh người dùng; không chỉ tin việc client hiển thị hộp thoại sinh trắc học.
- Với khóa vật lý hoặc phương tiện cấp bởi tổ chức, có bước giao nhận và ràng buộc phù hợp; việc nhân viên bấm “đã giao” không tự thay thế kiểm tra kỹ thuật cần thiết.

Sau khi thay, xác định rõ credential ID nào bị thu hồi. Với passkey đồng bộ, ứng dụng thường quản lý credential đã đăng ký tại relying party; không nên hứa chỉ vô hiệu hóa riêng một điện thoại nếu các bản đồng bộ dùng cùng credential và hệ thống không phân biệt được.

### 12.2. Không kế thừa độ tin cậy của session trước recovery

Một chính sách tham khảo cho nhánh nghi ngờ chiếm đoạt:

1. Vô hiệu hóa session cũ và các refresh-token family thuộc phạm vi sự cố.
2. Thu hồi trusted-device hoặc remember-MFA tương ứng.
3. Đóng recovery session sau khi operation bắt đầu và chỉ cho đọc tiến độ qua cơ chế giới hạn.
4. Yêu cầu đăng nhập mới bằng cấu hình sau reset.
5. Với tác vụ giá trị cao, giữ hạn chế sau recovery theo chính sách riêng.

Một lựa chọn triển khai là session epoch: token mang phiên bản tại lúc cấp, còn máy chủ kiểm tra với phiên bản hiện hành của tài khoản. Nếu chỉ kiểm chữ ký và hạn JWT mà không kiểm tra trạng thái thu hồi, token cũ có thể tiếp tục dùng đến khi hết hạn.

OWASP nhấn mạnh vô hiệu hóa session ở phía máy chủ; xóa cookie trên trình duyệt không làm bản session ID bị đánh cắp mất hiệu lực. [OWASP Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html#expire-and-max-age-attributes)

Đối với hệ thống liên kết đăng nhập, cần xét cả session của ứng dụng và session tại identity provider. Đăng xuất ở một nơi không bảo đảm đã kết thúc ở mọi nơi. API key, personal access token hoặc OAuth grant có vòng đời riêng cũng cần được đưa vào kế hoạch xử lý sự cố khi có căn cứ; chúng không tự biến mất vì mật khẩu hay MFA đã đổi.

Nếu chỉ thay thiết bị trong điều kiện ít rủi ro, tổ chức có thể chọn phạm vi thu hồi hẹp hơn. Quyết định đó phải được biểu diễn trong session plan đã duyệt để dịch vụ thực thi không tự suy đoán.

## 13. Thông báo, phản đối và chống lạm dụng

### 13.1. Thông báo là cơ chế phát hiện

Một thông báo hữu ích cho biết loại thay đổi, thời điểm, thông tin nhận diện yêu cầu đã che phù hợp và cách báo “tôi không thực hiện yêu cầu này”. Không chứa token reset, secret TOTP hoặc giấy tờ định danh.

NIST yêu cầu thông báo đối với recovery và việc gắn authenticator mới; hướng dẫn cũng nhấn mạnh khả năng thông báo độc lập. Thông báo hỗ trợ phát hiện gian lận, không thay thế bằng chứng cần để phê duyệt. [NIST SP 800-63B-4, Account Notifications](https://pages.nist.gov/800-63-4/sp800-63b/events/#notification)

Các mốc thông báo trong thiết kế tham khảo gồm: tiếp nhận một yêu cầu có ý nghĩa, đủ người phê duyệt, bắt đầu thời gian chờ và hoàn tất thay đổi. Có thể gộp thông báo để tránh gây nhiễu nhưng vẫn giữ dấu vết từng sự kiện.

Kênh thông báo cần được đánh giá khả năng đã bị chiếm. Không tự động gửi toàn bộ bằng chứng nhạy cảm tới mọi địa chỉ cũ: một địa chỉ cũ có thể đã được thay vì mất quyền kiểm soát. Chính sách chọn kênh dựa trên lịch sử và trạng thái xác minh.

### 13.2. Phản đối không phải quyền quản trị vô hạn

Liên kết báo nghi ngờ có thể giúp tạo cảnh báo hoặc tạm dừng đúng yêu cầu recovery. Nó không được dùng để cấp quyền đăng nhập hoặc thay email.

Nếu người không xác thực có thể bấm một liên kết để khóa toàn bộ tài khoản vô thời hạn, hệ thống tạo thêm đường từ chối dịch vụ. Cần giới hạn tác động, ghi nhận nguồn phản đối và xác minh bổ sung trước những hành động rộng hơn.

Ngược lại, việc không ai phản đối trong khoảng chờ không được diễn giải thành bằng chứng người yêu cầu là chủ tài khoản.

### 13.3. Chống lạm dụng ở cả phía người yêu cầu và người duyệt

Các biện pháp vận hành tham khảo:

- Giới hạn tốc độ theo tài khoản, tenant, thiết bị, mạng và nguồn gửi để giảm spam lẫn tấn công phân tán.
- Hạn chế số hồ sơ đang hoạt động; liên kết hoặc gộp yêu cầu thay vì cấp nhiều grant độc lập.
- Không để một yêu cầu chưa được xác minh tự thu hồi yêu cầu hợp lệ đang tiến hành.
- Có phản hồi tiếp nhận phù hợp để không lộ việc một email có tài khoản hay không.
- Giám sát một nhân viên duyệt quá nhiều hồ sơ hoặc liên tục duyệt ngoài giờ bất thường.
- Bảo vệ chống CSRF, clickjacking và XSS cho giao diện duyệt; hạn chế chức năng duyệt hàng loạt.
- Khi dịch vụ xác minh hoặc policy engine lỗi, giữ hồ sơ chờ; không chuyển lỗi kỹ thuật thành duyệt mặc định.

Giới hạn tốc độ theo tài khoản cần tránh biến thành cách khóa người dùng hợp lệ. Có thể làm chậm yêu cầu mới, gộp thông báo và chuyển kiểm tra thủ công thay vì tự khóa đăng nhập bình thường.

## 14. Audit và khả năng giải thích quyết định

Một bản ghi audit hữu ích cần trả lời được:

- Ai tiếp nhận, ai xác minh, ai duyệt và actor dịch vụ nào thực thi?
- Người duyệt đã thấy snapshot nào; policy nào có hiệu lực?
- Bằng chứng nào được sử dụng, từ đâu và có hiệu lực đến khi nào?
- Quyết định cho phép thay gì, trong khoảng nào, với kế hoạch session nào?
- Operation thực tế đã thu hồi, thêm hoặc hạn chế những gì?
- Nếu có lỗi, phần nào đã áp dụng và phần nào đang chờ?

Có thể dùng reason code như **INSUFFICIENT_EVIDENCE**, **QUORUM_PENDING**, **APPROVAL_EXPIRED**, **SECURITY_CONTEXT_CHANGED**, **OWNER_DISPUTE** và **SESSION_REVOCATION_PENDING**. Reason code nội bộ có thể chi tiết hơn thông điệp trả cho người chưa xác thực.

Audit cần chống sửa trái phép và kiểm soát người đọc. Không ghi token, mã khôi phục, secret, ảnh giấy tờ hoặc nội dung sinh trắc học vào log thông thường. Bằng chứng nhạy cảm cần kho lưu riêng, thời hạn giữ và quyền truy cập được quản trị.

Các chỉ số nên xem cùng nhau: thời gian chờ duyệt, tỷ lệ yêu cầu thiếu bằng chứng, số hồ sơ stale, độ trễ thu hồi session, số phản đối và sự cố chiếm đoạt sau recovery. Tối ưu riêng thời gian xử lý có thể tạo áp lực khiến người duyệt bỏ qua điều kiện.

## 15. Ví dụ xuyên suốt: mất điện thoại có TOTP

Người dùng Lan báo mất điện thoại chứa ứng dụng TOTP. Lan còn nhớ mật khẩu nhưng không còn dùng được yếu tố thứ hai. Tài khoản có mã recovery được cấp trước.

1. **Tiếp nhận:** máy chủ tạo yêu cầu thay đúng authenticator TOTP; không tự đổi email và không tắt MFA.
2. **Xác minh:** Lan nhập bằng chứng qua giao diện an toàn. Máy chủ xác minh bộ bằng chứng theo chính sách mục tiêu và tiêu thụ mã recovery đã dùng theo cơ chế nguyên tử; nhân viên không yêu cầu Lan đọc mã qua điện thoại.
3. **Đánh giá:** mật khẩu kết hợp mã recovery chỉ được chấp nhận nếu phương thức đó đáp ứng chính sách cho tài khoản. Một IP quen thuộc không cứu được bằng chứng sai.
4. **Phê duyệt:** hệ thống hoặc người có thẩm quyền ghi quyết định cho revision hiện tại. Nếu đây là tài khoản đặc quyền, thực hiện quorum theo nhánh đặc quyền.
5. **Thông báo và chờ:** nếu chính sách yêu cầu, gửi thông báo và giữ COOLDOWN. Bằng chứng phải còn hợp lệ khi đi tiếp.
6. **Đăng ký giới hạn:** grant được trao đổi một lần thành recovery session; Lan chỉ có quyền đăng ký phương tiện thay thế được duyệt.
7. **Chứng minh phương tiện mới:** Lan hoàn thành challenge tương ứng. Bản pending được gắn với đúng request.
8. **Thực thi:** kiểm tra lại snapshot và quyết định; bắt đầu operation, thu hồi TOTP cũ theo kế hoạch, cập nhật cấu hình và hàng rào session.
9. **Hoàn tất:** đợi các xác nhận bắt buộc, đóng tiến trình recovery và yêu cầu đăng nhập mới. Rà soát lại phương thức recovery; nếu phát hành bộ mã mới theo chính sách, vô hiệu hóa bộ cũ tương ứng.

Ba nhánh thay đổi cần được hiểu rõ:

- Nếu email recovery đổi trong lúc chờ, yêu cầu không được dùng approval cũ để tiếp tục mà chưa đánh giá lại.
- Nếu Lan còn một khóa bảo mật khác đủ mức đảm bảo, hệ thống ưu tiên nhánh thay phương tiện sau xác thực lại phù hợp.
- Nếu không còn bằng chứng được chấp nhận, bộ phận hỗ trợ hướng dẫn quy trình xác minh thay thế đã được phê chuẩn; chức danh, yêu cầu khẩn hoặc việc biết mật khẩu không tự tạo ngoại lệ.

Trong ví dụ này, tiêu thụ một mã recovery hợp lệ không có nghĩa là mọi session ứng dụng được cấp ngay. Bằng chứng được gắn với hồ sơ, còn việc cấp quyền vẫn theo các bước phê duyệt và thực thi.

## 16. Những câu hỏi cần trả lời khi thiết kế

Để chuyển bài học thành thiết kế cụ thể, hãy xác định:

1. Authenticator nào được thay và authenticator nào vẫn phải giữ?
2. Bằng chứng tối thiểu của từng loại tài khoản là gì; các nguồn có thể cùng bị chiếm không?
3. Ai có quyền xác minh, ai có quyền duyệt và khi nào cần hai người?
4. Thay đổi nào làm approval cũ mất hiệu lực?
5. Grant dùng một lần được trao đổi nguyên tử như thế nào?
6. Phương tiện mới chứng minh quyền kiểm soát ở bước nào?
7. Session, refresh token và trusted device được thu hồi ở đâu?
8. Điểm thực thi nào còn có thể chấp nhận trạng thái cache cũ?
9. Nếu reset chỉ áp dụng một phần, operation được tiếp tục hoặc xử lý sự cố như thế nào?
10. Người dùng được thông báo và phản đối qua kênh nào mà không tạo thêm đường chiếm đoạt hoặc từ chối dịch vụ?

Một thiết kế có thể giải thích được từng quyết định phải nối liền **bằng chứng → thẩm quyền → phạm vi → thực thi → kiểm soát truy cập sau reset**. Nút “Approve” chỉ là giao diện của chuỗi kiểm soát đó.

