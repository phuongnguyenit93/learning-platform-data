# Phân biệt trách nhiệm của DatabaseClient với R2dbcEntityTemplate

## 1. Hai API phục vụ hai mức làm việc với database

Spring Data R2DBC cung cấp nhiều cách truy cập cơ sở dữ liệu. Hai thành phần thường được dùng trực tiếp là **DatabaseClient** và **R2dbcEntityTemplate**. Cả hai đều làm việc trên nền R2DBC, trả về publisher reactive và có thể sử dụng cùng một ConnectionFactory, nhưng chúng giải quyết hai loại công việc khác nhau.

- **DatabaseClient** là API thực thi SQL. Lập trình viên viết câu SQL, bind giá trị, đọc từng Row và quyết định cách ánh xạ kết quả.
- **R2dbcEntityTemplate** là API hướng entity của Spring Data Relational. Nó sử dụng mapping metadata, converter và dialect để tạo các thao tác insert, select, update, delete, count và exists theo kiểu entity.

Có thể hình dung mối quan hệ như sau:

~~~text
                    Application
                         |
             +-----------+-----------+
             |                       |
             v                       v
       DatabaseClient        R2dbcEntityTemplate
       SQL-oriented                 Entity-oriented
             |                       |
             |              +--------+---------+
             |              |                  |
             |              v                  v
             |       Mapping Context    R2dbcConverter
             |              |                  |
             +--------------+------------------+
                            |
                            v
                       ConnectionFactory
                            |
                            v
                         R2DBC Driver
                            |
                            v
                     Relational Database
~~~

R2dbcEntityTemplate sử dụng DatabaseClient ở bên dưới cùng mapping infrastructure của Spring Data. Vì vậy, đây không phải hai công nghệ kết nối database cạnh tranh nhau. Chúng là hai mức API trên cùng một nền tảng.

Khi cần kiểm soát SQL, JOIN, CTE, biểu thức database-specific hoặc một DTO tùy chỉnh, DatabaseClient thường phù hợp. Khi thao tác chủ yếu xoay quanh entity và muốn tận dụng mapping metadata, Criteria, Query và Update, R2dbcEntityTemplate thường thuận tiện hơn.

## 2. DatabaseClient chịu trách nhiệm gì?

DatabaseClient tập trung vào việc gửi SQL đến database và xử lý kết quả do R2DBC driver trả về. Nó không yêu cầu mỗi câu SQL phải tương ứng với một entity được ánh xạ.

Các trách nhiệm chính:

- Nhận câu SQL và các bind parameter.
- Chuyển named parameter sang dạng bind mà dialect/driver sử dụng.
- Thực thi câu lệnh thông qua ConnectionFactory.
- Cung cấp Row và RowMetadata cho callback đọc kết quả.
- Trả về các publisher cho result rows hoặc số hàng bị ảnh hưởng.
- Cho phép ánh xạ thủ công sang entity, DTO, record hoặc kiểu scalar.

Ví dụ truy vấn trực tiếp:

~~~java
Flux<CustomerSummary> customers =
        databaseClient.sql("""
                SELECT id, name, status
                FROM customers
                WHERE status = :status
                ORDER BY id
                """)
            .bind("status", "ACTIVE")
            .map((row, metadata) -> new CustomerSummary(
                    row.get("id", Long.class),
                    row.get("name", String.class),
                    row.get("status", String.class)
            ))
            .all();
~~~

Trong ví dụ này, lập trình viên quyết định:

- Bảng nào được truy vấn: customers.
- Cột nào được lấy: id, name, status.
- Điều kiện và thứ tự: WHERE, ORDER BY.
- Giá trị nào được bind: status.
- Kiểu kết quả: CustomerSummary.
- Cách chuyển từng Row thành object Java.

DatabaseClient không tự suy ra SELECT list từ CustomerSummary. Nó cũng không tự đọc annotation @Table trên DTO để viết lại câu SQL. Câu lệnh và cách ánh xạ kết quả là trách nhiệm của code sử dụng API.

### 2.1. Khi nào dùng DatabaseClient?

DatabaseClient phù hợp khi:

- Cần JOIN nhiều bảng để tạo read model hoặc báo cáo.
- Cần CTE, window function, subquery hoặc cú pháp đặc thù của database.
- Cần SQL rõ ràng để kiểm soát SELECT list, predicate, alias và execution semantics.
- Kết quả là DTO/projection không phải aggregate entity.
- Cần dùng DML với RETURNING hoặc tính năng riêng của database.
- Truy vấn quá đặc thù để diễn đạt thuận tiện bằng Criteria hoặc repository method.

