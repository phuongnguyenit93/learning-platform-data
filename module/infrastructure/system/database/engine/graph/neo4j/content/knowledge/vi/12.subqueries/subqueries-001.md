# CALL với truy vấn con và cách truyền biến theo phiên bản Cypher

> **Chương:** Truy vấn con  
> **Phạm vi:** Neo4j property graph, truy vấn Cypher dùng `CALL` để xử lý các nhóm node/relationship, tính toán theo từng hàng và cập nhật đồ thị. Trọng tâm là **cách đưa biến từ truy vấn ngoài vào truy vấn con**, đặc biệt khi chuyển từ Cypher cũ sang Cypher 5 và Cypher 25.

## 1. Tại sao cần `CALL` subquery?

Trong property graph của Neo4j, một câu truy vấn thường bắt đầu bằng `MATCH` để tìm node và relationship, rồi `WITH` hoặc `RETURN` để tổng hợp kết quả. Khi cần xử lý **riêng từng node đầu vào** — chẳng hạn lấy tối đa hai người quen của mỗi người, đếm quan hệ theo từng nhóm, hoặc cập nhật dữ liệu theo lô — `CALL { ... }` giúp tổ chức phần xử lý thành một **truy vấn con** có phạm vi biến rõ ràng.

Cần phân biệt hai cách dùng từ khóa `CALL`:

- `CALL (p) { ... }`: gọi **truy vấn con Cypher**, do người viết truy vấn định nghĩa ngay trong dấu ngoặc nhọn.
- `CALL db.labels() YIELD label`: gọi **procedure** đã được Neo4j hoặc ứng dụng cung cấp; cách truyền tham số và `YIELD` thuộc cơ chế procedure.

Bài này tập trung vào dạng thứ nhất. `CALL` subquery không tạo ra một bảng dữ liệu độc lập rồi ghép tùy ý: **nó được đánh giá cho từng hàng đầu vào từ truy vấn ngoài**. Các cột do truy vấn con `RETURN` sẽ được nối vào hàng tương ứng ở truy vấn ngoài.

Ví dụ đơn giản, chạy được trên **Neo4j 5.23+** hoặc các bản mới hơn hỗ trợ cú pháp scope:

```cypher
UNWIND [1, 2, 3] AS n
CALL (n) {
  RETURN n * n AS square
}
RETURN n, square
ORDER BY n;
```

| n | square |
|---:|---:|
| 1 | 1 |
| 2 | 4 |
| 3 | 9 |

Ở đây `UNWIND` tạo ba hàng; mỗi hàng có một giá trị `n`. `CALL (n)` đưa `n` của chính hàng đó vào truy vấn con; `RETURN ... AS square` tạo cột `square` cho truy vấn ngoài.

```text
Truy vấn ngoài                Truy vấn con             Kết quả ghép
n = 1  -------------------->  square = 1    ------->  (1, 1)
n = 2  -------------------->  square = 4    ------->  (2, 4)
n = 3  -------------------->  square = 9    ------->  (3, 9)
```

## 2. Bảng tương thích: cú pháp truyền biến thay đổi thế nào?

Điểm dễ nhầm là **phiên bản máy chủ Neo4j** và **phiên bản ngôn ngữ Cypher** không còn luôn mang cùng một số phiên bản.

