# Checklist kiểm chứng cấu hình, SQL và luồng thực thi trước khi kết luận lỗi

Khi một thao tác Spring Data R2DBC thất bại, nguyên nhân có thể nằm ở nhiều lớp khác nhau: Spring tạo bean sai, repository được gắn với template không đúng, SQL sinh ra không khớp schema, tham số được bind sai kiểu, publisher chưa được subscribe, transaction manager không quản lý đúng `ConnectionFactory`, hoặc database/driver trả về lỗi mà tầng Service diễn giải chưa chính xác.

Một thông báo lỗi ở cuối pipeline không tự chỉ ra lớp gây lỗi. Ví dụ `DataAccessResourceFailureException` có thể bắt nguồn từ database không truy cập được, pool không cấp được connection, TLS/authentication thất bại hoặc network timeout. Một kết quả rỗng có thể là hành vi đúng của `Mono.empty()`, do predicate sai, do tenant context thiếu hoặc do repository đang truy vấn nhầm database. Một thao tác ghi không rollback có thể do transaction manager sai, nhưng cũng có thể vì publisher đã bị tách bằng `subscribe()` hoặc lỗi bị chuyển thành completion trước transaction boundary.

Vì vậy, trước khi kết luận, hãy kiểm chứng theo một trình tự có bằng chứng: cấu hình thực tế → repository và template → SQL cuối cùng → bind values và kiểu dữ liệu → subscription/reactive context → transaction/resource → hành vi database/driver → test tái hiện. Bài học này cung cấp checklist chẩn đoán có hệ thống, cách thu thập bằng chứng an toàn và cách phân biệt lỗi cấu hình với lỗi truy vấn hoặc lỗi dữ liệu.

## 1. Nguyên tắc chẩn đoán: đi từ bằng chứng đến kết luận

Không nên bắt đầu bằng cách sửa ngẫu nhiên repository, tăng pool size hoặc thêm `onErrorResume`. Trước hết hãy mô tả triệu chứng có thể tái hiện:

- Thao tác nào thất bại và với input nào?
- Lỗi xảy ra ở lúc khởi động, lúc subscribe, khi acquire connection, khi thực thi SQL hay khi đọc kết quả?
- Lỗi xảy ra với mọi request hay chỉ một tenant, một kiểu dữ liệu hoặc một dữ liệu cụ thể?
- Lỗi xuất hiện sau thay đổi cấu hình, migration, driver version hay code release nào?
- Có thể tái hiện trên database test cùng phiên bản không?
- Trạng thái dữ liệu cuối trong database là gì?

Một kết luận kỹ thuật nên chỉ rõ bằng chứng hỗ trợ nó. Ví dụ:

```text
Triệu chứng:
  OrderRepository.findById(42) trả dữ liệu của database billing.

Bằng chứng:
  - Repository thuộc package orders.repository.
  - Package được scan bởi BillingR2dbcConfiguration.
  - entityOperationsRef = billingEntityTemplate.
  - billingEntityTemplate dùng billingConnectionFactory.
  - Fixture ID 42 chỉ tồn tại trong billing database.

Kết luận:
  Repository được gắn nhầm R2dbcEntityOperations.
```

Kết luận như vậy có thể kiểm chứng và sửa đúng chỗ. Ngược lại, “R2DBC bị lỗi” hoặc “pool quá nhỏ” chưa phải chẩn đoán.

### 1.1. Phân biệt các lớp lỗi

| Lớp | Câu hỏi trọng tâm | Ví dụ bằng chứng |
|---|---|---|
| Spring configuration | Bean nào được tạo và được inject? | Bean names, qualifiers, condition report |
| Repository wiring | Repository dùng operations/template nào? | `basePackages`, `entityOperationsRef` |
| SQL generation | Câu SQL thực tế là gì? | SQL log, query instrumentation |
| Parameter binding | Giá trị và kiểu bind có đúng không? | Bind metadata, database error code |
| Reactive execution | Publisher có được subscribe và giữ context không? | `StepVerifier`, operator trace |
| Transaction | Manager và connection resource có khớp không? | Transaction manager, rollback test |
| Database/driver | Server và driver thực thi thế nào? | SQLSTATE, vendor code, server log |
| Data/schema | Schema và dữ liệu có đúng trạng thái không? | Migration version, `information_schema`, fixture |
| Performance | Nghẽn ở query, pool hay database? | Query plan, latency, pool metrics |

Một request có thể đi qua nhiều lớp, vì vậy hãy xác định điểm đầu tiên có bằng chứng sai thay vì chỉ xử lý exception cuối cùng.

## 2. Checklist ban đầu trước khi thay đổi code

Trước khi chỉnh sửa, ghi lại các thông tin sau:

- [ ] Thời điểm bắt đầu lỗi và release/build đang chạy.
- [ ] Endpoint, Service method hoặc Repository method gây lỗi.
- [ ] Input tối thiểu để tái hiện, đã loại bỏ dữ liệu nhạy cảm.
- [ ] Database product/version và môi trường đang kết nối.
- [ ] R2DBC driver, Spring Boot, Spring Data và R2DBC SPI versions.
- [ ] Active Spring profiles và nguồn cấu hình thực tế.
- [ ] Bean names của `ConnectionFactory`, `R2dbcEntityOperations` và `ReactiveTransactionManager`.
- [ ] SQL cuối cùng và loại lỗi database nếu đã thực thi.
- [ ] Trạng thái dữ liệu trước và sau thao tác.
- [ ] Có hay không transaction, retry, fallback, cancellation hoặc nested subscription.
- [ ] Có thể tái hiện bằng integration test độc lập không?

