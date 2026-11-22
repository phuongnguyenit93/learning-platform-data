# Quét toàn bảng và các tình huống quét tuần tự có lợi

Trong chương **Cơ chế truy cập** của module **DATABASE_PERFORMANCE**, cần hiểu rằng optimizer chọn cách đọc dữ liệu dựa trên lượng công việc dự kiến, chứ không phải luôn ưu tiên chỉ mục. Quét toàn bảng (*full table scan*) hoặc quét tuần tự (*sequential scan*) có thể là lựa chọn nhanh và ổn định khi truy vấn cần phần lớn dữ liệu, bảng nhỏ, hoặc chi phí truy cập từng dòng qua chỉ mục cao hơn chi phí đọc các trang liên tiếp.

Mục tiêu của tối ưu hiệu năng cơ sở dữ liệu là giảm tổng chi phí phục vụ workload: số trang phải đọc, CPU để lọc và xử lý, bộ nhớ trung gian, thời gian chờ I/O và ảnh hưởng tới truy vấn khác. Vì vậy, thấy `Seq Scan`, `Table Scan` hay `TABLE ACCESS FULL` trong execution plan chưa đủ để kết luận truy vấn có vấn đề. Cần đối chiếu điều kiện lọc, số dòng thực tế, số trang đọc, độ rộng dữ liệu, trạng thái cache và tải đồng thời.

## 1. Quét toàn bảng là gì?

Quét toàn bảng là phương thức đọc lần lượt các phần dữ liệu của một bảng để tìm dòng thỏa điều kiện hoặc xử lý toàn bộ tập dữ liệu. Tùy hệ quản trị, tên operator và cách tổ chức lưu trữ khác nhau:

| Hệ quản trị | Tên thường gặp trong kế hoạch | Ý nghĩa khái quát |
|---|---|---|
| PostgreSQL | `Seq Scan`, `Parallel Seq Scan` | Đọc các trang heap theo cách tuần tự; có thể dùng nhiều worker song song |
| MySQL/InnoDB | `type = ALL` trong `EXPLAIN`; full table scan | Đọc toàn bộ bảng. Với InnoDB, dữ liệu bảng được tổ chức theo clustered index, thường là khóa chính nếu có |
| SQL Server | `Table Scan`, `Clustered Index Scan` | Đọc toàn bộ heap hoặc toàn bộ leaf level của clustered index |
| Oracle Database | `TABLE ACCESS FULL` | Đọc các block của segment bảng; có thể dùng multiblock I/O và direct path tùy điều kiện |

Các operator này không hoàn toàn đồng nhất về cách lưu trữ hoặc cách đọc vật lý. Điểm chung là phạm vi đọc bao phủ toàn bảng hoặc toàn bộ cấu trúc dữ liệu tương ứng, thay vì tìm một vùng nhỏ bằng phép tra cứu chỉ mục.

Quét tuần tự thường tận dụng việc đọc nhiều block liên tiếp, read-ahead, cache và khả năng xử lý theo lô. Tuy nhiên, không nên hiểu rằng mọi lần quét đều chỉ đọc đúng một dải block vật lý liên tiếp trên thiết bị. Phân bố trang, mức phân mảnh, phân vùng, cache và tầng lưu trữ đều ảnh hưởng đường đọc thực tế.

## 2. Vì sao quét tuần tự đôi khi nhanh hơn dùng chỉ mục

Chỉ mục giúp tìm vị trí các dòng cần thiết mà không phải kiểm tra toàn bộ bảng. Nhưng sau khi tìm được khóa, hệ quản trị có thể vẫn phải truy cập trang dữ liệu để lấy các cột còn thiếu. Nếu truy vấn cần nhiều dòng, các lần truy cập trang này có thể tạo ra lượng I/O lớn và phân tán.

Hãy so sánh hai cách thực hiện:

- **Dùng chỉ mục:** tìm khóa trong cây chỉ mục, xác định các dòng phù hợp, rồi có thể đọc thêm trang bảng để lấy cột còn thiếu. Nếu kết quả trải trên nhiều trang, có thể phát sinh nhiều lần truy cập dữ liệu.
- **Quét tuần tự:** đọc các trang của bảng theo phạm vi rộng, kiểm tra điều kiện lọc trên từng dòng và giữ lại kết quả cần thiết. Mỗi trang có thể được xử lý một lần trong quá trình quét.

