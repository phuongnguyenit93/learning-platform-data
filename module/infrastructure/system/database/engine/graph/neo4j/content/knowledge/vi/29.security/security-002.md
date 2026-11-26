# Phân quyền theo vai trò và khả năng của edition hoặc gói dịch vụ trong Neo4j

## 1. Vì sao phân quyền phải được thiết kế cùng mô hình graph?

Neo4j lưu dữ liệu bằng **property graph**: node, relationship và các thuộc tính. Một ứng dụng có thể dùng Cypher để đọc danh sách khách hàng, đi từ đơn hàng sang sản phẩm, sửa quan hệ hoặc quản lý index. Những hành động này có **rủi ro và phạm vi quyền khác nhau**.

Ví dụ hệ thống thương mại B2B có ba nhóm người dùng:

- Nhân viên chăm sóc khách hàng chỉ được xem đơn hàng và trạng thái, không được xem thông tin tài chính nhạy cảm.
- Dịch vụ đặt hàng cần tạo đơn và quan hệ mua hàng nhưng không có quyền quản lý user hay sửa schema.
- Quản trị viên hạ tầng cần quản lý tài khoản, role, constraint, index và cấu hình vận hành.

Nếu cả ba dùng chung tài khoản `neo4j` với quyền quản trị, việc ứng dụng bị lộ credential hoặc một đoạn Cypher bị lỗi có thể ảnh hưởng tới **toàn bộ graph**. Đó là lý do cần áp dụng nguyên tắc **least privilege**: mỗi danh tính chỉ có những quyền thực sự cần.

Bài thuộc chương **Bảo mật** giải thích:

1. **Authentication** (xác thực danh tính) khác gì **authorization** (quyết định quyền truy cập)?
2. Cơ chế **role-based access control — RBAC** của Neo4j tổ chức user, role và privilege như thế nào?
3. Cú pháp `CREATE ROLE`, `GRANT`, `DENY`, `REVOKE`, `SHOW PRIVILEGES` dùng trong trường hợp nào?
4. Khả năng này có trên **Community, Enterprise, AuraDB Free, Professional, Business Critical, Virtual Dedicated Cloud** hay không?
5. Java Driver và Spring Data Neo4j phải triển khai kết nối, kiểm thử và phân tách quyền thế nào?

> **Phạm vi phiên bản:** Cú pháp minh họa hướng tới Neo4j hiện hành thuộc dòng 5.x và lịch phát hành `2025.MM`/`2026.MM`. Các tính năng và giới hạn theo edition hoặc gói AuraDB có thể thay đổi; trước khi triển khai phải đối chiếu trang tính năng của **phiên bản và dịch vụ cụ thể**.

## 2. Trước hết, phân biệt xác thực, phân quyền và kiểm soát truy cập ứng dụng

| Khái niệm | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Authentication** | Ai đang kết nối? | Native username/password, LDAP, OIDC/SSO tùy edition |
| **Authorization** | Danh tính đó được làm gì? | Chỉ `MATCH` node `Order`, không được `CREATE` hoặc quản lý role |
| **Database/graph access** | Được truy cập phạm vi nào? | Database `neo4j`, node `Customer`, thuộc tính `status` |
| **Application authorization** | Người dùng cuối được gọi API nào và xem bản ghi nào? | Khách A chỉ xem đơn thuộc mình và tenant của mình |
| **Operational security** | Credential, mạng, log, backup có an toàn không? | TLS, secret manager, firewall, audit, rotation |

Đừng nhầm chúng: đăng nhập thành công **không đồng nghĩa** được đọc mọi node. Ngược lại, ứng dụng có `@PreAuthorize` trong Spring **không tự biến thành RBAC tại database**. Nếu tài khoản kết nối Bolt có quyền rộng, những truy vấn gửi trực tiếp bằng credential đó vẫn chạy trong phạm vi quyền rộng ấy.

Sơ đồ luồng kiểm tra:

```text
HTTP request / background job
         |
         v
Xác thực người dùng ở ứng dụng / IdP
         |
         v
Kiểm tra tenant, nghiệp vụ, route, input
         |
         v
Java Driver / Spring Data Neo4j
         |  credential database
         v
Neo4j xác thực connection
         |
         v
DBMS xét role + privilege + scope
         |
         +-- Cho phép: thực thi Cypher trên graph nhìn thấy
         |
         +-- Không cho phép: ẩn dữ liệu khi đọc hoặc từ chối thao tác ghi
```

Có thể có nhiều lớp phòng vệ: RBAC ở Neo4j **bổ sung** cho kiểm soát nghiệp vụ trong ứng dụng, không miễn trách nhiệm kiểm tra quyền sở hữu đơn hàng hay tenant.

## 3. Ma trận hỗ trợ theo edition và AuraDB tier

### 3.1. Neo4j tự vận hành

| Bản phân phối | Authentication | RBAC tùy biến & phân quyền chi tiết | Ghi chú |
| --- | --- | --- | --- |
| **Community Edition** | Có tài khoản native và mật khẩu | **Không có RBAC** | Có thể quản lý user ở mức cơ bản nhưng **mọi user có quyền admin ngầm định**; không tạo role reader thật |
| **Enterprise Edition** | Native, LDAP/OIDC và lựa chọn khác theo cấu hình | **Có** | Custom roles, `GRANT`/`DENY`/`REVOKE`, phân quyền database/graph/thuộc tính và quản trị |
| **Infinigraph** | Khả năng Enterprise và cơ chế triển khai liên quan | **Có** | Gói chuyên về graph quy mô lớn bao gồm các khả năng Enterprise; kiểm tra ranh giới theo shard/đặc tính cụ thể |
| **Enterprise for Developers** | Tính năng Enterprise cho phát triển khi giấy phép cho phép | **Có trong môi trường được cấp phép** | Không suy rằng giấy phép developer đủ để triển khai production |

**Điểm dễ nhầm trong Community Edition:** Có thể chạy `CREATE USER` với native password, nhưng **không tạo được mô hình “user A chỉ đọc, user B được ghi” bằng RBAC**. Theo tài liệu Neo4j hiện hành, Community không có role và mọi user có quyền quản trị ngầm định. Tạo thêm nhiều tài khoản ở Community giúp phân biệt credential, **không cung cấp least-privilege ở tầng Neo4j**.

### 3.2. Neo4j AuraDB — dịch vụ được quản lý

| AuraDB tier | RBAC & fine-grained database privileges | Đặc điểm cần chú ý |
| --- | --- | --- |
| **Free** | **Không** | Phù hợp học tập/thử nghiệm; có xác thực nhưng không có chính sách RBAC chi tiết |
| **Professional** | **Không** | Dù trả phí và có các tiện ích vận hành, không đồng nghĩa có `CREATE ROLE`/phân quyền graph chi tiết |
| **Business Critical** | **Có** | Hỗ trợ RBAC/fine-grained access control và property-based access control; nhiều khả năng doanh nghiệp |
| **Virtual Dedicated Cloud** | **Có** | Hỗ trợ RBAC như Business Critical, kết hợp những khả năng hạ tầng chuyên biệt của tier |

