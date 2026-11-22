# Mục tiêu phân vùng và điều kiện phiên bản/edition/giấy phép trong Oracle

Một bảng giao dịch có thể tăng từ vài triệu lên hàng tỷ hàng. Khi dữ liệu lớn dần, các câu hỏi không chỉ còn là “truy vấn có dùng index không?” mà còn là: làm sao loại bỏ nhanh những vùng dữ liệu không liên quan, lưu dữ liệu theo vòng đời, xóa dữ liệu cũ mà không chạy DELETE khổng lồ, bảo trì từng phần của bảng và giữ thời gian phục hồi trong giới hạn vận hành? **Table partitioning** của Oracle chia một bảng logic thành nhiều partition vật lý theo một hoặc nhiều khóa phân vùng. Ứng dụng vẫn truy vấn một bảng, còn Oracle có thể làm việc trên những partition cần thiết.

Phân vùng phục vụ nhiều mục tiêu: quản lý vòng đời dữ liệu, partition pruning, bảo trì theo từng phần, hỗ trợ partition-wise joins và một số chiến lược song song. Tuy nhiên, phân vùng không tự động làm mọi truy vấn nhanh hơn. Hiệu quả phụ thuộc partition key, cách truy vấn lọc dữ liệu, số lượng và kích thước partition, index, thống kê và execution plan.

Ngoài thiết kế kỹ thuật, partitioning còn có điều kiện **phiên bản, edition và giấy phép**. Việc một database có thể nhận cú pháp hoặc hiển thị tính năng trong data dictionary không chứng minh tổ chức đã có quyền sử dụng tính năng đó. Đặc biệt, trong Oracle Database 19c, Partitioning là option cần được cấp phép riêng cho Enterprise Edition; Standard Edition 2 không cung cấp option này. Các dịch vụ cloud và hợp đồng khác có thể có điều khoản đóng gói khác, vì vậy phải xác nhận đúng sản phẩm, release, edition, dịch vụ, metric và hợp đồng đang sử dụng.

Bài học thuộc nhóm **Phân vùng** của Database Engine Relational Oracle. Nội dung đi từ mục tiêu phân vùng, các phương pháp phân vùng và cách thiết kế khóa, đến pruning, index, bảo trì partition, điều kiện release/edition/licensing và quy trình kiểm tra trước khi triển khai.

Sau bài này, bạn có thể:

- Giải thích vì sao một bảng lớn cần được phân vùng và khi nào không nên phân vùng.
- Phân biệt partitioning với indexing, sharding và việc chia bảng thành nhiều bảng thủ công.
- Chọn RANGE, INTERVAL, LIST, HASH hoặc composite partitioning theo phân bố dữ liệu và workload.
- Thiết kế partition key để hỗ trợ partition pruning và vòng đời dữ liệu.
- Hiểu local index, global index và tác động của partition maintenance.
- Dùng EXPLAIN PLAN/DBMS_XPLAN để xác nhận partition pruning.
- Quản lý partition bằng ADD, DROP, TRUNCATE, EXCHANGE, SPLIT, MERGE và các thao tác phù hợp.
- Nhận diện các điều kiện phụ thuộc phiên bản, COMPATIBLE và edition.
- Phân biệt khả năng kỹ thuật, feature usage và quyền sử dụng theo giấy phép.
- Lập checklist xác minh hợp đồng/giấy phép trước khi bật partitioning ở môi trường thật.

> **Phạm vi phiên bản:** Ví dụ DDL dùng cú pháp Oracle Database 19c. Các kiểu partitioning, giới hạn, thao tác online, khả năng tự động và điều kiện cấp phép có thể thay đổi theo release, edition, dịch vụ cloud và hợp đồng. Hãy đối chiếu tài liệu Licensing Information User Manual của đúng phiên bản và điều khoản đặt mua của tổ chức trước khi triển khai.

## 1. Partitioning là gì?

Partitioning chia một bảng lớn thành nhiều phần nhỏ gọi là partition dựa trên giá trị của partition key. Mỗi partition là một phần của cùng một bảng logic, có thể được quản lý như một đơn vị riêng trong nhiều thao tác.

~~~text
APPLICATION
    |
    | SELECT ... FROM SALES
    v
LOGICAL TABLE: SALES
    |
    +-- PARTITION P2026_01
    +-- PARTITION P2026_02
    +-- PARTITION P2026_03
    +-- PARTITION P2026_04
    +-- PARTITION P2026_05
    +-- PARTITION P2026_06
~~~

Ứng dụng vẫn viết:

~~~sql
SELECT SUM(amount)
FROM sales
WHERE sale_date >= DATE '2026-03-01'
  AND sale_date <  DATE '2026-04-01';
~~~

Thông thường không cần chỉ rõ tên partition. Optimizer có thể xác định partition nào có thể chứa dữ liệu phù hợp và chỉ truy cập phần cần thiết.

### 1.1. Partition là đơn vị quản lý bên trong một bảng logic

Một partition không phải là một bảng độc lập mà ứng dụng phải UNION thủ công. Bảng partitioned vẫn có:

- Một tên bảng và một định nghĩa cột.
- Một mô hình SQL chung cho truy vấn/DML.
- Constraint và metadata ở cấp bảng, cùng một số metadata ở cấp partition.
- Các partition/subpartition được quản lý bởi database.

Oracle lưu dữ liệu của các partition trong các segment tương ứng khi segment được cấp phát. Cấu trúc vật lý cụ thể phụ thuộc tablespace, segment creation và loại partition.

### 1.2. Partitioning khác indexing

| Khái niệm | Mục đích | Phạm vi |
| --- | --- | --- |
| Index | Tìm hàng theo khóa/biểu thức hiệu quả | Một cấu trúc chỉ mục phụ |
| Partitioning | Chia bảng thành các vùng dữ liệu có thể quản lý riêng | Tổ chức dữ liệu của bảng |
| Subpartitioning | Chia tiếp từng partition theo chiều thứ hai | Cấu trúc phân vùng nhiều cấp |
| Sharding | Phân phối dữ liệu qua nhiều database/shard | Nhiều database hoặc shard |

Partitioning không thay thế index. Một truy vấn có thể dùng partition pruning trước, rồi dùng local index trong các partition còn lại. Một truy vấn khác có thể chỉ quét các partition cần thiết bằng full scan.

### 1.3. Partitioning khác việc tạo nhiều bảng theo tháng

Tự tạo SALES_2026_01, SALES_2026_02, SALES_2026_03 rồi UNION ALL thủ công khiến ứng dụng phải tự quản lý:

- Bảng nào chứa kỳ nào.
- Bảng mới cho kỳ tiếp theo.
- Truy vấn phải ghép bao nhiêu bảng.
- Constraint, quyền, index và thống kê giữa các bảng.
- Các thao tác ghi và truy vấn xuyên kỳ.

Partitioning giữ một giao diện bảng thống nhất và để Oracle quản lý ranh giới partition.

## 2. Mục tiêu chính của partitioning

Partitioning không phải mục tiêu tự thân. Hãy chọn nó khi một hoặc nhiều lợi ích sau có giá trị thực tế.

### 2.1. Quản lý vòng đời dữ liệu

Đây thường là lý do mạnh nhất cho bảng lịch sử lớn. Ví dụ bảng SALES giữ dữ liệu theo tháng:

- Partition hiện tại nhận INSERT.
- Partition các tháng trước chủ yếu đọc.
- Partition cũ hơn thời hạn lưu trữ được archive hoặc drop.
- Một partition có thể được nén/di chuyển theo chính sách storage phù hợp.

Xóa một partition cũ bằng thao tác DDL có thể hiệu quả hơn DELETE hàng triệu dòng, vì không phải tạo undo/redo cho từng hàng theo cách một DML lớn thường làm. Tuy nhiên, DROP/TRUNCATE PARTITION là thao tác DDL, có implicit commit và không thể rollback như DELETE. Phải xác nhận retention policy và backup trước khi thực hiện.