Giả sử bảng `orders` có 10 triệu dòng. Truy vấn báo cáo cần tổng hợp doanh thu của một trạng thái phổ biến, khớp 7 triệu dòng và đọc nhiều cột. Một chỉ mục không bao phủ các cột đó có thể dẫn tới việc đọc chỉ mục rồi truy cập bảng nhiều lần. Quét bảng tuần tự có thể đọc các trang một lượt, lọc dữ liệu và tính tổng với chi phí thấp hơn.

Ngược lại, nếu truy vấn tìm một đơn hàng theo khóa chính và chỉ trả về một dòng, quét toàn bộ bảng sẽ làm công việc thừa rất lớn. Khi dữ liệu ít và chỉ mục phù hợp, index seek hoặc index lookup thường hiệu quả hơn.

### 2.1. Mô hình chi phí trực quan

Có thể mô tả đơn giản hai lựa chọn như sau:

\[
C_{scan} \approx C_{read\ all\ pages} + C_{filter\ all\ rows}
\]

\[
C_{index} \approx C_{traverse\ index} + C_{read\ matching\ entries}
              + C_{fetch\ required\ rows}
\]

Đây là mô hình tư duy, không phải công thức cost chính xác của một hệ quản trị. Optimizer còn xét CPU, số trang, cache, độ phân cụm, song song, chi phí sort, bộ nhớ, thống kê và nhiều yếu tố khác.

Khi tỷ lệ dòng phù hợp tăng, số lần đọc dữ liệu qua chỉ mục và số trang phải truy cập có thể tăng tới mức quét tuần tự rẻ hơn. Không có một ngưỡng chọn lọc cố định áp dụng cho mọi bảng. Ngưỡng hòa vốn thay đổi theo kích thước dòng, cấu trúc chỉ mục, mức phân cụm, loại storage, cache, cột cần trả về và workload đồng thời.

### 2.2. Những tình huống quét toàn bảng thường có lợi

| Tình huống | Vì sao scan có thể phù hợp |
|---|---|
| Truy vấn cần phần lớn dòng | Đọc toàn bộ trang một lượt có thể rẻ hơn nhiều lần lookup qua chỉ mục |
| Bảng nhỏ | Số trang ít; chi phí mở và duyệt chỉ mục có thể không đem lại lợi ích |
| Báo cáo tổng hợp toàn kỳ | Truy vấn phải đọc lượng dữ liệu lớn để tính `SUM`, `COUNT`, `AVG` hoặc nhóm dữ liệu |
| Chỉ mục không bao phủ truy vấn | Dùng index có thể phải quay lại bảng để lấy nhiều cột |
| Dữ liệu được đọc theo lô | Scan có thể tận dụng read-ahead, batch processing hoặc parallel scan |
| Cache đã chứa phần lớn bảng | Đọc trang từ bộ nhớ có thể rẻ hơn việc thực hiện nhiều lần truy cập chỉ mục và lookup |
| Phân vùng hoặc vùng dữ liệu cần đọc đã được thu hẹp | Scan trong phạm vi partition đã pruning có thể hiệu quả dù đó là scan toàn bộ partition |

Một truy vấn `COUNT(*)` trên bảng lớn có thể cần đọc toàn bộ cấu trúc dữ liệu nếu không có metadata hoặc cấu trúc thay thế đáp ứng chính xác yêu cầu. Một báo cáo tính doanh thu theo tháng cũng có thể cần đọc phần lớn dòng của tháng đó. Trong các trường hợp này, scan không phải lỗi thiết kế; đó có thể là cách hoàn thành công việc ít tốn kém nhất.

## 3. Những yếu tố quyết định scan hay index access

Optimizer thường kết hợp nhiều yếu tố để chọn access path.

### 3.1. Độ chọn lọc và số dòng cần trả về

Độ chọn lọc cho biết tỷ lệ dòng thỏa điều kiện. Điều kiện `WHERE order_id = 123` thường có độ chọn lọc rất cao vì chỉ khớp một dòng. Điều kiện `WHERE status = 'OPEN'` có thể khớp phần lớn bảng nếu trạng thái này phổ biến.