Thông tin đối chiếu theo trang **Neo4j Pricing — Security / RBAC and Fine-Grained Access Control**, cập nhật tại thời điểm biên soạn (11/2026). Tên tier và tính năng có thể đổi.

**Chú ý hai hệ phân quyền trong Aura:**

1. **Aura Console / Organization / Project roles:** ai được tạo, xem, quản lý hoặc thanh toán instance trong console.
2. **Neo4j DBMS roles/privileges:** ai được `MATCH`, `WRITE`, truy cập database hoặc sửa schema qua Bolt/Cypher.

Một người là **admin của tổ chức trên Aura Console không mặc nhiên có mọi quyền dữ liệu**, và phân quyền ở Console không có nghĩa Free/Professional hỗ trợ Cypher RBAC. Hãy kiểm tra đúng **database tier** và mô hình identity dùng cho connection.

Ngoài ra, trên AuraDB nhiều lệnh quản trị hạ tầng như `CREATE DATABASE`, `DROP DATABASE` hoặc điều khiển server bị hạn chế và phải thao tác qua console/API dịch vụ, **ngay cả khi tier hỗ trợ RBAC**. Quyền quản trị DBMS không vượt qua giới hạn của nền tảng managed service.

### 3.3. Chọn môi trường theo yêu cầu thực tế

- **Học Cypher, prototype đơn giản:** Community hoặc AuraDB Free có thể đủ nếu không cần các role khác nhau tại database.
- **Production trên Aura có dữ liệu nhạy cảm cần RBAC native:** đánh giá Business Critical hoặc Virtual Dedicated Cloud.
- **Tự host với nhiều nhóm user, SSO, phân quyền nhãn/thuộc tính:** đánh giá Enterprise và các điều kiện giấy phép, vận hành.
- **Bắt buộc dùng Community/Professional:** triển khai authorization chặt ở backend, không cấp Bolt credential trực tiếp cho người dùng cuối, tách instance khi cần ranh giới dữ liệu mạnh; **không trình bày những phương án này là tương đương với DBMS RBAC**.

## 4. Cơ chế RBAC của Neo4j: user → role → privilege

Neo4j Enterprise tổ chức các quyền thành một mô hình:

```text
Users / service accounts
    |                 |
    v                 v
  role A            role B            (một user có nhiều role)
    |                 |
    +--------+--------+
             |
             v
       Effective privileges
         /      |      \
    DATABASE   GRAPH   DBMS
     ACCESS    MATCH   USER/ROLE
               WRITE   PROCEDURE
```

### 4.1. Nguyên tắc của `GRANT`, `DENY` và `REVOKE`

- **`GRANT`:** cho phép một hành động đối với một role trong phạm vi chỉ định.
- **`DENY`:** từ chối hành động được chỉ định. Khi vừa có `GRANT` vừa có `DENY` áp dụng, **`DENY` có ưu tiên** đối với quyền tương ứng.
- **Không có `GRANT` phù hợp:** thông thường **không được phép** thực hiện hành động ấy.
- **`REVOKE GRANT`:** xóa một quyền đã được cấp; khác với việc tạo `DENY`.
- **`REVOKE DENY`:** xóa một quy tắc từ chối; nếu vẫn không có `GRANT`, quyền vẫn không có.
- **`REVOKE`** không kèm `GRANT`/`DENY` có thể thu hồi cả hai dạng đối với quyền đã chỉ định.

Khi một user có nhiều role, các `GRANT` có hiệu lực được xét kết hợp; **một `DENY` phù hợp trong bất kỳ role nào** có thể ngăn quyền do role khác cấp. Đừng chỉ kiểm tra role vừa tạo mà quên user đang có `reader`, `editor`, `admin` hoặc role tự định nghĩa khác.

### 4.2. Các tầng quyền độc lập

| Tầng | Ví dụ privilege | Ý nghĩa |
| --- | --- | --- |
| **Database** | `ACCESS`, `START`, `STOP` | Vào database nào; thao tác vận hành theo quyền |
| **Graph data** | `TRAVERSE`, `READ`, `MATCH`, `CREATE`, `DELETE`, `SET PROPERTY`, `WRITE` | Đi qua node/relationship, đọc thuộc tính, cập nhật graph |
| **Schema** | `SHOW INDEX`, `INDEX MANAGEMENT`, `CONSTRAINT MANAGEMENT` | Xem, tạo hoặc quản lý index/constraint |
| **DBMS** | `CREATE USER`, `ROLE MANAGEMENT`, `SHOW PRIVILEGE` | Quản trị danh tính, vai trò và quyền |
| **Procedures/functions** | `EXECUTE PROCEDURE`, `EXECUTE USER DEFINED FUNCTION`, `EXECUTE BOOSTED...` | Cho phép gọi procedure/UDF và giới hạn quyền thực thi |
| **Data loading** | `LOAD` và chính sách file/URL tương ứng | Kiểm soát nhập dữ liệu từ nguồn ngoài |

**`GRANT ACCESS ON DATABASE neo4j` không tự cấp `MATCH` dữ liệu.** Muốn đọc dữ liệu cần cả quyền vào database **và** quyền graph tương ứng. Tương tự, có `MATCH` trên một label không có nghĩa được phép `CREATE` trên label ấy.

### 4.3. `TRAVERSE` khác `READ` và `MATCH`

| Quyền đọc | Cấp khả năng | Ví dụ |
| --- | --- | --- |
| `TRAVERSE` | Tìm thấy/đi qua node hoặc relationship theo phạm vi được cấp | Có thể xét sự tồn tại/duyệt tới node, chưa chắc đọc được property |
| `READ {prop}` | Đọc một hoặc nhiều thuộc tính của phần tử **đã có quyền đi tới** | Đọc `status` nhưng không mặc nhiên được đi tới mọi node |
| `MATCH {prop}` | Kết hợp `TRAVERSE` và `READ` theo phần tử/properties tương ứng | Cho phép tìm `Order` và đọc `orderId`, `status` |

Một graph query có thể cần quyền trên **cả node đầu, relationship và node đích**. Nếu user được phép đọc node `Order` nhưng relationship `PLACED` bị ẩn, truy vấn duyệt từ `Customer` qua `PLACED` có thể không thấy đường đi.

Đối với đọc bị hạn chế, Neo4j thường **ẩn những phần graph không nhìn thấy**, làm truy vấn trả ít dòng hoặc không có dòng; đối với thao tác ghi thiếu quyền, truy vấn thường **bị từ chối bằng lỗi**. Điều này quan trọng khi viết test: một truy vấn trả `[]` không đủ chứng minh dữ liệu không tồn tại.

## 5. Built-in roles và vai trò đặc biệt của `PUBLIC`

Trên Enterprise/tier hỗ trợ, Neo4j có các built-in role:

| Role | Khả năng mặc định, diễn giải ngắn | Dùng khi |
| --- | --- | --- |
| `PUBLIC` | Tất cả user đều có; mặc định quyền vào home database, thực thi procedure/UDF và `LOAD` ở phạm vi quy định; **không có quyền đọc graph** | Quyền nền; phải audit kỹ |
| `reader` | Đọc và traverse graph trên các database, xem một số thông tin schema | Người dùng cần đọc rộng, chỉ khi thực sự phù hợp |
| `editor` | Đọc và sửa graph, **không tạo tên label/type/property-key mới** | Cập nhật dữ liệu theo schema có sẵn |
| `publisher` | Như editor và có khả năng tạo tên label/relationship type/property-key mới | Ứng dụng nghiệp vụ cần mở rộng tên schema |
| `architect` | Như publisher và quản lý index/constraint | Migration hoặc thiết kế schema |
| `admin` | Quản trị DBMS, user, role, quyền và hầu hết chức năng quản trị | Tài khoản vận hành được kiểm soát chặt |

**Không gán `admin` hoặc `architect` cho tài khoản web service chỉ để “không bị lỗi”.** Một ứng dụng CRUD thường không cần quản lý database, user, index hoặc schema.

`PUBLIC` là role mặc định **không thể loại khỏi user**, nhưng các privilege của nó có thể được chỉnh bởi người quản trị có thẩm quyền. Mặc định `PUBLIC` có một số quyền về procedure/function/LOAD, vì vậy **“role tự tạo rất hẹp” chưa chắc có quyền thực tế hẹp tương ứng** nếu không kiểm tra quyền kế thừa từ `PUBLIC`. Khi harden production, cần cân nhắc khả năng ứng dụng đang dùng những procedure có quyền và rủi ro đặc biệt; không thu hồi hàng loạt mà chưa kiểm thử.

## 6. Thực hành: tạo role chỉ đọc một phần graph

### 6.1. Điều kiện chạy ví dụ

**Chỉ dùng Neo4j Enterprise hoặc AuraDB Business Critical/Virtual Dedicated Cloud (khi lệnh được dịch vụ cho phép).** Trong Community hoặc AuraDB Free/Professional, các lệnh custom role/fine-grained privileges dưới đây **không được hỗ trợ**.

Ví dụ sử dụng database có tên `neo4j` và hai label riêng:
- `SecDemoCustomer {tenantId, customerId, name}`.
- `SecDemoOrder {tenantId, orderId, status, internalNote}`.
- Relationship `(:SecDemoCustomer)-[:SEC_DEMO_PLACED]->(:SecDemoOrder)`.

Để đơn giản, các bước tạo dữ liệu chạy bằng **tài khoản quản trị trong database thử nghiệm**, còn lệnh RBAC chạy trên **`system`**. Đừng dùng trực tiếp trên production hoặc trong database có dữ liệu thật cùng label mà chưa đánh giá.

### 6.2. Tạo dữ liệu demo với quyền ghi phù hợp

Trên database `neo4j`:

```cypher
UNWIND [
  {tenantId: 't1', customerId: 'c1', name: 'An'},
  {tenantId: 't2', customerId: 'c2', name: 'Bình'}
] AS row
MERGE (c:SecDemoCustomer {
  tenantId: row.tenantId,
  customerId: row.customerId
})
SET c.name = row.name;
```

```cypher
UNWIND [
  {tenantId: 't1', customerId: 'c1', orderId: 'o101',
   status: 'PAID', note: 'Dữ liệu nhạy cảm A'},
  {tenantId: 't2', customerId: 'c2', orderId: 'o201',
   status: 'NEW', note: 'Dữ liệu nhạy cảm B'}
] AS row
MATCH (c:SecDemoCustomer {
  tenantId: row.tenantId,
  customerId: row.customerId
})
MERGE (o:SecDemoOrder {
  tenantId: row.tenantId,
  orderId: row.orderId
})
SET o.status = row.status,
    o.internalNote = row.note
MERGE (c)-[:SEC_DEMO_PLACED]->(o);
```

Nếu tạo dữ liệu mẫu trên môi trường dùng chung, thêm constraint duy nhất theo cặp `(tenantId, customerId)` và `(tenantId, orderId)` trước khi triển khai ghi đồng thời. Trong ví dụ học tập chạy tuần tự, `MERGE` giúp lặp lại mà không tạo thêm quan hệ giống hệt.

### 6.3. Tạo role và cấp quyền tối thiểu

Kết nối `system` bằng tài khoản có quyền quản lý role và privilege. Chạy **từng lệnh độc lập**:

```cypher
CREATE ROLE sec_demo_order_reader IF NOT EXISTS;
```

```cypher
GRANT ACCESS ON DATABASE neo4j
TO sec_demo_order_reader;
```

```cypher
GRANT MATCH {tenantId, customerId}
ON GRAPH neo4j NODES SecDemoCustomer
TO sec_demo_order_reader;
```

```cypher
GRANT MATCH {tenantId, orderId, status}
ON GRAPH neo4j NODES SecDemoOrder
TO sec_demo_order_reader;
```

```cypher
GRANT TRAVERSE
ON GRAPH neo4j RELATIONSHIPS SEC_DEMO_PLACED
TO sec_demo_order_reader;
```

Role này được thiết kế để:
- Vào database `neo4j`.
- Tìm hai loại node và đọc **các property đã liệt kê**, không được đọc `name` của customer hoặc `internalNote` của order.
- Đi qua relationship `SEC_DEMO_PLACED` mà không cần đọc property của relationship.
- **Không được ghi graph** vì chưa cấp quyền ghi.

Không nên gán thêm built-in `reader` cho cùng user demo, vì `reader` mặc định có quyền đọc rộng và có thể làm mất mục đích kiểm thử việc giới hạn thuộc tính.

### 6.4. Gán role cho tài khoản test

Trên `system`, với một mật khẩu được **sinh ngẫu nhiên, truyền bằng parameter từ công cụ quản trị/secret manager**, có thể tạo user native:

```cypher
CREATE USER sec_demo_app IF NOT EXISTS
SET PASSWORD $initialPassword CHANGE NOT REQUIRED;
```

```cypher
GRANT ROLE sec_demo_order_reader TO sec_demo_app;
```

Với service account, `CHANGE NOT REQUIRED` giúp dịch vụ có thể kết nối tự động; cần **quy trình đổi mật khẩu và bảo quản secret** bên ngoài code/repository. `IF NOT EXISTS` không cập nhật mật khẩu của user đã tồn tại. Trên Aura, cách tạo native user và cấp quyền còn phụ thuộc tier/quy trình quản lý dịch vụ; xác minh cú pháp hiện được hỗ trợ.

**Không đưa mật khẩu thật vào ví dụ, source control, log hoặc câu lệnh shell hiển thị trong lịch sử terminal.** Parameter chỉ bảo vệ một phần nguy cơ rò rỉ từ query string; hệ thống cấp phát và lưu credential vẫn phải an toàn.

