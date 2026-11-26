# Tham số truy vấn và phân biệt dữ liệu đầu vào với cấu trúc câu lệnh trong Cypher

> **Chương:** Nền tảng Cypher  
> **Phạm vi:** Neo4j sử dụng mô hình *property graph* để lưu node, relationship và property. Bài này giải thích cách truyền dữ liệu đầu vào vào câu truy vấn Cypher bằng **tham số** (*query parameters*), phân biệt tham số với biến của mẫu đồ thị, đồng thời xác định ranh giới giữa **giá trị dữ liệu** và **cấu trúc câu lệnh**. Kiến thức này áp dụng trực tiếp khi dùng Neo4j Browser, Java Driver và Spring Data Neo4j.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích ý nghĩa của cú pháp `$tenThamSo` và cách giá trị được cung cấp từ bên ngoài truy vấn.
2. Phân biệt **biến Cypher**, **tham số**, **label**, **relationship type**, **property key** và **giá trị literal**.
3. Truyền tham số dạng chuỗi, số, boolean, `null`, list, map và giá trị thời gian trong các điều kiện truy vấn.
4. Viết câu truy vấn sử dụng lại được thay vì ghép chuỗi chứa giá trị người dùng.
5. Hiểu vì sao tham số hóa làm giảm nguy cơ *Cypher injection* và thường hỗ trợ tái sử dụng kế hoạch truy vấn.
6. Biết phần nào của cấu trúc Cypher không thể được thay bằng một tham số thông thường; nhận diện các cú pháp động có điều kiện phiên bản.
7. Sử dụng tham số trong thao tác đọc, cập nhật, nhập nhiều bản ghi, phân trang và tích hợp ứng dụng Java.
8. Chẩn đoán lỗi thiếu tham số, sai tên, sai kiểu, truyền `null` và điều kiện không trả kết quả.

## 2. Vấn đề: câu truy vấn ổn định, dữ liệu đầu vào thay đổi

Giả sử ứng dụng cần tìm thông tin nhân sự theo ID. Lần đầu tìm An, lần sau tìm Bình. Hai yêu cầu chỉ khác **giá trị ID**, còn nghiệp vụ và cấu trúc đồ thị không đổi.

Viết bằng literal:

```cypher
MATCH (p:Person {id: 'p1'})
RETURN p.name AS ten;
```

Lần tiếp theo phải đổi đoạn `'p1'` thành `'p2'`. Khi ứng dụng tự ghép chuỗi từ đầu vào người dùng để tạo truy vấn, việc kiểm soát kiểu dữ liệu, ký tự đặc biệt và an toàn trở nên khó hơn.

Viết bằng tham số:

```cypher
MATCH (p:Person {id: $personId})
RETURN p.name AS ten;
```

Truy vấn **giữ nguyên**, còn bên gọi gửi giá trị riêng:

```json
{
  "personId": "p1"
}
```

hoặc:

```json
{
  "personId": "p2"
}
```

Ở đây `$personId` là **chỗ tham chiếu đến dữ liệu đầu vào đã được ràng buộc**. Dấu `$` đứng trước tên tham số; tên `personId` phải khớp với khóa do bên gọi truyền vào.

Trong mô hình ứng dụng, có thể hình dung:

```text
Mã Cypher cố định:
MATCH (p:Person {id: $personId}) RETURN p.name
                │
                ▼
Tham số do ứng dụng gửi:
{ personId: "p1" }
                │
                ▼
Neo4j xử lý điều kiện id với giá trị "p1"
                │
                ▼
Record kết quả: { name: "An" }
```

**Điểm cốt lõi:** tham số chứa **giá trị dữ liệu**. Nó không phải một đoạn văn bản Cypher để Neo4j tự dán vào câu lệnh rồi diễn giải lại như cú pháp.

## 3. Sáu khái niệm thường bị nhầm với nhau

Xét mẫu:

```cypher
MATCH (p:Person)-[r:WORKS_ON]->(pr:Project)
WHERE p.id = $personId AND r.role = $role
RETURN p.name AS ten, pr.name AS duAn;
```

| Thành phần | Loại | Ý nghĩa |
|---|---|---|
| `p`, `r`, `pr` | **Biến Cypher** | Được ràng buộc với node/relationship theo từng dòng của truy vấn. |
| `$personId`, `$role` | **Tham số** | Giá trị do bên gọi truyền, chẳng hạn `'p1'` và `'lead'`. |
| `Person`, `Project` | **Node label** | Điều kiện về nhãn của node, xuất hiện sau dấu `:` trong `(...)`. |
| `WORKS_ON` | **Relationship type** | Loại cạnh cần khớp trong `[...]`. |
| `id`, `role`, `name` | **Property key** | Tên thuộc tính được truy cập, ví dụ `p.id`, `r.role`. |
| `'lead'`, `25`, `true` | **Literal** | Giá trị được viết trực tiếp trong văn bản câu truy vấn. |

Những khác biệt quan trọng:

- `p` là một **biến**, không phải tham số; `$p` là một **tham số có tên p**, không trỏ đến node của biến `p`.
- `Person` trong `(p:Person)` là label; `Person` trong `(Person)` lại là **tên biến**, do thiếu dấu `:`.
- `$personId` là dữ liệu đầu vào; `personId` không có dấu `$` được hiểu theo quy tắc định danh trong truy vấn, không tự đọc tham số.
- `p.name` đọc thuộc tính `name` của node do `p` tham chiếu; `$name` đọc **tham số** có tên `name`.
- `AS ten` tạo tên cột/biến trong kết quả trung gian, không tạo tham số `$ten`.

### 3.1. Biến tồn tại theo phạm vi; tham số có sẵn theo lần thực thi

```cypher
MATCH (p:Person {id: $personId})
WITH p.name AS ten
RETURN ten;
```

Biến `p` được giới thiệu qua `MATCH` rồi **biến mất sau `WITH`** vì chỉ `ten` được chuyển tiếp. Ngược lại, tham số `$personId` là một phần của bộ đầu vào cho lần thực thi truy vấn; nó không phải cột bảng trung gian và không cần được đưa vào `WITH` để tiếp tục tham chiếu ở những biểu thức hợp lệ phía sau.

