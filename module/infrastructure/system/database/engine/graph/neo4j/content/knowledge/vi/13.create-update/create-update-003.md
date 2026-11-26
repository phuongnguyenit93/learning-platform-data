# Phân biệt MERGE toàn mẫu với MERGE từng thực thể và quan hệ

> **Chương:** Tạo và cập nhật  
> **Mô-đun:** `DATABASE_ENGINE_GRAPH_NEO4J` — Neo4j, property graph và truy vấn Cypher.

Khi lưu dữ liệu liên kết trong Neo4j, ứng dụng thường cần **tìm hoặc tạo** một nút và **nối các nút** thành quan hệ. Cypher có lệnh `MERGE` để đáp ứng nhu cầu này. Tuy nhiên, viết một `MERGE` chứa **cả đường mẫu** và viết nhiều `MERGE` để xử lý **từng nút, sau đó từng quan hệ** có thể tạo kết quả rất khác nhau.

Ví dụ, hệ thống đã có nhân viên An và dự án Atlas nhưng chưa ghi nhận An tham gia Atlas. Nếu sử dụng `MERGE` cho toàn mẫu `(An)-[:WORKS_ON]->(Atlas)` với cả hai nút chưa được ràng buộc biến từ trước, Neo4j không tự tái sử dụng hai nút chỉ vì thuộc tính của chúng trùng khớp. Đây là một trong những nguyên nhân phổ biến gây **tạo trùng nút** hoặc **vi phạm ràng buộc duy nhất**.

Bài học tập trung vào tính nguyên tử của mẫu tìm kiếm của `MERGE`, vai trò của biến đã được ràng buộc, cách thiết kế khóa nghiệp vụ và quy trình thêm quan hệ an toàn.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Diễn giải đúng ngữ nghĩa “khớp toàn mẫu hoặc tạo toàn mẫu” của `MERGE`.
2. Dự đoán kết quả của `MERGE` khi đồ thị rỗng, khi chỉ có nút và khi quan hệ đã tồn tại.
3. Phân biệt `MERGE` toàn mẫu chưa ràng buộc nút, `MERGE` từng nút rồi từng quan hệ, và `MATCH` các nút đã có rồi `MERGE` quan hệ.
4. Sử dụng `ON CREATE SET` và `ON MATCH SET` đúng với từng `MERGE`, tránh đưa thuộc tính thường thay đổi vào khóa so khớp.
5. Áp dụng constraint, tham số, `UNWIND` và quan sát kết quả để hạn chế trùng dữ liệu trong ứng dụng Java, Spring Data Neo4j hoặc quá trình nhập dữ liệu.

## 2. Nhắc lại: mẫu đồ thị và MERGE

Trong mô hình *property graph*:

- **Node (nút)** biểu diễn thực thể, ví dụ `:Person`, `:Project`.
- **Relationship (quan hệ)** nối hai nút với một hướng và một kiểu, ví dụ `[:WORKS_ON]`.
- **Property (thuộc tính)** mô tả nút hoặc quan hệ, ví dụ `personId`, `projectId`, `role`.
- **Biến Cypher** như `p`, `pr`, `r` tham chiếu thành phần trong **phạm vi truy vấn**; biến không phải khóa định danh lâu dài của dữ liệu.

Dữ liệu nghiệp vụ minh họa:

~~~text
(:Person {personId: 'P01', name: 'An'})
                 |
                 | [:WORKS_ON {role: 'Backend'}]
                 v
(:Project {projectId: 'PR01', title: 'Atlas'})
~~~

Cú pháp cơ bản:

~~~cypher
MERGE (p:Person {personId: 'P01'})
RETURN p;
~~~

`MERGE` trước hết thử khớp mẫu đã nêu. Nếu có mẫu phù hợp, các thành phần tương ứng được dùng lại. Nếu không có mẫu phù hợp, Neo4j tạo phần cần tạo theo ngữ nghĩa **của cả mẫu trong mệnh đề `MERGE` đó**.

**Điểm khác với `CREATE`:** `CREATE` yêu cầu tạo mới theo mẫu. `MERGE` thực hiện tìm hoặc tạo theo mẫu. Nhưng `MERGE` **không bảo đảm duy nhất toàn cục** nếu dữ liệu thiếu khóa nghiệp vụ và ràng buộc phù hợp; cũng không tự ghép các phần khớp rời rạc của một mẫu chưa tồn tại thành một đường kết nối hoàn chỉnh.

## 3. MERGE toàn mẫu: khớp cả đường hoặc tạo cả đường

Xem truy vấn sau:

~~~cypher
MERGE (p:Person {personId: 'P01'})
      -[r:WORKS_ON]->
      (pr:Project {projectId: 'PR01'})
RETURN p, r, pr;
~~~

Đây là **một mệnh đề `MERGE` chứa toàn bộ mẫu ba thành phần**:

~~~text
(p:Person {personId: 'P01'})
       -[:WORKS_ON]->
