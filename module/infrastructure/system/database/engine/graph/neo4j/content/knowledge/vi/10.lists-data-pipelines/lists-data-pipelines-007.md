# Kết hợp WITH, ORDER BY và LIMIT theo từng giai đoạn xử lý

Trong Neo4j, một truy vấn Cypher thường đi qua nhiều bước: tìm các node và relationship, lọc dữ liệu, chọn một tập bản ghi, tổng hợp rồi trả kết quả. Ba thành phần `WITH`, `ORDER BY` và `LIMIT` giúp kiểm soát **những hàng nào được chuyển sang bước kế tiếp**. Đặt chúng ở giai đoạn khác nhau có thể làm thay đổi cả kết quả, chứ không chỉ thay đổi tốc độ chạy.

Bài học thuộc nhóm **Danh sách và luồng dữ liệu**, tập trung vào cách xử lý luồng hàng trong Cypher trên property graph của Neo4j. Sau khi học, bạn có thể:

- Phân biệt vai trò của `WITH`, `ORDER BY` và `LIMIT`, cũng như phạm vi biến sau mỗi `WITH`.
- Chọn đúng vị trí áp dụng `LIMIT` trước hoặc sau khi tổng hợp.
- Viết chuỗi nhiều giai đoạn lấy top-N, phân trang và top-N theo từng nhóm.
- Nhận diện lỗi kết quả không ổn định và các điểm cần xem trong kế hoạch thực thi.

## 1. Ba thành phần tác động đến luồng dữ liệu như thế nào?

| Thành phần | Vai trò | Điều cần nhớ |
| --- | --- | --- |
| `WITH` | Chuyển kết quả trung gian sang giai đoạn tiếp theo; chọn biến, tính biểu thức, `DISTINCT` hoặc tổng hợp. | Biến không được đưa qua `WITH` sẽ ra khỏi phạm vi sử dụng của các mệnh đề sau. |
| `ORDER BY` | Sắp xếp hàng theo một hoặc nhiều khóa, tăng dần (`ASC`) hoặc giảm dần (`DESC`). | Khi cần chọn top-N có nghĩa nghiệp vụ rõ ràng, hãy xác định thứ tự **trước** `LIMIT`. |
| `LIMIT` | Giữ tối đa N hàng ở vị trí xuất hiện. | `LIMIT` trong `WITH` giới hạn đầu vào của bước tiếp theo; `LIMIT` trong `RETURN` giới hạn kết quả trả về. |

Một mẫu thường dùng:

~~~cypher
MATCH (o:Order)
WHERE o.status = 'PAID'
WITH o
ORDER BY o.createdAt DESC, o.id ASC
LIMIT 10
RETURN o.id AS maDon, o.createdAt AS ngayTao
ORDER BY ngayTao DESC, maDon ASC;
~~~

Đọc từ trên xuống: tìm đơn đã thanh toán → xếp theo mới nhất, dùng mã đơn để phá hòa → chỉ chuyển 10 đơn đầu tiên sang `RETURN` → xuất kết quả theo thứ tự xác định. Ví dụ giả định `o.id` là duy nhất và `o.createdAt` có cùng kiểu dữ liệu thời gian. Hai biểu thức sắp xếp trong `RETURN` được ghi rõ để thứ tự hiển thị không phụ thuộc vào những thay đổi sau này của truy vấn.

**Phân biệt hai phạm vi giới hạn:**

~~~cypher
// Giới hạn trước khi tổng hợp: chỉ tính trên 10 đơn mới nhất.
MATCH (o:Order)
WITH o ORDER BY o.createdAt DESC, o.id ASC LIMIT 10
RETURN count(*) AS soDon, sum(o.total) AS tongTien;
~~~

~~~cypher
// Tổng hợp mọi đơn, rồi chỉ trả về tối đa 10 nhóm.
MATCH (o:Order)
WITH o.status AS trangThai, count(*) AS soDon, sum(o.total) AS tongTien
RETURN trangThai, soDon, tongTien
ORDER BY soDon DESC, trangThai ASC
LIMIT 10;
~~~

