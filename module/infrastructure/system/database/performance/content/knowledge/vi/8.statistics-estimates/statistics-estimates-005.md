# Thống kê nhiều cột và thống kê mở rộng theo hệ quản trị

Bộ tối ưu truy vấn phải ước lượng số hàng sẽ đi qua từng bước của kế hoạch thực thi trước khi chọn cách quét dữ liệu, thứ tự join, kiểu join, cách sắp xếp và phân bổ bộ nhớ. Ước lượng này được gọi là cardinality estimate. Nếu ước lượng sai đáng kể, một kế hoạch có thể trông hợp lý trên dữ liệu nhỏ nhưng trở nên chậm khi chạy với dữ liệu thật.

Thống kê một cột thường mô tả phân bố của từng cột riêng lẻ. Tuy nhiên, dữ liệu nghiệp vụ thường có quan hệ giữa các cột: mã vùng xác định một phần tỉnh/thành, trạng thái đơn hàng liên quan đến loại giao dịch, hoặc mã sản phẩm gắn với một nhóm danh mục. Khi bộ tối ưu giả định các cột độc lập trong khi chúng có tương quan, phép ước lượng kết hợp có thể sai.

Thống kê nhiều cột và thống kê mở rộng cung cấp thêm thông tin về quan hệ giữa các cột, số tổ hợp phân biệt, nhóm giá trị phổ biến hoặc biểu thức. Mỗi hệ quản trị có cách triển khai và giới hạn riêng. Vì vậy, cần hiểu loại thống kê nào có sẵn, khi nào bộ tối ưu sử dụng chúng và cách xác minh bằng kế hoạch thực thi thực tế.

## 1. Cardinality và vai trò của thống kê

Cardinality trong kế hoạch truy vấn thường chỉ số hàng mà một toán tử hoặc một tập điều kiện được ước lượng sẽ tạo ra. Ví dụ, với bảng orders có 10 triệu hàng, điều kiện status = 'OPEN' có thể trả về 2 triệu hàng. Một điều kiện khác region_id = 12 có thể trả về 500 nghìn hàng.

Nếu bộ tối ưu biết phân bố của từng cột, nó có thể ước lượng mức chọn lọc (selectivity) của từng điều kiện. Selectivity là tỷ lệ hàng thỏa điều kiện so với tổng số hàng.

Khi có hai điều kiện trên cùng bảng, một mô hình đơn giản thường gặp là giả định độc lập:

```text
P(A AND B) ≈ P(A) × P(B)
Estimated rows ≈ Table rows × P(A) × P(B)
```

Giả định này có thể hữu ích nếu hai thuộc tính thực sự độc lập. Nhưng nếu region_id và province_code có quan hệ chặt chẽ, nhân hai xác suất riêng biệt có thể đánh giá thấp hoặc cao số hàng thực tế.

Ví dụ, giả sử bảng khách hàng có 1.000.000 hàng. Điều kiện region_id = 4 khớp 100.000 hàng (10%), còn province_code = 'P04' khớp 80.000 hàng (8%). Nếu bộ tối ưu giả định độc lập, số hàng kết hợp được ước lượng là:

```text
1.000.000 × 0,10 × 0,08 = 8.000 hàng
```

Nhưng nếu tất cả khách hàng ở tỉnh P04 đều thuộc vùng 4, kết quả thực tế có thể là 80.000 hàng. Ước lượng đã thấp hơn 10 lần. Với các điều kiện có tương quan âm, ước lượng độc lập cũng có thể cao hơn thực tế nhiều lần.

Sai lệch cardinality ảnh hưởng đến lựa chọn kế hoạch:

- Bộ tối ưu có thể chọn nested loop khi số hàng thực tế lớn, làm số lần tra cứu bảng hoặc chỉ mục tăng mạnh.
- Bộ tối ưu có thể chọn hash join hoặc sort với kích thước bộ nhớ không phù hợp.
- Thứ tự join có thể thay đổi; một bảng trung gian bị ước lượng quá nhỏ có thể được đưa vào đầu chuỗi join.
- Bộ nhớ dành cho sort, hash hoặc aggregate có thể không đủ, dẫn đến spill ra đĩa.
- Chi phí ước lượng của các nhánh kế hoạch có thể sai, khiến lựa chọn chỉ mục hoặc kiểu truy cập không phù hợp.

Thống kê không quyết định trực tiếp kế hoạch duy nhất. Bộ tối ưu còn xét chi phí CPU, I/O, cấu hình, chỉ mục, tham số và các ràng buộc khác. Tuy nhiên, cardinality thường là đầu vào rất quan trọng của quá trình đó.

## 2. Thống kê một cột và giới hạn khi dữ liệu có tương quan

Thống kê một cột có thể chứa số hàng, số giá trị phân biệt, số NULL, giá trị nhỏ/lớn, histogram hoặc nhóm giá trị phổ biến. Cách lưu trữ và tên trường khác nhau giữa các hệ quản trị.

