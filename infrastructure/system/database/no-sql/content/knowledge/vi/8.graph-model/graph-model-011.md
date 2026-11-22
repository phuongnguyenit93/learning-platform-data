# Ví dụ Neo4j hoặc hệ đồ thị khác với mô hình/ngôn ngữ tương ứng

Trong các mô hình NoSQL, **mô hình đồ thị** (*graph model*) phù hợp khi mối liên hệ giữa các thực thể là phần quan trọng của dữ liệu và câu truy vấn. Một hệ thống học trực tuyến không chỉ có học viên và khóa học: học viên đăng ký khóa học, khóa học bao phủ chủ đề, khóa học khác yêu cầu hoàn thành khóa trước đó, và người học có thể theo dõi nhau. Những câu hỏi như “khóa học nào là điều kiện tiên quyết gián tiếp của khóa nâng cao?” hay “gợi ý khóa học theo các chủ đề đã học” tự nhiên được diễn đạt bằng **đường đi qua nhiều mối liên hệ**.

Bài học sử dụng **Neo4j** và ngôn ngữ truy vấn **Cypher** để xây dựng một ví dụ xuyên suốt. Mục tiêu là thấy rõ **mô hình dữ liệu**, **ngôn ngữ truy vấn** và **hệ quản trị** phối hợp thế nào, không coi chúng là ba tên gọi của cùng một thứ.

## 1. Phân biệt mô hình đồ thị, Cypher và Neo4j

| Khái niệm | Vai trò | Trong ví dụ |
| --- | --- | --- |
| **Mô hình đồ thị thuộc tính** (*property graph*) | Biểu diễn các thực thể bằng đỉnh, liên hệ bằng cạnh và dữ liệu bổ sung bằng thuộc tính | Học viên, khóa học, chủ đề và các liên kết giữa chúng |
| **Cypher** | Ngôn ngữ truy vấn và thao tác đồ thị theo các mẫu node–relationship | `MATCH`, `CREATE`, `MERGE`, `WHERE`, `RETURN` |
| **Neo4j** | DBMS hiện thực việc lưu, truy vấn, lập chỉ mục, bảo đảm giao dịch và vận hành đồ thị | Phần mềm chạy các lệnh Cypher trên dữ liệu mẫu |

Một hệ đồ thị khác có thể sử dụng cách biểu diễn hoặc ngôn ngữ khác, ví dụ **Apache TinkerPop/Gremlin** thường được dùng với mô hình đồ thị thuộc tính qua các hệ hỗ trợ Gremlin; **RDF** dùng bộ ba subject–predicate–object và thường được truy vấn bằng **SPARQL**. Những hệ này không có cùng ngữ nghĩa và cú pháp với Neo4j/Cypher, dù đều xử lý dữ liệu có quan hệ.

**Graph DBMS** cũng không bắt buộc tốt hơn cơ sở dữ liệu quan hệ cho mọi workload. Cần xét loại liên kết, độ sâu duyệt, tần suất cập nhật, kích thước và các ràng buộc nghiệp vụ. Mô hình đồ thị phát huy giá trị khi việc **đi theo kết nối** là thao tác thường xuyên, chứ không chỉ vì hệ thống có khóa ngoại hoặc nhiều bảng.

## 2. Property graph biểu diễn dữ liệu ra sao?

Mô hình **labeled property graph** của Neo4j gồm:

- **Node (đỉnh):** thường đại diện một thực thể, chẳng hạn học viên hoặc khóa học.
- **Label (nhãn node):** phân loại node, ví dụ `:Student`, `:Course`, `:Topic`. Một node có thể có nhiều label.
- **Relationship (cạnh có hướng):** nối **hai node** với một loại quan hệ, chẳng hạn `:ENROLLED_IN`, `:COVERS` hay `:PREREQUISITE_OF`.
- **Relationship type (loại cạnh):** diễn tả ý nghĩa mối liên hệ; quan hệ có hướng nguồn–đích.
- **Property (thuộc tính):** cặp khóa–giá trị trên node hoặc relationship, chẳng hạn `studentId`, `title`, `status`, `enrolledAt`.
- **Path (đường đi):** chuỗi node và relationship nối tiếp nhau, có thể dùng trong truy vấn điều kiện tiên quyết hoặc mạng liên kết.

Ký hiệu Cypher cơ bản:

~~~cypher
(s:Student {studentId: 'U1', name: 'An'})
       -[:ENROLLED_IN {status: 'COMPLETED'}]->
(c:Course {courseId: 'C1', title: 'Java căn bản'})
~~~

Ở đây:

1. `(s:Student {...})` là một node có label `Student` và các property.
2. `-[:ENROLLED_IN {...}]->` là một relationship **đi từ Student đến Course**, có property `status`.
3. `(c:Course {...})` là node đích.

### Hướng của relationship có ý nghĩa gì?

Ta quy ước:

~~~text
(Student)-[:ENROLLED_IN]->(Course)
(Course)-[:COVERS]->(Topic)
(CourseA)-[:PREREQUISITE_OF]->(CourseB)
(StudentA)-[:FOLLOWS]->(StudentB)
~~~

`(CourseA)-[:PREREQUISITE_OF]->(CourseB)` nghĩa là **CourseA phải được học trước CourseB**. Nếu muốn tìm khóa tiên quyết của `CourseB`, truy vấn phải đi **ngược hướng cạnh** từ B về A.

Không có quy tắc bắt buộc mọi graph DBMS phải đặt cạnh tiên quyết theo hướng này. Đây là **hợp đồng mô hình hóa của ví dụ**. Nếu đổi hướng mà không đổi truy vấn, kết quả có thể bị đảo nghĩa.

### Thuộc tính node/relationship khác một tài liệu JSON tùy ý

Neo4j lưu các property thuộc kiểu mà hệ quản trị hỗ trợ. Không nên mặc định có thể lưu một object JSON lồng nhiều cấp trực tiếp làm giá trị property theo cùng cách document DBMS lưu tài liệu. Với cấu trúc lồng nhau, ta có thể cân nhắc biểu diễn thành các node/relationship, chuyển thành chuỗi JSON (khi chỉ lưu như payload), hoặc sử dụng mô hình lưu trữ khác.

**Nhãn và loại cạnh** giúp mô hình hóa ý nghĩa liên kết; **property** diễn tả thông tin cụ thể của một node hoặc mối liên hệ. Chẳng hạn thời điểm đăng ký thuộc quan hệ giữa học viên và khóa học, nên có thể đặt ở `ENROLLED_IN.enrolledAt`.

## 3. Bài toán: đồ thị cho hệ thống học trực tuyến

