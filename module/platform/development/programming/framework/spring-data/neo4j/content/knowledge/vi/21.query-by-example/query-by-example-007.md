# Phân trang, sắp xếp và fluent query theo phiên bản

Query by Example (QBE) trong Spring Data Neo4j (SDN) cho phép tạo điều kiện tìm kiếm từ một entity mẫu (probe) và bộ quy tắc so khớp (ExampleMatcher). Khi kết quả có nhiều node, ứng dụng thường cần sắp xếp, phân trang hoặc chỉ lấy một phần dữ liệu. Spring Data cung cấp các overload QBE nhận Sort và Pageable; các phiên bản Spring Data Commons mới hơn còn có fluent query API để kết hợp sort, giới hạn, phân trang và chọn kiểu kết quả ngay tại nơi gọi repository.

Cần kiểm tra phiên bản Spring Data Commons mà dự án thực sự đang chạy. Không phải mọi phiên bản SDN đều cung cấp cùng một tập phương thức QBE. Bài học này trình bày cách phân trang và sắp xếp với QBE, cách dùng fluent query khi có hỗ trợ, cách chọn API tương thích và những giới hạn cần cân nhắc khi probe có quan hệ graph.

## Ôn lại cấu trúc Query by Example

Một truy vấn QBE gồm ba thành phần:

- **Probe:** entity mẫu chứa các giá trị muốn tìm.
- **ExampleMatcher:** quy định cách so khớp từng property, ví dụ chính xác, chứa chuỗi con hoặc không phân biệt hoa thường.
- **Example:** kết hợp probe và matcher thành đối tượng truy vấn.

Giả sử ứng dụng quản lý nhân viên:

~~~java
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Person")
public class Person {

    @Id
    private String employeeCode;

    private String firstName;
    private String lastName;
    private String email;
    private Boolean active;
    private Integer age;

    protected Person() {
    }

    public String getEmployeeCode() { return employeeCode; }
    public String getFirstName() { return firstName; }
    public String getLastName() { return lastName; }
    public String getEmail() { return email; }
    public Boolean getActive() { return active; }
    public Integer getAge() { return age; }

    public void setEmployeeCode(String value) { employeeCode = value; }
    public void setFirstName(String value) { firstName = value; }
    public void setLastName(String value) { lastName = value; }
    public void setEmail(String value) { email = value; }
    public void setActive(Boolean value) { active = value; }
    public void setAge(Integer value) { age = value; }
}
~~~

Repository cần kế thừa Neo4jRepository:

~~~java
import org.springframework.data.neo4j.repository.Neo4jRepository;

public interface PersonRepository extends Neo4jRepository<Person, String> {
}
~~~

Tạo probe và matcher:

~~~java
import org.springframework.data.domain.Example;
import org.springframework.data.domain.ExampleMatcher;

Person probe = new Person();
probe.setLastName("nguyen");
probe.setActive(true);

ExampleMatcher matcher = ExampleMatcher.matchingAll()
    .withMatcher(
        "lastName",
        ExampleMatcher.GenericPropertyMatchers.contains().ignoreCase()
    );

Example<Person> example = Example.of(probe, matcher);
~~~

Các property khác có giá trị null được bỏ qua theo mặc định. lastName được so khớp theo chuỗi con, không phân biệt hoa thường; active được so khớp chính xác với true. matchingAll() yêu cầu tất cả điều kiện có trong probe đều phải khớp.

QBE phù hợp với bộ lọc được hình thành từ các property đơn giản. Nó không thay thế một trình dựng truy vấn Cypher tổng quát: điều kiện có nhóm ngoặc phức tạp, traversal nhiều nhánh, aggregation hoặc quy tắc trên nhiều relationship thường cần @Query hay Neo4jClient.

## Sắp xếp kết quả bằng Sort

Có thể truyền Sort vào overload findAll(Example, Sort):

~~~java
import org.springframework.data.domain.Sort;

Sort sort = Sort.by(
    Sort.Order.asc("lastName"),
    Sort.Order.asc("firstName"),
    Sort.Order.asc("employeeCode")
);

Iterable<Person> people = personRepository.findAll(example, sort);
~~~

Các tên trong Sort.Order là property Java của entity, không phải tên label, tên relationship hay tên cột SQL. Ví dụ lastName và employeeCode phải tồn tại trên Person.

