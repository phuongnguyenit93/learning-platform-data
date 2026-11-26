# Khóa nhóm ngầm định và cách nhận diện mức tổng hợp

Trong Neo4j, nhiều truy vấn Cypher phải biến hàng loạt node, relationship và đường khớp mẫu thành một báo cáo: số đơn hàng theo khách hàng, doanh thu theo trạng thái hoặc số sản phẩm trong mỗi đơn. Các hàm như `count()`, `sum()`, `avg()`, `min()` và `max()` giúp tổng hợp dữ liệu, nhưng có một quyết định quan trọng hơn cả việc chọn hàm: **mỗi dòng kết quả đại diện cho đối tượng hoặc nhóm nào?**

Khác với SQL thường dùng mệnh đề `GROUP BY`, Cypher suy ra **khóa nhóm ngầm định (implicit grouping key)** từ các biểu thức được chiếu trong `WITH` hoặc `RETURN`. Vì vậy, chỉ cần thêm một property vào `RETURN` là mức tổng hợp có thể thay đổi. Trong hệ thống dùng *property graph*, số đường khớp mẫu trước bước tổng hợp còn có thể tăng khi truy vấn đi qua nhiều relationship.

Bài này tập trung vào cách nhận diện và kiểm soát **mức tổng hợp (aggregation grain)**: một dòng là toàn bộ đồ thị, một trạng thái, một khách hàng, một cặp khách hàng–trạng thái hay một dòng chi tiết sản phẩm.

## 1. Dữ liệu mẫu: quan sát một tập dòng có thể nhân lên

Xét mô hình cửa hàng sách:

~~~text
(:Customer)-[:PLACED]->(:Order)-[:CONTAINS {quantity}]->(:Product)
~~~

`Customer` có `id`, `name`; `Order` có `id`, `amount` (VND), `status`; `Product` có `sku`, `name`; relationship `CONTAINS` có `quantity`.

Tạo bộ dữ liệu trong **cơ sở dữ liệu thực hành trống** (chỉ chạy `CREATE` một lần):

~~~cypher
CREATE
  (c01:Customer {id: 'C01', name: 'An'}),
  (c02:Customer {id: 'C02', name: 'Binh'}),
  (c03:Customer {id: 'C03', name: 'An'}),
  (c04:Customer {id: 'C04', name: 'Chi'}),
  (o101:Order {id: 'O101', amount: 100000, status: 'PAID'}),
  (o102:Order {id: 'O102', amount: 200000, status: 'PAID'}),
  (o103:Order {id: 'O103', amount: 150000, status: 'PENDING'}),
  (o104:Order {id: 'O104', amount: 50000, status: 'PAID'}),
  (p01:Product {sku: 'P01', name: 'Graph'}),
  (p02:Product {sku: 'P02', name: 'Java'}),
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

Bộ dữ liệu có **4 khách hàng, 4 đơn hàng, 5 relationship `CONTAINS`**:

| Mã khách | Tên | Đơn hàng | Tổng giá trị đơn |
|---|---|---|---:|
| C01 | An | O101, O102 | 300000 |
| C02 | Binh | O103 | 150000 |
| C03 | An | O104 | 50000 |
| C04 | Chi | Không có | 0 |

Hai khách hàng khác nhau (C01 và C03) cùng tên `An`. O101 chứa hai sản phẩm nên có **hai dòng** nếu truy vấn từ đơn hàng tới chi tiết sản phẩm. Hai tình huống này giúp kiểm tra đúng hai rủi ro: **gộp nhầm nhóm** và **cộng trùng khi nhân dòng**.

## 2. Khóa nhóm ngầm định là gì?

Trong một phép chiếu có hàm tổng hợp (`WITH` hoặc `RETURN`), có thể hình dung các biểu thức thành hai loại:

1. **Biểu thức tổng hợp:** `count(o)`, `sum(o.amount)`, `avg(o.amount)`... tạo giá trị từ nhiều dòng.
2. **Biểu thức không tổng hợp:** `c`, `c.id`, `c.name`, `o.status`... xác định các **khóa nhóm ngầm định**.