(pr:Project {projectId: 'PR01'})
~~~

Khi `p` và `pr` chưa được ràng buộc từ `MATCH` hoặc mệnh đề trước, Neo4j cố tìm **một đường phù hợp với toàn bộ mẫu**. Việc tồn tại riêng một nút `Person` và một nút `Project` có đúng ID **chưa đủ** để mẫu trên được coi là đã khớp, nếu chưa tồn tại quan hệ `WORKS_ON` giữa chúng.

### 3.1. Ba trạng thái đầu vào và kết quả

Giả sử khóa `personId` và `projectId` là định danh nghiệp vụ, và toàn bộ ví dụ bên dưới sử dụng **các trạng thái dữ liệu giả định độc lập**, không phải chạy nối tiếp ba tình huống trong cùng cơ sở dữ liệu.

| Trạng thái trước truy vấn | `MERGE` toàn mẫu sẽ làm gì? |
|---|---|
| Chưa có người P01, dự án PR01 và quan hệ `WORKS_ON` | Tạo hai nút và một quan hệ |
| Đã có cả hai nút P01, PR01 nhưng **chưa có quan hệ** giữa chúng | Không khớp toàn mẫu; cố tạo một mẫu mới gồm hai nút và một quan hệ |
| Đã có đủ P01 `-[:WORKS_ON]->` PR01 | Khớp mẫu đang có, sử dụng lại các thành phần đã khớp |

Đối với hàng thứ hai, kết quả phụ thuộc ràng buộc:

- **Không có constraint duy nhất:** có thể xuất hiện bản sao nút P01, PR01 cùng một quan hệ mới nối các bản sao đó.
- **Có constraint duy nhất** trên `:Person(personId)` và `:Project(projectId)`: truy vấn có thể thất bại do việc tạo hai nút mới xung đột với các nút hiện hữu. Nó **không tự đổi chiến lược** để tái sử dụng hai nút và chỉ tạo quan hệ.

### 3.2. Sơ đồ minh họa tình huống có sẵn hai nút

**Trước khi chạy** `MERGE` toàn mẫu:

~~~text
[P01: An]                              [PR01: Atlas]
  (Person)                              (Project)

     Hai nút đã có, chưa có WORKS_ON giữa chúng.
~~~

**Sau khi chạy trên đồ thị không có constraint duy nhất:**

~~~text
[P01: An]                              [PR01: Atlas]
  (Person)                              (Project)

[P01: An] --[:WORKS_ON]--------------> [PR01: Atlas]
  (Person mới)                           (Project mới)
~~~

Quan hệ mới nối hai bản sao vừa tạo, **không phải** hai nút ban đầu. Các thuộc tính giống nhau không khiến hai nút là cùng một thực thể trong đồ thị.

### 3.3. Vì sao “toàn mẫu” quan trọng?

Một mẫu quan hệ gồm cấu trúc, nhãn, kiểu quan hệ, hướng và các giá trị thuộc tính dùng để so khớp. Thiếu một thành phần khiến mẫu **không khớp đầy đủ**:

~~~cypher
MERGE (p:Person {personId: 'P01'})
      -[:WORKS_ON {role: 'Backend'}]->
      (pr:Project {projectId: 'PR01'});
~~~

Giả sử đã tồn tại P01 `-[:WORKS_ON {role: 'Data'}]->` PR01. Mẫu yêu cầu `role: 'Backend'` không khớp quan hệ cũ; nếu hai đầu mút chưa được ràng buộc, `MERGE` toàn mẫu lại cố tạo cả mẫu mới. Bởi vậy, các trường như `role`, `status` hay `updatedAt` cần được cân nhắc kỹ: nếu chúng thay đổi theo thời gian, không nên mặc nhiên đưa chúng vào phần định danh của mẫu.

## 4. MERGE từng thực thể, rồi MERGE quan hệ

Với bài toán “P01 tham gia PR01”, cách tổ chức câu lệnh thường phù hợp hơn là:

~~~cypher
MERGE (p:Person {personId: 'P01'})
MERGE (pr:Project {projectId: 'PR01'})
MERGE (p)-[r:WORKS_ON]->(pr)
RETURN p.personId AS personId,
       pr.projectId AS projectId,
       type(r) AS relationshipType;
~~~

Ở đây có **ba mệnh đề `MERGE` độc lập**:

1. `MERGE (p:Person {personId: 'P01'})` tìm hoặc tạo **nút Person**; sau mệnh đề này, `p` đã tham chiếu tới nút cụ thể.
2. `MERGE (pr:Project {projectId: 'PR01'})` tìm hoặc tạo **nút Project**; sau mệnh đề này, `pr` đã tham chiếu tới nút cụ thể.
3. `MERGE (p)-[r:WORKS_ON]->(pr)` tìm quan hệ giữa **đúng hai nút đã được ràng buộc**, hoặc tạo quan hệ nếu chưa có.

