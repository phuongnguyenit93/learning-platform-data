# Composite partitioning và lựa chọn subpartition trong Oracle

Partitioning chia một bảng lớn thành các phần nhỏ hơn để quản lý và truy cập dữ liệu hiệu quả. Với **composite partitioning** (phân vùng kết hợp), Oracle chia bảng theo hai tầng: partition ở tầng ngoài và subpartition ở tầng trong. Tầng partition thường biểu diễn một chiều phân chia lớn như thời gian hoặc khu vực; tầng subpartition tiếp tục chia nhỏ mỗi partition theo một chiều khác như khách hàng, vùng bán hàng hoặc hash key.

Chọn đúng subpartition key và phương pháp subpartition có thể giúp truy vấn loại bỏ thêm các vùng dữ liệu không cần đọc, phân phối dữ liệu và I/O hợp lý, hỗ trợ quản lý dữ liệu theo vòng đời. Chọn sai có thể tạo quá nhiều subpartition, tăng chi phí metadata và maintenance, trong khi truy vấn vẫn phải đọc nhiều dữ liệu.

Bài học này giải thích cấu trúc hai tầng, các kiểu composite partitioning phổ biến, cách tạo bảng RANGE-HASH và RANGE-LIST, subpartition template, partition pruning/subpartition pruning, local/global index, metadata và tiêu chí chọn subpartition theo workload.

## 1. Partition và subpartition là gì?

Partitioning chia một bảng logic thành các phần được quản lý riêng. Ứng dụng vẫn truy vấn một bảng bằng tên bảng; Oracle xác định partition hoặc subpartition cần truy cập dựa trên điều kiện truy vấn và metadata partitioning.

Với bảng composite-partitioned:

- **Partition** là phần chia ở tầng thứ nhất.
- **Subpartition** là phần chia ở tầng thứ hai bên trong từng partition.
- **Partition key** xác định partition.
- **Subpartition key** xác định subpartition bên trong partition tương ứng.

Ví dụ một bảng giao dịch bán hàng có thể chia theo hai chiều:

1. Tầng partition theo quý của ngày bán hàng.
2. Tầng subpartition theo HASH của mã khách hàng.

~~~text
SALES_FACT
|
+-- P2025_Q1
|   +-- SP1 (hash customer)
|   +-- SP2
|   +-- SP3
|   +-- SP4
|
+-- P2025_Q2
|   +-- SP1
|   +-- SP2
|   +-- SP3
|   +-- SP4
|
+-- P2025_Q3
|   +-- SP1
|   +-- SP2
|   +-- SP3
|   +-- SP4
|
+-- P2025_Q4
    +-- SP1
    +-- SP2
    +-- SP3
    +-- SP4
~~~

Hình dung trên cho thấy mỗi partition có bốn subpartition. Nếu có bốn partition và bốn subpartition cho mỗi partition, bảng có tổng cộng 16 subpartition.

### 1.1. Partitioning không tạo ra nhiều bảng độc lập

Các partition và subpartition thuộc cùng một bảng logic:

~~~sql
SELECT *
FROM sales_fact
WHERE sale_date >= DATE '2025-01-01'
  AND sale_date <  DATE '2025-04-01';
~~~

Không cần UNION thủ công từng partition. Optimizer có thể thực hiện partition pruning để chỉ truy cập các partition liên quan.

### 1.2. Hai tầng giải quyết hai chiều phân chia

| Tầng | Câu hỏi thiết kế | Ví dụ |
|---|---|---|
| Partition | Dữ liệu được quản lý theo nhóm lớn nào? | Quý bán hàng, năm tài chính, khu vực |
| Subpartition | Trong mỗi nhóm lớn, cần chia nhỏ theo chiều nào? | Khách hàng, hash key, vùng, loại giao dịch |

Không nhất thiết phải có hai tầng chỉ vì bảng lớn. Nếu một partitioning key đã hỗ trợ pruning và maintenance đủ tốt, thêm subpartition có thể chỉ làm tăng độ phức tạp.

## 2. Composite partitioning hoạt động như thế nào?

Composite partitioning áp dụng một phương pháp partitioning ở tầng ngoài và một phương pháp subpartitioning ở tầng trong. Một số tổ hợp phổ biến:

- RANGE-HASH: partition theo khoảng giá trị, subpartition theo hash.
- RANGE-LIST: partition theo khoảng giá trị, subpartition theo danh sách giá trị.
- RANGE-RANGE: partition theo một khoảng, subpartition theo một khoảng khác.
- LIST-HASH: partition theo danh sách, subpartition theo hash.
- LIST-RANGE: partition theo danh sách, subpartition theo khoảng.
- LIST-LIST: cả hai tầng đều chia theo danh sách.
- HASH-HASH: partition và subpartition đều dùng hash.

Oracle hỗ trợ nhiều tổ hợp composite partitioning; cú pháp và một số khả năng cụ thể có thể phụ thuộc phiên bản. Khi thiết kế, hãy xác nhận loại partitioning được hỗ trợ trong phiên bản database đang triển khai.

### 2.1. RANGE-HASH

Tầng ngoài dùng RANGE, thường theo ngày hoặc số thứ tự. Tầng trong dùng HASH, thường theo customer_id, account_id hoặc một khóa phân phối.

Phù hợp khi:

- Dữ liệu có vòng đời theo thời gian.
- Truy vấn thường lọc theo khoảng thời gian.
- Trong từng khoảng thời gian, dữ liệu cần phân phối thành nhiều vùng để giảm tập trung I/O hoặc hỗ trợ quản lý.
- Truy vấn thường có cả điều kiện thời gian và hash key.

Ví dụ: dữ liệu bán hàng theo quý, chia tiếp thành tám hash subpartition theo CUSTOMER_ID.

### 2.2. RANGE-LIST

Tầng ngoài chia theo khoảng, tầng trong chia theo danh sách. Ví dụ:

- Partition theo quý.
- Subpartition theo REGION_CODE: NORTH, CENTRAL, SOUTH và OTHER.

