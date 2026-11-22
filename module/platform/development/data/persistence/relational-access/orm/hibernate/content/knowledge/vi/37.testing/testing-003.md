# Giới hạn khi thay hệ quản trị đích bằng cơ sở dữ liệu trong bộ nhớ khi kiểm thử Hibernate ORM

## 1. Test chạy xanh trên H2 nhưng production lỗi ngay khi deploy

Một dự án Spring Boot dùng Hibernate ORM và PostgreSQL. Để test chạy nhanh, nhóm phát triển cấu hình H2 in-memory:

~~~yaml
spring:
  datasource:
    url: jdbc:h2:mem:testdb;DB_CLOSE_DELAY=-1
    driver-class-name: org.h2.Driver
    username: sa
    password:
  jpa:
    hibernate:
      ddl-auto: create-drop
~~~

Các test repository đều pass. Nhưng khi deploy PostgreSQL, một migration thất bại vì partial index; một query native dùng cú pháp PostgreSQL không chạy; một cột timestamp có timezone được đọc khác kỳ vọng; một constraint mà H2 không mô phỏng giống production cho phép dữ liệu sai.

Đây không nhất thiết là bug của Hibernate. H2 và PostgreSQL là **hai hệ quản trị cơ sở dữ liệu khác nhau**, có parser, dialect, kiểu dữ liệu, transaction behavior, locking, constraint implementation và optimizer riêng.

Một database in-memory rất hữu ích để kiểm thử nhanh persistence logic. Nhưng nếu dùng nó làm bản thay thế hoàn toàn cho database production, test có thể chứng minh một điều kiện trên H2 mà không chứng minh được hành vi tương ứng trên hệ quản trị đích.

Bài học thuộc chương **Kiểm thử**, tập trung vào câu hỏi:

> Khi nào có thể dùng H2/HSQLDB/SQLite để kiểm thử Hibernate, những khác biệt nào có thể làm test sai lệch, và khi nào phải chạy integration test với đúng database production?

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt unit test, repository slice test và integration test với database thật.
2. Giải thích vì sao Hibernate dialect không làm các database tương đương nhau.
3. Nhận diện khác biệt về DDL, SQL types, JSON, UUID, timestamp, collation và generated IDs.
4. Hiểu giới hạn của H2 compatibility mode như `MODE=PostgreSQL`.
5. Nhận biết các khác biệt về constraint, index, transaction, isolation, locking và sequence.
6. Hiểu vì sao test query native, migration và execution plan cần hệ quản trị đích.
7. Cấu hình Spring Boot để test dùng đúng database và không bị thay bằng embedded database.
8. Sử dụng Testcontainers với PostgreSQL hoặc database production tương ứng.
9. Thiết kế test nhanh và test fidelity cao theo test pyramid.
10. Tránh dữ liệu test dùng chung, race condition và khác biệt lifecycle của in-memory database.
11. Chọn những phần cần kiểm thử bằng database thật dựa trên rủi ro.
12. Tổ chức CI để phát hiện lỗi migration/schema/query trước khi deploy.

Ví dụ dùng Java 17+, Spring Boot 3.x, Jakarta Persistence, Hibernate ORM 6.x, Spring Data JPA, H2 và PostgreSQL. Cú pháp cấu hình, phiên bản driver và Testcontainers cần khớp dependency thực tế của dự án.

## 2. In-memory database giải quyết bài toán gì?

Một in-memory database lưu database trong bộ nhớ tiến trình thay vì một database server độc lập. Với H2, ví dụ:

~~~properties
spring.datasource.url=jdbc:h2:mem:orders-test
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
~~~

Ưu điểm:

- Khởi động nhanh, không cần cài database server cho mỗi developer.
- Test có thể tạo schema và dữ liệu fixture trong vài giây.
- Dễ cô lập database theo test suite.
- Phù hợp kiểm tra mapping cơ bản, repository methods, dirty checking và transaction flow đơn giản.
- Có thể chạy ở môi trường CI không có dịch vụ database ngoài.

Nhược điểm:

- Không phải cùng engine với PostgreSQL/MySQL/SQL Server/Oracle.
- Có thể không hỗ trợ SQL extension, type hoặc DDL production.
- Optimizer, execution plans và index behavior khác.
- Locking, isolation, sequences và generated values có thể khác.
- Migration có thể pass trên H2 nhưng fail trên database đích.
- Một số lỗi chỉ xuất hiện với driver, connection pool hoặc server configuration production.

### 2.1. “In-memory” không có nghĩa “không có SQL”

Hibernate vẫn tạo SQL và JDBC driver vẫn thực thi SQL. H2 có parser, type system, optimizer và transaction engine riêng. Việc không cần process database server bên ngoài không khiến nó hiểu mọi SQL của PostgreSQL.

### 2.2. “Test dùng Hibernate” không đồng nghĩa “test dùng database đích”

Hibernate tạo SQL dựa trên mapping, query và dialect; database nhận SQL rồi thực thi theo semantics của chính nó:

~~~text
Entity / JPQL / Criteria
       |
       v
Hibernate ORM + Dialect
       |
       v
SQL + JDBC parameters
       |
       v
Database engine
       |
       v
Rows / locks / constraints / transaction result
~~~

Test với H2 chỉ xác minh toàn bộ đường đi trên **H2**. Nó không tự chứng minh PostgreSQL sẽ cho cùng kết quả.

## 3. Bốn lớp khác biệt cần phân biệt

| Lớp | Ví dụ | In-memory DB có thể khác thế nào? |
|---|---|---|
| ORM mapping | @Column, @JoinColumn, @Version, fetch strategy | Mapping cơ bản có thể hoạt động, nhưng DDL/type generated khác |
| SQL dialect | JSON operators, upsert, sequence syntax, pagination | Parser hoặc function không tương thích |
| Database semantics | Isolation, locks, constraints, collations, generated IDs | Cùng SQL nhưng kết quả/exception/timing khác |
| Operations | Migrations, pool, permissions, extensions, replication | H2 không mô phỏng server topology/configuration |

Một test có thể rất tốt ở lớp mapping nhưng vẫn không đủ ở lớp migration/SQL semantics. Vì vậy không nên gắn nhãn “integration test” rồi cho rằng mọi production behavior đã được xác minh.

### 3.1. Dialect chỉ dịch SQL, không mô phỏng engine

Hibernate PostgreSQLDialect có thể chọn cú pháp sequence, limit/offset và kiểu DDL phù hợp. Nó không biến H2 thành PostgreSQL:

- H2 vẫn kiểm tra SQL bằng parser H2.
- H2 vẫn áp dụng transaction/locking của H2.
- H2 vẫn có type system và optimizer H2.
- Các extension PostgreSQL không tự xuất hiện trong H2.

### 3.2. Cấu hình dialect sai có thể làm test còn kém đại diện hơn

Không nên ép:

~~~properties
spring.jpa.database-platform=org.hibernate.dialect.PostgreSQLDialect
~~~

khi JDBC URL đang trỏ H2 rồi kết luận đã test PostgreSQL. Việc ép dialect có thể khiến Hibernate phát SQL kiểu PostgreSQL mà H2 không hỗ trợ, hoặc DDL không phản ánh đúng cách H2 tự phát hiện. **Dialect và database thực tế phải được cấu hình nhất quán.**

Trong cấu hình thông thường, Hibernate có thể nhận diện dialect từ JDBC metadata. Chỉ cấu hình dialect tường minh khi có lý do cụ thể và đã xác minh version/provider.

## 4. H2 compatibility mode không phải PostgreSQL thu nhỏ

H2 có các compatibility modes, ví dụ:

~~~properties
spring.datasource.url=jdbc:h2:mem:orders-test;MODE=PostgreSQL
~~~

Mode này giúp H2 chấp nhận hoặc mô phỏng một số cú pháp/behavior gần PostgreSQL. Nó **không triển khai đầy đủ mọi tính năng và semantics của PostgreSQL**.

### 4.1. Điều compatibility mode có thể giúp

- Một số cú pháp SQL phổ biến.
- Một số quy tắc đặt tên/kiểu dữ liệu.
- Một số hàm hoặc syntax tương thích theo phiên bản H2.
- Giảm khác biệt khi test repository đơn giản.

Phạm vi chính xác phụ thuộc H2 version và mode được bật.

### 4.2. Điều compatibility mode không bảo đảm

- Tất cả PostgreSQL operators, extensions và casts.
- JSONB semantics/indexes.
- Partial indexes và mọi DDL nâng cao.
- RLS, role privileges và PostgreSQL-specific policies.
- Locking, MVCC, isolation edge cases giống hệt PostgreSQL.
- Query planner và execution plan.
- PL/pgSQL, triggers/functions và extension-specific types.
- Error codes, SQLSTATE và exception timing giống production.

### 4.3. Mode có thể che bug theo cách nguy hiểm

Một test pass trong H2 PostgreSQL mode có thể chỉ chứng minh parser của H2 chấp nhận câu SQL đó. Nó không chứng minh SQL chạy được trên PostgreSQL hoặc có cùng query plan/locking.

Không dùng compatibility mode như bằng chứng duy nhất cho một migration hoặc native query production-specific.

## 5. H2 in-memory database có lifecycle riêng

Một URL H2:

~~~text
jdbc:h2:mem:orders-test
~~~

thường tạo database trong memory gắn với lifecycle connections của database đó. Khi connection cuối cùng đóng, database có thể bị xóa tùy URL/configuration.

### 5.1. DB_CLOSE_DELAY=-1

~~~text
jdbc:h2:mem:orders-test;DB_CLOSE_DELAY=-1
~~~

có thể giữ database sống đến khi JVM kết thúc ngay cả khi không còn connection. Điều này hữu ích khi pool mở/đóng connections trong test, nhưng cũng khiến dữ liệu/schema có thể tồn tại giữa các test trong cùng JVM nếu dùng lại cùng database name.