Với trạng thái đã có P01 và PR01 nhưng chưa nối nhau, hai `MERGE` đầu sử dụng lại các nút phù hợp và `MERGE` cuối tạo quan hệ mới:

~~~text
[P01: An] --[:WORKS_ON]--> [PR01: Atlas]
  nút cũ        mới          nút cũ
~~~

Điều quan trọng là **biến `p` và `pr` đã có giá trị trước khi tạo quan hệ**. Mẫu quan hệ không được phép tự ý tạo lại hai nút đầu mút đã được ràng buộc.

### 4.1. So sánh trực tiếp

| Tiêu chí | `MERGE` toàn mẫu khi nút chưa được ràng buộc | `MERGE` từng nút, sau đó quan hệ |
|---|---|---|
| Số mệnh đề | Một `MERGE` cho đường đầy đủ | Nhiều `MERGE`, mỗi mệnh đề có nhiệm vụ riêng |
| Phần bắt buộc khớp | Toàn bộ đường được khai báo | Từng nút trước, rồi quan hệ nối các nút đã tìm/tạo |
| Khi đã có cả hai nút nhưng thiếu quan hệ | Cố tạo toàn bộ mẫu mới | Tái sử dụng hai nút, tạo quan hệ còn thiếu |
| Khi có constraint duy nhất của nút | Có thể lỗi do xung đột khi tạo toàn mẫu | Phù hợp hơn khi định danh từng nút bằng khóa duy nhất |
| Khi chạy lặp lại | Tìm lại toàn mẫu nếu đã có | Tìm lại từng nút và quan hệ đã có |
| Trường hợp phù hợp | Muốn kiểm tra/tạo cả mẫu như một đơn vị, hoặc mẫu nhỏ với thành phần hoàn toàn mới | Đồng bộ dữ liệu liên kết, tái sử dụng thực thể, nhập dữ liệu từ ứng dụng |

**Lưu ý:** `MERGE` từng nút vẫn có thể gây kết quả sai nếu thuộc tính dùng làm khóa không duy nhất hoặc được chọn không đúng. Cấu trúc mệnh đề tốt chỉ phát huy hiệu quả khi đi cùng khóa nghiệp vụ và constraint.

### 4.2. Khi hai nút bắt buộc đã tồn tại: MATCH + MERGE

Đôi khi ứng dụng phải **từ chối tạo quan hệ nếu chưa có người hoặc dự án**, tức là không được tự tạo nút thiếu. Hãy dùng `MATCH`:

~~~cypher
MATCH (p:Person {personId: 'P01'})
MATCH (pr:Project {projectId: 'PR01'})
MERGE (p)-[r:WORKS_ON]->(pr)
RETURN p.personId AS personId,
       pr.projectId AS projectId,
       type(r) AS relationshipType;
~~~

Hai `MATCH` ràng buộc `p` và `pr` vào nút hiện có, sau đó `MERGE` chỉ xử lý quan hệ. Nếu một `MATCH` không trả kết quả, truy vấn không có dòng để tiếp tục và **không tạo quan hệ**. Điều này khác với `MERGE` từng nút, vốn có thể tạo nút còn thiếu.

### 4.3. Trường hợp đầu mút đã ràng buộc nhưng vẫn dùng một MERGE

Tên gọi “`MERGE` toàn mẫu” chỉ có ý nghĩa khi xem cả **phạm vi biến**. Ví dụ:

~~~cypher
MATCH (p:Person {personId: 'P01'})
MATCH (pr:Project {projectId: 'PR01'})
MERGE (p)-[r:WORKS_ON]->(pr)
RETURN r;
~~~

Dù mẫu trong `MERGE` có hình dạng một đường gồm hai đầu mút và một quan hệ, `p` và `pr` **đã được ràng buộc** trước đó, nên không xảy ra việc tạo bản sao hai nút như ví dụ `MERGE` toàn mẫu chưa ràng buộc. Không thể dựa riêng vào số lượng dấu ngoặc trong mệnh đề để kết luận có tạo lại nút hay không.

## 5. ON CREATE SET và ON MATCH SET áp dụng cho từng MERGE

`ON CREATE SET` chạy khi chính mệnh đề `MERGE` ngay trước đó **tạo mới** mẫu của mình. `ON MATCH SET` chạy khi mệnh đề `MERGE` đó **khớp mẫu đang tồn tại**.

Ví dụ tạo hoặc tìm người theo khóa ổn định và cập nhật tên:

~~~cypher
MERGE (p:Person {personId: $personId})
ON CREATE SET
  p.name = $name,
  p.createdAt = datetime()
ON MATCH SET
  p.name = $name,
  p.updatedAt = datetime()
RETURN p;
~~~

`personId` là khóa so khớp. Khi nút mới, gán `createdAt`; khi tìm thấy nút, cập nhật `name` và `updatedAt`.

### 5.1. Kết hợp ba MERGE, đặt thuộc tính đúng vị trí