Phù hợp khi mỗi khoảng thời gian cần được tách theo các nhóm nghiệp vụ hữu hạn, dễ giải thích và có yêu cầu truy vấn theo nhóm.

### 2.3. RANGE-RANGE

Tầng ngoài chia theo một khoảng, tầng trong chia theo khoảng thứ hai. Ví dụ:

- Partition theo ORDER_DATE.
- Subpartition theo SHIP_DATE.

Phù hợp khi hai chiều thời gian đều có ý nghĩa trong truy vấn hoặc quản lý. Cần chú ý các khoảng subpartition ở từng partition phải được thiết kế nhất quán với dữ liệu và ranh giới nghiệp vụ.

### 2.4. LIST-HASH

Tầng ngoài chia theo nhóm danh mục như REGION_CODE hoặc BUSINESS_UNIT; tầng trong dùng HASH để phân phối dữ liệu theo khóa có nhiều giá trị.

Phù hợp khi số nhóm partition hữu hạn, nhưng mỗi nhóm vẫn chứa nhiều dữ liệu và cần phân phối đều theo một khóa.

## 3. Chọn partition key trước, rồi mới chọn subpartition key

Một cách thiết kế thực tế là bắt đầu từ câu hỏi quản lý dữ liệu và truy vấn phổ biến:

1. Dữ liệu được thêm vào theo chiều nào?
2. Dữ liệu cũ được lưu trữ, nén hoặc xóa theo chu kỳ nào?
3. Các truy vấn thường lọc theo cột nào?
4. Có khóa thứ hai giúp giảm vùng dữ liệu cần đọc bên trong partition không?
5. Có cần phân phối dữ liệu để tránh tập trung vào một vùng không?

Ví dụ bảng FACT_SALES:

| Thuộc tính | Giá trị |
|---|---|
| Số dòng | Hàng trăm triệu |
| Dữ liệu mới | Thêm liên tục theo SALE_DATE |
| Truy vấn báo cáo | Lọc khoảng SALE_DATE |
| Truy vấn khách hàng | Lọc CUSTOMER_ID trong khoảng thời gian |
| Vòng đời | Dữ liệu theo quý được archive hoặc drop sau thời hạn |

Một lựa chọn có thể là RANGE(SALE_DATE) ở tầng partition và HASH(CUSTOMER_ID) ở tầng subpartition. Partition key giải quyết lọc thời gian và vòng đời; subpartition key giúp chia nhỏ dữ liệu khách hàng bên trong từng quý.

Không chọn CUSTOMER_ID làm partition key chỉ vì ứng dụng hay tìm theo khách hàng nếu yêu cầu retention, archive và drop dữ liệu lại chủ yếu theo thời gian. Khi đó, RANGE theo ngày ở tầng ngoài thường phù hợp hơn với vòng đời dữ liệu.

## 4. Chuẩn bị bảng thực hành RANGE-HASH

Ta tạo bảng bán hàng:

- SALE_DATE: ngày bán hàng, partition key.
- CUSTOMER_ID: mã khách hàng, subpartition key.
- SALE_ID: mã giao dịch.
- REGION_CODE: vùng bán hàng.
- AMOUNT: giá trị giao dịch.

Ví dụ dùng RANGE theo quý và HASH theo CUSTOMER_ID với bốn subpartition trong mỗi partition.

### 4.1. Tạo bảng

Chạy trong schema lab thuộc PDB thực hành. Nếu bảng cùng tên đã tồn tại, hãy dùng schema hoặc tên khác; không ghi đè dữ liệu đang sử dụng.

~~~sql
CREATE TABLE lab_sales_fact (
    sale_id      NUMBER(12) NOT NULL,
    sale_date    DATE NOT NULL,
    customer_id  NUMBER(10) NOT NULL,
    region_code  VARCHAR2(12 CHAR) NOT NULL,
    amount       NUMBER(14,2) NOT NULL,
    CONSTRAINT ck_lab_sales_amount CHECK (amount >= 0)
)
PARTITION BY RANGE (sale_date)
SUBPARTITION BY HASH (customer_id)
SUBPARTITIONS 4
(
    PARTITION p2025_q1 VALUES LESS THAN (DATE '2025-04-01'),
    PARTITION p2025_q2 VALUES LESS THAN (DATE '2025-07-01'),
    PARTITION p2025_q3 VALUES LESS THAN (DATE '2025-10-01'),
    PARTITION p2025_q4 VALUES LESS THAN (DATE '2026-01-01'),
    PARTITION pmax     VALUES LESS THAN (MAXVALUE)
);
~~~

Với RANGE partitioning, partition đầu tiên nhận mọi giá trị nhỏ hơn ranh giới đầu tiên. Trong ví dụ này, P2025_Q1 nhận các ngày trước 1/4/2025; P_MAX nhận các ngày từ 1/1/2026 trở đi. Khi triển khai, hãy khai báo các mốc sao cho dải thời gian và tên partition phản ánh đúng nghiệp vụ.

Mỗi partition có bốn hash subpartition theo CUSTOMER_ID.

### 4.2. Thêm dữ liệu mẫu

~~~sql
INSERT INTO lab_sales_fact (
    sale_id,
    sale_date,
    customer_id,
    region_code,
    amount
)
SELECT
    LEVEL,
    DATE '2025-01-01' + MOD(LEVEL, 365),
    MOD(LEVEL * 37, 10000) + 1,
    CASE MOD(LEVEL, 3)
        WHEN 0 THEN 'NORTH'
        WHEN 1 THEN 'CENTRAL'
        ELSE 'SOUTH'
    END,
    MOD(LEVEL * 19, 100000) / 100
FROM dual
CONNECT BY LEVEL <= 200000;

COMMIT;
~~~

### 4.3. Tạo local index

~~~sql
CREATE INDEX ix_lab_sales_customer
ON lab_sales_fact (customer_id)
LOCAL;
~~~

LOCAL index được chia theo cấu trúc partitioning của bảng. Với bảng composite-partitioned, local index cũng được tổ chức tương ứng theo các partition/subpartition của bảng. Local index thường thuận lợi cho maintenance theo partition và có thể hỗ trợ các truy vấn trong từng partition.