### 5.2. Tên database dùng chung có thể làm test nhiễm nhau

Nếu mọi test class cùng dùng `orders-test` và schema không được reset:

- Test trước để lại rows.
- Sequence/identity không reset như fixture kỳ vọng.
- Test sau phụ thuộc thứ tự chạy.
- Parallel tests ghi đè hoặc nhìn thấy dữ liệu của nhau.

Có thể dùng database name riêng theo test context, hoặc chủ động reset schema/transaction theo chiến lược rõ.

### 5.3. Parallel test

Hai test dùng cùng in-memory database name có thể chia sẻ database. Dù mỗi test có transaction riêng, DDL, commits hoặc data cleanup có thể xung đột.

Không bật parallel execution mà không thiết kế isolation cho database, schema, fixtures và connection pool.

### 5.4. In-memory database không tự tạo một database cho mỗi test method

Spring TestContext có thể cache ApplicationContext/DataSource giữa các test classes. Nếu URL và context được tái sử dụng, database có thể cũng được tái sử dụng. `@Transactional` rollback mỗi test không tự rollback các thao tác ngoài transaction, DDL hoặc commits được tạo bởi code khác.

## 6. DDL và kiểu dữ liệu khác nhau

Entity:

~~~java
@Entity
@Table(name = "orders")
public class PurchaseOrder {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "total_amount", precision = 19, scale = 2)
    private BigDecimal totalAmount;

    @Column(name = "created_at")
    private Instant createdAt;
}
~~~

Hibernate có thể sinh DDL khác nhau theo dialect:

- Kiểu số decimal.
- Timestamp/date/time.
- Boolean.
- UUID.
- Identity/sequence.
- Binary/text.
- Enum mapping.
- JSON hoặc database-specific types.

Một schema H2 được Hibernate `create-drop` tự tạo không chứng minh migration PostgreSQL thực tế tạo đúng schema.

### 6.1. ddl-auto=create có thể che migration lỗi

Nếu test luôn dùng:

~~~yaml
spring:
  jpa:
    hibernate:
      ddl-auto: create-drop
~~~

Hibernate tạo schema từ entity metadata và bỏ qua việc migration production có chạy được hay không. Một migration thiếu index, sai type hoặc dùng cú pháp sai vẫn không bị phát hiện.

### 6.2. Production schema thường do Flyway/Liquibase sở hữu

Trong hệ thống có migration, test quan trọng nên chạy:

1. Database sạch.
2. Migration từ version đầu tới hiện tại.
3. Hibernate schema validation.
4. Repository/service integration tests.

Hibernate `ddl-auto=validate` chỉ kiểm tra một phần tương thích schema/mapping; nó không xác minh toàn bộ indexes, triggers, RLS policies, grants, functions hoặc query plans.

### 6.3. Không để Hibernate tự sửa schema production

Với schema do migration quản lý, thường dùng:

~~~yaml
spring:
  jpa:
    hibernate:
      ddl-auto: validate
~~~

ở integration test tương ứng. `update` không phải công cụ migration có versioning, review và rollback đầy đủ.

## 7. SQL types: timestamp, timezone và precision

Một khác biệt thường gây bug:

~~~java
private Instant createdAt;
private LocalDateTime scheduledAt;
private OffsetDateTime submittedAt;
~~~

Java time types có ý nghĩa khác nhau:

- Instant: một thời điểm trên timeline UTC.
- LocalDateTime: ngày giờ không có timezone/offset.
- OffsetDateTime: ngày giờ kèm UTC offset.

PostgreSQL có `timestamp without time zone` và `timestamp with time zone` (`timestamptz`); cách lưu/hiển thị và conversion khác với H2.

### 7.1. H2 có thể không bộc lộ lỗi timezone

Test dùng default JVM timezone UTC có thể pass. Production chạy timezone khác hoặc session timezone khác có thể hiển thị/convert giá trị khác kỳ vọng.

### 7.2. Precision khác nhau

Database có thể làm tròn/cắt fractional seconds ở precision khác nhau. Test:

~~~java
Instant original = Instant.parse(
    "2026-03-01T10:20:30.123456789Z");
~~~

có thể không đọc lại đúng nanoseconds sau persist/flush/refresh. Không assert equality nanosecond tuyệt đối nếu database column precision thấp hơn; xác định precision contract và normalize kỳ vọng.

### 7.3. Test theo timezone rõ ràng

- Chọn một chính sách lưu thời gian, thường UTC/Instant cho thời điểm tuyệt đối.
- Cấu hình JVM và JDBC timezone rõ ràng.
- Test với database production.
- Kiểm tra conversion khi query range theo ngày địa phương.
- Không dùng LocalDateTime như một thời điểm toàn cầu nếu business cần timezone.

### 7.4. Date range và DST

H2 và PostgreSQL có thể khác trong cast/date arithmetic hoặc timezone rules theo môi trường. Các báo cáo theo ngày địa phương cần test timezone thực tế, kể cả daylight-saving nếu nghiệp vụ chạy ở vùng có DST.

## 8. Decimal, numeric và rounding

Một entity:

~~~java
@Column(precision = 19, scale = 2, nullable = false)
private BigDecimal amount;
~~~

Không chỉ test:

~~~java
assertEquals(new BigDecimal("10.00"), entity.getAmount());
~~~

cần test:

- Giá trị tối đa theo precision/scale.
- Giá trị vượt precision.
- Nhiều chữ số thập phân.
- Rounding/truncation.
- Arithmetic trong SQL.
- Cast giữa NUMERIC và các kiểu khác.

### 8.1. So sánh BigDecimal

`BigDecimal.equals()` so sánh cả scale; `10.0` và `10.00` không bằng nhau theo equals. Khi business so sánh số tiền, thường dùng compareTo hoặc normalize scale theo contract.

### 8.2. Database có thể từ chối hoặc làm tròn khác

H2 có thể xử lý một số giá trị khác PostgreSQL; production NUMERIC precision overflow có thể tạo lỗi chỉ xuất hiện khi deploy. Dùng Testcontainers để kiểm tra constraint/precision thật.

### 8.3. Tiền tệ không chỉ là BigDecimal

Nếu amount cần currency, model phải giữ currency code và quy tắc scale/rounding theo currency. Đừng kỳ vọng một column DECIMAL tự xác định số chữ số thập phân theo từng tiền tệ.

## 9. UUID, identity và sequence

Generated ID behavior khác nhau theo database/generator.

### 9.1. IDENTITY

~~~java
@Id
@GeneratedValue(strategy = GenerationType.IDENTITY)
private Long id;
~~~

Database tạo ID khi INSERT. Hibernate thường cần thực thi INSERT sớm để lấy generated key, có thể ảnh hưởng flush timing và JDBC insert batching.

### 9.2. SEQUENCE

~~~java
@Id
@GeneratedValue(strategy = GenerationType.SEQUENCE,
                generator = "order_seq")
@SequenceGenerator(
    name = "order_seq",
    sequenceName = "purchase_order_seq",
    allocationSize = 50
)
private Long id;
~~~

PostgreSQL có sequence; H2 cũng có sequence nhưng allocation/DDL/behavior không phải bằng chứng cho mọi database khác.

### 9.3. ID gaps là bình thường

Rollback, sequence allocation/pooling và database behavior có thể tạo gaps. Không test rằng ID luôn liên tiếp 1,2,3 hoặc reset về một số cố định trừ khi test đang kiểm tra cơ chế reset riêng.

### 9.4. UUID type

PostgreSQL có native `uuid`; H2 có type/representation riêng. Native query cast, index size, ordering và driver binding có thể khác. Nếu dùng UUID trong native SQL, test trên PostgreSQL để xác minh parameter binding và casts.

### 9.5. Assigned IDs và Spring Data isNew

Với ID do ứng dụng gán, Spring Data JPA có thể nhận diện entity new theo ID/version/Persistable. H2 không thay đổi logic isNew; nhưng test chỉ với H2 không chứng minh generator/migration production hoạt động đúng. Test assigned ID riêng với entity metadata và DB constraint thực.

## 10. Boolean, enum và string semantics

### 10.1. Boolean representation

Một DB lưu BOOLEAN native, DB khác có thể dùng BIT/NUMBER hoặc mapping khác. Test native SQL và migration không nên giả định mọi dialect có cùng literal/DDL.

### 10.2. Enum ORDINAL nguy hiểm

~~~java
@Enumerated(EnumType.ORDINAL)
private OrderStatus status;
~~~

ORDINAL lưu vị trí enum. Thêm/reorder enum constant có thể đổi ý nghĩa dữ liệu. Đây là rủi ro domain independent of H2; test database thật không tự giải quyết. Thường dùng STRING hoặc converter với stable code theo business contract.

### 10.3. Case sensitivity và collation

Các database khác nhau về:

- So sánh chữ hoa/chữ thường.
- Accent sensitivity.
- Unicode normalization.
- Trailing spaces.
- LIKE/ILIKE.
- Sort order.

Ví dụ query `where email = 'User@example.com'` có thể cho kết quả khác theo collation/case semantics. H2 pass không chứng minh PostgreSQL collation/extension production giống.

### 10.4. Unique email và normalization

Nếu business muốn email không phân biệt hoa thường, hãy thiết kế rõ: normalize ở application, unique index trên lower(email), citext (PostgreSQL extension) hoặc policy phù hợp. Test migration/index trên database đích.

## 11. JSON, arrays, enums native và database extensions

PostgreSQL có JSON/JSONB, arrays, range types, enums, full-text search, operators và extensions. H2 không tái tạo đầy đủ những tính năng này.

### 11.1. JSONB

Native query:

~~~sql
SELECT id
FROM purchase_orders
WHERE metadata ->> 'source' = 'web';
~~~

Toán tử `->>` là PostgreSQL-specific. H2 mode không bảo đảm hỗ trợ cùng semantics. Test query trên PostgreSQL thật.

