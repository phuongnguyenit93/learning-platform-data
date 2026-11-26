# Nhiều nhãn trên một nút và ý nghĩa phân loại thực thể

## 1. Mục tiêu học tập

Neo4j lưu trữ dữ liệu liên kết theo **property graph**: nút (*node*) biểu diễn thực thể, quan hệ (*relationship*) diễn đạt liên kết giữa các nút và thuộc tính (*property*) mô tả dữ kiện. Bên cạnh đó, **nhãn** (*label*) phân loại nút để ta có thể tìm kiếm, đặt quy tắc dữ liệu và tổ chức mô hình.

Trong chương **Thành phần đồ thị** của module `DATABASE_ENGINE_GRAPH_NEO4J`, bài này đi sâu vào một điểm quan trọng: **một nút có thể mang nhiều nhãn cùng lúc**. Đây là cách Neo4j biểu diễn một thực thể thuộc nhiều nhóm hoặc đảm nhiệm nhiều vai trò, trong khi vẫn giữ một nút duy nhất để kết nối bằng Cypher.

Sau bài học, bạn có thể:

- Giải thích vì sao một nút có thể có nhiều nhãn và **không cần tạo bản sao** cho từng vai trò.
- Phân biệt **node**, **label**, **property** và **relationship** khi phân loại thực thể.
- Viết Cypher để tạo, đọc, thêm, bỏ và kết hợp các nhãn trên cùng một nút.
- Hiểu rằng mẫu có nhiều nhãn như `(p:Person:Employee)` yêu cầu nút **đồng thời có tất cả** những nhãn được nêu.
- Thiết kế phân loại phù hợp với vai trò nghiệp vụ, truy vấn, index, constraint và cách ánh xạ dữ liệu trong Java/Spring Data Neo4j.
- Nhận ra các lỗi thường gặp: coi nhãn là kế thừa tự động, tạo một nút cho mỗi nhãn, lạm dụng nhãn để chứa giá trị thuộc tính hoặc tạo nút trùng khi `MERGE`.

## 2. Nhãn là gì và vì sao một nút có nhiều nhãn?

**Label** là tên phân loại gắn trực tiếp với nút. Một nút có thể có **không, một hoặc nhiều nhãn**; các nhãn trên cùng nút tạo thành một tập hợp, không phải một danh sách có thứ tự mang ý nghĩa nghiệp vụ.

Ví dụ trong hệ thống đào tạo nội bộ, Nguyễn An vừa là một con người, vừa là nhân viên, đồng thời có nhiệm vụ hướng dẫn người mới:

```text
              CÙNG MỘT NÚT
   ┌─────────────────────────────────┐
   │ :Person :Employee :Mentor       │
   │ personId: "P001"                │
   │ fullName: "Nguyễn An"           │
   │ department: "Engineering"       │
   └─────────────────────────────────┘
```

Mẫu Cypher:

```cypher
(an:Person:Employee:Mentor {
  personId: 'P001',
  fullName: 'Nguyễn An',
  department: 'Engineering'
})
```

Ở đây:

| Thành phần | Vai trò | Ví dụ |
| --- | --- | --- |
| **Node** | Đại diện cho một thực thể có danh tính riêng | Một nút duy nhất biểu diễn Nguyễn An |
| **Labels** | Những nhóm/vai trò mà thực thể đang thuộc về | `Person`, `Employee`, `Mentor` |
| **Properties** | Các giá trị mô tả nút | `personId`, `fullName`, `department` |
| **Relationships** | Những liên kết của nút đến nút khác | `(an)-[:WORKS_AT]->(company)`, `(an)-[:MENTORS]->(junior)` |

Nếu mô hình tạo riêng một nút `:Person`, một nút `:Employee` và một nút `:Mentor` cho **cùng một Nguyễn An** chỉ để biểu diễn ba vai trò, ứng dụng sẽ phải đồng bộ tên, mã, trạng thái và các quan hệ giữa những bản sao đó. Gắn nhiều nhãn lên **một nút** thường là lựa chọn đơn giản hơn khi cả ba nhãn thực sự mô tả cùng một thực thể.

**Điểm cốt lõi:** Có nhiều nhãn **không** có nghĩa là có nhiều nút. Mỗi nút vẫn là một thực thể duy nhất, có một tập property và các relationship của riêng nó.

## 3. Cú pháp Cypher cho nhiều nhãn

### 3.1. Tạo một nút có nhiều nhãn

Trong database thực hành, chạy lệnh sau một lần:

```cypher
CREATE (p:Person:Employee:Mentor {
  personId: 'ML-P001',
  fullName: 'Nguyễn An',
  department: 'Engineering',
  active: true
})
RETURN p;
```