### 4.4. Thu thập statistics

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname     => USER,
        tabname     => 'LAB_SALES_FACT',
        cascade     => TRUE,
        granularity => 'ALL'
    );
END;
/
~~~

Statistics giúp optimizer ước lượng số dòng và chi phí cho partition pruning, subpartition pruning và access path. Chính sách thu thập statistics có thể khác theo môi trường; không chạy gather thủ công trên production khi chưa xem xét chính sách DBA.

## 5. RANGE-LIST và subpartition template

Với RANGE-LIST, tầng ngoài chia theo thời gian, tầng trong chia theo danh sách vùng. Subpartition template định nghĩa cùng một cấu trúc subpartition cho mỗi partition được tạo.

### 5.1. Tạo bảng

~~~sql
CREATE TABLE lab_sales_region (
    sale_id      NUMBER(12) NOT NULL,
    sale_date    DATE NOT NULL,
    region_code  VARCHAR2(12 CHAR) NOT NULL,
    customer_id  NUMBER(10) NOT NULL,
    amount       NUMBER(14,2) NOT NULL
)
PARTITION BY RANGE (sale_date)
SUBPARTITION BY LIST (region_code)
SUBPARTITION TEMPLATE
(
    SUBPARTITION sp_north   VALUES ('NORTH'),
    SUBPARTITION sp_central VALUES ('CENTRAL'),
    SUBPARTITION sp_south   VALUES ('SOUTH'),
    SUBPARTITION sp_other   VALUES (DEFAULT)
)
(
    PARTITION p2025_q1 VALUES LESS THAN (DATE '2025-04-01'),
    PARTITION p2025_q2 VALUES LESS THAN (DATE '2025-07-01'),
    PARTITION p2025_q3 VALUES LESS THAN (DATE '2025-10-01'),
    PARTITION p2025_q4 VALUES LESS THAN (DATE '2026-01-01')
);
~~~

Oracle áp dụng template cho từng partition. Mỗi partition có các subpartition cho NORTH, CENTRAL, SOUTH và OTHER. Khi thêm partition thời gian mới, template giúp tạo đúng cấu trúc subpartition thống nhất.

### 5.2. Vì sao cần template?

Nếu không dùng template, ta có thể phải khai báo subpartition cho từng partition. Với nhiều partition theo tháng/quý/năm, việc lặp cấu hình dễ gây thiếu hoặc khác nhau giữa các partition.

Template giúp:

- Duy trì cùng danh sách subpartition cho các partition.
- Đặt tên subpartition dễ nhận diện.
- Định nghĩa DEFAULT cho các giá trị vùng chưa liệt kê.
- Đơn giản hóa việc thêm partition mới.

### 5.3. Thêm dữ liệu và kiểm tra

~~~sql
INSERT INTO lab_sales_region VALUES
  (1, DATE '2025-01-10', 'NORTH', 101, 1200);
INSERT INTO lab_sales_region VALUES
  (2, DATE '2025-02-11', 'SOUTH', 102, 900);
INSERT INTO lab_sales_region VALUES
  (3, DATE '2025-04-05', 'CENTRAL', 103, 1500);
INSERT INTO lab_sales_region VALUES
  (4, DATE '2025-05-20', 'WEST', 104, 700);
COMMIT;
~~~

WEST không có subpartition riêng nên thuộc DEFAULT subpartition SP_OTHER trong partition thời gian tương ứng.

## 6. Partition pruning và subpartition pruning

Pruning là việc Oracle loại bỏ partition hoặc subpartition không cần truy cập dựa trên điều kiện truy vấn.

- **Partition pruning**: loại bỏ partition ở tầng ngoài.
- **Subpartition pruning**: tiếp tục loại bỏ subpartition ở tầng trong.

Mục tiêu là giảm số vùng dữ liệu cần đọc, từ đó giảm I/O và công việc xử lý.

### 6.1. Chỉ có điều kiện trên partition key

Với bảng RANGE-HASH theo SALE_DATE và CUSTOMER_ID:

~~~sql
SELECT COUNT(*)
FROM lab_sales_fact
WHERE sale_date >= DATE '2025-04-01'
  AND sale_date <  DATE '2025-07-01';
~~~

Oracle có thể chỉ truy cập partition P2025_Q2. Vì không có điều kiện CUSTOMER_ID, tất cả hash subpartition bên trong partition này có thể cần được xét.

### 6.2. Có cả partition key và subpartition key

~~~sql
SELECT sale_id, sale_date, customer_id, amount
FROM lab_sales_fact
WHERE sale_date >= DATE '2025-04-01'
  AND sale_date <  DATE '2025-07-01'
  AND customer_id = 1234;
~~~

Oracle có thể:

1. Prune các partition không thuộc quý 2/2025.
2. Trong partition còn lại, prune hash subpartition không tương ứng với CUSTOMER_ID = 1234.
3. Truy cập các entry/dòng phù hợp trong subpartition được chọn.

Đây là trường hợp khai thác hai tầng rõ nhất: predicate thời gian giới hạn partition, predicate khách hàng giới hạn subpartition.

### 6.3. Chỉ có điều kiện trên subpartition key

~~~sql
SELECT COUNT(*)
FROM lab_sales_fact
WHERE customer_id = 1234;
~~~

Oracle có thể prune subpartition theo hash key trong từng partition, nhưng vẫn phải xem xét các partition thời gian vì không có điều kiện SALE_DATE. Subpartition pruning không tự động loại bỏ toàn bộ các partition ngoài.

### 6.4. Predicate không phù hợp có thể hạn chế pruning

Điều kiện viết trực tiếp trên partition key thường dễ giúp optimizer xác định phạm vi:

~~~sql
WHERE sale_date >= DATE '2025-04-01'
  AND sale_date < DATE '2025-07-01'
~~~

Tránh áp dụng hàm không cần thiết lên partition key:

~~~sql
-- Có thể làm pruning khó hơn tùy biểu thức và khả năng biến đổi:
WHERE TO_CHAR(sale_date, 'YYYY-MM') = '2025-04'
~~~

