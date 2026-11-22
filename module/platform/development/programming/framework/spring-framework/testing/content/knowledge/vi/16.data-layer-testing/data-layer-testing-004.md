# Khác biệt SQL dialect, kiểu dữ liệu và transaction isolation

Kiểm thử tầng dữ liệu cần xác nhận ứng dụng lưu, truy vấn và cập nhật dữ liệu đúng trên hệ quản trị cơ sở dữ liệu mà hệ thống thực sự sử dụng. Một repository test có thể chạy thành công trên database nhúng nhưng thất bại khi triển khai lên PostgreSQL, MySQL, SQL Server hoặc Oracle vì mỗi hệ quản trị có SQL dialect, kiểu dữ liệu, quy tắc chuyển đổi và hành vi transaction riêng.

Khác biệt không chỉ nằm ở cú pháp câu lệnh. Các database có thể xử lý khác nhau đối với `BOOLEAN`, `UUID`, JSON, timestamp có timezone, số thập phân, identity/sequence, collation, giá trị `NULL`, unique constraint và mức cô lập transaction. Một test chạy trên database thay thế có thể không phát hiện lỗi chỉ xuất hiện ở production. Vì vậy, cần chọn môi trường test theo câu hỏi cần kiểm chứng, đồng thời thiết kế test để phân biệt lỗi mapping, lỗi SQL dialect và lỗi do transaction isolation.

## 1. SQL dialect là gì?

SQL là ngôn ngữ truy vấn có chuẩn chung, nhưng mỗi hệ quản trị triển khai và mở rộng chuẩn theo cách riêng. **SQL dialect** là tập cú pháp, hàm, kiểu dữ liệu và quy tắc SQL cụ thể mà một database hỗ trợ.

Một số khác biệt thường gặp:

| Chủ đề | Ví dụ khác biệt |
|---|---|
| Giới hạn số dòng | PostgreSQL/MySQL hỗ trợ `LIMIT`; SQL Server thường dùng `TOP` hoặc `OFFSET ... FETCH` |
| Sinh khóa | PostgreSQL hỗ trợ sequence; MySQL thường dùng `AUTO_INCREMENT`; SQL Server có `IDENTITY` và `SEQUENCE` |
| Ghép chuỗi | `||`, `CONCAT(...)` hoặc toán tử `+` tùy database và kiểu dữ liệu |
| Kiểu Boolean | Có database có kiểu `BOOLEAN`; database khác lưu dưới dạng `BIT` hoặc biểu diễn số |
| JSON | Kiểu và toán tử truy vấn JSON khác nhau, ví dụ `jsonb` trong PostgreSQL và kiểu JSON của MySQL |
| Ngày giờ | Kiểu `TIMESTAMP`, `DATETIME`, `TIMESTAMP WITH TIME ZONE` có ngữ nghĩa khác nhau |
| Upsert | `ON CONFLICT`, `ON DUPLICATE KEY UPDATE`, `MERGE` hoặc cú pháp riêng |
| Hàm chuỗi/ngày giờ | Tên hàm, tham số và kiểu kết quả có thể khác nhau |
| Identifier | Quy tắc viết hoa/thường, quote và từ khóa dành riêng khác nhau |

Một repository dùng JPQL hoặc Criteria API thường giảm phụ thuộc vào cú pháp riêng của database vì Hibernate chuyển biểu thức sang SQL phù hợp với dialect. Tuy nhiên, native SQL, function tự định nghĩa, migration script và một số mapping kiểu dữ liệu vẫn phụ thuộc hệ quản trị cụ thể.

## 2. Phân biệt kiểm thử logic repository và kiểm thử dialect thật

Không phải test nào cũng cần chạy trên database production. Hãy xác định điều cần chứng minh:

- Repository thực hiện đúng quy tắc tìm kiếm, lọc, phân trang và sắp xếp hay không.
- Entity mapping có tương thích với kiểu dữ liệu và constraint của database thật hay không.
- Native query có đúng cú pháp và trả về đúng kiểu dữ liệu trên dialect đích hay không.
- Migration có tạo schema đúng trên phiên bản database đang triển khai hay không.
- Transaction isolation có ngăn được các anomaly mà nghiệp vụ không chấp nhận hay không.

Một test với database nhúng có thể phù hợp để kiểm tra mapping đơn giản hoặc logic repository ít phụ thuộc dialect. Khi test liên quan đến native SQL, JSON operator, sequence, collation, locking hoặc isolation, nên chạy trên cùng hệ quản trị và phiên bản tương thích với production.

| Mục tiêu kiểm thử | Môi trường phù hợp |
|---|---|
| Unit test service, không kiểm tra SQL | Mock/fake repository |
| Repository query đơn giản, ít phụ thuộc dialect | Database nhúng có thể đủ cho phản hồi nhanh |
| Native SQL hoặc function riêng của database | Cùng database engine với production |
| Kiểu dữ liệu đặc thù, sequence, JSON, collation | Database thật qua Testcontainers hoặc môi trường tương đương |
| Migration và schema production | Chạy migration trên đúng engine/version |
| Transaction isolation và concurrency | Database hỗ trợ đúng isolation/locking đang triển khai |

Database nhúng không phải bản mô phỏng hoàn hảo của database production. Ví dụ, H2 có thể chấp nhận một số cú pháp tương thích nhưng vẫn khác PostgreSQL hoặc MySQL về kiểu dữ liệu, function, constraint và transaction. Việc test qua trên H2 chỉ chứng minh hành vi trên H2.

## 3. SQL portable và SQL phụ thuộc dialect

Khi viết repository, có thể chọn JPQL, Criteria API, Spring Data derived query hoặc native SQL. Mỗi lựa chọn có mức phụ thuộc database khác nhau.

### 3.1. Derived query và JPQL

Spring Data JPA có thể tạo query từ tên phương thức:

```java
interface CustomerRepository extends JpaRepository<Customer, Long> {
    List<Customer> findByStatusAndCreatedAtAfter(
            CustomerStatus status,
            Instant createdAt);
}
```

JPQL truy vấn entity và thuộc tính Java thay vì bảng/cột trực tiếp:

```java
@Query("""
       select o
       from Order o
       where o.customerId = :customerId
         and o.status = :status
       order by o.createdAt desc
       """)
List<Order> findRecentOrders(
        @Param("customerId") String customerId,
        @Param("status") OrderStatus status);
```

Hibernate dịch JPQL thành SQL dựa trên dialect và mapping. Cách này thường giúp query ít phụ thuộc cú pháp database hơn. Tuy vậy, hành vi vẫn có thể chịu ảnh hưởng bởi collation, kiểu dữ liệu, null semantics, precision timestamp, generated SQL và khả năng hỗ trợ tính năng của provider.

### 3.2. Native query

Native query cho phép viết SQL trực tiếp:

```java
@Query(value = """
        select *
        from customer
        where status = :status
        order by created_at desc
        limit :pageSize
        """, nativeQuery = true)
List<Customer> findLatestCustomers(
        @Param("status") String status,
        @Param("pageSize") int pageSize);
```

`LIMIT` không portable sang mọi database. Nếu production dùng SQL Server, query trên có thể không chạy. Khi dùng native query, hãy kiểm tra trên đúng dialect đích và tránh dựa vào database nhúng để xác nhận tính đúng đắn của cú pháp.

Nếu cần hỗ trợ nhiều dialect, có thể:

- Dùng JPQL/Criteria API nếu biểu thức đáp ứng được yêu cầu.
- Dùng API phân trang của Spring Data thay vì tự viết `LIMIT`.
- Tách implementation repository theo database khi cú pháp khác nhau đáng kể.
- Dùng Hibernate function hoặc abstraction phù hợp, nhưng vẫn test generated SQL trên từng dialect cần hỗ trợ.

Không nên hy sinh tính rõ ràng của query chỉ để tránh mọi khác biệt dialect. Nếu hệ thống chủ đích phụ thuộc một database cụ thể, viết SQL tận dụng tính năng của database đó là hợp lý; điều quan trọng là test đúng engine và version.

## 4. Cấu hình Hibernate dialect và database metadata

Hibernate cần biết database để sinh SQL tương thích. Trong nhiều cấu hình hiện đại, Hibernate có thể nhận diện dialect từ JDBC metadata của database. Spring Boot thường cấu hình datasource và để Hibernate xác định dialect phù hợp.

Trong phần lớn trường hợp, không cần khai báo cứng `hibernate.dialect` nếu metadata đủ để nhận diện. Khai báo dialect cũ hoặc không tương thích có thể làm Hibernate sinh SQL không phù hợp với database/version đang chạy.

Khi cần cấu hình rõ ràng, hãy dùng dialect đúng với phiên bản Hibernate và database đang sử dụng. Tên class dialect có thể thay đổi giữa các major version Hibernate; không sao chép cấu hình từ một phiên bản cũ mà chưa kiểm tra tài liệu của phiên bản hiện tại.

### 4.1. Test trên database thật với Testcontainers

Testcontainers giúp chạy database engine thật trong container dùng riêng cho test. Ví dụ PostgreSQL:

```java
@DataJpaTest
@Testcontainers
@AutoConfigureTestDatabase(replace = AutoConfigureTestDatabase.Replace.NONE)
class CustomerRepositoryPostgresTest {
    @Container
    static final PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }

    @Autowired
    private CustomerRepository customers;

    @Test
    void persistsCustomerUsingPostgres() {
        Customer saved = customers.save(new Customer("Lan"));
        customers.flush();

        assertThat(customers.findById(saved.getId())).isPresent();
    }
}
```

`@AutoConfigureTestDatabase(replace = Replace.NONE)` yêu cầu Spring Boot giữ datasource đã cấu hình thay vì thay bằng embedded database. `@DynamicPropertySource` truyền JDBC URL và credential mà container cấp lúc runtime. Container static thường được dùng chung cho test class.

Ví dụ trên cần dependency Testcontainers phù hợp, gồm module PostgreSQL và JUnit Jupiter integration. Tag image nên được cố định theo phiên bản tương thích với production; tránh dùng tag `latest` vì database có thể thay đổi hành vi giữa các lần chạy.

### 4.2. Kiểm thử nhiều database engine

Nếu ứng dụng hỗ trợ nhiều engine, cần chạy test riêng trên từng engine mà sản phẩm cam kết hỗ trợ. Có thể tổ chức test suite theo profile hoặc build task để chọn database container tương ứng.

Không dùng một database nhúng duy nhất rồi suy luận rằng mọi dialect đều hoạt động. Một query có thể hợp lệ trên PostgreSQL nhưng lỗi trên MySQL, hoặc ngược lại. Kiểm thử theo ma trận engine/version giúp phát hiện sai khác trước khi triển khai.

## 5. Khác biệt kiểu dữ liệu và mapping

Kiểu dữ liệu Java và kiểu dữ liệu SQL không phải lúc nào cũng tương ứng một-một. Hibernate thực hiện chuyển đổi dựa trên mapping, JDBC driver và database dialect. Những khác biệt về precision, timezone, binary representation hoặc semantics có thể làm dữ liệu thay đổi khi ghi và đọc lại.

### 5.1. `BOOLEAN` và giá trị logic

Java có `boolean`/`Boolean`, nhưng database có thể biểu diễn logic bằng `BOOLEAN`, `BIT`, hoặc kiểu số. Một số database không có kiểu boolean độc lập và dùng kiểu khác để lưu true/false.

```java
@Entity
class FeatureFlag {
    @Id
    private Long id;

    @Column(nullable = false)
    private boolean enabled;
}
```

Test nên ghi và đọc lại cả hai giá trị, đồng thời xác nhận nullability theo yêu cầu. Với `Boolean` có thể null, cần phân biệt `false` và `null`; với primitive `boolean`, Java không thể biểu diễn null.

Không giả định mọi database đều chấp nhận literal `TRUE`/`FALSE` trong native SQL. Nếu query dùng literal riêng của dialect, hãy test trên engine đích.

### 5.2. `DECIMAL`/`NUMERIC` và `BigDecimal`

Số tiền hoặc giá trị cần độ chính xác thập phân nên thường dùng `BigDecimal` trong Java và `DECIMAL`/`NUMERIC` trong database:

```java
@Column(precision = 19, scale = 4, nullable = false)
private BigDecimal amount;
```

`precision` là tổng số chữ số, `scale` là số chữ số sau dấu thập phân. Nếu dữ liệu vượt giới hạn, database có thể từ chối, làm tròn hoặc chuyển đổi tùy engine và cấu hình.

Test nên kiểm tra:

- Giá trị ở giới hạn precision/scale.
- Giá trị có nhiều chữ số thập phân hơn scale.
- Giá trị âm hoặc bằng 0 nếu nghiệp vụ cho phép.
- Hành vi khi vượt precision.
- Giá trị đọc lại sau khi flush và clear persistence context.

Trong assertion Java, `BigDecimal.equals()` phân biệt scale, nên `10.0` và `10.00` không bằng nhau theo `equals`. Nếu nghiệp vụ chỉ quan tâm giá trị số, dùng `compareTo` hoặc AssertJ `isEqualByComparingTo`. Nếu scale là một phần hợp đồng lưu trữ, hãy kiểm tra cả scale.

### 5.3. `UUID`

UUID có thể được lưu dưới dạng kiểu UUID native, binary hoặc chuỗi ký tự tùy database và mapping. PostgreSQL có kiểu `uuid`; các database khác có thể dùng `BINARY(16)`, `CHAR(36)` hoặc kiểu tương đương.

```java
@Entity
class ApiClient {
    @Id
    private UUID id;
}
```

Không giả định native SQL có thể so sánh UUID bằng cùng một literal trên mọi engine. Test cần kiểm tra round-trip: lưu UUID đã biết, flush/clear, đọc lại và xác nhận đúng giá trị. Nếu ứng dụng dùng native query theo UUID, chạy test trên database thật để xác nhận binding JDBC.

### 5.4. Timestamp, timezone và precision

Java có nhiều kiểu thời gian với ngữ nghĩa khác nhau:

| Java | Ý nghĩa |
|---|---|
| `Instant` | Một thời điểm tuyệt đối trên timeline UTC |
| `OffsetDateTime` | Ngày giờ kèm offset UTC |
| `ZonedDateTime` | Ngày giờ gắn với `ZoneId` và quy tắc timezone |
| `LocalDateTime` | Ngày giờ địa phương không chứa zone/offset |
| `LocalDate` | Ngày lịch không chứa thời điểm |
| `LocalTime` | Giờ trong ngày không chứa ngày hoặc timezone |

Database có thể lưu `TIMESTAMP`, `TIMESTAMP WITH TIME ZONE`, `DATETIME` hoặc kiểu riêng. Tên kiểu không đảm bảo semantics giống nhau giữa các engine. Một số database chuẩn hóa về UTC; một số lưu local fields; có database không giữ nguyên timezone identifier mà chỉ giữ instant hoặc offset theo cách riêng.

Test nên:

- Chọn một instant cố định, không gọi `now()` trực tiếp.
- Đặt timezone JVM và database rõ ràng khi test có chuyển đổi zone.
- Ghi/đọc lại qua JDBC/JPA để xác nhận round-trip.
- Kiểm tra precision vì database có thể lưu đến giây, millisecond hoặc microsecond tùy kiểu và engine.
- Kiểm tra thời điểm gần ranh giới ngày, daylight saving time nếu nghiệp vụ dùng timezone có DST.

Ví dụ dùng `Clock.fixed`:

```java
@Test
void persistsInstantAtExpectedPrecision() {
    Instant expected = Instant.parse("2026-11-12T08:30:00.123456Z");
    EventRecord record = repository.save(new EventRecord(expected));
    repository.flush();
    entityManager.clear();

    Instant actual = repository.findById(record.getId()).orElseThrow()
            .getOccurredAt();

    assertThat(actual).isEqualTo(expected);
}
```

Assertion bằng nhau tuyệt đối chỉ đúng nếu kiểu cột và driver giữ precision tương ứng. Nếu database chủ đích làm tròn hoặc cắt precision, hãy xác định quy tắc chuẩn hóa và so sánh theo precision được hỗ trợ. Không thêm tolerance tùy tiện để làm test qua.

### 5.5. JSON và kiểu dữ liệu bán cấu trúc

PostgreSQL có `json`/`jsonb`; MySQL có kiểu JSON; một số hệ quản trị khác lưu JSON trong text hoặc dùng extension. Khả năng index, so sánh, query path và chuẩn hóa JSON có thể khác nhau.

Nếu entity lưu JSON qua converter hoặc Hibernate type, test cần xác nhận cả serialization và deserialization. Nếu repository dùng operator riêng như `->>` hoặc hàm JSON theo dialect, bắt buộc chạy trên engine tương ứng.

Test nên phân biệt:

- JSON hợp lệ có được serialize và đọc lại đúng cấu trúc không.
- Field thiếu khác với field có giá trị `null` như thế nào.
- Số trong JSON có bị chuyển đổi precision không.
- Thứ tự key có thuộc hợp đồng hay chỉ là chi tiết serialization.
- Native query JSON path có trả đúng kiểu và kết quả không.

Không so sánh chuỗi JSON thô nếu thứ tự key hoặc khoảng trắng không thuộc hợp đồng. Có thể parse về cây JSON rồi so sánh cấu trúc. Nhưng nếu database query phụ thuộc kiểu `jsonb`, cần test query đó trên PostgreSQL thật.

### 5.6. Binary, BLOB và CLOB

Java `byte[]`, `Blob`, `Clob` hoặc stream có thể ánh xạ sang `BLOB`, `BYTEA`, `VARBINARY`, `TEXT` hoặc kiểu tương ứng. Giới hạn kích thước, cách streaming và giới hạn row có thể khác nhau.

Test nên kiểm tra payload nhỏ, payload rỗng, payload lớn gần giới hạn ứng dụng và round-trip byte chính xác. Nếu dùng stream, bảo đảm stream được đóng và test không giữ tài nguyên sau khi context đóng.

## 6. Identity, sequence và generated key

Database có nhiều cách sinh khóa:

- Identity/auto-increment column.
- Sequence riêng.
- UUID được sinh trong ứng dụng.
- Trigger hoặc default expression.

