# Hàm tổng hợp, GROUP BY và giới hạn ngữ nghĩa truy vấn

## 1. Mục tiêu và cách tư duy đúng với Cassandra

Trong cơ sở dữ liệu quan hệ, một truy vấn kiểu `SELECT status, SUM(amount) FROM orders GROUP BY status` thường là thao tác quen thuộc. Trong **Apache Cassandra**, CQL cũng có các hàm tổng hợp như `COUNT`, `MIN`, `MAX`, `SUM`, `AVG` và mệnh đề `GROUP BY`, nhưng **không có cùng khả năng nhóm dữ liệu tùy ý như SQL trên hệ quản trị quan hệ**.

Cassandra là cơ sở dữ liệu **wide-column phân tán**, được thiết kế để đọc/ghi hiệu quả theo **partition key** và lưu các hàng đã được sắp xếp theo **clustering key**. Vì vậy, khả năng tổng hợp phải được hiểu cùng với:

- **Partition key:** quyết định vị trí phân vùng dữ liệu trên các replica.
- **Clustering columns:** quyết định trật tự các hàng trong một partition, và là cơ sở cho việc nhóm theo tiền tố khóa chính.
- **Replication và consistency level:** ảnh hưởng cách coordinator đọc dữ liệu trên replica và mức xác nhận của kết quả.
- **Chi phí quét dữ liệu:** Cassandra không tự duy trì các phép đếm và tổng giá trị tùy ý cho từng truy vấn.

Sau bài này, người học có thể sử dụng các hàm tổng hợp CQL, viết truy vấn `GROUP BY` hợp lệ trên primary key, nhận diện giới hạn của `WHERE`, `HAVING`, `ORDER BY`, đánh giá chi phí quét nhiều hàng, và thiết kế bảng theo truy vấn khi ứng dụng Java cần thống kê thường xuyên.

## 2. Hàm tổng hợp CQL làm gì?

**Aggregate function** nhận các giá trị từ nhiều hàng trong tập kết quả rồi tạo một giá trị tổng hợp. Các hàm tích hợp thường gặp:

| Hàm | Ý nghĩa | Ví dụ CQL | Lưu ý |
| --- | --- | --- | --- |
| `COUNT(*)` | Đếm số hàng được nhìn thấy bởi truy vấn. | `COUNT(*)` | Cần duyệt dữ liệu liên quan; không phải số đếm lưu sẵn trong metadata của bảng. |
| `COUNT(column)` | Đếm các giá trị không `null` của cột. | `COUNT(total_amount)` | Có thể khác `COUNT(*)` nếu cột thông thường bị thiếu/không còn giá trị. |
| `MIN(column)` | Giá trị nhỏ nhất trong tập giá trị hợp lệ. | `MIN(total_amount)` | Không có nghĩa chọn “hàng có ngày sớm nhất” nếu dùng cột khác. |
| `MAX(column)` | Giá trị lớn nhất trong tập giá trị hợp lệ. | `MAX(total_amount)` | Không tự trả về toàn bộ hàng chứa giá trị lớn nhất. |
| `SUM(column)` | Tổng các giá trị số. | `SUM(total_amount)` | Phụ thuộc kiểu dữ liệu và tập hàng được quét. |
| `AVG(column)` | Giá trị trung bình của các giá trị số. | `AVG(total_amount)` | Kiểu dữ liệu/độ chính xác ảnh hưởng kết quả hiển thị. |

Những aggregate này thường bỏ qua giá trị `null` của cột đầu vào (riêng `COUNT(*)` đếm hàng). `COUNT(*)` đếm **hàng logic hiện còn hiển thị tại thời điểm đọc**, không đếm mọi bản ghi vật lý trong SSTable: dữ liệu hết TTL, tombstone và dữ liệu được reconcile theo replica có thể làm kết quả khác số mục lịch sử trên đĩa.

Không có `GROUP BY`, một truy vấn aggregate trả về **một kết quả tổng hợp cho tập hàng phù hợp**:

~~~sql
SELECT COUNT(*) AS order_count,
       SUM(total_amount) AS gross_amount,
       MIN(total_amount) AS smallest_order,
       MAX(total_amount) AS largest_order,
       AVG(total_amount) AS average_order
