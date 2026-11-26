# collect để gom dữ liệu và quản lý kích thước danh sách

Trong Neo4j, truy vấn Cypher thường đi từ một node sang nhiều relationship để tìm các thực thể liên quan. Chẳng hạn, một khách hàng có nhiều đơn hàng, một đơn hàng chứa nhiều sản phẩm, hoặc một người có nhiều bạn bè. Khi ứng dụng muốn trả **một dòng cho mỗi thực thể chính** và kèm danh sách những thực thể liên quan, hàm tổng hợp `collect()` là công cụ quan trọng.

Tuy nhiên, `collect()` có thể tạo danh sách rất lớn khi đồ thị có nhiều nhánh quan hệ. Để sử dụng tốt, cần hiểu số dòng đầu vào, khóa nhóm, cách loại trùng, thứ tự kết quả và thời điểm áp dụng `LIMIT`. Bài học thuộc chương **Tổng hợp dữ liệu** của module Neo4j, tập trung vào kỹ thuật gom dữ liệu theo mô hình *property graph* và kiểm soát kích thước kết quả trong Cypher.

## 1. collect() giải quyết bài toán gì?

Giả sử một khách hàng có ba đơn hàng. Một truy vấn `MATCH` thường trả ba dòng:

~~~cypher
MATCH (c:Customer {id: 'C01'})-[:PLACED]->(o:Order)
RETURN c.id AS maKhach, o.id AS maDon;
~~~

Ứng dụng có thể muốn một cấu trúc gần với JSON:

~~~json
{
  "maKhach": "C01",
  "maDon": ["O101", "O102", "O104"]
}
~~~

Đây là lúc dùng `collect(o.id)`: **gom các giá trị từ nhiều dòng thành một list** trong mỗi nhóm tổng hợp.

~~~cypher
MATCH (c:Customer {id: 'C01'})-[:PLACED]->(o:Order)
RETURN c.id AS maKhach, collect(o.id) AS maDon;
~~~

`collect()` là **hàm tổng hợp (aggregation function)**. Nó khác với list literal `['a', 'b']`, vì list literal được khai báo trực tiếp, còn `collect()` xây dựng list từ những dòng dữ liệu do truy vấn tạo ra.

## 2. Bộ dữ liệu mẫu dùng xuyên suốt

Xét property graph của cửa hàng sách:

~~~text
(:Customer)-[:PLACED]->(:Order)-[:CONTAINS {quantity}]->(:Product)
~~~

- `Customer`: khách hàng, có `id` và `name`.
- `Order`: đơn hàng, có `id`, `createdAt` (kiểu `date`), `amount` và `status`.
- `Product`: sản phẩm, có `sku` và `name`.
- `CONTAINS.quantity`: số lượng sản phẩm trong đơn.

Tạo dữ liệu trên một **cơ sở dữ liệu thực hành trống** và chỉ chạy lệnh `CREATE` này một lần:

~~~cypher
CREATE
  (an:Customer {id: 'C01', name: 'An'}),
  (binh:Customer {id: 'C02', name: 'Binh'}),
  (chi:Customer {id: 'C03', name: 'Chi'}),
  (o101:Order {id: 'O101', createdAt: date('2026-11-01'),
                amount: 120000, status: 'PAID'}),
  (o102:Order {id: 'O102', createdAt: date('2026-11-03'),
                amount: 80000, status: 'PAID'}),
  (o103:Order {id: 'O103', createdAt: date('2026-11-04'),
                amount: 200000, status: 'PENDING'}),
  (o104:Order {id: 'O104', createdAt: date('2026-11-05'),
                amount: 60000, status: 'PAID'}),
  (o105:Order {id: 'O105', createdAt: date('2026-11-06'),
                amount: 50000, status: 'PAID'}),
  (p01:Product {sku: 'P01', name: 'Java'}),
  (p02:Product {sku: 'P02', name: 'Neo4j'}),
  (p03:Product {sku: 'P03', name: 'Cypher'}),
  (an)-[:PLACED]->(o101),
  (an)-[:PLACED]->(o102),
  (an)-[:PLACED]->(o104),
  (binh)-[:PLACED]->(o103),
  (binh)-[:PLACED]->(o105),
  (o101)-[:CONTAINS {quantity: 1}]->(p01),
  (o101)-[:CONTAINS {quantity: 2}]->(p02),
  (o102)-[:CONTAINS {quantity: 1}]->(p02),
  (o103)-[:CONTAINS {quantity: 2}]->(p01),
  (o103)-[:CONTAINS {quantity: 1}]->(p03),
  (o104)-[:CONTAINS {quantity: 1}]->(p02),
  (o105)-[:CONTAINS {quantity: 3}]->(p03);
