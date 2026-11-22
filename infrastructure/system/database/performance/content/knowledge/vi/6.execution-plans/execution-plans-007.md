# So sánh kế hoạch với nhiều giá trị tham số và nhiều kích thước dữ liệu

Trong chương **Kế hoạch thực thi** của module **DATABASE_PERFORMANCE**, việc đọc execution plan cần gắn với cách dữ liệu và tải thực tế thay đổi. Một câu SQL có thể nhận nhiều giá trị tham số: có giá trị khớp vài dòng, có giá trị khớp hàng trăm nghìn dòng; có khoảng ngày chỉ chứa dữ liệu của một giờ, có khoảng ngày bao phủ nhiều năm. Khi bảng lớn dần hoặc phân bố dữ liệu thay đổi, kế hoạch từng chạy tốt có thể trở nên tốn kém.

Vì vậy, không nên đánh giá một câu truy vấn chỉ bằng một lần chạy với một bộ tham số và một bộ dữ liệu nhỏ. Cần tạo các nhóm tham số đại diện, kiểm tra nhiều quy mô dữ liệu, đọc kế hoạch ước lượng và kế hoạch thực tế, rồi so sánh thời gian, I/O, CPU, bộ nhớ và độ ổn định dưới tải đồng thời. Mục tiêu là hiểu khi nào optimizer chọn kế hoạch phù hợp, khi nào ước lượng sai và vì sao một kế hoạch có thể tốt cho nhóm tham số này nhưng kém cho nhóm khác.

## 1. Vì sao cùng một câu SQL có thể có nhiều kế hoạch phù hợp

Optimizer chọn kế hoạch dựa trên cấu trúc câu lệnh, chỉ mục, thống kê dữ liệu, tham số có thể biết tại thời điểm tối ưu và các thiết lập của hệ quản trị. Một kế hoạch không có chi phí thấp nhất trong mọi tình huống.

Giả sử ứng dụng quản lý đơn hàng có bảng `orders` với các cột:

| Cột | Ý nghĩa | Đặc điểm phân bố có thể gặp |
|---|---|---|
| `order_id` | Mã đơn hàng | Khóa duy nhất |
| `tenant_id` | Khách hàng hoặc đơn vị sở hữu | Một số tenant rất lớn, nhiều tenant nhỏ |
| `status` | Trạng thái đơn hàng | Một trạng thái phổ biến, một trạng thái hiếm |
| `created_at` | Thời điểm tạo | Dữ liệu tăng theo thời gian |
| `total_amount` | Tổng giá trị | Phân bố lệch, có ngoại lệ lớn |

Truy vấn tra cứu đơn hàng có thể có dạng:

```sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE tenant_id = :tenant_id
  AND status = :status
  AND created_at >= :from_time
ORDER BY created_at DESC
LIMIT 50;
```

Với một tenant nhỏ và trạng thái hiếm, điều kiện có thể chỉ khớp vài dòng. Một index seek hoặc index range scan có thể đọc ít trang và trả kết quả nhanh. Với tenant chiếm phần lớn bảng và trạng thái phổ biến, cùng điều kiện có thể khớp hàng triệu dòng. Optimizer có thể chọn quét tuần tự hoặc quét phạm vi rộng vì truy cập chỉ mục rồi quay lại bảng nhiều lần sẽ tốn kém hơn.

Sự khác nhau này không tự động có nghĩa optimizer sai. **Kế hoạch tốt là kế hoạch có tổng chi phí thực tế thấp trong điều kiện cụ thể**, không phải kế hoạch có tên operator trông tối ưu nhất. Một sequential scan đôi khi hợp lý; một index seek đôi khi vẫn chậm nếu nó lặp lại quá nhiều lần hoặc phải đọc nhiều trang dữ liệu.

## 2. Ba chiều cần thay đổi khi kiểm thử

Để đánh giá độ bền của kế hoạch, cần xem đồng thời ba chiều: giá trị tham số, phân bố dữ liệu và quy mô dữ liệu.