Hãy xây một đồ thị nhỏ với ba nhóm thực thể:

| Loại node | Định danh | Thuộc tính chính |
| --- | --- | --- |
| `Student` | `studentId` | `name` |
| `Course` | `courseId` | `title`, `level` |
| `Topic` | `topicId` | `name` |

Và bốn loại relationship:

| Loại relationship | Hướng | Ý nghĩa |
| --- | --- | --- |
| `ENROLLED_IN` | Student → Course | Học viên đăng ký khóa học; có `status`, `enrolledAt` |
| `COVERS` | Course → Topic | Khóa học đề cập tới một chủ đề |
| `PREREQUISITE_OF` | Course → Course | Khóa nguồn là tiên quyết của khóa đích |
| `FOLLOWS` | Student → Student | Một học viên theo dõi học viên khác |

Dữ liệu mẫu:

**Học viên**

| ID | Tên |
| --- | --- |
| U1 | An |
| U2 | Bình |
| U3 | Chi |

**Khóa học**

| ID | Tên | Cấp độ |
| --- | --- | --- |
| C1 | Java căn bản | beginner |
| C2 | Spring Boot | intermediate |
| C3 | Neo4j thực hành | intermediate |
| C4 | Nhập môn NoSQL | beginner |
| C5 | Đồ thị nâng cao | advanced |

**Chủ đề**

| ID | Tên |
| --- | --- |
| T1 | Java |
| T2 | Spring |
| T3 | NoSQL |
| T4 | Graph |

Các quan hệ nghiệp vụ:

~~~text
Student:
  An (U1)   ── ENROLLED_IN, COMPLETED ──> Java căn bản (C1)
  An (U1)   ── ENROLLED_IN, COMPLETED ──> Nhập môn NoSQL (C4)
  Bình (U2) ── ENROLLED_IN, COMPLETED ──> Neo4j thực hành (C3)
  Chi (U3)  ── ENROLLED_IN, IN_PROGRESS ──> Spring Boot (C2)

Khóa học và chủ đề:
  C1 ── COVERS ──> Java (T1)
  C2 ── COVERS ──> Java (T1), Spring (T2)
  C3 ── COVERS ──> NoSQL (T3), Graph (T4)
  C4 ── COVERS ──> NoSQL (T3)
  C5 ── COVERS ──> Graph (T4)

Tiên quyết:
  C1 ── PREREQUISITE_OF ──> C2
  C4 ── PREREQUISITE_OF ──> C3 ── PREREQUISITE_OF ──> C5

Theo dõi:
  U1 ── FOLLOWS ──> U2 ── FOLLOWS ──> U3
~~~

Đồ thị này nhỏ để học cú pháp, nhưng có đủ các tình huống thực tế: quan hệ một–nhiều, nhiều–nhiều, liên kết giữa hai node cùng loại và đường đi qua nhiều bước.

## 4. Khởi tạo dữ liệu bằng Cypher

Các câu lệnh dưới đây được thiết kế để chạy trên một database Neo4j mà bạn được phép sửa dữ liệu. Có thể chạy từng khối trong Neo4j Browser, Cypher Shell hoặc công cụ Cypher tương thích.

### 4.1. Tạo ràng buộc định danh

Trước khi dùng `MERGE` theo ID nghiệp vụ, nên khai báo các ràng buộc duy nhất:

~~~cypher
CREATE CONSTRAINT student_id_unique IF NOT EXISTS
FOR (s:Student)
REQUIRE s.studentId IS UNIQUE;

CREATE CONSTRAINT course_id_unique IF NOT EXISTS
FOR (c:Course)
REQUIRE c.courseId IS UNIQUE;

CREATE CONSTRAINT topic_id_unique IF NOT EXISTS
FOR (t:Topic)
REQUIRE t.topicId IS UNIQUE;
~~~

Đây là cú pháp ràng buộc **Neo4j Cypher**. Các ràng buộc nói rằng giá trị ID được dùng phải là duy nhất cho các node có label tương ứng trong phạm vi database. Trong hệ thống thực tế, cần quyết định cách xử lý ID thiếu và kiểm tra khả năng áp dụng schema/constraint theo phiên bản, cấu hình Neo4j đang dùng.

Ràng buộc này giúp giữ tính toàn vẹn danh tính của node; nó **không tự bảo đảm** mọi học viên chỉ có đúng một relationship `ENROLLED_IN` tới mỗi khóa, không bảo đảm không có chu trình tiên quyết và không tự xác nhận quyền đăng ký.

### 4.2. Tạo các node

Thay vì viết từng lệnh `CREATE`, có thể dùng `UNWIND` để chuyển các phần tử trong danh sách thành từng dòng đầu vào:

~~~cypher
UNWIND [
  {studentId: 'U1', name: 'An'},
  {studentId: 'U2', name: 'Bình'},
  {studentId: 'U3', name: 'Chi'}
] AS row
MERGE (s:Student {studentId: row.studentId})
SET s.name = row.name;

UNWIND [
  {courseId: 'C1', title: 'Java căn bản', level: 'beginner'},
  {courseId: 'C2', title: 'Spring Boot', level: 'intermediate'},
  {courseId: 'C3', title: 'Neo4j thực hành', level: 'intermediate'},
  {courseId: 'C4', title: 'Nhập môn NoSQL', level: 'beginner'},
  {courseId: 'C5', title: 'Đồ thị nâng cao', level: 'advanced'}
] AS row
MERGE (c:Course {courseId: row.courseId})
SET c.title = row.title,
    c.level = row.level;

UNWIND [
  {topicId: 'T1', name: 'Java'},
  {topicId: 'T2', name: 'Spring'},
  {topicId: 'T3', name: 'NoSQL'},
  {topicId: 'T4', name: 'Graph'}
] AS row
MERGE (t:Topic {topicId: row.topicId})
SET t.name = row.name;
~~~

**`MERGE`** tìm một mẫu phù hợp, và tạo mẫu đó nếu chưa có. Khi dùng cùng ID với constraint duy nhất, việc chạy lại các khối tạo node thường giúp tránh tạo thêm node trùng định danh. Phần `SET` gán lại tên hoặc level mỗi lần chạy; nếu có thay đổi thật ở dữ liệu hiện hành, chạy lại ví dụ có thể ghi đè giá trị. Vì vậy dữ liệu mẫu nên nằm trong môi trường học tập riêng.

**`CREATE`** luôn tạo phần tử mới mà không kiểm tra mẫu đã tồn tại theo nghĩa `MERGE`; nếu có constraint, việc tạo trùng ID sẽ báo lỗi. Chọn `CREATE` hay `MERGE` phụ thuộc nhu cầu phát sinh thực thể mới và tính idempotent của quy trình nạp.

