# Lọc trước tổng hợp và lọc sau tổng hợp bằng WITH

Trong Neo4j, một câu truy vấn Cypher có thể phải trả lời hai câu hỏi rất khác nhau:

- **Những đơn hàng nào được đưa vào phép tính?** Ví dụ: chỉ tính những đơn đã thanh toán.
- **Những nhóm nào được giữ lại sau khi tính?** Ví dụ: chỉ hiển thị khách hàng có ít nhất hai đơn đã thanh toán.

Câu hỏi thứ nhất cần **lọc dòng trước tổng hợp**, còn câu hỏi thứ hai cần **lọc nhóm sau tổng hợp**. Trong chương **Tổng hợp dữ liệu**, `WHERE` và `WITH` giúp đặt các điều kiện đúng thời điểm, đồng thời giữ cho mức tổng hợp (*aggregation grain*) của truy vấn đồ thị rõ ràng.

Đây là kỹ năng quan trọng khi thống kê dữ liệu liên kết bằng Neo4j: mỗi `MATCH` sinh các dòng từ những mẫu node–relationship phù hợp; `WITH` có thể gộp các dòng đó thành nhóm; `WHERE` trước và sau `WITH` có thể cho kết quả hoàn toàn khác nhau dù dùng cùng một điều kiện nghiệp vụ.

## 1. Dữ liệu mẫu

Xét property graph của hệ thống quản lý đơn hàng:

~~~text
(:Customer {id, name})-[:PLACED]->(:Order {id, amount, status})
~~~

`Customer` là khách hàng, `Order` là đơn hàng; `PLACED` thể hiện khách tạo đơn. Thuộc tính `amount` là giá trị đơn hàng tính bằng VND, `status` biểu thị trạng thái.

Tạo dữ liệu sau trên **cơ sở dữ liệu thực hành trống**. Chỉ chạy lệnh `CREATE` một lần để tránh tạo bản ghi trùng:

~~~cypher
CREATE
  (an:Customer {id: 'C01', name: 'An'}),
  (binh:Customer {id: 'C02', name: 'Binh'}),
  (chi:Customer {id: 'C03', name: 'Chi'}),
  (dung:Customer {id: 'C04', name: 'Dung'}),
  (o101:Order {id: 'O101', amount: 100000, status: 'PAID'}),
  (o102:Order {id: 'O102', amount: 150000, status: 'PAID'}),
  (o103:Order {id: 'O103', amount: 90000, status: 'PENDING'}),
  (o104:Order {id: 'O104', amount: 200000, status: 'PAID'}),
  (o105:Order {id: 'O105', amount: 70000, status: 'CANCELLED'}),
  (o106:Order {id: 'O106', amount: 50000, status: 'PAID'}),
  (an)-[:PLACED]->(o101),
  (an)-[:PLACED]->(o102),
  (an)-[:PLACED]->(o103),
  (binh)-[:PLACED]->(o104),
  (binh)-[:PLACED]->(o105),
  (dung)-[:PLACED]->(o106);
~~~

Bảng đối chiếu nghiệp vụ:

| Khách | Đơn hàng | Tất cả đơn | Đơn PAID | Tổng tiền PAID |
|---|---|---:|---:|---:|
| C01 / An | O101, O102, O103 | 3 | 2 | 250000 |
| C02 / Binh | O104, O105 | 2 | 1 | 200000 |
| C03 / Chi | Không có | 0 | 0 | 0 |
| C04 / Dung | O106 | 1 | 1 | 50000 |

Có tổng cộng **6 đơn**, trong đó **4 đơn PAID** với tổng giá trị **500000 VND**. Các giá trị này sẽ được dùng để kiểm chứng truy vấn.

## 2. Hai thời điểm lọc khác nhau

Hãy tưởng tượng một truy vấn dưới dạng luồng dữ liệu:

~~~text
MATCH                  → tạo các dòng từ mẫu đồ thị
WHERE trước WITH       → loại dòng không thỏa điều kiện
WITH ... count/sum     → nhóm và tính chỉ số cho từng nhóm
WHERE sau WITH         → loại các nhóm không thỏa chỉ số
RETURN                 → trình bày kết quả
~~~

Ví dụ yêu cầu: **“Liệt kê khách hàng có ít nhất hai đơn đã thanh toán, kèm số đơn và tổng tiền đã thanh toán.”**

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)
WHERE o.status = 'PAID'
WITH
  c,
  count(o) AS soDonDaThanhToan,
  sum(o.amount) AS tongDaThanhToan
