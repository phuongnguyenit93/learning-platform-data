# Tương quan giữa các cột và giới hạn của giả định độc lập

Trong chương **Thống kê và ước lượng** của module **DATABASE_PERFORMANCE**, việc hiểu cách optimizer ước lượng số dòng là nền tảng để đọc kế hoạch thực thi và tìm nguyên nhân truy vấn chậm. Một nguồn sai lệch phổ biến xuất hiện khi điều kiện lọc liên quan đến nhiều cột có tương quan với nhau, nhưng thống kê mà hệ quản trị đang dùng chỉ mô tả từng cột riêng lẻ.

Khi không có thông tin về mối liên hệ giữa các cột, optimizer có thể ước lượng như thể các điều kiện độc lập. Giả định này đôi khi đủ tốt, nhưng có thể sai rất xa với dữ liệu thực tế. Sai lệch số dòng có thể dẫn đến chọn sai thứ tự join, access path, kiểu join hoặc lượng bộ nhớ cấp phát. Bài học này giải thích giả định độc lập, cách nhận biết tương quan, cách đọc sai lệch estimated rows so với actual rows và các cơ chế thống kê nhiều cột trong những hệ quản trị phổ biến.

## 1. Giả định độc lập trong ước lượng số dòng

Optimizer cần dự đoán số dòng thỏa mãn điều kiện trước khi thực thi. Với một bảng có (N) dòng và một điều kiện lọc (A), số dòng ước lượng thường được mô hình hóa bằng:

\[
\widehat{N_A} = N \times \widehat{P(A)}
\]

Trong đó \(\widehat{P(A)}\) là độ chọn lọc ước lượng từ thống kê. Khi có hai điều kiện `A` và `B` kết hợp bằng `AND`, nếu không có thông tin về quan hệ giữa chúng, optimizer có thể sử dụng giả định:

\[
P(A \cap B) \approx P(A) \times P(B)
\]

Ví dụ, bảng `orders` có 10 triệu dòng. Thống kê riêng lẻ cho biết:

- 10% đơn hàng thuộc `tenant_id = 42`.
- 20% đơn hàng có `status = 'OPEN'`.

Nếu coi hai điều kiện độc lập, số dòng ước lượng là:

\[
10.000.000 \times 0,10 \times 0,20 = 200.000
\]

Nhưng giả sử tenant 42 là khách hàng lớn và 80% đơn hàng của tenant này đang ở trạng thái `OPEN`. Số dòng thực tế là:

\[
10.000.000 \times 0,10 \times 0,80 = 800.000
\]

Ước lượng độc lập thấp hơn thực tế bốn lần. Ở một tình huống khác, nếu chỉ 2% đơn hàng của tenant 42 có trạng thái `OPEN`, số dòng thực tế chỉ là 20.000; khi đó giả định độc lập lại ước lượng cao hơn mười lần.

Điều cần nhớ là xác suất đồng thời phải được suy ra từ phân bố kết hợp, không phải lúc nào cũng bằng tích xác suất riêng lẻ. Với hai điều kiện bất kỳ:

\[
P(A \cap B) = P(A) \times P(B \mid A)
\]

Giả định độc lập thay \(P(B \mid A)\) bằng \(P(B)\). Khi xác suất của `B` thay đổi đáng kể theo giá trị của `A`, phép thay thế này tạo ra sai số.

## 2. Nhận biết tương quan giữa các cột

Tương quan xuất hiện khi phân bố của một cột phụ thuộc vào giá trị của cột khác. Nó có thể là quan hệ gần như xác định, quan hệ thống kê mạnh hoặc quan hệ yếu chỉ xuất hiện ở một số nhóm dữ liệu.

### 2.1. Ví dụ trong dữ liệu nghiệp vụ

| Cột thứ nhất | Cột thứ hai | Mối liên hệ có thể gặp |
|---|---|---|
| `tenant_id` | `status` | Tenant lớn có tỷ lệ đơn hàng đang mở khác tenant nhỏ |
| `city` | `postal_code` | Mã bưu chính chỉ thuộc một hoặc một số khu vực nhất định |
| `country_code` | `currency_code` | Một số quốc gia chủ yếu sử dụng một loại tiền tệ |
| `product_category` | `brand_id` | Một thương hiệu chỉ xuất hiện trong một số nhóm sản phẩm |
| `event_date` | `event_type` | Một loại sự kiện tăng mạnh trong một giai đoạn |
| `account_type` | `risk_level` | Phân bố mức rủi ro thay đổi theo loại tài khoản |

