# Khóa phân vùng theo thời gian, khách hàng hoặc miền dữ liệu

Partition key là cột hoặc nhóm cột Oracle dùng để quyết định một hàng thuộc partition nào của bảng. Chọn partition key ảnh hưởng trực tiếp đến khả năng partition pruning, cách dữ liệu được phân phối, việc lưu trữ theo vòng đời, chi phí bảo trì và khả năng tận dụng index hoặc partition-wise join.

Ba hướng thiết kế thường gặp là:

- **Theo thời gian:** dùng ngày hoặc thời điểm phát sinh dữ liệu, phù hợp với dữ liệu tăng liên tục và có vòng đời lưu trữ rõ ràng.
- **Theo khách hàng:** dùng customer ID hoặc tenant ID, phù hợp khi truy vấn thường xuyên giới hạn theo một khách hàng và cần phân phối dữ liệu giữa nhiều partition.
- **Theo miền dữ liệu:** dùng vùng địa lý, đơn vị kinh doanh, loại nghiệp vụ hoặc một miền phân loại ổn định, phù hợp khi truy vấn và vận hành thường chia theo các miền đó.

Không có một khóa phân vùng tốt cho mọi workload. Khóa phải phản ánh cách ứng dụng đọc, ghi, lưu trữ và xóa dữ liệu. Bài học sử dụng cú pháp Oracle Database 19c làm bối cảnh tham chiếu; một số tùy chọn DDL và operation có thể khác theo phiên bản.

## 1. Partition key là gì?

Partitioned table là một bảng logic được chia thành nhiều partition vật lý. Mỗi partition lưu một phần dữ liệu của bảng, nhưng ứng dụng vẫn truy vấn bảng theo tên bảng thông thường.

Ví dụ bảng giao dịch:

~~~sql
CREATE TABLE sales (
    sale_id      NUMBER(12) NOT NULL,
    sale_date    DATE NOT NULL,
    customer_id  NUMBER(12) NOT NULL,
    region_code  VARCHAR2(20),
    amount       NUMBER(14,2) NOT NULL
);
~~~

Nếu partition theo SALE_DATE, Oracle dùng giá trị ngày để xác định partition chứa hàng. Nếu partition theo CUSTOMER_ID, giá trị khách hàng quyết định partition. Nếu partition theo REGION_CODE, mã miền dữ liệu quyết định partition.

Partition key có thể gồm một hoặc nhiều cột. Kiểu partitioning quyết định cách Oracle diễn giải giá trị khóa:

| Kiểu | Cách chia |
|---|---|
| RANGE | Theo các khoảng giá trị có biên |
| LIST | Theo danh sách giá trị hoặc nhóm giá trị được khai báo |
| HASH | Dùng hàm băm để phân phối giá trị khóa |
| COMPOSITE | Kết hợp hai tầng, ví dụ RANGE-HASH hoặc RANGE-LIST |

### 1.1 Partitioning là tổ chức lưu trữ vật lý

Partition key không phải một bộ lọc tự động của ứng dụng. Một truy vấn có điều kiện phù hợp với partition key có thể cho phép Oracle bỏ qua partition không liên quan (*partition pruning*).

Ví dụ bảng partition theo tháng:

~~~sql
SELECT SUM(amount)
FROM sales
WHERE sale_date >= DATE '2026-03-01'
  AND sale_date <  DATE '2026-04-01';
~~~

Oracle có thể chỉ đọc partition tháng 3/2026 thay vì quét mọi partition. Nhưng nếu truy vấn chỉ lọc CUSTOMER_ID mà không có điều kiện SALE_DATE, Oracle có thể phải đọc nhiều hoặc tất cả partition thời gian.

### 1.2 Partition key phải xuất phát từ workload

Trước khi chọn khóa, hãy trả lời:

1. Truy vấn thường lọc theo cột nào?
2. Dữ liệu tăng theo chiều nào: thời gian, khách hàng, khu vực hay loại nghiệp vụ?
3. Có cần xóa hoặc lưu trữ dữ liệu cũ theo kỳ không?
4. Phân bố dữ liệu có đều giữa các giá trị khóa không?
5. Một partition dự kiến có bao nhiêu hàng và bao nhiêu GB?
6. Có nhiều session cùng ghi vào một partition không?
7. Các JOIN lớn có thể căn chỉnh partition key hay không?
8. Khóa có ổn định trong suốt vòng đời của hàng không?

Chọn khóa chỉ vì cột có nhiều giá trị khác nhau hoặc vì một truy vấn đơn lẻ thường dẫn tới thiết kế khó vận hành.

## 2. Chọn partition key theo thời gian

Partition theo thời gian rất phổ biến với bảng giao dịch, sự kiện, log, hóa đơn, lịch sử đo đạc và dữ liệu phát sinh liên tục.

Các cột thường dùng:

- ORDER_DATE.
- SALE_DATE.
- CREATED_AT.
- EVENT_TIMESTAMP.
- BUSINESS_DATE.

### 2.1 Vì sao thời gian thường là partition key tốt?

Partition theo thời gian phù hợp khi:

- Truy vấn thường giới hạn khoảng ngày/tháng/quý.
- Dữ liệu mới liên tục được thêm vào.
- Dữ liệu cũ có thể được lưu trữ hoặc xóa theo kỳ.
- Báo cáo thường chạy theo ngày, tháng hoặc năm.
- Có thể quản lý từng kỳ bằng thao tác partition maintenance.

Ví dụ, hệ thống bán hàng giữ dữ liệu nóng 24 tháng. Khi tháng mới bắt đầu, hệ thống tạo partition mới; dữ liệu quá thời hạn có thể được archive rồi drop partition tương ứng theo chính sách lưu trữ.

### 2.2 RANGE partition theo tháng

Ví dụ tạo bảng partition theo tháng:

~~~sql
CREATE TABLE sales_by_month (
    sale_id      NUMBER(12) NOT NULL,
    sale_date    DATE NOT NULL,
    customer_id  NUMBER(12) NOT NULL,
    amount       NUMBER(14,2) NOT NULL
)
PARTITION BY RANGE (sale_date) (
    PARTITION p_before_2026
        VALUES LESS THAN (DATE '2026-01-01'),
    PARTITION p2026_01
        VALUES LESS THAN (DATE '2026-02-01'),
    PARTITION p2026_02
        VALUES LESS THAN (DATE '2026-03-01'),
    PARTITION p2026_03
        VALUES LESS THAN (DATE '2026-04-01'),
    PARTITION p_future
        VALUES LESS THAN (MAXVALUE)
);
~~~

RANGE partition dùng biên trên dạng exclusive. Partition P2026_01 chứa các giá trị từ biên dưới của nó (sau partition trước) tới trước ngày 1/2/2026. Với DATE, giá trị có cả phần giờ, nên điều kiện báo cáo theo tháng thường nên dùng khoảng nửa mở:

~~~sql
WHERE sale_date >= DATE '2026-03-01'
  AND sale_date <  DATE '2026-04-01'
~~~

Không nên dùng:

~~~sql
WHERE TRUNC(sale_date, 'MM') = DATE '2026-03-01'
~~~

nếu mục tiêu là lọc partition theo cột SALE_DATE thông thường. Hàm bọc quanh partition key có thể khiến việc pruning khó hơn hoặc yêu cầu biến đổi khác. Khoảng nửa mở vừa bao phủ mọi thời điểm trong tháng, vừa tránh phụ thuộc vào giá trị 23:59:59 ở ngày cuối.

### 2.3 INTERVAL partitioning cho dữ liệu tăng theo thời gian

Nếu dữ liệu liên tục phát sinh ở các kỳ tương lai, INTERVAL partitioning giúp Oracle tự tạo partition khi cần:

~~~sql
CREATE TABLE sales_interval (
    sale_id      NUMBER(12) NOT NULL,
    sale_date    DATE NOT NULL,
    customer_id  NUMBER(12) NOT NULL,
    amount       NUMBER(14,2) NOT NULL
)
PARTITION BY RANGE (sale_date)
INTERVAL (NUMTOYMINTERVAL(1, 'MONTH')) (
    PARTITION p_before_2026
        VALUES LESS THAN (DATE '2026-01-01')
);
~~~

Partition đầu tiên xác định mốc chuyển tiếp. Khi insert dữ liệu vượt mốc này, Oracle có thể tạo các interval partition tương ứng với khoảng tháng. Tên partition do Oracle tạo có thể là tên hệ thống; nếu vận hành cần tên dễ đọc, hãy kiểm tra cách quản lý metadata và chiến lược đặt tên phù hợp.

INTERVAL không thay thế việc giám sát dung lượng, thống kê, index và chính sách retention. Cần kiểm tra partition mới có được tạo đúng theo kỳ và storage attributes mong muốn hay không.

### 2.4 Chọn granularity: ngày, tháng, quý hay năm?

| Granularity | Phù hợp khi | Rủi ro |
|---|---|---|
| Ngày | Dữ liệu rất lớn, truy vấn và retention theo ngày | Số partition tăng nhanh |
| Tháng | Workload báo cáo và retention theo tháng | Một tháng có thể quá lớn với hệ thống rất lớn |
| Quý | Dữ liệu vừa phải, báo cáo theo quý | Truy vấn một tháng phải đọc một partition lớn hơn |
| Năm | Dữ liệu không quá lớn, retention dài | Ít khả năng pruning cho truy vấn ngắn và maintenance kém chi tiết |

Không có số lượng partition tối ưu chung. Chọn granularity dựa trên tổng dung lượng, tốc độ tăng dữ liệu, số partition dự kiến trong nhiều năm, overhead quản lý và khả năng vận hành.

### 2.5 Dữ liệu đến muộn và dữ liệu lịch sử

Hệ thống thời gian thực có thể nhận giao dịch muộn:

- Giao dịch tháng trước đến sau khi partition tháng trước đã được tạo.
- Dữ liệu import lịch sử có ngày cũ.
- Sự kiện có timestamp từ thiết bị không đồng bộ giờ.

Partitioning theo thời điểm phát sinh cần có đường xử lý dữ liệu đến muộn. Có thể cần partition cho lịch sử, partition catch-all phù hợp, hoặc quy trình staging rồi chuyển dữ liệu vào partition đích.

Nếu dùng partition MAXVALUE làm nơi nhận dữ liệu tương lai, khi thêm partition mới cần xử lý split MAXVALUE theo quy trình thích hợp. Với interval partitioning, Oracle tạo partition tương ứng cho các giá trị nằm ngoài transition point.

### 2.6 DATE, TIMESTAMP và múi giờ

Chọn đúng kiểu dữ liệu thời gian:

- DATE lưu ngày và giờ tới giây, không chứa múi giờ.
- TIMESTAMP có phần giây chính xác hơn nhưng không tự mang múi giờ.
- TIMESTAMP WITH TIME ZONE lưu thông tin múi giờ.
- TIMESTAMP WITH LOCAL TIME ZONE được chuẩn hóa theo database time zone và hiển thị theo session time zone.

Nếu dữ liệu đến từ nhiều múi giờ, cần xác định chuẩn lưu trữ, thường là UTC hoặc một quy ước thống nhất, trước khi partition. Tránh để cùng một thời điểm nghiệp vụ rơi vào partition khác nhau chỉ vì session sử dụng múi giờ khác.

### 2.7 Retention và partition maintenance

Partition theo thời gian giúp thao tác theo kỳ:

~~~sql
ALTER TABLE sales_by_month
TRUNCATE PARTITION p2026_01;
~~~

TRUNCATE PARTITION loại bỏ dữ liệu trong partition mà không cần DELETE từng hàng. Nếu kỳ đã hết hạn và không cần giữ cấu trúc partition:

~~~sql
ALTER TABLE sales_by_month
DROP PARTITION p2026_01;
~~~

Các thao tác này là DDL, có ranh giới implicit commit trong Oracle. Chúng không thể được rollback như một DELETE chưa commit. Trước khi chạy cần xác nhận retention, archive, backup/recovery và index maintenance.

## 3. Chọn partition key theo khách hàng

Partition theo CUSTOMER_ID hoặc TENANT_ID phù hợp với hệ thống SaaS, CRM, billing, dữ liệu tài khoản hoặc nền tảng đa khách hàng khi phần lớn truy vấn giới hạn theo một khách hàng.

Ví dụ:

~~~sql
SELECT order_id, order_date, total_amount
FROM orders
WHERE customer_id = :customer_id;
~~~

Nếu bảng partition theo CUSTOMER_ID, Oracle có thể xác định partition liên quan và tránh đọc dữ liệu của khách hàng khác.

### 3.1 HASH partition theo customer_id

Với số khách hàng lớn hoặc liên tục tăng, LIST partition riêng cho từng khách hàng thường không phải lựa chọn tốt. HASH partition phân phối các giá trị khóa qua một số partition cố định:

~~~sql
CREATE TABLE customer_events (
    event_id     NUMBER(14) NOT NULL,
    customer_id  NUMBER(12) NOT NULL,
    event_time   TIMESTAMP NOT NULL,
    event_type   VARCHAR2(30),
    payload      CLOB
)
PARTITION BY HASH (customer_id)
PARTITIONS 32;
~~~

Truy vấn equality theo customer_id có thể được hash pruning tới partition tương ứng:

~~~sql
SELECT event_id, event_time, event_type
FROM customer_events
WHERE customer_id = :customer_id;
~~~

HASH partition phù hợp khi:

- Có rất nhiều customer ID.
- Muốn phân phối khách hàng qua số partition cố định.
- Không cần đặt tên/quản lý partition riêng cho từng khách hàng.
- Truy vấn thường dùng equality hoặc danh sách giá trị khóa.

### 3.2 HASH không chia nhỏ dữ liệu của cùng một khách hàng

Điểm quan trọng: tất cả hàng có cùng CUSTOMER_ID được hash vào cùng partition. HASH phân phối các khách hàng khác nhau giữa các partition; nó không tự chia một khách hàng rất lớn thành nhiều partition.

Nếu một khách hàng tạo 40% tổng số sự kiện, partition chứa khách hàng đó vẫn có thể lớn bất thường. Đây là skew theo khóa. Tăng số partition không làm một customer ID duy nhất tự phân tán qua nhiều partition.

Với khách hàng rất lớn, cần xem xét:

- Thiết kế subpartition theo một khóa khác nếu truy vấn chấp nhận đọc nhiều subpartition.
- Tách workload hoặc dữ liệu của khách hàng đặc biệt theo mô hình riêng.
- Tổng hợp/archiving dữ liệu lịch sử.
- Phân phối theo khóa sự kiện nếu mục tiêu là chia tải ghi, đồng thời chấp nhận truy vấn theo customer có thể phải đọc nhiều partition hơn.

Không thêm một cột vào partition key chỉ để làm partition nhỏ hơn nếu điều đó phá vỡ pruning hoặc yêu cầu quản lý dữ liệu.

### 3.3 RANGE partition theo customer_id

RANGE partition theo ID có thể hữu ích khi ID có miền giá trị rõ và truy vấn thường truy cập các khoảng ID:

~~~sql
CREATE TABLE customer_archive (
    customer_id NUMBER(12) NOT NULL,
    customer_name VARCHAR2(200),
    created_at TIMESTAMP
)
PARTITION BY RANGE (customer_id) (
    PARTITION p_customer_0_99999
        VALUES LESS THAN (100000),
    PARTITION p_customer_100k_199k
        VALUES LESS THAN (200000),
    PARTITION p_customer_200k_299k
        VALUES LESS THAN (300000),
    PARTITION p_customer_other
        VALUES LESS THAN (MAXVALUE)
);
~~~

Điều này phù hợp hơn với truy vấn theo dải ID hoặc quản lý nhóm ID. Tuy nhiên, ID tăng tuần tự có thể làm mọi INSERT mới dồn vào partition cuối, tạo điểm nóng ghi. RANGE theo customer ID cũng không bảo đảm mỗi partition có số hàng bằng nhau vì mỗi khách hàng có thể phát sinh số lượng dữ liệu khác nhau.

### 3.4 LIST partition cho một số tenant lớn

LIST partition có thể hợp lý nếu có một số ít tenant lớn, ổn định và cần quản lý riêng:

~~~sql
CREATE TABLE tenant_transactions (
    transaction_id NUMBER(14) NOT NULL,
    tenant_code    VARCHAR2(30) NOT NULL,
    created_at     TIMESTAMP NOT NULL,
    amount         NUMBER(14,2)
)
PARTITION BY LIST (tenant_code) (
    PARTITION p_tenant_a VALUES ('TENANT_A'),
    PARTITION p_tenant_b VALUES ('TENANT_B'),
    PARTITION p_other VALUES (DEFAULT)
);
~~~

LIST phù hợp với tập giá trị phân loại có quy mô kiểm soát được. Nếu có hàng chục nghìn hoặc hàng triệu tenant, tạo một partition cho mỗi tenant sẽ làm metadata, DDL, index và vận hành phức tạp.

### 3.5 Partition theo khách hàng và bảo mật tenant

Partitioning không thay thế kiểm soát truy cập dữ liệu:

- Điều kiện TENANT_ID trong SQL vẫn phải được kiểm tra.
- Có thể cần Virtual Private Database (VPD), row-level security hoặc cơ chế phân quyền ứng dụng phù hợp.
- Không coi việc mỗi tenant nằm trong partition riêng là ranh giới bảo mật.
- Cần tránh SQL injection hoặc việc client tự sửa tenant ID để đọc dữ liệu tenant khác.

Partition pruning là tối ưu lưu trữ/truy cập, không phải authorization.

## 4. Chọn partition key theo miền dữ liệu

Miền dữ liệu có thể là:

- REGION_CODE hoặc COUNTRY_CODE.
- BUSINESS_UNIT.
- PRODUCT_CATEGORY.
- TRANSACTION_TYPE.
- SOURCE_SYSTEM.
- Một nhóm dữ liệu nghiệp vụ ổn định.

Nếu ứng dụng thường truy vấn theo miền và mỗi miền có khối lượng đủ lớn, LIST partition có thể giúp tổ chức dữ liệu rõ ràng.

### 4.1 LIST partition theo vùng

~~~sql
CREATE TABLE regional_sales (
    sale_id      NUMBER(12) NOT NULL,
    region_code  VARCHAR2(20) NOT NULL,
    sale_date    DATE NOT NULL,
    amount       NUMBER(14,2) NOT NULL
)
PARTITION BY LIST (region_code) (
    PARTITION p_north VALUES ('NORTH'),
    PARTITION p_central VALUES ('CENTRAL'),
    PARTITION p_south VALUES ('SOUTH'),
    PARTITION p_other VALUES (DEFAULT)
);
~~~

Truy vấn:

~~~sql
SELECT SUM(amount)
FROM regional_sales
WHERE region_code = 'SOUTH';
~~~

có thể được pruning tới partition SOUTH.

### 4.2 Chọn miền có giá trị ổn định

Một partition key theo miền dữ liệu nên:

- Có số lượng giá trị hữu hạn hoặc kiểm soát được.
- Ít thay đổi trong vòng đời hàng.
- Có ý nghĩa trong truy vấn hoặc vận hành.
- Có phân bố dữ liệu đủ hợp lý.
- Có quy trình thêm miền mới rõ ràng.

Nếu một hàng đổi REGION_CODE thường xuyên, nó có thể phải chuyển partition. Nếu một miền chứa 90% dữ liệu, partition còn lại rất nhỏ trong khi partition lớn trở thành điểm nóng.

### 4.3 Không nên partition LIST theo trạng thái thay đổi thường xuyên

Ví dụ trạng thái đơn hàng:

~~~text
NEW -> PAID -> SHIPPED -> COMPLETED
~~~

Nếu partition theo STATUS, mỗi lần đổi trạng thái có thể làm hàng chuyển partition. Điều này tạo thêm chi phí DML, index maintenance và row movement; các truy vấn lịch sử theo thời gian cũng có thể không pruning tốt.

Partition theo trạng thái chỉ nên cân nhắc khi trạng thái ổn định, dữ liệu được phân chia rõ theo trạng thái và workload/maintenance thực sự hưởng lợi. Với trạng thái thay đổi thường xuyên, một index phù hợp hoặc partition theo thời gian thường là ứng viên khác cần so sánh.

### 4.4 Miền dữ liệu không đồng nghĩa với phân vùng theo giá trị có cardinality cao

Một số cột như EMAIL, DEVICE_ID, ORDER_ID có hàng triệu giá trị khác nhau. Chia LIST partition theo từng giá trị sẽ tạo quá nhiều partition và không phù hợp để quản lý. Nếu cần phân phối theo khóa có cardinality cao, HASH thường thích hợp hơn; nếu cần truy vấn một giá trị cụ thể, index có thể đã đủ.

## 5. Kết hợp thời gian với khách hàng hoặc miền dữ liệu

Một hệ thống lớn có thể vừa cần pruning theo ngày, vừa cần phân phối dữ liệu theo customer hoặc region. Composite partitioning cho phép chia hai tầng.

### 5.1 RANGE-HASH: thời gian ở tầng ngoài, khách hàng ở tầng trong

~~~sql
CREATE TABLE sales_range_hash (
    sale_id      NUMBER(14) NOT NULL,
    sale_date    DATE NOT NULL,
    customer_id  NUMBER(12) NOT NULL,
    amount       NUMBER(14,2) NOT NULL
)
PARTITION BY RANGE (sale_date)
SUBPARTITION BY HASH (customer_id)
SUBPARTITIONS 8 (
    PARTITION p2026_01
        VALUES LESS THAN (DATE '2026-02-01'),
    PARTITION p2026_02
        VALUES LESS THAN (DATE '2026-03-01'),
    PARTITION p2026_03
        VALUES LESS THAN (DATE '2026-04-01')
);
~~~

Thiết kế này có hai mục tiêu:

- RANGE theo SALE_DATE để pruning theo kỳ và quản lý retention.
- HASH theo CUSTOMER_ID để chia dữ liệu của các khách hàng khác nhau trong từng partition thời gian.

Truy vấn lọc ngày và customer có thể pruning partition thời gian và subpartition hash nếu optimizer xác định được khóa:

~~~sql
SELECT SUM(amount)
FROM sales_range_hash
WHERE sale_date >= DATE '2026-02-01'
  AND sale_date <  DATE '2026-03-01'
  AND customer_id = :customer_id;
~~~

Lưu ý rằng tất cả hàng của cùng một customer trong một tháng vẫn vào cùng hash subpartition của tháng đó. Thiết kế này phân phối nhiều khách hàng trong kỳ, không chia một khách hàng lớn ra nhiều hash subpartition.