Ví dụ:

```cypher
MATCH (p:Person {id: $personId})
WITH p.name AS ten
RETURN ten, $personId AS idDaTim;
```

Câu trên hợp lệ dù biến `p` đã ra khỏi phạm vi. Giá trị của `$personId` được lấy từ bộ tham số, không lấy từ biến `p`.

## 4. Chuẩn bị bộ dữ liệu Neo4j thực hành

Chạy khối lệnh sau trong **database thực hành riêng**. Mẫu dùng ID có tiền tố `c005-` để tránh nhầm với các ví dụ khác. `MERGE` tìm mẫu trước khi tạo, nhưng trong hệ thống thật vẫn cần thiết kế uniqueness constraint phù hợp nếu ID phải duy nhất dưới tải đồng thời.

```cypher
MERGE (an:Person {id: 'c005-an'})
SET an.name = 'An', an.age = 30,
    an.city = 'Hà Nội', an.active = true

MERGE (binh:Person {id: 'c005-binh'})
SET binh.name = 'Bình', binh.age = 27,
    binh.city = 'TP. Hồ Chí Minh', binh.active = true

MERGE (chi:Person {id: 'c005-chi'})
SET chi.name = 'Chi', chi.age = 35,
    chi.city = 'Hà Nội', chi.active = false

MERGE (dung:Person {id: 'c005-dung'})
SET dung.name = 'Dũng', dung.age = 24,
    dung.city = 'Đà Nẵng', dung.active = true

MERGE (api:Project {id: 'c005-api'})
SET api.name = 'Graph API', api.status = 'active'

MERGE (pipeline:Project {id: 'c005-pipeline'})
SET pipeline.name = 'Data Pipeline', pipeline.status = 'planned'

MERGE (an)-[lead:WORKS_ON]->(api)
SET lead.role = 'lead'
MERGE (binh)-[dev:WORKS_ON]->(api)
SET dev.role = 'developer'
MERGE (chi)-[advisor:WORKS_ON]->(pipeline)
SET advisor.role = 'advisor';
```

Sơ đồ:

```text
(An:Person, 30, Hà Nội) ─[WORKS_ON {role:lead}]───────> (Graph API:Project)
(Bình:Person, 27, TP.HCM) ─[WORKS_ON {role:developer}]─> (Graph API:Project)
(Chi:Person, 35, Hà Nội) ─[WORKS_ON {role:advisor}]────> (Data Pipeline:Project)
(Dũng:Person, 24, Đà Nẵng)      (chưa tham gia dự án)
```

Các số dòng dự kiến trong bài chỉ chính xác khi các node mẫu có ID duy nhất và không có quan hệ phát sinh thêm. Nếu database đã có dữ liệu khác, hãy giữ điều kiện theo ID thay vì `MATCH (p:Person)` không lọc.

## 5. Cú pháp và cách cung cấp tham số

Cú pháp tham chiếu cơ bản:

```cypher
WHERE p.id = $personId
```

Người viết truy vấn đặt tên tham số, chẳng hạn `personId`; bên gọi cung cấp **bản đồ tham số** với key tương ứng và value có kiểu phù hợp:

```json
{
  "personId": "c005-an"
}
```

Ví dụ truy vấn có **hai** tham số:

```cypher
MATCH (p:Person)
WHERE p.age >= $minAge AND p.city = $city
RETURN p.name AS ten, p.age AS tuoi
ORDER BY ten;
```

Giá trị đầu vào:

```json
{
  "minAge": 25,
  "city": "Hà Nội"
}
```

Trong dữ liệu mẫu, kết quả là **An (30)** và **Chi (35)**. Câu truy vấn không cần chỉnh sửa khi đổi `city` sang một thành phố khác.

### 5.1. Tham số được thiết lập ở đâu?

Tùy công cụ, có các cách cung cấp giá trị:

- **Neo4j Browser / cypher-shell:** thiết lập tham số bằng lệnh của công cụ rồi chạy câu Cypher.
- **Java Driver:** đưa map tham số vào API thực thi truy vấn.
- **Spring Data Neo4j:** khai báo tham số trong phương thức repository hoặc phương thức gọi truy vấn.

Ví dụ câu lệnh của Neo4j Browser có thể sử dụng dạng:

```text
:param personId => 'c005-an'
```

Sau đó chạy:

```cypher
MATCH (p:Person {id: $personId})
RETURN p.name AS ten;
```

Lưu ý: lệnh `:param` thuộc **giao diện công cụ**, không phải mệnh đề Cypher đưa vào một chuỗi truy vấn của Java Driver. Cú pháp quản lý tham số của từng client có thể khác nhau theo phiên bản; điều bất biến là bên gọi phải cung cấp giá trị cho `$personId`.

### 5.2. Tên tham số phải khớp chính xác

`$personId` khác `$personID` vì tên phân biệt chữ hoa và chữ thường. Nếu câu truy vấn cần `$personId` mà bên gọi chỉ gửi key `id`, truy vấn bị lỗi **thiếu tham số**; Neo4j không suy đoán tên dựa trên nội dung.

Giá trị `null` và **tham số không được truyền** là hai trường hợp khác nhau:

- `{personId: null}`: tham số **có mặt**, mang giá trị `null`.
- `{}`: hoàn toàn không có key `personId`; câu truy vấn vẫn yêu cầu giá trị này.

Do đó, với tham số tùy chọn, bên gọi cần truyền **cả key cùng giá trị `null`** hoặc chọn một câu truy vấn khác không cần tham số đó.

## 6. Tham số cho các kiểu dữ liệu thường gặp

### 6.1. Chuỗi, số và boolean

```cypher
MATCH (p:Person)
WHERE p.id IN $personIds
  AND p.age >= $minAge
  AND p.active = $isActive
RETURN p.name AS ten, p.age AS tuoi
ORDER BY tuoi DESC;
```

Bộ tham số:

```json
{
  "personIds": ["c005-an", "c005-binh", "c005-chi", "c005-dung"],
  "minAge": 25,
  "isActive": true
}
```

Kết quả: An (30), Bình (27). Chi lớn tuổi nhưng `active = false`; Dũng `age = 24`.

