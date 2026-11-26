# CREATE để tạo nút, quan hệ và thuộc tính trong Neo4j

> **Chương:** Tạo và cập nhật  
> **Chủ đề:** Sử dụng câu lệnh `CREATE` của Cypher để tạo dữ liệu theo mô hình *property graph*.

Trong mô-đun `DATABASE_ENGINE_GRAPH_NEO4J`, Neo4j được sử dụng để biểu diễn dữ liệu liên kết bằng **nút (node)**, **quan hệ (relationship)** và **thuộc tính (property)**. Cypher là ngôn ngữ để mô tả các mẫu đồ thị, truy vấn quan hệ và đường đi. `CREATE` là thao tác cơ bản để thêm nút hoặc quan hệ mới, gắn nhãn, kiểu quan hệ và thuộc tính ngay khi tạo. Đây cũng là nền tảng trước khi học `MATCH`, `MERGE`, `SET`, index, constraint, Java Driver hoặc Spring Data Neo4j.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích `CREATE` tạo thành phần nào trong mô hình property graph và cách đọc mẫu Cypher.
2. Tạo một hoặc nhiều nút với nhãn và thuộc tính; tạo quan hệ có hướng và thuộc tính của quan hệ.
3. Phân biệt **tạo cả hai nút mới** với **tạo quan hệ giữa hai nút đã có**.
4. Sử dụng tham số để truyền dữ liệu, và `UNWIND` để tạo nhiều bản ghi.
5. Nhận diện nguy cơ tạo trùng dữ liệu, dùng ràng buộc duy nhất khi cần, và phân biệt nhanh `CREATE` với `MERGE`.

## 2. `CREATE` và mô hình property graph

Xét dữ liệu “An tham gia dự án Kho tri thức với vai trò backend”:

~~~text
(:Person {personId: "P01", name: "An"})
       |
       | [:WORKS_ON {role: "backend"}]
       v
(:Project {projectId: "PR01", title: "Kho tri thức"})
~~~

| Thành phần | Ý nghĩa | Biểu diễn trong Cypher |
|---|---|---|
| Nút (node) | Một thực thể, ví dụ người hoặc dự án | `(p)` |
| Nhãn (label) | Nhóm/phân loại nút | `(p:Person)` |
| Thuộc tính nút | Dữ liệu dạng khóa–giá trị gắn với nút | `{personId: 'P01', name: 'An'}` |
| Quan hệ (relationship) | Kết nối giữa hai nút, có hướng | `(p)-[r]->(pr)` |
| Kiểu quan hệ (type) | Ý nghĩa của kết nối | `[r:WORKS_ON]` |
| Thuộc tính quan hệ | Thông tin của chính kết nối | `[r:WORKS_ON {role: 'backend'}]` |
| Biến (variable) | Tên dùng trong phạm vi câu truy vấn để tham chiếu thành phần | `p`, `pr`, `r` |

Cú pháp tổng quát:

~~~cypher
CREATE (n:Label {key1: value1, key2: value2})
RETURN n;
~~~

- `CREATE` thêm dữ liệu theo mẫu được viết sau lệnh.
- Dấu ngoặc tròn `(...)` biểu diễn nút; dấu ngoặc vuông `[...]` biểu diễn quan hệ.
- `:Person` là nhãn của nút; `:WORKS_ON` là kiểu quan hệ.
- `n` là **biến trong câu truy vấn**, không phải ID lâu dài của nút.
- `RETURN` giúp quan sát dữ liệu vừa tạo; không bắt buộc nếu chỉ cần ghi dữ liệu.

**Điểm cần nhớ:** `CREATE` luôn yêu cầu tạo thành phần mới theo mẫu. Nó không tự tìm một nút hoặc quan hệ có cùng thuộc tính để sử dụng lại.

## 3. Tạo nút và thuộc tính

### 3.1. Tạo nút đơn giản

~~~cypher
CREATE (p:Person {
  personId: 'P-101',
  name: 'Nguyễn An',
  age: 27,
  active: true
})
RETURN p;
~~~

Truy vấn tạo **một nút** mang nhãn `Person` và bốn thuộc tính. Giá trị `personId` ở đây là **khóa nghiệp vụ do ứng dụng định nghĩa**, không phải ID nội bộ của Neo4j.

Có thể tạo nút không có thuộc tính hoặc có nhiều nhãn:

~~~cypher
CREATE (draft:Document)
RETURN draft;
~~~

