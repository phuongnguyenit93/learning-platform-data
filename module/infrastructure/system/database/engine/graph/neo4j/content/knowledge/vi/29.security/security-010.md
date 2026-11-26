# Rà soát quyền tối thiểu và thử nghiệm các tình huống truy cập bị từ chối

Trong Neo4j, một dịch vụ có thể cần đọc node `:Order` và relationship `:PLACED`, nhưng **không nên** vì thế mà được quyền xem lương nhân viên, xóa toàn bộ đồ thị hoặc quản trị tài khoản. **Nguyên tắc quyền tối thiểu (least privilege)** yêu cầu mỗi danh tính chỉ có những quyền cần thiết cho đúng tác vụ, đúng database, đúng đối tượng đồ thị và đúng thời điểm.

Bài thuộc chương **Bảo mật** của module `DATABASE_ENGINE_GRAPH_NEO4J`. Module dùng Neo4j để mô hình hóa property graph, truy vấn Cypher, tạo index/constraint, nhập dữ liệu và kết nối qua Java Driver hoặc Spring Data Neo4j (SDN). Bảo mật phải được kiểm chứng trên **các truy vấn và giao dịch thực sự do những ứng dụng đó chạy**: quyền đọc dữ liệu, quyền ghi, quyền thực thi procedure và khả năng nhìn thấy các label/property nhạy cảm.

Chỉ đọc bảng phân quyền là chưa đủ. Kiểm thử phải chứng minh đồng thời:

- **Được phép:** tác vụ nghiệp vụ hợp lệ vẫn đọc/ghi đúng kết quả.
- **Bị từ chối:** thao tác không được cấp quyền không thể thực hiện.
- **Không rò dữ liệu:** thuộc tính hoặc node bị che khuất không xuất hiện trong kết quả, kể cả khi truy vấn không báo lỗi.
- **Không có tác dụng phụ:** sau truy cập bị từ chối, dữ liệu quan trọng vẫn giữ nguyên.

> **Phạm vi:** Ví dụ quyền chi tiết trong bài dựa trên **Neo4j Enterprise Edition 5.x** có hỗ trợ role-based access control (RBAC) và fine-grained graph privileges. Neo4j Community Edition không cung cấp đầy đủ cùng cơ chế vai trò/quyền chi tiết; Neo4j Aura còn phụ thuộc gói dịch vụ và chính sách quản trị. Hãy đối chiếu tài liệu **đúng phiên bản, edition và môi trường** trước khi triển khai. Chỉ chạy lệnh quản trị tài khoản và các test cố ý bị từ chối trên **database thực hành cô lập**.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Liệt kê quyền cần thiết cho một đường đi nghiệp vụ từ **API → Java Driver/SDN → Cypher → graph**.
2. Phân biệt `ACCESS` trên database, `TRAVERSE` đối với node/relationship, `READ` thuộc tính, `MATCH`, quyền ghi và quyền thực thi procedure.
3. Rà soát **quyền hiệu lực** sau khi tính nhiều role, role `PUBLIC` và các quy tắc `GRANT`/`DENY`.
4. Phân biệt **permission error** với kết quả **rỗng/`null` do dữ liệu bị ẩn**.
5. Viết ma trận **positive test** và **negative test**, kiểm tra dữ liệu trước/sau thao tác ghi bị từ chối.
6. Kiểm thử thật qua Java Driver với **hai danh tính khác nhau** và cảnh báo các rủi ro về tài khoản, log, tham số Cypher, APOC và thay đổi quyền theo thời gian.

## 2. Quyền tối thiểu là thuộc tính của *danh tính thực thi*

Một ứng dụng Spring Data Neo4j có thể sử dụng repository tên `OrderRepository`, nhưng Neo4j **không quyết định quyền dựa trên tên class**. Quyết định truy cập dựa vào **danh tính đã xác thực**, database được chọn và các role/quyền hiệu lực của danh tính đó.

~~~mermaid
flowchart LR
    API["REST API / Scheduled job"] --> APP["Service + Java Driver / SDN"]
    APP --> CRED["Neo4j identity"]
    CRED --> ROLES["Các role được gán<br/>kể cả PUBLIC"]
    ROLES --> POLICY["GRANT / DENY<br/>theo DB, node, relationship, property"]
    POLICY --> Q["Cypher / procedure"]
    Q --> DATA["Dữ liệu được nhìn thấy<br/>hoặc thao tác được phép"]
~~~

**Những câu hỏi cần trả lời trước khi cấp quyền:**

| Câu hỏi | Ví dụ |
|---|---|
| **Ai** chạy truy vấn? | `order-api-reader`, `order-api-writer`, `schema-migrator` |
| **Ở database nào?** | Chỉ database `neo4j` của môi trường kiểm thử, không phải mọi database |
| **Đối tượng nào?** | Node `:SecCustomer`, `:SecOrder`, relationship `:PLACED` |
| **Thuộc tính nào?** | `customerId`, `orderId`, `amount`; không gồm `email`, `internalNote` |
| **Hành động nào?** | Đọc đường liên kết, đọc vài property, hay sửa trạng thái đơn hàng? |
| **Có cần procedure/admin?** | Service đọc đơn thường không cần tạo user, xóa database hoặc gọi plugin truy cập file |
| **Khi nào thu hồi?** | Khi chức năng bị ngừng, chuyển service hoặc hết thời gian triển khai |

Không dùng chung tài khoản `neo4j`/admin cho mọi microservice. Một tài khoản có quyền quá rộng khiến lỗi ứng dụng, Cypher injection hoặc thông tin xác thực bị lộ có thể tác động đến dữ liệu ngoài phạm vi nghiệp vụ.

### Các lớp bảo vệ không thay thế nhau

- **Authentication:** xác thực người đang kết nối; mật khẩu/token/certificate sai có thể gây lỗi trước khi chạy Cypher.
- **Authorization:** quyết định danh tính đó được đọc, ghi hoặc quản trị gì. Đăng nhập thành công **không có nghĩa** được phép gọi mọi lệnh.
- **Schema constraint:** bảo đảm tính duy nhất hoặc kiểu dữ liệu, nhưng **không phải** cơ chế hạn chế người dùng được xem thuộc tính.
- **Validation ở ứng dụng:** quyết định thao tác có hợp lệ theo nghiệp vụ, nhưng **không thay được** quyền Neo4j ở tầng database.
- **Kết nối bảo mật/TLS:** bảo vệ kênh truyền; không thay thế RBAC.

