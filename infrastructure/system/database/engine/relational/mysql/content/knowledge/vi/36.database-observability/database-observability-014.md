# Giới hạn dữ liệu nhạy cảm và thời gian lưu log/trace

## Mục tiêu

Trong chương **Quan sát hệ thống**, bài học này giúp bạn thiết kế log và trace đủ thông tin để chẩn đoán MySQL nhưng không biến hệ thống quan sát thành một bản sao dữ liệu nghiệp vụ. Sau bài học, bạn có thể:

- Nhận diện dữ liệu nhạy cảm có thể xuất hiện trong log và trace của ứng dụng, MySQL và nền tảng thu thập telemetry.
- Chọn trường được phép ghi, loại bỏ hoặc che dữ liệu trước khi gửi đến nơi lưu trữ.
- Hiểu rủi ro của general query log, slow query log và dữ liệu câu lệnh trong Performance Schema.
- Xác định thời gian lưu theo mục đích, mức độ nhạy cảm và yêu cầu vận hành; quản lý cả bản sao lưu và dữ liệu lưu trữ dài hạn.
- Kiểm chứng rằng dữ liệu bị cấm không lọt vào log/trace và dữ liệu hết hạn được xóa theo chính sách.

## 1. Quan sát tốt phải đi cùng giới hạn dữ liệu

Log ghi lại sự kiện đã xảy ra; trace mô tả một yêu cầu đi qua những thành phần nào và mất bao lâu ở mỗi bước. Với MySQL, các tín hiệu này có thể giúp tìm truy vấn chậm, lỗi kết nối, deadlock, truy cập bất thường và điểm nghẽn tài nguyên. Tuy nhiên, nội dung câu SQL, tham số, thông tin kết nối hoặc thuộc tính gắn với một người dùng có thể tiết lộ dữ liệu nghiệp vụ.

Ví dụ, câu lệnh sau chứa giá trị email ngay trong phần SQL:

```sql
SELECT id, status
FROM customer
WHERE email = 'lan@example.com';
```

Nếu ứng dụng ghi nguyên câu SQL vào log, email có thể được sao chép sang hệ thống tập trung, công cụ tìm kiếm log, kho lưu trữ, bản xuất phục vụ hỗ trợ và bản sao lưu của những hệ thống đó. Người có quyền đọc log khi ấy có thể nhìn thấy dữ liệu mà họ không được phép truy cập trong ứng dụng.

Vì vậy, mỗi tín hiệu quan sát cần trả lời hai câu hỏi: **Thông tin nào thực sự cần để vận hành?** và **Ai có thể xem thông tin đó trong suốt vòng đời lưu trữ?** Thu thập càng nhiều dữ liệu không đồng nghĩa với khả năng quan sát càng tốt. Mục tiêu là thu thập đủ ngữ cảnh để tìm nguyên nhân, với lượng dữ liệu nhạy cảm thấp nhất.

## 2. Xác định dữ liệu có thể xuất hiện trong log và trace

Không chỉ nội dung do ứng dụng tự ghi mới có rủi ro. Một trường dữ liệu có thể đi qua nhiều lớp: ứng dụng, driver, MySQL, agent thu thập, bộ chuyển tiếp, kho lưu trữ và công cụ phân tích. Cần lập danh mục cho toàn bộ đường đi này.

| Nguồn | Dữ liệu có thể xuất hiện | Rủi ro cần kiểm soát |
|---|---|---|
| Log ứng dụng | Email, số điện thoại, tên, mã đơn hàng, nội dung biểu mẫu, token | Lộ dữ liệu cá nhân hoặc thông tin xác thực |
| Log truy vấn MySQL | SQL text, giá trị literal, tên bảng/cột, tài khoản kết nối | Lộ tham số truy vấn, cấu trúc nghiệp vụ hoặc danh tính tài khoản |
| Error log | Thông tin lỗi, địa chỉ máy khách, tên tài khoản, tên database hoặc đường dẫn | Tiết lộ thông tin hạ tầng và định danh |
| Audit log | Người dùng, nguồn kết nối, hành động, đối tượng bị truy cập | Có thể chứa dữ liệu định danh; thường cần bảo vệ và lưu lâu hơn log chẩn đoán |
| Trace | Tên operation, câu truy vấn, thuộc tính span, baggage, URL hoặc header được truyền tiếp | Dữ liệu nhạy cảm lan truyền qua nhiều dịch vụ |
| Log của agent và proxy | Nhãn, metadata, cấu hình kết nối, lỗi gửi dữ liệu | Có thể vô tình ghi credential hoặc thông tin nội bộ |

