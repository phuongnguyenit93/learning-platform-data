# Phát hiện dữ liệu vi phạm trước khi áp dụng ràng buộc trong Neo4j

Trong Neo4j, **constraint** (ràng buộc dữ liệu) bảo vệ tính nhất quán của property graph: mã khách hàng không bị trùng, thuộc tính bắt buộc luôn có, cặp khóa nghiệp vụ xác định duy nhất một node, hoặc thuộc tính phải mang đúng kiểu. Tuy nhiên, khi thêm constraint vào cơ sở dữ liệu **đã có dữ liệu**, Neo4j phải kiểm tra những node/relationship thuộc phạm vi áp dụng. Nếu tìm thấy bản ghi vi phạm, thao tác tạo constraint sẽ thất bại; Neo4j không tự sửa hay bỏ qua dữ liệu sai.

Bài học trong chương **Ràng buộc dữ liệu** tập trung vào cách **kiểm kê, phát hiện, diễn giải và xử lý vi phạm trước khi chạy `CREATE CONSTRAINT`** bằng Cypher. Đây là bước quan trọng khi nhập dữ liệu, di chuyển lược đồ, dùng Neo4j Java Driver hoặc Spring Data Neo4j, và trước khi đưa một hệ thống đồ thị vào vận hành.

> **Nguyên tắc:** xác định chính xác quy tắc muốn áp dụng → truy vấn tìm dữ liệu vi phạm → quyết định cách sửa theo nghiệp vụ → kiểm tra lại → tạo constraint → xác minh và giám sát các lần ghi sau đó. Tránh tạo constraint rồi mới tìm cách sửa theo thông báo lỗi đầu tiên.

## 1. Biết constraint nào sẽ kiểm tra điều gì

Mỗi loại constraint phát hiện một dạng dữ liệu sai khác nhau. Trước khi audit, cần chốt **label/relationship type**, **thuộc tính**, **đơn vị được coi là duy nhất** và **quy tắc về giá trị thiếu**.

| Loại ràng buộc | Điều kiện dữ liệu cần thỏa | Dạng vi phạm cần tìm trước |
| --- | --- | --- |
| Property uniqueness trên node | Các node cùng label không được có **giá trị thuộc tính trùng nhau** khi thuộc tính hiện diện | Nhiều node có cùng giá trị khóa |
| Composite uniqueness trên node | Không có hai node cùng label có **cùng bộ giá trị** của các thuộc tính tham gia, khi toàn bộ bộ giá trị hiện diện | Trùng cặp/bộ khóa, ví dụ `(tenantId, orderCode)` |
| Property existence trên node | Mỗi node thuộc label phải có thuộc tính bắt buộc | Thuộc tính thiếu hoặc là `null` |
| Node key | Kết hợp **tồn tại đầy đủ** và **duy nhất** cho khóa đơn hoặc khóa tổ hợp | Vừa cần tìm bản ghi thiếu khóa, vừa cần tìm nhóm khóa trùng |
| Property uniqueness/existence/key trên relationship | Kiểm tra giá trị thuộc tính của mọi relationship cùng type (tùy loại constraint và khả năng hỗ trợ) | Quan hệ thiếu mã hoặc dùng trùng mã |
| Property type constraint | Giá trị hiện diện phải thuộc kiểu khai báo, ví dụ `INTEGER` | Giá trị lưu sai kiểu như tuổi là chuỗi |

**Điểm dễ nhầm:** property uniqueness **không** đồng nghĩa với property existence. Nhiều node thiếu `email` vẫn có thể không vi phạm uniqueness. Tương tự, composite uniqueness không tự yêu cầu từng thành phần của khóa đều tồn tại. Nếu cần cả hai điều kiện, dùng node key khi phiên bản/edition hỗ trợ, hoặc phối hợp các constraint tương ứng.

Các ví dụ DDL phía dưới theo cú pháp Neo4j 5.x. Một số loại constraint, đặc biệt **existence**, **key** và **property type**, phụ thuộc phiên bản cũng như edition (thường cần Enterprise). Kiểm tra khả năng hỗ trợ trên môi trường đích trước khi triển khai; `property type constraint` là tính năng của dòng Neo4j 5 từ 5.9.

## 2. Chuẩn bị bộ dữ liệu audit có lỗi chủ đích

Chạy đoạn tạo dữ liệu sau **một lần duy nhất trên database thử nghiệm**. Các label `AuditCustomer`, `AuditOrder` và type `AUDIT_PLACED` giúp tách biệt ví dụ với dữ liệu ứng dụng. Nếu chạy `CREATE` nhiều lần, số hàng và số lỗi dự kiến sẽ thay đổi.

