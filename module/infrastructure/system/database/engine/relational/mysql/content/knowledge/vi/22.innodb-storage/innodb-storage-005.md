# Page split, page merge và phân mảnh khi chèn/cập nhật

## Mục tiêu bài học

Sau bài này, bạn có thể:

- Mô tả cách InnoDB tổ chức dữ liệu và index trong các B-tree page.
- Giải thích vì sao INSERT hoặc UPDATE có thể làm một page bị split.
- Phân biệt page split, page merge, page reorganization và fragmentation.
- Dự đoán ảnh hưởng của khóa tuần tự, khóa ngẫu nhiên và secondary index đến cách phân bố page.
- Giải thích MERGE_THRESHOLD và innodb_fill_factor, cũng như phạm vi tác động của từng thiết lập.
- Theo dõi số lần split/merge bằng INNODB_METRICS.
- Nhận biết khi nào nên rebuild hoặc OPTIMIZE TABLE để thu hồi không gian.
- Thiết kế khóa và quy trình ghi để hạn chế chi phí bảo trì B-tree.

InnoDB lưu dữ liệu và index trong các page thuộc cấu trúc B-tree. Khi thêm một bản ghi vào page đã gần đầy, InnoDB có thể phải chia page thành các page nhỏ hơn và cập nhật node cha. Khi xóa dữ liệu hoặc làm một khóa ngắn đi, page có thể trở nên thưa; InnoDB có thể thử gộp nó với page lân cận. Các thay đổi này duy trì cấu trúc index nhưng cũng tạo thêm công việc ghi, cấp phát page và quản lý không gian.

Page split và page merge là hoạt động bình thường của B-tree. Chúng trở thành vấn đề hiệu năng khi xảy ra thường xuyên, tạo nhiều page thưa hoặc làm thứ tự vật lý của page kém thuận lợi cho truy cập. Muốn chẩn đoán đúng, cần hiểu cách INSERT và UPDATE tác động lên clustered index, secondary index và không gian của tablespace.

## 1. Page và B-tree của InnoDB

### 1.1. Page là đơn vị lưu trữ cơ bản

InnoDB chia dữ liệu bảng và index thành các page. Kích thước page mặc định là 16 KB; giá trị thực tế phụ thuộc innodb_page_size được chọn khi khởi tạo instance. Page size của một instance không thể thay đổi sau khi instance đã được khởi tạo.

Một B-tree index gồm nhiều tầng:

- Root page là điểm bắt đầu tìm kiếm.
- Non-leaf page chứa khóa phân cách và con trỏ đến page ở tầng dưới.
- Leaf page chứa bản ghi index. Với clustered index, leaf page chứa dữ liệu hàng; với secondary index, leaf page chứa khóa secondary cùng khóa chính của hàng.

Các page lá được sắp theo thứ tự khóa logic. B-tree giữ cho đường đi từ root đến mọi leaf có độ sâu cân bằng, giúp tìm kiếm theo khóa không phải quét toàn bộ bảng.

### 1.2. Clustered index và secondary index

Mỗi bảng InnoDB có một clustered index. Thông thường, PRIMARY KEY là clustered index và các hàng được tổ chức theo khóa chính.

Nếu không khai báo PRIMARY KEY, InnoDB chọn một UNIQUE index có các cột NOT NULL làm clustered index. Nếu không có index phù hợp, InnoDB tạo clustered index ẩn trên row ID.

Secondary index là các index còn lại. Mỗi bản ghi secondary index chứa các cột khóa của index và giá trị khóa chính tương ứng để InnoDB tìm đến hàng trong clustered index.

Ví dụ:

~~~sql
CREATE TABLE order_line (
    order_id BIGINT UNSIGNED NOT NULL,
    line_no INT UNSIGNED NOT NULL,
    product_id BIGINT UNSIGNED NOT NULL,
    quantity INT UNSIGNED NOT NULL,
    unit_price DECIMAL(12, 2) NOT NULL,
    PRIMARY KEY (order_id, line_no),
    KEY idx_product (product_id)
) ENGINE = InnoDB;
~~~

Trong ví dụ này:

- PRIMARY KEY (order_id, line_no) xác định thứ tự của clustered index.
- idx_product là secondary index.
- Bản ghi của idx_product lưu product_id cùng các cột khóa chính order_id và line_no.

Vì khóa chính xuất hiện trong các secondary index, một PRIMARY KEY dài làm mọi secondary index tốn thêm không gian. Nhiều page hơn đồng nghĩa buffer pool phải quản lý nhiều page hơn và có thể tăng I/O cũng như công việc bảo trì index.

### 1.3. Một bảng có nhiều cây index độc lập

Mỗi index B-tree có tập page riêng và thứ tự khóa riêng. Một INSERT vào bảng có thể cần cập nhật clustered index và tất cả secondary index.

Ví dụ, một hàng mới có id tăng dần nhưng created_at và customer_id phân bố ngẫu nhiên:

- Clustered index có thể thêm bản ghi ở vùng khóa lớn nhất.
- Secondary index theo created_at phải tìm vị trí theo ngày giờ.
- Secondary index theo customer_id phải tìm vị trí theo customer_id.

Do đó, khóa chính tuần tự không loại bỏ page split trong các secondary index có khóa được chèn theo thứ tự ngẫu nhiên.

## 2. Page split là gì?

Page split xảy ra khi một bản ghi cần được chèn vào B-tree page nhưng page không còn đủ chỗ. InnoDB phải phân bố lại các bản ghi trên nhiều page để có chỗ cho bản ghi mới mà vẫn giữ thứ tự index.

Ở mức khái quát, quá trình có thể gồm:

1. Tìm leaf page chứa vị trí khóa cần chèn.
2. Thử chèn bản ghi và tổ chức lại page nếu còn đủ không gian.
3. Nếu page không thể chứa bản ghi, cấp phát page khác và phân chia các bản ghi giữa các page.
4. Cập nhật liên kết page và node cha để cây tiếp tục tìm kiếm đúng.
5. Nếu node cha cũng đầy, việc chia có thể lan lên tầng cao hơn.
6. Nếu root cần chia, InnoDB có thể tạo root mới và làm tăng chiều cao cây.

Không phải mọi INSERT đều gây split. Nếu page còn chỗ, InnoDB chỉ cần chèn bản ghi và cập nhật các cấu trúc liên quan. Page split là thao tác cấu trúc khi không gian của page hiện tại không đủ.

### Page reorganization khác page split

Trước khi cấp page mới, InnoDB có thể tổ chức lại các bản ghi bên trong page để gom các vùng trống rời rạc thành không gian liên tục. Page reorganization vẫn sử dụng page hiện tại; page split cần thêm page và cập nhật cấu trúc cây. Vì vậy, một lần reorganization thành công không đồng nghĩa với một lần split.