### 6.5. Kiểm chứng quyền với chính tài khoản ít quyền

Đăng nhập bằng `sec_demo_app` và chạy trên database `neo4j`:

```cypher
MATCH (c:SecDemoCustomer)-[:SEC_DEMO_PLACED]->(o:SecDemoOrder)
RETURN c.customerId AS customerId,
       o.orderId AS orderId,
       o.status AS status
ORDER BY orderId;
```

Role đã có `MATCH` trên các node và `TRAVERSE` trên quan hệ; câu trên chỉ yêu cầu những property được cấp, nên dự kiến trả hai đơn trong bộ dữ liệu mẫu.

Thử đọc thuộc tính nhạy cảm:

```cypher
MATCH (o:SecDemoOrder {orderId: 'o101'})
RETURN o.internalNote AS internalNote;
```

Đừng lấy việc thấy `null`/giá trị không được đọc được làm kết luận “dữ liệu đã bị xóa”. Hãy đối chiếu với kết quả từ tài khoản có quyền phù hợp và kiểm tra effective privileges. Truy vấn này **không được cung cấp thông tin nhạy cảm** cho role demo theo chính sách dự định.

Thử ghi (dự kiến không được phép):

```cypher
MATCH (o:SecDemoOrder {orderId: 'o101'})
SET o.status = 'CANCELLED';
```

Khi thử bằng user chỉ đọc, thao tác `SET` phải bị chặn bởi chính sách. Thử nghiệm âm tính như vậy nên thực hiện trên **database riêng** hoặc dùng dữ liệu được phép thay đổi, phòng khi bạn vô tình đăng nhập bằng tài khoản admin.

### 6.6. Xem quyền có hiệu lực

Trên `system` với quyền quản trị phù hợp:

```cypher
SHOW ROLES;
```

```cypher
SHOW ROLE sec_demo_order_reader PRIVILEGES AS COMMANDS;
```

```cypher
SHOW USER sec_demo_app PRIVILEGES;
```

```cypher
SHOW ROLES WITH USERS;
```

`SHOW ROLE ... PRIVILEGES` giúp kiểm tra role, còn `SHOW USER ... PRIVILEGES` giúp kiểm tra **tập quyền của user nhận nhiều role**. Kết quả phụ thuộc native/external authentication và quyền người đang chạy lệnh. Với LDAP/OIDC, một số thông tin về user ngoài nhà cung cấp native không thể liệt kê cho user khác theo cách giống hệt tài khoản native.

## 7. Đọc hẹp hơn bằng `GRANT` và từ chối bằng `DENY`

### 7.1. Khi không cần đọc, đừng cấp quyền

Một thiết kế an toàn thường bắt đầu bằng:
- `GRANT ACCESS` chỉ cho database cần dùng.
- `GRANT MATCH` chỉ cho label/relationship/properties cần thiết.
- **Không cấp `WRITE`**, `INDEX MANAGEMENT`, `ROLE MANAGEMENT` nếu không phục vụ nghiệp vụ.

Điều này có ưu điểm hơn việc cấp `MATCH {*} ON GRAPH *` rồi cố viết nhiều lệnh `DENY` loại trừ: mọi label/property mới xuất hiện sau này sẽ **không tự được mở quyền** nếu không khớp grant hiện có.

### 7.2. `DENY` vượt `GRANT` nhưng không thay thế `REVOKE`

Giả sử trong môi trường thử nghiệm có role đọc rộng:

```cypher
CREATE ROLE sec_demo_broad_reader IF NOT EXISTS;
```

```cypher
GRANT ACCESS ON DATABASE neo4j TO sec_demo_broad_reader;
```

```cypher
GRANT MATCH {*} ON GRAPH neo4j TO sec_demo_broad_reader;
```

Nếu muốn tạm chặn một label đặc biệt:

```cypher
DENY MATCH {*} ON GRAPH neo4j NODES SecDemoSecret
TO sec_demo_broad_reader;
```

`DENY` chặn quyền phù hợp **dù role khác có thể đã cấp `GRANT` rộng**. Nhưng grant rộng vẫn còn đó. Muốn **loại bỏ quy tắc DENY**, dùng:

```cypher
REVOKE DENY MATCH {*} ON GRAPH neo4j NODES SecDemoSecret
FROM sec_demo_broad_reader;
```

Muốn loại bỏ **grant rộng**:

```cypher
REVOKE GRANT MATCH {*} ON GRAPH neo4j
FROM sec_demo_broad_reader;
```

Bốn thao tác có nghĩa khác nhau: cấp, từ chối, thu hồi cấp và thu hồi từ chối. Trên production, ưu tiên **grant hẹp** hơn là giữ grant rộng và duy trì một danh sách deny khó kiểm chứng.

### 7.3. Cấp quyền và thu hồi quyền trên thuộc tính cụ thể

Role demo ban đầu có quyền đọc ba property của `SecDemoOrder`. Nếu requirement đổi, chỉ cho đọc `tenantId` và `orderId`:

```cypher
REVOKE GRANT MATCH {tenantId, orderId, status}
ON GRAPH neo4j NODES SecDemoOrder
FROM sec_demo_order_reader;
```

```cypher
GRANT MATCH {tenantId, orderId}
ON GRAPH neo4j NODES SecDemoOrder
TO sec_demo_order_reader;
```

Đây là một **migration policy**, không phải một phần bắt buộc của demo trước đó. Sau khi làm, những truy vấn cần `status` phải được kiểm thử lại. Đừng tự ý bỏ một quyền rồi để ứng dụng production phát sinh lỗi hoặc trả kết quả thiếu.

## 8. Phân quyền theo thuộc tính và tenant: có thể làm gì, không thể làm gì?

### 8.1. Giới hạn bằng label/relationship/property

Neo4j Enterprise và các tier AuraDB hỗ trợ có thể phân quyền đọc trên:
- Node theo **label**.
- Relationship theo **type**.
- Những **property cụ thể** của các phần tử đó.

Đó là **fine-grained graph authorization**, khác với database-wide role `reader`. Tuy nhiên, phân quyền đọc property **không tự bảo đảm** một user chỉ thấy những node có cùng `tenantId`. Với multi-tenant, phải xét quy tắc theo giá trị thuộc tính hoặc ranh giới database/instance.

### 8.2. Property-based access control (PBAC)

Trong môi trường hỗ trợ, Neo4j có thể gắn quyền với điều kiện thuộc tính. Ví dụ **một role cố định chỉ thấy node đơn hàng có `tenantId = 't1'`**:

```cypher
CREATE ROLE sec_demo_t1_reader IF NOT EXISTS;
```

```cypher
GRANT ACCESS ON DATABASE neo4j TO sec_demo_t1_reader;
```

```cypher
GRANT MATCH {tenantId, orderId, status}
ON GRAPH neo4j FOR (o:SecDemoOrder)
WHERE o.tenantId = 't1'
TO sec_demo_t1_reader;
```

