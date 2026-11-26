# MERGE để tìm hoặc tạo dữ liệu theo mẫu trong Neo4j

> **Chương:** Tạo và cập nhật  
> **Chủ đề:** `MERGE` trong Cypher — tìm mẫu đồ thị đã tồn tại hoặc tạo mẫu mới.

Trong mô-đun `DATABASE_ENGINE_GRAPH_NEO4J`, dữ liệu được biểu diễn dưới dạng **property graph**: nút chứa thông tin thực thể, quan hệ kết nối các thực thể và thuộc tính lưu đặc điểm của cả nút lẫn quan hệ. Cypher cung cấp `MATCH` để truy vấn, `CREATE` để tạo mới và `MERGE` để thực hiện thao tác **tìm hoặc tạo theo mẫu** (*match or create*). Kỹ thuật này rất hữu ích khi đồng bộ người dùng, nhập dữ liệu nhiều lần, quản lý quan hệ thành viên hoặc ghi quan hệ giữa những thực thể đã được xác định.

Bài học giải thích `MERGE` ở cấp mẫu đồ thị, các nhánh `ON CREATE`/`ON MATCH`, khóa nghiệp vụ, constraint và index, nhập dữ liệu theo lô, cùng cách gọi Cypher từ Java Driver. Trọng tâm là sử dụng đúng ngữ nghĩa của `MERGE` để tránh tạo nút hoặc quan hệ ngoài ý muốn.

## 1. Mục tiêu học tập

Hoàn thành bài học, bạn có thể:

1. Phân biệt `MATCH`, `CREATE` và `MERGE` dựa trên dữ liệu đã có.
2. Giải thích vì sao `MERGE` xét **cả mẫu**, thay vì tự động ghép từng phần của mẫu.
3. Dùng `MERGE` cho nút có khóa nghiệp vụ và phân biệt thuộc tính định danh với thuộc tính thay đổi.
4. Viết `ON CREATE SET` và `ON MATCH SET` để xử lý đúng lần tạo đầu tiên và các lần khớp sau.
5. Tạo quan hệ giữa các nút hiện có bằng cách ràng buộc đầu mút trước khi `MERGE` quan hệ.
6. Thiết kế constraint, truy vấn hàng loạt và giao dịch phù hợp với yêu cầu tránh trùng.

## 2. Khái niệm cốt lõi: `MERGE` khớp hoặc tạo toàn bộ mẫu

Cú pháp đơn giản:

~~~cypher
MERGE (p:Person {personId: 'P-001'})
RETURN p;
~~~

Neo4j xử lý một mẫu `(p:Person {personId: 'P-001'})` như sau:

- **Có nút khớp mẫu:** gắn biến `p` với nút hiện có; không tạo thêm nút cho mẫu đó.
- **Không có nút khớp mẫu:** tạo một nút `Person` với `personId = 'P-001'`; gắn biến `p` với nút vừa tạo.

Hình dung luồng xử lý:

~~~mermaid
flowchart TD
    A["MERGE mẫu Cypher"] --> B{"Có mẫu khớp đầy đủ?"}
    B -->|Có| C["Dùng dữ liệu hiện có"]
    B -->|Không| D["Tạo mẫu mới"]
    C --> E["ON MATCH SET (nếu khai báo)"]
    D --> F["ON CREATE SET (nếu khai báo)"]
    E --> G["Chuyển dòng kết quả sang mệnh đề tiếp theo"]
    F --> G
~~~

`MERGE` thường được dùng để viết truy vấn có thể chạy lặp lại mà vẫn nhận diện cùng một thực thể hoặc kết nối. Tuy nhiên, **chỉ có `MERGE` không bảo đảm mọi tình huống đều không trùng dữ liệu**. Tính duy nhất còn phụ thuộc vào mẫu khớp, khóa nghiệp vụ, dữ liệu hiện tại, constraint và ghi đồng thời.

### So sánh ba lệnh cơ bản

| Lệnh | Khi dữ liệu khớp đã tồn tại | Khi dữ liệu chưa tồn tại | Mục đích |
|---|---|---|---|
| `MATCH (p:Person {personId: $id})` | Trả về nút phù hợp | Không trả dòng kết quả | Đọc/tìm |
| `CREATE (p:Person {personId: $id})` | Vẫn yêu cầu tạo nút mới | Tạo nút mới | Tạo mới |
| `MERGE (p:Person {personId: $id})` | Sử dụng nút khớp | Tạo nút mới | Tìm hoặc tạo |

Nếu có nhiều nút cùng khớp mẫu, `MERGE` có thể tạo **nhiều dòng kết quả khớp**; nó không tự hợp nhất các nút bị trùng thành một.