Không ghi password, token, URL có credential, thông tin cá nhân hoặc toàn bộ bind values nhạy cảm vào issue/log. Dùng ID giả, dữ liệu fixture và cấu hình đã che secret.

## 3. Xác nhận cấu hình Spring đang được sử dụng

Property trong file YAML không nhất thiết là giá trị cuối cùng. Environment variable, command-line argument, profile, config server hoặc test override có thể ghi đè nó.

### 3.1. Xác nhận active profile

Kiểm tra log khởi động và cấu hình `spring.profiles.active`. Xác nhận các property của R2DBC được lấy từ đúng profile. Nếu local chạy `dev` còn CI chạy `test`, không so sánh hai môi trường mà chưa biết khác biệt cấu hình.

Ví dụ cấu hình:

```yaml
spring:
  profiles:
    active: dev
  r2dbc:
    url: r2dbc:postgresql://localhost:5432/store
    username: store_app
    password: ${DB_PASSWORD}
```

Trong production, profile thường được cung cấp bởi môi trường triển khai. Không hard-code profile hoặc secret trong code chỉ để làm test chạy được.

### 3.2. Kiểm tra điều kiện auto-configuration

Khởi động Spring Boot với `--debug` để xem condition evaluation report. Báo cáo cho biết auto-configuration nào match, bị loại hoặc back off do bean/property nào. Điều này hữu ích khi ứng dụng không tạo bean R2DBC mặc định vì đã khai báo bean tùy chỉnh hoặc thiếu dependency.

Nếu có Actuator, endpoint `conditions` và `beans` có thể hỗ trợ điều tra. Bảo vệ endpoint này và chỉ expose theo chính sách vận hành; thông tin bean có thể tiết lộ cấu trúc nội bộ.

### 3.3. Xác nhận dependency thực tế

Sau khi nâng Spring Boot hoặc driver, kiểm tra dependency tree:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

Hoặc với Maven:

```bash
mvn dependency:tree
```

Tìm các thành phần:

- R2DBC driver của database đang dùng.
- R2DBC SPI.
- Spring Data Relational/R2DBC.
- Spring Framework.
- R2DBC Pool nếu ứng dụng dùng pool.
- JDBC driver nếu migration tool hoặc module khác cần JDBC.

Ưu tiên dependency management/BOM của Spring Boot. Không override một thành phần nền chỉ vì thấy một version mới hơn; cần xác nhận compatibility giữa SPI, driver và Spring Data.

### 3.4. Kiểm tra URL và loại connection

R2DBC URL phải dùng scheme của driver, ví dụ:

```text
r2dbc:postgresql://host:5432/database
r2dbc:mysql://host:3306/database
```

JDBC URL như `jdbc:postgresql://...` không phải R2DBC URL. Nếu ứng dụng có cả JDBC và R2DBC, kiểm tra mỗi bean đang sử dụng URL/driver đúng loại. Cùng một database server không có nghĩa hai connection path là một resource transaction.

### 3.5. Không in toàn bộ Environment hoặc URL có secret

Khi diagnostic, chỉ log tên profile, driver metadata, host/database đã được che thông tin và bean name. Không log password, token hoặc URI có credential. Nếu cần so sánh cấu hình, tạo bản đã redact trước khi chia sẻ.

## 4. Xác nhận bean và nhóm Repository

Với một database, auto-configuration thường đủ. Với nhiều database, cần kiểm tra từng repository được gắn với đúng `R2dbcEntityOperations`.

### 4.1. Liệt kê bean theo type

Có thể dùng breakpoint, Actuator được bảo vệ hoặc một diagnostic component tạm thời:

```java
@Component
class R2dbcBeanDiagnostics implements ApplicationRunner {

    private final ApplicationContext context;

    R2dbcBeanDiagnostics(ApplicationContext context) {
        this.context = context;
    }

    @Override
    public void run(ApplicationArguments args) {
        context.getBeansOfType(ConnectionFactory.class)
                .forEach((name, factory) ->
                        log.info("ConnectionFactory bean={} driver={}",
                                name, factory.getMetadata().getName()));

        context.getBeansOfType(R2dbcEntityOperations.class)
                .forEach((name, operations) ->
                        log.info("EntityOperations bean={} type={}",
                                name, operations.getClass().getName()));

        context.getBeansOfType(ReactiveTransactionManager.class)
                .forEach((name, manager) ->
                        log.info("Reactive transaction manager={} type={}",
                                name, manager.getClass().getName()));
    }
}
```

Đoạn code cần logger/import phù hợp với dự án. Chỉ log metadata không nhạy cảm. Không log `toString()` của connection factory nếu implementation có thể chứa URL hoặc credential.

### 4.2. Đọc `@EnableR2dbcRepositories`

Kiểm tra:

- `basePackages` hoặc `basePackageClasses` có bao phủ repository đang lỗi không?
- Có hai cấu hình cùng scan một package không?
- `entityOperationsRef` trỏ tới bean nào?
- `transactionManagerRef` trỏ tới manager nào?
- Base repository có cần `@NoRepositoryBean` không?
- Có repository interface concrete bị đặt nhầm annotation không?

Ví dụ cấu hình nhiều database:

```java
@Configuration
@EnableR2dbcRepositories(
        basePackages = "com.example.orders.repository",
        entityOperationsRef = "ordersEntityTemplate",
        transactionManagerRef = "ordersTransactionManager")
class OrdersR2dbcConfiguration {
}
```

Package orders không nên đồng thời bị cấu hình billing scan với `billingEntityTemplate`.

### 4.3. Lần theo template tới ConnectionFactory

```java
@Bean
R2dbcEntityOperations ordersEntityTemplate(
        @Qualifier("ordersConnectionFactory") ConnectionFactory factory) {
    return new R2dbcEntityTemplate(factory);
}
```

Kiểm tra template được tạo từ factory nào. Một lỗi thường gặp là template và transaction manager tự tạo hai `ConnectionFactory` instance riêng dù cùng URL. Cách đúng là khai báo factory một lần rồi inject cùng bean vào cả hai.

### 4.4. Dùng qualifier khi có nhiều bean cùng type

Nếu có nhiều `ConnectionFactory` hoặc `DatabaseClient`, injection cần `@Qualifier` hoặc một quy tắc `@Primary` rõ ràng. `@Primary` chỉ chọn ứng viên mặc định; nó không tự gắn repository vào đúng nhóm.

### 4.5. Kiểm chứng database bằng fixture marker

Để xác nhận repository thực sự truy vấn database nào, tạo dữ liệu marker khác nhau ở mỗi database:

- Orders database: `ORD-MARKER-ONLY-ORDERS`.
- Billing database: `INV-MARKER-ONLY-BILLING`.

Gọi repository tương ứng và xác nhận chỉ fixture của database đó xuất hiện. Đây là bằng chứng thực thi tốt hơn việc chỉ nhìn tên bean.

## 5. Xác nhận dialect và mapping metadata

Spring Data R2DBC sử dụng dialect theo database/driver để tạo bind marker và xử lý một số khác biệt SQL. Nếu dialect sai hoặc mapping metadata không đúng, SQL sinh ra có thể không hợp lệ.

### 5.1. Kiểm tra dialect được phân giải

Có thể kiểm tra dialect trong diagnostic test:

```java
R2dbcDialect dialect = DialectResolver.getDialect(connectionFactory);
assertThat(dialect).isNotNull();
```

Phân giải thành công chỉ cho biết framework nhận diện được dialect. Nó không chứng minh mọi SQL đặc thù đều được hỗ trợ.

### 5.2. Kiểm tra entity annotation

Với entity đang lỗi, kiểm tra:

- `@Table` trỏ đúng bảng/schema.
- `@Column` trỏ đúng tên cột.
- `@Id` đánh dấu khóa chính đúng.
- `@Version` có kiểu và semantics phù hợp nếu dùng optimistic locking.
- `@ReadOnlyProperty`, `@InsertOnlyProperty`, `@Transient` có đúng mục đích.
- Constructor/persistence constructor khớp property.
- Projection alias khớp tên property hoặc mapping callback.

Ví dụ:

```java
@Table("orders")
public record OrderEntity(
        @Id Long id,
        @Column("order_code") String orderCode,
        @Column("created_at") Instant createdAt,
        @Version Long version
) {
}
```

Một property Java tên `createdAt` không tự động chứng minh database có cột `created_at`; hãy xác nhận schema và mapping cùng nhau.

### 5.3. Phân biệt entity mapping và projection mapping

Query có thể trả entity đầy đủ, interface projection, DTO hoặc một row được map thủ công. Cơ chế mapping khác nhau. Nếu entity đọc đúng nhưng DTO có trường null, kiểm tra alias, constructor parameter và kiểu của `Row.get(...)` trước khi thay đổi schema.

## 6. Thu thập SQL thực tế trước khi sửa query

Tên method repository không cho biết chính xác SQL cuối cùng. Derived query, query annotation, `R2dbcEntityTemplate` và `DatabaseClient` có thể tạo SQL khác nhau.

### 6.1. Xác định nguồn tạo SQL

Phân loại thao tác:

- Derived repository method như `findByStatusAndCreatedAtAfter`.
- `@Query` khai báo SQL tường minh.
- `R2dbcEntityTemplate` query/update DSL.
- `DatabaseClient` với SQL thủ công.
- Custom repository implementation.
- Bulk update/delete hoặc stored procedure/function.

Mỗi đường đi có mapping, conversion và lifecycle khác nhau. Đừng giả định SQL custom đi qua toàn bộ entity callback giống `repository.save(entity)`.

### 6.2. Bật logging có chọn lọc

Trong profile debug/test, có thể tăng log level cho package Spring Data R2DBC hoặc driver theo phiên bản thư viện. Tên logger và chi tiết bind logging có thể thay đổi giữa phiên bản; kiểm tra tài liệu của đúng version đang chạy.

Ví dụ cấu hình minh họa:

```yaml
logging:
  level:
    org.springframework.data.r2dbc: DEBUG
    io.r2dbc.postgresql.QUERY: DEBUG
```

Logger cụ thể phụ thuộc driver. Không bật bind-value logging rộng rãi trên production nếu tham số có thông tin cá nhân, token, dữ liệu tài chính hoặc secret. Ưu tiên chỉ ghi SQL template, query name, correlation ID và thời gian.

### 6.3. Kiểm tra SQL trong database server

Database server có thể cung cấp query log, statement statistics hoặc slow query log. Những nguồn này giúp xác nhận SQL thực sự đến server, thời gian thực thi và plan. Hãy bật có chọn lọc vì query logging có thể tạo lượng log lớn hoặc lộ dữ liệu nhạy cảm.

