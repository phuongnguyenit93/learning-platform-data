# Recent authentication requirement: Yêu cầu xác thực gần đây trong khôi phục tài khoản

Trong chương **Eligibility Rules** của `SECURITY_AUTHENTICATION_ACCOUNT_RECOVERY`, **recent authentication requirement** là điều kiện yêu cầu một thao tác phải dựa trên sự kiện xác thực còn đủ mới và đáp ứng chính sách của chính thao tác đó. Mục tiêu là giảm khả năng một session cũ, một phiên bỏ quên hoặc một quyền truy cập bị đánh cắp được dùng để thay đổi phương thức xác thực của tài khoản.

Tuy nhiên, “vừa xác thực” không tự đồng nghĩa “đủ quyền khôi phục”. Nhập lại một mật khẩu đã bị lộ vẫn không loại trừ kẻ biết mật khẩu. Một phiên vừa được làm mới cũng không chứng minh người dùng vừa cung cấp bằng chứng. Khi người dùng mất mật khẩu, MFA, passkey hoặc thiết bị xác thực, hệ thống cần đường dự phòng phù hợp thay vì yêu cầu họ dùng lại chính yếu tố đã mất.

Bài học trình bày cách xác định độ mới của bằng chứng, kết hợp nó với mức bảo đảm và phạm vi thao tác, cấp token dùng một lần, xử lý hết hạn và kiểm soát session sau thay đổi.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt thời điểm xác thực với thời điểm tạo token, làm mới session và hoạt động gần nhất.
- Diễn đạt điều kiện xác thực gần đây theo tài khoản, phương thức, mục đích và trạng thái bảo mật.
- Giải thích vì sao xác thực bằng một phương thức không phù hợp vẫn không đủ dù vừa diễn ra.
- Thiết kế xác thực tăng cường mà không chặn người đã mất yếu tố khỏi mọi đường khôi phục.
- Ràng buộc kết quả xác thực với quyền thay credential có phạm vi và thời hạn rõ ràng.
- Xử lý bằng chứng hết hạn, nhiều tab, thay đổi đồng thời và xác thực qua nhà cung cấp danh tính.

## 2. Vì sao một session còn hiệu lực có thể chưa đủ?

Một session chứng minh rằng hệ thống đã cấp quyền truy cập theo một ngữ cảnh trước đó và quyền đó chưa bị hết hạn hoặc thu hồi theo cơ chế thực thi. Nó không tự chứng minh người đang cầm session vừa xác thực, vẫn kiểm soát mọi yếu tố hay được phép thay đổi tất cả thiết lập bảo mật.

Đọc trang hồ sơ và thay MFA có mức tác động khác nhau. Thay email khôi phục hoặc thêm passkey có thể tạo đường truy cập còn tồn tại sau khi session hiện tại hết hiệu lực. Vì vậy, thao tác quản lý phương tiện xác thực thường cần điều kiện riêng.

| Tình huống | Rủi ro nếu chỉ kiểm tra có session |
|---|---|
| Trình duyệt dùng chung còn đăng nhập | Người khác có thể đổi đường khôi phục của chủ tài khoản |
| Cookie session bị lấy | Đối phương có thể biến quyền tạm thời thành credential lâu dài |
| Session tồn tại lâu nhưng yếu tố đã thay đổi | Ngữ cảnh cũ không còn phản ánh trạng thái bảo mật hiện tại |
| Phiên mới được tạo từ một bước khôi phục hẹp | Máy chủ có thể gán nhầm quyền đã vượt toàn bộ yêu cầu đăng nhập |
| Nhân viên hỗ trợ đang đăng nhập | Xác thực của nhân viên bị nhầm thành bằng chứng về chủ tài khoản |

Yêu cầu xác thực gần đây giúp giới hạn một số rủi ro này bằng cách yêu cầu bằng chứng mới phù hợp. Nó không thay thế kiểm soát quyền, xác minh danh tính, chống lạm dụng hay thu hồi phương tiện truy cập đã bị chiếm.

## 3. “Gần đây” phải nói về sự kiện nào?

Một hệ thống có thể có nhiều dấu thời gian liên quan. Tên trường dưới đây chỉ mang tính minh họa; ý nghĩa của dữ liệu phải được quy định trong thiết kế.

| Dấu thời gian | Phản ánh điều gì? | Có tự chứng minh xác thực mới không? |
|---|---|---|
| `authenticated_at` | Thời điểm sự kiện xác thực thực sự diễn ra theo nguồn đáng tin cậy | Có thể dùng nếu phương thức, chủ thể và điều kiện được chấp nhận |
| `token_issued_at` | Thời điểm phát hành một token | Không; token có thể dựa trên xác thực cũ |
| `session_created_at` | Thời điểm tạo đối tượng session | Không; session có thể được tạo từ kết quả hoặc quyền có sẵn |
| `session_refreshed_at` | Thời điểm gia hạn hoặc đổi token của session | Không; thường không có bằng chứng người dùng mới |
| `last_seen_at` | Thời điểm có hoạt động gần nhất | Không; hoạt động có thể do script hoặc đối phương thực hiện |
| `assertion_validated_at` | Thời điểm máy chủ kiểm tra một thông điệp xác thực | Không tự động; thông điệp có thể mô tả một sự kiện cũ |
| `recovery_evidence_checked_at` | Thời điểm một bằng chứng khôi phục được kiểm tra | Chỉ có giá trị trong phạm vi và theo chính sách dành cho bằng chứng đó |

