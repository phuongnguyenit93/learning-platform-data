# Sinh UUID bằng UUIDStringGenerator

Trong Spring Data Neo4j (SDN), mỗi node entity cần một thuộc tính định danh để repository và cơ chế ánh xạ nhận diện đúng thực thể. Neo4j có định danh nội bộ riêng cho node, nhưng định danh nội bộ đó không nên trở thành mã tham chiếu lâu dài của ứng dụng. Khi muốn dùng UUID được lưu thành thuộc tính trên node, SDN cung cấp **UUIDStringGenerator**.

Generator này phù hợp khi ứng dụng cần một ID dạng chuỗi, độc lập với ID nội bộ của Neo4j và có thể dùng trong API, thông điệp hoặc tham chiếu giữa các dịch vụ. **UUIDStringGenerator** tạo UUID ở phía ứng dụng trong quá trình SDN lưu entity; SDN ghi giá trị đó vào property được đánh dấu **@Id**. Bài học tập trung vào cách khai báo generator, lưu entity, truy vấn theo UUID và duy trì quy tắc định danh nhất quán.

## UUIDStringGenerator giải quyết điều gì?

UUID (Universally Unique Identifier) là định danh có không gian giá trị rất lớn, thường được biểu diễn dưới dạng chuỗi 36 ký tự gồm các nhóm hex và dấu gạch nối, ví dụ:

~~~text
7d9f5a31-8a42-4b0c-9a18-1c5d7e2f4b60
~~~

UUID giúp ứng dụng tạo ra định danh khó trùng lặp mà không cần lấy số thứ tự từ một database trung tâm. **UUIDStringGenerator** sử dụng bộ sinh UUID của Java và trả về giá trị chuỗi để SDN gán cho thuộc tính định danh của entity.

Khai báo generator tường minh giúp phân biệt hai cách dùng ID:

| Cách khai báo | Ý nghĩa |
|---|---|
| **@Id @GeneratedValue** | Dùng generator mặc định của SDN, thường gắn với định danh nội bộ do Neo4j quản lý |
| **@Id @GeneratedValue(UUIDStringGenerator.class)** | Yêu cầu SDN sinh UUID dạng String và lưu vào thuộc tính ID của node |
| **@Id** không có **@GeneratedValue** | Ứng dụng phải cung cấp giá trị ID trước khi lưu |

UUID được lưu như một property của node, chẳng hạn **p.id**. Neo4j vẫn có định danh nội bộ của node ở tầng lưu trữ; hai loại định danh này tồn tại song song. Khi repository dùng UUID làm ID, các thao tác của SDN dựa trên property được đánh dấu **@Id**.

## Khai báo UUIDStringGenerator trong entity

Để dùng generator, thuộc tính ID cần có kiểu **String**, được đánh dấu bằng cả **@Id** và **@GeneratedValue(UUIDStringGenerator.class)**.

~~~java
import org.springframework.data.neo4j.core.schema.GeneratedValue;
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;
import org.springframework.data.neo4j.core.schema.UUIDStringGenerator;

@Node("Person")
public class Person {

    @Id
    @GeneratedValue(UUIDStringGenerator.class)
    private String id;

    private String fullName;
    private String email;

    protected Person() {
        // Dành cho cơ chế ánh xạ của Spring Data Neo4j.
    }

    public Person(String fullName, String email) {
        this.fullName = fullName;
        this.email = email;
    }

    public String getId() {
        return id;
    }

    public String getFullName() {
        return fullName;
    }

    public String getEmail() {
        return email;
    }
}
~~~

Các điểm cần chú ý:

- **@Node("Person")** ánh xạ entity vào node có label **Person**.
- **@Id** xác định thuộc tính mà SDN dùng làm định danh entity.
- **@GeneratedValue(UUIDStringGenerator.class)** chỉ định generator tạo UUID dạng chuỗi khi entity được lưu.
- **id** có kiểu **String**, phù hợp với giá trị do generator cung cấp.
- Constructor tạo mới không nhận tham số **id**. Ứng dụng để generator cấp ID khi lưu entity.

Không tự gán UUID vào **id** khi đang dùng generator này. Nếu ứng dụng chủ động gán ID, hãy bỏ **@GeneratedValue** và chọn chiến lược định danh do ứng dụng quản lý. Tránh kết hợp hai cơ chế sinh ID trên cùng một thuộc tính vì sẽ khiến vòng đời định danh khó dự đoán.