### 4.3. Tạo quan hệ giữa khóa học và chủ đề

~~~cypher
UNWIND [
  {courseId: 'C1', topicId: 'T1'},
  {courseId: 'C2', topicId: 'T1'},
  {courseId: 'C2', topicId: 'T2'},
  {courseId: 'C3', topicId: 'T3'},
  {courseId: 'C3', topicId: 'T4'},
  {courseId: 'C4', topicId: 'T3'},
  {courseId: 'C5', topicId: 'T4'}
] AS row
MATCH (c:Course {courseId: row.courseId})
MATCH (t:Topic {topicId: row.topicId})
MERGE (c)-[:COVERS]->(t);
~~~

Ở đây:

- `MATCH` tìm node theo ID đã tạo.
- `MERGE (c)-[:COVERS]->(t)` tạo cạnh nếu chưa có cạnh cùng mẫu giữa cặp node.
- Nếu một `courseId` hoặc `topicId` không tồn tại, dòng đầu vào tương ứng không có kết quả `MATCH` và sẽ không tạo cạnh. Khi nhập dữ liệu thật, nên theo dõi và báo lỗi bản ghi không tìm thấy node đích.

### 4.4. Tạo các liên kết điều kiện tiên quyết

~~~cypher
UNWIND [
  {prerequisiteId: 'C1', courseId: 'C2'},
  {prerequisiteId: 'C4', courseId: 'C3'},
  {prerequisiteId: 'C3', courseId: 'C5'}
] AS row
MATCH (p:Course {courseId: row.prerequisiteId})
MATCH (c:Course {courseId: row.courseId})
MERGE (p)-[:PREREQUISITE_OF]->(c);
~~~

Cạnh `C4 → C3 → C5` diễn tả: muốn học **C5** phải hoàn thành **C3**, và trước C3 lại cần **C4**. Đây là một quan hệ **bắc cầu về yêu cầu nghiệp vụ**, nhưng trong dữ liệu chỉ cần lưu các cạnh trực tiếp; khi truy vấn có thể đi theo nhiều bước để suy ra điều kiện gián tiếp.

### 4.5. Tạo quan hệ đăng ký và theo dõi

~~~cypher
UNWIND [
  {studentId: 'U1', courseId: 'C1', status: 'COMPLETED'},
  {studentId: 'U1', courseId: 'C4', status: 'COMPLETED'},
  {studentId: 'U2', courseId: 'C3', status: 'COMPLETED'},
  {studentId: 'U3', courseId: 'C2', status: 'IN_PROGRESS'}
] AS row
MATCH (s:Student {studentId: row.studentId})
MATCH (c:Course {courseId: row.courseId})
MERGE (s)-[e:ENROLLED_IN]->(c)
SET e.status = row.status,
    e.enrolledAt = datetime('2026-11-01T08:00:00Z');

UNWIND [
  {followerId: 'U1', followedId: 'U2'},
  {followerId: 'U2', followedId: 'U3'}
] AS row
MATCH (a:Student {studentId: row.followerId})
MATCH (b:Student {studentId: row.followedId})
MERGE (a)-[:FOLLOWS]->(b);
~~~

`status` nằm trên quan hệ `ENROLLED_IN` vì trạng thái này mô tả **một học viên đối với một khóa học**, không phải trạng thái toàn cục của học viên hay khóa học. Một khóa có thể được một học viên hoàn thành nhưng học viên khác đang học dở.

Thời điểm `enrolledAt` cố định trong dữ liệu mẫu để ví dụ dễ tái lập. Trong ứng dụng thực tế, nên dùng thời điểm đăng ký thật và quy tắc không làm mới thời điểm đó khi chạy lại một thao tác cập nhật trạng thái.

> Lưu ý: `MERGE` thường giúp tránh tạo trùng mẫu trong các lần chạy tuần tự. Với nhiều yêu cầu ghi đồng thời, đặc biệt là uniqueness của **relationship**, chỉ dựa vào `MERGE` mà không có ràng buộc/logic giao dịch phù hợp chưa đủ để chứng minh không thể có cạnh trùng. Cần xác định đơn vị định danh của quan hệ đăng ký và thiết kế bảo đảm theo yêu cầu thực tế.

## 5. Truy vấn cơ bản: MATCH, WHERE, RETURN

Trong Cypher, cú pháp `MATCH` mô tả **mẫu đồ thị cần tìm**, còn `RETURN` chọn dữ liệu trả về. Cách đọc dễ hiểu là “tìm các node và cạnh khớp hình dạng này”.

### 5.1. Lấy các khóa học của học viên An

~~~cypher
MATCH (s:Student {studentId: 'U1'})-[e:ENROLLED_IN]->(c:Course)
RETURN s.name AS student,
       c.courseId AS courseId,
       c.title AS course,
       e.status AS status
ORDER BY courseId;
~~~

Kết quả kỳ vọng với dữ liệu mẫu:

| student | courseId | course | status |
| --- | --- | --- | --- |
| An | C1 | Java căn bản | COMPLETED |
| An | C4 | Nhập môn NoSQL | COMPLETED |

**Giải thích mẫu:** `(s:Student {...})` định vị học viên U1, `-[e:ENROLLED_IN]->` yêu cầu một cạnh đăng ký đi ra từ học viên, `(c:Course)` là khóa đích. Vì tên relationship `e` được khai báo, ta đọc được `e.status` như dữ liệu của chính lần đăng ký.

### 5.2. Tìm khóa học thuộc chủ đề NoSQL

~~~cypher
MATCH (c:Course)-[:COVERS]->(t:Topic {topicId: 'T3'})
RETURN c.courseId AS courseId, c.title AS title
ORDER BY courseId;
~~~

Kết quả kỳ vọng: **C3 — Neo4j thực hành** và **C4 — Nhập môn NoSQL**.

Đây là một liên kết nhiều–nhiều: một khóa học có thể bao phủ nhiều chủ đề; một chủ đề có thể xuất hiện ở nhiều khóa học. Mối liên hệ trở thành relationship trực tiếp, không cần xây bảng join ở tầng mô hình đồ thị.

### 5.3. Lọc thuộc tính của relationship

~~~cypher
MATCH (s:Student)-[e:ENROLLED_IN {status: 'COMPLETED'}]->(c:Course)
RETURN s.name AS student, c.title AS completedCourse
ORDER BY student, completedCourse;
~~~

Kết quả chứa những lần đăng ký có `status = 'COMPLETED'`. **Đăng ký** và **hoàn thành** là hai trạng thái khác nhau: người đang học dở như Chi có `ENROLLED_IN` nhưng không phải đã hoàn thành.

