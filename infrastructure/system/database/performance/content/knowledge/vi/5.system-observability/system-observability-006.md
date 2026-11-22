# Lấy mẫu và kiểm soát chi phí giám sát khi hệ thống đang chịu tải

## Mục tiêu học tập

Sau bài học này, bạn có thể:

- Giải thích vì sao thu thập telemetry có thể tiêu tốn CPU, bộ nhớ, I/O và mạng của ứng dụng lẫn cơ sở dữ liệu.
- Phân biệt cách lấy mẫu metrics, logs và traces; biết loại dữ liệu nào cần giữ đầy đủ và loại nào có thể lấy mẫu.
- Chọn chiến lược lấy mẫu phù hợp với mục tiêu điều tra, mức tải và ngân sách quan sát.
- Giới hạn chi phí bằng ngân sách sự kiện, chu kỳ thu thập, hàng đợi có giới hạn, kiểm soát cardinality và chính sách lưu trữ.
- Đo tác động của hệ thống giám sát và kiểm chứng rằng việc giảm telemetry không che khuất sự cố hiệu năng.

## 1. Vì sao phải kiểm soát chi phí quan sát?

Quan sát hệ thống (observability) là khả năng suy luận trạng thái bên trong của một hệ thống từ dữ liệu mà nó phát ra. Với cơ sở dữ liệu, dữ liệu quan sát thường gồm metrics, logs, traces, thống kê truy vấn, sự kiện chờ, thông tin khóa và đôi khi cả dữ liệu profiling.

Những dữ liệu này giúp trả lời các câu hỏi như: truy vấn nào đang tiêu tốn nhiều thời gian CPU, giao dịch nào chờ khóa, bộ nhớ đệm có giảm hiệu quả không, I/O đang tăng ở thiết bị nào, hay độ trễ xuất hiện ở ứng dụng, connection pool hay máy chủ cơ sở dữ liệu.

Tuy nhiên, thu thập và chuyển dữ liệu quan sát cũng cần tài nguyên. Mỗi sự kiện có thể yêu cầu đọc đồng hồ, tạo đối tượng, định dạng chuỗi, ghi bộ đệm, cấp phát bộ nhớ, mã hóa, nén, gửi qua mạng và lưu trữ ở hệ thống giám sát. Truy vấn các catalog hoặc view thống kê quá thường xuyên cũng có thể tạo tải trên chính máy chủ cần quan sát.

Khi hệ thống rảnh, chi phí đó có thể khó nhận ra. Khi hệ thống gần bão hòa, một lượng telemetry lớn có thể cạnh tranh CPU, bộ nhớ, I/O và kết nối với workload nghiệp vụ. Nếu hệ thống giám sát làm tăng hàng đợi hoặc khiến truy vấn chậm hơn, dữ liệu quan sát có nguy cơ làm thay đổi hiện tượng mà ta đang cố đo. Đây là hiệu ứng người quan sát (observer effect).

Vì vậy, mục tiêu của bài học trong module DATABASE_PERFORMANCE là duy trì đủ tín hiệu để chẩn đoán hiệu năng, đồng thời giữ chi phí quan sát trong một ngân sách có thể đo và kiểm soát.

## 2. Những thành phần tạo ra chi phí giám sát

Chi phí quan sát xuất hiện ở nhiều nơi, không chỉ ở máy chủ lưu trữ metrics hoặc log.

| Thành phần | Chi phí có thể phát sinh | Ví dụ trong hệ thống cơ sở dữ liệu |
| --- | --- | --- |
| Instrumentation trong ứng dụng | CPU, cấp phát bộ nhớ và độ trễ trên đường xử lý | Tạo span cho mọi lời gọi SQL, gắn nhiều thuộc tính vào từng span |
| Thu thập tại cơ sở dữ liệu | CPU, bộ nhớ, khóa nội bộ và I/O | Truy vấn view thống kê liên tục, bật log mọi câu SQL hoặc thu stack trace thường xuyên |
| Bộ đệm và hàng đợi | Bộ nhớ và chi phí sao chép dữ liệu | Giữ hàng nghìn sự kiện chờ exporter gửi đi |
| Truyền dữ liệu | CPU mã hóa/nén, băng thông mạng và retry | Gửi log truy vấn dài hoặc trace có nhiều span |
| Xử lý telemetry | CPU, bộ nhớ và I/O ở collector hoặc backend | Gộp histogram, xử lý tail sampling, lập chỉ mục log |
| Lưu trữ và truy vấn | Dung lượng, chỉ mục và chi phí truy vấn | Lưu trace chi tiết lâu ngày hoặc tạo quá nhiều time series |

