# UNION và UNION ALL để hợp nhất các tập kết quả

> **Chương:** Truy vấn con  
> **Phạm vi:** Neo4j property graph và Cypher, hợp nhất nhiều nhánh truy vấn bằng `UNION` và `UNION ALL`; đặc biệt là xử lý kết quả đã hợp nhất bên trong `CALL` subquery.  
> **Mục tiêu:** Chọn đúng quy tắc giữ/loại hàng trùng, thiết kế cột trả về nhất quán, kết hợp kết quả từ nhiều loại relationship, tổng hợp hoặc phân trang sau hợp nhất, và viết cú pháp phù hợp với phiên bản Neo4j đang chạy.

## 1. Vì sao cần hợp nhất nhiều tập kết quả?

Trong Neo4j, cùng một dịch vụ có thể liên kết đến dịch vụ khác qua nhiều **loại relationship**. Chẳng hạn:

- `(API)-[:DEPENDS_ON]->(Auth)`: API có phụ thuộc vào Auth.
- `(API)-[:CALLS]->(Auth)`: API gọi Auth khi chạy.
- `(API)-[:CALLS]->(Billing)`: API còn gọi Billing.

Nếu muốn hỏi **“dịch vụ API liên quan tới những dịch vụ nào theo cả hai loại quan hệ?”**, ta có thể chạy hai nhánh `MATCH` khác nhau rồi hợp nhất các hàng trả về:

```cypher
MATCH (:UnionDemoService {id: 'api'})-[:DEPENDS_ON]->(d:UnionDemoService)
RETURN d.name AS destination

UNION

MATCH (:UnionDemoService {id: 'api'})-[:CALLS]->(d:UnionDemoService)
RETURN d.name AS destination;
```

Từ khóa `UNION` ghép kết quả của các **nhánh truy vấn** thành một tập kết quả. Cách dùng phổ biến:

- Hợp nhất kết quả của hai mẫu quan hệ khác nhau.
- Hợp nhất node thuộc các nhóm/nhãn khác nhau vào một kiểu dữ liệu trả về.
- Gom danh sách sự kiện từ các nguồn khác nhau.
- Trả các trường hợp đặc biệt bằng nhiều nhánh có logic đọc khác nhau.
- Dùng `CALL { ... UNION ... }` để **đếm, gom nhóm, sắp xếp hoặc phân trang sau khi hợp nhất**.

Mỗi nhánh có thể có `MATCH`, `WHERE`, `WITH` và `RETURN` riêng. Tuy nhiên, **schema của kết quả** phải tương thích: các nhánh `UNION` phải có **cùng số cột và cùng tên cột**.

## 2. Quy tắc nền tảng: `UNION` loại trùng, `UNION ALL` giữ trùng

Hãy bắt đầu với ví dụ không phụ thuộc dữ liệu trong graph.

### 2.1. `UNION ALL` giữ nguyên tất cả hàng

```cypher
UNWIND ['Auth', 'Catalog'] AS destination
RETURN destination

UNION ALL

UNWIND ['Auth', 'Billing'] AS destination
RETURN destination;
```

Các hàng kết quả (thứ tự hiển thị không được bảo đảm nếu chưa có `ORDER BY`):

| destination |
|---|
| Auth |
| Catalog |
| Auth |
| Billing |

Có **4 hàng**: hai hàng đến từ nhánh đầu và hai hàng từ nhánh sau. `Auth` xuất hiện **hai lần** vì `UNION ALL` giữ các hàng trùng nhau.

Có thể hiểu theo ngữ nghĩa *multiset* (túi chứa các hàng có thể lặp):

```text
Nhánh A: [Auth, Catalog]
Nhánh B: [Auth, Billing]
                 │
                 ▼
             UNION ALL
                 │
                 ▼
[Auth, Catalog, Auth, Billing]    (4 hàng)
```

### 2.2. `UNION` loại các hàng trùng nhau

Cùng dữ liệu nhưng thay `UNION ALL` bằng `UNION`:

```cypher
UNWIND ['Auth', 'Catalog'] AS destination
RETURN destination

UNION

UNWIND ['Auth', 'Billing'] AS destination
RETURN destination;
```

Kết quả có **3 hàng**:

| destination |
|---|
| Auth |
| Catalog |
| Billing |

`UNION` mặc định áp dụng ngữ nghĩa **DISTINCT** cho kết quả hợp nhất. Nó không cần một lệnh `DISTINCT` riêng mới loại trùng.

### 2.3. Bảng chọn nhanh

| Tình huống | Nên dùng | Lý do |
|---|---|---|
| Chỉ muốn danh sách dịch vụ đích **duy nhất** | `UNION` | Cùng một hàng kết quả xuất hiện từ nhiều nhánh thì chỉ giữ một. |
| Cần giữ **mọi lần xuất hiện** để đếm sự kiện, quan hệ hoặc nguồn | `UNION ALL` | Số lần lặp mang ý nghĩa nghiệp vụ. |
| Muốn biết cùng một đích được tìm thấy từ **những loại quan hệ nào** | `UNION ALL` và thêm cột chỉ nguồn | Giữ thông tin của từng nhánh để phân tích. |
| Các nhánh chắc chắn không thể có hàng trùng | Thường dùng `UNION ALL` | Tránh công việc khử trùng lặp không cần thiết; vẫn phải đo hiệu năng. |
| Cần kết quả duy nhất sau khi đã hợp nhất nhiều nhánh | `UNION` hoặc `RETURN DISTINCT` bên ngoài `CALL` khi phù hợp | Chỉ giữ các hàng duy nhất theo đúng các cột được chọn. |

**Ghi nhớ:** `UNION` loại trùng theo **toàn bộ hàng kết quả được trả về**, không mặc định theo tên node, `id` hay một khóa mà ứng dụng tự suy đoán.

## 3. Đồ thị ví dụ: phụ thuộc và lời gọi giữa các dịch vụ

Bài này dùng năm node thuộc nhãn `UnionDemoService`, với hai loại relationship `DEPENDS_ON` và `CALLS`.