### 2.2. Partition pruning

Partition pruning là khả năng loại bỏ các partition chắc chắn không chứa hàng thỏa predicate. Nếu bảng được phân vùng theo SALE_DATE và truy vấn chỉ lấy tháng 3, Oracle có thể bỏ qua các partition tháng khác.

~~~text
SALES
  P_JAN   [bo qua]
  P_FEB   [bo qua]
  P_MAR   [DOC]
  P_APR   [bo qua]
  P_MAY   [bo qua]
~~~

Pruning giảm số partition/segment cần truy cập. Nó có thể giảm I/O, CPU và thời gian xử lý, đặc biệt với truy vấn có điều kiện phù hợp trên partition key.

### 2.3. Bảo trì theo từng phần

Thay vì bảo trì toàn bộ bảng, DBA có thể thao tác ở cấp partition:

- Truncate partition để làm rỗng một kỳ.
- Drop partition đã hết retention.
- Exchange partition với bảng staging.
- Split hoặc merge partition khi thay đổi ranh giới.
- Move partition sang tablespace khác nếu có kế hoạch storage.
- Gather statistics ở cấp partition khi thích hợp.

Khả năng và tác động của từng thao tác phụ thuộc release, index type, constraint, logging, concurrency và tùy chọn online.

### 2.4. Availability và giảm phạm vi bảo trì

Một số thao tác có thể giới hạn phạm vi ảnh hưởng ở partition cần thay đổi. Điều này giúp tổ chức bảo trì dữ liệu cũ hoặc staging theo từng phần. Nhưng không nên suy ra mọi thao tác partition đều online hoặc không chặn truy vấn/DML. Hãy kiểm tra tùy chọn online được hỗ trợ trong đúng release và đánh giá lock, global index maintenance, undo/redo và thời gian chạy.

### 2.5. Partition-wise joins

Nếu hai bảng được phân vùng tương thích theo join key, Oracle có thể thực hiện partition-wise join: xử lý từng cặp partition tương ứng thay vì phải ghép toàn bộ dữ liệu trên một vùng lớn. Điều này có thể giảm giao tiếp dữ liệu và hỗ trợ parallel execution.

Partition-wise join cần điều kiện phân vùng và join phù hợp. Không phải cứ hai bảng cùng có partition là Oracle tự động dùng partition-wise join.

### 2.6. Parallelism và khả năng mở rộng

Partition có thể tạo đơn vị công việc cho parallel query và parallel DML. Oracle có thể chia công việc theo partition hoặc subpartition. Nhưng parallel execution tiêu thụ CPU, I/O, memory và tài nguyên PX; partition nhiều không có nghĩa hệ thống tự động nhanh hơn.

### 2.7. Quản lý storage và chính sách dữ liệu

Các partition khác nhau có thể được đặt ở tablespace khác nhau để hỗ trợ chính sách lưu trữ, backup/recovery và vòng đời. Ví dụ dữ liệu gần đây ở storage hiệu năng cao, dữ liệu lịch sử ở storage rẻ hơn. Các tính năng nén, ILM và tiering có điều kiện kỹ thuật/giấy phép riêng cần được kiểm tra độc lập.

## 3. Khi nào nên và không nên phân vùng?

### 3.1. Trường hợp đáng cân nhắc

- Bảng rất lớn và truy vấn thường lọc theo một chiều ổn định như ngày, tenant hoặc vùng dữ liệu.
- Dữ liệu có vòng đời rõ, ví dụ giữ 13 tháng rồi archive.
- DBA thường xuyên xóa/nạp/di chuyển dữ liệu theo kỳ.
- Báo cáo đọc một số kỳ cụ thể trong khi bảng lưu nhiều năm.
- Các bảng fact có thể được phân vùng tương thích để partition-wise join.
- Có yêu cầu quản lý backup, storage hoặc maintenance ở cấp vùng dữ liệu.

### 3.2. Trường hợp partitioning có thể không cần thiết

- Bảng nhỏ, truy vấn đọc gần như toàn bộ bảng.
- Workload không lọc theo partition key.
- Dữ liệu ít và không có nhu cầu lifecycle management.
- Số lượng partition làm tăng độ phức tạp nhưng không giảm chi phí truy cập.
- Ứng dụng cần lookup theo khóa không liên quan partition key và global index trở thành điểm phụ thuộc lớn.
- Edition/giấy phép hoặc dịch vụ đang dùng không cho phép feature cần thiết.

Không có ngưỡng số dòng duy nhất để quyết định partitioning. Một bảng vài chục triệu dòng có thể cần partitioning nếu có lifecycle/time pruning; một bảng lớn hơn vẫn có thể không được lợi nếu mọi truy vấn đều đọc toàn bộ dữ liệu.

### 3.3. Đặt câu hỏi trước khi thiết kế

1. Truy vấn quan trọng lọc theo cột nào?
2. Dữ liệu có tăng theo thời gian hay phân bố theo tenant/region?
3. Dữ liệu cũ được giữ, archive hoặc xóa theo quy tắc nào?
4. DML có phân bố đều giữa partition hay dồn vào một partition nóng?
5. Có cần unique key toàn bảng không?
6. Index sẽ là local hay global?
7. Có cần partition-wise join không?
8. Database release, edition và quyền sử dụng partitioning là gì?
9. Công cụ backup, replication, ETL và migration có hỗ trợ partition không?
10. Đã có baseline execution plan và runtime metrics để so sánh chưa?

## 4. Các chiến lược partitioning cơ bản

Oracle hỗ trợ nhiều phương pháp phân vùng. Hãy chọn theo semantics dữ liệu và access pattern, không chọn theo tên kỹ thuật.

### 4.1. RANGE partitioning

RANGE phân vùng theo các khoảng giá trị có thứ tự. Đây là lựa chọn phổ biến cho ngày tháng, số thứ tự hoặc khóa có thứ tự tự nhiên.

