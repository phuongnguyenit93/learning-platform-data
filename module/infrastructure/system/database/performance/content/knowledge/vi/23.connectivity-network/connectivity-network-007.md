# Kích thước kết quả, truyền theo luồng và việc giữ kết nối lâu

Một truy vấn có thể chạy nhanh trong DBMS nhưng API vẫn phản hồi chậm vì phải truyền một tập kết quả lớn qua mạng, giải mã từng hàng, ánh xạ thành object và gửi tiếp đến client. Nếu driver tải toàn bộ kết quả vào RAM trước khi ứng dụng xử lý, bộ nhớ ứng dụng có thể tăng mạnh. Nếu ứng dụng đọc từng phần nhưng giữ cursor và connection quá lâu, connection pool bị chiếm dụng, transaction kéo dài và request khác phải chờ.

Trong module **DATABASE_PERFORMANCE**, tối ưu hiệu năng cần dựa trên đo đạc tải, kế hoạch thực thi, thống kê và cơ chế truy cập dữ liệu. Chương **Kết nối và mạng** giúp người học hiểu tác động của kích thước kết quả, truyền theo luồng và thời gian giữ kết nối. Bài học tập trung vào cách giảm lượng dữ liệu cần trả về, lựa chọn pagination hoặc streaming, điều chỉnh fetch size, xử lý backpressure, quản lý cursor và transaction, đồng thời đo riêng thời gian xử lý trong DBMS, thời gian truyền mạng và thời gian ứng dụng tiêu thụ kết quả.

Sau bài học, người học có thể:

- Ước lượng kích thước kết quả từ số hàng, độ rộng hàng và các cột được chọn.
- Giải thích vì sao SELECT * và cột LOB lớn làm tăng RAM, I/O và thời gian truyền.
- Phân biệt tải toàn bộ kết quả, fetch theo lô, cursor streaming và pagination.
- Chọn fetch size dựa trên latency mạng, row width, bộ nhớ và thời gian xử lý của client.
- Nhận diện backpressure khi ứng dụng đọc kết quả chậm hơn tốc độ DBMS tạo dữ liệu.
- Hiểu tác động của cursor và transaction dài đến connection pool, snapshot, lock và vacuum/undo.
- Thiết kế connection pool, timeout và giới hạn số stream đồng thời.
- Đánh giá TCP/TLS, round trip, compression, batching và N+1 query.
- Đo thời gian execute, thời gian fetch, số byte truyền, bộ nhớ client và thời gian giữ connection.
- Chọn cách xuất dữ liệu lớn an toàn mà vẫn đáp ứng yêu cầu nghiệp vụ.

## 1. Kích thước kết quả là một phần của chi phí truy vấn

### 1.1. Thời gian truy vấn không kết thúc khi DBMS tìm được hàng

Một request đọc dữ liệu thường đi qua nhiều giai đoạn:

1. Ứng dụng gửi SQL và tham số qua driver.
2. DBMS parse, lập kế hoạch và thực thi.
3. DBMS tạo các hàng kết quả.
4. Driver nhận dữ liệu qua giao thức mạng.
5. Driver giải mã kiểu dữ liệu và tạo cấu trúc hàng.
6. Ứng dụng đọc, chuyển đổi hoặc xử lý từng hàng.
7. Ứng dụng tuần tự hóa kết quả và gửi tiếp đến người dùng hoặc dịch vụ khác.

Thời gian người dùng quan sát có thể biểu diễn khái quát:

\[
T_{end-to-end} =
T_{queue} + T_{execute} + T_{fetch} +
T_{decode} + T_{application} + T_{response}
\]

Các giai đoạn có thể chồng lấp khi streaming hoặc pipeline hoạt động. Công thức giúp phân loại nơi tiêu tốn thời gian, không phải phép cộng chính xác trong mọi driver.

Nếu chỉ đo thời gian execute ở DBMS, có thể bỏ qua phần fetch và xử lý client. Một truy vấn trả 10 hàng có thể hoàn thành nhanh; truy vấn trả 5 triệu hàng có thể mất nhiều phút để truyền và tiêu thụ dù execution plan không có nút thắt rõ ràng.

### 1.2. Số hàng và độ rộng hàng

Kích thước kết quả phụ thuộc cả số hàng lẫn số byte trung bình mỗi hàng.

Mô hình ước lượng:

\[
ResultBytes \approx RowCount \times AverageRowWidth
\]

Ví dụ, truy vấn trả 2 triệu hàng với độ rộng trung bình 600 byte tạo khoảng 1,2 GB dữ liệu thô trước khi tính overhead của giao thức, metadata, object trong ứng dụng và định dạng JSON/CSV.

Độ rộng thực tế có thể khác độ dài khai báo của cột. VARCHAR(500) không có nghĩa mỗi hàng luôn chiếm 500 byte; cần đo phân bố dữ liệu thật. Ngược lại, một cột JSON, TEXT, XML hoặc BLOB có thể chứa payload lớn và làm kích thước hàng tăng đột biến.

Khi ước lượng, hãy xem:

- Số hàng thực tế sau filter.
- Độ dài trung bình và percentile cao của từng cột.
- Encoding và charset.
- Giá trị NULL và overhead biểu diễn.
- Kiểu dữ liệu LOB có được truyền inline hay theo cơ chế riêng.
- Overhead protocol, driver và object serialization.

### 1.3. SELECT * có thể làm tăng chi phí nhiều lần

Ví dụ:

~~~sql
SELECT *
FROM orders
WHERE tenant_id = :tenant_id
  AND created_at >= :start_time
  AND created_at < :end_time;
~~~

Nếu ứng dụng chỉ cần order_id, created_at và status, việc lấy thêm payload, notes, JSON hoặc các cột LOB làm tăng:

- Số byte DBMS phải đọc hoặc truy cập.
- Số byte gửi qua mạng.
- RAM driver dùng để giữ các hàng.
- RAM ứng dụng dùng để tạo object.
- Thời gian giải mã, ánh xạ và tuần tự hóa.
- Áp lực garbage collection hoặc cấp phát bộ nhớ.
- Thời gian connection phải phục vụ request.

Nên liệt kê đúng cột cần thiết:

~~~sql
SELECT order_id, created_at, status
FROM orders
WHERE tenant_id = :tenant_id
  AND created_at >= :start_time
  AND created_at < :end_time;
~~~

Projection hợp lý có thể giảm cả I/O trong DBMS lẫn chi phí mạng. Với index bao phủ, DBMS đôi khi còn tránh được việc truy cập bảng đầy đủ; điều đó phụ thuộc index và execution plan.

### 1.4. Một cột lớn có thể chi phối toàn bộ kết quả

Giả sử mỗi hàng có order_id, created_at, status, description trung bình 2 KB và document_blob trung bình 200 KB. Nếu API chỉ hiển thị mã đơn và trạng thái nhưng vẫn lấy document_blob, payload có thể tăng hàng trăm lần. Hãy tách metadata thường xuyên đọc khỏi nội dung lớn hoặc chỉ tải nội dung khi người dùng mở chi tiết.

