# Kiểm tra tính hợp lệ của yêu cầu khôi phục tài khoản

## 1. Mục tiêu và phạm vi

Trong chương **Initiation Requests**, yêu cầu khôi phục là thông điệp mở đầu khi người dùng mất mật khẩu, thiết bị MFA, passkey hoặc phương tiện xác thực khác. **Recovery request validation** là quá trình máy chủ kiểm tra thông điệp đó có thể được tiếp nhận và chuyển sang bước xác minh nào theo chính sách.

Một yêu cầu có cấu trúc đúng chưa chứng minh người gửi sở hữu tài khoản. Người biết địa chỉ email của nạn nhân cũng có thể gửi đúng cấu trúc. Vì vậy, kết quả kiểm tra ở giai đoạn này chỉ cho phép bắt đầu một quy trình bị giới hạn; nó không cấp quyền đặt lại mật khẩu, xóa MFA, thêm passkey hay đăng nhập.

Sau bài học, người học cần có khả năng:

- Phân biệt kiểm tra cú pháp, kiểm tra ý nghĩa nghiệp vụ và xác minh quyền sở hữu.
- Thiết kế hợp đồng đầu vào nhỏ, rõ ràng, không nhận quyền hạn từ phía khách.
- Ràng buộc yêu cầu với đúng tenant, tài khoản, mục đích và kênh khôi phục đã đăng ký.
- Tiếp nhận yêu cầu mà không tiết lộ tài khoản tồn tại hay gây khóa tài khoản của nạn nhân.
- Xử lý giới hạn tần suất, gửi lặp và thay đổi trạng thái tài khoản trước khi phát hành bằng chứng khôi phục.

## 2. Ví dụ xuyên suốt: mất điện thoại có MFA

Lan sử dụng một ứng dụng có mật khẩu và MFA. Sau khi mất điện thoại, Lan mở trang khôi phục, nhập email và chọn lý do mất phương tiện MFA.

Máy chủ có thể kiểm tra rằng email đúng định dạng và lý do nằm trong danh sách hỗ trợ. Tuy nhiên, máy chủ chưa biết người gửi có thực sự là Lan hay không. Việc trình duyệt gửi thêm các giá trị như “đã xác minh”, “tài khoản quản trị” hoặc “gửi mã đến email mới” không tạo ra bằng chứng.

Một yêu cầu như sau chỉ thể hiện điều người gửi muốn làm:

~~~http
POST /v1/account-recovery/requests
Content-Type: application/json

{
  "identifier": "lan@example.invalid",
  "requestedAction": "RECOVER_MFA_ACCESS"
}
~~~

Sau khi tiếp nhận, hệ thống phải tự xác định tài khoản, phương án khôi phục khả dụng và bằng chứng cần thu thập. Nếu Lan không còn dùng được kênh đã đăng ký, hệ thống phải đi qua phương án xác minh thay thế được thiết kế trước. Không thể coi địa chỉ mới Lan vừa nhập là kênh đã đáng tin.

## 3. Ba loại kiểm tra cần tách biệt

| Loại kiểm tra | Câu hỏi được trả lời | Ví dụ | Kết luận tối đa |
|---|---|---|---|
| Cú pháp và cấu trúc | Máy chủ có hiểu yêu cầu một cách duy nhất không? | JSON hợp lệ, không trùng tên thuộc tính, độ dài trong giới hạn | Có thể phân tích thông điệp |
| Ý nghĩa nghiệp vụ và chính sách | Yêu cầu có phù hợp với tài khoản và luồng khôi phục được phép không? | Mục đích được hỗ trợ, tenant đúng, kênh phù hợp còn hiệu lực | Có thể bắt đầu bước tiếp theo |
| Bằng chứng và quyền hạn | Người gửi đã đáp ứng yêu cầu xác minh cho thao tác cụ thể chưa? | Bằng chứng hợp lệ và gắn đúng giao dịch | Có thể cấp một quyền khôi phục giới hạn theo chính sách |

Trong bài này, trọng tâm là hai hàng đầu. Hàng cuối là ranh giới mà quá trình tiếp nhận không được tự ý vượt qua.

Có thể diễn đạt điều kiện nội bộ bằng công thức:

