# Thiết kế input validation policy

## 1. Mục tiêu bài thực hành

Một yêu cầu như “hệ thống phải kiểm tra đầu vào” chưa đủ để thiết kế, triển khai hoặc nghiệm thu. Nó không cho biết đầu vào nào cần kiểm tra, hệ thống chấp nhận những biểu diễn nào, giới hạn ở đâu và phản ứng ra sao khi kiểm tra thất bại.

Trong bài thực hành tổng hợp này, bạn chuyển mục tiêu an toàn thông tin và mô hình đe dọa thành **input validation policy**: chính sách xác định điều kiện để dữ liệu được tiếp nhận, cách diễn giải dữ liệu và hành vi bắt buộc khi dữ liệu không đạt yêu cầu. Chính sách phải truy vết được từ rủi ro đến yêu cầu, vị trí thực thi và bằng chứng kiểm thử.

Sau bài học, bạn cần thực hiện được các việc sau:

- Phân biệt kiểm tra cú pháp, ngữ nghĩa, quyền truy cập và tính hợp lệ của trạng thái nghiệp vụ.
- Đặc tả kiểu dữ liệu, miền giá trị, giới hạn tài nguyên, chuẩn hóa và xử lý trường thiếu hoặc không xác định.
- Viết yêu cầu bảo mật có mã định danh, điều kiện, hành vi và tiêu chí chấp nhận đo được.
- Chỉ ra kiểm tra nào nằm ở biên HTTP, bộ phân tích, tầng nghiệp vụ, cơ sở dữ liệu và luồng xử lý tệp.
- Thiết kế kiểm thử hợp lệ, không hợp lệ, biên, đối kháng và đồng thời; giải thích bằng chứng nào chứng minh yêu cầu đã được thực hiện.

Đầu ra của bài là một bộ đặc tả có thể giao cho người phát triển, người kiểm thử và người vận hành. Những ngưỡng trong tình huống dưới đây là quyết định của bài tập, không phải ngưỡng bảo mật áp dụng cho mọi hệ thống.

## 2. Tình huống: API tạo đề nghị thanh toán

Một nền tảng quản lý chi phí phục vụ nhiều doanh nghiệp, mỗi doanh nghiệp là một tenant. Nhân viên được cấp quyền có thể tạo đề nghị thanh toán cho nhà cung cấp thuộc doanh nghiệp của mình. Hồ sơ có thể gắn các tài liệu đã tải lên hệ thống.

Phạm vi chính sách là:

```http
POST /v1/payment-requests
Content-Type: application/json
Idempotency-Key: req-20261128-0001
```

Ví dụ một body hợp lệ:

```json
{
  "supplier_id": "bd94ce6b-1cd6-4f24-93aa-3d61a617edc7",
  "currency": "VND",
  "amount": "1250000",
  "invoice_number": "INV-2026/008",
  "due_date": "2026-12-15",
  "description": "Thanh toán thiết bị cho văn phòng",
  "attachment_ids": [
    "ea8e3f54-8272-4ef8-944a-99c9c1b0c783"
  ]
}
```

Để tái lập ví dụ và các ca kiểm thử về ngày, cố định đồng hồ máy chủ tại ngày nghiệp vụ `2026-11-28`, tính theo múi giờ `Asia/Ho_Chi_Minh`. Trong vận hành, ngày nghiệp vụ được lấy từ đồng hồ máy chủ, không nhận từ client.

### 2.1. Những quyết định nghiệp vụ đã được chốt

- Người gọi phải được xác thực và có quyền `payment_request:create` trong tenant hiện tại.
- `tenant_id` và `requested_by` được lấy từ ngữ cảnh xác thực đã được máy chủ xác minh.
- `status` ban đầu do máy chủ gán là `DRAFT`; API này không thực hiện chuyển tiền hoặc tự phê duyệt.
- Nhà cung cấp phải thuộc tenant hiện tại và đang hoạt động.
- Mỗi tổ hợp `(tenant_id, supplier_id, invoice_number)` chỉ tạo được một đề nghị trong phạm vi bài tập; hủy đề nghị không giải phóng tổ hợp này.
- Chỉ chấp nhận `VND` và `USD`. Bài tập dùng hạn mức `1..100000000` VND hoặc `0.01..10000.00` USD cho mỗi đề nghị.
- Ngày đến hạn nằm trong đoạn từ ngày nghiệp vụ hiện tại đến 90 ngày sau, tính cả hai đầu.
- Tệp đính kèm phải thuộc phạm vi người gọi được phép sử dụng, đã hoàn tất kiểm tra và gắn với nội dung bất biến.

Nếu một quyết định nghiệp vụ thay đổi, chính sách và các ca kiểm thử liên quan phải đổi cùng nhau. Không để người triển khai tự suy đoán hạn mức, múi giờ hoặc cách làm tròn.

### 2.2. Tài sản và ranh giới tin cậy

Tài sản cần bảo vệ gồm tính đúng đắn của đề nghị thanh toán, sự cách ly giữa các doanh nghiệp, dữ liệu hóa đơn, khả năng phục vụ và dấu vết điều tra.

Client, trường form ẩn, JavaScript ở trình duyệt, tên tệp và metadata do bên tải lên cung cấp đều là nguồn chưa tin cậy. Một dịch vụ nội bộ cũng phải kiểm tra dữ liệu nhận qua ranh giới của mình theo hợp đồng tương ứng; nhãn “nội bộ” không tự chứng minh đầu vào hợp lệ.

Kiểm tra ở trình duyệt giúp người dùng sửa lỗi sớm. Máy chủ chịu trách nhiệm quyết định cuối cùng. Cơ sở dữ liệu duy trì các bất biến cần được bảo vệ trước cạnh tranh giữa nhiều request.

## 3. Xác định rủi ro trước khi viết quy tắc

Bắt đầu từ hành vi có thể gây thiệt hại, sau đó xác định quy tắc có thể ngăn chặn hoặc giới hạn hành vi đó.

| Mã rủi ro | Tình huống đe dọa hoặc sai sót | Hậu quả cần ngăn chặn |
| --- | --- | --- |
| R-01 | JSON rất lớn, lồng sâu hoặc có khóa trùng khiến các thành phần diễn giải khác nhau | Cạn tài nguyên hoặc kiểm tra một giá trị nhưng sử dụng giá trị khác |
| R-02 | Client gửi `tenant_id`, `requested_by`, `status` hoặc thuộc tính nội bộ | Gán dữ liệu sang tenant khác, giả người tạo hoặc bỏ qua luồng phê duyệt |
| R-03 | ID nhà cung cấp hoặc tệp có cấu trúc hợp lệ nhưng nằm ngoài quyền | Tham chiếu trái phép và lộ sự tồn tại của đối tượng |
| R-04 | Số tiền âm, dùng số thực, biểu diễn số mơ hồ hoặc vượt hạn mức | Sai lệch giá trị tài chính và vượt giới hạn nghiệp vụ |
| R-05 | Tệp giả loại, chưa được quét hoặc bị thay thế sau kiểm tra | Sử dụng nội dung nguy hiểm hoặc chưa được phê chuẩn |
| R-06 | Hai request cùng kiểm tra “chưa tồn tại hóa đơn” rồi cùng ghi | Tạo hồ sơ trùng và phát sinh tác vụ lặp |
| R-07 | Dữ liệu đầu vào được ghép vào truy vấn, HTML hoặc log | Injection, thực thi nội dung tại trình duyệt hoặc giả mạo log |
| R-08 | Thông báo lỗi hoặc log chứa nguyên payload, token hay dữ liệu hóa đơn | Rò rỉ thông tin và mở rộng phạm vi tiếp cận dữ liệu nhạy cảm |
| R-09 | Các tầng dùng cách chuẩn hóa hoặc schema khác nhau | Kiểm tra không nhất quán và lỗi tương thích khó phát hiện |
| R-10 | Request sai bị lặp liên tục hoặc kích hoạt xử lý tệp đắt tiền | Cạn ngân sách xử lý dù từng request vẫn dưới giới hạn kích thước |