```text
                   DEPENDS_ON
          ┌──────────────────────> (Auth)
          │                         ^  ^
          │                         │  │
        (API) ──DEPENDS_ON──> (Catalog)  │
          │                       │      │
          │                       └──────┤ DEPENDS_ON
          │                              │
          └──CALLS──────> (Billing) ──────┘
          │
          └──CALLS────────────────> (Auth)

        (Catalog) ──CALLS─────────> (Auth)
        (Metrics) không có cạnh đi ra trong dữ liệu mẫu
```

Bảng cạnh chính xác:

| Nguồn | Relationship | Đích |
|---|---|---|
| API | `DEPENDS_ON` | Auth |
| API | `DEPENDS_ON` | Catalog |
| Billing | `DEPENDS_ON` | Auth |
| Catalog | `DEPENDS_ON` | Auth |
| API | `CALLS` | Auth |
| API | `CALLS` | Billing |
| Catalog | `CALLS` | Auth |

Tạo dữ liệu trên **database thực hành riêng**:

```cypher
MERGE (api:UnionDemoService {id: 'api'})
  SET api.name = 'API'
MERGE (auth:UnionDemoService {id: 'auth'})
  SET auth.name = 'Auth'
MERGE (catalog:UnionDemoService {id: 'catalog'})
  SET catalog.name = 'Catalog'
MERGE (billing:UnionDemoService {id: 'billing'})
  SET billing.name = 'Billing'
MERGE (metrics:UnionDemoService {id: 'metrics'})
  SET metrics.name = 'Metrics'
WITH api, auth, catalog, billing
MERGE (api)-[:DEPENDS_ON]->(auth)
MERGE (api)-[:DEPENDS_ON]->(catalog)
MERGE (billing)-[:DEPENDS_ON]->(auth)
MERGE (catalog)-[:DEPENDS_ON]->(auth)
MERGE (api)-[:CALLS]->(auth)
MERGE (api)-[:CALLS]->(billing)
MERGE (catalog)-[:CALLS]->(auth);
```

`MERGE` giúp chạy lại ví dụ trên đồ thị mẫu sạch mà không cố ý tạo cạnh trùng kiểu giữa cùng cặp node. Các kết quả bên dưới giả định chỉ có **năm node và bảy cạnh** mang nhãn/kiểu của ví dụ. Nếu database chứa thêm cạnh cùng loại, kết quả thực tế có thể khác.

## 4. Hợp nhất kết quả hai mẫu relationship trên cùng đồ thị

### 4.1. Dùng `UNION ALL` để giữ đủ bốn lần xuất hiện

```cypher
MATCH (:UnionDemoService {id: 'api'})-[:DEPENDS_ON]->(d:UnionDemoService)
RETURN d.name AS destination

UNION ALL

MATCH (:UnionDemoService {id: 'api'})-[:CALLS]->(d:UnionDemoService)
RETURN d.name AS destination;
```

Các giá trị trả về:

| Nhánh | destination |
|---|---|
| `DEPENDS_ON` | Auth |
| `DEPENDS_ON` | Catalog |
| `CALLS` | Auth |
| `CALLS` | Billing |

Có **4 hàng**, trong đó `Auth` xuất hiện hai lần. Bảng thêm cột “Nhánh” để giải thích nguồn, còn truy vấn thực tế chỉ trả đúng **một cột `destination`**.

### 4.2. Dùng `UNION` để lấy đích duy nhất

```cypher
MATCH (:UnionDemoService {id: 'api'})-[:DEPENDS_ON]->(d:UnionDemoService)
RETURN d.name AS destination

UNION

MATCH (:UnionDemoService {id: 'api'})-[:CALLS]->(d:UnionDemoService)
RETURN d.name AS destination;
```

Kết quả có **3 hàng**: `Auth`, `Billing` và `Catalog`. Do hai nhánh cùng trả chuỗi `"Auth"` trong cùng cột `destination`, `UNION` giữ một hàng duy nhất.

### 4.3. Thêm cột nguồn sẽ thay đổi tiêu chí loại trùng

Nếu cần biết một đích được tìm thấy qua loại quan hệ nào, thêm cột `relationType` ở **cả hai nhánh**:

```cypher
MATCH (:UnionDemoService {id: 'api'})-[:DEPENDS_ON]->(d:UnionDemoService)
RETURN d.name AS destination, 'DEPENDS_ON' AS relationType

UNION

MATCH (:UnionDemoService {id: 'api'})-[:CALLS]->(d:UnionDemoService)
RETURN d.name AS destination, 'CALLS' AS relationType;
```

Kết quả có **4 hàng**, dù dùng `UNION`:

| destination | relationType |
|---|---|
| Auth | DEPENDS_ON |
| Catalog | DEPENDS_ON |
| Auth | CALLS |
| Billing | CALLS |

Hai hàng `(Auth, DEPENDS_ON)` và `(Auth, CALLS)` **khác nhau** bởi cột `relationType`, nên không bị loại trùng.

Điều này đặc biệt quan trọng khi dùng `UNION` để hợp nhất các sự kiện từ nhiều nguồn: nếu thêm `source`, `eventId` hay `createdAt` vào `RETURN`, hai hàng vốn có cùng khóa nghiệp vụ có thể trở thành **hai hàng khác nhau**. Khi cần duy nhất theo **một tập khóa cụ thể**, hãy chiếu đúng các khóa đó trước khi khử trùng lặp hoặc tổng hợp sau `CALL`.

## 5. Quy tắc cột và lỗi cú pháp thường gặp

### 5.1. Các nhánh phải trả cùng **số lượng và tên cột**

Đây là câu truy vấn **sai**:

```cypher
// SAI: tên cột không giống nhau.
MATCH (:UnionDemoService {id: 'api'})-[:DEPENDS_ON]->(d)
RETURN d.name AS dependency

UNION

MATCH (:UnionDemoService {id: 'api'})-[:CALLS]->(d)
RETURN d.name AS callee;
```

Nhánh thứ nhất trả cột `dependency`, nhánh thứ hai trả cột `callee`. Để sửa, thống nhất alias:

```cypher
MATCH (:UnionDemoService {id: 'api'})-[:DEPENDS_ON]->(d)
RETURN d.name AS destination

UNION

MATCH (:UnionDemoService {id: 'api'})-[:CALLS]->(d)
RETURN d.name AS destination;
```