Số dòng thực tế quan trọng hơn chỉ nhìn vào số lượng giá trị phân biệt. Hai cột có cùng số giá trị phân biệt vẫn có thể có phân bố rất khác nhau. Nếu thống kê đánh giá sai tần suất của giá trị phổ biến, optimizer có thể chọn scan hoặc index access không phù hợp.

### 3.2. Độ rộng dòng và số cột được truy vấn

Truy vấn chỉ cần hai cột nhỏ có thể dùng covering index để đọc ít dữ liệu. Truy vấn lấy nhiều cột hoặc cột có kích thước lớn có thể khiến chỉ mục không bao phủ được kết quả. Khi phải đọc phần lớn dòng, scan bảng có thể giảm số lần quay lại trang dữ liệu.

Ví dụ, truy vấn sau chỉ cần các cột có thể nằm trong một chỉ mục ghép phù hợp:

```sql
SELECT order_id, created_at
FROM orders
WHERE tenant_id = 42
  AND status = 'OPEN';
```

Trong khi truy vấn sau cần thêm nhiều cột khác:

```sql
SELECT *
FROM orders
WHERE status = 'OPEN';
```

Không nên dùng `SELECT *` trong ứng dụng nếu không cần toàn bộ cột. Dù vậy, chỉ giảm danh sách cột cũng chưa đảm bảo optimizer sẽ chọn index access; vẫn phải đo trên dữ liệu thực tế.

### 3.3. Độ phân cụm và tính cục bộ của dữ liệu

Nếu các dòng có khóa chỉ mục gần nhau cũng nằm gần nhau trên trang dữ liệu, truy cập qua chỉ mục có thể cần ít lần đọc trang hơn. Nếu các dòng phù hợp phân tán trên nhiều trang, index lookup có thể tạo nhiều truy cập rời rạc. Độ phân cụm (*clustering*) vì vậy ảnh hưởng tới chi phí thực tế của index access.

Với dữ liệu được tổ chức theo clustered index, chẳng hạn InnoDB hoặc SQL Server, truy cập theo khóa clustered có đặc điểm khác với heap hoặc bảng heap có secondary index. Cần đọc đúng mô hình lưu trữ của hệ quản trị trước khi suy luận số lần lookup.

### 3.4. Cache và loại lưu trữ

Khi bảng nằm trong buffer pool hoặc cache, scan có thể đọc từ RAM với chi phí thấp. Khi dữ liệu không nằm trong cache, thời gian đọc phụ thuộc storage và khả năng đọc song song. SSD, NVMe và hệ thống lưu trữ phân tán có đặc tính khác nhau; không thể áp dụng một ngưỡng selectivity chung dựa trên kinh nghiệm của môi trường khác.

Đo warm cache và cold cache khi cả hai phản ánh điều kiện vận hành cần hỗ trợ. Không xóa cache hoặc khởi động lại máy chủ dùng chung chỉ để tạo một phép thử cold cache nếu chưa có kế hoạch vận hành được kiểm soát.

### 3.5. Song song và tải đồng thời

Một số hệ quản trị có thể chia scan thành nhiều phần và xử lý song song. Parallel scan có thể giảm elapsed time cho truy vấn lớn, nhưng làm tăng tổng CPU, I/O và mức tranh chấp tài nguyên. Nếu nhiều truy vấn scan cùng lúc, throughput toàn hệ thống có thể giảm dù từng truy vấn riêng lẻ chạy nhanh hơn.

Do đó, cần đánh giá cả thời gian một truy vấn và tác động của nó tới workload khác. Một báo cáo chạy nhanh hơn nhờ dùng nhiều worker chưa chắc là lựa chọn tốt nếu nó làm các giao dịch trực tuyến bị chậm.

## 4. Đọc kế hoạch thực thi khi gặp table scan

Khi thấy scan trong execution plan, hãy kiểm tra các thông tin sau:

