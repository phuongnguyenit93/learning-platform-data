# New integration security checklist

## 1. Mục đích: bảo vệ quy tắc nghiệp vụ qua ranh giới hệ thống

Một tích hợp mới mở thêm đường để dữ liệu và lệnh đi vào hệ thống. Đường đó có thể là API thanh toán, webhook giao hàng, đồng bộ khách hàng, dịch vụ cấp quyền, hàng đợi sự kiện hoặc tác vụ import. Nếu chỉ kiểm tra kết nối thành công và chữ ký hợp lệ, ứng dụng vẫn có thể giao hàng khi chưa thu tiền, ghi nhận giao dịch vào sai tổ chức hoặc hoàn tiền nhiều lần sau timeout.

Trong **Business Logic Security**, câu hỏi trung tâm là:

> Khi hệ thống khác gửi dữ liệu, nhận lệnh, xử lý chậm, gửi trùng hoặc báo trạng thái không nhất quán, những quy tắc nghiệp vụ nào vẫn phải được giữ?

Checklist này giúp thiết kế và kiểm tra một tích hợp mới theo các quy tắc đó. Nó tập trung vào business invariants, state machine, quyền theo đối tượng, transaction, idempotency và tình huống tấn công logic. Kết nối được xác thực là điều kiện cần; mỗi dữ liệu được xác thực còn phải có ý nghĩa hợp lệ đối với giao dịch cụ thể.

### 1.1. Khi nào dùng checklist?

- Trước khi tích hợp một đối tác hoặc dịch vụ nội bộ mới.
- Khi thêm webhook, tác vụ nền hoặc đường đồng bộ có thể đổi trạng thái nghiệp vụ.
- Khi đổi phiên bản API, tài khoản merchant, mô hình tenant hoặc chính sách retry.
- Khi bổ sung quyền ghi vào tích hợp vốn chỉ đọc dữ liệu.
- Khi dùng lại một tích hợp cho hành động có hậu quả lớn hơn, chẳng hạn từ truy vấn giá sang tạo giao dịch.

Mỗi mục cần được đánh dấu theo một trong ba trạng thái: `[ ]` chưa hoàn tất, `[x]` đã có bằng chứng, hoặc `N/A — lý do và người xác nhận`. Không đánh dấu hoàn tất chỉ vì tài liệu đối tác có nhắc đến khả năng tương ứng; phải xác định cấu hình và hành vi mà hệ thống thực sự sử dụng.

## 2. Hồ sơ tối thiểu của tích hợp

Trước khi chọn cơ chế kỹ thuật, cần ghi rõ tích hợp được phép tạo ra thay đổi gì.

| Nội dung | Điều cần xác định |
|---|---|
| Mục đích | Thu tiền, hoàn tiền, giao hàng, cấp quyền, đồng bộ hồ sơ hay mục đích khác? |
| Chủ sở hữu | Ai chịu trách nhiệm nghiệp vụ, vận hành và liên hệ đối tác? |
| Chiều dữ liệu | Gửi lệnh, nhận webhook, polling, đọc hàng đợi hay nhập theo lô? |
| Tài sản | Tiền, tồn kho, quyền sử dụng, thông tin khách hàng hoặc hạn mức nào có thể bị ảnh hưởng? |
| Chủ thể | Người dùng nào khởi tạo; dịch vụ nào thực thi; tenant và tài khoản đối tác nào liên quan? |
| Nguồn có thẩm quyền | Hệ thống nào quyết định giá, quyền, trạng thái thanh toán và trạng thái giao hàng? |
| Định danh | ID nội bộ, ID đối tác, merchant, môi trường và phiên bản được ánh xạ thế nào? |
| Cam kết xử lý | Đối tác hỗ trợ chống trùng, tra cứu kết quả và lưu khóa trong bao lâu? |
| Thất bại | Timeout, sự kiện mất, sai thứ tự hoặc trạng thái chưa rõ được giải quyết ra sao? |
| Dữ liệu và quyền | Tích hợp cần những trường, phạm vi credential và thời hạn truy cập nào? |
| Giới hạn | Giới hạn giao dịch, thời gian xử lý, lưu dữ liệu và phạm vi hỗ trợ đã được thống nhất? |

Một sơ đồ tối thiểu nên biểu diễn được cả đường ra lẫn đường vào:

```text
Người dùng
   |
   v
API nghiệp vụ --> CSDL nội bộ + outbox --> Worker --> API đối tác
                      ^                                |
                      |                                v
                 Bộ xử lý sự kiện <-- inbox <-- Webhook
                      ^
                      |
                  Đối soát chủ động
```

Outbox lưu ý định gửi lệnh cùng transaction dữ liệu nội bộ. Inbox lưu sự kiện đã nhận để xử lý có kiểm soát. Cả hai đều không tự biến nhiều hệ thống độc lập thành một transaction duy nhất.

## 3. Ví dụ xuyên suốt: thanh toán đơn hàng và cấp quyền sử dụng

Giả sử người dùng mua một gói dịch vụ. Ứng dụng tạo đơn hàng, gọi đối tác thanh toán và cấp quyền sử dụng sau khi xác nhận tiền đã được thu theo hợp đồng tích hợp.

Một bộ bất biến mẫu:

1. Giá và quyền lợi của đơn hàng được xác định ở máy chủ, gắn với phiên bản đã chốt.
2. Giao dịch thanh toán thuộc đúng đơn hàng, tenant, tài khoản merchant và môi trường.
3. Chỉ trạng thái xác nhận đã thu tiền mới đủ điều kiện cấp quyền; tạo phiên thanh toán hoặc giữ tiền chưa mặc nhiên tương đương đã thu.
4. Số tiền và tiền tệ xác nhận phải khớp chính sách của đơn hàng.
5. Một giao dịch ngoài không được dùng để thanh toán cho nhiều đơn hàng trái quy tắc.
6. Một đơn hàng không được cấp trùng cùng một quyền lợi do retry hoặc webhook trùng.
7. Đơn hàng bị hủy, hết hạn hoặc có thanh toán muộn phải theo luồng xử lý đã định nghĩa.
8. Tác vụ hoàn tiền không được vượt số đã thu sau khi tính cả phần đã hoàn và đang giữ chỗ.

