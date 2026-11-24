# Administrator notification trong khôi phục tài khoản

## 1. Mục đích của thông báo cho quản trị viên

Trong quy trình khôi phục tài khoản, một thay đổi nhỏ có thể làm thay đổi người kiểm soát quyền truy cập: phát hành token thay mật khẩu, gỡ MFA, thu hồi passkey, thay kênh khôi phục hoặc cho phép đăng ký thiết bị mới. Các hành động này cần được nhìn thấy bởi những người có trách nhiệm bảo vệ tài khoản và vận hành dịch vụ.

**Administrator notification** là cơ chế đưa sự kiện khôi phục tới đúng quản trị viên, đúng phạm vi và với đủ ngữ cảnh để họ có thể xử lý. Thông báo có thể phục vụ yêu cầu phê duyệt, phát hiện lạm dụng, theo dõi thực thi hoặc cảnh báo quy trình đang gặp lỗi.

Trong module `SECURITY_AUTHENTICATION_ACCOUNT_RECOVERY`, thông báo hỗ trợ khôi phục an toàn khi người dùng mất mật khẩu, MFA, passkey hoặc thiết bị xác thực. Nó kết nối đánh giá rủi ro, xác minh danh tính, token dùng một lần, chống lạm dụng và kiểm soát phiên thành một quy trình có thể quan sát và phản ứng.

Thông báo tự nó không xác minh danh tính, không cấp quyền khôi phục và không thay thế phê duyệt. Một email đã được nhà cung cấp chấp nhận cũng không chứng minh rằng người trực đã đọc hoặc xử lý sự kiện.

Ba câu hỏi cần được trả lời cho mỗi loại thông báo là:

1. Ai cần biết sự kiện này, và vì sao họ có quyền biết?
2. Người nhận cần thực hiện hành động nào trong hệ thống chính thức?
3. Nếu thông báo không đến hoặc không được xử lý, quy trình sẽ tiếp tục thế nào?

## 2. Phân biệt người nhận và mục đích

Không nên gộp mọi thông báo về khôi phục thành một email gửi cho tất cả quản trị viên. Mỗi nhóm có trách nhiệm khác nhau và quyền truy cập dữ liệu khác nhau.

| Nhóm người nhận | Mục đích | Ví dụ |
| --- | --- | --- |
| Nhóm vận hành khôi phục | Theo dõi hồ sơ và xử lý tác vụ đang chờ | Cần bổ sung bằng chứng, yêu cầu sắp hết hạn |
| Người phê duyệt được phân công | Ra quyết định trong phạm vi được cấp | Đề xuất gỡ MFA đang chờ phê duyệt độc lập |
| Nhóm an ninh | Phát hiện và điều tra dấu hiệu lạm dụng | Nhiều lần khôi phục tài khoản đặc quyền từ các nguồn bất thường |
| Quản trị viên tenant | Theo dõi thay đổi thuộc tenant của mình | Tài khoản quản trị tenant vừa được khôi phục |
| Nhóm vận hành hệ thống | Xử lý lỗi kỹ thuật | Hàng đợi thông báo tồn đọng hoặc kênh gửi bị gián đoạn |

Thông báo cho **chủ tài khoản** là một luồng riêng. Người dùng có thể cần biết rằng ai đó đã yêu cầu khôi phục tài khoản của họ hoặc một yếu tố xác thực vừa bị thay. Nội dung dành cho chủ tài khoản không nên mặc nhiên giống nội dung điều tra dành cho nhóm an ninh.

Nếu tài khoản đích là tài khoản của một quản trị viên, không chỉ gửi thông báo cho chính người đó rồi coi như đã có giám sát độc lập. Theo policy, cần định tuyến tới nhóm an ninh hoặc người có trách nhiệm độc lập. Đây là trường hợp tài khoản đặc quyền có thể đang bị chiếm, nên phiên và kênh liên lạc của chủ tài khoản cũng cần được đánh giá rủi ro.

## 3. Những sự kiện nào cần phát thông báo?

Sự kiện nên mô tả điều đã xảy ra hoặc điều đang cần xử lý, thay vì một trạng thái mơ hồ như `RECOVERY_UPDATE` cho mọi tình huống.

