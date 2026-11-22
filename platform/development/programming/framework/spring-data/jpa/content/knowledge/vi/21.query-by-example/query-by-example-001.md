# Mô hình probe, Example và ExampleMatcher trong Spring Data JPA

Query by Example (QBE) cho phép tìm entity bằng cách tạo một đối tượng mẫu (probe), điền những thuộc tính cần tìm rồi mô tả cách so khớp bằng ExampleMatcher. Spring Data JPA chuyển Example thành điều kiện truy vấn, nhờ đó ứng dụng có thể xây dựng bộ lọc tìm kiếm động mà không cần viết một derived query hoặc một câu JPQL riêng cho từng tổ hợp trường.

QBE phù hợp với form tìm kiếm có nhiều trường tùy chọn và các điều kiện tương đối đơn giản. Nó đặc biệt hữu ích khi người dùng chỉ nhập một vài thuộc tính, ví dụ tên bắt đầu bằng một chuỗi, email khớp chính xác và tuổi bằng một giá trị cụ thể. QBE có giới hạn: không biểu diễn được mọi nhóm điều kiện OR/AND lồng nhau, không so khớp collection/map và không thay thế Specification hoặc Querydsl cho truy vấn phức tạp.

Bài học này giải thích ba thành phần Probe, Example và ExampleMatcher, cách bỏ qua null, xử lý primitive, cấu hình matcher toàn cục/theo thuộc tính, dùng fluent API để sắp xếp, phân trang, cuộn và stream, cùng cách kiểm thử và lựa chọn QBE trong ứng dụng thực tế.

## 1. Query by Example gồm những thành phần nào?

QBE có ba thành phần:

1. **Probe:** đối tượng domain được điền các giá trị muốn tìm.
2. **ExampleMatcher:** quy định cách so khớp, ví dụ AND hay OR, so khớp chuỗi chính xác hay chứa chuỗi, bỏ qua thuộc tính nào và có phân biệt hoa thường hay không.
3. **Example:** đóng gói probe cùng matcher để truyền cho repository.

Luồng tổng quát:

~~~mermaid
flowchart TD
    A[Tạo probe từ entity] --> B[Điền các thuộc tính cần tìm]
    B --> C[Tạo ExampleMatcher]
    C --> D[Đóng gói thành Example]
    D --> E[Repository nhận Example]
    E --> F[Spring Data JPA tạo predicate]
    F --> G[Database trả entity phù hợp]
~~~

Ví dụ ý tưởng: muốn tìm người có firstname bắt đầu bằng "An" và lastname bằng "Nguyen", ta tạo một Person probe, đặt hai thuộc tính đó rồi dùng matcher cấu hình STARTING cho firstname và EXACT cho lastname.

QBE không yêu cầu khai báo một method repository riêng cho từng tổ hợp điều kiện. Cùng một repository method có thể nhận nhiều Example khác nhau.

## 2. Tạo entity làm Probe

Probe thường là một instance của entity mà repository quản lý. Những thuộc tính được gán giá trị sẽ trở thành điều kiện tìm kiếm theo matcher; những thuộc tính null thường được bỏ qua theo mặc định.

Ví dụ entity Person:

~~~java
package com.example.people;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "people")
public class Person {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(length = 100)
    private String firstname;

    @Column(length = 100)
    private String lastname;

    @Column(length = 200)
    private String email;

    private Integer age;

    private Boolean active;

    protected Person() {
    }

    public Person(
            String firstname,
            String lastname,
            String email,
            Integer age,
            Boolean active) {
        this.firstname = firstname;
        this.lastname = lastname;
        this.email = email;
        this.age = age;
        this.active = active;
    }

    public Long getId() {
        return id;
    }

    public String getFirstname() {
        return firstname;
    }

    public void setFirstname(String firstname) {
        this.firstname = firstname;
    }

    public String getLastname() {
        return lastname;
    }

    public void setLastname(String lastname) {
        this.lastname = lastname;
    }

    public String getEmail() {
        return email;
    }