Checklist phải làm rõ giả định. Ví dụ dưới đây giả sử một đơn được thanh toán toàn bộ bằng một giao dịch, cùng một tiền tệ. Nếu sản phẩm cho phép trả thiếu, trả nhiều lần, thanh toán dư hoặc nhiều tiền tệ, cần mô hình phân bổ riêng thay vì ép mọi trường hợp vào một phép so sánh bằng.

### 3.1. Phân biệt các loại định danh

| Định danh | Ý nghĩa | Không được mặc nhiên coi là |
|---|---|---|
| `orderId` | Đơn hàng nội bộ | Bằng chứng thanh toán |
| `paymentAttemptId` | Một lần thử thanh toán | Toàn bộ lịch sử của đơn hàng |
| `providerPaymentId` | Giao dịch của đối tác | ID duy nhất trên mọi merchant và môi trường |
| `providerEventId` | Một sự kiện được gửi | ID duy nhất của tác động nghiệp vụ |
| `commandId` | Một lệnh nghiệp vụ ổn định | Mã sinh mới cho mỗi lần retry |
| `idempotencyKey` | Khóa xử lý lặp trong phạm vi cam kết | Quyền thực hiện giao dịch |
| `correlationId` | Liên kết quan sát, truy vết | Ràng buộc chống trùng có hiệu lực dữ liệu |

Cùng một giao dịch có thể sinh nhiều sự kiện khác ID. Vì vậy, chống trùng theo `providerEventId` chưa đủ để ngăn việc cấp hai lần cùng một quyền lợi.

## 4. Checklist về nguồn tin cậy và hợp đồng dữ liệu

- [ ] Đã phân loại từng trường theo nguồn có thẩm quyền và mục đích sử dụng.
- [ ] Dữ liệu từ trình duyệt, redirect hoặc ứng dụng di động không tự trở thành bằng chứng thu tiền.
- [ ] Phản hồi API và webhook được hiểu theo đúng ý nghĩa trạng thái của đối tác.
- [ ] Trường không biết, enum lạ, dữ liệu thiếu và phiên bản không hỗ trợ có chính sách xử lý rõ ràng.
- [ ] Đã xác định đơn vị tiền, độ chính xác, cách làm tròn, múi giờ và cách diễn giải thời hạn.
- [ ] Dữ liệu được chuẩn hóa và kiểm tra trước khi dùng vào so sánh hoặc tính toán nghiệp vụ.
- [ ] ID ngoài được ánh xạ trong đúng phạm vi đối tác, merchant và môi trường.
- [ ] Callback có chữ ký hợp lệ vẫn được kiểm tra quan hệ với lệnh nội bộ.
- [ ] Các thay đổi hợp đồng dữ liệu quan trọng được kiểm thử trước khi chấp nhận.
- [ ] Khi chưa thể xác minh điều kiện tạo giá trị, tích hợp không mặc nhiên cho phép giao hàng, cấp quyền hoặc chi tiền.

### 4.1. Bảng nguồn có thẩm quyền mẫu

| Dữ liệu | Nguồn quyết định | Kiểm tra cần có |
|---|---|---|
| Giá bán và quyền lợi | Danh mục hoặc báo giá nội bộ được chốt | Đúng phiên bản, chủ thể và thời hạn |
| Người sở hữu đơn | Ngữ cảnh xác thực và dữ liệu nội bộ | Đúng tenant, đúng quyền |
| Số tiền thực tế đã thu | Kết quả đối tác đã xác minh | Khớp giao dịch, merchant, tiền tệ và chính sách |
| Trạng thái đơn hàng | State machine nội bộ | Chuyển trạng thái hợp lệ từ trạng thái hiện tại |
| Quyền sử dụng đã cấp | Dịch vụ quản lý quyền | Ràng buộc duy nhất và quan hệ với nguồn cấp |
| Ghi chú hoặc metadata ngoài | Dữ liệu tham chiếu | Không dùng một mình để cấp quyền hoặc chọn tenant |

Ví dụ, một callback trả `status=success` có thể chỉ cho biết bước khởi tạo đã thành công. Cần ánh xạ trạng thái theo hợp đồng cụ thể; không đặt luật chung rằng chuỗi “success” luôn nghĩa là tiền đã được thu.

Nếu đối tác trả số tiền theo đơn vị nhỏ nhất, ứng dụng phải chuyển đổi theo quy ước tiền tệ của tích hợp. Không giả định mọi tiền tệ đều có hai chữ số thập phân. Biểu diễn tiền cần độ chính xác phù hợp, chẳng hạn số nguyên theo đơn vị đã thống nhất hoặc kiểu thập phân với quy tắc làm tròn rõ ràng.

## 5. Checklist về danh tính, tenant và quyền thực thi

Một tích hợp có credential hợp lệ vẫn có thể bị lợi dụng để hành động thay cho người không đủ quyền. Khi đó, dịch vụ có đặc quyền đang thực hiện một lệnh mà chủ thể khởi tạo không được phép yêu cầu.

- [ ] Người khởi tạo có quyền trên đúng đơn hàng, tài khoản, khách hàng hoặc tài nguyên.
- [ ] Quyền tạo lệnh được kiểm tra trước khi gọi hệ thống ngoài.
- [ ] Worker chỉ thực thi các lệnh đã được tạo qua luồng hợp lệ và còn đáp ứng điều kiện nghiệp vụ cần thiết.
- [ ] Tenant không được chọn chỉ từ trường tùy ý trong body, query, header hoặc metadata webhook.
- [ ] Ánh xạ tenant sang merchant và credential được quản lý ở máy chủ.
- [ ] Không lấy credential của tenant này để xử lý giao dịch thuộc tenant khác.
- [ ] Các endpoint đọc kết quả, retry, hủy và hoàn tiền cũng kiểm tra quyền theo đối tượng.
- [ ] Quyền tích hợp chỉ bao gồm các thao tác cần thiết; quyền đọc không mặc nhiên bao gồm tạo hoặc hoàn giao dịch.
- [ ] Luồng thay đổi credential, merchant và điểm nhận callback có quyền quản trị thích hợp.
- [ ] Thao tác cần phê duyệt có kiểm tra khác người tạo, đúng phiên bản và đúng nội dung.
- [ ] Đã xác định việc thu hồi quyền ảnh hưởng thế nào đến lệnh đã được chấp thuận và lệnh chưa được chấp thuận.