## 3. Các loại quyền Neo4j phải phân biệt

Neo4j có quyền ở nhiều phạm vi. Ví dụ sau dùng **Enterprise RBAC** và một database có tên `neo4j`.

| Nhóm | Ý nghĩa thực tế | Nếu thiếu thì sao? |
|---|---|---|
| `ACCESS ON DATABASE` | Cho phép danh tính truy cập database đã chọn | Có thể không chọn hoặc chạy truy vấn trên DB đó |
| `TRAVERSE ON GRAPH ... NODES ...` | Cho phép đi qua/nhìn thấy node theo label | Node có thể **không xuất hiện** trong kết quả |
| `TRAVERSE ON GRAPH ... RELATIONSHIPS ...` | Cho phép duyệt relationship theo type | Pattern `MATCH` có thể không tìm thấy đường đi |
| `READ {property} ON GRAPH ...` | Cho phép đọc những property được cấp | Property bị che có thể trả `null` |
| `MATCH {property} ON GRAPH ...` | Thuận tiện cho quyền `TRAVERSE` cộng quyền `READ` tương ứng | Chỉ thấy node/relationship và property được cho phép |
| `WRITE` hoặc quyền ghi chi tiết | Cho phép tạo/xóa node/relationship, gán property theo phạm vi | Ghi không được phép sẽ bị từ chối |
| `EXECUTE PROCEDURE` / `EXECUTE FUNCTION` | Cho phép gọi function/procedure ở cấp DBMS | Có thể bị từ chối khi gọi chức năng yêu cầu quyền |
| `EXECUTE BOOSTED PROCEDURE` | Cho procedure chạy với quyền nâng cao theo cấu hình | Không cấp tràn lan; tăng rủi ro vượt phạm vi tác vụ |
| Quyền quản trị DBMS/database | Tạo user, role, database, quản lý đặc quyền, ... | Service nghiệp vụ thường **không cần** |

`GRANT MATCH {orderId, amount} ON GRAPH neo4j NODES SecOrder TO some_role` là một cách cấp quyền **đọc và duyệt** node `SecOrder` theo tập property được chỉ định. Điều đó **không cấp quyền ghi**.

Một lưu ý rất quan trọng về kiểm thử quyền:

> **Không có quyền đọc ≠ mọi lần đều ném exception.** Khi không có quyền `TRAVERSE`, `MATCH` có thể trả **0 hàng** dù admin nhìn thấy node. Khi không được `READ` một property, biểu thức `n.secret` có thể trả **`null`**. Ngược lại, lệnh ghi, truy cập database hoặc gọi procedure không được phép thường báo lỗi quyền. Bài test phải kiểm tra **đúng ngữ nghĩa thực tế** cho từng tình huống.

### Role, `PUBLIC` và `DENY`

Một user có thể mang **nhiều role**. Quyền `GRANT` từ các role có thể cộng gộp; một `DENY` thích hợp thường **có ưu tiên** trước `GRANT` xung đột theo quy tắc authorization của Neo4j. Role **`PUBLIC`** áp dụng cho mọi người dùng và có thể mang quyền mặc định; **đừng chỉ xem role do nhóm tự tạo** rồi kết luận user không có quyền khác.

Ví dụ, nếu `order_reader` chỉ cấp đọc `orderId` nhưng một role khác của cùng user cho phép đọc mọi property, phép thử với user đó có thể nhìn thấy nhiều dữ liệu hơn dự kiến. Kiểm tra **quyền hiệu lực của user** thay vì chỉ đọc một lệnh `GRANT` trong script triển khai.

## 4. Định nghĩa kịch bản kiểm thử

Giả sử ứng dụng **Order API** có hai loại danh tính:

- `qa_order_reader`: đọc mã khách hàng, mã đơn và số tiền; **không** được đọc email/internal note, sửa đơn hoặc xem dữ liệu lương.
- `qa_order_writer`: một danh tính riêng phục vụ nghiệp vụ ghi theo quy tắc cụ thể; không mặc nhiên có quyền quản trị schema/người dùng.

Trong bài tập, ta tập trung kiểm chứng `qa_order_reader`. Dữ liệu đồ thị dự kiến:

~~~mermaid
flowchart LR
    C["SecCustomer<br/>customerId=C01<br/>email=an@example.test"]
    O["SecOrder<br/>orderId=O01<br/>amount=120000<br/>internalNote=VIP"]
    P["SecPayroll<br/>payrollId=P01<br/>salary=45000000"]
    C -->|PLACED| O
    P -.->|"Không thuộc quyền Order API"| P
~~~

Chỉ chạy phần chuẩn bị dưới đây **với tài khoản quản trị trong database thử nghiệm**:

~~~cypher
// Chạy trên database neo4j của môi trường kiểm thử.
MERGE (c:SecCustomer {customerId: 'C01'})
SET c.email = 'an@example.test',
    c.name = 'An'
MERGE (o:SecOrder {orderId: 'O01'})
SET o.amount = 120000,
    o.internalNote = 'VIP'
MERGE (c)-[:PLACED]->(o)
MERGE (p:SecPayroll {payrollId: 'P01'})
SET p.salary = 45000000;
~~~

Kiểm tra bằng tài khoản **admin** để bảo đảm fixture thực sự tồn tại:

~~~cypher
MATCH (c:SecCustomer {customerId: 'C01'})-[:PLACED]->
      (o:SecOrder {orderId: 'O01'})
MATCH (p:SecPayroll {payrollId: 'P01'})
RETURN c.email AS email,
       o.amount AS amount,
       o.internalNote AS internalNote,
       p.salary AS salary;
~~~

Kết quả mong đợi: email `an@example.test`, amount `120000`, note `VIP` và salary `45000000`.

**Vì sao phải có bước admin kiểm chứng?** Nếu test của reader trả `null` cho email hoặc 0 node lương, đó có thể là **do dữ liệu nguồn thật sự không có** chứ chưa chắc do RBAC. Positive fixture check bằng danh tính có quyền phù hợp giúp loại bỏ “test xanh giả”.

