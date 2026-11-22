# Giới hạn thuộc tính được phép lọc bằng QuerydslBinderCustomizer

## Mục tiêu

Khi repository tích hợp Querydsl được export bằng Spring Data REST, client có thể truyền điều kiện lọc qua query parameter trên URL. Ví dụ GET /people?firstName=An yêu cầu tìm các Person có firstName phù hợp.

Nếu không giới hạn binding, nhiều thuộc tính persistent có thể trở thành khóa lọc mà client được phép gửi. Điều này đặc biệt đáng chú ý với các thuộc tính nội bộ hoặc thuộc tính bị ẩn khỏi JSON bằng @JsonIgnore: quy tắc serialization của Jackson không phải là danh sách cho phép filter của Querydsl.

QuerydslBinderCustomizer cho phép xác định chính xác thuộc tính nào được phép lọc và cách mỗi giá trị được chuyển thành Querydsl predicate. Với API công khai hoặc dữ liệu nhạy cảm, nên dùng allow-list bằng excludeUnlistedProperties(true) kết hợp including(...), thay vì chỉ loại trừ một vài field.

## 1. Querydsl filtering trong Spring Data REST

Querydsl là thư viện tạo truy vấn có kiểu dữ liệu an toàn thông qua các biểu thức Predicate. Spring Data cung cấp QuerydslPredicateExecutor<T> để repository thực thi predicate:

~~~java
public interface PersonRepository
        extends JpaRepository<Person, Long>,
                QuerydslPredicateExecutor<Person> {
}
~~~

QuerydslPredicateExecutor cung cấp các thao tác như:

- findAll(Predicate): tìm các entity thỏa điều kiện.
- findAll(Predicate, Pageable): tìm theo điều kiện và phân trang.
- count(Predicate): đếm số entity phù hợp.
- exists(Predicate): kiểm tra có entity phù hợp hay không.

Khi repository được Spring Data REST export, Querydsl có thể được dùng để lọc collection resource bằng query parameter. Ví dụ:

~~~http
GET /people?firstName=An&lastName=Nguyen
Accept: application/hal+json
~~~

Các parameter được ánh xạ thành predicate tương đương với điều kiện trên thuộc tính của entity. Repository thực thi predicate và Spring Data REST trả collection representation theo cấu hình hiện tại.

Querydsl filtering cần có hỗ trợ Querydsl phù hợp với store và các Q-type được tạo bởi annotation processing. Với Spring Data JPA, Q-type thường có tên như QPerson và được sinh từ entity Person.

## 2. QuerydslBindings và quy tắc mặc định

QuerydslBindings là nơi cấu hình các binding từ request parameter sang Querydsl expression. Có thể cấu hình theo một property cụ thể hoặc theo kiểu Java.

Các binding mặc định phổ biến:

- Giá trị đơn trên thuộc tính đơn giản thường được so sánh bằng eq.
- Giá trị đơn trên thuộc tính collection có thể được ánh xạ thành contains.
- Nhiều giá trị cho một thuộc tính đơn giản có thể được ánh xạ thành in.

Nếu không thay đổi cấu hình, excludeUnlistedProperties mặc định là false. Điều này có nghĩa các thuộc tính chưa được cấu hình binding riêng vẫn có thể dùng binding mặc định theo kiểu dữ liệu.

Vì vậy, chỉ gọi excluding(root.password) sẽ loại trừ field password nhưng vẫn để các thuộc tính khác tiếp tục dùng binding mặc định. Cách này phù hợp với deny-list nhỏ, nhưng không tạo ra một danh sách cho phép rõ ràng.

## 3. Allow-list: chỉ mở các thuộc tính được chọn

Để chỉ cho phép một tập thuộc tính được lọc:

1. Gọi bindings.excludeUnlistedProperties(true).
2. Gọi bindings.including(...) với các Querydsl path được phép.
3. Chỉ định binding riêng cho các path được mở nếu cần thay đổi cách so khớp.

Ví dụ entity:

~~~java
@Entity
public class Person {

    @Id
    @GeneratedValue
    private Long id;

