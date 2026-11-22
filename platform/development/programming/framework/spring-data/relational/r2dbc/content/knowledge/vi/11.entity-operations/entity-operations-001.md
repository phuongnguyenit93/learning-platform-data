# Khởi tạo và sử dụng R2dbcEntityTemplate

**R2dbcEntityTemplate** là API truy cập dữ liệu ở mức entity của Spring Data R2DBC. Nó cho phép ứng dụng insert, select, update và delete entity bằng các đối tượng Java, đồng thời sử dụng metadata mapping, converter và dialect của Spring Data Relational để chuyển thao tác thành SQL phù hợp.

Template nằm giữa repository abstraction và SQL trực tiếp. Khi repository không đủ linh hoạt cho một truy vấn động, nhưng ứng dụng vẫn muốn giữ entity mapping của Spring Data, R2dbcEntityTemplate là lựa chọn phù hợp. Nếu cần kiểm soát toàn bộ SQL và ánh xạ kết quả tùy chỉnh, có thể dùng DatabaseClient ở tầng thấp hơn.

## 1. R2dbcEntityTemplate nằm ở đâu?

Trong Spring Data R2DBC, ứng dụng có thể truy cập dữ liệu qua nhiều mức trừu tượng:

- **Repository**: cung cấp CRUD và truy vấn theo phương thức hoặc query khai báo.
- **R2dbcEntityTemplate**: cung cấp thao tác entity linh hoạt thông qua fluent API, Query và Criteria.
- **DatabaseClient**: thực thi SQL trực tiếp qua Spring R2DBC.

R2dbcEntityTemplate phối hợp với hạ tầng mapping và kết nối:

~~~mermaid
flowchart TB
    A["Ứng dụng / Service"]
    B["Repository reactive"]
    C["R2dbcEntityTemplate"]
    D["ReactiveDataAccessStrategy"]
    E["RelationalMappingContext"]
    F["R2dbcConverter"]
    G["R2dbcDialect"]
    H["DatabaseClient"]
    I["ConnectionFactory"]
    J["R2DBC Driver"]
    K[("Database")]

    A --> B
    A --> C
    B --> C
    C --> D
    D --> E
    D --> F
    D --> G
    C --> H
    H --> I
    I --> J
    J --> K
~~~

Sơ đồ thể hiện quan hệ trách nhiệm ở mức khái niệm. Ứng dụng thường gọi repository hoặc template. Template sử dụng metadata entity và converter để ánh xạ dữ liệu; dialect cung cấp khác biệt SQL theo hệ quản trị; DatabaseClient thực thi câu lệnh qua ConnectionFactory và driver.

### 1.1. Template đảm nhiệm những gì?

R2dbcEntityTemplate hỗ trợ các nhóm thao tác chính:

| Nhóm thao tác | Mục đích |
|---|---|
| Insert | Thêm entity mới vào bảng |
| Select | Truy vấn entity theo điều kiện |
| Update | Cập nhật entity hoặc các cột theo điều kiện |
| Delete | Xóa entity theo định danh hoặc điều kiện |
| Mapping | Chuyển đổi giữa entity Java và dữ liệu R2DBC |
| Fluent operations | Xây dựng thao tác theo chuỗi API có kiểu dữ liệu rõ ràng |

Template sử dụng cùng hệ thống mapping của Spring Data R2DBC. Vì vậy, entity có thể khai báo @Table, @Column, @Id, @Version, @Embedded hoặc các metadata quan hệ được hỗ trợ.

### 1.2. Template không phải là connection pool

R2dbcEntityTemplate không tự thay thế R2DBC driver hoặc quản lý một pool độc lập. Nó sử dụng DatabaseClient và ConnectionFactory được cấu hình cho ứng dụng. Connection pool, nếu cần, được cấu hình ở tầng ConnectionFactory.

Cũng không nên tạo một template mới cho mỗi request. Template là thành phần dùng chung, thường được Spring quản lý như một bean và inject vào service hoặc lớp truy cập dữ liệu.