| Sự kiện | Ý nghĩa vận hành | Hành động có thể cần |
| --- | --- | --- |
| Yêu cầu khôi phục được tiếp nhận | Có hồ sơ mới hợp lệ về mặt tiếp nhận | Phân loại nếu thuộc diện xử lý thủ công |
| Rủi ro vượt ngưỡng policy | Quy trình tự động không được tiếp tục như bình thường | Điều tra hoặc chuyển luồng kiểm soát cao hơn |
| Đề xuất đang chờ phê duyệt | Cần quyết định cho một snapshot cụ thể | Xem bằng chứng và phê duyệt hoặc từ chối |
| Đề xuất bị thay đổi hoặc phê duyệt hết hiệu lực | Quyết định cũ không còn đủ điều kiện | Xem lại đề xuất hiện tại |
| Quyền khôi phục được phát hành | Một khả năng nhạy cảm vừa được cấp | Theo dõi với tài khoản hoặc tình huống cần giám sát |
| Khôi phục đã áp dụng | Trạng thái xác thực đã thực sự thay đổi | Kiểm tra hậu xử lý theo policy |
| Thu hồi phiên thất bại hoặc chưa hoàn tất | Một phần quyền truy cập cũ có thể còn hiệu lực | Xử lý sự cố và giới hạn ảnh hưởng |
| Có dấu hiệu vượt quyền hoặc bỏ qua phê duyệt | Đường quản trị có hành vi bị từ chối đáng chú ý | Điều tra an ninh |
| Gửi thông báo bắt buộc thất bại kéo dài | Lớp quan sát hoặc điều phối không hoạt động | Chuyển kênh dự phòng hoặc xử lý sự cố |

Không phải mọi yêu cầu đặt lại mật khẩu thông thường đều phải gọi người trực. Việc phát quá nhiều cảnh báo làm giảm khả năng nhận biết sự kiện quan trọng. Policy cần phân loại mức độ và mục đích: thông tin để tra cứu, tác vụ phải xử lý, cảnh báo cần phản ứng ngay.

Các yếu tố phân loại có thể gồm mức đặc quyền của tài khoản, số yếu tố bị mất, dấu hiệu chiếm tài khoản, yêu cầu thay kênh liên lạc, số lần thử gần đây, mức độ khẩn cấp và kết quả xác minh danh tính. Không để client tự gửi `severity=LOW` rồi quyết định mức cảnh báo của chính yêu cầu đó.

Đối với sự kiện nhạy cảm, thông báo phải nêu rõ **trạng thái thực tế**. “Đã được phê duyệt” không có nghĩa “đã thực thi”; “đã gửi yêu cầu thu hồi phiên” không có nghĩa “mọi phiên đã mất hiệu lực”. Tách các trạng thái giúp người trực không đóng sự cố quá sớm.

## 4. Xác định người nhận từ nguồn đáng tin cậy

Một lỗi nguy hiểm là lấy địa chỉ quản trị viên từ biểu mẫu khôi phục:

```text
Người yêu cầu nhập adminEmail
        ↓
Hệ thống gửi chi tiết hoặc liên kết xử lý tới adminEmail đó
```

Người yêu cầu có thể nhập địa chỉ do mình kiểm soát, biến thông báo thành công cụ lấy dữ liệu hoặc giả mạo người có thẩm quyền.

Người nhận phải được phân giải từ nguồn phân quyền và cấu hình đáng tin cậy, ví dụ danh bạ quản trị tenant, danh sách trực ca được quản lý hoặc nhóm an ninh đã được phê duyệt. Cần xét ít nhất:

- Tenant và tài khoản đích của hồ sơ.
- Vai trò hiện tại và phạm vi quyền của người nhận.
- Loại sự kiện và trách nhiệm xử lý.
- Trạng thái hoạt động của danh tính và kênh nhận.
- Các điều kiện độc lập, như loại trừ người lập yêu cầu khỏi nhóm phê duyệt theo policy.

Một địa chỉ thuộc domain công ty chưa đủ để chứng minh có quyền nhận. Một người có vai trò quản trị ở tenant A cũng không được nhận dữ liệu khôi phục của tenant B. Với danh sách phân phối hoặc kênh chat, cần quản lý cả thành viên, quyền truy cập lịch sử và khả năng chuyển tiếp của kênh.

Nếu thay đổi người nhận hoặc kênh nhận là thao tác nhạy cảm, bản thân thao tác đó cần kiểm soát và truy vết. Không cho một người vừa đổi toàn bộ đích nhận cảnh báo sang địa chỉ của mình, vừa thực hiện khôi phục mà không có lớp giám sát độc lập phù hợp.

### Người nhận thay đổi khi thông báo đang chờ