Cần phân biệt rõ các loại quyết định:

| Loại kiểm tra | Câu hỏi cần trả lời | Ví dụ |
| --- | --- | --- |
| Cú pháp và cấu trúc | Có đọc được và đúng hình dạng không? | Body là JSON object, không có khóa trùng |
| Miền giá trị | Giá trị có đúng tập được chấp nhận không? | `currency` chỉ là `VND` hoặc `USD` |
| Ngữ nghĩa liên trường | Các trường có hợp lý khi kết hợp không? | VND không có phần thập phân; ngày đến hạn không ở quá khứ |
| Phân quyền | Người gọi có quyền thực hiện và tham chiếu không? | Có quyền tạo và sử dụng tệp được chỉ định |
| Trạng thái và bất biến | Điều kiện có còn đúng khi commit không? | Nhà cung cấp còn hoạt động; khóa duy nhất hóa đơn chưa bị chiếm |

Input validation hỗ trợ các lớp sau nhưng không thay thế chúng. Một UUID hợp lệ không chứng minh quyền truy cập; một chuỗi văn bản hợp lệ không bảo đảm an toàn khi ghép vào HTML hoặc câu SQL.

## 4. Hợp đồng tại biên HTTP và bộ phân tích

Chính sách `IVP-PAYMENT-1.0` áp dụng các quy tắc sau cho endpoint trong bài tập.

| Thành phần | Quy tắc bắt buộc | Kết quả khi vi phạm |
| --- | --- | --- |
| Phương thức | Chỉ nhận `POST` tại endpoint này | `405` |
| Kiểu nội dung | Nhận `application/json`; không có charset hoặc charset là UTF-8, so khớp nhãn không phân biệt hoa thường | `415` nếu kiểu hoặc charset không được hỗ trợ |
| Mã hóa nội dung HTTP | Chỉ nhận không có `Content-Encoding` hoặc giá trị `identity` | `415` cho nội dung nén trong phiên bản này |
| Dung lượng body | Tối đa 16384 byte body thực nhận, tính cả khoảng trắng JSON, không tính header | `413` khi vượt giới hạn |
| Mã hóa ký tự | UTF-8 hợp lệ; không chấp nhận Unicode lỗi hoặc surrogate không ghép cặp sau giải mã JSON | `400` |
| Cú pháp | Đúng một tài liệu JSON hoàn chỉnh, không có dữ liệu thừa phía sau | `400` |
| Root | Root phải là object, không phải array, chuỗi, số hoặc `null` | `422` nếu JSON hợp lệ nhưng sai kiểu root |
| Độ sâu | Tối đa 4 container; root tính là 1, object hoặc array con cộng 1 | `400` khi parser chạm giới hạn |
| Số thuộc tính | Mỗi object tối đa 20 tên thuộc tính | `400` khi parser chạm giới hạn |
| Khóa trùng | Từ chối tên khóa trùng nhau sau giải mã escape JSON, ở mọi object | `400` |
| Thuộc tính lạ | Root chỉ có bảy thuộc tính trong ma trận ở mục 6 | `422`; không âm thầm bỏ qua |
| Header idempotency | Đúng một `Idempotency-Key`, dài 8–64 ký tự ASCII thuộc `[A-Za-z0-9_-]`; so sánh phân biệt hoa thường | `400` nếu thiếu hoặc sai |

Giới hạn byte phải được thực thi khi đọc luồng, kể cả khi client không gửi hoặc gửi sai `Content-Length`. Dừng đọc khi vượt ngưỡng; không đợi cấp phát toàn bộ body rồi mới kiểm tra. Proxy, máy chủ HTTP và ứng dụng phải có cấu hình nhất quán với giới hạn này.

Giới hạn độ sâu và số khóa bảo vệ tài nguyên ngay tại parser, trước khi dựng toàn bộ cây dữ liệu. Chỉ kiểm tra sau khi parse thành object trong bộ nhớ không đáp ứng mục đích này.

Ví dụ sau phải bị từ chối, dù framework có thể mặc định giữ giá trị đầu hoặc cuối:

```json
{
  "amount": "1000",
  "amount": "999999999"
}
```

Tương tự, `"amount"` và `"\u0061mount"` được tính là cùng một tên khóa. Chính sách không cho phép proxy, bộ kiểm tra schema và bộ ánh xạ đối tượng lựa chọn các giá trị khác nhau.

## 5. Quy tắc chuẩn hóa và thứ tự diễn giải

Chuẩn hóa là quyết định có thể thay đổi ý nghĩa dữ liệu, vì vậy phải đặc tả theo từng trường. Không dùng một hàm “làm sạch” chung cho toàn bộ payload.

1. Áp dụng giới hạn tài nguyên và giải mã HTTP/UTF-8/JSON đúng một lần ở lớp tương ứng.
2. Xác minh kiểu JSON và cấu trúc trước khi biến đổi giá trị.
3. Áp dụng đúng phép chuẩn hóa được cho phép cho từng trường.
4. Kiểm tra điều kiện của biểu diễn đã chuẩn hóa; chuyển đổi sang kiểu miền đã chọn.
5. Dùng chính giá trị và kiểu miền đã được kiểm tra để xử lý và lưu trữ.

Các quy tắc cụ thể:

- `supplier_id` và từng `attachment_id` phải là UUID dạng chuẩn 36 ký tự viết thường, có dấu gạch ngang đúng vị trí. Không trim, sửa ID sai hoặc nhận dạng rút gọn mà một thư viện parser có thể hỗ trợ.
- `currency` phải khớp chính xác `VND` hoặc `USD`. Không tự chuyển chữ thường thành chữ hoa.
- `amount` phải là JSON string theo ngữ pháp ở mục 6. Không trim, nhận dấu phân cách hàng nghìn, dấu cộng hoặc số mũ.
- `invoice_number` dùng ASCII theo quy định; không tự viết hoa, bỏ dấu cách hoặc thay dấu phân cách vì có thể làm thay đổi khóa chống trùng.
- `due_date` được parse nghiêm ngặt thành ngày lịch, không tự sửa một ngày không tồn tại thành ngày kế tiếp.
- `description` đổi CRLF hoặc CR thành LF, sau đó chuẩn hóa Unicode NFC. Đo độ dài trên kết quả này. Không trim; chuỗi toàn khoảng trắng vẫn là văn bản hợp lệ trong tình huống này.
- Không URL-decode lại các chuỗi lấy từ JSON. Trường chứa URL hoặc dữ liệu mã hóa nếu được bổ sung sau này cần hợp đồng riêng.

