# Biểu thức, toán tử, độ ưu tiên và cách viết điều kiện rõ nghĩa trong Cypher

> **Chương:** Nền tảng Cypher  
> **Bối cảnh:** Neo4j lưu dữ liệu dạng *property graph* gồm node, relationship và thuộc tính. Khi truy vấn bằng Cypher, những biểu thức nhỏ như `p.age >= 25`, `pr.status = 'active'` hay `w.role IN $roles` quyết định mẫu đồ thị nào được giữ lại. Bài học tập trung vào ý nghĩa của biểu thức, các nhóm toán tử, thứ tự ưu tiên và cách diễn đạt điều kiện chính xác, dễ kiểm tra.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Nhận biết **literal, biến, tham số, truy cập thuộc tính, lời gọi hàm và biểu thức tổng hợp** trong Cypher.
2. Dùng đúng toán tử số học, so sánh, logic, chuỗi, list và kiểm tra giá trị thiếu.
3. Hiểu **ba giá trị logic** `true`, `false` và `null`; dự đoán dòng nào được giữ bởi `WHERE`.
4. Đọc và viết điều kiện có nhiều `AND`, `OR`, `NOT`, `XOR` mà không nhầm thứ tự ưu tiên.
5. Sử dụng ngoặc `(...)` để diễn đạt các nhóm điều kiện theo đúng yêu cầu nghiệp vụ.
6. Kết hợp `CASE`, `coalesce`, `IN`, các phép kiểm tra list và `EXISTS { ... }` trong bài toán đồ thị.
7. Phân biệt điều kiện thuộc `MATCH`, `OPTIONAL MATCH` hoặc lọc sau `WITH`.
8. Biết khi nào cần truyền tham số, chuẩn hóa kiểu dữ liệu và xem kế hoạch thực thi khi điều kiện truy vấn phức tạp.

## 2. Biểu thức trong Cypher là gì?

**Biểu thức** (*expression*) là một thành phần của câu truy vấn được đánh giá thành **giá trị**. Giá trị đó có thể là số, chuỗi, boolean, `null`, list, map, node, relationship, path hoặc một giá trị temporal.

Ví dụ:

| Biểu thức | Kiểu giá trị hoặc vai trò |
|---|---|
| `25` | Số nguyên literal. |
| `'Hà Nội'` | Chuỗi literal. |
| `true` | Boolean literal. |
| `null` | Giá trị thiếu/không xác định. |
| `p.age` | Truy cập property `age` của node được gán biến `p`. |
| `$minAge` | Tham số do ứng dụng cung cấp. |
| `p.age + 1` | Biểu thức số học. |
| `p.age >= $minAge` | Biểu thức điều kiện, thường cho `true`, `false` hoặc `null`. |
| `coalesce(p.city, 'Chưa cập nhật')` | Lời gọi hàm để thay thế giá trị `null`. |
| `[p.name, p.city]` | List gồm hai phần tử. |
| `{name: p.name, age: p.age}` | Map chứa các giá trị được tính từ biến. |
| `CASE WHEN p.age >= 18 THEN 'adult' ELSE 'minor' END` | Biểu thức rẽ nhánh theo điều kiện. |

Một biểu thức có thể xuất hiện ở nhiều vị trí:

```cypher
MATCH (p:Person)
WHERE p.age >= $minAge
RETURN p.name AS ten, p.age + 1 AS tuoiNamSau
ORDER BY tuoiNamSau DESC;
```

- `MATCH` tạo biến `p` qua mẫu node.
- `WHERE` dùng biểu thức điều kiện để lọc mẫu.
- `RETURN` đánh giá các biểu thức thành cột kết quả.
- `ORDER BY` sắp xếp theo biểu thức/cột đã đặt tên.

**Quy tắc quan trọng:** Trong `WHERE`, chỉ các dòng có điều kiện đánh giá thành **`true`** được giữ. `false` và `null` đều không làm dòng vượt qua bộ lọc.

## 3. Bộ dữ liệu mẫu để kiểm tra từng điều kiện

Các ví dụ sử dụng một tập node và relationship cố định. Hãy chạy đoạn sau trong **database thực hành**; ID có tiền tố `c006-` để tránh nhầm với ví dụ khác. `MERGE` giúp tìm trước khi tạo mẫu, nhưng cơ sở dữ liệu thật vẫn cần uniqueness constraint nếu ID nghiệp vụ phải duy nhất giữa nhiều giao dịch.

```cypher
MERGE (an:Person {id: 'c006-an'})
SET an.name = 'An', an.age = 30,
    an.city = 'Hà Nội', an.active = true,
    an.score = 92, an.tags = ['graph', 'java']

MERGE (binh:Person {id: 'c006-binh'})
SET binh.name = 'Bình', binh.age = 27,
    binh.city = 'TP. Hồ Chí Minh', binh.active = true,
    binh.score = 77, binh.tags = ['java', 'api']

MERGE (chi:Person {id: 'c006-chi'})
SET chi.name = 'Chi', chi.age = 35,
    chi.city = 'Hà Nội', chi.active = false,
    chi.score = 88, chi.tags = ['graph', 'data']

MERGE (dung:Person {id: 'c006-dung'})
SET dung.name = 'Dũng', dung.age = 24, dung.active = true
REMOVE dung.city, dung.score, dung.tags

MERGE (api:Project {id: 'c006-api'})
SET api.name = 'Graph API', api.status = 'active',
    api.budget = 100

MERGE (reco:Project {id: 'c006-reco'})
SET reco.name = 'Recommendation', reco.status = 'planned',
    reco.budget = 40

MERGE (an)-[wa:WORKS_ON]->(api)
SET wa.role = 'lead', wa.since = 2021
MERGE (an)-[wb:WORKS_ON]->(reco)
SET wb.role = 'reviewer', wb.since = 2024
MERGE (binh)-[wc:WORKS_ON]->(api)
SET wc.role = 'developer', wc.since = 2023
MERGE (chi)-[wd:WORKS_ON]->(reco)
SET wd.role = 'advisor', wd.since = 2022

MERGE (an)-[:KNOWS]->(binh)
MERGE (binh)-[:KNOWS]->(chi);
```

Tóm tắt dữ liệu:

| Person | age | active | city | score | tags |
|---|---:|---|---|---:|---|
| An | 30 | `true` | Hà Nội | 92 | `['graph', 'java']` |
| Bình | 27 | `true` | TP. Hồ Chí Minh | 77 | `['java', 'api']` |
| Chi | 35 | `false` | Hà Nội | 88 | `['graph', 'data']` |
| Dũng | 24 | `true` | Không có property | Không có property | Không có property |

```text
An   ──WORKS_ON {role: lead}─────> Graph API (active, budget:100)
  └──WORKS_ON {role: reviewer}───> Recommendation (planned, budget:40)
Bình ──WORKS_ON {role: developer}─> Graph API
Chi  ──WORKS_ON {role: advisor}───> Recommendation
Dũng   (không có WORKS_ON)

An ──KNOWS──> Bình ──KNOWS──> Chi
```

Để chỉ lọc những người thuộc bộ mẫu khi database có dữ liệu khác, dùng:

```cypher
MATCH (p:Person)
WHERE p.id IN ['c006-an', 'c006-binh', 'c006-chi', 'c006-dung']
RETURN p.name AS ten;
```

Những bảng kết quả dưới đây giả định mỗi ID mẫu chỉ ứng với một node và không có relationship ngoài bộ mẫu nối vào các node đó.

## 4. Biến, literal, tham số và kiểu dữ liệu

Đây là những thành phần cơ bản tạo nên biểu thức:

```cypher
MATCH (p:Person)-[w:WORKS_ON]->(pr:Project)
WHERE p.id = $personId
  AND pr.status = 'active'
  AND w.since >= 2020
RETURN p.name, w.role, pr.name;
```