~~~text
được bắt đầu xác minh =
    đầu vào có cấu trúc hợp lệ
    AND ngữ cảnh tenant được xác định đáng tin
    AND mục đích được hỗ trợ
    AND tài khoản đủ điều kiện theo chính sách
    AND phương án xác minh phù hợp tồn tại
    AND kiểm soát lạm dụng cho phép
~~~

Công thức không có điều kiện “người gửi khai đã sở hữu tài khoản”. Kết quả cũng không đồng nghĩa “được khôi phục ngay”.

Ngoài ra, **phản hồi công khai và quyết định nội bộ là hai việc khác nhau**. Một yêu cầu đúng cấu trúc cho tài khoản không tồn tại vẫn có thể nhận thông báo tiếp nhận chung, trong khi bên trong không tạo giao dịch khôi phục có quyền hạn.

## 4. Hợp đồng đầu vào: nhận nhu cầu, không nhận quyền hạn

Một API khởi tạo nên nhận ít thông tin nhất cần thiết. Bảng dưới là hợp đồng minh họa, không phải giới hạn áp dụng cho mọi sản phẩm.

| Thành phần | Quy tắc minh họa | Lý do |
|---|---|---|
| Phương thức và định dạng | POST, JSON; giới hạn kích thước body trước khi phân tích | Tránh tạo tác dụng phụ qua GET và tránh đầu vào quá lớn |
| identifier | Chuỗi bắt buộc, có giới hạn độ dài theo loại định danh | Kiểm soát tài nguyên và xác định đầu vào để tra cứu |
| requestedAction | Một giá trị thuộc enum do máy chủ quy định | Tránh tên thao tác tùy ý hoặc quyền khôi phục quá rộng |
| Trường ngoài hợp đồng | Từ chối theo một quy tắc thống nhất | Tránh vô tình ánh xạ dữ liệu khách vào mô hình nội bộ |
| Idempotency-Key nếu hỗ trợ | Có giới hạn độ dài, phạm vi và thời gian lưu rõ ràng | Hỗ trợ retry mà không liên tục tạo giao dịch hoặc gửi thông báo |

Ví dụ một triển khai chọn giới hạn body 8 KiB và định danh tối đa 320 ký tự. Đây là **quyết định thiết kế minh họa**; phải đối chiếu với loại định danh mà sản phẩm thực sự hỗ trợ, đồng thời phân biệt số byte của body với số ký tự sau khi giải mã.

Không nhận trực tiếp các trường sau làm nguồn quyết định:

~~~json
{
  "accountId": "account-of-victim",
  "tenantId": "another-tenant",
  "isVerified": true,
  "skipMfa": true,
  "recoveryLevel": "ADMIN",
  "deliveryEmail": "attacker@example.invalid",
  "callbackUrl": "https://attacker.example.invalid/collect"
}
~~~

Nếu nghiệp vụ cần một trường tương tự, phải định nghĩa và xác thực riêng. Chẳng hạn, mã tenant có thể là thông tin định tuyến công khai, nhưng máy chủ vẫn phải kiểm tra tenant đó thuộc miền phục vụ hợp lệ và tra cứu trong đúng không gian tài khoản. Không được dùng nguyên giá trị khách gửi để vượt ranh giới tenant.

### 4.1. Kiểm tra phía trình duyệt không thay thế máy chủ

Trình duyệt có thể hướng dẫn người dùng sửa email hoặc chọn một lý do hợp lệ. Những kiểm tra đó hỗ trợ trải nghiệm, nhưng người gửi có thể bỏ qua giao diện và gọi API trực tiếp.

Máy chủ cần kiểm tra lại cấu trúc, kiểu dữ liệu, giới hạn độ dài và tập giá trị. Nếu gateway và dịch vụ phân tích JSON khác nhau, cần tránh cách diễn giải mơ hồ như hai thuộc tính identifier trong cùng một object. Không để một lớp dùng giá trị đầu còn lớp khác dùng giá trị cuối.

### 4.2. Không ràng buộc trực tiếp payload vào thực thể tài khoản

Dùng một DTO riêng cho yêu cầu khởi tạo. Không đưa toàn bộ payload vào đối tượng Account hoặc cơ chế cập nhật thuộc tính tự động. Việc thêm trường vào mô hình tài khoản sau này không được vô tình mở ra quyền sửa trường đó qua API khôi phục.