Ví dụ, `amount = " 1000 "` bị từ chối thay vì được sửa thành `"1000"`. Với mô tả tiếng Việt, các biểu diễn Unicode tương đương được đưa về NFC để áp dụng giới hạn và lưu trữ nhất quán.

Không áp dụng quy tắc NFC của `description` cho mật khẩu, token, chữ ký hoặc định danh không có hợp đồng tương tự. Việc chuẩn hóa tùy tiện có thể phá vỡ cách xác minh những giá trị đó.

## 6. Ma trận validation cho từng trường

Năm trường `supplier_id`, `currency`, `amount`, `invoice_number`, `due_date` là bắt buộc. `description` và `attachment_ids` là tùy chọn. Với mọi trường được phép, **gửi tường minh `null` đều bị từ chối**; thiếu và null không đồng nghĩa.

| Trường | Kiểu và quy tắc | Thiếu, rỗng và mặc định |
| --- | --- | --- |
| `supplier_id` | String UUID chuẩn viết thường; tham chiếu nhà cung cấp hoạt động trong tenant và thuộc quyền sử dụng | Thiếu, `null`, rỗng: lỗi |
| `currency` | String, một trong `VND`, `USD` | Thiếu, `null`, rỗng: lỗi |
| `amount` | String tối đa 12 ký tự, khớp toàn bộ mẫu bên dưới và thỏa quy tắc theo đồng tiền | Thiếu, `null`, rỗng: lỗi; không có mặc định |
| `invoice_number` | String ASCII 1–40 ký tự, khớp toàn bộ mẫu bên dưới | Thiếu, `null`, rỗng: lỗi |
| `due_date` | String đúng 10 ký tự `YYYY-MM-DD`; ngày lịch tồn tại, từ ngày nghiệp vụ đến ngày nghiệp vụ + 90 ngày | Thiếu, `null`, rỗng: lỗi |
| `description` | String; sau chuẩn hóa tối đa 1000 Unicode code point và 4096 byte UTF-8; loại ký tự điều khiển C0/C1, trừ LF và TAB | Thiếu: `""`; gửi `""`: hợp lệ; `null`: lỗi |
| `attachment_ids` | Array tối đa 5 string UUID chuẩn, không trùng; từng tệp và tổng dung lượng đạt mục 7 | Thiếu: `[]`; gửi `[]`: hợp lệ; `null`: lỗi |

Hai mẫu dùng chức năng **khớp toàn bộ chuỗi**, không tìm một đoạn con:

```text
amount:         (?:0|[1-9][0-9]{0,8})(?:\.[0-9]{1,2})?
invoice_number: [A-Z0-9][A-Z0-9/-]{0,39}
```

Chữ số trong hai mẫu là ASCII `0..9`; không thay bằng lớp ký tự có thể nhận thêm chữ số Unicode. Nếu lưu mẫu vào JSON, YAML hoặc mã nguồn, áp dụng quy tắc escape của đúng định dạng đó.

### 6.1. Số tiền và đồng tiền

Sau kiểm tra cú pháp, parse bằng kiểu thập phân chính xác, chẳng hạn `BigDecimal` trong Java. Không đi qua `float` hoặc `double`, không làm tròn giá trị sai để biến nó thành giá trị hợp lệ.

| Đồng tiền | Biểu diễn đầu vào | Miền giá trị | Biểu diễn chuẩn khi lưu/xuất trong bài tập |
| --- | --- | --- | --- |
| VND | Chỉ phần nguyên, không có dấu chấm | `1 <= amount <= 100000000` | Chuỗi số nguyên, ví dụ `"1250000"` |
| USD | Phần nguyên, hoặc phần thập phân dài 1–2 chữ số | `0.01 <= amount <= 10000.00` | Hai chữ số thập phân, ví dụ `"12.00"` |

Ví dụ:

- `VND / "1"` hợp lệ; `VND / "1.0"` bị từ chối theo chính sách biểu diễn đã chọn.
- `USD / "12.3"` hợp lệ, được lưu/xuất thành `"12.30"` mà không đổi giá trị.
- `USD / "0.001"` bị từ chối; không làm tròn thành `"0.00"` hoặc `"0.01"`.
- `"01"`, `"+1"`, `"1e3"`, `"1,000"` và JSON number `1000` bị từ chối.
- `VND / "100000001"` đúng ngữ pháp nhưng vượt hạn mức nên bị từ chối.

Đây là điều kiện đầu vào của bài tập. Hạn mức phê duyệt, hạn mức chi tiêu theo vai trò hoặc chống gian lận nếu có phải được đặc tả như điều kiện nghiệp vụ/phân quyền riêng.

### 6.2. Ngày và phép đo độ dài

`due_date` là ngày, không phải thời điểm. Không nhận timestamp như `2026-12-15T00:00:00Z` rồi tự cắt phần ngày. Các quyết định về ngày dùng cùng một ngày nghiệp vụ được chốt cho lần xử lý; không đọc đồng hồ rải rác khiến kết quả thay đổi sát nửa đêm.

Với fixture `2026-11-28`, hai biên hợp lệ là `2026-11-28` và `2027-02-26`. `2026-11-27` và `2027-02-27` nằm ngoài đoạn cho phép.

“1000 ký tự” của `description` nghĩa là 1000 Unicode code point sau chuẩn hóa, không phải 1000 byte, 1000 đơn vị UTF-16 hoặc 1000 ký tự mà mắt người cảm nhận. Một emoji ghép có thể chiếm nhiều code point. UI cần dùng cùng thuật toán đo với máy chủ và giải thích giới hạn phù hợp với người dùng.

## 7. Chính sách cho đối tượng tham chiếu và tệp

Kiểm tra ID gồm kiểm tra hình thức và kiểm tra đối tượng mà ID chỉ đến. Bước đầu thành công không cho phép bỏ qua bước sau.

### 7.1. Nhà cung cấp và cách ly tenant

- Truy vấn phải giới hạn theo tenant từ ngữ cảnh xác thực và quyền sử dụng của người gọi.
- Nhà cung cấp phải hoạt động tại điểm kiểm tra bất biến và ghi nhận đề nghị mới.
- Nhà cung cấp không tồn tại và nhà cung cấp ngoài phạm vi người gọi cùng trả `404 REFERENCE_NOT_FOUND` sau khi request đã qua kiểm tra hình thức.
- Không trả tên tenant, nhà cung cấp hoặc trạng thái thực của đối tượng mà người gọi không được phép thấy.

Thông báo lỗi thống nhất giảm lộ thông tin qua phản hồi. Nếu mô hình đe dọa bao gồm suy đoán qua thời gian xử lý hoặc lưu lượng, cần biện pháp và kiểm thử tương ứng; cùng status code chưa giải quyết toàn bộ các kênh đó.

### 7.2. Tệp đã tải lên

Endpoint chỉ nhận ID tệp, không nhận URL tùy ý hoặc đường dẫn filesystem. Dịch vụ không tải nội dung từ URL do client tự thêm vào payload.

Mỗi ID được chấp nhận phải thỏa tất cả điều kiện:

1. Thuộc tenant hiện tại và thuộc quyền sử dụng. Cùng tenant chưa đủ nếu tệp có chính sách chia sẻ riêng.
2. Trạng thái `READY`: đã hoàn tất kiểm tra, chưa bị cách ly hoặc thu hồi.
3. Loại tệp là PDF, JPEG hoặc PNG, xác định bằng nội dung và bộ phân tích phù hợp, không chỉ tên mở rộng hay `Content-Type` client gửi.
4. Từng tệp không vượt `5 * 1024 * 1024` byte. Tổng các tệp trong đề nghị không vượt `20 * 1024 * 1024` byte.
5. Nội dung gắn với ID và mã băm đã kiểm tra là bất biến; không thay nội dung dưới cùng ID sau khi chuyển `READY`.

Luồng tải lên cách ly tệp trước khi kiểm tra, giới hạn CPU/bộ nhớ/thời gian của công cụ xử lý và vận hành các lớp phát hiện nội dung nguy hiểm theo thiết kế. Quét mã độc là một lớp kiểm soát; kết quả quét không biến định dạng phức tạp thành nội dung hoàn toàn an toàn.

Tệp không tồn tại hoặc ngoài quyền trả `404 REFERENCE_NOT_FOUND`. Tệp thuộc quyền nhưng chưa `READY` trả `422 ATTACHMENT_NOT_READY`. Không đáp ứng kích thước/số lượng/loại trả lỗi miền giá trị tương ứng; không tự bỏ tệp sai để phần còn lại thành hợp lệ.

Tên tệp chỉ là nhãn hiển thị, không làm đường dẫn lưu trữ. Tầng phục vụ tệp cần phân quyền, cách ly và header tải/hiển thị phù hợp. Các yêu cầu kiến trúc này không thể thay bằng regex của `attachment_ids`.

## 8. Đặc tả yêu cầu bảo mật có thể nghiệm thu

Một yêu cầu tốt nêu được chủ thể thực hiện, đầu vào/điều kiện, hành vi bắt buộc, kết quả và phép kiểm chứng. Tránh các từ “hợp lý”, “đủ mạnh” hoặc “được làm sạch” nếu chưa có định nghĩa đo được.

### VAL-01 — Kiểm soát biểu diễn và tài nguyên tại biên

Máy chủ phải thực thi toàn bộ hợp đồng HTTP/parser ở mục 4 trước khi ánh xạ body vào đối tượng nghiệp vụ. Body vượt 16384 byte, JSON có khóa trùng hoặc vượt độ sâu không được gây ghi dữ liệu nghiệp vụ, liên kết tệp hay phát sự kiện `PaymentRequestCreated`.

**Nghiệm thu:** gửi payload ở đúng ngưỡng và vượt ngưỡng qua ingress thực tế; xác minh status code, việc dừng đọc và không có tác dụng nghiệp vụ. Kiểm tra header idempotency phải được thực hiện cả khi body hợp lệ.

### VAL-02 — Schema đóng và kiểu dữ liệu chính xác

Máy chủ phải từ chối thuộc tính ngoài bảy trường công khai, mọi giá trị `null` và mọi giá trị sai kiểu theo ma trận. Không tự ép number thành string hoặc string thành array. Trường tùy chọn bị thiếu chỉ nhận đúng mặc định đã đặc tả.

**Nghiệm thu:** kiểm tra từng trường với thiếu, `null`, rỗng, sai kiểu và thuộc tính lạ; xác minh `tenant_id` hoặc `status` không thể đi vào đối tượng lưu thông qua ánh xạ tự động.

### VAL-03 — Chuẩn hóa có kiểm soát và giá trị miền chính xác

Máy chủ phải chuẩn hóa theo từng trường ở mục 5, dùng kiểu thập phân chính xác cho số tiền và ngày lịch cho ngày đến hạn. Giá trị lưu phải là giá trị đã kiểm tra. Không kiểm tra bản chuẩn hóa rồi lưu bản thô vào cùng trường nghiệp vụ.

**Nghiệm thu:** kiểm thử chuẩn hóa Unicode, giới hạn sau chuẩn hóa, các biểu diễn số bị cấm, biên tiền tệ và biên ngày với đồng hồ cố định.

### VAL-04 — Danh tính và thuộc tính hệ thống từ nguồn tin cậy

Máy chủ phải lấy tenant, người tạo và quyền từ ngữ cảnh xác thực đã xác minh; phải tự gán trạng thái ban đầu. Client không có quyền cung cấp hoặc ghi đè ba thuộc tính này tại endpoint hiện tại.

**Nghiệm thu:** request chưa xác thực trả `401`, principal thiếu quyền tạo trả `403`, body cung cấp thuộc tính hệ thống trả `422`; không có đề nghị nào được tạo trong các trường hợp đó.

### VAL-05 — Kiểm tra quyền trên mọi đối tượng tham chiếu

Mọi nhà cung cấp và tệp phải được kiểm tra cả phạm vi tenant lẫn quyền sử dụng. API trả thông báo tham chiếu công khai thống nhất cho đối tượng không tồn tại và đối tượng ngoài quyền.

**Nghiệm thu:** dùng ID đúng hình thức của tenant khác và tệp cùng tenant nhưng không được chia sẻ; đối chiếu status code, error code, cấu trúc phản hồi và việc không tạo liên kết.

### VAL-06 — Tệp đủ điều kiện và nội dung bất biến

Máy chủ chỉ gắn tệp đáp ứng toàn bộ mục 7.2; một tệp không đạt làm thất bại cả yêu cầu tạo. Điều kiện `READY` và quyền sử dụng phải còn đúng tại điểm cam kết liên kết theo cơ chế nhất quán đã chọn.

**Nghiệm thu:** kiểm tra tệp ở biên 5 MiB, tổng ở biên 20 MiB, tệp bị cách ly và thay đổi trạng thái khi đang xử lý. Chứng minh không thể ghi đè nội dung sau `READY` bằng cùng ID.

### VAL-07 — Chống cạnh tranh và lặp yêu cầu

Hệ thống phải duy trì ràng buộc duy nhất hóa đơn và ngữ nghĩa idempotency ở mục 10 dưới tải đồng thời. Lỗi kiểm tra hoặc xung đột không để lại hồ sơ dở dang hay sự kiện tạo hồ sơ có thể được tiêu thụ.

**Nghiệm thu:** gửi hai request đồng thời cùng hóa đơn, cùng key, cùng key khác nội dung và tình huống mất kết nối sau commit; đối chiếu số bản ghi và sự kiện logic.

### VAL-08 — Lỗi có cấu trúc, log tối thiểu

Phản hồi lỗi tuân thủ mục 11, không phản chiếu giá trị nhạy cảm, stack trace hoặc chi tiết truy vấn. Log validation chỉ dùng metadata được phép, giới hạn tối đa 10 lỗi trường trong một phản hồi/log tổng hợp cho một request.

**Nghiệm thu:** gửi token giả, dòng mới và dữ liệu hóa đơn trong payload; kiểm tra phản hồi/log không chứa nguyên payload, nội dung mô tả, token hoặc số hóa đơn.

### VAL-09 — Bảo vệ tại nơi sử dụng dữ liệu

Dữ liệu hợp lệ phải được truyền vào truy vấn qua tham số, vào giao diện qua mã hóa theo ngữ cảnh và vào log qua trường dữ liệu có cấu trúc. Không xem validation là quyền bỏ các lớp bảo vệ này.