~~~

Bộ dữ liệu có ba khách hàng, năm đơn hàng, ba sản phẩm và bảy quan hệ `CONTAINS`.

| Khách hàng | Các đơn hàng | Số đơn |
|---|---|---:|
| C01 / An | O101, O102, O104 | 3 |
| C02 / Binh | O103, O105 | 2 |
| C03 / Chi | Chưa có đơn | 0 |

Chính trường hợp Chi chưa có đơn sẽ giúp kiểm tra cách `collect()` xử lý `null`.

## 3. Cú pháp collect() và kiểu dữ liệu trả về

Dạng cơ bản:

~~~cypher
collect(bieuThuc)
collect(DISTINCT bieuThuc)
~~~

Với mỗi nhóm kết quả, `collect()` nhận từng giá trị biểu thức ở các dòng trong nhóm và tạo **list** chứa các giá trị **khác `null`**. Nó có thể gom ID, chuỗi, số, node, relationship hoặc map.

Ví dụ gom toàn bộ mã đơn:

~~~cypher
MATCH (o:Order)
RETURN collect(o.id) AS danhSachMaDon;
~~~

Kết quả là **một dòng** chứa list gồm năm mã đơn; thứ tự phần tử chưa được đảm bảo nếu không chỉ định sắp xếp.

Nếu thêm khóa nhóm không tổng hợp, Cypher gom list theo từng nhóm:

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)
RETURN
  c.id AS maKhach,
  collect(o.id) AS danhSachMaDon
ORDER BY maKhach;
~~~

Có hai dòng kết quả, một cho C01 và một cho C02. C03 không xuất hiện do `MATCH` thông thường đòi hỏi phải có quan hệ `PLACED`.

### 3.1. Gom node, property hay map?

Ba cách dưới đây tạo các list với **phần tử khác nhau**:

~~~cypher
MATCH (c:Customer {id: 'C01'})-[:PLACED]->(o:Order)
RETURN
  collect(o) AS dsNodeDon,
  collect(o.id) AS dsMaDon,
  collect(o {.id, .amount, .status}) AS dsTomTatDon;
~~~

| Biểu thức | Kiểu phần tử | Thích hợp khi |
|---|---|---|
| `collect(o)` | Node `Order` | Cần làm việc tiếp với thực thể trong Cypher |
| `collect(o.id)` | Chuỗi | API chỉ cần mã đơn |
| `collect(o {.id, .amount, .status})` | Map | API cần cấu trúc dữ liệu rõ ràng và ít trường |

Map projection `o {.id, .amount, .status}` chỉ lấy các property được liệt kê. Khi trả kết quả qua Java Driver hoặc API, cách gom map nhỏ thường dễ kiểm soát kích thước dữ liệu truyền đi hơn việc trả toàn bộ node có nhiều property.

Chú ý: giảm số property giúp **giảm kích thước phần tử**, nhưng không giới hạn **số phần tử** của list. Một khách hàng có hàng trăm nghìn đơn vẫn có thể tạo một list rất lớn.

### 3.2. collect() và count() không thay thế nhau

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)
RETURN
  c.id AS maKhach,
  count(o) AS soDon,
  collect(o.id) AS maDon
ORDER BY maKhach;
~~~