~~~sql
CREATE TABLE sales_range_lab (
    sale_id NUMBER NOT NULL,
    sale_date DATE NOT NULL,
    customer_id NUMBER NOT NULL,
    amount NUMBER(12,2) NOT NULL
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

Mỗi partition nhận giá trị nhỏ hơn upper bound được khai báo. Ví dụ P2026_01 chứa ngày từ 2026-01-01 đến trước 2026-02-01 vì partition trước đó đã nhận mọi giá trị nhỏ hơn 2026-01-01.

RANGE phù hợp với dữ liệu có thứ tự và truy vấn theo khoảng. Cần xác định partition tương lai hoặc chính sách tạo partition mới để tránh lỗi khi INSERT vượt ranh giới cao nhất.

### 4.2. INTERVAL partitioning

INTERVAL là phần mở rộng của range partitioning, cho phép Oracle tự tạo partition tiếp theo khi dữ liệu mới vượt transition point. Nó hữu ích cho dữ liệu thời gian được nạp liên tục theo tháng/quý/ngày.

~~~sql
CREATE TABLE sales_interval_lab (
    sale_id NUMBER NOT NULL,
    sale_date DATE NOT NULL,
    customer_id NUMBER NOT NULL,
    amount NUMBER(12,2) NOT NULL
)
PARTITION BY RANGE (sale_date)
INTERVAL (NUMTOYMINTERVAL(1, 'MONTH'))
(
    PARTITION p_before_2026
        VALUES LESS THAN (DATE '2026-01-01')
);
~~~

Partition đầu tiên là range partition tường minh. Khi có dữ liệu vượt transition point, Oracle có thể tạo interval partition tương ứng. Tên partition do Oracle sinh nếu không có cơ chế đặt tên phù hợp trong thiết kế.

Interval partitioning tiện cho nạp dữ liệu định kỳ nhưng không thay thế việc giám sát số lượng partition, retention và giới hạn release. Hãy kiểm tra các quy tắc interval và loại partition key được hỗ trợ trong phiên bản mục tiêu.

### 4.3. LIST partitioning

LIST phân vùng theo các giá trị rời rạc, ví dụ khu vực, loại sản phẩm hoặc mã thị trường:

~~~sql
CREATE TABLE customer_list_lab (
    customer_id NUMBER NOT NULL,
    region_code VARCHAR2(10 CHAR) NOT NULL,
    customer_name VARCHAR2(100 CHAR)
)
PARTITION BY LIST (region_code) (
    PARTITION p_north VALUES ('NORTH'),
    PARTITION p_south VALUES ('SOUTH'),
    PARTITION p_east  VALUES ('EAST'),
    PARTITION p_other VALUES (DEFAULT)
);
~~~

DEFAULT partition nhận các giá trị không được liệt kê trong các partition còn lại. Nó giúp tránh lỗi insert khi xuất hiện giá trị mới, nhưng cũng có nghĩa dữ liệu mới có thể dồn vào p_other cho đến khi DBA phân chia lại.

LIST phù hợp khi miền giá trị nhỏ và có ý nghĩa nghiệp vụ rõ. Nếu giá trị tăng liên tục hoặc số distinct quá lớn, LIST có thể tạo quá nhiều partition.

### 4.4. HASH partitioning

HASH phân phối hàng vào các partition dựa trên hàm hash của partition key. Nó phù hợp khi cần phân bố dữ liệu tương đối đều và không có một range/lifecycle tự nhiên.

~~~sql
CREATE TABLE event_hash_lab (
    event_id NUMBER NOT NULL,
    tenant_id NUMBER NOT NULL,
    event_time TIMESTAMP NOT NULL,
    payload CLOB
)
PARTITION BY HASH (tenant_id)
PARTITIONS 8;
~~~

HASH có thể giúp phân tán dữ liệu và DML trên nhiều partition. Nhưng truy vấn theo khoảng thời gian sẽ không tự prune theo EVENT_TIME nếu partition key là TENANT_ID. Chọn key dựa trên truy vấn quan trọng và phân bố dữ liệu.

### 4.5. Composite partitioning

Composite partitioning chia theo một phương pháp ở cấp partition rồi chia tiếp mỗi partition bằng một phương pháp khác. Ví dụ RANGE-HASH:

~~~sql
CREATE TABLE sales_range_hash_lab (
    sale_id NUMBER NOT NULL,
    sale_date DATE NOT NULL,
    customer_id NUMBER NOT NULL,
    amount NUMBER(12,2) NOT NULL
)
PARTITION BY RANGE (sale_date)
SUBPARTITION BY HASH (customer_id)
SUBPARTITIONS 4
(
    PARTITION p2026_01 VALUES LESS THAN (DATE '2026-02-01'),
    PARTITION p2026_02 VALUES LESS THAN (DATE '2026-03-01'),
    PARTITION p2026_03 VALUES LESS THAN (DATE '2026-04-01')
);
~~~

Ví dụ này chia theo tháng trước, rồi hash theo customer_id trong mỗi tháng. Truy vấn theo tháng có thể prune partition; truy vấn trong tháng có thể tận dụng subpartition pruning nếu có điều kiện phù hợp trên customer_id.

Các kiểu composite và khả năng kết hợp phụ thuộc release. Hãy kiểm tra tài liệu đúng phiên bản trước khi dùng một phương pháp cụ thể.

### 4.6. Reference partitioning

Reference partitioning cho phép bảng con phân vùng theo quan hệ khóa ngoại đến bảng cha đã được partition. Nó hữu ích khi dữ liệu con cần đi cùng partition của bản ghi cha, ví dụ order header và order lines. Cấu trúc cần foreign key phù hợp và điều kiện hỗ trợ theo tài liệu Oracle.

~~~sql
CREATE TABLE orders_parent_lab (
    order_id NUMBER PRIMARY KEY,
    order_date DATE NOT NULL
)
PARTITION BY RANGE (order_date) (
    PARTITION p_before_2026 VALUES LESS THAN (DATE '2026-01-01'),
    PARTITION p2026 VALUES LESS THAN (DATE '2027-01-01'),
    PARTITION p_future VALUES LESS THAN (MAXVALUE)
);

CREATE TABLE order_lines_ref_lab (
    order_id NUMBER NOT NULL,
    line_id NUMBER NOT NULL,
    product_id NUMBER NOT NULL,
    quantity NUMBER NOT NULL,
    CONSTRAINT pk_order_lines_ref_lab
        PRIMARY KEY (order_id, line_id),
    CONSTRAINT fk_order_lines_ref_lab
        FOREIGN KEY (order_id)
        REFERENCES orders_parent_lab(order_id)
)
PARTITION BY REFERENCE (fk_order_lines_ref_lab);
~~~

Reference partitioning giúp các hàng con đi theo partition của hàng cha theo quan hệ tham chiếu. Khả năng dùng các thao tác partition maintenance cascade và các giới hạn liên quan phải được kiểm tra theo release.

## 5. Chọn partition key

Partition key là quyết định quan trọng nhất của thiết kế. Chọn sai key có thể khiến partitioning chỉ tăng độ phức tạp mà không giảm công việc truy vấn.

### 5.1. Chọn theo predicate thường dùng

Nếu đa số báo cáo lọc theo SALE_DATE, range partition theo SALE_DATE có thể hỗ trợ pruning. Nếu hệ thống chủ yếu xử lý từng tenant và dữ liệu phân bố theo tenant, hash/list partition theo TENANT_ID có thể phù hợp.

Hãy xem SQL thực tế, không chỉ dựa trên mô tả nghiệp vụ. Một cột có ý nghĩa nghiệp vụ nhưng không xuất hiện trong predicate/join/lifecycle có thể không phải partition key tốt.

### 5.2. Chọn theo vòng đời dữ liệu

Nếu dữ liệu cũ được archive hoặc drop theo tháng, partition key ngày/tháng tạo đơn vị retention tự nhiên. Nếu phải xóa dữ liệu cũ theo tenant hoặc vùng, partition key tương ứng có thể giúp thao tác theo vùng.

### 5.3. Cân bằng số lượng và kích thước partition

Partition quá lớn làm giảm lợi ích maintenance/pruning. Partition quá nhỏ hoặc quá nhiều làm tăng metadata, parse/optimization overhead, công việc quản trị, index partition và số lượng segment. Không có số lượng partition tối ưu chung cho mọi hệ thống.

Hãy ước lượng:

- Tốc độ tăng dữ liệu.
- Kích thước trung bình mỗi kỳ.
- Số kỳ cần giữ online.
- Số partition cần truy vấn trong một câu.
- Số subpartition trên mỗi partition.
- Số index partition tương ứng.

### 5.4. Tránh skew và hot partition

LIST partition theo một tenant lớn có thể khiến một partition chứa phần lớn dữ liệu. HASH có thể phân bố đều hơn, nhưng nếu key có skew hoặc workload tập trung trên một giá trị, một số partition/blocks vẫn có thể nóng.

Kiểm tra số hàng, dung lượng và DML rate theo partition. Đừng chỉ nhìn số partition được khai báo rồi giả định dữ liệu đã phân bố đều.

### 5.5. Partition key và unique constraints

Với partitioned table, local unique index/unique constraint có những yêu cầu về việc partition key phải nằm trong unique key để Oracle có thể bảo đảm tính duy nhất trong từng partition. Nếu cần unique key toàn bảng không chứa partition key, có thể phải dùng global unique index hoặc thiết kế khóa khác.

Ví dụ một bảng SALES partition theo SALE_DATE nhưng SALE_ID phải duy nhất toàn bảng:

- Unique key (SALE_ID, SALE_DATE) có thể phù hợp với local unique index nếu semantics nghiệp vụ cho phép cặp này.
- Nếu chỉ SALE_ID phải duy nhất toàn bảng, global unique index trên SALE_ID có thể cần thiết.

Đây là trade-off quan trọng: global index có thể làm partition maintenance phức tạp hơn. Hãy thiết kế uniqueness và partitioning cùng lúc, không để đến cuối mới phát hiện không thể tạo constraint mong muốn.

## 6. Partition pruning

### 6.1. Static pruning

Nếu predicate xác định partition từ literal hoặc bind value có thể được xác định lúc parse/execute, Oracle có thể biết trước vùng partition cần truy cập. Ví dụ:

~~~sql
SELECT SUM(amount)
FROM sales_range_lab
WHERE sale_date >= DATE '2026-02-01'
  AND sale_date <  DATE '2026-03-01';
~~~

Với range partition theo SALE_DATE, chỉ partition tương ứng tháng 2 cần được đọc.

### 6.2. Dynamic pruning

Trong một số truy vấn, partition cần truy cập phụ thuộc giá trị được biết trong runtime, ví dụ bind variable, join hoặc subquery. Oracle có thể thực hiện dynamic pruning khi chạy. Execution plan có thể biểu diễn partition start/stop bằng KEY thay vì số partition tĩnh.

### 6.3. Predicate cần tương thích với partition key

Predicate rõ ràng:

~~~sql
WHERE sale_date >= :start_date
  AND sale_date < :end_date
~~~

thường dễ hỗ trợ pruning hơn một biểu thức bọc cột:

~~~sql
WHERE TO_CHAR(sale_date, 'YYYY-MM') = :month_text
~~~

Một số biểu thức có thể được optimizer biến đổi hoặc hỗ trợ bằng function-based partitioning/virtual column, nhưng không nên dựa vào điều đó nếu có thể viết range predicate trên partition key.

### 6.4. Truy vấn không lọc partition key

Nếu bảng partition theo SALE_DATE nhưng câu SQL chỉ lọc CUSTOMER_ID, Oracle có thể phải truy cập nhiều hoặc tất cả partition. Index local trên CUSTOMER_ID có thể giúp từng partition, nhưng không tự loại bỏ các partition.

Đây là lý do phải thiết kế partition key theo workload. Partitioning không tự động giải quyết mọi truy vấn.

### 6.5. Xem pruning trong execution plan

~~~sql
EXPLAIN PLAN FOR
SELECT SUM(amount)
FROM sales_range_lab
WHERE sale_date >= DATE '2026-02-01'
  AND sale_date <  DATE '2026-03-01';

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

Trong plan, xem các cột PARTITION_START và PARTITION_STOP. Giá trị số hoặc KEY có thể cho biết phạm vi partition được chọn; cách hiển thị phụ thuộc static/dynamic pruning và plan format.

Actual plan:

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       SUM(amount)
FROM sales_range_lab
WHERE sale_date >= DATE '2026-02-01'
  AND sale_date <  DATE '2026-03-01';

SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL, NULL, 'ALLSTATS LAST +PARTITION +PREDICATE'
    )
);
~~~