| Thành phần | Giải nghĩa |
|---|---|
| `p`, `w`, `pr` | Biến node/relationship được ràng buộc theo từng dòng. |
| `Person`, `Project` | Label; thuộc cấu trúc graph pattern. |
| `WORKS_ON` | Relationship type; thuộc cấu trúc graph pattern. |
| `p.id`, `w.since`, `pr.status` | Truy cập property qua dấu chấm. |
| `$personId` | Tham số dữ liệu, ví dụ `'c006-an'`. |
| `'active'`, `2020` | Literal trong truy vấn. |
| `=`, `>=`, `AND` | Toán tử tạo điều kiện. |

### 4.1. Chuỗi, số và boolean phải đúng kiểu

```cypher
RETURN 25 AS so,
       '25' AS chuoi,
       true AS dangHoatDong,
       null AS khongCoGiaTri;
```

`25` là số, `'25'` là chuỗi. `true` là boolean, `'true'` là chuỗi. Không nên viết điều kiện so sánh khác kiểu rồi mong Neo4j tự chuyển kiểu theo ý định ứng dụng.

Ví dụ này dùng tham số số:

```cypher
MATCH (p:Person)
WHERE p.id IN ['c006-an', 'c006-binh', 'c006-chi', 'c006-dung']
  AND p.age >= $minAge
RETURN p.name AS ten, p.age AS tuoi;
```

Bên gọi truyền `{"minAge": 30}` sẽ chọn An và Chi. Truyền `{"minAge": "30"}` là truyền **chuỗi** và có thể dẫn tới lỗi không tương thích kiểu khi so với tuổi dạng số.

### 4.2. Phép truy cập property có thể tạo `null`

```cypher
MATCH (p:Person {id: 'c006-dung'})
RETURN p.name AS ten,
       p.city AS thanhPho,
       p.score AS diem;
```

Vì Dũng không có property `city` và `score`, hai biểu thức tương ứng cho `null`. Neo4j không lưu property có giá trị `null` giống một giá trị dữ liệu thông thường; đặt một property thành `null` tương đương với việc loại bỏ property đó.

## 5. Toán tử số học

Các toán tử số học thông dụng:

| Toán tử | Ý nghĩa | Ví dụ |
|---|---|---|
| `+` | Cộng hai số; có các cách dùng khác với chuỗi/list theo kiểu toán hạng. | `7 + 3` → `10` |
| `-` | Trừ hai số; dấu âm có thể đứng trước biểu thức số. | `7 - 3` → `4` |
| `*` | Nhân. | `7 * 3` → `21` |
| `/` | Chia. | `8 / 2` → `4` |
| `%` | Phép lấy phần dư. | `10 % 3` → `1` |
| `^` | Lũy thừa. | `2 ^ 3` → `8` |

Một biểu thức số học trên property:

```cypher
MATCH (p:Person {id: 'c006-an'})
RETURN p.name AS ten,
       p.age AS tuoiHienTai,
       p.age + 1 AS tuoiNamSau,
       p.score * 2 AS diemNhanDoi;
```

Với An, `tuoiNamSau = 31` và `diemNhanDoi = 184`.

### 5.1. Ưu tiên số học

Trong các phép toán thông dụng, nhân/chia/lấy dư có ưu tiên cao hơn cộng/trừ:

```cypher
RETURN 2 + 3 * 4 AS ketQuaKhongNgoac,
       (2 + 3) * 4 AS ketQuaCoNgoac;
```

Kết quả là `14` và `20`.

Lũy thừa `^` được đánh giá ưu tiên hơn những phép cộng/trừ thông thường; nếu biểu thức có thêm dấu âm đơn ngôi, hãy viết rõ nhóm bằng ngoặc để tránh hiểu sai:

```cypher
RETURN (2 ^ 3) + 1 AS giaTri,   // 9
       -(2 ^ 2) AS amBon,       // -4
       (-2) ^ 2 AS duongBon;    // 4
```

**Gợi ý khi viết:** Ngoặc nhóm mang ý nghĩa nghiệp vụ, không chỉ là cách làm toán tử chạy đúng. Chẳng hạn, nếu phép tính phụ thuộc `p.score` và một hệ số, hãy đặt ngoặc ngay cả khi có thể suy ra thứ tự ưu tiên bằng trí nhớ.

### 5.2. Chia cho số không và giá trị thiếu

Đừng giả định biểu thức có phép chia cho 0 sẽ luôn cho kết quả hữu ích. Khi mẫu số đến từ dữ liệu và có thể bằng 0, hãy mô tả rõ cách xử lý:

```cypher
WITH 100.0 AS total, 0.0 AS divisor
RETURN CASE
         WHEN divisor = 0 THEN null
         ELSE total / divisor
       END AS tyLe;
```

Ở đây `tyLe = null` theo **quy tắc nghiệp vụ do ta đặt**, không dựa vào hành vi lỗi chia cho 0. Khi mẫu số có thể là `null`, cần xét thêm điều kiện `divisor IS NULL` nếu muốn phân biệt nguyên nhân.

## 6. Toán tử so sánh và điều kiện khoảng

| Toán tử | Ý nghĩa |
|---|---|
| `=` | So sánh bằng. |
| `<>` | So sánh khác. |
| `<`, `<=` | Nhỏ hơn, nhỏ hơn hoặc bằng. |
| `>`, `>=` | Lớn hơn, lớn hơn hoặc bằng. |
| `IS NULL` | Kiểm tra biểu thức là `null`. |
| `IS NOT NULL` | Kiểm tra biểu thức khác `null`. |

Ví dụ: lấy người có tuổi từ 25 đến 32, tính cả hai đầu:

```cypher
MATCH (p:Person)
WHERE p.id IN ['c006-an', 'c006-binh', 'c006-chi', 'c006-dung']
  AND p.age >= 25
  AND p.age <= 32
RETURN p.name AS ten, p.age AS tuoi
ORDER BY tuoi DESC;
```

Kết quả: An (30), Bình (27). Điều kiện khoảng được diễn đạt bằng **hai phép so sánh** và `AND`.

### 6.1. Một điều kiện phải đủ rõ về miền giá trị

Giả sử yêu cầu là “người trên 30 tuổi”:

```cypher
WHERE p.age > 30
```

Không giống “người từ 30 tuổi”:

```cypher
WHERE p.age >= 30
```

Trong dữ liệu mẫu, `p.age > 30` chỉ chọn Chi, còn `p.age >= 30` chọn An và Chi.

### 6.2. Tránh so sánh lẫn lộn kiểu

So sánh số với số, chuỗi với chuỗi, ngày với ngày khi có ý nghĩa. Ví dụ:

```cypher
RETURN date('2026-11-25') >= date('2026-11-01') AS trongThang;
```

Kết quả là `true`. Nếu property trong database là kiểu `Date`, ứng dụng nên truyền giá trị date tương ứng hoặc chuyển đổi chuỗi đầu vào có chủ đích. So sánh ngày tháng dưới dạng chuỗi không phải thay thế tổng quát cho so sánh kiểu temporal.

## 7. Toán tử logic: `AND`, `OR`, `NOT`, `XOR`

Điều kiện Cypher có thể kết hợp những biểu thức boolean:

- `A AND B`: cả A và B phải đúng.
- `A OR B`: ít nhất một điều kiện đúng.
- `NOT A`: phủ định giá trị logic của A.
- `A XOR B`: đúng khi chỉ **một trong hai** điều kiện đúng.

Với giá trị không thiếu:

| A | B | `A AND B` | `A OR B` | `A XOR B` |
|---|---|---|---|---|
| `true` | `true` | `true` | `true` | `false` |
| `true` | `false` | `false` | `true` | `true` |
| `false` | `true` | `false` | `true` | `true` |
| `false` | `false` | `false` | `false` | `false` |