Không có một quy tắc chung rằng mọi job phải dùng lại quyền tương tác hiện tại của người khởi tạo. Có lệnh đã được chấp thuận và phải hoàn tất theo cam kết nghiệp vụ; có lệnh phải dừng khi quyền bị thu hồi. Cần phân loại rõ, lưu căn cứ chấp thuận và kiểm tra đúng chính sách tại bước thực thi.

### 5.1. Ràng buộc giao dịch vào phạm vi đúng

Một ánh xạ có thể cần các trường:

```text
tenantId
provider
environment
merchantAccountId
orderId
paymentAttemptId
providerPaymentId
expectedAmount
currency
orderVersion
```

Khi nhận webhook, phải đối chiếu với ánh xạ được thiết lập từ luồng tạo giao dịch hợp lệ. Không chỉ đọc `orderId` do bên ngoài gửi rồi cập nhật đơn mang ID đó.

Ràng buộc duy nhất nên phản ánh phạm vi ID mà đối tác cam kết, chẳng hạn `(provider, environment, merchantAccountId, providerPaymentId)`. Phạm vi thực tế cần lấy từ hợp đồng tích hợp, không suy đoán rằng ID là duy nhất toàn cục.

## 6. Checklist về lệnh gửi ra ngoài

- [ ] Lệnh được tạo từ dữ liệu nghiệp vụ đã xác minh và phiên bản đã chốt.
- [ ] Client không thể tùy ý chọn số tiền, trạng thái, người hưởng hoặc tài khoản merchant có thẩm quyền.
- [ ] Mỗi lệnh có `commandId` ổn định qua các lần gửi lại.
- [ ] Các trường ảnh hưởng tác động được giữ nhất quán khi retry.
- [ ] Đã xác định cách tra cứu lệnh cũ trước khi tạo lệnh thay thế.
- [ ] Điểm đến và credential được chọn từ cấu hình tin cậy.
- [ ] URL do người dùng cung cấp, nếu tính năng cần hỗ trợ, có chính sách đích đến, redirect và truy cập mạng phù hợp.
- [ ] Không chuyển tiếp credential sang host khác ngoài phạm vi được phép khi theo redirect.
- [ ] Thời gian chờ, retry và giới hạn tần suất phù hợp với cả khả năng đối tác lẫn quy tắc nghiệp vụ.
- [ ] Không coi lỗi mạng hoặc mã lỗi tạm thời là bằng chứng lệnh chưa được thực hiện.
- [ ] Dữ liệu nhạy cảm gửi ra ngoài được giới hạn theo nhu cầu của thao tác.

### 6.1. Khóa nội dung sau phê duyệt

Với một lệnh hoàn tiền, quyết định phê duyệt nên ràng buộc với yêu cầu và phiên bản có các dữ liệu ảnh hưởng quyết định: số tiền, tiền tệ, giao dịch gốc và người hưởng nếu nghiệp vụ cho phép chọn người hưởng.

Nếu dữ liệu này đổi sau phê duyệt, phải từ chối thay đổi hoặc yêu cầu phê duyệt lại. Một worker chỉ thấy `approved=true` nhưng lấy số tiền mới nhất từ bản ghi có thể thực thi số tiền chưa từng được duyệt.

### 6.2. Điểm đến cũng là một phần ranh giới tin cậy

Nếu một dịch vụ nhận URL tùy ý rồi gửi request bằng quyền mạng nội bộ hoặc credential mạnh, người gọi có thể điều khiển dịch vụ truy cập đích ngoài dự kiến. Cần xác định đích được phép và xác minh theo mô hình triển khai; không chỉ kiểm tra URL bắt đầu bằng một chuỗi tên miền.

Bảo vệ đường kết nối hỗ trợ bảo vệ nghiệp vụ: một lệnh hoàn tiền đúng số tiền nhưng gửi đến sai tài khoản hoặc sai môi trường vẫn là sai lệnh.

## 7. Checklist về webhook và xác minh sự kiện

Một webhook hợp lệ về mật mã chỉ chứng minh nguồn gửi theo cơ chế đang dùng. Nó chưa chứng minh giao dịch thuộc đơn hàng nào, có được phép thay đổi trạng thái hiện tại hay có đúng số tiền phải thu hay không.

- [ ] Cơ chế xác thực webhook được triển khai theo hợp đồng đối tác, bao gồm dữ liệu ký và thuật toán được chấp nhận.
- [ ] Nếu chữ ký dựa trên raw body, hệ thống giữ đúng chuỗi byte cần xác minh trước khi biến đổi JSON.
- [ ] Key ID, tài khoản gửi và cấu hình tích hợp được ánh xạ vào nguồn khóa tin cậy; không lấy khóa xác minh từ URL tùy ý do request chỉ định.
- [ ] Nếu giao thức có timestamp và cửa sổ chấp nhận, đã kiểm tra chúng theo đúng ý nghĩa của giao thức.
- [ ] Có chống phát lại và chống trùng; timestamp không được dùng thay cho ràng buộc tác động nghiệp vụ.
- [ ] Mã giao dịch, merchant, môi trường, số tiền và tiền tệ được đối chiếu với lệnh nội bộ.
- [ ] Sự kiện chưa ánh xạ được không làm ứng dụng tự tạo đơn hàng hoặc cấp quyền.
- [ ] Loại sự kiện và phiên bản không hỗ trợ không bị diễn giải thành thành công.
- [ ] Giới hạn kích thước, định dạng và chi phí xử lý của endpoint đã được xác định.
- [ ] Đã phân biệt nhận sự kiện bền vững với xử lý nghiệp vụ hoàn tất.
- [ ] Chỉ xác nhận đã nhận theo hợp đồng sau khi sự kiện hợp lệ được lưu hoặc giao vào cơ chế bền vững phù hợp.
- [ ] Có cách phát hiện và xử lý sự kiện đã nhận nhưng chưa xử lý được.