Phân loại dữ liệu trước khi chọn trường log. Một cách phân loại thực tế gồm:

| Nhóm | Ví dụ | Cách xử lý |
|---|---|---|
| Cấm ghi | Mật khẩu, access token, refresh token, private key, chuỗi kết nối có credential, mã xác thực dùng một lần | Không ghi ở bất kỳ mức log nào; loại bỏ tại nguồn |
| Nhạy cảm | Số định danh, email, số điện thoại, địa chỉ, dữ liệu thanh toán, nội dung người dùng, giá trị tham số chứa dữ liệu cá nhân | Không ghi giá trị thô; nếu có mục đích được phê duyệt, chỉ ghi dạng đã giảm thiểu hoặc giả danh hóa |
| Nội bộ | Tên schema, bảng, máy chủ, tài khoản dịch vụ, mã tenant, cấu trúc truy vấn | Chỉ ghi khi cần; giới hạn người xem và thời gian lưu |
| Vận hành thông thường | Loại thao tác, thời lượng, số hàng đọc, mã lỗi đã chuẩn hóa, phiên bản ứng dụng | Có thể ghi theo allowlist và chính sách lưu trữ |

Phân loại phải xét cả tổ hợp trường. Một `trace_id` thường không phải dữ liệu cá nhân, nhưng khi liên kết với bảng ánh xạ người dùng hoặc một sự kiện cụ thể, nó có thể trở thành khóa tra cứu dẫn đến dữ liệu nhạy cảm. Tương tự, `tenant_id`, `customer_id` hay tên bảng có thể không chứa nội dung cá nhân nhưng vẫn tiết lộ cấu trúc hoặc khách hàng nội bộ.

## 3. Kiểm soát nội dung log truy vấn MySQL

MySQL có nhiều nguồn thông tin phục vụ chẩn đoán. Mỗi nguồn có mục đích và mức độ chi tiết khác nhau; không nên bật tất cả rồi chuyển toàn bộ dữ liệu sang kho log mà không đánh giá.

### General query log

General query log ghi nhận hoạt động mà máy chủ nhận được, gồm các câu lệnh từ client. Đây là công cụ hữu ích khi cần điều tra ngắn hạn một vấn đề cụ thể, nhưng có thể tạo lượng dữ liệu lớn và lưu nguyên nội dung câu lệnh. Nếu câu SQL chứa literal nhạy cảm, dữ liệu đó có thể xuất hiện trong log.

Trong môi trường production, thường nên để general query log tắt trong vận hành bình thường. Khi cần bật để điều tra, hãy giới hạn khoảng thời gian, phạm vi máy chủ và người có quyền truy cập; xác định trước vị trí lưu, cách xoay vòng và thời điểm tắt. `log_output` cho phép chọn `FILE`, `TABLE`, kết hợp `FILE,TABLE` hoặc `NONE`; các lựa chọn này quyết định đích xuất log, không tự động loại bỏ hay che giá trị nhạy cảm.

### Slow query log

Slow query log giúp tìm truy vấn vượt ngưỡng thời gian. Nó có giá trị cho tối ưu hiệu năng, nhưng nội dung truy vấn được ghi vẫn có thể chứa giá trị literal. Vì vậy, bật slow query log không đồng nghĩa dữ liệu đã an toàn.

Ví dụ cấu hình khởi điểm trong tệp cấu hình MySQL:

```ini
[mysqld]
general_log = OFF
slow_query_log = ON
long_query_time = 1
log_output = FILE
```

`long_query_time = 1` chỉ là giá trị minh họa một giây, không phải ngưỡng phù hợp cho mọi hệ thống. Hãy chọn ngưỡng dựa trên mục tiêu độ trễ, tải thực tế và lượng log có thể xử lý. Nếu cần điều tra câu truy vấn chứa dữ liệu nhạy cảm, giới hạn quyền đọc tệp log và thời gian lưu; cân nhắc dùng dữ liệu tổng hợp hoặc fingerprint thay cho SQL text đầy đủ.

