# Thực thi theo lô với `CALL { ... } IN TRANSACTIONS` và điều kiện sử dụng

## 1. Vì sao cần chia một truy vấn Cypher thành nhiều giao dịch?

Neo4j lưu dữ liệu theo **property graph**: node biểu diễn thực thể, relationship biểu diễn liên kết và cả hai có thể mang thuộc tính. Khi nhập hàng triệu người dùng, doanh nghiệp hoặc quan hệ giữa chúng, một truy vấn ghi duy nhất có thể giữ nhiều thay đổi, khóa và trạng thái giao dịch trong thời gian dài. Nếu toàn bộ thao tác nằm trong **một transaction**, lỗi gần cuối có thể buộc hệ thống hoàn tác tất cả thay đổi của transaction đó.

`CALL { ... } IN TRANSACTIONS` là cơ chế Cypher để **chia các dòng đầu vào của truy vấn con thành những lô nhỏ và thực thi từng lô trong một transaction riêng**. Cơ chế này hữu ích khi:

- Nhập dữ liệu từ `LOAD CSV` vào node và relationship.
- Cập nhật hoặc chuẩn hóa một tập dữ liệu đồ thị lớn.
- Xử lý độc lập từng nhóm bản ghi mà có thể chấp nhận kết quả được commit từng phần.

Ví dụ, với 2.500 dòng đầu vào và kích thước lô 1.000:

```text
2.500 dòng đầu vào
  ├── Dòng    1–1.000 → Transaction 1 → COMMIT
  ├── Dòng 1.001–2.000 → Transaction 2 → COMMIT
  └── Dòng 2.001–2.500 → Transaction 3 → COMMIT
```

**Điểm cốt lõi:** `OF 1000 ROWS` đếm **dòng đầu vào chuyển vào subquery**, không phải số node, relationship hoặc câu lệnh `MERGE` được thực hiện. Một dòng có thể làm thay đổi nhiều thực thể đồ thị.

## 2. Cú pháp và cách thực thi

### 2.1. Cú pháp khuyến nghị trên Cypher 5.23 trở lên

```cypher
UNWIND range(1, 2500) AS itemId
CALL (itemId) {
  MERGE (:ImportedItem {id: itemId})
} IN TRANSACTIONS OF 1000 ROWS;
```

Trình tự xử lý:

1. `UNWIND` tạo ra 2.500 dòng; mỗi dòng có biến `itemId`.
2. `CALL (itemId)` khai báo rõ biến từ truy vấn ngoài được đưa vào truy vấn con.
3. Phần thân `{ MERGE ... }` chạy với mỗi dòng trong lô.
4. Neo4j commit các thay đổi theo lô 1.000 dòng; lô cuối có 500 dòng.

Từ Cypher 5.23, **variable scope clause** `CALL (itemId)` là cách nhập biến được ưu tiên. `CALL ()` dùng khi không cần biến nào từ truy vấn ngoài; `CALL (*)` nhập mọi biến đang nằm trong phạm vi, nên chỉ dùng khi thực sự cần.

### 2.2. Cú pháp `CALL { ... }` trên phiên bản cũ

Trước khi có variable scope clause, biến được đưa vào truy vấn con qua `WITH` ở đầu subquery:

```cypher
UNWIND range(1, 2500) AS itemId
CALL {
  WITH itemId
  MERGE (:ImportedItem {id: itemId})
} IN TRANSACTIONS OF 1000 ROWS;
```

Hai cách trên minh họa cùng nguyên tắc phân lô. **Importing `WITH` là cú pháp cũ và đã được đánh dấu deprecated từ Cypher 5.23**; khi viết truy vấn mới cho phiên bản hỗ trợ, ưu tiên `CALL (itemId) { ... }`.

Nếu bỏ `OF n ROWS`, kích thước lô mặc định là **1.000 dòng**. Có thể ghi rõ `IN TRANSACTIONS OF 500 ROWS` hoặc `IN TRANSACTIONS OF 2000 ROWS` để người đọc và người vận hành thấy chủ ý phân lô.