Một quản trị viên có thể bị thu hồi quyền sau khi sự kiện được tạo nhưng trước khi email được gửi lại. Vì vậy, trước mỗi lần gửi dữ liệu nhạy cảm, cần kiểm tra lại người nhận còn đủ điều kiện theo policy. Không gửi lại vô hạn đến một địa chỉ đã bị loại khỏi phạm vi.

Nếu dùng thông báo tối giản chỉ dẫn người nhận vào console, máy chủ vẫn phải kiểm tra quyền hiện tại mỗi lần mở hồ sơ. Một email cũ không giữ lại quyền đọc sau khi vai trò đã bị thu hồi.

Việc thay người nhận không nên xóa mất lịch sử. Lưu nhóm đích hoặc quyết định định tuyến lúc tạo sự kiện, các lần phân giải sau đó, người nhận thực tế và lý do thay đổi. Nếu không tìm thấy người nhận hợp lệ cho một thông báo bắt buộc, ghi rõ lỗi và chuyển theo tuyến dự phòng đã cấu hình.

## 5. Nội dung đủ để phản ứng, không mang theo bí mật

Một thông báo tốt giúp người nhận nhận biết loại sự kiện, phạm vi, mức độ và bước xử lý. Nó không nên trở thành bản sao hồ sơ xác minh danh tính.

Ví dụ nội dung tối giản:

```text
Chủ đề: [Recovery][Cần xem xét] Hồ sơ AR-2481

Một đề xuất khôi phục MFA đang chờ xử lý trong tenant bạn quản lý.
Mức độ: cần phê duyệt độc lập theo policy.
Phạm vi đề xuất: đăng ký lại yếu tố xác thực đã mất.
Mã hồ sơ: AR-2481
Thời điểm sự kiện: 09:10, 24/11/2026, Asia/Saigon.

Mở console bảo mật chính thức để xem bằng chứng và quyết định.
Thông báo này không chứa token khôi phục và không thực hiện phê duyệt.
```

Mốc thời gian trên chỉ minh họa cách hiển thị rõ múi giờ. Trong triển khai, lưu thời gian theo một chuẩn nhất quán và chuyển sang múi giờ thích hợp khi trình bày. Phân biệt thời điểm sự kiện xảy ra với thời điểm thông báo được gửi, nhất là khi hàng đợi bị chậm.

Nội dung có thể bao gồm mã hồ sơ không mang quyền truy cập, loại hành động, mức độ, trạng thái và đường dẫn tới console. Nếu cần nhận diện tài khoản, chỉ hiển thị dữ liệu tối thiểu phù hợp với kênh và quyền người nhận. Một màn hình khóa điện thoại hoặc tiêu đề email có thể bị người ngoài nhìn thấy.

Không đưa các dữ liệu sau vào thông báo vận hành thông thường:

- Mật khẩu hiện tại hoặc mật khẩu mới.
- OTP, backup code, khóa bí mật MFA hoặc token khôi phục đầy đủ.
- Liên kết mang quyền đăng nhập hoặc quyền đổi yếu tố xác thực không cần xác thực lại.
- Bản chụp giấy tờ, dữ liệu định danh thô hoặc toàn bộ hồ sơ xác minh.
- Cookie, refresh token, header xác thực hoặc nội dung phiên quản trị.

Các chi tiết bằng chứng và tín hiệu điều tra nên được xem trong hệ thống có phân quyền và ghi nhận truy cập. Việc một quản trị viên có quyền xử lý tác vụ không mặc nhiên cho phép xuất tất cả bằng chứng ra email.

### Bảo vệ template và liên kết

Dữ liệu như tên hiển thị, lý do yêu cầu và ghi chú có thể do người không đáng tin cậy nhập. Khi đưa vào HTML, phải escape đúng ngữ cảnh. Với email dạng văn bản, vẫn cần ngăn xuống dòng trái phép trong header, chèn liên kết giả và nội dung đánh lừa người nhận.

Tạo liên kết từ origin console đã được cấu hình và xác minh. Không xây origin từ header `Host`, `X-Forwarded-Host` hoặc một tham số `returnUrl` chưa được kiểm soát. Hạ tầng proxy có thể cung cấp các header hợp lệ trong kiến trúc đã cấu hình, nhưng không nên mặc định mọi giá trị nhận được đều đáng tin cậy.

Liên kết hồ sơ chỉ là định vị. Người mở vẫn phải đăng nhập, có quyền trên tenant và đáp ứng yêu cầu xác thực tăng cường nếu thực hiện hành động nhạy cảm. Đoán được mã hồ sơ không được tạo ra quyền đọc hoặc quyền khôi phục.

