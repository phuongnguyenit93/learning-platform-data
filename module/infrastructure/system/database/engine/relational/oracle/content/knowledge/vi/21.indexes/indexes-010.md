# Reverse key index, khóa tăng dần và khả năng truy vấn theo khoảng trong Oracle

Trong Oracle Database, B-tree index thường lưu các khóa theo thứ tự tăng dần. Khi một bảng nhận nhiều bản ghi mới với khóa được tạo bằng sequence tăng dần, các giá trị mới thường được chèn vào vùng cuối cùng của index. Nếu nhiều session cùng insert, chúng có thể tập trung truy cập một số leaf block ở mép phải của cây B-tree. Trong một số workload ghi đồng thời cao, đây là nguyên nhân gây **right-hand index leaf block contention**.

**Reverse key index** là một loại B-tree index đảo thứ tự byte của khóa trước khi lưu trong index. Việc đảo byte phân tán các khóa tăng dần tới nhiều vùng leaf block hơn, giảm tập trung insert vào leaf block cuối. Đổi lại, thứ tự logic của index không còn tương ứng với thứ tự giá trị gốc. Vì vậy, reverse key index hỗ trợ tra cứu bằng điều kiện bằng phù hợp, nhưng không hỗ trợ index range scan theo thứ tự khóa như B-tree thông thường.

Bài học giải thích mối liên hệ giữa khóa tăng dần, contention ở leaf block, cách reverse key index hoạt động, tác động tới truy vấn bằng và truy vấn khoảng, cách tạo/rebuild index, chẩn đoán và lựa chọn giải pháp thay thế.

## 1. B-tree index và cấu trúc leaf block

B-tree index của Oracle được tổ chức thành các tầng:

- **Root block:** điểm bắt đầu để tìm kiếm.
- **Branch blocks:** các block trung gian chứa khóa phân nhánh và con trỏ tới tầng thấp hơn.
- **Leaf blocks:** lưu giá trị khóa index cùng ROWID (hoặc thông tin hàng tương ứng) để tìm dữ liệu trong table.

Sơ đồ đơn giản:

~~~text
                    ROOT
                      |
             +--------+--------+
             |                 |
          BRANCH A          BRANCH B
          /     \            /     \
         v       v          v       v
      LEAF 1  LEAF 2      LEAF 3  LEAF 4
       keys    keys        keys    keys
~~~

B-tree giữ khóa theo thứ tự để Oracle có thể đi từ root xuống đúng branch và leaf block. Khi tìm một giá trị cụ thể, Oracle lần theo các nhánh phù hợp. Khi tìm một khoảng giá trị, Oracle có thể bắt đầu tại leaf block chứa giá trị đầu khoảng rồi đi qua các leaf block kế tiếp cho tới khi hết khoảng.

### 1.1. Leaf block split

Khi leaf block không còn đủ chỗ cho khóa mới, Oracle có thể thực hiện block split để phân chia các entry giữa các block. Split là hoạt động bình thường của B-tree, không phải lúc nào cũng là lỗi hiệu năng.

Với khóa phân bố đều, insert có thể đi vào nhiều leaf block. Với khóa tăng dần liên tục, phần lớn khóa mới có xu hướng đi vào vùng cuối cùng của index. Khi nhiều session đồng thời insert, vùng cuối này có thể trở thành điểm nóng.

### 1.2. Khóa tăng dần là gì?

Khóa tăng dần (monotonically increasing key) là khóa có giá trị mới thường lớn hơn các khóa trước đó. Các ví dụ phổ biến:

- Primary key lấy từ Oracle sequence.
- Cột ID được tạo theo bộ đếm tăng dần ở ứng dụng.
- Timestamp hoặc số thứ tự sự kiện có độ phân giải và thứ tự tăng.
- Mã giao dịch chứa phần số tăng liên tục.

Ví dụ:

| Lần insert | ID |
|---:|---:|
| 1 | 1001 |
| 2 | 1002 |
| 3 | 1003 |
| 4 | 1004 |
| 5 | 1005 |

Trong B-tree index thông thường trên ID, các giá trị mới thường được thêm vào đầu mút phải của thứ tự index.

### 1.3. Right-hand index hot block

Khi nhiều session insert khóa tăng dần cùng lúc, chúng có thể cùng cần sửa leaf block cuối hoặc các leaf block ở vùng cuối index. Oracle phải điều phối quyền truy cập block và buffer tương ứng. Điều này có thể dẫn tới chờ như:

- buffer busy waits trong một số tình huống cạnh tranh buffer block.
- enq: TX - index contention trong một số trường hợp contention liên quan index/transaction.
- gc buffer busy acquire hoặc gc buffer busy release trong môi trường RAC khi block nóng phải di chuyển/được yêu cầu giữa các instance.
- Các wait event khác tùy phiên bản, loại index và đường thực thi.

Không phải mọi bảng có sequence đều bị contention. Vấn đề phụ thuộc số session ghi đồng thời, tốc độ insert, kích thước block, cấu hình cache, loại index, workload RAC và thời gian giữ block. Một ứng dụng ghi tuần tự với concurrency thấp có thể không cần reverse key index.

## 2. Vì sao khóa tăng dần có thể gây contention?

Giả sử index B-tree bình thường có các leaf block chứa khóa:

~~~text
LEAF A: 1001, 1002, 1003
LEAF B: 1004, 1005, 1006
LEAF C: 1007, 1008, 1009  <-- vùng cuối
~~~

Khi nhiều session cùng insert 1010, 1011, 1012..., chúng thường tìm đến vùng cuối của index. Nếu leaf block chưa đủ chỗ, split có thể xảy ra; nếu nhiều session cùng cần block nóng, chúng phải chờ quyền truy cập phù hợp.

~~~text
Session 1 ---- insert ID 1010 ----+
Session 2 ---- insert ID 1011 ----+----> Right-most leaf block
Session 3 ---- insert ID 1012 ----+
Session 4 ---- insert ID 1013 ----+
                                      |
                                      v
                             Cạnh tranh block nóng
~~~