### 11.2. JSON containment và index

~~~sql
SELECT *
FROM purchase_orders
WHERE metadata @> '{"channel":"web"}'::jsonb;
~~~

`@>`, cast `::jsonb` và GIN indexes là các chi tiết PostgreSQL. Test H2 không xác minh query hoặc index đó.

### 11.3. PostgreSQL arrays

~~~sql
SELECT *
FROM product_catalog
WHERE tags @> ARRAY['fragile'];
~~~

Type binding, operators và array indexes cần database đích.

### 11.4. Extensions

Ví dụ `pg_trgm`, `PostGIS`, `citext`, `pgcrypto` cần extension được cài và migration chạy đúng. Container PostgreSQL phải dùng image có extension cần thiết hoặc image tùy chỉnh đã được kiểm soát.

### 11.5. Test domain mapping vẫn có thể dùng H2

Nếu entity chỉ có scalar fields portable, test mapper/business behavior trên H2 vẫn có ích. Nhưng bất kỳ test nào dựa vào native type/operator/extension phải chạy trên database hỗ trợ feature đó.

## 12. Identity, generated columns và default values

DDL production có thể dùng:

~~~sql
CREATE TABLE purchase_orders (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_number TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    normalized_code TEXT GENERATED ALWAYS AS
        (upper(btrim(order_number))) STORED
);
~~~

H2 có thể hỗ trợ một phần identity/generated columns nhưng cú pháp, restriction và metadata JDBC khác.

### 12.1. Default value ở database

Nếu mapping:

~~~java
@Column(name = "created_at",
        insertable = false,
        updatable = false)
private Instant createdAt;
~~~

Hibernate có thể không ghi column và cần generated-value handling/refresh để đọc giá trị DB default theo mapping. Test với H2 không bảo đảm PostgreSQL driver trả generated value cùng cách.

### 12.2. Generated column

Nếu query native phụ thuộc generated column, test migration và generated expression trên DB đích. Hibernate schema validation có thể không xác minh expression đầy đủ.

### 12.3. Không set ID thủ công trong test rồi kết luận identity generator đúng

Một fixture INSERT id cố định bằng SQL hữu ích cho test data, nhưng không kiểm tra generated identity path. Cần test riêng tạo entity không ID, persist/flush, xác nhận ID được sinh và có thể đọc lại.

## 13. Constraints: UNIQUE, FOREIGN KEY, CHECK và deferred checks

H2 và PostgreSQL có thể khác về chi tiết constraint, error timing và các tính năng nâng cao.

### 13.1. UNIQUE và NULL

Semantics UNIQUE với NULL có khác biệt giữa các database và có thể được điều chỉnh bằng PostgreSQL `NULLS NOT DISTINCT` ở version hỗ trợ. Nếu business cần unique cả khi giá trị NULL, test trên DB đích và thiết kế NOT NULL/partial index/constraint cụ thể.

### 13.2. Partial unique index

~~~sql
CREATE UNIQUE INDEX uq_active_order
ON purchase_orders(organization_id, order_number)
WHERE deleted_at IS NULL;
~~~

Partial indexes là tính năng quan trọng của PostgreSQL. H2 có thể không hỗ trợ đúng syntax/semantics cần thiết. Test migration và concurrent insert conflict bằng PostgreSQL.

### 13.3. CHECK constraint

~~~sql
CHECK (total_amount >= 0)
~~~

H2 có thể thực thi constraint đơn giản, nhưng function/cast/collation/NULL behavior phức tạp có thể khác. Kiểm tra DB đích nếu integrity phụ thuộc expression.

### 13.4. Composite foreign keys

~~~sql
FOREIGN KEY (organization_id, customer_id)
REFERENCES customers(organization_id, id)
~~~

Đây là cách bảo đảm Order và Customer cùng organization. Test H2 chỉ có ý nghĩa nếu schema/engine thực sự hỗ trợ constraint như mong đợi; với PostgreSQL production, nên có test trực tiếp trên PostgreSQL để xác minh DDL và SQLSTATE.

### 13.5. Deferrable constraints

PostgreSQL hỗ trợ một số UNIQUE/FOREIGN KEY constraints có thể DEFERRABLE, cho phép kiểm tra ở cuối transaction thay vì từng statement. H2 không nhất thiết mô phỏng giống. Nếu ứng dụng dựa vào:

~~~sql
SET CONSTRAINTS ALL DEFERRED;
~~~

thì test phải chạy trên PostgreSQL.

### 13.6. Exception timing

Một vi phạm constraint có thể được phát hiện khi INSERT/UPDATE, khi flush hoặc lúc commit tùy loại constraint/database. Test chỉ assert exception ở đúng dòng `save()` trên H2 có thể sai trên PostgreSQL. Nên assert transaction outcome và loại constraint violation theo contract, không phụ thuộc thời điểm exception quá cụ thể nếu DB cho phép deferred checks.

## 14. Indexes, partial indexes và query plans

H2 có optimizer riêng; nó không tạo execution plan giống PostgreSQL.

### 14.1. Một index được khai báo chưa chắc được dùng

~~~sql
CREATE INDEX idx_orders_org_status
ON purchase_orders(organization_id, status);
~~~

H2 có thể chọn index trong fixture nhỏ, PostgreSQL có thể chọn sequential scan vì selectivity thấp hoặc thống kê khác. Điều ngược lại cũng có thể xảy ra.

### 14.2. Partial index

~~~sql
CREATE INDEX idx_active_orders
ON purchase_orders(organization_id, created_at DESC)
WHERE deleted_at IS NULL;
~~~

Nếu production query dựa vào partial index, cần kiểm tra:

- Migration tạo index thành công.
- Predicate query phù hợp với predicate index.
- PostgreSQL planner chọn index với dữ liệu đại diện.
- Write overhead/size được chấp nhận.

### 14.3. EXPLAIN khác database

Không dùng execution plan H2 để kết luận PostgreSQL query nhanh. Trên PostgreSQL:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT ...
FROM purchase_orders
WHERE organization_id = 7
  AND deleted_at IS NULL;
~~~

`ANALYZE` thực thi query. Với DML, cần cẩn thận side effects. Hãy chạy trên test database/fixture phù hợp.

### 14.4. Data distribution quan trọng

Một test database có 10 rows không phản ánh production có 10 triệu rows và skew giữa tenants. Index/plan test cần seed dữ liệu có phân bố gần thực tế hoặc dùng performance environment riêng.

## 15. Transaction và isolation khác nhau

Database in-memory có thể hỗ trợ transaction, nhưng không đồng nghĩa cùng isolation/locking semantics với production.

### 15.1. READ COMMITTED và snapshots

PostgreSQL READ COMMITTED tạo snapshot mới cho mỗi statement. Một transaction chạy hai SELECT có thể thấy dữ liệu committed khác nhau nếu transaction khác commit giữa hai câu.

Một database khác có thể triển khai snapshot/isolation khác. Test H2 không đủ để chứng minh concurrent behavior của PostgreSQL.

### 15.2. REPEATABLE READ

PostgreSQL REPEATABLE READ có semantics MVCC riêng; update conflict/serialization behavior khác với nhiều database. Nếu service dựa vào snapshot nhất quán, chạy test đồng thời trên DB production.

### 15.3. SERIALIZABLE

Serializable có thể abort transaction để tránh anomaly; application phải xử lý retry. Số lần retry và SQLSTATE cụ thể cần test trên engine đích.

### 15.4. Pessimistic locks

JPA:

~~~java
@Lock(LockModeType.PESSIMISTIC_WRITE)
@Query("select o from PurchaseOrder o where o.id = :id")
Optional<PurchaseOrder> findForUpdate(@Param("id") Long id);
~~~

Hibernate tạo SQL lock theo dialect. PostgreSQL có `FOR UPDATE`, `NOWAIT`, `SKIP LOCKED` và các lock modes; behavior khi row không tồn tại, lock timeout và deadlock khác database.

### 15.5. Test lock phải có nhiều connections/transactions

Một test single-thread với một transaction không chứng minh pessimistic locking hoạt động. Cần hai transaction độc lập, coordination bằng latches/barriers và timeout có kiểm soát, chạy trên DB đích.

## 16. Optimistic locking và @Version

~~~java
@Version
private long version;
~~~

Hibernate thường đưa version vào WHERE của UPDATE/DELETE để phát hiện stale state. Đây là cơ chế JPA/Hibernate, nhưng SQL, row-count handling và concurrency timing vẫn chịu database/driver.

### 16.1. Test cơ bản

1. Transaction A và B cùng load Order version 4.
2. A update rồi commit, version thành 5.
3. B update rồi flush/commit.
4. B nhận optimistic-lock conflict.

### 16.2. Vì sao cần DB thật?

Test phải kiểm tra hai transactions thực sự chạy đồng thời trên hai connections. In-memory DB có thể khác scheduling, lock behavior và exception timing; nếu production là PostgreSQL, hãy có concurrency integration test với PostgreSQL.

### 16.3. Không chỉ assert exception class cụ thể ở một tầng

Hibernate có thể ném OptimisticLockException hoặc exception provider-specific; Spring exception translation có thể chuyển thành ObjectOptimisticLockingFailureException/DataAccessException. Test nên đặt assertion tại boundary ứng dụng và xác minh row state cuối cùng.

## 17. SQL functions, operators và syntax

JPQL/HQL portable hơn native SQL, nhưng cũng có function/provider-specific extensions. Native SQL phụ thuộc database trực tiếp.

### 17.1. PostgreSQL-specific syntax

Ví dụ:

~~~sql
INSERT INTO reference_codes(code, label)
VALUES (:code, :label)
ON CONFLICT (code)
DO UPDATE SET label = EXCLUDED.label;
~~~