Chi phí thường tăng theo số sự kiện, kích thước mỗi sự kiện, số thuộc tính, tần suất thu thập và thời gian lưu trữ. Một hệ thống phát 20.000 span mỗi giây với kích thước trung bình 1 KB tạo ra khoảng 20 MB dữ liệu mỗi giây trước khi tính overhead của giao thức, chỉ mục và bản sao. Con số minh họa này cho thấy số lượng sự kiện và kích thước payload đều quan trọng.

Không phải mọi loại instrumentation có chi phí như nhau. Đọc một bộ đếm đã được hệ quản trị tổng hợp thường rẻ hơn tạo một stack trace cho mỗi lần thực thi. Ghi một metric có nhãn ổn định thường rẻ hơn tạo một time series mới cho mỗi giá trị SQL hoặc mã người dùng.

## 3. Phân biệt metrics, logs và traces trước khi lấy mẫu

Chính sách lấy mẫu phải dựa trên ý nghĩa của dữ liệu. Không nên áp dụng cùng một tỷ lệ cho mọi tín hiệu.

| Loại telemetry | Mô tả | Mục đích chính | Cách kiểm soát thường dùng |
| --- | --- | --- | --- |
| Metrics | Số đo được tổng hợp theo thời gian, như số truy vấn, độ trễ, CPU hoặc số lần chờ khóa | Theo dõi xu hướng, cảnh báo và so sánh tải | Giới hạn nhãn, chọn chu kỳ scrape hợp lý, dùng histogram hoặc sketch |
| Logs | Sự kiện dạng bản ghi, thường có nội dung và ngữ cảnh chi tiết | Giải thích một lỗi hoặc hành động cụ thể | Lọc mức độ, lấy mẫu theo nhóm, giới hạn tốc độ và kích thước |
| Traces | Các span liên kết thành đường đi của một request hoặc transaction qua nhiều thành phần | Tìm thành phần gây chậm và quan hệ giữa các lời gọi | Head sampling, tail sampling, quy tắc ưu tiên và giới hạn tốc độ |
| Profiles | Mẫu stack hoặc mức sử dụng tài nguyên theo thời gian | Tìm hàm hoặc đường mã tiêu tốn CPU/bộ nhớ | Sampling theo thời gian, giới hạn tần suất và thời lượng profiling |

Metrics thường được tổng hợp trước khi xuất. Ví dụ, bộ đếm số truy vấn có thể tăng cho mọi truy vấn, sau đó exporter gửi giá trị tổng hợp mỗi khoảng thời gian. Không cần tạo một log riêng cho từng lần tăng bộ đếm.

Với độ trễ, histogram hoặc sketch có thể ghi nhận phân bố trong quá trình xử lý rồi xuất các bucket hoặc cấu trúc tổng hợp. Nếu cần p95 và p99 đáng tin cậy, nên tính chúng từ histogram/sketch được cập nhật cho toàn bộ quan sát hoặc từ nguồn đo có quy tắc rõ ràng. Lấy mẫu một số trace rồi tính p99 từ số trace được giữ lại có thể bỏ sót phần đuôi chậm, nhất là khi sự kiện chậm hiếm.

Logs và traces thường chứa nhiều chi tiết hơn nên là ứng viên phù hợp để lấy mẫu, nhưng cần giữ các nhóm sự kiện có giá trị điều tra cao theo chính sách rõ ràng. Metrics tổng hợp về số lỗi, tỷ lệ timeout và phân bố độ trễ vẫn cần duy trì ngay cả khi log hoặc trace bị giảm.