## 6. Thông báo, xác nhận đã nhận và phê duyệt là ba việc khác nhau

Một hệ thống có thể ghi nhận ba loại hành động riêng:

| Hành động | Nó chứng minh điều gì? | Nó không chứng minh điều gì? |
| --- | --- | --- |
| Nhà cung cấp chấp nhận gửi | Thông điệp đã được bên gửi tiếp nhận | Người cần xử lý đã đọc |
| Quản trị viên xác nhận đã nhận | Một người được xác thực nhận trách nhiệm xử lý theo contract | Đề xuất đã được phê duyệt |
| Quản trị viên phê duyệt | Người có quyền đồng ý với snapshot cụ thể | Tác vụ đã thực thi thành công |

Theo dõi mở email hoặc click liên kết không phải bằng chứng chắc chắn rằng quản trị viên đã đọc. Công cụ quét bảo mật có thể tự mở link; một người cũng có thể mở email nhưng chưa kiểm tra bằng chứng.

Nếu cần xác nhận đã nhận, thực hiện trong console hoặc qua tích hợp được xác thực, kiểm tra quyền và ghi nhận danh tính người nhận trách nhiệm. Không coi một pixel được tải là sự kiện hoàn tất tác vụ.

Nếu cần phê duyệt, quyết định phải gắn với snapshot bất biến của yêu cầu, có kiểm tra quyền và các điều kiện độc lập. Không chấp nhận trả lời email “OK” hoặc nhấn một liên kết công khai để thay thế toàn bộ cổng phê duyệt. Hành động thay đổi trạng thái không nên xảy ra chỉ vì một trình quét truy cập link bằng phương thức GET.

Thông báo cũ cũng cần được xử lý đúng: khi đề xuất đã bị hủy, hết hạn hoặc thay phiên bản, mở link phải hiển thị trạng thái hiện tại. Không cho nút trong email cũ thực thi quyết định đối với đề xuất mới.

## 7. Gửi bền vững bằng sự kiện và outbox

Không nên gửi email trực tiếp rồi mới cập nhật trạng thái khôi phục, hoặc cập nhật xong rồi gửi email theo cách không lưu dấu vết. Cách thứ nhất có thể gửi thông báo về một thay đổi chưa từng được commit. Cách thứ hai có thể bỏ mất thông báo nếu tiến trình dừng ngay sau khi dữ liệu khôi phục đã được ghi.

Nếu trạng thái và outbox nằm trong cùng cơ sở dữ liệu giao dịch, có thể ghi chúng trong một giao dịch:

```text
Giao dịch nghiệp vụ:
  kiểm tra điều kiện và chuyển trạng thái yêu cầu
  ghi sự kiện nghiệp vụ có event_id ổn định
  ghi một hàng outbox cho sự kiện đó
  commit

Bộ gửi thông báo:
  nhận sự kiện đã commit
  phân giải người nhận và kênh còn hợp lệ
  dựng thông báo tối thiểu từ template được quản lý
  gửi qua adapter tương ứng
  lưu từng lần thử, phản hồi và trạng thái giao nhận
```

Nếu hệ thống phân tán dùng event log hoặc cơ chế giao sự kiện khác, cần bảo đảm tương đương theo contract của kiến trúc. Chỉ gọi một message broker bên trong đoạn code có annotation giao dịch không tự tạo ra giao dịch nguyên tử giữa broker và cơ sở dữ liệu.

Một cấu trúc sự kiện minh họa:

```yaml
eventId: 972f25d1-8e34-49d5-a116-7b9a08d8a082
eventType: RECOVERY_APPROVAL_REQUIRED
schemaVersion: 1
tenantId: 3372ca68-c75c-4aba-b675-b2e1e268e3e0
requestId: d1aca98c-0620-43c2-bde6-c634858505d7
proposalVersion: 2
occurredAt: '2026-11-24T02:10:00Z'
severity: ACTION_REQUIRED
routingPolicyId: ADMINISTRATIVE_RECOVERY_REVIEW
```

Sự kiện không chứa token, mật khẩu hoặc tài liệu xác minh. Người gửi nạp dữ liệu được phép từ dịch vụ nghiệp vụ; không tin toàn bộ payload do người yêu cầu khôi phục gửi lên. Quyền phát sự kiện và quyền dùng hàng đợi cũng cần được giới hạn để kẻ tấn công không tự tạo cảnh báo giả.

### Retry và chống gửi trùng

