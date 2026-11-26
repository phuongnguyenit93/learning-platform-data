# Kết hợp nhiều phép tổng hợp mà không nhân đôi số liệu

Trong Neo4j, một báo cáo thường cần nhiều chỉ số cùng lúc: **số đơn hàng**, **tổng tiền**, **số yêu cầu hỗ trợ** và **tổng số sản phẩm đã mua** của từng khách hàng. Các phép tính `count()`, `sum()`, `avg()`, `min()`, `max()` có thể xuất hiện trong một câu `RETURN` hoặc `WITH`. Tuy nhiên, nếu truy vấn đi qua nhiều nhánh quan hệ, **một node có thể xuất hiện nhiều lần trong các dòng trung gian**. Khi đó, kết quả tổng hợp có thể sai dù cú pháp Cypher hợp lệ.

Bài học thuộc chương **Tổng hợp dữ liệu** của module Neo4j. Trọng tâm là xác định đúng **đơn vị được tính** (*grain*), kiểm soát số dòng do các mẫu property graph tạo ra, rồi kết hợp nhiều phép tổng hợp mà không cộng hoặc đếm trùng. Các kỹ thuật dùng được cho truy vấn báo cáo trước khi trả kết quả qua Java Driver, Spring Data Neo4j hoặc một API dịch vụ.

## 1. Mô hình và bộ dữ liệu thực hành

Xét đồ thị của một cửa hàng sách có khách hàng, đơn hàng, yêu cầu hỗ trợ và sản phẩm:

~~~text
(:Customer)-[:PLACED]->(:Order)-[:HAS_LINE {quantity}]->(:Product)
      |
      +------[:OPENED]----->(:Ticket)
~~~

- `Customer`: `id`, `name`; định danh khách hàng.
- `Order`: `id`, `amount` (giá trị đơn, VND), `status`.
- `Ticket`: `id`, `status`; yêu cầu hỗ trợ mà khách đã mở.
- `Product`: `sku`, `name`; sản phẩm trong một hoặc nhiều đơn.
- `HAS_LINE.quantity`: số lượng của sản phẩm trong đơn.

Tạo dữ liệu trên **cơ sở dữ liệu thực hành trống**. Chỉ chạy một lần để không tạo các node và relationship trùng:

~~~cypher
CREATE
  (an:Customer {id: 'C01', name: 'An'}),
  (binh:Customer {id: 'C02', name: 'Binh'}),
  (chi:Customer {id: 'C03', name: 'Chi'}),
  (dung:Customer {id: 'C04', name: 'Dung'}),
  (o101:Order {id: 'O101', amount: 100000, status: 'PAID'}),
  (o102:Order {id: 'O102', amount: 100000, status: 'PENDING'}),
  (o103:Order {id: 'O103', amount: 150000, status: 'PAID'}),
  (o104:Order {id: 'O104', amount: 80000, status: 'PAID'}),
  (t01:Ticket {id: 'T01', status: 'OPEN'}),
  (t02:Ticket {id: 'T02', status: 'CLOSED'}),
  (t03:Ticket {id: 'T03', status: 'OPEN'}),
  (t04:Ticket {id: 'T04', status: 'OPEN'}),
  (p01:Product {sku: 'P01', name: 'Neo4j'}),
  (p02:Product {sku: 'P02', name: 'Java'}),
  (an)-[:PLACED]->(o101),
  (an)-[:PLACED]->(o102),
  (binh)-[:PLACED]->(o103),
  (dung)-[:PLACED]->(o104),
  (an)-[:OPENED]->(t01),
  (an)-[:OPENED]->(t02),
  (binh)-[:OPENED]->(t03),
  (chi)-[:OPENED]->(t04),
  (o101)-[:HAS_LINE {quantity: 1}]->(p01),
  (o101)-[:HAS_LINE {quantity: 2}]->(p02),
  (o102)-[:HAS_LINE {quantity: 3}]->(p02),
  (o103)-[:HAS_LINE {quantity: 2}]->(p01),
  (o104)-[:HAS_LINE {quantity: 1}]->(p02);
~~~

Các chỉ số **đúng theo nghiệp vụ** của từng khách như sau:

| Khách | Số đơn | Tổng tiền đơn (VND) | Số ticket | Ticket OPEN | Tổng số lượng sản phẩm |
|---|---:|---:|---:|---:|---:|
| C01 / An | 2 | 200000 | 2 | 1 | 6 |
| C02 / Binh | 1 | 150000 | 1 | 1 | 2 |
| C03 / Chi | 0 | 0 | 1 | 1 | 0 |
| C04 / Dung | 1 | 80000 | 0 | 0 | 1 |
| **Tổng** | **4** | **430000** | **4** | **3** | **9** |

Lưu ý: O101 và O102 là **hai đơn khác nhau nhưng cùng có `amount = 100000`**. Đây là dữ liệu cố ý dùng để chứng minh rằng `sum(DISTINCT o.amount)` không thể thay thế tổng tiền của các đơn hàng riêng biệt.

## 2. Vì sao tổng hợp bị nhân đôi?

Giả sử muốn trả cùng lúc số đơn, tổng tiền và số ticket của mỗi khách. Truy vấn sau trông có vẻ hợp lý:

~~~cypher
MATCH (c:Customer)
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
OPTIONAL MATCH (c)-[:OPENED]->(t:Ticket)
RETURN
  c.id AS maKhach,
  count(o) AS soDon,
  sum(o.amount) AS tongTien,
  count(t) AS soTicket
ORDER BY maKhach;
~~~

Nhưng với An, hai nhánh `PLACED` và `OPENED` đều là quan hệ **một đến nhiều**. Mỗi đơn có thể kết hợp với mỗi ticket của cùng khách:

| Dòng sau hai OPTIONAL MATCH | Đơn `o` | Ticket `t` | `o.amount` |
|---:|---|---|---:|
| 1 | O101 | T01 | 100000 |
| 2 | O101 | T02 | 100000 |
| 3 | O102 | T01 | 100000 |
| 4 | O102 | T02 | 100000 |

Vì vậy truy vấn trả cho C01:

- `count(o) = 4` thay vì **2**.
- `sum(o.amount) = 400000` thay vì **200000**.
- `count(t) = 4` thay vì **2**.

Đây là hiện tượng **nhân số dòng trung gian** (*row multiplication/fan-out*). Cypher đang tổng hợp trên các **cặp đơn–ticket**, không phải lần lượt trên tập đơn và tập ticket độc lập.

Nếu một khách có `m` đơn và `n` ticket, hai nhánh quan hệ không phụ thuộc nhau có thể tạo `m × n` dòng khi cả hai tập đều không rỗng. Với `OPTIONAL MATCH`, nhánh không khớp vẫn giữ dòng với biến tương ứng bằng `null`; vì vậy không thể đơn giản lấy tích `m × n` cho mọi trường hợp có tập rỗng.

### 2.1. Phân biệt count(*) và count(biến)

Đối với Chi, khách không có đơn nhưng có một ticket T04:

~~~cypher
MATCH (c:Customer {id: 'C03'})
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
OPTIONAL MATCH (c)-[:OPENED]->(t:Ticket)
RETURN
  count(*) AS soDong,
  count(o) AS soDon,
  count(t) AS soTicket;
~~~

Kết quả: `soDong = 1`, `soDon = 0`, `soTicket = 1`. `OPTIONAL MATCH` giữ khách dù biến đơn `o` là `null`. Khi đếm thực thể liên quan, `count(o)` và `count(t)` rõ nghĩa hơn `count(*)`.

### 2.2. Sai ở mức dòng đầu vào, không phải tại hàm sum()

`sum(o.amount)` thực hiện đúng yêu cầu kỹ thuật: cộng các giá trị `o.amount` ở **mọi dòng đang tồn tại**. Lỗi nằm ở việc một đơn được lặp lại qua nhiều đường khớp mẫu. Bởi vậy, cách xử lý hiệu quả là xác định đúng **mỗi chỉ số thuộc mức nào** trước khi tổng hợp.

## 3. COUNT(DISTINCT) giải quyết được gì và không giải quyết được gì?

Khi chỉ cần đếm số thực thể khác nhau, `DISTINCT` có thể loại các lần xuất hiện trùng:

~~~cypher
MATCH (c:Customer)
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
OPTIONAL MATCH (c)-[:OPENED]->(t:Ticket)
RETURN
  c.id AS maKhach,
  count(DISTINCT o) AS soDon,
  count(DISTINCT t) AS soTicket
ORDER BY maKhach;
~~~

Với An, kết quả đã đúng: `soDon = 2`, `soTicket = 2`. `DISTINCT o` dựa trên **danh tính node đơn**, nên hai lần xuất hiện của O101 chỉ được đếm một lần.