### 2.1. Giá trị tham số và độ chọn lọc

Độ chọn lọc (*selectivity*) mô tả tỷ lệ dòng thỏa mãn điều kiện. Nếu điều kiện trả về 10 dòng trong bảng 10 triệu dòng, nó có độ chọn lọc cao; nếu trả về 7 triệu dòng thì độ chọn lọc thấp. Trong thực tế, không chỉ số lượng dòng mà cả vị trí vật lý, mức phân cụm, số cột cần đọc và thứ tự sắp xếp cũng ảnh hưởng chi phí.

Không nên chỉ chọn một giá trị tham số trung bình. Hãy phân loại tham số thành các nhóm đại diện:

| Nhóm | Ví dụ | Điều cần quan sát |
|---|---|---|
| Giá trị rất hiếm | Tenant nhỏ, trạng thái hiếm | Optimizer có tận dụng chỉ mục để đọc ít dòng không? |
| Giá trị phổ biến | Tenant lớn, trạng thái thường gặp | Index scan có phải đọc quá nhiều trang và truy cập bảng nhiều lần không? |
| Giá trị không có kết quả | Mã tenant hoặc khoảng thời gian không khớp | Optimizer có ước lượng hợp lý cho trường hợp rỗng không? |
| Khoảng hẹp | Một giờ hoặc một ngày | Điều kiện range có giới hạn số dòng tốt không? |
| Khoảng rộng | Nhiều tháng hoặc nhiều năm | Kế hoạch có chuyển sang scan hoặc chiến lược khác hợp lý không? |
| Giá trị lệch mạnh | Một tenant chứa phần lớn dữ liệu | Thống kê có phản ánh phân bố lệch và giá trị phổ biến không? |

Độ chọn lọc của nhiều điều kiện kết hợp có thể khác xa tích số các độ chọn lọc riêng lẻ. Ví dụ, `tenant_id` và `status` có tương quan: tenant lớn có thể có tỷ lệ đơn hàng `OPEN` cao hơn tenant nhỏ. Thống kê từng cột riêng biệt có thể không mô tả đầy đủ tương quan đó.

### 2.2. Phân bố và độ lệch dữ liệu

Hai bảng có cùng số dòng vẫn có thể tạo ra kế hoạch khác nhau. Một bảng phân bố đều theo `tenant_id`; bảng khác có một tenant chiếm 70% dữ liệu. Một trạng thái có thể chiếm gần như toàn bộ dòng trong bảng, trong khi trạng thái khác chỉ xuất hiện ở một phần rất nhỏ.

Các đặc điểm nên kiểm tra:

- Tần suất giá trị phổ biến và hiếm, độ lệch (*skew*) giữa các nhóm.
- Tương quan giữa các cột thường xuất hiện cùng điều kiện lọc.
- Số giá trị phân biệt, giá trị `NULL`, khoảng min/max và phân bố theo thời gian.
- Mức phân cụm vật lý của dữ liệu so với thứ tự khóa chỉ mục.
- Tốc độ tăng dữ liệu và thay đổi phân bố sau các đợt nhập hoặc xóa dữ liệu lớn.

Thống kê cũ có thể khiến optimizer ước lượng số dòng sai. Khi dữ liệu thay đổi đáng kể, cần kiểm tra thời điểm cập nhật thống kê và cách lấy mẫu trước khi quy lỗi cho optimizer.

### 2.3. Kích thước dữ liệu

Hãy kiểm thử ít nhất một quy mô gần hiện tại và các quy mô dự kiến trong vòng đời hệ thống. Ví dụ, nếu bảng hiện có khoảng một triệu dòng và dự kiến tăng lên vài chục triệu dòng, cần kiểm tra kế hoạch ở cả hai mức. Khi dữ liệu tăng, những yếu tố sau có thể đổi:

- Bảng và chỉ mục có vượt bộ nhớ đệm hay không.
- Số trang phải đọc, độ sâu cây chỉ mục và mức phân mảnh.
- Số dòng trung gian của join, sort hoặc aggregate.
- Bộ nhớ cần cho hash và sort; thao tác có tràn ra vùng tạm không.
- Khả năng dùng song song và mức tranh chấp CPU, I/O khi có nhiều truy vấn.

Không chỉ tăng số dòng bằng cách nhân bản dữ liệu giống hệt. Dataset kiểm thử cần giữ đặc điểm phân bố, độ lệch, tương quan và độ dài giá trị gần với production. Nếu chỉ nhân bản cùng một nhóm giá trị, thống kê có thể không đại diện cho dữ liệu thật.

## 3. Thiết kế ma trận kiểm thử

Một ma trận kiểm thử giúp tránh lựa chọn tùy ý các bộ tham số. Có thể bắt đầu bằng cách kết hợp ba nhóm tham số với ba quy mô dữ liệu:

| Bộ thử | Tham số | Quy mô dữ liệu | Mục đích |
|---|---|---|---|
| A | Tenant nhỏ, trạng thái hiếm, khoảng hẹp | Nhỏ | Kiểm tra đường truy cập có chọn lọc cao |
| B | Tenant lớn, trạng thái phổ biến, khoảng rộng | Nhỏ | Kiểm tra optimizer với phân bố lệch ở quy mô nhỏ |
| C | Tenant nhỏ, trạng thái hiếm, khoảng hẹp | Lớn | Xem kế hoạch có giữ hiệu quả khi bảng tăng |
| D | Tenant lớn, trạng thái phổ biến, khoảng rộng | Lớn | Kiểm tra tình huống trả về nhiều dòng và scan rộng |
| E | Tenant không tồn tại hoặc khoảng rỗng | Nhỏ và lớn | Kiểm tra ước lượng và chi phí khi không có kết quả |
| F | Tham số đại diện cho median workload | Nhỏ và lớn | Đo hiệu năng ở tình huống phổ biến |

Không nhất thiết phải chạy toàn bộ tích Descartes của mọi giá trị. Hãy chọn những tổ hợp có ý nghĩa với nghiệp vụ và có khả năng làm thay đổi độ chọn lọc hoặc kế hoạch. Với hệ thống đa tenant, nên có tenant lớn nhất, tenant trung vị và một tenant nhỏ; với bảng sự kiện, nên có khoảng thời gian ngắn, thường gặp và dài.

Ghi lại mỗi lần thử với cùng một bộ thông tin:

| Trường | Nội dung cần ghi |
|---|---|
| Query identity | Tên truy vấn, query hash hoặc query id nếu hệ quản trị cung cấp |
| Tham số | Giá trị hoặc nhóm giá trị, khoảng ngày, trạng thái |
| Dataset | Số dòng bảng, số dòng từng nhóm quan trọng, kích thước bảng và chỉ mục |
| Thống kê | Thời điểm cập nhật, chế độ lấy mẫu và histogram nếu có |
| Môi trường | Phiên bản, cấu hình, mức đồng thời, trạng thái cache |
| Kế hoạch | Plan hash/id, operator chính, estimated rows và actual rows |
| Kết quả | Elapsed, CPU, logical/physical reads, wait, memory, spill và số dòng trả về |

## 4. Cách đọc và so sánh kế hoạch

Khi so sánh hai kế hoạch, hãy đi từ cấu trúc tổng thể tới các nút có chi phí lớn. Không nên kết luận chỉ dựa trên tổng `cost` mà optimizer hiển thị. Cost là ước lượng nội bộ dùng để so sánh phương án trong cùng bối cảnh; nó không phải thời gian thực tế tính bằng millisecond.

### 4.1. Những phần cần so sánh

