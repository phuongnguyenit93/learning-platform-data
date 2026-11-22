# Lưu trữ theo vòng đời dữ liệu và chiến lược xóa dữ liệu cũ trong Oracle

## 1. Vì sao cần quản lý vòng đời dữ liệu?

Trong một hệ thống vận hành lâu năm, dữ liệu thường tăng liên tục: đơn hàng, giao dịch, log nghiệp vụ, lịch sử truy cập, sự kiện, dữ liệu cảm biến và dữ liệu báo cáo. Không phải mọi dữ liệu đều cần được lưu trên cùng loại storage, có cùng thời gian truy cập hoặc được giữ vô thời hạn.

**Information Lifecycle Management (ILM)** là cách tổ chức dữ liệu theo các giai đoạn tồn tại và giá trị sử dụng của nó. Một chính sách thường phân biệt:

- Dữ liệu mới, được truy cập thường xuyên: lưu trên storage nhanh để phục vụ giao dịch.
- Dữ liệu đã ổn định, ít được cập nhật nhưng vẫn cần truy vấn: chuyển sang storage có chi phí thấp hơn hoặc nén để giảm dung lượng.
- Dữ liệu lịch sử cần lưu theo quy định: archive, có kiểm soát quyền truy cập và khả năng phục hồi.
- Dữ liệu đã hết thời hạn lưu trữ và không còn legal hold: purge khỏi hệ thống theo quy trình được phê duyệt.

Oracle Partitioning giúp quản lý các nhóm dữ liệu theo từng phần độc lập. Nếu bảng được partition theo thời gian, DBA có thể archive, move, compress, truncate hoặc drop một partition thay vì phải xử lý hàng triệu row riêng lẻ.

Một quy trình vòng đời tốt phải trả lời được các câu hỏi:

1. Dữ liệu được giữ trong hệ thống giao dịch bao lâu?
2. Khi nào chuyển dữ liệu sang archive hoặc storage rẻ hơn?
3. Dữ liệu nào cần được giữ theo luật, hợp đồng hoặc yêu cầu kiểm toán?
4. Khi nào được phép xóa vĩnh viễn?
5. Dữ liệu đã archive có thể được truy vấn hoặc khôi phục bằng cách nào?
6. Việc xóa có ảnh hưởng foreign key, index, materialized view, replication, backup và ứng dụng không?

> Nội dung dùng Oracle Database 19c. Partitioning là tính năng có yêu cầu license riêng trong các trường hợp áp dụng; cần xác nhận entitlement của tổ chức trước khi triển khai. Các ví dụ DDL chỉ chạy trong schema lab hoặc maintenance window được phê duyệt. DDL của Oracle có implicit commit và không thể rollback như một câu DELETE.

## 2. Thiết kế chính sách retention trước khi thiết kế partition

Không nên bắt đầu bằng câu lệnh DROP PARTITION. Trước hết cần có chính sách retention được nghiệp vụ và quản trị dữ liệu thống nhất.

### 2.1. Xác định mốc thời gian retention

Một bảng có thể có nhiều cột thời gian:

- CREATED_AT: thời điểm hệ thống ghi nhận row.
- EVENT_TIME: thời điểm sự kiện thực sự xảy ra.
- BUSINESS_DATE: ngày nghiệp vụ dùng để đối soát.
- CLOSED_AT: thời điểm hồ sơ kết thúc.
- INGESTED_AT: thời điểm dữ liệu được nạp vào database.

Partition key nên dựa trên cột phù hợp với truy vấn, retention và quy trình vận hành. Ví dụ:

- Bảng giao dịch thường partition theo BUSINESS_DATE hoặc TRANSACTION_DATE.
- Bảng log sự kiện có thể partition theo EVENT_TIME hoặc INGESTED_AT.
- Bảng hồ sơ có thể partition theo CLOSED_AT nếu retention bắt đầu sau khi hồ sơ đóng.

Không mặc định CREATED_AT luôn là cột phù hợp. Một sự kiện có thể được gửi muộn nhiều ngày; nếu retention theo thời điểm nhận dữ liệu nhưng yêu cầu pháp lý tính từ thời điểm phát sinh, chính sách có thể sai.

### 2.2. Định nghĩa các khoảng thời gian

Ví dụ chính sách minh họa:

| Giai đoạn | Tuổi dữ liệu | Cách quản lý |
| --- | --- | --- |
| HOT | 0–12 tháng | Online trên storage hiệu năng cao |
| WARM | Trên 12 đến 36 tháng | Vẫn query được, có thể nén hoặc chuyển tablespace |
| ARCHIVE | Trên 36 đến 84 tháng | Lưu ở archive table/tablespace hoặc hệ thống lưu trữ riêng |
| PURGE | Sau 84 tháng | Xóa khi hết nghĩa vụ lưu trữ và không có legal hold |

Các con số chỉ là ví dụ. Thời hạn thực tế phải theo luật, hợp đồng, yêu cầu kiểm toán, chính sách bảo mật và mục tiêu phục hồi.

### 2.3. Phân biệt archive và purge

**Archive** là chuyển dữ liệu sang một nơi lưu trữ khác nhưng vẫn giữ khả năng truy xuất hoặc phục hồi theo chính sách.

**Purge** là xóa dữ liệu khỏi phạm vi lưu trữ được quản lý. Một lệnh DROP PARTITION không phải là archive; nó xóa partition khỏi bảng. Nếu cần giữ dữ liệu lịch sử, phải archive hoặc export trước.

Không nên gọi một bản backup thông thường là archive. Backup phục vụ khôi phục hệ thống; archive phục vụ lưu trữ có chủ đích theo thời hạn và thường cần metadata, khả năng tìm kiếm, quyền truy cập và quy trình phục hồi riêng.

### 2.4. Legal hold và ngoại lệ retention

Một hồ sơ có thể cần giữ lâu hơn chính sách chung do:

- Tranh chấp hoặc điều tra đang diễn ra.
- Yêu cầu kiểm toán.
- Hợp đồng hoặc quy định chuyên ngành.
- Lệnh bảo toàn dữ liệu.

Quy trình purge phải kiểm tra legal hold trước khi xóa. Có thể quản lý danh sách hold trong bảng điều khiển riêng hoặc thông qua hệ thống quản trị hồ sơ. Không giả định partition cũ là đủ điều kiện xóa chỉ vì ngày partition đã vượt cutoff.

## 3. Partitioning là nền tảng của retention theo thời gian

### 3.1. Partitioning hoạt động thế nào?

Partitioning chia một bảng logic thành các partition vật lý. Ứng dụng vẫn truy vấn cùng tên bảng; Oracle tự định tuyến row tới partition theo partition key.

Ví dụ:

~~~text
SALES
  |
  +-- P2025_01  (01-Jan đến trước 01-Feb)
  +-- P2025_02  (01-Feb đến trước 01-Mar)
  +-- P2025_03  (01-Mar đến trước 01-Apr)
  +-- P2025_04  (01-Apr đến trước 01-May)
  ...
~~~

Nếu query có điều kiện trên partition key, Oracle có thể chỉ truy cập các partition liên quan. Cơ chế đó gọi là partition pruning.

Ví dụ:

~~~sql
SELECT SUM(amount)
FROM sales
WHERE sale_date >= DATE '2025-02-01'
  AND sale_date <  DATE '2025-03-01';
~~~

Nếu SALES partition theo SALE_DATE, Oracle có thể chỉ đọc partition tháng 2 thay vì quét toàn bộ bảng.

### 3.2. Chọn granularity