```cypher
CREATE
  (c1:AuditCustomer {sourceId: 'C1', email: 'an@example.com', age: 29}),
  (c2:AuditCustomer {sourceId: 'C2', email: 'an@example.com', age: 31}),
  (c3:AuditCustomer {sourceId: 'C3', age: 22}),
  (c4:AuditCustomer {sourceId: 'C4', email: ' AN@Example.com ', age: '25'}),
  (c5:AuditCustomer {sourceId: 'C5', email: 'binh@example.com', age: 40}),
  (o1:AuditOrder {sourceId: 'O1', tenantId: 'T1', orderCode: '001'}),
  (o2:AuditOrder {sourceId: 'O2', tenantId: 'T1', orderCode: '001'}),
  (o3:AuditOrder {sourceId: 'O3', tenantId: 'T2', orderCode: '001'}),
  (o4:AuditOrder {sourceId: 'O4', tenantId: 'T1'}),
  (c1)-[:AUDIT_PLACED {sourceId: 'R1', eventId: 'E1'}]->(o1),
  (c2)-[:AUDIT_PLACED {sourceId: 'R2', eventId: 'E1'}]->(o2),
  (c3)-[:AUDIT_PLACED {sourceId: 'R3'}]->(o3);
```

Dữ liệu cố ý chứa các tình huống sau:

- **C1/C2** có `email` trùng chính xác; **C4** có email cùng ý nghĩa nếu nghiệp vụ bỏ qua hoa/thường và khoảng trắng; **C3** thiếu email.
- **C4** có `age` dạng chuỗi `'25'`, dù quy tắc dự kiến yêu cầu số nguyên.
- **O1/O2** trùng khóa `(T1, 001)`; **O3** có cùng `orderCode` nhưng ở tenant khác nên **không** trùng khóa tổ hợp; **O4** thiếu `orderCode`.
- **R1/R2** có `eventId = 'E1'`; **R3** thiếu `eventId`.

Mỗi bản ghi có `sourceId` để thuận tiện truy vết về dữ liệu nhập. Trong ứng dụng thực, nên dựa vào **mã nghiệp vụ ổn định** như vậy khi bàn cách sửa. `elementId()` hữu ích để tìm node/relationship trong phiên làm việc nhưng không nên lưu lâu dài như định danh nghiệp vụ, đặc biệt qua lần nhập lại, xóa hoặc tái tạo dữ liệu.

## 3. Phát hiện trùng giá trị trước uniqueness constraint

### 3.1. Kiểm tra trùng chính xác

Giả sử muốn đặt uniqueness cho `AuditCustomer.email`. Dùng `GROUP BY` theo cách Cypher: đưa biểu thức khóa và các hàm tổng hợp vào `WITH`, sau đó lọc nhóm có nhiều hơn một hàng.

```cypher
MATCH (c:AuditCustomer)
WHERE c.email IS NOT NULL
WITH c.email AS email,
     count(*) AS occurrences,
     collect(c.sourceId) AS records
WHERE occurrences > 1
RETURN email, occurrences, records
ORDER BY occurrences DESC, email;
```

Kết quả dự kiến:

| email | occurrences | records |
| --- | ---: | --- |
| `an@example.com` | 2 | `['C1', 'C2']` |

Bộ lọc `WHERE c.email IS NOT NULL` khớp với hành vi uniqueness: thiếu thuộc tính không tạo một giá trị khóa để so trùng. Nếu chỉ quan tâm xem **có vi phạm hay không** trên tập dữ liệu lớn, không cần `collect()` tất cả mã bản ghi:

```cypher
MATCH (c:AuditCustomer)
WHERE c.email IS NOT NULL
WITH c.email AS email, count(*) AS occurrences
WHERE occurrences > 1
RETURN count(*) AS duplicateGroups,
       coalesce(sum(occurrences - 1), 0) AS excessRecords;
```

Với dữ liệu mẫu, `duplicateGroups = 1` và `excessRecords = 1`. `excessRecords` là số bản ghi vượt quá một bản ghi được giữ trên mỗi nhóm, **không** tự quyết định bản ghi nào cần xóa.

### 3.2. Phân biệt trùng kỹ thuật với trùng theo nghiệp vụ