**Chú ý kiểu:** số `25` không giống chuỗi `"25"`; boolean `true` không giống chuỗi `"true"`. Nên truyền kiểu đúng từ API thay vì trông đợi Neo4j tự đổi kiểu. Khi cần chuyển kiểu có chủ đích, sử dụng hàm Cypher như `toInteger(...)`, sau khi đã xác thực đầu vào.

### 6.2. List và toán tử `IN`

```cypher
MATCH (p:Person)
WHERE p.id IN $ids
RETURN p.name AS ten
ORDER BY ten;
```

Tham số:

```json
{
  "ids": ["c005-an", "c005-chi"]
}
```

Kết quả: An và Chi.

Nếu `ids = []`, biểu thức `p.id IN $ids` không khớp node nào. Đừng viết `IN [$ids]` khi `$ids` đã là list: cặp ngoặc vuông ngoài sẽ tạo **một list chứa list**, không phải danh sách giá trị mong muốn.

### 6.3. Map cho bộ lọc hoặc dữ liệu cập nhật

Tham số có thể chứa map:

```json
{
  "filter": {
    "city": "Hà Nội",
    "minAge": 25
  }
}
```

Truy vấn:

```cypher
MATCH (p:Person)
WHERE p.id IN ['c005-an', 'c005-binh', 'c005-chi', 'c005-dung']
  AND p.city = $filter.city
  AND p.age >= $filter.minAge
RETURN p.name AS ten
ORDER BY ten;
```

`$filter` là **một tham số map**; `$filter.city` lấy value của key `city` trong map đó. Nó khác `p.city`: vế trái đọc thuộc tính của node, vế phải đọc giá trị được gửi vào.

Ví dụ sửa thuộc tính cho một node:

```cypher
MATCH (p:Person {id: $personId})
SET p += $changes
RETURN p.id AS id, properties(p) AS thuocTinh;
```

Map tham số:

```json
{
  "personId": "c005-an",
  "changes": {
    "city": "Đà Nẵng",
    "active": true
  }
}
```

`SET p += $changes` cập nhật/thêm các property được chỉ định, giữ lại những property khác. Nếu value trong map là `null`, việc cập nhật có thể xóa property tương ứng. **Chỉ cho phép các key được ứng dụng chấp nhận**: tham số hóa bảo vệ cú pháp truy vấn nhưng không tự ngăn người dùng yêu cầu sửa thuộc tính nhạy cảm hoặc không được phép. Đoạn ví dụ thay đổi dữ liệu, vì vậy chỉ thực thi trên database thực hành.

### 6.4. Kiểu thời gian

Nếu bên gọi gửi ngày dạng chuỗi ISO, có thể chuyển sang kiểu `Date` của Cypher:

```cypher
WITH date($startDate) AS batDau
RETURN batDau, batDau + duration({days: 7}) AS sauMotTuan;
```

Tham số:

```json
{
  "startDate": "2026-11-25"
}
```

Giá trị `$startDate` được cung cấp từ ngoài. Hàm `date(...)` quyết định ý nghĩa kiểu dữ liệu, còn cú pháp `duration({days: 7})` là phần cấu trúc cố định của biểu thức. Java Driver cũng có khả năng gửi một số kiểu temporal trực tiếp; hãy chọn kiểu phù hợp với cách thiết kế thuộc tính trong Neo4j.

## 7. `null` và bộ lọc tùy chọn

`null` là giá trị đặc biệt, không tương đương với chuỗi `"null"` hoặc danh sách rỗng `[]`.

### 7.1. So sánh với `null` không giống kiểm tra `IS NULL`

```cypher
MATCH (p:Person {id: 'c005-an'})
WHERE p.city = $city
RETURN p.name AS ten;
```

Nếu truyền `{city: null}`, so sánh `p.city = null` không cho `true`, nên không có dòng nào khớp. Để kiểm tra giá trị thiếu, dùng `IS NULL` hoặc `IS NOT NULL` theo mục tiêu.

### 7.2. Mẫu bộ lọc thành phố tùy chọn

Yêu cầu: nếu `$city` có giá trị, lọc theo thành phố; nếu `$city = null`, bỏ qua điều kiện thành phố.

```cypher
MATCH (p:Person)
WHERE p.id IN ['c005-an', 'c005-binh', 'c005-chi', 'c005-dung']
  AND ($city IS NULL OR p.city = $city)
RETURN p.name AS ten, p.city AS thanhPho
ORDER BY ten;
```

- Khi `city = "Hà Nội"`: An, Chi.
- Khi `city = null`: cả bốn người.
- Khi **không truyền key `city`**: không thể xem mặc định là `null`; cần bổ sung key hoặc dùng truy vấn khác.

Biểu thức `OR` có thể ảnh hưởng đến cách trình tối ưu khai thác index trong một số tình huống. Với tập dữ liệu lớn hoặc nhiều bộ lọc tùy chọn, có thể cần thiết kế các biến thể truy vấn cố định khác nhau và đo bằng `EXPLAIN`/`PROFILE`.

### 7.3. Giá trị mặc định khác với “không truyền tham số”

```cypher
WITH coalesce($minAge, 0) AS tuoiToiThieu
MATCH (p:Person)
WHERE p.id IN ['c005-an', 'c005-binh', 'c005-chi', 'c005-dung']
  AND p.age >= tuoiToiThieu
RETURN p.name AS ten;
```

`coalesce` chọn giá trị khác `null` đầu tiên. Nhưng để biểu thức hoạt động khi không có tuổi tối thiểu, bên gọi vẫn cần **truyền key `minAge` với giá trị `null`**. Thiếu hẳn key không phải tình huống được `coalesce` tự khắc phục.

## 8. Phân biệt dữ liệu đầu vào với cấu trúc câu lệnh

Đây là trọng tâm của bài. Một câu Cypher có **cấu trúc truy vấn**, bao gồm mệnh đề, mẫu node–relationship, tên label/type, khóa thuộc tính và cách sắp xếp. Tham số thông thường chỉ mang giá trị ở **vị trí biểu thức dữ liệu** mà cú pháp cho phép.

Xét các ví dụ:

| Ý định | Cách viết | Hợp lệ/ý nghĩa |
|---|---|---|
| Lọc ID động | `WHERE p.id = $id` | Đúng: `$id` là giá trị. |
| Lọc tuổi động | `WHERE p.age >= $minAge` | Đúng: `$minAge` là số. |
| Lọc nhiều ID | `WHERE p.id IN $ids` | Đúng nếu `$ids` là list phù hợp. |
| Đọc thuộc tính được chọn động | `RETURN p[$propertyKey]` | Có thể dùng biểu thức truy cập property động trong các phiên bản hỗ trợ cú pháp này. |
| Thay nguyên mệnh đề `MATCH` | `$clause (p:Person)` | Sai: tham số không phải từ khóa Cypher. |
| Thay mẫu bằng chuỗi | `MATCH $pattern` | Sai: chuỗi đầu vào không được phân tích lại thành graph pattern. |
| Dùng giá trị như label tĩnh | `MATCH (p:$label)` | Không phải cú pháp tham số hóa label trực tiếp. |
| Dùng chuỗi làm danh sách cột sắp xếp | `ORDER BY $sortBy` | Không tự biến chuỗi `"p.name"` thành biểu thức thuộc tính `p.name`. |

### 8.1. Truyền một chuỗi không có nghĩa là truyền mã Cypher

Giả sử `$pattern` có giá trị:

```json
{
  "pattern": "(p:Person)-[:WORKS_ON]->(pr:Project)"
}
```

Neo4j nhận đó là **chuỗi văn bản**, không tự sử dụng chuỗi làm phần bên phải của `MATCH`. Nếu muốn kiểm tra một quan hệ, phải viết **mẫu đồ thị đúng cú pháp ngay trong câu truy vấn**:

```cypher
MATCH (p:Person)-[:WORKS_ON]->(pr:Project)
WHERE p.id = $personId
RETURN pr.name AS duAn;
```

### 8.2. Property key động và ranh giới kiểm soát

Với truy vấn đọc, bạn có thể chọn một thuộc tính theo tên key:

```cypher
MATCH (p:Person {id: $personId})
RETURN p[$propertyKey] AS giaTri;
```

Tham số:

```json
{
  "personId": "c005-an",
  "propertyKey": "city"
}
```

`p[$propertyKey]` là **biểu thức truy cập property bằng khóa động**; kết quả là chuỗi tên thành phố. Nó khác việc đưa `$propertyKey` vào giữa câu lệnh ở một vị trí chỉ chấp nhận định danh tĩnh. Ứng dụng vẫn cần **allowlist** các key được quyền đọc, ví dụ `name`, `city`, `age`, vì truy vấn hợp lệ không có nghĩa mọi property đều được phép tiết lộ.

### 8.3. Label và relationship type động phụ thuộc phiên bản Cypher

Trong cách viết cơ bản:

```cypher
MATCH (p:Person)-[:WORKS_ON]->(pr:Project)
RETURN p, pr;
```

`Person`, `WORKS_ON`, `Project` là **các token cấu trúc**, không phải vị trí nhận tham số theo kiểu thay thế văn bản. Vì thế, kiểu viết `(p:$label)` hay `-[:$type]->` không phải cách tham số hóa chuẩn.

**Lưu ý phiên bản:** Neo4j từ **5.26** có cú pháp chuyên biệt cho *dynamic labels* và *dynamic relationship types* ở những ngữ cảnh được hỗ trợ. Ví dụ với phiên bản hỗ trợ:

```cypher
MATCH (n:$($label))
RETURN n
LIMIT 10;
```

Với tham số `{label: "Person"}`, biểu thức động `$($label)` được đánh giá theo quy tắc của cú pháp Cypher tương ứng. Đây **không phải** tính năng “nối chuỗi truy vấn”; nó là **một cấu trúc Cypher được ngôn ngữ hỗ trợ rõ ràng**. Khả năng hỗ trợ, cách tối ưu bằng index và phạm vi ngữ cảnh dùng cú pháp động khác nhau theo phiên bản/phiên bản Cypher. Khi cần viết truy vấn chạy trên nhiều phiên bản, hãy đối chiếu tài liệu tương ứng và dùng label/type tĩnh khi phù hợp.

Đối với nghiệp vụ chỉ cho phép một số label/type, hãy đặt quy tắc cho phép cụ thể, ví dụ chỉ chấp nhận `Person` hoặc `Project`, và kiểm soát quyền truy cập. Cú pháp động không thay thế xác thực đầu vào và phân quyền.

### 8.4. Sắp xếp theo yêu cầu từ UI

Tham số giá trị:

```cypher
MATCH (p:Person)
WHERE p.id IN $ids AND p.age >= $minAge
RETURN p.name AS ten, p.age AS tuoi
ORDER BY tuoi DESC;
```

Ở đây `$minAge` là dữ liệu, còn `tuoi DESC` là cách sắp xếp đã được **định nghĩa trước**. Nếu UI cho chọn sắp xếp theo tên hoặc tuổi, hai lựa chọn rõ ràng là:

1. Chọn một trong **các mẫu câu truy vấn cố định** đã được ứng dụng duyệt trước.
2. Dùng **biểu thức `CASE`** trong `ORDER BY` khi có một số tùy chọn hữu hạn, bảo đảm các nhánh có kiểu so sánh phù hợp.

Đừng lấy giá trị `"p.name DESC"` từ request rồi chèn nguyên văn vào câu Cypher. Việc tham số hóa một chuỗi như thế không tự thực hiện việc sắp xếp theo biểu thức được mô tả.

## 9. Vì sao tham số hóa giúp giảm Cypher injection?

Giả sử ứng dụng Java tự tạo câu lệnh:

```java
// KHÔNG an toàn: name đến từ người dùng
String query =
    "MATCH (p:Person) WHERE p.name = '" + userName + "' RETURN p";
```

Khi `userName` chứa dấu nháy hoặc ký tự có ý nghĩa đặc biệt trong Cypher, văn bản truy vấn có thể bị thay đổi ngữ nghĩa hoặc bị lỗi. Nếu đầu vào bị kiểm soát bởi kẻ tấn công, đây là nguy cơ **Cypher injection**.