### 7.1. Không nhầm các loại thời gian

Một sự kiện có thể chứa thời điểm giao dịch xảy ra, thời điểm tạo sự kiện và timestamp của lần gửi webhook. Các giá trị này không nhất thiết giống nhau.

Sự kiện nghiệp vụ cũ có thể được gửi lại hợp lệ. Cần xác định timestamp nào được ký, timestamp nào phục vụ chống phát lại và trường nào chỉ mô tả thời điểm nghiệp vụ. Không tự loại mọi giao dịch cũ chỉ vì thời điểm phát sinh nằm ngoài cửa sổ dành cho lần truyền request.

Ngược lại, một webhook vừa đến cũng có thể mô tả trạng thái cũ. Thứ tự nhận không tự chứng minh thứ tự thay đổi tại đối tác.

### 7.2. Hai lớp chống trùng cần tách biệt

| Lớp | Mục tiêu | Ví dụ cơ chế |
|---|---|---|
| Tiếp nhận sự kiện | Không tạo nhiều bản ghi cùng một sự kiện trong cùng phạm vi | Unique key theo đối tác, tài khoản, môi trường và event ID |
| Tác động nghiệp vụ | Không cấp quyền hoặc ghi nhận tiền nhiều lần cho cùng căn cứ | Chuyển trạng thái có điều kiện và unique key theo định danh nghiệp vụ |

Một bản ghi inbox có thể ở `RECEIVED`, `PROCESSING`, `PROCESSED` hoặc trạng thái lỗi cần xử lý. Tên trạng thái tùy hệ thống, nhưng phải phân biệt được “đã nhận” với “đã áp dụng”.

Nếu webhook đến lần đầu được lưu rồi worker lỗi, lần gửi lại không được biến việc tìm thấy inbox thành kết luận rằng nghiệp vụ đã xong. Hệ thống cần tiếp tục xử lý bản ghi đang chờ hoặc có cơ chế phục hồi riêng.

## 8. Checklist về state machine và sự kiện đến sai thứ tự

- [ ] Trạng thái của đối tác được ánh xạ sang trạng thái nghiệp vụ có ý nghĩa rõ ràng.
- [ ] Trạng thái thanh toán, đơn hàng, cấp quyền và hoàn tiền được phân biệt khi chúng mô tả các vòng đời khác nhau.
- [ ] Mỗi chuyển trạng thái có điều kiện về trạng thái nguồn, giao dịch, số tiền và phiên bản liên quan.
- [ ] Không có API cho phép client gán trực tiếp trạng thái như `PAID`, `FULFILLED` hoặc `REFUNDED`.
- [ ] Kết quả trùng trở thành thao tác không làm thay đổi thêm dữ liệu khi đúng cùng căn cứ nghiệp vụ.
- [ ] Sự kiện cũ không làm lùi trạng thái trái quy tắc.
- [ ] Sự kiện mâu thuẫn được giữ làm bằng chứng và đưa vào luồng xác minh.
- [ ] Đã định nghĩa thanh toán muộn, thanh toán hai lần và kết quả đến sau hủy.
- [ ] Đã xác định khi nào phải truy vấn lại đối tác thay vì tin trực tiếp vào một sự kiện.
- [ ] Worker tạo tác động tiếp theo chỉ thực thi khi điều kiện của bước đó còn hợp lệ hoặc đã được chốt theo chính sách.

### 8.1. Bảng phản ứng mẫu

| Dữ liệu nhận được | Điều kiện nội bộ | Hành vi mẫu |
|---|---|---|
| Đã tạo phiên thanh toán | Đơn đang chờ thanh toán | Lưu tham chiếu; chưa cấp quyền |
| Đã giữ tiền, chưa xác nhận thu | Theo mô hình tách giữ và thu tiền | Ghi trạng thái giữ tiền; chưa coi là đã thu |
| Đã thu đủ tiền | Khớp đơn, tenant, merchant, tiền tệ, phiên bản và đơn còn được phép nhận thanh toán | Ghi nhận thanh toán; tạo ý định cấp quyền nguyên tử |
| Cùng kết quả thu tiền đến lại | Giao dịch đó đã được ghi nhận | Không tạo thêm cấp quyền |
| Kết quả thất bại cũ đến sau thành công | Chưa có căn cứ đảo giao dịch | Không hạ trạng thái thành chưa thanh toán chỉ theo thứ tự đến |
| Đã thu tiền sau khi đơn bị hủy | Luồng thanh toán thông thường không còn hợp lệ | Ghi nhận sự thật đã thu; áp dụng luồng thanh toán muộn hoặc đối soát |
| Hai lần thử khác nhau cùng thu tiền | Đơn chỉ cho phép thanh toán một lần | Ghi nhận đủ cả hai giao dịch; xử lý khoản thừa theo chính sách |
| Hoàn tiền hoặc đảo giao dịch | Đã có giao dịch thu tiền tương ứng | Áp dụng vòng đời hoàn hoặc điều chỉnh riêng |

Cần bảo toàn sự thật tài chính ngay cả khi không thể áp dụng đường đi thông thường của đơn hàng. Nếu đối tác đã thu tiền cho đơn bị hủy, chỉ bỏ qua webhook sẽ che giấu một khoản tiền thực tế cần xử lý.

Tương tự, sự kiện báo hoàn tiền không nên đơn giản đưa thanh toán về trạng thái “chưa từng thanh toán”. Lịch sử thu và hoàn cần đủ dữ liệu để đối soát và xác định các quyền lợi đã cấp.

### 8.2. Tranh chấp giữa cấp quyền và hủy đơn