Với mỗi **tổ hợp giá trị khóa nhóm khác nhau**, Cypher trả một dòng tổng hợp. Nếu không có khóa nhóm, toàn bộ tập dòng vào được tổng hợp thành một nhóm chung.

Ví dụ:

~~~cypher
MATCH (o:Order)
RETURN count(o) AS soDon, sum(o.amount) AS tongTien;
~~~

Kết quả:

| soDon | tongTien |
|---:|---:|
| 4 | 500000 |

Không có biểu thức nào ngoài hàm tổng hợp trong `RETURN`, do đó có **một nhóm** và **một dòng kết quả**.

Thêm `o.status`:

~~~cypher
MATCH (o:Order)
RETURN
  o.status AS trangThai,
  count(o) AS soDon,
  sum(o.amount) AS tongTien
ORDER BY trangThai;
~~~

| trangThai | soDon | tongTien |
|---|---:|---:|
| PAID | 3 | 350000 |
| PENDING | 1 | 150000 |

Ở đây `o.status` là khóa nhóm ngầm định. Đơn hàng được chia thành hai nhóm `PAID` và `PENDING`, dù trong truy vấn **không hề viết `GROUP BY`**.

Có thể đọc truy vấn theo cách:

~~~text
MATCH tạo các dòng đầu vào
    ↓
Chọn khóa nhóm từ biểu thức không tổng hợp
    ↓
Gom các dòng có cùng bộ giá trị khóa
    ↓
Tính count/sum/avg... trên từng nhóm
    ↓
RETURN một dòng cho mỗi nhóm
~~~

Cụm `AS trangThai` chỉ đặt tên cột kết quả; không làm mất vai trò khóa nhóm của `o.status`.

## 3. Nhận diện mức tổng hợp bằng số và danh tính khóa nhóm

**Mức tổng hợp** là câu trả lời cho câu hỏi: “Một dòng sau `WITH` hoặc `RETURN` đại diện cho cái gì?”. Hãy nhìn cả **biểu thức không tổng hợp** lẫn **số dòng vào**.

| Khóa nhóm ngầm định | Một dòng đại diện cho | Ví dụ đầu ra |
|---|---|---|
| Không có khóa | Toàn bộ tập đầu vào | 4 đơn hàng |
| `o.status` | Một trạng thái đơn hàng | PAID, PENDING |
| `c` | Một node khách hàng cụ thể | C01, C02, C03, C04 |
| `c.id` | Một mã khách hàng | C01, C02, C03, C04 |
| `c.name` | Một **giá trị tên**, có thể gồm nhiều khách | An, Binh, Chi |
| `c.id` và `o.status` | Một cặp khách hàng–trạng thái | (C01, PAID), (C02, PENDING)... |

### 3.1. Một nhóm cho mỗi khách hàng

~~~cypher
MATCH (c:Customer)
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
RETURN
  c.id AS maKhach,
  c.name AS ten,
  count(o) AS soDon,
  sum(o.amount) AS tongTien
ORDER BY maKhach;
~~~

| maKhach | ten | soDon | tongTien |
|---|---|---:|---:|
| C01 | An | 2 | 300000 |
| C02 | Binh | 1 | 150000 |
| C03 | An | 1 | 50000 |
| C04 | Chi | 0 | 0 |

Các biểu thức `c.id` và `c.name` cùng làm khóa nhóm. Vì `id` trong dữ liệu mẫu là duy nhất, mỗi khách chỉ xuất hiện ở một nhóm. `OPTIONAL MATCH` giữ C04 dù khách đó chưa có đơn nào.

Có thể nhóm trực tiếp theo node:

~~~cypher
MATCH (c:Customer)
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
WITH c, count(o) AS soDon
RETURN c.id AS maKhach, c.name AS ten, soDon
ORDER BY maKhach;
~~~

Ở bước `WITH c, count(o)`, **chính node `c`** là khóa nhóm. Hai node có property `name = 'An'` vẫn là hai node khác nhau, nên không bị gộp.

### 3.2. Nhầm lẫn khi dùng thuộc tính hiển thị làm khóa

Nếu thay mã khách bằng tên:

~~~cypher
MATCH (c:Customer)
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
RETURN
  c.name AS ten,
  count(o) AS soDon,
  sum(o.amount) AS tongTien
ORDER BY ten;
~~~

| ten | soDon | tongTien |
|---|---:|---:|
| An | 3 | 350000 |
| Binh | 1 | 150000 |
| Chi | 0 | 0 |

Đây là truy vấn **đúng nếu muốn gộp theo tên**, nhưng **sai nếu báo cáo cần từng khách hàng**: C01 và C03 đều tên An, nên bị gộp thành một nhóm.

**Nguyên tắc:** muốn một dòng đại diện cho một thực thể, hãy dùng node đó hoặc khóa định danh nghiệp vụ thực sự duy nhất (ví dụ `c.id`). Những thuộc tính mang ý nghĩa hiển thị như tên, nhãn, thành phố có thể không duy nhất.

### 3.3. Thêm một khóa làm mức tổng hợp chi tiết hơn

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)
RETURN
  c.id AS maKhach,
  o.status AS trangThai,
  count(o) AS soDon
ORDER BY maKhach, trangThai;
~~~

Bộ khóa `(c.id, o.status)` xác định **một khách hàng ở một trạng thái**, thay vì toàn bộ đơn của khách. Với dữ liệu mẫu có các nhóm:

| maKhach | trangThai | soDon |
|---|---|---:|
| C01 | PAID | 2 |
| C02 | PENDING | 1 |
| C03 | PAID | 1 |

Nếu chỉ cần tổng số đơn theo trạng thái, hãy bỏ `c.id` khỏi phép chiếu:

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)
RETURN o.status AS trangThai, count(o) AS soDon
ORDER BY trangThai;
~~~

Kết quả trở về hai nhóm: `PAID = 3`, `PENDING = 1`. Việc thêm hoặc bỏ **một khóa nhóm** làm thay đổi câu hỏi mà truy vấn đang trả lời.

## 4. WITH có thể đổi mức tổng hợp ở từng chặng

`WITH` không chỉ truyền dữ liệu giữa các phần của truy vấn. Khi chứa hàm tổng hợp, nó **chốt kết quả ở một mức tổng hợp mới** và chuyển các dòng đã nhóm sang chặng tiếp theo.

### 4.1. Tổng hợp theo khách hàng trước, rồi mới xử lý tiếp

~~~cypher
MATCH (c:Customer)
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
WITH
  c,
  count(o) AS soDon,
  sum(o.amount) AS tongTien
WHERE soDon >= 2
RETURN
  c.id AS maKhach,
  c.name AS ten,
  soDon,
  tongTien;
~~~

`WITH` nhóm theo node `c` và tính `soDon`, `tongTien`. `WHERE` phía sau `WITH` lọc **nhóm đã tính xong**, nên chỉ còn C01 với `soDon = 2`, `tongTien = 300000`.

Lưu ý: sau `WITH c, count(o) AS soDon, ...`, biến `o` không còn được truyền tiếp. Nếu cần dùng `o` ở phần sau, phải thiết kế lại phép chiếu hoặc truy vấn cho phù hợp; đưa `o` vào cùng `WITH` tổng hợp cũng sẽ thay đổi khóa nhóm.

### 4.2. Từ mức khách hàng trở lại mức tên

Có thể cố ý thực hiện **hai cấp tổng hợp**:

~~~cypher
MATCH (c:Customer)
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
WITH c, count(o) AS soDonTheoKhach, sum(o.amount) AS tienTheoKhach
RETURN
  c.name AS ten,
  sum(soDonTheoKhach) AS tongSoDon,
  sum(tienTheoKhach) AS tongTien
ORDER BY ten;
~~~

Chặng thứ nhất: một dòng **mỗi node khách hàng**. Chặng thứ hai: một dòng **mỗi giá trị tên**.

| ten | tongSoDon | tongTien |
|---|---:|---:|
| An | 3 | 350000 |
| Binh | 1 | 150000 |
| Chi | 0 | 0 |