## 4. Lấy mẫu là gì và tác động ra sao?

Lấy mẫu (sampling) là chọn một phần dữ liệu quan sát để lưu hoặc chuyển tiếp, thay vì giữ mọi sự kiện. Tỷ lệ lấy mẫu có thể là cố định, theo xác suất, theo tốc độ tối đa hoặc thay đổi theo điều kiện.

Giả sử một dịch vụ tạo 50.000 trace mỗi phút. Nếu lấy mẫu ngẫu nhiên 2%, số trace kỳ vọng được giữ là khoảng 1.000 mỗi phút. Tỷ lệ thấp làm giảm chi phí truyền và lưu trữ, nhưng cũng làm giảm cơ hội quan sát các trường hợp hiếm.

Với lấy mẫu độc lập theo xác suất p, nếu một loại sự kiện xuất hiện k lần thì xác suất giữ được ít nhất một sự kiện thuộc loại đó là `1 - (1 - p)^k`. Nếu chỉ có một sự kiện lỗi và p = 0,02, xác suất giữ sự kiện đó chỉ là 2%. Do đó, lấy mẫu ngẫu nhiên thuần túy có thể bỏ lỡ một lỗi đơn lẻ rất quan trọng.

Lấy mẫu cũng có thể tạo sai lệch. Nếu chỉ giữ các trace hoàn tất nhanh, ta sẽ đánh giá thấp độ trễ. Nếu chỉ lấy mẫu một tenant hoặc một loại truy vấn, số liệu tổng hợp không còn đại diện cho toàn bộ workload. Chính sách cần ghi nhận tỷ lệ lấy mẫu và cách chọn mẫu để người đọc hiểu giới hạn của dữ liệu.

## 5. Các chiến lược lấy mẫu phổ biến

### Lấy mẫu theo xác suất (probabilistic sampling)

Mỗi sự kiện có xác suất p được chọn độc lập. Cách này đơn giản, phân bố mẫu khá đều khi số lượng sự kiện lớn và dễ dự đoán chi phí trung bình.

Phù hợp khi cần một mẫu tổng quát để quan sát luồng phổ biến. Hạn chế chính là có thể bỏ lỡ sự kiện hiếm như deadlock, lỗi kết nối đơn lẻ hoặc một truy vấn mất nhiều giây.

### Lấy mẫu theo tỷ lệ cố định (head sampling)

Quyết định lấy mẫu được đưa ra ở đầu request hoặc trace. Ví dụ, khi một request bắt đầu, SDK quyết định giữ 5% trace; quyết định đó được truyền xuống các dịch vụ và lời gọi cơ sở dữ liệu.

Head sampling có chi phí thấp vì những trace bị loại không cần được ghi đầy đủ. Tuy nhiên, quyết định được đưa ra trước khi biết request sẽ chậm hay lỗi. Nếu trace bị loại từ đầu, collector phía sau không thể khôi phục các span đã không được gửi.

Để giữ tính nhất quán, quyết định lấy mẫu nên được truyền theo trace context. Nếu mỗi dịch vụ tự quyết định độc lập, một trace có thể chỉ còn một số span rời rạc và khó giải thích.

### Lấy mẫu sau khi quan sát (tail sampling)

Tail sampling trì hoãn quyết định đến khi collector đã nhận đủ span của trace hoặc hết thời gian chờ. Collector có thể ưu tiên giữ trace có lỗi, thời gian dài, có span cơ sở dữ liệu chờ khóa hoặc thuộc nhóm nghiệp vụ quan trọng.

Cách này hữu ích khi cần giữ các trường hợp bất thường mà head sampling có thể bỏ lỡ. Đổi lại, collector phải giữ dữ liệu tạm trong bộ nhớ, chờ đủ span và xử lý nhiều trace hơn trước khi loại bỏ. Khi tải tăng, chính bộ phận tail sampling cũng có thể trở thành nút thắt.

