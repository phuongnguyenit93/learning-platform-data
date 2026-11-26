# count, sum, avg, min và max trong truy vấn đồ thị

Trong Neo4j, dữ liệu được lưu dưới dạng **node**, **relationship** và các **property**. Khi truy vấn bằng Cypher, ta thường không chỉ muốn lấy ra các node có liên quan mà còn cần trả lời những câu hỏi như: một khách hàng đã đặt bao nhiêu đơn, tổng giá trị đơn hàng là bao nhiêu, mức trung bình là gì, hay đơn hàng lớn nhất thuộc về ai. Năm hàm tổng hợp `count()`, `sum()`, `avg()`, `min()` và `max()` giải quyết các nhu cầu đó.

Điểm đặc thù của truy vấn đồ thị là **mỗi đường khớp mẫu (matched path) có thể tạo ra một dòng kết quả trung gian**. Vì vậy, trước khi tổng hợp, cần hiểu Cypher đang có bao nhiêu dòng và một node có xuất hiện lặp lại qua nhiều đường đi hay không.

## 1. Dữ liệu mẫu và mục tiêu

Xét mô hình cửa hàng sách:

~~~text
(:Customer)-[:PLACED]->(:Order)-[:HAS_ITEM {quantity}]->(:Product)
~~~

- `Customer`: khách hàng; có `id` và `name`.
- `Order`: đơn hàng; có `id`, `amount` (giá trị đơn hàng, đơn vị VND) và `status`.
- `Product`: sản phẩm; có `sku` và `name`.
- `HAS_ITEM.quantity`: số lượng sản phẩm được đặt trong một dòng đơn hàng.

Tạo bộ dữ liệu nhỏ để có thể tự chạy tất cả ví dụ dưới đây trên cơ sở dữ liệu thực hành trống:

~~~cypher
CREATE
  (an:Customer {id: 'C01', name: 'An'}),
  (binh:Customer {id: 'C02', name: 'Binh'}),
  (chi:Customer {id: 'C03', name: 'Chi'}),
  (o101:Order {id: 'O101', amount: 120000, status: 'PAID'}),
  (o102:Order {id: 'O102', amount: 80000,  status: 'PAID'}),
  (o103:Order {id: 'O103', amount: 200000, status: 'PENDING'}),
  (neo4j:Product {sku: 'P01', name: 'Neo4j'}),
  (java:Product {sku: 'P02', name: 'Java'}),
  (an)-[:PLACED]->(o101),
  (an)-[:PLACED]->(o102),
  (binh)-[:PLACED]->(o103),
  (o101)-[:HAS_ITEM {quantity: 1}]->(neo4j),
  (o101)-[:HAS_ITEM {quantity: 2}]->(java),
  (o102)-[:HAS_ITEM {quantity: 1}]->(java),
  (o103)-[:HAS_ITEM {quantity: 3}]->(neo4j);
~~~

Chạy lệnh `CREATE` **một lần** trên cơ sở dữ liệu thực hành trống để tránh tạo dữ liệu trùng. Trong bộ dữ liệu này, An có hai đơn, Binh có một đơn, còn Chi chưa có đơn nào. Đơn O101 chứa hai loại sản phẩm; chi tiết này giúp quan sát hiện tượng nhân số dòng khi duyệt thêm quan hệ.

## 2. Năm hàm tổng hợp hoạt động như thế nào?

| Hàm | Ý nghĩa | Kết quả thường dùng |
|---|---|---|
| `count(*)` | Đếm mọi dòng đi vào phép tổng hợp, kể cả dòng có giá trị `null` ở một biến | Số dòng/đường khớp mẫu |
| `count(x)` | Đếm những dòng mà biểu thức `x` khác `null` | Số node, relationship hoặc giá trị có mặt |
| `sum(x)` | Cộng các giá trị số khác `null` | Tổng doanh thu, tổng số lượng |
| `avg(x)` | Trung bình cộng các giá trị số khác `null` | Giá trị đơn hàng trung bình |
| `min(x)`, `max(x)` | Lấy giá trị nhỏ nhất/lớn nhất trong các giá trị so sánh được, bỏ qua `null` | Biên dưới/biên trên của một tập |