Hibernate có thể chọn chiến lược sinh ID khác nhau tùy dialect. Ví dụ, database có sequence có thể dùng sequence generator; database khác dùng identity. Những khác biệt này ảnh hưởng đến thời điểm insert SQL, batching và việc lấy generated key.

Test persistence nên kiểm tra ID sau khi lưu và flush:

```java
@Test
void assignsDatabaseGeneratedId() {
    Customer customer = new Customer("Lan");

    Customer saved = repository.save(customer);
    repository.flush();

    assertThat(saved.getId()).isNotNull();
    assertThat(repository.findById(saved.getId())).isPresent();
}
```

Nếu entity dùng sequence có tên cụ thể hoặc native sequence query, test phải chạy trên database có sequence semantics tương ứng. Nếu ID do database sinh, không hardcode giá trị ID cụ thể trừ khi fixture chủ động kiểm soát sequence.

### 6.1. Generated value và thời điểm flush

`save()` không phải lúc nào cũng đồng nghĩa SQL đã được gửi ngay. JPA có thể trì hoãn ghi đến flush hoặc commit. Khi test cần xác nhận constraint, generated key hoặc SQL error, gọi `flush()` để buộc persistence context đồng bộ với database.

Để xác nhận dữ liệu được đọc lại từ database, sau `flush()` có thể `clear()` persistence context rồi truy vấn lại. Nếu chỉ đọc cùng entity đang được quản lý, test có thể nhận object trong bộ nhớ và bỏ qua lỗi mapping hoặc lưu trữ.

## 7. Identifier, collation và quy tắc so sánh chuỗi

Database có thể khác nhau về cách so sánh chuỗi, xử lý chữ hoa/thường, dấu tiếng Việt, accent và khoảng trắng. Collation ảnh hưởng đến `ORDER BY`, `LIKE`, unique constraint và equality.

Ví dụ, hai giá trị `Lan` và `lan` có thể được coi là bằng nhau trong một collation case-insensitive nhưng khác nhau trong collation case-sensitive. Chuỗi có dấu và không dấu cũng có thể được so sánh khác nhau tùy collation.

Test repository liên quan tìm kiếm hoặc unique constraint nên dùng database có collation giống production. Đừng giả định kết quả `findByNameIgnoreCase` hoặc unique index giống nhau trên mọi engine.

Tên bảng/cột cũng có khác biệt do identifier quoting và từ khóa dành riêng. Một tên hợp lệ trên database này có thể là reserved keyword trên database khác. Dùng tên rõ ràng, tránh keyword và kiểm tra migration trên engine đích.

## 8. Null semantics và constraint

SQL dùng logic ba giá trị: `TRUE`, `FALSE` và `UNKNOWN` do `NULL`. Biểu thức `column = NULL` không tương đương `column IS NULL`; kết quả so sánh thông thường với null là unknown.

JPQL/Criteria API có thể giúp tạo predicate phù hợp, nhưng native query vẫn phải tuân thủ SQL null semantics. Test nên bao gồm:

- Cột có giá trị và cột `NULL`.
- `IS NULL` và `IS NOT NULL`.
- Unique constraint khi có một hoặc nhiều giá trị null.
- Foreign key và `ON DELETE` behavior.
- Check constraint và default value.

Cách database xử lý unique constraint với nhiều null có thể khác nhau. Một số engine cho phép nhiều null trong unique index; một số cấu hình hoặc kiểu index có hành vi riêng. Nếu nghiệp vụ phụ thuộc vào quy tắc này, test trên đúng database.

## 9. Migration và schema phải khớp database test

Repository test chỉ có ý nghĩa khi schema test phản ánh schema mà ứng dụng sử dụng. Nếu test tự tạo schema bằng Hibernate `ddl-auto=create-drop` nhưng production dùng Flyway hoặc Liquibase, test có thể bỏ qua lỗi migration.

Với migration test, nên chạy chính các migration của ứng dụng trên database test cùng engine:

```java
@SpringBootTest
@Testcontainers
class DatabaseMigrationIntegrationTest {
    @Container
    static final PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }

    @Test
    void startsApplicationAgainstMigratedSchema() {
        // Context khởi động thành công sau khi migration được áp dụng.
    }
}
```

Spring Boot có thể tự chạy Flyway/Liquibase khi context khởi tạo nếu dependency và cấu hình phù hợp. Test cần xác nhận migration được áp dụng đúng thứ tự và schema cuối cùng hỗ trợ repository.

### 9.1. Tránh để Hibernate che lỗi migration

Nếu production dựa vào migration nhưng test để Hibernate tự tạo toàn bộ schema, test có thể qua dù migration bị thiếu cột, index hoặc constraint. Với test xác nhận migration, hãy để migration tạo schema và dùng Hibernate validate nếu phù hợp với cấu hình ứng dụng.

Không nên bật đồng thời nhiều cơ chế cùng quản lý schema mà không có chủ đích. Ví dụ, Flyway tạo schema và Hibernate `create` lại schema có thể khiến test không còn kiểm tra migration thực tế.

## 10. Transaction isolation là gì?

Transaction isolation xác định mức độ một transaction nhìn thấy thay đổi từ transaction khác và cách database xử lý các thao tác đọc/ghi đồng thời. Mục tiêu là kiểm soát những anomaly có thể xảy ra khi nhiều transaction cùng làm việc trên dữ liệu.

Các hiện tượng thường được nhắc đến:

- **Dirty read:** transaction đọc dữ liệu chưa commit của transaction khác.
- **Non-repeatable read:** cùng một row được đọc hai lần trong một transaction nhưng giá trị thay đổi do transaction khác commit update.
- **Phantom read:** cùng một predicate query được thực hiện hai lần nhưng tập row thỏa điều kiện thay đổi do transaction khác insert/delete và commit.
- **Lost update:** hai transaction cùng cập nhật dựa trên giá trị cũ, khiến một cập nhật ghi đè cập nhật còn lại.
- **Write skew:** các transaction đọc cùng một tập dữ liệu rồi cập nhật những row khác nhau, mỗi transaction riêng lẻ đều thỏa invariant nhưng kết hợp lại làm invariant bị vi phạm.