Tail sampling chỉ có thể lựa chọn trong số trace mà nó nhận được. Nếu SDK đã loại bỏ trace ở đầu, collector không có dữ liệu để đánh giá trace đó. Một thiết kế thường dùng là giữ một tỷ lệ head đủ để collector có thể lựa chọn, đồng thời bảo đảm ngân sách collector đáp ứng được lượng dữ liệu đầu vào.

### Lấy mẫu theo tốc độ (rate limiting)

Thay vì giữ một tỷ lệ phần trăm, hệ thống đặt giới hạn như tối đa 200 sự kiện mỗi giây cho một nhóm. Cách này kiểm soát được tốc độ đầu ra khi tải tăng đột biến.

Rate limiting có thể làm tỷ lệ phần trăm thực tế thay đổi theo tải. Khi số sự kiện thấp, phần lớn hoặc tất cả sự kiện được giữ; khi số sự kiện vượt giới hạn, một số bị loại. Cần ghi lại số sự kiện bị loại và không coi dữ liệu sau giới hạn là mẫu ngẫu nhiên.

### Lấy mẫu thích ứng (adaptive sampling)

Tỷ lệ lấy mẫu thay đổi theo lưu lượng, loại sự kiện hoặc ngân sách tài nguyên. Ví dụ, hệ thống giảm tỷ lệ trace của luồng đọc phổ biến khi tải tăng, nhưng vẫn dành ngân sách cho trace lỗi và giao dịch thanh toán.

Chính sách thích ứng cần có giới hạn rõ ràng, thời gian ổn định và cơ chế chống dao động. Nếu tỷ lệ thay đổi liên tục theo tải tức thời, so sánh giữa các cửa sổ thời gian có thể khó diễn giải. Hãy xuất cả tỷ lệ lấy mẫu thực tế và số sự kiện bị loại.

## 6. Thiết kế chính sách riêng cho từng loại tín hiệu

Không nên đặt một tỷ lệ chung cho toàn bộ telemetry. Hãy xác định câu hỏi điều tra và giá trị của từng loại dữ liệu.

| Tín hiệu | Chính sách gợi ý | Lưu ý
| --- | --- | --- |
| Bộ đếm request, query và lỗi | Cập nhật đầy đủ tại nguồn, xuất giá trị tổng hợp theo chu kỳ | Tránh ghi một log cho mỗi lần tăng bộ đếm |
| Histogram độ trễ | Cập nhật histogram/sketch cho toàn bộ quan sát nếu chi phí cho phép | Không tính p95/p99 từ một tập trace đã lấy mẫu nhỏ mà không nêu sai số |
| Metrics tài nguyên máy chủ | Thu thập theo chu kỳ ổn định và giới hạn nhãn | Scrape quá dày có thể làm truy vấn hệ thống thống kê tốn tài nguyên |
| Log lỗi và timeout | Ưu tiên giữ, nhưng giới hạn tốc độ và khử trùng lặp khi lỗi lặp lại dồn dập | Đếm đầy đủ lỗi bằng metric ngay cả khi log bị giới hạn |
| Log truy vấn chậm | Giữ theo ngưỡng, lấy mẫu theo fingerprint và áp dụng giới hạn tốc độ | Tránh ghi SQL literal hoặc bind value chứa dữ liệu nhạy cảm |
| Trace thành công phổ biến | Head sampling hoặc xác suất có tỷ lệ đã công bố | Duy trì trace context xuyên suốt request |
| Trace lỗi hoặc chậm | Ưu tiên tail sampling hoặc quy tắc giữ theo điều kiện | Bảo đảm collector có đủ bộ nhớ và giới hạn thời gian chờ |
| Profiling | Lấy mẫu theo thời gian trong cửa sổ điều tra | Bật profiling chi tiết có thời hạn và đo overhead |

Chính sách giữ lỗi cần có giới hạn. Khi một lỗi xuất hiện hàng chục nghìn lần mỗi giây, giữ mọi bản ghi giống nhau có thể làm backend quá tải và che mất các sự kiện khác. Có thể giữ một số mẫu đại diện, đếm tổng số lỗi bằng metric, gom nhóm theo fingerprint và lưu một số ví dụ có ngữ cảnh.