Ví dụ, câu truy vấn sau lọc theo hai cột:

```sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE tenant_id = 42
  AND status = 'OPEN';
```

Nếu tenant 42 có tỷ lệ đơn hàng `OPEN` khác hẳn tỷ lệ chung của toàn bảng, thống kê riêng của `tenant_id` và `status` không đủ để mô tả chính xác số dòng của tổ hợp này. Câu truy vấn có thể bị ước lượng sai ngay cả khi thống kê từng cột đều mới và chính xác.

### 2.2. Tương quan dương, tương quan âm và quan hệ phụ thuộc

- **Tương quan dương:** một giá trị ở cột này thường xuất hiện cùng một giá trị hoặc nhóm giá trị ở cột kia. Ví dụ, một `tenant_id` lớn có tỷ lệ `status = 'OPEN'` cao.
- **Tương quan âm:** khi một điều kiện đúng, điều kiện kia ít có khả năng đúng hơn mức trung bình. Ví dụ, một nhóm sản phẩm gần như không có trạng thái khuyến mãi.
- **Phụ thuộc gần như xác định:** biết giá trị cột thứ nhất gần như suy ra được cột thứ hai. Ví dụ, `postal_code` thường xác định một khu vực hành chính trong một quốc gia.
- **Tương quan cục bộ:** mối liên hệ chỉ tồn tại ở một nhóm giá trị hoặc trong một khoảng thời gian. Ví dụ, một loại sự kiện tăng mạnh trong một chiến dịch ngắn hạn.

Không nên nhầm tương quan với quan hệ nhân quả. Việc hai cột thường xuất hiện cùng nhau không chứng minh cột này gây ra cột kia. Đối với optimizer, điều quan trọng là phân bố kết hợp có giúp dự đoán số dòng tốt hơn hay không.

### 2.3. Cách kiểm tra phân bố thực tế

Hãy đo phân bố kết hợp trên dữ liệu đại diện. Ví dụ:

```sql
SELECT tenant_id,
       status,
       COUNT(*) AS row_count
FROM orders
GROUP BY tenant_id, status
ORDER BY row_count DESC;
```

Để so sánh tỷ lệ `OPEN` giữa các tenant:

```sql
SELECT tenant_id,
       COUNT(*) AS total_orders,
       SUM(CASE WHEN status = 'OPEN' THEN 1 ELSE 0 END) AS open_orders,
       1.0 * SUM(CASE WHEN status = 'OPEN' THEN 1 ELSE 0 END)
           / NULLIF(COUNT(*), 0) AS open_ratio
FROM orders
GROUP BY tenant_id
ORDER BY total_orders DESC;
```

Kết quả giúp phát hiện tenant lớn, tenant có tỷ lệ trạng thái khác biệt và những nhóm có phân bố lệch. Với bảng lớn, truy vấn tổng hợp có thể tốn tài nguyên; hãy chạy trên replica, bản sao phân tích hoặc trong khoảng tải được kiểm soát nếu cần. Có thể lấy mẫu để khám phá ban đầu, nhưng phải hiểu sai số lấy mẫu và tránh kết luận từ một mẫu không đại diện.

## 3. Vì sao thống kê từng cột chưa đủ

Histogram hoặc thống kê tần suất một cột mô tả phân bố biên (*marginal distribution*) của cột đó. Ví dụ, histogram của `status` có thể cho biết 20% toàn bảng là `OPEN`; histogram của `tenant_id` có thể cho biết tenant 42 chiếm 10% dữ liệu. Hai histogram riêng biệt không cho biết tỷ lệ `OPEN` trong riêng tenant 42.

Có thể hình dung hai bảng dữ liệu có cùng phân bố biên:

| Tập dữ liệu | Tỷ lệ tenant 42 | Tỷ lệ `OPEN` toàn bảng | Tỷ lệ `OPEN` trong tenant 42 |
|---|---:|---:|---:|
| A | 10% | 20% | 80% |
| B | 10% | 20% | 2% |

Hai tập dữ liệu có thể có cùng số dòng của từng giá trị riêng lẻ nhưng số dòng của tổ hợp `tenant_id = 42 AND status = 'OPEN'` khác nhau rất lớn. Optimizer chỉ có thống kê đơn cột không thể phân biệt hai trường hợp này một cách đáng tin cậy.

### 3.1. Ảnh hưởng tới kế hoạch thực thi

Ước lượng sai cardinality có thể tác động dây chuyền:

1. **Chọn access path:** optimizer nghĩ chỉ có vài dòng nên chọn index lookup lặp lại nhiều lần, trong khi thực tế phải đọc hàng trăm nghìn dòng.
2. **Chọn thứ tự join:** optimizer đưa bảng có số dòng thực tế lớn vào phía ngoài nested loop hoặc chọn thứ tự join làm tăng mạnh dữ liệu trung gian.
3. **Chọn kiểu join:** nested loop, hash join hoặc merge join có thể được chọn dựa trên số dòng sai.
4. **Cấp phát bộ nhớ:** hash hoặc sort có thể nhận memory grant quá nhỏ, gây spill ra đĩa; hoặc được cấp quá nhiều bộ nhớ, làm giảm số truy vấn chạy đồng thời.
5. **Dự đoán thời gian và tài nguyên:** kế hoạch có thể tiêu thụ nhiều I/O, CPU hoặc temp space hơn dự kiến.

Một dấu hiệu quan trọng là chênh lệch lớn giữa `estimated rows` và `actual rows` tại một operator. Hãy tìm nút đầu tiên mà sai lệch xuất hiện; các nút phía trên có thể chỉ đang nhận đầu vào sai từ nút trước đó.

### 3.2. Khi giả định độc lập vẫn có ích

Giả định độc lập là một mô hình đơn giản và đôi khi hợp lý. Nếu hai điều kiện gần như không liên quan trong workload, tích các độ chọn lọc riêng có thể là xấp xỉ tốt. Thống kê đa cột cũng có chi phí lưu trữ, thu thập và quản lý; không cần tạo cho mọi tổ hợp cột.

Ưu tiên điều tra khi:

- Một truy vấn lọc đồng thời trên nhiều cột và estimated rows sai rõ rệt.
- Một số giá trị tham số chạy rất nhanh, giá trị khác lại chậm bất thường.
- Thứ tự join hoặc kiểu join không phù hợp với số dòng thực tế.
- Các cột có quan hệ nghiệp vụ rõ ràng hoặc phân bố lệch mạnh.
- Thống kê đơn cột mới nhưng optimizer vẫn ước lượng sai.

## 4. Thống kê nhiều cột trong PostgreSQL

PostgreSQL hỗ trợ extended statistics để mô tả một số đặc điểm của nhiều cột hoặc biểu thức trong cùng một bảng. Các loại thống kê thường dùng gồm:

- `dependencies`: mô tả mức độ phụ thuộc thống kê giữa các cột.
- `mcv`: lưu các tổ hợp giá trị phổ biến nhất (*most common values*) cùng tần suất của chúng.
- `ndistinct`: ước lượng số tổ hợp giá trị phân biệt, hữu ích với `GROUP BY` trên nhiều cột.

### 4.1. Tạo extended statistics

Giả sử truy vấn thường lọc theo `tenant_id` và `status`. Có thể tạo đối tượng thống kê:

```sql
CREATE STATISTICS orders_tenant_status_stats
    (dependencies, mcv, ndistinct)
ON tenant_id, status
FROM orders;

ANALYZE orders;
```

Lệnh `CREATE STATISTICS` khai báo những cột cần mô tả. `ANALYZE` thu thập dữ liệu để điền các thống kê. Tạo đối tượng mà không chạy `ANALYZE` thì optimizer chưa có dữ liệu mới để sử dụng.

Có thể xem thông tin thống kê đã thu thập:

```sql
SELECT statistics_name,
       attnames,
       kinds,
       dependencies,
       most_common_vals,
       most_common_freqs
FROM pg_stats_ext
WHERE schemaname = 'public'
  AND tablename = 'orders';
```

`pg_stats_ext` là view tiện dụng để xem các extended statistics mà người dùng có quyền đọc. Dữ liệu MCV có thể giúp optimizer ước lượng các tổ hợp phổ biến cụ thể thay vì nhân độ chọn lọc biên của từng cột.

### 4.2. Hiểu giới hạn của từng loại

`dependencies` không phải mô hình xác suất tổng quát cho mọi biểu thức. PostgreSQL chủ yếu dùng thống kê phụ thuộc cho các điều kiện so sánh đơn giản giữa cột và hằng số, chẳng hạn `tenant_id = 42` và `status = 'OPEN'`. Nó không giải quyết mọi điều kiện range, mọi biểu thức phức tạp, mọi phép `OR` hay tương quan giữa hai bảng trong join.

`mcv` hữu ích khi các tổ hợp cụ thể xuất hiện đủ thường xuyên để nằm trong danh sách giá trị phổ biến. Nếu tổ hợp hiếm hoặc phân bố thay đổi liên tục, MCV có thể không mô tả đủ tình huống. Có thể điều chỉnh mục tiêu thống kê khi cần, nhưng tăng quá cao sẽ tăng chi phí thu thập và kích thước thống kê.

`ndistinct` hỗ trợ ước lượng số tổ hợp phân biệt, đặc biệt với `GROUP BY` nhiều cột. Nó không thay thế thống kê về tần suất từng tổ hợp khi cần ước lượng một điều kiện lọc cụ thể.

Ví dụ, nếu truy vấn thường nhóm theo cả tenant và trạng thái:

```sql
SELECT tenant_id, status, COUNT(*)
FROM orders
GROUP BY tenant_id, status;
```

thống kê `ndistinct` có thể giúp PostgreSQL ước lượng số nhóm tốt hơn. Nếu mục tiêu chính là điều kiện lọc kết hợp, `dependencies` và `mcv` có thể phù hợp hơn. Chọn loại thống kê theo kiểu sai lệch cần xử lý.

### 4.3. So sánh trước và sau

Trước khi tạo extended statistics, lưu kế hoạch và số liệu runtime của một số bộ tham số đại diện. Sau khi tạo và chạy `ANALYZE`, đo lại với cùng điều kiện:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, created_at, total_amount
FROM orders
WHERE tenant_id = 42
  AND status = 'OPEN';
```

So sánh estimated rows với actual rows ở nút scan và các nút phía trên. Nếu ước lượng cải thiện nhưng thời gian không giảm, có thể kế hoạch cũ vốn đã hợp lý hoặc nút thắt nằm ở I/O, khóa hay tải đồng thời. Mục tiêu đầu tiên của extended statistics là giúp optimizer hiểu dữ liệu tốt hơn; cải thiện thời gian là kết quả cần đo, không phải điều được bảo đảm.

## 5. Thống kê nhiều cột trong SQL Server

SQL Server lưu histogram cho cột đầu tiên của một statistics object nhiều cột và lưu density information cho các tiền tố cột. Thông tin này có thể giúp cardinality estimator hiểu mức độ phân biệt của tổ hợp cột, nhưng không tương đương một histogram hai chiều đầy đủ cho mọi tổ hợp giá trị.

Có thể tạo statistics trên nhóm cột thường được lọc cùng nhau:

```sql
CREATE STATISTICS st_orders_tenant_status
ON dbo.orders (tenant_id, status);
```

Xem histogram và density vector:

```sql
DBCC SHOW_STATISTICS
    ('dbo.orders', 'st_orders_tenant_status')
