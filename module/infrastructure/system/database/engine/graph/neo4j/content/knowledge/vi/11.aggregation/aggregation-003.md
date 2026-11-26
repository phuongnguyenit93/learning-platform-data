# Phân biệt đếm hàng, đếm giá trị khác null và đếm giá trị duy nhất

Trong Neo4j, truy vấn Cypher có thể trả về nhiều dòng do một node khớp với nhiều relationship hoặc nhiều đường đi. Vì vậy, câu hỏi “có bao nhiêu?” cần được làm rõ: **bao nhiêu dòng kết quả**, **bao nhiêu giá trị thật sự tồn tại**, hay **bao nhiêu giá trị khác nhau**?

Ba cách viết cốt lõi là:

- `count(*)`: đếm **tất cả dòng** đi vào phép tổng hợp.
- `count(bieuThuc)`: đếm các dòng có **giá trị biểu thức khác `null`**.
- `count(DISTINCT bieuThuc)`: đếm các **giá trị khác nhau, khác `null`** của biểu thức.

Bài học thuộc chương **Tổng hợp dữ liệu** của module **DATABASE_ENGINE_GRAPH_NEO4J**. Trong mô hình *property graph* (node, relationship và property), việc phân biệt ba phép đếm giúp thống kê đúng khách hàng, đơn hàng, đường liên kết và dữ liệu thiếu trong các truy vấn Cypher; đây cũng là nền tảng để xây báo cáo bằng Java Driver hoặc Spring Data Neo4j.

## 1. Ba phép đếm khác nhau thế nào?

Giả sử một truy vấn tạo ra các dòng với biểu thức `x` nhận lần lượt: `10`, `null`, `10`, `20`, `null`.

| Cách viết | Điều được đếm | Kết quả |
|---|---|---:|
| `count(*)` | Mọi dòng, bất kể giá trị của `x` | 5 |
| `count(x)` | Các dòng có `x` khác `null` | 3 |
| `count(DISTINCT x)` | Các giá trị `x` khác nhau và khác `null`: `10`, `20` | 2 |

Có thể kiểm tra bằng một truy vấn Cypher độc lập, không cần tạo dữ liệu:

~~~cypher
UNWIND [10, null, 10, 20, null] AS x
RETURN
  count(*) AS soDong,
  count(x) AS soGiaTriCoMat,
  count(DISTINCT x) AS soGiaTriKhacNhau;
~~~

Kết quả:

| soDong | soGiaTriCoMat | soGiaTriKhacNhau |
|---:|---:|---:|
| 5 | 3 | 2 |

Ở ví dụ này, **một dòng có `x = null` vẫn là một dòng**. Vì thế `count(*)` giữ cả hai dòng `null`, còn hai cách đếm theo biểu thức bỏ qua chúng.

Một cách tự kiểm tra là viết ra tập dòng trước khi tổng hợp:

~~~text
Dòng   x        count(*)   count(x)   count(DISTINCT x)
1      10          +1         +1         +1 (10 mới)
2      null        +1          -          -
3      10          +1         +1          - (10 đã có)
4      20          +1         +1         +1 (20 mới)
5      null        +1          -          -
Tổng                5          3          2
~~~

Từ đây rút ra hai điểm:

1. `DISTINCT` loại giá trị **trùng theo biểu thức được chọn**, không tự biết đơn vị nghiệp vụ là khách hàng hay đơn hàng.
2. `count(x)` đếm **số lần xuất hiện khác `null`**, không tự gộp những giá trị giống nhau.

## 2. Dữ liệu mẫu để thực hành trên property graph

Xét mô hình cửa hàng sách:

~~~text
(:Customer)-[:PLACED]->(:Order)-[:CONTAINS {quantity}]->(:Product)
~~~

Trong đó `Customer` có `id`, `name`, `email`, `city`; `Order` có `id`, `amount`, `status`; `Product` có `sku`, `name`; quan hệ `CONTAINS` có số lượng `quantity`.

Chạy **một lần** trong cơ sở dữ liệu thực hành trống:

~~~cypher
CREATE
  (c01:Customer {
    id: 'C01', name: 'An',
    email: 'an@example.test', city: 'Ha Noi'
  }),
  (c02:Customer {
    id: 'C02', name: 'Binh',
    email: 'binh@example.test', city: 'Ha Noi'
  }),
  (c03:Customer {
    id: 'C03', name: 'An',
    email: 'an@example.test', city: 'Da Nang'
  }),
  (c04:Customer {id: 'C04', name: 'Chi', city: 'Hue'}),
  (o101:Order {id: 'O101', amount: 120000, status: 'PAID'}),
  (o102:Order {id: 'O102', amount: 120000, status: 'PAID'}),
  (o103:Order {id: 'O103', amount: 200000, status: 'PENDING'}),
  (o104:Order {id: 'O104', amount: 90000, status: 'PAID'}),
  (p01:Product {sku: 'P01', name: 'Java'}),
  (p02:Product {sku: 'P02', name: 'Neo4j'}),
  (c01)-[:PLACED]->(o101),
  (c01)-[:PLACED]->(o102),
  (c02)-[:PLACED]->(o103),
  (c03)-[:PLACED]->(o104),
  (o101)-[:CONTAINS {quantity: 1}]->(p01),
  (o101)-[:CONTAINS {quantity: 2}]->(p02),
  (o102)-[:CONTAINS {quantity: 1}]->(p01),
  (o103)-[:CONTAINS {quantity: 3}]->(p02),
  (o104)-[:CONTAINS {quantity: 1}]->(p01);
~~~

Bộ dữ liệu được thiết kế cố ý để quan sát các trường hợp dễ nhầm:

| Tình huống | Dữ liệu minh họa |
|---|---|
| Khách hàng không có đơn | C04 (Chi) |
| Property bị thiếu | C04 không có `email` |
| Trùng giá trị thuộc tính | C01 và C03 cùng `name = 'An'`, `email = 'an@example.test'` |
| Hai node khác nhau có cùng tiền đơn | O101 và O102 đều có `amount = 120000` |
| Một đơn nối tới nhiều sản phẩm | O101 có hai quan hệ `CONTAINS` |

Việc dùng hai khách hàng cùng email chỉ nhằm thực hành về giá trị trùng, không phải gợi ý cho quy tắc dữ liệu của hệ thống thực tế. Trên dữ liệu mẫu có **4 khách hàng, 4 đơn, 4 quan hệ `PLACED`, 5 quan hệ `CONTAINS`**; tổng giá trị đơn là `530000` VND.

## 3. count(*): đếm số dòng trung gian

Cách đơn giản nhất:

~~~cypher
MATCH (c:Customer)
RETURN count(*) AS soDong;
~~~

Kết quả là `4` vì `MATCH (c:Customer)` tạo một dòng cho mỗi node khách hàng.

Nếu chuyển sang duyệt quan hệ đặt hàng:

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)
RETURN count(*) AS soDong;
~~~

Kết quả vẫn là `4`, nhưng lúc này mỗi dòng là **một lần khớp mẫu khách hàng–đơn hàng**. Hai kết quả bằng nhau chỉ là ngẫu nhiên ở dữ liệu mẫu; chúng có thể khác nhau nếu một khách tạo nhiều đơn hoặc một đơn được liên kết theo mô hình phức tạp hơn.

Tiếp tục mở rộng tới sản phẩm:

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)-[:CONTAINS]->(p:Product)
RETURN count(*) AS soDong;
~~~

Kết quả là `5`, vì O101 khớp hai sản phẩm.

**Kết luận:** `count(*)` **không đồng nghĩa với “đếm node”**. Nó đếm số dòng do toàn bộ phần truy vấn phía trước tạo ra. Nếu một node xuất hiện qua ba mẫu quan hệ, node ấy có thể đóng góp ba dòng.

### 3.1. Đếm relationship theo dòng khớp

~~~cypher
MATCH (o:Order)-[item:CONTAINS]->(p:Product)
RETURN
  count(*) AS soDong,
  count(item) AS soQuanHe;