### 7.1. Ví dụ điều kiện kết hợp

Yêu cầu: “Người đang hoạt động **và** có tuổi từ 28 trở lên”.

```cypher
MATCH (p:Person)
WHERE p.id IN ['c006-an', 'c006-binh', 'c006-chi', 'c006-dung']
  AND (p.active = true AND p.age >= 28)
RETURN p.name AS ten;
```

Chỉ **An** thỏa. Chi 35 tuổi nhưng `active = false`; Bình 27 tuổi; Dũng 24 tuổi.

### 7.2. Phủ định một nhóm điều kiện

```cypher
MATCH (p:Person)
WHERE p.id IN ['c006-an', 'c006-binh', 'c006-chi', 'c006-dung']
  AND NOT (p.active = true AND p.age >= 28)
RETURN p.name AS ten
ORDER BY ten;
```

Kết quả: Bình, Chi, Dũng. Ngoặc sau `NOT` làm rõ rằng ta phủ định **toàn bộ** điều kiện kép.

Không nên diễn giải `NOT (A AND B)` thành `(NOT A) AND (NOT B)`. Theo quy tắc De Morgan, ý nghĩa tương đương là `(NOT A) OR (NOT B)` (với logic ba giá trị của Cypher cũng cần giữ ngữ nghĩa `null`).

## 8. Độ ưu tiên của toán tử

Nếu một biểu thức không có ngoặc, hệ quản trị cần quy tắc để quyết định phần nào được đánh giá trước. Dưới đây là thứ tự **theo nhóm từ ưu tiên cao xuống thấp** thường cần khi đọc điều kiện Cypher:

| Nhóm | Toán tử/biểu thức tiêu biểu | Ghi chú |
|---|---|---|
| Truy cập giá trị | `p.age`, `list[0]`, `map['key']` | Gắn giá trị/thuộc tính trước khi sử dụng vào biểu thức lớn. |
| Lũy thừa và dấu số học | `^`, dấu `+`/`-` đơn ngôi | Nên đặt ngoặc khi kết hợp dấu âm và lũy thừa. |
| Nhân, chia, lấy dư | `*`, `/`, `%` | Cao hơn cộng/trừ. |
| Cộng, trừ | `+`, `-` | Thực hiện sau nhóm nhân/chia trong các biểu thức thông thường. |
| So sánh và kiểm tra | `=`, `<>`, `<`, `>=`, `IN`, `IS NULL`, ... | Tạo giá trị logic dùng ở các nhóm sau. |
| Phủ định logic | `NOT` | Cao hơn `AND`, `XOR`, `OR`. |
| Hội logic | `AND` | Cao hơn `XOR` và `OR`. |
| Hoặc loại trừ | `XOR` | Cao hơn `OR`. |
| Tuyển logic | `OR` | Ưu tiên thấp nhất trong bốn toán tử logic này. |

Các mục là **nhóm diễn giải**. Khi có những cú pháp ít gặp, dấu số học đơn ngôi, toán tử mới theo phiên bản hoặc biểu thức lồng sâu, hãy thêm ngoặc để truyền đạt ý định rõ ràng thay vì dựa vào thứ tự ghi nhớ.

### 8.1. `AND` được ưu tiên hơn `OR`

```cypher
RETURN true OR false AND false AS khongNgoac,
       (true OR false) AND false AS coNgoac;
```

`khongNgoac = true` vì `false AND false` được nhóm trước. `coNgoac = false` vì `true OR false` được nhóm trước.

### 8.2. Một khác biệt nghiệp vụ rất dễ bỏ sót

Xét yêu cầu A: **“Lấy người đang hoạt động, hoặc người từ 30 tuổi và ở Hà Nội.”**

```cypher
MATCH (p:Person)
WHERE p.id IN ['c006-an', 'c006-binh', 'c006-chi', 'c006-dung']
  AND (p.active = true OR (p.age >= 30 AND p.city = 'Hà Nội'))
RETURN p.name AS ten
ORDER BY ten;
```

Kết quả là **An, Bình, Chi, Dũng**: ba người `active = true` được nhận; Chi tuy inactive nhưng trên 30 và ở Hà Nội.

Yêu cầu B: **“Lấy những người ở Hà Nội, đồng thời đang hoạt động hoặc từ 30 tuổi.”**

```cypher
MATCH (p:Person)
WHERE p.id IN ['c006-an', 'c006-binh', 'c006-chi', 'c006-dung']
  AND ((p.active = true OR p.age >= 30) AND p.city = 'Hà Nội')
RETURN p.name AS ten
ORDER BY ten;
```

Chỉ có **An và Chi**. Hai yêu cầu rất giống về từ ngữ nhưng phạm vi áp dụng “ở Hà Nội” khác nhau. **Ngoặc là một phần của đặc tả nghiệp vụ.**

### 8.3. Gắn điều kiện ID với một nhóm `OR`

Một lỗi phổ biến:

```cypher
// DỄ SAI: nhánh OR phía sau có thể bỏ qua điều kiện ID
MATCH (p:Person)
WHERE p.id IN ['c006-an', 'c006-binh']
  AND p.active = true
  OR p.age >= 30
RETURN p.name;
```

Theo ưu tiên `AND` trước `OR`, câu này có nghĩa:

```text
(id thuộc danh sách AND active)
OR (age >= 30)
```

Vì vậy nhánh tuổi có thể đưa vào kết quả những node **không thuộc danh sách ID**, chẳng hạn Chi hoặc bất kỳ nhân sự khác có tuổi từ 30. Nếu yêu cầu là “chỉ trong hai ID, chọn người active hoặc từ 30 tuổi”, hãy viết:

```cypher
MATCH (p:Person)
WHERE p.id IN ['c006-an', 'c006-binh']
  AND (p.active = true OR p.age >= 30)
RETURN p.name AS ten;
```

Ngoặc thứ hai thể hiện ranh giới rõ ràng giữa **tập đối tượng được phép xét** và **điều kiện lựa chọn bên trong tập**.

## 9. `null` và logic ba giá trị

Trong Cypher, một property không tồn tại hoặc một biến không khớp trong `OPTIONAL MATCH` thường cho `null`. Trong điều kiện logic, `null` biểu diễn **chưa biết/không xác định**; nó không đồng nghĩa với `false`.

### 9.1. Các phép logic với `null`

| A | B | `A AND B` | `A OR B` |
|---|---|---|---|
| `true` | `null` | `null` | `true` |
| `false` | `null` | `false` | `null` |
| `null` | `true` | `null` | `true` |
| `null` | `false` | `false` | `null` |
| `null` | `null` | `null` | `null` |

`NOT null` cho `null`; một biểu thức `XOR` có toán hạng `null` cũng cho `null`. Trường hợp `false AND null` luôn cho `false` vì bất kể giá trị chưa biết là gì, cả hai điều kiện cũng không thể đồng thời đúng.

### 9.2. So sánh với `null`

```cypher
RETURN null = null AS soSanhBang,
       null <> 1 AS soSanhKhac,
       NOT null AS phuDinh;
```

Cả ba cột có giá trị `null`. Không được dùng `p.city = null` để tìm người thiếu property `city`; hãy dùng:

```cypher
MATCH (p:Person)
WHERE p.id IN ['c006-an', 'c006-binh', 'c006-chi', 'c006-dung']
  AND p.city IS NULL
RETURN p.name AS ten;
```

Kết quả: **Dũng**.

### 9.3. `<>` không tự bao gồm giá trị thiếu

Yêu cầu: “Tìm người không ở Hà Nội”.

```cypher
MATCH (p:Person)
WHERE p.id IN ['c006-an', 'c006-binh', 'c006-chi', 'c006-dung']
  AND p.city <> 'Hà Nội'
RETURN p.name AS ten;
```