Một mẫu khác dùng `WHERE`:

~~~cypher
MATCH (c:Course)
WHERE c.level = 'beginner'
RETURN c.courseId AS id, c.title AS title
ORDER BY id;
~~~

Trong dữ liệu mẫu, `C1` và `C4` được trả về. Đây là phép lọc thuộc tính, không nhất thiết cần duyệt cạnh; graph DBMS vẫn thực hiện các truy vấn lọc thông thường.

## 6. Duyệt nhiều bước: quan hệ tiên quyết trực tiếp và gián tiếp

Đây là kiểu truy vấn khiến mô hình đồ thị dễ diễn đạt.

### 6.1. Khóa tiên quyết trực tiếp của C5

~~~cypher
MATCH (prereq:Course)-[:PREREQUISITE_OF]->
      (target:Course {courseId: 'C5'})
RETURN prereq.courseId AS prerequisiteId,
       prereq.title AS prerequisiteTitle;
~~~

Kết quả chỉ có **C3 — Neo4j thực hành** vì C3 là node nối trực tiếp vào C5.

### 6.2. Mọi khóa tiên quyết trong tối đa ba bước

~~~cypher
MATCH (prereq:Course)-[:PREREQUISITE_OF*1..3]->
      (target:Course {courseId: 'C5'})
RETURN DISTINCT
       prereq.courseId AS prerequisiteId,
       prereq.title AS prerequisiteTitle
ORDER BY prerequisiteId;
~~~

Kết quả:

| prerequisiteId | prerequisiteTitle |
| --- | --- |
| C3 | Neo4j thực hành |
| C4 | Nhập môn NoSQL |

`*1..3` là mẫu quan hệ **độ dài biến thiên** (*variable-length path*), cho phép duyệt từ 1 đến 3 cạnh `PREREQUISITE_OF` liên tiếp theo hướng chỉ định. Nếu mục tiêu là tìm khóa tiên quyết của C5, mẫu đi từ `prereq` **theo chiều đi vào target**.

Một cách khác là duyệt ngược từ C5:

~~~cypher
MATCH (target:Course {courseId: 'C5'})
      <-[:PREREQUISITE_OF*1..3]-(prereq:Course)
RETURN DISTINCT prereq.courseId AS prerequisiteId
ORDER BY prerequisiteId;
~~~

Hai truy vấn diễn tả cùng ý nghĩa với quy ước hướng cạnh của ví dụ.

### 6.3. Xem đường đi cụ thể

~~~cypher
MATCH p = (start:Course {courseId: 'C4'})
          -[:PREREQUISITE_OF*1..3]->
          (nextCourse:Course)
RETURN [n IN nodes(p) | n.courseId] AS coursePath,
       length(p) AS relationHops
ORDER BY relationHops, coursePath;
~~~

Các đường đi mẫu:

~~~text
[C4, C3]      → 1 relationship
[C4, C3, C5]  → 2 relationships
~~~

`nodes(p)` trả danh sách node trên đường đi; biểu thức danh sách lấy `courseId` của từng node. `length(p)` là số relationship của đường đi, **không phải** số node.

### Giới hạn độ sâu để kiểm soát chi phí

Truy vấn đường đi có độ dài biến thiên dễ phát sinh nhiều kết quả nếu graph lớn, có rất nhiều nhánh hoặc chu trình. Hãy:

- Giới hạn độ dài hợp lý như `*1..3` hoặc `*1..5` nếu nghiệp vụ cho phép.
- Định vị node bắt đầu bằng ID có index/constraint phù hợp.
- Giới hạn số kết quả/đường đi cần trả và tránh đưa toàn bộ path lớn lên ứng dụng.
- Xác định có cho phép chu trình tiên quyết không; với khóa học, thường **không được** vì A không thể vừa là tiên quyết trực tiếp/gián tiếp của chính A.

`DISTINCT` loại dòng kết quả trùng, nhưng **không loại chi phí đã phát sinh khi duyệt** các đường đi trùng. Nếu quan hệ tiên quyết rất sâu hoặc có nhiều nhánh, cần đo kế hoạch thực thi và cân nhắc mô hình hỗ trợ.

## 7. Truy vấn qua hai loại relationship để gợi ý khóa học

Giả sử muốn gợi ý cho học viên **những khóa chưa đăng ký nhưng có chủ đề trùng với các khóa đã hoàn thành**.

Mẫu đồ thị:

~~~text
(Student)-[:ENROLLED_IN {status:'COMPLETED'}]->
   (CompletedCourse)-[:COVERS]->
      (Topic)<-[:COVERS]-
         (CandidateCourse)
~~~

Cypher:

~~~cypher
MATCH (s:Student {studentId: 'U1'})
      -[:ENROLLED_IN {status: 'COMPLETED'}]->
      (done:Course)
      -[:COVERS]->
      (t:Topic)
      <-[:COVERS]-
      (candidate:Course)
WHERE NOT EXISTS {
  MATCH (s)-[:ENROLLED_IN]->(candidate)
}
RETURN candidate.courseId AS courseId,
       candidate.title AS title,
       count(DISTINCT t) AS sharedTopicCount
ORDER BY sharedTopicCount DESC, courseId
LIMIT 5;
~~~

Với dữ liệu mẫu, An đã hoàn thành C1 và C4:

- C1 bao phủ chủ đề Java; C2 cũng bao phủ Java.
- C4 bao phủ chủ đề NoSQL; C3 cũng bao phủ NoSQL.

Do đó, kết quả gợi ý theo **chủ đề trùng** gồm **C2** và **C3** (cùng số chủ đề chung là 1; sắp tiếp theo `courseId`).

Điểm cần phân biệt:

- Truy vấn **không gợi ý khóa đã đăng ký** vì có điều kiện `NOT EXISTS`.
- `count(DISTINCT t)` đếm số chủ đề chung khác nhau, tránh nhân số lần do các đường đi tạo ra.
- Điểm số theo chủ đề chung chỉ là một **tiêu chí gợi ý đơn giản**. Đề xuất khóa học có thể còn cần điều kiện tiên quyết, trình độ, thời lượng, ngôn ngữ, giới hạn quyền truy cập và trạng thái xuất bản.

Đây là một cách viết mạch lạc bằng pattern graph. Một hệ quan hệ cũng có thể thực hiện bằng các phép JOIN và truy vấn phù hợp, nhưng phải khai báo những mối nối bảng/khóa trung gian thay vì mô tả đường đi trực tiếp bằng relationship.