| Granularity | Phù hợp khi | Điểm cần cân nhắc |
| --- | --- | --- |
| Theo ngày | Lưu lượng rất lớn, cần purge/archive chính xác theo ngày | Số partition tăng nhanh |
| Theo tháng | Nhiều hệ thống giao dịch và báo cáo | Cân bằng tốt giữa quản trị và số lượng partition |
| Theo quý | Lượng dữ liệu vừa phải, retention theo quý | Ít linh hoạt khi cần xóa một phần tháng |
| Theo năm | Dữ liệu ít hoặc retention theo năm | Một partition có thể quá lớn |

Không chọn partition theo ngày chỉ vì muốn xóa dữ liệu chính xác hơn nếu mỗi ngày chỉ có vài trăm row. Số lượng partition, subpartition, index partition và chi phí dictionary cũng cần được tính đến.

### 3.3. Partition key phải phù hợp với truy vấn và retention

Nếu phần lớn query lọc theo ngày giao dịch và chính sách retention cũng tính từ ngày giao dịch, partition theo ngày giao dịch là lựa chọn tự nhiên.

Nếu query thường xuyên lọc theo CUSTOMER_ID nhưng retention theo ngày, có thể kết hợp:

- RANGE theo SALE_DATE.
- LOCAL index trên CUSTOMER_ID.
- Composite partitioning nếu có nhu cầu và license/kiến trúc cho phép.

Không nên partition theo một cột chỉ để thuận tiện cho DDL nếu nó không phản ánh cách dữ liệu được truy cập hoặc quản lý.

### 3.4. Ranh giới partition là upper bound không bao gồm

Với RANGE partitioning, giá trị trong VALUES LESS THAN là cận trên không bao gồm. Ví dụ:

~~~sql
PARTITION p2025_01 VALUES LESS THAN (DATE '2025-02-01')
~~~

Partition này chứa ngày từ trước 01-Feb-2025, tính từ lower bound của partition trước. Để biểu diễn tháng 1, predicate đúng là:

~~~sql
sale_date >= DATE '2025-01-01'
AND sale_date < DATE '2025-02-01'
~~~

Đây là khoảng nửa mở [đầu tháng, đầu tháng kế tiếp). Nó tránh lỗi ở thời điểm cuối ngày, đặc biệt khi cột DATE có thành phần giờ/phút/giây.

### 3.5. Thống nhất múi giờ

Với dữ liệu sự kiện đa quốc gia, cần thống nhất:

- Timestamp được lưu theo UTC hay giờ địa phương.
- Ngày nghiệp vụ được tính theo timezone nào.
- Thời điểm cutoff được tính theo calendar nào.
- Cách xử lý dữ liệu đến muộn và sự kiện có timestamp lùi.

Nếu partition theo DATE nhưng dữ liệu được chuyển từ TIMESTAMP WITH TIME ZONE, phải chuyển đổi nhất quán trước khi lưu. Không để một tiến trình nạp theo UTC còn tiến trình khác nạp theo giờ địa phương mà không có quy ước.

## 4. Tạo bảng RANGE partition theo tháng

Ví dụ bảng giao dịch bán hàng:

~~~sql
CREATE TABLE sales_lifecycle (
    sale_id      NUMBER        NOT NULL,
    sale_date    DATE          NOT NULL,
    customer_id  NUMBER        NOT NULL,
    amount       NUMBER(12,2)  NOT NULL,
    status       VARCHAR2(20 CHAR)
)
PARTITION BY RANGE (sale_date)
(
    PARTITION p2025_01 VALUES LESS THAN (DATE '2025-02-01'),
    PARTITION p2025_02 VALUES LESS THAN (DATE '2025-03-01'),
    PARTITION p2025_03 VALUES LESS THAN (DATE '2025-04-01')
);
~~~

Trong ví dụ, partition đầu tiên chứa các ngày nhỏ hơn 01-Feb-2025. Cần hiểu ranh giới của partition đầu tiên bao gồm cả các ngày trước 01-Jan-2025 nếu bảng không có partition thấp hơn.

Tạo local index:

~~~sql
CREATE INDEX ix_sales_lifecycle_customer
ON sales_lifecycle(customer_id, sale_date)
LOCAL;
~~~

Local index được partition tương ứng với table partitions. Đây là lựa chọn thuận tiện cho partition maintenance vì các index partition gắn với từng table partition.

### 4.1. Thêm partition cho tháng mới

Trước khi nạp dữ liệu tháng tiếp theo:

~~~sql
ALTER TABLE sales_lifecycle
ADD PARTITION p2025_04
VALUES LESS THAN (DATE '2025-05-01');
~~~

Nếu không có partition chứa giá trị ngày mới, INSERT có thể lỗi ORA-14400. Quy trình vận hành nên tạo partition tương lai trước khi batch nạp dữ liệu bắt đầu.

### 4.2. Có nên tạo partition MAXVALUE?

Có thể tạo một partition cuối với VALUES LESS THAN (MAXVALUE) để tránh lỗi khi dữ liệu đến muộn hoặc partition tương lai chưa được tạo. Tuy nhiên, row mới có thể đi vào partition MAXVALUE thay vì partition tháng dự kiến.

Khi cần thêm partition có cận nhỏ hơn MAXVALUE, phải SPLIT partition MAXVALUE. Việc này có thể cần di chuyển dữ liệu và bảo trì index.

Vì vậy:

- Dùng MAXVALUE nếu ưu tiên không để INSERT thất bại khi dữ liệu vượt cận.
- Có quy trình theo dõi và xử lý dữ liệu trong MAXVALUE.
- Không để partition MAXVALUE trở thành nơi chứa dữ liệu không được phân loại vô thời hạn.
- Nếu không dùng MAXVALUE, tạo partition trước và có cảnh báo trước thời điểm nạp.

### 4.3. Cập nhật partition key

Oracle mặc định DISABLE ROW MOVEMENT. Nếu UPDATE partition key làm row phải chuyển sang partition khác, câu lệnh có thể lỗi ORA-14402.

Có thể cho phép row movement:

~~~sql
ALTER TABLE sales_lifecycle ENABLE ROW MOVEMENT;
~~~

Chỉ bật khi nghiệp vụ thực sự cần cập nhật partition key. Việc chuyển row có thể phát sinh chi phí index, redo/undo và thay đổi ROWID; không nên xem nó như thao tác cập nhật cột thông thường.

## 5. Interval partitioning: tự tạo partition theo thời gian

Nếu dữ liệu phát sinh liên tục theo tháng, có thể dùng INTERVAL partitioning để Oracle tự tạo partition cho các giá trị vượt transition point.

~~~sql
CREATE TABLE sales_interval (
    sale_id      NUMBER NOT NULL,
    sale_date    DATE   NOT NULL,
    customer_id  NUMBER NOT NULL,
    amount       NUMBER(12,2) NOT NULL
)
PARTITION BY RANGE (sale_date)
INTERVAL (NUMTOYMINTERVAL(1, 'MONTH'))
(
    PARTITION p_before_2025
    VALUES LESS THAN (DATE '2025-01-01')
);
~~~

Partition RANGE được khai báo ban đầu xác định transition point. Khi INSERT row có SALE_DATE ở vùng interval, Oracle tự tạo partition theo khoảng tháng.

### 5.1. Lợi ích và giới hạn

Lợi ích:

- Không phải tạo từng partition tháng bằng script.
- Giảm nguy cơ quên tạo partition mới.
- Phù hợp dữ liệu time-series có thời gian phát sinh đều đặn.

Điểm cần lưu ý:

- Partition mới có thể được đặt tên hệ thống dạng SYS_P... nếu không có tên do người dùng quản lý.
- Phải theo dõi số partition và tên partition trong data dictionary.
- Interval partitioning vẫn cần kế hoạch retention, archive và purge.
- Không phải mọi kiểu partition key hoặc mọi loại interval đều phù hợp với mọi nghiệp vụ.

