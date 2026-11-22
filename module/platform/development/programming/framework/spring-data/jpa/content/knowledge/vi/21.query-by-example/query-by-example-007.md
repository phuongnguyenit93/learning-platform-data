# Thực thi linh hoạt với fluent query của QueryByExampleExecutor

Query by Example (QBE) cho phép tạo điều kiện tìm kiếm từ một đối tượng mẫu (probe) và ExampleMatcher. Khi Repository kế thừa QueryByExampleExecutor, ứng dụng có thể gọi findBy() để thực thi Example bằng một fluent query. Fluent query cho phép tùy chỉnh cách lấy kết quả ngay tại nơi gọi: sắp xếp, giới hạn số dòng, chọn projection và lấy dữ liệu dưới dạng List, Page, Slice, Window hoặc Stream.

Cách tiếp cận này hữu ích khi cùng một điều kiện tìm kiếm cần được dùng theo nhiều hình thức khác nhau. Ví dụ, màn hình danh sách cần Page, hộp gợi ý chỉ cần 10 kết quả đầu, API báo cáo cần projection, còn tác vụ xử lý dữ liệu lớn muốn cuộn theo Window. Thay vì tạo nhiều phương thức Repository gần giống nhau, có thể giữ một Example rồi chọn cách thực thi bằng fluent query.

## 1. QueryByExampleExecutor và phương thức findBy()

QueryByExampleExecutor là interface của Spring Data cung cấp các thao tác tìm kiếm theo Example. JpaRepository kế thừa khả năng Query by Example, vì vậy Repository thông thường có thể dùng findBy() mà không cần tự implement interface này.

Phương thức fluent query có dạng khái quát:

~~~java
<S extends T, R> R findBy(
        Example<S> example,
        Function<FetchableFluentQuery<S>, R> queryFunction
);
~~~

Ý nghĩa các kiểu:

- T là kiểu Entity mà Repository quản lý.
- S là kiểu probe được dùng để tạo Example, thường là chính Entity T hoặc một subtype phù hợp.
- R là kiểu kết quả mà hàm queryFunction trả về.
- Example chứa probe và ExampleMatcher.
- FetchableFluentQuery cung cấp các thao tác cấu hình truy vấn và các phương thức kết thúc để lấy kết quả.

Điểm quan trọng là findBy() nhận một hàm. Spring Data đưa fluent query vào hàm đó; ứng dụng cấu hình truy vấn rồi gọi một terminal operation như all(), page(), slice(), scroll() hoặc stream(). Kết quả cuối cùng của terminal operation trở thành giá trị trả về của findBy().

## 2. Chuẩn bị Entity và Repository

Ví dụ dùng Entity Person:

~~~java
import jakarta.persistence.*;

@Entity
@Table(name = "people")
public class Person {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String firstName;
    private String lastName;
    private Boolean active;

    protected Person() {
    }

    public Person(String firstName, String lastName, Boolean active) {
        this.firstName = firstName;
        this.lastName = lastName;
        this.active = active;
    }

    public Long getId() {
        return id;
    }

    public String getFirstName() {
        return firstName;
    }

    public String getLastName() {
        return lastName;
    }

    public Boolean getActive() {
        return active;
    }

    public void setFirstName(String firstName) {
        this.firstName = firstName;
    }

    public void setLastName(String lastName) {
        this.lastName = lastName;
    }

    public void setActive(Boolean active) {
        this.active = active;
    }
}
~~~

Repository:

~~~java
import org.springframework.data.jpa.repository.JpaRepository;

public interface PersonRepository
        extends JpaRepository<Person, Long> {
}
~~~

JpaRepository cung cấp sẵn khả năng Query by Example. Có thể tạo probe và ExampleMatcher trong service rồi truyền vào findBy().

Probe là một đối tượng dùng để mô tả điều kiện. Các thuộc tính có giá trị sẽ được dùng để tạo predicate theo matcher; các thuộc tính null thường được bỏ qua theo mặc định.

## 3. Tạo Example từ probe và ExampleMatcher

Ví dụ tìm người có họ bắt đầu bằng “Nguyen”, không phân biệt chữ hoa/thường:

~~~java
Person probe = new Person(null, "Nguyen", null);

ExampleMatcher matcher = ExampleMatcher.matchingAll()
        .withIgnorePaths("id")
        .withMatcher(
                "lastName",
                ExampleMatcher.GenericPropertyMatchers
                        .startsWith()
                        .ignoreCase()
        );