1. **Access path:** table scan, sequential scan, index seek, index range scan, bitmap scan hoặc index scan. Kiểm tra số trang và số dòng thực sự được đọc.
2. **Join strategy:** nested loop, hash join hoặc merge join. Nested loop thường phù hợp khi phía ngoài nhỏ và phía trong có đường truy cập hiệu quả; hash join có thể phù hợp với tập dữ liệu lớn hơn nhưng cần bộ nhớ.
3. **Estimated rows và actual rows:** sai lệch lớn có thể khiến optimizer chọn join, thứ tự join hoặc cấp phát bộ nhớ không phù hợp.
4. **Loops và số lần thực thi operator:** một nút có thời gian thấp mỗi lần nhưng bị gọi hàng trăm nghìn lần vẫn có thể chiếm phần lớn chi phí.
5. **Sort, aggregate và dữ liệu tạm:** xem sort có tận dụng thứ tự chỉ mục không, hash/sort có tràn ra đĩa hay không.
6. **Parallelism:** kiểm tra số worker, thời gian chờ đồng bộ, CPU cộng dồn và hiệu quả tăng tốc. Nhiều worker hơn không luôn làm truy vấn nhanh hơn.
7. **Memory grant hoặc work memory:** xác định bộ nhớ cấp phát có quá lớn, quá nhỏ hoặc gây cạnh tranh giữa nhiều truy vấn không.
8. **Predicate và residual filter:** phân biệt điều kiện được dùng để tìm phạm vi trong chỉ mục với điều kiện phải lọc sau khi đọc dữ liệu.

### 4.2. Đo kế hoạch thực tế

Kế hoạch ước lượng cho biết optimizer dự đoán điều gì. Kế hoạch thực tế cho biết truy vấn đã làm gì trong một lần chạy cụ thể. Cần đối chiếu cả hai, đồng thời lưu ý việc thu thập runtime plan có thể tạo thêm chi phí và chỉ phản ánh lần thực thi được đo.

Ở PostgreSQL, ví dụ:

```sql
EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
SELECT order_id, created_at, total_amount
FROM orders
WHERE tenant_id = 42
  AND status = 'OPEN'
  AND created_at >= TIMESTAMPTZ '2026-01-01 00:00:00+07'
ORDER BY created_at DESC
LIMIT 50;
```

Ghi lại `Planning Time`, `Execution Time`, `actual rows`, `loops`, `Buffers` và các thông tin liên quan. Với `EXPLAIN ANALYZE`, câu lệnh được thực thi thật; chỉ dùng trên truy vấn đọc an toàn hoặc môi trường thử nghiệm khi có thao tác ghi. Kết quả của một lần chạy không đại diện cho mọi giá trị tham số.

Ở MySQL 8.0.18 trở lên, `EXPLAIN ANALYZE` có thể hiển thị cây thực thi kèm thời gian và số dòng thực tế. Cần kiểm tra phiên bản vì cú pháp và khả năng hỗ trợ khác nhau. Có thể dùng `EXPLAIN FORMAT=TREE` để xem cấu trúc kế hoạch mà không thực thi truy vấn theo cách của `EXPLAIN ANALYZE`.

Ở SQL Server, bật Actual Execution Plan trong công cụ truy vấn và kết hợp:

```sql
SET STATISTICS IO ON;
SET STATISTICS TIME ON;

SELECT order_id, created_at, total_amount
FROM dbo.orders
WHERE tenant_id = @tenant_id
  AND status = @status
  AND created_at >= @from_time
ORDER BY created_at DESC;

SET STATISTICS IO OFF;
SET STATISTICS TIME OFF;
```

Đọc actual rows, estimated rows, logical reads, CPU time, elapsed time, memory grant và cảnh báo spill nếu có. `SET STATISTICS TIME` và `SET STATISTICS IO` bổ sung số liệu thực thi; chúng không thay thế việc ghi lại tham số và bối cảnh chạy.

## 5. Kiểm tra độ nhạy tham số và cơ chế tái sử dụng kế hoạch