## 2. Khởi tạo và cấu hình R2dbcEntityTemplate

### 2.1. Dùng Spring Boot auto-configuration

Trong ứng dụng Spring Boot, cách thông thường là khai báo dependency starter và R2DBC driver, sau đó cấu hình kết nối trong application.yml.

Ví dụ Gradle:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-r2dbc")
    runtimeOnly("org.postgresql:r2dbc-postgresql")
}
~~~

Cấu hình kết nối:

~~~yaml
spring:
  r2dbc:
    url: r2dbc:postgresql://localhost:5432/shop
    username: ${DB_USERNAME}
    password: ${DB_PASSWORD}
~~~

Khi classpath và cấu hình phù hợp, Spring Boot tạo ConnectionFactory và các thành phần R2DBC cần thiết. R2dbcEntityTemplate có thể được cấu hình dựa trên ConnectionFactory và các thành phần mapping của ứng dụng.

Inject template bằng constructor:

~~~java
import org.springframework.data.r2dbc.core.R2dbcEntityTemplate;
import org.springframework.stereotype.Service;

@Service
public class CustomerService {

    private final R2dbcEntityTemplate template;

    public CustomerService(R2dbcEntityTemplate template) {
        this.template = template;
    }
}
~~~

Ứng dụng không cần tự gọi ConnectionFactories.get() trong mỗi service. Hãy để Spring container quản lý các bean kết nối và template, sau đó inject chúng vào nơi cần sử dụng.

Tên starter, cách auto-configuration và điều kiện tạo bean phụ thuộc phiên bản Spring Boot. Nếu dự án dùng phiên bản cũ hoặc cấu hình tùy chỉnh, hãy kiểm tra dependency management và tài liệu đúng phiên bản.

### 2.2. Cấu hình thủ công

Khi không dùng Spring Boot hoặc cần kiểm soát nhiều ConnectionFactory, ứng dụng có thể cấu hình các thành phần Spring Data R2DBC bằng Java configuration.

Spring Data R2DBC cung cấp AbstractR2dbcConfiguration để tích hợp ConnectionFactory và các thành phần mapping. Trong cấu hình thủ công, cần cung cấp ConnectionFactory tương ứng với driver, đồng thời bảo đảm template sử dụng đúng DatabaseClient, dialect và custom conversions của factory đó.

Không tạo nhiều factory cho cùng database nếu không có nhu cầu tách biệt rõ ràng. Nếu ứng dụng kết nối nhiều database, mỗi template phải gắn với đúng ConnectionFactory và transaction manager tương ứng. Các constructor và extension point có thể khác nhau giữa các phiên bản Spring Data; ưu tiên cách cấu hình được tài liệu phiên bản dự án hỗ trợ.

## 3. Entity dùng trong ví dụ

Giả sử ứng dụng quản lý khách hàng với bảng customer:

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

Mapping:

| Property Java | Cột trong database | Ý nghĩa |
|---|---|---|
| id | id | Khóa định danh |
| fullName | full_name | Họ tên |
| email | email | Địa chỉ email |
| active | active | Trạng thái hoạt động |
| version | version | Version cho optimistic locking |

Record là immutable. Khi insert hoặc update, template có thể trả về instance mới phản ánh ID/version do quá trình persistence tạo ra. Vì vậy, cần sử dụng entity được phát ra từ publisher thay vì tiếp tục dùng instance đầu vào với giả định rằng nó đã bị thay đổi.

## 4. Insert: thêm entity mới

Template cung cấp fluent API để insert entity.

~~~java
Customer customer =
    new Customer(null, "Nguyen An", "an@example.com", true, null);

return template.insert(Customer.class)
    .using(customer);
~~~

insert(Customer.class) xác định kiểu entity cần ghi. using(customer) cung cấp instance sẽ được insert. Kết quả là một Mono<Customer> phát ra entity đã lưu.