Ví dụ, người dùng xác thực lúc 08:00. Token được làm mới lúc 10:00 và có hoạt động lúc 10:01. Nếu không có bằng chứng xác thực mới, tuổi của sự kiện xác thực lúc 10:02 vẫn tính từ 08:00, không phải 10:00 hay 10:01.

### Không đóng dấu “bây giờ” lên bằng chứng cũ

Nếu một máy chủ nhận lại kết quả xác thực cũ, việc kiểm tra chữ ký hoặc đọc cơ sở dữ liệu ở thời điểm hiện tại không làm sự kiện đó mới hơn. Cần giữ riêng thời điểm sự kiện gốc và thời điểm kiểm tra kết quả.

Tương tự, mở lại trang, kéo dài thời gian chờ hỗ trợ hay di chuyển hồ sơ sang nhân viên khác không tạo ra một lần xác thực mới.

### Nguồn thời gian và dữ liệu phải đáng tin cậy

Client không được tự gửi `authenticated_at = now` hoặc cờ `recently_verified = true` để thỏa điều kiện. Máy chủ phải lấy sự kiện từ thành phần xác thực có thẩm quyền, hoặc từ thông điệp của bên được tin cậy đã được kiểm tra đúng.

Thời gian nên được xử lý như thời điểm tuyệt đối phía máy chủ, với kiểm soát đồng bộ và sai lệch phù hợp. Nếu dữ liệu có thời điểm tương lai bất thường, không nên mặc định coi là rất mới. Đồng hồ đếm ngược trên giao diện không có quyền quyết định bằng chứng đã hết hạn hay chưa.

## 4. Độ mới chỉ là một phần của điều kiện đủ

Một điều kiện có thể được diễn đạt ở mức khái niệm:

```text
Đủ điều kiện cho thao tác =
    Đúng tài khoản và tenant
    + Phương thức và thuộc tính đáp ứng chính sách
    + Sự kiện còn đủ mới
    + Mục đích và ngữ cảnh được phép
    + Trạng thái bảo mật chưa làm mất hiệu lực bằng chứng
    + Các điều kiện phê duyệt hoặc khôi phục khác đã đạt
```

Các dấu cộng thể hiện điều kiện kết hợp, không phải phép cộng điểm để bù trừ. Một sự kiện rất mới không bù được việc nó thuộc tài khoản khác hoặc được xác thực bằng phương thức không được phép.

### Cửa sổ độ mới

Với một sự kiện được tin cậy, quy tắc thời gian đơn giản là:

```text
age = trusted_server_now - event.authenticated_at

Điều kiện thời gian:
  age không âm ngoài sai lệch được chính sách cho phép
  age không vượt cửa sổ độ mới của thao tác
```

Không có một cửa sổ cố định phù hợp cho mọi dịch vụ và thao tác. Chính sách cần chọn giới hạn dựa trên tác động, mô hình session, phương thức xác thực và khả năng sử dụng thực tế. Nếu đưa ra con số trong thiết kế, phải xem đó là cấu hình đã được lựa chọn, không phải quy luật an toàn chung.

### Mỗi phần bằng chứng có thể có tuổi khác nhau

Nếu mật khẩu vừa được kiểm tra nhưng MFA chỉ được kiểm tra từ lâu, không được cập nhật toàn bộ ngữ cảnh thành “MFA mới”. Khi một thao tác yêu cầu nhiều điều kiện, phải đánh giá độ mới và thuộc tính của từng phần bằng chứng cần thiết.

Lấy thời điểm mới nhất trong mọi sự kiện rồi áp dụng cho cả bộ yếu tố có thể che giấu một yếu tố đã cũ. Hệ thống cần lưu đủ thông tin để biết chính xác sự kiện nào đáp ứng yêu cầu nào.

## 5. Xác thực mới bằng phương thức nào mới có ý nghĩa?

