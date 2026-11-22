# Table compression trong Oracle: đánh đổi CPU, dung lượng và điều kiện tính năng/giấy phép

**Table compression** là kỹ thuật giảm dung lượng lưu trữ dữ liệu bảng trong Oracle Database bằng cách biểu diễn các giá trị hoặc các nhóm giá trị theo dạng nén. Khi cùng một lượng dữ liệu chiếm ít block hơn, hệ thống có thể giảm I/O vật lý, giảm dung lượng segment và đôi khi tăng hiệu quả sử dụng bộ nhớ cache. Tuy nhiên, nén và giải nén cũng tiêu tốn CPU, tạo chi phí khi ghi/cập nhật dữ liệu, và các chế độ compression của Oracle có **điều kiện kỹ thuật cũng như điều kiện giấy phép khác nhau**.

Vì vậy, quyết định nén một bảng không chỉ là hỏi “tiết kiệm được bao nhiêu GB?”. Cần xét đồng thời: dữ liệu có lặp đủ để nén tốt không, bảng chủ yếu đọc hay ghi, truy vấn đọc bao nhiêu block, thời gian đáp ứng yêu cầu, chi phí nén dữ liệu cũ, mô hình phân vùng, phiên bản/edition Oracle, loại hạ tầng lưu trữ và quyền sử dụng tính năng theo hợp đồng.

Bài học này tập trung vào **nén dữ liệu bảng (table segment compression)** trong ngữ cảnh lưu trữ Oracle Database. Những khái niệm nén backup, nén mạng, nén index, nén SecureFiles LOB hay nén trong In-Memory Column Store sẽ được nhắc đến để phân biệt, nhưng không được đánh đồng với table compression.

## 1. Table compression nằm ở đâu trong kiến trúc lưu trữ?

Oracle tổ chức dữ liệu bảng thành các **data block** nằm trong các **extent** thuộc **segment** của bảng hoặc partition. Một bảng heap thông thường chứa các bản ghi theo định dạng hàng, cùng metadata quản lý block, khoảng trống và thông tin cần thiết cho khả năng truy cập/nhất quán.

Sơ đồ khái niệm:

~~~text
Logical table SALES
        |
        v
Table segment (hoặc mỗi partition có segment riêng)
        |
   +----+----------+----------+
   |    |          |          |
 Extent 1       Extent 2    Extent ...
   |               |
   v               v
Data blocks     Data blocks
   |
   +-- Row data / metadata / free space
~~~

Khi bật một chế độ **row store compression**, Oracle có thể lưu dữ liệu hàng trong các block theo cách tận dụng giá trị lặp hoặc biểu diễn ngắn hơn, giúp nhiều dữ liệu hữu ích nằm trong cùng số block. Ở các chế độ **Hybrid Columnar Compression (HCC)**, đơn vị tổ chức và nén có tính chất khác: dữ liệu được nhóm thành các **compression unit**, tổ chức theo cột trong phạm vi unit để đạt tỉ lệ nén cao hơn cho dữ liệu đọc nhiều.

Điều quan trọng:

- Compression **thay đổi cách lưu trên storage**, không thay đổi logic bảng mà ứng dụng nhìn qua SQL thông thường.
- Cùng tên bảng và cùng dữ liệu logic, hai chế độ nén có thể tạo ra chi phí CPU, dung lượng và đặc tính DML rất khác nhau.
- Compression không tự tạo index, không sửa thiết kế quan hệ, không loại bỏ yêu cầu về ràng buộc, transaction hoặc thống kê optimizer.
- Compression không nhất thiết giảm kích thước của **mọi** loại đối tượng liên quan. Index, LOB segment, materialized view và các cấu trúc khác có cơ chế lưu trữ và nén riêng.

### 1.1 Vì sao dữ liệu có thể nén?

Xét một bảng đơn hàng có hàng triệu bản ghi:

| order_id | status | region | channel |
|---:|---|---|---|
| 101 | PAID | HCM | WEB |
| 102 | PAID | HCM | WEB |
| 103 | PAID | HCM | WEB |
| 104 | CANCELLED | HN | APP |
| 105 | PAID | HCM | WEB |

Các giá trị như `PAID`, `HCM`, `WEB` xuất hiện lặp lại. Thay vì phải lưu đầy đủ mọi chuỗi lặp cho mọi hàng theo cùng cách, một số kỹ thuật nén có thể tái sử dụng biểu diễn của những giá trị giống nhau.

Ví dụ ý niệm (không phải định dạng block vật lý chính xác của Oracle):

~~~text
Trước nén:
PAID | HCM | WEB
PAID | HCM | WEB
PAID | HCM | WEB

Sau nén, hình dung:
Dictionary: #1=PAID, #2=HCM, #3=WEB
Rows:       #1/#2/#3, #1/#2/#3, #1/#2/#3
~~~

Độ nén thực tế phụ thuộc kiểu dữ liệu, chuỗi lặp, phân bố giá trị, mức hạt nén, kích thước block, cách nạp dữ liệu và đặc tính của từng chế độ compression. Dữ liệu ngẫu nhiên, đã được nén ở tầng khác hoặc có nhiều giá trị duy nhất có thể tiết kiệm rất ít.

## 2. Ba họ table compression cần phân biệt

Oracle cung cấp nhiều cơ chế nén với mục đích khác nhau. Tên cú pháp, khả năng hỗ trợ và quyền sử dụng có thể thay đổi theo **phiên bản phát hành, edition, dịch vụ cloud và thiết bị lưu trữ**.

| Họ nén | Mục đích chính | Đường ghi phù hợp | Điểm đánh đổi |
|---|---|---|---|
| **Basic Table Compression** — thường dùng `ROW STORE COMPRESS BASIC` | Giảm dung lượng các bảng được nạp/biến đổi bằng thao tác bulk hoặc direct-path | CTAS, bulk/direct-path load, table/partition move | DML thông thường có thể không được nén hiệu quả như các khối được tạo bằng bulk; cần có kế hoạch tái tổ chức |
| **Advanced Row Compression** — `ROW STORE COMPRESS ADVANCED` | Nén dữ liệu dạng hàng trong khi vẫn hỗ trợ workload đọc/ghi với DML thường xuyên hơn | Bảng hoạt động có `INSERT`, `UPDATE`, `DELETE` | Có thêm công việc CPU/metadata khi nén hoặc tái nén block; điều kiện sử dụng tính năng/giấy phép đặc thù |
| **Hybrid Columnar Compression (HCC)** — `COLUMN STORE COMPRESS FOR QUERY ...` hoặc `... FOR ARCHIVE ...` | Nén mạnh cho dữ liệu đọc nhiều, phân tích hoặc lưu trữ lịch sử | Bulk load, partition dữ liệu lạnh, scan/reporting | Cập nhật từng hàng thường kém phù hợp, cần hạ tầng hỗ trợ HCC và kiểm tra license/edition cụ thể |

Ba họ này không phải một thang “BASIC → ADVANCED → HCC” bắt buộc. Chúng phục vụ **những dạng thao tác khác nhau**. Một bảng giao dịch ghi liên tục có thể hợp với Advanced Row Compression hơn HCC; một partition dữ liệu lịch sử chủ yếu đọc có thể hợp với HCC nếu hạ tầng và giấy phép cho phép.

### 2.1 Tên cú pháp SQL nhìn nhanh

