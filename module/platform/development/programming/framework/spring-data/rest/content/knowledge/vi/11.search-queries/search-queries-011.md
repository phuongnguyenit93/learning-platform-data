# QuerydslPredicateExecutor và tùy chỉnh binding khi phiên bản, kho dữ liệu hỗ trợ

## 1. Querydsl trong Spring Data

Querydsl là thư viện Java giúp xây dựng truy vấn có kiểu dữ liệu an toàn từ các biểu thức. Thay vì ghép chuỗi query hoặc tạo một finder method cho từng tổ hợp bộ lọc, ứng dụng có thể kết hợp điều kiện thành một Predicate.

Các lớp Q-type được sinh từ domain model mô tả thuộc tính và kiểu dữ liệu tương ứng. Ví dụ QPerson.firstName là một StringPath, còn QPerson.age là một NumberPath. Compiler và IDE có thể kiểm tra tên thuộc tính cũng như operation được gọi trên từng kiểu path.

Spring Data cung cấp **QuerydslPredicateExecutor<T>** để repository thực thi Predicate. Khi phiên bản Spring Data và store module có hỗ trợ, ứng dụng có thể lọc, đếm hoặc kiểm tra sự tồn tại của dữ liệu bằng predicate mà không phải khai báo method riêng cho mọi tổ hợp điều kiện.

Cần phân biệt ba phần:

- **Querydsl:** xây dựng biểu thức truy vấn có kiểu.
- **QuerydslPredicateExecutor:** hợp đồng repository để thực thi Predicate.
- **Querydsl web binding:** chuyển query parameter HTTP thành Predicate; có thể tùy chỉnh quy tắc chuyển đổi.

Chỉ thêm Querydsl vào classpath chưa đủ. Store module phải có implementation tương ứng, Q-type phải được sinh đúng và web binding phải được cấu hình hoặc được Spring Data REST tích hợp trong phiên bản đang dùng.

## 2. QuerydslPredicateExecutor cung cấp những gì?

Các thao tác phổ biến của interface gồm:

~~~~java
public interface QuerydslPredicateExecutor<T> {

    Optional<T> findOne(Predicate predicate);

    Iterable<T> findAll(Predicate predicate);

    Iterable<T> findAll(Predicate predicate, Sort sort);

    Page<T> findAll(Predicate predicate, Pageable pageable);

    long count(Predicate predicate);

    boolean exists(Predicate predicate);
}
~~~~

| Method | Công dụng |
|---|---|
| findOne(predicate) | Tìm một kết quả phù hợp; có thể báo lỗi nếu có nhiều kết quả trong trường hợp implementation yêu cầu duy nhất |
| findAll(predicate) | Lấy các kết quả phù hợp |
| findAll(predicate, sort) | Lấy kết quả phù hợp và sắp xếp |
| findAll(predicate, pageable) | Lấy một trang kết quả phù hợp |
| count(predicate) | Đếm số bản ghi phù hợp |
| exists(predicate) | Kiểm tra có bản ghi phù hợp hay không |

Predicate là điều kiện truy vấn, không phải dữ liệu đầu vào cần lưu. Ví dụ:

~~~~java
QPerson person = QPerson.person;

Predicate predicate = person.active.isTrue()
        .and(person.firstName.containsIgnoreCase("an"));

Page<Person> result = repository.findAll(
        predicate,
        PageRequest.of(0, 20)
);
~~~~

Điều kiện trên chọn người đang hoạt động và có firstName chứa chuỗi “an”, không phân biệt hoa thường. Q-type giúp các expression giữ đúng kiểu dữ liệu.

## 3. Điều kiện hỗ trợ theo phiên bản và store

Khả năng dùng Querydsl phụ thuộc release train và module lưu trữ. Trước khi thiết kế API, xác nhận:

1. Phiên bản Spring Data đang dùng còn cung cấp integration Querydsl phù hợp.
2. Store module có implementation cho QuerydslPredicateExecutor.
3. Phiên bản Querydsl tương thích với Spring Data, Spring Boot và namespace persistence.
4. Annotation processor đã sinh Q-type cho entity hoặc document.
5. Repository được tạo thành bean và thực thi predicate được với store thật.

Spring Data JPA có tích hợp Querydsl. Những module lưu trữ khác có thể hỗ trợ khác nhau hoặc không hỗ trợ ở phiên bản đang dùng. Không suy ra rằng mọi Spring Data repository đều có thể thêm QuerydslPredicateExecutor.

### Dependency và Q-type generation

Với Spring Data JPA, dự án thường cần Querydsl JPA module và annotation processor để sinh các lớp Q-type. Cấu trúc dependency Maven có thể tương tự:

~~~~xml
<dependency>
    <groupId>com.querydsl</groupId>
    <artifactId>querydsl-jpa</artifactId>
</dependency>

<dependency>
    <groupId>com.querydsl</groupId>
    <artifactId>querydsl-apt</artifactId>
    <scope>provided</scope>
</dependency>
~~~~

Đây là khung minh họa, không phải cấu hình dùng nguyên xi cho mọi dự án. Với Querydsl dùng Jakarta Persistence, artifact/classifier và annotation processor phải tương ứng với jakarta.persistence; dự án cũ dùng javax.persistence cần cấu hình namespace cũ. Hãy dùng dependency management của Spring Boot hoặc BOM tương ứng để chọn phiên bản tương thích.

Sau khi cấu hình annotation processor, build sinh các lớp dạng:

~~~~text
target/generated-sources/annotations/
    com/example/domain/QPerson.java
~~~~

Q-type là mã sinh tự động, không sửa trực tiếp. Khi thêm hoặc đổi thuộc tính domain, chạy lại build để cập nhật Q-type. Nếu IDE không tìm thấy QPerson, kiểm tra annotation processor, generated-sources directory, package và namespace persistence.

## 4. Khai báo repository

Một repository JPA có thể kết hợp JpaRepository, QuerydslPredicateExecutor và QuerydslBinderCustomizer:

~~~~java
@RepositoryRestResource(path = "people")
public interface PersonRepository
        extends JpaRepository<Person, Long>,
                QuerydslPredicateExecutor<Person>,
                QuerydslBinderCustomizer<QPerson> {

    @Override
    default void customize(
            QuerydslBindings bindings,
            QPerson root) {
        // Khai báo quy tắc binding.
    }
}
~~~~

Ba interface có trách nhiệm riêng:

- **JpaRepository<Person, Long>** cung cấp các thao tác repository theo JPA.
- **QuerydslPredicateExecutor<Person>** cho phép thực thi Predicate trên Person.
- **QuerydslBinderCustomizer<QPerson>** cho phép định nghĩa cách query parameter được bind thành predicate.

Nếu API chỉ cần đọc, hãy chọn repository contract tối thiểu phù hợp với store. Kế thừa JpaRepository cũng mang theo các thao tác ghi; cần giới hạn REST exposure và authorization nếu không muốn công bố chúng.

## 5. Query parameter thành Predicate

Khi Querydsl web support được tích hợp, client có thể gửi thuộc tính cần lọc dưới dạng query parameter:

~~~~http
GET /people?firstName=An&active=true
Accept: application/hal+json
~~~~

Luồng xử lý khái quát:

1. Xác định domain type, ví dụ Person.
2. Đọc các query parameter được phép bind.
3. Chuyển chuỗi HTTP thành kiểu Java tương ứng như Boolean, Long, enum hoặc ngày tháng.
4. Tạo điều kiện Querydsl cho từng thuộc tính.
5. Kết hợp các điều kiện thành một Predicate.
6. Đưa Predicate cho repository thực thi.

Predicate tương đương có thể được viết:

~~~~java
QPerson person = QPerson.person;

Predicate predicate = person.firstName.eq("An")
        .and(person.active.isTrue());
~~~~

Trong Spring Data REST, khi repository và phiên bản được tích hợp với QuerydslPredicateExecutor, query parameter của collection resource có thể được dùng để lọc. Với Spring Data Web trong controller MVC tùy chỉnh, có thể dùng **@QuerydslPredicate** để nhận Predicate từ request.

Không mặc định mọi query parameter đều trở thành điều kiện tìm kiếm. Binding có thể bị giới hạn bởi customizer, kiểu thuộc tính, conversion và cấu hình phiên bản.

## 6. Tùy chỉnh binding bằng QuerydslBinderCustomizer

QuerydslBindings xác định cách từng thuộc tính được chuyển thành điều kiện. Quy tắc mặc định có thể phụ thuộc kiểu thuộc tính và phiên bản. Nếu API cần semantics rõ ràng, hãy khai báo binding tường minh.

Ví dụ: tìm chuỗi theo contains không phân biệt hoa thường và loại password khỏi khả năng tìm kiếm:

~~~~java
@RepositoryRestResource(path = "people")
public interface PersonRepository
        extends JpaRepository<Person, Long>,
                QuerydslPredicateExecutor<Person>,
                QuerydslBinderCustomizer<QPerson> {

    @Override
    default void customize(
            QuerydslBindings bindings,
            QPerson root) {

        bindings.bind(root.firstName)
                .first((path, value) ->
                        path.containsIgnoreCase(value));

        bindings.bind(String.class)
                .first((StringPath path, String value) ->
                        path.containsIgnoreCase(value));

        bindings.excluding(root.password);
    }
}
~~~~