DatabaseClient cũng phù hợp với các câu lệnh đơn giản. Tuy nhiên, nếu phải tự viết lại nhiều CRUD SQL giống nhau cho từng entity, mapping metadata và thao tác của template có thể giảm đáng kể phần code lặp.

## 3. R2dbcEntityTemplate chịu trách nhiệm gì?

R2dbcEntityTemplate là API hướng entity của Spring Data R2DBC. Nó triển khai abstraction **R2dbcEntityOperations** và kết hợp DatabaseClient với mapping context và converter.

Các trách nhiệm chính:

- Sử dụng kiểu entity để xác định bảng và metadata mapping.
- Ánh xạ property Java với cột database.
- Tôn trọng các annotation mapping như @Table, @Column, @Id và @Version.
- Chuyển đổi giá trị qua R2dbcConverter và custom conversions.
- Tạo các thao tác insert, select, update, delete, count và exists.
- Hỗ trợ Criteria, Query, Sort và Update để xây dựng điều kiện mà không cần tự viết toàn bộ SQL.
- Trả về entity hoặc scalar result theo API được chọn.

Ví dụ entity:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table("customers")
public record Customer(
        @Id Long id,
        String name,
        @Column("email_address") String email,
        String status
) {}
~~~

Entity khai báo bảng customers và ánh xạ property email sang cột email_address. Khi dùng template, ứng dụng truyền Customer.class; Spring Data sử dụng metadata này để tạo câu SQL phù hợp với dialect và ánh xạ kết quả.

### 3.1. Khi nào dùng R2dbcEntityTemplate?

R2dbcEntityTemplate phù hợp khi:

- Thao tác CRUD theo entity hoặc aggregate.
- Muốn dùng metadata @Table, @Column và naming strategy.
- Muốn tạo điều kiện bằng Criteria và Query.
- Muốn thực hiện update/delete có điều kiện và nhận số hàng bị ảnh hưởng.
- Muốn đọc entity với mapping và custom conversions đã cấu hình.
- Muốn kiểm soát truy vấn linh hoạt hơn repository nhưng vẫn giữ entity mapping.

Template không phải ORM đầy đủ như JPA/Hibernate. Nó không cung cấp persistence context, lazy-loading proxy hoặc dirty checking kiểu JPA. Ứng dụng vẫn chủ động đọc, thay đổi và lưu entity qua publisher reactive.

## 4. Cùng một thao tác đọc được viết theo hai cách

Giả sử cần tìm khách hàng theo trạng thái ACTIVE.

### 4.1. Dùng DatabaseClient

~~~java
public Flux<CustomerSummary> findActiveCustomers() {
    return databaseClient.sql("""
            SELECT id, name, status
            FROM customers
            WHERE status = :status
            ORDER BY id
            """)
        .bind("status", "ACTIVE")
        .map((row, metadata) -> new CustomerSummary(
                row.get("id", Long.class),
                row.get("name", String.class),
                row.get("status", String.class)
        ))
        .all();
}
~~~

Code khai báo đầy đủ SQL và row mapping. Kết quả chỉ có ba trường theo DTO CustomerSummary.

### 4.2. Dùng R2dbcEntityTemplate

~~~java
public Flux<Customer> findActiveCustomers() {
    Query query = Query.query(
            Criteria.where("status").is("ACTIVE")
    ).sort(Sort.by(Sort.Order.asc("id")));

    return template.select(query, Customer.class);
}
~~~

Template sử dụng Customer.class để xác định bảng, cột và cách chuyển đổi kết quả. Query mô tả điều kiện lọc và sort bằng property metadata.

Hai ví dụ không hoàn toàn giống nhau về kiểu kết quả: DatabaseClient trả CustomerSummary, còn template trả Customer. Có thể dùng projection/DTO ở các API phù hợp của Spring Data, nhưng khi cần một SQL read model đặc thù, DatabaseClient thường cho quyền kiểm soát trực tiếp hơn.

### 4.3. Khác biệt chính