Đây là PostgreSQL UPSERT. H2 có cú pháp MERGE hoặc các syntax tương thích riêng, nhưng không thể thay thế hoàn toàn semantics của ON CONFLICT, unique index inference và concurrency.

### 17.2. JSON operators

~~~sql
metadata ->> 'channel'
metadata @> '{"channel":"web"}'::jsonb
~~~

cần PostgreSQL.

### 17.3. String/date functions

`ILIKE`, `date_trunc`, `AT TIME ZONE`, `FILTER (WHERE ...)`, `DISTINCT ON`, window functions và các casts có semantics/dialect khác nhau. Một số database hỗ trợ function tương tự nhưng tên, null handling, collation và type coercion có thể khác.

### 17.4. HQL function registration

Hibernate có thể render function theo dialect hoặc function registry. Test H2 có thể dùng function implementation khác. Nếu ứng dụng đăng ký custom SQL function, kiểm tra SQL sinh ra và thực thi trên DB production.

## 18. Pagination và ordering không hoàn toàn portable

Hibernate thường dịch setFirstResult/setMaxResults sang cú pháp pagination của dialect. Tuy nhiên:

- Ordering có thể khác theo collation.
- NULLS FIRST/LAST defaults có thể khác.
- Offset lớn có cost khác.
- Tie-breaking không ổn định nếu ORDER BY không unique.
- Native pagination syntax có thể riêng database.

### 18.1. Luôn có thứ tự ổn định

~~~sql
ORDER BY created_at DESC, id DESC
~~~

Nếu chỉ ORDER BY created_at và nhiều rows cùng timestamp, thứ tự giữa chúng không được bảo đảm. H2 và PostgreSQL có thể trả thứ tự khác nhau.

### 18.2. NULL ordering

Nếu business dựa vào NULLS LAST/FIRST, khai báo rõ trong query/dialect phù hợp hoặc dùng expression portable đã được test. Không dựa vào default của database.

### 18.3. Keyset pagination

Nếu dùng tuple comparison:

~~~sql
WHERE (created_at, id) < (:createdAt, :id)
~~~

thì phải xác minh database đích hỗ trợ semantics/casts phù hợp. Query portable dạng OR có thể dùng thay thế nhưng cần plan/index test.

## 19. Collation, case sensitivity và Unicode

Test với:

~~~text
ABC-001
abc-001
Ánh
Anh
é
e + combining accent
~~~

có thể cho kết quả khác giữa H2 và PostgreSQL tùy collation/locale/extension.

### 19.1. Unique case-insensitive

Một business key không phân biệt hoa thường có thể được enforce bằng:

- Application normalization.
- PostgreSQL functional unique index trên lower(...).
- Extension citext.
- Collation/case-insensitive type theo database.

Nếu production dùng citext hoặc collation riêng, H2 không xác minh được.

### 19.2. Unicode normalization

Hai chuỗi nhìn giống nhau có thể có code points khác. Database collation/normalization không phải lúc nào cũng tự normalize giống nhau. Nếu key nghiệp vụ cần canonical form, chuẩn hóa trước khi persist và test dữ liệu Unicode đại diện.

### 19.3. LIKE và wildcard escaping

Escape %, _ và ký tự escape trong LIKE cần kiểm thử theo SQL/dialect thực tế. Không cho rằng H2 parser và collation mô phỏng production.

## 20. Stored procedures, triggers và generated columns

Nếu production dùng:

- Trigger audit.
- Trigger cập nhật timestamp.
- Stored procedure.
- Function tính giá.
- Generated columns.
- Materialized views.

thì test H2 chỉ hữu ích nếu nó có implementation tương đương, điều thường không có.

### 20.1. Trigger order và transaction

PostgreSQL trigger có timing BEFORE/AFTER/INSTEAD OF và row/statement-level semantics. Trigger có thể gọi function, ghi bảng audit trong cùng transaction. Một trigger lỗi có thể rollback statement/transaction.

Test bằng PostgreSQL để xác minh trigger thật, không thay bằng callback Hibernate nếu mục tiêu là DB trigger.

### 20.2. Hibernate lifecycle callback không tương đương DB trigger

JPA @PreUpdate không chạy khi SQL native/JDBC writer cập nhật trực tiếp. DB trigger có thể áp dụng cho mọi writer có quyền ghi vào bảng. Thay thế trigger bằng callback trong H2 làm test mất chính đặc tính cần xác minh.

### 20.3. Migration phải tạo trigger/function

Test migration cần xác nhận function và trigger tồn tại, đúng owner/permissions và thực thi. `ddl-auto=validate` không đủ để kiểm tra toàn bộ.

## 21. Migration portability: Flyway/Liquibase

Một migration:

~~~sql
CREATE INDEX idx_active_orders
ON purchase_orders(organization_id, created_at)
WHERE deleted_at IS NULL;
~~~

có thể chạy trên PostgreSQL nhưng không chạy trên H2.

### 21.1. Hai chiến lược test migration

**Chiến lược A — Migration portable:** giữ SQL ở tập con chung, chạy trên nhiều DB. Dù vậy vẫn cần test DB đích để kiểm tra DDL thực tế.

**Chiến lược B — Migration theo database:** dùng Flyway locations/profiles riêng hoặc Liquibase contexts/labels cho PostgreSQL-specific DDL, đồng thời test đúng changelog được deploy.

Không nên cố làm một SQL migration giả portable bằng nhiều nhánh khó hiểu nếu feature chỉ có trên database đích.

### 21.2. Test database từ schema sạch

Một migration test tốt:

1. Khởi tạo database rỗng đúng engine/version.
2. Chạy toàn bộ migration từ đầu.
3. Xác nhận schema/constraints/indexes/triggers.
4. Chạy Hibernate schema validation.
5. Thực hiện một số insert/query/update quan trọng.
6. Xác nhận dữ liệu/constraint behavior.

### 21.3. Test nâng cấp từ version cũ

Production thường không deploy trên database rỗng. Cần test:

- Snapshot schema từ release trước.
- Dữ liệu đại diện có edge cases.
- Chạy migration upgrade.
- Xác nhận dữ liệu cũ giữ nguyên/được backfill.
- Chạy app version mới với schema sau migration.

### 21.4. Migration online và lock

PostgreSQL `CREATE INDEX CONCURRENTLY` có transaction restrictions; ALTER TABLE có lock levels khác nhau; backfill lớn có thể tạo WAL/replication lag. H2 không mô phỏng các operational constraints này.

Migration test trên PostgreSQL xác minh cú pháp/behavior, còn performance/lock impact cần môi trường dữ liệu gần production.

## 22. Hibernate schema generation và ddl-auto

### 22.1. create-drop

Phù hợp test mapping nhanh:

~~~yaml
spring:
  jpa:
    hibernate:
      ddl-auto: create-drop
~~~

Nhưng schema được Hibernate tạo mới, không chứng minh migration production.

### 22.2. validate

~~~yaml
spring:
  jpa:
    hibernate:
      ddl-auto: validate
~~~

Hữu ích để kiểm tra entity mapping khớp một phần schema do migration tạo. Không xác minh đầy đủ indexes, triggers, policies, grants hoặc stored procedures.

### 22.3. none

Trong production, schema có thể được migration tool quản lý và Hibernate không tạo/sửa schema. Test với `none` cần bảo đảm migrations đã chạy trước khi SessionFactory khởi động.

### 22.4. Không dùng create-drop để “test migration”

Nếu Hibernate tạo schema trước Flyway, Flyway có thể thấy schema không đúng baseline hoặc migration không chạy theo đường thực tế. Test migration nên để migration tool tạo schema từ đầu, sau đó Hibernate validate.

## 23. Spring Boot test: @DataJpaTest có thể thay DataSource

Spring Boot `@DataJpaTest` là slice test cho JPA. Theo cấu hình mặc định, auto-configuration có thể thay DataSource bằng embedded database nếu tìm thấy H2/HSQL/Derby trên classpath.

Ví dụ:

~~~java
@DataJpaTest
class PurchaseOrderRepositoryTest {
    @Autowired
    PurchaseOrderRepository repository;
}
~~~

Nếu build có H2 dependency, test có thể chạy H2 dù application runtime dùng PostgreSQL.

### 23.1. Không đoán test đang dùng database nào

Hãy kiểm tra:

- JDBC URL thực tế trong test context.
- Driver class.
- Database product/version qua JDBC metadata.
- Hibernate dialect được nhận diện.
- Log Flyway/Liquibase.

Một annotation `@DataJpaTest` không cho biết engine cuối cùng nếu test configuration có override.

### 23.2. Không thay database khi muốn test engine thật

Với Spring Boot versions hỗ trợ:

~~~java
@DataJpaTest
@AutoConfigureTestDatabase(
    replace = AutoConfigureTestDatabase.Replace.NONE
)
class PurchaseOrderRepositoryTest {
}
~~~

`replace = NONE` yêu cầu giữ DataSource được cấu hình. Nó **không tự tạo PostgreSQL**; phải cung cấp DataSource URL/container cho test.

### 23.3. Kiểm tra cấu hình theo version Spring Boot

Property/annotation behavior có thể thay đổi theo Spring Boot version. Đừng copy annotation cũ rồi tin rằng nó vô hiệu mọi test database replacement. Đọc effective test configuration/log khi nâng cấp framework.

## 24. Cấu hình H2 test profile tách biệt

Một profile:

~~~yaml
# application-test-h2.yml
spring:
  datasource:
    url: jdbc:h2:mem:orders-h2;DB_CLOSE_DELAY=-1
    driver-class-name: org.h2.Driver
    username: sa
    password:
  jpa:
    hibernate:
      ddl-auto: create-drop
    properties:
      hibernate:
        show_sql: false
~~~

Test:

~~~java
@ActiveProfiles("test-h2")
@DataJpaTest
class CustomerRepositoryFastTest {
}
~~~

