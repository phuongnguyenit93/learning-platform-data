# Thiết kế ID ổn định, ràng buộc duy nhất và dữ liệu dùng chung

Trong một ứng dụng sử dụng Spring Data Neo4j, cùng một người dùng, khách hàng hoặc sản phẩm có thể được tham chiếu từ nhiều phần của đồ thị. Nếu mỗi lần tạo quan hệ ta lại sinh một node mới cho cùng một thực thể, dữ liệu sẽ bị phân mảnh: thông tin cập nhật ở một node không tự xuất hiện ở node còn lại, truy vấn đếm có thể cho kết quả sai và việc quản lý quyền truy cập trở nên khó khăn.

Thiết kế định danh ổn định, ràng buộc duy nhất và cách chia sẻ node giúp bảo đảm mỗi thực thể có một danh tính rõ ràng trong đồ thị. Spring Data Neo4j ánh xạ danh tính đó qua `@Id`, còn Neo4j bảo vệ tính duy nhất ở tầng cơ sở dữ liệu bằng constraint. Với dữ liệu được nhiều thực thể dùng chung, ta tạo một node đại diện và nối tới node đó bằng relationship phù hợp với ngữ cảnh nghiệp vụ.

## 1. Vì sao cần ID ổn định?

ID là giá trị dùng để nhận diện một thực thể qua nhiều lần đọc, ghi và cập nhật. Một ID tốt cần đáp ứng các đặc điểm:

- **Duy nhất:** không trùng với ID của một thực thể khác trong phạm vi được xác định.
- **Ổn định:** không thay đổi khi tên, email, địa chỉ hoặc thuộc tính mô tả thay đổi.
- **Có thể tái sử dụng:** ứng dụng có thể dùng cùng ID khi đồng bộ dữ liệu, xử lý thông điệp lặp hoặc tham chiếu thực thể từ hệ thống khác.
- **Có phạm vi rõ ràng:** nếu ID chỉ duy nhất trong một tenant hoặc một hệ thống nguồn, mô hình phải thể hiện namespace đó.

Ví dụ, tên người dùng `Nguyen Van An` không phải ID tốt vì nhiều người có thể trùng tên và một người có thể đổi tên. Email cũng có thể thay đổi hoặc được tái sử dụng theo chính sách của tổ chức. Một UUID do ứng dụng cấp thường phù hợp hơn làm định danh kỹ thuật:

```java
String personId = UUID.randomUUID().toString();
```

Nếu nghiệp vụ đã có mã bất biến và duy nhất, chẳng hạn mã sản phẩm toàn cục do hệ thống chủ quản cấp, mã đó cũng có thể làm ID. Hãy kiểm tra tính duy nhất trong đúng phạm vi nghiệp vụ trước khi chọn.

Không nên dùng ID nội bộ của Neo4j như `id()` hoặc `elementId()` làm mã nghiệp vụ được lưu trong API, URL, file xuất hoặc hệ thống bên ngoài. Các giá trị nội bộ này phục vụ việc định vị node trong cơ sở dữ liệu; vòng đời và bảo đảm ổn định của chúng không tương đương một ID do ứng dụng quản lý. Nếu một thực thể cần được tham chiếu lâu dài, hãy lưu một thuộc tính ID ổn định do ứng dụng sở hữu.

## 2. Chọn loại ID theo miền dữ liệu

Có ba lựa chọn thường gặp:

| Cách định danh | Ví dụ | Khi phù hợp | Điểm cần cân nhắc |
|---|---|---|---|
| ID tự nhiên (natural key) | Mã ISBN, mã sản phẩm toàn cục | Giá trị do nghiệp vụ cấp, bất biến và duy nhất | Không chọn thuộc tính có thể đổi hoặc chỉ duy nhất trong một phạm vi chưa mô hình hóa |
| ID thay thế (surrogate key) | UUID ngẫu nhiên | Ứng dụng cần một định danh độc lập với thuộc tính nghiệp vụ | Cần tạo và truyền ID nhất quán qua các luồng tạo dữ liệu |
| ID từ hệ thống ngoài | `sourceSystem` + `externalId` | Đồng bộ CRM, ERP, danh mục hoặc hệ thống đối tác | Phải giữ namespace để tránh hai nguồn cấp cùng một mã |