Kiểm tra trạng thái hiện tại bằng các lệnh chỉ đọc:

```sql
SHOW GLOBAL VARIABLES
WHERE Variable_name IN (
  'general_log',
  'slow_query_log',
  'long_query_time',
  'log_output'
);
```

Thay đổi cấu hình ở production cần tuân theo quy trình vận hành của hệ thống, kiểm tra phiên bản MySQL và đánh giá tác động trước khi áp dụng. Không bật log chi tiết trên diện rộng chỉ để thu thập dữ liệu dự phòng.

### Error log, audit log và Performance Schema

Error log giúp tìm lỗi khởi động, lỗi lưu trữ, lỗi kết nối và sự cố máy chủ. Dù thường không ghi toàn bộ dữ liệu hàng, log này vẫn có thể chứa tên tài khoản, địa chỉ máy khách, tên database hoặc đường dẫn nội bộ. Hãy giới hạn quyền đọc và áp dụng thời gian lưu phù hợp.

Audit log tập trung vào ai đã thực hiện hành động nào, từ đâu và trên đối tượng nào. Đây là dữ liệu phục vụ điều tra bảo mật và trách nhiệm giải trình, nên yêu cầu về tính toàn vẹn, quyền truy cập và thời gian lưu có thể khác log hiệu năng. Chỉ bật các sự kiện cần thiết để đáp ứng mục đích kiểm soát đã xác định.

Performance Schema cung cấp dữ liệu chẩn đoán trong bộ nhớ. Chẳng hạn, `events_statements_summary_by_digest` tổng hợp thống kê theo digest; `DIGEST_TEXT` biểu diễn dạng câu lệnh đã chuẩn hóa và thường hữu ích hơn việc lưu từng câu SQL thô. Ngược lại, các bảng lịch sử câu lệnh có thể cung cấp `SQL_TEXT`, vốn cần được xem là nội dung có khả năng chứa dữ liệu nhạy cảm.

Ví dụ đọc thống kê theo digest:

```sql
SELECT
  DIGEST_TEXT,
  COUNT_STAR,
  AVG_TIMER_WAIT,
  SUM_ROWS_EXAMINED
FROM performance_schema.events_statements_summary_by_digest
ORDER BY SUM_TIMER_WAIT DESC
LIMIT 10;
```

Digest giảm lộ giá trị literal nhưng không phải cơ chế ẩn danh hoàn chỉnh. Tên schema, bảng, cột hoặc cấu trúc truy vấn vẫn có thể tiết lộ thông tin nội bộ. Cần giới hạn quyền truy vấn các bảng Performance Schema và kiểm tra nội dung trước khi xuất dữ liệu ra ngoài máy chủ.

## 4. Thiết kế log và trace theo allowlist

Hãy định nghĩa schema log/trace bằng danh sách trường được phép (allowlist). Mỗi trường cần có mục đích, chủ sở hữu, phân loại dữ liệu và thời gian lưu. Mặc định loại bỏ trường không được khai báo. Cách này dễ kiểm soát hơn việc ghi mọi thứ rồi cố tìm và che các trường nguy hiểm.

Một bản ghi truy vấn phục vụ hiệu năng có thể gồm:

```json
{
  "event": "db.query",
  "service": "order-api",
  "operation": "find-orders-by-status",
  "db.system": "mysql",
  "db.operation": "SELECT",
  "db.query.summary": "SELECT orders WHERE status = ?",
  "duration_ms": 42,
  "rows_examined": 1200,
  "outcome": "success",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736"
}
```

Đây là ví dụ schema minh họa; tên thuộc tính thực tế phụ thuộc thư viện instrumentation. Bản ghi giữ lại operation, dạng truy vấn đã rút gọn, thời lượng, số hàng và mã liên kết trace. Nó không lưu email, mã khách hàng, tham số truy vấn hoặc câu SQL có literal.

Một số quy tắc triển khai quan trọng:

1. **Giảm thiểu tại nguồn.** Ứng dụng hoặc instrumentation phải loại bỏ dữ liệu nhạy cảm trước khi gửi event ra khỏi tiến trình. Redaction ở collector là lớp bảo vệ bổ sung; dữ liệu đã đi qua hàng đợi hoặc proxy vẫn có thể bị lưu ở đó.
2. **Ưu tiên tên operation ổn định.** Dùng `find-orders-by-status` thay vì đưa URL, tên người dùng hoặc giá trị đầu vào vào tên span. Tên span có giá trị thay đổi theo từng yêu cầu làm tăng cardinality và có thể tiết lộ dữ liệu.
3. **Không ghi tham số thô.** Dùng placeholder, query summary hoặc fingerprint đã được kiểm soát. Không đưa bind parameter vào message, exception hoặc thuộc tính trace.
4. **Lọc header và baggage.** Chỉ truyền tiếp các header cần thiết. Loại bỏ `Authorization`, cookie, token và trường định danh không cần thiết trước khi tạo span hoặc gửi sang dịch vụ khác.
5. **Che dữ liệu có chủ đích.** Nếu cần liên kết sự kiện theo một đối tượng, dùng mã giả danh hóa có kiểm soát hoặc mã tham chiếu không thể suy ngược từ log. Hash đơn giản của email hoặc số điện thoại vẫn có thể bị dò bằng từ điển; không xem hash không khóa là ẩn danh.
6. **Kiểm soát lỗi.** Exception có thể chứa câu SQL, giá trị tham số, đường dẫn hoặc dữ liệu đầu vào. Chuẩn hóa thông báo lỗi và giữ stack trace chi tiết trong phạm vi được bảo vệ.

Không nên gắn mọi `user_id`, `order_id` hoặc `tenant_id` vào tất cả span. Nếu cần điều tra một trường hợp cụ thể, hãy dùng cơ chế tra cứu có quyền kiểm soát và thời hạn rõ ràng thay vì biến mọi trace thành chỉ mục dữ liệu người dùng.

## 5. Chọn thời gian lưu log và trace

Thời gian lưu phải bắt đầu từ mục đích sử dụng. Log debug để chẩn đoán sự cố ngắn hạn thường không cần lưu lâu như audit log phục vụ điều tra. Trace có khối lượng lớn và thường hữu ích nhất trong khoảng thời gian gần sự cố; metric đã tổng hợp có thể được giữ lâu hơn để phân tích xu hướng.

Một chính sách cần xác định riêng cho từng loại dữ liệu:

| Loại dữ liệu | Mục đích chính | Ví dụ thời gian lưu khởi điểm | Điều cần cân nhắc |
|---|---|---:|---|
| Log debug tạm thời | Điều tra lỗi cụ thể | 1–7 ngày | Chỉ bật theo thời hạn; xóa sau khi kết thúc điều tra |
| Log ứng dụng vận hành | Tìm lỗi và đối chiếu yêu cầu gần đây | 14–30 ngày | Giảm thiểu dữ liệu cá nhân; giới hạn quyền tìm kiếm |
| Slow query log | Phân tích truy vấn chậm | 7–30 ngày | Có thể chứa SQL text; cân nhắc fingerprint và ngưỡng ghi |
| Trace chi tiết | Theo dõi luồng yêu cầu và độ trễ | 3–14 ngày | Dung lượng lớn; dùng sampling và giới hạn thuộc tính |
| Metric tổng hợp | Phân tích xu hướng hiệu năng | 90 ngày đến 13 tháng | Giữ dữ liệu đã tổng hợp, tránh nhãn định danh có cardinality cao |
| Audit log | Điều tra truy cập và đáp ứng nghĩa vụ kiểm soát | Theo chính sách bảo mật/pháp lý; ví dụ 90–365 ngày | Cần bảo vệ tính toàn vẹn, quyền đọc và quy trình lưu trữ dài hạn |

Các khoảng thời gian trên chỉ là ví dụ để bắt đầu thảo luận chính sách, không phải chuẩn bắt buộc hoặc tư vấn pháp lý. Thời hạn chính thức phải căn cứ vào yêu cầu pháp luật áp dụng, hợp đồng, quy định nội bộ, mục tiêu khôi phục, nhu cầu điều tra và chi phí lưu trữ. Nếu yêu cầu pháp lý quy định thời hạn cụ thể, yêu cầu đó được ưu tiên.