| Môi trường | Cách truyền biến từ ngoài vào `CALL` | Lưu ý |
|---|---|---|
| Neo4j 4.4 | `CALL { WITH x ... }` | Dùng `WITH` đầu tiên trong truy vấn con để import biến. |
| Neo4j 5.0–5.22 | `CALL { WITH x ... }` | Cú pháp cũ tiếp tục được dùng. |
| Neo4j 5.23 trở lên | **Ưu tiên** `CALL (x) { ... }` | Neo4j 5.23 giới thiệu *variable scope clause*. `CALL { WITH x ... }` và `CALL { ... }` không khai báo scope bắt đầu được đánh dấu *deprecated*. |
| Neo4j 5.24 trở lên | `CALL (x) { ... }`; có thêm `OPTIONAL CALL (x) { ... }` | `OPTIONAL CALL` có thể giữ lại hàng ngoài khi truy vấn con không trả hàng. |
| Neo4j 2025.06 trở lên | `CYPHER 5` hoặc `CYPHER 25` | Một máy chủ có thể chạy cả hai phiên bản ngôn ngữ. Cú pháp `CALL (x)` dùng được ở cả hai; tính năng mới sau mốc 2025.06 có thể chỉ có trong Cypher 25. |

**Quy tắc chọn cú pháp:** khi ứng dụng chắc chắn chạy Neo4j **5.23+**, dùng `CALL (x)` cho code mới. Nếu phải tương thích 4.4 hoặc 5.0–5.22, dùng importing `WITH` và chấp nhận việc cú pháp đó bị khuyến nghị thay thế trên bản mới. Không thể dùng `CALL (x)` trên Neo4j 5.22 chỉ bằng cách thêm tiền tố `CYPHER 25`: bản máy chủ cũ không cung cấp Cypher 25.

Từ Neo4j **2025.06**, có thể chọn ngôn ngữ trên từng câu truy vấn:

```cypher
CYPHER 25
WITH 7 AS x
CALL (x) {
  RETURN x * 10 AS result
}
RETURN result;
```

```cypher
CYPHER 5
WITH 7 AS x
CALL (x) {
  RETURN x * 10 AS result
}
RETURN result;
```

Cả hai cho `result = 70` khi chạy trên máy chủ hỗ trợ chọn phiên bản ngôn ngữ. Từ Neo4j **2026.02**, các cơ sở dữ liệu mới được cấu hình rõ hơn theo Cypher 25; cơ sở dữ liệu nâng cấp có thể giữ cấu hình cũ. Vì vậy khi di chuyển hệ thống, hãy kiểm tra **cả phiên bản máy chủ lẫn ngôn ngữ mặc định của database**.

## 3. Truyền biến bằng variable scope clause — cách hiện đại

Cú pháp tổng quát:

```cypher
... // Truy vấn ngoài tạo các biến a, b, c
CALL (a, b) {
  // Truy vấn con nhìn thấy a, b
  // c không được import nên không khả dụng ở đây
  RETURN ... AS output
}
RETURN a, b, c, output;
```

Có ba trường hợp quan trọng:

| Cú pháp | Biến có thể dùng trong truy vấn con | Khi nên dùng |
|---|---|---|
| `CALL (a, b) { ... }` | Chỉ `a` và `b` từ bên ngoài | Mặc định nên chọn: phụ thuộc rõ ràng, dễ đọc và bảo trì. |
| `CALL (*) { ... }` | Tất cả biến đang nằm trong scope của truy vấn ngoài | Truy vấn nhỏ hoặc cần toàn bộ ngữ cảnh; cẩn thận khi câu truy vấn ngoài mở rộng. |
| `CALL () { ... }` | Không import biến nào từ ngoài | Truy vấn con độc lập với dữ liệu của hàng ngoài; nó **vẫn chạy cho mỗi hàng đầu vào**. |

**Import một hoặc nhiều biến:**

```cypher
WITH 4 AS price, 3 AS quantity, 'HN' AS region
CALL (price, quantity) {
  RETURN price * quantity AS total
}
RETURN region, price, quantity, total;
```

Kết quả: `region = 'HN'`, `price = 4`, `quantity = 3`, `total = 12`. `region` chỉ có ở truy vấn ngoài; không cần import để `RETURN` bên ngoài sử dụng.

**Import tất cả biến:**

```cypher
WITH 4 AS price, 3 AS quantity
CALL (*) {
  RETURN price * quantity AS total
}
RETURN total;
```

**Không import biến:**

