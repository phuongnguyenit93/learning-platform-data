# Hàm kiểm tra nhãn, loại quan hệ và thuộc tính thực thể trong Neo4j Cypher

## 1. Vì sao cần kiểm tra cấu trúc của thực thể?

Trong **property graph** của Neo4j, một **node** có thể mang nhiều **label** (nhãn), một **relationship** có đúng một **type** (loại quan hệ), và cả node lẫn relationship đều có thể chứa các **property** dưới dạng cặp `key: value`. Khi truy vấn bằng Cypher, ta thường phải trả lời những câu hỏi như:

- Node này có nhãn `Person`, `Actor` hay đồng thời cả hai?
- Một liên kết giữa người và phim là `ACTED_IN` hay `DIRECTED`?
- Thực thể hiện có những thuộc tính nào; thuộc tính `birthYear` hoặc `role` có tồn tại không?
- Có thể kiểm tra cấu trúc dữ liệu mà không phải biết trước tất cả tên thuộc tính hay không?

Những phép kiểm tra này hữu ích khi dữ liệu không đồng nhất, khi nhập dữ liệu từ nhiều nguồn, khi viết truy vấn kiểm tra chất lượng dữ liệu hoặc khi xây dựng ứng dụng dùng **Neo4j Java Driver** và **Spring Data Neo4j**. Nội dung dưới đây tập trung vào các biểu thức và hàm Cypher: `labels()`, `type()`, `keys()`, `properties()`, truy cập thuộc tính và `IS NULL` / `IS NOT NULL`.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt label của node, type của relationship và property của thực thể.
2. Dùng `labels(n)` và biểu thức nhãn để phân loại node; dùng `type(r)` để phân loại quan hệ.
3. Dùng `keys()`, `properties()` và truy cập thuộc tính động để khám phá dữ liệu.
4. Kiểm tra sự có mặt của thuộc tính bằng `IS NOT NULL` và nhận biết ngữ nghĩa của `null`.
5. Lựa chọn biểu thức phù hợp khi tối ưu truy vấn Cypher.

## 2. Chuẩn bị đồ thị ví dụ

Giả sử ứng dụng lưu thông tin người tham gia sản xuất phim. Một người có thể vừa là `Person` vừa là `Actor` hoặc `Director`; một phim là `Movie`. Các quan hệ có thể có thuộc tính riêng.

```text
(an:Person:Actor {personId, name, birthYear})
     |
     +--[:ACTED_IN {role, screenTime}]-->(phim:Movie {movieId, title, year})
                                              ^
                                              |
                                 [:DIRECTED]--+
                                              |
                          (binh:Person:Director {personId, name})
```

Tạo dữ liệu minh họa bằng Cypher:

```cypher
MERGE (an:Person {personId: 'p-001'})
SET an:Actor, an.name = 'An', an.birthYear = 1993
MERGE (binh:Person {personId: 'p-002'})
SET binh:Director, binh.name = 'Bình'
MERGE (phim:Movie {movieId: 'm-001'})
SET phim.title = 'Mùa hạ', phim.year = 2024
MERGE (an)-[vai:ACTED_IN]->(phim)
SET vai.role = 'Lan', vai.screenTime = 42
MERGE (binh)-[:DIRECTED]->(phim);
```

`MERGE` giúp có thể chạy lại ví dụ để cập nhật các thực thể đã khớp mẫu. Trong ứng dụng thực tế, nên tạo **unique constraint** cho định danh nghiệp vụ như `Person.personId` và `Movie.movieId` để bảo đảm tính duy nhất khi ghi dữ liệu đồng thời.

| Thành phần | Cú pháp minh họa | Ý nghĩa |
| --- | --- | --- |
| Nhãn của node | `:Person`, `:Actor` | Một node có thể mang nhiều nhãn. |
| Loại quan hệ | `:ACTED_IN` | Một relationship có một loại duy nhất. |
| Thuộc tính node | `an.birthYear` | Giá trị được lưu trực tiếp trên node. |
| Thuộc tính quan hệ | `vai.role` | Giá trị được lưu trực tiếp trên relationship. |

**Chú ý:** `Actor` là nhãn, không phải thuộc tính `an.Actor`; `ACTED_IN` là loại quan hệ, không phải thuộc tính `vai.type`. Đó là ba thành phần khác nhau của property graph.

## 3. Kiểm tra nhãn của node với `labels()`

