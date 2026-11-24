# Recovery initiation notification — Thông báo khi bắt đầu khôi phục tài khoản

## 1. Thông báo khởi tạo xác nhận sự kiện nào?

**Recovery initiation notification** là thông báo cho chủ tài khoản biết hệ thống đã ghi nhận một yêu cầu khôi phục liên quan đến tài khoản. Yêu cầu có thể nhằm đặt lại mật khẩu, lấy lại quyền truy cập khi mất MFA, khôi phục sau khi mất passkey hoặc thay thiết bị xác thực.

Sự kiện bắt đầu khôi phục chưa chứng minh ai là người yêu cầu. Một người lạ biết email đăng nhập cũng có thể gửi yêu cầu. Vì vậy, thông báo cần mô tả đúng điều hệ thống biết: có một yêu cầu đã được tiếp nhận, với mục đích và thời điểm cụ thể. Không viết “Bạn đã yêu cầu” nếu chưa xác thực được người khởi xướng.

Thông báo này giúp người dùng nhận biết hoạt động ngoài dự kiến và biết cách xem xét hoặc báo cáo. Nó không tự xác minh danh tính, phê duyệt khôi phục, đổi mật khẩu, xóa MFA, đăng ký passkey hay tạo session đăng nhập.

| Thông điệp | Sự kiện được xác nhận | Quyền phát sinh từ việc nhận hoặc đọc |
| --- | --- | --- |
| Phản hồi tại trang yêu cầu | Hệ thống đã tiếp nhận đầu vào theo hợp đồng công khai | Không có quyền đối với tài khoản |
| Thông báo khởi tạo | Một yêu cầu khôi phục được ghi nhận trong phạm vi được mô tả | Không có quyền thực hiện tác vụ khôi phục |
| Thư chứa challenge hoặc liên kết tiếp tục | Một cơ chế kiểm tra bằng chứng đã được cấp | Chỉ quyền được policy của challenge quy định khi xác minh hợp lệ |
| Thông báo hoàn tất | Một thay đổi cụ thể đã thực sự hoàn thành | Không tự tạo thêm quyền đăng nhập |

Một sản phẩm có thể ghép thông báo khởi tạo và hướng dẫn tiếp tục trong cùng email. Khi đó, phần có token phải được thiết kế như một challenge bảo mật riêng. Không coi toàn bộ email là một thông báo thông thường rồi bỏ qua phạm vi, thời hạn và kiểm soát sử dụng của token.

Bài này dùng một thiết kế minh họa cho dịch vụ khôi phục tài khoản. Các trạng thái, trường dữ liệu và quy tắc điều phối bên dưới là đề xuất thiết kế cần điều chỉnh theo mô hình đe dọa của sản phẩm, không phải cấu hình bắt buộc của một nhà cung cấp.

## 2. Chọn thời điểm phát sinh thông báo

Điểm kích hoạt phải tương ứng với một sự kiện nội bộ đã tồn tại bền vững. Ví dụ: hệ thống đã xác định tài khoản, chấp nhận một yêu cầu khôi phục theo policy và commit recovery request. Nếu giao dịch tạo request rollback, không gửi thư nói rằng request đó đã được tạo.

Luồng tiếp nhận có thể phân biệt ba kết quả nội bộ:

1. Không có tài khoản phù hợp hoặc yêu cầu không đủ điều kiện để tạo giao dịch.
2. Có một giao dịch hợp lệ nhưng thông báo đang được hạn chế hoặc gộp theo chính sách chống lạm dụng.
3. Có giao dịch hợp lệ và một ý định gửi thông báo được lưu để xử lý.

Các kết quả này không nhất thiết được công khai khác nhau tại endpoint chưa xác thực. Một phản hồi có thể là:

> Nếu thông tin phù hợp với tài khoản và yêu cầu đủ điều kiện, hướng dẫn sẽ được gửi qua kênh đã đăng ký.

Không trả về địa chỉ nhận đã che, notification ID hay trạng thái chuyển phát chỉ ở nhánh tài khoản tồn tại. Những khác biệt này có thể trở thành tín hiệu dò tài khoản dù câu thông báo chính giống nhau.

[OWASP Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html) khuyến nghị phản hồi nhất quán, hạn chế khác biệt thời gian xử lý và chống yêu cầu tự động quá mức. Đây là cơ sở cho việc tách phản hồi công khai khỏi quyết định gửi nội bộ trong ví dụ này.