Nếu việc cấp quyền nằm ở dịch vụ khác, sự kiện `OrderPaid` không tự giải quyết được cuộc đua với lệnh hủy. Cần có chính sách về thời điểm chốt quyền thực hiện:

- Hủy chỉ được chấp nhận trước một chuyển trạng thái nhất định, được kiểm tra nguyên tử.
- Hoặc dịch vụ cấp quyền phải xác nhận điều kiện hiện tại và từ chối lệnh đã bị vô hiệu hóa.
- Hoặc hệ thống chấp nhận thực hiện trước rồi có thao tác thu hồi theo quy tắc bù đã thiết kế.

Đây là các lựa chọn thiết kế cần phân tích theo sản phẩm. Không thể giải quyết bằng việc thêm một lần đọc trạng thái rồi vẫn để thay đổi xảy ra không phối hợp sau lần đọc đó.

## 9. Checklist về transaction, outbox và cập nhật đồng thời

- [ ] Việc ghi nhận kết quả ngoài, đổi trạng thái và tạo ý định bước tiếp theo có phạm vi transaction rõ ràng.
- [ ] Không có khoảng hở khiến trạng thái đã cập nhật nhưng lệnh tiếp theo bị mất khi tiến trình dừng.
- [ ] Các worker cạnh tranh không cùng áp dụng một chuyển trạng thái hoặc cùng tiêu một hạn mức.
- [ ] Có cơ chế khóa, cập nhật có điều kiện hoặc kiểm soát phiên bản thích hợp với bất biến.
- [ ] Các đường ghi từ webhook, polling, API quản trị và job đều dùng cùng cơ chế bảo vệ.
- [ ] Việc đánh dấu inbox đã xử lý gắn nguyên tử với các cập nhật cục bộ cần bảo vệ.
- [ ] Outbox được ghi cùng transaction với thay đổi nghiệp vụ tạo ra nó.
- [ ] Consumer của outbox chịu được việc nhận trùng và tiến trình dừng giữa các bước.
- [ ] Đã xác định cách khôi phục công việc đang xử lý khi worker chết hoặc lease hết hạn.
- [ ] Không coi khóa trong một tiến trình đơn lẻ là bảo vệ đủ cho nhiều instance.

### 9.1. Luồng xử lý inbox minh họa

Đây là mã giả cho phần cập nhật cục bộ; không phải mã triển khai hoàn chỉnh:

```text
Khi nhận webhook:
    xác thực nguồn gửi theo cấu hình tin cậy
    phân tích và kiểm tra envelope
    trong transaction tiếp nhận:
        thêm inbox bằng định danh sự kiện có ràng buộc duy nhất
        nếu đã tồn tại, giữ trạng thái xử lý hiện có
    trả phản hồi theo hợp đồng sau khi tiếp nhận bền vững

Khi worker xử lý inbox:
    trong transaction nghiệp vụ:
        khóa bản ghi inbox hoặc sử dụng cơ chế nhận việc tương đương
        nếu đã PROCESSED: kết thúc, không áp dụng lại

        đọc và phối hợp khóa các bản ghi nghiệp vụ theo thứ tự thống nhất
        kiểm tra merchant, tenant, ánh xạ giao dịch, số tiền và tiền tệ
        đánh giá chuyển trạng thái từ trạng thái hiện tại

        nếu dữ liệu không hợp lệ hoặc có mâu thuẫn:
            lưu kết quả từ chối hoặc yêu cầu đối soát
            không tạo tác động nghiệp vụ chưa được cho phép
        nếu chuyển trạng thái mới được chấp nhận:
            ghi nhận giao dịch và trạng thái mới
            ghi outbox cho tác động tiếp theo nếu cần

        đánh dấu kết quả xử lý inbox trong cùng transaction
```

Mọi tác vụ cấp quyền ở dịch vụ khác diễn ra sau transaction này. Tác vụ đó phải có định danh nghiệp vụ ổn định và cơ chế chống trùng riêng; việc đánh dấu inbox `PROCESSED` chưa chứng minh quyền đã được cấp ở dịch vụ ngoài.

Nếu cần gọi đối tác để xác minh thêm, tránh giữ khóa dữ liệu trong suốt thời gian chờ mạng. Có thể lấy kết quả xác minh trước, rồi vào transaction để kiểm tra lại trạng thái và phiên bản hiện tại trước khi áp dụng.

### 9.2. Hạn mức vẫn phải được bảo vệ nguyên tử

Với hoàn tiền, một bất biến thường là:

```text
refundedAmount + reservedRefundAmount <= capturedAmount
```

Mỗi lệnh mới phải chiếm hạn mức trong cùng phạm vi nguyên tử với việc tạo lệnh. Khi thành công, chuyển khoản giữ chỗ sang đã hoàn. Khi thất bại dứt điểm, giải phóng khoản giữ chỗ. Khi kết quả chưa xác định, không trả hạn mức chỉ vì request đã timeout.

Hai lệnh khác ID vẫn có thể cùng vượt hạn mức nếu mỗi lệnh chỉ đọc số dư rồi ghi riêng. Chống trùng sự kiện hoặc chống trùng theo ID không thay thế việc bảo vệ bất biến cộng dồn.

## 10. Checklist về idempotency và retry xuyên hệ thống

- [ ] Đã xác định một “thao tác nghiệp vụ” là gì và khi nào người dùng thực sự yêu cầu thao tác mới.
- [ ] Khóa idempotency có phạm vi rõ ràng theo tenant, client hoặc chủ thể, loại thao tác và tài khoản đối tác khi cần.
- [ ] Cùng khóa được ràng buộc với cùng nội dung nghiệp vụ; nội dung khác bị từ chối.
- [ ] Khóa gửi sang đối tác được giữ ổn định khi retry cùng một lệnh.
- [ ] Các request đồng thời cùng khóa được phối hợp bằng ràng buộc dữ liệu, không chỉ bằng kiểm tra trước khi insert.
- [ ] Đã xác định phản hồi khi thao tác đang chạy, đã xong, lỗi dứt điểm hoặc chưa rõ kết quả.
- [ ] Retry chỉ áp dụng cho nhóm lỗi và thời điểm được phép theo hợp đồng.
- [ ] Có giới hạn số lần, khoảng chờ và mức tải; retry không tạo đợt yêu cầu dồn dập khi đối tác phục hồi.
- [ ] Thời hạn lưu khóa nội bộ và thời hạn chống trùng của đối tác được ghi rõ.
- [ ] Không tự tạo khóa mới khi chưa biết lệnh cũ đã tạo tác động hay chưa.
- [ ] Truy xuất kết quả theo khóa vẫn kiểm tra quyền hiện tại.
- [ ] Ràng buộc nghiệp vụ độc lập ngăn người gọi đổi khóa để vượt quy tắc.