Neo4j so sánh giá trị thuộc tính theo kiểu và giá trị lưu trong database. Vì thế `'an@example.com'` và `' AN@Example.com '` là hai chuỗi khác nhau; uniqueness trên `email` **không** xem chúng là trùng.

Nếu sản phẩm quy định email phải được so sau khi bỏ khoảng trắng ngoài và không phân biệt hoa/thường, audit bằng khóa chuẩn hóa:

```cypher
MATCH (c:AuditCustomer)
WHERE c.email IS NOT NULL
WITH toLower(trim(c.email)) AS normalizedEmail,
     count(*) AS occurrences,
     collect(c.sourceId) AS records
WHERE occurrences > 1
RETURN normalizedEmail, occurrences, records;
```

Kết quả có một nhóm `an@example.com` gồm **3 bản ghi C1, C2, C4**. Đây là **kiểm tra theo quy tắc nghiệp vụ**, không phải chính xác tập vi phạm của uniqueness constraint trên thuộc tính gốc. Nếu muốn database enforce tính duy nhất đã chuẩn hóa, cần thiết kế một thuộc tính khóa đã chuẩn hóa (ví dụ `emailKey`), sửa dữ liệu nguồn và tạo uniqueness cho `emailKey`.

Các hàm như `trim()`, `toLower()` kỳ vọng dữ liệu chuỗi. Nếu dữ liệu nhập có thể sai kiểu, nên phát hiện giá trị sai kiểu trước khi chạy biểu thức chuẩn hóa hàng loạt.

## 4. Phát hiện thiếu thuộc tính trước existence hoặc node key

Với mỗi thuộc tính bắt buộc, dùng `IS NULL`:

```cypher
MATCH (c:AuditCustomer)
WHERE c.email IS NULL
RETURN c.sourceId AS sourceId, properties(c) AS currentProperties
ORDER BY sourceId;
```

Kết quả có **C3**. Trong Neo4j, không thể lưu một property với giá trị `null` như một giá trị thông thường: đặt property thành `null` tương đương loại bỏ property đó. Do vậy `c.email IS NULL` bao phủ trường hợp không có thuộc tính.

Đối với khóa tổ hợp, cần tìm **mọi hàng thiếu ít nhất một thành phần**, chứ không chỉ hàng thiếu toàn bộ:

```cypher
MATCH (o:AuditOrder)
WHERE o.tenantId IS NULL OR o.orderCode IS NULL
RETURN o.sourceId AS sourceId,
       o.tenantId AS tenantId,
       o.orderCode AS orderCode
ORDER BY sourceId;
```

Kết quả có **O4**, thiếu `orderCode`. Hàng này **không gây lỗi cho composite uniqueness** trên `(tenantId, orderCode)`, nhưng **gây lỗi cho node key** tương ứng.

Nếu muốn audit số lượng trước khi đi sâu vào bản ghi:

```cypher
MATCH (c:AuditCustomer)
RETURN count(*) AS totalCustomers,
       count(c.email) AS customersWithEmail,
       count(*) - count(c.email) AS missingEmail;
```

Ví dụ cho kết quả `totalCustomers = 5`, `customersWithEmail = 4` và `missingEmail = 1`. `count(property)` chỉ đếm giá trị khác `null`; `count(*)` đếm mọi hàng.

## 5. Phát hiện trùng khóa tổ hợp

Giả sử `orderCode` chỉ cần duy nhất **trong từng tenant**. Đơn vị duy nhất là cặp `(tenantId, orderCode)`, không phải `orderCode` riêng lẻ.

```cypher
MATCH (o:AuditOrder)
WHERE o.tenantId IS NOT NULL AND o.orderCode IS NOT NULL
WITH o.tenantId AS tenantId,
     o.orderCode AS orderCode,
     count(*) AS occurrences,
     collect(o.sourceId) AS records
WHERE occurrences > 1
RETURN tenantId, orderCode, occurrences, records
ORDER BY occurrences DESC, tenantId, orderCode;
```

Kết quả:

| tenantId | orderCode | occurrences | records |
| --- | --- | ---: | --- |
| `T1` | `001` | 2 | `['O1', 'O2']` |

**O3** không bị coi là trùng với O1/O2 vì thuộc tenant `T2`. Khi thiết kế constraint, chọn sai phạm vi (chẳng hạn uniqueness chỉ trên `orderCode`) sẽ khiến dữ liệu hợp lệ bị xem là vi phạm.

Đối với **composite uniqueness**, cần chạy kiểm tra trùng cho các bộ có đủ thuộc tính. Đối với **composite node key**, phải chạy **cả** kiểm tra trùng ở phần này **và** kiểm tra thiếu khóa ở mục 4.