Lỗi mạng, giới hạn tốc độ hoặc timeout có thể yêu cầu gửi lại. Bộ gửi cần giới hạn số lần thử, tăng khoảng chờ phù hợp, thêm độ lệch ngẫu nhiên và phân biệt lỗi tạm thời với lỗi không thể khắc phục bằng retry.

Một khóa chống trùng có thể gồm:

```text
event_id + recipient_identity + channel + notification_purpose
```

Lưu phiên bản template đã dùng và giữ các lần retry của cùng thông báo nhất quán. Nếu nội dung cần sửa vì sự kiện nghiệp vụ đã thay đổi, phát thông báo cập nhật có quan hệ rõ ràng với sự kiện trước, thay vì âm thầm thay nội dung của một quyết định đã gửi.

Khóa chống trùng trong cơ sở dữ liệu giúp ngăn nhiều worker tạo cùng một tác vụ gửi. Tuy nhiên, nếu nhà cung cấp đã nhận thông điệp nhưng phản hồi bị mất, lần retry vẫn có thể tạo email thứ hai trừ khi phía nhận hỗ trợ cơ chế chống trùng tương ứng. Thiết kế phải chấp nhận khả năng gửi ít nhất một lần và bảo đảm bản sao không gây thêm tác dụng phụ bảo mật.

Không để việc gửi lại thông báo tạo token khôi phục mới, thay đổi thời hạn hồ sơ, cộng thêm phiếu phê duyệt hoặc thực thi lại hành động. Vòng đời thông báo và vòng đời quyền khôi phục phải được tách rõ.

### Thứ tự và sự kiện đến muộn

Thông báo “đang chờ phê duyệt” có thể tới sau thông báo “đã hủy” nếu các kênh có độ trễ khác nhau. Gắn request ID, phiên bản đề xuất và thời điểm sự kiện vào dữ liệu để đối chiếu. Console luôn hiển thị trạng thái hiện tại và lịch sử, không suy ra trạng thái chỉ từ email đến sau cùng.

Trước khi gửi một tác vụ đã chờ lâu, có thể kiểm tra nó còn có ích hay không. Nếu yêu cầu đã đóng, đánh dấu thông báo tác vụ là không còn phù hợp và ghi lý do theo policy. Không âm thầm bỏ cảnh báo an ninh chỉ vì hồ sơ đã được đóng; dấu hiệu lạm dụng vẫn có thể cần điều tra.

## 8. Xử lý khi thông báo là điều kiện của quy trình

Không phải mọi loại thông báo đều có ảnh hưởng giống nhau tới quyền tiếp tục khôi phục. Policy nên định nghĩa rõ mức bảo đảm cần có.

| Loại yêu cầu | Điều kiện ví dụ | Khi không đạt |
| --- | --- | --- |
| Thông tin hậu xử lý | Lưu được sự kiện và tác vụ gửi bền vững | Retry, theo dõi tồn đọng và chuyển tuyến khi vượt ngưỡng |
| Tác vụ cần người tiếp nhận | Người trực có quyền xác nhận đã nhận | Chuyển người hoặc nhóm trực theo quy trình |
| Thao tác cần phê duyệt | Có quyết định hợp lệ cho snapshot hiện tại | Giữ chờ, hết hạn hoặc từ chối theo policy |
| Hành động yêu cầu thông báo trước | Đạt tiêu chí giao nhận được policy chấp nhận trước khi có tác dụng | Chưa áp dụng hành động; dùng kênh dự phòng đã duyệt nếu có |

“Gửi thành công” phải có định nghĩa cụ thể: đã tạo tác vụ, nhà cung cấp chấp nhận, báo phát tới hòm thư, hay người có quyền xác nhận đã nhận. Các mức này không tương đương và đều có giới hạn. Báo phát của email không chứng minh một con người đã đọc; xác nhận đã nhận cũng không thay thế quyết định phê duyệt.

Nếu cần thông báo trước hành động, quy trình phải có trạng thái chờ riêng. Sau khi điều kiện thông báo đạt, máy chủ vẫn kiểm tra lại hiệu lực yêu cầu, bằng chứng, phê duyệt và rủi ro trước khi tiêu thụ quyền thực thi. Một callback cũ không được làm sống lại đề xuất đã hết hạn.

Không thể thu hồi chắc chắn một thay đổi đã có tác dụng chỉ bằng cách phát hiện email gửi lỗi sau đó. Ví dụ, người dùng đã hoàn tất đổi yếu tố xác thực; lỗi email hậu xử lý không nên tự khôi phục yếu tố đã bị báo mất. Cần ghi nhận trạng thái thực tế và xử lý sự cố theo policy, thay vì thực hiện một phép rollback bảo mật tùy tiện.

