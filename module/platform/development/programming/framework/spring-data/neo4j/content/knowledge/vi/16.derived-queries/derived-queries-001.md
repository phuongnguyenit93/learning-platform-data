# Cấu trúc tên phương thức và chiến lược tìm truy vấn

Spring Data Neo4j (SDN) cho phép khai báo truy vấn ngay trong tên phương thức repository. Cơ chế này thường được gọi là derived query hoặc query derivation: Spring Data phân tích tên phương thức, đối chiếu các thuộc tính trong mô hình entity rồi tạo truy vấn Cypher tương ứng. Với những thao tác lọc, sắp xếp và đếm phổ biến, derived query giúp repository ngắn gọn và thể hiện ý định truy vấn ngay trong chữ ký phương thức.

Để dùng hiệu quả, cần hiểu cấu trúc tên phương thức, các từ khóa điều kiện, cách parser đi qua property path và cách Spring Data quyết định dùng truy vấn suy diễn hay truy vấn đã khai báo. Tên phương thức là một phần của hợp đồng kỹ thuật: chỉ cần viết sai tên thuộc tính hoặc ghép từ khóa không đúng vị trí, repository có thể không khởi tạo được hoặc tạo truy vấn khác với ý định.

## Derived query hoạt động như thế nào?

Giả sử ứng dụng quản lý nhân viên và phòng ban. Entity Java có các thuộc tính đơn giản và một relationship tới **Department**:

~~~java
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Department")
public class Department {

    @Id
    private String code;

    private String name;

    protected Department() {
    }
}
~~~

~~~java
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;
import org.springframework.data.neo4j.core.schema.Relationship;

@Node("Person")
public class Person {

    @Id
    private String employeeCode;

    private String firstName;
    private String lastName;
    private String email;
    private String status;
    private Integer age;
    private Boolean active;

    @Relationship(type = "WORKS_IN")
    private Department department;

    protected Person() {
    }
}
~~~

Repository khai báo các phương thức truy vấn theo tên thuộc tính Java:

~~~java
import java.util.List;
import java.util.Optional;
import org.springframework.data.neo4j.repository.Neo4jRepository;

public interface PersonRepository extends Neo4jRepository<Person, String> {

    Optional<Person> findByEmail(String email);

    List<Person> findByLastName(String lastName);

    List<Person> findByLastNameAndActiveTrue(String lastName);

    List<Person> findByAgeGreaterThanEqual(Integer minimumAge);
}
~~~

Khi Spring tạo repository proxy, framework phân tích tên từng phương thức chưa có truy vấn khai báo. Ví dụ **findByLastNameAndActiveTrue** được tách thành:

- **find**: loại thao tác đọc.
- **By**: điểm bắt đầu phần điều kiện.
- **LastName**: property **lastName**.
- **And**: nối điều kiện.
- **ActiveTrue**: property **active** phải có giá trị true.

SDN dùng metadata của entity để tạo Cypher và ánh xạ kết quả về kiểu trả về. Developer không phải viết **MATCH** hoặc **WHERE** cho những điều kiện đơn giản này.

## Cấu trúc tên phương thức

Một tên derived query phổ biến có thể đọc theo cấu trúc:

~~~text
find [Distinct] [TopN | FirstN] By <PropertyPath> <Operator>
    [And | Or <PropertyPath> <Operator>]
    [OrderBy <PropertyPath> [Asc | Desc]]
~~~

Các phần có ý nghĩa như sau:

| Phần tên | Vai trò | Ví dụ |
|---|---|---|
| Subject/prefix | Chọn loại thao tác | **find**, **exists**, **count**, **delete** |
| **Distinct** | Yêu cầu kết quả không trùng | **findDistinctByLastName** |
| **Top** hoặc **First** | Giới hạn số kết quả | **findTop10ByActiveTrue** |
| **By** | Phân cách subject và predicate | **findByEmail** |
| Property path | Xác định thuộc tính cần kiểm tra | **LastName**, **DepartmentName** |
| Operator | Xác định phép so sánh | **Containing**, **GreaterThan** |
| **And**, **Or** | Kết hợp nhiều điều kiện | **findByLastNameAndActiveTrue** |
| **OrderBy** | Sắp xếp kết quả | **findByActiveTrueOrderByLastNameAsc** |