Xử lý bất đồng bộ giúp tách thời gian chuyển phát khỏi HTTP request, nhưng không tự bảo đảm hai nhánh có thời gian giống nhau. Cần tránh đường thoát nhanh dễ phân biệt và tránh đưa kết quả tra cứu vào những trường công khai khác.

## 3. Người nhận phải đến từ nguồn tin cậy

Địa chỉ nhận thông báo bảo mật phải được chọn từ dữ liệu tài khoản và policy mà server kiểm soát. Trường “email mới để liên hệ” do người đang khôi phục nhập chưa đủ điều kiện để thay thế kênh thông báo của chủ tài khoản.

Ví dụ, một người nhập email của nạn nhân để mở request, sau đó đưa địa chỉ của họ làm “email nhận kết quả”. Nếu hệ thống gửi mọi cảnh báo sang địa chỉ mới, người yêu cầu có thể vừa điều khiển luồng vừa che hoạt động khỏi chủ tài khoản.

Có thể lưu tham chiếu tới một phiên bản contact đã xác minh, chẳng hạn một địa chỉ email hoặc kênh bảo mật đã đăng ký. Tham chiếu này cần thể hiện rõ nó được chọn theo policy nào và tại thời điểm nào.

| Tình huống | Cách xử lý cần được định nghĩa |
| --- | --- |
| Tài khoản có email bảo mật đã xác minh | Chọn contact theo policy, không lấy địa chỉ tùy ý trong request |
| Người dùng báo mất điện thoại | Không mặc định SMS tới điện thoại đó là kênh có thể tiếp cận |
| Mất thiết bị chứa passkey | Có thể dùng kênh cảnh báo khác đã đăng ký; kênh cảnh báo không tự trở thành bằng chứng thay passkey |
| Không còn kênh nhận khả dụng | Ghi nhận hạn chế và áp dụng nhánh khôi phục phù hợp; không tự giảm điều kiện xác minh |
| Contact thay đổi khi job đang chờ | Đánh giá lại phiên bản contact và policy; không tự chuyển job sang địa chỉ mới |

Việc chọn contact tại thời điểm tạo sự kiện và việc kiểm tra trước khi gửi là hai việc khác nhau. Lưu phiên bản được chọn giúp giải thích quyết định ban đầu. Kiểm tra lại giúp tránh gửi tới một contact đã bị thu hồi. Nếu policy yêu cầu gửi cảnh báo tới cả địa chỉ cũ và mới khi thay contact, hãy biểu diễn thành các ý định gửi riêng có lý do rõ ràng.

Không tự sửa lịch sử người nhận của một thông báo đã gửi để trông giống cấu hình tài khoản hiện tại.

## 4. Nội dung cần rõ ràng và tiết lộ ít dữ liệu

Thông báo nên cho người nhận biết sự kiện, thời điểm, tác vụ được yêu cầu và cách xem xét an toàn. Tên sản phẩm và giọng văn cần nhất quán để người dùng dễ nhận diện.

Một mẫu email thông báo thuần túy có thể là:

~~~text
Tiêu đề: Đã ghi nhận yêu cầu khôi phục tài khoản

Hệ thống đã ghi nhận một yêu cầu khôi phục quyền truy cập
liên quan đến tài khoản của bạn.

Thời điểm ghi nhận: 24/11/2026, 14:30 (UTC+07:00)
Nội dung yêu cầu: Khôi phục quyền truy cập khi mất thiết bị xác thực

Thông báo này ghi nhận việc bắt đầu một yêu cầu;
nó không xác nhận rằng việc khôi phục đã hoàn tất.

Nếu bạn đang thực hiện yêu cầu, hãy tiếp tục theo hướng dẫn
trong ứng dụng hoặc trang khôi phục chính thức đã mở.

Nếu bạn không nhận ra hoạt động này, hãy tự mở ứng dụng
hoặc nhập địa chỉ trang web chính thức để xem mục Bảo mật
và báo cáo yêu cầu không mong muốn.

Nhân viên hỗ trợ không yêu cầu bạn gửi mật khẩu,
mã xác thực hoặc mã dự phòng để xử lý thông báo này.
~~~

Đây là mẫu cho thông báo không chứa challenge. Nếu người dùng đang bị đăng xuất, trang được hướng dẫn phải có đường hỗ trợ phù hợp với trạng thái đó; không bắt họ đi qua một chức năng chỉ truy cập được sau khi đã khôi phục xong.

