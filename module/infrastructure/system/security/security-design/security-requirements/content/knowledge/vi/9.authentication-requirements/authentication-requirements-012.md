# Authentication event logging

## 1. Ghi log sự kiện xác thực để bảo vệ điều gì?

**Authentication event logging** là việc ghi nhận có cấu trúc các sự kiện liên quan đến xác thực: bắt đầu và kết thúc một lần đăng nhập, kiểm tra yếu tố bổ sung, đăng ký phương thức, khôi phục tài khoản, tạo hoặc thu hồi phiên và các lỗi ảnh hưởng đến quyết định xác thực.

Trong thiết kế yêu cầu bảo mật, câu “hệ thống phải ghi log đăng nhập” chưa đủ để triển khai hoặc nghiệm thu. Nhóm phát triển cần biết sự kiện nào phải có, ý nghĩa chính xác của từng sự kiện, dữ liệu nào được phép ghi, khi nào log phải xuất hiện và hệ thống phải xử lý ra sao khi không thể lưu bằng chứng.

Một yêu cầu có thể kiểm chứng sẽ cụ thể hơn:

> Mỗi lần đăng nhập được xử lý đến một kết quả cuối cùng tại dịch vụ xác thực phải có một sự kiện kết thúc, chứa định danh giao dịch, kết quả và mã nguyên nhân đã chuẩn hóa. Sự kiện không được chứa mật khẩu, mã dùng một lần hoặc token có thể dùng để truy cập. Khi thành phần thu thập log hoạt động bình thường, ít nhất 99% sự kiện phải có thể truy vấn trong 60 giây tính từ lúc phát sinh, đo theo cửa sổ một giờ trên tải nghiệm thu đã xác định.

Log giúp phát hiện tấn công, điều tra sự cố, đối chiếu thay đổi bảo mật và kiểm chứng hệ thống có thực hiện chính sách đã cam kết hay không. Log **không thay thế** việc kiểm tra mật khẩu, MFA, giới hạn thử hoặc thu hồi phiên. Nếu hệ thống vừa cho phép một lần đăng nhập sai chính sách vừa ghi nhận rất đầy đủ, yêu cầu ngăn chặn vẫn chưa đạt.

Bài học này tập trung vào cách chuyển mục tiêu quan sát hoạt động xác thực thành yêu cầu cụ thể, liên kết được với rủi ro, kiến trúc và kiểm thử trong vòng đời phát triển.

### 1.1. Phân biệt các loại thông tin quan sát

| Loại thông tin | Mục đích chính | Ví dụ |
| --- | --- | --- |
| Log sự kiện xác thực | Tái dựng quyết định và chuỗi hành vi liên quan đến danh tính. | Một giao dịch bị từ chối vì bằng chứng MFA hết hạn. |
| Log kiểm toán thay đổi bảo mật | Đối chiếu ai đã thay đổi trạng thái bảo mật, khi nào và kết quả ra sao. | Một quản trị viên đăng ký phương thức xác thực mới. |
| Log chẩn đoán | Hỗ trợ xử lý lỗi kỹ thuật. | Kết nối tới nhà cung cấp danh tính bị timeout. |
| Chỉ số tổng hợp | Theo dõi xu hướng, tải, tỷ lệ và ngưỡng cảnh báo. | Tỷ lệ đăng nhập thất bại trong năm phút. |
| Dấu vết phân tán | Theo dõi một yêu cầu đi qua các thành phần. | Thời gian qua gateway, dịch vụ xác thực và kho phiên. |

Các nguồn có thể liên kết bằng mã tương quan, nhưng không nên mặc định đưa toàn bộ nội dung yêu cầu vào mọi nguồn. Một dấu vết phân tán chứa header `Authorization` vẫn làm lộ bí mật dù log xác thực chính đã được lọc đúng.

## 2. Xác định phạm vi và rủi ro trước khi chọn trường log

Giả sử một cổng nghiệp vụ có khách hàng, nhân viên và quản trị viên. Hệ thống hỗ trợ mật khẩu, MFA, đăng nhập liên kết với nhà cung cấp danh tính và API gọi từ dịch vụ nội bộ. Các dịch vụ gửi sự kiện về một nền tảng thu thập tập trung.

MFA là xác thực đa yếu tố. Nhà cung cấp danh tính, thường gọi là IdP, thực hiện một phần hoặc toàn bộ việc kiểm tra danh tính. Dịch vụ nhận kết quả đăng nhập vẫn phải kiểm tra kết quả đó theo chính sách của mình.

Những câu hỏi cần chốt trước khi đặc tả log gồm:

- Những đường xác thực nào đang tồn tại: web, di động, API, tài khoản khẩn cấp, tác vụ tự động?
- Thành phần nào có đủ thẩm quyền phát sự kiện “xác thực thành công”?
- Sự kiện nào cần chứng minh đến từng giao dịch, sự kiện nào chỉ dùng đo xu hướng?
- Cần theo dõi một tài khoản, một nguồn truy cập hay một chuỗi khôi phục trong bao lâu?
- Dữ liệu nào là bí mật xác thực, dữ liệu cá nhân hoặc dữ liệu không đáng tin từ client?
- Ai có quyền tìm kiếm, xuất và thay đổi cấu hình lưu giữ log?
- Khi mất collector hoặc kho log, truy cập nào được tiếp tục và truy cập nào phải dừng?

### 2.1. Bản đồ rủi ro minh họa

| Mã | Kịch bản | Thuộc tính yêu cầu ở log |
| --- | --- | --- |
| R-L01 | Kẻ tấn công thử nhiều mật khẩu hoặc dùng thông tin bị rò rỉ. | Đếm đúng kết quả, liên kết tài khoản và nguồn theo chính sách. |
| R-L02 | Người dùng mất MFA bị chiếm tài khoản qua đường khôi phục. | Liên kết các bước khôi phục, thay phương thức và thu hồi phiên. |
| R-L03 | Mật khẩu, OTP hoặc token bị ghi vào log. | Giới hạn dữ liệu ngay tại nơi sinh và kiểm tra toàn bộ đường thu thập. |
| R-L04 | Client giả mạo thành công hoặc chèn nội dung làm sai log. | Nguồn phát được xác thực, dữ liệu được cấu trúc và đầu vào được giới hạn. |
| R-L05 | Sự kiện bị mất, bị xóa hoặc đến trễ trong thời gian tấn công. | Độ bền, kiểm soát truy cập, phát hiện khoảng trống và độ trễ đo được. |
| R-L06 | Luồng log bị làm ngập để gây mất bằng chứng hoặc làm chậm đăng nhập. | Ngân sách tài nguyên, chính sách quá tải và giám sát mất sự kiện. |
| R-L07 | Log được dùng ngoài mục đích điều tra hoặc bị khai thác để suy đoán tài khoản. | Hạn chế dữ liệu, phân quyền, thời hạn lưu và kiểm toán truy cập. |