Tên property viết theo camel case của Java. **lastName** trở thành **LastName**, **employeeCode** trở thành **EmployeeCode**. Không dùng label Neo4j (**Person**) hoặc tên relationship (**WORKS_IN**) thay cho property path.

Ví dụ:

~~~java
List<Person> findByLastNameAndAgeGreaterThanEqual(String lastName, Integer age);
~~~

Phương thức này tìm người có **lastName** bằng giá trị tham số và **age** lớn hơn hoặc bằng tham số thứ hai. Thứ tự tham số phải tương ứng với thứ tự điều kiện trong tên phương thức.

## Prefix và kiểu thao tác

Các prefix thông dụng xác định mục tiêu của phương thức:

| Prefix | Mục đích | Ví dụ |
|---|---|---|
| **find…By** | Đọc entity hoặc projection phù hợp | **findByEmail** |
| **read…By**, **get…By**, **query…By** | Các biến thể tên cho thao tác đọc | **readByActiveTrue** |
| **exists…By** | Kiểm tra có bản ghi phù hợp | **existsByEmail** |
| **count…By** | Đếm số entity phù hợp | **countByActiveTrue** |
| **delete…By**, **remove…By** | Xóa entity phù hợp | **deleteByEmployeeCode** |

Ví dụ repository:

~~~java
public interface PersonRepository extends Neo4jRepository<Person, String> {

    boolean existsByEmail(String email);

    long countByActiveTrue();

    long deleteByEmployeeCode(String employeeCode);
}
~~~

Chọn kiểu trả về phù hợp với mục đích: **boolean** cho kiểm tra tồn tại, **long** cho số lượng và **void** hoặc kiểu kết quả được hỗ trợ cho thao tác xóa. Hành vi xóa entity có relationship cần được kiểm tra theo mô hình và phiên bản SDN của dự án; xóa node có thể liên quan đến các relationship đang nối với node đó. Với thao tác có tác động lớn, cân nhắc viết Cypher tường minh để kiểm soát chính xác node và cạnh cần xóa.

## Predicate và các toán tử thường dùng

Phần predicate bắt đầu sau **By**. Spring Data Commons định nghĩa nhiều từ khóa truy vấn; SDN chuyển những biểu thức được hỗ trợ thành Cypher. Bảng dưới đây mô tả nhóm toán tử thường gặp. Hãy đối chiếu danh sách hỗ trợ với phiên bản SDN đang dùng, đặc biệt khi truy vấn có kiểu dữ liệu hoặc cấu trúc quan hệ phức tạp.

| Từ khóa | Ý nghĩa | Ví dụ |
|---|---|---|
| Không ghi toán tử | So sánh bằng | **findByLastName(value)** |
| **Is**, **Equals** | So sánh bằng tường minh | **findByEmailIs(value)** |
| **Not** | Khác giá trị | **findByStatusNot(status)** |
| **GreaterThan**, **After** | Lớn hơn | **findByAgeGreaterThan(age)** |
| **GreaterThanEqual** | Lớn hơn hoặc bằng | **findByAgeGreaterThanEqual(age)** |
| **LessThan**, **Before** | Nhỏ hơn | **findByAgeLessThan(age)** |
| **LessThanEqual** | Nhỏ hơn hoặc bằng | **findByAgeLessThanEqual(age)** |
| **Between** | Nằm trong khoảng | **findByAgeBetween(min, max)** |
| **In**, **NotIn** | Thuộc hoặc không thuộc tập giá trị | **findByStatusIn(statuses)** |
| **IsNull**, **IsNotNull** | Property không có hoặc có giá trị | **findByEmailIsNotNull()** |
| **True**, **False** | Boolean đúng hoặc sai | **findByActiveTrue()** |
| **Containing** | Chuỗi chứa đoạn con | **findByLastNameContaining(fragment)** |
| **StartingWith**, **EndingWith** | Chuỗi bắt đầu/kết thúc bằng giá trị | **findByEmailStartingWith(prefix)** |
| **Like**, **NotLike** | So khớp theo mẫu | **findByLastNameLike(pattern)** |
| **IgnoreCase** | So sánh chuỗi không phân biệt hoa thường | **findByEmailIgnoreCase(email)** |

