# Trùng entity gốc, tích Descartes và quan hệ bị thiếu trong kết quả

Khi viết custom Cypher cho Spring Data Neo4j (SDN), một truy vấn có thể trả về nhiều dòng chứa cùng một node gốc, tạo ra nhiều tổ hợp dòng không cần thiết hoặc chỉ trả node gốc mà bỏ mất relationship cần ánh xạ. Những kết quả này có thể khiến repository trả entity lặp, thống kê bị phóng đại hoặc object Java thiếu các liên kết vốn có trong graph.

Để tránh lỗi, cần hiểu hai lớp riêng biệt: **Cypher tạo tập dòng kết quả như thế nào** và **SDN dùng các giá trị trong từng dòng để ánh xạ entity ra sao**. Node xuất hiện trong phần MATCH không tự động có mặt trong dữ liệu trả về. Muốn SDN ánh xạ một relationship, truy vấn phải trả đủ node và relationship cần thiết theo mapping của entity. Đồng thời, phải kiểm soát số dòng trước khi ánh xạ, nhất là khi truy vấn đi qua nhiều nhánh one-to-many.

## Mô hình dùng trong bài

Giả sử ứng dụng quản lý một người, các dự án người đó tham gia và các kỹ năng người đó có. Một Person có thể tham gia nhiều Project và có nhiều Skill.

~~~java
import java.util.LinkedHashSet;
import java.util.Set;

import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;
import org.springframework.data.neo4j.core.schema.Relationship;

@Node("Person")
public class Person {

    @Id
    private String employeeCode;

    private String fullName;

    @Relationship(type = "WORKS_ON")
    private Set<Project> projects = new LinkedHashSet<>();

    @Relationship(type = "HAS_SKILL")
    private Set<Skill> skills = new LinkedHashSet<>();

    protected Person() {
    }

    public String getEmployeeCode() {
        return employeeCode;
    }

    public String getFullName() {
        return fullName;
    }

    public Set<Project> getProjects() {
        return projects;
    }

    public Set<Skill> getSkills() {
        return skills;
    }
}
~~~

~~~java
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Project")
public class Project {

    @Id
    private String projectCode;

    private String name;

    protected Project() {
    }
}
~~~

~~~java
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Skill")
public class Skill {

    @Id
    private String skillCode;

    private String name;

    protected Skill() {
    }
}
~~~

Graph minh họa có thể chứa:

~~~cypher
CREATE (p:Person {employeeCode: "E-01", fullName: "Lan Nguyen"})
CREATE (pr1:Project {projectCode: "PR-01", name: "Graph Search"})
CREATE (pr2:Project {projectCode: "PR-02", name: "Knowledge Hub"})
CREATE (s1:Skill {skillCode: "SK-01", name: "Java"})
CREATE (s2:Skill {skillCode: "SK-02", name: "Cypher"})
CREATE (s3:Skill {skillCode: "SK-03", name: "Spring Data Neo4j"})
CREATE (p)-[:WORKS_ON]->(pr1)
CREATE (p)-[:WORKS_ON]->(pr2)
CREATE (p)-[:HAS_SKILL]->(s1)
CREATE (p)-[:HAS_SKILL]->(s2)
CREATE (p)-[:HAS_SKILL]->(s3);
~~~

Một người có hai dự án và ba kỹ năng. Khi truy vấn từng nhánh riêng, số dòng có thể nhỏ và dễ hiểu. Khi kết hợp nhiều nhánh, số dòng có thể tăng theo tích số phần tử ở từng nhánh.

## Cypher trả về dòng, không tự trả về một entity duy nhất

Cypher trả về một bảng kết quả. Mỗi tổ hợp khớp với pattern tạo thành một dòng. Nếu một node gốc nối với nhiều node đích, node gốc có thể xuất hiện lặp lại ở nhiều dòng.

Ví dụ:

~~~cypher
MATCH (p:Person {employeeCode: $employeeCode})-[:WORKS_ON]->(project:Project)
RETURN p, project;
~~~

Với hai dự án, kết quả có hai dòng:

| Dòng | p | project |
|---|---|---|
| 1 | Person E-01 | Project PR-01 |
| 2 | Person E-01 | Project PR-02 |

Đây không phải dữ liệu graph bị nhân đôi. Node Person vẫn chỉ là một node; nó xuất hiện ở hai dòng vì có hai kết quả ghép với Project.

Nếu repository trả List<Person> từ một custom query có nhiều dòng như vậy, không nên mặc định SDN sẽ luôn gộp mọi dòng có cùng node gốc thành một phần tử duy nhất trong mọi kiểu truy vấn và mọi phiên bản. Hãy thiết kế kết quả để số dòng tương ứng với cardinality mà phương thức repository công bố, rồi xác minh hành vi mapping bằng integration test.

### Khi chỉ cần entity gốc

Nếu mục tiêu là lấy danh sách người thỏa điều kiện, không cần dữ liệu dự án trong kết quả, hãy khử trùng node gốc:

~~~cypher
MATCH (p:Person)-[:WORKS_ON]->(:Project)
WHERE p.fullName CONTAINS $keyword
RETURN DISTINCT p
ORDER BY p.fullName;
~~~

RETURN DISTINCT p trả mỗi node Person một lần, dù người đó có nhiều dự án phù hợp. Vì truy vấn chỉ trả node gốc, các collection relationship trong entity không được yêu cầu ánh xạ từ kết quả này. Nếu cần projects hoặc skills, phải trả thêm dữ liệu quan hệ tương ứng.

DISTINCT áp dụng trên toàn bộ biểu thức được trả về. Ví dụ:

~~~cypher
MATCH (p:Person)-[:WORKS_ON]->(project:Project)
RETURN DISTINCT p, project;
~~~

Kết quả vẫn có nhiều dòng cho cùng một p nếu các project khác nhau, bởi mỗi cặp (p, project) là một tổ hợp khác nhau. DISTINCT không có nghĩa là “chỉ giữ một dòng cho mỗi entity gốc” khi các cột còn lại khác nhau.

## Tích Descartes khi ghép nhiều nhánh relationship

Vấn đề lớn hơn xuất hiện khi truy vấn mở rộng nhiều nhánh one-to-many độc lập từ cùng node gốc. Ví dụ, người có dự án và kỹ năng:

~~~cypher
MATCH (p:Person {employeeCode: $employeeCode})-[:WORKS_ON]->(project:Project)
MATCH (p)-[:HAS_SKILL]->(skill:Skill)
RETURN p, project, skill;
~~~

Hai nhánh cùng được mở rộng từ p. Với hai dự án và ba kỹ năng, mỗi dự án được ghép với mỗi kỹ năng, tạo ra sáu dòng:

| Dòng | Project | Skill |
|---|---|---|
| 1 | PR-01 | SK-01 |
| 2 | PR-01 | SK-02 |
| 3 | PR-01 | SK-03 |
| 4 | PR-02 | SK-01 |
| 5 | PR-02 | SK-02 |
| 6 | PR-02 | SK-03 |

Số dòng trung gian là tích số phần tử của hai nhánh: \(2 \times 3 = 6\). Nếu có thêm nhánh CERTIFIED_IN với bốn chứng chỉ, số tổ hợp có thể tăng thành \(2 \times 3 \times 4 = 24\). Đây là tích Descartes (Cartesian product) giữa các tập kết quả của các nhánh.

Hiện tượng này không chỉ làm lặp p. Các node dự án và kỹ năng cũng xuất hiện lặp lại trong các tổ hợp. Nếu dùng count(*), tổng số dòng sẽ bị hiểu nhầm thành số người, số dự án hoặc số kỹ năng. Nếu collect(project) và collect(skill) trực tiếp, collection có thể chứa cùng một node nhiều lần.

OPTIONAL MATCH không tự loại bỏ tích Descartes. Truy vấn sau vẫn có thể nhân số dòng nếu cả hai nhánh đều khớp nhiều phần tử:

~~~cypher
MATCH (p:Person {employeeCode: $employeeCode})
OPTIONAL MATCH (p)-[:WORKS_ON]->(project:Project)
OPTIONAL MATCH (p)-[:HAS_SKILL]->(skill:Skill)
RETURN p, project, skill;
~~~