Không nên loại bỏ toàn bộ tín hiệu lỗi để bảo vệ hệ thống giám sát. Cần duy trì một đường đếm tối thiểu, có giới hạn tài nguyên và cảnh báo khi log/trace bị loại do rate limit hoặc exporter không theo kịp.

## 7. Kiểm soát chi phí metrics và cardinality

Metrics có thể trở nên đắt đỏ khi số lượng time series tăng. Mỗi tổ hợp tên metric và nhãn có thể tạo ra một chuỗi thời gian riêng. Nếu gắn `user_id`, `order_id`, SQL literal hoặc giá trị tìm kiếm làm nhãn, số tổ hợp có thể tăng rất nhanh.

Ví dụ, metric `db_query_duration_seconds` với nhãn `query_group`, `operation` và `database` có thể có số tổ hợp hữu hạn. Nếu thêm nhãn `customer_id` với hàng triệu giá trị, hệ thống có thể tạo hàng triệu time series dù số loại truy vấn không đổi.

Hãy dùng nhãn có cardinality thấp và ổn định:

- Nhóm truy vấn đã chuẩn hóa hoặc query fingerprint.
- Loại thao tác như SELECT, INSERT, UPDATE hoặc DELETE.
- Tên cơ sở dữ liệu, cụm hoặc dịch vụ với số lượng hữu hạn.
- Kết quả thành công/thất bại hoặc nhóm mã lỗi.

Tránh đưa vào nhãn các giá trị thay đổi theo từng request như ID người dùng, ID đơn hàng, chuỗi SQL đầy đủ, tham số bind, URL có query string hoặc thông báo lỗi nguyên văn. Nếu cần điều tra một giá trị cụ thể, hãy dùng log hoặc trace có kiểm soát, che dữ liệu nhạy cảm và giới hạn lưu trữ.

Chu kỳ scrape cũng cần được chọn theo tốc độ thay đổi và chi phí truy vấn. Scrape mỗi giây không mặc nhiên tốt hơn mỗi 15 giây. Với một số view thống kê, truy vấn liên tục có thể gây tải và bản thân mẫu một giây có thể quá nhiễu. Hãy bắt đầu từ chu kỳ đủ để nhận biết sự cố cần phát hiện, sau đó đo chi phí và độ trễ cảnh báo.

## 8. Quan sát truy vấn mà không làm quá tải cơ sở dữ liệu

Thống kê truy vấn là nguồn dữ liệu quan trọng để tìm câu SQL tiêu tốn nhiều thời gian, đọc nhiều trang hoặc được gọi quá thường xuyên. Nên ưu tiên thống kê đã tổng hợp theo mẫu truy vấn thay vì lưu mọi câu lệnh đầy đủ.

Ví dụ với PostgreSQL khi extension `pg_stat_statements` đã được cài đặt và cấu hình, có thể xem các fingerprint truy vấn đang tiêu tốn thời gian thực thi tích lũy:

```sql
SELECT
    queryid,
    calls,
    total_exec_time,
    mean_exec_time,
    rows,
    shared_blks_hit,
    shared_blks_read
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 20;
```

Truy vấn này đọc số liệu đã được tổng hợp theo query identity. `total_exec_time` giúp tìm nhóm truy vấn chiếm tổng thời gian lớn; `mean_exec_time` cho biết thời gian trung bình mỗi lần; `shared_blks_read` và `shared_blks_hit` cung cấp thêm bối cảnh về truy cập block. Đây không phải danh sách đầy đủ mọi lần thực thi và cũng không cung cấp phân phối độ trễ của từng lần gọi.

Để tìm phần đuôi chậm, cần kết hợp histogram hoặc log truy vấn chậm có ngưỡng phù hợp. Có thể đặt ngưỡng log đủ cao để chỉ giữ truy vấn đáng điều tra, sau đó lấy mẫu hoặc giới hạn tốc độ theo query fingerprint. Khi cần phân tích một lần chạy cụ thể, hãy dùng trace hoặc log có chọn lọc.