Các dạng thông tin phổ biến:

| Loại thông tin | Mô tả | Hỗ trợ ước lượng |
|---|---|---|
| Row count | Tổng số hàng hoặc số hàng trong phân vùng | Quy mô tập dữ liệu |
| Distinct count | Số giá trị phân biệt | Điều kiện bằng và số nhóm trong GROUP BY |
| NULL fraction | Tỷ lệ giá trị NULL | Điều kiện IS NULL/IS NOT NULL |
| Minimum/maximum | Biên giá trị quan sát được | Điều kiện khoảng và ngoài miền |
| Histogram | Phân bố giá trị theo bucket hoặc khoảng | Điều kiện bằng, khoảng, độ lệch dữ liệu |
| Most common values (MCV) | Giá trị xuất hiện thường xuyên | Ước lượng chính xác hơn cho giá trị lệch |
| Density/frequency | Mật độ hoặc tần suất theo cách hệ quản trị định nghĩa | Ước lượng điều kiện và tổ hợp |

Thống kê một cột vẫn có thể không đủ trong các tình huống sau:

1. **Tương quan phụ thuộc:** một giá trị của cột A gần như xác định giá trị của cột B.
2. **Nhóm giá trị phổ biến:** một số cặp hoặc bộ ba giá trị xuất hiện nhiều hơn hẳn các tổ hợp còn lại.
3. **Số tổ hợp phân biệt:** số cặp (A, B) khác nhau khác xa tích hoặc phép suy ra từ số distinct riêng lẻ.
4. **Điều kiện trên biểu thức:** truy vấn lọc theo lower(email), date(created_at) hoặc biểu thức tính toán mà thống kê cột gốc không mô tả trực tiếp.
5. **Dữ liệu lệch theo phân vùng hoặc thời gian:** thống kê tổng thể có thể không đại diện cho phần dữ liệu truy vấn đang đọc.

### Phân biệt các dạng thống kê mở rộng

- **Column group / multicolumn statistics:** mô tả quan hệ hoặc phân bố của một nhóm cột.
- **Functional dependencies:** mô tả mức độ một cột phụ thuộc vào một hoặc nhiều cột khác.
- **Multivariate MCV:** ghi nhận các tổ hợp giá trị phổ biến trên nhiều cột.
- **Multivariate distinct / ndistinct:** ước lượng số tổ hợp phân biệt của nhiều cột, hữu ích cho GROUP BY hoặc DISTINCT.
- **Expression statistics:** mô tả phân bố của biểu thức được dùng trong điều kiện truy vấn.
- **Filtered statistics:** mô tả một tập con hàng thỏa điều kiện, giúp ước lượng workload có phạm vi hẹp.

Tên gọi và khả năng sử dụng khác nhau giữa các DBMS. Không phải hệ quản trị nào cũng hỗ trợ tất cả loại thống kê trên, và một loại thống kê có thể chỉ được áp dụng cho một số dạng predicate nhất định.

## 3. Khi nào nên tạo thống kê nhiều cột?

Không nên tạo thống kê mở rộng cho mọi tổ hợp cột trong bảng. Mỗi đối tượng thống kê cần được thu thập, lưu trữ và cập nhật; quá nhiều đối tượng làm tăng chi phí bảo trì và khó quản lý.

Hãy cân nhắc tạo thống kê nhiều cột khi có bằng chứng:

- Một truy vấn thường xuyên lọc đồng thời nhiều cột của cùng một bảng.
- Các cột có tương quan nghiệp vụ rõ ràng.
- Kế hoạch cho thấy estimated rows khác actual rows nhiều lần ở node áp dụng nhiều điều kiện.
- Thứ tự join hoặc kiểu join không phù hợp với số hàng thực tế.
- GROUP BY hoặc DISTINCT trên nhiều cột có số tổ hợp ước lượng sai.
- Một nhóm giá trị cụ thể xuất hiện rất thường xuyên và tạo ra độ lệch lớn.
- Điều kiện lọc dùng biểu thức lặp lại và thống kê cột gốc không mô tả đủ phân bố.

Trước khi tạo, hãy kiểm tra:

1. Query fingerprint nào đang chịu ảnh hưởng và tổng thời gian tích lũy của nó.
2. Các điều kiện lọc có nằm trên cùng một bảng hay không.
3. Sai lệch bắt đầu ở node nào trong execution plan.
4. Thống kê hiện tại đã cũ, lấy mẫu chưa đủ hoặc không phản ánh phân bố mới hay chưa.
5. Có thể giải quyết bằng cập nhật thống kê hiện có, viết lại predicate hoặc chỉ mục phù hợp hay không.

Thống kê mở rộng không thay thế chỉ mục. Thống kê giúp bộ tối ưu ước lượng tốt hơn; chỉ mục cung cấp một cấu trúc truy cập dữ liệu. Có thể cần cả hai, nhưng chúng giải quyết hai vấn đề khác nhau.

## 4. PostgreSQL: CREATE STATISTICS và ANALYZE