Chỉ có **Bình**. Dũng không xuất hiện, vì `null <> 'Hà Nội'` cho `null`, không phải `true`.

Nếu yêu cầu là “không ở Hà Nội **hoặc chưa cập nhật thành phố**”, phải viết tường minh:

```cypher
MATCH (p:Person)
WHERE p.id IN ['c006-an', 'c006-binh', 'c006-chi', 'c006-dung']
  AND (p.city <> 'Hà Nội' OR p.city IS NULL)
RETURN p.name AS ten
ORDER BY ten;
```

Kết quả là **Bình, Dũng**.

### 9.4. `coalesce` thay thế `null` có chủ đích

```cypher
MATCH (p:Person)
WHERE p.id IN ['c006-an', 'c006-binh', 'c006-chi', 'c006-dung']
RETURN p.name AS ten,
       coalesce(p.city, 'Chưa cập nhật') AS thanhPho
ORDER BY ten;
```

`coalesce` trả **biểu thức đầu tiên khác `null`**; Dũng hiển thị `'Chưa cập nhật'`. Đây là một quy tắc hiển thị do chúng ta chọn, không làm property thiếu trong database trở thành giá trị thật.

Với property số, `coalesce(p.score, 0)` có thể hữu ích khi yêu cầu nghiệp vụ xem “chưa có điểm” như 0. Nếu thiếu điểm và điểm bằng 0 có ý nghĩa khác nhau, phải **giữ tách biệt** và kiểm tra bằng `IS NULL`.

## 10. Toán tử trên chuỗi

Cypher hỗ trợ các điều kiện phổ biến:

| Biểu thức | Ý nghĩa | Ví dụ |
|---|---|---|
| `name STARTS WITH 'B'` | Bắt đầu bằng chuỗi. | `'Bình'` khớp. |
| `name ENDS WITH 'nh'` | Kết thúc bằng chuỗi. | `'Bình'` khớp. |
| `city CONTAINS 'Hà'` | Có chuỗi con. | `'Hà Nội'` khớp. |
| `name =~ 'B.*'` | Khớp biểu thức chính quy (*regular expression*). | `'Bình'` khớp. |
| `toLower(name)` | Chuyển chuỗi thành chữ thường. | Dùng khi thiết kế lọc không phân biệt hoa/thường. |
| `trim(name)` | Loại khoảng trắng đầu/cuối. | Hữu ích khi xử lý đầu vào có khoảng trắng thừa. |

Ví dụ:

```cypher
MATCH (p:Person)
WHERE p.id IN ['c006-an', 'c006-binh', 'c006-chi', 'c006-dung']
  AND p.name STARTS WITH 'B'
RETURN p.name AS ten;
```

Kết quả: **Bình**.

### 10.1. So khớp chữ hoa/thường

`STARTS WITH`, `ENDS WITH`, `CONTAINS` là phép tìm chuỗi theo ký tự đã cho, không tự động thực hiện mọi quy tắc chuẩn hóa ngôn ngữ và dấu tiếng Việt. Khi nghiệp vụ cần lọc không phân biệt hoa/thường:

```cypher
MATCH (p:Person)
WHERE p.id IN ['c006-an', 'c006-binh', 'c006-chi', 'c006-dung']
  AND toLower(p.name) STARTS WITH toLower($prefix)
RETURN p.name AS ten;
```

Với tham số `{"prefix": "b"}`, tìm thấy **Bình**. Chữ có dấu, tổ hợp Unicode và đối chiếu ngôn ngữ cần được thiết kế riêng nếu ứng dụng yêu cầu tìm không phân biệt dấu.

### 10.2. Biểu thức chính quy `=~`

```cypher
MATCH (p:Person)
WHERE p.id IN ['c006-an', 'c006-binh', 'c006-chi', 'c006-dung']
  AND p.name =~ '(?i)b.*'
RETURN p.name AS ten;
```

Mẫu dùng `(?i)` để bật so khớp không phân biệt hoa/thường theo quy tắc regex, và `b.*` để yêu cầu chuỗi bắt đầu bằng “b” rồi theo sau bởi bất kỳ ký tự nào. Kết quả: **Bình**.

**Chọn đúng công cụ:** nếu chỉ muốn tìm theo tiền tố, `STARTS WITH` thường rõ nghĩa hơn regex. Với regex do người dùng cung cấp, ứng dụng cần kiểm soát độ phức tạp và đầu vào để tránh những mẫu gây truy vấn tốn tài nguyên.

### 10.3. Phép cộng trên chuỗi khác phép cộng số học

```cypher
MATCH (p:Person {id: 'c006-an'})
RETURN 'Nhân sự: ' + p.name AS nhan;
```

Kết quả: `'Nhân sự: An'`. Toán tử `+` có hành vi phụ thuộc kiểu dữ liệu; tránh trộn số và chuỗi tùy tiện. Nếu cần hiển thị số, chuyển kiểu có chủ đích, ví dụ `toString(p.age)`.

## 11. `IN`, list và điều kiện tập hợp

Toán tử `IN` kiểm tra một giá trị có thuộc list hay không:

```cypher
MATCH (p:Person)
WHERE p.id IN ['c006-an', 'c006-binh', 'c006-chi', 'c006-dung']
  AND p.city IN ['Hà Nội', 'Đà Nẵng']
RETURN p.name AS ten
ORDER BY ten;
```

Kết quả: **An, Chi**. Dũng thiếu property `city`, nên điều kiện không đánh giá thành `true` dù danh sách chứa `'Đà Nẵng'`.

### 11.1. Danh sách là dữ liệu, không phải cú pháp được ghép chuỗi

Trong ứng dụng nên truyền list qua tham số:

```cypher
MATCH (p:Person)
WHERE p.id IN $ids
RETURN p.name AS ten;
```

Với:

```json
{
  "ids": ["c006-an", "c006-chi"]
}
```

Truy vấn chọn An và Chi. Không viết `p.id IN [$ids]` nếu `$ids` đã là list: cách đó tạo **một list chứa nguyên list đầu vào**, sai ý định.

### 11.2. List rỗng và phần tử `null`

```cypher
RETURN 1 IN [] AS trongDanhSachRong,
       1 IN [1, 2] AS coTrongDanhSach,
       1 IN [2, null] AS khongChacChan;
```

Theo thứ tự:

- `1 IN []` → `false`.
- `1 IN [1, 2]` → `true`.
- `1 IN [2, null]` → `null`: không có số 1 khớp rõ ràng, nhưng list chứa một giá trị chưa biết.

Vì vậy, dữ liệu thiếu trong list có thể ảnh hưởng đến kết quả điều kiện. Ứng dụng nên xác định liệu phần tử `null` có hợp lệ trong danh sách lọc hay không.

### 11.3. Kiểm tra phần tử của property dạng list

```cypher
MATCH (p:Person)
WHERE p.id IN ['c006-an', 'c006-binh', 'c006-chi', 'c006-dung']
  AND 'graph' IN coalesce(p.tags, [])
RETURN p.name AS ten
ORDER BY ten;
```

Kết quả: **An, Chi**. `coalesce(p.tags, [])` giúp trường hợp Dũng không có `tags` được hiểu là danh sách rỗng **cho mục đích biểu thức này**.

Ngoài `IN`, bạn có thể dùng **list predicates** khi yêu cầu phức tạp:

```cypher
MATCH (p:Person)
WHERE p.id IN ['c006-an', 'c006-binh', 'c006-chi', 'c006-dung']
  AND any(tag IN coalesce(p.tags, []) WHERE tag = 'graph')
RETURN p.name AS ten
ORDER BY ten;
```

`any(...)` kiểm tra có ít nhất một phần tử thỏa điều kiện; kết quả vẫn là An và Chi.