Mỗi trường dữ liệu phải phục vụ một mục đích rõ ràng trong các rủi ro này. “Có thể sau này sẽ cần” không phải lý do đủ để ghi toàn bộ request body, header hoặc hồ sơ người dùng.

Các con số trong bài là **giả định minh họa của cổng nghiệp vụ này**, không phải ngưỡng chung áp dụng cho mọi tổ chức. Khi đưa vào đặc tả thật, nhóm phải chọn ngưỡng dựa trên mô hình đe dọa, tải, khả năng phản ứng và chính sách dữ liệu.

## 3. Danh mục sự kiện và ý nghĩa kết quả

### 3.1. Ghi theo vòng đời, không chỉ theo màn hình đăng nhập

| Nhóm | Sự kiện cần xem xét | Giá trị điều tra |
| --- | --- | --- |
| Đăng nhập | Yêu cầu được tiếp nhận, kết quả thành công hoặc thất bại, yêu cầu bị hạn chế. | Nhận biết thử mật khẩu, lỗi tích hợp hoặc thay đổi bất thường. |
| MFA và xác thực bổ sung | Thử thách được phát hành, kiểm tra thất bại, hoàn tất, hết hạn hoặc bị hủy. | Tách lỗi yếu tố bổ sung khỏi lỗi mật khẩu và phát hiện lạm dụng. |
| Phương thức xác thực | Đăng ký, kích hoạt, xóa, thay thế, tạo bộ mã dự phòng. | Xác định thay đổi giúp chiếm quyền kiểm soát lâu dài. |
| Khôi phục | Bắt đầu, xác minh bằng chứng, hoàn tất, hết hạn, bị từ chối. | Tái dựng đường đi qua cơ chế dự phòng. |
| Phiên | Tạo, hết hạn, đăng xuất, thu hồi một phiên hoặc tất cả phiên. | Đối chiếu khả năng truy cập sau thay đổi bảo mật. |
| Đăng nhập liên kết | Kết quả kiểm tra phản hồi, lỗi issuer hoặc audience, lỗi nhà cung cấp. | Nhận biết vi phạm ranh giới tin cậy và lỗi cấu hình. |
| Danh tính dịch vụ | Xác thực workload thành công hoặc thất bại, credential hết hạn hoặc bị thu hồi. | Theo dõi giả mạo dịch vụ và lỗi luân chuyển khóa. |
| Ngoại lệ vận hành | Sử dụng tài khoản khẩn cấp, lỗi lưu sự kiện, mất kết nối collector. | Phát hiện đường truy cập đặc biệt và khoảng trống quan sát. |

Workload là đơn vị phần mềm đang chạy, chẳng hạn một dịch vụ hoặc tác vụ nền. Với workload, không áp dụng máy móc các trường như trình duyệt hay MFA của con người; vẫn cần định danh dịch vụ, môi trường, phương thức và kết quả phù hợp.

Danh mục phải xác định sự kiện bắt buộc cho từng luồng. Không nhất thiết ghi từng lần tải trang đăng nhập như một sự kiện kiểm toán quan trọng. Tuy nhiên, không được bỏ qua API cũ hoặc đường hỗ trợ chỉ vì chúng không đi qua giao diện mới.

### 3.2. Thành công ở bước nào?

Xét chuỗi sau:

```text
Tiếp nhận giao dịch
    -> Mật khẩu đúng
    -> Cần MFA
    -> MFA hợp lệ
    -> Kiểm tra chính sách phiên
    -> Tạo phiên
    -> Kết thúc giao dịch đăng nhập: thành công
```

“Mật khẩu đúng” không đồng nghĩa “đăng nhập thành công”. Nếu MFA chưa hoàn tất, sự kiện phải thể hiện bước đang chờ hoặc kết quả kiểm tra yếu tố, không phát `authentication.completed` với `outcome=success`.

Cần tách **kết quả** và **nguyên nhân**:

- `success`: thao tác cụ thể của sự kiện đã hoàn tất theo chính sách.
- `failure`: thao tác bị từ chối, với mã nguyên nhân nội bộ phù hợp.
- `pending`: còn chờ bước khác, không phải kết quả cuối của toàn bộ đăng nhập.
- `error`: không hoàn tất do lỗi xử lý hoặc phụ thuộc; không được tính là xác thực thành công.

Sự kiện cuối có thể dùng nguyên nhân như `invalid_credentials`, `factor_expired`, `rate_limited`, `policy_rejected` hoặc `dependency_unavailable`. Từ điển giá trị phải được quản lý thống nhất, thay vì để mỗi dịch vụ tự đặt cách viết.

Mã nguyên nhân dành cho điều tra có thể chi tiết hơn phản hồi công khai, nhưng vẫn cần hạn chế quyền đọc. Không trả nguyên văn nguyên nhân nội bộ cho client nếu điều đó làm lộ sự tồn tại của tài khoản hoặc trạng thái bảo mật.

### 3.3. Số lượng sự kiện và giao dịch bị bỏ dở

Đặc tả cần phân biệt:

1. Một giao dịch đăng nhập, có thể gồm nhiều bước.
2. Một lần kiểm tra yếu tố, có thể thất bại rồi được thử lại.
3. Một bản ghi sự kiện, có thể được truyền lại nhiều lần.

Không đếm cả ba loại thành “số lần đăng nhập thất bại”. Cần quy định trường nào xác định giao dịch, trường nào xác định lần kiểm tra và sự kiện nào được dùng cho mỗi chỉ số.

Với luồng nhiều bước, nên có thời hạn giao dịch và cách đóng trạng thái bỏ dở. Ví dụ, giao dịch chờ MFA quá năm phút được kết thúc với nguyên nhân `interaction_expired` bởi thành phần quản lý giao dịch. Thành phần này phải phối hợp với đường hoàn tất để không sinh hai kết quả cuối mâu thuẫn. Các yêu cầu bị chặn trước dịch vụ xác thực có sự kiện tại gateway, không tự biến thành một lần kiểm tra mật khẩu đã diễn ra.

## 4. Lược đồ sự kiện: đủ liên kết, không mang bí mật

### 4.1. Các trường cốt lõi