WITH HISTOGRAM, DENSITY_VECTOR;
```

Trong kết quả:

- Histogram mô tả phân bố của cột đầu tiên trong danh sách statistics.
- Density vector cung cấp thông tin về độ phân biệt của các tiền tố cột, có thể hỗ trợ ước lượng tổ hợp.
- Thống kê nhiều cột không ghi lại mọi tần suất kết hợp có thể có; vì vậy một số tương quan phức tạp vẫn có thể bị ước lượng sai.

Thứ tự cột trong statistics có ý nghĩa. Nếu `tenant_id` là cột đầu tiên, histogram mô tả `tenant_id`; nếu đảo thứ tự, histogram sẽ mô tả `status`. Hãy chọn thứ tự phù hợp với cột có phân bố cần mô tả, đồng thời kiểm tra các truy vấn khác dùng cùng statistics.

Với một nhóm con có phân bố khác biệt mạnh, filtered statistics có thể hữu ích:

```sql
CREATE STATISTICS st_orders_open_tenant
ON dbo.orders (tenant_id)
WHERE status = 'OPEN';
```

Filtered statistics mô tả phân bố trong tập dòng thỏa điều kiện lọc. Chúng phù hợp khi một nhóm dữ liệu có hành vi khác biệt và optimizer có thể áp dụng thống kê đó cho truy vấn tương ứng. Cần cập nhật thống kê sau thay đổi dữ liệu đáng kể và kiểm tra kế hoạch thực tế.

Cardinality Estimator có thể thay đổi cách xử lý tương quan theo phiên bản và compatibility level. Không nên mặc định một mô hình độc lập duy nhất áp dụng cho mọi bản SQL Server. Khi kết quả ước lượng thay đổi sau nâng cấp hoặc đổi compatibility level, hãy so sánh actual plan, Query Store và thống kê liên quan.

## 6. Thống kê nhiều cột trong MySQL

MySQL có thống kê chỉ mục và histogram cột. Histogram của MySQL mô tả phân bố của từng cột; nó không phải histogram nhiều chiều thể hiện trực tiếp tần suất của mọi tổ hợp cột. Vì vậy, hai histogram đơn cột vẫn có thể bỏ lỡ tương quan giữa `tenant_id` và `status`.

Có thể cập nhật thống kê bảng và chỉ mục:

```sql
ANALYZE TABLE orders;
```

Với phiên bản MySQL 8.0 hỗ trợ histogram, có thể thu thập histogram cho từng cột:

```sql
ANALYZE TABLE orders
UPDATE HISTOGRAM ON tenant_id, status
WITH 100 BUCKETS;
```

Histogram giúp mô tả phân bố riêng của `tenant_id` và `status`. Nó có thể cải thiện ước lượng cho điều kiện trên một cột, nhưng không tự cung cấp xác suất có điều kiện của `status` khi biết `tenant_id`.

Chỉ mục ghép có thể cung cấp thông tin về cardinality của các tiền tố chỉ mục và tạo đường truy cập phù hợp với điều kiện kết hợp:

```sql
CREATE INDEX ix_orders_tenant_status_created
ON orders (tenant_id, status, created_at);
```

Chỉ mục này có thể phù hợp với truy vấn lọc theo `tenant_id`, `status` và khoảng `created_at`. Thống kê chỉ mục ghép cung cấp thông tin về số giá trị phân biệt của các tiền tố; điều đó hữu ích nhưng không đồng nghĩa optimizer có đầy đủ phân bố chung chi tiết cho mọi cặp giá trị. Thứ tự cột phải dựa trên mẫu truy vấn, tính chọn lọc, điều kiện range và thứ tự sắp xếp. Trước khi thêm chỉ mục, hãy đo dung lượng, chi phí insert/update/delete và tác động tới các truy vấn hiện có.

## 7. Extended statistics trong Oracle Database

Oracle Database hỗ trợ column group statistics để mô tả mối tương quan giữa các cột trong cùng một bảng. Khi optimizer cần ước lượng điều kiện lọc nhiều cột, thống kê nhóm cột có thể giúp tránh nhân các độ chọn lọc riêng lẻ trong trường hợp dữ liệu có tương quan.

Ví dụ tạo column group cho `tenant_id` và `status`:

```sql
SELECT DBMS_STATS.CREATE_EXTENDED_STATS(
         ownname   => 'APP',
         tabname   => 'ORDERS',
         extension => '(TENANT_ID, STATUS)'
       ) AS extension_name
FROM dual;
```

Sau đó thu thập thống kê bảng:

```sql
BEGIN
  DBMS_STATS.GATHER_TABLE_STATS(
    ownname => 'APP',
    tabname => 'ORDERS',
    method_opt => 'FOR ALL COLUMNS SIZE AUTO'
  );
