# Giới hạn của Query by Example và lựa chọn truy vấn khác

**Query by Example (QBE)** là cách tạo truy vấn từ một đối tượng mẫu (probe) thay vì viết câu SQL hoặc tên phương thức truy vấn. Trong Spring Data R2DBC, ứng dụng điền các giá trị cần tìm vào probe, cấu hình ExampleMatcher để quyết định cách so khớp, rồi truyền Example cho repository reactive.

QBE phù hợp với màn hình tìm kiếm đơn giản có nhiều trường tùy chọn. Nó dễ dùng và giúp tránh phải tạo một phương thức repository cho mọi tổ hợp bộ lọc. Tuy nhiên, QBE chỉ diễn đạt được một tập điều kiện nhất định. Khi truy vấn cần nhóm AND/OR phức tạp, join, biểu thức database, projection đặc thù hoặc kiểm soát SQL rõ ràng, nên chuyển sang derived query, @Query, R2dbcEntityTemplate hoặc DatabaseClient.

## 1. Query by Example là gì?

QBE gồm ba thành phần:

- **Probe**: một instance entity chứa các giá trị muốn tìm.
- **ExampleMatcher**: quy định cách so khớp từng property hoặc toàn bộ probe.
- **Example**: kết hợp probe và matcher để repository thực thi truy vấn.

Ví dụ, nếu muốn tìm khách hàng có tên chứa chuỗi An và đang hoạt động, có thể tạo một Customer mẫu:

~~~java
Customer probe = new Customer(
    null,
    "An",
    null,
    true,
    null
);
~~~

Các giá trị null thường được bỏ qua theo mặc định. Vì vậy, probe này chỉ đưa các property fullName và active vào điều kiện tìm kiếm. Matcher có thể thay đổi cách so khớp chuỗi fullName từ exact thành containing.

~~~java
ExampleMatcher matcher = ExampleMatcher.matching()
    .withMatcher(
        "fullName",
        ExampleMatcher.GenericPropertyMatchers.contains()
            .ignoreCase()
    );

Example<Customer> example = Example.of(probe, matcher);
~~~

Repository thực thi Example và phát kết quả reactive:

~~~java
Flux<Customer> customers = repository.findAll(example);
~~~

Ý tưởng chính là: **giá trị trong probe quyết định property nào được dùng để lọc; ExampleMatcher quyết định cách so khớp các giá trị đó.**

## 2. Dùng QBE với Spring Data R2DBC

Repository cần hỗ trợ reactive Query by Example. Các repository Spring Data R2DBC tiêu chuẩn cung cấp các thao tác QBE thông qua ReactiveQueryByExampleExecutor trong những phiên bản hỗ trợ tương ứng.

Ví dụ entity:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table("customer")
public record Customer(
    @Id Long id,
    @Column("full_name") String fullName,
    String email,
    Boolean active,
    @Version Long version
) {}
~~~

Repository:

~~~java
import org.springframework.data.repository.reactive.ReactiveCrudRepository;
import org.springframework.data.repository.query.ReactiveQueryByExampleExecutor;

public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long>,
                ReactiveQueryByExampleExecutor<Customer> {
}
~~~

Ví dụ trên thể hiện rõ abstraction QBE mà repository cần có. Trong một số phiên bản/cấu hình Spring Data R2DBC, repository chuyên biệt đã kế thừa reactive QBE executor; hãy dùng đúng interface do phiên bản dự án cung cấp và không khai báo thêm executor không tương thích. Với reactive repository, các phương thức QBE trả về Mono hoặc Flux thay vì kiểu đồng bộ.

Các thao tác QBE thường dùng gồm:

| Phương thức | Kết quả | Mục đích |
|---|---|---|
| findOne(example) | Mono<T> | Lấy một kết quả phù hợp |
| findAll(example) | Flux<T> | Lấy tất cả kết quả phù hợp |
| findAll(example, sort) | Flux<T> | Lấy kết quả theo thứ tự |
| count(example) | Mono<Long> | Đếm số kết quả |
| exists(example) | Mono<Boolean> | Kiểm tra có kết quả hay không |

Chữ ký chính xác và interface kế thừa có thể thay đổi theo phiên bản Spring Data. Hãy kiểm tra dependency của dự án khi dùng API QBE.

## 3. Cách tạo probe

Probe là một instance của kiểu domain mà repository quản lý. Các property có giá trị được dùng làm điều kiện; các property null thường bị bỏ qua theo mặc định.