Dấu `:` phân tách các nhãn gắn với **cùng biến `p`**. Cú pháp `:Person:Employee:Mentor` **không** tạo ba nút.

Đọc lại thông tin:

```cypher
MATCH (p:Person {personId: 'ML-P001'})
RETURN p.personId AS personId,
       p.fullName AS fullName,
       labels(p) AS labels,
       properties(p) AS properties;
```

Hàm `labels(p)` trả về danh sách các nhãn hiện tại. Danh sách có thể chứa `Person`, `Employee`, `Mentor`; **không nên dựa vào thứ tự nhãn** khi kiểm tra kết quả.

### 3.2. Chỉ định nhiều nhãn trong MATCH

```cypher
MATCH (p:Person:Employee)
RETURN p.personId AS id, p.fullName AS name;
```

Truy vấn này tìm các nút có **cả nhãn `Person` lẫn nhãn `Employee`**. Nó không có nghĩa “Person **hoặc** Employee”.

Nói cách khác:

```text
MATCH (p:Person)             → Tất cả nút mang nhãn Person
MATCH (p:Employee)           → Tất cả nút mang nhãn Employee
MATCH (p:Person:Employee)    → Giao của hai nhóm: có cả hai nhãn
```

Một nút `:Person:Employee:Mentor` thỏa mãn cả ba mẫu trên. Một nút chỉ mang `:Person` không thỏa mãn `(p:Person:Employee)`.

### 3.3. Thêm nhãn vào nút đã tồn tại

Giả sử người này được giao thêm vai trò quản lý:

```cypher
MATCH (p:Person {personId: 'ML-P001'})
SET p:Manager
RETURN labels(p) AS labels;
```

`SET p:Manager` gắn nhãn `Manager` vào nút `p` hiện có; các nhãn `Person`, `Employee`, `Mentor` và các property vẫn được giữ.

Có thể thêm nhiều nhãn trong một câu lệnh:

```cypher
MATCH (p:Person {personId: 'ML-P001'})
SET p:Trainer:Reviewer
RETURN labels(p) AS labels;
```

Nếu một nhãn đã tồn tại trên nút, việc gắn lại cùng nhãn không tạo thêm một “bản sao” nhãn đó.

### 3.4. Bỏ một hoặc nhiều nhãn

Khi Nguyễn An không còn làm quản lý:

```cypher
MATCH (p:Person {personId: 'ML-P001'})
REMOVE p:Manager
RETURN labels(p) AS labels,
       p.fullName AS fullName;
```

Lệnh `REMOVE p:Manager` chỉ bỏ nhãn `Manager`; **không xóa nút, thuộc tính hoặc các nhãn khác**. Có thể bỏ nhiều nhãn:

```cypher
MATCH (p:Person {personId: 'ML-P001'})
REMOVE p:Trainer:Reviewer
RETURN labels(p) AS labels;
```

Phân biệt ba thao tác:

| Cú pháp | Tác động |
| --- | --- |
| `SET p:Mentor` | Thêm nhãn `Mentor` vào nút |
| `REMOVE p:Mentor` | Bỏ nhãn `Mentor` khỏi nút |
| `DELETE p` | Xóa **nút**; khi còn relationship, phải xử lý các quan hệ liên quan trước hoặc dùng thao tác xóa có tính đến chúng |

Không nên dùng `DELETE` khi chỉ muốn thay đổi phân loại.

## 4. Ý nghĩa của nhiều nhãn: một thực thể, nhiều góc nhìn

Hãy xét ba cách sử dụng nhãn thường gặp trong mô hình hóa.

### 4.1. Loại cơ bản và vai trò chuyên biệt

```text
(:Person:Employee)
(:Person:Customer)
(:Person:Employee:Customer)
```

Ba mẫu trên đều có thể hợp lệ. Một người vừa là nhân viên vừa là khách hàng có thể dùng **một nút** mang cả ba nhãn. Truy vấn `MATCH (p:Customer)` sẽ tìm được người đó; truy vấn `MATCH (p:Employee)` cũng tìm được cùng nút đó.

Tuy nhiên, **không tự động có quan hệ kế thừa** giữa các nhãn. Neo4j không suy ra rằng “đã là `Employee` thì nhất định là `Person`”. Chỉ các nhãn **thực sự được gắn** mới xuất hiện trong `labels(p)` và được khớp bởi mẫu truy vấn.

Ví dụ:

```cypher
CREATE (e:Employee {
  personId: 'ML-E001',
  employeeId: 'ML-E001',
  fullName: 'Bình'
})
RETURN labels(e) AS labels;
```

Nút trên chỉ có nhãn `Employee`. Nó sẽ **không** được trả về bởi `MATCH (p:Person:Employee)` trừ khi ta chủ động thêm nhãn `Person`:

```cypher
MATCH (e:Employee {employeeId: 'ML-E001'})
SET e:Person
RETURN labels(e) AS labels;
```

Nhãn có thể giúp biểu diễn ý tưởng “vai trò chuyên biệt thuộc loại cơ bản”, nhưng việc duy trì quy tắc này là trách nhiệm của thiết kế dữ liệu, câu lệnh ghi và quy trình nhập dữ liệu.

### 4.2. Một thực thể tham gia nhiều ngữ cảnh nghiệp vụ

Trong nền tảng giáo dục, một người có thể là `:User`, `:Learner` và `:Instructor` cùng lúc:

```cypher
CREATE (u:User:Learner:Instructor {
  userId: 'ML-U001',
  displayName: 'Chi'
})
RETURN u;
```

Khi truy vấn màn hình học tập, ta dùng `MATCH (u:Learner)`. Khi hiển thị danh sách giảng viên, ta dùng `MATCH (u:Instructor)`. Cả hai truy vấn có thể trỏ về **cùng một `userId`**.

Cách này phù hợp nếu dữ liệu thực sự có chung một danh tính và vòng đời. Nếu “giảng viên” là một hợp đồng độc lập có nhiều trạng thái, ngày bắt đầu, ngày kết thúc hoặc liên kết riêng với nhiều tổ chức, có thể cần thêm nút `:InstructorAssignment` và các relationship; một nhãn đơn thuần có thể chưa đủ.

### 4.3. Phân loại để phục vụ truy vấn và quy tắc dữ liệu

Nhãn thường giúp giới hạn phạm vi truy vấn:

```cypher
MATCH (p:Person:Mentor)
RETURN p.fullName AS mentorName
ORDER BY mentorName;
```

Nhãn cũng được sử dụng trong định nghĩa **index** và **constraint**, chẳng hạn yêu cầu mọi mã `personId` xuất hiện tối đa một lần trong nhóm `Person`. Điều này giúp tập dữ liệu linh hoạt vẫn có các quy tắc toàn vẹn ở những điểm cần thiết.

## 5. Nhiều nhãn là phép giao nhóm, không phải phép hợp

Đây là điểm quan trọng nhất khi đọc một mẫu nhiều nhãn.

Giả sử database có bốn nút:

| Nút | Nhãn |
| --- | --- |
| An | `Person`, `Employee`, `Mentor` |
| Bình | `Person`, `Employee` |
| Chi | `Person`, `Customer` |
| Dũng | `Organization` |

Kết quả mong đợi:

| Truy vấn | Nút trả về |
| --- | --- |
| `MATCH (n:Person)` | An, Bình, Chi |
| `MATCH (n:Employee)` | An, Bình |
| `MATCH (n:Person:Employee)` | An, Bình |
| `MATCH (n:Person:Employee:Mentor)` | An |
| `MATCH (n:Organization)` | Dũng |

Để tìm **Person hoặc Organization**, tránh hiểu nhầm cú pháp nhiều nhãn là OR. Một cách viết tương thích và dễ hiểu là:

```cypher
MATCH (n)
WHERE 'Person' IN labels(n)
   OR 'Organization' IN labels(n)
RETURN n;
```

Đây là ví dụ minh họa ngữ nghĩa OR, **không mặc định là cách tối ưu cho đồ thị lớn**, vì mẫu `MATCH (n)` không giới hạn nút theo một nhãn ban đầu. Trong dữ liệu lớn, có thể dùng các nhánh truy vấn theo từng label rồi kết hợp kết quả, hoặc cú pháp biểu thức nhãn theo phiên bản Cypher đang sử dụng.

### 5.1. Dùng WHERE để diễn đạt điều kiện nhãn

```cypher
MATCH (p:Person)
WHERE p:Employee
RETURN p.personId, p.fullName;
```

Về điều kiện nhãn, cách này tương đương mẫu:

```cypher
MATCH (p:Person:Employee)
RETURN p.personId, p.fullName;
```

Nếu cần kiểm tra danh sách nhãn bằng hàm:

```cypher
MATCH (p:Person)
WHERE 'Employee' IN labels(p)
RETURN p.personId AS id;
```

`labels(p)` phù hợp khi cần **kiểm tra hoặc hiển thị các nhãn thực tế**; khi đã biết các nhãn cần khớp, ưu tiên mẫu có label rõ ràng để truy vấn dễ đọc và giúp bộ tối ưu thấy điều kiện phân loại trực tiếp.

### 5.2. Đếm nút theo nhãn và giao nhãn

```cypher
MATCH (p:Person)
RETURN count(p) AS totalPeople;

MATCH (p:Person:Employee)
RETURN count(p) AS peopleWhoAreEmployees;

MATCH (p:Person:Employee:Mentor)
RETURN count(p) AS employeesWhoAreMentors;
```