1. **Phạm vi scan:** scan toàn bảng, scan một partition hay scan một vùng đã được giới hạn?
2. **Estimated rows và actual rows:** optimizer dự đoán bao nhiêu dòng và thực tế đọc/giữ lại bao nhiêu dòng?
3. **Rows removed by filter:** có bao nhiêu dòng bị loại sau khi đọc? Tỷ lệ dòng bị loại cao có thể gợi ý điều kiện lọc chưa tận dụng được chỉ mục, nhưng chưa đủ để kết luận scan sai.
4. **Số trang hoặc logical reads:** scan đã đọc bao nhiêu block/page? So sánh với kích thước bảng và với kế hoạch dùng chỉ mục.
5. **Thời gian CPU và elapsed:** thời gian có chủ yếu do lọc/tính toán hay do chờ I/O?
6. **Parallelism:** có bao nhiêu worker, mức tăng tốc có tương xứng với CPU sử dụng không?
7. **Sort, hash và memory:** scan có đưa nhiều dòng vào sort/hash hoặc tạo spill ra vùng tạm không?
8. **Predicate pushdown và partition pruning:** điều kiện có được áp dụng sớm ở tầng đọc dữ liệu không, hay phải lọc sau khi đọc nhiều dữ liệu?

### 4.1. PostgreSQL

Ví dụ kiểm tra truy vấn tổng hợp:

```sql
EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
SELECT status, COUNT(*)
FROM orders
WHERE created_at >= TIMESTAMPTZ '2026-01-01 00:00:00+07'
GROUP BY status;
```

Nếu kế hoạch có `Seq Scan` hoặc `Parallel Seq Scan`, đọc:

- `actual rows` và `Rows Removed by Filter` để biết số dòng đi qua scan và số dòng bị loại.
- `Buffers: shared hit` và `shared read` để hiểu hoạt động shared buffers. `shared read` không luôn đồng nghĩa đọc vật lý từ thiết bị vì hệ điều hành có thể phục vụ từ page cache.
- `Planning Time` và `Execution Time` để phân biệt chi phí lập kế hoạch và chạy câu lệnh.
- Thông tin worker trong `Parallel Seq Scan` để đánh giá hiệu quả song song.

`EXPLAIN ANALYZE` thực thi truy vấn. Chỉ chạy trên truy vấn đọc an toàn hoặc môi trường thử nghiệm nếu câu lệnh có tác động ghi dữ liệu. Có thể so sánh với một phương án index access trên bản sao dữ liệu tương đương, nhưng không nên ép planner bằng cách tắt scan trong production để chứng minh một giả thuyết.

### 4.2. MySQL/InnoDB

Với MySQL, kiểm tra `EXPLAIN` hoặc `EXPLAIN ANALYZE` ở phiên bản hỗ trợ:

```sql
EXPLAIN ANALYZE
SELECT status, COUNT(*)
FROM orders
WHERE created_at >= '2026-01-01 00:00:00'
GROUP BY status;
```

Trong dạng `EXPLAIN` dạng bảng, `type = ALL` thường cho biết full table scan. Đọc thêm `rows`, `filtered`, `key`, `possible_keys` và `Extra`. `rows` là ước lượng số dòng cần đọc; `filtered` là tỷ lệ phần trăm ước lượng còn lại sau điều kiện lọc. Với InnoDB, bảng được tổ chức theo clustered index, do đó full scan thường đọc leaf pages của clustered index. Nếu khóa chính rộng, cấu trúc này cũng ảnh hưởng kích thước và chi phí scan.

`EXPLAIN ANALYZE` hiển thị iterator thực thi cùng thời gian và số dòng thực tế. Đối chiếu số dòng thực tế với ước lượng, và kiểm tra xem thời gian có nằm ở scan hay ở sort/aggregate phía trên. Trên phiên bản không hỗ trợ `EXPLAIN ANALYZE`, dùng `EXPLAIN` và công cụ đo runtime phù hợp.

### 4.3. SQL Server

Trong SQL Server, xem Actual Execution Plan để phân biệt `Table Scan` trên heap và `Clustered Index Scan` trên clustered index. Kết hợp số liệu:

```sql
SET STATISTICS IO ON;
SET STATISTICS TIME ON;

SELECT status, COUNT(*)
FROM dbo.orders
WHERE created_at >= '2026-01-01T00:00:00'
GROUP BY status;

SET STATISTICS IO OFF;
SET STATISTICS TIME OFF;
```

Đọc logical reads, physical reads, scan count, CPU time và elapsed time. Trong execution plan, kiểm tra actual rows, estimated rows, predicate, parallelism, memory grant và cảnh báo spill. `Clustered Index Scan` không nhất thiết là lựa chọn xấu; nếu truy vấn cần phần lớn dòng thì đọc toàn bộ leaf level có thể rẻ hơn hàng loạt key lookup.