Chú ý:
- Điều kiện `'t1'` là **giá trị trong privilege**, không phải `$tenantId` động được ứng dụng truyền cho mỗi request.
- Role chỉ cấp quyền trên node `SecDemoOrder`; muốn duyệt từ `Customer` qua `SEC_DEMO_PLACED` phải cấp thêm quyền có điều kiện phù hợp trên các node/relationship liên quan.
- Nếu user đồng thời có role khác với quyền `MATCH {*}` rộng và **không có deny thích hợp**, kết quả có thể rộng hơn ý định.
- **Thuộc tính dùng để xét PBAC phải được bảo vệ khỏi sửa trái phép.** Nếu user có thể sửa `tenantId`, họ có thể thay đổi điều kiện áp quyền.
- Property-based privilege chỉ cho phép một điều kiện thuộc tính trên mỗi privilege; việc biểu diễn logic phức tạp cần thiết kế và kiểm thử kỹ.

**Cảnh báo quan trọng:** với PBAC, một số `DENY` dựa trên so sánh thuộc tính có thể **fail open** nếu điều kiện không đánh giá được (ví dụ property `null` hoặc vắng mặt). Vì thế thiết kế **`GRANT` theo allowlist có điều kiện** thường an toàn và dễ chứng minh hơn mô hình `GRANT` rộng + `DENY tenantId <> 't1'`.

### 8.3. RBAC, PBAC và ABAC không phải một tính năng duy nhất

- **RBAC**: role nhận privileges rồi gán cho user.
- **PBAC**: quyền gắn điều kiện trên **giá trị thuộc tính graph**, trong phạm vi phiên bản hỗ trợ.
- **ABAC**: quyền/role có thể được quyết định qua **thuộc tính danh tính hoặc auth rule** ở những phiên bản Neo4j mới có hỗ trợ.

Ví dụ từ Neo4j **2026.06** có user tags cho một số tính năng liên quan ABAC; những khả năng auth rule/Cypher 25 mới còn được bổ sung theo từng release. **Không mặc định cấu hình ABAC hoạt động trên Neo4j 5.x cũ hoặc mọi Aura tier**, và không copy chính sách ABAC thử nghiệm vào production mà chưa xác minh tài liệu đúng bản đang chạy.

### 8.4. Multi-tenant và kiến trúc ứng dụng

| Phương án | Ưu điểm | Điều kiện/rủi ro |
| --- | --- | --- |
| Một database, app luôn lọc `tenantId` | Đơn giản hơn khi chưa có RBAC native | Phụ thuộc việc mọi code path đều kiểm tra quyền; credential DB thường có quyền rộng |
| Custom role/PBAC cho mỗi tenant | Chính sách một phần được DBMS cưỡng chế | Số role lớn, điều kiện phức tạp, cấp quyền nhất quán trên traversal, hạn chế theo edition |
| Database riêng cho các nhóm tenant | Ranh giới database rõ hơn | Cần edition/tier cho phép nhiều database; chi phí vận hành |
| Instance riêng cho tenant nhạy cảm | Tách hạ tầng và credential rõ ràng | Chi phí cao hơn; vận hành và backup phân tán |
| RBAC/PBAC + app authorization | Phòng vệ nhiều lớp | Phải kiểm thử toàn bộ chính sách và quyền hiệu lực |

Một truy vấn `MATCH (o:Order {tenantId: $tenantId})` là điều kiện nghiệp vụ hữu ích, **không thay thế kiểm soát ở cấp database** nếu người dùng có thể kết nối Bolt trực tiếp bằng credential được cấp quyền rộng.

## 9. Procedure, APOC, GDS và đặc quyền tăng cường

### 9.1. Khả năng thực thi procedure không có nghĩa chỉ được đọc

Ứng dụng Neo4j có thể dùng:
- `CALL db.index.fulltext.queryNodes(...)` để tìm kiếm.
- Các procedure APOC để nhập/xuất, xử lý theo lô hoặc gọi HTTP.
- GDS `gds.*` để project graph và chạy thuật toán.
- Procedure/UDF tự viết bằng Java.

Quyền của user không chỉ liên quan `MATCH`/`WRITE`. Cần kiểm tra:
- `EXECUTE PROCEDURE` hoặc `EXECUTE USER DEFINED FUNCTION` được cấp cho phạm vi tên nào.
- Có quyền **boosted** hay không, tức thực thi trong ngữ cảnh quyền nâng cao; phải thận trọng vì có thể làm lộ dữ liệu ngoài quyền đọc thông thường.
- Cấu hình `allowlist`/`unrestricted` của DBMS trên môi trường tự vận hành, cùng policy file/network và edition.
- Tính khả dụng của APOC Core/Extended hoặc GDS trên tier đang dùng.

### 9.2. Vai trò `PUBLIC` cần được audit

Theo default hiện hành, `PUBLIC` có thể cho phép gọi nhiều procedure/UDF và `LOAD`. Không kết luận “custom role chỉ có MATCH nên mọi API khác đều vô hiệu”. Nếu ứng dụng không cần gọi procedure hoặc nạp dữ liệu, đánh giá phương án **thu hẹp quyền PUBLIC** phù hợp chính sách bảo mật, sau khi thử nghiệm tác động lên ứng dụng/driver và các tiện ích vận hành.

**Không sao chép tùy tiện lệnh `DENY EXECUTE PROCEDURE *` hoặc thu hồi toàn bộ quyền PUBLIC trong hệ thống đang chạy.** Nó có thể phá các chức năng nền hoặc workflow hợp lệ. Nên đo quyền thực tế, ghi change request, backup/rollback policy và thử trên staging.

## 10. Kiểm thử phân quyền: phải kiểm tra cả đường được phép và bị cấm

Một ma trận test đáng tin cậy dùng **tài khoản thật tương ứng role**, không chỉ xem nội dung `SHOW ROLE ... PRIVILEGES`:

| Tình huống | Kỳ vọng với `sec_demo_order_reader` | Loại test |
| --- | --- | --- |
| Đăng nhập và đọc `SecDemoOrder.orderId`/`status` | Thành công | Positive |
| Duyệt `Customer-[:SEC_DEMO_PLACED]->Order` | Thành công với property được cấp | Positive |
| Đọc `SecDemoOrder.internalNote` | Không xem được giá trị nhạy cảm | Negative |
| `SET o.status = 'CANCELLED'` | Bị từ chối ghi | Negative |
| `CREATE (:SecDemoOrder {...})` | Bị từ chối ghi | Negative |
| `CREATE INDEX`/`DROP CONSTRAINT` | Bị từ chối quản lý schema | Negative |
| `CREATE USER`/`GRANT ROLE` | Bị từ chối quản trị RBAC | Negative |
| Đọc node khác label không được cấp | Không hiện nội dung graph tương ứng | Negative |
| Gắn thêm role `reader` cho test user | Có thể làm quyền đọc rộng hơn | Regression/hardening |
| Thêm property `internalNote2` mới | Không tự được đọc nếu grant chỉ liệt kê property | Regression |