Hãy dùng khoảng ngày nửa mở thay cho việc chuyển cột ngày thành chuỗi. Nếu nghiệp vụ thực sự cần truy vấn theo biểu thức, hãy xem xét virtual column/function-based partitioning phù hợp và kiểm tra plan.

## 7. Pruning với RANGE-LIST

Với bảng LAB_SALES_REGION, truy vấn theo thời gian và vùng:

~~~sql
SELECT sale_id, sale_date, region_code, amount
FROM lab_sales_region
WHERE sale_date >= DATE '2025-01-01'
  AND sale_date <  DATE '2025-04-01'
  AND region_code IN ('NORTH', 'SOUTH');
~~~

Oracle có thể prune:

- Partition theo khoảng SALE_DATE, chỉ còn P2025_Q1.
- Subpartition theo LIST REGION_CODE, chỉ còn SP_NORTH và SP_SOUTH.

Nếu chỉ có điều kiện REGION_CODE mà không có SALE_DATE:

~~~sql
SELECT COUNT(*)
FROM lab_sales_region
WHERE region_code = 'NORTH';
~~~

Oracle có thể chọn subpartition NORTH trong mỗi partition, nhưng vẫn xét các partition thời gian có thể chứa dữ liệu.

## 8. Đọc execution plan để xem pruning

### 8.1. EXPLAIN PLAN

~~~sql
EXPLAIN PLAN FOR
SELECT sale_id, sale_date, customer_id, amount
FROM lab_sales_fact
WHERE sale_date >= DATE '2025-04-01'
  AND sale_date <  DATE '2025-07-01'
  AND customer_id = 1234;

SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY(
        NULL,
        NULL,
        'BASIC +PARTITION +PREDICATE +COST +NOTE'
    )
);
~~~

Trong plan, xem các cột PSTART và PSTOP cùng operation liên quan đến table/index access. Với partitioned object, Oracle có thể hiển thị phạm vi partition/subpartition được truy cập hoặc ký hiệu cho dynamic pruning.

### 8.2. Static và dynamic pruning

- **Static pruning**: optimizer xác định partition cần truy cập từ literal hoặc thông tin có thể biết ngay khi parse.
- **Dynamic pruning**: partition được xác định tại runtime, ví dụ khi giá trị đến từ bind variable, join hoặc một biểu thức chỉ biết khi thực thi.

Plan có thể hiển thị giá trị PSTART/PSTOP cụ thể hoặc ký hiệu như KEY cho pruning động, tùy access path và phiên bản.

### 8.3. Xem thống kê runtime

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       sale_id, sale_date, customer_id, amount
FROM lab_sales_fact
WHERE sale_date >= DATE '2025-04-01'
  AND sale_date <  DATE '2025-07-01'
  AND customer_id = 1234;

SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +PARTITION +PREDICATE +COST'
    )
);
~~~

ALLSTATS LAST cho phép xem thống kê thực tế của lần chạy gần nhất nếu được thu thập. Hãy so sánh E-Rows và A-Rows, buffers, reads và thời gian. EXPLAIN PLAN một mình chỉ cho biết kế hoạch ước lượng, không chứng minh runtime thực tế.

## 9. Subpartition key nên chọn như thế nào?

Subpartition key cần phục vụ một mục tiêu rõ ràng. Một số tiêu chí:

### 9.1. Truy vấn có predicate trên subpartition key

Nếu phần lớn truy vấn luôn lọc theo CUSTOMER_ID, subpartition theo HASH(CUSTOMER_ID) có thể giúp Oracle prune subpartition khi có điều kiện equality phù hợp.

Nếu ứng dụng thường lọc REGION_CODE bằng danh sách nhỏ, LIST subpartition có thể phù hợp.

Nếu truy vấn cần khoảng giá trị thứ hai, RANGE subpartition có thể giúp loại trừ các khoảng không liên quan.

Không chọn key chỉ vì cột có vẻ quan trọng. Hãy xem predicate thực tế của các SQL thường chạy.

### 9.2. Cardinality và phân bố dữ liệu

HASH thường phù hợp với khóa có nhiều giá trị và cần phân phối tương đối đều. LIST phù hợp với số nhóm hữu hạn, có ý nghĩa nghiệp vụ. RANGE phù hợp khi giá trị có thứ tự và truy vấn dùng khoảng.

| Subpartition method | Đặc điểm key | Trường hợp thường cân nhắc |
|---|---|---|
| HASH | Nhiều giá trị, cần phân phối | CUSTOMER_ID, ACCOUNT_ID |
| LIST | Nhóm hữu hạn, có ý nghĩa | REGION_CODE, CHANNEL_CODE |
| RANGE | Có thứ tự, truy vấn theo khoảng | SHIP_DATE, EVENT_DATE, số mức |

### 9.3. Cân bằng dữ liệu

HASH có thể phân phối dòng giữa các subpartition dựa trên hash key. Đây là lựa chọn hữu ích khi không muốn một giá trị phổ biến tạo ra một subpartition quá lớn như cách chia LIST theo nhóm nghiệp vụ.

LIST có thể tạo kích thước subpartition không đồng đều nếu một nhóm chứa phần lớn dữ liệu. Cần đo phân bố trước khi quyết định.

RANGE có thể tạo subpartition mất cân bằng nếu ranh giới không phản ánh phân bố dữ liệu hoặc dữ liệu tập trung vào một khoảng.

### 9.4. Tính ổn định của key

Chọn cột subpartition có giá trị ít thay đổi. Nếu UPDATE thường xuyên làm thay đổi subpartition key, Oracle có thể phải di chuyển dòng giữa các subpartition; điều này làm tăng chi phí DML và có thể ảnh hưởng ROWID.

Nếu cột key là một thuộc tính nghiệp vụ có thể thay đổi nhiều, hãy cân nhắc tác động của row movement và index trước khi dùng làm subpartition key.

### 9.5. Maintenance và retention