| Khía cạnh | DatabaseClient | R2dbcEntityTemplate |
|---|---|---|
| Mức trừu tượng | SQL-oriented | Entity-oriented |
| Chọn bảng | Trong SQL | Từ target entity metadata |
| Chọn cột | SELECT list trong SQL | Mapping/query API và khả năng projection |
| Mapping | Callback hoặc row mapper do ứng dụng viết | R2dbcConverter và mapping metadata |
| Điều kiện | SQL và bind parameter | Criteria, Query |
| Tính năng database-specific | Truy cập trực tiếp qua SQL | Có thể dùng qua API SQL thấp hơn khi cần |
| Kết quả | Row, DTO, scalar hoặc kiểu tùy chỉnh | Thường là entity hoặc scalar theo thao tác |
| Phù hợp | JOIN, báo cáo, query đặc thù | CRUD và thao tác theo entity |

## 5. Insert: lưu entity hay thực thi SQL?

### 5.1. Insert bằng R2dbcEntityTemplate

~~~java
Customer input = new Customer(
        null,
        "An Nguyen",
        "an@example.test",
        "ACTIVE"
);

Mono<Customer> inserted =
        template.insert(Customer.class).using(input);
~~~

Template biết Customer được ánh xạ vào bảng customers. Nó sử dụng metadata và converter để tạo giá trị ghi. Nếu database sinh ID và driver/dialect hỗ trợ trả lại generated value, entity phát ra từ Mono có thể chứa ID mới.

Với entity immutable như record, hãy dùng entity được phát ra từ publisher; không giả định object đầu vào đã được mutate.

### 5.2. Insert bằng DatabaseClient

~~~java
Mono<CustomerSummary> inserted =
        databaseClient.sql("""
                INSERT INTO customers (name, email_address, status)
                VALUES (:name, :email, :status)
                RETURNING id, name, status
                """)
            .bind("name", "An Nguyen")
            .bind("email", "an@example.test")
            .bind("status", "ACTIVE")
            .map((row, metadata) -> new CustomerSummary(
                    row.get("id", Long.class),
                    row.get("name", String.class),
                    row.get("status", String.class)
            ))
            .one();
~~~

Ví dụ sử dụng cú pháp RETURNING của PostgreSQL. SQL chỉ định rõ cột được ghi và cột được trả lại. Nếu dùng database không hỗ trợ RETURNING theo cú pháp này, cần dùng cơ chế generated key hoặc câu lệnh phù hợp với database đó.

### 5.3. Chọn cách nào?

Dùng template khi muốn insert entity theo metadata và nhận entity sau lưu. Dùng DatabaseClient khi cần SQL đặc thù, cần trả DTO tùy chỉnh hoặc cần kiểm soát chính xác câu lệnh.

Không nên giả định hai cách có cùng hành vi về generated columns nếu SQL và driver khác nhau. Với DatabaseClient, chính câu SQL và API fetch/map quyết định kết quả được trả về. Với template, mapping infrastructure xử lý theo dialect và metadata.

## 6. Update và delete

### 6.1. Update bằng R2dbcEntityTemplate

~~~java
Query query = Query.query(Criteria.where("id").is(customerId));

Mono<Long> updated =
        template.update(Customer.class)
                .matching(query)
                .apply(Update.update("status", "INACTIVE"));
~~~

Template tạo thao tác update cho bảng được ánh xạ từ Customer. Criteria dùng property Java; Update chỉ định property cần cập nhật. Kết quả là số hàng bị ảnh hưởng.

### 6.2. Update bằng DatabaseClient

~~~java
Mono<Long> updated =
        databaseClient.sql("""
                UPDATE customers
                SET status = :status
                WHERE id = :id
                """)
            .bind("status", "INACTIVE")
            .bind("id", customerId)
            .fetch()
            .rowsUpdated();
~~~

Ở đây SQL hoàn toàn tường minh. DatabaseClient trả số hàng bị ảnh hưởng thông qua rowsUpdated().

### 6.3. Delete bằng R2dbcEntityTemplate

~~~java
Mono<Long> deleted =
        template.delete(Customer.class)
                .matching(Query.query(Criteria.where("id").is(customerId)))
                .all();
~~~

### 6.4. Delete bằng DatabaseClient

~~~java
Mono<Long> deleted =
        databaseClient.sql("""
                DELETE FROM customers
                WHERE id = :id
                """)
            .bind("id", customerId)
            .fetch()
            .rowsUpdated();
~~~

Template hữu ích khi điều kiện được biểu diễn tự nhiên qua Criteria và entity mapping. DatabaseClient hữu ích khi SQL cần nhiều biểu thức, JOIN, CTE hoặc database-specific syntax.