**Lưu ý:** Không chạy câu `DELETE`, `DROP` hoặc `CREATE` để kiểm thử quyền trên dữ liệu production. Dùng bản sao/trang test. Nếu vô tình chạy bằng user admin, thao tác có thể thành công và gây hậu quả thật.

### 10.1. Chẩn đoán kết quả `[]` và lỗi thiếu quyền

- **Truy vấn đọc trả 0 dòng** có thể do không có dữ liệu, không được traverse node/relationship, điều kiện WHERE sai hoặc dữ liệu thuộc tenant khác.
- **Property không đọc được** có thể là restriction hoặc property thực sự không tồn tại; đối chiếu cùng dữ liệu với account có quyền.
- **Truy vấn ghi báo thiếu quyền** cho biết cần xem quyền tương ứng, nhưng không có nghĩa nên cấp `admin`.
- **Lệnh quản trị không tồn tại** có thể do edition/tier không hỗ trợ, không chỉ do thiếu privilege.
- **`SHOW ROLE` chỉ cho thấy role**; user nhận nhiều role, `PUBLIC` và external auth có thể làm quyền hiệu lực khác dự đoán.

## 11. Java Driver: ứng dụng phải kết nối với danh tính có quyền phù hợp

### 11.1. Không sử dụng admin credential cho request thông thường

Ví dụ Neo4j Java Driver 6.x đọc danh sách đơn:

```java
import java.util.Map;
import org.neo4j.driver.AuthTokens;
import org.neo4j.driver.Driver;
import org.neo4j.driver.GraphDatabase;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

String uri = System.getenv("NEO4J_URI");
String username = System.getenv("NEO4J_READ_USER");
String password = System.getenv("NEO4J_READ_PASSWORD");

// NEO4J_URI nên là neo4j+s://... hoặc bolt+s://...
// theo chứng chỉ và cấu hình server thực tế.
try (Driver driver = GraphDatabase.driver(
        uri, AuthTokens.basic(username, password));
     Session session = driver.session(
        SessionConfig.forDatabase("neo4j"))) {

    var orders = session.executeRead(tx ->
        tx.run(
            """
            MATCH (o:SecDemoOrder)
            WHERE o.tenantId = $tenantId
            RETURN o.orderId AS id, o.status AS status
            ORDER BY id
            """,
            Map.of("tenantId", "t1")
        ).list(record -> Map.of(
            "id", record.get("id").asString(),
            "status", record.get("status").asString()
        ))
    );

    System.out.println(orders);
}
```

Trong hệ thống thực tế, **tạo và dùng chung `Driver` một lần** trong vòng đời ứng dụng; đoạn `try (Driver ...)` ở đây minh họa chương trình standalone. Mỗi operation tạo session riêng và đóng sau khi tiêu thụ kết quả.

Tài khoản `NEO4J_READ_USER` phải được cấu hình **trước** bằng RBAC tương ứng trong môi trường hỗ trợ; env var **không tạo role**. Mã Java cần kiểm soát `tenantId` từ ngữ cảnh đã xác thực, không tin mọi giá trị người gọi cung cấp. Dù đã có PBAC, giữ điều kiện nghiệp vụ vẫn giúp query chọn lọc và bảo vệ nhiều lớp.

### 11.2. Khi ứng dụng cần cả đọc lẫn ghi

Một cách phân quyền là dùng **hai credential khác nhau**:
- Credential reader cho API báo cáo và màn hình.
- Credential writer cho service chịu trách nhiệm thay đổi graph, với role ghi **đúng schema**.

Tuy nhiên, không tạo hai `Driver` cho mỗi request; quản lý mỗi Driver/pool dùng chung theo cấu hình. Mỗi bí mật có vòng đời riêng, được cấp từ secret manager, có rotation, không log/password dump.

Khi credential writer dùng `executeWrite(...)`, callback có thể bị driver retry sau transient failure. Phải bảo đảm thao tác ghi idempotent và có constraint nghiệp vụ. **RBAC không giải quyết duplicate write do retry**, giống như transaction không thay thế kiểm tra tenant/ownership.

### 11.3. Impersonation và người dùng cuối

Trong những triển khai hỗ trợ **impersonation** của Java Driver, một connection có thể chạy truy vấn dưới danh tính được chỉ định nếu tài khoản gốc có quyền impersonate phù hợp. Đây là tính năng có điều kiện về edition, quyền và chính sách bảo mật; không thể chỉ đặt một username bất kỳ trong client rồi kỳ vọng được impersonate.

Không dùng impersonation để thay thế authentication của end user hoặc tùy ý cấp quyền `IMPERSONATE` cho tài khoản ứng dụng. Nếu hệ thống nhiều tenant, mô hình mapping user → role → DBMS privilege phải được thiết kế, thử nghiệm và audit.

## 12. Spring Data Neo4j và Spring Security: hai tầng trách nhiệm

Với Spring Data Neo4j, repository hoặc `Neo4jClient`/`ReactiveNeo4jClient` thường dùng credential cấu hình tại datasource/driver. Spring Security kiểm soát request và quyền ở tầng ứng dụng, **không tự cấp/tước Neo4j role khi gọi repository**.

Ví dụ mô tả luồng ứng dụng:

```java
@PreAuthorize("hasAuthority('order:read')")
public List<OrderSummary> findOrdersForCurrentCustomer(
        String tenantId, String customerId) {
    // Thực tế: tenantId/customerId phải được lấy và kiểm chứng
    // từ authenticated principal / authorization context.
    return orderReadRepository.findSummaries(tenantId, customerId);
}
```

Đoạn trên chỉ mô tả **một lớp kiểm tra API**; nó cần một repository/interface và security configuration thật để biên dịch, không thay thế kiểm tra tenant/ownership. Một người dùng có `order:read` không mặc nhiên được xem mọi đơn cùng database.

Những điểm cần nhớ:

1. Credential DB trong Spring thường là **service identity**, không phải identity của HTTP user.
2. `@PreAuthorize` giới hạn đường đi trong service nhưng không thay đổi quyền Bolt của credential.
3. Nếu service dùng admin credential, một lỗ hổng injection hoặc một query chạy sai có thể vượt qua giả định phân quyền ở service.
4. Nên dùng custom Cypher/DTO để chỉ đọc property được cấp; khi repository hydrate một entity có property bị ẩn, mapping có thể nhận giá trị thiếu hoặc khác dự kiến.
5. Kiểm thử cả **role tại DB** và **authorization tại service**, gồm trường hợp user truy cập sai tenant, sai owner và sai role.
6. Triển khai `reader`, `writer` hoặc `reporter` bằng các tài khoản/role phù hợp, thay vì cố dùng một tài khoản `admin` cho mọi bean và job.

## 13. LDAP, OIDC/SSO, Aura và quyền thực tế