END;
/
```

Column group statistics giúp optimizer mô tả tổ hợp cột cho các trường hợp phù hợp. Nó không thay thế histogram đơn cột và không bảo đảm mô hình hóa mọi tương quan hoặc mọi dạng biểu thức. Việc tạo extended statistics cần quyền phù hợp; hãy kiểm tra tên schema, chính sách thu thập và tài liệu theo phiên bản Oracle đang vận hành.

## 8. Phân biệt thống kê tương quan với chỉ mục ghép

Thống kê và chỉ mục có liên quan nhưng giải quyết hai vấn đề khác nhau:

| Cơ chế | Vai trò chính | Câu hỏi được trả lời |
|---|---|---|
| Histogram đơn cột | Mô tả phân bố một cột | Một giá trị hoặc khoảng của cột này phổ biến đến đâu? |
| Thống kê nhiều cột/column group | Mô tả một phần phân bố kết hợp hoặc mức phụ thuộc | Các điều kiện trên nhóm cột có thường xuất hiện cùng nhau không? |
| Chỉ mục ghép | Cung cấp đường truy cập và thống kê cardinality của tiền tố chỉ mục | Có thể tìm các dòng theo nhiều cột mà không quét toàn bảng không? |
| Chỉ mục bao phủ | Lưu thêm cột cần đọc để giảm truy cập bảng | Có thể trả kết quả từ chỉ mục mà không phải lookup thêm không? |

Tạo extended statistics không tạo đường truy cập mới; nó giúp optimizer ước lượng tốt hơn. Tạo chỉ mục ghép có thể tạo đường truy cập mới và thay đổi chi phí đọc/ghi, nhưng không bảo đảm mô tả đầy đủ phân bố kết hợp. Có workload cần cả hai; cũng có workload chỉ cần cập nhật thống kê hiện có.

## 9. Quy trình điều tra sai lệch do tương quan

Khi phát hiện truy vấn có estimated rows sai đáng kể, hãy đi theo quy trình sau:

1. **Xác định operator đầu tiên sai lệch.** So sánh estimated rows với actual rows từ dưới lên. Đừng chỉ nhìn nút cuối cùng của kế hoạch.
2. **Kiểm tra điều kiện lọc.** Xác định các cột được dùng cùng nhau trong `WHERE`, `JOIN`, `GROUP BY` và xem chúng có quan hệ nghiệp vụ hoặc phân bố lệch không.
3. **Đo phân bố kết hợp.** Dùng `GROUP BY`, tỷ lệ có điều kiện hoặc mẫu dữ liệu đại diện để kiểm tra giả định độc lập.
4. **Kiểm tra chất lượng thống kê.** Xem thời điểm cập nhật, sample size, histogram, số giá trị phân biệt và dữ liệu vừa thay đổi.
5. **Chọn cơ chế phù hợp.** Dùng extended statistics, column group, multi-column statistics, filtered statistics hoặc chỉ mục ghép tùy hệ quản trị và vấn đề.
6. **Thu thập lại thống kê.** Tạo đối tượng thống kê xong phải thực hiện bước thu thập theo yêu cầu của hệ quản trị.
7. **Đo lại cùng bộ tham số.** Dùng cùng dữ liệu, tham số và điều kiện tải để so sánh estimated rows, actual rows, plan, elapsed, CPU, I/O và memory.
8. **Kiểm tra workload liên quan.** Xác nhận thay đổi không làm truy vấn khác chậm hơn hoặc tăng chi phí ghi và lưu trữ quá mức.

### Ví dụ quyết định

Giả sử một truy vấn lọc `tenant_id = 42 AND status = 'OPEN'` có estimated rows là 20.000 nhưng actual rows là 800.000. Điều tra cho thấy tenant 42 có tỷ lệ `OPEN` cao bất thường.

- Nếu dùng PostgreSQL, thử extended statistics với `dependencies` và `mcv`, rồi `ANALYZE`.
- Nếu dùng SQL Server, xem histogram và density vector; cân nhắc statistics nhiều cột hoặc filtered statistics cho nhóm `OPEN`.
- Nếu dùng MySQL, kiểm tra histogram đơn cột, thống kê chỉ mục ghép và khả năng chọn thứ tự cột phù hợp với truy vấn.
- Nếu dùng Oracle, xem column group statistics và trạng thái thu thập thống kê.

Sau đó chạy lại truy vấn với tenant 42, một tenant nhỏ, một tenant trung vị và một tenant lớn khác. Nếu ước lượng của tenant 42 cải thiện nhưng các tenant khác suy giảm, cần đánh giá lại cấu hình thống kê và cách optimizer xử lý các nhóm tham số. Không ép một mô hình duy nhất nếu workload có nhiều nhóm phân bố rất khác nhau.

## 10. Giới hạn và sai lầm thường gặp

- **Coi các cột luôn độc lập:** dữ liệu nghiệp vụ thường có tương quan, đặc biệt ở hệ thống đa tenant, phân loại, địa lý và thời gian.
- **Cho rằng histogram đơn cột mô tả được tổ hợp:** histogram biên không chứa đầy đủ xác suất có điều kiện giữa nhiều cột.
- **Nhầm tương quan với phụ thuộc hàm tuyệt đối:** quan hệ gần như xác định có thể có ngoại lệ, `NULL` hoặc thay đổi theo thời gian.
- **Tạo thống kê nhiều cột cho mọi tổ hợp:** số lượng tổ hợp tăng nhanh và làm tăng chi phí thu thập, lưu trữ, bảo trì.
- **Quên thu thập lại thống kê:** tạo đối tượng thống kê chưa có nghĩa optimizer đã có dữ liệu mới.
- **Giả định extended statistics giải quyết mọi join:** nhiều cơ chế thống kê nhiều cột chỉ mô tả cột trong cùng một bảng và có giới hạn với join hoặc biểu thức phức tạp.
- **Đồng nhất thống kê với chỉ mục:** thống kê cải thiện ước lượng; chỉ mục tạo đường truy cập và làm thay đổi chi phí ghi.
- **Chỉ kiểm tra một giá trị tham số:** một tổ hợp có thể cải thiện trong khi nhóm khác vẫn sai lệch.
- **Chỉ nhìn estimated cost:** cần so sánh actual rows, thời gian, I/O, CPU, memory và spill.
- **Bỏ qua độ mới của dữ liệu:** phân bố có thể đổi sau batch load, xóa dữ liệu hoặc chiến dịch nghiệp vụ.

## 11. Checklist đánh giá tương quan và thống kê

- [ ] Đã xác định các cột thường xuất hiện cùng nhau trong điều kiện lọc hoặc nhóm dữ liệu.
- [ ] Đã so sánh phân bố biên với phân bố kết hợp trên dữ liệu đại diện.
- [ ] Đã tìm operator đầu tiên có estimated rows sai khác lớn so với actual rows.
- [ ] Đã kiểm tra độ mới, sample size và cấu hình thống kê hiện tại.
- [ ] Đã chọn đúng loại thống kê nhiều cột theo khả năng của hệ quản trị.
- [ ] Đã thu thập lại thống kê sau khi tạo hoặc thay đổi đối tượng thống kê.
- [ ] Đã kiểm thử nhiều giá trị tham số và các nhóm dữ liệu có độ lệch khác nhau.
- [ ] Đã đo lại plan, elapsed, CPU, I/O, memory và spill.
- [ ] Đã kiểm tra ảnh hưởng tới workload khác, chi phí ghi và dung lượng lưu trữ.
- [ ] Đã lưu kết quả trước/sau cùng điều kiện để có thể so sánh về sau.

Giả định độc lập là một cách xấp xỉ hữu ích khi các cột không có tương quan đáng kể. Khi dữ liệu có quan hệ rõ rệt, thống kê từng cột có thể khiến optimizer dự đoán sai số dòng và chọn kế hoạch kém. Bằng cách đo phân bố kết hợp, xác định đúng operator sai lệch và sử dụng thống kê nhiều cột phù hợp, nhóm vận hành có thể cải thiện chất lượng ước lượng và làm cho kế hoạch thực thi ổn định hơn trên dữ liệu thực tế.
