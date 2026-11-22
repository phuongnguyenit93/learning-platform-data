# Tìm kiếm, đếm, kiểm tra tồn tại và phân trang bằng Example

**Query by Example (QBE)** là cách xây dựng truy vấn động từ một object mẫu (probe). Thay vì viết một method repository cho từng tổ hợp bộ lọc hoặc tự ghép JPQL, ứng dụng tạo một entity có các field cần tìm, cấu hình quy tắc so khớp bằng `ExampleMatcher`, rồi đóng gói thành `Example<T>`.

Spring Data JPA cung cấp các thao tác tìm kiếm, đếm, kiểm tra tồn tại và phân trang dựa trên Example. QBE đặc biệt phù hợp với màn hình tìm kiếm có nhiều bộ lọc tùy chọn nhưng điều kiện chủ yếu là so sánh giá trị. Khi cần biểu thức phức tạp, điều kiện OR được nhóm, khoảng giá trị hoặc truy vấn trên collection, hãy cân nhắc Specification, Criteria API, Querydsl hoặc JPQL.

## 1. QBE gồm những thành phần nào?

QBE có bốn thành phần chính:

1. **Probe**: object domain chứa các giá trị muốn tìm. Các field được điền sẽ trở thành tiêu chí theo quy tắc nullability và matcher.
2. **ExampleMatcher**: mô tả cách so khớp, ví dụ AND/OR, bỏ qua field, so khớp chuỗi, không phân biệt hoa thường và cách xử lý null.
3. **Example**: kết hợp probe với matcher thành đối tượng truy vấn.
4. **FetchableFluentQuery**: API fluent để tùy chỉnh projection, sort, giới hạn, Page, Slice, Stream hoặc thao tác lấy kết quả khác.

Luồng tổng quát:

```text
Request tìm kiếm
      |
      v
Tạo probe từ các bộ lọc hợp lệ
      |
      v
Cấu hình ExampleMatcher
      |
      v
Example.of(probe, matcher)
      |
      +----------+-----------+------------+
      |          |           |            |
    findAll     count      exists      findOne
      |
      v
  Pageable / Sort
```

QBE không yêu cầu viết tên field trong câu JPQL/SQL cho từng điều kiện cơ bản. Tuy nhiên, khi cấu hình matcher theo từng thuộc tính, ta vẫn dùng property path Java như `firstName` hoặc `address.city`.

## 2. Repository cần hỗ trợ QueryByExampleExecutor

`JpaRepository<T, ID>` kế thừa `QueryByExampleExecutor<T>`, vì vậy repository Spring Data JPA thông thường đã có các method QBE:

```java
import org.springframework.data.jpa.repository.JpaRepository;

public interface PersonRepository
        extends JpaRepository<Person, Long> {
}
```

Không cần khai báo lại `findAll(Example)`, `count(Example)`, `exists(Example)` hay `findOne(Example)`.

Các method cốt lõi:

```java
<S extends T> Optional<S> findOne(Example<S> example);

<S extends T> Iterable<S> findAll(Example<S> example);

<S extends T> Iterable<S> findAll(Example<S> example, Sort sort);

<S extends T> Page<S> findAll(
    Example<S> example,
    Pageable pageable
);

<S extends T> long count(Example<S> example);

<S extends T> boolean exists(Example<S> example);
```

Trong hợp đồng `QueryByExampleExecutor`, `findAll(Example)` và `findAll(Example, Sort)` trả về `Iterable`. Hãy dùng đúng kiểu theo interface và phiên bản Spring Data đang dùng; nếu cần kiểu List, có thể chuyển kết quả hoặc khai báo kiểu phù hợp ở tầng ứng dụng.

## 3. Tạo entity làm probe

Ví dụ entity Person:

```java
import jakarta.persistence.*;

@Entity
@Table(name = "people")
public class Person {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "first_name")
    private String firstName;

    @Column(name = "last_name")
    private String lastName;

    private String city;

    private Integer age;

    private Boolean active;

    protected Person() {
    }

    public Long getId() {
        return id;
    }

    public String getFirstName() {
        return firstName;
    }

    public void setFirstName(String firstName) {
        this.firstName = firstName;
    }

    public String getLastName() {
        return lastName;
    }

    public void setLastName(String lastName) {
        this.lastName = lastName;
    }

    public String getCity() {
        return city;
    }

    public void setCity(String city) {
        this.city = city;
    }

    public Integer getAge() {
        return age;
    }

    public void setAge(Integer age) {
        this.age = age;
    }

    public Boolean getActive() {
        return active;
    }

    public void setActive(Boolean active) {
        this.active = active;
    }
}
```

Để làm ví dụ tìm kiếm, tạo một probe chỉ điền những tiêu chí cần dùng:

```java
Person probe = new Person();
probe.setFirstName("An");
probe.setCity("Da Nang");
probe.setActive(true);
```

Các thuộc tính `lastName`, `age` và `id` vẫn null. Theo mặc định, QBE bỏ qua property có giá trị null, nên chúng không trở thành điều kiện tìm kiếm.

Kết quả logic dự kiến là:

```sql
WHERE first_name = 'An'
  AND city = 'Da Nang'
  AND active = TRUE
```

Đây là mô tả logic. SQL thực tế do provider sinh ra có thể dùng bind parameter, alias và cú pháp riêng của database.

### 3.1. Cẩn thận với kiểu primitive

QBE xác định field có được đưa vào điều kiện hay không dựa trên nullability. Field reference có giá trị null thường bị bỏ qua. Field primitive như `int`, `long`, `boolean` luôn có giá trị mặc định và vì vậy luôn được xem là có giá trị, trừ khi bị ignore trong matcher.

Ví dụ:

```java
private boolean active;
private int age;
```

Một probe mới tạo có `active = false` và `age = 0`. QBE có thể hiểu đây là hai điều kiện tìm kiếm thực sự, dù người dùng không hề chọn chúng.

Với bộ lọc tùy chọn, nên dùng kiểu wrapper:

```java
private Boolean active;
private Integer age;
```

Khi không chọn active hoặc age, để chúng null. Khi người dùng chọn false hoặc 0, giá trị đó vẫn được biểu diễn chính xác và có thể trở thành tiêu chí tìm kiếm.

Cũng cần chú ý các field kỹ thuật như id, version hoặc thời điểm tạo. Nếu probe có giá trị ở những field này, hãy bỏ chúng khỏi matcher bằng `withIgnorePaths(...)` khi chúng không phải tiêu chí nghiệp vụ.

## 4. Example.of() với matcher mặc định

Tạo Example đơn giản:

```java
Person probe = new Person();
probe.setFirstName("An");

Example<Person> example = Example.of(probe);
```

`Example.of(probe)` sử dụng matcher mặc định:

- Các field null bị bỏ qua.
- Các field có giá trị được dùng làm điều kiện.
- Các điều kiện mặc định được kết hợp theo AND.
- Chuỗi dùng kiểu so khớp mặc định của store/provider; trong cấu hình thông thường là exact match và phân biệt hoa thường.
- Các kiểu không phải chuỗi được so khớp chính xác.

Vì hành vi chuỗi có thể phụ thuộc store và database, nên cấu hình rõ matcher khi yêu cầu nghiệp vụ cần starts-with, contains hoặc không phân biệt hoa thường.

Có thể tạo Example với matcher tường minh:

```java
ExampleMatcher matcher = ExampleMatcher.matchingAll();

Example<Person> example = Example.of(probe, matcher);
```

`matchingAll()` thể hiện rõ mọi điều kiện có giá trị trong probe phải cùng đúng. `matching()` cũng là cách viết thường dùng cho chế độ AND mặc định.

## 5. ExampleMatcher: cấu hình cách so khớp

`ExampleMatcher` cho phép đặt quy tắc chung và quy tắc riêng cho từng property path.

Ví dụ:

```java
ExampleMatcher matcher = ExampleMatcher.matchingAll()
    .withIgnorePaths("id", "age")
    .withIgnoreCase()
    .withStringMatcher(
        ExampleMatcher.StringMatcher.CONTAINING
    );
```

Ý nghĩa:

- `matchingAll()`: các điều kiện được kết hợp bằng AND.
- `withIgnorePaths("id", "age")`: không dùng id và age làm điều kiện.
- `withIgnoreCase()`: so khớp chuỗi không phân biệt hoa thường.
- `CONTAINING`: chuỗi trong probe phải xuất hiện ở bất kỳ vị trí nào trong giá trị lưu.

Nếu probe có `firstName = "an"` và `city = "da"`, điều kiện chuỗi tương đương ý tưởng:

```sql
LOWER(first_name) LIKE '%an%'
AND LOWER(city) LIKE '%da%'
```

Cú pháp SQL cụ thể phụ thuộc database/provider. So khớp không phân biệt hoa thường có thể làm thay đổi khả năng tận dụng index thông thường; nếu truy vấn quan trọng, hãy xem execution plan và cân nhắc collation hoặc functional index phù hợp.

### 5.1. Các chế độ StringMatcher

Các chế độ thường dùng:

| StringMatcher | Ý nghĩa | Ví dụ với probe "An" |
|---|---|---|
| EXACT | Khớp toàn bộ chuỗi | "An" |
| STARTING | Chuỗi bắt đầu bằng giá trị probe | "An Nguyen" |
| ENDING | Chuỗi kết thúc bằng giá trị probe | "Tran An" |
| CONTAINING | Chuỗi có chứa giá trị probe | "Nguyen An Binh" |
| DEFAULT | Dùng hành vi mặc định của store | Phụ thuộc store/provider |
| REGEX | Biểu thức chính quy ở một số store | Không được Spring Data JPA hỗ trợ cho QBE |