Partition key thường gắn với đơn vị quản lý dữ liệu lớn: tháng, quý, năm, khu vực. Subpartition key nên hỗ trợ truy vấn/phân phối mà không làm maintenance trở nên quá phức tạp.

Nếu yêu cầu chủ yếu là drop dữ liệu cũ theo tháng, RANGE partitioning có thể đã đủ. Thêm HASH subpartition chỉ nên thực hiện khi có lợi ích về truy vấn, phân phối I/O, index hoặc vận hành được chứng minh.

## 10. Chọn số lượng subpartition

Số subpartition ảnh hưởng đến:

- Số vùng dữ liệu phải quản lý.
- Khả năng phân phối dữ liệu và I/O.
- Mức độ pruning khi truy vấn có subpartition key.
- Số partition/subpartition của local index.
- Metadata, statistics, backup, maintenance và thao tác DDL.

Ví dụ nếu có 120 partition theo tháng và mỗi partition có 16 subpartition:

\[
120 \times 16 = 1920 \text{ subpartitions}
\]

Nếu có thêm nhiều bảng fact và local index, số đối tượng partitioned cần quản lý có thể tăng nhanh.

### 10.1. Không chọn số subpartition theo số CPU một cách máy móc

HASH subpartitioning có thể giúp phân phối dữ liệu, nhưng đặt 64 subpartition chỉ vì máy có 64 CPU không bảo đảm query nhanh hơn 8 hoặc 16 subpartition. Số lượng cần dựa trên:

- Kích thước dữ liệu mỗi partition.
- Số block và mức song song thực tế.
- Số truy vấn đồng thời.
- Khả năng pruning.
- Kích thước local index.
- Thời gian tạo, rebuild và gather statistics.

### 10.2. Subpartition quá ít

Nếu mỗi partition có quá ít subpartition:

- Có thể chưa giảm đủ kích thước vùng đọc.
- Khả năng phân phối I/O có thể hạn chế.
- Một số workload vẫn tập trung vào ít vùng dữ liệu.

### 10.3. Subpartition quá nhiều

Nếu mỗi partition có quá nhiều subpartition:

- Tăng số lượng metadata.
- Tăng số đối tượng index subpartition.
- Tăng chi phí gather statistics và bảo trì.
- Dễ tạo nhiều subpartition rất nhỏ, làm tăng overhead.
- Quản trị DDL phức tạp hơn.

Chọn số lượng vừa đủ cho kích thước dữ liệu và workload. Hãy đo bằng dữ liệu đại diện trước khi áp dụng toàn bộ hệ thống.

## 11. Subpartition template

Template định nghĩa trước cấu trúc subpartition áp dụng cho từng partition. Đây là công cụ hữu ích khi tất cả partition cần cùng một cấu trúc tầng trong.

### 11.1. Template cho HASH

~~~sql
CREATE TABLE lab_hash_template (
    event_id    NUMBER NOT NULL,
    event_date  DATE NOT NULL,
    customer_id NUMBER NOT NULL,
    payload     VARCHAR2(100 CHAR)
)
PARTITION BY RANGE (event_date)
SUBPARTITION BY HASH (customer_id)
SUBPARTITION TEMPLATE
(
    SUBPARTITION sp_h1,
    SUBPARTITION sp_h2,
    SUBPARTITION sp_h3,
    SUBPARTITION sp_h4
)
(
    PARTITION p2025 VALUES LESS THAN (DATE '2026-01-01'),
    PARTITION p2026 VALUES LESS THAN (DATE '2027-01-01')
);
~~~

Template tạo cùng số lượng và cấu trúc hash subpartition cho các partition. Tên thực tế của subpartition được Oracle quản lý theo quy tắc đặt tên và metadata; hãy truy vấn USER_TAB_SUBPARTITIONS để xác định tên được tạo.

### 11.2. Template cho LIST

Ví dụ RANGE-LIST ở phần 5 đã định nghĩa template cho NORTH, CENTRAL, SOUTH và DEFAULT. Khi thêm partition thời gian, cấu trúc subpartition list được áp dụng thống nhất.

### 11.3. Khi không có template

Nếu không khai báo template, có thể chỉ định subpartition trực tiếp trong từng partition. Cách này hữu ích khi mỗi partition cần cấu trúc riêng, nhưng làm DDL dài và khó duy trì nhất quán.

Template phù hợp khi cấu trúc subpartition giống nhau. Nếu các partition có yêu cầu khác nhau, khai báo riêng có thể phù hợp hơn.

## 12. Local index và global index trên bảng composite-partitioned

Index là phần quan trọng của thiết kế partitioning. Cần chọn index sao cho vừa hỗ trợ truy vấn vừa đáp ứng yêu cầu maintenance.

### 12.1. Local index

Local index được chia theo cấu trúc partitioning của bảng. Mỗi partition/subpartition của index tương ứng với phần dữ liệu table tương ứng.

~~~sql
CREATE INDEX ix_lab_sales_date_local
ON lab_sales_fact (sale_date)
LOCAL;
~~~

Ưu điểm:

- Index partition/subpartition gắn với phạm vi dữ liệu của bảng.
- Maintenance một partition thường dễ kiểm soát hơn.
- Có thể rebuild hoặc quản lý một phần index theo đơn vị partition.
- Local index thường phù hợp với bảng có vòng đời dữ liệu theo partition.

Local index không phải lúc nào cũng tối ưu cho truy vấn tìm một khóa trên toàn bộ bảng; access path và phạm vi partition vẫn quyết định chi phí.

### 12.2. Global index

Global index có cấu trúc phân vùng độc lập với partitioning của bảng hoặc có thể là nonpartitioned index. Nó hữu ích khi truy vấn cần tìm theo khóa trên nhiều partition mà không có predicate partition key phù hợp.

Ưu điểm:

- Có thể cung cấp một cấu trúc index toàn cục theo key truy vấn.
- Hữu ích cho unique key không chứa partition key hoặc truy vấn xuyên nhiều partition.

Điểm cần cân nhắc:

- Một số thao tác DROP/TRUNCATE/EXCHANGE partition có thể làm global index không usable hoặc cần maintenance tùy cú pháp và phiên bản.
- Duy trì global index có thể tăng chi phí khi dữ liệu được quản lý theo partition.
- Cần chọn chính sách UPDATE INDEXES hoặc rebuild phù hợp.

### 12.3. Chọn local hay global

| Yêu cầu | Hướng thường cân nhắc |
|---|---|
| Maintenance dữ liệu theo partition thường xuyên | Local index |
| Truy vấn theo partition key và trong phạm vi partition | Local index thường phù hợp |
| Tìm khóa xuyên nhiều partition mà không có partition predicate | Global index có thể hữu ích |
| Unique key không chứa partition key | Có thể cần global unique index hoặc thiết kế khóa khác |
| Cần drop/truncate partition nhanh và đơn giản | Cân nhắc local index và ảnh hưởng global index |

Không có quy tắc “local luôn tốt” hoặc “global luôn nhanh”. Hãy xem predicate, constraint, maintenance và execution plan.

## 13. Partition-wise join và subpartitioning

Partitioning tương thích giữa hai bảng có thể giúp Oracle thực hiện partition-wise join, tức là nối các phần dữ liệu tương ứng thay vì phải xử lý toàn bộ hai bảng như hai khối lớn.

Ví dụ bảng SALES_FACT và SALES_TARGET đều partition theo cùng khoảng SALE_DATE, và có cấu trúc partition tương thích. Nếu truy vấn join theo partition key và điều kiện phù hợp, Oracle có thể xử lý từng cặp partition.

Với composite partitioning, subpartitioning tương thích cũng có thể hỗ trợ join ở mức nhỏ hơn, đặc biệt khi hai bảng dùng cùng phương pháp và key subpartition phù hợp. Điều kiện chính xác phụ thuộc partitioning scheme, join predicate và execution plan.

Không chỉ khai báo cùng số subpartition là đủ để bảo đảm partition-wise join. Hãy xác nhận cấu trúc partitioning và operation thực tế trong plan.

## 14. Xem metadata partition và subpartition

Oracle cung cấp các Data Dictionary views để xem cấu trúc.

### 14.1. Xem kiểu partitioning

~~~sql
SELECT
    table_name,
    partitioning_type,
    subpartitioning_type,
    partition_count,
    def_subpartition_count
FROM user_part_tables
WHERE table_name IN ('LAB_SALES_FACT', 'LAB_SALES_REGION');
~~~

### 14.2. Xem các partition

~~~sql
SELECT
    table_name,
    partition_name,
    partition_position,
    high_value,
    num_rows,
    tablespace_name
FROM user_tab_partitions
WHERE table_name = 'LAB_SALES_FACT'
ORDER BY partition_position;
~~~

### 14.3. Xem các subpartition

~~~sql
SELECT
    table_name,
    partition_name,
    subpartition_name,
    subpartition_position,
    high_value,
    num_rows,
    tablespace_name
FROM user_tab_subpartitions
WHERE table_name = 'LAB_SALES_FACT'
ORDER BY partition_name, subpartition_position;
~~~

### 14.4. Xem partition key và subpartition key

~~~sql
SELECT
    name,
    object_type,
    column_name,
    column_position
FROM user_part_key_columns
WHERE name = 'LAB_SALES_FACT'
ORDER BY column_position;
~~~

~~~sql
SELECT
    name,
    object_type,
    column_name,
    column_position
FROM user_subpart_key_columns
WHERE name = 'LAB_SALES_FACT'
ORDER BY column_position;
~~~

Tên view/cột metadata có thể khác theo loại đối tượng và phiên bản; kiểm tra ALL/USER dictionary views tương ứng nếu schema không sở hữu bảng. Các view USER_* chỉ hiển thị đối tượng thuộc schema hiện tại.

## 15. Maintenance ở tầng partition và subpartition

Một lợi ích quan trọng của partitioning là quản lý dữ liệu theo phần. Với composite table, cần phân biệt thao tác ở tầng partition và subpartition.

### 15.1. TRUNCATE PARTITION

~~~sql
ALTER TABLE lab_sales_fact
TRUNCATE PARTITION p2025_q1;
~~~

Lệnh xóa dữ liệu trong toàn bộ partition P2025_Q1, tức tất cả subpartition nằm trong partition đó. Bản thân bảng và các partition khác vẫn tồn tại.

### 15.2. TRUNCATE SUBPARTITION

~~~sql
ALTER TABLE lab_sales_fact
TRUNCATE SUBPARTITION subpartition_name;
~~~

Thay SUBPARTITION_NAME bằng tên thực tế tra từ USER_TAB_SUBPARTITIONS. Lệnh chỉ xóa dữ liệu trong một subpartition.

### 15.3. DROP PARTITION

~~~sql
ALTER TABLE lab_sales_fact
DROP PARTITION p2025_q1;
~~~

Lệnh loại bỏ partition cùng các subpartition của nó. Đây là thay đổi cấu trúc dữ liệu; kiểm tra index và phụ thuộc trước khi chạy.

### 15.4. ADD PARTITION

Với RANGE partitioning, có thể thêm partition ở cuối dải:

~~~sql
ALTER TABLE lab_sales_fact
ADD PARTITION p2026_q1
VALUES LESS THAN (DATE '2026-04-01');
~~~

Với bảng composite, subpartition mới phải được xác định theo template hoặc khai báo phù hợp với cú pháp của loại partitioning. Nếu bảng không có template, hãy cung cấp subpartition definitions theo yêu cầu của Oracle.

### 15.5. MOVE SUBPARTITION

Có thể di chuyển subpartition sang tablespace khác:

~~~sql
ALTER TABLE lab_sales_fact
MOVE SUBPARTITION subpartition_name
TABLESPACE users;
~~~

Thao tác MOVE có thể làm thay đổi ROWID và ảnh hưởng index; cần chọn tùy chọn cập nhật/rebuild index phù hợp với phiên bản và chính sách vận hành.

### 15.6. SPLIT và MERGE