### 2.1. Minh họa một leaf page bị chia

Giả sử một leaf page đang chứa các khóa theo thứ tự:

~~~text
Page A
[ 10 | 20 | 30 | 40 | 50 | 60 ]
~~~

Khi cần chèn khóa 35 nhưng page không còn đủ chỗ, InnoDB có thể phân chia dữ liệu thành hai page:

~~~text
Trước:
Page A
[ 10 | 20 | 30 | 40 | 50 | 60 ]

Sau:
Page A                  Page B
[ 10 | 20 | 30 ]        [ 35 | 40 | 50 | 60 ]

Node cha được cập nhật để dẫn đến cả Page A và Page B.
~~~

Đây là mô hình minh họa để hiểu việc phân chia và cập nhật node cha. Cách InnoDB chọn điểm chia và phân bố phần trống phụ thuộc vị trí chèn, kích thước bản ghi và trạng thái page; không nên giả định mọi split đều chia đúng một nửa.

### 2.2. Split có thể lan lên nhiều tầng

Nếu leaf page split, node cha phải nhận thêm thông tin về page mới. Nếu node cha không đủ chỗ, nó cũng có thể split. Quá trình có thể tiếp tục đến root.

Khi root split, cây có thể tăng thêm một tầng. Chiều cao cây lớn hơn không nhất thiết là vấn đề; B-tree được thiết kế để duy trì tìm kiếm hiệu quả khi dữ liệu tăng. Điều cần quan tâm là chi phí phát sinh khi split xảy ra liên tục và mức độ phân mảnh của các page.

### 2.3. Chi phí của page split

Một page split có thể cần:

- Cấp phát page và cập nhật metadata quản lý page.
- Di chuyển hoặc sắp xếp lại một phần bản ghi index.
- Ghi thay đổi lên nhiều page trong buffer pool.
- Cập nhật node cha và các liên kết page.
- Tạo thêm hoạt động redo để bảo đảm khả năng phục hồi.
- Giữ các latch nội bộ trong khi thay đổi cấu trúc B-tree.

Split không đồng nghĩa với việc toàn bộ bảng bị khóa. Tuy nhiên, đây là công việc bổ sung trên đường ghi và có thể làm tăng độ trễ, I/O và tranh chấp nội bộ khi nhiều transaction cùng cập nhật vùng index liên quan.

## 3. Thứ tự INSERT ảnh hưởng đến page split

### 3.1. Chèn khóa tuần tự

Khi khóa tăng dần, bản ghi mới thường được chèn vào vùng cuối của index. Với clustered index có thứ tự tăng hoặc giảm đều, InnoDB có thể giữ các page gần đầy và để lại một phần không gian cho lần chèn hoặc cập nhật tiếp theo.

Tài liệu MySQL 8.4 mô tả rằng InnoDB cố gắng để trống 1/16 page trong clustered index cho tăng trưởng sau này. Với dữ liệu được chèn tuần tự, page thường đạt khoảng 15/16 dung lượng.

Khóa AUTO_INCREMENT thường tạo mẫu chèn tăng dần:

~~~sql
CREATE TABLE event_update_demo (
    event_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    event_time DATETIME NOT NULL,
    event_type SMALLINT UNSIGNED NOT NULL,
    payload VARCHAR(160) NOT NULL,
    PRIMARY KEY (event_id),
    KEY idx_event_time (event_time)
) ENGINE = InnoDB;

INSERT INTO event_update_demo (
    event_id,
    event_time,
    event_type,
    payload
)
VALUES (
    1001,
    '2026-02-15 10:10:00',
    1,
    'initial event'
);
~~~

Các INSERT mới vào clustered index thường đi về phía khóa lớn nhất. Điều này có tính tuần tự và thường tận dụng page locality tốt hơn so với chèn khóa ngẫu nhiên.

Trong workload có rất nhiều transaction đồng thời, vùng cuối của index có thể trở thành điểm nóng vì nhiều luồng ghi cùng truy cập page lân cận. Vì vậy, khóa tuần tự giúp giảm chèn ngẫu nhiên nhưng vẫn cần đo mức tranh chấp thực tế.

### 3.2. Chèn khóa ngẫu nhiên

Nếu khóa chính phân bố ngẫu nhiên, mỗi INSERT có thể đi vào một leaf page khác nhau tùy giá trị khóa. Các page ở nhiều vùng của cây cùng nhận bản ghi mới.

Với clustered index, tài liệu MySQL mô tả page có thể đạt khoảng 1/2 đến 15/16 dung lượng khi bản ghi được chèn theo thứ tự ngẫu nhiên. Đây là khoảng quan sát về cách InnoDB lấp page, không phải cam kết rằng mỗi page split luôn chia đôi.

Hệ quả có thể gồm:

- Page split xảy ra ở nhiều vùng khác nhau của cây.
- Page có nhiều khoảng trống hơn sau các lần phân chia.
- Các page logic liền kề không nhất thiết nằm gần nhau trên thiết bị lưu trữ.
- Buffer pool phải giữ nhiều vùng index đang được ghi.
- Các lần quét theo thứ tự index có thể phải đọc nhiều page hơn.

Ví dụ khóa chính được cấp từ bên ngoài:

~~~sql
CREATE TABLE event_random_demo (
    event_id BIGINT UNSIGNED NOT NULL,
    event_time DATETIME NOT NULL,
    event_type SMALLINT UNSIGNED NOT NULL,
    payload VARCHAR(160) NOT NULL,
    PRIMARY KEY (event_id),
    KEY idx_event_time (event_time)
) ENGINE = InnoDB;
~~~

Nếu event_id đến từ một bộ sinh số ngẫu nhiên hoặc một ID không có thứ tự, INSERT có thể phân bố trên nhiều leaf page. Đây là một nguyên nhân phổ biến làm clustered index có page occupancy và mức phân mảnh khác với mẫu chèn tuần tự.

Không phải khóa ngẫu nhiên nào cũng sai. Một số hệ thống cần ID khó đoán hoặc được sinh độc lập trên nhiều node. Khi chọn khóa, hãy cân bằng yêu cầu nghiệp vụ, tính phân tán, độ dài khóa, khả năng sắp xếp theo thời gian và chi phí ghi index.

### 3.3. Secondary index có thứ tự riêng

Giả sử event_id tăng dần nhưng event_time không tăng dần:

~~~sql
INSERT INTO event_update_demo (event_time, event_type, payload)
VALUES
    ('2026-02-15 10:10:00', 1, 'event A'),
    ('2026-01-04 08:30:00', 2, 'event B'),
    ('2026-02-02 17:45:00', 1, 'event C'),
    ('2026-01-21 12:00:00', 3, 'event D');