## 3. Tìm hoặc tạo nút bằng khóa nghiệp vụ

### 3.1. Xác định danh tính của thực thể

Giả sử mỗi người dùng có mã `userId` duy nhất trong hệ thống. Truy vấn:

~~~cypher
MERGE (u:User {userId: 'U-101'})
RETURN u;
~~~

Lần đầu tiên (chưa có nút `User` tương ứng), truy vấn tạo nút:

~~~text
(:User {userId: 'U-101'})
~~~

Những lần sau, truy vấn tìm và sử dụng nút đã có. `userId` là **khóa nghiệp vụ** (*business key*) do ứng dụng kiểm soát. Nó khác với ID nội bộ của Neo4j, và phù hợp để nhận diện dữ liệu qua các lần đồng bộ hoặc import.

Để kiểm tra trạng thái:

~~~cypher
MATCH (u:User {userId: 'U-101'})
RETURN u.userId AS userId, labels(u) AS labels;
~~~

### 3.2. Không đưa thuộc tính dễ thay đổi vào mẫu nhận diện

**Cách dễ gây trùng dữ liệu:**

~~~cypher
MERGE (u:User {
  userId: 'U-101',
  displayName: 'An'
});
~~~

Sau này người dùng đổi tên thành “An Nguyễn”:

~~~cypher
MERGE (u:User {
  userId: 'U-101',
  displayName: 'An Nguyễn'
});
~~~

Hai mẫu trên không giống nhau vì `displayName` khác. Nếu không có constraint, Neo4j có thể tạo nút `User` thứ hai cùng `userId`. Nếu có constraint duy nhất trên `userId`, truy vấn thứ hai có thể **bị từ chối do vi phạm constraint**. Truy vấn đó không tự chuyển thành cập nhật tên.

**Cách phù hợp: chỉ dùng khóa ổn định trong `MERGE`, cập nhật các thông tin còn lại bằng `SET`.**

~~~cypher
MERGE (u:User {userId: 'U-101'})
SET u.displayName = 'An Nguyễn'
RETURN u;
~~~

Với hệ thống thật, đưa giá trị vào tham số:

~~~cypher
MERGE (u:User {userId: $userId})
SET u.displayName = $displayName
RETURN u.userId AS userId, u.displayName AS displayName;
~~~

Ví dụ tham số:

~~~json
{
  "userId": "U-101",
  "displayName": "An Nguyễn"
}
~~~

**Quy tắc thiết kế:** Thuộc tính trong mẫu `MERGE` nên mô tả **danh tính hoặc điều kiện khớp cố định**. Tên hiển thị, số lượt truy cập, trạng thái hay thời gian cập nhật thường thuộc phần `SET`.

## 4. `ON CREATE SET` và `ON MATCH SET`

`MERGE` cho phép tách hai nhánh xử lý:

- `ON CREATE SET`: chỉ chạy khi `MERGE` **tạo mẫu mới**.
- `ON MATCH SET`: chỉ chạy khi `MERGE` **khớp mẫu có sẵn**.
- `SET` độc lập: chạy trong cả hai trường hợp khi dòng dữ liệu đi đến mệnh đề này.

Ví dụ một bản ghi nhân viên:

~~~cypher
MERGE (e:Employee {employeeId: $employeeId})
ON CREATE SET
  e.fullName = $fullName,
  e.department = $department,
  e.createdAt = datetime()
ON MATCH SET
  e.fullName = $fullName,
  e.department = $department,
  e.updatedAt = datetime()
RETURN e.employeeId AS employeeId,
       e.fullName AS fullName,
       e.createdAt AS createdAt,
       e.updatedAt AS updatedAt;
~~~

Tham số ví dụ:

~~~json
{
  "employeeId": "EMP-101",
  "fullName": "Lê Bình",
  "department": "Platform"
}
~~~

| Tình huống | Nhánh chạy | Kết quả mong đợi |
|---|---|---|
| Chưa có `Employee` với `EMP-101` | `ON CREATE SET` | Tạo nút, đặt tên/phòng ban và `createdAt` |
| Đã có nút đó | `ON MATCH SET` | Sử dụng nút cũ, cập nhật tên/phòng ban và `updatedAt` |

`createdAt` được đặt ở lần tạo đầu tiên và không bị `ON MATCH` ghi đè. `updatedAt` chỉ xuất hiện khi cập nhật ở nhánh khớp; nếu nghiệp vụ muốn có thời gian cập nhật ngay khi tạo, có thể đặt nó ở cả hai nhánh.

### Phân biệt cập nhật dữ liệu và khả năng chạy lặp

~~~cypher
MERGE (p:Product {sku: $sku})
ON CREATE SET p.createdAt = datetime()
SET p.price = $price;
~~~