### 3.1. `labels(node)` trả về điều gì?

`labels(n)` trả về **danh sách chuỗi** chứa các nhãn của node `n`. Một node không có nhãn cho kết quả là danh sách rỗng `[]`; đầu vào `null` cho kết quả `null`. Thứ tự phần tử trong danh sách nhãn **không được bảo đảm**, vì vậy không nên dựa vào `labels(n)[0]` để xác định «nhãn chính».

```cypher
MATCH (p:Person)
RETURN p.name AS ten,
       labels(p) AS danhSachNhan
ORDER BY ten;
```

Với dữ liệu ví dụ, node của An có các nhãn `Person` và `Actor`; node của Bình có `Person` và `Director`. Thứ tự hiển thị giữa các nhãn có thể khác nhau.

Để kiểm tra một nhãn có mặt trong danh sách, dùng toán tử `IN`:

```cypher
MATCH (p:Person)
WHERE 'Actor' IN labels(p)
RETURN p.name AS dienVien;
```

Truy vấn trên trả về **An**. Có thể dùng một danh sách nhãn cần kiểm tra:

```cypher
MATCH (n)
WHERE all(requiredLabel IN ['Person', 'Actor']
          WHERE requiredLabel IN labels(n))
RETURN n.name AS ten;
```

Biểu thức `all(...)` chỉ đúng nếu node có **đủ cả hai nhãn**.

### 3.2. Kiểm tra nhãn trực tiếp trong pattern hoặc `WHERE`

Khi nhãn đã biết tại thời điểm viết truy vấn, cách diễn đạt ngắn gọn và rõ ý hơn là kiểm tra trực tiếp bằng mẫu node:

```cypher
MATCH (p:Person:Actor)
RETURN p.name AS dienVien;
```

Ở đây, `:Person:Actor` biểu thị điều kiện **AND**: node phải mang cả hai nhãn. Một cách tương đương để biểu đạt điều kiện là:

```cypher
MATCH (p:Person)
WHERE p:Actor
RETURN p.name AS dienVien;
```

Nếu cần kiểm tra một trong nhiều nhãn, có thể viết:

```cypher
MATCH (p:Person)
WHERE p:Actor OR p:Director
RETURN p.name AS nguoiLamPhim;
```

Trong Cypher hiện đại còn có cú pháp biểu thức nhãn phong phú hơn (ví dụ dùng `&` và `|`). Các ví dụ với `:Person:Actor`, `WHERE p:Actor` và `OR` ở trên dễ đọc và phù hợp để học các phép kiểm tra cơ bản.

**Khi nào dùng `labels(n)`?** Hãy dùng nó khi cần **trả về danh sách nhãn**, kiểm tra nhãn được truyền linh hoạt (ví dụ `$requiredLabel IN labels(n)`), hoặc khảo sát dữ liệu. Khi nhãn cố định, nên khai báo trực tiếp trong `MATCH` để bộ lập kế hoạch Cypher có nhiều cơ hội tận dụng chỉ mục theo nhãn.

## 4. Kiểm tra loại quan hệ với `type()`

### 4.1. `type(relationship)`

`type(r)` trả về **một chuỗi** là loại của relationship `r`; khi `r` bằng `null`, kết quả là `null`. Hàm này dành cho **relationship**, không dành cho node; ngược lại, `labels()` dành cho node chứ không dành cho relationship.

```cypher
MATCH (p:Person)-[r]->(m:Movie)
RETURN p.name AS nguoi,
       type(r) AS loaiQuanHe,
       m.title AS phim
ORDER BY nguoi;
```

Kết quả dự kiến gồm An với loại `ACTED_IN` và Bình với loại `DIRECTED`.

Lọc theo loại bằng so sánh chuỗi:

```cypher
MATCH (p:Person)-[r]->(m:Movie)
WHERE type(r) = 'ACTED_IN'
RETURN p.name AS dienVien, m.title AS phim;
```

Hoặc chấp nhận nhiều loại:

```cypher
MATCH (p:Person)-[r]->(m:Movie)
WHERE type(r) IN ['ACTED_IN', 'DIRECTED']
RETURN p.name, type(r), m.title;
```

### 4.2. Khi đã biết loại quan hệ, viết thẳng trong mẫu

```cypher
MATCH (p:Person)-[r:ACTED_IN]->(m:Movie)
RETURN p.name AS dienVien, r.role AS vaiDien, m.title AS phim;
```