Ví dụ lọc theo khoảng tuổi và tập trạng thái:

~~~java
import java.util.Collection;

List<Person> findByAgeBetween(Integer minimum, Integer maximum);

List<Person> findByStatusIn(Collection<String> statuses);
~~~

Với **Between**, hai đầu mút thường được tính vào khoảng. Khi nghiệp vụ cần khoảng nửa mở như **age >= min AND age < max**, hãy biểu đạt rõ bằng hai điều kiện hoặc dùng **@Query** nếu tên phương thức trở nên khó đọc.

Các từ khóa như **Containing**, **Like**, **IgnoreCase** có ý nghĩa riêng với chuỗi. Không dùng chúng cho một thuộc tính số hoặc boolean. Với kiểu dữ liệu đặc thù, collection property, temporal hoặc spatial, hãy xác nhận hỗ trợ của phiên bản SDN trước khi dựa vào derived query.

### Kết hợp And và Or

Có thể ghép nhiều điều kiện:

~~~java
List<Person> findByLastNameAndActiveTrue(String lastName);

List<Person> findByFirstNameOrLastName(String firstName, String lastName);
~~~

**And** yêu cầu cả hai điều kiện đúng; **Or** cho phép một trong các điều kiện đúng. Với biểu thức có nhiều nhóm ngoặc hoặc logic phức tạp, tên phương thức không thể hiện trực quan cấu trúc như một câu Cypher. Khi đó nên dùng **@Query** để viết rõ **WHERE**, dấu ngoặc và thứ tự đánh giá điều kiện.

Không nên đặt tên phương thức quá dài chỉ để mã hóa một biểu thức nghiệp vụ phức tạp. Tên dài khó rà soát, khó phát hiện lỗi parser và khiến thay đổi domain kéo theo nhiều thay đổi tên method.

## Giới hạn kết quả và sắp xếp

Có thể yêu cầu lấy một số lượng kết quả giới hạn bằng **Top** hoặc **First**:

~~~java
List<Person> findTop10ByActiveTrueOrderByLastNameAsc();

Optional<Person> findFirstByEmailIgnoreCase(String email);
~~~

**Top10** giới hạn kết quả tối đa mười phần tử. **First** tương đương giới hạn một phần tử đầu tiên theo thứ tự truy vấn. Nếu không chỉ định **OrderBy**, thứ tự trả về không được bảo đảm; đừng dùng **First** như thể nó luôn chọn bản ghi mới nhất hoặc nhỏ nhất.

Sắp xếp được mô tả bằng **OrderBy** và tên property:

~~~java
List<Person> findByActiveTrueOrderByLastNameAscFirstNameAsc();
~~~

Ví dụ trên sắp xếp theo **lastName** tăng dần, sau đó **firstName** tăng dần. Có thể dùng **Desc** để sắp xếp giảm dần:

~~~java
List<Person> findByActiveTrueOrderByAgeDescLastNameAsc();
~~~

Nếu nghiệp vụ cần chọn một kết quả theo tiêu chí cụ thể, hãy chỉ rõ property và thứ tự, ví dụ **findTop1ByDepartmentNameOrderByLastNameAsc**. Một thứ tự ổn định nên có thêm tiêu chí phụ khi nhiều bản ghi có cùng giá trị sắp xếp.

## Property path qua relationship

Derived query có thể biểu đạt việc lọc theo thuộc tính của entity liên quan nếu property path đó được SDN hỗ trợ. Ví dụ **Person** có relationship **department**, còn **Department** có property **name**. Có thể khai báo:

~~~java
List<Person> findByDepartmentName(String departmentName);
~~~

Tên được phân tích thành đường dẫn **department.name**. Khi cần làm rõ ranh giới giữa hai property, dùng dấu gạch dưới:

~~~java
List<Person> findByDepartment_Name(String departmentName);
~~~

Dấu gạch dưới biểu thị điểm tách property path, không phải tên property trong Neo4j. Tên phải khớp với mô hình Java: **department** là thuộc tính relationship trong **Person**, **name** là thuộc tính của **Department**.