### 10.1. Một tình huống timeout nguy hiểm

```text
Ứng dụng gửi lệnh hoàn tiền R1 với khóa K1
Đối tác thực hiện hoàn tiền
Phản hồi bị mất
Ứng dụng tự tạo R2 với khóa K2
Đối tác coi R2 là lệnh mới và hoàn thêm lần nữa
```

Cách xử lý cần giữ lệnh `R1` và định danh ổn định của nó. Hệ thống tra cứu theo tham chiếu được hỗ trợ hoặc gửi lại với cùng khóa trong phạm vi cam kết của đối tác. Nếu không có cơ chế an toàn để kết luận, chuyển sang đối soát thay vì đoán rằng chưa thực hiện.

Chính sách phải tính cả trường hợp thời hạn lưu khóa của đối tác đã hết. Gửi lại cùng chuỗi khóa sau thời hạn đó có thể không còn được chống trùng. Không tuyên bố hiệu lực vô thời hạn chỉ vì cơ sở dữ liệu nội bộ còn giữ bản ghi.

### 10.2. Idempotency không đồng nghĩa với “exactly once”

Một mô hình phổ biến là vận chuyển có thể lặp, kết hợp chống trùng tại các điểm tạo tác động. Điều này đòi hỏi cơ chế ở từng ranh giới:

| Ranh giới | Điều cần phối hợp |
|---|---|
| Client tới API | Khóa, dấu vân tay nội dung, quyền và thao tác đã ghi nhận |
| CSDL tới outbox | Ý định gửi và thay đổi nghiệp vụ cùng transaction |
| Worker tới đối tác | Command ID, khóa ổn định và khả năng tra cứu |
| Webhook tới inbox | Định danh sự kiện, tiếp nhận bền vững và trạng thái xử lý |
| Sự kiện tới cấp quyền | Định danh quyền lợi và điều kiện tạo duy nhất |

Ví dụ, unique key theo `(tenantId, orderId, benefitType)` có thể phù hợp nếu mỗi đơn chỉ cấp một quyền lợi loại đó. Nếu đơn có nhiều dòng hoặc nhiều đơn vị được cấp riêng, phải chọn định danh phản ánh đúng đơn vị nghiệp vụ, không sao chép khóa mẫu một cách máy móc.

Dấu vân tay request cần bao gồm các trường ảnh hưởng tác động sau khi chuẩn hóa hợp lệ, chẳng hạn số tiền, tiền tệ, đơn hàng và người hưởng. Nó không thay thế việc kiểm tra quyền hoặc hạn mức.

## 11. Checklist về lỗi từng phần, đối soát và xử lý bù

- [ ] Đã phân biệt lệnh chưa gửi, đã gửi, đã xác nhận thành công, thất bại dứt điểm và chưa rõ kết quả.
- [ ] Mỗi tình huống lỗi có hành động tiếp theo, chủ sở hữu và thời hạn cần xem xét.
- [ ] Có truy vấn hoặc nguồn dữ liệu đối soát độc lập với webhook nếu nghiệp vụ cần.
- [ ] Kết quả đối soát đi qua cùng cơ chế kiểm tra trạng thái và bất biến với các đường vào khác.
- [ ] Không dùng polling để ghi đè trực tiếp trạng thái vừa được webhook cập nhật.
- [ ] Đã xác định cách xử lý khoản tiền, tồn kho hoặc quyền lợi bị giữ quá lâu.
- [ ] Xử lý bù là hành động có quyền hạn, điều kiện, định danh và audit riêng.
- [ ] Tác vụ chạy lại hoặc replay không bỏ qua kiểm tra chỉ vì do người vận hành khởi tạo.
- [ ] Đã có quy trình cho giao dịch không ánh xạ được, thanh toán thừa và sai lệch giữa hai hệ thống.

| Tình huống | Rủi ro | Hành vi cần thiết kế |
|---|---|---|
| Đối tác nhận lệnh nhưng phản hồi mất | Tạo lại tác động | Giữ định danh, đánh dấu chưa rõ và tra cứu |
| Nội bộ đã commit nhưng worker chưa gửi | Ý định bị bỏ quên | Outbox và cơ chế phục hồi công việc chờ |
| Đã nhận webhook nhưng xử lý lỗi | Mất cập nhật nghiệp vụ | Inbox bền vững, retry và theo dõi tồn đọng |
| Đã cấp quyền nhưng ghi nhận kết quả bị mất | Cấp trùng khi chạy lại | Định danh nguồn cấp và chống trùng ở dịch vụ quyền |
| Đã thu tiền nhưng không thể cung cấp dịch vụ | Giữ tiền sai chính sách | Đối soát và xử lý bù được chấp thuận |
| Hoàn tiền timeout | Vừa hoàn trùng vừa giải phóng sai hạn mức | Giữ khoản chờ phù hợp đến khi có kết luận |

Xử lý bù không phải rollback tức thời của một transaction phân tán. Một khoản hoàn tiền có thể thất bại, mất thời gian hoặc không thu hồi được quyền lợi đã sử dụng. Cần mô hình hóa cả tiến trình và kết quả của thao tác bù.

