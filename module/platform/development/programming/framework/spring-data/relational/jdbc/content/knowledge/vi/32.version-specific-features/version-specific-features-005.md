# Upsert bằng JdbcAggregateTemplate: yêu cầu dialect và giới hạn version

**Upsert** là thao tác ghi có hai kết quả: nếu hàng mang khóa định danh đã tồn tại thì cập nhật hàng đó; nếu chưa tồn tại thì chèn hàng mới. Spring Data JDBC cung cấp thao tác này qua `JdbcAggregateTemplate.upsert(instance)` từ Spring Data Relational **4.1**.

Upsert của Spring Data JDBC dựa vào câu lệnh native do database hỗ trợ, thường là `INSERT ... ON CONFLICT` hoặc `MERGE`. Vì vậy, thao tác chỉ dùng được khi dialect và `DataAccessStrategy` hỗ trợ upsert một câu lệnh. Entity phải có ID được gán trước và tính năng hiện chưa hỗ trợ optimistic locking.

Bài học giải thích cách dùng API, vai trò của dialect, khác biệt giữa `save`, `insert`, `update` và `upsert`, các giới hạn theo phiên bản, ảnh hưởng tới child entities và cách kiểm thử với database thực tế.

## 1. Upsert giải quyết vấn đề gì?

Một luồng ghi thường gặp là đồng bộ dữ liệu từ hệ thống ngoài. Hệ thống nguồn đã cấp một ID ổn định cho khách hàng hoặc đơn hàng. Ứng dụng cần ghi dữ liệu đó dù bản ghi đã có hay chưa.

Nếu dùng cách kiểm tra rồi mới ghi:

```java
if (repository.existsById(customer.getId())) {
    repository.save(customer);
} else {
    repository.save(customer);
}
```

Ví dụ trên còn chưa xử lý đúng khác biệt giữa insert/update, nhưng ngay cả khi tách hai nhánh, nó vẫn có race condition:

1. Request A kiểm tra ID chưa tồn tại.
2. Request B cũng kiểm tra ID đó chưa tồn tại.
3. Cả hai cùng thực hiện INSERT.
4. Một request thành công, request còn lại gặp duplicate key.

Một thao tác native upsert để database xử lý xung đột trong một câu lệnh. Điều này loại bỏ bước đọc tồn tại trước khi ghi và để database áp dụng cơ chế conflict handling dựa trên khóa.

### 1.1. Upsert không phải một lệnh update thông thường

| Trạng thái của ID trong database | Kết quả upsert |
|---|---|
| Chưa có hàng mang ID đó | INSERT |
| Đã có hàng mang ID đó | UPDATE theo quy tắc dialect |
| ID không được gán trên entity | Không đáp ứng điều kiện của API |
| Dialect/DataAccessStrategy không hỗ trợ native upsert | Có thể ném UnsupportedOperationException |

Upsert hữu ích khi ID đã có từ trước, ví dụ:

- Đồng bộ khách hàng từ CRM.
- Nhập dữ liệu đơn hàng từ hệ thống đối tác.
- Cập nhật trạng thái từ message có khóa nghiệp vụ ổn định.
- Đồng bộ cấu hình theo tenant.
- Ghi snapshot hoặc projection có primary key do ứng dụng xác định.

Upsert không thay thế mọi thao tác lưu. Nếu use case cần kiểm tra domain invariant, optimistic locking hoặc cập nhật một phần có điều kiện, cần chọn API phù hợp hơn.

## 2. API upsert của JdbcAggregateTemplate

`JdbcAggregateTemplate` là API cấp template để thao tác aggregate trực tiếp, bên cạnh Spring Data JDBC repository.

Có thể inject template như một Spring bean:

```java
@Service
public class CustomerSyncService {

    private final JdbcAggregateTemplate aggregateTemplate;

    public CustomerSyncService(JdbcAggregateTemplate aggregateTemplate) {
        this.aggregateTemplate = aggregateTemplate;
    }

    public Customer synchronize(Customer customer) {
        return aggregateTemplate.upsert(customer);
    }
}
```

Method có dạng tổng quát:

```java
<T> T upsert(T instance)
```

API nhận aggregate root, không nhận câu SQL hoặc tên bảng. Spring Data dùng mapping metadata, converter, dialect và data access strategy để tạo và thực thi các thao tác relational.

### 2.1. ID phải được gán trước

Entity truyền vào phải có identifier. Đây là điều kiện quan trọng vì database cần biết khóa nào dùng để xác định xung đột.

Ví dụ dùng ID do ứng dụng cấp:

```java
@Table("customers")
public record Customer(
        @Id Long id,
        String externalCode,
        String displayName,
        String email
) {
}
```

Gọi upsert:

```java
Customer customer = new Customer(
        7001L,
        "CRM-7001",
        "Nguyen An",
        "an@example.test"
);

Customer saved = aggregateTemplate.upsert(customer);
```

`7001L` là ID đã được xác định trước khi gọi. Không thiết kế luồng này với giả định database sẽ tự sinh identity ID rồi mới quyết định insert hay update.

Nếu database-generated ID là yêu cầu chính, các thao tác `insert` hoặc `save` thường phù hợp hơn. Upsert cần khóa để xác định conflict target trước khi chạy.

### 2.2. Kết quả trả về

`upsert` trả về instance aggregate sau khi thao tác được thực thi. Tùy mapping và dialect, instance trả về có thể phản ánh giá trị ID mà dialect cung cấp.

Không nên dựa vào upsert để lấy một identity ID chưa có trước đó. Điều kiện API vẫn là entity phải có identifier được gán.

## 3. Phiên bản Spring Data JDBC hỗ trợ upsert

`JdbcAggregateTemplate.upsert` được giới thiệu trong Spring Data Relational **4.1**.

| Phiên bản Spring Data Relational | API JdbcAggregateTemplate.upsert |
|---|---|
| 3.x | Chưa có |
| 4.0.x | Chưa có |
| 4.1 trở lên | Có, nếu dialect và data access strategy hỗ trợ |

Vì Spring Data JDBC phụ thuộc Spring Data Relational, cần kiểm tra phiên bản thực tế của cả hai module trong dependency management. Không thể thêm lời gọi `upsert` vào source đang dùng 4.0.x rồi kỳ vọng nó hoạt động chỉ vì database hỗ trợ cú pháp SQL upsert.

### 3.1. Kiểm tra dependency version

Với Spring Boot, thường nên để BOM của Boot quản lý các phiên bản Spring Data tương thích. Kiểm tra dependency tree hoặc dependency report để biết version được resolve, thay vì chỉ nhìn version khai báo trực tiếp.

Ví dụ Gradle:

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-jdbc")
}
```

Nếu muốn dùng API upsert, hãy chọn Spring Boot/Spring Data release train quản lý Spring Data Relational 4.1 trở lên. Không nâng riêng `spring-data-relational` lên một version khác với `spring-data-jdbc` nếu chưa xác nhận tương thích.

### 3.2. Lỗi biên dịch trên version cũ

Nếu source báo không tìm thấy method `upsert(Customer)` trên `JdbcAggregateTemplate`, kiểm tra:

- Spring Data JDBC đang dùng version nào.
- Spring Data Relational đang được resolve về version nào.
- Có dependency override hoặc BOM khác đang ghim version cũ không.
- IDE và Gradle có đang dùng cùng dependency graph không.

Nâng version cần giữ tương thích với Spring Boot, Spring Framework và JDBC driver đang dùng.

## 4. Yêu cầu dialect: native single-statement upsert

Không phải database nào cũng dùng cùng cú pháp upsert. Spring Data Relational dựa vào dialect để biết cách tạo câu lệnh tương ứng.

Hai dạng cú pháp thường gặp:

### 4.1. PostgreSQL: INSERT ... ON CONFLICT

Ví dụ SQL minh họa:

```sql
INSERT INTO customers (id, external_code, display_name, email)
VALUES (:id, :externalCode, :displayName, :email)
ON CONFLICT (id)
DO UPDATE SET
    external_code = EXCLUDED.external_code,
    display_name = EXCLUDED.display_name,
    email = EXCLUDED.email;
