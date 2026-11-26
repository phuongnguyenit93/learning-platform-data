# ON CREATE SET và ON MATCH SET khi đồng bộ dữ liệu trong Neo4j

> **Chương:** Tạo và cập nhật  
> **Mô-đun:** `DATABASE_ENGINE_GRAPH_NEO4J` — sử dụng Neo4j để mô hình hóa dữ liệu liên kết theo property graph và truy vấn quan hệ, đường đi bằng Cypher.

Trong một hệ thống quản lý nhân viên, người dùng hoặc dự án, dữ liệu thường đến từ nhiều lần đồng bộ: lần đầu cần **tạo thực thể**, những lần sau cần **cập nhật thực thể đã có**. Cypher cung cấp `MERGE` để tìm hoặc tạo theo mẫu; đi kèm với nó, `ON CREATE SET` và `ON MATCH SET` cho phép chạy **hai nhánh cập nhật khác nhau** tùy kết quả của `MERGE`.

Nhờ đó, ứng dụng có thể ghi nhận ngày tạo chỉ một lần, cập nhật lần đồng bộ gần nhất, giữ định danh nghiệp vụ ổn định và xử lý riêng thuộc tính của **nút (node)** hoặc **quan hệ (relationship)**. Việc hiểu chính xác hai nhánh này còn giúp thiết kế nhập dữ liệu hàng loạt, constraint, truy vấn Java Driver và Spring Data Neo4j mà không tạo trùng đồ thị.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích thời điểm thực thi `ON CREATE SET` và `ON MATCH SET` trong một mệnh đề `MERGE`.
2. Viết truy vấn tạo hoặc cập nhật nút bằng khóa nghiệp vụ, đồng thời bảo toàn thuộc tính chỉ gán khi tạo.
3. Dùng `SET` không điều kiện khi một thuộc tính cần cập nhật ở **cả hai nhánh**.
4. Đồng bộ hai nút và quan hệ giữa chúng bằng các `MERGE` riêng, đặt xử lý tạo/khớp đúng vị trí.
5. Nhận diện các lỗi thường gặp: thiếu constraint, khóa không ổn định, giá trị `null`, mẫu quan hệ quá rộng, dữ liệu bị ghi đè khi đồng bộ.
6. Vận dụng tham số, `UNWIND` và giao dịch từ Java Driver hoặc truy vấn tùy biến của Spring Data Neo4j.

## 2. Cú pháp cốt lõi và ý nghĩa hai nhánh

Cú pháp khái quát:

~~~cypher
MERGE (n:Label {businessKey: $businessKey})
ON CREATE SET
  n.createdAt = datetime(),
  n.name = $name
ON MATCH SET
  n.lastSyncedAt = datetime(),
  n.name = $name
RETURN n;
~~~

Đọc theo thứ tự:

1. `MERGE` kiểm tra có nút mang nhãn `Label` với thuộc tính `businessKey` tương ứng hay không.
2. Nếu **không có mẫu phù hợp**, `MERGE` tạo mẫu mới; các lệnh gán sau `ON CREATE SET` được thực thi.
3. Nếu **có mẫu phù hợp**, `MERGE` dùng thành phần đã khớp; các lệnh gán sau `ON MATCH SET` được thực thi.
4. `RETURN` trả về dữ liệu sau thao tác, để ứng dụng có thể xác nhận kết quả.

`ON CREATE SET` và `ON MATCH SET` là **các nhánh của `MERGE`**, không phải câu lệnh đứng độc lập sau `CREATE` hoặc `MATCH`. Chúng cũng không phải câu lệnh điều kiện tổng quát cho mọi mệnh đề trong truy vấn.

| Câu lệnh | Tác dụng | Chạy khi nào? |
|---|---|---|
| `MERGE (n:Label {id: $id})` | Tìm hoặc tạo mẫu | Mỗi lần xử lý dòng đầu vào |
| `ON CREATE SET n.createdAt = datetime()` | Gán thuộc tính riêng cho dữ liệu mới | Mẫu của **MERGE ngay trước đó** vừa được tạo |
| `ON MATCH SET n.lastSyncedAt = datetime()` | Gán thuộc tính riêng cho dữ liệu đã khớp | Mẫu của **MERGE ngay trước đó** đã tồn tại |
| `SET n.name = $name` | Gán thuộc tính không điều kiện | Khi dòng truy vấn đi tới `SET`, ở cả hai nhánh |

Bạn có thể dùng chỉ `ON CREATE SET`, chỉ `ON MATCH SET` hoặc cả hai. Nếu cần một thuộc tính được gán ở cả hai trường hợp, có thể viết ở cả hai nhánh, nhưng `SET` không điều kiện thường ngắn gọn hơn.

### 2.1. Hình dung luồng xử lý

~~~mermaid
flowchart TD
    A["Nhận khóa nghiệp vụ và dữ liệu mới"] --> B["MERGE theo khóa nghiệp vụ"]
    B --> C{"Có mẫu khớp?"}
    C -->|Không| D["Tạo mẫu mới"]
    D --> E["ON CREATE SET"]
    C -->|Có| F["Dùng lại mẫu đã có"]
    F --> G["ON MATCH SET"]
    E --> H["SET không điều kiện, nếu có"]
    G --> H
    H --> I["RETURN hoặc tiếp tục truy vấn"]
