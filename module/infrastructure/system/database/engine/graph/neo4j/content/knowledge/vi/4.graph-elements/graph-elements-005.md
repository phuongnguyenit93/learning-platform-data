# Phân biệt thuộc tính của nút với thuộc tính của quan hệ

## 1. Mục tiêu học tập

Trong Neo4j, **property graph** gồm các **nút** (*node*) và **quan hệ** (*relationship*). Cả hai đều có thể lưu **thuộc tính** (*property*) dưới dạng cặp khóa–giá trị, nhưng việc chọn nơi đặt thuộc tính quyết định **ý nghĩa**, **khả năng truy vấn** và **độ chính xác** của dữ liệu.

Bài học thuộc chương **Thành phần đồ thị** của module `DATABASE_ENGINE_GRAPH_NEO4J`. Phạm vi module là sử dụng Neo4j để mô hình hóa dữ liệu liên kết, truy vấn quan hệ và đường đi bằng Cypher; từ đây tiếp tục tìm hiểu index, constraint, tối ưu truy vấn, nhập dữ liệu, Neo4j Java Driver, Spring Data Neo4j và vận hành cơ sở dữ liệu đồ thị.

Sau bài học, bạn có thể:

1. Phân biệt thuộc tính mô tả **thực thể** với thuộc tính mô tả **một liên kết cụ thể**.
2. Mô hình hóa đúng những dữ kiện thay đổi theo cặp nút, chẳng hạn **vai trò khi làm việc**, **ngày bắt đầu hợp tác**, **số lượng sản phẩm trong đơn hàng**.
3. Đọc, thêm, sửa và xóa property trên node và relationship bằng **Cypher**.
4. Nhận biết tình huống một cặp nút có **nhiều quan hệ**, từ đó tránh cập nhật sai hoặc đếm sai dữ liệu.
5. Biết khi nào một mối liên kết có **danh tính và vòng đời riêng** nên được nâng thành nút trung gian.
6. Hiểu tác động của việc đặt property đến index, constraint và cách ứng dụng Java tương tác với Neo4j.

## 2. Cùng là property, nhưng thuộc về hai đối tượng khác nhau

Ví dụ một người tên **An** làm việc tại công ty **Alpha**:

```text
(:Person {
  personId: 'P001',
  fullName: 'An',
  email: 'an@example.com'
})
          |
          | [:WORKS_AT {
          |   role: 'Developer',
          |   startedOn: 2024-01-10
          | }]
          v
(:Company {
  companyId: 'C001',
  name: 'Alpha',
  country: 'VN'
})
```

Trong mô hình này:

- `Person.personId`, `Person.fullName` và `Person.email` mô tả **người An**.
- `Company.companyId`, `Company.name` và `Company.country` mô tả **công ty Alpha**.
- `WORKS_AT.role` và `WORKS_AT.startedOn` mô tả **việc An làm tại Alpha**, không phải bản chất cố định của An hay Alpha.

Đọc bằng Cypher:

```cypher
MATCH (p:Person)-[r:WORKS_AT]->(c:Company)
RETURN p.fullName AS personName,
       c.name AS companyName,
       r.role AS roleAtCompany,
       r.startedOn AS employmentStart;
```

**Quy tắc trực giác:** Nếu một giá trị chỉ có nghĩa khi biết **cả hai đầu mút** và **loại quan hệ**, nó thường thuộc relationship. Nếu giá trị mô tả một thực thể ngay cả khi chưa xét liên kết cụ thể nào, nó thường thuộc node.

## 3. So sánh thuộc tính node và relationship

| Tiêu chí | Property của **node** | Property của **relationship** |
| --- | --- | --- |
| Đối tượng được mô tả | Một thực thể, sự vật, khái niệm | Một liên kết/hành động giữa hai thực thể |
| Vị trí lưu | Trong dấu ngoặc tròn `(n:Label {key: value})` | Trong dấu ngoặc vuông `-[r:TYPE {key: value}]->` |
| Ví dụ phù hợp | `Person.fullName`, `Company.name`, `Product.sku` | `WORKS_AT.startedOn`, `FOLLOWS.since`, `CONTAINS.quantity` |
| Có cần biết đầu mút để hiểu? | Thường không | Thường có |
| Số giá trị khi một thực thể có nhiều liên kết | Một property trên node biểu diễn giá trị ở cấp thực thể | Mỗi relationship có bộ property **riêng** |
| Truy cập bằng Cypher | `p.fullName`, `properties(p)` | `r.startedOn`, `properties(r)` |
| Phạm vi index/constraint | Theo **label** của nút và property | Theo **type** của relationship và property |
| Hướng của liên kết | Không có hướng | Relationship có **start node** và **end node** |

Một node có thể có nhiều label nhưng property vẫn thuộc **node duy nhất** đó. Mỗi relationship có **đúng một type**, có hai đầu mút và một tập property riêng. Neo4j cho phép hai node nối với nhau bằng **nhiều relationship**, kể cả cùng type và cùng hướng.

### 3.1. Cú pháp nhìn nhanh

```cypher
// Thuộc tính của nút: email thuộc về p
(p:Person {personId: 'P001', email: 'an@example.com'})

// Thuộc tính của quan hệ: since thuộc về r
(p)-[r:FOLLOWS {since: date('2025-06-01')}]->(q)

// Thuộc tính của nút còn lại: name thuộc về q
(q:Person {personId: 'P002', name: 'Bình'})
```

Ba dòng trên minh họa **các mẫu cú pháp**, không phải ba câu lệnh độc lập để chạy trực tiếp. Khi tạo dữ liệu thật, dùng `CREATE` hoặc `MERGE` trong một câu lệnh đầy đủ.

## 4. Câu hỏi quyết định nơi đặt thuộc tính