~~~cypher
CREATE (engineer:Person:Employee {
  personId: 'P-102',
  name: 'Trần Bình',
  team: 'Platform'
})
RETURN engineer;
~~~

Một nút có thể mang nhiều nhãn (ví dụ `Person` và `Employee`), giúp phân loại theo nhiều góc nhìn. Nên đặt nhãn, kiểu quan hệ và tên thuộc tính có quy ước thống nhất vì Cypher phân biệt chữ hoa, chữ thường.

### 3.2. Kiểu giá trị thuộc tính

Các ví dụ thường gặp:

~~~cypher
CREATE (p:Product {
  productId: 'SP-001',          // chuỗi
  price: 125000.50,            // số thực
  quantity: 12,                // số nguyên
  available: true,             // boolean
  tags: ['database', 'graph'],  // danh sách giá trị đơn giản
  releasedOn: date('2025-07-01'),
  createdAt: datetime()
})
RETURN p;
~~~

Neo4j hỗ trợ các giá trị thuộc tính như chuỗi, số, boolean, kiểu thời gian, điểm không gian và danh sách các giá trị đơn giản phù hợp. **Không thể lưu một map lồng nhau trực tiếp làm một thuộc tính nút/quan hệ**. Ví dụ `address: {city: 'Hà Nội'}` không phải thuộc tính hợp lệ để lưu nguyên map. Thay vào đó, dùng `city: 'Hà Nội'` hoặc mô hình hóa địa chỉ thành nút riêng khi có quan hệ cần truy vấn.

`null` không biểu diễn một thuộc tính có giá trị “rỗng” được lưu trên nút: thuộc tính có giá trị `null` được xem như không tồn tại. Với trường bắt buộc, cần kiểm tra đầu vào và cân nhắc constraint thích hợp.

### 3.3. Tạo nút từ tham số

Trong ứng dụng, không ghép trực tiếp dữ liệu người dùng vào chuỗi Cypher. Truyền giá trị qua tham số bắt đầu bằng `$`:

~~~cypher
CREATE (p:Person {
  personId: $personId,
  name: $name,
  age: $age
})
RETURN p.personId AS personId, p.name AS name;
~~~

Ví dụ bộ tham số do ứng dụng gửi:

~~~json
{
  "personId": "P-103",
  "name": "Lê Chi",
  "age": 25
}
~~~

Tham số giúp truy vấn dễ tái sử dụng, xử lý chuỗi có dấu nháy đúng cách và giảm nguy cơ chèn mã Cypher qua giá trị nhập. Tham số trong ví dụ dùng cho **giá trị thuộc tính**; nhãn và kiểu quan hệ động có quy tắc riêng tùy phiên bản Cypher, nên ưu tiên tên cố định khi mới học.

### 3.4. Kết hợp `CREATE` và `SET`

Bạn có thể khai báo phần lớn thuộc tính ngay trong mẫu `CREATE`; `SET` hữu ích khi cần bổ sung hay tính toán thuộc tính sau khi nút đã được đặt vào biến:

~~~cypher
CREATE (p:Person {personId: 'P-104'})
SET p.name = 'Phạm Dung',
    p.createdAt = datetime(),
    p.active = true
RETURN p;
~~~

`CREATE` tạo nút; `SET` gán hoặc thay đổi thuộc tính trên nút/quan hệ đã được tham chiếu. Với bài toán cập nhật dữ liệu **đang tồn tại**, thường dùng `MATCH ... SET` thay vì tạo nút mới.

## 4. Tạo quan hệ giữa các nút

### 4.1. Tạo hai nút mới và quan hệ cùng lúc

~~~cypher
CREATE
  (an:Person {personId: 'P-201', name: 'An'}),
  (binh:Person {personId: 'P-202', name: 'Bình'}),
  (an)-[r:KNOWS {since: 2024, context: 'cùng dự án'}]->(binh)
RETURN an.name AS fromPerson, type(r) AS relationshipType,
       r.since AS since, binh.name AS toPerson;
~~~

Kết quả về mặt cấu trúc:

~~~text
(:Person {personId: 'P-201', name: 'An'})
         -[:KNOWS {since: 2024, context: 'cùng dự án'}]->
(:Person {personId: 'P-202', name: 'Bình'})
~~~

Trong cùng câu truy vấn, biến `an` và `binh` được sử dụng lại để chỉ đúng các nút vừa tạo; `r` tham chiếu quan hệ mới. `since` là **thuộc tính của quan hệ**, vì nó mô tả thời điểm hai người quen nhau, không phải thuộc tính cố hữu của một người.