~~~

**Quan trọng:** “có mẫu khớp” nghĩa là khớp **toàn bộ mẫu trong chính mệnh đề `MERGE`**. Nếu `MERGE` chứa cả đường quan hệ chưa được ràng buộc nút, việc hai nút có cùng ID đã tồn tại chưa đủ để kích hoạt nhánh `ON MATCH SET`. Phần sau sẽ minh họa cách tách `MERGE` từng thực thể và quan hệ.

## 3. Ví dụ cơ bản: đồng bộ hồ sơ nhân viên

Giả sử hệ thống bên ngoài cung cấp:

~~~json
{
  "employeeId": "E001",
  "fullName": "Nguyễn An",
  "department": "Engineering",
  "active": true
}
~~~

Trong Neo4j, `employeeId` là **khóa nghiệp vụ ổn định** của nút `Employee`. `fullName`, `department` và `active` là các trường có thể đổi sau này.

~~~cypher
MERGE (e:Employee {employeeId: $employeeId})
ON CREATE SET
  e.createdAt = datetime(),
  e.source = 'hr-system'
ON MATCH SET
  e.lastSyncedAt = datetime()
SET e.fullName = $fullName,
    e.department = $department,
    e.active = $active
RETURN e.employeeId AS employeeId,
       e.fullName AS fullName,
       e.createdAt AS createdAt,
       e.lastSyncedAt AS lastSyncedAt;
~~~

Kết quả theo các lần chạy:

| Lần thực thi | Trạng thái trước khi chạy | Nhánh `MERGE` | Tác động |
|---|---|---|---|
| Lần 1 | Chưa có `Employee(employeeId='E001')` | `ON CREATE SET` | Tạo nút; ghi `createdAt`, `source` và ba trường nghiệp vụ |
| Lần 2 | Đã có nút E001 | `ON MATCH SET` | Giữ `createdAt`; ghi `lastSyncedAt`; cập nhật các trường nghiệp vụ |
| Lần 3 | Vẫn có nút E001, phòng ban đổi | `ON MATCH SET` | Vẫn dùng nút cũ; cập nhật `department`, `lastSyncedAt` |

Như vậy, `createdAt` mô tả lúc nút được tạo trong đồ thị, còn `lastSyncedAt` mô tả lần **đã khớp và được xử lý**. Trong ví dụ này, `lastSyncedAt` sẽ **chưa có** ngay sau lần tạo đầu tiên vì chỉ được gán ở nhánh `ON MATCH SET`.

Nếu yêu cầu nghiệp vụ là ghi nhận **mọi lần đồng bộ**, kể cả lần đầu, hãy đặt `lastSyncedAt` trong `SET` chung:

~~~cypher
MERGE (e:Employee {employeeId: $employeeId})
ON CREATE SET e.createdAt = datetime()
SET e.fullName = $fullName,
    e.department = $department,
    e.lastSyncedAt = datetime()
RETURN e;
~~~

Hai cách đều hợp lệ, nhưng ý nghĩa của `lastSyncedAt` khác nhau; chọn theo yêu cầu nghiệp vụ.

### 3.1. Vì sao không MERGE theo toàn bộ hồ sơ?

Truy vấn dễ gây lỗi:

~~~cypher
MERGE (e:Employee {
  employeeId: $employeeId,
  fullName: $fullName,
  department: $department
})
ON CREATE SET e.createdAt = datetime();
~~~

Nếu `department` thay đổi, mẫu cũ không khớp mẫu mới. Neo4j sẽ cố tạo nút mới với cùng `employeeId`, gây **trùng thực thể** nếu không có constraint hoặc **lỗi vi phạm constraint** nếu đã cấu hình khóa duy nhất.

Nên tách rõ:

- **Khóa nhận diện:** thuộc tính bền vững, ví dụ `employeeId`.
- **Thuộc tính cần đồng bộ:** `fullName`, `department`, `active`.
- **Metadata vòng đời:** `createdAt`, `lastSyncedAt`, `source`, `updatedAt`.

Truy vấn sử dụng `MERGE` theo khóa rồi `SET` các trường biến đổi sẽ giữ nguyên thực thể khi thông tin thay đổi.

## 4. Các kiểu cập nhật thường gặp

### 4.1. Chỉ ghi thuộc tính trong lần tạo đầu tiên

Một số dữ liệu không được sửa tùy tiện sau khi hình thành, ví dụ `registeredAt` hoặc `createdBy`:

~~~cypher
MERGE (u:User {userId: $userId})
ON CREATE SET
  u.registeredAt = datetime(),
  u.createdBy = $actor
SET u.displayName = $displayName
RETURN u;
~~~

Khi tài khoản đã tồn tại, `registeredAt` và `createdBy` được giữ nguyên; `displayName` có thể thay đổi.

### 4.2. Chỉ chỉnh sửa khi nút đã tồn tại

~~~cypher
MERGE (d:Device {deviceId: $deviceId})
ON CREATE SET
  d.firstSeenAt = datetime(),
  d.state = 'new'
ON MATCH SET
  d.lastSeenAt = datetime(),
  d.state = 'known'
RETURN d;
~~~

Lần đầu `state` là `new`, những lần khớp sau `state` chuyển sang `known`. Tuy nhiên, khi cần mô hình hóa trạng thái nghiệp vụ có nhiều giá trị, **không nên** đặt cứng `state = 'known'` nếu việc đồng bộ có thể vô tình ghi đè trạng thái do ứng dụng khác quản lý.