| Hàm kiểm tra list | Ý nghĩa với các điều kiện xác định `true`/`false` |
|---|---|
| `any(x IN list WHERE condition)` | Có ít nhất một phần tử thỏa. |
| `all(x IN list WHERE condition)` | Mọi phần tử đều thỏa. |
| `none(x IN list WHERE condition)` | Không có phần tử nào thỏa. |
| `single(x IN list WHERE condition)` | Chính xác một phần tử thỏa. |

Với list rỗng, `any` và `single` cho `false`, còn `all` và `none` cho `true`; hãy xét hành vi này khi viết điều kiện kiểu “mọi thẻ đều hợp lệ”. Khi phần tử/điều kiện có `null`, các phép kiểm tra list cũng tuân theo logic ba giá trị trong các trường hợp chưa thể xác định kết quả.

## 12. Biểu thức map và truy cập property động

Map giúp nhóm các giá trị có tên:

```cypher
WITH {minAge: 25, requiredCity: 'Hà Nội'} AS f
MATCH (p:Person)
WHERE p.id IN ['c006-an', 'c006-binh', 'c006-chi', 'c006-dung']
  AND p.age >= f.minAge
  AND p.city = f.requiredCity
RETURN p.name AS ten;
```

Map `f` chứa hai khóa `minAge` và `requiredCity`. Kết quả là An và Chi.

Bạn cũng có thể truy cập property theo key động bằng biểu thức:

```cypher
MATCH (p:Person {id: 'c006-an'})
RETURN p[$propertyName] AS giaTri;
```

Nếu truyền tham số `{"propertyName": "city"}`, `giaTri = 'Hà Nội'`. `p[$propertyName]` là **truy cập property bằng khóa động**, khác với việc truyền một chuỗi để thay toàn bộ mệnh đề truy vấn.

Khi ứng dụng cho phép chọn property động, phải **giới hạn tập key được đọc** theo nghiệp vụ, nhất là với dữ liệu nhạy cảm. Tham số hóa giúp tách dữ liệu khỏi cú pháp truy vấn nhưng không thay thế phân quyền.

## 13. `CASE`: diễn đạt lựa chọn có điều kiện

Đôi khi cần trả một giá trị được tính theo nhiều trường hợp. `CASE` là biểu thức phù hợp:

```cypher
MATCH (p:Person)
WHERE p.id IN ['c006-an', 'c006-binh', 'c006-chi', 'c006-dung']
RETURN p.name AS ten,
       CASE
         WHEN p.score IS NULL THEN 'Chưa chấm'
         WHEN p.score >= 90 THEN 'Xuất sắc'
         WHEN p.score >= 80 THEN 'Đạt'
         ELSE 'Cần cải thiện'
       END AS xepLoai
ORDER BY ten;
```

| ten | xepLoai |
|---|---|
| An | Xuất sắc |
| Bình | Cần cải thiện |
| Chi | Đạt |
| Dũng | Chưa chấm |

`CASE` xét các nhánh `WHEN` theo thứ tự; nhánh đầu tiên có điều kiện `true` quyết định giá trị trả về. Nếu không có nhánh nào phù hợp và không có `ELSE`, kết quả là `null`.

### 13.1. `CASE` giúp nêu rõ các tình huống biên

Nếu Dũng thiếu điểm, đừng mặc định xếp Dũng vào nhóm “dưới 80” mà không kiểm tra `null`. Nhánh `WHEN p.score IS NULL` đặt trước làm rõ rằng “chưa có điểm” **khác** “điểm thấp”.

### 13.2. Dạng đơn giản khi chỉ so sánh bằng

```cypher
MATCH (pr:Project)
WHERE pr.id IN ['c006-api', 'c006-reco']
RETURN pr.name AS ten,
       CASE pr.status
         WHEN 'active' THEN 'Đang chạy'
         WHEN 'planned' THEN 'Đang lên kế hoạch'
         ELSE 'Khác'
       END AS trangThaiHienThi;
```

`CASE pr.status WHEN ...` phù hợp với so sánh giá trị bằng nhau. Khi yêu cầu có khoảng số, nhiều điều kiện hoặc kiểm tra `null`, dạng `CASE WHEN condition THEN ...` thường diễn đạt rõ hơn.

## 14. `EXISTS { ... }`: điều kiện trên sự tồn tại của mẫu đồ thị

Trong property graph, một yêu cầu phổ biến là “người nào **có** quan hệ tham gia dự án đang hoạt động”, nhưng ta không cần liệt kê từng relationship.

```cypher
MATCH (p:Person)
WHERE p.id IN ['c006-an', 'c006-binh', 'c006-chi', 'c006-dung']
  AND EXISTS {
    MATCH (p)-[:WORKS_ON]->(pr:Project)
    WHERE pr.status = 'active'
  }
RETURN p.name AS ten
ORDER BY ten;
```

Kết quả: **An, Bình**. Biến `p` bên trong biểu thức tồn tại liên quan đến `p` của dòng bên ngoài. Điều kiện kiểm tra **có ít nhất một mẫu thỏa**; nó không tạo hai dòng cho An chỉ vì An có thể có nhiều quan hệ khác.

### 14.1. So sánh với `MATCH` mở rộng rồi `DISTINCT`

Một cách khác:

```cypher
MATCH (p:Person)-[:WORKS_ON]->(pr:Project)
WHERE p.id IN ['c006-an', 'c006-binh', 'c006-chi', 'c006-dung']
  AND pr.status = 'active'
RETURN DISTINCT p.name AS ten
ORDER BY ten;
```

Kết quả hiện tại cũng là An, Bình. Nhưng về ngữ nghĩa:

- `EXISTS { ... }` diễn đạt **điều kiện tồn tại** trực tiếp trên mỗi người.
- `MATCH` mở rộng ra các dòng tương ứng relationship, rồi `DISTINCT` mới loại tên lặp.

Khi không cần thông tin của relationship, một biểu thức tồn tại thường diễn đạt ý định rõ hơn; hiệu năng thực tế vẫn phụ thuộc dữ liệu và kế hoạch Neo4j chọn.

### 14.2. Phủ định một điều kiện tồn tại

```cypher
MATCH (p:Person)
WHERE p.id IN ['c006-an', 'c006-binh', 'c006-chi', 'c006-dung']
  AND NOT EXISTS {
    MATCH (p)-[:WORKS_ON]->(:Project {status: 'active'})
  }
RETURN p.name AS ten
ORDER BY ten;
```

Kết quả: **Chi, Dũng**. Chi có dự án nhưng chỉ là `planned`; Dũng không có dự án. `NOT EXISTS` ở đây có nghĩa “không tồn tại dự án active được kết nối theo mẫu”, không phải “không có bất kỳ dự án nào”.

## 15. Điều kiện gắn với `MATCH`, `OPTIONAL MATCH` và `WITH`

Vị trí của `WHERE` quyết định **đối tượng bị loại**. Điều này đặc biệt quan trọng khi có relationship tùy chọn.

### 15.1. `WHERE` của `MATCH`

```cypher
MATCH (p:Person)-[w:WORKS_ON]->(pr:Project)
WHERE p.id IN ['c006-an', 'c006-binh', 'c006-chi', 'c006-dung']
  AND pr.status = 'active'
  AND w.role IN ['lead', 'developer']
RETURN p.name AS ten, pr.name AS duAn, w.role AS vaiTro
ORDER BY ten;
```

Kết quả: An – Graph API – lead; Bình – Graph API – developer. Chỉ các mẫu **đầy đủ** thỏa điều kiện được giữ.

### 15.2. `WHERE` của `OPTIONAL MATCH`

Yêu cầu: giữ cả bốn người, nhưng nếu có quan hệ tham gia dự án active với vai trò lead thì lấy dự án đó.