Chạy lại với cùng `sku` không tạo thêm nút `Product` nếu chỉ có một nút khớp và không xảy ra cạnh tranh ghi gây trùng. Tuy nhiên, `price` có thể thay đổi ở mỗi lần chạy. Nếu gán `updatedAt = datetime()` trong mọi lần chạy thì thuộc tính thời gian cũng đổi, dù đầu vào giống nhau. Do đó, “chạy lặp không tạo trùng cấu trúc” khác với “mọi thuộc tính luôn giữ nguyên”.

### `MERGE` có thể nhận nhiều nhãn

~~~cypher
MERGE (e:Person:Employee {employeeId: 'EMP-102'})
RETURN labels(e) AS labels;
~~~

Mẫu này đòi hỏi một nút có **cả hai nhãn** và giá trị `employeeId` đã chỉ định. Một nút chỉ có nhãn `Person` với cùng `employeeId` chưa phải mẫu khớp đầy đủ. Khi thiết kế nhập liệu từ nhiều nguồn, nên chọn nhãn và khóa nhất quán để tránh phân mảnh danh tính.

## 5. Quan trọng: `MERGE` xét toàn bộ mẫu quan hệ

### 5.1. Cạm bẫy khi `MERGE` đồng thời hai nút và một quan hệ

Giả sử đồ thị đã có:

~~~text
(:Person {personId: 'P-101'})      (:Team {teamId: 'T-01'})
~~~

Giữa hai nút hiện **chưa có** quan hệ `MEMBER_OF`. Truy vấn sau thoạt nhìn có vẻ dùng để tạo một quan hệ còn thiếu:

~~~cypher
MERGE (p:Person {personId: 'P-101'})
      -[:MEMBER_OF]->
      (t:Team {teamId: 'T-01'});
~~~

Nhưng `MERGE` kiểm tra **toàn bộ mẫu** gồm nút người, quan hệ và nút nhóm. Vì chưa có kết nối đầy đủ, mẫu không khớp; Cypher có thể cố **tạo toàn bộ mẫu**, bao gồm **hai nút mới và một quan hệ**. Không có constraint, điều đó có thể dẫn đến các nút mang `personId`/`teamId` trùng. Có constraint, câu lệnh có thể thất bại thay vì tự nối hai nút cũ.

Đây là khác biệt quyết định giữa “tìm hoặc tạo mẫu” và “tìm hoặc tạo từng thành phần của mẫu”.

### 5.2. Cách đúng: ràng buộc các nút trước rồi `MERGE` quan hệ

Khi **cả hai đầu mút đều đã tồn tại**:

~~~cypher
MATCH (p:Person {personId: 'P-101'})
MATCH (t:Team {teamId: 'T-01'})
MERGE (p)-[r:MEMBER_OF]->(t)
RETURN p.personId AS personId,
       type(r) AS relation,
       t.teamId AS teamId;
~~~

- `MATCH` đầu tiên gắn `p` với nút người có sẵn.
- `MATCH` thứ hai gắn `t` với nút nhóm có sẵn.
- `MERGE (p)-[r:MEMBER_OF]->(t)` tìm quan hệ đúng loại, đúng chiều giữa hai nút đó; nếu chưa có thì tạo quan hệ mới.
- Vì `p` và `t` đã được ràng buộc, bước `MERGE` không yêu cầu tạo lại hai nút đầu mút.

Nếu `MATCH` không tìm thấy một trong hai nút, không có dòng nào tới `MERGE`, nên **không tạo quan hệ**. Nếu `MATCH` trả nhiều nút cho một khóa, kết quả có thể phát sinh nhiều cặp và nhiều quan hệ; cần xử lý dữ liệu trùng và ràng buộc tính duy nhất.

### 5.3. Cách đúng khi nút cũng có thể chưa tồn tại

Nếu muốn tự tạo người, nhóm và kết nối khi cần, hãy dùng **ba mệnh đề `MERGE` riêng biệt**:

~~~cypher
MERGE (p:Person {personId: $personId})
  ON CREATE SET p.name = $personName
MERGE (t:Team {teamId: $teamId})
  ON CREATE SET t.name = $teamName
MERGE (p)-[r:MEMBER_OF]->(t)
  ON CREATE SET r.joinedAt = date(),
                r.role = $role
RETURN p.personId AS personId,
       t.teamId AS teamId,
       r.role AS role;
~~~

Đầu tiên, từng nút được nhận diện bằng khóa nghiệp vụ; cuối cùng quan hệ được tìm hoặc tạo giữa **hai biến đã buộc**. Các thuộc tính `joinedAt` và `role` nằm trên quan hệ vì mô tả việc **một người thuộc một nhóm**, không phải đặc điểm độc lập của người hoặc nhóm.

