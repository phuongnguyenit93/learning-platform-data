# Khác biệt H2 với hệ quản trị triển khai và rủi ro kết quả sai lệch

H2 là cơ sở dữ liệu Java gọn nhẹ, thường được dùng trong test Spring Data JPA vì khởi động nhanh và có thể chạy trong bộ nhớ. Tuy nhiên, một bài test chạy xanh trên H2 chỉ chứng minh hành vi đã được kiểm tra trong môi trường H2. Nó không tự chứng minh câu SQL, kiểu dữ liệu, transaction, khóa đồng thời, migration hay hiệu năng sẽ hoạt động giống trên PostgreSQL, MySQL, Oracle hoặc hệ quản trị đang triển khai.

Rủi ro xuất hiện khi test dùng H2 thay cho database thật nhưng ứng dụng lại phụ thuộc vào hành vi riêng của database production. H2 có thể chấp nhận SQL mà database đích từ chối, diễn giải kiểu dữ liệu khác, xử lý thứ tự null khác hoặc không tái hiện đúng khóa và mức cô lập. Kết quả là test xanh nhưng lỗi xuất hiện sau khi deploy.

Cách tiếp cận phù hợp là dùng H2 cho các kiểm thử nhanh, có phạm vi rõ ràng; đồng thời chạy các kiểm thử tích hợp quan trọng trên cùng engine và phiên bản database với môi trường triển khai.

## 1. H2 là gì và vì sao được dùng trong kiểm thử?

H2 là relational database viết bằng Java, có thể chạy embedded hoặc chạy ở chế độ server. Với Spring Boot, một cấu hình phổ biến là database trong bộ nhớ:

~~~properties
spring.datasource.url=jdbc:h2:mem:jpa-test
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.jpa.hibernate.ddl-auto=create-drop
~~~

Khi dùng URL `jdbc:h2:mem:jpa-test`, database thường tồn tại trong bộ nhớ của JVM và được truy cập qua các connection cùng tên database. Khi database đóng theo vòng đời connection cuối cùng, dữ liệu có thể biến mất. Tùy cấu hình và cách test mở connection, việc tạo database mới hoặc giữ database giữa các connection có thể ảnh hưởng đến kết quả.

H2 hữu ích vì:

- Không cần cài một database server riêng cho mỗi lần chạy test.
- Khởi động nhanh, dễ tạo schema và dữ liệu kiểm thử.
- Phù hợp với nhiều bài test repository, mapping entity, quan hệ và truy vấn JPQL tương đối portable.
- Có thể tích hợp với `@DataJpaTest` và Spring Boot auto-configuration.

Nhưng H2 là một database engine riêng, có parser SQL, kiểu dữ liệu, optimizer, transaction manager và hành vi riêng. Việc nó hỗ trợ cú pháp gần giống một hệ quản trị khác không biến nó thành chính hệ quản trị đó.

## 2. Compatibility mode không biến H2 thành PostgreSQL hoặc MySQL

H2 có các chế độ tương thích cú pháp, ví dụ:

~~~properties
spring.datasource.url=jdbc:h2:mem:jpa-test;MODE=PostgreSQL
~~~

Hoặc:

~~~properties
spring.datasource.url=jdbc:h2:mem:jpa-test;MODE=MySQL
~~~

Compatibility mode giúp H2 chấp nhận hoặc diễn giải một số cú pháp theo phong cách database được chọn. Mức hỗ trợ phụ thuộc phiên bản H2 và không bao phủ toàn bộ ngữ nghĩa của hệ quản trị đích.

Chẳng hạn, `MODE=PostgreSQL` không cung cấp toàn bộ extension, operator, kiểu dữ liệu, planner, locking, isolation và quy tắc catalog của PostgreSQL. Tương tự, `MODE=MySQL` không tái tạo toàn bộ SQL mode, collation, engine InnoDB, behavior của index hay các đặc điểm của MySQL.

Có thể dùng mode để giảm một số khác biệt cú pháp trong test nhanh, nhưng không nên dùng kết quả của mode làm bằng chứng tương đương production. Nếu một tính năng phụ thuộc vào PostgreSQL JSONB, toán tử `->>`, `ON CONFLICT`, extension hoặc MySQL-specific function, cần test trên engine thật.

## 3. Khác biệt về SQL dialect và native query

Hibernate dùng dialect để chuyển đổi một phần thao tác ORM thành SQL phù hợp với database. Khi test chạy H2, Hibernate có thể phát SQL theo dialect H2; khi production chạy PostgreSQL hoặc MySQL, SQL được sinh theo dialect tương ứng.