Nên thêm một tiêu chí duy nhất ở cuối thứ tự sắp xếp, chẳng hạn employeeCode. Nếu chỉ sắp xếp theo lastName, nhiều người có cùng họ có thể đổi vị trí tương đối giữa các lần truy vấn. Một thứ tự có khóa phân biệt giúp phân trang ổn định hơn.

Có thể chọn chiều giảm dần:

~~~java
Sort newestFirst = Sort.by(
    Sort.Order.desc("age"),
    Sort.Order.asc("employeeCode")
);
~~~

Ví dụ trên sắp xếp tuổi giảm dần, rồi mã nhân viên tăng dần. Với property có thể null, cần xác định cách xử lý giá trị thiếu phù hợp với database và yêu cầu giao diện; không nên giả định mọi kiểu sắp xếp sẽ xử lý null giống nhau.

Nếu cần sort theo property nằm sâu trong relationship, hãy kiểm tra hỗ trợ của phiên bản SDN thay vì mặc định rằng Sort có thể traversal mọi đường dẫn graph. Khi việc sắp xếp phụ thuộc node liên quan hoặc một phép tính Cypher, dùng custom query sẽ thể hiện rõ pattern và thứ tự hơn.

## Phân trang bằng Pageable

QBE có overload nhận Pageable và trả về Page:

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;

Sort sort = Sort.by(
    Sort.Order.asc("lastName"),
    Sort.Order.asc("employeeCode")
);

Pageable pageable = PageRequest.of(0, 20, sort);

Page<Person> firstPage = personRepository.findAll(example, pageable);
~~~

PageRequest.of(page, size, sort) dùng chỉ số trang bắt đầu từ 0. Với trang đầu tiên có 20 phần tử, page là 0 và size là 20. Trang kế tiếp là PageRequest.of(1, 20, sort).

Một Page<Person> cung cấp cả nội dung và metadata:

~~~java
import java.util.List;

List<Person> content = firstPage.getContent();
long totalElements = firstPage.getTotalElements();
int totalPages = firstPage.getTotalPages();
boolean hasNext = firstPage.hasNext();
boolean hasPrevious = firstPage.hasPrevious();
~~~

| Phương thức | Thông tin |
|---|---|
| getContent() | Các entity trong trang hiện tại |
| getNumber() | Chỉ số trang hiện tại, bắt đầu từ 0 |
| getSize() | Kích thước trang được yêu cầu |
| getNumberOfElements() | Số phần tử thực tế trong trang |
| getTotalElements() | Tổng số kết quả phù hợp |
| getTotalPages() | Tổng số trang |
| hasNext() | Có trang tiếp theo hay không |
| hasPrevious() | Có trang trước đó hay không |

Để tạo API response, có thể chuyển Page thành DTO thay vì trả trực tiếp entity persistence:

~~~java
public record PersonPageResponse(
    List<PersonSummary> items,
    int page,
    int size,
    long totalElements,
    int totalPages,
    boolean hasNext
) {
}
~~~

Hãy giới hạn kích thước trang ở tầng ứng dụng. Không nên để client gửi một size quá lớn khiến truy vấn tải quá nhiều node hoặc relationship. Với trang rất sâu, offset pagination có thể tốn chi phí do database phải bỏ qua nhiều kết quả trước khi trả trang được yêu cầu.

### Ví dụ service phân trang QBE

~~~java
import org.springframework.data.domain.Example;
import org.springframework.data.domain.ExampleMatcher;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.stereotype.Service;

@Service
public class PersonSearchService {

    private static final int MAX_PAGE_SIZE = 100;
    private final PersonRepository people;

    public PersonSearchService(PersonRepository people) {
        this.people = people;
    }

    public Page<Person> search(
            String lastName,
            Boolean active,
            int page,
            int size) {

        if (page < 0) {
            throw new IllegalArgumentException("Page must be zero or greater");
        }
        if (size < 1 || size > MAX_PAGE_SIZE) {
            throw new IllegalArgumentException("Page size is outside the allowed range");
        }

        Person probe = new Person();
        probe.setLastName(lastName);
        probe.setActive(active);

        ExampleMatcher matcher = ExampleMatcher.matchingAll()
            .withIgnoreNullValues()
            .withMatcher(
                "lastName",
                ExampleMatcher.GenericPropertyMatchers.contains().ignoreCase()
            );

        Example<Person> example = Example.of(probe, matcher);
        Sort sort = Sort.by(
            Sort.Order.asc("lastName"),
            Sort.Order.asc("employeeCode")
        );

        return people.findAll(example, PageRequest.of(page, size, sort));
    }
}
~~~