## 5. Thiết kế role chỉ được đọc đúng dữ liệu cần thiết

Phần này dùng **Neo4j Enterprise**. Các lệnh `CREATE USER`/`CREATE ROLE`/`GRANT` cần người có quyền quản trị tương ứng và được chạy trên **system database**; lệnh truy vấn dữ liệu trong `MATCH` chạy trên **database nghiệp vụ**.

### 5.1. Tạo role và user thử nghiệm

Trên system database, tài khoản được ủy quyền thực hiện:

~~~cypher
// SYSTEM DATABASE - chạy với quyền quản trị phù hợp.
CREATE ROLE qa_order_reader_role IF NOT EXISTS;
~~~

~~~cypher
// PASSWORD được cung cấp từ biến/tham số bảo mật của môi trường test.
CREATE USER qa_order_reader IF NOT EXISTS
SET PASSWORD $testPassword
CHANGE NOT REQUIRED;
~~~

~~~cypher
GRANT ROLE qa_order_reader_role TO qa_order_reader;
~~~

**Không dùng mật khẩu ví dụ cho production.** Trong ứng dụng thực, đưa credential từ secret manager hoặc môi trường bảo mật, bật TLS phù hợp và kiểm soát việc ghi query/parameter vào log. Lệnh tạo user bằng tham số ở đây nhằm tránh ghép mật khẩu trực tiếp vào chuỗi Cypher; vẫn phải kiểm tra chính sách logging.

### 5.2. Cấp quyền truy cập database và đối tượng

Các lệnh này cũng chạy trên **system database**:

~~~cypher
GRANT ACCESS ON DATABASE neo4j TO qa_order_reader_role;

GRANT MATCH {customerId}
ON GRAPH neo4j NODES SecCustomer
TO qa_order_reader_role;

GRANT MATCH {orderId, amount}
ON GRAPH neo4j NODES SecOrder
TO qa_order_reader_role;

GRANT TRAVERSE
ON GRAPH neo4j RELATIONSHIPS PLACED
TO qa_order_reader_role;
~~~

Mục đích:

1. User được truy cập **database `neo4j`**.
2. Có thể đọc **`customerId`** của node `SecCustomer`, nhưng không được cấp `email` hoặc `name` qua role này.
3. Có thể đọc **`orderId`, `amount`** trên `SecOrder`, nhưng không được cấp `internalNote` qua role này.
4. Có thể duyệt relationship `PLACED` để xác định khách hàng nào có đơn nào.
5. Không cấp quyền đọc node `SecPayroll`, không cấp `WRITE` và không cấp quyền admin qua role này.

**Không hiểu nhầm “không cấp” với “bị từ chối chắc chắn”:** một role **khác** (kể cả những quyền thừa kế) vẫn có thể cấp quyền tương ứng. Bước kiểm thử phải dùng tài khoản thực với **tổng quyền hiệu lực** và xác nhận user không mang role không mong muốn.

### 5.3. Khi nào dùng `DENY` rõ ràng?

Một `DENY` có thể hữu ích khi có một role chung cấp quyền đọc rộng, nhưng cần chặn một property nhạy cảm:

~~~cypher
// Chạy ở system, ví dụ dùng khi có chính sách cần chặn tường minh.
DENY READ {email}
ON GRAPH neo4j NODES SecCustomer
TO qa_order_reader_role;
~~~

Điểm quan trọng: **chính sách deny chỉ áp dụng theo phạm vi và ngữ nghĩa quyền được định nghĩa**; nó không thay việc rà soát mọi role và quyền thao tác gián tiếp. Với role thiết kế từ đầu, **chỉ `GRANT` đủ các property cần dùng** thường dễ quản lý hơn việc cấp rộng rồi liên tục `DENY`. Nếu áp dụng deny, hãy thử tác động lên các query và procedure thực tế trước khi rollout.

## 6. Rà soát quyền hiệu lực trước khi test

Trên **system database**, người có quyền quản trị phù hợp kiểm tra:

~~~cypher
SHOW USERS
YIELD user, roles, suspended
WHERE user = 'qa_order_reader'
RETURN user, roles, suspended;
~~~

~~~cypher
SHOW ROLE qa_order_reader_role PRIVILEGES AS COMMANDS;
~~~

~~~cypher
SHOW USER qa_order_reader PRIVILEGES AS COMMANDS;
~~~

Khi đọc kết quả, xác minh:

- User **không bị suspended** và được gán **đúng role dự kiến**.
- Có `ACCESS` đến đúng database, không vô tình cấp `ACCESS ON DATABASE *` nếu service chỉ cần một database.
- Quyền đọc gắn đúng label/type/property; không có quyền đọc `SecPayroll` ngoài dự định.
- Không có quyền `WRITE`/quản trị không cần thiết; không có quyền thực thi procedure nhạy cảm vượt phạm vi.
- Role `PUBLIC`, role tích hợp hoặc role phụ khác **không làm quyền hiệu lực rộng hơn** kế hoạch.
- Nếu có `DENY`, kiểm tra đúng đối tượng bị chặn và ảnh hưởng đến lệnh hợp lệ.

`SHOW ROLE ... PRIVILEGES` mô tả quyền **của một role**; `SHOW USER ... PRIVILEGES` dùng để xem quyền theo **user**. Không dùng danh sách quyền của một role riêng lẻ thay cho bằng chứng về user thực.

## 7. Ma trận kiểm thử được phép/bị từ chối

Để đánh giá least privilege, cần định nghĩa **kết quả được mong đợi** trước khi chạy. Đây là ma trận dành cho `qa_order_reader` sau khi đã thiết lập quyền và bảo đảm không có quyền dư.

