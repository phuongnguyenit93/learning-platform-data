# Recovery API compatibility: Tương thích khi tiến hóa API khôi phục tài khoản

API khôi phục tài khoản thường phục vụ nhiều thế hệ client cùng lúc: website vừa cập nhật, ứng dụng mobile chưa được nâng cấp và tích hợp của đối tác có lịch phát hành riêng. Khi bổ sung phương thức xác minh, thay định dạng token hoặc điều chỉnh hành trình khôi phục, một thay đổi nhỏ ở API có thể khiến người dùng mất đường lấy lại tài khoản.

Tuy nhiên, duy trì tương thích không có nghĩa tiếp tục cho phép một cách khôi phục đã không còn đủ an toàn. Thiết kế cần giữ ổn định hợp đồng có thể hỗ trợ, đồng thời bảo đảm client cũ không trở thành đường vòng để bỏ qua chính sách bảo mật hiện hành.

Bài học này trình bày cách quản lý hợp đồng, phiên bản, token và quá trình chuyển đổi của API khôi phục mật khẩu, MFA, passkey và thiết bị xác thực.

## 1. Tương thích có nhiều lớp

Một client gửi được request tới máy chủ mới chưa chắc đã tương thích đầy đủ.

| Lớp tương thích | Điều cần giữ | Ví dụ thay đổi có thể gây lỗi |
| --- | --- | --- |
| Thư viện hoặc mã nguồn | Client vẫn dùng được SDK theo hợp đồng đã công bố | Đổi tên hàm hoặc kiểu tham số |
| Truyền dữ liệu | Request và response vẫn được giải mã đúng | Đổi một field từ chuỗi sang object |
| Ngữ nghĩa | Client vẫn hiểu đúng kết quả và hành động tiếp theo | Dùng cùng trạng thái thành công cho cả “đã tiếp nhận” và “đã khôi phục” |
| Quy trình | Các bước cũ còn có đường tiếp tục hợp lệ | Thêm bước xác minh nhưng client không biết cách hiển thị |
| Ràng buộc bảo mật | Mọi phiên bản đều tuân thủ quyền và trạng thái cần thiết | V1 bỏ qua bằng chứng bổ sung mà V2 yêu cầu |