PostgreSQL hỗ trợ extended statistics cho các cột của cùng một bảng. Có thể chọn các loại thống kê như dependencies, ndistinct và mcv.

- dependencies: mô tả quan hệ phụ thuộc giữa các cột, hữu ích khi các giá trị có quan hệ xác định hoặc gần xác định.
- ndistinct: ước lượng số tổ hợp phân biệt của nhóm cột, hữu ích cho GROUP BY và DISTINCT.
- mcv: lưu các tổ hợp giá trị phổ biến để bộ tối ưu ước lượng tốt hơn cho nhóm giá trị lệch.

### Ví dụ tạo thống kê mở rộng

Giả sử bảng orders có region_id, status và channel. Một số trạng thái chỉ xuất hiện ở một số kênh hoặc vùng. Có thể tạo đối tượng thống kê:

```sql
CREATE STATISTICS st_orders_region_status
    (dependencies, ndistinct, mcv)
ON region_id, status
FROM orders;

ANALYZE orders;
```

CREATE STATISTICS khai báo nhóm cột và loại thống kê. ANALYZE thu thập dữ liệu mẫu để cập nhật thống kê bảng và đối tượng thống kê mở rộng. Nếu chỉ tạo đối tượng mà chưa thu thập thống kê, bộ tối ưu chưa có đủ dữ liệu mới để sử dụng.

Với workload có điều kiện theo region_id và status, hãy so sánh estimated rows với actual rows trong EXPLAIN ANALYZE. Có thể dùng:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, created_at
FROM orders
WHERE region_id = 4
  AND status = 'OPEN';
```

Kiểm tra thông tin extended statistics trong catalog view:

```sql
SELECT
    statistics_name,
    attnames,
    kinds,
    n_distinct,
    dependencies,
    most_common_vals,
    most_common_freqs
FROM pg_stats_ext
WHERE schemaname = 'public'
  AND tablename = 'orders';
```

Tên schema và bảng cần thay theo môi trường. Quyền xem catalog và các cột được cung cấp có thể phụ thuộc phiên bản PostgreSQL.

### Điều chỉnh mục tiêu thu thập

Nếu một nhóm cột có phân bố phức tạp, có thể tăng statistics target cho đối tượng:

```sql
ALTER STATISTICS st_orders_region_status
    SET STATISTICS 500;

ANALYZE orders;
```

Target cao hơn có thể giữ được nhiều thông tin phân bố hơn nhưng làm tăng thời gian thu thập và kích thước thống kê. Chỉ tăng khi kết quả đo cho thấy thống kê hiện tại chưa mô tả đủ dữ liệu.

PostgreSQL cũng hỗ trợ thống kê cho biểu thức trong các phiên bản hiện đại. Ví dụ, khi truy vấn thường lọc theo lower(email), có thể tạo expression statistics phù hợp với cú pháp phiên bản đang dùng:

```sql
CREATE STATISTICS st_customer_email_lower
ON (lower(email))
FROM customers;

ANALYZE customers;
```

Expression statistics giúp ước lượng điều kiện trên biểu thức. Nếu cần truy cập nhanh theo biểu thức, vẫn có thể cần expression index riêng:

```sql
CREATE INDEX idx_customer_email_lower
ON customers (lower(email));
```

Thống kê và chỉ mục biểu thức có vai trò khác nhau: một bên hỗ trợ ước lượng, bên kia hỗ trợ truy cập.

### Giới hạn cần biết

- Extended statistics được khai báo trên các cột của cùng một bảng; chúng không phải cơ chế tổng quát để mô tả mọi tương quan giữa hai bảng trong join.
- Functional dependencies chỉ có ích với những dạng điều kiện mà bộ tối ưu hỗ trợ; không nên giả định nó mô hình hóa mọi range predicate, biểu thức hoặc phép so sánh cột với cột.
- ndistinct chủ yếu hỗ trợ ước lượng số nhóm phân biệt, không tự làm truy vấn nhanh hơn.
- MCV có thể hữu ích với tổ hợp giá trị lệch, nhưng không lưu mọi tổ hợp có thể có.
- Cần chạy ANALYZE sau khi tạo hoặc thay đổi đối tượng thống kê để thu thập thông tin.

## 5. SQL Server: multicolumn statistics, density và filtered statistics

SQL Server lưu thống kê trong các statistics object. Thống kê có thể được tạo tự động hoặc thủ công; thống kê trên chỉ mục cũng chứa thông tin phân bố. Có thể tạo một statistics object trên nhiều cột để cung cấp thêm thông tin về các tổ hợp.

Ví dụ:

```sql
CREATE STATISTICS st_Orders_Region_Status
ON dbo.Orders (RegionId, Status)
WITH FULLSCAN;
```

FULLSCAN đọc toàn bộ dữ liệu để thu thập thống kê, thường tốn tài nguyên hơn lấy mẫu. Với bảng lớn, hãy chọn phương pháp phù hợp với cửa sổ bảo trì và độ chính xác cần thiết.

Cập nhật thống kê cụ thể:

```sql
UPDATE STATISTICS dbo.Orders
    st_Orders_Region_Status