### 2.3. Khác biệt với truy vấn con thông thường

| Cách viết | Ranh giới transaction | Phù hợp |
| --- | --- | --- |
| `CALL { ... }` hoặc `CALL (x) { ... }` không có `IN TRANSACTIONS` | Thực thi trong transaction của truy vấn bao quanh | Truy vấn con dùng để tính toán, lọc, tổng hợp hoặc ghi cần cùng tính nguyên tử |
| `CALL { ... } IN TRANSACTIONS` hoặc `CALL (x) { ... } IN TRANSACTIONS` | Mỗi lô đầu vào chạy trong transaction riêng | Nhập/cập nhật dữ liệu lớn, chấp nhận commit từng phần |
| `UNWIND` kết hợp `MERGE` nhưng không dùng `IN TRANSACTIONS` | Không tự tạo ranh giới transaction giữa các dòng | Tác vụ vừa/nhỏ cần một transaction |

Chỉ dùng `UNWIND` hoặc `WITH ... LIMIT` **không đồng nghĩa** với việc Neo4j tự commit theo lô.

## 3. Ví dụ thực tế: nhập người dùng và quan hệ với doanh nghiệp

Giả sử tệp `users-companies.csv` có dữ liệu:

```csv
userId,userName,companyId,companyName
u001,An,c001,Acme
u002,Binh,c001,Acme
u003,Chi,c002,Northwind
```

Mục tiêu: tạo node `User`, node `Company` và relationship `MEMBER_OF` giữa chúng. Trước khi nhập, tạo constraint để giữ duy nhất khóa định danh và hỗ trợ truy cập bằng khóa:

```cypher
CREATE CONSTRAINT user_id_unique IF NOT EXISTS
FOR (u:User) REQUIRE u.id IS UNIQUE;

CREATE CONSTRAINT company_id_unique IF NOT EXISTS
FOR (c:Company) REQUIRE c.id IS UNIQUE;
```

Các lệnh tạo constraint được thực thi riêng trước câu lệnh nhập dữ liệu. Trên Cypher 5.23 trở lên:

```cypher
LOAD CSV WITH HEADERS FROM 'file:///users-companies.csv' AS row
WITH row
WHERE row.userId IS NOT NULL
  AND trim(row.userId) <> ''
  AND row.companyId IS NOT NULL
  AND trim(row.companyId) <> ''
CALL (row) {
  MERGE (u:User {id: row.userId})
  SET u.name = row.userName

  MERGE (c:Company {id: row.companyId})
  SET c.name = row.companyName

  MERGE (u)-[:MEMBER_OF]->(c)
} IN TRANSACTIONS OF 1000 ROWS;
```

Giải thích:

- `LOAD CSV WITH HEADERS` đưa từng dòng CSV vào biến `row`; điều kiện `WHERE` bỏ các dòng thiếu khóa chính trước khi chia lô.
- `MERGE` tìm node theo khóa `id`; nếu không tồn tại thì tạo mới. Constraint duy nhất giúp tránh sinh nhiều node có cùng `id`, kể cả khi import lại.
- `SET` cập nhật tên khi nguồn dữ liệu thay đổi. `MERGE (u)-[:MEMBER_OF]->(c)` tránh tạo lặp relationship có cùng kiểu và hai đầu mút trong cách mô hình hóa này.
- `IN TRANSACTIONS OF 1000 ROWS` đưa tối đa 1.000 dòng hợp lệ vào mỗi transaction. Đây là kích thước lô của **dòng CSV đã qua lọc**, không phải 1.000 node.

Đường dẫn `file:///` thường trỏ tới thư mục import mà máy chủ Neo4j được phép đọc, **không phải đường dẫn trên máy chạy ứng dụng Java**. Với dịch vụ không cho đọc tệp cục bộ, cần dùng một URL dữ liệu được cấu hình và cho phép truy cập.