~~~cypher
MERGE (p:Person {personId: $personId})
ON CREATE SET
  p.name = $personName,
  p.createdAt = datetime()
ON MATCH SET
  p.name = $personName

MERGE (pr:Project {projectId: $projectId})
ON CREATE SET
  pr.title = $projectTitle,
  pr.createdAt = datetime()
ON MATCH SET
  pr.title = $projectTitle

MERGE (p)-[r:WORKS_ON]->(pr)
ON CREATE SET
  r.role = $role,
  r.joinedOn = date(),
  r.createdAt = datetime()
ON MATCH SET
  r.role = $role,
  r.updatedAt = datetime()

RETURN p.personId AS personId,
       pr.projectId AS projectId,
       r.role AS role;
~~~

Ở đây:

- Nhóm `ON CREATE/ON MATCH` đầu thuộc **mệnh đề MERGE nút Person**.
- Nhóm tiếp theo thuộc **mệnh đề MERGE nút Project**.
- Nhóm cuối thuộc **mệnh đề MERGE quan hệ WORKS_ON**.

Điều này cho phép bạn tách chính sách ghi dữ liệu cho từng thực thể và quan hệ. Với kiểu liên kết chỉ cần lưu một quan hệ `WORKS_ON` cho mỗi cặp người–dự án, `role` thường là **thuộc tính cập nhật** của quan hệ, không phải một phần khóa so khớp.

### 5.2. Không đưa dữ liệu thay đổi thường xuyên vào khóa MERGE

Cách dễ gây lỗi:

~~~cypher
MERGE (p:Person {
  personId: $personId,
  name: $personName,
  department: $department
});
~~~

Nếu nhân viên chuyển phòng hoặc thay đổi tên, mẫu mới khác mẫu cũ. Neo4j có thể cố tạo một nút khác cùng `personId`; khi có constraint duy nhất sẽ gặp lỗi.

Cách phù hợp hơn:

~~~cypher
MERGE (p:Person {personId: $personId})
SET p.name = $personName,
    p.department = $department
RETURN p;
~~~

**Quy tắc:** thuộc tính trong phần `MERGE` nên mô tả **điều kiện nhận diện ổn định** của thực thể; thuộc tính thường thay đổi được cập nhật bằng `SET` hoặc các nhánh `ON CREATE/ON MATCH`. Nếu khóa nghiệp vụ có thể thay đổi, hãy cân nhắc dùng một định danh ổn định khác.

## 6. Constraint và index: giữ đúng định danh

Để hạn chế tạo trùng khi nhiều người hoặc nhiều luồng cùng ghi, hãy tạo **ràng buộc duy nhất** cho khóa nghiệp vụ.

Ví dụ trên cơ sở dữ liệu học tập Neo4j hỗ trợ cú pháp constraint này:

~~~cypher
CREATE CONSTRAINT person_personId_unique IF NOT EXISTS
FOR (p:Person)
REQUIRE p.personId IS UNIQUE;
~~~

~~~cypher
CREATE CONSTRAINT project_projectId_unique IF NOT EXISTS
FOR (pr:Project)
REQUIRE pr.projectId IS UNIQUE;
~~~

Khi tạo constraint, Neo4j yêu cầu dữ liệu đang có phải đáp ứng điều kiện duy nhất. Nếu tồn tại nhiều nút cùng khóa, thao tác tạo constraint có thể thất bại và phải xử lý bản ghi trùng trước.

### 6.1. Constraint làm gì, không làm gì?

Constraint duy nhất giúp:

- Ngăn hai nút cùng nhãn có cùng giá trị khóa đã ràng buộc.
- Giúp bảo toàn khóa nghiệp vụ khi nhiều giao dịch cạnh tranh.
- Cung cấp cơ sở cho tìm kiếm chính xác theo `personId` hoặc `projectId`; ràng buộc duy nhất của nút đi kèm index hỗ trợ truy vấn.

Nhưng constraint **không**:

- Chuyển `MERGE` toàn mẫu thành “ghép các nút đã có rồi tạo mỗi quan hệ”.
- Tự quyết định đâu là khóa nghiệp vụ đúng.
- Bảo đảm chỉ có một quan hệ giữa hai nút khi không có chính sách/ràng buộc dành cho quan hệ và ghi đồng thời.

Một nút có constraint duy nhất trên `personId` vẫn có thể thiếu `personId` nếu không có ràng buộc hiện diện thích hợp. Vì vậy, luôn kiểm tra đầu vào.

### 6.2. MERGE và NULL

Không sử dụng giá trị `null` cho một thuộc tính định danh trong mẫu `MERGE`:

~~~cypher
// Nếu $personId = null, câu lệnh MERGE có thể báo lỗi
MERGE (p:Person {personId: $personId});
~~~