Đây là **index leaf block contention**, không đồng nghĩa với row lock contention trên cùng một hàng. Các session có thể đang insert những hàng khác nhau, nhưng vẫn tranh chấp cùng block index vì khóa mới có vị trí gần nhau trong thứ tự index.

### 2.1. Vì sao sequence CACHE không tự giải quyết hot leaf block?

Sequence CACHE giúp Oracle cấp phát một nhóm giá trị sequence trong bộ nhớ, giảm nhu cầu truy cập/ghi dictionary và giảm một số loại sequence allocation contention. Tuy nhiên, các giá trị được cấp phát vẫn có thể tăng dần và vẫn đi vào vùng cuối của B-tree index thông thường.

Vì vậy cần phân biệt:

| Vấn đề | Cơ chế liên quan | Hướng xử lý có thể xem xét |
|---|---|---|
| Cạnh tranh cấp phát sequence | Sequence state/allocation, đặc biệt với cấu hình và workload RAC | CACHE, NOORDER khi phù hợp, scalable sequence tùy release |
| Cạnh tranh leaf block của index | Nhiều insert vào cùng vùng cuối B-tree | Reverse key index, hash partitioned index, thiết kế khóa/phân vùng khác |
| Cạnh tranh trên cùng một hàng | Row lock/TX row lock contention | Điều chỉnh transaction và logic cập nhật |
| Cạnh tranh buffer/block khác | Buffer cache, ITL hoặc block nóng | Xác định block/segment và loại wait trước khi thay đổi |

Tăng CACHE có thể cải thiện chi phí cấp phát sequence nhưng không đảo thứ tự khóa trong index. Nếu bottleneck nằm ở right-hand leaf block, cần giải quyết ở thiết kế index hoặc phân phối khóa.

### 2.2. RAC và right-hand index contention

Trong Oracle RAC, mỗi instance có buffer cache riêng nhưng các instance cùng truy cập database files. Khi một index leaf block bị nhiều instance sửa, block có thể phải được chuyển quyền sở hữu hoặc truyền qua interconnect theo cơ chế Cache Fusion. Nếu một leaf block nóng liên tục chuyển giữa các instance, có thể xuất hiện global cache wait.

Reverse key index có thể phân tán các khóa tăng dần tới nhiều leaf block, nhờ đó giảm tập trung trên một block ở mép phải. Tuy nhiên, nó không loại bỏ mọi loại RAC contention và không thay thế việc phân tích AWR/ASH hoặc wait event thực tế.

## 3. Reverse key index hoạt động như thế nào?

Reverse key index là B-tree index mà Oracle đảo thứ tự byte của khóa trước khi sắp xếp/lưu index entry. Đây là phép đảo byte, không phải đảo chuỗi ký tự theo cách người dùng nhìn thấy.

Ví dụ minh họa về ý tưởng byte:

~~~text
Khóa số ban đầu:       [byte A] [byte B] [byte C]
Khóa trong reverse:    [byte C] [byte B] [byte A]
~~~

Đây là mô hình khái niệm; biểu diễn nội bộ thực tế phụ thuộc datatype và cách Oracle mã hóa giá trị. Điều quan trọng là thứ tự byte bị đảo khiến các giá trị tăng dần liên tiếp không còn nằm cạnh nhau theo thứ tự số học thông thường trong B-tree.

Với sequence tăng dần, các khóa mới có thể được phân bố ra nhiều vị trí leaf block hơn thay vì tập trung ở một đầu mút của index.

### 3.1. Reverse key không thay đổi giá trị cột trong bảng

Giả sử bảng có ID 1001, 1002, 1003. Reverse key index chỉ thay đổi cách khóa được tổ chức trong index. Giá trị trong table vẫn là 1001, 1002, 1003.

Các câu truy vấn vẫn viết theo giá trị gốc:

~~~sql
SELECT *
FROM orders
WHERE order_id = 1002;
~~~

Oracle có thể dùng reverse key index để tìm khóa bằng chính giá trị 1002. Ứng dụng không cần tự đảo ID trước khi truy vấn.

### 3.2. Phân tán insert

B-tree bình thường sắp xếp theo khóa gốc. Reverse key index thay đổi thứ tự lưu trữ, làm những khóa tăng dần gần nhau về giá trị có thể đi tới các vị trí khác nhau trong index.

~~~text
Normal B-tree index:
1001 -> 1002 -> 1003 -> 1004 -> 1005 -> vùng cuối
                                            ^
                                            |
                                   nhiều insert tập trung

Reverse key B-tree:
Khóa gốc 1001 -> vị trí index A
Khóa gốc 1002 -> vị trí index B
Khóa gốc 1003 -> vị trí index C
Khóa gốc 1004 -> vị trí index D
Khóa gốc 1005 -> vị trí index E

=> insert có thể phân tán trên nhiều leaf block
~~~

Sơ đồ chỉ diễn tả xu hướng. Mức độ phân tán phụ thuộc byte representation, kiểu khóa, dải giá trị và dữ liệu thực tế; reverse key không bảo đảm phân phối đồng đều tuyệt đối.

### 3.3. Reverse key vẫn là B-tree index

Reverse key index không phải hash index. Nó vẫn có cấu trúc B-tree và vẫn hỗ trợ tìm kiếm theo equality khi điều kiện phù hợp. Điểm thay đổi quan trọng là thứ tự khóa trong index không còn tương ứng với thứ tự tăng/giảm của giá trị gốc.

## 4. Tạo reverse key index

Có thể tạo reverse key index bằng từ khóa REVERSE:

~~~sql
CREATE INDEX ix_orders_order_id_rev
ON orders (order_id)
REVERSE;
~~~

Ví dụ với khóa duy nhất:

~~~sql
CREATE UNIQUE INDEX ux_orders_order_id_rev
ON orders (order_id)
REVERSE;
~~~

Reverse key index vẫn có thể là unique index và vẫn thực thi uniqueness trên khóa. Việc đảo byte không làm mất tính duy nhất của giá trị gốc.

