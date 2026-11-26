# Truy vấn con có tương quan và ảnh hưởng đến số lần thực thi

> **Chương:** Truy vấn con  
> **Hệ quản trị:** Neo4j, property graph và ngôn ngữ Cypher.  
> **Mục tiêu:** Hiểu *correlated subquery* (truy vấn con có tương quan), số hàng được chuyển vào `CALL`, cách truy vấn con làm thay đổi số hàng đầu ra, và cách giảm công việc lặp lại khi truy vấn quan hệ, đường đi hoặc cập nhật đồ thị.

## 1. Truy vấn con có tương quan là gì?

Trong cơ sở dữ liệu đồ thị Neo4j, các node được nối với nhau bằng relationship. Chẳng hạn một dịch vụ `API` có thể phụ thuộc các dịch vụ `Auth` và `Catalog`. Ta thường muốn xử lý **riêng từng dịch vụ**: liệt kê dependency, đếm số dependency hoặc ghi nhận trạng thái.

Một **truy vấn con có tương quan** (*correlated subquery*) là truy vấn con sử dụng một hay nhiều **biến từ truy vấn ngoài**. Truy vấn con có thể cho kết quả khác nhau khi giá trị biến ngoài thay đổi.

```cypher
MATCH (s:CorrDemoService)
CALL (s) {
  MATCH (s)-[:DEPENDS_ON]->(d:CorrDemoService)
  RETURN d.name AS dependency
}
RETURN s.name AS service, dependency;
```

Ở đây:

- `s` được tạo bởi `MATCH` ngoài và **được truyền vào** subquery qua `CALL (s)`.
- `d` là biến **nội bộ** của subquery, đại diện cho dependency của `s` hiện tại.
- Subquery tìm dependency gắn với **chính node `s` của hàng đầu vào**, không tìm một tập dependency chung cho toàn bộ bảng kết quả.
- Mỗi hàng do subquery `RETURN` sẽ được ghép với hàng tương ứng của truy vấn ngoài.

Đây là ngữ nghĩa *theo từng hàng đầu vào*, không có nghĩa ứng dụng Java gửi thêm một lệnh Cypher qua mạng cho từng hàng. Toàn bộ câu truy vấn vẫn là **một câu lệnh gửi tới Neo4j**; server tổ chức công việc trong execution plan.

## 2. Dữ liệu minh họa: đồ thị phụ thuộc dịch vụ

Xét năm node `:CorrDemoService` cùng bốn relationship `:DEPENDS_ON`:

```text
     (API) ───────────────> (Auth)
       │                      ^
       │                      │
       └──> (Catalog) ────────┤
                              │
            (Billing) ────────┘

     (Metrics)   [không có DEPENDS_ON đi ra]
```

| Dịch vụ | `id` | Số dependency đi ra |
|---|---|---:|
| API | `api` | 2 (Auth, Catalog) |
| Auth | `auth` | 0 |
| Billing | `billing` | 1 (Auth) |
| Catalog | `catalog` | 1 (Auth) |
| Metrics | `metrics` | 0 |

Tạo dữ liệu trên **database thực hành riêng**. Dùng `MERGE` để các lần chạy lại trên đồ thị mẫu sạch không cố ý tạo thêm node/relationship giống nhau:

```cypher
MERGE (api:CorrDemoService {id: 'api'})
  SET api.name = 'API'
MERGE (auth:CorrDemoService {id: 'auth'})
  SET auth.name = 'Auth'
MERGE (billing:CorrDemoService {id: 'billing'})
  SET billing.name = 'Billing'
MERGE (catalog:CorrDemoService {id: 'catalog'})
  SET catalog.name = 'Catalog'
MERGE (metrics:CorrDemoService {id: 'metrics'})
  SET metrics.name = 'Metrics'
WITH api, auth, billing, catalog
MERGE (api)-[:DEPENDS_ON]->(auth)
MERGE (api)-[:DEPENDS_ON]->(catalog)
MERGE (billing)-[:DEPENDS_ON]->(auth)
MERGE (catalog)-[:DEPENDS_ON]->(auth);
```

Các ví dụ sau giả định đồ thị thực hành chỉ có **năm node mang nhãn `CorrDemoService`** và các quan hệ trên. Dữ liệu thật có thêm quan hệ sẽ cho kết quả khác.

## 3. Quy tắc nền tảng: `CALL` được đánh giá theo từng hàng đầu vào

Theo ngữ nghĩa Neo4j Cypher, một `CALL` subquery chạy **một lần cho mỗi hàng đi vào**. Nếu truy vấn ngoài đưa vào ba hàng thì sẽ có ba lần đánh giá subquery, gắn với ba ngữ cảnh hàng đó.

Ví dụ không cần đồ thị:

```cypher
UNWIND [10, 20, 30] AS number
CALL (number) {
  RETURN number * 2 AS doubled
}
RETURN number, doubled
ORDER BY number;
```

| number | doubled |
|---:|---:|
| 10 | 20 |
| 20 | 40 |
| 30 | 60 |

Sơ đồ luồng dữ liệu:

```text
Truy vấn ngoài                  CALL (number)              Hàng sau CALL

number = 10  ────────────────>  RETURN 20  ────────────>  (10, 20)
number = 20  ────────────────>  RETURN 40  ────────────>  (20, 40)
number = 30  ────────────────>  RETURN 60  ────────────>  (30, 60)
```

Điểm quyết định **số ngữ cảnh được xử lý** là số hàng **đang có ngay trước `CALL`**. Không thể chỉ nhìn số node toàn đồ thị hoặc số hàng ở `RETURN` cuối để suy ra điều đó.

### 3.1. Không có hàng đầu vào thì sao?

```cypher
UNWIND [] AS number
CALL (number) {
  RETURN number * 2 AS doubled
}
RETURN number, doubled;
```