```cypher
UNWIND ['A', 'B'] AS code
CALL () {
  RETURN 100 AS fixedValue
}
RETURN code, fixedValue
ORDER BY code;
```

Truy vấn con không sử dụng `code` nhưng vẫn được gọi hai lần: kết quả là `('A', 100)` và `('B', 100)`. `CALL ()` **không có nghĩa là chỉ thực thi một lần cho cả câu truy vấn**.

### Biến được import tồn tại xuyên suốt truy vấn con

Với scope clause, biến import có tính chất *global trong phạm vi truy vấn con*: một `WITH` thông thường ở giữa không loại bỏ khả năng tham chiếu biến đó.

```cypher
WITH 11 AS x
CALL (x) {
  UNWIND [2, 3] AS factor
  WITH factor
  RETURN x * factor AS product
}
RETURN x, product
ORDER BY product;
```

Kết quả là `(11, 22)` và `(11, 33)`, dù `WITH factor` không nhắc tới `x`.

Tuy nhiên, **không được đặt bí danh trong dấu ngoặc import**, cũng không được khai báo lại biến đã import:

```cypher
// SAI: scope clause chỉ nhận tên biến, không nhận alias
WITH 1 AS x
CALL (x AS renamed) {
  RETURN renamed AS value
}
RETURN value;
```

```cypher
// ĐÚNG: đặt alias ở outer query trước khi import
WITH 1 AS x
WITH x AS renamed
CALL (renamed) {
  RETURN renamed + 1 AS value
}
RETURN value;
```

Một biến có sẵn ở truy vấn ngoài cũng **không được trở thành tên cột mới** do truy vấn con trả về. Chẳng hạn, với `WITH 1 AS x`, viết `CALL (x) { RETURN x AS x }` sẽ gây xung đột tên. Giữ `x` ở ngoài rồi chỉ trả về cột mới `RETURN x + 1 AS nextX`.

## 4. Truyền biến bằng importing `WITH` — cú pháp cho phiên bản cũ

Trên Neo4j 4.4 và Neo4j 5.0–5.22, phần đầu của truy vấn con phải import biến bằng `WITH`. Ví dụ ở mục 1 được viết tương đương:

```cypher
UNWIND [1, 2, 3] AS n
CALL {
  WITH n
  RETURN n * n AS square
}
RETURN n, square
ORDER BY n;
```

Lưu ý: `WITH n` trong ví dụ là **importing WITH**, được nhận dạng vì đây là clause đầu tiên bên trong `CALL { ... }` (hoặc sau `USE` khi môi trường hỗ trợ). Nó có quy tắc chặt hơn `WITH` thông thường:

1. Chỉ được dùng **tham chiếu biến đơn giản**, ví dụ `WITH n` hoặc `WITH n, multiplier`.
2. Không viết biểu thức/đổi tên ngay tại importing `WITH`: `WITH n AS number` và `WITH n + 1 AS nextN` không hợp lệ trong vai trò này.
3. Không nối ngay `WHERE`, `ORDER BY`, `LIMIT`, `SKIP` hoặc `DISTINCT` vào importing `WITH`.
4. Nếu có nhiều nhánh `UNION` bên trong truy vấn con, **mỗi nhánh cần importing `WITH` riêng** nếu sử dụng biến bên ngoài.

Ví dụ **sai** với phiên bản cũ:

```cypher
UNWIND [1, 2, 3, 4] AS n
CALL {
  WITH n
  WHERE n > 2
  RETURN n * 10 AS value
}
RETURN n, value;
```

Cách sửa là dùng **hai `WITH` liên tiếp**; cái thứ nhất import, cái thứ hai mới lọc dữ liệu:

```cypher
UNWIND [1, 2, 3, 4] AS n
CALL {
  WITH n
  WITH n
  WHERE n > 2
  RETURN n * 10 AS value
}
RETURN n, value
ORDER BY n;
```