```

Khi chưa có hàng với ID đó, database insert. Khi xảy ra conflict trên khóa mục tiêu, database chạy nhánh update.

### 4.2. MySQL: INSERT ... ON DUPLICATE KEY UPDATE

Ví dụ SQL minh họa:

```sql
INSERT INTO customers (id, external_code, display_name, email)
VALUES (?, ?, ?, ?)
ON DUPLICATE KEY UPDATE
    external_code = VALUES(external_code),
    display_name = VALUES(display_name),
    email = VALUES(email);
```

Cú pháp cụ thể có thể thay đổi theo phiên bản MySQL. Spring Data không yêu cầu ứng dụng tự viết đoạn SQL này khi dialect đã hỗ trợ; dialect chịu trách nhiệm render câu lệnh thích hợp.

### 4.3. MERGE

Một số database dùng câu lệnh `MERGE` để biểu diễn insert hoặc update theo điều kiện match:

```sql
MERGE INTO customers target
USING (
    SELECT :id AS id, :displayName AS display_name
) source
ON (target.id = source.id)
WHEN MATCHED THEN
    UPDATE SET target.display_name = source.display_name
WHEN NOT MATCHED THEN
    INSERT (id, display_name)
    VALUES (source.id, source.display_name);
```

Đây chỉ là hình dạng khái quát. Cú pháp và khả năng của `MERGE` khác nhau giữa SQL Server, Oracle, DB2 và các database khác.

### 4.4. Vì sao phải là single-statement upsert?

Một cách triển khai kiểu:

1. SELECT kiểm tra ID.
2. Nếu có thì UPDATE.
3. Nếu không thì INSERT.

không tương đương native upsert trong môi trường concurrent. Hai transaction có thể cùng quan sát “chưa tồn tại” rồi cùng insert.

Native upsert cho database xử lý conflict trong một statement theo semantics của vendor. Vì vậy, dialect phải cung cấp khả năng render upsert; chỉ hỗ trợ SELECT, INSERT và UPDATE riêng lẻ là chưa đủ.
## 5. Database và dialect được hỗ trợ

Tài liệu Spring Data Relational 4.1 liệt kê hỗ trợ upsert cho các database sau:

| Database | Dạng native thường dùng |
|---|---|
| PostgreSQL | `INSERT ... ON CONFLICT` |
| H2 | Cú pháp upsert theo dialect H2 |
| MySQL | `INSERT ... ON DUPLICATE KEY UPDATE` |
| MariaDB | `INSERT ... ON DUPLICATE KEY UPDATE` |
| SQL Server | `MERGE` |
| Oracle | `MERGE` |
| DB2 | `MERGE` |
| HSQLDB | Cú pháp upsert theo dialect HSQLDB |

Danh sách và mức hỗ trợ cần được đối chiếu với tài liệu của release train ứng dụng đang sử dụng. Một database có thể hỗ trợ native upsert ở cấp SQL nhưng dialect của một phiên bản Spring Data cụ thể chưa chắc đã cung cấp implementation tương ứng.

### 5.1. Database chưa hỗ trợ

Nếu dialect không hỗ trợ upsert một câu lệnh, thao tác có thể ném:

```java
UnsupportedOperationException
```

`DataAccessStrategy` tùy chỉnh cũng cần cung cấp upsert. Một implementation tự viết hoặc adapter MyBatis không tự có khả năng upsert chỉ vì interface cấp cao có method đó.

Khi gặp lỗi này:

- Xác nhận database product và dialect thực tế.
- Kiểm tra Spring Data version.
- Kiểm tra `DataAccessStrategy` đang được cấu hình.
- Kiểm tra database có native upsert và phiên bản SQL cần thiết không.
- Chọn custom SQL hoặc nâng cấp khi có hỗ trợ phù hợp.

Không trả một dialect giả cho database không tương thích chỉ để vượt qua bước khởi động. SQL sai có thể gây lỗi dữ liệu ở runtime.

## 6. Khác biệt giữa save, insert, update và upsert

Bốn thao tác này có mục đích khác nhau:

| Method | Cách quyết định | Hành vi |
|---|---|---|
| `save(instance)` | Dựa trên trạng thái mới/cũ theo mapping và entity information | Insert hoặc update |
| `insert(instance)` | Không kiểm tra trạng thái mới/cũ | Luôn insert |
| `update(instance)` | Không kiểm tra trạng thái mới/cũ | Luôn update |
| `upsert(instance)` | Dựa vào xung đột ID trong database | Native insert-or-update |

### 6.1. save không đồng nghĩa upsert

`save` thường chọn insert hoặc update theo trạng thái mới của entity, chẳng hạn ID/version hoặc cơ chế `Persistable.isNew()`.

Với assigned ID, một entity có ID khác null có thể được coi là entity đã tồn tại theo quy tắc newness. Nếu hàng chưa có trong database, nhánh update có thể không cập nhật được hàng nào.

`upsert` sử dụng database conflict handling để quyết định insert hay update theo ID. Nó phù hợp khi ID đã được cấp trước nhưng bản ghi có thể chưa tồn tại.

### 6.2. insert và update khi biết chắc trạng thái

Dùng `insert` khi chắc chắn ID chưa có và muốn lỗi nếu vi phạm unique key.

Dùng `update` khi chắc chắn hàng đã tồn tại và muốn cập nhật aggregate. Nếu có `@Version`, update hỗ trợ optimistic locking.

Không dùng upsert chỉ vì muốn “lưu cho chắc” nếu use case yêu cầu phát hiện bản ghi đã tồn tại hoặc phát hiện xung đột version.

## 7. Ví dụ service đồng bộ khách hàng

Entity dùng assigned ID:

```java
@Table("customers")
public record Customer(
        @Id Long id,
        @Column("external_code") String externalCode,
        @Column("display_name") String displayName,
        String email
) {
}
```

Service:

```java
@Service
public class CustomerSyncService {