Nếu tất cả kênh bắt buộc đều thất bại, dùng tuyến dự phòng được cấu hình và xác minh trước. Không gửi hồ sơ sang số điện thoại hoặc email mới do người gọi cung cấp để vượt lỗi kênh. Nếu không có tuyến hợp lệ, đưa quy trình về trạng thái chờ hoặc xử lý sự cố đúng với điều kiện của hành động.

### Callback từ nhà cung cấp

Webhook báo gửi, bounce hoặc thất bại phải được xác thực theo cơ chế của nhà cung cấp. Kiểm tra chữ ký trên đúng dữ liệu gốc, giới hạn thời gian và chống phát lại theo contract được sử dụng; liên kết callback với lần gửi đã biết.

Callback không được tự thay tài khoản đích, người nhận hoặc trạng thái phê duyệt. Một sự kiện `DELIVERED` chỉ cập nhật dữ liệu giao nhận trong phạm vi của nó. Nó không phải lệnh “cho phép khôi phục tài khoản”.

## 9. Ví dụ Java: dựng thông báo không mang quyền khôi phục

Ví dụ dưới minh họa một thông báo văn bản thuần. Các trường động gồm định danh có kiểu, thời gian và loại sự kiện do máy chủ xác định. Không đưa lý do tự do, tên hiển thị hoặc token vào nội dung.

```java
import java.net.URI;
import java.time.Instant;
import java.util.Objects;
import java.util.UUID;

enum RecoveryEventType {
    APPROVAL_REQUIRED,
    RECOVERY_APPLIED,
    SESSION_REVOCATION_INCOMPLETE
}

record RecoveryNoticeEvent(
        UUID eventId,
        UUID tenantId,
        UUID requestId,
        Instant occurredAt,
        RecoveryEventType type) {
}

record PlainTextNotice(String subject, String body) {
}

final class RecoveryNoticeComposer {
    // Địa chỉ minh họa; triển khai dùng origin đã được quản lý và xác minh.
    private static final URI CONSOLE_ORIGIN =
            URI.create("https://security.example.org");

    static PlainTextNotice compose(RecoveryNoticeEvent event) {
        Objects.requireNonNull(event);
        Objects.requireNonNull(event.eventId());
        Objects.requireNonNull(event.tenantId());
        Objects.requireNonNull(event.requestId());
        Objects.requireNonNull(event.occurredAt());
        Objects.requireNonNull(event.type());

        String title = switch (event.type()) {
            case APPROVAL_REQUIRED -> "Đề xuất đang chờ phê duyệt";
            case RECOVERY_APPLIED -> "Khôi phục đã được áp dụng";
            case SESSION_REVOCATION_INCOMPLETE ->
                    "Thu hồi phiên chưa hoàn tất";
        };

        URI requestPage = CONSOLE_ORIGIN.resolve(
                "/admin/recovery/requests/" + event.requestId());

        String body = """
                Sự kiện: %s
                Mã sự kiện: %s
                Mã hồ sơ: %s
                Thời điểm sự kiện (UTC): %s

                Mở console chính thức: %s
                Đăng nhập để xem phạm vi và trạng thái hiện tại.
                Thông báo không chứa token khôi phục.
                """.formatted(
                title,
                event.eventId(),
                event.requestId(),
                event.occurredAt(),
                requestPage);

        return new PlainTextNotice("[Recovery] " + title, body);
    }
}
```

Ví dụ dùng cú pháp Java hiện đại để minh họa dựng nội dung, không bao gồm gửi email hay quyết định phân quyền. Việc không truyền địa chỉ người nhận vào composer giúp tránh trộn thao tác dựng nội dung với quyết định ai được nhận dữ liệu.

Trong luồng thực tế, một thành phần khác phải phân giải người nhận từ `tenantId`, kiểm tra quyền hiện tại, áp dụng policy kênh, lưu tác vụ chống trùng và gọi adapter gửi. API của console phải xác minh rằng request thuộc đúng tenant và người đăng nhập được phép đọc nó. Không tin tenant do URL hoặc client khai báo nếu không đối chiếu với hồ sơ phía máy chủ.

Nếu chuyển sang HTML, cần template escape phù hợp; kiểu dữ liệu UUID trong ví dụ không có nghĩa mọi chuỗi khác đều an toàn để chèn trực tiếp vào HTML. Nếu thêm trường tự do sau này, phải xét lại cách đưa trường đó vào nội dung và giới hạn thông tin được gửi.