Với LOB, có thể dùng truy vấn hai bước: lấy danh sách ID và metadata trước, sau đó lấy nội dung lớn theo ID khi thực sự cần. Cần tránh N+1 request khi tải từng LOB; có thể batch theo nhóm ID hoặc dùng endpoint tải riêng có giới hạn.

### 1.5. Chi phí phía client cũng tăng theo số hàng

Một hàng trong ResultSet không chỉ chiếm đúng số byte trên wire. Driver có thể tạo object, buffer và metadata; ứng dụng có thể ánh xạ thành entity, DTO, map hoặc JSON object. Overhead heap của object thường lớn hơn dữ liệu thô.

Ví dụ, 1 triệu hàng có payload 200 byte không đồng nghĩa ứng dụng chỉ cần 200 MB heap. Nếu mỗi hàng tạo nhiều object và chuỗi riêng, tổng heap có thể lớn hơn đáng kể. Cần đo heap allocation và peak memory trong runtime thực tế.

## 2. Giảm lượng dữ liệu trước khi tối ưu truyền

### 2.1. Lọc tại DBMS

Nếu client chỉ cần dữ liệu của một tenant hoặc một khoảng thời gian, hãy đưa predicate vào SQL để DBMS loại hàng trước khi gửi:

~~~sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE tenant_id = :tenant_id
  AND created_at >= :from_time
  AND created_at < :to_time
  AND status = 'PAID';
~~~

Lọc tại DBMS thường giảm số hàng truyền qua mạng và lượng dữ liệu ứng dụng phải xử lý. Cần bảo đảm predicate có access path phù hợp và không làm sai semantics.

### 2.2. Tổng hợp ở nơi dữ liệu đang nằm

Nếu ứng dụng chỉ cần tổng doanh thu theo ngày, không nên tải từng dòng đơn hàng rồi cộng trong application:

~~~sql
SELECT
    CAST(created_at AS DATE) AS order_day,
    SUM(total_amount) AS revenue,
    COUNT(*) AS order_count
FROM orders
WHERE tenant_id = :tenant_id
  AND created_at >= :from_time
  AND created_at < :to_time
GROUP BY CAST(created_at AS DATE)
ORDER BY order_day;
~~~

DBMS trả số dòng tổng hợp nhỏ hơn nhiều. Tuy nhiên, cần kiểm tra expression trên cột ngày, index và partition key nếu có; có thể lọc bằng khoảng trực tiếp trên timestamp rồi chỉ chuyển ngày ở phần group.

Tổng hợp trong DBMS có thể tăng CPU hoặc workspace của query. Dù vậy, khi kết quả cuối nhỏ hơn rất nhiều so với dữ liệu đầu vào, giảm network transfer và client processing thường có lợi.

### 2.3. Chỉ trả trường phục vụ màn hình hiện tại

Một API danh sách thường chỉ cần một tập cột nhỏ. Không nên dùng cùng truy vấn chi tiết cho cả trang danh sách và trang xem một bản ghi.

Có thể tách:

- List endpoint: ID, tên, trạng thái, thời gian và vài trường hiển thị.
- Detail endpoint: trường đầy đủ và LOB.
- Export endpoint: luồng tải dữ liệu lớn có giới hạn riêng.

Cách tách này giúp mỗi luồng có ngân sách payload, timeout và concurrency phù hợp.

### 2.4. Tránh N+1 query

N+1 xảy ra khi ứng dụng đọc N hàng rồi gửi thêm một truy vấn cho mỗi hàng để lấy dữ liệu liên quan. Ví dụ, lấy 500 khách hàng rồi gọi một query riêng để lấy số đơn của từng người tạo 501 round trip.

Thay vì:

~~~text
1 query lấy 500 khách hàng
500 query lấy thông tin đơn hàng cho từng khách hàng
Tổng: 501 query/round trip logic
~~~

Có thể dùng JOIN, aggregate hoặc batch query:

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    COUNT(o.order_id) AS order_count
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.customer_id
WHERE c.region_id = :region_id
GROUP BY c.customer_id, c.customer_name;
~~~

JOIN có thể tạo duplicate hoặc fanout nếu grain không được xác định rõ. Phải giữ đúng ngữ nghĩa và xem execution plan. Một cách khác là lấy danh sách ID rồi truy vấn theo nhóm với WHERE customer_id IN (...), có giới hạn kích thước batch và xử lý parameter limit của DBMS.

### 2.5. Batching giảm round trip nhưng không nên tạo batch quá lớn

Gửi một batch gồm nhiều thao tác có thể giảm network round trip và overhead parse/execute. Nhưng batch quá lớn có thể:

- Giữ nhiều dữ liệu trong RAM client.
- Tạo transaction dài.
- Giữ lock hoặc version cũ lâu hơn.
- Tăng log và rollback cost.
- Tạo burst I/O và CPU.
- Làm timeout hoặc retry trở nên tốn kém.

Chọn batch size dựa trên số hàng, kích thước payload, latency mạng và khả năng rollback. Với import/export, xử lý theo batch có checkpoint thường dễ phục hồi hơn một transaction khổng lồ.

## 3. Tải toàn bộ, fetch theo lô và streaming

### 3.1. Tải toàn bộ kết quả (buffered result)

Một số driver hoặc API tải toàn bộ kết quả vào client trước khi trả quyền điều khiển cho ứng dụng. Cách này đơn giản: sau khi query hoàn thành, ứng dụng có thể duyệt kết quả nhiều lần mà không giữ connection cho mỗi lần đọc.

Nhược điểm:

- Peak memory tăng theo kích thước toàn bộ kết quả.
- Thời gian chờ trước khi ứng dụng bắt đầu xử lý có thể dài.
- Một kết quả lớn có thể gây GC pressure hoặc OutOfMemoryError.
- Nhiều request buffered đồng thời làm RAM client tăng theo concurrency.

Buffered result phù hợp với tập kết quả nhỏ, có giới hạn rõ ràng và cần truy cập nhiều lần. Không nên dùng mặc định cho hàng triệu hàng hoặc payload LOB lớn.

### 3.2. Fetch theo lô (fetch size)

Fetch size điều khiển số hàng driver yêu cầu hoặc nhận trong một lần lấy dữ liệu, tùy driver và chế độ cursor. Thay vì lấy toàn bộ kết quả, driver nhận một batch, ứng dụng xử lý rồi lấy batch tiếp theo.

Fetch size nhỏ:

- Giảm lượng dữ liệu giữ cùng lúc.
- Có thể tăng số lần round trip.
- Có thể làm tăng chi phí giao thức và latency mạng.

Fetch size lớn:

- Giảm số lần round trip.
- Có thể tăng throughput khi mạng có latency cao.
- Tăng RAM phía driver và ứng dụng.
- Có thể làm client giữ connection lâu hơn nếu xử lý mỗi batch chậm.