JPQL thường portable hơn native SQL vì truy vấn trên entity và thuộc tính Java thay vì tên bảng, tên cột và cú pháp riêng của database. Tuy nhiên, JPQL vẫn được provider dịch thành SQL của engine đang chạy. Một JPQL query có thể hoạt động trên H2 nhưng gặp khác biệt về hàm, kiểu dữ liệu hoặc khả năng dịch trên database khác.

Native query gắn trực tiếp hơn với database:

~~~java
public interface ProductRepository extends JpaRepository<Product, Long> {

    @Query(value = """
        select *
          from product
         where lower(name) like lower(concat('%', :keyword, '%'))
        """, nativeQuery = true)
    List<Product> searchByName(@Param("keyword") String keyword);
}
~~~

Ví dụ này dùng cú pháp tương đối phổ biến, nhưng không nên suy rộng rằng mọi native query đều portable. Các khác biệt thường gặp gồm:

- Hàm chuỗi, ngày giờ, JSON, toán học và chuyển kiểu.
- Cú pháp phân trang, giới hạn kết quả và biểu thức window.
- Upsert, returning clause, conflict handling và CTE.
- Cách quote identifier, schema, tên bảng và tên cột.
- Cú pháp khóa hàng, hint và stored procedure.
- Câu truy vấn count đi kèm native query phân trang.

Một native query chạy trên H2 chỉ xác nhận parser và engine H2 chấp nhận nó. Nếu production dùng SQL đặc thù, hãy chạy chính query đó trên database production-compatible trong integration test.

## 4. Khác biệt về kiểu dữ liệu và quy tắc so sánh

Mapping Java sang SQL không phải lúc nào cũng giống nhau giữa các engine. Cùng một entity có thể được Hibernate ánh xạ sang kiểu cột khác tùy dialect và phiên bản database.

Các khu vực dễ phát sinh sai lệch:

| Nhóm dữ liệu | Rủi ro cần kiểm tra |
|---|---|
| Boolean | Database có thể lưu bằng BOOLEAN, BIT, số hoặc quy ước riêng |
| UUID | Cách lưu dạng native UUID hay chuỗi/binary có thể khác |
| Timestamp | Độ chính xác phần giây, timezone và chuyển đổi giữa local/UTC có thể khác |
| Numeric/Decimal | Precision, scale, làm tròn và overflow |
| String | Độ dài, Unicode, collation và so sánh phân biệt hoa thường |
| JSON | JSON và JSONB, validation, operator và index phụ thuộc engine |
| Array/Enum | Kiểu native và cách ánh xạ phụ thuộc database/provider |
| BLOB/CLOB | Driver, streaming, giới hạn kích thước và cách lưu |

Ví dụ, H2 có thể chấp nhận một kiểu cột hoặc phép chuyển đổi mà database đích xử lý khác. Test chỉ kiểm tra lưu rồi đọc một giá trị đơn giản có thể bỏ qua lỗi precision, timezone, encoding hoặc giới hạn độ dài.

### Hoa thường, collation và dấu

Quy tắc so sánh chuỗi phụ thuộc collation và cấu hình database. Một truy vấn tìm `"admin"` có thể cho kết quả khác với `"Admin"` khi engine hoặc collation khác nhau. So sánh có dấu, không dấu, ký tự Unicode và sắp xếp theo ngôn ngữ cũng có thể khác.

Không nên dùng kết quả sắp xếp hoặc tìm kiếm trên H2 để khẳng định production có cùng thứ tự. Nếu nghiệp vụ phụ thuộc vào collation, hãy cấu hình và test với collation thực tế trên database đích.

### NULL và thứ tự sắp xếp

Thứ tự `NULL` khi `ORDER BY` có thể khác giữa các engine hoặc giữa cú pháp mặc định và biểu thức chỉ định rõ. Một trang kết quả được sắp xếp theo ngày có thể có thứ tự khác nếu nhiều hàng có giá trị null.

Nếu nghiệp vụ cần thứ tự ổn định, hãy chỉ định rõ cách sắp xếp null theo khả năng portable của JPA hoặc dùng biểu thức tương ứng đã kiểm tra trên engine đích. Cũng nên thêm khóa phụ duy nhất vào `ORDER BY` khi phân trang để tránh các hàng cùng giá trị bị đổi vị trí giữa các lần truy vấn.

## 5. DDL, constraint, sequence và cách tạo schema

Spring Boot có thể để Hibernate tự tạo schema cho test bằng `ddl-auto=create` hoặc `create-drop`. Cách này thuận tiện cho test mapping, nhưng schema do Hibernate sinh không nhất thiết giống schema được tạo từ migration trong production.