Khi database tự sinh ID, ID có thể được trả về trong entity kết quả:

~~~java
Mono<Customer> saved =
    template.insert(Customer.class)
        .using(customer);

return saved.map(Customer::id);
~~~

Đối với entity immutable hoặc record, giá trị ID mới nằm trong instance được trả về. Đừng bỏ qua kết quả insert nếu tầng nghiệp vụ cần ID vừa sinh.

### 4.1. Insert nhiều entity

Có thể kết hợp nhiều thao tác insert bằng Reactor:

~~~java
import reactor.core.publisher.Flux;

Flux<Customer> customers = Flux.just(
    new Customer(null, "An", "an@example.com", true, null),
    new Customer(null, "Binh", "binh@example.com", true, null)
);

return customers.concatMap(customer ->
    template.insert(Customer.class).using(customer)
);
~~~

concatMap thực hiện tuần tự từng thao tác và giữ thứ tự phát kết quả. Nếu dùng flatMap, các thao tác có thể được thực hiện đồng thời tùy mức concurrency. Hãy chọn toán tử theo yêu cầu thứ tự, giới hạn tải và transaction của ứng dụng.

Đối với lô dữ liệu lớn, cân nhắc batch API hoặc cách import phù hợp với database và driver. Không nên tạo một publisher chứa toàn bộ dữ liệu không giới hạn trong bộ nhớ.

## 5. Select: truy vấn entity

Template hỗ trợ select bằng kiểu entity và điều kiện Query.

Ví dụ truy vấn tất cả khách hàng:

~~~java
Flux<Customer> allCustomers =
    template.select(Customer.class)
        .all();
~~~

Truy vấn theo điều kiện:

~~~java
import org.springframework.data.relational.core.query.Criteria;
import org.springframework.data.relational.core.query.Query;

Query query = Query.query(
    Criteria.where("active").is(true)
);

Flux<Customer> activeCustomers =
    template.select(Customer.class)
        .matching(query)
        .all();
~~~

Criteria.where("active") tham chiếu property trong entity. Mapping context và naming strategy sẽ giúp chuyển property thành tên cột tương ứng khi tạo SQL.

### 5.1. Query và Criteria

Query mô tả điều kiện, sắp xếp và giới hạn kết quả. Criteria mô tả biểu thức điều kiện.

Một số phép so sánh thường dùng:

| Biểu thức Criteria | Ý nghĩa |
|---|---|
| is(value) | Bằng giá trị |
| isNull() | Giá trị là NULL |
| isNotNull() | Giá trị không NULL |
| greaterThan(value) | Lớn hơn |
| greaterThanOrEquals(value) | Lớn hơn hoặc bằng |
| lessThan(value) | Nhỏ hơn |
| lessThanOrEquals(value) | Nhỏ hơn hoặc bằng |
| in(values) | Thuộc tập giá trị |
| like(pattern) | Khớp mẫu LIKE |
| not(value) | Phủ định điều kiện |

Ví dụ kết hợp điều kiện:

~~~java
Query query = Query.query(
    Criteria.where("active").is(true)
        .and("email").like("%@example.com")
);
~~~

Có thể dùng các điều kiện so sánh để xây dựng truy vấn theo yêu cầu nghiệp vụ. Khi kết hợp nhiều biểu thức AND/OR, hãy kiểm tra cách nhóm điều kiện để SQL sinh ra đúng logic mong muốn.

### 5.2. Sắp xếp và giới hạn kết quả

Query có thể kết hợp Sort, limit và offset:

~~~java
import org.springframework.data.domain.Sort;
import org.springframework.data.relational.core.query.Criteria;
import org.springframework.data.relational.core.query.Query;

Query query = Query.query(
        Criteria.where("active").is(true)
    )
    .sort(Sort.by(Sort.Direction.DESC, "fullName"))
    .limit(20)
    .offset(0);

Flux<Customer> customers =
    template.select(Customer.class)
        .matching(query)
        .all();