Fetch size là một tham số đánh đổi, không có giá trị tối ưu chung. Cần điều chỉnh theo row width và latency thực tế.

### 3.3. Streaming bằng cursor

Streaming cho phép ứng dụng đọc kết quả từng phần thay vì materialize toàn bộ trong bộ nhớ client. Driver có thể dùng server-side cursor, protocol portal hoặc cơ chế fetch nội bộ. Chi tiết phụ thuộc DBMS và driver.

Mô hình khái quát:

~~~text
Ứng dụng gửi query
      |
      v
DBMS thực thi và chuẩn bị kết quả
      |
      v
Driver nhận một batch
      |
      v
Ứng dụng xử lý từng hàng trong batch
      |
      v
Driver yêu cầu batch tiếp theo
      |
      v
Lặp cho đến hết kết quả
~~~

Streaming giúp giới hạn peak memory phía client, nhưng thường giữ statement, cursor và connection trong suốt quá trình đọc. Nếu cursor phụ thuộc transaction, transaction cũng có thể phải mở lâu.

### 3.4. Streaming không có nghĩa DBMS luôn tạo từng hàng đúng lúc

Một truy vấn có ORDER BY, DISTINCT, GROUP BY, hash join hoặc window function có thể cần xử lý nhiều hoặc toàn bộ đầu vào trước khi trả hàng đầu tiên. Driver streaming không loại bỏ workspace hoặc sort trong DBMS.

Cần phân biệt:

- Streaming ở tầng driver: client nhận từng phần.
- Pipeline trong execution plan: các node có thể truyền hàng liên tục.
- Blocking operator: node cần tích lũy hoặc sắp xếp dữ liệu trước khi phát kết quả.

Nếu query có blocking operator, thời gian đến hàng đầu tiên (time to first row) vẫn có thể cao dù client dùng cursor.

### 3.5. Chọn giữa buffered và streaming

| Tiêu chí | Buffered result | Fetch theo lô/streaming |
|---|---|---|
| Peak RAM client | Tăng theo toàn bộ kết quả | Thường giới hạn theo batch và object đang xử lý |
| Round trip | Có thể ít hơn sau khi tải | Có thể nhiều lần fetch |
| Bắt đầu xử lý | Có thể phải chờ tải nhiều dữ liệu | Có thể xử lý sau batch đầu |
| Thời gian giữ connection | Có thể ngắn hơn nếu tải xong nhanh | Có thể kéo dài suốt lúc client đọc |
| Độ phức tạp | Đơn giản | Cần đóng cursor và xử lý lỗi giữa luồng |
| Phù hợp | Kết quả nhỏ, bounded | Kết quả lớn, xử lý tuần tự hoặc export |

## 4. Fetch size và độ trễ mạng

### 4.1. Round trip có chi phí cố định

Một lần fetch thường có overhead giao thức và latency mạng. Nếu fetch size quá nhỏ, driver phải gửi nhiều request để lấy hết dữ liệu.

Ví dụ, kết quả có 100.000 hàng:

- Fetch size 100: khoảng 1.000 lần lấy batch.
- Fetch size 1.000: khoảng 100 lần.
- Fetch size 5.000: khoảng 20 lần.

Đây là phép chia lý tưởng hóa; driver có thể fetch thêm, prefetch hoặc thay đổi cách truyền theo protocol. Số round trip thực tế cần đo bằng driver metrics hoặc network tracing.

Nếu RTT giữa ứng dụng và DBMS là 5 ms, 1.000 lượt fetch tuần tự có thể thêm đáng kể thời gian chờ. Tăng batch size có thể giảm round trip, nhưng cần tính số byte mỗi batch và RAM.

### 4.2. Ước lượng kích thước batch

Một ước lượng:

\[
BatchMemory \approx FetchSize \times AverageRowWidth
\]

Nếu fetch size là 2.000 hàng và độ rộng trung bình 1,5 KB, payload thô một batch khoảng 3 MB. Driver và object mapping có thể cần nhiều hơn mức này.

Nếu 20 stream đồng thời, mỗi stream giữ 3 MB payload thô thì riêng phần batch đã khoảng 60 MB, chưa tính overhead. Hãy dùng row width p95 nếu dữ liệu có độ lệch lớn, không chỉ average.

### 4.3. Tối ưu theo băng thông và latency

Trên mạng có latency cao nhưng băng thông tốt, batch lớn hơn có thể tăng throughput bằng cách giảm round trip. Trên mạng hạn chế băng thông hoặc client có RAM nhỏ, batch nhỏ hơn có thể giúp kiểm soát peak memory và tránh buffer quá lớn.

Cần đo:

- RTT giữa ứng dụng và DBMS.
- Throughput mạng.
- Số byte nhận/gửi.
- Số fetch round trip.
- Batch size thực tế.
- Thời gian decode và xử lý mỗi batch.
- Thời gian connection bị giữ.
- Peak heap của client.

Không tăng fetch size chỉ vì truy vấn có nhiều hàng. Nếu mỗi hàng có LOB 1 MB, batch 1.000 hàng có thể tạo payload cỡ 1 GB.

### 4.4. Prefetch và pipelining

Một số driver có thể prefetch batch tiếp theo trong khi ứng dụng xử lý batch hiện tại hoặc dùng cơ chế pipelining. Điều này có thể che latency mạng nhưng tăng số buffer đang tồn tại và phức tạp hóa backpressure.

Cần đọc tài liệu driver cụ thể. Không giả định fetch size đồng nghĩa với số hàng chính xác được giữ trong RAM hoặc số round trip cố định.

## 5. Backpressure: khi client tiêu thụ chậm

### 5.1. Backpressure là gì?

Backpressure xảy ra khi phía tiêu thụ không xử lý dữ liệu nhanh bằng phía tạo hoặc truyền dữ liệu. Với truy vấn DB, DBMS/driver có thể tạo kết quả nhanh nhưng ứng dụng đọc, chuyển đổi hoặc ghi tiếp chậm.

Ví dụ:

- DBMS tạo 20.000 hàng/giây.
- Mạng truyền được 15.000 hàng/giây.
- Ứng dụng chỉ xử lý được 5.000 hàng/giây.

Nếu các tầng buffer không có giới hạn, dữ liệu chờ có thể tích lũy và làm RAM tăng. Nếu buffer có giới hạn, producer phải chờ hoặc bị điều tiết. Trong một luồng JDBC đồng bộ, ứng dụng đọc chậm thường khiến lần fetch tiếp theo bị trì hoãn; cursor và connection vẫn bị giữ.

### 5.2. Tác động đến DBMS và connection pool

Một stream đọc chậm có thể:

- Giữ connection trong thời gian dài.
- Giữ cursor và statement mở.
- Giữ transaction hoặc snapshot lâu nếu cursor cần transaction.
- Làm connection pool hết slot.
- Tăng thời gian chờ của request mới.
- Giữ tài nguyên server-side liên quan đến cursor hoặc query.
- Làm tăng độ trễ của các thao tác phụ thuộc cùng transaction.

