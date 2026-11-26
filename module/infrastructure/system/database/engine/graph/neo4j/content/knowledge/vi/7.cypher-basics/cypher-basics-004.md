# Luồng bảng trung gian, số hàng kết quả và phạm vi biến trong Cypher

> **Chương:** Nền tảng Cypher  
> **Ngữ cảnh module:** Neo4j lưu dữ liệu dạng *property graph* gồm node, relationship và property. Khi viết Cypher để truy vấn quan hệ hoặc đường đi, điều quan trọng không chỉ là mẫu đồ thị có khớp hay không mà còn là **mỗi mệnh đề làm thay đổi bao nhiêu dòng dữ liệu và biến nào còn sử dụng được**. Những nguyên lý này là nền tảng để đọc kết quả, tối ưu truy vấn và xử lý bản ghi từ Java Driver hoặc Spring Data Neo4j.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Hình dung một câu truy vấn Cypher như luồng các **bảng trung gian gồm nhiều dòng và cột**.
2. Dự đoán số dòng sau `MATCH`, `WHERE`, `OPTIONAL MATCH`, `UNWIND`, `WITH`, `DISTINCT` và `LIMIT`.
3. Giải thích vì sao một node đầu vào có thể tạo nhiều dòng khi khớp nhiều relationship.
4. Phân biệt `count(*)`, `count(x)`, `count(DISTINCT x)` và ảnh hưởng của `null`.
5. Biết biến nào được truyền qua `WITH`, khi nào biến mất khỏi phạm vi, và vai trò của bí danh `AS`.
6. Điều khiển **độ hạt** của kết quả bằng khóa nhóm, phép tổng hợp và vị trí đặt `ORDER BY`/`LIMIT`.
7. Nhận ra truy vấn làm bùng nổ dòng do tích Descartes hoặc do mở rộng nhiều nhánh quan hệ.

## 2. Mô hình tư duy: mỗi giai đoạn nhận và phát các dòng

Cypher là ngôn ngữ **khai báo**: ta viết mẫu cần tìm và kết quả mong muốn, Neo4j chọn kế hoạch thực thi. Để **lý giải ngữ nghĩa**, có thể tưởng tượng các mệnh đề lần lượt làm việc trên một bảng kết quả trung gian:

```text
MATCH ...       -> tạo / mở rộng dòng bằng mẫu đồ thị
WHERE ...       -> giữ những dòng thỏa điều kiện
OPTIONAL MATCH  -> mở rộng nếu khớp; nếu không thì giữ dòng với null
WITH ...        -> chọn cột, tạo biểu thức, gom nhóm, lọc, sắp xếp
MATCH ...       -> dùng lại các biến còn trong phạm vi và mở rộng tiếp
RETURN ...      -> tạo các cột kết quả trả cho bên gọi
```

Đây là **mô hình logic** để hiểu câu truy vấn. Neo4j không nhất thiết tạo các bảng vật lý riêng sau mỗi mệnh đề: trình tối ưu có thể dùng pipeline, operator, index và những chiến lược thực thi khác. Các phép toán có thể được lên kế hoạch lại khi vẫn giữ ngữ nghĩa của truy vấn.

### 2.1. Một dòng là một bộ giá trị gắn với biến

Ví dụ:

```cypher
MATCH (p:Person)-[w:WORKS_ON]->(pr:Project)
RETURN p.name AS nhanSu, w.role AS vaiTro, pr.name AS duAn;
```

Ngay sau `MATCH`, một dòng có thể chứa:

| Biến `p` | Biến `w` | Biến `pr` |
|---|---|---|
| Node An | Relationship WORKS_ON (role = lead) | Node Graph API |
| Node An | Relationship WORKS_ON (role = advisor) | Node Recommendation |
| Node Bình | Relationship WORKS_ON (role = developer) | Node Graph API |

Mỗi cột trung gian có thể chứa **node, relationship, path, chuỗi, số, list, map hoặc `null`**. Một biến như `p` không “chỉ giữ một người duy nhất cho cả truy vấn”: nó có thể có giá trị khác nhau giữa các dòng; cùng một node cũng có thể xuất hiện ở nhiều dòng.

**Khái niệm độ hạt (*granularity*):** Truy vấn đang trả “một dòng cho mỗi node”, “một dòng cho mỗi quan hệ” hay “một dòng cho mỗi nhóm”? Việc nêu rõ độ hạt trước khi viết câu truy vấn giúp tránh đếm sai và tạo kết quả trùng.

## 3. Dữ liệu mẫu xuyên suốt bài

Để đối chiếu chính xác số dòng, dùng **database thực hành** với dữ liệu sau. Các ID có tiền tố `c004-` để dễ nhận diện. Các kết quả đếm trong bài giả định không có node/relationship trùng ID và không có quan hệ bổ sung nối vào các node mẫu.

```cypher
MERGE (an:Person {id: 'c004-an'})
SET an.name = 'An', an.age = 30

MERGE (binh:Person {id: 'c004-binh'})
SET binh.name = 'Bình', binh.age = 27

MERGE (chi:Person {id: 'c004-chi'})
SET chi.name = 'Chi', chi.age = 35

MERGE (dung:Person {id: 'c004-dung'})
SET dung.name = 'Dũng', dung.age = 24

MERGE (api:Project {id: 'c004-api'})
SET api.name = 'Graph API', api.status = 'active'

MERGE (reco:Project {id: 'c004-reco'})
SET reco.name = 'Recommendation', reco.status = 'planned'

MERGE (pipeline:Project {id: 'c004-pipeline'})
SET pipeline.name = 'Data Pipeline', pipeline.status = 'active'

MERGE (an)-[wa:WORKS_ON]->(api)
SET wa.role = 'lead'
MERGE (an)-[wb:WORKS_ON]->(reco)
SET wb.role = 'advisor'
MERGE (binh)-[wc:WORKS_ON]->(api)
SET wc.role = 'developer'
MERGE (chi)-[wd:WORKS_ON]->(reco)
SET wd.role = 'lead'

MERGE (an)-[:KNOWS]->(binh)
MERGE (binh)-[:KNOWS]->(chi);
```

Sơ đồ rút gọn:

```text
An   ──WORKS_ON──> Graph API       (active)
  └──WORKS_ON──> Recommendation   (planned)
Bình ─WORKS_ON──> Graph API       (active)
Chi  ─WORKS_ON──> Recommendation  (planned)
Dũng   (chưa tham gia dự án)

Data Pipeline (active)             (chưa có nhân sự)
An ──KNOWS──> Bình ──KNOWS──> Chi
```

**Bảng chuẩn để tự kiểm tra:**

| Đối tượng | Số lượng |
|---|---:|
| Node `Person` của bộ mẫu | 4 |
| Node `Project` của bộ mẫu | 3 |
| Relationship `WORKS_ON` của bộ mẫu | 4 |
| Relationship `KNOWS` của bộ mẫu | 2 |
| Người có ít nhất một dự án | 3 |
| Người chưa có dự án | 1 (Dũng) |
| Dự án chưa có nhân sự | 1 (Data Pipeline) |

Trong truy vấn thực hành, chúng ta thường dùng:

```cypher
MATCH (p:Person)
WHERE p.id IN ['c004-an', 'c004-binh', 'c004-chi', 'c004-dung']
RETURN p.name AS ten;
```

Điều kiện `WHERE` bảo đảm chỉ xét bốn người của bài, ngay cả khi database có dữ liệu `Person` khác. Nếu thực hành trên database đã có thêm cạnh nối các node mẫu, số dòng khi mở rộng quan hệ sẽ thay đổi theo dữ liệu thực tế.

## 4. `MATCH`: từ một dòng sang nhiều dòng

### 4.1. Bắt đầu bằng một tập node

```cypher
MATCH (p:Person)
WHERE p.id IN ['c004-an', 'c004-binh', 'c004-chi', 'c004-dung']
RETURN p.name AS ten
ORDER BY ten;
```

Sau `MATCH` và `WHERE`, có **4 dòng**:

| Dòng | `p` |
|---:|---|
| 1 | Node An |
| 2 | Node Bình |
| 3 | Node Chi |
| 4 | Node Dũng |

`RETURN p.name` chuyển node ở mỗi dòng thành cột chuỗi; bản thân việc chọn thuộc tính không mặc định gộp các dòng.

### 4.2. Mở rộng một relationship

```cypher
MATCH (p:Person)
WHERE p.id IN ['c004-an', 'c004-binh', 'c004-chi', 'c004-dung']
MATCH (p)-[w:WORKS_ON]->(pr:Project)
RETURN p.name AS nguoi, w.role AS vaiTro, pr.name AS duAn
ORDER BY nguoi, duAn;
```

Mệnh đề `MATCH` thứ hai được áp dụng với những giá trị `p` đã ràng buộc:

| `p` đầu vào | Số relationship khớp | Dòng đầu ra |
|---|---:|---|
| An | 2 | An – Graph API; An – Recommendation |
| Bình | 1 | Bình – Graph API |
| Chi | 1 | Chi – Recommendation |
| Dũng | 0 | Không còn dòng của Dũng |
| **Tổng** | **4** | **4 dòng** |

Số node đầu vào là 4; số dòng sau mở rộng cũng bằng 4 **chỉ là trùng hợp**. Một lần mở rộng có thể tăng hoặc giảm số dòng vì một dòng đầu vào có thể khớp 0, 1 hoặc nhiều relationship.

Mô hình tổng quát khi mỗi dòng đầu vào `i` khớp `m_i` mẫu:

\[
\text{Số dòng sau MATCH} = \sum_{i=1}^{n} m_i
\]

Ví dụ trên: `2 + 1 + 1 + 0 = 4`.

### 4.3. Lọc trước khi mở rộng làm thay đổi số dòng

```cypher
MATCH (p:Person)
WHERE p.id IN ['c004-an', 'c004-binh', 'c004-chi', 'c004-dung']
  AND p.age >= 30
MATCH (p)-[:WORKS_ON]->(pr:Project)
RETURN p.name AS nguoi, pr.name AS duAn;
```

Sau `WHERE` chỉ còn **An và Chi** (2 dòng); sau `MATCH` mở rộng thành **3 dòng**: An có hai dự án, Chi có một. Đừng lấy số người khớp điều kiện làm số dòng cuối nếu còn nối quan hệ ở bước sau.

## 5. `WHERE`: loại dòng hoặc ràng buộc mẫu

Trong truy vấn đọc cơ bản, điều kiện `WHERE` gắn với `MATCH` giúp giới hạn mẫu cần khớp:

```cypher
MATCH (p:Person)-[:WORKS_ON]->(pr:Project)
WHERE p.id IN ['c004-an', 'c004-binh', 'c004-chi', 'c004-dung']
  AND pr.status = 'active'
RETURN p.name AS nguoi, pr.name AS duAn
ORDER BY nguoi;
```

Trong bốn cạnh `WORKS_ON`, chỉ hai cạnh dẫn đến dự án `active`. Kết quả:

| nguoi | duAn |
|---|---|
| An | Graph API |
| Bình | Graph API |

Nếu điều kiện là `WHERE p.age > 30`, chỉ Chi đạt tuổi nhưng dự án của Chi có trạng thái `planned`; khi kết hợp thêm điều kiện `pr.status = 'active'`, không còn dòng nào.

Ở mức logic, có thể tưởng tượng `WHERE` giữ dòng mà biểu thức điều kiện là `true`. Trong Cypher, một biểu thức liên quan đến `null` có thể cho kết quả `null` (không phải `true`), nên dòng đó cũng bị loại khi lọc.

## 6. `OPTIONAL MATCH`: giữ dòng với `null`

Khác với `MATCH` bắt buộc khớp, `OPTIONAL MATCH` giữ mỗi dòng đầu vào ngay cả khi **không tìm được** kết nối, bằng cách gán `null` cho biến mới không khớp.

```cypher
MATCH (p:Person)
WHERE p.id IN ['c004-an', 'c004-binh', 'c004-chi', 'c004-dung']
OPTIONAL MATCH (p)-[:WORKS_ON]->(pr:Project)
RETURN p.name AS nguoi, pr.name AS duAn
ORDER BY nguoi, duAn;
```

| nguoi | duAn |
|---|---|
| An | Graph API |
| An | Recommendation |
| Bình | Graph API |
| Chi | Recommendation |
| Dũng | `null` |