Các hàm tổng hợp biến nhiều dòng thành một dòng cho mỗi **nhóm**. Nếu câu lệnh `RETURN` hoặc `WITH` chỉ chứa các biểu thức tổng hợp thì Cypher tạo một nhóm chung. Nếu có cả biểu thức không tổng hợp, chẳng hạn `c.name` hoặc `o.status`, các biểu thức đó trở thành **khóa nhóm**.

Ví dụ, thống kê mọi đơn hàng:

~~~cypher
MATCH (o:Order)
RETURN
  count(o) AS soDon,
  sum(o.amount) AS tongGiaTri,
  avg(o.amount) AS trungBinh,
  min(o.amount) AS thapNhat,
  max(o.amount) AS caoNhat;
~~~

Kết quả mong đợi: `soDon = 3`, `tongGiaTri = 400000`, `trungBinh ≈ 133333.33`, `thapNhat = 80000`, `caoNhat = 200000`. Giá trị trung bình có thể được hiển thị với nhiều chữ số thập phân hơn.

## 3. count(): đếm đúng đối tượng cần đếm

### 3.1. Phân biệt count(*) và count(biểu_thức)

Với `MATCH (o:Order)`, mỗi đơn hàng tạo một dòng nên `count(*)` và `count(o)` đều là 3. Tuy nhiên, khi dùng `OPTIONAL MATCH`, một khách hàng không có đơn vẫn được giữ lại, với biến `o` mang giá trị `null`:

~~~cypher
MATCH (c:Customer)
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
RETURN
  c.name AS khachHang,
  count(*) AS soDong,
  count(o) AS soDon
ORDER BY khachHang;
~~~

| khachHang | soDong | soDon |
|---|---:|---:|
| An | 2 | 2 |
| Binh | 1 | 1 |
| Chi | 1 | 0 |

Chi vẫn tạo ra **một dòng do `OPTIONAL MATCH`**, nhưng dòng này không có node `o`. Do đó:

- Dùng `count(*)` khi thật sự muốn biết số dòng trung gian.
- Dùng `count(o)` khi muốn đếm các đơn hàng tồn tại, đặc biệt sau `OPTIONAL MATCH`.
- Dùng `count(o.amount)` nếu mục tiêu là đếm số giá trị `amount` khác `null`, vì một node tồn tại vẫn có thể thiếu property.

### 3.2. count(DISTINCT ...): loại bỏ lần xuất hiện lặp

Khi mở rộng từ đơn hàng sang sản phẩm, O101 xuất hiện hai lần vì có hai quan hệ `HAS_ITEM`:

~~~cypher
MATCH (o:Order)-[:HAS_ITEM]->(p:Product)
RETURN
  count(*) AS soDongChiTiet,
  count(o) AS soLanXuatHienCuaDon,
  count(DISTINCT o) AS soDonKhacNhau;
~~~

Kết quả: `soDongChiTiet = 4`, `soLanXuatHienCuaDon = 4`, nhưng `soDonKhacNhau = 3`.

`DISTINCT` tác động lên giá trị của biểu thức được đếm. `count(DISTINCT o)` đếm số node đơn hàng khác nhau, còn `count(DISTINCT o.status)` đếm số giá trị trạng thái khác nhau (ở dữ liệu mẫu là 2). Cần chọn chính xác đơn vị đếm: dòng, đơn hàng, quan hệ hay trạng thái.

## 4. sum() và avg(): tổng và trung bình

### 4.1. Tổng hợp trên property của node

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)
RETURN
  c.name AS khachHang,
  count(o) AS soDon,
  sum(o.amount) AS tongGiaTri,
  avg(o.amount) AS giaTriTrungBinh