### 13.1. Xác thực ngoài không tự định nghĩa quyền graph

Neo4j Enterprise có những cách tích hợp LDAP/OIDC tùy cấu hình và phiên bản. Identity provider xác minh danh tính hoặc cung cấp thuộc tính/group; Neo4j vẫn phải quyết định quyền theo role/privilege đã ánh xạ.

Những lỗi thường gặp:
- Token hợp lệ nhưng role mapping chưa có, nên user vào được nhưng không đọc được data.
- Một group IdP bị cấp role quá rộng, khiến mọi user trong group nhìn được graph.
- Thay đổi group/user trong IdP nhưng phiên đăng nhập và token/cache chưa phản ánh ngay.
- Cấu hình nhiều auth provider có thể làm quyền hiệu lực khác dự kiến, cần test bằng account thật.

### 13.2. Aura tổ chức và database không phải một tài khoản

Trong Aura, tài khoản quản lý tổ chức, project và instance **không đồng nhất** với DBMS user dùng Bolt. Khi thiết kế quyền:

- Xác định người nào được quản lý **Aura Console**.
- Xác định DBMS user hoặc phương thức SSO nào được **kết nối và truy vấn graph**.
- Kiểm tra tier có RBAC/SSO database hay không, thay vì dựa vào việc console có danh sách thành viên.
- Nếu chỉ ở Free/Professional, không soạn migration `CREATE ROLE` như thể nó sẽ chạy; thiết kế lại hoặc nâng tier khi yêu cầu DBMS-enforced RBAC là bắt buộc.

## 14. Vận hành RBAC an toàn: cấu hình, thay đổi và giám sát

### 14.1. Policy as code

Dù quản trị privilege bằng Cypher, nên lưu thiết kế role trong migration được review, với:

- Tên role nói rõ nghiệp vụ: `order_reader`, `order_writer`, `schema_migrator`.
- Danh sách database, label, relationship, property cần truy cập.
- Người sở hữu/đơn vị phê duyệt, lý do cần privilege.
- Tài khoản nào được gán role và thời gian rà soát.
- Test positive/negative sau mỗi thay đổi schema.
- Phương án rollback `REVOKE` hoặc khôi phục grant cũ.

Không sử dụng `CREATE OR REPLACE ROLE` bừa bãi: câu lệnh thay role hiện có, có thể làm mất privileges cũ. Khi muốn tạo role idempotent mà không ghi đè cấu hình hiện có, dùng `CREATE ROLE ... IF NOT EXISTS` rồi **đối soát privilege**, không giả định role cũ đã đúng.

### 14.2. Quản lý mật khẩu và secret

- Không commit username/password có đặc quyền cao vào repository.
- Dùng secret manager và rotation, thu hồi credential không còn dùng.
- Dùng TLS khi kết nối qua mạng; xác minh certificate và URI phù hợp.
- Giới hạn truy cập mạng tới Bolt, nhất là database tự vận hành.
- Ghi log hành động quản trị/audit theo tính năng edition/tier; không log mật khẩu, dữ liệu nhạy cảm hoặc access token.

### 14.3. Thao tác đọc/ghi khi đang thay role

Nếu đổi quyền user khi họ đang có session/transaction hoặc connection pool sẵn, cần kiểm tra hành vi áp dụng thay đổi quyền theo phiên bản và phạm vi transaction hiện tại. **Xóa user không nhất thiết tự chấm dứt các session/transaction đang chạy**. Với sự cố credential bị lộ, đừng chỉ sửa role rồi coi mọi kết nối độc hại đã mất hiệu lực; thực hiện quy trình thu hồi credential, kết thúc session/transaction khi cần và rà soát audit.

## 15. Những giới hạn và hiểu nhầm thường gặp

| Quan niệm sai | Thực tế |
| --- | --- |
| “Community có nhiều native user nên có RBAC.” | Community không có role, mọi user có quyền admin ngầm định; không đáp ứng least-privilege trong DBMS |
| “Aura Professional trả phí nên có phân quyền graph chi tiết.” | RBAC/fine-grained được liệt kê cho Business Critical và Virtual Dedicated Cloud, không phải Professional |
| “Admin Aura Console cũng là admin mọi dữ liệu Neo4j.” | Quyền console và quyền DBMS là hai lớp khác nhau |
| “`GRANT ACCESS` là đọc được graph.” | Cần quyền `TRAVERSE`/`READ`/`MATCH` tương ứng |
| “`READ` property là tự tìm thấy node.” | Cần `TRAVERSE`; `MATCH` kết hợp cả hai |
| “Role A `GRANT` thì role B `DENY` không liên quan.” | Quyền hiệu lực xét nhiều role; `DENY` có ưu tiên |
| “`DENY` xóa `GRANT`.” | Cả hai vẫn tồn tại; phải `REVOKE` khi muốn gỡ |
| “Không thấy node nghĩa là node không tồn tại.” | Có thể node/relationship bị ẩn do read privileges |
| “`MATCH {*}` đọc được mọi node nên luôn đúng.” | Quá rộng; khi thêm label/property mới có thể mở quyền ngoài dự định |
| “PBAC dùng `DENY tenantId <> x` là luôn kín.” | Điều kiện sai/missing/null có thể gây **fail-open** nếu đã có grant rộng |
| “Cấp `reader` rồi dùng custom role để hạn chế lại.” | `reader` có quyền rộng; muốn giới hạn cần thiết kế `DENY` phù hợp hoặc không cấp role đó |
| “Hễ có `@PreAuthorize` thì đã có Neo4j RBAC.” | Quyền Spring không tự thay quyền của credential Bolt |
| “Procedure chạy được nghĩa là an toàn.” | Kiểm tra `EXECUTE`, boosted, file/network permissions và side effects |
| “Role chỉ đọc thì có thể bỏ qua `PUBLIC`.” | `PUBLIC` được mọi user kế thừa và có những quyền nền cần audit |
| “RBAC tự giải quyết quyền xem từng đơn theo session HTTP.” | Cần identity mapping, property-based privileges hoặc authorization theo ứng dụng, không tự suy từ request |
| “Mọi lệnh quản trị có quyền admin đều chạy trên Aura.” | Managed service giới hạn các thao tác hạ tầng theo tier |
| “Thêm role mới và cấp quyền là đủ.” | Cần test bằng chính user, kiểm tra group/role khác và log |

## 16. Checklist thiết kế quyền cho một service Neo4j