Một truy vấn **sai** khác là trả số cột khác nhau:

```cypher
// SAI: nhánh đầu hai cột, nhánh sau chỉ một cột.
MATCH (:UnionDemoService {id: 'api'})-[:DEPENDS_ON]->(d)
RETURN d.name AS destination, 'dependency' AS origin

UNION ALL

MATCH (:UnionDemoService {id: 'api'})-[:CALLS]->(d)
RETURN d.name AS destination;
```

Cách sửa: cả hai đều trả hai cột `destination` và `origin`.

```cypher
MATCH (:UnionDemoService {id: 'api'})-[:DEPENDS_ON]->(d)
RETURN d.name AS destination, 'dependency' AS origin

UNION ALL

MATCH (:UnionDemoService {id: 'api'})-[:CALLS]->(d)
RETURN d.name AS destination, 'runtime-call' AS origin;
```

**Quy tắc thực hành:** xem phần `RETURN` của từng nhánh như một “hợp đồng dữ liệu”: cùng danh sách cột và alias, đồng thời nên có **kiểu dữ liệu tương thích** cho từng cột để ứng dụng dễ xử lý.

### 5.2. Tên biến bên trong các nhánh được đặt độc lập

Hai nhánh có thể dùng tên biến khác nhau nếu alias cuối cùng giống nhau:

```cypher
MATCH (:UnionDemoService {id: 'api'})-[:DEPENDS_ON]->(dependency)
RETURN dependency.name AS destination

UNION ALL

MATCH (:UnionDemoService {id: 'api'})-[:CALLS]->(callee)
RETURN callee.name AS destination;
```

Tên `dependency` và `callee` là biến nội bộ của nhánh tương ứng. Giao diện hợp nhất chỉ quan tâm cột `destination` được xuất ra.

### 5.3. `UNION` loại hàng giống nhau, không tự làm sạch dữ liệu

Hai node khác nhau vẫn có thể có cùng thuộc tính `name`. Nếu chỉ trả `name`, `UNION` xem các giá trị tên giống nhau là trùng trong tập kết quả. Nếu muốn phân biệt **thực thể**, hãy trả node hoặc khóa định danh phù hợp:

```cypher
MATCH (:UnionDemoService {id: 'api'})-[:DEPENDS_ON]->(d)
RETURN d.id AS serviceId, d.name AS destination

UNION

MATCH (:UnionDemoService {id: 'api'})-[:CALLS]->(d)
RETURN d.id AS serviceId, d.name AS destination;
```

Ở đây việc khử trùng lặp dựa trên **cặp cột `(serviceId, destination)`**. Khi ứng dụng cần định danh bền vững, nên có khóa nghiệp vụ `id` và constraint phù hợp, tránh chỉ dựa vào tên hiển thị.

### 5.4. Một hàng có giá trị `null` vẫn là một hàng

Đừng nhầm “không có dữ liệu” với “không có hàng”.

```cypher
UNWIND [null] AS destination
RETURN destination

UNION

UNWIND [null] AS destination
RETURN destination;
```

Hai nhánh đều trả một hàng có `destination = null`; `UNION` chỉ giữ **một hàng**. Nếu dùng `UNION ALL`, sẽ có **hai hàng `null`**.

Tuy nhiên, nếu một nhánh `MATCH` không khớp và **không có `OPTIONAL MATCH`**, nhánh đó trả **0 hàng**. `UNION` không tự bổ sung `null` khi nhánh rỗng.

## 6. `UNION` ở phạm vi truy vấn ngoài và bên trong `CALL`

Vì bài nằm trong chương **Truy vấn con**, cần hiểu hai hình thức.

### 6.1. `UNION` trực tiếp ở cấp truy vấn

```cypher
MATCH (s:UnionDemoService {id: 'api'})-[:DEPENDS_ON]->(d)
RETURN d.name AS destination

UNION ALL

MATCH (s:UnionDemoService {id: 'api'})-[:CALLS]->(d)
RETURN d.name AS destination;
```

Đây là một **combined query**: kết quả của nhiều nhánh được hợp nhất trực tiếp. Có thể dùng cho API chỉ trả dữ liệu thô.

### 6.2. Bọc `UNION` trong `CALL` để xử lý **sau khi hợp nhất**

Từ **Neo4j 5.23**, dùng `CALL ()` nếu truy vấn con không import biến từ ngoài:

```cypher
CALL () {
  MATCH (:UnionDemoService {id: 'api'})-[:DEPENDS_ON]->(d)
  RETURN d.name AS destination

  UNION ALL

  MATCH (:UnionDemoService {id: 'api'})-[:CALLS]->(d)
  RETURN d.name AS destination
}
RETURN destination
ORDER BY destination;
```

Kết quả đã được sắp xếp rõ ràng:

| destination |
|---|
| Auth |
| Auth |
| Billing |
| Catalog |

Kỹ thuật này quan trọng vì `UNION` **không bảo đảm thứ tự hàng kết quả**. Nếu cần sắp xếp hoặc phân trang **toàn bộ tập đã hợp nhất**, đặt `ORDER BY`, `SKIP` và `LIMIT` **bên ngoài khối `CALL`**.

### 6.3. Tổng hợp sau `UNION ALL` để giữ số lần xuất hiện

Ví dụ: “Mỗi dịch vụ đích được tham chiếu bao nhiêu lần theo **hai loại cạnh** trên toàn bộ đồ thị?”

```cypher
CALL () {
  MATCH (s:UnionDemoService)-[:DEPENDS_ON]->(d:UnionDemoService)
  RETURN d.name AS destination

  UNION ALL

  MATCH (s:UnionDemoService)-[:CALLS]->(d:UnionDemoService)
  RETURN d.name AS destination
}
RETURN destination, count(*) AS occurrences
ORDER BY occurrences DESC, destination;
```

| destination | occurrences |
|---|---:|
| Auth | 5 |
| Billing | 1 |
| Catalog | 1 |

Nguồn gốc của `Auth = 5`:

- `DEPENDS_ON` từ API, Billing, Catalog đến Auth: **3 hàng**.
- `CALLS` từ API, Catalog đến Auth: **2 hàng**.
- `UNION ALL` giữ đủ năm hàng; `count(*)` ngoài khối `CALL` gộp theo `destination`.