Truy vấn thứ nhất tổng hợp **10 hàng đã chọn**; truy vấn thứ hai tổng hợp **toàn bộ hàng phù hợp**, rồi lấy tối đa 10 nhóm trạng thái. Không thể thay vị trí `LIMIT` tùy ý mà giữ nguyên ý nghĩa.

## 2. Ví dụ chạy độc lập: chọn ba bản ghi đứng đầu

Để thử ngay trong Neo4j Browser mà không cần tạo dữ liệu, dùng `UNWIND` biến một danh sách giả lập thành các hàng:

~~~cypher
UNWIND [
  {ma: 'O01', khach: 'An',   soTien: 120},
  {ma: 'O02', khach: 'Binh', soTien: 300},
  {ma: 'O03', khach: 'An',   soTien: 300},
  {ma: 'O04', khach: 'Chi',  soTien: 90},
  {ma: 'O05', khach: 'Binh', soTien: 160},
  {ma: 'O06', khach: 'Chi',  soTien: 200}
] AS don
WITH don
ORDER BY don.soTien DESC, don.ma ASC
LIMIT 3
RETURN don.ma AS maDon, don.khach AS khach, don.soTien AS soTien
ORDER BY soTien DESC, maDon ASC;
~~~

Kết quả dự kiến:

| maDon | khach | soTien |
| --- | --- | ---: |
| O02 | Binh | 300 |
| O03 | An | 300 |
| O06 | Chi | 200 |

Hai đơn O02 và O03 cùng có `soTien = 300`. Khóa phụ `don.ma ASC` làm thứ tự giữa hai đơn trở nên xác định. `UNWIND` tự nó không bảo đảm thứ tự đầu ra; không nên dựa vào thứ tự phần tử ban đầu khi dùng `LIMIT`.

Một cách hình dung luồng xử lý:

~~~text
UNWIND (6 hàng)
    |
    v
WITH don + ORDER BY soTien DESC, ma ASC (6 hàng đã xếp thứ tự)
    |
    v
LIMIT 3 (chỉ còn O02, O03, O06)
    |
    v
RETURN ... ORDER BY ... (3 hàng được hiển thị)
~~~

**Lưu ý:** `LIMIT 3` nghĩa là “tối đa ba hàng”, không có nghĩa “mọi hàng cùng hạng với hàng thứ ba”. Nếu cần giữ tất cả các trường hợp đồng hạng, phải xác định ngưỡng hoặc áp dụng cách xếp hạng phù hợp với yêu cầu nghiệp vụ.

## 3. WITH tạo ranh giới giai đoạn và phạm vi biến

Mỗi `WITH` xác định những giá trị được mang tiếp. Nó cũng là nơi hợp lý để đổi tên cột và tạo kết quả trung gian từ nhiều hàng của đồ thị.

Giả sử mô hình dữ liệu gồm `(:Customer {id})-[:PLACED]->(:Order {id, total, createdAt, status})`. Đoạn truy vấn dưới đây tính doanh thu theo khách từ các đơn đã thanh toán, xếp hạng rồi lấy năm khách đầu:

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)
WHERE o.status = 'PAID'
WITH c.id AS maKhach, o.total AS giaTri
WITH maKhach, count(*) AS soDon, sum(giaTri) AS tongTien
ORDER BY tongTien DESC, maKhach ASC
LIMIT 5
RETURN maKhach, soDon, tongTien
ORDER BY tongTien DESC, maKhach ASC;
~~~

Ở `WITH` đầu, chỉ `maKhach` và `giaTri` còn được dùng ở các bước kế tiếp. `WITH` thứ hai nhóm theo `maKhach`, tính số đơn và tổng tiền; `ORDER BY ... LIMIT 5` vì thế chọn **năm khách có doanh thu cao nhất**, chứ không chọn năm đơn hàng đắt nhất. Nếu các đơn có `total = null`, `count(*)` vẫn đếm hàng đó còn `sum(giaTri)` bỏ qua giá trị null; cần xác định quy tắc làm sạch dữ liệu khi sử dụng số liệu thực tế.