Với partitioning RANGE/LIST, SPLIT có thể chia một partition thành nhiều partition theo ranh giới mới; MERGE có thể gộp các partition liền kề. Với composite table, phải chỉ rõ cấu trúc subpartition cho các phần mới theo cú pháp tương ứng.

Ví dụ cú pháp partition-level split ở mức minh họa:

~~~sql
ALTER TABLE lab_sales_fact
SPLIT PARTITION pmax AT (DATE '2026-04-01')
INTO (
    PARTITION p2026_q1,
    PARTITION pmax
);
~~~

Đây là ví dụ khung cho RANGE partition. Khi bảng có subpartition, hãy cung cấp subpartition definitions hoặc dùng template phù hợp; không sao chép nguyên lệnh vào production nếu chưa kiểm tra cú pháp chính xác cho cấu trúc bảng.

## 16. Interval partitioning kết hợp subpartition

Với dữ liệu tăng theo thời gian, Oracle có thể tự tạo partition RANGE mới bằng INTERVAL partitioning khi dữ liệu vượt ranh giới đã khai báo.

Ví dụ khái niệm:

~~~sql
CREATE TABLE lab_interval_sales (
    sale_id     NUMBER NOT NULL,
    sale_date   DATE NOT NULL,
    customer_id NUMBER NOT NULL,
    amount      NUMBER(14,2)
)
PARTITION BY RANGE (sale_date)
INTERVAL (NUMTOYMINTERVAL(1, 'MONTH'))
SUBPARTITION BY HASH (customer_id)
SUBPARTITIONS 4
(
    PARTITION p_before_2025
    VALUES LESS THAN (DATE '2025-01-01')
);
~~~

Oracle có thể tạo interval partition cho các tháng mới khi dữ liệu được chèn vượt partition transition point. Mỗi interval partition sử dụng cấu trúc subpartition theo khai báo composite.

Interval partitioning giảm nhu cầu thêm partition thủ công, nhưng không tự giải quyết mọi bài toán maintenance. Cần kiểm tra phiên bản Oracle, loại dữ liệu partition key, interval expression và giới hạn số partition.

## 17. NULL và DEFAULT trong subpartition

### 17.1. LIST subpartition

Với LIST subpartition, cần xác định rõ cách xử lý các giá trị không nằm trong danh sách:

~~~sql
SUBPARTITION TEMPLATE
(
    SUBPARTITION sp_north VALUES ('NORTH'),
    SUBPARTITION sp_south VALUES ('SOUTH'),
    SUBPARTITION sp_other VALUES (DEFAULT)
)
~~~

DEFAULT nhận các giá trị không được liệt kê trong những subpartition còn lại. Nếu không có DEFAULT và dữ liệu chèn mang giá trị không khớp, INSERT có thể thất bại vì không tìm được partition/subpartition phù hợp.

Nếu cột có thể NULL, hãy kiểm tra quy tắc NULL và constraint của cột; không dựa vào DEFAULT để thay thế một thiết kế dữ liệu rõ ràng.

### 17.2. RANGE subpartition

Với RANGE, ranh giới phải bao phủ miền giá trị có thể xuất hiện. Nếu cần nhận mọi giá trị lớn hơn, thường có thể dùng MAXVALUE ở subpartition cuối của mỗi partition theo thiết kế phù hợp.

### 17.3. HASH subpartition

HASH phân phối theo hàm hash của key, không có danh sách giá trị để khai báo DEFAULT. Nếu key có NULL, Oracle vẫn áp dụng quy tắc hash cho giá trị đó; hãy kiểm tra constraint và hành vi dữ liệu theo thiết kế thực tế.

## 18. Subpartition pruning không thay thế partition pruning

Giả sử bảng RANGE-HASH:

- Partition key: SALE_DATE.
- Subpartition key: CUSTOMER_ID.

Các tình huống:

| Predicate | Partition pruning | Subpartition pruning |
|---|---|---|
| Chỉ SALE_DATE | Có thể chọn một/vài partition | Thường xét tất cả subpartition trong partition được chọn |
| Chỉ CUSTOMER_ID | Không loại được partition theo thời gian | Có thể chọn subpartition hash tương ứng trong các partition |
| SALE_DATE và CUSTOMER_ID | Chọn partition theo ngày | Tiếp tục chọn subpartition theo hash key |
| Không có cả hai | Không có pruning theo hai key | Không có pruning theo hai key |

Đây là cách nhìn khái quát. Optimizer có thể áp dụng pruning tĩnh hoặc động, và access path thực tế còn phụ thuộc biểu thức, bind, join, statistics và phiên bản.

Nếu phần lớn truy vấn chỉ lọc CUSTOMER_ID mà không có SALE_DATE, RANGE-HASH vẫn có thể phải xét mọi partition thời gian. Khi đó cần đánh giá liệu subpartition pruning có đủ giảm chi phí hay một thiết kế partitioning khác phù hợp hơn.

## 19. Những sai lầm thiết kế thường gặp

| Sai lầm | Hệ quả | Cách xem xét lại |
|---|---|---|
| Chọn subpartition key không xuất hiện trong predicate | Subpartition pruning ít giá trị | Phân tích SQL workload trước khi chọn key |
| Tạo quá nhiều subpartition | Metadata/index/statistics/maintenance tăng | Chọn số lượng dựa trên kích thước và đo đạc |
| Dùng LIST cho nhóm có phân bố cực lệch | Một số subpartition rất lớn, số khác nhỏ | Đánh giá HASH hoặc điều chỉnh nhóm |
| Dùng HASH khi truy vấn cần khoảng giá trị | Không tận dụng được range pruning theo key | Cân nhắc RANGE nếu predicate theo khoảng |
| Chỉ có subpartition predicate mà quên partition key | Vẫn phải xét nhiều partition ngoài | Bổ sung predicate partition key khi nghiệp vụ cho phép |
| Tạo local index cho mọi cột | Nhiều index subpartition, tăng DML cost | Chọn index theo workload |
| Bỏ qua global index khi drop/truncate partition | Index có thể cần rebuild/maintenance | Lập kế hoạch index maintenance trước DDL |
| Dựa vào EXPLAIN PLAN mà không đo runtime | Có thể kết luận sai về lợi ích pruning | Xem actual rows, buffers, reads và thời gian |
| Dùng hàm lên partition key không cần thiết | Có thể làm pruning kém hiệu quả | Viết predicate trực tiếp theo khoảng key |