Thay bằng truy vấn có tham số:

```java
String query = """
    MATCH (p:Person)
    WHERE p.name = $name
    RETURN p
    """;

Map<String, Object> params = Map.of("name", userName);
```

Trong trường hợp này, `userName` được chuyển như **giá trị chuỗi**. Ký tự nháy trong tên không trở thành dấu nháy mở/đóng của văn bản Cypher. Giá trị được xử lý như dữ liệu cần so sánh với thuộc tính `p.name`.

**Nhưng tham số hóa không làm tất cả hành động trở nên an toàn:** hệ thống vẫn phải kiểm soát người dùng được xem node nào, được đọc/sửa property nào, được phép chạy loại truy vấn nào và có thể yêu cầu giới hạn dữ liệu ra sao. Đặc biệt, tham số hóa **không bảo vệ** đoạn cấu trúc truy vấn được ghép chuỗi ngoài cơ chế tham số.

## 10. Kế hoạch truy vấn và hiệu năng

Neo4j lập kế hoạch thực thi từ câu Cypher và các điều kiện có thể sử dụng index/constraint. Khi chỉ thay đổi giá trị đầu vào, tham số giúp **giữ nguyên văn bản truy vấn** để hệ quản trị có cơ hội tái sử dụng kế hoạch được cache.

Ví dụ hai lần chạy:

```cypher
MATCH (p:Person {id: $personId})
RETURN p.name AS ten;
```

Lần 1: `personId = "c005-an"`. Lần 2: `personId = "c005-binh"`. Cấu trúc biểu thức so khớp ID không đổi.

Tuy nhiên:

- Tham số hóa **không tự tạo index**. Nếu tìm thường xuyên theo `Person.id`, cần đánh giá index hoặc uniqueness constraint trên property này.
- Không phải mọi truy vấn cùng văn bản đều có chi phí ngang nhau: giá trị tham số có thể khớp số lượng node/relationship khác nhau.
- Khả năng cache kế hoạch, lựa chọn operator và cơ chế tối ưu có thể thay đổi theo phiên bản Neo4j.
- Tham số hóa không sửa được việc ghép mẫu sai tạo tích Descartes hoặc làm tăng số dòng khi một node khớp nhiều quan hệ.

Bạn có thể xem kế hoạch dự kiến:

```cypher
EXPLAIN
MATCH (p:Person {id: $personId})
RETURN p.name AS ten;
```

Khi thực thi ở Neo4j Browser hoặc Driver, vẫn phải **cung cấp tham số** `personId`. Dùng `PROFILE` nếu cần quan sát số dòng và thống kê thực tế; lưu ý `PROFILE` có thực thi truy vấn, kể cả truy vấn ghi.

## 11. Ví dụ đọc dữ liệu hoàn chỉnh với tham số

**Yêu cầu:** tìm những người đang hoạt động, từ tuổi tối thiểu, trong danh sách ID đã chọn; trả tên, tuổi, thành phố.

```cypher
MATCH (p:Person)
WHERE p.id IN $personIds
  AND p.active = $active
  AND p.age >= $minAge
RETURN p.id AS id,
       p.name AS ten,
       p.age AS tuoi,
       p.city AS thanhPho
ORDER BY tuoi DESC, id ASC;
```

Input:

```json
{
  "personIds": ["c005-an", "c005-binh", "c005-chi", "c005-dung"],
  "active": true,
  "minAge": 26
}
```

Kết quả kỳ vọng:

| id | ten | tuoi | thanhPho |
|---|---|---:|---|
| c005-an | An | 30 | Hà Nội |
| c005-binh | Bình | 27 | TP. Hồ Chí Minh |

Giải thích theo luồng:

1. `MATCH` chọn các node `Person` có thể khớp.
2. `$personIds` là một **list** dùng cùng toán tử `IN`.
3. `$active` là **boolean** được so với property `p.active`.
4. `$minAge` là **số** được so với `p.age`.
5. `RETURN` chọn các cột; `ORDER BY` quy định thứ tự đầu ra cố định.

Đổi `minAge` sang `31` sẽ cho **0 dòng**, nhưng không cần sửa văn bản câu Cypher.

## 12. Ghi dữ liệu bằng tham số: `MERGE`, `SET` và danh sách bản ghi

### 12.1. Tìm hoặc tạo node theo ID nghiệp vụ

```cypher
MERGE (p:Person {id: $personId})
ON CREATE SET p.name = $name, p.age = $age
ON MATCH SET p.name = $name
RETURN p.id AS id, p.name AS ten, p.age AS tuoi;
```

Input:

```json
{
  "personId": "c005-lan",
  "name": "Lan",
  "age": 29
}
```

`MERGE` kiểm tra node có label `Person` và `id` bằng tham số. `ON CREATE SET` chỉ chạy nếu node mới được tạo; `ON MATCH SET` chạy nếu đã khớp. Đặt ID nghiệp vụ làm điều kiện chính giúp tách việc nhận diện node khỏi những thuộc tính dễ thay đổi như tên hoặc tuổi.

Để bảo đảm ID duy nhất khi có giao dịch đồng thời, cần thiết kế uniqueness constraint tương ứng. `MERGE` tự nó không phải một thay thế cho ràng buộc này.

### 12.2. Tạo hoặc cập nhật relationship theo hai ID

```cypher
MATCH (p:Person {id: $personId})
MATCH (pr:Project {id: $projectId})
MERGE (p)-[w:WORKS_ON]->(pr)
SET w.role = $role
RETURN p.name AS nguoi, pr.name AS duAn, w.role AS vaiTro;
```

Input:

```json
{
  "personId": "c005-dung",
  "projectId": "c005-api",
  "role": "tester"
}
```

Ở đây, `Person`, `Project` và `WORKS_ON` là cấu trúc truy vấn do ứng dụng định nghĩa; ba tham số mang **giá trị** để chọn node và đặt thuộc tính. `MATCH` tìm hai node trước khi `MERGE` quan hệ giúp tránh việc vô tình tạo thêm node không mong muốn.