| Bằng chứng vừa được kiểm tra | Có thể hỗ trợ việc gì? | Giới hạn cần giữ |
|---|---|---|
| Mật khẩu hiện tại | Xác thực lại cho một số thao tác theo chính sách | Không ngăn kẻ đã biết mật khẩu khỏi thao tác chỉ yêu cầu lại mật khẩu |
| Authenticator còn được chấp nhận | Chứng minh khả năng dùng phương tiện theo cơ chế đã kiểm tra | Không tự cấp quyền đổi mọi kênh hoặc bỏ mọi điều kiện khác |
| Passkey được xác thực thành công | Cung cấp các thuộc tính xác thực mà máy chủ đã kiểm tra | Không suy ra tính chất hoặc số yếu tố chỉ từ tên gọi passkey |
| Recovery code hợp lệ | Đáp ứng một đường khôi phục đã định nghĩa | Không tự biến thành lần đăng nhập đủ mọi yếu tố; mã vẫn có thể bị đánh cắp |
| Mã nhận ở email mới | Kiểm soát email mới tại thời điểm đó | Không chứng minh quyền thay kênh cũ của tài khoản |
| Người duyệt vừa xác thực | Chứng minh ngữ cảnh của người duyệt theo quyền được giao | Không tự chứng minh danh tính hay quyền sở hữu của người xin khôi phục |

Một thao tác thay MFA cần loại trừ mô hình đối phương đã có mật khẩu nhưng chưa có MFA. Nếu chỉ hỏi lại mật khẩu, việc xác thực xảy ra cách đây vài giây cũng không giải quyết mô hình đó.

Với passkey hoặc một phương thức có nhiều thuộc tính, chính sách phải dựa vào những thuộc tính thực sự được kiểm tra, như điều kiện sử dụng authenticator và kết quả xác minh người dùng nếu được yêu cầu. Không coi tên phương thức là bằng chứng rằng mọi điều kiện đều đã đạt.

Cũng cần xét tính độc lập: mật khẩu, email và mã dự phòng có thể cùng phụ thuộc một thiết bị hoặc kho bí mật. Nhiều kiểm tra mới không tự tạo ra nhiều nguồn tin độc lập.

## 6. Áp dụng yêu cầu khi người dùng đã mất yếu tố

Không nên yêu cầu đăng nhập và xác thực lại đầy đủ trước mọi bước tiếp nhận khôi phục. Người quên mật khẩu hoặc mất MFA thường tìm tới quy trình vì họ không thể hoàn tất chính đường đăng nhập đó.

Cần phân biệt **được bắt đầu yêu cầu**, **được xác minh theo đường dự phòng** và **được thay đổi tài khoản**. Mỗi giai đoạn có thể có điều kiện khác nhau; tạo hồ sơ không tự cấp quyền thay credential.

| Tình huống | Hướng đánh giá phù hợp |
|---|---|
| Có session, còn authenticator cần thiết | Dùng bằng chứng còn đủ mới hoặc yêu cầu xác thực tăng cường theo thao tác |
| Mất mật khẩu nhưng còn authenticator dự phòng | Dùng đường khôi phục được chính sách chấp nhận; không bắt buộc nhập lại mật khẩu đã quên |
| Còn mật khẩu nhưng mất MFA | Mật khẩu mới kiểm tra chưa đủ nếu thao tác cần thay chính MFA đang thiếu; xét bằng chứng dự phòng |
| Mất passkey trên thiết bị chính, còn passkey khác | Có thể xác thực bằng phương tiện còn lại nếu đáp ứng chính sách |
| Mất toàn bộ authenticator nhưng còn recovery code | Kiểm tra mã và điều kiện bổ sung theo đường khôi phục, ghi nhận kết quả với phạm vi riêng |
| Không còn bằng chứng đủ điều kiện | Chuyển quy trình hỗ trợ hoặc xét duyệt đã thiết kế; không tự hạ yêu cầu vì không còn yếu tố |

### Ghi đúng loại bằng chứng khôi phục

Nếu hệ thống chấp nhận một recovery code để mở hồ sơ thay MFA, hãy ghi nhận rằng mã dự phòng đã được kiểm tra cho hồ sơ và mục đích đó. Không cập nhật một cờ chung rằng người dùng vừa hoàn tất toàn bộ đăng nhập bằng mật khẩu và MFA, vì các kiểm tra đó có thể chưa diễn ra.

Độ mới của kiểm tra khôi phục vẫn quan trọng, nhưng nó phải đi cùng loại bằng chứng, phạm vi được cấp và các điều kiện bổ sung. Sau khi thay yếu tố, quyền của session được quyết định riêng theo chính sách, không suy ra từ một nhãn “recent”.

### Tránh cả hai thái cực

Chấp nhận lời khai mất thiết bị rồi bỏ mọi yêu cầu sẽ tạo đường chiếm quyền. Ngược lại, chỉ chấp nhận chính authenticator đã mất sẽ khiến người dùng hợp lệ không có đường về. Cần chuẩn bị authenticator dự phòng, recovery code, kênh phù hợp và quy trình hỗ trợ trước sự cố.

Nếu không còn cơ sở phân biệt chủ tài khoản với đối phương, hệ thống cần giữ giới hạn và cung cấp đường xử lý có thẩm quyền. Việc chờ thêm thời gian hoặc hỏi lại nhiều thông tin công khai không tự thay thế bằng chứng còn thiếu.