Các khác biệt cần chú ý:

- Kiểu dữ liệu và độ dài cột được suy ra từ annotation.
- Tên index, constraint và sequence.
- Cú pháp identity/auto increment và chiến lược sinh ID.
- Unique constraint, foreign key, check constraint và hành vi khi vi phạm.
- Schema, catalog, identifier được quote và quy tắc viết hoa/thường.
- Default value, generated column, trigger và stored procedure.

Nếu production dùng Flyway hoặc Liquibase, một test chỉ chạy `ddl-auto=create-drop` không xác nhận migration có thể chạy thành công trên database đích. Migration có thể chứa cú pháp DDL đặc thù, câu lệnh tạo index riêng, function hoặc extension mà H2 không hỗ trợ.

Với các bài test migration, hãy chạy migration trên đúng engine và phiên bản database đích. Sau khi migration hoàn tất, kiểm tra schema và thực hiện một số thao tác đọc/ghi đại diện.

### Chiến lược sinh khóa chính

`GenerationType.IDENTITY`, sequence và table generator có hành vi khác nhau. H2 có thể hỗ trợ một đường sinh ID khác với PostgreSQL hoặc MySQL. Một test insert thành công trên H2 không chứng minh production dùng đúng sequence, đúng quyền truy cập sequence hoặc đúng cấu hình allocation.

Hãy kiểm tra:

- Annotation `@GeneratedValue` và `@SequenceGenerator` có khớp schema production không.
- Tên sequence, increment và allocation size.
- Giá trị ID sau insert và sau khi EntityManager flush.
- Việc import dữ liệu hoặc insert đồng thời có gây trùng khóa hay không.

## 6. Transaction, isolation và khóa đồng thời

Transaction là một trong những nơi H2 dễ tạo cảm giác an toàn giả. Hai engine có thể khác về MVCC, lock granularity, thời điểm lấy lock, deadlock detection, timeout và cách xử lý transaction đồng thời.

Các tính năng cần kiểm thử trên database đích khi ứng dụng phụ thuộc vào chúng:

- `SELECT ... FOR UPDATE` và các biến thể khóa hàng.
- Optimistic locking với `@Version`.
- Pessimistic locking qua `@Lock`.
- Isolation level như READ COMMITTED, REPEATABLE READ và SERIALIZABLE.
- Deadlock, lock timeout và retry.
- Unique constraint khi hai transaction cùng insert một giá trị.
- Cập nhật đồng thời và lost update.
- `SKIP LOCKED` hoặc `NOWAIT` nếu ứng dụng sử dụng.

H2 có hỗ trợ một số cơ chế transaction và locking, nhưng hành vi chi tiết không đại diện cho engine production. Một test chạy tuần tự không thể chứng minh code an toàn khi có hai request đồng thời.

Ví dụ, kiểm tra tồn kho bằng cách đọc số lượng rồi cập nhật có thể vượt qua test đơn luồng nhưng vẫn bán vượt số lượng khi hai transaction chạy đồng thời. Hãy tạo integration test có hai transaction độc lập, đồng bộ thời điểm đọc/ghi và xác nhận kết quả trên database thật.

## 7. H2 và rủi ro test phân trang, truy vấn và optimizer

H2 và database production có optimizer, thống kê, index selection và execution plan khác nhau. Một truy vấn chạy nhanh trên vài chục bản ghi H2 có thể chậm trên bảng production có hàng triệu bản ghi.

Các rủi ro gồm:

- Truy vấn N+1 bị che khuất bởi dữ liệu test quá nhỏ.
- Index không được dùng như dự kiến.
- Query plan thay đổi khi dữ liệu phân bố khác.
- Phân trang thiếu thứ tự ổn định.
- Native query dùng cú pháp phân trang riêng.
- Count query không tương đương với truy vấn dữ liệu.
- Join, distinct, group by và fetch strategy tạo kế hoạch khác.

Test H2 có thể kiểm tra kết quả logic cơ bản, nhưng không thay thế việc kiểm tra `EXPLAIN` hoặc `EXPLAIN ANALYZE` trên engine và dữ liệu gần production. Không nên lấy thời gian chạy H2 để dự đoán thời gian production.

## 8. @DataJpaTest có thể đang dùng database nào?

`@DataJpaTest` tạo test slice tập trung vào JPA: entity, repository và cấu hình liên quan. Spring Boot thường cấu hình test transaction và rollback sau mỗi test. Khi có embedded database như H2 trên classpath, Spring Boot có thể tự thay datasource đang cấu hình bằng embedded database theo chính sách auto-configuration.