Cả hai đều có thể trả số hàng bị tác động. Nếu caller cần biết bản ghi có tồn tại hay không, hãy định nghĩa semantics rõ ràng: 0 hàng có thể là kết quả bình thường với thao tác idempotent, hoặc là lỗi nghiệp vụ nếu hợp đồng yêu cầu phải có đúng một bản ghi.

## 7. Mapping và chuyển đổi dữ liệu

Đây là một khác biệt quan trọng giữa hai API.

### 7.1. Mapping trong R2dbcEntityTemplate

Template dùng mapping metadata và R2dbcConverter để chuyển entity thành giá trị lưu trữ và ngược lại. Những annotation như @Table, @Column, @Id, @Version, @Embedded và @MappedCollection có thể tham gia vào mapping theo mô hình Spring Data Relational.

Nếu dự án đăng ký custom converters trong R2dbcCustomConversions, mapping của template có thể sử dụng chúng. Ví dụ domain value object EmailAddress có thể được chuyển thành String khi ghi và chuyển String thành EmailAddress khi đọc.

~~~java
@Table("customers")
public record Customer(
        @Id Long id,
        @Column("email_address") EmailAddress email
) {}
~~~

Khi dùng template, ứng dụng không phải tự gọi converter cho từng property. Mapping infrastructure thực hiện chuyển đổi theo metadata và custom conversions đã cấu hình.

### 7.2. Mapping trong DatabaseClient

DatabaseClient cung cấp Row và RowMetadata cho callback. Khi dùng API map thủ công:

~~~java
.map((row, metadata) -> new CustomerSummary(
        row.get("id", Long.class),
        row.get("name", String.class),
        row.get("status", String.class)
))
~~~

lập trình viên chịu trách nhiệm chọn cột, kiểu Java và cách tạo object. Custom conversions được cấu hình cho entity mapping không có nghĩa callback thủ công tự động chuyển mọi giá trị thành kiểu domain mong muốn.

Nếu cột email_address được đọc dưới dạng String nhưng DTO cần EmailAddress, có thể chuyển đổi tường minh trong callback hoặc dùng một mapper/converter phù hợp:

~~~java
.map((row, metadata) -> new CustomerContact(
        row.get("id", Long.class),
        new EmailAddress(row.get("email_address", String.class))
))
~~~

Cần xử lý null đúng với schema và domain. Row.get có thể trả null khi cột SQL NULL; không truyền giá trị null vào constructor không chấp nhận null.

### 7.3. Khi nào mapping thủ công là lợi thế?

Mapping thủ công hữu ích khi kết quả không phải một entity hoàn chỉnh:

- DTO tổng hợp từ nhiều bảng.
- Kết quả có aggregate function như COUNT, SUM hoặc AVG.
- Projection chỉ có vài cột và alias riêng.
- Truy vấn báo cáo hoặc read model.
- Kiểu kết quả database-specific.

Ngược lại, với entity CRUD thường xuyên, viết callback thủ công cho từng cột có thể tạo code lặp và tăng nguy cơ quên field hoặc map sai kiểu.

## 8. Bind parameter, null và an toàn SQL

DatabaseClient yêu cầu bind giá trị vào marker. Ví dụ:

~~~java
databaseClient.sql("""
        SELECT id, name
        FROM customers
        WHERE email_address = :email
        """)
    .bind("email", email)
    .fetch()
    .all();
~~~

Named parameter giúp code dễ đọc; DatabaseClient xử lý việc chuyển thành bind marker phù hợp với dialect/driver.

Với giá trị null, không nên gọi bind(name, null). Cần khai báo kiểu đích:

~~~java
databaseClient.sql("""
        SELECT id, name
        FROM customers
        WHERE status = :status
        """)
    .bindNull("status", String.class)
    .fetch()
    .all();
~~~

Nếu dùng R2dbcEntityTemplate, giá trị property và Criteria được xử lý qua mapping infrastructure. Dù dùng API nào, bind parameter chỉ dành cho giá trị dữ liệu, không dùng để thay tên bảng, tên cột hoặc từ khóa SQL.

Không nối chuỗi người dùng trực tiếp vào SQL:

~~~java
// Không an toàn
String sql = "SELECT * FROM customers WHERE name = '" + name + "'";
~~~