**Nghiệm thu:** lưu mô tả chứa dấu nháy hoặc đoạn giống HTML như văn bản hợp lệ; xác minh truy vấn không đổi cấu trúc, giao diện hiển thị văn bản và log không tạo bản ghi giả.

### VAL-10 — Chính sách đồng nhất và có phiên bản

Schema, validator nghiệp vụ, hợp đồng lỗi, cấu hình ingress và fixture kiểm thử phải liên kết đến phiên bản `IVP-PAYMENT-1.0`. Mọi thay đổi hành vi chấp nhận/từ chối phải có người phê duyệt, phân tích tương thích và cập nhật kiểm thử.

**Nghiệm thu:** đối chiếu cấu hình triển khai với đặc tả và chạy cùng tập ca hợp đồng tại ranh giới API được phát hành. Chính sách máy chủ vẫn được thực thi khi bỏ qua UI.

## 9. Phân bổ yêu cầu vào kiến trúc

Không phải kiểm tra nào cũng nên dồn vào một biểu thức chính quy hoặc annotation trên DTO.

| Lớp | Trách nhiệm trong chính sách | Bằng chứng thiết kế |
| --- | --- | --- |
| Ingress / HTTP server | Giới hạn byte, kiểu/mã hóa nội dung, lưu lượng | Cấu hình và kiểm thử qua ingress thật |
| Parser JSON | UTF-8/Unicode, cú pháp, độ sâu, số khóa, khóa trùng | Cấu hình parser và payload raw |
| DTO / schema | Danh sách trường, kiểu, required, null, độ dài và array | Schema hoặc DTO whitelist; ca hợp đồng |
| Bộ chuẩn hóa và kiểu miền | Chuẩn hóa mô tả, số tiền chính xác, ngày lịch | Quy tắc trường và fixture đầu vào–giá trị lưu |
| Dịch vụ nghiệp vụ | Liên trường, quyền tạo, quyền tham chiếu, trạng thái đối tượng | Ma trận quyền và sơ đồ quyết định |
| Transaction / cơ sở dữ liệu | Duy nhất hóa đơn, ghi nguyên tử, điều phối đồng thời, idempotency | Unique constraint, cơ chế đồng thời, bằng chứng rollback |
| Kho tệp / worker xử lý tệp | Cách ly, kiểm tra nội dung, tính bất biến, ngân sách xử lý | Máy trạng thái tệp và quyền thay đổi nội dung |
| Hiển thị / log | Mã hóa đầu ra theo ngữ cảnh, log tối thiểu dữ liệu | Kiểm thử hiển thị và mẫu log |

Kiểm tra ở nhiều lớp có thể cùng tồn tại vì bảo vệ các ranh giới khác nhau. Tuy nhiên, quy tắc nghiệp vụ phải có một định nghĩa có thẩm quyền; không để UI nhận USD ba chữ số thập phân, máy chủ tự làm tròn còn báo cáo dùng số thực.

Luồng tham khảo, trong đó replay là việc trả kết quả của request đã commit:

```text
Nhận request
  -> giới hạn transport / content type / encoding
  -> xác thực và kiểm tra quyền tạo
  -> kiểm tra header idempotency, parse JSON có giới hạn
  -> schema, chuẩn hóa, kiểu miền và quy tắc biểu diễn cố định
  -> tra bản ghi idempotency đã commit:
       nếu có: so nội dung, kiểm tra quyền đọc hiện tại, trả replay
       nếu chưa có: tiếp tục yêu cầu mới
  -> kiểm tra nghiệp vụ biến động: ngày, hạn mức, quyền/trạng thái tham chiếu
  -> cơ chế nhất quán/transaction đã chọn:
       phân xử quyền sở hữu key và kiểm tra lại khi có cạnh tranh
       xác nhận bất biến còn đúng, duy trì unique constraint
       ghi đề nghị + liên kết tệp + bản ghi sự kiện cùng cam kết
  -> trả kết quả

Lỗi trước commit
  -> không có đề nghị, liên kết hoặc sự kiện tạo hồ sơ được cam kết
  -> có thể có log, metric hoặc bản ghi kiểm soát idempotency an toàn
```

Các lỗi transport có thể xuất hiện trước xác thực. Sau đó xử lý xác thực/quyền tạo, header idempotency, parser, schema, biểu diễn cố định, nhánh replay hoặc kiểm tra nghiệp vụ của yêu cầu mới và xung đột khi ghi. Khi kiểm thử một quy tắc, các phần còn lại của request cần hợp lệ để lỗi không bị lớp trước che khuất.

### 9.1. Ngân sách lưu lượng

Quyết định cho bài tập là token bucket theo cặp tenant–principal đã xác thực, sức chứa 10 token, nạp đều 1 token/giây, mỗi lần gọi endpoint tiêu thụ 1 token. Như vậy tốc độ duy trì là 60 request/phút và có burst tối đa 10 khi bucket đầy. Phần vượt trả `429`; tốc độ duy trì này không có nghĩa mọi cửa sổ 60 giây đều chứa tối đa 60 request.

Trước xác thực, ingress dùng bucket theo IP nguồn đã được xác định qua chuỗi proxy tin cậy: sức chứa 20, nạp 2 token/giây, mỗi request tiêu thụ 1. Không nhận tùy ý địa chỉ do client đưa vào header chuyển tiếp. Đây là cấu hình ví dụ phải được đánh giá lại khi nhiều người dùng dùng chung IP hoặc khi phân tán trên nhiều ingress.

Thiết kế triển khai phải bảo đảm ngân sách được phối hợp trên các instance hoặc công bố rõ cách phân chia để tổng ngân sách không tăng theo số replica. Rate limit không thay thế giới hạn byte, độ sâu hoặc ngân sách của worker xử lý tệp.

## 10. Bất biến giao dịch và idempotency

### 10.1. Kiểm tra trước ghi chưa giải quyết cạnh tranh

Hai request có thể cùng thấy “chưa có hóa đơn” nếu chỉ `SELECT` rồi `INSERT`. Chính sách yêu cầu ràng buộc duy nhất tại nơi phân xử ghi đồng thời trên `(tenant_id, supplier_id, invoice_number)`.

Vi phạm ràng buộc được ánh xạ thành `409 INVOICE_CONFLICT`, không lộ tên constraint hoặc câu SQL. Thay đổi nghiệp vụ thuộc lần tạo phải rollback nếu không thể commit.

Với trạng thái nhà cung cấp hoặc tệp, thiết kế phải chỉ ra cơ chế giữ điều kiện đúng tại điểm commit: khóa phù hợp, kiểm tra phiên bản kèm ghi có điều kiện nguyên tử hoặc bảo đảm tương đương. Nếu dữ liệu ở dịch vụ khác, một transaction cục bộ không tự bao phủ dịch vụ đó; cần giao thức phối hợp hoặc điều chỉnh ranh giới cam kết.

### 10.2. Quy tắc idempotency