`count(o)` trả **một số**, trong khi `collect(o.id)` trả **một list**. Khi chỉ cần số lượng, nên dùng `count()` vì không cần tạo và giữ một danh sách ID.

## 4. Giữ cả nhóm không có phần tử: OPTIONAL MATCH và null

Khi báo cáo phải bao gồm khách hàng chưa có đơn, bắt đầu từ toàn bộ node khách hàng và dùng `OPTIONAL MATCH`:

~~~cypher
MATCH (c:Customer)
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
RETURN
  c.id AS maKhach,
  count(o) AS soDon,
  collect(o.id) AS maDon
ORDER BY maKhach;
~~~

| maKhach | soDon | maDon |
|---|---:|---|
| C01 | 3 | List gồm O101, O102, O104 |
| C02 | 2 | List gồm O103, O105 |
| C03 | 0 | `[]` |

Với Chi, `OPTIONAL MATCH` tạo một dòng có `o = null`. Biểu thức `o.id` cũng là `null`, và `collect(o.id)` **bỏ qua phần tử null**. Vì vậy list của Chi là `[]`, không phải `[null]`.

Có thể tự kiểm tra quy tắc này bằng truy vấn không phụ thuộc dữ liệu mẫu:

~~~cypher
UNWIND ['A', null, 'B'] AS x
RETURN
  count(*) AS soDong,
  count(x) AS soGiaTri,
  collect(x) AS danhSach;
~~~

Kết quả: `soDong = 3`, `soGiaTri = 2` và `danhSach` chứa `'A'`, `'B'` theo một thứ tự không nên phụ thuộc nếu chưa sắp xếp.

Nếu tất cả giá trị đều `null`, `collect()` trả list rỗng `[]`. Nếu không có khóa nhóm và đầu vào hoàn toàn rỗng, truy vấn tổng hợp như sau vẫn trả một dòng chứa `[]`:

~~~cypher
MATCH (o:Order)
WHERE o.status = 'CANCELLED'
RETURN collect(o.id) AS maDon;
~~~

Ngược lại, nếu cùng truy vấn chiếu thêm `o.status` làm khóa nhóm, tập đầu vào rỗng sẽ tạo **không dòng kết quả**.

## 5. collect(DISTINCT ...): tránh phần tử trùng

Trong đồ thị, cùng một node có thể được khớp nhiều lần qua các đường đi khác nhau. Đặc biệt, sản phẩm `Neo4j` của An xuất hiện trong **ba đơn hàng**. Xét truy vấn:

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)-[:CONTAINS]->(p:Product)
RETURN
  c.id AS maKhach,
  count(p) AS soDongSanPham,
  collect(p.name) AS cacLanSanPhamXuatHien,
  collect(DISTINCT p.name) AS cacLoaiSanPham
ORDER BY maKhach;
~~~

| maKhach | soDongSanPham | cacLanSanPhamXuatHien | cacLoaiSanPham |
|---|---:|---|---|
| C01 | 4 | Java, Neo4j, Neo4j, Neo4j | Java, Neo4j |
| C02 | 3 | Java, Cypher, Cypher | Java, Cypher |

Các cột list trong bảng được viết theo một thứ tự minh họa; truy vấn chưa chỉ định thứ tự nên Neo4j có thể trả thứ tự khác.

- `collect(p.name)` **giữ số lần xuất hiện** của cùng tên sản phẩm.
- `collect(DISTINCT p.name)` **giữ một phần tử cho mỗi tên khác nhau** trong từng nhóm khách hàng.
- `collect(DISTINCT p)` loại trùng theo **danh tính node**, hữu ích nếu nhiều node có thể trùng tên.
- `DISTINCT` không bảo đảm thứ tự của list.

### 5.1. Chọn đúng đơn vị khi loại trùng