WHERE soDonDaThanhToan >= 2
RETURN
  c.id AS maKhach,
  c.name AS ten,
  soDonDaThanhToan,
  tongDaThanhToan
ORDER BY maKhach;
~~~

Kết quả:

| maKhach | ten | soDonDaThanhToan | tongDaThanhToan |
|---|---|---:|---:|
| C01 | An | 2 | 250000 |

Giải thích theo từng giai đoạn:

1. `MATCH` tìm được sáu dòng đơn hàng.
2. `WHERE o.status = 'PAID'` giữ bốn dòng đơn đã thanh toán.
3. `WITH c, count(o), sum(o.amount)` tạo ba nhóm khách C01, C02, C04; khóa nhóm ngầm định là node `c`.
4. `WHERE soDonDaThanhToan >= 2` chỉ giữ nhóm C01.
5. `RETURN` xuất một dòng kết quả cho An.

Điểm mấu chốt: **lọc trước quyết định dữ liệu nào tham gia phép tính; lọc sau quyết định kết quả tổng hợp nào được hiển thị**.

## 3. Lọc trước tổng hợp: WHERE trên dòng nguồn

`WHERE` đặt sau `MATCH` thường kiểm tra property, nhãn, giá trị hoặc điều kiện liên quan đến **từng dòng đang khớp mẫu**:

~~~cypher
MATCH (o:Order)
WHERE o.status = 'PAID'
RETURN
  count(o) AS soDon,
  sum(o.amount) AS tongTien,
  avg(o.amount) AS giaTriTrungBinh;
~~~

Kết quả: `soDon = 4`, `tongTien = 500000`, `giaTriTrungBinh = 125000.0`.

Trong truy vấn này, các đơn `PENDING` và `CANCELLED` bị loại trước `RETURN`, nên không đóng góp vào tổng hoặc trung bình. Nếu bỏ `WHERE`, tổng giá trị cả sáu đơn sẽ là `660000`, không còn là tổng tiền đã thanh toán.

### 3.1. Lọc theo nhiều điều kiện

Ví dụ chỉ tính đơn đã thanh toán và có giá trị ít nhất 100000 VND:

~~~cypher
MATCH (o:Order)
WHERE o.status = 'PAID' AND o.amount >= 100000
RETURN count(o) AS soDon, sum(o.amount) AS tongTien;
~~~

Kết quả: `soDon = 3`, `tongTien = 450000` (O101, O102, O104). O106 dù đã thanh toán vẫn bị loại vì chỉ có giá trị 50000.

### 3.2. Lọc thực thể gốc trước khi duyệt quan hệ

Nếu báo cáo chỉ dành cho một khách, có thể xác định khách trước rồi mới duyệt đơn:

~~~cypher
MATCH (c:Customer)
WHERE c.id = 'C01'
MATCH (c)-[:PLACED]->(o:Order)
WHERE o.status = 'PAID'
RETURN c.name AS ten, count(o) AS soDon, sum(o.amount) AS tongTien;
~~~

Kết quả: An, 2 đơn PAID, tổng 250000 VND.

Đặt điều kiện có tính chọn lọc sớm thường giúp giảm khối lượng dữ liệu phải duyệt. Trong môi trường thực tế, nên đánh giá chỉ mục cho `Customer.id` hoặc các property dùng lọc thường xuyên; khả năng sử dụng index còn phụ thuộc vào kế hoạch thực thi của Neo4j.

## 4. Lọc sau tổng hợp: WITH ... WHERE

Cypher không sử dụng mệnh đề `HAVING` theo kiểu SQL để lọc kết quả nhóm. Thay vào đó, một cách phổ biến là **tổng hợp trong `WITH`**, đặt alias cho chỉ số, rồi **lọc bằng `WHERE` sau `WITH`**.

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)
WITH c, count(o) AS soDon
WHERE soDon >= 2
RETURN c.id AS maKhach, c.name AS ten, soDon
ORDER BY maKhach;
~~~

Kết quả:

| maKhach | ten | soDon |
|---|---|---:|
| C01 | An | 3 |
| C02 | Binh | 2 |

`WHERE soDon >= 2` lọc **khách hàng theo chỉ số đã tính**, không lọc từng đơn. Nó chỉ có ý nghĩa khi `soDon` đã tồn tại sau phép tổng hợp.