Ví dụ các khai báo thường gặp trên phiên bản Oracle hỗ trợ:

~~~sql
-- Basic Table Compression: dữ liệu lưu theo dạng row store.
CREATE TABLE orders_basic
ROW STORE COMPRESS BASIC
AS SELECT * FROM orders_source;

-- Advanced Row Compression: dành cho row-store với DML.
CREATE TABLE orders_advanced
ROW STORE COMPRESS ADVANCED
AS SELECT * FROM orders_source;

-- HCC: yêu cầu môi trường storage/edition phù hợp.
CREATE TABLE orders_query_archive
COLUMN STORE COMPRESS FOR QUERY HIGH
AS SELECT * FROM orders_source;
~~~

Đây là **ba phương án minh họa riêng**, không phải bộ lệnh cần chạy nối tiếp. `ORDERS_SOURCE` chỉ là tên nguồn giả định. Không chạy các lệnh thử chế độ Advanced hoặc HCC trên một hệ thống chưa xác nhận quyền sử dụng và hỗ trợ kỹ thuật. Những lệnh `CREATE TABLE ... AS SELECT` cũng tạo ra bảng mới, tiêu tốn không gian và không tự sao chép đầy đủ mọi ràng buộc, chỉ mục, trigger hay grant của bảng nguồn.

## 3. Basic Table Compression: tối ưu các đợt nạp dữ liệu lớn

**Basic Table Compression** là dạng nén row-store phù hợp khi dữ liệu được xây dựng hoặc nạp theo lô, không phải nơi luôn có nhiều cập nhật nhỏ xen kẽ.

### 3.1 Cơ chế và đặc tính

Ở mức khái niệm, Oracle sử dụng biểu diễn nén trong block nhằm giảm không gian dành cho các giá trị lặp. Các thao tác được tổ chức theo **direct-path/bulk** hoặc thao tác viết lại segment thường thuận lợi để tạo các block nén.

Ví dụ các kịch bản hay gặp:

- Tạo một bảng báo cáo mới bằng `CREATE TABLE ... AS SELECT` (CTAS).
- Nạp dữ liệu theo lô bằng đường ghi thích hợp cho direct-path.
- Viết lại một table segment hoặc partition bằng `ALTER TABLE ... MOVE` khi quy trình vận hành cho phép.
- Chuyển dữ liệu đã ổn định sang partition lịch sử và nén khi partition trở thành dữ liệu lạnh.

Lưu ý **không đồng nhất Basic Table Compression với “mọi INSERT tự được nén”**. Khi dùng conventional-path DML, cách dữ liệu mới hoặc dữ liệu đã sửa được lưu có thể khác với khối được nén từ direct-path. Tỉ lệ nén thực tế của cả segment có thể giảm theo thời gian nếu workload tiếp tục cập nhật nhiều.

### 3.2 Ví dụ đọc nhiều, ghi ít

Giả sử công ty có bảng `SALES_HISTORY_2024` chỉ nạp một lần sau chốt số, người dùng chủ yếu chạy:

~~~sql
SELECT region_code, SUM(net_amount) AS net_sales
FROM sales_history_2024
WHERE invoice_date >= DATE '2024-01-01'
  AND invoice_date <  DATE '2025-01-01'
GROUP BY region_code;
~~~

Nếu nén giúp số block bảng giảm, quét toàn bảng hoặc quét partition có thể cần ít I/O vật lý hơn. CPU vẫn phải xử lý nén/giải nén trong quá trình đọc. Kết quả là **có thể nhanh hơn** nếu I/O từng là nút cổ chai; nhưng cũng **có thể chậm hơn** nếu CPU đã bão hòa hoặc dữ liệu không nén tốt.

## 4. Advanced Row Compression: cân bằng nén với DML thường xuyên

**Advanced Row Compression** được thiết kế để áp dụng nén row-store trong môi trường có DML thông thường, không chỉ khi bulk load. Một số tài liệu hoặc hệ thống cũ nhắc tên **OLTP Table Compression** / cú pháp `COMPRESS FOR OLTP`; cú pháp hiện đại thường dùng `ROW STORE COMPRESS ADVANCED`. Cần tham chiếu cú pháp tương thích với bản Oracle cụ thể.

### 4.1 Nó khác Basic ở đâu?

Giả sử bảng `ORDERS` liên tục nhận đơn và thay đổi trạng thái:

~~~sql
INSERT INTO orders (order_id, customer_id, status)
VALUES (:p_order_id, :p_customer_id, 'NEW');

UPDATE orders
SET status = 'PAID'
WHERE order_id = :p_order_id;
~~~

Trong workload này, cách tổ chức block phải xử lý không chỉ đọc mà còn việc thêm và cập nhật hàng theo thời gian. Advanced Row Compression có cơ chế quản lý nén theo quá trình DML; nó tránh yêu cầu phải liên tục dùng một thao tác bulk riêng để duy trì dạng nén cho dữ liệu hoạt động.

Tuy nhiên, “Advanced” **không có nghĩa DML không tốn chi phí**. Nén hoặc tái nén block có thể làm tăng CPU trong một số thời điểm, và khi sửa một hàng cần xem tác động tới không gian block, undo/redo, giao dịch và mức đồng thời. Những trường hợp dữ liệu quá biến động hoặc ít khả năng nén có thể không hưởng lợi đủ để bù lại chi phí.

### 4.2 Nén theo block và hiệu ứng với cập nhật

Trong một block nén, các giá trị lặp có thể được biểu diễn qua cấu trúc chung. Khi một hàng được cập nhật:

- Giá trị mới có thể lặp với các giá trị đang có hoặc hoàn toàn khác.
- Việc cập nhật có thể làm thay đổi khả năng nén của block.
- Block có thể cần thêm thao tác quản lý/tái nén theo thuật toán của Oracle.
- Nếu không còn đủ chỗ phù hợp, các hiệu ứng quản lý hàng như row migration có thể xuất hiện tùy cách lưu trữ/thay đổi dữ liệu.

Không nên giả định mọi `UPDATE` gây tái nén toàn bảng, hoặc một lần `UPDATE` luôn mang chi phí cố định. Tác động cần được đo ở dữ liệu và workload thực.

### 4.3 Khi nào đáng cân nhắc?

Các bảng có nhiều giá trị lặp ở nhiều hàng, dung lượng lớn, đọc nhiều hoặc vừa đọc vừa ghi và có ngân sách CPU phù hợp là ứng viên cần đo thử. Các bảng nhỏ, ít lặp, giao dịch có SLA ghi cực chặt hoặc đang áp lực CPU thường cần cân nhắc kỹ.

**Điều kiện sử dụng:** Advanced Row Compression có quy định tính năng/giấy phép riêng, thường gắn với **Oracle Advanced Compression** trong nhiều mô hình cấp phép thương mại. Không suy rằng tính năng đã được phép chỉ vì câu SQL chạy thành công; phải xác nhận entitlement theo release, edition, cloud service và hợp đồng trước khi bật trên dữ liệu thật.

## 5. Hybrid Columnar Compression: hướng phân tích và lưu trữ dữ liệu lạnh

**Hybrid Columnar Compression (HCC)** kết hợp tính chất tổ chức theo nhóm hàng (compression unit) với việc sắp xếp các giá trị theo cột trong phạm vi unit để nén mạnh hơn, đặc biệt khi các cột có dữ liệu lặp hoặc có phân bố thuận lợi.