## Lưu entity và nhận ID được sinh

Khai báo repository với kiểu ID là **String**, vì kiểu generic thứ hai của **Neo4jRepository** phải khớp với kiểu thuộc tính **@Id**:

~~~java
import java.util.Optional;
import org.springframework.data.neo4j.repository.Neo4jRepository;

public interface PersonRepository extends Neo4jRepository<Person, String> {

    Optional<Person> findByEmail(String email);
}
~~~

Khi tạo entity, truyền các thuộc tính nghiệp vụ vào constructor rồi gọi **save**:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PersonService {

    private final PersonRepository people;

    public PersonService(PersonRepository people) {
        this.people = people;
    }

    @Transactional
    public Person create(String fullName, String email) {
        Person person = new Person(fullName, email);
        return people.save(person);
    }
}
~~~

Trong quá trình **save**, SDN gọi **UUIDStringGenerator** ở phía ứng dụng, sau đó ghi giá trị UUID vào property ID của node. Giá trị này có thể đọc từ entity được trả về bởi **save**. Vì vậy, hãy dùng đối tượng trả về để lấy ID sau khi lưu:

~~~java
Person saved = personService.create("Lan Nguyen", "lan@example.test");

String personId = saved.getId();
if (personId == null || personId.isBlank()) {
    throw new IllegalStateException("Person ID was not generated");
}
~~~

Không dùng ID trước khi entity được lưu. Trước thao tác **save**, đối tượng mới chưa có giá trị **id** do generator cấp. Sau khi lưu thành công, có thể dùng UUID để tra cứu:

~~~java
Person person = people.findById(personId)
    .orElseThrow(() -> new PersonNotFoundException(personId));
~~~

Với kiểu ID **String**, các phương thức kế thừa như **findById**, **existsById** và **deleteById** nhận UUID dạng chuỗi. Chúng không nhận ID nội bộ của Neo4j và cũng không tự tra cứu theo email hay mã nghiệp vụ.

## Bảo vệ tính duy nhất bằng constraint

UUID có xác suất trùng rất thấp, nhưng quy tắc duy nhất vẫn nên được thực thi ở database. Tạo uniqueness constraint cho thuộc tính ID:

~~~cypher
CREATE CONSTRAINT person_id_unique IF NOT EXISTS
FOR (p:Person)
REQUIRE p.id IS UNIQUE;
~~~

Constraint này bảo đảm không có hai node **Person** cùng mang một giá trị **id** khác null. Nó cũng bảo vệ dữ liệu khi có nhiều ứng dụng hoặc nhiều đường ghi cùng truy cập database.

Nếu node có thêm mã nghiệp vụ, hãy tạo constraint riêng cho thuộc tính đó khi quy tắc nghiệp vụ yêu cầu duy nhất:

~~~cypher
CREATE CONSTRAINT person_employee_code_unique IF NOT EXISTS
FOR (p:Person)
REQUIRE p.employeeCode IS UNIQUE;
~~~

**id** và **employeeCode** có ý nghĩa khác nhau. UUID là khóa kỹ thuật ổn định của entity; mã nhân viên là khóa nghiệp vụ có thể được dùng trong quy trình tổ chức. Không dùng một constraint thay cho constraint còn lại.

Trước khi tạo constraint trên dữ liệu đã tồn tại, cần kiểm tra các node thiếu ID hoặc có giá trị trùng. Neo4j sẽ từ chối tạo uniqueness constraint nếu dữ liệu hiện tại vi phạm quy tắc. Với database mới, nên đưa câu lệnh constraint vào migration hoặc quy trình khởi tạo schema để môi trường phát triển, kiểm thử và production dùng cùng quy tắc.

## Tra cứu entity theo UUID

Khi đã có UUID, repository có thể tra cứu trực tiếp bằng **findById(String id)** được kế thừa từ **Neo4jRepository**; không cần khai báo lại phương thức này. Nếu cần tra cứu theo một thuộc tính khác, khai báo query method riêng, chẳng hạn **findByEmail(String email)** như trong ví dụ repository ở trên.

Ví dụ sử dụng:

~~~java
Person person = people.findById("7d9f5a31-8a42-4b0c-9a18-1c5d7e2f4b60")
    .orElseThrow(() -> new PersonNotFoundException("Person not found"));
~~~