### 4.1. Vì sao không đặt count() trực tiếp ở WHERE của MATCH?

Ví dụ dưới đây không đúng cú pháp/ngữ nghĩa tổng hợp của Cypher:

~~~cypher
// SAI: không dùng count() làm điều kiện trực tiếp tại WHERE sau MATCH
MATCH (c:Customer)-[:PLACED]->(o:Order)
WHERE count(o) >= 2
RETURN c.id;
~~~

Ở thời điểm `WHERE` gắn với `MATCH`, Cypher đang xử lý các dòng phù hợp, chưa có nhóm để tính `count(o)`. Hãy tạo nhóm bằng `WITH` rồi lọc alias:

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)
WITH c, count(o) AS soDon
WHERE soDon >= 2
RETURN c.id AS maKhach, soDon;
~~~

Cần phân biệt rõ: `WHERE` sau `MATCH` lọc **dòng nguồn**; `WHERE` ngay sau `WITH` đã tổng hợp lọc **dòng kết quả nhóm**.

### 4.2. Lọc theo tổng tiền, trung bình hoặc nhiều chỉ số

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)
WHERE o.status = 'PAID'
WITH
  c,
  count(o) AS soDonPaid,
  sum(o.amount) AS tongTienPaid,
  avg(o.amount) AS trungBinhPaid
WHERE soDonPaid >= 1 AND tongTienPaid >= 100000
RETURN
  c.id AS maKhach,
  soDonPaid,
  tongTienPaid,
  trungBinhPaid
ORDER BY maKhach;
~~~

Kết quả có C01 (2 đơn, 250000, trung bình 125000) và C02 (1 đơn, 200000, trung bình 200000). C04 bị loại vì tổng tiền đã thanh toán là 50000.

Có thể dùng các toán tử logic `AND`, `OR` để đặt nhiều điều kiện lên **các chỉ số đã tổng hợp** giống như trên.

## 5. So sánh cùng ngưỡng nhưng đặt WHERE khác vị trí

Xem hai câu hỏi:

**Câu A:** “Những khách nào có ít nhất hai **đơn PAID**?”

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)
WHERE o.status = 'PAID'
WITH c, count(o) AS soDon
WHERE soDon >= 2
RETURN c.id AS maKhach, soDon;
~~~

Chỉ C01 có `soDon = 2`.

**Câu B:** “Những khách nào có ít nhất hai **đơn bất kỳ**?”

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)
WITH c, count(o) AS soDon
WHERE soDon >= 2
RETURN c.id AS maKhach, soDon
ORDER BY maKhach;
~~~

C01 có 3 đơn; C02 có 2 đơn. Truy vấn B không ràng buộc trạng thái đơn hàng.

Nếu yêu cầu là “khách có từ hai đơn bất kỳ, nhưng chỉ hiển thị số đơn PAID của họ”, hai bước cần được tách:

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)
WITH c, count(o) AS tongSoDon
WHERE tongSoDon >= 2
OPTIONAL MATCH (c)-[:PLACED]->(paid:Order)
WHERE paid.status = 'PAID'
RETURN
  c.id AS maKhach,
  tongSoDon,
  count(paid) AS soDonPaid
ORDER BY maKhach;
~~~

| maKhach | tongSoDon | soDonPaid |
|---|---:|---:|
| C01 | 3 | 2 |
| C02 | 2 | 1 |

`WITH` đầu tiên xác định tập khách đạt điều kiện theo **tổng số đơn**. `OPTIONAL MATCH` phía sau mới đếm đơn PAID cho những khách đó. Không nên dịch chuyển `WHERE o.status = 'PAID'` lên trước `WITH` nếu điều kiện chọn khách phải dựa trên **tất cả đơn**.

## 6. Nhận diện khóa nhóm ngầm định trong WITH

Trong phép chiếu `WITH` có hàm tổng hợp, các biểu thức không tổng hợp xác định khóa nhóm. Sự lựa chọn khóa nhóm ảnh hưởng trực tiếp đến việc lọc sau đó.

### 6.1. Nhóm theo khách hàng

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)
WITH c, count(o) AS soDon
WHERE soDon >= 2
RETURN c.id AS maKhach, soDon;
~~~

`c` là khóa nhóm, nên `soDon` là số đơn **của mỗi node khách hàng**.

### 6.2. Nhóm theo trạng thái

