# Truy vấn con COUNT và COLLECT khi phiên bản hỗ trợ

> **Chương:** Truy vấn con  
> **Phạm vi:** Neo4j property graph và Cypher; đếm kết quả truy vấn con bằng `COUNT { ... }`, gom kết quả thành danh sách bằng `COLLECT { ... }` và chọn cách viết tương thích khi dùng phiên bản Neo4j cũ.  
> **Mục tiêu:** Hiểu chính xác đơn vị được đếm, cách kiểm soát danh sách trả về, phạm vi biến và những khác biệt với hàm tổng hợp `count()`, `collect()`.

## 1. Vì sao cần `COUNT { ... }` và `COLLECT { ... }`?

Trong Neo4j, một node có thể nối tới rất nhiều node khác qua relationship. Khi hiển thị thông tin một dịch vụ, ta thường muốn vừa giữ **một hàng cho mỗi dịch vụ** vừa tính:

- Dịch vụ phụ thuộc **bao nhiêu** dịch vụ khác?
- Danh sách tên **các dịch vụ mà nó phụ thuộc** gồm những ai?
- Có **bao nhiêu đường phụ thuộc hai bước**?
- Lấy **tối đa hai dependency đầu tiên theo tên** cho từng dịch vụ.
- Có bao nhiêu dependency mang thuộc tính `critical = true`?

Nếu viết `MATCH` trực tiếp cho mọi quan hệ rồi `RETURN`, một dịch vụ có ba quan hệ có thể sinh ba hàng; muốn ra một hàng phải gom nhóm. Các biểu thức truy vấn con giải quyết nhu cầu này ở ngay vị trí của một **biểu thức**:

```cypher
MATCH (s:CountCollectDemoService)
RETURN s.name AS service,
       COUNT { (s)-[:DEPENDS_ON]->(:CountCollectDemoService) } AS directCount,
       COLLECT {
         MATCH (s)-[:DEPENDS_ON]->(d:CountCollectDemoService)
         RETURN d.name AS dependency
         ORDER BY dependency
       } AS dependencies
ORDER BY service;
```

Ý nghĩa:

- `COUNT { ... }` đếm **số hàng được tạo bởi truy vấn con** và trả một số nguyên.
- `COLLECT { ... }` lấy **giá trị của đúng một cột `RETURN`** ở từng hàng con để tạo một danh sách.
- Biến `s` từ truy vấn ngoài được dùng **trực tiếp bên trong** các truy vấn con; không phải khai báo `WITH s` để import.
- Kết quả biểu thức được tính cho mỗi hàng `s`; dùng hai biểu thức này không tự nhân số hàng bên ngoài.

> **Cần phân biệt:** `COUNT { ... }` và `COLLECT { ... }` là **subquery expressions**; `count(...)` và `collect(...)` là **aggregation functions**. Dấu ngoặc nhọn `{ ... }` khác với ngoặc tròn `(...)` cả về cú pháp lẫn phạm vi xử lý.

## 2. Điều kiện phiên bản: không nên áp dụng một cú pháp cho mọi Neo4j

| Phiên bản môi trường | `COUNT { ... }` | `COLLECT { ... }` | Lựa chọn cho ứng dụng |
|---|---|---|---|
| Neo4j 4.4 | Không hỗ trợ dạng `COUNT { ... }` mới | Không hỗ trợ | Dùng `OPTIONAL MATCH` + `count()/collect()` hoặc `CALL { WITH s ... }`. |
| Neo4j 5.0–5.2 | Có biểu thức `COUNT { ... }` cho các mẫu/trường hợp được hỗ trợ | Chưa hỗ trợ | Dùng `COUNT` cho đếm mẫu đơn giản; dùng aggregate hoặc `CALL` để trả danh sách. |
| Neo4j 5.3–5.5 | `COUNT` mở rộng để hỗ trợ truy vấn đọc như `UNION` và `WITH` bên trong | Chưa hỗ trợ | Dùng `COUNT` phức tạp khi cần; danh sách vẫn dựa vào `collect()` hoặc `CALL`. |
| Neo4j 5.6 trở lên | Hỗ trợ | **Hỗ trợ `COLLECT { ... }`** | Có thể dùng cả hai trong `RETURN`/`WHERE`/`SET` tại vị trí biểu thức hợp lệ. |
| Neo4j 2025.06 trở lên, chạy Cypher 5 hoặc Cypher 25 | Hỗ trợ các ví dụ phổ thông của bài | Hỗ trợ các ví dụ phổ thông của bài | Cypher 25 còn có một số dạng truy vấn con điều kiện `WHEN ... THEN ... ELSE` mà Cypher 5 không có. |

**Lưu ý về phiên bản:** Neo4j 5.6 nghĩa là bản phát hành **5.6**, không phải “Cypher 5.6” do người dùng tùy ý chọn. Từ dòng phát hành Neo4j **2025.06**, máy chủ có thể hỗ trợ chọn **Cypher 5** hay **Cypher 25**. Phần ví dụ chính ở đây dùng cú pháp phổ biến của Neo4j **5.6+**, không yêu cầu các cú pháp riêng của Cypher 25.

Nếu hệ thống có nhiều môi trường (development, CI, staging, production), hãy kiểm tra phiên bản **thực sự chạy ở nơi thực thi**, không chỉ dựa vào phiên bản thư viện Java Driver hoặc Spring Data Neo4j. Driver mới không tự bổ sung cú pháp Cypher còn thiếu trên máy chủ cũ.

## 3. Dữ liệu mẫu: sơ đồ phụ thuộc của các dịch vụ