Không viết “mật khẩu của bạn vẫn an toàn” hoặc “tài khoản chưa có thay đổi nào” chỉ dựa vào thời điểm tạo request. Khi email đến muộn, có thể đã có sự kiện khác xảy ra. Nội dung nên gắn với sự kiện đã quan sát thay vì khẳng định trạng thái hiện tại chưa được kiểm tra.

Không đưa vào thông báo thuần túy:

- Mật khẩu, OTP, mã dự phòng, cookie, khóa riêng hoặc nội dung hồ sơ xác minh.
- Kết luận nội bộ về độ tin cậy của bằng chứng, điểm rủi ro hay lý do phê duyệt chi tiết.
- Tên thiết bị, vị trí hoặc IP do client tự khai báo nhưng được trình bày như dữ kiện đã xác minh.
- Toàn bộ email, số điện thoại hoặc định danh cá nhân khi mục đích chỉ cần nhận biết sự kiện.

Nếu hiển thị vị trí ước lượng từ mạng, cần diễn đạt đúng mức chắc chắn và cân nhắc quyền riêng tư. Không dùng vị trí đó để kết luận ai đã mở request. Với push trên màn hình khóa, nội dung cần ngắn và ít chi tiết hơn trang bảo mật sau khi đã kiểm tra quyền.

## 5. Liên kết xem xét không được trở thành đường cấp quyền ngoài ý muốn

Thông báo thuần túy có thể hướng tới một trang bảo mật ở tên miền được cấu hình sẵn. Trang này phải kiểm tra quyền trước khi tiết lộ giao dịch hoặc thực hiện hành động. Biết request ID hay bấm một liên kết xem chi tiết không tự chứng minh quyền sở hữu tài khoản.

Một số quy tắc thiết kế hữu ích:

- Tạo URL từ origin chính thức do server quản lý; không ghép tên miền từ đầu vào của request.
- Không dùng liên kết rút gọn hoặc tên miền khiến người nhận khó nhận diện dịch vụ.
- Không cho tham số điều hướng dẫn sang một địa chỉ tùy ý.
- Không đặt một hành động thay đổi tài khoản trực tiếp trên GET chỉ vì người dùng mở thư.
- Không để bot xem trước email hoặc trình quét liên kết vô tình phê duyệt, hủy hay tiêu thụ quyền khôi phục.

Nếu sản phẩm cần nút “Không phải tôi”, hãy xác định quyền của nút đó. Một capability chỉ cho báo cáo request cụ thể cần được giới hạn vào đúng mục đích đó; nó không được đổi mật khẩu, đăng xuất mọi thiết bị hoặc vô hiệu hóa MFA. Thiết kế có thể mở trang xác nhận và áp dụng kiểm tra bổ sung trước tác động nhạy cảm.

Không tự khóa tài khoản hoặc thu hồi mọi session chỉ vì một người chưa xác thực đã gửi yêu cầu khôi phục. Một hành động bảo vệ có tác động lớn cần căn cứ và policy riêng; nếu không, tính năng cảnh báo có thể bị biến thành công cụ từ chối dịch vụ.

## 6. Chống gửi dồn dập mà vẫn giữ được tín hiệu bảo mật

Thông báo khởi tạo có thể bị lạm dụng để làm đầy hộp thư, gây phiền nhiễu hoặc khiến người dùng bỏ qua một cảnh báo quan trọng xuất hiện sau đó. Giới hạn tại IP là chưa đủ nếu nguồn tấn công phân tán; chỉ giới hạn theo tài khoản cũng chưa đủ để bảo vệ toàn bộ hạ tầng gửi.

Một mô hình kiểm soát có thể phối hợp:

| Phạm vi | Mục đích |
| --- | --- |
| Nguồn yêu cầu | Hạn chế tự động hóa và lưu lượng bất thường |
| Tài khoản hoặc contact đích | Hạn chế số thông báo một nạn nhân phải nhận |
| Tenant và toàn hệ thống | Bảo vệ ngân sách, năng lực hàng đợi và nhà cung cấp |
| Loại thông báo | Tách chính sách khởi tạo khỏi phê duyệt, thay đổi yếu tố và hoàn tất |
| Request cụ thể | Gộp các lần yêu cầu gửi lại không cần thiết |

Thời gian chờ và ngân sách phải được xác định theo sản phẩm. Không có một con số phù hợp cho mọi luồng mất mật khẩu, MFA và passkey. Trong hệ thống nhiều instance, quyết định tiêu thụ ngân sách cần có cơ chế đồng thời phù hợp; kiểm tra cục bộ rồi cập nhật sau có thể để nhiều worker cùng vượt hạn mức.