Đoạn này làm thay đổi dữ liệu thực hành: sau khi chạy, Dũng sẽ có quan hệ `WORKS_ON` nên các ví dụ phía trên giả định Dũng chưa có dự án sẽ không còn đúng. Bạn có thể dùng database thực hành riêng cho từng nhóm ví dụ hoặc khôi phục bộ dữ liệu về trạng thái ban đầu.

### 12.3. Nhập một danh sách bằng `UNWIND`

Ứng dụng có thể gửi **một tham số list chứa nhiều map** để thực hiện nhiều lần thao tác theo cùng một mẫu:

```cypher
UNWIND $rows AS row
MERGE (p:Person {id: row.id})
SET p.name = row.name,
    p.age = row.age
RETURN count(p) AS soBanGhiXuLy;
```

Input ví dụ:

```json
{
  "rows": [
    {"id": "c005-e1", "name": "Hà", "age": 28},
    {"id": "c005-e2", "name": "Minh", "age": 31}
  ]
}
```

`UNWIND` chuyển list thành các dòng trung gian `row`. Dấu chấm `row.id` đọc trường trong map của từng dòng; nó không phải một câu truy vấn tự tạo ra từ chuỗi. Với input này, `count(p)` trong ví dụ trả `2`, phản ánh **số dòng được xử lý** chứ không nhất thiết là số node mới được tạo nếu các ID đã tồn tại.

Với lượng dữ liệu lớn, nên phân lô phù hợp, xem xét giao dịch, constraint và giới hạn bộ nhớ; không nên mặc định gửi toàn bộ dữ liệu khổng lồ trong một tham số list.

## 13. Truyền tham số từ Neo4j Java Driver

Java Driver thực thi văn bản truy vấn cùng một cấu trúc tham số. Ví dụ đơn giản dưới đây minh họa cách gửi giá trị qua `Map`:

```java
import org.neo4j.driver.AuthTokens;
import org.neo4j.driver.Driver;
import org.neo4j.driver.GraphDatabase;
import org.neo4j.driver.Session;

import java.util.List;
import java.util.Map;

public class PersonLookup {
    public static void main(String[] args) {
        // Giá trị kết nối được cấp từ cấu hình môi trường thực tế.
        String uri = System.getenv("NEO4J_URI");
        String username = System.getenv("NEO4J_USER");
        String password = System.getenv("NEO4J_PASSWORD");

        String cypher = """
                MATCH (p:Person)
                WHERE p.id IN $ids AND p.age >= $minAge
                RETURN p.name AS ten
                ORDER BY ten
                """;

        Map<String, Object> params = Map.of(
                "ids", List.of("c005-an", "c005-binh", "c005-chi"),
                "minAge", 28
        );

        try (Driver driver = GraphDatabase.driver(
                     uri, AuthTokens.basic(username, password));
             Session session = driver.session()) {
            List<String> names = session.run(cypher, params)
                    .list(record -> record.get("ten").asString());
            names.forEach(System.out::println);
        }
    }
}
```

Khi chạy với dữ liệu mẫu, danh sách in ra là **An** và **Chi**. Dù đầu vào gồm ba ID, Bình 27 tuổi nên bị lọc bởi `minAge = 28`.

Những điều cần chú ý:

- `session.run(cypher, params)` nhận **văn bản Cypher** và **map tham số** riêng biệt.
- Key trong map `"ids"` ứng với `$ids`; key `"minAge"` ứng với `$minAge`.
- `record.get("ten")` lấy cột kết quả `ten` do `RETURN ... AS ten` tạo ra, **không phải** một tham số.
- `Map.of(...)` của Java không chấp nhận value `null`. Nếu tham số tùy chọn phải là `null`, hãy dùng một `Map` cho phép lưu null hoặc API tạo tham số phù hợp.
- Không ghi trực tiếp URI, mật khẩu và dữ liệu nhạy cảm trong mã nguồn; ví dụ lấy cấu hình từ biến môi trường để nhấn mạnh sự tách biệt này.
- Với ứng dụng production, chọn database, cách quản lý Driver/Session, transaction và timeout phù hợp vòng đời ứng dụng; đoạn mã trên chỉ nhằm minh họa phần **truyền tham số**.

### 13.1. Sai kiểu trong Java có thể dẫn tới không khớp hoặc lỗi

Ví dụ:

```java
// Sai mục đích khi age là số nguyên: truyền chuỗi "28"
Map<String, Object> wrong = Map.of("minAge", "28");

// Đúng: giá trị số
Map<String, Object> correct = Map.of("minAge", 28);
```

Không nên dựa vào Neo4j tự diễn giải chuỗi thành số để so sánh. API nên xác thực kiểu input trước khi tạo map tham số.

## 14. Tham số trong Spring Data Neo4j

Trong Spring Data Neo4j, một repository có thể dùng `@Query` với tham số có tên. Ví dụ khái niệm dưới đây giả định ứng dụng đã có entity `Person` được ánh xạ đúng label `Person` và trường ID:

```java
import org.springframework.data.neo4j.repository.Neo4jRepository;
import org.springframework.data.neo4j.repository.query.Query;
import org.springframework.data.repository.query.Param;
import java.util.List;

public interface PersonRepository
        extends Neo4jRepository<Person, String> {

    @Query("""
           MATCH (p:Person)
           WHERE p.city = $city AND p.age >= $minAge
           RETURN p
           """)
    List<Person> findInCityFromAge(
            @Param("city") String city,
            @Param("minAge") int minAge);
}
```

Điều cần phân biệt:

- `@Query` xác định **cấu trúc Cypher** có mẫu node `Person` và điều kiện lọc.
- `@Param("city")` và `@Param("minAge")` kết nối đối số của phương thức Java với `$city` và `$minAge`.
- `RETURN p` trả **node** để cơ chế ánh xạ entity xử lý. Nếu trả các scalar hoặc projection, cần thiết kế kiểu trả về tương ứng.
- Cách ánh xạ ID, quan hệ, entity, DTO và transaction phụ thuộc cấu hình Spring Data Neo4j của ứng dụng; ví dụ chỉ minh họa tham số, không thay thế thiết kế repository đầy đủ.

Ở ứng dụng thực tế, có thể dùng phương thức truy vấn do framework sinh tự động khi phù hợp. Dù dùng `@Query` hay phương thức repository, hãy giữ dữ liệu người dùng là **giá trị tham số**.

