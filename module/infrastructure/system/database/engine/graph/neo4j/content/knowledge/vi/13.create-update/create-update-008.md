# FOREACH và các lựa chọn cập nhật có điều kiện trong Neo4j Cypher

## Mục tiêu

Khi làm việc với **Neo4j**, dữ liệu được biểu diễn dưới dạng **property graph**: node mang label và property, relationship có hướng, loại và property. Một câu lệnh cập nhật đôi khi chỉ được thực hiện nếu node hoặc mối quan hệ đáp ứng điều kiện nghiệp vụ: đánh dấu công việc quá hạn, tạo liên kết cho công việc ưu tiên cao, hoặc chỉ ghi một trường khi có dữ liệu đầu vào hợp lệ.

Sau bài học, bạn có thể:

- Hiểu cú pháp, phạm vi biến và giới hạn của `FOREACH` trong Cypher.
- Thực hiện cập nhật có điều kiện bằng `FOREACH` kết hợp `CASE`.
- Chọn đúng giữa `WHERE` + `SET`, `CASE` trong biểu thức, `UNWIND`, `MERGE ... ON CREATE/ON MATCH`, subquery `CALL` và `WHEN` của Cypher 25.
- Tránh lỗi liên quan đến giá trị `null`, bản ghi bị lọc, cập nhật lặp và hiệu năng khi thao tác với đồ thị.

> **Phạm vi phiên bản:** `FOREACH`, `CASE`, `WHERE`, `MERGE` và `UNWIND` trong các ví dụ chính phù hợp với Cypher 5 và Cypher 25. Cú pháp truy vấn điều kiện `WHEN ... THEN ... ELSE` chỉ có trong **Cypher 25**, được giới thiệu từ **Neo4j 2025.06**. Khi thử ví dụ, dùng Neo4j Browser hoặc một môi trường Cypher tương ứng với phiên bản đã chọn.

## 1. Bối cảnh: điều kiện áp dụng cho hàng hay cho thuộc tính?

Hãy xét đồ thị quản lý dự án:

```text
(:Project {code: "P-01"})
     │
     ├──[:HAS_TASK]──> (:Task {id: "T-101", status: "OPEN", priority: 9})
     ├──[:HAS_TASK]──> (:Task {id: "T-102", status: "OPEN", priority: 3})
     └──[:HAS_TASK]──> (:Task {id: "T-103", status: "DONE", priority: 8})
```

Ba nhu cầu khác nhau dẫn đến ba cách viết khác nhau:

1. **Chỉ sửa node đủ điều kiện:** lọc bằng `WHERE` rồi `SET`.
2. **Tính giá trị mới theo nhiều nhánh:** dùng `CASE` ở phía phải của `SET`.
3. **Chạy một nhóm lệnh ghi hoặc tạo relationship khi điều kiện đúng:** có thể dùng `FOREACH` với danh sách điều kiện, hoặc subquery điều kiện trên phiên bản hỗ trợ.

`FOREACH` vốn dùng để lặp qua **danh sách** nhằm **ghi dữ liệu**. Mẫu `FOREACH + CASE` tận dụng danh sách có một phần tử để thực thi một lần và danh sách rỗng để bỏ qua; vì vậy nó đôi khi được gọi là cách mô phỏng `IF` trong Cypher 5.

## 2. Chuẩn bị dữ liệu thực hành

Chạy hai câu lệnh tạo ràng buộc trên **cơ sở dữ liệu thử nghiệm**:

```cypher
CREATE CONSTRAINT project_code_unique IF NOT EXISTS
FOR (p:Project) REQUIRE p.code IS UNIQUE;
```

```cypher
CREATE CONSTRAINT task_id_unique IF NOT EXISTS
FOR (t:Task) REQUIRE t.id IS UNIQUE;
```

Sau đó tạo một dự án và ba công việc:

```cypher
MERGE (p:Project {code: 'P-01'})
WITH p
UNWIND [
  {id: 'T-101', status: 'OPEN', priority: 9, dueDate: date('2025-10-01')},
  {id: 'T-102', status: 'OPEN', priority: 3, dueDate: date('2030-01-01')},
  {id: 'T-103', status: 'DONE', priority: 8, dueDate: date('2025-09-01')}
] AS data
MERGE (t:Task {id: data.id})
SET t.status = data.status,
    t.priority = data.priority,
    t.dueDate = data.dueDate
MERGE (p)-[:HAS_TASK]->(t);
```

Trong ví dụ, `T-101` đang mở, có độ ưu tiên cao và đã quá hạn; `T-102` đang mở nhưng chưa đến hạn; `T-103` đã hoàn tất. Chạy lại câu lệnh khởi tạo sẽ đặt lại `status`, `priority` và `dueDate` của ba công việc; các property hoặc relationship do bài thực hành thêm vào sẽ không tự bị xóa. Nếu muốn so sánh kết quả từng ví dụ độc lập, hãy dùng cơ sở dữ liệu thử nghiệm sạch.

Kiểm tra dữ liệu:

```cypher
MATCH (p:Project {code: 'P-01'})-[:HAS_TASK]->(t:Task)
RETURN p.code AS projectCode, t.id AS taskId,
       t.status AS status, t.priority AS priority, t.dueDate AS dueDate
ORDER BY taskId;
```

## 3. Cú pháp và ngữ nghĩa của FOREACH

Mẫu tổng quát:

```cypher
FOREACH (item IN listExpression |
  SET item.someProperty = 'value'
)
```

- `listExpression` phải cho ra một danh sách; phần thân được thực hiện **một lần cho mỗi phần tử** trong danh sách.
- Phần thân chỉ nhận các thao tác cập nhật như `SET`, `REMOVE`, `CREATE`, `MERGE`, `DELETE` hoặc `FOREACH` lồng nhau. Không đặt `MATCH`, `OPTIONAL MATCH`, `WITH` hay `RETURN` bên trong dấu ngoặc của `FOREACH`.
- Biến lặp và những biến mới được tạo **bên trong** `FOREACH` có phạm vi riêng. Biến khai báo **trước** `FOREACH` vẫn có thể được tham chiếu trong phần thân, nhưng biến nội bộ không tự động xuất hiện ở phía ngoài.
- `FOREACH` không sinh ra một bảng kết quả như `UNWIND`. Khi cần tiếp tục đọc, lọc hoặc kết hợp mẫu cho từng phần tử, thường nên sử dụng `UNWIND`.

Ví dụ: đánh dấu tất cả công việc thuộc dự án sau khi gom chúng vào danh sách.

```cypher
MATCH (:Project {code: 'P-01'})-[:HAS_TASK]->(t:Task)
WITH collect(DISTINCT t) AS tasks
FOREACH (task IN tasks |
  SET task.checkedByBatch = true
);
```

`collect(DISTINCT t)` tránh đưa cùng node vào danh sách nhiều lần khi một mẫu truy vấn có thể trả về các dòng trùng. Với đồ thị lớn, không nên gom toàn bộ node vào một danh sách khổng lồ chỉ để cập nhật; có thể xử lý theo dòng bằng `MATCH ... WHERE ... SET`.

`FOREACH` cũng hữu ích với node hoặc relationship thuộc đường đi:

```cypher
MATCH p = (project:Project {code: 'P-01'})-[:HAS_TASK]->(:Task)
FOREACH (r IN relationships(p) |
  SET r.inspected = true
);
```

Ở đây `relationships(p)` trả về danh sách relationship nằm trên từng đường đi được khớp.

## 4. FOREACH + CASE: chỉ ghi khi điều kiện đúng

`CASE` là **biểu thức chọn giá trị**, không phải một khối lệnh điều khiển. Để điều khiển việc thực thi phần thân `FOREACH`, ta cho `CASE` trả về danh sách:

```cypher
MATCH (t:Task)
FOREACH (_ IN CASE
  WHEN t.status = 'OPEN' AND t.dueDate < date() THEN [1]
  ELSE []
END |
  SET t.isOverdue = true,
      t.needsReview = true
)
RETURN t.id AS taskId, t.isOverdue AS isOverdue
ORDER BY taskId;
```