Phân biệt **loại trùng kỹ thuật** và **giảm tần suất nghiệp vụ**:

- Cùng một sự kiện được chuyển tới worker hai lần: dùng định danh ổn định để không tạo hai ý định gửi mới.
- Hai request khác nhau cùng nhắm một tài khoản: đó là hai sự kiện, dù policy có thể gộp hoặc hạn chế thông báo cho người nhận.

Khi một cảnh báo bị hạn chế, vẫn giữ được dấu vết nội bộ tối thiểu về quyết định và lý do. Có thể hiển thị tổng hợp trong khu vực bảo mật khi người dùng có quyền truy cập. Không bỏ mọi cảnh báo tiếp theo chỉ vì một nguồn tấn công đã dùng hết ngân sách của thông báo khởi tạo.

Cụ thể, thông báo về việc MFA đã được thay hoặc tài khoản đã được khôi phục cần chính sách riêng. Dùng chung một cooldown cho mọi loại thông điệp có thể khiến đợt yêu cầu rác che khuất sự kiện có tác động lớn hơn.

## 7. Lưu ý định gửi cùng sự kiện khởi tạo

Thiết kế cần xử lý khoảng hở giữa việc commit recovery request và việc gọi nhà cung cấp email hoặc SMS. Gửi trước commit có thể tạo thông báo cho một request không tồn tại; gửi sau commit mà không lưu công việc có thể làm mất thông báo khi tiến trình dừng.

Có thể dùng transactional outbox: trong cùng giao dịch với request, lưu sự kiện và ý định chuyển tiếp. Sau commit, worker nhận công việc rồi thực hiện chuyển phát. Outbox không làm việc gửi tới nhà cung cấp trở thành một phần của giao dịch cơ sở dữ liệu.

[AWS — Transactional outbox pattern](https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/transactional-outbox.html) mô tả cách xử lý vấn đề ghi kép này và lưu ý rằng chuyển tiếp có thể trùng, nên bên xử lý phải có khả năng nhận biết bản sao.

~~~mermaid
sequenceDiagram
    participant U as Người yêu cầu
    participant R as Recovery Service
    participant D as Cơ sở dữ liệu
    participant W as Notification Worker
    participant P as Nhà cung cấp
    U->>R: Gửi yêu cầu khôi phục
    R->>R: Áp dụng chính sách tiếp nhận
    R->>D: Commit request và ý định thông báo
    R-->>U: Phản hồi công khai nhất quán
    W->>D: Nhận công việc đã commit
    W->>W: Kiểm tra contact, policy và thời hạn gửi
    W->>P: Gửi với định danh chuyển phát ổn định
    P-->>W: Kết quả chấp nhận hoặc lỗi
    W->>D: Lưu kết quả chuyển phát
~~~

Sơ đồ mô tả nhánh có request hợp lệ và được phép gửi. Nó không yêu cầu phải tạo một notification thật cho mọi đầu vào không khớp tài khoản. Đối với nhánh bị hạn chế gửi, có thể lưu quyết định nội bộ thay cho một công việc chuyển phát.

Nếu thông báo là kiểm soát bắt buộc của một nhánh khôi phục, cần định nghĩa điều kiện tiến trình được tiếp tục: đã lưu bền vững ý định gửi, nhà cung cấp đã chấp nhận hay một điều kiện khác. Không để trạng thái gửi ngầm trở thành quyết định phê duyệt khôi phục.

## 8. Hợp đồng dữ liệu của một thông báo

Một envelope minh họa có thể chỉ mang tham chiếu và dữ liệu cần thiết cho template:

~~~json
{
  "notificationId": "2ab43612-31be-4f37-9561-c92d7122908f",
  "sourceEventId": "907f2c54-b887-42cf-9449-064bc572ed43",
  "type": "RECOVERY_INITIATED",
  "requestId": "551aff05-b6be-49b6-a3b7-a42177d53239",
  "subjectAccountId": "b28bf766-2a43-4ba9-972a-2bb408158401",
  "recipientContactRef": "contact-42-version-3",
  "channel": "EMAIL",
  "locale": "vi",
  "templateVersion": "recovery-initiated-v1",
  "policyVersion": "recovery-notification-v2",
  "occurredAt": "2026-11-24T07:30:00Z",
  "sendBefore": "2026-11-24T08:00:00Z",
  "variables": {
    "purposeLabel": "Khôi phục quyền truy cập khi mất thiết bị xác thực"
  }
}
~~~