Ví dụ:

~~~java
Customer probe = new Customer(
    null,             // id: bỏ qua
    "Nguyen",         // fullName: dùng để tìm
    null,             // email: bỏ qua
    true,             // active: dùng để tìm
    null              // version: bỏ qua
);
~~~

Probe không phải là entity cần lưu. Nó chỉ là đối tượng mang giá trị tìm kiếm. Không gọi save(probe) và không cần gán ID để thực hiện QBE.

Nên tạo probe chuyên biệt cho từng thao tác tìm kiếm. Tránh dùng một entity nghiệp vụ đang được chỉnh sửa làm probe vì những property còn sót lại có thể vô tình trở thành điều kiện truy vấn.

### 3.1. Null property mặc định được bỏ qua

Với ExampleMatcher mặc định, null property không tham gia điều kiện:

~~~java
Example<Customer> example =
    Example.of(new Customer(null, "An", null, null, null));
~~~

Ví dụ này tìm theo fullName; id, email, active và version không được dùng làm điều kiện vì chúng đang null.

Điều này tiện cho bộ lọc tùy chọn, nhưng có một hệ quả: **QBE mặc định không thể hiểu null trong probe là yêu cầu tìm cột IS NULL.** Null thường có nghĩa “không cung cấp điều kiện”.

### 3.2. Muốn tìm giá trị NULL

Nếu nghiệp vụ cần tìm các hàng có email là NULL, có thể dùng matcher bao gồm null values:

~~~java
ExampleMatcher matcher = ExampleMatcher.matching()
    .withIncludeNullValues()
    .withIgnorePaths("id", "fullName", "active", "version");

Example<Customer> example = Example.of(
    new Customer(null, null, null, null, null),
    matcher
);
~~~

Cần thận trọng: withIncludeNullValues() có thể đưa mọi property null của probe vào điều kiện, không chỉ email. Một probe có nhiều thuộc tính null có thể tạo ra truy vấn quá chặt hoặc không đúng mục đích.

Nếu chỉ muốn kiểm tra một property cụ thể là NULL, Query/Criteria thường rõ ràng hơn:

~~~java
Query query = Query.query(
    Criteria.where("email").isNull()
);

return template.select(Customer.class)
    .matching(query)
    .all();
~~~

Với bộ lọc có nhiều trạng thái, hãy phân biệt “không lọc”, “tìm NULL” và “tìm theo giá trị” bằng một kiểu Filter hoặc enum riêng.

### 3.3. Primitive property có giá trị mặc định

QBE khó bỏ qua một property primitive vì primitive không thể chứa null.

Ví dụ:

~~~java
public class CustomerProbe {
    private boolean active;
    private int age;
}
~~~

Khi tạo object mới, active mặc định là false và age mặc định là 0. Những giá trị này có thể được xem là giá trị cần tìm thay vì “không cung cấp bộ lọc”.

Nếu trường cần trạng thái tùy chọn, hãy dùng kiểu wrapper:

~~~java
private Boolean active;
private Integer age;
~~~

Wrapper cho phép null biểu diễn “bỏ qua điều kiện”. Đây là điểm quan trọng khi thiết kế probe cho form tìm kiếm.

## 4. Cấu hình ExampleMatcher

ExampleMatcher điều khiển cách so khớp property. Matcher mặc định thường sử dụng exact matching cho chuỗi và bỏ qua property null.

Ví dụ matcher tùy chỉnh:

~~~java
ExampleMatcher matcher = ExampleMatcher.matching()
    .withIgnorePaths("id", "version")
    .withStringMatcher(ExampleMatcher.StringMatcher.CONTAINING)
    .withIgnoreCase();
~~~

Ý nghĩa:

- withIgnorePaths bỏ qua các property không muốn đưa vào điều kiện.
- withStringMatcher đặt cách so khớp mặc định cho các property kiểu String.
- withIgnoreCase yêu cầu so khớp chuỗi không phân biệt chữ hoa/chữ thường nếu store hỗ trợ.

Có thể cấu hình riêng từng property:

~~~java
ExampleMatcher matcher = ExampleMatcher.matching()
    .withIgnorePaths("id", "version")
    .withMatcher(
        "fullName",
        ExampleMatcher.GenericPropertyMatchers.contains()
            .ignoreCase()
    )
    .withMatcher(
        "email",
        ExampleMatcher.GenericPropertyMatchers.exact()
            .ignoreCase()
    );