    private final JdbcAggregateTemplate aggregateTemplate;

    public CustomerSyncService(JdbcAggregateTemplate aggregateTemplate) {
        this.aggregateTemplate = aggregateTemplate;
    }

    @Transactional
    public Customer synchronize(Customer incoming) {
        return aggregateTemplate.upsert(incoming);
    }
}
```

Khi message đồng bộ mang ID `7001`:

- Nếu `customers.id = 7001` chưa có, database insert khách hàng.
- Nếu đã có, database update theo câu lệnh upsert của dialect.
- Service không cần gọi `existsById` trước khi ghi.

`@Transactional` tạo ranh giới cho thao tác persistence của service. Nếu aggregate có child actions hoặc nhiều statement, transaction giúp chúng cùng commit/rollback khi dùng cùng DataSource và transaction manager.

### 7.1. Dùng transaction khi aggregate có child entities

Native upsert cho root là một statement, nhưng aggregate có thể phát sinh thêm thao tác relational cho child rows. Nếu các statement đó cần atomic, gọi template bên trong transaction phù hợp.

Ví dụ:

```java
@Transactional
public PurchaseOrder synchronizeOrder(PurchaseOrder incoming) {
    return aggregateTemplate.upsert(incoming);
}
```

Không giả định một method template luôn tự mở transaction bao quanh mọi statement khi được gọi trực tiếp. Đặt transaction boundary rõ ràng ở application service khi use case yêu cầu atomicity.

## 8. Upsert với aggregate có child collection

Spring Data JDBC quản lý aggregate root và các child entity theo mapping. Upsert có hành vi đặc biệt ở phần aggregate:

- Root được biểu diễn bằng một action upsert native.
- Các entity tham chiếu/child trong aggregate được xử lý bằng các action delete và insert.
- Các child rows không mặc định được upsert từng hàng theo primary key riêng.

Điều này có nghĩa aggregate child collection có thể được thay thế bằng nội dung hiện tại của instance.

Ví dụ:

```java
@Table("orders")
public record PurchaseOrder(
        @Id Long id,
        String orderCode,
        @MappedCollection(idColumn = "order_id")
        List<OrderLine> lines
) {
}
```

Nếu database đang có order `100` với hai dòng hàng, instance mới có cùng ID nhưng ba dòng hàng, upsert sẽ dùng native upsert cho root và thực hiện các thao tác delete/insert cho child rows theo aggregate change.

### 8.1. Hệ quả với child ID và metadata

Vì child rows được delete rồi insert lại, cần cân nhắc:

- Child có ID do database sinh tự động có thể nhận ID mới.
- Timestamp tạo của child có thể được tạo lại nếu mapping/callback gán giá trị mới.
- Trigger database trên DELETE/INSERT có thể chạy.
- Audit log ở cấp child có thể ghi nhận xóa và tạo mới.
- Foreign key từ bảng khác trỏ trực tiếp tới child row có thể bị ảnh hưởng.
- Một child row được giữ nguyên về mặt domain vẫn có thể bị thay thế vật lý.

Nếu child có identity/lifecycle độc lập hoặc cần giữ nguyên ID và metadata, upsert toàn aggregate có thể không phải lựa chọn phù hợp. Hãy dùng workflow update riêng hoặc persistence logic chuyên biệt cho child.

### 8.2. AggregateReference không phải cascade upsert

`AggregateReference` biểu diễn ID tham chiếu tới một aggregate root khác. Nó không có nghĩa aggregate được tham chiếu sẽ tự động được upsert cùng root hiện tại.

Ví dụ order tham chiếu customer:

```java
private AggregateReference<Customer, Long> customer;
```

Upsert order lưu giá trị khóa customer trên order. Nếu customer cũng cần được tạo/cập nhật, hãy thực hiện use case đó rõ ràng qua repository/template của Customer.

## 9. Optimistic locking chưa được hỗ trợ

Đây là giới hạn quan trọng của upsert trong Spring Data JDBC: **upserts hiện không hỗ trợ optimistic locking**.

Nếu entity có:

```java
@Version
private Long version;
```

không được giả định `upsert` sẽ kiểm tra version cũ và từ chối ghi khi một transaction khác đã cập nhật bản ghi.

### 9.1. Rủi ro lost update

Giả sử hai request cùng đọc một customer ở version 5:

1. Request A thay đổi email.
2. Request B thay đổi display name.
3. A ghi thành công.
4. B gọi upsert với snapshot cũ.
5. B có thể ghi đè các giá trị A vừa cập nhật vì upsert không kiểm tra version theo optimistic-lock contract.

Nếu use case cần phát hiện xung đột concurrent update, dùng thao tác có optimistic locking như `save`/`update` với `@Version`, hoặc SQL custom có điều kiện version rõ ràng.

### 9.2. Chọn API theo concurrency requirement

| Yêu cầu | Hướng phù hợp |
|---|---|
| ID có sẵn, cần insert-or-update nhanh, không cần optimistic lock | `upsert` |
| Cần kiểm tra version cũ | `save` hoặc `update` với `@Version` |
| Chỉ insert và muốn duplicate key báo lỗi | `insert` |
| Chỉ update và muốn phát hiện version mismatch | `update` với `@Version` |
| Cần atomic condition phức tạp | Custom SQL có version predicate hoặc stored procedure |

Không thêm `@Version` rồi kết luận dữ liệu đã được bảo vệ khi gọi upsert. API hiện tại ghi rõ giới hạn này.

## 10. Upsert và dữ liệu đầy đủ so với partial update

Upsert nhận một instance domain để ánh xạ thành câu lệnh ghi. Hãy truyền object chứa trạng thái mà use case muốn lưu đầy đủ.

Không dùng upsert như một PATCH request chỉ chứa vài field có giá trị, vì những field còn lại có thể được ánh xạ thành NULL/default và ghi đè dữ liệu đang có tùy mapping và SQL generated.

Ví dụ không an toàn nếu mục tiêu chỉ cập nhật email:

```java
Customer partial = new Customer(
        7001L,
        null,
        null,
        "new@example.test"
);

