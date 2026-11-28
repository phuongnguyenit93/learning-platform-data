# Định danh nghiệp vụ và định danh nội bộ của cơ sở dữ liệu

## Vì sao cần phân biệt hai loại định danh?

Khi xây dựng tầng dữ liệu đồ thị bằng Spring Data Neo4j, mỗi node cần có một định danh để ứng dụng tìm lại và cập nhật đúng thực thể. Neo4j cũng quản lý định danh nội bộ cho node và relationship. Hai khái niệm này phục vụ những mục đích khác nhau.

**Định danh nghiệp vụ** (business identifier) được xác định bởi miền nghiệp vụ hoặc hệ thống tích hợp. Ví dụ: mã nhân viên **EMP-1042**, mã khách hàng **CUS-00831** hay mã hợp đồng **CTR-2026-015**. Định danh này có ý nghĩa trong quy trình nghiệp vụ và có thể được trao đổi qua API, thông điệp hoặc báo cáo.

**Định danh nội bộ của cơ sở dữ liệu** (internal database identifier) do Neo4j quản lý để nhận diện một phần tử trong graph store. Nó phục vụ việc lưu trữ và truy cập nội bộ, không mang ý nghĩa nghiệp vụ. Trong Cypher hiện đại, hàm **elementId()** trả về định danh nội bộ dạng chuỗi. Hàm **id()** là API cũ và đã bị đánh dấu deprecated trong các phiên bản Neo4j mới.

Trong Spring Data Neo4j (SDN), annotation **@Id** đánh dấu thuộc tính được dùng làm định danh của entity khi ánh xạ object với node. Thuộc tính này có thể là mã nghiệp vụ, UUID do ứng dụng tạo, hoặc ID nội bộ được SDN sinh ra khi dùng cấu hình **@GeneratedValue** mặc định. Vì vậy, **@Id** là khái niệm định danh trong mô hình ánh xạ của SDN; nó không đồng nghĩa rằng mọi ID đều là định danh nghiệp vụ.

| Loại định danh | Ai quản lý? | Ví dụ | Nên dùng ở đâu? |
|---|---|---|---|
| Định danh nghiệp vụ | Miền nghiệp vụ hoặc hệ thống nguồn | EMP-1042 | API, tích hợp, tra cứu nghiệp vụ |
| Khóa thay thế của ứng dụng | Ứng dụng | UUID 7d… | Định danh ổn định cho entity khi mã nghiệp vụ có thể đổi |
| ID nội bộ Neo4j | Neo4j | Giá trị từ elementId(n) | Chẩn đoán hoặc thao tác kỹ thuật ngắn hạn |
| @Id của SDN | Mô hình entity của ứng dụng | String id hoặc String employeeCode | Xác định entity cho repository và quá trình ánh xạ |

Một thuộc tính có thể vừa là định danh nghiệp vụ vừa là **@Id**, nếu nó ổn định và duy nhất. Tuy nhiên, không nên mặc định dùng ID nội bộ của Neo4j làm mã định danh mà các hệ thống bên ngoài phụ thuộc vào.

## Vì sao không nên dùng ID nội bộ làm mã nghiệp vụ?

ID nội bộ thuộc về cách Neo4j tổ chức dữ liệu. Giá trị của nó không phải hợp đồng định danh lâu dài cho ứng dụng: nó có thể không còn đại diện cho cùng một node sau các thao tác xóa, khôi phục hoặc di chuyển dữ liệu; ID đã giải phóng cũng có thể được tái sử dụng tùy cơ chế lưu trữ và phiên bản. **elementId()** là giá trị opaque, ứng dụng không nên phân tích cấu trúc hoặc tự tạo giá trị theo định dạng của nó.

Nếu API trả **elementId()** cho client rồi client lưu lại, ứng dụng đã để một chi tiết triển khai của database trở thành giao kèo bên ngoài. Khi dữ liệu được nạp lại hoặc chuyển sang môi trường khác, các tham chiếu này có thể không còn hợp lệ. Tương tự, dùng ID nội bộ làm khóa ngoại trong hệ thống khác khiến việc đồng bộ và phục hồi dữ liệu phụ thuộc vào trạng thái vật lý của một database cụ thể.