~~~

Trong ví dụ, fullName dùng contains không phân biệt hoa thường, còn email dùng exact không phân biệt hoa thường. Các property String khác vẫn dùng quy tắc mặc định.

### 4.1. Các kiểu StringMatcher

Các chế độ thường gặp:

| StringMatcher | Ý nghĩa | Mẫu tương đương về ý tưởng |
|---|---|---|
| DEFAULT | Dùng quy tắc mặc định của store/matcher | Thường là exact |
| EXACT | Khớp toàn bộ chuỗi | value |
| STARTING | Bắt đầu bằng chuỗi | value% |
| ENDING | Kết thúc bằng chuỗi | %value |
| CONTAINING | Có chứa chuỗi | %value% |

Khả năng hỗ trợ và cách triển khai phụ thuộc store và phiên bản. Không giả định mọi chế độ hoặc mọi collation hoạt động giống nhau trên tất cả hệ quản trị.

QBE không phải API để viết tùy ý một mẫu LIKE hoàn chỉnh. Nếu cần escape wildcard, biểu thức ESCAPE, full-text search hoặc pattern đặc thù database, hãy dùng Query/Criteria khi đủ khả năng hoặc viết SQL qua DatabaseClient.

### 4.2. Ignore case

Có thể yêu cầu ignore case cho toàn bộ property String:

~~~java
ExampleMatcher matcher = ExampleMatcher.matching()
    .withIgnoreCase();
~~~

Hoặc chỉ cho một property:

~~~java
ExampleMatcher matcher = ExampleMatcher.matching()
    .withMatcher(
        "email",
        ExampleMatcher.GenericPropertyMatchers.exact().ignoreCase()
    );
~~~

Kết quả không phân biệt hoa thường phụ thuộc cách Spring Data tạo biểu thức và quy tắc so sánh của database. Với dữ liệu Unicode, ngôn ngữ có dấu hoặc collation đặc biệt, hãy kiểm tra kết quả trên đúng hệ quản trị mục tiêu.

### 4.3. Matching all và matching any

QBE hỗ trợ hai cách kết hợp các property được chọn:

- matching(): tất cả điều kiện được kết hợp theo AND.
- matchingAny(): các điều kiện được kết hợp theo OR.

Ví dụ AND:

~~~java
ExampleMatcher matcher = ExampleMatcher.matching();
~~~

Nếu probe có fullName và active, kết quả cần thỏa cả hai điều kiện.

Ví dụ OR:

~~~java
ExampleMatcher matcher = ExampleMatcher.matchingAny();
~~~

Với cùng probe, kết quả có thể thỏa fullName hoặc active.

matchingAny() hữu ích cho tìm kiếm rộng trên vài trường. Tuy nhiên, nó chỉ cung cấp cách kết hợp ở mức các property được matcher chọn. Nó không phải bộ dựng biểu thức boolean tổng quát để tạo các nhóm lồng nhau như:

~~~sql
WHERE tenant_id = :tenant
  AND (full_name LIKE :name OR email LIKE :email)
  AND active = TRUE
~~~

Khi cần nhóm AND/OR như vậy, hãy dùng Criteria hoặc SQL tường minh.

## 5. Ví dụ hoàn chỉnh: tìm khách hàng bằng probe

Giả sử màn hình tìm kiếm có các trường tên, email và trạng thái hoạt động. Người dùng có thể bỏ trống một vài trường.

~~~java
import org.springframework.data.domain.Example;
import org.springframework.data.domain.ExampleMatcher;
import reactor.core.publisher.Flux;

public Flux<Customer> search(
        String name,
        String email,
        Boolean active) {

    Customer probe = new Customer(
        null,
        name,
        email,
        active,
        null
    );

    ExampleMatcher matcher = ExampleMatcher.matching()
        .withIgnorePaths("id", "version")
        .withMatcher(
            "fullName",
            ExampleMatcher.GenericPropertyMatchers.contains()
                .ignoreCase()
        )
        .withMatcher(
            "email",
            ExampleMatcher.GenericPropertyMatchers.exact()
                .ignoreCase()
        );

    Example<Customer> example = Example.of(probe, matcher);

    return repository.findAll(example);
}
~~~

Với đầu vào:

~~~text
name = "An"
email = null
active = true
~~~

QBE tạo điều kiện dựa trên fullName và active; email null được bỏ qua. Matcher yêu cầu tên chứa An không phân biệt hoa thường.