### 5.2 RANGE-LIST: thời gian và miền dữ liệu

Nếu báo cáo và retention theo tháng, đồng thời vận hành theo vùng:

~~~sql
CREATE TABLE sales_range_list (
    sale_id      NUMBER(14) NOT NULL,
    sale_date    DATE NOT NULL,
    region_code  VARCHAR2(20) NOT NULL,
    amount       NUMBER(14,2) NOT NULL
)
PARTITION BY RANGE (sale_date)
SUBPARTITION BY LIST (region_code)
SUBPARTITION TEMPLATE (
    SUBPARTITION sp_north VALUES ('NORTH'),
    SUBPARTITION sp_central VALUES ('CENTRAL'),
    SUBPARTITION sp_south VALUES ('SOUTH'),
    SUBPARTITION sp_other VALUES (DEFAULT)
)
(
    PARTITION p2026_01 VALUES LESS THAN (DATE '2026-02-01'),
    PARTITION p2026_02 VALUES LESS THAN (DATE '2026-03-01')
);
~~~

SUBPARTITION TEMPLATE áp dụng cùng cấu trúc miền cho các partition thời gian được tạo theo định nghĩa. Trước khi dùng trong môi trường mục tiêu, kiểm tra cú pháp và hỗ trợ của phiên bản Oracle cụ thể.

### 5.3 Chọn thứ tự hai tầng

Thứ tự partition và subpartition có ý nghĩa vận hành:

- RANGE ngoài, HASH trong: thường thuận lợi khi retention và pruning theo thời gian là ưu tiên chính.
- RANGE ngoài, LIST trong: phù hợp khi cần tổ chức từng miền bên trong mỗi kỳ.
- HASH ngoài, RANGE trong: có thể dùng khi phân phối khách hàng là ưu tiên chính nhưng vẫn cần chia thời gian bên trong mỗi nhóm.

Không chọn thứ tự chỉ dựa trên một câu truy vấn. Xem các truy vấn phổ biến, maintenance, số lượng partition/subpartition và khả năng partition-wise join.

### 5.4 Composite partitioning làm tăng số object

Nếu có 120 partition tháng và mỗi partition có 16 subpartition, bảng có 1.920 subpartition. Cần tính tổng số partition/subpartition qua nhiều năm, số index partition, metadata, thống kê và thời gian bảo trì.

Tăng số lượng phân vùng không miễn phí. Chỉ thêm tầng subpartition khi nó giải quyết một vấn đề cụ thể như phân phối dữ liệu, song song hoặc pruning.

## 6. So sánh ba hướng partition key

| Tiêu chí | Theo thời gian | Theo khách hàng | Theo miền dữ liệu |
|---|---|---|---|
| Kiểu thường dùng | RANGE hoặc INTERVAL | HASH, đôi khi RANGE/LIST | LIST hoặc RANGE |
| Truy vấn hưởng lợi | Khoảng ngày/tháng/quý | Equality theo customer/tenant | Lọc theo region/business unit/type |
| Retention | Rất thuận lợi theo kỳ | Cần chính sách theo khách hàng hoặc archive riêng | Thuận lợi nếu vòng đời theo miền |
| Phân phối dữ liệu | Dữ liệu mới có thể tập trung ở partition mới | HASH phân phối nhiều khóa khách hàng | Phụ thuộc mức cân bằng giữa miền |
| Rủi ro skew | Một kỳ có lượng dữ liệu tăng đột biến | Khách hàng lớn tạo partition nóng | Một miền chiếm đa số dữ liệu |
| Khóa có đổi không? | Ngày nghiệp vụ thường ít đổi nhưng có thể có sửa lịch sử | Customer/tenant ID thường ổn định | Region/status có thể đổi |
| Maintenance | Tạo, archive, drop partition theo kỳ | Thêm/đổi số partition hash thường cần kế hoạch | Thêm giá trị miền và quản lý DEFAULT |
| Truy vấn ngoài khóa | Có thể phải đọc nhiều partition | Có thể phải đọc nhiều partition | Có thể phải đọc nhiều partition |

### 6.1 Một số mô hình workload

| Workload | Thiết kế có thể xem xét |
|---|---|
| Giao dịch bán hàng, báo cáo theo tháng, retention 7 năm | RANGE/INTERVAL theo ngày giao dịch |
| SaaS có hàng triệu tenant nhỏ, truy vấn theo tenant ID | HASH theo tenant ID |
| Một số ít tenant lớn cần quản lý riêng | LIST theo tenant lớn hoặc thiết kế phân tầng |
| Log sự kiện truy vấn theo tháng và customer | RANGE theo thời gian, HASH subpartition theo customer |
| Dữ liệu phân chia theo vùng ổn định, báo cáo theo vùng | LIST theo region |
| Dữ liệu theo miền và cần retention theo tháng | RANGE-LIST |
| ID tăng liên tục, truy vấn theo khoảng ID | RANGE theo ID nếu chấp nhận hotspot ghi và phân bố phù hợp |

Đây là các hướng thiết kế để thử nghiệm, không phải công thức áp dụng tự động.

## 7. Partition pruning và cách partition key tác động truy vấn

Partition pruning là khả năng Oracle bỏ qua partition không cần đọc dựa trên predicate và metadata partition.

### 7.1 Static pruning

Khi giá trị lọc có thể xác định lúc parse/optimization, Oracle có thể xác định partition cần đọc từ sớm.

~~~sql
SELECT COUNT(*)
FROM sales_by_month
WHERE sale_date >= DATE '2026-01-01'
  AND sale_date <  DATE '2026-02-01';
~~~

Với literal ngày và RANGE partition phù hợp, plan có thể chỉ định một partition.

### 7.2 Dynamic pruning

Khi giá trị partition key chỉ được biết trong lúc thực thi, ví dụ qua bind variable, nested-loop join hoặc subquery, Oracle có thể xác định partition cần đọc ở runtime. Plan có thể hiển thị thông tin partition start/stop dạng dynamic tùy operation.

Không nên kết luận dynamic pruning không xảy ra chỉ vì EXPLAIN PLAN không hiển thị một con số partition cố định. Cần xem actual cursor plan và predicate.

### 7.3 Xem PSTART và PSTOP

Ví dụ:

~~~sql
EXPLAIN PLAN FOR
SELECT SUM(amount)
FROM sales_by_month
WHERE sale_date >= DATE '2026-03-01'
  AND sale_date <  DATE '2026-04-01';

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

Trong partitioned plan, chú ý:

- PSTART: partition bắt đầu được truy cập.
- PSTOP: partition cuối cùng được truy cập.
- Một giá trị cụ thể hoặc một dải hẹp thường cho thấy pruning.
- KEY/KEY(I) hoặc ký hiệu dynamic khác có thể cho biết partition được xác định khi chạy.

Ý nghĩa ký hiệu phụ thuộc operation và phiên bản; đọc cùng Predicate Information và actual plan.

### 7.4 Predicate phải tương thích với partition key

Partition theo SALE_DATE:

~~~sql
WHERE sale_date >= :from_date
  AND sale_date <  :to_date
~~~

thường thuận lợi hơn:

~~~sql
WHERE TO_CHAR(sale_date, 'YYYY-MM') = '2026-03'
~~~

Biểu thức thứ hai chuyển cột thành chuỗi, có thể làm mất khả năng pruning đơn giản và phụ thuộc NLS/format. Hãy truyền bind đúng kiểu DATE/TIMESTAMP và lọc bằng khoảng giá trị.

### 7.5 Chỉ lọc cột không phải partition key

Nếu bảng partition theo SALE_DATE nhưng truy vấn chỉ có:

~~~sql
WHERE customer_id = :customer_id
~~~