| Giá trị điều kiện | Danh sách từ `CASE` | Số lần chạy phần thân |
| --- | --- | --- |
| `true` | `[1]` | 1 |
| `false` | `[]` | 0 |
| `null` | `[]`, nhờ nhánh `ELSE` | 0 |

Biến `_` chỉ đóng vai trò giữ phần tử giả, không tham gia câu lệnh `SET`. Với dữ liệu mẫu, `T-101` được đánh dấu; `T-102` chưa quá hạn và `T-103` đã hoàn tất nên bị bỏ qua.

**Điểm cần phân biệt:** nhánh `ELSE []` có nghĩa **không cập nhật**, chứ không có nghĩa đặt thuộc tính về `false` hay xóa thuộc tính trước đó. Nếu điều kiện của một công việc thay đổi, cờ cũ có thể vẫn còn. Để đồng bộ cờ đúng/sai sau mỗi lần chạy, dùng `SET + CASE` ở mục 5.2.

### Nhiều thao tác ghi trong cùng một nhánh

Một ưu điểm của `FOREACH + CASE` là gom các lệnh ghi chỉ được phép chạy khi điều kiện đúng. Ví dụ tạo liên kết báo cáo công việc ưu tiên cao:

```cypher
MATCH (p:Project {code: 'P-01'})-[:HAS_TASK]->(t:Task)
FOREACH (_ IN CASE
  WHEN t.status = 'OPEN' AND t.priority >= 8 THEN [1]
  ELSE []
END |
  SET t.escalationLevel = 2
  MERGE (p)-[:ESCALATES]->(t)
);
```

Với dữ liệu mẫu, chỉ `T-101` được gắn mức leo thang và quan hệ `ESCALATES`. `MERGE` có thể tái sử dụng mẫu quan hệ đã có, giảm nguy cơ tạo trùng khi chạy lại; `CREATE` sẽ tạo một quan hệ mới mỗi lần thực thi.

Nếu cần `MATCH` bổ sung để tìm node khác, hãy thực hiện **trước** `FOREACH`, hoặc chọn `UNWIND`/subquery. Ví dụ với node người phụ trách có thể không tồn tại:

```cypher
MATCH (t:Task {id: 'T-101'})
OPTIONAL MATCH (u:User {id: 'U-01'})
FOREACH (_ IN CASE
  WHEN u IS NOT NULL AND t.status = 'OPEN' THEN [1]
  ELSE []
END |
  MERGE (u)-[:ASSIGNED_TO]->(t)
);
```

Nếu chưa có `U-01`, `OPTIONAL MATCH` đặt `u` là `null` và danh sách rỗng ngăn câu lệnh `MERGE` chạy. Điều kiện kiểm tra tồn tại của node là thiết yếu trước khi dùng nó trong mẫu ghi.

## 5. Các lựa chọn cập nhật có điều kiện

### 5.1. WHERE + SET: lọc node trước khi ghi

Khi chỉ cần cập nhật những node thỏa một điều kiện, đây thường là cách trực tiếp nhất:

```cypher
MATCH (t:Task)
WHERE t.status = 'OPEN' AND t.priority >= 8
SET t.reviewRequired = true
RETURN count(t) AS updatedTasks;
```

`WHERE` loại những dòng không thỏa điều kiện **trước bước ghi**. Khác với `CASE` đặt ở phía phải của `SET`, các node bị loại không đi tiếp qua phần còn lại của truy vấn. Trong ví dụ, `updatedTasks` là số dòng còn lại sau bước lọc; nếu phép `MATCH` tạo nhiều dòng cho cùng một node thì cần chú ý trùng lặp hoặc sử dụng `WITH DISTINCT t`.

### 5.2. SET + CASE: tính giá trị cần lưu

Khi muốn **mọi node đều có trạng thái được tính lại**, biểu thức `CASE` đủ dùng:

```cypher
MATCH (t:Task)
SET t.isOverdue =
  CASE
    WHEN t.status = 'OPEN' AND t.dueDate < date() THEN true
    ELSE false
  END
RETURN t.id AS taskId, t.isOverdue AS isOverdue
ORDER BY taskId;
```