Sử dụng hai chặng là hợp lý khi cần báo cáo tổng hợp từ kết quả đã tính theo thực thể. Tuy nhiên, chỉ gộp theo tên khi đó là chủ đích nghiệp vụ.

### 4.3. Nhóm theo một phân loại được tính toán

Khóa nhóm không nhất thiết là property có sẵn. Có thể tạo một phân loại trước khi tổng hợp:

~~~cypher
MATCH (o:Order)
WITH
  o,
  CASE
    WHEN o.amount >= 150000 THEN 'Tu 150 nghin'
    ELSE 'Duoi 150 nghin'
  END AS nhomGiaTri
RETURN
  nhomGiaTri,
  count(o) AS soDon,
  sum(o.amount) AS tongTien
ORDER BY nhomGiaTri;
~~~

| nhomGiaTri | soDon | tongTien |
|---|---:|---:|
| Duoi 150 nghin | 2 | 150000 |
| Tu 150 nghin | 2 | 350000 |

Ở bước `WITH` chưa có phép tổng hợp nên mỗi đơn vẫn là một dòng. Sang `RETURN`, chỉ `nhomGiaTri` là khóa nhóm; `o` được đưa vào hàm `count(o)` và `sum(o.amount)`.

Nên tách những biểu thức tính toán phức tạp qua `WITH` như trên. Việc trộn trực tiếp hàm tổng hợp vào phép tính có biểu thức không tổng hợp dễ khiến khóa nhóm khó nhận diện và có thể vướng quy tắc **implicit grouping expressions** của phiên bản Cypher đang dùng.

## 5. Số dòng trước khi tổng hợp quyết định kết quả

**Khóa nhóm đúng vẫn chưa đủ** nếu các dòng đầu vào đã nhân lên do duyệt quan hệ.

Xét truy vấn từ khách hàng qua đơn hàng đến sản phẩm:

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)
MATCH (o)-[line:CONTAINS]->(p:Product)
RETURN
  c.id AS maKhach,
  count(o) AS soLanDonXuatHien,
  count(DISTINCT o) AS soDonThuc,
  sum(o.amount) AS tongTienTinhTheoDong,
  sum(line.quantity) AS soLuongSanPham
ORDER BY maKhach;
~~~

| maKhach | soLanDonXuatHien | soDonThuc | tongTienTinhTheoDong | soLuongSanPham |
|---|---:|---:|---:|---:|
| C01 | 3 | 2 | 400000 | 4 |
| C02 | 1 | 1 | 150000 | 3 |
| C03 | 1 | 1 | 50000 | 1 |

O101 của C01 có hai relationship `CONTAINS`, vì vậy giá trị `100000` xuất hiện **hai lần**. `sum(o.amount) = 400000` đang tổng hợp theo **dòng sản phẩm**, trong khi doanh thu thật của C01 chỉ là `300000`.

`count(DISTINCT o)` sửa được **số đơn khác nhau** nhưng không tự sửa `sum(o.amount)`. Đặc biệt, `sum(DISTINCT o.amount)` cũng không phải cách tổng quát để tính doanh thu: nếu hai đơn thực sự có số tiền bằng nhau, hàm đó sẽ gộp nhầm hai giá trị tiền.

### 5.1. Đặt phép tổng hợp tại đúng mức trước khi mở rộng

Tính số đơn và tiền **trước** khi đi tới các dòng sản phẩm:

~~~cypher
MATCH (c:Customer)
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
WITH
  c,
  count(o) AS soDon,
  sum(o.amount) AS tongTien
OPTIONAL MATCH (c)-[:PLACED]->(:Order)-[line:CONTAINS]->(:Product)
RETURN
  c.id AS maKhach,
  c.name AS ten,
  soDon,
  tongTien,
  sum(line.quantity) AS soLuongSanPham
ORDER BY maKhach;
~~~

| maKhach | ten | soDon | tongTien | soLuongSanPham |
|---|---|---:|---:|---:|
| C01 | An | 2 | 300000 | 4 |
| C02 | Binh | 1 | 150000 | 3 |
| C03 | An | 1 | 50000 | 1 |
| C04 | Chi | 0 | 0 | 0 |