Nếu primary key hoặc unique constraint được hỗ trợ bởi một reverse key index, cần thiết kế rõ vì tính năng kiểm tra uniqueness vẫn hoạt động nhưng các truy vấn range theo khóa đó không thể dựa vào thứ tự index như B-tree thường.

### 4.1. Reverse key index trên composite key

Có thể tạo index nhiều cột:

~~~sql
CREATE INDEX ix_event_account_seq_rev
ON account_events (account_id, event_seq)
REVERSE;
~~~

Đây vẫn là index composite. Tuy nhiên, do key order bị đảo, không nên kỳ vọng các nguyên tắc range scan/prefix access của composite B-tree thông thường sẽ hoạt động theo thứ tự giá trị gốc. Hãy kiểm tra execution plan của các predicate thực tế.

Nếu workload chủ yếu tra cứu chính xác theo toàn bộ khóa hoặc các cột phù hợp, reverse key có thể hữu ích. Nếu workload cần range theo account/time hoặc đọc các sự kiện liền kề, reverse key có thể làm truy vấn kém hiệu quả.

### 4.2. Chuyển index hiện có sang reverse hoặc non-reverse

Có thể rebuild index để thay đổi đặc tính reverse:

~~~sql
ALTER INDEX ix_orders_order_id
REBUILD REVERSE;
~~~

Để chuyển reverse key index trở lại B-tree index thông thường:

~~~sql
ALTER INDEX ix_orders_order_id_rev
REBUILD NOREVERSE;
~~~

Rebuild là thao tác bảo trì index cần kế hoạch về thời gian, không gian tạm, I/O, lock/availability và ảnh hưởng DML tùy tùy chọn/cấu hình. Không chạy rebuild tùy tiện trên index lớn trong giờ cao điểm.

### 4.3. Kiểm tra DDL index

Có thể xem DDL được lưu trong data dictionary:

~~~sql
SELECT DBMS_METADATA.GET_DDL(
           'INDEX',
           'IX_ORDERS_ORDER_ID_REV',
           USER
       )
FROM dual;
~~~

Kết quả DDL giúp xác nhận index được tạo với REVERSE hay không. Dictionary view USER_INDEXES cung cấp nhiều thông tin về index như uniqueness, status, leaf blocks và clustering factor; không nên suy luận đặc tính reverse chỉ từ tên index do ứng dụng đặt.

## 5. Equality lookup: reverse key index vẫn hữu ích

Reverse key index giữ khả năng tìm kiếm bằng khóa chính xác. Ví dụ:

~~~sql
SELECT order_id, customer_id, order_status
FROM orders
WHERE order_id = :order_id;
~~~

Với index phù hợp, Oracle có thể thực hiện index unique scan hoặc index range scan tùy tính duy nhất và cấu trúc truy vấn. Sau khi tìm được entry, Oracle có thể dùng ROWID để truy cập hàng trong table.

Các trường hợp thường phù hợp:

- Tìm một đơn hàng theo primary key.
- Tìm một event theo ID duy nhất.
- Kiểm tra tồn tại một khóa chính xác.
- Join bằng điều kiện equality trên khóa có index.
- Cập nhật/xóa một hàng theo khóa equality.

Ví dụ:

~~~sql
UPDATE orders
SET order_status = 'SHIPPED'
WHERE order_id = :order_id;
~~~

Nếu workload có nhiều insert và lookup equality theo ID, reverse key index có thể là một lựa chọn đáng cân nhắc khi đã xác định hot leaf block contention là bottleneck.

### 5.1. Equality trên composite index

Với index:

~~~sql
CREATE INDEX ix_event_account_seq_rev
ON account_events (account_id, event_seq)
REVERSE;
~~~

Một truy vấn equality theo cả hai cột:

~~~sql
SELECT event_id, account_id, event_seq
FROM account_events
WHERE account_id = :account_id
  AND event_seq = :event_seq;
~~~

có thể sử dụng index nếu optimizer thấy có lợi. Cần phân biệt truy vấn này với yêu cầu lấy một dải event_seq của một account.

## 6. Range query: điểm đánh đổi lớn nhất

B-tree index thông thường sắp xếp khóa theo thứ tự, nên hỗ trợ các predicate khoảng như:

~~~sql
SELECT order_id, order_date
FROM orders
WHERE order_id BETWEEN 100000 AND 101000;
~~~

Oracle có thể bắt đầu tại leaf chứa khóa đầu khoảng và duyệt tiếp các leaf entry đến khóa cuối khoảng.

Với reverse key index, thứ tự byte đã bị đảo. Các khóa có giá trị gốc nằm gần nhau không nhất thiết nằm liền nhau trong index. Vì vậy, reverse key index **không hỗ trợ index range scan theo thứ tự khóa gốc**.

Các predicate thường không thể tận dụng reverse key index như B-tree thường:

~~~sql
WHERE order_id BETWEEN :low_id AND :high_id
~~~

~~~sql
WHERE order_id > :last_seen_id
~~~

~~~sql
WHERE order_id < :cutoff_id
~~~

~~~sql
ORDER BY order_id
~~~

Oracle có thể chọn full table scan, một index khác, hoặc một đường truy cập khác. Không nên kỳ vọng reverse key index sẽ giúp các truy vấn này nhanh hơn chỉ vì index có tồn tại.

### 6.1. So sánh equality và range

| Predicate | B-tree thường | Reverse key B-tree |
|---|---|---|
| id = :id | Có thể dùng index equality lookup | Có thể dùng index equality lookup |
| id IN (:a, :b, :c) | Có thể dùng nhiều equality probes | Có thể dùng nhiều equality probes |
| id BETWEEN :a AND :b | Có thể dùng index range scan | Không hỗ trợ range scan theo thứ tự ID |
| id > :id | Có thể dùng index range scan | Không hỗ trợ range scan theo thứ tự ID |
| ORDER BY id | Có thể đọc theo thứ tự index nếu plan phù hợp | Không thể dựa vào thứ tự reverse index để trả thứ tự ID gốc |
| Lấy các ID liên tiếp | Thường phù hợp | Thường không phù hợp |