Kết quả có **5 dòng**. `OPTIONAL MATCH` không đồng nghĩa “mỗi người luôn chỉ ra một dòng”: An vẫn tạo hai dòng, nhưng Dũng giữ một dòng chứa `null` thay vì bị loại.

Với số mẫu khớp `m_i` của mỗi dòng đầu vào:

\[
\text{Số dòng sau OPTIONAL MATCH} = \sum_{i=1}^{n}\max(1,m_i)
\]

Trong ví dụ: `max(1,2) + max(1,1) + max(1,1) + max(1,0) = 5`.

### 6.1. `WHERE` đi cùng `OPTIONAL MATCH`

Yêu cầu: giữ **tất cả nhân sự**, nhưng chỉ đi theo các cạnh dẫn tới dự án đang chạy.

```cypher
MATCH (p:Person)
WHERE p.id IN ['c004-an', 'c004-binh', 'c004-chi', 'c004-dung']
OPTIONAL MATCH (p)-[:WORKS_ON]->(pr:Project)
WHERE pr.status = 'active'
RETURN p.name AS nguoi, pr.name AS duAnDangChay
ORDER BY nguoi;
```

`WHERE pr.status = 'active'` ở đây **thuộc mẫu tùy chọn**. An và Bình khớp `Graph API`; Chi và Dũng không có dự án `active`, nhưng vẫn còn một dòng `null`:

| nguoi | duAnDangChay |
|---|---|
| An | Graph API |
| Bình | Graph API |
| Chi | `null` |
| Dũng | `null` |

### 6.2. Đặt điều kiện sau `WITH` lại có ý nghĩa khác

```cypher
MATCH (p:Person)
WHERE p.id IN ['c004-an', 'c004-binh', 'c004-chi', 'c004-dung']
OPTIONAL MATCH (p)-[:WORKS_ON]->(pr:Project)
WITH p, pr
WHERE pr.status = 'active'
RETURN p.name AS nguoi, pr.name AS duAnDangChay
ORDER BY nguoi;
```

Lúc này `WHERE` **lọc các dòng sau `WITH`**. Nó loại Chi vì `Recommendation` là `planned`, loại Dũng vì `pr = null` và loại dòng An – Recommendation. Kết quả chỉ còn **2 dòng** (An, Bình).

| Điều kiện đặt ở đâu? | Ý nghĩa | Có giữ Chi và Dũng? |
|---|---|---|
| Ngay sau `OPTIONAL MATCH` | Ràng buộc mẫu được tìm tùy chọn | Có, với `pr = null` |
| Sau `WITH p, pr` | Lọc toàn bộ bảng trung gian đã có | Không |

Đây là khác biệt quan trọng khi viết báo cáo cần giữ cả người không có quan hệ phù hợp.

## 7. `WITH`: ranh giới phạm vi biến và giai đoạn xử lý

`WITH` giống phép **chiếu cột** cộng với khả năng tính biểu thức, gom nhóm và giới hạn dòng. Nó phân chia câu truy vấn thành các giai đoạn có **phạm vi biến** rõ ràng.

### 7.1. Chỉ biến được chuyển tiếp mới còn dùng được

```cypher
MATCH (p:Person)
WHERE p.id = 'c004-an'
WITH p.name AS ten, p.age AS tuoi
RETURN ten, tuoi;
```

`WITH p.name AS ten, p.age AS tuoi` tạo hai cột mang giá trị chuỗi và số. Từ sau `WITH`, chỉ `ten` và `tuoi` còn trong phạm vi; biến node `p` **không được chuyển tiếp**.

Ví dụ **cố ý sai**:

```cypher
// Sai: p đã ra khỏi phạm vi
MATCH (p:Person {id: 'c004-an'})
WITH p.name AS ten
RETURN p.age AS tuoi;
```

Sửa bằng cách giữ `p`:

```cypher
MATCH (p:Person {id: 'c004-an'})
WITH p, p.name AS ten
RETURN ten, p.age AS tuoi;
```

Hoặc lấy sẵn thuộc tính cần dùng rồi truyền tiếp, như câu hợp lệ đầu tiên.

### 7.2. Bí danh `AS` thay đổi tên cột/biến

```cypher
MATCH (p:Person {id: 'c004-an'})
WITH p AS nhanSu
RETURN nhanSu.name AS ten;
```

`p AS nhanSu` giữ nguyên giá trị node nhưng **đổi tên biến** sang `nhanSu`; ở phần sau, tên `p` không còn trong phạm vi. Ngược lại, `WITH p.name AS nhanSu` cho ra một **chuỗi**, không phải node; `nhanSu.age` không còn ý nghĩa truy cập thuộc tính người.

### 7.3. Giữ nhiều biến khi cần mở rộng tiếp

```cypher
MATCH (p:Person {id: 'c004-an'})-[r:KNOWS]->(friend:Person)
WITH p, friend
MATCH (p)-[:WORKS_ON]->(pr:Project)
RETURN friend.name AS ban, pr.name AS duAn
ORDER BY duAn;
```

Sau `WITH p, friend`, `p` và `friend` vẫn còn, còn `r` không. Vì An có một người bạn đi ra và hai dự án, truy vấn trả **2 dòng**:

| ban | duAn |
|---|---|
| Bình | Graph API |
| Bình | Recommendation |

Nếu cần trả `r.since` ở cuối, phải truyền `r` qua `WITH`. Trái lại, không cần giữ `r` khi chỉ muốn nối tiếp node `p` và `friend`.

### 7.4. `WITH *` và lựa chọn phạm vi rõ ràng

`WITH *` truyền tiếp tất cả biến hiện có. Nó thuận tiện khi thử nghiệm:

```cypher
MATCH (p:Person {id: 'c004-an'})-[:WORKS_ON]->(pr:Project)
WITH *
RETURN p.name AS nguoi, pr.name AS duAn;
```

Trong truy vấn lớn, nên liệt kê rõ `WITH p, pr` hoặc những cột cần dùng. Cách đó giúp thấy được phạm vi, tránh vô tình giữ các biến không cần thiết và làm sai **mức gom nhóm** ở những bước có phép tổng hợp.

### 7.5. Tên biến và tham số không giống nhau

```cypher
MATCH (p:Person)
WHERE p.id = $personId
RETURN p.name AS ten;
```