Ví dụ sai về phạm vi biến:

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)
WITH c.id AS maKhach
RETURN maKhach, o.total AS giaTri; // Lỗi: o đã ra khỏi phạm vi.
~~~

Cách sửa là chuyển tiếp biến cần dùng (chẳng hạn `WITH c.id AS maKhach, o.total AS giaTri`) hoặc tính giá trị cần thiết ngay tại `WITH`. Tránh mang theo mọi biến không cần thiết vì sẽ khó biết chính xác giai đoạn đang xử lý những gì.

## 4. Ghép nhiều giai đoạn: top 100 đơn, rồi top 5 khách

Bài toán: **Trong 100 đơn đã thanh toán mới nhất trên toàn hệ thống, tìm năm khách có tổng giá trị đơn lớn nhất.** Đây là ví dụ mà giới hạn ở hai giai đoạn có ý nghĩa khác nhau.

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)
WHERE o.status = 'PAID'
WITH c, o
ORDER BY o.createdAt DESC, o.id ASC
LIMIT 100

WITH c.id AS maKhach, count(*) AS soDon, sum(o.total) AS tongTien
ORDER BY tongTien DESC, maKhach ASC
LIMIT 5

RETURN maKhach, soDon, tongTien
ORDER BY tongTien DESC, maKhach ASC;
~~~

| Giai đoạn | Đầu ra chuyển tiếp | Ý nghĩa |
| --- | --- | --- |
| `MATCH` và `WHERE` | Các cặp khách–đơn đã thanh toán | Tập dữ liệu ban đầu theo điều kiện lọc. |
| `WITH c, o ORDER BY ... LIMIT 100` | Tối đa 100 cặp, ưu tiên đơn mới nhất | Giới hạn **toàn hệ thống** trước khi nhóm. |
| `WITH c.id, count, sum ...` | Mỗi khách một hàng | Tính số lượng và doanh thu chỉ từ tối đa 100 đơn trên. |
| `ORDER BY tongTien ... LIMIT 5` | Tối đa năm khách | Xếp hạng sau khi đã tổng hợp. |
| `RETURN ... ORDER BY ...` | Kết quả cuối | Hiển thị cùng tiêu chí xếp hạng. |

Nếu yêu cầu đổi thành “năm khách có doanh thu lớn nhất **trên tất cả** đơn đã thanh toán”, phải bỏ `LIMIT 100` ở giai đoạn đầu. Nếu yêu cầu là “100 đơn mới nhất **của mỗi khách**”, `LIMIT 100` hiện tại cũng không đáp ứng vì nó giới hạn toàn cục; xem cách làm theo nhóm ở mục 6.

## 5. Giới hạn trước hay sau tổng hợp: một thay đổi, hai kết quả

Xét tập điểm minh họa có năm hàng. Đây là hai truy vấn độc lập, có thể chạy trực tiếp.

**Trường hợp A — Lấy hai hàng điểm cao nhất rồi mới cộng theo nhóm:**

~~~cypher
UNWIND [
  {ma: 'A1', nhom: 'A', diem: 100},
  {ma: 'A2', nhom: 'A', diem: 50},
  {ma: 'B1', nhom: 'B', diem: 90},
  {ma: 'B2', nhom: 'B', diem: 90},
  {ma: 'C1', nhom: 'C', diem: 85}
] AS x
WITH x
ORDER BY x.diem DESC, x.ma ASC
LIMIT 2
WITH x.nhom AS nhom, sum(x.diem) AS tongDiem
RETURN nhom, tongDiem
ORDER BY tongDiem DESC, nhom ASC;
~~~

Kết quả: nhóm A = 100 và nhóm B = 90. Chỉ A1 và B1 vượt qua `LIMIT 2`, nên những hàng còn lại không góp vào tổng.