Cần xác thực `personId` và `projectId` ở lớp ứng dụng trước khi gửi truy vấn. Tránh tạo nút dự phòng bằng các khóa như chuỗi rỗng chỉ để vượt qua kiểm tra `null`; chúng có thể làm sai dữ liệu.

### 6.3. Quan hệ song song và ghi đồng thời

`MERGE (p)-[:WORKS_ON]->(pr)` tìm quan hệ phù hợp giữa hai nút **theo kiểu và hướng đã chỉ định**. Khi đã có quan hệ phù hợp, `MERGE` thường dùng lại quan hệ đó, nhưng nếu từ trước đã tồn tại **nhiều quan hệ giống mẫu**, việc khớp có thể trả **nhiều dòng**. `MERGE` không tự xóa các quan hệ trùng hiện hữu.

Trong ghi đồng thời, vẫn phải thiết kế giao dịch và cơ chế toàn vẹn thích hợp. Constraint duy nhất của **nút** không mặc nhiên ngăn trùng **quan hệ**. Nếu nghiệp vụ yêu cầu định danh riêng từng quan hệ, cân nhắc một khóa nghiệp vụ cho quan hệ cùng ràng buộc tương ứng khi phiên bản/kiểu dữ liệu của Neo4j hỗ trợ, đồng thời kiểm soát tính nhất quán ở ứng dụng. Không nên coi `MERGE` đơn lẻ là bảo đảm tuyệt đối cho mọi trường hợp cạnh tranh ghi.

## 7. Thuộc tính quan hệ có tham gia nhận diện hay không?

Cùng hai nút có thể có nhiều quan hệ `WORKS_ON` nếu mô hình cho phép nhiều lần phân công.

**Tình huống A — Mỗi người chỉ có một phân công hiện tại trên một dự án:** kiểu quan hệ và hai đầu mút đủ để nhận diện, còn `role` được cập nhật.

~~~cypher
MATCH (p:Person {personId: $personId})
MATCH (pr:Project {projectId: $projectId})
MERGE (p)-[r:WORKS_ON]->(pr)
ON CREATE SET r.startedOn = date()
SET r.role = $role
RETURN r;
~~~

Nếu vai trò đổi từ `Backend` sang `Tech Lead`, cùng quan hệ được cập nhật (giả sử dữ liệu đầu vào không có quan hệ trùng và mỗi đầu mút được nhận diện duy nhất).

**Tình huống B — Cần lưu nhiều đợt phân công độc lập:** quan hệ phải có định danh như `assignmentId` hoặc được biểu diễn bằng nút `Assignment`, tùy mô hình.

~~~cypher
MATCH (p:Person {personId: $personId})
MATCH (pr:Project {projectId: $projectId})
MERGE (p)-[r:WORKS_ON {assignmentId: $assignmentId}]->(pr)
ON CREATE SET r.startedOn = date($startDate)
SET r.role = $role
RETURN r;
~~~

Truy vấn B phân biệt các quan hệ theo `assignmentId` trên **hai đầu mút đã có**. Nếu yêu cầu toàn vẹn là duy nhất theo `assignmentId` trên toàn kiểu quan hệ, hãy thiết kế thêm constraint phù hợp và xử lý xung đột. Nếu `assignmentId` của một bản ghi có thể chỉ ra hai đầu mút khác nhau, cần xác định chính sách sửa lỗi dữ liệu vì `MERGE` theo cả đầu mút không tự di chuyển quan hệ cũ.

### 7.1. Hướng quan hệ là một phần của mẫu

~~~cypher
MERGE (a)-[:REPORTS_TO]->(b);
~~~

không cùng mẫu với:

~~~cypher
MERGE (b)-[:REPORTS_TO]->(a);
~~~

Với các quan hệ có tính hướng rõ như `REPORTS_TO`, `WORKS_ON`, `OWNS`, phải viết đúng chiều. Cypher cho phép mẫu `MERGE` không chỉ định hướng ở trường hợp nhất định, nhưng khi phải tạo quan hệ, hướng được Neo4j lựa chọn và không nên dùng cách này nếu nghiệp vụ phụ thuộc chiều.

## 8. Ví dụ đối chiếu chạy được: hai nút đã tồn tại

**Giả định:** các ví dụ sau chạy trong môi trường thử nghiệm với hai nút:

~~~cypher
CREATE
  (:Person {personId: 'P-MERGE-01', name: 'An'}),
  (:Project {projectId: 'PR-MERGE-01', title: 'Atlas'});
~~~

Chỉ chạy bước chuẩn bị **một lần** trên dữ liệu thử nghiệm chưa có hai khóa trên. Bước dưới dùng để kiểm tra:

~~~cypher
MATCH (p:Person {personId: 'P-MERGE-01'})
MATCH (pr:Project {projectId: 'PR-MERGE-01'})
RETURN p.personId AS personId, pr.projectId AS projectId;
~~~

### 8.1. Cách viết toàn mẫu dễ gây trùng

