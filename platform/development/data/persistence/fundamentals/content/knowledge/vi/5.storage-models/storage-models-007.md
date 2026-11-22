# Mô hình đồ thị và truy cập theo quan hệ

## 1. Khi nào dữ liệu nên được nhìn như một đồ thị?

Trong một nền tảng học Java, một khóa học có thể yêu cầu hoàn thành một hoặc nhiều khóa học khác; khóa học bắt buộc đó lại có điều kiện tiên quyết riêng. Khi người học muốn biết **toàn bộ các kiến thức cần học trước khi bắt đầu một khóa**, hệ thống phải đi qua nhiều bước liên kết thay vì chỉ đọc một bản ghi.

Trong bài toán khác, cùng một kiểu truy cập xuất hiện khi cần tìm bạn của bạn, phát hiện chuỗi giao dịch bất thường, lần theo quan hệ phụ thuộc giữa dịch vụ, hay tìm đường nối hai thực thể trong hệ thống quyền truy cập. Điểm chung là **mối liên hệ giữa các đối tượng chính là dữ liệu cần truy vấn**.

**Mô hình đồ thị (graph model)** biểu diễn thông tin bằng các **đỉnh/nút (vertices/nodes)** và **cạnh/quan hệ (edges/relationships)**. Thay vì chỉ tập trung vào thuộc tính của từng đối tượng, mô hình này cho phép biểu diễn rõ đối tượng nào kết nối với đối tượng nào, theo hướng nào và với ý nghĩa gì.

Bài học thuộc chương **Mô hình lưu trữ** của học phần **DATA_PERSISTENCE_FUNDAMENTALS**. Khi thiết kế persistence cho Java, hiểu mô hình đồ thị giúp lựa chọn cách lưu dữ liệu, truy vấn quan hệ nhiều bước, tổ chức chỉ mục và kiểm soát tính nhất quán phù hợp với nhu cầu thực tế.

Sau bài học, người học có thể:

- Nhận biết nút, cạnh, hướng cạnh, nhãn và thuộc tính trong đồ thị.
- Phân biệt đồ thị có thuộc tính và dữ liệu đồ thị kiểu RDF ở mức khái niệm.
- Thiết kế một đồ thị điều kiện tiên quyết giữa các khóa học.
- Viết truy vấn đi theo quan hệ một bước và nhiều bước; hiểu ảnh hưởng của chu trình và số nhánh.
- So sánh biểu diễn bằng graph database với bảng liên kết và truy vấn đệ quy trong cơ sở dữ liệu quan hệ.
- Ánh xạ truy vấn đồ thị vào tầng persistence Java và xác định các ràng buộc nghiệp vụ quan trọng.

## 2. Các thành phần của một đồ thị

Một đồ thị thường được ký hiệu là **G = (V, E)**, trong đó **V** là tập đỉnh và **E** là tập cạnh kết nối các đỉnh.

| Thành phần | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Node / vertex** | Một thực thể hay sự kiện có định danh | Khóa học **Java Persistence** |
| **Edge / relationship** | Mối liên hệ giữa hai nút | **Java Persistence REQUIRES SQL Căn bản** |
| **Hướng cạnh** | Chiều của quan hệ nếu đồ thị có hướng | Từ khóa học nâng cao sang khóa học cần học trước |
| **Label / type** | Phân loại nút hoặc cạnh | Nút **Course**, cạnh **REQUIRES** |
| **Property** | Thuộc tính của nút hoặc cạnh | **courseId**, **title**, **createdAt** |
| **Path** | Chuỗi nút và cạnh kết nối các điểm | Transactions → Java Persistence → SQL Căn bản |
| **Degree** | Số cạnh gắn với một nút; trong đồ thị có hướng có bậc vào và bậc ra | Số điều kiện tiên quyết trực tiếp của một khóa |

Cần phân biệt **mối quan hệ trong nghiệp vụ** với **quan hệ (relation) trong mô hình quan hệ toán học**: từ *relationship* ở đồ thị chỉ cạnh nối hai nút; còn *relation* trong relational model được biểu diễn bằng bảng. Hai mô hình có thể lưu cùng sự thật nhưng tổ chức và truy vấn theo cách khác nhau.

### 2.1. Ví dụ về đồ thị có hướng

Quy ước **A → B** nghĩa là **A yêu cầu học B trước**:

~~~mermaid
flowchart LR
    T["Giao dịch dữ liệu<br/>courseId: tx"] -->|REQUIRES| J["Java Persistence<br/>courseId: java-db"]
    J -->|REQUIRES| S["SQL căn bản<br/>courseId: sql-basics"]
    J -->|REQUIRES| M["Mô hình dữ liệu<br/>courseId: data-models"]
    M -->|REQUIRES| S
~~~

Đồ thị này nói lên ba điều:

1. **tx** có điều kiện tiên quyết trực tiếp là **java-db**.
2. **tx** có các điều kiện tiên quyết gián tiếp **sql-basics** và **data-models**.
3. Từ **tx** đến **sql-basics** có hơn một đường đi: qua **java-db → sql-basics**, hoặc qua **java-db → data-models → sql-basics**.

Khi truy vấn **danh sách khóa học bắt buộc**, ta thường muốn mỗi khóa xuất hiện **một lần**. Khi truy vấn **các chuỗi phụ thuộc**, hai đường đi khác nhau đều có ý nghĩa. Vì vậy, cần phân biệt **trả về nút có thể đến được (reachable nodes)** với **trả về mọi đường đi (paths)**.

### 2.2. Thuộc tính của cạnh

Một cạnh không chỉ cho biết hai nút có liên hệ. Trong **property graph**, cạnh còn có thể mang thuộc tính riêng, chẳng hạn:

~~~text
(:User {userId: "u1"})
  -[:MEMBER_OF {role: "editor", since: "2026-01-15"}]->
(:Team {teamId: "platform"})
~~~

Ở đây, **role** và **since** mô tả tư cách thành viên của **u1 trong team platform**, không phải thuộc tính toàn cục của user hay team. Khi một liên hệ có vòng đời, trạng thái hoặc quyền riêng, đặt thuộc tính trên cạnh có thể tự nhiên hơn việc nhét chúng vào một trong hai nút.

Tuy nhiên, nếu quan hệ trở thành một thực thể có nhiều trạng thái, lịch sử sửa đổi và các quan hệ con, có thể cần mô hình hóa nó thành một nút riêng. Thiết kế phải phản ánh đúng nghiệp vụ, không phụ thuộc duy nhất vào việc cú pháp vẽ cạnh có gọn hay không.

## 3. Những kiểu biểu diễn đồ thị phổ biến

Không phải mọi hệ thống đồ thị đều dùng cùng một cấu trúc hoặc ngôn ngữ truy vấn.

### 3.1. Property graph

**Property graph** thường gồm:

- **Nút** có nhãn và thuộc tính khóa–giá trị.
- **Cạnh** có loại, hướng, và có thể có thuộc tính.
- Nút có thể liên kết với nhiều nút khác, kể cả cùng nhãn hoặc khác nhãn.

Ví dụ một nút khóa học có thể được mô tả bằng:

~~~text
(:Course {
  courseId: "java-db",
  title: "Java Persistence",
  level: "intermediate"
})
~~~

Một số hệ quản trị graph database hỗ trợ **Cypher** hoặc các biến thể liên quan để truy vấn theo mẫu hình (pattern matching); những hệ khác dùng ngôn ngữ hoặc API riêng. Cú pháp bên dưới dùng **Neo4j/Cypher** làm ví dụ cụ thể, không phải cú pháp chung của mọi cơ sở dữ liệu đồ thị.

### 3.2. RDF và triple

Trong mô hình **RDF**, dữ liệu thường được biểu diễn thành các bộ ba **subject – predicate – object**. Chẳng hạn:

~~~turtle
@prefix ex: <https://example.org/learning/> .

ex:tx ex:requires ex:java-db .
ex:java-db ex:requires ex:sql-basics .
~~~

RDF thường sử dụng **IRI** làm định danh và **SPARQL** để truy vấn; các liên kết có thể được tiếp tục khai thác bằng ontology và suy luận ngữ nghĩa khi hệ thống hỗ trợ. RDF không đồng nhất với property graph: cách biểu diễn thuộc tính trên quan hệ, quy tắc ngữ nghĩa và công cụ truy vấn có khác biệt.

Ví dụ SPARQL lấy các điều kiện tiên quyết ở độ sâu bất kỳ:

~~~sparql
PREFIX ex: <https://example.org/learning/>

SELECT DISTINCT ?requiredCourse
WHERE {
  ex:tx ex:requires+ ?requiredCourse .
}
~~~

Dấu **+** trong *property path* yêu cầu một hoặc nhiều bước theo quan hệ **requires**. Với dữ liệu thật, phải tính đến chu trình và chi phí truy vấn; cơ chế đánh giá đường đi của SPARQL cũng không tương đương từng chi tiết với Cypher.

## 4. Thiết kế đồ thị cho khóa học và điều kiện tiên quyết

Với bài toán nền tảng học Java, ta sử dụng mô hình **property graph**:

- Nút **Course** có **courseId** và **title**.
- Cạnh **REQUIRES** hướng từ khóa học cần chuẩn bị đến khóa học tiên quyết.
- Một khóa có thể có nhiều cạnh **REQUIRES** đi ra.
- Nhiều khóa có thể cùng yêu cầu một khóa nền tảng.

### 4.1. Xác định danh tính ổn định

Không nên dùng tên hiển thị làm định danh vì tên có thể đổi hoặc không duy nhất. Thay vào đó, **courseId** là mã ổn định; **title** là thuộc tính có thể sửa.

Trong Neo4j, có thể tạo ràng buộc duy nhất cho **Course.courseId**:

~~~cypher
CREATE CONSTRAINT course_id_unique IF NOT EXISTS
FOR (c:Course)
REQUIRE c.courseId IS UNIQUE;
~~~

**Lưu ý:** Ràng buộc **UNIQUE** không có nghĩa mọi nút Course bắt buộc phải có **courseId** trong tất cả cấu hình và phiên bản Neo4j. Điều kiện bắt buộc tồn tại thuộc tính và các kiểm tra bổ sung cần được thiết kế riêng nếu nghiệp vụ yêu cầu; khả năng áp dụng một số loại constraint phụ thuộc phiên bản/phiên bản sản phẩm.

### 4.2. Tạo các nút và liên kết

Ví dụ Cypher sau sử dụng **MERGE** để tìm hoặc tạo nút theo định danh và tạo cạnh nếu mẫu liên kết chưa tồn tại:

~~~cypher
MERGE (sql:Course {courseId: 'sql-basics'})
  ON CREATE SET sql.title = 'SQL căn bản'
MERGE (model:Course {courseId: 'data-models'})
  ON CREATE SET model.title = 'Mô hình dữ liệu'
MERGE (java:Course {courseId: 'java-db'})
  ON CREATE SET java.title = 'Java Persistence'
MERGE (tx:Course {courseId: 'tx'})
  ON CREATE SET tx.title = 'Giao dịch dữ liệu'
MERGE (tx)-[:REQUIRES]->(java)
MERGE (java)-[:REQUIRES]->(sql)
MERGE (java)-[:REQUIRES]->(model)
MERGE (model)-[:REQUIRES]->(sql);
~~~

Với dữ liệu đã dựng, đồ thị có bốn nút Course và bốn cạnh REQUIRES. Thao tác **MERGE** giúp tránh tạo lại đúng mẫu đã tồn tại khi chạy lại, đặc biệt khi có ràng buộc duy nhất trên khóa định danh. Nó **không tự kiểm tra mọi quy tắc nghiệp vụ** như cấm vòng phụ thuộc giữa nhiều khóa học.

Nếu cần cập nhật tên khóa học mỗi lần chạy, **ON CREATE SET** chưa đủ vì mệnh đề này chỉ có hiệu lực với nút vừa tạo; khi đó phải chủ động dùng **SET**, phù hợp với ý đồ đồng bộ dữ liệu.

### 4.3. Phân biệt hướng và ngữ nghĩa cạnh

Trong ví dụ, **(tx)-[:REQUIRES]->(java)** là quan hệ có hướng. Nó khẳng định **tx yêu cầu java**; không có nghĩa **java yêu cầu tx**.

Một truy vấn bỏ hướng có thể phù hợp với mạng quan hệ hai chiều, nhưng có thể sai trong đồ thị điều kiện tiên quyết. Cũng không nên đặt tên cạnh chung chung như **LINKED_TO** khi ý nghĩa nghiệp vụ cần phân biệt **REQUIRES**, **DEPENDS_ON**, **BELONGS_TO** hoặc **GRANTS_ACCESS**.

## 5. Truy cập theo quan hệ: từ một bước đến nhiều bước

### 5.1. Lấy điều kiện tiên quyết trực tiếp

~~~cypher
MATCH (course:Course {courseId: $courseId})-[:REQUIRES]->(required:Course)
RETURN required.courseId AS prerequisiteId,
       required.title AS title
ORDER BY prerequisiteId;
~~~

Nếu **courseId = 'java-db'**, kết quả gồm **sql-basics** và **data-models**. Mẫu **(a)-[:REQUIRES]->(b)** tương đương yêu cầu tìm những nút đích nối với **a** bằng một cạnh REQUIRES đi ra.

**$courseId** là tham số do ứng dụng cung cấp, giúp tách giá trị đầu vào khỏi câu truy vấn. Không nên ghép chuỗi giá trị tùy ý vào Cypher.

### 5.2. Duyệt nhiều bước với giới hạn độ sâu

~~~cypher
MATCH (course:Course {courseId: $courseId})
      -[:REQUIRES*1..3]->(required:Course)
RETURN DISTINCT required.courseId AS prerequisiteId,
                required.title AS title
ORDER BY prerequisiteId;
~~~

Trong cú pháp Cypher được minh họa, **\*1..3** nghĩa là duyệt từ 1 đến tối đa 3 cạnh REQUIRES. Với **courseId = 'tx'**, tập khóa học có thể đến được là:

| prerequisiteId | Khoảng cách ngắn nhất tính theo số cạnh |
| --- | ---: |
| java-db | 1 |
| data-models | 2 |
| sql-basics | 2 |

**DISTINCT** loại giá trị trùng do một nút có thể được tìm thấy theo nhiều đường đi. Nó không có nghĩa truy vấn chỉ đi qua một đường; cơ sở dữ liệu vẫn phải thực hiện công việc tìm các mẫu phù hợp theo kế hoạch thực thi.