**Trường hợp B — Cộng toàn bộ điểm theo nhóm rồi chọn hai nhóm có tổng cao nhất:**

~~~cypher
UNWIND [
  {ma: 'A1', nhom: 'A', diem: 100},
  {ma: 'A2', nhom: 'A', diem: 50},
  {ma: 'B1', nhom: 'B', diem: 90},
  {ma: 'B2', nhom: 'B', diem: 90},
  {ma: 'C1', nhom: 'C', diem: 85}
] AS x
WITH x.nhom AS nhom, sum(x.diem) AS tongDiem
ORDER BY tongDiem DESC, nhom ASC
LIMIT 2
RETURN nhom, tongDiem
ORDER BY tongDiem DESC, nhom ASC;
~~~

Kết quả: nhóm B = 180, nhóm A = 150. Ở đây `LIMIT 2` chọn hai **nhóm**, sau khi đã tính tổng từ cả năm hàng.

| Câu hỏi nghiệp vụ | Nơi đặt giới hạn |
| --- | --- |
| “Tổng giá trị của 20 đơn mới nhất là bao nhiêu?” | `ORDER BY` thời gian và `LIMIT 20` **trước** `sum()`. |
| “20 khách có tổng doanh thu cao nhất là ai?” | `sum()` theo khách **trước**, rồi `ORDER BY` doanh thu và `LIMIT 20`. |
| “Những đơn mới nhất trong 20 khách có doanh thu cao nhất?” | Xếp hạng, giới hạn khách trước; sau đó lấy đơn của tập khách đã chọn và xếp/giới hạn theo yêu cầu mới. |

## 6. Top-N toàn cục khác top-N theo từng nhóm

Mệnh đề:

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)
WITH c, o
ORDER BY o.createdAt DESC, o.id ASC
LIMIT 3
RETURN c.id AS maKhach, o.id AS maDon;
~~~

chỉ lấy **ba đơn mới nhất trên toàn bộ các khách**. Nó không lấy ba đơn cho mỗi khách.

Để lấy tối đa ba đơn đã thanh toán mới nhất **của từng khách**, có thể sắp xếp trước khi `collect()`, sau đó cắt danh sách theo nhóm:

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)
WHERE o.status = 'PAID'
WITH c, o
ORDER BY c.id ASC, o.createdAt DESC, o.id ASC
WITH c, collect(o)[..3] AS baDonMoiNhat
UNWIND baDonMoiNhat AS o
RETURN c.id AS maKhach, o.id AS maDon, o.createdAt AS ngayTao
ORDER BY maKhach ASC, ngayTao DESC, maDon ASC;
~~~

`WITH ... ORDER BY` bảo đảm thứ tự hàng đưa **trực tiếp** vào mệnh đề `WITH` tiếp theo, nên các phần tử được `collect(o)` gom theo mỗi khách tuân theo thứ tự đã xếp. Cú pháp `[..3]` lấy tối đa ba phần tử đầu danh sách; khách có một hoặc hai đơn thì chỉ có tương ứng một hoặc hai kết quả. Cách này phải gom các đơn của từng khách thành danh sách trước khi cắt, nên có thể tốn bộ nhớ nếu mỗi khách có rất nhiều đơn.

Khi số đơn lớn, có thể đặt `ORDER BY ... LIMIT` bên trong **subquery chạy theo từng khách**. Với phiên bản Neo4j hỗ trợ cú pháp nhập biến `CALL (c) { ... }`:

~~~cypher
MATCH (c:Customer)
CALL (c) {
  MATCH (c)-[:PLACED]->(o:Order)
  WHERE o.status = 'PAID'
  RETURN o.id AS maDon, o.createdAt AS ngayTao
  ORDER BY ngayTao DESC, maDon ASC
  LIMIT 3
}
RETURN c.id AS maKhach, maDon, ngayTao
ORDER BY maKhach ASC, ngayTao DESC, maDon ASC;
~~~