### 5.4. Hướng và kiểu quan hệ là một phần mẫu

~~~cypher
MERGE (a)-[:FOLLOWS]->(b)
~~~

không có cùng mẫu hướng với:

~~~cypher
MERGE (b)-[:FOLLOWS]->(a)
~~~

Với quan hệ có hướng, vị trí nút nguồn và nút đích quan trọng. Quan hệ `FOLLOWS` cũng khác `KNOWS` hay `MEMBER_OF`. Hãy chọn kiểu và hướng phản ánh quy tắc nghiệp vụ.

Cypher cho phép truy vấn mẫu không chỉ định hướng trong một số ngữ cảnh, nhưng khi tạo hoặc tìm quan hệ bằng `MERGE` nên **viết hướng tường minh** để người đọc hiểu rõ ý nghĩa dữ liệu.

## 6. `MERGE` quan hệ có thuộc tính

Thuộc tính có thể là một phần của điều kiện khớp quan hệ:

~~~cypher
MATCH (u:User {userId: $userId})
MATCH (c:Course {courseId: $courseId})
MERGE (u)-[r:ENROLLED_IN {enrollmentCode: $enrollmentCode}]->(c)
ON CREATE SET
  r.enrolledAt = datetime(),
  r.status = 'ACTIVE'
ON MATCH SET
  r.lastCheckedAt = datetime()
RETURN u.userId AS userId,
       c.courseId AS courseId,
       r.enrollmentCode AS enrollmentCode,
       r.status AS status;
~~~

Ở đây, `enrollmentCode` là thành phần nhận diện quan hệ đăng ký. Nếu thay đổi `enrollmentCode`, mẫu quan hệ cũng thay đổi, và câu lệnh có thể tạo thêm quan hệ mới. Đừng đặt trường dễ đổi như `status` vào phần nhận diện nếu nghiệp vụ muốn **cập nhật cùng một quan hệ**.

Nếu quy tắc là “mỗi người chỉ có một lần ghi danh trên mỗi khóa học”, có thể dùng mẫu:

~~~cypher
MATCH (u:User {userId: $userId})
MATCH (c:Course {courseId: $courseId})
MERGE (u)-[r:ENROLLED_IN]->(c)
ON CREATE SET r.enrolledAt = datetime()
SET r.status = $status
RETURN r;
~~~

Câu lệnh này phù hợp khi **cặp nút + kiểu quan hệ** xác định duy nhất kết nối theo nghiệp vụ. Nếu một người có thể ghi danh nhiều lần vào cùng khóa học (nhiều kỳ học, nhiều sự kiện), cần đưa định danh lần ghi danh vào mô hình, hoặc tạo nút `Enrollment` riêng. Trong trường hợp cần lưu **mọi sự kiện mới** thay vì hợp nhất sự kiện theo mẫu, `CREATE` thường phù hợp hơn.

## 7. `MERGE`, constraint và index

### 7.1. Vì sao cần constraint duy nhất?

Chỉ `MERGE` không thay thế quy tắc toàn vẹn dữ liệu. Nếu hai giao dịch đồng thời đều thấy chưa có nút `User` với cùng `userId`, việc thiếu constraint có thể dẫn đến bản ghi trùng. Hãy định nghĩa khóa nghiệp vụ và ràng buộc duy nhất:

~~~cypher
CREATE CONSTRAINT user_userId_unique IF NOT EXISTS
FOR (u:User)
REQUIRE u.userId IS UNIQUE;
~~~

~~~cypher
CREATE CONSTRAINT team_teamId_unique IF NOT EXISTS
FOR (t:Team)
REQUIRE t.teamId IS UNIQUE;
~~~

Với dữ liệu đúng chuẩn, constraint giúp ngăn **hai nút cùng nhãn có cùng giá trị khóa**. Constraint có thể khiến truy vấn vi phạm thất bại; ứng dụng phải xử lý lỗi và chính sách thử lại giao dịch khi phù hợp.

Trước khi tạo constraint trên cơ sở dữ liệu có sẵn, cần kiểm tra dữ liệu trùng. Nếu đã có nhiều nút `User` cùng `userId`, việc tạo constraint duy nhất sẽ không thành công cho đến khi dữ liệu được làm sạch.

### 7.2. Khớp một phần có thể gây lỗi constraint

Giả sử đã có:

~~~text
(:User {userId: 'U-101', email: 'an@example.com'})
~~~

và `userId` bị ràng buộc duy nhất. Truy vấn:

~~~cypher
MERGE (u:User {
  userId: 'U-101',
  email: 'an.new@example.com'
});
~~~

