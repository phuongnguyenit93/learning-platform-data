# Kiểm chứng kết quả tổng hợp bằng bộ dữ liệu nhỏ có đáp án

## 1. Vì sao cần kiểm chứng phép tổng hợp?

Trong Neo4j, truy vấn Cypher tổng hợp dữ liệu bằng các hàm như `count()`, `sum()`, `avg()`, `min()`, `max()` và `collect()`. Kết quả phụ thuộc trực tiếp vào **số dòng được tạo ra sau khi khớp mẫu đồ thị**. Chỉ một quan hệ một-nhiều cũng có thể khiến số dòng tăng lên; `MATCH` có thể bỏ sót thực thể không có quan hệ, còn `OPTIONAL MATCH` có thể tạo dòng chứa `null`. Vì vậy, một kết quả có vẻ hợp lý vẫn có thể sai.

Cách kiểm chứng đáng tin cậy là dựng **bộ dữ liệu cố định, đủ nhỏ để tính đáp án bằng tay**, sau đó đối chiếu từng nhóm và các phép kiểm tra chéo bằng Cypher. Kỹ thuật này phù hợp khi xây dựng báo cáo trên *property graph*, kiểm thử câu truy vấn, kiểm tra dữ liệu nhập và xác nhận kết quả trả về qua Neo4j Java Driver hoặc Spring Data Neo4j.

Sau bài học, bạn có thể:

- Tạo một đồ thị thử nghiệm độc lập và tính các tổng hợp mong đợi trước khi chạy truy vấn.
- Phân biệt `count(*)`, `count(biến)` và `count(DISTINCT biến)` trên các mẫu quan hệ một-nhiều.
- Kiểm tra tổng hợp theo đơn hàng, khách hàng, sản phẩm và toàn bộ dữ liệu.
- Phát hiện lỗi do mất nhóm rỗng, nhân bản dòng, dùng `DISTINCT` sai chỗ hoặc dựa vào thứ tự kết quả không được bảo đảm.
- Viết truy vấn tự so sánh **kết quả thực tế** với **đáp án cố định** mà không cần APOC.

> **Phạm vi và đơn vị:** Các giá trị tiền trong bài đều tính bằng **nghìn đồng**. Ví dụ: `260` tương ứng 260.000 đồng. Đây là dữ liệu giả lập phục vụ kiểm chứng, không phải cơ sở dữ liệu nghiệp vụ thật.

## 2. Dựng đồ thị thử nghiệm có thể chạy lại

Mô hình sử dụng bốn loại node:

- `Customer` — khách hàng.
- `Order` — đơn hàng.
- `Line` — dòng hàng, lưu `qty` (số lượng) và `unitPrice` (đơn giá).
- `Product` — sản phẩm.

Ba kiểu quan hệ có hướng:

~~~text
(Customer)-[:PLACED]->(Order)-[:HAS_LINE]->(Line)-[:OF_PRODUCT]->(Product)
~~~

Tất cả node của bài có thêm nhãn `QA008` để truy vấn không lẫn với dữ liệu khác. Chỉ thực hiện lệnh xóa dữ liệu thử trong **database dùng để thực hành**.

**Bước 1 — Xóa bộ dữ liệu QA008 của lần chạy trước (nếu có):**

~~~cypher
MATCH (n:QA008)
DETACH DELETE n;
~~~

**Bước 2 — Tạo bộ dữ liệu chuẩn:**