Ví dụ Cypher tương đương về ý nghĩa:

~~~cypher
MATCH (p:Person)-[:WORKS_IN]->(d:Department)
WHERE d.name = $departmentName
RETURN p;
~~~

Đây là cách hiểu về đường truy vấn, không phải cam kết rằng SDN sẽ sinh đúng nguyên văn Cypher này. Hướng relationship, mapping, alias và phiên bản thư viện có thể làm câu lệnh sinh ra khác nhau. Hãy xác minh bằng integration test nếu truy vấn qua relationship là một phần quan trọng của nghiệp vụ.

Nếu đường dẫn property trở nên mơ hồ hoặc có nhiều nhánh, hãy viết **@Query** với pattern Cypher tường minh. Điều này đặc biệt hữu ích khi cần lọc nhiều cấp relationship, kiểm tra sự tồn tại của một nhánh hoặc kết hợp các điều kiện có logic phức tạp.

## Kiểu trả về và số lượng kết quả

Kiểu trả về nên phản ánh số lượng kết quả mà nghiệp vụ mong đợi:

| Kiểu trả về | Ý nghĩa |
|---|---|
| **Person** | Mong đợi một kết quả; trường hợp không tìm thấy hoặc nhiều kết quả cần xử lý theo contract của phương thức |
| **Optional<Person>** | Có thể không tìm thấy hoặc tìm thấy một entity |
| **List<Person>** | Có thể có nhiều kết quả |
| **Collection<Person>** | Tập kết quả nhiều phần tử |
| **boolean** | Thường dùng cho **exists…By** |
| **long** | Thường dùng cho **count…By** hoặc số lượng bị tác động nếu phương thức xóa hỗ trợ |
| Projection/DTO | Chỉ trả về các trường được chọn |

Ví dụ:

~~~java
Optional<Person> findByEmail(String email);

List<Person> findByLastName(String lastName);

boolean existsByEmployeeCode(String employeeCode);

long countByActiveTrue();
~~~

Nếu điều kiện không bảo đảm duy nhất, tránh trả trực tiếp một entity đơn. Ví dụ nhiều người có thể cùng họ, do đó **findByLastName** nên trả **List<Person>**. Nếu email được bảo đảm duy nhất bằng constraint, **Optional<Person>** thể hiện đúng hơn kỳ vọng của ứng dụng.

Kiểu trả về không tự tạo uniqueness constraint. Nếu một property phải duy nhất, hãy bảo vệ quy tắc đó bằng constraint trong Neo4j và xử lý lỗi khi ghi đồng thời.

## Phương thức repository dành riêng và quy tắc findById

**Neo4jRepository** kế thừa các phương thức như **findById**, **existsById** và **deleteById**. Đây là các phương thức repository dành riêng để thao tác theo thuộc tính được đánh dấu **@Id**, không phải lúc nào cũng là query method tìm property tên **id**.

Ví dụ entity có **employeeCode** là ID:

~~~java
@Node("Person")
public class Person {

    @Id
    private String employeeCode;

    private String email;
}
~~~

Khi đó:

~~~java
Optional<Person> person = people.findById("EMP-1042");
~~~

**findById** tìm theo thuộc tính **employeeCode** được đánh dấu **@Id**. Nó không có nghĩa là tìm theo bất kỳ property nào tên **id** hoặc theo mã khác.

Nếu entity có property nghiệp vụ tên **id** nhưng property đó không phải thuộc tính **@Id**, tên phương thức **findById** có thể bị hiểu là phương thức dành riêng của repository. Hãy dùng descriptive token để parser nhận ra đây là query method theo property, ví dụ **findPersonById(String id)**, và kiểm tra tên thuộc tính ID thực tế của entity.

## Chiến lược tìm truy vấn (Query Lookup Strategy)

Khi Spring Data khởi tạo repository, framework phải quyết định lấy truy vấn từ đâu. Cơ chế này được cấu hình bằng **QueryLookupStrategy**.

Có ba chiến lược chính:

| Chiến lược | Cách hoạt động | Khi phù hợp |
|---|---|---|
| **CREATE** | Luôn tạo truy vấn từ tên phương thức | Muốn repository chủ yếu dùng derived query |
| **USE_DECLARED_QUERY** | Yêu cầu phương thức có truy vấn đã khai báo; không tự suy diễn nếu thiếu | Muốn kiểm soát mọi truy vấn bằng **@Query** hoặc khai báo tường minh |
| **CREATE_IF_NOT_FOUND** | Tìm truy vấn đã khai báo trước; nếu không có thì suy diễn từ tên phương thức | Muốn kết hợp **@Query** cho truy vấn phức tạp và derived query cho truy vấn đơn giản |

**CREATE_IF_NOT_FOUND** là lựa chọn mặc định phổ biến của Spring Data. Vì vậy, một phương thức có **@Query** sẽ dùng truy vấn được khai báo; phương thức không có khai báo sẽ được phân tích tên nếu có thể.

Có thể cấu hình rõ chiến lược khi bật repository:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.repository.query.QueryLookupStrategy;
import org.springframework.data.neo4j.repository.config.EnableNeo4jRepositories;

@Configuration
@EnableNeo4jRepositories(
    queryLookupStrategy = QueryLookupStrategy.Key.CREATE_IF_NOT_FOUND
)
public class Neo4jRepositoryConfiguration {
}
~~~

Thông thường không cần thêm cấu hình này nếu mặc định đã phù hợp. Chỉ tùy chỉnh khi dự án có chính sách rõ ràng về nguồn truy vấn. Với **USE_DECLARED_QUERY**, một phương thức chỉ có tên **findByEmail** mà không có truy vấn khai báo sẽ không được tự động suy diễn và có thể khiến repository không khởi tạo thành công.

### Kết hợp derived query với @Query

Derived query phù hợp với điều kiện ngắn và rõ ràng. Khi cần traversal nhiều cấp, projection đặc thù, aggregation, subquery hoặc logic Cypher khó biểu đạt bằng tên phương thức, hãy khai báo **@Query**. Ví dụ repository có truy vấn khai báo:

~~~java
import java.util.List;
import org.springframework.data.neo4j.repository.Neo4jRepository;
import org.springframework.data.neo4j.repository.query.Query;
import org.springframework.data.repository.query.Param;

public interface PersonRepository extends Neo4jRepository<Person, String> {

    @Query("""
        MATCH (p:Person)-[:WORKS_IN]->(d:Department)
        WHERE d.name = $departmentName
          AND p.active = true
        RETURN p
        ORDER BY p.lastName, p.firstName
        """)
    List<Person> findActivePeopleInDepartment(
        @Param("departmentName") String departmentName
    );
}
~~~

Truy vấn khai báo làm rõ pattern graph, điều kiện và thứ tự. Hãy dùng bind parameter thay vì ghép dữ liệu đầu vào vào chuỗi Cypher. Đặt tên method mô tả nghiệp vụ dù query không được suy diễn từ tên.

## Chọn derived query hay @Query?