sẽ không khớp nút cũ vì `email` khác. Tạo nút mới lại vi phạm duy nhất `userId`, nên câu lệnh có thể báo lỗi. Cách sửa là nhận diện theo `userId` trước, sau đó cập nhật `email`:

~~~cypher
MERGE (u:User {userId: 'U-101'})
SET u.email = 'an.new@example.com'
RETURN u;
~~~

Constraint không làm thay đổi quy tắc “khớp toàn bộ mẫu” của `MERGE`.

### 7.3. Vai trò của index khi sử dụng `MERGE`

Index giúp Neo4j tìm nút theo nhãn và thuộc tính hiệu quả hơn, đặc biệt khi đồ thị lớn. Constraint duy nhất trên thuộc tính nút cũng hỗ trợ truy cập dữ liệu theo khóa đó. Khi `MERGE` chạy thường xuyên, cần cân nhắc:

- Đặt constraint cho khóa nghiệp vụ thực sự phải duy nhất.
- Chọn mẫu khớp có nhãn và khóa rõ ràng; tránh dùng tên tự do, giá trị không ổn định làm khóa.
- Xem kế hoạch thực thi bằng `EXPLAIN` để biết cách tìm nút; đo với `PROFILE` trên môi trường phù hợp vì `PROFILE` **thực thi truy vấn**, bao gồm truy vấn ghi.
- Tránh kết hợp `MERGE` với `MATCH` trả về quá nhiều dòng ngoài ý muốn; mỗi dòng có thể dẫn đến một lần đánh giá mẫu.

## 8. Lỗi thường gặp và cách xử lý

| Dấu hiệu | Nguyên nhân | Điều chỉnh |
|---|---|---|
| Chạy lại vẫn có nút trùng | Không có khóa ổn định hoặc dữ liệu có sẵn đã trùng | Xác định khóa nghiệp vụ, làm sạch dữ liệu, thêm constraint |
| Mỗi lần đổi tên lại tạo nút mới | Đưa `name` vào mẫu `MERGE` | `MERGE` theo ID; `SET` tên |
| Tạo bản sao của cả hai nút | `MERGE` cả đường nối khi nút chưa buộc | `MATCH` hoặc `MERGE` riêng từng nút, rồi `MERGE` quan hệ |
| Không thấy quan hệ mới | `MATCH` đầu mút không trả dòng | Kiểm tra nhãn, khóa và dữ liệu trước khi nối |
| Quan hệ xuất hiện nhiều bản | Dữ liệu đầu mút hoặc quan hệ đã trùng; ghi đồng thời | Làm sạch dữ liệu, xác định mô hình duy nhất, thiết kế giao dịch/constraint phù hợp |
| Lỗi constraint khi `MERGE` | Mẫu có thuộc tính không khớp nhưng khóa duy nhất đã tồn tại | Chỉ `MERGE` bằng khóa, dùng `SET` cho thuộc tính thay đổi |
| Truy vấn lỗi với giá trị `null` | Thuộc tính dùng trong mẫu `MERGE` mang giá trị `null` | Kiểm tra hoặc loại dòng thiếu khóa trước `MERGE` |
| Cập nhật không chạy khi tạo mới | Dùng `ON MATCH SET` nhưng nút vừa được tạo | Dùng `ON CREATE SET` hoặc `SET` chung |

### Giá trị `null` trong khóa khớp

Ví dụ sau không thể dùng một `userId = null` làm điều kiện để tạo/khớp nút:

~~~cypher
MERGE (u:User {userId: $userId})
RETURN u;
~~~

Khi tham số `$userId` là `null`, `MERGE` sẽ lỗi vì không thể tìm/tạo nút bằng thuộc tính khóa `null` trong mẫu. Nên kiểm tra ở tầng ứng dụng. Với nhập danh sách, có thể bỏ qua dòng thiếu khóa:

~~~cypher
UNWIND $users AS item
WITH item
WHERE item.userId IS NOT NULL
MERGE (u:User {userId: item.userId})
ON CREATE SET u.createdAt = datetime()
SET u.displayName = item.displayName
RETURN count(DISTINCT u) AS distinctUsers;
~~~

Truy vấn bỏ qua các bản ghi không có `userId`; nếu nghiệp vụ yêu cầu mọi bản ghi phải hợp lệ, nên **báo lỗi xác thực** thay vì âm thầm bỏ qua.

## 9. Nhập dữ liệu theo lô với `UNWIND` + `MERGE`

Giả sử cần đồng bộ danh sách học viên nhiều lần từ nguồn bên ngoài. Dữ liệu tham số:

~~~json
{
  "students": [
    {"studentId": "ST-101", "name": "Hà", "city": "Hà Nội"},
    {"studentId": "ST-102", "name": "Linh", "city": "Đà Nẵng"},
    {"studentId": "ST-103", "name": "Khánh", "city": "TP.HCM"}
  ]
}
~~~