Không có hàng nào đi vào `CALL`, nên truy vấn không tạo hàng kết quả. Một `CALL` không tự sinh ra hàng ngoài đã mất.

Ngược lại, nếu một câu truy vấn **bắt đầu bằng `CALL ()`** mà trước đó không có `MATCH`/`UNWIND` lọc sạch dữ liệu, Cypher có ngữ cảnh khởi tạo để truy vấn có thể trả kết quả:

```cypher
CALL () {
  RETURN 42 AS answer
}
RETURN answer;
```

Kết quả là một hàng `answer = 42`.

### 3.2. Biến tương quan được lấy từ đúng hàng hiện tại

```cypher
UNWIND [1, 2, 3] AS n
WITH n, 10 AS factor
CALL (n, factor) {
  RETURN n * factor AS scaled
}
RETURN n, scaled
ORDER BY n;
```

Truy vấn con được phép sử dụng `n` và `factor` vì hai biến đó được import tường minh bằng `CALL (n, factor)`. Giá trị của chúng tương ứng với hàng hiện tại.

Nếu `factor` không được import, truy vấn con sẽ không nhìn thấy `factor` theo cơ chế scope clause hiện đại.

## 4. Không tương quan vẫn có thể được gọi theo từng hàng

Một nhầm lẫn phổ biến: **`CALL ()` không đồng nghĩa “chạy đúng một lần cho cả câu truy vấn”**. Nó chỉ nói rằng subquery **không import biến ngoài**.

```cypher
UNWIND ['A', 'B', 'C'] AS code
CALL () {
  RETURN 'ready' AS state
}
RETURN code, state
ORDER BY code;
```

| code | state |
|---|---|
| A | ready |
| B | ready |
| C | ready |

Dù nội dung `CALL ()` không phụ thuộc `code`, biểu thức `state` vẫn được ghép vào **từng hàng**. Theo ngữ nghĩa `CALL`, có ba ngữ cảnh đánh giá.

Cũng vậy, nếu subquery đọc một tổng số toàn đồ thị:

```cypher
MATCH (s:CorrDemoService)
CALL () {
  MATCH (other:CorrDemoService)
  RETURN count(other) AS totalServices
}
RETURN s.name AS service, totalServices
ORDER BY service;
```

Trên đồ thị mẫu, có **năm hàng**, mỗi hàng có `totalServices = 5`. Nội dung `CALL ()` không liên quan đến `s`, nhưng vẫn nằm ở vị trí theo từng hàng ngoài.

**Phân biệt hai khái niệm:**

| Khái niệm | Câu hỏi cần trả lời |
|---|---|
| Có tương quan (*correlated*)? | Truy vấn con có sử dụng giá trị biến của truy vấn ngoài không? |
| Có bao nhiêu hàng đầu vào? | Đến vị trí `CALL`, luồng truy vấn ngoài còn bao nhiêu hàng? |

Một truy vấn con **có tương quan** thường phải dùng giá trị khác nhau cho từng hàng. Một `CALL ()` **không tương quan** vẫn mang ngữ nghĩa gọi theo từng hàng. Trình tối ưu có thể tổ chức lại một số bước đọc khi hợp lệ; đừng tự suy diễn số lượt quét vật lý chỉ dựa vào dấu `()`.

## 5. Số hàng ra: returning subquery, unit subquery và `OPTIONAL CALL`

Để phân biệt “số lần đánh giá” và “số dòng kết quả”, ta xét **năm hàng đầu vào** là năm dịch vụ mẫu.

Giả sử `kᵢ` là số hàng mà một **returning subquery** tạo ra cho hàng đầu vào thứ `i`.

- `CALL` returning thông thường: số hàng sau `CALL` bằng tổng `k₁ + k₂ + ... + kₙ`.
- `OPTIONAL CALL` returning: nếu một hàng không có kết quả con, nó vẫn đóng góp **một hàng với giá trị trả về `null`**; tổng số hàng là tổng các `max(1, kᵢ)`.
- `CALL` **unit** không có `RETURN`: giữ số hàng ngoài bằng số hàng đầu vào, dù bên trong có thể cập nhật nhiều node/relationship.
- Returning subquery có một tổng hợp toàn cục như `RETURN count(d)` thường trả **một hàng chứa 0** khi không có `d`, do đó có thể giữ nguyên số hàng ngoài.

### 5.1. Returning subquery có thể loại hàng hoặc nhân hàng

```cypher
MATCH (s:CorrDemoService)
CALL (s) {
  MATCH (s)-[:DEPENDS_ON]->(d:CorrDemoService)
  RETURN d.name AS dependency
}
RETURN s.name AS service, dependency
ORDER BY service, dependency;
```

Kết quả:

| service | dependency |
|---|---|
| API | Auth |
| API | Catalog |
| Billing | Auth |
| Catalog | Auth |

Trước `CALL` có **5 hàng**; sau `CALL` còn **4 hàng**. Điều đó hoàn toàn không mâu thuẫn với ngữ nghĩa “một lần cho mỗi hàng”: API tạo **2 hàng**, Auth tạo **0**, Billing **1**, Catalog **1**, Metrics **0**.

Bảng đầy đủ:

| Hàng ngoài | Hàng do `MATCH` trong subquery trả về | Hàng sau `CALL` thường |
|---|---:|---:|
| API | 2 | 2 |
| Auth | 0 | 0 |
| Billing | 1 | 1 |
| Catalog | 1 | 1 |
| Metrics | 0 | 0 |
| **Tổng** | **4** | **4** |

Nếu chỉ nhìn `RETURN` cuối có 4 hàng rồi kết luận truy vấn con được đánh giá 4 lần là sai: đầu vào logic của `CALL` vẫn có 5 hàng.

### 5.2. `OPTIONAL CALL` giữ các hàng không khớp