FROM orders_lab.orders_by_store_day
WHERE store_id = 'store-A';
~~~

Truy vấn trên sẽ được thực hiện sau khi tạo bảng và nạp dữ liệu ở mục 3. Các alias `AS order_count`, `AS gross_amount` giúp Java driver đọc kết quả bằng tên có ý nghĩa.

> **Cần nhớ:** CQL aggregate là phép tính trên dữ liệu truy vấn phải đọc. Đừng suy ra `COUNT(*)` là phép đếm tức thời `O(1)`, đặc biệt khi quét một partition lớn hoặc toàn bảng.

## 3. Dữ liệu thực hành: nhóm đơn hàng theo ngày trong một cửa hàng

Giả sử hệ thống thương mại điện tử cần trả lời: **“Mỗi ngày, cửa hàng A có bao nhiêu đơn và tổng giá trị là bao nhiêu?”**.

Để làm ví dụ, ta tạo một keyspace với `NetworkTopologyStrategy`. Cần thay `dc1` bằng **tên data center thực tế**, và lab phải có đủ replica để đáp ứng cấu hình RF = 3 nếu dùng `LOCAL_QUORUM`.

~~~sql
CREATE KEYSPACE IF NOT EXISTS orders_lab
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3
};

CREATE TABLE IF NOT EXISTS orders_lab.orders_by_store_day (
  store_id text,
  order_day date,
  order_id uuid,
  order_status text,
  total_amount decimal,
  PRIMARY KEY ((store_id), order_day, order_id)
) WITH CLUSTERING ORDER BY (order_day DESC, order_id ASC);
~~~

Ý nghĩa primary key:

- **`store_id` là partition key:** các đơn của cùng cửa hàng trong ví dụ nằm trong một partition.
- **`order_day` là clustering column thứ nhất:** các hàng trong partition được sắp theo ngày, thuận tiện nhóm theo ngày.
- **`order_id` là clustering column thứ hai:** phân biệt các đơn cùng ngày.
- **`order_status` và `total_amount` là regular columns:** có thể dùng `total_amount` trong `SUM`, nhưng `order_status` không tự trở thành khóa nhóm.

Đây là **bảng thực hành nhỏ** để minh họa cú pháp; production thường cần **bucketing** (ví dụ `(store_id, month_bucket)`) để tránh một partition tăng mãi theo nhiều năm.

Nạp dữ liệu với năm đơn hàng, trong đó ngày 20 có cả đơn `CANCELLED`:

~~~sql
INSERT INTO orders_lab.orders_by_store_day
  (store_id, order_day, order_id, order_status, total_amount)
VALUES ('store-A', '2026-11-20',
        00000000-0000-4000-8000-000000000001, 'PAID', 100.50);

INSERT INTO orders_lab.orders_by_store_day
  (store_id, order_day, order_id, order_status, total_amount)
VALUES ('store-A', '2026-11-20',
        00000000-0000-4000-8000-000000000002, 'PAID', 50.00);

INSERT INTO orders_lab.orders_by_store_day
  (store_id, order_day, order_id, order_status, total_amount)
VALUES ('store-A', '2026-11-20',
        00000000-0000-4000-8000-000000000003, 'CANCELLED', 75.00);

INSERT INTO orders_lab.orders_by_store_day
  (store_id, order_day, order_id, order_status, total_amount)
VALUES ('store-A', '2026-11-21',
        00000000-0000-4000-8000-000000000004, 'PAID', 200.00);

INSERT INTO orders_lab.orders_by_store_day
  (store_id, order_day, order_id, order_status, total_amount)
VALUES ('store-A', '2026-11-21',
        00000000-0000-4000-8000-000000000005, 'PAID', 25.00);
~~~

Trong lab chưa có ghi đồng thời hoặc TTL, các phép tính dự kiến là:

| Ngày | Số đơn | Tổng `total_amount` | Ghi chú |
| --- | ---: | ---: | --- |
| `2026-11-20` | 3 | 225.50 | Bao gồm một đơn `CANCELLED`. |
| `2026-11-21` | 2 | 225.00 | Hai đơn `PAID`. |
| **Cả partition** | **5** | **450.50** | Chỉ thuộc `store-A`. |

Các con số phản ánh **toàn bộ đơn**; chúng **không tự mang nghĩa “doanh thu đã thanh toán”** chỉ vì cột đặt tên `total_amount`. Nếu cần lọc theo trạng thái, phải thiết kế đường truy vấn phù hợp.

## 4. `GROUP BY` đúng cách: nhóm theo tiền tố primary key

Truy vấn tổng hợp đơn theo ngày:

~~~sql
SELECT store_id,
       order_day,
       COUNT(*) AS order_count,
       SUM(total_amount) AS gross_amount,
       MIN(total_amount) AS min_amount,
       MAX(total_amount) AS max_amount
FROM orders_lab.orders_by_store_day
WHERE store_id = 'store-A'
GROUP BY store_id, order_day;
~~~

Với dữ liệu trên, có **hai nhóm** `(store-A, 2026-11-20)` và `(store-A, 2026-11-21)`. Vì `store_id` đã được ràng buộc bằng dấu `=`, Cassandra có thể xử lý nhóm theo `order_day` trong partition được xác định. Câu truy vấn minh họa liệt kê đầy đủ các cột nhóm theo đúng thứ tự primary key để dễ đọc.

### Vì sao thứ tự khóa quan trọng?

Giả sử primary key là:

~~~text
PRIMARY KEY ((store_id), order_day, order_id)
             partition    clustering  clustering
~~~

Các khóa nhóm hợp lệ phải là **các cột của primary key theo thứ tự khai báo**, với các quy tắc bỏ qua cột đã được ràng buộc bằng equality trong `WHERE`. Ví dụ:

| Mẫu truy vấn | Cách hiểu |
| --- | --- |
| `WHERE store_id = 'store-A' GROUP BY store_id` | Tổng hợp thành một nhóm cho partition của cửa hàng. |
| `WHERE store_id = 'store-A' GROUP BY store_id, order_day` | Tổng hợp theo ngày trong partition. |
| `WHERE store_id = 'store-A' GROUP BY store_id, order_day, order_id` | Mỗi đơn có khóa riêng, thường chỉ còn một hàng trên nhóm. |
| `GROUP BY order_status` | **Không hợp lệ:** `order_status` không thuộc primary key. |
| `GROUP BY order_day, store_id` | **Không hợp lệ theo thứ tự khóa:** đảo thứ tự các cột nhóm. |

Đây là điểm khác SQL: Cassandra không thể tự động gom các giá trị `order_status` của mọi partition thành các nhóm tùy ý, rồi sắp chúng theo tổng lớn nhất như một hệ thống phân tích dữ liệu tổng quát.

### Sơ đồ đường đi của một truy vấn nhóm

~~~mermaid
flowchart TD
    Q["SELECT ... WHERE store_id = 'store-A'"] --> P["Partition key xác định partition và replica"]
    P --> C["Coordinator đọc các hàng theo clustering key"]
    C --> G["GROUP BY store_id, order_day"]
    G --> A1["2026-11-20: COUNT=3, SUM=225.50"]
    G --> A2["2026-11-21: COUNT=2, SUM=225.00"]
    A1 --> R["Trả các hàng tổng hợp"]
    A2 --> R
~~~

**Không có bước tự động tạo chỉ mục hoặc bảng tổng hợp vĩnh viễn** sau `GROUP BY`. Lần sau chạy truy vấn, hệ thống vẫn phải đọc các dữ liệu liên quan. Sơ đồ thể hiện luồng logic; số node replica tham gia đọc còn phụ thuộc consistency level.

## 5. Giới hạn ngữ nghĩa: `GROUP BY` trong Cassandra khác SQL như thế nào?

### 5.1. Không nhóm tùy ý theo regular column

Truy vấn người dùng SQL thường nghĩ tới:

~~~sql
-- KHÔNG HỢP LỆ cho bảng ví dụ trong Cassandra:
SELECT order_status, COUNT(*)
FROM orders_lab.orders_by_store_day
GROUP BY order_status;
~~~