Oracle có thể phải đọc mọi partition thời gian vì không biết customer nằm ở kỳ nào. Index cục bộ trên CUSTOMER_ID trong mỗi partition hoặc một global index có thể giúp tìm dữ liệu, nhưng partition pruning theo ngày không thể xảy ra khi không có điều kiện thời gian.

Đây là lý do partition key phải phản ánh workload chính, và index là một công cụ bổ sung cho các đường truy cập khác.

## 8. Index trên bảng partitioned

Partitioning ảnh hưởng cách tổ chức index. Oracle có hai nhóm chính:

- **Local index:** mỗi partition của index được căn chỉnh với partition tương ứng của table.
- **Global index:** index bao phủ nhiều hoặc toàn bộ partition của table; có thể là nonpartitioned global index hoặc global partitioned index.

### 8.1 Local index

Ví dụ:

~~~sql
CREATE INDEX ix_sales_local_customer
ON sales_by_month(customer_id)
LOCAL;
~~~

Oracle tạo một index partition cho mỗi table partition. Khi truy vấn đã pruning một partition, Oracle chỉ cần xét phần local index tương ứng.

Ưu điểm:

- Cấu trúc index căn chỉnh với table partition.
- Dễ bảo trì theo partition trong nhiều thao tác lifecycle.
- Có thể giảm phạm vi index cần truy cập khi truy vấn đã pruning table partition.

Điểm cần cân nhắc:

- Nếu truy vấn không có partition key, có thể phải truy cập nhiều local index partition.
- Unique local index phải bao gồm các cột partition key cần thiết để bảo đảm tính duy nhất phù hợp trên phạm vi từng partition.
- Maintenance operation vẫn cần xem trạng thái index và tùy chọn DDL cụ thể.

### 8.2 Global index

Global index có thể tìm khóa trên nhiều partition mà không cần biết trước partition của hàng:

~~~sql
CREATE INDEX ix_sales_global_sale_id
ON sales_by_month(sale_id);
~~~

Nếu SALE_ID unique toàn bảng nhưng không chứa SALE_DATE, một global unique index có thể là cách enforce uniqueness trên toàn bộ partition.

Ưu điểm:

- Hỗ trợ truy vấn theo khóa không phải partition key.
- Có thể enforce uniqueness toàn bảng dù partition key không nằm trong unique key.

Đánh đổi:

- Một số thao tác DROP/TRUNCATE/SPLIT/MERGE partition có thể ảnh hưởng global index.
- Cần dùng tùy chọn maintenance thích hợp hoặc rebuild index khi cần.
- Global index có thể tạo thêm chi phí và ảnh hưởng khả dụng khi partition maintenance.

### 8.3 Unique constraint và partition key

Giả sử bảng partition theo SALE_DATE:

~~~sql
PARTITION BY RANGE (sale_date)
~~~

Muốn đặt unique key chỉ trên SALE_ID:

~~~sql
UNIQUE (sale_id)
~~~

Một local unique index không thể tự bảo đảm SALE_ID duy nhất trên toàn bộ partition nếu SALE_DATE không nằm trong khóa unique. Hai hàng ở hai partition khác nhau có thể có cùng SALE_ID.

Các lựa chọn thiết kế:

1. Đưa partition key vào unique key nếu ngữ nghĩa nghiệp vụ cho phép, ví dụ UNIQUE(SALE_DATE, SALE_ID).
2. Dùng global unique index để enforce SALE_ID duy nhất toàn bảng.
3. Thiết kế một bảng registry/sequence key phù hợp nếu cần một cơ chế định danh toàn cục khác.

Không thay đổi unique key chỉ để thỏa yêu cầu local index nếu điều đó làm yếu đi quy tắc dữ liệu.

### 8.4 Partition maintenance và global index

Khi DROP hoặc TRUNCATE partition, kiểm tra global index có bị đánh dấu UNUSABLE hay không và có cần duy trì index trong cùng DDL không. Một số phiên bản hỗ trợ các tùy chọn như UPDATE INDEXES; cú pháp và hành vi phụ thuộc thao tác, phiên bản và loại index.

Ví dụ minh họa thao tác:

~~~sql
ALTER TABLE sales_by_month
DROP PARTITION p2026_01
UPDATE INDEXES;
~~~

Kiểm tra tài liệu phiên bản Oracle mục tiêu trước khi chạy trên production. Sau maintenance, xác nhận trạng thái index:

~~~sql
SELECT index_name,
       status,
       partitioned
FROM user_indexes
WHERE table_name = 'SALES_BY_MONTH';
~~~

Với local index partition, có thể xem trạng thái từng partition index:

~~~sql
SELECT index_name,
       partition_name,
       status
FROM user_ind_partitions
WHERE index_name LIKE 'IX_SALES%';
~~~

## 9. Partition key và constraint

Partition key có ảnh hưởng đến cách Oracle enforce PRIMARY KEY và UNIQUE constraint.

### 9.1 Primary key không chứa partition key

Nếu khóa chính không chứa partition key, database vẫn cần bảo đảm duy nhất trên toàn bảng. Một local unique index không thể bảo đảm điều đó chỉ bằng cách kiểm tra từng partition riêng lẻ. Oracle có thể cần global index hoặc một thiết kế khóa khác.

### 9.2 Primary key chứa partition key

Nếu nghiệp vụ cho phép khóa ghép:

~~~sql
PRIMARY KEY (sale_date, sale_id)
~~~

và bảng partition theo SALE_DATE, local unique index có thể là một lựa chọn phù hợp vì khóa chứa partition key.

Nhưng điều này thay đổi semantics của khóa: cùng SALE_ID có thể xuất hiện ở hai ngày khác nhau mà vẫn khác composite key. Chỉ dùng khi định danh nghiệp vụ thực sự là cặp ngày và ID.

### 9.3 Foreign key và partitioning

Partitioning không tự làm mất hiệu lực foreign key. Tuy nhiên, thao tác partition maintenance như DROP/TRUNCATE PARTITION có thể tương tác với constraint tham chiếu và cần tùy chọn hoặc quy trình phù hợp.

Trước khi drop partition, phải xác định:

- Partition chứa dữ liệu có hàng con tham chiếu không?
- Có cần archive đồng bộ bảng con không?
- Có dùng reference partitioning không?
- DDL có cần CASCADE hoặc thao tác theo thứ tự không?
- Các constraint và index sau thao tác còn VALID/USABLE không?

Không drop partition chỉ dựa vào ngày dữ liệu nếu chưa kiểm tra quan hệ tham chiếu và chính sách lưu trữ.

## 10. Thay đổi partition key và row movement

Nếu UPDATE partition key làm hàng chuyển từ partition này sang partition khác, Oracle cần thực hiện row movement.

Ví dụ bảng partition theo SALE_DATE:

~~~sql
UPDATE sales_by_month
SET sale_date = DATE '2026-03-15'
WHERE sale_id = 1001;
~~~

Nếu hàng đang ở partition tháng 1 và chuyển sang partition tháng 3, thao tác có thể bị từ chối khi row movement chưa được bật.

Có thể bật:

~~~sql
ALTER TABLE sales_by_month
ENABLE ROW MOVEMENT;
~~~

Khi row movement được bật, Oracle có thể chuyển hàng sang partition đích khi partition key thay đổi. ROWID của hàng có thể thay đổi, vì vậy ứng dụng không nên xem ROWID là định danh nghiệp vụ lâu dài.

### 10.1 Row movement không miễn phí

UPDATE partition key có thể phát sinh:

- Xóa entry cũ và tạo entry mới ở partition đích.
- Duy trì local/global index.
- Ghi redo/undo.
- Ảnh hưởng trigger, foreign key và concurrency theo operation.