~~~

Hai giá trị đều là `5` vì trong mẫu này mỗi dòng có một relationship `item` khác `null`. Muốn biết có **bao nhiêu quan hệ khác nhau** khi truy vấn phức tạp có thể làm lặp lại quan hệ, hãy dùng `count(DISTINCT item)` với đúng biến quan hệ.

## 4. count(biểu_thức): chỉ đếm giá trị khác null

Một node tồn tại không có nghĩa mọi property của node đều tồn tại.

~~~cypher
MATCH (c:Customer)
RETURN
  count(*) AS soDong,
  count(c) AS soNode,
  count(c.email) AS soEmailCoMat;
~~~

Kết quả:

| soDong | soNode | soEmailCoMat |
|---:|---:|---:|
| 4 | 4 | 3 |

C04 là node khách hàng hợp lệ, nên được tính vào `count(*)` và `count(c)`. Tuy nhiên C04 không có property `email`, nên `c.email` cho `null` và không đóng góp vào `count(c.email)`.

Trong Neo4j, property không có giá trị thường được biểu diễn bằng **không có property**; việc gán `null` cho property tương đương loại bỏ property. Đối với phép đếm, truy cập property bị thiếu cho giá trị `null`.

### 4.1. count(node) khác count(property)

| Biểu thức | Trả lời câu hỏi |
|---|---|
| `count(c)` | Có bao nhiêu dòng chứa node `c` khác `null`? |
| `count(c.email)` | Có bao nhiêu dòng có giá trị email khác `null`? |
| `count(c.name)` | Có bao nhiêu dòng có tên khác `null`? |
| `count(o)` | Có bao nhiêu dòng chứa node đơn hàng `o`? |
| `count(o.amount)` | Có bao nhiêu dòng có property tiền đơn khác `null`? |

Với dữ liệu mẫu, `count(c.name) = 4` và `count(c.email) = 3`. `count(c.email)` không xác minh email hợp lệ về định dạng, chỉ kiểm tra biểu thức có trả `null` hay không. Chuỗi rỗng `''` vẫn là giá trị khác `null` và sẽ được đếm.

### 4.2. Không đếm số phần tử trong list

`count(x)` đếm **một giá trị biểu thức trên mỗi dòng**. Nếu `x` là một list có nhiều phần tử, cả list vẫn là **một giá trị**, không phải nhiều dòng.

~~~cypher
WITH ['Java', 'Neo4j'] AS tags
RETURN
  count(tags) AS soGiaTriList,
  size(tags) AS soPhanTu;
~~~

Kết quả `soGiaTriList = 1`, `soPhanTu = 2`. Nếu muốn đếm số phần tử sau khi biến list thành nhiều dòng, dùng `UNWIND`:

~~~cypher
WITH ['Java', 'Neo4j'] AS tags
UNWIND tags AS tag
RETURN count(tag) AS soPhanTu;
~~~

Kết quả `2`. Khi viết báo cáo, cần phân biệt **số dòng chứa list** với **số phần tử của list**.

## 5. count(DISTINCT biểu_thức): đếm giá trị duy nhất

Từ tập khách hàng:

~~~cypher
MATCH (c:Customer)
RETURN
  count(c) AS soKhach,
  count(DISTINCT c) AS soNodeKhacNhau,
  count(c.name) AS soTenCoMat,
  count(DISTINCT c.name) AS soTenKhacNhau,
  count(c.email) AS soEmailCoMat,
  count(DISTINCT c.email) AS soEmailKhacNhau;
~~~

Kết quả:

| soKhach | soNodeKhacNhau | soTenCoMat | soTenKhacNhau | soEmailCoMat | soEmailKhacNhau |
|---:|---:|---:|---:|---:|---:|
| 4 | 4 | 4 | 3 | 3 | 2 |

Giải thích:

- `count(DISTINCT c)` phân biệt **danh tính node**; C01 và C03 là hai node khác nhau dù cùng tên và email.
- `count(DISTINCT c.name)` phân biệt **chuỗi tên**: `An`, `Binh`, `Chi` → `3`.
- `count(DISTINCT c.email)` chỉ còn `an@example.test` và `binh@example.test` → `2`. Email thiếu của C04 là `null`, không được đếm.

`DISTINCT` luôn áp dụng lên giá trị của **biểu thức được ghi sau nó**. Với `DISTINCT c`, Neo4j so sánh thực thể node; với `DISTINCT c.email`, Neo4j so sánh giá trị property email.

### 5.1. Đếm thực thể khác với đếm giá trị thuộc tính

Đối với đơn hàng, O101 và O102 là **hai node khác nhau** nhưng có cùng `amount = 120000`:

~~~cypher
MATCH (o:Order)
RETURN
  count(DISTINCT o) AS soDonKhacNhau,
  count(DISTINCT o.id) AS soMaDonKhacNhau,
  count(DISTINCT o.amount) AS soMucTienKhacNhau;
~~~

Kết quả lần lượt là `4`, `4`, `3`.

Không dùng `count(DISTINCT o.amount)` để trả lời câu hỏi “có bao nhiêu đơn hàng?”: biểu thức ấy đếm các **mức giá trị tiền khác nhau**, không đếm đơn. Trong bộ dữ liệu này có ba mức: `90000`, `120000`, `200000`.

Một cảnh báo tương tự khi dùng `sum(DISTINCT o.amount)`: vì O101 và O102 có cùng giá trị, `sum(DISTINCT o.amount) = 410000`, trong khi tổng tiền **bốn đơn** đúng là `530000`. Loại trùng theo giá trị tiền có thể làm mất những đơn hợp lệ.

## 6. OPTIONAL MATCH: trường hợp ba cách đếm chênh lệch rõ nhất

`OPTIONAL MATCH` giữ dòng bên trái khi không tìm thấy mẫu quan hệ tương ứng. Biến thuộc phần không khớp nhận `null` nhưng dòng vẫn tồn tại.

~~~cypher
MATCH (c:Customer)
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
RETURN
  c.id AS maKhach,
  count(*) AS soDong,
  count(o) AS soDon
ORDER BY maKhach;
~~~

Kết quả:

| maKhach | soDong | soDon |
|---|---:|---:|
| C01 | 2 | 2 |
| C02 | 1 | 1 |
| C03 | 1 | 1 |
| C04 | 1 | 0 |

C04 không có đơn hàng, nhưng `OPTIONAL MATCH` tạo một dòng chứa `c = C04` và `o = null`. Vì thế:

- `count(*) = 1` đối với C04 vì có một dòng được giữ lại.
- `count(o) = 0` đối với C04 vì không có node đơn hàng.
- `count(DISTINCT o) = 0` đối với C04 vì không có giá trị đơn hàng khác `null` để đếm.

### 6.1. Đếm toàn bộ dữ liệu sau OPTIONAL MATCH

~~~cypher
MATCH (c:Customer)
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
RETURN
  count(*) AS soDong,
  count(c) AS soLanKhachXuatHien,
  count(DISTINCT c) AS soKhachKhacNhau,
  count(o) AS soDon,
  count(DISTINCT o) AS soDonKhacNhau;
~~~

| soDong | soLanKhachXuatHien | soKhachKhacNhau | soDon | soDonKhacNhau |
|---:|---:|---:|---:|---:|
| 5 | 5 | 4 | 4 | 4 |

C01 có hai đơn nên xuất hiện trên hai dòng; ba khách còn lại mỗi người một dòng. Tổng số dòng là `2 + 1 + 1 + 1 = 5`. `count(c) = 5` **không** có nghĩa cơ sở dữ liệu có năm khách hàng: đó là số lần biến `c` có giá trị trên các dòng.

### 6.2. Đặt WHERE đúng vị trí khi đếm có điều kiện

Ví dụ đếm số đơn đã thanh toán **cho mọi khách, kể cả khách chưa thanh toán**:

~~~cypher
MATCH (c:Customer)
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
WHERE o.status = 'PAID'
RETURN c.id AS maKhach, count(o) AS soDonPaid
ORDER BY maKhach;
~~~

Kết quả: C01 có `2`, C02 có `0`, C03 có `1`, C04 có `0`. `WHERE` gắn với phần `OPTIONAL MATCH` khiến những khách không có đơn phù hợp vẫn được giữ lại.

Ngược lại, nếu đặt điều kiện lọc trên biến `o` **sau một `WITH`**:

~~~cypher
MATCH (c:Customer)
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
WITH c, o
WHERE o.status = 'PAID'
RETURN c.id AS maKhach, count(o) AS soDonPaid
ORDER BY maKhach;
~~~

Các dòng có `o = null` hoặc trạng thái khác `PAID` bị loại ở `WHERE` sau `WITH`, nên C02 và C04 **không xuất hiện** trong báo cáo. Nếu cần giữ nhóm có số đếm 0, kiểm tra vị trí điều kiện lọc và cách dùng `OPTIONAL MATCH`.

## 7. Mức tổng hợp (grouping grain) làm thay đổi ý nghĩa của phép đếm

Trong Cypher, các biểu thức không tổng hợp ở cùng `RETURN` hoặc `WITH` xác định **khóa nhóm ngầm định**. Kết quả của `count()` luôn được tính **riêng cho từng nhóm**.

Ví dụ đếm theo thành phố:

~~~cypher
MATCH (c:Customer)
RETURN
  c.city AS thanhPho,
  count(*) AS soDong,
  count(c.email) AS soEmailCoMat,
  count(DISTINCT c.email) AS soEmailKhacNhau
ORDER BY thanhPho;
~~~

| thanhPho | soDong | soEmailCoMat | soEmailKhacNhau |
|---|---:|---:|---:|
| Da Nang | 1 | 1 | 1 |
| Ha Noi | 2 | 2 | 2 |
| Hue | 1 | 0 | 0 |

Từng nhóm chỉ xét những dòng mang cùng `c.city`. `count(DISTINCT c.email)` ở đây đếm email khác nhau **trong một thành phố**, không phải trên toàn bộ đồ thị.

### 7.1. Nhóm theo tên có thể gộp nhiều khách hàng

~~~cypher
MATCH (c:Customer)
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
RETURN
  c.name AS ten,
  count(c) AS soLanXuatHienKhach,
  count(DISTINCT c) AS soKhachThuc,
  count(o) AS soDon
ORDER BY ten;
~~~

Kết quả:

| ten | soLanXuatHienKhach | soKhachThuc | soDon |
|---|---:|---:|---:|
| An | 3 | 2 | 3 |
| Binh | 1 | 1 | 1 |
| Chi | 1 | 1 | 0 |

Nhóm `An` gồm **C01 và C03**. Vì C01 có hai đơn, `count(c) = 3`, nhưng chỉ có **hai node khách hàng khác nhau**, nên `count(DISTINCT c) = 2`. Nếu mục tiêu là một dòng cho mỗi khách, hãy nhóm theo node `c` hoặc khóa định danh duy nhất:

~~~cypher
MATCH (c:Customer)
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
RETURN
  c.id AS maKhach,
  c.name AS ten,
  count(o) AS soDon
ORDER BY maKhach;
~~~

Phân biệt hai câu hỏi nghiệp vụ:

- “Có bao nhiêu khách hàng khác nhau tên An?” → `count(DISTINCT c)` sau khi lọc hoặc nhóm theo tên.
- “Khách hàng C01 có bao nhiêu đơn?” → nhóm theo `c.id` (hoặc `c`) rồi `count(o)`.

## 8. Khi relationship làm nhân số dòng, DISTINCT có thể cần thiết

Từ mỗi đơn hàng, ta mở rộng tới các sản phẩm:

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)
MATCH (o)-[item:CONTAINS]->(p:Product)
RETURN
  count(*) AS soDongChiTiet,
  count(o) AS soLanDonXuatHien,
  count(DISTINCT o) AS soDonKhacNhau,
  count(item) AS soQuanHeChiTiet,
  count(DISTINCT p) AS soSanPhamKhacNhau;