OPTIONAL MATCH giữ lại người không có dự án hoặc kỹ năng bằng cách đưa giá trị null cho nhánh không khớp. Nhưng khi cả hai nhánh có nhiều phần tử, chúng vẫn kết hợp với nhau thành nhiều dòng.

## Dùng DISTINCT và collect khi cần gom kết quả theo node gốc

Nếu muốn một dòng cho mỗi người và các collection chứa dữ liệu liên quan, có thể gom kết quả bằng aggregation:

~~~cypher
MATCH (p:Person {employeeCode: $employeeCode})
OPTIONAL MATCH (p)-[workRel:WORKS_ON]->(project:Project)
OPTIONAL MATCH (p)-[skillRel:HAS_SKILL]->(skill:Skill)
RETURN p,
       collect(DISTINCT workRel) AS workRelationships,
       collect(DISTINCT project) AS projects,
       collect(DISTINCT skillRel) AS skillRelationships,
       collect(DISTINCT skill) AS skills;
~~~

collect(DISTINCT ...) loại phần tử lặp trong từng collection. Với dữ liệu minh họa, projects có hai node, skills có ba node, và mỗi collection relationship chứa các cạnh tương ứng. Việc gom nhóm theo p khiến kết quả cuối có một dòng cho người được chọn.

Tuy nhiên, cần phân biệt hai việc:

- collect(DISTINCT ...) làm sạch collection kết quả và đưa các dòng về một nhóm theo node gốc.
- Nó không ngăn các dòng trung gian được tạo ra bởi tích Descartes. Nếu các nhánh rất rộng, Cypher vẫn phải xử lý nhiều tổ hợp trước khi aggregation hoàn tất.

Với graph nhỏ, truy vấn này có thể đủ rõ ràng. Với nhiều nhánh one-to-many hoặc độ kết nối cao, nên tách từng nhánh thành một subquery tương quan để tránh nhân các nhánh với nhau.

## Tách từng nhánh bằng correlated subquery

Có thể tính collection dự án và collection kỹ năng trong hai subquery độc lập. Mỗi subquery nhận p qua WITH, mở rộng một nhánh rồi gom kết quả trước khi trả về truy vấn ngoài:

~~~cypher
MATCH (p:Person {employeeCode: $employeeCode})

CALL {
    WITH p
    OPTIONAL MATCH (p)-[workRel:WORKS_ON]->(project:Project)
    RETURN collect(DISTINCT workRel) AS workRelationships,
           collect(DISTINCT project) AS projects
}

CALL {
    WITH p
    OPTIONAL MATCH (p)-[skillRel:HAS_SKILL]->(skill:Skill)
    RETURN collect(DISTINCT skillRel) AS skillRelationships,
           collect(DISTINCT skill) AS skills
}

RETURN p,
       workRelationships,
       projects,
       skillRelationships,
       skills;
~~~

Ở đây, subquery thứ nhất chỉ xử lý quan hệ WORKS_ON, subquery thứ hai chỉ xử lý HAS_SKILL. Mỗi subquery trả về một dòng đã gom theo p; truy vấn ngoài kết hợp các collection đã được gom thay vì ghép từng dự án với từng kỹ năng. Cách này giảm nguy cơ tạo tích Descartes giữa các nhánh độc lập.

CALL { ... } với biến được đưa vào qua WITH là correlated subquery. Hãy xác nhận cú pháp này được hỗ trợ bởi phiên bản Neo4j mà dự án đang sử dụng. Với phiên bản chưa hỗ trợ, có thể chạy từng truy vấn nhánh riêng trong cùng transaction hoặc dùng một truy vấn khác phù hợp với phiên bản.

Khi dùng custom query để ánh xạ Person, cần kiểm tra SDN phiên bản dự án có nhận các node và relationship nằm trong các collection kết quả như mong muốn hay không. Truy vấn phải trả đủ node gốc, node đích và relationship cần thiết cho các thuộc tính @Relationship; nếu kết quả chỉ dành cho báo cáo, cân nhắc ánh xạ sang DTO thay vì entity.