Nếu ngày giao dịch thường xuyên bị sửa từ kỳ này sang kỳ khác, partition theo ngày có thể làm tăng chi phí cập nhật. Có thể cần staging/correction table hoặc quy trình điều chỉnh dữ liệu lịch sử.

### 10.2 Tránh partition key thường xuyên thay đổi

Các cột phù hợp làm partition key thường ổn định:

- Ngày nghiệp vụ được xác nhận.
- Tenant ID bất biến.
- Region code ít thay đổi.
- Loại dữ liệu được xác định lúc tạo và hiếm khi đổi.

Các cột như trạng thái xử lý, người phụ trách hiện tại hoặc mức ưu tiên thường thay đổi nhiều; cần cân nhắc kỹ trước khi dùng làm partition key.

## 11. Partition-wise join và khóa phân vùng

Partition-wise join là kỹ thuật Oracle có thể dùng để join các bảng partition tương thích, xử lý các partition tương ứng thay vì phải di chuyển toàn bộ dữ liệu như một tập lớn.

Ví dụ hai bảng cùng partition theo SALE_DATE với ranh giới tương thích:

~~~sql
CREATE TABLE sales_header (
    sale_id   NUMBER,
    sale_date DATE,
    customer_id NUMBER,
    amount NUMBER(14,2)
)
PARTITION BY RANGE (sale_date) (
    PARTITION p2026_01 VALUES LESS THAN (DATE '2026-02-01'),
    PARTITION p2026_02 VALUES LESS THAN (DATE '2026-03-01')
);

CREATE TABLE sales_detail (
    sale_id   NUMBER,
    sale_date DATE,
    line_no   NUMBER,
    product_id NUMBER,
    quantity NUMBER
)
PARTITION BY RANGE (sale_date) (
    PARTITION p2026_01 VALUES LESS THAN (DATE '2026-02-01'),
    PARTITION p2026_02 VALUES LESS THAN (DATE '2026-03-01')
);
~~~

Join có điều kiện theo khóa tương ứng:

~~~sql
SELECT h.sale_date,
       h.sale_id,
       SUM(d.quantity) AS total_quantity
FROM sales_header h
JOIN sales_detail d
  ON d.sale_id = h.sale_id
 AND d.sale_date = h.sale_date
GROUP BY h.sale_date, h.sale_id;
~~~

Nếu partitioning và join key tương thích, Oracle có thể xử lý từng cặp partition tương ứng (*partition-wise join*). Lợi ích có thể gồm giảm trao đổi dữ liệu giữa parallel servers và giới hạn phạm vi xử lý.

### 11.1 Partition-wise join không tự xảy ra chỉ vì hai bảng đều partitioned

Cần các điều kiện tương thích về partition key, kiểu partitioning, partition boundaries hoặc subpartitioning và join predicate. Nếu hai bảng partition theo các khóa không liên quan, Oracle không thể mặc nhiên ghép partition số 1 của bảng A với partition số 1 của bảng B.

Đọc execution plan để xác nhận partition-wise join hoặc các operation parallel tương ứng. Không suy luận chỉ từ DDL.

### 11.2 Reference partitioning

Trong mô hình cha-con, Oracle hỗ trợ reference partitioning dựa trên foreign key được hỗ trợ. Bảng con có thể được partition theo cách tương ứng với partition của bảng cha mà không cần lặp lại một partition key độc lập.

Ví dụ đơn hàng và chi tiết đơn hàng có quan hệ cha-con; reference partitioning có thể giúp dữ liệu chi tiết đi cùng partition của đơn hàng. Đây là thiết kế chuyên biệt, cần kiểm tra yêu cầu khóa ngoại, kiểu partitioning và các giới hạn của phiên bản.

## 12. Partition key, dữ liệu NULL và giá trị ngoài miền

Giá trị NULL và giá trị không nằm trong danh sách/range cần được xử lý rõ.

### 12.1 RANGE partition

RANGE partition phân phối giá trị theo biên. Giá trị NULL có quy tắc so sánh của Oracle và thường nằm ở partition range thấp nhất phù hợp; nếu không có partition bao phủ giá trị, INSERT có thể lỗi vì không tìm được partition.

### 12.2 LIST partition

LIST partition có thể khai báo DEFAULT để nhận các giá trị không thuộc partition được liệt kê:

~~~sql
PARTITION p_other VALUES (DEFAULT)
~~~

Nếu không có DEFAULT và giá trị không khớp partition nào, INSERT có thể nhận lỗi không tìm thấy partition. DEFAULT giúp tiếp nhận miền mới nhưng cũng có thể che giấu dữ liệu sai chính tả hoặc mã miền chưa được phê duyệt; cần theo dõi số hàng trong partition DEFAULT.

### 12.3 HASH partition

HASH partition dùng hàm băm để định tuyến giá trị khóa. Với khóa NULL hoặc giá trị cụ thể, Oracle vẫn xác định partition theo quy tắc hash. HASH không tạo vùng giá trị có thể đọc theo khoảng như RANGE.

### 12.4 Kiểm soát dữ liệu đầu vào

Nếu SALE_DATE là bắt buộc, khai báo NOT NULL. Nếu REGION_CODE phải thuộc danh sách miền hợp lệ, dùng foreign key hoặc constraint phù hợp. Partitioning không thay thế validation dữ liệu.

## 13. Skew, hotspot và phân phối dữ liệu

Một thiết kế có số partition đẹp trên giấy vẫn có thể mất cân bằng trong thực tế.

### 13.1 Skew theo thời gian

Một số kỳ có chiến dịch bán hàng lớn, cuối năm hoặc sự kiện đặc biệt. Partition tháng đó có thể lớn gấp nhiều lần các tháng khác.

Giải pháp có thể cân nhắc:

- Granularity nhỏ hơn cho giai đoạn cao điểm.
- Composite partitioning.
- Subpartition theo customer hoặc region.
- Phân bổ storage và parallel workload phù hợp.

Không cần thiết chia nhỏ mọi tháng nếu chỉ một số kỳ đặc biệt có khối lượng cao; hãy cân nhắc chi phí vận hành.

### 13.2 Skew theo khách hàng

HASH(customer_id) phân phối các customer khác nhau, nhưng một customer có lượng dữ liệu rất lớn vẫn tập trung vào một hash partition. Hãy đo số hàng và dung lượng theo customer:

~~~sql
SELECT customer_id,
       COUNT(*) AS row_count,
       SUM(DBMS_LOB.GETLENGTH(payload)) AS payload_bytes
FROM customer_events
GROUP BY customer_id
ORDER BY row_count DESC
FETCH FIRST 20 ROWS ONLY;
~~~

Ví dụ trên giả định PAYLOAD là CLOB và cần đo dung lượng nội dung; với kiểu dữ liệu khác, thay phép tính phù hợp. Truy vấn thống kê có thể tốn tài nguyên trên bảng lớn, nên chạy theo kế hoạch và phạm vi được kiểm soát.

### 13.3 Skew theo miền

Nếu vùng SOUTH chứa 80% dữ liệu, LIST partition theo REGION_CODE tạo một partition lớn và hai partition nhỏ. Pruning vẫn có ích cho truy vấn theo vùng, nhưng partition lớn có thể gây tải không đều.

Có thể kết hợp RANGE thời gian với LIST vùng, hoặc HASH subpartition bên trong miền, nếu workload thực sự cần. Cũng cần cân nhắc việc một vùng có thể thay đổi mã hoặc tách địa giới.

### 13.4 Hot partition do ghi