    private String firstName;
    private String lastName;
    private String city;

    private String passwordHash;
    private String internalNote;
}
~~~

Repository dùng QuerydslBinderCustomizer:

~~~java
@RepositoryRestResource(path = "people")
public interface PersonRepository
        extends JpaRepository<Person, Long>,
                QuerydslPredicateExecutor<Person>,
                QuerydslBinderCustomizer<QPerson> {

    @Override
    default void customize(
            QuerydslBindings bindings,
            QPerson person) {

        bindings.excludeUnlistedProperties(true);

        bindings.including(
            person.firstName,
            person.lastName,
            person.city
        );

        bindings.bind(person.firstName)
            .first((path, value) -> path.containsIgnoreCase(value));

        bindings.bind(person.lastName)
            .first((path, value) -> path.containsIgnoreCase(value));

        bindings.bind(person.city)
            .first((path, value) -> path.equalsIgnoreCase(value));
    }
}
~~~

Trong ví dụ này:

- Client có thể lọc theo firstName, lastName và city.
- Các thuộc tính khác không được liệt kê sẽ bị loại khỏi quá trình binding.
- firstName và lastName dùng tìm kiếm chứa chuỗi, không phân biệt chữ hoa/chữ thường.
- city dùng so sánh bằng, không phân biệt chữ hoa/chữ thường.

Các request hợp lệ có thể là:

~~~http
GET /people?firstName=an
GET /people?lastName=nguyen&city=Hanoi
~~~

Request dùng field không nằm trong allow-list, ví dụ passwordHash hoặc internalNote, sẽ không tạo binding cho các thuộc tính đó. Hành vi HTTP cụ thể với parameter không hợp lệ phụ thuộc phiên bản và lớp xử lý request; không thiết kế client dựa trên giả định rằng mọi parameter không được phép đều phải trả cùng một status code. Điều cần bảo đảm là thuộc tính bị loại không tham gia predicate.

## 4. Deny-list: loại trừ một số thuộc tính

Nếu API nội bộ có yêu cầu cho phép hầu hết field và chỉ cần loại bỏ một số field, có thể dùng excluding(...):

~~~java
@RepositoryRestResource(path = "people")
public interface PersonRepository
        extends JpaRepository<Person, Long>,
                QuerydslPredicateExecutor<Person>,
                QuerydslBinderCustomizer<QPerson> {

    @Override
    default void customize(
            QuerydslBindings bindings,
            QPerson person) {

        bindings.excluding(
            person.passwordHash,
            person.internalNote
        );
    }
}
~~~

Cách này ngăn hai thuộc tính đã chỉ định được dùng làm filter key. Các thuộc tính còn lại vẫn có thể nhận binding mặc định.

| Cấu hình | Hành vi | Khi nên dùng |
|---|---|---|
| Mặc định, không exclude | Các thuộc tính đủ điều kiện dùng binding mặc định | Chỉ khi đã đánh giá phạm vi field được phép |
| excluding(path...) | Loại một số field cụ thể | API nội bộ có deny-list ổn định |
| excludeUnlistedProperties(true) + including(path...) | Chỉ cho phép field được liệt kê | API công khai, dữ liệu nhạy cảm hoặc cần kiểm soát chặt |

Với dữ liệu quan trọng, allow-list thường dễ kiểm soát hơn vì một thuộc tính mới được thêm vào entity sẽ không tự động trở thành filter key.

## 5. Binding theo từng thuộc tính và theo kiểu dữ liệu

Có hai cách phổ biến để thay đổi cách Querydsl diễn giải giá trị.

### 5.1. Binding theo path cụ thể

Dùng bindings.bind(root.property) khi một field cần cách lọc riêng:

~~~java
bindings.bind(person.firstName)
    .first((path, value) -> path.containsIgnoreCase(value));

bindings.bind(person.age)
    .first((path, value) -> path.goe(value));
~~~

Ví dụ:

- firstName=an dùng contains-ignore-case.
- age=18 có thể được định nghĩa thành điều kiện age >= 18.

