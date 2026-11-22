# Tạo truy vấn bằng DatabaseClient.sql

Spring Data R2DBC cung cấp repository abstraction cho các thao tác CRUD phổ biến. Khi cần viết SQL tường minh, join phức tạp, projection riêng, truy vấn database-specific hoặc kiểm soát chính xác câu lệnh, ứng dụng có thể dùng **DatabaseClient** của Spring Framework.

DatabaseClient cung cấp API fluent để tạo câu SQL, bind giá trị, thực thi statement và map kết quả về Java object. API trả về Mono hoặc Flux, vì vậy có thể kết hợp trực tiếp với service và controller reactive. Phần quan trọng là giữ đúng ranh giới giữa SQL template và dữ liệu đầu vào: bind value bằng parameter, còn identifier hoặc fragment động phải được kiểm soát theo allowlist.

## 1. DatabaseClient dùng khi nào?

DatabaseClient nằm ở tầng truy cập dữ liệu thấp hơn repository. Nó phù hợp khi:

- Cần viết câu SQL tùy chỉnh mà derived query không diễn đạt rõ.
- Cần join nhiều bảng và map thành DTO/read model.
- Cần dùng CTE, window function, JSON operator hoặc tính năng riêng của database.
- Cần kiểm soát projection và alias của cột.
- Cần chạy câu UPDATE/DELETE và nhận số hàng bị ảnh hưởng.
- Cần tích hợp SQL thủ công với reactive transaction do Spring quản lý.

Repository vẫn là lựa chọn tốt cho CRUD và query method thông thường. R2dbcEntityTemplate hữu ích khi muốn thao tác theo entity và query criteria. DatabaseClient phù hợp khi câu SQL là trung tâm của thao tác.

| API | Mức trừu tượng | Phù hợp với |
|---|---|---|
| ReactiveCrudRepository | Cao | CRUD và query method theo entity |
| R2dbcEntityTemplate | Trung bình | Entity operations, Criteria, mapping |
| DatabaseClient | Thấp hơn | SQL tường minh, join, projection và database-specific query |
| R2DBC SPI Connection/Statement | Thấp nhất | Kiểm soát connection/statement trực tiếp khi API cao hơn không đáp ứng |

DatabaseClient vẫn dùng R2DBC SPI bên dưới. Nó không biến SQL thành portable giữa mọi database; câu SQL viết tay vẫn phải tuân theo dialect của server đang kết nối.

## 2. DatabaseClient được tạo từ ConnectionFactory

DatabaseClient cần một ConnectionFactory để mở connection tới database. Trong ứng dụng Spring Boot có R2DBC starter và một ConnectionFactory mặc định, auto-configuration thường cung cấp DatabaseClient để inject. Hành vi cụ thể phụ thuộc phiên bản Boot và cấu hình bean của ứng dụng.

Nếu tự cấu hình, có thể tạo bean:

~~~java
import io.r2dbc.spi.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.r2dbc.core.DatabaseClient;

@Configuration
class DatabaseClientConfiguration {

    @Bean
    DatabaseClient databaseClient(ConnectionFactory connectionFactory) {
        return DatabaseClient.create(connectionFactory);
    }
}
~~~

Service inject DatabaseClient:

~~~java
@Service
public class CustomerQueryService {

    private final DatabaseClient databaseClient;

    public CustomerQueryService(DatabaseClient databaseClient) {
        this.databaseClient = databaseClient;
    }
}
~~~

DatabaseClient được thiết kế để dùng chung như một bean. Không tạo ConnectionFactory hoặc DatabaseClient mới cho từng request. Connection lifecycle được quản lý bởi client, ConnectionFactory và transaction infrastructure của Spring.

### 2.1. Khi có nhiều ConnectionFactory

Nếu ứng dụng có nhiều database, tạo một DatabaseClient cho từng ConnectionFactory và đặt tên bean rõ ràng:

~~~java
@Configuration
class MultiDatabaseClientConfiguration {

    @Bean("ordersDatabaseClient")
    DatabaseClient ordersDatabaseClient(
            @Qualifier("ordersConnectionFactory")
            ConnectionFactory connectionFactory) {
        return DatabaseClient.create(connectionFactory);
    }

    @Bean("billingDatabaseClient")
    DatabaseClient billingDatabaseClient(
            @Qualifier("billingConnectionFactory")
            ConnectionFactory connectionFactory) {
        return DatabaseClient.create(connectionFactory);
    }
}
~~~

Service phải inject đúng client:

~~~java
public BillingQueryService(
        @Qualifier("billingDatabaseClient")
        DatabaseClient databaseClient) {
    this.databaseClient = databaseClient;
}
~~~