Sau khi nhập, có thể kiểm tra:

```cypher
MATCH (u:User)-[:MEMBER_OF]->(c:Company)
RETURN c.id AS companyId, c.name AS companyName, count(u) AS members
ORDER BY members DESC;
```

Với CSV mẫu, `Acme` có 2 người dùng và `Northwind` có 1 người dùng.

## 4. Ví dụ cập nhật tập node lớn

Không nhất thiết phải dùng `LOAD CSV`. Truy vấn ngoài có thể chọn node đã tồn tại rồi chuyển khóa định danh vào subquery:

```cypher
MATCH (u:User)
WHERE u.needsReview = true
WITH u.id AS userId
CALL (userId) {
  MATCH (u:User {id: userId})
  SET u.reviewStatus = 'PENDING',
      u.needsReview = false
} IN TRANSACTIONS OF 500 ROWS;
```

Ở đây, truy vấn ngoài chọn người dùng cần cập nhật; truy vấn con tìm lại node bằng khóa và ghi theo từng nhóm 500 dòng. Cần có index/constraint thích hợp trên `User.id` để tránh quét toàn bộ graph trong mỗi lần tìm node.

Không nên tạo một danh sách khổng lồ bằng `collect(...)` trước `CALL` chỉ để chia lô: `collect` có thể làm tăng bộ nhớ và mất lợi thế xử lý luồng dòng đầu vào.

## 5. Xử lý lỗi, rollback và chạy lại

### 5.1. Một lô lỗi ảnh hưởng tới những gì?

Mỗi lô là một transaction. Nếu lô 3 gặp lỗi, các thay đổi thuộc **lô 3 bị rollback**; những lô trước đó đã commit **không tự động bị rollback theo**. Đây là điểm khác biệt quyết định so với việc ghi toàn bộ dữ liệu trong một transaction.

Mặc định, lỗi làm truy vấn dừng và báo lỗi. Trên phiên bản Neo4j hỗ trợ các tùy chọn này, có thể điều chỉnh bằng `ON ERROR`:

| Chế độ | Khi một lô bị lỗi | Tác động cần lưu ý |
| --- | --- | --- |
| `ON ERROR FAIL` (mặc định) | Dừng và báo lỗi | Các lô đã commit vẫn tồn tại |
| `ON ERROR CONTINUE` | Rollback lô lỗi và thử xử lý các lô tiếp theo | Có thể bỏ sót cả những dòng hợp lệ nằm trong lô lỗi |
| `ON ERROR BREAK` | Rollback lô lỗi và không xử lý các lô còn lại | Cho phép ngừng các lần ghi tiếp theo tại lô lỗi |

Ví dụ minh họa báo trạng thái theo lô:

```cypher
UNWIND [
  {id: 'u101'},
  {id: null},
  {id: 'u103'},
  {id: 'u104'}
] AS row
CALL (row) {
  MERGE (:ImportDemo {id: row.id})
} IN TRANSACTIONS OF 2 ROWS
  ON ERROR CONTINUE
  REPORT STATUS AS batchStatus
RETURN row.id AS inputId, batchStatus;
```

Trong ví dụ này, `MERGE` không thể dùng giá trị `id: null`. Vì hai dòng đầu thuộc cùng một lô, **cả lô đầu bị rollback**, kể cả thay đổi cho `u101`. Chế độ `CONTINUE` cho phép lô sau (`u103`, `u104`) tiếp tục. `REPORT STATUS AS batchStatus` cung cấp thông tin trạng thái để ứng dụng kiểm tra các lô thành công/thất bại; cú pháp và trường thông tin chi tiết có thể khác nhau theo phiên bản.

**Không dùng `ON ERROR CONTINUE` để che lỗi dữ liệu.** Hãy log kết quả, đối soát số dòng hợp lệ, số dòng được xử lý và số dòng bị bỏ qua. Nếu lỗi chỉ nằm ở một dòng, việc retry với lô nhỏ hơn hoặc sửa CSV giúp tránh làm mất cả lô.