~~~

| soDongChiTiet | soLanDonXuatHien | soDonKhacNhau | soQuanHeChiTiet | soSanPhamKhacNhau |
|---:|---:|---:|---:|---:|
| 5 | 5 | 4 | 5 | 2 |

O101 có hai relationship `CONTAINS` nên xuất hiện **hai lần**; `count(o)` sẽ đếm cả hai, còn `count(DISTINCT o)` chỉ tính O101 một lần.

Tại đây, mỗi loại đếm trả lời một câu hỏi khác nhau:

| Nhu cầu | Biểu thức phù hợp |
|---|---|
| Tổng dòng chi tiết đã khớp | `count(*)` |
| Tổng số lần đơn xuất hiện trong dòng chi tiết | `count(o)` |
| Tổng số đơn khác nhau có sản phẩm | `count(DISTINCT o)` |
| Số quan hệ dòng chi tiết | `count(item)` |
| Số sản phẩm khác nhau được tham chiếu | `count(DISTINCT p)` |

### 8.1. Không tự ý DISTINCT toàn bộ kết quả

`RETURN DISTINCT c.id, o.status` trả các cặp `(mã khách, trạng thái)` khác nhau. Điều này **không giống** `RETURN c.id, count(DISTINCT o)`, vốn cho số đơn khác nhau theo khách.

Khi báo cáo có nhiều nhánh quan hệ, một thực thể có thể được lặp lại theo từng tổ hợp các nhánh. Đặt `DISTINCT` lên **đúng biến** cần đếm hoặc dùng `WITH` để xác định lại mức tổng hợp trước khi mở rộng thêm.

### 8.2. DISTINCT trong đếm không sửa được mọi phép tổng hợp

~~~cypher
MATCH (o:Order)-[:CONTAINS]->(p:Product)
RETURN
  count(o) AS soLanDon,
  count(DISTINCT o) AS soDonKhacNhau,
  sum(o.amount) AS tongTienTheoDong;
~~~

Kết quả `soLanDon = 5`, `soDonKhacNhau = 4`, nhưng `tongTienTheoDong = 650000` vì O101 bị cộng hai lần. Tổng đúng của bốn đơn là `530000`:

~~~cypher
MATCH (o:Order)
RETURN
  count(o) AS soDon,
  sum(o.amount) AS tongTien;
~~~

Cả `count(DISTINCT o)` lẫn `sum(DISTINCT o.amount)` đều **không tự sửa** các phép tính tổng khác bị nhân dòng. Cần tính chỉ số trên đúng đơn vị nguồn: tổng tiền phải cộng trên từng **đơn**, số lượng sản phẩm phải cộng trên từng **relationship dòng hàng**.

## 9. Đếm khi không có dữ liệu đầu vào

Nếu truy vấn không khớp node nào và không có khóa nhóm, các hàm tổng hợp vẫn trả một dòng giá trị 0:

~~~cypher
MATCH (o:Order)
WHERE o.status = 'CANCELLED'
RETURN
  count(*) AS soDong,
  count(o) AS soDon,
  count(DISTINCT o) AS soDonKhacNhau;
~~~

Kết quả là **một dòng** với cả ba cột bằng `0`.

Tuy nhiên, thêm khóa nhóm `o.status`:

~~~cypher
MATCH (o:Order)
WHERE o.status = 'CANCELLED'
RETURN
  o.status AS trangThai,
  count(*) AS soDong;
~~~

Truy vấn này trả **không dòng nào**, vì không có dòng đầu vào để hình thành một nhóm trạng thái. Phân biệt hai trường hợp quan trọng với ứng dụng Java: nhận một `Record` chứa số 0 khác với nhận danh sách kết quả rỗng.

Một tình huống khác là có dòng đầu vào nhưng giá trị biểu thức đều `null`:

~~~cypher
UNWIND [null, null] AS x
RETURN
  count(*) AS soDong,
  count(x) AS soGiaTri,
  count(DISTINCT x) AS soGiaTriDuyNhat;
~~~

Kết quả là `2`, `0`, `0`. Không nên suy luận `count(x) = 0` đồng nghĩa với không có dòng nào; có thể **tồn tại dòng nhưng thiếu giá trị**.

## 10. Có nên biến null thành một giá trị để đếm không?

Giả sử muốn biết số nhóm email, trong đó “thiếu email” cũng được xem là một nhóm. `count(DISTINCT c.email)` trả `2`, bỏ qua `null`. Có thể chủ động thay `null` bằng một nhãn:

~~~cypher
MATCH (c:Customer)
WITH coalesce(c.email, '(thieu email)') AS nhomEmail
RETURN count(DISTINCT nhomEmail) AS soNhomEmail;
~~~

Kết quả là `3`: email của An, email của Binh và nhóm thiếu email. Nhưng đây là **định nghĩa nghiệp vụ mới**: từ chỗ không đếm giá trị `null` sang chỗ coi dữ liệu thiếu là một nhóm riêng. Chọn nhãn thay thế sao cho không trùng với giá trị thật, hoặc tách nhóm thiếu bằng biểu thức rõ ràng.

Không nên áp dụng `coalesce(x, 0)` một cách tùy tiện. Nếu `0` là giá trị hợp lệ trong dữ liệu, nó có thể làm nhóm thiếu giá trị bị gộp với nhóm mang giá trị 0 thực sự.

## 11. Kiểm tra tính đúng và hiệu năng

Khi thống kê trên một đồ thị lớn, thực hiện lần lượt:

1. **Xác định đơn vị:** muốn đếm đường khớp mẫu, node khách hàng, node đơn hàng, relationship hay giá trị property?
2. **Xác định khả năng null:** `MATCH` hay `OPTIONAL MATCH` có thể tạo biến `null`? Property có thể bị thiếu?
3. **Xác định khả năng lặp:** một node có xuất hiện qua nhiều relationship/đường đi? Có nhiều node khác nhau cùng giá trị property?
4. **Chọn khóa nhóm:** `RETURN c.id, count(o)` là đếm theo khách; `RETURN o.status, count(o)` là đếm theo trạng thái.
5. **So sánh từng loại đếm trên dữ liệu nhỏ:** đặt `count(*)`, `count(o)`, `count(DISTINCT o)` cạnh nhau để nhận ra độ chênh.
6. **Xem kế hoạch chạy:** dùng `EXPLAIN` và `PROFILE` để quan sát truy vấn có nhân nhiều dòng trước bước tổng hợp hay không.

Ví dụ kiểm tra thực tế số dòng trong phép duyệt:

~~~cypher
PROFILE
MATCH (c:Customer)-[:PLACED]->(o:Order)-[:CONTAINS]->(p:Product)
RETURN
  count(*) AS soDong,
  count(DISTINCT o) AS soDon;
~~~

Truy vấn này trả `soDong = 5` và `soDon = 4`. Khi dữ liệu lớn hơn, số dòng đầu vào cho phép tính `DISTINCT` là yếu tố cần quan sát vì loại trùng thường phải lưu/so sánh các giá trị đã gặp. Một số truy vấn đếm rất đơn giản có thể tận dụng cơ chế thống kê của Neo4j; không nên giả định mọi phép `count()` hoặc `count(DISTINCT ...)` đều có cùng hiệu năng. Hãy dựa vào kế hoạch thực thi thay vì suy đoán.

Khi ứng dụng đọc kết quả bằng Java Driver, nên dùng alias có ý nghĩa (`soDong`, `soDon`, `soDonKhacNhau`) và kiểm tra liệu truy vấn trả một dòng hay nhiều nhóm. Khi viết repository method trong Spring Data Neo4j, cần giữ nguyên ý nghĩa của khóa nhóm và kiểu dữ liệu của chỉ số; đổi alias hoặc thay `count(DISTINCT o)` bằng `count(o)` có thể làm báo cáo sai dù truy vấn vẫn chạy.