Khi chưa rõ kết quả, hành động an toàn tùy tài sản cần bảo vệ: tạm giữ hạn mức, dừng cấp quyền mới, cho phép tra cứu hoặc chuyển xử lý thủ công. Phải lưu bằng chứng và có lộ trình giải quyết, tránh để trạng thái “chờ” tồn tại không người phụ trách.

## 12. Checklist về credential, quan sát và vòng đời tích hợp

- [ ] Credential được lưu và cấp cho đúng thành phần; không đưa vào mã client hoặc log.
- [ ] Môi trường thử nghiệm và thật được tách theo cấu hình, tài khoản và dữ liệu cần thiết.
- [ ] Việc xoay khóa có kế hoạch xử lý các request hoặc webhook còn đang trên đường truyền.
- [ ] Có thể thu hồi credential bị lộ mà vẫn giữ dữ liệu phục vụ đối soát.
- [ ] Log liên kết được tenant, đơn hàng, command ID, giao dịch đối tác và event ID.
- [ ] Audit ghi rõ ai tạo, ai duyệt, phiên bản nào được thực thi và kết quả nào đã xác minh.
- [ ] Không ghi toàn bộ token, chữ ký dùng như bí mật hoặc dữ liệu nhạy cảm không cần thiết.
- [ ] Có chỉ số cho webhook không hợp lệ, sự kiện trùng, lệnh chưa rõ kết quả, backlog và sai lệch đối soát.
- [ ] Có cách tạm dừng tác động mới mà vẫn tiếp nhận bằng chứng cần thiết và xử lý giao dịch đang dở.
- [ ] Khi gỡ tích hợp, đã xét webhook muộn, command chờ, khoản giữ chỗ và nghĩa vụ dữ liệu còn lại.

Ví dụ, tắt worker gửi lệnh mới không nên đồng nghĩa xóa toàn bộ inbox hoặc bỏ theo dõi các khoản thanh toán đã gửi. Một tích hợp ngừng tiếp nhận giao dịch mới vẫn có thể cần xử lý kết quả, hoàn tiền và đối soát của giao dịch cũ.

Rate limit và hạn mức nghiệp vụ cần được tách rõ. Giới hạn số request mỗi phút giúp kiểm soát tải; quy tắc “mỗi đơn chỉ cấp quyền một lần” hay “tổng hoàn không vượt tiền đã thu” vẫn cần ràng buộc độc lập.

## 13. Ma trận kiểm thử tình huống tấn công logic

Kiểm thử tích hợp cần chứng minh kết quả nghiệp vụ, không chỉ chứng minh endpoint trả HTTP thành công. Với mỗi tình huống, kiểm tra cả dữ liệu, trạng thái, khoản giữ chỗ, số lệnh ngoài và quyền lợi thực tế được cấp.

| Tình huống | Thao tác thử | Kết quả cần quan sát |
|---|---|---|
| Giả kết quả từ trình duyệt | Sửa tham số redirect thành đã thanh toán | Không cấp quyền từ dữ liệu trình duyệt |
| Sai chữ ký | Gửi body bị sửa hoặc chữ ký không hợp lệ | Không tạo cập nhật nghiệp vụ |
| Sai tenant | Dùng sự kiện hợp lệ về xác thực nhưng ánh xạ sang tenant khác | Từ chối quan hệ; không đổi đơn sai tenant |
| Sai merchant hoặc môi trường | Dùng giao dịch của tài khoản hoặc môi trường khác | Không nhận làm thanh toán của đơn đang xét |
| Sai số tiền hoặc tiền tệ | Gửi kết quả không khớp chính sách thanh toán | Không đi theo luồng đã thu đủ tiền; lưu ngoại lệ phù hợp |
| Giữ tiền chưa thu | Gửi trạng thái chỉ thể hiện authorization | Chưa cấp quyền theo giả định của ví dụ |
| Bỏ phê duyệt | Gọi thẳng lệnh hoàn tiền từ yêu cầu chưa được duyệt | Không gửi lệnh ra ngoài |
| Sửa sau phê duyệt | Đổi số tiền hoặc giao dịch gốc trước khi worker chạy | Không thực thi nội dung chưa được duyệt |
| Trùng event ID | Gửi cùng sự kiện nhiều lần và đồng thời | Không áp dụng tác động thêm lần nữa |
| Khác event ID, cùng kết quả | Gửi hai sự kiện cùng xác nhận một giao dịch | Chỉ một căn cứ cấp cùng quyền lợi |
| Sai thứ tự | Cho trạng thái đang xử lý đến sau đã thu | Không làm lùi trạng thái trái quy tắc |
| Webhook và polling cùng cập nhật | Chạy hai đường xử lý trên cùng giao dịch | Một chuyển trạng thái và một ý định cấp quyền |
| Thu tiền sau hủy | Nhận thành công khi đơn đã bị hủy | Ghi nhận tiền thực tế; theo luồng thanh toán muộn |
| Hai lần thử cùng thành công | Xác nhận hai giao dịch cho một đơn | Không cấp trùng; khoản thu thừa được theo dõi |
| Cùng khóa, khác nội dung | Retry nhưng đổi số tiền hoặc người hưởng | Từ chối xung đột; không tạo lệnh khác dưới khóa cũ |
| Đổi khóa để lặp nghiệp vụ | Gửi nhiều khóa cho cùng yêu cầu chỉ được thực thi một lần | Ràng buộc nghiệp vụ vẫn giữ |
| Timeout sau tác động | Làm mất phản hồi sau khi đối tác đã xử lý | Không tự sinh lệnh mới; tra cứu bằng định danh cũ |
| Lỗi sau tiếp nhận | Dừng worker sau khi inbox đã được lưu | Sự kiện được khôi phục xử lý, không bị coi nhầm đã xong |
| Lỗi quanh commit | Dừng trước hoặc sau commit thay đổi và outbox | Không có trạng thái đã đổi nhưng mất ý định cần gửi |
| Hết thời hạn khóa | Mô phỏng retry khi đối tác không còn chống trùng | Áp dụng chính sách tra cứu hoặc xử lý ngoại lệ |
| Tranh hạn mức hoàn | Hai lệnh hợp lệ riêng lẻ nhưng tổng vượt tiền đã thu | Tổng giữ chỗ và đã hoàn không vượt giới hạn |
| Chạy lại tác vụ vận hành | Replay inbox, outbox hoặc batch cũ | Không bỏ qua quyền và không tạo tác động trùng |