`p` là biến gắn với node ở các dòng; `$personId` là tham số do Neo4j Browser hoặc ứng dụng Java gửi vào, ví dụ `'c004-an'`. Tham số cung cấp **giá trị dữ liệu** và không làm biến `p` tồn tại ngoài phạm vi `WITH`.

## 8. Phép tổng hợp thay đổi số dòng và độ hạt

`count`, `sum`, `avg`, `collect`, `min` và `max` là các hàm tổng hợp thường gặp. Trong `WITH` hay `RETURN`, chúng tạo **một dòng trên mỗi nhóm** xác định bởi các biểu thức không tổng hợp trong cùng mệnh đề.

### 8.1. Trước khi gom nhóm: một người có thể nhiều dòng

```cypher
MATCH (p:Person)
WHERE p.id IN ['c004-an', 'c004-binh', 'c004-chi', 'c004-dung']
OPTIONAL MATCH (p)-[:WORKS_ON]->(pr:Project)
RETURN p.name AS nguoi, pr.name AS duAn
ORDER BY nguoi, duAn;
```

Kết quả có **5 dòng** như mục 6, trong đó An xuất hiện hai lần.

### 8.2. Gom nhóm để trở thành một dòng cho mỗi người

```cypher
MATCH (p:Person)
WHERE p.id IN ['c004-an', 'c004-binh', 'c004-chi', 'c004-dung']
OPTIONAL MATCH (p)-[:WORKS_ON]->(pr:Project)
WITH p, count(pr) AS soDuAn, collect(pr.name) AS tenDuAn
RETURN p.name AS nguoi, soDuAn, tenDuAn
ORDER BY nguoi;
```

| nguoi | soDuAn | tenDuAn |
|---|---:|---|
| An | 2 | `['Graph API', 'Recommendation']` |
| Bình | 1 | `['Graph API']` |
| Chi | 1 | `['Recommendation']` |
| Dũng | 0 | `[]` |

Thứ tự phần tử trong danh sách của An có thể thay đổi nếu chưa xác định thứ tự đầu vào. Điều chắc chắn là `collect(pr.name)` chứa hai tên dự án, còn `collect` bỏ qua các giá trị `null` nên Dũng có danh sách rỗng.

**Diễn giải:** Trong `WITH p, count(pr), collect(pr.name)`, `p` là khóa nhóm. Từ 5 dòng trung gian, truy vấn tạo **4 nhóm**, mỗi nhóm một dòng.

### 8.3. Vì sao giữ thêm `pr` có thể làm đếm sai?

So sánh:

```cypher
MATCH (p:Person {id: 'c004-an'})-[:WORKS_ON]->(pr:Project)
WITH p, count(pr) AS soDuAn
RETURN p.name AS nguoi, soDuAn;
```

Kết quả: **An – 2**.

Nếu vô tình thêm `pr` vào danh sách khóa nhóm:

```cypher
MATCH (p:Person {id: 'c004-an'})-[:WORKS_ON]->(pr:Project)
WITH p, pr, count(pr) AS soDuAnTrongNhom
RETURN p.name AS nguoi, pr.name AS duAn, soDuAnTrongNhom;
```

Kết quả thành **2 dòng**, mỗi dòng có `soDuAnTrongNhom = 1` vì khóa nhóm lúc này là **cặp `(p, pr)`**, thay vì chỉ `p`. Đây là lỗi thường gặp: số biến được giữ trong `WITH` có thể quyết định độ hạt của kết quả.

### 8.4. `count(*)` và `count(pr)` khi có `null`

```cypher
MATCH (p:Person)
WHERE p.id IN ['c004-an', 'c004-binh', 'c004-chi', 'c004-dung']
OPTIONAL MATCH (p)-[:WORKS_ON]->(pr:Project)
RETURN p.name AS nguoi,
       count(*) AS soDong,
       count(pr) AS soDuAn
ORDER BY nguoi;
```

| nguoi | soDong | soDuAn |
|---|---:|---:|
| An | 2 | 2 |
| Bình | 1 | 1 |
| Chi | 1 | 1 |
| Dũng | 1 | 0 |

- `count(*)` đếm **mọi dòng trong nhóm**, kể cả dòng có một số cột `null`.
- `count(pr)` chỉ đếm các dòng mà `pr` **khác `null`**.
- `count(DISTINCT pr)` đếm số **project duy nhất** trong mỗi nhóm, đặc biệt cần khi việc nối thêm mẫu khác có thể làm một project lặp trên nhiều dòng.

Một truy vấn không có khóa nhóm mà chỉ trả `count(*)` cho toàn bộ tập dữ liệu sẽ tạo một giá trị tổng. Khi tập đầu vào không có dòng, biểu thức tổng hợp không kèm khóa nhóm như `count(*)` vẫn cho kết quả `0`; trái lại, nếu có khóa nhóm thì không có nhóm để xuất ra.

### 8.5. Lọc **sau** khi đã tính tổng hợp

Yêu cầu: chỉ lấy những người tham gia từ hai dự án trở lên.

```cypher
MATCH (p:Person)
WHERE p.id IN ['c004-an', 'c004-binh', 'c004-chi', 'c004-dung']
OPTIONAL MATCH (p)-[:WORKS_ON]->(pr:Project)
WITH p, count(pr) AS soDuAn
WHERE soDuAn >= 2
RETURN p.name AS nguoi, soDuAn;
```

Giai đoạn `WITH` rút 5 dòng thành 4 nhóm. `WHERE` đi sau `WITH` chỉ giữ nhóm của An, nên `RETURN` có **1 dòng**. Nếu đặt điều kiện tổng số dự án trước `WITH` khi chưa có biến `soDuAn`, truy vấn không thể sử dụng bí danh này.

## 9. `DISTINCT`: giảm dòng trùng theo những cột được chọn

Một node có thể xuất hiện nhiều lần trong các dòng vì khớp nhiều cạnh:

```cypher
MATCH (p:Person)-[:WORKS_ON]->(pr:Project)
WHERE p.id IN ['c004-an', 'c004-binh', 'c004-chi', 'c004-dung']
RETURN p.name AS nguoi
ORDER BY nguoi;
```