Một đơn hàng có thể chứa nhiều sản phẩm, nên phép duyệt từ `Order` sang `Product` sẽ nhân dòng của đơn hàng:

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)-[:CONTAINS]->(p:Product)
RETURN
  c.id AS maKhach,
  collect(o.id) AS maDonCoLap,
  collect(DISTINCT o.id) AS maDonKhacNhau
ORDER BY maKhach;
~~~

Với C01, danh sách có lặp chứa `O101` **hai lần** vì đơn đó có hai dòng sản phẩm. Danh sách `DISTINCT` chỉ còn ba mã đơn khác nhau: O101, O102, O104.

Tuy nhiên, không nên dùng `DISTINCT` một cách máy móc. Nếu nghiệp vụ cần thống kê **mỗi lần một sản phẩm xuất hiện trong đơn**, loại trùng sẽ làm mất thông tin về số lần xuất hiện. Nếu cần **số lượng hàng hóa**, sử dụng `sum(line.quantity)` trên relationship, vì `collect(DISTINCT p.name)` chỉ trả tên loại sản phẩm.

## 6. Thứ tự phần tử: phải sắp xếp trước khi collect

Một sai lầm phổ biến là mặc định list trả về theo thời gian tạo đơn hoặc theo ID. Trong Cypher, thứ tự dòng không được bảo đảm khi không có `ORDER BY`; do đó list từ `collect()` cũng **không nên được coi là đã sắp xếp**.

Muốn gom danh sách đơn hàng mới nhất đến cũ nhất cho từng khách hàng:

~~~cypher
MATCH (c:Customer)
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
WITH c, o
ORDER BY c.id, o.createdAt DESC, o.id ASC
RETURN
  c.id AS maKhach,
  collect(o.id) AS maDonMoiDenCu
ORDER BY maKhach;
~~~

Kết quả mong đợi:

| maKhach | maDonMoiDenCu |
|---|---|
| C01 | `['O104', 'O102', 'O101']` |
| C02 | `['O105', 'O103']` |
| C03 | `[]` |

`ORDER BY` trong `WITH` đảm bảo thứ tự dòng được đưa vào **mệnh đề `RETURN` ngay sau nó**. Vì vậy `collect(o.id)` nhận các đơn theo thứ tự đã chọn. Dùng thêm `o.id ASC` làm khóa phụ để kết quả ổn định nếu hai đơn có cùng ngày tạo.

Sự khác nhau rất quan trọng:

~~~cypher
MATCH (c:Customer)
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
RETURN c.id AS maKhach, collect(o.id) AS maDon
ORDER BY maKhach;
~~~

Trong truy vấn thứ hai, `ORDER BY maKhach` chỉ **sắp xếp các dòng khách hàng**, không sắp xếp phần tử bên trong `maDon`.

Nếu cần sắp xếp list theo thuộc tính node, hãy sắp xếp **những dòng node** bằng `WITH ... ORDER BY ...` trước khi gọi `collect()`. Không dựa vào thứ tự tạo node hoặc thứ tự quét index.

## 7. Quản lý kích thước danh sách: LIMIT phải đặt đúng chỗ

`collect()` có thể đưa rất nhiều giá trị vào **một list trên một nhóm**. Số khách hàng ít không có nghĩa kết quả nhỏ: chỉ một khách hàng có một triệu đơn cũng đủ khiến list ID, node hoặc map lớn.

### 7.1. Cắt list sau collect: ngắn gọn nhưng vẫn phải tạo list đầy đủ

~~~cypher
MATCH (c:Customer)
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
WITH c, o
ORDER BY c.id, o.createdAt DESC, o.id ASC
WITH c, collect(o.id) AS tatCaMaDon
RETURN
  c.id AS maKhach,
  size(tatCaMaDon) AS tongSoDon,
  tatCaMaDon[0..2] AS haiMaDonMoiNhat
ORDER BY maKhach;
~~~

Trong Cypher, lát cắt `[0..2]` lấy các phần tử ở chỉ số `0` và `1`, **không bao gồm vị trí `2`**. Kết quả C01 có `['O104', 'O102']`, C02 có `['O105', 'O103']`, C03 là `[]`.