Kết quả chỉ có `n = 3` và `n = 4`. Các hàng `n = 1`, `n = 2` không được giữ lại, vì truy vấn con không trả hàng nào cho chúng.

Khi đã có Neo4j 5.23+, hãy thay hai `WITH` theo kiểu cũ bằng:

```cypher
UNWIND [1, 2, 3, 4] AS n
CALL (n) {
  WITH n
  WHERE n > 2
  RETURN n * 10 AS value
}
RETURN n, value
ORDER BY n;
```

Lúc này `WITH n` là `WITH` **thông thường**, không còn là importing `WITH`; vì vậy có thể dùng `WHERE`.

Một khác biệt đáng nhớ: với cú pháp cũ, các `WITH` tiếp theo **có thể loại biến import khỏi scope** theo quy tắc `WITH` thông thường. Với `CALL (n)` mới, `n` vẫn có thể được tham chiếu ở bất cứ phần nào bên trong truy vấn con.

## 5. Ví dụ property graph: lấy quan hệ theo từng node

Để thấy tại sao phạm vi biến quan trọng với **node**, **relationship** và truy vấn quan hệ, hãy dùng một đồ thị nhỏ:

```text
(An) ──KNOWS──> (Bình) ──KNOWS──> (Chi)

  └────────────KNOWS────────────> (Chi)

(Dũng)     [không có quan hệ KNOWS]
```

Tạo dữ liệu trong **database thử nghiệm**; `MERGE` giúp chạy lại ví dụ mà không cố ý thêm các node/relationship trùng cùng mẫu:

```cypher
MERGE (an:SubqueryDemoPerson {id: 'an'})
  SET an.name = 'An'
MERGE (binh:SubqueryDemoPerson {id: 'binh'})
  SET binh.name = 'Bình'
MERGE (chi:SubqueryDemoPerson {id: 'chi'})
  SET chi.name = 'Chi'
MERGE (dung:SubqueryDemoPerson {id: 'dung'})
  SET dung.name = 'Dũng'
WITH an, binh, chi
MERGE (an)-[:KNOWS]->(binh)
MERGE (an)-[:KNOWS]->(chi)
MERGE (binh)-[:KNOWS]->(chi);
```

### 5.1. Đếm số quan hệ của từng người, kể cả người có 0 quan hệ

```cypher
MATCH (p:SubqueryDemoPerson)
CALL (p) {
  OPTIONAL MATCH (p)-[:KNOWS]->(friend:SubqueryDemoPerson)
  RETURN count(friend) AS knownCount
}
RETURN p.name AS person, knownCount
ORDER BY knownCount DESC, person;
```

| person | knownCount |
|---|---:|
| An | 2 |
| Bình | 1 |
| Chi | 0 |
| Dũng | 0 |

`CALL (p)` đưa **node p** vào scope bên trong. `OPTIONAL MATCH` cho phép xử lý cả trường hợp không có quan hệ, và `count(friend)` đếm các giá trị khác `null`, nên `Chi` và `Dũng` có số đếm bằng 0.

Với Neo4j 4.4–5.22, thay phần mở đầu của subquery bằng:

```cypher
MATCH (p:SubqueryDemoPerson)
CALL {
  WITH p
  OPTIONAL MATCH (p)-[:KNOWS]->(friend:SubqueryDemoPerson)
  RETURN count(friend) AS knownCount
}
RETURN p.name AS person, knownCount
ORDER BY knownCount DESC, person;
```

### 5.2. Lấy tối đa một người quen cho **mỗi** người

```cypher
MATCH (p:SubqueryDemoPerson)
CALL (p) {
  MATCH (p)-[:KNOWS]->(friend:SubqueryDemoPerson)
  RETURN friend.name AS firstFriend
  ORDER BY firstFriend
  LIMIT 1
}
RETURN p.name AS person, firstFriend
ORDER BY person;
```

| person | firstFriend |
|---|---|
| An | Bình |
| Bình | Chi |