Có thể đặt truy vấn này trong repository để trả về một Person cùng hai collection quan hệ:

~~~java
import java.util.Optional;
import org.springframework.data.neo4j.repository.Neo4jRepository;
import org.springframework.data.neo4j.repository.query.Query;
import org.springframework.data.repository.query.Param;

public interface PersonRepository extends Neo4jRepository<Person, String> {

    @Query("""
        MATCH (p:Person {employeeCode: $employeeCode})
        CALL {
            WITH p
            OPTIONAL MATCH (p)-[workRel:WORKS_ON]->(project:Project)
            RETURN collect(DISTINCT workRel) AS workRelationships,
                   collect(DISTINCT project) AS projects
        }
        CALL {
            WITH p
            OPTIONAL MATCH (p)-[skillRel:HAS_SKILL]->(skill:Skill)
            RETURN collect(DISTINCT skillRel) AS skillRelationships,
                   collect(DISTINCT skill) AS skills
        }
        RETURN p, workRelationships, projects, skillRelationships, skills
        """)
    Optional<Person> findPersonGraphByEmployeeCode(
        @Param("employeeCode") String employeeCode
    );
}
~~~

Điều kiện employeeCode cần xác định duy nhất một Person để kiểu Optional<Person> phản ánh đúng kết quả mong đợi. Cấu trúc trả về ở trên là một dòng cho node gốc cùng các danh sách relationship và node đích; vẫn cần chạy integration test với đúng phiên bản SDN/Neo4j để xác nhận ánh xạ collection theo entity metadata.

## Quan hệ bị thiếu vì truy vấn không trả về relationship

Một lỗi khác là truy vấn có MATCH qua relationship nhưng chỉ RETURN node gốc:

~~~cypher
MATCH (p:Person)-[:WORKS_ON]->(project:Project)
WHERE p.employeeCode = $employeeCode
RETURN p;
~~~

Pattern đã đi qua WORKS_ON để lọc người có dự án. Nhưng kết quả chỉ chứa p. SDN không thể suy ra từ một node trả về rằng ứng dụng muốn nạp collection projects, cũng không có các relationship và node đích trong record để ánh xạ chúng. Entity có thể nhận được các property của Person nhưng thiếu collection dự án.

Để ánh xạ quan hệ, trả về node gốc cùng relationship và node đích:

~~~cypher
MATCH (p:Person {employeeCode: $employeeCode})
OPTIONAL MATCH (p)-[r:WORKS_ON]->(project:Project)
RETURN p, collect(DISTINCT r), collect(DISTINCT project);
~~~

Kết quả có các thành phần cần thiết để ánh xạ relationship WORKS_ON: node Person, các relationship r và các node Project. Dùng OPTIONAL MATCH nếu vẫn muốn trả người khi người đó chưa tham gia dự án nào. Nếu dùng MATCH bắt buộc cho nhánh dự án, người không có dự án sẽ không xuất hiện trong kết quả.

Với nhiều nhánh, trả về đủ các relationship và endpoint cho từng thuộc tính @Relationship. Ví dụ, entity Person có projects và skills; query cần trả WORKS_ON, các Project, HAS_SKILL và các Skill nếu muốn SDN dựng cả hai collection.

Không phải cứ trả p là SDN tự chạy thêm mọi relationship đã khai báo trong entity. Phạm vi mapping của custom query phụ thuộc cấu trúc dữ liệu mà truy vấn trả về và cơ chế mapping của phiên bản SDN.

## Phân biệt entity mapping và DTO/projection

Không phải truy vấn nào cũng cần trả về entity graph. Nếu màn hình chỉ hiển thị tên người, tên dự án và số lượng kỹ năng, DTO có thể phù hợp hơn:

~~~java
import java.util.List;

public record PersonOverview(
    String employeeCode,
    String fullName,
    List<String> projectNames,
    List<String> skillNames
) {
}
~~~

Cypher có thể trả các giá trị đã gom theo node gốc:

~~~cypher
MATCH (p:Person {employeeCode: $employeeCode})
CALL {
    WITH p
    OPTIONAL MATCH (p)-[:WORKS_ON]->(project:Project)
    RETURN collect(DISTINCT project.name) AS projectNames
}
CALL {
    WITH p
    OPTIONAL MATCH (p)-[:HAS_SKILL]->(skill:Skill)
    RETURN collect(DISTINCT skill.name) AS skillNames
}
RETURN p.employeeCode AS employeeCode,
       p.fullName AS fullName,
       projectNames,
       skillNames;
~~~

DTO chỉ chứa các giá trị phục vụ màn hình; nó không yêu cầu SDN tái tạo đầy đủ entity graph. Khi dùng projection hoặc DTO, tên cột trả về cần khớp với constructor/property mà cơ chế mapping đang dùng. Nếu dùng Neo4jClient, có thể map từng record một cách tường minh.

Không nên trả DTO nhưng khai báo method có kiểu Person hoặc ngược lại. Kiểu trả về của repository phải khớp cấu trúc dữ liệu Cypher trả về. Nếu cần thao tác cập nhật entity sau khi đọc DTO, hãy tải lại entity theo use case cập nhật hoặc thực hiện lệnh ghi có mục tiêu.

## Đếm và phân trang khi có nhiều relationship

Tích Descartes cũng làm sai thống kê nếu đếm dòng thay vì đếm node gốc. Ví dụ:

~~~cypher
MATCH (p:Person)-[:WORKS_ON]->(project:Project)
MATCH (p)-[:HAS_SKILL]->(skill:Skill)
RETURN count(*) AS rows,
       count(DISTINCT p) AS people,
       count(DISTINCT project) AS projects,
       count(DISTINCT skill) AS skills;
~~~

Với một người có hai dự án và ba kỹ năng, count(*) có thể bằng sáu, trong khi số người là một, số dự án là hai và số kỹ năng là ba. Chọn hàm đếm theo đối tượng nghiệp vụ cần đo.

Nếu phân trang danh sách người dựa trên nhiều relationship, hãy xác định trang theo tập node gốc duy nhất. Có thể tách bước chọn và phân trang node gốc trước khi mở rộng các nhánh liên quan, hoặc dùng subquery để gom relationship sau khi đã chọn các node cần trả. Tránh áp dụng SKIP/LIMIT trên tập dòng đã bị nhân bởi nhiều nhánh, vì một người có nhiều liên kết có thể chiếm nhiều vị trí trong trang.

Ví dụ phân trang node gốc trước:

~~~cypher
MATCH (p:Person)
WHERE p.active = true
WITH DISTINCT p
ORDER BY p.fullName, p.employeeCode
SKIP $skip
LIMIT $limit

CALL {
    WITH p
    OPTIONAL MATCH (p)-[r:WORKS_ON]->(project:Project)
    RETURN collect(DISTINCT r) AS projectRelationships,
           collect(DISTINCT project) AS projects
}

RETURN p, projectRelationships, projects
ORDER BY p.fullName, p.employeeCode;
~~~

Bước WITH DISTINCT p xác định tập người duy nhất trước khi phân trang. Sau đó subquery lấy relationship cho từng người trong trang. Hãy bổ sung các nhánh cần thiết và bảo đảm thứ tự sắp xếp có tiêu chí ổn định, ví dụ dùng cả employeeCode khi nhiều người có cùng fullName.

## Quy trình chẩn đoán khi kết quả bị lặp hoặc thiếu quan hệ

Khi repository trả dữ liệu không như mong đợi, hãy kiểm tra theo thứ tự:

1. **Chạy Cypher trực tiếp.** Xem số dòng, các cột trả về và số lần node gốc xuất hiện.
2. **Kiểm tra cardinality từng nhánh.** Đếm số project, skill hoặc node liên quan của một root để tính số dòng dự kiến.
3. **Tìm tích Descartes.** Xác định có nhiều pattern one-to-many độc lập được ghép trong cùng một query hay không.
4. **Kiểm tra RETURN.** Xác nhận root node, relationship và endpoint cần ánh xạ đều có trong kết quả.
5. **Chọn cách khử trùng hoặc gom nhóm.** Dùng RETURN DISTINCT root nếu chỉ cần root; dùng collect(DISTINCT ...) hoặc subquery nếu cần các collection quan hệ.
6. **Kiểm tra kiểu trả về.** Dùng entity cho kết quả entity graph, DTO/projection cho dữ liệu tổng hợp hoặc màn hình.
7. **Viết integration test.** Tạo dữ liệu có nhiều phần tử ở mỗi nhánh và cả trường hợp không có relationship để xác nhận mapping.