- Phạm vi khóa là `(tenant_id, principal_id, endpoint, Idempotency-Key)`; không dùng khóa chung giữa các tenant.
- Khóa đang xử lý được giữ bằng cơ chế nguyên tử; không cho hai request cùng sở hữu một lần tạo.
- Sau thành công, lưu kết quả idempotency tối thiểu 24 giờ từ lúc commit.
- Dấu vân tay nội dung được tính trên dữ liệu miền đã chuẩn hóa, gồm giá trị mặc định. Thứ tự thuộc tính JSON không ảnh hưởng; thứ tự `attachment_ids` được giữ nguyên và có ảnh hưởng trong phiên bản này.
- Trong thời gian lưu, cùng key và cùng dữ liệu trả lại kết quả đã commit, không tạo thêm hồ sơ. Cùng key khác dữ liệu trả `409 IDEMPOTENCY_CONFLICT`.
- Trùng key đang xử lý trả `409 REQUEST_IN_PROGRESS`; client retry theo hợp đồng và giữ key cũ.
- Lỗi trước commit không được đánh dấu đã tạo thành công. Reservation phải có trạng thái thất bại hoặc lease hết hạn để phục hồi sau crash.

Trước khi trả kết quả cũ, vẫn xác thực và kiểm tra quyền tạo/đọc kết quả theo hợp đồng hiện tại. Nếu quyền đã bị thu hồi, trả lỗi quyền; biết khóa không cho phép đọc kết quả.

Retry đúng nội dung của lần tạo đã thành công không chạy lại những điều kiện nghiệp vụ có thể thay đổi theo thời gian như cửa sổ ngày hoặc trạng thái nhà cung cấp. Parser, schema và chuẩn hóa xác định dữ liệu miền trước; sau đó kiểm tra kết quả đã commit; chỉ yêu cầu mới tiếp tục kiểm tra các điều kiện biến động. Nếu phiên bản chính sách mới đổi cách chuẩn hóa, phải duy trì khả năng nhận diện kết quả cũ hoặc có kế hoạch chuyển đổi rõ ràng.

Sau thời gian lưu, khóa có thể được xem là mới. Ràng buộc duy nhất hóa đơn vẫn ngăn tạo lại cùng tổ hợp theo nghiệp vụ bài tập.

Nếu phát sự kiện bất đồng bộ, có thể dùng outbox cùng transaction với đề nghị. Worker có thể giao lại sự kiện; bên tiêu thụ xử lý lặp theo ID sự kiện. “Không tạo tác dụng nghiệp vụ lặp” không có nghĩa hạ tầng chỉ giao sự kiện đúng một lần.

## 11. Hợp đồng lỗi và logging

### 11.1. Phản hồi lỗi

Ví dụ lỗi schema/ngữ nghĩa:

```json
{
  "error": {
    "code": "VALIDATION_FAILED",
    "request_id": "req_7e429d41",
    "details": [
      {
        "field": "amount",
        "code": "AMOUNT_SCALE_NOT_ALLOWED",
        "message": "Số tiền không đúng số chữ số thập phân cho đồng tiền đã chọn."
      }
    ]
  }
}
```

Trả tối đa 10 lỗi trường, theo thứ tự trường trong ma trận rồi đến chỉ số phần tử array. Không phản chiếu giá trị sai vào `message`. Với thuộc tính lạ, dùng lỗi cấp body `UNKNOWN_FIELD`; không phản chiếu tên khóa tùy ý do client đặt vào log hoặc thông báo.

| Status | Tình huống | Mã công khai tiêu biểu |
| --- | --- | --- |
| `400` | Cú pháp/mã hóa JSON, khóa trùng, giới hạn parser, header idempotency sai | `MALFORMED_REQUEST` |
| `401` | Chưa xác thực hợp lệ | `AUTHENTICATION_REQUIRED` |
| `403` | Thiếu quyền tạo hoặc đọc kết quả replay | `ACCESS_DENIED` |
| `404` | Tham chiếu không tồn tại hoặc ngoài quyền | `REFERENCE_NOT_FOUND` |
| `405` | Phương thức không hỗ trợ | `METHOD_NOT_ALLOWED` |
| `409` | Trùng hóa đơn, key xung đột hoặc đang xử lý | `INVOICE_CONFLICT`, `IDEMPOTENCY_CONFLICT`, `REQUEST_IN_PROGRESS` |
| `413` | Body vượt 16384 byte | `PAYLOAD_TOO_LARGE` |
| `415` | Kiểu nội dung, charset hoặc content encoding không hỗ trợ | `UNSUPPORTED_REPRESENTATION` |
| `422` | Schema, miền giá trị, liên trường; trạng thái tệp/nhà cung cấp thuộc quyền nhưng không phù hợp | `VALIDATION_FAILED` |
| `429` | Vượt ngân sách lưu lượng | `RATE_LIMITED` |
| `503` | Không thể xác minh điều kiện do thành phần phụ thuộc lỗi | `DEPENDENCY_UNAVAILABLE` |

Không trả `422` khi cơ sở dữ liệu hoặc dịch vụ kiểm tra tệp mất kết nối. Đó là lỗi khả dụng, không phải bằng chứng đầu vào sai. Khi chưa xác minh được điều kiện bắt buộc, không tạo hồ sơ bằng nhánh bỏ qua kiểm tra; trả lỗi có thể retry và không ghi nhận thành công giả.

### 11.2. Logging và quan sát

Một sự kiện log validation có thể chỉ gồm:

```json
{
  "event": "input_validation_rejected",
  "request_id": "req_7e429d41",
  "route": "/v1/payment-requests",
  "policy_version": "IVP-PAYMENT-1.0",
  "error_code": "AMOUNT_SCALE_NOT_ALLOWED",
  "field": "amount",
  "http_status": 422
}
```

Không log toàn bộ body, token, nội dung mô tả, số hóa đơn hoặc idempotency key thô. Nếu cần liên kết tenant/principal để điều tra, dùng định danh nội bộ hoặc giá trị giả danh hóa theo thiết kế logging đã được phê duyệt, giới hạn quyền truy cập và thời gian lưu tương ứng.

Chỉ dùng route, field và error code từ danh sách cố định làm label metric; không dùng giá trị đầu vào khiến số chuỗi thời gian tăng không giới hạn. Chuỗi client điều khiển nếu thật sự cần ghi phải giới hạn độ dài và ghi như dữ liệu có cấu trúc.

Đặt cảnh báo khi tăng lỗi khóa trùng, request quá lớn, tham chiếu ngoài phạm vi hoặc lỗi phụ thuộc. Tỷ lệ `422` tăng sau phát hành cũng có thể là lỗi tương thích client; không mặc định mọi lỗi validation đều là tấn công.

## 12. Bộ ca kiểm thử nghiệm thu

Dùng fixture thống nhất: principal có quyền tạo trong tenant A; nhà cung cấp hoạt động thuộc A; nhà cung cấp thuộc B; tệp A đã `READY`; tệp A chưa `READY`; tệp A không được chia sẻ cho principal; và tệp thuộc B. Mỗi ca dùng key mới, trừ các ca cố ý kiểm tra replay/xung đột.

Các ngày dùng đồng hồ cố định ở mục 2. Mọi biến thể không được đề cập đều giữ đúng request hợp lệ mẫu. Với ca từ chối, kiểm tra cả phản hồi và số bản ghi nghiệp vụ/liên kết/sự kiện đã commit.