ORDER BY khachHang;
~~~

| khachHang | soDon | tongGiaTri | giaTriTrungBinh |
|---|---:|---:|---:|
| An | 2 | 200000 | 100000.0 |
| Binh | 1 | 200000 | 200000.0 |

Chi không xuất hiện vì `MATCH` thông thường loại bỏ các khách hàng không khớp quan hệ. Nếu báo cáo phải có cả những người chưa mua hàng, sử dụng `OPTIONAL MATCH`:

~~~cypher
MATCH (c:Customer)
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
RETURN
  c.name AS khachHang,
  count(o) AS soDon,
  coalesce(sum(o.amount), 0) AS tongGiaTri,
  avg(o.amount) AS giaTriTrungBinh
ORDER BY khachHang;
~~~

Chi có `soDon = 0`, `tongGiaTri = 0` và `giaTriTrungBinh = null`. `avg()` không thể tính trung bình khi không có giá trị hợp lệ. Không nên mặc định thay `null` bằng 0 cho trung bình nếu 0 sẽ khiến người đọc nhầm rằng có một quan sát với giá trị bằng 0.

### 4.2. Tổng hợp property của relationship

Một chỉ số trong đồ thị thường nằm trên **quan hệ**, chẳng hạn số lượng từng sản phẩm trong một đơn:

~~~cypher
MATCH (o:Order)-[item:HAS_ITEM]->(p:Product)
RETURN
  p.name AS sanPham,
  count(item) AS soDongDonHang,
  sum(item.quantity) AS tongSoLuong
ORDER BY sanPham;
~~~

| sanPham | soDongDonHang | tongSoLuong |
|---|---:|---:|
| Java | 2 | 3 |
| Neo4j | 2 | 4 |

Ở đây `sum(item.quantity)` cộng số lượng trên từng quan hệ `HAS_ITEM`. `count(item)` lại đếm số dòng quan hệ, không đếm số cuốn sách. Hai chỉ số có ý nghĩa nghiệp vụ khác nhau.

### 4.3. Chỉ tổng hợp một tập con

Giá trị của đơn đang chờ thanh toán không phải doanh thu đã thu. Lọc trước khi tổng hợp:

~~~cypher
MATCH (o:Order)
WHERE o.status = 'PAID'
RETURN
  count(o) AS soDonDaThanhToan,
  sum(o.amount) AS doanhThuDaThanhToan,
  avg(o.amount) AS trungBinhDonDaThanhToan;
~~~

Kết quả lần lượt là `2`, `200000` và `100000.0`. Điều kiện `WHERE` quyết định **những dòng nào đi vào hàm tổng hợp**.

Trong hệ thống thật, để tránh sai số khi tính tiền, có thể lưu giá trị tiền dưới dạng số nguyên theo đơn vị tiền nhỏ nhất phù hợp (ví dụ số VND nguyên), thay vì dùng số thực nhị phân cho các phép cộng cần độ chính xác tuyệt đối.

## 5. min() và max(): tìm cực trị

~~~cypher
MATCH (o:Order)
RETURN
  min(o.amount) AS donNhoNhat,
  max(o.amount) AS donLonNhat;
~~~

Kết quả là `80000` và `200000`. Hai hàm này trả về **giá trị cực trị**, không tự trả về node đơn hàng tương ứng. Muốn biết đơn nào có giá trị cao nhất, sắp xếp các đơn rồi lấy dòng đầu tiên:

~~~cypher
MATCH (o:Order)
RETURN o.id AS maDon, o.amount AS giaTri
ORDER BY giaTri DESC, maDon ASC
LIMIT 1;
~~~

Kết quả là đơn `O103`, giá trị `200000`. Phần sắp xếp phụ `maDon ASC` làm kết quả ổn định khi nhiều đơn cùng giá trị; `LIMIT 1` chỉ trả về một đơn trong trường hợp đồng hạng.