### 5.2. Kiểm tra partition tự sinh

~~~sql
SELECT table_name,
       partition_name,
       partition_position,
       tablespace_name,
       num_rows
FROM user_tab_partitions
WHERE table_name = 'SALES_INTERVAL'
ORDER BY partition_position;
~~~

Với interval partitioning, không nên hard-code tên SYS_P... trong quy trình purge nếu tên có thể thay đổi giữa các database. Có thể dùng partition position, HIGH_VALUE hoặc metadata được quản lý bởi quy trình tạo partition để xác định đúng partition.

### 5.3. Tạo partition theo mốc thời gian

Oracle hỗ trợ cú pháp tham chiếu partition theo giá trị:

~~~sql
SELECT COUNT(*)
FROM sales_interval PARTITION FOR (DATE '2025-03-15');
~~~

Điều này hữu ích khi tên partition do hệ thống sinh. Với DDL bảo trì như DROP PARTITION, câu lệnh cần tên partition; ứng dụng vận hành phải tra metadata để lấy đúng tên và kiểm tra high value trước khi chạy.

## 6. Tổ chức HOT, WARM, ARCHIVE và PURGE

Một kiến trúc có thể dùng tablespace và partition để đặt dữ liệu ở các tầng khác nhau:

~~~text
                   Chính sách vòng đời
                           |
             +-------------+-------------+
             |             |             |
            HOT           WARM         ARCHIVE
          mới nhất      ít truy cập    lịch sử dài hạn
             |             |             |
        fast storage   lower-cost TS   archive TS / export
             |             |             |
             +-------------+-------------+
                           |
                      hết retention
                           |
                    legal hold check
                           |
                         PURGE
~~~

Ví dụ:

- HOT: partition 12 tháng gần nhất.
- WARM: partition từ tháng 13 đến tháng 36, có thể chuyển tablespace hoặc nén.
- ARCHIVE: partition cũ hơn, exchange sang bảng archive hoặc export ra kho lưu trữ.
- PURGE: xóa sau thời hạn pháp lý và khi đã xác nhận archive/backup theo yêu cầu.

Không bắt buộc phải có bốn tablespace. Có thể dùng cùng tablespace nhưng phân loại theo partition, hoặc lưu archive ngoài database. Quan trọng là có metadata và quy trình xác định dữ liệu đang ở tầng nào.

## 7. DROP PARTITION: xóa dữ liệu cũ nhanh theo partition

### 7.1. Khi nào dùng?

Nếu toàn bộ partition nằm ngoài retention và đã xử lý archive/legal hold, DROP PARTITION là cách hiệu quả để xóa một nhóm dữ liệu lớn.

~~~sql
ALTER TABLE sales_lifecycle
DROP PARTITION p2025_01
UPDATE INDEXES;
~~~

Lệnh xóa partition tháng 1 khỏi bảng, gồm dữ liệu trong partition và metadata partition. Local index partition tương ứng cũng được xử lý.

### 7.2. DROP PARTITION khác DELETE

| Đặc điểm | DROP PARTITION | DELETE |
| --- | --- | --- |
| Phạm vi | Toàn bộ một partition | Row thỏa WHERE |
| Cách thực hiện | DDL quản lý segment/metadata | DML theo row |
| Undo/redo | Không giống xóa từng row; thường giảm đáng kể so với DELETE lớn | Phát sinh undo/redo cho thay đổi row và index |
| DELETE trigger | Không chạy như từng row DELETE | DELETE trigger được kích hoạt |
| ON DELETE CASCADE | Không tự thực thi như DELETE từng row | Có thể xóa row con nếu FK dùng ON DELETE CASCADE |
| Rollback | Không thể rollback DDL | Có thể rollback trước COMMIT |
| Recycle bin | Partition bị drop không được đưa vào recycle bin | Không áp dụng recycle bin theo cách đó |
| Phù hợp | Xóa trọn partition đã hết retention | Xóa một phần row hoặc cần trigger/FK semantics |

### 7.3. DROP PARTITION không thể khôi phục bằng ROLLBACK

DROP PARTITION là DDL. Oracle thực hiện implicit commit theo quy tắc DDL và partition bị drop không được đưa vào recycle bin. Vì vậy:

- Không chạy DROP PARTITION trước khi xác nhận archive.
- Kiểm tra đúng table, partition và high value.
- Có backup hoặc archive phù hợp với yêu cầu phục hồi.
- Ghi audit về ai chạy, lúc nào, partition nào và lý do.

Đừng giả định FLASHBACK TABLE hoặc recycle bin có thể phục hồi partition đã drop. Hãy xác nhận phương án recovery trước khi purge.

### 7.4. Giới hạn DROP PARTITION

- Không thể drop partition cuối cùng nếu bảng chỉ còn một partition; khi đó phải xử lý ở cấp bảng.
- Một số thao tác có giới hạn với interval partitioning, reference partitioning và các kiểu bảng đặc biệt.
- Nếu có foreign key tham chiếu dữ liệu trong partition, phải xử lý quan hệ trước.
- Sau DDL, kiểm tra local/global index status.

## 8. TRUNCATE PARTITION: xóa row nhưng giữ partition

Nếu cần làm rỗng partition nhưng vẫn giữ partition definition:

~~~sql
ALTER TABLE sales_lifecycle
TRUNCATE PARTITION p2025_01
UPDATE INDEXES;
~~~

Khác với DROP PARTITION:

- TRUNCATE PARTITION giữ partition trong bảng.
- Các row trong partition bị loại bỏ.
- Local index partition tương ứng được truncate.
- Global index cần được duy trì hoặc xử lý theo tùy chọn thích hợp.

TRUNCATE PARTITION phù hợp khi partition sẽ được tái sử dụng hoặc khi muốn xóa dữ liệu của một vùng nhưng giữ cấu trúc partition.

### 8.1. DROP STORAGE và REUSE STORAGE

Oracle hỗ trợ tùy chọn điều khiển cách xử lý không gian của partition khi truncate:

- DROP STORAGE: trả lại phần lớn extent được cấp phát vượt mức ban đầu theo quy tắc storage của Oracle.
- REUSE STORAGE: giữ không gian để partition có thể tái sử dụng.

Hãy chọn theo mục tiêu dung lượng và khả năng nạp lại. Không nhầm TRUNCATE PARTITION với việc xóa partition metadata.

### 8.2. TRUNCATE PARTITION cũng không rollback được

TRUNCATE là DDL, không thể rollback để khôi phục row đã xóa. Trước khi chạy cần kiểm tra archive, backup, foreign key và index.

## 9. Archive bằng EXCHANGE PARTITION

Một chiến lược phổ biến là chuyển partition cũ thành một bảng độc lập, sau đó archive hoặc export bảng đó.

### 9.1. Ý tưởng

~~~text
SALES partitioned table
        |
        | EXCHANGE PARTITION
        v
SALES_ARCHIVE_STAGE nonpartitioned table
        |
        +--> export / backup / move tablespace
        |
        +--> kiểm tra archive
        |
        +--> giữ hoặc purge theo retention
~~~

EXCHANGE PARTITION trao đổi segment dữ liệu giữa partition của bảng partitioned và bảng nonpartitioned. Đây là thao tác metadata/segment swap, thường nhanh hơn copy hàng triệu row bằng INSERT SELECT.

### 9.2. Tạo bảng archive staging tương thích

Ví dụ cấu trúc bảng:

~~~sql
CREATE TABLE sales_archive_stage (
    sale_id      NUMBER NOT NULL,
    sale_date    DATE   NOT NULL,
    customer_id  NUMBER NOT NULL,
    amount       NUMBER(12,2) NOT NULL,
    status       VARCHAR2(20 CHAR)
);
~~~

