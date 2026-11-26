# Nút, nhãn và thuộc tính trong mô hình đồ thị thuộc tính

## 1. Mục tiêu học tập và bối cảnh

Neo4j là cơ sở dữ liệu đồ thị sử dụng **mô hình đồ thị thuộc tính** (*property graph*). Trong module `DATABASE_ENGINE_GRAPH_NEO4J`, mô hình này là nền tảng để biểu diễn dữ liệu có nhiều mối liên kết, truy vấn quan hệ và đường đi bằng **Cypher**, rồi tiến tới thiết kế index, constraint, nhập dữ liệu, tích hợp Java Driver/Spring Data Neo4j và vận hành hệ thống.

Sau bài học, bạn có thể:

- Giải thích **node (nút)**, **label (nhãn)** và **property (thuộc tính)**; phân biệt vai trò của chúng với **relationship (quan hệ)**.
- Mô hình hóa một thực thể thành nút có một hoặc nhiều nhãn và một tập thuộc tính phù hợp.
- Dùng Cypher tạo, tìm kiếm, đọc và cập nhật nút, nhãn, thuộc tính.
- Hiểu cách Neo4j xử lý thuộc tính thiếu giá trị, `null`, kiểu dữ liệu và định danh nút.
- Biết khi nào cần ràng buộc duy nhất, index và khi nào nên tách dữ liệu thành nút có quan hệ.

Hãy hình dung một hệ thống nhân sự: người, công ty và kỹ năng đều có thể trở thành nút; một người làm việc cho một công ty hoặc biết một kỹ năng được biểu diễn bằng quan hệ. Bài này tập trung vào **cấu tạo của mỗi nút**; quan hệ chỉ được nhắc tới để đặt các thành phần vào đúng ngữ cảnh.

## 2. Cấu trúc cơ bản của property graph

Một đồ thị thuộc tính gồm các **nút** và **quan hệ**. Cả hai có thể mang thuộc tính; nút có thể có một hoặc nhiều nhãn. Ví dụ:

```text
(:Person:Employee {
    personId: "p001",
    fullName: "Nguyễn An",
    active: true
})
          |
          | [:WORKS_AT {since: 2023}]
          v
(:Company {
    companyId: "c001",
    name: "GreenTech"
})
```

| Thành phần | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Node** | Một thực thể trong đồ thị, có danh tính riêng | Nút đại diện cho Nguyễn An |
| **Label** | Phân loại/vai trò gắn lên nút; một nút có thể mang nhiều nhãn | `:Person`, `:Employee` |
| **Property** | Cặp `key: value` lưu thông tin của nút hoặc quan hệ | `fullName: "Nguyễn An"` |
| **Relationship** | Kết nối có hướng và có kiểu giữa hai nút | `[:WORKS_AT]` |

Trong cú pháp Cypher:

- `(p)`: biến `p` đại diện cho một nút, chưa giới hạn nhãn.
- `(p:Person)`: nút có nhãn `Person`.
- `(p:Person:Employee)`: cùng một nút có **cả hai** nhãn `Person` và `Employee`.
- `(p:Person {personId: 'p001'})`: nút có nhãn `Person` và thuộc tính `personId` mang giá trị `'p001'`.
- `(p)-[:WORKS_AT]->(c)`: quan hệ từ nút `p` đến nút `c`; hướng mũi tên là một phần của mô hình.

**Lưu ý:** Nút `Person` không phải một dòng trong bảng `Person` theo nghĩa bắt buộc của cơ sở dữ liệu quan hệ. Neo4j cho phép các nút cùng nhãn mang những tập thuộc tính khác nhau; quy ước mô hình và constraint giúp dữ liệu nhất quán.

## 3. Node: thực thể có danh tính

**Node** là đơn vị biểu diễn một sự vật, con người, sự kiện hoặc khái niệm cần lưu trữ và kết nối. Ví dụ: khách hàng, tài khoản, đơn hàng, sản phẩm, địa điểm. Mỗi nút tồn tại độc lập với các giá trị thuộc tính của nó: hai nút có cùng tên và ngày sinh vẫn là **hai nút khác nhau** nếu được tạo riêng.

Trong Neo4j, câu lệnh `CREATE` tạo nút mới:

```cypher
CREATE (p:Person:Employee {
  personId: 'p001',
  fullName: 'Nguyễn An',
  age: 29,
  active: true,
  skills: ['Java', 'Cypher'],
  joinedOn: date('2024-07-01')
})
RETURN p;
```

Ở đây, `p` là biến cục bộ trong truy vấn, **không phải thuộc tính lưu trong cơ sở dữ liệu**. Nút có hai nhãn, sáu thuộc tính và được lưu trữ sau khi truy vấn ghi thành công. Nếu chạy lại `CREATE`, Neo4j sẽ tạo **một nút khác**; bản thân `CREATE` không tự kiểm tra trùng `personId`.

### 3.1. Danh tính kỹ thuật và định danh nghiệp vụ

Neo4j cung cấp `elementId(p)` để tham chiếu phần tử trong các thao tác nhất định. Tuy nhiên, không nên xem `elementId` là khóa nghiệp vụ ổn định khi xuất/nhập, tái tạo hoặc di chuyển dữ liệu. Ứng dụng thường cần một thuộc tính riêng như `personId`, `customerId` hoặc `orderId`:

```cypher
MATCH (p:Person {personId: 'p001'})
RETURN p.personId AS personId, elementId(p) AS elementId;
```

**Nguyên tắc:** Dùng mã nghiệp vụ bất biến để tra cứu, trao đổi giữa các hệ thống và tạo liên kết qua API; áp dụng **uniqueness constraint** để ngăn hai nút cùng nhãn mang cùng mã (xem mục 8).

## 4. Label: phân loại và biểu đạt vai trò của nút

Label là tên phân loại, đặt sau dấu `:` trong Cypher. Không cần khai báo bảng hoặc tạo label trước: khi ghi một nút có label, Neo4j sẽ sử dụng tên label đó trong dữ liệu. Label có tính chất **tập hợp**: một nút có thể mang nhiều nhãn; nhiều nút có thể mang cùng một nhãn.

Ví dụ, nhân viên đồng thời là một con người:

```cypher
MATCH (p:Person {personId: 'p001'})
SET p:Mentor
RETURN labels(p) AS labels;
```

Kết quả là danh sách nhãn có thể gồm `Person`, `Employee`, `Mentor` (không nên phụ thuộc vào thứ tự phần tử của danh sách này). Nếu vai trò `Mentor` không còn phù hợp:

```cypher
MATCH (p:Person {personId: 'p001'})
REMOVE p:Mentor
RETURN labels(p) AS labels;
```

### 4.1. Khi nào dùng label, khi nào dùng property?

| Câu hỏi thiết kế | Thường dùng **label** | Thường dùng **property** |
| --- | --- | --- |
| Biểu thị nhóm thực thể/vai trò có ý nghĩa trong đồ thị? | `:Person`, `:Employee`, `:Company` | Không phải lựa chọn chính |
| Lọc theo trạng thái hoặc giá trị có thể thay đổi thường xuyên? | Không cần tạo nhãn mới cho mỗi giá trị | `status: 'ACTIVE'`, `age: 29` |
| Cần truy vấn mọi nút của một loại, đặt constraint/index theo loại? | Có: `MATCH (p:Person)` | Có thể thêm bộ lọc thuộc tính |
| Là giá trị gần như duy nhất cho từng nút? | Không dùng label kiểu `:Person_p001` | `personId: 'p001'` |

Quy ước đặt tên nên rõ ràng và nhất quán: label như `Person`, `Order`, `Customer`, thuộc tính như `personId`, `createdAt`. Neo4j phân biệt chữ hoa và chữ thường: `:Person` khác `:person`, `fullName` khác `fullname`.

Label không tự bảo đảm tất cả nút `:Person` đều có `personId` hoặc `fullName`. Việc bắt buộc thuộc tính phải có, kiểm tra giá trị duy nhất hoặc kiểm tra kiểu có thể cần constraint và quy tắc ứng dụng.

## 5. Property: dữ liệu mô tả nút

Property là cặp **khóa – giá trị**. Trong ví dụ `{fullName: 'Nguyễn An', age: 29}`, `fullName` và `age` là khóa; `'Nguyễn An'` và `29` là giá trị. Cùng một nhãn, các nút có thể có các thuộc tính khác nhau:

```cypher
CREATE (:Person {personId: 'p002', fullName: 'Bình'});
CREATE (:Person {personId: 'p003', fullName: 'Chi', email: 'chi@example.com'});
```