Cách này thuận tiện với tập nhỏ, nhưng **không giảm số phần tử mà `collect()` phải tạo ra trước khi cắt**. Khi một nhóm quá lớn, việc `collect()` rồi mới lấy lát cắt vẫn có nguy cơ tốn bộ nhớ và thời gian.

### 7.2. LIMIT toàn cục không có nghĩa LIMIT cho mỗi nhóm

Truy vấn dưới đây **chỉ giữ hai dòng đơn trên toàn bộ kết quả**, rồi mới nhóm:

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)
WITH c, o
ORDER BY o.createdAt DESC, o.id ASC
LIMIT 2
RETURN c.id AS maKhach, collect(o.id) AS maDon;
~~~

Với dữ liệu mẫu, hai đơn mới nhất trên **toàn hệ thống** là O105 của C02 và O104 của C01. Cả hai khách có một mã đơn trong kết quả; đây **không phải** hai đơn mới nhất *của mỗi khách*.

Nguyên tắc: nếu `LIMIT` đặt trước `collect()` trên tập dòng chung, nó giới hạn **toàn bộ dòng**, không tự động chia giới hạn theo khóa nhóm.

### 7.3. Giới hạn mỗi nhóm bằng subquery

Để lấy tối đa **hai đơn gần nhất cho từng khách hàng**, cần thực hiện việc sắp xếp và giới hạn **trong phạm vi từng khách**. Có thể dùng `CALL` subquery với cú pháp tương thích nhiều bản Neo4j 5.x:

~~~cypher
MATCH (c:Customer)
CALL {
  WITH c
  OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
  WITH o
  ORDER BY o.createdAt DESC, o.id ASC
  LIMIT 2
  RETURN collect(o.id) AS maDonGanNhat
}
RETURN
  c.id AS maKhach,
  maDonGanNhat
ORDER BY maKhach;
~~~

| maKhach | maDonGanNhat |
|---|---|
| C01 | `['O104', 'O102']` |
| C02 | `['O105', 'O103']` |
| C03 | `[]` |

Subquery được thực hiện theo từng dòng `c` từ truy vấn ngoài. Ở mỗi lần chạy, `LIMIT 2` giới hạn các dòng đơn **trước** khi `collect()` tạo list. Khách không có đơn vẫn được giữ nhờ `OPTIONAL MATCH`, và `collect(null)` tạo `[]`.

Kỹ thuật này **giới hạn số phần tử của list**. Nó không có nghĩa hệ quản trị luôn chỉ cần duyệt đúng hai relationship; muốn biết chi phí lọc và sắp xếp thực tế, hãy kiểm tra `PROFILE`.

Lưu ý về phiên bản: ví dụ dùng cú pháp nhập biến bằng `WITH c` bên trong `CALL { ... }` vốn phổ biến trong Neo4j 5. Một số bản Neo4j mới hơn hỗ trợ cú pháp phạm vi biến `CALL (c) { ... }`. Khi triển khai trong dự án, nên chọn cú pháp phù hợp với phiên bản Cypher thực tế.

### 7.4. Tham số hóa giới hạn

Khi kích thước list phụ thuộc vào yêu cầu từ API, có thể dùng tham số `$maxItems` thay vì viết cố định số 2:

~~~cypher
MATCH (c:Customer {id: $customerId})
CALL {
  WITH c
  OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
  WITH o
  ORDER BY o.createdAt DESC, o.id ASC
  LIMIT $maxItems
  RETURN collect(o {.id, .amount, .createdAt}) AS donGanNhat
}
RETURN c.id AS maKhach, donGanNhat;
~~~

Ứng dụng nên kiểm tra `maxItems` là số nguyên không âm và đặt một **ngưỡng tối đa hợp lý** trước khi gửi truy vấn, ví dụ giới hạn API chỉ trả tối đa 20 hoặc 50 đơn trên một khách. Dùng tham số tránh phải ghép chuỗi Cypher từ dữ liệu nhập của người dùng.