Một số hệ quản trị có thể tái sử dụng kế hoạch đã biên dịch. Nếu kế hoạch được tạo dựa trên một giá trị tham số có độ chọn lọc rất khác các lần chạy sau, hiệu năng có thể dao động. Hiện tượng này thường được gọi là *parameter sensitivity* hoặc *parameter sniffing* tùy hệ quản trị.

### 5.1. PostgreSQL: generic plan và custom plan

PostgreSQL có thể thực thi prepared statement bằng kế hoạch tùy biến theo giá trị tham số (*custom plan*) hoặc kế hoạch tổng quát không phụ thuộc một bộ giá trị cụ thể (*generic plan*). Chế độ `plan_cache_mode = auto` cho phép PostgreSQL lựa chọn dựa trên chi phí ước lượng của các lần lập kế hoạch ban đầu. Với dữ liệu lệch mạnh, generic plan có thể không tối ưu cho một số nhóm tham số.

Ví dụ tạo prepared statement:

```sql
PREPARE orders_by_tenant(bigint, text, timestamptz) AS
SELECT order_id, created_at, total_amount
FROM orders
WHERE tenant_id = $1
  AND status = $2
  AND created_at >= $3
ORDER BY created_at DESC
LIMIT 50;

EXPLAIN (ANALYZE, BUFFERS)
EXECUTE orders_by_tenant(
    42,
    'OPEN',
    TIMESTAMPTZ '2026-01-01 00:00:00+07'
);
```

Để chẩn đoán, có thể so sánh kế hoạch khi ép custom và generic trong một session thử nghiệm:

```sql
SET plan_cache_mode = force_custom_plan;
EXPLAIN (ANALYZE, BUFFERS)
EXECUTE orders_by_tenant(
    42, 'OPEN', TIMESTAMPTZ '2026-01-01 00:00:00+07'
);

SET plan_cache_mode = force_generic_plan;
EXPLAIN (ANALYZE, BUFFERS)
EXECUTE orders_by_tenant(
    42, 'OPEN', TIMESTAMPTZ '2026-01-01 00:00:00+07'
);

RESET plan_cache_mode;
```

Đây là phép thử chẩn đoán. Không nên đặt `force_custom_plan` hoặc `force_generic_plan` ở phạm vi rộng chỉ dựa trên một truy vấn. Custom plan có thêm chi phí lập kế hoạch; generic plan giảm chi phí lập kế hoạch nhưng có thể không thích nghi với giá trị lệch. Hãy đo cả planning time và execution time trên nhiều nhóm tham số.

### 5.2. SQL Server: parameter sniffing và parameter-sensitive plan

SQL Server có thể dùng giá trị tham số lúc biên dịch để ước lượng cardinality và tạo kế hoạch được tái sử dụng. Đây là cơ chế hữu ích khi workload ổn định, nhưng có thể tạo ra kế hoạch không phù hợp nếu lần biên dịch đầu tiên dùng tham số hiếm trong khi các lần sau dùng tham số phổ biến, hoặc ngược lại.

Khi điều tra, cần:

- Ghi nhận giá trị tham số đã dùng trong lần chạy chậm và lần chạy nhanh.
- So sánh actual execution plan và estimated rows ở các operator quan trọng.
- Kiểm tra plan được tái sử dụng, thống kê liên quan và thay đổi phân bố dữ liệu.
- Xem Query Store để xác định kế hoạch nào gắn với khoảng thời gian hiệu năng tốt hoặc xấu.
- Kiểm tra tính năng Parameter Sensitive Plan (PSP) trên SQL Server 2022 với compatibility level phù hợp. PSP có thể tạo dispatcher plan và các query variant cho những nhóm độ chọn lọc khác nhau; không phải mọi truy vấn đều đủ điều kiện áp dụng.

Các cách xử lý như `OPTION (RECOMPILE)`, `OPTIMIZE FOR`, thay đổi parameterization hoặc force plan đều có trade-off. `RECOMPILE` có thể dùng giá trị hiện tại để tạo kế hoạch mới nhưng tăng chi phí biên dịch. `OPTIMIZE FOR UNKNOWN` có thể giảm phụ thuộc vào một giá trị cụ thể nhưng kế hoạch trung bình không chắc tốt cho nhóm lệch. Chỉ áp dụng sau khi đã có ma trận đo và xác định rõ workload nào được cải thiện hoặc suy giảm.