Khi xây dựng mô hình, hãy lần lượt hỏi:

1. **Dữ kiện này nói về ai/cái gì?** Một người, sản phẩm hay công ty? Đặt trên node tương ứng.
2. **Giá trị có thay đổi theo người còn lại trong liên kết không?** Một người có chức vụ khác nhau ở hai công ty? Đặt ở quan hệ làm việc hoặc thực thể việc làm.
3. **Có thể tồn tại nhiều lần liên kết giữa cùng hai nút không?** Hai lần mua cùng sản phẩm có ngày, giá khác nhau? Cần lưu mỗi lần thành một relationship riêng hoặc nút sự kiện.
4. **Bản thân liên kết có định danh, trạng thái, lịch sử và nhiều quan hệ khác không?** Khi đó một node riêng như `Employment`, `OrderLine` hoặc `Booking` có thể phù hợp hơn.
5. **Dữ kiện thay đổi vào thời điểm nào?** Là giá trị hiện tại của thực thể hay ảnh chụp tại thời điểm một giao dịch diễn ra? Cần tránh ghi đè lịch sử.

Ví dụ, `Product.currentPrice` có thể thuộc sản phẩm nếu nó biểu diễn giá đang niêm yết; `CONTAINS.unitPriceAtOrder` biểu diễn **giá được áp dụng trong một đơn cụ thể**. Đổi giá sản phẩm hôm nay không được làm thay đổi giá của các đơn đã hoàn thành.

## 5. Ví dụ xuyên suốt: một người làm việc tại nhiều công ty

Giả sử An từng là Developer tại Alpha và hiện là Tech Lead tại Beta.

```text
                              [:WORKS_AT {
 (:Person {                    assignmentId: 'A001',
   personId: 'P001',            role: 'Developer',
   fullName: 'An'              startedOn: 2021-03-01,
 }) ─────────────────────────→ endedOn: 2023-12-31
  │                          }] (:Company {name: 'Alpha'})
  │
  │ [:WORKS_AT {
  │   assignmentId: 'A002',
  │   role: 'Tech Lead',
  │   startedOn: 2024-01-01
  │ }]
  └──────────────────────────→ (:Company {name: 'Beta'})
```

**Vì sao không để `role: 'Tech Lead'` trực tiếp trên node `Person`?**

Nếu An cùng lúc làm ở hai công ty, `Person.role` không nói rõ chức vụ đó thuộc công ty nào. Nếu chỉ giữ chức vụ mới nhất trên `Person`, thông tin lịch sử về vị trí tại Alpha bị ghi đè.

Đặt `role`, `startedOn`, `endedOn` trên **mỗi quan hệ `WORKS_AT`** thể hiện đúng bối cảnh. Trong khi đó, `fullName` và `personId` vẫn thuộc `Person`; `name` và `companyId` vẫn thuộc `Company`.

### 5.1. Khởi tạo bộ dữ liệu thử nghiệm

Chạy một lần trong **database dùng để học**, vì `CREATE` luôn tạo dữ liệu mới:

```cypher
CREATE (an:Person {
  personId: 'GE005-P001',
  fullName: 'An',
  email: 'an@example.com'
})
CREATE (alpha:Company {
  companyId: 'GE005-C001',
  name: 'Alpha',
  country: 'VN'
})
CREATE (beta:Company {
  companyId: 'GE005-C002',
  name: 'Beta',
  country: 'VN'
})
CREATE (an)-[:WORKS_AT {
  assignmentId: 'GE005-A001',
  role: 'Developer',
  startedOn: date('2021-03-01'),
  endedOn: date('2023-12-31')
}]->(alpha)
CREATE (an)-[:WORKS_AT {
  assignmentId: 'GE005-A002',
  role: 'Tech Lead',
  startedOn: date('2024-01-01')
}]->(beta)
RETURN an, alpha, beta;
```

Mỗi lần `CREATE` thành công, Neo4j tạo hai relationship độc lập giữa An và hai công ty. Thuộc tính `role` cùng tên nhưng có **hai giá trị ở hai liên kết**.

### 5.2. Đọc property ở đúng cấp

```cypher
MATCH (p:Person {personId: 'GE005-P001'})
      -[r:WORKS_AT]->(c:Company)
RETURN p.personId AS personId,
       p.fullName AS personName,
       c.companyId AS companyId,
       c.name AS companyName,
       r.assignmentId AS assignmentId,
       r.role AS roleAtCompany,
       r.startedOn AS startedOn,
       r.endedOn AS endedOn
ORDER BY startedOn;
```

Kết quả dự kiến:

| personName | companyName | roleAtCompany | startedOn | endedOn |
| --- | --- | --- | --- | --- |
| An | Alpha | Developer | 2021-03-01 | 2023-12-31 |
| An | Beta | Tech Lead | 2024-01-01 | `null` |

`null` trong kết quả của Beta xuất hiện vì `endedOn` **chưa tồn tại trên relationship đó**. Không tự suy ra `null` luôn nghĩa là “đang làm”: trong hệ thống thật, nó cũng có thể nghĩa là chưa biết. Hãy xác định quy ước nghiệp vụ rõ ràng; có thể dùng property `status` nếu cần phân biệt “đang làm”, “đã nghỉ” và “không rõ”.

### 5.3. Cập nhật chức vụ tại một công ty

```cypher
MATCH (p:Person {personId: 'GE005-P001'})
      -[r:WORKS_AT {assignmentId: 'GE005-A002'}]->
      (c:Company {companyId: 'GE005-C002'})
SET r.role = 'Engineering Manager'
RETURN p.fullName AS personName,
       c.name AS companyName,
       r.role AS newRole;
```