Vì các nhóm có thể **chồng lấp**, tổng số nút `Person` và số nút `Employee` không đại diện cho hai tập rời nhau. Đừng cộng chúng để tính “tổng số người” khi nhiều nút mang cả hai nhãn.

## 6. Khi nào nên dùng label, property hay relationship?

Một thực thể có thể được mô tả bằng cả ba cơ chế; chọn cơ chế dựa trên **bản chất thông tin** và nhu cầu truy vấn.

| Nhu cầu | Cách biểu diễn thường phù hợp | Ví dụ |
| --- | --- | --- |
| Phân loại thực thể thành nhóm/vai trò có ý nghĩa | **Label** | `:Person:Employee`, `:User:Instructor` |
| Lưu một giá trị mô tả, có thể thay đổi | **Property** | `department: 'Engineering'`, `status: 'ACTIVE'` |
| Nối thực thể này với thực thể khác | **Relationship** | `(p)-[:WORKS_AT]->(c)` |
| Mô hình hóa bản ghi có danh tính và vòng đời riêng | **Node riêng + relationship** | `(:Person)-[:HAS]->(:EmploymentContract)` |

### 6.1. Label so với thuộc tính trạng thái

Ví dụ có hai cách biểu diễn:

```cypher
(:Employee:Active {employeeId: 'E001'})
(:Employee {employeeId: 'E001', status: 'ACTIVE'})
```

Cả hai đều có thể có lý do sử dụng, nhưng không nên tạo nhãn cho **mọi giá trị** như `:Status_ACTIVE`, `:Status_PENDING`, `:Status_SUSPENDED` chỉ vì một trường có tập giá trị. Khi trạng thái thường xuyên thay đổi hoặc cần lọc/so sánh giá trị, một **property `status`** thường đơn giản hơn.

Ngược lại, nếu một nhóm có ý nghĩa ổn định, được nhiều truy vấn sử dụng và có các constraint/index hoặc chính sách mô hình riêng, **label** có thể phù hợp.

**Câu hỏi thực tế:** “Employee” là một **loại/vai trò** của người trong đồ thị, trong khi “Engineering” có thể chỉ là **giá trị phòng ban**. Không nhất thiết tạo các nhãn `:Engineering`, `:Finance` cho từng phòng, nhất là khi cần nhiều thông tin về phòng ban thì nên mô hình hóa nút `:Department`.

### 6.2. Label so với quan hệ giữa thực thể

Gắn nhãn `:Mentor` cho một người **không chỉ ra người đó hướng dẫn ai**. Nếu nghiệp vụ cần truy vấn “ai hướng dẫn ai”, phải lưu relationship:

```cypher
MATCH (mentor:Person:Mentor {personId: 'ML-P001'})
MATCH (learner:Person {personId: 'ML-E001'})
CREATE (mentor)-[:MENTORS {startedOn: date()}]->(learner)
RETURN mentor.fullName AS mentorName,
       learner.fullName AS learnerName;
```

Trong câu truy vấn trên, nhãn `Mentor` dùng để phân loại **người hướng dẫn**, còn loại quan hệ `MENTORS` biểu diễn **một liên kết hướng dẫn cụ thể**. Không nên dùng chỉ label để thay thế thông tin có hai đầu mút.

### 6.3. Khi nào cần tách nhiều nút?

Việc có nhiều vai trò **không bắt buộc** phải nhiều nút. Nhưng khi mỗi vai trò có một định danh riêng, dữ liệu nhạy cảm cần tách quyền truy cập, lịch sử thay đổi độc lập hoặc quan hệ phức tạp, mô hình nhiều nút có thể phù hợp hơn.

Ví dụ, một `:Person` có thể có nhiều `:Employment` theo thời gian:

```text
(:Person)
    |
    +--[:HAS_EMPLOYMENT]--> (:Employment {startedOn, endedOn})
    |                                 |
    |                                 +--[:AT_COMPANY]--> (:Company)
    |
    +--[:HAS_EMPLOYMENT]--> (:Employment {startedOn, endedOn})
                                      |
                                      +--[:AT_COMPANY]--> (:Company)
```

Nút `Employment` biểu diễn **một lần làm việc/hợp đồng** có vòng đời riêng; label `Employee` trên `Person` (nếu dùng) chỉ thể hiện một phân loại hiện tại hoặc quy ước nghiệp vụ, không tự lưu lịch sử hợp đồng.

## 7. Quy ước thiết kế và tính nhất quán giữa các nhãn

### 7.1. Chọn một nhãn nền cho thực thể có danh tính

Một cách tổ chức dễ hiểu là:

```text
:Person + :Employee
:Person + :Customer
:Person + :Employee + :Mentor
```

Trong mô hình này, `Person` là nhãn nền, còn `Employee`, `Customer`, `Mentor` mô tả các vai trò. Quy tắc “mọi `Employee` đều có `Person`” là **quy ước của ứng dụng**, không phải quy tắc kế thừa Neo4j tự thi hành.

Khi ghi dữ liệu, hãy làm rõ:

- Vai trò nào được phép cùng tồn tại, vai trò nào loại trừ nhau?
- Vai trò nào là tạm thời, vai trò nào lâu dài?
- Khi bỏ vai trò, giữ hay xóa dữ liệu gắn với vai trò đó?
- Bộ phận nào của ứng dụng có quyền thay đổi nhãn?
- Định danh nào bảo đảm cùng một người không bị tạo thành hai nút?

### 7.2. Tránh số lượng nhãn bùng nổ

**Không nên** tạo nhãn riêng cho từng mã, ngày, người dùng hoặc giá trị bất kỳ:

```text
(:Person_P001)
(:Person_P002)
(:Employee_2025)
(:Customer_HaNoi)
```

Những nhãn này khiến mô hình khó quản lý và thay đổi liên tục theo dữ liệu. Thông thường nên biểu diễn bằng:

```cypher
(:Person:Employee {
  personId: 'P001',
  joinedYear: 2025,
  city: 'Hà Nội'
})
```

Chỉ tạo nhãn cho **nhóm có ý nghĩa mô hình** và được dùng rõ ràng trong truy vấn hoặc quy tắc quản lý.

### 7.3. Nhất quán tên và kiểu chữ

Neo4j phân biệt chữ hoa/chữ thường trong tên nhãn:

```text
:Person     khác :person
:Employee   khác :EMPLOYEE
```

Quy ước phổ biến cho label là danh từ hoặc tên vai trò dạng PascalCase: `Person`, `Employee`, `Instructor`, `Order`. Giữ nhất quán giữa truy vấn Cypher, dữ liệu nhập, mã Java và cấu hình ánh xạ.

## 8. Index, constraint và phạm vi của nhãn

Label tham gia vào việc xác định **tập nút mà index và constraint áp dụng**.

### 8.1. Định danh nghiệp vụ nhất quán trên nhãn nền

Trong ví dụ `Person` là nhãn nền, có thể tạo uniqueness constraint trên `personId`:

```cypher
CREATE CONSTRAINT person_id_unique IF NOT EXISTS
FOR (p:Person)
REQUIRE p.personId IS UNIQUE;
```

Ràng buộc này có ý nghĩa: **không được có hai nút mang nhãn `Person` với cùng giá trị `personId`**. Nó áp dụng cho nút `:Person`, `:Person:Employee` hay `:Person:Customer` vì tất cả đều có nhãn `Person`.

Tuy nhiên:

- Unique constraint **không tự yêu cầu** mọi nút `Person` phải có `personId`. Kiểu constraint bắt buộc tồn tại thuộc tính hoặc node key có điều kiện hỗ trợ riêng theo phiên bản/edition.
- Một nút chỉ có nhãn `Employee` nhưng **không** có `Person` không thuộc phạm vi của constraint `FOR (p:Person)`.
- Uniqueness trên `Employee.employeeId` là một phạm vi khác với uniqueness trên `Person.personId`; cần thiết kế khóa theo cách ứng dụng nhận diện thực thể.

### 8.2. Index cho truy vấn theo vai trò và thuộc tính

Ví dụ thường xuyên tra cứu nhân viên theo `employeeCode`:

```cypher
CREATE INDEX employee_code_idx IF NOT EXISTS
FOR (e:Employee)
ON (e.employeeCode);
```

Và truy vấn:

```cypher
MATCH (e:Employee {employeeCode: $employeeCode})
RETURN e;
```

Vì các label không làm thay đổi danh tính nút, một nút `:Person:Employee` có thể được tìm thông qua label `Person` theo `personId` hoặc qua label `Employee` theo `employeeCode`, nếu các giá trị và cấu hình phù hợp.

Một truy vấn có nhiều nhãn như `MATCH (e:Person:Employee)` có thể được bộ tối ưu lựa chọn kế hoạch khác nhau tùy số liệu thống kê, index, điều kiện property và phiên bản Neo4j. Không nên giả định rằng việc thêm nhãn tự động khiến mọi truy vấn nhanh hơn.

Kiểm tra:

```cypher
SHOW CONSTRAINTS;
SHOW INDEXES;

EXPLAIN
MATCH (e:Person:Employee {personId: $personId})
RETURN e;
```