`LIMIT 1` ở **trong** subquery áp dụng cho **mỗi hàng `p`**. Nếu đặt `LIMIT 1` ở cuối câu truy vấn ngoài thì chỉ lấy một hàng cho **toàn bộ** kết quả, không phải một hàng cho mỗi người. `Chi` và `Dũng` biến mất ở đây vì `MATCH` trong subquery không tìm thấy hàng nào.

Từ **Neo4j 5.24+**, có thể giữ hai người này bằng `OPTIONAL CALL`:

```cypher
MATCH (p:SubqueryDemoPerson)
OPTIONAL CALL (p) {
  MATCH (p)-[:KNOWS]->(friend:SubqueryDemoPerson)
  RETURN friend.name AS firstFriend
  ORDER BY firstFriend
  LIMIT 1
}
RETURN p.name AS person, firstFriend
ORDER BY person;
```

`Chi` và `Dũng` sẽ xuất hiện với `firstFriend = null`. Đây là điểm giống `OPTIONAL MATCH`: khi subquery không tạo hàng nào, `OPTIONAL CALL` giữ hàng đầu vào và gán `null` cho các cột trả về của subquery.

Nếu phải tương thích với Neo4j cũ chưa có `OPTIONAL CALL`, một lựa chọn là trả về **một kết quả tổng hợp** cho từng người:

```cypher
MATCH (p:SubqueryDemoPerson)
CALL {
  WITH p
  OPTIONAL MATCH (p)-[:KNOWS]->(friend:SubqueryDemoPerson)
  WITH friend
  ORDER BY friend.name
  RETURN collect(friend.name)[0] AS firstFriend
}
RETURN p.name AS person, firstFriend
ORDER BY person;
```

Do `collect()` bỏ qua giá trị `null`, người không có quan hệ nhận `firstFriend = null`, và mỗi người vẫn có một hàng kết quả. Với số lượng bạn bè rất lớn, cách gom toàn bộ thành danh sách cần được cân nhắc về bộ nhớ; `OPTIONAL CALL` kết hợp `LIMIT` thường rõ nghĩa hơn trên phiên bản hỗ trợ.

### 5.3. `UNION` trong subquery và phạm vi import

Giả sử muốn lấy cả quan hệ `KNOWS` đi ra và đi vào đối với người tên `Chi`.

Ở Neo4j 5.23+, import `targetName` **một lần** cho toàn bộ subquery; mỗi nhánh `UNION ALL` đều dùng được biến đó:

```cypher
WITH 'Chi' AS targetName
CALL (targetName) {
  MATCH (a:SubqueryDemoPerson {name: targetName})-[:KNOWS]->(b)
  RETURN b.name AS otherPerson, 'outgoing' AS direction
  UNION ALL
  MATCH (a:SubqueryDemoPerson {name: targetName})<-[:KNOWS]-(b)
  RETURN b.name AS otherPerson, 'incoming' AS direction
}
RETURN targetName, otherPerson, direction
ORDER BY direction, otherPerson;
```

Kết quả: hai hàng `('Chi', 'An', 'incoming')` và `('Chi', 'Bình', 'incoming')`. Với Neo4j cũ dùng importing `WITH`, **mỗi nhánh cần import lại**:

```cypher
WITH 'Chi' AS targetName
CALL {
  WITH targetName
  MATCH (a:SubqueryDemoPerson {name: targetName})-[:KNOWS]->(b)
  RETURN b.name AS otherPerson, 'outgoing' AS direction
  UNION ALL
  WITH targetName
  MATCH (a:SubqueryDemoPerson {name: targetName})<-[:KNOWS]-(b)
  RETURN b.name AS otherPerson, 'incoming' AS direction
}
RETURN targetName, otherPerson, direction
ORDER BY direction, otherPerson;
```