Không phải mọi DBMS đều giữ lock cho một SELECT streaming theo cùng cách. Snapshot, MVCC, isolation level và cursor semantics quyết định loại tài nguyên bị giữ. Hãy xác định engine và chế độ transaction cụ thể.

### 5.3. Buffer có giới hạn

Trong pipeline ứng dụng, nên dùng bounded queue hoặc buffer giới hạn thay vì unbounded queue. Khi consumer chậm, producer phải chờ hoặc giảm tốc, thay vì tiếp tục giữ dữ liệu trong heap.

Ví dụ pseudocode:

~~~java
BlockingQueue<RowBatch> queue =
    new ArrayBlockingQueue<>(4);

// Producer đọc tối đa 4 batch đang chờ.
// Consumer xử lý và giải phóng batch trước khi producer tiếp tục.
~~~

Đây là minh họa mô hình điều phối, không phải đoạn chương trình đầy đủ. Cần xử lý lỗi, cancellation, đóng cursor và shutdown để producer không bị treo khi consumer dừng.

### 5.4. Hủy luồng khi client bỏ request

Nếu client ngắt kết nối hoặc người dùng rời trang, ứng dụng cần hủy công việc đang chạy:

1. Đánh dấu request bị hủy.
2. Dừng đọc thêm hàng.
3. Hủy statement nếu driver/DBMS hỗ trợ.
4. Đóng ResultSet/cursor và statement.
5. Rollback transaction nếu transaction được mở cho tác vụ đó.
6. Trả connection về pool sau khi xác nhận trạng thái sạch.

Không trả connection về pool khi cursor hoặc transaction vẫn còn mở. Một connection bẩn có thể làm request tiếp theo gặp lỗi, giữ tài nguyên hoặc đọc trạng thái session không mong muốn.

## 6. Cursor và thời gian giữ kết nối

### 6.1. Cursor thường gắn với connection

Server-side cursor thường được tạo trong session/connection cụ thể. Ứng dụng phải tiếp tục dùng connection đó để fetch các batch tiếp theo. Không thể tùy ý lấy batch đầu trên connection A rồi lấy batch sau trên connection B, trừ khi hệ thống có cơ chế riêng hỗ trợ.

Vì vậy, streaming giúp giảm RAM client nhưng có thể làm connection bị chiếm dụng lâu hơn. Nếu ứng dụng đọc một triệu hàng và xử lý từng hàng trong vài phút, connection có thể bị giữ trong suốt thời gian đó.

### 6.2. Connection pool có số slot hữu hạn

Giả sử pool có 40 connection. Nếu 30 connection bị các stream export giữ trong 2 phút, chỉ còn 10 slot phục vụ request OLTP. Khi lượng request tăng, thời gian chờ lấy connection có thể tăng dù DBMS còn CPU và RAM.

Cần theo dõi:

- Active, idle và pending connection.
- Thời gian chờ acquire connection.
- Thời gian giữ connection.
- Số stream đang mở.
- Thời gian fetch từng batch.
- Số transaction/cursor đang tồn tại.
- Số request bị timeout khi chờ pool.

Không chỉ đặt pool size lớn hơn để giải quyết hàng đợi. Pool lớn hơn có thể cho phép nhiều query đồng thời hơn, tăng memory pressure và tải DBMS.

### 6.3. Giữ transaction lâu có thể gây tác động khác nhau theo engine

Một transaction đọc dài có thể giữ snapshot cũ hoặc ảnh hưởng việc dọn dẹp phiên bản dữ liệu:

- PostgreSQL: transaction/snapshot lâu có thể giữ xmin cũ, làm vacuum không thể loại bỏ một số tuple dead và góp phần gây table/index bloat.
- MySQL InnoDB: read view lâu có thể giữ các phiên bản cũ trong undo history, làm purge chậm dọn.
- Oracle: consistent read dựa trên undo; transaction đọc lâu có thể làm tăng nhu cầu giữ undo và gặp rủi ro snapshot too old nếu undo không còn đủ.
- SQL Server: tác động phụ thuộc isolation level và row versioning; transaction dài trong chế độ dùng version store có thể giữ version lâu hơn, đồng thời lock-based isolation có thể giữ lock tùy truy vấn.

Một SELECT dài không tự động giữ mọi row lock trong mọi engine. Phải xem isolation level, cursor type và transaction semantics trước khi kết luận.

### 6.4. Cursor đóng muộn

Các lỗi thường gặp:

- Không đóng ResultSet trong mọi nhánh lỗi.
- Giữ transaction mở trong khi ứng dụng gọi dịch vụ ngoài.
- Stream kết quả trực tiếp cho HTTP client nhưng không xử lý client disconnect.
- Dùng connection trong một callback kéo dài sau khi query đã hoàn tất.
- Để cursor mở trong lúc người dùng tải từng phần chậm.

Hãy đóng tài nguyên bằng try-with-resources hoặc cơ chế tương đương, đặt timeout và tách thời gian xử lý ngoài DB khỏi transaction nếu có thể.

## 7. Pagination hay streaming?

### 7.1. Pagination theo yêu cầu người dùng

Pagination phù hợp khi người dùng chỉ xem từng trang nhỏ và có thể quay lại sau. API có thể trả 20 hoặc 50 hàng mỗi request, sau đó client yêu cầu trang tiếp theo.

OFFSET/LIMIT đơn giản nhưng offset lớn có thể khiến DBMS phải bỏ qua nhiều hàng. Keyset pagination dùng giá trị khóa cuối trang trước để tiếp tục, thường ổn định hơn với dữ liệu lớn khi có index hỗ trợ.

Ví dụ keyset theo thời gian và ID:

~~~sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE tenant_id = :tenant_id
  AND (
       created_at < :last_created_at
       OR (created_at = :last_created_at AND order_id < :last_order_id)
  )
ORDER BY created_at DESC, order_id DESC
LIMIT 50;
~~~

Trang đầu bỏ điều kiện cursor; các trang sau bind hai giá trị cuối trang trước. Index phù hợp có thể là (tenant_id, created_at DESC, order_id DESC), tùy DBMS.

### 7.2. Streaming phù hợp với xử lý tuần tự lớn

Streaming phù hợp khi cần xử lý toàn bộ tập dữ liệu nhưng không cần giữ tất cả trong RAM:

- Export dữ liệu.
- Tạo file báo cáo.
- Đồng bộ dữ liệu sang hệ thống khác.
- Tính toán theo luồng.
- Xử lý batch tuần tự.

Nếu người dùng chỉ cần một trang, streaming toàn bộ bảng là lãng phí. Nếu tác vụ cần mọi hàng, pagination theo nhiều request có thể tạo nhiều round trip và khó giữ snapshot nhất quán; cursor streaming có thể phù hợp hơn nếu transaction lifetime được kiểm soát.

### 7.3. Keyset không tự giải quyết mọi vấn đề