Nếu thay `UNION ALL` bằng `UNION`, sẽ chỉ còn **một hàng Auth** sau hợp nhất; lúc đó `count(*)` ngoài khối sẽ là 1, **không còn là số lượt xuất hiện**.

### 6.4. Phân trang toàn bộ kết quả

Ví dụ trả hai dòng đầu của danh sách đã hợp nhất sau khi sắp xếp:

```cypher
CALL () {
  MATCH (:UnionDemoService {id: 'api'})-[:DEPENDS_ON]->(d)
  RETURN d.name AS destination

  UNION ALL

  MATCH (:UnionDemoService {id: 'api'})-[:CALLS]->(d)
  RETURN d.name AS destination
}
RETURN destination
ORDER BY destination
SKIP 0
LIMIT 2;
```

Kết quả là hai hàng `Auth`, `Auth` vì dùng `UNION ALL`. Nếu ứng dụng muốn **hai dịch vụ khác nhau**, hãy chuyển thành `UNION` hoặc khử trùng lặp trước khi phân trang.

Khi dùng cursor/pagination trên dữ liệu thật, nên có khóa sắp xếp ổn định, không chỉ dựa vào tên không duy nhất.

## 7. `ORDER BY` và `LIMIT` trong mỗi nhánh khác giới hạn toàn cục

Giả sử muốn tìm **một đích theo thứ tự tên** từ mỗi loại relationship của API:

```cypher
CALL () {
  MATCH (:UnionDemoService {id: 'api'})-[:DEPENDS_ON]->(d)
  RETURN d.name AS destination
  ORDER BY destination
  LIMIT 1

  UNION ALL

  MATCH (:UnionDemoService {id: 'api'})-[:CALLS]->(d)
  RETURN d.name AS destination
  ORDER BY destination
  LIMIT 1
}
RETURN destination
ORDER BY destination;
```

Kết quả có **2 hàng Auth**:

- Nhánh `DEPENDS_ON` xét `Auth, Catalog`, lấy `Auth`.
- Nhánh `CALLS` xét `Auth, Billing`, lấy `Auth`.

Hai `LIMIT 1` áp dụng **riêng cho mỗi nhánh**, rồi `UNION ALL` ghép hai kết quả. Đây là **top một trên từng nguồn**, không phải top một trên toàn bộ nguồn.

Ngược lại:

```cypher
CALL () {
  MATCH (:UnionDemoService {id: 'api'})-[:DEPENDS_ON]->(d)
  RETURN d.name AS destination

  UNION ALL

  MATCH (:UnionDemoService {id: 'api'})-[:CALLS]->(d)
  RETURN d.name AS destination
}
RETURN destination
ORDER BY destination
LIMIT 1;
```

Ví dụ này trả đúng **1 hàng Auth** cho toàn bộ hợp nhất.

| Vị trí `LIMIT` | Ý nghĩa |
|---|---|
| Trong từng nhánh trước `UNION ALL` | Giới hạn **mỗi nguồn/nhánh**. |
| Bên ngoài `CALL` sau hợp nhất | Giới hạn **toàn bộ tập kết quả**. |
| Sau `WITH` trước `CALL` khi có nhiều hàng đầu vào | Giới hạn **số hàng ngoài được gửi vào subquery**. |

Đối với `LIMIT`, nên có `ORDER BY` ở cùng phạm vi để xác định rõ phần tử được chọn.

## 8. `UNION` trong truy vấn con **có tương quan**

Khi cần hợp nhất quan hệ cho **mỗi dịch vụ**, dùng `CALL` nhận node `s` từ truy vấn ngoài. Từ **Neo4j 5.23**, cú pháp khuyên dùng là `CALL (s) { ... }`:

```cypher
MATCH (s:UnionDemoService)
CALL (s) {
  MATCH (s)-[:DEPENDS_ON]->(d:UnionDemoService)
  RETURN d.name AS destination

  UNION ALL

  MATCH (s)-[:CALLS]->(d:UnionDemoService)
  RETURN d.name AS destination
}
RETURN s.name AS sourceService, destination
ORDER BY sourceService, destination;
```

Kết quả có **7 hàng**:

| sourceService | destination |
|---|---|
| API | Auth |
| API | Auth |
| API | Billing |
| API | Catalog |
| Billing | Auth |
| Catalog | Auth |
| Catalog | Auth |

Giải thích:

- API có 2 cạnh `DEPENDS_ON` và 2 cạnh `CALLS`: **4 hàng**.
- Billing có 1 cạnh `DEPENDS_ON`: **1 hàng**.
- Catalog có 1 cạnh `DEPENDS_ON` và 1 cạnh `CALLS`: **2 hàng**.
- Auth và Metrics không có cạnh đi ra: **0 hàng**, nên biến mất khỏi kết quả của returning `CALL`.

`CALL (s)` xử lý theo **từng hàng `s`**. Cả hai nhánh `UNION ALL` bên trong sử dụng cùng node `s` của hàng hiện tại, không cần `WITH s` nữa khi đã dùng scope clause.

### 8.1. Khi dùng `UNION`, mỗi dịch vụ được khử trùng lặp riêng

Thay `UNION ALL` bằng `UNION` trong khối trên:

- API: `Auth, Billing, Catalog` → **3 hàng**.
- Billing: `Auth` → **1 hàng**.
- Catalog: `Auth` → **1 hàng**.
- Auth, Metrics: **0 hàng**.

Tổng cộng **5 hàng**. Việc loại trùng xảy ra **trong từng lần đánh giá subquery cho từng `s`**. Kết quả từ hai node nguồn khác nhau vẫn là hai hàng khác nhau ở truy vấn ngoài (ví dụ Billing → Auth và Catalog → Auth).

### 8.2. Giữ node nguồn không có quan hệ

Từ **Neo4j 5.24**, `OPTIONAL CALL` giữ hàng `s` khi khối con không trả kết quả:

```cypher
MATCH (s:UnionDemoService)
OPTIONAL CALL (s) {
  MATCH (s)-[:DEPENDS_ON]->(d:UnionDemoService)
  RETURN d.name AS destination

  UNION

  MATCH (s)-[:CALLS]->(d:UnionDemoService)
  RETURN d.name AS destination
}
RETURN s.name AS sourceService, destination
ORDER BY sourceService, destination;
```