## 20. Bài tập thực hành

### Bài 1 — Phân biệt hai tầng

Cho bảng partition theo RANGE(SALE_DATE), subpartition theo HASH(CUSTOMER_ID).

**Yêu cầu:** giải thích partition key và subpartition key; cho biết mỗi partition có bao nhiêu subpartition nếu khai báo SUBPARTITIONS 8 và có 12 partition.

**Đáp án định hướng:** 12 × 8 = 96 subpartition.

### Bài 2 — Tạo RANGE-HASH

Tạo bảng giao dịch partition theo tháng và subpartition theo hash account_id với tám subpartition mỗi tháng.

**Yêu cầu:** chèn dữ liệu qua hai tháng và xem metadata.

### Bài 3 — Tạo RANGE-LIST

Tạo bảng sự kiện partition theo quý, subpartition theo danh sách EVENT_TYPE hoặc REGION_CODE, có DEFAULT subpartition.

**Câu hỏi:** dữ liệu mang một region mới sẽ vào đâu?

### Bài 4 — Quan sát pruning hai tầng

Viết ba truy vấn trên LAB_SALES_FACT:

1. Chỉ lọc SALE_DATE.
2. Chỉ lọc CUSTOMER_ID.
3. Lọc cả SALE_DATE và CUSTOMER_ID.

Dùng DBMS_XPLAN để so sánh PSTART/PSTOP và operation.

### Bài 5 — Template

Tạo RANGE-LIST table có template bốn vùng. Thêm partition thời gian mới và kiểm tra cấu trúc subpartition tự động được áp dụng.

### Bài 6 — Local và global index

Tạo local index trên CUSTOMER_ID và so sánh với một global index phù hợp cho truy vấn xuyên partition.

**Câu hỏi:** thao tác DROP/TRUNCATE partition ảnh hưởng maintenance của hai loại index thế nào?

### Bài 7 — Chọn số subpartition

Một bảng có 60 partition tháng, mỗi partition dự kiến 20 triệu dòng. So sánh các phương án 4, 8, 16 và 32 hash subpartition.

**Yêu cầu:** nêu số subpartition tổng cộng, lợi ích dự kiến và chi phí metadata/maintenance cần đo.

### Bài 8 — Chọn method

Chọn HASH, LIST hoặc RANGE cho subpartition trong các tình huống:

- CUSTOMER_ID có nhiều giá trị và cần phân phối đều.
- REGION_CODE có năm nhóm nghiệp vụ cố định.
- SHIP_DATE cần truy vấn theo khoảng.

### Bài 9 — Partition maintenance

Tra tên một subpartition thực tế trong USER_TAB_SUBPARTITIONS và viết lệnh TRUNCATE SUBPARTITION tương ứng trong môi trường lab.

### Bài 10 — Thiết kế theo workload

Một bảng fact có truy vấn chủ yếu theo ngày và khách hàng; dữ liệu cũ được drop theo quý. Đề xuất partition key, subpartition key, method và số subpartition khởi đầu. Giải thích cần đo những gì trước khi triển khai.

## 21. Quy trình lựa chọn subpartition

Khi thiết kế composite partitioning, hãy đi theo thứ tự:

1. **Xác định vòng đời dữ liệu:** cần drop, archive, compress hoặc exchange dữ liệu theo tháng/quý/năm hay nhóm nghiệp vụ nào?
2. **Chọn partition key:** ưu tiên chiều hỗ trợ maintenance và predicate lọc chính.
3. **Phân tích SQL workload:** xác định cột thường lọc bên trong mỗi partition.
4. **Chọn subpartition method:** HASH cho phân phối; LIST cho nhóm hữu hạn; RANGE cho truy vấn theo khoảng.
5. **Chọn subpartition key:** dùng cột ổn định, xuất hiện trong predicate và có phân bố phù hợp.
6. **Ước lượng số subpartition:** cân bằng kích thước, pruning, concurrency và chi phí quản trị.
7. **Thiết kế template:** dùng khi các partition cần cùng cấu trúc subpartition.
8. **Thiết kế index:** cân nhắc local/global theo truy vấn và partition maintenance.
9. **Thu thập statistics:** bảo đảm optimizer có dữ liệu ước lượng.
10. **Đo execution plan và runtime:** kiểm tra pruning, actual rows, buffers, I/O và chi phí DML.

Sơ đồ:

~~~text
Xác định vòng đời và truy vấn chính
               |
               v
        Chọn partition key
               |
               v
  Cần chia nhỏ bên trong partition?
          /             \
        Không            Có
         |                |
         v                v
   Partition đơn     Phân tích predicate
                          |
                          v
               Chọn HASH / LIST / RANGE
                          |
                          v
                Chọn subpartition key
                          |
                          v
                Ước lượng số subpartition
                          |
                          v
                 Template và index
                          |
                          v
                Thu thập statistics
                          |
                          v
               Xem plan và đo runtime
                          |
                          v
                 Điều chỉnh thiết kế
~~~

Composite partitioning chia bảng thành hai tầng để kết hợp quản lý dữ liệu theo nhóm lớn với pruning hoặc phân phối chi tiết bên trong từng nhóm. Partition key nên phản ánh vòng đời dữ liệu và điều kiện truy vấn chính; subpartition key nên phục vụ truy vấn, cân bằng dữ liệu hoặc phân phối I/O. RANGE-HASH thường phù hợp với dữ liệu thời gian cần chia theo khóa có nhiều giá trị; RANGE-LIST phù hợp khi mỗi khoảng thời gian cần các nhóm nghiệp vụ hữu hạn; RANGE-RANGE phù hợp khi cả hai chiều đều có ý nghĩa theo khoảng. Số subpartition, template và local/global index cần được chọn theo workload thực tế, sau đó xác nhận bằng execution plan và thống kê runtime.