Từ **Neo4j 5.24**, có `OPTIONAL CALL`:

```cypher
MATCH (s:CorrDemoService)
OPTIONAL CALL (s) {
  MATCH (s)-[:DEPENDS_ON]->(d:CorrDemoService)
  RETURN d.name AS dependency
}
RETURN s.name AS service, dependency
ORDER BY service, dependency;
```

Kết quả có **6 hàng**:

| service | dependency |
|---|---|
| API | Auth |
| API | Catalog |
| Auth | `null` |
| Billing | Auth |
| Catalog | Auth |
| Metrics | `null` |

`OPTIONAL CALL` giữ hàng ngoài của Auth và Metrics khi subquery trả 0 hàng. Nó **không ép mỗi dịch vụ chỉ còn một hàng**: API vẫn có hai dependency nên có hai hàng.

### 5.3. Tổng hợp bên trong có thể giữ một hàng cho mỗi dịch vụ

```cypher
MATCH (s:CorrDemoService)
CALL (s) {
  MATCH (s)-[:DEPENDS_ON]->(d:CorrDemoService)
  RETURN count(d) AS dependencyCount
}
RETURN s.name AS service, dependencyCount
ORDER BY service;
```

| service | dependencyCount |
|---|---:|
| API | 2 |
| Auth | 0 |
| Billing | 1 |
| Catalog | 1 |
| Metrics | 0 |

`RETURN count(d)` là một tổng hợp **không có khóa nhóm**, nên nó trả **một hàng** chứa `0` kể cả khi `MATCH` không tìm thấy dependency. Kết quả có 5 hàng.

Cần lưu ý sự khác nhau nếu thêm khóa nhóm:

```cypher
MATCH (s:CorrDemoService)
CALL (s) {
  MATCH (s)-[:DEPENDS_ON]->(d:CorrDemoService)
  RETURN d.name AS dependency, count(*) AS matches
}
RETURN s.name AS service, dependency, matches
ORDER BY service, dependency;
```

Vì đã nhóm theo `d.name`, trường hợp không có `d` sẽ **không có nhóm để trả về**. Auth và Metrics lại biến mất; API tiếp tục có hai hàng.

### 5.4. Unit subquery giữ số hàng dù có ghi đồ thị

Ví dụ minh họa **chỉ chạy trên database thực hành**:

```cypher
UNWIND [101, 102, 103] AS eventId
CALL (eventId) {
  MERGE (:CorrDemoEvent {id: eventId})
}
RETURN eventId
ORDER BY eventId;
```

Đây là **unit subquery** vì không có `RETURN` trong `CALL`. Có ba hàng đi vào và ba hàng đi ra; `MERGE` chạy với từng `eventId`.

Nếu dữ liệu đầu vào có giá trị lặp, như `[101, 101, 102]`, subquery vẫn **nhận ba hàng**. Với `MERGE` phù hợp có thể chỉ tạo hai node; với `CREATE` sẽ tạo ba node. **Số hàng**, **số lượt xử lý logic** và **số node được tạo** là ba đại lượng khác nhau.

## 6. Bốn cách làm thay đổi số hàng đi vào `CALL`

Giả sử cần tính dependencyCount của dịch vụ trong danh sách đầu vào. Vì mục tiêu là giảm công việc lặp, việc sắp xếp các clause **trước** subquery rất quan trọng.

### 6.1. `WHERE` trước `CALL`: lọc sớm

```cypher
MATCH (s:CorrDemoService)
WHERE s.id IN ['api', 'billing']
CALL (s) {
  MATCH (s)-[:DEPENDS_ON]->(d:CorrDemoService)
  RETURN count(d) AS dependencyCount
}
RETURN s.name AS service, dependencyCount
ORDER BY service;
```

Thay vì năm node đầu vào, chỉ **API** và **Billing** đi vào `CALL`.

Khi lọc bằng khóa định danh thường xuyên, index hoặc constraint thích hợp cho `s.id` có thể giúp Neo4j tìm hai node mà không cần quét toàn bộ nhãn.

### 6.2. `WITH DISTINCT` trước `CALL`: tránh lặp khi được phép

```cypher
UNWIND ['api', 'api', 'billing'] AS serviceId
MATCH (s:CorrDemoService {id: serviceId})
CALL (s) {
  MATCH (s)-[:DEPENDS_ON]->(d:CorrDemoService)
  RETURN count(d) AS dependencyCount
}
RETURN s.name AS service, dependencyCount;
```

Có **ba hàng đầu vào** dù chỉ có hai node dịch vụ khác nhau. API xuất hiện **hai lần** nên kết quả cũng có hai hàng API.

Nếu yêu cầu là **mỗi dịch vụ duy nhất một lần**, chuyển sang:

```cypher
UNWIND ['api', 'api', 'billing'] AS serviceId
MATCH (s:CorrDemoService {id: serviceId})
WITH DISTINCT s
CALL (s) {
  MATCH (s)-[:DEPENDS_ON]->(d:CorrDemoService)
  RETURN count(d) AS dependencyCount
}
RETURN s.name AS service, dependencyCount
ORDER BY service;
```

Lúc này còn **hai hàng** trước `CALL`. `DISTINCT` chỉ nên dùng khi việc bỏ hàng trùng **không làm sai nghiệp vụ**. Chẳng hạn tác vụ ghi một sự kiện cho **mỗi lần xuất hiện trong dữ liệu đầu vào** thì không thể tự ý gộp các hàng trùng.

### 6.3. `ORDER BY ... LIMIT` trước `CALL`: chọn nhóm đầu vào

```cypher
MATCH (s:CorrDemoService)
WITH s
ORDER BY s.name
LIMIT 2
CALL (s) {
  MATCH (s)-[:DEPENDS_ON]->(d:CorrDemoService)
  RETURN count(d) AS dependencyCount
}
RETURN s.name AS service, dependencyCount
ORDER BY service;
```