WITH FULLSCAN;
```

Có thể kiểm tra nội dung bằng:

```sql
DBCC SHOW_STATISTICS
    (N'dbo.Orders', N'st_Orders_Region_Status')
WITH STAT_HEADER, DENSITY_VECTOR, HISTOGRAM;
```

### Histogram và density vector

Trong SQL Server, histogram của một statistics object được xây dựng trên cột đầu tiên trong danh sách cột thống kê. Density vector cung cấp thông tin mật độ cho các tiền tố cột của đối tượng thống kê. Vì vậy, thứ tự cột trong statistics object có ý nghĩa.

Ví dụ, với thống kê (RegionId, Status), histogram mô tả phân bố của RegionId; density vector có thông tin cho tiền tố RegionId và tổ hợp (RegionId, Status). Điều này giúp bộ tối ưu có thêm dữ liệu về mật độ của nhóm cột, nhưng không có nghĩa histogram đa chiều đầy đủ cho mọi cặp giá trị.

Nếu workload chủ yếu lọc theo Status trước, hãy cân nhắc một statistics object khác có Status làm cột đầu tiên, sau khi đo và đánh giá chi phí. Tạo nhiều đối tượng trùng lặp không có mục tiêu rõ ràng sẽ tăng chi phí cập nhật.

### Filtered statistics

Filtered statistics mô tả một tập con hàng. Chúng hữu ích khi một truy vấn thường truy cập nhóm dữ liệu nhỏ và có phân bố khác phần còn lại:

```sql
CREATE STATISTICS st_Orders_Open_Customer
ON dbo.Orders (CustomerId)
WHERE Status = 'OPEN';
```

Thống kê này tập trung vào các đơn hàng đang mở. Bộ tối ưu có thể dùng nó khi predicate của truy vấn phù hợp với điều kiện lọc. Cần bảo đảm biểu thức truy vấn tương thích với predicate của filtered statistics; nếu điều kiện không khớp hoặc tham số hóa khiến bộ tối ưu không thể chứng minh tính phù hợp, thống kê có thể không được sử dụng.

### Kiểm tra và quản lý

- Dùng sys.stats, sys.stats_columns và sys.dm_db_stats_properties để kiểm tra đối tượng thống kê, cột và thông tin cập nhật.
- Xem histogram và density bằng DBCC SHOW_STATISTICS.
- Dùng actual execution plan và số hàng thực tế để kiểm tra tác động.
- Theo dõi auto update statistics, thời điểm cập nhật và số hàng thay đổi kể từ lần thu thập.
- Với bảng phân vùng lớn, tìm hiểu incremental statistics nếu phiên bản và cấu hình hỗ trợ.

Thống kê nhiều cột không giống một chỉ mục ghép. Nó có thể cải thiện ước lượng tổ hợp, nhưng không cung cấp đường truy cập để tìm hàng. Nếu truy vấn cần đọc ít hàng theo (RegionId, Status), một index phù hợp có thể vẫn cần thiết.

## 6. MySQL: histogram một cột và thống kê tiền tố chỉ mục

MySQL cung cấp thống kê chỉ mục và histogram cho cột. InnoDB lưu persistent statistics cho bảng và chỉ mục; ANALYZE TABLE cập nhật thông tin phân bố mà bộ tối ưu dùng để ước lượng.

Ví dụ cập nhật thống kê chỉ mục:

```sql
ANALYZE TABLE orders;
```

MySQL 8.0 hỗ trợ histogram trên các cột:

```sql
ANALYZE TABLE orders
UPDATE HISTOGRAM ON status, region_id
WITH 64 BUCKETS;
```

Mỗi histogram mô tả phân bố của một cột. Việc liệt kê nhiều cột trong câu lệnh không tạo ra một histogram đa chiều mô tả tương quan giữa các cột.

Có thể xem histogram trong INFORMATION_SCHEMA.COLUMN_STATISTICS:

```sql
SELECT
    SCHEMA_NAME,
    TABLE_NAME,
    COLUMN_NAME,
    HISTOGRAM
FROM INFORMATION_SCHEMA.COLUMN_STATISTICS
WHERE SCHEMA_NAME = DATABASE()
  AND TABLE_NAME = 'orders';