## 7. Lưu sự kiện xác thực đủ chi tiết để quyết định

Một cờ `reauthenticated = true` không diễn đạt được phương thức, thời điểm, mục đích và điều kiện vô hiệu hóa. Một bản ghi khái niệm có thể gồm:

```text
authentication_event:
    event_id
    subject_id
    tenant_id
    authenticated_at
    method
    verified_attributes
    source
    context_binding
    permitted_purposes
    account_security_version
    invalidation_state
```

Các trường chỉ là ví dụ. Hệ thống cần định nghĩa rõ bên nào tạo, kiểm tra và có quyền sử dụng chúng. Không để client tự tạo bản ghi hoặc tự gắn thuộc tính xác minh mà máy chủ chưa kiểm tra.

### Ràng buộc chủ thể và ngữ cảnh

Bằng chứng của tài khoản A không được dùng cho tài khoản B, kể cả khi cùng một trình duyệt đang có nhiều session. Tương tự, quyền quản trị trong tenant này không tự tạo quyền khôi phục tài khoản thuộc tenant khác.

Ngữ cảnh đã xác thực cần có cơ chế bảo vệ và thu hồi phù hợp. Nếu bằng chứng được dùng để cấp quyền thay đổi một hồ sơ cụ thể, có thể cần ràng buộc thêm `case_id`, loại thao tác và phiên bản nội dung thay đổi. Biết `event_id` chỉ là biết định danh, không tự tạo quyền sử dụng sự kiện đó.

### Một sự kiện có thể được dùng bao nhiêu lần?

Xác thực gần đây không mặc nhiên là bằng chứng chỉ dùng một lần. Chính sách có thể cho phép một sự kiện đáp ứng nhiều thao tác phù hợp trong một cửa sổ thời gian, hoặc yêu cầu bằng chứng riêng gắn với từng thay đổi nhạy cảm.

Phải quyết định điều này rõ ràng. Đối với quyền áp dụng thay đổi được cấp dưới dạng grant dùng một lần, việc sự kiện xác thực còn mới không làm grant đã dùng có hiệu lực trở lại. Nếu chỉ cho phép một lần cấp quyền từ một bằng chứng, cần kiểm soát cả việc phát hành grant để tránh tạo nhiều grant song song.

### Vô hiệu hóa khi trạng thái bảo mật thay đổi

Đổi mật khẩu, xóa authenticator, thay kênh khôi phục hoặc phát hiện chiếm quyền có thể làm bằng chứng và grant cũ không còn được chấp nhận. Cần xác định sự kiện nào tăng phiên bản bảo mật hoặc đánh dấu vô hiệu hóa, và thành phần nào thực sự kiểm tra trạng thái đó.

Không nhất thiết mọi hoạt động thông thường đều làm mất hiệu lực bằng chứng. Điều cần có là quy tắc phù hợp với thao tác, tránh để một sự kiện cũ được tiếp tục dùng sau thay đổi làm mất cơ sở tin cậy của nó.

## 8. Thực hiện xác thực tăng cường đúng mục đích

**Step-up authentication**, hay xác thực tăng cường, là bước yêu cầu thêm hoặc mới hơn bằng chứng để đạt điều kiện của một thao tác. Tên màn hình “xác thực lại” không đủ; hệ thống phải thực sự kiểm tra bằng chứng được chính sách chấp nhận.

Một trình tự có thể gồm:

1. Máy chủ xác định thao tác, tài khoản, tenant và phiên bản nội dung dự kiến.
2. Chính sách xác định các phương thức và thuộc tính cần đạt, cùng giới hạn độ mới.
3. Hệ thống dùng bằng chứng hiện có nếu còn phù hợp, hoặc phát challenge cho phương thức được phép.
4. Máy chủ kiểm tra challenge, phản hồi, điều kiện dùng và trạng thái chống phát lại.
5. Hệ thống ghi nhận sự kiện đúng thời điểm, đúng loại bằng chứng và đúng ngữ cảnh.
6. Các điều kiện khôi phục khác được đánh giá trước khi cấp quyền thay đổi.

Challenge cần có thời hạn, mục đích và liên kết với ngữ cảnh phù hợp. Mã hoặc phản hồi đã dùng không được tự chấp nhận lại chỉ để tạo dấu thời gian mới. Với một phương thức không có ràng buộc mục đích trong chính thông điệp mật mã, hệ thống vẫn cần quản lý ngữ cảnh và giới hạn sử dụng ở lớp kiểm tra phía máy chủ.

Cần cho người dùng biết họ đang xác thực để làm gì, như thay MFA hay thêm passkey. Một xác nhận mơ hồ có thể bị lạm dụng để dụ người dùng thực hiện thao tác thật mà họ không hiểu. Độ mới của bằng chứng không tự chứng minh người dùng đã hiểu hoặc đồng ý với mọi thay đổi đi kèm.

### Xác thực qua nhà cung cấp danh tính