## 10. Chống lạm dụng thông báo và ngập cảnh báo

Kẻ tấn công có thể gửi hàng loạt yêu cầu khôi phục để làm phiền người dùng, khiến người trực bỏ qua cảnh báo hoặc che giấu một yêu cầu nguy hiểm trong nhiều thông báo bình thường. Đường gửi thông báo vì vậy cũng cần chống lạm dụng.

Các biện pháp có thể phối hợp gồm:

- Giới hạn tốc độ tiếp nhận yêu cầu theo nhiều chiều phù hợp: tài khoản, tenant, nguồn và đặc điểm rủi ro.
- Chống tạo nhiều tác vụ cho cùng một sự kiện nghiệp vụ.
- Gộp các sự kiện lặp có cùng ý nghĩa thành một hồ sơ hoặc bản tổng hợp có số lượng rõ ràng.
- Dành tài nguyên và tuyến xử lý riêng cho cảnh báo ưu tiên cao.
- Chuyển một đợt yêu cầu bất thường thành cảnh báo tổng hợp về hành vi lạm dụng.
- Theo dõi số sự kiện bị gộp, trì hoãn hoặc chặn để người vận hành vẫn thấy quy mô thật.

Không dùng một giới hạn chung khiến kẻ tấn công có thể tiêu hết hạn mức bằng sự kiện thấp rồi làm mất cảnh báo tài khoản đặc quyền. Cũng không gộp mọi thứ chỉ theo email người dùng nếu việc đó có thể trộn tenant hoặc trộn các loại hành động khác nhau.

Thông báo chuyển tới email hoặc chat có thể bị chuyển tiếp ngoài hệ thống. Nội dung tối giản giảm ảnh hưởng nhưng không thay thế kiểm soát thành viên và cấu hình kênh. Các kênh chứa chi tiết nhạy cảm cần được quản lý như một phần của bề mặt quản trị.

API tiếp nhận khôi phục không nên tiết lộ danh sách quản trị viên, lịch trực hoặc địa chỉ nhận thông báo. Phản hồi công khai cần tránh trở thành công cụ xác định tài khoản hoặc cấu trúc quản trị. Các thông tin điều phối đó chỉ hiển thị cho người có quyền thích hợp.

## 11. Nhật ký, giám sát và chuyển tuyến

Mỗi thông báo cần có quan hệ truy vết tới sự kiện nghiệp vụ nhưng không làm lộ bí mật. Có thể lưu:

```text
notification_id, event_id, request_id, tenant_id
purpose, template_version, routing_policy_version
recipient_reference, channel, attempt_number
created_at, attempted_at, provider_reference
delivery_state, error_category, next_attempt_at
acknowledged_by, acknowledged_at, escalation_reference
```

Chỉ ghi các trường xác nhận khi có hành động tương ứng hợp lệ. Không tự điền `acknowledged_by` bằng người nhận dự kiến chỉ vì nhà cung cấp trả về thành công.

Địa chỉ nhận cũng có thể là dữ liệu nhạy cảm. Tùy nhu cầu vận hành, dùng tham chiếu tới danh bạ hoặc giá trị che bớt trong log phổ thông; giới hạn quyền xem bản đầy đủ. Không lưu token truy cập adapter, toàn bộ request gửi nhà cung cấp hoặc bằng chứng danh tính vào log chỉ để dễ debug.

Các chỉ số vận hành hữu ích gồm tuổi của thông báo chưa gửi lâu nhất, độ trễ theo mức độ, tỷ lệ lỗi theo kênh, số người nhận không còn hợp lệ, tác vụ chưa được tiếp nhận và thời gian chuyển tuyến. Số email “sent” đơn thuần không mô tả liệu quy trình khôi phục có được theo dõi hay không.

Khi gửi thất bại sau giới hạn retry, giữ tác vụ trong khu vực xử lý lỗi có kiểm soát thay vì xóa im lặng. Một tác vụ được đưa ra gửi lại vẫn phải kiểm tra thời hạn, trạng thái hồ sơ và quyền người nhận. Không phát lại nguyên lô cũ mà bỏ các điều kiện đó.

Quy tắc chuyển tuyến cần nêu nhóm nhận tiếp theo, điều kiện kích hoạt và cách kết thúc trách nhiệm. Khi một người đã nhận xử lý, các người khác phải thấy trạng thái đó để tránh xử lý trùng; việc nhận xử lý không ngăn người có quyền khác thực hiện quy trình ứng cứu cần thiết.