Lúc này `T-101` nhận `true`, còn `T-102` và `T-103` nhận `false`. Nhờ nhánh `ELSE`, các cờ cũ được cập nhật lại theo tình trạng hiện tại.

`CASE` cũng hỗ trợ nhiều nhánh theo thứ tự:

```cypher
MATCH (t:Task)
SET t.queue = CASE
  WHEN t.status = 'DONE' THEN 'ARCHIVE'
  WHEN t.priority IS NULL THEN 'UNCLASSIFIED'
  WHEN t.priority >= 8 THEN 'URGENT'
  ELSE 'NORMAL'
END;
```

Nhánh đầu tiên trả về `true` được chọn. `CASE` chỉ **tính một giá trị** cho `t.queue`; nó không thể tự chạy `CREATE`, `MERGE` hay một chuỗi lệnh ghi.

### 5.3. SET += CASE: cập nhật có điều kiện một nhóm thuộc tính

Khi điều kiện đúng, có thể ghép một map vào node; khi sai, ghép map rỗng:

```cypher
MATCH (t:Task)
SET t += CASE
  WHEN t.status = 'OPEN' AND t.priority >= 8
    THEN {reviewRequired: true, route: 'URGENT'}
  ELSE {}
END;
```

`SET t += map` chỉ thêm/ghi đè các property có tên trong map, giữ nguyên property khác. `SET t = map` có nghĩa **thay toàn bộ tập property** của node, nên không dùng thay thế nếu không có chủ đích. Đây là lựa chọn ngắn gọn cho nhiều property, nhưng vẫn không tạo hoặc xóa relationship.

Trong Neo4j, đặt một property bằng `null` sẽ **xóa property đó**. Chẳng hạn:

```cypher
MATCH (t:Task)
SET t.reviewReason = CASE
  WHEN t.status = 'OPEN' AND t.priority >= 8 THEN 'HIGH_PRIORITY'
  ELSE null
END;
```

Hãy chọn `ELSE false` nếu nghiệp vụ cần lưu cờ boolean, hoặc `ELSE null` nếu muốn thuộc tính không tồn tại khi điều kiện sai.

### 5.4. MERGE với ON CREATE / ON MATCH: phân biệt mới tạo và đã tồn tại

`MERGE` tìm hoặc tạo một mẫu. Hai nhánh đi kèm chỉ phụ thuộc vào việc **mẫu đó vừa được tạo hay đã được tìm thấy**:

```cypher
MERGE (t:Task {id: 'T-104'})
ON CREATE SET t.status = 'OPEN',
              t.createdAt = datetime()
ON MATCH SET t.lastSeenAt = datetime()
RETURN t.id AS taskId, t.status AS status,
       t.createdAt AS createdAt, t.lastSeenAt AS lastSeenAt;
```

Lần đầu, `T-104` được tạo và chạy `ON CREATE`; những lần sau, mẫu được tìm thấy và chạy `ON MATCH`. Đây **không phải** cơ chế `IF t.priority >= 8`: muốn lọc theo điều kiện nghiệp vụ, vẫn cần `WHERE`, `CASE`, `FOREACH` hoặc truy vấn điều kiện. Ràng buộc duy nhất trên `Task.id` giúp khóa nghiệp vụ được bảo vệ khi ghi đồng thời.

### 5.5. UNWIND + WHERE: làm việc với danh sách, vẫn cần MATCH

`UNWIND` biến từng phần tử danh sách thành một dòng truy vấn. Sau đó có thể `WITH`, `WHERE`, `MATCH` và `SET` như bình thường:

```cypher
UNWIND [
  {id: 'T-101', rating: 3},
  {id: 'T-102', rating: null},
  {id: 'T-999', rating: 2}
] AS data
WITH data
WHERE data.rating IS NOT NULL
MATCH (t:Task {id: data.id})
SET t.importRating = data.rating
RETURN count(t) AS updatedTasks;
```

Kết quả là chỉ `T-101` được ghi `importRating`: `T-102` bị loại vì giá trị `null`, còn `T-999` không tìm thấy node tương ứng. Trường hợp nhập dữ liệu thực tế từ Java Driver, danh sách có thể được truyền dưới dạng tham số thay cho danh sách viết trực tiếp trong Cypher.