Bảng exchange phải tương thích về số cột, thứ tự, kiểu dữ liệu và các điều kiện Oracle yêu cầu. Nếu dùng INCLUDING INDEXES, cần tạo index tương ứng trên bảng exchange để đổi các local index partition phù hợp.

### 9.3. Exchange partition

~~~sql
ALTER TABLE sales_lifecycle
EXCHANGE PARTITION p2025_01
WITH TABLE sales_archive_stage
INCLUDING INDEXES
WITH VALIDATION
UPDATE GLOBAL INDEXES;
~~~

Ý nghĩa:

- Dữ liệu của partition P2025_01 được chuyển sang SALES_ARCHIVE_STAGE.
- Dữ liệu hiện có trong SALES_ARCHIVE_STAGE (nếu có) được đổi vào partition.
- INCLUDING INDEXES yêu cầu các index tương ứng để exchange index segment phù hợp.
- WITH VALIDATION yêu cầu Oracle kiểm tra row của bảng exchange có thuộc partition đang đổi hay không. Đây là mặc định nếu không ghi rõ.
- UPDATE GLOBAL INDEXES yêu cầu duy trì global index trong thao tác.

Sau khi exchange, partition P2025_01 trở thành rỗng nếu bảng staging ban đầu rỗng; bảng staging nhận dữ liệu lịch sử. Có thể export, move hoặc compress bảng archive.

### 9.4. WITH VALIDATION và WITHOUT VALIDATION

WITH VALIDATION kiểm tra dữ liệu trong bảng exchange có phù hợp với partition key bounds hay không. Nếu có row ngoài khoảng, thao tác thất bại.

WITHOUT VALIDATION bỏ qua bước kiểm tra. Chỉ dùng khi quy trình đã bảo đảm dữ liệu đúng partition bằng một cách tin cậy. Nếu bỏ qua validation mà row không phù hợp, dữ liệu có thể nằm sai partition logic và ảnh hưởng partition pruning hoặc kết quả quản trị.

Không chọn WITHOUT VALIDATION chỉ để làm lệnh nhanh hơn khi chưa có kiểm soát dữ liệu.

### 9.5. INCLUDING INDEXES và EXCLUDING INDEXES

- INCLUDING INDEXES: đổi các index tương ứng giữa local index partition và index trên bảng exchange khi các cấu trúc đáp ứng yêu cầu.
- EXCLUDING INDEXES: không exchange các index tương ứng; một số index có thể bị đánh dấu unusable và cần rebuild.

Nếu bảng có global index, cần đánh giá UPDATE GLOBAL INDEXES. Exchange partition không tự bảo đảm mọi global index luôn usable trong mọi trường hợp.

### 9.6. Kiểm tra sau exchange

~~~sql
SELECT COUNT(*)
FROM sales_archive_stage;

SELECT COUNT(*)
FROM sales_lifecycle PARTITION (p2025_01);
~~~

Đối chiếu số lượng và dữ liệu mẫu trước khi export hoặc purge. Sau khi xác nhận archive đã an toàn, có thể bỏ partition rỗng nếu chính sách cần:

~~~sql
ALTER TABLE sales_lifecycle
DROP PARTITION p2025_01
UPDATE INDEXES;
~~~

Nếu muốn giữ partition để nạp lại hoặc duy trì cấu trúc, có thể giữ partition rỗng.

## 10. Archive sang tablespace hoặc hệ thống lưu trữ khác

Sau khi exchange partition thành bảng archive, có thể:

- Chuyển bảng sang archive tablespace.
- Dùng compression phù hợp với storage.
- Export bằng Data Pump.
- Chuyển tablespace bằng transportable tablespaces nếu kiến trúc và điều kiện phù hợp.
- Đưa bản export sang object storage hoặc hệ thống archive doanh nghiệp.

Ví dụ chuyển bảng archive sang tablespace:

~~~sql
ALTER TABLE sales_archive_stage
MOVE TABLESPACE archive_ts;
~~~

Nếu muốn dùng compression, lựa chọn cú pháp và mức nén theo loại storage, edition và license. Hybrid Columnar Compression phụ thuộc nền tảng lưu trữ được hỗ trợ; không giả định có thể dùng trên mọi storage.

### 10.1. Archive phải có metadata

Một archive hữu ích cần lưu:

- Tên bảng nguồn và partition.
- Lower/upper bound của partition.
- Thời điểm archive.
- Số row và checksum/đối soát nếu quy trình yêu cầu.
- Phiên bản schema và mapping cột.
- Nơi lưu bản export hoặc tablespace.
- Retention của chính archive.
- Quy trình phục hồi và người có quyền thực hiện.

Chỉ có file dump không có metadata sẽ làm việc tìm và khôi phục dữ liệu khó hơn.

## 11. Xử lý index khi bảo trì partition

Partition maintenance có thể ảnh hưởng index. Cần phân biệt local và global indexes.

### 11.1. Local index

Local index có partition tương ứng với table partition. Khi drop/truncate table partition, local index partition tương ứng được drop/truncate cùng thao tác.

Đây là lý do local indexes thường thuận tiện cho bảng có retention theo thời gian.

### 11.2. Global index

Global index có thể tham chiếu row ở nhiều table partitions. Khi drop/truncate/exchange partition, Oracle phải xử lý các entry liên quan để index không trỏ sai hoặc mất khả năng sử dụng.

Ví dụ:

~~~sql
ALTER TABLE sales_lifecycle
DROP PARTITION p2025_01
UPDATE INDEXES;
~~~

UPDATE INDEXES yêu cầu Oracle duy trì index trong thao tác. Nếu bỏ qua, global index hoặc index partitions có thể bị đánh dấu UNUSABLE và phải rebuild.

### 11.3. Asynchronous global index maintenance

Oracle 19c hỗ trợ asynchronous global index maintenance cho DROP PARTITION và TRUNCATE PARTITION trong các trường hợp được hỗ trợ. Với heap-organized tables, thao tác có thể chủ yếu cập nhật metadata và việc dọn entry mồ côi được thực hiện sau.

Các giới hạn cần chú ý gồm loại bảng, object types, domain indexes và các điều kiện khác. Oracle có job hệ thống để dọn global indexes deferred; không tự ý xóa job đó.

Ngay cả khi cơ chế bất đồng bộ được dùng, vẫn nên ghi rõ UPDATE INDEXES theo hướng dẫn Oracle và kiểm tra trạng thái index sau thao tác. UPDATE INDEXES không có nghĩa chi phí bằng không: duy trì index đồng bộ có thể kéo dài DDL và tạo redo/undo.

### 11.4. Kiểm tra index sau maintenance

~~~sql
SELECT index_name, status
FROM user_indexes
WHERE table_name = 'SALES_LIFECYCLE';
~~~

Partitioned index:

~~~sql
SELECT index_name, partition_name, status
FROM user_ind_partitions
WHERE index_name IN (
    SELECT index_name
    FROM user_indexes
    WHERE table_name = 'SALES_LIFECYCLE'
)
ORDER BY index_name, partition_position;
~~~

Nếu có index partition UNUSABLE, cần xác định đúng phạm vi và rebuild theo chính sách trước khi workload phụ thuộc index tiếp tục.

## 12. Foreign key và dữ liệu liên quan

Đây là một trong những điểm dễ làm purge thất bại.

### 12.1. Parent và child

Giả sử:

- SALES là bảng parent chứa giao dịch.
- SALE_LINES là bảng child chứa chi tiết giao dịch.
- SALE_LINES.SALE_ID tham chiếu SALES.SALE_ID.

Nếu muốn drop partition cũ của SALES trong khi row child vẫn tham chiếu tới row parent, Oracle có thể không cho phép thao tác do referential integrity.