~~~

Khi dùng Sort, tham chiếu property của entity. Cần chọn thứ tự ổn định khi phân trang; nếu chỉ sort theo cột có giá trị trùng nhau, các trang có thể không ổn định khi dữ liệu thay đổi. Có thể bổ sung khóa định danh làm tiêu chí sắp xếp phụ.

### 5.3. Lấy một kết quả

Nếu chỉ cần một entity, có thể dùng fluent API với one():

~~~java
Query query = Query.query(
    Criteria.where("email").is("an@example.com")
);

Mono<Customer> customer =
    template.select(Customer.class)
        .matching(query)
        .one();
~~~

one() phù hợp khi truy vấn dự kiến có tối đa một kết quả. Nếu điều kiện có thể khớp nhiều bản ghi và nghiệp vụ chỉ muốn lấy bản ghi đầu tiên, hãy chọn API first() hoặc truy vấn có sort/limit rõ ràng theo phiên bản đang dùng. Không dựa vào thứ tự database không cam kết.

### 5.4. Đếm và kiểm tra sự tồn tại

Khi chỉ cần số lượng hoặc câu trả lời có/không, nên dùng API count/exists của template thay vì tải toàn bộ entity về bộ nhớ rồi đếm.

~~~java
Mono<Long> countActive =
    template.count(
        Query.query(Criteria.where("active").is(true)),
        Customer.class
    );

Mono<Boolean> hasCustomer =
    template.exists(
        Query.query(Criteria.where("email").is("an@example.com")),
        Customer.class
    );
~~~

Các phương thức này để tầng truy cập dữ liệu thực hiện thao tác tương ứng với database. Hãy kiểm tra chữ ký API của phiên bản Spring Data R2DBC trong dự án nếu đang dùng phiên bản cũ.

## 6. Update: cập nhật dữ liệu

Có hai tình huống thường gặp:

1. Cập nhật entity theo ID hoặc theo cơ chế persistence của entity.
2. Cập nhật một tập cột theo điều kiện Query.

Khi muốn cập nhật một số cột cho các hàng thỏa điều kiện, có thể dùng Update và Query.

~~~java
import org.springframework.data.relational.core.query.Criteria;
import org.springframework.data.relational.core.query.Query;
import org.springframework.data.relational.core.query.Update;

Query query = Query.query(
    Criteria.where("email").is("an@example.com")
);

Update update = Update.update("active", false);

Mono<Long> changedRows =
    template.update(Customer.class)
        .matching(query)
        .apply(update);
~~~

Kết quả là số hàng được cập nhật. Update.update chỉ định giá trị cho một property/cột. Có thể nối thêm các thay đổi khác bằng API Update của phiên bản Spring Data đang dùng.

Ví dụ cập nhật nhiều thuộc tính:

~~~java
Update update = Update.update("active", false)
    .set("fullName", "Nguyen An (inactive)");
~~~

Query xác định hàng nào bị tác động; Update xác định giá trị cần ghi. Điều kiện phải đủ chặt để tránh cập nhật nhầm nhiều bản ghi.

### 6.1. Update theo entity và optimistic locking

Khi cập nhật entity có @Version, Spring Data có thể dùng version để phát hiện ghi đè dữ liệu từ một phiên bản cũ. Với entity được đọc trước đó, hãy giữ version hiện tại và để cơ chế mapping/persistence xử lý optimistic locking.

Nếu sử dụng update theo Query để sửa trực tiếp nhiều cột, cần hiểu cách thao tác đó tương tác với version. Một câu update thủ công không nhất thiết tự động có cùng ngữ nghĩa optimistic locking như thao tác save/update entity. Nếu nghiệp vụ cần bảo vệ concurrency, hãy đưa version vào điều kiện hoặc dùng thao tác entity có hỗ trợ version theo API phù hợp.

### 6.2. Phân biệt update và upsert