JPA không hỗ trợ regex matching trong QBE. Không cấu hình `REGEX` rồi kỳ vọng Hibernate sẽ tạo truy vấn regex portable.

### 5.2. Cấu hình matcher riêng từng field

Không phải mọi chuỗi đều nên dùng cùng một quy tắc. Ví dụ firstName cần starts-with, lastName cần contains, city cần exact:

```java
ExampleMatcher matcher = ExampleMatcher.matchingAll()
    .withIgnorePaths("id", "age")
    .withMatcher(
        "firstName",
        property -> property.startsWith().ignoreCase()
    )
    .withMatcher(
        "lastName",
        property -> property.contains().ignoreCase()
    )
    .withMatcher(
        "city",
        property -> property.exact().ignoreCase()
    );
```

Các cấu hình riêng theo property path có độ ưu tiên cao hơn cấu hình mặc định ở cấp matcher. Nhờ vậy, có thể đặt quy tắc chung rồi chỉ ghi đè những field cần hành vi khác.

Tên property phải là tên thuộc tính Java, không phải tên cột database. Trong ví dụ, dùng `firstName`, dù cột vật lý là `first_name`.

### 5.3. Ignore một số thuộc tính

Dùng `withIgnorePaths` khi probe chứa các field không nên trở thành điều kiện:

```java
ExampleMatcher matcher = ExampleMatcher.matchingAll()
    .withIgnorePaths("id", "createdAt", "updatedAt", "version");
```

Đây là cách hữu ích khi probe được tạo từ entity có nhiều field kỹ thuật. Dù field đang null thường bị bỏ qua, ignore path vẫn giúp bảo đảm chúng không vô tình trở thành tiêu chí nếu có giá trị.

### 5.4. Không phân biệt hoa thường

Có thể áp dụng cho mọi chuỗi:

```java
ExampleMatcher matcher = ExampleMatcher.matchingAll()
    .withIgnoreCase();
```

Hoặc chỉ một số property:

```java
ExampleMatcher matcher = ExampleMatcher.matchingAll()
    .withMatcher(
        "firstName",
        property -> property.exact().ignoreCase()
    );
```

Không phân biệt hoa thường thường được thực hiện bằng cách chuẩn hóa biểu thức so sánh ở database, chẳng hạn dùng LOWER. Hành vi phụ thuộc collation và database; kiểm thử với dữ liệu Unicode/tiếng Việt nếu ứng dụng có yêu cầu tìm kiếm ngôn ngữ cụ thể.

## 6. matchingAll() và matchingAny()

Mặc định QBE kết hợp các tiêu chí bằng AND. Ví dụ:

```java
ExampleMatcher matcher = ExampleMatcher.matchingAll();
```

Nếu probe có firstName = "An" và city = "Da Nang", kết quả cần thỏa cả hai:

```sql
WHERE first_name = 'An'
  AND city = 'Da Nang'
```

Dùng `matchingAny()` để kết hợp các predicate có giá trị bằng OR:

```java
ExampleMatcher matcher = ExampleMatcher.matchingAny()
    .withIgnorePaths("id");
```

Với probe có firstName = "An", city = "Da Nang", logic trở thành:

```sql
WHERE first_name = 'An'
   OR city = 'Da Nang'
```

matchingAny hữu ích cho tìm kiếm rộng, ví dụ tìm người có tên hoặc thành phố khớp một giá trị.

**Giới hạn quan trọng:** QBE không biểu diễn được các nhóm điều kiện AND/OR lồng nhau tùy ý, ví dụ:

```sql
WHERE first_name = 'An'
   OR (city = 'Da Nang' AND active = TRUE)
```

`matchingAny()` chỉ đổi cách kết hợp các predicate do probe tạo ra; nó không cung cấp cây biểu thức boolean để nhóm tùy ý. Với logic phức tạp như trên, dùng Specification, Criteria API, Querydsl hoặc JPQL.

## 7. Null handling: bỏ qua null hay tìm giá trị NULL?

Mặc định, QBE bỏ qua các field null. Ví dụ:

```java
Person probe = new Person();
probe.setCity("Da Nang");
// active vẫn null

Example<Person> example = Example.of(probe);
```

Chỉ city được dùng làm điều kiện. QBE không tự tạo `active IS NULL` cho field active.

Nếu muốn các field null trở thành điều kiện tìm các cột NULL, cấu hình:

```java
ExampleMatcher matcher = ExampleMatcher.matchingAll()
    .withIncludeNullValues()
    .withIgnorePaths("id");

Example<Person> example = Example.of(probe, matcher);
```