DROP/TRUNCATE PARTITION là DDL, không tương đương DELETE từng row. Không giả định ON DELETE CASCADE sẽ tự chạy khi drop partition.

### 12.2. Thứ tự purge

Một quy trình có thể:

1. Archive parent và child theo cùng kỳ retention.
2. Kiểm tra số lượng row và quan hệ khóa ngoại trong archive.
3. Xóa child rows/partitions theo chính sách.
4. Xóa parent rows/partitions.
5. Kiểm tra constraints và index.

Nếu bảng child cũng partition theo thời gian, cần xác định cách đồng bộ ranh giới và thứ tự purge. Nếu partition theo REFERENCE partitioning, Oracle có các quy tắc cascade và giới hạn riêng; không áp dụng cú pháp của bảng RANGE thông thường một cách máy móc.

### 12.3. DELETE và ON DELETE CASCADE

Nếu cần xóa row theo từng bản ghi:

~~~sql
DELETE FROM sales
WHERE sale_date < :cutoff_date;
~~~

DELETE tuân thủ foreign key và có thể kích hoạt ON DELETE CASCADE. Nó cũng chạy DELETE triggers và tạo undo/redo cho row changes.

Đối với partition lớn, có thể archive rồi dùng DDL partition maintenance nếu đã xử lý quan hệ. Nếu cần cascade hoặc trigger semantics, DELETE có thể là lựa chọn phù hợp dù chậm hơn.

### 12.4. Không disable constraint tùy tiện

Một số quy trình partition maintenance có thể yêu cầu disable/re-enable constraint. Trước khi làm:

- Kiểm tra có row child còn tham chiếu dữ liệu sắp xóa không.
- Bảo đảm constraint được enable và validate lại.
- Không mở lại workload trong khi constraint chưa được khôi phục.
- Ghi nhận trạng thái constraint trước/sau.

Nếu có dữ liệu tham chiếu còn tồn tại, việc disable constraint rồi drop partition có thể để lại orphan rows. Phải giải quyết dữ liệu con trước khi xác nhận hoàn tất.

## 13. DELETE theo batch khi bảng không partition

Không phải mọi bảng đều có partitioning. Với bảng không partition hoặc chỉ cần xóa một phần dữ liệu, có thể dùng DELETE theo batch.

### 13.1. Vì sao không nên xóa hàng triệu row trong một câu?

Một DELETE lớn có thể:

- Tạo lượng undo và redo lớn.
- Giữ row locks trong thời gian dài.
- Tăng áp lực undo tablespace.
- Làm transaction rollback rất lâu nếu có lỗi.
- Tạo tải cho index, foreign key và trigger.
- Ảnh hưởng replication, standby và backup window.

Batch delete chia công việc thành các transaction nhỏ hơn. Đổi lại, mỗi batch có thể commit độc lập; quy trình phải có khả năng chạy lại an toàn.

### 13.2. Ví dụ PL/SQL xóa theo batch ROWID

~~~sql
DECLARE
    l_deleted PLS_INTEGER;
BEGIN
    LOOP
        DELETE FROM sales_nonpartitioned
        WHERE ROWID IN (
            SELECT rid
            FROM (
                SELECT ROWID AS rid
                FROM sales_nonpartitioned
                WHERE sale_date < DATE '2020-01-01'
                ORDER BY sale_date
            )
            WHERE ROWNUM <= 10000
        );

        l_deleted := SQL%ROWCOUNT;
        COMMIT;

        EXIT WHEN l_deleted = 0;
    END LOOP;
END;
/
~~~

Ví dụ dùng 10.000 row mỗi batch; kích thước batch phải được đo theo workload và dung lượng undo. Điều kiện phải ổn định và có index phù hợp nếu cần. Nếu có row được thêm vào vùng cutoff trong khi job đang chạy, quy trình cần định nghĩa có xử lý row mới đó hay không.

### 13.3. Batch delete phải restartable

Vì mỗi batch COMMIT riêng:

- Job có thể dừng sau một số batch.
- Lần chạy lại phải tiếp tục mà không gây lỗi hoặc xóa nhầm dữ liệu mới.
- Ghi lại cutoff, batch start/end, số row xóa và trạng thái.
- Có thể dùng key range hoặc partition/key boundary để checkpoint.

Không ghi nhận “job thành công” chỉ vì block cuối cùng không lỗi; phải đối soát tổng số row còn lại và số row đã xóa.

### 13.4. DELETE theo ROWID không phải giải pháp cho mọi bảng

Nếu predicate có index tốt và số row cần xóa ít, DELETE trực tiếp có thể đủ:

~~~sql
DELETE FROM sales_nonpartitioned
WHERE sale_date < :cutoff_date;
~~~

Nếu cần xóa phần lớn dữ liệu, archive hoặc CTAS/partition exchange/redefinition có thể phù hợp hơn. Quyết định phụ thuộc trigger, FK, index, downtime, khả năng rollback và dung lượng.

## 14. So sánh các chiến lược xóa dữ liệu cũ

| Chiến lược | Phù hợp | Chi phí/rủi ro |
| --- | --- | --- |
| DELETE theo predicate | Xóa một phần nhỏ, cần trigger/FK semantics | Undo/redo, row locks, index maintenance |
| DELETE theo batch | Bảng không partition, lượng lớn nhưng cần chia transaction | Nhiều commit, phải checkpoint/restart |
| TRUNCATE PARTITION | Xóa toàn bộ row trong partition nhưng giữ cấu trúc | DDL không rollback; FK và index cần kiểm tra |
| DROP PARTITION | Xóa hẳn partition đã hết retention | DDL không rollback, không vào recycle bin |
| EXCHANGE PARTITION | Archive hoặc chuyển dữ liệu partition thành bảng riêng | Yêu cầu cấu trúc tương thích, validation và index handling |
| MOVE PARTITION | Chuyển partition sang tablespace/storage khác | I/O, index maintenance, lock và dung lượng |
| Data Pump/export | Tạo bản archive độc lập | Cần quản lý dump, metadata, checksum và restore |
| Materialized/summary data | Giữ số liệu tổng hợp sau khi xóa chi tiết | Phải xác định yêu cầu truy vấn và audit |

Không có một cách xóa phù hợp cho mọi bảng. Hãy chọn theo kích thước dữ liệu, retention, quan hệ khóa ngoại, yêu cầu trigger, thời gian bảo trì và recovery.

## 15. Chuyển partition sang storage rẻ hơn và nén dữ liệu

Partition cũ có thể vẫn cần query nhưng ít được truy cập. Khi đó, move partition sang tablespace khác hoặc compression có thể giảm chi phí.

### 15.1. MOVE PARTITION

~~~sql
ALTER TABLE sales_lifecycle
MOVE PARTITION p2025_01
TABLESPACE archive_ts
UPDATE INDEXES;
~~~

Lệnh di chuyển partition sang tablespace archive. UPDATE INDEXES yêu cầu Oracle duy trì index theo thao tác được hỗ trợ. Nếu không duy trì index, một số index hoặc index partition có thể cần rebuild.

### 15.2. ONLINE MOVE

~~~sql
ALTER TABLE sales_lifecycle
MOVE PARTITION p2025_01
TABLESPACE archive_ts
ONLINE
UPDATE INDEXES;
~~~

ONLINE MOVE cho phép DML đồng thời theo các điều kiện hỗ trợ của Oracle. Không có nghĩa thao tác không cần khóa hoặc không tiêu thụ thêm tài nguyên. Kiểm tra giới hạn phiên bản, loại bảng, LOB, index và edition trước khi dùng.

### 15.3. Compression

Oracle hỗ trợ nhiều dạng table compression. Ví dụ cú pháp có thể dùng khi storage/edition/license hỗ trợ:

~~~sql
ALTER TABLE sales_lifecycle
MOVE PARTITION p2025_01
TABLESPACE archive_ts
COMPRESS FOR QUERY LOW
UPDATE INDEXES;
~~~

Hybrid Columnar Compression phụ thuộc nền tảng lưu trữ hỗ trợ. Các mức compression và quyền sử dụng tính năng phải được kiểm tra theo Oracle Licensing Information và hợp đồng triển khai. Không sao chép cú pháp compression từ Exadata hoặc storage appliance sang môi trường không hỗ trợ.

### 15.4. MOVE không phải archive

MOVE chỉ thay đổi vị trí/lưu trữ của partition bên trong database. Dữ liệu vẫn ở trong bảng logic. Nếu yêu cầu lưu trữ độc lập hoặc xóa khỏi hệ thống giao dịch, cần exchange/export/archive rồi purge theo chính sách.

## 16. Heat Map và Automatic Data Optimization (ADO)

Oracle cung cấp Heat Map và Automatic Data Optimization để hỗ trợ ILM.

### 16.1. Heat Map

Heat Map theo dõi thông tin truy cập và sửa đổi dữ liệu. ADO có thể dùng thông tin đó để đánh giá policy nén hoặc di chuyển dữ liệu.

Để sử dụng ADO, cần bật Heat Map ở cấp hệ thống theo cấu hình và quyền DBA:

~~~sql
ALTER SYSTEM SET HEAT_MAP = ON SCOPE = BOTH;
~~~

Việc bật tham số và quyền thực thi cần được DBA quản lý. Kiểm tra cấu hình:

~~~sql
SHOW PARAMETER heat_map;
~~~

### 16.2. ADO policy

Ví dụ policy nén segment sau sáu tháng không được truy cập:

~~~sql
ALTER TABLE sales_lifecycle ILM ADD POLICY
    COLUMN STORE COMPRESS FOR ARCHIVE HIGH
    SEGMENT
    AFTER 6 MONTHS OF NO ACCESS;
~~~

Đây là ví dụ minh họa theo cú pháp ADO của Oracle. Compression level và storage phải được hỗ trợ. HCC phụ thuộc nền tảng lưu trữ; cần xác nhận licensing.

### 16.3. ADO không tự động là purge policy

Các policy compression/tiering giúp thay đổi cách lưu trữ hoặc vị trí dữ liệu khi điều kiện được đáp ứng. Chúng không thay thế retention policy và không có nghĩa Oracle tự xóa mọi row hết hạn.

Purge vẫn cần quy trình được kiểm soát:

- Tính cutoff.
- Kiểm tra legal hold.
- Archive hoặc xác nhận không cần archive.
- Kiểm tra foreign key/index.
- Thực hiện partition DDL hoặc batch DELETE.
- Đối soát và ghi audit.

### 16.4. Theo dõi policy

Oracle có các data dictionary views và package DBMS_ILM để quản lý, đánh giá hoặc thực thi ADO tasks. DBA cần xem trạng thái policy, kết quả thực thi và quyền cần thiết trước khi tự động hóa.

Không tạo ADO policy rồi giả định nó đã chạy. Phải theo dõi lịch thực thi, lỗi, dung lượng và kết quả nén/di chuyển.

## 17. Quản lý metadata và theo dõi partition

### 17.1. USER_TAB_PARTITIONS

~~~sql
SELECT table_name,
       partition_name,
       partition_position,
       tablespace_name,
       num_rows,
       last_analyzed
FROM user_tab_partitions
WHERE table_name = 'SALES_LIFECYCLE'
ORDER BY partition_position;
~~~

View cho biết các partition của bảng hiện tại. HIGH_VALUE cũng có trong metadata nhưng kiểu LONG khiến một số công cụ SQL không thể xử lý như cột VARCHAR2 thông thường.

### 17.2. USER_PART_TABLES và USER_PART_KEY_COLUMNS

~~~sql
SELECT table_name,
       partitioning_type,
       subpartitioning_type,
       partition_count,
       interval
FROM user_part_tables
WHERE table_name = 'SALES_LIFECYCLE';
~~~

~~~sql
SELECT name,
       object_type,
       column_name,
       column_position
FROM user_part_key_columns
WHERE name = 'SALES_LIFECYCLE'
ORDER BY column_position;
~~~

Các view này giúp kiểm tra phương pháp partition và partition key.

### 17.3. Dung lượng segment theo partition

~~~sql
SELECT segment_name,
       partition_name,
       segment_type,
       tablespace_name,
       bytes,
       blocks
FROM user_segments
WHERE segment_name = 'SALES_LIFECYCLE'
ORDER BY partition_name;
~~~

Số liệu segment giúp theo dõi partition nào đang chiếm nhiều storage. Không suy ra số row chính xác chỉ từ dung lượng segment vì compression, row length, block fullness và index đều ảnh hưởng.

### 17.4. Index partitions

~~~sql
SELECT index_name,
       partition_name,
       status,
       tablespace_name
FROM user_ind_partitions
WHERE index_name LIKE 'IX_SALES%'
ORDER BY index_name, partition_position;
~~~

Sau partition maintenance, kiểm tra index partition status để phát hiện UNUSABLE.

## 18. Tự động hóa retention bằng lịch chạy có kiểm soát

Một job retention có thể chạy hàng tháng, nhưng không nên chỉ dựa trên ngày hiện tại rồi DROP partition ngay.

Quy trình nên có các bước:

1. Tính cutoff theo timezone/calendar đã thống nhất.
2. Lấy danh sách partition có upper bound nhỏ hơn cutoff.
3. Kiểm tra legal hold và ngoại lệ.
4. Xác nhận archive/export đã hoàn tất và đối soát.
5. Kiểm tra foreign key và partition phụ thuộc.
6. Kiểm tra local/global index maintenance.
7. Tạo kế hoạch DDL cho partition cụ thể.
8. Chạy trong maintenance window hoặc cơ chế concurrency đã được phê duyệt.
9. Kiểm tra trạng thái partition, index và số liệu còn lại.
10. Ghi audit kết quả.

### 18.1. Không dựng tên partition chỉ bằng chuỗi ngày

Tên partition có thể do người dùng đặt hoặc Oracle tự sinh. Với interval partitioning, tên có thể có dạng SYS_P...; do đó job cần tra dictionary metadata thay vì tự giả định tên P_YYYY_MM.

### 18.2. Chạy DDL theo từng partition

Đối với purge quan trọng, thường dễ kiểm soát hơn nếu mỗi partition là một bước riêng:

- Ghi log partition mục tiêu.
- Kiểm tra archive.
- Thực hiện DDL.
- Xác nhận partition đã biến mất hoặc rỗng theo mục tiêu.
- Kiểm tra index.
- Đánh dấu hoàn tất.

Nếu một partition lỗi, job có thể dừng và tiếp tục từ partition chưa xử lý, thay vì xóa nhiều kỳ trong một thao tác khó đối soát.

### 18.3. Không chạy đồng thời hai job trên cùng partition

Job archive, move, exchange và purge không nên tranh chấp cùng một partition. Dùng scheduler lock, control table hoặc cơ chế điều phối để bảo đảm chỉ một workflow quản lý một partition tại một thời điểm.

## 19. Ảnh hưởng tới backup, standby và hệ thống downstream

Trước khi xóa dữ liệu cũ, phải xác định các bản sao dữ liệu khác:

- RMAN backup và recovery window.
- Data Guard standby và redo apply.
- GoldenGate hoặc CDC.
- Materialized views và refresh logs.
- Data warehouse, lake hoặc hệ thống báo cáo.
- Export files và archive storage.