### 6.4. Không kết luận từ SQL string trong source

Source có thể chứa `@Query`, nhưng framework còn xử lý bind marker, mapping metadata, pagination hoặc dialect. Với query quan trọng, thu thập SQL thực tế hoặc chạy test trên database mục tiêu để xác nhận semantics.

## 7. Checklist kiểm tra SQL và bind parameters

Khi SQL lỗi hoặc trả sai dữ liệu, kiểm tra theo thứ tự:

### 7.1. Tên bảng, schema và cột

- [ ] Bảng tồn tại trong đúng database/schema.
- [ ] Tên cột khớp schema thực tế.
- [ ] Case sensitivity/identifier quoting phù hợp database.
- [ ] Alias của select khớp projection.
- [ ] Migration đã chạy trên đúng database.
- [ ] Search path/default schema không làm query trỏ sang bảng khác.

### 7.2. Predicate và semantics

- [ ] Có đủ điều kiện tenant/authorization.
- [ ] `AND`/`OR` được nhóm đúng bằng ngoặc.
- [ ] Null semantics đúng (`IS NULL` thay vì `= NULL`).
- [ ] Khoảng thời gian dùng đúng inclusive/exclusive boundary.
- [ ] Collation/case sensitivity phù hợp.
- [ ] Empty collection có hành vi được định nghĩa.
- [ ] Sort có tie-breaker để paging ổn định.
- [ ] Count query đếm đúng entity logic sau join/group.

### 7.3. Bind marker và kiểu tham số

- [ ] Tên/position bind marker đúng với API/driver.
- [ ] Số lượng tham số khớp câu SQL.
- [ ] Thứ tự positional bind đúng.
- [ ] Null dùng `bindNull(name, type)` khi API yêu cầu.
- [ ] Kiểu Java tương thích với kiểu SQL.
- [ ] Decimal precision/scale không bị mất.
- [ ] Timestamp/offset/timezone được chuyển đổi đúng.
- [ ] UUID, JSON, array và enum có codec/converter phù hợp.
- [ ] List lớn không vượt giới hạn bind parameter.

Ví dụ bind null có kiểu:

```java
databaseClient.sql("""
        SELECT id
        FROM customers
        WHERE optional_code IS NOT DISTINCT FROM :code
        """)
        .bindNull("code", String.class)
        .map((row, metadata) -> row.get("id", Long.class))
        .all();
```

`IS NOT DISTINCT FROM` là cú pháp được PostgreSQL hỗ trợ; database khác có thể cần biểu thức tương đương. Ví dụ này nhấn mạnh bind null có kiểu, không phải cú pháp portable cho mọi hệ quản trị.

### 7.4. Generated values và default

- [ ] ID được database sinh có được driver trả về không?
- [ ] Cột `DEFAULT` có bị insert thành explicit `NULL` không?
- [ ] Generated column có bị ứng dụng cố ghi không?
- [ ] Trigger có sửa giá trị sau insert/update không?
- [ ] Entity bất biến có dùng instance trả về từ `save` không?
- [ ] Nếu driver không trả generated field, có đọc lại entity không?

Đừng giả định Java `null` luôn làm database áp dụng default. Nếu cột được đưa vào INSERT và bind `NULL`, database thường lưu null hoặc từ chối theo constraint.

## 8. Đối chiếu SQL với schema và dữ liệu thật

Khi SQL hợp lệ nhưng trả sai kết quả, hãy kiểm tra schema/data thay vì tiếp tục sửa query theo cảm tính.

### 8.1. Kiểm tra schema version

Nếu dùng Flyway/Liquibase hoặc migration tool khác, xác nhận version đã áp dụng trên đúng database. Một migration chạy ở local không chứng minh production hoặc test container đã chạy.

Kiểm tra:

- Bảng migration history.
- Schema/table được tạo trong database mục tiêu.
- Column type, nullability và default.
- Primary key, foreign key, unique/check constraints.
- Index và generated/identity configuration.
- Trigger/function nếu có.

### 8.2. Kiểm tra dữ liệu trước và sau thao tác

Với thao tác ghi, chụp trạng thái cần thiết trước khi gọi service, sau đó đọc lại qua query độc lập. Điều này giúp phân biệt:

- Không có lệnh ghi được thực thi.
- Lệnh ghi thất bại.
- Lệnh ghi thành công nhưng mapping response sai.
- Lệnh ghi đã commit một phần.
- Transaction rollback đúng nhưng test đang đọc từ cache hoặc connection có snapshot khác.

Không dựa duy nhất vào object Java được trả về nếu cần xác nhận database state. Với entity bất biến hoặc generated fields, instance trả về và row lưu có thể khác nếu driver không trả mọi giá trị.

### 8.3. Dùng fixture có natural key

Tạo fixture dễ tìm như `ORD-DIAG-001` hoặc `customer@example.test`. Tránh giả định identity ID luôn là 1. Dữ liệu test cần có cả trường hợp thỏa và không thỏa predicate để phát hiện query quá rộng hoặc thiếu điều kiện.

### 8.4. Kiểm tra tenant isolation

Tạo hai tenant với dữ liệu tương tự nhau. Gọi query của tenant A và xác nhận không có hàng tenant B. Nếu dùng tenant Context hoặc PostgreSQL RLS, kiểm tra cả ứng dụng truyền đúng tenant lẫn database policy thực sự được áp dụng trong transaction.