~~~cypher
CREATE
  (c1:QA008:Customer {id: 'C01', name: 'An'}),
  (c2:QA008:Customer {id: 'C02', name: 'Bình'}),
  (c3:QA008:Customer {id: 'C03', name: 'Chi'}),
  (c4:QA008:Customer {id: 'C04', name: 'Dũng'}),

  (o1:QA008:Order {id: 'O01'}),
  (o2:QA008:Order {id: 'O02'}),
  (o3:QA008:Order {id: 'O03'}),
  (o4:QA008:Order {id: 'O04'}),

  (l1:QA008:Line {id: 'L01', qty: 2, unitPrice: 100}),
  (l2:QA008:Line {id: 'L02', qty: 3, unitPrice: 20}),
  (l3:QA008:Line {id: 'L03', qty: 1, unitPrice: 100}),
  (l4:QA008:Line {id: 'L04', qty: 5, unitPrice: 20}),
  (l5:QA008:Line {id: 'L05', qty: 2, unitPrice: 50}),

  (p1:QA008:Product {id: 'P01', name: 'Sách'}),
  (p2:QA008:Product {id: 'P02', name: 'Bút'}),
  (p3:QA008:Product {id: 'P03', name: 'Vở'})

WITH c1, c2, c3, o1, o2, o3, o4,
     l1, l2, l3, l4, l5, p1, p2, p3
CREATE
  (c1)-[:PLACED]->(o1),
  (c1)-[:PLACED]->(o2),
  (c2)-[:PLACED]->(o3),
  (c3)-[:PLACED]->(o4),

  (o1)-[:HAS_LINE]->(l1),
  (o1)-[:HAS_LINE]->(l2),
  (o2)-[:HAS_LINE]->(l3),
  (o3)-[:HAS_LINE]->(l4),
  (o3)-[:HAS_LINE]->(l5),

  (l1)-[:OF_PRODUCT]->(p1),
  (l2)-[:OF_PRODUCT]->(p2),
  (l3)-[:OF_PRODUCT]->(p1),
  (l4)-[:OF_PRODUCT]->(p2),
  (l5)-[:OF_PRODUCT]->(p3);
~~~

Lưu ý có **đơn hàng O04 không có dòng hàng** và **khách hàng C04 không có đơn hàng**. Hai trường hợp này là chủ ý để kiểm tra cách xử lý nhóm rỗng.

**Bước 3 — Kiểm tra dữ liệu nền:**

~~~cypher
MATCH (n:QA008)
RETURN count(n) AS soNode;
~~~

Kết quả phải là **16 node**: 4 khách hàng + 4 đơn hàng + 5 dòng hàng + 3 sản phẩm.

~~~cypher
MATCH (a:QA008)-[r]->(b:QA008)
RETURN count(r) AS soQuanHe;
~~~

Kết quả phải là **14 quan hệ**: 4 `PLACED` + 5 `HAS_LINE` + 5 `OF_PRODUCT`. Nếu hai số này sai, cần sửa lại dữ liệu mẫu trước khi đánh giá các truy vấn tổng hợp.

## 3. Lập bảng đáp án độc lập với Cypher

Trước khi viết `sum()`, tính giá trị từng dòng hàng theo công thức:

\[
\text{Thành tiền dòng}=\text{qty}\times\text{unitPrice}
\]

| Dòng hàng | Đơn hàng | Sản phẩm | Số lượng | Đơn giá | Thành tiền |
|---|---|---|---:|---:|---:|
| L01 | O01 | P01 — Sách | 2 | 100 | 200 |
| L02 | O01 | P02 — Bút | 3 | 20 | 60 |
| L03 | O02 | P01 — Sách | 1 | 100 | 100 |
| L04 | O03 | P02 — Bút | 5 | 20 | 100 |
| L05 | O03 | P03 — Vở | 2 | 50 | 100 |
| **Tổng** | | | **13** | | **560** |

Từ bảng trên, ta xác định được các đáp án cần đối chiếu:

**Theo đơn hàng:**

| Đơn hàng | Số dòng hàng | Tổng tiền |
|---|---:|---:|
| O01 | 2 | 260 |
| O02 | 1 | 100 |
| O03 | 2 | 200 |
| O04 | 0 | 0 |

**Theo khách hàng:**

| Mã KH | Khách hàng | Số đơn | Số dòng hàng | Tổng tiền |
|---|---|---:|---:|---:|
| C01 | An | 2 | 3 | 360 |
| C02 | Bình | 1 | 2 | 200 |
| C03 | Chi | 1 | 0 | 0 |
| C04 | Dũng | 0 | 0 | 0 |