Kết quả có **7 hàng**: 5 hàng quan hệ duy nhất từ API/Billing/Catalog, cộng Auth và Metrics với `destination = null`.

Nếu muốn **một hàng mỗi dịch vụ** kèm số đích duy nhất, tổng hợp sau `OPTIONAL CALL`:

```cypher
MATCH (s:UnionDemoService)
OPTIONAL CALL (s) {
  MATCH (s)-[:DEPENDS_ON]->(d:UnionDemoService)
  RETURN d.id AS destinationId

  UNION

  MATCH (s)-[:CALLS]->(d:UnionDemoService)
  RETURN d.id AS destinationId
}
RETURN s.name AS service,
       count(destinationId) AS uniqueDestinationCount
ORDER BY service;
```

| service | uniqueDestinationCount |
|---|---:|
| API | 3 |
| Auth | 0 |
| Billing | 1 |
| Catalog | 1 |
| Metrics | 0 |

Lưu ý dùng `count(destinationId)`, vì `count(*)` sẽ đếm cả hàng có `null` do `OPTIONAL CALL` bổ sung. Nếu dùng `count(*)`, Auth và Metrics sẽ bị đếm thành 1, sai mục tiêu nghiệp vụ.

## 9. Hỗ trợ phiên bản Neo4j và Cypher

Không nên coi tất cả cú pháp trong bài đều chạy được ở mọi phiên bản. Những mốc đáng nhớ:

| Môi trường | Cú pháp nên dùng hoặc tính năng mới |
|---|---|
| Neo4j 4.4 | `UNION`, `UNION ALL` và `CALL { ... }` có thể sử dụng; truyền biến ngoài vào mỗi nhánh bằng *importing* `WITH`. |
| Neo4j 5.0–5.18 | `UNION` và `UNION ALL` tiếp tục dùng được; chưa có từ khóa `UNION DISTINCT`. |
| Neo4j 5.19 trở lên | Thêm `UNION DISTINCT`, tương đương ý nghĩa với `UNION`. |
| Neo4j 5.23 trở lên | Có `CALL (s) { ... }`, `CALL () { ... }` thay cách import `WITH` cũ; cách cũ bị đánh dấu *deprecated*. |
| Neo4j 5.24 trở lên | Có `OPTIONAL CALL` để giữ hàng ngoài không có kết quả con. |
| Neo4j 2025.06 trở lên, **Cypher 25** | Có cú pháp **nhóm truy vấn bằng dấu ngoặc nhọn** khi muốn kết hợp `UNION` và `UNION ALL` ở các cấp khác nhau. |

Từ dòng Neo4j **2025.06**, một máy chủ có thể hỗ trợ lựa chọn phiên bản ngôn ngữ **`CYPHER 5`** và **`CYPHER 25`**. Đây là lựa chọn *ngôn ngữ*, khác với bản phát hành Neo4j server. Không thể chạy cú pháp riêng cho 5.23/5.24/Cypher 25 trên máy chủ quá cũ chỉ bằng cách thêm tiền tố `CYPHER 25`.

### 9.1. `UNION DISTINCT` tương đương `UNION`

Từ **Neo4j 5.19**:

```cypher
UNWIND ['Auth', 'Catalog'] AS destination
RETURN destination

UNION DISTINCT

UNWIND ['Auth', 'Billing'] AS destination
RETURN destination;
```

Kết quả vẫn là ba hàng `Auth, Billing, Catalog`. `UNION DISTINCT` diễn đạt tường minh việc loại trùng, phù hợp hướng chuẩn hóa GQL.

### 9.2. Import biến ở **từng nhánh** trên Neo4j cũ

Nếu chạy Neo4j **4.4–5.22**, có thể viết lại ví dụ truy vấn con có tương quan ở mục 8:

```cypher
MATCH (s:UnionDemoService)
CALL {
  WITH s
  MATCH (s)-[:DEPENDS_ON]->(d:UnionDemoService)
  RETURN d.name AS destination

  UNION ALL

  WITH s
  MATCH (s)-[:CALLS]->(d:UnionDemoService)
  RETURN d.name AS destination
}
RETURN s.name AS sourceService, destination
ORDER BY sourceService, destination;
```

**Cực kỳ quan trọng:** trên cú pháp importing `WITH` cũ, mỗi nhánh dùng biến ngoài `s` thì **mỗi nhánh cần `WITH s` riêng**. Chỉ import ở nhánh đầu rồi dùng `s` tại nhánh thứ hai sẽ báo lỗi phạm vi biến.

Với scope clause từ 5.23, một lần khai báo `CALL (s)` áp dụng cho **toàn bộ** khối subquery có các nhánh `UNION`.

### 9.3. Nhóm `UNION` và `UNION ALL` trong Cypher 25

Trên **Neo4j 2025.06+ khi sử dụng Cypher 25**, có thể dùng ngoặc nhọn để nhóm kết quả theo quy tắc mong muốn.

Ví dụ: hợp nhất hai loại relationship rồi **loại trùng trong nhóm**, sau đó bổ sung một hàng kiểm tra `Auth` bằng `UNION ALL`:

```cypher
CYPHER 25
{
  MATCH (:UnionDemoService {id: 'api'})-[:DEPENDS_ON]->(d:UnionDemoService)
  RETURN d.name AS destination

  UNION

  MATCH (:UnionDemoService {id: 'api'})-[:CALLS]->(d:UnionDemoService)
  RETURN d.name AS destination
}

UNION ALL

UNWIND ['Auth'] AS destination
RETURN destination;
```

Phần trong `{ ... }` trả **Auth, Billing, Catalog** (mỗi đích một lần). Nhánh cuối thêm một hàng `Auth`; kết quả có **4 hàng**, trong đó Auth xuất hiện hai lần.

Dấu ngoặc nhọn ở đây dùng để **nhóm combined queries trong Cypher 25**, không phải `CALL` subquery. Đây là tính năng có điều kiện phiên bản: **không dùng nguyên xi ví dụ trên trong Cypher 5 hay Neo4j 5.x cũ**. Với ứng dụng cần tương thích rộng, thường dễ đọc hơn khi sử dụng `CALL` subquery và phân tách các bước xử lý rõ ràng.