`min()` và `max()` còn hữu ích với các giá trị có thứ tự so sánh, ví dụ thời điểm bắt đầu/kết thúc được lưu dưới dạng `date` hoặc `datetime`. Để báo cáo có ý nghĩa, các giá trị đưa vào cùng một phép tổng hợp nên thống nhất kiểu dữ liệu và ý nghĩa nghiệp vụ.

## 6. Nhóm dữ liệu bằng RETURN và WITH

Trong Cypher, không cần khai báo `GROUP BY` riêng. Các biểu thức **không tổng hợp** trong cùng phép chiếu xác định nhóm.

~~~cypher
MATCH (o:Order)
RETURN
  o.status AS trangThai,
  count(*) AS soDon,
  sum(o.amount) AS tongGiaTri,
  avg(o.amount) AS trungBinh
ORDER BY trangThai;
~~~

| trangThai | soDon | tongGiaTri | trungBinh |
|---|---:|---:|---:|
| PAID | 2 | 200000 | 100000.0 |
| PENDING | 1 | 200000 | 200000.0 |

Câu lệnh `WITH` cũng có thể thực hiện tổng hợp và đưa kết quả sang bước tiếp theo. Ví dụ, tìm khách hàng có ít nhất hai đơn hàng:

~~~cypher
MATCH (c:Customer)
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
WITH c, count(o) AS soDon, sum(o.amount) AS tongGiaTri
WHERE soDon >= 2
RETURN c.name AS khachHang, soDon, tongGiaTri
ORDER BY soDon DESC;
~~~

Chỉ có An thỏa điều kiện. Lúc này `WHERE soDon >= 2` chạy **sau** bước tổng hợp trong `WITH`, nên lọc được theo kết quả đếm.

Quy tắc quan trọng: trước mỗi bước `RETURN` hoặc `WITH` có hàm tổng hợp, hãy xác định rõ khóa nhóm. Thêm một biến không tổng hợp vào `RETURN` có thể chia một nhóm lớn thành nhiều nhóm nhỏ và làm thay đổi toàn bộ kết quả.

## 7. null, kết quả rỗng và OPTIONAL MATCH

Hầu hết hàm tổng hợp bỏ qua giá trị `null` trong biểu thức đầu vào. Quan sát ví dụ độc lập:

~~~cypher
UNWIND [10, null, 20] AS x
RETURN
  count(*) AS soDong,
  count(x) AS soGiaTri,
  sum(x) AS tong,
  avg(x) AS trungBinh,
  min(x) AS nhoNhat,
  max(x) AS lonNhat;
~~~

Kết quả: `soDong = 3`, `soGiaTri = 2`, `tong = 30`, `trungBinh = 15.0`, `nhoNhat = 10`, `lonNhat = 20`.

Khi không có giá trị số hợp lệ, `avg()` trả `null`; `min()` và `max()` cũng trả `null` nếu không có giá trị để so sánh. `count()` trả 0 khi không có giá trị cần đếm; `sum()` trả 0 khi không có giá trị để cộng. Cần phân biệt “không có quan sát” với “quan sát có giá trị bằng 0”, nhất là khi hiển thị báo cáo.

Với `OPTIONAL MATCH`, đặt `WHERE` ngay sau mẫu quan hệ tùy chọn để vẫn giữ các khách hàng không có đơn phù hợp:

~~~cypher
MATCH (c:Customer)
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
WHERE o.status = 'PAID'
RETURN
  c.name AS khachHang,
  count(o) AS soDonDaThanhToan,
  sum(o.amount) AS tongDaThanhToan
ORDER BY khachHang;
~~~

Kết quả theo thứ tự An/Binh/Chi: số đơn đã thanh toán là `2/0/0`; tổng tiền đã thanh toán là `200000/0/0`. Điều kiện `WHERE` này gắn với `OPTIONAL MATCH`, nên Binh và Chi vẫn được giữ lại.