Các thuộc tính như tên, email hoặc số điện thoại cũng không mặc nhiên là định danh tốt. Chúng có thể thay đổi, có thể bị dùng chung hoặc có quy tắc chuẩn hóa phức tạp. Chỉ chọn chúng làm khóa nghiệp vụ khi quy tắc miền bảo đảm tính duy nhất và độ ổn định đó.

## Chọn định danh cho node

Trước khi viết entity, hãy xác định vòng đời của thực thể và quy tắc định danh:

1. **Chọn khóa có ý nghĩa và ổn định.** Nếu miền nghiệp vụ cấp một mã bất biến, chẳng hạn mã nhân viên, có thể dùng trực tiếp mã đó. Nếu mã nghiệp vụ có thể thay đổi hoặc chỉ duy nhất trong một phạm vi, hãy cân nhắc UUID do ứng dụng tạo làm khóa kỹ thuật ổn định.
2. **Tách thuộc tính có thể thay đổi khỏi khóa.** Tên, email, địa chỉ và trạng thái thường là thuộc tính mô tả. Thay đổi chúng không nên làm thực thể trở thành một node khác.
3. **Bảo đảm tính duy nhất trong database.** Quy tắc ở tầng Java không đủ để ngăn hai request đồng thời tạo cùng một mã. Hãy khai báo uniqueness constraint trong Neo4j.
4. **Dùng cùng một quy tắc ở mọi đường ghi dữ liệu.** Repository, Cypher tùy chỉnh, import và tiến trình đồng bộ phải thống nhất cách nhận diện node.

### Ví dụ: UUID làm khóa của entity, mã nhân viên là khóa nghiệp vụ

Trong ví dụ này, **id** là UUID do ứng dụng tạo và được SDN dùng làm **@Id**. **employeeCode** là mã nghiệp vụ, duy nhất theo quy tắc của tổ chức. Email chỉ là thuộc tính liên hệ.

~~~java
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Person")
public class Person {

    @Id
    private String id;

    private String employeeCode;
    private String fullName;
    private String email;

    protected Person() {
        // Dành cho cơ chế ánh xạ của Spring Data Neo4j.
    }

    public Person(String id, String employeeCode, String fullName, String email) {
        this.id = id;
        this.employeeCode = employeeCode;
        this.fullName = fullName;
        this.email = email;
    }

    public String getId() {
        return id;
    }

    public String getEmployeeCode() {
        return employeeCode;
    }

    public String getFullName() {
        return fullName;
    }

    public String getEmail() {
        return email;
    }
}
~~~

Tạo constraint để Neo4j thực thi hai quy tắc duy nhất:

~~~cypher
CREATE CONSTRAINT person_id_unique IF NOT EXISTS
FOR (p:Person)
REQUIRE p.id IS UNIQUE;

CREATE CONSTRAINT person_employee_code_unique IF NOT EXISTS
FOR (p:Person)
REQUIRE p.employeeCode IS UNIQUE;
~~~

Constraint thứ nhất bảo vệ khóa ánh xạ của SDN. Constraint thứ hai bảo vệ mã nghiệp vụ. Nếu hệ thống có nhiều nguồn cấp mã, cần xác định rõ phạm vi duy nhất; có thể dùng một mã đã namespace hóa hoặc một khóa tổng hợp phù hợp với mô hình dữ liệu và khả năng constraint của phiên bản Neo4j đang triển khai.

Repository khai báo kiểu ID đúng với kiểu của thuộc tính **@Id**:

~~~java
import java.util.Optional;
import org.springframework.data.neo4j.repository.Neo4jRepository;

public interface PersonRepository extends Neo4jRepository<Person, String> {

    Optional<Person> findByEmployeeCode(String employeeCode);
}
~~~

**findById(uuid)** tìm theo thuộc tính **id** được đánh dấu **@Id**. **findByEmployeeCode(code)** là truy vấn dẫn xuất theo thuộc tính nghiệp vụ. Hai phương thức có thể cùng tồn tại vì chúng phục vụ hai mục đích tra cứu khác nhau.