### 5.3. MySQL: thống kê, histogram và giá trị range

MySQL optimizer sử dụng thống kê chỉ mục và các thông tin về phân bố dữ liệu để ước lượng số dòng. Với dữ liệu lệch, thống kê không đủ mới hoặc histogram chưa phù hợp, số dòng ước lượng có thể sai. Giá trị tham số trong điều kiện bằng hoặc khoảng có thể dẫn tới số dòng dự kiến khác nhau.

Có thể cập nhật thống kê chỉ mục bằng:

```sql
ANALYZE TABLE orders;
```

Với MySQL 8.0, histogram một cột có thể giúp optimizer hiểu phân bố của cột không được mô tả đủ bởi thống kê chỉ mục:

```sql
ANALYZE TABLE orders
UPDATE HISTOGRAM ON status, tenant_id
WITH 100 BUCKETS;
```

Histogram giúp mô tả tần suất hoặc phân bố của từng cột, nhưng không tự mô tả đầy đủ tương quan giữa nhiều cột. Nếu `tenant_id` và `status` có tương quan mạnh, cần kiểm tra sai lệch ước lượng bằng `EXPLAIN ANALYZE` và đánh giá thiết kế chỉ mục hoặc cách biểu diễn dữ liệu. Không nên tạo histogram hoặc tăng số bucket một cách máy móc; cần xác nhận nó cải thiện ước lượng và kế hoạch trong nhóm truy vấn mục tiêu.

## 6. So sánh ở nhiều quy mô dữ liệu

Kế hoạch có thể thay đổi khi bảng tăng kích thước, ngay cả khi giá trị tham số không đổi. Một chỉ mục hiệu quả trên bảng 50 nghìn dòng có thể không còn đáp ứng tốt khi bảng lên 100 triệu dòng nếu điều kiện lọc trả về tỷ lệ lớn dữ liệu hoặc chỉ mục không bao phủ các cột cần đọc.

Khi so sánh quy mô, cần kiểm soát các yếu tố sau:

- **Tỷ lệ phân bố:** giữ tỷ lệ tenant lớn/nhỏ, trạng thái phổ biến/hiếm và dữ liệu gần đây/cũ tương tự thực tế.
- **Thống kê:** cập nhật thống kê sau khi nạp dữ liệu; ghi nhận sampling, histogram và thời điểm cập nhật.
- **Cache:** tách kết quả warm cache và cold cache nếu cả hai có ý nghĩa với production. Không cố ý xóa cache trên máy chủ dùng chung nếu không có kế hoạch kiểm soát.
- **Lưu trữ:** dùng cùng loại storage và cấu hình I/O hoặc ghi rõ khác biệt giữa môi trường.
- **Đồng thời:** thử cả truy vấn đơn lẻ lẫn mức đồng thời đại diện; một plan tốt đơn lẻ có thể gây tranh chấp CPU, memory hoặc I/O khi nhiều session cùng chạy.
- **Tác vụ nền:** kiểm soát vacuum, analyze, backup, batch load và các tác vụ có thể làm thay đổi số liệu.

Nên lưu một baseline cho mỗi mức dữ liệu. Không chỉ lưu ảnh chụp plan; hãy lưu SQL, tham số, số dòng bảng, thống kê, cấu hình, số liệu runtime và ngày đo. Khi hệ thống tăng dữ liệu, chạy lại đúng bộ thử để nhận ra lúc nào plan thay đổi và hiệu năng bắt đầu suy giảm.

## 7. Ví dụ phân tích kế hoạch thay đổi theo tham số

Giả sử bảng `orders` có 40 triệu dòng. Một chỉ mục hiện có là `(tenant_id, status, created_at)`. Ma trận đo cho thấy:

| Bộ tham số | Số dòng ước lượng | Số dòng thực tế | Kế hoạch | Elapsed minh họa |
|---|---:|---:|---|---:|
| Tenant nhỏ, `CANCELLED`, 1 ngày | 20 | 18 | Index range scan | 4 ms |
| Tenant lớn, `OPEN`, 1 ngày | 80.000 | 620.000 | Index range scan + lookup | 780 ms |
| Tenant lớn, `OPEN`, 2 năm | 1.200.000 | 14.000.000 | Sequential/table scan | 1.900 ms |
| Tenant không tồn tại | 1 | 0 | Index lookup | 2 ms |

Đây là số liệu giả định để minh họa cách đọc. Ở dòng thứ hai, sai lệch ước lượng lớn có thể khiến optimizer đánh giá thấp số lần truy cập bảng sau khi đọc chỉ mục. Ở dòng thứ ba, scan toàn bảng có thể là lựa chọn hợp lý vì điều kiện trả về phần lớn dữ liệu. Không thể kết luận chỉ mục bị lỗi chỉ vì optimizer chọn scan.

Các bước điều tra:

1. Kiểm tra thống kê về `tenant_id`, `status` và `created_at`; xác định có histogram hoặc thống kê mở rộng phù hợp hay không.
2. Đối chiếu actual rows với estimated rows ở từng operator, không chỉ nhìn tổng số dòng cuối cùng.
3. Xác định index lookup có đọc nhiều trang ngẫu nhiên hay không và các cột được chọn có thể được bao phủ bởi chỉ mục một cách hợp lý không.
4. Kiểm tra mức phân cụm dữ liệu, độ rộng chỉ mục và chi phí ghi nếu định thay đổi thứ tự cột hoặc thêm chỉ mục bao phủ.
5. Chạy lại ma trận với tenant nhỏ, tenant lớn, trạng thái hiếm/phổ biến và khoảng ngày ngắn/dài.
6. Đo dưới tải đồng thời để xem kế hoạch có làm tăng I/O, CPU hoặc memory pressure cho các truy vấn khác không.

Giải pháp có thể là cập nhật thống kê, bổ sung histogram hoặc thống kê tương quan, thay đổi thứ tự cột chỉ mục, giảm số cột cần đọc, tách truy vấn theo nhóm tham số, hoặc để optimizer chọn các kế hoạch khác nhau. Chỉ chọn phương án sau khi so sánh toàn bộ ma trận và chi phí duy trì chỉ mục.

## 8. Tiêu chí đánh giá và cách ghi kết quả

Một báo cáo so sánh nên có cả chỉ số về kế hoạch lẫn chỉ số về kết quả thực tế:

| Nhóm | Chỉ số | Cách dùng |
|---|---|---|
| Độ chính xác ước lượng | Estimated rows so với actual rows | Tìm nơi optimizer đánh giá sai cardinality |
| Thời gian | Planning/compile time, elapsed time, CPU time | Tách chi phí lập kế hoạch và thực thi |
| I/O | Logical reads, physical reads, buffer hits, read latency | Đo lượng dữ liệu phải truy cập và mức phụ thuộc lưu trữ |
| Bộ nhớ | Memory grant, sort/hash memory, spill, temp usage | Phát hiện cấp phát không phù hợp hoặc tràn ra đĩa |
| Cấu trúc kế hoạch | Access path, join order, join type, loops, parallelism | Giải thích vì sao chi phí thay đổi |
| Chất lượng dịch vụ | p50, p95, p99, throughput, lỗi và timeout | Đánh giá trải nghiệm dưới tải thực tế |
| Ổn định | Plan changes, số lần compile, biến động theo thời gian | Phát hiện hồi quy và độ nhạy tham số |

Không dùng một ngưỡng tuyệt đối cho mọi truy vấn. Ví dụ, 100 ms có thể là chậm với endpoint tra cứu đơn giản nhưng phù hợp với báo cáo tổng hợp lớn. Hãy so sánh với SLO của workload và đường cơ sở trước đó.