Để kiểm tra quyền theo đối tượng và kiểm tra số tiền, cần đi qua lớp xác thực thành công trong môi trường kiểm thử rồi đưa vào dữ liệu sai quan hệ hoặc sai nghiệp vụ. Nếu mọi request đều bị chặn do sai chữ ký, bài kiểm thử mới chứng minh lớp chữ ký, chưa chứng minh các lớp phía sau.

### 13.1. Kịch bản cạnh tranh tối thiểu

Với đơn hàng chưa được cấp quyền:

1. Chuẩn bị một giao dịch đã thu tiền, khớp đầy đủ với đơn hàng.
2. Tạo hai sự kiện khác ID cùng phản ánh kết quả đó.
3. Gửi đồng thời qua hai tác vụ hoặc kết nối độc lập; có thể chạy thêm polling.
4. Đợi các worker xử lý và consumer cấp quyền hoàn tất.
5. Xác nhận chỉ có một lần chuyển trạng thái có hiệu lực và một quyền lợi theo đơn vị nghiệp vụ.
6. Xác nhận các lần nhận còn lại được ghi nhận đúng, không tạo outbox hoặc lệnh cấp quyền thừa.

Kiểm thử này cần kết hợp với ràng buộc duy nhất và cơ chế transaction đã thiết kế. Một lần chạy không gặp lỗi không chứng minh mọi cách xen kẽ đều an toàn.

### 13.2. Những thuộc tính nên kiểm tra sau mỗi chuỗi sự kiện

```text
Không có cấp quyền từ thanh toán chưa được xác minh.
Mỗi giao dịch ngoài được gắn vào đúng phạm vi tích hợp và đơn hàng.
Mỗi chuyển trạng thái được phép bởi state machine.
Không có tác động trùng ngoài cam kết xử lý lặp.
Tổng đã hoàn + đang giữ chỗ không vượt tiền đã thu.
Kết quả chưa rõ vẫn có định danh, bằng chứng và đường đối soát.
Sự kiện sai hoặc mâu thuẫn không làm mất lịch sử cần điều tra.
```

Có thể sinh các chuỗi gồm gửi trùng, đảo thứ tự, retry, hủy và nhận kết quả muộn để kiểm tra các thuộc tính này. Ưu tiên những chuỗi có thể tạo tiền, quyền lợi hoặc thay đổi tài nguyên thuộc tenant khác.

## 14. Mẫu bằng chứng cho một mục checklist

| Trường | Ví dụ |
|---|---|
| Mã kiểm soát | `INT-PAYMENT-01` |
| Quy tắc | Một đơn chỉ cấp một quyền lợi theo loại và đơn vị đã xác định |
| Giả định hợp đồng | Đã xác định trạng thái thực sự nghĩa là thu tiền thành công |
| Nguồn dữ liệu | Ánh xạ payment attempt nội bộ và kết quả đối tác đã xác minh |
| Điểm cưỡng chế | Transaction áp dụng kết quả; unique key tại dịch vụ cấp quyền |
| Các đường vào | Webhook, polling và đối soát thủ công |
| Bằng chứng | Hai sự kiện khác ID và polling chạy đồng thời; kiểm tra số quyền được cấp |
| Quan sát vận hành | Số xung đột chống trùng, backlog cấp quyền và giao dịch chưa rõ |
| Chủ sở hữu | Nhóm nghiệp vụ thanh toán cùng nhóm quản lý quyền |
| Giới hạn còn lại | Phạm vi chống trùng và những điều kiện cần xử lý ngoại lệ |

Mỗi mục chưa hoàn tất cần ghi rõ hệ quả, người phụ trách và cách xử lý. Mục `N/A` cần giải thích vì sao không có tác động tương ứng; ví dụ tích hợp chỉ đọc danh mục có thể không cần cơ chế hoàn tiền, nhưng vẫn phải kiểm tra nguồn giá nếu dữ liệu đó được dùng để bán hàng.

## 15. Điều kiện hoàn tất checklist của tích hợp mới

- [ ] Hợp đồng trạng thái, định danh, đơn vị dữ liệu và nguồn có thẩm quyền đã rõ.
- [ ] Người khởi tạo và dịch vụ thực thi có đúng quyền trên đúng đối tượng, tenant và tài khoản đối tác.
- [ ] Giá trị nhạy cảm không được quyết định trực tiếp từ client hoặc metadata ngoài.
- [ ] Chuyển trạng thái và quy tắc phê duyệt được cưỡng chế cho mọi đường vào.
- [ ] Các cập nhật liên quan hạn mức và quyền lợi được bảo vệ trước thao tác đồng thời.
- [ ] Retry, idempotency và chống replay có phạm vi cùng thời hạn được ghi rõ.
- [ ] Có đường xử lý sự kiện trùng, sai thứ tự, mất phản hồi và kết quả chưa xác định.
- [ ] Inbox, outbox và consumer có cơ chế phục hồi không tạo tác động thừa.
- [ ] Có bằng chứng kiểm thử cả lỗi xác thực lẫn lỗi nghiệp vụ sau xác thực.
- [ ] Có quan sát, đối soát, tạm dừng, xử lý bù và chủ sở hữu cho sai lệch.
- [ ] Đã xem xét tác động khi đổi khóa, đổi API hoặc ngừng tích hợp.
- [ ] Các giới hạn còn lại được ghi nhận cùng quyết định xử lý của người có trách nhiệm.

Một tích hợp bảo vệ được logic nghiệp vụ khi mọi dữ liệu và lệnh đi qua ranh giới hệ thống đều được gắn đúng danh tính, đúng tài nguyên, đúng trạng thái và đúng tác động được phép; việc gửi lại hoặc thất bại từng phần không tạo thêm quyền lợi ngoài quy tắc.