Mẫu `-[r:ACTED_IN]->` vừa ràng buộc **loại quan hệ**, vừa thể hiện **chiều** của liên kết. Khi loại đã biết trước, mẫu có khai báo type thường rõ nghĩa và giúp bộ lập kế hoạch giới hạn quan hệ cần duyệt sớm hơn so với duyệt mọi loại rồi gọi `type(r)` để lọc.

Một điểm quan trọng: mặc dù node có thể có nhiều label, **một relationship chỉ có một type tại một thời điểm**. Muốn biểu đạt hai ý nghĩa quan hệ khác nhau, thường tạo hai relationship có hai type khác nhau, hoặc thiết kế lại mô hình tùy nghiệp vụ.

## 5. Khám phá tên và giá trị thuộc tính

### 5.1. `keys(entity)` liệt kê tên thuộc tính

`keys(n)` hoặc `keys(r)` trả về danh sách tên các thuộc tính hiện có trên node hoặc relationship. `keys()` cũng nhận một map. Hàm không liệt kê nhãn hay loại quan hệ. Thứ tự các tên thuộc tính không được bảo đảm.

```cypher
MATCH (p:Person)
RETURN p.name AS ten, keys(p) AS tenThuocTinh
ORDER BY ten;
```

Đối với An, danh sách bao gồm `personId`, `name` và `birthYear`; đối với Bình, danh sách chỉ gồm `personId` và `name`.

Relationship cũng có thuộc tính:

```cypher
MATCH (p:Person)-[r]->(m:Movie)
RETURN p.name AS nguoi,
       type(r) AS loaiQuanHe,
       keys(r) AS tenThuocTinhQuanHe;
```

Quan hệ `ACTED_IN` của An có `role` và `screenTime`; quan hệ `DIRECTED` của Bình không được gán property nên `keys(r)` trả về `[]`.

Để đếm **số thuộc tính** của một thực thể:

```cypher
MATCH (p:Person)
RETURN p.name AS ten, size(keys(p)) AS soThuocTinh;
```

Đừng đồng nhất `size(keys(p))` với số nhãn hoặc số cạnh của node: đó chỉ là **số khóa thuộc tính**.

### 5.2. `properties(entity)` lấy map thuộc tính

`properties(n)` hoặc `properties(r)` trả về **map** chứa các cặp khóa–giá trị của thực thể. Với thực thể không có thuộc tính, kết quả là map rỗng `{}`. Hàm cũng nhận map và trả về nội dung của map đó.

```cypher
MATCH (p:Person)-[r]->(m:Movie)
RETURN p.name AS nguoi,
       properties(p) AS thongTinNguoi,
       type(r) AS loaiQuanHe,
       properties(r) AS thongTinQuanHe;
```

Ví dụ, `properties(r)` của quan hệ `ACTED_IN` có dạng:

```json
{"role": "Lan", "screenTime": 42}
```

Trong khi `properties(r)` của quan hệ `DIRECTED` là `{}`. `properties(p)` **không** chứa label của node; muốn lấy label phải gọi `labels(p)` riêng.

### 5.3. Truy cập thuộc tính trực tiếp hoặc theo tên động

Khi biết trước tên thuộc tính, dùng cú pháp dấu chấm:

```cypher
MATCH (p:Person)
RETURN p.name AS ten, p.birthYear AS namSinh;
```

Nếu tên thuộc tính do một biểu thức hoặc tham số cung cấp, Cypher hỗ trợ truy cập bằng dấu ngoặc vuông:

```cypher
WITH 'birthYear' AS tenTruong
MATCH (p:Person)
RETURN p.name AS ten,
       p[tenTruong] AS giaTri;
```

Đây là **truy cập thuộc tính động**, khác với `p.birthYear` sử dụng tên khóa cố định. Nếu khóa không tồn tại, giá trị đọc được là `null`.

Để biến một map thuộc tính thành các dòng dữ liệu:

```cypher
MATCH (p:Person {personId: 'p-001'})
UNWIND keys(p) AS tenTruong
RETURN tenTruong, p[tenTruong] AS giaTri
ORDER BY tenTruong;
```

Cách này hữu ích trong màn hình kiểm tra dữ liệu hoặc quy trình xuất dữ liệu có cấu trúc thay đổi. Khi chỉ cần vài trường cố định, nên chọn trực tiếp các trường đó thay vì trả về toàn bộ `properties(p)`.