Trong hệ thống có SSO, chuyển hướng sang nhà cung cấp rồi nhận được phản hồi không tự chứng minh người dùng vừa xác thực lại. Nhà cung cấp có thể dùng session đã tồn tại và không yêu cầu bằng chứng mới.

Ứng dụng cần dựa vào nguồn được tin cậy, kiểm tra tính hợp lệ và phạm vi của thông điệp, đối chiếu đúng chủ thể và tenant, đồng thời hiểu ý nghĩa của thời điểm và thuộc tính xác thực nhận được. Thời điểm ứng dụng nhận hoặc kiểm tra phản hồi không được thay cho thời điểm xác thực gốc.

Nếu nhà cung cấp không cung cấp đủ thông tin có thể tin cậy để đánh giá độ mới hoặc thuộc tính cần thiết, ứng dụng không được tự suy ra chúng. Cần một cơ chế tăng cường được hỗ trợ và kiểm chứng, hoặc một đường xử lý khác phù hợp với chính sách và thẩm quyền của tổ chức.

### Không tạo thêm đường gây phiền nhiễu

Giới hạn gửi challenge, thử mã và yêu cầu xác thực lại để giảm dò đoán, spam và quấy rối người dùng. Một yêu cầu chưa được xác minh không nên tự thu hồi mọi session hoặc làm mất credential hiện có.

Nếu người dùng không còn phương thức được yêu cầu, giao diện cần chỉ đường dự phòng thay vì lặp vô hạn cùng một challenge. Mọi chuyển sang đường dự phòng vẫn phải đáp ứng chính sách dành cho thao tác, không được tự biến thành quyền bỏ yếu tố.

## 9. Giới hạn thời gian của quyền thay đổi được cấp

Giả sử bằng chứng còn đủ mới khi mở trang xác nhận, nhưng người dùng để trang đó rất lâu rồi mới gửi yêu cầu. Nếu máy chủ chỉ kiểm tra lúc hiển thị trang, điều kiện gần đây có thể bị vượt qua ở bước thực sự thay đổi dữ liệu.

Cần xác định rõ chính sách yêu cầu độ mới tại thời điểm nào. Với một thiết kế yêu cầu bằng chứng vẫn đủ mới khi áp dụng, grant không được sống lâu hơn giới hạn đó.

```text
grant_not_after = thời điểm sớm nhất trong:
    thời hạn hồ sơ
    thời hạn của các bằng chứng cần thiết
    authenticated_at + cửa sổ tương ứng của từng sự kiện cần thiết
    thời hạn phê duyệt nếu có
    thời điểm cấp grant + thời hạn grant theo chính sách
```

Khi áp dụng, máy chủ vẫn kiểm tra trạng thái thu hồi, phiên bản bảo mật, nội dung được phép và việc grant đã dùng chưa. Chỉ có thời hạn đúng không bảo đảm các điều kiện khác vẫn đạt.

Một thiết kế khác có thể chấp nhận độ mới tại lúc phê duyệt rồi cấp quyền tiếp tục có vòng đời riêng. Nếu chọn cách đó, phải nêu rõ ý nghĩa và rủi ro của quyền được ủy quyền; không tuyên bố rằng sự kiện xác thực gốc luôn còn mới tới lúc áp dụng. Không âm thầm dùng thời điểm tạo grant để đặt lại tuổi bằng chứng.

### Không gia hạn vô hạn bằng hoạt động

Tải lại trang, làm mới access token hoặc mở lại hồ sơ không tự gia hạn sự kiện xác thực. Muốn có một sự kiện mới phải có kiểm tra bằng chứng mới thực sự, hoặc xử lý theo một cơ chế ủy quyền đã được chính sách định nghĩa rõ.

Nếu grant hết hạn trước áp dụng, có thể xác thực lại hoặc đánh giá lại hồ sơ theo đường phù hợp rồi cấp quyền mới khi đủ điều kiện. Không chỉ sửa `expires_at` của grant cũ mà bỏ qua các điều kiện đã thay đổi.

## 10. Quyết định phía máy chủ và kiểm soát đồng thời

Một quyết định cần dùng dữ liệu có thẩm quyền và chọn đúng tập bằng chứng đáp ứng chính sách. Không chỉ kiểm tra có bất kỳ sự kiện mới nào trong lịch sử.

```text
authorize_recovery_change(context, case, requested_change):
    require context may request this operation for case
    require case.subject and case.tenant match the target account
    require requested_change matches case.current_change_version
    require case is active and not expired

    account = load_current_account_security_state(case.subject)
    rules = resolve_current_policy(account, case.operation)
    events = load_server_validated_events_for(context, case.subject)

    evidence_result = evaluate_required_evidence_set(
        requirements = rules.required_evidence,
        events = events,
        now = trusted_server_time,
        subject = account.id,
        tenant = account.tenant,
        purpose = case.operation,
        security_state = account.security_state
    )

    if evidence_result is insufficient:
        return ACCEPTED_FRESH_PROOF_OR_RECOVERY_ROUTE_REQUIRED

    require other_recovery_conditions_satisfied(case, rules)

    return issue_narrow_grant(
        subject = account.id,
        tenant = account.tenant,
        operation = case.operation,
        case_id = case.id,
        change_version = case.current_change_version,
        evidence_references = evidence_result.selected_events,
        security_version = account.security_version,
        not_after = calculate_allowed_deadline(case, rules, evidence_result),
        use_limit = 1
    )
```