Dùng profile riêng để không vô tình trỏ application-test vào production-like database hoặc ngược lại. Không đặt credentials production trong test profile.

### 24.1. Tên database và isolation

Nếu parallel test hoặc context cache có thể chia sẻ cùng URL, cân nhắc database name duy nhất theo suite/worker. Tuy nhiên random database name làm Spring context cache khó tái sử dụng; cần chọn chiến lược rõ giữa isolation và startup cost.

### 24.2. Dọn dữ liệu

Có thể dùng transaction rollback cho test repository, nhưng:

- DDL có thể commit/không rollback tùy engine.
- Code dùng REQUIRES_NEW có thể commit độc lập.
- Async/background worker có thể ghi ngoài transaction test.
- Test migration cần database/schema riêng.

Đừng coi @Transactional trên test là cleanup universal.

## 25. Testcontainers: chạy đúng engine trong container

Testcontainers khởi động database thật trong Docker cho integration tests. Ví dụ PostgreSQL:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
@SpringBootTest
class OrderPostgresIntegrationTest {
    @Container
    static final PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine")
            .withDatabaseName("orders_test")
            .withUsername("test")
            .withPassword("test");

    @DynamicPropertySource
    static void databaseProperties(
            DynamicPropertyRegistry registry) {
        registry.add(
            "spring.datasource.url",
            postgres::getJdbcUrl
        );
        registry.add(
            "spring.datasource.username",
            postgres::getUsername
        );
        registry.add(
            "spring.datasource.password",
            postgres::getPassword
        );
        registry.add(
            "spring.datasource.driver-class-name",
            postgres::getDriverClassName
        );
    }

    @Test
    void contextStartsAgainstPostgres() {
        // Integration assertions.
    }
}
~~~

Đây là mẫu dùng Testcontainers JUnit Jupiter và Spring Boot. Dependency Testcontainers, Docker environment và PostgreSQL image version phải được khai báo đúng trong project.

### 25.1. Chọn image cùng major version production

Nếu production dùng PostgreSQL 16, test bằng PostgreSQL 16 giúp giảm khác biệt. Image tag nên pin version cụ thể; tránh `latest` khiến test thay đổi ngoài dự kiến.

### 25.2. ServiceConnection trong Spring Boot mới

Với Spring Boot hỗ trợ `@ServiceConnection`, cấu hình có thể ngắn hơn:

~~~java
@Testcontainers
@SpringBootTest
class OrderIntegrationTest {
    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");
}
~~~

Feature `@ServiceConnection` phụ thuộc Spring Boot version và Testcontainers integration module. Nếu không được hỗ trợ, dùng `@DynamicPropertySource` như ví dụ trước.

### 25.3. Testcontainers không chỉ dành cho PostgreSQL

Có thể chạy MySQL, MariaDB, SQL Server, Oracle-compatible images hoặc các services khác nếu image/license/runtime phù hợp. Chọn **đúng engine production**, không chỉ một container database bất kỳ.

### 25.4. Docker là dependency của test

Testcontainers cần Docker-compatible runtime. CI runner phải cung cấp Docker daemon/socket/permissions. Nếu không có, test có thể fail trước khi Spring context khởi tạo; đây là môi trường test chưa sẵn sàng, không phải lỗi Hibernate mapping.

## 26. Test migration bằng Testcontainers

Một migration test nên để Flyway/Liquibase chạy trên database container sạch:

~~~yaml
spring:
  flyway:
    enabled: true
  jpa:
    hibernate:
      ddl-auto: validate
~~~

### 26.1. Vì sao thứ tự quan trọng?

~~~text
Start PostgreSQL container
  -> Tạo database/schema
  -> Flyway migrate
  -> Hibernate build SessionFactory
  -> Validate mapping
  -> Run repository/service tests
~~~

Nếu Hibernate `create-drop` tạo schema trước, test có thể không chạy cùng đường production.

### 26.2. Kiểm tra database objects

Ngoài Hibernate validation, có thể query PostgreSQL catalogs để xác minh:

- Constraint names và definitions.
- Indexes và partial predicates.
- Triggers/functions.
- RLS enabled/policies.
- Column types/nullability/defaults.
- Extensions.

### 26.3. Migration từ version cũ

Có thể tạo một container, chạy migration tới version cũ, seed legacy data, sau đó chạy migration mới nhất và xác nhận data. Đây là cách kiểm tra upgrade path thực tế hơn chỉ chạy database rỗng.

### 26.4. Không phụ thuộc migration checksum thay đổi ngoài ý muốn

Flyway versioned migrations nên immutable sau khi đã áp dụng ở môi trường chia sẻ/production. Test migration từ release trước cần dùng đúng artifacts/versions để xác nhận upgrade, không sửa file migration cũ rồi chạy lại trên DB trống và nghĩ đã test deployment path.

## 27. So sánh H2 và PostgreSQL theo feature

| Feature | H2 in-memory | PostgreSQL | Cách kiểm thử nên dùng |
|---|---|---|---|
| Entity mapping scalar cơ bản | Tốt cho test nhanh | Production engine | H2 + một số Postgres integration |
| JPQL/HQL đơn giản | Thường tốt | Production engine | H2 nhanh, PostgreSQL smoke/integration |
| Native SQL PostgreSQL | Không đầy đủ | Hỗ trợ theo version | PostgreSQL thật |
| JSONB operators/indexes | Không tương đương đầy đủ | Native | PostgreSQL thật |
| Partial indexes | Hỗ trợ khác/không tương đương | Native | PostgreSQL thật |
| PostgreSQL extensions | Không mặc định | Có nếu cài extension | Image/container có extension |
| RLS/policies | Không tương đương | Native | PostgreSQL thật + runtime role |
| Trigger PL/pgSQL | Không tương đương | Native | PostgreSQL thật |
| Flyway PostgreSQL DDL | Có thể fail hoặc sai semantics | Native | Migration Testcontainers |
| Basic UNIQUE/FK/CHECK | Hữu ích | Production semantics | H2 nhanh + PostgreSQL constraint tests |
| Deferrable constraints | Không tương đương đầy đủ | Có | PostgreSQL thật |
| MVCC/locking concurrency | Khác engine | Production semantics | PostgreSQL thật |
| Query plan/index performance | Không đại diện | Production optimizer | PostgreSQL với data đại diện |
| Generated ID cơ bản | Hữu ích | Production generator | H2 nhanh + DB thật |
| Timezone/type precision | Có thể khác | Production type semantics | PostgreSQL thật |

## 28. Unit test, slice test và integration test nên chia thế nào?

Không phải mọi test đều cần Docker. Một test pyramid hợp lý:

~~~mermaid
flowchart TD
    A[Unit tests: domain, validation, mapping] --> B[Repository slice tests]
    B --> C[Integration tests: production DB]
    C --> D[Performance / migration / concurrency suites]
    style A fill:#d9ead3,stroke:#38761d
    style B fill:#fff2cc,stroke:#bf9000
    style C fill:#cfe2f3,stroke:#0b5394
    style D fill:#f4cccc,stroke:#990000
~~~

### 28.1. Unit tests

Kiểm tra:

- Domain invariants.
- Business key normalization.
- Validation.
- Mapping DTO.
- State transitions.
- Service orchestration qua mocks/fakes khi không cần DB semantics.

Không cần H2 cho một test thuần Java.

### 28.2. Repository slice tests

Kiểm tra:

- Spring Data derived queries.
- JPQL/HQL.
- Entity mappings.
- Cascade/orphan behavior.
- Dirty checking.
- Basic transaction rollback.

H2 có thể giúp chạy nhanh, nhưng query/type/constraint nhạy database cần test lại bằng engine thật.

### 28.3. Integration tests với DB production

Kiểm tra:

- Migration thật.
- Native SQL và database-specific functions.
- Constraint/index/trigger/RLS.
- Generated columns/defaults.
- Locking/isolation/concurrency.
- Query semantics và driver binding.

### 28.4. Performance tests

Kiểm tra:

- Execution plans.
- Index selection.
- Query latency dưới dữ liệu lớn.
- Connection pool/lock contention.
- Batch/stream behavior.

Không chạy performance assertions quá nhạy thời gian trong mọi unit test; dùng suite riêng với môi trường ổn định.

## 29. Spring Boot @DataJpaTest với Testcontainers

Một cấu hình:

~~~java
@DataJpaTest
@AutoConfigureTestDatabase(
    replace = AutoConfigureTestDatabase.Replace.NONE
)
@Testcontainers
class PurchaseOrderRepositoryPostgresTest {
    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");

    @Autowired
    PurchaseOrderRepository repository;

    @Test
    void findsOrderByOrganization() {
        // Persist fixture, flush, query and assert.
    }
}
~~~

### 29.1. Test slice có thể không load toàn bộ app config

@DataJpaTest chỉ load phần cần cho JPA slice. Nếu project có Flyway, tenant config, converters hoặc custom Hibernate properties, kiểm tra chúng có được import trong slice test hay cần `@Import`/test configuration riêng.

### 29.2. Migration có được chạy không?

Xác minh Flyway/Liquibase auto-configuration có được kích hoạt trong test slice. Không mặc định rằng migration đã chạy chỉ vì DataSource hoạt động.

### 29.3. @ServiceConnection và replace=NONE

Hai cấu hình có vai trò khác nhau:

- @ServiceConnection cung cấp connection details từ container.
- replace=NONE ngăn test database auto-replacement theo cấu hình tương ứng.

Không dùng chúng như hai cách thay thế nhau.

### 29.4. Test transaction rollback mặc định

@DataJpaTest thường bọc test method trong transaction và rollback sau test. Nếu cần xác minh commit behavior, after-commit events, transaction visibility hoặc nhiều transactions đồng thời, phải tạo transaction boundaries độc lập (ví dụ TransactionTemplate/service proxy) thay vì để một test transaction bao hết.

## 30. Testcontainers lifecycle và thời gian chạy