aggregateTemplate.upsert(partial);
```

Object này có thể khiến các cột khác bị ghi bằng null/default theo mapping. Để cập nhật một phần, dùng `JdbcTemplate`, custom repository với câu UPDATE cụ thể hoặc tải aggregate hiện tại, thay đổi field cần thiết rồi lưu bằng API phù hợp.

### 10.1. Upsert và unique constraint khác

API mô tả upsert theo identifier của aggregate root. Nếu bảng có unique constraint khác, ví dụ `external_code`, conflict trên constraint đó có thể có behavior khác tùy database và conflict target mà dialect tạo ra.

Không giả định upsert theo ID sẽ tự động merge theo mọi unique key. Nếu business key là conflict target, hãy kiểm tra khả năng dialect/API của phiên bản đang dùng hoặc viết SQL riêng với conflict target phù hợp.
## 11. Callbacks và lifecycle events

`JdbcAggregateTemplate` thực hiện upsert qua aggregate persistence pipeline. Các callback lifecycle của Spring Data JDBC như `BeforeConvertCallback`, `BeforeSaveCallback` và `AfterSaveCallback` có thể tham gia pipeline này khi được cấu hình.

Điều đó cho phép ứng dụng tiếp tục dùng callback để:

- Chuẩn hóa domain value trước khi conversion.
- Bổ sung metadata cần lưu.
- Quan sát aggregate change trước khi SQL chạy.
- Phản ứng sau khi các thao tác persistence đã được thực thi.

Tuy nhiên, `AfterSaveCallback` không có nghĩa transaction đã commit. Nếu method service còn chạy trong transaction, exception sau callback vẫn có thể làm transaction rollback.

Không gửi email hoặc publish message như thể dữ liệu đã commit chỉ vì callback after-save đã chạy. Dùng outbox hoặc cơ chế after-commit phù hợp khi cần side effect bền vững.

## 12. Upsert và transaction atomicity

Một upsert root được dialect render thành một câu lệnh native. Aggregate có child collection có thể phát sinh nhiều statement bổ sung để delete/insert child rows.

Nếu một statement thành công nhưng statement sau thất bại, ứng dụng cần transaction để bảo đảm toàn bộ aggregate change cùng commit hoặc rollback.

Ví dụ:

```java
@Service
public class OrderImportService {