Đây là pseudocode khái niệm. `evaluate_required_evidence_set` phải kiểm tra phương thức, thuộc tính, độ mới, phạm vi và trạng thái vô hiệu hóa theo yêu cầu thực tế. Nó không chỉ tính tuổi của sự kiện gần nhất hoặc đếm số lần đã nhập mã.

### Kiểm tra lại ở bước áp dụng

Trước khi thay credential, máy chủ cần kiểm tra grant đúng tài khoản, tenant, thao tác và phiên bản nội dung; grant còn hạn, chưa dùng và chưa bị thu hồi. Theo thiết kế yêu cầu độ mới tới lúc áp dụng, tập bằng chứng cũng phải còn đáp ứng điều kiện tại thời điểm này.

Việc kiểm tra trạng thái bảo mật, tiêu thụ quyền và ghi thay đổi phải phối hợp nguyên tử hoặc bằng cơ chế có bảo đảm tương đương. Nếu một tab đã đổi MFA, tab khác không được tiếp tục dùng ngữ cảnh cũ để áp dụng thay đổi xung đột.

Kiểm tra ở đầu request rồi thực hiện sau một khoảng chờ mà không kiểm soát thay đổi đồng thời có thể tạo khoảng trống giữa quyết định và thực thi. Cần kiểm tra phiên bản hoặc dùng cơ chế đồng bộ phù hợp tại điểm áp dụng.

Nếu phản hồi bị mất sau thành công, hệ thống có thể dùng định danh lệnh và kết quả đã ghi nhận để xử lý retry. Việc trả lại biên nhận theo quyền phù hợp không được biến thành một lần áp dụng mới hoặc phát hành thêm grant từ quyền đã dùng.

### Giới hạn của yêu cầu gần đây trước session bị chiếm

Nếu đối phương lấy được một session ngay sau khi chủ tài khoản xác thực, sự kiện có thể vẫn nằm trong cửa sổ cho phép. Thu hẹp cửa sổ chỉ giảm thời gian có thể lạm dụng, không chứng minh người đang thao tác là chủ tài khoản.

Tùy tác động, có thể cần challenge riêng cho thao tác, ràng buộc ngữ cảnh, tín hiệu phát hiện và kiểm soát quyền bổ sung. Nếu thiết bị hoặc bí mật dùng để xác thực tăng cường cũng bị đối phương kiểm soát, biện pháp đó tiếp tục có giới hạn. Không nên trình bày xác thực gần đây như giải pháp đầy đủ cho mọi dạng chiếm session.

## 11. Tình huống thực tế: Token mới nhưng xác thực đã cũ

Tài khoản của Lan dùng mật khẩu và MFA. Lan muốn thay MFA trên thiết bị chính nhưng vẫn có một authenticator dự phòng được chấp nhận. Trong ví dụ này, chính sách thay MFA yêu cầu các bằng chứng phù hợp có tuổi không quá **5 phút** tại lúc áp dụng. Con số này chỉ là cấu hình minh họa của ví dụ, không phải mức an toàn chung cho mọi hệ thống.

| Thời điểm | Sự kiện | Cách đánh giá |
|---|---|---|
| 09:00 | Lan hoàn tất đăng nhập bằng mật khẩu và MFA | Ghi thời điểm của các kiểm tra thực tế |
| 11:00 | Session được làm mới bằng cơ chế hiện có | Không cập nhật tuổi xác thực thành 11:00 |
| 11:01 | Lan mở trang thay MFA | Session còn hiệu lực nhưng bằng chứng từ 09:00 đã quá cửa sổ của thao tác |
| 11:02 | Lan nhập lại mật khẩu | Chỉ kiểm tra mật khẩu trở nên mới; chưa làm mới MFA |
| 11:03 | Lan xác thực bằng authenticator dự phòng đạt chính sách | Có bằng chứng mới phù hợp trong ngữ cảnh thao tác |
| 11:04 | Lan xác nhận thay MFA | Máy chủ kiểm tra toàn bộ điều kiện và trạng thái hiện tại trước khi áp dụng |

Trong ví dụ, sự kiện mật khẩu lúc 11:02 đạt giới hạn tuổi tới mốc 11:07, còn kiểm tra authenticator lúc 11:03 đạt tới mốc 11:08, tùy quy ước biên thời gian của hệ thống. Nếu cả hai đều là điều kiện bắt buộc, không thể chỉ lấy mốc muộn hơn. Thời hạn grant hoặc hồ sơ còn có thể làm quyền hết hạn sớm hơn các mốc đó.