### 4.3. Cập nhật ở cả hai nhánh bằng SET

~~~cypher
MERGE (p:Product {sku: $sku})
ON CREATE SET
  p.createdAt = datetime()
ON MATCH SET
  p.lastSeenAsExistingAt = datetime()
SET p.name = $name,
    p.price = $price,
    p.updatedAt = datetime()
RETURN p;
~~~

Ở lần tạo và lần khớp, `SET` đều được thực thi. Nhánh `ON MATCH SET` chỉ ghi `lastSeenAsExistingAt` khi mẫu có sẵn.

### 4.4. Gộp map tham số với `+=`

Nếu ứng dụng có một tập thuộc tính cần cập nhật, có thể dùng:

~~~cypher
MERGE (p:Product {sku: $sku})
ON CREATE SET p.createdAt = datetime()
SET p += $properties
RETURN p;
~~~

Ví dụ `$properties` là:

~~~json
{
  "name": "Sách Graph",
  "price": 150000,
  "inStock": true
}
~~~

`SET p += $properties` cập nhật các khóa có trong map, giữ nguyên các thuộc tính **không được đề cập**; nếu map truyền một khóa với giá trị `null`, thuộc tính tương ứng có thể bị xóa. Trong khi đó, `SET p = $properties` thay toàn bộ tập thuộc tính bằng map mới, có thể làm mất `createdAt` hay khóa nghiệp vụ. Vì thế, không truyền map tùy ý từ người dùng vào câu lệnh cập nhật mà chưa kiểm soát danh sách trường được phép ghi.

Ngoài ra, không cần đặt `sku` vào map cập nhật: khóa `sku` đã nằm trong mẫu nhận diện và nên được giữ ổn định.

## 5. Khi nào nên ON CREATE SET, ON MATCH SET và SET?

Các nhánh không phải lựa chọn phong cách đơn thuần; chúng biểu diễn **chính sách nghiệp vụ**:

| Thuộc tính | Mong muốn | Cách triển khai gợi ý |
|---|---|---|
| `employeeId` | Nhận diện ổn định | Đặt trong mẫu `MERGE` |
| `createdAt` | Chỉ gán lần đầu | `ON CREATE SET` |
| `importSource` | Ghi nguồn lúc tạo, giữ lịch sử nguồn ban đầu | `ON CREATE SET` |
| `firstJoinedOn` | Thời điểm quan hệ được tạo trong đồ thị | `ON CREATE SET` của `MERGE` quan hệ |
| `fullName` | Đồng bộ mỗi lần nhận giá trị hợp lệ | `SET` chung |
| `active` | Đồng bộ trạng thái hiện tại | `SET` chung |
| `lastSyncedAt` | Đánh dấu mọi lần đồng bộ, kể cả lần đầu | `SET` chung |
| `lastMatchedAt` | Chỉ đánh dấu khi mẫu đã tồn tại | `ON MATCH SET` |
| `retryCount` | Chỉ tăng ở lần gặp lại | `ON MATCH SET n.retryCount = coalesce(n.retryCount, 0) + 1` |

**Phân biệt quan trọng:** Tên trường thời gian mang ý nghĩa nghiệp vụ. `createdAt` được gán trong `ON CREATE SET` là **thời điểm tạo bản ghi Neo4j**, không nhất thiết là ngày thực thể ra đời ở nguồn dữ liệu. Nếu nguồn đã có `createdAt` đáng tin cậy thì nên đặt tên riêng, ví dụ `sourceCreatedAt`, và cân nhắc chính sách đồng bộ riêng.

## 6. Đồng bộ nút và quan hệ: mỗi MERGE có một nhánh riêng

Trong property graph, dữ liệu không chỉ gồm nút mà còn gồm quan hệ. Giả sử một nhân viên tham gia dự án:

~~~text
(:Employee {employeeId: 'E001'})
           -[:WORKS_ON {role: 'Backend'}]->
(:Project {projectId: 'PR001'})
~~~

Yêu cầu:

- Tìm hoặc tạo nhân viên theo `employeeId`.
- Tìm hoặc tạo dự án theo `projectId`.
- Tìm hoặc tạo **một quan hệ `WORKS_ON`** giữa hai nút trên.
- Ghi thời điểm quan hệ được tạo chỉ một lần; cập nhật vai trò khi đồng bộ lại.

~~~cypher
MERGE (e:Employee {employeeId: $employeeId})
ON CREATE SET
  e.fullName = $employeeName,
  e.createdAt = datetime()

MERGE (pr:Project {projectId: $projectId})
ON CREATE SET
  pr.title = $projectTitle,
  pr.createdAt = datetime()

MERGE (e)-[r:WORKS_ON]->(pr)
ON CREATE SET
  r.joinedAt = date(),
  r.createdAt = datetime()
ON MATCH SET
  r.lastMatchedAt = datetime()
SET r.role = $role

RETURN e.employeeId AS employeeId,
       pr.projectId AS projectId,
       r.role AS role,
       r.joinedAt AS joinedAt;
~~~

Phân tích từng mệnh đề:

1. `MERGE (e:Employee ...)` chỉ quyết định nút nhân viên có cần tạo hay không. `ON CREATE SET e...` thuộc mệnh đề này.
2. `MERGE (pr:Project ...)` quyết định riêng nút dự án. `ON CREATE SET pr...` chỉ chạy nếu **nút dự án** được tạo mới.
3. `MERGE (e)-[r:WORKS_ON]->(pr)` quyết định riêng quan hệ. `e` và `pr` đã được ràng buộc trước đó nên quan hệ dùng đúng hai nút đã tìm/tạo.
4. `ON CREATE SET r.joinedAt...` chỉ chạy khi **quan hệ** mới được tạo. `ON MATCH SET r.lastMatchedAt...` chạy khi **quan hệ** đã khớp, không phụ thuộc việc nút nhân viên và dự án vừa được tạo hay đã tồn tại.
5. `SET r.role = $role` chạy ở cả hai nhánh của `MERGE` quan hệ.

### 6.1. Nhánh xử lý có thể khác nhau trong cùng một truy vấn

Ví dụ đồ thị đã có nhân viên E001 nhưng chưa có dự án PR001:

| Thành phần | Mệnh đề MERGE | Nhánh xảy ra |
|---|---|---|
| Employee E001 | `MERGE (e:Employee ...)` | `ON MATCH` nếu khai báo |
| Project PR001 | `MERGE (pr:Project ...)` | `ON CREATE` |
| Quan hệ `WORKS_ON` | `MERGE (e)-[r:WORKS_ON]->(pr)` | `ON CREATE` |

**Không có một nhánh `ON CREATE` hoặc `ON MATCH` chung cho toàn truy vấn.** Mỗi mệnh đề `MERGE` đánh giá mẫu và nhánh của chính mình trên dữ liệu ở thời điểm nó thực thi.

### 6.2. Tránh MERGE toàn mẫu chưa ràng buộc đầu mút

Cách viết dưới đây có thể tạo trùng nút khi **hai đầu mút đã có nhưng chưa có quan hệ**:

~~~cypher
MERGE (e:Employee {employeeId: $employeeId})
      -[r:WORKS_ON]->
      (pr:Project {projectId: $projectId})
ON CREATE SET r.createdAt = datetime();
~~~

Vì cả `e` và `pr` chưa được ràng buộc từ trước, mệnh đề yêu cầu tìm **toàn bộ đường**. Nếu chưa có đường phù hợp, `MERGE` có thể cố tạo cả hai nút và quan hệ, thay vì chỉ nối hai nút cũ. Với constraint duy nhất trên khóa nút, truy vấn có thể báo lỗi.

Khi nghiệp vụ có các thực thể độc lập được tái sử dụng ở nhiều quan hệ, hãy **MERGE từng nút trước**, rồi MERGE quan hệ. Nếu các nút **bắt buộc tồn tại**, dùng `MATCH` cho đầu mút:

~~~cypher
MATCH (e:Employee {employeeId: $employeeId})
MATCH (pr:Project {projectId: $projectId})
MERGE (e)-[r:WORKS_ON]->(pr)
ON CREATE SET r.createdAt = datetime()
ON MATCH SET r.lastMatchedAt = datetime()
SET r.role = $role
RETURN r;
~~~

Nếu một đầu mút không tồn tại, truy vấn `MATCH` không trả dòng tương ứng nên không có quan hệ được tạo.

## 7. Khóa nghiệp vụ, constraint và việc ghi đồng thời

`MERGE` thuận tiện nhưng **không tự thay thế ràng buộc dữ liệu**. Với hệ thống có nhiều giao dịch hoặc nhiều tiến trình đồng bộ, cần định nghĩa khóa nghiệp vụ rõ ràng và áp dụng constraint phù hợp.

Ví dụ:

~~~cypher
CREATE CONSTRAINT employee_id_unique IF NOT EXISTS
FOR (e:Employee)
REQUIRE e.employeeId IS UNIQUE;
~~~

~~~cypher
CREATE CONSTRAINT project_id_unique IF NOT EXISTS
FOR (pr:Project)
REQUIRE pr.projectId IS UNIQUE;
~~~

Các ràng buộc này yêu cầu mỗi giá trị `employeeId` hay `projectId` chỉ thuộc về tối đa một nút tương ứng trong cùng nhãn. Constraint duy nhất cho nút cũng cung cấp index phục vụ truy vấn tìm kiếm khóa.

**Lưu ý triển khai:** Nếu dữ liệu hiện có đã trùng khóa, tạo constraint có thể thất bại. Hãy làm sạch dữ liệu trước và xử lý lỗi ràng buộc tại ứng dụng.

### 7.1. Tính duy nhất của nút không quyết định tính duy nhất của quan hệ

Ngay cả khi `Employee(employeeId)` và `Project(projectId)` đều duy nhất, hai nút vẫn có thể có nhiều quan hệ `WORKS_ON` song song. `MERGE (e)-[r:WORKS_ON]->(pr)` giúp tìm lại quan hệ phù hợp theo kiểu và hướng trong các trường hợp thông thường, nhưng không tự xóa các quan hệ trùng đã tồn tại, và constraint của nút không bảo đảm duy nhất cho mọi quan hệ trong ghi đồng thời.