Tuy nhiên, không nên suy ra rằng thêm `DISTINCT` vào mọi phép tổng hợp đều đúng:

~~~cypher
MATCH (c:Customer {id: 'C01'})
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
OPTIONAL MATCH (c)-[:OPENED]->(t:Ticket)
RETURN
  sum(o.amount) AS tongSaiViLapDong,
  sum(DISTINCT o.amount) AS tongSaiViGopGiaTri,
  count(DISTINCT o) AS soDonDung;
~~~

| Phép tính | Kết quả | Vấn đề |
|---|---:|---|
| `sum(o.amount)` | 400000 | Mỗi đơn bị tính hai lần do hai ticket |
| `sum(DISTINCT o.amount)` | 100000 | Hai đơn thật có cùng amount nên bị gộp |
| `count(DISTINCT o)` | 2 | Đếm đúng hai node đơn khác nhau |

**`DISTINCT` hoạt động trên giá trị của biểu thức**, không tự hiểu đơn vị nghiệp vụ. Tổng tiền phải cộng **một lần cho mỗi đơn hàng**, kể cả khi hai đơn có cùng số tiền.

Tương tự, `collect(DISTINCT o)` hoặc `count(DISTINCT o)` có thể cần xử lý nhiều phần tử và dùng bộ nhớ. Khi báo cáo phức tạp, nên tránh tạo ra số dòng lặp quá lớn ngay từ đầu.

## 4. Giải pháp 1: Tổng hợp tuần tự bằng WITH

Một cách rõ ràng là tính **chỉ số của đơn hàng trước khi mở rộng sang ticket**:

~~~cypher
MATCH (c:Customer)
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
WITH
  c,
  count(o) AS soDon,
  sum(o.amount) AS tongTien
OPTIONAL MATCH (c)-[:OPENED]->(t:Ticket)
RETURN
  c.id AS maKhach,
  soDon,
  tongTien,
  count(t) AS soTicket
ORDER BY maKhach;
~~~

Kết quả:

| maKhach | soDon | tongTien | soTicket |
|---|---:|---:|---:|
| C01 | 2 | 200000 | 2 |
| C02 | 1 | 150000 | 1 |
| C03 | 0 | 0 | 1 |
| C04 | 1 | 80000 | 0 |

Ở `WITH c, count(o), sum(o.amount)`, khóa nhóm ngầm định là node `c`. Mỗi khách chỉ còn **một dòng** với số đơn và tổng tiền đã tính. Sau đó, `OPTIONAL MATCH` sang `Ticket` có thể tạo nhiều dòng ticket, nhưng hai chỉ số `soDon` và `tongTien` được **mang theo dưới dạng giá trị đã tính**. Chỉ `count(t)` được tính trên các dòng ticket ở bước cuối.

Quan trọng: ở `RETURN` cuối, `c.id`, `soDon` và `tongTien` là các biểu thức không tổng hợp nên trở thành **khóa nhóm** cho `count(t)`. Với bộ dữ liệu này, mã khách duy nhất nên kết quả vẫn một dòng mỗi khách.

### 4.1. Thêm nhiều chỉ số trên cùng nguồn dữ liệu

Các phép tổng hợp `count`, `sum`, `avg`, `min`, `max` có thể đi cùng nhau **nếu chúng được tính trên cùng tập dòng đúng mức**:

~~~cypher
MATCH (c:Customer)
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
WITH
  c,
  count(o) AS soDon,
  sum(o.amount) AS tongTien,
  avg(o.amount) AS trungBinhDon,
  min(o.amount) AS donNhoNhat,
  max(o.amount) AS donLonNhat,
  count(CASE WHEN o.status = 'PAID' THEN o END) AS soDonPaid,
  sum(CASE WHEN o.status = 'PAID' THEN o.amount ELSE 0 END)
    AS tienPaid
RETURN
  c.id AS maKhach,
  soDon,
  tongTien,
  trungBinhDon,
  donNhoNhat,
  donLonNhat,
  soDonPaid,
  tienPaid
ORDER BY maKhach;
~~~

Với C01, `soDon = 2`, `tongTien = 200000`, `trungBinhDon = 100000`, `donNhoNhat = 100000`, `donLonNhat = 100000`, `soDonPaid = 1`, `tienPaid = 100000`.