| Trường | Ý nghĩa và yêu cầu |
| --- | --- |
| `schema_version` | Phiên bản hợp đồng dữ liệu; collector phải xử lý hoặc cách ly phiên bản không hỗ trợ theo chính sách. |
| `event_id` | Định danh duy nhất của sự kiện, giữ nguyên khi truyền lại; không có quyền xác thực. |
| `event_type` | Loại sự kiện trong danh mục được phê duyệt. |
| `occurred_at` | Thời điểm phát sinh tại nguồn, có múi giờ rõ ràng, chuẩn hóa UTC. |
| `observed_at` | Thời điểm collector nhận sự kiện, do collector bổ sung. |
| `service`, `environment` | Nguồn phát và môi trường; được đối chiếu với danh tính của producer. |
| `interaction_id` | Mã liên kết các bước trong một giao dịch; không phải token để tiếp tục đăng nhập. |
| `request_id` | Mã liên kết với yêu cầu kỹ thuật, được kiểm tra định dạng và độ dài. |
| `actor` | Chủ thể khởi tạo, khi đã xác định được từ nguồn tin cậy. |
| `subject` | Tài khoản hoặc credential chịu tác động; khác actor khi có thao tác thay mặt. |
| `outcome`, `reason_code` | Kết quả của sự kiện và nguyên nhân chuẩn hóa. |
| `auth_context` | Phương thức, bước và chính sách được áp dụng, không chứa bằng chứng bí mật. |
| `source` | Thông tin nguồn ở mức cần thiết, kèm mức tin cậy hoặc tình trạng không xác định. |

Không phải sự kiện nào cũng có đủ actor và subject. Trước khi xác thực, người gửi mới chỉ khai báo một danh tính; không được trình bày khai báo đó như danh tính đã được chứng minh. Khi hỗ trợ thay phương thức cho người dùng khác, actor là nhân viên hỗ trợ còn subject là tài khoản được hỗ trợ. Chỉ có một trường `user` thường làm mất sự phân biệt này.

### 4.2. Ví dụ sự kiện sau khi toàn bộ đăng nhập đã hoàn tất

```json
{
  "schema_version": "1.0",
  "event_id": "evt_7b1a9f20",
  "event_type": "authentication.completed",
  "occurred_at": "2026-11-27T03:15:24.120Z",
  "observed_at": "2026-11-27T03:15:24.480Z",
  "service": "identity-service",
  "environment": "production",
  "interaction_id": "int_93d45e61",
  "request_id": "req_f4308b21",
  "actor": {
    "kind": "account",
    "account_ref": "acct_0042",
    "identity_verified": true
  },
  "subject": {
    "kind": "account",
    "account_ref": "acct_0042"
  },
  "outcome": "success",
  "reason_code": "policy_satisfied",
  "auth_context": {
    "methods": ["password", "totp"],
    "policy_id": "employee-login-v3",
    "session_ref": "sref_830cb741"
  },
  "source": {
    "network_ref": "net_c4a283",
    "address_origin": "trusted_gateway",
    "client_type": "web"
  }
}
```

Các định danh trong ví dụ là dữ liệu giả để minh họa cấu trúc, không phải đề xuất về độ dài mã trong hệ thống thật. `totp` biểu thị phương thức mã dùng một lần theo thời gian; log không chứa mã đó hoặc bí mật dùng để sinh mã. `session_ref` là mã quan sát riêng, không phải cookie phiên, access token hoặc giá trị mà API chấp nhận để truy cập. `network_ref` là định danh nguồn được tạo theo chính sách dữ liệu, không mặc định cho biết địa chỉ IP đầy đủ.

### 4.3. Tài khoản chưa xác định và tương quan an toàn

Khi đăng nhập thất bại, hệ thống có thể chưa xác định được một account hợp lệ. Khi đó, để `account_ref` vắng mặt hoặc dùng trạng thái rõ ràng; không tạo ra một tài khoản có vẻ đã được xác minh.

Nếu cần nhận biết nhiều lần thử cùng một định danh được nhập, có thể thiết kế `login_hint_ref` bằng phép biến đổi có khóa, chẳng hạn HMAC, trên giá trị đã chuẩn hóa cùng phạm vi tenant và phiên bản khóa. Không dùng hàm băm công khai đơn giản trên email rồi mặc định rằng đã ẩn danh: miền giá trị dễ đoán có thể cho phép dò lại. Giá trị có khóa vẫn là dữ liệu liên kết được và phải được bảo vệ, không trở thành dữ liệu công khai.

Phải chốt cách chuẩn hóa, nơi giữ khóa, thời gian có thể liên kết và ảnh hưởng của luân chuyển khóa tới điều tra. Tài khoản ở hai tenant không nên bị liên kết ngoài ý muốn. Việc chuẩn hóa cũng phải thống nhất với quy tắc đăng nhập thực tế, tránh gộp hai định danh mà hệ thống coi là khác nhau.

## 5. Không biến log thành kho thông tin xác thực

### 5.1. Danh sách dữ liệu được phép và bị cấm

An toàn hơn là xây sự kiện từ danh sách trường được phép, thay vì ghi toàn bộ yêu cầu rồi cố che một vài khóa có tên quen thuộc. Việc lọc vẫn cần ở các lớp khác để phòng lỗi, nhưng không thay thế việc giới hạn dữ liệu ngay khi tạo sự kiện.

| Dữ liệu | Cách đặc tả |
| --- | --- |
| Mật khẩu, OTP, mã dự phòng | Cấm ghi giá trị ở cả đường thành công, thất bại và ngoại lệ. |
| Khóa riêng, bí mật TOTP, client secret | Cấm ghi vào mọi đích log, dấu vết, thông báo lỗi và tệp lỗi do ứng dụng tạo. |
| Cookie phiên, access token, refresh token | Cấm ghi nguyên giá trị hoặc phần có thể dùng lại để truy cập. |
| Token đặt lại mật khẩu, mã ủy quyền, token đăng ký phương thức | Cấm ghi, kể cả khi nằm trong URL hoặc header chuyển hướng. |
| Bộ kiểm chứng mật khẩu | Không đưa vào log; đây vẫn là dữ liệu nhạy cảm có thể bị dò ngoại tuyến. |
| Tên phương thức và mã chính sách | Cho phép theo tập giá trị đã định nghĩa; không kèm bí mật của phương thức. |
| Định danh tài khoản nội bộ | Cho phép khi có mục đích, quyền đọc và thời hạn lưu phù hợp. |
| Email, số điện thoại, địa chỉ IP | Chỉ ghi mức chi tiết cần thiết theo chính sách; ưu tiên mã tham chiếu khi đáp ứng mục đích. |
| User-Agent và header tùy ý | Không mặc định ghi nguyên văn; giới hạn, chuẩn hóa hoặc chuyển sang phân loại client. |

Mã hóa một kho log không làm việc ghi mật khẩu trở nên chấp nhận được. Người có quyền giải mã hoặc hệ thống phân tích vẫn có thể nhìn thấy bí mật. Tương tự, che token ở giao diện tìm kiếm không đủ nếu bản rõ còn nằm trong hàng đợi, tệp xuất hoặc kho lưu trữ.

### 5.2. Kiểm soát ở mọi điểm có thể sao chép dữ liệu