Ta dùng property graph trong hệ thống microservices, gồm năm node dịch vụ. Relationship `:DEPENDS_ON` nghĩa là dịch vụ ở đầu mũi tên phải sử dụng dịch vụ ở cuối mũi tên. Thuộc tính `critical` đánh dấu phụ thuộc quan trọng.

```text
                      DEPENDS_ON
            +------------------------> (Auth)
            |                            ^  ^
            |                            |  |
          (API) ---------> (Catalog) ----+  |
            |                              |
            +--------------> (Billing) ----+
                           DEPENDS_ON

         (Metrics) -- không có DEPENDS_ON đi ra
```

Các cạnh cụ thể:

| Từ | Đến | `critical` |
|---|---|---|
| API | Auth | `true` |
| API | Catalog | `false` |
| API | Billing | `true` |
| Catalog | Auth | `false` |
| Billing | Auth | `true` |

Dữ liệu kiểm thử có thể tạo trong **database thử nghiệm**:

```cypher
MERGE (api:CountCollectDemoService {id: 'api'})
SET api.name = 'API'
MERGE (auth:CountCollectDemoService {id: 'auth'})
SET auth.name = 'Auth'
MERGE (catalog:CountCollectDemoService {id: 'catalog'})
SET catalog.name = 'Catalog'
MERGE (billing:CountCollectDemoService {id: 'billing'})
SET billing.name = 'Billing'
MERGE (metrics:CountCollectDemoService {id: 'metrics'})
SET metrics.name = 'Metrics'
WITH api, auth, catalog, billing
MERGE (api)-[r1:DEPENDS_ON]->(auth)
SET r1.critical = true
MERGE (api)-[r2:DEPENDS_ON]->(catalog)
SET r2.critical = false
MERGE (api)-[r3:DEPENDS_ON]->(billing)
SET r3.critical = true
MERGE (catalog)-[r4:DEPENDS_ON]->(auth)
SET r4.critical = false
MERGE (billing)-[r5:DEPENDS_ON]->(auth)
SET r5.critical = true;
```

`MERGE` khiến các lần chạy lại trên đồ thị mẫu sạch không cố ý tạo thêm mẫu quan hệ giống nhau. Trong hệ thống thật, nên có uniqueness constraint cho khóa định danh. Những kết quả trong bài giả định nhãn `:CountCollectDemoService` chỉ chứa năm node và các cạnh trên.

## 4. `COUNT { ... }` — đếm hàng mà một mẫu hoặc truy vấn con tạo ra

### 4.1. Đếm số dependency trực tiếp

```cypher
MATCH (s:CountCollectDemoService)
RETURN s.name AS service,
       COUNT {
         (s)-[:DEPENDS_ON]->(:CountCollectDemoService)
       } AS dependencyCount
ORDER BY service;
```

| service | dependencyCount |
|---|---:|
| API | 3 |
| Auth | 0 |
| Billing | 1 |
| Catalog | 1 |
| Metrics | 0 |

Ở dạng đơn giản chỉ chứa một mẫu quan hệ, có thể **bỏ từ khóa `MATCH`** trong `COUNT`:

```cypher
COUNT { (s)-[:DEPENDS_ON]->(d:CountCollectDemoService) }
```

Nếu cần nhiều clause hoặc diễn đạt có điều kiện rõ, viết dạng đầy đủ:

```cypher
COUNT {
  MATCH (s)-[:DEPENDS_ON]->(d:CountCollectDemoService)
}
```

Dù API có ba dependency, truy vấn ngoài vẫn chỉ có một hàng `service = 'API'`. Với Auth và Metrics không có dependency, kết quả là **0**, không cần `OPTIONAL MATCH` ở truy vấn ngoài.

### 4.2. Đếm có lọc thuộc tính của relationship

```cypher
MATCH (s:CountCollectDemoService)
RETURN s.name AS service,
       COUNT {
         MATCH (s)-[r:DEPENDS_ON]->(d:CountCollectDemoService)
         WHERE r.critical = true
       } AS criticalCount
ORDER BY service;
```

| service | criticalCount |
|---|---:|
| API | 2 |
| Auth | 0 |
| Billing | 1 |
| Catalog | 0 |
| Metrics | 0 |

Chỉ những **hàng tương ứng với mẫu có `r.critical = true`** được đếm. Có thể kết hợp điều kiện trên node `d`, relationship `r` hoặc tham số `$name`/`$minRisk`.

### 4.3. Lọc truy vấn ngoài theo số lượng quan hệ

Tìm các dịch vụ có từ **hai dependency trực tiếp** trở lên:

```cypher
MATCH (s:CountCollectDemoService)
WHERE COUNT {
  (s)-[:DEPENDS_ON]->(:CountCollectDemoService)
} >= 2
RETURN s.name AS service;
```

Kết quả: **API**.

`COUNT { ... }` có thể xuất hiện trong `WHERE` như một biểu thức số nguyên, không bắt buộc chỉ dùng trong `RETURN`. So sánh với `EXISTS { ... }`:

- `EXISTS { ... }`: trả `true/false`, phù hợp với câu hỏi “có ít nhất một?”.
- `COUNT { ... }`: trả số `0, 1, 2, ...`, phù hợp với “có bao nhiêu?” hoặc “có từ N trở lên?”.

Với điều kiện đơn giản `> 0`, `EXISTS` thể hiện ý định rõ hơn; với ngưỡng `>= 2`, `COUNT` là lựa chọn tự nhiên.

### 4.4. Đếm đường đi và đếm node đích là hai yêu cầu khác nhau

Xét các đường phụ thuộc **đúng hai bước**:

```cypher
MATCH (s:CountCollectDemoService {id: 'api'})
RETURN COUNT {
  MATCH (s)-[:DEPENDS_ON]->(:CountCollectDemoService)
        -[:DEPENDS_ON]->(downstream:CountCollectDemoService)
} AS twoHopPathCount;
```