Các truy vấn tra cứu dùng tham số truy vấn hoặc cơ chế tương đương, không ghép chuỗi từ identifier vào SQL. Nếu kiểm tra định dạng bằng biểu thức chính quy, cần chọn cách kiểm tra có chi phí được kiểm soát; dữ liệu dài bất thường phải bị chặn trước.

## 5. Chuẩn hóa định danh mà không đổi danh tính

Chuẩn hóa giúp tra cứu nhất quán, nhưng chuẩn hóa sai có thể đưa yêu cầu sang một tài khoản khác.

Áp dụng cùng chính sách định danh mà hệ thống đã dùng khi đăng ký và xác minh tài khoản. Không tự bổ sung quy tắc mới chỉ cho trang khôi phục.

Đối với email, cần phân biệt các thao tác:

- Loại bỏ khoảng trắng bao quanh chỉ khi hợp đồng định danh của sản phẩm cho phép.
- Xử lý phần tên miền, tên miền quốc tế và dạng tra cứu theo chính sách đã được xác định.
- Giữ nguyên hoặc chuẩn hóa phần trước dấu @ theo quy tắc tài khoản hiện hữu; không mặc định mọi nhà cung cấp có cùng hành vi.
- Không tự xóa dấu chấm hoặc phần “+tag” để gộp tài khoản.
- Không gộp hai chuỗi Unicode trông giống nhau chỉ vì chúng giống nhau khi hiển thị.

Nếu sản phẩm hỗ trợ alias, quan hệ alias phải được lưu và xác minh rõ ràng. Chỉ một thao tác biến đổi chuỗi không tạo ra quan hệ sở hữu.

Ví dụ, việc hệ thống từng coi hai địa chỉ là hai tài khoản riêng nhưng endpoint khôi phục lại bỏ “+tag” có thể làm tra cứu sai tài khoản. Cách xử lý đúng là dùng cùng chỉ mục định danh chuẩn đã được thiết kế cho sản phẩm, trong phạm vi tenant tương ứng.

Giá trị dùng tra cứu và giá trị hiển thị cũng có vai trò khác nhau. Không xuất identifier nguyên bản ra log hay thông báo lỗi chỉ để hỗ trợ gỡ lỗi.

## 6. Kiểm tra ý nghĩa nghiệp vụ bằng dữ liệu máy chủ

Sau khi nhận đầu vào, máy chủ phải nạp trạng thái có thẩm quyền thay vì dựa vào khai báo của người gửi.

### 6.1. Ràng buộc tenant và tài khoản

Khóa tra cứu có thể gồm tenant đã được xác định hợp lệ và định danh đã chuẩn hóa. Cùng một email xuất hiện trong hai tenant không có nghĩa yêu cầu cho tenant A được phép tác động tài khoản ở tenant B.

Với tenant được suy ra từ hostname hoặc thông tin gateway, cần xác thực miền phục vụ và cấu hình proxy tin cậy. Không coi mọi Host, X-Forwarded-Host hay header tự gửi từ Internet là thông tin định tuyến có thẩm quyền.

Khi tra cứu thành công, lưu định danh tài khoản nội bộ trong giao dịch. Các bước sau sử dụng quan hệ đã được ràng buộc đó, không cho khách đổi accountId giữa chừng.

### 6.2. Ràng buộc mục đích

requestedAction là nhu cầu khai báo, còn phương án khôi phục được phép do máy chủ chọn.

| Nhu cầu | Điều phải kiểm tra | Điều không được suy diễn |
|---|---|---|
| Quên mật khẩu | Tài khoản có mật khẩu cục bộ và có phương án đặt lại phù hợp không? | Được bỏ MFA sau khi đổi mật khẩu |
| Mất phương tiện MFA | Có mã dự phòng, yếu tố còn lại hoặc quy trình xác minh thay thế nào? | Biết email là đủ để xóa MFA |
| Mất passkey hoặc thiết bị | Có passkey khác hoặc phương án khôi phục đã thiết kế không? | Được đăng ký passkey mới ngay khi gửi yêu cầu |
| Mất tất cả phương tiện | Có quy trình đánh giá danh tính hoặc hỗ trợ thủ công được phê duyệt không? | Có thể chuyển sang kênh mới không cần bằng chứng |
| Tài khoản do nhà cung cấp danh tính ngoài quản lý | Hệ thống nào chịu trách nhiệm khôi phục thông tin xác thực? | Ứng dụng được tạo mật khẩu cục bộ để bỏ qua nhà cung cấp đó |