### 4.4. Oracle Database

Oracle có thể hiển thị `TABLE ACCESS FULL` trong execution plan. Để lấy số liệu runtime thực tế, có thể dùng `GATHER_PLAN_STATISTICS` cho câu lệnh thử nghiệm và xem cursor tương ứng:

```sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       status, COUNT(*)
FROM orders
WHERE created_at >= DATE '2026-01-01'
GROUP BY status;

SELECT *
FROM TABLE(
  DBMS_XPLAN.DISPLAY_CURSOR(
    NULL,
    NULL,
    'ALLSTATS LAST +PREDICATE +BUFFERS'
  )
);
```

Đọc `E-Rows` so với `A-Rows`, số lần thực thi, buffer gets và physical reads. Oracle có thể dùng multiblock reads và direct path reads trong một số điều kiện. Một full table scan lớn có thể là lựa chọn hợp lý cho báo cáo hoặc phân tích, nhưng vẫn cần đánh giá ảnh hưởng tới I/O và các workload khác.

## 5. Phân biệt scan hợp lý và scan đáng điều tra

Không nên đánh giá scan chỉ bằng tên operator. Bảng sau gợi ý cách phân loại ban đầu:

| Dấu hiệu | Diễn giải có thể có | Việc cần kiểm tra |
|---|---|---|
| Bảng nhỏ, scan nhanh, ít buffer/page | Scan có thể là lựa chọn tối ưu | So sánh với index path và overhead tổng thể; thường không cần thay đổi |
| Truy vấn trả về phần lớn bảng | Scan có thể giảm nhiều lookup rời rạc | Kiểm tra số cột đọc, throughput I/O và khả năng xử lý song song |
| Bảng rất lớn, kết quả chỉ vài dòng nhưng vẫn full scan | Có thể thiếu chỉ mục phù hợp hoặc optimizer ước lượng sai | Kiểm tra predicate, kiểu dữ liệu, hàm trên cột, thống kê và index khả dụng |
| Estimated rows sai xa actual rows | Thống kê hoặc mô hình ước lượng có thể không phản ánh dữ liệu | Cập nhật thống kê, kiểm tra skew, histogram và tương quan cột |
| Scan gây I/O cao và ảnh hưởng truy vấn khác | Scan có thể cạnh tranh băng thông lưu trữ hoặc cache | Xem lịch chạy báo cáo, partition pruning, giới hạn đồng thời và kế hoạch đọc |
| Scan theo partition nhỏ, có pruning tốt | Phạm vi đọc đã được giới hạn hiệu quả | Kiểm tra partition được chọn và lượng dữ liệu thực sự cần đọc |

### 5.1. Khi scan có thể là vấn đề

Hãy điều tra sâu hơn nếu truy vấn có tính chọn lọc cao nhưng vẫn đọc toàn bảng, đặc biệt khi bảng lớn và dữ liệu trả về ít. Các nguyên nhân có thể gồm:

- Chưa có chỉ mục bắt đầu bằng cột phù hợp với điều kiện lọc.
- Điều kiện lọc áp dụng hàm hoặc phép chuyển đổi lên cột khiến chỉ mục khó được sử dụng.
- Kiểu dữ liệu của tham số và cột không tương thích, gây implicit conversion.
- Thống kê cũ, histogram không đủ hoặc ước lượng cardinality sai.
- Điều kiện lọc được áp dụng muộn thay vì pushdown tới tầng truy cập dữ liệu.
- Chỉ mục hiện có không bao phủ cột cần đọc và số lần lookup dự kiến quá lớn.
- Partition pruning không hoạt động do cách viết điều kiện hoặc thiết kế partition.

Ví dụ, nếu cột `created_at` có chỉ mục nhưng truy vấn viết `WHERE DATE(created_at) = '2026-01-01'`, việc áp dụng hàm lên cột có thể cản trở range seek tùy hệ quản trị. Có thể viết điều kiện dạng khoảng:

```sql
WHERE created_at >= TIMESTAMP '2026-01-01 00:00:00'
  AND created_at <  TIMESTAMP '2026-01-02 00:00:00'
```