Không chuyển UUID thành số hoặc cắt bớt chuỗi để tạo khóa rút gọn. Hãy giữ nguyên giá trị chuỗi đã được sinh và truyền nó qua các tầng ứng dụng dưới dạng cùng một định dạng.

Nếu dùng Cypher tùy chỉnh, truy vấn theo property UUID:

~~~cypher
MATCH (p:Person {id: $id})
RETURN p;
~~~

Trong Spring Data Neo4j, tham số của truy vấn tùy chỉnh phải được truyền bằng cơ chế bind parameter của repository hoặc **Neo4jClient**. Không nối UUID vào chuỗi Cypher bằng phép ghép chuỗi.

Nếu muốn viết truy vấn tường minh thay cho query method dẫn xuất, bổ sung phương thức sau vào **PersonRepository**. Hai import được dùng cho annotation và tham số:

~~~java
import java.util.Optional;
import org.springframework.data.neo4j.repository.query.Query;
import org.springframework.data.repository.query.Param;

@Query("MATCH (p:Person {id: $id}) RETURN p")
Optional<Person> findPersonByUuid(@Param("id") String id);
~~~

Tên property trong Cypher phải khớp với property được lưu trên node. Nếu đổi tên thuộc tính ID hoặc dùng mapping tùy chỉnh, cần đồng bộ lại truy vấn Cypher và schema.

## Kết hợp UUID với relationship

Khi mô hình hóa đồ thị, UUID nhận diện từng node entity. Relationship kết nối các node đó theo ý nghĩa miền nghiệp vụ. SDN quản lý quan hệ thông qua thuộc tính được đánh dấu **@Relationship**; không cần tự chèn UUID của hai node vào relationship chỉ để SDN nhận diện hai đầu mối.

Ví dụ một người thuộc về một phòng ban:

~~~java
import org.springframework.data.neo4j.core.schema.GeneratedValue;
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;
import org.springframework.data.neo4j.core.schema.UUIDStringGenerator;

@Node("Department")
public class Department {

    @Id
    @GeneratedValue(UUIDStringGenerator.class)
    private String id;

    private String name;

    protected Department() {
    }

    public Department(String name) {
        this.name = name;
    }

    public String getId() {
        return id;
    }

    public String getName() {
        return name;
    }
}
~~~

Trong entity **Person**, import **org.springframework.data.neo4j.core.schema.Relationship** và có thể ánh xạ quan hệ tới **Department**:

~~~java
@Relationship(type = "WORKS_IN")
private Department department;
~~~

Khi lưu một graph gồm nhiều entity mới, SDN xử lý ID cho các node theo generator đã khai báo trên từng entity. Nếu **Person** và **Department** đều dùng **UUIDStringGenerator**, mỗi node sẽ nhận UUID riêng. Nếu chỉ một entity khai báo generator, không được giả định entity còn lại cũng tự động có UUID.

Khi cần lưu thuộc tính trên relationship, có thể dùng **@RelationshipProperties** và **@TargetNode** theo mô hình SDN. UUID của node đầu và node đích vẫn thuộc về hai entity; thuộc tính định danh của relationship là vấn đề riêng tùy loại mô hình. Với một quan hệ có vòng đời độc lập như hợp đồng hoặc lần phân công, cân nhắc biểu diễn quan hệ đó thành node trung gian có UUID riêng.

## Dùng UUID nhất quán khi ghi bằng Cypher

Repository **save** biết cách dùng generator đã khai báo trong entity. Tuy nhiên, lệnh Cypher viết tay, script import hoặc dịch vụ khác không tự động chạy annotation của SDN. Những đường ghi này phải tuân theo cùng quy tắc định danh.

Nếu tạo node trực tiếp bằng Cypher, có thể dùng hàm **randomUUID()** của Neo4j:

~~~cypher
MERGE (p:Person {employeeCode: $employeeCode})
ON CREATE SET
    p.id = randomUUID(),
    p.createdAt = datetime()
SET
    p.fullName = $fullName,
    p.email = $email
RETURN p;
~~~

Ở đây, **randomUUID()** tạo UUID trong database khi node được tạo mới. **MERGE** dựa trên khóa nghiệp vụ ổn định để tránh tạo node mới khi cập nhật tên hoặc email. Constraint trên **id** bảo vệ thuộc tính định danh kỹ thuật; constraint trên **employeeCode** bảo vệ quy tắc duy nhất của mã nghiệp vụ.