### 5.2. Thiết kế để chạy lại an toàn

Vì dữ liệu có thể đã commit một phần, lần nhập tiếp theo phải cân nhắc tính **idempotent** (chạy lại không tạo dữ liệu trùng):

- Dùng `MERGE` theo khóa nghiệp vụ ổn định; tạo uniqueness constraint phù hợp.
- Định nghĩa rõ quan hệ nào được coi là trùng; `CREATE` relationship vô điều kiện có thể nhân đôi liên kết khi retry.
- Phân biệt lỗi dữ liệu nguồn (thiếu khóa, sai kiểu) với lỗi vận hành (timeout, tranh chấp khóa, mất kết nối).
- Kiểm tra kết quả sau mỗi lần chạy bằng truy vấn đếm và đối soát dữ liệu nguồn, không chỉ dựa vào thông báo truy vấn đã kết thúc.

Nếu yêu cầu nghiệp vụ là **thành công tất cả hoặc rollback tất cả**, hãy dùng một transaction thông thường với khối lượng phù hợp, hoặc thiết kế quy trình staging/xác nhận riêng. Không lựa chọn `IN TRANSACTIONS` cho yêu cầu nguyên tử toàn cục.

## 6. Điều kiện thực thi và tích hợp Java

### 6.1. Bắt buộc chạy trong implicit transaction

Truy vấn dùng `CALL { ... } IN TRANSACTIONS` phải được gửi dưới dạng **implicit transaction (auto-commit)**. Không đặt nó bên trong explicit/managed transaction đã mở trước.

| Môi trường | Cách dùng |
| --- | --- |
| Neo4j Browser | Dùng tiền tố `:auto` khi Browser yêu cầu truy vấn chạy ở auto-commit |
| Neo4j Java Driver | Dùng `Session.run(query)` và consume kết quả để đảm bảo truy vấn đã hoàn tất |
| Java Driver `session.executeWrite(...)` / `Transaction.run(...)` | Không phù hợp vì bao truy vấn trong managed/explicit transaction |
| Spring Data Neo4j có `@Transactional` | Không gọi truy vấn phân lô trong transaction do Spring quản lý; chọn luồng thực thi auto-commit phù hợp và xem xét transaction boundary của tầng ứng dụng |

Ví dụ Java Driver (giả sử đã có đối tượng `driver` và quyền truy cập CSV từ máy chủ Neo4j):

```java
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

String cypher = """
    LOAD CSV WITH HEADERS FROM 'file:///users-companies.csv' AS row
    WITH row
    WHERE row.userId IS NOT NULL AND trim(row.userId) <> ''
    CALL (row) {
      MERGE (u:User {id: row.userId})
      SET u.name = row.userName
    } IN TRANSACTIONS OF 1000 ROWS
    """;

try (Session session = driver.session(
        SessionConfig.forDatabase("neo4j"))) {
    session.run(cypher).consume();
}
```

`Session.run(...)` gửi truy vấn dưới dạng implicit transaction. Lệnh `consume()` đảm bảo driver nhận hết kết quả và phần tổng kết thực thi, giúp phát hiện lỗi trước khi thoát khỏi khối `try`. Đừng bọc đoạn mã này trong `executeWrite` chỉ vì truy vấn có `MERGE`: thao tác phân lô tự quản lý các transaction bên trong.

### 6.2. Chọn kích thước lô

Không có một kích thước lô tối ưu cho mọi graph:

| Lô | Lợi ích | Rủi ro |
| --- | --- | --- |
| Nhỏ (ví dụ 100–500 dòng) | Ít dữ liệu cần rollback, chiếm ít tài nguyên mỗi transaction | Tốn chi phí mở/commit nhiều transaction |
| Trung bình (ví dụ 1.000 dòng) | Điểm bắt đầu hợp lý cho nhiều bài toán nhập dữ liệu | Vẫn phải đo theo số thao tác thực tế của mỗi dòng |
| Lớn (ví dụ 5.000–10.000 dòng) | Ít lần commit hơn | Có thể tăng bộ nhớ, thời gian giữ khóa, chi phí rollback và tranh chấp |