Service kiểm tra page và size trước khi gọi repository, sau đó tạo probe từ dữ liệu tìm kiếm. Giá trị null được bỏ qua; nếu lastName có nội dung, matcher áp dụng quy tắc chứa chuỗi con. Nếu active có giá trị, nó được so khớp chính xác.

MAX_PAGE_SIZE = 100 là chính sách minh họa, không phải giới hạn cố định của SDN. Chọn mức tối đa theo kích thước entity, số relationship cần tải, độ phức tạp truy vấn và tải database.

## Fluent query API cho Query by Example

Các phiên bản Spring Data Commons mới hơn cung cấp phương thức findBy(Example, Function) trong QueryByExampleExecutor. API này cho phép cấu hình kết quả ngay tại nơi gọi repository: sắp xếp, giới hạn, phân trang hoặc chuyển sang projection.

Ví dụ phân trang bằng fluent query:

~~~java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;

Pageable pageable = PageRequest.of(
    0,
    20,
    Sort.by(
        Sort.Order.asc("lastName"),
        Sort.Order.asc("employeeCode")
    )
);

Page<Person> page = personRepository.findBy(
    example,
    query -> query.page(pageable)
);
~~~

Có thể cấu hình sort ngay trong fluent query:

~~~java
import java.util.List;

List<Person> firstTen = personRepository.findBy(
    example,
    query -> query
        .sortBy(Sort.by(
            Sort.Order.asc("lastName"),
            Sort.Order.asc("employeeCode")
        ))
        .limit(10)
        .all()
);
~~~

Fluent query hữu ích khi cùng một probe cần nhiều cách lấy kết quả mà không phải tạo nhiều repository method. Một số terminal operation thường dùng gồm:

| Operation | Kết quả |
|---|---|
| all() | Tất cả kết quả phù hợp |
| first() | Kết quả đầu tiên hoặc rỗng |
| one() | Tối đa một kết quả; lỗi nếu có nhiều hơn một |
| page(pageable) | Một trang cùng metadata tổng số |
| slice(pageable) | Một lát kết quả, thường không cần tổng số phần tử |
| stream() | Stream kết quả; cần đóng stream sau khi dùng |
| count() | Số kết quả phù hợp |
| exists() | Có ít nhất một kết quả phù hợp hay không |

Các operation và kiểu trả về cụ thể phụ thuộc API fluent query trong phiên bản Spring Data Commons được quản lý bởi dự án. Khi cần projection, API cũng có thể cung cấp as(...) và project(...); hãy kiểm tra kiểu projection và khả năng mapping mà phiên bản SDN đang dùng hỗ trợ.

Ví dụ giới hạn một kết quả:

~~~java
import java.util.Optional;

Optional<Person> firstMatch = personRepository.findBy(
    example,
    query -> query
        .sortBy(Sort.by(Sort.Order.asc("employeeCode")))
        .first()
);
~~~

Ví dụ chỉ kiểm tra có kết quả hay không:

~~~java
boolean hasMatch = personRepository.findBy(
    example,
    query -> query.exists()
);
~~~

Callback của findBy cần trả về kết quả cuối cùng như Page, List, Optional hoặc boolean. Không giữ fluent query để sử dụng sau callback; nó được thiết kế để cấu hình và thực thi trong phạm vi lời gọi findBy.

## Khác biệt API theo phiên bản Spring Data

QBE cơ bản và fluent query không xuất hiện cùng thời điểm. Khi nâng cấp hoặc bảo trì ứng dụng, hãy xác định API nào có trong dependency thực tế thay vì chỉ dựa vào ví dụ trên mạng.

| Năng lực | Spring Data Commons trước 2.6 | Spring Data Commons 2.6 trở lên |
|---|---|---|
| Example, ExampleMatcher | Có | Có |
| findAll(example) | Có | Có |
| findAll(example, sort) | Có | Có |
| findAll(example, pageable) | Có | Có |
| findBy(example, queryFunction) fluent API | Chưa có trong API QBE chuẩn | Có |
| Cấu hình sort/page qua fluent query | Không dùng được qua findBy | Có, tùy terminal operation và module hỗ trợ |

Spring Data Commons 2.6 bổ sung fluent query API cho Query by Example. Các bản Spring Data Commons mới hơn tiếp tục phát triển API này. Tuy nhiên, việc có method trong Commons không tự bảo đảm mọi hành vi projection hoặc query đặc thù đều được hỗ trợ giống nhau ở từng module SDN. Hãy kiểm tra phiên bản SDN tương thích và API thực tế của repository.