`EXPLAIN` lập kế hoạch mà không thực thi truy vấn. `PROFILE` có thể cho biết kế hoạch và số liệu thực thi khi thật sự chạy truy vấn; dùng trên database thử nghiệm hoặc với truy vấn phù hợp để tránh tác động không mong muốn.

## 9. MERGE và nguy cơ tạo trùng khi thay đổi vai trò

Đây là một lỗi quan trọng khi làm việc với nhiều nhãn.

Giả sử database đã có:

```cypher
CREATE (:Person {
  personId: 'ML-P003',
  fullName: 'Dũng'
});
```

Khi Dũng trở thành nhân viên, **đừng mặc định** rằng mẫu `MERGE` gồm cả hai nhãn sẽ tìm thấy nút cũ:

```cypher
// KHÔNG phù hợp khi chỉ muốn bổ sung vai trò cho Person đã có
MERGE (p:Person:Employee {personId: 'ML-P003'})
RETURN p;
```

Vì nút cũ chưa mang `Employee`, **mẫu đầy đủ không khớp**. Nếu không có ràng buộc phù hợp, hệ thống có thể tạo **một nút thứ hai** mang cả hai nhãn và cùng `personId`. Nếu có uniqueness constraint `Person.personId`, thao tác tạo trùng có thể bị từ chối. Dù trường hợp nào, đây không phải cách cập nhật vai trò mong muốn.

**Cách phù hợp hơn:** nhận diện nút bằng nhãn nền và khóa nghiệp vụ, sau đó gắn thêm nhãn vai trò.

```cypher
MERGE (p:Person {personId: $personId})
ON CREATE SET p.fullName = $fullName
SET p:Employee
RETURN p, labels(p) AS labels;
```

Khi chạy với `$personId = 'ML-P003'`, truy vấn sẽ tìm nút `Person` đã có và gắn nhãn `Employee` lên **chính nút đó**. Nên có uniqueness constraint trên `Person.personId` để bảo vệ danh tính khi nhiều giao dịch đồng thời.

Nếu bản ghi đã được bảo đảm tồn tại, có thể viết đơn giản:

```cypher
MATCH (p:Person {personId: $personId})
SET p:Employee
RETURN p;
```

Trong nhập dữ liệu hàng loạt, thực hiện bước chuẩn hóa định danh và gộp bản ghi trùng theo quy tắc nghiệp vụ trước khi gắn các nhãn vai trò; không suy ra trùng thực thể chỉ vì hai nút có cùng tên hiển thị.

## 10. Hành vi khi thay đổi nhãn: cần chú ý điều gì?

Thêm hoặc bỏ label chỉ làm thay đổi **phân loại** của nút; nó không tự động:

- Tạo thêm một nút mới hay sao chép property.
- Chuyển dữ liệu từ một nút sang nút khác.
- Tạo hoặc xóa các quan hệ như `WORKS_AT` hay `MENTORS`.
- Thiết lập khóa định danh hoặc bảo đảm các trường bắt buộc mà ứng dụng mong đợi.
- Suy luận ra nhãn cha theo quy ước phân loại.

Tuy nhiên, **thay đổi nhãn có thể làm thay đổi phạm vi mà index/constraint áp dụng cho nút**. Ví dụ, khi gắn nhãn `Person` cho một nút có `personId` trùng với nút `Person` khác, uniqueness constraint trên `Person.personId` sẽ ngăn thao tác không hợp lệ. Khi bỏ một nhãn, các truy vấn chỉ tìm nhãn đó sẽ không còn trả về nút.

Ví dụ minh họa:

```cypher
MATCH (p:Person {personId: 'ML-P001'})
REMOVE p:Mentor
RETURN p.personId AS id, labels(p) AS labels;
```

Sau lệnh, quan hệ `MENTORS` (nếu tồn tại) **vẫn được lưu**; hệ thống cần quy tắc nghiệp vụ riêng nếu việc ngừng vai trò đồng nghĩa phải kết thúc quan hệ hướng dẫn hoặc cập nhật lịch sử.

## 11. Ứng dụng trong Java Driver và Spring Data Neo4j

### 11.1. Truyền mã định danh dưới dạng tham số

Ứng dụng không nên ghép trực tiếp `personId` từ người dùng vào chuỗi Cypher. Với Neo4j Java Driver, có thể chạy truy vấn có tham số:

```cypher
MATCH (p:Person {personId: $personId})
SET p:Mentor
RETURN p.personId AS id, labels(p) AS currentLabels;
```

Driver truyền map tham số tương ứng, ví dụ:

```json
{
  "personId": "ML-P001"
}
```

Cách này giúp tách **cấu trúc truy vấn** và **giá trị nghiệp vụ**. Với các yêu cầu thay đổi loại vai trò theo đầu vào, không nên ghép tên label tùy ý từ request: hãy dùng danh sách nhãn được phép và kiểm soát truy vấn theo mô hình ứng dụng.