| Tình huống | Ai kiểm tra? | Kỳ vọng | Cách xác minh |
|---|---|---|---|
| Đọc `SecOrder.orderId` và `amount` | Reader | **Cho phép**, trả một đơn | So với dữ liệu admin |
| Duyệt `SecCustomer-[:PLACED]->SecOrder` | Reader | **Cho phép**, trả cặp `C01/O01` | So khóa và hướng cạnh |
| Đọc `SecCustomer.email` | Reader | Bị che; thường là `null` | Admin xác nhận email tồn tại |
| Đọc `SecOrder.internalNote` | Reader | Bị che; thường là `null` | Admin xác nhận note tồn tại |
| `MATCH` node `SecPayroll` | Reader | **Không nhìn thấy** node, thường 0 hàng | Admin xác nhận 1 node |
| `SET o.amount = ...` | Reader | **Bị từ chối** bằng lỗi authorization | Admin kiểm tra amount không đổi |
| `DELETE` node đơn hàng | Reader | **Bị từ chối** nếu không có quyền ghi/xóa | Admin xác nhận node/cạnh còn |
| Tạo role/user hoặc quản trị database | Reader | **Bị từ chối** vì thiếu quyền quản trị | Không có role/user mới |
| Gọi procedure nhạy cảm | Reader | Theo danh sách `EXECUTE` được cấp, nên từ chối nếu không được phép | Kiểm tra danh sách procedure/quyền trên server |

**Đừng viết một assertion duy nhất kiểu “mọi truy cập không được phép phải ném `ClientException`”.** Lệnh `MATCH` khi bị hạn chế traversal có thể trả **ít hàng hơn**, còn property thiếu quyền có thể trả **`null`**. Cần đặt kỳ vọng đúng từng loại quyền.

## 8. Test 1 — Truy vấn hợp lệ phải thành công

Kết nối vào database `neo4j` bằng **credential `qa_order_reader`**, không dùng admin:

~~~cypher
MATCH (c:SecCustomer {customerId: 'C01'})
      -[:PLACED]->(o:SecOrder)
RETURN c.customerId AS customerId,
       o.orderId AS orderId,
       o.amount AS amount
ORDER BY orderId;
~~~

Với fixture ở mục 4, kết quả đúng:

| customerId | orderId | amount |
|---|---|---:|
| C01 | O01 | 120000 |

Nếu truy vấn không trả kết quả, đừng vội gán “thiếu `READ`”. Kiểm tra cả `ACCESS` database, `TRAVERSE` trên **hai loại node và relationship**, role thừa kế và dữ liệu fixture. Khi một bước traverse bị chặn, toàn bộ pattern có thể không khớp dù các node tồn tại.

## 9. Test 2 — Property bị che không đồng nghĩa property bị xóa

Vẫn bằng tài khoản reader:

~~~cypher
MATCH (c:SecCustomer {customerId: 'C01'})
RETURN c.customerId AS customerId,
       c.email AS email;
~~~

Kỳ vọng: vẫn có node `C01` nhưng `email` là `null` hoặc không đọc được giá trị theo chính sách quyền của phiên bản, trong khi tài khoản admin truy vấn:

~~~cypher
MATCH (c:SecCustomer {customerId: 'C01'})
RETURN c.email AS email;
// Admin kỳ vọng 'an@example.test'
~~~

**Hai điều cần assert đồng thời:**

1. Admin xác nhận giá trị nhạy cảm **thật sự tồn tại**.
2. Reader **không thể thu được giá trị nhạy cảm**, dù có thể đọc ID công khai.

Trong Cypher, `null` cũng có thể do property vốn thiếu. Vì vậy chỉ kiểm tra `email IS NULL` trong một phiên reader **không chứng minh** chính sách đã bảo vệ dữ liệu.

Ngoài truy cập bằng dot-property, nên kiểm tra những cách lấy dữ liệu như `properties(c)`, map projection và truy vấn do SDN sinh. Một chính sách đúng cần bảo vệ dữ liệu ở lớp authorization của Neo4j thay vì chỉ giấu cột trong UI.

## 10. Test 3 — Node/relationship bị chặn có thể trở thành kết quả rỗng

Với tài khoản reader:

~~~cypher
MATCH (p:SecPayroll)
RETURN count(p) AS payrollNodes;
~~~

Kỳ vọng: `payrollNodes = 0` nếu danh tính không có quyền traverse `SecPayroll` và không có role khác cho phép. Với admin:

~~~cypher
MATCH (p:SecPayroll)
RETURN count(p) AS payrollNodes;
// Admin kỳ vọng 1 theo fixture.
~~~

Đây là tình huống **lọc dữ liệu theo quyền** chứ không nhất thiết là lỗi exception. Nếu ứng dụng lẫn lộn “không tồn tại” với “không được nhìn thấy”, API có thể đưa ra thông báo sai. Trong nhiều hệ thống, trả lời “không tìm thấy hoặc không có quyền” còn là lựa chọn để **tránh lộ sự tồn tại của tài nguyên**.

Tương tự, nếu node `SecCustomer` và `SecOrder` được thấy nhưng relationship `PLACED` không có quyền `TRAVERSE`, query `MATCH (c)-[:PLACED]->(o)` có thể không ra hàng. Không mở quyền vào mọi relationship chỉ để sửa một bài test; phải xem lại nhu cầu nghiệp vụ và mô hình truy cập.

## 11. Test 4 — Thao tác ghi bị từ chối phải không để lại tác dụng phụ

Trước hết, tài khoản admin đọc trạng thái ban đầu:

~~~cypher
MATCH (o:SecOrder {orderId: 'O01'})
RETURN o.amount AS amount;
// 120000
~~~

Tài khoản reader cố ghi:

~~~cypher
MATCH (o:SecOrder {orderId: 'O01'})
SET o.amount = 999999
RETURN o.orderId AS orderId;
~~~

Vì role reader không được cấp quyền ghi, giao dịch này phải **không thể sửa `amount`**. Với các cấu hình Neo4j RBAC phù hợp, thao tác ghi bị từ chối bằng lỗi quyền, chẳng hạn thuộc nhóm `Neo.ClientError.Security.*`.

Sau đó admin truy vấn lại:

~~~cypher
MATCH (o:SecOrder {orderId: 'O01'})
RETURN o.amount AS amount;
// Phải vẫn là 120000.
~~~

Nếu chỉ kiểm tra “reader nhận exception” mà **không đọc lại trạng thái graph**, một bài kiểm thử có thể bỏ sót lỗi ranh giới giao dịch hoặc dữ liệu đã thay đổi từ giao dịch khác. Nếu test bao gồm nhiều câu lệnh, hãy xác minh chúng nằm trong **cùng transaction** trước khi kết luận toàn bộ tác vụ được rollback.