Một thực thể có thể có cả ID nội bộ ổn định lẫn mã từ hệ thống ngoài. Ví dụ, `Person.id` là UUID do nền tảng tạo, còn `externalId` là mã nhân viên từ hệ thống HR. ID nội bộ dùng làm danh tính trong graph; mã ngoài dùng để đồng bộ và tra cứu với nguồn dữ liệu.

Nếu mỗi hệ thống nguồn có thể cấp cùng một `externalId`, cặp `(sourceSystem, externalId)` mới là khóa nghiệp vụ duy nhất. Đừng áp constraint duy nhất riêng cho `externalId` trong trường hợp đó vì sẽ từ chối các mã hợp lệ đến từ nguồn khác nhau.

Với dữ liệu nhiều tenant, cần quyết định ID có duy nhất toàn hệ thống hay chỉ trong từng tenant. Nếu ID chỉ duy nhất trong tenant, dùng khóa ghép `(tenantId, externalId)` hoặc tạo UUID toàn cục làm `id` và giữ thêm cặp thuộc tính ngoài để đồng bộ. Không dựa vào quy ước ngầm mà không có constraint thể hiện phạm vi đó.

## 3. Ánh xạ ID ổn định trong Spring Data Neo4j

Spring Data Neo4j dùng `@Id` để đánh dấu thuộc tính định danh của node entity. Ví dụ dưới đây sử dụng UUID dạng chuỗi do ứng dụng cấp:

```java
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;
import org.springframework.data.annotation.Version;

import java.util.UUID;

@Node("Person")
public class Person {
    @Id
    private String id;

    @Version
    private Long version;

    private String name;
    private String email;
    private String sourceSystem;
    private String externalId;

    protected Person() {
    }

    public Person(String name, String email) {
        this.id = UUID.randomUUID().toString();
        this.name = name;
        this.email = email;
    }

    public String getId() {
        return id;
    }

    public String getName() {
        return name;
    }
}
```

Trong ví dụ:

- `@Node("Person")` ánh xạ lớp Java thành node có nhãn `Person`.
- `@Id` đánh dấu thuộc tính `id` là định danh mà Spring Data Neo4j sử dụng để nhận diện entity.
- Constructor tạo UUID trước khi lưu, vì vậy ID không phụ thuộc vào một lần insert để có giá trị.
- `@Version` bật cơ chế optimistic locking. Dùng kiểu wrapper `Long` để trạng thái ban đầu là `null`; Spring Data có thể dùng thuộc tính version này trong chiến lược xác định entity mới. Sau khi lưu, version được quản lý để phát hiện cập nhật dựa trên phiên bản cũ.

Với ID được gán sẵn, cần chú ý cách Spring Data xác định entity mới hay đã tồn tại. Nếu chỉ nhìn vào `id` khác `null`, một entity mới có thể bị xem như entity đã lưu. Một thuộc tính `@Version` kiểu wrapper chưa có giá trị giúp phân biệt trạng thái mới và hỗ trợ optimistic locking. Một lựa chọn khác là triển khai `Persistable` và cung cấp `isNew()` theo vòng đời của ứng dụng. Hãy chọn một cơ chế rõ ràng và kiểm tra với phiên bản Spring Data Neo4j đang sử dụng.

`@Version` không thay thế constraint duy nhất. Version giúp phát hiện xung đột cập nhật đồng thời trên entity; constraint bảo đảm không có hai node cùng nhãn mang một giá trị ID bị trùng. Hai cơ chế giải quyết hai vấn đề khác nhau.

## 4. Bảo vệ tính duy nhất bằng constraint của Neo4j

Kiểm tra ID ở Java là hữu ích nhưng chưa đủ. Hai request có thể chạy đồng thời trên nhiều instance ứng dụng; cả hai cùng kiểm tra thấy chưa có ID rồi cùng thử tạo node. Cơ sở dữ liệu phải là nơi thực thi quy tắc duy nhất.