Quan hệ trong Neo4j có **hướng**. `(an)-[:KNOWS]->(binh)` có nút nguồn là `an` và nút đích là `binh`. Khi đọc dữ liệu, Cypher có thể khớp mẫu không chỉ định hướng, nhưng lúc tạo nên biểu diễn đúng chiều nghiệp vụ. Mỗi quan hệ có đúng một kiểu, ví dụ `KNOWS` hoặc `WORKS_ON`.

### 4.2. Tạo quan hệ giữa **hai nút đã tồn tại**

Đây là thao tác thường gặp trong ứng dụng. Giả sử đã có người với `personId = 'P-201'` và người với `personId = 'P-202'`:

~~~cypher
MATCH (a:Person {personId: 'P-201'})
MATCH (b:Person {personId: 'P-202'})
CREATE (a)-[r:COLLABORATES_WITH {
  project: 'Dự án đồ thị',
  startedOn: date('2025-04-01')
}]->(b)
RETURN a.name AS fromPerson, type(r) AS relation, b.name AS toPerson;
~~~

**Trình tự thực thi:** `MATCH` tìm và ràng buộc biến `a`, `b` vào các nút đã có; `CREATE` chỉ tạo quan hệ mới giữa chúng. Truy vấn không tạo thêm hai nút `Person`.

Nếu một trong hai `MATCH` không tìm thấy nút nào, không có dòng dữ liệu để truyền vào `CREATE`, nên **không có quan hệ được tạo**. Nếu mỗi `MATCH` khớp nhiều nút, truy vấn có thể tạo nhiều quan hệ tương ứng với các cặp khớp; khóa nghiệp vụ duy nhất giúp tránh sai sót này.

**Bẫy dễ gặp:** Viết riêng `CREATE (a:Person {personId: 'P-201'})` sẽ tạo một nút mới, ngay cả khi đã có nút `Person` cùng `personId` (trừ khi constraint làm câu lệnh thất bại). Muốn sử dụng nút đã có, hãy tìm nó bằng `MATCH` trước.

### 4.3. Quan hệ không tồn tại độc lập

Không thể tạo một quan hệ “đứng riêng” mà không có hai đầu mút. Một mẫu hợp lệ phải chứa nút nguồn và nút đích:

~~~cypher
CREATE (a:Author {authorId: 'A-301', name: 'Mai'})
       -[r:WROTE {year: 2026}]->
       (b:Book {bookId: 'B-301', title: 'Nhập môn Graph'})
RETURN a.name AS author, r.year AS year, b.title AS book;
~~~

Ở đây hai nút và quan hệ được tạo cùng một mẫu. Các tên biến `a`, `r`, `b` chỉ dùng trong phạm vi truy vấn.

## 5. Tạo nhiều nút và nhiều quan hệ trong một câu lệnh

`CREATE` chấp nhận nhiều mẫu phân tách bằng dấu phẩy. Ví dụ một nhóm cùng tham gia dự án:

~~~cypher
CREATE
  (lan:Person {personId: 'P-401', name: 'Lan'}),
  (minh:Person {personId: 'P-402', name: 'Minh'}),
  (project:Project {
    projectId: 'PR-401',
    title: 'Kho tri thức Neo4j'
  }),
  (lan)-[:KNOWS {since: 2023}]->(minh),
  (lan)-[:WORKS_ON {role: 'Backend'}]->(project),
  (minh)-[:WORKS_ON {role: 'Data Engineer'}]->(project)
RETURN lan.name AS personA, minh.name AS personB,
       project.title AS projectName;
~~~

Tất cả thành phần được khai báo trong câu truy vấn này tham chiếu tới cùng biến `project`, vì vậy hai quan hệ `WORKS_ON` trỏ về cùng một nút dự án. Cách này phù hợp khi **toàn bộ đối tượng đều cần tạo mới**.

Nếu dự án đã tồn tại, cần `MATCH (project:Project {projectId: ...})` trước khi `CREATE` quan hệ; nếu tạo lại `project` mỗi lần sẽ sinh dự án trùng.

## 6. Tạo hàng loạt với `UNWIND`

`UNWIND` biến từng phần tử của danh sách thành một dòng để câu lệnh sau xử lý. Với tham số `$people` là danh sách các map:

~~~json
{
  "people": [
    {"personId": "P-501", "name": "Hà"},
    {"personId": "P-502", "name": "Khoa"},
    {"personId": "P-503", "name": "Linh"}
  ]
}
~~~

Truy vấn tạo ba nút:

~~~cypher
UNWIND $people AS item
CREATE (p:Person {
  personId: item.personId,
  name: item.name
})
RETURN count(p) AS createdCount;
~~~

Nếu đầu vào chứa ba phần tử hợp lệ và không vi phạm constraint, `createdCount` là `3`. `UNWIND` hữu ích cho nhập dữ liệu từ ứng dụng hoặc dữ liệu đã được xử lý. Với tập dữ liệu rất lớn, nên chia lô và kiểm soát kích thước giao dịch theo khả năng hệ thống; việc chạy lại cùng lô với `CREATE` vẫn có nguy cơ tạo bản ghi trùng.

## 7. Tránh dữ liệu trùng và bảo đảm toàn vẹn

### 7.1. `CREATE` khác gì `MERGE`?

| Lệnh | Hành vi cốt lõi | Khi nào dùng |
|---|---|---|
| `CREATE` | Tạo mới thành phần theo mẫu | Chắc chắn cần bản ghi/quan hệ mới |
| `MATCH` | Tìm thành phần đã có, không tạo mới | Nối các nút hiện hữu hoặc chuẩn bị cập nhật |
| `MERGE` | Tìm mẫu phù hợp; nếu không có thì tạo | Muốn “có đúng mẫu này” theo logic tìm hoặc tạo |
| `SET` | Gán/thay đổi nhãn hoặc thuộc tính trên thành phần đã tham chiếu | Ghi thêm hoặc cập nhật thông tin |

Ví dụ, chạy **hai lần** câu lệnh sau trên cơ sở dữ liệu không có ràng buộc sẽ tạo **hai nút khác nhau** cùng `personId`:

~~~cypher
CREATE (:Person {personId: 'P-601', name: 'Nga'});
~~~

Để ngăn hai nút `Person` trùng khóa nghiệp vụ `personId`, có thể tạo ràng buộc duy nhất trước khi nhập dữ liệu:

~~~cypher
CREATE CONSTRAINT person_personId_unique IF NOT EXISTS
FOR (p:Person)
REQUIRE p.personId IS UNIQUE;
~~~

Lúc này, tạo nút có cùng `personId` với nút đã tồn tại sẽ bị từ chối vì vi phạm constraint. **Constraint không biến `CREATE` thành cập nhật hay “tìm hoặc tạo”**: câu truy vấn vẫn là yêu cầu tạo mới và có thể báo lỗi. Trên dữ liệu đã có trùng, việc tạo constraint cũng có thể thất bại; cần xử lý dữ liệu trước.

Khi thực sự cần ngữ nghĩa tìm hoặc tạo, xem `MERGE`:

~~~cypher
MERGE (p:Person {personId: $personId})
ON CREATE SET p.name = $name, p.createdAt = datetime()
RETURN p;
~~~

Ở ví dụ này, `personId` là khóa để nhận diện người; `ON CREATE SET` chỉ chạy khi nút được tạo mới. Cần thiết kế khóa nghiệp vụ và constraint phù hợp vì `MERGE` một mình không thay thế mọi bảo đảm về tính duy nhất khi có ghi đồng thời.

### 7.2. Lưu ý khi tạo quan hệ

Hai nút duy nhất **không đồng nghĩa quan hệ giữa chúng là duy nhất**:

~~~cypher
MATCH (a:Person {personId: 'P-201'})
MATCH (b:Person {personId: 'P-202'})
CREATE (a)-[:FOLLOWS]->(b);
~~~

Chạy lại truy vấn có thể tạo thêm một quan hệ `FOLLOWS` song song giữa cùng hai nút. Nếu quy tắc nghiệp vụ chỉ cho phép một quan hệ loại này, hãy cân nhắc `MERGE (a)-[:FOLLOWS]->(b)` sau khi đã xác định đúng hai nút và thiết kế cơ chế toàn vẹn thích hợp.