Ví dụ, một tài khoản chỉ đăng nhập liên kết có thể không có mật khẩu cục bộ. Luồng quên mật khẩu không được âm thầm tạo mật khẩu mới cho tài khoản đó. Cách hướng dẫn hoặc chuyển luồng vẫn phải cân nhắc tránh tiết lộ trạng thái tài khoản cho người chưa xác minh.

### 6.3. Ràng buộc kênh khôi phục

Kênh nhận liên kết hoặc mã phải được lấy từ hồ sơ tin cậy và còn đủ điều kiện theo chính sách.

Một số điểm cần xem xét:

- Kênh đã được xác minh trước đó hay chỉ mới được nhập?
- Kênh có vừa thay đổi và còn chịu hạn chế đối với thao tác khôi phục không?
- Loại kênh có đáp ứng mục đích và mức rủi ro của tài khoản không?
- Người dùng còn sử dụng được kênh đó hay phải đi qua quy trình thay thế?
- Trạng thái kênh có thay đổi giữa lúc tiếp nhận và lúc gửi bằng chứng không?

Không trả danh sách email, số điện thoại hoặc loại yếu tố của tài khoản ngay sau khi nhập identifier. Ngay cả giá trị bị che một phần cũng có thể giúp người khác suy đoán thông tin. Việc hiển thị chi tiết kênh cần được đặt sau mức xác minh phù hợp với thiết kế của sản phẩm.

### 6.4. Ràng buộc trạng thái tài khoản

Tài khoản đang bị vô hiệu hóa do sự cố hoặc bị hạn chế theo chính sách không được tự mở khóa bằng một yêu cầu khôi phục thông thường.

Phân biệt ít nhất các tình huống nội bộ: tài khoản không tồn tại, chưa đủ điều kiện khôi phục, đủ điều kiện tự phục vụ, cần đánh giá bổ sung và thuộc hệ thống xác thực khác. Không cần đưa các nhãn này vào phản hồi công khai.

Một lỗi tạm thời của cơ sở dữ liệu hoặc dịch vụ đánh giá rủi ro cũng không phải bằng chứng hợp lệ. Nếu chưa đủ điều kiện để quyết định, trì hoãn hoặc từ chối bước nhạy cảm theo chính sách; không mặc định cho phép bỏ qua kiểm tra.

## 7. Phản hồi công khai không làm lộ tài khoản

Endpoint khởi tạo thường không yêu cầu đăng nhập, vì người dùng đang mất quyền truy cập. Do đó, nó dễ trở thành công cụ dò tài khoản nếu phản hồi khác nhau theo kết quả tra cứu.

Với yêu cầu đúng cấu trúc, một hợp đồng minh họa là:

~~~http
HTTP/1.1 202 Accepted
Content-Type: application/json
Cache-Control: no-store

{
  "message": "Nếu thông tin phù hợp với điều kiện khôi phục, hướng dẫn tiếp theo sẽ được gửi qua phương thức đã đăng ký."
}
~~~

Trong thiết kế này, thông điệp không xác nhận tài khoản tồn tại, việc gửi đã thành công hay người gửi đã được xác minh. Mã 202 mô tả việc tiếp nhận để xử lý; nó không chứng nhận hoàn tất khôi phục.

Giữ cách phản hồi thống nhất đối với các trường hợp phụ thuộc vào trạng thái tài khoản: không tìm thấy, không đủ điều kiện, bị hạn chế hoặc bị giới hạn gửi theo tài khoản.

Lỗi cú pháp có thể được trả riêng nếu không phụ thuộc tài khoản, chẳng hạn:

| Tình huống | Phản hồi có thể công khai |
|---|---|
| Body không phải JSON hoặc sai kiểu dữ liệu | Lỗi đầu vào thống nhất, chẳng hạn 400 |
| Body vượt giới hạn | Từ chối kích thước, chẳng hạn 413 |
| Định dạng nội dung không hỗ trợ | Lỗi định dạng, chẳng hạn 415 |
| Nguồn gửi vượt ngân sách áp dụng độc lập với tài khoản | Giới hạn nguồn gửi, chẳng hạn 429 |
| Email đúng cấu trúc nhưng tài khoản không tồn tại | Cùng phản hồi tiếp nhận chung |
| Tài khoản có thật nhưng đã hết ngân sách gửi | Cùng phản hồi tiếp nhận chung; không gửi thêm |