first(...) nhận một giá trị; nếu client gửi nhiều giá trị cho cùng parameter, binding này dùng giá trị đầu tiên. Nếu nghiệp vụ cần xử lý toàn bộ giá trị, dùng all(...) với multi-value binding và xây dựng predicate phù hợp.

### 5.2. Binding theo kiểu dữ liệu

Có thể áp dụng một quy tắc chung cho mọi thuộc tính cùng kiểu:

~~~java
bindings.bind(String.class)
    .first((StringPath path, String value) ->
        path.containsIgnoreCase(value));
~~~

Binding theo kiểu giúp giảm code khi nhiều thuộc tính String có cùng quy tắc. Tuy nhiên, nếu đang dùng allow-list nghiêm ngặt, cần cân nhắc kỹ binding kiểu toàn cục: nó có thể mở cách xử lý chung cho nhiều path cùng kiểu. Để giữ phạm vi rõ ràng, ưu tiên khai báo binding theo path và chỉ liệt kê các path được phép.

## 6. Nested property và quan hệ

Querydsl path có thể trỏ đến thuộc tính lồng nhau. Ví dụ Person có địa chỉ:

~~~java
@Embeddable
public class Address {
    private String city;
    private String district;
}
~~~

~~~java
@Entity
public class Person {
    @Id
    private Long id;

    @Embedded
    private Address address;
}
~~~

Q-type có thể biểu diễn path lồng nhau, ví dụ person.address.city. Nếu chỉ cho phép lọc theo thành phố:

~~~java
@Override
default void customize(
        QuerydslBindings bindings,
        QPerson person) {

    bindings.excludeUnlistedProperties(true);
    bindings.including(person.address.city);

    bindings.bind(person.address.city)
        .first((path, value) -> path.equalsIgnoreCase(value));
}
~~~

Không nên mở toàn bộ object lồng nhau nếu client chỉ cần một field con. Có thể loại trừ path ở cấp cha để loại cả các path con; ví dụ loại address sẽ loại cả address.city và address.district. Nếu dùng allow-list, chỉ đưa đúng nested path cần thiết vào including(...).

## 7. Dùng alias cho tên filter công khai

QuerydslBindings còn hỗ trợ alias cho path. Alias giúp API không phải công bố trực tiếp tên property Java:

~~~java
bindings.bind(person.firstName)
    .as("name")
    .first((path, value) -> path.containsIgnoreCase(value));
~~~

Client có thể dùng tên name theo alias đã cấu hình:

~~~http
GET /people?name=An
~~~

Khi dùng alias, cần thống nhất tên parameter trong tài liệu API và kiểm thử rằng tên property gốc không vô tình còn được mở theo một binding khác. Alias là tên công khai của filter; nó không thay đổi tên field trong entity hoặc schema database.

## 8. QuerydslBinderCustomizer được áp dụng ở đâu?

Có thể triển khai QuerydslBinderCustomizer<QPerson> trực tiếp trên repository interface. Spring Data nhận customizer này khi xây dựng binding cho repository và dùng nó thay cho các binding mặc định tương ứng.

Cấu trúc thường dùng:

~~~java
@RepositoryRestResource(path = "people")
public interface PersonRepository
        extends JpaRepository<Person, Long>,
                QuerydslPredicateExecutor<Person>,
                QuerydslBinderCustomizer<QPerson> {

    @Override
    default void customize(
            QuerydslBindings bindings,
            QPerson root) {
        // allow-list và binding rules
    }
}
~~~

Một customizer cũng có thể được chỉ định cho tham số @QuerydslPredicate(bindings = ...) trong Controller Spring MVC tự viết. Trường hợp đó customizer được áp dụng cho predicate của handler tương ứng. Với filter tích hợp vào repository, đặt customizer trên chính repository giúp quy tắc đi cùng repository thay vì phụ thuộc từng Controller.

Nếu ứng dụng có nhiều repository, không giả định một allow-list trên Person sẽ tự động áp dụng cho Order hoặc các domain type khác. Hãy định nghĩa và áp dụng chính sách cho từng repository có Querydsl filtering. Có thể dùng QuerydslBinderCustomizerDefaults để chia sẻ quy tắc chung, nhưng allow-list theo domain type vẫn cần được xác định rõ.