Hãy xác nhận partition pruning thực sự xảy ra và số hàng/blocks được đọc phù hợp với kỳ vọng.

## 7. Local index và global index

Index trên partitioned table có thể được tổ chức local hoặc global. Đây là quyết định ảnh hưởng truy vấn, uniqueness và chi phí partition maintenance.

### 7.1. Local index

Local index được chia tương ứng với partition của bảng. Mỗi table partition có index partition tương ứng. Local index partitioning thường dễ bảo trì khi thêm/drop/truncate partition.

~~~sql
CREATE INDEX ix_sales_date_local_lab
ON sales_range_lab(sale_date)
LOCAL;
~~~

Local index có thể local prefixed hoặc local nonprefixed tùy thứ tự cột index so với partition key. Tính local giúp quản lý từng index partition cùng table partition.

### 7.2. Global index

Global index có phạm vi bao trùm nhiều partition của bảng. Nó có thể hỗ trợ lookup theo khóa không chứa partition key và unique key toàn bảng.

~~~sql
CREATE INDEX ix_sales_id_global_lab
ON sales_range_lab(sale_id)
GLOBAL;
~~~

Global index không được chia tương ứng một-một với từng table partition theo cách local index. Có thể là nonpartitioned global index hoặc global partitioned index theo thiết kế.

### 7.3. So sánh local và global

| Tiêu chí | Local index | Global index |
| --- | --- | --- |
| Phạm vi | Tương ứng từng table partition | Bao phủ nhiều table partition |
| Pruning | Thường phù hợp với truy vấn prune partition | Có thể hỗ trợ lookup không biết partition |
| Partition maintenance | Thường dễ cô lập theo partition | Có thể cần duy trì/rebuild hoặc cập nhật global index |
| Unique key | Local unique có quy tắc liên quan partition key | Có thể bảo vệ unique key không chứa partition key |
| Quản trị | Nhiều index partitions | Quản lý phạm vi toàn bảng hoặc global partitions |

Không có lựa chọn tốt nhất chung. Nếu truy vấn luôn lọc partition key và dữ liệu được quản lý theo partition, local index thường dễ vận hành. Nếu cần lookup nhanh theo khóa toàn cục không chứa partition key, global index có thể cần thiết.

### 7.4. Global index và partition maintenance

DROP, TRUNCATE, EXCHANGE hoặc MOVE partition có thể ảnh hưởng global index. Oracle cung cấp các tùy chọn maintenance, ví dụ UPDATE GLOBAL INDEXES trong một số thao tác, hoặc các lựa chọn liên quan index unusable tùy release và câu lệnh.

~~~sql
ALTER TABLE sales_range_lab
DROP PARTITION p2026_01
UPDATE GLOBAL INDEXES;
~~~

Đây là cú pháp minh họa cho release hỗ trợ tùy chọn tương ứng. Cần kiểm tra cú pháp chính xác, online behavior, tác động DML và chi phí index maintenance theo phiên bản đang dùng. Không chạy DROP partition nếu chưa xác nhận retention, backup và dependency.

### 7.5. Index UNUSABLE

Một số thao tác partition có thể làm global index hoặc index partition trở thành UNUSABLE nếu không yêu cầu/không thực hiện maintenance phù hợp. Khi index unusable, các truy vấn/DML phụ thuộc index có thể bị ảnh hưởng hoặc lỗi tùy tình huống.

Sau partition maintenance, kiểm tra:

~~~sql
SELECT index_name, status
FROM user_indexes
WHERE table_name = 'SALES_RANGE_LAB';

SELECT index_name, partition_name, status
FROM user_ind_partitions
WHERE index_name IN (
    SELECT index_name
    FROM user_indexes
    WHERE table_name = 'SALES_RANGE_LAB'
)
ORDER BY index_name, partition_position;
~~~

Nếu cần rebuild, lập kế hoạch tài nguyên và concurrency; đừng tự động rebuild mọi index sau mọi thao tác mà không hiểu trạng thái và chi phí.

## 8. Quản lý partition trong vòng đời dữ liệu

### 8.1. Thêm partition

Với range partition có partition cuối MAXVALUE, thêm partition ở giữa cần split hoặc thao tác phù hợp vì MAXVALUE đã nhận mọi giá trị cao hơn:

~~~sql
ALTER TABLE sales_range_lab
SPLIT PARTITION p_future
AT (DATE '2026-05-01')
INTO (
    PARTITION p2026_04,
    PARTITION p_future
);
~~~

Ví dụ này tạo ranh giới tháng 4 trước partition tương lai. Hãy xác định đúng upper bound và tên partition theo quy ước vận hành.

Nếu không có MAXVALUE và giá trị mới lớn hơn partition cao nhất, có thể dùng ADD PARTITION theo cú pháp phù hợp:

~~~sql
ALTER TABLE sales_range_lab
ADD PARTITION p2026_04
VALUES LESS THAN (DATE '2026-05-01');
~~~