Phép `WITH` đầu tiên gom các đơn theo `c`, vì vậy `tongTien` đã được tính đúng và chỉ có một giá trị trên mỗi khách. `OPTIONAL MATCH` tiếp theo có thể nhân dòng theo sản phẩm, nhưng chỉ `line.quantity` cần được cộng tại mức chi tiết đó. Những cột `maKhach`, `ten`, `soDon`, `tongTien` trở thành khóa nhóm ở `RETURN` cuối.

Một cách suy nghĩ hiệu quả là phân biệt **mức của dữ liệu nguồn** (đơn hàng, dòng sản phẩm) và **mức của chỉ số** (số đơn, doanh thu, số lượng bán). Chỉ số nào được tính từ mức nào thì nên tổng hợp trên đúng tập dòng của mức đó.

## 6. OPTIONAL MATCH, null và nhóm rỗng

Với `MATCH` thông thường, khách hàng không có đơn bị loại khỏi tập dòng. `OPTIONAL MATCH` giữ khách đó và gán `null` cho biến không khớp.

~~~cypher
MATCH (c:Customer)
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
RETURN
  c.id AS maKhach,
  count(*) AS soDong,
  count(o) AS soDon
ORDER BY maKhach;
~~~

| maKhach | soDong | soDon |
|---|---:|---:|
| C01 | 2 | 2 |
| C02 | 1 | 1 |
| C03 | 1 | 1 |
| C04 | 1 | 0 |

Tại nhóm C04, `count(*) = 1` vì vẫn có một dòng kết quả từ `OPTIONAL MATCH`; `count(o) = 0` vì không có node đơn hàng. Khi báo cáo số thực thể liên quan, thường cần `count(o)` thay vì `count(*)`.

### 6.1. Khi khóa nhóm là null

~~~cypher
MATCH (c:Customer)
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
RETURN
  o.status AS trangThai,
  count(c) AS soDongKhach,
  count(o) AS soDon
ORDER BY trangThai;
~~~

Bên cạnh `PAID` và `PENDING`, truy vấn còn có nhóm `trangThai = null` đại diện cho những dòng khách hàng không có đơn. Nhóm này có `soDongKhach = 1` và `soDon = 0`.

Điều này không có nghĩa tồn tại một trạng thái đơn hàng tên là `null`: đó là **giá trị thiếu** xuất hiện khi phép nối tùy chọn không khớp. Khi thiết kế báo cáo, cân nhắc có nên giữ nhóm này hay thay bằng nhãn như `'Chua co don'` sau khi đã xác định đúng ý nghĩa.

### 6.2. Không có dòng đầu vào khác với không có nhóm

Hai truy vấn sau sử dụng cùng bộ lọc không khớp đơn nào, nhưng cho hình dạng kết quả khác nhau:

~~~cypher
MATCH (o:Order)
WHERE o.status = 'CANCELLED'
RETURN count(o) AS soDon;
~~~

Trả **một dòng** có `soDon = 0`, vì phép tổng hợp không có khóa nhóm.

~~~cypher
MATCH (o:Order)
WHERE o.status = 'CANCELLED'
RETURN o.status AS trangThai, count(o) AS soDon;
~~~

Trả **không dòng nào**, vì có khóa nhóm `o.status` nhưng không có dòng đầu vào nào để hình thành nhóm. Đây là chi tiết quan trọng khi ứng dụng Java hoặc API mong chờ một dòng chứa số 0.

## 7. WHERE, ORDER BY, DISTINCT có ảnh hưởng gì đến khóa nhóm?

Ba thành phần này dễ bị nhầm với cơ chế nhóm:

| Thành phần | Vai trò | Ghi nhớ |
|---|---|---|
| `WHERE` trước phép tổng hợp | Lọc dòng đầu vào | Có thể làm thay đổi số lượng và tổng tiền của nhóm |
| `WHERE` sau `WITH` tổng hợp | Lọc kết quả nhóm đã tính | Dùng được alias tổng hợp như `soDon` |
| `ORDER BY` | Sắp xếp dòng kết quả | Không tạo khóa nhóm mới |
| `LIMIT` sau tổng hợp | Giữ một số nhóm đầu ra | Không thay đổi cách tính các nhóm được giữ |
| `DISTINCT` | Loại kết quả trùng theo biểu thức được chọn | Không thay thế việc xác định mức tổng hợp |