Nếu `UNWIND` xuất hiện cùng với `WHERE`, cần đặt `WHERE` sau một `WITH` thích hợp (như ví dụ); không viết `UNWIND ... AS data WHERE ...` như thể `UNWIND` hỗ trợ `WHERE` trực tiếp.

### 5.6. CALL và WHEN: nhánh truy vấn điều kiện trong Cypher 25

Kể từ **Neo4j 2025.06**, **Cypher 25** bổ sung `WHEN ... THEN ... ELSE` để thực thi các **nhánh truy vấn**, kể cả nhánh có thao tác ghi. Ví dụ:

```cypher
CYPHER 25
MATCH (t:Task)
CALL (t) {
  WHEN t.status = 'OPEN' AND t.priority >= 8 THEN {
    SET t.reviewRequired = true
    RETURN 'updated' AS action
  }
  ELSE {
    RETURN 'skipped' AS action
  }
}
RETURN t.id AS taskId, action
ORDER BY taskId;
```

`CALL (t)` đưa biến `t` từ truy vấn bên ngoài vào subquery. Hai nhánh đều trả về một cột tên `action` để kết quả có cấu trúc thống nhất. Với ba công việc được khởi tạo ban đầu, `T-101` báo `updated`, `T-102` và `T-103` báo `skipped`; `T-104` cũng báo `skipped` nếu đã chạy ví dụ ở mục 5.4.

Lưu ý ba điểm khi dùng `WHEN`:

- Phải chọn **Cypher 25** trên một bản Neo4j có hỗ trợ. Không dùng cú pháp này trên Neo4j 5 đời cũ hoặc truy vấn đang chạy ở chế độ Cypher 5.
- Trong truy vấn có `MATCH` ở ngoài, `WHEN` phải nằm trong subquery thích hợp như `CALL (t) { ... }`; không thể đặt trực tiếp `MATCH ... WHEN ...` theo kiểu một mệnh đề thông thường.
- Nếu subquery có nhánh trả về dòng mà không có `ELSE`, các dòng không đi vào nhánh nào có thể không xuất hiện ở kết quả ngoài. Chủ động dùng `ELSE` khi cần giữ một kết quả cho mọi dòng đầu vào.

Đối với bài toán phải `MATCH` thêm mẫu bên trong điều kiện, subquery `CALL` linh hoạt hơn `FOREACH` vì phần thân `FOREACH` chỉ cho phép các lệnh ghi. Khi cần các nhánh thực thi khác nhau trên hệ Cypher 25, `WHEN` thường dễ đọc hơn mẹo danh sách `[1]`/`[]`.

## 6. Chọn cách viết theo nhu cầu

| Tình huống | Lựa chọn phù hợp | Lý do |
| --- | --- | --- |
| Chỉ sửa node đạt điều kiện | `MATCH ... WHERE ... SET` | Ngắn, rõ và lọc dòng trước khi ghi |
| Mỗi node cần một giá trị khác nhau | `SET property = CASE ... END` | Tính lại giá trị cho cả nhánh đúng và sai |
| Cập nhật nhiều property, giữ nguyên các field khác | `SET n += CASE ... END` | Ghép map có điều kiện |
| Lặp cập nhật trên node/relationship có sẵn trong list hoặc path | `FOREACH` | Thực thi thao tác ghi cho từng phần tử |
| Chỉ chạy nhiều thao tác ghi khi điều kiện đúng trên Cypher 5 | `FOREACH + CASE` | Danh sách một phần tử hoặc rỗng điều khiển số lần ghi |
| Phải tìm thêm node cho từng phần tử danh sách | `UNWIND` với `MATCH`/`WHERE` | Hỗ trợ các mệnh đề đọc lẫn ghi |
| Phân biệt một mẫu được tạo mới hay đã có | `MERGE ... ON CREATE/ON MATCH` | Điều kiện phụ thuộc kết quả của `MERGE` |
| Nhiều nhánh truy vấn, có thể đọc và ghi khác nhau trên Cypher 25 | `CALL (...) { WHEN ... THEN ... ELSE ... }` | Diễn đạt nhánh điều kiện rõ ràng |