Example<Person> example = Example.of(probe, matcher);
~~~

Trong ví dụ:

- Probe chỉ có lastName được đặt giá trị.
- id được bỏ qua tường minh.
- matchingAll() yêu cầu các điều kiện được tạo từ những thuộc tính được xét phải cùng đúng.
- startsWith() tạo điều kiện tìm theo tiền tố.
- ignoreCase() yêu cầu so sánh chuỗi không phân biệt hoa/thường.

ExampleMatcher là đối tượng cấu hình bất biến; các phương thức with... trả về matcher đã được cấu hình để tiếp tục sử dụng.

### matchingAll() và matchingAny()

Hai chế độ kết hợp điều kiện phổ biến:

- matchingAll(): kết hợp các thuộc tính được xét bằng AND.
- matchingAny(): kết hợp các thuộc tính được xét bằng OR.

Ví dụ probe có cả firstName và lastName:

~~~java
Person probe = new Person("An", "Nguyen", null);

ExampleMatcher allMatcher = ExampleMatcher.matchingAll()
        .withIgnoreCase();

ExampleMatcher anyMatcher = ExampleMatcher.matchingAny()
        .withIgnoreCase();

Example<Person> allExample = Example.of(probe, allMatcher);
Example<Person> anyExample = Example.of(probe, anyMatcher);
~~~

allExample tìm người thỏa cả firstName và lastName. anyExample tìm người thỏa firstName hoặc lastName.

QBE không phải bộ xây dựng biểu thức Boolean tổng quát. matchingAny() áp dụng OR cho các thuộc tính được xét; nó không cho phép tự do nhóm biểu thức như (firstName = ? OR lastName = ?) AND active = true theo mọi cấu trúc tùy ý. Khi cần nhóm điều kiện phức tạp, cân nhắc Specification, Querydsl hoặc @Query.

## 4. Fluent query thay đổi cách lấy kết quả

Sau khi tạo Example, có thể dùng findBy() để cấu hình cách thực thi:

~~~java
List<Person> people = repository.findBy(
        example,
        query -> query
                .sortBy(Sort.by("lastName").ascending())
                .all()
);
~~~

Ở đây:
- query là FetchableFluentQuery được Spring Data cung cấp trong callback.
- sortBy() thêm thứ tự sắp xếp.
- all() thực thi truy vấn và trả về List<Person>.

Tên thuộc tính trong Sort là tên thuộc tính Java của Entity, ví dụ lastName, không phải tên cột SQL như last_name.

Điểm mạnh của fluent query là điều kiện Example và cách lấy kết quả được tách riêng. Có thể giữ nguyên Example nhưng thay terminal operation tùy theo use case.

## 5. Giới hạn số kết quả bằng limit()

Nếu chỉ cần một số lượng kết quả tối đa, dùng limit():

~~~java
List<Person> suggestions = repository.findBy(
        example,
        query -> query
                .sortBy(Sort.by("lastName").ascending())
                .limit(10)
                .all()
);
~~~

Truy vấn trả tối đa 10 Person phù hợp. limit() hữu ích cho autocomplete, danh sách gợi ý hoặc các thao tác chỉ cần một tập kết quả nhỏ.

Limit không đồng nghĩa với phân trang. Nó chỉ đặt giới hạn tối đa cho kết quả được lấy. Nếu cần điều hướng nhiều trang, dùng page() hoặc slice(); nếu cần tiếp tục cuộn theo vị trí, dùng scroll().

Nên kết hợp limit() với Sort ổn định nếu kết quả cần có thứ tự xác định. Nếu chỉ sắp xếp theo một trường có thể trùng, hãy thêm ID làm tiêu chí phụ.

## 6. Sắp xếp linh hoạt bằng sortBy()

Fluent query nhận Sort để điều khiển thứ tự kết quả:

~~~java
List<Person> people = repository.findBy(
        example,
        query -> query
                .sortBy(Sort.by(
                        Sort.Order.asc("lastName"),
                        Sort.Order.asc("firstName"),
                        Sort.Order.asc("id")
                ))
                .all()
);
~~~

Thứ tự trên sắp xếp theo lastName, sau đó firstName, cuối cùng id. ID tạo tie-breaker để kết quả có thứ tự xác định khi nhiều người có cùng tên.

Có thể tạo Sort trước rồi truyền vào:

~~~java
Sort sort = Sort.by(
        Sort.Order.desc("active"),
        Sort.Order.asc("lastName")
);

List<Person> people = repository.findBy(
        example,
        query -> query.sortBy(sort).all()
);
~~~

Không lấy tên cột SQL làm thuộc tính Sort khi dùng fluent query trên Entity. Spring Data cần tên thuộc tính persistent trong mô hình Java. Nếu sắp xếp theo biểu thức SQL tùy chỉnh hoặc hàm database, cần một query mechanism phù hợp hơn.

## 7. Chuyển kết quả thành projection bằng as()

Fluent query có thể trả về một kiểu projection thay vì toàn bộ Entity. Ví dụ interface projection:

~~~java
public interface PersonSummary {
    Long getId();
    String getFirstName();
    String getLastName();
}
~~~

Sử dụng as():

~~~java
List<PersonSummary> summaries = repository.findBy(
        example,
        query -> query
                .as(PersonSummary.class)
                .sortBy(Sort.by("lastName").ascending())
                .all()
);
~~~

as(PersonSummary.class) yêu cầu Spring Data tạo kết quả theo kiểu projection. Điều này hữu ích khi API chỉ cần một số trường và không cần toàn bộ trạng thái Entity.

Projection giúp thể hiện rõ dữ liệu đầu ra, giảm việc chuyển đổi thủ công và có thể hạn chế các thuộc tính được đọc tùy kiểu projection/provider. Hãy kiểm tra SQL thực tế nếu mục tiêu là giảm số cột được SELECT.

### Chọn các thuộc tính bằng project()

project() cho phép chỉ định các thuộc tính cần đưa vào kết quả:

~~~java
List<Person> partialPeople = repository.findBy(
        example,
        query -> query
                .project("id", "firstName", "lastName")
                .all()
);
~~~

Tên thuộc tính trong project() là tên persistent property của Entity. Chỉ chọn những trường cần thiết cho use case.

Khi kết hợp projection và scrolling bằng keyset, cần giữ trong projection tất cả thuộc tính sắp xếp và khóa cần thiết để Spring Data xác định vị trí tiếp theo. Không loại bỏ trường sort chỉ vì giao diện không hiển thị trường đó.

## 8. Phân trang bằng page()

Nếu giao diện cần tổng số phần tử và tổng số trang, dùng page():

~~~java
Page<Person> page = repository.findBy(
        example,
        query -> query
                .sortBy(Sort.by("lastName").ascending())
                .page(PageRequest.of(0, 20))
);
~~~

Kết quả là Page<Person>, có thể lấy:

~~~java
List<Person> content = page.getContent();
long totalElements = page.getTotalElements();
int totalPages = page.getTotalPages();
boolean hasNext = page.hasNext();
~~~

Page có thông tin tổng số. Spring Data có thể cần count query để tính totalElements, dù trong một số trường hợp framework suy ra được tổng số từ nội dung trang và có thể tránh truy vấn đếm riêng.

Dùng Page khi giao diện thực sự cần tổng số chính xác. Với bảng lớn, count query có thể là phần tốn kém đáng kể.

## 9. Dùng slice() khi không cần tổng số

Nếu giao diện chỉ cần biết còn dữ liệu để tải tiếp, dùng Slice():

~~~java
Slice<Person> slice = repository.findBy(
        example,
        query -> query
                .sortBy(Sort.by("id").ascending())
                .slice(PageRequest.of(0, 50))
);
~~~

Slice cung cấp nội dung hiện tại và trạng thái hasNext(), nhưng không cung cấp totalElements hoặc totalPages như Page. Do đó, nó tránh nhu cầu đếm tổng số chính xác.

Ví dụ:

~~~java
if (slice.hasNext()) {
    // Hiển thị nút tải thêm hoặc chuyển trang.
}
~~~

Chọn Page cho giao diện cần “trang 2 trên 10”. Chọn Slice cho danh sách cuộn hoặc nút “Tải thêm” khi chỉ cần biết có phần tử tiếp theo.

## 10. Cuộn kết quả bằng scroll()

Fluent query cũng có thể trả Window<T> để cuộn theo ScrollPosition:

~~~java
Window<Person> window = repository.findBy(
        example,
        query -> query
                .sortBy(Sort.by("id").ascending())
                .scroll(ScrollPosition.offset())
);
~~~

Sau đó, lấy vị trí phần tử cuối để yêu cầu Window kế tiếp:

~~~java
ScrollPosition nextPosition =
        window.positionAt(window.size() - 1);

Window<Person> nextWindow = repository.findBy(
        example,
        query -> query
                .sortBy(Sort.by("id").ascending())
                .scroll(nextPosition)
);
~~~

Vị trí cuộn có ngữ nghĩa exclusive: cửa sổ tiếp theo bắt đầu sau phần tử được chỉ định. Vì vậy, dùng vị trí của phần tử cuối đã xử lý để tránh lặp phần tử.

Cần kiểm tra window.isEmpty() và window.hasNext() trước khi lấy vị trí. Nếu cửa sổ rỗng, không được gọi positionAt(-1).

Ví dụ vòng lặp:

~~~java
ScrollPosition position = ScrollPosition.offset();

while (true) {
    Window<Person> window = repository.findBy(
            example,
            query -> query
                    .sortBy(Sort.by("id").ascending())
                    .scroll(position)
    );

    if (window.isEmpty()) {
        break;
    }

    for (Person person : window) {
        process(person);
    }

    if (!window.hasNext()) {
        break;
    }

    position = window.positionAt(window.size() - 1);
}
~~~

Đoạn vòng lặp minh họa ý tưởng điều khiển từng Window; trong Java, biến được capture trong lambda phải là final hoặc effectively final. Khi cập nhật vị trí qua nhiều vòng, có thể dùng một biến final cho từng lần gọi hoặc dùng WindowIterator để tránh vấn đề capture.

Cách viết hoàn chỉnh với biến vị trí được chụp theo từng vòng:

~~~java
ScrollPosition position = ScrollPosition.offset();

while (true) {
    ScrollPosition currentPosition = position;

    Window<Person> window = repository.findBy(
            example,
            query -> query
                    .sortBy(Sort.by("id").ascending())
                    .scroll(currentPosition)
    );

    if (window.isEmpty()) {
        break;
    }

    for (Person person : window) {
        process(person);
    }

    if (!window.hasNext()) {
        break;
    }

    position = window.positionAt(window.size() - 1);
}
~~~

Nếu dùng keyset scrolling, hãy chọn thứ tự ổn định, có ID làm tie-breaker và bảo đảm các thuộc tính sort không-null, có mặt trong projection.

## 11. Duyệt nhiều Window bằng WindowIterator

WindowIterator đơn giản hóa việc lặp qua các Window:

~~~java
import org.springframework.data.domain.ScrollPosition;
import org.springframework.data.support.WindowIterator;

WindowIterator<Person> iterator = WindowIterator.of(position ->
        repository.findBy(
                example,
                query -> query
                        .sortBy(Sort.by("id").ascending())
                        .scroll(position)
        )
).startingAt(ScrollPosition.offset());

while (iterator.hasNext()) {
    Person person = iterator.next();
    process(person);
}
~~~

WindowIterator nhận hàm tạo Window theo ScrollPosition, tự chuyển sang vị trí tiếp theo và cung cấp các phần tử lần lượt cho vòng lặp.

Dùng WindowIterator khi muốn xử lý từng phần tử tuần tự. Dùng vòng lặp thủ công khi cần kiểm soát checkpoint, transaction hoặc logging theo từng Window.

Scrolling qua QBE giúp kết hợp điều kiện probe với việc đọc tập dữ liệu theo từng phần. Tuy nhiên, nó không tạo snapshot bất biến của toàn bộ bảng; nếu dữ liệu thay đổi trong lúc xử lý, kết quả có thể chịu ảnh hưởng của thứ tự và điều kiện truy vấn.

## 12. Dùng stream() và quản lý tài nguyên

Fluent query có thể trả Stream<T>:

~~~java
@Transactional(readOnly = true)
public void processMatchingPeople(Example<Person> example) {
    try (Stream<Person> people = repository.findBy(
            example,
            query -> query
                    .sortBy(Sort.by("id").ascending())
                    .stream()
    )) {
        people.forEach(this::process);
    }
}
~~~

Stream có thể gắn với tài nguyên JDBC hoặc persistence provider. Vì vậy:
- Tiêu thụ Stream trong transaction phù hợp.
- Đóng Stream bằng try-with-resources.
- Không trả Stream ra khỏi service sau khi transaction đã kết thúc.
- Không giữ Stream mở lâu hơn cần thiết.
- Nếu cần checkpoint và xử lý theo lô, cân nhắc Window thay cho Stream.