## 8. Khi nào không nên collect: phân trang thay vì trả một list lớn

Có những trường hợp API thực sự cần hiển thị hàng nghìn đơn hàng và người dùng chỉ xem một trang tại một thời điểm. Nếu gom tất cả đơn vào một list lớn rồi trả về Java Driver, ứng dụng phải nhận và giữ toàn bộ kết quả dù giao diện chỉ hiển thị 20 dòng.

Thay vào đó, trả **mỗi đơn một record** và phân trang:

~~~cypher
MATCH (c:Customer {id: $customerId})-[:PLACED]->(o:Order)
RETURN
  o.id AS maDon,
  o.createdAt AS ngayTao,
  o.amount AS giaTri
ORDER BY ngayTao DESC, maDon ASC
SKIP $offset
LIMIT $pageSize;
~~~

Các tham số ví dụ:

~~~json
{
  "customerId": "C01",
  "offset": 0,
  "pageSize": 20
}
~~~

Cách này giới hạn số dòng phải **trả về cho ứng dụng**. Việc dùng `SKIP` sâu vẫn có thể tốn chi phí vì hệ quản trị cần duyệt/bỏ qua các dòng trước đó; khi dữ liệu rất lớn và phải phân trang nhiều, có thể cân nhắc phân trang theo khóa (keyset/cursor) trên cặp thứ tự ổn định như `(createdAt, id)`.

Chọn cách trả dữ liệu theo nhu cầu:

| Nhu cầu | Cách làm phù hợp |
|---|---|
| Chỉ muốn biết có bao nhiêu đơn | `count(o)` |
| Cần danh sách nhỏ có giới hạn | `collect()` sau `LIMIT` theo từng nhóm |
| Muốn tổng hợp vài thuộc tính của mỗi đơn | `collect(o {.id, .amount})` |
| Muốn duyệt một danh sách đơn rất dài | `RETURN` từng record, phân trang |
| Cần một tập sản phẩm duy nhất | `collect(DISTINCT p)` hoặc `collect(DISTINCT p.sku)` |

## 9. Phân tích một số bẫy thường gặp

### 9.1. Nhầm giữa số lượng và độ dài list

~~~cypher
MATCH (c:Customer)
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
RETURN
  c.id AS maKhach,
  count(o) AS soDon,
  size(collect(o.id)) AS kichThuocList
ORDER BY maKhach;
~~~

Trong dữ liệu mẫu, `soDon` và `kichThuocList` bằng nhau. Tuy nhiên, điều này chỉ đúng khi cùng một biểu thức, cùng số dòng và không dùng `DISTINCT` khác nhau. Khi chỉ cần số lượng, `count(o)` rõ ý và thường tiết kiệm bộ nhớ hơn `size(collect(o.id))`.

### 9.2. Nhân bản do nhiều relationship

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)-[:CONTAINS]->(p:Product)
RETURN c.id AS maKhach, collect(o.id) AS maDon
ORDER BY maKhach;
~~~

Với C01, O101 xuất hiện hai lần vì đơn chứa hai loại sản phẩm. Nếu muốn lấy **mỗi đơn một lần**, tốt nhất là gom đơn trước khi mở rộng đến sản phẩm, hoặc dùng `collect(DISTINCT o.id)` khi việc loại trùng đúng với mục tiêu nghiệp vụ.

### 9.3. Cắt list rồi mới đếm làm mất tổng số

~~~cypher
MATCH (c:Customer)
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
WITH c, o
ORDER BY c.id, o.createdAt DESC
WITH c, collect(o.id)[0..2] AS topHai
RETURN c.id AS maKhach, size(topHai) AS soDon;
~~~

Tên `soDon` trong truy vấn này gây hiểu nhầm: `size(topHai)` chỉ đếm số phần tử **sau khi đã cắt**, tối đa bằng 2. Nó không còn là tổng số đơn của khách. Nếu cần cả tổng số đơn và top hai đơn, phải tính riêng `count(o)` ở mức phù hợp hoặc dùng list đầy đủ cho tập nhỏ.