Kết quả là **2**, vì có hai cách đi:

```text
API -> Catalog -> Auth
API -> Billing -> Auth
```

Nhưng cả hai đường đều tới **một node đích Auth**. Nếu muốn đếm **số node đích khác nhau**, dùng `RETURN DISTINCT` ngay trong `COUNT` (Neo4j 5.3+):

```cypher
MATCH (s:CountCollectDemoService {id: 'api'})
RETURN COUNT {
  MATCH (s)-[:DEPENDS_ON]->(:CountCollectDemoService)
        -[:DEPENDS_ON]->(downstream:CountCollectDemoService)
  RETURN DISTINCT downstream
} AS uniqueDownstreamCount;
```

Kết quả là **1**. Khác biệt nằm ở **hàng con được đếm**:

| Cách viết | Mỗi hàng con đại diện cho | Giá trị cho API |
|---|---|---:|
| `COUNT { MATCH (s)-[:DEPENDS_ON]->()-[:DEPENDS_ON]->(d) }` | Một kết quả khớp đường hai bước | 2 |
| `COUNT { MATCH (s)-[:DEPENDS_ON]->()-[:DEPENDS_ON]->(d) RETURN DISTINCT d }` | Một node đích duy nhất | 1 |

Trong mô hình có nhiều tuyến dẫn đến cùng dịch vụ, đếm đường đi và đếm dịch vụ bị ảnh hưởng có thể khác rất xa nhau. Trước khi viết truy vấn, cần xác định chính xác muốn đếm **quan hệ, mẫu đường đi, hay node khác nhau**.

### 4.5. `COUNT` với `UNION`: chú ý trùng lặp

Từ Neo4j **5.3+**, `COUNT` hỗ trợ truy vấn đọc phức tạp, bao gồm `UNION`. Ví dụ muốn đếm **tên dịch vụ** xuất hiện trong danh sách phụ thuộc trực tiếp **hoặc** phụ thuộc hai bước:

```cypher
MATCH (s:CountCollectDemoService {id: 'api'})
RETURN COUNT {
  MATCH (s)-[:DEPENDS_ON]->(d:CountCollectDemoService)
  RETURN d.name AS depName
  UNION
  MATCH (s)-[:DEPENDS_ON]->(:CountCollectDemoService)
        -[:DEPENDS_ON]->(d:CountCollectDemoService)
  RETURN d.name AS depName
} AS distinctAffectedServiceCount;
```

Kết quả là **3** (Auth, Billing, Catalog). `UNION` loại bỏ các hàng trùng nhau sau khi ghép hai nhánh.

Nếu thay bằng `UNION ALL`, kết quả là **5**: ba kết quả trực tiếp và hai đường hai bước đi tới Auth. Với `UNION` (loại trùng), mỗi nhánh cần `RETURN` cùng số lượng và tên cột; hãy viết tường minh `AS depName` để dễ kiểm soát.

## 5. `COLLECT { ... }` — tạo danh sách ngay trong biểu thức

### 5.1. Cú pháp cơ bản và kết quả danh sách rỗng

Từ **Neo4j 5.6**, có thể viết:

```cypher
MATCH (s:CountCollectDemoService)
RETURN s.name AS service,
       COLLECT {
         MATCH (s)-[:DEPENDS_ON]->(d:CountCollectDemoService)
         RETURN d.name AS dependency
         ORDER BY dependency
       } AS dependencies
ORDER BY service;
```

| service | dependencies |
|---|---|
| API | `["Auth", "Billing", "Catalog"]` |
| Auth | `[]` |
| Billing | `["Auth"]` |
| Catalog | `["Auth"]` |
| Metrics | `[]` |

Điểm khác `COUNT` là `COLLECT` **bắt buộc kết thúc bằng một `RETURN` có đúng một cột**. Cột đó có thể là chuỗi, số, node, relationship, map hoặc một giá trị khác Cypher hỗ trợ trong danh sách.

Khi truy vấn con không có hàng kết quả, giá trị trả về là **danh sách rỗng `[]`**. Đây là một tiện ích quan trọng khi xây API: có thể trả `dependencies: []` thay vì làm biến mất dịch vụ không có quan hệ.

**Hai dạng không hợp lệ:**

```cypher
// SAI: thiếu RETURN cuối cùng
MATCH (s:CountCollectDemoService)
RETURN COLLECT {
  MATCH (s)-[:DEPENDS_ON]->(d:CountCollectDemoService)
} AS dependencies;
```

```cypher
// SAI: RETURN hai cột, trong khi COLLECT chỉ cho một cột
MATCH (s:CountCollectDemoService)
RETURN COLLECT {
  MATCH (s)-[r:DEPENDS_ON]->(d:CountCollectDemoService)
  RETURN d.name, r.critical
} AS dependencies;
```

### 5.2. Trả một map khi cần nhiều trường

Để lấy cả tên dependency lẫn mức độ quan trọng, gói chúng vào **một giá trị map**:

```cypher
MATCH (s:CountCollectDemoService {id: 'api'})
RETURN COLLECT {
  MATCH (s)-[r:DEPENDS_ON]->(d:CountCollectDemoService)
  RETURN {name: d.name, critical: r.critical} AS item
  ORDER BY item.name
} AS dependencies;
```

Kết quả:

```json
[
  {"name": "Auth", "critical": true},
  {"name": "Billing", "critical": true},
  {"name": "Catalog", "critical": false}
]
```

`RETURN { ... } AS item` tạo **một cột kiểu map**, đáp ứng quy tắc `COLLECT`. Khi dùng Java Driver, cột này có dạng danh sách các giá trị map; ứng dụng có thể ánh xạ sang DTO phù hợp.