## 6. Audit thuộc tính trên relationship

Constraint áp dụng cho relationship được đánh giá trên **tất cả relationship của cùng type**, bất kể chúng nối các node nào. Ví dụ, yêu cầu mọi `AUDIT_PLACED` có `eventId` và mỗi `eventId` được dùng không quá một lần.

Kiểm tra trùng:

```cypher
MATCH ()-[r:AUDIT_PLACED]->()
WHERE r.eventId IS NOT NULL
WITH r.eventId AS eventId,
     count(*) AS occurrences,
     collect(r.sourceId) AS records
WHERE occurrences > 1
RETURN eventId, occurrences, records;
```

Kết quả: `eventId = 'E1'` xuất hiện **2 lần**, tại R1/R2.

Kiểm tra thiếu:

```cypher
MATCH ()-[r:AUDIT_PLACED]->()
WHERE r.eventId IS NULL
RETURN r.sourceId AS sourceId,
       properties(r) AS currentProperties;
```

Kết quả có **R3**. Mẫu `MATCH ()-[r:AUDIT_PLACED]->()` không giới hạn label của hai node đầu mút, do đó không vô tình bỏ sót relationship cùng type nối những loại node khác.

Một điều cần phân biệt: ràng buộc unique trên `r.eventId` kiểm tra **giá trị eventId toàn cục trong relationship type**. Nếu yêu cầu “eventId chỉ duy nhất đối với từng tenant”, hãy đưa phạm vi tenant vào mô hình khóa và lựa chọn constraint phù hợp; không thể mặc nhiên suy phạm vi từ node đầu mút.

## 7. Phát hiện sai kiểu trước property type constraint

Một dữ liệu có thể **hiện diện và không trùng** nhưng vẫn sai kiểu. Trong bộ dữ liệu mẫu, `C4.age` là chuỗi `'25'` trong khi quy tắc mong muốn là số nguyên.

Với Cypher có hỗ trợ **type predicate** (Neo4j 5.9 trở lên), có thể kiểm tra:

```cypher
MATCH (c:AuditCustomer)
WHERE c.age IS NOT NULL
  AND NOT (c.age IS :: INTEGER)
RETURN c.sourceId AS sourceId,
       c.age AS actualValue,
       valueType(c.age) AS actualType;
```

Truy vấn tìm được **C4**. Nếu `age` có thể thiếu và nghiệp vụ yêu cầu bắt buộc, phải kiểm tra thêm `WHERE c.age IS NULL`: **type constraint không thay thế existence constraint**.

Không nên “sửa” mọi chuỗi thành số bằng cách ép kiểu hàng loạt trước khi xem dữ liệu. Với các giá trị như `'25'`, `'25 tuổi'` hoặc `'không rõ'`, một phép chuyển đổi áp dụng bừa có thể mất thông tin hoặc tạo dữ liệu sai. Hãy xác định quy tắc chuyển đổi, ghi nhận bản gốc và kiểm tra trường hợp không chuyển đổi được.

**Tính hợp lệ nghiệp vụ khác tính hợp lệ lược đồ:** kiểu `STRING` không đảm bảo email có định dạng phù hợp; kiểu `INTEGER` không đảm bảo tuổi nằm trong miền giá trị cho phép. Các quy tắc này cần kiểm tra bổ sung ở quy trình nhập dữ liệu hoặc lớp ứng dụng.

## 8. Quy trình audit và xử lý trước migration

### Bước 1 — Ghi rõ bộ constraint dự kiến

Ví dụ:

| Đối tượng | Quy tắc dự kiến | Kiểm tra phải vượt qua |
| --- | --- | --- |
| `AuditCustomer.email` | Unique và bắt buộc | Không trùng giá trị thật; không thiếu |
| `AuditCustomer.age` | `INTEGER` | Không có giá trị hiện diện sai kiểu |
| `AuditOrder(tenantId, orderCode)` | Node key | Không thiếu thành phần; không trùng cặp |
| `AUDIT_PLACED.eventId` | Unique và bắt buộc | Không trùng; không thiếu |

Nếu cần kiểm tra những constraint **đã tồn tại** để tránh cấu hình trùng hoặc mâu thuẫn, có thể xem:

```cypher
SHOW CONSTRAINTS
YIELD name, type, entityType, labelsOrTypes, properties
RETURN name, type, entityType, labelsOrTypes, properties
ORDER BY name;
```