Vì vậy, không thể suy ra rằng mọi nút `Person` đều có `email`. Không có thuộc tính `email` vẫn là trạng thái dữ liệu hợp lệ nếu mô hình không bắt buộc nó.

### 5.1. Các kiểu giá trị thường gặp

| Nhóm | Ví dụ thuộc tính | Cú pháp Cypher |
| --- | --- | --- |
| Chuỗi (`STRING`) | Tên, email, mã nghiệp vụ | `fullName: 'Nguyễn An'` |
| Số nguyên (`INTEGER`) | Tuổi, số lần đăng nhập | `age: 29` |
| Số thực (`FLOAT`) | Điểm trung bình, tọa độ đo lường | `rating: 4.5` |
| Logic (`BOOLEAN`) | Trạng thái kích hoạt | `active: true` |
| Ngày, giờ và khoảng thời gian | Ngày tham gia, thời điểm tạo | `joinedOn: date('2024-07-01')`, `createdAt: datetime()` |
| Tọa độ không gian | Vị trí địa lý | `location: point({latitude: 10.82, longitude: 106.63})` |
| Danh sách giá trị đơn giản | Kỹ năng, nhãn từ khóa do ứng dụng quản lý | `skills: ['Java', 'Cypher']` |

Khi **lưu thành thuộc tính**, Neo4j hỗ trợ các kiểu giá trị thuộc tính hợp lệ, trong đó có các kiểu cơ bản, không gian, thời gian và danh sách phù hợp. **Map lồng nhau**, danh sách chứa node/relationship hoặc cấu trúc đối tượng tùy ý có thể tồn tại trong biểu thức Cypher nhưng **không thể gán nguyên xi thành một property lưu trữ**. Hãy tách thành các property phẳng hoặc các nút liên kết, tùy bản chất dữ liệu.

Ví dụ sau minh họa map dùng tạm để xử lý trong truy vấn, không phải thuộc tính lưu trữ:

```cypher
WITH {city: 'Hà Nội', postalCode: '100000'} AS address
RETURN address.city AS city;
```

Nếu địa chỉ chỉ là thông tin đơn giản của một người, có thể dùng `city` và `postalCode` làm hai property. Nếu một địa chỉ cần chia sẻ giữa nhiều người, có lịch sử thay đổi hoặc cần tìm đường qua các địa điểm, cân nhắc nút `:Address`/`:Location` và relationship.

### 5.2. `null` và thuộc tính không tồn tại

Trong Neo4j, **property có giá trị `null` không được lưu như một cặp khóa – giá trị thông thường**. Gán `null` cho property có tác dụng **xóa** property đó:

```cypher
MATCH (p:Person {personId: 'p001'})
SET p.nickname = 'An'
RETURN p.nickname AS nickname;

MATCH (p:Person {personId: 'p001'})
SET p.nickname = null
RETURN p.nickname AS nickname;
```

Ở truy vấn thứ hai, `nickname` bị xóa; đọc `p.nickname` sẽ trả về `null`. Truy vấn kiểm tra:

```cypher
MATCH (p:Person)
WHERE p.email IS NULL
RETURN p.personId AS personId;

MATCH (p:Person)
WHERE p.email IS NOT NULL
RETURN p.personId AS personId, p.email AS email;
```

`IS NULL` tìm cả tình huống khóa thuộc tính không tồn tại; muốn cung cấp giá trị dự phòng khi đọc, dùng `coalesce(p.email, 'Chưa cung cấp')`. Đừng nhầm `null` với chuỗi rỗng `''`, giá trị `false` hay số `0`: các giá trị sau có thể được lưu và mang ý nghĩa riêng.

### 5.3. Đọc nhiều thuộc tính

```cypher
MATCH (p:Person {personId: 'p001'})
RETURN
  p.fullName AS fullName,
  keys(p) AS propertyKeys,
  properties(p) AS allProperties,
  labels(p) AS nodeLabels;
```

- `p.fullName` truy cập một property bằng tên.
- `keys(p)` trả về các khóa property đang tồn tại.
- `properties(p)` trả về map gồm các property hiện có.
- `labels(p)` trả về danh sách label, không phải property.

## 6. Thao tác với node, label và property bằng Cypher