Các nhánh `UNION` cần thống nhất **tên và số cột `RETURN`**. `UNION` mặc định loại kết quả trùng; `UNION ALL` giữ các hàng trùng, hữu ích nếu cần phản ánh đầy đủ các quan hệ.

## 6. Truy vấn con trả hàng và truy vấn con chỉ ghi dữ liệu

Có hai kiểu `CALL` subquery khác nhau về **số hàng** ở truy vấn ngoài:

| Kiểu | Bên trong subquery | Ảnh hưởng đến hàng ngoài |
|---|---|---|
| *Returning subquery* | Có `RETURN` | Có thể xuất 0, 1 hoặc nhiều hàng cho một hàng đầu vào. Nếu 0 hàng, hàng đầu vào bị loại (trừ khi dùng `OPTIONAL CALL` trên bản hỗ trợ). |
| *Unit subquery* | Không có `RETURN` | Thường dùng cho `CREATE`, `MERGE`, `SET`, `DELETE`; giữ nguyên số hàng của truy vấn ngoài. |

Ví dụ unit subquery: đánh dấu tất cả node thử nghiệm là đã kiểm tra.

```cypher
MATCH (p:SubqueryDemoPerson)
CALL (p) {
  SET p.checked = true
}
RETURN p.id AS processedId
ORDER BY processedId;
```

Phần `CALL` không trả cột mới; câu truy vấn ngoài vẫn có bốn hàng `an`, `binh`, `chi` và `dung`.

Đừng nhầm `CALL () { RETURN count(*) AS c }` với unit subquery. Dù có vẻ chỉ trả một giá trị, nó **vẫn là returning subquery**. Sự khác biệt nằm ở **có hay không có `RETURN`**, không phụ thuộc số lượng cột.

Một subquery trả về quá nhiều hàng sẽ nhân số lượng hàng ngoài. Nếu truy vấn ngoài đưa vào 100 node, và mỗi node có trung bình 20 quan hệ thỏa `MATCH` bên trong, kết quả có thể lên tới khoảng 2.000 hàng. Hãy dùng `LIMIT` theo nhóm, tổng hợp `count()` / `collect()` hoặc lọc sớm khi phù hợp.

## 7. Dùng `CALL ... IN TRANSACTIONS` cho xử lý theo lô

Khi nhập dữ liệu, tạo node hoặc cập nhật đồ thị với lượng hàng lớn, có thể thêm `IN TRANSACTIONS` sau subquery để Neo4j xử lý theo các **inner transaction** theo lô.

Ví dụ dành cho **Neo4j 5.23+**; thực hiện trên database thử nghiệm:

```cypher
UNWIND range(1, 2500) AS num
CALL (num) {
  MERGE (:SubqueryBatchDemo {id: num})
} IN TRANSACTIONS OF 500 ROWS
RETURN count(*) AS submittedRows;
```

Có 2.500 hàng đầu vào và kích thước lô là 500 hàng; thay đổi được commit dần theo các inner transaction. Với Neo4j 4.4–5.22, dùng cú pháp nhập biến cũ trong khối:

```cypher
UNWIND range(1, 2500) AS num
CALL {
  WITH num
  MERGE (:SubqueryBatchDemo {id: num})
} IN TRANSACTIONS OF 500 ROWS
RETURN count(*) AS submittedRows;
```

Cần chú ý:

- `CALL { ... } IN TRANSACTIONS` chỉ chạy trong **implicit/auto-commit transaction**, không chạy bên trong explicit transaction. Trong Neo4j Browser, dùng `:auto` trước câu truy vấn nếu Browser yêu cầu.
- Với Java Driver, không bọc câu lệnh này bằng managed transaction như `session.executeWrite(...)`; dùng cách thực thi cho **implicit transaction**, ví dụ `session.run(query, params)`, rồi tiêu thụ hết kết quả theo API Driver.
- Các lô đã commit trước đó có thể vẫn tồn tại khi một lô sau thất bại. Thiết kế logic có thể chạy lại an toàn, chẳng hạn `MERGE` theo khóa định danh phù hợp, và theo dõi lỗi.
- `IN TRANSACTIONS` giải quyết **ranh giới commit và kích thước lô**; nó không tự bảo đảm truy vấn nhanh nếu mỗi hàng phải quét toàn đồ thị. Với tìm kiếm theo `id`, hãy kiểm tra index/constraint phù hợp và kế hoạch `PROFILE`.