**Theo sản phẩm:**

| Mã SP | Sản phẩm | Số dòng hàng | Tổng số lượng | Tổng tiền |
|---|---|---:|---:|---:|
| P01 | Sách | 2 | 3 | 300 |
| P02 | Bút | 2 | 8 | 160 |
| P03 | Vở | 1 | 2 | 100 |

Các bất biến đối chiếu quan trọng:

- Tổng tiền từ các dòng hàng: **560**.
- Tổng tiền theo đơn hàng: `260 + 100 + 200 + 0 = 560`.
- Tổng tiền theo khách hàng: `360 + 200 + 0 + 0 = 560`.
- Tổng tiền theo sản phẩm: `300 + 160 + 100 = 560`.
- Tổng số lượng sản phẩm đã bán: **13**.
- Tổng số dòng hàng: **5**; số đơn có ít nhất một dòng hàng: **3**; tổng số đơn: **4**.

Khi các cách tính độc lập cho kết quả khác nhau, phải xem lại chiều quan hệ, điều kiện lọc và số dòng hình thành trước phép tổng hợp.

## 4. Kiểm chứng tổng hợp toàn đồ thị

Đối với tổng hợp ở cấp **dòng hàng**, không cần đi qua đơn hàng hoặc khách hàng nếu tất cả thông tin cần thiết đã có trên `Line`. Đường đi ngắn hơn giảm nguy cơ tạo bản sao dòng không cần thiết.

~~~cypher
MATCH (l:QA008:Line)
RETURN
  count(l) AS soDong,
  sum(l.qty) AS tongSoLuong,
  sum(l.qty * l.unitPrice) AS tongTien,
  min(l.qty * l.unitPrice) AS dongNhoNhat,
  max(l.qty * l.unitPrice) AS dongLonNhat,
  avg(l.qty * l.unitPrice) AS trungBinhMoiDong;
~~~

| soDong | tongSoLuong | tongTien | dongNhoNhat | dongLonNhat | trungBinhMoiDong |
|---:|---:|---:|---:|---:|---:|
| 5 | 13 | 560 | 60 | 200 | 112.0 |

Giải thích: năm thành tiền dòng là `[200, 60, 100, 100, 100]`. Do đó trung bình trên **mỗi dòng hàng** bằng `560 / 5 = 112.0`, không phải giá trung bình của một đơn vị sản phẩm. Nếu cần giá bán bình quân theo **đơn vị**, phải tính `sum(l.qty * l.unitPrice) / sum(l.qty)` và diễn đạt rõ ý nghĩa; với bộ dữ liệu này đó là `560 / 13`, xấp xỉ **43,08 nghìn đồng/đơn vị**.

Kiểm tra số mức đơn giá khác nhau:

~~~cypher
MATCH (l:QA008:Line)
WITH DISTINCT l.unitPrice AS donGia
ORDER BY donGia
RETURN collect(donGia) AS cacDonGia;
~~~

Đáp án chính xác là **`[20, 50, 100]`**. Ở đây `DISTINCT` áp dụng cho *đơn giá*, sau đó `ORDER BY` bảo đảm thứ tự khi đưa vào `collect()`.

## 5. Kiểm chứng nhóm theo đơn hàng, kể cả đơn trống

~~~cypher
MATCH (o:QA008:Order)
OPTIONAL MATCH (o)-[:HAS_LINE]->(l:QA008:Line)
RETURN
  o.id AS donHang,
  count(l) AS soDong,
  coalesce(sum(l.qty * l.unitPrice), 0) AS tongTien
ORDER BY donHang;
~~~

| donHang | soDong | tongTien |
|---|---:|---:|
| O01 | 2 | 260 |
| O02 | 1 | 100 |
| O03 | 2 | 200 |
| O04 | 0 | 0 |

`OPTIONAL MATCH` giữ lại O04, dù không có quan hệ `HAS_LINE`. Với nhóm đó, biến `l` là `null`: `count(l)` trả về 0, còn `coalesce(..., 0)` thể hiện yêu cầu nghiệp vụ rằng tổng tiền đơn hàng rỗng là 0. Đây là cách viết dễ đọc và ổn định khi bổ sung các phép tổng hợp khác có thể trả về `null`.