“Có thể dùng” không có nghĩa optimizer luôn chọn index. Oracle quyết định theo cost, statistics, selectivity, clustering factor, số cột cần đọc và các yếu tố khác.

### 6.2. Vì sao không thể range scan sau khi đảo byte?

Giả sử giá trị gốc có thứ tự:

~~~text
1001 < 1002 < 1003 < 1004 < 1005
~~~

Sau khi đảo byte, thứ tự index không còn bảo toàn thứ tự số học này. Các entry thỏa điều kiện 1002 đến 1004 có thể nằm rải rác ở nhiều leaf block. Oracle không thể chỉ đi từ một leaf block đầu khoảng tới leaf block cuối khoảng theo thứ tự gốc như với B-tree bình thường.

Để trả kết quả, database có thể phải xem xét nhiều entry hoặc dùng đường truy cập khác; lợi ích của index range scan bị mất.

### 6.3. ORDER BY và MIN/MAX

Không dùng reverse key index khi mục tiêu chính là đọc dữ liệu theo thứ tự khóa, ví dụ:

~~~sql
SELECT order_id
FROM orders
ORDER BY order_id DESC
FETCH FIRST 100 ROWS ONLY;
~~~

B-tree thường có thể hỗ trợ một số kế hoạch đọc index theo thứ tự phù hợp. Reverse key index không lưu thứ tự số học gốc, vì vậy không thể thay thế B-tree thường cho loại truy vấn này.

Các truy vấn MIN/MAX trên khóa cũng cần đánh giá tương tự. Nếu cần tìm min/max hoặc top-N theo giá trị gốc, reverse key index thường không phải index thích hợp.

## 7. Reverse key index và composite index

Với composite B-tree thông thường, thứ tự cột và leading column ảnh hưởng khả năng truy cập. Ví dụ:

~~~sql
CREATE INDEX ix_orders_customer_date
ON orders (customer_id, order_date);
~~~

Index này có thể phù hợp cho:

~~~sql
WHERE customer_id = :customer_id
  AND order_date >= :from_date
  AND order_date < :to_date
~~~

vì Oracle có thể định vị vùng của một customer rồi range scan theo date.

Nếu tạo reverse key:

~~~sql
CREATE INDEX ix_orders_customer_date_rev
ON orders (customer_id, order_date)
REVERSE;
~~~

thứ tự byte bị đảo làm mất đặc tính sắp xếp theo customer/date gốc. Không nên mặc định rằng predicate equality trên leading column rồi range trên cột thứ hai vẫn dùng được theo cách của index thường.

### 7.1. Chọn index theo mẫu truy cập

| Mẫu truy vấn | Index thường | Reverse key |
|---|---|---|
| Equality theo toàn bộ khóa | Phù hợp | Có thể phù hợp |
| Equality theo khóa duy nhất | Phù hợp | Có thể phù hợp |
| Equality leading key, range trailing key | Có thể rất phù hợp | Thường không phù hợp cho range |
| Range theo timestamp/sequence | Phù hợp nếu key order tương ứng | Không phù hợp |
| Lấy N bản ghi mới nhất | Có thể phù hợp với DESC/order phù hợp | Không phù hợp để dựa vào thứ tự khóa gốc |
| Insert đồng thời bằng ID tăng dần | Có thể gặp right-hand contention | Có thể giảm tập trung leaf block |

Đừng chuyển tất cả index trên bảng sang REVERSE. Một bảng có thể cần nhiều index khác nhau phục vụ các workload khác nhau; reverse key chỉ nên áp dụng cho index mà lợi ích ghi quan trọng hơn khả năng range scan.

## 8. Reverse key index, sequence và khóa tăng dần

Một pattern phổ biến:

~~~sql
CREATE SEQUENCE orders_seq
    START WITH 1
    INCREMENT BY 1
    CACHE 1000
    NOORDER;

CREATE TABLE orders (
    order_id NUMBER PRIMARY KEY,
    customer_id NUMBER NOT NULL,
    order_date DATE NOT NULL
);
~~~

Khi insert:

~~~sql
INSERT INTO orders (order_id, customer_id, order_date)
VALUES (orders_seq.NEXTVAL, :customer_id, SYSDATE);
~~~

Nếu primary key được hỗ trợ bởi B-tree index bình thường, khóa mới có xu hướng đi về vùng cuối index.

Có thể tạo reverse key unique index để phân tán insert:

~~~sql
CREATE UNIQUE INDEX ux_orders_order_id_rev
ON orders (order_id)
REVERSE;
~~~

Sau đó dùng index này để hỗ trợ constraint hoặc truy vấn equality theo ID tùy cách thiết kế constraint/index. Khi thay index hỗ trợ constraint hiện hữu, cần tuân theo quy trình quản lý constraint và index phù hợp, không đơn giản drop index đang được constraint sử dụng.

### 8.1. Sequence CACHE

CACHE giữ trước một dải giá trị sequence trong bộ nhớ, giúp giảm overhead cấp phát. Ví dụ:

~~~sql
CREATE SEQUENCE orders_seq
    START WITH 1
    INCREMENT BY 1
    CACHE 1000;
~~~

CACHE không bảo đảm sequence liên tục không có gap. Instance restart, rollback hoặc việc cấp phát không sử dụng hết cache có thể tạo khoảng trống. Sequence không phải công cụ tạo số chứng từ liên tục không thiếu số.

CACHE có thể giảm sequence allocation overhead nhưng không thay đổi thứ tự key trong B-tree. Nếu right-hand leaf block vẫn là bottleneck, tăng CACHE một mình có thể không giải quyết được.

### 8.2. ORDER và NOORDER trong RAC

Sequence có thể được cấu hình ORDER hoặc NOORDER. ORDER yêu cầu bảo đảm thứ tự cấp phát theo yêu cầu của sequence trong môi trường hỗ trợ; NOORDER cho phép cấp phát không bảo đảm thứ tự toàn cục giữa các instance. Với workload RAC cần throughput cao, NOORDER thường được cân nhắc nếu nghiệp vụ không yêu cầu thứ tự toàn cục.