Điều này có thể khiến developer nghĩ test đang dùng PostgreSQL hoặc MySQL trong khi thực tế test đang chạy H2.

Ví dụ test repository:

~~~java
@DataJpaTest
class ProductRepositoryTest {

    @Autowired
    private ProductRepository productRepository;

    @Test
    void findsActiveProducts() {
        Product product = new Product("Keyboard", true);
        productRepository.save(product);

        List<Product> result = productRepository.findByActiveTrue();

        assertThat(result).contains(product);
    }
}
~~~

Test này hữu ích để kiểm tra repository cơ bản. Nhưng nếu nó chạy H2, nó không xác nhận native SQL, migration, locking hay kiểu dữ liệu trên database production.

Nếu muốn `@DataJpaTest` sử dụng datasource được cung cấp bởi Testcontainers hoặc cấu hình test database bên ngoài, hãy tắt hành vi thay thế embedded database:

~~~java
@DataJpaTest
@AutoConfigureTestDatabase(
    replace = AutoConfigureTestDatabase.Replace.NONE
)
class ProductRepositoryPostgresTest {
    // Cấu hình datasource trỏ đến PostgreSQL test instance
}
~~~

Với `@SpringBootTest`, ứng dụng thường nạp cấu hình datasource đầy đủ hơn và không có cùng mục tiêu thay datasource như JPA test slice. Dù dùng annotation nào, hãy xác nhận URL, driver và engine thực tế của test trước khi kết luận.

### Transaction rollback của test cũng có thể che khuất lỗi

Các test slice JPA thường chạy trong transaction và rollback sau test. Điều này tiện cho việc cô lập dữ liệu, nhưng có thể che khuất hành vi chỉ xảy ra khi commit:

- Constraint hoặc lỗi ghi được phát hiện ở thời điểm flush/commit.
- Transaction synchronization và callback sau commit.
- Hành vi của transaction lồng nhau hoặc nhiều transaction.
- Dữ liệu nhìn thấy từ connection khác sau commit.

Khi cần xác nhận commit, hãy chủ động flush và dùng transaction test được thiết kế phù hợp, hoặc chạy thao tác qua service trong transaction riêng rồi đọc dữ liệu từ transaction/connection khác. Đừng chỉ kiểm tra entity còn trong persistence context vì nó chưa chắc đã được database commit.

## 9. Kiểm thử trên database thật bằng Testcontainers

Testcontainers giúp khởi chạy database thật trong container dùng cho test. Với ứng dụng triển khai PostgreSQL, test có thể dùng PostgreSQL container cùng major version và cấu hình gần production.

Ví dụ với Spring Boot 3.1 trở lên, có thể dùng `@ServiceConnection`:

~~~java
@Testcontainers
@DataJpaTest
@AutoConfigureTestDatabase(
    replace = AutoConfigureTestDatabase.Replace.NONE
)
class ProductRepositoryPostgresTest {

    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @Autowired
    private ProductRepository productRepository;

    @Test
    void persistsAndQueriesOnPostgres() {
        Product product = new Product("Keyboard", true);
        productRepository.saveAndFlush(product);

        assertThat(productRepository.findByActiveTrue())
                .extracting(Product::getName)
                .contains("Keyboard");
    }
}
~~~

Đây là ví dụ cấu hình kiểm thử, giả định project đã khai báo các dependency test cần thiết: Testcontainers JUnit Jupiter, module PostgreSQL, PostgreSQL JDBC driver và Spring Boot Testcontainers. Quản lý phiên bản dependency theo Spring Boot dependency management hoặc Testcontainers BOM của dự án.

`@ServiceConnection` tự cung cấp thông tin kết nối container cho Spring Boot. Với phiên bản Spring Boot cũ hơn hoặc không dùng service connection, có thể cấu hình datasource bằng `@DynamicPropertySource`.

Lợi ích của cách này:

- Test chạy trên PostgreSQL thật, nên parser, dialect, kiểu dữ liệu và nhiều hành vi transaction gần với production hơn.
- Có thể chạy migration thực tế khi Spring khởi động.
- Kiểm tra native query và function đặc thù.
- Có thể tạo test concurrency và constraint thực tế.
- Database container có thể được tạo mới cho mỗi suite hoặc tái sử dụng theo cấu hình CI.

Container vẫn có thể khác production nếu khác phiên bản, extension, collation, timezone, cấu hình server hoặc dữ liệu. Vì vậy hãy khớp phiên bản và cấu hình quan trọng, không chỉ khớp tên engine.