Nếu cần **nhiều chỉ số có điều kiện trong cùng một lần duyệt**, có thể kết hợp `CASE` với tổng hợp:

~~~cypher
MATCH (c:Customer)
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
RETURN
  c.name AS khachHang,
  count(o) AS tongSoDon,
  count(CASE WHEN o.status = 'PAID' THEN o END) AS donDaThanhToan,
  sum(CASE WHEN o.status = 'PAID' THEN o.amount ELSE 0 END)
    AS tienDaThanhToan
ORDER BY khachHang;
~~~

Cách này đếm tất cả đơn bằng `count(o)`, nhưng chỉ cộng giá trị cho các đơn có trạng thái `PAID`. Cần kiểm tra cẩn thận phần `ELSE` trong `CASE`: trả `0` nghĩa là dòng đó đóng góp 0 vào tổng, trong khi không có `ELSE` thường tạo `null` và được hàm tổng hợp bỏ qua.

## 8. Bẫy thường gặp: một node bị tính nhiều lần sau khi mở rộng quan hệ

Xét truy vấn sau:

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)
MATCH (o)-[:HAS_ITEM]->(p:Product)
RETURN c.name AS khachHang, sum(o.amount) AS tongGiaTri
ORDER BY khachHang;
~~~

Với An, đơn O101 xuất hiện **hai lần** vì kết nối tới hai sản phẩm. Vì thế truy vấn trả `320000` cho An (`120000 + 120000 + 80000`) thay vì `200000`. Truy vấn không sai về mặt cú pháp, nhưng **đang cộng trên các dòng chi tiết sản phẩm** thay vì trên từng đơn hàng.

Cách khắc phục là tổng hợp theo đơn hàng **trước** khi mở rộng sang quan hệ chi tiết, sau đó mới tính số lượng sản phẩm:

~~~cypher
MATCH (c:Customer)
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
WITH
  c,
  count(o) AS soDon,
  sum(o.amount) AS tongGiaTriDon
OPTIONAL MATCH (c)-[:PLACED]->(:Order)-[item:HAS_ITEM]->(:Product)
RETURN
  c.name AS khachHang,
  soDon,
  tongGiaTriDon,
  sum(item.quantity) AS tongSoLuong
ORDER BY khachHang;
~~~

Kết quả mong đợi:

| khachHang | soDon | tongGiaTriDon | tongSoLuong |
|---|---:|---:|---:|
| An | 2 | 200000 | 4 |
| Binh | 1 | 200000 | 3 |
| Chi | 0 | 0 | 0 |

Không nên sửa bẫy trên bằng `sum(DISTINCT o.amount)`. Nếu hai đơn khác nhau cùng có `amount = 120000`, `DISTINCT` trên **giá trị tiền** sẽ gộp nhầm chúng thành một. Chỉ dùng `DISTINCT` khi thực sự muốn loại bỏ những giá trị trùng theo đúng định nghĩa của chỉ số.

Một nguyên tắc an toàn khi viết truy vấn đồ thị là: **chọn đơn vị tổng hợp (khách hàng, đơn hàng, sản phẩm hoặc quan hệ) trước, rồi kiểm tra số dòng sau từng `MATCH`**. Nhiều nhánh quan hệ hoặc nhiều mẫu `MATCH` độc lập có thể làm số dòng tăng mạnh và nhân đôi giá trị được cộng.

## 9. Hiệu năng và kiểm tra kết quả

Với đồ thị lớn, chi phí truy vấn không chỉ phụ thuộc vào phép cộng hay phép đếm, mà còn phụ thuộc vào số node/relationship được duyệt và số dòng phải đưa qua bước tổng hợp.