## 10. Khi nào nên dùng `UNION` thay vì một mẫu `MATCH` duy nhất?

Đôi khi các nhánh chỉ khác loại relationship, ví dụ lấy đích của `DEPENDS_ON` hoặc `CALLS`. Khi đó Cypher còn hỗ trợ **mẫu quan hệ có nhiều loại**; tùy phiên bản và yêu cầu, có thể viết một `MATCH` thay thế:

```cypher
MATCH (:UnionDemoService {id: 'api'})-[r:DEPENDS_ON|CALLS]->(d:UnionDemoService)
RETURN DISTINCT d.name AS destination
ORDER BY destination;
```

Kết quả: `Auth, Billing, Catalog`. Đây là cách gọn khi **cả hai loại quan hệ dùng cùng hướng, cùng mẫu node, cùng điều kiện lọc**.

Ngược lại, `UNION` hữu ích khi:

- Một nhánh tìm đường quan hệ đi ra, nhánh khác tìm quan hệ đi vào.
- Mỗi nhánh có điều kiện `WHERE` hoặc số bước đường đi rất khác nhau.
- Mỗi nguồn cần `ORDER BY`/`LIMIT` riêng.
- Các nhánh truy vấn các nhãn node khác nhau nhưng muốn chuẩn hóa về cùng các cột đầu ra.
- Cần phân biệt nguồn để tổng hợp theo nhóm.

Ví dụ ghép **hai hướng khác nhau** của `DEPENDS_ON` tại Auth:

```cypher
MATCH (src:UnionDemoService)-[:DEPENDS_ON]->
      (:UnionDemoService {id: 'auth'})
RETURN src.name AS neighbor, 'incoming' AS direction

UNION ALL

MATCH (:UnionDemoService {id: 'auth'})-[:DEPENDS_ON]->
      (dst:UnionDemoService)
RETURN dst.name AS neighbor, 'outgoing' AS direction;
```

Kết quả có **3 hàng incoming** từ API, Billing và Catalog. Auth không có `DEPENDS_ON` đi ra nên nhánh `outgoing` trả 0 hàng. Hai nhánh có thể thiết kế độc lập nhưng vẫn chuẩn hóa cặp cột `neighbor` và `direction`.

### Một `MATCH` với `OR` có luôn tương đương `UNION` không?

Không nhất thiết. `WHERE conditionA OR conditionB` lọc **các hàng đã được `MATCH` tạo ra**, còn `UNION` ghép kết quả từ **hai luồng truy vấn**, mỗi luồng có thể tạo số hàng riêng. Nếu các nhánh tìm những mẫu đường đi khác nhau hoặc trả nhiều hàng cho cùng node, số lượng hàng sẽ khác. Kiểm tra cả **schema và cardinality** trước khi thay thế.

## 11. Hiệu năng: chi phí loại trùng và số hàng được tạo

So với `UNION ALL`, `UNION` có thêm công việc **phát hiện và loại các hàng giống nhau**. Khi các nhánh trả nhiều dữ liệu, công việc này có thể tiêu tốn CPU và bộ nhớ.

Tuy nhiên, không nên suy ra rằng `UNION ALL` **luôn nhanh hơn trong toàn bộ ứng dụng**: giữ nhiều hàng hơn có thể làm các bước `ORDER BY`, `collect()`, `count()`, ánh xạ Java và truyền mạng tốn kém hơn. Lựa chọn đúng trước hết phải dựa trên **ngữ nghĩa nghiệp vụ**.

### 11.1. Kiểm tra bằng `EXPLAIN`

```cypher
EXPLAIN
CALL () {
  MATCH (:UnionDemoService {id: 'api'})-[:DEPENDS_ON]->(d)
  RETURN d.name AS destination

  UNION

  MATCH (:UnionDemoService {id: 'api'})-[:CALLS]->(d)
  RETURN d.name AS destination
}
RETURN destination
ORDER BY destination;
```

`EXPLAIN` hiển thị kế hoạch dự kiến **mà không chạy truy vấn**. Tùy phiên bản/runtime, có thể thấy các operator kết hợp nhánh, loại trùng, mở rộng quan hệ, sắp xếp. Đừng cố gắn chặt kiến thức vào một tên operator, vì cách tổ chức kế hoạch có thể thay đổi.

### 11.2. Đo bằng `PROFILE`

```cypher
PROFILE
CALL () {
  MATCH (:UnionDemoService {id: 'api'})-[:DEPENDS_ON]->(d)
  RETURN d.name AS destination

  UNION ALL

  MATCH (:UnionDemoService {id: 'api'})-[:CALLS]->(d)
  RETURN d.name AS destination
}
RETURN destination, count(*) AS occurrences
ORDER BY occurrences DESC, destination;
```

Đọc các chỉ số như **Rows**, **DB Hits**, **Estimated Rows**, thời gian/bộ nhớ nếu được hiển thị. Có thể so sánh `UNION` với `UNION ALL` trên **dữ liệu đại diện** để biết phần xử lý nào đang tốn tài nguyên.

### 11.3. Lọc trước mỗi nhánh, chọn cột gọn

1. Dùng `WHERE` ở ngay nhánh phù hợp để tránh sinh hàng không cần thiết.
2. Trả các cột đủ cho nghiệp vụ; nhiều cột khiến so sánh trùng lặp phức tạp hơn và có thể làm hai hàng vốn trùng theo khóa chính trở nên khác nhau.
3. Nếu cần top N cho mỗi nguồn, áp dụng `ORDER BY ... LIMIT` trong nhánh. Nếu cần top N của tập hợp, áp dụng ngoài `CALL`.
4. Nếu phải tra cứu node liên tục theo `id`, cân nhắc index/constraint. Từ khóa `UNION` không bù được chi phí quét toàn nhãn ở từng nhánh.
5. Khi một danh sách đã có bảo đảm độc nhất theo khóa, `UNION ALL` có thể tránh khử trùng lặp; đừng tự thêm `DISTINCT` nếu không có yêu cầu.