Mức isolation được chọn ảnh hưởng đến những anomaly database phải ngăn chặn. Tuy nhiên, tên isolation level không đảm bảo hành vi giống hệt giữa mọi engine; database có thể dùng MVCC, locking hoặc cơ chế khác để đạt semantics tương ứng.

## 11. Các mức isolation chuẩn

JDBC và Spring định nghĩa các mức isolation phổ biến:

| Mức | Dirty read | Non-repeatable read | Phantom read |
|---|---|---|---|
| `READ_UNCOMMITTED` | Có thể | Có thể | Có thể |
| `READ_COMMITTED` | Không | Có thể | Có thể |
| `REPEATABLE_READ` | Không | Không theo mô hình chuẩn | Có thể theo mô hình chuẩn |
| `SERIALIZABLE` | Không | Không | Không theo mô hình chuẩn |

Đây là cách phân loại theo semantics SQL/JDBC truyền thống. Database cụ thể có thể mạnh hơn mức yêu cầu hoặc triển khai khác bằng MVCC/locking. Ví dụ, PostgreSQL triển khai `READ UNCOMMITTED` như `READ COMMITTED`; PostgreSQL `REPEATABLE READ` có semantics snapshot isolation và ngăn nhiều anomaly hơn mô hình SQL tối thiểu, nhưng vẫn có thể xảy ra serialization anomaly/write skew. SQL Server có các tùy chọn locking và row-versioning riêng; MySQL/InnoDB dùng MVCC và locking theo isolation level.

### 11.1. `READ_UNCOMMITTED`

Mức này cho phép transaction có thể đọc thay đổi chưa commit từ transaction khác trong mô hình chuẩn. Điều đó tạo nguy cơ dirty read: transaction A đọc giá trị mà transaction B sau đó rollback.

Ví dụ:

```text
T1: UPDATE account SET balance = 0 WHERE id = 1;  (chưa commit)
T2: SELECT balance FROM account WHERE id = 1;    (có thể đọc 0)
T1: ROLLBACK;
```

T2 đã đọc một giá trị chưa bao giờ được commit. Nhiều database production không cho phép dirty read dù client yêu cầu `READ_UNCOMMITTED`; hãy kiểm tra hành vi của engine thay vì suy luận chỉ từ annotation.

### 11.2. `READ_COMMITTED`

Transaction chỉ đọc dữ liệu đã commit. Tuy nhiên, cùng một query hoặc cùng một row có thể trả giá trị khác nhau ở hai lần đọc nếu transaction khác commit thay đổi giữa hai lần đó.

Mức này thường được dùng làm mặc định ở nhiều database. Nó phù hợp với nhiều ứng dụng, nhưng không tự giải quyết lost update hoặc invariant cần đọc một snapshot ổn định.

### 11.3. `REPEATABLE_READ`

Mức này nhằm bảo đảm dữ liệu đã đọc không thay đổi giữa các lần đọc trong transaction theo semantics chuẩn. Cách database đạt điều đó có thể dựa vào lock hoặc snapshot. Phantom row vẫn được phép trong mô hình chuẩn, dù một số engine có thể ngăn nhiều phantom bằng next-key lock hoặc snapshot semantics mạnh hơn.

Đừng suy luận rằng `REPEATABLE_READ` luôn ngăn mọi cập nhật đồng thời hoặc write skew. Hãy kiểm tra engine và invariant cụ thể của ứng dụng.

### 11.4. `SERIALIZABLE`

`SERIALIZABLE` yêu cầu kết quả tương đương một thứ tự thực thi tuần tự của các transaction. Database có thể khóa, phát hiện xung đột hoặc hủy một transaction với serialization failure để giữ tính nhất quán.

Ứng dụng phải sẵn sàng xử lý transaction bị từ chối hoặc cần retry khi có xung đột. Test nên kiểm tra cả kết quả nghiệp vụ lẫn cách service xử lý lỗi serialization nếu database có thể trả lỗi đó.

## 12. Cấu hình isolation bằng Spring `@Transactional`

Spring cho phép chọn isolation level trên `@Transactional`:

```java
@Transactional(isolation = Isolation.REPEATABLE_READ)
public AccountSnapshot readStableBalance(Long accountId) {
    // Các truy vấn trong transaction này dùng isolation đã chỉ định
    // nếu transaction mới được bắt đầu bởi transaction manager.
}
```

Các giá trị trong `org.springframework.transaction.annotation.Isolation` tương ứng với JDBC isolation level:

- `DEFAULT`: dùng mức mặc định của transaction manager/database.
- `READ_UNCOMMITTED`.
- `READ_COMMITTED`.
- `REPEATABLE_READ`.
- `SERIALIZABLE`.

### 12.1. Isolation chỉ được áp dụng khi transaction mới được tạo

Một điểm dễ bỏ sót: nếu method tham gia một transaction đã tồn tại với propagation `REQUIRED`, isolation được khai báo trên method gọi sau không tự thay đổi isolation của transaction hiện tại. Transaction đã bắt đầu với manager và isolation ban đầu.

Ví dụ, test method đã mở transaction `READ_COMMITTED`, sau đó gọi service có `@Transactional(isolation = SERIALIZABLE)` và propagation mặc định `REQUIRED`. Service thường tham gia transaction đang có; nó không thể nâng isolation của transaction đó giữa chừng.

Nếu cần transaction mới với isolation riêng, có thể dùng propagation `REQUIRES_NEW` hoặc tạo transaction tường minh qua `TransactionTemplate`. Hãy hiểu tác động commit/rollback của transaction mới vì nó có thể tồn tại độc lập với transaction test bên ngoài.

### 12.2. Kiểm tra isolation không tương thích

`AbstractPlatformTransactionManager` có thuộc tính `validateExistingTransaction`. Khi bật, manager có thể từ chối tham gia một transaction hiện có nếu isolation hoặc read-only attribute không tương thích với yêu cầu của transaction mới. Đây là cơ chế giúp phát hiện việc service yêu cầu isolation cao hơn nhưng lại âm thầm tham gia transaction có isolation thấp.

Không giả định cấu hình isolation trên annotation luôn được áp dụng khi có transaction bên ngoài. Test cần tạo đúng transaction boundary và xác nhận manager/database thực thi mức mong đợi.

