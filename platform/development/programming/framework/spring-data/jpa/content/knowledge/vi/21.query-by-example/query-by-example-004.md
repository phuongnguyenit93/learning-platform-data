# matchingAll, matchingAny và tùy chỉnh theo thuộc tính

Spring Data JPA cung cấp **Query by Example (QBE)** để xây dựng truy vấn từ một entity mẫu (probe). Thay vì viết một method repository cho từng tổ hợp điều kiện tìm kiếm, ứng dụng tạo object chứa các giá trị cần tìm, cấu hình **ExampleMatcher**, rồi truyền **Example** vào repository.

Hai chiến lược kết hợp điều kiện quan trọng là:

- **matchingAll()**: tất cả thuộc tính được đưa vào probe phải khớp (logic AND).
- **matchingAny()**: chỉ cần một trong các thuộc tính được đưa vào probe khớp (logic OR).

Bạn cũng có thể tùy chỉnh cách so khớp riêng cho từng thuộc tính: chính xác, bắt đầu bằng, kết thúc bằng, chứa chuỗi, không phân biệt hoa thường, bỏ qua field hoặc biến đổi giá trị trước khi so khớp.

QBE phù hợp với màn hình tìm kiếm có các điều kiện đơn giản và tùy chọn. Khi cần biểu thức logic lồng nhau, khoảng giá trị hoặc truy vấn phức tạp, nên dùng Specification, Criteria API hoặc JPQL.

**Điều kiện của ví dụ:** các đoạn mã dùng Java 17 trở lên, Spring Boot 3.x và Spring Data JPA. Ứng dụng cần **spring-boot-starter-data-jpa**, JDBC driver, DataSource và schema phù hợp. Các đoạn mã là những phần của ứng dụng Spring Boot, không phải chương trình độc lập có thể chạy chỉ bằng **javac**.

## 1. Query by Example là gì?

QBE gồm ba thành phần:

1. **Probe**: entity mẫu chứa các giá trị cần tìm.
2. **ExampleMatcher**: quy tắc quyết định thuộc tính nào được xét và cách so khớp.
3. **Example**: kết hợp probe và matcher để truyền vào repository.

Luồng xử lý:

~~~text
Tạo entity probe
      |
      v
Cấu hình ExampleMatcher
      |
      v
Example.of(probe, matcher)
      |
      v
repository.findAll(example)
      |
      v
Spring Data tạo điều kiện truy vấn
      |
      v
Kết quả entity phù hợp
~~~

Ví dụ, nếu probe có firstName = "An" và lastName = "Nguyen", QBE có thể tạo điều kiện tương đương:

~~~sql
WHERE first_name = 'An'
  AND last_name = 'Nguyen'
~~~

Cú pháp SQL thực tế do JPA provider và database quyết định. Trong Java, bạn làm việc với thuộc tính entity, không cần tự viết tên bảng hoặc cột.

## 2. Entity và repository mẫu

Ta dùng entity Person với các thuộc tính tìm kiếm thường gặp:

~~~java
package com.example.people.domain;

import jakarta.persistence.*;

@Entity
@Table(name = "people")
public class Person {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String firstName;

    private String lastName;

    private String email;

    private Integer age;

    private Boolean active;

    protected Person() {
    }