Trong ví dụ này, giới hạn ba hàng áp dụng **cho mỗi lần thực thi subquery với một khách**, và khách không có đơn phù hợp không xuất hiện ở kết quả. Cú pháp trên thuộc các phiên bản Neo4j 5 hỗ trợ variable scope clause của `CALL` (từ Neo4j 5.23); với bản cũ hơn, dùng dạng `CALL { WITH c ... }` phù hợp phiên bản đó. Hiệu năng thực tế còn phụ thuộc chỉ mục và kế hoạch thực thi.

## 7. Phân trang: luôn có thứ tự ổn định

Ví dụ trang kết quả các đơn đã thanh toán:

~~~cypher
MATCH (o:Order)
WHERE o.status = 'PAID'
RETURN o.id AS maDon, o.createdAt AS ngayTao, o.total AS giaTri
ORDER BY ngayTao DESC, maDon ASC
SKIP $offset
LIMIT $pageSize;
~~~

Với `$offset = 0` và `$pageSize = 20`, truy vấn lấy tối đa 20 hàng đầu; trang kế tiếp dùng `$offset = 20`. Tham số phân trang phải là số nguyên không âm; mã đơn là khóa phụ duy nhất để các bản ghi cùng thời điểm vẫn có thứ tự rõ ràng.

Phân trang bằng `SKIP` có thể tốn chi phí khi bỏ qua nhiều hàng. Khi dữ liệu thay đổi giữa hai lần gọi, các trang có thể lặp hoặc thiếu bản ghi dù thứ tự xác định. Với danh sách lớn và cập nhật liên tục, cân nhắc phân trang theo khóa (keyset/cursor) dựa trên cặp `(createdAt, id)` của hàng cuối trang trước. Nếu điều kiện sắp xếp thay đổi, điều kiện cursor cũng phải thay đổi tương ứng.

## 8. Các lỗi thường gặp và cách tự kiểm tra

| Dấu hiệu | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `LIMIT 10` trả về các hàng khác nhau giữa các lần chạy | Thiếu `ORDER BY` hoặc có quá nhiều giá trị đồng hạng | Thêm thứ tự rõ ràng; dùng khóa phụ duy nhất nếu cần tính xác định. |
| Tổng doanh thu nhỏ bất thường | Giới hạn số đơn trước khi `sum()` dù muốn tính tất cả đơn | Chuyển `LIMIT` về sau bước tổng hợp. |
| Cypher báo biến chưa được định nghĩa | `WITH` trước đó đã bỏ biến | Mang biến/bí danh cần dùng qua `WITH` hoặc tính trước. |
| Muốn ba bản ghi cho mỗi nhóm nhưng chỉ nhận ba bản ghi tổng cộng | `LIMIT` đặt ở luồng chung | Dùng tập hợp theo nhóm hoặc subquery có giới hạn cho mỗi nhóm. |
| Thứ tự hiển thị không đúng sau các bước xử lý bổ sung | Dựa vào thứ tự từ bước trung gian | Đặt `ORDER BY` tại `RETURN` cuối. |
| Top-N không đúng khi dữ liệu thiếu hoặc sai kiểu | Khóa sắp xếp có `null`, số lưu dưới dạng chuỗi, hoặc kiểu thời gian không nhất quán | Chuẩn hóa thuộc tính; quy định xử lý `null`, có thể dùng `coalesce()` khi thích hợp. |
| Truy vấn chậm dù `LIMIT` nhỏ | Cần đọc, nhóm hoặc sắp xếp nhiều hàng trước khi biết top-N | Xem `PROFILE`, điều kiện lọc, mô hình đồ thị và chỉ mục phù hợp. |

Một số quy tắc thực hành:

1. Viết yêu cầu nghiệp vụ bằng lời: “top-N của **hàng nào**, xét trên **tập nào**, tính theo **khóa nào**?”. Sau đó mới chọn vị trí `WITH` và `LIMIT`.
2. Đặt khóa sắp xếp quan trọng nhất trước, thêm khóa phụ để phá hòa. Với giá trị `null`, xác định trước cách xếp hạng; `coalesce(o.total, 0)` chỉ phù hợp nếu nghiệp vụ thật sự xem thiếu giá trị như bằng 0.
3. Sau mỗi `WITH`, xem lại những biến còn tồn tại và số hàng dự kiến. Các bước `DISTINCT`, `count()`, `sum()` hoặc `collect()` có thể làm thay đổi số hàng.
4. Nếu có `ORDER BY` trên kết quả tổng hợp, ưu tiên sắp xếp theo bí danh đã tính, ví dụ `WITH c.id AS maKhach, sum(o.total) AS tongTien ORDER BY tongTien DESC`.
5. Dùng `$topN`, `$offset` và `$pageSize` làm tham số được kiểm tra kiểu và miền giá trị từ ứng dụng thay vì nối chuỗi Cypher thủ công.

## 9. Hiệu năng: LIMIT không bảo đảm truy vấn chỉ đọc N hàng

`LIMIT` giới hạn **số hàng đầu ra của giai đoạn**, nhưng những toán tử đứng trước nó có thể đã quét đồ thị, kết hợp hàng, tổng hợp hoặc sắp xếp một lượng dữ liệu lớn. Nếu cần lấy top-N theo một thuộc tính, một kế hoạch có thể tận dụng cấu trúc chỉ mục hoặc toán tử top-N, nhưng không nên giả định luôn có tối ưu này.

Để kiểm tra, chạy `EXPLAIN` (chỉ xem kế hoạch) hoặc `PROFILE` (thực thi và đo) trên truy vấn đọc:

~~~cypher
PROFILE
MATCH (o:Order)
WHERE o.status = 'PAID'
WITH o
ORDER BY o.createdAt DESC, o.id ASC
LIMIT $topN
RETURN o.id AS maDon, o.createdAt AS ngayTao
ORDER BY ngayTao DESC, maDon ASC;
~~~

Quan sát số `Rows`, `DB Hits` và các toán tử như `Sort`, `Top`, `NodeIndexSeek`/`NodeIndexScan` (tên và cách hiển thị tùy phiên bản/kế hoạch). Chỉ mục phù hợp với bộ lọc `status` và khóa thời gian `createdAt` có thể giúp ích, nhưng cần xác nhận qua kế hoạch thực tế, đặc biệt khi còn khóa phá hòa `id`. Đừng đẩy `LIMIT` lên sớm chỉ để giảm chi phí nếu việc đó làm sai tập dữ liệu cần tổng hợp.

## 10. Tự luyện theo giai đoạn

Trên mô hình `Customer`–`PLACED`–`Order` đã giới thiệu, hãy tự xác định **giai đoạn đặt giới hạn** trước khi viết mã:

1. Tìm **10 đơn có giá trị cao nhất** trong tất cả đơn đã thanh toán. Cần sắp xếp theo `o.total DESC`, phá hòa bằng `o.id ASC`, rồi giới hạn ngay trước kết quả trả về.
2. Tìm **10 khách mua nhiều đơn nhất**. Cần `count(*)` theo khách trước, rồi sắp xếp theo số đơn và giới hạn ở mức khách.
3. Tìm **hai đơn mới nhất của mỗi khách**. `LIMIT 2` ở mức toàn cục là sai; cần giới hạn theo nhóm như mục 6.

Gợi ý lời giải cho câu 2:

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)
WHERE o.status = 'PAID'
WITH c.id AS maKhach, count(*) AS soDon
ORDER BY soDon DESC, maKhach ASC
LIMIT 10
RETURN maKhach, soDon
ORDER BY soDon DESC, maKhach ASC;
~~~

Điểm cốt lõi là mỗi `WITH` tạo ra một **ranh giới dữ liệu trung gian**. Hãy quyết định đúng thứ tự “lọc → sắp xếp → giới hạn → tổng hợp” hoặc “lọc → tổng hợp → sắp xếp → giới hạn” theo câu hỏi thực tế; từ đó mới tối ưu bằng kế hoạch thực thi của Neo4j.