Kết quả có **4 dòng**: An, An, Bình, Chi. Nếu chỉ cần danh sách người duy nhất:

```cypher
MATCH (p:Person)-[:WORKS_ON]->(:Project)
WHERE p.id IN ['c004-an', 'c004-binh', 'c004-chi', 'c004-dung']
RETURN DISTINCT p.name AS nguoi
ORDER BY nguoi;
```

Kết quả có **3 dòng**: An, Bình, Chi. `DISTINCT` loại các bản ghi trùng theo **toàn bộ biểu thức** trong phần chiếu, không tự loại tất cả biến trùng ở những cột khác.

Ví dụ:

```cypher
MATCH (p:Person)-[:WORKS_ON]->(pr:Project)
WHERE p.id = 'c004-an'
RETURN DISTINCT p.name AS nguoi, pr.name AS duAn;
```

Vẫn có **2 dòng**, vì tổ hợp `(An, Graph API)` và `(An, Recommendation)` khác nhau.

`DISTINCT` hữu ích để diễn đạt đúng ngữ nghĩa dữ liệu duy nhất; không nên dùng nó để che giấu một phép nối sai dẫn đến số dòng tăng ngoài ý muốn.

## 10. `UNWIND`: biến danh sách thành nhiều dòng

`UNWIND` thực hiện một chuyển đổi khác `collect`: nó **trải** từng phần tử của list thành một dòng.

```cypher
UNWIND ['c004-an', 'c004-binh', 'c004-chi'] AS personId
MATCH (p:Person {id: personId})
RETURN personId, p.name AS ten;
```

Trong đồ thị mẫu, list đầu vào có ba phần tử, tạo **3 dòng**; mỗi dòng sau đó khớp một node. Nếu một `personId` không khớp node, `MATCH` loại dòng tương ứng; khi muốn giữ lại ID không khớp, dùng `OPTIONAL MATCH`.

### 10.1. Dữ liệu trùng làm xuất hiện dòng trùng

```cypher
UNWIND [1, 1, 2] AS giaTri
RETURN giaTri;
```

Trả **3 dòng**, dù chỉ có hai giá trị phân biệt. Thêm `RETURN DISTINCT giaTri` sẽ còn **2 dòng**.

### 10.2. Danh sách rỗng loại hết dòng của luồng

```cypher
WITH 'An' AS ten
UNWIND [] AS item
RETURN ten, item;
```

Trả **0 dòng**: `UNWIND []` không phát sinh phần tử, nên dòng `ten = 'An'` ban đầu cũng không được truyền tiếp. Đây là đặc điểm quan trọng khi chuyển một cột chứa list sang các dòng.

### 10.3. `collect` và `UNWIND` thay đổi hình dạng bảng ngược nhau

```cypher
UNWIND ['Graph API', 'Recommendation'] AS duAn
WITH collect(duAn) AS danhSach
UNWIND danhSach AS tungDuAn
RETURN tungDuAn;
```

| Giai đoạn | Dòng | Nội dung |
|---|---:|---|
| `UNWIND` đầu tiên | 2 | Một tên dự án trên mỗi dòng |
| `WITH collect(duAn)` | 1 | Một list gồm hai tên dự án |
| `UNWIND danhSach` | 2 | Hai dòng chứa từng tên dự án |

Vì vậy, luôn kiểm tra kiểu dữ liệu cột: **list trong một ô** và **nhiều dòng** là hai cấu trúc khác nhau.

## 11. `ORDER BY`, `SKIP` và `LIMIT` đặt ở đâu?

`ORDER BY` sắp xếp dòng; `SKIP` và `LIMIT` làm giảm số dòng theo vị trí. Phạm vi áp dụng của chúng phụ thuộc giai đoạn `WITH` hoặc `RETURN` mà chúng đi kèm.

### 11.1. Giới hạn trước khi mở rộng quan hệ

```cypher
MATCH (p:Person)
WHERE p.id IN ['c004-an', 'c004-binh', 'c004-chi', 'c004-dung']
WITH p
ORDER BY p.age DESC, p.id
LIMIT 2
OPTIONAL MATCH (p)-[:WORKS_ON]->(pr:Project)
RETURN p.name AS nguoi, pr.name AS duAn
ORDER BY nguoi, duAn;
```

Theo tuổi, hai người đứng đầu là **Chi (35)** và **An (30)**. `WITH ... LIMIT 2` chọn **2 node trước** khi mở rộng; sau `OPTIONAL MATCH`, hai người này tạo **3 dòng** (Chi 1, An 2).

### 11.2. Giới hạn sau khi mở rộng quan hệ

```cypher
MATCH (p:Person)
WHERE p.id IN ['c004-an', 'c004-binh', 'c004-chi', 'c004-dung']
OPTIONAL MATCH (p)-[:WORKS_ON]->(pr:Project)
RETURN p.name AS nguoi, pr.name AS duAn
ORDER BY nguoi, duAn
LIMIT 2;
```

`LIMIT 2` ở cuối chỉ lấy **2 dòng kết quả**, đều có thể thuộc cùng một người (trong dữ liệu mẫu là hai dòng của An), **không phải hai người khác nhau**.

Nếu mục tiêu “hai người và danh sách tất cả dự án của mỗi người”, trước tiên phải gom theo người hoặc chọn người trước khi mở rộng, rồi mới giới hạn.

### 11.3. Phân trang phải có thứ tự ổn định

```cypher
MATCH (p:Person)
WHERE p.id IN ['c004-an', 'c004-binh', 'c004-chi', 'c004-dung']
RETURN p.id AS id, p.name AS ten
ORDER BY ten, id
SKIP 0
LIMIT 2;
```

`SKIP 0` bỏ qua không dòng nào; `LIMIT 2` lấy tối đa hai dòng tiếp theo sau khi sắp xếp. Thêm `id` làm tiêu chí phụ nếu có tên trùng nhau. Không có `ORDER BY`, thứ tự dòng không được bảo đảm. Khi dữ liệu thay đổi giữa các lần truy vấn, phân trang bằng offset vẫn có thể gặp dòng lặp/bị bỏ sót; các hệ thống lớn thường cân nhắc phân trang dựa trên khóa.

## 12. Nhiều mẫu độc lập: tích Descartes làm bùng nổ số dòng