Update không có nghĩa là insert nếu không tìm thấy bản ghi. Nếu điều kiện không khớp hàng nào, kết quả thường là số hàng thay đổi bằng 0. Upsert là hành vi riêng phụ thuộc cú pháp và khả năng của database; không nên giả định template.update() tự động tạo bản ghi mới.

## 7. Delete: xóa entity

Có thể xóa theo điều kiện Query:

~~~java
Query query = Query.query(
    Criteria.where("active").is(false)
);

Mono<Long> deletedRows =
    template.delete(Customer.class)
        .matching(query)
        .all();
~~~

Kết quả cho biết số hàng bị xóa. Trước khi dùng điều kiện rộng, hãy xác định phạm vi dữ liệu cần xóa và có thể kiểm tra số hàng dự kiến bị tác động trong quy trình nghiệp vụ.

Xóa theo ID có thể biểu diễn bằng Criteria:

~~~java
Query query = Query.query(
    Criteria.where("id").is(customerId)
);

Mono<Long> deleted =
    template.delete(Customer.class)
        .matching(query)
        .all();
~~~

Nếu thao tác xóa phải phối hợp với các cập nhật khác, hãy đặt chúng trong cùng transaction reactive khi dùng chung transaction manager và ConnectionFactory.

## 8. Fluent API và cách đọc chuỗi thao tác

R2dbcEntityTemplate cung cấp fluent API để thể hiện thứ tự thao tác một cách rõ ràng.

Ví dụ select:

~~~java
template.select(Customer.class)
    .matching(query)
    .all();
~~~

Có thể đọc theo thứ tự:

1. select dữ liệu thành Customer.
2. Áp dụng điều kiện Query.
3. Phát tất cả kết quả dưới dạng Flux<Customer>.

Ví dụ insert:

~~~java
template.insert(Customer.class)
    .using(customer);
~~~

Đọc theo thứ tự:

1. Chọn kiểu entity Customer.
2. Cung cấp instance cần insert.
3. Nhận Mono<Customer> chứa entity được lưu.

Ví dụ update:

~~~java
template.update(Customer.class)
    .matching(query)
    .apply(update);
~~~

Đọc theo thứ tự:

1. Chọn kiểu entity và bảng tương ứng.
2. Chọn những hàng thỏa Query.
3. Áp dụng các thay đổi trong Update.
4. Nhận số hàng được cập nhật.

Fluent API giúp tách rõ kiểu entity, điều kiện và dữ liệu thay đổi. Nó cũng giảm việc phải tự quản lý Row hoặc viết SQL cho những thao tác entity thông thường.

## 9. Mapping, conversion và tên property

R2dbcEntityTemplate sử dụng hạ tầng mapping chung của Spring Data Relational:

- RelationalMappingContext cung cấp metadata entity và property.
- R2dbcConverter chuyển đổi giữa entity và dữ liệu R2DBC.
- R2dbcCustomConversions bổ sung conversion cho kiểu domain riêng.
- R2dbcDialect cung cấp quy tắc SQL phụ thuộc hệ quản trị.
- ReactiveDataAccessStrategy phối hợp các thành phần này cho thao tác truy cập dữ liệu.

Ví dụ entity có cột tên snake_case:

~~~java
@Table("customer")
public record Customer(
    @Id Long id,
    @Column("full_name") String fullName
) {}
~~~

Trong Query và Criteria, thường sử dụng property Java là fullName. Mapping strategy sẽ chuyển property đó sang cột full_name theo metadata. Không nên tự ghép tên cột theo một quy tắc khác với mapping context.

### 9.1. Custom conversions

Nếu entity có kiểu domain riêng, hãy đăng ký converter trong cấu hình Spring Data R2DBC. Template dùng chung converter đã cấu hình, nên các thao tác insert/select/update có thể tận dụng quy tắc chuyển đổi đó.

Ví dụ một kiểu Money cần chuyển thành kiểu database hỗ trợ. Converter phải được đăng ký theo đúng chiều đọc và ghi. Nếu driver không hỗ trợ kiểu Java đích, cần kiểm tra codec/type support của driver; custom converter Spring Data không tự bổ sung khả năng giao thức cho driver.