Với C03 không có đơn, `soDon = 0`, `tongTien = 0`, `trungBinhDon = null`, `min/max = null`. Đây là khác biệt có ý nghĩa: không có quan sát để tính trung bình hoặc cực trị.

### 4.2. Lọc nhóm giữa hai phép tổng hợp

Muốn chỉ thống kê ticket của khách có **ít nhất hai đơn**, lọc trên số đơn **sau** `WITH`:

~~~cypher
MATCH (c:Customer)
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
WITH c, count(o) AS soDon, sum(o.amount) AS tongTien
WHERE soDon >= 2
OPTIONAL MATCH (c)-[:OPENED]->(t:Ticket)
RETURN
  c.id AS maKhach,
  soDon,
  tongTien,
  count(t) AS soTicket;
~~~

Chỉ còn C01. Điều kiện `WHERE` sau `WITH` áp dụng lên **nhóm khách đã tổng hợp**, giúp tránh mở rộng quan hệ sang ticket cho các khách bị loại.

## 5. Giải pháp 2: CALL subquery cho các nhánh độc lập

Khi cần nhiều chỉ số từ nhiều quan hệ độc lập, có thể dùng `CALL { ... }` để tính riêng từng nhánh rồi ghép về node khách hàng:

~~~cypher
MATCH (c:Customer)
CALL {
  WITH c
  OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
  RETURN
    count(o) AS soDon,
    sum(o.amount) AS tongTien
}
CALL {
  WITH c
  OPTIONAL MATCH (c)-[:OPENED]->(t:Ticket)
  RETURN
    count(t) AS soTicket,
    count(CASE WHEN t.status = 'OPEN' THEN t END) AS soTicketMo
}
RETURN
  c.id AS maKhach,
  soDon,
  tongTien,
  soTicket,
  soTicketMo
ORDER BY maKhach;
~~~

Mỗi `CALL` chạy trong ngữ cảnh của khách `c` hiện tại. Subquery thứ nhất chỉ duyệt đơn hàng, nên tổng tiền không chịu ảnh hưởng từ số ticket. Subquery thứ hai chỉ duyệt ticket, nên số ticket không chịu ảnh hưởng từ số đơn.

| maKhach | soDon | tongTien | soTicket | soTicketMo |
|---|---:|---:|---:|---:|
| C01 | 2 | 200000 | 2 | 1 |
| C02 | 1 | 150000 | 1 | 1 |
| C03 | 0 | 0 | 1 | 1 |
| C04 | 1 | 80000 | 0 | 0 |

**Vì sao vẫn giữ khách không có đơn hoặc ticket?** Mỗi subquery sử dụng `OPTIONAL MATCH` và hàm tổng hợp không khóa nhóm, nên trả **một dòng chỉ số cho mỗi khách** kể cả khi nhánh không có quan hệ. Nếu thay thành `MATCH` bắt buộc và subquery không trả dòng, dòng khách ở bên ngoài có thể bị loại.

Ví dụ trên dùng `WITH c` để nhập biến vào subquery, tương thích với nhiều phiên bản Neo4j 5. Các phiên bản mới hơn hỗ trợ cách viết rõ phạm vi biến như `CALL (c) { ... }`; cần dùng cú pháp phù hợp phiên bản Neo4j đang chạy.

### 5.1. Khi nào ưu tiên WITH, khi nào ưu tiên CALL?

| Tình huống | Hướng phù hợp |
|---|---|
| Hai tập quan hệ đơn giản, có thể tính lần lượt | `WITH` tổng hợp một nhánh rồi mở rộng nhánh kế |
| Nhiều nhánh độc lập, mỗi nhánh có nhiều bước `MATCH/WHERE/WITH` | `CALL` subquery độc lập |
| Muốn tái sử dụng nhiều chỉ số trên cùng tập đơn | Tính chung trong một `WITH` hoặc một subquery |
| Chỉ cần số thực thể khác nhau sau khi các dòng bị nhân | Có thể dùng `count(DISTINCT node)`, cân nhắc chi phí |
| Chỉ có một nhánh và một mức tính | `MATCH ... RETURN` tổng hợp trực tiếp |

Subquery không tự động bảo đảm truy vấn luôn nhanh hơn. Lợi ích chính là **tách phạm vi tổng hợp và tránh sản phẩm kết hợp của các nhánh**. Cần `PROFILE` để xác nhận số dòng và chi phí thật.

## 6. Trộn tổng tiền đơn hàng và số lượng sản phẩm: hai mức dữ liệu khác nhau