Keyset pagination cần thứ tự ổn định và khóa cursor duy nhất. Nếu sắp xếp theo một cột không duy nhất, thêm tie-breaker. Nếu dữ liệu thay đổi giữa các request, hàng có thể dịch chuyển theo thứ tự hoặc xuất hiện trùng/thiếu tùy semantics.

Nếu cần snapshot nhất quán qua nhiều trang, phải xác định cách giữ snapshot hoặc dùng một mốc dữ liệu cố định. Giữ transaction mở xuyên suốt thời gian người dùng đọc từng trang có thể tạo vấn đề lâu dài; một watermark hoặc snapshot export có thể phù hợp hơn tùy nghiệp vụ.

### 7.4. Export rất lớn có thể cần job bất đồng bộ

Với hàng chục triệu hàng, giữ HTTP request và DB connection mở cho đến khi người dùng tải xong có thể không phù hợp. Một mô hình khác:

1. Người dùng tạo yêu cầu export.
2. Hệ thống xếp job vào queue.
3. Worker đọc dữ liệu theo batch/cursor có giới hạn.
4. Worker ghi file vào object storage hoặc kho tệp.
5. Job cập nhật trạng thái và thời hạn tải.
6. Người dùng tải file sau khi hoàn tất.

Mô hình này tách thời gian DB connection khỏi tốc độ tải của trình duyệt. Cần kiểm soát quyền truy cập file, thời hạn lưu trữ, retry, checkpoint và giới hạn concurrency của worker.

## 8. Ví dụ theo driver và DBMS

Các API fetch size và cursor không đồng nhất giữa driver. Hãy kiểm tra đúng phiên bản driver, cấu hình auto-commit, prepared statement và protocol đang dùng.

### 8.1. JDBC: đọc ResultSet theo lô

Ví dụ Java tổng quát:

~~~java
String sql = """
    SELECT order_id, created_at, total_amount
    FROM orders
    WHERE tenant_id = ?
    ORDER BY order_id
    """;

try (Connection connection = dataSource.getConnection();
     PreparedStatement statement =
         connection.prepareStatement(
             sql,
             ResultSet.TYPE_FORWARD_ONLY,
             ResultSet.CONCUR_READ_ONLY)) {

    statement.setLong(1, tenantId);
    statement.setFetchSize(500);

    try (ResultSet resultSet = statement.executeQuery()) {
        while (resultSet.next()) {
            long orderId = resultSet.getLong("order_id");
            Timestamp createdAt = resultSet.getTimestamp("created_at");
            BigDecimal total = resultSet.getBigDecimal("total_amount");

            process(orderId, createdAt, total);
        }
    }
}
~~~

Đây là mẫu minh họa. setFetchSize(500) là gợi ý cho driver, không phải bảo đảm mọi driver sẽ dùng server-side cursor hoặc chỉ giữ đúng 500 hàng. Cần xác minh hành vi qua tài liệu và phép đo.

### 8.2. PostgreSQL JDBC

Với PostgreSQL JDBC, cursor-based fetching thường cần:

- ResultSet forward-only.
- Fetch size dương.
- Auto-commit tắt trong thời gian đọc cursor.
- Transaction vẫn mở trong lúc fetch.

Ví dụ:

~~~java
connection.setAutoCommit(false);

try (PreparedStatement statement = connection.prepareStatement(
        sql,
        ResultSet.TYPE_FORWARD_ONLY,
        ResultSet.CONCUR_READ_ONLY)) {

    statement.setFetchSize(1000);

    try (ResultSet rs = statement.executeQuery()) {
        while (rs.next()) {
            processRow(rs);
        }
    }

    connection.commit();
} catch (Exception e) {
    connection.rollback();
    throw e;
}
~~~

Khi dùng cursor, transaction được giữ đến khi hoàn tất fetch và commit/rollback. Hãy tránh thực hiện công việc ngoài DB chậm bên trong vòng lặp nếu điều đó kéo dài snapshot. Cấu hình và hành vi cụ thể cần kiểm tra với phiên bản pgJDBC đang dùng.

### 8.3. MySQL Connector/J

MySQL Connector/J có nhiều chế độ buffering và cursor fetch. Trong một số cấu hình, driver mặc định buffer toàn bộ ResultSet. Cursor-based fetching với server-side prepared statement có thể cần cấu hình useCursorFetch=true, bật server-side prepared statements và đặt fetch size dương. Hành vi cụ thể phụ thuộc phiên bản Connector/J và kiểu statement.

Không giả định chỉ gọi setFetchSize() là đủ. Kiểm tra cấu hình driver, memory profile và số round trip. Một số chế độ streaming đặc thù có giới hạn về việc thực hiện query khác trên cùng connection khi ResultSet chưa được đọc hết.

### 8.4. SQL Server JDBC

SQL Server JDBC driver hỗ trợ các cơ chế buffering và adaptive buffering cho kết quả, cùng các tùy chọn fetch size. Cần xem tài liệu driver để biết cách áp dụng với kiểu dữ liệu lớn và ResultSet cụ thể.

Nếu dùng adaptive buffering, driver có thể đọc dữ liệu theo nhu cầu thay vì giữ toàn bộ hàng trong bộ nhớ. Tuy nhiên, ResultSet vẫn giữ connection và statement cho đến khi đóng. Hãy đo thời gian giữ connection và hành vi khi client đọc chậm.

### 8.5. Oracle JDBC

Oracle JDBC cung cấp row prefetch/fetch size để điều chỉnh số hàng được lấy mỗi lượt. Tăng prefetch có thể giảm round trip nhưng tăng bộ nhớ và có thể làm tăng lượng dữ liệu đọc trước khi ứng dụng cần.

Với LOB, streaming qua locator hoặc API đọc theo chunk có thể phù hợp hơn việc materialize toàn bộ nội dung. Cần kiểm tra semantics transaction và thời gian giữ connection trong khi đọc LOB.

### 8.6. Driver-specific behavior phải được đo

Một thiết lập tên giống nhau có thể có semantics khác nhau giữa các driver. Cần ghi lại:

- Driver name và version.
- Protocol mode.
- Auto-commit và transaction isolation.
- Fetch size/prefetch.
- Server-side cursor có thực sự được dùng không.
- Buffered hay adaptive result mode.
- Số fetch round trip.
- Peak memory client và thời gian giữ connection.

## 9. Mạng, giao thức và mã hóa

### 9.1. Throughput và round trip là hai giới hạn khác nhau

Một kết nối mạng có thể có băng thông cao nhưng latency lớn. Nếu ứng dụng thực hiện nhiều lượt fetch nhỏ tuần tự, latency có thể chi phối tổng thời gian dù tổng số byte không lớn.

Ngược lại, một batch rất lớn có thể giảm số round trip nhưng bị giới hạn bởi throughput hoặc làm tăng thời gian giữ buffer.

Cần phân biệt:

- Latency: thời gian một lần trao đổi.
- Throughput: lượng dữ liệu truyền mỗi giây.
- Bandwidth: năng lực tối đa của đường truyền.
- RTT: thời gian khứ hồi của gói/trao đổi.
- Packet loss và retransmission: có thể làm giảm throughput.
- Connection setup: DNS, TCP handshake, TLS handshake và authentication.

Tái sử dụng connection qua pool có thể giảm chi phí thiết lập kết nối, nhưng connection idle cần timeout và validation phù hợp.

### 9.2. TLS và mã hóa

TLS bảo vệ dữ liệu trên đường truyền nhưng có chi phí CPU và một số overhead giao thức. Với kết nối được tái sử dụng, handshake không xảy ra cho mỗi query. Khi mở quá nhiều connection ngắn hạn, chi phí handshake và authentication có thể đáng kể.

Không tắt TLS chỉ để giảm latency nếu dữ liệu cần được bảo vệ. Hãy đo CPU, handshake rate, connection churn và latency trước khi tối ưu reuse hoặc cấu hình TLS.

### 9.3. Compression

Nén có thể giảm số byte truyền, đặc biệt với JSON, văn bản hoặc payload lặp. Nhưng compression tiêu thụ CPU và có thể tăng latency nếu dữ liệu nhỏ hoặc CPU đã bão hòa.

Cần xem:

- Tỷ lệ nén thực tế.
- CPU ở DBMS, proxy và client.
- Số byte trước/sau nén.
- Kích thước batch.
- Latency end-to-end.
- Khả năng nén của giao thức/driver/proxy đang dùng.

Không phải mọi giao thức database đều hỗ trợ compression theo cùng cách. Một số engine có tùy chọn compression ở protocol; một số workload có thể nén ở tầng ứng dụng hoặc gateway.

### 9.4. Connection reuse và keepalive

Connection pool giúp tránh thiết lập TCP/TLS/authentication cho mỗi request. Nhưng giữ quá nhiều connection idle có overhead và có thể vượt giới hạn server hoặc proxy.

TCP keepalive giúp phát hiện một số connection chết sau thời gian idle, nhưng không thay thế validation của pool, query timeout hoặc transaction timeout. Cần cấu hình idle timeout, max lifetime và keepalive theo chính sách mạng, firewall, load balancer và DBMS.

### 9.5. Gần DBMS hơn có thể giảm latency mạng

Nếu ứng dụng và DBMS ở vùng mạng khác nhau, mỗi round trip có thể tốn nhiều thời gian hơn. Đặt service gần DBMS hoặc dùng tầng xử lý dữ liệu gần nguồn có thể giảm latency và chi phí truyền.

Nhưng thay đổi topology cần cân nhắc độ sẵn sàng, bảo mật, replication, data locality và chi phí vận hành. Không phải lúc nào di chuyển ứng dụng cũng khả thi; batching và giảm số round trip có thể là bước tối ưu ít thay đổi hơn.

## 10. Connection pool và timeout cho luồng dài

### 10.1. Tách pool theo loại workload

Một pool chung có thể bị các export hoặc báo cáo dài chiếm hết connection. Có thể dùng pool hoặc quota riêng cho:

- OLTP request ngắn.
- Báo cáo.
- Export/stream.
- Job nền và batch.
- Tác vụ quản trị.

Tách pool không tạo thêm tài nguyên DBMS. Tổng connection tối đa của tất cả pool vẫn phải nằm trong ngân sách server và giới hạn workload.

### 10.2. Giới hạn stream đồng thời

Nếu mỗi stream giữ một connection trong 90 giây, 20 stream có thể giữ 20 slot gần một phút rưỡi. Một pool 30 connection chỉ còn 10 slot cho request khác.

Có thể đặt semaphore hoặc quota cho export:

~~~text
Nếu số export đang chạy < giới hạn:
    nhận job và mở cursor
Ngược lại:
    xếp job vào hàng đợi hoặc trả trạng thái chờ
Khi export kết thúc:
    đóng cursor, transaction và connection
    giải phóng slot
~~~

Giới hạn cần dựa trên thời gian giữ connection, memory workspace, I/O và SLO của workload tương tác.

### 10.3. Phân biệt các loại timeout

Các timeout có ý nghĩa khác nhau:

- Connection timeout: thời gian tối đa để thiết lập kết nối.
- Pool acquire timeout: thời gian chờ lấy connection từ pool.
- Query/statement timeout: thời gian cho phép câu lệnh chạy.
- Socket/network timeout: thời gian chờ dữ liệu trên socket.
- Transaction timeout: thời gian tối đa giữ transaction nếu framework/DBMS hỗ trợ.
- Idle-in-transaction timeout: giới hạn transaction mở nhưng không hoạt động ở một số DBMS.
- HTTP/request timeout: thời gian request ở tầng ứng dụng.

Đặt timeout đồng bộ và hợp lý. HTTP timeout ngắn hơn query timeout có thể khiến client bỏ request trong khi DBMS vẫn chạy nếu cancellation không được truyền xuống. Query timeout quá ngắn có thể hủy tác vụ hợp lệ. Cần kiểm tra cơ chế cancellation của driver.

### 10.4. Hủy truy vấn và trả connection về pool

Khi timeout hoặc client disconnect:

1. Gửi cancel nếu driver hỗ trợ.
2. Chờ DBMS kết thúc hoặc xác nhận trạng thái.
3. Đóng ResultSet và statement.
4. Rollback transaction nếu cần.
5. Reset session state nếu pool yêu cầu.
6. Chỉ trả connection về pool khi nó ở trạng thái có thể tái sử dụng.

Nếu không thể xác nhận connection sạch, loại bỏ connection khỏi pool thay vì tái sử dụng trong trạng thái không xác định.

## 11. Đo thời gian execute, fetch và xử lý ứng dụng

### 11.1. Đừng gộp tất cả thành query time

Nên tách các mốc:

- Thời gian chờ connection pool.
- Thời gian gửi query và chờ first row.
- Thời gian DBMS execute nếu có thể đo riêng.
- Thời gian fetch toàn bộ ResultSet.
- Thời gian decode và map object.
- Thời gian xử lý từng hàng.
- Thời gian serialize.
- Thời gian gửi response.
- Tổng thời gian connection bị giữ.

Một truy vấn có thể có execute time 100 ms nhưng fetch time 8 giây. Khi đó, tối ưu index có thể không giúp nhiều bằng giảm payload, tăng fetch size hợp lý hoặc giảm client processing.

### 11.2. Thời gian đến hàng đầu tiên (time to first row)

Time to first row đo thời gian từ lúc gửi query đến khi ứng dụng nhận hàng đầu tiên. Chỉ số này quan trọng với UI và stream vì người dùng có thể bắt đầu thấy dữ liệu sớm.

Time to first row có thể cao do:

- DBMS phải sort hoặc hash toàn bộ tập trước khi phát.
- Query plan có blocking operator.
- Mạng hoặc connection setup chậm.
- Driver buffer nhiều hàng trước khi trả kết quả.
- DBMS cần đọc nhiều dữ liệu trước khi tạo hàng đầu tiên.