Nếu đổi thành `MATCH (o)-[:HAS_LINE]->(l)`, **O04 biến mất khỏi kết quả**. Khi báo cáo cần xuất mọi đơn hàng, đây là lỗi thiếu nhóm, dù tổng tiền của ba đơn còn lại vẫn đúng.

## 6. Kiểm chứng nhóm theo khách hàng và tính bội số hàng

Từ khách hàng đến dòng hàng có thể có hai tầng một-nhiều: một khách đặt nhiều đơn, mỗi đơn có nhiều dòng. Đếm số dòng của kết quả khớp mẫu **không tương đương** với đếm số đơn duy nhất.

~~~cypher
MATCH (c:QA008:Customer)
OPTIONAL MATCH (c)-[:PLACED]->(o:QA008:Order)
OPTIONAL MATCH (o)-[:HAS_LINE]->(l:QA008:Line)
RETURN
  c.id AS khachHang,
  c.name AS ten,
  count(*) AS soDongKhongGianKetQua,
  count(o) AS soLanXuatHienDon,
  count(DISTINCT o) AS soDonThucTe,
  count(l) AS soDongHang,
  coalesce(sum(l.qty * l.unitPrice), 0) AS tongTien
ORDER BY khachHang;
~~~

| khachHang | ten | soDongKhongGianKetQua | soLanXuatHienDon | soDonThucTe | soDongHang | tongTien |
|---|---|---:|---:|---:|---:|---:|
| C01 | An | 3 | 3 | 2 | 3 | 360 |
| C02 | Bình | 2 | 2 | 1 | 2 | 200 |
| C03 | Chi | 1 | 1 | 1 | 0 | 0 |
| C04 | Dũng | 1 | 0 | 0 | 0 | 0 |

Điểm cần nhớ:

1. `count(*)` đếm **dòng kết quả**, kể cả dòng được `OPTIONAL MATCH` giữ lại khi các biến quan hệ là `null`. Vì vậy C03 và C04 vẫn có giá trị 1.
2. `count(o)` đếm các giá trị `o` khác `null`. Đơn O01 xuất hiện hai lần vì có hai dòng hàng, làm số lần xuất hiện của đơn ở C01 tăng thành 3.
3. `count(DISTINCT o)` đếm **đơn khác nhau**, đúng với yêu cầu "số đơn hàng thực tế": C01 có 2 đơn, C02 có 1, C03 có 1, C04 có 0.
4. `count(l)` đếm dòng hàng; đơn rỗng và khách không có đơn đều nhận 0.
5. Với mô hình mẫu, mỗi dòng hàng thuộc đúng một đơn, nên `sum(l.qty * l.unitPrice)` trên các dòng liên kết cho đáp án 360, 200, 0, 0.

**Hai lỗi dễ nhầm:**

~~~cypher
// SAI khi muốn đếm số đơn: đếm mỗi lần đơn xuất hiện sau khi nối với dòng.
MATCH (c:QA008:Customer)
OPTIONAL MATCH (c)-[:PLACED]->(o:QA008:Order)
OPTIONAL MATCH (o)-[:HAS_LINE]->(l:QA008:Line)
RETURN c.id AS khachHang, count(o) AS soDonSai
ORDER BY khachHang;
~~~

Truy vấn trên trả về `3, 2, 1, 0` theo C01–C04, thay vì `2, 1, 1, 0`.

~~~cypher
// SAI khi muốn giữ đơn rỗng: OPTIONAL MATCH gộp hai chặng thành một mẫu.
MATCH (c:QA008:Customer)
OPTIONAL MATCH (c)-[:PLACED]->(o:QA008:Order)-[:HAS_LINE]->(l:QA008:Line)
RETURN c.id AS khachHang, count(DISTINCT o) AS soDonSai
ORDER BY khachHang;
~~~