```

Histogram lưu dưới dạng JSON; có thể xem số bucket, loại histogram và tần suất theo cấu trúc được phiên bản MySQL sử dụng. Cần kiểm tra phiên bản vì chi tiết biểu diễn và cách bộ tối ưu sử dụng có thể thay đổi.

### Thống kê tiền tố của chỉ mục ghép

Trong MySQL, chỉ mục ghép như:

```sql
CREATE INDEX idx_orders_region_status
ON orders (region_id, status);
```

cung cấp thống kê cardinality cho các tiền tố của chỉ mục. Tiền tố (region_id) và (region_id, status) có thông tin khác nhau. Thống kê này hỗ trợ bộ tối ưu khi điều kiện truy vấn phù hợp với thứ tự cột.

Có thể xem chỉ mục và cardinality bằng:

```sql
SHOW INDEX FROM orders;
```

Cardinality thường là giá trị ước lượng, không phải số đếm chính xác tại mọi thời điểm. Khi cần kiểm tra, hãy chạy ANALYZE TABLE và so sánh kế hoạch EXPLAIN trước/sau.

MySQL không cung cấp một cơ chế thống kê mở rộng nhóm cột tổng quát tương đương trực tiếp với PostgreSQL extended statistics hoặc Oracle column-group statistics trong các phiên bản phổ biến. Histogram tích hợp là thống kê một cột; thống kê chỉ mục ghép cung cấp thông tin tiền tố. Khi dữ liệu có tương quan phức tạp, cần đánh giá kế hoạch, chỉ mục ghép, cách viết predicate và khả năng mô hình hóa dữ liệu.

Một số cấu hình InnoDB cho phép điều chỉnh số trang lấy mẫu để thu thập persistent statistics. Tăng mẫu có thể cải thiện ước lượng trên phân bố phức tạp nhưng làm ANALYZE TABLE tốn thời gian hơn. Không nên thay đổi tham số toàn cục chỉ để xử lý một truy vấn trước khi xác nhận vấn đề nằm ở chất lượng thống kê.

## 7. Oracle: column-group và expression statistics

Oracle hỗ trợ extended statistics cho nhóm cột và biểu thức thông qua DBMS_STATS. Column-group statistics giúp bộ tối ưu mô tả tương quan giữa nhiều cột trong cùng một bảng.

Ví dụ tạo thống kê cho nhóm REGION_ID và STATUS:

```sql
SELECT DBMS_STATS.CREATE_EXTENDED_STATS(
    ownname   => USER,
    tabname   => 'ORDERS',
    extension => '(REGION_ID, STATUS)'
)
FROM DUAL;
```

Sau khi tạo extension, thu thập thống kê bảng:

```sql
BEGIN
  DBMS_STATS.GATHER_TABLE_STATS(
    ownname => USER,
    tabname => 'ORDERS',
    method_opt => 'FOR ALL COLUMNS SIZE AUTO',
    cascade => TRUE
  );
END;
/
```

Column group được quản lý như một phần của thống kê mở rộng. Khi bộ tối ưu gặp predicate phù hợp trên nhóm cột, nó có thể sử dụng thông tin này để cải thiện cardinality estimate.

Oracle cũng hỗ trợ expression statistics, ví dụ thống kê cho biểu thức UPPER(CUSTOMER_NAME) nếu truy vấn thường lọc theo biểu thức đó. Có thể tạo extended statistics cho biểu thức theo cú pháp DBMS_STATS.CREATE_EXTENDED_STATS tương ứng với phiên bản đang dùng.

### Xác định nhóm cột đáng tạo

Oracle cung cấp cơ chế báo cáo mức sử dụng cột trong predicate, ví dụ DBMS_STATS.SEED_COL_USAGE và DBMS_STATS.REPORT_COL_USAGE. Có thể dùng thông tin sử dụng để tìm các cột thường xuất hiện cùng nhau trong điều kiện lọc, sau đó đánh giá column group phù hợp.

Không nên tạo mọi nhóm cột có thể có. Một bảng có 20 cột có số lượng tổ hợp rất lớn; chỉ những nhóm được truy vấn thực sự dùng và có tương quan đáng kể mới đáng được xem xét.

Chi tiết package, quyền và cách quản lý extension phụ thuộc phiên bản Oracle. Hãy kiểm tra tài liệu của phiên bản đang triển khai trước khi chạy thủ tục trong môi trường sản xuất.

## 8. So sánh khả năng giữa các hệ quản trị

| Hệ quản trị | Cơ chế chính | Thông tin có thể mô tả | Lưu ý |
|---|---|---|---|
| PostgreSQL | CREATE STATISTICS với dependencies, ndistinct, MCV; expression statistics | Phụ thuộc cột, tổ hợp phổ biến, số tổ hợp phân biệt, biểu thức | Cần ANALYZE; phạm vi và dạng predicate được hỗ trợ có giới hạn |
| SQL Server | Multicolumn statistics, index statistics, filtered statistics | Histogram cột đầu, density vector cho tiền tố cột, phân bố tập con | Histogram không phải histogram đa chiều; thứ tự cột quan trọng |
| MySQL | InnoDB index statistics, single-column histograms | Phân bố từng cột và cardinality tiền tố chỉ mục ghép | Histogram tích hợp là từng cột; không có column-group extended stats tổng quát tương đương |
| Oracle | DBMS_STATS extended column-group và expression statistics | Tương quan cột và phân bố biểu thức | Cần tạo extension và thu thập thống kê; khả năng phụ thuộc phiên bản |

Không nên chuyển nguyên cú pháp hoặc giả định giữa các hệ quản trị. Ví dụ, một câu lệnh tạo multicolumn statistics của SQL Server không có nghĩa nó sẽ lưu histogram đa chiều như một MCV statistic của PostgreSQL. Khi chuyển hệ quản trị, hãy ánh xạ theo mục tiêu ước lượng cần đạt, không chỉ theo tên tính năng.

## 9. Ví dụ tổng hợp: thống kê tương quan trạng thái và kênh bán hàng

Giả sử bảng orders có 20 triệu hàng, với các cột:

- region_id: vùng xử lý đơn.
- channel: kênh bán hàng.
- status: trạng thái đơn.
- created_at: thời điểm tạo.

Trong dữ liệu, đơn hàng từ kênh PARTNER chủ yếu xuất hiện ở một số vùng và có tỷ lệ PENDING cao hơn. Một báo cáo lọc đồng thời:

```sql
SELECT COUNT(*)
FROM orders
WHERE region_id = 3
  AND channel = 'PARTNER'
  AND status = 'PENDING';