Lệnh này thay `role` của **quan hệ làm việc A002**, không thay property của node An và cũng không tác động đến vai trò Developer tại Alpha.

Nếu thay bằng:

```cypher
MATCH (p:Person {personId: 'GE005-P001'})
SET p.role = 'Engineering Manager'
RETURN p.fullName AS name, p.role AS role;
```

Thì `p.role` trở thành **thuộc tính của node Person**, không phải thuộc tính của `WORKS_AT`. Dữ liệu vẫn hợp lệ về cú pháp nhưng **khác ngữ nghĩa**; nếu ứng dụng có cả hai trường `p.role` và `r.role`, phải quy định rõ nguồn thông tin nào là chính xác để tránh mâu thuẫn.

## 6. Thuộc tính quan hệ biểu diễn ngữ cảnh của mối liên kết

Một số mẫu thông dụng:

| Mẫu đồ thị | Property node | Property relationship | Lý do |
| --- | --- | --- | --- |
| `(Person)-[:WORKS_AT]->(Company)` | `Person.fullName`, `Company.name` | `role`, `startedOn`, `endedOn` | Vai trò và thời hạn thuộc lần làm việc tại công ty |
| `(User)-[:FOLLOWS]->(User)` | `User.userId`, `User.displayName` | `since`, `notificationsEnabled` | Mỗi người có cấu hình theo dõi khác nhau cho từng người khác |
| `(Order)-[:CONTAINS]->(Product)` | `Order.orderId`, `Product.sku` | `quantity`, `unitPriceAtOrder` | Số lượng và giá mua thuộc từng dòng sản phẩm trong đơn |
| `(Service)-[:DEPENDS_ON]->(Service)` | `Service.name`, `Service.version` | `dependencyType`, `criticality` | Mức độ phụ thuộc là của cặp dịch vụ |
| `(Person)-[:ATTENDED]->(Event)` | `Person.personId`, `Event.eventId` | `checkedInAt`, `ticketClass` | Thời điểm check-in và hạng vé thuộc lần tham dự |

### 6.1. Cùng khóa property không có nghĩa cùng ngữ nghĩa

Neo4j không cấm một node và một relationship cùng có property tên `status`. Ví dụ:

```cypher
(u:User {status: 'ACTIVE'})
  -[:SUBSCRIBED_TO {status: 'PAUSED'}]->
(channel:Channel {status: 'PUBLIC'})
```

Ở đây:

- `u.status` là trạng thái tài khoản.
- `r.status` là trạng thái đăng ký của người dùng với kênh.
- `channel.status` là trạng thái công khai của kênh.

Tên khóa giống nhau, nhưng chúng thuộc **ba đối tượng khác nhau**. Trong truy vấn, dùng biến cụ thể (`u.status`, `r.status`, `channel.status`) để tránh nhầm lẫn.

### 6.2. Thuộc tính mô tả sự kiện và lịch sử

Hai người có thể gặp nhau nhiều lần hoặc một tài khoản chuyển tiền nhiều lần đến tài khoản khác:

```text
(:Account A)-[:TRANSFERRED {eventId: 'T001', amount: 100000}]->(:Account B)
(:Account A)-[:TRANSFERRED {eventId: 'T002', amount: 250000}]->(:Account B)
```

Hai `amount` thuộc **hai lần chuyển tiền**. Nếu lưu `amount` trên node A hoặc B, không thể biết số tiền nào thuộc giao dịch nào. Neo4j cho phép nhiều relationship cùng hướng, cùng type và hai đầu mút; chính property `eventId` giúp phân biệt các sự kiện về mặt nghiệp vụ.

Trong tình huống tài chính, có thể lưu tiền bằng **số nguyên ở đơn vị nhỏ nhất** (ví dụ đồng hoặc xu) cùng `currency` nếu phù hợp, để tránh những sai số không mong muốn khi biểu diễn bằng số thực.

## 7. Cùng cơ chế property: kiểu dữ liệu và giá trị `null`

Về kỹ thuật, node và relationship đều dùng cơ chế lưu property tương tự. Các loại giá trị thường gặp:

| Loại | Ví dụ node | Ví dụ relationship |
| --- | --- | --- |
| Chuỗi | `fullName: 'An'` | `role: 'Developer'` |
| Số nguyên | `age: 28` | `quantity: 3` |
| Số thực | `rating: 4.5` | `weight: 0.85` |
| Boolean | `active: true` | `approved: false` |
| Date/time | `birthDate: date('1998-04-01')` | `startedOn: date('2024-01-01')` |
| Danh sách giá trị hợp lệ | `skills: ['Java', 'Cypher']` | `permissions: ['READ', 'WRITE']` |
| Điểm không gian | `location: point({latitude: 10.82, longitude: 106.63})` | `meetingPoint: point({latitude: 10.82, longitude: 106.63})` |

**Lưu ý:** Trong Cypher, map và danh sách phức tạp có thể tồn tại tạm thời trong biểu thức, nhưng không thể lưu một **map lồng nhau bất kỳ** hoặc một node/relationship như giá trị của một property thông thường. Nếu cần dữ liệu cấu trúc phức tạp và có liên kết riêng, cân nhắc tạo node/relationship thay vì nhồi mọi thứ vào property.

### 7.1. Property không tồn tại và `null`

Đọc một property không tồn tại trả về `null`:

```cypher
MATCH (p:Person {personId: 'GE005-P001'})
      -[r:WORKS_AT {assignmentId: 'GE005-A002'}]->
      (c:Company)
RETURN p.nickname AS nickname,
       r.endedOn AS endedOn,
       c.name AS companyName;
```

Trong dữ liệu mẫu, `p.nickname` và `r.endedOn` đều không có, nên kết quả tương ứng là `null`.