Với mỗi loại log/trace, hãy ghi rõ:

- **Mục đích:** sự cố nào hoặc yêu cầu kiểm soát nào cần dữ liệu này?
- **Chủ sở hữu:** nhóm nào chịu trách nhiệm cho nội dung và thời hạn lưu?
- **Thời hạn nóng:** dữ liệu có thể tìm kiếm nhanh trong bao lâu?
- **Lưu trữ dài hạn:** có cần archive không, ai được truy cập và có mã hóa không?
- **Hết hạn:** hệ thống nào xóa dữ liệu, xóa trong bao lâu và cách kiểm chứng là gì?
- **Ngoại lệ:** ai được phép đặt legal hold hoặc gia hạn, lý do và ngày xem xét lại là gì?

### Tính cả bản sao và đường đi của dữ liệu

Xóa bản ghi khỏi giao diện tìm kiếm không đảm bảo dữ liệu đã biến mất. Log có thể còn trong hàng đợi, bucket lưu trữ, bản sao vùng, snapshot, backup hoặc bản xuất tải về. Chính sách phải mô tả vòng đời của tất cả bản sao do tổ chức quản lý.

Nếu dữ liệu nằm trong backup bất biến, không thể xóa từng bản ghi ngay lập tức, hãy xác định thời hạn backup tự hết hạn, giới hạn quyền khôi phục và quy trình xử lý dữ liệu sau khi restore. Một lần restore không được vô tình đưa dữ liệu đã hết hạn trở lại kho log đang hoạt động.

Ước tính dung lượng cơ bản bằng:

```text
Dung lượng lưu xấp xỉ = dữ liệu phát sinh mỗi ngày × số ngày lưu
```

Ví dụ, hệ thống phát sinh 2 GB log đã nén mỗi ngày và lưu 30 ngày cần khoảng 60 GB cho một bản lưu, trước khi tính chỉ mục, bản sao và phần dự phòng. Nếu có ba bản sao độc lập, dung lượng vật lý có thể cao hơn đáng kể. Việc giảm trường dữ liệu, sampling trace và rút ngắn thời hạn log debug vừa giảm rủi ro vừa giảm chi phí.

## 6. Bảo vệ kho log và trace

Ngay cả khi dữ liệu đã được giảm thiểu, kho log vẫn là hệ thống nhạy cảm vì nó tập trung nhiều dấu vết vận hành. Áp dụng các biện pháp sau:

- **Phân quyền tối thiểu:** tách quyền cấu hình collector, ghi dữ liệu, tìm kiếm, xuất dữ liệu và quản trị retention. Người phát triển không mặc nhiên cần quyền đọc mọi log production.
- **Xác thực và mã hóa:** dùng xác thực dịch vụ, mã hóa khi truyền và mã hóa khi lưu; quản lý khóa theo quy trình riêng.
- **Kiểm toán truy cập:** ghi nhận ai tìm kiếm, xuất hoặc thay đổi chính sách lưu trữ; bảo vệ audit trail khỏi bị sửa bởi cùng tài khoản có quyền quản trị log.
- **Tách môi trường:** không chuyển log production sang môi trường phát triển hoặc kiểm thử nếu chưa giảm thiểu dữ liệu và có phê duyệt phù hợp.
- **Giới hạn xuất dữ liệu:** đặt giới hạn kết quả, thời gian tải xuống và quyền chia sẻ; kiểm soát các dashboard hoặc liên kết truy vấn có thể mở rộng cho nhiều người.
- **Bảo vệ cấu hình:** không đặt credential trong cấu hình agent, command line, biến log hoặc repository; dùng secret manager và cơ chế cấp quyền dịch vụ.

Sampling giúp giảm lượng trace cần lưu. Có thể lấy mẫu tỷ lệ nhỏ với yêu cầu thành công thông thường và giữ tỷ lệ cao hơn cho lỗi hoặc độ trễ vượt ngưỡng bằng tail sampling. Tuy nhiên, sampling không phải biện pháp che dữ liệu: mọi span được tạo vẫn phải tuân thủ allowlist và redaction trước khi được gửi đi.