Dù dùng NOORDER, giá trị sequence vẫn có thể tăng trong từng cache/instance theo cách riêng và vẫn có thể tạo vùng insert nóng tùy thiết kế. Reverse key index xử lý vấn đề phân bố vị trí index, khác với cách sequence phân phối số.

### 8.3. Scalable sequence

Một số phiên bản Oracle hỗ trợ scalable sequence để phân tán giá trị được sinh ra theo cấu trúc có thành phần định danh nhằm giảm contention khi cấp phát sequence trong workload concurrent/RAC. Cú pháp và khả năng phụ thuộc release.

Scalable sequence có thể giúp giảm một loại contention khác, nhưng cần cân nhắc:
- Giá trị sinh ra có thể không còn mang ý nghĩa tăng liên tục đơn giản theo thời gian.
- Dải số và độ dài key có thể thay đổi.
- Ứng dụng không được giả định sequence là timestamp hoặc thứ tự commit.
- Cần kiểm tra range query, unique key và yêu cầu nghiệp vụ.

Scalable sequence và reverse key index không phải hai tên gọi của cùng một giải pháp. Một bên thay đổi cách sinh/phân phối giá trị; bên kia thay đổi cách lưu key trong B-tree.

## 9. Reverse key index trong workload RAC

Trong RAC, nhiều instance có thể cùng insert vào một bảng dùng primary key tăng dần. Với B-tree thường, vùng leaf block cuối có thể trở thành hot block được yêu cầu qua Cache Fusion.

Reverse key index có thể phân tán các insert ra nhiều leaf block và giảm việc nhiều instance cùng tranh chấp một block. Tuy nhiên:

- Nó không loại bỏ row lock nếu nhiều session cập nhật cùng hàng.
- Nó không loại bỏ contention ở sequence allocation.
- Nó không loại bỏ contention ở table block nếu table itself có hot block.
- Nó không giải quyết mọi global cache wait.
- Nó đánh đổi range scan và thứ tự index theo khóa gốc.

Khi workload RAC cần cả insert throughput và range query, có thể phải cân nhắc nhiều index hoặc partitioning strategy thay vì dùng reverse key cho index duy nhất.

## 10. Phương án thay thế hoặc bổ sung

Reverse key index là một công cụ chuyên biệt. Các lựa chọn khác có thể phù hợp hơn tùy workload.

### 10.1. Hash-partitioned global index

Một global index partitioned theo hash có thể phân phối các key vào nhiều index partition. Điều này có thể giảm tập trung ghi vào một vùng duy nhất mà vẫn giữ cấu trúc B-tree bên trong từng partition.

Khái niệm:

~~~text
Key -> HASH(key) -> Index partition
                      |       |       |
                      v       v       v
                    Part 1  Part 2  Part 3
~~~

Ví dụ cú pháp minh họa cho global hash-partitioned index:

~~~sql
CREATE INDEX ix_orders_id_hash
ON orders (order_id)
GLOBAL PARTITION BY HASH (order_id)
PARTITIONS 8;
~~~

Cú pháp/khả năng cụ thể phụ thuộc loại bảng, phiên bản và điều kiện partitioning. Hash partitioning phân phối khóa vào partition theo hash, nên range trên giá trị gốc có thể phải truy cập nhiều partition. Hãy kiểm tra execution plan và tài liệu đúng release.

### 10.2. Table/index partitioning

Nếu bảng được partition theo ngày hoặc một thuộc tính nghiệp vụ, local indexes có thể phân phối dữ liệu và index segment theo partition. Điều này hữu ích khi workload có predicate partition key và vòng đời dữ liệu theo partition.

Partitioning không tự động loại bỏ right-hand contention nếu tất cả insert vẫn đi vào một partition/index leaf cuối. Cần chọn partition key và local/global index strategy phù hợp với pattern ghi.

### 10.3. Thiết kế khóa có phân tán

Một khóa có thành phần shard/instance/tenant hoặc hash prefix có thể phân phối insert tốt hơn, nhưng thay đổi semantics của khóa và có thể ảnh hưởng range/order. Ví dụ, thêm tenant prefix vào composite key có thể phân tán workload giữa tenant nếu tenant traffic không quá skewed. Không nên tự thêm random prefix nếu ứng dụng cần thứ tự toàn cục hoặc khóa đơn giản.

### 10.4. Reverse key kết hợp index thường khác trên cùng bảng

Có thể duy trì một reverse key index phục vụ insert/equality và một index khác phục vụ range query, nếu chi phí storage/DML cho hai index được chấp nhận. Tuy nhiên, mỗi index bổ sung làm tăng chi phí insert/update/delete vì Oracle phải duy trì thêm cấu trúc.

Ví dụ minh họa:
- Unique reverse index trên ORDER_ID để giảm hot leaf khi insert và hỗ trợ equality lookup.
- Index thường trên ORDER_DATE, ORDER_ID để phục vụ báo cáo theo ngày và phân trang theo ngày.

Không nên tạo cả normal và reverse index trên cùng một cột chỉ để “phòng khi cần”; phải có query workload cụ thể và đo chi phí.

## 11. Khi nào nên và không nên dùng reverse key index?

### 11.1. Dấu hiệu nên đánh giá reverse key

- Bảng nhận insert đồng thời rất cao.
- Index key tăng dần hoặc tăng gần liên tục.
- AWR/ASH hoặc session monitoring cho thấy contention liên quan index leaf/block.
- Insert tập trung vào right-most leaf block.
- Truy vấn chủ yếu lookup equality theo key.
- Các báo cáo range/order theo key có thể dùng index khác hoặc chấp nhận đường truy cập khác.

### 11.2. Dấu hiệu không phù hợp

- Truy vấn thường xuyên dùng BETWEEN, >, < trên khóa index.
- Ứng dụng cần lấy ID mới nhất/cũ nhất theo thứ tự index.
- Truy vấn cần ORDER BY key và FETCH FIRST N.
- Index là đường truy cập quan trọng cho range pagination.
- Bottleneck thực tế nằm ở sequence allocation, row lock, table hot block hoặc một cơ chế khác.
- Insert concurrency thấp nên lợi ích phân tán không đáng chi phí mất range scan.