Yêu cầu phải bao phủ ứng dụng, reverse proxy, gateway, agent thu thập, hệ thống dấu vết, hàng đợi lỗi, collector, kho tìm kiếm và bản xuất phục vụ hỗ trợ.

Các lỗi hay gặp gồm:

- Proxy ghi cả query string của liên kết khôi phục.
- Thư viện HTTP ghi request hoặc response body khi bật chế độ debug.
- Một ngoại lệ đính kèm đối tượng request chứa mật khẩu.
- Công cụ giám sát thu header `Authorization` hoặc `Cookie` mặc định.
- Thông báo lỗi của nhà cung cấp danh tính chứa dữ liệu tùy ý rồi được ghi nguyên văn.
- Hàng đợi cách ly sự kiện sai lược đồ vẫn lưu toàn bộ payload chưa lọc.

Phải ghi rõ nơi áp dụng bộ lọc, cấu hình nào được phép thay đổi và cách phát hiện cấu hình debug không phù hợp ở môi trường sản xuất. Sự kiện không hợp lệ cần được cách ly theo cách vẫn bảo vệ dữ liệu, không tạo một kho bí mật thứ hai dưới tên “log lỗi”.

### 5.3. Chống chèn nội dung và giả nguồn

Dữ liệu từ client là đầu vào không đáng tin. Tên đăng nhập chứa ký tự xuống dòng không được biến thành hai sự kiện hoặc giả một dòng “đăng nhập thành công”. Cần dùng bộ tuần tự hóa có cấu trúc, không nối chuỗi thủ công; đồng thời giới hạn kích thước và tập giá trị của trường thích hợp.

Với địa chỉ nguồn, phải phân biệt IP của kết nối trực tiếp và địa chỉ được proxy chuyển tiếp. Chỉ tin các header chuyển tiếp từ proxy đã được cấu hình tin cậy. Client tự gửi `X-Forwarded-For` không chứng minh mình đến từ địa chỉ đó. Nếu không xác định được nguồn đáng tin, ghi trạng thái không xác định thay vì chế tạo một nguồn có vẻ chính xác.

Tương tự, collector không được chỉ tin trường `service` do payload tự khai báo. Nó cần xác thực danh tính bên gửi và kiểm tra bên đó có quyền phát loại sự kiện, môi trường và phạm vi tenant tương ứng hay không. Trình duyệt có thể gửi telemetry riêng, nhưng telemetry đó không có cùng thẩm quyền với quyết định từ dịch vụ xác thực.

## 6. Độ tin cậy của đường truyền và lưu sự kiện

### 6.1. Phân biệt phát sinh, chấp nhận bền vững và truy vấn được

Một sự kiện có thể đi qua nhiều trạng thái:

```text
Quyết định xác thực hoặc thay đổi bảo mật
    -> Tạo sự kiện đã lọc dữ liệu
    -> Ghi vào bộ đệm hoặc outbox bền vững
    -> Truyền tới collector đã xác thực
    -> Kiểm tra lược đồ và xử lý trùng
    -> Lưu kho
    -> Có thể truy vấn và áp dụng quy tắc phát hiện
```

Gọi hàm logger thành công không nhất thiết có nghĩa sự kiện đã bền vững. Collector nhận thành công cũng không nhất thiết có nghĩa sự kiện đã lập chỉ mục và có thể tìm kiếm. Một yêu cầu thời gian phải nêu rõ điểm bắt đầu và điểm kết thúc.

Ví dụ, yêu cầu “99% truy vấn được trong 60 giây” được đo từ `occurred_at` tới thời điểm sự kiện xuất hiện ở nguồn truy vấn phục vụ điều tra, trên cửa sổ một giờ khi các phụ thuộc hoạt động bình thường. Cần có yêu cầu riêng về lỗi phụ thuộc, không loại toàn bộ sự cố khỏi phép đo rồi coi như không có rủi ro mất bằng chứng.

### 6.2. Truyền lại, trùng và thứ tự

Đường truyền có thử lại thường có thể giao một sự kiện nhiều lần. Cần giữ nguyên `event_id` khi truyền lại và quy định nơi loại trùng, thời hạn giữ khóa loại trùng, cách xử lý sau thời hạn đó. Các quy tắc cảnh báo phải đếm sự kiện hoặc giao dịch duy nhất theo mục đích, tránh một lần thất bại bị truyền lại năm lần thành năm lần thử mật khẩu.

Không nên mặc định sự kiện đến collector đúng thứ tự phát sinh. Kết quả cuối có thể đến trước sự kiện trung gian do đường truyền khác nhau. Dùng `interaction_id`, thời điểm và số thứ tự trong phạm vi nguồn hoặc giao dịch nếu cần. Số thứ tự phải có quy tắc cho khởi động lại và nhiều producer; một số nguyên tăng cục bộ không tự tạo thứ tự toàn cục.

Yêu cầu “không mất và không trùng tuyệt đối” cần được thay bằng các thuộc tính có thể thực hiện và kiểm thử: ghi bền vững, giao lại có giới hạn, loại trùng theo khóa, đối soát, phát hiện khoảng trống và công bố giới hạn của cửa sổ phục hồi.

### 6.3. Đồng hồ và độ trễ

Cần đồng bộ đồng hồ nguồn, lưu thời gian UTC có độ chính xác đã quy định và theo dõi độ lệch. Không sửa đè `occurred_at` bằng thời gian nhận để che việc sự kiện đến trễ.

Trong tình huống minh họa, nguồn phát có mục tiêu lệch đồng hồ không quá hai giây. Khi vượt ngưỡng, sinh cảnh báo chất lượng dữ liệu và đánh dấu nguồn thời gian không đáng tin. Collector giữ cả thời gian phát sinh và thời gian quan sát để điều tra. Việc sắp xếp hoặc phát hiện cửa sổ tấn công cần nêu có chấp nhận sự kiện đến muộn hay không và trong bao lâu.

### 6.4. Đứt kết nối, quá tải và chính sách hành vi lỗi

Không có một lựa chọn chung “luôn tiếp tục” hoặc “luôn từ chối” phù hợp với mọi sự kiện. Chính sách phải được quyết định theo rủi ro và năng lực ghi bền vững cục bộ, thay vì để một ngoại lệ logger tự quyết định khả năng đăng nhập.

Ví dụ chính sách:

| Tình huống | Hành vi được đặc tả |
| --- | --- |
| Collector tạm ngừng, outbox vẫn ghi được | Tiếp tục các luồng đã được phê duyệt, giữ sự kiện bền vững và thử lại; cảnh báo độ sâu, tuổi bản ghi cũ nhất. |
| Thay đổi phương thức của quản trị viên nhưng không ghi được sự kiện bền vững | Không xác nhận thay đổi; giao dịch phải không để lại trạng thái bảo mật đã đổi mà thiếu bản ghi bắt buộc. |
| Tạo phiên quản trị nhưng không ghi được sự kiện bền vững trong hai giây | Không cấp phiên mới; trả lỗi phù hợp và phát tín hiệu lỗi qua kênh giám sát độc lập nếu kênh đó còn hoạt động. |
| Bộ đệm gần đầy | Cảnh báo trước khi cạn, áp dụng chính sách ưu tiên đã phê duyệt; không âm thầm bỏ sự kiện kiểm toán bắt buộc. |
| Lưu trữ đầy hoặc luồng lỗi kéo dài | Áp dụng quyết định cho từng nhóm truy cập và sự kiện đã ghi trong đặc tả; chỉ rõ điều kiện dừng hoặc hoạt động suy giảm. |

Outbox là nơi lưu sự kiện bền vững để gửi đi sau. Với thay đổi trạng thái có giao dịch dữ liệu phù hợp, có thể ghi sự kiện outbox cùng giao dịch với thay đổi để tránh trạng thái “đã đổi MFA nhưng chưa có bằng chứng”. Đây là lựa chọn kiến trúc cần chứng minh; chỉ gọi một hệ thống log bên ngoài trước hoặc sau cập nhật không tự bảo đảm hai việc luôn nhất quán.

Dung lượng phải dựa trên tốc độ sự kiện, kích thước, thời gian gián đoạn cần chịu và hệ số dự phòng. Ví dụ, 100 sự kiện mỗi giây trong hai giờ tạo 720.000 sự kiện; trung bình 2 KiB mỗi sự kiện đã cần khoảng 1,37 GiB cho payload, chưa tính metadata và dự phòng. Phải kiểm thử với tải thực tế và bảo vệ dữ liệu trong bộ đệm, không chỉ mua đủ dung lượng kho cuối.

Nếu dùng lấy mẫu hoặc tổng hợp cho lưu lượng rất lớn, phải nêu nhóm được áp dụng, dữ liệu nào mất, cách đếm số sự kiện bị bỏ và ảnh hưởng tới phát hiện. Không lấy mẫu tùy ý các thay đổi phương thức, khôi phục hoàn tất hoặc sử dụng tài khoản đặc quyền nếu yêu cầu cần bằng chứng từng lần.

## 7. Bảo vệ, phân quyền và vòng đời dữ liệu log

### 7.1. Phân quyền riêng với quyền quản trị ứng dụng

Người có quyền sửa tài khoản không mặc nhiên cần quyền sửa hoặc xóa bằng chứng về thao tác của mình. Cần tách quyền phát sự kiện, đọc log, xuất dữ liệu, quản lý chính sách và xóa dữ liệu theo vòng đời.

Một mô hình minh họa:

- Dịch vụ xác thực chỉ có quyền gửi loại sự kiện thuộc phạm vi được giao.
- Nhân viên hỗ trợ chỉ xem thông tin cần thiết cho xử lý yêu cầu, không xem bí mật hay toàn bộ nguồn truy cập.
- Nhóm điều tra được tìm kiếm dữ liệu chi tiết trong phạm vi được cấp, có ghi nhận việc truy cập và xuất dữ liệu.
- Nhóm vận hành kho quản lý hạ tầng theo quyền được phân tách; thao tác đặc biệt có cơ chế phê duyệt và bằng chứng.
- Công việc xóa theo thời hạn chạy bằng danh tính chuyên biệt, với quyền và nhật ký thực thi riêng.

Cần ngăn truy vấn chéo tenant ngoài quyền được cấp, bảo vệ truyền tải và dữ liệu lưu trữ, quản lý khóa cùng quyền giải mã. Không để bản xuất CSV hoặc tệp đính kèm điều tra trở thành đường bỏ qua phân quyền của kho chính.

### 7.2. Tính toàn vẹn và giới hạn của bằng chứng

Có thể dùng lưu trữ chỉ ghi thêm, khóa chống sửa/xóa theo thời hạn hoặc chữ ký để hỗ trợ phát hiện thay đổi, tùy mức rủi ro. Một checksum lưu cạnh cùng tệp và cùng quyền sửa không đủ bảo vệ trước người có thể sửa cả hai.

Ngay cả log đã ký cũng không tự chứng minh sự kiện có thật nếu nguồn phát đã bị chiếm quyền. Yêu cầu cần kết hợp bảo vệ producer, xác thực nguồn, hạn chế quyền, đối chiếu với nguồn độc lập và theo dõi mất tín hiệu. Nên mô tả chính xác “phát hiện sửa đổi sau khi nhận” thay vì khẳng định tuyệt đối rằng log không thể bị giả mạo.

### 7.3. Thời hạn lưu và xóa

Đặc tả cần nêu thời gian tìm kiếm trực tuyến, thời gian lưu trữ tổng, cách xóa hoặc hết hạn ở các bản sao và điều kiện tạm giữ phục vụ điều tra theo chính sách tổ chức. Không suy ra thời gian lưu từ dung lượng ổ đĩa còn trống.

Ví dụ giả định: log có thể truy vấn trực tuyến 30 ngày, lưu tổng cộng 180 ngày; tác vụ hết hạn chạy hằng ngày và hoàn tất xóa các bản thuộc diện xóa trong 24 giờ sau mốc hết hạn. Bản sao lưu, hàng đợi, bản xuất và dữ liệu lưu trữ phải có lịch tương ứng được xác định riêng. Không tuyên bố xóa hoàn tất nếu bản rõ vẫn còn ở một đích chưa được tính tới.

Khi có tạm giữ được phê duyệt, cần ghi phạm vi, lý do, người chịu trách nhiệm và ngày xem xét lại. Các giá trị 30 và 180 ngày chỉ là ví dụ thiết kế; thời hạn thật phải đến từ mục đích sử dụng và nghĩa vụ áp dụng cho hệ thống.

## 8. Từ sự kiện sang phát hiện có thể hành động

### 8.1. Đặc tả quy tắc, không chỉ yêu cầu “có cảnh báo”

Một quy tắc cần có tập sự kiện đầu vào, khóa nhóm, cửa sổ thời gian, cách xử lý trùng, ngưỡng, thời hạn phát cảnh báo và nhóm nhận xử lý. Với dữ liệu không đầy đủ hoặc đến muộn, cần quy định quy tắc còn đáng tin tới mức nào.

Ví dụ phát hiện thử đăng nhập tập trung vào một tài khoản:

```text
Nguồn: authentication.completed từ producer được tin cậy
Kết quả: failure, reason_code = invalid_credentials
Khóa nhóm: tenant + account_ref hoặc login_hint_ref theo chính sách
Đơn vị đếm: interaction_id duy nhất, sau khi loại trùng event_id
Cửa sổ: trượt 5 phút theo thời điểm phát sinh
Ngưỡng: ít nhất 20 giao dịch thất bại
Đầu ra: cảnh báo trong tối đa 2 phút khi dữ liệu đến đúng hạn
```