## 9. Kiểm chứng reactive execution và subscription

R2DBC API trả `Mono`/`Flux`; tạo publisher chưa có nghĩa câu SQL đã chạy. SQL được thực thi khi có subscription.

### 9.1. Kiểm tra publisher có được subscribe

Ví dụ sai:

```java
public Mono<Void> createCustomer(CustomerEntity customer) {
    customerRepository.save(customer);
    return Mono.empty();
}
```

Publisher `save` được tạo nhưng không được kết hợp vào kết quả trả về, nên thao tác ghi không được thực thi qua luồng đó.

Ví dụ đúng:

```java
public Mono<Void> createCustomer(CustomerEntity customer) {
    return customerRepository.save(customer).then();
}
```

### 9.2. Không tạo nested subscription

Ví dụ sai:

```java
public Mono<Void> placeOrder(OrderEntity order) {
    orderRepository.save(order).subscribe();
    return Mono.empty();
}
```

Subscription riêng không còn nằm trong pipeline mà caller quản lý. Error, cancellation, transaction và Reactor Context có thể bị tách khỏi luồng chính.

Kết hợp publisher:

```java
public Mono<Void> placeOrder(OrderEntity order) {
    return orderRepository.save(order).then();
}
```

### 9.3. Tránh block trong reactive service

`block()` có thể làm chặn thread và phá vỡ context/transaction propagation. Không dùng trong controller/service reactive. Trong test, ưu tiên `StepVerifier`; nếu một test setup imperative cần `.block()`, chỉ thực hiện ở thread test bình thường và không gọi từ event-loop thread.

### 9.4. Xác nhận lỗi có được phát ra hay bị nuốt

Các operator như `onErrorResume`, `onErrorReturn` có thể biến error signal thành completion/giá trị. Nếu thao tác ghi thất bại nhưng lỗi bị fallback thành một object, caller có thể tưởng rằng ghi thành công.

Kiểm tra operator chain trước khi transaction boundary và trước khi response được trả về. Chỉ fallback khi có phương án nghiệp vụ hợp lệ; giữ nguyên lỗi nếu cần rollback hoặc báo thất bại.

### 9.5. Xác nhận Reactor Context

Nếu service cần tenant, actor hoặc correlation ID, đọc bằng `deferContextual` ở thời điểm subscription. Kiểm tra `contextWrite` đặt đúng vị trí; nó cung cấp context cho các operator upstream.

Không giả định mọi subscription đều bắt nguồn từ WebFlux. Scheduler, message consumer và test có thể cần tự thiết lập context. Nếu thiếu tenant context, fail closed bằng lỗi rõ ràng thay vì query không có tenant predicate.

## 10. Kiểm chứng transaction manager và resource

Khi một thao tác không rollback hoặc chỉ một phần dữ liệu được ghi, hãy xác nhận manager và connection factory trước khi thay đổi business logic.

### 10.1. Xác nhận đúng loại transaction manager

R2DBC cần `ReactiveTransactionManager`, thường là `R2dbcTransactionManager`. `DataSourceTransactionManager` và `JpaTransactionManager` quản lý resource JDBC/JPA, không tự quản lý R2DBC connection.

### 10.2. Xác nhận cùng ConnectionFactory

Repository/template và transaction manager phải cùng tham chiếu bean `ConnectionFactory` tương ứng. Hai factory có cùng URL nhưng là hai pool/instance khác nhau có thể không chia sẻ transaction resource.

### 10.3. Chỉ định manager khi có nhiều manager

```java
@Transactional(transactionManager = "ordersTransactionManager")
public Mono<OrderEntity> createOrder(OrderEntity order) {
    return orderRepository.save(order);
}
```

Nếu dùng `TransactionalOperator`, tạo operator từ đúng reactive manager:

```java
TransactionalOperator operator =
        TransactionalOperator.create(ordersTransactionManager);

return orderRepository.save(order).as(operator::transactional);
```

### 10.4. Kiểm tra transaction boundary

- [ ] Method transactional trả `Mono`/`Flux` và publisher được trả về caller.
- [ ] Không có `subscribe()` hoặc `block()` tạo execution riêng.
- [ ] Repository dùng cùng factory với transaction manager.
- [ ] Không có operator nuốt lỗi trước khi transaction hoàn tất.
- [ ] Các thao tác cần atomicity thực sự dùng cùng database/resource.
- [ ] Test đọc trạng thái cuối qua connection/transaction độc lập.

### 10.5. Tạo lỗi có kiểm soát để chứng minh rollback

Một integration test nên:

1. Bắt đầu transaction.
2. Thực hiện một ghi hợp lệ.
3. Cố ý gây lỗi ở bước tiếp theo.
4. Xác nhận publisher phát error.
5. Đọc lại dữ liệu qua một transaction độc lập.
6. Xác nhận ghi đầu tiên đã rollback.

Chỉ thấy exception không chứng minh rollback. Dữ liệu cuối mới là bằng chứng.

### 10.6. Không giả định transaction bao trùm nhiều database

Một `R2dbcTransactionManager` quản lý một `ConnectionFactory`. Nếu một service ghi orders database rồi billing database, transaction orders không tự rollback billing. Xác định rõ cần saga, outbox, compensation hay distributed transaction được hỗ trợ.

## 11. Kiểm tra pool, timeout và kết nối

Khi lỗi xảy ra trước khi database thực thi SQL, kiểm tra connection acquisition và pool.

### 11.1. Phân biệt acquire timeout với query timeout