Chỉ hai dịch vụ theo tên đứng đầu là **API** và **Auth** được đưa tới `CALL`.

Nếu đặt `LIMIT 2` **sau** `CALL`, ý nghĩa chuyển thành giới hạn **số hàng kết quả cuối**, không còn là tuyên bố rằng “chỉ hai dịch vụ được lựa chọn để xử lý”. Ngoài ra, hệ thực thi dạng luồng có thể dừng sớm khi đã đủ kết quả cuối; vì vậy **không được suy diễn một con số chính xác về lượt thao tác vật lý** chỉ bằng cách đếm hàng cuối. Khi cần giới hạn rõ ràng đầu vào, đặt `LIMIT` **trước `CALL`**.

### 6.4. Tổng hợp trước `CALL`: chuyển nhiều hàng thành nhóm

Giả sử muốn một lần kiểm tra cho **mỗi số dependency**:

```cypher
MATCH (s:CorrDemoService)
WITH s, COUNT {
  (s)-[:DEPENDS_ON]->(:CorrDemoService)
} AS degree
WITH degree, count(*) AS servicesInGroup
CALL (degree) {
  RETURN CASE
    WHEN degree = 0 THEN 'none'
    WHEN degree = 1 THEN 'single'
    ELSE 'multiple'
  END AS category
}
RETURN degree, servicesInGroup, category
ORDER BY degree;
```

Các hàng được gộp theo `degree` trước `CALL`. Trên đồ thị mẫu có **3 nhóm**:

| degree | servicesInGroup | category |
|---:|---:|---|
| 0 | 2 | none |
| 1 | 2 | single |
| 2 | 1 | multiple |

Trong ví dụ này có thể dùng `CASE` ngay tại truy vấn ngoài mà không cần `CALL`; subquery chỉ giúp minh họa việc đổi **đơn vị xử lý từ node sang nhóm**.

## 7. `LIMIT` bên trong subquery giới hạn kết quả cho từng hàng

Một nhiệm vụ phổ biến trong graph: lấy **người liên kết đầu tiên** hoặc **hai dependency đầu tiên của mỗi dịch vụ**, thay vì lấy hai kết quả đầu tiên trên toàn hệ thống.

```cypher
MATCH (s:CorrDemoService)
CALL (s) {
  MATCH (s)-[:DEPENDS_ON]->(d:CorrDemoService)
  RETURN d.name AS dependency
  ORDER BY dependency
  LIMIT 1
}
RETURN s.name AS service, dependency
ORDER BY service;
```

Kết quả:

| service | dependency |
|---|---|
| API | Auth |
| Billing | Auth |
| Catalog | Auth |

`LIMIT 1` nằm **trong** `CALL` nên mỗi dịch vụ trả tối đa một dependency. Auth và Metrics vẫn bị loại vì không có dependency; `LIMIT` không tự sinh hàng `null`.

Trường hợp cần giữ đủ năm dịch vụ, một lựa chọn tương thích với các bản 5.x có scope clause là:

```cypher
MATCH (s:CorrDemoService)
CALL (s) {
  OPTIONAL MATCH (s)-[:DEPENDS_ON]->(d:CorrDemoService)
  RETURN d.name AS dependency
  ORDER BY dependency
  LIMIT 1
}
RETURN s.name AS service, dependency
ORDER BY service;
```

`OPTIONAL MATCH` tạo một hàng với `d = null` khi không có quan hệ; lúc đó `CALL` trả ra một hàng cho mỗi dịch vụ. Từ **Neo4j 5.24**, có thể dùng `OPTIONAL CALL` với `MATCH` thường để giữ hàng thiếu.

### So sánh vị trí `LIMIT`

| Vị trí | Giới hạn điều gì? |
|---|---|
| Trước `CALL`: `WITH s ORDER BY ... LIMIT 2` | Số hàng đầu vào subquery. |
| Trong `CALL`: `RETURN d ... LIMIT 2` | Số hàng con tối đa **cho mỗi hàng ngoài**. |
| Sau `CALL`: `RETURN ... LIMIT 2` | Số hàng được trả **cho toàn bộ câu truy vấn**. |

Với `LIMIT`, nên đi kèm `ORDER BY` tại đúng phạm vi để kết quả được xác định theo tiêu chí rõ ràng.

## 8. `EXISTS`, `COUNT`, `COLLECT` cũng có tương quan, nhưng trả biểu thức

Từ khóa `CALL` không phải nơi duy nhất có ngữ nghĩa tương quan trong Cypher.

Các *subquery expression* dưới đây có thể tham chiếu biến ngoài **trực tiếp**, không cần `CALL (s)`:

```cypher
MATCH (s:CorrDemoService)
RETURN s.name AS service,
       EXISTS {
         MATCH (s)-[:DEPENDS_ON]->(:CorrDemoService)
       } AS hasDependencies,
       COUNT {
         (s)-[:DEPENDS_ON]->(:CorrDemoService)
       } AS dependencyCount,
       COLLECT {
         MATCH (s)-[:DEPENDS_ON]->(d:CorrDemoService)
         RETURN d.name AS dependency
         ORDER BY dependency
       } AS dependencies
ORDER BY service;
```

Truy vấn này yêu cầu **Neo4j 5.6+** vì có `COLLECT { ... }`.

| service | hasDependencies | dependencyCount | dependencies |
|---|---|---:|---|
| API | `true` | 2 | `["Auth", "Catalog"]` |
| Auth | `false` | 0 | `[]` |
| Billing | `true` | 1 | `["Auth"]` |
| Catalog | `true` | 1 | `["Auth"]` |
| Metrics | `false` | 0 | `[]` |

Chú ý sự khác nhau:

| Dạng | Giá trị trả về | Biến từ ngoài | Ảnh hưởng số hàng ngoài |
|---|---|---|---|
| `CALL (s) { ... RETURN ... }` | 0, 1 hoặc nhiều hàng con | Import tường minh | Có thể nhân/loại hàng |
| `CALL (s) { ... }` không `RETURN` | Không trả cột con | Import tường minh | Giữ nguyên hàng ngoài |
| `EXISTS { ... }` | Boolean | Tự động nhìn thấy trong scope | Bản thân biểu thức không nhân hàng |
| `COUNT { ... }` | Số nguyên | Tự động nhìn thấy trong scope | Bản thân biểu thức không nhân hàng |
| `COLLECT { ... RETURN ... }` | Danh sách | Tự động nhìn thấy trong scope | Bản thân biểu thức không nhân hàng |

Các biểu thức trên **được hiểu theo ngữ cảnh từng hàng `s`**, nhưng điều đó không có nghĩa mọi lần đánh giá đều tương ứng với một lệnh truy vấn con vật lý độc lập trên server. Neo4j có thể tối ưu các bước đọc hoặc dừng tìm sớm, đặc biệt với `EXISTS`. Hãy dùng `PROFILE` để biết tổng công việc trên phiên bản và dữ liệu thực tế.

### Vì sao `COUNT { ... }` đôi lúc cho 1 dù không có quan hệ?

`COUNT { ... }` đếm **hàng của truy vấn bên trong**, không đếm số giá trị khác `null`. Ví dụ:

```cypher
MATCH (s:CorrDemoService {id: 'metrics'})
RETURN COUNT {
  OPTIONAL MATCH (s)-[:DEPENDS_ON]->(d:CorrDemoService)
  RETURN d
} AS numberOfRows;
```

Kết quả là **1** vì `OPTIONAL MATCH` tạo một hàng có `d = null`. Đếm đúng dependency thì dùng `COUNT { MATCH ... }`, nhận **0**.

Tương tự, `COUNT { MATCH ... RETURN count(d) }` có thể cho **1** khi subquery tổng hợp tạo một hàng `0`. Đây là ví dụ rõ nhất cho việc **số hàng** khác **giá trị dữ liệu trong hàng**.

## 9. Phiên bản Neo4j quyết định cách truyền biến

### 9.1. Scope clause hiện đại từ Neo4j 5.23

Từ **Neo4j 5.23**, có thể khai báo biến import ngay sau `CALL`:

```cypher
MATCH (s:CorrDemoService)
CALL (s) {
  MATCH (s)-[:DEPENDS_ON]->(d:CorrDemoService)
  RETURN count(d) AS degree
}
RETURN s.name, degree;
```

Các dạng import:

| Dạng | Biến ngoài có thể tham chiếu trong subquery |
|---|---|
| `CALL (s) { ... }` | Chỉ `s` |
| `CALL (s, threshold) { ... }` | `s` và `threshold` |
| `CALL (*) { ... }` | Tất cả biến đang có ở outer scope |
| `CALL () { ... }` | Không import biến ngoài |

Sử dụng `CALL (s)` thay vì `CALL (*)` thường làm rõ phụ thuộc của truy vấn con. Với scope clause, biến import vẫn có thể được sử dụng bên trong subquery kể cả sau một `WITH` không liệt kê lại biến đó.

### 9.2. Cú pháp cũ cho Neo4j 4.4–5.22

Các máy chủ trước 5.23 không hiểu `CALL (s)`. Dùng *importing WITH*:

```cypher
MATCH (s:CorrDemoService)
CALL {
  WITH s
  MATCH (s)-[:DEPENDS_ON]->(d:CorrDemoService)
  RETURN count(d) AS degree
}
RETURN s.name AS service, degree
ORDER BY service;
```

Ở cú pháp cũ, `WITH s` mở đầu truy vấn con có mục đích import biến. Không gắn `WHERE`, `ORDER BY`, `LIMIT` hoặc alias trực tiếp vào importing `WITH`. Nếu cần lọc ngay sau khi import, dùng hai `WITH`:

```cypher
MATCH (s:CorrDemoService)
CALL {
  WITH s
  WITH s
  WHERE s.id <> 'metrics'
  MATCH (s)-[:DEPENDS_ON]->(d:CorrDemoService)
  RETURN count(d) AS degree
}
RETURN s.name AS service, degree
ORDER BY service;
```

Truy vấn trên không còn là ví dụ tốt để **lọc hàng ngoài**: do `RETURN count(d)` tổng hợp không có khóa nhóm, các trường hợp không khớp vẫn có thể trả một hàng đếm 0. Muốn loại Metrics một cách rõ ràng và giảm số hàng đi vào subquery, hãy đặt `WHERE s.id <> 'metrics'` **trước `CALL`** ở truy vấn ngoài.

Nếu dùng `WITH` thông thường trong subquery cũ và bỏ biến `s` khỏi scope, những clause sau sẽ không còn tham chiếu được `s`. Với scope clause mới, biến đã import có phạm vi xuyên suốt subquery.

### 9.3. Máy chủ, phiên bản ngôn ngữ và Java Driver

| Môi trường | Quy tắc thực hành |
|---|---|
| Neo4j 4.4 và 5.0–5.22 | Dùng `CALL { WITH s ... }`. |
| Neo4j 5.23 trở lên | Ưu tiên `CALL (s) { ... }`; importing `WITH` được khuyến nghị thay thế. |
| Neo4j 5.24 trở lên | Có thêm `OPTIONAL CALL` để giữ hàng không khớp. |
| Neo4j 2025.06 trở lên | Có thể có lựa chọn **Cypher 5** hoặc **Cypher 25**; phân biệt phiên bản **ngôn ngữ** với phiên bản **máy chủ**. |