## 13. Transaction isolation trong test-managed transaction

Spring TestContext Framework có thể mở transaction cho test method khi class hoặc method được đánh dấu `@Transactional`:

```java
@SpringBootTest
@Transactional(isolation = Isolation.READ_COMMITTED)
class AccountRepositoryIsolationTest {
    @Autowired
    private AccountRepository accounts;

    @Test
    void readsCommittedAccountState() {
        // Test chạy trong transaction do Spring Test quản lý.
    }
}
```

Transaction manager được chọn sẽ bắt đầu transaction test với isolation được yêu cầu nếu manager và database hỗ trợ. Test transaction mặc định rollback sau method.

Khi có nhiều transaction manager, hãy chỉ rõ manager trong `@Transactional` của test. Isolation level được yêu cầu cho transaction do manager đó mở; nó không tự cấu hình manager khác.

### 13.1. `@Commit`, `@Rollback` và isolation

`@Commit` và `@Rollback` điều khiển kết quả cuối của test-managed transaction, không thay đổi isolation level:

```java
@Test
@Transactional(isolation = Isolation.SERIALIZABLE)
@Rollback
void rollsBackSerializableTestTransaction() {
    // Transaction chạy ở SERIALIZABLE rồi rollback sau test.
}
```

Nếu cần kiểm tra trạng thái sau commit, có thể dùng `@Commit` hoặc `TestTransaction.flagForCommit()` và kết thúc transaction. Dữ liệu commit phải được cleanup để không ảnh hưởng test khác.

### 13.2. Flush và clear không tạo transaction mới

Trong JPA, `flush()` gửi các thay đổi đang chờ đến database, còn `clear()` xóa entity đang được quản lý khỏi persistence context. Hai thao tác này hữu ích để kiểm tra SQL và đọc lại dữ liệu, nhưng không thay đổi isolation level và không tạo transaction mới.

Để kiểm tra visibility giữa hai transaction, cần hai transaction thực sự độc lập, thường chạy trên hai connection. Gọi hai repository method liên tiếp trong cùng test transaction không đủ để mô phỏng hai transaction đồng thời.

## 14. Thiết kế concurrency test để quan sát isolation

Isolation chỉ có ý nghĩa khi có nhiều transaction cùng hoạt động. Một test chạy tuần tự trong một transaction không thể chứng minh dirty read, non-repeatable read hoặc lost update có xảy ra hay không.

Một concurrency test thường cần:

1. Hai transaction riêng biệt, mỗi transaction có connection riêng.
2. Đồng bộ thời điểm đọc/ghi bằng latch, barrier hoặc coordination primitive.
3. Một trình tự thao tác xác định để tái hiện anomaly cần kiểm tra.
4. Timeout hữu hạn để test không treo khi transaction bị lock.
5. Cleanup dữ liệu sau khi cả hai transaction hoàn tất.

Không dùng `Thread.sleep` để đoán transaction kia đã commit. Dùng `CountDownLatch`, `CyclicBarrier`, `Phaser` hoặc future để điều phối chính xác các bước.

### 14.1. Tạo transaction độc lập bằng `TransactionTemplate`

`TransactionTemplate` cho phép test tạo transaction trên manager cụ thể:

```java
@SpringBootTest
class IsolationIntegrationTest {
    @Autowired
    PlatformTransactionManager transactionManager;

    @Autowired
    JdbcTemplate jdbc;

    @Test
    void executesWorkInSeparateTransactions() {
        TransactionTemplate first = new TransactionTemplate(transactionManager);
        TransactionTemplate second = new TransactionTemplate(transactionManager);

        first.setIsolationLevel(TransactionDefinition.ISOLATION_READ_COMMITTED);
        second.setIsolationLevel(TransactionDefinition.ISOLATION_READ_COMMITTED);

        first.executeWithoutResult(status -> {
            // Transaction thứ nhất.
        });

        second.executeWithoutResult(status -> {
            // Transaction thứ hai.
        });
    }
}
```

Đoạn code minh họa cách tạo transaction với isolation riêng; để quan sát anomaly, cần chạy chúng đồng thời trên thread khác nhau và điều phối thao tác bằng synchronization primitive. Nếu gọi lần lượt như ví dụ, không có cạnh tranh đồng thời.

### 14.2. Test-managed transaction và thread binding

Spring transaction thường được bind vào thread hiện tại. Một task chạy trong `@Async`, executor hoặc thread khác không tự tham gia transaction test của thread gọi. Đây là điều quan trọng khi viết concurrency test: mỗi worker cần mở transaction riêng qua `TransactionTemplate` hoặc một service transactional được gọi qua proxy.

Không truyền một `EntityManager` đang được quản lý hoặc JDBC `Connection` của thread test sang worker thread. Mỗi transaction cần resource phù hợp với thread và transaction manager.

### 14.3. Ví dụ điều phối hai transaction

Một ví dụ khung dùng latch:

```java
CountDownLatch firstReadDone = new CountDownLatch(1);
CountDownLatch allowFirstToContinue = new CountDownLatch(1);

ExecutorService executor = Executors.newFixedThreadPool(2);
try {
    Future<BigDecimal> first = executor.submit(() ->
            transactionTemplate.execute(status -> {
                BigDecimal initial = readBalance();
                firstReadDone.countDown();
                await(allowFirstToContinue);
                return readBalance();
            }));

    Future<?> second = executor.submit(() -> {
        await(firstReadDone);
        transactionTemplate.executeWithoutResult(status -> updateBalance("150.00"));
    });

    second.get(5, TimeUnit.SECONDS);
    allowFirstToContinue.countDown();
    BigDecimal valueSeenAgain = first.get(5, TimeUnit.SECONDS);
} finally {
    allowFirstToContinue.countDown();
    executor.shutdownNow();
}
```

Đây là khung điều phối; để test thực tế, mỗi worker phải dùng transaction template được cấu hình đúng manager và isolation, `await` cần xử lý timeout/interruption, còn dữ liệu phải được tạo và cleanup độc lập. Kết quả mong đợi phụ thuộc isolation level và database engine. Không dùng đoạn khung này như một assertion portable cho mọi database.

## 15. Các anomaly cần kiểm thử