- **Acquire timeout:** ứng dụng chờ lấy connection từ pool quá lâu.
- **Connect timeout:** không thiết lập được connection tới server.
- **Statement/query timeout:** SQL đã gửi nhưng không hoàn tất trong giới hạn.
- **Lock timeout:** query chờ lock quá lâu.

Các timeout này có nguyên nhân và cách xử lý khác nhau. Không tăng tất cả timeout cùng lúc.

### 11.2. Quan sát pool metrics

Theo dõi:

- Active/allocated connections.
- Idle connections.
- Pending borrowers.
- Acquire latency và timeout count.
- Connection creation/validation failure.
- Thời gian connection bị giữ trong transaction.

Nếu pending borrowers tăng nhưng database query latency thấp, có thể connection bị giữ quá lâu hoặc pool quá nhỏ. Nếu database CPU/lock đã bão hòa, tăng pool có thể làm tình hình tệ hơn.

### 11.3. Kiểm tra connection leak và cancellation

Một publisher bị bỏ quên, nested subscription hoặc luồng streaming không được tiêu thụ có thể giữ tài nguyên lâu hơn dự kiến. Kiểm tra connection có được đóng/trả về pool khi complete, error và cancel. Nếu dùng LOB hoặc stream kết quả lớn, xác nhận cancellation cleanup với driver cụ thể.

### 11.4. Kiểm tra TLS và authentication

Nếu connection không tạo được, xác nhận hostname, port, DNS, certificate chain, TLS mode, authentication method và credential rotation. Không tắt certificate verification để “thử xem có chạy không” trong môi trường production. Dùng cấu hình test riêng và certificate phù hợp.

## 12. Đọc exception và mã lỗi database

Exception của Spring thường là lớp abstraction trên lỗi driver. Khi cần chẩn đoán sâu, giữ lại:

- Exception type của Spring.
- Cause chain.
- SQLSTATE hoặc vendor error code nếu driver cung cấp.
- Tên constraint/table/column nếu an toàn để ghi log.
- Query name hoặc operation name.
- Correlation/trace ID.

Không viết logic nghiệp vụ dựa vào message text nếu có mã lỗi ổn định hơn. Message có thể thay đổi theo driver version hoặc ngôn ngữ server.

### 12.1. Nhóm lỗi thường gặp

| Nhóm | Ví dụ | Hướng kiểm tra |
|---|---|---|
| Connection | refused, reset, timeout | Network, DNS, TLS, credential, pool |
| Syntax | syntax error, missing relation/column | SQL cuối, dialect, schema version |
| Constraint | unique, foreign key, check, not-null | Fixture, race condition, constraint semantics |
| Conversion | cannot decode/bind type | Java/SQL type, codec, converter |
| Transaction | deadlock, serialization failure | Isolation, lock order, retry policy |
| Resource | too many connections, pool acquire timeout | Pool metrics, concurrency, transaction duration |
| Cancellation | statement cancelled, subscriber cancelled | Timeout/cancel path, driver cleanup |

### 12.2. Giữ cause khi chuyển lỗi

Nếu chuyển exception persistence thành domain exception, giữ cause:

```java
return repository.save(entity)
        .onErrorMap(DuplicateKeyException.class,
                error -> new CustomerConflictException(
                        entity.email(), error));
```

Không bỏ cause nếu cần SQLSTATE hoặc vendor code để điều tra. Đồng thời, không trả thông tin nội bộ của database trực tiếp cho client.

## 13. Kiểm tra query plan và hiệu năng

Nếu query trả đúng nhưng chậm, không kết luận do R2DBC chỉ vì API reactive. Database vẫn phải parse, plan, scan, join, sort và đọc dữ liệu.

### 13.1. Chạy EXPLAIN trên database mục tiêu

Với PostgreSQL:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, order_code, created_at
FROM orders
WHERE tenant_id = 42
  AND status = 'PAID'
ORDER BY created_at DESC, id DESC
LIMIT 50;
```

Xem actual rows, estimated rows, buffers, sort spill, join strategy và thời gian. `EXPLAIN ANALYZE` thực thi câu query; chỉ dùng với query an toàn và dữ liệu/môi trường phù hợp.

### 13.2. Không ép mọi query phải dùng index

Sequential scan có thể hợp lý nếu bảng nhỏ hoặc predicate trả phần lớn dữ liệu. Kiểm tra chi phí và workload thay vì assert cứng một loại scan.

### 13.3. Phát hiện N+1

Đếm số query trong một use case. Nếu lấy 100 orders rồi gọi repository lấy customer riêng cho từng order, số query có thể tăng theo số hàng. Dùng join/projection hoặc batch lookup nếu phù hợp.

### 13.4. Phân biệt query chậm và chờ pool

Đo riêng thời gian acquire connection, thời gian execute SQL và thời gian mapping/stream response. Một request chậm có thể chờ pool trước khi query bắt đầu; chỉ nhìn tổng HTTP latency sẽ không phân biệt được.

## 14. Tái hiện bằng integration test nhỏ nhất

Khi đã có giả thuyết, tạo test tối thiểu trên database mục tiêu. Test nên có fixture nhỏ, deterministic và chứng minh một lớp cụ thể.

### 14.1. Test repository bằng StepVerifier

```java
@Test
void findsOrderByCode() {
    StepVerifier.create(orderRepository.findByOrderCode("ORD-DIAG-001"))
            .assertNext(order -> {
                assertThat(order.orderCode()).isEqualTo("ORD-DIAG-001");
                assertThat(order.status()).isEqualTo("PAID");
            })
            .verifyComplete();
}
```

Test này cần schema/fixture đã được tạo trong database thật hoặc Testcontainers. Nó xác nhận query và mapping ở mức repository.

### 14.2. Test empty khác error

```java
StepVerifier.create(customerRepository.findById(999999L))
        .verifyComplete();