Trong database demo riêng, có thể tạo uniqueness constraint cho `id`:

```cypher
CREATE CONSTRAINT union_demo_service_id IF NOT EXISTS
FOR (s:UnionDemoService)
REQUIRE s.id IS UNIQUE;
```

Constraint uniqueness giúp tránh các node trùng `id` khác `null` và cung cấp index phục vụ tìm node theo `id`.

## 12. Dùng kết quả `UNION ALL` với Java Driver và Spring Data Neo4j

Các nhánh `UNION` được xử lý **trên Neo4j server**. Ứng dụng Java chỉ gửi **một câu Cypher** và nhận kết quả có schema đã chuẩn hóa.

Ví dụ dùng Java Driver 5.x, với `Driver driver` đã được cấu hình, đọc từng hàng có hai cột `destination` và `relationType`:

```java
import org.neo4j.driver.Session;
import java.util.List;
import java.util.Map;

String cypher = """
    CALL () {
      MATCH (:UnionDemoService {id: $sourceId})-[:DEPENDS_ON]->(d:UnionDemoService)
      RETURN d.name AS destination, 'DEPENDS_ON' AS relationType

      UNION ALL

      MATCH (:UnionDemoService {id: $sourceId})-[:CALLS]->(d:UnionDemoService)
      RETURN d.name AS destination, 'CALLS' AS relationType
    }
    RETURN destination, relationType
    ORDER BY relationType, destination
    """;

try (Session session = driver.session()) {
    List<String> rows = session.executeRead(tx ->
        tx.run(cypher, Map.of("sourceId", "api"))
          .list(record ->
              record.get("relationType").asString()
              + " -> "
              + record.get("destination").asString())
    );
    rows.forEach(System.out::println);
}
```

Kết quả theo thứ tự đã khai báo:

```text
CALLS -> Auth
CALLS -> Billing
DEPENDS_ON -> Auth
DEPENDS_ON -> Catalog
```

Điểm cần nhớ:

- Tham số `$sourceId` dùng chung cho cả hai nhánh. Tránh ghép trực tiếp dữ liệu người dùng vào chuỗi Cypher.
- Do `RETURN` của hai nhánh có **cùng cột**, Java có thể ánh xạ một kiểu dữ liệu trả về duy nhất.
- Trong Spring Data Neo4j, `@Query` tùy chỉnh cũng có thể trả projection/DTO với cùng hai cột `destination` và `relationType`; mapping thực tế phụ thuộc phiên bản và cấu trúc repository.
- `CALL ()` có từ Neo4j 5.23. Với máy chủ cũ hơn, **đổi thành `CALL { ... }`** khi không import biến, giữ nguyên các nhánh `UNION ALL`.
- Nâng cấp Java Driver hoặc Spring Data Neo4j không tự bổ sung cú pháp mới cho **Neo4j server**.

## 13. Những lỗi thường gặp

| Dấu hiệu | Nguyên nhân | Cách xử lý |
|---|---|---|
| `UNION` báo lỗi cột trả về không khớp | Các nhánh dùng alias khác tên hoặc số cột khác nhau. | Đồng nhất danh sách `RETURN ... AS ...` ở mọi nhánh. |
| Mong `UNION` chỉ giữ một Auth nhưng vẫn có hai hàng Auth | Có thêm `relationType`/`source` khác nhau, khiến hai **hàng đầy đủ** không trùng. | Chỉ trả khóa cần khử trùng hoặc `RETURN DISTINCT` đúng tập cột sau khi hợp nhất. |
| Mất số lần xuất hiện khi `count(*)` | Dùng `UNION` trước khi đếm nên đã loại các hàng lặp. | Dùng `UNION ALL` nếu mục tiêu là đếm từng lượt phát sinh. |
| Trùng quá nhiều hàng trong kết quả API | Dùng `UNION ALL` khi chỉ muốn đích duy nhất. | Chuyển sang `UNION` hoặc khử trùng theo khóa phù hợp. |
| Kết quả đảo thứ tự giữa các lần chạy | `UNION` không cam kết thứ tự. | Sắp xếp **sau hợp nhất** qua `CALL` với `ORDER BY` ngoài. |
| `LIMIT 1` trả hai hàng thay vì một | Có `LIMIT 1` riêng ở **hai nhánh**. | Muốn một hàng toàn cục thì giới hạn ngoài `CALL`. |
| `Variable s not defined` trong nhánh thứ hai của `CALL { ... UNION ... }` cũ | Nhánh thứ hai chưa `WITH s` để import. | Dùng importing `WITH s` ở **từng nhánh**; trên 5.23+ dùng `CALL (s)`. |
| Câu truy vấn trả 0 hàng cho dịch vụ không có cạnh | Returning `CALL` không có hàng con để ghép. | `OPTIONAL CALL` từ 5.24+ hoặc dùng tổng hợp/truy vấn thay thế khi cần giữ hàng. |
| `count(*)` tính 1 cho node không có liên kết sau `OPTIONAL CALL` | `OPTIONAL CALL` giữ hàng với cột con `null`. | `count(destinationId)` thay vì `count(*)`. |
| `UNION DISTINCT` bị báo lỗi | Neo4j trước 5.19. | Dùng `UNION` truyền thống. |
| Nhóm `{ ... } UNION ALL ...` không được nhận | Cú pháp nhóm combined queries yêu cầu **Cypher 25** trên máy chủ hỗ trợ. | Dùng cú pháp tương thích hoặc chuyển đúng version, không áp dụng trên bản cũ. |
| Truy vấn chậm dù dùng `UNION ALL` | Các nhánh `MATCH` quét rộng hoặc hậu xử lý phải sắp xếp quá nhiều hàng. | Lọc/index phù hợp, thu hẹp projection và đo bằng `PROFILE`. |

## 14. Bài tập tự luyện

Dùng đồ thị tại mục 3. Hãy thử dự đoán **số hàng** trước khi chạy.

### Bài 1. Hợp nhất danh sách đích của API và giữ số lần xuất hiện

Viết truy vấn trả một cột `destination` từ cả `DEPENDS_ON` và `CALLS`, **giữ trùng**.

**Đáp án:**