Gán `null` cho property của node hoặc relationship có nghĩa **xóa property**:

```cypher
MATCH (p:Person {personId: 'GE005-P001'})
SET p.nickname = 'A'
SET p.nickname = null
RETURN p.nickname AS nickname;
```

```cypher
MATCH (:Person {personId: 'GE005-P001'})
      -[r:WORKS_AT {assignmentId: 'GE005-A002'}]->(:Company)
SET r.note = 'Cần cập nhật'
SET r.note = null
RETURN r.note AS note;
```

Kiểm tra thuộc tính thiếu bằng `IS NULL`:

```cypher
MATCH (p:Person)-[r:WORKS_AT]->(c:Company)
WHERE r.endedOn IS NULL
RETURN p.fullName AS personName, c.name AS companyName;
```

**Phân biệt:** `null` khác chuỗi rỗng `''`, số `0` và Boolean `false`; những giá trị này có thể được lưu và mang ý nghĩa riêng.

## 8. Đọc property và metadata bằng Cypher

Các hàm cơ bản:

| Hàm/biểu thức | Tác dụng |
| --- | --- |
| `p.fullName` | Đọc thuộc tính `fullName` từ node `p` |
| `r.role` | Đọc thuộc tính `role` từ relationship `r` |
| `properties(p)` | Lấy map property hiện có của node |
| `properties(r)` | Lấy map property hiện có của relationship |
| `keys(p)` | Lấy tên các property hiện có trên node |
| `keys(r)` | Lấy tên các property hiện có trên relationship |
| `labels(p)` | Lấy các label của node, không phải property |
| `type(r)` | Lấy type của relationship, không phải property |
| `startNode(r)` | Lấy node đầu theo hướng lưu của relationship |
| `endNode(r)` | Lấy node cuối theo hướng lưu của relationship |

Ví dụ đọc cạnh cùng hai đầu mút:

```cypher
MATCH (p:Person {personId: 'GE005-P001'})-[r:WORKS_AT]->(c:Company)
RETURN labels(p) AS personLabels,
       properties(p) AS personProperties,
       type(r) AS relationshipType,
       properties(r) AS employmentProperties,
       labels(c) AS companyLabels,
       properties(c) AS companyProperties
ORDER BY r.startedOn;
```

Có thể hiển thị từng cặp key–value cho mục đích kiểm tra dữ liệu:

```cypher
MATCH (p:Person {personId: 'GE005-P001'})-[r:WORKS_AT]->(c:Company)
UNWIND keys(r) AS propertyName
RETURN c.name AS companyName,
       propertyName,
       r[propertyName] AS propertyValue
ORDER BY companyName, propertyName;
```

`r[propertyName]` đọc property theo **tên khóa động**. Đây là cách phù hợp khi chưa biết trước mọi property của relationship. Với truy vấn ứng dụng đã biết trường cần lấy, ưu tiên `r.role` hoặc `r.startedOn` để code dễ hiểu.

## 9. Cập nhật và xóa property: cùng cú pháp, khác đối tượng

### 9.1. Thêm/sửa property trên node

```cypher
MATCH (p:Person {personId: 'GE005-P001'})
SET p.email = 'an.new@example.com',
    p.updatedAt = datetime()
RETURN properties(p) AS personProperties;
```

### 9.2. Thêm/sửa property trên relationship

```cypher
MATCH (p:Person {personId: 'GE005-P001'})
      -[r:WORKS_AT {assignmentId: 'GE005-A002'}]->
      (c:Company {companyId: 'GE005-C002'})
SET r.role = 'Engineering Manager',
    r.updatedAt = datetime()
RETURN properties(r) AS employmentProperties;
```

### 9.3. Cập nhật map property

`SET n += {...}` hoặc `SET r += {...}` thêm/cập nhật các khóa được liệt kê, giữ lại các khóa khác:

```cypher
MATCH (p:Person {personId: 'GE005-P001'})
SET p += {active: true, department: 'Engineering'}
RETURN properties(p);
```

```cypher
MATCH (:Person)-[r:WORKS_AT {assignmentId: 'GE005-A002'}]->(:Company)
SET r += {role: 'Tech Lead', employmentType: 'FULL_TIME'}
RETURN properties(r);
```

Ngược lại, `SET p = {...}` hoặc `SET r = {...}` **thay toàn bộ tập property**, có thể xóa các khóa không xuất hiện trong map. Khi chỉ cập nhật một vài trường, nên dùng `+=` hoặc `SET ... .key`.

### 9.4. Xóa property không đồng nghĩa xóa node/relationship

```cypher
MATCH (p:Person {personId: 'GE005-P001'})
REMOVE p.department
RETURN keys(p) AS personPropertyKeys;
```

```cypher
MATCH (:Person)-[r:WORKS_AT {assignmentId: 'GE005-A002'}]->(:Company)
REMOVE r.employmentType
RETURN keys(r) AS relationshipPropertyKeys;
```

Hai câu trên chỉ xóa property. **`DELETE r` xóa cả relationship**, còn **`DELETE p` xóa node** (và phải xử lý các cạnh còn nối với node). Đừng dùng thao tác xóa phần tử khi chỉ cần bỏ một thuộc tính.

## 10. Quan hệ song song: đặt property đúng nhưng vẫn cần định danh

Một người có thể làm tại **cùng công ty qua nhiều đợt tuyển dụng**:

```text
(:Person An) ──[:WORKS_AT {
    assignmentId: 'A101',
    role: 'Developer',
    startedOn: 2020-01-01,
    endedOn: 2021-12-31
}]──→ (:Company Alpha)

(:Person An) ──[:WORKS_AT {
    assignmentId: 'A205',
    role: 'Consultant',
    startedOn: 2025-03-01
}]──→ (:Company Alpha)
```