### 11.3. Bảng quyết định nhanh

| Workload | Hướng lựa chọn |
|---|---|
| Insert đồng thời cao, khóa sequence tăng dần, lookup equality | Đánh giá reverse key index |
| Insert đồng thời cao, cần range theo key thường xuyên | Đánh giá hash partitioning, partition strategy hoặc khóa phân tán; giữ B-tree thường nếu phù hợp |
| Đọc range/top-N theo ID là truy vấn trọng yếu | B-tree thường |
| Chỉ có sequence wait, không có index leaf contention | Điều tra CACHE/ORDER/scalable sequence và sequence workload |
| Nhiều update cùng một hàng | Điều tra row lock; reverse key không giải quyết |
| RAC có hot index block | Đo global cache contention và đánh giá reverse/hash partitioned index |

## 12. Đo và chẩn đoán index contention

Không nên tạo reverse key index chỉ vì thấy ID dùng sequence. Cần chứng minh bottleneck nằm ở index leaf block.

### 12.1. Kiểm tra wait event

DBA có thể quan sát session đang chờ:

~~~sql
SELECT sid,
       serial#,
       username,
       event,
       wait_class,
       seconds_in_wait,
       sql_id,
       blocking_session
FROM v$session
WHERE wait_class <> 'Idle'
ORDER BY seconds_in_wait DESC;
~~~

Một số event cần chú ý tùy phiên bản và workload:
- buffer busy waits;
- enq: TX - index contention;
- gc buffer busy acquire;
- gc buffer busy release;
- các event liên quan global cache hoặc index block.

Tên event chính xác và ý nghĩa có thể thay đổi giữa release. Hãy đọc wait event cùng object/segment, SQL_ID, module/action và thời điểm tải cao.

### 12.2. Xem thống kê theo segment

V$SEGMENT_STATISTICS có thể cung cấp các thống kê như logical reads, physical reads, buffer busy waits hoặc ITL waits theo segment, tùy release và statistic được hỗ trợ.

~~~sql
SELECT owner,
       object_name,
       subobject_name,
       statistic_name,
       value
FROM v$segment_statistics
WHERE owner = USER
  AND object_name IN ('IX_ORDERS_ID', 'IX_ORDERS_ORDER_ID_REV')
  AND statistic_name IN (
      'logical reads',
      'physical reads',
      'buffer busy waits',
      'ITL waits'
  )
ORDER BY object_name, statistic_name;
~~~

Đây là thống kê tích lũy. Khi so sánh, hãy ghi lại giá trị ở đầu và cuối cùng một khoảng thời gian/workload tương đương, rồi tính delta. Không so sánh raw cumulative value giữa hai segment có tuổi đời hoặc lượng DML khác nhau.

### 12.3. Xem thông tin index

~~~sql
SELECT index_name,
       table_name,
       uniqueness,
       status,
       blevel,
       leaf_blocks,
       distinct_keys,
       clustering_factor,
       num_rows,
       last_analyzed
FROM user_indexes
WHERE table_name = 'ORDERS'
ORDER BY index_name;
~~~

Các thông tin như BLEVEL, LEAF_BLOCKS, DISTINCT_KEYS, CLUSTERING_FACTOR giúp hiểu cấu trúc và thống kê index, nhưng không tự chứng minh có contention. Hãy kết hợp với wait event, segment stats và workload.

### 12.4. Xác định SQL gây insert vào index

Kết hợp SQL_ID với SQL text và module/action của session để tìm statement insert/update/delete trên bảng. Nếu có quyền, AWR/ASH có thể giúp phân tích theo thời gian và object; việc sử dụng AWR/ASH phụ thuộc license và chính sách môi trường.

Không bật trace toàn hệ thống hoặc truy vấn các view quản trị với quyền cao chỉ để tìm một index nóng nếu chưa có phạm vi điều tra phù hợp.

## 13. So sánh execution plan: equality và range

Tạo hai bảng lab độc lập để so sánh, tránh duy trì đồng thời cả normal và reverse index trên cùng một cột trong bài đo insert.

### 13.1. Tạo dữ liệu lab

Chỉ thực hành trong schema DEV/TEST được cấp quyền:

~~~sql
CREATE TABLE lab_normal_key (
    id      NUMBER NOT NULL,
    payload VARCHAR2(50)
);

CREATE TABLE lab_reverse_key (
    id      NUMBER NOT NULL,
    payload VARCHAR2(50)
);

INSERT INTO lab_normal_key (id, payload)
SELECT LEVEL, 'row-' || TO_CHAR(LEVEL)
FROM dual
CONNECT BY LEVEL <= 100000;

INSERT INTO lab_reverse_key (id, payload)
SELECT LEVEL, 'row-' || TO_CHAR(LEVEL)
FROM dual
CONNECT BY LEVEL <= 100000;

COMMIT;
~~~

Tạo index:

~~~sql
CREATE INDEX ix_lab_normal_key
ON lab_normal_key (id);

CREATE INDEX ix_lab_reverse_key
ON lab_reverse_key (id)
REVERSE;

BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(USER, 'LAB_NORMAL_KEY');
    DBMS_STATS.GATHER_TABLE_STATS(USER, 'LAB_REVERSE_KEY');
END;
/
~~~

### 13.2. Equality lookup trên index thường

~~~sql
EXPLAIN PLAN FOR
SELECT payload
FROM lab_normal_key
WHERE id = 50000;

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

### 13.3. Equality lookup trên reverse key index

~~~sql
EXPLAIN PLAN FOR
SELECT payload
FROM lab_reverse_key
WHERE id = 50000;

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

Cả hai truy vấn có thể dùng index equality lookup nếu optimizer đánh giá có lợi. Tên operation cụ thể phụ thuộc index uniqueness, projection và cost.

### 13.4. Range query trên index thường

~~~sql
EXPLAIN PLAN FOR
SELECT payload
FROM lab_normal_key
WHERE id BETWEEN 50000 AND 50100;

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

Optimizer có thể chọn INDEX RANGE SCAN trên B-tree thường.