Nếu bạn nối các mẫu không chia sẻ biến và không có điều kiện ràng buộc, số dòng có thể bị **nhân** với nhau.

```cypher
MATCH (p:Person), (pr:Project)
WHERE p.id IN ['c004-an', 'c004-binh', 'c004-chi', 'c004-dung']
  AND pr.id IN ['c004-api', 'c004-reco', 'c004-pipeline']
RETURN p.name AS nguoi, pr.name AS duAn
ORDER BY nguoi, duAn;
```

Có 4 người và 3 dự án, vì thế truy vấn trả **4 × 3 = 12 dòng**: mọi kết hợp người–dự án, kể cả những người không tham gia dự án đó. Đây là **tích Descartes** (Cartesian product).

Nếu muốn chỉ lấy người thực sự tham gia dự án, mẫu phải chứa relationship:

```cypher
MATCH (p:Person)-[:WORKS_ON]->(pr:Project)
WHERE p.id IN ['c004-an', 'c004-binh', 'c004-chi', 'c004-dung']
RETURN p.name AS nguoi, pr.name AS duAn;
```

Kết quả chỉ có **4 dòng** tương ứng bốn relationship `WORKS_ON`.

### 12.1. Mở rộng hai nhánh cũng có thể nhân số dòng

Ví dụ cần “người quen của An” và “các dự án An tham gia”:

```cypher
MATCH (an:Person {id: 'c004-an'})-[:KNOWS]->(ban:Person)
MATCH (an)-[:WORKS_ON]->(pr:Project)
RETURN an.name AS nguoi, ban.name AS ban, pr.name AS duAn;
```

An có **1 quan hệ KNOWS đi ra** và **2 quan hệ WORKS_ON đi ra**, nên kết quả có **1 × 2 = 2 dòng**. Nếu An có 5 người quen và 4 dự án, có thể có tới **20 dòng tổ hợp**. Không phải lúc nào đây cũng là lỗi; quan trọng là bạn cần một dòng cho mỗi tổ hợp hay một dòng cho mỗi người.

Nếu mục tiêu là một dòng cho An và hai danh sách độc lập, có thể tách giai đoạn:

```cypher
MATCH (an:Person {id: 'c004-an'})
OPTIONAL MATCH (an)-[:KNOWS]->(ban:Person)
WITH an, collect(DISTINCT ban.name) AS dsBan
OPTIONAL MATCH (an)-[:WORKS_ON]->(pr:Project)
RETURN an.name AS nguoi,
       dsBan,
       collect(DISTINCT pr.name) AS dsDuAn;
```

`WITH` gom kết quả nhánh đầu về **một dòng cho An**, rồi mới mở rộng nhánh thứ hai. Cách này phù hợp khi cần hai danh sách độc lập; đồng thời làm rõ độ hạt mong muốn.

## 13. Ví dụ tổng hợp: truy vết số dòng ở từng mệnh đề

**Bài toán:** Liệt kê nhân sự từ 25 tuổi, có ít nhất một dự án đang hoạt động; trả tên, số dự án active và danh sách tên dự án. Sắp xếp người có nhiều dự án active lên trước, rồi theo tên.

```cypher
MATCH (p:Person)
WHERE p.id IN ['c004-an', 'c004-binh', 'c004-chi', 'c004-dung']
  AND p.age >= 25
OPTIONAL MATCH (p)-[:WORKS_ON]->(pr:Project)
WHERE pr.status = 'active'
WITH p,
     count(pr) AS soDuAnActive,
     collect(DISTINCT pr.name) AS dsDuAnActive
WHERE soDuAnActive > 0
RETURN p.name AS nguoi, soDuAnActive, dsDuAnActive
ORDER BY soDuAnActive DESC, nguoi ASC;
```

Phân tích bảng trung gian:

| Mệnh đề / giai đoạn | Độ hạt và biến có mặt | Số dòng |
|---|---|---:|
| `MATCH (p:Person)` + điều kiện ID | Mỗi người: An, Bình, Chi, Dũng; biến `p` | 4 |
| `WHERE p.age >= 25` | Loại Dũng (24 tuổi); còn An, Bình, Chi | 3 |
| `OPTIONAL MATCH` + điều kiện `pr.status = 'active'` | An – Graph API; Bình – Graph API; Chi – `null` | 3 |
| `WITH p, count(pr), collect(...)` | Gom theo `p`: An 1, Bình 1, Chi 0 | 3 |
| `WHERE soDuAnActive > 0` | Loại nhóm của Chi | 2 |
| `RETURN ... ORDER BY ...` | Trả hai dòng, mỗi người một dòng | 2 |

Kết quả:

| nguoi | soDuAnActive | dsDuAnActive |
|---|---:|---|
| An | 1 | `['Graph API']` |
| Bình | 1 | `['Graph API']` |

**Phạm vi biến** cũng thay đổi rõ ràng:

```text
MATCH p
  └─ p
OPTIONAL MATCH pr
  └─ p, pr
WITH p, count(pr) AS soDuAnActive, collect(...) AS dsDuAnActive
  └─ p, soDuAnActive, dsDuAnActive
RETURN ...
  └─ nguoi, soDuAnActive, dsDuAnActive (các cột kết quả)
```

Sau `WITH`, biến `pr` không còn sẵn để dùng trực tiếp ở `RETURN`, bởi nó không được chuyển tiếp như biến độc lập. Các dữ liệu cần thiết của `pr` đã được **tổng hợp thành số lượng và danh sách**.

### 13.1. Nếu muốn giữ cả người không có dự án active

Chỉ cần bỏ điều kiện lọc sau `WITH`:

```cypher
MATCH (p:Person)
WHERE p.id IN ['c004-an', 'c004-binh', 'c004-chi', 'c004-dung']
OPTIONAL MATCH (p)-[:WORKS_ON]->(pr:Project)
WHERE pr.status = 'active'
WITH p, count(pr) AS soDuAnActive, collect(pr.name) AS dsDuAnActive
RETURN p.name AS nguoi, soDuAnActive, dsDuAnActive
ORDER BY nguoi;
```

Lúc này có **4 dòng**, bao gồm Chi và Dũng với số dự án `0` và list rỗng `[]`. Điều kiện tuổi cũng đã được bỏ để minh họa việc giữ đủ bốn người.