### 8.2. DROP PARTITION

~~~sql
ALTER TABLE sales_range_lab
DROP PARTITION p_before_2026;
~~~

DROP PARTITION loại bỏ partition và dữ liệu trong đó. Đây là thao tác phá hủy dữ liệu, có implicit commit và cần xác nhận retention/backup. Nó thường hiệu quả hơn DELETE toàn bộ hàng trong partition khi mục tiêu là loại bỏ cả vùng dữ liệu.

### 8.3. TRUNCATE PARTITION

~~~sql
ALTER TABLE sales_range_lab
TRUNCATE PARTITION p2026_01;
~~~

TRUNCATE PARTITION làm rỗng partition nhưng giữ cấu trúc partition. Dùng cho staging/reload hoặc xóa dữ liệu kỳ cụ thể khi semantics cho phép. Nó là DDL và không rollback như DELETE.

### 8.4. EXCHANGE PARTITION

EXCHANGE PARTITION hoán đổi segment dữ liệu giữa một partition và một bảng không partition tương thích. Mẫu này thường dùng để nạp dữ liệu staging nhanh:

~~~sql
ALTER TABLE sales_range_lab
EXCHANGE PARTITION p2026_01
WITH TABLE sales_stage_lab
WITHOUT VALIDATION;
~~~

WITHOUT VALIDATION bỏ qua một số kiểm tra ranh giới partition; chỉ dùng khi dữ liệu staging đã được xác minh chắc chắn thuộc partition đích. Nếu dữ liệu sai range/list, có thể làm dữ liệu không khớp định nghĩa partition. Tùy chọn validation, index maintenance và online exchange phụ thuộc release/định nghĩa.

### 8.5. SPLIT PARTITION

SPLIT chia một partition thành hai hoặc nhiều partition:

~~~sql
ALTER TABLE sales_range_lab
SPLIT PARTITION p_future
AT (DATE '2026-07-01')
INTO (
    PARTITION p2026_h1_future,
    PARTITION p_future
);
~~~

Dùng khi partition hiện tại quá lớn hoặc cần thay đổi ranh giới. Hãy đánh giá thời gian thao tác, index maintenance, logging và ảnh hưởng truy cập đồng thời.

### 8.6. MERGE PARTITIONS

MERGE kết hợp các partition liền kề theo cú pháp hỗ trợ của loại partition:

~~~sql
ALTER TABLE sales_range_lab
MERGE PARTITIONS p2026_01, p2026_02
INTO PARTITION p2026_q1_part;
~~~

Tên và range của partition sau merge phải phù hợp với thứ tự/định nghĩa. Merge có thể hữu ích khi dữ liệu cũ cần quản lý ở mức quý thay vì tháng.

### 8.7. Interval partition và partition maintenance

Interval partition có thể được tạo tự động khi insert vượt transition point. Tuy nhiên, tự động tạo partition không tự động giải quyết retention, stats, tablespace, naming, index status và giám sát số lượng partition. Hãy có job quản trị để theo dõi partition được tạo và chính sách dữ liệu.

## 9. Statistics và optimizer trên partitioned table

### 9.1. Thống kê cấp bảng và cấp partition

Optimizer cần statistics để ước lượng số hàng và chọn access path. Với partitioned table, statistics có thể được thu thập ở cấp table/global và partition. Một số thống kê incremental có thể giúp duy trì global statistics hiệu quả khi chỉ có partition mới thay đổi, tùy cấu hình và phiên bản.

### 9.2. Thu thập statistics

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname          => USER,
        tabname          => 'SALES_RANGE_LAB',
        granularity      => 'AUTO',
        cascade          => TRUE,
        estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE
    );
END;
/
~~~

GRANULARITY AUTO cho DBMS_STATS chọn mức thu thập phù hợp theo đối tượng/cấu hình. Trên hệ thống thật, hãy theo DBA statistics policy, incremental statistics và maintenance window.

### 9.3. Xem partition metadata

~~~sql
SELECT
    table_name,
    partitioning_type,
    subpartitioning_type,
    partition_count,
    partitioning_key_count
FROM user_part_tables
WHERE table_name = 'SALES_RANGE_LAB';
~~~

Xem từng partition:

~~~sql
SELECT
    partition_name,
    partition_position,
    high_value,
    num_rows,
    blocks,
    tablespace_name
FROM user_tab_partitions
WHERE table_name = 'SALES_RANGE_LAB'
ORDER BY partition_position;
~~~

HIGH_VALUE trong một số dictionary views được biểu diễn dưới dạng LONG, nên công cụ SQL có thể hạn chế thao tác lọc/hiển thị trực tiếp. Dùng DBMS_METADATA hoặc công cụ dictionary phù hợp nếu cần trích xuất DDL/range.

### 9.4. Kiểm tra execution plan

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       COUNT(*)
FROM sales_range_lab
WHERE sale_date >= DATE '2026-02-01'
  AND sale_date < DATE '2026-03-01';

SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL, NULL, 'ALLSTATS LAST +PARTITION +PREDICATE'
    )
);
~~~

Đánh giá:

- PARTITION_START/PARTITION_STOP có chỉ ra vùng cần đọc không?
- A-Rows có phù hợp với số hàng trong kỳ không?
- Buffers có giảm so với truy vấn không prune không?
- Optimizer có chọn local/global index phù hợp không?
- Có operation đọc tất cả partition do predicate thiếu partition key không?

## 10. Phiên bản Oracle: điều kiện kỹ thuật

Partitioning là tính năng phát triển qua nhiều release. Không thể lấy cú pháp hoặc khả năng của một release mới rồi mặc định database cũ hỗ trợ. Khi thiết kế, phải xác định release và mức compatibility của database đích.

### 10.1. Xác định release đang chạy

~~~sql
SELECT banner
FROM v$version
ORDER BY banner;
~~~

Hoặc:

~~~sql
SELECT product, version, status
FROM product_component_version
WHERE product LIKE 'Oracle Database%';
~~~

Các view này cho biết phiên bản/phần mềm đang chạy. Chúng không cho biết tổ chức đã mua giấy phép partitioning.

### 10.2. Kiểm tra COMPATIBLE

~~~sql
SHOW PARAMETER compatible;
~~~

Hoặc:

~~~sql
SELECT name, value
FROM v$parameter
WHERE name = 'compatible';
~~~

COMPATIBLE ảnh hưởng khả năng database sử dụng một số cấu trúc/tính năng định dạng mới. Nâng binary lên release mới không đồng nghĩa mọi tính năng mới được bật nếu COMPATIBLE chưa được nâng phù hợp. Thay đổi COMPATIBLE cần kế hoạch DBA và không phải thao tác tùy tiện.

### 10.3. Kiểm tra cú pháp theo đúng release

Trước khi dùng một loại partition hoặc thao tác maintenance:

1. Mở SQL Language Reference/Database VLDB and Partitioning Guide đúng release.
2. Kiểm tra cú pháp CREATE TABLE và ALTER TABLE của release đó.
3. Kiểm tra giới hạn số partition, loại partition key và datatype.
4. Kiểm tra tính năng online, parallel, reference/interval/composite support.
5. Kiểm tra điều kiện edition và licensing.
6. Thử trong môi trường cùng release/edition/COMPATIBLE với production.

Không dùng một bài blog hoặc cú pháp từ phiên bản khác làm căn cứ cuối cùng cho release target.

### 10.4. Các loại partition và tính năng mới có thể khác giữa release

Qua các thế hệ Oracle, hỗ trợ partitioning đã mở rộng: range/list/hash, composite, interval, reference partitioning, tự động hóa một số dạng partition và các thao tác maintenance/online. Tên tính năng, giới hạn, cú pháp và điều kiện sử dụng không đồng nhất giữa mọi phiên bản.