DatabaseClient gắn với ConnectionFactory đã truyền vào lúc tạo. Một client của Orders không tự chạy truy vấn trên Billing chỉ vì SQL có nhắc đến schema hoặc tên database khác.

## 3. Cấu trúc fluent API

Một truy vấn DatabaseClient thường có các bước:

1. Gọi sql(...) với SQL template.
2. Bind parameter bằng bind(...) hoặc bindNull(...).
3. Chọn cách map row nếu cần.
4. Chọn cách lấy kết quả: one(), first(), all() hoặc rowsUpdated().
5. Kết hợp publisher trong reactive chain.

Mẫu tổng quát:

~~~java
databaseClient.sql("""
        SELECT id, email
        FROM customer
        WHERE id = :id
        """)
    .bind("id", customerId)
    .map((row, metadata) -> /* chuyển Row thành object */)
    .one();
~~~

Các method tạo thành một pipeline. Publisher thường lazy; câu SQL được thực thi khi có subscriber tiêu thụ kết quả. Vì vậy, chỉ tạo publisher không có nghĩa truy vấn đã chạy.

Không gọi subscribe() bên trong service để tự khởi chạy một nhánh độc lập. Hãy trả Mono/Flux cho caller hoặc nối publisher với flatMap, map, then và các operator phù hợp.

## 4. Named parameter và bind giá trị

DatabaseClient hỗ trợ named parameter trong SQL template. Viết marker dạng :parameterName và truyền tên không có dấu hai chấm vào bind.

Ví dụ:

~~~java
public Mono<Customer> findByEmail(String email) {
    return databaseClient.sql("""
            SELECT id, email, display_name
            FROM customer
            WHERE email = :email
            """)
        .bind("email", email)
        .map((row, metadata) -> new Customer(
            row.get("id", Long.class),
            row.get("email", String.class),
            row.get("display_name", String.class)
        ))
        .one();
}
~~~

Trong ví dụ:

- :email là named marker trong SQL.
- bind("email", email) cung cấp giá trị cho marker.
- DatabaseClient chuyển named parameter sang bind marker mà dialect/driver cần.
- .one() trả Mono<Customer> vì thao tác mong đợi tối đa một hàng.

Tên parameter phải khớp chính xác. Nếu SQL có :customerId nhưng code bind "id", statement sẽ thiếu binding.

### 4.1. Không nối giá trị đầu vào vào SQL

Không làm như sau:

~~~java
String sql = "SELECT id, email FROM customer WHERE email = '"
    + email
    + "'";
~~~

Nếu email chứa ký tự SQL đặc biệt, cấu trúc câu lệnh có thể bị thay đổi. Dùng bind parameter:

~~~java
databaseClient.sql("""
        SELECT id, email
        FROM customer
        WHERE email = :email
        """)
    .bind("email", email)
    .fetch()
    .all();
~~~

Database nhận email như một giá trị dữ liệu. Bind parameter là lớp bảo vệ chính cho value input và giúp driver truyền kiểu dữ liệu đúng.

### 4.2. Parameter chỉ thay thế value

Không thể dùng bind parameter để thay:

- Tên table hoặc schema.
- Tên column hoặc alias.
- ASC/DESC.
- Operator hoặc keyword.
- Một đoạn WHERE, JOIN hay ORDER BY tùy ý.

Ví dụ ORDER BY :sortColumn không chọn cột theo tên được gửi vào. Database xem sortColumn là một value expression.

Nếu cần sort động, hãy ánh xạ lựa chọn từ request sang một tập identifier cố định do ứng dụng kiểm soát, sau đó mới ghép fragment hợp lệ vào SQL. Các value filter vẫn phải bind riêng.

## 5. Bind null bằng bindNull

Không truyền null vào bind(...). R2DBC cần biết kiểu Java của SQL NULL để driver có thể xác định kiểu parameter.

Ví dụ:

~~~java
public Mono<Integer> updateNickname(Long id, String nickname) {
    var spec = databaseClient.sql("""
            UPDATE customer
            SET nickname = :nickname
            WHERE id = :id
            """)
        .bind("id", id);

    if (nickname == null) {
        spec = spec.bindNull("nickname", String.class);
    } else {
        spec = spec.bind("nickname", nickname);
    }

    return spec.fetch().rowsUpdated();
}
~~~

bindNull("nickname", String.class) biểu diễn SQL NULL có kiểu String/VARCHAR phù hợp với cột nickname. Chọn Java type theo kiểu cột và mapping driver.

Phân biệt ba trường hợp:

- Parameter có giá trị: dùng bind.
- Parameter cần SQL NULL: dùng bindNull với Java type.
- SQL không có parameter đó: không bind.