Relationship `HAS_LINE` chứa số lượng sản phẩm. Nếu nối thẳng từ đơn đến sản phẩm rồi cộng cả tiền đơn lẫn số lượng, một đơn có nhiều dòng sản phẩm sẽ bị lặp:

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)
MATCH (o)-[line:HAS_LINE]->(p:Product)
RETURN
  c.id AS maKhach,
  count(o) AS soLanDonXuatHien,
  count(DISTINCT o) AS soDonThuc,
  sum(o.amount) AS tongTienSai,
  sum(line.quantity) AS tongSoLuong
ORDER BY maKhach;
~~~

Với C01, O101 có hai dòng sản phẩm (`P01`, `P02`) và O102 có một dòng. Vì vậy:

- `soLanDonXuatHien = 3`, trong khi số đơn thật là **2**.
- `tongTienSai = 300000`, trong khi tổng tiền thật là **200000**.
- `tongSoLuong = 6` là **đúng** vì mỗi `HAS_LINE` đóng góp một lượng hàng vào tổng.

Đơn vị của `o.amount` là **đơn hàng**, còn đơn vị của `line.quantity` là **dòng sản phẩm**. Muốn kết hợp chúng đúng, cần tính mỗi chỉ số tại mức tương ứng.

### 6.1. Tổng hợp hai cấp: từ dòng sản phẩm về đơn, rồi về khách

~~~cypher
MATCH (c:Customer)
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
OPTIONAL MATCH (o)-[line:HAS_LINE]->(:Product)
WITH
  c,
  o,
  sum(line.quantity) AS soLuongTheoDon
RETURN
  c.id AS maKhach,
  count(o) AS soDon,
  sum(o.amount) AS tongTien,
  sum(soLuongTheoDon) AS tongSoLuong
ORDER BY maKhach;
~~~

Trong `WITH c, o, sum(line.quantity)`, khóa nhóm là cặp **(khách, đơn)**. Mỗi đơn chỉ còn một dòng sau khi gom các dòng sản phẩm. Vì vậy, `sum(o.amount)` ở `RETURN` chỉ cộng **một lần trên mỗi đơn**.

| maKhach | soDon | tongTien | tongSoLuong |
|---|---:|---:|---:|
| C01 | 2 | 200000 | 6 |
| C02 | 1 | 150000 | 2 |
| C03 | 0 | 0 | 0 |
| C04 | 1 | 80000 | 1 |

Lưu ý: mẫu hai cấp này giả định mỗi đơn thuộc một khách trong mô hình và mỗi `HAS_LINE` là một dòng chi tiết hợp lệ. Nếu trong dữ liệu thật một đơn có thể được khớp nhiều lần ngay trước `WITH` do các nhánh khác, cần gỡ nguyên nhân nhân dòng trước đó.

### 6.2. Phân lập cả ba tập chỉ số trong subquery

Khi cần **đơn hàng + ticket + số lượng sản phẩm** cùng lúc, có thể giữ riêng từng phép tổng hợp:

~~~cypher
MATCH (c:Customer)
CALL {
  WITH c
  OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
  RETURN
    count(o) AS soDon,
    sum(o.amount) AS tongTien
}
CALL {
  WITH c
  OPTIONAL MATCH (c)-[:OPENED]->(t:Ticket)
  RETURN count(t) AS soTicket
}
CALL {
  WITH c
  OPTIONAL MATCH (c)-[:PLACED]->(:Order)-[line:HAS_LINE]->(:Product)
  RETURN sum(line.quantity) AS tongSoLuong
}
RETURN
  c.id AS maKhach,
  soDon,
  tongTien,
  soTicket,
  tongSoLuong
ORDER BY maKhach;
~~~

Truy vấn này cho kết quả đúng như bảng dữ liệu mẫu ở mục 1, bao gồm C03 không có đơn và C04 không có ticket.

## 7. Khi thêm nhánh thứ ba, lỗi có thể tăng rất nhanh

Nếu nối đồng thời ba nhánh trong một luồng:

~~~cypher
MATCH (c:Customer)
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
OPTIONAL MATCH (o)-[line:HAS_LINE]->(:Product)
OPTIONAL MATCH (c)-[:OPENED]->(t:Ticket)
RETURN
  c.id AS maKhach,
  count(DISTINCT o) AS soDon,
  count(DISTINCT t) AS soTicket,
  sum(o.amount) AS tongTienSai,
  sum(line.quantity) AS tongSoLuongSai