Spring Boot quản lý một bộ phiên bản Spring Data thông qua dependency management. Khi dùng Spring Boot, ưu tiên phiên bản SDN và Spring Data Commons do BOM của Boot quản lý; không tự nâng riêng spring-data-commons lên một phiên bản khác nếu chưa xác minh tính tương thích. Phiên bản Boot chỉ là dấu hiệu để tra dependency, không thay thế việc kiểm tra phiên bản đã resolve.

Có thể kiểm tra dependency trong dự án bằng các lệnh sau:

~~~bash
# Maven
mvn dependency:tree -Dincludes=org.springframework.data:spring-data-commons,org.springframework.data:spring-data-neo4j

# Gradle
./gradlew dependencyInsight --dependency spring-data-commons --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-data-neo4j --configuration runtimeClasspath
~~~

Nếu phiên bản Commons thấp hơn 2.6 hoặc repository không có method findBy(Example, Function), dùng các overload QBE cơ bản như findAll(example, pageable) và findAll(example, sort). Đây là cách tương thích rộng hơn và vẫn đáp ứng phân trang, sắp xếp.

Khi nâng cấp, không chỉ sửa compile error. Hãy kiểm tra lại:

- Method fluent query có sẵn trên repository interface hay không.
- Kiểu trả về Page, Slice, Optional hoặc projection có được hỗ trợ đúng không.
- Sort theo property của entity có hoạt động như mong đợi không.
- Query được tạo ra có giữ đúng điều kiện QBE và mapping graph không.
- Các integration test chạy với đúng phiên bản Neo4j và SDN đang triển khai.

## Probe, giá trị mặc định và giới hạn so khớp

QBE lấy các giá trị trong probe để tạo điều kiện. Vì vậy, cách khai báo kiểu Java ảnh hưởng trực tiếp đến điều kiện tìm kiếm.

### Null và primitive default

Các property null thường được bỏ qua theo mặc định. Tuy nhiên, primitive như boolean và int luôn có giá trị mặc định (false và 0), nên chúng có thể trở thành điều kiện ngoài ý muốn.

Ví dụ nếu probe có:

~~~java
private boolean active;
private int age;
~~~

Một probe mới có thể mang active = false và age = 0. QBE có thể hiểu đây là giá trị cần so khớp, dù người dùng không yêu cầu lọc hai trường đó. Với bộ lọc tùy chọn, wrapper Boolean và Integer thường phù hợp hơn vì có thể để null khi không muốn áp dụng điều kiện.

Nếu muốn loại một property khỏi probe, có thể dùng withIgnorePaths("age"). Đừng dựa vào việc khởi tạo entity rồi hy vọng mọi giá trị mặc định sẽ tự bị bỏ qua.

### matchingAll và matchingAny

- matchingAll() yêu cầu tất cả property có giá trị trong probe đều phải khớp (logic AND).
- matchingAny() cho phép một trong các property có giá trị khớp (logic OR).

Ví dụ:

~~~java
ExampleMatcher anyFieldMatches = ExampleMatcher.matchingAny()
    .withIgnorePaths("active", "age");
~~~

Với probe chứa cả firstName và lastName, matcher này tìm entity khớp ít nhất một trong các property được xét. Đây là OR trên các điều kiện được chọn; nó không cung cấp cách biểu đạt tùy ý các nhóm logic như (firstName = ? AND active = true) OR (lastName = ? AND age > ?). Với điều kiện nhóm phức tạp, dùng Cypher tường minh.

### Giới hạn với relationship và cấu trúc graph

QBE thuận tiện cho điều kiện property đơn giản trên probe, nhưng không phải công cụ để mô tả mọi pattern graph. Các truy vấn cần:

- Traversal nhiều cấp hoặc nhiều nhánh relationship.
- Điều kiện trên relationship property.
- Aggregation, path hoặc subquery.
- Điều kiện OR/AND có nhóm ngoặc tùy ý.
- Sắp xếp theo một phép tính hoặc node liên quan phức tạp.

nên được biểu đạt bằng @Query hoặc Neo4jClient. Không giả định rằng đặt một object relationship vào probe sẽ tự tạo đúng traversal và điều kiện graph mà nghiệp vụ cần. Kiểm tra hỗ trợ cụ thể của SDN version và viết integration test cho mapping quan hệ.