Không dùng 429 riêng cho “tài khoản này tồn tại và đã bị giới hạn”. Nếu chính sách giới hạn nguồn gửi phụ thuộc việc tài khoản có tồn tại hay không, nó cũng có thể tạo kênh rò rỉ.

Ngoài nội dung và status code, cần xem xét header, độ dài body, chuyển hướng và thời gian xử lý. Xử lý tra cứu và gửi thông báo phía sau một hàng đợi có thể giảm chênh lệch quan sát được, nhưng không tự bảo đảm thời gian bằng nhau. Không coi một lệnh ngủ cố định là giải pháp đầy đủ cho mọi kênh thời gian.

Nếu trả mã biên nhận công khai, mã phải khó đoán và không mang thông tin về tài khoản. Endpoint kiểm tra biên nhận, nếu có, cũng không được tiết lộ trạng thái nhạy cảm mà giai đoạn khởi tạo đã chủ ý che giấu.

## 8. Chống lạm dụng trước tác dụng phụ

Yêu cầu đúng cấu trúc vẫn có thể là thư rác, nỗ lực gây tốn tài nguyên hoặc bước chuẩn bị chiếm đoạt tài khoản.

### 8.1. Áp dụng nhiều chiều giới hạn

| Chiều kiểm soát | Rủi ro được giảm | Giới hạn của tín hiệu |
|---|---|---|
| IP, mạng nguồn hoặc nguồn gửi | Tăng lưu lượng, gọi API tự động | Có NAT dùng chung và bot phân tán |
| Định danh hoặc tài khoản đích | Một nạn nhân bị nhận quá nhiều thông báo | Có thể bị kẻ khác cố ý tiêu hết ngân sách |
| Kênh nhận thông báo | Gửi dồn email hoặc SMS | Một kênh có thể liên quan nhiều yêu cầu |
| Tenant và toàn hệ thống | Chi phí gửi và quá tải diện rộng | Cần tránh để một tenant ảnh hưởng mọi tenant khác |
| Mẫu hành vi theo thời gian | Nguồn gửi thử nhiều định danh | Tín hiệu cần được kết hợp, không phải bằng chứng sở hữu |

Giới hạn phải được kiểm tra trước hành động tốn kém hoặc gây tác dụng phụ. Tại hệ thống nhiều instance, việc kiểm tra rồi tăng bộ đếm cần có tính nguyên tử phù hợp; chỉ dùng biến trong bộ nhớ từng instance có thể để lọt các yêu cầu song song.

Có thể dùng CAPTCHA hoặc thử thách chống bot theo rủi ro. Vượt thử thách chỉ làm tăng độ tin cậy rằng yêu cầu ít tự động hơn; nó không chứng minh quyền sở hữu tài khoản.

### 8.2. Không biến kiểm soát thành công cụ từ chối dịch vụ

Không khóa đăng nhập bình thường chỉ vì có nhiều yêu cầu khôi phục chưa xác minh. Nếu làm vậy, người khác chỉ cần biết email là có thể khóa tài khoản nạn nhân.

Tương tự, không liên tục vô hiệu hóa mọi token đang chờ chỉ vì xuất hiện yêu cầu khởi tạo mới. Kẻ tấn công có thể gửi lặp để làm liên kết hợp lệ của người dùng vừa nhận mất hiệu lực. Chính sách số giao dịch đang chờ, thời gian chờ gửi lại và thay thế bằng chứng cần được thiết kế rõ, với ngân sách chống lạm dụng.

Việc đạt giới hạn nên ngăn gửi thêm hoặc trì hoãn khởi tạo theo chính sách. Nó không được tự trở thành lệnh thu hồi phiên, xóa yếu tố hay thay đổi thông tin đăng nhập.

### 8.3. Ngữ cảnh trình duyệt và proxy