### 15.1. Dirty read

Để kiểm tra dirty read, transaction A cập nhật row nhưng chưa commit; transaction B đọc row trong khoảng đó; sau đó A rollback. Nếu B nhìn thấy giá trị chưa commit, dirty read đã xảy ra.

Hầu hết database production thường dùng ít nhất `READ_COMMITTED` hoặc có semantics mạnh hơn. Khi kiểm tra `READ_UNCOMMITTED`, cần biết engine có thực sự hỗ trợ hay nâng mức lên `READ_COMMITTED`.

### 15.2. Non-repeatable read

Transaction A đọc một row. Transaction B cập nhật row và commit. Transaction A đọc lại cùng row. Ở `READ_COMMITTED`, giá trị thứ hai có thể khác; ở isolation mạnh hơn, database có thể giữ snapshot hoặc lock để giá trị không đổi.

Test phải bảo đảm cả hai lần đọc của A nằm trong cùng transaction và B commit ở giữa. Nếu mỗi lần đọc mở transaction mới, test không còn kiểm tra non-repeatable read.

### 15.3. Phantom read

Transaction A chạy query theo predicate, ví dụ `status = 'OPEN'`. Transaction B insert một row mới có status `OPEN` rồi commit. A chạy lại cùng query. Nếu tập row thay đổi, test quan sát phantom.

Một số engine dùng snapshot hoặc range lock để ngăn hiện tượng này ở mức isolation nhất định. Hãy chạy test trên database đích và kiểm tra semantics cụ thể.

### 15.4. Lost update

Hai transaction cùng đọc balance 100. T1 tính 110, T2 tính 120; cả hai ghi lại giá trị dựa trên snapshot cũ. Nếu T2 ghi sau T1, kết quả cuối có thể là 120 thay vì 130 hoặc một giá trị được kỳ vọng theo quy tắc nghiệp vụ.

Để tránh lost update, ứng dụng có thể dùng optimistic locking (`@Version`), pessimistic locking (`SELECT ... FOR UPDATE`), atomic update query hoặc isolation phù hợp. Test cần chạy hai transaction cạnh tranh và xác nhận một transaction bị từ chối/retry hoặc kết quả cuối bảo toàn invariant.

### 15.5. Write skew

Write skew xảy ra khi hai transaction đọc cùng một tập dữ liệu, mỗi transaction cập nhật row khác nhau và cả hai cùng commit, khiến invariant toàn cục bị vi phạm. Ví dụ, hệ thống cần luôn có ít nhất một bác sĩ trực. Hai transaction cùng đọc thấy hai bác sĩ đang trực rồi mỗi transaction cho một người nghỉ; nếu không có cơ chế bảo vệ, cuối cùng không còn ai trực.

`REPEATABLE_READ` theo snapshot isolation vẫn có thể cho phép write skew ở một số database. `SERIALIZABLE`, constraint phù hợp hoặc locking ở đúng phạm vi có thể ngăn lỗi. Test phải mô phỏng đúng invariant, không chỉ xác nhận hai row được cập nhật.

## 16. Isolation không thay thế optimistic/pessimistic locking

Isolation level là thuộc tính của transaction. Optimistic và pessimistic locking là cơ chế phối hợp truy cập dữ liệu ở cấp row/entity hoặc query. Chúng có thể bổ sung cho isolation nhưng không đồng nghĩa với nhau.

### 16.1. Optimistic locking với `@Version`

JPA hỗ trợ optimistic locking qua `@Version`:

```java
@Entity
class InventoryItem {
    @Id
    private Long id;

    private int quantity;

    @Version
    private long version;
}
```

Khi hai transaction cùng cập nhật một entity, provider kiểm tra version. Transaction ghi sau có thể nhận `OptimisticLockException` hoặc exception được Spring dịch tương ứng nếu version đã thay đổi.

Test cần dùng hai persistence context/transaction riêng để xác nhận xung đột. Hai entity reference trong cùng persistence context không mô phỏng được hai transaction độc lập.

### 16.2. Pessimistic locking

Repository có thể yêu cầu lock:

```java
@Lock(LockModeType.PESSIMISTIC_WRITE)
@Query("select i from InventoryItem i where i.id = :id")
Optional<InventoryItem> findForUpdate(@Param("id") Long id);
```

Hibernate sẽ sinh SQL lock phù hợp với dialect. Cú pháp và hành vi lock có thể khác giữa database. Test nên xác nhận transaction thứ hai bị block hoặc nhận lỗi theo timeout/deadlock policy đã cấu hình.

Không dùng sleep để kiểm tra lock. Dùng latch để giữ transaction thứ nhất mở trong khi transaction thứ hai cố lấy lock, và đặt timeout cho test để tránh treo suite.

## 17. Database default isolation và cấu hình thực tế

Isolation mặc định có thể khác theo engine và cấu hình server. Ví dụ, nhiều cấu hình PostgreSQL dùng `READ COMMITTED`, trong khi InnoDB của MySQL thường mặc định `REPEATABLE READ`. DBA hoặc connection/session settings có thể thay đổi mặc định.

Vì vậy, test không nên suy luận isolation chỉ từ tên database. Hãy kiểm tra:

- Cấu hình isolation của datasource/session.
- `@Transactional(isolation = ...)` trên service và test.
- Transaction manager được chọn.
- Propagation có tham gia transaction có sẵn hay tạo transaction mới.
- Driver và database version.
- Các setting riêng của engine như snapshot isolation hoặc row versioning.

Nếu ứng dụng phụ thuộc vào một isolation cụ thể, hãy cấu hình rõ trên transaction boundary quan trọng và test trên database đích. Nếu ứng dụng dùng database default, ghi nhận default đó trong cấu hình vận hành và kiểm tra khi nâng phiên bản engine.

## 18. Kiểm thử lỗi do dialect và isolation trên CI

Một suite data-layer có thể chia thành các nhóm:

| Nhóm | Mục tiêu | Cách chạy |
|---|---|---|
| Repository nhanh | Kiểm tra derived query và mapping cơ bản | Có thể dùng database nhúng nếu đã xác định giới hạn |
| Dialect integration | Native SQL, JSON, sequence, collation và type mapping | Testcontainers với engine production |
| Migration | Schema và dữ liệu sau Flyway/Liquibase | Database container cùng engine/version |
| Concurrency/isolation | Locking, transaction anomalies, optimistic version | Database thật, test đồng thời có synchronization |
| Compatibility matrix | Hỗ trợ nhiều engine/version | Job CI riêng cho từng engine/version |

Để CI ổn định:

- Cố định image version thay vì dùng tag thay đổi.
- Đảm bảo test cleanup dữ liệu và tài nguyên.
- Dùng timeout cho lock, future và latch.
- Tránh dựa vào thứ tự test hoặc dữ liệu tồn tại từ lần chạy trước.
- Phân biệt lỗi do container chưa sẵn sàng với lỗi SQL thực tế.
- Chỉ chạy concurrency test khi môi trường có tài nguyên đủ và test có đồng bộ xác định.

## 19. Các lỗi thường gặp và cách xử lý

### Test qua trên H2 nhưng thất bại trên production

Query có thể dùng cú pháp hoặc kiểu dữ liệu riêng. Chạy test liên quan trên đúng database engine; ưu tiên Testcontainers cho native SQL, migration và locking.

### Dữ liệu thời gian lệch vài mili/micro giây

Database hoặc driver có precision khác với Java. Xác định precision cột, quy tắc làm tròn và timezone; so sánh theo hợp đồng thực tế.

### `BigDecimal` không bằng nhau dù giá trị nhìn giống

`equals` phân biệt scale. Dùng so sánh số học nếu scale không thuộc hợp đồng, hoặc kiểm tra scale riêng khi cần.

### UUID đọc lại không giống định dạng ghi vào

Database có thể dùng native UUID, binary hoặc string. Kiểm tra mapping/driver và test round-trip trên engine thật.

### Query sắp xếp chuỗi khác nhau

Collation ảnh hưởng case sensitivity, accent và ordering. Dùng database có collation production và viết assertion phản ánh quy tắc tìm kiếm thực tế.

### Transaction test không rollback dữ liệu

Có thể thao tác dùng transaction manager khác, propagation `REQUIRES_NEW`, async thread hoặc connection không tham gia transaction test. Xác định transaction boundary và manager thực tế.

### Isolation annotation dường như không có tác dụng

Method có thể tham gia transaction đã tồn tại với isolation khác. Tạo transaction mới hoặc dùng `REQUIRES_NEW`/`TransactionTemplate` để kiểm soát rõ ranh giới.

### Concurrency test bị treo

Một thread có thể đang giữ lock hoặc latch không được release khi test thất bại. Dùng `try/finally`, timeout hữu hạn và luôn release synchronization primitive trong cleanup.

### Kết quả isolation khác giữa database

Các engine dùng MVCC, locking và semantics riêng. Không khẳng định một anomaly sẽ xảy ra giống nhau ở mọi engine chỉ dựa vào tên isolation level; chạy test trên engine/version thực tế.

## 20. Quy trình thiết kế data-layer test

Khi kiểm thử repository hoặc transaction, hãy thực hiện theo trình tự:

1. Xác định database engine và version production cần tương thích.
2. Xác định query đang dùng JPQL/Criteria hay native SQL.
3. Liệt kê kiểu dữ liệu có nguy cơ khác biệt: decimal, UUID, JSON, timestamp, boolean, binary và collation.
4. Chọn database nhúng hay database thật dựa trên điều cần chứng minh.
5. Nếu cần database thật, khởi chạy Testcontainers với image version phù hợp và giữ datasource đã cấu hình.
6. Chạy migration thực tế nếu test cần xác nhận schema production.
7. Gọi `flush()` và `clear()` khi cần kiểm tra SQL, constraint và dữ liệu đọc lại.
8. Xác định transaction manager, propagation và isolation level cho từng thao tác.
9. Với concurrency, dùng transaction/connection riêng và đồng bộ bằng latch/barrier thay vì sleep.
10. Xác nhận kết quả cuối, lỗi xung đột hoặc rollback đúng theo hợp đồng và cleanup mọi dữ liệu đã commit.

Một test nên trả lời một câu hỏi rõ ràng: query có chạy trên dialect này không, mapping có giữ đúng dữ liệu không, migration có tạo đúng schema không, hay isolation có bảo vệ invariant không. Khi tách mục tiêu như vậy, lỗi sẽ dễ chẩn đoán và suite không cần khởi chạy database nặng cho mọi unit test.

## 21. Nguyên tắc cần nhớ

- SQL dialect ảnh hưởng cú pháp, function, kiểu dữ liệu, generated key, collation và locking.
- Database nhúng không chứng minh native SQL hoặc transaction behavior tương thích với production.
- Dùng Testcontainers hoặc môi trường cùng engine/version khi test phụ thuộc dialect, migration, kiểu dữ liệu hoặc isolation.
- Kiểm tra round-trip cho `BigDecimal`, UUID, JSON, timestamp, binary và giá trị boolean/null theo semantics thực tế.
- `flush()` buộc đồng bộ với database; `clear()` buộc đọc lại qua persistence context mới, nhưng hai thao tác không tạo transaction mới.
- Isolation level xác định cách các transaction nhìn thấy thay đổi; semantics thực tế còn phụ thuộc database engine và version.
- `@Transactional(isolation = ...)` không nâng isolation của transaction đã tồn tại mà method tham gia.
- Test-managed transaction thường rollback sau test, nhưng transaction manager khác, `REQUIRES_NEW` hoặc thread khác có thể tạo dữ liệu tồn tại độc lập.
- Concurrency test cần transaction và connection riêng, synchronization xác định, timeout hữu hạn và cleanup đáng tin cậy.
- Isolation không thay thế optimistic/pessimistic locking hoặc constraint bảo vệ invariant nghiệp vụ.

Kiểm thử tầng dữ liệu đáng tin cậy phải phản ánh database mà ứng dụng sẽ chạy. Khi chọn đúng engine, kiểm tra kiểu dữ liệu qua round-trip và tạo transaction boundary có chủ đích, test có thể phát hiện lỗi dialect, mapping và concurrency trước khi chúng xuất hiện trong môi trường thật.