## 6. Kiểm tra thuộc tính có tồn tại bằng `IS NOT NULL`

### 6.1. Có thuộc tính hay không?

Trong các phiên bản Neo4j hiện đại, cách chuẩn để kiểm tra một property đã được gán giá trị là `entity.property IS NOT NULL`:

```cypher
MATCH (p:Person)
WHERE p.birthYear IS NOT NULL
RETURN p.name AS ten, p.birthYear AS namSinh;
```

Truy vấn trên chỉ trả về An, vì Bình không có property `birthYear`. Câu lệnh ngược lại tìm thực thể thiếu giá trị:

```cypher
MATCH (p:Person)
WHERE p.birthYear IS NULL
RETURN p.name AS thieuNamSinh;
```

Với dữ liệu mẫu, kết quả là Bình.

Đối với thuộc tính của relationship:

```cypher
MATCH (p:Person)-[r]->(m:Movie)
WHERE r.role IS NOT NULL
RETURN p.name, type(r), r.role;
```

Trong ví dụ này chỉ quan hệ `ACTED_IN` của An có `role`.

### 6.2. Hiểu đúng `null` trong property graph

Trong Neo4j, property của node và relationship không lưu một giá trị `null` như một giá trị thuộc tính thông thường. **Gán `null` sẽ xóa thuộc tính đó**:

```cypher
MATCH (p:Person {personId: 'p-002'})
SET p.birthYear = null
RETURN p.birthYear IS NULL AS thieuNamSinh;
```

Kết quả `true`, vì `birthYear` không tồn tại trên node. Thực tế, Bình vốn đã thiếu thuộc tính này, nên lệnh trên không làm thay đổi dữ liệu mẫu. Trong các biểu thức Cypher, `null` còn mang nghĩa «không có giá trị», chẳng hạn khi đọc một thuộc tính bị thiếu hoặc khi `OPTIONAL MATCH` không tìm thấy kết quả.

**Không dùng `= null` hoặc `<> null` để tìm thuộc tính thiếu**. So sánh thông thường với `null` tạo ra kết quả `null` (không phải `true`), nên không thỏa điều kiện `WHERE`. Hãy dùng `IS NULL` hoặc `IS NOT NULL`.

Ngoài ra, các giá trị `0`, `false` và chuỗi rỗng `''` **không phải `null`**. Ví dụ, một property có giá trị `false` vẫn thỏa `IS NOT NULL`:

```cypher
WITH {active: false, note: ''} AS thongTin
RETURN thongTin.active IS NOT NULL AS coActive,
       thongTin.note IS NOT NULL AS coNote,
       thongTin.missing IS NULL AS thieuMissing;
```

Cả ba kết quả trong truy vấn này đều là `true`. Dữ liệu lưu ở dạng map có thể được xử lý bằng cùng cú pháp đọc thuộc tính.

> Lưu ý tương thích: một số ví dụ Cypher cũ dùng `exists(n.property)` để kiểm tra property. Cú pháp đó đã bị loại bỏ trong các phiên bản Neo4j mới; hãy dùng `n.property IS NOT NULL`. Đừng nhầm phép kiểm tra property này với `EXISTS { ... }`, vốn dùng để kiểm tra sự tồn tại của một mẫu hoặc truy vấn con.

## 7. Kết hợp kiểm tra nhãn, loại quan hệ và thuộc tính

### 7.1. Tìm diễn viên có năm sinh và vai diễn hợp lệ

```cypher
MATCH (p:Person:Actor)-[r:ACTED_IN]->(m:Movie)
WHERE p.birthYear IS NOT NULL
  AND r.role IS NOT NULL
RETURN p.name AS dienVien,
       p.birthYear AS namSinh,
       m.title AS phim,
       r.role AS vaiDien;
```

Trong truy vấn này:

1. `p:Person:Actor` bảo đảm node có cả hai nhãn.
2. `r:ACTED_IN` bảo đảm quan hệ đúng loại.
3. `p.birthYear IS NOT NULL` và `r.role IS NOT NULL` kiểm tra thuộc tính có giá trị.
4. `RETURN` chỉ lấy những trường cần thiết cho kết quả.

### 7.2. Kiểm kê dữ liệu và nhận diện bản ghi thiếu trường