Nếu endpoint dựa vào cookie hoặc phiên trình duyệt, áp dụng biện pháp chống CSRF phù hợp, chẳng hạn kiểm tra nguồn yêu cầu, token chống CSRF và thuộc tính cookie theo thiết kế. CORS không phải cơ chế đầy đủ để ngăn mọi yêu cầu chéo nguồn.

Với endpoint hoàn toàn ẩn danh, vẫn phải chống gửi hàng loạt và lạm dụng thông báo; kiểm tra Origin riêng lẻ không thay thế giới hạn tần suất.

Nếu dùng IP để đánh giá rủi ro, chỉ lấy địa chỉ chuyển tiếp từ chuỗi proxy đã cấu hình tin cậy. Header X-Forwarded-For do khách tự gửi không phải dữ liệu đáng tin.

## 9. Lưu quyết định và xử lý bất đồng bộ

Một thiết kế minh họa tách tiếp nhận công khai khỏi xử lý nội bộ như sau:

~~~mermaid
flowchart TD
    A[Nhận yêu cầu] --> B[Kiểm tra cấu trúc và ngữ cảnh]
    B -->|Sai cấu trúc| C[Trả lỗi đầu vào chung]
    B -->|Đúng cấu trúc| D[Kiểm soát nguồn gửi]
    D -->|Vượt giới hạn nguồn| E[Phản hồi giới hạn nguồn]
    D -->|Được tiếp nhận| F[Ghi công việc xử lý bền vững]
    F --> G[Trả phản hồi tiếp nhận chung]
    F --> H[Tra cứu tài khoản và chính sách nội bộ]
    H -->|Không đủ điều kiện| I[Không phát hành bằng chứng]
    H -->|Đủ điều kiện| J[Kiểm tra nguyên tử ngân sách và trạng thái]
    J -->|Cho phép| K[Tạo giao dịch chờ xác minh]
    K --> L[Ghi tác vụ gửi đến kênh đã đăng ký]
    J -->|Không cho phép| I
~~~

Sơ đồ không có đường đi thẳng từ “đúng cấu trúc” đến “đã khôi phục”. Công việc bền vững ở đây có thể được triển khai bằng hàng đợi hoặc cơ chế lưu tác vụ khác; không nên trả thành công rồi chỉ giữ công việc trong bộ nhớ tiến trình.

Mã giả dưới đây minh họa thứ tự trách nhiệm, không phải mã triển khai đầy đủ:

~~~text
handleInitiation(httpRequest):
    envelope = parseBoundedRequest(httpRequest)
    input = validateStrictSchema(envelope)
    tenant = resolveAndValidateTenant(httpRequest)
    lookupKey = canonicalizeUsingRegisteredIdentityPolicy(input.identifier)

    enforceSourceAdmissionLimits(httpRequest.trustedSourceContext)

    enqueueDurably(
        tenant = tenant,
        lookupKey = lookupKey,
        requestedAction = input.requestedAction,
        callerRetryScope = validatedRetryScope(httpRequest)
    )

    return genericAcceptedResponse()

processInitiation(job):
    account = findAccount(job.tenant, job.lookupKey)

    if account is absent:
        recordMinimalOutcome("NO_ACTION")
        return

    decision = evaluateCurrentRecoveryPolicy(account, job.requestedAction)

    if decision does not allow initiation:
        recordMinimalOutcome("NO_ACTION")
        return

    transaction:
        recheckAccountAndChannelVersions(account, decision)
        enforceAtomicAccountAndDeliveryBudgets(account, decision.channel)
        deduplicateWithinValidatedRetryScope(job)
        request = createPendingProofRequest(
            accountId = account.id,
            tenantId = job.tenant,
            purpose = decision.allowedPurpose,
            channelReference = decision.channel,
            policyVersion = decision.policyVersion
        )
        appendDeliveryOutbox(request)
~~~

Đoạn mã giả lược bỏ chi tiết thử thách chống bot, hệ thống đánh giá rủi ro, lưu bằng chứng và gửi thông báo. Nếu có bước đánh giá bổ sung, thêm bước đó vào chính sách trước khi phát hành bằng chứng, không thêm đường tắt dựa trên dữ liệu khách tự khai.

Một số đặc điểm cần giữ khi hiện thực hóa:

- Lưu giao dịch và tác vụ gửi nhất quán, chẳng hạn qua transactional outbox. Tránh ghi giao dịch thất bại nhưng thông báo vẫn được gửi.
- Chọn kênh từ dữ liệu máy chủ. Nếu kênh hoặc chính sách đổi sau khi công việc vào hàng đợi, kiểm tra lại trước khi phát hành hoặc gửi; công việc cũ không được tự chuyển sang địa chỉ mới.
- Khi nhiều tiến trình xử lý cùng lúc, giới hạn và chống tạo lặp phải bảo vệ được cả cạnh tranh giữa các instance.
- Retry của bộ gửi không được biến thành nhiều quyền khôi phục độc lập ngoài chính sách.
- Nếu hàng đợi không thể tiếp nhận bền vững, trả lỗi dịch vụ chung phù hợp. Không tuyên bố đã tiếp nhận một công việc chắc chắn bị bỏ mất.

Trạng thái lưu có thể chứa mã yêu cầu, tenant, accountId nội bộ, mục đích, tham chiếu kênh, thời điểm tạo, hạn hiệu lực, phiên bản chính sách và trạng thái **PENDING_PROOF**. Các dữ liệu này do máy chủ tạo hoặc xác định; không sao chép nguyên payload khách thành giao dịch có quyền hạn.

Khi bước sau tạo token hoặc mã, bằng chứng phải được ràng buộc với đúng giao dịch, tài khoản và mục đích. Token cho đặt lại mật khẩu không mặc nhiên cho phép xóa MFA. Cơ chế hết hạn, dùng một lần và tiêu thụ nguyên tử cần được bảo đảm ở bước kiểm tra bằng chứng và thực thi thao tác tương ứng.

## 10. Retry, yêu cầu trùng và thay đổi trạng thái

Mạng không ổn định có thể khiến người dùng bấm lại. Kẻ tấn công cũng có thể chủ động tạo nhiều yêu cầu trùng. Hệ thống cần xử lý được cả hai mà không suy diễn rằng retry là một lần xác minh mới.

Nếu hỗ trợ Idempotency-Key:

1. Kiểm tra định dạng, độ dài và thời gian lưu khóa.
2. Giới hạn khóa trong ngữ cảnh người gửi do máy chủ xác lập, chẳng hạn phiên khởi tạo ngẫu nhiên, cùng tenant và nội dung yêu cầu được ràng buộc.
3. Không trả lại giao dịch của người khác chỉ vì hai bên chọn cùng một chuỗi khóa.
4. Xử lý việc cùng khóa nhưng khác nội dung bằng quy tắc rõ ràng, độc lập với việc tài khoản có tồn tại.
5. Vẫn áp dụng giới hạn tần suất; đổi khóa không được cấp lại ngân sách gửi.

Idempotency không thay thế khóa giao dịch, ràng buộc dữ liệu hoặc bộ đếm nguyên tử. Một thiết kế vẫn có thể tạo hai giao dịch nếu cả hai tiến trình cùng kiểm tra “chưa tồn tại” trước khi một tiến trình kịp ghi.

Tình huống khác: yêu cầu được tiếp nhận lúc 09:00, nhưng lúc 09:01 chủ tài khoản hoặc bộ phận bảo mật đổi trạng thái tài khoản hay thu hồi kênh. Đến 09:02, tác vụ gửi mới chạy. Dữ liệu đọc lúc 09:00 không đủ để cho phép gửi ở 09:02.

Cách xử lý là gắn phiên bản hoặc điều kiện trạng thái vào giao dịch, kiểm tra lại ở các điểm phát hành và thực thi quan trọng, rồi hủy hoặc đánh giá lại yêu cầu nếu điều kiện đã thay đổi.

## 11. Quan sát vận hành mà không rò rỉ bí mật

Nhật ký nên giúp giải thích vì sao hệ thống tiếp nhận, trì hoãn hoặc không phát hành bằng chứng, nhưng không trở thành kho dữ liệu xác thực.

Có thể ghi mã tương quan nội bộ, loại thao tác, nhóm kết quả, quyết định giới hạn và thời gian xử lý. Không ghi token, OTP, liên kết khôi phục hoàn chỉnh hoặc địa chỉ nhận nguyên vẹn vào log thông thường.