Tránh chạy `EXPLAIN ANALYZE` trên mọi truy vấn đang phục vụ người dùng. Tùy hệ quản trị và câu lệnh, việc thực thi để phân tích có thể làm truy vấn chạy thật, tạo tải và có tác dụng phụ nếu câu lệnh ghi dữ liệu. Hãy dùng môi trường kiểm thử hoặc một lần tái hiện có kiểm soát; chọn kế hoạch thực thi theo cách phù hợp với hệ quản trị.

## 9. Giới hạn hàng đợi, exporter và lưu trữ

Ngay cả khi SDK đã lấy mẫu, hệ thống vẫn có thể gặp quá tải ở bước chuyển tiếp. Nếu exporter gửi chậm hơn tốc độ tạo telemetry, hàng đợi tăng dần. Hàng đợi không giới hạn có thể chiếm hết bộ nhớ; retry vô hạn có thể tạo thêm tải khi backend đang gặp sự cố.

Cần đặt các giới hạn rõ ràng:

- Kích thước hàng đợi tối đa và hành vi khi đầy.
- Timeout cho mỗi lần gửi và giới hạn số lần retry.
- Batch size và chu kỳ flush.
- Tốc độ gửi tối đa theo loại tín hiệu.
- Chính sách loại bỏ khi quá tải và bộ đếm số sự kiện bị loại.
- Giới hạn bộ nhớ và CPU cho collector.
- Thời gian lưu dữ liệu thô và chính sách giảm độ phân giải dữ liệu cũ.

Khi hàng đợi đầy, hệ thống có thể loại telemetry theo chính sách ưu tiên, nhưng không nên để việc gửi dữ liệu quan sát chặn vô thời hạn luồng request nghiệp vụ. Các exporter thường cần chạy bất đồng bộ, có timeout và có đường thoát khi backend không sẵn sàng.

Đối với cơ sở dữ liệu, nên tránh để ứng dụng chờ backend telemetry trước khi trả kết quả cho người dùng. Nếu cần lưu cục bộ tạm thời, phải giới hạn dung lượng và thời gian lưu, đồng thời quy định cách xử lý khi tiến trình khởi động lại hoặc đĩa đầy.

## 10. Kiểm soát quan sát trong các tình huống tải cao

Khi hệ thống đang chịu tải, chính sách quan sát cần chuyển sang chế độ ưu tiên tín hiệu có giá trị chẩn đoán cao. Có thể thiết kế các mức:

| Mức | Khi sử dụng | Thu thập |
| --- | --- | --- |
| Bình thường | Tải trong giới hạn và hệ thống ổn định | Metrics tổng hợp, trace thành công theo tỷ lệ, log theo mức độ |
| Cảnh báo | Độ trễ hoặc tài nguyên bắt đầu tăng | Tăng tỷ lệ trace của nhóm liên quan trong ngân sách, giữ log lỗi, lấy thêm thống kê truy vấn |
| Sự cố | Có timeout, lock wait hoặc I/O tăng mạnh | Ưu tiên trace lỗi/chậm, snapshot thống kê có giới hạn, giảm dữ liệu ít giá trị và theo dõi telemetry bị loại |
| Phục hồi | Tải và độ trễ giảm về mức ổn định | Trở về tỷ lệ bình thường từ từ, giữ lại cửa sổ dữ liệu sự cố theo thời hạn |

Việc tăng sampling khi có sự cố phải tính đến khả năng chịu tải của collector và backend. Nếu hệ thống đang phát sinh lượng trace lớn vì mỗi request đều chậm, tăng tỷ lệ giữ tất cả trace có thể làm hệ thống giám sát sụp trước khi thu được dữ liệu hữu ích.

Một cách an toàn hơn là giữ một ngân sách cố định cho mỗi nhóm, ưu tiên trace có lỗi hoặc vượt ngưỡng, và giảm mẫu của luồng thành công phổ biến. Có thể lưu snapshot thống kê truy vấn theo chu kỳ thưa hơn thay vì truy vấn view hệ thống liên tục.

## 11. Đo overhead và xác nhận chính sách