### 30.1. Static container

Một static @Container thường sống qua các test methods trong một test class. Nó tránh khởi động lại container cho mỗi method, nhưng database state vẫn phải được quản lý.

### 30.2. Container shared giữa nhiều classes

Có thể dùng singleton container pattern hoặc Spring context lifecycle để giảm startup cost. Nhưng cần cẩn thận:

- Spring ApplicationContext có thể giữ DataSource sau khi container đã dừng.
- Parallel test classes có thể dùng chung database.
- Test fixtures có thể nhiễm nhau.
- Container lifecycle phải dài hơn mọi connection/session đang dùng.

### 30.3. Không dùng reusable container một cách vô thức

Testcontainers reusable containers có thể giữ database state giữa các lần chạy local. Điều đó tăng tốc nhưng giảm tính lặp lại nếu cleanup không nghiêm ngặt. CI nên ưu tiên môi trường test sạch và có thể tái lập.

### 30.4. Database name/schema riêng

Có thể tách database/schema theo suite hoặc worker. Nếu dùng schema riêng, mọi migration/search_path/connection settings phải trỏ đúng schema. Với PostgreSQL RLS/session variables, xác minh context không bị rò rỉ qua pool.

## 31. Kiểm thử nhiều database vendors nếu sản phẩm hỗ trợ

Nếu phần mềm chính thức hỗ trợ PostgreSQL và MySQL, không nên dùng H2 làm đại diện cho cả hai.

### 31.1. Vendor-specific test matrix

~~~text
Fast domain tests       -> không cần DB
Portable repository    -> H2 hoặc PostgreSQL, tùy mục tiêu
PostgreSQL native SQL   -> PostgreSQL Testcontainers
MySQL-specific behavior -> MySQL Testcontainers
Migration per vendor   -> đúng vendor/version
Performance            -> production-like environment
~~~

### 31.2. Tránh một test suite dùng syntax của vendor A rồi kỳ vọng vendor B

Nếu query được thiết kế riêng cho PostgreSQL, đánh dấu test thuộc PostgreSQL suite. Nếu ứng dụng tuyên bố hỗ trợ nhiều vendor, cần abstraction/query implementation riêng và tests tương ứng.

### 31.3. Dialect selection

Không chọn dialect dựa vào profile tên “test” mà không xem JDBC URL thực tế. Khi container chạy MySQL, Hibernate phải dùng MySQL dialect phù hợp; khi chạy PostgreSQL, phải dùng PostgreSQL dialect. Thường để Hibernate detect từ metadata nếu không có lý do override.

### 31.4. Database version cũng quan trọng

PostgreSQL 13 và 16, MySQL 5.7 và 8.4 có feature/optimizer differences. Pin version test theo production support matrix, không chỉ pin vendor.

## 32. Kiểm thử transaction và locking với nhiều connections

Một ví dụ test concurrent:

~~~java
ExecutorService pool = Executors.newFixedThreadPool(2);
CountDownLatch bothLoaded = new CountDownLatch(2);
CountDownLatch allowCommit = new CountDownLatch(1);

// Mỗi task gọi một Spring service method tạo transaction riêng.
// Hai transactions load cùng entity, cùng báo bothLoaded,
// sau đó mới được cho phép update/commit.
~~~

Đây là skeleton mô tả phối hợp; không dùng một EntityManager chia sẻ giữa hai threads. Mỗi transaction phải có persistence context/connection riêng.

### 32.1. Không đặt @Transactional lên test method cho mọi concurrency test

Nếu test method giữ một outer transaction, hai service transactions có thể tham gia/không tham gia theo propagation khác mong muốn. Hãy thiết kế rõ transaction boundaries và xác nhận hai connections độc lập.

### 32.2. Test pessimistic lock

1. T1 lấy PESSIMISTIC_WRITE.
2. T2 cố lấy cùng row.
3. T2 phải chờ hoặc timeout theo lock policy.
4. T1 commit/rollback.
5. T2 tiếp tục hoặc nhận lỗi.

Thực hiện trên database đích; H2 không phải bằng chứng cho PostgreSQL lock behavior.

### 32.3. Test SKIP LOCKED

Nếu outbox worker dùng PostgreSQL `FOR UPDATE SKIP LOCKED`, cần chạy đúng SQL trên PostgreSQL. H2 compatibility mode không xác minh semantics hai workers claim rows không trùng.

## 33. Test SQL exception và Spring exception translation

Một database có thể trả SQLState/vendor error code khác. Spring/Hibernate chuyển exception qua các lớp:

~~~text
Database error
  -> JDBC SQLException (SQLState/vendor code)
  -> Hibernate JDBC exception
  -> Spring DataAccessException translation
  -> Application error mapping
~~~

### 33.1. Không assert message database quá cụ thể

Tránh:

~~~java
assertEquals(
    "Unique index or primary key violation",
    exception.getMessage()
);
~~~

Message có thể thay đổi theo version/locale. Assert exception category/constraint behavior phù hợp hơn.

### 33.2. SQLState có thể là contract nội bộ

Nếu code dựa vào PostgreSQL SQLSTATE 23505 để map duplicate key, test H2 không chứng minh branch này. Viết test với PostgreSQL thật.

### 33.3. Exception có thể xuất hiện tại flush hoặc commit

JPA có thể trì hoãn SQL tới flush; deferred constraints có thể được kiểm tra ở commit. Test nên thực hiện transaction thật và xác nhận kết quả cuối, không mặc định `repository.save()` phải ném ngay.

### 33.4. Transaction bị abort sau SQL error

PostgreSQL thường đánh dấu transaction aborted sau một statement error; không thể tiếp tục query bình thường trong transaction đó nếu chưa rollback/savepoint handling đúng. H2 có thể có behavior khác. Test error recovery/retry trên DB đích.

## 34. Kiểm thử upsert và idempotency

PostgreSQL:

~~~sql
INSERT INTO reference_codes(code, label)
VALUES (:code, :label)
ON CONFLICT (code)
DO UPDATE SET label = EXCLUDED.label;
~~~

Không dùng H2 MERGE như bằng chứng rằng PostgreSQL ON CONFLICT có cùng concurrency semantics.

### 34.1. Hai requests cùng key

Test:

1. T1 và T2 đồng thời insert cùng unique business key.
2. Xác định một row duy nhất cuối cùng.
3. Kiểm tra row được update hay request thứ hai nhận conflict theo contract.
4. Kiểm tra side effects không phát hai lần.

### 34.2. Idempotency key

Nếu bảng có:

~~~sql
UNIQUE (organization_id, idempotency_key)
~~~

phải test unique constraint và retry trên PostgreSQL. H2 pass chỉ chứng minh H2 đã thực thi constraint.

## 35. Native query và Stored Procedure phải test trên engine đích

Một repository:

~~~java
@Query(value = """
    SELECT id, order_number
    FROM purchase_orders
    WHERE metadata ->> 'source' = :source
    """, nativeQuery = true)
List<Object[]> findByJsonSource(
    @Param("source") String source
);
~~~

có thể compile trong Java nhưng chỉ chạy trên PostgreSQL.

### 35.1. Repository startup không chứng minh SQL chạy được

Một số native query chỉ được thực thi khi method được gọi; Spring context khởi động thành công không xác minh parser/column/function.

### 35.2. Stored procedure

JPA `@NamedStoredProcedureQuery` và `StoredProcedureQuery` phụ thuộc procedure thật đã tồn tại. Test cần migration tạo procedure trên database đích, thực thi với parameter/output/transaction semantics thật.

### 35.3. Result mapping

Driver có thể trả UUID, JSON, arrays, numeric hoặc timestamp dưới Java/JDBC types khác nhau. Test DTO/SqlResultSetMapping bằng đúng driver production.

## 36. Test database permissions và RLS

Một test container chạy bằng superuser có thể làm policy security trông như không hoạt động.

### 36.1. Tạo runtime role giống ứng dụng

~~~sql
CREATE ROLE app_runtime LOGIN PASSWORD 'test-password';
GRANT CONNECT ON DATABASE orders_test TO app_runtime;
GRANT USAGE ON SCHEMA public TO app_runtime;
GRANT SELECT, INSERT, UPDATE, DELETE
ON ALL TABLES IN SCHEMA public TO app_runtime;
~~~

Các quyền sequence/default privileges cũng có thể cần. Dùng role thực tế phù hợp, không copy grants minh họa một cách rộng rãi vào production.

### 36.2. RLS test

Nếu production dùng PostgreSQL Row-Level Security:

- Bật RLS trong migration.
- Chạy test bằng app_runtime.
- Thiết lập organization context trên connection/transaction.
- Thử SELECT/INSERT/UPDATE cross-tenant.
- Test behavior khi context không được thiết lập.
- Test cache/first-level context không vô tình bypass lần đọc mới.

### 36.3. Table owner và BYPASSRLS

Role owner hoặc role có BYPASSRLS có thể bypass policy tùy cấu hình. Test bằng superuser sẽ không chứng minh app_runtime bị giới hạn đúng. Cân nhắc FORCE ROW LEVEL SECURITY khi phù hợp và test đúng role.

## 37. Test cache trên DB thật

In-memory test có thể không giống production cache topology.

### 37.1. First-level cache

L1 là persistence context của Hibernate; test H2 cũng có L1. Nhưng test security/query semantics phải phân biệt:

- Entity đã managed.
- Entity mới load qua SQL.
- Entity từ L2.
- DTO từ Spring Cache.

### 37.2. Second-level cache

Nếu production dùng Redis/Ehcache/Infinispan hoặc Hibernate L2, H2 repository test không tự kiểm tra invalidation/serialization/tenant isolation. Cần test cache provider và database integration tương ứng khi đây là rủi ro.

### 37.3. Cache key

Một cache key thiếu tenant ID có thể lẫn dữ liệu giữa organizations ngay cả khi database query scoped đúng. Test cache hit cho hai tenants có cùng business key.