Stream và Window có vòng đời khác nhau. Stream là luồng phần tử có thể giữ tài nguyên mở; Window là một phần kết quả giới hạn được lấy qua một truy vấn.

## 13. Kết hợp limit(), projection và sortBy()

Các thao tác fluent có thể kết hợp để tạo một truy vấn đọc cụ thể:

~~~java
List<PersonSummary> suggestions = repository.findBy(
        example,
        query -> query
                .as(PersonSummary.class)
                .project("id", "firstName", "lastName")
                .sortBy(Sort.by(
                        Sort.Order.asc("lastName"),
                        Sort.Order.asc("id")
                ))
                .limit(15)
                .all()
);
~~~

Ví dụ này:
1. Dùng Example làm điều kiện tìm kiếm.
2. Chuyển kết quả sang PersonSummary.
3. Chỉ yêu cầu các thuộc tính cần cho projection.
4. Sắp xếp theo lastName rồi id.
5. Giới hạn tối đa 15 kết quả.
6. Thực thi và trả List<PersonSummary>.

Hãy bảo đảm projection có các thuộc tính cần cho việc sắp xếp và mọi cơ chế tiếp tục cuộn nếu dùng keyset. Khi kết hợp as() và project(), hãy kiểm tra integration test với phiên bản Spring Data JPA đang chạy để xác nhận kiểu projection và tập cột được ánh xạ như mong muốn.

## 14. findBy() phải trả kết quả cuối cùng trong callback

Một đặc điểm quan trọng của fluent query là đối tượng FetchableFluentQuery chỉ được sử dụng trong phạm vi callback findBy(). Callback phải thực thi một terminal operation và trả kết quả cuối cùng.

Đúng:

~~~java
List<Person> people = repository.findBy(
        example,
        query -> query
                .sortBy(Sort.by("id"))
                .all()
);
~~~

Không nên trả chính query object để dùng sau callback:

~~~java
// Không làm như vậy:
var query = repository.findBy(
        example,
        queryFunction -> queryFunction
);
~~~

Fluent query là đối tượng cấu hình truy vấn có phạm vi sử dụng trong callback. Không lưu nó vào field, không cache nó để thực thi ở thời điểm khác và không trả nó ra ngoài. Hãy gọi all(), page(), slice(), scroll(), stream() hoặc terminal operation phù hợp ngay trong lambda.

## 15. Các terminal operation thường dùng

Các terminal operation quyết định kiểu kết quả cuối cùng:

| Terminal operation | Kết quả | Dùng khi |
|---|---|---|
| all() | List<T> hoặc List<Projection> | Lấy tất cả kết quả phù hợp trong giới hạn truy vấn |
| page(Pageable) | Page<T> | Cần tổng số và thông tin trang |
| slice(Pageable) | Slice<T> | Cần biết còn trang tiếp theo |
| scroll(ScrollPosition) | Window<T> | Đọc theo cửa sổ và tiếp tục bằng vị trí |
| stream() | Stream<T> | Xử lý luồng và quản lý tài nguyên đúng cách |

Kiểu T trong bảng có thể là Entity hoặc kiểu projection sau khi cấu hình as(). Chọn terminal operation theo nhu cầu thực tế; không dùng Page chỉ vì nó có nhiều metadata nếu giao diện không cần tổng số.

## 16. Giới hạn của Query by Example

Fluent query chỉ thay đổi cách thực thi và định dạng kết quả. Nó không làm QBE trở thành một ngôn ngữ truy vấn tổng quát.

Các giới hạn quan trọng của QBE:

- Không biểu diễn được mọi phép so sánh như greater-than, less-than, between hoặc các biểu thức tùy ý cho mọi kiểu dữ liệu.
- Không hỗ trợ cấu trúc nhóm Boolean phức tạp tùy ý như kết hợp nhiều nhóm AND/OR lồng nhau.
- Không phù hợp để mô tả mọi truy vấn collection hoặc Map.
- Các thuộc tính null thường bị bỏ qua theo mặc định; muốn xử lý null cần cấu hình null handling phù hợp.
- Giá trị mặc định của primitive như false hoặc 0 có thể được xem là giá trị probe, vì primitive không thể biểu diễn trạng thái “chưa đặt”.
- Hành vi so sánh chuỗi và ignore case vẫn phụ thuộc provider/database.

Nếu cần điều kiện như price > 100, createdAt BETWEEN hai mốc, hoặc (status = A OR status = B) AND tenantId = X, hãy cân nhắc Specification, Criteria API, Querydsl hoặc @Query.