Không nên giả định rằng bật telemetry chỉ tạo ra chi phí không đáng kể. Hãy đo nó như một thay đổi hiệu năng.

Một quy trình kiểm chứng có thể thực hiện như sau:

1. **Tạo đường cơ sở.** Chạy workload đại diện khi instrumentation ở mức tối thiểu, ghi throughput, p50/p95/p99, lỗi, CPU, bộ nhớ, I/O và số kết nối.
2. **Bật metrics cơ bản.** Thu thập các bộ đếm, gauge và histogram cần thiết; chạy lại workload trong điều kiện tương đương.
3. **Bật logs có chọn lọc.** Thêm log truy vấn chậm hoặc lỗi theo ngưỡng; đo kích thước log, CPU, I/O và độ trễ.
4. **Bật tracing theo tỷ lệ.** Tăng sampling từng bước và đo số span mỗi giây, kích thước payload, CPU SDK, bộ nhớ queue và độ trễ exporter.
5. **Thử tải cao và backend chậm.** Làm cho tốc độ telemetry tăng hoặc backend nhận dữ liệu chậm để xác nhận queue, timeout, retry và drop hoạt động đúng.
6. **So sánh chất lượng tín hiệu.** Xác minh có thể phát hiện nhóm truy vấn chậm, lỗi, lock wait và I/O tăng với độ trễ cảnh báo phù hợp.
7. **Chọn ngân sách cuối.** Giữ cấu hình đáp ứng yêu cầu chẩn đoán trong giới hạn overhead đã đặt; ghi lại tỷ lệ lấy mẫu và số liệu bị loại.

Ví dụ, nếu bật tracing 100% làm CPU ứng dụng tăng 8% và p95 request tăng 12 ms trong workload mục tiêu, còn tracing 5% làm CPU tăng 1% và p95 tăng 2 ms, nhóm vận hành có thể cân nhắc 5% làm mức bình thường và dùng chính sách ưu tiên sự kiện bất thường khi có sự cố. Các con số này chỉ minh họa cách so sánh, không phải ngưỡng chung cho mọi hệ thống.

Đo riêng từng lớp nếu có thể. CPU tăng trong ứng dụng có thể do instrumentation; CPU tăng ở collector có thể do xử lý và nén; I/O tăng ở cơ sở dữ liệu có thể do truy vấn thống kê hoặc log ghi đồng bộ. Phân biệt nơi phát sinh chi phí giúp chọn đúng biện pháp.

## 12. Ví dụ chính sách quan sát cho một dịch vụ

Giả sử một dịch vụ bán hàng có các nhóm truy vấn tìm sản phẩm, xem chi tiết và đặt hàng. Một chính sách minh họa có thể là:

```yaml
observability_policy:
  metrics:
    collect_interval: 15s
    query_latency: histogram_all_requests
    labels:
      - service
      - database
      - query_fingerprint
      - operation
  traces:
    default_head_sample_rate: 0.02
    preserve_errors: true
    preserve_slow_requests: true
    slow_threshold: 500ms
    max_traces_per_second: 150
  logs:
    slow_query_threshold: 300ms
    error_rate_limit_per_second: 50
    deduplicate_repeated_messages: true
  exporter:
    queue_limit: 10000
    send_timeout: 5s
    retry_limit: 3
```

Đây là cấu hình khái niệm để minh họa các quyết định, không phải schema dùng trực tiếp cho một sản phẩm telemetry cụ thể. `preserve_errors` và `preserve_slow_requests` cần được triển khai bằng tail sampling hoặc cơ chế tương đương; head sampling đơn thuần không thể giữ lại một trace đã bị loại trước đó. Giới hạn 150 trace/giây cũng phải được phân bổ để không làm mất toàn bộ trace của nhóm nghiệp vụ quan trọng.

Trong triển khai thật, cần xác định rõ đơn vị của `slow_threshold`, nơi đánh giá ngưỡng, cách lan truyền sampling decision, thời gian chờ tail sampling và hành vi khi queue đầy. Đồng thời, bộ đếm lỗi và histogram độ trễ vẫn phải được cập nhật ngay cả khi trace tương ứng không được giữ.