### 9.4. DISTINCT không giữ số lần mua hoặc quantity

Khi một sản phẩm xuất hiện trong nhiều đơn, `collect(DISTINCT p.name)` chỉ trả mỗi tên một lần. Nó không cho biết số lần khách mua sản phẩm, và không đại diện cho tổng số lượng đã mua (`line.quantity`). Chọn phép tổng hợp dựa theo mục đích: **danh sách loại sản phẩm**, **số dòng đơn hàng**, hay **tổng số lượng** là ba đại lượng khác nhau.

### 9.5. Không có ORDER BY thì lấy phần tử đầu tiên là tùy ý

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)
WITH c, collect(o.id) AS dsDon
RETURN c.id AS maKhach, head(dsDon) AS maDonDau;
~~~

`head(dsDon)` có nghĩa phần tử đầu list, **không có nghĩa đơn mới nhất**. Muốn lấy đơn mới nhất, phải sắp xếp theo `o.createdAt DESC` trước bước `collect`, hoặc truy vấn từng khách với `ORDER BY ... LIMIT 1`.

## 10. Kiểm tra hiệu năng và kết quả

Khi gặp query `collect()` chậm hoặc tiêu tốn nhiều bộ nhớ, hãy điều tra hai biến số: **số dòng tạo ra trước phép tổng hợp** và **kích thước list trong từng nhóm**.

Ví dụ kiểm tra kế hoạch cho việc gom mã đơn:

~~~cypher
PROFILE
MATCH (c:Customer)-[:PLACED]->(o:Order)
RETURN c.id AS maKhach, collect(o.id) AS maDon;
~~~

Trong bản kế hoạch thực thi, quan sát số dòng qua các phép mở rộng relationship và toán tử tổng hợp. Không chỉ xem tổng số record trả về: truy vấn có thể trả ba dòng khách hàng nhưng đã phải xử lý hàng triệu dòng đơn.

Một số nguyên tắc vận hành:

1. **Lọc sớm**: dùng khóa khách hàng, điều kiện thời gian, trạng thái đơn hoặc những điều kiện nghiệp vụ phù hợp trước bước gom list.
2. **Giới hạn số phần tử trước khi collect**: dùng subquery theo từng thực thể để có `ORDER BY` và `LIMIT` đúng phạm vi; cắt list sau `collect` không bảo vệ bước gom khỏi dữ liệu quá lớn.
3. **Chỉ lấy trường cần thiết**: gom ID hoặc map projection nhỏ nếu phía ứng dụng không cần toàn bộ node.
4. **Tránh gom dữ liệu chỉ để đếm**: ưu tiên `count()`, `sum()` hoặc hàm tổng hợp số phù hợp.
5. **Kiểm tra tập trung vào nhóm lớn**: độ lớn list có thể phân bố rất lệch giữa các khách hàng. Thử cả khách không có đơn, một đơn và khách nhiều đơn.
6. **Tối ưu truy vấn từ dữ liệu và kế hoạch thật**: index/constraint phù hợp giúp truy tìm điểm xuất phát, nhưng không tự động xóa bỏ chi phí gom hàng trăm nghìn phần tử.

Trong ứng dụng Java Driver hoặc Spring Data Neo4j, tránh xây DTO có list không giới hạn nếu người dùng chỉ cần một trang kết quả. Ngay cả khi Cypher chạy được, ứng dụng còn phải giải mã record và giữ danh sách trong bộ nhớ ở phía Java.

## 11. Bài tập thực hành

### Bài 1. Danh sách ID của mỗi khách, kể cả khách không có đơn

**Yêu cầu:** trả `maKhach`, `soDon`, `dsMaDon`; một dòng cho mỗi khách; danh sách theo ngày mới nhất trước.

<details>
<summary>Lời giải tham khảo</summary>