Nếu cảnh báo lỗi gửi cũng được phát qua chính kênh đang hỏng, lớp giám sát có thể im lặng cùng lúc. Có thể dùng một kênh giám sát độc lập đã cấu hình trước, cùng dashboard truy cập được bởi người trực. Không để mọi cơ chế dự phòng cùng phụ thuộc vào một bí mật, một mailbox hoặc một quyền quản trị đơn lẻ.

## 12. Tình huống xuyên suốt: khôi phục MFA cho quản trị viên tenant

Quản trị viên An báo mất điện thoại chứa MFA và không thể dùng phương thức xác thực dự phòng. Yêu cầu đi vào luồng khôi phục thủ công vì tài khoản có quyền quản trị tenant.

Hệ thống tạo hồ sơ và thông báo tối giản cho nhóm Recovery Operations được phân giải từ tenant của An. Nhóm an ninh nhận một sự kiện có mức độ phù hợp do tài khoản đặc quyền. Không gửi token khôi phục cho các nhóm này và không xem email phản hồi của An là bằng chứng đủ để gỡ MFA.

Sau xác minh danh tính và đánh giá rủi ro, nhân viên tạo đề xuất có phiên bản cụ thể. Người phê duyệt độc lập nhận thông báo tác vụ. Một người nhấn link từ email, đăng nhập console và thấy bằng chứng cùng phạm vi hiện tại. Việc mở link chỉ ghi nhận truy cập, chưa tạo phiếu phê duyệt.

Trong lúc chờ người thứ hai, người lập hồ sơ sửa đề xuất để thêm thay đổi kênh khôi phục. Snapshot cũ bị thay thế theo policy và các phê duyệt cũ không được dùng tiếp. Email cũ vẫn dẫn tới hồ sơ nhưng console giải thích rằng đề xuất trước không còn hiệu lực.

Khi đề xuất cuối cùng đủ điều kiện, dịch vụ áp dụng hành động và ghi sự kiện cùng outbox. Nhóm an ninh nhận thông báo “khôi phục đã áp dụng”; chủ tài khoản nhận thông báo riêng qua kênh được phép. Việc thu hồi một nhóm phiên chưa hoàn tất tạo sự kiện riêng, không bị che bởi thông báo thành công của bước trước.

Giả sử nhà cung cấp email gặp timeout sau khi đã tiếp nhận một thông điệp. Retry có thể làm người trực nhận hai bản giống nhau. Cả hai bản có cùng mã sự kiện và dẫn tới cùng trạng thái hồ sơ; chúng không tạo thêm token, phê duyệt hay hành động khôi phục.

Nếu kênh của nhóm trực tiếp tục lỗi, tác vụ được chuyển qua tuyến dự phòng đã duyệt và xuất hiện trên dashboard vận hành. Một callback báo gửi muộn sau khi hồ sơ đóng chỉ cập nhật lịch sử giao nhận. Nó không mở lại hồ sơ hoặc thay đổi kết quả khôi phục.

## 13. Các nguyên tắc thiết kế cần giữ

Thông báo quản trị cần phục vụ một trách nhiệm cụ thể, với người nhận được phân quyền theo đúng tenant và loại sự kiện. Nội dung nên đủ để định hướng phản ứng, còn bí mật và bằng chứng chi tiết được giữ trong hệ thống chính thức.

Sự kiện phải phản ánh trạng thái đã xảy ra hoặc tác vụ thực sự đang chờ. Luồng gửi cần chịu được retry, bản sao và độ trễ mà không tạo lại quyền khôi phục. Những trạng thái như đã gửi, đã nhận trách nhiệm, đã phê duyệt và đã thực thi phải được ghi nhận riêng.

Khi thông báo là điều kiện của một hành động, policy cần xác định rõ mức giao nhận và phương án khi không đạt. Khi thông báo chỉ phục vụ hậu xử lý, lỗi gửi vẫn phải được theo dõi và chuyển tuyến mà không tự ý đảo ngược trạng thái bảo mật đã áp dụng.

Một cơ chế administrator notification có giá trị khi nó giúp người đúng thẩm quyền phát hiện và xử lý khôi phục bất thường, đồng thời không mở thêm đường lấy token, vượt quyền hoặc rò rỉ hồ sơ. Khả năng quan sát chỉ hoàn chỉnh khi gắn được sự kiện, thông báo, phản ứng của con người và kết quả thực thi vào cùng một chuỗi truy vết.