### 9.2. Projection và kết quả tùy chỉnh

Template phù hợp nhất khi ứng dụng muốn làm việc với entity đã có mapping. Nếu truy vấn trả về một phần cột hoặc một cấu trúc báo cáo khác entity, có thể dùng projection hoặc DatabaseClient với mapping callback tùy theo độ phức tạp và API phiên bản.

Không nên cố dựng một entity đầy đủ từ tập cột thiếu nếu constructor của entity cần các property khác. Với báo cáo, DTO/record riêng thường thể hiện chính xác cấu trúc kết quả hơn.

## 10. Kết hợp R2dbcEntityTemplate với transaction

Template thực hiện thao tác reactive. Khi nhiều thao tác phải thành công hoặc rollback cùng nhau, cần sử dụng reactive transaction manager tương ứng với ConnectionFactory.

Có thể dùng @Transactional trên service method trả về Mono hoặc Flux:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import reactor.core.publisher.Mono;

@Service
public class CustomerRegistrationService {

    private final R2dbcEntityTemplate template;

    public CustomerRegistrationService(R2dbcEntityTemplate template) {
        this.template = template;
    }

    @Transactional
    public Mono<Customer> register(Customer customer) {
        return template.insert(Customer.class)
            .using(customer);
    }
}
~~~

Với nhiều thao tác, có thể nối các publisher trong cùng phương thức transactional:

~~~java
@Transactional
public Mono<Customer> registerWithAudit(Customer customer) {
    return template.insert(Customer.class)
        .using(customer)
        .flatMap(saved ->
            template.insert(AuditEntry.class)
                .using(AuditEntry.createdFor(saved.id()))
                .thenReturn(saved)
        );
}
~~~

Ví dụ giả định AuditEntry là entity được mapping hợp lệ và cùng template/transaction manager sử dụng một ConnectionFactory. Nếu hai thao tác dùng hai ConnectionFactory hoặc transaction manager khác nhau, không thể mặc định chúng tham gia cùng một transaction cục bộ.

Trong reactive transaction, transaction context được truyền qua chuỗi reactive. Hãy trả về publisher từ phương thức và không gọi block() hoặc subscribe() bên trong để tách thao tác ra khỏi ngữ cảnh transaction.

Có thể dùng TransactionalOperator khi muốn điều khiển transaction bằng chương trình. Dù dùng @Transactional hay TransactionalOperator, cần cấu hình đúng R2dbcTransactionManager.

## 11. Kết hợp template với Repository và DatabaseClient

Một ứng dụng không bắt buộc chỉ chọn một API.

| API | Nên dùng khi | Mức kiểm soát |
|---|---|---|
| ReactiveCrudRepository | CRUD phổ biến, truy vấn theo phương thức, query khai báo | Cao về abstraction, ít SQL trực tiếp |
| R2dbcEntityTemplate | Truy vấn entity động, thao tác CRUD linh hoạt với mapping Spring Data | Trung bình |
| DatabaseClient | SQL phức tạp, join/CTE, projection tùy chỉnh, cần kiểm soát câu lệnh | Trực tiếp ở mức SQL |

Ví dụ một service có thể dùng repository cho thao tác đơn giản và template cho bộ lọc động:

~~~java
public class CustomerQueryService {

    private final CustomerRepository repository;
    private final R2dbcEntityTemplate template;

    public CustomerQueryService(
            CustomerRepository repository,
            R2dbcEntityTemplate template) {
        this.repository = repository;
        this.template = template;
    }

    public Mono<Customer> findById(Long id) {
        return repository.findById(id);
    }

    public Flux<Customer> findActiveByEmailDomain(String domain) {
        Query query = Query.query(
            Criteria.where("active").is(true)
                .and("email").like("%@" + domain)
        );

        return template.select(Customer.class)
            .matching(query)
            .all();
    }
}
~~~