- **Lọc sớm:** nếu chỉ cần đơn đã thanh toán, đặt `WHERE o.status = 'PAID'` trước phép tổng hợp để giảm số dòng xử lý.
- **Tổng hợp đúng thời điểm:** dùng `WITH` để gộp kết quả trước khi mở rộng thêm các quan hệ không cần thiết cho chỉ số đang tính.
- **Cân nhắc DISTINCT:** chỉ loại trùng trên đúng thực thể cần đếm; việc loại trùng trên tập kết quả lớn cũng cần bộ nhớ và thời gian.
- **Xem kế hoạch thực thi:** `EXPLAIN` cho biết kế hoạch dự kiến, còn `PROFILE` thực thi truy vấn và hiển thị số dòng thực tế qua các toán tử. Đối chiếu số dòng trước/sau khi duyệt quan hệ để phát hiện nhân bản không mong muốn.
- **Kiểm tra lọc bằng chỉ mục:** với property được dùng thường xuyên trong điều kiện lọc, một index phù hợp có thể giúp tìm node đầu vào nhanh hơn; cần xem kế hoạch thực tế thay vì giả định mọi truy vấn tổng hợp đều sử dụng index.

Ví dụ kiểm tra truy vấn thống kê đơn đã thanh toán:

~~~cypher
PROFILE
MATCH (o:Order)
WHERE o.status = 'PAID'
RETURN count(o) AS soDonDaThanhToan;
~~~

Khi kiểm thử, hãy đối chiếu tối thiểu ba tình huống: node có nhiều quan hệ, node không có quan hệ và property bị thiếu/`null`. Với các tình huống này, sai số trong kết quả tổng hợp thường dễ bộc lộ nhất.

## 10. Bài tập tự luyện

**Bài 1.** Viết truy vấn thống kê tổng số lượng đã đặt của từng sản phẩm, kể cả sản phẩm chưa được đặt. Với dữ liệu mẫu, Java có 3 đơn vị và Neo4j có 4 đơn vị.

<details>
<summary>Gợi ý đáp án</summary>

~~~cypher
MATCH (p:Product)
OPTIONAL MATCH (:Order)-[item:HAS_ITEM]->(p)
RETURN
  p.name AS sanPham,
  count(item) AS soDongDonHang,
  sum(item.quantity) AS tongSoLuong
ORDER BY sanPham;
~~~

</details>

**Bài 2.** Liệt kê mọi khách hàng kèm số đơn và giá trị đơn lớn nhất. Khách hàng chưa từng đặt hàng phải xuất hiện với số đơn bằng 0 và giá trị lớn nhất bằng `null`.

<details>
<summary>Gợi ý đáp án</summary>

~~~cypher
MATCH (c:Customer)
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
RETURN
  c.name AS khachHang,
  count(o) AS soDon,
  max(o.amount) AS giaTriLonNhat
ORDER BY khachHang;
~~~

</details>

**Bài 3.** Một truy vấn bắt đầu ở `Order`, đi tiếp tới `Product`, rồi dùng `sum(o.amount)` để tính tổng tiền. Hãy giải thích tại sao kết quả có thể lớn hơn thực tế và viết lại truy vấn sao cho một đơn chỉ được cộng một lần. Có thể dùng mẫu xử lý bằng `WITH` trong mục 8 để đối chiếu.

## Ghi nhớ

- `count(*)` đếm **dòng**; `count(x)` đếm giá trị **khác null**; `count(DISTINCT x)` đếm các giá trị khác nhau.
- `sum()` và `avg()` xử lý số; `min()` và `max()` tìm cực trị; hầu hết phép tổng hợp bỏ qua `null`.
- Biểu thức không tổng hợp trong `RETURN` hoặc `WITH` xác định **khóa nhóm**.
- `OPTIONAL MATCH` giữ những node không có quan hệ phù hợp, nên đặc biệt hữu ích cho báo cáo cần hiển thị cả nhóm có giá trị 0.
- Trước khi cộng hoặc đếm trong đồ thị, phải hiểu **một thực thể xuất hiện bao nhiêu lần trong tập dòng trung gian**. Đây là điểm quyết định tính đúng đắn của truy vấn tổng hợp Cypher.