RANGE theo timestamp tăng liên tục thường khiến mọi INSERT mới đi vào partition cuối hiện tại. Đây là hành vi có thể dự đoán và thường phù hợp với lifecycle, nhưng nếu tốc độ ghi rất cao, cần xem contention ở index, block, sequence, segment và parallel insert.

HASH subpartition có thể giúp phân tán một số workload ghi bên trong kỳ, nhưng hiệu quả phụ thuộc khóa subpartition và cách ghi. Hash theo customer vẫn gom một khách hàng vào một subpartition; chọn khóa khác có thể phân phối tốt hơn nhưng làm truy vấn customer kém pruning hơn.

## 14. Quản lý số lượng partition

Partition quá ít có thể làm mỗi partition quá lớn, giảm hiệu quả pruning và maintenance. Partition quá nhiều làm tăng metadata, số index partition, thống kê, thời gian parse/maintenance và độ phức tạp vận hành.

Hãy ước lượng:

- Số partition hiện tại.
- Số partition sau 1, 3, 5 hoặc 10 năm.
- Số subpartition trên mỗi partition.
- Số index partition tương ứng.
- Tần suất tạo, split, merge, exchange, drop partition.
- Số partition truy vấn thường phải mở.

Ví dụ, partition theo ngày trong 10 năm tạo hơn 3.600 partition. Nếu mỗi partition còn 16 subpartition, số subpartition vượt 58.000. Đây có thể là lựa chọn hợp lý với một workload đặc biệt lớn nhưng cần đánh giá kỹ metadata và vận hành.

## 15. Thống kê và optimizer trên bảng partitioned

Optimizer cần thống kê ở cấp bảng, partition và index để ước lượng cardinality/cost. Khi dữ liệu tăng hoặc partition mới được tạo, statistics có thể cần được thu thập theo chiến lược phù hợp.

Các khái niệm:

- Global table statistics mô tả toàn bảng.
- Partition-level statistics mô tả từng partition.
- Subpartition statistics mô tả tầng con nếu có.
- Local index statistics tương ứng với index partition.
- Global index statistics mô tả index toàn cục.

Nếu một partition mới có phân bố khác biệt, global stats cũ có thể khiến optimizer ước lượng sai. Hãy theo dõi stats sau partition maintenance và load lớn.

### 15.1 Kiểm tra partition metadata

~~~sql
SELECT partition_name,
       partition_position,
       high_value,
       num_rows,
       blocks,
       last_analyzed
FROM user_tab_partitions
WHERE table_name = 'SALES_BY_MONTH'
ORDER BY partition_position;
~~~

HIGH_VALUE được lưu dưới dạng metadata expression và có thể hiển thị kiểu LONG ở một số view; không phải mọi công cụ có thể lọc/format trực tiếp trường này như VARCHAR2 thông thường. Truy vấn trên dùng để minh họa các trường metadata cơ bản.

### 15.2 Thu thập statistics

Ví dụ minh họa:

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname          => USER,
        tabname          => 'SALES_BY_MONTH',
        estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE,
        method_opt       => 'FOR ALL COLUMNS SIZE AUTO',
        cascade          => TRUE,
        granularity      => 'AUTO'
    );
END;
/
~~~

DBMS_STATS có nhiều tùy chọn và chính sách incremental statistics. Hãy dùng chính sách của DBA, đặc biệt với bảng lớn, partition mới và global statistics. Không chạy gather stats tùy tiện trên production chỉ để thử một plan.

## 16. Thiết kế partition key và index cho các truy vấn điển hình

Giả sử truy vấn chính là:

~~~sql
SELECT customer_id,
       SUM(amount)
FROM sales
WHERE sale_date >= :from_date
  AND sale_date <  :to_date
  AND customer_id = :customer_id
GROUP BY customer_id;
~~~

Thiết kế có thể xem xét:

- RANGE/INTERVAL theo SALE_DATE để pruning theo kỳ.
- HASH subpartition theo CUSTOMER_ID để phân phối customer trong từng kỳ.
- Local index theo CUSTOMER_ID nếu truy vấn và dữ liệu chứng minh có lợi.
- Local/global index khác cho khóa định danh theo yêu cầu uniqueness.

Nhưng nếu truy vấn chủ yếu là:

~~~sql
SELECT *
FROM sales
WHERE sale_id = :sale_id;
~~~

thì partition theo thời gian không giúp pruning nếu không biết SALE_DATE. Global index trên SALE_ID có thể là lựa chọn, hoặc ứng dụng phải lưu thêm thông tin partition key khi truy vấn.

### 16.1 Không lặp index giống partition key một cách máy móc

Nếu partition theo RANGE(SALE_DATE), local index chỉ trên SALE_DATE có thể ít giá trị với truy vấn đã pruning và range scan trực tiếp trên partition. Index vẫn có thể hữu ích trong một số truy vấn, nhưng cần xem access pattern.

Một index trên (CUSTOMER_ID, SALE_DATE) có thể phục vụ customer lookup bên trong partition; global index trên SALE_ID có thể phục vụ lookup toàn cục. Mỗi index tăng chi phí DML và storage, nên phải có lý do.

## 17. Quy trình chọn partition key

~~~mermaid
flowchart TD
    A["Thu thập workload truy vấn và DML"] --> B["Xác định predicate lọc phổ biến"]
    B --> C{"Truy vấn và retention theo thời gian?"}
    C -->|Có| D["Đánh giá RANGE / INTERVAL theo ngày"]
    C -->|Không| E{"Equality theo customer hoặc tenant?"}
    E -->|Có| F["Đánh giá HASH hoặc LIST theo quy mô tenant"]
    E -->|Không| G{"Miền dữ liệu hữu hạn và ổn định?"}
    G -->|Có| H["Đánh giá LIST / RANGE theo miền"]
    G -->|Không| I["Cân nhắc không partition hoặc thiết kế khác"]
    D --> J["Đo phân bố và skew"]
    F --> J
    H --> J
    I --> K["Kiểm tra index, constraint và maintenance"]
    J --> K
    K --> L["Benchmark bằng actual execution plan"]
    L --> M["Chốt thiết kế và quy trình vận hành"]
~~~

Các bước cụ thể:

1. Thu thập truy vấn thực tế, tần suất, số hàng và thời gian chạy.
2. Xác định cột lọc, join, group by và sort phổ biến.
3. Xác định nhu cầu retention/archive/delete.
4. Đo phân bố số hàng theo từng giá trị ứng viên.
5. Chọn RANGE, LIST, HASH hoặc composite theo workload.
6. Xác định local/global index và yêu cầu unique constraint.
7. Kiểm tra row movement và thay đổi khóa.
8. Thiết kế DDL maintenance, stats, backup và recovery.
9. Benchmark trên dữ liệu có phân bố gần production.
10. Kiểm tra pruning và actual plan sau triển khai.

## 18. Những lỗi thiết kế thường gặp