| Mã | Thay đổi hoặc điều kiện thử | Kỳ vọng chính | Yêu cầu |
| --- | --- | --- | --- |
| T-01 | Request mẫu, tham chiếu hợp lệ | `201`, tiền chính xác, trạng thái `DRAFT`, tenant/người tạo đúng ngữ cảnh | VAL-03, VAL-04 |
| T-02 | Bỏ `description`, bỏ `attachment_ids`, rồi gửi `null` cho từng trường | Thiếu dùng mặc định; `null` trả `422` | VAL-02 |
| T-03 | Gửi thêm `tenant_id`, `requested_by`, `status`, `callback_url` | Từng request trả `422`, không ghi đè thuộc tính nội bộ | VAL-02, VAL-04 |
| T-04 | `amount` là number hoặc `attachment_ids` là string | `422`, không ép kiểu | VAL-02 |
| T-05 | JSON hoàn chỉnh 16384 byte và 16385 byte, dùng khoảng trắng để đạt kích thước | Đúng ngưỡng qua kiểm tra byte; vượt ngưỡng `413` | VAL-01 |
| T-06 | Luồng không khai báo độ dài hoặc độ dài không phản ánh số byte thực nhận | Không nhận quá giới hạn; chặn request bất thường tại lớp phù hợp | VAL-01 |
| T-07 | Hai khóa `amount`, kể cả một khóa dùng escape `\u0061mount` | `400`, không có bản ghi được tạo | VAL-01 |
| T-08 | JSON lồng đến 4 container và đến 5 container | Mức 4 qua giới hạn parser rồi có thể lỗi schema; mức 5 bị parser chặn `400` | VAL-01 |
| T-09 | UTF-8 hỏng, JSON sai cú pháp, root array | Hai trường hợp đầu `400`; root array hợp lệ cú pháp trả `422` | VAL-01, VAL-02 |
| T-10 | VND với `"1"`, `"100000000"`, `"0"`, `"100000001"`, `"1.0"` | Hai giá trị đầu hợp lệ; ba giá trị sau `422` | VAL-03 |
| T-11 | USD với `"0.01"`, `"10000.00"`, `"0.001"`, `"10000.01"` | Hai giá trị đầu hợp lệ; hai giá trị sau `422` | VAL-03 |
| T-12 | Tiền là `"01"`, `"+1"`, `"1e3"`, `"1,000"` hoặc có dấu cách | `422`, không tự sửa hoặc làm tròn | VAL-03 |
| T-13 | Hai biên ngày, hai ngày ngoài biên ở mục 6.2 và `2026-02-30` | Hai biên hợp lệ; ngoài biên/ngày không tồn tại `422` | VAL-03 |
| T-14 | Mô tả 1000/1001 code point sau NFC, tiếng Việt có dấu tổ hợp và emoji ghép | Đo đúng định nghĩa; giá trị lưu đúng NFC | VAL-03 |
| T-15 | Mô tả chứa `<script>alert(1)</script>`, dấu nháy hoặc LF hợp lệ | Có thể nhận như văn bản; hiển thị an toàn và không tạo log giả | VAL-09 |
| T-16 | ID chuẩn của nhà cung cấp B, ID không tồn tại, tệp B, tệp A ngoài quyền | Cùng phản hồi công khai `404 REFERENCE_NOT_FOUND`, không lộ dữ liệu đối tượng | VAL-05 |
| T-17 | Tệp A chưa `READY`, bị cách ly hoặc nhà cung cấp A ngừng hoạt động | `422` nếu người gọi được quyền biết đối tượng; không tạo hồ sơ/liên kết | VAL-05, VAL-06 |
| T-18 | Array 5 ID hợp lệ, 6 ID hoặc lặp một ID | 5 ID qua số lượng; 6 ID hoặc lặp trả `422` | VAL-02, VAL-06 |
| T-19 | Tệp đúng 5 MiB và hơn 1 byte; tổng đúng 20 MiB và hơn 1 byte | Các biên qua kích thước; phần vượt `422` | VAL-06 |
| T-20 | Hai request đồng thời cùng hóa đơn, khác key | Một hồ sơ được tạo; request còn lại `409 INVOICE_CONFLICT` | VAL-07 |
| T-21 | Cùng key, dữ liệu tương đương sau chuẩn hóa, khác thứ tự khóa JSON | Cùng kết quả đã commit, không thêm hồ sơ/sự kiện logic | VAL-07 |
| T-22 | Cùng key nhưng đổi tiền; hoặc cùng key khi request đầu đang xử lý | `409 IDEMPOTENCY_CONFLICT` hoặc `409 REQUEST_IN_PROGRESS` đúng tình huống | VAL-07 |
| T-23 | Tạo thành công rồi retry sau mất phản hồi; ngày nghiệp vụ đã đổi | Kết quả cũ nếu còn quyền và trong thời gian lưu, không tạo lại | VAL-07 |
| T-24 | Phụ thuộc kiểm tra tham chiếu lỗi; crash trước/sau commit | `503` khi chưa xác minh được; retry phục hồi đúng, không có hồ sơ dở dang | VAL-06, VAL-07 |
| T-25 | Chưa xác thực; thiếu quyền; replay sau khi mất quyền | `401`/`403` theo hợp đồng, không lộ kết quả đã lưu | VAL-04, VAL-07 |
| T-26 | Payload lỗi chứa dữ liệu nhạy cảm giả và CR/LF | Tối đa 10 lỗi, không raw payload, không giả mạo log | VAL-08, VAL-09 |
| T-27 | Tệp đổi trạng thái hoặc nhà cung cấp ngừng hoạt động giữa kiểm tra và ghi | Giữ bất biến đã công bố tại điểm commit | VAL-05, VAL-06, VAL-07 |
| T-28 | Gọi API trực tiếp bỏ UI; so fixture trên bản triển khai | Cùng chính sách máy chủ; phiên bản/cấu hình khớp đặc tả | VAL-10 |
| T-29 | Header key thiếu/trùng/sai; sai content type/charset; nội dung nén | `400` cho key; `415` cho biểu diễn không hỗ trợ | VAL-01 |
| T-30 | Gửi chuỗi request theo hai bucket đã đặc tả | Sức chứa, tốc độ nạp và phạm vi khóa đúng; phần vượt `429` | VAL-01, kiểm soát R-10 |

Các ca qua giới hạn parser không nhất thiết hợp lệ về nghiệp vụ. Root chỉ cho bảy trường, nên object có 20 khóa có thuộc tính lạ và lỗi schema; object có 21 khóa cần bị parser chặn sớm. Quan sát lớp từ chối để chứng minh đúng kiểm soát.

Bổ sung biên `invoice_number` 1/40/41 ký tự, ID viết hoa/rút gọn, ký tự điều khiển bị cấm trong mô tả và số lỗi vượt 10. Với Unicode hợp lệ, giới hạn 1000 code point cũng khiến mô tả không thể vượt 4096 byte UTF-8; không thể tạo ca vượt riêng giới hạn byte mà vẫn thỏa giới hạn code point. Cần hiểu quan hệ giữa các ràng buộc thay vì tạo một fixture bất khả thi.

Tại mức parser, bổ sung object 20/21 thuộc tính, dữ liệu thừa sau JSON và surrogate lỗi. Với các kiểm thử tài nguyên, ghi lại mức giới hạn và số liệu quan sát ở tuyến triển khai thực; không chỉ chứng minh rằng một hàm validator trả `false`.

## 13. Hồ sơ truy vết từ rủi ro đến bằng chứng

Người đánh giá cần nhìn thấy vì sao quy tắc tồn tại và bằng chứng nào chứng minh nó được thực thi.