    private final JdbcAggregateTemplate template;

    public OrderImportService(JdbcAggregateTemplate template) {
        this.template = template;
    }

    @Transactional
    public PurchaseOrder importOrder(PurchaseOrder order) {
        return template.upsert(order);
    }
}
```

Transaction manager phải quản lý cùng DataSource mà Spring Data JDBC đang sử dụng. Nếu một phần công việc chạy qua DataSource khác, local JDBC transaction này không tự biến thành distributed transaction.

## 13. Khi nào không nên dùng upsert?

Upsert không phù hợp với mọi luồng ghi.

Tránh dùng khi:

- Entity không có ID trước khi ghi.
- Database/dialect hiện tại không hỗ trợ native upsert.
- Use case cần optimistic locking.
- Chỉ muốn cập nhật một vài cột.
- Child rows phải giữ nguyên identity hoặc audit lifecycle.
- Cần phát hiện duplicate thay vì âm thầm cập nhật.
- Conflict target phải là một business key khác với aggregate ID nhưng dialect không hỗ trợ cách đó.
- Custom `DataAccessStrategy` chưa triển khai upsert.

Trong các trường hợp này, dùng `insert`, `update`, `save`, custom SQL hoặc một workflow application service rõ ràng hơn.

## 14. Fallback khi version hoặc dialect chưa hỗ trợ

### 14.1. Dùng custom SQL native

Nếu database hỗ trợ upsert nhưng Spring Data JDBC version chưa có API, có thể dùng `NamedParameterJdbcTemplate` để viết SQL native.

Ví dụ PostgreSQL:

```java
@Repository
public class CustomerNativeUpsertRepository {

    private final NamedParameterJdbcTemplate jdbc;