Nâng cấp Java Driver hoặc Spring Data Neo4j **không tự bổ sung cú pháp subquery cho Neo4j server cũ**. Cần xác định version của database mà ứng dụng thực sự kết nối trước khi chọn cú pháp.

## 10. Tương quan, thứ tự thực thi và cập nhật dữ liệu

Neo4j cho phép `CALL` subquery ghi dữ liệu bằng `CREATE`, `MERGE`, `SET`, `DELETE`. Khi có nhiều hàng đầu vào, các lần thực thi trong cùng câu truy vấn có thể **quan sát thay đổi của lần trước**.

Ví dụ trong database thực hành:

```cypher
UNWIND [1, 2, 3] AS seq
WITH seq
ORDER BY seq
CALL (seq) {
  CREATE (:CorrDemoLog {sequence: seq})
}
RETURN count(*) AS submittedRows;
```

Có ba hàng được gửi vào `CALL`; câu truy vấn tạo ba node log và `submittedRows = 3`. `ORDER BY` trước `CALL` làm rõ thứ tự hàng được chuyển vào nếu logic ghi có phụ thuộc thứ tự.

**Lưu ý:** nếu nhiều đầu vào cập nhật **cùng một node**, không nên dựa vào “thứ tự tình cờ” của `MATCH`. Neo4j không bảo đảm thứ tự đưa hàng ngoài vào subquery khi không có `ORDER BY` thích hợp **trước `CALL`**. Với xử lý song song hoặc giao dịch concurrent, cần thêm phân tích về khả năng nhìn thấy thay đổi và tính độc lập của các lô.

Cũng cần phân biệt **một câu lệnh** với **từng thao tác ghi**. Từ ứng dụng Java, một lệnh `session.run(query, params)` có thể khiến Neo4j thực hiện nhiều lượt ghi do các hàng trong `UNWIND`, nhưng không tạo từng round-trip mạng cho mỗi hàng.

## 11. `IN TRANSACTIONS`: số lần gọi khác số lần commit

Với khối lượng lớn, `CALL ... IN TRANSACTIONS` xử lý các hàng ngoài theo **lô** để commit từng inner transaction.

```cypher
UNWIND range(1, 5) AS id
CALL (id) {
  MERGE (:CorrDemoBatchItem {id: id})
} IN TRANSACTIONS OF 2 ROWS
RETURN count(*) AS submittedRows;
```

Khi thực thi trên Neo4j hỗ trợ `CALL (id)` (5.23+), có:

- **5 hàng đầu vào** với `id = 1, 2, 3, 4, 5`.
- **5 lần xử lý logic** của unit subquery theo các hàng.
- **3 lô inner transaction**: lô đầu 2 hàng, lô thứ hai 2 hàng, lô cuối 1 hàng.
- `submittedRows = 5` trong kết quả tổng hợp.

**Không được hiểu `OF 2 ROWS` là “chỉ chạy truy vấn con hai lần”.** Tham số này quy định số **hàng đầu vào trong mỗi lô commit**.

Chỉ áp dụng `CALL { ... } IN TRANSACTIONS` trong **implicit transaction**. Trong Neo4j Browser, dùng `:auto` nếu cần; với Java Driver, dùng hình thức implicit transaction (ví dụ `session.run(...)` và tiêu thụ kết quả), không bọc trong `session.executeWrite(...)`.

Các lô trước đã commit có thể vẫn tồn tại khi lô sau lỗi; thiết kế thao tác ghi có thể chạy lại an toàn và đặt index/constraint phù hợp cho `MERGE`. Neo4j đời mới còn hỗ trợ các tùy chọn concurrent transaction; chúng làm thay đổi giả định về thứ tự và khả năng quan sát thay đổi giữa lô, vì vậy chỉ dùng khi dữ liệu và thao tác độc lập.

### Vì sao phải tạo hàng **trước** subquery?

Nếu muốn cập nhật 5.000 node theo các lô 1.000 hàng, trước hết `MATCH`/`UNWIND` hoặc `LOAD CSV` phải tạo 5.000 **hàng đầu vào** rồi mới `CALL ... IN TRANSACTIONS OF 1000 ROWS`.

Nếu toàn bộ việc tìm 5.000 node được đặt **bên trong** một `CALL () { ... }` và truy vấn ngoài chỉ có một hàng, phần `IN TRANSACTIONS` chỉ nhìn thấy **một hàng đầu vào**, nên không thể tự chia 5.000 node thành năm lô theo cách mong muốn.

## 12. Ước lượng chi phí và xác minh với `EXPLAIN`, `PROFILE`

### 12.1. Công thức tư duy để nhận ra công việc lặp

Giả sử:

- `N`: số hàng đi vào `CALL`.
- `kᵢ`: số hàng returning subquery trả về cho hàng thứ `i`.
- `cᵢ`: chi phí xử lý mẫu/đường đi/ghi dữ liệu cho hàng thứ `i`.

Về mặt ngữ nghĩa, returning `CALL` tạo **tổng `kᵢ` hàng**; tổng công việc thường phụ thuộc **tổng `cᵢ`**. Số hàng kết quả `kᵢ` chỉ là một chỉ báo, **không phải thước đo trực tiếp thời gian xử lý**.

Ví dụ, 100 dịch vụ cùng có 20 dependency có thể tạo khoảng 2.000 hàng với `MATCH` trong `CALL`. Nếu chỉ cần cờ “có dependency”, dùng `EXISTS` có thể tránh tạo ra toàn bộ danh sách kết quả. Nếu chỉ cần số lượng, dùng `COUNT { ... }` hoặc một tổng hợp hợp lý.

Một subquery có tương quan với cùng khóa mà bị lặp trên nhiều hàng có thể tạo nhiều công việc giống nhau. Tuy nhiên, không nên suy ra rằng mỗi lần tương quan tạo một *network query* riêng: server vẫn thực thi cùng một câu Cypher mà client gửi đi.