| Nhu cầu | Lựa chọn gợi ý | Lý do |
|---|---|---|
| Tìm theo một property | Derived query | Ngắn, dễ đọc và ít mã |
| Ghép một vài điều kiện đơn giản | Derived query | Tên thể hiện trực tiếp predicate |
| Kiểm tra tồn tại hoặc đếm | **exists…By**, **count…By** | Kiểu trả về sát với mục tiêu |
| Giới hạn kết quả và sắp xếp đơn giản | **Top**/**First** và **OrderBy** | Không cần viết Cypher riêng |
| Truy vấn qua một property path đơn giản | Derived query nếu SDN hỗ trợ | Tận dụng metadata entity |
| Nhiều nhánh relationship hoặc điều kiện phức tạp | **@Query** | Chủ động kiểm soát pattern và logic |
| Aggregation, path, subquery hoặc projection đặc thù | **@Query** | Tên phương thức không đủ biểu đạt |
| Cần Cypher tối ưu hoặc tính năng đặc thù của Neo4j | **@Query** hoặc **Neo4jClient** | Viết rõ câu lệnh và tham số |

Đừng chuyển mọi truy vấn thành **@Query**: điều đó làm mất lợi ích của query derivation cho trường hợp đơn giản. Ngược lại, đừng cố nhồi một truy vấn phức tạp vào một tên method dài. Hãy chọn cách thể hiện mà người bảo trì có thể hiểu và kiểm tra nhanh.

## Lỗi thường gặp và cách xử lý

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| **No property ... found** | Tên property trong method không tồn tại trong entity | Kiểm tra camel case và property path Java |
| Repository không khởi tạo được | Parser không hiểu tên hoặc chiến lược yêu cầu declared query | Rà tên method, annotation **@Query** và query lookup strategy |
| **findById** trả về kết quả theo khóa khác mong đợi | Đây là phương thức dành riêng dùng thuộc tính **@Id** | Dùng tên query có descriptive token để truy vấn property nghiệp vụ |
| Dùng **First** nhưng kết quả không ổn định | Không khai báo thứ tự | Thêm **OrderBy** theo tiêu chí rõ ràng |
| Tên method quá dài và khó đọc | Nhồi nhiều điều kiện hoặc nhiều nhánh logic | Chuyển sang **@Query** |
| Property path qua relationship không hoạt động | Sai tên relationship property, hướng hoặc mapping | Kiểm tra entity và thử truy vấn Cypher tường minh |
| **Optional<T>** gặp nhiều kết quả | Điều kiện không duy nhất | Dùng **List<T>** hoặc tạo constraint nếu domain yêu cầu duy nhất |
| Dùng toán tử không phù hợp kiểu dữ liệu | Predicate không tương thích property | Chọn toán tử đúng kiểu và xác nhận hỗ trợ của SDN version |
| Dùng derived delete mà không hiểu ảnh hưởng graph | Node có thể còn relationship hoặc có quy tắc xóa riêng | Xác minh semantics và dùng Cypher tường minh khi cần kiểm soát |

Khi một derived query không chạy như mong đợi, hãy kiểm tra theo thứ tự: tên property trong entity, ranh giới **By**, toán tử, kiểu tham số, kiểu trả về và chiến lược lookup. Với truy vấn qua relationship, kiểm tra cả mapping và hướng cạnh. Nếu vẫn chưa rõ, viết một truy vấn Cypher tương đương để xác nhận logic graph trước khi đưa lại vào repository.

## Bài tập thực hành

Với hai entity **Person** và **Department** ở đầu bài, hãy khai báo repository và thử các yêu cầu:

1. Tìm một người theo email, trả **Optional<Person>**.
2. Tìm tất cả người theo họ.
3. Tìm người đang hoạt động theo họ, dùng **And** và **True**.
4. Tìm người có tuổi lớn hơn hoặc bằng một ngưỡng.
5. Đếm số người đang hoạt động.
6. Lấy tối đa mười người đang hoạt động, sắp xếp theo họ rồi tên.
7. Tìm người theo tên phòng ban qua property path **department.name**.
8. Viết một truy vấn **@Query** để tìm người đang hoạt động thuộc phòng ban có tên cho trước.
9. Thử cấu hình **CREATE_IF_NOT_FOUND**, sau đó quan sát khác biệt khi dùng **USE_DECLARED_QUERY** với một method không có **@Query**.
10. Tạo một property nghiệp vụ có tên **id** không phải **@Id**, rồi kiểm tra cách đặt tên descriptive token để tránh trùng với phương thức dành riêng **findById**.

Khi hoàn thành, hãy giải thích được parser tách subject và predicate như thế nào, vì sao tên property phải khớp entity, khi nào dùng property path qua relationship, và cách **QueryLookupStrategy** chọn giữa truy vấn khai báo với truy vấn suy diễn.

Derived query là cách viết repository ngắn gọn cho các truy vấn có cấu trúc quen thuộc. Hiểu rõ tên method và query lookup strategy giúp ứng dụng Spring Data Neo4j giữ được repository dễ đọc, tránh nhầm lẫn giữa ID và property thông thường, đồng thời chuyển sang Cypher tường minh đúng lúc khi yêu cầu truy vấn vượt quá khả năng biểu đạt của tên phương thức.