Hãy bind value. Nếu cần dynamic identifier hoặc dynamic sort, chuyển input sang allowlist identifier do ứng dụng kiểm soát. SpEL hoặc bind parameter không phải cơ chế an toàn để thay tên cột từ request.

## 9. Query phức tạp: vì sao DatabaseClient thường phù hợp hơn?

Một truy vấn báo cáo có thể kết hợp nhiều bảng và phép tổng hợp:

~~~sql
SELECT
    c.id AS customer_id,
    c.name AS customer_name,
    COUNT(o.id) AS order_count,
    MAX(o.created_at) AS latest_order_at
FROM customers c
LEFT JOIN orders o ON o.customer_id = c.id
WHERE c.status = :status
GROUP BY c.id, c.name
ORDER BY latest_order_at DESC NULLS LAST, c.id ASC;
~~~

Kết quả không nhất thiết là Customer aggregate. Có thể định nghĩa DTO:

~~~java
public record CustomerOrderStats(
        Long customerId,
        String customerName,
        Long orderCount,
        Instant latestOrderAt
) {}
~~~

Và map bằng DatabaseClient:

~~~java
Flux<CustomerOrderStats> stats =
        databaseClient.sql("""
                SELECT
                    c.id AS customer_id,
                    c.name AS customer_name,
                    COUNT(o.id) AS order_count,
                    MAX(o.created_at) AS latest_order_at
                FROM customers c
                LEFT JOIN orders o ON o.customer_id = c.id
                WHERE c.status = :status
                GROUP BY c.id, c.name
                ORDER BY latest_order_at DESC NULLS LAST, c.id ASC
                """)
            .bind("status", "ACTIVE")
            .map((row, metadata) -> new CustomerOrderStats(
                    row.get("customer_id", Long.class),
                    row.get("customer_name", String.class),
                    row.get("order_count", Long.class),
                    row.get("latest_order_at", Instant.class)
            ))
            .all();
~~~

DatabaseClient cho phép SQL thể hiện chính xác JOIN, GROUP BY, aggregate function và alias. Template có thể thực hiện nhiều truy vấn entity-oriented, nhưng với một read model báo cáo phức tạp, việc ép kết quả thành aggregate entity thường không cần thiết.

Nếu SQL dùng cú pháp riêng như PostgreSQL JSON operators, array functions, RETURNING, window functions hoặc CTE đặc thù, DatabaseClient là nơi tự nhiên để sử dụng trực tiếp.

## 10. Khi nào R2dbcEntityTemplate giúp giảm code?

Với thao tác CRUD thông thường, template có thể tránh việc lặp lại SQL và row mapping.

Ví dụ tìm Customer theo ID:

~~~java
Mono<Customer> customer =
        template.selectOne(
                Query.query(Criteria.where("id").is(id)),
                Customer.class
        );
~~~

Nếu viết bằng DatabaseClient, phải khai báo SELECT list, FROM, WHERE, bind ID và tạo Customer từ Row.

Tương tự, khi mapping entity thay đổi do đổi tên cột qua @Column, template tiếp tục dựa trên metadata. Với SQL viết tay, các câu query phải được cập nhật để khớp tên cột mới.

Template cũng giúp sử dụng naming strategy và custom conversions thống nhất. Điều này hữu ích khi dự án có nhiều entity và schema mapping cần được quản lý tập trung.

Tuy nhiên, template không tự làm query nhanh hơn. SQL sinh ra vẫn cần được xem xét và đo lường. Nếu một truy vấn cần chọn đúng vài cột, JOIN đặc thù hoặc tận dụng tính năng database, SQL tường minh có thể rõ ràng và dễ tối ưu hơn.

## 11. Transaction: cả hai API có thể cùng tham gia

DatabaseClient và R2dbcEntityTemplate có thể tham gia reactive transaction nếu chúng sử dụng cùng ConnectionFactory và được điều phối bởi transaction manager phù hợp.

Ví dụ service dùng template để đọc entity rồi dùng DatabaseClient để ghi audit row:

~~~java
@Transactional
public Mono<Customer> changeStatus(Long id, String status) {
    return template.selectOne(
                Query.query(Criteria.where("id").is(id)),
                Customer.class
            )
            .switchIfEmpty(Mono.error(
                    new CustomerNotFoundException(id)
            ))
            .flatMap(customer ->
                    databaseClient.sql("""
                            UPDATE customers
                            SET status = :status
                            WHERE id = :id
                            """)
                        .bind("status", status)
                        .bind("id", id)
                        .fetch()
                        .rowsUpdated()
                        .then(databaseClient.sql("""
                                INSERT INTO customer_audit
                                    (customer_id, action)
                                VALUES (:id, :action)
                                """)
                            .bind("id", id)
                            .bind("action", "STATUS_CHANGED")
                            .fetch()
                            .rowsUpdated())
                        .thenReturn(new Customer(
                                customer.id(),
                                customer.name(),
                                customer.email(),
                                status
                        ))
            );
}
~~~

Đây là ví dụ minh họa phối hợp hai API. Các thao tác phải dùng cùng ConnectionFactory/transaction context để được thực hiện trong cùng reactive transaction. Nếu một API dùng ConnectionFactory khác, transaction manager này không tự bao trùm thao tác kia.

Phương thức transactional cần trả về publisher cho Spring quản lý. Không gọi subscribe() hoặc block() bên trong vì có thể tách thao tác khỏi transaction context hoặc chặn event-loop.

Với nhiều database, cần transaction manager riêng cho từng ConnectionFactory. Một local R2DBC transaction không tự tạo transaction phân tán giữa nhiều database.

## 12. Reactive execution và vòng đời publisher

Cả DatabaseClient lẫn R2dbcEntityTemplate đều trả về Mono hoặc Flux. Việc gọi API thường tạo publisher mô tả thao tác; I/O được thực hiện khi publisher được subscribe.

Ví dụ:

~~~java
Mono<Customer> customer = template.selectOne(
        Query.query(Criteria.where("id").is(1L)),
        Customer.class
);
~~~

Chưa có truy vấn nào nhất thiết được chạy chỉ vì biến customer đã được tạo. Publisher sẽ được tiêu thụ bởi WebFlux, StepVerifier hoặc một subscriber hợp lệ.

Tương tự với DatabaseClient:

~~~java
Flux<Map<String, Object>> rows =
        databaseClient.sql("SELECT id, name FROM customers")
                .fetch()
                .all();
~~~

Không nên tự subscribe trong service chỉ để ép truy vấn chạy. Hãy trả publisher về caller để lỗi, cancellation, backpressure và transaction được quản lý xuyên suốt pipeline.

Dùng:

- map khi chuyển đổi một giá trị đồng bộ.
- flatMap khi bước tiếp theo trả về Mono hoặc publisher.
- then khi chỉ cần tín hiệu hoàn tất.
- rowsUpdated khi cần số hàng bị tác động từ DML.

Cả hai API đều có thể ghép trong cùng Reactor pipeline miễn là giữ đúng ConnectionFactory và transaction context.

## 13. Hiệu năng: không có API nào luôn nhanh hơn

DatabaseClient thấp hơn về mức trừu tượng, nhưng điều đó không đồng nghĩa mọi truy vấn dùng nó sẽ nhanh hơn template. Hiệu năng phụ thuộc:

- SQL thực tế được thực thi.
- Index, filter, join, sort và execution plan.
- Số cột và số hàng trả về.
- Kích thước dữ liệu truyền qua mạng.
- Driver và kiểu dữ liệu.
- Chi phí row mapping hoặc entity conversion.
- Số truy vấn và round-trip.
- Pool, concurrency và transaction duration.

DatabaseClient có thể tránh việc mapping entity đầy đủ khi chỉ cần DTO nhỏ. R2dbcEntityTemplate có thể giảm code thủ công và dùng mapping đã tối ưu theo metadata. Nhưng nếu cả hai tạo cùng SQL và cùng kết quả, chênh lệch có thể nhỏ so với chi phí database/network.

Hãy đo bằng SQL logging có kiểm soát, EXPLAIN/EXPLAIN ANALYZE phù hợp với database và benchmark trên dữ liệu đại diện. Không bật log bind parameter nhạy cảm trong production nếu chưa có cơ chế bảo vệ.

## 14. Kết hợp hai API trong cùng một ứng dụng

Một thiết kế phổ biến là dùng template cho các thao tác entity-oriented và DatabaseClient cho query chuyên biệt.

Ví dụ:

~~~java
@Service
public class CustomerService {

    private final R2dbcEntityTemplate template;
    private final DatabaseClient databaseClient;

    public CustomerService(
            R2dbcEntityTemplate template,
            DatabaseClient databaseClient) {
        this.template = template;
        this.databaseClient = databaseClient;
    }