Với probe, nên ưu tiên wrapper như Boolean hoặc Integer khi cần phân biệt “không lọc thuộc tính này” với “lọc theo false/0”.

## 17. Phân biệt điều kiện Example và fluent query

Hai phần này có trách nhiệm khác nhau:

| Thành phần | Trách nhiệm |
|---|---|
| Probe | Chứa các giá trị mẫu |
| ExampleMatcher | Quy định cách so sánh và kết hợp các giá trị probe |
| Example | Đóng gói probe cùng matcher |
| findBy() | Nhận Example và mở fluent query |
| Fluent query | Cấu hình sort, limit, projection và cách lấy kết quả |
| Terminal operation | Thực thi và trả List, Page, Slice, Window hoặc Stream |

Ví dụ, thay đổi từ all() sang page() không thay đổi điều kiện tìm kiếm. Nó chỉ thay đổi cách kết quả được lấy và metadata đi kèm.

Tương tự, thay đổi as(PersonSummary.class) không làm Example khớp thêm hoặc bớt bản ghi; nó thay đổi hình dạng dữ liệu trả về.

## 18. Ví dụ service tái sử dụng một Example

Có thể đóng gói việc tạo Example trong service rồi dùng nhiều fluent query khác nhau:

~~~java
import org.springframework.data.domain.*;
import org.springframework.data.domain.Example;
import org.springframework.data.domain.ExampleMatcher;
import org.springframework.stereotype.Service;
import java.util.List;

@Service
public class PersonSearchService {

    private final PersonRepository repository;

    public PersonSearchService(PersonRepository repository) {
        this.repository = repository;
    }

    private Example<Person> createExample(String lastName) {
        Person probe = new Person(null, lastName, true);

        ExampleMatcher matcher = ExampleMatcher.matchingAll()
                .withIgnorePaths("id")
                .withMatcher(
                        "lastName",
                        ExampleMatcher.GenericPropertyMatchers
                                .startsWith()
                                .ignoreCase()
                );

        return Example.of(probe, matcher);
    }

    public List<PersonSummary> suggestions(String lastName) {
        Example<Person> example = createExample(lastName);

        return repository.findBy(example, query -> query
                .as(PersonSummary.class)
                .sortBy(Sort.by("lastName").ascending())
                .limit(10)
                .all());
    }

    public Page<Person> searchPage(
            String lastName,
            Pageable pageable) {

        Example<Person> example = createExample(lastName);

        return repository.findBy(example, query -> query
                .sortBy(Sort.by("lastName").ascending())
                .page(pageable));
    }
}
~~~

Service tái sử dụng cùng quy tắc tìm kiếm nhưng chọn kết quả khác nhau:
- suggestions() trả tối đa 10 projection cho hộp gợi ý.
- searchPage() trả Page<Person> cho màn hình có phân trang.

Đây là ví dụ cấu trúc minh họa. Dự án cần có PersonRepository, PersonSummary và các Entity accessor tương ứng. Nếu cần thay đổi điều kiện lọc, sửa createExample() hoặc tạo matcher riêng theo use case.

## 19. Kiểm thử fluent query

Nên kiểm tra cả điều kiện QBE và cách fluent query trả kết quả.

Ví dụ repository test:

~~~java
@DataJpaTest
class PersonRepositoryTest {

    @Autowired
    private PersonRepository repository;

    @Test
    void fluentQueryAppliesExampleSortAndLimit() {
        repository.save(new Person("An", "Nguyen", true));
        repository.save(new Person("Binh", "Nguyen", true));
        repository.save(new Person("Chi", "Tran", true));

        Person probe = new Person(null, "Nguyen", true);

        ExampleMatcher matcher = ExampleMatcher.matchingAll()
                .withIgnorePaths("id")
                .withMatcher(
                        "lastName",
                        ExampleMatcher.GenericPropertyMatchers
                                .exact()
                                .ignoreCase()
                );

        Example<Person> example = Example.of(probe, matcher);

        List<Person> result = repository.findBy(
                example,
                query -> query
                        .sortBy(Sort.by("firstName").ascending())
                        .limit(1)
                        .all()
        );

        assertEquals(1, result.size());
        assertEquals("An", result.get(0).getFirstName());
    }
}
~~~

Với dữ liệu fixture trên, kết quả mong đợi:

~~~text
size = 1
firstName = An
~~~

Nên bổ sung test cho:
1. matchingAll() và matchingAny().
2. IgnoreCase, exact, startsWith và containing.
3. Null probe fields và ignorePaths.
4. Primitive default values so với wrapper types.
5. sortBy() với nhiều tiêu chí.
6. limit() và projection.
7. Page có totalElements chính xác.
8. Slice có hasNext() đúng.
9. Window tiếp tục đúng vị trí, không lặp hoặc bỏ sót phần tử.
10. Stream được tiêu thụ và đóng trong transaction phù hợp.

Chạy integration test trên database mục tiêu nếu hành vi collation, kiểu dữ liệu hoặc kế hoạch truy vấn có ý nghĩa với ứng dụng. Không chỉ dựa vào test trên database in-memory để kết luận mọi hành vi production giống nhau.

## 20. Những lỗi thường gặp

**Chỉ tạo Example nhưng không gọi terminal operation**

Example chỉ mô tả điều kiện. findBy() cần callback thực thi một terminal operation để lấy kết quả.

**Trả fluent query ra khỏi callback**

Đối tượng query chỉ có phạm vi sử dụng trong callback. Trả nó ra ngoài hoặc lưu để dùng sau là sai vòng đời API.

**Nhầm sort property với tên cột SQL**

sortBy() trên Entity dùng tên thuộc tính Java như lastName, không dùng tên cột last_name.

**Dùng Page dù không cần tổng số**

Page có thể cần count query. Nếu chỉ cần biết còn kết quả tiếp theo, dùng Slice hoặc Window.

**Projection thiếu thuộc tính sort khi scrolling**

Keyset cần giá trị của thuộc tính sắp xếp và khóa để xác định vị trí. Đưa các trường này vào projection.

**Dùng primitive trong probe rồi vô tình lọc theo giá trị mặc định**

false hoặc 0 có thể trở thành điều kiện tìm kiếm. Dùng wrapper khi cần trạng thái chưa thiết lập.

**Kỳ vọng QBE biểu diễn điều kiện phức tạp tùy ý**

QBE có giới hạn về toán tử và nhóm Boolean. Chuyển sang Specification, Querydsl hoặc @Query khi điều kiện vượt khả năng matcher.

**Dùng Stream mà không đóng**

Stream có thể giữ tài nguyên JDBC. Dùng try-with-resources và transaction phù hợp.

**Dùng limit() thay cho phân trang**

limit chỉ giới hạn số kết quả tối đa. Dùng page(), slice() hoặc scroll() khi cần tiếp tục qua tập dữ liệu.

## 21. Quy trình chọn fluent query cho một use case

Khi xây dựng tìm kiếm linh hoạt:

1. Tạo probe với các thuộc tính mà người dùng thực sự cung cấp.
2. Chọn ExampleMatcher: matchingAll hoặc matchingAny, kiểu so khớp chuỗi, ignore case và ignore paths.
3. Dùng Example.of(probe, matcher) để đóng gói điều kiện.
4. Gọi repository.findBy(example, query -> ...) để cấu hình fluent query.
5. Dùng sortBy() và limit() khi cần sắp xếp hoặc giới hạn.
6. Dùng as() hoặc project() nếu chỉ cần một phần dữ liệu.
7. Chọn all(), page(), slice(), scroll() hoặc stream() theo cách tiêu thụ kết quả.
8. Không trả fluent query object ra khỏi callback.
9. Kiểm tra SQL, count query, index và projection trên database thực tế.
10. Nếu điều kiện lọc vượt khả năng QBE, chuyển sang Specification, Querydsl hoặc @Query thay vì làm probe phức tạp khó hiểu.

## 22. Kết luận

QueryByExampleExecutor.findBy() kết hợp Example với FetchableFluentQuery để tách điều kiện tìm kiếm khỏi cách lấy kết quả. Probe và ExampleMatcher quyết định bản ghi nào phù hợp; fluent query quyết định sort, limit, projection và terminal operation. Dùng all() cho List, page() khi cần tổng số, slice() khi chỉ cần biết còn trang tiếp theo, scroll() cho Window và stream() khi quản lý tài nguyên đúng cách. Fluent query phải được thực thi trong callback và không được lưu hoặc trả ra ngoài. QBE vẫn có giới hạn về toán tử và nhóm điều kiện; với truy vấn phức tạp, hãy dùng Specification, Querydsl hoặc @Query.