```cypher
MATCH (p:Person)
WHERE p.id IN ['c006-an', 'c006-binh', 'c006-chi', 'c006-dung']
OPTIONAL MATCH (p)-[w:WORKS_ON]->(pr:Project)
WHERE pr.status = 'active' AND w.role = 'lead'
RETURN p.name AS ten, pr.name AS duAnLead
ORDER BY ten;
```

| ten | duAnLead |
|---|---|
| An | Graph API |
| Bình | `null` |
| Chi | `null` |
| Dũng | `null` |

`WHERE` ngay sau `OPTIONAL MATCH` là điều kiện **của mẫu tùy chọn**. Người không có một match phù hợp vẫn giữ dòng đầu vào, còn biến mới như `pr` có giá trị `null`.

### 15.3. `WHERE` sau `WITH` lọc các dòng đã có

```cypher
MATCH (p:Person)
WHERE p.id IN ['c006-an', 'c006-binh', 'c006-chi', 'c006-dung']
OPTIONAL MATCH (p)-[w:WORKS_ON]->(pr:Project)
WITH p, w, pr
WHERE pr.status = 'active' AND w.role = 'lead'
RETURN p.name AS ten, pr.name AS duAnLead;
```

Chỉ còn **An**. Dòng Bình – Graph API có role developer nên bị lọc; Chi – Recommendation là planned; Dũng có `pr = null`. Điều kiện đặt sau `WITH` đã lọc **toàn bộ dòng**, không còn ý nghĩa giữ dòng tùy chọn khi không khớp.

Để diễn đạt đúng yêu cầu, hãy hỏi: “Tôi muốn **chỉ lấy những người** thỏa điều kiện, hay **giữ mọi người và tùy chọn thông tin liên quan**?” Câu trả lời quyết định vị trí đặt điều kiện.

## 16. Biểu thức sau `WITH` và phạm vi biến

`WITH` giúp tạo biến cho một giá trị đã tính và dùng tiếp trong `WHERE` hoặc `RETURN`.

```cypher
MATCH (p:Person)
WHERE p.id IN ['c006-an', 'c006-binh', 'c006-chi', 'c006-dung']
WITH p, p.score >= 80 AS diemDat
WHERE diemDat = true
RETURN p.name AS ten, p.score AS diem;
```

Kết quả: An (92), Chi (88). Dũng có `p.score = null`, vì vậy `diemDat` là `null` và không vượt qua `WHERE diemDat = true`.

Một biến chỉ còn trong phạm vi sau `WITH` nếu được **chuyển tiếp**:

```cypher
// Cố ý sai: p đã không được giữ qua WITH
MATCH (p:Person {id: 'c006-an'})
WITH p.score >= 80 AS diemDat
RETURN p.name AS ten, diemDat;
```

Phiên bản đúng:

```cypher
MATCH (p:Person {id: 'c006-an'})
WITH p, p.score >= 80 AS diemDat
RETURN p.name AS ten, diemDat;
```

`WITH` còn là nơi tổng hợp để tạo điều kiện trên kết quả đã đếm:

```cypher
MATCH (p:Person)
WHERE p.id IN ['c006-an', 'c006-binh', 'c006-chi', 'c006-dung']
OPTIONAL MATCH (p)-[:WORKS_ON]->(pr:Project)
WITH p, count(pr) AS soDuAn
WHERE soDuAn >= 2
RETURN p.name AS ten, soDuAn;
```

Chỉ An có hai dự án. `WHERE soDuAn >= 2` được thực hiện sau khi biểu thức tổng hợp tạo bí danh `soDuAn`.

## 17. Truyền tham số để điều kiện vừa an toàn vừa dễ tái sử dụng

Với ứng dụng Java, các giá trị thường thay đổi theo request: tuổi tối thiểu, thành phố, danh sách role, ngưỡng điểm. Hãy giữ cấu trúc Cypher ổn định và đưa giá trị vào tham số:

```cypher
MATCH (p:Person)-[w:WORKS_ON]->(pr:Project)
WHERE p.id IN $personIds
  AND p.age >= $minAge
  AND w.role IN $roles
  AND pr.status = $status
RETURN p.name AS ten, pr.name AS duAn, w.role AS vaiTro
ORDER BY ten;
```

Tham số mẫu:

```json
{
  "personIds": ["c006-an", "c006-binh", "c006-chi", "c006-dung"],
  "minAge": 25,
  "roles": ["lead", "developer"],
  "status": "active"
}
```

Kết quả: An – Graph API – lead; Bình – Graph API – developer. Các literal `Person`, `WORKS_ON`, `Project` là một phần cấu trúc mẫu, còn tham số mang **giá trị dữ liệu**.

### 17.1. Ví dụ truyền từ Java Driver

```java
import java.util.List;
import java.util.Map;

String cypher = """
    MATCH (p:Person)
    WHERE p.id IN $ids
      AND p.age >= $minAge
      AND (p.active = true OR p.score >= $minScore)
    RETURN p.name AS ten, p.age AS tuoi
    ORDER BY ten
    """;

Map<String, Object> params = Map.of(
    "ids", List.of("c006-an", "c006-binh", "c006-chi", "c006-dung"),
    "minAge", 25,
    "minScore", 85
);

// Giả sử session là org.neo4j.driver.Session đã mở.
var records = session.run(cypher, params)
                     .list(row -> row.get("ten").asString());
```

Kết quả là **An, Bình, Chi**:

- An: hoạt động, đủ tuổi, điểm cao.
- Bình: hoạt động và đủ tuổi; điểm dưới 85 vẫn đạt nhánh `OR`.
- Chi: không hoạt động, nhưng đủ tuổi và điểm 88 vượt ngưỡng.
- Dũng: không đủ 25 tuổi, nên bị loại dù đang hoạt động.

Không ghép các giá trị người dùng thành chuỗi Cypher như `"... p.age >= " + userInput`. Việc truyền qua map tham số giữ các giá trị ở đúng vị trí dữ liệu, giảm nguy cơ Cypher injection. Ứng dụng vẫn cần xác thực kiểu, miền giá trị và quyền truy cập.

### 17.2. Thiếu tham số khác với tham số bằng `null`

Nếu một truy vấn có `$city`:

- Map `{"city": null}` có key `city` với giá trị `null`.
- Map `{}` thiếu hẳn key; câu truy vấn yêu cầu `$city` sẽ không tự nhận `null`.

Với bộ lọc thành phố tùy chọn:

```cypher
MATCH (p:Person)
WHERE p.id IN $ids
  AND ($city IS NULL OR p.city = $city)
RETURN p.name AS ten;
```

Hãy truyền `city = null` khi muốn bỏ lọc thành phố, hoặc một tên thành phố khi muốn lọc. Điều kiện dùng ngoặc để nhóm nhánh tùy chọn và không ảnh hưởng điều kiện giới hạn `id`.

## 18. Tối ưu điều kiện mà vẫn giữ đúng ngữ nghĩa

Một điều kiện **đúng** phải cho kết quả đúng trước khi tối ưu. Khi đánh giá truy vấn:

1. **Đặt bộ lọc có ý nghĩa rõ ràng.** Chọn label/type và thuộc tính nghiệp vụ thay vì tìm toàn bộ graph rồi kiểm tra nhiều biểu thức tùy ý.
2. **Dùng tham số đúng kiểu.** So sánh kiểu ngày với ngày, số với số; tránh chuyển kiểu ngầm.
3. **Giữ điều kiện không làm thay đổi ý định khi thiếu property.** Đặc biệt xem xét `null`, `IS NULL` và `OPTIONAL MATCH`.
4. **Cẩn trọng với hàm trên property có index.** Ví dụ `toLower(p.name)` có thể khiến cách dùng index khác với điều kiện trên `p.name` nguyên bản. Chọn chiến lược chuẩn hóa và index theo yêu cầu tìm kiếm thực tế.
5. **Quan sát số dòng trung gian.** Một người có nhiều quan hệ khớp có thể sinh nhiều dòng; dùng `EXISTS` khi chỉ cần kiểm tra tồn tại.
6. **Kiểm tra kế hoạch thực thi.** `EXPLAIN` xem kế hoạch ước lượng; `PROFILE` thực thi và cung cấp số liệu thực tế.