ORDER BY maKhach;
~~~

Với C01:

- O101 có hai dòng sản phẩm, O102 có một → **3 dòng sản phẩm**.
- C01 có hai ticket → **mỗi dòng sản phẩm kết hợp với hai ticket**, tạo **6 dòng**.
- `sum(o.amount) = 600000` vì cả ba dòng sản phẩm đều mang amount 100000 và đều bị lặp theo ticket.
- `sum(line.quantity) = 12` thay vì **6** vì mỗi số lượng bị tính hai lần.
- `count(DISTINCT o) = 2` và `count(DISTINCT t) = 2` có thể trông đúng, làm lỗi của hai phép cộng khó phát hiện hơn.

Kết quả có vài cột đúng không có nghĩa toàn bộ truy vấn đúng. Khi kết hợp nhiều chỉ số, cần xem **mỗi phép tính** lấy giá trị từ cấp node/relationship nào và xuất hiện bao nhiêu lần trong tập dòng trung gian.

## 8. Lọc dữ liệu nguồn và tổng hợp có điều kiện

Nhiều báo cáo cần số đơn tổng cộng, số đơn PAID và doanh thu PAID cùng một lúc. Nếu đặt `WHERE o.status = 'PAID'` trước phép `count(o)`, chỉ số tổng số đơn sẽ bị mất những đơn chưa thanh toán. Thay vào đó, tính các chỉ số trên **cùng tập dòng đơn** bằng `CASE`:

~~~cypher
MATCH (c:Customer)
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
RETURN
  c.id AS maKhach,
  count(o) AS tongSoDon,
  count(CASE WHEN o.status = 'PAID' THEN o END) AS soDonPaid,
  sum(CASE WHEN o.status = 'PAID' THEN o.amount ELSE 0 END)
    AS tienPaid
ORDER BY maKhach;
~~~

| maKhach | tongSoDon | soDonPaid | tienPaid |
|---|---:|---:|---:|
| C01 | 2 | 1 | 100000 |
| C02 | 1 | 1 | 150000 |
| C03 | 0 | 0 | 0 |
| C04 | 1 | 1 | 80000 |

`count(CASE WHEN ... THEN o END)` đếm những dòng `CASE` trả về node khác `null`. `sum(CASE ... ELSE 0 END)` cộng số tiền cho đơn thỏa điều kiện và đóng góp 0 cho dòng không thỏa.

Nếu chỉ báo cáo đơn PAID, một `WHERE o.status = 'PAID'` trước khi tổng hợp có thể dễ đọc và làm giảm dòng. Nếu cần **nhiều chỉ số với điều kiện khác nhau**, phép tổng hợp `CASE` phù hợp, miễn là tập dòng không bị nhân do những nhánh khác.

Để lọc **khách có tổng tiền PAID lớn hơn 100000**, có thể dùng `WITH` rồi `WHERE`:

~~~cypher
MATCH (c:Customer)
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
WITH
  c,
  sum(CASE WHEN o.status = 'PAID' THEN o.amount ELSE 0 END)
    AS tienPaid
WHERE tienPaid > 100000
RETURN c.id AS maKhach, tienPaid
ORDER BY maKhach;
~~~

Chỉ C02 thỏa điều kiện `> 100000` với `tienPaid = 150000`. Điều kiện `WHERE` này áp dụng trên **nhóm sau tổng hợp**, khác với `WHERE` lọc từng đơn trước khi tính.

## 9. Cách tự kiểm chứng trước khi tin số liệu

Một bảng kết quả có 4 khách không cho biết truy vấn đã xử lý bao nhiêu dòng. Để tìm điểm nhân dòng, có thể tạm trả chi tiết các biến:

~~~cypher
MATCH (c:Customer {id: 'C01'})
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
OPTIONAL MATCH (c)-[:OPENED]->(t:Ticket)
RETURN
  c.id AS maKhach,
  o.id AS maDon,
  t.id AS maTicket,
  o.amount AS tienDon
ORDER BY maDon, maTicket;
~~~

Bảng này có **4 dòng** thay vì 2 dòng đơn hoặc 2 dòng ticket. Đó là dấu hiệu rõ ràng rằng tổng hợp trực tiếp trên dòng hiện tại sẽ nhân số liệu.

Có thể đo số dòng và số thực thể khác nhau trước khi quyết định cấu trúc:

~~~cypher
MATCH (c:Customer)
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
OPTIONAL MATCH (c)-[:OPENED]->(t:Ticket)
RETURN
  c.id AS maKhach,
  count(*) AS soDongTrungGian,
  count(DISTINCT o) AS soDonKhacNhau,
  count(DISTINCT t) AS soTicketKhacNhau
ORDER BY maKhach;
~~~

| maKhach | soDongTrungGian | soDonKhacNhau | soTicketKhacNhau |
|---|---:|---:|---:|
| C01 | 4 | 2 | 2 |
| C02 | 1 | 1 | 1 |
| C03 | 1 | 0 | 1 |
| C04 | 1 | 1 | 0 |

Khi `soDongTrungGian` lớn hơn số thực thể đơn hoặc ticket, cần đánh giá lại những hàm `sum()` và `avg()` đang chạy trên tập dòng này.

### 9.1. Các câu hỏi kiểm tra mức tính

1. **Một dòng báo cáo biểu diễn gì?** Một khách, một đơn, một sản phẩm hay một tổ hợp?
2. **Mỗi chỉ số thuộc đơn vị nào?** Tiền theo đơn, lượng hàng theo `HAS_LINE`, ticket theo node `Ticket`.
3. **Có bao nhiêu đường khớp mẫu cho một đơn vị đó?** Hai nhánh một–nhiều có thể nhân dòng.
4. **Có được phép loại trùng không?** `count(DISTINCT o)` dùng được khi muốn đếm node đơn riêng biệt; `sum(DISTINCT amount)` không bảo toàn đơn khác nhau có cùng giá trị.
5. **Nên tổng hợp ở đâu?** Dùng `WITH` theo đúng mức hoặc `CALL` tách nhánh trước khi ghép kết quả.

### 9.2. PROFILE giúp phát hiện nở số dòng

~~~cypher
PROFILE
MATCH (c:Customer)
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
OPTIONAL MATCH (c)-[:OPENED]->(t:Ticket)
RETURN c.id AS maKhach, sum(o.amount) AS tongTienSai;
~~~

Trong kế hoạch thực thi, quan sát **số dòng thực tế** qua các toán tử mở rộng relationship và tổng hợp. Nếu số dòng tăng mạnh trước phép tính, cần kiểm tra có nhân theo nhiều nhánh hay không. Với đồ thị lớn, `EXPLAIN` cho biết kế hoạch dự kiến mà không thực thi, còn `PROFILE` thực thi truy vấn để hiển thị số liệu đo được.

Chỉ mục và constraint có thể giúp xác định điểm bắt đầu (ví dụ tra cứu `Customer.id`), nhưng **không tự khắc phục tổng sai do nhân dòng**. Trước khi tinh chỉnh chỉ mục, cần đảm bảo cấu trúc phép tổng hợp chính xác.

## 10. Khi trả kết quả cho Java Driver và Spring Data Neo4j

Kết quả báo cáo thông thường nên **một record cho mỗi khóa nghiệp vụ** với các alias rõ nghĩa:

~~~cypher
MATCH (c:Customer)
CALL {
  WITH c
  OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
  RETURN count(o) AS orderCount, sum(o.amount) AS orderAmount
}
CALL {
  WITH c
  OPTIONAL MATCH (c)-[:OPENED]->(t:Ticket)
  RETURN count(t) AS ticketCount
}
RETURN
  c.id AS customerId,
  orderCount,
  orderAmount,
  ticketCount
ORDER BY customerId;
~~~

Java Driver có thể đọc các cột `customerId`, `orderCount`, `orderAmount`, `ticketCount` thành đối tượng thống kê/DTO. Với Spring Data Neo4j, có thể dùng projection thích hợp cho kết quả báo cáo thay vì ép chúng thành một node entity.

**Kiểu và ý nghĩa của cột cần được giữ nhất quán:** `orderCount = 0` nghĩa là không có đơn; `orderAmount = 0` nghĩa là tổng tiền trên tập rỗng bằng 0. Các giá trị `avg`, `min`, `max` trên tập không có dữ liệu có thể là `null`, nên phía Java cần xử lý nullable khi ánh xạ.

Khi xây API, tránh đếm lại theo số record của truy vấn có nhiều dòng chi tiết; báo cáo đúng phải được tính tại mức dữ liệu phù hợp ngay từ Cypher.

## 11. Bài tập và lời giải

### Bài 1. Phát hiện phép nhân dòng