`order_status` chỉ là regular column nên **không thể dùng làm khóa nhóm**. Việc thêm `ALLOW FILTERING` không biến regular column thành một clustering key và không nới quy tắc `GROUP BY`.

Nếu nghiệp vụ thường hỏi “đếm đơn theo trạng thái của một cửa hàng”, cần một **bảng khác có primary key phục vụ chính truy vấn đó**, hoặc bảng kết quả tổng hợp riêng. Ví dụ có thể chọn clustering prefix `order_status` trước `order_day` khi mô hình đọc thật sự cần nhóm theo trạng thái.

### 5.2. `WHERE` phải hợp với partition key/clustering key

Truy vấn:

~~~sql
-- Không phải đường truy vấn hiệu quả trên schema hiện tại:
SELECT COUNT(*)
FROM orders_lab.orders_by_store_day
WHERE order_status = 'PAID';
~~~

không có điều kiện partition key, và `order_status` không phải khóa có thể định tuyến truy vấn theo schema trên. Cassandra thường từ chối đường truy vấn cần lọc không được hỗ trợ, hoặc yêu cầu cơ chế index/đường truy vấn khác; **không nên thêm `ALLOW FILTERING` chỉ để ép bảng thành công cụ thống kê toàn cluster**.

Ngay cả khi có index, cần đánh giá riêng cardinality, selectivity, bản phân phối dữ liệu và giới hạn `GROUP BY`. Index không tự biến mọi truy vấn `GROUP BY` thành phép nhóm tùy ý như SQL.

### 5.3. Không có `HAVING` kiểu SQL hay sắp xếp theo tổng tùy ý

CQL không cung cấp `HAVING SUM(total_amount) > ...` để lọc nhóm kiểu SQL, cũng không hỗ trợ `ORDER BY SUM(total_amount) DESC` như một phép sắp xếp tự do theo kết quả aggregate:

~~~sql
-- Ý tưởng SQL, không phải câu CQL hợp lệ:
SELECT order_day, SUM(total_amount) AS gross
FROM orders_lab.orders_by_store_day
WHERE store_id = 'store-A'
GROUP BY store_id, order_day
HAVING SUM(total_amount) > 200
ORDER BY gross DESC;
~~~

Với kết quả nhỏ, ứng dụng có thể lọc và sắp xếp **sau khi lấy các nhóm**. Với dữ liệu lớn và dashboard thường xuyên, nên lưu **bảng tổng hợp được tính trước** theo key của màn hình, hoặc dùng hệ thống phân tích phù hợp.

`ORDER BY` CQL, nếu sử dụng, bị ràng buộc bởi **clustering columns** và điều kiện trên partition key; nó không phải phép `ORDER BY` tùy cột hoặc tùy biểu thức aggregate của SQL.

### 5.4. Cẩn thận khi chọn cột không nằm trong khóa nhóm

Cassandra cho phép một số câu `SELECT` trả thêm các cột không được nhóm hay tổng hợp. Trong trường hợp đó, giá trị không tổng hợp được lấy từ **một hàng đại diện của nhóm** theo cách truy vấn xử lý dữ liệu, **không phải một tính chất của toàn nhóm**.

Ví dụ, `SELECT order_day, order_status, COUNT(*) ... GROUP BY store_id, order_day` có thể hiển thị `order_status = 'PAID'` bên cạnh nhóm có cả `PAID` và `CANCELLED`. Nếu đọc nhãn trạng thái đó như “cả nhóm đều PAID”, kết luận sẽ sai. Vì thế, chỉ nên `SELECT` **cột thuộc khóa nhóm** và **biểu thức aggregate** khi muốn báo cáo một nhóm có ý nghĩa.

Nếu muốn biết “trạng thái phổ biến nhất”, “đơn lớn nhất thuộc khách hàng nào” hay “giá trị của hàng có `MAX`”, cần thiết kế truy vấn/bảng khác; `MAX` trả giá trị lớn nhất chứ không trả nguyên hàng chứa nó.