~~~cypher
MERGE (p:Person {personId: 'P-MERGE-01'})
      -[r:WORKS_ON]->
      (pr:Project {projectId: 'PR-MERGE-01'})
RETURN p, r, pr;
~~~

Nếu chưa có `WORKS_ON` giữa hai nút và không có constraint duy nhất, thao tác này có thể tạo thêm **hai nút cùng giá trị ID nghiệp vụ**. Nếu đã có constraint duy nhất, thao tác có thể lỗi do trùng khóa.

**Không chạy truy vấn này trên dữ liệu thật chỉ để thử.** Nên thực hành trên đồ thị kiểm thử riêng, hoặc dùng `EXPLAIN` để xem kế hoạch mà không thực thi phần ghi.

### 8.2. Cách viết dùng lại nút hiện có

Trên trạng thái ban đầu với hai nút duy nhất, chưa có quan hệ:

~~~cypher
MATCH (p:Person {personId: 'P-MERGE-01'})
MATCH (pr:Project {projectId: 'PR-MERGE-01'})
MERGE (p)-[r:WORKS_ON]->(pr)
ON CREATE SET r.role = 'Backend', r.createdAt = datetime()
ON MATCH SET r.role = 'Backend'
RETURN p.personId AS personId,
       pr.projectId AS projectId,
       r.role AS role;
~~~

Lần chạy đầu tạo quan hệ, **không tạo thêm nút**. Chạy lại khi chỉ có một quan hệ khớp sẽ sử dụng lại quan hệ đó. Điều kiện quan trọng là mỗi `MATCH` tìm đúng một đầu mút.

Kiểm tra các nút và quan hệ:

~~~cypher
MATCH (p:Person {personId: 'P-MERGE-01'})
RETURN count(p) AS personCount;
~~~

~~~cypher
MATCH (pr:Project {projectId: 'PR-MERGE-01'})
RETURN count(pr) AS projectCount;
~~~

~~~cypher
MATCH (p:Person {personId: 'P-MERGE-01'})
      -[r:WORKS_ON]->
      (pr:Project {projectId: 'PR-MERGE-01'})
RETURN count(r) AS relationshipCount;
~~~

Nếu bắt đầu từ đúng hai nút duy nhất và đã chạy đúng một lần truy vấn `MATCH` + `MERGE` ở trên, ba kết quả kỳ vọng lần lượt là `1`, `1`, `1`.

### 8.3. Với dữ liệu có thể thiếu nút

Nếu mục tiêu là tạo cả người hoặc dự án khi thiếu, dùng cách `MERGE` từng thực thể:

~~~cypher
MERGE (p:Person {personId: 'P-MERGE-02'})
ON CREATE SET p.name = 'Bình'
MERGE (pr:Project {projectId: 'PR-MERGE-02'})
ON CREATE SET pr.title = 'Tìm kiếm tri thức'
MERGE (p)-[:WORKS_ON]->(pr)
RETURN p.personId AS personId, pr.projectId AS projectId;
~~~

Bất kể hai nút đã có hay chưa, cách này có thể tìm/tạo từng nút rồi tìm/tạo quan hệ. Khi dữ liệu có thể bị ghi song song, bổ sung constraint và kiểm soát giao dịch.

## 9. Tạo hoặc nối hàng loạt bằng UNWIND

Ứng dụng thường nhận một danh sách phân công, mỗi bản ghi gồm mã người, mã dự án và vai trò.

Ví dụ cấu trúc tham số:

~~~json
{
  "assignments": [
    {
      "personId": "P01",
      "personName": "An",
      "projectId": "PR01",
      "projectTitle": "Atlas",
      "role": "Backend"
    },
    {
      "personId": "P02",
      "personName": "Bình",
      "projectId": "PR01",
      "projectTitle": "Atlas",
      "role": "Data Engineer"
    }
  ]
}
~~~

Truy vấn:

~~~cypher
UNWIND $assignments AS row
MERGE (p:Person {personId: row.personId})
ON CREATE SET p.name = row.personName
MERGE (pr:Project {projectId: row.projectId})
ON CREATE SET pr.title = row.projectTitle
MERGE (p)-[r:WORKS_ON]->(pr)
ON CREATE SET r.createdAt = datetime()
SET r.role = row.role
RETURN count(r) AS processedAssignments;
~~~

Với hai dòng đầu vào hợp lệ và dữ liệu không có trùng khóa:

- Hai nút Person được tìm/tạo theo `personId`.
- Một nút Project được tìm/tạo theo `projectId` dù `PR01` xuất hiện ở nhiều dòng.
- Quan hệ `WORKS_ON` được tìm/tạo giữa từng người và dự án tương ứng.
- `count(r)` đếm số dòng xử lý có quan hệ khớp; **không phải** số quan hệ mới được tạo trong lần chạy này.