Hai relationship có cùng type, hướng và đầu mút nhưng đại diện **hai đợt làm việc độc lập**. Không nên dùng duy nhất cặp người–công ty làm khóa phân biệt các đợt.

### 10.1. Cẩn trọng khi MATCH một cặp đầu mút

Ví dụ:

```cypher
MATCH (p:Person {personId: $personId})-[r:WORKS_AT]->
      (c:Company {companyId: $companyId})
SET r.role = $role;
```

Nếu tồn tại **nhiều `WORKS_AT` giữa hai node**, câu lệnh này cập nhật **tất cả** relationship khớp mẫu. Khi cần sửa **một đợt làm việc cụ thể**, thêm điều kiện định danh:

```cypher
MATCH (p:Person {personId: $personId})
      -[r:WORKS_AT {assignmentId: $assignmentId}]->
      (c:Company {companyId: $companyId})
SET r.role = $role
RETURN r.assignmentId AS assignmentId, r.role AS role;
```

Ở mô hình này, `assignmentId` nên được cấp riêng cho từng đợt, và hệ thống cần kiểm soát tính duy nhất của ID nghiệp vụ.

### 10.2. Đếm số liên kết và số thực thể liên quan

```cypher
MATCH (p:Person {personId: $personId})-[r:WORKS_AT]->(c:Company)
RETURN count(r) AS employmentPeriods,
       count(DISTINCT c) AS distinctCompanies;
```

`count(r)` đếm **số quan hệ làm việc**; `count(DISTINCT c)` đếm **số công ty khác nhau**. Hai số có thể khác nhau vì một người có thể làm nhiều đợt tại cùng công ty.

## 11. Khi nên nâng quan hệ thành node riêng?

Relationship phù hợp khi dữ liệu chủ yếu mô tả **mối liên kết giữa hai node**. Tuy nhiên, có những trường hợp bản thân “lần liên kết” cần được quản lý như **thực thể độc lập**.

### 11.1. Ví dụ đơn hàng và dòng hàng

Một mô hình đơn giản:

```text
(:Order {orderId: 'O001'})
  -[:CONTAINS {quantity: 2, unitPriceAtOrder: 120000}]->
(:Product {sku: 'SKU001', name: 'Sách Cypher'})
```

`Product.name` và `Product.sku` mô tả sản phẩm. `CONTAINS.quantity` và `CONTAINS.unitPriceAtOrder` mô tả **dòng sản phẩm của đơn O001**. Đặt `quantity: 2` trên `Product` sẽ sai khi đơn O002 mua 5 cuốn.

Nếu một đơn có nhiều dòng cùng SKU với khuyến mãi khác nhau, mỗi dòng có mã riêng, trạng thái hoàn trả và quan hệ đến phiếu giảm giá, có thể dùng:

```text
(:Order {orderId: 'O001'})
     |
     | [:HAS_LINE]
     v
(:OrderLine {lineId: 'L001', quantity: 2, unitPrice: 120000})
     |
     | [:FOR_PRODUCT]
     v
(:Product {sku: 'SKU001'})
```

Khi đó `OrderLine` là **node có định danh riêng**, dễ nối tới những đối tượng liên quan (khuyến mãi, trả hàng, kho). Việc chọn mô hình nên dựa trên **quy tắc nghiệp vụ và kiểu truy vấn cần hỗ trợ**, không chỉ dựa trên số property.

### 11.2. Ví dụ hợp đồng lao động có vòng đời phức tạp

Nếu một lần làm việc có hợp đồng, phụ lục, phê duyệt, phòng ban, hồ sơ thuế và kiểm toán độc lập, có thể mô hình:

```text
(:Person)-[:HAS_EMPLOYMENT]->(:Employment {
  employmentId: 'E001',
  startedOn: date(...),
  status: 'ACTIVE'
})-[:AT_COMPANY]->(:Company)
```

Nút `Employment` mang thông tin của **một đợt làm việc**; nó có thể nối đến các thực thể khác. Nếu chỉ cần lưu `role` và `startedOn` theo từng cặp người–công ty, relationship `WORKS_AT` với property thường là đủ.

**Dấu hiệu nên cân nhắc node trung gian:** sự kiện/liên kết có ID riêng, nhiều trạng thái, vòng đời dài, nhiều thực thể khác tham chiếu đến nó, hoặc cần quan hệ từ **chính sự kiện** sang các node khác. Neo4j không cho phép gắn một relationship như **đầu mút của relationship khác**.

## 12. MERGE, idempotency và cập nhật dữ liệu chính xác

### 12.1. MERGE trên node

Để tạo hoặc tìm người theo mã nghiệp vụ:

```cypher
MERGE (p:Person {personId: $personId})
ON CREATE SET p.fullName = $fullName
RETURN p;
```

`MERGE` tìm theo mẫu, tạo khi không có mẫu phù hợp. Dùng uniqueness constraint trên `Person.personId` để chống trùng ID khi nhập dữ liệu hoặc ghi đồng thời.

### 12.2. MERGE trên relationship: chọn đúng khóa

Khi nghiệp vụ chỉ cho phép **một quan hệ hiện có** giữa một người và công ty theo cùng type/hướng, có thể dùng:

```cypher
MATCH (p:Person {personId: $personId})
MATCH (c:Company {companyId: $companyId})
MERGE (p)-[r:WORKS_AT]->(c)
ON CREATE SET r.startedOn = date()
RETURN r;
```

Nhưng khi **một người có nhiều đợt làm việc tại cùng công ty**, cách này **không phù hợp**, vì các đợt đều cùng mẫu `(p)-[:WORKS_AT]->(c)`. Khi đó cần phân biệt từng đợt, chẳng hạn bằng `assignmentId`:

```cypher
MATCH (p:Person {personId: $personId})
MATCH (c:Company {companyId: $companyId})
MERGE (p)-[r:WORKS_AT {assignmentId: $assignmentId}]->(c)
ON CREATE SET
  r.role = $role,
  r.startedOn = date($startedOn)
RETURN r.assignmentId AS assignmentId;
```

**Hai lưu ý:**

- `MERGE` khớp **toàn bộ mẫu**, gồm type, hướng, hai đầu mút và các property trong map. Nếu `assignmentId` đã được dùng cho một liên kết khác, hãy xử lý lỗi định danh thay vì âm thầm tạo/sửa sai giao dịch.
- `MERGE` không tự xóa relationship trùng đã tồn tại và không thay thế mọi cơ chế điều phối ghi đồng thời. Cần thiết kế transaction, constraint và xử lý xung đột theo nghiệp vụ.

### 12.3. Tránh đặt property có thể thay đổi trong khóa MERGE

Mẫu sau dễ gây hiểu lầm:

```cypher
MERGE (p:Person {personId: $personId, fullName: $fullName})
```

Nếu `fullName` thay đổi, **mẫu đầy đủ không khớp** và Neo4j có thể cố tạo người thứ hai, hoặc gặp lỗi uniqueness constraint. Tốt hơn nên `MERGE` theo `personId` rồi cập nhật `fullName` bằng `SET`.

Tương tự, với relationship nên `MERGE` theo **định danh của liên kết**, không đưa `role` hoặc ngày cập nhật vào map mẫu nếu các giá trị đó có thể thay đổi theo thời gian.

## 13. Index và constraint áp dụng ở đâu?

Trong Neo4j, index và constraint giúp tra cứu, kiểm soát dữ liệu theo **nhãn node**, **type relationship** và thuộc tính.

### 13.1. Constraint duy nhất trên property của node

```cypher
CREATE CONSTRAINT person_id_unique IF NOT EXISTS
FOR (p:Person)
REQUIRE p.personId IS UNIQUE;

CREATE CONSTRAINT company_id_unique IF NOT EXISTS
FOR (c:Company)
REQUIRE c.companyId IS UNIQUE;
```

Các constraint này ngăn hai node cùng nhãn `Person` có `personId` giống nhau hoặc hai node `Company` có `companyId` giống nhau.

### 13.2. Constraint duy nhất trên property của relationship

Với Neo4j hỗ trợ relationship property uniqueness constraints (ví dụ Neo4j 5 và các bản tương thích):

```cypher
CREATE CONSTRAINT works_at_assignment_unique IF NOT EXISTS
FOR ()-[r:WORKS_AT]-()
REQUIRE r.assignmentId IS UNIQUE;
```

Constraint trên **`WORKS_AT.assignmentId`** bảo vệ mã đợt làm việc, nhưng **không cấm nhiều `WORKS_AT` cùng cặp node** nếu mỗi đợt có mã riêng.

**Phân biệt:** Uniqueness constraint thường **không bắt buộc** mọi node/relationship trong phạm vi phải có property đó. Các ràng buộc về property existence hoặc key có điều kiện hỗ trợ theo phiên bản, edition Neo4j đang vận hành.

### 13.3. Index cho tra cứu

```cypher
CREATE INDEX person_email_idx IF NOT EXISTS
FOR (p:Person)
ON (p.email);

CREATE INDEX works_at_start_idx IF NOT EXISTS
FOR ()-[r:WORKS_AT]-()
ON (r.startedOn);
```

Index node hỗ trợ một số truy vấn theo email người; index relationship có thể hỗ trợ một số truy vấn theo ngày bắt đầu liên kết. Việc một index có được sử dụng hay không tùy điều kiện truy vấn, thống kê dữ liệu, phiên bản và bộ tối ưu; không nên tạo index cho mọi property một cách máy móc.

Kiểm tra kế hoạch:

```cypher
SHOW INDEXES;
SHOW CONSTRAINTS;

EXPLAIN
MATCH (p:Person {personId: $personId})-[r:WORKS_AT]->(c:Company)
WHERE r.startedOn >= date($fromDate)
RETURN p.fullName, c.name, r.startedOn;
```

`EXPLAIN` chỉ lập kế hoạch. `PROFILE` chạy truy vấn thực và cung cấp thông tin thực thi; nên kiểm tra trên dữ liệu phù hợp để đánh giá hiệu quả index.

## 14. Truy vấn nhiều quan hệ: không nhầm property và số hàng

### 14.1. Đếm đúng cấp

Ví dụ An có hai quan hệ `WORKS_AT`:

```cypher
MATCH (p:Person {personId: 'GE005-P001'})-[r:WORKS_AT]->(c:Company)
RETURN
  count(r) AS employmentRecords,
  count(DISTINCT c) AS companyCount;
```

`count(r)` đếm số **bản ghi liên kết**, `count(DISTINCT c)` đếm **công ty khác nhau**. Nếu một người đã làm hai lần ở cùng công ty, hai kết quả này khác nhau.

### 14.2. Nhân bản hàng khi ghép nhiều mẫu

Giả sử một người có 2 quan hệ `WORKS_AT` và 3 quan hệ `FOLLOWS`:

```cypher
MATCH (p:Person {personId: $personId})-[employment:WORKS_AT]->(c)
MATCH (p)-[following:FOLLOWS]->(friend)
RETURN count(employment) AS employmentRows,
       count(following) AS followingRows;
```

Truy vấn này có thể tạo **2 × 3 = 6 hàng ghép**; `count(employment)` và `count(following)` đều thành 6, không phản ánh số quan hệ thực tế. Nếu mục tiêu là đếm **relationship duy nhất**:

```cypher
MATCH (p:Person {personId: $personId})
OPTIONAL MATCH (p)-[employment:WORKS_AT]->()
WITH p, count(DISTINCT employment) AS employmentCount
OPTIONAL MATCH (p)-[following:FOLLOWS]->()
RETURN employmentCount,
       count(DISTINCT following) AS followingCount;
```

`OPTIONAL MATCH` cho phép người vẫn có mặt trong kết quả khi không có một loại quan hệ nào. Với các báo cáo phức tạp, cũng có thể tính từng nhóm qua subquery, rồi kết hợp theo mã thực thể.

### 14.3. Phân biệt trạng thái “không có liên kết” và “liên kết không có thuộc tính”

Hai trường hợp khác nhau:

1. **Không có `WORKS_AT`**: mẫu bắt buộc `MATCH (p)-[r:WORKS_AT]->(c)` không trả về hàng cho người đó.
2. **Có `WORKS_AT` nhưng thiếu `role`**: mẫu khớp, `r.role` trả về `null`.

Ví dụ giữ cả người chưa có công ty:

```cypher
MATCH (p:Person)
OPTIONAL MATCH (p)-[r:WORKS_AT]->(c:Company)
RETURN p.personId AS personId,
       c.name AS companyName,
       r.role AS roleAtCompany
ORDER BY personId, companyName;
```

Nhớ rằng với một người có nhiều quan hệ, `OPTIONAL MATCH` vẫn trả về **nhiều hàng**, mỗi hàng mô tả một liên kết khớp.

## 15. Tích hợp Java Driver và Spring Data Neo4j

### 15.1. Neo4j Java Driver: truyền tham số theo ngữ cảnh

Ứng dụng Java nên tách **cấu trúc câu lệnh Cypher** khỏi dữ liệu nhận từ người dùng. Ví dụ cập nhật ngày kết thúc **một quan hệ việc làm**:

```cypher
MATCH (p:Person {personId: $personId})
      -[r:WORKS_AT {assignmentId: $assignmentId}]->
      (c:Company {companyId: $companyId})
SET r.endedOn = date($endedOn)
RETURN p.personId AS personId,
       c.companyId AS companyId,
       r.assignmentId AS assignmentId,
       r.endedOn AS endedOn;
```

Client truyền map tham số, chẳng hạn:

```json
{
  "personId": "GE005-P001",
  "companyId": "GE005-C002",
  "assignmentId": "GE005-A002",
  "endedOn": "2027-06-30"
}
```

Không nối chuỗi tùy ý để chèn mã người, ID quan hệ hay giá trị ngày vào Cypher. Đặc biệt, cần giữ đúng cú pháp `r.endedOn` thay vì vô tình ghi `p.endedOn` hoặc `c.endedOn`.

### 15.2. Spring Data Neo4j: phân biệt entity và relationship properties

Trong Spring Data Neo4j, node thường được biểu diễn bằng entity có `@Node`; các thuộc tính của entity tương ứng với property trên node. Với relationship có thông tin riêng như `WORKS_AT.role`, `WORKS_AT.startedOn`, có thể mô hình hóa bằng loại đối tượng mang `@RelationshipProperties` kết hợp `@TargetNode` theo phiên bản hỗ trợ.

Về mặt ý tưởng:

```text
Person entity
  personId, fullName               → property trên (:Person)
  employment relationships         → các cạnh WORKS_AT

Employment relationship properties
  assignmentId, role, startedOn    → property trên [:WORKS_AT]
  targetNode                       → node (:Company)

Company entity
  companyId, name                  → property trên (:Company)
```

Cần chú ý:

- Quan hệ có **hướng** và **type**; cấu hình ánh xạ phải phù hợp với chiều lưu.
- Một người có thể có **nhiều relationship cùng type**, kể cả nhiều lần làm tại cùng công ty nếu nghiệp vụ cho phép.
- Việc cập nhật một entity không nên vô tình ghi đè dữ liệu của relationship khác.
- Khi dùng entity ánh xạ và Cypher tùy chỉnh trên cùng dữ liệu, phải kiểm tra hành vi lưu/đọc của phiên bản Spring Data Neo4j cụ thể.

Mô hình thuộc tính đúng từ đầu giúp ứng dụng Java phân biệt **thông tin thực thể** với **thông tin liên kết** mà không cần phỏng đoán dựa trên tên trường.

## 16. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Đặt `WORKS_AT.role` thành `Person.role` khi người có nhiều công việc | Không biết vai trò thuộc công ty nào, có thể ghi đè lịch sử | Đặt trên relationship hoặc node `Employment` |
| Đặt `OrderLine.quantity` thành `Product.quantity` | Nhầm số lượng đã mua với tồn kho/toàn cục | Lưu số lượng theo dòng đơn hàng |
| Dùng giá hiện tại `Product.price` cho đơn lịch sử | Đơn cũ đổi tổng tiền khi giá sản phẩm thay đổi | Lưu `unitPriceAtOrder` trên cạnh dòng hàng hoặc node `OrderLine` |
| Cập nhật `r.role` mà không xác định đúng relationship | Có thể sửa tất cả liên kết cùng cặp đầu–cuối | Dùng mã nghiệp vụ riêng như `assignmentId` |
| Cho rằng giữa hai nút chỉ có một relationship | Bỏ sót nhiều đợt làm việc/giao dịch | Xác định cardinality theo nghiệp vụ và truy vấn rõ ràng |
| Dùng `SET r = {...}` khi chỉ muốn sửa một property | Mất các property khác | Dùng `SET r.key = ...` hoặc `SET r += {...}` |
| Đồng nhất `null` với chuỗi rỗng hay trạng thái kết thúc | Diễn giải sai dữ liệu thiếu | Quy định rõ trạng thái, dùng `IS NULL` khi cần |
| Đếm số hàng sau nhiều `MATCH` rồi tưởng là số relationship | Đếm quá nhiều do tích Descartes giữa các mẫu | Dùng `DISTINCT` hoặc phân nhóm/subquery rõ ràng |
| Cho rằng index trên `Person.email` hỗ trợ mọi truy vấn theo `WORKS_AT.startedOn` | Kỳ vọng sai về hiệu năng | Chọn index theo label/type và property đang lọc |
| Biến mọi sự kiện phức tạp thành property của một cạnh | Khó gắn trạng thái, chứng từ và các mối liên hệ khác | Cân nhắc node trung gian có danh tính riêng |