### 5.5. `LIMIT` không biến một phép tổng hợp lớn thành rẻ

Khi có `GROUP BY`, `LIMIT` giới hạn số **hàng kết quả nhóm** trả về. Nó **không tạo ra thống kê duy trì sẵn**, cũng không bảo đảm rằng dữ liệu phía sau một nhóm được tính với chi phí hằng số. `PER PARTITION LIMIT` có ngữ nghĩa giới hạn theo partition/nhóm, tùy cấu trúc truy vấn.

Ví dụ:

~~~sql
SELECT order_day, COUNT(*) AS order_count
FROM orders_lab.orders_by_store_day
WHERE store_id = 'store-A'
GROUP BY store_id, order_day
LIMIT 7;
~~~

Truy vấn chỉ yêu cầu tối đa bảy nhóm ngày, nhưng nếu mỗi ngày chứa hàng triệu đơn thì **các hàng trong nhóm vẫn phải được xử lý** để đếm chính xác.

### 5.6. Không coi aggregate là một phép snapshot giao dịch toàn cục

Cassandra thực hiện đọc qua coordinator/replica theo consistency level. `LOCAL_QUORUM` làm tăng số phản hồi cục bộ cần có, nhưng **không biến nhiều partition thành một snapshot giao dịch nhất quán như hệ SQL có MVCC**. Trong lúc truy vấn chạy, ghi đồng thời, TTL, timestamp, tombstone, replica chậm hoặc dữ liệu chưa repair có thể ảnh hưởng quan sát.

Vì vậy, con số từ `COUNT(*)` hoặc `SUM` nên được hiểu là **kết quả đọc CQL ở consistency level cụ thể**, không phải tự động là sổ cái tài chính đã được chốt giao dịch.

## 6. Chi phí phân tán và lựa chọn consistency level

Với `WHERE store_id = 'store-A'`, partition key cho phép Cassandra xác định nhóm replica lưu partition. Node nhận request làm **coordinator**, chọn đường đọc phù hợp consistency level, lấy dữ liệu và tính/trả kết quả aggregate. Khi đọc nhiều partition, phạm vi công việc rộng hơn và có thể liên quan nhiều bộ replica.

| Truy vấn | Phạm vi dữ liệu phải xử lý | Đánh giá |
| --- | --- | --- |
| `COUNT(*) WHERE store_id = ?` | Các hàng liên quan trong partition của một cửa hàng | Có thể phù hợp với partition nhỏ, nhưng không mặc nhiên tức thời. |
| `GROUP BY store_id, order_day WHERE store_id = ?` | Các hàng trong partition được nhóm theo clustering key | Phù hợp để minh họa và dùng có kiểm soát khi partition vừa phải. |
| `COUNT(*)` không có `WHERE` | Có thể phải quét dữ liệu trên nhiều partition/node | Rủi ro cao về latency, timeout và tải cluster. |
| Nhóm tất cả cửa hàng theo regular column | Không được hỗ trợ như SQL ad hoc trên bảng này | Cần bảng theo truy vấn/tiền tổng hợp hoặc hệ phân tích. |

Nếu một partition có quá nhiều hàng, quét tổng hợp có thể tạo áp lực lên disk, CPU, mạng, bộ nhớ, coordinator và thời hạn request. Nó còn phải xử lý các chi phí đọc như SSTable, tombstone và đối chiếu replica khi cần. **Compaction** giúp quản lý SSTable cục bộ; **repair** giúp đồng bộ dữ liệu giữa replica. Hai cơ chế này **không biến `COUNT(*)` thành một chỉ số đã được tính sẵn**.

Khi dùng `LOCAL_QUORUM` với RF = 3 trong DC cục bộ, đọc cần đủ **hai phản hồi replica thích hợp**; `LOCAL_ONE` chỉ cần một phản hồi và có thể thấy dữ liệu cũ hơn. Truy vấn aggregate cũng chịu các cân nhắc nhất quán này như những truy vấn đọc khác.

## 7. Cách thiết kế cho truy vấn thống kê thật

### 7.1. Giữ nhóm nhỏ bằng partition key và bucket