Binding cụ thể cho firstName xác định semantics của field đó. Binding theo String.class áp dụng quy tắc cho các thuộc tính chuỗi còn lại. excluding(root.password) ngăn password được dùng làm query parameter.

Binding theo field phù hợp khi thuộc tính có quy tắc riêng. Binding theo kiểu phù hợp khi muốn dùng cùng một quy tắc cho nhiều field. Hãy kiểm tra hành vi thực tế của phiên bản đang dùng nếu một thuộc tính khớp cả binding cụ thể và binding theo kiểu.

### Một số expression thường dùng

~~~~java
@Override
default void customize(QuerydslBindings bindings, QPerson root) {

    // So khớp chính xác.
    bindings.bind(root.email)
            .first((path, value) -> path.eq(value));

    // Chuỗi chứa, không phân biệt hoa thường.
    bindings.bind(root.firstName)
            .first((path, value) ->
                    path.containsIgnoreCase(value));

    // Số lớn hơn hoặc bằng giá trị gửi lên.
    bindings.bind(root.age)
            .first((path, value) -> path.goe(value));

    // Chỉ cho phép một số field.
    bindings.including(
            root.firstName,
            root.lastName,
            root.active,
            root.age
    );
}
~~~~

Các expression như eq, contains, containsIgnoreCase, startsWithIgnoreCase, goe, loe và in được dùng tùy kiểu Q-path. Không gọi operation của StringPath trên NumberPath hoặc path không có operation tương ứng.

## 7. first và all: một hay nhiều giá trị

Query parameter có thể xuất hiện nhiều lần:

~~~~http
GET /people?status=ACTIVE&status=PENDING
~~~~

Binding API cung cấp hai kiểu xử lý:

- **first(...)** dùng một giá trị đầu tiên theo contract của binding.
- **all(...)** nhận tập giá trị và cho phép tạo điều kiện từ toàn bộ tập đó.

Ví dụ tìm status thuộc một trong các giá trị gửi lên:

~~~~java
bindings.bind(root.status)
        .all((path, values) ->
                Optional.of(path.in(values)));
~~~~

Predicate tương đương status IN ('ACTIVE', 'PENDING'). Nếu dùng first cho tham số nhiều giá trị, các giá trị còn lại không được kết hợp thành điều kiện IN. Dùng all khi endpoint cần xử lý toàn bộ giá trị.

## 8. Excluding và including: blacklist hay allowlist

Binding có thể mở cho nhiều thuộc tính của domain type. Điều đó tiện khi phát triển nhưng có thể vô tình công bố khả năng lọc trên field không nên xuất hiện trong API.

**Excluding** tạo danh sách field bị cấm:

~~~~java
bindings.excluding(
        root.password,
        root.resetToken,
        root.internalNotes
);
~~~~

Cách này phù hợp khi phần lớn field được phép tìm kiếm và chỉ có một số field cần loại bỏ.

**Including** tạo allowlist field được phép bind:

~~~~java
bindings.including(
        root.firstName,
        root.lastName,
        root.email,
        root.active
);
~~~~

Cách này phù hợp với API công khai, nơi chỉ một tập nhỏ field có ý nghĩa tìm kiếm. Những thuộc tính không nằm trong allowlist không được mở thành query parameter.

Ẩn field trong response không đủ để bảo vệ tìm kiếm. Một field không được serialize vẫn có thể nhạy cảm nếu server cho phép client lọc theo field đó. Hãy kiểm soát binding độc lập với serialization và authorization.

## 9. Dùng @QuerydslPredicate trong controller tùy chỉnh

Ngoài repository resource tự động của Spring Data REST, Spring Data Web hỗ trợ bind Predicate vào tham số controller bằng @QuerydslPredicate.

~~~~java
@RestController
@RequestMapping("/people")
class PersonSearchController {

    private final PersonRepository repository;

    PersonSearchController(PersonRepository repository) {
        this.repository = repository;
    }

    @GetMapping("/filter")
    Page<Person> filter(
            @QuerydslPredicate(root = Person.class)
            Predicate predicate,
            Pageable pageable) {

        return repository.findAll(predicate, pageable);
    }
}
~~~~

Request:

~~~~http
GET /people/filter?firstName=An&active=true&page=0&size=20
~~~~

Spring Data Web tạo Predicate từ query parameter; controller chuyển predicate và Pageable cho QuerydslPredicateExecutor.