Khi đó các property null được đưa vào tiêu chí theo null handling của matcher. Cần dùng rất thận trọng: entity thường có nhiều field nullable, và include null values có thể tạo ra nhiều điều kiện IS NULL ngoài ý muốn.

Nếu yêu cầu là tìm những người có city NULL nhưng vẫn lọc active = true, hãy cân nhắc tạo probe/matcher riêng với ignore paths phù hợp hoặc dùng Specification/JPQL để biểu đạt rõ điều kiện. Đừng bật includeNullValues trên một entity lớn mà không kiểm soát các field được đưa vào query.

Null parameter cũng không đồng nghĩa với "bỏ qua bộ lọc" trong mọi trường hợp. QBE mặc định bỏ qua null vì null handling của ExampleMatcher; đây là quy tắc của QBE, không phải quy tắc chung của mọi query Spring Data.

## 8. Tìm kiếm bằng findAll(Example)

Ví dụ repository:

```java
public interface PersonRepository
        extends JpaRepository<Person, Long> {
}
```

Service tạo probe và lấy tất cả kết quả:

```java
@Service
public class PersonSearchService {

    private final PersonRepository repository;

    public PersonSearchService(PersonRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public Iterable<Person> search(String firstName, String city) {
        Person probe = new Person();
        probe.setFirstName(firstName);
        probe.setCity(city);

        ExampleMatcher matcher = ExampleMatcher.matchingAll()
            .withIgnorePaths("id", "age");

        Example<Person> example = Example.of(probe, matcher);

        return repository.findAll(example);
    }
}
```

Nếu không có bản ghi phù hợp, `findAll(example)` trả về một Iterable rỗng. Không cần kiểm tra kết quả null.

Không dùng `findAll(example)` cho bảng có thể trả về rất nhiều bản ghi mà không có giới hạn. Đây là truy vấn không phân trang; cân nhắc Page hoặc Slice khi dữ liệu lớn.

## 9. Đếm bằng count(Example)

Có thể đếm số entity thỏa cùng một probe/matcher:

```java
long count = repository.count(example);
```

Ví dụ:

```java
@Transactional(readOnly = true)
public long countActivePeopleInCity(String city) {
    Person probe = new Person();
    probe.setCity(city);
    probe.setActive(true);

    ExampleMatcher matcher = ExampleMatcher.matchingAll()
        .withIgnorePaths("id", "age");

    return repository.count(Example.of(probe, matcher));
}
```

`count(example)` trả về `long`, không tải toàn bộ entity chỉ để đếm. Database vẫn phải thực hiện truy vấn đếm theo các điều kiện tương ứng; hiệu năng phụ thuộc số dòng, index, độ chọn lọc và join do mapping tạo ra.

Nếu chỉ cần biết có ít nhất một kết quả, hãy dùng `exists(example)` thay vì đếm tất cả rồi so sánh với 0.

## 10. Kiểm tra tồn tại bằng exists(Example)

Method:

```java
boolean exists = repository.exists(example);
```

trả true nếu có ít nhất một entity phù hợp và false nếu không có.

Ví dụ kiểm tra có người đang hoạt động ở thành phố:

```java
@Transactional(readOnly = true)
public boolean hasActivePerson(String city) {
    Person probe = new Person();
    probe.setCity(city);
    probe.setActive(true);

    Example<Person> example = Example.of(
        probe,
        ExampleMatcher.matchingAll().withIgnorePaths("id", "age")
    );

    return repository.exists(example);
}
```

Không nên dùng `count(example) > 0` khi mục đích chỉ là tồn tại. exists diễn đạt đúng ý định và cho provider/database cơ hội tối ưu truy vấn theo nhu cầu boolean.

QBE existence check cũng không thay thế unique constraint. Nếu cần bảo đảm một thuộc tính duy nhất, hãy đặt constraint/index ở database và xử lý xung đột đồng thời trong service.

## 11. Tìm một kết quả bằng findOne(Example)

`findOne(example)` trả về `Optional<T>`:

```java
Optional<Person> person = repository.findOne(example);
```

- Không có kết quả: Optional.empty().
- Có đúng một kết quả: Optional chứa entity.
- Có nhiều hơn một kết quả: ném `IncorrectResultSizeDataAccessException`.

Vì vậy, chỉ dùng findOne khi điều kiện probe có tính duy nhất theo nghiệp vụ hoặc database constraint. Không dùng nó như cách tùy tiện lấy một bản ghi đầu tiên trong nhiều kết quả.

Nếu muốn lấy một kết quả đầu tiên theo thứ tự, dùng fluent API với `first()` và sort:

```java
Optional<Person> first = repository.findBy(
    example,
    query -> query
        .sortBy(Sort.by(Sort.Order.asc("lastName"), Sort.Order.asc("id")))
        .first()
);
```