### 7.3. Một số lỗi phổ biến

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Chạy lại lệnh làm tăng số nút | `CREATE` luôn tạo mới | Dùng khóa nghiệp vụ, constraint; cân nhắc `MERGE` |
| Có hai nút người cùng tên | Tên người không bảo đảm duy nhất | Định danh bằng `personId`, không dựa vào `name` |
| Quan hệ trỏ đến nút “bản sao” | Tạo lại nút đầu mút bằng `CREATE` | `MATCH` các đầu mút đã tồn tại rồi mới `CREATE` quan hệ |
| Không tạo được quan hệ | `MATCH` trước đó không trả dòng nào | Kiểm tra nhãn, giá trị khóa, thứ tự truy vấn |
| Tạo nhiều quan hệ ngoài dự kiến | `MATCH` trả nhiều kết quả | Kiểm tra khóa duy nhất và số lượng nút được khớp |
| Lỗi khi lưu thuộc tính | Cố gắng lưu map lồng nhau hoặc kiểu không hợp lệ | Làm phẳng thuộc tính hoặc tách thực thể thành nút |
| Lỗi vi phạm constraint | Định danh đã tồn tại | Kiểm tra logic tạo mới và yêu cầu nghiệp vụ |

## 8. Ví dụ tích hợp: nhân viên tham gia dự án

Ví dụ dưới đây thể hiện quy trình thêm dữ liệu theo property graph: định danh nút bằng khóa nghiệp vụ, tạo nhân viên và dự án, tạo quan hệ mang thuộc tính vai trò, rồi truy vấn lại. Các lệnh thực thi theo thứ tự; nên chạy trong môi trường học tập với dữ liệu mẫu riêng.

**Bước 1 — Tạo constraint cho khóa nghiệp vụ.**

~~~cypher
CREATE CONSTRAINT demo_employee_id_unique IF NOT EXISTS
FOR (e:Employee) REQUIRE e.employeeId IS UNIQUE;
~~~

~~~cypher
CREATE CONSTRAINT demo_project_id_unique IF NOT EXISTS
FOR (p:Project) REQUIRE p.projectId IS UNIQUE;
~~~

**Bước 2 — Tạo hai nhân viên, một dự án và quan hệ.**

~~~cypher
CREATE
  (ha:Employee {
    employeeId: 'E-DEMO-01',
    name: 'Hà',
    department: 'Engineering'
  }),
  (khoa:Employee {
    employeeId: 'E-DEMO-02',
    name: 'Khoa',
    department: 'Data'
  }),
  (project:Project {
    projectId: 'PR-DEMO-01',
    title: 'Phân tích quan hệ khách hàng'
  }),
  (ha)-[:WORKS_ON {
    role: 'Backend Developer',
    startedOn: date('2026-01-10')
  }]->(project),
  (khoa)-[:WORKS_ON {
    role: 'Data Engineer',
    startedOn: date('2026-02-01')
  }]->(project)
RETURN ha.employeeId AS employeeA, khoa.employeeId AS employeeB,
       project.projectId AS projectId;
~~~

**Bước 3 — Kiểm tra các quan hệ vừa tạo.**

~~~cypher
MATCH (e:Employee)-[r:WORKS_ON]->(p:Project)
WHERE p.projectId = 'PR-DEMO-01'
RETURN e.name AS employee,
       r.role AS role,
       r.startedOn AS startDate,
       p.title AS project
ORDER BY employee;
~~~

Kết quả mong đợi có **hai dòng**, một dòng cho Hà và một dòng cho Khoa, cùng trỏ về dự án `PR-DEMO-01`. Truy vấn kiểm tra không làm thay đổi đồ thị.

**Bước 4 — Thêm một người đã tồn tại vào dự án đã tồn tại.**

~~~cypher
MATCH (e:Employee {employeeId: 'E-DEMO-01'})
MATCH (p:Project {projectId: 'PR-DEMO-01'})
CREATE (e)-[:REVIEWS {frequency: 'weekly'}]->(p)
RETURN e.name AS reviewer, p.title AS project;
~~~

Bước 4 chỉ tạo **một quan hệ mới**; không tạo thêm nhân viên hay dự án. Nếu chạy lại bước 2, constraint sẽ ngăn tạo lại các nút có cùng khóa và câu lệnh có thể thất bại. Nếu chạy lại bước 4, quan hệ `REVIEWS` có thể bị tạo trùng.

## 9. Dùng `CREATE` qua Neo4j Java Driver

Trong ứng dụng Java, hãy truyền tham số và quản lý giao dịch bằng Driver. Ví dụ phương thức thêm người dưới đây giả định ứng dụng đã cấu hình và quản lý vòng đời của đối tượng `Driver`:

~~~java
import java.util.Map;
import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;

public final class PersonRepository {
    private final Driver driver;

    public PersonRepository(Driver driver) {
        this.driver = driver;
    }