Truy vấn:

~~~cypher
UNWIND $students AS row
MERGE (s:Student {studentId: row.studentId})
ON CREATE SET s.createdAt = datetime()
SET s.name = row.name,
    s.city = row.city
RETURN count(DISTINCT s) AS studentsProcessed;
~~~

`UNWIND` chuyển từng phần tử danh sách thành dòng, và `MERGE` nhận diện học viên theo `studentId`. Khi chạy lại với cùng dữ liệu, truy vấn không cần tạo lại nút đã khớp. `count(DISTINCT s)` cho biết số **nút khác nhau được xử lý** trong kết quả, không phải số nút mới tạo.

Các lưu ý khi nhập hàng loạt:

1. Chuẩn hóa và kiểm tra khóa trước khi đưa vào `MERGE` (`studentId` không rỗng, kiểu dữ liệu thống nhất).
2. Xử lý khóa trùng trong cùng lô nếu các dòng mang thuộc tính mâu thuẫn; không nên phụ thuộc thứ tự `UNWIND` để chọn bản ghi thắng.
3. Thiết lập constraint duy nhất cho `Student.studentId` khi dữ liệu yêu cầu một nút cho mỗi học viên.
4. Với dữ liệu lớn, chia lô hoặc dùng cơ chế giao dịch theo lô phù hợp phiên bản và môi trường, tránh một giao dịch quá lớn.
5. Theo dõi số dòng đầu vào, số thực thể được xử lý và các lỗi constraint; đừng suy từ `count(*)` rằng có cùng số nút được tạo.

## 10. Ví dụ hoàn chỉnh: đồng bộ học viên và đăng ký khóa học

Bài toán: hệ thống học tập cần quản lý **một nút cho mỗi học viên**, **một nút cho mỗi khóa học** và **một quan hệ đăng ký cho mỗi cặp học viên–khóa học**. Dữ liệu có thể được gửi lại sau lỗi mạng, vì vậy lặp lại thao tác không nên tạo thêm cùng kết nối.

### Bước 1 — Khai báo khóa duy nhất

Chạy một lần khi thiết lập mô hình, sau khi bảo đảm dữ liệu hiện có không vi phạm:

~~~cypher
CREATE CONSTRAINT learner_learnerId_unique IF NOT EXISTS
FOR (l:Learner)
REQUIRE l.learnerId IS UNIQUE;
~~~

~~~cypher
CREATE CONSTRAINT course_courseId_unique IF NOT EXISTS
FOR (c:Course)
REQUIRE c.courseId IS UNIQUE;
~~~

### Bước 2 — Tìm hoặc tạo nút, rồi tìm hoặc tạo quan hệ

~~~cypher
MERGE (l:Learner {learnerId: 'L-901'})
ON CREATE SET
  l.fullName = 'Trần An',
  l.createdAt = datetime()
MERGE (c:Course {courseId: 'C-901'})
ON CREATE SET
  c.title = 'Neo4j nền tảng',
  c.createdAt = datetime()
MERGE (l)-[r:ENROLLED_IN]->(c)
ON CREATE SET
  r.enrolledAt = datetime(),
  r.status = 'ACTIVE'
RETURN l.learnerId AS learnerId,
       c.courseId AS courseId,
       r.enrolledAt AS enrolledAt,
       r.status AS status;
~~~

Đồ thị kết quả:

~~~text
(:Learner {learnerId: 'L-901', fullName: 'Trần An'})
          |
          | [:ENROLLED_IN {status: 'ACTIVE', enrolledAt: ...}]
          v
(:Course {courseId: 'C-901', title: 'Neo4j nền tảng'})
~~~

Nếu chạy lần thứ hai trong điều kiện dữ liệu không trùng và không có giao dịch ghi cạnh tranh gây ra quan hệ song song, truy vấn sẽ tìm các nút và quan hệ đã có. `ON CREATE SET r.enrolledAt` không chạy lại, nên thời gian ghi danh ban đầu được giữ nguyên.

### Bước 3 — Kiểm tra kết quả bằng `MATCH`

~~~cypher
MATCH (l:Learner {learnerId: 'L-901'})
      -[r:ENROLLED_IN]->
      (c:Course {courseId: 'C-901'})
RETURN l.fullName AS learner,
       c.title AS course,
       r.status AS status,
       r.enrolledAt AS enrolledAt;
~~~

Trong mô hình hợp lệ với mỗi cặp chỉ một quan hệ đăng ký, truy vấn trả về **một dòng**. Nếu trả nhiều dòng, dữ liệu có thể đã có quan hệ trùng và cần rà soát.

### Bước 4 — Cập nhật trạng thái đăng ký