Ý niệm về compression unit:

~~~text
Các hàng logic:
row1: date1 | HCM | PAID | 150
row2: date2 | HCM | PAID | 200
row3: date3 | HCM | PAID | 400
row4: date4 | HCM | PAID | 500

HCC compression unit (minh họa):
date:   [date1, date2, date3, date4]
region: [HCM, HCM, HCM, HCM]  -> nén hiệu quả
status: [PAID, PAID, PAID, PAID] -> nén hiệu quả
amount: [150, 200, 400, 500]
~~~

Đây chỉ là sơ đồ ý niệm. Cách tổ chức compression unit và thuật toán thật do Oracle thực hiện; không thể suy ra cấu trúc byte vật lý từ bảng minh họa.

### 5.1 Query compression và archive compression

Các kiểu cú pháp HCC điển hình:

~~~sql
-- Các lựa chọn hướng truy vấn phân tích.
COLUMN STORE COMPRESS FOR QUERY LOW
COLUMN STORE COMPRESS FOR QUERY HIGH

-- Các lựa chọn hướng lưu trữ/ít truy cập.
COLUMN STORE COMPRESS FOR ARCHIVE LOW
COLUMN STORE COMPRESS FOR ARCHIVE HIGH
~~~

Thông thường, chế độ ưu tiên **query** hướng đến cân bằng hiệu quả nén với tốc độ đọc phân tích; chế độ ưu tiên **archive** chú trọng mức tiết kiệm không gian hơn, có thể trả giá bằng chi phí CPU và thời gian nén/giải nén cao hơn. `LOW` và `HIGH` cũng là các mức đánh đổi trong mỗi nhóm.

Đừng coi những cấp độ này là cam kết tỉ lệ nén tuyệt đối. Mức tiết kiệm phụ thuộc dữ liệu, phương thức nạp, storage và phiên bản.

### 5.2 HCC và cập nhật từng hàng

HCC phù hợp với các vùng dữ liệu đã ổn định, được nạp theo đợt và chủ yếu quét/đọc. Khi có cập nhật đơn lẻ thường xuyên:

- Oracle có thể phải thực hiện thao tác xử lý dữ liệu nén phức tạp hơn so với row store.
- Hàng mới hoặc hàng đã thay đổi có thể không giữ nguyên cách biểu diễn trong compression unit ban đầu.
- Tỉ lệ nén và hiệu năng DML có thể suy giảm khi dữ liệu bị thay đổi lặp đi lặp lại.
- Việc chuyển lại dữ liệu sang trạng thái nén mong muốn có thể cần thao tác bulk/tổ chức lại theo quy trình được hỗ trợ.

Vì vậy không nên đặt toàn bộ bảng đơn hàng đang liên tục cập nhật vào HCC chỉ vì tỷ lệ nén của bản snapshot thử nghiệm rất cao.

### 5.3 Điều kiện hạ tầng và giấy phép của HCC

HCC là ví dụ rõ ràng của tính năng **không thể chỉ nhìn cú pháp SQL để suy ra được phép sử dụng**. Khả năng hỗ trợ phụ thuộc vào cơ sở dữ liệu, loại storage hoặc dịch vụ Oracle được xác nhận cho HCC, edition, release và quy định entitlement. Một số dòng thiết bị/dịch vụ Oracle tích hợp hỗ trợ HCC; không mặc định database đặt trên ổ đĩa bất kỳ hoặc dịch vụ cloud bất kỳ đều hỗ trợ cùng cơ chế.

Trước khi thiết kế HCC, phải hỏi:

1. Chính xác **Oracle Database version/release update, edition và deployment model** nào đang dùng?
2. Segment sẽ đặt trên **loại storage** nào, có được Oracle hỗ trợ HCC theo cấu hình đó không?
3. Hợp đồng và **Licensing Information/User Manual** tương ứng cho phép dùng HCC chế độ nào?
4. Có ràng buộc về thao tác bulk load, DML, chuyển dữ liệu hoặc sao chép giữa storage không?
5. Nếu chuyển bảng/partition sang hệ thống khác, chế độ nén đó còn được hỗ trợ tại đích không?

Cần xác minh câu trả lời trong tài liệu Oracle và điều khoản cấp phép của chính môi trường triển khai; một bảng hướng dẫn chung không thể thay thế xác nhận này.

## 6. Nén bảng không giống nén index, LOB hay In-Memory

Trong một cơ sở dữ liệu có thể đồng thời tồn tại nhiều cơ chế compression:

| Thành phần | Nội dung cần phân biệt |
|---|---|
| **Heap table / table partition** | Basic, Advanced Row Compression hoặc HCC ở những môi trường cho phép |
| **B-tree index** | Có các cơ chế nén khóa/index riêng; không tự động giảm kích thước cùng tỷ lệ với table |
| **SecureFiles LOB** | Compression riêng đối với LOB như tài liệu/ảnh, có điều kiện cấp phép riêng |
| **In-Memory Column Store** | Biểu diễn dữ liệu theo cột trong bộ nhớ để tăng tốc truy vấn; mức nén trong memory khác với cách lưu segment trên disk |
| **RMAN backup compression** | Nén dữ liệu backup, không thay đổi table segment đang được database sử dụng |
| **Network/data transport compression** | Tối ưu dữ liệu truyền giữa thành phần, không đồng nghĩa table được lưu nén |

Ví dụ bảng có cột `BLOB` chứa file ZIP/JPEG vốn đã nén: bật row-store compression cho bảng **không đảm bảo** dung lượng LOB lớn sẽ giảm, vì dữ liệu LOB có thể nằm trong segment riêng và áp dụng chính sách khác. Cũng không thể suy từ kích thước backup nhỏ hơn rằng table segment trên đĩa đã được nén.

Khi so sánh tiết kiệm chi phí, hãy xác định phạm vi đo: **chỉ heap table**, **table + indexes + LOBs**, **toàn tablespace**, hay **backup/storage bill**. Các con số có thể khác nhau rất nhiều.

## 7. Đánh đổi CPU và I/O: vì sao compression có lúc nhanh, có lúc chậm?

Compression là một ví dụ của đánh đổi **tính toán** lấy **dung lượng và lượng dữ liệu di chuyển**.

Giả sử một báo cáo phải đọc 60 GiB dữ liệu bảng chưa nén. Sau compression, cùng dữ liệu logic được lưu trong 24 GiB. Nếu workload chủ yếu bị giới hạn bởi I/O, giảm số block đọc có thể mang lại lợi ích rõ rệt. Nhưng việc giải nén và xử lý định dạng compressed block tiêu tốn CPU; nếu CPU đã bão hòa, thời gian thực thi có thể không giảm, thậm chí tăng.

### 7.1 Công thức đo tỉ lệ nén

Gọi:

- `U` = kích thước dữ liệu/table segment trước nén, đo trên cùng phạm vi.
- `C` = kích thước sau nén, cùng dữ liệu và cùng phạm vi đo.

Hai chỉ số:

\[
\text{Compression ratio} = \frac{U}{C}
\]

\[
\text{Space saving} = \frac{U-C}{U}\times 100\%
\]

Nếu `U = 60 GiB` và `C = 24 GiB`:

- **Compression ratio:** `60 / 24 = 2.5:1`.
- **Space saving:** `(60 - 24) / 60 = 60%`.

Con số 60% là **dung lượng tiết kiệm trong phạm vi đo**, không chứng minh tốc độ truy vấn tăng 60%, CPU giảm 60% hoặc hóa đơn storage giảm đúng 60%.

### 7.2 CPU được tiêu tốn ở đâu?

Nén có thể làm tăng chi phí tính toán trong một số hoạt động:

- **Bulk load / CTAS / MOVE:** tạo biểu diễn compressed block hoặc compression unit.
- **Đọc dữ liệu:** giải nén hoặc xử lý trực tiếp trên dữ liệu nén theo cơ chế của engine.
- **DML thông thường:** cập nhật hàng, chèn hàng, quản lý không gian block và có thể tái nén.
- **Thao tác tổ chức lại segment:** tạo dữ liệu nén mới, xây lại các cấu trúc phụ thuộc.

Khả năng giải nén hiệu quả phụ thuộc thuật toán và phần cứng. Với dữ liệu đọc nhiều, CPU thêm cho mỗi block có thể nhỏ hơn lợi ích giảm I/O; với tải ghi nặng hoặc dữ liệu ít khả năng nén thì kết quả có thể ngược lại.

### 7.3 Hai kịch bản đối lập

**Kịch bản A — Kho dữ liệu phân tích**

- Bảng lịch sử 200 triệu hàng.
- Nhiều báo cáo quét partition cũ.
- Dữ liệu lặp ở nhiều cột, ít cập nhật.
- Storage I/O là nút cổ chai, CPU còn dư.

Compression có khả năng giúp giảm số block đọc và giảm dung lượng lưu trữ. Nếu hạ tầng và entitlement phù hợp, có thể so sánh Basic, Advanced và HCC theo độ trễ báo cáo.

**Kịch bản B — Bảng giao dịch nóng**

- Mỗi giây có nhiều `INSERT`/`UPDATE` lên các block đang hoạt động.
- Giao dịch có SLA p95/p99 nghiêm ngặt.
- CPU đã gần bão hòa, table tương đối nhỏ và cache hit cao.
- Cột chứa nhiều giá trị gần như duy nhất hoặc dữ liệu đã nén.

Lợi ích I/O/dung lượng có thể nhỏ so với chi phí CPU/DML và tác động tới độ trễ giao dịch. Chọn không nén cũng là một quyết định kỹ thuật hợp lý.

## 8. Vì sao tiết kiệm dung lượng không bằng tiết kiệm tổng chi phí?

Một table segment nén nhỏ hơn có thể tiết kiệm storage, nhưng tổng chi phí hệ thống còn gồm:

| Khoản chi phí | Compression có thể tác động như thế nào? |
|---|---|
| **Dung lượng table segment** | Thường có thể giảm khi dữ liệu đủ nén |
| **I/O vật lý khi đọc** | Có thể giảm do số block lưu trữ ít hơn |
| **SGA buffer cache** | Một số workload có thể giữ nhiều dữ liệu hữu ích hơn trên cùng dung lượng cache |
| **CPU** | Có thể tăng do nén/giải nén và quản lý compressed blocks |
| **INSERT/UPDATE/DELETE latency** | Có thể tăng hoặc thay đổi, phụ thuộc chế độ nén và mẫu DML |
| **UNDO/REDO** | Không có kết luận một chiều; ghi nén, update, move, DDL và cơ chế logging tạo khối lượng công việc khác nhau |
| **TEMP/PGA** | Không mặc nhiên giảm tương ứng với tỷ lệ nén của table; các phép sort/hash vẫn có cấu trúc trung gian riêng |
| **Index/LOB storage** | Có thể không thay đổi nếu không cấu hình riêng |
| **Backup/replication** | Có thể có lợi ích hoặc chi phí tùy công cụ, định dạng backup, cách ghi log và hạ tầng |
| **Migration/rebuild** | Cần I/O, CPU, dung lượng tạm, có thể ảnh hưởng ROWID/index và khả năng truy cập |
| **Giấy phép/phí dịch vụ** | Một số chế độ nén yêu cầu option/edition/storage hoặc gói dịch vụ phù hợp |

Vì vậy, không dùng công thức “table nhỏ đi 50% nên hệ thống nhanh hơn 2 lần”. Hiệu năng thực là kết quả của cả database, truy vấn, dữ liệu, concurrency, hạ tầng và chính sách vận hành.

### 8.1 Nén và buffer cache

Ở một số đường truy cập, Oracle có thể xử lý dữ liệu ở dạng nén trong các block, giúp một lượng dữ liệu logic lớn hơn được biểu diễn trong số block ít hơn. Điều này có thể hữu ích khi working set lớn và buffer cache thường xuyên phải tải dữ liệu từ storage.

Nhưng nếu truy vấn đã làm việc gần như hoàn toàn trong cache, giảm block vật lý thêm một chút không nhất thiết đem lại lợi ích tương xứng. Cần quan sát **logical reads, physical reads, CPU time, elapsed time** và tình trạng buffer cache trong cùng kịch bản.

### 8.2 Nén và index access

Một truy vấn OLTP như:

~~~sql
SELECT status, total_amount
FROM orders
WHERE order_id = :p_order_id;
~~~

có thể truy cập chủ yếu bằng index theo khóa chính rồi lấy đúng một hàng. Dù table nén hơn, số lượng logical reads của truy vấn này có thể thay đổi rất ít. Ngược lại, báo cáo quét phần lớn table có nhiều cơ hội hưởng lợi I/O hơn.

Đừng xem compression như cách thay thế index, partitioning, tối ưu filter hoặc thiết kế đúng của câu SQL.

## 9. Các thao tác làm nén dữ liệu cũ và dữ liệu mới

Một bảng tồn tại trong thời gian dài chứa nhiều block đã lưu. **Thay thuộc tính compression không đồng nghĩa toàn bộ block cũ tự viết lại ngay lập tức.**

### 9.1 Khai báo chế độ cho bảng

Trên phiên bản hỗ trợ, câu lệnh:

~~~sql
ALTER TABLE sales_history
ROW STORE COMPRESS BASIC;
~~~

thay đổi thuộc tính compression của bảng cho các hoạt động phù hợp sau đó. Những hàng đã tồn tại trong các block cũ **không được bảo đảm đồng loạt chuyển sang dạng nén chỉ vì thay metadata**.

Tương tự, thay đổi chế độ sang Advanced hoặc `NOCOMPRESS` không tự động viết lại mọi block đang có. Một bảng có thể có dữ liệu vật lý được tạo ở các thời điểm và trạng thái compression khác nhau; dictionary thể hiện thiết lập, không phải bằng chứng mọi block đều cùng dạng.

### 9.2 Viết lại table segment bằng MOVE

Một thao tác tạo lại table segment thường dùng để áp dụng chế độ nén cho dữ liệu hiện có:

~~~sql
-- Minh họa DDL vận hành, không chạy trên bảng production khi chưa lập kế hoạch.
ALTER TABLE sales_history
MOVE ROW STORE COMPRESS BASIC;
~~~

`MOVE` có thể cần dung lượng trống bổ sung trong quá trình thực thi, tạo I/O/CPU đáng kể, thay đổi ROWID của hàng và làm ảnh hưởng trạng thái các index phụ thuộc tùy phiên bản/cách thực hiện. Các tùy chọn online và bảo trì index có ràng buộc riêng. Vì thế:

- Chạy thử trên bản sao hoặc môi trường stage trước.
- Xác định đủ dung lượng, cửa sổ bảo trì và khả năng ứng dụng chịu được tác động.
- Xác định index/constraint/dependency cần bảo trì và xác nhận trạng thái index sau thao tác.
- Lập phương án rollback/restore phù hợp; đừng nhầm `ROLLBACK` SQL với hoàn tác DDL đã commit.
- Đảm bảo các hoạt động bulk/migration có ghi log, được theo dõi và tuân thủ quyền sử dụng feature.

### 9.3 CTAS để thử nghiệm mà không thay bảng nguồn

`CREATE TABLE ... AS SELECT` cho phép dựng bản sao dữ liệu theo chế độ nén trong schema thí nghiệm, nhưng nó **không bảo toàn tự động toàn bộ đặc tính của bảng nguồn**. Cần hiểu sự khác nhau về index, constraint, grants, trigger, partitioning, LOB settings và thống kê khi so sánh.

Nếu muốn so sánh công bằng, tạo những bản sao độc lập từ **cùng snapshot dữ liệu**, chạy cùng truy vấn và chọn cùng phạm vi đối tượng khi đo dung lượng. Việc thử Advanced hoặc HCC phải được duyệt theo entitlement trước.

## 10. Partition compression: nóng để ghi, lạnh để đọc

Partitioning và table compression giải quyết hai vấn đề khác nhau:

- **Partitioning** tổ chức dữ liệu thành các phân đoạn logic/vật lý nhỏ hơn theo tiêu chí như ngày hoặc vùng, giúp quản lý và có thể giảm dữ liệu cần đọc khi optimizer partition-pruning.
- **Compression** giảm dung lượng/chi phí lưu trữ của dữ liệu trong segment tương ứng.

Kết hợp hai cơ chế hữu ích khi mỗi partition có vòng đời khác nhau.

Ví dụ hệ thống đơn hàng lưu theo tháng:

~~~text
ORDERS
 |
 +-- P_2026_11    [HOT]   giao dịch mới, cập nhật nhiều
 +-- P_2026_10    [WARM]  chủ yếu đọc, một số cập nhật muộn
 +-- P_2026_09    [COLD]  gần như chỉ báo cáo
 +-- P_2026_08    [COLD]  lưu lịch sử
 +-- ...
~~~

Một chính sách có thể là:

1. Dữ liệu tháng hiện tại dùng `NOCOMPRESS` hoặc chế độ row compression phù hợp với DML nếu được phép.
2. Khi hết thời gian sửa đổi thường xuyên, phân vùng được chuyển qua một quy trình bulk/reorganization có kiểm soát.
3. Partition lịch sử dùng Basic hoặc HCC phù hợp entitlement, storage và yêu cầu truy vấn.
4. Báo cáo có filter ngày để tận dụng partition pruning; nén làm giảm I/O phần dữ liệu thật sự phải đọc.

Mẫu cú pháp minh họa trong môi trường hỗ trợ:

~~~sql
-- Xác định đúng partition và tác động index trước khi thực thi.
ALTER TABLE orders
MOVE PARTITION p_2026_08
ROW STORE COMPRESS BASIC;
~~~

Thao tác `MOVE PARTITION` là DDL có tác động vật lý, có thể ảnh hưởng index (đặc biệt các thành phần index liên quan) và tính sẵn sàng. Tùy phiên bản, tính năng/tùy chọn bảo trì index và online khác nhau. Ví dụ này trình bày chiến lược quản lý dữ liệu; không phải lệnh chạy trên production khi chưa có kế hoạch.

**Partitioning cũng có điều kiện cấp phép/tính năng riêng tùy môi trường Oracle.** Không nên mặc định rằng vì Basic compression được phép nên tự động được phép dùng mọi tính năng partitioning liên quan.

## 11. Đo compression bằng một bài lab cô lập

Các lệnh sau dành cho một **schema thực hành riêng** có quyền tạo bảng và quota phù hợp. Mục tiêu là quan sát tỉ lệ nén và kết quả truy vấn, không phải tuning database đang phục vụ người dùng. Các ví dụ tập trung vào **BASIC** để minh họa quá trình; chỉ chạy nếu môi trường cấp phép và hỗ trợ chế độ đó. Với Advanced/HCC, phải xác nhận entitlement trước khi tạo bản sao thử.

### 11.1 Tạo dữ liệu giả lập có độ lặp

~~~sql
CREATE TABLE lab_sales_source AS
SELECT LEVEL AS sale_id,
       MOD(LEVEL - 1, 1000) + 1 AS customer_id,
       DATE '2026-01-01' + MOD(LEVEL, 300) AS sale_date,
       CASE MOD(LEVEL, 4)
           WHEN 0 THEN 'HCM'
           WHEN 1 THEN 'HN'
           WHEN 2 THEN 'DN'
           ELSE 'CT'
       END AS region_code,
       CASE MOD(LEVEL, 5)
           WHEN 0 THEN 'REFUNDED'
           WHEN 1 THEN 'PAID'
           ELSE 'COMPLETED'
       END AS sale_status,
       RPAD('STANDARD-SALES-RECORD', 160, 'X') AS repeated_text,
       ROUND(MOD(LEVEL * 37, 10000) / 100, 2) AS amount
FROM dual
CONNECT BY LEVEL <= 100000;
~~~

Ở đây nhiều giá trị `REGION_CODE`, `SALE_STATUS` và `REPEATED_TEXT` lặp lại; bài lab có khả năng thể hiện tác dụng nén rõ hơn dữ liệu ngẫu nhiên. Tuy nhiên nó **không đại diện cho mọi workload**: dữ liệu thật có phân bố khóa, số lần update, kích thước hàng và nhiều loại cột khác.

### 11.2 Dựng hai bản sao từ cùng nguồn

~~~sql
-- Bản sao heap không nén.
CREATE TABLE lab_sales_plain
NOCOMPRESS
AS
SELECT * FROM lab_sales_source;

-- Bản sao Basic Table Compression.
CREATE TABLE lab_sales_basic
ROW STORE COMPRESS BASIC
AS
SELECT * FROM lab_sales_source;
~~~

`CTAS` là một cách tạo segment theo bulk load thích hợp để quan sát Basic compression. Đảm bảo cả hai câu chạy thành công, cùng số hàng và cùng dữ liệu logic trước khi đo. Bảng nguồn `LAB_SALES_SOURCE` chỉ giúp tạo tập thử; không tính nó vào kích thước so sánh giữa `PLAIN` và `BASIC`.

### 11.3 Xem metadata compression

Không cần quyền xem toàn database, user sở hữu bảng có thể truy vấn:

~~~sql
SELECT table_name, compression, compress_for
FROM user_tables
WHERE table_name IN ('LAB_SALES_PLAIN', 'LAB_SALES_BASIC')
ORDER BY table_name;
~~~

Kết quả phản ánh **metadata của đối tượng**. Nó không phải phép đo phần trăm dữ liệu thực sự nén. Nếu một bảng được bật nén sau khi chứa dữ liệu cũ, `COMPRESSION`/`COMPRESS_FOR` có thể cho biết chế độ đã cấu hình nhưng không chứng minh tất cả hàng cũ đang nén.