Nếu domain là dữ liệu đầu vào bên ngoài, hãy kiểm tra và chuẩn hóa nó trước khi tạo pattern LIKE. Criteria bind giá trị như tham số, nhưng ký tự wildcard trong pattern vẫn có ý nghĩa đối với LIKE và cần được xử lý theo yêu cầu nghiệp vụ.

Khi SQL phức tạp đến mức phải kiểm soát join, alias, CTE hoặc hàm riêng của database, DatabaseClient có thể rõ ràng hơn. Template không phải lý do để ép mọi truy vấn phải biểu diễn thành entity CRUD.

## 12. Phân trang và truy vấn động

Một lợi ích của Query là có thể xây dựng điều kiện theo dữ liệu đầu vào.

Ví dụ tạo bộ lọc có điều kiện:

~~~java
Criteria criteria = Criteria.where("active").is(true);

if (emailDomain != null && !emailDomain.isBlank()) {
    criteria = criteria.and("email").like("%@" + emailDomain);
}

Query query = Query.query(criteria)
    .sort(Sort.by(Sort.Direction.ASC, "fullName"))
    .limit(pageSize)
    .offset((long) page * pageSize);

return template.select(Customer.class)
    .matching(query)
    .all();
~~~

Đây là mẫu khái niệm cho bộ lọc tùy chọn. Khi triển khai, cần xác thực page/pageSize, giới hạn pageSize tối đa và bảo đảm điều kiện sort chỉ dùng property được cho phép. Không nhận tên cột hoặc tên property tùy ý từ client rồi chuyển thẳng vào truy vấn.

Offset pagination dễ sử dụng nhưng có thể tốn kém khi offset rất lớn. Với tập dữ liệu lớn và thay đổi thường xuyên, có thể cân nhắc keyset pagination hoặc truy vấn theo khóa tiếp tục, tùy yêu cầu và khả năng database.

## 13. Kiểm thử lớp sử dụng R2dbcEntityTemplate

Có thể kiểm thử service sử dụng template bằng cách kiểm thử tích hợp với database R2DBC tương thích, thường dùng H2 cho các tình huống đơn giản hoặc Testcontainers với hệ quản trị gần production hơn.

Các tình huống nên được kiểm tra trong dự án:

- Insert trả về entity có ID đúng.
- Select theo Criteria trả về đúng tập dữ liệu.
- Sort, limit và offset tạo thứ tự/kết quả mong muốn.
- Update chỉ tác động những hàng thỏa điều kiện.
- Delete trả về số hàng bị xóa đúng.
- @Version phát hiện cập nhật cạnh tranh nếu được cấu hình.
- Custom conversion hoạt động ở cả chiều đọc và ghi.
- Transaction rollback khi một thao tác trong chuỗi publisher phát sinh lỗi.

Khi dùng database nhúng cho test, cần nhớ dialect và kiểu dữ liệu có thể khác production. Một test H2 thành công không chứng minh SQL đặc thù PostgreSQL hoặc MySQL sẽ hoạt động giống hệt. Với hành vi phụ thuộc database, hãy có kiểm thử tích hợp trên đúng hệ quản trị mục tiêu.

## 14. Những lỗi thường gặp

### 14.1. Không có bean R2dbcEntityTemplate

Nguyên nhân thường là thiếu starter/dependency, thiếu driver, thiếu cấu hình ConnectionFactory hoặc auto-configuration đã bị thay thế bởi cấu hình tùy chỉnh.

Cách xử lý: kiểm tra runtime classpath, URL, bean ConnectionFactory và điều kiện auto-configuration của phiên bản Spring Boot đang dùng.

### 14.2. Query không tìm thấy property

Criteria thường tham chiếu property Java của entity. Nếu dùng tên cột SQL thay cho property hoặc viết sai tên property, mapping có thể không tạo SQL như mong đợi.