### 5.3. Lấy Top N theo từng node với `ORDER BY` và `LIMIT`

Mục tiêu: lấy **hai dependency có tên đứng đầu theo thứ tự chữ cái** của **mỗi dịch vụ**:

```cypher
MATCH (s:CountCollectDemoService)
RETURN s.name AS service,
       COLLECT {
         MATCH (s)-[:DEPENDS_ON]->(d:CountCollectDemoService)
         RETURN d.name AS dependency
         ORDER BY dependency
         LIMIT 2
       } AS firstTwoDependencies
ORDER BY service;
```

Kết quả của API là `["Auth", "Billing"]`, không có Catalog. Các dịch vụ chỉ có một dependency giữ danh sách một phần tử; Auth và Metrics là `[]`.

`LIMIT 2` ở **bên trong** `COLLECT` giới hạn kết quả **cho mỗi node `s`**. Ngược lại, `LIMIT 2` ở cuối truy vấn ngoài chỉ giới hạn hai **dịch vụ** được trả về.

Nếu muốn phân trang danh sách liên kết, có thể đặt `SKIP` và `LIMIT` sau `ORDER BY` bên trong, với điều kiện ứng dụng xác định được một thứ tự ổn định. Không có `ORDER BY`, **thứ tự các phần tử không được bảo đảm**.

### 5.4. Loại trùng trong danh sách

Nếu nhiều đường khác nhau dẫn tới cùng node đích, `COLLECT` mặc định nhận giá trị ở **từng hàng**, nên có thể có phần tử trùng.

```cypher
MATCH (s:CountCollectDemoService {id: 'api'})
RETURN COLLECT {
  MATCH (s)-[:DEPENDS_ON]->(:CountCollectDemoService)
        -[:DEPENDS_ON]->(d:CountCollectDemoService)
  RETURN d.name AS downstream
  ORDER BY downstream
} AS allTwoHopDestinations;
```

Kết quả: `["Auth", "Auth"]` (hai đường khác nhau).

Muốn danh sách node đích **không trùng**, thêm `DISTINCT`:

```cypher
MATCH (s:CountCollectDemoService {id: 'api'})
RETURN COLLECT {
  MATCH (s)-[:DEPENDS_ON]->(:CountCollectDemoService)
        -[:DEPENDS_ON]->(d:CountCollectDemoService)
  RETURN DISTINCT d.name AS downstream
  ORDER BY downstream
} AS uniqueTwoHopDestinations;
```

Kết quả: `["Auth"]`.

**Quy tắc:** `COLLECT { ... }` không mặc nhiên loại trùng. Tên “collect” diễn tả việc gom các **hàng kết quả**, không có nghĩa là tạo một tập hợp (*set*).

### 5.5. Dùng `COLLECT` như một biểu thức trong `WHERE` hoặc `CASE`

Dùng `COLLECT { ... }` trong biểu thức membership:

```cypher
MATCH (s:CountCollectDemoService)
WHERE 'Auth' IN COLLECT {
  MATCH (s)-[:DEPENDS_ON]->(d:CountCollectDemoService)
  RETURN d.name AS dependency
}
RETURN s.name AS service
ORDER BY service;
```

Kết quả: **API, Billing, Catalog**. Với câu hỏi đơn giản “có dependency tên Auth không?”, `EXISTS { MATCH ... WHERE ... }` thường diễn đạt tốt hơn và tránh phải tạo danh sách. Nhưng `COLLECT` hữu ích khi cần **danh sách thực tế** cho phần xử lý tiếp theo.

## 6. Khác biệt giữa subquery expression và aggregate function

Hai cặp tên dễ gây nhầm:

| Cú pháp | Thuộc loại | Đơn vị xử lý | Kết quả |
|---|---|---|---|
| `COUNT { MATCH ... }` | Biểu thức truy vấn con | Các hàng do truy vấn **bên trong ngoặc nhọn** tạo ra cho mỗi hàng ngoài | Số nguyên |
| `count(d)` | Hàm tổng hợp | Các giá trị `d` khác `null` trong **nhóm hàng hiện tại** | Số nguyên |
| `COLLECT { MATCH ... RETURN d.name }` | Biểu thức truy vấn con | Giá trị của một cột ở các hàng con | Danh sách |
| `collect(d.name)` | Hàm tổng hợp | Các giá trị `d.name` khác `null` trong nhóm hàng hiện tại | Danh sách |

Ví dụ tổng hợp bằng `OPTIONAL MATCH`:

```cypher
MATCH (s:CountCollectDemoService)
OPTIONAL MATCH (s)-[:DEPENDS_ON]->(d:CountCollectDemoService)
RETURN s.name AS service,
       count(d) AS dependencyCount,
       collect(d.name) AS dependencies
ORDER BY service;
```

Truy vấn trên vẫn trả đủ năm dịch vụ; `count(d)` cho `0` khi `d = null`, còn `collect(d.name)` bỏ các giá trị `null` nên trả `[]` với Auth và Metrics.

Cách này hữu ích cho phiên bản cũ, nhưng cần chú ý **nhân số hàng trước khi tổng hợp**. Nếu sau `MATCH` đầu tiên có hai nhánh quan hệ độc lập, ví dụ một dịch vụ có 3 dependency và 4 deployment, hai `MATCH` liên tiếp có thể tạo **3 × 4 = 12 hàng**. Khi đó `count(d)` và `collect(d.name)` có thể bị lặp hoặc sai nếu không xử lý nhóm/`DISTINCT`.

Với `COUNT { ... }` và `COLLECT { ... }`, mỗi biểu thức xử lý **mẫu riêng gắn với `s`**, tránh vấn đề nhân hàng do kết hợp nhiều mẫu độc lập trong cùng một luồng kết quả:

```cypher
MATCH (s:CountCollectDemoService)
RETURN s.name AS service,
       COUNT {
         (s)-[:DEPENDS_ON]->(:CountCollectDemoService)
       } AS dependencyCount,
       COLLECT {
         MATCH (s)-[:DEPENDS_ON]->(d:CountCollectDemoService)
         RETURN d.name AS name
         ORDER BY name
       } AS dependencyNames
ORDER BY service;
```

Việc đổi cú pháp không tự bảo đảm tốc độ tốt hơn; nó chủ yếu làm rõ rằng số đếm và danh sách được tạo theo từng node ngoài.

## 7. Biến ngoài, biến trong và những cái bẫy phạm vi

### 7.1. Biến ngoài được dùng trực tiếp

```cypher
MATCH (s:CountCollectDemoService)
RETURN s.name AS service,
       COUNT {
         MATCH (s)-[r:DEPENDS_ON]->(d:CountCollectDemoService)
         WHERE r.critical = true
       } AS criticalCount,
       COLLECT {
         MATCH (s)-[:DEPENDS_ON]->(d:CountCollectDemoService)
         RETURN d.id AS dependencyId
       } AS dependencyIds;
```

Biến `s` được định nghĩa ở truy vấn ngoài nên khả dụng trong **cả hai** expression. Các biến `r`, `d` khai báo trong mỗi expression có scope cục bộ; chúng không “rò” ra ngoài.

Ví dụ **sai**:

```cypher
// SAI: d chỉ được khai báo bên trong COLLECT.
MATCH (s:CountCollectDemoService)
RETURN COLLECT {
  MATCH (s)-[:DEPENDS_ON]->(d:CountCollectDemoService)
  RETURN d.name AS dependency
} AS dependencies,
d.name AS outsideName;
```

Nếu muốn tên `d` ở mức hàng ngoài, cần một `MATCH` phù hợp hoặc `CALL { ... RETURN ... }` để xuất biến.

### 7.2. Không khai báo lại biến ngoài bằng cùng tên trong expression

Các biến từ outer scope có thể truy cập suốt truy vấn con; tránh **shadowing** bằng cách tạo biến mới có cùng tên. Ví dụ:

```cypher
// SAI: biến 'target' đã tồn tại ở ngoài, lại được khai báo trong WITH bên trong.
WITH 'Auth' AS target
MATCH (s:CountCollectDemoService {id: 'api'})
RETURN COUNT {
  WITH 'Billing' AS target
  MATCH (s)-[:DEPENDS_ON]->(d:CountCollectDemoService)
  WHERE d.name = target
} AS n;
```

Cách sửa: dùng tên khác như `desiredName`:

```cypher
WITH 'Auth' AS target
MATCH (s:CountCollectDemoService {id: 'api'})
RETURN COUNT {
  WITH 'Billing' AS desiredName
  MATCH (s)-[:DEPENDS_ON]->(d:CountCollectDemoService)
  WHERE d.name = desiredName
} AS n;
```

Kết quả là **1** vì API phụ thuộc Billing. Biến `target` ngoài không bị đổi. Các trường hợp `WITH` bên trong dạng phức tạp thuộc phần được hỗ trợ từ Neo4j 5.3+ đối với `COUNT`; `COLLECT` từ 5.6+.

### 7.3. Cẩn thận với `OPTIONAL MATCH` và aggregate bên trong `COUNT`

`COUNT { ... }` **đếm hàng truy vấn con**, không đếm giá trị khác `null`.

Ví dụ sau có thể gây hiểu nhầm:

```cypher
MATCH (s:CountCollectDemoService {id: 'metrics'})
RETURN COUNT {
  OPTIONAL MATCH (s)-[:DEPENDS_ON]->(d:CountCollectDemoService)
  RETURN d
} AS rowsFromOptionalMatch;
```

Kết quả là **1**, dù Metrics không có dependency. Lý do: `OPTIONAL MATCH` tạo **một hàng có `d = null`** khi không tìm thấy quan hệ; `COUNT { ... }` đếm hàng đó.

Tương tự:

```cypher
MATCH (s:CountCollectDemoService {id: 'metrics'})
RETURN COUNT {
  MATCH (s)-[:DEPENDS_ON]->(d:CountCollectDemoService)
  RETURN count(d) AS innerCount
} AS rowsFromAggregation;
```

Kết quả cũng là **1**: `RETURN count(d)` tạo **một hàng tổng hợp** với giá trị `0`, nên lớp `COUNT { ... }` bên ngoài đếm một hàng. Để đếm dependency, dùng `COUNT { MATCH ... }` trực tiếp; không lồng tổng hợp như trên.

Đối với `COLLECT`, nếu dùng `OPTIONAL MATCH` rồi `RETURN d.name` khi không khớp, có thể nhận phần tử `null` thay vì danh sách rỗng vì truy vấn con đã có một hàng `null`. Muốn `[]` khi không có liên kết, dùng `MATCH` thông thường trong `COLLECT` và để biểu thức tự xử lý trường hợp 0 hàng.

## 8. Ứng dụng thực tế: trang tổng quan phụ thuộc và cảnh báo

Ví dụ một truy vấn trả đủ thông tin để hiển thị một dòng trên dashboard quản trị dịch vụ:

```cypher
MATCH (s:CountCollectDemoService)
RETURN
  s.id AS id,
  s.name AS name,
  COUNT {
    MATCH (s)-[:DEPENDS_ON]->(:CountCollectDemoService)
  } AS dependencyCount,
  COUNT {
    MATCH (s)-[r:DEPENDS_ON]->(:CountCollectDemoService)
    WHERE r.critical = true
  } AS criticalDependencyCount,
  COLLECT {
    MATCH (s)-[:DEPENDS_ON]->(d:CountCollectDemoService)
    RETURN d.name AS dependencyName
    ORDER BY dependencyName
  } AS dependencyNames
ORDER BY name;
```