~~~

Clustered index nhận event_id mới theo thứ tự AUTO_INCREMENT. Nhưng idx_event_time phải chèn ngày giờ vào vị trí tương ứng trong B-tree của secondary index. Nếu ngày giờ phân bố ngẫu nhiên, secondary index vẫn có thể split.

Vì vậy, khi phân tích page split, phải xem xét từng index chứ không chỉ nhìn PRIMARY KEY.

## 4. UPDATE có thể gây split hoặc merge như thế nào?

UPDATE có thể thay đổi kích thước hàng, vị trí lưu trữ hoặc khóa index. Tác động phụ thuộc cột nào được cập nhật và page còn bao nhiêu chỗ.

### 4.1. UPDATE cột không thuộc index

Nếu cập nhật một cột không thuộc index và hàng vẫn vừa trong page hiện tại, InnoDB thường có thể ghi lại hàng trên cùng page.

Ví dụ:

~~~sql
UPDATE event_update_demo
SET payload = 'payload đã được hiệu chỉnh'
WHERE event_id = 1001;
~~~

Nếu payload tăng độ dài nhưng page còn đủ chỗ, hàng có thể vẫn được lưu trong page hiện tại. Nếu không đủ chỗ, InnoDB phải xử lý việc tổ chức lại bản ghi và có thể cần page khác hoặc các thay đổi cấu trúc lưu trữ liên quan.

Không nên kết luận rằng mọi UPDATE làm VARCHAR dài hơn đều gây page split. Kết quả phụ thuộc độ dài thực tế, row format, cách lưu cột dài và không gian còn lại.

### 4.2. UPDATE cột thuộc secondary index

Nếu UPDATE thay đổi giá trị của một cột thuộc secondary index, InnoDB phải loại bỏ mục index cũ và thêm mục index mới theo khóa mới.

Ví dụ:

~~~sql
UPDATE event_update_demo
SET event_time = '2026-03-01 09:00:00'
WHERE event_id = 1001;
~~~

event_time là cột của idx_event_time. Việc cập nhật có thể làm bản ghi rời khỏi vị trí khóa cũ và được chèn vào vị trí mới. Vị trí mới có thể nằm trên một page khác và có thể kích hoạt page split nếu page đích không còn đủ chỗ.

UPDATE một cột index vì vậy có thể tốn công hơn UPDATE một cột không index.

### 4.3. UPDATE làm khóa dài hơn hoặc ngắn hơn

Giả sử index được tạo trên code:

~~~sql
CREATE TABLE product_code (
    product_id BIGINT UNSIGNED NOT NULL,
    code VARCHAR(120) NOT NULL,
    description VARCHAR(200) NOT NULL,
    PRIMARY KEY (product_id),
    UNIQUE KEY uq_product_code (code)
) ENGINE = InnoDB;
~~~

Cập nhật code từ chuỗi ngắn sang chuỗi dài hơn có thể làm bản ghi secondary index lớn hơn. Nếu page đích không đủ chỗ, InnoDB có thể phải split page.

Ngược lại, khi khóa index ngắn đi, bản ghi có thể chiếm ít chỗ hơn. Nếu page trở nên thưa và tỷ lệ lấp đầy thấp hơn MERGE_THRESHOLD, InnoDB có thể thử merge với page lân cận.

### 4.4. UPDATE khóa chính

Khóa chính xác định thứ tự clustered index và được lưu trong các secondary index. Thay đổi khóa chính có thể làm hàng phải được chuyển sang vị trí mới trong clustered index và cập nhật giá trị khóa chính trong các secondary index.

Vì vậy, khóa chính nên ổn định trong suốt vòng đời bản ghi. Nếu ứng dụng thường xuyên đổi khóa chính, chi phí cập nhật nhiều cây index có thể đáng kể.

## 5. Page merge là gì?

Page merge là thao tác gộp một index page có ít dữ liệu với page lân cận khi tổng dữ liệu có thể vừa trong một page.

InnoDB có thể thử merge khi:

- Một bản ghi bị xóa và page trở nên thưa.
- UPDATE làm bản ghi ngắn đi và giảm tỷ lệ sử dụng page.
- Tỷ lệ lấp đầy của page giảm xuống dưới MERGE_THRESHOLD.

Nếu hai page có thể chứa chung các bản ghi sau khi gộp, InnoDB cập nhật node cha và giải phóng một page để tái sử dụng trong tablespace.

Page merge giúp thu hồi page trống trong B-tree, nhưng không nhất thiết làm file .ibd nhỏ lại ngay. Page được giải phóng có thể được tái sử dụng cho dữ liệu khác trong tablespace.

### 5.1. Minh họa page merge

Giả sử hai page lân cận đang chứa:

~~~text
Page A                  Page B
[ 10 | 20 ]             [ 30 | 40 ]

Sau khi merge:
Page A
[ 10 | 20 | 30 | 40 ]

Page B được giải phóng để InnoDB tái sử dụng.
~~~

Đây là mô hình khái quát. Việc merge thực tế phụ thuộc tổng kích thước bản ghi, không gian page và ngưỡng merge.

### 5.2. MERGE_THRESHOLD mặc định là 50

InnoDB dùng MERGE_THRESHOLD để quyết định khi nào thử gộp page. Giá trị mặc định là 50, nghĩa là khi page có tỷ lệ lấp đầy thấp hơn 50% sau thao tác xóa hoặc làm ngắn bản ghi, InnoDB thử merge với page lân cận.

Giá trị hợp lệ nằm trong khoảng 1 đến 50. MERGE_THRESHOLD có thể được cấu hình ở cấp bảng hoặc từng index:

- Thiết lập ở cấp index có độ ưu tiên cao hơn thiết lập ở cấp bảng.
- Nếu không khai báo, giá trị mặc định là 50.
- Hạ ngưỡng khiến InnoDB đợi page thưa hơn mới thử merge.
- Ngưỡng quá thấp có thể để lại nhiều page trống và làm file dữ liệu lớn hơn.

### 5.3. Vì sao merge rồi lại split?

Giả sử hai page đều gần 50% đầy. Khi một page rơi xuống dưới ngưỡng 50%, InnoDB thử merge với page bên cạnh. Nếu page mới sau merge gần đầy, một INSERT tiếp theo có thể khiến nó split lại.

Hiện tượng merge-split lặp lại có thể làm tăng công việc bảo trì index mà không đem lại lợi ích ổn định.