    public CustomerNativeUpsertRepository(NamedParameterJdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public void upsert(Customer customer) {
        String sql = """
            INSERT INTO customers (id, external_code, display_name, email)
            VALUES (:id, :externalCode, :displayName, :email)
            ON CONFLICT (id)
            DO UPDATE SET
                external_code = EXCLUDED.external_code,
                display_name = EXCLUDED.display_name,
                email = EXCLUDED.email
            """;

        MapSqlParameterSource parameters = new MapSqlParameterSource()
                .addValue("id", customer.id())
                .addValue("externalCode", customer.externalCode())
                .addValue("displayName", customer.displayName())
                .addValue("email", customer.email());

        jdbc.update(sql, parameters);
    }
}
```

Đây là SQL dành cho PostgreSQL. Với MySQL, SQL Server hoặc database khác, cần dùng cú pháp vendor tương ứng.

Custom SQL trực tiếp không tự thực hiện aggregate mapping, child replacement, entity callbacks hoặc auditing như `JdbcAggregateTemplate`. Nếu cần các behavior đó, ứng dụng phải thiết kế và thực hiện rõ ràng.

### 14.2. Tránh SELECT rồi INSERT/UPDATE khi cần concurrency safety

Fallback dạng:

```java
if (template.findById(id, Customer.class) == null) {
    template.insert(customer);
} else {
    template.update(customer);
}
```

có thể phù hợp khi chỉ có một writer hoặc đã có khóa/serialization bên ngoài. Nhưng nếu nhiều writer đồng thời, đây là check-then-act và có race condition.

Nếu cần tính atomic, ưu tiên native SQL upsert hoặc cơ chế khóa/serialization được thiết kế rõ ràng.

## 15. Kiểm thử upsert

Cần kiểm thử cả nhánh insert, nhánh update, dialect và giới hạn optimistic locking.

### 15.1. Test insert khi chưa có ID

```java
@DataJdbcTest
class CustomerUpsertTest {

    @Autowired
    JdbcAggregateTemplate template;

    @Autowired
    JdbcTemplate jdbc;