Mẫu gộp yêu cầu **cả hai chặng cùng tồn tại**. O04 không có dòng hàng nên không khớp toàn bộ mẫu; C03 bị tính 0 đơn. Vì vậy, hãy dùng **hai mệnh đề `OPTIONAL MATCH` riêng biệt** khi cần giữ cả khách không có đơn lẫn đơn chưa có dòng hàng.

## 7. Kiểm chứng nhóm theo sản phẩm

~~~cypher
MATCH (l:QA008:Line)-[:OF_PRODUCT]->(p:QA008:Product)
RETURN
  p.id AS sanPham,
  p.name AS ten,
  count(l) AS soDongHang,
  sum(l.qty) AS soLuong,
  sum(l.qty * l.unitPrice) AS tongTien
ORDER BY sanPham;
~~~

| sanPham | ten | soDongHang | soLuong | tongTien |
|---|---|---:|---:|---:|
| P01 | Sách | 2 | 3 | 300 |
| P02 | Bút | 2 | 8 | 160 |
| P03 | Vở | 1 | 2 | 100 |

Truy vấn sử dụng `p.id` và `p.name` làm khóa nhóm trong `RETURN`; khi đưa các biểu thức không tổng hợp vào cùng `RETURN` với hàm tổng hợp, Cypher nhóm theo các biểu thức đó. Dùng mã định danh ổn định giúp tránh gộp nhầm hai sản phẩm trùng tên.

Nếu muốn liệt kê **cả sản phẩm chưa từng bán**, hãy bắt đầu từ `Product` rồi `OPTIONAL MATCH` sang `Line`; khi đó đặt mục tiêu rõ ràng cho tổng bằng 0. Bộ dữ liệu hiện tại chưa có sản phẩm tồn kho nhưng không bán, vì vậy truy vấn `MATCH` ở trên đủ để đối chiếu cả ba sản phẩm trong mẫu.

## 8. Vì sao không được dùng DISTINCT bừa bãi trong SUM?

`DISTINCT` có ích khi đếm đơn bị lặp sau khi mở rộng quan hệ, nhưng có thể làm mất số liệu hợp lệ nếu áp dụng trực tiếp vào **giá trị tiền**.

~~~cypher
MATCH (l:QA008:Line)
RETURN
  sum(l.qty * l.unitPrice) AS tongDung,
  sum(DISTINCT l.qty * l.unitPrice) AS tongSai;
~~~

| tongDung | tongSai |
|---:|---:|
| 560 | 360 |

Vì thành tiền ở L03, L04 và L05 đều là 100, `sum(DISTINCT ...)` chỉ giữ **một** giá trị 100. Phép tính sai trở thành `200 + 60 + 100 = 360`. Ba dòng hàng là ba giao dịch hợp lệ, dù có cùng thành tiền.

Quy tắc thực hành: xác định **thực thể hoặc dòng nghiệp vụ cần đếm/tổng hợp** trước; khi cần xử lý việc một đơn xuất hiện nhiều lần, sử dụng `count(DISTINCT o)` cho số đơn. Đừng thay mọi `sum()` bằng `sum(DISTINCT ...)` để che lỗi nhân bản dữ liệu từ một mẫu khớp quá rộng.

Nếu truy vấn đã nối thêm quan hệ khiến một dòng hàng xuất hiện nhiều lần, nên thu gọn về **mỗi dòng hàng một bản ghi** bằng `WITH DISTINCT l` hoặc nhóm theo `l.id` trước khi tính tổng, đồng thời kiểm tra xem các giá trị đầu vào có thực sự duy nhất theo định danh đó hay không.

## 9. Viết phép kiểm thử tự động so với đáp án

Thay vì đọc bảng bằng mắt, ta có thể đặt đáp án cố định trong danh sách map, sau đó dùng `UNWIND` để tạo mỗi trường hợp kiểm thử. Truy vấn sau so sánh đủ bốn khách hàng và trả về cột `passed`:

~~~cypher
WITH [
  {id: 'C01', orders: 2, lines: 3, revenue: 360},
  {id: 'C02', orders: 1, lines: 2, revenue: 200},
  {id: 'C03', orders: 1, lines: 0, revenue: 0},
  {id: 'C04', orders: 0, lines: 0, revenue: 0}
] AS expected
UNWIND expected AS e
OPTIONAL MATCH (c:QA008:Customer {id: e.id})
OPTIONAL MATCH (c)-[:PLACED]->(o:QA008:Order)
OPTIONAL MATCH (o)-[:HAS_LINE]->(l:QA008:Line)
WITH e,
     count(DISTINCT c) AS customers,
     count(DISTINCT o) AS orders,
     count(l) AS lines,
     coalesce(sum(l.qty * l.unitPrice), 0) AS revenue
RETURN
  e.id AS customerId,
  customers,
  orders,
  lines,
  revenue,
  customers = 1
    AND orders = e.orders
    AND lines = e.lines
    AND revenue = e.revenue AS passed
ORDER BY customerId;
~~~

Đáp án: **4 hàng, cả 4 giá trị `passed` đều là `true`**.

Tại sao dùng `OPTIONAL MATCH` ngay cả ở lần tìm khách hàng đầu tiên? Vì nếu dùng `MATCH` và một khách hàng mong đợi bị xóa khỏi dữ liệu, dòng kiểm thử đó có thể **biến mất**, tạo cảm giác tất cả những dòng còn lại đều đạt. Với `OPTIONAL MATCH`, dòng mong đợi được giữ lại; `customers = 0` làm kiểm thử thất bại. Việc đếm `DISTINCT c` cũng phát hiện trường hợp có nhiều node cùng mã khách hàng.

Để đối chiếu tổng tiền theo hai đường tính độc lập, chạy thêm:

~~~cypher
MATCH (o:QA008:Order)
OPTIONAL MATCH (o)-[:HAS_LINE]->(l:QA008:Line)
WITH o, coalesce(sum(l.qty * l.unitPrice), 0) AS orderTotal
WITH sum(orderTotal) AS totalByOrders
OPTIONAL MATCH (line:QA008:Line)
WITH totalByOrders,
     coalesce(sum(line.qty * line.unitPrice), 0) AS totalByLines
RETURN
  totalByOrders,
  totalByLines,
  totalByOrders = totalByLines
    AND totalByLines = 560 AS passed;
~~~

Kết quả phải là `totalByOrders = 560`, `totalByLines = 560`, `passed = true`. Phép kiểm tra chéo giúp tìm những lỗi làm mất hoặc nhân bản dòng trong phần nối từ đơn hàng; tuy nhiên hai tổng bằng nhau **chưa đủ** bảo đảm mọi nhóm đều đúng, nên vẫn cần các phép kiểm tra theo C01–C04, O01–O04 và P01–P03.

Có thể dùng cùng kiểu kiểm thử trong Java Driver hoặc Spring Data Neo4j: truy vấn trả về danh sách record, ứng dụng so sánh theo **mã định danh** và xác nhận đầy đủ số nhóm, các giá trị số, cột `passed`. Khi viết kiểm thử tích hợp, tạo lại fixture trong một database thử nghiệm riêng và không dựa vào thứ tự dòng nếu truy vấn thiếu `ORDER BY`.

## 10. Checklist tìm lỗi khi kết quả không khớp