Trong workload có nhiều INSERT và DELETE xen kẽ ở cùng vùng khóa, có thể thử hạ MERGE_THRESHOLD. Việc điều chỉnh phải dựa trên số lần merge, split, mức sử dụng không gian và độ trễ thực tế.

## 6. Cấu hình MERGE_THRESHOLD

### 6.1. Đặt ngưỡng cho một bảng

Có thể cấu hình MERGE_THRESHOLD trong table COMMENT:

~~~sql
CREATE TABLE product_code_tuned (
    product_id BIGINT UNSIGNED NOT NULL,
    code VARCHAR(120) NOT NULL,
    PRIMARY KEY (product_id),
    KEY idx_code (code)
) ENGINE = InnoDB
COMMENT = 'MERGE_THRESHOLD=45';
~~~

Với bảng đã tồn tại:

~~~sql
ALTER TABLE product_code_tuned
COMMENT = 'MERGE_THRESHOLD=45';
~~~

### 6.2. Đặt ngưỡng cho một index

Có thể cấu hình riêng trên index bằng index COMMENT:

~~~sql
CREATE TABLE event_by_customer (
    event_id BIGINT UNSIGNED NOT NULL,
    customer_id BIGINT UNSIGNED NOT NULL,
    event_time DATETIME NOT NULL,
    PRIMARY KEY (event_id),
    KEY idx_customer_time (customer_id, event_time)
        COMMENT 'MERGE_THRESHOLD=40'
) ENGINE = InnoDB;
~~~

Nếu ngưỡng của index là 40, thiết lập riêng đó được ưu tiên so với ngưỡng của bảng.

Kiểm tra cấu hình:

~~~sql
SHOW INDEX FROM event_by_customer;
SHOW CREATE TABLE event_by_customer;
~~~

SHOW INDEX hiển thị comment của index trong cột Index_comment. SHOW CREATE TABLE cho phép kiểm tra định nghĩa bảng và table comment.

### 6.3. Chọn ngưỡng theo workload

| Mẫu workload | Hướng đánh giá |
|---|---|
| INSERT tăng dần, ít DELETE | Thường không cần tùy chỉnh ngưỡng |
| INSERT ngẫu nhiên xen kẽ DELETE | Theo dõi merge-split trước khi điều chỉnh |
| UPDATE làm khóa index thường xuyên ngắn đi | Kiểm tra số lần merge và page occupancy |
| Merge thường xuyên theo sau bởi split | Thử hạ ngưỡng trong môi trường kiểm thử |
| Cần giảm số page trống tối đa | Không hạ ngưỡng quá thấp nếu gây lãng phí không gian |

Không có một giá trị MERGE_THRESHOLD tối ưu cho mọi bảng. Một ngưỡng thấp hơn có thể giảm số lần merge-split nhưng giữ nhiều page thưa hơn. Một ngưỡng cao hơn có thể thu hồi page sớm nhưng dễ tạo chu kỳ merge rồi split lại.

## 7. innodb_fill_factor và phần không gian dành cho tăng trưởng

innodb_fill_factor điều khiển mức độ lấp đầy page khi InnoDB tạo hoặc rebuild B-tree index bằng sorted index build.

Giá trị mặc định là 100. Giá trị 80 là gợi ý để lấp khoảng 80% page và dành phần còn lại cho tăng trưởng sau này. Đây là hint chứ không phải giới hạn cứng; tỷ lệ thực tế có thể khác.

Các điểm cần nhớ:

- innodb_fill_factor có phạm vi GLOBAL và có thể thay đổi động.
- Áp dụng cho cả leaf page và non-leaf page của B-tree.
- Không áp dụng cho external page lưu dữ liệu TEXT hoặc BLOB.
- Giá trị 100 vẫn để trống 1/16 không gian trong clustered index page theo quy tắc của InnoDB.
- Thiết lập này tác động đến sorted index build, không phải công tắc điều khiển trực tiếp mọi INSERT thông thường.

Kiểm tra:

~~~sql
SHOW VARIABLES LIKE 'innodb_fill_factor';
~~~

Ví dụ đọc thiết lập:

~~~sql
SELECT
    @@GLOBAL.innodb_fill_factor AS fill_factor;
~~~

Nếu đặt 80 trước khi rebuild index, InnoDB dùng giá trị đó làm gợi ý cho sorted index build:

~~~sql
SET @original_fill_factor = @@GLOBAL.innodb_fill_factor;

SET GLOBAL innodb_fill_factor = 80;

ALTER TABLE event_update_demo
FORCE;

SET GLOBAL innodb_fill_factor = @original_fill_factor;
~~~

Đây là ví dụ minh họa cho môi trường thử nghiệm. ALTER TABLE ... FORCE rebuild bảng và index, có thể tốn I/O, thời gian và dung lượng tạm. Câu lệnh lưu và khôi phục giá trị GLOBAL ban đầu trong session hiện tại; nếu DDL thất bại giữa chừng, hãy kiểm tra và khôi phục thiết lập thủ công. Đánh giá ảnh hưởng đến các DDL khác đang chạy và chỉ thực hiện trong cửa sổ bảo trì phù hợp.

Không đặt fill factor thấp chỉ vì nhìn thấy một vài page split. Page trống giúp hấp thụ tăng trưởng nhưng cũng làm tăng số page cần lưu, đọc và giữ trong buffer pool. Mục tiêu là cân bằng chi phí ghi và chi phí đọc theo mẫu dữ liệu thực tế.

## 8. Phân mảnh trong InnoDB

Phân mảnh (fragmentation) là tình trạng bố trí page và dữ liệu không còn thuận lợi cho truy cập tuần tự hoặc sử dụng không gian.

Trong InnoDB, có thể gặp hai biểu hiện:

1. Thứ tự vật lý của index page trên đĩa không gần với thứ tự logic của các bản ghi index.
2. Có nhiều page chưa sử dụng trong các khối 64 page đã được cấp phát cho index.

Một bảng có thể chiếm nhiều không gian hơn dự kiến hoặc cần đọc nhiều page hơn khi quét index.

### 8.1. Phân mảnh do chèn ngẫu nhiên

Chèn khóa ngẫu nhiên vào secondary index có thể làm page split ở nhiều vùng. Các page mới được cấp phát không nhất thiết nằm liền kề vật lý với page trước đó.

Khi quét index theo thứ tự khóa, InnoDB vẫn đi theo cấu trúc B-tree, nhưng bố trí page vật lý có thể làm việc đọc dữ liệu kém tuần tự hơn.

### 8.2. Khoảng trống do DELETE

DELETE trong InnoDB không nhất thiết xóa vật lý bản ghi ngay tại thời điểm câu lệnh chạy. Bản ghi có thể được đánh dấu xóa và được purge khi không còn cần cho các consistent read đang tồn tại.