Khi tạo entity, ứng dụng sinh UUID trước khi gọi repository:

~~~java
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PersonService {

    private final PersonRepository people;

    public PersonService(PersonRepository people) {
        this.people = people;
    }

    @Transactional
    public Person register(String employeeCode, String fullName, String email) {
        Person person = new Person(
            UUID.randomUUID().toString(),
            employeeCode,
            fullName,
            email
        );
        return people.save(person);
    }
}
~~~

Ví dụ này giả định **employeeCode** đã được xác thực theo quy tắc nghiệp vụ. Nếu hai giao dịch đồng thời đăng ký cùng mã, uniqueness constraint trong Neo4j là lớp bảo vệ cuối cùng; ứng dụng nên xử lý lỗi constraint thành phản hồi nghiệp vụ phù hợp. Không nên chỉ thực hiện thao tác “đọc xem mã đã tồn tại chưa rồi mới ghi”, vì hai request có thể cùng vượt qua bước đọc trước khi một request ghi dữ liệu.

### Khi nào dùng mã nghiệp vụ trực tiếp làm @Id?

Nếu mã nghiệp vụ bất biến, duy nhất toàn hệ thống và không phụ thuộc vào một nguồn có thể thay đổi, có thể dùng chính mã đó làm thuộc tính **@Id**:

~~~java
@Node("Department")
public class Department {

    @Id
    private String departmentCode;

    private String name;
}
~~~

Khi đó repository có kiểu **Neo4jRepository<Department, String>** và **findById("ENG")** tra cứu theo mã phòng ban. Vì không dùng generator, ứng dụng phải cung cấp **departmentCode** trước khi lưu. Nếu quy tắc mã thay đổi hoặc mã chỉ duy nhất trong một công ty/tenant, nên tách khóa kỹ thuật ổn định khỏi mã nghiệp vụ và thiết kế constraint tương ứng.

SDN cũng hỗ trợ cấu hình **@Id** kết hợp **@GeneratedValue** để sinh ID. Với generator mặc định, ID gắn với cơ chế định danh nội bộ của Neo4j; cách này thuận tiện cho lưu trữ nhưng không phù hợp để công bố như mã định danh lâu dài của domain. Nếu cần một khóa kỹ thuật ổn định độc lập với database, hãy chủ động sinh UUID ở ứng dụng hoặc cấu hình generator UUID theo đúng phiên bản SDN đang dùng. Kiểu Java và cách generator được khai báo cần khớp với phiên bản thư viện của dự án.

## Dùng định danh trong Cypher và quan hệ đồ thị

Khi viết Cypher, hãy tìm node bằng thuộc tính nghiệp vụ hoặc khóa ứng dụng đã chọn. Ví dụ sau dùng mã nhân viên làm khóa để tạo hoặc cập nhật node:

~~~cypher
MERGE (p:Person {employeeCode: $employeeCode})
ON CREATE SET
    p.id = $id,
    p.createdAt = datetime()
SET
    p.fullName = $fullName,
    p.email = $email
RETURN p
~~~

**MERGE** chỉ dựa trên thuộc tính nhận diện ổn định. Không đưa **fullName** hoặc **email** vào mẫu **MERGE** nếu chúng có thể thay đổi, vì một thay đổi giá trị có thể khiến truy vấn tạo node mới. Constraint duy nhất trên **employeeCode** giúp bảo vệ quy tắc này khi có ghi đồng thời. Nếu dùng repository **save**, SDN nhận diện entity bằng thuộc tính **@Id**; nó không tự suy ra rằng **employeeCode** là khóa chỉ vì thuộc tính đó có vẻ duy nhất trong nghiệp vụ.

Quan hệ trong graph nối các node đã được nhận diện. Có thể tìm hai đầu mối bằng mã ổn định rồi tạo cạnh:

~~~cypher
MATCH (employee:Person {employeeCode: $employeeCode})
MATCH (department:Department {departmentCode: $departmentCode})
MERGE (employee)-[r:WORKS_IN]->(department)
SET r.startedOn = date($startedOn)
RETURN employee, r, department
~~~