Tạo unique constraint cho `Person.id`:

```cypher
CREATE CONSTRAINT person_id_unique IF NOT EXISTS
FOR (p:Person)
REQUIRE p.id IS UNIQUE;
```

Và cho `Project.id`:

```cypher
CREATE CONSTRAINT project_id_unique IF NOT EXISTS
FOR (p:Project)
REQUIRE p.id IS UNIQUE;
```

Constraint gắn với nhãn và thuộc tính. Hai node `Person` không thể có cùng `id`, trong khi một node `Person` và một node `Project` có thể dùng cùng chuỗi ID nếu mô hình không đặt thêm quy tắc khác. Vì vậy, hãy chọn tên thuộc tính và phạm vi constraint theo từng loại thực thể.

Nếu mã ngoài chỉ duy nhất trong một hệ thống nguồn, tạo constraint ghép:

```cypher
CREATE CONSTRAINT person_source_external_unique IF NOT EXISTS
FOR (p:Person)
REQUIRE (p.sourceSystem, p.externalId) IS UNIQUE;
```

Với dữ liệu nhiều tenant mà mã ngoài chỉ duy nhất trong tenant, có thể dùng:

```cypher
CREATE CONSTRAINT person_tenant_external_unique IF NOT EXISTS
FOR (p:Person)
REQUIRE (p.tenantId, p.externalId) IS UNIQUE;
```

Unique constraint chỉ kiểm soát các giá trị được lưu; nó không tự bảo đảm mọi node đều có thuộc tính ID bắt buộc. Ứng dụng cần kiểm tra ID trước khi ghi. Nếu phiên bản và edition Neo4j triển khai hỗ trợ property existence hoặc node key constraint, có thể bổ sung quy tắc bắt buộc tồn tại tương ứng. Dù vậy, constraint duy nhất vẫn là lớp bảo vệ cần thiết cho khóa định danh.

Khi tạo constraint trên dữ liệu đã có, Neo4j sẽ kiểm tra các node hiện tại. Nếu đã tồn tại ID trùng, thao tác tạo constraint thất bại. Hãy xử lý dữ liệu trùng trước: xác định node nào là bản ghi chuẩn, chuyển các relationship sang node chuẩn, hợp nhất thuộc tính theo quy tắc nghiệp vụ rồi xóa bản sao. Không xóa node trùng trước khi bảo toàn các quan hệ đang tham chiếu tới nó.

## 5. Dữ liệu dùng chung: một node, nhiều relationship

Giả sử một người có thể tham gia nhiều dự án. Thông tin tên và email là thuộc tính của người; tên dự án là thuộc tính của dự án; vai trò và ngày bắt đầu tham gia là thông tin riêng của mối quan hệ giữa người đó với một dự án.

Mô hình đồ thị có thể biểu diễn như sau:

```text
(Person)-[:CONTRIBUTES_TO {role, joinedOn}]->(Project)
```

Một `Person` được tạo một lần và có thể nối tới nhiều `Project`. Khi người đó đổi email, ứng dụng cập nhật một node. Khi người đó đổi vai trò trong một dự án, ứng dụng cập nhật relationship tương ứng mà không ảnh hưởng tới vai trò trong dự án khác.

Ví dụ ánh xạ relationship có thuộc tính bằng Spring Data Neo4j:

```java
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;
import org.springframework.data.neo4j.core.schema.Relationship;
import org.springframework.data.neo4j.core.schema.RelationshipId;
import org.springframework.data.neo4j.core.schema.RelationshipProperties;
import org.springframework.data.neo4j.core.schema.TargetNode;

import java.time.LocalDate;
import java.util.HashSet;
import java.util.Set;

@Node("Project")
public class Project {
    @Id
    private String id;

    private String name;

    @Relationship(
        type = "CONTRIBUTES_TO",
        direction = Relationship.Direction.INCOMING
    )
    private Set<Contribution> contributors = new HashSet<>();

    // Constructor, getter và setter được lược bớt.
}

@RelationshipProperties
public class Contribution {
    @RelationshipId
    private Long id;

    private String role;
    private LocalDate joinedOn;

    @TargetNode
    private Person person;

    // Constructor, getter và setter được lược bớt.
}
```