Ví dụ này giả định các property String null được bỏ qua và active là Boolean wrapper. Nếu active là boolean primitive, giá trị mặc định false có thể vô tình trở thành điều kiện.

## 6. Những giới hạn quan trọng của Query by Example

QBE đơn giản vì nó chỉ mô tả một probe và một tập quy tắc so khớp. Sự đơn giản đó cũng tạo ra các giới hạn.

### 6.1. Không biểu diễn được nhóm điều kiện lồng nhau tùy ý

QBE hỗ trợ matchingAll và matchingAny, nhưng không cho phép mô tả mọi biểu thức boolean.

Ví dụ yêu cầu:

~~~sql
WHERE tenant_id = :tenant
  AND (full_name LIKE :name OR email LIKE :email)
  AND active = TRUE
~~~

Không thể diễn đạt chính xác cấu trúc nhóm này chỉ bằng một ExampleMatcher thông thường. matchingAny() có thể OR các property trong probe, nhưng không thể đặt riêng hai property vào một nhóm OR rồi AND với tenant và active theo ý muốn.

Dùng Criteria để xây dựng các nhóm điều kiện hoặc dùng DatabaseClient khi cần SQL chính xác.

### 6.2. Không phù hợp với join và truy vấn nhiều bảng

Probe mô tả property của một entity. QBE không phải công cụ dựng join tùy ý giữa nhiều bảng, subquery hoặc CTE.

Spring Data Relational tập trung vào mô hình aggregate và mapping quan hệ. Không nên giả định rằng property object lồng nhau sẽ tự động tạo join giống một số ORM.

Nếu cần kết hợp customer với order, product hoặc bảng thống kê, hãy dùng truy vấn phù hợp ở tầng SQL hoặc template. Với join phức tạp, DatabaseClient thường là lựa chọn trực tiếp.

### 6.3. Không diễn đạt được biểu thức SQL tùy chỉnh

QBE không phải nơi để viết:

- Hàm trên cột như LOWER(), COALESCE(), DATE_TRUNC().
- So sánh giữa hai cột.
- Subquery hoặc EXISTS.
- Window function.
- Full-text search hoặc toán tử riêng của database.
- Điều kiện ESCAPE tùy chỉnh cho LIKE.
- Biểu thức JSON hoặc kiểu dữ liệu đặc thù.

Nếu truy vấn cần những biểu thức đó, dùng @Query hoặc DatabaseClient.

### 6.4. String matching bị giới hạn

QBE cung cấp một số kiểu so khớp chuỗi định sẵn. Nó không cho phép biểu diễn mọi mẫu tìm kiếm tùy ý như regex hoặc một biểu thức LIKE phức tạp với nhiều wildcard và quy tắc escape.

Khả năng cụ thể của regex và các chế độ khác còn phụ thuộc datastore. Không nên dựa vào hỗ trợ regex của một module Spring Data khác rồi giả định Spring Data R2DBC có hành vi tương tự.

### 6.5. Null và giá trị mặc định của primitive dễ gây nhầm lẫn

Null thường có nghĩa bỏ qua điều kiện. Muốn tìm NULL phải cấu hình includeNullValues hoặc chọn API khác. Primitive luôn có giá trị mặc định nên khó biểu diễn trạng thái “không lọc”.

Với form tìm kiếm, kiểu wrapper và probe chuyên dụng thường an toàn hơn.

### 6.6. Không phải công cụ để điều khiển projection tùy ý

QBE hướng tới việc tìm entity theo probe. Nếu chỉ cần vài cột, một DTO báo cáo, aggregate hoặc phép tính, QBE thường không phải cách phù hợp.

Dùng projection repository hoặc DatabaseClient để ánh xạ kết quả theo cấu trúc cần thiết.

### 6.7. Cách so khớp phụ thuộc database

Ignore case, chuỗi rỗng, collation, kiểu dữ liệu và một số chế độ StringMatcher có thể cho kết quả khác nhau giữa các hệ quản trị.

QBE giúp tránh viết SQL thủ công cho truy vấn đơn giản, nhưng không làm mất khác biệt giữa các database. Hãy kiểm thử trên hệ quản trị thực tế.

## 7. Khi nào nên chọn derived query?

Derived query là truy vấn được tạo từ tên phương thức repository.

Ví dụ:

~~~java
import org.springframework.data.repository.reactive.ReactiveCrudRepository;
import reactor.core.publisher.Flux;