Controller tùy chỉnh phù hợp khi cần route tìm kiếm riêng, kết hợp predicate với logic nghiệp vụ hoặc tenant scope, trả DTO/projection, giới hạn kết quả, validation riêng hoặc authorization bổ sung.

@QuerydslPredicate cần Spring Data web support và cấu hình tương thích. Nếu muốn áp dụng custom binding cho controller, có thể dùng QuerydslBinderCustomizer trên repository hoặc binder được chỉ định theo API của phiên bản đang dùng.

## 10. Nested path và alias

Querydsl cho phép xây dựng điều kiện trên thuộc tính lồng nhau thông qua Q-type:

~~~~java
bindings.bind(root.address.city)
        .first((path, value) ->
                path.equalsIgnoreCase(value));
~~~~

QPerson có thể cung cấp path tới address.city nếu domain model và Q-type biểu diễn quan hệ đó. Tuy nhiên, mở path lồng nhau ra HTTP API cần cân nhắc:

- Association có thể tạo join tốn kém.
- Quan hệ collection có thể làm tăng số dòng kết quả hoặc gây truy vấn nặng.
- Field lồng nhau có thể chứa dữ liệu nhạy cảm.
- Tên property Java có thể không phải tên API mong muốn.

Nếu phiên bản QuerydslBindings hỗ trợ alias cho binding, có thể công bố tên query parameter thân thiện hơn tên thuộc tính nội bộ. Xác nhận method as(...) và behavior của nó trong Javadoc đúng phiên bản trước khi dùng.

## 11. Phân trang, sắp xếp và hiệu năng

Kết hợp Predicate với Pageable giúp API lọc và phân trang trong cùng request:

~~~~http
GET /people?active=true&page=0&size=20&sort=lastName,asc
~~~~

Với controller tùy chỉnh, có thể gọi:

~~~~java
Page<Person> page = repository.findAll(predicate, pageable);
~~~~

Không nên cho client yêu cầu page size không giới hạn. Cần cân nhắc:

- Index database cho field thường được lọc hoặc sắp xếp.
- Chỉ cho sort trên field được phép và có index phù hợp.
- Predicate trên association hoặc field không có index có thể rất tốn kém.
- Tổng số kết quả có thể yêu cầu count query riêng.
- Nhiều filter kết hợp có thể tạo query phức tạp.
- Giới hạn số điều kiện và kích thước danh sách giá trị.

Predicate-based search linh hoạt, nhưng không bảo đảm mọi tổ hợp điều kiện đều có hiệu năng tốt.

## 12. Kiểu dữ liệu và conversion

Web binding thường bắt đầu từ giá trị chuỗi trong URL. Spring Data cần chuyển giá trị đó thành kiểu Java phù hợp để tạo predicate.

~~~~http
GET /people?age=30&active=true&status=ACTIVE&createdAt=2026-01-15
~~~~

Các giá trị có thể được chuyển thành Integer/Long, Boolean, enum và ngày tháng nếu ConversionService có converter tương ứng.

Khi binding không hoạt động như mong đợi, kiểm tra:

1. Tên query parameter có khớp property path hoặc alias không.
2. Q-type có chứa thuộc tính đó không.
3. Giá trị chuỗi có chuyển đổi được sang kiểu domain không.
4. Có custom converter hoặc formatter nào thay đổi conversion không.
5. Binding có bị including/excluding giới hạn không.
6. Store module có hỗ trợ expression và operation tương ứng không.

Không tự parse mọi giá trị bằng toString() rồi tạo predicate không có kiểm tra kiểu. Dùng conversion và Querydsl path đúng kiểu giúp phát hiện lỗi sớm hơn.

## 13. Bảo mật bề mặt tìm kiếm

Querydsl web binding có thể mở ra một ngôn ngữ truy vấn nhỏ qua URL. Vì vậy, cần xem binding là một phần của API public.

- Chỉ cho phép tìm kiếm trên field có ý nghĩa nghiệp vụ.
- Loại trừ password, token, secret, internal flag và dữ liệu cá nhân không cần thiết.
- Ưu tiên allowlist với including(...) cho API public.
- Không cho client tự chọn path tùy ý hoặc mở mọi association.
- Bổ sung tenant/ownership predicate từ server; không tin query parameter do client gửi để giới hạn tenant.
- Kiểm soát page size, sort field và số lượng giá trị cho mỗi filter.
- Dùng index phù hợp và theo dõi query chậm.
- Trả projection/DTO nếu client không cần toàn bộ entity.
- Áp dụng authorization trước khi thực thi truy vấn.