Ví dụ:

```cypher
EXPLAIN
MATCH (p:Person)
WHERE p.id = $personId
  AND p.age >= $minAge
RETURN p.name AS ten;
```

Câu lệnh cần được chạy với bộ tham số có `personId`, `minAge`. Index hoặc uniqueness constraint trên `Person.id` thường hữu ích cho truy vấn bắt đầu từ ID nghiệp vụ; điều này không thay thế việc kiểm tra độ đúng của điều kiện logic.

**Không nên dựa vào việc `AND`/`OR` được đánh giá theo thứ tự vật lý từ trái sang phải** để tạo cơ chế phòng lỗi. Cypher là khai báo và trình tối ưu có thể chọn kế hoạch thực thi phù hợp. Nếu cần xử lý trường hợp nguy hiểm như mẫu số 0 hay giá trị thiếu, hãy diễn đạt rõ bằng `CASE` hoặc điều kiện tương ứng.

## 19. Bài toán tổng hợp: lọc nhân sự theo tiêu chí nghiệp vụ

**Yêu cầu:** Trong danh sách nhân sự được chọn, chỉ xét người từ 25 tuổi. Giữ những người **đang hoạt động và có dự án active thuộc vai trò được phép**, hoặc **có điểm từ ngưỡng cao**. Trả tên, thành phố hiển thị, số dự án phù hợp và nhóm kết quả.

```cypher
MATCH (p:Person)
WHERE p.id IN $ids
  AND p.age >= $minAge
OPTIONAL MATCH (p)-[w:WORKS_ON]->(pr:Project)
WHERE pr.status = $status
  AND w.role IN $roles
WITH p,
     count(pr) AS soDuAnPhuHop,
     collect(DISTINCT pr.name) AS dsDuAnPhuHop
WHERE (p.active = true AND soDuAnPhuHop >= 1)
   OR (p.score IS NOT NULL AND p.score >= $minScore)
RETURN p.name AS ten,
       coalesce(p.city, 'Chưa cập nhật') AS thanhPho,
       soDuAnPhuHop,
       dsDuAnPhuHop,
       CASE
         WHEN soDuAnPhuHop >= 1 THEN 'Có dự án phù hợp'
         ELSE 'Đạt ngưỡng điểm'
       END AS lyDo
ORDER BY soDuAnPhuHop DESC, ten ASC;
```

Tham số:

```json
{
  "ids": ["c006-an", "c006-binh", "c006-chi", "c006-dung"],
  "minAge": 25,
  "status": "active",
  "roles": ["lead", "developer"],
  "minScore": 85
}
```

**Diễn giải từng giai đoạn:**

| Giai đoạn | Điều kiện và tác dụng | Kết quả với dữ liệu mẫu |
|---|---|---|
| `MATCH` và `WHERE` đầu | Chọn ID hợp lệ, tuổi từ 25 | An, Bình, Chi; loại Dũng |
| `OPTIONAL MATCH` + `WHERE` | Tìm dự án active với role thuộc list | An – Graph API; Bình – Graph API; Chi – `null` |
| `WITH` | Gom theo `p` và đếm dự án phù hợp | An 1, Bình 1, Chi 0 |
| `WHERE` sau `WITH` | Kiểm tra nhóm điều kiện hoạt động/dự án **hoặc** điểm cao | Giữ cả An, Bình, Chi |
| `RETURN` | Tạo cột, thay `null` hiển thị, chọn nhãn `lyDo` | 3 dòng cuối |

| ten | thanhPho | soDuAnPhuHop | dsDuAnPhuHop | lyDo |
|---|---|---:|---|---|
| An | Hà Nội | 1 | `['Graph API']` | Có dự án phù hợp |
| Bình | TP. Hồ Chí Minh | 1 | `['Graph API']` | Có dự án phù hợp |
| Chi | Hà Nội | 0 | `[]` | Đạt ngưỡng điểm |

Vì `WITH` đã gom theo `p`, số dòng cuối là **mỗi người một dòng**, không phải mỗi relationship một dòng. `OPTIONAL MATCH` giữ được Chi dù cô ấy không có dự án active. Ngưỡng điểm cao cho phép Chi được giữ bởi nhánh thứ hai của `OR`. Ngoặc khiến phạm vi của từng nhánh được thể hiện rõ.

## 20. Những lỗi điều kiện thường gặp

| Lỗi | Vì sao sai hoặc khó hiểu | Viết rõ hơn |
|---|---|---|
| `p.age >= 25 OR p.active = true AND p.city = 'Hà Nội'` | `AND` có ưu tiên cao hơn `OR`; dễ hiểu khác yêu cầu. | Viết rõ `(p.age >= 25 OR p.active = true) AND p.city = 'Hà Nội'` hoặc nhóm theo đúng nghiệp vụ. |
| `p.city = null` | So sánh với null không cho `true`. | `p.city IS NULL`. |
| `p.city <> 'Hà Nội'` để tìm cả người chưa có city | Thiếu property tạo `null` và bị lọc. | `p.city <> 'Hà Nội' OR p.city IS NULL`. |
| `p.age >= '25'` | Chuỗi khác số. | Dùng literal số `25` hoặc tham số số. |
| `p.id IN [$ids]` với `$ids` đã là list | Tạo list lồng nhau. | `p.id IN $ids`. |
| `p.name = '$name'` | Đang so với chuỗi ký tự `$name`. | `p.name = $name`. |
| `WHERE p.tags CONTAINS 'graph'` | `CONTAINS` là phép tìm chuỗi con, không phải kiểm tra phần tử list. | `'graph' IN coalesce(p.tags, [])`. |
| `NOT p.active = true AND p.age >= 30` | Phạm vi phủ định không rõ cho người đọc. | `NOT (p.active = true AND p.age >= 30)` nếu phủ định cả nhóm. |
| `OPTIONAL MATCH` rồi lọc property tùy chọn sau `WITH` | Làm mất dòng `null` đã được giữ. | Gắn điều kiện với `OPTIONAL MATCH` nếu cần bảo toàn dòng. |
| Dùng `MATCH` nhiều quan hệ rồi trả node không gom nhóm | Một node khớp nhiều cạnh tạo nhiều dòng. | Dùng `EXISTS` khi chỉ cần điều kiện tồn tại; tổng hợp/`DISTINCT` khi đúng mục tiêu. |
| Đưa một chuỗi `"p.age DESC"` vào `$sortBy` rồi nghĩ nó trở thành mã sắp xếp | Tham số mang dữ liệu, không thay cấu trúc cú pháp. | Chọn các truy vấn/biểu thức được ứng dụng cho phép. |
| Chỉ dùng `coalesce(p.score, 0)` mà bỏ qua ý nghĩa “chưa có điểm” | Đồng nhất giá trị thiếu với điểm thật bằng 0. | Dùng `IS NULL` và `CASE` nếu hai trường hợp khác nhau. |

## 21. Bài tập tự luyện

Các bài dưới đây sử dụng dữ liệu ở mục 3. Hãy tự dự đoán kết quả, sau đó đối chiếu đáp án.

### Bài 1. Thứ tự ưu tiên của `AND` và `OR`

Truy vấn sau khác gì khi thêm ngoặc quanh nhánh `OR`?

```cypher
MATCH (p:Person)
WHERE p.id IN ['c006-an', 'c006-binh', 'c006-chi', 'c006-dung']
  AND p.active = true OR p.age >= 30
RETURN p.name AS ten
ORDER BY ten;
```