Không bind parameter đã khai báo trong SQL thường dẫn tới lỗi khi execute. Không truyền parameter không có nghĩa là truyền SQL NULL.

### 5.1. NULL trong điều kiện WHERE

SQL dùng logic ba giá trị. Biểu thức nickname = NULL không trở thành TRUE cho hàng có nickname NULL. Nếu cần tìm giá trị null, dùng IS NULL:

~~~sql
SELECT id, email
FROM customer
WHERE nickname IS NULL
~~~

Nếu API có filter tùy chọn, tạo nhánh predicate tương ứng. Đừng dùng một parameter null rồi kỳ vọng phép so sánh bằng sẽ tìm các hàng null.

## 6. Bind theo index và marker native

DatabaseClient hỗ trợ named parameters để giảm phụ thuộc vào marker native của driver. Nếu dùng R2DBC SPI trực tiếp qua Connection.createStatement(...), cần viết marker theo driver và bind theo index.

Ví dụ PostgreSQL native:

~~~java
Statement statement = connection.createStatement("""
    SELECT id, email
    FROM customer
    WHERE email = $1
    """);

statement.bind(0, email);
~~~

Trong PostgreSQL, marker đầu tiên hiển thị là $1, nhưng API R2DBC SPI dùng index zero-based, nên gọi bind(0, ...).

Không nhầm hai cơ chế:

| Cách thực thi | Marker trong SQL | Cách bind |
|---|---|---|
| Spring DatabaseClient named parameter | :email | bind("email", value) |
| R2DBC SPI native PostgreSQL | $1 | bind(0, value) |
| R2DBC SPI driver dùng positional marker khác | Theo driver | Index theo thứ tự marker |

Nếu chuyển SQL từ DatabaseClient sang raw Statement, phải điều chỉnh marker và binding theo driver. Không copy nguyên SQL template named parameter sang Statement native.

## 7. Chọn one(), first(), all() và rowsUpdated()

DatabaseClient cung cấp nhiều cách tiêu thụ kết quả. Chọn theo cardinality và ý nghĩa thao tác.

| Phương thức | Kiểu trả về | Ý nghĩa |
|---|---|---|
| one() | Mono<T> | Tối đa một hàng; lỗi nếu có nhiều hàng |
| first() | Mono<T> | Lấy hàng đầu tiên nếu có |
| all() | Flux<T> | Phát tất cả hàng |
| rowsUpdated() | Mono<Integer> | Số hàng bị tác động bởi update/delete/insert tùy driver |

### 7.1. Dùng one() cho kết quả duy nhất

Ví dụ tìm theo primary key:

~~~java
public Mono<Customer> findById(Long id) {
    return databaseClient.sql("""
            SELECT id, email, display_name
            FROM customer
            WHERE id = :id
            """)
        .bind("id", id)
        .map(customerMapper)
        .one();
}
~~~

one() phù hợp khi điều kiện bảo đảm tối đa một hàng. Nếu SQL vô tình trả nhiều hàng, đây là tín hiệu lỗi thay vì âm thầm bỏ các hàng còn lại.

Nếu kết quả có thể có nhiều hàng, dùng all() hoặc giới hạn/sắp xếp rõ ràng trước khi dùng first().

### 7.2. Dùng first() khi chỉ cần hàng đầu

Ví dụ lấy bản ghi mới nhất:

~~~java
public Mono<Order> findLatestOrder(Long customerId) {
    return databaseClient.sql("""
            SELECT id, customer_id, created_at, total
            FROM purchase_order
            WHERE customer_id = :customerId
            ORDER BY created_at DESC, id DESC
            """)
        .bind("customerId", customerId)
        .map(orderMapper)
        .first();
}
~~~

ORDER BY cần xác định thứ tự rõ ràng. Nếu không có sort, “hàng đầu tiên” không có ý nghĩa ổn định giữa các lần chạy.

Nếu có thể, thêm giới hạn ở SQL theo cú pháp database để server chỉ phải trả phần dữ liệu cần thiết.

### 7.3. Dùng all() cho danh sách

~~~java
public Flux<Customer> findActiveCustomers() {
    return databaseClient.sql("""
            SELECT id, email, display_name
            FROM customer
            WHERE active = :active
            ORDER BY id
            """)
        .bind("active", true)
        .map(customerMapper)
        .all();
}
~~~

all() trả Flux<Customer>. Flux rỗng khi không có hàng và phát lỗi nếu query thất bại.

Không collectList() toàn bộ một bảng lớn chỉ để đổi Flux thành Mono<List<T>>. Với danh sách lớn, dùng pagination hoặc xử lý theo batch.