### 13.5. Range query trên reverse key index

~~~sql
EXPLAIN PLAN FOR
SELECT payload
FROM lab_reverse_key
WHERE id BETWEEN 50000 AND 50100;

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

Reverse key index không hỗ trợ range scan theo thứ tự ID gốc. Optimizer có thể chọn full table scan hoặc đường truy cập khác. Đừng ép index hint để kết luận rằng reverse index có khả năng range scan; hãy quan sát operation thực tế.

### 13.6. Xem predicate và thống kê thực thi

Khi thực thi truy vấn thật trong lab, có thể dùng:

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       payload
FROM lab_normal_key
WHERE id BETWEEN 50000 AND 50100;

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY_CURSOR(NULL, NULL, 'ALLSTATS LAST +PREDICATE'));
~~~

Lặp lại cho bảng reverse. Đảm bảo câu lệnh vừa chạy là cursor được hiển thị, và statistics collection được bật cho statement đó. So sánh actual rows, buffers, access predicate và operation; không chỉ nhìn cost ước lượng.

## 14. Thực hành concurrency để quan sát right-hand contention

Một session đơn lẻ insert tuần tự thường không thể hiện rõ hot leaf block contention. Cần workload có nhiều session đồng thời.

### 14.1. Tạo bảng so sánh riêng

~~~sql
CREATE TABLE lab_insert_normal (
    id      NUMBER NOT NULL,
    payload VARCHAR2(100)
);

CREATE TABLE lab_insert_reverse (
    id      NUMBER NOT NULL,
    payload VARCHAR2(100)
);

CREATE UNIQUE INDEX ux_lab_insert_normal
ON lab_insert_normal (id);

CREATE UNIQUE INDEX ux_lab_insert_reverse
ON lab_insert_reverse (id)
REVERSE;
~~~

### 14.2. Dùng sequence cho mỗi bảng

~~~sql
CREATE SEQUENCE lab_normal_seq START WITH 1 INCREMENT BY 1 CACHE 1000 NOORDER;
CREATE SEQUENCE lab_reverse_seq START WITH 1 INCREMENT BY 1 CACHE 1000 NOORDER;
~~~

Mỗi worker/session insert một số lượng lớn hàng vào bảng tương ứng:

~~~sql
INSERT INTO lab_insert_normal (id, payload)
VALUES (lab_normal_seq.NEXTVAL, 'normal');

COMMIT;
~~~

~~~sql
INSERT INTO lab_insert_reverse (id, payload)
VALUES (lab_reverse_seq.NEXTVAL, 'reverse');

COMMIT;
~~~

Lặp lại nhiều lần từ nhiều session hoặc dùng một công cụ benchmark có kiểm soát. Không chạy hai workload cùng lúc trên cùng một index nếu mục tiêu là so sánh độc lập; hãy giữ số session, số hàng, payload, commit frequency và thời gian chạy tương đương.

### 14.3. So sánh kết quả

Ghi nhận:
- Tổng số hàng được insert.
- Rows/second hoặc thời gian hoàn tất.
- Wait events theo thời gian.
- Segment statistics trước/sau.
- CPU, I/O, redo và commit latency.
- Ảnh hưởng tới truy vấn equality và range liên quan.

Reverse key index có thể giảm một số loại leaf block contention, nhưng không bảo đảm throughput luôn tăng. Nếu bottleneck nằm ở redo, log file sync, sequence allocation hoặc storage I/O, kết quả có thể khác.

### 14.4. Không dùng bài lab làm benchmark production

Bài thực hành chỉ minh họa phương pháp. Kết quả phụ thuộc CPU, storage, cache, database release, concurrency, index size, RAC và các workload đồng thời. Muốn thay đổi index production, cần benchmark với dữ liệu và tỷ lệ đọc/ghi đại diện.

## 15. Chuyển đổi index và kế hoạch triển khai

Nếu đã xác định một B-tree index thường bị right-hand contention và workload chủ yếu equality, có thể đánh giá chuyển sang reverse key.

Một quy trình triển khai có kiểm soát:

1. Xác định index và SQL gây contention.
2. Phân loại workload: equality, range, ORDER BY, pagination, MIN/MAX.
3. Kiểm tra các constraint phụ thuộc index.
4. Tạo thử reverse index trong môi trường kiểm thử.
5. Đối chiếu execution plan cho các SQL quan trọng.
6. Benchmark insert concurrency và read workload.
7. Lập kế hoạch rebuild/constraint handling, storage, availability và rollback.
8. Triển khai trong cửa sổ phù hợp.
9. Theo dõi wait events, segment stats, SQL latency và lỗi ứng dụng.
10. Nếu trade-off không chấp nhận được, rebuild NOREVERSE hoặc khôi phục index strategy theo kế hoạch.

### 15.1. Rebuild có thể cần thêm tài nguyên

Rebuild index có thể cần thêm không gian segment và TEMP, I/O, CPU và có thể ảnh hưởng DML tùy cách thực hiện. Online rebuild có các giới hạn và điều kiện riêng theo loại index, release và license. Không mặc định rằng mọi reverse key index đều có thể online rebuild trong mọi môi trường.

### 15.2. Unique constraint và index

Nếu index đang hỗ trợ primary key/unique constraint, phải kiểm tra cách constraint được gắn với index. Không drop index trước khi hiểu dependency. Có thể cần dùng ALTER TABLE ENABLE/DISABLE hoặc USING INDEX theo kế hoạch constraint cụ thể, nhưng các thao tác này có thể ảnh hưởng tính toàn vẹn và concurrency. Thực hiện trong môi trường thử nghiệm trước.

## 16. Những hiểu lầm thường gặp