public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {

    Flux<Customer> findByActiveTrue();

    Flux<Customer> findByFullNameContainingIgnoreCase(String name);

    Flux<Customer> findByEmailIsNull();

    Flux<Customer> findByActiveTrueAndFullNameContainingIgnoreCase(
        String name
    );
}
~~~

Derived query phù hợp khi:

- Điều kiện truy vấn ổn định và có thể diễn đạt bằng tên phương thức.
- Số tổ hợp điều kiện không quá lớn.
- Muốn API repository thể hiện rõ nghiệp vụ.
- Không cần SQL tùy chỉnh hoặc nhóm điều kiện quá phức tạp.

Không nên tạo hàng chục phương thức cho mọi tổ hợp filter. Nếu bộ lọc thay đổi động theo nhiều tham số, Criteria hoặc QBE có thể gọn hơn.

## 8. Khi nào nên chọn @Query?

Dùng @Query khi câu SQL có cấu trúc tương đối cố định và cần viết tường minh ngay trên repository.

Ví dụ:

~~~java
import org.springframework.data.r2dbc.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.data.repository.reactive.ReactiveCrudRepository;
import reactor.core.publisher.Flux;

public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {

    @Query("""
        SELECT id, full_name, email, active, version
        FROM customer
        WHERE active = :active
          AND LOWER(full_name) LIKE LOWER(:pattern)
        """)
    Flux<Customer> searchByName(
        @Param("active") Boolean active,
        @Param("pattern") String pattern
    );
}
~~~

@Query phù hợp khi:

- SQL cần được kiểm soát rõ ràng.
- Truy vấn dùng hàm database hoặc cú pháp đặc thù.
- Cần join hoặc projection mà derived query/QBE không diễn đạt thuận tiện.
- Câu SQL ổn định, dễ đặt cạnh repository method.

Ưu điểm là SQL nằm gần repository contract. Hạn chế là truy vấn động với nhiều nhánh điều kiện có thể làm annotation dài và khó bảo trì. Với bộ lọc tùy chọn phức tạp, hãy cân nhắc template hoặc custom repository fragment.

## 9. Khi nào nên chọn R2dbcEntityTemplate và Criteria?

R2dbcEntityTemplate phù hợp khi truy vấn cần điều kiện động nhưng vẫn muốn dùng entity mapping của Spring Data.

Ví dụ bộ lọc có tenant bắt buộc, tên tùy chọn, email tùy chọn và active tùy chọn:

~~~java
import org.springframework.data.relational.core.query.Criteria;
import org.springframework.data.relational.core.query.Query;
import reactor.core.publisher.Flux;

public Flux<Customer> search(
        Long tenantId,
        String name,
        String email,
        Boolean active) {

    Criteria criteria =
        Criteria.where("tenantId").is(tenantId);

    if (name != null && !name.isBlank()) {
        criteria = criteria.and("fullName")
            .like("%" + name.trim() + "%");
    }

    if (email != null && !email.isBlank()) {
        criteria = criteria.and("email")
            .is(email.trim());
    }

    if (active != null) {
        criteria = criteria.and("active").is(active);
    }

    Query query = Query.query(criteria)
        .limit(100);

    return template.select(Customer.class)
        .matching(query)
        .all();
}
~~~

Criteria có thể được kết hợp bằng AND và OR để xây dựng điều kiện linh hoạt hơn QBE. Template cũng hỗ trợ sort, limit, offset và các thao tác entity khác.

Nên dùng Criteria khi:

- Bộ lọc có nhiều tham số tùy chọn.
- Cần nhóm điều kiện AND/OR.
- Cần kiểm tra NULL tường minh.
- Muốn giữ entity mapping, conversion và dialect của Spring Data.
- Không cần viết toàn bộ SQL bằng tay.

Nếu truy vấn đòi hỏi join, CTE hoặc cú pháp database riêng mà Query/Criteria không thể diễn đạt, chuyển sang DatabaseClient.

## 10. Khi nào nên chọn DatabaseClient?

DatabaseClient thuộc Spring R2DBC và cho phép thực thi SQL trực tiếp. Ứng dụng tự kiểm soát câu lệnh, bind parameter và cách ánh xạ Row.

Ví dụ:

~~~java
import org.springframework.r2dbc.core.DatabaseClient;
import reactor.core.publisher.Flux;