Sau khi bản ghi được loại bỏ vật lý, page có thể còn nhiều khoảng trống. Nếu page đủ thưa, cơ chế merge có thể gộp page với page lân cận.

Xóa nhiều hàng không đồng nghĩa file .ibd sẽ giảm kích thước ngay. Page được giải phóng có thể được tái sử dụng nội bộ. Để trả không gian về hệ điều hành, thường cần rebuild bảng trong file-per-table tablespace.

### 8.3. InnoDB vẫn cần một mức không gian trống

Không phải mọi page trống đều là lãng phí. InnoDB cố ý để lại khoảng trống cho INSERT và UPDATE trong tương lai.

Tài liệu MySQL 8.4 mô tả mức fill factor của các B-tree page có thể thay đổi trong khoảng 50% đến 100%. Với clustered index, InnoDB cố gắng giữ 1/16 page trống cho tăng trưởng. Vì vậy, không nên kỳ vọng mọi page đều lấp đầy 100%.

InnoDB quản lý page và tablespace khác với cách lưu trữ của MyISAM. Không nên áp dụng nguyên xi cách đánh giá hoặc lịch OPTIMIZE định kỳ của MyISAM cho InnoDB.

## 9. Theo dõi split, merge và dung lượng

### 9.1. Theo dõi INNODB_METRICS

InnoDB cung cấp bộ đếm trong INFORMATION_SCHEMA.INNODB_METRICS. Các bộ đếm liên quan gồm:

- index_page_splits: số lần page index bị split.
- index_page_merge_attempts: số lần thử merge page.
- index_page_merge_successful: số lần merge thành công.
- index_page_reorg_attempts: số lần thử tổ chức lại page.
- index_page_reorg_successful: số lần tổ chức lại page thành công.

Các bộ đếm index thường bị tắt mặc định. Có thể bật riêng các bộ đếm cần theo dõi:

~~~sql
SET GLOBAL innodb_monitor_enable = index_page_splits;
SET GLOBAL innodb_monitor_enable = index_page_merge_attempts;
SET GLOBAL innodb_monitor_enable = index_page_merge_successful;
SET GLOBAL innodb_monitor_enable = index_page_reorg_attempts;
SET GLOBAL innodb_monitor_enable = index_page_reorg_successful;
~~~

Đọc các bộ đếm:

~~~sql
SELECT
    name,
    count,
    status,
    time_enabled
FROM information_schema.innodb_metrics
WHERE name IN (
    'index_page_splits',
    'index_page_merge_attempts',
    'index_page_merge_successful',
    'index_page_reorg_attempts',
    'index_page_reorg_successful'
)
ORDER BY name;
~~~

Các bộ đếm này phản ánh hoạt động của toàn instance, không phân tách riêng theo từng bảng. Hãy ghi nhận giá trị trước và sau một workload kiểm thử để so sánh mức tăng. Nếu nhiều ứng dụng đang ghi đồng thời, kết quả có thể bao gồm hoạt động của các bảng khác.

Việc bật metrics có thêm overhead. Trước khi bật, ghi lại trạng thái ban đầu của module. Chỉ tắt module sau thử nghiệm nếu chính bạn đã bật nó và không có workload chẩn đoán khác đang sử dụng; không tắt một module vốn đã được quản trị viên bật trước đó.

Nếu các bộ đếm này trước đó đang tắt và được bật riêng cho lần chẩn đoán này, có thể tắt sau khi hoàn tất:

~~~sql
SET GLOBAL innodb_monitor_disable = index_page_splits;
SET GLOBAL innodb_monitor_disable = index_page_merge_attempts;
SET GLOBAL innodb_monitor_disable = index_page_merge_successful;
SET GLOBAL innodb_monitor_disable = index_page_reorg_attempts;
SET GLOBAL innodb_monitor_disable = index_page_reorg_successful;
~~~

Cần quyền quản trị phù hợp để thay đổi các biến monitor. Nên thử trong môi trường development hoặc staging trước khi bật trên production.

### 9.2. Kiểm tra dung lượng bảng

Có thể xem kích thước dữ liệu, index và dung lượng trống ước tính:

~~~sql
SELECT
    table_name,
    engine,
    table_rows,
    data_length,
    index_length,
    data_free
FROM information_schema.tables
WHERE table_schema = DATABASE()
  AND table_name IN (
      'event_update_demo',
      'event_random_demo',
      'product_code'
  );
~~~

Các giá trị thống kê của InnoDB có thể là ước lượng. DATA_FREE phản ánh không gian trống được báo cáo ở cấp tablespace và không phải một chỉ số chính xác cho tỷ lệ phân mảnh của từng index.

Có thể dùng thêm:

~~~sql
SHOW TABLE STATUS LIKE 'event_update_demo';
SHOW INDEX FROM event_update_demo;
~~~

Kết hợp kích thước, tốc độ tăng trưởng, số lần split/merge, độ trễ truy vấn và mẫu đọc thực tế. Không kết luận bảng bị phân mảnh nặng chỉ vì DATA_FREE lớn hoặc index có nhiều page trống.

### 9.3. So sánh số liệu theo thời gian

Một lần chụp metrics chỉ cho biết bộ đếm tích lũy. Quy trình đo có ý nghĩa hơn:

1. Ghi lại số split, merge và reorganization trước thử nghiệm.
2. Chạy workload có mẫu INSERT/UPDATE/DELETE xác định.
3. Đọc lại các bộ đếm.
4. Tính mức tăng trong khoảng thử nghiệm.
5. So sánh với số hàng ghi, dung lượng index và độ trễ truy vấn.
6. Lặp lại với một thiết kế khóa hoặc cấu hình khác.

Không nên so sánh hai lần đo nếu số lượng hàng, index, cache state hoặc mức đồng thời khác nhau quá nhiều.

## 10. Khi nào nên rebuild hoặc OPTIMIZE TABLE?

InnoDB có thể cần rebuild sau khi xóa nhiều dữ liệu hoặc khi page distribution khiến việc quét index và bảng kém hiệu quả. Tuy nhiên, một mức phân mảnh nhất định là bình thường.

### 10.1. OPTIMIZE TABLE với InnoDB

Với InnoDB, OPTIMIZE TABLE được ánh xạ thành ALTER TABLE ... FORCE. Thao tác này rebuild bảng, cập nhật thống kê index và giải phóng không gian chưa sử dụng trong clustered index.

Ví dụ:

~~~sql
OPTIMIZE TABLE event_update_demo;
~~~

Có thể dùng lệnh rebuild tương đương:

~~~sql
ALTER TABLE event_update_demo ENGINE = InnoDB;
~~~

Hoặc:

~~~sql
ALTER TABLE event_update_demo FORCE;
~~~

OPTIMIZE TABLE dùng online DDL cho bảng InnoDB thông thường, giảm thời gian gián đoạn cho DML đồng thời. Dù vậy, thao tác vẫn cần khóa độc quyền trong thời gian ngắn ở các pha prepare và commit. Nó cũng có thể tiêu thụ đáng kể CPU, I/O và dung lượng đĩa trong khi rebuild.

Các bảng InnoDB có FULLTEXT index không hỗ trợ đường online DDL này và có thể dùng table-copy method. Cấu hình old_alter_table hoặc tùy chọn server liên quan cũng có thể làm thay đổi cách rebuild. Hãy kiểm tra điều kiện cụ thể trước khi chạy trên bảng lớn.

### 10.2. innodb_file_per_table và thu hồi dung lượng

Khi innodb_file_per_table bật, mỗi bảng có tablespace riêng thường được lưu trong file .ibd. Sau khi rebuild, không gian không còn cần thiết có thể được trả về hệ điều hành.

Nếu bảng nằm trong system tablespace dùng chung, các page trống có thể được InnoDB tái sử dụng cho bảng khác nhưng file system tablespace không tự thu nhỏ.

Kiểm tra:

~~~sql
SHOW VARIABLES LIKE 'innodb_file_per_table';
~~~

Không giả định OPTIMIZE TABLE luôn làm file dữ liệu nhỏ đi. Kết quả phụ thuộc tablespace, workload và phần không gian được giải phóng.

### 10.3. Khi nào nên cân nhắc rebuild?

Có thể đánh giá rebuild khi:

- Đã xóa một lượng lớn hàng và không gian trống khó được tái sử dụng hiệu quả.
- Bảng hoặc index tăng kích thước bất thường so với lượng dữ liệu còn lại.
- Index scan hoặc table scan chậm hơn rõ rệt sau một giai đoạn ghi/xóa lớn.
- Có bằng chứng về nhiều page thưa hoặc bố trí page kém thuận lợi.
- Cần tái tạo index sau thay đổi dữ liệu hoặc cấu trúc phù hợp.

Không nên chạy OPTIMIZE TABLE theo lịch cố định cho mọi bảng mà không đo lợi ích. Rebuild tạo tải I/O, cần dung lượng làm việc và có thể ảnh hưởng đến độ trễ của workload.

### 10.4. ANALYZE TABLE không thay thế rebuild

ANALYZE TABLE cập nhật thống kê index để optimizer ước lượng cardinality và chọn kế hoạch truy vấn. Nó không phải thao tác rebuild hoặc defragment bảng.

~~~sql
ANALYZE TABLE event_update_demo;
~~~

Nếu vấn đề là optimizer chọn sai index do thống kê cũ, ANALYZE TABLE có thể hữu ích. Nếu vấn đề là page distribution hoặc không gian trống sau nhiều thao tác ghi/xóa, cần đánh giá rebuild riêng.

## 11. Thiết kế để giảm chi phí split và fragmentation

### 11.1. Chọn khóa chính phù hợp

Khóa chính nên:

- Ngắn để giảm kích thước secondary index.
- Ổn định, ít bị cập nhật.
- Có thứ tự phù hợp với mẫu ghi nếu nghiệp vụ cho phép.
- Duy nhất và không NULL.

AUTO_INCREMENT là lựa chọn tốt cho nhiều bảng ghi tuần tự. Nhưng hệ thống phân tán hoặc yêu cầu ID sinh độc lập có thể cần khóa khác. Hãy đo chi phí của lựa chọn đó trên cả clustered index và secondary index.

### 11.2. Giữ secondary index có mục đích

Mỗi secondary index cần được cập nhật khi INSERT, DELETE hoặc UPDATE cột khóa liên quan. Quá nhiều index làm tăng công việc ghi và số B-tree phải duy trì.

Trước khi thêm index, hãy xác định truy vấn nào cần nó. Sau khi thay đổi workload, đánh giá index không còn được dùng và cân nhắc loại bỏ có kiểm soát.

### 11.3. Hạn chế thay đổi khóa index không cần thiết

Nếu một cột thường xuyên được cập nhật và có trong nhiều secondary index, mỗi thay đổi có thể cần loại bỏ entry cũ và thêm entry mới. Chọn khóa index ổn định khi có thể.

Với các cột chuỗi có độ dài thay đổi, cân nhắc độ dài dữ liệu thực tế và tác động đến page occupancy. Không cần khai báo VARCHAR quá rộng cho mọi cột nếu dữ liệu nghiệp vụ có giới hạn rõ ràng.

### 11.4. Gom các thao tác ghi hợp lý

Với workload bulk insert, có thể giảm overhead bằng cách nạp dữ liệu theo lô và sắp xếp đầu vào theo khóa index phù hợp khi điều đó không làm thay đổi ý nghĩa nghiệp vụ.

Đối với index được tạo mới hoặc rebuild, InnoDB có sorted index build để nạp bản ghi theo thứ tự, giảm chi phí chèn từng entry vào B-tree. Đây là một cơ chế khác với đường INSERT thông thường.

### 11.5. Đánh giá trade-off thay vì tối ưu một chỉ số

| Lựa chọn | Lợi ích có thể có | Chi phí cần xem xét |
|---|---|---|
| Khóa chính tăng dần | Chèn clustered index tuần tự | Có thể tập trung ghi ở vùng cuối |
| Khóa chính ngẫu nhiên | Dễ sinh ID phân tán | Chèn vào nhiều vùng, tăng split và page thưa |
| Giảm số secondary index | Giảm công việc ghi index | Một số truy vấn có thể phải đọc nhiều hàng hơn |
| Fill factor thấp hơn khi rebuild | Dành chỗ cho tăng trưởng | Tăng số page và chi phí đọc |
| MERGE_THRESHOLD thấp hơn | Giảm merge-split lặp lại | Giữ nhiều page thưa hơn |
| Rebuild bảng | Tái tổ chức page và thu hồi không gian | Tốn I/O, thời gian và dung lượng làm việc |

## 12. Thực hành so sánh khóa tuần tự và khóa ngẫu nhiên

Bài lab tạo hai bảng có cùng cấu trúc dữ liệu. Một bảng dùng AUTO_INCREMENT; bảng còn lại nhận khóa chính được phân bố ngẫu nhiên. Cả hai cùng có secondary index theo event_time.

### 12.1. Tạo bảng

~~~sql
CREATE TABLE event_sequential (
    event_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    event_time DATETIME NOT NULL,
    category_id INT UNSIGNED NOT NULL,
    payload VARCHAR(100) NOT NULL,
    PRIMARY KEY (event_id),
    KEY idx_event_time (event_time)
) ENGINE = InnoDB;