Ví dụ chỉ xét đơn đã thanh toán:

~~~cypher
MATCH (o:Order)
WHERE o.status = 'PAID'
RETURN count(o) AS soDon, sum(o.amount) AS tongTien;
~~~

Kết quả một nhóm: `soDon = 3`, `tongTien = 350000`. Điều kiện `WHERE` làm giảm tập dòng trước `RETURN`.

Ngược lại, tìm những trạng thái có ít nhất hai đơn:

~~~cypher
MATCH (o:Order)
WITH o.status AS trangThai, count(o) AS soDon
WHERE soDon >= 2
RETURN trangThai, soDon
ORDER BY soDon DESC;
~~~

Đầu tiên nhóm theo trạng thái, sau đó chỉ giữ nhóm `PAID` với `soDon = 3`. `ORDER BY` chỉ sắp xếp các nhóm cuối cùng.

So sánh:

~~~cypher
MATCH (o:Order)
RETURN DISTINCT o.status AS trangThai;
~~~

Truy vấn `DISTINCT` trên trả hai giá trị trạng thái khác nhau nhưng **không tính số đơn**. Muốn thống kê số đơn theo trạng thái, dùng `RETURN o.status, count(o)` với khóa nhóm phù hợp.

## 8. Phương pháp kiểm tra mức tổng hợp trước khi chạy truy vấn

Trước khi tin vào một phép tổng hợp Cypher, hãy trả lời tuần tự năm câu hỏi:

1. **Một dòng báo cáo phải đại diện cho gì?** Ví dụ: một khách hàng, một trạng thái hay một cặp khách hàng–sản phẩm.
2. **Khóa nào định danh mức đó?** Chọn `c` hoặc `c.id` nếu cần phân biệt từng khách; tránh dùng tên trừ khi chủ đích gộp cùng tên.
3. **Mỗi `MATCH` đang tạo bao nhiêu dòng?** Đi qua quan hệ một-nhiều có thể lặp lại node và property của node.
4. **Hàm tổng hợp tính trên đơn vị nào?** `count(o)` đếm lần xuất hiện, `count(DISTINCT o)` đếm node khác nhau, `sum(o.amount)` cộng tiền trên từng dòng nhận được.
5. **Sau mỗi `WITH`, mức dữ liệu có thay đổi không?** Những biểu thức không tổng hợp được mang qua `WITH` có thể là khóa nhóm tại chặng đó.

Có thể kiểm tra số dòng trung gian trước khi viết phép tổng hợp cuối:

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)
MATCH (o)-[line:CONTAINS]->(p:Product)
RETURN
  c.id AS maKhach,
  o.id AS maDon,
  p.sku AS maSanPham,
  o.amount AS giaTriDon,
  line.quantity AS soLuong
ORDER BY maKhach, maDon, maSanPham;
~~~

Ở đây C01 xuất hiện **ba dòng**, không phải hai, bởi O101 có hai sản phẩm. Khi có dữ liệu lớn, dùng `EXPLAIN` để xem kế hoạch dự kiến và `PROFILE` để quan sát số dòng thực tế qua từng toán tử. Chỉ nên kết luận truy vấn hiệu quả sau khi đối chiếu kế hoạch với dữ liệu thực tế.

Để truy vấn dễ bảo trì, nên đặt alias rõ ràng, ví dụ `soDonTheoKhach`, `tongTienTheoDon`, `soDongSanPham`, thay vì dùng mọi chỉ số dưới tên chung `total`. Alias bộc lộ **đơn vị tính** và giúp phát hiện tổng hợp sai mức khi đọc code.

## 9. Bài tập và lời giải tham khảo

### Bài 1. Nhận diện mức tổng hợp

Cho truy vấn:

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)
RETURN
  c.name AS ten,
  o.status AS trangThai,
  count(o) AS soDon;
~~~