## 10. Xây dựng chiến lược test theo nhiều lớp

Không cần chạy mọi test trên database thật. Có thể phân tầng theo chi phí và mức độ phụ thuộc database:

| Loại kiểm thử | Database phù hợp | Mục tiêu |
|---|---|---|
| Unit test service | Mock/fake khi phù hợp | Quy tắc nghiệp vụ độc lập database |
| Repository test nhanh | H2 hoặc database thật | Mapping và truy vấn portable |
| Native query test | Database production-compatible | Xác minh cú pháp và kết quả riêng engine |
| Migration test | Database production-compatible | Chứng minh migration chạy được |
| Transaction/locking test | Database production-compatible | Kiểm tra commit, rollback và cạnh tranh |
| Performance test | Database gần production | Đo execution plan và thời gian thực tế |

Một pipeline CI thực tế có thể chạy:

1. Unit test nhanh ở mỗi lần thay đổi.
2. JPA test H2 cho mapping và truy vấn portable nếu dự án có lợi từ tốc độ.
3. Integration test bằng Testcontainers cho native query, migration, locking và transaction quan trọng.
4. Một bộ performance/regression test riêng trên môi trường có cấu hình gần production.

Nếu chi phí container chấp nhận được, có thể chạy toàn bộ repository integration tests trên database thật và giảm phụ thuộc vào H2. Quyết định này tùy thời gian CI và mức độ ứng dụng phụ thuộc vào đặc tính database.

## 11. Checklist điều tra khi H2 xanh nhưng production lỗi

Khi một test pass trên H2 nhưng lỗi xuất hiện trên production, hãy kiểm tra theo thứ tự:

1. Test thực tế dùng engine nào? Xem JDBC URL, driver, Spring profile và log khởi tạo datasource.
2. Hibernate đang dùng dialect nào? Xác nhận dialect được auto-detect hoặc cấu hình có phù hợp database thật.
3. Query lỗi là JPQL, derived query, Criteria hay native SQL?
4. Có khác biệt về kiểu dữ liệu, precision, timezone, collation hoặc null ordering không?
5. Schema test được tạo bằng Hibernate hay migration Flyway/Liquibase?
6. Có sequence, identity, trigger, extension hoặc function đặc thù không?
7. Có test nào phụ thuộc vào isolation, row lock, deadlock hoặc concurrency không?
8. Test có rollback trước khi commit hoặc chỉ đọc dữ liệu từ persistence context không?
9. Dữ liệu test có đủ lớn và đủ đa dạng để bộc lộ vấn đề phân trang, index hoặc query plan không?
10. Integration test trên đúng engine/version có tái hiện lỗi không?

Khi tìm ra khác biệt, hãy thêm một regression test chạy trên database production-compatible để ngăn lỗi quay lại. H2 test có thể tiếp tục tồn tại nếu nó cung cấp phản hồi nhanh cho một hành vi portable.

## 12. Những giả định dễ gây kết quả sai lệch

| Giả định | Thực tế |
|---|---|
| H2 ở PostgreSQL mode tương đương PostgreSQL | Mode chỉ hỗ trợ một phần khác biệt; engine vẫn là H2 |
| Repository test xanh chứng minh native SQL production đúng | Cần chạy query trên database đích |
| `ddl-auto=create-drop` chứng minh migration production chạy được | Cần chạy Flyway/Liquibase trên đúng engine |
| Test transaction rollback chứng minh commit thành công | Cần kiểm tra đường commit riêng |
| Test đơn luồng chứng minh locking an toàn | Cần kiểm thử nhiều transaction đồng thời |
| H2 chạy nhanh nghĩa là production query nhanh | Optimizer, index và dữ liệu khác nhau |
| Mapping một entity thành công chứng minh mọi kiểu dữ liệu đúng | Cần kiểm tra precision, timezone, collation và kiểu native |

## Kết luận

H2 là công cụ tốt cho kiểm thử nhanh các hành vi JPA portable, nhưng nó không thay thế database production. Compatibility mode chỉ giúp tương thích một phần cú pháp. SQL dialect, kiểu dữ liệu, schema migration, collation, transaction, locking và query planner vẫn có thể khác đáng kể.

Hãy xác định rõ test đang chạy trên engine nào, giữ H2 cho những kiểm tra phù hợp, và dùng Testcontainers hoặc môi trường integration với đúng database/version cho native query, migration, concurrency và hành vi quan trọng khi commit. Một kết quả QA đáng tin cậy cần phản ánh đúng engine mà ứng dụng sẽ sử dụng khi triển khai.