Giới hạn **3** là một quyết định theo ví dụ, không phải quy tắc cố định. Nếu muốn tìm toàn bộ điều kiện tiên quyết trong một đồ thị có độ sâu lớn hơn, giới hạn này có thể bỏ sót dữ liệu. Nếu không giới hạn phù hợp, số đường đi có thể tăng quá lớn và gây truy vấn tốn tài nguyên.

### 5.3. Truy xuất đường đi thay vì chỉ lấy đích

Khi cần hiển thị **vì sao** một khóa học là điều kiện tiên quyết, trả về **path** thay vì chỉ nút đích:

~~~cypher
MATCH path = (course:Course {courseId: $courseId})
             -[:REQUIRES*1..3]->(required:Course)
RETURN [node IN nodes(path) | node.courseId] AS learningPath
ORDER BY length(path), learningPath;
~~~

Ví dụ đường đi tới **sql-basics** có thể là:

~~~text
tx -> java-db -> sql-basics
tx -> java-db -> data-models -> sql-basics
~~~

Hai đường đi đến cùng một nút vẫn hữu ích trong giao diện giải thích lộ trình học, nhưng nếu hệ thống chỉ cần một đường ngắn nhất thì truy vấn mọi path thường làm nhiều việc không cần thiết. Một bài toán **tìm đường ngắn nhất** nên dùng đúng toán tử/thuật toán phù hợp với trọng số, hướng và ràng buộc được hỗ trợ bởi hệ quản trị.

### 5.4. Chu trình, nút lặp và bùng nổ đường đi

Nếu ai đó thêm cạnh **sql-basics → tx**, đồ thị xuất hiện chu trình:

~~~text
tx -> java-db -> sql-basics -> tx
~~~

Trong nghiệp vụ điều kiện tiên quyết, chu trình này thường **không hợp lệ** vì một người học không thể hoàn thành chuỗi khóa bắt buộc theo thứ tự tuyến tính. Trong các miền khác, chu trình lại là dữ liệu bình thường, chẳng hạn mạng người dùng theo dõi lẫn nhau.

Với mỗi nút có trung bình **b** nhánh liên kết và truy vấn duyệt sâu **d** bước, số lựa chọn đường đi *có thể* tăng theo cấp số nhân, cỡ **b^d** trong trường hợp phân nhánh mạnh. Số lượng thực tế còn phụ thuộc các nút chung, các chu trình, quy tắc không dùng lại cạnh và cách công cụ truy vấn tối ưu.

Hệ quả thực tế:

- Bắt đầu từ nút có định danh chọn lọc.
- Giới hạn loại cạnh và độ sâu khi yêu cầu nghiệp vụ cho phép.
- Chọn rõ cần **các nút đích**, **một đường** hay **mọi đường đi**.
- Không trả về toàn bộ đường đi nếu giao diện chỉ cần ID hoặc số lượng.
- Kiểm tra bậc liên kết cao, vì một nút nối với hàng triệu nút có thể là điểm nghẽn.

## 6. Cùng quan hệ đó trong cơ sở dữ liệu quan hệ

Graph database không phải cách duy nhất lưu dữ liệu có mối quan hệ. Trong relational database, điều kiện tiên quyết có thể dùng **bảng liên kết** chứa hai khóa ngoại:

~~~sql
-- Ví dụ PostgreSQL
CREATE TABLE course (
    course_id TEXT PRIMARY KEY,
    title     TEXT NOT NULL
);

CREATE TABLE course_prerequisite (
    course_id       TEXT NOT NULL REFERENCES course(course_id),
    prerequisite_id TEXT NOT NULL REFERENCES course(course_id),
    PRIMARY KEY (course_id, prerequisite_id),
    CHECK (course_id <> prerequisite_id)
);
~~~

Một hàng **('tx', 'java-db')** trong **course_prerequisite** có ý nghĩa tương đương cạnh **tx → java-db**. Hai cột khóa ngoại bảo đảm các khóa học ở hai đầu tồn tại, còn khóa chính ghép ngăn một cặp bị lưu lặp.

**CHECK (course_id <> prerequisite_id)** chỉ ngăn tự trỏ trực tiếp; nó **không ngăn được chu trình dài** như tx → java-db → sql-basics → tx. Trong cả hai kiểu lưu trữ, việc ngăn chu trình theo nghiệp vụ thường cần quy tắc bổ sung.

### 6.1. Lấy quan hệ một bước bằng JOIN

~~~sql
SELECT prerequisite_id
FROM course_prerequisite
WHERE course_id = 'java-db';
~~~

Đây là truy vấn đơn giản; hệ cơ sở dữ liệu quan hệ có thể xử lý rất hiệu quả nhờ khóa chính hoặc chỉ mục thích hợp. **Không nên mặc định graph database nhanh hơn** cho truy vấn một hoặc hai bước.

### 6.2. Lấy quan hệ nhiều bước bằng recursive CTE

PostgreSQL hỗ trợ **WITH RECURSIVE**. Ví dụ sau đi tối đa 3 bước và giữ danh sách nút đã đi qua để tránh quay lại nút cũ trên cùng đường đi:

~~~sql
WITH RECURSIVE reachable(prerequisite_id, depth, visited) AS (
    SELECT
        cp.prerequisite_id,
        1,
        ARRAY[cp.course_id, cp.prerequisite_id]
    FROM course_prerequisite AS cp
    WHERE cp.course_id = 'tx'

    UNION ALL

    SELECT
        cp.prerequisite_id,
        r.depth + 1,
        r.visited || cp.prerequisite_id
    FROM reachable AS r
    JOIN course_prerequisite AS cp
      ON cp.course_id = r.prerequisite_id
    WHERE r.depth < 3
      AND NOT (cp.prerequisite_id = ANY(r.visited))
)
SELECT DISTINCT prerequisite_id
FROM reachable
ORDER BY prerequisite_id;
~~~

Hệ thống vẫn có thể tìm được các nút giống truy vấn Cypher có độ sâu 1 đến 3. Trong ví dụ, **visited** là mảng giá trị TEXT của PostgreSQL; chi tiết cú pháp này không portable nguyên vẹn sang mọi SQL database.

### 6.3. Hai cách biểu diễn khác nhau ở đâu?

| Tiêu chí | Bảng quan hệ | Property graph |
| --- | --- | --- |
| Biểu diễn liên kết | Khóa ngoại, bảng liên kết | Cạnh có loại và hướng |
| Truy vấn một bước | JOIN hoặc đọc bảng liên kết | Pattern một cạnh |
| Truy vấn số bước biến thiên | Recursive CTE, lặp hoặc cơ chế riêng | Pattern nhiều cạnh, traversal hoặc thuật toán đồ thị |
| Ràng buộc ID | PRIMARY KEY, UNIQUE | Constraint/index tùy hệ quản trị |
| Ràng buộc hai đầu liên kết | FOREIGN KEY | Cạnh nối trực tiếp các nút; kiểm tra khác tùy hệ quản trị |
| Giao dịch và tổng hợp dạng bảng | SQL/ACID rất phổ biến, công cụ trưởng thành | Tùy khả năng graph database và thiết kế cụ thể |
| Hệ sinh thái Java | JDBC, JPA/Hibernate, nhiều driver | Driver/API theo sản phẩm, ví dụ Neo4j Java Driver |
| Chi phí vận hành | Phù hợp nếu đã có relational DB và truy vấn đáp ứng | Cần cân nhắc thêm vận hành, migration, giám sát và tích hợp |

**Relational model** phù hợp khi dữ liệu có cấu trúc bảng ổn định, nhiều ràng buộc, báo cáo tổng hợp và giao dịch liên bảng. **Graph model** đáng cân nhắc khi nghiệp vụ tập trung vào các đường liên kết đa dạng, truy vấn nhiều bước, khám phá láng giềng hoặc thuật toán đồ thị. Một số relational database hỗ trợ truy vấn đồ thị hiệu quả, và một số graph database cũng dùng các kỹ thuật lưu trữ không quá khác với hệ thống khác. Quyết định cần dựa trên truy vấn thực tế và phép đo.

## 7. Triển khai tầng persistence Java với graph database

Ở ranh giới persistence, các phần nghiệp vụ thường không cần biết cách truy vấn được biểu diễn bằng Cypher hay SQL. Có thể thiết kế một giao diện truy vấn điều kiện tiên quyết:

~~~java
import java.util.List;

public interface CoursePrerequisiteRepository {
    List<String> findPrerequisiteIds(String courseId);
}
~~~

Một triển khai cụ thể dùng **Neo4j Java Driver** (API kiểu Neo4j Driver 5.x) minh họa cách đọc dữ liệu:

~~~java
import java.util.List;

import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;
import org.neo4j.driver.Values;

public final class Neo4jCoursePrerequisiteRepository
        implements CoursePrerequisiteRepository {

    private final Driver driver;

    public Neo4jCoursePrerequisiteRepository(Driver driver) {
        this.driver = driver;
    }

    @Override
    public List<String> findPrerequisiteIds(String courseId) {
        String cypher = """
                MATCH (c:Course {courseId: $courseId})
                      -[:REQUIRES*1..3]->(p:Course)
                RETURN DISTINCT p.courseId AS id
                ORDER BY id
                """;

        try (Session session = driver.session()) {
            return session.executeRead(tx ->
                    tx.run(
                        cypher,
                        Values.parameters("courseId", courseId)
                    ).list(row -> row.get("id").asString())
            );
        }
    }
}
~~~

Giải thích các quyết định:

- **Driver** nên được tạo và chia sẻ ở phạm vi ứng dụng, rồi đóng lúc ứng dụng kết thúc, vì nó quản lý kết nối và tài nguyên.
- **Session** thường dùng trong phạm vi từng thao tác; **try-with-resources** bảo đảm đóng session.
- **executeRead** dùng giao dịch đọc có quản lý, với cơ chế retry của driver cho loại lỗi phù hợp.
- **Values.parameters** truyền tham số an toàn, tránh nối trực tiếp chuỗi người dùng vào Cypher.
- Kết quả được ánh xạ thành **List<String>** để lớp gọi nhận đúng dữ liệu cần thiết, không phụ thuộc trực tiếp vào kiểu **Record** của driver.