Hỏi: một dòng kết quả đại diện cho gì? Với dữ liệu mẫu, có bao nhiêu dòng? Điều gì xảy ra với hai khách cùng tên `An`?

**Lời giải:** Khóa nhóm là `(c.name, o.status)`, tức một **tên–trạng thái**, không phải một khách hàng cụ thể. Có hai dòng: `(An, PAID, 3)` và `(Binh, PENDING, 1)`. Để báo cáo theo từng khách, thay `c.name` bằng `c.id` hoặc nhóm theo node `c` trước bước hiển thị tên.

### Bài 2. Viết lại truy vấn theo đúng đơn vị

Yêu cầu: trả một dòng cho mỗi khách hàng, gồm mã khách, tên, số đơn và đơn lớn nhất; Chi phải xuất hiện với `soDon = 0`, `donLonNhat = null`.

**Lời giải:**

~~~cypher
MATCH (c:Customer)
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
WITH c, count(o) AS soDon, max(o.amount) AS donLonNhat
RETURN
  c.id AS maKhach,
  c.name AS ten,
  soDon,
  donLonNhat
ORDER BY maKhach;
~~~

Kết quả `donLonNhat` của C01/C02/C03/C04 lần lượt là `200000/150000/50000/null`.

### Bài 3. Đọc lỗi nhân dòng

Vì sao truy vấn dưới đây trả tổng tiền của C01 là `400000`?

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)-[:CONTAINS]->(p:Product)
RETURN c.id AS maKhach, sum(o.amount) AS tongTien;
~~~

**Lời giải:** Trong dữ liệu đầu vào, O101 có hai dòng sản phẩm nên giá trị `100000` bị cộng hai lần. Tổng theo khách phải được tính sau khi khớp đến `Order`, **trước khi mở rộng** sang `Product`:

~~~cypher
MATCH (c:Customer)
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
WITH c, sum(o.amount) AS tongTien
RETURN c.id AS maKhach, tongTien
ORDER BY maKhach;
~~~

Kết quả C01 là `300000`, C02 `150000`, C03 `50000`, C04 `0`.

### Bài 4. Phân biệt không có nhóm và nhóm có giá trị 0

Dự đoán số dòng của mỗi truy vấn với `status = 'CANCELLED'` trong dữ liệu mẫu:

~~~cypher
MATCH (o:Order)
WHERE o.status = 'CANCELLED'
RETURN count(o) AS soDon;
~~~

~~~cypher
MATCH (o:Order)
WHERE o.status = 'CANCELLED'
RETURN o.status AS trangThai, count(o) AS soDon;
~~~

**Lời giải:** Truy vấn thứ nhất trả một dòng `soDon = 0`; truy vấn thứ hai trả không dòng nào vì cần khóa `trangThai` để hình thành nhóm.

## 10. Ghi nhớ

- **Khóa nhóm của `RETURN` hoặc `WITH` có tổng hợp được suy ra từ biểu thức không tổng hợp** trong cùng phép chiếu.
- **Một dòng kết quả = một tổ hợp khóa nhóm**; không có khóa nhóm thì toàn bộ đầu vào tạo một nhóm.
- **Tên hiển thị không thay thế khóa định danh**: `c.name` có thể gộp nhiều khách hàng khác nhau; `c` hoặc `c.id` phân biệt được từng khách.
- **Mỗi `WITH` là một cơ hội đổi mức dữ liệu**. Nhóm theo khách, theo trạng thái và theo dòng sản phẩm là những phép tính khác nhau.
- **Số dòng đầu vào quyết định số đếm và tổng**. Duyệt quan hệ một-nhiều có thể làm lặp node; `count(DISTINCT o)` chỉ giải quyết việc đếm node, không tự sửa tổng tiền.
- **`OPTIONAL MATCH` giữ nhóm không có quan hệ**, còn `count(*)` và `count(o)` có thể cho kết quả khác nhau khi `o = null`.
- Trước khi viết `sum()` hay `avg()`, hãy mô tả được bằng một câu: **“Giá trị này được tính trên các dòng đại diện cho đơn vị nào?”**.