## 8. Những lỗi thường gặp khi nâng cấp và cách xử lý

| Hiện tượng | Nguyên nhân | Cách sửa |
|---|---|---|
| `Variable x not defined` bên trong `CALL` | Chưa import `x` hoặc đã mất scope ở cú pháp `WITH` cũ. | Neo4j 5.23+: `CALL (x)`; bản cũ: `CALL { WITH x ... }` và giữ `x` qua các `WITH` cần thiết. |
| Lỗi cú pháp ở `CALL (x)` | Máy chủ trước Neo4j 5.23. | Dùng importing `WITH` hoặc nâng cấp môi trường. |
| `Importing WITH ... WHERE is not allowed` | Gắn `WHERE` trực tiếp sau importing `WITH`. | Dùng `WITH x WITH x WHERE ...` ở bản cũ; ở bản mới dùng `CALL (x) { WITH x WHERE ... }`. |
| Lỗi ở `CALL (x AS alias)` | Scope clause không hỗ trợ alias hoặc biểu thức. | Đặt alias ở truy vấn ngoài, rồi import tên biến mới. |
| Xung đột tên biến trả về | `RETURN` trong subquery tạo tên đã có ở outer scope. | Đặt tên output khác, ví dụ `AS score`; biến outer vẫn sẵn có ở outer. |
| Mất người không có quan hệ | Returning subquery có `MATCH` trả 0 hàng. | Dùng `OPTIONAL CALL` (5.24+) hoặc truy vấn con tổng hợp có `OPTIONAL MATCH`. |
| Kết quả chỉ còn một người | Đặt `LIMIT 1` ở truy vấn ngoài thay vì trong subquery. | Đưa `ORDER BY ... LIMIT 1` vào trong `CALL (p) { ... }` để giới hạn **theo từng p**. |
| `Variable x not defined` ở nhánh `UNION` thứ hai | Cú pháp cũ chỉ import `x` trong nhánh thứ nhất. | Lặp `WITH x` ở từng nhánh; trên 5.23+ dùng `CALL (x)`. |
| Lỗi khi dùng `IN TRANSACTIONS` | Câu truy vấn được gọi trong explicit/managed transaction. | Thực thi bằng implicit transaction. |

Khi thấy thông báo *deprecated* về importing `WITH`, cần phân biệt **cảnh báo thay đổi tương lai** với **lỗi truy vấn hiện tại**. Đầu tiên xác định phiên bản Neo4j đang chạy; sau đó chuyển sang scope clause nếu môi trường cho phép.

## 9. Thiết kế truy vấn dễ bảo trì và hiệu quả