Một partition đã drop khỏi primary có thể vẫn còn trong backup hoặc downstream. Nếu retention là yêu cầu xóa dữ liệu cá nhân hoặc dữ liệu nhạy cảm, cần xem cả các bản sao và quy trình hết hạn backup; xóa trên bảng chính chưa chắc đã xóa khỏi toàn bộ hệ sinh thái.

Ngược lại, nếu archive là yêu cầu pháp lý, cần bảo đảm bản archive tồn tại và có thể khôi phục trước khi xóa bản online.

## 20. Những lỗi và tình huống thường gặp

| Lỗi/hiện tượng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| ORA-14400 | Giá trị partition key không map được vào partition hiện có | Tạo partition tương lai, kiểm tra range bounds hoặc interval |
| ORA-14402 | UPDATE partition key làm row phải chuyển partition trong khi row movement bị disable | Tránh update partition key hoặc ENABLE ROW MOVEMENT có kiểm soát |
| ORA-02266 | Parent key được tham chiếu bởi foreign key đang enable | Xử lý child rows/constraints theo thứ tự và validate lại |
| ORA-01502 | Index/index partition unusable sau partition maintenance | Kiểm tra index status, dùng UPDATE INDEXES hoặc rebuild |
| ORA-14083 | Thử DROP partition cuối cùng của bảng | Không thể drop partition duy nhất; xử lý cấp bảng |
| Partition drop thành công nhưng không tìm thấy trong recycle bin | DROP PARTITION không đưa partition vào recycle bin | Archive/backup trước khi drop; chuẩn bị phương án restore |
| EXCHANGE PARTITION thất bại | Bảng staging không tương thích hoặc row không nằm trong partition range | Kiểm tra cấu trúc, index, constraint và dùng WITH VALIDATION |
| Index global bị unusable | Không duy trì global index trong partition DDL | UPDATE INDEXES/UPDATE GLOBAL INDEXES theo cú pháp hỗ trợ hoặc rebuild |
| Archive thiếu row | Exchange/export chưa đối soát hoặc validation bị bỏ qua sai cách | Đối chiếu count, key range, checksum và metadata |
| Purge chậm | DELETE quá nhiều row, index/FK/trigger và undo/redo lớn | Dùng partition maintenance nếu nghiệp vụ cho phép |
| Job retention xóa nhầm dữ liệu | Cutoff, timezone, legal hold hoặc partition name sai | Dry-run, approval, audit, kiểm tra HIGH_VALUE và archive |
| ADO policy không chạy | Heat Map chưa bật, policy chưa đủ điều kiện hoặc job lỗi | Kiểm tra HEAT_MAP, policy metadata và DBMS_ILM status |
| Archive table không thể truy vấn như mong muốn | Schema version hoặc index/constraint khác với bảng nguồn | Lưu metadata schema, kiểm thử restore và query |

## 21. Bộ thực hành tự chứa

Các bài lab dùng bảng riêng, không thao tác trên dữ liệu ứng dụng.

### 21.1. Tạo bảng partition theo tháng

~~~sql
CREATE TABLE sales_lifecycle_lab (
    sale_id NUMBER NOT NULL,
    sale_date DATE NOT NULL,
    customer_id NUMBER NOT NULL,
    amount NUMBER(12,2) NOT NULL
)
PARTITION BY RANGE (sale_date)
(
    PARTITION p2025_01 VALUES LESS THAN (DATE '2025-02-01'),
    PARTITION p2025_02 VALUES LESS THAN (DATE '2025-03-01'),
    PARTITION p2025_03 VALUES LESS THAN (DATE '2025-04-01')
);

CREATE INDEX ix_sales_lifecycle_lab_customer
ON sales_lifecycle_lab(customer_id, sale_date)
LOCAL;
~~~

### 21.2. Nạp dữ liệu mẫu

~~~sql
INSERT INTO sales_lifecycle_lab VALUES
(1, DATE '2025-01-10', 101, 100);

INSERT INTO sales_lifecycle_lab VALUES
(2, DATE '2025-02-15', 102, 200);

INSERT INTO sales_lifecycle_lab VALUES
(3, DATE '2025-03-20', 103, 300);

COMMIT;
~~~

### 21.3. Kiểm tra partition pruning

~~~sql
EXPLAIN PLAN FOR
SELECT SUM(amount)
FROM sales_lifecycle_lab
WHERE sale_date >= DATE '2025-02-01'
  AND sale_date < DATE '2025-03-01';

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

Quan sát partition access trong execution plan. Kết quả hiển thị phụ thuộc statistics và môi trường.

### 21.4. Archive bằng EXCHANGE PARTITION

Tạo bảng staging có cấu trúc tương thích:

~~~sql
CREATE TABLE sales_archive_lab (
    sale_id NUMBER NOT NULL,
    sale_date DATE NOT NULL,
    customer_id NUMBER NOT NULL,
    amount NUMBER(12,2) NOT NULL
);

CREATE INDEX ix_sales_archive_lab_customer
ON sales_archive_lab(customer_id, sale_date);
~~~

Exchange partition tháng 1:

~~~sql
ALTER TABLE sales_lifecycle_lab
EXCHANGE PARTITION p2025_01
WITH TABLE sales_archive_lab
INCLUDING INDEXES
WITH VALIDATION;
~~~

Đối chiếu:

~~~sql
SELECT COUNT(*) FROM sales_archive_lab;
SELECT COUNT(*) FROM sales_lifecycle_lab PARTITION (p2025_01);
~~~

Bảng archive nhận dữ liệu tháng 1; partition tháng 1 trong bảng nguồn rỗng nếu staging ban đầu rỗng.

### 21.5. Kiểm tra index và drop partition rỗng

~~~sql
SELECT index_name, status
FROM user_indexes
WHERE table_name = 'SALES_LIFECYCLE_LAB';

ALTER TABLE sales_lifecycle_lab
DROP PARTITION p2025_01
UPDATE INDEXES;
~~~

Kiểm tra partition metadata:

~~~sql
SELECT partition_name, partition_position, num_rows
FROM user_tab_partitions
WHERE table_name = 'SALES_LIFECYCLE_LAB'
ORDER BY partition_position;
~~~

### 21.6. Thử TRUNCATE PARTITION

~~~sql
ALTER TABLE sales_lifecycle_lab
TRUNCATE PARTITION p2025_02
UPDATE INDEXES;
~~~

Partition tháng 2 vẫn tồn tại nhưng không còn row. Đây là điểm khác biệt với DROP PARTITION.

### 21.7. Thử interval partitioning

~~~sql
CREATE TABLE sales_interval_lab (
    sale_id NUMBER,
    sale_date DATE NOT NULL,
    amount NUMBER(12,2)
)
PARTITION BY RANGE (sale_date)
INTERVAL (NUMTOYMINTERVAL(1, 'MONTH'))
(
    PARTITION p_before_2025
    VALUES LESS THAN (DATE '2025-01-01')
);

INSERT INTO sales_interval_lab
VALUES (1, DATE '2025-04-10', 500);

COMMIT;
~~~

Kiểm tra partition do Oracle tạo:

~~~sql
SELECT partition_name, partition_position, tablespace_name
FROM user_tab_partitions
WHERE table_name = 'SALES_INTERVAL_LAB'
ORDER BY partition_position;
~~~

### 21.8. Dọn lab

~~~sql
DROP TABLE sales_archive_lab PURGE;
DROP TABLE sales_lifecycle_lab PURGE;
DROP TABLE sales_interval_lab PURGE;
~~~

DDL có implicit commit. Chỉ chạy sau khi đã hoàn thành bài thực hành.

## 22. Checklist trước khi archive hoặc purge