Không đưa `pending`, lỗi phụ thuộc và từng lần truyền lại vào số lần sai mật khẩu. Nếu một giao dịch có nhiều lần kiểm tra yếu tố, quy tắc cần dùng đúng sự kiện của loại thử đang phát hiện, thay vì cộng tất cả kết quả vào cùng bộ đếm.

Một quy tắc bổ sung có thể xem xét nhiều tài khoản bị thử từ cùng nguồn trong một cửa sổ. Tuy nhiên, mạng dùng chung có thể chứa nhiều người hợp lệ, còn kẻ tấn công có thể dùng nhiều nguồn. IP hoặc `network_ref` là tín hiệu cần diễn giải theo bối cảnh, không phải bằng chứng chắc chắn về một con người hay một thiết bị.

### 8.2. Liên kết với thành công và thay đổi bảo mật

Chuỗi “nhiều lần thất bại, sau đó thành công, rồi thay phương thức MFA” có thể đáng điều tra hơn từng sự kiện riêng lẻ. Có thể liên kết bằng định danh tài khoản, giao dịch, thời gian và mã thay đổi bảo mật, nhưng phải tránh kết luận tự động rằng mọi chuỗi như vậy đều là chiếm đoạt tài khoản.

Cảnh báo cần chứa liên kết tới các sự kiện liên quan, phạm vi tài khoản hoặc tenant, lý do kích hoạt và hành động đầu tiên cho người xử lý. Không đưa bí mật xác thực vào thông báo gửi qua email, công cụ trực ca hoặc hệ thống quản lý sự cố.

Nếu cảnh báo được dùng để tự động khóa tài khoản, đó là một quyết định kiểm soát truy cập riêng. Phải có yêu cầu về độ tin cậy tín hiệu, phạm vi tác động, cách mở lại và chống việc kẻ tấn công cố ý tạo log để khóa nạn nhân.

### 8.3. Theo dõi sức khỏe chính đường log

Không có cảnh báo tấn công không chứng minh không có tấn công. Có thể producer đã ngừng phát hoặc collector đã ngừng nhận.

Các tín hiệu cần xem xét gồm số sự kiện đã phát, đã ghi bền vững, đã nhận, bị từ chối lược đồ, bị loại trùng, bị bỏ theo chính sách; tuổi sự kiện cũ nhất trong hàng đợi; độ trễ truy vấn; tỷ lệ nguồn lệch đồng hồ; và tình trạng thực thi quy tắc.

Nên có tín hiệu hoạt động định kỳ cho producer quan trọng và sự kiện kiểm tra tổng hợp được đánh dấu riêng để không làm sai chỉ số đăng nhập thật. Nếu chỉ dùng chính hàng đợi đang lỗi để gửi cảnh báo về hàng đợi đó, khả năng phát hiện sự cố sẽ bị giới hạn; cần một đường quan sát độc lập phù hợp mức rủi ro.

## 9. Bộ yêu cầu đo được và liên kết rủi ro

Các yêu cầu dưới đây minh họa cách biến thiết kế thành cam kết. Những tập giá trị, quyền và ngưỡng dẫn chiếu chính sách phải được chốt trong hồ sơ triển khai trước nghiệm thu.

| Mã | Yêu cầu | Rủi ro | Thành phần chịu trách nhiệm | Bằng chứng chính |
| --- | --- | --- | --- | --- |
| AUTHLOG-01 | Mỗi giao dịch xác thực đã kết thúc phải có kết quả cuối theo lược đồ được phê duyệt; không phát thành công trước khi hoàn tất các bước chính sách và cấp phiên tương ứng. | R-L01, R-L02, R-L04 | Dịch vụ xác thực và nhóm tài khoản. | Đối chiếu giao dịch với sự kiện; mật khẩu đúng nhưng MFA sai không sinh đăng nhập thành công. |
| AUTHLOG-02 | Không ghi bí mật xác thực vào bất kỳ đích thu thập nào trong phạm vi hệ thống, kể cả đường lỗi và cách ly. | R-L03 | Chủ các producer, proxy và nền tảng quan sát. | Thử dữ liệu đánh dấu ở mọi vị trí đầu vào và kiểm tra các đích đã đăng ký. |
| AUTHLOG-03 | Thay phương thức của quản trị viên phải có bản ghi bền vững cùng thay đổi trước khi báo thành công; không tạo phiên quản trị mới nếu không ghi bền vững được sự kiện bắt buộc trong hai giây. | R-L02, R-L05 | Nhóm danh tính và lưu trữ giao dịch. | Mô phỏng lỗi outbox, dừng tiến trình và đối chiếu trạng thái với sự kiện sau phục hồi. |
| AUTHLOG-04 | Khi phụ thuộc bình thường, ít nhất 99% sự kiện truy vấn được trong 60 giây, đo theo cửa sổ một giờ tại tải nghiệm thu 100 sự kiện mỗi giây. | R-L01, R-L05 | Nền tảng thu thập và kho tìm kiếm. | Đo thời gian từ nguồn tới khả năng truy vấn, không chỉ thời gian HTTP trả về. |
| AUTHLOG-05 | Truyền lại giữ nguyên `event_id`; cảnh báo và chỉ số không đếm trùng cùng sự kiện trong cửa sổ loại trùng bảy ngày. | R-L01, R-L05 | Producer, collector và nhóm phát hiện. | Gửi trùng, đảo thứ tự, khởi động lại và phát lại trong cửa sổ đã định. |
| AUTHLOG-06 | Quy tắc ít nhất 20 giao dịch sai thông tin xác thực trong năm phút phải tạo cảnh báo trong hai phút khi dữ liệu đến đúng hạn; sự kiện đến muộn có chính sách xử lý riêng. | R-L01 | Nhóm phát hiện và trực vận hành. | Phát chuỗi kiểm thử có trùng và dữ liệu gây nhiễu; kiểm tra nội dung cùng thời gian cảnh báo. |
| AUTHLOG-07 | Nguồn có độ lệch đồng hồ quá hai giây phải được đánh dấu chất lượng thời gian và cảnh báo trong năm phút kể từ khi phát hiện. | R-L05 | Nhóm hạ tầng thời gian và collector. | Mô phỏng lệch đồng hồ; giữ đúng cả thời điểm gốc lẫn thời điểm nhận. |
| AUTHLOG-08 | Quyền đọc, xuất, sửa cấu hình và xóa log phải tách theo vai trò; truy vấn hoặc xuất dữ liệu ngoài tenant được cấp phải bị từ chối. | R-L04, R-L07 | Nhóm nền tảng và quản trị truy cập. | Kiểm thử quyền phủ định, truy cập chéo tenant và bằng chứng kiểm toán thao tác quản trị. |
| AUTHLOG-09 | Thời hạn trực tuyến 30 ngày, tổng 180 ngày và việc xóa trong 24 giờ sau hết hạn phải được thực hiện cho các đích tương ứng; tạm giữ có quyết định riêng. | R-L07 | Chủ dữ liệu và nhóm lưu trữ. | Dữ liệu kiểm thử hết hạn, kết quả tác vụ xóa và đối chiếu bản sao theo lịch đã công bố. |
| AUTHLOG-10 | Collector chỉ chấp nhận nguồn phát được xác thực và đúng phạm vi sự kiện; trường nguồn từ payload không được tự quyết định thẩm quyền. | R-L04 | Nhóm nền tảng thu thập. | Producer giả, producer thật nhưng sai môi trường và sự kiện sai phạm vi đều bị từ chối. |