| name | dependencyCount | criticalDependencyCount | dependencyNames |
|---|---:|---:|---|
| API | 3 | 2 | `["Auth", "Billing", "Catalog"]` |
| Auth | 0 | 0 | `[]` |
| Billing | 1 | 1 | `["Auth"]` |
| Catalog | 1 | 0 | `["Auth"]` |
| Metrics | 0 | 0 | `[]` |

Từ kết quả này, ứng dụng có thể phân loại dịch vụ có nhiều phụ thuộc cần giám sát, dịch vụ không phụ thuộc hệ thống khác, hoặc tạo DTO trả cho API. Dữ liệu được mô hình hóa bằng node/relationship; `COUNT` và `COLLECT` là **phần đọc và tạo biểu thức**, không thay đổi graph.

Một điều kiện cảnh báo đơn giản:

```cypher
MATCH (s:CountCollectDemoService)
WHERE COUNT {
  MATCH (s)-[r:DEPENDS_ON]->(:CountCollectDemoService)
  WHERE r.critical = true
} >= 2
RETURN s.name AS serviceRequiringReview;
```

Kết quả: **API**.

## 9. Cách viết thay thế khi máy chủ chưa hỗ trợ `COLLECT { ... }`

### 9.1. Neo4j 4.4 hoặc 5.0–5.5: aggregate `collect()`

Nếu chưa có biểu thức `COLLECT { ... }`, vẫn có thể dùng:

```cypher
MATCH (s:CountCollectDemoService)
OPTIONAL MATCH (s)-[:DEPENDS_ON]->(d:CountCollectDemoService)
RETURN s.name AS service,
       count(d) AS dependencyCount,
       collect(d.name) AS dependencyNames
ORDER BY service;
```

Phương án này tương thích rộng hơn, nhưng dễ gặp vấn đề **nhân hàng** nếu sau đó nối nhiều mẫu độc lập vào cùng một dòng `MATCH`.

### 9.2. Neo4j 4.4–5.22: `CALL { WITH s ... }` khi cần Top N cho từng node

Đối với danh sách có lọc/sắp xếp/giới hạn riêng theo node, `CALL` subquery có thể tạo một cột danh sách:

```cypher
MATCH (s:CountCollectDemoService)
CALL {
  WITH s
  OPTIONAL MATCH (s)-[:DEPENDS_ON]->(d:CountCollectDemoService)
  WITH d
  ORDER BY d.name
  RETURN collect(d.name)[0..2] AS firstTwoDependencies
}
RETURN s.name AS service, firstTwoDependencies
ORDER BY service;
```

Giải thích:

- `WITH s` đầu tiên import biến ngoài theo cú pháp `CALL` cũ.
- `OPTIONAL MATCH` giữ cả Auth/Metrics không có dependency.
- `WITH d ORDER BY d.name` sắp xếp trước khi `collect()` tổng hợp, sau đó lát cắt `[0..2]` chỉ lấy phần tử có chỉ số 0 và 1.
- `collect(d.name)` bỏ giá trị `null`, nên danh sách của Auth/Metrics vẫn là `[]`.

Từ Neo4j 5.23+, với `CALL` subquery mới, có thể import tường minh bằng `CALL (s) { ... }`. Tuy nhiên, **`COUNT { ... }` và `COLLECT { ... }` vẫn không cần cú pháp import đó**.

### 9.3. Chọn cách viết theo nhu cầu

| Bài toán | Neo4j mới đủ tính năng | Phiên bản cũ |
|---|---|---|
| Đếm dependency theo từng node | `COUNT { ... }` | `OPTIONAL MATCH` + `count(d)`, hoặc `CALL` với aggregate |
| Danh sách dependency theo từng node | `COLLECT { ... RETURN ... }` (5.6+) | `collect(d.name)` hoặc `CALL` + `collect()` |
| Top 2 dependency cho mỗi node | `COLLECT { ... ORDER BY ... LIMIT 2 }` | `CALL`, sắp xếp rồi `collect()[0..2]` |
| Cần trả nhiều cột cho từng dependency | `COLLECT` trả **một map** mỗi hàng | `collect({ ... })` hoặc `CALL` returning subquery |
| Chỉ kiểm tra có dependency không | `EXISTS { ... }` | `EXISTS { ... }` theo cú pháp phiên bản hỗ trợ |

## 10. Tương tác với Java Driver và Spring Data Neo4j

Các biểu thức `COUNT`/`COLLECT` chạy trên **server**. Java Driver chỉ gửi Cypher và nhận giá trị trả về, còn Spring Data Neo4j xây dựng mapping giữa dữ liệu đồ thị và đối tượng Java.

Ví dụ Java Driver 5.x, với một `Driver driver` đã được cấu hình và kết nối:

```java
import org.neo4j.driver.Record;
import org.neo4j.driver.Session;
import org.neo4j.driver.Value;

import java.util.List;
import java.util.Map;

String query = """
    MATCH (s:CountCollectDemoService {id: $serviceId})
    RETURN COUNT {
             (s)-[:DEPENDS_ON]->(:CountCollectDemoService)
           } AS dependencyCount,
           COLLECT {
             MATCH (s)-[:DEPENDS_ON]->(d:CountCollectDemoService)
             RETURN d.name AS dependency
             ORDER BY dependency
           } AS dependencies
    """;

try (Session session = driver.session()) {
    Record record = session.run(
        query, Map.of("serviceId", "api")
    ).single();

    int dependencyCount = record.get("dependencyCount").asInt();
    List<String> dependencies =
        record.get("dependencies").asList(Value::asString);

    System.out.println(dependencyCount); // 3
    System.out.println(dependencies);    // [Auth, Billing, Catalog]
}
```