Thời hạn gửi 30 phút trong dữ liệu trên chỉ là ví dụ về độ mới của thông báo. Nó không phải thời hạn của recovery token hoặc quy định chờ trước khi thay MFA. Mỗi loại thời hạn phải có ý nghĩa riêng.

Ý nghĩa của các nhóm trường:

- **Nguồn gốc:** source event và request liên kết thông báo với sự kiện đã commit.
- **Đích gửi:** tham chiếu contact giúp chọn đúng phiên bản mà không đưa địa chỉ nhận vào mọi message trung gian.
- **Tái hiện:** phiên bản template, locale và policy giúp giải thích nội dung đã chọn.
- **Độ mới:** thời điểm sự kiện và hạn gửi giúp nhận diện công việc đã quá cũ.
- **Dữ liệu trình bày:** chỉ chứa biến được template cho phép; không serialize nguyên recovery request.

Tham chiếu nội bộ vẫn là dữ liệu cần kiểm soát truy cập. Không trả nguyên envelope cho người chưa xác thực hoặc đưa nó vào URL công khai. Nhà cung cấp cuối cùng có thể cần địa chỉ thực để gửi; việc dùng contact reference chỉ giảm phạm vi sao chép, không loại bỏ trách nhiệm bảo vệ địa chỉ đó.

Template và nhãn tác vụ phải được chọn từ giá trị server kiểm soát. Mọi nội dung có nguồn từ người dùng cần được mã hóa phù hợp khi dựng HTML, và không được chèn trực tiếp vào header email.

## 9. Trạng thái chuyển phát phải có ngữ nghĩa riêng

Có thể quản lý một công việc qua các trạng thái sau:

| Trạng thái | Điều hệ thống biết |
| --- | --- |
| PENDING | Công việc đã được lưu và chưa được worker nhận |
| LEASED | Một worker đang có quyền xử lý trong thời gian giới hạn |
| PROVIDER_ACCEPTED | Nhà cung cấp đã chấp nhận yêu cầu gửi |
| DELIVERY_REPORTED | Có báo cáo chuyển phát với ngữ nghĩa do nhà cung cấp định nghĩa |
| RETRY_WAIT | Có lỗi tạm thời đủ điều kiện thử lại |
| DELIVERY_UNKNOWN | Chưa biết nhà cung cấp đã nhận hoặc gửi hay chưa |
| FAILED | Công việc kết thúc theo chính sách xử lý lỗi |
| SUPPRESSED | Policy chủ động không gửi |
| EXPIRED | Không còn phù hợp để gửi vì quá thời hạn |

Nhà cung cấp chấp nhận không có nghĩa người dùng đã nhận hoặc đọc. Một báo cáo phát thành công cũng không chứng minh người đọc là chủ tài khoản. Trạng thái chuyển phát không được dùng như bằng chứng đủ để đặt lại mật khẩu hoặc thay MFA.

Một trường hợp khó là timeout sau khi gửi: nhà cung cấp có thể đã nhận thư, trong khi worker chưa lưu được kết quả. Đánh dấu “chưa gửi” và gửi lại ngay có thể tạo bản sao. Nếu nhà cung cấp hỗ trợ idempotency, dùng cùng định danh của cùng một ý định gửi trong các lần thử lại, theo đúng hợp đồng và thời hạn họ hỗ trợ. Nếu có API đối soát, tận dụng nó để giải quyết trạng thái chưa biết.

Nếu không có cơ chế loại trùng xuyên hệ thống, cần chấp nhận khả năng gửi trùng và đặt chính sách thử lại hữu hạn. Không tuyên bố email được gửi đúng một lần chỉ vì bảng notification có khóa duy nhất.

Worker có lease cần cơ chế nhận việc và lưu kết quả an toàn khi lease hết hạn. Một worker cũ không được ghi đè kết quả của lần xử lý mới chỉ vì nó vừa trở lại sau timeout. Có thể dùng phiên bản lease để kiểm tra quyền cập nhật, đồng thời vẫn cần cơ chế xử lý tác động gửi bên ngoài.

## 10. Công việc đến muộn và request đã đổi trạng thái

Trước khi gửi, worker cần biết thông báo còn phù hợp hay không. Một job khởi tạo có thể được xử lý sau khi request đã hủy, hết hạn hoặc hoàn tất. Nếu gửi nguyên văn “hãy tiếp tục khôi phục ngay”, người nhận có thể nhầm rằng request còn hiệu lực.

Policy cần phân biệt hai mục đích:

1. **Hướng dẫn có tính thời điểm:** chỉ hữu ích khi request còn đủ điều kiện tiếp tục; quá hạn thì không gửi hướng dẫn cũ.
2. **Cảnh báo về sự kiện đã xảy ra:** có thể vẫn cần gửi sau đó, nhưng phải ghi rõ thời điểm sự kiện và không khẳng định trạng thái hiện tại.

Không tự đổi loại thông báo từ “khởi tạo” sang “hoàn tất” chỉ bằng cách đọc trạng thái mới nhất. Thông báo hoàn tất phải dựa trên sự kiện hoàn tất tương ứng. Nếu cần thay thế job cũ, ghi nhận quyết định đó để có thể giải thích vì sao một thư không được phát.

Kiểm tra trước khi gửi không loại bỏ hoàn toàn cuộc đua với thay đổi xảy ra ngay sau đó. Vì vậy, nội dung nên vẫn đúng khi được đọc muộn; mọi đường dẫn thực hiện tác vụ phải kiểm tra lại trạng thái và quyền ở thời điểm sử dụng.

## 11. Quan hệ với MFA, passkey và session

Mất thiết bị có thể đồng thời làm mất kênh nhận cảnh báo và phương thức xác thực. Đây là tình huống phải được dự kiến trong thiết kế, không phải lý do để coi email bất kỳ là bằng chứng đủ thay thế mọi yếu tố.

[OWASP Multifactor Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html) thảo luận riêng về reset và thay đổi yếu tố MFA. Khi áp dụng các ý tưởng thông báo của bài này cho MFA hoặc passkey, cần giữ nguyên yêu cầu xác minh của chính luồng đó.

Một session còn tồn tại trên thiết bị khác có thể giúp người dùng xem cảnh báo. Tuy nhiên, quyền xem, quyền báo cáo và quyền cho phép tác vụ nhạy cảm phải được kiểm tra riêng. Session đang đăng nhập không mặc nhiên thỏa yêu cầu xác thực gần đây hoặc policy phê duyệt thay yếu tố.

Nhận, đọc hoặc bỏ qua một cảnh báo khởi tạo không được tự:

- Cấp session đầy đủ cho người đang khôi phục.
- Nâng mức xác thực của session hiện có.
- Thu hồi tất cả session của chủ tài khoản.
- Xác nhận thiết bị mới là đáng tin cậy.

Nếu cần phản ứng mạnh hơn khi phát hiện dấu hiệu chiếm đoạt, đó là quyết định bảo vệ tài khoản có căn cứ riêng và cần được ghi nhận bằng sự kiện phù hợp.

## 12. Tình huống vận dụng

Một tài khoản có email bảo mật đã xác minh và đang mất điện thoại chứa ứng dụng MFA. Người dùng mở yêu cầu khôi phục. Gần cùng lúc, một nguồn khác tạo nhiều yêu cầu vào cùng tài khoản.

Cách xử lý trong thiết kế minh họa:

1. Endpoint tiếp nhận không trả khác biệt công khai để xác nhận tài khoản tồn tại hoặc tiết lộ email bảo mật.
2. Request đủ điều kiện được lưu cùng sự kiện và ý định thông báo; việc tiếp nhận chưa thay MFA hay tạo session mới.
3. Người nhận được chọn từ email bảo mật đã xác minh. Email liên hệ mới nhập trong request không tự thay thế đích cảnh báo.
4. Policy theo tài khoản và nguồn giảm các thư khởi tạo lặp lại; dấu vết lạm dụng vẫn được lưu ở nơi có quyền truy cập phù hợp.
5. Worker gửi thông báo đầu tiên nhưng gặp timeout. Công việc được xử lý như kết quả chưa biết, không giả định chắc chắn rằng thư chưa được gửi.
6. Nếu một thông báo khởi tạo đến muộn, nội dung vẫn mô tả thời điểm bắt đầu. Trang xem xét kiểm tra trạng thái hiện tại thay vì tin dữ liệu cũ trong thư.
7. Nếu MFA sau đó thực sự được thay, sự kiện hoàn tất tạo cảnh báo riêng theo policy của thay đổi yếu tố; ngân sách thư khởi tạo không tự che mất cảnh báo này.

Ở mỗi bước, cần giữ riêng ba kết luận: **yêu cầu đã bắt đầu**, **thông báo đã được xử lý đến đâu**, và **tác vụ khôi phục đã được cho phép hoặc hoàn tất hay chưa**. Chỉ dữ kiện tương ứng mới được dùng để cập nhật từng kết luận.