Giảm fetch size không thể sửa một sort blocking lớn trong execution plan. Cần phân tích cả plan và driver.

### 11.3. Thời gian đến hàng cuối cùng

Time to last row phản ánh thời gian hoàn tất fetch toàn bộ. Với export, đây có thể là chỉ số chính. Cần đo cùng tổng số hàng và tổng byte để so sánh công bằng.

Nếu một phiên bản query trả ít cột hơn, thời gian có thể giảm do truyền ít byte dù DBMS execute time không đổi. Hãy ghi payload size để giải thích kết quả.

### 11.4. Instrumentation ở ứng dụng

Một cách đo tổng quát:

~~~java
long acquireStart = System.nanoTime();
long acquiredAt = 0;
long queryStart = 0;
long firstRowAt = 0;
long finishedAt = 0;
long rowCount = 0;

try (Connection connection = dataSource.getConnection()) {
    acquiredAt = System.nanoTime();

    try (PreparedStatement statement = connection.prepareStatement(sql)) {
        statement.setFetchSize(fetchSize);
        queryStart = System.nanoTime();

        try (ResultSet rs = statement.executeQuery()) {
            while (rs.next()) {
                if (firstRowAt == 0) {
                    firstRowAt = System.nanoTime();
                }
                processRow(rs);
                rowCount++;
            }
            finishedAt = System.nanoTime();
        }
    }
}

long releasedAt = System.nanoTime();
recordMetrics(
    acquiredAt - acquireStart,
    firstRowAt == 0 ? 0 : firstRowAt - queryStart,
    finishedAt - queryStart,
    releasedAt - acquiredAt,
    rowCount
);
~~~

Đây là pseudocode minh họa. Trong chương trình thật, gán finishedAt ngay sau khi vòng lặp fetch kết thúc, ghi metric trong nhánh finally phù hợp và xử lý trường hợp không có hàng, lỗi, cancellation và transaction theo đúng framework. Thời điểm releasedAt được ghi sau khi Connection đóng và được trả về pool. Nếu query execute mất nhiều thời gian trước khi trả hàng đầu tiên, firstRowAt sẽ phản ánh điều đó.

### 11.5. Đo số byte và throughput

Ghi lại:

- Số hàng trả về.
- Số byte protocol nhận.
- Số byte sau compression nếu có.
- Kích thước payload JSON/CSV.
- Thời gian fetch.
- Throughput byte/giây và hàng/giây.
- RTT và số fetch round trip.
- CPU decode/serialize.
- Peak heap và allocation rate.

Nếu driver không cung cấp byte count, có thể dùng network metrics, proxy telemetry hoặc đo payload ở tầng ứng dụng. Cần phân biệt byte database protocol với byte HTTP response vì encoding và serialization có thể làm kích thước thay đổi.

## 12. Ví dụ: API export làm cạn connection pool

### 12.1. Hiện tượng

Một API export đơn hàng dùng cursor streaming để tránh tải toàn bộ dữ liệu vào heap. Khi nhiều người dùng export cùng lúc:

- Heap client ổn định hơn trước.
- Connection pool thường xuyên hết slot.
- Request OLTP chờ lấy connection.
- Thời gian giữ connection export lên đến 3 phút.
- Một số transaction đọc tồn tại lâu.
- p95 của API tăng dù CPU DBMS không bão hòa.

Streaming đã giải quyết một vấn đề bộ nhớ client nhưng làm lộ giới hạn connection concurrency.

### 12.2. Giả thuyết

- Export không có giới hạn concurrency.
- Client tải file chậm nên cursor được giữ lâu.
- Ứng dụng ghi file trực tiếp vào HTTP response trong khi vẫn giữ DB connection.
- Transaction mở trong suốt thời gian serialize và truyền file.
- Fetch size quá nhỏ làm tăng round trip.
- Query lấy thêm cột LOB không cần thiết.
- Client disconnect nhưng query không được cancel.

### 12.3. Thay đổi thử nghiệm

1. Chuyển export sang job bất đồng bộ.
2. Worker đọc dữ liệu theo batch và ghi file vào object storage.
3. Giới hạn số export worker đồng thời.
4. Đóng cursor/transaction ngay sau khi file hoàn tất.
5. Cho người dùng tải file đã tạo, không giữ DB connection trong lúc trình duyệt tải.
6. Chỉ lấy các cột cần thiết và tách LOB nếu không bắt buộc.
7. Điều chỉnh fetch size dựa trên payload và RTT.
8. Thêm cancellation, timeout và checkpoint cho job.

### 12.4. Kết quả minh họa

| Chỉ số | Trước | Sau thử nghiệm |
|---|---:|---:|
| Export đồng thời | 20 | 4 worker |
| Thời gian giữ DB connection trung bình | 180 s | 24 s |
| Pool acquire p95 của OLTP | 1.200 ms | 35 ms |
| Peak heap worker | 3,8 GB | 620 MB |
| Export hoàn tất | 180 s | 205 s |
| OLTP p95 | 420 ms | 95 ms |

Các số liệu chỉ minh họa. Export chậm hơn một chút do được giới hạn worker và xử lý file theo job, nhưng connection pool và OLTP ổn định hơn. Đây có thể là trade-off phù hợp khi export không cần phản hồi đồng bộ tức thì.

## 13. Những sai lầm thường gặp

**Chỉ đo thời gian execute trên DBMS.**  
Fetch, decode, serialize và network transfer có thể chiếm phần lớn thời gian end-to-end.

**Dùng SELECT * cho API danh sách.**  
Cột lớn không cần thiết làm tăng I/O, payload, RAM và thời gian giữ connection.

**Buffer toàn bộ kết quả lớn trong client.**  
Peak heap có thể tăng theo số hàng và overhead object.

**Cho rằng streaming luôn nhanh hơn.**  
Streaming giảm RAM client nhưng có thể tăng round trip và giữ connection/cursor lâu.

**Đặt fetch size quá nhỏ.**  
Nhiều lượt fetch tuần tự có thể làm latency mạng chi phối.

**Đặt fetch size quá lớn.**  
Batch lớn có thể làm tăng heap, thời gian xử lý và lượng dữ liệu phải bỏ nếu client hủy.

**Để transaction mở trong lúc gọi dịch vụ ngoài.**  
Transaction dài có thể giữ snapshot, lock hoặc version cũ tùy engine và isolation.

**Tăng connection pool để xử lý request chờ.**  
Pool lớn có thể tăng số query đồng thời và làm DBMS quá tải.

**Dùng cursor streaming cho một trang UI nhỏ.**  
Pagination có giới hạn thường phù hợp hơn nếu người dùng chỉ cần một phần kết quả.

**Dùng OFFSET sâu cho export lớn.**  
DBMS có thể phải bỏ qua nhiều hàng; keyset hoặc cursor theo batch có thể phù hợp hơn tùy workload.