## 14. Quan sát số dòng thật bằng `EXPLAIN` và `PROFILE`

Các con số trong ví dụ trên là **cardinality logic** suy ra từ đồ thị mẫu. Trên dữ liệu thực, Neo4j cung cấp kế hoạch để hiểu các operator và số dòng được xử lý.

```cypher
EXPLAIN
MATCH (p:Person)-[:WORKS_ON]->(pr:Project)
WHERE p.id = 'c004-an'
RETURN pr.name AS duAn;
```

`EXPLAIN` đưa ra kế hoạch ước lượng mà **không thực thi** truy vấn. Để quan sát số dòng thực tế tại các operator:

```cypher
PROFILE
MATCH (p:Person)-[:WORKS_ON]->(pr:Project)
WHERE p.id = 'c004-an'
RETURN pr.name AS duAn;
```

`PROFILE` thực thi truy vấn và cung cấp thống kê thực tế, thường gồm số dòng, số lần chạm dữ liệu (tùy operator và phiên bản). `PROFILE` có thể gây thay đổi dữ liệu nếu dùng với truy vấn ghi, vì vậy chỉ chạy trên dữ liệu phù hợp.

Khi phân tích kế hoạch, cần phân biệt:

- **Số dòng logic** mong muốn: số bản ghi đầu ra đúng bài toán.
- **Số dòng trung gian**: có thể rất lớn do mở rộng nhiều cạnh hoặc ghép nhiều nhánh.
- **Kế hoạch vật lý**: operator, chỉ mục và thứ tự xử lý có thể được trình tối ưu lựa chọn để giảm chi phí mà vẫn giữ kết quả đúng.

Index hoặc constraint thường giúp tìm điểm bắt đầu nhanh và bảo toàn dữ liệu định danh; chúng **không tự biến bốn cạnh `WORKS_ON` thành bốn người duy nhất**. Muốn đổi độ hạt, phải diễn đạt rõ bằng phép tổng hợp hoặc `DISTINCT`.

## 15. Liên hệ khi đọc kết quả qua Java Driver và Spring Data Neo4j

Một kết quả Cypher gồm các **record**. Nếu `RETURN` đưa ra nhiều dòng cho cùng một node, ứng dụng nhận **nhiều record**, dù các record có thể tham chiếu tới cùng một node.

Ví dụ:

```cypher
MATCH (p:Person)-[:WORKS_ON]->(pr:Project)
WHERE p.id = $personId
RETURN p.name AS personName, pr.name AS projectName
ORDER BY projectName;
```

Khi `$personId = 'c004-an'`, truy vấn trả **2 record**:

| personName | projectName |
|---|---|
| An | Graph API |
| An | Recommendation |

Nếu ứng dụng muốn **một người với danh sách dự án**, hãy chọn cấu trúc đầu ra phù hợp ngay trong Cypher:

```cypher
MATCH (p:Person {id: $personId})
OPTIONAL MATCH (p)-[:WORKS_ON]->(pr:Project)
RETURN p.id AS personId,
       p.name AS personName,
       collect(pr.name) AS projects;
```

Truy vấn này tạo một dòng chứa cột `projects` kiểu list. Với hai đầu ra trên, cách ánh xạ sang DTO hoặc projection trong Java sẽ khác nhau: ví dụ đầu có thể thành danh sách bản ghi mỗi dự án, ví dụ sau có thể thành một object chứa danh sách. Khi dùng Spring Data Neo4j để ánh xạ entity và quan hệ, cần thiết kế truy vấn trả về đúng hình dạng mà cơ chế ánh xạ mong đợi.

## 16. Các lỗi thường gặp và cách tự kiểm tra

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| Một người xuất hiện nhiều dòng | Người đó khớp nhiều relationship. | Xác định độ hạt; `WITH p, collect(...)` hoặc `RETURN DISTINCT p` nếu đúng nhu cầu. |
| Dòng của người không có dự án biến mất | Dùng `MATCH` bắt buộc. | Dùng `OPTIONAL MATCH` khi cần giữ dòng. |
| `OPTIONAL MATCH` rồi vẫn mất dòng `null` | `WHERE` lọc bảng sau `WITH`. | Đặt điều kiện trong `OPTIONAL MATCH` hoặc xử lý `null` có chủ ý. |
| `count(*) = 1` cho người chưa có dự án | Đếm dòng được giữ bởi `OPTIONAL MATCH`. | Dùng `count(pr)` hoặc `count(r)` để đếm giá trị khớp. |
| `count(pr)` quá lớn | Dự án lặp sau khi nối nhiều nhánh. | Kiểm tra mẫu nối; cân nhắc `count(DISTINCT pr)`. |
| Báo lỗi biến không được định nghĩa | `WITH` không truyền biến cần dùng. | Thêm biến vào `WITH` hoặc đưa giá trị cần dùng sang bí danh. |
| Mỗi dự án bị đếm thành một nhóm | Giữ `pr` cùng với `p` trong `WITH` tổng hợp. | Chỉ giữ khóa nhóm đúng độ hạt muốn có. |
| `LIMIT 2` nhưng chỉ có một người | Giới hạn hai **dòng**, có thể đều là của cùng node. | Chọn người trước hoặc gom theo người trước rồi giới hạn. |
| Kết quả tăng từ vài dòng lên hàng nghìn | Hai mẫu độc lập tạo tích Descartes hoặc các nhánh nhân tổ hợp. | Gắn quan hệ/điều kiện nối, hoặc gom từng nhánh trước khi nối nhánh tiếp theo. |
| `UNWIND []` không trả được dòng gốc | Danh sách rỗng không tạo phần tử nào. | Xử lý danh sách rỗng trước `UNWIND` nếu cần bảo toàn dòng. |
| Hai lần chạy phân trang cho thứ tự khác nhau | Thiếu `ORDER BY` hoặc khóa sắp xếp chưa đủ rõ. | Sắp xếp theo khóa ổn định, cân nhắc chiến lược phân trang theo khóa. |

**Ba câu hỏi để tự đọc truy vấn dài:**