## 15. Phân trang: dữ liệu là tham số, thứ tự là cấu trúc

Truy vấn phân trang có thể lấy offset và kích thước trang từ tham số:

```cypher
MATCH (p:Person)
WHERE p.id IN $ids
RETURN p.id AS id, p.name AS ten, p.age AS tuoi
ORDER BY ten ASC, id ASC
SKIP $offset
LIMIT $pageSize;
```

Input:

```json
{
  "ids": ["c005-an", "c005-binh", "c005-chi", "c005-dung"],
  "offset": 0,
  "pageSize": 2
}
```

Kết quả là tối đa **hai dòng đầu** theo thứ tự `ten, id`. `offset` và `pageSize` phải là giá trị số nguyên phù hợp; ứng dụng nên xác thực chúng **không âm** và giới hạn kích thước trang.

Tại sao `ORDER BY` được viết tĩnh? Vì yêu cầu “sắp theo tên hay theo tuổi” là **thay đổi biểu thức sắp xếp**. Các chuỗi như `"p.age DESC"` không được Neo4j đọc lại thành biểu thức khi truyền vào `$sortBy`. Nếu cho phép UI chọn cách sắp xếp, nên dùng các phương án cố định đã được xác thực.

Khi dùng `SKIP` cho nhiều trang, nhớ rằng dữ liệu có thể thay đổi giữa các lần truy vấn. Với tập dữ liệu lớn và luồng cập nhật thường xuyên, phân trang dựa trên khóa (*keyset pagination*) có thể phù hợp hơn.

## 16. Bảng lỗi thường gặp

| Hiện tượng | Nguyên nhân | Hướng xử lý |
|---|---|---|
| Báo thiếu `$personId` | Map gửi `id` thay vì `personId`, hoặc không gửi key. | Đảm bảo tên tham số khớp và luôn được cung cấp. |
| Không có kết quả khi so ID | Truyền `"p1"` nhưng node lưu `"c005-an"`, hoặc sai kiểu. | Kiểm tra giá trị và kiểu của tham số, đối chiếu dữ liệu. |
| `WHERE p.name = '$name'` luôn so tên với chữ `$name` | Đặt tên tham số bên trong dấu nháy chuỗi. | Viết `WHERE p.name = $name`. |
| `WHERE p.age >= $minAge` lỗi kiểu | Ứng dụng gửi chuỗi `"25"` thay vì số `25`. | Xác thực/chuyển kiểu đầu vào trước khi gửi. |
| `WHERE p.city = $city` không khớp khi `city = null` | So sánh thông thường với null không cho true. | Thiết kế điều kiện `IS NULL` hoặc bộ lọc tùy chọn. |
| `IN [$ids]` không khớp | `$ids` đã là list nhưng bị bọc thêm một list. | Viết `IN $ids`. |
| `MATCH (p:$label)` báo lỗi | Tham số thông thường không được gắn như label tĩnh. | Dùng label tĩnh hoặc cú pháp dynamic label được phiên bản hỗ trợ. |
| `ORDER BY $sortBy` không đổi cách sắp xếp | Chuỗi tham số không trở thành biểu thức Cypher. | Chọn biểu thức sắp xếp đã được ứng dụng duyệt trước. |
| `RETURN p` lỗi sau `WITH p.name AS ten` | Biến `p` không được chuyển tiếp. | `WITH p, p.name AS ten` hoặc chỉ dùng `ten`. |
| Giá trị đầu vào chứa dấu nháy làm truy vấn lỗi | Ứng dụng ghép giá trị trực tiếp vào văn bản Cypher. | Truyền giá trị qua API tham số. |
| Dùng `Map.of("city", null)` trong Java bị lỗi | `Map.of` không chấp nhận null. | Dùng map phù hợp khi cần truyền null. |
| Ghi các thuộc tính ngoài ý muốn bằng `SET p += $changes` | Cho phép map chứa key tùy ý. | Kiểm soát allowlist các property được phép cập nhật. |
| Một node xuất hiện nhiều dòng | Node khớp nhiều relationship; không phải lỗi tham số. | Xác định độ hạt, dùng `DISTINCT`/gom nhóm khi đúng nghiệp vụ. |

## 17. Quy trình thiết kế truy vấn có tham số

Đối với một API truy vấn Neo4j, có thể dùng các bước sau:

1. **Xác định cấu trúc cố định.** Ví dụ: bắt đầu từ node `Person`, tìm `WORKS_ON` đến `Project`, trả tên dự án.
2. **Xác định dữ liệu thay đổi.** Ví dụ: ID người, tuổi tối thiểu, trạng thái dự án, danh sách ID cần lọc.
3. **Đặt tên tham số rõ nghĩa.** Ví dụ `$personId`, `$minAge`, `$status`, `$ids`; tránh tên một chữ dễ nhầm với biến.
4. **Khai báo hợp đồng kiểu dữ liệu.** `personId: String`, `minAge: Integer`, `ids: List<String>`, `status: String`.
5. **Xử lý điều kiện tùy chọn.** Phân biệt key thiếu, `null`, chuỗi rỗng và danh sách rỗng theo nghiệp vụ.
6. **Giới hạn các lựa chọn cấu trúc.** Label, type, cột sắp xếp và property có thể đọc/ghi cần được xác thực theo allowlist; chỉ dùng cú pháp động nếu phiên bản hỗ trợ.
7. **Chạy thử với nhiều bộ giá trị.** Kiểm tra đầu vào bình thường, không khớp, kiểu sai, `null`, ký tự đặc biệt và danh sách rỗng.
8. **Quan sát hiệu năng khi cần.** Dùng `EXPLAIN`, `PROFILE`, đánh giá index/constraint và số dòng trung gian.

Ví dụ hợp đồng API:

```text
Endpoint: GET /people/projects
Input:
  personId: string (bắt buộc)
  status: string (bắt buộc, chỉ active hoặc planned)
Output:
  danh sách tên dự án khớp
```

Truy vấn Cypher:

```cypher
MATCH (p:Person {id: $personId})-[:WORKS_ON]->(pr:Project)
WHERE pr.status = $status
RETURN pr.id AS id, pr.name AS ten
ORDER BY ten;
```