Trong ứng dụng có nhiều database, cần cấu hình đúng database mục tiêu thay vì mặc định. Mức nhất quán đọc/ghi, thời hạn timeout và retry phải phù hợp yêu cầu nghiệp vụ, đặc biệt khi thao tác vừa ghi thêm cạnh vừa lập tức kiểm tra điều kiện tiên quyết.

**Điểm giới hạn của ví dụ:** truy vấn chỉ lấy quan hệ sâu tối đa ba bước. Nếu hợp đồng repository yêu cầu *mọi* điều kiện tiên quyết, cần xác định cách duyệt đủ sâu có giới hạn an toàn hoặc sử dụng giải pháp thiết kế khác. Không nên đặt tên hàm thể hiện tính toàn vẹn tuyệt đối rồi âm thầm bỏ sót nút ở độ sâu bốn.

### 7.1. Đọc đồ thị và ghi đồ thị là hai bài toán khác nhau

Khi thêm cạnh **A REQUIRES B**, ứng dụng cần kiểm tra:

1. A và B tồn tại, có định danh hợp lệ và thuộc phạm vi dữ liệu cho phép.
2. A khác B.
3. Nếu nghiệp vụ yêu cầu đồ thị không có chu trình, **B chưa thể đi đến A** qua chuỗi REQUIRES.
4. Sau khi kiểm tra, cạnh mới được tạo trong một giao dịch có cơ chế xử lý xung đột phù hợp.

Kiểm tra chu trình trước rồi ghi ở hai giao dịch rời rạc dễ gặp **race condition**: hai yêu cầu đồng thời có thể mỗi bên thấy đồ thị chưa có chu trình rồi cùng tạo hai cạnh gây chu trình. Khi bất biến này nghiêm ngặt, cần có cách điều phối ghi, khóa hoặc kiểm soát đồng thời thích hợp với hệ quản trị; kiểm tra ở tầng Java đơn thuần chưa đủ.

## 8. Thiết kế đúng quan hệ trước khi tối ưu truy vấn

### 8.1. Tránh nhầm hướng, nhầm kiểu và nhầm cấp độ

Nếu đặt cạnh **java-db → tx** thay vì **tx → java-db**, truy vấn điều kiện tiên quyết sẽ trả dữ liệu sai dù câu lệnh chạy hợp lệ.

Nếu một khóa học thuộc nhiều chương trình, quan hệ **Course -[:IN_PROGRAM]-> Program** không giống **Course -[:REQUIRES]-> Course**. Các cạnh có cùng hai đầu cũng có thể mang ý nghĩa khác nhau; không thể suy luận chúng tương đương chỉ vì nối cùng một cặp nút.

Nên mô tả mỗi loại quan hệ bằng một câu hoàn chỉnh có thể đọc theo hướng, ví dụ: **“Khóa học A yêu cầu hoàn thành khóa học B.”** Điều này giúp thống nhất mã truy vấn, API Java và mô hình dữ liệu.

### 8.2. Xác định tính duy nhất của liên kết

Một cặp khóa học có thể cần **tối đa một** cạnh REQUIRES. Nhưng với loại cạnh khác, có thể được phép nhiều cạnh giữa hai nút, ví dụ **USER -[:PURCHASED {orderId, purchasedAt}]-> PRODUCT** vì cùng một người có thể mua cùng sản phẩm nhiều lần.

Nếu dùng **MERGE** không suy nghĩ về định danh của quan hệ, hệ thống có thể gộp nhầm các sự kiện cần phân biệt. Đối với các sự kiện có danh tính và lịch sử độc lập, cân nhắc mô hình hóa đơn hàng hoặc giao dịch thành nút/sự kiện riêng với mã ổn định.

### 8.3. Cần thiết kế chiến lược xóa dữ liệu

Xóa một khóa học có thể ảnh hưởng nhiều khóa khác đang tham chiếu nó bằng REQUIRES. Một số graph database không cho xóa nút còn liên kết trừ khi các cạnh được xử lý trước, hoặc có thao tác xóa cả cạnh kèm nút. Điều này **không đồng nghĩa** hệ thống tự bảo vệ đúng quy tắc nghiệp vụ.

Với dữ liệu phục vụ kiểm toán hoặc lịch sử hoàn thành khóa, nên cân nhắc **archived/deactivated** thay vì xóa vật lý, bảo đảm các truy vấn hiện tại loại trừ dữ liệu đã ngừng hoạt động nhưng dữ liệu lịch sử vẫn có thể được đối chiếu khi cần.

## 9. Hiệu năng: truy vấn mối quan hệ cần đo điều gì?