### 12.2. Dùng `EXPLAIN` để xem kế hoạch

```cypher
EXPLAIN
MATCH (s:CorrDemoService)
CALL (s) {
  MATCH (s)-[:DEPENDS_ON]->(d:CorrDemoService)
  RETURN d.name AS dependency
}
RETURN s.name AS service, dependency;
```

`EXPLAIN` cho biết Neo4j dự kiến chạy những operator nào nhưng **không thực thi truy vấn**.

Có thể gặp operator liên quan đến việc áp dụng subquery theo hàng (*Apply* hoặc biến thể khác), đọc node, mở rộng relationship và chiếu cột. Tên operator tùy phiên bản, runtime và cấu trúc truy vấn.

### 12.3. Dùng `PROFILE` để đo trên dữ liệu thực

```cypher
PROFILE
MATCH (s:CorrDemoService)
CALL (s) {
  MATCH (s)-[:DEPENDS_ON]->(d:CorrDemoService)
  RETURN count(d) AS degree
}
RETURN s.name AS service, degree
ORDER BY service;
```

`PROFILE` **thực thi** truy vấn và hiển thị số liệu tại các operator, chẳng hạn:

- **Rows:** số hàng từng operator thực sự sản xuất (thường là tổng trong suốt lần chạy).
- **DB Hits:** các lượt truy cập dữ liệu mà operator thực hiện.
- **Estimated Rows:** dự đoán cardinality để so với thực tế.
- Thời gian/bộ nhớ hoặc thông tin khác nếu runtime và công cụ hiển thị hỗ trợ.

Quan sát số hàng **đi vào** operator áp dụng truy vấn con, số hàng **đi ra**, và những lần mở rộng relationship tốn chi phí. Dựa trên kế hoạch thực tế để xác định có quá nhiều đầu vào trùng, mẫu con duyệt rộng hoặc sắp xếp danh sách lớn.

Không nên khẳng định “operator X chạy chính xác N lần” chỉ từ một con số `Rows`: kế hoạch có thể gộp, đẩy điều kiện, chạy theo pipeline hoặc dừng sớm trong trường hợp cho phép. Mục tiêu là xác định **cardinality và chi phí** có phù hợp với kỳ vọng hay không.

### 12.4. Index giúp gì trong subquery có tương quan?

Nếu mỗi hàng trong subquery phải tìm dịch vụ theo một mã khác, index/constraint trên thuộc tính đó có thể giảm chi phí của từng lượt tra cứu.

Ví dụ tạo uniqueness constraint **trong database thực hành**:

```cypher
CREATE CONSTRAINT corr_demo_service_id IF NOT EXISTS
FOR (s:CorrDemoService)
REQUIRE s.id IS UNIQUE;
```

Từ đó, truy vấn tìm dịch vụ bằng `id` có cơ hội dùng index được constraint hỗ trợ. Nếu đã giữ **node `s`** từ truy vấn ngoài và chỉ mở rộng `(s)-[:DEPENDS_ON]->(...)`, không cần tìm lại `s` bằng tên/ID bên trong mỗi subquery.

## 13. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Hướng xử lý |
|---|---|---|
| `CALL` trả 4 hàng dù có 5 dịch vụ | Returning subquery trả 0 hàng cho Auth và Metrics, API trả 2 hàng. | Phân biệt hàng đầu vào và đầu ra; dùng tổng hợp, `OPTIONAL MATCH` hoặc `OPTIONAL CALL` nếu cần giữ dịch vụ không khớp. |
| `CALL ()` vẫn tạo kết quả lặp cho mỗi dịch vụ | Không import biến chỉ có nghĩa **không tương quan**, không có nghĩa chạy một lần toàn cục. | Nếu cần một tổng toàn cục, tính trước rồi ghép theo yêu cầu, hoặc viết lại truy vấn phù hợp. |
| Truy vấn con đọc/ghi lại cùng dịch vụ nhiều lần | Hàng ngoài trùng do `UNWIND` hoặc nhiều `MATCH`. | Xem số hàng trước `CALL`; dùng `WITH DISTINCT` khi nghiệp vụ cho phép. |
| `LIMIT 1` ngoài cùng chỉ trả một dòng toàn bộ | `LIMIT` có phạm vi ở câu truy vấn ngoài. | Đưa `LIMIT` vào subquery để lấy một kết quả **mỗi hàng**; đưa lên trước `CALL` để chỉ xử lý một hàng đầu vào. |
| `count(*)` bên ngoài khiến “mất” số hàng khác biệt | Aggregate ngoài biến nhiều hàng thành một hàng tổng hợp. | Kiểm tra điểm nhóm và giá trị đếm; đo cardinality trung gian. |
| `COUNT { OPTIONAL MATCH ... }` trả 1 với dịch vụ không có quan hệ | `OPTIONAL MATCH` tạo một hàng chứa `null`. | Dùng `COUNT { MATCH ... }` khi đếm kết quả khớp thực. |
| Báo lỗi biến không tồn tại bên trong `CALL` | Chưa import biến ngoài. | Neo4j 5.23+: `CALL (s)`; bản cũ: `CALL { WITH s ... }`. |
| Dùng `CALL (s)` nhưng server báo lỗi cú pháp | Neo4j server cũ hơn 5.23. | Dùng importing `WITH` hoặc nâng cấp server. |
| Cập nhật dữ liệu dựa vào thứ tự ngẫu nhiên | Không có `ORDER BY` trước `CALL`. | Định thứ tự rõ ràng khi thật sự cần xử lý có thứ tự; cân nhắc xung đột khi chạy concurrent. |
| `IN TRANSACTIONS OF 1000 ROWS` vẫn tạo một lô | Subquery chỉ nhận một hàng ngoài; `MATCH` hoặc `UNWIND` lớn nằm bên trong. | Tạo các hàng đầu vào từ `MATCH`/`UNWIND`/`LOAD CSV` **trước `CALL`**. |
| Nhìn 5 dòng kết quả và kết luận 5 lượt truy cập DB | Số dòng không phản ánh toàn bộ lượt duyệt hoặc tối ưu vật lý. | Dùng `PROFILE`; đọc `Rows`, `DB Hits` và kế hoạch thực tế. |