public Flux<CustomerSummary> searchSummary(String keyword) {
    String pattern = "%" + keyword.trim() + "%";

    return databaseClient.sql("""
            SELECT c.id, c.full_name, COUNT(o.id) AS order_count
            FROM customer c
            LEFT JOIN purchase_order o ON o.customer_id = c.id
            WHERE c.full_name LIKE :pattern
            GROUP BY c.id, c.full_name
            ORDER BY c.full_name
            """)
        .bind("pattern", pattern)
        .map((row, metadata) -> new CustomerSummary(
            row.get("id", Long.class),
            row.get("full_name", String.class),
            row.get("order_count", Long.class)
        ))
        .all();
}
~~~

Ví dụ dùng join, group by và projection nên QBE không phù hợp. DatabaseClient cho phép viết SQL đúng với nhu cầu và ánh xạ kết quả sang DTO riêng.

~~~java
public record CustomerSummary(
    Long id,
    String fullName,
    Long orderCount
) {}
~~~

Luôn bind giá trị đầu vào thay vì nối chúng vào chuỗi SQL. Nếu dùng LIKE và muốn tìm wildcard như ký tự literal, cần escape % và _ theo cú pháp database; bind parameter tự nó không loại bỏ ý nghĩa wildcard.

## 11. So sánh các lựa chọn

| Tiêu chí | Query by Example | Derived query | @Query | R2dbcEntityTemplate | DatabaseClient |
|---|---|---|---|---|---|
| Cách định nghĩa | Probe + ExampleMatcher | Tên phương thức | SQL trong annotation | Query + Criteria | SQL trực tiếp |
| Điều kiện tùy chọn | Thuận tiện với null property | Thường phải tạo phương thức riêng | Có thể nhưng annotation dễ dài | Rất linh hoạt | Rất linh hoạt |
| AND/OR đơn giản | matchingAll/matchingAny | Qua tên phương thức | SQL tùy ý | Có thể kết hợp Criteria | SQL tùy ý |
| Nhóm boolean lồng nhau | Không phù hợp | Giới hạn | Có | Linh hoạt theo Criteria API | Toàn quyền SQL |
| NULL | Include null values, cần cẩn trọng | IsNull/IsNotNull | SQL tường minh | isNull/isNotNull | SQL tường minh |
| String matching | Các chế độ định sẵn | Keyword định sẵn | SQL tùy ý | Criteria/LIKE | SQL tùy ý |
| Join và subquery | Không phù hợp | Giới hạn theo repository query | Có | Không phải thế mạnh | Phù hợp |
| Mapping entity | Tự động | Tự động | Tự động khi trả entity phù hợp | Tự động | Thường tự map |
| Projection tùy chỉnh | Hạn chế | Có qua projection phù hợp | Có | Tùy API | Rất linh hoạt |
| Nơi nên đặt | Tìm kiếm đơn giản theo probe | Truy vấn nghiệp vụ ổn định | SQL cố định, tường minh | Bộ lọc động ở mức entity | SQL phức tạp hoặc đặc thù |

## 12. Kết hợp nhiều cách trong cùng một ứng dụng

Không cần ép mọi truy vấn vào một abstraction duy nhất.

Một ứng dụng có thể:

- Dùng QBE cho màn hình tìm kiếm đơn giản với các trường độc lập.
- Dùng derived query cho thao tác nghiệp vụ có điều kiện ổn định.
- Dùng @Query cho một số SQL cố định có join hoặc hàm database.
- Dùng R2dbcEntityTemplate cho bộ lọc động ở mức entity.
- Dùng DatabaseClient cho báo cáo, thống kê hoặc truy vấn SQL phức tạp.

Để dễ bảo trì, hãy đặt truy vấn phức tạp trong repository hoặc custom repository fragment thay vì viết SQL rải rác trong controller. Service nên điều phối nghiệp vụ và kết hợp publisher reactive.

### 12.1. Custom repository fragment

Nếu một repository có nhiều truy vấn động phức tạp, có thể tách phần triển khai thành fragment riêng.

~~~java
public interface CustomerSearchRepository {
    Flux<Customer> search(CustomerSearchFilter filter);
}
~~~

~~~java
public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long>,
                CustomerSearchRepository {
}
~~~

Phần triển khai CustomerSearchRepositoryImpl có thể inject R2dbcEntityTemplate hoặc DatabaseClient. Cách này giữ repository contract gọn và gom logic tìm kiếm vào một thành phần có trách nhiệm rõ ràng.