Các ví dụ sau minh họa thao tác riêng lẻ. Khi thực hành trên cùng cơ sở dữ liệu, lưu ý `CREATE` có thể tạo dữ liệu trùng nếu chạy nhiều lần.

### 6.1. Tìm nút theo nhãn và điều kiện

```cypher
MATCH (p:Person)
WHERE p.active = true AND p.age >= 18
RETURN p.personId AS id, p.fullName AS name, p.age AS age
ORDER BY name;
```

`MATCH (p:Person)` giới hạn tập ứng viên theo label; `WHERE` lọc theo giá trị property. Trong đồ thị lớn, index thích hợp có thể giúp giảm lượng dữ liệu phải quét (xem mục 8).

### 6.2. Cập nhật property mà vẫn giữ các thuộc tính khác

```cypher
MATCH (p:Person {personId: 'p001'})
SET p.age = 30,
    p.department = 'Engineering'
RETURN p;
```

Có thể cộng dồn tập thuộc tính từ một map:

```cypher
MATCH (p:Person {personId: 'p001'})
SET p += {age: 31, active: true}
RETURN p;
```

`SET p += {...}` chỉ cập nhật/thêm các khóa được chỉ rõ (khóa có giá trị `null` sẽ bị xóa). Ngược lại, `SET p = {...}` **thay thế toàn bộ tập thuộc tính** của nút, có thể làm mất các thuộc tính không có trong map; chỉ dùng khi đó là chủ đích.

Xóa thuộc tính bằng `REMOVE`:

```cypher
MATCH (p:Person {personId: 'p001'})
REMOVE p.department
RETURN keys(p) AS remainingKeys;
```

### 6.3. Dùng tham số thay vì ghép chuỗi vào truy vấn

Ứng dụng Java/Spring Data Neo4j thường truyền dữ liệu qua **Cypher parameters**, ví dụ `$personId` và `$fullName`. Cách này giúp tách cấu trúc câu lệnh khỏi dữ liệu, cho phép tái sử dụng truy vấn và hạn chế rủi ro chèn mã Cypher:

```cypher
MATCH (p:Person {personId: $personId})
SET p.fullName = $fullName
RETURN p.personId AS id, p.fullName AS name;
```

Khi gọi truy vấn, client cung cấp map tham số tương ứng, chẳng hạn `{personId: 'p001', fullName: 'Nguyễn An'}`. Các dấu `$` là phần của cú pháp tham số, không phải tên property trong cơ sở dữ liệu.

### 6.4. `MERGE` để tìm hoặc tạo nút theo khóa xác định

`MERGE` cố gắng khớp mẫu nút; nếu không có mẫu phù hợp thì tạo mới. Với khóa định danh riêng, ta thường viết:

```cypher
MERGE (p:Person {personId: $personId})
ON CREATE SET
  p.fullName = $fullName,
  p.createdAt = datetime()
RETURN p;
```

`MERGE` **không thay thế uniqueness constraint** khi có nhiều giao dịch đồng thời. Hãy tạo constraint cho `personId` trước để bảo vệ tính duy nhất. Tránh đưa các thuộc tính có thể thay đổi như `fullName` hoặc `email` vào cùng map mẫu `MERGE`, vì giá trị thay đổi có thể làm mẫu không khớp và dẫn đến tạo nút ngoài ý muốn.

## 7. Ví dụ mô hình hóa: khách hàng và đơn hàng

Giả sử một nền tảng đặt hàng cần lưu thông tin khách hàng và các đơn hàng. Một mô hình đơn giản:

```text
(:Person:Customer {customerId, fullName, email})
                  |
                  | [:PLACED]
                  v
          (:Order {orderId, totalAmount, placedAt})
```

**Vì sao cần tách nút `Order`?** Một khách hàng có thể tạo nhiều đơn; mỗi đơn có định danh, ngày đặt, tổng tiền và các quan hệ riêng với sản phẩm, giao hàng hoặc thanh toán. Nếu lưu toàn bộ đơn vào chuỗi hay danh sách trên nút khách hàng, việc truy vấn từng đơn, cập nhật và đi theo các mối liên kết sẽ khó hơn.

Tạo dữ liệu ví dụ:

```cypher
CREATE (c:Person:Customer {
  customerId: 'C001',
  fullName: 'Lan',
  email: 'lan@example.com'
})
CREATE (o:Order {
  orderId: 'O101',
  totalAmount: 850000,
  placedAt: datetime('2025-03-15T10:30:00+07:00')
})
CREATE (c)-[:PLACED]->(o)
RETURN c, o;
```

Truy vấn tên khách hàng và đơn họ đã đặt:

```cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)
RETURN c.customerId AS customerId,
       c.fullName AS customerName,
       o.orderId AS orderId,
       o.totalAmount AS totalAmount;
```

Ví dụ này minh họa ba lớp ý nghĩa:

1. **Node** `c` đại diện cho khách hàng; `o` đại diện cho một đơn hàng riêng biệt.
2. **Label** `Person` và `Customer` cùng phân loại nút `c`; `Order` phân loại nút `o`.
3. **Property** lưu các dữ kiện của từng thực thể; **relationship** `PLACED` diễn đạt khách hàng đặt đơn.

Trong dữ liệu thực tế, nên thiết lập constraint cho `customerId`, `orderId` và lựa chọn chiến lược chống tạo trùng trước khi nhập hàng loạt.

## 8. Index và constraint gắn với label/property

Property graph linh hoạt về cấu trúc, nhưng hệ thống sản xuất thường phải kiểm soát chất lượng dữ liệu và tốc độ truy vấn. Hai cơ chế nền tảng:

| Công cụ | Mục đích | Ví dụ |
| --- | --- | --- |
| **Constraint** | Áp đặt quy tắc toàn vẹn, ví dụ giá trị mã không trùng giữa các nút cùng label | `Person.personId` duy nhất |
| **Index** | Hỗ trợ truy xuất theo label và property trong các dạng truy vấn thích hợp | Tra cứu `Person.fullName` |

Tạo constraint duy nhất cho mã người:

```cypher
CREATE CONSTRAINT person_id_unique IF NOT EXISTS
FOR (p:Person)
REQUIRE p.personId IS UNIQUE;
```

Tạo index trên tên:

```cypher
CREATE INDEX person_full_name_idx IF NOT EXISTS
FOR (p:Person)
ON (p.fullName);
```

Kiểm tra định nghĩa hiện có:

```cypher
SHOW CONSTRAINTS;
SHOW INDEXES;
```

Constraint duy nhất ngăn **hai giá trị `personId` bằng nhau**, nhưng **không mặc nhiên bắt buộc mọi nút `Person` đều có thuộc tính này**. Muốn vừa bắt buộc tồn tại vừa duy nhất, hãy tìm hiểu thêm về existence constraint/node key và điều kiện hỗ trợ của phiên bản, edition Neo4j đang dùng.

Để quan sát kế hoạch thực thi của một truy vấn:

```cypher
EXPLAIN
MATCH (p:Person {personId: 'p001'})
RETURN p;
```

`EXPLAIN` chỉ lập kế hoạch, không chạy truy vấn. Khi có index/constraint phù hợp, bộ tối ưu **có thể** sử dụng thao tác tra cứu bằng index; quyết định cụ thể phụ thuộc dữ liệu, thống kê, điều kiện truy vấn và phiên bản Neo4j. Đừng mặc định cứ có index là mọi truy vấn đều nhanh hơn.

## 9. Những sai lầm thiết kế thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Tạo label riêng cho từng người, ví dụ `:Person_C001` | Khó truy vấn cả loại thực thể, phát sinh nhiều label không có ý nghĩa mô hình | Dùng `:Person` và `personId: 'C001'` |
| Cho rằng `CREATE` tự bảo đảm `personId` không trùng | Có thể tạo hai nút biểu diễn cùng thực thể | Dùng khóa nghiệp vụ, uniqueness constraint và chiến lược nhập dữ liệu phù hợp |
| Dùng tên người hoặc email dễ đổi làm định danh duy nhất dài hạn | Đổi tên/email khiến liên kết nghiệp vụ thiếu ổn định | Ưu tiên ID bền vững; kiểm tra email riêng nếu nghiệp vụ cần |
| Lưu danh sách đối tượng lồng nhau vào một property | Không phù hợp kiểu property lưu trữ và khó truy vấn quan hệ | Tách thành các property cơ bản hoặc các node/relationship |
| Xem `null` giống chuỗi rỗng | Sai kết quả lọc và cập nhật | Dùng `IS NULL`/`IS NOT NULL` và định nghĩa rõ ý nghĩa dữ liệu thiếu |
| Dùng `SET n = {...}` khi chỉ muốn sửa một trường | Mất các trường không được nhắc trong map | Dùng `SET n.key = value` hoặc `SET n += {...}` |
| Lẫn `:Person` với `:person`, `fullName` với `fullname` | Truy vấn không tìm thấy dữ liệu như mong đợi | Áp dụng quy ước đặt tên thống nhất, kiểm tra `labels(n)`/`keys(n)` |
| Xem `elementId(n)` là mã nghiệp vụ bất biến | Có thể mất tính ổn định khi dữ liệu được tái tạo hoặc chuyển môi trường | Lưu định danh nghiệp vụ riêng |