1. **Edition/tier:** Community, Enterprise, Aura Free/Professional/Business Critical/Virtual Dedicated Cloud? Chính xác những capability nào có trong bản đang dùng?
2. **Danh tính:** user/service account native hay LDAP/OIDC? Ai sở hữu và xoay vòng secret?
3. **Role nghiệp vụ:** tách read-only, writer, migration và admin; tránh tài khoản dùng chung quyền cao.
4. **Database scope:** user phải vào database nào? Chỉ cấp `ACCESS` cần thiết.
5. **Graph scope:** label/type/property nào? Cần `TRAVERSE`, `READ` hay `MATCH`?
6. **Write scope:** có cần `CREATE`, `DELETE`, `SET PROPERTY` hay `WRITE` không? Có tạo property key mới không?
7. **Schema/DBMS:** ai được quản lý index, constraint, user, role, load và procedure?
8. **Role tổng hợp:** user có role `reader`/`editor`/`PUBLIC`/external group nào thêm không?
9. **Tenant:** database-level, PBAC/ABAC hay application authorization? Có đường đi xuyên tenant không?
10. **Test:** positive và negative bằng credential ít quyền thật; kiểm tra dữ liệu bị ẩn và lỗi ghi.
11. **Java/Spring:** không dùng admin credential cho API; quản lý Driver, transaction, secret và input.
12. **Giám sát:** audit quyền, thay đổi role, login bất thường, procedure và quá trình thu hồi credential.
13. **Upgrade:** đối chiếu Cypher version, neo4j edition, Aura feature matrix và các API quản trị đã đổi.

## 17. Bài tập tự luyện

1. Một nhóm dùng Community Edition và tạo ba user native. Họ muốn một user chỉ đọc và một user chỉ ghi. Có thể làm bằng RBAC không? Nêu lựa chọn thay thế và giới hạn bảo mật.
2. Lập bảng khác nhau giữa AuraDB Free, Professional, Business Critical và Virtual Dedicated Cloud về RBAC, khả năng quản lý database và kiểm soát quyền graph.
3. Giải thích vì sao `GRANT ACCESS ON DATABASE neo4j` chưa đủ để chạy `MATCH (n) RETURN n`.
4. Tạo role `report_reader` chỉ được đọc `Order(orderId, status)` và đi theo relationship `PLACED` từ `Customer`. Viết các `GRANT` cần thiết trong môi trường hỗ trợ.
5. Một user có `reader` và một custom role hạn chế `Order`. Có chắc user chỉ đọc `Order` không? Phân tích cách hợp nhất quyền.
6. Khác nhau giữa `REVOKE GRANT` và `REVOKE DENY` là gì? Viết câu lệnh thu hồi một quyền `MATCH` đã cấp.
7. Tại sao việc dùng `DENY MATCH {*} FOR (n:Order) WHERE n.tenantId <> 't1'` có thể nguy hiểm nếu `tenantId` thiếu?
8. Kiểm thử một `SecDemoOrder` có `internalNote`. Hãy mô tả cách chứng minh role đọc đơn không được xem giá trị nhưng vẫn đọc được `status`.
9. Trong Spring Boot, một service có `@PreAuthorize` nhưng dùng credential Neo4j `admin`. Nêu ít nhất ba rủi ro và cách giảm thiểu.
10. Một ứng dụng dùng APOC để import JSON, GDS để phân tích graph và Java Driver để đọc đơn. Đề xuất cách cấp quyền procedure/function và tách job phân tích khỏi API.
11. Sự cố credential writer bị lộ: vì sao chỉ `DROP USER` chưa chắc chấm dứt ngay mọi transaction đang chạy? Đề xuất checklist ứng phó.
12. Thiết kế quy trình chuyển từ AuraDB Professional sang tier hỗ trợ DBMS RBAC, bao gồm migration role, test quyền, quản lý secret và rollback.

## 18. Ghi nhớ

- Neo4j RBAC điều khiển **user → role → privilege** với các phạm vi **DBMS, database, graph, label/type, property**.
- **`GRANT` cấp, `DENY` chặn, `REVOKE` thu hồi**. `DENY` có ưu tiên khi áp dụng; user có thể có nhiều role và đều mang quyền của `PUBLIC`.
- **`TRAVERSE`, `READ` và `MATCH` khác nhau**. Quyền vào database chưa phải quyền đọc graph; quyền đọc property chưa phải quyền đi tới node.
- **Community Edition không có role/fine-grained RBAC**; **Enterprise Edition có**. Trên AuraDB, **Business Critical và Virtual Dedicated Cloud hỗ trợ RBAC**, còn **Free và Professional không** theo bảng tính năng hiện hành.
- Built-in `reader` có quyền đọc rộng, `editor` có quyền ghi dữ liệu, `architect` quản lý schema và `admin` quản trị DBMS; không gán cho service chỉ vì tiện.
- **PBAC/ABAC cần edition, version, policy và thử nghiệm cụ thể**; tránh `DENY` dựa trên thuộc tính có thể fail-open khi dữ liệu thiếu.
- **Spring Security và quyền Aura Console không thay thế Neo4j DBMS RBAC**. Java Driver sử dụng quyền của identity kết nối; hãy tách credential và kiểm tra bằng user thật.
- **Least privilege + kiểm thử âm tính + quản lý secret + TLS + audit** là một quy trình liên tục, không phải một lần chạy `GRANT`.

### Tài liệu tham khảo chính thức

- [Neo4j Operations Manual — Authentication and authorization](https://neo4j.com/docs/operations-manual/current/authentication-authorization/)
- [Neo4j Operations Manual — Role-based access control](https://neo4j.com/docs/operations-manual/current/authentication-authorization/manage-privileges/)
- [Neo4j Operations Manual — Built-in roles and privileges](https://neo4j.com/docs/operations-manual/current/authentication-authorization/built-in-roles/)
- [Neo4j Operations Manual — Manage roles](https://neo4j.com/docs/operations-manual/current/authentication-authorization/manage-roles/)
- [Neo4j Operations Manual — Manage users](https://neo4j.com/docs/operations-manual/current/authentication-authorization/manage-users/)
- [Neo4j Operations Manual — Read privileges](https://neo4j.com/docs/operations-manual/current/authentication-authorization/privileges-reads/)
- [Neo4j Operations Manual — Write privileges](https://neo4j.com/docs/operations-manual/current/authentication-authorization/privileges-writes/)
- [Neo4j Operations Manual — Database privileges](https://neo4j.com/docs/operations-manual/current/authentication-authorization/database-administration/)
- [Neo4j Operations Manual — Property-based access control](https://neo4j.com/docs/operations-manual/current/authentication-authorization/property-based-access-control/)
- [Neo4j Operations Manual — RBAC limitations](https://neo4j.com/docs/operations-manual/current/authentication-authorization/limitations/)
- [Neo4j Operations Manual — Procedure and function privileges](https://neo4j.com/docs/operations-manual/current/authentication-authorization/manage-execute-permissions/)
- [Neo4j Aura — Cypher and Aura](https://neo4j.com/docs/cypher-manual/current/introduction/cypher-aura/)
- [Neo4j — Pricing and edition feature comparison](https://neo4j.com/pricing/)
- [Neo4j Java Driver Manual — Connect to the database](https://neo4j.com/docs/java-manual/current/connect/)
- [Spring Data Neo4j — Reference](https://docs.spring.io/spring-data/neo4j/reference/)