## 7. Kiểm chứng chính sách trước khi đưa vào vận hành

Chính sách chỉ có tác dụng khi có thể kiểm chứng. Hãy thử nghiệm trên môi trường kiểm soát bằng dữ liệu giả lập có dấu hiệu dễ tìm, chẳng hạn chuỗi `SENSITIVE_TEST_9F31`, email giả và token giả. Gửi các giá trị đó qua những luồng truy vấn, lỗi và trace dự kiến; sau đó tìm trong mọi đích log, hàng đợi và kho lưu trữ để xác nhận giá trị thô không xuất hiện.

Quy trình triển khai gợi ý:

1. Liệt kê nguồn phát log/trace, collector, queue, kho lưu trữ, dashboard, bản xuất và backup.
2. Phân loại trường dữ liệu; xác định trường cấm, trường cần giảm thiểu và trường được phép.
3. Thiết lập allowlist tại nguồn; tắt ghi SQL thô và debug chi tiết khi không có nhu cầu đã phê duyệt.
4. Cấu hình thời hạn cho từng loại tín hiệu, chính sách archive, xóa và xử lý backup.
5. Thử với dữ liệu giả lập, kiểm tra kết quả tìm kiếm ở tất cả đích đến và kiểm tra quyền truy cập.
6. Chạy thử quy trình hết hạn; xác nhận dữ liệu bị xóa khỏi kho hoạt động và có thời hạn rõ ràng cho bản sao lưu.
7. Theo dõi tỷ lệ log bị loại, lỗi redaction, dung lượng phát sinh và các trường mới xuất hiện ngoài schema.

Nếu phát hiện secret hoặc dữ liệu cá nhân đã lọt vào log, hãy giới hạn quyền truy cập ngay, xác định phạm vi và các bản sao bị ảnh hưởng, luân chuyển credential nếu có nguy cơ lộ, rồi thực hiện xóa hoặc cô lập theo quy trình ứng phó sự cố. Ghi nhận quyết định và bằng chứng cần thiết trong hệ thống sự cố được bảo vệ. Không tiếp tục sao chép đoạn log chứa dữ liệu đó vào ticket, email hoặc kênh trao đổi thông thường.

## 8. Checklist áp dụng cho hệ thống MySQL

Trước khi bật hoặc thay đổi cơ chế quan sát, hãy xác nhận:

- [ ] General query log chỉ được bật khi có mục đích và thời hạn điều tra rõ ràng.
- [ ] Slow query log có ngưỡng phù hợp; người vận hành hiểu rằng SQL text vẫn có thể chứa literal nhạy cảm.
- [ ] Error log, audit log và dữ liệu Performance Schema có quyền đọc phù hợp.
- [ ] Log và trace dùng allowlist; không ghi password, token, cookie, credential hoặc bind parameter thô.
- [ ] Span name, label và baggage không chứa giá trị định danh hoặc dữ liệu đầu vào không cần thiết.
- [ ] Mỗi loại dữ liệu có chủ sở hữu, mục đích, thời hạn lưu, quy tắc archive và xóa.
- [ ] Backup, snapshot, bản sao vùng và dữ liệu sau restore nằm trong vòng đời retention.
- [ ] Truy cập và xuất log được phân quyền, mã hóa và kiểm toán.
- [ ] Kiểm thử bằng dữ liệu giả lập chứng minh dữ liệu cấm không xuất hiện ở các đích thu thập.

## Kết luận

Quan sát MySQL an toàn bắt đầu từ việc quyết định dữ liệu nào được phép rời khỏi ứng dụng và máy chủ. Hãy ưu tiên operation, thời lượng, số hàng, mã lỗi chuẩn hóa và thống kê theo digest; chỉ thu thập SQL text hoặc dữ liệu chi tiết trong tình huống có kiểm soát. Mỗi loại log và trace cần thời hạn lưu dựa trên mục đích, yêu cầu áp dụng và toàn bộ vòng đời của các bản sao. Khi giảm thiểu dữ liệu ngay tại nguồn, phân quyền kho lưu trữ và kiểm chứng việc hết hạn, đội vận hành vẫn có đủ tín hiệu để chẩn đoán mà không tạo thêm một kho dữ liệu nhạy cảm khó kiểm soát.