Một tiêu chí hữu ích khi lựa chọn giữa **property** và **node**: nếu dữ liệu chỉ mô tả đơn giản một thực thể, property thường đủ; nếu đối tượng có danh tính riêng, nhiều thuộc tính, nhiều liên kết hoặc cần truy vấn độc lập, hãy cân nhắc node.

## 10. Thực hành có hướng dẫn

Để tránh ảnh hưởng dữ liệu thật, hãy chạy phần thực hành trong một database thử nghiệm. Các câu lệnh bên dưới giả định chưa có nút `Skill` với mã `S001`.

**Bài 1 – Tạo nút đa nhãn và đọc thuộc tính**

```cypher
CREATE (s:Skill:TechnicalSkill {
  skillId: 'S001',
  name: 'Cypher',
  level: 'BEGINNER'
})
RETURN labels(s) AS labels,
       properties(s) AS properties;
```

Quan sát `Skill` và `TechnicalSkill` là **hai nhãn của cùng một nút**, còn `skillId`, `name` và `level` là các thuộc tính.

**Bài 2 – Thay đổi thuộc tính và nhãn**

```cypher
MATCH (s:Skill {skillId: 'S001'})
SET s.level = 'INTERMEDIATE'
SET s:QueryLanguageSkill
REMOVE s:TechnicalSkill
RETURN labels(s) AS labels, s.level AS level;
```

Dự kiến: nút còn nhãn `Skill` và có nhãn `QueryLanguageSkill`, không còn nhãn `TechnicalSkill`; `level` mang giá trị `INTERMEDIATE`. Việc thay đổi nhãn không tự tạo nút mới.

**Bài 3 – Kiểm tra thuộc tính vắng mặt**

```cypher
MATCH (s:Skill {skillId: 'S001'})
REMOVE s.level
RETURN s.level AS level,
       'level' IN keys(s) AS hasLevel;
```

Dự kiến: `level` trả về `null`, `hasLevel` bằng `false`. Lý do là thuộc tính `level` không còn được lưu trong nút.

Nếu muốn thử tính duy nhất, trước tiên tạo constraint `skillId` trên nhãn `Skill` trong database thử nghiệm, sau đó thử tạo hai nút có cùng `skillId`; thao tác thứ hai phải bị từ chối nếu cả hai đều mang nhãn `Skill` và constraint đang có hiệu lực.

## 11. Tổng kết

- **Node** đại diện cho thực thể có danh tính; **label** phân loại/vai trò; **property** lưu cặp khóa–giá trị; **relationship** nối các nút.
- Một node có thể có nhiều label và một tập property linh hoạt. Label không tự ép buộc tất cả node phải có cùng thuộc tính.
- `CREATE` tạo mới; `MATCH` truy vấn; `SET` cập nhật property/label; `REMOVE` loại bỏ property/label; `MERGE` tìm hoặc tạo theo mẫu.
- Property không lưu trực tiếp giá trị `null`; khóa bị thiếu được đọc thành `null`. Tránh lưu map lồng nhau như một property và chọn đúng kiểu dữ liệu.
- Dùng định danh nghiệp vụ kèm constraint phù hợp để quản lý thực thể; dùng index cho nhu cầu truy vấn thực tế. Mô hình hóa đối tượng có liên kết riêng thành node và relationship khi cần.

Nắm chắc ba thành phần **node – label – property** giúp bạn viết mẫu Cypher chính xác, tránh dữ liệu trùng và tạo nền tảng cho các bài tiếp theo về relationship, đường đi, lập chỉ mục, tối ưu truy vấn và tích hợp Neo4j với ứng dụng Java.