### Truy cập bị từ chối khác lỗi constraint

Nếu một người ghi được phép nhưng tạo hai node `SecOrder` có cùng `orderId` trên database có uniqueness constraint, lỗi có thể là **vi phạm schema**, không phải lỗi quyền. Hãy tách **authorization negative test** khỏi **constraint negative test** để không gọi mọi `ClientException` là lỗi `FORBIDDEN`.

## 12. Test 5 — Không cho phép leo thang đặc quyền qua quản trị/procedure

Tài khoản ứng dụng đọc đơn **không cần** `CREATE USER`, `CREATE ROLE`, `GRANT`/`DENY`, quản lý database hoặc thực thi các procedure quản trị nhạy cảm.

Với user reader, trên môi trường Enterprise cô lập, thử chạy một lệnh quản trị vô hại về ý định:

~~~cypher
SHOW USERS;
~~~

Việc câu lệnh này trả gì phụ thuộc các quyền quản trị **SHOW USER**, phiên bản Neo4j và ngữ cảnh database. Nếu reader có thể liệt kê thông tin quản trị không cần thiết, hãy rà soát quyền đã cấp; nếu không được phép, ứng dụng phải xử lý lỗi và không tự chuyển sang tài khoản admin.

**Không dùng lệnh thật `CREATE USER` hoặc `DROP DATABASE` trong negative test mặc định** chỉ để thử quyền. Một khi môi trường bị cấu hình sai và user vô tình có quyền, bài test sẽ gây thay đổi thật. Thay bằng truy vấn `SHOW` có kiểm soát hoặc chạy kiểm tra quyền hiệu lực từ tài khoản quản trị.

### Procedure và plugin

Kiểm tra tên procedure/đặc quyền bằng tài khoản admin hoặc account có quyền xem:

~~~cypher
SHOW PROCEDURES
YIELD name
WHERE name STARTS WITH 'apoc.'
RETURN name
ORDER BY name
LIMIT 30;
~~~

Hãy đánh giá procedure có khả năng:

- Đọc/ghi tệp hoặc gọi URL (`apoc.load.*`, export, ...).
- Thực thi Cypher động với cấu hình nhạy cảm.
- Thực hiện tác vụ quản trị hoặc thao tác bằng đặc quyền nâng cao.
- Truy cập database khác hoặc dữ liệu không thuộc phạm vi API.

**Có quyền `EXECUTE PROCEDURE` không mặc nhiên đồng nghĩa mọi procedure đều được phép thao tác ngoài phạm vi graph.** Còn phải xem **quyền graph**, allowlist, unrestricted/boosted procedure và các cấu hình an toàn của server. Tuy nhiên, cấp quyền rộng rồi dựa vào “ứng dụng không gọi thủ tục đó” là mô hình yếu; cần **hạn chế ngay tại Neo4j**.

## 13. Kiểm thử hai danh tính với Java Driver

Để chứng minh authorization, test phải **thực sự kết nối bằng tài khoản bị giới hạn**. Nếu mọi truy vấn dùng tài khoản admin, test có thể luôn xanh nhưng không phản ánh quyền của ứng dụng.

### 13.1. Thiết lập môi trường test

Gợi ý dùng **JUnit 5 + Testcontainers + Neo4j Enterprise Edition** trong môi trường đã chấp nhận điều khoản sử dụng phù hợp. Đưa quyền, user, role và dữ liệu fixture vào bước thiết lập database độc lập. Sau đó mở hai `Driver`:

~~~java
import org.neo4j.driver.AuthTokens;
import org.neo4j.driver.Driver;
import org.neo4j.driver.GraphDatabase;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

// URI và mật khẩu lấy từ cấu hình test/secret, không hard-code production.
Driver adminDriver = GraphDatabase.driver(
    boltUri, AuthTokens.basic("neo4j", adminPassword));

Driver readerDriver = GraphDatabase.driver(
    boltUri, AuthTokens.basic("qa_order_reader", readerPassword));

// Dùng database cụ thể để tránh phụ thuộc home database.
SessionConfig graphDb = SessionConfig.forDatabase("neo4j");
~~~

Đây là **đoạn cấu hình minh họa**, không phải file Java độc lập. Việc provision role/user cần được làm **trước khi tạo phiên reader hoặc chạy test**; đối với Testcontainers, điều này thường nằm trong bootstrap setup hoặc bước `@BeforeAll`.

### 13.2. Positive test: reader đọc được thông tin công khai

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

@Test
void readerCanReadOrderSummary() {
    try (Session session = readerDriver.session(graphDb)) {
        var record = session.executeRead(tx -> tx.run("""
            MATCH (c:SecCustomer {customerId: 'C01'})
                  -[:PLACED]->(o:SecOrder)
            RETURN c.customerId AS customerId,
                   o.orderId AS orderId,
                   o.amount AS amount
            """).single());

        assertEquals("C01", record.get("customerId").asString());
        assertEquals("O01", record.get("orderId").asString());
        assertEquals(120000L, record.get("amount").asLong());
    }
}
~~~

Test khẳng định reader **có đủ** quyền phục vụ nghiệp vụ. Chỉ có negative test mà không có positive test dễ tạo bộ kiểm thử “thành công” khi tài khoản **không đọc được bất cứ thứ gì**.

### 13.3. Negative test: property bị ẩn

~~~java
import static org.junit.jupiter.api.Assertions.assertTrue;

@Test
void readerCannotSeeCustomerEmail() {
    // Admin xác nhận fixture thật có email.
    try (Session admin = adminDriver.session(graphDb)) {
        var row = admin.executeRead(tx -> tx.run("""
            MATCH (c:SecCustomer {customerId: 'C01'})
            RETURN c.email AS email
            """).single());
        assertEquals("an@example.test", row.get("email").asString());
    }

    // Reader vẫn thấy C01, nhưng không được đọc email.
    try (Session reader = readerDriver.session(graphDb)) {
        var row = reader.executeRead(tx -> tx.run("""
            MATCH (c:SecCustomer {customerId: 'C01'})
            RETURN c.customerId AS id, c.email AS email
            """).single());
        assertEquals("C01", row.get("id").asString());
        assertTrue(row.get("email").isNull());
    }
}
~~~