Nếu cần tương quan nhiều lần gửi theo định danh, sử dụng cơ chế giảm lộ dữ liệu phù hợp, chẳng hạn mã HMAC có khóa được quản lý và kiểm soát truy cập. Hash không khóa của email không bảo đảm ẩn danh vì không gian email có thể bị đoán và đối chiếu.

Định danh cần thiết trong hàng đợi vẫn là dữ liệu nhạy cảm: hạn chế quyền đọc, bảo vệ dữ liệu và đặt thời gian lưu phù hợp. Không gắn email, số điện thoại hoặc accountId vào nhãn metric có cardinality cao.

Theo dõi ít nhất tỷ lệ lỗi cấu trúc, mức giới hạn theo nguồn, lượng yêu cầu theo tenant, lượng thông báo thực gửi và độ trễ xử lý. Sự tăng đột biến cần dẫn đến điều tra hoặc điều chỉnh chống lạm dụng, không tự động nới lỏng yêu cầu xác minh.

## 12. Các tình huống cần kiểm chứng khi triển khai

| Tình huống | Kết quả mong đợi |
|---|---|
| JSON sai kiểu hoặc có thuộc tính trùng | Bị chặn trước khi tra cứu hoặc tạo tác dụng phụ |
| Hai định danh tương tự nhưng thuộc hai tài khoản riêng | Không bị gộp bởi quy tắc chuẩn hóa tự phát |
| Tài khoản tồn tại và không tồn tại, đầu vào cùng hợp đồng | Không khác nhau về thông tin trạng thái tài khoản trong phản hồi công khai |
| Khách thêm skipMfa hoặc deliveryEmail | Không làm thay đổi chính sách hoặc kênh nhận |
| Cùng email ở hai tenant | Chỉ tra cứu và ràng buộc trong tenant hợp lệ |
| Nhiều yêu cầu song song cho cùng tài khoản | Giới hạn và chống tạo lặp vẫn giữ đúng ngân sách |
| Đổi Idempotency-Key liên tục | Không vượt giới hạn gửi |
| Người khác gửi khôi phục dồn dập cho nạn nhân | Không tự khóa đăng nhập, xóa MFA hay thu hồi phiên của nạn nhân |
| Header IP chuyển tiếp bị giả mạo | Không thay được nguồn tin cậy mà chính sách sử dụng |
| Kênh bị thu hồi trong lúc công việc chờ xử lý | Không gửi bằng chứng đến kênh đã mất hiệu lực |
| Hệ thống đánh giá rủi ro hoặc hàng đợi gặp lỗi | Không bỏ qua bước kiểm tra hoặc báo đã tiếp nhận bền vững khi chưa thực hiện được |
| Yêu cầu chỉ mới ở PENDING_PROOF | Không thể đổi mật khẩu, thêm passkey hoặc tạo phiên đăng nhập đầy đủ |

Việc so sánh chống dò tài khoản cần xem cả nội dung, mã HTTP, header và phân bố thời gian qua nhiều lần gọi. Không thể kết luận không có rò rỉ thời gian chỉ từ một cặp phản hồi.

## 13. Vận dụng vào ví dụ của Lan

Đối với yêu cầu mất phương tiện MFA của Lan, máy chủ trước hết kiểm tra cấu trúc và giới hạn nguồn gửi. Sau khi tiếp nhận, nó tra cứu trong đúng tenant bằng chính sách định danh hiện hữu.

Nếu tìm thấy tài khoản và có phương án phù hợp, hệ thống tạo giao dịch chờ xác minh với mục đích khôi phục quyền truy cập MFA. Kênh nhận và yêu cầu bằng chứng được chọn từ dữ liệu máy chủ. Một địa chỉ mới do người gửi nhập không được dùng thay kênh tin cậy.

Nếu không tìm thấy tài khoản, tài khoản bị hạn chế hoặc đã hết ngân sách gửi, phản hồi công khai vẫn không xác nhận những trạng thái đó. Hệ thống không xóa MFA và không thu hồi phiên chỉ vì yêu cầu được gửi đến.

Khi Lan hoàn thành bằng chứng ở bước tiếp theo, máy chủ còn phải kiểm tra hiệu lực giao dịch và quyền thao tác cụ thể. Việc đặt lại thông tin xác thực, xử lý session và đăng ký yếu tố mới chỉ diễn ra tại bước đã được cấp quyền tương ứng.