## 14. Bài tập tự kiểm tra

Các câu dưới đây dùng đồ thị ở mục 2. Trước khi chạy, hãy thử dự đoán **số hàng đi vào `CALL`** và **số hàng cuối**.

**Bài 1.** Có bao nhiêu hàng đầu vào và kết quả?

```cypher
UNWIND ['api', 'api', 'billing', 'metrics'] AS id
MATCH (s:CorrDemoService {id: id})
CALL (s) {
  MATCH (s)-[:DEPENDS_ON]->(d:CorrDemoService)
  RETURN d.name AS dependency
}
RETURN s.name AS service, dependency;
```

**Đáp án:** 4 hàng ngoài đi vào `CALL`; số hàng cuối là **5**:

- API xuất hiện hai lần, mỗi lần cho 2 dependency: `2 × 2 = 4` hàng.
- Billing cho 1 hàng.
- Metrics cho 0 hàng.

**Bài 2.** Thay `CALL` bằng `OPTIONAL CALL` trên bản 5.24+, số hàng cuối là bao nhiêu?

**Đáp án:** **6** hàng: 4 từ hai lần API, 1 từ Billing, 1 từ Metrics với `dependency = null`.

**Bài 3.** Nếu đặt `WITH DISTINCT s` trước `CALL` ở bài 1, có bao nhiêu hàng đi vào và đi ra?

**Đáp án:** Có **3 hàng** đi vào (API, Billing, Metrics) và **3 hàng** đi ra (2 của API, 1 của Billing).

**Bài 4.** Tìm một kết quả cuối cho mỗi dịch vụ, kể cả dịch vụ có 0 dependency, mà không cần `OPTIONAL CALL`.

```cypher
MATCH (s:CorrDemoService)
CALL (s) {
  MATCH (s)-[:DEPENDS_ON]->(d:CorrDemoService)
  RETURN count(d) AS dependencyCount
}
RETURN s.name AS service, dependencyCount
ORDER BY service;
```

**Đáp án:** 5 hàng, lần lượt có số đếm `API = 2`, `Auth = 0`, `Billing = 1`, `Catalog = 1`, `Metrics = 0`.

**Bài 5.** Có 2.501 hàng ngoài, xử lý `IN TRANSACTIONS OF 1000 ROWS` ở chế độ mặc định xử lý tuần tự, tối đa có bao nhiêu lô khi không lỗi?

**Đáp án:** **3 lô** (1.000, 1.000, 501). Số hàng cần xử lý logic vẫn là **2.501**.

## 15. Ghi nhớ để viết truy vấn thực tế

1. **Xác định hàng đầu vào ngay trước `CALL`.** Biến tương quan được lấy theo hàng hiện tại; số node toàn graph không luôn bằng số lần xử lý logic.
2. **Không tương quan không có nghĩa chỉ chạy một lần.** `CALL ()` không import biến nhưng vẫn theo ngữ nghĩa áp dụng cho hàng ngoài.
3. **Phân biệt số hàng và giá trị trong hàng.** Returning subquery có thể tạo 0/nhiều hàng; `OPTIONAL CALL` giữ hàng trống; tổng hợp không khóa nhóm có thể trả một hàng chứa `0`.
4. **Giảm hàng trước subquery nếu nghiệp vụ cho phép.** `WHERE`, `DISTINCT`, `LIMIT` và tổng hợp đặt đúng chỗ giúp giảm các ngữ cảnh phải xử lý.
5. **Đặt `ORDER BY`/`LIMIT` theo đúng phạm vi.** Bên trong giới hạn từng hàng; trước `CALL` giới hạn đầu vào; sau `CALL` giới hạn tổng đầu ra.
6. **Dùng `EXISTS`/`COUNT`/`COLLECT` khi chỉ cần một biểu thức.** Chúng có cơ chế scope riêng và không làm nhân hàng như returning `CALL`.
7. **Đo bằng kế hoạch thực tế.** `PROFILE` cho biết số hàng và chi phí trên server, trong khi “số lần thực thi” suy ra từ cú pháp chỉ mô tả ngữ nghĩa.

## Tài liệu tham khảo

- [Neo4j Cypher Manual — CALL subqueries](https://neo4j.com/docs/cypher-manual/current/subqueries/call-subquery/) — ngữ nghĩa theo hàng, import biến, kết quả của returning/unit subquery và quản lý bộ nhớ.
- [Neo4j Cypher Manual — EXISTS subqueries](https://neo4j.com/docs/cypher-manual/current/subqueries/existential/) — truy vấn con Boolean có tương quan.
- [Neo4j Cypher Manual — COUNT subqueries](https://neo4j.com/docs/cypher-manual/current/subqueries/count/) — đếm hàng của truy vấn con theo biến ngoài.
- [Neo4j Cypher Manual — COLLECT subqueries](https://neo4j.com/docs/cypher-manual/current/subqueries/collect/) — gom giá trị theo từng hàng ngoài thành danh sách.
- [Neo4j Cypher Manual — CALL subqueries in transactions](https://neo4j.com/docs/cypher-manual/current/subqueries/subqueries-in-transactions/) — xử lý input rows theo lô và quy tắc implicit transaction.
- [Neo4j Cypher Manual — Execution plans](https://neo4j.com/docs/cypher-manual/current/planning-and-tuning/execution-plans/) — đọc `EXPLAIN` và `PROFILE` để xác minh cardinality, chi phí thực thi.