```cypher
MATCH (p:Person)
RETURN p.personId AS id,
       p.name AS ten,
       'Actor' IN labels(p) AS laDienVien,
       p.birthYear IS NOT NULL AS coNamSinh,
       keys(p) AS cacTruongHienCo
ORDER BY id;
```

Truy vấn trả về một hàng cho mỗi `Person`, gồm các cờ Boolean để kiểm tra tình trạng dữ liệu và danh sách khóa đang có. Đây là một cách xây dựng báo cáo kiểm kê trước khi áp dụng ràng buộc dữ liệu.

### 7.3. Đọc đồ thị linh hoạt khi chưa biết loại quan hệ

```cypher
MATCH (p:Person)-[r]->(m:Movie)
RETURN p.name AS nguoi,
       labels(p) AS nhanNguoi,
       type(r) AS quanHe,
       properties(r) AS duLieuQuanHe,
       m.title AS phim;
```

Đây là dạng truy vấn hữu ích khi khám phá dữ liệu, nhưng khi đã biết nhãn và loại quan hệ cần tìm, nên đưa chúng vào `MATCH` để giới hạn phạm vi tìm kiếm.

## 8. Bảng ghi nhớ nhanh

| Cần kiểm tra / lấy dữ liệu | Cú pháp Cypher | Kiểu kết quả | Ghi chú |
| --- | --- | --- | --- |
| Tất cả nhãn của node | `labels(n)` | Danh sách chuỗi | Node có thể có nhiều nhãn. |
| Node có nhãn cụ thể | `n:Person` hoặc `'Person' IN labels(n)` | Boolean | Nhãn cố định nên ưu tiên ràng buộc trong `MATCH`. |
| Node có cả hai nhãn | `MATCH (n:Person:Actor)` | Mẫu node | Ý nghĩa AND. |
| Loại của relationship | `type(r)` | Chuỗi | Một relationship có một type. |
| Relationship có loại cụ thể | `type(r) = 'ACTED_IN'` hoặc `[r:ACTED_IN]` | Boolean hoặc mẫu quan hệ | Mẫu có type cố định thường dễ tối ưu hơn. |
| Tên thuộc tính | `keys(n)`, `keys(r)` | Danh sách chuỗi | Không bao gồm label/type. |
| Map thuộc tính | `properties(n)`, `properties(r)` | Map | Không bao gồm label/type. |
| Thuộc tính có giá trị | `n.name IS NOT NULL` | Boolean | Cách chuẩn để kiểm tra property. |
| Thuộc tính thiếu giá trị | `n.name IS NULL` | Boolean | Đúng với property không tồn tại. |
| Thuộc tính với tên động | `n[tenTruong]` | Giá trị hoặc `null` | Có thể dùng biến hoặc tham số cho tên khóa. |

## 9. Lưu ý về hiệu năng và thiết kế truy vấn

- **Đặt nhãn và loại quan hệ vào pattern khi đã biết trước.** `MATCH (p:Person)-[:ACTED_IN]->(m:Movie)` diễn đạt cấu trúc cần tìm rõ hơn `MATCH (p)-[r]->(m) WHERE 'Person' IN labels(p) AND type(r) = 'ACTED_IN'`.
- **Lọc theo thuộc tính càng sớm càng tốt.** Nếu có chỉ mục phù hợp, truy vấn với nhãn và thuộc tính cố định, chẳng hạn `MATCH (p:Person {personId: 'p-001'})`, có thể tránh phải duyệt toàn bộ graph.
- **Đừng dùng `keys()` hoặc `properties()` thay cho điều kiện trực tiếp một cách không cần thiết.** Khi chỉ kiểm tra `birthYear`, `p.birthYear IS NOT NULL` rõ ý hơn `'birthYear' IN keys(p)`. Kết quả cũng dễ được bộ lập kế hoạch tối ưu hơn.
- **Tránh trả về toàn bộ thuộc tính khi không cần.** `properties(n)` có thể tạo dữ liệu trả về lớn và bao gồm các trường mà ứng dụng không cần hiển thị. Hãy liệt kê các thuộc tính cần dùng trong `RETURN`.
- **Dùng `EXPLAIN` / `PROFILE` để kiểm chứng.** Chiến lược truy vấn thực tế phụ thuộc phiên bản Neo4j, chỉ mục, phân bố dữ liệu và cách viết Cypher; không nên khẳng định một hàm luôn nhanh hoặc luôn chậm trong mọi trường hợp.