Sort có thêm id làm tie-breaker để kết quả có thứ tự xác định khi lastName trùng nhau.

## 12. Phân trang bằng findAll(Example, Pageable)

QBE hỗ trợ trực tiếp Page:

```java
Pageable pageable = PageRequest.of(
    0,
    20,
    Sort.by(
        Sort.Order.asc("lastName"),
        Sort.Order.asc("id")
    )
);

Page<Person> page = repository.findAll(example, pageable);
```

Các thông tin thường dùng:

```java
List<Person> content = page.getContent();
int pageNumber = page.getNumber();
int pageSize = page.getSize();
long totalElements = page.getTotalElements();
int totalPages = page.getTotalPages();
boolean hasNext = page.hasNext();
```

`Page` cung cấp cả nội dung và metadata tổng số phần tử/trang. Để tính tổng, provider có thể cần thực hiện count query ngoài truy vấn lấy nội dung trang. Nếu giao diện chỉ cần biết còn trang tiếp theo, cân nhắc fluent QBE API với Slice để tránh yêu cầu tổng số bản ghi.

Một endpoint có thể nhận Pageable:

```java
@GetMapping("/people")
public Page<PersonResponse> search(
        @PageableDefault(size = 20, sort = "id") Pageable pageable,
        PersonSearchRequest request
) {
    return personSearchService.search(request, pageable);
}
```

Ở service, map request DTO sang probe và matcher, sau đó gọi `findAll(example, pageable)`. Không bind trực tiếp toàn bộ entity từ request nếu entity có field nội bộ như id, version, tenant hoặc trạng thái quản trị. Chỉ map những bộ lọc API cho phép.

Page size và sort vẫn cần giới hạn ở web/service theo chính sách API. QBE không tự bảo vệ ứng dụng khỏi page size quá lớn hoặc sort field không được phép.

## 13. Sort bằng findAll(Example, Sort)

Nếu không cần pagination nhưng cần sắp xếp:

```java
Iterable<Person> people = repository.findAll(
    example,
    Sort.by(
        Sort.Order.asc("lastName"),
        Sort.Order.asc("id")
    )
);
```

Sort dùng property Java, ví dụ `lastName`, không dùng tên cột `last_name`. Hãy giới hạn sort field theo allowlist nếu Sort đến từ HTTP request. Sort ổn định nên có một khóa duy nhất làm tiêu chí cuối.

`findAll(example, sort)` vẫn trả tất cả kết quả phù hợp; Sort không giới hạn số dòng. Nếu dữ liệu lớn, dùng Pageable hoặc fluent API có giới hạn.

## 14. Fluent QBE API với findBy()

Từ Spring Data 2.6, `QueryByExampleExecutor` có `findBy(example, queryFunction)`. API này cho phép cấu hình projection, sort, limit, Page, Slice, Window, Stream, count và exists trong một callback.

Ví dụ lấy Page dạng projection:

```java
public interface PersonSummary {
    String getFirstName();
    String getLastName();
    String getCity();
}
```

Thực thi:

```java
Page<PersonSummary> page = repository.findBy(
    example,
    query -> query
        .as(PersonSummary.class)
        .page(PageRequest.of(
            0,
            20,
            Sort.by("lastName")
        ))
);
```

`as(PersonSummary.class)` chọn kiểu kết quả projection. Cách này hữu ích khi màn hình chỉ cần vài field và không cần hydrate toàn bộ entity graph.

Có thể giới hạn kết quả:

```java
List<PersonSummary> topTen = repository.findBy(
    example,
    query -> query
        .as(PersonSummary.class)
        .sortBy(Sort.by("lastName").ascending())
        .limit(10)
        .all()
);
```

Có thể dùng Slice:

```java
Slice<Person> slice = repository.findBy(
    example,
    query -> query.slice(
        PageRequest.of(0, 50, Sort.by("id").ascending())
    )
);
```

Hoặc đếm/kiểm tra tồn tại bằng fluent query:

```java
long total = repository.findBy(example, query -> query.count());

boolean any = repository.findBy(example, query -> query.exists());
```

Đối tượng fluent query chỉ hợp lệ bên trong callback của `findBy`. Callback phải trả về kết quả terminal như Page, Slice, List, Optional, count hoặc exists; không trả chính đối tượng query để dùng sau khi callback kết thúc.

Khi đã có nhu cầu đơn giản, các method `count(example)`, `exists(example)` và `findAll(example, pageable)` trực tiếp thường dễ đọc hơn. Dùng fluent API khi cần projection, limit, sort hoặc result type linh hoạt.

## 15. Nested property path

QBE có thể cấu hình property path lồng nhau bằng dấu chấm, ví dụ `address.city`. Với entity có embedded value:

```java
@Embeddable
public class Address {

    private String city;

    protected Address() {
    }

    public String getCity() {
        return city;
    }

    public void setCity(String city) {
        this.city = city;
    }
}

@Entity
public class Person {

    @Id
    @GeneratedValue
    private Long id;

    @Embedded
    private Address address;

    // Các field và accessor khác
}
```

Tạo probe:

```java
Person probe = new Person();
Address address = new Address();
address.setCity("Da Nang");
probe.setAddress(address);

ExampleMatcher matcher = ExampleMatcher.matchingAll()
    .withIgnorePaths("id")
    .withMatcher(
        "address.city",
        property -> property.exact().ignoreCase()
    );

Example<Person> example = Example.of(probe, matcher);
```

Tên matcher là property path Java `address.city`. Đây là điều kiện trên một thuộc tính lồng đơn giản. QBE không hỗ trợ biểu thức nhóm tùy ý hoặc matching trên collection/map; với quan hệ phức tạp, hãy xác minh provider và mapping cụ thể.

## 16. Map request tìm kiếm thành probe an toàn

Trong API thực tế, nên có DTO riêng cho tiêu chí tìm kiếm:

```java
public record PersonSearchRequest(
    String firstName,
    String lastName,
    String city,
    Boolean active,
    Integer age
) {
}
```

Service tạo probe từ những field được phép:

```java
@Transactional(readOnly = true)
public Page<Person> search(
        PersonSearchRequest request,
        Pageable pageable
) {
    Person probe = new Person();

    if (request.firstName() != null
            && !request.firstName().isBlank()) {
        probe.setFirstName(request.firstName().trim());
    }

    if (request.lastName() != null
            && !request.lastName().isBlank()) {
        probe.setLastName(request.lastName().trim());
    }

    if (request.city() != null && !request.city().isBlank()) {
        probe.setCity(request.city().trim());
    }

    probe.setActive(request.active());
    probe.setAge(request.age());

    ExampleMatcher matcher = ExampleMatcher.matchingAll()
        .withIgnorePaths("id")
        .withMatcher(
            "firstName",
            property -> property.startsWith().ignoreCase()
        )
        .withMatcher(
            "lastName",
            property -> property.contains().ignoreCase()
        )
        .withMatcher(
            "city",
            property -> property.exact().ignoreCase()
        );

    Example<Person> example = Example.of(probe, matcher);

    return repository.findAll(example, pageable);
}
```

Ví dụ giả định repository có các entity field và accessor tương ứng. Trong dự án thực tế, nên validate page size/sort trước khi gọi repository, và chỉ đưa các field được API công khai vào probe.

Chuỗi rỗng không giống null. Vì QBE mặc định bỏ qua null chứ không mặc định bỏ qua mọi chuỗi blank, hãy chuẩn hóa request trước khi set probe. Nếu không, chuỗi rỗng có thể trở thành điều kiện tìm kiếm ngoài ý muốn.

Không cho client gửi trực tiếp tên property matcher tùy ý. Các property path và quy tắc matching nên do ứng dụng kiểm soát để tránh query quá tốn kém hoặc vô tình tìm theo field nội bộ.

## 17. QBE không hỗ trợ những gì?

QBE có chủ đích giữ API đơn giản. Các giới hạn quan trọng:

| Nhu cầu | QBE | Hướng thay thế |
|---|---|---|
| Field bằng giá trị | Có | QBE |
| Chuỗi exact/starts/ends/contains | Có, tùy database/provider | QBE hoặc JPQL |
| Không phân biệt hoa thường | Có | QBE, kiểm thử collation/index |
| AND giữa các field | Có mặc định | QBE |
| OR giữa các predicate ở mức cao nhất | Có với matchingAny | QBE |
| Nhóm AND/OR lồng tùy ý | Không | Specification, Criteria, Querydsl, JPQL |
| Điều kiện lớn hơn/nhỏ hơn/between | Không trực tiếp | Specification, Querydsl, JPQL |
| Collection hoặc Map matching | Không | Join query, Specification, Querydsl |
| Regex trong Spring Data JPA QBE | Không hỗ trợ | Database-specific query nếu thật sự cần |
| Aggregate/group by/having | Không phù hợp | JPQL/native SQL |
| Subquery và EXISTS phức tạp | Không phù hợp | Specification, JPQL, Querydsl |

QBE rất tiện khi điều kiện chỉ là các giá trị mẫu. Nó không phải ngôn ngữ xây dựng mọi loại biểu thức SQL.

## 18. Khi nào nên chọn Specification thay cho QBE?

Giả sử màn hình tìm kiếm cần các điều kiện:

- status thuộc một tập trạng thái.
- totalAmount nằm trong khoảng min/max.
- createdAt nằm trong khoảng ngày.
- tên khách hàng chứa một chuỗi.
- phải có ít nhất một OrderItem thỏa điều kiện.
- nhóm điều kiện theo logic `A AND (B OR C)`.

QBE không diễn đạt tốt những toán tử, join và nhóm boolean này. Spring Data JPA Specification cho phép xây dựng predicate bằng Criteria API:

```java
public static Specification<Person> cityIs(String city) {
    return (root, query, cb) ->
        city == null
            ? cb.conjunction()
            : cb.equal(root.get("city"), city);
}
```

Có thể kết hợp Specification bằng `and()` và `or()`. Querydsl cũng phù hợp khi muốn biểu thức có kiểu kiểm tra compile-time. Với truy vấn cố định và dễ đọc, JPQL `@Query` vẫn là lựa chọn tốt.

Chọn QBE khi probe tự nhiên biểu diễn bộ lọc. Chuyển sang Specification/Querydsl/JPQL khi phải viết logic mà probe không thể thể hiện.

## 19. Hiệu năng và index

QBE là cách tạo query, không phải cơ chế làm query tự động nhanh hơn. Hiệu năng phụ thuộc SQL được sinh, số field có điều kiện, kiểu string matching, index, số hàng phù hợp và kế hoạch thực thi.

Một số lưu ý:

- Exact match trên field có index thường dễ tối ưu hơn contains.
- `CONTAINING` thường tạo pattern có wildcard ở cả hai phía, nên B-tree index thông thường có thể không hỗ trợ hiệu quả.
- Ignore case có thể làm query dùng biểu thức LOWER; index thông thường có thể không được tận dụng nếu database không có functional index/collation phù hợp.
- Page cần metadata tổng số có thể phát sinh count query.
- Projection giúp giảm cột và object graph được tải.
- Không gọi `findAll(example)` trên bảng lớn nếu không có giới hạn.
- Kiểm tra SQL và execution plan trên đúng database production.

Ví dụ index cho tìm kiếm exact theo city và active:

```sql
CREATE INDEX idx_people_city_active
    ON people (city, active);
```

Đây chỉ là ví dụ. Thứ tự cột index và việc tạo index phụ thuộc workload, độ chọn lọc, database và các truy vấn khác. Không tạo index chỉ vì field xuất hiện trong probe.

## 20. Kiểm thử QBE

Nên kiểm thử các hành vi quan trọng:

1. Probe chỉ có một field: chỉ field đó được dùng làm điều kiện.
2. Probe có nhiều field: matchingAll yêu cầu tất cả điều kiện cùng đúng.
3. matchingAny: một trong các điều kiện đủ để khớp.
4. Field null mặc định bị bỏ qua.
5. withIncludeNullValues tạo điều kiện cho field null theo matcher.
6. Primitive field có giá trị mặc định vẫn có thể được đưa vào query.
7. IgnorePaths loại field kỹ thuật như id/version.
8. StringMatcher EXACT, STARTING, ENDING và CONTAINING hoạt động đúng.
9. IgnoreCase hoạt động đúng với dữ liệu và collation thực tế.
10. count/exists trả kết quả phù hợp với cùng Example.
11. findOne trả Optional.empty hoặc entity và báo lỗi khi có nhiều kết quả.
12. Page trả content, sort và metadata đúng.
13. Fluent projection chỉ trả field cần thiết.
14. Request có chuỗi blank được chuẩn hóa theo chính sách API.

Ví dụ test repository:

```java
@DataJpaTest
class PersonRepositoryQbeTest {

    @Autowired
    PersonRepository repository;

    @Test
    void searchesCountsAndChecksExistenceUsingSameExample() {
        Person first = new Person();
        first.setFirstName("An");
        first.setCity("Da Nang");
        first.setActive(true);

        Person second = new Person();
        second.setFirstName("Binh");
        second.setCity("Da Nang");
        second.setActive(true);

        Person third = new Person();
        third.setFirstName("An");
        third.setCity("Hue");
        third.setActive(false);

        repository.saveAll(List.of(first, second, third));
        repository.flush();

        Person probe = new Person();
        probe.setCity("Da Nang");
        probe.setActive(true);

        Example<Person> example = Example.of(
            probe,
            ExampleMatcher.matchingAll().withIgnorePaths("id", "age")
        );

        assertThat(repository.count(example)).isEqualTo(2);
        assertThat(repository.exists(example)).isTrue();
        assertThat(repository.findAll(example)).hasSize(2);
    }
}
```

Đây là khung test minh họa; entity cần có constructor/accessor phù hợp với dự án. Test dùng cùng Example cho ba thao tác để xác nhận predicate được tái sử dụng nhất quán.

Test phân trang có thể kiểm tra:

```java
Page<Person> page = repository.findAll(
    example,
    PageRequest.of(0, 1, Sort.by("id").ascending())
);

assertThat(page.getContent()).hasSize(1);
assertThat(page.getTotalElements()).isEqualTo(2);
assertThat(page.hasNext()).isTrue();
```

Nếu dùng database-specific collation hoặc string function, hãy bổ sung integration test trên cùng hệ quản trị với môi trường chạy thật.

## 21. Lỗi thường gặp

| Biểu hiện | Nguyên nhân | Cách xử lý |
|---|---|---|
| Không tìm thấy bản ghi dù probe chỉ có tên | Field primitive khác đang mang giá trị mặc định và được đưa vào điều kiện | Dùng wrapper hoặc ignore field |
| Kết quả rỗng khi probe có nhiều field | matchingAll mặc định yêu cầu tất cả field khớp | Kiểm tra probe và dùng matchingAny nếu nghiệp vụ là OR |
| Tìm chuỗi không phân biệt hoa thường không đúng | Chưa bật ignoreCase hoặc collation khác kỳ vọng | Cấu hình matcher rõ và kiểm thử database |
| Chuỗi rỗng trở thành điều kiện | Chỉ null mới bị bỏ qua mặc định | Trim/normalize request và không set blank |
| Tìm field NULL không ra kết quả | Null mặc định bị bỏ qua | Dùng includeNullValues có kiểm soát hoặc query riêng |
| findOne ném IncorrectResultSizeDataAccessException | Có nhiều hàng cùng khớp probe | Dùng List/Page hoặc bảo đảm điều kiện duy nhất |
| QBE không lọc được khoảng tuổi | QBE so khớp exact cho kiểu không phải chuỗi | Dùng Specification/Querydsl/JPQL |
| Không thể viết A AND (B OR C) | QBE không hỗ trợ grouped predicates tùy ý | Dùng Specification hoặc Criteria |
| Regex không hoạt động | JPA QBE không hỗ trợ regex matching | Dùng truy vấn database-specific nếu cần |
| Query chậm với CONTAINING | Wildcard hai đầu khó tận dụng B-tree index | Đo execution plan và cân nhắc search strategy |
| Page chậm do count | Page cần metadata tổng số | Dùng Slice nếu không cần total |
| Sort theo field nội bộ | Chuyển Sort request thẳng vào repository | Dùng allowlist sort ở API |

## 22. Bài tập thực hành

1. Tạo Person entity và PersonRepository kế thừa JpaRepository.
2. Tạo probe chỉ có city và xác nhận các field null bị bỏ qua.
3. Thêm active kiểu Boolean để phân biệt false với null.
4. Dùng matchingAll để kết hợp firstName và city bằng AND.
5. Dùng matchingAny để tìm theo firstName hoặc city.
6. Cấu hình firstName starts-with ignoreCase và lastName contains ignoreCase.
7. Dùng withIgnorePaths để loại id, version và createdAt.
8. Thử withIncludeNullValues và quan sát SQL IS NULL được tạo.
9. Dùng count(example) và exists(example) cho cùng một probe.
10. Dùng findOne(example) với dữ liệu duy nhất và dữ liệu trùng.
11. Phân trang bằng findAll(example, pageable), kiểm tra totalElements và sort.
12. Dùng fluent API để trả projection Page hoặc Slice.
13. Tạo embedded Address và tìm theo property path address.city.
14. Thử yêu cầu điều kiện age >= 18 và giải thích vì sao cần Specification/JPQL.
15. So sánh QBE với Specification cho một form tìm kiếm có nhiều bộ lọc tùy chọn.

## 23. Tài liệu tham khảo chính thức

- [Spring Data JPA — Query by Example](https://docs.spring.io/spring-data/jpa/reference/repositories/query-by-example.html): probe, ExampleMatcher, null handling, string matching, fluent API và các giới hạn của QBE.
- [QueryByExampleExecutor API — Spring Data Commons](https://docs.spring.io/spring-data/commons/docs/3.5.x/api/org/springframework/data/repository/query/QueryByExampleExecutor.html): chữ ký và hợp đồng findOne, findAll, count, exists, Page và fluent findBy.
- [ListQueryByExampleExecutor API — Spring Data Commons](https://docs.spring.io/spring-data/commons/docs/3.5.x/api/org/springframework/data/repository/query/ListQueryByExampleExecutor.html): biến thể trả List trong các repository hỗ trợ interface này.

**Nguyên tắc xuyên suốt:** tạo probe từ những bộ lọc được phép, dùng ExampleMatcher để xác định null/string/AND-OR, rồi tái sử dụng Example cho tìm kiếm, count, exists và pagination. QBE phù hợp với điều kiện so khớp đơn giản; khi cần range, collection, subquery hoặc nhóm AND/OR phức tạp, hãy chuyển sang Specification, Querydsl hoặc JPQL.