Nếu nghiệp vụ yêu cầu **mỗi lần tham gia một dự án là một bản ghi lịch sử độc lập**, có thể định danh quan hệ bằng `assignmentId` hoặc dùng nút `Assignment`. Khi đó `MERGE` theo đúng khóa quan hệ; không sử dụng việc đổi `role` để vô tình tạo ra một quan hệ lịch sử mới.

### 7.2. Khóa MERGE không được null

~~~cypher
MERGE (e:Employee {employeeId: $employeeId})
ON CREATE SET e.createdAt = datetime();
~~~

Nếu `$employeeId = null`, `MERGE` với thuộc tính khóa này sẽ báo lỗi. Cần kiểm tra khóa nghiệp vụ **trước** khi chạy. Constraint duy nhất cũng không có nghĩa mọi nút bắt buộc có khóa: nếu muốn đảm bảo thuộc tính luôn tồn tại, hãy thiết kế ràng buộc hiện diện phù hợp với phiên bản Neo4j và chính sách dữ liệu.

### 7.3. Dữ liệu sai khóa hoặc khóa thay đổi

Tránh dùng tên người, tiêu đề dự án hoặc email có thể đổi làm định danh nếu nghiệp vụ không bảo đảm chúng ổn định. Nếu cần khóa tổng hợp (ví dụ mỗi mã nhân viên chỉ duy nhất trong một công ty), mẫu nhận diện có thể là:

~~~cypher
MERGE (e:Employee {
  companyId: $companyId,
  employeeId: $employeeId
})
ON CREATE SET e.createdAt = datetime()
SET e.fullName = $fullName
RETURN e;
~~~

Trong trường hợp này, constraint cũng phải được thiết kế theo **cặp thuộc tính** chứ không chỉ riêng `employeeId`.

## 8. Đồng bộ có lặp lại và tính idempotent

Một tiến trình nhập liệu có thể chạy lại cùng một bản ghi do lỗi mạng, retry giao dịch hoặc đồng bộ theo lịch. Ta thường muốn:

- **Không tăng số nút/quan hệ** khi chạy lại cùng khóa.
- **Không làm mất ngày tạo** khi bản ghi đã có.
- Chỉ cập nhật những trường mà nguồn dữ liệu được phép quản lý.
- Không vô tình thay đổi dữ liệu nếu sự kiện cũ đến sau sự kiện mới.

`MERGE` theo khóa ổn định, kết hợp constraint và các nhánh cập nhật, hỗ trợ **idempotency về cấu trúc**: chạy lại cùng định danh không có ý định tạo thực thể mới. Nhưng ghi `lastSyncedAt = datetime()` sau mỗi lần chạy sẽ làm **trạng thái thuộc tính thay đổi**; vì thế truy vấn có thể *idempotent về số lượng thực thể* mà **không idempotent về toàn bộ thuộc tính**.

### 8.1. Đừng nhầm lastSyncedAt với nguồn sự kiện

Giả sử nguồn gửi một mã sự kiện `eventId` và mốc cập nhật `sourceUpdatedAt`. Nếu hai lần đồng bộ có cùng nội dung nhưng mốc chạy khác nhau, `datetime()` phản ánh thời gian ghi **vào Neo4j**, không phải thời gian thay đổi thực tế ở nguồn. Để giữ dấu vết nguồn:

~~~cypher
MERGE (e:Employee {employeeId: $employeeId})
ON CREATE SET e.createdAt = datetime()
SET e.fullName = $fullName,
    e.sourceUpdatedAt = datetime($sourceUpdatedAt),
    e.lastSyncedAt = datetime()
RETURN e;
~~~

Ví dụ trên vẫn ghi đè `fullName` khi một bản tin cũ đến trễ. Nếu nguồn có thể gửi ngoài thứ tự, cần bổ sung **quy tắc phiên bản hoặc thời gian hợp lệ** trước khi cập nhật dữ liệu. `ON MATCH SET` tự nó không so sánh bản tin cũ/mới.

### 8.2. Có giá trị null trong dữ liệu đồng bộ

Trong Cypher, gán một thuộc tính bằng `null` có nghĩa là **xóa thuộc tính đó**. Ví dụ:

~~~cypher
MERGE (e:Employee {employeeId: $employeeId})
SET e.department = $department
RETURN e;
~~~

Nếu `$department` bằng `null`, thuộc tính `department` sẽ bị xóa. Điều đó đúng nếu nguồn chủ đích yêu cầu xóa, nhưng nguy hiểm khi `null` chỉ nghĩa là “trường này không được gửi”.

Nếu chính sách là **bỏ qua giá trị null**, một lựa chọn đơn giản:

~~~cypher
MERGE (e:Employee {employeeId: $employeeId})
SET e.department = coalesce($department, e.department)
RETURN e;
~~~

`coalesce` lấy giá trị đầu tiên khác `null`. Nếu cả hai cùng `null` thì không còn thuộc tính `department`, phù hợp với trạng thái chưa có dữ liệu. Cần phân biệt rõ **trường thiếu**, **giá trị null chủ ý** và **chuỗi rỗng** theo giao thức tích hợp; dùng `coalesce` đồng nghĩa không hỗ trợ yêu cầu xóa thuộc tính bằng `null`.

### 8.3. Không tăng bộ đếm chỉ vì truy vấn được retry

Ví dụ:

~~~cypher
MERGE (j:Job {jobId: $jobId})
ON CREATE SET j.createdAt = datetime(), j.seenCount = 1
ON MATCH SET j.seenCount = coalesce(j.seenCount, 0) + 1;
~~~

`seenCount` tăng ở mỗi lần khớp lại, kể cả khi xử lý cùng bản tin lặp lại. Nếu chỉ muốn tính **số sự kiện duy nhất**, cần nhận diện từng sự kiện bằng khóa riêng hoặc cơ chế khử trùng trước khi tăng bộ đếm. `ON MATCH SET` không tự cung cấp bảo đảm “xử lý đúng một lần”.

## 9. Tạo và cập nhật nhiều bản ghi bằng UNWIND

`UNWIND` biến danh sách thành các dòng, cho phép sử dụng cùng một quy tắc `MERGE` và `ON CREATE/ON MATCH SET` với từng bản ghi.

Ví dụ tham số:

~~~json
{
  "employees": [
    {
      "employeeId": "E001",
      "fullName": "Nguyễn An",
      "department": "Engineering",
      "active": true
    },
    {
      "employeeId": "E002",
      "fullName": "Trần Bình",
      "department": "Data",
      "active": true
    }
  ]
}
~~~

Truy vấn:

~~~cypher
UNWIND $employees AS row
MERGE (e:Employee {employeeId: row.employeeId})
ON CREATE SET
  e.createdAt = datetime(),
  e.importSource = 'hr-batch'
ON MATCH SET
  e.lastMatchedAt = datetime()
SET e.fullName = row.fullName,
    e.department = row.department,
    e.active = row.active,
    e.lastSyncedAt = datetime()
RETURN count(*) AS processedRows;
~~~

Với hai mã nhân viên hợp lệ, duy nhất trong input và constraint phù hợp, truy vấn sẽ tìm/tạo hai nút. Nếu E001 đã tồn tại mà E002 chưa có, `ON MATCH SET` áp dụng cho dòng E001 và `ON CREATE SET` áp dụng cho dòng E002.

`processedRows` là **số dòng xử lý đi tới `RETURN`**, không phải số nhân viên mới được tạo. Nếu dữ liệu ban đầu chứa nhiều nút trùng khóa khiến `MERGE` khớp nhiều nút, số dòng có thể vượt kỳ vọng.

### 9.1. Quy tắc cho dữ liệu đầu vào theo lô

- Xác thực `employeeId` không rỗng và không phải `null` cho mọi dòng.
- Khử trùng khóa trong cùng lô, đặc biệt khi các dòng cùng ID có giá trị khác nhau. `UNWIND` không cam kết thứ tự, nên không được dựa vào “dòng cuối cùng thắng” nếu không có quy tắc sắp xếp/phiên bản phù hợp.
- Xử lý rõ giá trị `null` và các trường chỉ được cập nhật theo điều kiện.
- Chia lô hợp lý với dữ liệu lớn, theo dõi thời gian truy vấn và áp lực giao dịch.
- Tạo constraint trước khi nhập, sau khi đã đảm bảo dữ liệu hiện hữu đáp ứng ràng buộc.

### 9.2. Đồng bộ quan hệ hàng loạt

Ví dụ mỗi dòng gồm một nhân viên, một dự án và vai trò, với mục tiêu tìm/tạo cả đầu mút và quan hệ:

~~~cypher
UNWIND $assignments AS row
MERGE (e:Employee {employeeId: row.employeeId})
ON CREATE SET e.createdAt = datetime(), e.fullName = row.employeeName

MERGE (pr:Project {projectId: row.projectId})
ON CREATE SET pr.createdAt = datetime(), pr.title = row.projectTitle

MERGE (e)-[r:WORKS_ON]->(pr)
ON CREATE SET r.createdAt = datetime()
ON MATCH SET r.lastMatchedAt = datetime()
SET r.role = row.role

RETURN count(*) AS processedAssignments;
~~~

Hai nhân viên tham gia cùng một dự án sẽ dùng chung nút dự án **nếu cùng `projectId` và dữ liệu được bảo vệ bằng constraint**. Mỗi `MERGE` đánh giá nhánh tạo/khớp riêng cho từng dòng và từng thành phần.

## 10. Sử dụng từ Neo4j Java Driver

Trong Java, nên truyền tham số thay vì ghép tên, ID hoặc các giá trị khác trực tiếp vào chuỗi Cypher. Ví dụ dưới đây nhận một bản ghi đồng bộ, tìm hoặc tạo `Employee` và trả lại ID:

~~~java
import java.util.Map;
import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;

public final class EmployeeSyncService {
    private final Driver driver;

    public EmployeeSyncService(Driver driver) {
        this.driver = driver;
    }

    public String syncEmployee(
            String employeeId,
            String fullName,
            String department
    ) {
        String cypher = """
                MERGE (e:Employee {employeeId: $employeeId})
                ON CREATE SET e.createdAt = datetime()
                ON MATCH SET e.lastMatchedAt = datetime()
                SET e.fullName = $fullName,
                    e.department = $department,
                    e.lastSyncedAt = datetime()
                RETURN e.employeeId AS id
                """;

        try (Session session = driver.session()) {
            return session.executeWrite(tx ->
                    tx.run(cypher, Map.of(
                            "employeeId", employeeId,
                            "fullName", fullName,
                            "department", department
                    )).single().get("id").asString()
            );
        }
    }
}
~~~