## 8. Kiểm tra người học có thiếu điều kiện tiên quyết không

Một chức năng khác là kiểm tra **tất cả điều kiện tiên quyết gián tiếp** của khóa mong muốn đã được hoàn thành hay chưa.

Ta tạm giới hạn độ sâu tiên quyết tối đa 5 bước vì đây là dữ liệu mẫu:

~~~cypher
MATCH (s:Student {studentId: 'U1'})
MATCH (target:Course {courseId: 'C5'})
OPTIONAL MATCH (prereq:Course)
               -[:PREREQUISITE_OF*1..5]->
               (target)
WITH s, target, collect(DISTINCT prereq.courseId) AS requiredIds
OPTIONAL MATCH (s)-[:ENROLLED_IN {status: 'COMPLETED'}]->(done:Course)
WITH target, requiredIds, collect(DISTINCT done.courseId) AS completedIds
RETURN target.courseId AS targetId,
       requiredIds,
       completedIds,
       [id IN requiredIds WHERE NOT (id IN completedIds)] AS missingIds;
~~~

Với dữ liệu mẫu:

- Khóa C5 yêu cầu **C3** và gián tiếp **C4**.
- An đã hoàn thành **C1** và **C4**, nhưng chưa hoàn thành C3.
- Kết quả `missingIds` chứa **C3**. Thứ tự phần tử trong các danh sách thu thập không nên được dùng làm hợp đồng nếu truy vấn không chủ động sắp xếp.

`OPTIONAL MATCH` tương tự phép kết hợp tùy chọn: nếu không có quan hệ phù hợp, các biến mới sẽ có giá trị null để dòng dữ liệu trước đó vẫn được giữ. Khi tổng hợp bằng `collect`, cần hiểu xử lý giá trị null và các trường hợp không tồn tại node/học viên.

**Cảnh báo về phạm vi:** vì truy vấn giới hạn `*1..5`, nó chỉ chứng minh người học đủ điều kiện theo chuỗi tiên quyết tối đa 5 bước. Nếu nghiệp vụ cho phép chuỗi dài hơn, phải thay độ sâu hoặc dùng cơ chế bảo đảm bao phủ đầy đủ. Cũng phải ngăn chu trình và xác định rõ mốc “COMPLETED” có hiệu lực.

## 9. Truy vấn quan hệ xã hội và đường đi

Với graph người học:

~~~text
An (U1) ──FOLLOWS──> Bình (U2) ──FOLLOWS──> Chi (U3)
~~~

### 9.1. Ai là người mà An theo dõi trực tiếp?

~~~cypher
MATCH (a:Student {studentId: 'U1'})
      -[:FOLLOWS]->
      (b:Student)
RETURN b.studentId AS followedId, b.name AS followedName;
~~~

Kết quả: **U2 — Bình**.

### 9.2. Người được theo dõi trong một hoặc hai bước

~~~cypher
MATCH (a:Student {studentId: 'U1'})
      -[:FOLLOWS*1..2]->
      (b:Student)
WHERE b <> a
RETURN DISTINCT b.studentId AS studentId, b.name AS name
ORDER BY studentId;
~~~

Kết quả: **U2 — Bình**, **U3 — Chi**.

Đây chỉ là một ví dụ duyệt mạng quan hệ. Trong graph lớn, node có hàng triệu cạnh (**supernode**) có thể khiến một phép duyệt ngắn vẫn chạm lượng dữ liệu khổng lồ. Giới hạn số bước là cần thiết nhưng chưa đủ; điều kiện lọc, mức độ phân nhánh và số kết quả trung gian cũng phải được xem xét.

### 9.3. Tìm đường đi và ý nghĩa của “ngắn nhất”

Với một mạng quan hệ, có thể hỏi “giữa hai người có một đường đi qua tối đa vài bước không?”, hoặc “đường đi nào có số cạnh ít nhất?”. Tuy nhiên, “đường đi ngắn nhất theo số cạnh” khác với “đường đi có chi phí thấp nhất” khi mỗi cạnh có trọng số.

Ví dụ nếu quan hệ `FOLLOWS` chỉ có ý nghĩa từ người A theo dõi người B, truy vấn theo hướng ngược có ý nghĩa khác. Khi chọn thuật toán đường đi, cần xác định **hướng cạnh, trọng số, loại quan hệ và giới hạn độ dài** trước khi chọn hàm hay thư viện thuật toán.

Neo4j có ngôn ngữ Cypher để match đường đi; các bài toán như centrality, community detection hoặc shortest path theo trọng số tùy loại có thể cần thuật toán/thành phần phân tích đồ thị phù hợp. Không nên coi mọi phép phân tích đồ thị phức tạp đều chạy nhanh chỉ vì dữ liệu đã lưu trong graph DBMS.

## 10. Khi nào nên đặt dữ liệu ở node, relationship hay property?

Đây là quyết định thiết kế quan trọng nhất khi chuyển bài toán nghiệp vụ sang property graph.

| Dữ liệu | Cách biểu diễn có thể chọn | Lý do |
| --- | --- | --- |
| Học viên | Node `Student` | Có danh tính riêng, nhiều quan hệ với khóa học/người khác |
| Khóa học | Node `Course` | Có thể được nhiều người đăng ký và nhiều khóa khác tham chiếu |
| Chủ đề | Node `Topic` | Được nhiều khóa cùng sử dụng và có thể có quan hệ giữa các chủ đề |
| Trạng thái đăng ký | Property trên `ENROLLED_IN` | Phụ thuộc vào **cặp** học viên–khóa học |
| Thời điểm đăng ký | Property trên `ENROLLED_IN` | Thuộc về quan hệ đăng ký |
| Tiêu đề khóa học | Property trên `Course` | Mô tả khóa học |
| Điều kiện tiên quyết | Relationship `PREREQUISITE_OF` | Cần đi qua liên kết theo nhiều bước |

Tuy nhiên, nếu **một học viên có thể đăng ký lại cùng khóa nhiều lần**, chỉ một relationship `ENROLLED_IN` giữa hai node có thể không đủ để ghi lịch sử các lần tham gia. Có thể tạo node `Enrollment` riêng:

~~~text
(Student)-[:HAS_ENROLLMENT]->(Enrollment)
(Enrollment)-[:FOR_COURSE]->(Course)

Enrollment:
  enrollmentId
  startedAt
  completedAt
  attemptNumber
  status
~~~

Mỗi `Enrollment` khi đó có định danh, vòng đời và lịch sử riêng. Đây là ví dụ cho nguyên tắc: **mối quan hệ đơn giản có thể là một cạnh; mối quan hệ có đời sống nghiệp vụ riêng có thể cần thành thực thể/node**.