```cypher
MATCH (:UnionDemoService {id: 'api'})-[:DEPENDS_ON]->(d)
RETURN d.name AS destination
UNION ALL
MATCH (:UnionDemoService {id: 'api'})-[:CALLS]->(d)
RETURN d.name AS destination;
```

Có **4 hàng**: Auth hai lần, Billing một lần, Catalog một lần.

### Bài 2. Trả danh sách đích duy nhất

Thay đổi bài 1 để chỉ có một hàng cho mỗi tên dịch vụ đích.

**Đáp án:** dùng `UNION` thay `UNION ALL`. Có **3 hàng**: Auth, Billing, Catalog.

### Bài 3. Giải thích vì sao dùng `UNION` vẫn có bốn hàng

```cypher
MATCH (:UnionDemoService {id: 'api'})-[:DEPENDS_ON]->(d)
RETURN d.name AS destination, 'DEPENDS_ON' AS kind
UNION
MATCH (:UnionDemoService {id: 'api'})-[:CALLS]->(d)
RETURN d.name AS destination, 'CALLS' AS kind;
```

**Đáp án:** `UNION` so sánh **cặp `(destination, kind)`**, không chỉ cột `destination`. Hai hàng Auth có `kind` khác nhau nên đều được giữ.

### Bài 4. Đếm số lần xuất hiện của mỗi đích trên toàn đồ thị

Hãy hợp nhất mọi `DEPENDS_ON` và `CALLS` rồi đếm theo `d.name`.

**Đáp án:**

```cypher
CALL () {
  MATCH (:UnionDemoService)-[:DEPENDS_ON]->(d:UnionDemoService)
  RETURN d.name AS destination
  UNION ALL
  MATCH (:UnionDemoService)-[:CALLS]->(d:UnionDemoService)
  RETURN d.name AS destination
}
RETURN destination, count(*) AS appearances
ORDER BY appearances DESC, destination;
```

Kết quả là **Auth = 5, Billing = 1, Catalog = 1**. Truy vấn yêu cầu Neo4j 5.23+ vì dùng `CALL ()`.

### Bài 5. Giữ đủ cả năm dịch vụ, kể cả không có cạnh

Tìm số **đích duy nhất** của từng dịch vụ qua hai loại relationship, kể cả Auth và Metrics.

**Đáp án tham khảo cho Neo4j 5.24+:**

```cypher
MATCH (s:UnionDemoService)
OPTIONAL CALL (s) {
  MATCH (s)-[:DEPENDS_ON]->(d:UnionDemoService)
  RETURN d.id AS destinationId
  UNION
  MATCH (s)-[:CALLS]->(d:UnionDemoService)
  RETURN d.id AS destinationId
}
RETURN s.name AS sourceService,
       count(destinationId) AS destinationCount
ORDER BY sourceService;
```

Kết quả: **API = 3, Auth = 0, Billing = 1, Catalog = 1, Metrics = 0**.

### Bài 6. Sửa lỗi alias

Đoạn sau sai ở đâu?

```cypher
MATCH (a:UnionDemoService)-[:DEPENDS_ON]->(b:UnionDemoService)
RETURN b.name AS dependency
UNION ALL
MATCH (a:UnionDemoService)-[:CALLS]->(b:UnionDemoService)
RETURN b.name AS callee;
```

**Đáp án:** cả hai nhánh phải trả cùng tên cột; sửa thành `RETURN b.name AS destination` ở cả hai nhánh.

## 15. Kết luận và ghi nhớ

1. `UNION ALL` **giữ mọi hàng**, gồm các hàng trùng; `UNION` **loại hàng trùng** trên **toàn bộ cột đã `RETURN`**.
2. Mỗi nhánh cần trả **cùng số lượng và tên cột**, với schema và kiểu dữ liệu được thiết kế nhất quán.
3. Không nên dựa vào thứ tự hàng của `UNION`. Để sắp xếp, phân trang hoặc tổng hợp **sau khi hợp nhất**, đặt các nhánh vào `CALL { ... }`, rồi xử lý ở truy vấn ngoài.
4. Trong `CALL` có tương quan, các nhánh `UNION` xử lý theo từng hàng ngoài. Trên Neo4j 5.23+, dùng `CALL (s)`; trên bản cũ dùng `WITH s` ở **mỗi nhánh**.
5. `OPTIONAL CALL` (5.24+) giữ các hàng không có kết quả con; khi đếm cần chú ý `null`.
6. `UNION DISTINCT` xuất hiện từ Neo4j 5.19 và tương đương `UNION`. Cú pháp nhóm nhiều loại `UNION` là tính năng **Cypher 25** trên Neo4j 2025.06+.
7. Chọn `UNION` hay `UNION ALL` theo **ý nghĩa dữ liệu** trước, sau đó mới đo tác động hiệu năng bằng `EXPLAIN`/`PROFILE`.

## Tài liệu tham khảo

- [Neo4j Cypher Manual — Combined queries (UNION)](https://neo4j.com/docs/cypher-manual/current/queries/composed-queries/combined-queries/) — yêu cầu cột, `UNION`/`UNION ALL`, `UNION DISTINCT`, hậu xử lý và nhóm `UNION` trong Cypher 25.
- [Neo4j Cypher Manual 5 — Combined queries](https://neo4j.com/docs/cypher-manual/5/queries/combined-queries/) — các ví dụ tương thích với Cypher/Neo4j 5.
- [Neo4j Cypher Manual — CALL subqueries](https://neo4j.com/docs/cypher-manual/current/subqueries/call-subquery/) — xử lý kết quả `UNION` sau `CALL`, import biến và truy vấn con có tương quan.
- [Neo4j Cypher Manual — Select Cypher version](https://neo4j.com/docs/cypher-manual/current/queries/select-version/) — phân biệt Cypher 5 và Cypher 25 từ Neo4j 2025.06.
- [Neo4j Cypher Manual — ORDER BY](https://neo4j.com/docs/cypher-manual/current/clauses/order-by/) — quy tắc sắp xếp kết quả, tính xác định của thứ tự.
- [Neo4j Cypher Manual — Execution plans](https://neo4j.com/docs/cypher-manual/current/planning-and-tuning/execution-plans/) — `EXPLAIN` và `PROFILE` để xem chi phí truy vấn.