Không tạo UUID mới trong phần **SET** chạy mỗi lần cập nhật, vì điều đó sẽ thay đổi ID của entity và làm hỏng các tham chiếu đã lưu. Chỉ sinh ID khi tạo node lần đầu. Với các đường ghi kết hợp repository và Cypher, hãy thống nhất tên property ID, kiểu dữ liệu và quy tắc tạo mới để mọi entity đều có thể được SDN ánh xạ.

## Kiểm thử hành vi sinh UUID

Một integration test với Neo4j thực tế hoặc Testcontainers có thể xác nhận generator hoạt động với phiên bản SDN và Neo4j mà dự án đang sử dụng. Ví dụ dưới đây minh họa các điều cần kiểm tra; cấu hình Testcontainers và dependency kiểm thử được bổ sung theo dự án:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.neo4j.DataNeo4jTest;

@DataNeo4jTest
class PersonRepositoryTest {

    @Autowired
    private PersonRepository people;

    @Test
    void generatesDifferentIdsForNewPeople() {
        Person first = people.save(new Person("Lan Nguyen", "lan@example.test"));
        Person second = people.save(new Person("Minh Tran", "minh@example.test"));

        assertThat(first.getId()).isNotBlank();
        assertThat(second.getId()).isNotBlank();
        assertThat(first.getId()).isNotEqualTo(second.getId());

        assertThat(people.findById(first.getId())).isPresent();
        assertThat(people.findById(second.getId())).isPresent();
    }
}
~~~

Test này cần database Neo4j có thể truy cập và schema phù hợp. Nếu dùng uniqueness constraint, hãy khởi tạo constraint trong môi trường kiểm thử trước khi chạy test. Không nên chỉ kiểm tra UUID có đúng 36 ký tự rồi kết luận generator hoạt động: cần xác nhận ID được ghi vào node, được trả về entity và dùng lại được trong repository.

## Khi nào nên dùng UUIDStringGenerator?

**UUIDStringGenerator** phù hợp khi:

- Muốn thuộc tính ID của entity có kiểu **String** và được sinh tự động khi lưu.
- Cần định danh không phụ thuộc vào ID nội bộ của một Neo4j instance.
- Cần đưa ID vào API, event hoặc tham chiếu giữa các thành phần ứng dụng.
- Muốn nhiều node cùng loại có thể được tạo từ nhiều luồng xử lý mà không phải cấp số thứ tự tập trung.

Cần cân nhắc các điểm sau:

- UUID dạng chuỗi chiếm nhiều dung lượng hơn một số nguyên nhỏ; index trên thuộc tính ID cũng cần dung lượng tương ứng.
- UUID ngẫu nhiên không thể hiện thứ tự tạo. Không dùng UUID làm căn cứ sắp xếp theo thời gian; hãy lưu thuộc tính thời gian riêng.
- UUID khó đọc và không mang ý nghĩa nghiệp vụ. Nếu cần mã dễ nhớ cho người dùng, lưu thêm business key.
- **UUIDStringGenerator** tạo giá trị ở phía ứng dụng; Neo4j lưu UUID thành property trên node. Nếu ghi node bằng Cypher trực tiếp, đường ghi đó phải tự cung cấp ID, chẳng hạn dùng tham số từ ứng dụng hoặc hàm **randomUUID()** của Neo4j.
- Generator không tự thay thế uniqueness constraint hoặc quy tắc xác thực dữ liệu của ứng dụng.

Nếu cần tạo ID trước khi gửi một lệnh ghi hoặc phát hành event, UUID có thể được sinh ở tầng ứng dụng bằng **java.util.UUID**. Đó là một chiến lược khác: ứng dụng sở hữu việc tạo ID và entity chỉ dùng **@Id** mà không dùng **@GeneratedValue**. Không trộn cách sinh ID ở Java với **UUIDStringGenerator** trên cùng thuộc tính.

## Chuyển entity đang dùng ID nội bộ sang UUID

Nếu entity hiện đang dùng **@GeneratedValue** mặc định hoặc ID kiểu số, việc đổi sang UUID cần được thực hiện như một thay đổi schema và hợp đồng dữ liệu:

1. **Kiểm kê nơi dùng ID cũ.** Tìm các repository, Cypher query, API, message, cache và hệ thống tích hợp đang giữ ID nội bộ hoặc kiểu ID cũ.
2. **Bổ sung property UUID cho dữ liệu hiện có.** Sinh một UUID cho mỗi node còn thiếu giá trị, bảo đảm mỗi node giữ nguyên UUID sau các lần chạy migration.
3. **Kiểm tra dữ liệu trước khi thêm constraint.** Đảm bảo không có node thiếu UUID và không có hai node cùng UUID.
4. **Tạo uniqueness constraint.** Tạo constraint trên property UUID sau khi dữ liệu đã được backfill và xác minh.
5. **Cập nhật entity và repository.** Đổi thuộc tính **@Id** sang **String** với **@GeneratedValue(UUIDStringGenerator.class)** nếu các node mới sẽ được SDN cấp UUID; đổi kiểu ID generic của repository từ kiểu cũ sang **String**.
6. **Chuyển consumer sang ID mới.** Cập nhật API, event và dữ liệu tham chiếu. Có thể duy trì ánh xạ ID cũ sang UUID trong giai đoạn chuyển tiếp.
7. **Xác minh rồi mới ngừng dùng ID cũ.** Chỉ loại bỏ cơ chế tương thích sau khi mọi consumer đã chuyển đổi.

Không áp dụng generator mới lên dữ liệu cũ rồi kỳ vọng SDN tự điền UUID cho mọi node đã tồn tại. Generator phục vụ việc tạo ID cho entity mới; dữ liệu cũ cần được migration rõ ràng. Nếu một node đang có property ID, không ghi đè UUID mới trong mỗi lần cập nhật.

## Lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Khai báo thuộc tính ID kiểu **Long** với **UUIDStringGenerator** | Kiểu dữ liệu không khớp với UUID dạng chuỗi | Dùng **String** cho thuộc tính ID |
| Quên **@GeneratedValue(UUIDStringGenerator.class)** | SDN không biết phải dùng UUID generator | Khai báo generator trên thuộc tính **@Id** |
| Vừa gán ID thủ công vừa dùng generator | Quy tắc tạo ID không nhất quán | Chọn một cơ chế sinh ID duy nhất |
| Gọi **getId()** trước khi lưu entity mới | ID chưa được generator cấp | Lấy ID từ entity trả về sau **save** |
| Repository khai báo generic ID sai kiểu | Lệnh tìm/xóa theo ID không khớp entity | Dùng **Neo4jRepository<Person, String>** |
| Không tạo uniqueness constraint | Đường ghi khác có thể tạo ID trùng do lỗi hoặc dữ liệu sai | Tạo constraint trên property ID |
| Script Cypher không gán property ID | Node không theo quy tắc ánh xạ của entity | Dùng **randomUUID()** khi tạo node trực tiếp |
| Sinh lại UUID khi cập nhật node | Các tham chiếu cũ trỏ tới ID không còn tồn tại | Chỉ sinh ID khi tạo mới và giữ ổn định suốt vòng đời |
| Dùng UUID để biểu diễn mã nghiệp vụ hoặc thời gian | ID khó hiểu và không có thứ tự thời gian | Lưu business key và timestamp thành thuộc tính riêng |

## Tự kiểm tra

Với entity **Person** có thuộc tính **String id** được đánh dấu **@Id** và **@GeneratedValue(UUIDStringGenerator.class)**, hãy trả lời:

1. Vì sao thuộc tính **id** phải có kiểu **String**?
2. Ở thời điểm nào entity mới có giá trị ID được sinh?
3. Repository cần khai báo kiểu ID generic nào?
4. Vì sao nên tạo uniqueness constraint trên property ID dù UUID rất khó trùng?
5. Khi tạo node bằng Cypher trực tiếp, làm thế nào để bảo đảm node vẫn có ID tương thích với entity?
6. Vì sao không nên sinh lại UUID khi cập nhật một node đã tồn tại?
7. Nếu API cần một mã nhân viên dễ đọc, có nên thay UUID bằng mã nhân viên không? Hãy giải thích cách lưu hai giá trị theo hai mục đích riêng.

Khi dùng **UUIDStringGenerator**, hãy khai báo generator tường minh trên thuộc tính **@Id**, để SDN tạo ID ở phía ứng dụng khi lưu entity và giữ nguyên giá trị đó trong suốt vòng đời node. Kết hợp uniqueness constraint, repository có kiểu ID **String** và quy tắc ghi Cypher thống nhất để định danh hoạt động đúng trong toàn bộ tầng dữ liệu đồ thị.