### Bước 2 — Chạy kiểm tra **chỉ đọc**, lưu danh sách vi phạm

Các truy vấn `MATCH`/`RETURN` ở mục 3–7 không sửa dữ liệu. Lưu **loại vi phạm, khóa bị trùng hoặc thiếu, số lượng và mã nghiệp vụ** để bàn với chủ dữ liệu. Với nhiều bản ghi, trước tiên chỉ đếm nhóm, sau đó truy vấn chi tiết những nhóm cần xử lý; `collect()` toàn bộ node/ID có thể tiêu tốn bộ nhớ.

Không nên hiểu `LIMIT 10` trong truy vấn liệt kê lỗi là “toàn bộ dữ liệu chỉ có 10 lỗi”. `LIMIT` chỉ giới hạn **mẫu được hiển thị**; để quyết định đã sạch dữ liệu, dùng thống kê trên **toàn bộ phạm vi cần ràng buộc**.

### Bước 3 — Chọn cách xử lý theo nghiệp vụ

Tùy loại vi phạm, hướng xử lý có thể khác nhau:

1. **Trùng khóa:** xác định node/relationship nào là bản ghi đúng, có cần hợp nhất dữ liệu và quan hệ, hay thực chất khóa nghiệp vụ được chọn quá hẹp. Không dùng `DETACH DELETE` để xóa bản sao khi chưa kiểm tra các relationship liên quan.
2. **Thiếu thuộc tính:** bổ sung từ nguồn tin cậy, hoặc thống nhất xem bản ghi chưa đủ điều kiện có cần đổi trạng thái/label trước khi áp dụng constraint hay không.
3. **Sai kiểu:** xác minh dạng dữ liệu nguồn và quy tắc chuyển đổi; kiểm tra sau chuyển đổi.
4. **Trùng khi chuẩn hóa:** thống nhất việc bỏ khoảng trắng/hoa-thường và sử dụng cùng quy tắc ở API, quy trình import và dữ liệu đã tồn tại.

Lệnh `MERGE` của Cypher hữu ích khi tạo hoặc tìm dữ liệu theo khóa, nhưng **không tự hợp nhất các node trùng đã tồn tại**. Việc chọn bản ghi giữ lại, di chuyển quan hệ và xử lý thuộc tính xung đột phải là một phương án sửa dữ liệu có chủ đích.

Có thể xem trước khóa chuẩn hóa mà **không ghi** dữ liệu:

```cypher
MATCH (c:AuditCustomer)
WHERE c.email IS NOT NULL
RETURN c.sourceId AS sourceId,
       c.email AS originalEmail,
       toLower(trim(c.email)) AS proposedEmailKey
ORDER BY sourceId;
```

### Bước 4 — Kiểm tra lại sát thời điểm tạo constraint

Sau khi sửa, chạy lại tất cả truy vấn audit. Cần đạt **0 nhóm trùng**, **0 bản ghi thiếu** và **0 bản ghi sai kiểu** đúng theo từng constraint. Nếu ứng dụng vẫn đang ghi dữ liệu, bản ghi mới có thể xuất hiện giữa lần audit và lần tạo constraint. Lập kế hoạch migration phù hợp, kiểm soát luồng ghi trong giai đoạn chuyển tiếp và để constraint trở thành cơ chế bảo vệ sau khi tạo thành công.

### Bước 5 — Tạo constraint rồi xác minh

Các lệnh sau là **minh họa cấu hình đích**. **Không chạy trên bộ dữ liệu lỗi ở mục 2** nếu chưa làm sạch; những constraint liên quan sẽ thất bại. Dùng đúng tên và label/type của môi trường thực tế, đồng thời kiểm tra edition/version cho các loại constraint ngoài uniqueness cơ bản.

```cypher
// Unique trên email của node
CREATE CONSTRAINT audit_customer_email_unique IF NOT EXISTS
FOR (c:AuditCustomer)
REQUIRE c.email IS UNIQUE;
```

```cypher
// Existence: cần edition hỗ trợ
CREATE CONSTRAINT audit_customer_email_required IF NOT EXISTS
FOR (c:AuditCustomer)
REQUIRE c.email IS NOT NULL;
```

```cypher
// Node key tổ hợp: vừa unique, vừa yêu cầu đủ thuộc tính
CREATE CONSTRAINT audit_order_key IF NOT EXISTS
FOR (o:AuditOrder)
REQUIRE (o.tenantId, o.orderCode) IS NODE KEY;
```