## 17. Bài tập tự kiểm tra

### Bài 1. Phân loại nơi đặt thuộc tính

Với mô hình `(:Student)-[:ENROLLED_IN]->(:Course)`, hãy đặt các trường sau vào node hay relationship: `studentId`, `studentName`, `courseId`, `courseTitle`, `enrolledAt`, `finalGrade`.

**Đáp án gợi ý:** `studentId` và `studentName` thuộc `Student`; `courseId` và `courseTitle` thuộc `Course`; `enrolledAt` và `finalGrade` thuộc `ENROLLED_IN` vì mỗi học viên có thể ghi danh nhiều khóa, điểm cũng khác nhau theo khóa.

### Bài 2. Viết truy vấn đọc đúng property

Từ dữ liệu `GE005-P001`, trả về tên người, tên công ty, mã đợt làm việc và vai trò của từng lần làm việc.

**Đáp án:**

```cypher
MATCH (p:Person {personId: 'GE005-P001'})
      -[r:WORKS_AT]->(c:Company)
RETURN p.fullName AS person,
       c.name AS company,
       r.assignmentId AS assignment,
       r.role AS role
ORDER BY assignment;
```

### Bài 3. Đọc hai cú pháp SET

Cho `r` có `{assignmentId: 'A001', role: 'Developer', startedOn: date('2021-03-01')}`. Điều gì xảy ra nếu thực thi:

```cypher
SET r += {role: 'Senior Developer'}
```

So với:

```cypher
SET r = {role: 'Senior Developer'}
```

**Đáp án:** Với `+=`, chỉ `role` được thay, các property khác được giữ. Với `=`, toàn bộ property bị thay bằng map mới; `assignmentId` và `startedOn` biến mất, có thể vi phạm constraint hoặc phá dữ liệu.

### Bài 4. Nhận diện bản ghi liên kết

Một tài khoản A chuyển tiền đến B ba lần, mỗi lần có `eventId` riêng. Nên đặt `amount` ở đâu và vì sao?

**Đáp án:** Trên từng relationship `TRANSFERRED` hoặc trên node `Transfer` riêng cho mỗi giao dịch nếu có quy trình phức tạp. `amount` thuộc **mỗi lần chuyển**, không phải giá trị chung của tài khoản A hay B.

### Bài 5. Bổ sung điều kiện để không cập nhật nhầm

Đoạn mã sau có rủi ro gì nếu một người từng được thuê nhiều lần tại cùng công ty?

```cypher
MATCH (p:Person {personId: $personId})-[r:WORKS_AT]->
      (c:Company {companyId: $companyId})
SET r.role = $role;
```

**Đáp án:** Truy vấn sửa **mọi `WORKS_AT` khớp**. Hãy bổ sung `r.assignmentId = $assignmentId` hoặc điều kiện định danh nghiệp vụ khác để sửa **đúng đợt**; thiết lập constraint phù hợp để mã liên kết không bị trùng.

### Bài 6. Tư duy mô hình

Một lần tham dự hội nghị có vé, thanh toán, hóa đơn, lịch sử check-in/check-out và yêu cầu hoàn tiền. Nên lưu tất cả trên `[:ATTENDED]` hay tạo node `Attendance`?

**Đáp án gợi ý:** Node `Attendance` có định danh riêng thường phù hợp hơn vì bản thân lần tham dự có vòng đời và nhiều quan hệ riêng. Có thể dùng `(person)-[:HAS_ATTENDANCE]->(attendance)-[:FOR_EVENT]->(event)` và nối `attendance` với `Payment`, `Invoice`, `Refund` khi cần.

## 18. Tổng kết

- **Node property** mô tả **thực thể**: người, công ty, sản phẩm, đơn hàng. **Relationship property** mô tả **mối liên kết hoặc sự kiện** giữa hai thực thể.
- Khi một giá trị thay đổi theo **cặp nút, thời điểm hoặc lần tương tác**, hãy cân nhắc đặt trên relationship, không gắn vào node như thuộc tính toàn cục.
- Cả node và relationship đều hỗ trợ truy cập và cập nhật property bằng cú pháp như `properties(x)`, `keys(x)`, `SET x.key`, `SET x += {...}`, `REMOVE x.key`.
- Nhiều relationship có thể cùng type và hai đầu mút. Muốn sửa chính xác, cần **định danh từng liên kết** nếu nghiệp vụ có nhiều bản ghi.
- Dùng uniqueness constraint, index và transaction cho đúng **label/type và property**; không dùng `MERGE` theo property thay đổi để nhận diện thực thể.
- Khi một liên kết cần có **ID, vòng đời và các liên kết riêng**, mô hình node trung gian như `Employment` hoặc `OrderLine` có thể rõ ràng và dễ mở rộng hơn.

Phân biệt đúng property của nút và quan hệ là nền tảng để thiết kế property graph có ý nghĩa, viết Cypher chính xác, kiểm soát nhập dữ liệu, tối ưu truy vấn và ánh xạ dữ liệu với Neo4j Java Driver hoặc Spring Data Neo4j.