`Project.contributors` dùng hướng `INCOMING` vì relationship trong đồ thị đi từ `Person` vào `Project`. `Contribution` giữ các thuộc tính phụ thuộc vào cặp người–dự án. `@RelationshipId` là định danh relationship do SDN ánh xạ; không dùng nó làm mã nghiệp vụ hoặc khóa đồng bộ. `@TargetNode` trỏ tới node `Person` đã được định danh.

Không đưa `role` vào `Person`, bởi một người có thể giữ vai trò khác nhau trong từng dự án. Cũng không đưa `joinedOn` vào `Project`, bởi mỗi người có ngày tham gia khác nhau. Quy tắc thiết kế hữu ích là: thuộc tính mô tả một thực thể nằm trên node; thuộc tính mô tả một lần hoặc một kiểu liên kết giữa các thực thể nằm trên relationship.

## 6. Tạo hoặc tìm node dùng chung bằng MERGE

Khi đồng bộ dữ liệu hoặc xử lý một request có thể được gửi lại, `MERGE` giúp tìm node theo khóa rồi tạo nếu chưa có. Hãy dùng thuộc tính định danh ổn định trong mẫu `MERGE`:

```cypher
MERGE (p:Person {id: $personId})
ON CREATE SET
    p.name = $name,
    p.email = $email
ON MATCH SET
    p.name = $name,
    p.email = $email
RETURN p;
```

Không đưa tất cả thuộc tính có thể thay đổi vào mẫu `MERGE`:

```cypher
// Tránh cách này khi name hoặc email có thể thay đổi.
MERGE (p:Person {id: $personId, name: $name, email: $email})
RETURN p;
```

`MERGE` so khớp toàn bộ mẫu được khai báo. Nếu cùng `personId` nhưng tên hoặc email khác, mẫu có thể không khớp node hiện tại và tạo một node khác. Dùng ID ổn định trong `MERGE`, sau đó dùng `ON CREATE SET` hoặc `ON MATCH SET` để xử lý thuộc tính theo chính sách cập nhật.

Để nối người vào dự án, trước tiên tìm hai node bằng ID rồi tạo relationship:

```cypher
MATCH (p:Person {id: $personId})
MATCH (project:Project {id: $projectId})
MERGE (p)-[r:CONTRIBUTES_TO]->(project)
ON CREATE SET
    r.role = $role,
    r.joinedOn = date()
ON MATCH SET
    r.role = $role
RETURN p, r, project;
```

Truy vấn này giả định `Person` và `Project` đã tồn tại. Nếu một trong hai node không được tìm thấy, `MATCH` không tạo dòng kết quả và relationship sẽ không được tạo. Có thể dùng một quy trình tạo/tìm node trước, rồi nối relationship trong cùng transaction nghiệp vụ.

Kết hợp `MERGE` với unique constraint trên ID giúp tránh tạo nhiều node cùng danh tính, kể cả khi nhiều request đồng thời. `MERGE` không thay thế constraint: constraint mới là quy tắc được cơ sở dữ liệu thực thi trên toàn bộ dữ liệu và các transaction.

## 7. Repository và transaction cho dữ liệu được chia sẻ

Repository dùng ID ổn định làm kiểu định danh:

```java
import org.springframework.data.neo4j.repository.Neo4jRepository;

public interface PersonRepository
        extends Neo4jRepository<Person, String> {
}

public interface ProjectRepository
        extends Neo4jRepository<Project, String> {
}
```