Tương tự, không nhất thiết biến mọi string hoặc trạng thái thành node. Nếu `level = 'beginner'` chỉ là một thuộc tính đơn giản dùng để lọc, giữ nó dưới dạng property của `Course` có thể dễ hiểu hơn tạo node `Level` cho mọi giá trị.

## 11. Chỉ mục và constraint: bắt đầu từ đúng node

Mô hình đồ thị không loại bỏ nhu cầu lập chỉ mục. Một truy vấn thường có hai pha:

~~~text
Tìm node bắt đầu qua label/property
                   │
              Index/constraint
                   ▼
          Node có ID đã biết
                   │
              Duyệt cạnh
                   ▼
           Các node liên quan
~~~

Ví dụ tìm `Student` theo `studentId`, rồi đi qua cạnh `ENROLLED_IN`. Constraint duy nhất trên `studentId` giúp có đường truy cập thích hợp để tìm node bắt đầu. Sau đó graph engine duyệt theo các relationship được lưu.

Các loại index cụ thể (range, text, full-text, point, vector, v.v.) và cấu hình có thể khác nhau theo phiên bản Neo4j. Chúng không làm biến mọi truy vấn thành một lần đọc hằng số; những truy vấn bắt đầu từ node có quá nhiều cạnh vẫn có thể đắt đỏ.

### Xem kế hoạch thực thi

Với một truy vấn đọc, có thể xem kế hoạch bằng:

~~~cypher
EXPLAIN
MATCH (s:Student {studentId: 'U1'})-[:ENROLLED_IN]->(c:Course)
RETURN c.title AS title;
~~~

`EXPLAIN` mô tả kế hoạch dự kiến mà không thực thi truy vấn. `PROFILE` **thực thi** truy vấn và cung cấp thống kê kế hoạch; nên dùng với truy vấn đọc và môi trường phù hợp, vì nếu profile một truy vấn ghi thì phần thay đổi cũng được thực hiện.

Khi đánh giá hiệu năng, cần quan sát:

- DBMS có định vị node ban đầu bằng index/constraint hay quét nhiều node?
- Một bước duyệt qua bao nhiêu cạnh, đặc biệt với node bậc lớn?
- Có bao nhiêu kết quả trung gian trước `DISTINCT`, `ORDER BY` và `LIMIT`?
- Truy vấn nhiều bước có giới hạn độ sâu hợp lý không?
- Khối lượng dữ liệu, bộ nhớ, cache và độ trễ có đại diện cho môi trường thực tế không?

**Giới hạn `LIMIT 10` không bảo đảm hệ thống chỉ duyệt 10 cạnh**; tùy truy vấn, DBMS có thể phải tạo hoặc sắp xếp nhiều kết quả trung gian mới trả được 10 dòng.

## 12. Tham số hóa truy vấn và kết nối từ ứng dụng

Trong ứng dụng thật, ID học viên được nhập từ request. Thay vì ghép chuỗi Cypher, hãy **dùng tham số**:

~~~cypher
MATCH (s:Student {studentId: $studentId})
      -[:ENROLLED_IN]->
      (c:Course)
RETURN c.courseId AS id, c.title AS title
ORDER BY id;
~~~

Khi gọi qua Neo4j Driver, ứng dụng truyền tham số `studentId = "U1"` dưới dạng dữ liệu riêng. Điều này tránh việc nội dung ID bị diễn giải thành một phần cú pháp truy vấn, giúp quản lý kiểu đầu vào và có thể hỗ trợ tái sử dụng kế hoạch thực thi.

Ví dụ minh họa bằng pseudocode theo phong cách API:

~~~text
studentId = authenticatedRequest.studentId

query = """
MATCH (s:Student {studentId: $studentId})
      -[:ENROLLED_IN]->(c:Course)
RETURN c.courseId AS id, c.title AS title
"""

rows = neo4jDriver.runReadQuery(
  query,
  parameters = { studentId: studentId }
)

return rows
~~~

Đây là **pseudocode kiến trúc**, không phải tên hàm chuẩn của mọi phiên bản Neo4j Driver. Ứng dụng cần chọn driver chính thức tương ứng ngôn ngữ lập trình, quản lý kết nối/session/transaction và xử lý timeout hoặc retry theo đúng API.

Ngoài việc tham số hóa:

1. **Không tin ID người dùng do client tự gửi** nếu tài nguyên cần giới hạn theo người đăng nhập; phải xác thực và kiểm tra quyền trước khi truy vấn.
2. **Không tự động cho client gửi Cypher tùy ý** vào một endpoint có quyền ghi dữ liệu.
3. **Giới hạn truy vấn nhập từ bên ngoài** về độ sâu, loại relationship, số kết quả, timeout và lượng tài nguyên theo chính sách ứng dụng.
4. **Dùng tài khoản DBMS có quyền tối thiểu** theo nhu cầu đọc/ghi thực tế.

Cypher cũng có cú pháp tạo label/type động trong một số phiên bản, nhưng việc chọn loại cạnh, label và mẫu truy vấn từ dữ liệu người dùng cần kiểm soát chặt chẽ. Không coi tham số hóa giá trị là đủ để bảo vệ mọi thành phần động của một truy vấn.

## 13. Giao dịch và tính nhất quán của một thao tác đồ thị

Hãy xét yêu cầu: “Học viên U1 đăng ký khóa C3 nếu khóa tồn tại và chưa có đăng ký trùng”. Thao tác không chỉ là thêm cạnh; còn cần:

- Xác định học viên và khóa học thật sự tồn tại.
- Kiểm tra quyền truy cập khóa.
- Kiểm tra điều kiện tiên quyết và khả năng đăng ký lại.
- Quyết định có cho phép nhiều lần đăng ký/attempt hay không.
- Ghi quan hệ hoặc node `Enrollment` với trạng thái đúng.

Một ví dụ ghi quan hệ theo mẫu:

~~~cypher
MATCH (s:Student {studentId: $studentId})
MATCH (c:Course {courseId: $courseId})
MERGE (s)-[e:ENROLLED_IN]->(c)
ON CREATE SET
  e.status = 'IN_PROGRESS',
  e.enrolledAt = datetime();
~~~

`ON CREATE SET` chỉ đặt property khi relationship vừa được tạo qua `MERGE`, giúp tránh tự đổi thời điểm đăng ký trong lần chạy lại tuần tự. Nhưng thao tác này **không thực thi kiểm tra điều kiện tiên quyết**, không tự bảo đảm quyền, cũng không tự ngăn mọi cạnh trùng trong tình huống ghi đồng thời nếu thiếu thiết kế bảo đảm tương ứng.