Nếu tải lại cùng danh sách, `MERGE` theo từng thực thể và quan hệ tránh việc tạo lại cùng mẫu trong điều kiện bình thường; tuy nhiên vẫn cần constraint khóa, giao dịch và kiểm soát đầu vào để đảm bảo nhất quán khi nhiều tiến trình thực thi đồng thời. Với dữ liệu lớn, nên chia lô hợp lý và theo dõi kế hoạch truy vấn.

## 10. Kết nối với Java Driver và Spring Data Neo4j

Khi gửi truy vấn qua Neo4j Java Driver, nên dùng tham số thay vì ghép dữ liệu người dùng vào chuỗi Cypher. Ví dụ:

~~~java
import java.util.Map;
import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;

public class AssignmentService {
    private final Driver driver;

    public AssignmentService(Driver driver) {
        this.driver = driver;
    }

    public void assign(String personId, String projectId, String role) {
        String cypher = """
            MERGE (p:Person {personId: $personId})
            MERGE (pr:Project {projectId: $projectId})
            MERGE (p)-[r:WORKS_ON]->(pr)
            SET r.role = $role
            """;

        try (Session session = driver.session()) {
            session.executeWrite(tx -> {
                tx.run(cypher, Map.of(
                    "personId", personId,
                    "projectId", projectId,
                    "role", role
                )).consume();
                return null;
            });
        }
    }
}
~~~

Đoạn mã minh họa cách gửi một truy vấn gồm nhiều `MERGE` trong giao dịch ghi; đối tượng `Driver` do ứng dụng quản lý vòng đời. Ở hệ thống thực tế, hãy xác thực tham số, dùng khóa duy nhất, xác định database và xử lý lỗi giao dịch phù hợp.

Với **Spring Data Neo4j**, lớp entity và repository có thể giúp ánh xạ các nút và quan hệ. Tuy nhiên, việc lưu một đối tượng Java không thay thế việc hiểu ngữ nghĩa từng mẫu Cypher. Với các truy vấn tùy biến, nguyên tắc vẫn giữ nguyên: nhận diện từng nút bằng khóa ổn định trước khi tìm/tạo quan hệ. Phân biệt rõ kiểu ghi đồng bộ, tạo lịch sử và cập nhật thuộc tính để tránh tạo cấu trúc đồ thị ngoài ý muốn.

## 11. Hiệu năng và vận hành

Dùng `MERGE` từng nút cần thao tác tìm kiếm trên từng nhãn và khóa, vì vậy hiệu năng phụ thuộc vào dữ liệu và index/constraint:

- Tạo **constraint duy nhất** trên khóa nghiệp vụ trước khi nhập dữ liệu hàng loạt, nếu dữ liệu hiện hữu đã hợp lệ.
- Đặt nhãn và thuộc tính khóa rõ ràng như `:Person(personId)`, `:Project(projectId)`.
- Tránh dùng thuộc tính thay đổi liên tục làm khóa cho `MERGE`, khiến hệ thống mất khả năng tìm lại thực thể.
- Kiểm tra `MATCH` có trả đúng một bản ghi trên mỗi khóa hay không. Nếu trả nhiều bản ghi, số dòng ghép cặp và số quan hệ được xử lý có thể tăng ngoài dự kiến.
- Dùng `EXPLAIN` để quan sát kế hoạch mà **không thực thi câu lệnh ghi**. `PROFILE` thực thi truy vấn để đo thống kê thực tế, nên chỉ dùng với câu ghi trên dữ liệu thử nghiệm có kiểm soát.
- Chọn kích thước lô hợp lý khi dùng `UNWIND`; theo dõi lỗi constraint, số dòng xử lý, số nút và số quan hệ mới tạo.

Một số lỗi hay gặp:

| Hiện tượng | Nguyên nhân | Hướng xử lý |
|---|---|---|
| Hai nút có cùng `personId` sau khi nối quan hệ | `MERGE` toàn mẫu cố tạo toàn bộ đường mới | `MERGE` từng nút hoặc `MATCH` đầu mút rồi `MERGE` quan hệ |
| `MERGE` toàn mẫu báo lỗi trùng khóa | Constraint ngăn tạo nút mới cùng khóa khi thiếu quan hệ | Tách việc nhận diện nút và tạo quan hệ |
| Cập nhật tên người lại gây lỗi constraint | Đưa cả `name` vào mẫu `MERGE` của nút | `MERGE` theo khóa ổn định, dùng `SET` để cập nhật tên |
| Mỗi vai trò tạo một quan hệ khác nhau | `role` bị đưa vào phần so khớp dù là thuộc tính thay đổi | `MERGE` quan hệ theo hai đầu mút và kiểu, sau đó `SET r.role` |
| Một lệnh trả nhiều dòng và cập nhật nhiều quan hệ | Dữ liệu đã có quan hệ trùng hoặc `MATCH` khớp nhiều nút | Kiểm tra tính duy nhất của đầu mút và dữ liệu cũ |
| Quan hệ bị đảo chiều | Dùng chiều mũi tên sai khi `MERGE` | Thiết kế chiều chuẩn cho từng kiểu quan hệ |
| `MERGE` không chạy với giá trị khóa thiếu | Giá trị dùng trong mẫu là `null` | Xác thực định danh trước giao dịch |