    public String createPerson(String personId, String name) {
        String cypher = """
                CREATE (p:Person {personId: $personId, name: $name})
                RETURN p.personId AS id
                """;

        try (Session session = driver.session()) {
            return session.executeWrite(tx ->
                    tx.run(cypher, Map.of(
                            "personId", personId,
                            "name", name
                    )).single().get("id").asString()
            );
        }
    }
}
~~~

- `executeWrite` thực thi thao tác ghi qua giao dịch do Driver quản lý.
- `Map.of(...)` truyền tham số; mã Java không ghép chuỗi đầu vào thành câu lệnh Cypher.
- `single()` phù hợp khi câu lệnh dự kiến trả đúng một dòng.
- Trong ứng dụng thực tế, cần xác định database, chính sách lỗi, ràng buộc duy nhất và yêu cầu tái thực thi. Với Spring Data Neo4j, cách ánh xạ entity và lưu repository là lớp trừu tượng cao hơn; việc hiểu mẫu `CREATE` vẫn giúp đọc các truy vấn Cypher tùy biến.

## 10. Thực hành và tự kiểm tra

**Bài tập 1 — Nút và thuộc tính.** Viết câu lệnh tạo một nút `Course` có `courseId`, `title`, `durationHours` và `published`; trả về `courseId` và `title`.

<details>
<summary>Đáp án tham khảo</summary>

~~~cypher
CREATE (c:Course {
  courseId: 'C-001',
  title: 'Cypher căn bản',
  durationHours: 12,
  published: true
})
RETURN c.courseId AS courseId, c.title AS title;
~~~

</details>

**Bài tập 2 — Quan hệ có thuộc tính.** Giả sử đã tồn tại người có `personId = 'P-101'` và khóa học có `courseId = 'C-001'`. Hãy tạo quan hệ `ENROLLED_IN` mang `enrolledOn` là ngày hiện tại, không tạo lại hai nút.

<details>
<summary>Đáp án tham khảo</summary>

~~~cypher
MATCH (p:Person {personId: 'P-101'})
MATCH (c:Course {courseId: 'C-001'})
CREATE (p)-[:ENROLLED_IN {enrolledOn: date()}]->(c)
RETURN p.personId AS personId, c.courseId AS courseId;
~~~

</details>

**Bài tập 3 — Phân tích hành vi.** Sau khi chạy hai lần truy vấn sau, sẽ có bao nhiêu nút `:Category {name: 'Graph'}`, giả sử ban đầu chưa có dữ liệu tương ứng và chưa đặt constraint?

~~~cypher
CREATE (:Category {name: 'Graph'});
~~~

Đáp án: **Hai nút**. `CREATE` không kiểm tra trùng giá trị. Nếu định danh `Category` bằng tên, hãy cân nhắc khóa duy nhất và `MERGE`; nếu tên có thể đổi hoặc trùng, nên có `categoryId` riêng.

## 11. Ghi nhớ

- `CREATE` tạo nút mới, quan hệ mới và các thuộc tính khai báo trong mẫu Cypher.
- Nút có nhãn và thuộc tính; quan hệ phải nối hai nút, có hướng, có kiểu và có thể có thuộc tính.
- **Tạo mới toàn bộ đồ thị nhỏ:** `CREATE (a:...)-[:REL]->(b:...)`.
- **Nối dữ liệu đã tồn tại:** `MATCH` các nút đầu mút, rồi `CREATE` quan hệ.
- Dùng tham số `$...` và `UNWIND` cho dữ liệu đến từ ứng dụng hoặc tạo hàng loạt.
- `CREATE` có thể tạo trùng khi chạy lại; constraint bảo vệ khóa nghiệp vụ, còn `MERGE` phục vụ nhu cầu tìm hoặc tạo theo mẫu.
- Khi tối ưu và vận hành Neo4j, kiểm tra mô hình, truy vấn và ràng buộc trước khi ghi khối lượng lớn. `EXPLAIN` có thể giúp xem kế hoạch truy vấn; `PROFILE` thực thi truy vấn nên cần thận trọng với câu lệnh ghi.

**Tiếp nối:** Sau `CREATE`, học `MATCH` để tìm nút/quan hệ, `SET` và `REMOVE` để chỉnh sửa thuộc tính/nhãn, `MERGE` cho trường hợp tìm hoặc tạo, và `DELETE`/`DETACH DELETE` cho xóa dữ liệu theo quan hệ.