Nếu cần báo cáo theo ngày cho từng cửa hàng, tránh lưu toàn bộ lịch sử cửa hàng trong một partition không giới hạn kích thước. Một phương án là chia theo **tháng**:

~~~sql
CREATE TABLE IF NOT EXISTS orders_lab.orders_by_store_month (
  store_id text,
  month_bucket text,
  order_day date,
  order_id uuid,
  order_status text,
  total_amount decimal,
  PRIMARY KEY ((store_id, month_bucket), order_day, order_id)
) WITH CLUSTERING ORDER BY (order_day DESC, order_id ASC);
~~~

Truy vấn theo tháng chỉ đi vào partition `(store_id, month_bucket)`:

~~~sql
SELECT store_id, month_bucket, order_day,
       COUNT(*) AS order_count,
       SUM(total_amount) AS gross_amount
FROM orders_lab.orders_by_store_month
WHERE store_id = 'store-A'
  AND month_bucket = '2026-11'
GROUP BY store_id, month_bucket, order_day;
~~~

Ở đây, hai cột partition key được ràng buộc bằng `=`; `order_day` là clustering prefix tiếp theo. Muốn thống kê cả năm, ứng dụng có thể truy vấn từng bucket tháng rồi tổng hợp các kết quả; không nên dựa vào một truy vấn quét mọi partition để ghép thống kê như SQL tổng quát.

Với ứng dụng chỉ quan tâm đơn `PAID`, có thể duy trì thêm bảng chỉ chứa đơn đã thanh toán hoặc bảng có `order_status` nằm trong khóa phù hợp truy vấn. Đổi primary key là **quyết định mô hình dữ liệu**, vì nó ảnh hưởng cách ghi, phân tán, phạm vi partition và các truy vấn hợp lệ.

### 7.2. Tiền tổng hợp cho dashboard truy cập thường xuyên

Nếu màn hình hiển thị mỗi ngày “số đơn thanh toán” và “doanh thu đã thanh toán” với lưu lượng cao, một bảng thống kê đã tính sẵn thường phù hợp hơn:

~~~sql
CREATE TABLE IF NOT EXISTS orders_lab.paid_revenue_by_store_day (
  store_id text,
  order_day date,
  paid_order_count bigint,
  paid_amount decimal,
  calculated_at timestamp,
  PRIMARY KEY ((store_id), order_day)
) WITH CLUSTERING ORDER BY (order_day DESC);

SELECT order_day, paid_order_count, paid_amount
FROM orders_lab.paid_revenue_by_store_day
WHERE store_id = 'store-A';
~~~

Bảng này được **ứng dụng, job định kỳ hoặc luồng xử lý sự kiện** cập nhật bằng kết quả đã tính; `SELECT` đọc trực tiếp các số liệu theo ngày, không cần quét lại tất cả đơn. Đổi lại, phải thiết kế quy trình cập nhật khi đơn mới tạo, bị hủy, hoàn tiền, cập nhật trạng thái hoặc sự kiện bị phát lại.

Không nên dùng một chuỗi “đọc tổng hiện tại → cộng giá trị → ghi đè” thiếu kiểm soát khi nhiều worker cập nhật đồng thời: điều này gây **lost update**. Cassandra có kiểu `counter` cho một số bài toán đếm, nhưng thao tác tăng counter có đặc tính retry/idempotency riêng và không tự giải quyết tổng `decimal` hay phép đối soát tài chính. Với yêu cầu chính xác, cần cơ chế deduplication, mô hình sự kiện nguồn, checkpoint/reconciliation và chiến lược nhất quán phù hợp.

### 7.3. Khi nào nên dùng hệ phân tích chuyên dụng?

Các câu hỏi như “Top 100 cửa hàng theo doanh thu ở mọi vùng”, “GROUP BY `order_status` rồi `HAVING`”, “JOIN đơn hàng với bảng khách hàng”, phân tích nhiều chiều theo thời gian, hoặc thống kê rất dài ngày thường nên chuyển sang pipeline phân tích/OLAP thích hợp. Cassandra đóng vai trò **nguồn dữ liệu phục vụ truy vấn giao dịch theo key**, còn pipeline tập hợp dữ liệu để báo cáo ad hoc.