## Khi nào dùng QBE, fluent query hay Cypher?

| Nhu cầu | Cách tiếp cận |
|---|---|
| Tìm theo vài property đơn giản do người dùng nhập | QBE với ExampleMatcher |
| Tìm và sắp xếp theo property của entity | findAll(example, sort) |
| Phân trang cùng tổng số kết quả | findAll(example, pageable) |
| Cần giới hạn, sắp xếp hoặc phân trang linh hoạt tại nơi gọi | Fluent query nếu Commons/SDN hỗ trợ |
| Chỉ cần một kết quả đầu tiên hoặc kiểm tra tồn tại | findOne(example) hoặc fluent first()/exists() |
| Lọc qua nhiều relationship hoặc điều kiện Cypher đặc thù | @Query hoặc Neo4jClient |
| Trả dữ liệu tổng hợp cho màn hình | DTO/projection với truy vấn tường minh |

QBE giúp giảm mã khi tiêu chí tìm kiếm thay đổi theo các trường người dùng nhập. Fluent query bổ sung cách điều khiển kết quả tại nơi gọi, nhưng không thay đổi giới hạn cốt lõi của QBE. Khi yêu cầu truy vấn đã trở thành một pattern graph cụ thể, Cypher thường dễ kiểm tra và tối ưu hơn.

## Những lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Dùng fluent findBy với Spring Data Commons cũ | Không biên dịch hoặc repository không có method | Kiểm tra dependency đã resolve; dùng findAll(example, pageable/sort) nếu chưa hỗ trợ |
| Tự nâng riêng Spring Data Commons | Có thể lệch phiên bản với SDN và Spring Boot | Ưu tiên dependency management của Spring Boot |
| Sort theo tên label hoặc relationship type | Không khớp property của entity | Dùng tên property Java hợp lệ |
| Chỉ sort theo trường không duy nhất | Thứ tự giữa các trang có thể thay đổi | Thêm property định danh làm tiêu chí phụ |
| Dùng primitive trong probe cho bộ lọc tùy chọn | Giá trị mặc định false hoặc 0 bị dùng làm điều kiện | Dùng wrapper hoặc withIgnorePaths |
| Đưa relationship vào probe và kỳ vọng traversal tùy ý | Điều kiện graph có thể không được biểu đạt như mong muốn | Dùng @Query hoặc Neo4jClient |
| Dùng matchingAny() để thay cho biểu thức logic nhóm | Không thể biểu đạt chính xác các nhóm AND/OR phức tạp | Viết Cypher với ngoặc rõ ràng |
| Trả Page khi chỉ cần biết còn dữ liệu hay không | Phát sinh chi phí đếm tổng | Cân nhắc Slice hoặc lấy thêm một phần tử |
| Không giới hạn page size | Tải quá nhiều dữ liệu trong một request | Xác thực và đặt page size tối đa |

## Bài tập thực hành

Với entity Person có employeeCode, firstName, lastName, email, active và age, hãy thực hiện:

1. Tạo probe để tìm người có họ chứa chuỗi nhập vào, không phân biệt hoa thường.
2. Kết hợp điều kiện active = true bằng matchingAll().
3. Dùng Sort sắp xếp theo họ, tên và employeeCode.
4. Dùng PageRequest.of(0, 20, sort) và đọc totalElements, totalPages, hasNext.
5. Thử thay Boolean bằng boolean trong probe để quan sát ảnh hưởng của giá trị mặc định.
6. Dùng matchingAny() với firstName và lastName, sau đó giải thích phạm vi OR mà matcher tạo ra.
7. Kiểm tra phiên bản Spring Data Commons trong dependency và thử fluent findBy(example, query -> query.page(pageable)) nếu API có sẵn.
8. Dùng fluent query để lấy 10 kết quả đầu tiên theo employeeCode.
9. Thử một bộ lọc cần traversal sang Department; giải thích vì sao QBE có thể không đủ và viết lại bằng @Query.
10. Viết integration test cho trang đầu, trang cuối, page size không hợp lệ và trường hợp không có kết quả.

Khi dùng Query by Example trong Spring Data Neo4j, hãy tạo probe và matcher rõ ràng, chọn Sort có thứ tự ổn định và dùng Pageable khi cần metadata phân trang. Chỉ sử dụng fluent query khi phiên bản Spring Data Commons và module SDN của dự án hỗ trợ; nếu API chưa có, các overload QBE cơ bản vẫn cung cấp phân trang và sắp xếp cần thiết.