~~~cypher
MATCH (c:Customer)
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
WITH c, o
ORDER BY c.id, o.createdAt DESC, o.id
RETURN
  c.id AS maKhach,
  count(o) AS soDon,
  collect(o.id) AS dsMaDon
ORDER BY maKhach;
~~~

C03 có `soDon = 0` và `dsMaDon = []`. C01 có `['O104', 'O102', 'O101']`.

</details>

### Bài 2. Danh sách loại sản phẩm đã mua

**Yêu cầu:** với mỗi khách có đơn, chỉ trả một lần cho mỗi loại sản phẩm đã mua; không phụ thuộc số lần xuất hiện của sản phẩm trong các đơn.

<details>
<summary>Lời giải tham khảo</summary>

~~~cypher
MATCH (c:Customer)-[:PLACED]->(:Order)-[:CONTAINS]->(p:Product)
RETURN
  c.id AS maKhach,
  collect(DISTINCT p.name) AS loaiSanPham
ORDER BY maKhach;
~~~

C01 có hai loại `Java` và `Neo4j`; C02 có `Java` và `Cypher`. Thứ tự trong list chưa được bảo đảm.

</details>

### Bài 3. Chỉ lấy một đơn mới nhất theo từng khách

**Yêu cầu:** trả đủ cả C03, mỗi khách có tối đa một mã đơn mới nhất. Không tạo list chứa toàn bộ đơn trước khi cắt.

<details>
<summary>Lời giải tham khảo</summary>

~~~cypher
MATCH (c:Customer)
CALL {
  WITH c
  OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
  WITH o
  ORDER BY o.createdAt DESC, o.id ASC
  LIMIT 1
  RETURN collect(o.id) AS dsMaDon
}
RETURN c.id AS maKhach, dsMaDon
ORDER BY maKhach;
~~~

Kết quả: C01 có `['O104']`, C02 có `['O105']`, C03 có `[]`.

</details>

### Bài 4. Tìm lỗi trong phép gom

Cho truy vấn:

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)-[:CONTAINS]->(p:Product)
RETURN
  c.id AS maKhach,
  size(collect(o.id)) AS soDon;
~~~

**Câu hỏi:** vì sao C01 được đếm thành 4 thay vì 3? Có nên dùng `size(collect(DISTINCT o.id))`?

**Lời giải:** O101 có hai relationship `CONTAINS`, nên `o.id` xuất hiện hai lần. `size(collect(DISTINCT o.id))` sẽ cho 3 với dữ liệu mẫu, nhưng nếu chỉ cần **đếm**, `count(DISTINCT o)` diễn đạt rõ hơn và không phải tạo danh sách ID. Nếu truy vấn chưa cần thông tin sản phẩm, chỉ `MATCH` tới `Order` sẽ đơn giản hơn nữa.

## 12. Ghi nhớ

- `collect(x)` biến nhiều giá trị **khác null** thành một **list trên mỗi nhóm**; `collect(DISTINCT x)` loại phần tử trùng theo giá trị biểu thức `x`.
- Biểu thức không tổng hợp trong `RETURN` hoặc `WITH` xác định **khóa nhóm**. Để giữ khách không có đơn, dùng `OPTIONAL MATCH`; danh sách cho khách đó là `[]`.
- Muốn thứ tự list ổn định, dùng `WITH ... ORDER BY ...` ngay trước bước `collect()`. `ORDER BY` sau phép gom chỉ sắp xếp các dòng kết quả.
- `collect(x)[0..N]` giới hạn **kết quả cuối**, nhưng vẫn phải tạo list trước khi cắt. Để giới hạn từng khách, dùng subquery với `ORDER BY ... LIMIT` **trước `collect()`**.
- `LIMIT` trên tập dòng chung là giới hạn **toàn cục**, không phải giới hạn `N` cho mỗi nhóm.
- Nếu chỉ cần số đếm, dùng `count()`; nếu cần duyệt dữ liệu lớn, trả các record được phân trang thay vì một list không giới hạn.