Cách xử lý: đối chiếu tên property, @Column và NamingStrategy. Giữ tên property nhất quán trong Query.

### 14.3. Insert không trả về ID như mong đợi

Nguyên nhân có thể là schema không cấu hình sinh ID, kiểu ID không tương thích hoặc code bỏ qua entity được phát ra từ insert.

Cách xử lý: kiểm tra kiểu khóa và cấu hình database; tiếp tục dùng giá trị trả về từ Mono của thao tác insert.

### 14.4. Update không tác động hàng nào

Điều kiện Query có thể không khớp dữ liệu hoặc tham chiếu sai property. Update trả về số hàng bị thay đổi, vì vậy hãy kiểm tra giá trị đó nếu nghiệp vụ cần xác nhận thao tác thành công.

### 14.5. Truy vấn trả về dữ liệu thiếu

Nếu truy vấn chỉ chọn một số cột nhưng ánh xạ sang entity có constructor yêu cầu nhiều property, quá trình tạo entity có thể thất bại hoặc nhận giá trị thiếu.

Cách xử lý: select đủ cột hoặc ánh xạ sang DTO/projection phù hợp.

### 14.6. Transaction không bao trùm tất cả thao tác

Nguyên nhân có thể là gọi subscribe()/block() bên trong service, dùng ConnectionFactory khác nhau hoặc thiếu transaction manager phù hợp.

Cách xử lý: giữ các thao tác trong cùng chuỗi publisher, dùng cùng cấu hình kết nối và xác nhận reactive transaction manager.

### 14.7. Mong đợi lazy loading hoặc join tự động

R2dbcEntityTemplate là API entity mapping, không biến Spring Data R2DBC thành ORM tự động tải mọi quan hệ. Hãy thiết kế aggregate và viết truy vấn cần thiết; với join/projection phức tạp, dùng DatabaseClient khi phù hợp.

## 15. Nguyên tắc sử dụng trong ứng dụng

- Inject một R2dbcEntityTemplate được Spring quản lý thay vì tạo mới trong từng request.
- Dùng Query và Criteria để xây dựng điều kiện; tham chiếu property Java nhất quán với mapping.
- Dùng fluent API để biểu diễn rõ kiểu entity, điều kiện và thao tác.
- Luôn dùng entity được phát ra từ insert/save khi cần ID hoặc version mới.
- Kiểm tra số hàng trả về từ update/delete nếu nghiệp vụ cần xác nhận tác động.
- Dùng @Version và cơ chế optimistic locking khi nhiều thao tác có thể cập nhật cùng dữ liệu.
- Dùng custom conversions đã đăng ký cho kiểu domain riêng.
- Dùng DatabaseClient khi cần SQL trực tiếp và projection phức tạp.
- Giữ các thao tác cần transaction trong cùng reactive context và cùng ConnectionFactory.
- Tránh block()/subscribe() tùy tiện trong service reactive.
- Giới hạn page size, kiểm soát sort property và xác thực dữ liệu đầu vào khi xây dựng Query động.
- Kiểm thử trên hệ quản trị tương thích với production đối với hành vi phụ thuộc dialect.

## 16. Ghi nhớ

R2dbcEntityTemplate cung cấp cách thao tác dữ liệu ở mức entity mà vẫn giữ mapping và conversion của Spring Data R2DBC. Template hỗ trợ insert, select, update và delete; Query/Criteria giúp xây dựng điều kiện động; fluent API làm rõ thứ tự thao tác; transaction reactive giúp phối hợp nhiều thao tác thành một đơn vị công việc.

Hãy chọn repository khi CRUD và truy vấn nghiệp vụ phổ biến đã đủ; chọn R2dbcEntityTemplate khi cần linh hoạt hơn ở mức entity; chọn DatabaseClient khi cần kiểm soát SQL trực tiếp. Dù chọn API nào, ConnectionFactory, driver, dialect và mapping configuration phải tương thích với nhau để thao tác dữ liệu hoạt động đúng.