1. **Chỉ import những biến thực sự cần.** `CALL (person, maxResults)` thường dễ đọc hơn `CALL (*)` khi truy vấn ngoài chứa nhiều biến. Điều này làm rõ phụ thuộc và giảm rủi ro do bổ sung biến trong tương lai.
2. **Lọc ở nơi phù hợp.** Để lấy top N quan hệ **cho mỗi node**, đặt `ORDER BY` và `LIMIT` bên trong subquery; để giới hạn N node **trên toàn bộ kết quả**, đặt `LIMIT` ngoài.
3. **Nhìn số hàng trước và sau `CALL`.** Với subquery trả nhiều hàng, chi phí có thể tăng mạnh theo số lượng node/relationship. Dùng `EXPLAIN` hoặc `PROFILE` để kiểm tra `Apply`/các operator liên quan và số hàng thực tế.
4. **Dùng index cho điểm neo của truy vấn.** Nếu mỗi lần gọi phải tìm node bằng `id` hoặc khóa nghiệp vụ, index/constraint phù hợp có thể quan trọng hơn việc đổi giữa `CALL (x)` và `CALL (*)`.
5. **Nhận diện khi không cần `CALL`.** `EXISTS { ... }` dùng để kiểm tra sự tồn tại, `COUNT { ... }` để đếm, `COLLECT { ... }` để trả danh sách theo biểu thức; chúng có ngữ nghĩa và quy tắc scope riêng. Dùng `CALL` khi cần trả nhiều cột/hàng, xử lý riêng từng hàng, `UNION` hoặc thực hiện cập nhật.
6. **Cẩn trọng với thứ tự xử lý.** Thứ tự các hàng được đưa vào `CALL` không tự được bảo đảm. Nếu logic ghi phụ thuộc thứ tự, hãy chủ động `ORDER BY` ngay trước `CALL`. Các lần chạy subquery sau có thể quan sát thay đổi do lần trước thực hiện.

### Nhìn nhanh: chọn cú pháp nào?

```text
Máy chủ < Neo4j 5.23?
    Có  -> CALL { WITH x ... }
    Không
      |
      +-- Cần import biến ngoài? -> CALL (x, y) { ... }
      +-- Không cần?             -> CALL () { ... }
      +-- Cần toàn bộ?           -> CALL (*) { ... }  [dùng có chủ đích]
      |
      +-- Cần giữ hàng khi không khớp?
              Có và >= 5.24     -> OPTIONAL CALL (x) { ... }
              Bản cũ            -> OPTIONAL MATCH / aggregate để trả 1 hàng
```

## 10. Tóm tắt ghi nhớ

- `CALL` subquery được thực thi **cho từng hàng đầu vào**, và chỉ sử dụng biến ngoài khi được **import tường minh**.
- Cú pháp cũ: `CALL { WITH x ... }`. Cú pháp nên dùng từ Neo4j 5.23: `CALL (x) { ... }`, `CALL () { ... }` hoặc `CALL (*) { ... }`.
- Importing `WITH` có hạn chế riêng; trong `UNION` cũ phải import ở **từng nhánh**. Scope clause mới áp dụng cho **toàn bộ** subquery và giữ biến import luôn nhìn thấy bên trong.
- Returning subquery có thể làm thay đổi số hàng; unit subquery không làm thay đổi số hàng ngoài. `OPTIONAL CALL` (5.24+) giúp giữ hàng khi không có kết quả.
- Từ Neo4j 2025.06, cần hiểu thêm lựa chọn **Cypher 5 / Cypher 25**, bên cạnh phiên bản máy chủ.

## Tài liệu tham khảo

- [Neo4j Cypher Manual — CALL subqueries](https://neo4j.com/docs/cypher-manual/current/subqueries/call-subquery/) — cơ chế per-row, scope clause, importing `WITH`, unit/returning subquery và `OPTIONAL CALL`.
- [Neo4j Cypher Manual 4.4 — CALL subqueries](https://neo4j.com/docs/cypher-manual/4.4/clauses/call-subquery/) — cú pháp lịch sử phù hợp với môi trường cũ.
- [Neo4j Cypher Manual 5 — Additions/deprecations](https://neo4j.com/docs/cypher-manual/5/deprecations-additions-removals-compatibility/) — mốc 5.23 (scope clause) và 5.24 (`OPTIONAL CALL`).
- [Neo4j Cypher Manual — Select Cypher version](https://neo4j.com/docs/cypher-manual/current/queries/select-version/) — phân biệt Cypher 5/Cypher 25 từ Neo4j 2025.06.
- [Neo4j Cypher Manual — CALL subqueries in transactions](https://neo4j.com/docs/cypher-manual/current/subqueries/subqueries-in-transactions/) — xử lý theo lô và ràng buộc implicit transaction.