## 8. Kết nối Java và đọc giá trị aggregate

Với **Apache Cassandra Java Driver 4.x**, ứng dụng có thể chuẩn bị câu truy vấn theo partition key và gán consistency level lên statement. Ví dụ sau dùng bảng đã tạo ở mục 3:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;
import java.math.BigDecimal;
import java.net.InetSocketAddress;
import java.time.LocalDate;

public class DailyOrderSummary {
    public static void main(String[] args) {
        try (CqlSession session = CqlSession.builder()
                .addContactPoint(new InetSocketAddress("127.0.0.1", 9042))
                .withLocalDatacenter("dc1")
                .build()) {

            PreparedStatement prepared = session.prepare(
                    "SELECT order_day, COUNT(*) AS order_count, " +
                    "SUM(total_amount) AS gross_amount " +
                    "FROM orders_lab.orders_by_store_day " +
                    "WHERE store_id = ? " +
                    "GROUP BY store_id, order_day");

            BoundStatement statement = prepared.bind("store-A")
                    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);

            ResultSet result = session.execute(statement);
            for (Row row : result) {
                LocalDate day = row.getLocalDate("order_day");
                long count = row.getLong("order_count");
                BigDecimal gross = row.getBigDecimal("gross_amount");
                System.out.printf("%s: %d orders, gross %s%n",
                        day, count, gross);
            }
        }
    }
}
~~~

Điểm cần hiểu:

1. `WHERE store_id = ?` giúp driver và coordinator định tuyến theo **partition key**; việc bind bằng prepared statement là cách truyền giá trị an toàn và tái sử dụng kế hoạch CQL.
2. `LOCAL_QUORUM` yêu cầu đọc theo quorum replica trong data center cục bộ, **không tạo transaction snapshot toàn cluster**.
3. Alias `AS order_count`, `AS gross_amount` là tên cột kết quả mà `Row` sử dụng; `SUM(decimal)` được nhận bằng `BigDecimal`.
4. `127.0.0.1` và `dc1` chỉ dành cho lab; ứng dụng thực tế cần cấu hình contact point, local DC, TLS/authentication và timeout đúng topology.
5. Đây là ví dụ đọc dữ liệu quy mô nhỏ. Nếu truy vấn phải đọc hàng triệu đơn, đổi sang bảng tiền tổng hợp hoặc quy trình phân tích phù hợp thay vì chỉ tăng timeout.

## 9. Các lỗi suy luận thường gặp

| Nhận định | Đánh giá | Cách hiểu chính xác |
| --- | --- | --- |
| “Cassandra có `GROUP BY` nên có thể nhóm theo mọi cột.” | **Sai** | Cột nhóm bị ràng buộc bởi primary key và thứ tự khóa, có xét cột đã equality-bound. |
| “`COUNT(*)` lấy từ metadata, nên bảng rất lớn vẫn đếm ngay lập tức.” | **Sai** | Phải đọc tập hàng liên quan; rất tốn kém khi quét lớn. |
| “`MIN(amount)` trả về toàn bộ đơn hàng nhỏ nhất.” | **Sai** | Chỉ trả về giá trị tổng hợp nhỏ nhất, không tự lấy các cột của hàng tương ứng. |
| “`LIMIT 10` giúp tổng hợp luôn chỉ đọc 10 hàng nguồn.” | **Sai** | Với `GROUP BY`, số nhóm được trả về có giới hạn, nhưng công việc tổng hợp trong nhóm vẫn có thể lớn. |
| “`LOCAL_QUORUM` biến `SUM` thành báo cáo giao dịch chính xác ở mọi thời điểm.” | **Sai** | CL điều khiển phản hồi replica; không cung cấp snapshot toàn cục. |
| “Có thể dùng `HAVING` để giữ nhóm doanh thu trên ngưỡng.” | **Sai** | CQL không hỗ trợ `HAVING` kiểu SQL; lọc kết quả ở nơi khác hoặc dùng bảng phục vụ truy vấn. |
| “Bảng tiền tổng hợp cần cơ chế duy trì riêng.” | **Đúng** | Phải quản lý dữ liệu mới, cập nhật, hủy, phát lại sự kiện và đối soát. |