## 12. Bài tập tự luyện

### Bài 1. Đếm dòng có null

Cho truy vấn:

~~~cypher
UNWIND [1, 1, 2, null, null, 3] AS x
RETURN
  count(*) AS a,
  count(x) AS b,
  count(DISTINCT x) AS c;
~~~

Hãy dự đoán `a`, `b`, `c` trước khi chạy.

**Đáp án:** `a = 6`; `b = 4` (hai giá trị `null` bị bỏ qua); `c = 3` (các giá trị khác nhau là 1, 2, 3).

### Bài 2. Đếm khách có email và email khác nhau

Yêu cầu: dùng bộ dữ liệu mẫu để trả về một dòng gồm tổng khách, khách có email và số email khác nhau.

**Đáp án:**

~~~cypher
MATCH (c:Customer)
RETURN
  count(DISTINCT c) AS tongKhach,
  count(c.email) AS khachCoEmail,
  count(DISTINCT c.email) AS soEmailKhacNhau;
~~~

Kết quả: `4`, `3`, `2`. Nếu một customer có thể xuất hiện nhiều dòng do mở rộng relationship, cần cân nhắc cách xử lý lặp trước khi coi `count(c.email)` là **số khách** có email.

### Bài 3. Đếm đơn của mọi khách, kể cả chưa mua

Yêu cầu: một dòng cho mỗi mã khách và số đơn. C04 phải trả 0.

**Đáp án:**

~~~cypher
MATCH (c:Customer)
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
RETURN
  c.id AS maKhach,
  count(o) AS soDon
ORDER BY maKhach;
~~~

Kết quả theo thứ tự C01, C02, C03, C04: `2`, `1`, `1`, `0`. Nếu đổi thành `count(*)`, C04 sẽ bị tính nhầm là `1`.

### Bài 4. Đếm đơn khác nhau sau khi đi qua sản phẩm

Yêu cầu: đếm số đơn khác nhau có quan hệ `CONTAINS` và số dòng quan hệ sản phẩm.

**Đáp án:**

~~~cypher
MATCH (o:Order)-[:CONTAINS]->(p:Product)
RETURN
  count(*) AS soDongChiTiet,
  count(DISTINCT o) AS soDonKhacNhau;
~~~

Kết quả `5` và `4`. Sự chênh lệch xuất phát từ O101 có hai dòng sản phẩm.

### Bài 5. Tìm lỗi đếm theo tên

Tại sao truy vấn sau không thể dùng để xác định số khách hàng trong hệ thống?

~~~cypher
MATCH (c:Customer)
RETURN count(DISTINCT c.name) AS soKhach;
~~~

**Đáp án:** Nó đếm **số tên khác nhau**, không đếm node khách hàng; C01 và C03 đều tên An sẽ được đếm một lần. Với dữ liệu mẫu kết quả là `3`, trong khi có `4` khách hàng. Dùng `count(DISTINCT c)`, hoặc `count(DISTINCT c.id)` nếu `id` được đảm bảo duy nhất.

## Ghi nhớ

- **`count(*)`**: đếm mọi dòng hiện có tại điểm tổng hợp; dòng có biến `null` vẫn được tính.
- **`count(x)`**: đếm số dòng mà `x` khác `null`; giá trị trùng được tính nhiều lần.
- **`count(DISTINCT x)`**: đếm các giá trị `x` khác nhau và khác `null`.
- **Chọn đúng biểu thức:** `count(DISTINCT o)` đếm node đơn khác nhau; `count(DISTINCT o.amount)` chỉ đếm các mức giá trị tiền khác nhau.
- **Chú ý `OPTIONAL MATCH`:** khách hàng không có đơn vẫn có thể góp một dòng cho `count(*)`, nhưng không góp đơn vào `count(o)`.
- **Chú ý nhân dòng:** mở rộng relationship một-nhiều có thể tăng `count(*)` và `count(o)`; cần xác định đúng đơn vị đếm, khóa nhóm và phạm vi `DISTINCT`.