Nếu bản Neo4j/cấu hình cụ thể trả lỗi thay vì `null` cho phép thử, hãy xác minh ngữ nghĩa authorization của **phiên bản đó** trước khi sửa assertion. Mục tiêu bất biến là **giá trị nhạy cảm không đến tay tài khoản reader**.

### 13.4. Negative test: ghi bị từ chối và dữ liệu không đổi

~~~java
import static org.junit.jupiter.api.Assertions.assertThrows;
import org.neo4j.driver.exceptions.Neo4jException;

@Test
void readerCannotModifyOrderAmount() {
    try (Session reader = readerDriver.session(graphDb)) {
        Neo4jException error = assertThrows(
            Neo4jException.class,
            () -> reader.executeWrite(tx -> {
                tx.run("""
                    MATCH (o:SecOrder {orderId: 'O01'})
                    SET o.amount = 999999
                    """).consume();
                return null;
            }));

        // Phân loại chính xác bằng error.code() và exception type
        // theo server/driver hiện có; không so sánh chuỗi getMessage().
        System.out.println("Expected authorization failure: " + error.code());
    }

    try (Session admin = adminDriver.session(graphDb)) {
        long amount = admin.executeRead(tx -> tx.run("""
            MATCH (o:SecOrder {orderId: 'O01'})
            RETURN o.amount AS amount
            """).single().get("amount").asLong());
        assertEquals(120000L, amount);
    }
}
~~~

**Trong test production-grade**, thay `System.out.println` bằng log/metric an toàn và kiểm tra **mã lỗi nhóm Security** hoặc classification phù hợp; ví dụ trên nhấn mạnh việc đọc mã thay vì thông điệp. Nếu test chạy với tài khoản có role ghi ngoài ý muốn, thao tác `SET` sẽ thành công và `assertThrows` thất bại — đó chính là vấn đề test cần phát hiện.

### 13.5. Negative test: label không được nhìn thấy

~~~java
@Test
void readerCannotTraversePayrollNodes() {
    try (Session admin = adminDriver.session(graphDb)) {
        long existing = admin.executeRead(tx -> tx.run("""
            MATCH (p:SecPayroll)
            RETURN count(p) AS n
            """).single().get("n").asLong());
        assertEquals(1L, existing);
    }

    try (Session reader = readerDriver.session(graphDb)) {
        long visible = reader.executeRead(tx -> tx.run("""
            MATCH (p:SecPayroll)
            RETURN count(p) AS n
            """).single().get("n").asLong());
        assertEquals(0L, visible);
    }
}
~~~

Ở đây, `visible = 0` không phải bằng chứng node không tồn tại; **chỉ phép kiểm tra bằng admin** xác nhận dữ liệu gốc có một node và chính sách của reader giới hạn quyền nhìn thấy.

### 13.6. Không dùng quyền quản trị để chạy tất cả assertion

Hệ thống có thể có `schema-migrator` để tạo index/constraint và `order-api-reader` để đọc. Test cho `schema-migrator` phải được tách biệt khỏi test cho `order-api-reader`. Nếu một test dùng admin để seed và sau đó vẫn dùng admin để thực hiện lời gọi repository, nó **không kiểm tra được least privilege** của tài khoản ứng dụng.

Với **Spring Data Neo4j**, hãy chỉ định credential/database của service trong cấu hình test, gọi **repository/service thật**, rồi đối chiếu dữ liệu bằng một kết nối admin riêng **sau khi transaction của service đã commit hoặc rollback đúng như dự định**.

## 14. Viết test tự động mà không gây thay đổi ngoài ý muốn

Với các tình huống cố ý truy cập bị từ chối, bản thân bài test cũng cần quyền tối thiểu và cách ly:

| Quy tắc | Lý do |
|---|---|
| Dùng **database/container riêng** cho kiểm thử quyền | Tránh vô tình xóa user, role hay dữ liệu đang phục vụ hệ thống |
| Provision bằng admin; chạy nghiệp vụ bằng user bị giới hạn | Phân biệt bước thiết lập với bước xác minh quyền |
| Positive test và negative test theo cặp | Bắt được cả quyền thiếu lẫn quyền dư |
| Chỉ dùng fixture có giá trị rõ ràng | `null`/0 hàng không bị nhầm với dữ liệu thiếu |
| Dùng tên user/role/label dành riêng cho test | Không xung đột với role production |
| Negative test ghi có **trạng thái trước/sau** | Chứng minh không có dữ liệu bị thay đổi |
| Không làm thay đổi role giữa các test chạy song song | Tránh kết quả ngẫu nhiên do role cập nhật khi query đang chạy |
| Không dùng mật khẩu thật trong source/CI log | Giảm nguy cơ rò bí mật |
| Dọn user/role/test data chỉ trong môi trường do test sở hữu | Không phá tài nguyên của công việc khác |

**Chú ý về transaction:** một test đọc bằng admin trong transaction khác có thể **không thấy dữ liệu chưa commit** của bước tạo fixture. Cần commit fixture trước khi chạy test reader; nếu không, test “đọc 0 hàng” có thể do **isolation**, không phải do authorization.

### Mẫu thứ tự test đáng tin

~~~mermaid
flowchart TD
    A["Khởi tạo DB/container Enterprise test"] --> B["Tạo fixture bằng admin<br/>và COMMIT"]
    B --> C["Provision user/role/grants<br/>trên system"]
    C --> D["SHOW USER ... PRIVILEGES<br/>xác nhận quyền hiệu lực"]
    D --> E["Positive tests bằng reader"]
    E --> F["Negative tests: hidden data,<br/>write denied, missing traversal"]
    F --> G["Admin đọc lại trạng thái DB"]
    G --> H["Báo cáo PASS/FAIL + dọn test resources"]
~~~

## 15. Không để quyền cấu hình đúng nhưng ứng dụng vẫn rò dữ liệu

RBAC ở Neo4j là một lớp bảo vệ, không thay thế thiết kế ứng dụng an toàn. Một số rủi ro cần phối hợp kiểm tra:

### 15.1. Không nối trực tiếp đầu vào vào Cypher

**Sai:**

~~~java
String cypher =
    "MATCH (o:SecOrder {orderId: '" + userInput + "'}) RETURN o";
~~~

**Đúng:** dùng tham số:

~~~java
var record = session.executeRead(tx -> tx.run("""
        MATCH (o:SecOrder {orderId: $orderId})
        RETURN o.orderId AS id, o.amount AS amount
        """,
        java.util.Map.of("orderId", userInput)
    ).single());
~~~

Tham số giúp tách **giá trị** khỏi cấu trúc câu Cypher. Tuy nhiên, label/type và các thành phần cấu trúc truy vấn động có thể có giới hạn tham số theo phiên bản; nếu phải xây phần cấu trúc động, dùng **allowlist server-side** và kiểm thử, không nối chuỗi bất kỳ từ người dùng.

### 15.2. Không trả node nguyên vẹn khi API chỉ cần vài thuộc tính

Nếu endpoint chỉ cần `orderId` và `amount`, ưu tiên:

~~~cypher
MATCH (o:SecOrder {orderId: $orderId})
RETURN o.orderId AS orderId, o.amount AS amount;
~~~

thay vì trả toàn bộ `o` rồi dựa hoàn toàn vào Java DTO để “giấu” mọi trường nhạy cảm. Quyền Neo4j nên đảm bảo ứng dụng không có quyền đọc những property ngoài nhu cầu, đồng thời lớp API chỉ serializes dữ liệu đã được thiết kế rõ ràng.

### 15.3. Tách vai trò của service và migration

Một service đọc đơn không nên có quyền tạo index, constraint hay quản trị role chỉ vì quá trình deploy dùng một tài khoản chung. Tách:

- **Runtime reader:** chỉ đọc node, relationship và property cần phục vụ API.
- **Runtime writer:** cấp quyền ghi theo đúng nghiệp vụ, không dùng admin.
- **Schema migrator:** tạo/thay đổi index, constraint theo quy trình triển khai có kiểm soát.
- **Security administrator:** tạo user/role, cấp và thu hồi privilege qua quy trình phê duyệt.

Nếu service vận hành qua Spring Data Neo4j tự thực hiện migration khi khởi động, cần xác định rõ rủi ro của việc cấp quyền schema lâu dài cho **runtime identity**; cân nhắc tách migration thành job riêng.

### 15.4. Bảo mật credential và log

Neo4j Java Driver có thể kết nối bằng URI như `neo4j+s://` hoặc `bolt+s://` để xác minh TLS theo chế độ phù hợp. Chọn scheme theo hình thức triển khai và chứng chỉ. Không tắt xác minh chứng chỉ chỉ để vượt qua lỗi kết nối.

Các nguồn rò dữ liệu phổ biến:

- In `password`/`token` vào log khi tạo `AuthTokens.basic(...)`.
- Ghi nguyên tham số Cypher chứa PII vào query log hoặc trace.
- Trả nguyên `Neo4jException.getMessage()` và câu Cypher ra HTTP response.
- Tạo file `application.yml` chứa credential production rồi commit vào Git.
- Lưu secret vào metadata transaction/correlation ID.

Hãy log **mã lỗi, tên thao tác, request ID không nhạy cảm** và độ trễ; đưa secret vào secret manager, giới hạn người đọc log và thiết lập thời hạn lưu log.

## 16. Rà soát quyền theo thời gian và phát hiện *privilege drift*

Một bài test có thể đạt hôm nay nhưng thất bại sau khi một migration, vai trò mới hoặc thay đổi `PUBLIC` làm quyền hiệu lực thay đổi. Vì vậy, least privilege là **hoạt động lặp lại**, không phải cấu hình một lần.

### Checklist rà soát

1. **Lập danh sách truy vấn thật** do Java Driver/SDN gửi: endpoint nào cần label/type/property nào? Các procedure nào thực sự được gọi?
2. **Lập bảng role–identity–database**: người dùng và service account, database đích, role kế thừa, cả `PUBLIC`.
3. **Chụp trạng thái quyền hiệu lực** bằng `SHOW USER ... PRIVILEGES AS COMMANDS` từ tài khoản có quyền quản trị.
4. **Đánh dấu quyền không có lý do nghiệp vụ**: `ACCESS ON DATABASE *`, `MATCH {*}` rộng, quyền ghi/xóa mọi node, quản trị user/schema, procedure nâng cao.
5. **Chạy ma trận positive/negative tests** trên bản sao cấu hình quyền gần production, bằng identity thật của từng service.
6. **Kiểm tra thay đổi mới**: migration, plugin/APOC, bổ sung label/property, API mới hoặc tài khoản vừa được cấp thêm role.
7. **Thu hồi quyền không còn dùng** theo quy trình có rollback, đo tác động và chạy lại test nghiệp vụ.
8. **Ghi nhận owner, lý do, thời hạn và bằng chứng kiểm thử** của từng đặc quyền ngoại lệ.

### Mẫu biên bản kiểm tra

| Hạng mục | Kết quả cần ghi |
|---|---|
| Thời điểm, Neo4j version/edition, database | Môi trường nào được kiểm tra |
| Danh tính/role | `qa_order_reader` + role hiệu lực |
| Query/endpoint nghiệp vụ | Query đã thử và tham số mẫu |
| Các quyền bắt buộc | ACCESS, MATCH/READ/TRAVERSE theo đúng nhãn/thuộc tính |
| Quyền dư hoặc DENY xung đột | Bằng chứng từ SHOW PRIVILEGES |
| Positive test | Có đọc đúng C01/O01/120000 không? |
| Negative read/traverse tests | Email/note không lộ, SecPayroll không thấy |
| Negative write test | Có lỗi quyền và dữ liệu gốc vẫn 120000? |
| Procedure/admin test | Không có đặc quyền vượt nhu cầu |
| Kết luận/chủ sở hữu | PASS/FAIL, việc phải sửa và người chịu trách nhiệm |

**Đừng ghi “PASS” chỉ dựa vào một danh sách `GRANT`**. Cần cả dữ liệu thực nghiệm về quyền, trong đó có các kết quả rỗng/`null` mà Neo4j dùng để che giấu đối tượng.

## 17. Bài tập thực hành

### Bài 1 — Phân biệt ba kết quả bị hạn chế

Reader chạy ba truy vấn:

~~~cypher
MATCH (o:SecOrder {orderId: 'O01'})
RETURN o.amount AS amount;
~~~