## 10. Bài tập tự kiểm tra

**Bài 1.** Với bảng `orders_by_store_day`, viết truy vấn đếm tổng số đơn của `store-A` mà không chia ngày.

~~~sql
SELECT COUNT(*) AS total_orders
FROM orders_lab.orders_by_store_day
WHERE store_id = 'store-A';
~~~

Nếu dữ liệu đúng như mục 3 và không có thay đổi, kết quả là `5`.

**Bài 2.** Vì sao câu `GROUP BY order_status` không hợp lệ dù bảng có cột `order_status`?

**Đáp án:** `order_status` là regular column, không thuộc primary key. Cassandra không hỗ trợ nhóm tùy ý theo regular column như SQL. Cần bảng thiết kế theo truy vấn hoặc bảng tiền tổng hợp.

**Bài 3.** Truy vấn `GROUP BY store_id, order_day` trả một hàng có `order_status = 'PAID'` cho ngày 20. Có kết luận mọi đơn ngày 20 là `PAID` được không?

**Đáp án:** **Không.** Giá trị `order_status` không được nhóm/tổng hợp chỉ đến từ một hàng đại diện; nhóm ngày 20 có cả đơn `CANCELLED`.

**Bài 4.** Công ty muốn thống kê số đơn theo ngày cho 3.000 cửa hàng, mỗi cửa hàng có vài triệu đơn. Dùng `COUNT(*) GROUP BY order_day` trực tiếp trên toàn bảng cho mỗi lần mở dashboard có phù hợp không?

**Đáp án:** Không phù hợp trong phần lớn trường hợp. Query phải quét khối lượng dữ liệu lớn và dễ gây tải/timeout. Cần thiết kế partition và bucket hợp lý, lập bảng tổng hợp theo khóa truy vấn, hoặc đưa bài toán sang hệ phân tích.

**Bài 5.** Một hệ thống có RF = 3 ở `dc1`. Nếu đặt `LOCAL_ONE` thay vì `LOCAL_QUORUM` cho truy vấn `SUM`, liệu kết quả luôn giống nhau?

**Đáp án:** Không có bảo đảm như vậy khi replica có độ trễ cập nhật hoặc dữ liệu đang được sửa chữa. `LOCAL_ONE` cần một replica; `LOCAL_QUORUM` cần hai phản hồi. Mức nhất quán đọc khác nhau có thể dẫn tới quan sát khác nhau khi dữ liệu chưa hội tụ.

## 11. Quy trình ra quyết định trước khi viết truy vấn aggregate

~~~mermaid
flowchart TD
    A["Cần COUNT / SUM / AVG / MIN / MAX?"] --> B{"Truy vấn đã xác định partition key?"}
    B -->|Có| C{"GROUP BY chỉ dùng prefix primary key?"}
    B -->|Không| D["Xem lại data model hoặc luồng analytics"]
    C -->|Có| E{"Số hàng trong phạm vi quét nhỏ và bị giới hạn?"}
    C -->|Không| F["Thiết kế bảng theo câu hỏi hoặc bảng tiền tổng hợp"]
    E -->|Có| G["Có thể dùng aggregate CQL và đo latency thực tế"]
    E -->|Không| F
    D --> H["Không dùng full scan định kỳ cho dashboard lớn"]
    F --> I["Duy trì kết quả và đối soát khi dữ liệu thay đổi"]
~~~

**Ghi nhớ:** `COUNT`, `SUM`, `AVG`, `MIN`, `MAX` là các phép tổng hợp hợp lệ của CQL; `GROUP BY` chỉ nhóm theo cấu trúc **primary key** mà Cassandra có thể xử lý. Thiết kế bảng theo truy vấn và giới hạn kích thước partition quyết định hiệu quả thực tế. Khi cần lọc, sắp xếp hay kết hợp nhiều chiều theo ngữ nghĩa SQL, hãy chọn bảng kết quả tổng hợp hoặc hệ thống phân tích được thiết kế cho nhu cầu đó.