Một số khả năng quản lý storage, compression, ILM, online operations hoặc query optimization còn có thể phụ thuộc option khác ngoài Partitioning. Không suy luận rằng đã có quyền Partitioning thì mọi option liên quan đều được bao gồm.

## 11. Edition và giấy phép: điều kiện phải xác minh

Đây là phần cần tách biệt rõ ba câu hỏi:

1. **Database release có hỗ trợ tính năng về mặt kỹ thuật không?**
2. **Edition/dịch vụ đang dùng có cung cấp tính năng đó không?**
3. **Tổ chức có quyền sử dụng theo hợp đồng/metric hiện tại không?**

Ba câu hỏi này không tương đương.

### 11.1. Oracle Database 19c Enterprise Edition

Đối với Oracle Database 19c, Oracle Partitioning là một option của Enterprise Edition và cần giấy phép option tương ứng. Không nên coi việc đã mua Enterprise Edition là mặc nhiên đã mua Partitioning.

Nếu hệ thống chạy 19c Enterprise Edition và dự định tạo/sử dụng partitioned tables, cần xác minh hợp đồng có quyền Partitioning cho đúng deployment và metric trước khi triển khai.

### 11.2. Oracle Database 19c Standard Edition 2

Oracle Database 19c Standard Edition 2 không cung cấp Oracle Partitioning option. Không thiết kế giải pháp dựa trên table partitioning rồi kỳ vọng chỉ cần thay edition hoặc bật một tham số để sử dụng.

Nếu hệ thống hiện chạy SE2, hãy đánh giá lựa chọn khác như index, archival tables, bảng theo kỳ do ứng dụng quản lý, hoặc kế hoạch chuyển edition/service nếu có nhu cầu partitioning. Mỗi phương án có trade-off vận hành riêng.

### 11.3. Các release và edition khác

Không được suy rộng điều kiện 19c sang mọi release. Tên edition, sản phẩm, giới hạn và cách đóng gói option có thể thay đổi theo thời gian. Với release khác 19c:

- Tra đúng Licensing Information User Manual của release đó.
- Tra bảng feature availability theo edition.
- Xác nhận Partitioning có phải option riêng hay được bao gồm trong service/package.
- Kiểm tra các điều khoản theo cloud service, engineered system hoặc hợp đồng riêng.

Đặc biệt, không dùng một ma trận phiên bản cũ để kết luận quyền sử dụng của một dịch vụ cloud hiện tại.

### 11.4. Metric và phạm vi cấp phép

Oracle option có thể được cấp phép theo metric như Processor hoặc Named User Plus tùy hợp đồng. Không tự suy ra số lượng license chỉ từ số partition, số bảng hoặc số user truy vấn.

Phải xác minh:

- Metric trong hợp đồng.
- Processor definition/factor nếu áp dụng.
- Named User Plus minimums nếu áp dụng.
- Số server/node/processor và môi trường thuộc phạm vi hợp đồng.
- Quy tắc cluster, failover, disaster recovery, test/dev và cloud.
- Các điều khoản riêng của dịch vụ/hợp đồng.

Không tự đặt ra một công thức chung cho mọi deployment. License scope phụ thuộc tài liệu đặt mua, metric và điều khoản pháp lý cụ thể.

### 11.5. Feature usage không phải bằng chứng entitlement

Một số view/công cụ có thể hiển thị option hoặc feature usage:

~~~sql
SELECT parameter, value
FROM v$option
WHERE parameter LIKE '%Partition%';
~~~

V$OPTION có thể cho biết option được nhận diện/enable ở cấp software. Giá trị này **không chứng minh** tổ chức đã mua giấy phép.

~~~sql
SELECT name, detected_usages, currently_used,
       first_usage_date, last_usage_date
FROM dba_feature_usage_statistics
WHERE LOWER(name) LIKE '%partition%';
~~~

DBA_FEATURE_USAGE_STATISTICS có thể hỗ trợ theo dõi feature usage theo cơ chế Oracle. Nó không thay thế hợp đồng, Licensing Information User Manual hoặc kết luận của nhóm license management. Cách phát hiện/ghi nhận có thể phụ thuộc phiên bản và thời điểm.

Không dùng câu SELECT trên để tự tuyên bố “được phép dùng” hoặc “không cần license”. Đây là dữ liệu kỹ thuật phục vụ điều tra, không phải giấy phép.

### 11.6. Dịch vụ cloud và hợp đồng đóng gói

Một số dịch vụ Oracle Cloud hoặc dịch vụ managed/engineered có thể đóng gói quyền sử dụng theo service description/contract khác với cài đặt on-premises. Cần kiểm tra đúng SKU/service, region, deployment model và terms đang mua.

Không mặc định:

- Một database chạy trên cloud luôn được bao gồm mọi option.
- Một dịch vụ mang tên Enterprise tự động bao gồm Partitioning.
- Một tính năng hiển thị TRUE trong V$OPTION đồng nghĩa đã được cấp quyền.
- Quyền của môi trường test/dev tự động giống production.

Hãy dùng hợp đồng và tài liệu license của dịch vụ cụ thể làm căn cứ.

### 11.7. Một số option liên quan phải kiểm tra riêng

Partitioning không tự động cấp quyền cho mọi tính năng có thể dùng cùng bảng partition. Ví dụ, một thiết kế có thể còn dùng Advanced Compression, một số khả năng ILM/Heat Map, In-Memory hoặc option khác. Mỗi option cần được xác minh theo đúng release, edition và license terms. Không gộp tất cả thành một “gói partitioning”.

## 12. Quy trình xác minh trước khi dùng partitioning

Trước khi tạo partitioned table trên môi trường tổ chức, thực hiện theo trình tự:

### Bước 1 — Xác định môi trường

Ghi nhận:

- Database product và release.
- Edition.
- On-premises, cloud service hay engineered system.
- COMPATIBLE.
- RAC/cluster/standby nếu có.
- Nơi chạy DDL và nơi sẽ sử dụng feature.

### Bước 2 — Kiểm tra feature support

Đối chiếu SQL Language Reference, VLDB and Partitioning Guide và Licensing Information User Manual của đúng release. Xác nhận kiểu partition, giới hạn và thao tác maintenance cần thiết.

### Bước 3 — Kiểm tra entitlement

Đối chiếu order document, contract, metric, CSI/service SKU và deployment scope. Với Oracle 19c EE, xác minh Partitioning Option được cấp phép; với 19c SE2, không sử dụng Oracle Partitioning option.

### Bước 4 — Xác minh option liên quan

Nếu thiết kế còn dùng compression, ILM, online operations hoặc option khác, kiểm tra điều kiện của từng tính năng riêng.

### Bước 5 — Xây proof of concept

Thử trên môi trường cùng release/edition/COMPATIBLE:

- DDL tạo partition.
- INSERT vào các partition.
- Partition pruning.
- Local/global index behavior.
- Partition maintenance.
- Backup/restore, replication và ETL.
- Execution plan và runtime metrics.

### Bước 6 — Review vận hành và license

DBA, kiến trúc sư và license manager xác nhận:

- Lợi ích kỹ thuật có đo được không?
- Rủi ro maintenance/index có chấp nhận được không?
- Quyền sử dụng có đủ cho mọi deployment không?
- Có cần thay đổi hợp đồng hoặc kiến trúc không?

### Bước 7 — Triển khai có kiểm soát

Lập migration, backup/recovery plan, partition creation schedule, retention policy, index maintenance, statistics plan, monitoring và rollback/contingency. DDL partition có implicit commit; không đưa vào giữa một transaction nghiệp vụ.

## 13. Bài thực hành: partition pruning và lifecycle

Ví dụ sau dùng bảng lab và cú pháp range partition cơ bản. Chỉ chạy trên database mà việc sử dụng partitioning đã được xác minh phù hợp với release/edition/license.

### 13.1. Tạo bảng RANGE partition