**Ý nghĩa kỹ thuật:**

- `executeWrite` thực thi truy vấn trong giao dịch ghi do Driver quản lý, và có cơ chế thử lại phù hợp với một số lỗi tạm thời. Vì callback có thể được thực thi lại, tránh đặt **tác dụng phụ ngoài cơ sở dữ liệu** (như gửi email, gọi API thanh toán) bên trong callback mà không có cơ chế chống lặp.
- `Map.of` dùng cho tham số **không null** trong ví dụ này. Nếu dữ liệu cho phép null, cần xây dựng map tham số tương thích và xác định chính sách cập nhật thuộc tính.
- `single()` phù hợp khi khóa `employeeId` thực sự nhận diện một nút. Một constraint duy nhất giúp hỗ trợ giả định đó.
- Đối tượng `Driver` nên được quản lý và tái sử dụng theo vòng đời của ứng dụng; mỗi thao tác có thể mở/đóng `Session` thích hợp.
- Khi cần truy cập một cơ sở dữ liệu cụ thể, cấu hình database trên `Session` theo môi trường thực tế.

Trong **Spring Data Neo4j**, repository và entity mapping có thể thực hiện thao tác lưu dữ liệu ở mức trừu tượng cao hơn. Khi cần truy vấn tùy biến `@Query` để đồng bộ theo khóa, các quy tắc `MERGE`, `ON CREATE SET`, `ON MATCH SET` và constraint vẫn áp dụng. Ngoài nhánh cập nhật, ứng dụng cần quản lý giao dịch, phiên bản dữ liệu và các quan hệ được cập nhật từ nguồn.

## 11. Kiểm tra kết quả và tìm lỗi

Giả sử bạn đã đồng bộ nhân viên E001, có thể kiểm tra:

~~~cypher
MATCH (e:Employee {employeeId: 'E001'})
RETURN e.employeeId AS id,
       e.fullName AS name,
       e.createdAt AS createdAt,
       e.lastMatchedAt AS lastMatchedAt,
       e.lastSyncedAt AS lastSyncedAt;
~~~

Kiểm tra xem có nhiều nút cùng khóa hay không:

~~~cypher
MATCH (e:Employee)
WITH e.employeeId AS employeeId, count(*) AS total
WHERE employeeId IS NOT NULL AND total > 1
RETURN employeeId, total
ORDER BY total DESC;
~~~

Lệnh `EXPLAIN` có thể dùng để xem kế hoạch của truy vấn mà không thực thi phần ghi. `PROFILE` **thực thi truy vấn**, vì vậy khi kiểm tra truy vấn đồng bộ, chỉ sử dụng trên dữ liệu kiểm thử hoặc khi hiểu rõ tác động.

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| `createdAt` bị đổi ở mỗi lần đồng bộ | Dùng `SET` chung thay vì `ON CREATE SET` | Chuyển `createdAt` vào nhánh tạo |
| `lastSyncedAt` không có sau lần tạo đầu | Đặt trong `ON MATCH SET` | Nếu muốn ghi ở mọi lần, chuyển sang `SET` chung |
| Cập nhật phòng ban tạo thêm nút | Đưa `department` vào mẫu `MERGE` | `MERGE` theo khóa ổn định, cập nhật thuộc tính ngoài mẫu |
| Không tạo được dữ liệu vì vi phạm constraint | Cố tạo thực thể có khóa đã tồn tại theo mẫu khác hoặc dữ liệu có xung đột | Kiểm tra khóa, mẫu, dữ liệu trùng và trạng thái constraint |
| Quan hệ bị trùng hoặc xuất hiện nút bản sao | `MERGE` toàn đường khi đầu mút chưa được ràng buộc | Tách `MERGE` từng nút và quan hệ; dùng constraint |
| Thuộc tính biến mất sau đồng bộ | Truyền `null` hoặc `SET n = $map` thay toàn bộ thuộc tính | Xác định chính sách null, chỉ cập nhật trường được phép |
| Dữ liệu mới bị sự kiện cũ ghi đè | Không kiểm soát thứ tự/phiên bản nguồn | Kiểm tra mốc thay đổi hoặc version của nguồn trước khi cập nhật |
| Chỉ tiêu “số mới” không khớp `count(*)` | `count(*)` đếm dòng, không xác định nhánh vừa tạo | Thiết kế thống kê create/match riêng khi cần |
| Callback Java phát sinh tác dụng phụ nhiều lần | Giao dịch được thử lại | Không đặt tác dụng phụ không chống lặp vào callback |
| Câu lệnh `MERGE` lỗi với null | Khóa nghiệp vụ đầu vào bằng `null` | Xác thực khóa trước truy vấn |

## 12. Bài tập thực hành

### Bài tập 1: Tạo và cập nhật khóa học

Yêu cầu:

- Nút `Course` được nhận diện bằng `courseId`.
- `createdAt` chỉ ghi lần tạo đầu tiên.
- `title` và `published` được cập nhật sau mỗi lần đồng bộ.
- `lastMatchedAt` chỉ ghi khi khóa học đã có.

<details>
<summary>Đáp án tham khảo</summary>

~~~cypher
MERGE (c:Course {courseId: $courseId})
ON CREATE SET c.createdAt = datetime()
ON MATCH SET c.lastMatchedAt = datetime()
SET c.title = $title,
    c.published = $published