| Triệu chứng | Nguyên nhân cần kiểm tra | Cách xác minh/sửa |
|---|---|---|
| Thiếu C04 hoặc O04 | `MATCH` làm rơi thực thể không có quan hệ | Bắt đầu từ thực thể cần báo cáo, thêm `OPTIONAL MATCH` cho nhánh có thể rỗng |
| Đếm đơn của C01 là 3 | Một đơn xuất hiện nhiều lần theo số dòng hàng | Xem số dòng trước tổng hợp; dùng `count(DISTINCT o)` |
| C03 bị đếm thành 0 đơn | Gộp hai chặng trong cùng một `OPTIONAL MATCH` | Tách chặng khách–đơn và đơn–dòng |
| Tổng tiền là 360 thay vì 560 | Dùng `sum(DISTINCT thànhTiền)` | Giữ từng dòng hàng hợp lệ; phân biệt trùng thực thể với trùng giá trị |
| Nhóm có 0 dòng nhưng `count(*) = 1` | Dòng có biến `null` được giữ lại bởi `OPTIONAL MATCH` | Dùng `count(l)` khi cần số dòng hàng có thật |
| Một nhóm biến mất sau lọc | `WHERE` loại các dòng hoặc được đặt tại chặng không phù hợp | Xem lại vị trí điều kiện trước/sau `OPTIONAL MATCH` |
| Mảng `collect()` thay đổi thứ tự | Không có bảo đảm về thứ tự đầu vào | Dùng `WITH ... ORDER BY` trước `collect()` |
| Tất cả kiểm tra còn lại đều đạt khi thiếu một nhóm | Kiểm thử dùng `MATCH` làm rơi luôn dòng đáp án | Dùng `UNWIND` đáp án + `OPTIONAL MATCH` và so đủ số nhóm |

Nếu kết quả vẫn sai, gỡ truy vấn theo từng đoạn: kiểm tra số dòng sau mỗi `MATCH` hoặc `OPTIONAL MATCH` bằng một `RETURN` tạm thời, xác nhận các cặp node/quan hệ có đúng định danh, rồi mới đưa `sum()` hay `count()` trở lại. `PROFILE` có thể cho biết số dòng thực tế qua từng toán tử; trên bộ dữ liệu 16 node này, mục tiêu là **hiểu cardinality và tính đúng đắn**, chưa phải đo hiệu năng cho hệ thống lớn.

## 11. Bài tập tự kiểm chứng

**Bài 1.** Viết truy vấn tính `count(DISTINCT o)` trên những đơn **có ít nhất một dòng hàng**. Đáp án: **3** (O01, O02, O03). So sánh với tổng số đơn là **4**.

**Bài 2.** Viết truy vấn lấy `collect(l.id)` theo thứ tự tăng của mã dòng hàng. Đáp án: `['L01', 'L02', 'L03', 'L04', 'L05']`.

Gợi ý cho bài 2:

~~~cypher
MATCH (l:QA008:Line)
WITH l ORDER BY l.id
RETURN collect(l.id) AS ids;
~~~

**Bài 3.** Giả sử thêm một quan hệ thứ hai từ L01 đến cùng sản phẩm P01 trong dữ liệu lỗi. Phép nối `Line` → `Product` sẽ làm L01 xuất hiện hai lần; tổng nhóm P01 bị thổi từ **300** lên **500** nếu dùng ngay `sum(l.qty * l.unitPrice)`. Hãy kiểm tra lại số quan hệ `OF_PRODUCT`, phát hiện dòng bị lặp theo `l.id` và bảo vệ quy tắc **mỗi dòng hàng thuộc đúng một sản phẩm** bằng bước kiểm tra dữ liệu phù hợp.

Bài 3 chỉ là tình huống giả định; không cần sửa fixture chuẩn để hoàn thành hai bài đầu. Nếu chủ động thêm quan hệ để thử lỗi, hãy xóa và dựng lại fixture từ mục 2 trước khi chạy bộ kiểm chứng chính.

## 12. Dọn dữ liệu thử nghiệm

Sau khi thực hành, có thể xóa toàn bộ 16 node của fixture cùng các quan hệ gắn với chúng:

~~~cypher
MATCH (n:QA008)
DETACH DELETE n;
~~~

Chỉ dùng lệnh này trong database thực hành. Khi xây dựng bài kiểm thử lặp lại, hãy tạo fixture mới trước mỗi lần chạy, so sánh kết quả theo mã định danh và giữ **bảng đáp án độc lập** với câu truy vấn đang được kiểm thử. Chính bộ đáp án nhỏ, xác định được bằng tay, là cơ sở để tin cậy các phép tổng hợp trên đồ thị lớn hơn.