Google AIP-180 phân biệt source, wire và semantic compatibility. Có thể dùng cách phân loại đó để phân tích API khôi phục, nhưng đây là hướng dẫn của hệ sinh thái Google, không phải yêu cầu bắt buộc cho mọi API. Xem [AIP-180: Backwards compatibility](https://google.aip.dev/180).

Hai lỗi đối lập cần tránh:

- Chỉ quan tâm JSON còn đọc được, trong khi client hiểu sai quyền hoặc trạng thái.
- Giữ mọi hành vi cũ bằng cách cho phép người gọi chọn một phiên bản có yêu cầu xác minh yếu hơn.

Một thiết kế có thể cần từ chối an toàn trên client quá cũ và hướng dẫn người dùng chuyển sang một hành trình được hỗ trợ. Điều đó cần được nhìn nhận là thay đổi ảnh hưởng người dùng, không được che giấu bằng phản hồi thành công giả.

## 2. Xác định các ràng buộc không được nới theo phiên bản

Trước khi thiết kế V2, cần xác định những điều phải luôn đúng ở cả V1 và V2.

| Ràng buộc | Hệ quả đối với tương thích |
| --- | --- |
| Chưa đủ bằng chứng thì chưa được thay đổi tài khoản | Adapter cho client cũ không được tự coi bước mới là đã hoàn tất |
| Quyền gắn với đúng tài khoản, mục đích và giao dịch | Không lấy accountId từ body để ghi đè đích đã xác minh |
| Token hoặc quyền dùng một lần không được phát lại | Đổi phiên bản endpoint không tạo một lần sử dụng mới |
| Hết hạn và thu hồi có hiệu lực ở mọi đường vào | Không để V1 tiếp tục nhận token mà V2 đã từ chối |
| Phản hồi công khai hạn chế dò tài khoản | Bản cũ cũng không trả chi tiết tài khoản chỉ để giữ giao diện cũ |
| Chính sách MFA và passkey không bị bỏ qua | Client thiếu khả năng phải chuyển luồng hoặc dừng an toàn |
| Phiên khôi phục có phạm vi giới hạn | Không cấp phiên đăng nhập toàn quyền chỉ vì client cũ mong chờ |

Các nguyên tắc như phản hồi nhất quán, token có thời hạn và dùng một lần cũng được nêu trong [OWASP: Forgot Password](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html). Khi áp dụng cho MFA hoặc passkey, hệ thống còn cần chính sách xác minh phù hợp với thao tác đó.

Một phiên bản API cũ là một dạng hợp đồng giao tiếp được hỗ trợ, không phải một chính sách bảo mật do người gọi tùy chọn.

## 3. Phân loại thay đổi trước khi sửa hợp đồng

### Thay đổi có thể tương thích

Bổ sung một field response không bắt buộc có thể tương thích nếu client được thiết kế và tài liệu cho phép bỏ qua field chưa biết.

Ví dụ response ban đầu:

~~~json
{
  "requestId": "REQUEST_ID_MINH_HOA",
  "state": "PROOF_PENDING"
}
~~~

Response bổ sung:

~~~json
{
  "requestId": "REQUEST_ID_MINH_HOA",
  "state": "PROOF_PENDING",
  "helpUrl": "https://accounts.example.com/recovery/help"
}
~~~

Không thể kết luận thay đổi luôn an toàn chỉ vì field mới là tùy chọn. Một SDK dùng bộ giải mã quá chặt vẫn có thể lỗi; một client khác có thể tự điều hướng tới helpUrl mà không áp dụng quy tắc đích đến. Cần biết hợp đồng và cách tiêu thụ thực tế.

Những thay đổi khác thường cần xem xét gồm thêm endpoint mới, bổ sung thông tin không nhạy cảm và mở rộng tài liệu. Việc thêm dữ liệu vẫn không được làm lộ trạng thái tài khoản cho người chưa có quyền biết.

### Thay đổi thường gây phá vỡ

| Thay đổi | Vấn đề có thể xuất hiện |
| --- | --- |
| Đổi tên recoveryToken thành credential | Client cũ tiếp tục gửi field cũ |
| Đổi expiresIn từ giây sang mili giây | Client tính sai thời hạn |
| Thêm field request bắt buộc | Client cũ không gửi được dữ liệu cần thiết |
| Đổi 200 hoàn tất thành 202 đang xử lý | Client có thể hiển thị đã khôi phục khi việc chưa xong |
| Thêm trạng thái WAITING_REVIEW | Client không biết nên chờ, dừng hay tiếp tục |
| Thay định dạng token nhưng giữ bộ phân tích cũ | Client cắt ngắn hoặc kiểm tra định dạng sai |
| Yêu cầu bước xác minh bổ sung | Client cũ không có giao diện hoặc cơ chế để hoàn tất |

Đặc biệt, mở rộng một enum không luôn là thay đổi tương thích. Client cũ có thể dùng nhánh mặc định sai hoặc không giải mã được giá trị mới.

Các trạng thái không nhận diện được phải dẫn đến hành vi thận trọng: chưa cho phép thao tác nhạy cảm và cung cấp đường tiếp tục phù hợp. Không ánh xạ mọi trạng thái lạ thành SUCCESS.

### Không “bù” field bảo mật bằng giá trị mặc định dễ dãi

Giả sử V2 yêu cầu xác minh bổ sung trước khi thay MFA. Không thể làm V1 tương thích bằng quy tắc:

~~~text
Nếu client không gửi additionalProof:
    additionalProofPassed = true
~~~

Máy chủ cần xác định bằng chứng đã được kiểm tra từ trạng thái tin cậy của giao dịch. Thiếu dữ liệu cần thiết thì hành trình chưa đủ điều kiện, dù client thuộc phiên bản nào.

## 4. Dùng adapter để giữ hình dạng cũ, dùng chung lõi nghiệp vụ

Một lựa chọn kiến trúc là tách bộ chuyển đổi hợp đồng khỏi logic khôi phục.

~~~mermaid
flowchart LR
    C1[Client V1] --> A1[Adapter hợp đồng V1]
    C2[Client V2] --> A2[Adapter hợp đồng V2]
    A1 --> S[Dịch vụ khôi phục dùng chung]
    A2 --> S
    S --> P[Chính sách xác minh và cấp quyền]
    S --> T[Kho giao dịch và trạng thái token]
    S --> R[Thu hồi phiên và thông báo]
~~~

Adapter có nhiệm vụ:

- Kiểm tra request theo đúng schema của phiên bản.
- Chuyển tên field và cấu trúc sang lệnh nghiệp vụ nội bộ.
- Ánh xạ kết quả sang response cũ khi ý nghĩa vẫn chính xác.
- Từ chối hoặc hướng dẫn chuyển luồng khi hợp đồng cũ không biểu diễn được yêu cầu mới.

Adapter không có nhiệm vụ tạo ra bằng chứng xác minh, mở rộng quyền hoặc tự khôi phục một token đã hết hiệu lực.

### Ví dụ chuyển đổi request

V1 nhận:

~~~json
{
  "token": "RECOVERY_CREDENTIAL_MINH_HOA",
  "password": "MAT_KHAU_MOI_MINH_HOA"
}
~~~

V2 nhận:

~~~json
{
  "recoveryCredential": "RECOVERY_CREDENTIAL_MINH_HOA",
  "newPassword": "MAT_KHAU_MOI_MINH_HOA"
}
~~~

Cả hai có thể được chuyển thành một lệnh nội bộ:

~~~text
CompletePasswordRecovery(
    credential = credential lấy từ field được quy định,
    newPassword = mật khẩu nhận nguyên vẹn
)
~~~

Dịch vụ chung xác thực credential, tìm giao dịch, kiểm tra mục đích, quyền, thời hạn và trạng thái dùng một lần. Adapter chỉ đổi cách diễn đạt.

Không trim, đổi chữ hoa thường hoặc tự chuẩn hóa mật khẩu trong quá trình chuyển đổi. Nếu hệ thống có quy tắc xử lý mật khẩu, đó phải là một phần chính sách rõ ràng và nhất quán với đăng nhập.

### Không nhận mọi dạng field bằng một bộ giải mã mơ hồ

Nếu một endpoint đồng thời nhận token và recoveryCredential, cần quy tắc rõ cho trường hợp cả hai cùng xuất hiện. Có thể từ chối tổ hợp không hợp lệ thay vì chọn ngẫu nhiên hoặc tùy thứ tự giải mã.

Chính sách với field không biết trong command nên được xác định riêng. Việc client được phép bỏ qua field response mới không có nghĩa máy chủ phải chấp nhận mọi field request, nhất là các field có vẻ điều khiển quyền như verified hoặc skipMfa.

## 5. Tách phiên bản API, phiên bản token và chính sách xác minh

Ba loại phiên bản này có mục đích khác nhau:

| Loại phiên bản | Kiểm soát điều gì? | Nguồn quyết định |
| --- | --- | --- |
| Phiên bản API | Hình dạng request, response và quy trình giao tiếp | Hợp đồng endpoint hoặc cơ chế thương lượng đã công bố |
| Phiên bản token | Cách xác thực và diễn giải credential được hỗ trợ | Bộ xác thực tin cậy và metadata phát hành |
| Phiên bản chính sách | Điều kiện bằng chứng, quyền và xử lý rủi ro | Máy chủ và cấu hình chính sách được quản lý |

Một request tới /v1 không làm token được dùng lại, không đổi mục đích của token và không tự đưa chính sách xác minh về thời điểm V1 được phát hành.

### Dùng một nguồn chuẩn cho trạng thái giao dịch

Nếu cùng một credential được hỗ trợ qua cả hai adapter, việc tiêu thụ phải đi vào cùng trạng thái nghiệp vụ:

~~~text
POST /v1/recovery/password
    credential = C
    -> giao dịch T hoàn tất, C bị tiêu thụ

POST /v2/recovery/password
    credential = C
    -> không được thay đổi tài khoản lần thứ hai
~~~

Không lưu cờ used riêng theo phiên bản endpoint. Tương tự, giới hạn số lần thử bằng chứng phải xét phạm vi tài khoản, giao dịch hoặc các chiều rủi ro cần thiết; đổi đường dẫn API không được cấp lại một ngân sách thử độc lập ngoài thiết kế.

### Chuyển đổi định dạng credential

Nếu V2 dùng định dạng mới, máy chủ cần quy định rõ:

1. Credential cũ còn được chấp nhận trong điều kiện và thời hạn nào.
2. Endpoint nào được nhận loại credential nào.
3. Cách phát hiện loại token mà không tin một field tự khai báo của client.
4. Cách thu hồi hoặc tiêu thụ có hiệu lực trên mọi bộ xác thực liên quan.
5. Hành vi khi gặp phiên bản token không được hỗ trợ.

Không thử lần lượt nhiều bộ xác thực cho tới khi một bộ dễ dãi chấp nhận. Mỗi loại credential cần quy tắc nhận diện và xác thực đủ rõ để tránh nhầm token đăng nhập với token khôi phục.

Nếu có cơ chế đổi credential cũ sang mới, việc đổi phải kiểm tra quyền hiện có và trạng thái giao dịch. Không kéo dài thời hạn, khôi phục lượt sử dụng hoặc cấp thêm scope chỉ vì credential được đóng gói lại.

### Giao dịch đang dở khi chính sách đổi

Một bản ghi policyVersion có thể giúp truy vết quyết định trước đó, nhưng không bắt buộc máy chủ phải tiếp tục thực hiện một chính sách đã bị thu hồi vì rủi ro.

Thiết kế cần nói rõ khi nào giao dịch đang dở được tiếp tục, khi nào phải bổ sung bằng chứng và khi nào phải bắt đầu lại. Không để lựa chọn này trở thành hành vi ngầm phụ thuộc vào endpoint mà client gọi sau cùng.

## 6. Versioning và thương lượng khả năng

Một cách versioning dễ quan sát là đặt major version vào đường dẫn:

~~~text
POST /v1/recovery/requests
POST /v2/recovery/requests
~~~

Google AIP-185 dùng major version cho API của Google và mô tả việc có khoảng chuyển tiếp giữa các phiên bản. Đây là một nguồn tham khảo cho cách tổ chức hợp đồng, không bắt buộc mọi hệ thống phải chọn cùng chiến lược. Xem [AIP-185: API Versioning](https://google.aip.dev/185).

Có thể chọn versioning bằng media type hoặc một cơ chế khác, nhưng cần công bố rõ và tránh để version bị suy đoán từ nhiều tín hiệu mâu thuẫn.

Nếu dùng media type, Content-Type mô tả nội dung request, còn Accept biểu đạt dạng response client có thể nhận. Khi không hỗ trợ, các mã như 415 hoặc 406 có ý nghĩa tương ứng trong HTTP; không âm thầm giải mã theo một schema khác rồi thực hiện thay đổi tài khoản. Xem [RFC 9110: HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html).

### Khả năng client là thông tin giao tiếp, không phải bằng chứng

Client có thể khai báo rằng nó hỗ trợ một số hành động:

~~~json
{
  "supportedActions": [
    "ENTER_RECOVERY_CODE",
    "OPEN_HOSTED_RECOVERY"
  ]
}
~~~

Máy chủ có thể dùng thông tin đó để chọn cách trình bày hoặc đường tiếp tục. Nó không được dùng khai báo này để kết luận người dùng đã xác minh hoặc giảm yêu cầu bảo mật.

Ví dụ, client không hỗ trợ bước bổ sung có thể được hướng tới trang khôi phục do hệ thống quản lý. Việc chuyển giao phải bảo vệ quyền giao dịch, dùng đích đã xác định và không phát tán credential dài hạn qua URL.

Một User-Agent hoặc số phiên bản ứng dụng không phải bằng chứng rằng người gọi đang dùng phần mềm đáng tin. Kẻ tấn công có thể tự gửi các giá trị này.

### Không tự động fallback sau mọi lỗi

Client không nên hiểu 401, 403 hoặc 429 là tín hiệu thử lại cùng thao tác trên V1. Các lỗi xác thực, cấp quyền và hạn chế lạm dụng không phải lời mời tìm endpoint có chính sách yếu hơn.

Nếu hệ thống hỗ trợ một đường chuyển phiên bản hợp lệ, điều kiện chuyển phải được xác định trong hợp đồng và vẫn đi qua cùng kiểm soát nghiệp vụ.

## 7. Thay đổi trạng thái và xử lý retry

Một thay đổi từ khôi phục đồng bộ sang xử lý bất đồng bộ có thể ảnh hưởng trực tiếp đến ngữ nghĩa.

V1 có thể trả:

~~~json
{
  "result": "COMPLETED"
}
~~~

Trong khi V2 có thể cần:

~~~json
{
  "result": "PENDING",
  "nextAction": "WAIT_FOR_REVIEW"
}
~~~

Không thể ánh xạ PENDING thành COMPLETED chỉ để client cũ không lỗi. Nếu V1 không có cách biểu diễn trạng thái chờ, cần thiết kế phản hồi an toàn hoặc chuyển người dùng sang hành trình phù hợp; không tuyên bố đã khôi phục.

Các mã lỗi nghiệp vụ ổn định nên tách khỏi câu chữ hiển thị. Client không nên phân tích chuỗi thông báo để quyết định đã đủ quyền thay MFA hay chưa.

### Retry qua nhiều phiên bản

Kết nối có thể bị ngắt sau khi máy chủ đã đổi mật khẩu. Client thử lại qua endpoint khác vẫn phải chịu ràng buộc dùng một lần của cùng giao dịch.

Nếu có idempotency key, phạm vi của nó cần gắn với chủ thể hoặc quyền đã xác thực, giao dịch và thao tác nghiệp vụ. Đừng để chỉ việc đổi /v1 thành /v2 làm mất khả năng nhận diện cùng một lần hoàn tất.

Việc so sánh payload cho idempotency phải dựa trên ý nghĩa đã được giải mã hợp lệ. Không được “chuẩn hóa” làm thay đổi mật khẩu hoặc bằng chứng mà người dùng gửi.

Cũng không trả lại credential đã dùng trong một response được lưu để phục vụ retry. Kết quả được cung cấp lại chỉ nên chứa dữ liệu tối thiểu mà người gọi vẫn có quyền nhận.

## 8. Ngừng hỗ trợ phiên bản cũ một cách rõ ràng

Một kế hoạch chuyển đổi cần xác định:

- Những client và đối tác còn sử dụng hợp đồng cũ.
- Chức năng nào còn tương thích được bằng adapter.
- Thay đổi nào yêu cầu cập nhật client hoặc chuyển sang giao diện khác.
- Cách xử lý giao dịch và credential đang còn hiệu lực.
- Mốc ngừng nhận yêu cầu mới và cách kết thúc hành trình đang dở.
- Kênh thông báo và tài liệu chuyển đổi.

Có thể dùng Deprecation để báo tài nguyên đã hoặc sẽ bị đánh dấu ngừng khuyến nghị sử dụng, đồng thời liên kết tới hướng dẫn. RFC 9745 quy định giá trị ngày theo Structured Fields. Xem [RFC 9745: Deprecation](https://www.rfc-editor.org/rfc/rfc9745.html).

Sunset biểu đạt thời điểm tài nguyên dự kiến không còn đáp ứng như trước; nó có mục đích khác với thông báo deprecation. Xem [RFC 8594: Sunset](https://www.rfc-editor.org/rfc/rfc8594.html).

Ví dụ header với các mốc hoàn toàn minh họa:

~~~http
Deprecation: @1893456000
Sunset: Mon, 01 Jul 2030 00:00:00 GMT
Link: <https://developer.example.com/recovery/migrate-v2>; rel="deprecation"; type="text/html"
Cache-Control: no-store
~~~

Trong ví dụ, Deprecation tương ứng ngày 01/01/2030 UTC, còn Sunset là ngày 01/07/2030 UTC. Khi dùng cả hai, mốc Sunset không được sớm hơn mốc Deprecation theo RFC 9745.

Header là tín hiệu cho client và nhà phát triển, không phải bảo đảm mọi ứng dụng cũ sẽ đọc nó. Cần có cách truyền thông phù hợp với các bên sử dụng thực tế.

Sau khi ngừng hỗ trợ, phản hồi của endpoint cũ phải nhất quán và không làm lộ tài khoản tồn tại hay không. Không chuyển tiếp bí mật tới một đích mới tùy ý, và không giữ một endpoint bỏ qua xác minh chỉ để “client cũ vẫn chạy”.

## 9. Triển khai chuyển tiếp và rollback không làm sống lại quyền

Trong giai đoạn chuyển đổi, adapter V1 và V2 có thể chạy song song trên cùng lõi nghiệp vụ. Cần quản lý tương thích giữa các phiên bản máy chủ nữa, vì một đợt triển khai có thể tạm thời chứa cả node cũ lẫn node mới.

Một hướng tổ chức là mở rộng cấu trúc lưu trữ để cả hai thế hệ máy chủ cùng đọc được, chuyển dần cách sử dụng, rồi mới loại cấu trúc cũ khi không còn bên phụ thuộc. Với dữ liệu xác minh và quyền, mọi quy tắc mặc định trong quá trình chuyển đổi cần được xác định rõ.

Rollback phần mềm không được đồng nghĩa rollback trạng thái bảo mật. Không phục hồi snapshot khiến token đã dùng trở lại chưa dùng, không xóa dấu thu hồi và không giảm số lần thử đã ghi nhận.

Nếu máy chủ cũ không hiểu trạng thái bảo mật mới, việc đưa nó trở lại phục vụ giao dịch đó có thể không an toàn. Khi đó cần giới hạn rollback hoặc giữ giao dịch ngoài phạm vi xử lý của node không đủ khả năng.

Dữ liệu vận hành phục vụ chuyển đổi có thể gồm phiên bản API, loại client đã khai báo, số lượng yêu cầu và mã lỗi không nhạy cảm. Không cần thu token, mật khẩu hay mã dự phòng để biết client nào đang gặp vấn đề tương thích.

Một API khôi phục có khả năng tiến hóa tốt cho phép nhiều hợp đồng giao tiếp cùng tồn tại trong thời gian cần thiết, nhưng chỉ có các quyết định quyền được kiểm soát nhất quán. Khi hợp đồng cũ không còn biểu diễn được yêu cầu an toàn, hệ thống phải cung cấp đường chuyển đổi rõ ràng thay vì làm yếu bước xác minh.