```

Nếu repository không tìm thấy bản ghi, `Mono.empty()` hoàn tất bình thường. Đừng nhầm trường hợp này với lỗi connection. Nếu Service chuyển empty thành not-found, test Service riêng bằng `switchIfEmpty`.

### 14.3. Test bind null và kiểu dữ liệu

Tạo cột nullable và kiểm tra explicit null, sau đó kiểm tra `DEFAULT` bằng câu insert bỏ cột. Hai test riêng giúp phân biệt lỗi mapping với semantics database.

### 14.4. Test transaction rollback

Tạo một service transactional, cố ý làm bước sau thất bại và đọc lại trạng thái bằng transaction độc lập. Test không nên chỉ mock repository vì mock không chứng minh database rollback.

### 14.5. Test nhiều repository group

Với nhiều database, tạo marker fixture riêng trong mỗi database. Gọi từng repository và xác nhận nó chỉ nhìn thấy marker của database được chỉ định. Đây là cách phát hiện `entityOperationsRef` hoặc package scanning sai.

## 15. Thu thập bằng chứng trong production an toàn

Trong production, mục tiêu là có đủ thông tin để điều tra nhưng không làm lộ dữ liệu hoặc tăng tải quá mức.

### 15.1. Gắn correlation ID

Ghi correlation/trace ID cùng operation name để nối log giữa WebFilter, Service, repository và downstream call. Không dùng correlation ID làm danh tính hoặc token xác thực.

### 15.2. Ghi operation metadata thay vì payload

Log:

- Repository/query name.
- Database group/bean logical name.
- Duration và row count.
- Exception class, SQLSTATE/vendor code nếu an toàn.
- Correlation/trace ID.
- Tenant ID đã được phép log theo chính sách, có thể hash/pseudonymize.

Tránh log raw SQL parameter nếu chứa PII, secret hoặc dữ liệu tài chính. Nếu cần debug một giá trị, dùng fixture giả hoặc redacted value.

### 15.3. Bật diagnostic logging theo thời gian giới hạn

SQL/driver debug log có thể rất lớn. Bật có chọn lọc, trong khoảng thời gian ngắn, trên một instance hoặc môi trường staging trước. Ghi rõ thời điểm bật/tắt và kiểm tra log không chứa secret.

### 15.4. Không chạy query chẩn đoán nặng trên giờ cao điểm

`EXPLAIN ANALYZE`, full table count hoặc query kiểm tra dữ liệu toàn bảng có thể gây tải. Dùng replica/staging hoặc giới hạn phạm vi khi phù hợp. Đánh giá tác động trước khi chạy trên production.

## 16. Bảng quyết định nhanh theo triệu chứng

| Triệu chứng | Kiểm chứng đầu tiên | Bằng chứng cần có |
|---|---|---|
| ApplicationContext không khởi động | Bean, profile, dependency, condition report | Missing/ambiguous bean và nguồn cấu hình |
| Repository không được tạo | Package scan và repository factory | Base package, `entityOperationsRef` |
| Query chạy nhầm database | Template → ConnectionFactory | Bean chain và marker fixture |
| SQL báo thiếu bảng/cột | Schema version và SQL thực tế | Migration history, schema metadata |
| Query trả quá nhiều/ít hàng | Predicate, tenant, join, null semantics | Fixture có hàng thỏa/không thỏa |
| Projection có trường null | Alias, constructor, conversion | SQL result metadata và DTO mapping |
| Giá trị null/default sai | Explicit NULL vs omitted column | SQL insert và row lưu thực tế |
| Publisher không ghi dữ liệu | Subscription và composition | Không có nested/missing subscribe |
| Transaction không rollback | Manager, factory, pipeline | Rollback test và trạng thái cuối |
| Một phần database commit | Nhiều factory/manager | Resource boundary và transaction design |
| Pool acquire timeout | Pool metrics và connection lifecycle | Active/pending/acquire latency |
| Query chậm | Query plan và phase timing | EXPLAIN, database metrics, acquire time |
| Lỗi chỉ trong CI | Profile, dependency, database image | Version/configuration diff |

## 17. Quy trình chẩn đoán từ đầu đến cuối

Có thể dùng trình tự sau cho một incident hoặc bug report:

1. Ghi lại triệu chứng, input tối thiểu, release và thời điểm bắt đầu.
2. Phân loại lỗi xảy ra ở startup, connection, SQL execution, mapping, transaction hay response.
3. Xác nhận active profile, property source, database URL đã redact và dependency versions.
4. Liệt kê bean `ConnectionFactory`, `R2dbcEntityOperations` và `ReactiveTransactionManager`.
5. Lần từ repository package qua `@EnableR2dbcRepositories`, `entityOperationsRef` tới template/factory.
6. Xác nhận transaction manager dùng cùng factory và được chọn đúng.
7. Thu thập SQL cuối cùng, bind marker và kiểu tham số an toàn.
8. Đối chiếu tên bảng/cột, schema version, constraints, defaults và generated columns.
9. Xác nhận publisher được subscribe, không có nested subscription và context không bị thiếu.
10. Nếu có transaction, tạo lỗi có kiểm soát và đọc trạng thái cuối từ connection độc lập.
11. Kiểm tra driver/database error code, pool metrics, timeout và query plan tùy triệu chứng.
12. Tạo integration test nhỏ nhất tái hiện trên database mục tiêu.
13. Sửa lớp đầu tiên có bằng chứng sai; tránh thay đổi nhiều lớp cùng lúc.
14. Chạy test liên quan và xác nhận triệu chứng đã hết trong cùng điều kiện.
15. Ghi kết luận, nguyên nhân gốc, bằng chứng, phạm vi ảnh hưởng và cách phòng ngừa.

## 18. Mẫu ghi nhận kết quả điều tra

Một báo cáo ngắn nhưng có thể kiểm chứng nên có dạng:

```text
Symptom:
  Mô tả lỗi quan sát được và request tối thiểu.