## 9. Lưu ý bảo mật: CVE-2026-41837

Ngày 09/06/2026, Spring công bố advisory CVE-2026-41837 về tích hợp Querydsl của Spring Data REST. Advisory nêu rằng Querydsl integration chấp nhận các persistent property path làm filter key từ request parameter và không xem xét các tùy chỉnh Jackson trước khi chuyển chúng cho Querydsl.

Các phiên bản Spring Data REST bị ảnh hưởng được liệt kê trong advisory:

| Nhánh | Phiên bản bị ảnh hưởng |
|---|---|
| 5.0 | 5.0.0 đến 5.0.5 |
| 4.5 | 4.5.0 đến 4.5.11 |
| 4.4 | 4.4.0 đến 4.4.14 |
| 4.3 | 4.3.0 đến 4.3.16 |
| 3.7 | 3.7.19 và các bản trước đó |

Các bản sửa được advisory công bố:

| Bản sửa | Tình trạng phát hành trong advisory |
|---|---|
| 5.0.6 | OSS |
| 5.0.5.1 | Enterprise Support Only |
| 4.5.12 | OSS |
| 4.5.11.1 | Enterprise Support Only |
| 4.4.15 | Enterprise Support Only |
| 4.3.17 | Enterprise Support Only |
| 3.7.20 | Enterprise Support Only |

Ưu tiên nâng cấp lên bản đã sửa tương ứng với nhánh đang dùng. Nếu chưa thể nâng cấp, advisory hướng dẫn mitigation bằng cách triển khai QuerydslBinderCustomizer trên mỗi repository bị ảnh hưởng và gọi:

~~~java
bindings.excludeUnlistedProperties(true);
~~~

sau đó khai báo allow-list các property path thực sự được phép lọc bằng bindings.including(...).

Ví dụ mitigation:

~~~java
@Override
default void customize(
        QuerydslBindings bindings,
        QPerson person) {

    bindings.excludeUnlistedProperties(true);

    bindings.including(
        person.firstName,
        person.lastName,
        person.city
    );
}
~~~

Không dựa vào @JsonIgnore, projection hoặc việc ẩn field khỏi response để bảo vệ filter API. Những cơ chế đó kiểm soát representation; allow-list Querydsl mới kiểm soát các path được phép dùng làm query parameter. Cũng không chỉ thêm excluding(password) nếu yêu cầu là đóng mọi filter path chưa được duyệt.

## 10. Kiểm thử allow-list

Cần kiểm tra cả filter được phép và filter bị chặn. Ví dụ dưới đây là khung kiểm thử tích hợp; cần chuẩn bị fixture, cấu hình repository export và điều chỉnh status theo phiên bản ứng dụng:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class PersonQuerydslBindingTests {

    @Autowired
    MockMvc mvc;

    @Test
    void allowsFilteringByFirstName() throws Exception {
        mvc.perform(get("/people")
                .param("firstName", "An")
                .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk());
    }

    @Test
    void allowsFilteringByCity() throws Exception {
        mvc.perform(get("/people")
                .param("city", "Hanoi")
                .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk());
    }

    @Test
    void doesNotBindPasswordHash() throws Exception {
        mvc.perform(get("/people")
                .param("passwordHash", "secret-value")
                .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk());
        // Also assert that the result set is not filtered by passwordHash.
    }

    @Test
    void doesNotBindInternalNote() throws Exception {
        mvc.perform(get("/people")
                .param("internalNote", "confidential")
                .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk());
        // Also assert that the result set is not filtered by internalNote.
    }
}
~~~

Đối với parameter bị cấm, chỉ kiểm tra HTTP status là chưa đủ vì framework có thể bỏ qua parameter không được bind mà vẫn trả 200. Hãy chuẩn bị dữ liệu phân biệt và kiểm tra nội dung/tập kết quả để xác nhận filter bị cấm không tác động predicate.

Nên có các kiểm thử sau:

- Mỗi path trong allow-list đều tạo predicate và lọc đúng dữ liệu.
- Một path không được liệt kê không làm thay đổi tập kết quả.
- Field nhạy cảm hoặc bị ẩn khỏi JSON không thể dùng làm filter key.
- Nested path chỉ hoạt động khi được mở rõ ràng.
- Alias hoạt động theo tên công khai và không làm lộ path gốc ngoài dự định.
- Các quy tắc binding được áp dụng trên từng repository có Querydsl filtering.

## 11. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể gặp | Cách xử lý |
|---|---|---|
| Field không nằm trong allow-list vẫn lọc được | Chưa bật excludeUnlistedProperties(true) | Bật chế độ loại thuộc tính chưa liệt kê |
| Chỉ loại password nhưng field nội bộ khác vẫn lọc được | Dùng deny-list đơn lẻ | Chuyển sang allow-list cho API cần kiểm soát chặt |
| Field hợp lệ không lọc được | Quên gọi including(path) hoặc Q-type không đúng | Kiểm tra path trong customizer |
| String field lọc theo equals thay vì contains | Đang dùng binding mặc định | Định nghĩa bindings.bind(path).first(...) |
| Nhiều giá trị chỉ lấy giá trị đầu tiên | Dùng first(...) | Dùng all(...) nếu cần xử lý nhiều giá trị |
| Nested field vẫn bị mở rộng quá rộng | Mở cả object cha hoặc dùng binding kiểu toàn cục | Chỉ allow-list nested path cần thiết |
| @JsonIgnore nhưng vẫn có thể lọc field | Jackson không điều khiển Querydsl filter binding | Dùng QuerydslBinderCustomizer và nâng cấp bản đã sửa CVE |
| Một repository đã an toàn nhưng repository khác chưa | Customizer chỉ gắn với một domain type | Áp dụng allow-list trên từng repository có Querydsl |

## 12. Checklist giới hạn thuộc tính được phép lọc

- Kiểm tra repository có dùng QuerydslPredicateExecutor và Querydsl web filtering hay không.
- Liệt kê các filter path thực sự cần cho client.
- Bật excludeUnlistedProperties(true) khi cần allow-list.
- Dùng including(...) cho từng path được duyệt.
- Ưu tiên binding theo path cụ thể cho field được mở.
- Chỉ dùng excluding(...) khi chủ đích là deny-list và đã đánh giá toàn bộ field còn lại.
- Kiểm tra nested property, collection và alias.
- Không dùng @JsonIgnore thay cho filter authorization.
- Kiểm tra phiên bản Spring Data REST và nâng cấp bản đã sửa CVE-2026-41837.
- Áp dụng customizer cho từng repository có Querydsl filtering.
- Kiểm thử cả filter hợp lệ lẫn filter không được phép bằng cách so sánh tập kết quả.

## Kết luận

QuerydslBinderCustomizer kiểm soát cách request parameter được chuyển thành predicate và là điểm cấu hình quan trọng để giới hạn thuộc tính được phép lọc. excluding(...) tạo deny-list; excludeUnlistedProperties(true) kết hợp including(...) tạo allow-list rõ ràng. Với API cần bảo vệ, chỉ mở các path nghiệp vụ thực sự cần thiết và kiểm thử rằng field ngoài danh sách không ảnh hưởng kết quả. Đặc biệt, CVE-2026-41837 xác nhận rằng field bị Jackson ẩn vẫn có thể xuất hiện như filter key trên các phiên bản bị ảnh hưởng; hãy nâng cấp lên bản đã sửa và áp dụng allow-list cho từng repository.

## Tài liệu tham khảo

- Spring Security Advisory – CVE-2026-41837, affected versions and mitigation: https://spring.io/security/cve-2026-41837/
- Spring Data Commons – QuerydslBindings API (including, excluding, excludeUnlistedProperties): https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/querydsl/binding/QuerydslBindings.html
- Spring Data JPA – Querydsl extension and Querydsl web support: https://docs.spring.io/spring-data/jpa/reference/data-commons/repositories/core-extensions.html
- Spring Data REST – Repository resources and collection query behavior: https://docs.spring.io/spring-data/rest/reference/repository-resources.html