~~~cypher
MATCH (o:Order)
WITH o.status AS trangThai, count(o) AS soDon
WHERE soDon >= 2
RETURN trangThai, soDon;
~~~

Chỉ nhóm `PAID` còn lại với `soDon = 4`. Hai trạng thái `PENDING` và `CANCELLED` chỉ có một đơn mỗi trạng thái.

### 6.3. Nhóm theo cặp khách hàng và trạng thái

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)
WITH c.id AS maKhach, o.status AS trangThai, count(o) AS soDon
WHERE soDon >= 2
RETURN maKhach, trangThai, soDon;
~~~

Chỉ cặp `(C01, PAID)` có `soDon = 2`.

Hãy hỏi trước khi viết `WITH`: **một dòng sau bước này đại diện cho một khách, một trạng thái hay một cặp khách–trạng thái?** Điều kiện sau `WITH` đang lọc theo đúng mức đó.

## 7. OPTIONAL MATCH: giữ khách không có đơn khi lọc

Một báo cáo thường phải có cả khách hàng chưa đặt đơn. Với `MATCH` thông thường, khách C03 bị loại vì không có quan hệ `PLACED`. Sử dụng `OPTIONAL MATCH` để giữ lại khách này.

~~~cypher
MATCH (c:Customer)
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
RETURN
  c.id AS maKhach,
  count(o) AS tongSoDon
ORDER BY maKhach;
~~~

Kết quả: C01 = 3, C02 = 2, C03 = 0, C04 = 1.

### 7.1. Lọc bên trong OPTIONAL MATCH để giữ dòng khách

Để đếm **đơn PAID** của *mọi khách*, kể cả khách không có đơn PAID, đặt `WHERE` ngay sau `OPTIONAL MATCH`:

~~~cypher
MATCH (c:Customer)
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
WHERE o.status = 'PAID'
RETURN
  c.id AS maKhach,
  count(o) AS soDonPaid,
  sum(o.amount) AS tongTienPaid
ORDER BY maKhach;
~~~

| maKhach | soDonPaid | tongTienPaid |
|---|---:|---:|
| C01 | 2 | 250000 |
| C02 | 1 | 200000 |
| C03 | 0 | 0 |
| C04 | 1 | 50000 |

Trong trường hợp này, `WHERE` là điều kiện của **mẫu khớp tùy chọn**. Nếu không tìm thấy đơn PAID cho một khách, `OPTIONAL MATCH` vẫn giữ một dòng cho khách đó với `o = null`.

### 7.2. Đẩy điều kiện xuống sau WITH có thể loại mất khách

So sánh:

~~~cypher
MATCH (c:Customer)
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
WITH c, o
WHERE o.status = 'PAID'
RETURN c.id AS maKhach, count(o) AS soDonPaid
ORDER BY maKhach;
~~~

Truy vấn này **không còn giữ C03**. Vì điều kiện được đặt ở `WHERE` sau `WITH c, o`, nó là bộ lọc trên các dòng đã tạo. Dòng của C03 có `o = null`, nên biểu thức `o.status = 'PAID'` không cho giá trị `true` và bị loại.

Cả hai cách đặt `WHERE` đều có thể hợp lệ tùy yêu cầu; vị trí quyết định có giữ nhóm không khớp hay không.

### 7.3. Dùng count(o), tránh count(*) khi đếm đơn

~~~cypher
MATCH (c:Customer)
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
RETURN
  c.id AS maKhach,
  count(*) AS soDong,
  count(o) AS soDon
ORDER BY maKhach;
~~~

Với C03, `soDong = 1` nhưng `soDon = 0`. `OPTIONAL MATCH` tạo một dòng để giữ khách, song biến `o` là `null`. Vì vậy, nếu muốn đếm đơn hàng thực sự tồn tại, dùng `count(o)`.

## 8. Lọc có điều kiện trong phép tổng hợp

Đôi khi cần trên **cùng một dòng khách** cả số đơn toàn bộ, số đơn đã thanh toán và tổng tiền đã thanh toán. Nếu lọc `WHERE o.status = 'PAID'` trước khi nhóm, các đơn trạng thái khác sẽ biến mất khỏi `tongSoDon`. Trong tình huống này, có thể dùng `CASE` bên trong các hàm tổng hợp:

~~~cypher
MATCH (c:Customer)
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
WITH
  c,
  count(o) AS tongSoDon,
  count(CASE WHEN o.status = 'PAID' THEN o END) AS soDonPaid,
  sum(CASE WHEN o.status = 'PAID' THEN o.amount ELSE 0 END)
    AS tongTienPaid