### 11.4 Đo allocated segment size

~~~sql
SELECT segment_name,
       segment_type,
       bytes,
       ROUND(bytes / 1024 / 1024, 2) AS allocated_mb
FROM user_segments
WHERE segment_name IN ('LAB_SALES_PLAIN', 'LAB_SALES_BASIC')
ORDER BY segment_name;
~~~

`USER_SEGMENTS.BYTES` là **dung lượng đã cấp cho segment**, không phải tổng byte chứa payload các hàng. Với bảng nhỏ, extent allocation, high-water mark, free space và metadata có thể làm phép so sánh phần trăm chưa ổn định. Hai bảng vừa CTAS cùng dữ liệu thường giúp so sánh trực tiếp hơn, nhưng nên thử dữ liệu đủ lớn và đo lại với workload đại diện.

Đối với bảng partition, không chỉ nhìn tên table và giả định có một segment duy nhất: mỗi table partition/subpartition có thể có segment riêng. Cần đọc metadata partition và tổng hợp đúng phạm vi.

### 11.5 Xác nhận cùng số hàng và kết quả phân tích

~~~sql
SELECT 'PLAIN' AS variant,
       COUNT(*) AS row_count,
       SUM(amount) AS total_amount
FROM lab_sales_plain
UNION ALL
SELECT 'BASIC' AS variant,
       COUNT(*) AS row_count,
       SUM(amount) AS total_amount
FROM lab_sales_basic;
~~~

Sau đó chạy cùng truy vấn trên từng bảng:

~~~sql
SELECT region_code,
       sale_status,
       COUNT(*) AS n,
       SUM(amount) AS total_amount
FROM lab_sales_basic
WHERE sale_date >= DATE '2026-01-01'
  AND sale_date < DATE '2026-07-01'
GROUP BY region_code, sale_status
ORDER BY region_code, sale_status;
~~~

Đổi tên bảng từ `LAB_SALES_BASIC` sang `LAB_SALES_PLAIN` và đo trong điều kiện tương đương. Dữ liệu nén không được làm thay đổi kết quả SQL đúng về mặt logic.

### 11.6 Thu thập thống kê và đọc execution plan

Với account có quyền phù hợp trong schema lab:

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(USER, 'LAB_SALES_PLAIN');
    DBMS_STATS.GATHER_TABLE_STATS(USER, 'LAB_SALES_BASIC');
END;
/
~~~

Sau đó có thể kiểm tra plan:

~~~sql
EXPLAIN PLAN FOR
SELECT region_code, SUM(amount) AS total_amount
FROM lab_sales_basic
GROUP BY region_code;

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

`EXPLAIN PLAN` là **dự kiến**; nó không xác nhận số block hay CPU thực tế đã tiêu thụ. Muốn đánh giá hiệu năng cần chạy truy vấn, thu thập thời gian, logical/physical reads và plan runtime nếu được phép. Đừng dùng một lần chạy duy nhất làm kết luận: lần đầu có thể bị cold cache, lần sau có warm cache, và SQL khác có thể đang chạy đồng thời.

### 11.7 Dọn dữ liệu lab

Chỉ xóa các bảng do bạn tạo trong **schema lab** sau khi xác nhận không còn ai sử dụng. `DROP TABLE` là DDL có implicit commit và có thể khiến dữ liệu mất theo cơ chế quản lý đối tượng của Oracle; không dùng câu lệnh xóa bảng trên schema thật để tái tạo thử nghiệm.

## 12. Đánh giá hiệu năng công bằng: cần đo những gì?

Một thử nghiệm chỉ đo dung lượng chưa đủ để quyết định nén bảng production.

| Thước đo | Vì sao cần đo? | Gợi ý quan sát |
|---|---|---|
| **Table segment size** | Đánh giá tiết kiệm dung lượng bảng | `USER_SEGMENTS`/`DBA_SEGMENTS` theo đúng table/partition |
| **Tổng storage của đối tượng** | Index, LOB, partition khác có thể vẫn lớn | Tổng hợp đúng phạm vi table + index + LOB nếu đó là mục tiêu |
| **Elapsed time của SELECT** | Đánh giá tốc độ báo cáo thực tế | Nhiều lần chạy và cùng điều kiện cache/concurrency |
| **CPU time** | Nén/giải nén có thể làm tăng CPU | Runtime SQL statistics / công cụ theo dõi cho phép |
| **Logical và physical reads** | Phân biệt tác động lên buffer cache/I/O | Plan/runtime statistics; không đồng nhất hai chỉ số |
| **DML throughput, p95/p99 latency** | Đánh giá ảnh hưởng lên workload giao dịch | Load test INSERT/UPDATE/DELETE với mức đồng thời đại diện |
| **Redo/undo generated** | Kiểm tra chi phí thay đổi dữ liệu và migration | Quan sát vận hành theo cửa sổ workload tương đương |
| **Thời gian bulk load hoặc MOVE** | Nén dữ liệu cũ có thể là công việc tốn tài nguyên | Đo thời gian, CPU, I/O, dung lượng trống cần thêm |
| **Backup/restore duration** | Tác động vào quy trình bảo vệ dữ liệu | Kiểm tra riêng backup tool và loại nén backup |
| **License và phí nền tảng** | Xác nhận chi phí và quyền sử dụng | Hợp đồng, licensing guide theo release/deployment |

### 12.1 Trình tự benchmark đề xuất

1. **Chốt workload:** ví dụ 70% tra cứu theo mã đơn, 25% báo cáo theo ngày, 5% update trạng thái. Tỷ lệ là minh họa, không áp đặt.
2. **Đóng băng tập dữ liệu:** các bản sao phải cùng snapshot và cùng độ phân bố dữ liệu; nếu không, chênh lệch có thể đến từ dữ liệu chứ không phải compression.
3. **Kiểm tra cấu trúc và thống kê:** index/partition/LOB tương ứng, session settings, statistics, plan và bind values phải được ghi nhận.
4. **Đo cả cold và warm cache:** cùng kịch bản, không chọn một kết quả thuận lợi rồi tổng quát hóa.
5. **Đo dưới tải đồng thời:** một report nhanh hơn khi chạy một mình có thể không còn lợi ích khi CPU bị DML chiếm.
6. **Đo pha nạp/cập nhật dữ liệu:** không chỉ SELECT; đánh giá tổng chi phí vận hành của chế độ nén.
7. **Lập kết luận theo SLA:** dung lượng, CPU, I/O, p95/p99, thời gian batch, mức độ sẵn sàng và entitlement.

Không nên dùng một chỉ số “compression ratio cao nhất” làm tiêu chí duy nhất. Chọn chế độ nén là bài toán tối ưu **nhiều ràng buộc**.

## 13. Xác minh điều kiện tính năng và giấy phép

Phần này là một thành tố của thiết kế kỹ thuật, không phải bước giấy tờ ở cuối dự án. Trong Oracle, hai môi trường có thể cùng chấp nhận một câu DDL nhưng **quyền sử dụng thương mại không giống nhau**.

### 13.1 Những biến số quyết định entitlement

Trước khi bật một chế độ compression, xác nhận tối thiểu:

| Thông tin cần xác nhận | Vì sao quan trọng? |
|---|---|
| **Oracle Database release và edition** | Tập tính năng và điều kiện có thể khác theo bản phát hành/edition |
| **Môi trường on-premises hay cloud/managed database** | Một số quyền có thể được bao gồm trong một gói cloud nhưng cần option riêng trong mô hình khác |
| **Hạ tầng lưu trữ thực tế** | Đặc biệt với HCC, không phải storage nào cũng hỗ trợ |
| **Tính năng chính xác đang dùng** | Basic Table Compression, Advanced Row Compression, HCC Query/Archive, SecureFiles LOB và index compression là các phạm vi khác nhau |
| **Hợp đồng/SKU và tính năng đã mua hoặc dịch vụ đã đăng ký** | SQL chạy được không đồng nghĩa quyền sử dụng đã được cấp |
| **Cách chuyển bản sao/backup/data giữa môi trường** | Target có thể khác quyền sử dụng hoặc hỗ trợ storage |
| **Oracle Licensing Information User Manual cùng release** | Tài liệu tham chiếu chính thức về giới hạn kỹ thuật và phạm vi cấp phép |

Với **Basic Table Compression**, không suy từ chữ “Basic” rằng tính năng miễn phí trong mọi Oracle edition. Với **Advanced Row Compression**, phải xem yêu cầu của **Advanced Compression option** hoặc entitlement tương ứng trong gói dịch vụ đang dùng. Với **HCC**, phải kiểm tra thêm điều kiện storage/engine và chính sách licensing đặc thù. Ngay cả khi hệ thống đã mua một option, một tính năng khác có tên gần giống chưa chắc nằm trong cùng entitlement.

### 13.2 “Câu lệnh chạy được” không phải bằng chứng cấp phép

Database có thể cho phép thử một cú pháp tính năng trong một số tình huống vì cơ chế kiểm tra kỹ thuật và entitlement thương mại là hai khía cạnh khác nhau. Do đó:

- Không thử `ROW STORE COMPRESS ADVANCED` trên production rồi mới hỏi có cần license không.
- Không suy entitlement chỉ từ giá trị `COMPRESSION`/`COMPRESS_FOR` ở dictionary.
- Không suy entitlement chỉ từ việc một chức năng xuất hiện trên GUI.
- Không lấy việc một câu lệnh chạy thành công làm xác nhận từ Oracle.
- Không coi bảng đo sử dụng tính năng là bằng chứng tự động rằng doanh nghiệp **đã có** quyền dùng tính năng đó.

Các công cụ theo dõi feature usage có thể giúp kiểm kê, nhưng **điều khoản cấp phép/entitlement phải được đối chiếu độc lập** với nguồn chính thức và hợp đồng của đơn vị.

### 13.3 Nếu tài liệu phiên bản và kiến trúc dự án mâu thuẫn

Ưu tiên xác minh với tài liệu Oracle dành cho release/edition/deployment của hệ thống, đặc biệt khi sử dụng các dịch vụ cloud hoặc nền tảng tích hợp. Quyền sử dụng thay đổi theo thời gian và mô hình cung cấp; không áp dụng một khẳng định cấp phép cũ cho mọi release.

Một bảng quyết định ngắn trước khi bật compression:

~~~text
Cần nén bảng
    |
    v
Xác định loại dữ liệu / workload / SLA
    |
    v
Chọn ứng viên BASIC / ADVANCED / HCC
    |
    v
Kiểm tra version + edition + storage + entitlement
    |
    +-- Không hỗ trợ/chưa có quyền --> Dừng dùng chế độ đó, chọn phương án khác
    |
    +-- Được hỗ trợ và có quyền
            |
            v
    Benchmark dữ liệu và workload thật
            |
            v
    Quyết định rollout + rollback + monitoring
~~~

## 14. Các rủi ro vận hành khi chuyển bảng đang dùng sang nén

### 14.1 DDL, implicit commit và khả năng hoàn tác

Các lệnh `ALTER TABLE ... MOVE` và CTAS là DDL. Không kỳ vọng `ROLLBACK` thông thường sẽ hoàn tác một table move đã hoàn tất. Nếu chuyển đổi trên bảng thật, cần backup/restore hoặc chiến lược tạo bảng mới và chuyển đổi có kiểm soát, tùy yêu cầu sẵn sàng và khả năng rollback.

### 14.2 ROWID, index và đối tượng phụ thuộc

Các thao tác viết lại table segment có thể thay đổi `ROWID` và ảnh hưởng index. Nếu ứng dụng lưu ROWID lâu dài như định danh nghiệp vụ, đó đã là một thiết kế cần xem lại; ROWID có thể thay đổi khi dữ liệu di chuyển vật lý. Index cần được quản lý/trạng thái kiểm tra theo lệnh và phiên bản sử dụng; tránh giả định chúng vẫn tự hoạt động bình thường sau mọi loại MOVE.

### 14.3 Temporary space và lượng tài nguyên lúc chuyển đổi

Nén để **tiết kiệm dung lượng cuối cùng** vẫn có thể cần **thêm dung lượng trong quá trình chuyển đổi**: segment mới, index rebuild, undo/redo, backup hoặc không gian làm việc phụ trợ. Nếu bảng lớn và storage gần đầy, một kế hoạch “nén để giải phóng đĩa” vẫn có thể không thực hiện được nếu thiếu dung lượng ban đầu.

### 14.4 Dữ liệu mới có giữ đúng chế độ nén không?

Sau bulk migration, workload bình thường có thể bổ sung và sửa hàng theo phương thức khác. Với Basic hoặc HCC, dữ liệu mới/đã sửa có thể làm hiệu quả nén chung giảm. Vì thế cần giám sát **xu hướng segment size** và lên lịch quản lý lifecycle, thay vì chỉ đo ngay sau lần nén đầu.

### 14.5 Ảnh hưởng tới transaction và độ sẵn sàng

Một thao tác compression/reorganization chạy sai thời điểm có thể tạo I/O/CPU lớn, cạnh tranh với OLTP, gây khóa/gián đoạn theo cơ chế DDL và các giới hạn online. Phải xác định cửa sổ bảo trì, mức tải cho phép, quyền truy cập và công cụ rollback/recovery. Một bảng 2 TB được nén còn 900 GB vẫn có thể gây sự cố dịch vụ nếu phương án chuyển đổi không phù hợp.

## 15. Ma trận chọn chiến lược theo loại bảng

| Bối cảnh dữ liệu | Ứng viên đáng đánh giá | Lý do | Cần đặc biệt kiểm tra |
|---|---|---|---|
| Bảng giao dịch nhỏ, ghi rất nhiều, CPU cao | `NOCOMPRESS` hoặc benchmark Advanced nếu có entitlement | DML latency có thể quan trọng hơn dung lượng | CPU, p95/p99, row migration, ratio thực |
| Bảng giao dịch rất lớn, nhiều giá trị lặp, vừa đọc vừa ghi | Advanced Row Compression | Có cơ chế hỗ trợ DML thông thường tốt hơn Basic | Advanced Compression entitlement, throughput ghi |
| Bảng tổng hợp được dựng lại theo batch | Basic Table Compression | Nạp/CTAS theo lô phù hợp cơ chế Basic | Load time, truy vấn scan, edition/license |
| Partition của dữ liệu năm trước, ít cập nhật | Basic hoặc HCC (nếu hỗ trợ) | Giảm số block lưu trữ, tận dụng tính bất biến | DML muộn, storage HCC, query/archival SLA |
| Kho lịch sử phục vụ scan lớn, ít DML | HCC Query hoặc Archive (nếu hỗ trợ/được cấp phép) | Ưu tiên giảm dung lượng cho phân tích/lưu trữ | CPU giải nén, storage và entitlement |
| Bảng có BLOB/CLOB rất lớn | Xem chính sách SecureFiles LOB riêng | Row-store compression có thể không giải quyết phần LOB | LOB storage, loại dữ liệu đã nén, license |
| Truy vấn điểm theo PK, bảng fit trong cache | Có thể chưa cần nén | Lợi ích giảm physical I/O có thể hạn chế | CPU, index lookup, workload thực |