## 7. Lỗi thường gặp và cách tránh

**Lỗi 1 — Đặt MATCH trong FOREACH.**

```cypher
// SAI: MATCH không được dùng bên trong FOREACH.
WITH ['T-101', 'T-102'] AS ids
FOREACH (id IN ids |
  MATCH (t:Task {id: id})
  SET t.checked = true
);
```

Sửa bằng `UNWIND`:

```cypher
UNWIND ['T-101', 'T-102'] AS id
MATCH (t:Task {id: id})
SET t.checked = true;
```

**Lỗi 2 — Giả định ELSE [] sẽ hoàn tác cập nhật trước.** Nó chỉ bỏ qua lần chạy hiện tại. Muốn đồng bộ cả `true`/`false`, dùng `SET ... = CASE ... ELSE false END`; muốn xóa khi không thỏa điều kiện, dùng `ELSE null` cho property phù hợp.

**Lỗi 3 — Không xét null.** Trong Cypher, biểu thức như `t.priority >= 8` có thể trả về `null` khi thiếu `priority`. `CASE WHEN` chỉ chọn nhánh khi điều kiện là `true`. Sử dụng `IS NULL`/`IS NOT NULL`, `coalesce(...)` hoặc nhánh `ELSE` để quy định hành vi rõ ràng.

**Lỗi 4 — Dùng CREATE trong tác vụ chạy lại.** `CREATE (p)-[:ESCALATES]->(t)` mỗi lần chạy có thể sinh thêm relationship cùng kiểu giữa cùng cặp node. `MERGE` thường phù hợp hơn khi yêu cầu quan hệ chỉ có một mẫu tồn tại; cân nhắc ràng buộc khóa nghiệp vụ cho các node được tạo bằng `MERGE`.

**Lỗi 5 — Quên số dòng đầu vào.** Nếu một `MATCH` tạo ba dòng cho cùng node, phần thân `FOREACH` cũng có thể được chạy ba lần trên node đó. Kiểm tra số dòng, dùng `WITH DISTINCT` hoặc điều chỉnh mẫu khớp trước khi cập nhật.

**Lỗi 6 — Biến bên trong FOREACH bị mất phạm vi.** Ví dụ `FOREACH (id IN ids | CREATE (newTask:Task {id: id}))` không cho phép `RETURN newTask` sau `FOREACH`. Nếu cần trả về node vừa tạo, hãy dùng `UNWIND ids AS id CREATE (newTask:Task {id: id}) RETURN newTask`.

## 8. Tính đúng đắn, hiệu năng và vận hành

- **Khóa tìm kiếm:** dùng thuộc tính định danh ổn định (`Task.id`, `Project.code`), ràng buộc duy nhất và index thích hợp. Với `MATCH (t:Task {id: $taskId})`, truy vấn có thể tận dụng index từ unique constraint.
- **Tái chạy an toàn:** ưu tiên `MERGE` khi không muốn tạo lặp; với phép `SET`, xác định rõ thao tác nào đặt lại trạng thái và thao tác nào chỉ đánh dấu một lần. Các property như `lastModifiedAt = datetime()` có thể đổi ở mỗi lần chạy.
- **Dữ liệu đầu vào:** truyền tham số từ Java Driver/Spring Data Neo4j (ví dụ `$taskId`, `$minPriority`), không nối trực tiếp dữ liệu người dùng vào chuỗi Cypher. Ví dụ:

  ```cypher
  MATCH (t:Task {id: $taskId})
  WHERE t.status = 'OPEN' AND t.priority >= $minPriority
  SET t.reviewRequired = true
  RETURN t.id AS taskId;
  ```