Một đồ thị có vài trăm nút thường dễ truy vấn. Một đồ thị có hàng triệu nút và nhiều nút bậc cao có thể gặp chi phí lớn dù cú pháp chỉ vài dòng.

### 9.1. Đi từ điểm bắt đầu có chọn lọc

~~~cypher
MATCH (c:Course {courseId: $courseId})
      -[:REQUIRES*1..3]->(p:Course)
RETURN DISTINCT p.courseId;
~~~

Nút đầu **c** có định danh duy nhất, nên có thể được tìm nhanh khi hệ quản trị dùng đúng chỉ mục. Ngược lại, truy vấn bắt đầu bằng **MATCH (c:Course)** không có điều kiện rồi duyệt từ *tất cả* khóa học có thể tốn kém nhiều hơn.

Chỉ mục hỗ trợ **tìm điểm bắt đầu**, nhưng không triệt tiêu chi phí duyệt một mạng có rất nhiều cạnh. Cần xem **độ sâu**, **bậc nút**, **số đường đi**, **số kết quả trả về** và kế hoạch thực thi.

### 9.2. Hồ sơ truy vấn và giới hạn kết quả

Các hệ quản trị cung cấp công cụ xem kế hoạch truy vấn, ví dụ **EXPLAIN** hoặc **PROFILE** trong Neo4j. Khi tối ưu, nên đo:

- Số nút/cạnh đã đọc hoặc mở rộng.
- Có dùng index để định vị nút đầu hay không.
- Thời gian và tài nguyên truy vấn trên dữ liệu gần quy mô thật.
- Số hàng/path trung gian so với số kết quả cuối cùng.
- Tác động của bộ nhớ, cache, tải ghi đồng thời và kết nối mạng.

**LIMIT** có thể giảm số hàng trả về nhưng **không bảo đảm** tránh hết công việc duyệt hoặc sắp xếp; hiệu quả phụ thuộc truy vấn và kế hoạch thực thi. Với API liệt kê láng giềng, phân trang phải dựa trên trật tự xác định và hiểu giới hạn của việc phân trang trên tập kết quả luôn thay đổi.

### 9.3. Khi nào nên tính trước?

Nếu toàn bộ điều kiện tiên quyết của mỗi khóa thường được đọc rất nhiều lần nhưng chỉ thay đổi hiếm, có thể cân nhắc **cache hoặc bảng/nhóm dữ liệu truy cập đã tính trước**. Cách làm này đổi chi phí đọc lấy chi phí cập nhật và cơ chế làm mới khi cạnh REQUIRES thay đổi.

Nếu nghiệp vụ yêu cầu thông tin luôn mới ngay sau khi thêm quan hệ, cache không đồng bộ có thể gây lỗi. Quyết định tối ưu cần gắn với mức nhất quán được chấp nhận, không chỉ dựa trên thời gian phản hồi.

## 10. Giao dịch, nhất quán, bảo mật và vòng đời schema

Graph database vẫn là một phần của **tầng persistence**, nên vẫn có những nghĩa vụ chung của việc lưu dữ liệu bền vững:

**Giao dịch.** Tạo nút và cạnh liên quan cần diễn ra nguyên tử khi nghiệp vụ yêu cầu tất cả cùng tồn tại hoặc cùng thất bại. Không nên để người dùng thấy khóa học đã được tạo nhưng các quan hệ bắt buộc chỉ được ghi một nửa nếu hợp đồng nghiệp vụ coi đó là một thao tác.

**Ràng buộc.** Unique ID, loại cạnh hợp lệ, quan hệ được phép giữa những loại nút nào, điều kiện không tạo chu trình, quyền tạo cạnh và quy tắc xóa đều phải được xác định. Khả năng thực thi ở tầng database tùy sản phẩm; phần không thể khai báo cần được kiểm soát ở tầng dịch vụ và trong giao dịch.

**Bảo mật.** Truy vấn có tham số chỉ giải quyết phần ghép dữ liệu đầu vào; nó không thay cho **authorization**. Trong hệ thống nhiều tenant, lọc tenant ở nút bắt đầu chưa đủ nếu traversal có thể đi qua nút hoặc cạnh thuộc tenant khác. Phải có chính sách phạm vi cho **mọi nút/cạnh có thể truy cập**, đồng thời hạn chế quyền của tài khoản kết nối.

**Tiến hóa schema.** Thêm một loại node/relationship hoặc đổi tên property có thể ảnh hưởng tới truy vấn Cypher, mã ánh xạ Java, index, cache và dữ liệu cũ. Nên quản lý thay đổi bằng migration có phiên bản, dữ liệu mẫu kiểm thử và quy trình rollback phù hợp.

**Vận hành.** Cần có backup/restore, quan sát độ trễ truy vấn, thống kê lỗi kết nối, sử dụng pool, giám sát kích thước dữ liệu và kiểm soát thay đổi chỉ mục. Cách cấu hình và mức độ bảo đảm phụ thuộc sản phẩm và môi trường triển khai.