### 7.4. Dùng rowsUpdated() cho thao tác ghi

~~~java
public Mono<Integer> renameCustomer(Long id, String displayName) {
    return databaseClient.sql("""
            UPDATE customer
            SET display_name = :displayName
            WHERE id = :id
            """)
        .bind("displayName", displayName)
        .bind("id", id)
        .fetch()
        .rowsUpdated();
}
~~~

rowsUpdated() trả số hàng bị tác động theo thông tin driver cung cấp. Giá trị bằng 0 có thể có nghĩa ID không tồn tại hoặc điều kiện không khớp; service cần quyết định có chuyển thành not-found hay không.

Không giả định rowsUpdated() luôn là số hàng đã thay đổi giá trị. Một số database/driver báo số hàng matched, số hàng changed hoặc semantics khác. Xác nhận behavior theo driver và database.

## 8. Map Row thành Java object

DatabaseClient trả về Row và RowMetadata khi dùng map callback. Ứng dụng chuyển các cột thành DTO/entity phù hợp.

Ví dụ record:

~~~java
public record Customer(
    Long id,
    String email,
    String displayName
) {}
~~~

Mapper:

~~~java
private Customer mapCustomer(Row row, RowMetadata metadata) {
    return new Customer(
        row.get("id", Long.class),
        row.get("email", String.class),
        row.get("display_name", String.class)
    );
}
~~~

Dùng trong query:

~~~java
return databaseClient.sql("""
        SELECT id, email, display_name
        FROM customer
        WHERE id = :id
        """)
    .bind("id", id)
    .map(this::mapCustomer)
    .one();
~~~

Row.get(column, type) yêu cầu tên cột/alias và Java type phù hợp với driver. Với cột nullable, kết quả có thể là null; DTO phải cho phép null hoặc ứng dụng cần chuyển đổi sang kiểu biểu diễn phù hợp.

### 8.1. Alias cột trong JOIN

Khi join nhiều bảng có cột trùng tên như id, name hoặc created_at, luôn dùng alias rõ ràng:

~~~sql
SELECT
    c.id AS customer_id,
    c.email AS customer_email,
    o.id AS order_id,
    o.created_at AS order_created_at
FROM customer c
JOIN purchase_order o
  ON o.customer_id = c.id
WHERE c.id = :customerId
~~~

Mapper đọc theo alias:

~~~java
.map((row, metadata) -> new CustomerOrderView(
    row.get("customer_id", Long.class),
    row.get("customer_email", String.class),
    row.get("order_id", Long.class),
    row.get("order_created_at", LocalDateTime.class)
))
~~~

Alias giúp tránh nhầm cột và giảm phụ thuộc vào cách driver xử lý label trùng nhau.

### 8.2. Dùng RowMetadata khi cần kiểm tra metadata

RowMetadata có thể cung cấp thông tin về các cột trong result. Điều này hữu ích khi cần xử lý projection động hoặc kiểm tra metadata.

Thông thường, DTO mapping nên dùng tên alias đã biết. Không nên xây một mapper quá động nếu query có projection ổn định.

Không giữ Row hoặc RowMetadata để dùng sau khi callback hoàn tất. Hãy chuyển dữ liệu cần thiết thành object ngay trong mapper.

### 8.3. Kiểu dữ liệu và conversion

Không giả định mọi database trả cùng một Java type cho cùng một SQL type. UUID, JSON, array, numeric, timestamp, enum và kiểu riêng có thể khác theo driver.

Nếu cần converter hoặc codec, cấu hình theo driver và kiểm thử với database thật. Không ép mọi giá trị về String để né lỗi conversion vì có thể mất type semantics hoặc precision.

## 9. Truy vấn danh sách và pagination

DatabaseClient trả Flux khi dùng all(). Với endpoint danh sách, nên giới hạn dữ liệu ngay trong SQL.

Ví dụ PostgreSQL/MySQL:

~~~java
public Flux<Customer> findPage(int limit, int offset) {
    return databaseClient.sql("""
            SELECT id, email, display_name
            FROM customer
            ORDER BY id
            LIMIT :limit OFFSET :offset
            """)
        .bind("limit", limit)
        .bind("offset", offset)
        .map(customerMapper)
        .all();
}
~~~

Cú pháp LIMIT/OFFSET không portable cho mọi database. SQL Server thường dùng OFFSET/FETCH cùng ORDER BY. Hãy dùng dialect của server mục tiêu.

Validate limit và offset trước khi bind:

- limit phải lớn hơn 0.
- Giới hạn limit tối đa để tránh trả quá nhiều hàng.
- offset không âm và không vượt giới hạn nghiệp vụ.
- ORDER BY phải ổn định, thường thêm primary key làm tie-breaker.