WHERE tongSoDon >= 1
RETURN
  c.id AS maKhach,
  tongSoDon,
  soDonPaid,
  tongTienPaid
ORDER BY maKhach;
~~~

| maKhach | tongSoDon | soDonPaid | tongTienPaid |
|---|---:|---:|---:|
| C01 | 3 | 2 | 250000 |
| C02 | 2 | 1 | 200000 |
| C04 | 1 | 1 | 50000 |

`count(CASE WHEN ... THEN o END)` đếm những dòng mà `CASE` trả ra node `o` khác `null`. `sum(CASE WHEN ... THEN o.amount ELSE 0 END)` chỉ cộng tiền đơn PAID; các dòng khác góp 0.

`WHERE tongSoDon >= 1` nằm sau `WITH`, nên C03 bị loại khỏi báo cáo cuối dù vẫn được giữ trong tập đầu vào trước tổng hợp. Muốn báo cáo chứa cả C03, chỉ cần bỏ điều kiện lọc sau `WITH`.

Lưu ý: dùng `CASE` phù hợp khi cần **nhiều chỉ số khác điều kiện trên cùng một tập dòng**. Nếu cả báo cáo chỉ xét đơn PAID, `WHERE` trước tổng hợp thường đơn giản và dễ đọc hơn.

## 9. WITH cũng quản lý phạm vi biến

Sau `WITH`, chỉ các biến và alias được truyền qua phép chiếu mới có thể dùng ở bước kế tiếp. Điều này vừa giúp giảm dữ liệu phải mang theo vừa khiến một số lỗi thường gặp xuất hiện.

Ví dụ:

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)
WITH c, count(o) AS soDon
WHERE soDon >= 2
RETURN c.id AS maKhach, soDon;
~~~

Trong `RETURN`, ta vẫn dùng được `c` và `soDon`, nhưng biến `o` **không còn trong phạm vi**. Câu lệnh này sẽ không hợp lệ:

~~~cypher
// SAI: o không được truyền qua WITH
MATCH (c:Customer)-[:PLACED]->(o:Order)
WITH c, count(o) AS soDon
WHERE soDon >= 2
RETURN c.id AS maKhach, o.id AS maDon;
~~~

Nếu thêm `o` vào chính `WITH` có tổng hợp để “sửa lỗi”, khóa nhóm sẽ trở thành `(c, o)`. Khi đó `count(o)` có thể chỉ còn bằng 1 cho mỗi đơn, làm sai mục tiêu đếm số đơn **theo khách**.

Muốn vừa lọc nhóm theo tổng số đơn vừa lấy chi tiết từng đơn, hãy nhóm trước rồi khớp lại quan hệ:

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)
WITH c, count(o) AS soDon
WHERE soDon >= 2
MATCH (c)-[:PLACED]->(chiTiet:Order)
RETURN
  c.id AS maKhach,
  soDon,
  chiTiet.id AS maDon
ORDER BY maKhach, maDon;
~~~

Kết quả: ba dòng đơn của C01 và hai dòng đơn của C02; mỗi dòng chi tiết vẫn có `soDon` của khách tương ứng. **Đây là truy vấn trả chi tiết sau khi lọc nhóm**, nên kết quả cuối không còn một dòng trên mỗi khách nữa.

## 10. Tránh đếm/cộng trùng khi mở rộng quan hệ

Mức tổng hợp có thể bị sai nếu một đơn được nhân thành nhiều dòng sau khi đi tới các sản phẩm. Giả sử đồ thị mở rộng bằng:

~~~text
(:Order)-[:CONTAINS {quantity}]->(:Product)
~~~

Nếu một đơn có ba dòng sản phẩm, việc ghép thêm `MATCH (o)-[:CONTAINS]->(p)` sẽ làm đơn đó xuất hiện ba lần. Lúc này `count(o)` đếm **số lần xuất hiện trong dòng**, còn `sum(o.amount)` có thể cộng tiền của đơn nhiều lần.

Ví dụ mô phỏng tình huống không cần thêm dữ liệu mẫu:

~~~cypher
UNWIND [
  {orderId: 'O1', amount: 100000, sku: 'P01'},
  {orderId: 'O1', amount: 100000, sku: 'P02'},
  {orderId: 'O2', amount: 50000, sku: 'P03'}
] AS dong
RETURN
  count(dong) AS soDongChiTiet,
  count(DISTINCT dong.orderId) AS soDonKhacNhau,
  sum(dong.amount) AS tongBiLap;