CREATE TABLE event_random (
    event_id BIGINT UNSIGNED NOT NULL,
    event_time DATETIME NOT NULL,
    category_id INT UNSIGNED NOT NULL,
    payload VARCHAR(100) NOT NULL,
    PRIMARY KEY (event_id),
    KEY idx_event_time (event_time)
) ENGINE = InnoDB;
~~~

### 12.2. Nạp dữ liệu kiểm thử

Đoạn procedure sau tạo 20.000 hàng cho mỗi bảng. event_time có cùng mẫu phân bố ở hai bảng; khác biệt chính là thứ tự khóa chính.

~~~sql
DELIMITER //

CREATE PROCEDURE seed_page_split_demo()
BEGIN
    DECLARE i BIGINT DEFAULT 1;
    DECLARE event_time_value DATETIME;

    WHILE i <= 20000 DO
        SET event_time_value = TIMESTAMPADD(
            SECOND,
            MOD(i * 3571, 1000003),
            '2026-01-01 00:00:00'
        );

        INSERT INTO event_sequential (
            event_time,
            category_id,
            payload
        )
        VALUES (
            event_time_value,
            MOD(i, 100),
            RPAD('x', 100, 'x')
        );

        INSERT INTO event_random (
            event_id,
            event_time,
            category_id,
            payload
        )
        VALUES (
            MOD(i * 7919, 1000003) + 1,
            event_time_value,
            MOD(i, 100),
            RPAD('x', 100, 'x')
        );

        SET i = i + 1;
    END WHILE;
END//

DELIMITER ;

CALL seed_page_split_demo();

DROP PROCEDURE seed_page_split_demo;
~~~

Chạy trong database thực hành. Procedure chèn từng hàng để làm rõ mẫu khóa; đây không phải khuyến nghị về cách nạp bulk data cho production.

### 12.3. Bật và đọc metrics

Trước khi chạy procedure, bật bộ đếm split và ghi lại giá trị ban đầu:

~~~sql
SET GLOBAL innodb_monitor_enable = index_page_splits;

SELECT
    name,
    count,
    status
FROM information_schema.innodb_metrics
WHERE name = 'index_page_splits'
ORDER BY name;
~~~

Sau khi chạy procedure, đọc lại bộ đếm và so sánh mức tăng. Bộ đếm là toàn instance nên nên chạy lab trên server thử nghiệm ít workload khác. Nếu bạn đã bật bộ đếm riêng cho lab và trước đó nó đang tắt, hãy tắt lại sau khi đo bằng SET GLOBAL innodb_monitor_disable = index_page_splits.

### 12.4. So sánh dung lượng

~~~sql
SELECT
    table_name,
    table_rows,
    data_length,
    index_length,
    data_free
FROM information_schema.tables
WHERE table_schema = DATABASE()
  AND table_name IN (
      'event_sequential',
      'event_random'
  );
~~~

Dữ liệu thống kê có thể là ước lượng. Với hai bảng nhỏ, chênh lệch có thể chưa rõ. Tăng số lượng hàng hoặc lặp lại thử nghiệm để quan sát xu hướng.

### 12.5. Đọc kết quả

Khi phân tích, hãy trả lời:

- Bảng nào có clustered index được chèn theo thứ tự?
- Secondary index event_time có cùng mẫu chèn ở hai bảng không?
- Số lần split tăng thế nào sau khi nạp dữ liệu?
- Dung lượng data_length và index_length khác nhau ra sao?
- Nếu thay đổi event_time sang thứ tự tăng dần, secondary index sẽ chịu tác động gì?
- Nếu đổi khóa chính ngẫu nhiên thành khóa tăng dần, chi phí ghi thay đổi thế nào?

Kết quả cụ thể phụ thuộc phiên bản MySQL, page size, trạng thái buffer pool, row format, dữ liệu và workload. Mục tiêu của lab là quan sát xu hướng, không khẳng định một tỷ lệ split cố định.

## 13. Quy trình chẩn đoán page split và fragmentation

Khi nghi ngờ B-tree bị split hoặc phân mảnh nhiều, có thể thực hiện theo trình tự:

1. Xác định bảng và index nào đang chịu nhiều INSERT, UPDATE hoặc DELETE.
2. Kiểm tra clustered index và các secondary index, bao gồm thứ tự khóa và độ dài khóa.
3. Xác định mẫu chèn tăng dần hay ngẫu nhiên.
4. Ghi nhận số lần split, merge và reorganization bằng INNODB_METRICS.
5. So sánh mức tăng metrics với lượng ghi và thời gian đo.
6. Kiểm tra data_length, index_length, data_free và thời gian truy vấn.
7. Xác định page thưa là khoảng trống có chủ đích hay hệ quả của xóa/cập nhật.
8. Thử điều chỉnh MERGE_THRESHOLD hoặc fill factor trong môi trường kiểm thử nếu có bằng chứng phù hợp.
9. Đo lại với cùng workload.
10. Chỉ rebuild khi lợi ích dự kiến lớn hơn chi phí vận hành.

Có thể ghi nhớ mối quan hệ giữa thao tác dữ liệu và cấu trúc page bằng sơ đồ:

~~~mermaid
flowchart TD
    A[INSERT hoặc UPDATE] --> B{Khóa index thay đổi?}
    B -->|Không| C{Hàng có lớn hơn?}
    B -->|Có| D[Loại entry cũ và chèn entry mới]
    C -->|Không| E[Ghi lại hàng trong page nếu đủ chỗ]
    C -->|Có| F{Page còn đủ chỗ?}
    F -->|Có| E
    F -->|Không| G[Reorganize hoặc cấp page và split]
    D --> H{Page đích đủ chỗ?}
    H -->|Có| I[Chèn entry mới]
    H -->|Không| G
    I --> J[Kiểm tra trạng thái page]
    E --> J
    G --> J
    J --> K{DELETE hoặc UPDATE làm page thưa?}
    K -->|Có| L{Dưới MERGE_THRESHOLD?}
    L -->|Có| M[Thử merge với page lân cận]
    L -->|Không| N[Giữ page hiện tại]
    M --> O[Theo dõi merge-split và dung lượng]
    K -->|Không| N
~~~

## 14. Các hiểu nhầm thường gặp