## 13. Những sai lầm thường gặp

### 13.1. Dùng QBE cho mọi loại truy vấn

QBE phù hợp với tìm kiếm đơn giản theo probe. Dùng nó cho join, subquery, nhóm điều kiện phức tạp hoặc biểu thức database sẽ khiến mô hình truy vấn khó biểu đạt và khó hiểu.

Hãy chọn abstraction theo cấu trúc truy vấn.

### 13.2. Quên rằng null mặc định được bỏ qua

Nếu probe có email null, điều đó thường không có nghĩa email IS NULL. Nó thường có nghĩa bỏ qua email.

Muốn tìm NULL, dùng withIncludeNullValues một cách có kiểm soát hoặc dùng Criteria.isNull().

### 13.3. Dùng primitive cho bộ lọc tùy chọn

boolean false hoặc int 0 có thể trở thành điều kiện ngoài ý muốn. Dùng Boolean, Integer hoặc kiểu wrapper tương ứng để null biểu diễn “không lọc”.

### 13.4. Không bỏ qua ID và version

Nếu probe mang ID hoặc version, chúng có thể tham gia điều kiện và làm kết quả bị thu hẹp ngoài ý muốn. Dùng withIgnorePaths cho property không thuộc bộ lọc.

### 13.5. Nghĩ matchingAny tạo được mọi nhóm OR

matchingAny() OR các điều kiện probe được chọn. Nó không cho phép xây mọi nhóm boolean lồng nhau. Dùng Criteria hoặc SQL cho cấu trúc phức tạp.

### 13.6. Dùng chuỗi matcher mà không kiểm tra database

Ignore case và StringMatcher có thể phụ thuộc dialect, collation và phiên bản. Kiểm thử trên database mục tiêu, nhất là với Unicode và dữ liệu có dấu.

### 13.7. Dùng probe chứa trạng thái domain không liên quan

Một entity nghiệp vụ có thể chứa giá trị mặc định hoặc thuộc tính đã được gán từ nơi khác. Tái sử dụng instance đó làm probe có thể vô tình tạo thêm điều kiện. Tạo probe mới từ filter đầu vào sẽ dễ dự đoán hơn.

### 13.8. Mong QBE tự join quan hệ

QBE không tự biến property object hoặc aggregate khác thành join SQL tùy ý. Hãy dùng SQL hoặc API truy vấn phù hợp nếu cần dữ liệu từ nhiều bảng.

## 14. Quy trình chọn cách truy vấn

Khi thiết kế một tính năng tìm kiếm, có thể đi theo trình tự sau:

1. Xác định các điều kiện là cố định hay tùy chọn.
2. Nếu chỉ là các giá trị property độc lập, cân nhắc QBE.
3. Nếu truy vấn cố định và tên phương thức dễ đọc, cân nhắc derived query.
4. Nếu cần SQL cố định, join hoặc biểu thức riêng, cân nhắc @Query.
5. Nếu cần ghép điều kiện động và vẫn muốn entity mapping, dùng R2dbcEntityTemplate với Criteria.
6. Nếu cần toàn quyền SQL, projection, aggregate hoặc cú pháp database, dùng DatabaseClient.
7. Nếu logic truy vấn lớn, đóng gói trong custom repository fragment.
8. Kiểm thử trên database thực tế đối với khác biệt NULL, collation, kiểu dữ liệu và dialect.

## 15. Ghi nhớ

Query by Example dùng một probe và ExampleMatcher để tạo truy vấn từ giá trị entity. Nó phù hợp với bộ lọc đơn giản, nhất là khi nhiều property có thể được bỏ qua bằng null. Matcher cho phép chọn exact, containing, starting, ending, ignore case và cách kết hợp matchingAll/matchingAny trong phạm vi mà store hỗ trợ.

Giới hạn chính của QBE là không diễn đạt được mọi nhóm điều kiện boolean, join, subquery, biểu thức SQL hoặc projection tùy ý. Khi truy vấn vượt khỏi phạm vi đó, hãy chọn derived query cho điều kiện cố định, @Query cho SQL khai báo, R2dbcEntityTemplate/Criteria cho bộ lọc động ở mức entity, hoặc DatabaseClient cho SQL phức tạp. Chọn đúng mức trừu tượng giúp truy vấn dễ đọc, dễ kiểm thử và không làm QBE gánh những yêu cầu mà nó không được thiết kế để giải quyết.