1. **Một dòng ở giai đoạn này đại diện cho điều gì?** Một node, một relationship, một path, một tổ hợp hay một nhóm?
2. **Mỗi dòng vào có thể tạo bao nhiêu dòng ra?** Không khớp, một khớp, nhiều khớp, hay được giữ bằng `OPTIONAL MATCH`?
3. **Biến nào còn sống sau `WITH`?** Có đổi tên, chuyển thành scalar/list hoặc bị gộp vào hàm tổng hợp hay không?

## 17. Bài tập tự luyện

Các bài tập dưới đây dùng bộ dữ liệu ở mục 3. Hãy thử dự đoán số dòng **trước khi** chạy Cypher, sau đó đối chiếu.

### Bài 1. Đếm dòng sau mở rộng

Truy vấn sau trả bao nhiêu dòng và tên người nào lặp?

```cypher
MATCH (p:Person)
WHERE p.id IN ['c004-an', 'c004-binh', 'c004-chi', 'c004-dung']
MATCH (p)-[:WORKS_ON]->(pr:Project)
RETURN p.name AS nguoi, pr.name AS duAn;
```

<details>
<summary>Đáp án</summary>

Có **4 dòng**: An – Graph API, An – Recommendation, Bình – Graph API, Chi – Recommendation. **An** lặp hai lần vì có hai quan hệ `WORKS_ON`; Dũng không có dòng.

</details>

### Bài 2. Giữ người chưa tham gia dự án

Viết truy vấn trả mỗi người **một dòng**, kèm số dự án của người đó, kể cả Dũng với `0`.

<details>
<summary>Đáp án gợi ý</summary>

```cypher
MATCH (p:Person)
WHERE p.id IN ['c004-an', 'c004-binh', 'c004-chi', 'c004-dung']
OPTIONAL MATCH (p)-[:WORKS_ON]->(pr:Project)
RETURN p.name AS nguoi, count(pr) AS soDuAn
ORDER BY nguoi;
```

Kết quả: An 2, Bình 1, Chi 1, Dũng 0.

</details>

### Bài 3. Phạm vi của biến

Vì sao truy vấn sau lỗi? Sửa để trả tên và tuổi của An.

```cypher
// Truy vấn cố ý sai
MATCH (p:Person {id: 'c004-an'})
WITH p.name AS ten
RETURN ten, p.age AS tuoi;
```

<details>
<summary>Đáp án gợi ý</summary>

`p` không được chuyển qua `WITH`, nên đã ra khỏi phạm vi.

```cypher
MATCH (p:Person {id: 'c004-an'})
WITH p.name AS ten, p.age AS tuoi
RETURN ten, tuoi;
```

Hoặc dùng `WITH p, p.name AS ten` rồi `RETURN ten, p.age AS tuoi`.

</details>

### Bài 4. `WHERE` của `OPTIONAL MATCH`

Viết truy vấn giữ bốn người, trả số **dự án đang active** của mỗi người. Dữ liệu mẫu phải cho An 1, Bình 1, Chi 0, Dũng 0.

<details>
<summary>Đáp án gợi ý</summary>

```cypher
MATCH (p:Person)
WHERE p.id IN ['c004-an', 'c004-binh', 'c004-chi', 'c004-dung']
OPTIONAL MATCH (p)-[:WORKS_ON]->(pr:Project)
WHERE pr.status = 'active'
RETURN p.name AS nguoi, count(pr) AS soDuAnActive
ORDER BY nguoi;
```

Điều kiện `WHERE` gắn vào phần tùy chọn, nên Chi và Dũng vẫn có dòng với `count(pr) = 0`.

</details>

### Bài 5. `LIMIT` ở giai đoạn khác nhau

Dự đoán số dòng và danh tính người trong truy vấn:

```cypher
MATCH (p:Person)
WHERE p.id IN ['c004-an', 'c004-binh', 'c004-chi', 'c004-dung']
WITH p
ORDER BY p.age DESC
LIMIT 2
OPTIONAL MATCH (p)-[:WORKS_ON]->(pr:Project)
RETURN p.name AS nguoi, pr.name AS duAn;
```

<details>
<summary>Đáp án</summary>

`WITH` lấy **Chi và An** trước; `OPTIONAL MATCH` tạo **3 dòng**: Chi – Recommendation; An – Graph API; An – Recommendation. Không có `ORDER BY` cuối nên thứ tự ba dòng có thể khác.

</details>

### Bài 6. Tại sao bị nhân tổ hợp?

Cho hai mẫu độc lập với bốn người và ba dự án:

```cypher
MATCH (p:Person), (pr:Project)
WHERE p.id IN ['c004-an', 'c004-binh', 'c004-chi', 'c004-dung']
  AND pr.id IN ['c004-api', 'c004-reco', 'c004-pipeline']
RETURN p.name AS nguoi, pr.name AS duAn;
```

Hỏi số dòng và cách sửa nếu chỉ muốn trả cặp người–dự án thực sự có `WORKS_ON`?

<details>
<summary>Đáp án gợi ý</summary>

Có **12 dòng** vì `4 × 3`. Sửa bằng mẫu có relationship:

```cypher
MATCH (p:Person)-[:WORKS_ON]->(pr:Project)
WHERE p.id IN ['c004-an', 'c004-binh', 'c004-chi', 'c004-dung']
RETURN p.name AS nguoi, pr.name AS duAn;
```

Kết quả còn **4 dòng**.

</details>

## 18. Ghi nhớ

**Bảng trung gian** là mô hình hữu ích để hiểu ngữ nghĩa Cypher: mỗi dòng là một bộ giá trị của các biến tại một giai đoạn. `MATCH` có thể tăng hoặc giảm số dòng khi nối mẫu; `OPTIONAL MATCH` giữ dòng không khớp bằng `null`; `WHERE` loại dòng hoặc ràng buộc mẫu tùy vị trí; `WITH` quyết định biến nào còn trong phạm vi và liệu các dòng có được gom nhóm; `DISTINCT`, `UNWIND` và `LIMIT` tiếp tục thay đổi hình dạng bảng.

Muốn đọc và tối ưu truy vấn Neo4j một cách chắc chắn, hãy luôn xác định **độ hạt mong muốn, số dòng trung gian và phạm vi biến**. Những điều đó quyết định tính đúng đắn của phép đếm, danh sách quan hệ, truy vấn đường đi và cấu trúc bản ghi mà ứng dụng Java nhận được.