~~~

Kết quả: `soDongChiTiet = 3`, `soDonKhacNhau = 2`, nhưng `tongBiLap = 250000` thay vì 150000.

Cách an toàn là tính chỉ số của đơn **trước** khi mở rộng sang quan hệ chi tiết, sau đó mới lọc nhóm:

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)
WHERE o.status = 'PAID'
WITH c, count(o) AS soDonPaid, sum(o.amount) AS tongTienPaid
WHERE tongTienPaid >= 200000
RETURN
  c.id AS maKhach,
  soDonPaid,
  tongTienPaid
ORDER BY maKhach;
~~~

Kết quả giữ C01 và C02. Bởi phép tổng hợp được thực hiện trên từng đơn PAID ngay sau `PLACED`, chưa có bước mở rộng nhiều-nhiều làm nhân dòng. Nếu cần thêm thông tin sản phẩm cho những khách đạt điều kiện, hãy thực hiện `MATCH` tiếp theo **sau `WITH ... WHERE`**.

## 11. Hiệu năng: lọc càng sớm càng tốt, nhưng phải đúng nghĩa

Một bộ lọc trước phép tổng hợp thường làm giảm lượng dữ liệu mà toán tử tổng hợp cần xử lý. Bộ lọc sau phép tổng hợp giúp giảm **số nhóm được đưa sang các bước tiếp theo**, nhưng nó không làm biến mất chi phí tổng hợp đã xảy ra.

Ví dụ:

~~~cypher
PROFILE
MATCH (o:Order)
WHERE o.status = 'PAID'
WITH o.status AS trangThai, count(o) AS soDon
WHERE soDon >= 2
RETURN trangThai, soDon;
~~~

Với dữ liệu mẫu:

| Bước | Số dòng có ý nghĩa |
|---|---:|
| `MATCH (o:Order)` trước lọc trạng thái | 6 đơn |
| `WHERE o.status = 'PAID'` | 4 đơn |
| `WITH ... count(o)` nhóm theo `o.status` | 1 nhóm |
| `WHERE soDon >= 2` | 1 nhóm |

`PROFILE` cho biết số dòng thực tế qua từng toán tử trong kế hoạch do Neo4j chọn; bảng trên là diễn giải logic của tập dữ liệu mẫu, không phải dự đoán bắt buộc về cấu trúc hay thứ tự toán tử của mọi kế hoạch thực thi.

Các nguyên tắc khi tối ưu truy vấn:

- **Đặt điều kiện trên dữ liệu nguồn đúng chỗ**: lọc theo `status`, `amount` hoặc mã khách trước tổng hợp khi các điều kiện đó thuộc định nghĩa chỉ số.
- **Đặt điều kiện trên chỉ số sau `WITH`**: `soDon >= 2`, `tongTien > 100000` chỉ có nghĩa sau khi nhóm.
- **Chọn khóa nhóm phù hợp**: thêm property không tổng hợp vào `WITH` có thể tạo thêm nhiều nhóm và làm thay đổi chỉ số.
- **Tránh mở rộng quan hệ quá sớm**: một node có nhiều relationship có thể lặp lại trong tập dòng trước khi `sum` hoặc `count`.
- **Xem `EXPLAIN` / `PROFILE`**: đánh giá số dòng đầu vào, phép duyệt quan hệ và toán tử tổng hợp trên dữ liệu thực tế. Chỉ mục giúp truy xuất điểm xuất phát khi phù hợp, nhưng không đảm bảo loại bỏ chi phí tổng hợp.

Nếu ứng dụng Java Driver hay Spring Data Neo4j cần báo cáo nhóm, tốt hơn nên để Cypher thực hiện tổng hợp và lọc kết quả cần thiết trước khi trả record về ứng dụng, thay vì tải toàn bộ đơn hàng về Java để cộng thủ công.

## 12. Bài tập thực hành

### Bài 1. Chỉ những khách có ít nhất hai đơn PAID

Yêu cầu trả mã khách, tên, số đơn PAID và tổng tiền PAID. Với dữ liệu mẫu, kết quả phải chỉ có C01.