### 11.2. Ánh xạ entity và đa nhãn

Trong Spring Data Neo4j, cấu hình ánh xạ entity cần tương thích với **nhãn của nút** đang lưu. Với mô hình `Person` làm nhãn nền và `Employee`/`Mentor` làm vai trò, nên quyết định rõ:

1. Nhãn nào dùng để nhận diện entity chính khi tải/lưu?
2. Nhãn vai trò bổ sung do ai quản lý và ở bước nào của quy trình?
3. Khi cập nhật entity, ứng dụng có cần giữ lại các nhãn vai trò do dịch vụ khác gắn không?
4. Khi người dùng không còn vai trò, dữ liệu và relationship liên quan được xử lý ra sao?

Tùy phiên bản Spring Data Neo4j và cách cấu hình ánh xạ, thao tác lưu entity có thể quản lý những nhãn mà mapping coi là thuộc quyền của entity đó. Vì vậy, cần kiểm tra hành vi ánh xạ thực tế trước khi trộn cập nhật Cypher thủ công với lưu entity trên cùng nút.

## 12. Ví dụ tổng hợp: phân loại người dùng trong nền tảng học tập

Giả sử hệ thống có ba người dùng:

- An: người dùng, học viên và giảng viên.
- Bình: người dùng và học viên.
- Chi: người dùng và giảng viên.

Tạo một bộ dữ liệu độc lập trong database thử nghiệm:

```cypher
CREATE (:User:Learner:Instructor {
  userId: 'ML-U101',
  displayName: 'An'
});
CREATE (:User:Learner {
  userId: 'ML-U102',
  displayName: 'Bình'
});
CREATE (:User:Instructor {
  userId: 'ML-U103',
  displayName: 'Chi'
});
```

### 12.1. Tìm tất cả giảng viên

```cypher
MATCH (u:User:Instructor)
RETURN u.userId AS id, u.displayName AS name
ORDER BY id;
```

Kết quả dự kiến: **An** và **Chi**.

### 12.2. Tìm người đồng thời là học viên và giảng viên

```cypher
MATCH (u:User:Learner:Instructor)
RETURN u.userId AS id, u.displayName AS name;
```

Kết quả dự kiến: **An**. Mẫu khớp phép **giao** của ba nhóm nhãn.

### 12.3. Tìm học viên chưa có vai trò giảng viên

```cypher
MATCH (u:User:Learner)
WHERE NOT u:Instructor
RETURN u.userId AS id, u.displayName AS name;
```

Kết quả dự kiến: **Bình**.

### 12.4. Cấp thêm vai trò giảng viên cho Bình

```cypher
MATCH (u:User {userId: 'ML-U102'})
SET u:Instructor
RETURN u.displayName AS name, labels(u) AS labels;
```

Bình trở thành nút `:User:Learner:Instructor`. Không có nút người dùng mới; truy vấn ở mục 12.2 lúc này trả về **An và Bình**.

### 12.5. Thống kê theo nhãn

```cypher
MATCH (u:User)
RETURN count(u) AS totalUsers,
       sum(CASE WHEN u:Learner THEN 1 ELSE 0 END) AS learners,
       sum(CASE WHEN u:Instructor THEN 1 ELSE 0 END) AS instructors;
```

Theo trạng thái **sau bước 12.4**, có 3 user, 2 learner và 3 instructor. Số learner cộng instructor **lớn hơn tổng user** vì cùng một người có thể mang cả hai nhãn; đây là điều bình thường của mô hình đa nhãn.

## 13. Những lỗi mô hình hóa thường gặp

| Lỗi | Tác động | Cách sửa |
| --- | --- | --- |
| Tạo một nút riêng cho `Person`, `Employee` và `Mentor` của cùng một người | Trùng dữ liệu, khó đồng bộ và nối quan hệ | Gắn các nhãn thích hợp trên cùng một nút có định danh nghiệp vụ |
| Nghĩ `:Employee` tự suy ra `:Person` | Các truy vấn theo `Person` bỏ sót nút | Chủ động gắn nhãn nền và kiểm soát dữ liệu nhập |
| Đọc `(n:Person:Employee)` thành Person **hoặc** Employee | Truy vấn thiếu hoặc sai kết quả | Hiểu đây là điều kiện **đồng thời có cả hai nhãn** |
| Dùng label như `:User_123`, `:City_HaNoi` cho mọi giá trị | Số nhãn tăng theo dữ liệu, khó bảo trì | Dùng property hoặc node + relationship phù hợp |
| Dùng `MERGE (p:Person:Employee {id: ...})` khi nút `Person` đã tồn tại | Mẫu không khớp và có thể cố tạo nút trùng | `MERGE` hoặc `MATCH` theo nhãn nền + ID, rồi `SET p:Employee` |
| Cho rằng bỏ nhãn `Mentor` tự xóa liên kết `MENTORS` | Quan hệ cũ tiếp tục tồn tại, có thể sai nghiệp vụ | Thiết kế quy trình xử lý quan hệ/trạng thái theo nghiệp vụ |
| Đặt toàn bộ giá trị trạng thái thành nhiều nhãn động | Khó chuẩn hóa và lọc theo giá trị | Dùng property `status` khi cần biểu diễn một giá trị trạng thái |
| Dựa vào thứ tự trong `labels(n)` | Kết quả phụ thuộc chi tiết không nên giả định | Kiểm tra bằng phép thuộc danh sách hoặc so sánh tập nhãn |
| Giả định constraint trên `Person` áp dụng cho mọi `Employee` | Có thể bỏ sót nút không mang `Person` | Đặt constraint theo phạm vi label thực tế và duy trì quy ước nhãn |