| Hiểu nhầm | Thực tế | Cách xử lý |
|---|---|---|
| Mỗi INSERT đều gây page split | Split chỉ cần khi page không đủ chỗ sau khi tổ chức lại | Theo dõi số lần split thay vì đếm số INSERT |
| Chỉ clustered index mới split | Mỗi B-tree index đều có thể split | Đánh giá cả secondary index |
| AUTO_INCREMENT loại bỏ mọi fragmentation | Secondary index vẫn có thể nhận khóa ngẫu nhiên | Xem thứ tự ghi của từng index |
| Page split luôn chia đúng 50/50 | Cách chia phụ thuộc vị trí chèn và trạng thái page | Không dự đoán occupancy từ một ví dụ đơn giản |
| DELETE trả dung lượng về hệ điều hành ngay | Page có thể được tái sử dụng trong tablespace | Rebuild khi cần thu hồi dung lượng file-per-table |
| UPDATE cột bất kỳ đều split page | Chỉ một số thay đổi kích thước hoặc khóa mới cần cấu trúc page khác | Xác định cột có thuộc index không và page còn chỗ không |
| MERGE_THRESHOLD thấp luôn tốt | Ngưỡng thấp có thể để lại nhiều page thưa | Đo merge, split và dung lượng |
| innodb_fill_factor điều khiển mọi INSERT | Nó là hint cho sorted index build | Chỉ điều chỉnh khi tạo hoặc rebuild index |
| OPTIMIZE TABLE chỉ cập nhật statistics | Với InnoDB, nó rebuild bảng thông qua ALTER TABLE ... FORCE | Dự trù I/O, dung lượng và ảnh hưởng DDL |
| DATA_FREE là tỷ lệ fragmentation chính xác | Đây là thống kê dung lượng trống ở cấp tablespace | Kết hợp metrics, kích thước và workload |
| Page split đồng nghĩa bảng bị khóa hoàn toàn | Split là thay đổi cấu trúc B-tree, không phải khóa toàn bảng mặc định | Phân biệt latch nội bộ, row lock và metadata lock |

## 15. Bài tập thực hành

### Bài 1: Vẽ cấu trúc B-tree

Tạo một bảng có PRIMARY KEY và hai secondary index. Vẽ root, non-leaf và leaf page cho từng index. Giải thích vì sao một hàng xuất hiện trong nhiều cây index.

### Bài 2: So sánh khóa tuần tự và ngẫu nhiên

Dùng hai bảng event_sequential và event_random. Nạp cùng số hàng với hai mẫu khóa. So sánh số lần split và kích thước index.

### Bài 3: Chèn ngẫu nhiên vào secondary index

Giữ khóa chính AUTO_INCREMENT nhưng chèn event_time không theo thứ tự. Giải thích vì sao secondary index vẫn có thể split.

### Bài 4: UPDATE khóa index

Tạo bảng có UNIQUE index trên code. Cập nhật code từ giá trị ngắn sang dài và từ dài sang ngắn. Phân tích entry cũ, entry mới và khả năng split/merge.

### Bài 5: UPDATE cột không index

Cập nhật payload trên cùng bảng. So sánh với UPDATE cột thuộc index. Giải thích sự khác nhau về công việc bảo trì B-tree.

### Bài 6: Quan sát MERGE_THRESHOLD

Tạo hai bảng có MERGE_THRESHOLD khác nhau. Chạy workload DELETE và UPDATE làm ngắn khóa. Theo dõi số lần merge attempt và merge successful.

### Bài 7: Tìm hiện tượng merge-split

Tạo workload xen kẽ DELETE và INSERT vào cùng vùng khóa. Theo dõi số lần merge và split. Thử hạ MERGE_THRESHOLD rồi so sánh.

### Bài 8: Kiểm tra innodb_fill_factor

Ghi lại giá trị innodb_fill_factor. Rebuild một bảng thử nghiệm với fill factor 80 và 100. So sánh kích thước, page split về sau và chi phí đọc.

### Bài 9: Đánh giá fragmentation

Sau khi chèn và xóa nhiều hàng, kiểm tra data_length, index_length, data_free và thời gian quét. Giải thích vì sao một chỉ số riêng lẻ chưa đủ kết luận.

### Bài 10: Rebuild có kiểm soát

Chạy OPTIMIZE TABLE trên bảng thử nghiệm. Ghi lại dung lượng trước và sau, thời gian thực thi và khả năng DML đồng thời. Xác định điều kiện nào khiến thao tác phù hợp hoặc không phù hợp cho production.

## Kết luận

Page split xảy ra khi bản ghi mới không còn chỗ trong B-tree page; page merge là nỗ lực gộp page thưa sau DELETE hoặc UPDATE làm khóa ngắn đi. Thứ tự khóa, độ dài khóa chính, số lượng secondary index và cách cập nhật cột index quyết định lượng công việc cấu trúc mà InnoDB phải thực hiện.

Một mức page trống là cần thiết cho tăng trưởng và không đồng nghĩa với fragmentation bất thường. Dùng MERGE_THRESHOLD để điều chỉnh thời điểm thử merge, innodb_fill_factor để điều khiển gợi ý lấp đầy khi sorted index build, và INNODB_METRICS để quan sát hoạt động thực tế. Chỉ rebuild hoặc OPTIMIZE TABLE khi số liệu cho thấy lợi ích đủ lớn so với chi phí I/O, dung lượng và thời gian vận hành.

## Tài liệu tham khảo

- MySQL 8.4 Reference Manual — The Physical Structure of an InnoDB Index: https://dev.mysql.com/doc/refman/8.4/en/innodb-physical-structure.html
- MySQL 8.4 Reference Manual — Clustered and Secondary Indexes: https://dev.mysql.com/doc/refman/8.4/en/innodb-index-types.html
- MySQL 8.4 Reference Manual — Sorted Index Builds: https://dev.mysql.com/doc/refman/8.4/en/sorted-index-builds.html
- MySQL 8.4 Reference Manual — Configuring the Merge Threshold for Index Pages: https://dev.mysql.com/doc/refman/8.4/en/index-page-merge-threshold.html
- MySQL 8.4 Reference Manual — InnoDB Startup Options and System Variables: https://dev.mysql.com/doc/refman/8.4/en/innodb-parameters.html
- MySQL 8.4 Reference Manual — Defragmenting a Table: https://dev.mysql.com/doc/refman/8.4/en/innodb-file-defragmenting.html
- MySQL 8.4 Reference Manual — OPTIMIZE TABLE Statement: https://dev.mysql.com/doc/refman/8.4/en/optimize-table.html
- MySQL 8.4 Reference Manual — InnoDB INFORMATION_SCHEMA Metrics Table: https://dev.mysql.com/doc/refman/8.4/en/innodb-information-schema-metrics-table.html
- MySQL 8.4 Reference Manual — Optimizing Storage Layout for InnoDB Tables: https://dev.mysql.com/doc/refman/8.4/en/optimizing-innodb-storage-layout.html