Nếu Lan để trang tới 11:09 rồi mới xác nhận, thiết kế này phải yêu cầu bổ sung bằng chứng mới theo chính sách. Một grant được tạo sau 11:03 không tự xóa tuổi của những kiểm tra trước đó.

Nếu Lan đã mất cả authenticator dự phòng, hệ thống phải chuyển sang đường khôi phục MFA được chấp nhận, như recovery code kết hợp những điều kiện phù hợp với loại tài khoản. Không dùng mật khẩu vừa nhập lại để kết luận Lan đã hoàn tất MFA.

Sau khi thay đổi được áp dụng, hệ thống xử lý yếu tố cũ, các session và quyền tiếp tục theo chính sách. Đổi MFA không tự bảo đảm mọi access token hoặc phương tiện truy cập khác đã hết hiệu lực ở mọi dịch vụ.

## 12. Trải nghiệm khi bằng chứng chưa đủ hoặc đã hết hạn

Thông báo nên giải thích bước cần thiết theo cách người dùng có thể thực hiện, sau khi đã xác định phạm vi thông tin được phép hiển thị.

| Tình trạng | Hướng xử lý |
|---|---|
| Có bằng chứng còn mới và đúng phương thức | Cho tiếp tục các bước được phép, không yêu cầu xác thực lại vô ích |
| Bằng chứng đúng loại nhưng quá cũ | Yêu cầu kiểm tra mới theo phương thức còn dùng được |
| Mật khẩu mới kiểm tra nhưng thao tác còn thiếu yếu tố khác | Nêu bước bổ sung hoặc đường dự phòng, không gắn nhãn đã đủ MFA |
| Người dùng mất phương thức được yêu cầu | Cho đường khôi phục tương ứng với chính sách, không lặp mãi một challenge |
| Hồ sơ còn hạn nhưng grant đã hết hạn | Đánh giá lại để cấp quyền mới khi đủ điều kiện; giữ những tiến trình vẫn hợp lệ |
| Trạng thái bảo mật đã thay đổi | Dừng áp dụng từ ngữ cảnh cũ và hướng dẫn xác minh lại phù hợp |
| Đã áp dụng thành công ở lần gửi trước | Trả kết quả theo quyền phù hợp, không yêu cầu làm lại cùng thay đổi |

Đồng hồ đếm ngược có thể giúp người dùng biết cần hoàn tất sớm, nhưng máy chủ vẫn là nơi quyết định thời hạn. Tránh hứa rằng thao tác chắc chắn được phép chỉ vì trang còn mở hoặc nút xác nhận vẫn sáng.

Khi phải quay lại bước xác minh, có thể giữ dữ liệu không nhạy cảm và trạng thái hồ sơ còn hợp lệ. Không lưu mật khẩu mới, token hoặc mã dùng một lần vào URL, log hay bản nháp để khôi phục biểu mẫu.

Thông tin về phương thức đã đăng ký hoặc tầng bảo vệ có thể nhạy cảm. Ở endpoint công khai, phản hồi cần hạn chế dò tìm tài khoản; chi tiết hướng dẫn chỉ được hiển thị khi ngữ cảnh có quyền thích hợp.

## 13. Session, audit và giám sát sau quyết định

### Không nhầm xác thực mới với thu hồi thành công

Sau một lần xác thực tăng cường, các session cũ không tự biến mất. Sau khôi phục, cần quyết định rõ phiên nào bị thu hồi, refresh token nào bị vô hiệu hóa và credential nào vẫn được chấp nhận.

Với token tự chứa, việc thay mật khẩu hoặc tăng phiên bản bảo mật không có hiệu lực thu hồi sớm ở dịch vụ chỉ kiểm tra chữ ký và thời hạn. Cơ chế thu hồi phải được bên sử dụng token thực thi. API key, passkey và quyền cấp cho ứng dụng cũng có vòng đời riêng cần được xem xét khi có khả năng chiếm quyền.

Phiên cấp sau khôi phục cần phản ánh đúng điều kiện đã đạt. Một kết quả kiểm tra recovery code không tự chứng minh rằng session đã hoàn tất mọi yếu tố đăng nhập; hệ thống có thể cần hạn chế hành động cho tới khi các điều kiện khác được đáp ứng.

### Audit cần giữ được ý nghĩa của sự kiện

Nên ghi định danh sự kiện, chủ thể, tenant, loại bằng chứng, nguồn, thời điểm xác thực gốc, thời điểm kiểm tra và quyết định cho thao tác. Đối với grant, ghi phạm vi, thời hạn, trạng thái dùng và kết quả áp dụng mà không ghi token nguyên văn.

Không ghi mật khẩu, OTP, recovery code hoặc bí mật authenticator vào log. Dữ liệu cần đủ để điều tra tại sao một thao tác được chấp nhận hoặc yêu cầu lại bằng chứng, nhưng vẫn có giới hạn truy cập và thời gian lưu phù hợp.