RETURN c;
~~~

Nếu lần đầu chưa có nút `Course`, nhánh `ON CREATE SET` chạy và nhánh `ON MATCH SET` không chạy. Khi chạy lại với cùng `courseId`, hai vai trò đổi cho nhau.

</details>

### Bài tập 2: Tránh cập nhật sai ngày đăng ký

Xét câu lệnh:

~~~cypher
MERGE (u:User {userId: $userId})
SET u.registeredAt = datetime(),
    u.displayName = $displayName;
~~~

**Câu hỏi:** Vì sao `registeredAt` bị sai sau nhiều lần đồng bộ? Hãy sửa để giữ nguyên lần đăng ký đầu tiên.

<details>
<summary>Đáp án tham khảo</summary>

`SET` ở đây chạy trong **mọi lần** truy vấn đi tới mệnh đề, nên ngày đăng ký bị ghi lại. Chuyển sang `ON CREATE SET`:

~~~cypher
MERGE (u:User {userId: $userId})
ON CREATE SET u.registeredAt = datetime()
SET u.displayName = $displayName;
~~~

</details>

### Bài tập 3: Hai nút đã tồn tại, quan hệ có thể chưa có

Yêu cầu: `User U01` và `Group G01` **phải tồn tại trước**, không được tạo nút nếu thiếu. Tìm hoặc tạo quan hệ `MEMBER_OF`, chỉ ghi `joinedOn` khi quan hệ mới; cập nhật `membershipRole` ở mọi lần.

<details>
<summary>Đáp án tham khảo</summary>

~~~cypher
MATCH (u:User {userId: 'U01'})
MATCH (g:Group {groupId: 'G01'})
MERGE (u)-[r:MEMBER_OF]->(g)
ON CREATE SET r.joinedOn = date()
SET r.membershipRole = $role
RETURN u.userId AS userId,
       g.groupId AS groupId,
       r.joinedOn AS joinedOn,
       r.membershipRole AS membershipRole;
~~~

`MATCH` bảo đảm không tự tạo đầu mút, `MERGE` chỉ tìm/tạo quan hệ giữa hai nút đã ràng buộc. Nếu thiếu nút, truy vấn không tạo quan hệ.

</details>

### Bài tập 4: Hiểu đúng nhánh tạo/khớp

Giả sử nhân viên E01 **đã có**, dự án PR01 **chưa có**, chưa tồn tại quan hệ `WORKS_ON`:

~~~cypher
MERGE (e:Employee {employeeId: 'E01'})
ON CREATE SET e.createdFlag = true
ON MATCH SET e.matchedFlag = true
MERGE (p:Project {projectId: 'PR01'})
ON CREATE SET p.createdFlag = true
ON MATCH SET p.matchedFlag = true
MERGE (e)-[r:WORKS_ON]->(p)
ON CREATE SET r.createdFlag = true
ON MATCH SET r.matchedFlag = true
RETURN e, p, r;
~~~

**Câu hỏi:** Ba đối tượng sẽ nhận các cờ nào?

<details>
<summary>Đáp án</summary>

- `Employee E01` đã khớp: gán `matchedFlag = true`; `createdFlag` chỉ tồn tại nếu được ghi trước đó.
- `Project PR01` được tạo: gán `createdFlag = true`; không gán `matchedFlag` ở mệnh đề này.
- `WORKS_ON` vừa được tạo: gán `createdFlag = true`; không gán `matchedFlag` ở mệnh đề này.

Mỗi nhánh thuộc `MERGE` ngay trước, không có nhánh chung cho toàn truy vấn.

</details>

## 13. Ghi nhớ và vận dụng

- **`MERGE`** tìm hoặc tạo *mẫu*; **`ON CREATE SET`** chạy khi mẫu của `MERGE` đó được tạo; **`ON MATCH SET`** chạy khi mẫu đã khớp.
- **`SET` không điều kiện** phù hợp cho thuộc tính cần cập nhật cả khi tạo và khi khớp.
- **Nhận diện bằng khóa ổn định**: đặt khóa vào `MERGE`; đặt tên, trạng thái, giá trị kinh doanh và metadata thay đổi trong các nhánh `SET` thích hợp.
- **Mỗi `MERGE` có nhánh riêng**: khi đồng bộ đồ thị, tìm/tạo từng nút trước, rồi tìm/tạo quan hệ giữa các nút đã ràng buộc.
- **Constraint và dữ liệu hợp lệ** giúp bảo toàn định danh; riêng `MERGE` không thay thế chính sách toàn vẹn hoặc chống lặp mọi tình huống ghi đồng thời.
- **Đồng bộ lặp lại** không đồng nghĩa mọi giá trị bất biến: timestamp, bộ đếm và các bản tin đến sai thứ tự cần được thiết kế rõ.
- **Java Driver, Spring Data Neo4j và nhập liệu hàng loạt** đều dùng cùng ngữ nghĩa Cypher; sử dụng tham số, transaction, kiểm tra null và theo dõi dữ liệu nguồn.

Nắm vững `ON CREATE SET` và `ON MATCH SET` là bước quan trọng để viết truy vấn cập nhật Neo4j có kiểm soát, trước khi tiến tới tối ưu query plan, index/constraint, đồng bộ nguồn lớn và vận hành hệ thống đồ thị.