**Không hủy query khi client disconnect.**  
DBMS tiếp tục làm việc và connection vẫn bị giữ dù kết quả không còn người nhận.

**Không phân biệt byte protocol và byte HTTP.**  
Compression, JSON serialization và encoding làm kích thước hai tầng khác nhau.

## 14. Quy trình tối ưu kích thước kết quả và kết nối

Có thể áp dụng theo trình tự:

1. **Xác định nhu cầu dữ liệu:** màn hình hoặc job thực sự cần bao nhiêu hàng và cột?
2. **Ước lượng payload:** row count, average/p95 row width, LOB và encoding.
3. **Đọc execution plan:** số hàng đầu ra, blocking operator, sort, aggregate và I/O.
4. **Giảm dữ liệu:** filter, projection, aggregate, JOIN đúng grain và tránh N+1.
5. **Chọn cách đọc:** buffered cho tập nhỏ; pagination cho UI; cursor/streaming cho xử lý tuần tự lớn.
6. **Chọn fetch size:** cân bằng batch memory, RTT, throughput và client processing.
7. **Thiết kế backpressure:** bounded buffer, cancellation và giới hạn stream đồng thời.
8. **Giới hạn connection:** pool, quota theo workload và admission control.
9. **Quản lý transaction:** đóng cursor, commit/rollback và không giữ transaction khi xử lý ngoài DB.
10. **Đặt timeout:** pool acquire, statement, socket, transaction và request.
11. **Đo end-to-end:** execute, first row, fetch, last row, byte count, heap và connection hold time.
12. **Benchmark hỗn hợp:** chạy OLTP cùng export/report, tăng concurrency từng bước.
13. **Kiểm tra failure path:** client disconnect, timeout, lỗi giữa batch và retry.
14. **Xác nhận kết quả:** dữ liệu đầy đủ, không trùng/thiếu, quyền truy cập đúng và SLO đạt mục tiêu.

### 14.1. Bảng chọn chiến lược

| Tình huống | Chiến lược thường phù hợp | Điều cần kiểm soát |
|---|---|---|
| Trang danh sách 20-100 hàng | Pagination | Sort ổn định, index, cursor |
| Tập kết quả nhỏ và cần duyệt nhiều lần | Buffered result | Giới hạn số hàng và payload |
| Xử lý tuần tự hàng triệu dòng | Cursor/fetch theo lô | Connection hold, transaction và backpressure |
| Export rất lớn cho người dùng | Job bất đồng bộ + file | Worker concurrency, storage và expiry |
| Payload LOB lớn | Tải riêng theo ID hoặc stream LOB | Batch size, cancellation và quyền truy cập |
| Nhiều truy vấn liên quan | JOIN/aggregate hoặc batch | Fanout, cardinality và semantics |
| Mạng RTT cao | Batch/prefetch phù hợp | RAM và throughput |
| Client xử lý chậm | Bounded queue và admission control | Không giữ tài nguyên vô hạn |

### 14.2. Tiêu chí chấp nhận

Một thay đổi có thể được chấp nhận khi:

- Số byte trả về phù hợp với nhu cầu API.
- Peak heap client nằm trong ngân sách.
- Fetch throughput đạt mục tiêu.
- Time to first row và time to last row phù hợp SLO.
- Connection hold time và pool wait không gây nghẽn.
- Transaction/cursor được đóng ở cả nhánh thành công và lỗi.
- Không tăng spill hoặc I/O DBMS bất thường.
- Client disconnect và timeout giải phóng tài nguyên đúng.
- Kết quả không thiếu/trùng và quyền truy cập được giữ nguyên.
- Workload OLTP vẫn đạt p95/p99 khi export hoặc báo cáo chạy.

## 15. Kết luận

Kích thước kết quả là một phần quan trọng của hiệu năng cơ sở dữ liệu và ứng dụng. Số hàng, độ rộng hàng, LOB, số round trip và tốc độ tiêu thụ của client quyết định chi phí truyền và xử lý. Projection, filter và aggregate đúng chỗ có thể giảm payload trước khi dữ liệu rời DBMS.

Buffered result đơn giản nhưng có thể tiêu thụ RAM theo toàn bộ kết quả. Fetch theo lô và cursor streaming giới hạn bộ nhớ client, nhưng có thể tăng round trip và giữ connection, cursor hoặc transaction lâu hơn. Pagination phù hợp với giao diện cần một phần dữ liệu; streaming phù hợp với xử lý tuần tự lớn; export rất lớn thường nên chạy như job bất đồng bộ để không gắn vòng đời DB connection với tốc độ tải của trình duyệt.

Tối ưu cần đo riêng execute, first row, fetch, last row, số byte, heap, connection hold time và pool wait. Hãy kiểm soát fetch size, backpressure, cancellation, concurrency và timeout theo driver cùng DBMS thực tế. Một giải pháp tốt giảm dữ liệu truyền, giữ bộ nhớ và connection trong ngân sách, đồng thời bảo toàn tính đầy đủ và đúng đắn của kết quả.

## Câu hỏi tự kiểm tra

1. Vì sao thời gian execute của DBMS không phản ánh toàn bộ thời gian người dùng chờ?
2. Kích thước kết quả phụ thuộc những yếu tố nào ngoài số hàng?
3. Vì sao SELECT * có thể làm tăng cả I/O DBMS, network transfer và heap client?
4. Buffered result khác fetch theo lô và cursor streaming như thế nào?
5. Vì sao streaming có thể giảm RAM client nhưng làm connection pool thiếu slot?
6. Fetch size quá nhỏ và quá lớn tạo ra những chi phí nào?
7. Vì sao một truy vấn có ORDER BY hoặc hash aggregate vẫn có thể chậm trước khi trả hàng đầu tiên?
8. Backpressure xảy ra khi tốc độ producer và consumer khác nhau như thế nào?
9. Transaction đọc dài có thể ảnh hưởng vacuum, undo hoặc version store ra sao trên các DBMS khác nhau?
10. Vì sao không nên tăng connection pool chỉ để xử lý request đang chờ?
11. Khi nào keyset pagination phù hợp hơn OFFSET và khi nào cursor streaming phù hợp hơn pagination?
12. Vì sao export rất lớn có thể nên chạy bất đồng bộ và ghi file trước khi người dùng tải?
13. Cần đo những chỉ số nào để phân biệt DBMS execute chậm với fetch/network/client chậm?
14. Hãy thiết kế benchmark cho 10 stream đồng thời với các fetch size khác nhau, ghi nhận heap, round trip và connection hold time.

Khi review một truy vấn trả nhiều dữ liệu, hãy hỏi: ứng dụng thực sự cần bao nhiêu hàng và cột, payload chiếm bao nhiêu byte, client tiêu thụ nhanh đến đâu, connection bị giữ trong bao lâu và điều gì xảy ra khi client dừng giữa chừng. Những câu hỏi đó giúp tối ưu toàn bộ đường đi của dữ liệu từ DBMS đến người dùng.