Hãy bắt đầu bằng lô vừa phải, đo thời gian xử lý, tải bộ nhớ, thời gian chờ khóa và mức ổn định. Khi mỗi dòng tạo nhiều node/relationship hoặc ghi tới các node được chia sẻ bởi nhiều dòng, kích thước lô có thể cần nhỏ hơn. Đừng tăng kích thước chỉ vì số transaction giảm.

### 6.3. Những điều kiện nên kiểm tra trước khi chạy

1. **Tính độc lập:** các lô có thể commit độc lập và thứ tự hoàn thành phù hợp với nghiệp vụ.
2. **Khả năng retry:** có khóa định danh và quy tắc `MERGE` để tránh trùng dữ liệu.
3. **Dữ liệu đầu vào:** lọc/null-check các khóa bắt buộc, chuyển kiểu dữ liệu nếu cần và bảo đảm máy chủ truy cập được nguồn.
4. **Index/constraint:** các thao tác tìm hoặc `MERGE` theo khóa có index/uniqueness constraint phù hợp.
5. **Ngữ cảnh transaction:** client thực sự chạy implicit transaction; không có `@Transactional` hoặc `executeWrite` bao ngoài.
6. **Khả năng quan sát:** có cách đếm số dòng thành công/thất bại, theo dõi log và đối soát sau khi nạp.

## 7. Sai lầm thường gặp

**Nhầm phân lô với tính nguyên tử toàn bộ.** Transaction đã commit ở lô trước không được hoàn tác khi lô sau thất bại. Quy trình cần all-or-nothing không phù hợp với cách thực thi này.

**Truyền truy vấn vào managed transaction.** `CALL ... IN TRANSACTIONS` tự tạo transaction cho từng lô; Java Driver hoặc Spring mở explicit transaction bao ngoài sẽ gây lỗi. Cần thực thi ở chế độ auto-commit.

**Không xác định biến nhập vào subquery.** Với cú pháp mới, chỉ rõ `CALL (row) { ... }` để dùng `row` ở phần thân. Với cú pháp cũ, dùng `WITH row` ở đầu khối `CALL { ... }`.

**Thiếu constraint và chạy lại bằng `CREATE`.** Khi lô cuối lỗi, dữ liệu đã commit có thể tồn tại. Retry bằng `CREATE` có nguy cơ sinh node/relationship trùng; thiết kế khóa và `MERGE` ngay từ đầu.

**Xem 1.000 dòng là 1.000 thao tác ghi.** Một dòng có thể tạo/cập nhật nhiều node và relationship; kích thước transaction phụ thuộc công việc thực tế trong subquery.

**Lẫn lộn `LIMIT` với commit.** Việc giới hạn hoặc nhóm dòng ở tầng truy vấn không tự sinh transaction mới; chỉ `IN TRANSACTIONS` mới tạo ranh giới commit như minh họa ở đây.

## 8. Ghi nhớ

`CALL { ... } IN TRANSACTIONS` giúp Neo4j xử lý lượng lớn dữ liệu liên kết bằng **nhiều transaction nhỏ**, giảm khối lượng thay đổi của từng lần commit. Đổi lại, hệ thống có thể có **kết quả một phần** khi lỗi xảy ra, nên cần xử lý lỗi, đối soát và retry an toàn. Trên Cypher 5.23+, ưu tiên `CALL (biến) { ... } IN TRANSACTIONS OF n ROWS`; khi tích hợp qua Java Driver hoặc Spring Data Neo4j, điều kiện đặc biệt quan trọng là **gửi truy vấn bằng implicit transaction**.