## 12. Bài tập tự kiểm tra

### Bài 1 — Dự đoán kết quả

Giả sử đồ thị **chỉ có**:

~~~cypher
CREATE (:User {userId: 'U01'});
CREATE (:Group {groupId: 'G01'});
~~~

Chưa có quan hệ `MEMBER_OF`. Chưa áp dụng constraint duy nhất.

Câu lệnh A:

~~~cypher
MERGE (:User {userId: 'U01'})
      -[:MEMBER_OF]->
      (:Group {groupId: 'G01'});
~~~

Câu lệnh B (đặt ở một bản sao khác của trạng thái dữ liệu ban đầu):

~~~cypher
MERGE (u:User {userId: 'U01'})
MERGE (g:Group {groupId: 'G01'})
MERGE (u)-[:MEMBER_OF]->(g);
~~~

**Câu hỏi:** Câu lệnh nào có thể tạo thêm các nút cùng khóa nghiệp vụ?

<details>
<summary>Đáp án</summary>

- **A:** Không tìm thấy toàn mẫu. Có thể tạo thêm một `User`, một `Group` và quan hệ nối hai nút mới; nếu có constraint duy nhất trên hai khóa thì có thể báo lỗi thay vì tạo trùng.
- **B:** Từng nút được tìm thấy và dùng lại, `MERGE` cuối tạo quan hệ giữa hai nút cũ. Với dữ liệu mỗi khóa chỉ có một nút và chưa có quan hệ, không tạo thêm nút.

</details>

### Bài 2 — Viết truy vấn phù hợp

Yêu cầu: người `U02` và nhóm `G02` **phải tồn tại từ trước**; tạo quan hệ `MEMBER_OF` nếu thiếu, giữ `joinedOn` của lần tạo đầu, có thể cập nhật `role` trong mỗi lần gọi.

<details>
<summary>Đáp án tham khảo</summary>

~~~cypher
MATCH (u:User {userId: 'U02'})
MATCH (g:Group {groupId: 'G02'})
MERGE (u)-[m:MEMBER_OF]->(g)
ON CREATE SET m.joinedOn = date()
SET m.role = $role
RETURN u.userId AS userId, g.groupId AS groupId, m.role AS role;
~~~

Nếu không tìm thấy đầu mút, truy vấn không tạo nút mới cũng không tạo quan hệ.

</details>

### Bài 3 — Chọn khóa trong MERGE

Với dữ liệu người dùng, hãy so sánh hai mẫu:

~~~cypher
MERGE (u:User {userId: $userId, displayName: $displayName})
~~~

~~~cypher
MERGE (u:User {userId: $userId})
SET u.displayName = $displayName
~~~

Nếu người dùng đổi tên hiển thị, câu lệnh nào ổn định hơn? **Đáp án:** câu thứ hai vì dùng `userId` để nhận diện và cập nhật `displayName` riêng.

## 13. Tổng kết

| Nhu cầu | Mẫu truy vấn phù hợp |
|---|---|
| Cần nguyên một mẫu đường và chắc chắn muốn tìm/tạo **toàn mẫu** | `MERGE (a:Label {...})-[:TYPE]->(b:Label {...})`, hiểu rõ quy tắc khớp toàn mẫu |
| Cần tìm/tạo mỗi thực thể rồi nối chúng | `MERGE (a:Label {id: ...}) MERGE (b:Label {id: ...}) MERGE (a)-[:TYPE]->(b)` |
| Hai đầu mút **bắt buộc tồn tại** | `MATCH (a:Label {id: ...}) MATCH (b:Label {id: ...}) MERGE (a)-[:TYPE]->(b)` |
| Cần cập nhật thuộc tính thay đổi | `MERGE` theo khóa ổn định, sau đó `SET` hoặc `ON CREATE/ON MATCH SET` |
| Cần tránh trùng dữ liệu theo khóa nghiệp vụ | Constraint phù hợp, khóa ổn định và quản lý giao dịch; kiểm tra dữ liệu đầu vào |

**Ghi nhớ cốt lõi:** `MERGE` là thao tác tìm hoặc tạo **theo đúng mẫu trong từng mệnh đề**, không phải phép “tự lắp ghép” mọi nút rời rạc trùng thuộc tính. Khi các nút được định danh độc lập, hãy **ràng buộc từng đầu mút trước** rồi mới `MERGE` quan hệ giữa chúng.

**Liên hệ bài tiếp theo:** hiểu rõ `MERGE` giúp học các thao tác `SET`, `REMOVE`, `DELETE`, nhập dữ liệu theo lô, thiết kế constraint/index, đọc kế hoạch truy vấn và sử dụng truy vấn Cypher trong Java Driver hoặc Spring Data Neo4j.