- **Dữ liệu lớn:** tránh `collect(...)` một lượng node khổng lồ chỉ để đưa vào `FOREACH`. Xử lý theo dòng với `MATCH/WHERE/SET` hoặc `UNWIND`; khi nhập rất nhiều bản ghi, cân nhắc `CALL { ... } IN TRANSACTIONS` với kích thước lô phù hợp và lưu ý cơ chế giao dịch tự động của câu lệnh này.
- **Quan sát kế hoạch:** dùng `EXPLAIN` để xem kế hoạch mà không chạy cập nhật, hoặc `PROFILE` khi có thể chấp nhận thực thi ghi trên dữ liệu thử nghiệm. Kiểm tra việc tận dụng index và số dòng thực tế.
- **Ghi đồng thời:** `MERGE` cùng unique constraint giúp ngăn nhiều node trùng khóa, nhưng cập nhật cạnh tranh trên cùng node vẫn cần thiết kế transaction và xử lý retry ở tầng ứng dụng nếu xảy ra xung đột.

## 9. Bài thực hành tổng hợp

**Yêu cầu:** Với những `Task` thuộc `P-01`, nếu công việc đang mở, độ ưu tiên từ 8 trở lên và đã quá hạn, hãy đặt `requiresEscalation = true` và tạo quan hệ `(:Project)-[:ESCALATES]->(:Task)`. Chạy lại không tạo thêm quan hệ trùng.

Một lời giải dùng `FOREACH + CASE`, chạy trên Cypher 5 hoặc Cypher 25:

```cypher
MATCH (p:Project {code: 'P-01'})-[:HAS_TASK]->(t:Task)
FOREACH (_ IN CASE
  WHEN t.status = 'OPEN'
   AND t.priority >= 8
   AND t.dueDate IS NOT NULL
   AND t.dueDate < date()
  THEN [1]
  ELSE []
END |
  SET t.requiresEscalation = true
  MERGE (p)-[:ESCALATES]->(t)
);
```

Kiểm tra trạng thái và quan hệ:

```cypher
MATCH (p:Project {code: 'P-01'})-[:HAS_TASK]->(t:Task)
OPTIONAL MATCH (p)-[e:ESCALATES]->(t)
RETURN t.id AS taskId,
       t.status AS status,
       t.requiresEscalation AS requiresEscalation,
       count(e) AS escalationRelationships
ORDER BY taskId;
```

Nếu bắt đầu từ dữ liệu mẫu sạch, chỉ `T-101` có `requiresEscalation = true` và một quan hệ `ESCALATES`. Thử chạy câu lệnh cập nhật lần thứ hai: `count(e)` của `T-101` vẫn là 1. Nếu trước đó đã chạy mục 4, kết quả kiểm tra vẫn phù hợp vì `MERGE` tái sử dụng quan hệ có sẵn. Nếu muốn **gỡ** quan hệ khi điều kiện không còn đúng, cần thiết kế thêm một câu lệnh xóa có điều kiện; nhánh `ELSE []` hiện tại không tự gỡ quan hệ.

## 10. Ghi nhớ

`FOREACH` là mệnh đề lặp nhằm **ghi dữ liệu trên một danh sách**. Kết hợp `CASE WHEN ... THEN [1] ELSE [] END` cho phép chọn có hoặc không chạy nhóm thao tác ghi, nhưng không thay thế được `MATCH` bên trong phần thân và không tự hoàn tác cập nhật cũ. Trong phần lớn trường hợp cập nhật một thuộc tính hoặc lọc node, `WHERE + SET` hay `SET + CASE` đơn giản hơn. Với các truy vấn có điều kiện phức tạp trên Neo4j hiện đại, có thể dùng `WHEN` trong **Cypher 25**.

### Tài liệu tham khảo

- [Neo4j Cypher Manual — FOREACH](https://neo4j.com/docs/cypher-manual/current/clauses/foreach/)
- [Neo4j Cypher Manual — SET](https://neo4j.com/docs/cypher-manual/current/clauses/set/)
- [Neo4j Cypher Manual — MERGE](https://neo4j.com/docs/cypher-manual/current/clauses/merge/)
- [Neo4j Cypher Manual — Conditional queries (WHEN)](https://neo4j.com/docs/cypher-manual/current/queries/composed-queries/conditional-queries/)
- [Neo4j Cypher Manual — Select Cypher version](https://neo4j.com/docs/cypher-manual/current/queries/select-version/)