Ví dụ minh họa truy vấn có nhãn và khóa cố định để kiểm tra kế hoạch thực thi:

```cypher
EXPLAIN
MATCH (p:Person {personId: 'p-001'})
RETURN p.name;
```

`EXPLAIN` chỉ lập kế hoạch, còn `PROFILE` thực thi truy vấn và cung cấp số liệu thực tế. Với hệ thống lớn, nên cân nhắc tạo unique constraint hoặc index phù hợp trước khi đánh giá hiệu năng.

## 10. Lỗi thường gặp

| Sai lầm | Vì sao sai | Cách làm phù hợp |
| --- | --- | --- |
| Gọi `labels(r)` với relationship | `labels()` dành cho node. | Dùng `type(r)`. |
| Gọi `type(n)` với node | `type()` dành cho relationship. | Dùng `labels(n)`. |
| Dùng `n.Actor` để kiểm tra nhãn `Actor` | Cú pháp này tìm property tên `Actor`. | Dùng `n:Actor` hoặc `'Actor' IN labels(n)`. |
| Dùng `r.type` để đọc loại quan hệ | Đây là property tên `type` nếu có. | Dùng `type(r)`. |
| Dùng `p.name = null` | So sánh với `null` không tạo `true`. | Dùng `p.name IS NULL`. |
| Coi `labels(n)[0]` là nhãn chính | Không có bảo đảm thứ tự nhãn. | Kiểm tra nhãn theo tên. |
| Cho rằng `keys(n)` gồm cả nhãn | Hàm chỉ liệt kê khóa property. | Kết hợp `keys(n)` với `labels(n)` khi cần. |
| Quét mọi node để lọc label cố định | Có thể bỏ lỡ lợi ích của truy vấn theo nhãn. | Dùng `MATCH (n:Label)`. |

## 11. Bài thực hành tự kiểm tra

**Bài 1.** Liệt kê tên người, danh sách nhãn và số lượng thuộc tính của từng người.

```cypher
MATCH (p:Person)
RETURN p.name AS ten,
       labels(p) AS nhan,
       size(keys(p)) AS soThuocTinh
ORDER BY ten;
```

**Bài 2.** Liệt kê các quan hệ đi vào `Movie`, nhưng chỉ giữ những quan hệ có ít nhất một thuộc tính.

```cypher
MATCH (p:Person)-[r]->(m:Movie)
WHERE size(keys(r)) > 0
RETURN p.name AS nguoi,
       type(r) AS loaiQuanHe,
       properties(r) AS thuocTinh;
```

Với dữ liệu mẫu, chỉ quan hệ `ACTED_IN` được trả về.

**Bài 3.** Tìm những người mang nhãn `Person` nhưng chưa có thuộc tính `birthYear`; cho biết người đó có phải `Director` hay không.

```cypher
MATCH (p:Person)
WHERE p.birthYear IS NULL
RETURN p.name AS ten,
       'Director' IN labels(p) AS laDaoDien;
```

Kết quả dự kiến là Bình với `laDaoDien = true`.

**Bài 4 (mở rộng).** Đếm số quan hệ theo từng loại mà không cần biết trước type nào xuất hiện.

```cypher
MATCH ()-[r]->()
RETURN type(r) AS loaiQuanHe, count(*) AS soLuong
ORDER BY soLuong DESC, loaiQuanHe;
```

Với dữ liệu ví dụ độc lập, `ACTED_IN` và `DIRECTED` mỗi loại có một quan hệ. Nếu cơ sở dữ liệu còn chứa đồ thị khác, kết quả sẽ bao gồm cả những quan hệ ấy; có thể giới hạn `MATCH` theo nhãn node khi cần.

## 12. Tổng kết

Trong Cypher, cần phân biệt rõ ba lớp thông tin của property graph: **`labels(n)` kiểm tra cấu trúc nhãn của node; `type(r)` xác định loại relationship; `keys()`, `properties()` và truy cập thuộc tính làm việc với dữ liệu khóa–giá trị**. Khi yêu cầu là kiểm tra một property cụ thể có giá trị hay không, hãy dùng **`IS NOT NULL`** hoặc **`IS NULL`**. Khi nhãn và type đã biết, nên đưa chúng trực tiếp vào pattern `MATCH` để truy vấn dễ hiểu và có cơ hội tối ưu tốt hơn.