<details>
<summary>Đáp án tham khảo</summary>

Do `AND` ưu tiên hơn `OR`, truy vấn có thể lấy người từ 30 tuổi **ngoài danh sách ID**, nếu database có dữ liệu khác. Trên bộ mẫu, cả bốn người đều thỏa `active = true` hoặc `age >= 30`. Nếu muốn **chỉ xét bốn ID** rồi áp dụng một trong hai tiêu chí, viết:

```cypher
MATCH (p:Person)
WHERE p.id IN ['c006-an', 'c006-binh', 'c006-chi', 'c006-dung']
  AND (p.active = true OR p.age >= 30)
RETURN p.name AS ten
ORDER BY ten;
```

Trên bộ mẫu vẫn là An, Bình, Chi, Dũng, nhưng phạm vi ID được bảo toàn rõ ràng.

</details>

### Bài 2. `null` và toán tử khác

Truy vấn `WHERE p.city <> 'Hà Nội'` lấy những ai? Viết lại để lấy cả người thiếu `city`.

<details>
<summary>Đáp án tham khảo</summary>

Điều kiện gốc chỉ chọn **Bình**; Dũng có `p.city = null` nên phép `<>` cho `null`.

```cypher
MATCH (p:Person)
WHERE p.id IN ['c006-an', 'c006-binh', 'c006-chi', 'c006-dung']
  AND (p.city <> 'Hà Nội' OR p.city IS NULL)
RETURN p.name AS ten
ORDER BY ten;
```

Kết quả mới: **Bình, Dũng**.

</details>

### Bài 3. Kiểm tra list bằng `IN`

Tìm người có tag `'graph'`, kể cả khi một người không có property `tags`.

<details>
<summary>Đáp án tham khảo</summary>

```cypher
MATCH (p:Person)
WHERE p.id IN ['c006-an', 'c006-binh', 'c006-chi', 'c006-dung']
  AND 'graph' IN coalesce(p.tags, [])
RETURN p.name AS ten
ORDER BY ten;
```

Kết quả: **An, Chi**. Dũng được xử lý bằng danh sách rỗng nhưng không thỏa điều kiện.

</details>

### Bài 4. Phân loại điểm bằng `CASE`

Viết một biểu thức cho điểm từ 90 là “Xuất sắc”, từ 80 đến dưới 90 là “Đạt”, dưới 80 là “Cần cải thiện”, thiếu điểm là “Chưa chấm”.

<details>
<summary>Đáp án tham khảo</summary>

```cypher
MATCH (p:Person)
WHERE p.id IN ['c006-an', 'c006-binh', 'c006-chi', 'c006-dung']
RETURN p.name AS ten,
       CASE
         WHEN p.score IS NULL THEN 'Chưa chấm'
         WHEN p.score >= 90 THEN 'Xuất sắc'
         WHEN p.score >= 80 THEN 'Đạt'
         ELSE 'Cần cải thiện'
       END AS loai
ORDER BY ten;
```

An: Xuất sắc; Bình: Cần cải thiện; Chi: Đạt; Dũng: Chưa chấm.

</details>

### Bài 5. Điều kiện tồn tại relationship

Tìm những người **có ít nhất một dự án active**, trả một dòng cho mỗi người. Hãy dùng `EXISTS { ... }`.

<details>
<summary>Đáp án tham khảo</summary>

```cypher
MATCH (p:Person)
WHERE p.id IN ['c006-an', 'c006-binh', 'c006-chi', 'c006-dung']
  AND EXISTS {
    MATCH (p)-[:WORKS_ON]->(pr:Project)
    WHERE pr.status = 'active'
  }
RETURN p.name AS ten
ORDER BY ten;
```

Kết quả: **An, Bình**.

</details>

### Bài 6. Vị trí điều kiện với `OPTIONAL MATCH`

Viết truy vấn giữ **cả bốn người**, nhưng cột dự án chỉ lấy dự án active mà người đó có vai trò `'lead'`. Với người không khớp, cột dự án phải là `null`.

<details>
<summary>Đáp án tham khảo</summary>

```cypher
MATCH (p:Person)
WHERE p.id IN ['c006-an', 'c006-binh', 'c006-chi', 'c006-dung']
OPTIONAL MATCH (p)-[w:WORKS_ON]->(pr:Project)
WHERE pr.status = 'active' AND w.role = 'lead'
RETURN p.name AS ten, pr.name AS duAnLead
ORDER BY ten;
```

An – Graph API; Bình – `null`; Chi – `null`; Dũng – `null`. Đặt `WHERE` ngay sau `OPTIONAL MATCH` để điều kiện áp dụng vào mẫu tùy chọn.

</details>

### Bài 7. Sửa lỗi ngữ nghĩa với `IN`

Ứng dụng truyền `{"ids": ["c006-an", "c006-chi"]}`. Vì sao `WHERE p.id IN [$ids]` không diễn đạt đúng yêu cầu? Viết lại câu truy vấn.

<details>
<summary>Đáp án tham khảo</summary>

`$ids` là list; `[$ids]` là list **một phần tử mà phần tử đó lại là list**. Cách đúng:

```cypher
MATCH (p:Person)
WHERE p.id IN $ids
RETURN p.name AS ten
ORDER BY ten;
```

Kết quả: An, Chi.

</details>

### Bài 8. Phân tích một biểu thức ba giá trị

Dự đoán kết quả của:

```cypher
RETURN false AND null AS a,
       true OR null AS b,
       null = null AS c,
       NOT null AS d;
```

<details>
<summary>Đáp án</summary>

`a = false`, `b = true`, `c = null`, `d = null`. Bởi `false AND ...` chắc chắn sai, `true OR ...` chắc chắn đúng; so sánh và phủ định `null` vẫn không xác định.

</details>

### Bài 9. Suy luận hai yêu cầu nghiệp vụ khác nhau

Với hai điều kiện:

```cypher
// A
(p.active = true OR p.age >= 30) AND p.city = 'Hà Nội'

// B
p.active = true OR (p.age >= 30 AND p.city = 'Hà Nội')
```

Hãy giải thích tập kết quả trên bốn người mẫu.

<details>
<summary>Đáp án</summary>

- **A:** chỉ **An và Chi** vì yêu cầu thành phố Hà Nội cho cả hai nhánh.
- **B:** **An, Bình, Chi, Dũng** vì ai đang active đều thỏa, còn Chi thỏa nhánh tuổi và thành phố.

Ngoặc làm rõ phạm vi của ràng buộc thành phố; đây là khác biệt nghiệp vụ, không chỉ khác cách trình bày.

</details>

## 22. Ghi nhớ

Trong Cypher, mỗi biểu thức trả về một giá trị từ biến, literal, tham số, property, lời gọi hàm hoặc các toán tử. `WHERE` chỉ giữ những dòng có điều kiện `true`; khi property thiếu, `null` làm nhiều phép so sánh trở thành **không xác định**, vì vậy phải dùng `IS NULL`, `IS NOT NULL` hoặc xử lý `coalesce` theo đúng nghiệp vụ.

Với điều kiện phức tạp, hãy ưu tiên **ngoặc thể hiện rõ ý nghĩa**: `NOT`, `AND`, `XOR` và `OR` có thứ tự ưu tiên khác nhau, và một thay đổi ngoặc có thể làm thay đổi nhóm nhân sự hoặc mối quan hệ được chọn. Các biểu thức `CASE`, `IN`, `any` và `EXISTS { ... }` giúp mô tả các yêu cầu cụ thể, đặc biệt trong mô hình property graph của Neo4j. Khi đưa truy vấn vào Java Driver hoặc Spring Data Neo4j, tiếp tục truyền giá trị qua tham số, kiểm soát kiểu dữ liệu, số dòng kết quả và đánh giá kế hoạch thực thi khi cần tối ưu.