```cypher
// Unique trên thuộc tính relationship: cần phiên bản hỗ trợ
CREATE CONSTRAINT audit_event_unique IF NOT EXISTS
FOR ()-[r:AUDIT_PLACED]-()
REQUIRE r.eventId IS UNIQUE;
```

```cypher
// Property type constraint: tính năng Neo4j 5.9+ và edition hỗ trợ
CREATE CONSTRAINT audit_customer_age_integer IF NOT EXISTS
FOR (c:AuditCustomer)
REQUIRE c.age IS :: INTEGER;
```

`IF NOT EXISTS` chỉ tránh lỗi khi một constraint phù hợp đã tồn tại; **nó không cho phép bỏ qua dữ liệu vi phạm**. Sau khi triển khai, chạy lại `SHOW CONSTRAINTS` và xác nhận những constraint dự kiến thực sự hiện diện.

## 9. Vận hành an toàn trên đồ thị lớn

Audit toàn bộ một label lớn có thể cần đọc rất nhiều node/relationship và gom nhóm nhiều giá trị. Nên:

- **Ưu tiên các truy vấn tổng hợp nhỏ:** đếm số nhóm vi phạm trước, rồi xem danh sách `sourceId` của từng nhóm cần xử lý; giới hạn `collect()` khi nhóm trùng quá lớn.
- **Kiểm tra execution plan:** dùng `EXPLAIN` hoặc `PROFILE` với truy vấn chỉ đọc khi cần xem quy mô scan, index access và bộ nhớ của bước aggregation. `PROFILE` thực sự chạy truy vấn.
- **Chạy vào thời điểm phù hợp với tải:** thực thi audit lớn trên môi trường có tài nguyên được dự trù; xác định rõ database, label và relationship type đang kiểm tra.
- **Lưu bằng chứng có thể kiểm chứng:** số lỗi trước/sau, trường dữ liệu thay đổi, kết quả rà soát, thời điểm triển khai và constraint được tạo.
- **Bảo vệ các lần ghi mới:** chuẩn hóa và kiểm tra đầu vào ở quy trình import, Neo4j Java Driver hoặc Spring Data Neo4j; xử lý lỗi constraint trả về từ database theo nghiệp vụ. Các kiểm tra phía ứng dụng không thay thế bảo đảm đồng thời của constraint trong database.

Trong hệ thống nhiều tenant hoặc tích hợp nhiều nguồn dữ liệu, điều quan trọng nhất là xác định đúng **ranh giới duy nhất**: global, theo tenant hay theo nguồn. Một lược đồ ràng buộc sai phạm vi vẫn có thể nhất quán về mặt kỹ thuật nhưng không đúng nhu cầu nghiệp vụ.

## 10. Bảng tự kiểm trước khi bật constraint

| Câu hỏi kiểm tra | Dấu hiệu hoàn tất |
| --- | --- |
| Đã xác định label/type, property và phạm vi duy nhất chưa? | Có mô tả khóa nghiệp vụ và loại constraint cụ thể |
| Đã kiểm tra trùng chính xác theo khóa sẽ lưu chưa? | 0 nhóm có `count(*) > 1` |
| Có quy tắc chuẩn hóa chuỗi/giá trị không? | Đã audit bằng khóa chuẩn hóa tương ứng và thống nhất cách lưu |
| Đã kiểm tra mọi thuộc tính bắt buộc chưa? | 0 hàng có property `IS NULL` |
| Khóa tổ hợp có thiếu thành phần không? | 0 hàng thiếu bất cứ thành phần nào nếu dùng node key |
| Đã kiểm tra relationship và kiểu dữ liệu nếu có liên quan chưa? | 0 nhóm quan hệ trùng, 0 thuộc tính quan hệ thiếu, 0 giá trị sai kiểu |
| Đã kiểm tra lại sau sửa và ngay trước triển khai chưa? | Báo cáo audit mới nhất sạch, luồng ghi được kiểm soát |
| Đã xác minh constraint sau khi tạo chưa? | `SHOW CONSTRAINTS` hiển thị đầy đủ constraint mong muốn |

**Ghi nhớ:** thao tác tạo constraint là **bước cuối của việc làm sạch và xác minh dữ liệu**, không phải công cụ sửa dữ liệu. Một báo cáo audit có thể chỉ ra rất rõ “ai đang vi phạm điều gì”; quyết định “sửa ra sao” vẫn cần hiểu mô hình property graph, quan hệ giữa các node và khóa nghiệp vụ của hệ thống.