## 11. Các lỗi thiết kế thường gặp

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Dùng tên hiển thị làm ID | Đổi tên làm đứt liên kết hoặc tạo nhầm nút | Dùng mã định danh ổn định, ràng buộc duy nhất |
| Đảo chiều cạnh REQUIRES | Truy vấn trả phụ thuộc ngược | Viết rõ ý nghĩa một cạnh theo chiều nguồn → đích |
| Duyệt không giới hạn trên đồ thị lớn | Bùng nổ số đường đi, thời gian xử lý cao | Giới hạn độ sâu theo nghiệp vụ; chọn thuật toán phù hợp |
| Trả mọi path khi chỉ cần danh sách nút | Dữ liệu trùng lặp, tốn tài nguyên | Trả đích và DISTINCT khi phù hợp |
| Không kiểm tra chu trình cho đồ thị tiên quyết | Hình thành lộ trình không thể học hợp lệ | Kiểm tra tính tới được trước ghi, kiểm soát cạnh tranh |
| Xem MERGE như toàn bộ giải pháp toàn vẹn | Trùng sự kiện hoặc vi phạm quy tắc phức tạp | Thiết kế ID, constraint và giao dịch |
| Giả định graph database luôn nhanh hơn SQL | Tăng chi phí chuyển đổi, vận hành mà không có lợi ích | Benchmark trên workload thật, cân nhắc recursive CTE |
| Chỉ xác thực đầu vào mà quên quyền duyệt | Lộ dữ liệu từ nút liên quan thuộc phạm vi khác | Áp dụng authorization trên toàn đường duyệt |
| Xóa nút mà không xem tác động cạnh và lịch sử | Mất mối liên kết hoặc lịch sử nghiệp vụ | Thiết kế chính sách xóa/archival trước khi thực thi |

## 12. Tình huống thực hành và tự kiểm tra

**Tình huống A — Điều kiện tiên quyết.** Với đồ thị ở phần 2, người học mở khóa **tx**.

1. Khóa học tiên quyết trực tiếp là gì? **java-db**.
2. Có bao nhiêu khóa tiên quyết phân biệt trong tối đa 3 bước? **Ba**: **java-db**, **data-models**, **sql-basics**.
3. Có bao nhiêu đường đi từ **tx** đến **sql-basics** trong hình minh họa? **Hai**.
4. Nếu thêm cạnh **sql-basics → tx**, hệ thống phải phản ứng thế nào? Theo quy tắc *đồ thị điều kiện tiên quyết không có chu trình*, phải từ chối thao tác và duy trì tính nhất quán khi có ghi đồng thời.
5. Nếu chỉ cần danh sách khóa học đã loại trùng, vì sao dùng DISTINCT? Vì cùng một khóa học có thể được tìm thấy qua nhiều đường.

**Tình huống B — Chọn kiểu lưu trữ.** Một ứng dụng chỉ có bảng khách hàng và đơn hàng, cần tổng doanh thu theo tháng và lọc đơn theo trạng thái. Mô hình quan hệ với chỉ mục phù hợp có thể đáp ứng tốt; chưa có lý do tự động chuyển sang graph database. Ngược lại, một hệ thống cần lần theo đường phụ thuộc không cố định giữa hàng nghìn dịch vụ, tìm nút ảnh hưởng khi một dịch vụ bị lỗi và phân tích cụm liên kết có thể hưởng lợi từ mô hình đồ thị và công cụ truy vấn phù hợp.

**Tình huống C — Thiết kế Java.** Một API Java gọi **findPrerequisiteIds("tx")** và nhận ba ID. Nếu người thiết kế thêm tầng điều kiện tiên quyết thứ tư, hợp đồng API có trả đủ không? Với truy vấn **\*1..3**, **không**. Cần làm rõ hợp đồng trước khi giới hạn độ sâu trong triển khai, hoặc đổi API để thể hiện độ sâu được yêu cầu.

## 13. Ghi nhớ

**Mô hình đồ thị** đặt nút và cạnh vào trung tâm, giúp diễn đạt tự nhiên những bài toán cần *đi theo quan hệ*. Truy cập một bước tìm láng giềng trực tiếp; truy cập nhiều bước tìm nút có thể đến được hoặc đường đi qua chuỗi cạnh. Hướng cạnh, loại cạnh, chu trình và số nhánh quyết định tính đúng đắn lẫn chi phí truy vấn.

Cùng một quan hệ có thể được lưu bằng **bảng liên kết trong relational database** hoặc **cạnh trong graph database**; việc chọn công nghệ phải dựa trên tính chất truy vấn, ràng buộc, nhất quán và khả năng vận hành. Với ứng dụng Java, tầng persistence nên cung cấp API diễn đạt nghiệp vụ rõ ràng, dùng tham số hóa truy vấn, xử lý giao dịch và bảo vệ các bất biến dữ liệu, bất kể dữ liệu được lưu bằng SQL hay đồ thị.