Trong ví dụ, `COUNT` trả số nguyên; `COLLECT` trả `List<String>` có thứ tự nhờ `ORDER BY`. Nếu trả map, node hoặc relationship, hãy chọn API chuyển đổi `Value` tương ứng thay vì gọi `asString()` cho mọi phần tử.

Với Spring Data Neo4j, một repository query tùy chỉnh cũng có thể dùng cú pháp Cypher mà **máy chủ** hỗ trợ. Cần xác nhận mapping của projection/DTO theo phiên bản thư viện và loại dữ liệu cột. Đặc biệt, `COLLECT` trả về **một danh sách giá trị**, không đồng nghĩa Spring Data Neo4j tự động nạp toàn bộ entity graph hay quan hệ vào các trường entity.

**Không thể giải quyết lỗi “Invalid input COLLECT” bằng cách nâng cấp riêng Java Driver** khi Neo4j server vẫn là bản trước 5.6. Hãy chọn fallback `collect()`/`CALL` hoặc nâng cấp database.

## 11. Hiệu năng và kế hoạch truy vấn

### 11.1. Phạm vi node ngoài quyết định số lần đánh giá biểu thức

`COUNT` và `COLLECT` là các biểu thức có thể tương quan với `s` ở ngoài. Nếu `MATCH (s:CountCollectDemoService)` trả 10.000 node, các mẫu con sẽ phải được xử lý cho rất nhiều hàng. Việc gom thành một biểu thức **không loại bỏ chi phí duyệt quan hệ**.

Hãy lọc đối tượng sớm:

```cypher
EXPLAIN
MATCH (s:CountCollectDemoService {id: $serviceId})
RETURN COUNT {
  (s)-[:DEPENDS_ON]->(:CountCollectDemoService)
} AS dependencyCount;
```

Khi cần số hàng và chi phí thực tế:

```cypher
PROFILE
MATCH (s:CountCollectDemoService {id: $serviceId})
RETURN COLLECT {
  MATCH (s)-[:DEPENDS_ON]->(d:CountCollectDemoService)
  RETURN d.name AS name
  ORDER BY name
  LIMIT 5
} AS topDependencies;
```

Dùng `EXPLAIN` để xem kế hoạch mà không thực thi; dùng `PROFILE` để thu thống kê vận hành. Đừng dựa vào một tên operator cố định vì planner có thể thay đổi theo phiên bản và tình trạng thống kê.

### 11.2. Index và constraint

Khóa `id` là cách tự nhiên để tìm node đầu vào. Trong database demo riêng, có thể tạo uniqueness constraint:

```cypher
CREATE CONSTRAINT count_collect_demo_service_id IF NOT EXISTS
FOR (s:CountCollectDemoService)
REQUIRE s.id IS UNIQUE;
```

Constraint này ngăn các node thuộc nhãn demo có cùng `id` khác `null`, đồng thời có index hỗ trợ truy cập theo `id`. Lưu ý: constraint uniqueness không đồng nghĩa mọi node buộc phải có `id`; quy tắc bắt buộc thuộc tính là một loại constraint khác và có điều kiện phiên bản/edition riêng.

### 11.3. Giới hạn danh sách để tránh dùng quá nhiều bộ nhớ

Dù `COLLECT { ... }` trả đúng một cột, một node có hàng trăm nghìn quan hệ vẫn có thể tạo danh sách rất lớn. Đối với API hiển thị top N, hãy đưa `ORDER BY` và `LIMIT` vào bên trong biểu thức trước khi tạo danh sách.

Không nên mặc định coi `COLLECT` luôn nhanh hơn `collect()`. Chi phí thực tế phụ thuộc số hàng ngoài, mật độ quan hệ, điều kiện lọc, sắp xếp và phiên bản Neo4j. So sánh bằng `PROFILE` trên tập dữ liệu đại diện.

## 12. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân | Cách khắc phục |
|---|---|---|
| Cú pháp `COLLECT { ... }` không được nhận | Neo4j trước **5.6**, hoặc chế độ ngôn ngữ không hỗ trợ cú pháp dùng trong truy vấn. | Kiểm tra version thực tế; dùng `collect()`/`CALL` hoặc nâng cấp server. |
| `COUNT { ... }` với `UNION` lỗi trên bản 5.0–5.2 | Truy vấn đọc phức tạp trong `COUNT` chỉ được mở rộng từ **5.3**. | Dùng các dạng `COUNT` đơn giản phù hợp bản đang chạy hoặc chuyển sang aggregate/`CALL`. |
| `COLLECT` báo lỗi vì thiếu `RETURN` | `COLLECT` bắt buộc có `RETURN` cuối. | Trả đúng một biểu thức với alias rõ ràng. |
| `COLLECT` báo lỗi vì `RETURN a, b` | Truy vấn con trả hơn một cột. | Gói thành `RETURN {a: a, b: b} AS item`. |
| `COUNT` đếm 1 dù node không có quan hệ | `OPTIONAL MATCH` hoặc aggregate bên trong tạo một hàng, kể cả khi dữ liệu không khớp. | Đếm bằng `COUNT { MATCH ... }` trực tiếp. |
| Danh sách bị trùng tên | Nhiều đường/relationship tạo nhiều hàng dẫn đến cùng giá trị. | Dùng `RETURN DISTINCT ...` khi cần giá trị duy nhất. |
| `COUNT` trả 2 nhưng chỉ có 1 node đích | Hai đường khác nhau tới cùng node. | Định nghĩa rõ “số đường đi” hay “số node”; `RETURN DISTINCT d` nếu cần node duy nhất. |
| Lấy hai phần tử không ổn định | Có `LIMIT` mà không có `ORDER BY`. | Thêm `ORDER BY` trong truy vấn con trước `LIMIT`. |
| Không truy cập được `d` ở ngoài | `d` được tạo bên trong biểu thức truy vấn con. | Trả số/list; nếu cần xuất node theo hàng, dùng `MATCH` hoặc `CALL`. |
| Thêm `WITH` bên trong làm báo xung đột tên | Khai báo lại biến outer scope. | Đổi tên biến mới, tránh shadowing. |
| Nhiều `MATCH` khiến số đếm phình lên | Kết hợp các mẫu độc lập gây nhân hàng. | Tách mẫu thành các subquery expressions hoặc tổng hợp cẩn thận với `DISTINCT`. |