Vì `status` là thuộc tính thay đổi, không đưa nó vào mẫu `MERGE`:

~~~cypher
MATCH (l:Learner {learnerId: 'L-901'})
MATCH (c:Course {courseId: 'C-901'})
MERGE (l)-[r:ENROLLED_IN]->(c)
ON CREATE SET r.enrolledAt = datetime()
SET r.status = 'COMPLETED',
    r.updatedAt = datetime()
RETURN r.status AS status, r.updatedAt AS updatedAt;
~~~

Cách này có thể tạo quan hệ khi chưa có và cập nhật `status` trên quan hệ được khớp hoặc vừa tạo. Nếu nghiệp vụ **chỉ cho phép cập nhật đăng ký đã tồn tại**, thay `MERGE` quan hệ bằng `MATCH (l)-[r:ENROLLED_IN]->(c)` để không tự tạo quan hệ.

### Bước 5 — Trường hợp cần nhiều lần đăng ký

Nếu một học viên có thể học lại cùng khóa học qua nhiều đợt, không nên ép mọi lần ghi danh vào một quan hệ duy nhất. Có thể mô hình hóa mỗi lần đăng ký thành một nút có `enrollmentId` riêng:

~~~cypher
MATCH (l:Learner {learnerId: $learnerId})
MATCH (c:Course {courseId: $courseId})
MERGE (e:Enrollment {enrollmentId: $enrollmentId})
ON CREATE SET e.enrolledAt = datetime()
MERGE (l)-[:HAS_ENROLLMENT]->(e)
MERGE (e)-[:FOR_COURSE]->(c)
RETURN e.enrollmentId AS enrollmentId;
~~~

Ở đây, mỗi lần đăng ký có khóa riêng, cho phép cùng học viên ghi danh nhiều lần; nên thiết lập constraint cho `Enrollment.enrollmentId` nếu định danh bắt buộc duy nhất. Cần bảo đảm `enrollmentId` gắn với đúng học viên và khóa học theo quy tắc nghiệp vụ; câu lệnh trên không tự xác thực quan hệ hiện có nếu đầu vào mâu thuẫn.

## 11. Sử dụng `MERGE` từ Neo4j Java Driver

Ứng dụng Java nên truyền tham số, quản lý giao dịch và kiểm tra lỗi constraint. Ví dụ một phương thức đồng bộ một học viên:

~~~java
import java.util.Map;
import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;

public final class LearnerRepository {
    private final Driver driver;

    public LearnerRepository(Driver driver) {
        this.driver = driver;
    }

    public String upsertLearner(String learnerId, String fullName) {
        String cypher = """
                MERGE (l:Learner {learnerId: $learnerId})
                ON CREATE SET l.createdAt = datetime()
                SET l.fullName = $fullName
                RETURN l.learnerId AS id
                """;

        try (Session session = driver.session()) {
            return session.executeWrite(tx ->
                    tx.run(cypher, Map.of(
                            "learnerId", learnerId,
                            "fullName", fullName
                    )).single().get("id").asString()
            );
        }
    }
}
~~~

Giải thích:

- `Driver` được ứng dụng quản lý vòng đời; `Session` được đóng sau mỗi thao tác.
- `executeWrite(...)` thực hiện công việc ghi trong một transaction function của Driver.
- `$learnerId` và `$fullName` là tham số, tránh nối trực tiếp đầu vào vào chuỗi Cypher.
- `single()` phù hợp khi constraint và mô hình bảo đảm truy vấn trả đúng một dòng. Nếu dữ liệu có nhiều nút trùng `learnerId`, kết quả có thể không còn đúng một dòng.
- Transaction function có thể được Driver gọi lại khi xảy ra lỗi tạm thời theo cơ chế retry. Do đó, không nên đặt thao tác bên ngoài Neo4j không an toàn khi lặp (như gửi email thanh toán) ngay trong callback.
- `Map.of(...)` không nhận giá trị Java `null`; nên kiểm tra khóa và dữ liệu trước khi gọi.

Nếu dùng Spring Data Neo4j, entity và repository giúp ánh xạ đồ thị vào Java. Khi cần chính xác ngữ nghĩa `MERGE`/`ON CREATE`/`ON MATCH`, có thể viết câu Cypher tùy biến qua `@Query` và tham số phù hợp; không nên mặc định rằng mọi lời gọi `save(...)` tương đương nguyên xi một lệnh `MERGE`.

## 12. Thực hành và câu hỏi tự kiểm tra

### Bài tập 1 — Tìm hoặc tạo sản phẩm

Viết câu lệnh theo yêu cầu:

- `sku` định danh sản phẩm.
- Chỉ đặt `createdAt` lúc tạo lần đầu.
- Giá bán `price` được cập nhật ở mọi lần thực hiện.
- Trả về `sku`, `price`.