### 37.4. Warm/cold cache

Benchmark database/query không nên chỉ chạy sau khi cache đã warm. Cần đo cold path và warm path riêng.

## 38. Database cleanup và fixture strategy

### 38.1. Transaction rollback

Với repository slice test, `@Transactional` và rollback sau method giúp cô lập dữ liệu đơn giản. Nhưng sequence values có thể vẫn tăng, và các operations ngoài transaction không rollback.

### 38.2. @Sql

Spring `@Sql` có thể chạy script setup/cleanup. Xác định execution phase/transaction mode rõ; script DDL hoặc truncate có thể ảnh hưởng test context khác nếu DB được chia sẻ.

### 38.3. TRUNCATE và identity reset

PostgreSQL:

~~~sql
TRUNCATE TABLE order_items, purchase_orders
RESTART IDENTITY CASCADE;
~~~

`RESTART IDENTITY`, CASCADE và lock behavior có semantics database-specific. Không dùng cleanup script PostgreSQL rồi chạy nguyên trên H2.

### 38.4. Test fixtures nên mô tả domain

Dùng fixture builders:

~~~java
PurchaseOrder order = OrderFixture.activeFor(
    organization, customer
);
~~~

nhưng fixture builder không nên che việc test cần kiểm tra generated IDs, constraint violations hoặc migration schema. Với các case đó, dùng JDBC/SQL trực tiếp khi cần bypass application validation có chủ đích.

### 38.5. Tránh test phụ thuộc thứ tự

Không dùng IDs tăng dần giả định; không phụ thuộc dữ liệu test method trước; không share static mutable entities/EntityManagers; không dùng một DB name cho nhiều suites song song mà không isolation.

## 39. CI: chạy test nhanh và test đúng database

Một pipeline:

~~~mermaid
flowchart TD
    A[Commit / Pull request] --> B[Unit tests]
    B --> C[Fast repository tests]
    C --> D[Production DB Testcontainers]
    D --> E[Migration + schema validation]
    E --> F[Native SQL / constraints / transaction tests]
    F --> G[Build artifact]
    G --> H[Staging smoke tests]
~~~

### 39.1. Pull request checks

Có thể chạy:

- Unit tests nhanh.
- H2 tests cho portable repository behavior.
- PostgreSQL Testcontainers cho migrations, native SQL và constraints quan trọng.
- Static/build checks.

### 39.2. Nightly/extended tests

- Concurrency/locking suites.
- Dataset lớn và performance.
- Migration upgrade từ các version cũ.
- RLS/permissions.
- Multi-vendor matrix nếu sản phẩm hỗ trợ nhiều DB.

### 39.3. Docker unavailable

Nếu CI runner không có Docker-compatible runtime, không âm thầm thay PostgreSQL integration tests bằng H2 rồi đánh dấu suite đã pass. Tách job, dùng managed ephemeral DB/service hoặc runner có Docker; report rõ test nào không chạy.

### 39.4. Pin versions

Pin:

- PostgreSQL image major/minor policy.
- JDBC driver.
- Hibernate ORM.
- Spring Boot.
- Testcontainers.
- Migration tool.

Upgrade version là thay đổi cần test lại vì dialect, generated SQL, type mappings và engine behavior có thể đổi.

## 40. Những lúc H2 vẫn là lựa chọn hợp lý

Không cần loại bỏ H2 khỏi mọi dự án.

### 40.1. Mapping cơ bản

- Persist/find entity scalar.
- Basic one-to-many/many-to-one.
- Cascade trong các trường hợp đơn giản.
- Dirty checking cơ bản.
- JPQL query portable.
- Repository derived methods.

### 40.2. Service logic có transaction đơn giản

H2 có thể giúp test nhanh rằng:

- Một service lưu nhiều entities.
- Runtime validation hoạt động.
- Transaction rollback trong trường hợp thông thường.
- Mapping DTO và repository orchestration đúng.

### 40.3. Fast feedback cho developer

H2 có startup cost thấp, hữu ích khi chạy thường xuyên trong IDE. Giữ test scope rõ: test này chứng minh business/persistence logic trên H2, không chứng minh toàn bộ production database compatibility.

### 40.4. Điều kiện để tin cậy

- Không dùng native SQL production-specific trong test H2.
- Migrations/database-specific DDL có test đúng engine.
- Constraint/transaction behavior quan trọng có test đúng engine.
- Có integration suite production DB trong CI.
- Test data và transaction isolation được quản lý rõ.

## 41. Khi nào bắt buộc ưu tiên database production?

Ưu tiên đúng engine khi test:

1. Flyway/Liquibase migrations có cú pháp/vendor-specific.
2. Native SQL, stored procedures, triggers hoặc functions.
3. JSONB, arrays, enums native, extensions, spatial data.
4. Partial indexes, expression indexes, deferrable constraints.
5. RLS, grants, roles và permissions.
6. Locking, SKIP LOCKED, NOWAIT và concurrent transactions.
7. Optimistic/pessimistic locking behavior có yêu cầu production.
8. UPSERT và idempotency dưới concurrency.
9. Query plan, index selection, latency và performance.
10. Timestamp/timezone/precision nhạy cảm.
11. Collation/case-sensitive business keys.
12. Generated columns/defaults và driver-specific type binding.
13. Exception SQLSTATE/vendor code được dùng trong application mapping.
14. Partitioning, sharding hoặc database-specific features.
15. Hành vi cần đảm bảo ở mọi writer ngoài Hibernate.

## 42. Một ví dụ kiểm thử migration và repository với PostgreSQL

### 42.1. Dependencies khái niệm

Project cần:

- Spring Boot test/JPA dependencies.
- PostgreSQL JDBC driver.
- Testcontainers PostgreSQL module.
- Testcontainers JUnit integration.
- Flyway hoặc Liquibase nếu ứng dụng dùng migration.

Dependency coordinates và BOM version phải khớp build hiện tại; không hard-code nhiều version khác nhau cho Testcontainers modules nếu dự án đã quản lý bằng BOM.

### 42.2. Migration tạo constraint

~~~sql
CREATE TABLE organizations (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY
);

CREATE TABLE customers (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    organization_id BIGINT NOT NULL
        REFERENCES organizations(id),
    customer_code VARCHAR(50) NOT NULL,
    UNIQUE (organization_id, customer_code),
    UNIQUE (organization_id, id)
);

CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    organization_id BIGINT NOT NULL,
    customer_id BIGINT NOT NULL,
    order_number VARCHAR(50) NOT NULL,
    UNIQUE (organization_id, order_number),
    FOREIGN KEY (organization_id, customer_id)
        REFERENCES customers(organization_id, id)
);
~~~

### 42.3. Test cùng organization thành công

~~~java
@Test
void acceptsOrderForCustomerInSameOrganization() {
    // Persist Organization 7 và Customer 21.
    // Persist Order organization 7, customer 21.
    // Flush và xác nhận Order được lưu.
}
~~~

### 42.4. Test cross-organization bị DB chặn

~~~java
@Test
void databaseRejectsCrossOrganizationForeignKey() {
    // Seed org 7, org 8, Customer của org 8.
    // Dùng JdbcTemplate/native SQL để INSERT Order org 7
    // tham chiếu customer của org 8.
    // Assert data-integrity exception.
}
~~~

Nếu test qua constructor/service vốn đã từ chối cross-org, nó chỉ kiểm tra application guard. Dùng JDBC trong test constraint để chứng minh **database FK thực sự bảo vệ** khi application validation bị bypass.

### 42.5. Test schema validation

Khởi động Spring context với migration chạy trước Hibernate và:

~~~yaml
spring:
  jpa:
    hibernate:
      ddl-auto: validate
~~~

Điều này giúp phát hiện entity mapping lệch cột/type cơ bản so với schema sau migration. Constraint/index/trigger semantics vẫn cần assertions SQL riêng.

## 43. Một chiến lược test cho dự án nhiều database

Nếu sản phẩm hỗ trợ PostgreSQL production nhưng developer muốn H2 nhanh:

| Suite | Engine | Mục tiêu | Có thể chạy ở đâu? |
|---|---|---|---|
| Unit | Không DB | Domain rules, validation, mapping | Mọi commit |
| Fast persistence | H2 | Mapping/query portable cơ bản | Mọi commit |
| PostgreSQL integration | PostgreSQL container | Migration, native SQL, constraints, type semantics | Pull request/CI |
| PostgreSQL concurrency | PostgreSQL container | Locks, isolation, upsert, optimistic conflict | CI/extended |
| Performance | PostgreSQL gần production | Plans, indexes, throughput, pool | Nightly/release |
| Staging smoke | PostgreSQL deployment-like | Credentials, extensions, configuration, migrations | Pre-release |

Nếu sản phẩm còn hỗ trợ MySQL, thêm suite MySQL tương ứng cho những behavior được cam kết hỗ trợ. Không xem H2 là vendor-neutral oracle.