Một test quan trọng cần có ít nhất một người với hai dự án và ba kỹ năng. Nếu chỉ dùng một dự án và một kỹ năng, lỗi tích Descartes có thể không xuất hiện vì tích 1 x 1 vẫn chỉ là một dòng.

## Những lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| MATCH một-nhiều rồi RETURN root, child | Root lặp theo từng child | RETURN DISTINCT root nếu chỉ cần root |
| Ghép hai nhánh one-to-many độc lập | Số dòng tăng theo tích cardinality | Gom từng nhánh bằng subquery hoặc truy vấn riêng |
| Chỉ dùng collect() sau tích Descartes | Collection vẫn có thể chứa phần tử lặp | Dùng collect(DISTINCT ...); tách nhánh nếu số dòng trung gian lớn |
| Dùng RETURN DISTINCT root, child để mong mỗi root chỉ có một dòng | Mỗi child khác nhau vẫn tạo một dòng riêng | Chỉ trả root hoặc aggregate child |
| MATCH bắt buộc cho relationship tùy chọn | Root không có relationship bị loại khỏi kết quả | Dùng OPTIONAL MATCH khi cần giữ root |
| Chỉ RETURN root sau khi đã MATCH relationship | Entity không có dữ liệu relationship để ánh xạ | Trả root, relationship và node đích |
| Dùng count(*) để đếm root sau nhiều nhánh | Thống kê bị phóng đại | Dùng count(DISTINCT root) |
| Phân trang sau khi mở rộng các nhánh | Một root có thể chiếm nhiều vị trí hoặc bị tách giữa các trang | Phân trang root duy nhất trước khi mở rộng relationship |
| Dùng entity cho kết quả tổng hợp tùy ý | Mapping khó đoán hoặc thiếu field | Dùng DTO/projection và alias rõ ràng |

## Bài tập thực hành

Với graph Person, Project và Skill ở đầu bài:

1. Tạo một Person có hai Project và ba Skill.
2. Chạy query trả p, project và đếm số dòng; giải thích vì sao p xuất hiện hai lần.
3. Chạy query mở rộng đồng thời WORKS_ON và HAS_SKILL; xác nhận số dòng tăng thành sáu.
4. Dùng RETURN DISTINCT p để chỉ lấy người duy nhất và quan sát rằng relationship không được trả về.
5. Dùng collect(DISTINCT ...) để gom node và relationship của từng nhánh.
6. Tách hai nhánh bằng correlated subquery và so sánh số dòng trung gian, cấu trúc kết quả.
7. Viết một query chỉ RETURN p sau khi MATCH relationship rồi so sánh với query trả cả node, relationship và node đích.
8. Thêm một người không có dự án hoặc kỹ năng; thử MATCH và OPTIONAL MATCH để thấy khác biệt.
9. Viết thống kê dùng count(*) và count(DISTINCT p), giải thích vì sao kết quả khác nhau.
10. Viết integration test xác nhận một người có hai dự án và ba kỹ năng được ánh xạ thành đúng hai collection, không trùng và không thiếu phần tử.

Khi xây dựng custom query cho SDN, hãy kiểm soát số dòng mà Cypher tạo ra và trả đủ dữ liệu cho phần graph muốn ánh xạ. Dùng DISTINCT khi chỉ cần node gốc duy nhất, collect(DISTINCT ...) khi cần gom quan hệ và tách các nhánh one-to-many bằng subquery khi có nguy cơ tích Descartes. Với kết quả tổng hợp dành cho giao diện hoặc báo cáo, DTO/projection thường thể hiện hợp đồng dữ liệu rõ ràng hơn entity graph.