    public Person(
            String firstName,
            String lastName,
            String email,
            Integer age,
            Boolean active) {
        this.firstName = firstName;
        this.lastName = lastName;
        this.email = email;
        this.age = age;
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

    public String getEmail() {
        return email;
    }

    public Integer getAge() {
        return age;
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

    public void setEmail(String email) {
        this.email = email;
    }

    public void setAge(Integer age) {
        this.age = age;
    }

    public void setActive(Boolean active) {
        this.active = active;
    }
}
~~~

Repository:

~~~java
package com.example.people.repository;

import com.example.people.domain.Person;
import org.springframework.data.jpa.repository.JpaRepository;

public interface PersonRepository
        extends JpaRepository<Person, Long> {
}
~~~

**JpaRepository** cung cấp các thao tác Query by Example thông qua **QueryByExampleExecutor**. Bạn không cần viết một method riêng cho từng tổ hợp firstName, lastName, email hay age.

Ví dụ dưới đây giả định các field được ánh xạ trực tiếp như trong entity. Trong ứng dụng thực tế, tên property trong matcher phải đúng với tên thuộc tính Java, kể cả khi tên cột database khác.

## 3. matchingAll(): tất cả điều kiện phải khớp

**ExampleMatcher.matchingAll()** yêu cầu mọi thuộc tính được đưa vào probe và không bị bỏ qua đều khớp. Đây là chiến lược AND.

Ví dụ tìm người có firstName bắt đầu bằng "An" và lastName chính xác là "Nguyen":

~~~java
Person probe = new Person(null, null, null, null, null);
probe.setFirstName("An");
probe.setLastName("Nguyen");

ExampleMatcher matcher = ExampleMatcher.matchingAll()
    .withMatcher(
        "firstName",
        property -> property.startsWith().ignoreCase()
    )
    .withMatcher(
        "lastName",
        property -> property.exact().ignoreCase()
    );

Example<Person> example = Example.of(probe, matcher);

Iterable<Person> people = personRepository.findAll(example);
~~~

Điều kiện logic tương đương:

~~~sql
WHERE LOWER(first_name) LIKE 'an%'
  AND LOWER(last_name) = 'nguyen'
~~~

Đây là cách diễn đạt logic để dễ hiểu; hàm SQL, ký tự escape và cú pháp cụ thể phụ thuộc provider/database.

Nếu không chỉ định matcher, **matchingAll()** là chiến lược mặc định của ExampleMatcher. **ExampleMatcher.matching()** cũng tạo matcher với chiến lược matching all.

Dùng matchingAll khi các điều kiện tìm kiếm là những ràng buộc đồng thời, ví dụ:

- Tên bắt đầu bằng một chuỗi.
- Họ khớp chính xác.
- Email chứa một từ khóa.
- Trạng thái active bằng true.

## 4. matchingAny(): chỉ cần một điều kiện khớp

**ExampleMatcher.matchingAny()** kết hợp các thuộc tính được xét bằng logic OR. Chỉ cần một điều kiện khớp thì entity có thể được đưa vào kết quả.

Ví dụ tìm người có tên chứa "an" hoặc email chính xác là "support@example.test":

~~~java
Person probe = new Person(null, null, null, null, null);
probe.setFirstName("an");
probe.setEmail("support@example.test");

ExampleMatcher matcher = ExampleMatcher.matchingAny()
    .withMatcher(
        "firstName",
        property -> property.contains().ignoreCase()
    )
    .withMatcher(
        "email",
        property -> property.exact().ignoreCase()
    );

Example<Person> example = Example.of(probe, matcher);

Iterable<Person> people = personRepository.findAll(example);
~~~

Điều kiện logic tương đương:

~~~sql
WHERE LOWER(first_name) LIKE '%an%'
   OR LOWER(email) = 'support@example.test'
~~~

Với matchingAny, một người có firstName phù hợp vẫn có thể được trả về dù email khác giá trị probe. Ngược lại, người có email phù hợp cũng được trả về dù firstName không chứa "an".

### So sánh hai chiến lược

Giả sử probe có hai điều kiện A và B:

| A khớp | B khớp | matchingAll (A AND B) | matchingAny (A OR B) |
|---|---|---|---|
| Có | Có | Có | Có |
| Có | Không | Không | Có |
| Không | Có | Không | Có |
| Không | Không | Không | Không |

Điểm cần nhớ: matchingAll/matchingAny chỉ kết hợp các thuộc tính thực sự được đưa vào tiêu chí. Thuộc tính null mặc định bị bỏ qua; vì vậy một field null không tự động trở thành điều kiện IS NULL trong cả hai chiến lược.

## 5. Tùy chỉnh cách so khớp cho từng thuộc tính

**withMatcher(propertyPath, ...)** cho phép chỉ định quy tắc riêng cho một property. Các kiểu so khớp chuỗi thường dùng:

| Matcher | Ý nghĩa | Giá trị probe "spring" |
|---|---|---|
| **exact()** | Chuỗi bằng chính xác | **spring** |
| **startsWith()** | Bắt đầu bằng | **spring data** |
| **endsWith()** | Kết thúc bằng | **data spring** |
| **contains()** | Có chứa chuỗi | **learn spring data** |
| **regex()** | Khớp biểu thức chính quy | Phụ thuộc regex |

Ví dụ:

~~~java
ExampleMatcher matcher = ExampleMatcher.matchingAll()
    .withMatcher("firstName", m -> m.startsWith())
    .withMatcher("lastName", m -> m.endsWith())
    .withMatcher("email", m -> m.exact());
~~~

Khi probe có firstName = "An", lastName = "Nguyen" và email = "an@example.test", các điều kiện được tạo theo matcher tương ứng.

Tên property truyền vào **withMatcher** là tên thuộc tính Java. Nếu entity khai báo:

~~~java
@Column(name = "first_name")
private String firstName;
~~~

thì matcher phải dùng **firstName**, không phải **first_name**.

Có thể dùng đường dẫn property lồng nhau nếu mapping và provider hỗ trợ, ví dụ **address.city**. Đường dẫn phải trùng với cấu trúc thuộc tính entity.

## 6. Tùy chỉnh matcher mặc định và ghi đè theo property

Có thể đặt một kiểu so khớp chuỗi chung cho tất cả thuộc tính String, rồi ghi đè một property cụ thể:

~~~java
ExampleMatcher matcher = ExampleMatcher.matchingAll()
    .withStringMatcher(
        ExampleMatcher.StringMatcher.CONTAINING
    )
    .withIgnoreCase()
    .withMatcher(
        "email",
        property -> property.exact()
    );
~~~

Trong ví dụ:

- Mặc định các thuộc tính chuỗi được so khớp theo kiểu chứa chuỗi.
- Các thuộc tính chuỗi được so khớp không phân biệt hoa thường.
- Riêng email dùng so khớp chính xác thay cho chứa chuỗi.

Matcher theo từng property có thể ghi đè quy tắc mặc định. Điều này giúp tạo một quy tắc chung mà vẫn kiểm soát các field cần chính xác.

Các giá trị **StringMatcher** thường gặp:

- **DEFAULT**: dùng hành vi mặc định của store/provider.
- **EXACT**: khớp chính xác.
- **STARTING**: bắt đầu bằng.
- **ENDING**: kết thúc bằng.
- **CONTAINING**: chứa chuỗi.
- **REGEX**: dùng biểu thức chính quy nếu store hỗ trợ.

Không nên dùng regex tùy tiện cho truy vấn lớn. Cách dịch regex và khả năng tận dụng index phụ thuộc database/provider.

## 7. Bật hoặc tắt ignoreCase

Mặc định, so khớp chuỗi có phân biệt hoa thường theo cấu hình mặc định của store. Có thể bật không phân biệt hoa thường cho tất cả thuộc tính String:

~~~java
ExampleMatcher matcher = ExampleMatcher.matchingAll()
    .withIgnoreCase();
~~~

Hoặc chỉ bật cho một số property:

~~~java
ExampleMatcher matcher = ExampleMatcher.matchingAll()
    .withIgnoreCase("firstName", "lastName");
~~~

Cũng có thể cấu hình ngay trong matcher của property:

~~~java
ExampleMatcher matcher = ExampleMatcher.matchingAll()
    .withMatcher(
        "email",
        property -> property.exact().ignoreCase()
    );
~~~

Dùng ignoreCase có thể khiến provider tạo biểu thức như LOWER(column). Tùy database và index, cách này có thể ảnh hưởng hiệu năng. Nếu truy vấn không phân biệt hoa thường là yêu cầu thường xuyên, hãy cân nhắc collation phù hợp hoặc functional index theo database và kiểm tra execution plan.

## 8. Bỏ qua thuộc tính bằng withIgnorePaths

Probe là entity đầy đủ, nên ngoài các field tìm kiếm có thể còn ID, thời gian tạo, thời gian cập nhật hoặc trạng thái nội bộ. Không muốn các field đó tham gia truy vấn thì dùng **withIgnorePaths**.

~~~java
Person probe = new Person(null, null, null, null, null);
probe.setFirstName("An");
probe.setActive(true);

ExampleMatcher matcher = ExampleMatcher.matchingAll()
    .withIgnorePaths("id", "createdAt", "updatedAt");

Example<Person> example = Example.of(probe, matcher);
~~~

Các property trong ignorePaths bị loại khỏi điều kiện so khớp kể cả khi chúng có giá trị khác null.

Ví dụ thực tế:

- ID được sinh tự động không nên vô tình trở thành điều kiện tìm kiếm.
- createdAt và updatedAt thường không phải tiêu chí của form tìm kiếm.
- Field audit hoặc field kỹ thuật có thể cần bỏ qua.

Tên path phải là property Java. Nếu entity không có createdAt hoặc updatedAt, không đưa chúng vào cấu hình của ứng dụng thực tế.

## 9. Null mặc định được xử lý thế nào?

Theo mặc định, QBE bỏ qua các thuộc tính null trong probe. Điều này phù hợp với form tìm kiếm tùy chọn: người dùng chỉ nhập firstName thì các field còn lại không tham gia điều kiện.

~~~java
Person probe = new Person(null, null, null, null, null);
probe.setFirstName("An");

// lastName, email, age và active đang null nên mặc định bị bỏ qua.
Example<Person> example = Example.of(probe);
~~~

Nếu cần tìm các entity có một thuộc tính bằng SQL NULL, có thể bật **withIncludeNullValues()**:

~~~java
ExampleMatcher matcher = ExampleMatcher.matchingAll()
    .withIncludeNullValues()
    .withIgnorePaths("id", "createdAt", "updatedAt");

Example<Person> example = Example.of(probe, matcher);
~~~

Khi include null values được bật, các thuộc tính null được xét như điều kiện null theo semantics của QBE/JPA. Điều này có thể khiến rất nhiều field không được điền trong probe trở thành điều kiện IS NULL. Vì vậy, phải kết hợp với ignorePaths hoặc thiết kế probe cẩn thận.

Nếu mục tiêu là “không nhập thì bỏ qua, nhập lựa chọn đặc biệt thì tìm giá trị null”, hãy biểu diễn lựa chọn đó rõ ràng trong request/criteria và tạo matcher phù hợp. Không dùng một probe rỗng cùng include-null như cách tìm kiếm thông thường.

## 10. Lưu ý với kiểu primitive

QBE phân biệt null với giá trị có thật. Kiểu wrapper như **Integer**, **Boolean** có thể là null nên phù hợp với tiêu chí tìm kiếm tùy chọn.

Ngược lại, primitive như **int** và **boolean** luôn có giá trị mặc định:

- int mới khởi tạo có giá trị **0**.
- boolean mới khởi tạo có giá trị **false**.

Các giá trị này không phải null nên có thể bị xem là điều kiện tìm kiếm ngoài ý muốn.

Ví dụ entity dùng:

~~~java
private int age;
private boolean active;
~~~

Nếu probe mới được tạo, age = 0 và active = false có thể tham gia truy vấn. Cách xử lý:

1. Dùng **Integer** và **Boolean** nếu field có thể không được cung cấp trong tiêu chí tìm kiếm.
2. Hoặc thêm field primitive vào **withIgnorePaths** khi không muốn xét.
3. Chỉ đặt giá trị primitive khi người dùng thực sự chọn tiêu chí tương ứng.

Đây là lý do entity dùng wrapper thường dễ biểu diễn probe tìm kiếm hơn với các field tùy chọn.

## 11. Biến đổi giá trị trước khi so khớp

**withTransformer(propertyPath, transformer)** cho phép chuẩn hóa giá trị probe trước khi tạo điều kiện truy vấn.

Ví dụ loại bỏ khoảng trắng thừa ở email:

~~~java
ExampleMatcher matcher = ExampleMatcher.matchingAll()
    .withMatcher(
        "email",
        property -> property.exact().ignoreCase()
    )
    .withTransformer(
        "email",
        source -> source.map(value -> value.toString().trim())
    );
~~~

Nếu probe.email là **"  AN@example.test  "**, transformer trả về giá trị đã trim trước khi matcher tạo điều kiện. Transformer không sửa entity probe gốc; nó chuẩn hóa giá trị dùng cho việc so khớp.

Có thể dùng transformer cho việc chuẩn hóa chuỗi, định dạng hoặc xử lý đầu vào đơn giản. Không đặt truy vấn database hoặc logic nghiệp vụ phức tạp trong transformer.

## 12. Dùng Example với Sort và Pageable

QBE có thể kết hợp với sắp xếp và phân trang. Đây là điểm hữu ích khi form tìm kiếm có nhiều điều kiện tùy chọn và kết quả cần hiển thị theo từng trang.

Ví dụ sắp xếp:

~~~java
Example<Person> example = Example.of(probe, matcher);

Iterable<Person> people = personRepository.findAll(
    example,
    Sort.by(
        Sort.Order.asc("lastName"),
        Sort.Order.asc("firstName"),
        Sort.Order.asc("id")
    )
);
~~~

Ví dụ phân trang:

~~~java
Pageable pageable = PageRequest.of(
    0,
    20,
    Sort.by(
        Sort.Order.asc("lastName"),
        Sort.Order.asc("id")
    )
);

Page<Person> page = personRepository.findAll(example, pageable);
~~~

Pageable dùng page index bắt đầu từ 0. Page trả metadata như totalElements và totalPages; việc tính tổng có thể cần count query.

Thêm ID làm tiêu chí sắp xếp cuối cùng giúp thứ tự ổn định khi nhiều người có cùng lastName. QBE executor cơ bản cung cấp overload findAll với Pageable trả về Page.

## 13. Các phương thức QBE có sẵn trên repository

Thông qua **QueryByExampleExecutor**, repository hỗ trợ các thao tác phổ biến:

| Phương thức | Kết quả | Mục đích |
|---|---|---|
| **findOne(example)** | Optional | Tìm tối đa một kết quả; lỗi nếu có nhiều kết quả |
| **findAll(example)** | Iterable | Lấy tất cả kết quả phù hợp |
| **findAll(example, sort)** | Iterable | Lấy kết quả có sắp xếp |
| **findAll(example, pageable)** | Page | Lấy kết quả phân trang |
| **count(example)** | long | Đếm số kết quả phù hợp |
| **exists(example)** | boolean | Kiểm tra có kết quả phù hợp |

Ví dụ:

~~~java
Example<Person> example = Example.of(probe, matcher);

Optional<Person> one = personRepository.findOne(example);

long total = personRepository.count(example);

boolean found = personRepository.exists(example);
~~~

Chỉ dùng **findOne** khi điều kiện tìm kiếm bảo đảm tối đa một kết quả, chẳng hạn email duy nhất. Nếu nhiều entity cùng khớp, phương thức có thể ném **IncorrectResultSizeDataAccessException** thông qua lớp Spring Data.

## 14. ExampleMatcher là immutable

**ExampleMatcher** là đối tượng cấu hình bất biến. Các phương thức with... trả về matcher mới thay vì sửa instance hiện có.

Nên viết theo chuỗi:

~~~java
ExampleMatcher matcher = ExampleMatcher.matchingAll()
    .withIgnorePaths("id")
    .withIgnoreCase()
    .withMatcher("firstName", property -> property.startsWith());
~~~

Nếu cấu hình từng bước, phải gán lại kết quả:

~~~java
ExampleMatcher matcher = ExampleMatcher.matchingAll();

matcher = matcher.withIgnorePaths("id");
matcher = matcher.withIgnoreCase();
~~~

Nếu gọi **matcher.withIgnoreCase()** mà bỏ qua giá trị trả về, matcher ban đầu không nhận thay đổi. Đây là lỗi dễ gặp khi xây dựng matcher bằng nhiều câu lệnh.

Probe và matcher cũng nên được tạo mới theo từng request tìm kiếm. Không chia sẻ probe mutable giữa các request đồng thời.

## 15. Giới hạn của Query by Example

QBE tiện lợi nhưng không thay thế mọi kiểu truy vấn. Các giới hạn quan trọng:

- Không hỗ trợ biểu thức logic lồng tùy ý như (A AND B) OR (C AND D) chỉ bằng matchingAll/matchingAny.
- matchingAny chỉ OR các thuộc tính được xét; không tạo nhóm OR/AND lồng nhau.
- Không hỗ trợ trực tiếp các toán tử so sánh khoảng như greater-than, less-than, between theo cách linh hoạt của Specification.
- Không phù hợp với tiêu chí collection hoặc map.
- Không phải công cụ để viết join/fetch plan tùy ý.
- Không diễn đạt tốt các phép tính, subquery, aggregate hoặc điều kiện phụ thuộc nhiều bảng.

Ví dụ, nếu cần tìm:

~~~text
(age >= 18 AND active = true)
OR
(lastName starts with "Tran" AND email contains "example")
~~~

QBE không thể biểu diễn nhóm điều kiện này chỉ bằng một ExampleMatcher. Hãy dùng Specification/Criteria API hoặc JPQL.

### Khi nào nên dùng Specification?

Specification phù hợp khi điều kiện có thể ghép động bằng AND/OR và có các toán tử so sánh:

~~~java
public static Specification<Person> ageAtLeast(int minimumAge) {
    return (root, query, cb) ->
        cb.greaterThanOrEqualTo(root.get("age"), minimumAge);
}
~~~

Có thể kết hợp nhiều Specification bằng **and()** và **or()**. Với truy vấn có logic phức tạp, đây là cách diễn đạt rõ hơn so với cố ép QBE làm công việc ngoài phạm vi.

## 16. Kiểm thử matchingAll, matchingAny và property matcher

Có thể kiểm thử repository bằng **@DataJpaTest**. Ví dụ dưới đây giả định database test và schema cho Person đã được cấu hình:

~~~java
@DataJpaTest
class PersonExampleTest {

    @Autowired
    private PersonRepository personRepository;

    @Test
    void matchingAllRequiresEveryIncludedProperty() {
        personRepository.save(
            new Person("An", "Nguyen", "an@example.test", 25, true)
        );
        personRepository.save(
            new Person("An", "Tran", "other@example.test", 30, true)
        );

        Person probe = new Person(null, null, null, null, null);
        probe.setFirstName("An");
        probe.setLastName("Nguyen");

        ExampleMatcher matcher = ExampleMatcher.matchingAll()
            .withIgnoreCase("firstName", "lastName");

        Iterable<Person> result =
            personRepository.findAll(Example.of(probe, matcher));

        assertThat(result).hasSize(1);
        assertThat(result.iterator().next().getLastName())
            .isEqualTo("Nguyen");
    }

    @Test
    void matchingAnyAcceptsEitherIncludedProperty() {
        personRepository.save(
            new Person("An", "Nguyen", "an@example.test", 25, true)
        );
        personRepository.save(
            new Person("Binh", "Tran", "support@example.test", 30, true)
        );

        Person probe = new Person(null, null, null, null, null);
        probe.setFirstName("An");
        probe.setEmail("support@example.test");

        ExampleMatcher matcher = ExampleMatcher.matchingAny()
            .withMatcher("firstName", property -> property.exact())
            .withMatcher("email", property -> property.exact());

        Iterable<Person> result =
            personRepository.findAll(Example.of(probe, matcher));

        assertThat(result).hasSize(2);
    }
}
~~~

Trong test thứ hai, entity thứ nhất khớp firstName và entity thứ hai khớp email. Vì matcher là matchingAny, cả hai đều được trả về.

Khi kiểm thử, nên có dữ liệu khớp một điều kiện, khớp tất cả điều kiện và không khớp điều kiện nào. Cũng nên kiểm tra case-insensitive, ignorePaths, null handling và primitive default nếu entity có các field primitive.

## 17. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Kết quả quá ít với matchingAll | Tất cả field được đưa vào probe đều phải khớp | Kiểm tra field khác null và chuyển sang matchingAny nếu đúng nghiệp vụ |
| Kết quả quá rộng với matchingAny | Chỉ cần một field khớp | Chỉ đưa tiêu chí thực sự cần vào probe và chọn matchingAll khi cần AND |
| Field không nhập vẫn tham gia query | Dùng primitive có giá trị mặc định | Dùng wrapper hoặc ignorePaths |
| Không tìm được chuỗi khác hoa thường | Chưa bật ignoreCase | Dùng withIgnoreCase hoặc matcher riêng |
| Tìm kiếm chứa chuỗi nhưng chỉ khớp chính xác | Chưa đặt StringMatcher phù hợp | Dùng contains/CONTAINING |
| ID vô tình trở thành điều kiện | Probe có ID khác null | Dùng withIgnorePaths("id") |
| Tìm giá trị null không hoạt động | Null bị bỏ qua theo mặc định | Dùng withIncludeNullValues và kiểm soát các field khác |
| Matcher cấu hình không có tác dụng | Bỏ qua object mới trả về từ with... | Gán lại matcher hoặc chain cấu hình |
| QBE không diễn đạt được điều kiện | Cần range, nested boolean hoặc join phức tạp | Dùng Specification, Criteria hoặc JPQL |
| Trang kết quả không ổn định | Sort không có tie-breaker duy nhất | Thêm ID vào cuối Sort |

## 18. Checklist sử dụng QBE

- [ ] Tạo probe mới cho từng request tìm kiếm.
- [ ] Chỉ gán các field người dùng thực sự nhập.
- [ ] Dùng matchingAll khi mọi điều kiện phải khớp.
- [ ] Dùng matchingAny khi chỉ cần một điều kiện khớp.
- [ ] Dùng withMatcher để cấu hình chính xác, startsWith, endsWith hoặc contains theo property.
- [ ] Dùng withIgnoreCase cho field cần tìm không phân biệt hoa thường.
- [ ] Dùng withIgnorePaths cho ID, audit field hoặc thuộc tính không phải tiêu chí.
- [ ] Hiểu null mặc định bị bỏ qua và withIncludeNullValues thay đổi hành vi.
- [ ] Dùng wrapper thay cho primitive khi field tìm kiếm là tùy chọn.
- [ ] Gán lại kết quả của các phương thức with... vì ExampleMatcher bất biến.
- [ ] Kết hợp Sort/Pageable khi cần sắp xếp hoặc phân trang.
- [ ] Dùng Specification/JPQL khi cần range, join hoặc logic boolean lồng nhau.
- [ ] Kiểm thử SQL và kết quả với nhiều tổ hợp probe thực tế.

## 19. Kết luận

**matchingAll()** kết hợp các thuộc tính được xét bằng AND; **matchingAny()** kết hợp chúng bằng OR. **withMatcher()** cho phép quy định cách so khớp riêng cho từng property, còn **withIgnoreCase()**, **withIgnorePaths()**, **withIncludeNullValues()** và **withTransformer()** giúp kiểm soát hành vi tìm kiếm chi tiết hơn.

QBE phù hợp với form tìm kiếm có các tiêu chí đơn giản và tùy chọn. Hãy tạo probe rõ ràng, tránh field primitive mặc định vô tình tham gia truy vấn, và kiểm soát null. Khi cần điều kiện khoảng, join hoặc nhóm AND/OR lồng nhau, chuyển sang Specification hoặc JPQL để truy vấn dễ hiểu và chính xác.