## 14. Bài tập thực hành

Thực hiện trong database thử nghiệm để không ảnh hưởng dữ liệu thật.

**Bài 1 — Truy vấn giao của các nhãn.** Cho:

```text
N1: (:Person:Employee:Mentor)
N2: (:Person:Employee)
N3: (:Person:Customer)
N4: (:Company)
```

Hỏi:

1. `MATCH (n:Person:Employee)` khớp những nút nào?
2. `MATCH (n:Person:Mentor)` khớp những nút nào?
3. `MATCH (n:Person)` khớp bao nhiêu nút?

**Đáp án:** (1) N1, N2; (2) N1; (3) 3 nút — N1, N2, N3.

**Bài 2 — Cập nhật vai trò mà không tạo nút mới.** Viết Cypher để tìm người có `personId = 'ML-P001'`, thêm `:Reviewer`, bỏ `:Mentor`, rồi trả về các nhãn còn lại.

**Đáp án tham khảo:**

```cypher
MATCH (p:Person {personId: 'ML-P001'})
SET p:Reviewer
REMOVE p:Mentor
RETURN p.personId AS id, labels(p) AS labels;
```

**Bài 3 — Nhận diện lỗi MERGE.** Database đã có `(:User {userId: 'U100'})`. Vì sao `MERGE (:User:Instructor {userId: 'U100'})` có thể không bổ sung vai trò lên chính nút cũ?

**Đáp án:** `MERGE` tìm **toàn bộ mẫu** có cả hai nhãn và property. Nút cũ thiếu `Instructor` nên không khớp. Cách đúng cho việc thêm vai trò là tìm nút theo `:User` và `userId`, sau đó `SET u:Instructor`; cần constraint thích hợp trên ID để bảo vệ danh tính.

**Bài 4 — Thiết kế mô hình.** Một nhân viên từng làm ở ba công ty, mỗi lần có chức vụ và ngày bắt đầu/kết thúc riêng. Có nên dùng ba nhãn `:Employee_CompanyA`, `:Employee_CompanyB`, `:Employee_CompanyC`?

**Đáp án:** Thông thường không. Giữ nút `:Person`, có thể có `:Employee` theo quy ước hiện tại, và dùng relationship `WORKED_AT` có các property liên quan hoặc nút `Employment` nếu cần quản lý mỗi lần làm việc như thực thể riêng. Công ty nên là nút `:Company` có định danh rõ ràng.

## 15. Tổng kết

- Một nút Neo4j có thể mang **nhiều label** mà vẫn là **một thực thể duy nhất**.
- Nhãn phân loại thực thể theo nhóm/vai trò; property lưu giá trị; relationship mô tả kết nối giữa các thực thể.
- `MATCH (n:Person:Employee)` yêu cầu **cả hai nhãn**. Neo4j không suy luận rằng `Employee` tự động là `Person`.
- Dùng `SET n:Role` để thêm và `REMOVE n:Role` để bỏ nhãn, không cần tạo hoặc xóa nút.
- Chọn nhãn nền và mã nghiệp vụ ổn định; cân nhắc phạm vi constraint/index theo từng label; cẩn thận với `MERGE` trên mẫu có nhiều nhãn khi nút đã tồn tại.
- Khi thông tin có giá trị thay đổi, danh tính riêng hoặc hai đầu mút, hãy đánh giá **property** và **relationship** trước khi tạo thêm nhãn.

Hiểu đúng mô hình đa nhãn giúp bạn thiết kế property graph nhất quán, truy vấn Cypher theo vai trò chính xác và chuẩn bị tốt cho các chủ đề kế tiếp về relationship, đường đi, index/constraint, nhập dữ liệu và tích hợp Neo4j với ứng dụng Java.