Input ví dụ `{personId: "c005-an", status: "active"}` sẽ trả **Graph API**. Nếu thay `status = "planned"`, truy vấn không trả dự án nào đối với An trong dữ liệu mẫu. **Cấu trúc truy vấn và quyền truy cập vẫn được ứng dụng kiểm soát**, còn các giá trị được thay đổi bằng tham số.

## 18. Bài tập tự luyện

Các bài sau dùng dữ liệu ở mục 4 và giả định chưa chạy các ví dụ ghi thêm người/quan hệ ở mục 12.

### Bài 1. Thay literal bằng tham số

Chuyển câu sau sang dạng nhận tham số `$id`:

```cypher
MATCH (p:Person {id: 'c005-an'})
RETURN p.name AS ten;
```

<details>
<summary>Đáp án tham khảo</summary>

```cypher
MATCH (p:Person {id: $id})
RETURN p.name AS ten;
```

Input: `{"id": "c005-an"}`. Kết quả: **An**.

</details>

### Bài 2. Truyền hai kiểu giá trị

Viết truy vấn tìm người từ tuổi `$minAge`, có `active = $active`, chỉ thuộc bộ bốn ID `c005-`. Với `minAge = 28` và `active = true`, trả tên nào?

<details>
<summary>Đáp án tham khảo</summary>

```cypher
MATCH (p:Person)
WHERE p.id IN ['c005-an', 'c005-binh', 'c005-chi', 'c005-dung']
  AND p.age >= $minAge
  AND p.active = $active
RETURN p.name AS ten;
```

Input: `{"minAge": 28, "active": true}`. Kết quả chỉ có **An** (Chi đủ tuổi nhưng `active = false`).

</details>

### Bài 3. List và toán tử `IN`

Ứng dụng gửi `{"ids": ["c005-binh", "c005-dung"]}`. Viết câu Cypher trả tên của đúng hai người đó, không cần sửa truy vấn mỗi khi danh sách thay đổi.

<details>
<summary>Đáp án tham khảo</summary>

```cypher
MATCH (p:Person)
WHERE p.id IN $ids
RETURN p.name AS ten
ORDER BY ten;
```

Kết quả: **Bình, Dũng**. Nếu `ids = []` thì kết quả rỗng.

</details>

### Bài 4. Tham số hay biến?

Trong câu truy vấn sau, `p`, `Person`, `id`, `$personId`, `ten` thuộc loại nào?

```cypher
MATCH (p:Person {id: $personId})
RETURN p.name AS ten;
```

<details>
<summary>Đáp án</summary>

`p`: biến node. `Person`: label. `id`: property key. `$personId`: tham số do bên gọi truyền. `ten`: bí danh cột trả về. `name` trong `p.name` cũng là property key.

</details>

### Bài 5. Điều kiện tùy chọn với `null`

Viết câu truy vấn cho phép người dùng truyền `city = null` để lấy cả bốn người, hoặc `city = "Hà Nội"` để chỉ lấy An và Chi.

<details>
<summary>Đáp án tham khảo</summary>

```cypher
MATCH (p:Person)
WHERE p.id IN ['c005-an', 'c005-binh', 'c005-chi', 'c005-dung']
  AND ($city IS NULL OR p.city = $city)
RETURN p.name AS ten
ORDER BY ten;
```

Luôn cung cấp key `city`. Nếu chỉ bỏ key khỏi map tham số, truy vấn báo thiếu tham số.

</details>

### Bài 6. Nhận diện chỗ không thể dùng tham số thông thường

Tại sao câu `MATCH (p:$label) RETURN p` không phải cách truyền label động như truyền ID? Hãy nêu một cách xử lý khi chỉ cho phép chọn `Person` hoặc `Project`.

<details>
<summary>Đáp án tham khảo</summary>

Label thuộc cấu trúc mẫu đồ thị, không phải vị trí biểu thức nhận tham số theo cách thay thế `$id`. Ứng dụng có thể chọn **một trong hai truy vấn cố định**, mỗi truy vấn có label tĩnh và các giá trị lọc được tham số hóa:

```cypher
MATCH (p:Person {id: $id})
RETURN p;
```

hoặc:

```cypher
MATCH (pr:Project {id: $id})
RETURN pr;
```

Nếu Neo4j đang dùng hỗ trợ cú pháp dynamic label phù hợp, có thể cân nhắc cú pháp riêng và vẫn cần kiểm soát allowlist, quyền truy cập và kế hoạch thực thi.

</details>

### Bài 7. Viết truy vấn tìm dự án với tham số

Tìm dự án của một người bằng `$personId` và lọc dự án có trạng thái `$status`. Với input `{"personId": "c005-chi", "status": "planned"}`, kết quả dự kiến là gì?

<details>
<summary>Đáp án tham khảo</summary>

```cypher
MATCH (p:Person {id: $personId})-[:WORKS_ON]->(pr:Project)
WHERE pr.status = $status
RETURN pr.name AS duAn;
```

Kết quả: **Data Pipeline**.

</details>

## 19. Ghi nhớ

**Tham số Cypher** được viết bằng `$ten` và nhận giá trị từ bên gọi; **biến Cypher** như `p`, `r` và `pr` được ràng buộc qua mẫu truy vấn, tồn tại theo dòng và phạm vi của các mệnh đề. Label, relationship type, property key, cú pháp `MATCH`/`WHERE`/`RETURN` và biểu thức `ORDER BY` thuộc **cấu trúc câu lệnh**; chúng không tự được thay thế bằng chuỗi tham số như các giá trị ID hoặc tuổi.

Khi tích hợp Neo4j qua Java Driver hoặc Spring Data Neo4j, hãy viết **cấu trúc truy vấn có chủ đích**, truyền dữ liệu người dùng bằng tham số đúng kiểu và xác thực mọi lựa chọn có thể ảnh hưởng đến label, type, property hoặc quyền truy cập. Cách làm này giúp truy vấn dễ tái sử dụng, giảm nguy cơ injection và tạo nền tảng tốt để tối ưu bằng index, constraint và kế hoạch thực thi.