~~~sql
CREATE TABLE sales_partition_lab (
    sale_id NUMBER NOT NULL,
    sale_date DATE NOT NULL,
    customer_id NUMBER NOT NULL,
    amount NUMBER(12,2) NOT NULL
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

### 13.2. Nạp dữ liệu

~~~sql
INSERT INTO sales_partition_lab
VALUES (1, DATE '2026-01-05', 100, 120);

INSERT INTO sales_partition_lab
VALUES (2, DATE '2026-01-20', 101, 250);

INSERT INTO sales_partition_lab
VALUES (3, DATE '2026-02-10', 100, 80);

INSERT INTO sales_partition_lab
VALUES (4, DATE '2026-03-12', 102, 310);

INSERT INTO sales_partition_lab
VALUES (5, DATE '2026-04-01', 103, 90);

COMMIT;
~~~

### 13.3. Xem partition chứa dữ liệu

~~~sql
SELECT
    partition_name,
    partition_position,
    num_rows,
    blocks
FROM user_tab_partitions
WHERE table_name = 'SALES_PARTITION_LAB'
ORDER BY partition_position;
~~~

NUM_ROWS/BLOCKS phụ thuộc statistics. Nếu chưa gather stats, số liệu có thể NULL hoặc cũ.

### 13.4. Truy vấn một tháng

~~~sql
SELECT sale_id, sale_date, amount
FROM sales_partition_lab
WHERE sale_date >= DATE '2026-02-01'
  AND sale_date < DATE '2026-03-01';
~~~

Kiểm tra execution plan để xác nhận chỉ partition tháng 2 được truy cập. Dữ liệu lab nhỏ nên optimizer có thể chọn một scan path khác; hãy tập trung vào partition start/stop và actual plan.

### 13.5. Truy vấn không có partition key

~~~sql
SELECT SUM(amount)
FROM sales_partition_lab
WHERE customer_id = 100;
~~~

Vì partition key là SALE_DATE nhưng predicate chỉ lọc CUSTOMER_ID, Oracle có thể phải truy cập nhiều partition. Một local index trên CUSTOMER_ID có thể hỗ trợ lookup trong từng partition, nhưng không tự loại bỏ partition.

### 13.6. Thêm index local

~~~sql
CREATE INDEX ix_sales_customer_local_lab
ON sales_partition_lab(customer_id)
LOCAL;
~~~

So sánh execution plan của truy vấn CUSTOMER_ID trước và sau khi tạo index. Không mặc định index luôn được chọn; bảng lab nhỏ hoặc predicate ít chọn lọc có thể khiến full scan rẻ hơn.

### 13.7. Thêm partition tương lai

Vì p_future dùng MAXVALUE, dùng SPLIT để tạo partition mới:

~~~sql
ALTER TABLE sales_partition_lab
SPLIT PARTITION p_future
AT (DATE '2026-05-01')
INTO (
    PARTITION p2026_04,
    PARTITION p_future
);
~~~

Kiểm tra lại USER_TAB_PARTITIONS. Hãy hiểu rằng giá trị nhỏ hơn 2026-05-01 sau partition tháng 3 sẽ đi vào p2026_04; các giá trị từ 2026-05-01 trở lên vẫn ở p_future.

### 13.8. Truncate một partition lab

~~~sql
ALTER TABLE sales_partition_lab
TRUNCATE PARTITION p2026_01;
~~~

Thao tác này xóa dữ liệu trong partition tháng 1. Đây là DDL và không rollback như DELETE. Chỉ chạy sau khi chắc chắn dữ liệu lab có thể xóa.

### 13.9. Dọn bảng lab

~~~sql
DROP TABLE sales_partition_lab PURGE;
~~~

DROP TABLE là DDL có implicit commit. Không chạy trên bảng nghiệp vụ thật.

## 14. Tác động đến ứng dụng và hệ sinh thái dữ liệu

Partitioning ảnh hưởng nhiều hơn câu CREATE TABLE. Trước khi áp dụng, hãy xem mọi thành phần phụ thuộc:

### 14.1. SQL và ứng dụng

SQL thường vẫn tham chiếu tên bảng logic. Tuy nhiên, code có thể đang:

- Dựa vào ROWID hoặc giả định vật lý.
- Dùng hints chỉ định index/access path cũ.
- Truy vấn metadata để lấy danh sách bảng.
- Chạy DDL không tương thích với partitioned table.
- Có batch job xóa dữ liệu bằng DELETE thay vì partition maintenance.

Hãy kiểm tra các assumption vật lý và SQL hints trước migration.

### 14.2. ETL và bulk load

ETL có thể cần staging table, exchange partition hoặc direct-path insert. Kiểm tra:

- Dữ liệu có đúng range/list partition không.
- Constraint validation.
- Local/global index maintenance.
- Logging và recoverability.
- Statistics sau load.
- Partition mới có được tạo đúng lịch không.

### 14.3. Backup, recovery và standby

Partitioning thay đổi đơn vị quản trị segment, nhưng không thay thế chiến lược backup/recovery. Kiểm tra RMAN, Data Guard, replication, CDC và quy trình restore với partitioned objects. Một thao tác DROP partition có thể tạo thay đổi không thể đảo ngược bằng ROLLBACK; khả năng phục hồi phụ thuộc backup/archivelog và quy trình DBA.

### 14.4. Data Pump và migration

Export/import có thể xử lý partitioned tables, nhưng phải kiểm tra phiên bản nguồn/đích, metadata, tablespace mapping, index, partition definitions và license target. Không giả định import vào edition không hỗ trợ partition sẽ tự chuyển đổi thành heap table theo ý muốn.

## 15. Các lỗi và rủi ro thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| INSERT vượt partition range thất bại | Không có partition nhận giá trị mới | Thêm partition/interval hoặc MAXVALUE theo chính sách |
| Truy vấn đọc nhiều partition | Predicate không dùng partition key hoặc không thể prune | Xem partition key, predicate và execution plan |
| Index unusable sau maintenance | Global/local index chưa được duy trì phù hợp | Kiểm tra index status và tùy chọn maintenance |
| DROP partition làm mất dữ liệu | Thao tác DDL xóa toàn partition | Xác nhận retention/backup và phê duyệt trước DDL |
| Unique constraint không tạo được | Unique key không đáp ứng quy tắc local partitioned index | Xem global unique index hoặc thiết kế key/partition |
| Quá nhiều partition | Granularity quá nhỏ hoặc retention quá dài | Tính lại kỳ, subpartition và lifecycle |
| Dữ liệu lệch vào một partition | Skew của partition key hoặc giá trị mặc định | Xem phân bố dữ liệu, đổi key hoặc chiến lược |
| Partition pruning không xảy ra | Hàm/conversion trên key, bind/logic không phù hợp | Viết predicate rõ, xem plan và datatype |
| Optimizer chọn full scan | Kết quả lớn hoặc index/table access đắt hơn | Đánh giá selectivity, clustering và buffers |
| DDL partition chặn workload | Thao tác không online hoặc cần metadata/table locks | Kiểm tra release, online capability và maintenance window |
| Dùng được về kỹ thuật nhưng thiếu license | Nhầm feature availability với entitlement | Dừng triển khai, xác minh hợp đồng/option |
| Cú pháp không hỗ trợ | Release/COMPATIBLE không đáp ứng | Đối chiếu tài liệu đúng phiên bản |

## 16. Checklist lựa chọn và triển khai partitioning

Trước khi chốt thiết kế, hãy xác nhận:

**Mục tiêu dữ liệu**

- Bảng có đủ lớn hoặc có lifecycle đủ phức tạp để cần partition không?
- Truy vấn chính có lọc theo partition key không?
- Retention/archive/drop có thể được mô hình hóa theo partition không?
- Có hot partition hoặc skew không?

**Thiết kế kỹ thuật**

- RANGE, INTERVAL, LIST, HASH hay composite phù hợp?
- Ranh giới partition có đầy đủ, không chồng lấn và đúng kỳ không?
- Có partition tương lai hoặc quy trình tạo partition mới không?
- Unique constraints có bao gồm partition key hay cần global unique index?
- Local/global index nào cần thiết?
- Global index được bảo trì ra sao khi DROP/TRUNCATE/EXCHANGE/MOVE?
- Có cần partition-wise join hoặc parallel execution không?

**Vận hành**

- Statistics cấp partition/global được quản lý thế nào?
- ETL, Data Pump, backup, standby và CDC hỗ trợ ra sao?
- DDL có implicit commit và cần maintenance window nào?
- Monitoring phát hiện partition sắp hết range, partition skew và index unusable chưa?
- Có quy trình phục hồi/đối soát sau thao tác DDL không?

**Phiên bản và giấy phép**

- Release và COMPATIBLE đã được xác nhận chưa?
- Edition/dịch vụ có hỗ trợ partitioning không?
- Đúng release Licensing Information User Manual đã được kiểm tra chưa?
- Oracle 19c EE đã có entitlement Partitioning Option chưa?
- Nếu Oracle 19c SE2, thiết kế có dựa vào một tính năng không được cung cấp không?
- Metric, server/node, cloud SKU và contract scope đã được license manager xác nhận chưa?
- Các option liên quan như Advanced Compression/ILM có được xác minh riêng chưa?

## 17. Câu hỏi tự kiểm tra

1. Partitioning chia một bảng logic thành những đơn vị nào?
2. Partitioning khác indexing như thế nào?
3. Vì sao partitioning không tự động làm mọi truy vấn nhanh hơn?
4. Partition pruning là gì?
5. RANGE partitioning phù hợp với kiểu dữ liệu nào?
6. INTERVAL partitioning khác RANGE thông thường ở khả năng nào?
7. LIST partitioning và DEFAULT partition giải quyết tình huống nào?
8. HASH partitioning có lợi thế gì và không hỗ trợ pruning theo chiều nào trong ví dụ hash tenant_id?
9. Composite RANGE-HASH partitioning chia dữ liệu ra sao?
10. Vì sao phải chọn partition key theo workload và lifecycle?
11. Leading predicate trên partition key ảnh hưởng pruning như thế nào?
12. Static pruning và dynamic pruning khác nhau ở thời điểm xác định partition ra sao?
13. Local index khác global index ở phạm vi nào?
14. Vì sao global index có thể làm partition maintenance phức tạp hơn?
15. Unique key không chứa partition key có thể cần loại index nào?
16. DROP PARTITION khác DELETE hàng như thế nào về transaction semantics?
17. EXCHANGE PARTITION thường dùng trong quy trình nào?
18. Vì sao cần kiểm tra index status sau partition maintenance?
19. BLEVEL, partition count và statistics có thể xem ở đâu?
20. Vì sao V$OPTION không chứng minh đã có giấy phép?
21. DBA_FEATURE_USAGE_STATISTICS có thay thế hợp đồng license không?
22. Điều kiện Partitioning trong Oracle Database 19c Enterprise Edition là gì?
23. Oracle Database 19c Standard Edition 2 có cung cấp Oracle Partitioning option không?
24. Vì sao không được suy rộng ma trận license 19c sang mọi release/cloud service?
25. Những option liên quan nào cần kiểm tra riêng ngoài Partitioning?

**Gợi ý trả lời:**

1. Thành các partition/subpartition được quản lý bên trong cùng bảng logic.
2. Index là cấu trúc tìm kiếm phụ; partitioning chia dữ liệu bảng thành vùng quản lý.
3. Truy vấn có thể không lọc partition key, đọc nhiều partition hoặc cần phần lớn bảng.
4. Loại bỏ các partition chắc chắn không chứa hàng phù hợp.
5. Giá trị có thứ tự như DATE, timestamp hoặc số.
6. Oracle có thể tự tạo interval partition khi dữ liệu vượt transition point.
7. LIST chia theo miền giá trị rời rạc; DEFAULT nhận giá trị chưa liệt kê.
8. HASH phân bố dữ liệu; hash theo tenant_id không tự prune theo event_time.
9. Chia theo range ở cấp partition, rồi hash trong mỗi partition.
10. Để hỗ trợ truy vấn thực tế, retention và phân bố dữ liệu.
11. Predicate phù hợp giúp Oracle xác định partition cần đọc.
12. Static biết partition từ thông tin có thể xác định sớm; dynamic xác định khi chạy.
13. Local tương ứng table partition; global có phạm vi qua nhiều table partition.
14. Một thay đổi partition có thể cần cập nhật cấu trúc index bao phủ nhiều partition.
15. Có thể cần global unique index nếu unique key không chứa partition key.
16. DROP PARTITION là DDL, implicit commit và không rollback như DELETE.
17. Nạp/hoán đổi dữ liệu staging vào partition.
18. Một số thao tác có thể làm index hoặc index partition unusable nếu không maintenance.
19. USER_PART_TABLES, USER_TAB_PARTITIONS, USER_INDEXES và các view liên quan.
20. Nó phản ánh trạng thái option phần mềm, không phải entitlement theo hợp đồng.
21. Không.
22. Partitioning là option cần cấp phép riêng cho Enterprise Edition trong 19c.
23. Không.
24. Điều kiện edition, SKU, dịch vụ và contract có thể thay đổi theo release.
25. Ví dụ Advanced Compression, ILM/Heat Map, In-Memory hoặc option được dùng cùng thiết kế.

## Tài liệu Oracle tham khảo

- [Oracle Database 19c VLDB and Partitioning Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/vldbg/): khái niệm, chiến lược partitioning, pruning, index và partition maintenance.
- [Oracle Database 19c SQL Language Reference — CREATE TABLE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/CREATE-TABLE.html): cú pháp partitioning trong CREATE TABLE.
- [Oracle Database 19c SQL Language Reference — ALTER TABLE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/ALTER-TABLE.html): thao tác ADD, DROP, TRUNCATE, EXCHANGE, SPLIT, MERGE và các tùy chọn liên quan.
- [Oracle Database 19c SQL Tuning Guide — Partition Pruning](https://docs.oracle.com/en/database/oracle/oracle-database/19/vldbg/partition-pruning.html): partition pruning và cách optimizer loại bỏ partition.
- [Oracle Database 19c SQL Tuning Guide — Partition-Wise Joins](https://docs.oracle.com/en/database/oracle/oracle-database/19/vldbg/partition-wise-joins.html): điều kiện và lợi ích của partition-wise join.
- [Oracle Database 19c Licensing Information User Manual](https://docs.oracle.com/en/database/oracle/oracle-database/19/dblic/): edition, option và feature licensing của release 19c.
- [Oracle Database Licensing](https://www.oracle.com/corporate/pricing/database-licensing.html): thông tin cấp phép Oracle Database; cần đối chiếu với hợp đồng và service terms cụ thể.
- [Oracle Database Reference — V$OPTION](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-OPTION.html): thông tin option được nhận diện trong database.
- [Oracle Database Reference — DBA_FEATURE_USAGE_STATISTICS](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/DBA_FEATURE_USAGE_STATISTICS.html): dữ liệu theo dõi feature usage.

**Nguyên tắc cần nhớ:** Partitioning có giá trị khi nó giải quyết một mục tiêu đo được: loại bỏ partition không cần đọc, quản lý dữ liệu theo vòng đời hoặc bảo trì một phần bảng. Hãy chọn partition key theo truy vấn và cách dữ liệu được giữ/xóa, thiết kế local/global index cùng constraint, rồi xác nhận pruning bằng execution plan. Trước khi dùng trên hệ thống thật, phải kiểm tra đúng release, edition, service và quyền sử dụng theo hợp đồng. Khả năng kỹ thuật nhìn thấy trong database không đồng nghĩa tổ chức đã có giấy phép.