Khi ghi nhận kết quả, hãy ghi rõ:

- Câu SQL và schema/index liên quan.
- Bộ tham số thực tế hoặc lớp tham số, không ghi dữ liệu nhạy cảm không cần thiết.
- Kích thước bảng, phân bố dữ liệu và thời điểm cập nhật thống kê.
- Kế hoạch và operator khác biệt giữa các lần thử.
- Điều kiện cache, tải đồng thời, cấu hình và phiên bản.
- Kết quả trước/sau, độ biến động và ảnh hưởng đến các workload khác.

## 9. Những sai lầm thường gặp

- **Chỉ kiểm thử một bộ tham số:** bỏ sót tenant lớn, giá trị phổ biến, khoảng rộng hoặc dữ liệu rỗng.
- **Chỉ kiểm thử bảng nhỏ:** kế hoạch có thể đổi khi bảng vượt kích thước cache hoặc khi số dòng trung gian tăng mạnh.
- **Dùng dữ liệu phân bố đều giả tạo:** không phát hiện được skew và tương quan của production.
- **Cho rằng một plan phải thắng mọi trường hợp:** index seek không luôn tốt hơn scan; kế hoạch đúng phụ thuộc lượng dữ liệu cần đọc.
- **So sánh optimizer cost như thời gian thực:** cost là ước lượng nội bộ, cần đối chiếu actual runtime và tài nguyên.
- **Bỏ qua sai lệch cardinality:** số dòng ước lượng sai có thể dẫn đến join order, memory grant và access path kém.
- **Ép một kế hoạch cho mọi giá trị tham số:** có thể chữa trường hợp này nhưng làm chậm trường hợp khác.
- **Chạy thử khi cache và tải không được kiểm soát:** kết quả bị ảnh hưởng bởi cache, tác vụ nền và người dùng khác.
- **Chỉ đo một lần:** thời gian chịu ảnh hưởng của hệ điều hành, I/O và tải; cần lặp đủ số lần và so sánh phân vị.
- **Thêm chỉ mục mà không đo chi phí ghi:** chỉ mục mới tăng dung lượng, công việc insert/update/delete và chi phí bảo trì.

## 10. Checklist trước khi chấp nhận thay đổi

- [ ] Đã chọn các nhóm tham số hiếm, phổ biến, rỗng, khoảng hẹp và khoảng rộng phù hợp nghiệp vụ.
- [ ] Đã kiểm thử ở quy mô dữ liệu hiện tại và quy mô tăng trưởng dự kiến.
- [ ] Đã giữ phân bố và độ lệch dữ liệu gần với production.
- [ ] Đã cập nhật hoặc ghi nhận thống kê và histogram trước khi đo.
- [ ] Đã so sánh estimated rows với actual rows ở các operator quan trọng.
- [ ] Đã ghi lại plan, elapsed, CPU, logical/physical reads, memory và spill.
- [ ] Đã đo nhiều lần, phân biệt warm cache và cold cache khi cần.
- [ ] Đã kiểm tra hiệu năng ở mức đồng thời đại diện và ảnh hưởng tới workload khác.
- [ ] Đã đánh giá chi phí ghi, dung lượng và bảo trì nếu thêm hoặc sửa chỉ mục.
- [ ] Đã lưu baseline, điều kiện thử và cách quay lại nếu kết quả sau triển khai xấu đi.

So sánh kế hoạch với nhiều giá trị tham số và nhiều kích thước dữ liệu giúp phát hiện sớm độ nhạy tham số, sai lệch thống kê và điểm gãy khi dữ liệu tăng. Khi kết hợp ma trận kiểm thử với số liệu thực thi và tải đồng thời, nhóm có thể chọn cách tối ưu phù hợp cho từng nhóm workload và giữ hiệu năng ổn định trong quá trình hệ thống phát triển.