Các gợi ý này là **điểm bắt đầu để benchmark**, không phải công thức chung. Cùng một loại bảng có thể nên dùng chế độ khác nhau ở các môi trường có CPU, I/O, dữ liệu, giá storage và license khác nhau.

## 16. Những nhầm lẫn thường gặp

**“Table compression sẽ làm mọi SELECT chạy nhanh hơn.”** Không đúng. Truy vấn I/O-bound có thể hưởng lợi; truy vấn CPU-bound hoặc truy cập rất ít hàng có thể không cải thiện, thậm chí chịu thêm CPU.

**“Advanced luôn có tỉ lệ nén cao hơn Basic.”** Tên chế độ nói về khả năng xử lý workload và cơ chế nén, không phải cam kết mức ratio trên mọi tập dữ liệu. Phải đo trên dữ liệu thực tế.

**“HCC giống In-Memory Column Store.”** Không đúng. HCC là cơ chế lưu trữ nén dữ liệu bảng theo compression unit trên storage được hỗ trợ; In-Memory Column Store là cấu trúc trong memory để phục vụ truy vấn và có mô hình tính năng/giấy phép riêng.

**“Chạy ALTER TABLE ... COMPRESS thì tất cả block cũ lập tức được nén.”** Không đúng. Thay metadata và viết lại các block hiện có là hai việc khác nhau. Với dữ liệu cũ cần xác định thao tác phù hợp như CTAS/MOVE hoặc quy trình được hỗ trợ.

**“Đo USER_SEGMENTS giảm 60% nghĩa là cả database giảm 60%.”** Không đúng. Table chỉ là một phần của tổng storage; index, LOB, undo, redo, TEMP, backup và overhead khác có phạm vi riêng.

**“Chỉ cần tăng CPU để bù chi phí nén.”** Không chắc. DML, locking, bộ nhớ, I/O, redo, workload đồng thời và cách Oracle thực thi vẫn chi phối kết quả.

**“Basic là miễn phí, Advanced là trả phí, HCC thì luôn có sẵn trên mọi Oracle.”** Đây là kết luận cấp phép quá đơn giản và có thể sai theo release/edition/deployment. Cần đọc licensing guide, điều kiện storage và entitlement thực.

**“Có chức năng trong sản phẩm nghĩa là đã được cấp phép sử dụng.”** Không đúng. Khả năng kỹ thuật và quyền sử dụng thương mại là hai bước xác minh riêng.

## 17. Tình huống tổng hợp

Một doanh nghiệp chạy Oracle Database với hệ thống thương mại điện tử:

- `ORDERS_CURRENT` chứa đơn của 3 tháng gần nhất, cập nhật trạng thái liên tục.
- `ORDERS_HISTORY` chứa đơn 5 năm trước, chủ yếu dùng trong báo cáo tài chính và phân tích.
- `ORDER_ATTACHMENTS` chứa hình ảnh, hóa đơn PDF và tài liệu tải lên ở dạng LOB.
- Storage đang tăng nhanh; CPU vào giờ cao điểm đạt mức sử dụng cao.

Nhóm dự án muốn nén cả ba bảng theo mức mạnh nhất để tiết kiệm tiền lưu trữ.

### Cách suy luận phù hợp

**Đối với ORDERS_CURRENT:** phải thử nghiệm tác động lên ghi/đọc và độ trễ API; Advanced Row Compression chỉ là ứng viên nếu entitlement phù hợp. Nếu CPU đã bão hòa và nén không tiết kiệm đáng kể, giữ `NOCOMPRESS` có thể tốt hơn.

**Đối với ORDERS_HISTORY:** dữ liệu ít cập nhật, thường quét theo kỳ. Có thể so sánh Basic và HCC nếu môi trường cho phép. Nếu lưu theo partition, chỉ chuyển những partition đã đóng kỳ sang chế độ nén phù hợp; cần đo cả thời gian đọc báo cáo và thời gian move/nạp.

**Đối với ORDER_ATTACHMENTS:** không suy nén table sẽ giảm dung lượng ảnh/PDF đã nén. Phải kiểm tra loại LOB, định dạng file, SecureFiles compression và entitlement riêng. Nén thêm file đã nén có thể không hiệu quả.

**Đối với toàn hệ thống:** đo tổng storage đã cấp, CPU, I/O, p99 giao dịch và thời gian báo cáo. Không thay đổi đồng loạt ở giờ cao điểm; lập phương án chuyển đổi/rollback có kiểm soát.

### Bài tập suy nghĩ

1. Vì sao không nên đo chỉ `ORDERS_CURRENT` trong giờ ít tải rồi kết luận nén không ảnh hưởng OLTP?
2. Nếu Basic cho `ORDERS_HISTORY` ratio 2.2:1 còn HCC Archive đạt 4.5:1 nhưng báo cáo chậm hơn đáng kể, nên dùng chỉ số nào để ra quyết định?
3. Nếu bảng 500 GB sau nén còn 250 GB, liệu việc `MOVE` có chắc thực hiện được khi tablespace chỉ còn 100 GB trống?
4. Khi chuyển database từ hạ tầng được hỗ trợ HCC sang môi trường khác, những thông tin nào phải xác minh trước khi di chuyển dữ liệu?
5. Tại sao cần tách việc đo table segment với index segment và LOB segment?

**Gợi ý trả lời:** đánh giá workload đồng thời; cân bằng ratio với SLA và CPU; tính cả dung lượng trung gian khi viết lại segment; kiểm tra storage/edition/entitlement ở hệ đích; và giữ phạm vi đo nhất quán để tránh báo cáo sai mức tiết kiệm.

## 18. Ghi nhớ khi thiết kế table compression

Table compression trong Oracle là **một quyết định về kiến trúc lưu trữ và workload**, không chỉ là một câu lệnh DDL. Basic phù hợp hơn với dữ liệu nạp theo lô; Advanced Row Compression hướng đến khả năng nén ngay cả khi có DML thông thường; HCC phục vụ mạnh hơn cho dữ liệu phân tích/lưu trữ đọc nhiều trong những môi trường được hỗ trợ. Chọn chế độ nào phải dựa trên dữ liệu thật, CPU/I/O, hoạt động ghi, nhu cầu quản lý partition và thời gian báo cáo.

Trước khi triển khai, hãy xác định **phạm vi dữ liệu cần nén, cách đánh giá ratio, hiệu năng SQL/DML, tài nguyên khi chuyển đổi, và điều kiện tính năng/giấy phép chính xác của môi trường Oracle**. Một giải pháp tốt vừa tiết kiệm dung lượng, vừa giữ được SLA của hệ thống và nằm trong quyền sử dụng sản phẩm đã được xác nhận.