### 9.1. Keyset pagination

Với bảng lớn, offset sâu có thể khiến database phải bỏ qua nhiều hàng. Keyset pagination dùng giá trị cuối của trang trước:

~~~sql
SELECT id, email, display_name
FROM customer
WHERE id > :lastSeenId
ORDER BY id
LIMIT :limit
~~~

Cách này phù hợp khi thứ tự dựa trên khóa tăng dần và có index phù hợp. Nếu sort theo nhiều cột, cursor cần chứa đầy đủ giá trị sort và điều kiện so sánh tương ứng.

## 10. Truy vấn với nhiều điều kiện tùy chọn

Một số search endpoint cho phép filter theo nhiều field. Có thể xây SQL từ các predicate cố định, nhưng cần giữ value parameter riêng.

Ví dụ minh họa với tên filter tùy chọn:

~~~java
public Flux<Customer> search(String email, Boolean active) {
    StringBuilder sql = new StringBuilder("""
        SELECT id, email, display_name
        FROM customer
        WHERE 1 = 1
        """);

    var bindings = new LinkedHashMap<String, Object>();

    if (email != null) {
        sql.append(" AND email = :email");
        bindings.put("email", email);
    }

    if (active != null) {
        sql.append(" AND active = :active");
        bindings.put("active", active);
    }

    sql.append(" ORDER BY id");

    var spec = databaseClient.sql(sql.toString());

    for (var entry : bindings.entrySet()) {
        spec = spec.bind(entry.getKey(), entry.getValue());
    }

    return spec.map(customerMapper).all();
}
~~~

Các phần được nối vào SQL ở đây là fragment cố định do ứng dụng viết. Email và active được bind riêng. Nếu filter có thể mang SQL NULL, cần dùng bindNull với type phù hợp thay vì bỏ qua parameter hoặc gọi bind với null.

### 10.1. Dynamic sort phải dùng allowlist

Không dùng:

~~~sql
ORDER BY :sortColumn
~~~

Thay vào đó, chuyển lựa chọn client sang identifier cố định:

~~~java
String orderBy = switch (sortField) {
    case "email" -> "email";
    case "createdAt" -> "created_at";
    case "displayName" -> "display_name";
    default -> throw new IllegalArgumentException(
        "Unsupported sort field"
    );
};
~~~

Sau đó ghép orderBy từ allowlist vào SQL. Direction cũng phải được kiểm tra và chuyển thành một trong hai literal ASC hoặc DESC. Không nối trực tiếp chuỗi do client gửi.

Bind parameter không thể thay tên bảng, tên cột, schema, operator hoặc keyword. Quote identifier cũng không thay thế kiểm tra allowlist.

## 11. Bind collection trong IN clause

DatabaseClient hỗ trợ named parameter expansion cho collection trong các trường hợp phù hợp, thường dùng với IN:

~~~java
public Flux<Customer> findByIds(Collection<Long> ids) {
    if (ids.isEmpty()) {
        return Flux.empty();
    }

    return databaseClient.sql("""
            SELECT id, email, display_name
            FROM customer
            WHERE id IN (:ids)
            """)
        .bind("ids", ids)
        .map(customerMapper)
        .all();
}
~~~

Spring có thể mở rộng collection thành nhiều marker. Tuy nhiên, cần xác nhận API/version và driver đang dùng; collection expansion khác với bind một SQL array native.

### 11.1. Xử lý collection rỗng

Không để query tạo IN () nếu cơ chế expansion không hỗ trợ danh sách rỗng. Xử lý trước khi tạo query và quyết định semantics:

- Danh sách rỗng nghĩa là không có kết quả: trả Flux.empty().
- Danh sách rỗng nghĩa là không áp dụng filter: bỏ predicate IN.
- Danh sách rỗng là input không hợp lệ: trả validation error.

Không tự chọn semantics ngầm vì có thể khiến endpoint trả toàn bộ dữ liệu khi caller mong đợi không có kết quả.

### 11.2. Giới hạn số phần tử

Collection quá lớn có thể tạo statement với hàng nghìn marker, tăng parse cost hoặc vượt giới hạn driver/database. Giới hạn kích thước, chia batch hoặc dùng cơ chế array/table parameter phù hợp với database.

## 12. Insert và generated values

DatabaseClient có thể chạy INSERT và map kết quả được database trả về. Cách lấy generated ID phụ thuộc database và driver.

Ví dụ PostgreSQL dùng RETURNING:

~~~java
public Mono<Long> insertCustomer(String email, String displayName) {
    return databaseClient.sql("""
            INSERT INTO customer (email, display_name)
            VALUES (:email, :displayName)
            RETURNING id
            """)
        .bind("email", email)
        .bind("displayName", displayName)
        .map((row, metadata) -> row.get("id", Long.class))
        .one();
}
~~~

RETURNING là cú pháp database-specific; PostgreSQL hỗ trợ, nhưng không được mặc định mọi database có cùng cú pháp. Với database/driver khác, kiểm tra API generated values phù hợp hoặc dùng R2dbcEntityTemplate/repository nếu abstraction đó đáp ứng nhu cầu.

Nếu cột nullable, dùng bindNull với Java type thay vì bind giá trị null.

## 13. Update và delete

Update:

~~~java
public Mono<Integer> updateEmail(Long id, String email) {
    return databaseClient.sql("""
            UPDATE customer
            SET email = :email
            WHERE id = :id
            """)
        .bind("email", email)
        .bind("id", id)
        .fetch()
        .rowsUpdated();
}
~~~

Delete:

~~~java
public Mono<Integer> deleteById(Long id) {
    return databaseClient.sql("""
            DELETE FROM customer
            WHERE id = :id
            """)
        .bind("id", id)
        .fetch()
        .rowsUpdated();
}
~~~

rowsUpdated() trả Mono<Integer>. Service có thể kiểm tra count:

~~~java
return deleteById(id)
    .flatMap(count -> {
        if (count == 0) {
            return Mono.error(new CustomerNotFoundException(id));
        }
        return Mono.empty();
    });
~~~

Đây là lựa chọn nghiệp vụ. Một số endpoint coi delete không tồn tại vẫn là thành công idempotent; khi đó count bằng 0 không nhất thiết là lỗi.

## 14. Dùng DatabaseClient trong reactive transaction

DatabaseClient tích hợp với Spring transaction infrastructure. Khi có reactive transaction gắn với cùng ConnectionFactory, các thao tác DatabaseClient trong reactive context có thể tham gia transaction đó.

Ví dụ:

~~~java
@Transactional
public Mono<Customer> createCustomer(
        String email,
        String displayName) {

    return databaseClient.sql("""
            INSERT INTO customer (email, display_name)
            VALUES (:email, :displayName)
            RETURNING id, email, display_name
            """)
        .bind("email", email)
        .bind("displayName", displayName)
        .map(customerMapper)
        .one()
        .flatMap(customer ->
            databaseClient.sql("""
                    INSERT INTO audit_log (entity_type, entity_id, action)
                    VALUES (:type, :id, :action)
                    """)
                .bind("type", "CUSTOMER")
                .bind("id", customer.id())
                .bind("action", "CREATED")
                .fetch()
                .rowsUpdated()
                .thenReturn(customer)
        );
}
~~~

Ví dụ RETURNING dành cho PostgreSQL. Nếu hai lệnh cùng dùng DatabaseClient gắn với một ConnectionFactory và cùng reactive transaction context, chúng có thể commit/rollback cùng nhau.

### 14.1. Giữ mọi thao tác trong một publisher chain

Reactive transaction dùng Reactor Context để truyền transaction resource. Vì vậy:

- Trả Mono/Flux từ phương thức transactional.
- Nối các thao tác bằng flatMap, then, zip hoặc operator phù hợp.
- Không gọi subscribe() bên trong phương thức.
- Không gọi block() để lấy kết quả giữa chừng.
- Không khởi chạy tác vụ fire-and-forget rồi mong nó tham gia transaction.

Nếu dùng nhiều ConnectionFactory, transaction manager của một nguồn không tự quản lý client của nguồn khác.

### 14.2. Chọn transaction manager khi có nhiều nguồn

Nếu có nhiều ReactiveTransactionManager, chỉ định đúng manager:

~~~java
@Transactional(transactionManager = "ordersTransactionManager")
public Mono<Order> createOrder(...) {
    // Query qua ordersDatabaseClient.
}
~~~

Đảm bảo client và transaction manager cùng trỏ tới ConnectionFactory tương ứng. Một annotation không tạo transaction phân tán xuyên nhiều database.

### 14.3. TransactionalOperator

Có thể dùng TransactionalOperator để bao quanh publisher:

~~~java
return transactionalOperator.transactional(
    databaseClient.sql("""
            UPDATE account
            SET status = :status
            WHERE id = :id
            """)
        .bind("status", "ACTIVE")
        .bind("id", accountId)
        .fetch()
        .rowsUpdated()
);
~~~

TransactionalOperator hữu ích khi transaction boundary cần được thể hiện ngay trong reactive chain hoặc được lựa chọn theo luồng xử lý.

## 15. Xử lý lỗi và exception translation