Giải thích vì sao `count(o)`, `count(t)` và `sum(o.amount)` của An đều sai trong truy vấn sau:

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)
MATCH (c)-[:OPENED]->(t:Ticket)
RETURN c.id AS maKhach,
       count(o) AS soDon,
       count(t) AS soTicket,
       sum(o.amount) AS tongTien;
~~~

**Lời giải:** Với An, hai đơn kết hợp hai ticket tạo bốn dòng. Do đó `count(o) = 4`, `count(t) = 4`, `sum(o.amount) = 400000`; các giá trị đúng lần lượt là `2`, `2`, `200000`. Với các khách không có một trong hai nhánh, `MATCH` bắt buộc còn có thể loại họ hoàn toàn khỏi kết quả.

### Bài 2. Sửa truy vấn bằng WITH

Viết một truy vấn trả cả bốn khách cùng số đơn, tổng tiền và số ticket, không làm nhân số liệu.

**Lời giải:**

~~~cypher
MATCH (c:Customer)
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
WITH c, count(o) AS soDon, sum(o.amount) AS tongTien
OPTIONAL MATCH (c)-[:OPENED]->(t:Ticket)
RETURN
  c.id AS maKhach,
  soDon,
  tongTien,
  count(t) AS soTicket
ORDER BY maKhach;
~~~

Kết quả C01 = `(2, 200000, 2)`, C02 = `(1, 150000, 1)`, C03 = `(0, 0, 1)`, C04 = `(1, 80000, 0)`.

### Bài 3. Vì sao sum(DISTINCT) không đúng?

Hai đơn O101 và O102 của An đều có giá trị 100000. Tính `sum(DISTINCT o.amount)` sẽ cho bao nhiêu, và vì sao sai?

**Lời giải:** `sum(DISTINCT o.amount) = 100000`, vì có một **giá trị amount khác nhau** trong tập. Tuy nhiên, An có **hai đơn hàng khác nhau**, nên tổng tiền đúng là `100000 + 100000 = 200000`. Cần tổng hợp tại **mức đơn hàng**, không chỉ loại giá trị số trùng.

### Bài 4. Kết hợp ba nguồn bằng subquery

Trả một dòng cho mỗi khách với `soDon`, `soTicket`, `tongSoLuong` trong ba nhánh độc lập. Chi và Dung đều phải được giữ lại.

**Lời giải:**

~~~cypher
MATCH (c:Customer)
CALL {
  WITH c
  OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
  RETURN count(o) AS soDon
}
CALL {
  WITH c
  OPTIONAL MATCH (c)-[:OPENED]->(t:Ticket)
  RETURN count(t) AS soTicket
}
CALL {
  WITH c
  OPTIONAL MATCH (c)-[:PLACED]->(:Order)-[line:HAS_LINE]->(:Product)
  RETURN sum(line.quantity) AS tongSoLuong
}
RETURN c.id AS maKhach, soDon, soTicket, tongSoLuong
ORDER BY maKhach;
~~~

C01 `(2, 2, 6)`, C02 `(1, 1, 2)`, C03 `(0, 1, 0)`, C04 `(1, 0, 1)`.

## 12. Ghi nhớ

- Kết hợp nhiều `count()`, `sum()`, `avg()` trong một `RETURN` chỉ đúng khi **cùng tập dòng phù hợp với tất cả chỉ số**.
- Nhiều nhánh relationship một–nhiều có thể nhân số dòng. Với hai tập đều có phần tử, số tổ hợp có thể đạt `m × n`.
- `count(DISTINCT node)` có thể sửa số đếm thực thể; **`sum(DISTINCT amount)` không sửa được tổng tiền** khi các thực thể khác nhau cùng giá trị.
- Hãy tổng hợp từng tập quan hệ **trước khi nối sang nhánh khác** bằng `WITH`, hoặc tính độc lập trong các `CALL` subquery.
- Tổng tiền phải tính tại mức **Order**; số lượng sản phẩm tại mức **HAS_LINE**; số ticket tại mức **Ticket**.
- Dùng `OPTIONAL MATCH` và `count(biến)` để giữ nhóm không có quan hệ và phân biệt với `count(*)`.
- Kiểm tra số dòng trung gian, so sánh kết quả với dữ liệu mẫu, và dùng `PROFILE` trên đồ thị thực tế trước khi tin rằng báo cáo đã đúng và đủ hiệu quả.