| Rủi ro | Yêu cầu chính | Điểm thực thi | Bằng chứng nghiệm thu |
| --- | --- | --- | --- |
| R-01 | VAL-01, VAL-02 | Ingress, parser, schema | T-05 đến T-09; payload raw có khóa trùng và giới hạn parser |
| R-02 | VAL-02, VAL-04 | Schema đóng, ngữ cảnh xác thực, mapper whitelist | T-03, T-25, bản ghi hợp lệ T-01 |
| R-03 | VAL-05 | Dịch vụ nghiệp vụ, truy vấn giới hạn tenant/quyền | T-16, ma trận principal–đối tượng |
| R-04 | VAL-03 | Kiểu miền số tiền/ngày, validator liên trường | T-10 đến T-14, giá trị lưu chính xác |
| R-05 | VAL-06 | Kho tệp, pipeline kiểm tra, commit liên kết | T-17 đến T-19, T-27; bất biến nội dung |
| R-06 | VAL-07 | Unique constraint, idempotency, transaction/outbox | T-20 đến T-24; đếm hồ sơ/sự kiện logic |
| R-07 | VAL-09 | Query binding, rendering, structured logging | T-15, T-26; cấu trúc truy vấn và DOM hiển thị |
| R-08 | VAL-08 | Error mapper, logging pipeline | T-26, phản hồi và mẫu log |
| R-09 | VAL-03, VAL-10 | Chuẩn hóa, cấu hình phát hành | T-14, T-28, hồ sơ phiên bản |
| R-10 | VAL-01, VAL-06 | Byte/parser budget, rate limit, worker tệp | T-05, T-19, T-30; cấu hình và số liệu tài nguyên |

Mỗi bằng chứng gắn với phiên bản chính sách và bản triển khai được kiểm tra. Một dòng “đã có validator” hoặc ảnh UI báo lỗi không đủ chứng minh kiểm soát tại máy chủ, quyền đối tượng hoặc cạnh tranh ghi.

## 14. Nhiệm vụ học viên và sản phẩm cần nộp

### Nhiệm vụ A — Hoàn thiện chính sách

Viết `IVP-PAYMENT-1.0` thành tài liệu yêu cầu cho đội phát triển, giữ nguyên các quyết định nghiệp vụ của tình huống. Tài liệu có phạm vi, chủ sở hữu, nguồn tin cậy, ma trận trường, chuẩn hóa, lỗi, log và giới hạn tài nguyên.

Chủ nghiệp vụ xác nhận hạn mức/ngày/duy nhất hóa đơn; phụ trách bảo mật xác nhận rủi ro và ranh giới tin cậy; đội API thực thi; đội kiểm thử thu bằng chứng; đội vận hành xác nhận cấu hình và khả năng quan sát lớp từ chối.

### Nhiệm vụ B — Phân bổ vào kiến trúc

Vẽ luồng dữ liệu hoặc mô tả tuần tự từ ingress đến commit. Với từng kiểm tra, ghi nó chạy trước hay sau chuẩn hóa, tại lớp nào, lỗi nào được trả và điều gì xảy ra nếu thành phần kiểm tra lỗi.

Giải thích hai tình huống: cùng key được retry sau commit nhưng chưa nhận phản hồi; trạng thái tệp thay đổi giữa kiểm tra và commit.

### Nhiệm vụ C — Lập kế hoạch kiểm thử

Chọn đủ ca đại diện ở mục 12 để bao phủ mọi yêu cầu và bổ sung các biên còn thiếu. Ghi fixture, dữ liệu raw khi cần, kỳ vọng HTTP, giá trị lưu và việc không có tác dụng nghiệp vụ khi từ chối.

Tách kiểm thử schema, parser và đồng thời. Nếu dựng request bằng map/object của ngôn ngữ lập trình, bạn có thể làm mất khóa trùng trước khi gửi; trường hợp đó phải gửi JSON raw.

### Nhiệm vụ D — Bảo vệ quyết định thiết kế

Giải thích vì sao từ chối thuộc tính lạ, dùng decimal chính xác, chuẩn hóa riêng mô tả, kiểm tra từng tham chiếu và dùng unique constraint. Chỉ ra ảnh hưởng tương thích khi đổi hạn mức hoặc quy tắc số tiền.

Sản phẩm nộp gồm chính sách, bảng truy vết rủi ro–yêu cầu–kiểm thử, mô tả điểm thực thi và kế hoạch kiểm thử có fixture. Không bắt buộc xây ứng dụng hoàn chỉnh để chứng minh đã đặc tả được yêu cầu bảo mật.

### Nhiệm vụ E — Quản lý thay đổi chính sách

Giả sử phiên bản sau bổ sung `EUR` hoặc giảm hạn mức USD. Lập phân tích tác động đến client, schema, kiểu miền, dữ liệu đang có, kết quả idempotency và bộ kiểm thử. Không suy rằng chính sách đầu vào mới tự làm mất hiệu lực các hồ sơ đã được chấp nhận theo phiên bản cũ.

Đề xuất cách triển khai có quan sát: theo dõi mã lỗi theo phiên bản, cập nhật hợp đồng cho client và có cách quay lại cấu hình nhất quán nếu phát hiện lỗi. Không chạy chế độ chỉ cảnh báo để bỏ kiểm soát đang ngăn truy cập chéo tenant hoặc tạo dữ liệu sai; mọi ngoại lệ phải có phạm vi, thời hạn, người chịu trách nhiệm và rủi ro được chấp nhận rõ ràng.

## 15. Tiêu chí đánh giá và điều kiện hoàn thành

| Tiêu chí | Điểm | Biểu hiện đạt |
| --- | --- | --- |
| Phạm vi, tài sản, mô hình đe dọa | 15 | Rõ nguồn chưa tin cậy, tenant, hậu quả cần ngăn |
| Hợp đồng dữ liệu và chuẩn hóa | 25 | Có kiểu, required/null/default, giới hạn, liên trường, biểu diễn chuẩn |
| Quyền, trạng thái, tệp, cạnh tranh | 20 | Phân biệt cú pháp với quyền; có bất biến commit và replay |
| Yêu cầu đo được và truy vết | 15 | Mỗi yêu cầu có điều kiện, hành vi, phép kiểm chứng, rủi ro liên quan |
| Lỗi, log và phục hồi | 10 | Không rò dữ liệu; phân biệt input sai với phụ thuộc lỗi; retry không tạo lặp |
| Kế hoạch kiểm thử, bằng chứng | 15 | Bao phủ hợp lệ, sai, biên, parser, đồng thời và triển khai thực |

Bài trình bày tốt vẫn chưa hoàn thành nếu còn lỗ hổng nền tảng: tenant do client quyết định; UUID hợp lệ được xem là đã có quyền; dùng số thực rồi làm tròn tiền đầu vào; bỏ kiểm tra khi phụ thuộc lỗi; hoặc chống trùng chỉ bằng truy vấn trước ghi.

Trước khi giao đặc tả, xác minh mỗi quy tắc đều trả lời được: **kiểm tra điều gì, ở đâu, trên biểu diễn nào, với ngưỡng nào, thất bại ra sao và bằng chứng nào xác nhận kết quả**. Đây là cầu nối giữa mục tiêu bảo mật, thiết kế kiến trúc và tiêu chí kiểm thử trong vòng đời phát triển.