1. **Retention đã được phê duyệt chưa?** Xác định cutoff, timezone, loại ngày và thời hạn lưu trữ.
2. **Có legal hold hoặc ngoại lệ không?** Loại các hồ sơ cần giữ khỏi danh sách purge.
3. **Đã xác định đúng partition chưa?** Kiểm tra partition name, high value, partition position và row count.
4. **Dữ liệu đã được archive chưa?** Đối chiếu số row, key range, checksum và nơi lưu trữ.
5. **Có thể phục hồi archive không?** Kiểm tra metadata, schema version, quyền và quy trình restore.
6. **Có foreign key hoặc reference partitioning không?** Xử lý child data và constraints đúng thứ tự.
7. **Local/global indexes sẽ ra sao?** Chọn UPDATE INDEXES hoặc kế hoạch rebuild.
8. **Có downstream systems không?** Kiểm tra backup, standby, CDC, materialized views và báo cáo.
9. **DDL có implicit commit không?** Chuẩn bị transaction boundary và phê duyệt.
10. **Có dùng DROP hay TRUNCATE?** Drop bỏ partition metadata; truncate giữ partition rỗng.
11. **Có cần EXCHANGE PARTITION?** Chuẩn bị bảng staging tương thích và index tương ứng.
12. **Có dùng WITHOUT VALIDATION không?** Chỉ khi đã bảo đảm row mapping bằng quy trình khác.
13. **Có đủ storage và I/O không?** Tính đến archive, move, compression, global index maintenance và redo.
14. **Đã kiểm tra partition/index sau thao tác chưa?** Xác nhận trạng thái usable và dữ liệu còn lại.
15. **Đã ghi audit chưa?** Lưu người thực hiện, thời điểm, cutoff, partition, row count và kết quả.

## 23. Câu hỏi tự kiểm tra

**Câu 1.** ILM quản lý dữ liệu theo những giai đoạn nào?

**Câu 2.** Vì sao phải định nghĩa retention trước khi viết lệnh DROP PARTITION?

**Câu 3.** Partitioning giúp purge dữ liệu cũ nhanh hơn DELETE theo row như thế nào?

**Câu 4.** Với RANGE partition, VALUES LESS THAN có bao gồm cận trên không?

**Câu 5.** Vì sao nên dùng khoảng ngày nửa mở trong WHERE?

**Câu 6.** Interval partitioning tự động làm gì khi có row vượt transition point?

**Câu 7.** DROP PARTITION và TRUNCATE PARTITION khác nhau thế nào?

**Câu 8.** Partition đã DROP có vào recycle bin không?

**Câu 9.** Vì sao không thể ROLLBACK DROP PARTITION?

**Câu 10.** EXCHANGE PARTITION có sao chép từng row không?

**Câu 11.** WITH VALIDATION và WITHOUT VALIDATION khác nhau ra sao?

**Câu 12.** Vì sao phải kiểm tra global index sau partition maintenance?

**Câu 13.** ON DELETE CASCADE có tự chạy khi DROP PARTITION không?

**Câu 14.** Khi nào nên dùng DELETE theo batch thay cho partition DDL?

**Câu 15.** Heat Map và ADO có tự động xóa mọi dữ liệu hết retention không?

<details>
<summary>Gợi ý đáp án</summary>

1. HOT, WARM, ARCHIVE và PURGE là các giai đoạn minh họa; chính sách thực tế tùy nghiệp vụ.
2. Vì purge là thao tác phá hủy dữ liệu; cần biết dữ liệu nào hết hạn, có legal hold không và đã archive chưa.
3. DDL partition thao tác trên segment/metadata của cả nhóm row thay vì xử lý từng row và từng index entry.
4. Không. LESS THAN dùng cận trên không bao gồm.
5. Để bao phủ toàn bộ thời gian trong ngày/tháng mà không bỏ sót giá trị có thành phần giờ.
6. Tạo interval partition phù hợp để chứa row.
7. DROP xóa cả partition metadata và dữ liệu; TRUNCATE xóa row nhưng giữ partition.
8. Không. Partition bị drop không được đưa vào recycle bin.
9. Vì DROP PARTITION là DDL và có implicit commit.
10. Không theo cách copy từng row; EXCHANGE trao đổi segment/metadata khi cấu trúc đáp ứng yêu cầu.
11. WITH VALIDATION kiểm tra row có thuộc partition range; WITHOUT VALIDATION bỏ qua bước kiểm tra.
12. Vì global index có thể bị invalid/unusable nếu không được duy trì trong thao tác.
13. Không. ON DELETE CASCADE áp dụng cho DELETE DML, không tự chạy như xóa từng row khi drop partition.
14. Khi bảng không partition, chỉ xóa một phần row, hoặc cần trigger/FK semantics.
15. Không. ADO chủ yếu tự động hóa compression/tiering; purge cần retention workflow riêng.

</details>

## 24. Tài liệu Oracle chính thức

1. [Oracle Database 19c VLDB and Partitioning Guide — Introduction to Partitioning](https://docs.oracle.com/en/database/oracle/oracle-database/19/vldbg/partition-intro.html): partitioning, partition pruning, ILM và yêu cầu Oracle Partitioning option.
2. [Oracle Database 19c VLDB and Partitioning Guide — Partition Administration](https://docs.oracle.com/en/database/oracle/oracle-database/19/vldbg/partition-admin.html): tạo, quản lý và bảo trì partition.
3. [Oracle Database 19c VLDB and Partitioning Guide — Maintenance Operations for Partitioned Tables and Indexes](https://docs.oracle.com/en/database/oracle/oracle-database/19/vldbg/maintenance-partition-tables-indexes.html): DROP, TRUNCATE, EXCHANGE, UPDATE INDEXES, global index maintenance và referential integrity.
4. [Oracle Database 19c VLDB and Partitioning Guide — Using Partitioning in a Data Warehouse Environment](https://docs.oracle.com/en/database/oracle/oracle-database/19/vldbg/partition-warehouse.html): partition exchange load và xóa dữ liệu cũ trong data warehouse.
5. [Oracle Database 19c VLDB and Partitioning Guide — Using Partitioning in an OLTP Environment](https://docs.oracle.com/en/database/oracle/oracle-database/19/vldbg/partition-oltp.html): ảnh hưởng của partition maintenance tới DML và availability.
6. [Oracle Database 19c SQL Language Reference — CREATE TABLE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/CREATE-TABLE.html): RANGE, INTERVAL và table partitioning clauses.
7. [Oracle Database 19c SQL Language Reference — ALTER TABLE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/ALTER-TABLE.html): DROP/TRUNCATE/EXCHANGE/MOVE partition và các tùy chọn index.
8. [Oracle Database 19c Administrator's Guide — Managing Tables](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/managing-tables.html): compression, Heat Map và Automatic Data Optimization.
9. [Oracle Database 19c PL/SQL Packages and Types Reference — DBMS_ILM](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_ILM.html): quản lý và thực thi ADO policies.
10. [Oracle Database 19c Licensing Information](https://docs.oracle.com/en/database/oracle/oracle-database/19/dblic/Licensing-Information.html): điều kiện license cho các tùy chọn và tính năng liên quan.

**Nguyên tắc cần nhớ:** Xây dựng retention policy trước khi xóa dữ liệu. Partition theo thời gian giúp archive, move, compress và purge theo nhóm lớn; DROP PARTITION xóa cả partition, TRUNCATE PARTITION giữ partition rỗng, còn EXCHANGE PARTITION chuyển segment dữ liệu sang bảng độc lập để archive. Luôn kiểm tra legal hold, foreign key, local/global index, backup và downstream systems trước DDL. Nếu không thể xóa trọn partition hoặc cần trigger/FK semantics, dùng DELETE có kiểm soát, có thể chia batch và checkpoint. Heat Map/ADO hỗ trợ nén và phân tầng storage, nhưng không thay thế quy trình purge được phê duyệt.