<details>
<summary>Gợi ý lời giải</summary>

~~~cypher
MERGE (p:Product {sku: $sku})
ON CREATE SET p.createdAt = datetime()
SET p.price = $price
RETURN p.sku AS sku, p.price AS price;
~~~

</details>

### Bài tập 2 — Nối nút có sẵn

Giả sử đã có `(:Author {authorId: 'A-01'})` và `(:Book {bookId: 'B-01'})`. Viết truy vấn bảo đảm quan hệ `WROTE` theo chiều Author → Book tồn tại mà không tạo lại các nút.

<details>
<summary>Gợi ý lời giải</summary>

~~~cypher
MATCH (a:Author {authorId: 'A-01'})
MATCH (b:Book {bookId: 'B-01'})
MERGE (a)-[:WROTE]->(b)
RETURN a.authorId AS authorId, b.bookId AS bookId;
~~~

</details>

### Bài tập 3 — Dự đoán kết quả

Đồ thị đã có hai nút nhưng chưa có quan hệ:

~~~text
(:Person {personId: 'P-777'})
(:Team {teamId: 'T-777'})
~~~

Không có constraint. Bạn chạy:

~~~cypher
MERGE (:Person {personId: 'P-777'})
      -[:MEMBER_OF]->
      (:Team {teamId: 'T-777'});
~~~

**Câu hỏi:** Truy vấn có buộc phải dùng lại hai nút đã có không?

**Đáp án:** Không. Toàn mẫu chưa tồn tại, nên `MERGE` có thể tạo toàn bộ mẫu mới, kể cả hai nút đầu mút. Cách đúng là `MATCH` hai nút trước, rồi `MERGE` quan hệ; hoặc `MERGE` từng nút riêng biệt và dùng biến để nối chúng.

### Bài tập 4 — Định danh bằng thuộc tính thay đổi

Vì sao nên tránh:

~~~cypher
MERGE (u:User {userId: $userId, displayName: $displayName});
~~~

**Đáp án:** Khi tên thay đổi, mẫu không còn khớp. Truy vấn có thể tạo nút trùng hoặc vi phạm constraint. Thay bằng `MERGE (u:User {userId: $userId}) SET u.displayName = $displayName`.

### Bài tập 5 — Kiểm tra ngữ nghĩa của quan hệ

Một ứng dụng lưu lịch sử mỗi lần người dùng nhấp vào sản phẩm. Bạn nên dùng `CREATE` hay `MERGE` cho từng lần nhấp?

**Đáp án:** Nếu mỗi lượt nhấp là **một sự kiện riêng cần được lưu đầy đủ**, sử dụng `CREATE` để thêm sự kiện mới (thường là một nút Event với ID riêng), hoặc `MERGE` theo một `eventId` thực sự duy nhất khi cần chống gửi lại cùng sự kiện. `MERGE` chỉ theo cặp người dùng–sản phẩm sẽ gộp các lượt nhấp thành một mẫu kết nối và đánh mất số lần/sự kiện riêng nếu không có mô hình khác hỗ trợ.

## 13. Ghi nhớ

- `MERGE` là **tìm hoặc tạo theo mẫu**: nếu mẫu khớp thì dùng lại dữ liệu; nếu không thì tạo mẫu.
- `MERGE` đánh giá **toàn bộ mẫu được viết**, không tự nhận diện từng nút của đường nối.
- Với **nút**, dùng nhãn và khóa nghiệp vụ ổn định trong phần `MERGE`; để thuộc tính có thể thay đổi ở `SET`.
- `ON CREATE SET` chạy khi mẫu được tạo; `ON MATCH SET` chạy khi mẫu đã khớp.
- Với **quan hệ**, hãy ràng buộc các nút bằng `MATCH` hoặc `MERGE` riêng trước khi `MERGE` kết nối.
- Constraint duy nhất giúp bảo vệ danh tính nút, đặc biệt khi đồng bộ và ghi đồng thời; index hỗ trợ hiệu năng tìm kiếm.
- Dữ liệu trùng sẵn có, khóa `null`, nhiều kết quả `MATCH` và ghi cạnh tranh vẫn đòi hỏi xử lý đúng ở tầng dữ liệu và ứng dụng.
- `UNWIND` + `MERGE` là nền tảng cho import lặp lại; Java Driver giúp thực thi tham số hóa và giao dịch.

**Học tiếp:** Kết hợp `MERGE` với `MATCH`, `SET`, `REMOVE`, index/constraint, kế hoạch truy vấn và giao dịch khi xây dựng hệ thống Neo4j bằng Java Driver hoặc Spring Data Neo4j.