## 44. Các lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân | Hướng xử lý |
|---|---|---|
| H2 test pass, PostgreSQL migration fail | DDL khác dialect/feature | Test migration bằng PostgreSQL container |
| @DataJpaTest tự dùng H2 | Boot embedded database replacement | Kiểm tra JDBC URL; dùng Replace.NONE khi cần |
| PostgreSQLDialect nhưng URL H2 | Dialect và engine không nhất quán | Cấu hình đúng database hoặc để detect |
| MODE=PostgreSQL vẫn fail JSONB | Compatibility mode không phải engine PostgreSQL | Chạy PostgreSQL thật |
| Test pass khi tạo schema nhưng production thiếu index | ddl-auto=create-drop bỏ qua migration | Flyway/Liquibase migration test + schema assertions |
| Timestamp lệch giờ trên production | Timezone/type conversion khác | Test Instant/timestamptz trên DB đích |
| Decimal overflow chỉ xuất hiện khi deploy | Precision/scale behavior khác | Boundary tests trên DB production |
| Native query chạy H2 nhưng fail PostgreSQL | Syntax/function/operator khác | Test native SQL trên đúng engine |
| Unique key test không bắt được case NULL | NULL uniqueness semantics khác | NOT NULL/constraint policy và DB-specific test |
| Partial unique index migration fail | H2 không hỗ trợ tương đương | PostgreSQL Testcontainers |
| RLS test pass nhưng production lộ data | Test dùng owner/superuser hoặc thiếu context | Test runtime role và connection setting |
| Lock test không tái hiện production | Engine/isolation khác hoặc chỉ một connection | Concurrent transactions trên DB đích |
| Upsert race tạo duplicate | H2 MERGE không giống ON CONFLICT | Test PostgreSQL unique/upsert concurrency |
| Test query count quá thấp | L1/L2 cache warm hoặc data nhỏ | Context mới, cold cache, dataset lớn |
| Test bị nhiễm dữ liệu | H2 DB_CLOSE_DELAY=-1/shared context | DB/schema riêng và cleanup rõ |
| Parallel tests flake | Chia sẻ in-memory DB/schema | Isolate database name/schema/transactions |
| Flyway chạy sau Hibernate create-drop | Thứ tự schema ownership sai | Migration trước, Hibernate validate |
| Exception message test thay đổi | Vendor/version message khác | Assert exception category/SQLSTATE contract |
| Hibernate validate pass nhưng trigger thiếu | Validate không kiểm tra trigger | Query database catalogs/assert migration |
| Performance test H2 nhanh nhưng production chậm | Optimizer/index/scale khác | Benchmark DB thật với dữ liệu đại diện |
| Testcontainers fail trước test | Docker runtime/permissions unavailable | Cung cấp Docker-compatible runner; report suite không chạy |
| Container bị dừng khi Spring context còn dùng | Lifecycle không đồng bộ | Container sống lâu hơn context/connection |
| Test UUID pass nhưng native cast fail | Driver/type binding khác | PostgreSQL UUID integration test |

## 45. Bài thực hành

### Bài A — So sánh H2 và PostgreSQL

1. Tạo một Spring Boot JPA project dùng PostgreSQL production.
2. Cấu hình H2 test profile và PostgreSQL Testcontainers profile.
3. Chạy cùng repository tests trên cả hai.
4. Ghi lại JDBC URL, driver, dialect, product/version.
5. Thử query JPQL portable và native query PostgreSQL.
6. Phân loại test nào có thể giữ ở H2, test nào phải chuyển sang PostgreSQL.

### Bài B — Migration thật

1. Viết Flyway migration tạo partial unique index.
2. Chạy trên H2 và quan sát compatibility.
3. Chạy trên PostgreSQL container.
4. Kiểm tra index predicate qua PostgreSQL catalogs.
5. Chạy duplicate inserts với active/deleted records.
6. Xác nhận conflict behavior theo business contract.

### Bài C — Timestamp và decimal

1. Map Instant vào timestamptz.
2. Persist một giá trị có nanoseconds.
3. Read lại qua PostgreSQL JDBC.
4. Kiểm tra precision contract.
5. Thử JVM/session timezone khác nhau.
6. Thử BigDecimal vượt scale/precision.
7. So sánh kết quả H2 và PostgreSQL.

### Bài D — JSONB và native SQL

1. Tạo column jsonb qua migration.
2. Tạo query dùng `->>` và `@>`.
3. Tạo GIN index.
4. Chạy Testcontainers PostgreSQL.
5. Kiểm tra parameter binding/result mapping.
6. Dùng EXPLAIN để xác minh index với dataset đủ lớn.

### Bài E — Concurrency

1. Tạo hai transactions độc lập.
2. Test optimistic locking @Version.
3. Test PESSIMISTIC_WRITE.
4. Test SKIP LOCKED cho outbox.
5. Test concurrent insert cùng unique key.
6. Xác nhận retry/rollback behavior trên PostgreSQL.

### Bài F — Spring test configuration

1. Viết @DataJpaTest có H2 dependency.
2. Xác nhận database được chọn.
3. Bổ sung Replace.NONE và PostgreSQL container.
4. Xác nhận JDBC metadata là PostgreSQL.
5. Đảm bảo Flyway chạy trước Hibernate validate.
6. Kiểm tra profile test không thể trỏ nhầm production credentials.

### Bài G — Data cleanup và parallelism

1. Bật DB_CLOSE_DELAY=-1 cho H2.
2. Chạy hai test cùng database name và quan sát contamination.
3. Dùng database/schema riêng cho mỗi suite.
4. Chạy tests song song.
5. Kiểm tra sequence, commits và cleanup.
6. Chọn chiến lược phù hợp giữa context reuse và isolation.

### Bài H — CI matrix

1. Tạo job unit/fast H2.
2. Tạo job PostgreSQL Testcontainers.
3. Pin image version.
4. Chạy migration từ schema sạch.
5. Thêm job upgrade từ release schema cũ.
6. Thêm concurrency suite.
7. Báo riêng nếu Docker không sẵn sàng, không đổi sang H2 rồi coi như pass.

## 46. Checklist trước khi tin một database test

1. Test đang chạy trên database product/version nào?
2. JDBC URL, driver và Hibernate dialect có nhất quán không?
3. @DataJpaTest có tự thay DataSource bằng embedded DB không?
4. Test có đang ép PostgreSQLDialect nhưng thực tế chạy H2 không?
5. DDL được tạo bởi Hibernate hay migration production?
6. Flyway/Liquibase đã chạy đúng migrations trên database sạch chưa?
7. Hibernate schema validation có được bật ở integration test phù hợp không?
8. Database-specific types/functions/operators có được test trên đúng engine không?
9. Timezone, precision và decimal boundaries đã được kiểm tra chưa?
10. UNIQUE/FK/CHECK/partial/deferrable constraints có test đúng engine không?
11. Native SQL, stored procedures, triggers và extensions đã được thực thi thật chưa?
12. Transaction isolation, locking và concurrency có nhiều connections/transactions không?
13. Upsert/idempotency đã test race conditions trên DB đích chưa?
14. Query plan/index performance có được đo với data distribution đại diện không?
15. RLS/permissions đã chạy bằng runtime role, không phải superuser chưa?
16. L1/L2/application cache có làm test kết quả sai lệch không?
17. H2 database lifecycle/DB_CLOSE_DELAY có gây nhiễm dữ liệu không?
18. Parallel tests có dùng database/schema riêng hoặc cleanup được kiểm soát không?
19. Exception assertion có phụ thuộc message/vendor code không cần thiết không?
20. Testcontainers image version có pin theo production không?
21. CI có Docker-compatible runtime và report rõ suite không chạy không?
22. Migration upgrade từ version cũ có được kiểm tra không?
23. H2 tests có giới hạn rõ là fast/portable tests không?
24. Có production-database integration suite chạy trước khi merge/release không?

## 47. Tổng kết: in-memory database là công cụ tăng tốc, không phải bản sao production

~~~mermaid
flowchart TD
    A[Chọn loại behavior cần test] --> B{Domain logic không cần DB?}
    B -->|Có| C[Unit test]
    B -->|Không| D{Mapping/query portable cơ bản?}
    D -->|Có| E[H2/HSQL fast repository test]
    D -->|Không| F{Vendor-specific SQL, migration, type, lock, RLS?}
    F -->|Có| G[Đúng DB production bằng Testcontainers]
    F -->|Không rõ| H[Phân tích risk và chạy trên DB đích]
    G --> I[CI migration + integration checks]
    E --> I
    C --> I
~~~

Những nguyên tắc cần nhớ:

1. **H2/HSQLDB/SQLite là database khác production**, dù đều có thể chạy với Hibernate/JDBC.
2. **Hibernate dialect không biến engine này thành engine khác.** Dialect tạo SQL phù hợp; database vẫn tự parse và thực thi SQL theo semantics riêng.
3. **MODE=PostgreSQL chỉ tăng compatibility ở một số tính năng**, không tái tạo JSONB, extensions, RLS, planner, locking và mọi DDL PostgreSQL.
4. **ddl-auto=create-drop không kiểm thử migration production.** Dùng Flyway/Liquibase trên database đúng engine, sau đó Hibernate validate.
5. **Types, precision, timezone, generated IDs, collations và constraints có thể khác.** Test edge cases trên database đích.
6. **Native SQL, triggers, procedures, partial indexes, RLS và vendor-specific functions cần test đúng vendor.**
7. **Transaction/isolation/locking/concurrency không được chứng minh bằng một test single-thread trên H2.** Dùng nhiều transactions/connections trên engine production.
8. **Execution plan và performance chỉ có ý nghĩa khi đo trên database/phiên bản/dữ liệu gần production.**
9. **@DataJpaTest có thể tự thay DataSource.** Xác nhận JDBC metadata và dùng Replace.NONE khi test cần giữ container DataSource.
10. **Testcontainers cho phép chạy đúng database engine trong CI**, đồng thời kiểm tra migration, driver, native SQL và constraints thực.
11. **H2 vẫn hữu ích cho fast feedback** với domain logic, mapping và query portable, miễn là không tuyên bố nó chứng minh production compatibility.
12. **Phân tầng test**: unit nhanh, repository slice, integration đúng DB, rồi performance/migration/concurrency suites.

Mục tiêu không phải thay mọi H2 test bằng container chậm. Mục tiêu là biết chính xác **test nào đang chứng minh điều gì**. Dùng in-memory database để có feedback nhanh cho phần portable; dùng đúng hệ quản trị đích để xác minh migrations, SQL đặc thù, constraints, transactions, locks và performance. Khi ranh giới này rõ, test suite vừa nhanh vừa giảm nguy cơ “xanh trên máy dev, đỏ ở production”.