    public Mono<Customer> findById(Long id) {
        return template.selectOne(
                Query.query(Criteria.where("id").is(id)),
                Customer.class
        );
    }

    public Mono<Long> deactivate(Long id) {
        return template.update(Customer.class)
                .matching(Query.query(Criteria.where("id").is(id)))
                .apply(Update.update("status", "INACTIVE"));
    }

    public Flux<CustomerOrderStats> report(String status) {
        return databaseClient.sql("""
                SELECT c.id AS customer_id,
                       c.name AS customer_name,
                       COUNT(o.id) AS order_count
                FROM customers c
                LEFT JOIN orders o ON o.customer_id = c.id
                WHERE c.status = :status
                GROUP BY c.id, c.name
                ORDER BY c.id
                """)
            .bind("status", status)
            .map((row, metadata) -> new CustomerOrderStats(
                    row.get("customer_id", Long.class),
                    row.get("customer_name", String.class),
                    row.get("order_count", Long.class),
                    null
            ))
            .all();
    }
}
~~~

Ví dụ dùng template cho truy vấn entity và update đơn giản, DatabaseClient cho báo cáo JOIN. Cả hai được inject vào service và có thể dùng chung cấu hình R2DBC.

Trong ứng dụng thực tế, nên tách report query sang repository/DAO chuyên biệt nếu service bắt đầu chứa nhiều SQL. Điều quan trọng là ranh giới trách nhiệm rõ ràng, không phải buộc toàn bộ ứng dụng chỉ dùng một API.

## 15. Bảng quyết định lựa chọn API

| Tình huống | API phù hợp | Lý do |
|---|---|---|
| CRUD chuẩn cho entity | R2dbcEntityTemplate hoặc ReactiveCrudRepository | Tận dụng entity metadata và mapping |
| Insert entity và nhận generated ID | R2dbcEntityTemplate | Template xử lý mapping và generated values theo dialect |
| Select theo Criteria | R2dbcEntityTemplate | Điều kiện được xây dựng bằng property metadata |
| Update/delete theo entity và điều kiện | R2dbcEntityTemplate | Không cần viết SQL lặp lại |
| JOIN nhiều bảng thành DTO | DatabaseClient | Kiểm soát SQL và mapping read model |
| Báo cáo, GROUP BY, window function | DatabaseClient | SQL thể hiện rõ phép tổng hợp |
| SQL database-specific | DatabaseClient | Dùng trực tiếp cú pháp/feature của database |
| Cần rowsUpdated | DatabaseClient hoặc template update/delete | Cả hai có thể trả số hàng bị ảnh hưởng |
| Mapping custom value object trong entity | R2dbcEntityTemplate | Dùng R2dbcConverter và custom conversions |
| Mapping thủ công kết quả nhiều bảng | DatabaseClient | Callback tạo DTO theo từng Row |
| Câu lệnh có RETURNING đặc thù | DatabaseClient | Chủ động viết SQL và map returned rows |
| Cần query builder nhưng vẫn theo entity | R2dbcEntityTemplate | Criteria, Query, Sort và Update |

Không có quy tắc rằng một use case phải chọn một API cho toàn bộ vòng đời. Một service có thể dùng template để đọc aggregate, DatabaseClient để ghi audit hoặc chạy truy vấn báo cáo, miễn là transaction và ConnectionFactory được cấu hình đúng.

## 16. Những lỗi thường gặp khi chọn nhầm API

| Dấu hiệu | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| SQL và mapping lặp lại ở nhiều nơi | Dùng DatabaseClient cho CRUD entity đơn giản mà không có lý do | Cân nhắc R2dbcEntityTemplate hoặc repository |
| DTO thiếu field hoặc map sai cột | Row callback đọc nhầm tên/kiểu cột | Kiểm tra SELECT list, alias và mapping |
| Annotation @Column không có tác dụng trong SQL viết tay | Raw SQL không tự được viết lại theo entity metadata | Cập nhật tên cột trong SQL hoặc chuyển sang template mapping |
| Custom converter không được áp dụng trong callback | DatabaseClient map thủ công | Chuyển đổi tường minh hoặc dùng entity mapping API |
| Query báo cáo khó biểu đạt bằng Criteria | Dùng template cho SQL nhiều JOIN/aggregation | Dùng DatabaseClient với SQL rõ ràng |
| Bind null thất bại | Gọi bind(name, null) | Dùng bindNull với kiểu Java |
| SQL injection qua sort/table name | Nối identifier từ request | Dùng allowlist hoặc mapping metadata |
| Transaction không bao trùm cả hai API | Hai API dùng ConnectionFactory khác hoặc publisher bị subscribe riêng | Dùng cùng factory/transaction context và trả publisher |
| Generated ID không xuất hiện trong kết quả | Bỏ qua entity trả về hoặc SQL không trả generated key | Dùng kết quả template hoặc RETURNING/generated key phù hợp |
| Tải quá nhiều dữ liệu | Dùng entity đầy đủ khi chỉ cần vài cột | Projection/DTO với SELECT list tường minh |