Neo4j hỗ trợ transaction để phối hợp nhiều thay đổi trong phạm vi bảo đảm của DBMS. Khi hệ thống phải ghi sang dịch vụ ngoài (ví dụ gửi email, cập nhật một DBMS khác), transaction Neo4j **không tự động** bao trùm các tác động ngoài đó. Cần thiết kế phát sự kiện, retry và tính idempotent theo kiến trúc hệ thống.

### Xóa node hoặc xóa quan hệ

Cypher phân biệt:

~~~cypher
MATCH (a:Student {studentId: 'U1'})-[r:FOLLOWS]->
      (b:Student {studentId: 'U2'})
DELETE r;
~~~

Lệnh này chỉ xóa mối quan hệ theo dõi từ U1 đến U2; **hai node học viên vẫn tồn tại**.

Khi xóa node còn relationship, thao tác xóa đơn giản có thể không thành công vì còn cạnh liên kết. Neo4j có `DETACH DELETE` để xóa node cùng mọi relationship của node đó:

~~~cypher
// Chỉ minh họa cú pháp; không chạy trên dữ liệu cần giữ.
MATCH (s:Student {studentId: 'U3'})
DETACH DELETE s;
~~~

Đây là thao tác có hệ quả nghiệp vụ lớn; trong hệ thật cần cân nhắc quyền, retention, audit và trách nhiệm của các node/relationship liên quan. Với dữ liệu học tập, có thể tái tạo graph từ các lệnh tạo ban đầu.

## 14. So sánh mô hình đồ thị với cách lưu quan hệ hoặc tài liệu

Cùng bài toán học viên–khóa học–chủ đề có thể được biểu diễn bằng nhiều DBMS:

| Góc nhìn | RDBMS quan hệ | Document DBMS | Property graph DBMS |
| --- | --- | --- | --- |
| Học viên/khóa học | Bảng `students`, `courses` | Tài liệu student/course | Node `Student`, `Course` |
| Đăng ký | Bảng nối `enrollments` | Mảng hoặc tham chiếu | `ENROLLED_IN` hoặc node Enrollment |
| Chủ đề khóa học | Bảng nối `course_topics` | Mảng topicId, nhúng hoặc tham chiếu | `COVERS` giữa Course và Topic |
| Khóa tiên quyết | Bảng nối `course_prerequisites` | Danh sách ID tiên quyết | `PREREQUISITE_OF` |
| Truy vấn sâu | JOIN/CTE đệ quy hoặc truy vấn ứng dụng | Lookup, nhiều lần đọc hoặc aggregation | Path matching/traversal theo pattern |
| Điểm cần tối ưu | Join, index, ràng buộc, kế hoạch SQL | Nhúng/tham chiếu, index, kích thước tài liệu | Node bắt đầu, bậc node, số path, depth |

Ví dụ tìm khóa tiên quyết trực tiếp trong RDBMS có thể dùng `course_prerequisites(prerequisite_id, course_id)` và JOIN với bảng khóa học. Để lấy nhiều tầng, có thể sử dụng **recursive CTE** trong DBMS hỗ trợ hoặc logic ứng dụng.

Trong property graph, quan hệ này được biểu diễn trực tiếp thành cạnh, và Cypher cho phép viết một mẫu đường đi nhiều bước. Đó là **sự khác biệt trong biểu diễn và cách diễn đạt truy vấn**, không phải bằng chứng rằng mọi graph query nhanh hơn mọi SQL query.

### Trường hợp property graph đáng cân nhắc

- Các quan hệ quan trọng, nhiều loại liên kết và thường xuyên duyệt nhiều bước.
- Hệ thống gợi ý dựa trên liên kết người–sản phẩm–chủ đề.
- Quản lý kiến thức, phụ thuộc, cấu hình, mạng xã hội hoặc truy xuất nguồn gốc.
- Các câu hỏi về đường đi, hàng xóm, số bước và kết nối liên hệ.

### Trường hợp cần cân nhắc kỹ

- Truy vấn chủ yếu là đọc một bản ghi theo ID hoặc tính tổng trên bảng lớn.
- Phân tích khối lượng rất lớn cần quét, lọc, tổng hợp theo thời gian.
- Một số node có số cạnh cực lớn và mọi truy vấn phải mở rộng qua chúng.
- Nghiệp vụ cần nhiều thao tác quan hệ nghiêm ngặt, bộ công cụ báo cáo hoặc SQL đã được tối ưu tốt.

Có thể **kết hợp công nghệ**: RDBMS giữ trạng thái giao dịch, graph DBMS giữ projection liên kết cho truy vấn gợi ý. Trong cách này cần xác định nguồn dữ liệu có thẩm quyền và cách đồng bộ graph khi dữ liệu nguồn thay đổi.

## 15. Những lỗi mô hình hóa và truy vấn thường gặp

| Sai lầm | Hệ quả | Hướng giải quyết |
| --- | --- | --- |
| Đảo hướng `PREREQUISITE_OF` giữa các service | Tìm sai khóa tiên quyết hoặc khóa phụ thuộc | Định nghĩa hướng cạnh và kiểm tra bằng ví dụ cụ thể |
| Dùng một property string `"C1,C2"` thay vì quan hệ khi cần duyệt phụ thuộc | Khó truy vấn nhiều bước, khó kiểm tra tham chiếu | Tạo relationship/node phù hợp với vòng đời dữ liệu |
| Coi `ENROLLED_IN` đồng nghĩa đã hoàn thành | Gợi ý sai điều kiện tiên quyết | Lưu `status`/`completedAt` rõ ràng |
| Mọi truy vấn bắt đầu từ toàn bộ node | Quét rộng, nhiều kết quả trung gian | Bắt đầu từ label + ID/index chọn lọc |
| Duyệt `*` không giới hạn trong graph lớn | Bùng nổ đường đi và chi phí | Giới hạn độ sâu, hướng, loại cạnh, phạm vi kết quả |
| Dùng `LIMIT` rồi cho rằng traversal đã ít | Có thể vẫn tạo nhiều kết quả trước khi giới hạn | Đọc kế hoạch `EXPLAIN/PROFILE` |
| Dùng `MERGE` như bảo đảm uniqueness cho mọi cạnh | Có thể có quan hệ trùng khi thao tác cạnh tranh | Định danh/constraint/transaction hoặc mô hình Enrollment |
| Dùng ID nội bộ của DBMS làm business ID | Khó giữ định danh ổn định xuyên import/migration | Có ID nghiệp vụ riêng với constraint |
| Lưu mọi dữ liệu lồng nhau thành property tùy ý | Khó biểu diễn cấu trúc và quản lý kiểu | Xem kiểu property được hỗ trợ; tạo node hoặc dịch vụ lưu trữ tương ứng |
| Xóa node mà không xét quan hệ | Mất dữ liệu liên kết ngoài dự kiến | Quy trình xóa, audit, retention, thao tác rõ phạm vi |
| Dùng graph cho mọi bài toán chỉ vì có relationship | Tăng chi phí vận hành mà ít lợi ích | Chọn DBMS theo query/workload thực tế |