DatabaseClient dịch nhiều lỗi R2DBC thành hệ thống exception của Spring thuộc nhánh DataAccessException. Điều này giúp service xử lý lỗi theo abstraction của Spring thay vì phụ thuộc hoàn toàn vào exception class của từng driver.

Các nhóm lỗi thường gặp:

- Bad SQL grammar: cú pháp SQL hoặc tên object sai.
- Data integrity violation: unique, foreign key, not-null hoặc constraint.
- Type mismatch: bind hoặc conversion không phù hợp.
- Transient resource failure: network/database tạm thời không khả dụng.
- Connection/acquire timeout: pool không cấp được connection.
- Permission/authentication failure: user không có quyền hoặc credentials sai.

Không chuyển mọi DataAccessException thành “không tìm thấy”. Chỉ ánh xạ lỗi theo semantics đã biết. Lỗi syntax hoặc authentication không phải kết quả rỗng.

### 15.1. Giữ nguyên cause chain

Khi bọc lỗi thành exception domain, giữ cause:

~~~java
.onErrorMap(
    DataAccessException.class,
    error -> new CustomerPersistenceException(
        "Could not load customer",
        error
    )
)
~~~

Không làm mất SQLState/vendor code nếu cần hỗ trợ chẩn đoán.

### 15.2. Không log dữ liệu bind nhạy cảm

Log query name, datasource alias, duration, row count và error code đã làm sạch. Tránh log password, token, email cá nhân, thông tin thanh toán hoặc toàn bộ parameter values.

## 16. Tối ưu query và giới hạn tài nguyên

DatabaseClient cho phép viết SQL tường minh nhưng không tự bảo đảm query hiệu quả.

Cần chú ý:

- Chỉ select cột cần dùng thay vì SELECT *.
- Có index cho predicate và join key phù hợp.
- Dùng ORDER BY ổn định khi pagination.
- Giới hạn số hàng trả về.
- Tránh N+1 query khi map quan hệ.
- Không collectList() một tập dữ liệu không giới hạn.
- Đặt timeout ở tầng phù hợp.
- Kiểm tra query plan trên database thật.
- Theo dõi pool acquire latency và thời gian query.

### 16.1. Không giữ connection quá lâu

Một Flux được tiêu thụ chậm có thể giữ tài nguyên database lâu hơn dự kiến, tùy driver và cách fetch. Với export lớn, cân nhắc batch/keyset pagination hoặc job nền tạo file, thay vì giữ một truy vấn mở trong suốt thời gian client tải dữ liệu.

### 16.2. Không tạo N+1 query trong mapping

Không thực hiện query database bên trong mapper đồng bộ của từng row. Mapper nên chuyển Row thành object. Nếu cần load quan hệ, hãy tổ chức reactive pipeline có kiểm soát concurrency hoặc viết JOIN/projection phù hợp.

Ví dụ không nên gọi repository blocking trong map callback. Nếu cần một query cho mỗi customer, dùng flatMap/concatMap với concurrency được giới hạn; tốt hơn là cân nhắc một query join hoặc batch.

## 17. Kiểm thử DatabaseClient

Unit test có thể mock DatabaseClient để kiểm tra cách service phối hợp, nhưng mock không kiểm tra SQL parser, driver marker, type mapping hoặc transaction thực tế.

Nên có integration test trên database/driver mục tiêu, thường qua Testcontainers.

Các trường hợp nên kiểm tra:

- Named parameter được bind đúng.
- Missing parameter gây lỗi dễ chẩn đoán.
- SQL NULL dùng bindNull đúng type.
- Kết quả one() với 0, 1 và nhiều hàng.
- first() có ORDER BY ổn định.
- all() phát đủ hàng và hoàn tất.
- rowsUpdated() trả count đúng theo driver.
- UUID, JSON, decimal và temporal mapping.
- Collection expansion và collection rỗng.
- Identifier quote và schema qualification.
- Transaction commit/rollback khi nhiều query nối trong một chain.
- Cancellation và timeout giải phóng connection.
- SQL native có đúng dialect.
- SQL injection input được bind như value.

### 17.1. StepVerifier cho query một kết quả

~~~java
StepVerifier.create(queryService.findByEmail("test@example.com"))
    .expectNextMatches(customer ->
        customer.email().equals("test@example.com")
    )
    .verifyComplete();
~~~

### 17.2. StepVerifier cho danh sách

~~~java
StepVerifier.create(queryService.findActiveCustomers())
    .expectNextCount(2)
    .verifyComplete();
~~~

Dữ liệu fixture cần xác định rõ để test không phụ thuộc thứ tự mặc định của database. Nếu dùng all(), thêm ORDER BY trong SQL khi thứ tự là một phần của contract.