| Hiểu lầm | Cách hiểu đúng |
|---|---|
| Reverse key đảo chữ số ID | Oracle đảo byte của key trong index, không sửa giá trị cột |
| Reverse key là hash index | Nó vẫn là B-tree index |
| Reverse key làm insert nhanh hơn trong mọi trường hợp | Nó có thể giảm right-hand leaf block contention khi đó là bottleneck |
| Reverse key không hỗ trợ equality | Equality lookup vẫn có thể dùng reverse key index |
| Reverse key hỗ trợ BETWEEN giống B-tree thường | Nó không hỗ trợ range scan theo thứ tự giá trị gốc |
| CACHE lớn giải quyết mọi hot index block | CACHE giảm sequence allocation overhead, không thay thứ tự index key |
| Sequence không có gap nếu dùng ORDER | Sequence không bảo đảm gap-free; rollback/cache/restart có thể tạo gap |
| Mọi bảng dùng sequence đều cần reverse key | Chỉ cân nhắc khi có concurrency và bằng chứng contention |
| Reverse key loại bỏ row lock | Không; row lock vẫn cần cho DML cùng hàng |
| Reverse key luôn phân phối hoàn toàn đồng đều | Mức phân tán phụ thuộc byte representation và phân bố khóa |
| Có reverse index là optimizer sẽ dùng nó | Optimizer vẫn quyết định theo cost và predicate |
| Có thể giữ reverse index làm index duy nhất cho mọi truy vấn | Range, order và top-N theo key gốc thường cần index thường hoặc đường truy cập khác |

## 17. Câu hỏi ôn tập

**Câu 1.** Vì sao khóa tăng dần có thể gây right-hand index contention?

**Đáp án:** Khóa mới thường được chèn vào vùng cuối của B-tree index. Nhiều session đồng thời insert có thể cùng truy cập leaf block cuối, gây cạnh tranh buffer/block.

**Câu 2.** Reverse key index thay đổi điều gì?

**Đáp án:** Oracle đảo thứ tự byte của index key trước khi lưu, làm thay đổi vị trí sắp xếp trong B-tree và có thể phân tán các insert có khóa tăng dần.

**Câu 3.** Reverse key index có còn là B-tree không?

**Đáp án:** Có. Nó là B-tree index với key byte đã được đảo.

**Câu 4.** Reverse key index có hỗ trợ WHERE id = :id không?

**Đáp án:** Có thể. Equality lookup vẫn được hỗ trợ nếu optimizer thấy index phù hợp.

**Câu 5.** Vì sao reverse key index không phù hợp cho BETWEEN?

**Đáp án:** Thứ tự byte đã bị đảo nên các giá trị liên tiếp theo thứ tự số học gốc không nằm liên tiếp trong index; không thể thực hiện range scan theo thứ tự key gốc.

**Câu 6.** Reverse key index có giúp ORDER BY id không?

**Đáp án:** Không thể dựa vào thứ tự reverse index để trả kết quả theo thứ tự ID gốc; truy vấn có thể cần sort hoặc đường truy cập khác.

**Câu 7.** CACHE của sequence có thay thế reverse key index không?

**Đáp án:** Không. CACHE giảm overhead cấp phát sequence; reverse key thay đổi phân bố key trong index để giảm hot leaf block.

**Câu 8.** Reverse key index có thể là unique index không?

**Đáp án:** Có. Oracle vẫn kiểm tra uniqueness của giá trị khóa gốc.

**Câu 9.** Khi nào nên đánh giá reverse key index?

**Đáp án:** Khi insert đồng thời cao với khóa tăng dần, có bằng chứng right-hand leaf block contention và workload đọc chủ yếu equality.

**Câu 10.** Khi nào nên giữ B-tree index thường?

**Đáp án:** Khi truy vấn range, ORDER BY, top-N hoặc phân trang theo khóa gốc là quan trọng.

**Câu 11.** Reverse key index có giải quyết TX row lock contention không?

**Đáp án:** Không. Row lock contention là xung đột trên dữ liệu/transaction; reverse key xử lý phân bố insert trong index.

**Câu 12.** Làm sao kiểm tra lợi ích trước khi triển khai?

**Đáp án:** Benchmark normal và reverse index với workload đồng thời tương đương, đo wait event, segment statistics, throughput và execution plan của equality/range query.

## Kết luận

**Reverse key index là một B-tree index được Oracle đảo thứ tự byte của khóa để phân tán các insert có khóa tăng dần khỏi vùng leaf block cuối.** Nó có thể giảm right-hand index leaf block contention trong workload ghi đồng thời cao, đặc biệt khi nhiều session hoặc nhiều RAC instance cùng insert khóa sequence tăng dần.

Đổi lại, reverse key index không bảo toàn thứ tự giá trị gốc nên không hỗ trợ index range scan theo khóa đó. Equality lookup vẫn có thể sử dụng index, nhưng BETWEEN, các điều kiện lớn hơn/nhỏ hơn, ORDER BY và top-N theo key thường cần B-tree index thông thường hoặc một thiết kế khác. Sequence CACHE, NOORDER và scalable sequence xử lý các khía cạnh cấp phát khóa khác nhau; chúng không tự thay thế việc phân tán vị trí insert trong index.

Trước khi chọn reverse key, hãy xác định wait event và segment gây contention, phân loại truy vấn đọc theo equality/range, thử nghiệm normal và reverse trên workload đại diện, rồi đánh giá toàn bộ chi phí đọc/ghi. Reverse key là một lựa chọn có chủ đích cho một mẫu workload cụ thể, không phải cấu hình mặc định cho mọi primary key tăng dần.

## Tài liệu Oracle tham khảo

- [Oracle Database 19c Administrator's Guide — Managing Indexes](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/managing-indexes.html): quản lý B-tree index, reverse key index và các thao tác rebuild.
- [Oracle Database 19c SQL Reference — CREATE INDEX](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/CREATE-INDEX.html): cú pháp tạo index và tùy chọn REVERSE.
- [Oracle Database 19c SQL Reference — ALTER INDEX](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/ALTER-INDEX.html): rebuild index và tùy chọn NOREVERSE.
- [Oracle Database 19c Concepts — Indexes and Index-Organized Tables](https://docs.oracle.com/en/database/oracle/oracle-database/19/cncpt/indexes-and-index-organized-tables.html): cấu trúc và hoạt động của B-tree index.
- [Oracle Database 19c Performance Tuning Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgdba/index.html): phân tích wait events, contention và hiệu năng database.