AUTHLOG-04 không tự bảo đảm AUTHLOG-06: có thể log đã truy vấn được nhưng bộ máy quy tắc không chạy. Tương tự, có đủ trường lược đồ không chứng minh nội dung không chứa bí mật. Mỗi yêu cầu phải có bằng chứng phù hợp với thuộc tính mà nó cam kết.

## 10. Ví dụ đặc tả đầy đủ: không ghi bí mật xác thực

### AUTHLOG-02 — Giới hạn dữ liệu ở toàn bộ đường thu thập

**Mục tiêu:** giảm rủi ro người đọc log, công cụ hỗ trợ hoặc dịch vụ phân tích lấy được khả năng đăng nhập của người dùng.

**Phạm vi:** luồng mật khẩu, MFA, đăng nhập liên kết, khôi phục và quản lý phương thức; gồm ứng dụng, gateway, proxy, agent, collector, hàng đợi, kho truy vấn, dấu vết và bản xuất do hệ thống quản lý.

**Dữ liệu cấm:** mật khẩu, OTP, mã dự phòng, khóa riêng, bí mật TOTP, client secret, cookie phiên, access token, refresh token, mã ủy quyền và token khôi phục hoặc đăng ký có thể sử dụng. Bộ kiểm chứng mật khẩu cũng không được đưa vào log.

**Hành vi bắt buộc:**

1. Producer xây sự kiện từ danh sách trường được phép; không đính kèm request, response hoặc đối tượng credential nguyên vẹn.
2. Những đường log truy cập và dấu vết phải loại bỏ header, query parameter và trường body mang dữ liệu cấm trước khi ghi hoặc truyền tới bên thu thập.
3. Ngoại lệ, lỗi xác minh token và lỗi phản hồi IdP chỉ dùng mã nguyên nhân đã chuẩn hóa cùng thông tin chẩn đoán được phép. Không dùng thông báo lỗi tùy ý như payload kiểm toán.
4. Collector từ chối hoặc xử lý an toàn sự kiện không đúng lược đồ; đường từ chối và hàng đợi cách ly phải tuân thủ cùng chính sách dữ liệu.
5. Khi cần tương quan phiên, producer dùng mã quan sát riêng không thể dùng để xác thực. Khi cần liên kết định danh được khai báo, áp dụng chính sách mã tham chiếu đã phê duyệt.
6. Quyền bật log chẩn đoán và sửa bộ lọc phải được kiểm soát, có bằng chứng thay đổi; chế độ chẩn đoán không được vô hiệu hóa danh sách dữ liệu cấm.

**Tiêu chí chấp nhận:**

| Ca | Thao tác | Kết quả mong đợi |
| --- | --- | --- |
| Mật khẩu sai | Gửi mật khẩu thử nghiệm có chuỗi đánh dấu duy nhất. | Có sự kiện thất bại, không có giá trị mật khẩu trong các đích kiểm tra. |
| MFA thất bại | Dùng mã thử nghiệm và gây lỗi khi xác minh. | Có phương thức và nguyên nhân, không có mã hoặc bí mật sinh mã. |
| Khôi phục | Gửi token thử trong URL, mở liên kết rồi hoàn tất. | Các đích truy cập, ứng dụng và dấu vết không giữ token. |
| Token không hợp lệ | Gửi token thử sai định dạng, sai chữ ký hoặc sai bên nhận. | Mã nguyên nhân đủ phân loại; token đầu vào không bị chép vào ngoại lệ. |
| Sai lược đồ | Gửi payload thử có trường chứa dữ liệu cấm tới đường tiếp nhận được kiểm soát. | Sự kiện bị xử lý theo chính sách; log lỗi và kho cách ly không giữ bản rõ. |
| Chẩn đoán | Kích hoạt chế độ chẩn đoán được cho phép trong môi trường kiểm thử tương đương. | Chính sách cấm dữ liệu vẫn có hiệu lực. |
| Bản xuất | Xuất tập sự kiện đã tạo qua chức năng hỗ trợ điều tra. | Bản xuất chỉ chứa dữ liệu được phép, không bổ sung request hoặc token gốc. |

**Cách thu bằng chứng:** dùng bí mật giả và dấu đánh dấu trong môi trường kiểm thử, không dùng credential thật. Kiểm tra cả biểu diễn thường gặp của dữ liệu ở từng đường, như URL encoding hoặc chuỗi trong ngoại lệ. Tìm dấu đánh dấu là một phép thử hữu ích nhưng không chứng minh tuyệt đối mọi bí mật đã được loại bỏ; cần đối chiếu cấu hình và cách tạo sự kiện để xác nhận không có đường sao chép dữ liệu nguyên vẹn.

**Trách nhiệm:** nhóm tài khoản sở hữu yêu cầu đầu cuối; mỗi nhóm vận hành producer hoặc đích lưu phải cung cấp cấu hình và bằng chứng cho phần mình. Danh sách đích thu thập phải được cập nhật khi thêm công cụ quan sát mới.

## 11. Kiểm thử các thuộc tính dễ bị bỏ sót

### 11.1. Kiểm thử ngữ nghĩa và liên kết

Cần chạy luồng mật khẩu đúng nhưng MFA sai, MFA hoàn tất nhưng tạo phiên lỗi, giao dịch hết hạn và callback bị phát lại. Đối chiếu trạng thái cuối trong hệ thống với sự kiện cuối. Phải phân biệt được “kiểm tra yếu tố thành công” và “toàn bộ đăng nhập thành công”.

Với thay đổi thay mặt, kiểm tra actor và subject khác nhau đúng như thực tế. Với đăng nhập chưa xác định tài khoản, kiểm tra sự kiện không khẳng định một danh tính đã được xác minh. Với đăng nhập liên kết, thông tin về phương thức chỉ được ghi là đã xác minh sau khi kết quả từ nhà cung cấp được kiểm tra theo chính sách; không tin một trường do client tự khai báo.

### 11.2. Kiểm thử đầu vào không đáng tin