```

Nếu bộ tối ưu chỉ có thống kê một cột, nó có thể nhân selectivity của ba điều kiện như thể chúng độc lập. Giả sử mỗi điều kiện riêng lẻ có selectivity 10%, 5% và 20%, ước lượng độc lập là:

```text
20.000.000 × 0,10 × 0,05 × 0,20 = 20.000 hàng
```

Nhưng nếu các điều kiện có tương quan dương, số hàng thực tế có thể là 180.000. Nếu ước lượng chỉ 20.000, kế hoạch có thể chọn join hoặc cấp bộ nhớ dựa trên tập dữ liệu nhỏ hơn nhiều so với thực tế.

Quy trình xử lý:

1. Lấy actual execution plan và xác định node đầu tiên có estimated rows lệch mạnh.
2. Kiểm tra query fingerprint và tần suất chạy để biết truy vấn có đủ quan trọng.
3. Kiểm tra phân bố từng cột và quan hệ nghiệp vụ giữa các cột.
4. Chọn cơ chế thống kê phù hợp với DBMS: PostgreSQL MCV/dependencies, SQL Server multicolumn hoặc filtered statistics, Oracle column group, hoặc MySQL index-prefix statistics và histogram từng cột.
5. Thu thập lại thống kê và chạy cùng truy vấn với dữ liệu, tham số và điều kiện cache tương đương.
6. So sánh estimated rows, actual rows, join order, memory grant/spill, logical reads và thời gian.
7. Kiểm tra các truy vấn khác dùng cùng bảng để chắc rằng cải thiện không làm kế hoạch khác xấu đi đáng kể.

Một thống kê mở rộng có thể cải thiện ước lượng nhưng không bảo đảm truy vấn nhanh hơn nếu nút thắt thực tế là thiếu chỉ mục, I/O, lock contention hoặc mạng. Sau khi cardinality chính xác hơn, cần đánh giá kế hoạch mới và toàn bộ workload.

## 10. Thống kê và chỉ mục: phối hợp nhưng không nhầm lẫn

Thống kê và chỉ mục thường được xem xét cùng nhau, nhưng vai trò khác nhau:

| Thành phần | Vai trò | Ví dụ |
|---|---|---|
| Thống kê một cột | Mô tả phân bố riêng lẻ | Histogram của status |
| Thống kê nhiều cột | Mô tả tương quan hoặc số tổ hợp | Nhóm region_id, status |
| Thống kê biểu thức | Mô tả phân bố của biểu thức lọc | lower(email) |
| Chỉ mục một cột | Cung cấp đường truy cập theo một khóa | Index trên customer_id |
| Chỉ mục ghép | Cung cấp đường truy cập theo thứ tự nhiều khóa | Index (region_id, status, created_at) |
| Chỉ mục lọc/partial | Giữ tập con hàng thỏa predicate | Index chỉ cho đơn hàng đang mở |

Một truy vấn có thể cần thống kê mở rộng để bộ tối ưu ước lượng đúng, nhưng vẫn phải quét bảng nếu không có đường truy cập phù hợp. Ngược lại, chỉ mục ghép có thể cung cấp thống kê tiền tố nhưng chưa chắc mô tả đủ mọi tương quan hoặc phân bố lệch.

Trước khi tạo thêm chỉ mục, hãy kiểm tra:

- Điều kiện lọc và thứ tự cột của chỉ mục hiện có.
- Số hàng thực tế mà truy vấn cần đọc.
- Chi phí cập nhật chỉ mục khi thêm, sửa hoặc xóa dữ liệu.
- Dung lượng, I/O và thời gian bảo trì.
- Liệu sai lệch chính nằm ở cardinality hay ở đường truy cập dữ liệu.

## 11. Thời điểm thu thập và chất lượng thống kê

Thống kê có thể trở nên lỗi thời khi dữ liệu thay đổi. Một bảng tăng thêm hàng triệu bản ghi, một trạng thái mới chiếm phần lớn dữ liệu hoặc dữ liệu cũ được archive có thể làm phân bố khác xa lần thu thập trước.

Các nguyên nhân khiến thống kê không đại diện:

- Thu thập từ mẫu quá nhỏ đối với dữ liệu có độ lệch cao.
- Dữ liệu thay đổi nhanh sau lần ANALYZE hoặc update statistics.
- Bảng phân vùng có phân bố khác nhau giữa các partition.
- Một số giá trị hiếm nhưng quan trọng không xuất hiện trong mẫu.
- Histogram có số bucket không đủ để mô tả vùng phân bố quan trọng.
- Thống kê tổng thể che khuất phân bố của tập con hoặc một tenant cụ thể.
- Tham số truy vấn có độ chọn lọc rất khác nhau giữa các lần gọi.

Tăng sample size hoặc statistics target có thể cải thiện mô tả phân bố, nhưng làm tăng chi phí thu thập và có thể tăng kích thước metadata. Cần đo thời gian thu thập, ảnh hưởng lên tải hệ thống và độ cải thiện cardinality.

Với bảng phân vùng, cần hiểu DBMS dùng thống kê local, global hoặc kết hợp như thế nào. Một truy vấn chỉ đọc partition mới có thể cần thống kê đại diện cho partition đó; thống kê tổng thể không phải lúc nào cũng mô tả đúng tập dữ liệu cục bộ. Khả năng và cú pháp quản lý thống kê phân vùng khác nhau giữa các hệ quản trị.

### Prepared statement và tham số

Một truy vấn có thể nhận nhiều giá trị tham số với độ chọn lọc khác nhau. Ví dụ status = 'ARCHIVED' có thể trả về hàng triệu hàng, còn status = 'PENDING' chỉ trả về vài nghìn. Kế hoạch dùng chung hoặc kế hoạch được tối ưu theo một tham số có thể không tốt cho tham số khác, tùy cơ chế parameter sniffing hoặc generic/custom plan của DBMS.

Khi kiểm tra, hãy thử các nhóm tham số đại diện và xem kế hoạch thực tế. Không nên kết luận thống kê sai chỉ vì một giá trị tham số có kế hoạch khác; có thể đó là khác biệt hợp lý về selectivity.

## 12. Quy trình chẩn đoán sai lệch cardinality

Áp dụng quy trình có thể lặp lại:

1. **Chọn truy vấn quan trọng.** Dựa trên tổng thời gian tích lũy, p95/p99, số lần chạy và ảnh hưởng nghiệp vụ.
2. **Thu thập kế hoạch thực tế.** Ghi estimated rows, actual rows, loops, thời gian, buffer/logical reads và spill nếu công cụ cung cấp.
3. **Tìm node sai lệch đầu tiên.** Sai số ở node sớm có thể lan truyền qua các bước join phía sau.
4. **Kiểm tra predicate.** Xác định điều kiện đơn cột, nhiều cột, biểu thức, range, join predicate và tham số.
5. **Kiểm tra thống kê hiện tại.** Xem thời điểm cập nhật, sample, histogram, distinct count, MCV hoặc density.
6. **Đánh giá tương quan.** Dùng kiến thức nghiệp vụ và truy vấn tổng hợp để xác nhận các cột có phụ thuộc hoặc tổ hợp lệch hay không.
7. **Chọn cơ chế đúng DBMS.** Tạo hoặc cập nhật thống kê nhiều cột, filtered statistics, expression statistics hay histogram phù hợp.
8. **Thu thập lại thống kê.** Dùng lệnh và cửa sổ bảo trì phù hợp với hệ quản trị.
9. **So sánh cùng điều kiện.** Giữ nguyên dữ liệu, tham số, cache và mức tải càng giống nhau càng tốt.
10. **Đánh giá toàn workload.** Kiểm tra truy vấn khác, thời gian ghi, chi phí cập nhật thống kê và dung lượng.

Khi sai lệch xuất hiện ở node join giữa hai bảng, thống kê nhiều cột trên một bảng có thể không giải quyết đầy đủ vấn đề. Hãy kiểm tra thống kê từng bảng, phân bố khóa join, uniqueness, foreign key, số hàng thực tế và khả năng tương quan xuyên bảng. Không suy luận rằng mọi sai số join đều có thể sửa bằng column group.

## 13. Ví dụ so sánh trước và sau

Giả sử truy vấn lọc đơn hàng theo vùng và trạng thái có kết quả thực tế 150.000 hàng. Trước khi tạo thống kê nhiều cột, kế hoạch ước lượng 12.000 hàng.

Sau khi tạo thống kê phù hợp và thu thập lại:

| Chỉ số | Trước | Sau |
|---|---:|---:|
| Estimated rows tại node lọc | 12.000 | 142.000 |
| Actual rows | 150.000 | 150.000 |
| Sai lệch theo tỷ lệ actual/estimated | 12,5 lần | Khoảng 1,06 lần |
| Logical reads | 420.000 | 415.000 |
| Spill ra đĩa | Có | Không |
| Thời gian truy vấn | 1.800 ms | 1.050 ms |

Các con số là giả định minh họa. Trong trường hợp này, thống kê cải thiện ước lượng và giúp bộ tối ưu chọn cách xử lý phù hợp hơn, từ đó giảm spill. Logical reads gần như không đổi cho thấy lượng dữ liệu cần đọc chưa giảm đáng kể; cải thiện chủ yếu đến từ kế hoạch và phân bổ tài nguyên tốt hơn.

Nếu thời gian không giảm dù estimated rows chính xác hơn, hãy tiếp tục kiểm tra I/O, CPU, lock wait, chỉ mục và kích thước kết quả. Mục tiêu của thống kê là giúp bộ tối ưu có thông tin tốt hơn; bản thân việc tạo statistics không đảm bảo giảm thời gian.

## 14. Sai lầm thường gặp

- **Tạo thống kê cho mọi tổ hợp cột:** làm tăng chi phí quản lý nhưng không có bằng chứng rằng workload cần chúng.
- **Nhầm thống kê với chỉ mục:** thống kê hỗ trợ ước lượng, không tự cung cấp đường truy cập dữ liệu.
- **Quên thu thập sau khi tạo:** đối tượng thống kê tồn tại nhưng dữ liệu phân bố chưa được cập nhật.
- **Cho rằng histogram nhiều cột giống nhau ở mọi DBMS:** PostgreSQL MCV, SQL Server density vector, MySQL histogram và Oracle column group có mô hình khác nhau.
- **Không xem thứ tự cột:** đặc biệt quan trọng với histogram/density trong SQL Server và prefix statistics của chỉ mục ghép.
- **Tăng sample hoặc target quá cao:** làm ANALYZE/update statistics tốn tài nguyên mà lợi ích không đáng kể.
- **Chỉ kiểm tra một giá trị tham số:** bỏ qua parameter sensitivity và phân bố lệch.
- **Chỉ xem estimated cost:** không so sánh estimated rows với actual rows và tài nguyên thực tế.
- **Quy mọi sai số join cho thống kê nhiều cột:** nguyên nhân có thể nằm ở thống kê hai bảng, dữ liệu phân vùng, predicate hoặc ràng buộc chưa được khai báo.
- **Không kiểm tra truy vấn khác:** một thay đổi thống kê có thể khiến kế hoạch của workload khác thay đổi.

## 15. Checklist triển khai thống kê mở rộng

| Câu hỏi | Kết quả cần xác nhận |
|---|---|
| Truy vấn có lọc hoặc nhóm theo nhiều cột cùng bảng không? | Có mẫu truy vấn và tần suất rõ ràng |
| Estimated rows lệch actual rows ở node nào? | Xác định được node đầu tiên có sai lệch đáng kể |
| Các cột có tương quan hoặc nhóm giá trị phổ biến không? | Có bằng chứng từ dữ liệu hoặc quy tắc nghiệp vụ |
| DBMS hỗ trợ loại thống kê nào cho trường hợp đó? | Chọn đúng dependencies, MCV, density, column group, histogram hoặc filtered stats |
| Thống kê hiện tại có mới và đủ mẫu không? | Có thời điểm cập nhật và chất lượng mẫu phù hợp |
| Đã thu thập lại sau khi tạo/thay đổi chưa? | Lệnh ANALYZE/update stats hoàn tất |
| Kế hoạch mới có ước lượng gần thực tế hơn không? | Estimated rows và actual rows được đối chiếu |
| Thời gian và tài nguyên có cải thiện không? | Có số đo trước/sau cùng điều kiện |
| Truy vấn khác có bị ảnh hưởng không? | Đã kiểm tra workload liên quan |

## 16. Nguyên tắc ra quyết định

Thống kê nhiều cột và thống kê mở rộng có giá trị khi sai lệch cardinality bắt nguồn từ tương quan, độ lệch hoặc số tổ hợp mà thống kê đơn cột không mô tả đủ. PostgreSQL, SQL Server, MySQL và Oracle có những cơ chế khác nhau; cần chọn đúng khả năng của hệ quản trị đang vận hành thay vì áp dụng một công thức chung.

Hãy bắt đầu từ truy vấn thực tế và node có sai lệch đầu tiên. Kiểm tra phân bố dữ liệu, xác định loại quan hệ giữa các cột, tạo thống kê có mục tiêu và thu thập lại. Sau đó so sánh kế hoạch, số hàng thực tế, I/O, bộ nhớ, thời gian và tác động lên các truy vấn khác.

Một thống kê tốt giúp bộ tối ưu đưa ra quyết định dựa trên mô tả dữ liệu gần thực tế hơn. Hiệu năng chỉ được cải thiện khi quyết định mới phù hợp với workload và đường truy cập dữ liệu; vì vậy, mọi thay đổi đều phải được kiểm chứng bằng số đo trước và sau.