    public void setEmail(String email) {
        this.email = email;
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
~~~

Đây là entity hoàn chỉnh dùng cho các ví dụ tiếp theo. Probe không cần được persist; nó chỉ là đối tượng Java mang giá trị tìm kiếm. Constructor không tham số được bảo vệ để JPA có thể tạo entity, còn setter giúp ví dụ tạo probe dễ đọc.

Với QBE, hãy chỉ điền các thuộc tính người dùng thực sự muốn dùng làm tiêu chí. Không nên khởi tạo probe bằng một constructor tự gán giá trị mặc định cho mọi trường nếu các giá trị đó không phải tiêu chí tìm kiếm.

## 3. Khai báo repository hỗ trợ QBE

Spring Data JPA cung cấp QueryByExampleExecutor. JpaRepository đã kế thừa khả năng QBE, vì vậy repository thông thường có thể dùng trực tiếp các method nhận Example.

~~~java
package com.example.people;

import org.springframework.data.jpa.repository.JpaRepository;

public interface PersonRepository
        extends JpaRepository<Person, Long> {
}
~~~

Các method QBE thường dùng gồm:

| Method | Kết quả |
|---|---|
| findOne(example) | Optional chứa tối đa một entity |
| findAll(example) | Iterable các entity phù hợp |
| findAll(example, sort) | Iterable được sắp xếp |
| findAll(example, pageable) | Page entity |
| count(example) | Số entity phù hợp |
| exists(example) | Có ít nhất một entity phù hợp hay không |
| findBy(example, queryFunction) | Truy vấn qua fluent API |

Nếu findOne(example) khớp nhiều entity, Spring Data không tự chọn một dòng bất kỳ; nó báo lỗi kích thước kết quả không đúng. Chỉ dùng findOne khi điều kiện có thể xác định tối đa một entity.

## 4. Tạo Example đơn giản

Cách ngắn nhất là tạo probe rồi gọi Example.of():

~~~java
Person probe = new Person();
probe.setFirstname("An");

Example<Person> example = Example.of(probe);

List<Person> people = repository.findAll(example);
~~~

Với matcher mặc định:

- Các thuộc tính có giá trị null được bỏ qua.
- Các thuộc tính có giá trị được so khớp bằng phép bằng.
- Chuỗi được so khớp chính xác và phân biệt hoa thường theo mặc định.
- Các thuộc tính không được bỏ qua sẽ được kết hợp theo AND.

Vì vậy, probe có firstname = "An" và các thuộc tính khác null có nghĩa tìm Person có firstname bằng "An".

Khi cần thay đổi cách so khớp, truyền matcher vào Example.of():

~~~java
ExampleMatcher matcher = ExampleMatcher.matchingAll()
        .withIgnoreCase()
        .withStringMatcher(ExampleMatcher.StringMatcher.CONTAINING);

Example<Person> example = Example.of(probe, matcher);
~~~

Ví dụ này áp dụng tìm chuỗi con và không phân biệt hoa thường cho các thuộc tính chuỗi được xét, trừ khi một property matcher cụ thể ghi đè cấu hình chung.

## 5. matchingAll() và matchingAny()

ExampleMatcher có hai cách kết hợp điều kiện:

- matchingAll(): mọi tiêu chí có giá trị đều phải khớp, tương đương logic AND.
- matchingAny(): chỉ cần một tiêu chí có giá trị khớp, tương đương logic OR.

Ví dụ probe có firstname = "An" và lastname = "Nguyen".

~~~java
Person probe = new Person();
probe.setFirstname("An");
probe.setLastname("Nguyen");

ExampleMatcher allMatcher = ExampleMatcher.matchingAll();
ExampleMatcher anyMatcher = ExampleMatcher.matchingAny();

List<Person> allMatches =
        repository.findAll(Example.of(probe, allMatcher));

List<Person> anyMatches =
        repository.findAll(Example.of(probe, anyMatcher));
~~~

Ý nghĩa:

| Matcher | Điều kiện |
|---|---|
| matchingAll() | firstname = 'An' AND lastname = 'Nguyen' |
| matchingAny() | firstname = 'An' OR lastname = 'Nguyen' |

matchingAny() chỉ tạo OR giữa các thuộc tính có tiêu chí. Nó không tạo được những nhóm logic tùy ý như:

~~~sql
firstname = 'An'
OR (firstname = 'Binh' AND lastname = 'Nguyen')
~~~

Nếu cần nhóm điều kiện lồng nhau, dùng Specification, Criteria API hoặc Querydsl.

## 6. Bỏ qua thuộc tính null và includeNullValues()

Mặc định, ExampleMatcher bỏ qua các thuộc tính null trong probe. Đây là lý do QBE phù hợp với form tìm kiếm có trường tùy chọn.

Ví dụ:

~~~java
Person probe = new Person();
probe.setLastname("Tran");
// firstname, email, age và active vẫn null.

Example<Person> example = Example.of(probe);
List<Person> people = repository.findAll(example);
~~~

Điều kiện chỉ lọc theo lastname. Các trường null không tạo điều kiện IS NULL.

Nếu muốn tìm entity có một thuộc tính null, có thể dùng matcher includeNullValues():

~~~java
Person probe = new Person();
probe.setEmail(null);

ExampleMatcher matcher = ExampleMatcher.matchingAll()
        .withIncludeNullValues()
        .withIgnorePaths("id", "firstname", "lastname", "age", "active");

Example<Person> example = Example.of(probe, matcher);
List<Person> people = repository.findAll(example);
~~~

Matcher này đưa các thuộc tính null không bị ignore vào tiêu chí tìm kiếm; trong ví dụ, email phải là null. Các thuộc tính khác được bỏ qua tường minh để không vô tình tạo thêm nhiều điều kiện IS NULL.

Cần cẩn thận với includeNullValues(): nếu probe có nhiều thuộc tính null, matcher có thể yêu cầu tất cả các thuộc tính đó phải null. Với entity nhiều trường, hãy dùng ignorePaths hoặc tạo probe chuyên biệt để biểu đạt chính xác điều kiện cần tìm.

## 7. Primitive và giá trị mặc định có thể tạo điều kiện ngoài ý muốn

Primitive Java như boolean, int, long không thể có giá trị null. Khi tạo probe mới, chúng mặc định là false hoặc 0. QBE nhìn thấy đó là giá trị thực, nên có thể dùng chúng làm tiêu chí tìm kiếm.

Ví dụ nếu entity khai báo:

~~~java
private boolean active;
private int age;
~~~

Một probe mới sẽ có active = false và age = 0. Hai giá trị này có thể trở thành điều kiện ngoài ý muốn.

Có hai cách xử lý:

1. Dùng wrapper Boolean, Integer để biểu diễn trạng thái chưa được nhập bằng null.
2. Dùng withIgnorePaths("active", "age") khi không muốn các trường đó tham gia tìm kiếm.

Trong entity Person của bài này, active là Boolean và age là Integer, do đó probe mới có thể để hai trường null khi không cần lọc. Đây là lý do wrapper thường tiện hơn cho mô hình tìm kiếm.

Đừng nhầm null trong probe với giá trị false hoặc 0. Null nghĩa là không cung cấp tiêu chí theo mặc định; false và 0 là các giá trị cụ thể.

## 8. withIgnorePaths(): bỏ qua thuộc tính có giá trị

withIgnorePaths() bỏ qua các thuộc tính ngay cả khi probe đang có giá trị.

~~~java
Person probe = new Person();
probe.setFirstname("An");
probe.setLastname("Nguyen");
probe.setAge(0);

ExampleMatcher matcher = ExampleMatcher.matchingAll()
        .withIgnorePaths("id", "age");

Example<Person> example = Example.of(probe, matcher);
~~~

Trong ví dụ, age = 0 không tham gia điều kiện tìm kiếm. Điều này hữu ích khi probe được tạo từ form có các giá trị mặc định hoặc khi một số thuộc tính của entity không thuộc phạm vi tìm kiếm.

Đối với ID, version và các trường kỹ thuật, hãy quyết định rõ chúng có phải tiêu chí nghiệp vụ hay không. Để tránh vô tình lọc theo trường không mong muốn, có thể ignorePaths tường minh.

Tên property path dùng tên thuộc tính Java, không phải tên cột database. Ví dụ ignore "firstname", không phải tên cột SQL nếu cột được ánh xạ bằng @Column(name = ...).

## 9. StringMatcher: cách so khớp chuỗi

ExampleMatcher.StringMatcher quy định cách so khớp mặc định cho các thuộc tính chuỗi.

| Giá trị | Ý nghĩa | Điều kiện minh họa |
|---|---|---|
| EXACT | Khớp chính xác | firstname = 'An' |
| STARTING | Bắt đầu bằng chuỗi | firstname LIKE 'An%' |
| ENDING | Kết thúc bằng chuỗi | firstname LIKE '%An' |
| CONTAINING | Chứa chuỗi | firstname LIKE '%An%' |
| DEFAULT | Dùng mặc định của matcher/store | Theo cấu hình matcher |

Ví dụ tìm firstname bắt đầu bằng "An":

~~~java
Person probe = new Person();
probe.setFirstname("An");

ExampleMatcher matcher = ExampleMatcher.matchingAll()
        .withStringMatcher(ExampleMatcher.StringMatcher.STARTING);

List<Person> people =
        repository.findAll(Example.of(probe, matcher));
~~~

Ví dụ tìm chuỗi con:

~~~java
ExampleMatcher matcher = ExampleMatcher.matchingAll()
        .withStringMatcher(ExampleMatcher.StringMatcher.CONTAINING);
~~~

StringMatcher áp dụng cho thuộc tính chuỗi được xét. Nếu muốn mỗi trường có cách so khớp khác nhau, dùng withMatcher() theo property path.

REGEX có thể xuất hiện trong API matcher hoặc tài liệu của một số store, nhưng không nên giả định regex được hỗ trợ giống nhau bởi mọi Spring Data module và database. Với Spring Data JPA, hãy kiểm tra phiên bản/provider và dùng query riêng nếu cần biểu thức chính quy thực sự.

## 10. IgnoreCase: tìm kiếm không phân biệt hoa thường

Có thể bật ignore case cho mọi thuộc tính chuỗi:

~~~java
ExampleMatcher matcher = ExampleMatcher.matchingAll()
        .withIgnoreCase();
~~~

Hoặc chỉ bật cho một số thuộc tính:

~~~java
ExampleMatcher matcher = ExampleMatcher.matchingAll()
        .withIgnoreCase("firstname", "email");
~~~

Ví dụ:

~~~java
Person probe = new Person();
probe.setFirstname("an");

ExampleMatcher matcher = ExampleMatcher.matchingAll()
        .withIgnoreCase("firstname")
        .withStringMatcher(ExampleMatcher.StringMatcher.STARTING);

List<Person> people =
        repository.findAll(Example.of(probe, matcher));
~~~

Kết quả có thể khớp "An", "AN" hoặc "anna" theo quy tắc so sánh không phân biệt hoa thường được provider/database thực hiện.

IgnoreCase thường khiến provider tạo biểu thức tương tự LOWER(column) và LOWER(parameter), nhưng SQL cụ thể phụ thuộc Hibernate và database. Collation, locale và dấu tiếng Việt có thể ảnh hưởng kết quả; không nên mặc định rằng ignore case cũng loại bỏ dấu. Nếu cần tìm không phân biệt dấu, phải thiết kế chuẩn hóa riêng.

## 11. Matcher riêng cho từng thuộc tính

withMatcher() cho phép cấu hình một property path riêng. Đây là cách thường dùng khi firstname cần prefix, lastname cần exact và email cần ignore case.

~~~java
Person probe = new Person();
probe.setFirstname("An");
probe.setLastname("Nguyen");
probe.setEmail("EXAMPLE.COM");

ExampleMatcher matcher = ExampleMatcher.matchingAll()
        .withMatcher("firstname",
                property -> property.startsWith().ignoreCase())
        .withMatcher("lastname",
                property -> property.exact().ignoreCase())
        .withMatcher("email",
                property -> property.contains().ignoreCase());

Example<Person> example = Example.of(probe, matcher);
List<Person> people = repository.findAll(example);
~~~

Trong ví dụ:

- firstname bắt đầu bằng "An", không phân biệt hoa thường.
- lastname khớp chính xác với "Nguyen", không phân biệt hoa thường.
- email chứa "EXAMPLE.COM", không phân biệt hoa thường.

Property matcher ghi đè cấu hình string matcher toàn cục cho property đó. Những thuộc tính không được cấu hình riêng tiếp tục dùng matcher mặc định hoặc cấu hình chung.

Tên path phải trỏ tới thuộc tính hợp lệ của probe. Nếu entity có thuộc tính nhúng, có thể dùng path lồng nhau theo mapping, ví dụ address.city. Cần kiểm thử đường dẫn thực tế với mapping và provider của ứng dụng.

## 12. PropertyValueTransformer: chuẩn hóa giá trị probe

withTransformer() cho phép biến đổi giá trị của một thuộc tính trước khi tạo predicate. Ví dụ trim khoảng trắng đầu/cuối hoặc chuẩn hóa chữ hoa/thường.

~~~java
Person probe = new Person();
probe.setFirstname("  An  ");

ExampleMatcher matcher = ExampleMatcher.matchingAll()
        .withMatcher("firstname",
                property -> property.startsWith().ignoreCase())
        .withTransformer("firstname",
                value -> value
                        .map(String.class::cast)
                        .map(String::trim)
                        .map(trimmed -> (Object) trimmed));

Example<Person> example = Example.of(probe, matcher);
~~~

Transformer nhận Optional<Object>:

- Optional có giá trị khi probe property có giá trị.
- Có thể trả Optional.empty() để bỏ giá trị sau biến đổi.
- Có thể trả Optional chứa giá trị đã chuẩn hóa.
- Transformer chỉ ảnh hưởng cách tạo truy vấn; nó không thay đổi entity được lưu trong database.

Không dùng transformer để thực hiện logic nghiệp vụ phức tạp hoặc truy cập dịch vụ ngoài. Hãy giữ biến đổi đơn giản, xác định và dễ kiểm thử.

## 13. ExampleMatcher là immutable

ExampleMatcher được thiết kế bất biến. Các phương thức with... trả về một matcher mới, vì vậy cần gán kết quả trở lại biến nếu muốn giữ cấu hình.

Đúng:

~~~java
ExampleMatcher matcher = ExampleMatcher.matchingAll();
matcher = matcher.withIgnoreCase();
matcher = matcher.withIgnorePaths("id");
~~~

Cũng có thể nối chuỗi:

~~~java
ExampleMatcher matcher = ExampleMatcher.matchingAll()
        .withIgnoreCase()
        .withIgnorePaths("id", "active")
        .withStringMatcher(ExampleMatcher.StringMatcher.CONTAINING);
~~~

Không nên gọi withIgnoreCase() rồi bỏ qua giá trị trả về:

~~~java
ExampleMatcher matcher = ExampleMatcher.matchingAll();
matcher.withIgnoreCase(); // Không thay đổi matcher ban đầu.
~~~

Vì matcher immutable, có thể tái sử dụng cấu hình nền để tạo các matcher mới. Tuy nhiên, probe là object Java có thể thay đổi; không sửa probe sau khi tạo Example nếu muốn giữ điều kiện truy vấn ổn định và dễ hiểu.

## 14. Nested property và giới hạn của QBE

QBE có thể xử lý một số thuộc tính lồng nhau, ví dụ thuộc tính của embedded object hoặc association đơn. Tuy nhiên, QBE không phải công cụ biểu diễn mọi loại join và nhóm predicate.

Các giới hạn quan trọng:

- Không hỗ trợ so khớp collection-valued hoặc map-valued property như một tiêu chí QBE tổng quát.
- Không biểu diễn được nhóm điều kiện tùy ý với AND/OR lồng nhau.
- Không phù hợp với truy vấn cần điều kiện phức tạp trên nhiều collection.
- Không có cú pháp để diễn tả mọi phép so sánh lớn hơn/nhỏ hơn trên kiểu số hoặc ngày giờ bằng probe đơn thuần.
- String matching chủ yếu dành cho exact, starts, ends và contains; không giả định hỗ trợ mọi toán tử LIKE hoặc regex.
- QBE chỉ tạo predicate dựa trên giá trị probe và matcher; nó không phải ngôn ngữ truy vấn đầy đủ như JPQL.

Ví dụ QBE phù hợp:

~~~text
firstname bắt đầu bằng "An"
AND lastname khớp "Nguyen"
AND email chứa "example.com"
~~~

Ví dụ vượt quá khả năng diễn đạt tự nhiên của QBE:

~~~text
(age >= 18 AND active = true)
OR (age < 18 AND email IS NOT NULL)
~~~

Với truy vấn thứ hai, dùng Specification/Criteria API hoặc Querydsl để tạo predicate theo điều kiện nghiệp vụ.

## 15. findOne, findAll, count và exists

Repository hỗ trợ nhiều kiểu thao tác với Example:

~~~java
Person probe = new Person();
probe.setEmail("an@example.com");

Example<Person> example = Example.of(probe);

Optional<Person> one = repository.findOne(example);

List<Person> all = repository.findAll(example);

long count = repository.count(example);

boolean exists = repository.exists(example);
~~~

Ý nghĩa:

- findOne() trả Optional nếu có tối đa một kết quả; nếu có nhiều kết quả, nó báo lỗi kích thước kết quả.
- findAll() trả tất cả entity phù hợp.
- count() đếm entity phù hợp.
- exists() kiểm tra có ít nhất một entity phù hợp.

Không dùng findOne() cho một thuộc tính không duy nhất nếu nghiệp vụ cho phép nhiều kết quả. Dùng findAll() hoặc thêm điều kiện thực sự duy nhất.

Nếu chỉ cần biết có dữ liệu, exists() rõ ràng hơn việc tải toàn bộ danh sách rồi kiểm tra isEmpty().

## 16. Kết hợp QBE với Sort và Pageable

Có thể truyền Sort hoặc Pageable trực tiếp:

~~~java
Person probe = new Person();
probe.setLastname("Nguyen");

Example<Person> example = Example.of(probe);

List<Person> sorted = repository.findAll(
        example,
        Sort.by(Sort.Direction.ASC, "firstname")
);

Page<Person> page = repository.findAll(
        example,
        PageRequest.of(
                0,
                20,
                Sort.by(Sort.Direction.ASC, "firstname")
        )
);
~~~

Sort dùng tên thuộc tính Java, không phải tên cột vật lý. Nếu cần thứ tự ổn định khi phân trang, hãy thêm thuộc tính duy nhất làm tie-breaker, ví dụ id.

Page cung cấp content, totalElements và totalPages. Tùy query, Spring Data có thể chạy thêm count query. Nếu giao diện chỉ cần biết còn dữ liệu tiếp theo hay không, cân nhắc Slice hoặc fluent query slice để tránh tính tổng số.

## 17. Fluent Query API với Example

findBy(example, queryFunction) cho phép tinh chỉnh cách lấy kết quả mà không cần tạo thêm method repository. Fluent query có thể cấu hình sort, giới hạn, projection, page, slice và các cách đọc dữ liệu khác.

Ví dụ lấy trang đã sắp xếp:

~~~java
Page<Person> page = repository.findBy(
        example,
        query -> query
                .sortBy(Sort.by("lastname").ascending())
                .page(PageRequest.of(0, 20))
);
~~~

Ví dụ lấy một kết quả đầu tiên theo thứ tự:

~~~java
Optional<Person> first = repository.findBy(
        example,
        query -> query
                .sortBy(Sort.by("id").ascending())
                .first()
);
~~~

Fluent query callback phải trả về kết quả ngay trong lời gọi findBy(). Không lưu FetchableFluentQuery để sử dụng sau khi callback kết thúc.

### Projection qua fluent query

Nếu chỉ cần một số trường, có thể dùng projection thay vì tải toàn bộ entity. Ví dụ interface projection:

~~~java
public interface PersonNameView {
    String getFirstname();
    String getLastname();
}
~~~

~~~java
List<PersonNameView> names = repository.findBy(
        example,
        query -> query.as(PersonNameView.class).all()
);
~~~

Projection phải tương thích với thuộc tính và khả năng projection của Spring Data JPA đang dùng. Với báo cáo phức tạp, DTO query bằng JPQL có thể dễ kiểm soát hơn.

## 18. Cuộn dữ liệu bằng Scroll API

Với phiên bản Spring Data hỗ trợ Scroll API và fluent query của store module, có thể dùng Example cùng scroll để đọc dữ liệu theo từng Window thay vì tải toàn bộ kết quả.

Ví dụ cuộn theo offset:

~~~java
Window<Person> window = repository.findBy(
        example,
        query -> query
                .sortBy(Sort.by("id").ascending())
                .limit(100)
                .scroll(ScrollPosition.offset())
);
~~~

Window chứa tối đa 100 phần tử theo cấu hình trên. Nếu còn dữ liệu, có thể dùng vị trí cuối của window làm điểm bắt đầu cho lần tiếp theo:

~~~java
if (!window.isEmpty() && window.hasNext()) {
    ScrollPosition nextPosition =
            window.positionAt(window.size() - 1);

    Window<Person> nextWindow = repository.findBy(
            example,
            query -> query
                    .sortBy(Sort.by("id").ascending())
                    .limit(100)
                    .scroll(nextPosition)
    );
}
~~~

Một số điểm cần nhớ:

- Dùng thứ tự sắp xếp ổn định; thêm ID duy nhất làm tie-breaker.
- Offset scrolling có thể tốn kém khi offset rất lớn vì database vẫn phải đi qua các dòng trước đó.
- Keyset scrolling có thể hiệu quả hơn với tập dữ liệu lớn nếu sort và điều kiện phù hợp.
- Kiểu dữ liệu và khả năng scroll phụ thuộc phiên bản Spring Data, store module và query shape.
- Kiểm tra API thực tế của phiên bản dự án trước khi dùng; nếu QBE fluent query không hỗ trợ kiểu scroll cần thiết, dùng repository query hoặc phương án phân trang khác.

Scroll API phù hợp với batch processing, export hoặc xử lý dữ liệu nhiều hơn mức nên tải một lần vào bộ nhớ. Nó không phải thay thế cho pagination giao diện ở mọi trường hợp.

## 19. Stream kết quả QBE

Fluent query cũng có thể trả Stream:

~~~java
@Transactional(readOnly = true)
public void exportPeople(Example<Person> example) {
    try (Stream<Person> people = repository.findBy(
            example,
            query -> query.stream()
    )) {
        people.forEach(person ->
                System.out.println(person.getFirstname()));
    }
}
~~~

Các import liên quan:

~~~java
import java.util.stream.Stream;
import org.springframework.transaction.annotation.Transactional;
~~~

Stream có thể giữ tài nguyên database/cursor mở trong lúc duyệt, do đó:

- Đóng stream bằng try-with-resources.
- Giữ transaction mở trong suốt thời gian đọc.
- Không trả Stream ra khỏi service khi transaction đã kết thúc.
- Không giả định stream luôn tải từng dòng theo kiểu streaming thật; driver, provider và fetch size ảnh hưởng hành vi.
- Nếu cần giới hạn bộ nhớ, kiểm tra cấu hình fetch size và SQL thực tế.

Không nên dùng repository.findAll(example).stream() cho tập dữ liệu rất lớn vì findAll(example) đã tải toàn bộ kết quả trước khi tạo Stream trong bộ nhớ.

## 20. Xây dựng bộ lọc tìm kiếm từ request

QBE thường được dùng cho form tìm kiếm có nhiều trường tùy chọn. Có thể nhận DTO rồi ánh xạ sang probe:

~~~java
public record PersonSearchRequest(
        String firstname,
        String lastname,
        String email
) {
}
~~~

Service:

~~~java
@Service
public class PersonSearchService {

    private final PersonRepository repository;

    public PersonSearchService(PersonRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public List<Person> search(PersonSearchRequest request) {
        Person probe = new Person();
        probe.setFirstname(request.firstname());
        probe.setLastname(request.lastname());
        probe.setEmail(request.email());

        ExampleMatcher matcher = ExampleMatcher.matchingAll()
                .withIgnorePaths("id", "age", "active")
                .withIgnoreCase("firstname", "lastname", "email")
                .withMatcher("firstname",
                        property -> property.startsWith())
                .withMatcher("lastname",
                        property -> property.contains())
                .withMatcher("email",
                        property -> property.exact());

        return repository.findAll(Example.of(probe, matcher));
    }
}
~~~

DTO giới hạn những trường client được phép tìm kiếm. Không nên bind trực tiếp request vào entity probe nếu entity có các trường nội bộ như role, status, tenantId hoặc audit metadata mà client không được phép điều khiển.

Nếu cần chuẩn hóa blank thành null, thực hiện rõ ở tầng service hoặc DTO validation. Không tự động coi chuỗi rỗng, chuỗi chỉ có khoảng trắng và null là một nếu hợp đồng API chưa quy định như vậy.

## 21. Khi nào chọn QBE, Specification hay Querydsl?

| Tiêu chí | Query by Example | Specification/Criteria | Querydsl |
|---|---|---|---|
| Cách tạo điều kiện | Probe + matcher | Predicate bằng code | Predicate có API fluent/type-safe |
| Trường tùy chọn | Rất thuận tiện | Linh hoạt | Linh hoạt |
| AND/OR đơn giản | Có matchingAll/Any | Có | Có |
| Nhóm AND/OR lồng nhau | Hạn chế | Có | Có |
| So sánh >, <, between | Không phù hợp với probe cơ bản | Có | Có |
| Collection/exists phức tạp | Hạn chế | Có | Có |
| Độ dễ đọc với form tìm kiếm đơn giản | Cao | Trung bình | Trung bình |
| Phù hợp query phức tạp | Thấp | Cao | Cao |

Chọn QBE khi bộ lọc chủ yếu là equality và string matching, các trường đều tùy chọn và không cần nhóm predicate phức tạp.

Chọn Specification khi cần ghép predicate động, so sánh số/ngày, between, join hoặc điều kiện lồng nhau mà vẫn muốn dùng API Spring Data JPA.

Chọn Querydsl khi dự án đã dùng Querydsl và cần truy vấn type-safe với cấu trúc phong phú.

## 22. Kiểm thử QBE với @DataJpaTest

Ví dụ test sử dụng entity và repository đã khai báo ở trên:

~~~java
package com.example.people;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.data.domain.Example;
import org.springframework.data.domain.ExampleMatcher;

@DataJpaTest
class PersonRepositoryQbeTest {

    @Autowired
    private PersonRepository repository;

    @Test
    void matchesFirstnamePrefixIgnoringCase() {
        repository.save(new Person(
                "An", "Nguyen", "an@example.com", 25, true));
        repository.save(new Person(
                "Anna", "Tran", "anna@example.com", 30, true));
        repository.save(new Person(
                "Binh", "Nguyen", "binh@example.com", 28, true));

        Person probe = new Person();
        probe.setFirstname("an");

        ExampleMatcher matcher = ExampleMatcher.matchingAll()
                .withMatcher("firstname",
                        property -> property.startsWith().ignoreCase());

        List<Person> result =
                repository.findAll(Example.of(probe, matcher));

        assertThat(result)
                .extracting(Person::getFirstname)
                .containsExactlyInAnyOrder("An", "Anna");
    }

    @Test
    void ignoresNullProbePropertiesByDefault() {
        repository.save(new Person(
                "An", "Nguyen", "an@example.com", 25, true));
        repository.save(new Person(
                "Binh", "Nguyen", "binh@example.com", 28, true));
        repository.save(new Person(
                "Lan", "Tran", "lan@example.com", 24, false));

        Person probe = new Person();
        probe.setLastname("Nguyen");

        List<Person> result =
                repository.findAll(Example.of(probe));

        assertThat(result).hasSize(2);
        assertThat(result)
                .allMatch(person -> "Nguyen".equals(person.getLastname()));
    }

    @Test
    void matchingAnyUsesOrBetweenPopulatedProperties() {
        repository.save(new Person(
                "An", "Tran", "an@example.com", 25, true));
        repository.save(new Person(
                "Binh", "Nguyen", "binh@example.com", 28, true));
        repository.save(new Person(
                "Lan", "Le", "lan@example.com", 24, false));

        Person probe = new Person();
        probe.setFirstname("An");
        probe.setLastname("Nguyen");

        ExampleMatcher matcher = ExampleMatcher.matchingAny();
        List<Person> result =
                repository.findAll(Example.of(probe, matcher));

        assertThat(result).hasSize(2);
    }
}
~~~

Các test xác nhận prefix không phân biệt hoa thường, null được bỏ qua mặc định và matchingAny kết hợp OR. @DataJpaTest thường chạy transaction cho từng test và rollback sau khi test kết thúc.

Nên bổ sung test cho includeNullValues, ignorePaths, primitive default, property transformer và các nested property mà ứng dụng thực sự dùng. Nếu kết quả phụ thuộc collation, function hoặc hành vi database cụ thể, hãy chạy integration test trên cùng hệ quản trị với production.

## 23. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Probe mới không trả kết quả mong muốn | Primitive false/0 vô tình thành tiêu chí | Dùng wrapper hoặc ignorePaths |
| Trường null không được lọc IS NULL | Null bị bỏ qua theo mặc định | Dùng withIncludeNullValues và ignorePaths rõ ràng |
| Kết quả quá hẹp | matchingAll kết hợp nhiều tiêu chí bằng AND | Dùng matchingAny nếu nghiệp vụ yêu cầu OR đơn giản |
| Kết quả quá rộng | matchingAny chỉ cần một tiêu chí khớp | Dùng matchingAll hoặc giới hạn probe |
| Tìm "An" không khớp "Anna" | StringMatcher mặc định là exact | Dùng STARTING hoặc CONTAINING |
| IgnoreCase không bỏ dấu | IgnoreCase chỉ xử lý hoa/thường | Thiết kế chuẩn hóa dấu riêng nếu cần |
| withIgnoreCase không có tác dụng | Bỏ qua matcher mới được trả về | Gán lại hoặc nối chuỗi matcher |
| Transformer không được áp dụng | Sai property path hoặc trả Optional không phù hợp | Kiểm tra path và kiểu Optional<Object> |
| QBE không lọc collection | Collection/map không được hỗ trợ như probe criterion tổng quát | Dùng Specification/Querydsl |
| Không biểu diễn được nhóm điều kiện | QBE chỉ hỗ trợ matchingAll/Any đơn giản | Dùng Specification hoặc Querydsl |
| findOne báo lỗi nhiều kết quả | Probe không xác định duy nhất một entity | Dùng findAll hoặc thêm điều kiện duy nhất |
| Stream làm giữ kết nối lâu | Stream chưa đóng hoặc transaction kết thúc quá sớm | Dùng try-with-resources trong transaction |
| Scroll lặp hoặc bỏ sót dữ liệu | Sort không ổn định hoặc position không được cập nhật đúng | Dùng sort có khóa duy nhất và lấy position cuối Window |

## 24. Nguyên tắc thiết kế thực tế

- Tạo probe chỉ với các thuộc tính người dùng được phép tìm kiếm.
- Dùng wrapper cho thuộc tính có thể chưa được nhập.
- Dùng matchingAll cho form tìm kiếm thông thường; matchingAny chỉ khi OR giữa các trường là đúng nghiệp vụ.
- Để null bị bỏ qua theo mặc định; chỉ includeNullValues khi thật sự cần tìm các cột null.
- Cấu hình StringMatcher theo từng thuộc tính khi các trường có yêu cầu khác nhau.
- Dùng ignorePaths cho ID, trạng thái kỹ thuật hoặc giá trị mặc định không phải tiêu chí.
- Giữ ExampleMatcher bất biến và không sửa probe sau khi tạo Example.
- Dùng Page/Slice cho giao diện và Scroll/Stream cho xử lý dữ liệu lớn khi phiên bản/provider hỗ trợ.
- Đóng Stream và giữ transaction trong suốt quá trình đọc.
- Dùng Specification hoặc Querydsl khi cần nhóm predicate, range, join collection hoặc điều kiện phức tạp.
- Kiểm thử hành vi null, primitive, case, string matching và database thực tế.

## 25. Checklist tự đánh giá

- [ ] Giải thích được Probe, Example và ExampleMatcher.
- [ ] Tạo Example từ entity probe bằng Example.of().
- [ ] Dùng repository kế thừa JpaRepository để gọi QBE.
- [ ] Phân biệt matchingAll() và matchingAny().
- [ ] Hiểu null bị bỏ qua mặc định.
- [ ] Dùng withIncludeNullValues() để tìm thuộc tính null.
- [ ] Nhận diện vấn đề primitive false/0 trong probe.
- [ ] Dùng withIgnorePaths() để bỏ qua thuộc tính.
- [ ] Cấu hình EXACT, STARTING, ENDING và CONTAINING.
- [ ] Bật IgnoreCase toàn cục hoặc theo property.
- [ ] Dùng withMatcher() cho từng thuộc tính.
- [ ] Dùng withTransformer() để chuẩn hóa giá trị probe.
- [ ] Hiểu ExampleMatcher immutable.
- [ ] Biết giới hạn với collection, map và nhóm predicate phức tạp.
- [ ] Dùng findOne, findAll, count và exists đúng cardinality.
- [ ] Kết hợp Example với Sort, Pageable và fluent query.
- [ ] Biết đóng Stream và dùng transaction khi đọc dữ liệu lớn.
- [ ] Chọn QBE, Specification hoặc Querydsl theo độ phức tạp.
- [ ] Viết test cho null, OR/AND, string matcher và các trường hợp biên.

## 26. Kết luận

Probe là entity mẫu, Example đóng gói probe với matcher, còn ExampleMatcher định nghĩa cách kết hợp và so khớp thuộc tính. Spring Data JPA dùng ba thành phần này để tạo truy vấn động từ các giá trị được cung cấp mà không cần viết một method riêng cho từng tổ hợp bộ lọc.

QBE phù hợp với tìm kiếm đơn giản theo equality và chuỗi, đặc biệt khi nhiều trường có thể bỏ trống. Hãy chú ý null, primitive mặc định, AND/OR, ignorePaths và cấu hình matcher theo thuộc tính. Khi cần range, join collection hoặc nhóm điều kiện lồng nhau, chuyển sang Specification hoặc Querydsl. Với tập kết quả lớn, dùng fluent query, scroll hoặc stream theo khả năng phiên bản, luôn giữ thứ tự ổn định và quản lý transaction/tài nguyên đúng cách.