## 16. Bài tập tự thực hành với đồ thị mẫu

### Bài 1 — Nhận diện node, label và relationship

Với câu:

~~~cypher
MATCH (s:Student)-[e:ENROLLED_IN]->(c:Course)
RETURN s, e, c;
~~~

Hãy giải thích `s`, `e`, `c` đại diện cho gì, hướng mũi tên biểu diễn ý nghĩa nào, và tại sao `e.status` có thể khác nhau với từng cặp học viên–khóa học.

**Gợi ý:** `s` và `c` là node, `e` là relationship. Trạng thái nằm ở lần đăng ký, không thuộc toàn bộ khóa học.

### Bài 2 — Viết truy vấn chủ đề

Viết Cypher tìm các khóa bao phủ chủ đề `T4` và trả `courseId`, `title`. Với dữ liệu mẫu, những khóa nào được trả về?

**Gợi ý:** dùng `(c:Course)-[:COVERS]->(t:Topic {topicId: 'T4'})`. Kết quả có C3 và C5.

### Bài 3 — Phân biệt quan hệ trực tiếp và gián tiếp

Khóa C4 là tiên quyết trực tiếp hay gián tiếp của C5? Viết truy vấn dùng `*1..3` để tìm và lý giải cách đếm số cạnh.

**Gợi ý:** C4 là tiên quyết gián tiếp qua C3; đường đi C4 → C3 → C5 có 2 cạnh.

### Bài 4 — Gợi ý khóa học nhưng không bỏ qua điều kiện tiên quyết

Truy vấn chủ đề chung gợi ý C3 cho An. Vì sao việc đó chưa đủ để xác nhận An được phép đăng ký C3? Trong dữ liệu mẫu, An đã hoàn thành những khóa nào và có đáp ứng điều kiện trực tiếp của C3 không?

**Gợi ý:** phải kiểm tra `PREREQUISITE_OF`. C4 là điều kiện tiên quyết của C3, và An đã hoàn thành C4 nên đáp ứng điều kiện này theo dữ liệu mẫu.

### Bài 5 — Đăng ký lại một khóa học

Giả sử học viên được phép học lại cùng khóa ba lần. Mỗi lần có `attemptNumber`, thời điểm và kết quả riêng. Nên giữ một `ENROLLED_IN` hay tạo một node `Enrollment` riêng cho từng lần?

**Gợi ý:** node Enrollment có định danh riêng giúp mô tả vòng đời mỗi lần tham gia, thay vì ghi đè trạng thái duy nhất của cạnh ban đầu.

### Bài 6 — Phân tích kế hoạch

So sánh:

~~~cypher
EXPLAIN
MATCH (s:Student {studentId: 'U1'})-[:FOLLOWS*1..2]->(other)
RETURN other;
~~~

với:

~~~cypher
EXPLAIN
MATCH (s:Student)-[:FOLLOWS*1..2]->(other)
RETURN other;
~~~

Truy vấn nào có cơ hội giới hạn node bắt đầu tốt hơn? Vì sao vẫn cần đo khi dữ liệu thực lớn?

**Gợi ý:** truy vấn có `studentId = 'U1'` định vị một node cụ thể hơn; tổng chi phí còn phụ thuộc số cạnh và số đường đi từ node đó.

## 17. Checklist thiết kế trước khi chọn Neo4j

Một tài liệu thiết kế graph ngắn có thể nêu:

~~~yaml
domain: Learning Platform
graphModel: Labeled Property Graph
dbmsExample: Neo4j
queryLanguage: Cypher
nodeLabels:
  - Student
  - Course
  - Topic
relationshipTypes:
  - "Student -ENROLLED_IN-> Course"
  - "Course -COVERS-> Topic"
  - "Course -PREREQUISITE_OF-> Course"
  - "Student -FOLLOWS-> Student"
businessIds:
  Student: studentId
  Course: courseId
  Topic: topicId
criticalQueries:
  - "Get courses enrolled by student"
  - "Find direct and transitive prerequisites"
  - "Recommend courses via shared topics"
  - "Explore student follow connections"
constraints:
  - "Unique business ID per node label"
  - "No prerequisite cycles according to business rules"
  - "Define whether repeated enrollment is allowed"
queryLimits:
  - "Bound variable-length paths"
  - "Limit pages and concurrent graph requests"
consistency:
  - "Specify which dataset is authoritative"
  - "Coordinate downstream projections when applicable"
~~~

Đây là **mẫu đặc tả thiết kế**, không phải cấu hình có thể nạp trực tiếp vào Neo4j. Các quy tắc không có constraint tương ứng cần được thực thi qua ứng dụng hoặc cơ chế phù hợp và được kiểm chứng bằng dữ liệu, transaction và truy vấn thực tế.

## 18. Ghi nhớ

Ví dụ Neo4j cho thấy **property graph** biểu diễn dữ liệu thành node, relationship và property; **Cypher** mô tả những mẫu liên kết cần tìm bằng cú pháp trực quan; còn **Neo4j** là DBMS lưu trữ, lập chỉ mục và thực thi các truy vấn đó.

Ba nguyên tắc quan trọng khi thiết kế:

1. **Mô hình hóa mối liên hệ theo ý nghĩa nghiệp vụ:** chọn đúng node, loại relationship, hướng cạnh và thuộc tính của từng đối tượng.
2. **Thiết kế từ câu hỏi cần trả lời:** tra node bằng khóa ổn định, duyệt quan hệ đúng chiều, đặt giới hạn độ sâu và cân nhắc số lượng đường đi.
3. **Đánh giá dữ liệu và vận hành thật:** constraint, cập nhật đồng thời, bảo mật, node có quá nhiều cạnh, kế hoạch truy vấn và trách nhiệm dữ liệu nguồn.

Khi liên kết là trọng tâm của bài toán, mô hình đồ thị cùng ngôn ngữ Cypher giúp diễn đạt rõ những phép duyệt nhiều bước. Giá trị thực tế chỉ được xác nhận khi cách mô hình hóa đó đáp ứng đúng **truy vấn, ràng buộc và tải vận hành** của hệ thống.