<details>
<summary>Lời giải</summary>

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)
WHERE o.status = 'PAID'
WITH c, count(o) AS soDonPaid, sum(o.amount) AS tongTienPaid
WHERE soDonPaid >= 2
RETURN c.id AS maKhach, c.name AS ten, soDonPaid, tongTienPaid;
~~~

Kết quả: C01 / An / 2 / 250000.

</details>

### Bài 2. Đơn trên 100000 VND, rồi lọc nhóm theo tổng tiền

Yêu cầu: trước tiên chỉ xét các đơn có `amount >= 100000` (không cần phân biệt trạng thái), sau đó chỉ giữ khách có tổng giá trị **ít nhất 200000** từ những đơn đó.

<details>
<summary>Lời giải</summary>

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)
WHERE o.amount >= 100000
WITH c, count(o) AS soDonDatNguong, sum(o.amount) AS tongTienDatNguong
WHERE tongTienDatNguong >= 200000
RETURN c.id AS maKhach, soDonDatNguong, tongTienDatNguong
ORDER BY maKhach;
~~~

C01 có 2 đơn đạt ngưỡng với tổng 250000; C02 có 1 đơn đạt ngưỡng với tổng 200000. C04 bị loại vì chỉ có một đơn 50000.

</details>

### Bài 3. Giữ cả khách chưa có đơn

Yêu cầu: trả mọi khách cùng số đơn PAID; sử dụng `OPTIONAL MATCH` sao cho C03 vẫn xuất hiện với `soDonPaid = 0`.

<details>
<summary>Lời giải</summary>

~~~cypher
MATCH (c:Customer)
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
WHERE o.status = 'PAID'
RETURN c.id AS maKhach, count(o) AS soDonPaid
ORDER BY maKhach;
~~~

C01 = 2, C02 = 1, C03 = 0, C04 = 1.

</details>

### Bài 4. Nhận diện vị trí lọc sai

Xét truy vấn:

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)
WHERE o.status = 'PAID'
WITH c, count(o) AS soDon
WHERE soDon >= 2
RETURN c.id AS maKhach, soDon;
~~~

Một yêu cầu mới đòi hỏi “khách có ít nhất hai **đơn bất kỳ**, sau đó thống kê số đơn PAID”. Hãy cho biết tại sao truy vấn này không đáp ứng yêu cầu và viết lại.

<details>
<summary>Lời giải</summary>

`WHERE o.status = 'PAID'` nằm trước `count(o)`, vì vậy số đếm chỉ phản ánh đơn PAID. C02 có hai đơn bất kỳ nhưng chỉ một đơn PAID nên bị loại sai. Cần tổng hợp tất cả đơn trước, lọc khách đủ điều kiện rồi đếm đơn PAID ở bước riêng:

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)
WITH c, count(o) AS tongSoDon
WHERE tongSoDon >= 2
OPTIONAL MATCH (c)-[:PLACED]->(paid:Order)
WHERE paid.status = 'PAID'
RETURN c.id AS maKhach, tongSoDon, count(paid) AS soDonPaid
ORDER BY maKhach;
~~~

Kết quả gồm C01 / 3 / 2 và C02 / 2 / 1.

</details>

## 13. Ghi nhớ

- **Lọc trước tổng hợp** bằng `WHERE` ở bước `MATCH` xác định **dòng nào tham gia** `count`, `sum`, `avg`, v.v.
- **Lọc sau tổng hợp** bằng `WITH ... AS alias WHERE alias ...` xác định **nhóm nào được giữ lại**.
- Muốn lọc theo `count` hoặc `sum`, hãy tạo alias ở `WITH` rồi dùng `WHERE`. Không viết hàm tổng hợp trực tiếp trong `WHERE` của `MATCH`.
- Các biểu thức không tổng hợp trong `WITH` quyết định **khóa nhóm ngầm định**; thêm khóa có thể thay đổi hoàn toàn mức tính.
- `OPTIONAL MATCH ... WHERE` giữ thực thể gốc khi mẫu tùy chọn không khớp; chuyển điều kiện xuống `WITH ... WHERE` có thể loại dòng `null`.
- `WITH` kiểm soát **phạm vi biến**. Nếu muốn lọc khách theo số đơn rồi lấy từng đơn, hãy tổng hợp và lọc trước, sau đó khớp lại quan hệ.
- Tối ưu bằng cách giảm dòng nguồn trước tổng hợp và giảm nhóm trước các bước mở rộng tiếp theo, đồng thời đảm bảo vị trí lọc **đúng với câu hỏi nghiệp vụ**.