    @Test
    void insertsWhenIdDoesNotExist() {
        Customer customer = new Customer(
                7001L,
                "CRM-7001",
                "Nguyen An",
                "an@example.test"
        );

        Customer saved = template.upsert(customer);

        Integer count = jdbc.queryForObject(
                "SELECT COUNT(*) FROM customers WHERE id = ?",
                Integer.class,
                7001L
        );

        assertThat(count).isEqualTo(1);
        assertThat(saved.id()).isEqualTo(7001L);
    }
}
```

### 15.2. Test update khi ID đã tồn tại

```java
@Test
void updatesWhenIdAlreadyExists() {
    template.insert(new Customer(
            7002L,
            "CRM-7002",
            "Old Name",
            "old@example.test"
    ));

    Customer incoming = new Customer(
            7002L,
            "CRM-7002",
            "New Name",
            "new@example.test"
    );

    template.upsert(incoming);

    String displayName = jdbc.queryForObject(
            "SELECT display_name FROM customers WHERE id = ?",
            String.class,
            7002L
    );

    assertThat(displayName).isEqualTo("New Name");
}
```

### 15.3. Test child collection

Tạo aggregate có hai child, upsert lại cùng root ID với ba child, sau đó xác nhận:

- Root vẫn chỉ có một hàng.
- Child rows phản ánh collection mới.
- Child ID behavior phù hợp với chiến lược generated/assigned ID.
- Các trigger và foreign key liên quan hoạt động như dự kiến.

Nếu child row được delete/insert lại, không viết test giả định child ID cũ luôn được giữ nguyên.

### 15.4. Test optimistic locking limitation

Nếu aggregate có `@Version`, không viết test mong đợi upsert ném `OptimisticLockingFailureException` khi version cũ. Tính năng hiện không cung cấp optimistic locking cho upsert.

Hãy viết test riêng cho `update` hoặc `save` để chứng minh optimistic locking đang được dùng ở những use case cần nó.

### 15.5. Test trên database thật

H2 có thể hỗ trợ upsert, nhưng không chứng minh PostgreSQL/MySQL/SQL Server/Oracle có behavior giống nhau. Chạy integration test với đúng database và JDBC driver production, đặc biệt cho:

- Conflict target.
- Generated/assigned ID.
- Kiểu dữ liệu và converter.
- Child delete/insert order.
- Unique constraint ngoài primary key.
- Transaction rollback khi một child statement thất bại.

## 16. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Hướng xử lý |
|---|---|---|
| Không tìm thấy method `upsert` khi compile | Spring Data Relational thấp hơn 4.1 | Nâng release train tương thích hoặc dùng custom SQL |
| `UnsupportedOperationException` | Dialect/DataAccessStrategy không hỗ trợ upsert | Kiểm tra database, dialect và custom strategy |
| Upsert báo thiếu ID | Entity chưa có identifier | Cấp ID trước khi gọi |
| Hàng không được insert khi dùng `save` | Entity bị nhận diện là existing và save chọn update | Dùng upsert khi cần insert-or-update theo ID |
| Upsert ghi đè field thành NULL | Truyền partial object | Truyền aggregate state đầy đủ hoặc dùng UPDATE có chọn cột |
| Child ID thay đổi sau upsert | Child rows bị delete/insert lại | Dùng update workflow riêng nếu cần giữ identity |
| Audit child bị tạo lại | Child insert/delete lifecycle được kích hoạt | Thiết kế audit theo đúng semantics hoặc không upsert cả aggregate |
| Không phát hiện concurrent modification | Upsert không hỗ trợ optimistic locking | Dùng `@Version` với save/update hoặc SQL version predicate |
| Hai database không cùng rollback | Khác DataSource/transaction manager | Xác định transaction boundary và consistency strategy |
| Custom SQL không gọi callback | Dùng JdbcTemplate trực tiếp | Thực hiện mapping/auditing/lifecycle rõ ràng trong custom path |

## 17. Nguyên tắc sử dụng

- `JdbcAggregateTemplate.upsert` được giới thiệu từ Spring Data Relational 4.1.
- Entity phải có ID được gán trước khi gọi.
- Dialect và DataAccessStrategy phải hỗ trợ native single-statement upsert.
- Database xử lý insert/update theo conflict của identifier; không cần SELECT tồn tại trước.
- Tài liệu 4.1 liệt kê PostgreSQL, H2, MySQL, MariaDB, SQL Server, Oracle, DB2 và HSQLDB; kiểm tra lại danh sách theo release cụ thể.
- Root được upsert bằng native action; child entities trong aggregate được xử lý qua delete/insert actions.
- `@Version` và optimistic locking hiện không được hỗ trợ bởi upsert.
- Truyền aggregate state đầy đủ; không dùng upsert như partial update.
- Dùng transaction khi root và child changes phải atomic.
- `AggregateReference` không tự cascade upsert sang aggregate khác.
- Khi version/dialect chưa hỗ trợ, dùng native SQL có chủ đích và hiểu rằng custom JDBC path không tự tái tạo toàn bộ aggregate lifecycle.
- Kiểm thử với database và JDBC driver thật, bao gồm conflict, child collection và rollback.

Upsert trong `JdbcAggregateTemplate` hữu ích cho đồng bộ dữ liệu có identifier được cấp sẵn và cần insert-or-update nguyên tử ở cấp root. Khả năng này bắt đầu từ Spring Data Relational 4.1 và phụ thuộc vào dialect có native upsert. Hãy cân nhắc kỹ child delete/insert behavior và giới hạn optimistic locking trước khi dùng cho aggregate có nhiều thành phần hoặc có concurrent writers.

## Tài liệu tham khảo

- [Spring Data Relational 4.1 — Persisting Entities](https://docs.spring.io/spring-data/relational/reference/4.1/jdbc/entity-persistence.html)
- [JdbcAggregateOperations API — upsert](https://docs.spring.io/spring-data/jdbc/docs/current/api/org/springframework/data/jdbc/core/JdbcAggregateOperations.html)
- [RelationalEntityUpsertWriter API](https://docs.spring.io/spring-data/jdbc/docs/current/api/org/springframework/data/relational/core/conversion/RelationalEntityUpsertWriter.html)
- [Spring Data Relational 4.1.0 Release Notes](https://github.com/spring-projects/spring-data-relational/releases/tag/4.1.0)