| Lựa chọn sai | Hệ quả | Cách suy nghĩ lại |
|---|---|---|
| Partition theo cột không xuất hiện trong predicate | Truy vấn phải đọc nhiều partition | Chọn khóa theo workload thực tế |
| Partition theo customer bằng LIST cho hàng triệu tenant | Quá nhiều partition và metadata | Dùng HASH hoặc mô hình khác |
| HASH(customer_id) nhưng một customer chiếm phần lớn dữ liệu | Một partition vẫn rất lớn | Đo skew theo từng customer, cân nhắc chiến lược riêng |
| RANGE theo ID tăng liên tục | INSERT dồn vào partition cuối | Xem hotspot và workload ghi |
| LIST theo STATUS thay đổi thường xuyên | Row movement và maintenance tăng | Chọn khóa ổn định hơn |
| Partition theo thời gian nhưng truy vấn chỉ theo ID | Không pruning theo ngày | Index/global access path hoặc bổ sung điều kiện partition key |
| Chọn partition ngày cho dữ liệu nhỏ | Số partition tăng nhanh | Chọn granularity tháng/quý nếu phù hợp |
| Tạo quá nhiều subpartition | Metadata và maintenance phức tạp | Chỉ thêm tầng khi có lợi ích đo được |
| Dùng TRUNC(date_col) trong predicate | Có thể giảm khả năng pruning | Dùng khoảng ngày nửa mở |
| Quên global index khi drop partition | Index có thể unusable hoặc cần bảo trì | Lập kế hoạch index maintenance |
| Unique key không chứa partition key nhưng chỉ tạo local unique index | Không bảo đảm uniqueness toàn bảng | Dùng global unique index hoặc thiết kế khóa đúng nghiệp vụ |
| Bật row movement mà không xét ROWID | Ứng dụng có thể giữ ROWID cũ | Dùng khóa nghiệp vụ ổn định |
| Coi partition là ranh giới bảo mật | Có thể truy cập chéo tenant | Dùng authorization/row-level security |
| Tin rằng partitioning luôn làm truy vấn nhanh | Có thể tăng chi phí khi pruning không xảy ra | Đo actual plan và workload |

## 19. Bài thực hành tự kiểm tra

Các bài thực hành dùng schema thử nghiệm. Không chạy DDL destructive trên bảng production.

### Bài 1 — RANGE theo tháng

Tạo bảng partition theo SALE_DATE với ba partition tháng. Insert hàng ở mỗi tháng và truy vấn một tháng bằng khoảng nửa mở. Xem PSTART/PSTOP trong DBMS_XPLAN.

### Bài 2 — INTERVAL partition

Tạo bảng INTERVAL theo tháng với transition point. Insert một hàng ở kỳ tương lai. Xem USER_TAB_PARTITIONS để xác nhận partition được tạo.

### Bài 3 — HASH theo customer

Tạo bảng HASH partition 16 hoặc 32 partition theo CUSTOMER_ID. Insert dữ liệu cho nhiều customer. Truy vấn equality theo một customer và kiểm tra partition pruning.

### Bài 4 — Đo skew

Tạo một customer có lượng dữ liệu lớn hơn nhiều customer khác. Thống kê số hàng theo customer và giải thích vì sao HASH(customer_id) vẫn có một partition lớn.

### Bài 5 — LIST theo region

Tạo LIST partition cho NORTH, CENTRAL, SOUTH và DEFAULT. Insert mã vùng đã biết và mã mới. Kiểm tra partition nhận dữ liệu, sau đó đề xuất quy trình kiểm soát DEFAULT.

### Bài 6 — RANGE-HASH

Tạo bảng partition theo tháng và subpartition HASH theo customer. So sánh truy vấn chỉ có ngày với truy vấn có cả ngày và customer. Xem partition/subpartition pruning.

### Bài 7 — Row movement

Tạo bảng RANGE theo ngày. Insert một hàng ở tháng 1 rồi thử UPDATE SALE_DATE sang tháng 2 khi row movement tắt. Bật row movement trong schema thử nghiệm, chạy lại và quan sát kết quả.

### Bài 8 — Local và global index

Tạo local index trên CUSTOMER_ID và global index trên SALE_ID. So sánh truy vấn theo customer có điều kiện ngày với truy vấn theo sale ID không có ngày. Ghi nhận access path.

### Bài 9 — Unique constraint

Tạo bảng partition theo ngày và thử unique key chỉ trên SALE_ID. Tìm hiểu vì sao local unique index cần chứa partition key, rồi so sánh với global unique index.

### Bài 10 — Retention

Trong bảng thử nghiệm, archive dữ liệu một partition rồi DROP hoặc TRUNCATE partition. Kiểm tra index status, constraint và dữ liệu còn lại. Ghi rõ DDL có implicit commit và không rollback được như DML.

### Bài 11 — Partition-wise join

Tạo hai bảng cùng RANGE partition theo ngày với ranh giới giống nhau. Join trên các khóa phù hợp. Xem plan và xác định Oracle có sử dụng partition-wise join hay không.

### Bài 12 — So sánh với bảng không partition

Nạp cùng dữ liệu vào bảng thường và bảng partitioned. Chạy một truy vấn lọc ngày hẹp và một truy vấn không lọc ngày. So sánh plan, partition pruning, buffers, reads và thời gian. Không chỉ so sánh cost trong EXPLAIN PLAN.

## 20. Checklist trước khi triển khai partition key

**Workload**

- Các truy vấn quan trọng có predicate trên partition key không?
- Tần suất truy vấn theo thời gian, customer và miền dữ liệu là bao nhiêu?
- Có join key nào cần căn chỉnh partition không?
- Có truy vấn phải tìm dữ liệu mà không biết partition key không?

**Phân bố dữ liệu**

- Số hàng và dung lượng dự kiến mỗi partition?
- Partition lớn nhất so với trung bình?
- Có một customer/region chiếm phần lớn dữ liệu không?
- INSERT có dồn vào một partition hoặc subpartition không?

**Vòng đời**

- Dữ liệu giữ bao lâu?
- Có archive trước khi drop không?
- Dữ liệu đến muộn được xử lý ra sao?
- Ai tạo partition mới và giám sát partition tương lai?

**Index và constraint**

- Index nào local, index nào global?
- Unique key có chứa partition key không?
- Partition maintenance ảnh hưởng global index ra sao?
- Có foreign key hoặc bảng con cần xử lý cùng lúc không?

**Ứng dụng**

- Có UPDATE partition key không?
- Có cần ENABLE ROW MOVEMENT không?
- Ứng dụng có giữ ROWID lâu dài không?
- Tenant security được bảo vệ bằng cơ chế nào ngoài partitioning?

**Kiểm chứng**

- Actual plan có partition pruning không?
- PSTART/PSTOP có đúng kỳ vọng?
- E-Rows và A-Rows có chênh lệch lớn không?
- Có benchmark truy vấn theo và ngoài partition key không?
- Có kiểm tra DML throughput và partition maintenance không?

## 21. Ghi nhớ

| Hướng chọn khóa | Khi phù hợp | Điều phải kiểm tra |
|---|---|---|
| Thời gian | Truy vấn theo kỳ, dữ liệu tăng liên tục, retention theo thời gian | Granularity, dữ liệu đến muộn, interval, timezone, partition cuối |
| Khách hàng/tenant | Truy vấn equality theo tenant, cần phân phối nhiều khách hàng | HASH phân phối customer nhưng không chia một customer lớn |
| Miền dữ liệu | Giá trị miền hữu hạn, ổn định, truy vấn/maintenance theo miền | Skew, giá trị mới, DEFAULT và row movement |
| RANGE-HASH | Pruning theo thời gian và phân phối theo customer | Số subpartition, skew theo customer, partition-wise access |
| RANGE-LIST | Retention theo kỳ và vận hành theo miền | Số miền, DEFAULT, số lượng subpartition |

Partition key tốt giúp Oracle bỏ qua dữ liệu không liên quan, giúp đội vận hành quản lý dữ liệu theo vòng đời và giữ phân bố tài nguyên hợp lý. Hãy chọn khóa từ các truy vấn và quy trình thực tế, đo skew trước khi quyết định, và thiết kế index/constraint cùng với partitioning. RANGE theo thời gian, HASH theo khách hàng và LIST theo miền là những mẫu thường gặp, nhưng chỉ có execution plan, số liệu runtime và thử nghiệm trên dữ liệu đại diện mới xác nhận được thiết kế có phù hợp hay không.