## 13. Bài tập luyện tập với đồ thị mẫu

**Bài 1.** Viết truy vấn tìm các dịch vụ có **ít nhất một dependency critical**. Kết quả mong đợi: **API** và **Billing**.

```cypher
MATCH (s:CountCollectDemoService)
WHERE COUNT {
  MATCH (s)-[r:DEPENDS_ON]->(:CountCollectDemoService)
  WHERE r.critical = true
} >= 1
RETURN s.name AS service
ORDER BY service;
```

**Bài 2.** Viết truy vấn lấy tên các dependency critical của API, có thứ tự tăng dần. Kết quả mong đợi: `["Auth", "Billing"]`.

```cypher
MATCH (s:CountCollectDemoService {id: 'api'})
RETURN COLLECT {
  MATCH (s)-[r:DEPENDS_ON]->(d:CountCollectDemoService)
  WHERE r.critical = true
  RETURN d.name AS dependency
  ORDER BY dependency
} AS criticalDependencies;
```

**Bài 3.** Tìm số **dịch vụ khác nhau** mà API có thể tác động tới qua đúng hai bước. Vì sao khác với số đường hai bước?

```cypher
MATCH (s:CountCollectDemoService {id: 'api'})
RETURN COUNT {
  MATCH (s)-[:DEPENDS_ON]->(:CountCollectDemoService)
        -[:DEPENDS_ON]->(d:CountCollectDemoService)
  RETURN DISTINCT d
} AS uniqueDestinations;
```

Đáp án: **1**, vì hai đường đều kết thúc ở Auth.

**Bài 4.** Viết lại truy vấn danh sách dependency của bài 2 cho Neo4j 4.4, nơi chưa có `COLLECT { ... }`.

```cypher
MATCH (s:CountCollectDemoService {id: 'api'})
CALL {
  WITH s
  OPTIONAL MATCH (s)-[r:DEPENDS_ON]->(d:CountCollectDemoService)
  WHERE r.critical = true
  WITH d ORDER BY d.name
  RETURN collect(d.name) AS criticalDependencies
}
RETURN criticalDependencies;
```

Kết quả vẫn là `["Auth", "Billing"]`. Dạng `CALL` cũ cần `WITH s` để import biến; với `COLLECT` mới thì không.

## 14. Tổng kết

- `COUNT { ... }` đếm **số hàng của truy vấn con**, không nhất thiết là số node duy nhất; `RETURN DISTINCT` thay đổi số hàng được đếm.
- `COLLECT { ... }` tạo **danh sách từ đúng một cột `RETURN`**; cần một map khi muốn gom nhiều trường, và `[]` khi `MATCH` không có hàng.
- Dùng `ORDER BY`, `LIMIT`, `DISTINCT` **bên trong** `COLLECT` để quyết định danh sách của từng node ngoài.
- Biến bên ngoài khả dụng trực tiếp trong hai expression; biến mới bên trong không thể xuất ra ngoài. Chúng khác `CALL` subquery ở cơ chế import biến và bản chất kết quả.
- Mốc tương thích cần nhớ: `COUNT` có trên dòng Neo4j 5; các khả năng truy vấn đọc phong phú hơn từ **5.3**; `COLLECT` xuất hiện từ **5.6**. Neo4j 4.4 và các bản trước mốc hỗ trợ cần `count()/collect()` hoặc `CALL`.
- Khi nâng cấp ứng dụng Java hoặc Spring Data Neo4j, luôn xác nhận **phiên bản server**, kiểm tra số hàng của truy vấn và đo hiệu năng trên dữ liệu thực tế.

## Tài liệu tham khảo

- [Neo4j Cypher Manual — COUNT subqueries](https://neo4j.com/docs/cypher-manual/current/subqueries/count/) — đếm hàng, lọc, `UNION`, biến ngoài và các giới hạn.
- [Neo4j Cypher Manual — COLLECT subqueries](https://neo4j.com/docs/cypher-manual/current/subqueries/collect/) — tạo danh sách, yêu cầu `RETURN` một cột, lọc và `UNION`.
- [Neo4j Cypher Manual — Aggregating functions](https://neo4j.com/docs/cypher-manual/current/functions/aggregating/) — `count()`, `collect()` và cách xử lý `null`.
- [Neo4j Cypher Manual — Additions and compatibility (Neo4j 5)](https://neo4j.com/docs/cypher-manual/5/deprecations-additions-removals-compatibility/) — các mốc bổ sung cú pháp.
- [Neo4j Cypher Manual — ORDER BY](https://neo4j.com/docs/cypher-manual/current/clauses/order-by/) — thứ tự kết quả và tương tác với tổng hợp.
- [Neo4j Cypher Manual — Execution plans](https://neo4j.com/docs/cypher-manual/current/planning-and-tuning/execution-plans/) — `EXPLAIN` và `PROFILE`.