## 17. Kiểm thử hai API

Unit test có thể kiểm tra service logic và row mapping, nhưng để xác nhận SQL, dialect, generated values và converter cần integration test với database tương thích.

Nên kiểm thử:

- Template ánh xạ đúng @Table và @Column.
- Template insert trả ID/version theo mong đợi.
- Criteria và Sort tạo điều kiện đúng.
- DatabaseClient bind giá trị đúng và map alias/NULL chính xác.
- Query JOIN trả DTO đúng.
- rowsUpdated trả số hàng bị tác động.
- Custom conversions hoạt động qua entity mapping.
- Raw Row mapping chuyển đổi đúng khi dùng DatabaseClient.
- Cả hai API cùng tham gia reactive transaction khi dùng chung ConnectionFactory.
- Lỗi constraint hoặc connection được truyền qua publisher đúng cách.

Testcontainers là lựa chọn hữu ích để chạy database cùng loại với production. H2 hoặc mock có thể không phản ánh cú pháp SQL, generated key, kiểu dữ liệu hoặc hành vi dialect của database thực tế.

## 18. Checklist lựa chọn DatabaseClient hay R2dbcEntityTemplate

Trước khi viết thao tác dữ liệu, hãy tự xác định:

1. Kết quả có phải entity/aggregate đã được mapping không?
2. Có cần dùng @Table, @Column, naming strategy hoặc custom conversion không?
3. Truy vấn có JOIN, CTE, aggregation hoặc database-specific syntax không?
4. Caller cần entity đầy đủ, DTO, scalar hay chỉ rowsUpdated?
5. Có cần kiểm soát chính xác SELECT list và alias không?
6. Điều kiện có thể biểu diễn rõ bằng Criteria/Query không?
7. Nếu dùng SQL trực tiếp, đã bind mọi giá trị dữ liệu chưa?
8. Nếu cần dynamic identifier, đã dùng allowlist chưa?
9. API đang dùng có chia sẻ đúng ConnectionFactory và transaction context không?
10. Integration test đã xác nhận SQL và mapping trên database thực tế chưa?

Một nguyên tắc dễ nhớ: **DatabaseClient kiểm soát câu SQL và Row; R2dbcEntityTemplate kiểm soát thao tác theo entity metadata và mapping.** Chọn mức API thấp hơn khi cần quyền kiểm soát SQL; chọn mức entity-oriented khi muốn tận dụng mapping của Spring Data.

## 19. Kết luận

DatabaseClient và R2dbcEntityTemplate có trách nhiệm khác nhau nhưng bổ trợ cho nhau. DatabaseClient tập trung vào SQL, bind parameter, thực thi và ánh xạ Row do ứng dụng kiểm soát. R2dbcEntityTemplate tập trung vào entity mapping, sử dụng metadata, converter và dialect để thực hiện các thao tác CRUD/query theo kiểu entity.

Với CRUD thông thường, Criteria và thao tác theo aggregate, template giúp giảm SQL và mapping lặp lại. Với JOIN, báo cáo, projection đặc thù hoặc tính năng riêng của database, DatabaseClient cho phép viết SQL rõ ràng và kiểm soát hình dạng kết quả. Cả hai có thể dùng chung ConnectionFactory và cùng tham gia reactive transaction nếu được cấu hình đúng.

Không có API nào luôn nhanh hơn hoặc phù hợp cho mọi thao tác. Hãy chọn theo hình dạng dữ liệu, mức độ cần kiểm soát SQL, nhu cầu mapping và trách nhiệm của use case. Giữ bind parameter cho giá trị, kiểm soát identifier động, không chặn hoặc tự subscribe trong service, và kiểm thử với database thực tế để bảo đảm hành vi đúng.