Dùng tên đăng nhập dài, ký tự xuống dòng, dấu phân cách, dữ liệu Unicode và mã tương quan không hợp lệ. Kết quả cần là sự kiện có cấu trúc đúng, kích thước được giới hạn, không tạo bản ghi giả và không làm hỏng hệ thống tìm kiếm.

Thử tự đặt header chuyển tiếp từ client không qua proxy tin cậy. Nguồn trong log phải phản ánh chính sách tin cậy, không phản ánh tùy ý lời khai của client. Đồng thời kiểm tra producer giả hoặc producer hợp lệ gửi sai loại sự kiện.

### 11.3. Kiểm thử độ bền và phục hồi

Ngắt collector, gây lỗi ghi bộ đệm, làm đầy dung lượng, dừng tiến trình sau khi thay đổi bảo mật và trước khi gửi sự kiện. Khi phục hồi, đối chiếu trạng thái đã cam kết với sự kiện bền vững và kết quả truyền lại.

Thử gửi cùng `event_id` nhiều lần và đảo thứ tự sự kiện. Số giao dịch trong cảnh báo không được tăng theo số lần truyền lại. Thử cả ranh giới hết hạn cửa sổ loại trùng để hiểu giới hạn, thay vì giả định loại trùng được duy trì mãi mãi.

### 11.4. Kiểm thử quyền, thời gian và phát hiện

| Nhóm | Câu hỏi nghiệm thu |
| --- | --- |
| Quyền | Nhân viên hỗ trợ có thể đọc log tenant khác hoặc xóa bằng chứng về thao tác của mình không? |
| Lưu giữ | Bản hết hạn có biến mất khỏi đúng các đích trong thời gian đã cam kết không? |
| Độ trễ | Sau bao lâu sự kiện truy vấn được và sau bao lâu quy tắc tạo cảnh báo? |
| Đồng hồ | Khi nguồn lệch giờ, log có giữ thời gian gốc và đánh dấu chất lượng dữ liệu không? |
| Quy tắc | Ngưỡng 19 và 20 giao dịch có hành vi đúng; bản trùng có làm vượt ngưỡng giả không? |
| Tín hiệu nền | Khi producer ngừng phát, giám sát có phát hiện mất tín hiệu hay chỉ im lặng? |
| Quá tải | Luồng log có dùng cạn tài nguyên xác thực hoặc âm thầm mất sự kiện bắt buộc không? |

Kiểm thử cần dùng tải gồm cả thành công, thất bại, hạn chế tần suất và lỗi phụ thuộc. Chỉ đo một lần đăng nhập thành công trong điều kiện lý tưởng không đủ chứng minh các yêu cầu này.

## 12. Truy vết yêu cầu qua thiết kế và vận hành

Một chuỗi truy vết cho rủi ro lộ token có thể là:

```text
R-L03: Token khôi phục lọt vào log truy cập
    -> AUTHLOG-02: Cấm ghi bí mật ở mọi đích thu thập
    -> Thiết kế route khôi phục + lọc query tại proxy + sự kiện theo danh sách cho phép
    -> Kiểm thử token đánh dấu ở log proxy, ứng dụng, trace và kho xuất
    -> Theo dõi thay đổi cấu hình và kiểm tra khi bổ sung công cụ quan sát
```

Tương tự, rủi ro mất bằng chứng khi collector ngừng phải liên kết với yêu cầu độ bền, dung lượng bộ đệm, hành vi khi hết dung lượng, kiểm thử phục hồi và người nhận cảnh báo. Không chỉ liên kết với việc “đã cài agent”.

Khi phát triển tính năng mới, nhóm nên cập nhật danh mục sự kiện cùng tiêu chí chấp nhận ngay trong thiết kế. Khi thay lược đồ, phải kiểm tra consumer, quy tắc phát hiện và truy vấn điều tra còn hoạt động. Đổi tên `reason_code` có thể làm quy tắc ngừng phát hiện dù ứng dụng vẫn đăng nhập bình thường.

Mỗi yêu cầu nên có chủ sở hữu, phiên bản chính sách, bằng chứng nghiệm thu và thời điểm xem xét lại. Các thay đổi như thêm IdP, thêm SDK giám sát, đổi proxy hoặc mở đường khôi phục mới đều có thể tạo thêm điểm ghi bí mật hoặc khoảng trống sự kiện. Bằng chứng của phiên bản cũ không tự chứng minh thiết kế mới vẫn đáp ứng yêu cầu.

## 13. Bài tập áp dụng

Một đặc tả ban đầu viết: “Ghi lại mọi lần đăng nhập, lưu IP và thông báo lỗi để điều tra; gửi cảnh báo khi có nhiều lần sai.”

Hãy chuyển đặc tả này thành bộ yêu cầu có thể nghiệm thu:

1. Liệt kê sự kiện cho đăng nhập mật khẩu kèm MFA, mất MFA, đặt lại mật khẩu và thu hồi phiên.
2. Định nghĩa thế nào là một giao dịch và khi nào được phát kết quả cuối thành công.
3. Thiết kế lược đồ có actor, subject, kết quả, nguyên nhân, mã tương quan và nguồn thời gian.
4. Chọn dữ liệu nguồn cần thiết; nêu cách xử lý tài khoản chưa xác định và header IP không tin cậy.
5. Đặc tả dữ liệu cấm ghi, gồm cả proxy, dấu vết, ngoại lệ và hàng đợi lỗi.
6. Đặt ngưỡng độ trễ, quy tắc loại trùng, hành vi khi collector ngừng và chính sách khi bộ đệm đầy.
7. Viết ít nhất một ca thành công, một ca phủ định, một ca lỗi phụ thuộc và một ca kiểm tra quyền.

Ví dụ một phần đáp án: sự kiện kết thúc chỉ có `outcome=success` sau khi mật khẩu, MFA và chính sách tạo phiên đều đạt. Các bước dùng cùng `interaction_id`, từng sự kiện có `event_id` riêng và truyền lại giữ nguyên mã đó. Mật khẩu sai dùng mã nguyên nhân chuẩn hóa, không sao chép thông báo lỗi chứa đầu vào; cảnh báo đếm giao dịch duy nhất trong cửa sổ đã chốt. Khi không ghi bền vững được thay đổi MFA của quản trị viên, hệ thống không xác nhận thay đổi thành công.

Bộ yêu cầu hoàn chỉnh phải giúp nhóm triển khai biết cần phát và bảo vệ dữ liệu nào, nhóm kiểm thử biết điều gì phải quan sát được, còn nhóm vận hành biết khi nào bằng chứng thiếu hoặc không còn đáng tin. Đây là cơ sở để logging xác thực hỗ trợ trực tiếp mục tiêu bảo mật thay vì chỉ tạo thêm dữ liệu.