Ví dụ, nếu người dùng chỉ được xem dữ liệu của tenant hiện tại, predicate tenant phải được kết hợp từ security context ở server. Không chỉ dựa vào request tenantId do client gửi, vì client có thể thay ID để dò dữ liệu của tenant khác.

## 14. Kiểm thử Querydsl binding

Nên kiểm tra cả binding và kết quả thực thi trong store thật hoặc test slice phù hợp.

Ví dụ với MockMvc:

~~~~java
mockMvc.perform(get("/people/filter")
        .param("firstName", "an")
        .param("active", "true")
        .param("page", "0")
        .param("size", "10"))
    .andExpect(status().isOk());
~~~~

Test cần xác nhận kết quả có đúng semantics containsIgnoreCase, Boolean conversion và phân trang.

Với field bị loại trừ:

~~~~java
mockMvc.perform(get("/people/filter")
        .param("password", "secret"))
    .andExpect(status().isOk());
~~~~

Không chỉ kiểm tra status code; xác nhận parameter bị loại không làm thay đổi kết quả truy vấn hoặc bị từ chối theo contract của ứng dụng.

Các trường hợp nên kiểm tra:

1. Field không nằm trong including(...) không tạo điều kiện truy vấn.
2. Nhiều status tạo điều kiện IN khi dùng all(...).
3. first(...) xử lý giá trị theo contract.
4. Alias, nested path và type conversion hoạt động đúng.
5. Pageable không vượt maximum page size.
6. Tenant scope luôn được áp dụng kể cả khi client không gửi tenant parameter.
7. Predicate được dịch và thực thi đúng trên database/store thực tế.

Test chỉ kiểm tra Predicate object không đủ để chứng minh store module dịch và thực thi query đúng.

## 15. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Không tìm thấy QPerson | Annotation processor chưa chạy hoặc generated sources chưa được IDE nhận | Kiểm tra build processor và generated-sources |
| Repository không khởi tạo | Store/version không hỗ trợ QuerydslPredicateExecutor hoặc dependency không tương thích | Kiểm tra tài liệu store và dependency tree |
| Query parameter không lọc dữ liệu | Binding chưa kích hoạt hoặc tên property không khớp | Kiểm tra Spring Data web/REST integration và binder |
| String search trả kết quả quá rộng/hẹp | Semantics binding mặc định khác kỳ vọng | Khai báo first(...) rõ ràng |
| Nhiều giá trị chỉ lấy một giá trị | Đang dùng first(...) thay vì all(...) | Dùng all(...) và predicate IN khi phù hợp |
| Field nhạy cảm vẫn tìm được | Chưa excluding hoặc chưa dùng allowlist | Dùng excluding(...) hoặc including(...) |
| Truy vấn chậm | Predicate mở quá nhiều field, association hoặc thiếu index | Giới hạn binding, thêm index và phân tích query |
| Giá trị ngày/enum không parse | ConversionService thiếu converter hoặc format không đúng | Bổ sung converter/formatter và test request |
| Controller không nhận Predicate | Thiếu Spring Data web support hoặc root type không đúng | Kiểm tra @QuerydslPredicate và cấu hình web |

## 16. Kết luận

QuerydslPredicateExecutor cho phép Spring Data repository thực thi Predicate có kiểu dữ liệu; web binding có thể chuyển query parameter thành Predicate để tạo API tìm kiếm linh hoạt. Khả năng này phụ thuộc phiên bản Spring Data và store module, đồng thời cần Q-type được sinh đúng.

QuerydslBinderCustomizer là điểm mở rộng quan trọng để định nghĩa semantics cho từng field, áp dụng binding theo kiểu, xử lý một hay nhiều giá trị và giới hạn field bằng allowlist hoặc blacklist. Với API public, hãy ưu tiên allowlist, giới hạn phân trang và luôn thêm điều kiện bảo mật từ server. Kiểm thử với đúng phiên bản và database thực tế để bảo đảm predicate được bind và thực thi đúng.

## Tài liệu tham khảo

- [Spring Data Commons — QuerydslPredicateExecutor API](https://docs.spring.io/spring-data/commons/reference/api/java/org/springframework/data/querydsl/QuerydslPredicateExecutor.html)
- [Spring Data Commons — Querydsl web support](https://docs.spring.io/spring-data/commons/reference/repositories/core-extensions.html)
- [Spring Data REST — Reference documentation](https://docs.spring.io/spring-data/rest/reference/)
- [Spring Data JPA — Querydsl support](https://docs.spring.io/spring-data/jpa/reference/repositories/core-extensions.html)
- [Querydsl Reference Guide](https://querydsl.com/static/querydsl/latest/reference/html_single/)