### 17.3. Kiểm thử transaction rollback

Tạo integration test thực hiện thao tác đầu tiên thành công rồi cố ý gây lỗi ở thao tác thứ hai trong cùng reactive transaction. Sau khi publisher kết thúc bằng lỗi, query lại database để xác nhận thao tác đầu tiên đã rollback.

Không dùng mock để kết luận transaction đã rollback; cần database và transaction manager thật.

## 18. Những lỗi thường gặp

**Dùng DatabaseClient nhưng quên bind parameter.** SQL có marker nhưng execute không có giá trị tương ứng. Đối chiếu từng marker với bind.

**Truyền tên bind có dấu hai chấm.** SQL dùng :email nhưng bind nên nhận "email", không phải ":email".

**Dùng marker native sai driver.** DatabaseClient named marker và raw Statement native marker là hai cơ chế khác nhau.

**Bind null bằng bind.** Dùng bindNull với Java type phù hợp.

**Dùng one() cho query có nhiều hàng.** one() biểu diễn tối đa một hàng và có thể báo lỗi khi nhiều hàng. Dùng all() hoặc giới hạn/sắp xếp phù hợp.

**Dùng first() mà không có ORDER BY.** Kết quả đầu không ổn định. Đặt thứ tự rõ ràng.

**Dùng rowsUpdated() như giá trị boolean.** Count có thể bằng 0 hoặc lớn hơn 1. Xác định semantics của thao tác.

**Nối value input vào SQL.** Dễ tạo SQL injection. Dùng bind.

**Bind tên cột hoặc sort direction.** Value parameter không thể thay identifier/keyword. Dùng allowlist.

**Quên xử lý collection rỗng trong IN.** Xử lý semantics của danh sách rỗng trước khi tạo query.

**Map cột trùng tên trong JOIN.** Dùng alias duy nhất và map theo alias.

**Giữ Row sau mapper callback.** Chuyển dữ liệu sang DTO ngay trong callback.

**Dùng DatabaseClient của sai datasource.** Qualifier client và transaction manager theo đúng ConnectionFactory.

**Gọi subscribe() hoặc block() trong service.** Có thể tách thao tác khỏi reactive chain và transaction context. Trả publisher cho caller.

**Chỉ test bằng H2 hoặc mock.** Cú pháp, type mapping và behavior driver có thể khác production. Test với database mục tiêu.

## 19. Nguyên tắc thiết kế

- Dùng repository cho CRUD/query đơn giản và DatabaseClient cho SQL tùy chỉnh cần kiểm soát rõ.
- Inject một DatabaseClient dùng chung, gắn với ConnectionFactory phù hợp.
- Dùng named parameter và bind value; không nối dữ liệu đầu vào vào SQL.
- Dùng bindNull với Java type rõ ràng.
- Chọn one(), first(), all() theo cardinality và thứ tự dữ liệu.
- Dùng rowsUpdated() cho thao tác ghi và diễn giải count theo semantics của driver.
- Alias cột rõ ràng trong JOIN/projection.
- Dùng Java type phù hợp với SQL type và kiểm tra driver conversion.
- Xử lý collection rỗng và giới hạn kích thước IN.
- Allowlist identifier và direction động; bind các value filter riêng.
- Giữ query theo dialect database thực tế.
- Kết hợp DatabaseClient với reactive transaction trong cùng publisher chain.
- Chọn transaction manager theo đúng ConnectionFactory.
- Không subscribe/block bên trong service.
- Giới hạn kết quả, concurrency và thời gian giữ connection.
- Kiểm thử SQL, mapping, transaction và driver bằng integration test trên database mục tiêu.
- Không log parameter values hoặc dữ liệu nhạy cảm.

## 20. Ghi nhớ

DatabaseClient.sql là điểm bắt đầu để xây dựng một truy vấn R2DBC tường minh. Từ SQL template, ứng dụng bind giá trị, map Row thành DTO/entity rồi chọn one(), first(), all() hoặc rowsUpdated() theo kết quả mong muốn. Named parameter giúp tách dữ liệu khỏi câu SQL và DatabaseClient chuyển marker phù hợp với driver.

Hãy dùng bindNull cho SQL NULL, alias rõ ràng khi join, xử lý collection rỗng và pagination có giới hạn. Identifier động không thể bind như value nên phải đến từ allowlist và tuân theo dialect. DatabaseClient có thể tham gia reactive transaction khi dùng cùng ConnectionFactory và transaction context; giữ các thao tác trong một publisher chain và kiểm thử bằng database/driver thật để bảo đảm SQL, mapping và transaction hoạt động như mong đợi.