Các mẫu đáng xem xét gồm session liên tục được làm mới nhưng không có sự kiện xác thực mới, nhiều lần step-up thất bại rồi xin thay yếu tố, hoặc thao tác nhạy cảm ngay sau khi ngữ cảnh đổi bất thường. Tín hiệu cần được kết hợp với bằng chứng; không dùng riêng một IP mới hoặc việc đổi thiết bị để kết luận chiếm quyền.

## 14. Các tình huống kiểm tra thiết kế

| Tình huống | Kết quả kỳ vọng |
|---|---|
| Client tự khai vừa xác thực | Không được chấp nhận nếu không có sự kiện có thẩm quyền |
| Access token mới nhưng xác thực gốc đã cũ | Không được coi là vừa xác thực chỉ từ thời điểm phát token |
| Mật khẩu mới, MFA quá cửa sổ bắt buộc | Chưa đạt điều kiện yêu cầu cả hai phần phù hợp |
| Bằng chứng mới thuộc tài khoản hoặc tenant khác | Bị từ chối cho thao tác đích |
| SSO trả phản hồi mới dựa trên session cũ | Đánh giá thời điểm và thuộc tính xác thực gốc, không lấy thời điểm nhận phản hồi |
| Dấu thời gian tương lai bất thường | Không mặc định chấp nhận; xử lý sai lệch và kiểm tra nguồn theo chính sách |
| Người dùng mất yếu tố đang được yêu cầu | Có đường dự phòng đã thiết kế, không tự bỏ điều kiện và không lặp vô hạn |
| Recovery code được chấp nhận | Ghi đúng bằng chứng khôi phục và phạm vi, không tự gán đã đăng nhập đủ mọi yếu tố |
| Bằng chứng hết cửa sổ khi người dùng đang ở trang xác nhận | Kiểm tra lại ở bước áp dụng theo chính sách đã chọn |
| Trạng thái bảo mật đổi sau khi cấp grant | Grant cũ được kiểm tra lại và vô hiệu hóa khi điều kiện liên quan không còn đạt |
| Hai request đồng thời dùng cùng grant một lần | Chỉ một lần áp dụng hợp lệ |
| Retry sau khi thao tác đã commit | Không phát sinh thêm thay đổi hoặc session ngoài chính sách |

Đây là tiêu chí hành vi cần xác minh khi triển khai, bao gồm cả thời hạn, ngữ cảnh và chuyển trạng thái. Việc có màn hình nhập lại mật khẩu không chứng minh hệ thống đã đáp ứng toàn bộ các tiêu chí đó.

## 15. Bài tập áp dụng

**Đề bài:** Một ứng dụng cập nhật `authenticated_at` mỗi khi refresh token được sử dụng. Endpoint thay MFA chỉ yêu cầu timestamp này nằm trong cửa sổ nội bộ và cờ `mfa_enabled = true` trên tài khoản. Nếu người dùng chọn “mất điện thoại”, endpoint hỏi lại mật khẩu rồi cấp grant có thời hạn riêng, không kiểm tra trạng thái tài khoản khi áp dụng.

**Yêu cầu phân tích:**

1. Giải thích vì sao refresh không tự chứng minh có xác thực mới.
2. Phân biệt tài khoản đã đăng ký MFA với ngữ cảnh vừa xác thực bằng MFA.
3. Mô tả đối phương có mật khẩu hoặc session có thể lợi dụng các giả định nào.
4. Thiết kế đường thay MFA khi còn authenticator dự phòng và khi mất toàn bộ yếu tố.
5. Quy định thời hạn grant, điều kiện kiểm tra tại lúc áp dụng và hành vi retry sau thành công.

**Gợi ý:** Tách sự kiện xác thực khỏi vòng đời token và session, lưu phương thức cùng thuộc tính đã kiểm tra, đánh giá độ mới theo từng điều kiện bắt buộc và dùng bằng chứng khôi phục có phạm vi đúng. Cờ tài khoản có MFA chỉ mô tả cấu hình, không chứng minh người đang thao tác đã vượt MFA. Grant cần giới hạn rõ và được kiểm tra nhất quán với trạng thái bảo mật hiện tại.

## 16. Điều cần ghi nhớ

Yêu cầu xác thực gần đây phải nói rõ **ai đã được xác thực, bằng phương thức nào, vào lúc nào và cho thao tác gì**. Hoạt động gần nhất, token mới và một cờ xác minh chung không thay thế được các thông tin đó.

Độ mới chỉ có ý nghĩa khi bằng chứng đáp ứng đúng chính sách và còn hiệu lực trong ngữ cảnh hiện tại. Với người đã mất yếu tố, cần một đường khôi phục thực tế có mức bảo vệ phù hợp; quyền tiếp tục, thay credential và tạo session phải được giới hạn, kiểm tra lại và ghi nhận riêng.