Kiểu `String` trong `Neo4jRepository<Person, String>` phải khớp với kiểu thuộc tính `@Id`. Khi một service cần tạo/cập nhật người, tìm dự án và tạo relationship, đặt các thao tác thuộc cùng một nghiệp vụ trong transaction:

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ProjectMembershipService {
    private final PersonRepository personRepository;
    private final ProjectRepository projectRepository;

    public ProjectMembershipService(
            PersonRepository personRepository,
            ProjectRepository projectRepository) {
        this.personRepository = personRepository;
        this.projectRepository = projectRepository;
    }

    @Transactional
    public void verifySharedEntities(String personId, String projectId) {
        Person person = personRepository.findById(personId)
            .orElseThrow(() -> new IllegalArgumentException("Person not found"));
        Project project = projectRepository.findById(projectId)
            .orElseThrow(() -> new IllegalArgumentException("Project not found"));

        // Thực hiện nghiệp vụ tạo/cập nhật relationship tại đây.
        // Các thay đổi graph thuộc transaction của phương thức này.
    }
}
```

Ví dụ minh họa cách lấy hai entity dùng chung trong một transaction; phần cập nhật relationship có thể được thực hiện bằng cách sửa quan hệ đã ánh xạ rồi lưu aggregate, hoặc gọi một repository query Cypher chuyên biệt. Chọn một cách nhất quán với quy mô graph và vòng đời aggregate. Khi dùng query Cypher trực tiếp, hãy giữ thao tác tìm node và tạo relationship trong cùng transaction nếu nghiệp vụ yêu cầu tính nguyên tử.

Khi nhiều aggregate cùng tham chiếu một `Person`, không nên tải và lưu một đồ thị đối tượng quá lớn chỉ để thay đổi một thuộc tính của người đó. Cập nhật node dùng chung qua repository hoặc câu Cypher chuyên biệt, và chỉ tải các relationship cần thiết. Với màn hình đọc, projection giúp trả về đúng dữ liệu cần dùng mà không phải dựng toàn bộ graph.

## 8. Xử lý cập nhật đồng thời và đồng bộ dữ liệu

Hai vấn đề thường xuất hiện khi nhiều request cùng thao tác trên dữ liệu dùng chung:

**Trùng danh tính khi tạo đồng thời.** Hai request có thể cùng cố tạo một `Person` với cùng ID. Unique constraint chặn hai node trùng khóa. Ứng dụng cần xử lý lỗi constraint theo quy tắc nghiệp vụ, chẳng hạn đọc lại node đã được request kia tạo hoặc retry thao tác phù hợp. Không dựa vào bước `existsById()` trước khi `save()` như một khóa đồng bộ, vì giữa hai lệnh vẫn có thể có transaction khác ghi cùng ID.

**Ghi đè thay đổi của request khác.** Hai request đọc cùng một version rồi cùng cập nhật node. `@Version` cho phép SDN áp dụng optimistic locking: thao tác lưu dùng version hiện tại để phát hiện entity đã bị thay đổi kể từ lúc đọc. Khi có xung đột, ứng dụng cần quyết định đọc lại và áp dụng lại thay đổi, trả lỗi xung đột hoặc thực hiện chính sách hợp nhất. Không nên tự động retry vô hạn.

Với dữ liệu từ hệ thống ngoài, hãy xác định rõ nguồn nào có quyền sở hữu từng thuộc tính. Ví dụ, hệ thống HR quản lý tên chính thức và mã nhân viên, còn ứng dụng dự án quản lý vai trò tham gia. Khi nhận sự kiện đồng bộ, cập nhật các trường thuộc quyền của nguồn gửi; tránh để một nguồn ghi đè dữ liệu do nguồn khác quản lý.

Để xử lý sự kiện gửi lặp, dùng ID nguồn ổn định hoặc cặp namespace và external ID để xác định node. Dùng `MERGE` theo khóa đó, rồi cập nhật theo phiên bản hoặc timestamp nghiệp vụ nếu hệ thống nguồn cung cấp. Nếu sự kiện có thể đến sai thứ tự, cần quy tắc từ chối dữ liệu cũ thay vì luôn ghi đè bằng payload mới nhận.

## 9. Các lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Dùng tên hoặc email làm ID dù có thể thay đổi | Một người có thể bị xem là nhiều thực thể hoặc không tìm được sau khi đổi thông tin | Dùng UUID hoặc mã bất biến; lưu tên/email như thuộc tính |
| Dùng ID nội bộ Neo4j làm ID công khai | Hệ thống ngoài phụ thuộc vào định danh nội bộ không có bảo đảm nghiệp vụ phù hợp | Tạo thuộc tính ID do ứng dụng quản lý và đặt unique constraint |
| Chỉ kiểm tra trùng ở Java | Hai request đồng thời có thể cùng tạo bản ghi trùng | Đặt unique constraint trong Neo4j |
| `MERGE` bằng cả thuộc tính thay đổi | Có thể tạo node mới khi tên/email thay đổi | `MERGE` theo ID ổn định rồi `SET` thuộc tính |
| Lưu bản sao cùng một người trong mỗi dự án | Dữ liệu phân mảnh và cập nhật không nhất quán | Dùng một node `Person`, nhiều relationship tới `Project` |
| Đặt vai trò của dự án trên node người | Không thể biểu diễn vai trò khác nhau theo từng dự án | Đặt vai trò trên relationship có thuộc tính |
| Không mô hình hóa namespace của external ID | Mã từ hai hệ thống có thể va chạm | Dùng unique constraint ghép `sourceSystem` và `externalId` |
| Bỏ qua optimistic locking | Cập nhật đồng thời có thể ghi đè thay đổi | Dùng `@Version` và xử lý xung đột theo nghiệp vụ |

## 10. Quy trình thiết kế trước khi triển khai

Khi thêm một loại node hoặc quan hệ mới, hãy thực hiện theo trình tự:

1. Xác định thực thể trong thế giới nghiệp vụ và phân biệt nó với một bản ghi hoặc sự kiện.
2. Chọn ID bất biến, xác định phạm vi duy nhất và namespace nếu có.
3. Khai báo `@Id` trong entity và chọn cơ chế xác định entity mới khi ID được gán trước.
4. Tạo unique constraint trong Neo4j cho ID và các khóa nghiệp vụ cần bảo vệ.
5. Phân loại thuộc tính: thuộc tính riêng của node hay thuộc tính của relationship.
6. Thiết kế thao tác tạo/tìm dùng chung bằng `MERGE` theo khóa ổn định và cập nhật thuộc tính riêng.
7. Xác định transaction boundary, chiến lược optimistic locking và cách xử lý xung đột.
8. Kiểm tra các trường hợp tạo đồng thời, đổi thuộc tính mô tả, nhận sự kiện lặp và tham chiếu từ nhiều aggregate.

Thiết kế tốt giúp dữ liệu đồ thị giữ được một danh tính nhất quán cho mỗi thực thể, đồng thời vẫn thể hiện chính xác thông tin phụ thuộc vào từng quan hệ. Trong Spring Data Neo4j, `@Id`, `@Version`, relationship mapping và repository là phần ánh xạ ở ứng dụng; unique constraint và transaction của Neo4j bảo vệ các quy tắc quan trọng ở tầng dữ liệu.

## 11. Tự kiểm tra

1. Vì sao tên hoặc email thường không phải ID ổn định cho một node `Person`?
2. Khi ID đến từ nhiều hệ thống nguồn, vì sao cần kết hợp `sourceSystem` với `externalId`?
3. Unique constraint bảo vệ điều gì mà bước `existsById()` trong Java không thể bảo đảm khi có request đồng thời?
4. Khi dùng ID do ứng dụng gán trước, `@Version` kiểu `Long` giúp Spring Data nhận diện entity mới và phát hiện xung đột như thế nào?
5. Vì sao `role` nên nằm trên relationship `CONTRIBUTES_TO` trong ví dụ người tham gia nhiều dự án?
6. Vì sao nên dùng `MERGE` theo ID ổn định rồi `SET` tên/email thay vì đưa tất cả thuộc tính vào mẫu `MERGE`?
7. Nếu phát hiện hai node `Person` trùng mã nhưng đang có nhiều relationship, cần làm gì trước khi tạo unique constraint?