Environment:
  Spring Boot / Spring Data / driver / R2DBC SPI
  Database product + version
  Active profile (không chứa secret)

Evidence:
  Repository package và bean operations
  ConnectionFactory logical name/driver metadata
  Transaction manager được chọn
  SQL/query name và SQLSTATE/vendor code
  Schema/migration version
  Kết quả test hoặc trạng thái database cuối

Root cause:
  Lớp gây lỗi và lý do cụ thể.

Fix:
  Thay đổi tối thiểu và vì sao nó sửa nguyên nhân.

Verification:
  Test tái hiện trước/sau
  Integration/transaction/performance check liên quan

Residual risk:
  Điều kiện chưa được xác minh hoặc phạm vi chưa bao phủ.
```

Không ghi kết luận “đã sửa” chỉ vì request thử một lần thành công. Lặp lại test trong cùng điều kiện và kiểm tra trạng thái cuối.

## 19. Những kết luận vội vàng cần tránh

### “R2DBC không hỗ trợ transaction”

Trước hết xác nhận đúng reactive transaction manager, cùng `ConnectionFactory`, publisher không bị tách và database hỗ trợ transaction semantics cần thiết.

### “Repository bị lỗi”

Kiểm tra repository được tạo từ template nào, SQL cuối là gì và driver nhận bind values nào.

### “Database không có dữ liệu”

Xác nhận database/schema, tenant predicate, active profile và fixture marker trước khi kết luận.

### “Pool nhỏ nên query timeout”

Phân biệt acquire timeout, connect timeout, statement timeout và lock wait. Quan sát metrics trước khi đổi pool size.

### “Publisher không chạy vì WebFlux”

Kiểm tra subscription, operator composition, cancellation và nested subscribe. Reactive không có nghĩa publisher tự chạy khi được tạo.

### “Thêm onErrorResume là hết lỗi”

Fallback có thể che mất lỗi gốc, làm transaction commit ngoài dự kiến hoặc trả dữ liệu giả. Chỉ dùng khi có quy tắc phục hồi hợp lệ.

### “Test mock đã pass nên SQL đúng”

Mock không thực thi database. Cần integration test trên đúng engine/driver để xác nhận SQL và mapping.

## 20. Checklist trước khi kết luận nguyên nhân

- [ ] Đã tái hiện lỗi với input tối thiểu và biết chính xác thời điểm lỗi.
- [ ] Đã xác nhận active profile và cấu hình thực tế, không chỉ đọc YAML.
- [ ] Đã xác nhận database product/version và driver/framework versions.
- [ ] Đã kiểm tra condition report và các bean persistence được tạo.
- [ ] Đã xác định repository thuộc package scan nào.
- [ ] Đã lần `entityOperationsRef` tới template và `ConnectionFactory`.
- [ ] Đã xác nhận transaction manager dùng cùng `ConnectionFactory` khi cần.
- [ ] Đã thu thập SQL cuối cùng hoặc bằng chứng tương đương.
- [ ] Đã kiểm tra bind marker, kiểu tham số, null và collection behavior.
- [ ] Đã đối chiếu SQL với schema/migration/constraint thực tế.
- [ ] Đã xác nhận publisher được subscribe và không bị tách bằng `subscribe()`/`block()`.
- [ ] Đã kiểm tra Reactor Context/tenant/actor nếu query phụ thuộc chúng.
- [ ] Đã kiểm tra lỗi có bị fallback/nuốt trước transaction boundary không.
- [ ] Đã xác nhận trạng thái database sau success và failure.
- [ ] Đã phân biệt pool acquire, connect, statement và lock timeout.
- [ ] Đã xem driver/database error code và query plan nếu cần.
- [ ] Đã có integration test tái hiện trên database mục tiêu.
- [ ] Đã sửa đúng lớp có bằng chứng sai và chạy lại test liên quan.
- [ ] Đã ghi nguyên nhân gốc, bằng chứng và giới hạn chưa xác minh.

Chẩn đoán Spring Data R2DBC hiệu quả là quá trình kiểm chứng từng ranh giới của hệ thống. Hãy xác nhận Spring tạo đúng bean, repository dùng đúng template, template và transaction manager chia sẻ đúng connection factory, SQL và bind values khớp schema, publisher thực sự được thực thi trong context dự kiến, rồi mới kết luận database hoặc driver gây lỗi. Khi có integration test tái hiện và trạng thái dữ liệu cuối làm bằng chứng, việc sửa lỗi sẽ chính xác hơn và ít tạo ra thay đổi phụ không cần thiết.