Ở đây, **employeeCode** và **departmentCode** xác định hai node; bản thân relationship được nhận diện bởi kiểu quan hệ và hai đầu mối trong mẫu **MERGE**. Nếu nghiệp vụ cho phép nhiều lần làm việc, nhiều hợp đồng hoặc nhiều sự kiện cùng nối một cặp node, không nên gộp tất cả thành một cạnh duy nhất. Hãy mô hình hóa thuộc tính và vòng đời quan hệ một cách tường minh; khi quan hệ có mã riêng, trạng thái riêng hoặc cần được truy vấn độc lập, có thể biểu diễn nó thành một node nghiệp vụ trung gian, chẳng hạn **Employment** hoặc **Contract**.

Với SDN, **@Relationship** mô tả kết nối giữa các entity và **@RelationshipProperties** có thể ánh xạ các thuộc tính trên cạnh. Các thuộc tính quan hệ không thay thế định danh của hai node đầu mối. Nếu một quan hệ cần định danh nghiệp vụ riêng và vòng đời độc lập, mô hình node trung gian thường thể hiện ý nghĩa đó rõ ràng hơn.

Để kiểm tra sự khác biệt giữa ID nội bộ và mã nghiệp vụ, có thể chạy truy vấn chỉ phục vụ chẩn đoán:

~~~cypher
MATCH (p:Person)
RETURN elementId(p) AS neo4jElementId,
       p.id AS applicationId,
       p.employeeCode AS businessId
LIMIT 10;
~~~

Không lưu **neo4jElementId** vào URL, message event, bảng tham chiếu của hệ thống khác hoặc dữ liệu nghiệp vụ. Hãy dùng **applicationId** hay **businessId** theo đúng hợp đồng của ứng dụng.

## Định danh và transaction trong ứng dụng Spring

Một thao tác nghiệp vụ có thể cần tạo node, nối relationship và cập nhật thêm node khác. Đặt các thao tác đó trong cùng transaction để chúng cùng thành công hoặc cùng rollback:

~~~java
@Transactional
public Person assignToDepartment(
        String employeeCode,
        String departmentCode,
        LocalDate startedOn) {

    Person person = people.findByEmployeeCode(employeeCode)
        .orElseThrow(() -> new PersonNotFoundException(employeeCode));

    // Tìm Department và ghi quan hệ bằng repository hoặc Cypher phù hợp.
    // Các thao tác database trong phương thức này tham gia cùng transaction.
    return person;
}
~~~

Đoạn mã tập trung minh họa ranh giới transaction; phần tìm và ghi Department cần được bổ sung theo repository và mô hình quan hệ thực tế của ứng dụng. **@Transactional** không tự tạo ra tính duy nhất. Constraint của Neo4j mới là nơi thực thi ràng buộc duy nhất ở mức dữ liệu; transaction giúp nhóm các thay đổi có liên quan thành một đơn vị nhất quán.

Khi cần upsert bằng Cypher tùy chỉnh, hãy dùng tham số thay vì nối chuỗi, dùng **MERGE** trên khóa ổn định và để constraint xử lý tranh chấp ghi đồng thời. Khi constraint vi phạm, tầng service nên chuyển lỗi kỹ thuật thành lỗi nghiệp vụ có thể hiểu được, ví dụ “mã nhân viên đã tồn tại”.

## Chuyển đổi từ ID nội bộ sang định danh ổn định

Nếu hệ thống cũ đã lưu **id(n)** hoặc **elementId(n)** ở nơi khác, việc thay thế cần có lộ trình để tránh làm hỏng tham chiếu:

1. **Chọn khóa mới.** Quyết định dùng mã nghiệp vụ bất biến hay UUID do ứng dụng quản lý; xác định phạm vi duy nhất và quy tắc chuẩn hóa.
2. **Gán khóa cho dữ liệu hiện có.** Backfill thuộc tính mới cho mọi node cần định danh. Với UUID, mỗi node phải nhận một giá trị riêng và giá trị đó phải được lưu bền vững.
3. **Kiểm tra dữ liệu.** Tìm node thiếu khóa và các giá trị trùng trước khi tạo uniqueness constraint. Xử lý xung đột theo quy tắc nghiệp vụ, không tự chọn một bản ghi tùy tiện.
4. **Tạo constraint và cập nhật mapping.** Khai báo uniqueness constraint trong Neo4j, sau đó cập nhật **@Id**, kiểu ID của repository, Cypher và các truy vấn liên quan.
5. **Chuyển các hệ thống phụ thuộc.** Cập nhật API, message, cache và dữ liệu tham chiếu để dùng khóa mới. Trong giai đoạn chuyển tiếp, có thể duy trì bảng ánh xạ cũ sang mới nếu cần tương thích ngược.
6. **Ngừng phát hành ID nội bộ.** Sau khi các consumer đã chuyển đổi và được xác minh, ngừng dùng ID nội bộ trong hợp đồng ứng dụng.

Không tạo lại UUID mỗi lần đọc hoặc mỗi lần gọi **save**. Khóa ứng dụng phải được tạo một lần, lưu trong node và được giữ nguyên suốt vòng đời của entity. Nếu một mã nghiệp vụ thực sự cần thay đổi, cập nhật thuộc tính nghiệp vụ theo quy trình được kiểm soát; không âm thầm biến một thực thể cũ thành một thực thể mới bằng cách thay khóa ánh xạ.

## Những lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Đưa **elementId()** vào API công khai | Client phụ thuộc vào chi tiết lưu trữ của Neo4j | Trả về UUID hoặc mã nghiệp vụ ổn định |
| Dùng email làm **@Id** dù email có thể đổi | Đổi email làm thay đổi định danh entity | Dùng UUID hoặc mã bất biến; giữ email là thuộc tính riêng |
| Chỉ kiểm tra trùng ở Java | Hai request đồng thời vẫn có thể tạo dữ liệu trùng | Tạo uniqueness constraint trong Neo4j |
| Dùng **save()** với entity thiếu **@Id** | SDN không thể nhận diện entity theo cấu hình đã khai báo | Cấp ID trước khi lưu hoặc cấu hình generator phù hợp |
| Dùng nhiều quy tắc khóa trong Cypher và repository | Có thể tạo node trùng cho cùng một thực thể | Chuẩn hóa khóa và dùng thống nhất trong mọi đường ghi |
| Dùng **MERGE** với cả thuộc tính hay thay đổi | Cập nhật thuộc tính có thể tạo node mới | **MERGE** theo khóa ổn định, cập nhật thuộc tính bằng **SET** |
| Dùng một cạnh cho nhiều sự kiện nghiệp vụ độc lập | Mất lịch sử hoặc ghi đè ý nghĩa của quan hệ | Dùng relationship properties hoặc node trung gian có định danh riêng |

## Tự kiểm tra

Với mô hình **Person** có **id** là UUID, **employeeCode** là mã nghiệp vụ và **email** là thuộc tính liên hệ, hãy tự trả lời:

1. Khi gọi **people.findById(value)**, **value** phải là UUID hay mã nhân viên? Vì sao?
2. Nếu nhân viên đổi email, thuộc tính nào thay đổi và định danh nào phải giữ nguyên?
3. Nếu hai request cùng tạo **employeeCode = EMP-1042**, cơ chế nào bảo đảm database không lưu hai node có cùng mã?
4. Khi chuyển dữ liệu sang một Neo4j database khác, ứng dụng nên dùng giá trị nào để tiếp tục nhận diện cùng một nhân viên?
5. Nếu một nhân viên có nhiều hợp đồng với cùng một phòng ban theo thời gian, mô hình một cạnh **WORKS_IN** có đủ biểu diễn lịch sử không? Nên biểu diễn hợp đồng hoặc lần phân công như thế nào?

Một thiết kế tốt giúp định danh của entity ổn định qua các lần cập nhật, di chuyển và tích hợp. Trong Spring Data Neo4j, hãy chọn rõ thuộc tính **@Id**, bảo vệ khóa bằng constraint của Neo4j và giữ ID nội bộ trong phạm vi kỹ thuật của database.