Điều kiện khoảng thường giúp optimizer xác định phạm vi chỉ mục rõ ràng hơn. Cần kiểm tra kiểu thời gian, múi giờ và semantics của ứng dụng để bảo đảm kết quả không đổi.

### 5.2. Khi scan nên được giữ lại

Scan có thể nên được giữ nếu truy vấn cần phần lớn dòng, bảng nhỏ, chỉ mục không bao phủ hoặc kế hoạch scan cho thông lượng tốt hơn. Với báo cáo lớn, có thể cân nhắc chạy ngoài giờ cao điểm, dùng replica đọc, partition pruning, tổng hợp trước hoặc lưu kết quả theo kỳ nếu yêu cầu nghiệp vụ cho phép.

Không nên thêm chỉ mục chỉ để loại bỏ operator scan khỏi plan. Mỗi chỉ mục tiêu tốn dung lượng, làm tăng công việc insert/update/delete, tăng thời gian bảo trì và có thể làm cache bị phân tán. Chỉ mục mới cần chứng minh lợi ích trên workload đọc tổng thể sau khi tính cả chi phí ghi.

## 6. Quét toàn bảng trong môi trường có phân vùng và dữ liệu lớn

Một truy vấn có thể quét toàn bộ partition được chọn mà không quét toàn bảng. Ví dụ bảng `orders` được partition theo tháng; truy vấn chỉ yêu cầu tháng 1 thì partition pruning có thể loại các tháng khác. Kế hoạch vẫn hiển thị scan trên partition được chọn, nhưng lượng dữ liệu đọc đã nhỏ hơn đáng kể.

```sql
SELECT COUNT(*)
FROM orders
WHERE created_at >= TIMESTAMP '2026-01-01 00:00:00'
  AND created_at <  TIMESTAMP '2026-02-01 00:00:00';
```

Hãy kiểm tra danh sách partition được truy cập trong plan và xác nhận điều kiện lọc phù hợp với khóa partition. Nếu điều kiện không thể dùng để pruning, hệ quản trị có thể phải mở rộng phạm vi scan.

Với dữ liệu phân tích lớn, một số hệ thống lưu trữ dạng columnstore hoặc có cơ chế zone map/min-max metadata có thể bỏ qua segment hoặc row group không liên quan. Khi đó, hoạt động đọc có thể được gọi là scan ở cấp operator nhưng không nhất thiết đọc mọi byte của toàn bộ dữ liệu vật lý. Cần hiểu khả năng pruning, predicate pushdown và định dạng lưu trữ của nền tảng cụ thể.

## 7. Quy trình đo để quyết định có tối ưu scan hay không

1. **Xác định yêu cầu truy vấn.** Ghi rõ số dòng cần trả về, các cột cần đọc, điều kiện lọc, thứ tự sắp xếp và mục tiêu độ trễ.
2. **Kiểm tra kích thước và phân bố dữ liệu.** Xem số dòng, số trang, độ rộng dòng, phân bố giá trị, partition và tỷ lệ kết quả ước tính.
3. **Đọc execution plan.** Xác định scan phạm vi nào, estimated rows, actual rows, predicate, số lần đọc và các operator phía trên.
4. **Đo tài nguyên.** Ghi elapsed, CPU, logical reads, physical reads, buffer hits, I/O latency, memory, spill và wait event.
5. **Tạo phương án đối chứng.** Nếu có chỉ mục phù hợp, so sánh index access với scan trên cùng dataset và cùng tham số. Không chỉ dựa vào optimizer cost.
6. **Lặp lại trong điều kiện kiểm soát.** Đo nhiều lần, phân biệt warm/cold cache nếu cần và kiểm soát tác vụ nền.
7. **Thử mức đồng thời thực tế.** Đánh giá throughput, p95/p99 và ảnh hưởng tới truy vấn khác khi scan chạy cùng workload trực tuyến.
8. **Chọn thay đổi có bằng chứng.** Có thể giữ scan, tạo hoặc sửa chỉ mục, viết lại predicate, bật partition pruning, giảm dữ liệu đọc hoặc chuyển báo cáo sang replica.
9. **Đo lại sau thay đổi.** So sánh cùng bộ tham số, dữ liệu và điều kiện tải; kiểm tra cả chi phí ghi và bảo trì chỉ mục.

### Ví dụ đánh giá

Giả sử bảng `orders` có 30 triệu dòng và truy vấn lấy đơn hàng `OPEN` trong năm hiện tại:

```sql
SELECT status, SUM(total_amount)
FROM orders
WHERE created_at >= TIMESTAMP '2026-01-01 00:00:00'
GROUP BY status;
```

Nếu 70% dòng thuộc năm hiện tại, truy vấn phải đọc nhiều dữ liệu và tổng hợp. Một scan có thể hiệu quả hơn index range scan cộng hàng triệu lookup. Nếu chỉ 0,01% dòng thuộc một `tenant_id` và truy vấn chỉ cần vài cột, index access có thể tốt hơn. Nếu bảng partition theo tháng, pruning có thể thu hẹp scan xuống đúng các partition cần thiết.

Quyết định phải dựa trên actual rows, logical/physical reads, CPU, elapsed, memory và throughput dưới tải. Nếu scan nhanh trong thử nghiệm đơn lẻ nhưng làm p99 của API tăng mạnh khi chạy đồng thời, cần cân nhắc giới hạn thời gian chạy, replica hoặc lịch thực thi báo cáo.

## 8. Những sai lầm thường gặp

- **Cho rằng table scan luôn xấu:** scan có thể rẻ hơn nhiều lần truy cập chỉ mục khi cần phần lớn dữ liệu.
- **Cho rằng index seek luôn tốt:** seek có thể kéo theo rất nhiều key lookup hoặc bookmark lookup.
- **Dùng một ngưỡng selectivity cố định:** điểm hòa vốn phụ thuộc dữ liệu, storage, cache, độ rộng dòng và chỉ mục.
- **Chỉ nhìn estimated cost:** cost không phải thời gian thực tế; cần đo runtime và tài nguyên.
- **Bỏ qua partition pruning:** scan một partition không đồng nghĩa scan toàn bảng.
- **Không kiểm tra predicate:** hàm trên cột, implicit conversion hoặc kiểu dữ liệu sai có thể làm mất khả năng dùng index.
- **So sánh hai kế hoạch trong điều kiện cache khác nhau:** kết quả có thể phản ánh cache thay vì thay đổi access path.
- **Tạo index chỉ để plan hết scan:** chỉ mục làm tăng dung lượng và chi phí ghi, có thể gây hại workload tổng thể.
- **Không đo dưới tải đồng thời:** scan lớn có thể chiếm băng thông I/O, CPU và cache, làm truy vấn khác chậm hơn.
- **Dùng hint ép access path quá sớm:** hint có thể khiến kế hoạch kém khi dữ liệu hoặc tham số thay đổi.

## 9. Checklist đọc và đánh giá table scan

- [ ] Đã xác định scan toàn bảng, scan partition hay scan một cấu trúc clustered/heap.
- [ ] Đã biết tỷ lệ dòng thực tế cần trả về và số cột phải đọc.
- [ ] Đã so sánh estimated rows với actual rows.
- [ ] Đã kiểm tra logical reads, physical reads, buffers và thời gian I/O.
- [ ] Đã xem predicate, residual filter và khả năng partition pruning.
- [ ] Đã kiểm tra có chỉ mục phù hợp hoặc covering index hay không.
- [ ] Đã so sánh scan và index access trong cùng điều kiện dữ liệu, cache và tham số.
- [ ] Đã đo CPU, elapsed, memory, spill và wait event.
- [ ] Đã thử ở mức đồng thời đại diện và đánh giá ảnh hưởng tới workload khác.
- [ ] Đã tính chi phí ghi, dung lượng và bảo trì nếu đề xuất thêm chỉ mục.
- [ ] Đã lưu kết quả trước/sau để xác nhận thay đổi thực sự cải thiện hệ thống.

Quét toàn bảng và quét tuần tự là những cơ chế truy cập cần thiết trong nhiều workload. Khi truy vấn cần đọc phần lớn dữ liệu, scan có thể giảm số lần truy cập rời rạc và tận dụng khả năng đọc theo lô. Khi truy vấn chỉ cần một phần rất nhỏ của bảng, scan lớn có thể là dấu hiệu cần kiểm tra chỉ mục, thống kê hoặc điều kiện lọc. Đọc plan cùng số liệu runtime và tải đồng thời giúp xác định đúng trường hợp nào nên giữ scan và trường hợp nào cần thay đổi access path.