## 13. Những sai lầm thường gặp

- **Lấy mẫu mọi tín hiệu theo cùng một tỷ lệ.** Metrics tổng hợp, log và trace có mục đích khác nhau; chính sách cần phù hợp với ý nghĩa dữ liệu.
- **Tính p99 từ số trace đã lấy mẫu ít.** Phần đuôi chậm có thể bị bỏ sót; dùng histogram/sketch hoặc nêu rõ giới hạn thống kê.
- **Giữ lỗi bằng head sampling.** Quyết định ở đầu request chưa biết request có lỗi hay chậm; cần cơ chế đánh giá sau khi nhận đủ trace nếu muốn ưu tiên theo kết quả.
- **Tạo nhãn theo ID hoặc SQL literal.** Cardinality tăng nhanh làm backend tốn bộ nhớ, chỉ mục và chi phí truy vấn.
- **Scrape view thống kê quá thường xuyên.** Truy vấn giám sát có thể tiêu thụ tài nguyên và làm nhiễu hệ thống đang đo.
- **Để hàng đợi telemetry không giới hạn.** Backend chậm có thể khiến tiến trình cạn bộ nhớ hoặc tăng áp lực retry.
- **Không đếm dữ liệu bị loại.** Khi sampling hoặc rate limit thay đổi, người vận hành không biết mức thiếu hụt của dữ liệu.
- **Tăng sampling không giới hạn khi có sự cố.** Collector hoặc backend có thể quá tải đúng lúc cần chúng nhất.
- **Không đo overhead.** Một chính sách quan sát có thể làm thay đổi p95, CPU hoặc I/O mà không ai nhận ra.
- **Ghi toàn bộ câu SQL và tham số.** Nội dung có thể chứa dữ liệu nhạy cảm và làm payload lớn; ưu tiên fingerprint, nhóm truy vấn và trường đã làm sạch.

## 14. Danh sách kiểm tra trước khi triển khai

- [ ] Đã xác định câu hỏi vận hành mà từng metric, log hoặc trace cần trả lời.
- [ ] Metrics quan trọng như throughput, lỗi và histogram độ trễ được tổng hợp ở nguồn.
- [ ] Chính sách lấy mẫu được định nghĩa riêng cho logs, traces và profiles.
- [ ] Có quy tắc ưu tiên lỗi, timeout và truy vấn chậm cùng giới hạn tốc độ.
- [ ] Sampling decision được truyền nhất quán trong một trace.
- [ ] Cardinality của nhãn metric được giới hạn; không dùng ID hoặc SQL literal làm nhãn.
- [ ] Chu kỳ scrape và truy vấn thống kê đã được đo overhead.
- [ ] Queue, batch, timeout, retry và drop policy đều có giới hạn.
- [ ] Có metric cho số sự kiện được giữ, bị loại và tỷ lệ sampling thực tế.
- [ ] Đã kiểm thử khi backend telemetry chậm hoặc mất kết nối.
- [ ] Đã so sánh throughput, latency, CPU, bộ nhớ và I/O trước/sau khi bật telemetry.
- [ ] Dữ liệu nhạy cảm trong log và trace được che hoặc loại bỏ.

## Kết luận

Lấy mẫu và kiểm soát chi phí giám sát giúp giữ khả năng quan sát khi cơ sở dữ liệu và ứng dụng đang chịu tải. Hãy chọn chính sách theo ý nghĩa của từng tín hiệu: duy trì metrics tổng hợp và histogram cho các chỉ số cốt lõi, lấy mẫu logs và traces theo mục tiêu điều tra, ưu tiên lỗi và request chậm bằng cơ chế phù hợp, đồng thời giới hạn cardinality, hàng đợi, tốc độ gửi và thời gian lưu trữ. Cuối cùng, đo overhead trong workload đại diện và theo dõi cả dữ liệu bị loại để bảo đảm hệ thống giám sát cung cấp tín hiệu đáng tin cậy mà không trở thành một nguồn tải mới.