~~~cypher
MATCH (o:SecOrder {orderId: 'O01'})
RETURN o.internalNote AS note;
~~~

~~~cypher
MATCH (p:SecPayroll)
RETURN count(p) AS total;
~~~

**Câu hỏi:** Nếu quyền được thiết lập như mục 5 và dữ liệu fixture đúng, dự kiến ba kết quả là gì? Vì sao không được assert cả ba đều ném exception?

**Đáp án gợi ý:** Query đầu trả `120000`; query thứ hai không thấy `internalNote` (thường `null`); query thứ ba `count = 0` do không được traverse label. Neo4j có cơ chế lọc kết quả theo privilege; chỉ một số thao tác không được phép mới trả exception. Phải kiểm chứng dữ liệu thật qua admin để phân biệt do quyền với dữ liệu thiếu.

### Bài 2 — Phát hiện quyền dư

`SHOW ROLE order_reader PRIVILEGES` cho thấy role chỉ được đọc `SecOrder.orderId` và `amount`. Nhưng user thực vẫn đọc được `SecCustomer.email`. Vì sao?

**Đáp án gợi ý:** Có thể user mang role khác (hoặc quyền từ `PUBLIC`/chính sách khác) cấp `TRAVERSE` và `READ` rộng hơn. Phải dùng `SHOW USER ... PRIVILEGES`, kiểm tra các role của user và các `DENY` liên quan; không dựa vào một role riêng lẻ.

### Bài 3 — Kiểm tra rollback sau thao tác bị từ chối

Reader cố `SET o.amount = 1`. Một test chỉ kiểm tra `assertThrows(Neo4jException.class, ...)`. Hãy bổ sung hai assertion quan trọng.

**Đáp án gợi ý:** (1) Kiểm tra **loại/mã lỗi quyền**, không bắt nhầm lỗi cú pháp hoặc lỗi kết nối; (2) đọc lại `o.amount` bằng admin **sau transaction thất bại** và xác nhận nó vẫn `120000`. Nếu job gồm nhiều bước, cần xác định ranh giới transaction trước khi kết luận mọi thay đổi đều rollback.

### Bài 4 — Thiết kế hai tài khoản runtime

Ứng dụng có endpoint `GET /orders/{id}` và một job cập nhật `Order.status`. Đề xuất cách chia quyền tối thiểu.

**Đáp án gợi ý:** Tạo identity đọc chỉ có `ACCESS` và quyền đọc những label/property/path cần hiển thị; identity ghi có quyền tạo/cập nhật đối tượng và property phù hợp, không mặc nhiên có quyền đọc email hoặc quản trị schema. Tách job migration và bảo mật. Viết test positive/negative riêng cho từng identity và bảo đảm endpoint đọc không dùng credential writer.

### Bài 5 — Không có exception có nghĩa an toàn?

Một truy vấn `MATCH (p:SecPayroll) RETURN p.salary` chạy thành công nhưng trả 0 hàng. Đã chứng minh quyền `SecPayroll` bị hạn chế chưa?

**Đáp án gợi ý:** Chưa. Cần chứng minh `SecPayroll` thực sự có dữ liệu bằng admin, reader đang kết nối đúng database và transaction fixture đã commit. Sau đó đối chiếu quyền hiệu lực để xác nhận node bị che do không có quyền `TRAVERSE`.

### Bài 6 — Cấp quyền cho procedure

Một nhóm muốn cấp `EXECUTE BOOSTED PROCEDURE *` cho mọi service “để tránh lỗi permission”. Tại sao cần phản đối phương án này?

**Đáp án gợi ý:** Quyền procedure nâng cao có thể vượt phạm vi truy cập dự định và tạo bề mặt tấn công lớn, nhất là procedure xử lý file, URL hoặc câu Cypher động. Cần xác định procedure thực sự sử dụng, quyền cần thiết và giới hạn thực thi, sau đó kiểm thử từng dịch vụ với credential riêng.

## 18. Tài liệu tham khảo

- [Neo4j Operations Manual — Authentication & authorization](https://neo4j.com/docs/operations-manual/current/authentication-authorization/)
- [Neo4j Operations Manual — Managing privileges](https://neo4j.com/docs/operations-manual/current/authentication-authorization/manage-privileges/)
- [Neo4j Operations Manual — Role-based access control](https://neo4j.com/docs/operations-manual/current/authentication-authorization/)
- [Neo4j Cypher Manual — SHOW commands và graph privileges](https://neo4j.com/docs/cypher-manual/current/clauses/)
- [Neo4j Java Driver Manual — Connectivity và sessions](https://neo4j.com/docs/java-manual/current/connect/)
- [Neo4j Java Driver Manual — Managed transactions](https://neo4j.com/docs/java-manual/current/transactions/)
- [Neo4j Security Guide](https://neo4j.com/developer/guide-neo4j-security/)

Các liên kết `current` được cập nhật theo phiên bản. Khi ứng dụng dùng Neo4j 5.x, Aura hoặc phiên bản sau này, phải xác minh **edition, role/privilege syntax, quyền mặc định và cách xử lý thao tác bị chặn** bằng tài liệu của bản cài đặt thật.

## 19. Ghi nhớ

- **Least privilege** nghĩa là đúng danh tính, database, label/type, property và thao tác cần thiết — không dùng tài khoản admin làm identity runtime.
- **Rà soát quyền hiệu lực**, gồm nhiều role và `PUBLIC`; `DENY` có thể chặn `GRANT` theo phạm vi phù hợp.
- **Không có quyền đọc không đồng nghĩa luôn có exception**: node/relationship bị chặn có thể biến mất khỏi `MATCH`, property bị che có thể trả `null`.
- **Mỗi negative test cần positive control** bằng danh tính có quyền phù hợp và kiểm tra trạng thái dữ liệu sau thao tác ghi bị từ chối.
- **Java Driver/SDN phải chạy dưới credential thực sự bị giới hạn**; truy vấn chỉ bằng admin không chứng minh bảo vệ của tài khoản ứng dụng.
- **RBAC phải đi cùng tham số Cypher, bảo vệ credential, TLS, quyền procedure tối thiểu và kiểm thử drift định kỳ** để giảm rủi ro rò dữ liệu hoặc thay đổi trái phép.
